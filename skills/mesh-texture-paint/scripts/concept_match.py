#!/usr/bin/env python3
"""concept_match.py — how close a finished mesh is to its concept views, as numbers a person reads.

Renders the GLB (its base colour; clay where a part has none) from each concept view's direction
with paint_loop.py's cameras (front yaw 0, left 90, back 180, right 270, pitch 0, the same orbit,
fov and fill; framed on the bounding sphere so nothing is cut off), on a transparent background. Each concept view is warped onto the render's canvas: a
uniform scale and an offset that match the two silhouettes' bounding boxes (the dominant side of
the concept's box), then the small scale/shift search align_painted uses, run on the two alpha
masks. The three-quarter view has no fixed camera: of yaw 45 or 315 and pitch 0, 10, 20 or 30, the
camera whose silhouette matches best is kept (within 0.01 IoU, the one whose colours match best:
a mirror) and recorded with every candidate's numbers.

Per view:
  silhouette_iou   render alpha vs concept alpha after alignment (1 = the same outline; higher is closer)
  palette_de       symmetric mean nearest-colour distance between the two palettes, in CIELAB
                   delta E (0 = the same colours; lower is closer). Each palette is binned as
                   mvtex.concept_palette bins (4-unit cells, the cells holding 97% of the pixels)
  dinov2_sim       cosine of the DINOv2 embeddings of render and concept (shape, parts; higher is closer)
  siglip2_sim      cosine of the SigLIP 2 embeddings (what it shows, its style; higher is closer)
and over the views each metric's min and mean.

The embeddings come from codex-visual/scripts/embed.py, which needs torch + transformers.
DIR/pairs.json (render vs concept, per view) is always written. --sims SIMS.json reads
similarities measured elsewhere (copy DIR to a GPU host, run embed.py --pairs DIR/pairs.json
--out sims.json there, copy it back); --embed measures inline when the engine is present.
Otherwise the embedding numbers are null and the report says why: null is "not measured",
never a pass.

Every number is REPORTED ONLY: the report is gate/1 with pass true and report-only gates
(limit null): match.silhouette_iou_min, match.silhouette_iou_mean, match.palette_de_mean,
match.dinov2_sim_min, match.siglip2_sim_min. A gate not measured has value null and is listed in
"not_measured": [{name, why}]; an embedding gate is null unless every view has its value. A person decides.

Tiers: whole (the anchor mesh), three or fine (an assembled GLB: every mesh primitive is merged
with its node's world transform and keeps its own base colour). The tier is recorded.

  python3 concept_match.py runner.glb --view front=views/front.png --view left=views/left.png \\
      --view back=views/back.png --view right=views/right.png --view three_quarter=hero.png --out match/
  python3 concept_match.py --selftest

Writes DIR/renders/<view>.png, DIR/views/<view>.png (the concept on the same canvas),
DIR/compare.png (concept | render | outlines), DIR/pairs.json and DIR/concept_match.json.

Exit codes: 0 report written (whatever the numbers), 1 usage error (a bad flag, an unreadable
GLB, sims file or concept view, a view with no figure), 2 selftest failed.
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import io
import json
import math
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import cKDTree

import mvtex as M
from paint_loop import CONCEPT_YAW

HERE = Path(__file__).resolve().parent
EMBED = HERE.parent.parent / "codex-visual" / "scripts" / "embed.py"
VIEWS = (*CONCEPT_YAW, "three_quarter")
TQ_CANDIDATES = [(y, p) for y in (45.0, 315.0) for p in (0.0, 10.0, 20.0, 30.0)]
FILL = 0.92            # paint_loop's --fill
SS = 2                 # renders are supersampled 2x and box-filtered
SCALES = (0.97, 0.985, 1.0, 1.015, 1.03)   # align_painted's search
EMB_MODELS = ("dinov2", "siglip2")
HOW_TO_MEASURE = ("run codex-visual/scripts/embed.py --pairs {pairs} on a machine with torch and transformers, "
                  "then rerun with --sims")
_EMBED_MOD = None


def load_embed():
    """codex-visual's embed.py as a module, or None when that skill is not installed beside this one."""
    global _EMBED_MOD
    if _EMBED_MOD is None and EMBED.is_file():
        spec = importlib.util.spec_from_file_location("codex_visual_embed", EMBED)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _EMBED_MOD = mod
    return _EMBED_MOD


# ----------------------------------------------------------------------------- scene (several primitives)

class Refused(ValueError):
    """An input that cannot be measured (exit 1)."""


@dataclass
class Scene:
    mesh: M.Mesh            # every primitive merged, world space
    prim: np.ndarray        # (faces,) primitive index of each face
    looks: list             # per primitive: ("texture", HxWx3 uint8, factor rgb) | ("factor", rgb uint8) | ("clay", None)

    @property
    def coloured(self):
        return any(look[0] != "clay" for look in self.looks)


def _quat_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def node_matrix(node) -> np.ndarray:
    """A node's local 4x4: its matrix, else translation * rotation * scale."""
    if "matrix" in node:
        return np.array(node["matrix"], np.float64).reshape(4, 4).T
    m = np.eye(4)
    m[:3, :3] = _quat_matrix(node.get("rotation", (0, 0, 0, 1))) * np.array(node.get("scale", (1, 1, 1)), float)
    m[:3, 3] = node.get("translation", (0, 0, 0))
    return m


def _attr(js, binc, i):
    a = js["accessors"][i]
    if "bufferView" not in a or "sparse" in a:
        raise ValueError(f"accessor {i}: sparse or bufferView-less accessors are not read")
    if a["componentType"] not in M._CT:
        raise ValueError(f"accessor {i}: component type {a['componentType']} is not read")
    x = M._accessor(js, binc, i)
    if a.get("normalized") and a["componentType"] != 5126:
        x = x.astype(np.float64) / np.iinfo(M._CT[a["componentType"]]).max
    return x


def _image(js, binc, idx, base: Path):
    im = js["images"][idx]
    if "bufferView" in im:
        bv = js["bufferViews"][im["bufferView"]]
        o = bv.get("byteOffset", 0)
        data = binc[o:o + bv["byteLength"]]
    elif im.get("uri", "").startswith("data:"):
        data = base64.b64decode(im["uri"].split(",", 1)[1])
    else:
        data = (base / im["uri"]).read_bytes()
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))


def _look(js, binc, mat_i, base, cache):
    if mat_i is None or mat_i >= len(js.get("materials", [])):
        return ("clay", None)
    pbr = js["materials"][mat_i].get("pbrMetallicRoughness", {})
    factor = np.array(pbr.get("baseColorFactor", (1, 1, 1, 1))[:3], np.float64)
    slot = pbr.get("baseColorTexture")
    if slot is not None:
        src = js["textures"][slot["index"]].get("source")
        if src is not None:
            if src not in cache:
                cache[src] = _image(js, binc, src, base)
            return ("texture", cache[src], factor)
    if "baseColorFactor" in pbr:
        return ("factor", _to_srgb(factor))
    return ("clay", None)


def _to_srgb(lin):
    lin = np.clip(lin, 0, 1)
    s = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * lin ** (1 / 2.4) - 0.055)
    return np.clip(np.rint(s * 255), 0, 255).astype(np.uint8)


def _to_lin(srgb):
    c = np.asarray(srgb, np.float64) / 255.0
    return np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)


def bind_matrix(js, binc, skin_i, worlds) -> np.ndarray:
    """Where a skinned mesh sits in its bind pose: its first joint's world matrix times that joint's
    inverse bind matrix (glTF ignores the skinned node's own transform). An exporter that writes
    world-space vertices (Blender) gives the identity; one that writes them in the armature's space
    (an FBX-scale, Z-up armature) gives the armature's transform."""
    skin = js["skins"][skin_i]
    joints = skin.get("joints") or []
    if not joints or joints[0] not in worlds:
        return np.eye(4)
    ibm = np.eye(4)
    if "inverseBindMatrices" in skin:
        a = js["accessors"][skin["inverseBindMatrices"]]
        if a.get("type") != "MAT4" or a.get("componentType") != 5126 or "bufferView" not in a:
            raise ValueError("inverseBindMatrices: expected a float MAT4 accessor")
        bv = js["bufferViews"][a["bufferView"]]
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        ibm = np.frombuffer(binc, np.float32, count=16, offset=start).astype(np.float64).reshape(4, 4).T
    return worlds[joints[0]] @ ibm


def load_scene(path) -> Scene:
    """Every triangle primitive of the GLB's scene in world space (node transforms composed; a
    skinned mesh in its bind pose, bind_matrix), each with its base colour: texture x factor, a flat
    factor, or clay when it has no material."""
    path = Path(path)
    js, binc = M._glb_chunks(path.read_bytes())
    nodes = js.get("nodes", [])
    if js.get("scenes"):
        roots = js["scenes"][js.get("scene", 0)].get("nodes", [])
    else:
        kids = {c for n in nodes for c in n.get("children", [])}
        roots = [i for i in range(len(nodes)) if i not in kids]
    worlds, stack = {}, [(i, np.eye(4)) for i in roots]
    while stack:
        i, parent = stack.pop()
        worlds[i] = parent @ node_matrix(nodes[i])
        stack += [(c, worlds[i]) for c in nodes[i].get("children", [])]
    V, UV, F, P, looks, cache = [], [], [], [], [], {}
    for i in sorted(worlds):
        node = nodes[i]
        if "mesh" not in node:
            continue
        world = bind_matrix(js, binc, node["skin"], worlds) if "skin" in node else worlds[i]
        for prim in js["meshes"][node["mesh"]]["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            v = _attr(js, binc, prim["attributes"]["POSITION"]).astype(np.float64)
            v = v @ world[:3, :3].T + world[:3, 3]
            uv = (_attr(js, binc, prim["attributes"]["TEXCOORD_0"]).astype(np.float64)
                  if "TEXCOORD_0" in prim["attributes"] else np.zeros((len(v), 2)))
            f = (_attr(js, binc, prim["indices"]).astype(np.int64) if "indices" in prim
                 else np.arange(len(v), dtype=np.int64))
            f = f[: len(f) // 3 * 3].reshape(-1, 3)
            if not len(f):
                continue
            look = _look(js, binc, prim.get("material"), path.parent, cache)
            if look[0] == "texture" and "TEXCOORD_0" not in prim["attributes"]:
                look = ("factor", _to_srgb(look[2]))
            F.append(f + sum(len(x) for x in V))
            V.append(v)
            UV.append(uv)
            P.append(np.full(len(f), len(looks)))
            looks.append(look)
    if not F:
        raise ValueError("the GLB has no triangle primitive")
    mesh = M.Mesh(np.concatenate(V), np.concatenate(UV), np.concatenate(F), str(path))
    return Scene(mesh, np.concatenate(P), looks)


def render(scene: Scene, cam: M.Camera):
    """(rgb uint8 HxWx3, mask bool HxW) of the scene from cam: textures unlit, clay shaded grey."""
    mesh = scene.mesh
    tri, _dep, bar = M.render_buffers(mesh, cam)
    m = tri >= 0
    img = np.zeros((cam.height, cam.width, 3), np.uint8)
    pk = np.where(m, scene.prim[np.maximum(tri, 0)], -1)
    shade = None
    for k, look in enumerate(scene.looks):
        sel = pk == k
        if not sel.any():
            continue
        if look[0] == "texture":
            tex, factor = look[1], look[2]
            uv = (mesh.uv[mesh.f[tri[sel]]] * bar[sel][..., None]).sum(1)
            uv = np.where((uv < 0) | (uv > 1), np.mod(uv, 1.0), uv)
            h, w = tex.shape[:2]
            c = M.sample_bilinear(tex, uv[:, 0] * w, uv[:, 1] * h)
            if not np.allclose(factor, 1.0):
                c = _to_srgb(_to_lin(c) * factor).astype(np.float64)
            img[sel] = np.clip(c, 0, 255).astype(np.uint8)
        elif look[0] == "factor":
            img[sel] = look[1]
        else:
            if shade is None:
                shade = M._shade(mesh, cam, tri)
            img[sel] = np.clip(shade[sel] * 0.78 * 255, 0, 255).astype(np.uint8)[:, None]
    return img, m


def view_camera(scene: Scene, yaw, pitch, size):
    """paint_loop's orbit camera (same yaw, pitch, fov and fill around the box centre), framed on the
    bounding sphere instead of half the longest side so no view cuts the mesh off at the frame."""
    mesh = scene.mesh
    radius = float(np.linalg.norm(mesh.v.max(0) - mesh.v.min(0)) / 2)
    return M.Camera.orbit(mesh.center, radius, yaw, pitch, size=size, fill=FILL)


def render_rgba(scene: Scene, yaw, pitch, size):
    """RGBA uint8 (size x size) on transparent, supersampled SS x and box-filtered."""
    rgb, m = render(scene, view_camera(scene, yaw, pitch, size * SS))
    a = m.astype(np.float64)
    pre = rgb.astype(np.float64) * a[..., None]
    pre = pre.reshape(size, SS, size, SS, 3).mean((1, 3))
    a = a.reshape(size, SS, size, SS).mean((1, 3))
    col = np.where(a[..., None] > 0, pre / np.maximum(a[..., None], 1e-9), 0)
    return np.dstack([np.clip(np.rint(col), 0, 255), np.rint(a * 255)]).astype(np.uint8)


# ----------------------------------------------------------------------------- concept views and alignment

def load_concept(path):
    """(RGBA uint8, mask): the alpha when the image has a real one (the S2 cut-outs), else everything
    farther than 12 from the border's median colour (a view on black loses black at its edge)."""
    im = Image.open(path)
    im.load()
    rgba = np.asarray(im.convert("RGBA")).copy()
    if rgba[..., 3].min() < 255:
        mask = rgba[..., 3] > 127
    else:
        a = rgba[..., :3].astype(np.float64)
        bg = np.median(np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]), 0)
        mask = ndimage.binary_fill_holes(ndimage.binary_opening(np.abs(a - bg).max(2) > 12, iterations=1))
        rgba[..., 3] = np.where(mask, 255, 0)
    return rgba, mask


def bbox(mask):
    ys, xs = np.nonzero(mask)
    return float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)


def _affine(s, cx_in, cy_in, cx_out, cy_out, k=1.0):
    """PIL AFFINE coefficients for out(x) = in((x*k - c_out) / s + c_in) (k: output pixel size)."""
    a = k / s
    return (a, 0.0, cx_in - cx_out / s, 0.0, a, cy_in - cy_out / s)


def fit_concept(c_mask, r_mask, size, search=True):
    """Uniform scale + offset taking the concept's silhouette onto the render's: bounding boxes
    first (the concept box's dominant side), then align_painted's scale/shift search on the masks.
    Returns (s, (cx_in, cy_in), (cx_out, cy_out), iou_bbox)."""
    cx0, cy0, cx1, cy1 = bbox(c_mask)
    rx0, ry0, rx1, ry1 = bbox(r_mask)
    s = (ry1 - ry0) / (cy1 - cy0) if (cy1 - cy0) >= (cx1 - cx0) else (rx1 - rx0) / (cx1 - cx0)
    cin = ((cx0 + cx1) / 2, (cy0 + cy1) / 2)
    cout = ((rx0 + rx1) / 2, (ry0 + ry1) / 2)
    pim = Image.fromarray(c_mask.astype(np.uint8) * 255)
    k = 1 if size <= 512 else 2             # searched at full resolution up to 512 px, else at half
    fixed = r_mask[::k, ::k]
    shape = (fixed.shape[1], fixed.shape[0])

    def score(ss, dx, dy):
        w = np.asarray(pim.transform(shape, Image.AFFINE, _affine(ss, *cin, cout[0] + dx, cout[1] + dy, float(k)),
                                     Image.NEAREST)) > 127
        return M.iou(w, fixed)

    base = score(s, 0, 0)
    best = (base, 1.0, 0, 0)
    if not search:
        return s, cin, cout, base
    ms = max(4, int(round(16 * size / 1024)))
    for q in SCALES:
        for dy in range(-ms, ms + 1, 2):
            for dx in range(-ms, ms + 1, 2):
                v = score(s * q, dx, dy)
                if v > best[0] + 1e-6:
                    best = (v, q, dx, dy)
    _v, q, dx, dy = best
    return s * q, cin, (cout[0] + dx, cout[1] + dy), base


def warp_concept(rgba, s, cin, cout, size):
    im = Image.fromarray(rgba, "RGBA").convert("RGBa")
    out = im.transform((size, size), Image.AFFINE, _affine(s, *cin, *cout), Image.BICUBIC)
    return np.asarray(out.convert("RGBA"))


# ----------------------------------------------------------------------------- palette

def lab(rgb):
    """Plain CIELAB (D65): mvtex.chroma_lab with its dark-colour stretch of a and b undone."""
    cl = M.chroma_lab(rgb)
    f = np.clip(50.0 / np.maximum(cl[..., :1], 12.0), 1.0, 4.0)
    return np.concatenate([cl[..., :1], cl[..., 1:] / f], -1)


def palette(rgba, q=4.0, mass=0.97):
    """(cells, weights): the figure's Lab colours (alpha > 127, eroded 2 px) in q-unit cells, the
    most frequent cells holding `mass` of the pixels, as concept_palette keeps them."""
    fg = ndimage.binary_erosion(rgba[..., 3] > 127, iterations=2)
    if fg.sum() < 16:
        fg = rgba[..., 3] > 127
    if not fg.any():
        return None
    cells, cnt = np.unique(np.round(lab(rgba[..., :3][fg].astype(np.float64)) / q).astype(np.int32), axis=0,
                           return_counts=True)
    order = np.argsort(-cnt)
    keep = order[: int(np.searchsorted(np.cumsum(cnt[order]) / cnt.sum(), mass)) + 1]
    return cells[keep] * q, cnt[keep].astype(np.float64)


def palette_de(a_rgba, b_rgba):
    """Symmetric mean nearest-colour distance (delta E) between two figures' palettes."""
    pa, pb = palette(a_rgba), palette(b_rgba)
    if pa is None or pb is None:
        return None

    def one(x, y):
        d, _ = cKDTree(y[0]).query(x[0])
        return float((d * x[1]).sum() / x[1].sum())
    return round((one(pa, pb) + one(pb, pa)) / 2, 2)


# ----------------------------------------------------------------------------- report

def report_gate(name, value):
    """A gate that is measured and written, never failed (as paint_loop.report_gate)."""
    return {"name": name, "value": value, "limit": None, "pass": True, "report_only": True}


def _stats(vals):
    v = [x for x in vals if x is not None]
    if not v:
        return {"min": None, "mean": None, "n": 0}
    return {"min": round(min(v), 4), "mean": round(sum(v) / len(v), 4), "n": len(v)}


def embeddings(a, out: Path, names):
    """({view: {model: sim}}, source, engine, reason)."""
    if a.sims:
        doc = a.sims_doc
        sims = doc.get("sims") or {}
        got = {v: {m: (sims.get(v) or {}).get(m) for m in EMB_MODELS} for v in names}
        if doc.get("engine") is None:
            return got, "sims", None, "not measured: " + str(doc.get("reason") or f"{a.sims} has no engine")
        return got, "sims", doc["engine"], None
    blank = {v: {m: None for m in EMB_MODELS} for v in names}
    how = HOW_TO_MEASURE.format(pairs=out / "pairs.json")
    if not a.embed:
        return blank, None, None, f"not measured: {how}"
    E = load_embed()
    if E is None:
        return blank, None, None, f"not measured: codex-visual is not installed beside mesh-texture-paint; {how}"
    ok, why = E.available()
    if not ok and E._TEST_EMBEDDER is None:
        print(f"WARN concept_match: --embed but the engine is missing ({why})", file=sys.stderr)
        return blank, None, None, f"not measured ({why}): {how}"
    doc, code = E.run_pairs(E.read_pairs(out / "pairs.json"), list(EMB_MODELS), a.device)
    (out / "sims.json").write_text(json.dumps(doc, indent=1))
    if code:
        return blank, "inline", None, f"not measured: {doc.get('reason')}"
    return {v: {m: doc["sims"].get(v, {}).get(m) for m in EMB_MODELS} for v in names}, "inline", doc["engine"], None


def compare_sheet(rows, path, tile=192):
    """concept | render | outlines (white both, red concept only, cyan render only), one row per view."""
    sheet = Image.new("RGB", (3 * tile, len(rows) * (tile + 16)), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    grey = np.full((1, 1, 3), 128.0)
    for j, (name, concept, rend) in enumerate(rows):
        y = j * (tile + 16)
        d.text((4, y + 2), name, fill=(255, 255, 255))
        cm, rm = concept[..., 3] > 127, rend[..., 3] > 127
        diff = np.zeros(cm.shape + (3,), np.uint8)
        diff[cm & rm] = (230, 230, 230)
        diff[cm & ~rm] = (230, 60, 60)
        diff[rm & ~cm] = (60, 220, 230)
        for i, im in enumerate((concept, rend)):
            al = im[..., 3:4] / 255.0
            comp = (im[..., :3] * al + grey * (1 - al)).astype(np.uint8)
            sheet.paste(Image.fromarray(comp).resize((tile, tile), Image.LANCZOS), (i * tile, y + 16))
        sheet.paste(Image.fromarray(diff).resize((tile, tile), Image.NEAREST), (2 * tile, y + 16))
    sheet.save(path)


def run(a) -> dict:
    out = a.out
    for sub in ("renders", "views"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    scene = a.scene
    size = a.size
    views, rows, pairs = {}, [], []
    for name, cpath in a.views:
        rgba_c, c_mask = a.concepts[name]
        cands = TQ_CANDIDATES if name == "three_quarter" else [(float(CONCEPT_YAW[name]), 0.0)]
        tried = []
        for yaw, pitch in cands:
            rend = render_rgba(scene, yaw, pitch, size)
            r_mask = rend[..., 3] > 127
            if r_mask.any():
                tried.append({"yaw": yaw, "pitch": pitch, "rend": rend, "r_mask": r_mask,
                              "iou_bbox": fit_concept(c_mask, r_mask, size, search=False)[3]})
        if len(tried) > 1:   # the full search only where the boxes alone come close
            top = max(t["iou_bbox"] for t in tried)
            tried = [t for t in tried if t["iou_bbox"] >= top - 0.05]
        for t in tried:
            s, cin, cout, _b = fit_concept(c_mask, t["r_mask"], size)
            warped = warp_concept(rgba_c, s, cin, cout, size)
            t.update(warped=warped, s=s, iou=M.iou(warped[..., 3] > 127, t["r_mask"]),
                     de=palette_de(warped, t["rend"]) if scene.coloured else None)
        if not tried:
            raise Refused(f"view {name}: the mesh renders empty")
        # the best outline; a near tie (a mirror: yaw 45 and 315 of a symmetric body) goes to the colours
        top = max(t["iou"] for t in tried)
        near = [t for t in tried if t["iou"] >= top - 0.01]
        best = min(near, key=lambda t: (t["de"] if t["de"] is not None else 0.0, -t["iou"]))
        rend, warped = best["rend"], best["warped"]
        Image.fromarray(rend, "RGBA").save(out / "renders" / f"{name}.png")
        Image.fromarray(warped, "RGBA").save(out / "views" / f"{name}.png")
        pairs.append({"id": name, "a": f"renders/{name}.png", "b": f"views/{name}.png"})
        rm = rend[..., 3] > 127
        views[name] = {"concept": str(Path(cpath).resolve()), "yaw": best["yaw"], "pitch": best["pitch"],
                       "silhouette_iou": round(best["iou"], 4), "silhouette_iou_bbox": round(best["iou_bbox"], 4),
                       "concept_scale": round(best["s"], 4), "palette_de": best["de"],
                       "clipped": bool(rm[0].any() or rm[-1].any() or rm[:, 0].any() or rm[:, -1].any())}
        if len(tried) > 1:
            views[name]["candidates"] = [{"yaw": t["yaw"], "pitch": t["pitch"], "silhouette_iou": round(t["iou"], 4),
                                          "palette_de": t["de"]} for t in tried]
        rows.append((name, warped, rend))
    (out / "pairs.json").write_text(json.dumps({"pairs": pairs}, indent=1))
    compare_sheet(rows, out / "compare.png")
    names = [n for n, _ in a.views]
    sims, source, engine, reason = embeddings(a, out, names)
    for n in names:
        for m in EMB_MODELS:
            views[n][f"{m}_sim"] = sims[n][m]
    summary = {k: _stats([views[n][k] for n in names])
               for k in ("silhouette_iou", "palette_de", "dinov2_sim", "siglip2_sim")}
    not_measured = []
    if not scene.coloured:
        not_measured.append({"name": "match.palette_de_mean", "why": "the mesh has no base colour (a clay render)"})
    emb = {}
    for m in EMB_MODELS:
        lacking = [n for n in names if views[n][f"{m}_sim"] is None]
        if not lacking:
            emb[m] = summary[f"{m}_sim"]["min"]
            continue
        emb[m] = None             # never a min over part of the views: a missing view could be the worst
        summary[f"{m}_sim"].update(min=None, mean=None)
        why = reason or (f"not measured: {a.sims} has no {m} similarity for "
                         f"{', '.join(lacking)} (run embed.py on this DIR/pairs.json)")
        not_measured.append({"name": f"match.{m}_sim_min", "why": why})
    gates = [report_gate("match.silhouette_iou_min", summary["silhouette_iou"]["min"]),
             report_gate("match.silhouette_iou_mean", summary["silhouette_iou"]["mean"]),
             report_gate("match.palette_de_mean", summary["palette_de"]["mean"]),
             report_gate("match.dinov2_sim_min", emb["dinov2"]),
             report_gate("match.siglip2_sim_min", emb["siglip2"])]
    doc = {"schema": "gate/1", "tool": "concept_match", "pass": True, "path": str(Path(a.glb).resolve()),
           "tier": a.tier, "primitives": len(scene.looks), "size": size, "gates": gates, "views": views,
           "summary": summary,
           "embedding": {"source": source, "engine": engine, "pairs": str((out / "pairs.json").resolve())}}
    doc["not_measured"] = not_measured
    (out / "concept_match.json").write_text(json.dumps(doc, indent=1))
    return doc


def table(doc) -> str:
    def f(x, nd=3):
        return "-" if x is None else f"{x:.{nd}f}"
    lines = [f"{'view':14s} {'yaw':>5s} {'pitch':>5s} {'IoU':>6s} {'dE':>6s} {'dinov2':>7s} {'siglip2':>7s}"]
    for n, v in doc["views"].items():
        lines.append(f"{n:14s} {v['yaw']:5.0f} {v['pitch']:5.0f} {f(v['silhouette_iou']):>6s} "
                     f"{f(v['palette_de'], 1):>6s} {f(v['dinov2_sim']):>7s} {f(v['siglip2_sim']):>7s}")
    s = doc["summary"]
    for k in ("min", "mean"):
        lines.append(f"{'whole ' + k:14s} {'':5s} {'':5s} {f(s['silhouette_iou'][k]):>6s} {f(s['palette_de'][k], 1):>6s} "
                     f"{f(s['dinov2_sim'][k]):>7s} {f(s['siglip2_sim'][k]):>7s}")
    why = {}
    for x in doc.get("not_measured", []):
        why.setdefault(x["why"], []).append(x["name"])
    for r, gs in why.items():
        lines.append(f"{', '.join(gs)}: {r}")
    lines.append(f"tier {doc['tier']}, {doc['primitives']} primitive(s); report only: a person decides")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- CLI

class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1, never 2."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    ap = UsageParser(prog="concept_match.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("glb", type=Path, nargs="?", help="the mesh: the anchor, a painted GLB, an assembled GLB or the game mesh")
    ap.add_argument("--view", action="append", default=[], metavar="NAME=PNG",
                    help="a concept view: front, left, back, right or three_quarter (repeat)")
    ap.add_argument("--out", type=Path, help="output folder")
    ap.add_argument("--tier", choices=["whole", "three", "fine"], default="whole",
                    help="what the GLB is: the whole anchor mesh, or a three-part / fine assembled GLB")
    ap.add_argument("--sims", type=Path, help="sims.json written by codex-visual/scripts/embed.py for DIR/pairs.json")
    ap.add_argument("--embed", action="store_true", help="measure the embeddings here (needs torch + transformers)")
    ap.add_argument("--device", choices=["auto", "cuda", "mps", "cpu"], default="auto", help="for --embed")
    ap.add_argument("--size", type=int, default=512, help="canvas of renders and views, px (64-2048)")
    ap.add_argument("--selftest", action="store_true", help="synthetic checks; no network, no torch")
    return ap


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.glb is None or a.out is None or not a.view:
        ap.error("a GLB, --out and at least one --view NAME=PNG are required")
    if not 64 <= a.size <= 2048 or a.size % 2:
        ap.error("--size must be an even number in 64..2048")
    if a.sims and a.embed:
        ap.error("--sims and --embed: pick one")
    views, seen = [], set()
    for spec in a.view:
        name, _, p = spec.partition("=")
        if name not in VIEWS or not p:
            ap.error(f"--view {spec!r}: expected NAME=PNG with NAME one of {', '.join(VIEWS)}")
        if name in seen:
            ap.error(f"--view {name} given twice")
        seen.add(name)
        views.append((name, Path(p)))
    a.views = views
    a.concepts = {}
    for name, p in views:
        try:
            rgba, mask = load_concept(p)
        except OSError as e:
            ap.error(f"--view {name}: cannot read {p}: {e}")
        if mask.sum() < 16:
            ap.error(f"--view {name}: no figure found in {p}")
        a.concepts[name] = (rgba, mask)
    if a.sims:
        try:
            a.sims_doc = json.loads(a.sims.read_text(encoding="utf-8"))
            if not isinstance(a.sims_doc, dict) or not isinstance(a.sims_doc.get("sims"), dict):
                raise ValueError('no "sims" object')
        except (OSError, ValueError) as e:
            ap.error(f"--sims {a.sims}: {e}")
    try:
        a.scene = load_scene(a.glb)
    except (OSError, KeyError, IndexError, TypeError, ValueError) as e:
        ap.error(f"cannot read the GLB {a.glb}: {type(e).__name__}: {e}")
    try:
        doc = run(a)
    except Refused as e:
        ap.error(str(e))
    print(table(doc))
    print(f"wrote {a.out / 'concept_match.json'}")
    return 0


# ----------------------------------------------------------------------------- selftest

def contract_sample(case: str, doc: dict) -> None:
    """Hand one selftest report to tools/check-contracts.py: written to $UNITY_DEV_CONTRACT_OUT
    (else a fixed folder in the temp dir) as concept_match__<case>.gate.json, named on stdout."""
    folder = Path(os.environ.get("UNITY_DEV_CONTRACT_OUT") or Path(tempfile.gettempdir()) / "unity-dev-contract-out")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"concept_match__{case}.gate.json"
    path.write_text(json.dumps(doc, indent=1))
    print(f"selftest-output: {path}")


def selftest() -> int:
    import contextlib
    import time
    import paint_loop
    t0 = time.time()
    results = {}

    def check(name, cond, detail=""):
        results[name] = bool(cond)
        print(f"{'PASS' if cond else 'FAIL'} {name}" + (f"  {detail}" if detail else ""))

    def nm(rep):
        return {x["name"]: x["why"] for x in rep.get("not_measured", [])}

    def call(args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                code = main(args)
            except SystemExit as e:
                code = e.code
        return code, buf.getvalue()

    size = 128
    check("cameras_are_paint_loops", CONCEPT_YAW is paint_loop.CONCEPT_YAW
          and CONCEPT_YAW == {"front": 0, "left": 90, "back": 180, "right": 270})
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # a cube with six bright face colours (none dark: one view goes on black)
        cols = [(200, 60, 40), (60, 160, 200), (220, 200, 60), (90, 200, 90), (200, 90, 200), (240, 150, 60)]
        tex = np.zeros((128, 192, 3), np.uint8)
        for k, c in enumerate(cols):
            tex[(k // 3) * 64:(k // 3 + 1) * 64, (k % 3) * 64:(k % 3 + 1) * 64] = c
        cube = M.cube_mesh()
        glb = td / "cube.glb"
        M.write_glb(cube, Image.fromarray(tex), glb)
        box = M.Mesh(cube.v * np.array([1.8, 1.0, 1.0]), cube.uv, cube.f)
        M.write_glb(box, Image.fromarray(tex), td / "box.glb")

        # concept views: the mesh's own renders on other canvases (offset, scaled, non-square)
        def concepts(glb_path, folder, recolour=False, tq=(315.0, 20.0)):
            folder.mkdir()
            sc = load_scene(glb_path)
            paths = {}
            for name, (yaw, pitch) in {**{k: (float(v), 0.0) for k, v in CONCEPT_YAW.items()},
                                       "three_quarter": tq}.items():
                r = render_rgba(sc, yaw, pitch, 160)
                if recolour:
                    r = r.copy()
                    r[..., :3] = r[..., [2, 0, 1]]
                canvas = np.zeros((220, 200, 4), np.uint8)
                canvas[40:200, 10:170] = r
                p = folder / f"{name}.png"
                if name == "front":   # an opaque view on black: the mask comes from the border colour
                    al = canvas[..., 3:4] / 255.0
                    Image.fromarray((canvas[..., :3] * al).astype(np.uint8)).save(p)
                else:
                    Image.fromarray(canvas, "RGBA").save(p)
                paths[name] = p
            return paths

        same = concepts(glb, td / "same")
        wrong_col = concepts(glb, td / "colour", recolour=True)
        wrong_shape = concepts(td / "box.glb", td / "shape")

        def args(paths, out, *extra, glb_path=glb):
            return [str(glb_path), *[x for n, p in paths.items() for x in ("--view", f"{n}={p}")],
                    "--out", str(out), "--size", str(size), *extra]

        code, txt = call(args(same, td / "m_same"))
        rep = json.loads((td / "m_same" / "concept_match.json").read_text()) if code == 0 else {}
        g = {x["name"]: x["value"] for x in rep.get("gates", [])}
        check("identical_runs", code == 0, txt[-300:] if code else "")
        check("identical_iou_near_1", (g.get("match.silhouette_iou_min") or 0) >= 0.95, f"{g.get('match.silhouette_iou_min')}")
        check("identical_de_near_0", g.get("match.palette_de_mean") is not None and g["match.palette_de_mean"] <= 3.0,
              f"{g.get('match.palette_de_mean')}")
        check("files_written", all((td / "m_same" / d / f"{n}.png").is_file() for d in ("renders", "views") for n in same)
              and (td / "m_same" / "compare.png").is_file())
        pj = json.loads((td / "m_same" / "pairs.json").read_text()) if code == 0 else {"pairs": []}
        check("pairs_relative_to_dir", [p["id"] for p in pj["pairs"]] == list(same)
              and pj["pairs"][0] == {"id": "front", "a": "renders/front.png", "b": "views/front.png"})
        tq = rep.get("views", {}).get("three_quarter", {})
        check("three_quarter_camera_found", tq.get("pitch") == 20.0 and tq.get("yaw") == 315.0 and tq.get("silhouette_iou", 0) >= 0.95,
              f"yaw {tq.get('yaw')} pitch {tq.get('pitch')} iou {tq.get('silhouette_iou')}")
        check("report_only_gates", rep.get("pass") is True and all(x["limit"] is None and x["pass"] is True
                                                                   and "margin" not in x for x in rep.get("gates", [])))
        check("not_measured_by_default", g.get("match.dinov2_sim_min", 0) is None
              and "embed.py --pairs" in nm(rep).get("match.dinov2_sim_min", ""))
        check("no_ok_key", "ok" not in rep and all("ok" not in x for x in rep.get("gates", [])))
        check("tier_recorded", rep.get("tier") == "whole" and rep.get("primitives") == 1)
        if rep:
            contract_sample("whole", rep)

        code, _ = call(args(wrong_col, td / "m_col"))
        gc = {x["name"]: x["value"] for x in json.loads((td / "m_col" / "concept_match.json").read_text())["gates"]} if code == 0 else {}
        check("wrong_colour_de_worse", (gc.get("match.palette_de_mean") or 0) > max(15.0, 4 * (g.get("match.palette_de_mean") or 0)),
              f"{gc.get('match.palette_de_mean')} vs {g.get('match.palette_de_mean')}")
        check("wrong_colour_shape_still_fits", (gc.get("match.silhouette_iou_min") or 0) >= 0.95)
        code, _ = call(args(wrong_shape, td / "m_shape"))
        gs = {x["name"]: x["value"] for x in json.loads((td / "m_shape" / "concept_match.json").read_text())["gates"]} if code == 0 else {}
        check("wrong_shape_iou_worse", (gs.get("match.silhouette_iou_min") or 1) < 0.85,
              f"{gs.get('match.silhouette_iou_min')} vs {g.get('match.silhouette_iou_min')}")

        # an assembled GLB: a second node with its own material (a flat red) 1.5 to the right (+X)
        def assemble(js):
            js["materials"].append({"pbrMetallicRoughness": {"baseColorFactor": [1.0, 0.0, 0.0, 1.0]}})
            prim = dict(js["meshes"][0]["primitives"][0], material=1)
            js["meshes"].append({"primitives": [prim]})
            js["nodes"].append({"name": "parent", "translation": [1.5, 0.0, 0.0], "children": [2]})
            js["nodes"].append({"mesh": 1, "scale": [1.0, 1.0, 1.0]})
            js["scenes"][0]["nodes"] = [0, 1]
        M.edit_glb_json(glb, assemble, dst=td / "assembled.glb")
        sc = load_scene(td / "assembled.glb")
        lo, hi = sc.mesh.v.min(0), sc.mesh.v.max(0)
        check("assembled_loads_both", len(sc.looks) == 2 and len(sc.mesh.f) == 2 * len(cube.f)
              and abs(hi[0] - 2.0) < 1e-6 and abs(lo[0] + 0.5) < 1e-6, f"x {lo[0]:.2f}..{hi[0]:.2f}")
        front = render_rgba(sc, 0.0, 0.0, 128)
        fm = front[..., 3] > 127
        x0, y0, x1, y1 = bbox(fm)
        red = fm & (front[..., 0] > 200) & (front[..., 1] < 40) & (front[..., 2] < 40)
        rx = np.nonzero(red)[1]
        check("assembled_renders_both", 2.2 <= (x1 - x0) / (y1 - y0) <= 2.8, f"aspect {(x1 - x0) / (y1 - y0):.2f}")
        check("assembled_part_colour_and_side", red.sum() > 200 and rx.min() > (x0 + x1) / 2,
              "the +X part (the character's left) is on the right of the front view")
        rot = node_matrix({"rotation": [0.0, math.sin(math.pi / 4), 0.0, math.cos(math.pi / 4)], "translation": [0, 1, 0]})
        p = rot @ np.array([1.0, 0, 0, 1])
        check("node_trs_composed", np.allclose(p[:3], [0, 1, -1], atol=1e-9), f"{p[:3].round(3).tolist()}")
        # a skinned mesh under an armature turned 90 degrees about Y (vertices in the armature's
        # space, as an FBX-route exporter writes them): read in its bind pose, the box's long side is Z
        def skinned(js):
            js["skins"] = [{"joints": [2]}]
            js["nodes"] = [{"name": "armature", "rotation": [0.0, math.sin(math.pi / 4), 0.0, math.cos(math.pi / 4)],
                            "children": [1, 2]}, {"mesh": 0, "skin": 0}, {"name": "root"}]
            js["scenes"][0]["nodes"] = [0]
        M.edit_glb_json(td / "box.glb", skinned, dst=td / "skinned.glb")
        ext = np.ptp(load_scene(td / "skinned.glb").mesh.v, 0)
        check("skinned_read_in_bind_pose", abs(ext[2] - 1.8) < 1e-6 and abs(ext[0] - 1.0) < 1e-6, f"extent {ext.round(3).tolist()}")
        asm_views = concepts(td / "assembled.glb", td / "asm")
        code, _ = call(args(asm_views, td / "m_asm", "--tier", "three", glb_path=td / "assembled.glb"))
        ra = json.loads((td / "m_asm" / "concept_match.json").read_text()) if code == 0 else {}
        ga = {x["name"]: x["value"] for x in ra.get("gates", [])}
        check("assembled_tier_matches_itself", ra.get("tier") == "three" and ra.get("primitives") == 2
              and (ga.get("match.silhouette_iou_min") or 0) >= 0.93, f"{ga.get('match.silhouette_iou_min')}")

        # a sims file measured elsewhere is read back into the gates
        sims = {"engine": {"models": {"dinov2": "facebook/dinov2-base@main"}, "device": "cuda"},
                "sims": {"front": {"dinov2": 0.91, "siglip2": 0.85}, "left": {"dinov2": 0.82, "siglip2": 0.88},
                         "back": {"dinov2": 0.95, "siglip2": 0.80}, "right": {"dinov2": 0.9, "siglip2": 0.9},
                         "three_quarter": {"dinov2": 0.7, "siglip2": 0.75}}}
        (td / "sims.json").write_text(json.dumps(sims))
        code, _ = call(args(same, td / "m_sims", "--sims", str(td / "sims.json")))
        rs = json.loads((td / "m_sims" / "concept_match.json").read_text()) if code == 0 else {}
        gs2 = {x["name"]: x["value"] for x in rs.get("gates", [])}
        check("sims_read_back", gs2.get("match.dinov2_sim_min") == 0.7 and gs2.get("match.siglip2_sim_min") == 0.75
              and rs["views"]["left"]["dinov2_sim"] == 0.82 and rs.get("not_measured") == []
              and rs["embedding"]["source"] == "sims", f"{gs2.get('match.dinov2_sim_min')}")
        if rs:
            contract_sample("sims", rs)
        part = json.loads(json.dumps(sims))
        del part["sims"]["three_quarter"]          # the worst view is missing: no min over the other four
        (td / "part.json").write_text(json.dumps(part))
        code, _ = call(args(same, td / "m_part", "--sims", str(td / "part.json")))
        rp = json.loads((td / "m_part" / "concept_match.json").read_text()) if code == 0 else {}
        gp = {x["name"]: x["value"] for x in rp.get("gates", [])}
        check("sims_missing_a_view_not_measured", code == 0 and gp.get("match.dinov2_sim_min", 0) is None
              and gp.get("match.siglip2_sim_min", 0) is None
              and "three_quarter" in nm(rp).get("match.dinov2_sim_min", "")
              and rp["summary"]["dinov2_sim"]["min"] is None and rp["summary"]["dinov2_sim"]["n"] == 4,
              f"{gp.get('match.dinov2_sim_min')}")
        (td / "nosims.json").write_text(json.dumps({"engine": None, "reason": "not installed: torch",
                                                    "sims": {"front": {"dinov2": None, "siglip2": None}}}))
        code, _ = call(args({"front": same["front"]}, td / "m_nosims", "--sims", str(td / "nosims.json")))
        rn = json.loads((td / "m_nosims" / "concept_match.json").read_text()) if code == 0 else {}
        check("sims_without_engine_not_measured", code == 0 and rn["summary"]["dinov2_sim"]["min"] is None
              and "torch" in nm(rn).get("match.siglip2_sim_min", ""))

        # --embed: the engine missing -> not measured, a WARN, exit 0; an engine present -> measured
        E = load_embed()
        if E is None:
            check("embed_module_found", False, str(EMBED))
        else:
            E._FORCE_UNAVAILABLE = "not installed: torch"
            try:
                code, txt = call(args({"front": same["front"]}, td / "m_noeng", "--embed"))
                rm = json.loads((td / "m_noeng" / "concept_match.json").read_text()) if code == 0 else {}
                check("embed_missing_engine_not_measured", code == 0 and "WARN" in txt
                      and rm["gates"][3]["value"] is None and "torch" in nm(rm).get("match.dinov2_sim_min", ""))
            finally:
                E._FORCE_UNAVAILABLE = None

            def fake(images, model, device):
                return np.array([np.r_[np.asarray(im, np.float64).reshape(-1, 3).mean(0) / 255.0, 0.5] for im in images])
            E._TEST_EMBEDDER = fake
            try:
                code, txt = call(args({"front": same["front"], "left": same["left"]}, td / "m_eng", "--embed"))
                re_ = json.loads((td / "m_eng" / "concept_match.json").read_text()) if code == 0 else {}
                ge = {x["name"]: x["value"] for x in re_.get("gates", [])}
                check("embed_inline_measured", code == 0 and (ge.get("match.dinov2_sim_min") or 0) > 0.99
                      and re_["embedding"]["source"] == "inline" and (td / "m_eng" / "sims.json").is_file(),
                      f"{ge.get('match.dinov2_sim_min')}")
            finally:
                E._TEST_EMBEDDER = None

        # an untextured mesh renders clay: no palette, said so
        def strip(js):
            js["materials"] = []
            js["meshes"][0]["primitives"][0].pop("material")
        M.edit_glb_json(glb, strip, dst=td / "clay.glb")
        code, _ = call(args({"front": same["front"]}, td / "m_clay", glb_path=td / "clay.glb"))
        rc = json.loads((td / "m_clay" / "concept_match.json").read_text()) if code == 0 else {}
        check("clay_palette_not_measured", code == 0 and rc["gates"][2]["value"] is None
              and "clay" in nm(rc).get("match.palette_de_mean", ""))

        # the report keeps gate/1's shape (the validator itself runs in tools/check-contracts.py)
        def shaped(d):
            return (d.get("schema") == "gate/1" and d.get("pass") is True and isinstance(d.get("gates"), list)
                    and d["gates"] and all(isinstance(x.get("name"), str) and x["name"] and x["pass"] is True
                                           for x in d["gates"])
                    and not any(k in d for k in ("ok", "error", "refused")))
        check("report_shape", all(shaped(d) for d in (rep, rs, rn, rc)))

        # usage errors exit 1
        empty = td / "empty.png"
        Image.new("RGBA", (32, 32)).save(empty)
        for argv, why in (([str(glb), "--out", str(td / "u"), "--view", f"front={same['front']}", "--bogus"], "unknown_flag"),
                          ([str(glb), "--out", str(td / "u"), "--view", f"top={same['front']}"], "bad_view_name"),
                          ([str(glb), "--out", str(td / "u")], "no_view"),
                          ([str(td / "none.glb"), "--out", str(td / "u"), "--view", f"front={same['front']}"], "missing_glb"),
                          ([str(glb), "--out", str(td / "u"), "--view", f"front={empty}"], "empty_view"),
                          ([str(glb), "--out", str(td / "u"), "--view", f"front={same['front']}",
                            "--sims", str(td / "none.json")], "missing_sims"),
                          ([str(glb), "--out", str(td / "u"), "--view", f"front={same['front']}", "--tier", "parts"], "bad_tier")):
            code, _ = call(argv)
            check(f"usage_exit_1_{why}", code == 1, f"exit {code}")

    failed = [k for k, v in results.items() if not v]
    print(f"concept_match selftest: {len(results) - len(failed)}/{len(results)} passed in {time.time() - t0:.1f}s"
          + (f"; FAILED {failed}" if failed else ""))
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
