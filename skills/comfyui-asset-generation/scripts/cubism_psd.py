#!/usr/bin/env python3
"""cubism_psd.py — a Cubism-ready layered PSD from layer_split.py's layers and fills.

  cubism_psd.py LAYERS_DIR --fills FILLS_DIR/fills.json --out OUT_DIR [--name Runner2D]
  cubism_psd.py --selftest          offline: a synthetic head, the split rules, the PSD read back

Live2D Cubism builds blinks, gaze and lip motion by deforming separate drawings, so the face is
split the way its manual asks: one part per layer, the hidden parts drawn. The fills must include
face_blank (layer_split.py fills --cubism). The face is split on the 1024 px head crops, where an
eye is several times wider than on the canvas, and each part is scaled back with soft edges:
  face          the blank face fill (bald, no eyes, brows or mouth)
  eye_white_*   drawn whole under the iris, so the iris can move
  iris_*        the iris, its cut-off top completed to its convex hull
  eyelash_*     the dark lid line above the eye
  brow_*        from the bald fill: complete where the fringe hid it
  nose, mouth_line, mouth_inside (hidden: the open mouth's inside, shown by the mouth parameter)
  body          the split's hair, arms, hands, torso, pelvis, legs and feet, unchanged
Sides are _R/_L (front, the character's own) or _near (side view). Folders follow the depth
order (Arms, Body, Head with Hair, Face and Mouth, Legs; a side view's far limbs go last).

Writes OUT/<name>_cubism.psd (8-bit RGB, PSD version 1: Cubism documents PSD, not PSB), the
layer PNGs, manifest.json and cubism.gate.json (gate/1): cubism.composite_iou >= 0.99 and
cubism.composite_px40 <= 0.005 against the source; cubism.layers <= 100 (the FREE edition's
ArtMesh cap); cubism.names unique; cubism.format (read back: version 1, 8 bit, RGB);
cubism.mouth_hidden. Never rename a layer after the model is built: Cubism re-imports by name.

Exit codes: 0 written, gates passed; 1 usage error or missing inputs; 2 a gate failed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CROP = 1024


def _np():
    import numpy as np
    return np


def _ndi():
    from scipy import ndimage as ndi
    return ndi


def ls():
    sys.path.insert(0, str(HERE))
    import layer_split
    return layer_split


def hull_fill(m):
    """The convex hull of a mask, filled."""
    np = _np()
    from PIL import Image, ImageDraw
    ys, xs = np.nonzero(m)
    if len(xs) < 4:
        return m
    from scipy.spatial import ConvexHull
    pts = np.c_[xs, ys]
    try:
        h = ConvexHull(pts)
    except Exception:
        return m
    im = Image.new("L", (m.shape[1], m.shape[0]), 0)
    ImageDraw.Draw(im).polygon([tuple(map(float, pts[i])) for i in h.vertices], fill=1)
    return np.asarray(im).astype(bool) | m


class Crop:
    """The head box on the canvas <-> the 1024 px crop the head fills were made in."""

    def __init__(self, box, W, H, size=CROP):
        x0, y0, x1, y1 = box
        self.side = max(x1 - x0, y1 - y0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        self.sx0, self.sy0 = int(round(cx - self.side / 2)), int(round(cy - self.side / 2))
        self.W, self.H, self.size = W, H, size

    def to_crop(self, canvas_rgba):
        np = _np()
        side, sx0, sy0 = self.side, self.sx0, self.sy0
        sq = np.zeros((side, side, 4), np.float32)
        ax0, ay0 = max(sx0, 0), max(sy0, 0)
        ax1, ay1 = min(sx0 + side, self.W), min(sy0 + side, self.H)
        sq[ay0 - sy0:ay1 - sy0, ax0 - sx0:ax1 - sx0] = canvas_rgba[ay0:ay1, ax0:ax1]
        return ls().resize_rgba(sq, self.size, self.size)

    def to_canvas(self, crop_rgba):
        return ls().place(crop_rgba, (self.sx0, self.sy0, self.side), self.W, self.H)


def face_parts(src, bald, blank, mouth_open, eyes_m, mouth_m, head_m, view):
    """Crop-resolution parts: {name: (mask, picture)}. src/bald/blank/mouth_open are RGBA crops,
    the masks booleans in the same crop."""
    np, ndi = _np(), _ndi()
    L = ls()
    H, W = eyes_m.shape
    yy, xx = np.mgrid[:H, :W]
    rgb = bald[..., :3]
    mx, mn = rgb.max(-1), rgb.min(-1)
    lum = L.luma(rgb)
    parts = {}
    lab, n = ndi.label(ndi.binary_dilation(eyes_m, iterations=4))
    eyes = sorted([(lab == k) & eyes_m for k in range(1, n + 1)], key=lambda m: -m.sum())
    eyes = [m for m in eyes if m.sum() > 0.15 * eyes[0].sum()][:2] if eyes else []
    eyes.sort(key=lambda m: np.nonzero(m)[1].mean())
    names = (["R", "L"] if len(eyes) == 2 else ["near"]) if view == "front" else ["near"] * len(eyes)
    tops = []
    for side, em in zip(names, eyes):
        white = em & (mn > 175) & (mx - mn < 50)
        dark = em & (lum < 80)
        ys = np.nonzero(white.any(1))[0]
        ytop = int(ys.min()) if len(ys) else int(np.nonzero(em.any(1))[0].min())
        tops.append((side, ytop, em))
        whole = hull_fill(white) & ndi.binary_dilation(em, iterations=2)   # the opening, iris included
        iris = ndi.binary_opening(whole & ~white, iterations=2)
        iris = L.largest(iris) if iris.any() else iris
        iris = hull_fill(iris) & whole
        wc = np.median(rgb[white], 0) if white.any() else np.array([245.0, 245, 245])
        wimg = np.zeros_like(bald)
        wimg[..., :3] = wc
        wimg[..., 3] = 255
        parts[f"eye_white_{side}"] = (whole | iris, wimg)
        parts[f"iris_{side}"] = (iris, bald)
        lash = ndi.binary_dilation(em & (lum < 90) & ~whole, iterations=1) & em & ~whole
        parts[f"eyelash_{side}"] = (lash, bald)
        cx = np.nonzero(em)[1].mean()
        ew = np.ptp(np.nonzero(em)[1]) + 1
        bm = (lum < 110) & (bald[..., 3] > 127) & (yy < ytop - 4) & (yy > ytop - 1.2 * ew) & \
            (np.abs(xx - cx) < 0.9 * ew)
        bm = ndi.binary_opening(bm, iterations=2)
        if bm.any():
            bm = L.largest(bm)
            parts[f"brow_{side}"] = (ndi.binary_dilation(bm, iterations=2) & (bald[..., 3] > 127), bald)
    feat = np.zeros_like(eyes_m)
    for m, _ in parts.values():
        feat |= m
    face = (blank[..., 3] > 127) & head_m
    parts["face"] = (face, blank)
    mdark = mouth_m & (L.luma(src[..., :3]) < 120)
    parts["mouth_line"] = (ndi.binary_dilation(mdark, iterations=2) & mouth_m, src)
    mtop = int(np.nonzero(mouth_m.any(1))[0].min()) if mouth_m.any() else H // 2
    inside = (np.abs(mouth_open[..., :3] - blank[..., :3]).max(-1) > 40) & (mouth_open[..., 3] > 127) & \
        ndi.binary_dilation(mouth_m, iterations=12)
    inside = ndi.binary_fill_holes(ndi.binary_opening(inside, iterations=2))
    if inside.any():
        inside = L.largest(inside)
    parts["mouth_inside"] = (inside, mouth_open)
    eye_bot = max((int(np.nonzero(m.any(1))[0].max()) for _, _, m in tops), default=H // 3)
    nose = (np.abs(src[..., :3] - blank[..., :3]).max(-1) > 30) & (yy > eye_bot + 4) & (yy < mtop - 2) & head_m \
        & ~feat & ~ndi.binary_dilation(mouth_m, iterations=3) & (src[..., 3] > 127)
    nose = ndi.binary_opening(nose, iterations=1)
    if nose.any():
        parts["nose"] = (L.largest(ndi.binary_dilation(nose, iterations=2), keep_frac=0.2) & head_m, src)
    return parts, names


def build(layers_dir: Path, fills_path: Path, out: Path, name="Runner2D") -> dict:
    np = _np()
    L = ls()
    rig = json.loads((layers_dir / "rig2d.json").read_text(encoding="utf-8"))
    fills = json.loads(fills_path.read_text(encoding="utf-8"))
    fd = fills_path.parent
    if "face_blank" not in fills["fills"]:
        raise L.Refused("fills.json has no face_blank: run layer_split.py fills --cubism")
    W, H, view = rig["width"], rig["height"], rig["view"]
    crop = Crop(fills["head_box"], W, H)
    S = L.load(fd / fills["source"])
    lay = {n: L.load(layers_dir / f"{n}.png") for n in rig["layers"]}
    src_c = crop.to_crop(S)
    hc = fd / "head_crop"
    bald, blank, mo = (L.load(hc / f"{k}.png") for k in ("bald", "face_blank", "mouth_open"))
    eyes_c = crop.to_crop(lay["eyes_open"])[..., 3] > 64
    mouth_c = crop.to_crop(lay["mouth_closed"])[..., 3] > 64
    head_c = crop.to_crop(lay["head"])[..., 3] > 64
    parts, sides = face_parts(src_c, bald, blank, mo, eyes_c, mouth_c, head_c, view)
    out.mkdir(parents=True, exist_ok=True)
    layers = {}
    for n, (m, img) in parts.items():
        a = np.zeros_like(img)
        a[m] = img[m]
        layers[n] = crop.to_canvas(a)
    body = [n for n in rig["layers"] if n not in ("eyes_open", "eyes_closed", "mouth_open", "mouth_closed", "head")]
    for n in body:
        layers[n] = lay[n]
    for n, a in layers.items():
        L.save(a, out / f"{n}.png")
    face_order = [f"brow_{s}" for s in sides] + [f"eyelash_{s}" for s in sides] + [f"iris_{s}" for s in sides] + \
        [f"eye_white_{s}" for s in sides] + ["nose", "mouth_line", "face"]
    face_order = [n for n in face_order if n in layers]
    head = {"name": "Head", "group": [{"name": "Hair", "group": [{"name": "hair_front", "png": "hair_front.png"}]},
                                      {"name": "Face", "group": [{"name": n, "png": f"{n}.png"} for n in face_order]},
                                      {"name": "Mouth", "hidden": True,
                                       "group": [{"name": "mouth_inside", "png": "mouth_inside.png"}]}]}
    cat = lambda n: "Arms" if n.startswith(("arm_", "hand_")) else "Body" if n == "torso" else "Legs"
    tree, used, cur = [], set(), None
    for n in rig["layers"]:
        if n in ("hair_front", "eyes_open", "eyes_closed", "mouth_open", "mouth_closed", "head"):
            if not any(t.get("name") == "Head" for t in tree):
                tree.append(head)
                used.add("Head")
            cur = None
            continue
        c = cat(n)
        if cur is None or cur["cat"] != c:
            fname = c if c not in used else f"{c} back"
            used.add(fname)
            cur = {"name": fname, "group": [], "cat": c}
            tree.append(cur)
        cur["group"].append({"name": n, "png": f"{n}.png"})
    for t in tree:
        t.pop("cat", None)
    man = {"width": W, "height": H, "ids": "ids.json", "layers": tree}
    (out / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    sys.path.insert(0, str(HERE))
    import psd_write
    psd = out / f"{name}_cubism.psd"
    psd_write.write_manifest(out / "manifest.json", psd)
    doc = psd_write.read(psd)
    pix = [r for r in doc["records"] if not r["section"]]
    names = [r["name"] for r in pix]
    hidden = {r["name"] for r in doc["records"] if r["hidden"]}
    comp = doc["merged"].astype(np.float32)
    A = S[..., 3] > 127
    cA = comp[..., 3] > 127
    iou = float((A & cA).sum() / max((A | cA).sum(), 1))
    d = np.abs(comp[..., :3] * (comp[..., 3:4] / 255) - S[..., :3] * (S[..., 3:4] / 255)).max(-1)
    px40 = float(((d > 40) & (A | cA)).sum() / max((A | cA).sum(), 1))
    G = L.gate
    gates = [G("cubism.composite_iou", round(iou, 4), 0.99, iou >= 0.99),
             G("cubism.composite_px40", round(px40, 4), 0.005, px40 <= 0.005),
             G("cubism.layers", len(pix), 100, len(pix) <= 100),
             G("cubism.names", len(set(names)), len(names), len(set(names)) == len(names)),
             G("cubism.format", f"v{doc['version']} {doc['depth']}bit mode{doc['mode']}", "v1 8bit mode3",
               (doc["version"], doc["depth"], doc["mode"]) == (1, 8, 3)),
             G("cubism.mouth_hidden", "Mouth" in hidden, True, "Mouth" in hidden),
             G("cubism.face_parts", sorted(parts), "eyes, brows, nose, mouth",
               all(any(n.startswith(p) for n in parts) for p in ("eye_white", "iris", "eyelash", "brow", "mouth_line"))
               and parts["mouth_inside"][0].any())]
    ok = all(g["pass"] for g in gates)
    rep = {"schema": "gate/1", "tool": "cubism_psd", "pass": ok, "gates": gates, "psd": psd.name}
    (out / "cubism.gate.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return rep


def selftest() -> int:
    """A synthetic front figure through layer_split's split, a blank-face fill and the crops."""
    np = _np()
    L = ls()
    checks = {}
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        src, fills = L.synth("front")
        H, W = src.shape[:2]
        L.save(src, t / "source.png")
        blank = L.synth("front")[1]["bald"].copy()
        # the blank face: the bald head with the eyes and mouth painted over in skin
        yy, xx = np.mgrid[:H, :W]
        skin = np.array([235, 190, 160, 255], np.float32)
        feat = (((yy - 64) ** 2 / 12 ** 2 + (xx - 160) ** 2 / 14 ** 2) < 1) | \
               (((yy - 64) ** 2 / 12 ** 2 + (xx - 200) ** 2 / 14 ** 2) < 1) | \
               ((np.abs(yy - 91) < 10) & (np.abs(xx - 180) < 14))
        blank[feat] = skin
        fills["face_blank"] = blank
        box = [100, -10, 260, 150]
        crop = Crop(box, W, H)
        (t / "head_crop").mkdir()
        doc = {"view": "front", "facing": "front", "canvas": [W, H], "source": "source.png", "head_box": box, "fills": {}}
        for k, v in fills.items():
            L.save(v, t / f"{k}.png")
            L.save(crop.to_crop(v), t / "head_crop" / f"{k}.png")
            doc["fills"][k] = {"png": f"{k}.png"}
        (t / "fills.json").write_text(json.dumps(doc), encoding="utf-8")
        rep_s = L.split(t / "source.png", t / "fills.json", t / "layers", overlap=10)
        checks["split_ok"] = rep_s["pass"]
        rep = build(t / "layers", t / "fills.json", t / "cub", "Synth")
        g = {x["name"]: x for x in rep["gates"]}
        failing = {k: v for k, v in g.items() if not v["pass"]}
        if failing:
            print(json.dumps(failing, default=str), file=sys.stderr)
        checks["gates"] = rep["pass"]
        sys.path.insert(0, str(HERE))
        import psd_write
        tr = psd_write.tree(psd_write.read(t / "cub" / "Synth_cubism.psd"))
        top = [n["name"] for n in tr]
        checks["folders"] = top[:2] == ["Arms", "Body"] and "Head" in top and "Legs" in top
        head = next(n for n in tr if n["name"] == "Head")
        face = next(n for n in head["group"] if n["name"] == "Face")
        fn = {n["name"] for n in face["group"]}
        checks["eyes_split"] = {"eye_white_R", "eye_white_L", "iris_R", "iris_L"} <= fn
        m = hull_fill(np.pad(np.ones((5, 5), bool), 3))
        checks["hull"] = bool(m.sum() == 25)
    ok = all(checks.values())
    print(json.dumps({"checks": checks, "pass": ok}))
    return 0 if ok else 2


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1, never 2."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["--selftest"], ["selftest"]):
        return selftest()
    ap = UsageParser(prog="cubism_psd.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("layers", type=Path, help="layer_split.py split's output folder (rig2d.json and the PNGs)")
    ap.add_argument("--fills", type=Path, required=True, help="the fills.json made with --cubism")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--name", default="Character")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    for p in (a.layers / "rig2d.json", a.fills):
        if not p.is_file():
            ap.error(f"not found: {p}")
    try:
        rep = build(a.layers, a.fills, a.out, a.name)
    except ls().Refused as e:
        print(f"cubism_psd.py: refused: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"pass": rep["pass"], "psd": str(a.out / rep["psd"]),
                      "gates": {g["name"]: g["value"] for g in rep["gates"]}}))
    return 0 if rep["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
