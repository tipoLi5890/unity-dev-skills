#!/usr/bin/env python3
"""game_mesh.py — S5 route B as one gated run: retopology, UVs and a rebake from the showcase.

The showcase stays the source of detail. A copy is voxel-remeshed into one closed surface (which also
swallows an image-to-3D generator's back-to-back inner shell), retopologised to the budget, unwrapped,
and the showcase's base colour, normal and occlusion are baked onto it in Cycles (Selected to Active).
The result is written beside the gates that say whether it still is the showcase. Runs before the rig:
the ship track rigs once, on this mesh.

usage:
    python3 game_mesh.py SHOWCASE.glb|SHOWCASE.blend --out DIR --target-tris N [--tex-px 2048]
            [--name NAME] [--object NAME] [--body human|skirt|chibi] [--symmetry]
            [--autoremesher PATH] [--timeout S] [--voxel 0.005] [--cage 0.02] [--ray 0.06]
            [--margin-px 4] [--ao-samples 32] [--seed 0] [--blender PATH]
    blender -b --factory-startup -P game_mesh.py -- SHOWCASE ... (the same, inside Blender)
    python3 game_mesh.py --selftest                                  (the gate maths, numpy only)
    blender -b --factory-startup -P game_mesh.py -- --selftest-blender  (the whole route on a synthetic figure)

Run with python3 it starts Blender itself (--blender, $BLENDER, `blender` on PATH, the usual install).

input      a .glb (every mesh in it, joined) or a .blend (--object, else its only mesh object, appended
           into an empty scene; the file is never opened for writing). The game mesh is made in the
           showcase's own frame (world transforms applied), so both line up; S6 normalises as usual.
route      1 voxel remesh of a copy at --voxel x H (H the height; default 0.005), pieces under
             MIN_PIECE of its vertices dropped (specks); then the cavity filled (fill_cavity: an
             inward-facing inner shell joined to the skin at the hems survives the remesh as the inside
             of a thin hollow wall; openings up to about 2 x FILL_CLOSE voxels are closed) and remeshed
             again: a solid (a part the grid leaves apart, such as legs under a hem, stays its own piece);
           2 retopology to --target-tris: with --autoremesher PATH (the binary or its macOS .app),
             AutoRemesher on an OBJ of that surface, --target-quads target/2, under --timeout seconds
             (default 600) with QT_QPA_PLATFORM=offscreen; a timeout, a crash, no output or a result
             over the budget falls back to QuadriFlow and the reason is recorded (retopo.fallback).
             QuadriFlow (Blender): the surface collapse-decimated to PRE_DECIMATE x target first (it
             cancels, with a "needs to be manifold" warning, on a closed manifold surface more than
             about 6 x the target triangles), then target_faces = target/2, --symmetry for a
             symmetric character, --seed; up to QF_ATTEMPTS runs, the face target rescaled toward
             QF_AIM x target after each, the input decimated by 0.6 more after a cancel;
           3 Smart UV Project (UV_ANGLE), then each of its islands unwrapped angle-based from seams
             at the island borders (a projected island can fold onto itself); faces that still
             overlap (a band-shaped island flattens onto itself) projected again, up to 3 times;
             island scales averaged, packed; island margin --margin-px / --tex-px;
           4 Cycles bake from the showcase at --tex-px: base colour (Diffuse colour pass, sRGB),
             tangent normal and occlusion (--ao-samples), cage_extrusion --cage x H, max_ray_distance
             --ray x H. The base colour is baked with the showcase's metallic held at 0 (Cycles' Diffuse
             colour is base colour x (1 - metallic)); it is baked once more with no margin to count
             the missed texels. Roughness and metallic are not carried: the game material reads 0.7, 0.
gates      game.tris            the triangle count in [TRIS_FLOOR x target, target]
           game.one_surface     loose pieces of the game mesh, <= 1
           game.solid           enclosed volume / the volume of a SOLID_VOXEL x H voxel remesh of the
                                game mesh (which fills a thin hollow wall), >= SOLID_MIN: a hollow
                                shell (the inner shell kept as the inside of the wall) reads its
                                wall's share
           game.extent          max over x, y, z of |game extent - showcase extent| / H, <= EXTENT_MAX
           game.silhouette_iou_min  the smallest of 8 silhouette IoUs (azimuth every 45 deg, orthographic,
                                one frame, VIEW_PX px), >= IOU_MIN (assemble_parts' silhouette limit)
           game.uv_bounds       UV corners outside 0..1, <= 0
           game.uv_overlap      texels covered by two or more UV triangles / texels covered at all,
                                rasterised at --tex-px (a texel counts when its centre lies strictly
                                inside the triangle, so a shared edge never counts twice), <= UV_OVERLAP_MAX
           game.uv_stretch      per triangle, the singular values s1 >= s2 of the 3D -> UV map, scaled by
                                k = sqrt(UV area / 3D area) of the whole mesh: max(s1/k, k/s2) is how far
                                a texel is stretched or squashed in its worst direction against the mean
                                density; the 95th percentile weighted by 3D area, <= UV_STRETCH_MAX
           game.bake_miss       texels inside the UV islands (1 px in) that no ray reached, as a share,
                                from the no-margin base colour bake (alpha 0), <= BAKE_MISS_MAX
           game.bake_delta      mean CIE76 delta E between flat-lit, unshaded texture renders of the
                                showcase and the game mesh, same 8 cameras, over the pixels both cover
                                (2 px in from either edge), <= BAKE_DELTA_MAX
           game.mesh_check      character-autorig mesh_check.py --body on the written GLB passes
           Joints stay a picture: the deformation test of reference/game-mesh.md, after this run.
outputs    DIR/<name>_game.glb (uncompressed), DIR/<name>_game.blend (the game mesh alone, maps linked),
           DIR/textures/<name>_{BaseColor,Normal,Occlusion}.png, DIR/<name>_game_vs_showcase.png
           (rows: showcase textured, game textured, showcase clay, game clay; columns front, three
           quarter, left, back), DIR/<name>_bake_miss.png (UV space: grey islands, red where no ray hit),
           DIR/mesh_check.json, DIR/game_mesh.json.

Report: gate/1 (schemas/gate-1.json), every numeric gate with its margin. Exit codes: 0 every gate
passed (or a selftest passed); 2 a gate failed (or a selftest failed); 1 usage error or refused input
(no mesh, an unknown --object, no Blender). Arguments are parsed before bpy or numpy is imported.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
MESH_CHECK = os.path.normpath(os.path.join(HERE, "..", "..", "character-autorig", "scripts", "mesh_check.py"))

TRIS_FLOOR = 0.5          # game.tris: at least half the target (a retopology that collapsed reads under it)
EXTENT_MAX = 0.01         # game.extent: reference/game-mesh.md's "extents within 1%"
IOU_MIN = 0.95            # game.silhouette_iou_min: assemble_parts' assembly.silhouette limit
UV_OVERLAP_MAX = 0.001
UV_STRETCH_MAX = 2.0
BAKE_MISS_MAX = 0.005
BAKE_DELTA_MAX = 6.0      # delta E; assemble_parts' seam.colour limit
VIEW_PX = 512
AZIMUTHS = (0, 45, 90, 135, 180, 225, 270, 315)
SHEET_AZ = (0, 45, 90, 180)
FILL_CLOSE = 1            # cavity fill: openings up to about 2 x this many voxels are closed
SOLID_MIN = 0.9           # game.solid: enclosed volume / the volume of a coarse remesh of the same mesh
SOLID_VOXEL = 0.02        # that coarse remesh's voxel, fraction of the height: it fills any thin hollow wall
MIN_PIECE = 0.01          # voxel pieces under this share of the vertices are specks, dropped
UV_ANGLE = 45             # Smart UV Project's angle limit, degrees
PRE_DECIMATE = 4          # QuadriFlow input: this many times the target triangles (it cancels past ~6)
QF_ATTEMPTS = 3
QF_AIM = 0.95             # aim the triangle count at this share of the target
BODIES = ("human", "skirt", "chibi")


class Refused(Exception):
    pass


class UsageParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser():
    p = UsageParser(prog="game_mesh.py", description=__doc__.split("\n")[0],
                    epilog="Exit codes: 0 pass, 2 a gate failed, 1 usage error or refused input.")
    p.add_argument("--selftest", action="store_true", help="the gate maths on synthetic data (numpy)")
    p.add_argument("--selftest-blender", action="store_true", help="the whole route on a synthetic figure (bpy)")
    p.add_argument("showcase", nargs="?", help="the showcase .glb or .blend")
    p.add_argument("--out", help="the output folder")
    p.add_argument("--target-tris", type=int, help="the budget row's target_tris")
    p.add_argument("--tex-px", type=int, default=2048, help="the side of each baked map (default 2048)")
    p.add_argument("--name", help="default: the showcase file's stem")
    p.add_argument("--object", help="the showcase object in a .blend (default: its only mesh)")
    p.add_argument("--body", choices=BODIES, default="human", help="passed to mesh_check.py --body")
    p.add_argument("--symmetry", action="store_true", help="QuadriFlow mirror symmetry (X)")
    p.add_argument("--autoremesher", help="the AutoRemesher binary or .app: retopology by it, QuadriFlow on failure")
    p.add_argument("--timeout", type=float, default=600.0, help="seconds AutoRemesher may run (default 600)")
    p.add_argument("--voxel", type=float, default=0.005, help="voxel size, fraction of the height")
    p.add_argument("--cage", type=float, default=0.02, help="bake cage_extrusion, fraction of the height")
    p.add_argument("--ray", type=float, default=0.06, help="bake max_ray_distance, fraction of the height")
    p.add_argument("--margin-px", type=int, default=4, help="UV island and bake margin in texels")
    p.add_argument("--ao-samples", type=int, default=32)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--blender", help="the Blender executable, when run with python3")
    return p


def check_args(a):
    if a.selftest or a.selftest_blender:
        return None
    if not a.showcase or not a.out or not a.target_tris:
        return "SHOWCASE, --out and --target-tris are required"
    if a.target_tris < 100:
        return "--target-tris must be at least 100"
    if a.tex_px < 64 or a.tex_px & (a.tex_px - 1):
        return "--tex-px must be a power of two, 64 or more"
    for k in ("voxel", "cage", "ray"):
        if not 0 < getattr(a, k) < 0.5:
            return f"--{k} must be a fraction of the height in (0, 0.5)"
    if a.timeout <= 0:
        return "--timeout must be positive"
    if a.margin_px < 0 or a.ao_samples < 1:
        return "--margin-px must be 0 or more and --ao-samples 1 or more"
    if not os.path.isfile(a.showcase):
        return f"no such file: {a.showcase}"
    return None


def _np():
    import numpy as np
    return np


# Between the shared:gate_margin markers: a copy of tools/shared-blocks/gate_margin.py;
# check-consistency keeps every copy equal.
# >>> shared:gate_margin
def gate_margin(value, limit, op=None):
    """A gate's signed distance to its limit (gate/1 `margin`, schemas/README.md): positive is safe,
    negative is failing, 0 sits on the limit. op "<=": (L - v) / |L|; ">=": (v - L) / |L|; "range"
    (limit [lo, hi]): min(v - lo, hi - v) / ((hi - lo) / 2). A zero |L| or hi - lo keeps the plain
    difference. With op None a string limit such as "<= 0.08" or ">= 0.9" gives both. None when the
    value or limit is a bool, a string, not finite, or the op is not known: write no margin then."""
    import math

    def num(x):
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            return None
        return float(x) if math.isfinite(x) else None

    if op is None and isinstance(limit, str):
        s = limit.strip()
        for o in ("<=", ">="):
            if s.startswith(o):
                try:
                    op, limit = o, float(s[len(o):].strip())
                except ValueError:
                    return None
                break
    v = num(value)
    if v is None:
        return None
    if op == "range":
        if not isinstance(limit, (list, tuple)) or len(limit) != 2:
            return None
        lo, hi = num(limit[0]), num(limit[1])
        if lo is None or hi is None or hi < lo:
            return None
        d = min(v - lo, hi - v)
        half = (hi - lo) / 2
        m = d / half if half > 0 else d
    elif op in ("<=", ">="):
        lim = num(limit)
        if lim is None:
            return None
        d = lim - v if op == "<=" else v - lim
        m = d / abs(lim) if lim != 0 else d
    else:
        return None
    return round(m, 4) if math.isfinite(m) else None
# <<< shared:gate_margin


def r4(x):
    return None if x is None else round(float(x), 4)


def gate(name, value, limit, op, **extra):
    """One gate/1 gate: limit a number with op "<=" / ">=", or [lo, hi] with op "range"."""
    if value is None:
        passed = False
    elif op == "range":
        passed = limit[0] <= value <= limit[1]
    elif op == "<=":
        passed = value <= limit
    else:
        passed = value >= limit
    g = {"name": name, "value": value, "limit": limit if op == "range" else f"{op} {limit}", "pass": bool(passed)}
    m = gate_margin(value, limit, op)
    if m is not None:
        g["margin"] = m
    g.update(extra)
    return g


def report_doc(gates, **extra):
    ok = bool(gates) and all(g["pass"] for g in gates) and "refused" not in extra and "error" not in extra
    verdict = "green" if ok else ("harness" if "error" in extra and not gates else "failed")
    return {"schema": "gate/1", "tool": "game_mesh", "pass": ok, "verdict": verdict, "gates": gates, **extra}


# ------------------------------------------------------------------------------- the gate maths (numpy)
def raster_count(T, w, h, strict=True):
    """How many triangles cover each texel centre: T (n, 3, 2) in pixel units (x right, y the row),
    counts (h, w). strict: a centre counts only strictly inside a triangle, so two triangles sharing an
    edge never both claim a centre on it (the overlap count); else a centre on an edge counts too (the
    cover). Degenerate triangles cover nothing."""
    np = _np()
    T = np.asarray(T, float)
    cnt = np.zeros((h, w), np.int32)
    if not len(T):
        return cnt
    area2 = ((T[:, 1, 0] - T[:, 0, 0]) * (T[:, 2, 1] - T[:, 0, 1]) -
             (T[:, 1, 1] - T[:, 0, 1]) * (T[:, 2, 0] - T[:, 0, 0]))
    keep = np.abs(area2) > 1e-12
    T, sgn = T[keep], np.sign(area2[keep])
    lo = np.clip(np.floor(T.min(1) - 0.5).astype(np.int64) + 1, 0, [w, h])
    hi = np.clip(np.floor(T.max(1) - 0.5).astype(np.int64), -1, [w - 1, h - 1])
    span = np.maximum(hi - lo + 1, 0).max(1)
    todo = (hi[:, 0] >= lo[:, 0]) & (hi[:, 1] >= lo[:, 1])
    for k in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1 << 20):
        sel = np.nonzero(todo & (span <= k))[0]
        todo[sel] = False
        if not len(sel):
            continue
        kk = min(k, max(w, h))
        gx, gy = np.meshgrid(np.arange(kk), np.arange(kk))
        gx, gy = gx.reshape(-1), gy.reshape(-1)
        step = max(1, int(2e6 // (kk * kk)))
        for c0 in range(0, len(sel), step):
            s = sel[c0:c0 + step]
            px = lo[s, 0][:, None] + gx[None]
            py = lo[s, 1][:, None] + gy[None]
            fx, fy = px + 0.5, py + 0.5
            a, b, c = T[s, 0], T[s, 1], T[s, 2]

            def edge(p, q):
                return ((q[:, 0, None] - p[:, 0, None]) * (fy - p[:, 1, None]) -
                        (q[:, 1, None] - p[:, 1, None]) * (fx - p[:, 0, None])) * sgn[s, None]

            e0, e1, e2 = edge(a, b), edge(b, c), edge(c, a)
            inside = ((e0 > 0) & (e1 > 0) & (e2 > 0)) if strict else ((e0 >= 0) & (e1 >= 0) & (e2 >= 0))
            inside &= (px <= hi[s, 0][:, None]) & (py <= hi[s, 1][:, None])
            np.add.at(cnt, (py[inside], px[inside]), 1)
    return cnt


def uv_pixels(UV, F, px):
    """UV triangles (n, 3, 2) in texel units of a px x px map, row 0 at v = 0 (Blender's pixel order)."""
    np = _np()
    return np.asarray(UV, float)[np.asarray(F)] * px


def uv_overlap(UV, F, px):
    """(overlapped share, covered texels): texels covered by >= 2 triangles / texels covered at all."""
    T = uv_pixels(UV, F, px)
    over = int((raster_count(T, px, px) >= 2).sum())
    covered = int((raster_count(T, px, px, strict=False) >= 1).sum())
    return (over / covered if covered else 0.0), covered


def uv_bounds(UV, tol=1e-6):
    """UV corners outside 0..1 (a tol of slack)."""
    np = _np()
    UV = np.asarray(UV, float)
    return int(((UV < -tol) | (UV > 1 + tol)).any(1).sum())


def weighted_quantile(x, w, q):
    np = _np()
    x, w = np.asarray(x, float), np.asarray(w, float)
    if not len(x) or w.sum() <= 0:
        return None
    o = np.argsort(x)
    c = np.cumsum(w[o]) / w.sum()
    return float(x[o][min(int(np.searchsorted(c, q)), len(x) - 1)])


def uv_stretch(V, UV, F, q=0.95):
    """(p95 of max(s1/k, k/s2) weighted by 3D area, p95 of s1/s2): see game.uv_stretch. V (n, 3) per
    vertex, UV (n, 2) per corner-vertex (same indexing as V), F (m, 3)."""
    np = _np()
    P = np.asarray(V, float)[F]
    Q = np.asarray(UV, float)[F]
    e1, e2 = P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
    n = np.cross(e1, e2)
    a3 = np.linalg.norm(n, axis=1) / 2
    d1, d2 = Q[:, 1] - Q[:, 0], Q[:, 2] - Q[:, 0]
    auv = np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / 2
    good = a3 > 1e-14
    if not good.any() or auv.sum() <= 0:
        return None, None
    k = math.sqrt(auv[good].sum() / a3[good].sum())
    e1, e2, n, d1, d2, a3 = e1[good], e2[good], n[good], d1[good], d2[good], a3[good]
    l1 = np.linalg.norm(e1, axis=1)
    x = e1 / l1[:, None]
    y = np.cross(n / np.linalg.norm(n, axis=1)[:, None], x)
    Pm = np.stack([np.stack([l1, np.zeros_like(l1)], 1), np.stack([(e2 * x).sum(1), (e2 * y).sum(1)], 1)], 2)
    Qm = np.stack([d1, d2], 2)                       # columns: the two edges
    J = Qm @ np.linalg.inv(Pm)
    s = np.linalg.svd(J, compute_uv=False)
    s1, s2 = s[:, 0], s[:, 1]
    with np.errstate(divide="ignore", invalid="ignore"):
        worst = np.where(s2 > 1e-12, np.maximum(s1 / k, k / np.maximum(s2, 1e-300)), 1e6)
        aniso = np.where(s2 > 1e-12, s1 / np.maximum(s2, 1e-300), 1e6)
    return weighted_quantile(worst, a3, q), weighted_quantile(aniso, a3, q)


def erode(mask, r):
    """4-neighbour erosion, r steps; the border counts as outside."""
    np = _np()
    m = mask.copy()
    for _ in range(r):
        p = np.pad(m, 1, constant_values=False)
        m = m & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return m


def bake_miss(UV, F, alpha, px):
    """(share, texels, missed mask): texels inside the UV islands (1 texel in) whose no-margin bake alpha
    stayed 0 (no ray hit), over the texels inside."""
    np = _np()
    inside = erode(raster_count(uv_pixels(UV, F, px), px, px, strict=False) >= 1, 1)
    n = int(inside.sum())
    missed = inside & (np.asarray(alpha) < 0.5)
    return (float(missed.sum()) / n if n else None), n, missed


def iou(a, b):
    np = _np()
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 1.0


def srgb_to_lab(rgb):
    """CIELAB (D65) of sRGB values in 0..1, shape (..., 3)."""
    np = _np()
    c = np.clip(np.asarray(rgb, float), 0, 1)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def view_compare(a, b, edge_px=2):
    """Two RGBA frames (h, w, 4), 0..1, same camera: (silhouette IoU, sum of delta E, pixels compared)."""
    np = _np()
    ma, mb = a[..., 3] > 0.5, b[..., 3] > 0.5
    both = erode(ma, edge_px) & erode(mb, edge_px)
    n = int(both.sum())
    if not n:
        return iou(ma, mb), 0.0, 0
    de = np.linalg.norm(srgb_to_lab(a[..., :3][both]) - srgb_to_lab(b[..., :3][both]), axis=1)
    return iou(ma, mb), float(de.sum()), n


# ------------------------------------------------------------------------------------------- Blender
def find_blender(explicit=None):
    for c in (explicit, os.environ.get("BLENDER"), shutil.which("blender"),
              "/Applications/Blender.app/Contents/MacOS/Blender"):
        if c and (os.path.isfile(c) or shutil.which(c)):
            return c
    for c in sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"), reverse=True):
        return c
    return None


def only(*objs, active):
    import bpy
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def bake_world(obj):
    """Apply the world matrix to the mesh and drop the parent: vertex coordinates are world coordinates."""
    mw = obj.matrix_world.copy()
    obj.parent = None
    obj.data.transform(mw)
    obj.matrix_world.identity()


def load_showcase(path, object_name):
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
        meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    elif ext == ".blend":
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            names = list(src.objects)
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.objects = [object_name] if object_name in names else names
        meshes = [o for o in dst.objects if o is not None and o.type == 'MESH']
        if object_name:
            meshes = [o for o in meshes if o.name == object_name]
            if not meshes:
                raise Refused(f"no mesh object {object_name!r} in {path}")
        elif len(meshes) != 1:
            raise Refused(f"{path} has {len(meshes)} mesh objects: name one with --object")
        for o in meshes:
            bpy.context.scene.collection.objects.link(o)
    else:
        raise Refused(f"{path}: a .glb or .blend is wanted")
    if not meshes:
        raise Refused(f"no mesh in {path}")
    for o in meshes:
        if o.data.users > 1:
            o.data = o.data.copy()
        bake_world(o)
    for o in [o for o in bpy.data.objects if o not in meshes]:
        bpy.data.objects.remove(o, do_unlink=True)
    if len(meshes) > 1:
        only(*meshes, active=meshes[0])
        bpy.ops.object.join()
    show = meshes[0]
    show.name = "Showcase"
    if not len(show.data.polygons):
        raise Refused(f"no faces in {path}")
    return show


def tri_count(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def pieces(me):
    """Vertex count of each connected piece, largest first, and each vertex's piece label."""
    np = _np()
    n = len(me.vertices)
    E = np.empty(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", E)
    parent = np.arange(n)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b in E.reshape(-1, 2):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    lab = np.array([find(i) for i in range(n)])
    roots, inv, cnt = np.unique(lab, return_inverse=True, return_counts=True)
    return cnt, inv


def drop_specks(obj):
    """Delete the pieces under MIN_PIECE of the vertices (the voxel remesh's specks). Returns
    (pieces dropped, vertices dropped, vertex counts of the pieces kept)."""
    import bmesh
    cnt, inv = pieces(obj.data)
    keep = cnt >= MIN_PIECE * cnt.sum()
    if keep.all():
        return 0, 0, sorted(cnt.tolist(), reverse=True)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not keep[inv[v.index]]], context='VERTS')
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return int((~keep).sum()), int(cnt[~keep].sum()), sorted(cnt[keep].tolist(), reverse=True)


def _dilate(m):
    o = m.copy()
    o[1:] |= m[:-1]
    o[:-1] |= m[1:]
    o[:, 1:] |= m[:, :-1]
    o[:, :-1] |= m[:, 1:]
    o[:, :, 1:] |= m[:, :, :-1]
    o[:, :, :-1] |= m[:, :, 1:]
    return o


def fill_cavity(obj, vs, k=FILL_CLOSE):
    """Fill what the surface encloses. An inward-facing inner shell joined to the skin at the hems survives
    a voxel remesh as the inside of a thin hollow wall. The surface is rasterised on a grid of cell vs,
    thickened by k cells, the outside flood-filled from the grid's border, and the rest, k + 1 cells in
    from the outside, is added as blocks: the next voxel remesh of surface plus blocks is a solid.
    Returns the number of cells filled."""
    import bpy
    np = _np()
    V, F, _ = mesh_arrays(obj)
    lo = V.min(0) - (k + 3) * vs
    n = np.ceil((V.max(0) + (k + 3) * vs - lo) / vs).astype(int) + 1
    wall = np.zeros(n, bool)
    T = V[F]
    steps = np.ceil(2 * np.linalg.norm(T - np.roll(T, 1, axis=1), axis=2).max(1) / vs).astype(int).clip(1)
    for m in np.unique(steps):          # barycentric points at most half a cell apart on every triangle
        i, j = np.mgrid[0:m + 1, 0:m + 1]
        keep = i + j <= m
        w = np.stack([i[keep], j[keep], m - i[keep] - j[keep]], 1) / m
        P = np.einsum("bk,nkd->nbd", w, T[steps == m]).reshape(-1, 3)
        idx = np.floor((P - lo) / vs).astype(int)
        wall[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    for _ in range(k):
        wall = _dilate(wall)
    ext = np.zeros(n, bool)
    ext[0] = ext[-1] = True
    ext[:, 0] = ext[:, -1] = True
    ext[:, :, 0] = ext[:, :, -1] = True
    ext &= ~wall
    while True:
        grown = _dilate(ext) & ~wall
        if (grown == ext).all():
            break
        ext = grown
    for _ in range(k + 1):
        ext = _dilate(ext)
    fill = ~ext
    if not fill.any():
        return 0
    pad = np.pad(fill, 1)
    eye = np.eye(3, dtype=int)
    quads = []
    for ax in range(3):
        a1, a2 = [i for i in range(3) if i != ax]
        for sgn in (-1, 1):
            sl = [slice(1, -1)] * 3
            sl[ax] = slice(1 + sgn, pad.shape[ax] - 1 + sgn)
            cells = np.argwhere(fill & ~pad[tuple(sl)])
            o = cells + (eye[ax] if sgn > 0 else 0)
            q = np.stack([o, o + eye[a1], o + eye[a1] + eye[a2], o + eye[a2]], 1)
            quads.append(q[:, ::-1] if sgn < 0 else q)
    Q = np.concatenate(quads).reshape(-1, 3)
    corners, inv = np.unique(Q, axis=0, return_inverse=True)
    me = bpy.data.meshes.new("cavity_fill")
    me.from_pydata((lo + corners * vs).tolist(), [], inv.reshape(-1, 4).tolist())
    me.update()
    blocks = bpy.data.objects.new("cavity_fill", me)
    bpy.context.scene.collection.objects.link(blocks)
    only(obj, blocks, active=obj)
    bpy.ops.object.join()
    return int(fill.sum())


def volume(me):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    v = bm.calc_volume(signed=True)
    bm.free()
    return v


def solid_ratio(obj, H):
    """game.solid: the enclosed volume over that of a SOLID_VOXEL x H remesh of the same mesh (which fills
    a thin hollow wall): about 1 for a solid, the wall's share of the volume for a hollow shell."""
    import bpy
    c = duplicate(obj, "solid_probe")
    c.data.remesh_voxel_size = SOLID_VOXEL * H
    only(c, active=c)
    bpy.ops.object.voxel_remesh()
    ref = volume(c.data)
    bpy.data.objects.remove(c, do_unlink=True)
    return volume(obj.data) / ref if ref > 0 else None


def _selected_faces(obj):
    import bmesh
    bm = bmesh.from_edit_mesh(obj.data)
    return sum(1 for f in bm.faces if f.select)


def non_manifold_edges(me):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    n = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return n


def duplicate(obj, name):
    import bpy
    c = obj.copy()
    c.data = obj.data.copy()
    c.name = c.data.name = name
    bpy.context.scene.collection.objects.link(c)
    return c


def quadriflow(obj, target, symmetry, seed):
    """QuadriFlow to `target` triangles (quads count twice). Returns (ok, record)."""
    import bpy

    def decimate(o, ratio):
        only(o, active=o)
        m = o.modifiers.new("pre", "DECIMATE")
        m.ratio = ratio
        m.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=m.name)

    pre_ratio = min(1.0, PRE_DECIMATE * target / max(1, tri_count(obj.data)))
    if pre_ratio < 1.0:
        decimate(obj, pre_ratio)
    base = obj.data.copy()
    rec = {"tool": "quadriflow", "pre_tris": tri_count(base), "attempts": []}
    faces, best = max(1, target // 2), None
    for _ in range(QF_ATTEMPTS):
        obj.data = base.copy()
        only(obj, active=obj)
        res = bpy.ops.object.quadriflow_remesh(target_faces=int(faces), use_mesh_symmetry=symmetry,
                                               use_preserve_sharp=False, use_preserve_boundary=False,
                                               mode="FACES", seed=seed, smooth_normals=False)
        tris = tri_count(obj.data)
        done = res == {'FINISHED'} and tris < tri_count(base)
        rec["attempts"].append({"target_faces": int(faces), "input_tris": tri_count(base),
                                "result": sorted(res)[0], "tris": tris if done else None})
        if done and TRIS_FLOOR * target <= tris <= target:
            score = abs(tris - QF_AIM * target)
            if best is None or score < best[0]:
                best = (score, obj.data.copy(), tris)
            if tris >= 0.85 * target:
                break
        if not done:                    # cancelled: a coarser input surface
            obj.data = base
            decimate(obj, 0.6)
            base = obj.data.copy()
        else:
            faces = max(1, int(faces * QF_AIM * target / tris))
    if best is None:
        return False, rec
    obj.data = best[1]
    rec["tris"] = best[2]
    return True, rec


def autoremesher_exe(path):
    if path.endswith(".app") and os.path.isdir(path):
        found = glob.glob(os.path.join(path, "Contents", "MacOS", "*"))
        if found:
            return found[0]
    return path


def autoremesher(exe, obj, target, timeout, work):
    """AutoRemesher on an OBJ of obj. Returns (imported object or None, record)."""
    import bpy
    exe = autoremesher_exe(exe)
    src, dst, rpt = (os.path.join(work, n) for n in ("ar_in.obj", "ar_out.obj", "ar_report.txt"))
    only(obj, active=obj)
    bpy.ops.wm.obj_export(filepath=src, export_selected_objects=True, export_uv=False, export_normals=False,
                          export_materials=False, apply_modifiers=True)
    cmd = [exe, "--input", src, "--output", dst, "--report", rpt, "--target-quads", str(max(1, target // 2))]
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    rec = {"tool": "autoremesher", "command": cmd}
    t0 = time.time()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        rec.update(seconds=round(time.time() - t0, 1), fallback=f"timeout after {timeout:g} s")
        return None, rec
    except OSError as exc:
        rec.update(seconds=0.0, fallback=f"could not start: {exc}")
        return None, rec
    rec["seconds"] = round(time.time() - t0, 1)
    if res.returncode != 0:
        tail = (res.stderr or res.stdout or "").strip().splitlines()[-1:] or [""]
        rec["fallback"] = f"exit {res.returncode}: {tail[0][:200]}"
        return None, rec
    if not os.path.isfile(dst) or os.path.getsize(dst) == 0:
        rec["fallback"] = "no output file"
        return None, rec
    if os.path.isfile(rpt):
        with open(rpt, encoding="utf-8", errors="replace") as handle:
            rec["report"] = handle.read()[:2000]
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=dst)
    new = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    if not new or not len(new[0].data.polygons):
        for o in new:
            bpy.data.objects.remove(o, do_unlink=True)
        rec["fallback"] = "an empty mesh"
        return None, rec
    out = new[0]
    for o in new[1:]:
        bpy.data.objects.remove(o, do_unlink=True)
    bake_world(out)
    rec["tris"] = tri_count(out.data)
    if rec["tris"] > target:
        rec["fallback"] = f"over the budget: {rec['tris']} triangles"
        bpy.data.objects.remove(out, do_unlink=True)
        return None, rec
    return out, rec


def mesh_arrays(obj):
    """Vertices (world = local), triangles and per-corner UVs of a triangulated copy: (V, F, UVc, Fc)."""
    import bmesh
    np = _np()
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    V = np.array([v.co[:] for v in bm.verts], float)
    F = np.array([[v.index for v in f.verts] for f in bm.faces], np.int64)
    uvl = bm.loops.layers.uv.active
    UVc = None
    if uvl is not None:
        UVc = np.array([[lp[uvl].uv[:] for lp in f.loops] for f in bm.faces], float)
    bm.free()
    return V, F, UVc


def image_pixels(img):
    np = _np()
    a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)


def bake(show, game, kind, img, margin, samples, **extra):
    import bpy
    scene = bpy.context.scene
    scene.cycles.samples = samples
    scene.render.bake.margin = margin
    nt = game.data.materials[0].node_tree
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = img
    nt.nodes.active = node
    only(show, game, active=game)
    t0 = time.time()
    res = bpy.ops.object.bake(type=kind, **extra)
    nt.nodes.remove(node)
    if res != {'FINISHED'}:
        raise RuntimeError(f"bake {kind} returned {res}")
    return time.time() - t0


class NoMetal:
    """Cycles' Diffuse colour pass is base colour x (1 - metallic): a metal button bakes black. Inside this
    block every Principled BSDF of obj reads metallic 0 (links cut, values kept and put back)."""

    def __init__(self, obj):
        self.obj, self.saved = obj, []

    def __enter__(self):
        for mat in {m for m in self.obj.data.materials if m is not None and m.use_nodes}:
            nt = mat.node_tree
            for n in nt.nodes:
                if n.type == 'BSDF_PRINCIPLED':
                    sock = n.inputs["Metallic"]
                    links = [(lk.from_socket, sock) for lk in sock.links]
                    for lk in list(sock.links):
                        nt.links.remove(lk)
                    self.saved.append((nt, sock, sock.default_value, links))
                    sock.default_value = 0.0
        return self

    def __exit__(self, *exc):
        for nt, sock, value, links in self.saved:
            sock.default_value = value
            for a, b in links:
                nt.links.new(a, b)
        return False


def base_colour_node(obj):
    """The image node feeding the Principled BSDF's Base Color, else the first image node."""
    for mat in obj.data.materials:
        if mat is None or not mat.use_nodes:
            continue
        nt = mat.node_tree
        for n in nt.nodes:
            if n.type == 'BSDF_PRINCIPLED' and n.inputs["Base Color"].links:
                src = n.inputs["Base Color"].links[0].from_node
                if src.type == 'TEX_IMAGE':
                    return mat, src
        for n in nt.nodes:
            if n.type == 'TEX_IMAGE':
                return mat, n
    return None, None


def game_material(name, bc, nm, ao):
    import bpy
    import ship_merge
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bc
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    t2 = nt.nodes.new("ShaderNodeTexImage")
    t2.image = nm
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(t2.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    t3 = nt.nodes.new("ShaderNodeTexImage")
    t3.image = ao
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(t3.outputs["Color"], sep.inputs["Color"])
    grp = nt.nodes.new("ShaderNodeGroup")
    grp.node_tree = ship_merge.gltf_output_group()
    nt.links.new(sep.outputs["Red"], grp.inputs["Occlusion"])
    bsdf.inputs["Roughness"].default_value = 0.7
    nt.nodes.active = t
    return mat


class Views:
    """Orthographic cameras round the showcase: azimuth 0 is the front (the character faces -Y)."""

    def __init__(self, show, px):
        import bpy
        from mathutils import Vector
        np = _np()
        V, _, _ = mesh_arrays(show)
        lo, hi = V.min(0), V.max(0)
        self.centre = Vector(((lo + hi) / 2).tolist())
        self.height = float(hi[2] - lo[2])
        reach = float(np.sqrt(((V[:, :2] - (lo[:2] + hi[:2]) / 2) ** 2).sum(1)).max())
        self.scale = 1.08 * max(self.height, 2 * reach)
        scene = bpy.context.scene
        scene.render.engine = 'BLENDER_WORKBENCH'
        scene.render.resolution_x = scene.render.resolution_y = px
        scene.render.resolution_percentage = 100
        scene.render.film_transparent = True
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGBA'
        scene.view_settings.view_transform = 'Standard'
        scene.display.shading.show_backface_culling = False
        cd = bpy.data.cameras.new("GameMeshCam")
        cd.type = 'ORTHO'
        cd.ortho_scale = self.scale
        cd.clip_end = 20 * self.scale
        self.cam = bpy.data.objects.new("GameMeshCam", cd)
        scene.collection.objects.link(self.cam)
        scene.camera = self.cam
        self.tmp = tempfile.mkdtemp(prefix="game_mesh_")

    def shoot(self, obj, others, az, mode):
        """RGBA frame (h, w, 4), top row first, of obj alone: mode 'texture' (flat, unshaded) or 'clay'."""
        import bpy
        from mathutils import Matrix, Vector
        scene = bpy.context.scene
        for o in others:
            o.hide_render = True
        obj.hide_render = False
        sh = scene.display.shading
        if mode == "texture":
            sh.light, sh.color_type = 'FLAT', 'TEXTURE'
        else:
            sh.light, sh.color_type = 'STUDIO', 'SINGLE'
            sh.single_color = (0.8, 0.8, 0.78)
        a = math.radians(az)
        d = Vector((math.sin(a), math.cos(a), 0.0))      # the way the camera looks
        z = -d
        x = Vector((0, 0, 1)).cross(z).normalized()
        y = z.cross(x)
        self.cam.matrix_world = Matrix(((x[0], y[0], z[0], 0), (x[1], y[1], z[1], 0), (x[2], y[2], z[2], 0),
                                        (0, 0, 0, 1)))
        self.cam.location = self.centre - d * 5 * self.scale
        path = os.path.join(self.tmp, f"v{az}_{mode}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(path)
        out = image_pixels(img)[::-1].copy()
        bpy.data.images.remove(img)
        return out

    def close(self):
        import bpy
        bpy.data.objects.remove(self.cam, do_unlink=True)
        shutil.rmtree(self.tmp, ignore_errors=True)


def save_sheet(rows, path):
    import bpy
    np = _np()
    h, w = rows[0][0].shape[:2]
    gap = 6
    H = len(rows) * h + (len(rows) - 1) * gap
    W = len(rows[0]) * w + (len(rows[0]) - 1) * gap
    sheet = np.ones((H, W, 4), np.float32)
    for r, line in enumerate(rows):
        for k, a in enumerate(line):
            al = a[..., 3:4]
            sheet[r * (h + gap): r * (h + gap) + h, k * (w + gap): k * (w + gap) + w, :3] = a[..., :3] * al + (1 - al)
    img = bpy.data.images.new(os.path.basename(path), W, H, alpha=False)
    img.pixels.foreach_set(sheet[::-1].reshape(-1))
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def run_mesh_check(glb, body, out_json):
    if not os.path.isfile(MESH_CHECK):
        return None, f"mesh_check.py not found at {MESH_CHECK} (install character-autorig beside this skill)"
    if os.path.exists(out_json):           # a report left by an earlier run must never be read as this one
        os.remove(out_json)
    cmd = [sys.executable, "-I", MESH_CHECK, glb, "--body", body, "--out", out_json]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        return None, "mesh_check.py timed out after 1800 s"
    why = f"mesh_check.py exit {res.returncode}: {(res.stderr or '').strip()[-300:]}"
    if res.returncode not in (0, 2):       # 1 is usage or refused input: nothing was measured
        return None, why
    try:
        with open(out_json, encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError):
        try:
            doc = json.loads(res.stdout)
        except ValueError:
            return None, why
    if not isinstance(doc, dict) or bool(doc.get("pass")) != (res.returncode == 0):
        return None, f"mesh_check.py's report and its exit code disagree ({why})"
    return doc, None


def run(a, stop_after_retopo=False):
    """The route. Returns (exit code, gate/1 report)."""
    import bpy
    np = _np()
    t_all = time.time()
    secs = {}
    name = a.name or os.path.splitext(os.path.basename(a.showcase))[0]
    out = os.path.abspath(a.out)
    os.makedirs(os.path.join(out, "textures"), exist_ok=True)
    T = int(a.target_tris)

    t0 = time.time()
    show = load_showcase(os.path.abspath(a.showcase), a.object)
    Vs, Fs, _ = mesh_arrays(show)
    H = float(Vs[:, 2].max() - Vs[:, 2].min())
    ext_show = Vs.max(0) - Vs.min(0)
    secs["load"] = round(time.time() - t0, 1)
    info = {"name": name, "showcase": os.path.abspath(a.showcase), "height": r4(H), "target_tris": T,
            "tex_px": a.tex_px, "showcase_tris": int(len(Fs)), "blender": bpy.app.version_string}

    # 1 one closed surface
    t0 = time.time()
    surf = duplicate(show, f"{name}_surface")
    surf.data.materials.clear()
    surf.data.remesh_voxel_size = a.voxel * H
    only(surf, active=surf)
    bpy.ops.object.voxel_remesh()
    dropped, dropped_v, kept = drop_specks(surf)
    filled = fill_cavity(surf, a.voxel * H)
    if filled:
        only(surf, active=surf)
        bpy.ops.object.voxel_remesh()
        d2, v2, kept = drop_specks(surf)
        dropped, dropped_v = dropped + d2, dropped_v + v2
    info["voxel"] = {"cells_filled": filled, "size": r4(a.voxel * H), "tris": tri_count(surf.data),
                     "pieces_dropped": dropped,
                     "vertices_dropped": dropped_v, "pieces_kept": kept,
                     "non_manifold_edges": non_manifold_edges(surf.data)}
    secs["voxel"] = round(time.time() - t0, 1)

    # 2 retopology
    t0 = time.time()
    game, retopo = None, {}
    if a.autoremesher:
        work = tempfile.mkdtemp(prefix="game_mesh_ar_")
        try:
            game, retopo = autoremesher(a.autoremesher, surf, T, a.timeout, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    if game is None:
        game = duplicate(surf, f"{name}_game")
        ok, rec = quadriflow(game, T, a.symmetry, a.seed)
        if retopo:
            rec["autoremesher"] = retopo
            rec["fallback"] = retopo.get("fallback")
        retopo = rec
        if not ok:
            bpy.data.objects.remove(game, do_unlink=True)
            game = None
    else:
        game.name = game.data.name = f"{name}_game"
    secs["retopo"] = round(time.time() - t0, 1)
    info["retopo"] = retopo
    bpy.data.objects.remove(surf, do_unlink=True)
    gates = []
    if game is None:
        gates.append(gate("game.tris", None, [int(TRIS_FLOOR * T), T], "range",
                          why="the retopology gave no mesh inside the budget (retopo.attempts)"))
        return 2, report_doc(gates, **info, seconds=secs)
    if stop_after_retopo:
        return 0, report_doc([gate("game.tris", tri_count(game.data), [int(TRIS_FLOOR * T), T], "range")],
                             **info, seconds=secs)

    # loose bits QuadriFlow or AutoRemesher left: wire edges and lone vertices
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(game.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bm.to_mesh(game.data)
    bm.free()
    game.data.materials.clear()
    for p in game.data.polygons:
        p.use_smooth = True
    tris = tri_count(game.data)
    cnt, _ = pieces(game.data)
    info["game"] = {"tris": tris, "faces": len(game.data.polygons), "pieces": int(len(cnt)),
                    "non_manifold_edges": non_manifold_edges(game.data)}
    gates.append(gate("game.tris", tris, [int(TRIS_FLOOR * T), T], "range"))
    gates.append(gate("game.one_surface", int(len(cnt)), 1, "<="))
    sr = solid_ratio(game, H)
    gates.append(gate("game.solid", r4(sr), SOLID_MIN, ">="))
    Vg, Fg, _ = mesh_arrays(game)
    ext = float(np.abs((Vg.max(0) - Vg.min(0)) - ext_show).max() / H)
    gates.append(gate("game.extent", r4(ext), EXTENT_MAX, "<="))

    # 3 UVs
    t0 = time.time()
    scene_tool = bpy.context.scene.tool_settings
    only(game, active=game)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(UV_ANGLE), island_margin=a.margin_px / a.tex_px,
                             area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.mesh.mark_seam(clear=True)
    bpy.ops.uv.seams_from_islands()                    # each projected island unwrapped flat: no folds
    bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=a.margin_px / a.tex_px)
    sync = scene_tool.use_uv_select_sync
    scene_tool.use_uv_select_sync = True
    reprojected = []

    def pack():
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.average_islands_scale()
        bpy.ops.uv.pack_islands(margin=a.margin_px / a.tex_px, rotate=True)
    pack()
    for _ in range(3):              # an island shaped like a band flattens onto itself: project it again
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.uv.select_overlap()
        n = _selected_faces(game)
        if not n:
            break
        reprojected.append(n)
        bpy.ops.uv.smart_project(angle_limit=math.radians(UV_ANGLE), island_margin=a.margin_px / a.tex_px,
                                 area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
        pack()
    scene_tool.use_uv_select_sync = sync
    bpy.ops.object.mode_set(mode='OBJECT')
    Vg, Fg, UVc = mesh_arrays(game)
    # per-corner UVs: index them as their own vertices
    Fc = np.arange(len(Fg) * 3).reshape(-1, 3)
    UVflat, Vflat = UVc.reshape(-1, 2), Vg[Fg].reshape(-1, 3)
    out_n = uv_bounds(UVflat)
    ov, covered = uv_overlap(UVflat, Fc, a.tex_px)
    st, aniso = uv_stretch(Vflat, UVflat, Fc)
    info["uv"] = {"islands_margin_px": a.margin_px, "covered_share": r4(covered / a.tex_px ** 2),
                  "faces_reprojected": reprojected,
                  "stretch_p95": r4(st), "anisotropy_p95": r4(aniso)}
    gates.append(gate("game.uv_bounds", out_n, 0, "<="))
    gates.append(gate("game.uv_overlap", r4(ov), UV_OVERLAP_MAX, "<="))
    gates.append(gate("game.uv_stretch", r4(st), UV_STRETCH_MAX, "<="))
    secs["uv"] = round(time.time() - t0, 1)

    # 4 bake
    t0 = time.time()
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.use_denoising = False
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.use_cage = False
    scene.render.bake.cage_extrusion = a.cage * H
    scene.render.bake.max_ray_distance = a.ray * H
    scene.render.bake.target = 'IMAGE_TEXTURES'
    px = a.tex_px
    tmp_mat = bpy.data.materials.new(f"{name}_bake")
    tmp_mat.use_nodes = True
    game.data.materials.append(tmp_mat)
    probe = bpy.data.images.new(f"{name}_miss", px, px, alpha=True)
    with NoMetal(show):
        bake_secs = {"miss": bake(show, game, 'DIFFUSE', probe, 0, 1, pass_filter={'COLOR'})}
    alpha = image_pixels(probe)[..., 3]
    miss, inside, missed = bake_miss(UVflat, Fc, alpha, px)
    pic = np.ones((px, px, 4), np.float32)                 # white outside, grey islands, red: no ray hit
    pic[alpha >= 0.5, :3] = 0.7
    pic[missed, :3] = (1.0, 0.0, 0.0)
    probe.pixels.foreach_set(pic.reshape(-1))
    probe.filepath_raw = miss_png = os.path.join(out, f"{name}_bake_miss.png")
    probe.file_format = 'PNG'
    probe.save()
    bpy.data.images.remove(probe)
    gates.append(gate("game.bake_miss", r4(miss), BAKE_MISS_MAX, "<=", texels=inside))
    maps = {}
    for key, kind, space, samples, extra in (
            ("BaseColor", 'DIFFUSE', 'sRGB', 4, {"pass_filter": {'COLOR'}}),
            ("Normal", 'NORMAL', 'Non-Color', 4, {"normal_space": 'TANGENT'}),
            ("Occlusion", 'AO', 'Non-Color', a.ao_samples, {})):
        img = bpy.data.images.new(f"{name}_{key}", px, px, alpha=False)
        img.colorspace_settings.name = space
        if kind == 'DIFFUSE':
            with NoMetal(show):
                bake_secs[key] = bake(show, game, kind, img, a.margin_px, samples, **extra)
        else:
            bake_secs[key] = bake(show, game, kind, img, a.margin_px, samples, **extra)
        path = os.path.join(out, "textures", f"{name}_{key}.png")
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
        maps[key] = img
    game.data.materials.clear()
    bpy.data.materials.remove(tmp_mat)
    game.data.materials.append(game_material(f"{name}_game", maps["BaseColor"], maps["Normal"], maps["Occlusion"]))
    info["bake"] = {"cage_extrusion": r4(a.cage * H), "max_ray_distance": r4(a.ray * H), "margin_px": a.margin_px,
                    "ao_samples": a.ao_samples, "seconds": {k: round(v, 1) for k, v in bake_secs.items()}}
    secs["bake"] = round(time.time() - t0, 1)

    # 5 the same cameras: silhouettes, colour, the approval sheet
    t0 = time.time()
    mat_s, node_s = base_colour_node(show)
    if node_s is not None:
        mat_s.node_tree.nodes.active = node_s
    views = Views(show, VIEW_PX)
    per_view, de_sum, de_n, tex = {}, 0.0, 0, {}
    try:
        for az in AZIMUTHS:
            fs = views.shoot(show, [game], az, "texture")
            fg = views.shoot(game, [show], az, "texture")
            i, s, n = view_compare(fs, fg)
            per_view[str(az)] = {"iou": r4(i), "delta_e": r4(s / n) if n else None}
            de_sum, de_n = de_sum + s, de_n + n
            if az in SHEET_AZ:
                tex[az] = (fs, fg)
        rows = [[tex[az][0] for az in SHEET_AZ], [tex[az][1] for az in SHEET_AZ],
                [views.shoot(show, [game], az, "clay") for az in SHEET_AZ],
                [views.shoot(game, [show], az, "clay") for az in SHEET_AZ]]
        sheet = os.path.join(out, f"{name}_game_vs_showcase.png")
        save_sheet(rows, sheet)
    finally:
        views.close()
    worst = min(per_view, key=lambda k: per_view[k]["iou"])
    gates.append(gate("game.silhouette_iou_min", per_view[worst]["iou"], IOU_MIN, ">=", view=int(worst)))
    gates.append(gate("game.bake_delta", r4(de_sum / de_n) if de_n else None, BAKE_DELTA_MAX, "<="))
    info["views"] = per_view
    secs["views"] = round(time.time() - t0, 1)

    # 6 write, then mesh_check on the written GLB
    t0 = time.time()
    bpy.data.objects.remove(show, do_unlink=True)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)   # the showcase's maps
    game.data.name = game.name
    glb = os.path.join(out, f"{name}_game.glb")
    only(game, active=game)
    bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', use_selection=True, export_apply=True,
                              export_yup=True)
    blend = os.path.join(out, f"{name}_game.blend")
    map_paths = {k: img.filepath_raw for k, img in maps.items()}
    for img in maps.values():
        img.filepath = img.filepath_raw
    bpy.ops.wm.save_as_mainfile(filepath=blend, relative_remap=True, compress=True)
    mc_path = os.path.join(out, "mesh_check.json")
    mc, why = run_mesh_check(glb, a.body, mc_path)
    if mc is None:
        gates.append({"name": "game.mesh_check", "value": None, "limit": "mesh_check.py passes", "pass": False,
                      "why": why})
    else:
        failed = [g.get("name") for g in mc.get("gates", []) if not g.get("pass")]
        gates.append({"name": "game.mesh_check", "value": failed or "pass", "limit": "mesh_check.py passes",
                      "pass": bool(mc.get("pass")), "body": a.body,
                      "gates": {g.get("name"): {"value": g.get("value"), "pass": g.get("pass")}
                                for g in mc.get("gates", [])},
                      "inner_shell": (mc.get("double_shell") or {}).get("inner_shell")})
    secs["write_check"] = round(time.time() - t0, 1)
    secs["total"] = round(time.time() - t_all, 1)
    info["outputs"] = {"glb": glb, "blend": blend, "sheet": sheet, "mesh_check": mc_path, "bake_miss": miss_png,
                       "maps": map_paths}
    doc = report_doc(gates, **info, seconds=secs)
    return (0 if doc["pass"] else 2), doc


def write_report(out, doc):
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "game_mesh.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1, default=str)
    return path


# ---------------------------------------------------------------------------------------- selftests
def contract_sample(script, case, doc):
    """One selftest report for tools/check-contracts.py, named on stdout as `selftest-output: <path>`."""
    out = os.environ.get("UNITY_DEV_CONTRACT_OUT") or os.path.join(tempfile.gettempdir(), "unity-dev-contract-out")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{script}__{case}.gate.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1, default=str)
    print(f"selftest-output: {path}")


def selftest():
    """The gate maths on synthetic data: no Blender."""
    np = _np()
    failed = []

    def ok(name, cond, value=None):
        print(("PASS " if cond else "FAIL ") + name + ("" if value is None else f"  {value}"))
        if not cond:
            failed.append(name)

    # a 4 x 4 grid of quads in the unit square, two triangles each
    g = np.linspace(0, 1, 5)
    X, Y = np.meshgrid(g, g)
    V2 = np.c_[X.ravel(), Y.ravel()]
    F = []
    for r in range(4):
        for c in range(4):
            i = r * 5 + c
            F += [[i, i + 1, i + 6], [i, i + 6, i + 5]]
    F = np.array(F)
    V3 = np.c_[V2, np.zeros(len(V2))]
    uv = 0.05 + 0.9 * V2
    ov, cov = uv_overlap(uv, F, 256)
    ok("uv_overlap: a grid sharing every edge reads 0", ov == 0.0 and cov > 0, (ov, cov))
    F2 = np.r_[F, F[:4]]                               # four triangles laid twice
    ov2, _ = uv_overlap(uv, F2, 256)
    ok("uv_overlap: four triangles laid twice read their share (2/16 of the cover)", abs(ov2 - 4 / 32) < 0.01, r4(ov2))
    mirrored = uv.copy()
    mirrored[:, 0] = 1 - mirrored[:, 0]
    ok("uv_overlap: a mirrored (clockwise) layout reads 0 too", uv_overlap(mirrored, F, 256)[0] == 0.0)
    ok("uv_bounds: inside reads 0, two corners pushed out read 2",
       uv_bounds(uv) == 0 and uv_bounds(np.r_[uv, [[1.2, 0.5], [-0.1, 0.5]]]) == 2)

    s, an = uv_stretch(V3, uv, F)
    ok("uv_stretch: a uniform scale reads 1", abs(s - 1) < 1e-6 and abs(an - 1) < 1e-6, (r4(s), r4(an)))
    squash = uv.copy()
    squash[:, 0] *= 1 / 3
    s, an = uv_stretch(V3, squash, F)
    ok("uv_stretch: x squashed 3x reads sqrt(3) (density-normalised) and anisotropy 3",
       abs(s - math.sqrt(3)) < 1e-6 and abs(an - 3) < 1e-6, (r4(s), r4(an)))
    bent = uv.copy()
    bent[12, 0] += 0.2                                  # one interior vertex dragged: local shear
    s_b, _ = uv_stretch(V3, bent, F)
    ok("uv_stretch: a dragged vertex raises the p95 above 1.2", s_b > 1.2, r4(s_b))
    flat = uv.copy()
    flat[:, 1] = 0.5                                   # every triangle collapsed to a line
    s_f, _ = uv_stretch(V3, flat, F)
    ok("uv_stretch: a collapsed UV layout is refused (None)", s_f is None)

    a = np.zeros((40, 40), bool)
    a[10:30, 10:30] = True
    b = np.zeros_like(a)
    b[10:30, 15:35] = True
    ok("iou: two 20 px squares offset 5 px read 300/500", abs(iou(a, b) - 0.6) < 1e-9, r4(iou(a, b)))

    fa = np.zeros((40, 40, 4))
    fa[10:30, 10:30] = [0.5, 0.5, 0.5, 1]
    fb = fa.copy()
    i, s, n = view_compare(fa, fb)
    ok("view_compare: the same frame reads IoU 1 and delta E 0", i == 1.0 and s == 0.0 and n > 0)
    fb[..., :3] = np.where(fb[..., 3:] > 0, [0.6, 0.5, 0.5], 0)
    i, s, n = view_compare(fa, fb)
    de = float(np.linalg.norm(srgb_to_lab([0.5, 0.5, 0.5]) - srgb_to_lab([0.6, 0.5, 0.5])))
    ok("view_compare: a red shift reads its CIE76 delta E, compared 2 px in", abs(s / n - de) < 1e-6 and n == 16 * 16,
       (r4(s / n), n))

    alpha = np.ones((256, 256))
    m, inside, _ = bake_miss(uv, F, alpha, 256)
    ok("bake_miss: every texel hit reads 0", m == 0.0 and inside > 0)
    alpha[100:120, 100:120] = 0
    m, inside, missed = bake_miss(uv, F, alpha, 256)
    ok("bake_miss: a 20 x 20 hole reads its share", abs(m - 400 / inside) < 1e-9 and missed.sum() == 400, r4(m))

    ok("gate: a range reads its margin", gate("game.tris", 7600, [4000, 8000], "range")["margin"] == 0.2)
    gs = [gate("game.tris", 7600, [4000, 8000], "range"), gate("game.uv_overlap", 0.0, UV_OVERLAP_MAX, "<="),
          gate("game.silhouette_iou_min", 0.97, IOU_MIN, ">=")]
    doc = report_doc(gs, name="synthetic")
    ok("report: gate/1, pass, green, no ok key, margins numeric",
       doc["schema"] == "gate/1" and doc["pass"] and doc["verdict"] == "green" and "ok" not in doc
       and all(isinstance(g.get("margin"), float) for g in gs))
    contract_sample("game_mesh", "maths", doc)
    bad = report_doc([gate("game.bake_delta", 9.0, BAKE_DELTA_MAX, "<=")])
    ok("report: a failing gate fails the report, margin negative",
       not bad["pass"] and bad["verdict"] == "failed" and bad["gates"][0]["margin"] < 0)
    if os.path.isfile(MESH_CHECK):
        with tempfile.TemporaryDirectory() as td:
            junk, stale = os.path.join(td, "junk.glb"), os.path.join(td, "mesh_check.json")
            with open(junk, "wb") as handle:
                handle.write(b"not a mesh")
            with open(stale, "w", encoding="utf-8") as handle:
                json.dump({"schema": "gate/1", "pass": True, "gates": []}, handle)
            mc, why = run_mesh_check(junk, "human", stale)
            ok("mesh_check: a refused mesh is no pass, a stale passing report beside it is not read",
               mc is None and why is not None and not os.path.exists(stale), why)
    else:
        print("SKIP mesh_check: character-autorig is not installed beside this skill")
    print(json.dumps({"selftest": "pass" if not failed else "fail", "failed": failed}))
    return 0 if not failed else 2


def _figure(path, inner_shell=True):
    """A synthetic showcase: a stick figure in an A-pose (torso, head, legs, arms) with an image texture,
    and an inward-facing inner shell 1.5 mm inside it, as an image-to-3D generator writes one."""
    import bpy
    import bmesh
    np = _np()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    parts = []

    def cyl(r, a, b):
        from mathutils import Vector
        a, b = Vector(a), Vector(b)
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=r, depth=(b - a).length, location=(a + b) / 2)
        o = bpy.context.object
        o.rotation_mode = 'QUATERNION'
        o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference((b - a).normalized())
        parts.append(o)

    cyl(0.16, (0, 0, 0.78), (0, 0, 1.32))                         # torso
    for s in (-1, 1):
        cyl(0.07, (0.1 * s, 0, 0.0), (0.1 * s, 0, 0.84))          # legs
        cyl(0.05, (0.2 * s, 0, 1.26), (0.2 * s + 0.36 * s, 0, 0.84))  # arms, about 40 deg out
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.14, location=(0, 0, 1.46), segments=24, ring_count=12)
    parts.append(bpy.context.object)
    only(*parts, active=parts[0])
    bpy.ops.object.join()
    fig = bpy.context.object
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    fig.data.remesh_voxel_size = 0.012
    bpy.ops.object.voxel_remesh()
    fig.name = "Figure"
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.01)
    bpy.ops.object.mode_set(mode='OBJECT')
    side = 256
    yy, xx = np.mgrid[0:side, 0:side] / side
    rgb = np.stack([0.25 + 0.6 * (np.sin(xx * 25) > 0), 0.3 + 0.5 * yy, 0.5 + 0.4 * (np.cos(yy * 19) > 0)], -1)
    pix = np.concatenate([rgb, np.ones((side, side, 1))], -1).astype(np.float32)
    img = bpy.data.images.new("FigureTex", side, side, alpha=False)
    img.pixels.foreach_set(pix.reshape(-1))
    img.pack()
    mat = bpy.data.materials.new("Figure")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    fig.data.materials.append(mat)
    if inner_shell:
        bm = bmesh.new()
        bm.from_mesh(fig.data)
        bm.normal_update()
        dup = bmesh.ops.duplicate(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:])
        verts = [g for g in dup["geom"] if isinstance(g, bmesh.types.BMVert)]
        faces = [g for g in dup["geom"] if isinstance(g, bmesh.types.BMFace)]
        for v in verts:
            v.co -= v.normal * 0.0015
        bmesh.ops.reverse_faces(bm, faces=faces)
        bm.to_mesh(fig.data)
        bm.free()
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=False)


def _stub(path, body):
    with open(path, "w") as handle:
        handle.write("#!/bin/sh\n" + body + "\n")
    os.chmod(path, 0o755)
    return path


def selftest_blender():
    """The whole route on a synthetic figure, a planted bake fault, and AutoRemesher's three failures."""
    failed = []

    def ok(name, cond, value=None):
        print(("PASS " if cond else "FAIL ") + name + ("" if value is None else f"  {value}"))
        if not cond:
            failed.append(name)

    tmp = tempfile.mkdtemp(prefix="game_mesh_selftest_")
    try:
        src = os.path.join(tmp, "figure.glb")
        _figure(src)

        def args(out, *extra):
            return parser().parse_args([src, "--out", os.path.join(tmp, out), "--target-tris", "3000",
                                        "--tex-px", "256", "--ao-samples", "4", "--voxel", "0.006", *extra])

        code, doc = run(args("base"))
        write_report(os.path.join(tmp, "base"), doc)
        g = {x["name"]: x for x in doc["gates"]}
        ok("figure: every gate passes, exit 0", code == 0 and doc["pass"],
           {k: (v.get("value"), v["pass"]) for k, v in g.items()})
        ok("figure: QuadriFlow, inside the budget", doc["retopo"].get("tool") == "quadriflow"
           and g["game.tris"]["pass"], doc["game"]["tris"] if "game" in doc else None)
        ok("figure: the inner shell is gone (one piece, mesh_check inner_shell < 0.05)",
           g["game.one_surface"]["value"] == 1 and (g["game.mesh_check"].get("inner_shell") or 0) < 0.05,
           g["game.mesh_check"].get("inner_shell"))
        outs = doc.get("outputs", {})
        ok("figure: GLB, blend, three maps and the sheet written",
           all(os.path.isfile(p) for p in [outs.get("glb", ""), outs.get("blend", ""), outs.get("sheet", "")]
               + list(outs.get("maps", {}).values())) and len(outs.get("maps", {})) == 3)
        ok("figure: every numeric gate carries a margin",
           all("margin" in x for x in doc["gates"] if isinstance(x.get("value"), (int, float))))
        contract_sample("game_mesh", "figure", doc)

        import bpy
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, segments=48, ring_count=24)
        shell = bpy.context.object
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.49, segments=48, ring_count=24)
        inner = bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.flip_normals()
        bpy.ops.object.mode_set(mode='OBJECT')
        only(shell, inner, active=shell)
        bpy.ops.object.join()
        hollow = solid_ratio(shell, 1.0)
        cells = fill_cavity(shell, 0.005)
        shell.data.remesh_voxel_size = 0.005
        only(shell, active=shell)
        bpy.ops.object.voxel_remesh()
        filled = solid_ratio(shell, 1.0)
        ok("game.solid: a 1 cm hollow ball reads its wall's share; fill_cavity makes it solid",
           hollow is not None and hollow < 0.2 and cells > 0 and filled > SOLID_MIN, (r4(hollow), r4(filled)))

        code, doc = run(args("missed", "--cage", "0.0001", "--ray", "0.0002"))
        g = {x["name"]: x for x in doc["gates"]}
        ok("planted: a cage and ray too short to reach the showcase fail bake_miss and bake_delta, exit 2",
           code == 2 and not g["game.bake_miss"]["pass"] and not g["game.bake_delta"]["pass"],
           (g["game.bake_miss"]["value"], g["game.bake_delta"]["value"]))

        if os.name == "posix":
            for case, body, want in (
                    ("hang", "sleep 30", "timeout"),
                    ("crash", "echo 'segfault at load' >&2; exit 3", "exit 3"),
                    ("silent", "exit 0", "no output"),
                    ("dense", 'while [ $# -gt 0 ]; do case "$1" in --input) i=$2;; --output) o=$2;; esac; shift; done; '
                              'cp "$i" "$o"', "over the budget")):
                exe = _stub(os.path.join(tmp, f"stub_{case}"), body)
                code, doc = run(args(f"ar_{case}", "--autoremesher", exe, "--timeout", "3"), stop_after_retopo=True)
                rt = doc.get("retopo", {})
                ok(f"AutoRemesher {case}: falls back to QuadriFlow and says why ({want})",
                   code == 0 and rt.get("tool") == "quadriflow" and want in (rt.get("fallback") or ""),
                   rt.get("fallback"))
        else:
            print("SKIP AutoRemesher stubs: POSIX shell scripts")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"selftest": "pass" if not failed else "fail", "failed": failed}))
    return 0 if not failed else 2


# ---------------------------------------------------------------------------------------------- main
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    a = parser().parse_args(argv)
    problem = check_args(a)
    if problem:
        parser().error(problem)
    if a.selftest:
        sys.exit(selftest())
    try:
        import bpy  # noqa: F401
    except ImportError:
        blender = find_blender(a.blender)
        if not blender:
            print(json.dumps(report_doc([], refused="no Blender: pass --blender PATH or set BLENDER")))
            sys.exit(1)
        cmd = [blender, "-b", "--factory-startup", "--python-exit-code", "1", "-P", os.path.abspath(__file__),
               "--", *argv]
        sys.exit(subprocess.run(cmd).returncode)
    if a.selftest_blender:
        sys.exit(selftest_blender())
    try:
        code, doc = run(a)
    except Refused as exc:
        code, doc = 1, report_doc([], refused=str(exc))
    except Exception as exc:              # Blender -b exits 0 on an uncaught error: make it a failure
        import traceback
        traceback.print_exc()
        code, doc = 1, report_doc([], error=f"{type(exc).__name__}: {exc}")
    path = write_report(os.path.abspath(a.out), doc)
    print(json.dumps({k: doc[k] for k in ("schema", "tool", "pass", "verdict", "gates") if k in doc}, indent=1,
                     default=str))
    print(f"report: {path}")
    sys.stdout.flush()
    sys.exit(code)


if __name__ == "__main__":
    main()
