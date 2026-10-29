#!/usr/bin/env python3
"""bvh_io.py — read, write and pose a BVH file with numpy; used by contact_bake.py.

A module first (contact_bake.py imports it from this folder), with a selftest of its own:

    bvh_io.py --selftest
    bvh_io.py info FILE.bvh          prints joints, channels, frames, fps and the rest height

Conventions:
  * A rotation channel list is applied in the order written: "Zrotation Xrotation Yrotation"
    is R = Rz @ Rx @ Ry, angles in degrees. Any of the six orders is read and written.
  * A joint's local transform is translate(T) @ R, T = OFFSET + its position channels; for the
    root with three position channels T = the channels alone (absolute), as Blender's importer
    reads it, so a root OFFSET only places the rest. With identity rest orientations (every BVH),
    a joint's world rotation is the product of the locals down from the root, and its world
    position the parent's position plus the parent's world rotation applied to its T.
  * End Sites are kept as an offset on their joint (`end`), never as joints.
  * Units and the up axis are the file's own: nothing is converted here.

API (numpy arrays, F frames, J joints):
    Bvh(names, parents, offsets (J,3), channels [[str]], ends {j: (3,)}, frames (F, C), frame_time)
    parse(text) -> Bvh                      raises BvhError on a malformed file
    load(path) -> Bvh;  Bvh.dump() -> str;  Bvh.save(path)
    Bvh.local_rotations() -> (F, J, 3, 3)   from the rotation channels
    Bvh.local_positions() -> (F, J, 3)      offset + position channels
    Bvh.fk() -> (world_rot (F,J,3,3), world_pos (F,J,3))
    Bvh.set_rotations(local_rot (F,J,3,3), joints=None)   writes rotation channels back, unwrapped
    Bvh.set_positions(pos (F,J,3), joints)  writes position channels (absolute on the root, else
                                            the offset subtracted)
    euler_to_matrix(angles_deg (...,3), order "ZXY") / matrix_to_euler(R, order) -> degrees
    rot_between(a, b) -> the shortest-arc rotation taking direction a onto b, (...,3,3)
    polar(M) -> the nearest rotation to M (3x3 or batched), scale removed

Exit codes (CLI): 0 pass; 1 a refused input or a failed selftest. Requires numpy.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

AXES = {"X": 0, "Y": 1, "Z": 2}


class BvhError(Exception):
    pass


# ----------------------------------------------------------------------------- rotations

def _axis_rot(axis: int, ang: np.ndarray) -> np.ndarray:
    c, s = np.cos(ang), np.sin(ang)
    R = np.zeros(ang.shape + (3, 3))
    i, j = [(1, 2), (2, 0), (0, 1)][axis]
    R[..., axis, axis] = 1.0
    R[..., i, i] = c
    R[..., j, j] = c
    R[..., i, j] = -s
    R[..., j, i] = s
    return R


def euler_to_matrix(angles_deg, order: str) -> np.ndarray:
    a = np.radians(np.asarray(angles_deg, dtype=float))
    R = None
    for n, ch in enumerate(order):
        Ri = _axis_rot(AXES[ch], a[..., n])
        R = Ri if R is None else R @ Ri
    return R


def matrix_to_euler(R, order: str) -> np.ndarray:
    """R = R_i(a) R_j(b) R_k(c) for order "ijk" (three distinct axes); degrees, b in [-90, 90]."""
    R = np.asarray(R, dtype=float)
    i, j, k = (AXES[c] for c in order)
    s = 1.0 if (i, j, k) in ((0, 1, 2), (1, 2, 0), (2, 0, 1)) else -1.0
    b = np.arcsin(np.clip(s * R[..., i, k], -1.0, 1.0))
    a = np.arctan2(-s * R[..., j, k], R[..., k, k])
    c = np.arctan2(-s * R[..., i, j], R[..., i, i])
    # gimbal: |cos b| ~ 0 -> put everything in a, c = 0
    g = np.abs(np.cos(b)) < 1e-6
    if np.any(g):
        a = np.where(g, np.arctan2(s * R[..., k, j], R[..., j, j]), a)
        c = np.where(g, 0.0, c)
    return np.degrees(np.stack([a, b, c], axis=-1))


def polar(M) -> np.ndarray:
    U, _, Vt = np.linalg.svd(np.asarray(M, dtype=float))
    R = U @ Vt
    d = np.linalg.det(R)
    if np.any(d < 0):
        U = U.copy()
        U[..., :, -1] *= np.where(d < 0, -1.0, 1.0)[..., None]
        R = U @ Vt
    return R


def rot_between(a, b) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a / np.maximum(np.linalg.norm(a, axis=-1, keepdims=True), 1e-12)
    b = b / np.maximum(np.linalg.norm(b, axis=-1, keepdims=True), 1e-12)
    v = np.cross(a, b)
    c = np.sum(a * b, axis=-1)
    K = np.zeros(v.shape[:-1] + (3, 3))
    K[..., 0, 1], K[..., 0, 2] = -v[..., 2], v[..., 1]
    K[..., 1, 0], K[..., 1, 2] = v[..., 2], -v[..., 0]
    K[..., 2, 0], K[..., 2, 1] = -v[..., 1], v[..., 0]
    eye = np.broadcast_to(np.eye(3), K.shape)
    f = 1.0 / np.maximum(1.0 + c, 1e-12)
    R = eye + K + (K @ K) * f[..., None, None]
    # opposite directions: a half turn about any axis perpendicular to a
    opp = c < -1.0 + 1e-9
    if np.any(opp):
        ref = np.where(np.abs(a[..., :1]) < 0.9, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]))
        p = np.cross(a, ref)
        p /= np.maximum(np.linalg.norm(p, axis=-1, keepdims=True), 1e-12)
        half = 2.0 * p[..., :, None] * p[..., None, :] - eye
        R = np.where(opp[..., None, None], half, R)
    return R


# ----------------------------------------------------------------------------- the file

class Bvh:
    def __init__(self, names, parents, offsets, channels, ends, frames, frame_time):
        self.names = list(names)
        self.parents = [int(p) for p in parents]
        self.offsets = np.asarray(offsets, dtype=float).reshape(len(self.names), 3)
        self.channels = [list(c) for c in channels]
        self.ends = {int(k): np.asarray(v, dtype=float) for k, v in (ends or {}).items()}
        self.frame_time = float(frame_time)
        for j, p in enumerate(self.parents):
            if p >= j:
                raise BvhError(f"{self.names[j]}: a parent must come before its child")
        self.col = []
        n = 0
        for c in self.channels:
            self.col.append(n)
            n += len(c)
        self.n_channels = n
        fr = np.asarray(frames, dtype=float)
        if fr.ndim != 2 or fr.shape[1] != n:
            raise BvhError(f"frames must be (F, {n}), got {fr.shape}")
        self.frames = fr

    @property
    def fps(self) -> float:
        return 1.0 / self.frame_time if self.frame_time > 0 else 0.0

    @property
    def n_frames(self) -> int:
        return int(self.frames.shape[0])

    def index(self, name: str) -> int:
        return self.names.index(name)

    def children(self, j: int) -> list:
        return [c for c, p in enumerate(self.parents) if p == j]

    def rot_order(self, j: int) -> str:
        return "".join(c[0].upper() for c in self.channels[j] if c.lower().endswith("rotation"))

    def _cols(self, j: int, suffix: str) -> list:
        return [(self.col[j] + n, c[0].upper()) for n, c in enumerate(self.channels[j])
                if c.lower().endswith(suffix)]

    def local_rotations(self) -> np.ndarray:
        F, J = self.n_frames, len(self.names)
        out = np.broadcast_to(np.eye(3), (F, J, 3, 3)).copy()
        for j in range(J):
            cols = self._cols(j, "rotation")
            if cols:
                out[:, j] = euler_to_matrix(self.frames[:, [c for c, _ in cols]], "".join(a for _, a in cols))
        return out

    def _absolute(self, j: int) -> bool:
        return self.parents[j] < 0 and len(self._cols(j, "position")) == 3

    def local_positions(self) -> np.ndarray:
        F, J = self.n_frames, len(self.names)
        out = np.broadcast_to(self.offsets, (F, J, 3)).copy()
        for j in range(J):
            if self._absolute(j):
                out[:, j] = 0.0
            for c, a in self._cols(j, "position"):
                out[:, j, AXES[a]] += self.frames[:, c]
        return out

    def fk(self, local_rot=None, local_pos=None):
        Lr = self.local_rotations() if local_rot is None else local_rot
        Lp = self.local_positions() if local_pos is None else local_pos
        F, J = Lr.shape[:2]
        Wr = np.empty_like(Lr)
        Wp = np.empty((F, J, 3))
        for j in range(J):
            p = self.parents[j]
            if p < 0:
                Wr[:, j] = Lr[:, j]
                Wp[:, j] = Lp[:, j]
            else:
                Wr[:, j] = Wr[:, p] @ Lr[:, j]
                Wp[:, j] = Wp[:, p] + np.einsum("fab,fb->fa", Wr[:, p], Lp[:, j])
        return Wr, Wp

    def set_rotations(self, local_rot, joints=None):
        for j in (range(len(self.names)) if joints is None else joints):
            cols = self._cols(j, "rotation")
            if not cols:
                if not np.allclose(local_rot[:, j], np.eye(3), atol=1e-6):
                    raise BvhError(f"{self.names[j]} has no rotation channels to write")
                continue
            ang = matrix_to_euler(local_rot[:, j], "".join(a for _, a in cols))
            ang = np.degrees(np.unwrap(np.radians(ang), axis=0))
            for n, (c, _) in enumerate(cols):
                self.frames[:, c] = ang[:, n]

    def set_positions(self, pos, joints):
        for j in joints:
            cols = self._cols(j, "position")
            if len(cols) != 3:
                raise BvhError(f"{self.names[j]} has no three position channels to write")
            base = 0.0 if self._absolute(j) else self.offsets[j]
            for c, a in cols:
                self.frames[:, c] = pos[:, j, AXES[a]] - (base if np.isscalar(base) else base[AXES[a]])

    def dump(self, digits: int = 6) -> str:
        out = ["HIERARCHY"]
        fmt = "{:.%df}" % digits

        def num(v):
            s = fmt.format(float(v))
            return "0" if s.strip("-0.") == "" else s.rstrip("0").rstrip(".")

        def walk(j, depth):
            pad = "  " * depth
            out.append(f"{pad}{'ROOT' if self.parents[j] < 0 else 'JOINT'} {self.names[j]}")
            out.append(pad + "{")
            out.append(f"{pad}  OFFSET {' '.join(num(v) for v in self.offsets[j])}")
            out.append(f"{pad}  CHANNELS {len(self.channels[j])} {' '.join(self.channels[j])}".rstrip())
            kids = self.children(j)
            for c in kids:
                walk(c, depth + 1)
            if j in self.ends or not kids:
                e = self.ends.get(j, np.zeros(3))
                out.append(f"{pad}  End Site")
                out.append(pad + "  {")
                out.append(f"{pad}    OFFSET {' '.join(num(v) for v in e)}")
                out.append(pad + "  }")
            out.append(pad + "}")

        roots = [j for j, p in enumerate(self.parents) if p < 0]
        if len(roots) != 1:
            raise BvhError(f"a BVH needs exactly one root, got {len(roots)}")
        # the file order must be depth first from the root: renumber when it is not
        walk(roots[0], 0)
        out.append("MOTION")
        out.append(f"Frames: {self.n_frames}")
        out.append(f"Frame Time: {self.frame_time:.8f}")
        order = self.file_order()
        cols = [self.col[j] + n for j in order for n in range(len(self.channels[j]))]
        for row in self.frames[:, cols]:
            out.append(" ".join(num(v) for v in row))
        return "\n".join(out) + "\n"

    def file_order(self) -> list:
        root = [j for j, p in enumerate(self.parents) if p < 0][0]
        order = []

        def walk(j):
            order.append(j)
            for c in self.children(j):
                walk(c)
        walk(root)
        return order

    def save(self, path) -> None:
        Path(path).write_text(self.dump())


def parse(text: str) -> Bvh:
    tok = text.replace("{", " { ").replace("}", " } ").split()
    if not tok or tok[0].upper() != "HIERARCHY":
        raise BvhError("not a BVH: no HIERARCHY")
    names, parents, offsets, channels, ends = [], [], [], [], {}
    stack = []
    i = 1
    pending_end = False
    try:
        while i < len(tok):
            t = tok[i]
            u = t.upper()
            if u in ("ROOT", "JOINT"):
                names.append(tok[i + 1])
                parents.append(stack[-1] if stack else -1)
                if u == "ROOT" and stack:
                    raise BvhError("ROOT inside a joint")
                offsets.append([0.0, 0.0, 0.0])
                channels.append([])
                i += 2
                if tok[i] != "{":
                    raise BvhError(f"expected {{ after {names[-1]}")
                stack.append(len(names) - 1)
                i += 1
            elif u == "END":
                if tok[i + 1].upper() != "SITE" or tok[i + 2] != "{" or not stack:
                    raise BvhError("malformed End Site")
                pending_end = True
                i += 3
            elif u == "OFFSET":
                v = [float(x) for x in tok[i + 1:i + 4]]
                if pending_end:
                    ends[stack[-1]] = np.array(v)
                else:
                    offsets[stack[-1]] = v
                i += 4
            elif u == "CHANNELS":
                n = int(tok[i + 1])
                channels[stack[-1]] = tok[i + 2:i + 2 + n]
                for c in channels[stack[-1]]:
                    if c[0].upper() not in AXES or not c.lower().endswith(("rotation", "position")):
                        raise BvhError(f"unknown channel {c}")
                i += 2 + n
            elif t == "}":
                if pending_end:
                    pending_end = False
                else:
                    if not stack:
                        raise BvhError("unbalanced }")
                    stack.pop()
                i += 1
            elif u == "MOTION":
                break
            else:
                raise BvhError(f"unexpected token {t!r}")
        if stack or not names:
            raise BvhError("unbalanced hierarchy")
        if tok[i].upper() != "MOTION" or tok[i + 1].upper() != "FRAMES:":
            raise BvhError("no MOTION / Frames:")
        nf = int(tok[i + 2])
        if tok[i + 3].upper() != "FRAME" or tok[i + 4].upper() != "TIME:":
            raise BvhError("no Frame Time:")
        ft = float(tok[i + 5])
        vals = np.array([float(x) for x in tok[i + 6:]], dtype=float)
    except (IndexError, ValueError) as e:
        raise BvhError(f"malformed BVH: {e}") from None
    nc = sum(len(c) for c in channels)
    if vals.size != nf * nc:
        raise BvhError(f"MOTION holds {vals.size} values, expected {nf} x {nc}")
    if not np.all(np.isfinite(vals)):
        raise BvhError("non-finite value in MOTION")
    return Bvh(names, parents, offsets, channels, ends, vals.reshape(nf, nc), ft)


def load(path) -> Bvh:
    try:
        return parse(Path(path).read_text())
    except OSError as e:
        raise BvhError(f"cannot read {path}: {e}") from None


# ----------------------------------------------------------------------------- selftest

def selftest() -> int:
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    rng = np.random.default_rng(3)
    for order in ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"):
        ang = rng.uniform(-80, 80, size=(50, 3))
        R = euler_to_matrix(ang, order)
        back = matrix_to_euler(R, order)
        err = np.abs(euler_to_matrix(back, order) - R).max()
        check(f"euler round trip {order}", err < 1e-9 and np.abs(back - ang).max() < 1e-6, f"{err:.2e}")
    R = euler_to_matrix([[0, 90, 0]], "ZXY")
    check("gimbal decomposes to the same matrix",
          np.abs(euler_to_matrix(matrix_to_euler(R, "ZXY"), "ZXY") - R).max() < 1e-9)
    a = rng.normal(size=(20, 3))
    b = rng.normal(size=(20, 3))
    Rb = rot_between(a, b)
    got = np.einsum("nab,nb->na", Rb, a / np.linalg.norm(a, axis=1, keepdims=True))
    check("rot_between maps a onto b", np.abs(got - b / np.linalg.norm(b, axis=1, keepdims=True)).max() < 1e-9)
    check("rot_between opposite", np.abs(rot_between([0, 0, 1.0], [0, 0, -1.0]) @ [0, 0, 1.0] - [0, 0, -1]).max() < 1e-9)
    check("polar removes scale", np.abs(polar(R[0] * 1.3) - R[0]).max() < 1e-9)

    text = """HIERARCHY
ROOT Hips
{
  OFFSET 0 0 0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  JOINT Leg
  {
    OFFSET 0.1 -0.1 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT Shin
    {
      OFFSET 0 -0.4 0
      CHANNELS 3 Xrotation Yrotation Zrotation
      End Site
      {
        OFFSET 0 -0.4 0
      }
    }
  }
  JOINT Spine
  {
    OFFSET 0 0.1 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    End Site
    {
      OFFSET 0 0.3 0
    }
  }
}
MOTION
Frames: 2
Frame Time: 0.033333
0 0.9 0 0 0 0 0 0 0 0 0 0 0 0 0
0.1 0.9 0 0 0 90 90 0 0 0 0 0 10 0 0
"""
    b = parse(text)
    check("parse names and parents", b.names == ["Hips", "Leg", "Shin", "Spine"] and b.parents == [-1, 0, 1, 0])
    check("fps", abs(b.fps - 30.0) < 0.01)
    Wr, Wp = b.fk()
    check("fk rest", np.allclose(Wp[0, 2], [0.1, 0.4, 0.0]))
    b_off = parse(text.replace("ROOT Hips\n{\n  OFFSET 0 0 0", "ROOT Hips\n{\n  OFFSET 0 0.9 0"))
    check("root position channels are absolute (the root OFFSET places the rest only)",
          np.allclose(b_off.fk()[1], Wp))
    # frame 1: hips yaw 90 about Y, leg pitch 90 about Z (local), shin under it
    ref_leg = Wp[1, 0] + Wr[1, 0] @ np.array([0.1, -0.1, 0])
    check("fk child position", np.allclose(Wp[1, 1], ref_leg))
    b2 = parse(b.dump())
    check("dump round trip", np.allclose(b2.frames, b.frames, atol=1e-6) and b2.names == b.names
          and np.allclose(b2.offsets, b.offsets) and 2 in b2.ends)
    Lr = b.local_rotations()
    b3 = parse(b.dump())
    b3.frames[:, 6:] = 0.0
    b3.set_rotations(Lr, joints=[1, 2, 3])
    check("set_rotations reproduces the pose", np.abs(b3.fk()[1] - Wp).max() < 1e-9)
    bad = []
    for t in ("HIERARCHY\nROOT A\n{\n OFFSET 0 0\n", "nonsense", text.replace("Frames: 2", "Frames: 3"),
              text.replace("Zrotation Xrotation Yrotation\n    JOINT Shin", "Zrotation Xrotation Wrotation\n    JOINT Shin")):
        try:
            parse(t)
            bad.append(False)
        except BvhError:
            bad.append(True)
    check("malformed input refused", all(bad), str(bad))
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "a.bvh"
        b.save(p)
        check("save and load", load(p).n_frames == 2)

    ok = all(c["ok"] for c in checks)
    print(json.dumps({"selftest": "pass" if ok else "fail", "checks": len(checks),
                      "failed": [c for c in checks if not c["ok"]]}, indent=1))
    return 0 if ok else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("--selftest", "selftest"):
        return selftest()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("cmd", choices=["info"])
    p.add_argument("bvh")
    a = p.parse_args(argv)
    try:
        b = load(a.bvh)
    except BvhError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    _, Wp = b.fk()
    print(json.dumps({"ok": True, "joints": len(b.names), "frames": b.n_frames, "fps": round(b.fps, 4),
                      "root": b.names[b.file_order()[0]],
                      "position_channels": [b.names[j] for j in range(len(b.names)) if b._cols(j, "position")],
                      "names": b.names}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
