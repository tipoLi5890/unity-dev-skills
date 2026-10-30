#!/usr/bin/env python3
"""layout.py — the two-camera frame: compose renders into it, split video frames, map pixels to metres and back.

Ported from patch-gg/anymove (https://github.com/patch-gg/anymove), mocap/layout.py and the layout half of
blender/common.py, commit 7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0.
Changes from upstream: the module-level constants and the MOCAP_CREATURE environment variable became a `Layout`
object read from a rig_info.json "layout" block or a character.json "layout" block, so every stage takes the frame
from one file; a humanoid default (1376 x 768, 16:9 at 768p, both sides multiples of 32, front and side views of
688 px each, the ground near the bottom) replaces the wolf's 1280 x 720; a CLI composes the reference frame
(upstream tools/compose_ref.py) and checks a layout; --selftest added. The projection formulas are unchanged.

One frame holds two orthographic views at one scale. Front view (left, W_FRONT px) looks along +Y at the face:
u grows with X (the character's left, +X, is on the viewer's right). Side view (right, W_SIDE px) looks along +X
at the right flank: u grows with -Y, so a character facing -Y faces right. In both, v grows downward with -Z and
the ground (z = 0) is row GROUND_V. A joint at height z sits on the same row in both halves: that is what makes two
views enough for 3D (x from the front, y from the side, z from both) and what the agreement check measures.

usage:
    layout.py show [--rig-info RIG_INFO.json | --character CHARACTER.json] [--height 1.7]
    layout.py compose FRONT.png SIDE.png OUT.png [--rig-info RIG_INFO.json | --character CHARACTER.json]
    layout.py --selftest
Prints one JSON object. Exit codes: 0 done (or selftest passed), 2 a layout check failed (a side that is not a
multiple of 32, renders that do not match the layout), 1 refused input or a failed selftest.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

BG, FLOOR, DIVIDER = (128, 130, 134), (152, 154, 158), (34, 34, 38)
# a reading's heatmap peak under this is not trusted: detect's mean-confidence gate and the solve's agreement mask
MIN_CONF = 0.3
# The humanoid default: 16:9 at 768p with both sides multiples of 32 (H3 I2V takes width/height in steps of 32;
# confirm against /object_info before the first run, see reference/two-camera.md).
H_DEFAULT, W_FRONT_DEFAULT, W_SIDE_DEFAULT, GROUND_V_DEFAULT = 768, 688, 688, 688
# metres of frame above the ground per metre of character height: room for a jump with the arms raised
HEADROOM = 1.53


@dataclass(frozen=True)
class Layout:
    H: int = H_DEFAULT
    W_FRONT: int = W_FRONT_DEFAULT
    W_SIDE: int = W_SIDE_DEFAULT
    M_PER_PX: float = 1.7 * HEADROOM / GROUND_V_DEFAULT
    GROUND_V: int = GROUND_V_DEFAULT

    @property
    def W(self) -> int:
        return self.W_FRONT + self.W_SIDE

    @property
    def Z_CENTER(self) -> float:
        return (self.GROUND_V - self.H / 2) * self.M_PER_PX

    def as_dict(self) -> dict:
        d = asdict(self)
        d.update({"W": self.W, "Z_CENTER": self.Z_CENTER, "Y_CENTER": 0.0, "X_CENTER": 0.0})
        return d

    @classmethod
    def humanoid(cls, height_m: float = 1.7, headroom: float = HEADROOM) -> "Layout":
        return cls(M_PER_PX=round(height_m * headroom / GROUND_V_DEFAULT, 7))

    @classmethod
    def from_dict(cls, d: dict | None) -> "Layout":
        d = d or {}
        base = cls()
        return cls(H=int(d.get("H", base.H)), W_FRONT=int(d.get("W_FRONT", base.W_FRONT)),
                   W_SIDE=int(d.get("W_SIDE", base.W_SIDE)), M_PER_PX=float(d.get("M_PER_PX", base.M_PER_PX)),
                   GROUND_V=int(d.get("GROUND_V", base.GROUND_V)))

    @classmethod
    def from_rig_info(cls, info: dict) -> "Layout":
        return cls.from_dict(info.get("layout"))

    def checks(self) -> list:
        """Gates a video model's canvas needs: both sides multiples of 32, 16:9 within 1 %."""
        return [
            {"name": "layout.width_step_32", "value": self.W, "limit": "multiple of 32", "pass": self.W % 32 == 0},
            {"name": "layout.height_step_32", "value": self.H, "limit": "multiple of 32", "pass": self.H % 32 == 0},
            {"name": "layout.aspect_16_9", "value": round(self.W / self.H, 4), "limit": "16/9 within 1 %",
             "pass": abs(self.W / self.H / (16 / 9) - 1) <= 0.01},
            {"name": "layout.ground_in_frame", "value": self.GROUND_V, "limit": f"< {self.H}",
             "pass": 0 < self.GROUND_V < self.H},
        ]

    # --- the frame ---------------------------------------------------------------------------------------------
    def compose(self, front_rgba, side_rgba, bg=BG, floor=FLOOR, divider=DIVIDER):
        """Alpha-composite the two RGBA renders over the studio backdrop (grey wall, lighter floor band, divider)."""
        out = np.zeros((self.H, self.W, 3), np.float32)
        out[:] = bg
        out[self.GROUND_V:] = floor
        for img, x0 in ((front_rgba, 0), (side_rgba, self.W_FRONT)):
            img = img.astype(np.float32)
            a = img[..., 3:4] / 255.0
            h, w = img.shape[:2]
            out[:h, x0:x0 + w] = img[..., :3] * a + out[:h, x0:x0 + w] * (1 - a)
        out[:, self.W_FRONT - 2:self.W_FRONT + 2] = divider
        return out.clip(0, 255).astype(np.uint8)

    def split(self, frame):
        """A layout-sized frame (resize first if needed) into its front and side views."""
        return frame[:, :self.W_FRONT], frame[:, self.W_FRONT:]

    def project(self, p):
        """World points (..., 3) to pixel coordinates in each view: front (u, v) and side (u, v)."""
        p = np.asarray(p, np.float64)
        v = self.H / 2 - (p[..., 2] - self.Z_CENTER) / self.M_PER_PX
        front = np.stack([self.W_FRONT / 2 + p[..., 0] / self.M_PER_PX, v], -1)
        side = np.stack([self.W_SIDE / 2 - p[..., 1] / self.M_PER_PX, v], -1)
        return front, side

    def unproject_front(self, uv):
        """Front-view pixels to (x, z) in metres."""
        uv = np.asarray(uv, np.float64)
        return np.stack([(uv[..., 0] - self.W_FRONT / 2) * self.M_PER_PX,
                         self.Z_CENTER + (self.H / 2 - uv[..., 1]) * self.M_PER_PX], -1)

    def unproject_side(self, uv):
        """Side-view pixels to (y, z) in metres."""
        uv = np.asarray(uv, np.float64)
        return np.stack([-(uv[..., 0] - self.W_SIDE / 2) * self.M_PER_PX,
                         self.Z_CENTER + (self.H / 2 - uv[..., 1]) * self.M_PER_PX], -1)


def load_layout(rig_info: str | None = None, character: str | None = None, height: float | None = None) -> Layout:
    if rig_info:
        return Layout.from_rig_info(json.loads(Path(rig_info).read_text(encoding="utf-8")))
    if character:
        c = json.loads(Path(character).read_text(encoding="utf-8"))
        if "layout" in c:
            return Layout.from_dict(c["layout"])
        return Layout.humanoid(float(c.get("height_m", height or 1.7)))
    return Layout.humanoid(height or 1.7)


def _read_rgba(path: str):
    import cv2  # lazy: only compose needs it
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"cannot read {path}")
    if img.ndim == 2:
        img = np.dstack([img, img, img, np.full_like(img, 255)])
    if img.shape[2] == 3:
        img = np.dstack([img, np.full(img.shape[:2], 255, img.dtype)])
    return img[..., [2, 1, 0, 3]]


def selftest() -> int:
    checks = []

    def check(name, cond):
        checks.append({"name": name, "pass": bool(cond)})

    L = Layout.humanoid(1.7)
    check("default is 1376 x 768", (L.W, L.H) == (1376, 768))
    check("default passes its checks", all(g["pass"] for g in L.checks()))
    check("a 1365-wide frame fails the step gate", not Layout(W_FRONT=682, W_SIDE=683).checks()[0]["pass"])
    check("a square frame fails the aspect gate", not Layout(W_FRONT=384, W_SIDE=384).checks()[2]["pass"])
    check("a 760-high frame fails the height step gate", not Layout(H=760).checks()[1]["pass"])
    check("a ground row below the frame fails ground_in_frame", not Layout(GROUND_V=800).checks()[3]["pass"])
    p = np.array([[0.2, -0.3, 1.1], [0.0, 0.0, 0.0], [-0.4, 0.5, 2.0]])
    f, s = L.project(p)
    xz, yz = L.unproject_front(f), L.unproject_side(s)
    check("front round trip", np.allclose(xz, p[:, [0, 2]]))
    check("side round trip", np.allclose(yz, p[:, [1, 2]]))
    check("ground on row GROUND_V", np.isclose(f[1, 1], L.GROUND_V) and np.isclose(s[1, 1], L.GROUND_V))
    check("same row in both views", np.allclose(f[:, 1], s[:, 1]))
    check("+X is on the front view's right", f[0, 0] > L.W_FRONT / 2)
    check("-Y (facing) is on the side view's right", s[0, 0] > L.W_SIDE / 2)
    check("character fits with headroom", L.GROUND_V * L.M_PER_PX >= 1.7 * 1.5)
    # dragon rig_info layout reproduces the upstream Z_CENTER
    D = Layout.from_dict({"H": 720, "W_FRONT": 640, "W_SIDE": 640, "M_PER_PX": 0.006875, "GROUND_V": 630})
    check("upstream Z_CENTER", D.Z_CENTER == (630 - 720 / 2) * 0.006875)
    fr = np.zeros((L.H, L.W_FRONT, 4), np.uint8); fr[100:200, 100:200] = (255, 0, 0, 255)
    sd = np.zeros((L.H, L.W_SIDE, 4), np.uint8)
    img = L.compose(fr, sd)
    check("compose size", img.shape == (L.H, L.W, 3))
    check("compose keeps the render", tuple(img[150, 150]) == (255, 0, 0))
    check("compose floor band", tuple(img[L.H - 1, L.W - 10]) == FLOOR)
    check("compose divider", tuple(img[10, L.W_FRONT]) == DIVIDER)
    a, b = L.split(img)
    check("split widths", a.shape[1] == L.W_FRONT and b.shape[1] == L.W_SIDE)
    try:
        import cv2
    except ImportError:
        cv2 = None
    if cv2 is not None:   # compose's render_sizes gate, through the CLI
        import contextlib, io, tempfile
        with tempfile.TemporaryDirectory() as td:
            cv2.imwrite(f"{td}/f.png", np.zeros((L.H, L.W_FRONT, 4), np.uint8))
            cv2.imwrite(f"{td}/s.png", np.zeros((L.H, L.W_SIDE, 4), np.uint8))
            cv2.imwrite(f"{td}/small.png", np.zeros((L.H // 2, L.W_SIDE // 2, 4), np.uint8))
            with contextlib.redirect_stdout(io.StringIO()):
                good = main(["compose", f"{td}/f.png", f"{td}/s.png", f"{td}/o.png"])
                bad = main(["compose", f"{td}/f.png", f"{td}/small.png", f"{td}/o2.png"])
            check("compose CLI writes the frame, exit 0", good == 0 and cv2.imread(f"{td}/o.png").shape[:2] == (L.H, L.W))
            check("a half-size side render fails layout.render_sizes, exit 2", bad == 2)
    ok = all(c["pass"] for c in checks)
    print(json.dumps({"tool": "layout.py", "cv2_checks": cv2 is not None, "selftest": "pass" if ok else "fail", "checks": len(checks),
                      "failed": [c["name"] for c in checks if not c["pass"]]}))
    return 0 if ok else 1


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv or argv[:1] == ["selftest"]:
        return selftest()
    ap = UsageParser(prog="layout.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("show", "compose"):
        sp = sub.add_parser(name)
        if name == "compose":
            sp.add_argument("front"); sp.add_argument("side"); sp.add_argument("out")
        sp.add_argument("--rig-info"); sp.add_argument("--character"); sp.add_argument("--height", type=float)
    a = ap.parse_args(argv)
    try:
        L = load_layout(a.rig_info, a.character, a.height)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"tool": "layout.py", "ok": False, "error": f"refused: {exc}"})); return 1
    gates = L.checks()
    out = {"tool": "layout.py", "op": a.cmd, "layout": L.as_dict(), "gates": gates}
    if a.cmd == "compose":
        try:
            import cv2
            f, s = _read_rgba(a.front), _read_rgba(a.side)
        except (ImportError, ValueError) as exc:
            print(json.dumps({**out, "ok": False, "error": f"refused: {exc}"})); return 1
        size_ok = f.shape[:2] == (L.H, L.W_FRONT) and s.shape[:2] == (L.H, L.W_SIDE)
        gates.append({"name": "layout.render_sizes", "value": [list(f.shape[:2]), list(s.shape[:2])],
                      "limit": [[L.H, L.W_FRONT], [L.H, L.W_SIDE]], "pass": size_ok})
        if size_ok:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(a.out, L.compose(f, s)[..., ::-1])
            out["out"] = a.out
    out["ok"] = all(g["pass"] for g in gates)
    print(json.dumps(out))
    return 0 if out["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
