#!/usr/bin/env python3
"""eye_fit.py — eyeballs for a generated head: a sphere fitted into each painted eye, the painted eye cut out, bound to the eye bones.

An image-to-3D head has its eyes in the paint, on a nearly flat surface. `fit` puts a real eyeball
behind each painted eye opening of the assembled head (assemble_parts.py's output), removes the painted
eye surface in front of it and writes the eyeballs as their own objects; `bind`, after the rig, binds
each eyeball rigidly to its eye bone and re-exports the FBX. The geometry is numpy only (it would run
inside Blender); `fit` runs on the host with numpy and Pillow (the head's texture is decoded and the eye
textures encoded with Pillow) and edits the GLBs without a round trip through an importer.

usage:
    python3 eye_fit.py fit ASSEMBLY_DIR [--name c] [--head-material c_head] [--radius-frac 0.55]
                       [--report PATH] [--no-render]
    blender -b -P eye_fit.py -- bind OUT --eyes OUT/NAME_eyes.glb --rig-glb OUT/NAME.glb [--name NAME]
                       [--turn 25] [--report PATH]   (no --factory-startup: the FBX export needs Auto-Rig Pro)
    python3 eye_fit.py --selftest

fit, per eye, in the head's own frame (+Y up, facing +Z, the assembly's GLB frame):
  render     an orthographic front view of the head primitive (the faces of material --head-material in
             <c>_rig.glb), head width / 1300 per pixel: per pixel the face, its 3D point and its texel.
  find       sclera pixels (light and not warm: R - B < 55 and lum > 120 of 255, on faces turned to the
             camera) in the band 0.2..0.8 of the head's height from the top, grouped per side of the head's
             centre line (pieces split by the iris, gaps up to 0.12 x head width); the eyes are the pair
             of groups mirrored about the centre line (no group touching it: a mouth or teeth do), each
             0.05..0.30 x head width wide. The opening is the convex hull of the sclera and the iris (the
             largest dark blob, lum < 115, next to the sclera, opened with a disk of 0.1 x lid width so
             lash lines and lid shadow drop out).
  sphere     radius = --radius-frac x the lid-corner width (0.55, Auto-Rig Pro's proxy rule); axis = the
             mean normal of the faces seen in the opening; the front on the opening's most forward point,
             then pushed back by the 99th-percentile intrusion of a skin ring around the opening
             (0.012..0.08 x lid width outside it) plus 0.02 x radius, so the lids never cut into the ball.
  hollow     removed: the faces seen in the opening whose centroid lies inside it, and the faces no view
             of the front sees (an inner shell) within 0.98 x radius of the centre. Nothing else: every
             face under the mask, or every face inside the ball, opens holes to the inner shell.
  texture    a planar map along the eye axis (512 px; an equirect pole would blur the iris away): the
             painted opening (eroded 0.017 x lid width) projected onto the ball, the median sclera
             elsewhere; the back half repeats it, hidden in the socket.
Gates (gate/1, provisional, from one character): eye.found (both eyes), eye.symmetry (centre heights
within 0.5 x radius, radii within 15 %), eye.poke (ring intrusion <= 0.02 x radius), eye.rim_gap
(p90 of lid edge off the ball <= 0.25 x radius), eye.removed (faces removed per eye 1..3 % of the head's),
eye.in_opening (front view, the ball is the surface seen on >= 0.90 of the eroded opening).
Outputs in ASSEMBLY_DIR, only when every gate passes: <c>_eyes.glb (Eye.L, Eye.R: their own meshes,
materials and textures; node extras eye, centre, radius, axis), <c>_rig.glb and <c>_parts.glb with the
head's eye faces removed (the files assemble wrote are kept as <c>_rig.pre_eyes.glb and
<c>_parts.pre_eyes.glb; a second fit starts from them, an assemble after it replaces them; the edited
files carry asset.extras.eye_fit), <c>.eyes.gate.json, and unless --no-render eyes.png (front and 3/4,
painted and with eyeballs). <c>_parts.blend is not edited.

bind (after autorig, like assemble_parts.py bind for the hair): opens OUT/rig/<NAME>_arp.blend (backed up
once to rig/<NAME>_arp.pre_eyes.blend), imports the eyeballs, recovers the rig stage's import transform
from <NAME>.glb (scale from the z extents, shift from the minima), binds each eyeball with weight 1.0 to
the contract's Eye.L / Eye.R bone (rig/<NAME>.contract.json retarget_map; Auto-Rig Pro's c_eye.l/.r when
the face was built), else to Head (no eye bones: `degraded`, a warning, no failure), marks it parts_eye.
The skin's weights on an eye bone move to its parent (only the ball turns with the gaze), and the eye
bones with every bone pivoting at them (lids, the eye target) move onto the balls' centres (the face
rig is mirrored, a generated head is not); then the FBX is exported again with blender-retarget
brt_arp op export. An eye an earlier bind left is replaced.
Gates: eyes.transform_residual (<= 1e-5 x height), eyes.bound (every vertex one group, weight 1),
eyes.skin_off_eye_bone (no other mesh weighted to an eye bone), eyes.follows_bone (each eye bone turned
--turn degrees left, right, up and down as Unity turns LeftEye/RightEye, its own constraints and the
lids' follow of it muted meanwhile: the bone turned by the angle within 0.5 deg, and the evaluated
eyeball is its rigid motion of the rest one, <= 1e-5 x height), eyes.poke_turned (what the turns add
to the cut of the skin within 1.6 x radius into the ball <= 0.02 x radius). Reported: pivot_offset and
pivot_offset_after (eye bone head to the ball's centre, x radius), poke_rest, and the cut added with
the lids following (Blender's own face rig).
autorig.py all OUT <c>_rig.glb --eyes <c>_eyes.glb runs it as its eyes_bind step, after the contract (and
parts_bind) and before deform; with --facial the smart stage hands the eyeballs to Auto-Rig Pro's face
detection (arp_smart.py --eyes objects).

Exit codes: 0 every gate passed (or --selftest passed); 2 a gate failed; 1 usage error, refused input or
a failed --selftest. Arguments are parsed before numpy, Pillow or bpy is imported.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

GATES = {"poke": 0.02, "rim_gap": 0.25, "removed_max": 0.03, "in_opening": 0.98, "dy": 0.5, "radius_ratio": 1.15,
         "follow_deg": 0.5}
SCLERA_RB, SCLERA_LUM, DARK_LUM = 55, 120, 115     # of 255, sRGB
BAND = (0.2, 0.8)          # of the head's height, from the top
GROUP_GAP = 0.12           # x head width: sclera pieces split by the iris
EYE_WIDTH = (0.05, 0.30)   # x head width
CENTRE_CLEAR = 0.02        # x head width: no eye group reaches the centre line
PX_ACROSS = 1300           # pixels across the head's width
TEX = 512
MARK = "eye_fit"


class Refused(Exception):
    """Input this tool will not take (exit 1)."""


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser():
    p = UsageParser(prog="eye_fit.py", description=__doc__.split("\n")[0],
                    epilog="Exit codes: 0 pass, 2 a gate failed, 1 usage error or refused input.")
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd", parser_class=UsageParser)
    f = sub.add_parser("fit")
    f.add_argument("assembly_dir")
    f.add_argument("--name", help="the character (<c> of <c>_rig.glb); default: the one *_rig.glb there")
    f.add_argument("--head-material", help="the head primitive's material (default <c>_head)")
    f.add_argument("--radius-frac", type=float, default=0.55, help="eyeball radius / lid-corner width")
    f.add_argument("--report", help="also write the gate/1 report here")
    f.add_argument("--no-render", action="store_true")
    b = sub.add_parser("bind")
    b.add_argument("autorig_out")
    b.add_argument("--eyes", required=True)
    b.add_argument("--rig-glb", required=True)
    b.add_argument("--name")
    b.add_argument("--turn", type=float, default=25.0, help="degrees the eye bones are turned for the gates")
    b.add_argument("--report", help="also write the gate/1 report here")
    return p


def _np():
    import numpy as np
    return np


def gate(name, value, limit, passed, **extra):
    return {"name": name, "value": value, "limit": limit, "pass": bool(passed), **extra}


def r4(x):
    return None if x is None else round(float(x), 4)


# ------------------------------------------------------------------------------------ image basics
def erode(m, r):
    import part_math as pm
    return ~pm.dilate(~m, r) if r > 0 else m.copy()


def opening(m, r):
    import part_math as pm
    return pm.dilate(erode(m, r), r) if r > 0 else m.copy()


def label(m):
    """(labels int32, count): 8-connected components of a boolean image, by runs and union-find."""
    np = _np()
    h, w = m.shape
    runs, rows = [], []
    for y in range(h):
        row = m[y]
        if not row.any():
            rows.append((len(runs), len(runs)))
            continue
        d = np.diff(np.r_[0, row.astype(np.int8), 0])
        s, e = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
        start = len(runs)
        runs += [(y, int(a), int(b)) for a, b in zip(s, e)]
        rows.append((start, len(runs)))
    parent = list(range(len(runs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for y in range(1, h):
        a0, a1 = rows[y - 1]
        b0, b1 = rows[y]
        i = a0
        for j in range(b0, b1):
            _, s, e = runs[j]
            while i < a1 and runs[i][2] < s:      # previous-row run ends left of this one (8-connected: e >= s)
                i += 1
            k = i
            while k < a1 and runs[k][1] <= e:
                ra, rb = find(k), find(j)
                if ra != rb:
                    parent[rb] = ra
                k += 1
    lab = np.zeros((h, w), np.int32)
    ids = {}
    for j, (y, s, e) in enumerate(runs):
        lab[y, s:e] = ids.setdefault(find(j), len(ids) + 1)
    return lab, len(ids)


def convex_fill(pts, shape):
    """Boolean image of the convex hull of pixel points (k, 2) as (x, y)."""
    np = _np()
    h, w = shape
    P = sorted(set(map(tuple, np.asarray(pts, np.int64).tolist())))
    out = np.zeros((h, w), bool)
    if len(P) < 3:
        for x, y in P:
            out[y, x] = True
        return out

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for q in P:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    for q in reversed(P):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    hull = np.array(lower[:-1] + upper[:-1], float)
    x0, y0 = hull.min(0).astype(int)
    x1, y1 = hull.max(0).astype(int)
    gy, gx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
    inside = np.ones(gx.shape, bool)
    for a, b in zip(hull, np.roll(hull, -1, axis=0)):     # counter-clockwise in (x, y): left of every edge
        inside &= (b[0] - a[0]) * (gy - a[1]) - (b[1] - a[1]) * (gx - a[0]) >= -1e-9
    out[y0:y1 + 1, x0:x1 + 1] = inside
    return out


def lum(col8):
    return col8.astype(float).mean(2)


# ------------------------------------------------------------------------------------------ render
def render(V, F, UV, tex, box, upp):
    """Orthographic front render (+Z toward the camera) of a textured triangle mesh. box = (x0, x1, y0, y1);
    tex (h, w, 3) floats 0..1, rows top-down (glTF v). Returns fid (-1 background), pts (3D, nan), col,
    frame (units_per_px, cx, cy) and size (w, h)."""
    np = _np()
    import part_math as pm
    x0, x1, y0, y1 = box
    w, h = int(math.ceil((x1 - x0) / upp)), int(math.ceil((y1 - y0) / upp))
    frame = (upp, -x0 / upp, y1 / upp)
    fid = pm.label_raster(V, F, np.arange(1, len(F) + 1), "front", (w, h), frame) - 1
    ys, xs = np.nonzero(fid >= 0)
    f = fid[ys, xs]
    P = np.c_[frame[1] + V[:, 0] / upp, frame[2] - V[:, 1] / upp]
    a, b, c = P[F[f, 0]], P[F[f, 1]], P[F[f, 2]]
    q = np.c_[xs + 0.5, ys + 0.5]
    v0, v1, v2 = b - a, c - a, q - a
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    den = np.where(np.abs(den) < 1e-12, 1e-12, den)
    bv, bw = (d11 * d20 - d01 * d21) / den, (d00 * d21 - d01 * d20) / den
    B = np.clip(np.c_[1 - bv - bw, bv, bw], 0, 1)
    B /= np.maximum(B.sum(1, keepdims=True), 1e-12)
    pts = np.full((h, w, 3), np.nan)
    pts[ys, xs] = (V[F[f]] * B[:, :, None]).sum(1)
    col = np.zeros((h, w, 3))
    if tex is not None and len(f):
        T = (UV[F[f]] * B[:, :, None]).sum(1)
        th, tw = tex.shape[:2]
        px = np.clip((np.mod(T[:, 0], 1) * tw).astype(int), 0, tw - 1)
        py = np.clip((np.mod(T[:, 1], 1) * th).astype(int), 0, th - 1)
        col[ys, xs] = tex[py, px, :3]
    return {"fid": fid, "pts": pts, "col": col, "frame": frame, "size": (w, h)}


# --------------------------------------------------------------------------------------------- find
def find_eyes(r, V, F, head_box):
    """The two eye openings in a front render: {side: {mask, sclera, iris, lid_px}} and the pair's
    detail, or (None, why)."""
    np = _np()
    import part_math as pm
    col8 = np.clip(r["col"] * 255, 0, 255).astype(np.uint8)
    h, w = r["fid"].shape
    upp, cx, cy = r["frame"]
    x0, x1, y0, y1 = head_box
    W = (x1 - x0) / upp
    fn, _ = pm.face_normals(V, F)
    nz = np.full((h, w), -1.0)
    on = r["fid"] >= 0
    nz[on] = fn[r["fid"][on], 2]
    rows = np.arange(h)
    band = (rows >= BAND[0] * h) & (rows <= BAND[1] * h)
    c8 = col8.astype(int)
    sclera = on & (nz > 0.2) & band[:, None] & (c8[..., 0] - c8[..., 2] < SCLERA_RB) & (lum(col8) > SCLERA_LUM)
    sclera = opening(sclera, 1)
    xs_on = np.nonzero(on[band].any(0))[0]
    if not len(xs_on):
        return None, "the head is not in the front view"
    mid = np.array([np.median(np.nonzero(on[y])[0]) for y in np.nonzero(band)[0] if on[y].any()])
    centre = float(np.median(mid))
    lab, n = label(sclera)
    if n == 0:
        return None, "no sclera pixels in the eye band"
    comps = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if len(xs) < max(12, (0.005 * W) ** 2):
            continue
        comps.append({"ids": [i], "x0": xs.min(), "x1": xs.max(), "y0": ys.min(), "y1": ys.max(), "n": len(xs)})
    gap = GROUP_GAP * W
    groups = {"R": [], "L": []}            # R: the character's right, x < centre (image left in the front view)
    for c in sorted(comps, key=lambda c: -c["n"]):
        side = "R" if (c["x0"] + c["x1"]) / 2 < centre else "L"
        for g in groups[side]:
            dx = max(0, max(g["x0"], c["x0"]) - min(g["x1"], c["x1"]))
            dy = max(0, max(g["y0"], c["y0"]) - min(g["y1"], c["y1"]))
            if dx <= gap and dy <= 0.5 * gap:
                g["ids"] += c["ids"]
                g.update(x0=min(g["x0"], c["x0"]), x1=max(g["x1"], c["x1"]), y0=min(g["y0"], c["y0"]),
                         y1=max(g["y1"], c["y1"]), n=g["n"] + c["n"])
                break
        else:
            groups[side].append(dict(c))
    clear = CENTRE_CLEAR * W
    ok = lambda g: (EYE_WIDTH[0] * W <= g["x1"] - g["x0"] <= EYE_WIDTH[1] * W
                    and (g["x1"] < centre - clear or g["x0"] > centre + clear))
    best = None
    for gr in filter(ok, groups["R"]):
        for gl in filter(ok, groups["L"]):
            mr, ml = (gr["x0"] + gr["x1"]) / 2, (gl["x0"] + gl["x1"]) / 2
            yr, yl = (gr["y0"] + gr["y1"]) / 2, (gl["y0"] + gl["y1"]) / 2
            wr, wl = gr["x1"] - gr["x0"], gl["x1"] - gl["x0"]
            mirror = abs((mr + ml) / 2 - centre) / max(wr, wl)
            dy = abs(yr - yl) / max(wr, wl)
            size = abs(math.log(max(wr, 1) / max(wl, 1)))
            if mirror > 0.5 or dy > 0.5 or size > 0.5:
                continue
            score = mirror + dy + size
            if best is None or score < best[0]:
                best = (score, gr, gl, mirror, dy)
    if best is None:
        return None, f"no mirrored pair of sclera groups ({len(groups['R'])} right, {len(groups['L'])} left)"
    _, gr, gl, mirror, dy = best
    out = {"centre_px": centre, "mirror": r4(mirror), "dy": r4(dy)}
    for side, g in (("R", gr), ("L", gl)):
        m = np.isin(lab, g["ids"])
        lid = float(g["x1"] - g["x0"] + 1)
        ys, xs = np.nonzero(m)
        hull = convex_fill(np.c_[xs, ys], (h, w))
        near = pm.dilate(hull, max(2, int(round(0.11 * lid))))
        dark = near & on & (lum(col8) < DARK_LUM)
        half = np.zeros((h, w), bool)
        if side == "R":
            half[:, :int(centre)] = True
        else:
            half[:, int(centre) + 1:] = True
        dark = opening(dark & half, max(1, int(round(0.10 * lid))))
        dl, dn = label(dark)
        iris = np.zeros((h, w), bool)
        if dn:
            sizes = np.bincount(dl.ravel())[1:]
            iris = dl == 1 + int(np.argmax(sizes))
            if not (iris & hull).any() and not (pm.dilate(iris, 2) & hull).any():
                iris[:] = False
        ys, xs = np.nonzero(m | iris)
        mask = convex_fill(np.c_[xs, ys], (h, w)) & on
        out[side] = {"mask": mask, "sclera": m, "iris": iris, "lid_px": lid}
    return out, None


# ------------------------------------------------------------------------------------------- sphere
def uv_sphere(c, R, n, nu=48, nv=32):
    """(V, F, N, UV): a latitude-longitude sphere with its pole on the axis n, planar UV along n
    (u = 0.5 + 0.5 D.t, v = 0.5 - 0.5 D.b; t to +X, b up; glTF v runs down)."""
    np = _np()
    t, b = eye_frame(n)
    lon = np.linspace(0, 2 * np.pi, nu + 1)
    lat = np.linspace(0, np.pi, nv + 1)
    LO, LA = np.meshgrid(lon, lat)
    D = (np.cos(LA)[..., None] * n + np.sin(LA)[..., None] * (np.cos(LO)[..., None] * t + np.sin(LO)[..., None] * b))
    D = D.reshape(-1, 3)
    V = c + R * D
    UV = np.c_[0.5 + 0.5 * (D @ t), 0.5 - 0.5 * (D @ b)]
    F = []
    W = nu + 1
    for j in range(nv):
        for i in range(nu):
            a, b_, c_, d = j * W + i, j * W + i + 1, (j + 1) * W + i, (j + 1) * W + i + 1
            F += [[a, b_, c_], [b_, d, c_]]
    F = np.array(F, np.int64)
    # outward winding: flip if the first non-degenerate face points inward
    e = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    k = int(np.argmax(np.linalg.norm(e, axis=1)))
    if e[k] @ (V[F[k]].mean(0) - c) < 0:
        F = F[:, [0, 2, 1]]
    return V, F, D, UV


def eye_frame(n):
    np = _np()
    up = np.array([0.0, 1.0, 0.0])
    t = np.cross(up, n)
    if np.linalg.norm(t) < 1e-6:
        t = np.array([1.0, 0.0, 0.0])
    t /= np.linalg.norm(t)
    b = np.cross(n, t)
    return t, b / np.linalg.norm(b)


def fit_eyes(V, F, UV, tex, radius_frac=0.55, rim_fit=True, cover=True):
    """The numpy core. V, F, UV: the head primitive (glTF frame, +Y up, facing +Z); tex (h, w, 3) floats,
    rows top-down. Returns {ok, why, gates, eyes {side: {...}}, kill (bool per face), render, ...}."""
    np = _np()
    import part_math as pm
    lo, hi = V.min(0), V.max(0)
    Wd = float(hi[0] - lo[0])
    upp = Wd / PX_ACROSS
    pad = 0.02 * Wd
    box = (float(lo[0] - pad), float(hi[0] + pad), float(lo[1] - pad), float(hi[1] + pad))
    r = render(V, F, UV, tex, box, upp)
    found, why = find_eyes(r, V, F, (lo[0], hi[0], lo[1], hi[1]))
    res = {"render": r, "box": box, "upp": upp, "kill": np.zeros(len(F), bool), "eyes": {}, "why": why}
    if found is None:
        res["gates"] = [gate("eye.found", 0, 2, False, why=why)]
        res["ok"] = False
        return res
    fn, _ = pm.face_normals(V, F)
    cent = V[F].mean(1)
    upp_, cx, cy = r["frame"]
    h, w = r["fid"].shape
    visible = np.zeros(len(F), bool)
    vv = np.unique(r["fid"])
    visible[vv[vv >= 0]] = True
    qx = np.floor(cx + cent[:, 0] / upp_).astype(np.int64)
    qy = np.floor(cy - cent[:, 1] / upp_).astype(np.int64)
    okq = (qx >= 0) & (qy >= 0) & (qx < w) & (qy < h)
    col8 = np.clip(r["col"] * 255, 0, 255).astype(np.uint8)
    gates, eyes = [], {}
    kill = np.zeros(len(F), bool)
    for side in ("R", "L"):
        o = found[side]
        M, lid = o["mask"], o["lid_px"]
        pts = r["pts"]
        rim = M & ~erode(M, 1)
        ring = pm.dilate(M, max(3, int(round(0.08 * lid)))) & ~pm.dilate(M, max(1, int(round(0.012 * lid))))
        Pin, Prim, Pring = (pts[x] for x in (M, rim, ring))
        Pin, Prim, Pring = (p[np.isfinite(p).all(1)] for p in (Pin, Prim, Pring))
        fids = np.unique(r["fid"][M])
        fids = fids[fids >= 0]
        n = fn[fids].sum(0)
        n /= np.linalg.norm(n)
        width = float(Prim[:, 0].max() - Prim[:, 0].min())
        R = radius_frac * width
        mean = Pin.mean(0)
        front = mean + n * float(((Pin - mean) @ n).max())
        c = front - n * R
        if rim_fit:       # the lids rest on the ball: least squares |rim - c| = R, kept behind the rim
            c0 = c.copy()
            for _ in range(20):
                d = Prim - c
                L = np.linalg.norm(d, axis=1)
                J = -d / np.maximum(L, 1e-12)[:, None]
                step = np.linalg.lstsq(J, -(L - R), rcond=None)[0]
                c = c + step
                if np.linalg.norm(step) < 1e-7 * R:
                    break
            if (c - Prim.mean(0)) @ n > 0 or not np.isfinite(c).all():
                c = c0
        # pushed back along the axis until no ring point cuts into the ball by more than 0.9 x the gate
        cut = lambda x: float((R - np.linalg.norm(Pring - (c - x * n), axis=1)).max()) if len(Pring) else -1.0
        lo_, hi_ = 0.0, R
        if cut(0.0) > 0.9 * GATES["poke"] * R:
            for _ in range(30):
                mid_ = 0.5 * (lo_ + hi_)
                lo_, hi_ = (mid_, hi_) if cut(mid_) > 0.9 * GATES["poke"] * R else (lo_, mid_)
            push = hi_
        else:
            push = 0.0
        c = c - n * push
        gap = np.linalg.norm(Prim - c, axis=1) - R
        poke = max(0.0, float((R - np.linalg.norm(Pring - c, axis=1)).max())) / R if len(Pring) else 0.0
        inm = np.zeros(len(F), bool)
        inm[okq] = M[qy[okq], qx[okq]]
        seen = np.zeros(len(F), bool)
        seen[fids] = True
        k = inm & seen
        dv = V[F] - c
        disc = (np.linalg.norm(dv - (dv @ n)[..., None] * n, axis=2).max(1) < R) \
            & (np.linalg.norm(dv[..., :2], axis=2).max(1) < R)          # inside the ball's disc, axis and front
        if cover:         # only what the ball replaces: a face reaching past the ball's disc keeps its paint
            k &= disc
        # hidden faces (an inner shell, a lid's underside) inside the ball, or in front of it within its disc
        k |= ~visible & ((np.linalg.norm(cent - c, axis=1) < 0.98 * R) | (disc & ((cent - c) @ n > 0)))
        kill |= k
        Ve, Fe, Ne, UVe = uv_sphere(c, R, n)
        etex = eye_texture(c, R, n, r, M, col8, o["sclera"], lid)
        eyes[side] = {"V": Ve, "F": Fe, "N": Ne, "UV": UVe, "tex": etex, "centre": c, "radius": R, "axis": n,
                      "lid_width": width, "pushed_back": push, "rim_gap_mean": float(gap.mean() / R),
                      "rim_gap_p90": float(np.percentile(gap, 90) / R), "poke": poke, "removed": int(k.sum()),
                      "removed_visible": int((k & visible).sum()), "removed_hidden": int((k & ~visible).sum()),
                      "opening_px": int(M.sum()), "mask": M}
    nf = len(F)
    eR, eL = eyes["R"], eyes["L"]
    dy = abs(eR["centre"][1] - eL["centre"][1]) / max(eR["radius"], eL["radius"])
    ratio = max(eR["radius"], eL["radius"]) / min(eR["radius"], eL["radius"])
    gates.append(gate("eye.found", 2, 2, True))
    gates.append(gate("eye.symmetry", {"dy_over_R": r4(dy), "radius_ratio": r4(ratio)},
                      f"dy <= {GATES['dy']} x radius, radii within {GATES['radius_ratio']}",
                      dy <= GATES["dy"] and ratio <= GATES["radius_ratio"]))
    for side in ("R", "L"):
        e = eyes[side]
        gates.append(gate(f"eye.poke.{side}", r4(e["poke"]), f"<= {GATES['poke']} x radius", e["poke"] <= GATES["poke"]))
        gates.append(gate(f"eye.rim_gap.{side}", r4(e["rim_gap_p90"]), f"p90 <= {GATES['rim_gap']} x radius",
                          e["rim_gap_p90"] <= GATES["rim_gap"]))
        share = e["removed"] / nf
        gates.append(gate(f"eye.removed.{side}", e["removed"], f"1 .. {GATES['removed_max']} x {nf} head faces",
                          1 <= e["removed"] and share <= GATES["removed_max"]))
    # the ball is what the front view sees in the opening
    keep = ~kill
    after = composite(V, F[keep], UV, tex, eyes, box, upp, angle=0)
    gone = kill[np.maximum(r["fid"], 0)] & (r["fid"] >= 0)       # pixels whose painted face was removed
    for side in ("R", "L"):
        M = eyes[side]["mask"]
        mine = after["who"] == (1 if side == "R" else 2)
        hole = gone & M
        share = float(mine[hole].mean()) if hole.any() else 0.0
        eyes[side]["in_opening"] = share
        eyes[side]["ball_seen"] = float(mine[M].mean())
        gates.append(gate(f"eye.in_opening.{side}", r4(share), f">= {GATES['in_opening']} of the cut-out pixels",
                          share >= GATES["in_opening"], ball_seen_in_opening=r4(eyes[side]["ball_seen"])))
    res.update(kill=kill, eyes=eyes, gates=gates, ok=all(g["pass"] for g in gates), pair=found, after=after)
    return res


def eye_texture(c, R, n, r, M, col8, sclera, lid):
    """TEX x TEX uint8 RGB: the front view of the ball; the painted opening projected onto it, sclera elsewhere."""
    np = _np()
    t, b = eye_frame(n)
    g = (np.arange(TEX) + 0.5) / TEX * 2 - 1
    GU, GV = np.meshgrid(g, -g)                   # column: D.t from -1 to 1; row: D.b from 1 (top) to -1
    rr = GU ** 2 + GV ** 2
    inside_disk = rr < 1
    D = GU[..., None] * t + GV[..., None] * b + np.sqrt(np.clip(1 - rr, 0, 1))[..., None] * n
    P = c + R * D
    upp, cx, cy = r["frame"]
    h, w = M.shape
    px = np.floor(cx + P[..., 0] / upp).astype(np.int64)
    py = np.floor(cy - P[..., 1] / upp).astype(np.int64)
    ok = inside_disk & (px >= 0) & (py >= 0) & (px < w) & (py < h)
    Me = erode(M, max(1, int(round(0.017 * lid))))
    base = np.median(col8[sclera], 0) if sclera.any() else np.array([235, 235, 235])
    out = np.tile(base.astype(np.uint8), (TEX, TEX, 1))
    take = np.zeros_like(ok)
    take[ok] = Me[py[ok], px[ok]]
    out[take] = col8[py[take], px[take]]
    return out


def composite(V, F, UV, tex, eyes, box, upp, angle=0.0):
    """Front render of the head and the eyeballs, z-composited; angle turns everything about +Y (degrees).
    who: 0 background, 3 head, 1 eye R, 2 eye L."""
    np = _np()
    a = math.radians(angle)
    Ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    rh = render(V @ Ry.T, F, UV, tex, box, upp)
    col = rh["col"].copy()
    z = np.where(np.isfinite(rh["pts"][..., 2]), rh["pts"][..., 2], -np.inf)
    who = np.where(rh["fid"] >= 0, 3, 0)
    for k, side in ((1, "R"), (2, "L")):
        e = eyes.get(side)
        if not e:
            continue
        re = render(e["V"] @ Ry.T, e["F"], e["UV"], e["tex"].astype(float) / 255, box, upp)
        ze = np.where(np.isfinite(re["pts"][..., 2]), re["pts"][..., 2], -np.inf)
        win = ze > z
        col[win] = re["col"][win]
        who[win] = k
        z = np.maximum(z, ze)
    return {"col": col, "who": who}


# ---------------------------------------------------------------------------------------- GLB files
def _glb_bytes(gltf, binary):
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    binary = binary + b"\0" * (-len(binary) % 4)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binary))
    return out + struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(binary), 0x004E4942) + binary


def _node_mats(gltf):
    np = _np()
    import part_math as pm
    mats = {}

    def walk(i, parent):
        node = gltf["nodes"][i]
        m = parent @ pm._node_matrix(node)
        if "mesh" in node:
            mats.setdefault(node["mesh"], m)
        for ch in node.get("children", []):
            walk(ch, m)

    scene = gltf.get("scenes", [{}])[gltf.get("scene", 0)]
    for i in scene.get("nodes", range(len(gltf.get("nodes", [])))):
        walk(i, np.eye(4))
    return mats


def read_prims(path):
    """(gltf, binary, [{mesh, prim, material, V (world), F (local), UV, image bytes}])."""
    np = _np()
    import part_math as pm
    gltf, binary = pm._parse_glb(path)
    mats = _node_mats(gltf)
    out = []
    for mi, mesh in enumerate(gltf.get("meshes", [])):
        m = mats.get(mi, np.eye(4))
        for pi, prim in enumerate(mesh["primitives"]):
            if prim.get("mode", 4) != 4 or "indices" not in prim:
                continue
            V = pm._accessor(gltf, binary, prim["attributes"]["POSITION"]).astype(float) @ m[:3, :3].T + m[:3, 3]
            F = pm._accessor(gltf, binary, prim["indices"]).reshape(-1, 3).astype(np.int64)
            UV = (pm._accessor(gltf, binary, prim["attributes"]["TEXCOORD_0"]).astype(float)
                  if "TEXCOORD_0" in prim["attributes"] else np.zeros((len(V), 2)))
            mat = gltf["materials"][prim["material"]] if "material" in prim else {}
            image = None
            tex = mat.get("pbrMetallicRoughness", {}).get("baseColorTexture")
            if tex is not None:
                img = gltf["images"][gltf["textures"][tex["index"]]["source"]]
                if "bufferView" in img:
                    bv = gltf["bufferViews"][img["bufferView"]]
                    s = bv.get("byteOffset", 0)
                    image = binary[s: s + bv["byteLength"]]
            out.append({"mesh": mi, "prim": pi, "mesh_name": mesh.get("name"), "material": mat.get("name"),
                        "V": V, "F": F, "UV": UV, "image": image})
    return gltf, binary, out


def rewrite_indices(src, dst, edits, mark):
    """Copy a GLB, each (mesh, prim) of `edits` taking new triangle indices (appended as a new buffer
    view), and asset.extras.eye_fit = mark. Nothing else changes."""
    np = _np()
    import part_math as pm
    gltf, binary = pm._parse_glb(src)
    binary = bytearray(binary)
    for (mi, pi), F in edits.items():
        prim = gltf["meshes"][mi]["primitives"][pi]
        binary += b"\0" * (-len(binary) % 4)
        blob = np.asarray(F, np.uint32).reshape(-1).tobytes()
        gltf["bufferViews"].append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(blob),
                                    "target": 34963})
        binary += blob
        gltf["accessors"].append({"bufferView": len(gltf["bufferViews"]) - 1, "componentType": 5125,
                                  "count": int(np.asarray(F).size), "type": "SCALAR"})
        prim["indices"] = len(gltf["accessors"]) - 1
    gltf["buffers"][0]["byteLength"] = len(binary) + (-len(binary) % 4)
    gltf.setdefault("asset", {}).setdefault("extras", {})[MARK] = mark
    with open(dst, "wb") as handle:
        handle.write(_glb_bytes(gltf, bytes(binary)))


def png_rgb(a):
    """PNG bytes of an (h, w, 3) uint8 array, without Pillow."""
    h, w = a.shape[:2]
    raw = b"".join(b"\0" + a[r].tobytes() for r in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def write_eyes_glb(path, eyes, name):
    """Eye.L and Eye.R: their own node, mesh, material and embedded PNG; node extras eye, centre, radius, axis."""
    np = _np()
    blobs, views, acc = [], [], []
    off = 0

    def add(blob, target=None):
        nonlocal off
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(blob), **({"target": target} if target else {})})
        pad = blob + b"\0" * (-len(blob) % 4)
        blobs.append(pad)
        off += len(pad)
        return len(views) - 1

    gltf = {"asset": {"version": "2.0", "generator": "eye_fit.py"}, "scene": 0, "scenes": [{"nodes": []}],
            "nodes": [], "meshes": [], "materials": [], "textures": [], "images": [], "samplers": [{}],
            "accessors": acc, "bufferViews": views}
    for side in ("L", "R"):
        e = eyes[side]
        V, N, UV = (np.asarray(e[k], np.float32) for k in ("V", "N", "UV"))
        F = np.asarray(e["F"], np.uint32)
        ia = len(acc)
        acc.append({"bufferView": add(V.tobytes(), 34962), "componentType": 5126, "count": len(V), "type": "VEC3",
                    "min": V.min(0).tolist(), "max": V.max(0).tolist()})
        acc.append({"bufferView": add(N.tobytes(), 34962), "componentType": 5126, "count": len(N), "type": "VEC3"})
        acc.append({"bufferView": add(UV.tobytes(), 34962), "componentType": 5126, "count": len(UV), "type": "VEC2"})
        acc.append({"bufferView": add(F.tobytes(), 34963), "componentType": 5125, "count": F.size, "type": "SCALAR"})
        label = f"{name}_eye_{side.lower()}"
        gltf["images"].append({"bufferView": add(png_rgb(e["tex"])), "mimeType": "image/png", "name": label})
        gltf["textures"].append({"source": len(gltf["images"]) - 1, "sampler": 0})
        gltf["materials"].append({"name": label, "pbrMetallicRoughness": {
            "baseColorTexture": {"index": len(gltf["textures"]) - 1}, "metallicFactor": 0.0, "roughnessFactor": 0.35}})
        gltf["meshes"].append({"name": f"Eye.{side}", "primitives": [{
            "attributes": {"POSITION": ia, "NORMAL": ia + 1, "TEXCOORD_0": ia + 2}, "indices": ia + 3,
            "material": len(gltf["materials"]) - 1}]})
        gltf["nodes"].append({"name": f"Eye.{side}", "mesh": len(gltf["meshes"]) - 1, "extras": {
            "eye": side, "centre": [round(float(x), 6) for x in e["centre"]], "radius": round(float(e["radius"]), 6),
            "axis": [round(float(x), 6) for x in e["axis"]]}})
        gltf["scenes"][0]["nodes"].append(len(gltf["nodes"]) - 1)
    binary = b"".join(blobs)
    gltf["buffers"] = [{"byteLength": len(binary)}]
    with open(path, "wb") as handle:
        handle.write(_glb_bytes(gltf, binary))


def decode_image(data):
    """(h, w, 3) floats 0..1 from PNG or JPEG bytes (Pillow)."""
    np = _np()
    from PIL import Image
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB")).astype(float) / 255.0


def _face_keys(V, F):
    np = _np()
    return [tuple(k) for k in np.round(V[F].mean(1) * 1e6).astype(np.int64).tolist()]


# ---------------------------------------------------------------------------------------------- fit
def _source(path, backup):
    """The GLB assemble wrote: the backup when `path` is our own edit, else `path` (and it becomes the backup)."""
    import part_math as pm
    gltf, _ = pm._parse_glb(path)
    if MARK in (gltf.get("asset", {}).get("extras") or {}):
        if not os.path.isfile(backup):
            raise Refused(f"{path} was edited by eye_fit and {backup} is gone: run assemble_parts.py again")
        return backup
    shutil.copy2(path, backup)
    return backup


def fit(assembly_dir, name=None, head_material=None, radius_frac=0.55, render_png=True):
    np = _np()
    a = os.path.abspath(assembly_dir)
    if name is None:
        rigs = [f for f in os.listdir(a) if f.endswith("_rig.glb")] if os.path.isdir(a) else []
        if len(rigs) != 1:
            raise Refused(f"{a}: {len(rigs)} *_rig.glb files; pass --name")
        name = rigs[0][:-len("_rig.glb")]
    rig = os.path.join(a, f"{name}_rig.glb")
    parts = os.path.join(a, f"{name}_parts.glb")
    if not os.path.isfile(rig):
        raise Refused(f"missing {rig}")
    head_material = head_material or f"{name}_head"
    src = _source(rig, os.path.join(a, f"{name}_rig.pre_eyes.glb"))
    _, _, prims = read_prims(src)
    heads = [p for p in prims if p["material"] == head_material]
    if len(heads) != 1:
        raise Refused(f"{src}: {len(heads)} primitives of material {head_material!r} "
                      f"(have {sorted({str(p['material']) for p in prims})}); pass --head-material")
    hp = heads[0]
    if hp["image"] is None:
        raise Refused(f"{head_material!r} has no embedded base-colour texture")
    tex = decode_image(hp["image"])
    res = fit_eyes(hp["V"], hp["F"], hp["UV"], tex, radius_frac)
    eyes = res["eyes"]
    rep = {"schema": "gate/1", "tool": "eye_fit", "op": "fit", "name": name, "head_material": head_material,
           "head_faces": len(hp["F"]), "radius_frac": radius_frac, "frame": "the assembly GLB's (+Y up, facing +Z)",
           "eyes": {s: {"centre": [r4(x) for x in e["centre"]], "radius": round(float(e["radius"]), 5),
                        "axis": [r4(x) for x in e["axis"]], "lid_width": round(float(e["lid_width"]), 5),
                        "pushed_back": round(float(e["pushed_back"]), 5), "rim_gap_mean": r4(e["rim_gap_mean"]),
                        "rim_gap_p90": r4(e["rim_gap_p90"]), "poke": r4(e["poke"]), "faces_removed": e["removed"],
                        "faces_removed_hidden": e["removed_hidden"], "opening_px": e["opening_px"],
                        "in_opening": r4(e.get("in_opening")), "ball_seen": r4(e.get("ball_seen"))} for s, e in eyes.items()},
           "faces_removed": int(res["kill"].sum()), "gates": res["gates"]}
    if res.get("why"):
        rep["why"] = res["why"]
    ok = res["ok"]
    outputs = {}
    if ok:
        keep = ~res["kill"]
        mark = {"faces_removed": int(res["kill"].sum()), "from": os.path.basename(src)}
        rewrite_indices(src, rig, {(hp["mesh"], hp["prim"]): hp["F"][keep]}, mark)
        outputs["rig_glb"] = rig
        if os.path.isfile(parts):
            psrc = _source(parts, os.path.join(a, f"{name}_parts.pre_eyes.glb"))
            _, _, pprims = read_prims(psrc)
            gone = set(k for k, x in zip(_face_keys(hp["V"], hp["F"]), res["kill"]) if x)
            edits = {}
            for p in pprims:
                if p["material"] != head_material or (p["mesh_name"] or "").startswith("Hair"):
                    continue
                kk = _face_keys(p["V"], p["F"])
                drop = np.array([k in gone for k in kk])
                if drop.any():
                    edits[(p["mesh"], p["prim"])] = p["F"][~drop]
            if edits:
                rewrite_indices(psrc, parts, edits, mark)
                outputs["parts_glb"] = parts
                rep["parts_faces_removed"] = int(sum(len(p["F"]) - len(edits[(p["mesh"], p["prim"])])
                                                     for p in pprims if (p["mesh"], p["prim"]) in edits))
        eyes_glb = os.path.join(a, f"{name}_eyes.glb")
        write_eyes_glb(eyes_glb, eyes, name)
        outputs["eyes_glb"] = eyes_glb
    if render_png and eyes:
        png = os.path.join(a, "eyes.png")
        sheet(hp["V"], hp["F"], hp["UV"], tex, res, png)
        outputs["eyes_png"] = png
    rep.update(outputs=outputs, verdict="green" if ok else "failed", next=(
        f"autorig.py all OUT {os.path.join(a, name + '_rig.glb')}"
        + (f" --hair {os.path.join(a, name + '_hair.glb')}" if os.path.exists(os.path.join(a, name + '_hair.glb')) else "")
        + f" --eyes {os.path.join(a, name + '_eyes.glb')} --facial"
        if ok else "a person looks at eyes.png; the eyes stay painted"))
    rep["pass"] = rep["ok"] = ok
    gate_json = os.path.join(a, f"{name}.eyes.gate.json")
    with open(gate_json, "w", encoding="utf-8") as handle:
        json.dump(rep, handle, indent=1)
    return (0 if ok else 2), rep


def sheet(V, F, UV, tex, res, path):
    """eyes.png: the eyes close up, front and 3/4, painted and with eyeballs."""
    np = _np()
    from PIL import Image, ImageDraw
    eyes = res["eyes"]
    cs = [e["centre"] for e in eyes.values()]
    Rm = max(e["radius"] for e in eyes.values())
    cx = float(np.mean([c[0] for c in cs]))
    cy = float(np.mean([c[1] for c in cs]))
    half = max(abs(c[0] - cx) for c in cs) + 3.5 * Rm
    box = (cx - half, cx + half, cy - 2.2 * Rm, cy + 2.2 * Rm)
    upp = 2 * half / 640
    keep = ~res["kill"]
    tiles = []
    for ang in (0, 35):
        tiles.append((f"painted {ang} deg", composite(V, F, UV, tex, {}, box, upp, ang)["col"]))
        tiles.append((f"eyeballs {ang} deg", composite(V, F[keep], UV, tex, eyes, box, upp, ang)["col"]))
    hgt = tiles[0][1].shape[0]
    img = Image.new("RGB", (640 * 2 + 6, (hgt + 22) * 2), (28, 28, 32))
    d = ImageDraw.Draw(img)
    for i, (lab, col) in enumerate(tiles):
        x, y = (i % 2) * 646, (i // 2) * (hgt + 22)
        img.paste(Image.fromarray(np.clip(col * 255, 0, 255).astype(np.uint8)), (x, y + 22))
        d.text((x + 6, y + 5), lab, fill=(230, 230, 230))
    img.save(path)


# --------------------------------------------------------------------------------------------- bind
def _import_eyes(path, col):
    """Eye objects from a GLB (importer transform baked, helpers removed): {side: (obj, extras)}."""
    import bpy
    from mathutils import Matrix
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    out = {}
    for o in new:
        if o.type != 'MESH':
            continue
        w = o.matrix_world.copy()
        o.parent = None
        o.data.transform(w)
        o.matrix_world = Matrix.Identity(4)
        side = o.get("eye") or ("L" if o.name.startswith("Eye.L") else "R" if o.name.startswith("Eye.R") else None)
        if side in ("L", "R"):
            for c in list(o.users_collection):
                c.objects.unlink(o)
            col.objects.link(o)
            o.name = o.data.name = f"Eye.{side}"
            out[side] = o
    for o in new:
        if o.name in bpy.data.objects and o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    return out


def _evaluated(obj):
    import bpy
    np = _np()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    M = np.array(obj.matrix_world)
    return co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]


def bind(out, eyes_glb, rig_glb, name=None, turn=25.0):
    import bpy
    from mathutils import Matrix, Vector
    import assemble_parts as ap
    np = _np()
    out = os.path.abspath(out)
    rig_dir = os.path.join(out, "rig")
    if name is None:
        blends = [f for f in os.listdir(rig_dir) if f.endswith("_arp.blend") and ".pre_" not in f] \
            if os.path.isdir(rig_dir) else []
        if len(blends) != 1:
            raise Refused(f"{rig_dir}: {len(blends)} *_arp.blend files; pass --name")
        name = blends[0][:-len("_arp.blend")]
    blend = os.path.join(rig_dir, f"{name}_arp.blend")
    contract = os.path.join(rig_dir, f"{name}.contract.json")
    for p in (blend, contract, eyes_glb, rig_glb):
        if not os.path.isfile(p):
            raise Refused(f"missing {p}")
    with open(contract, encoding="utf-8") as handle:
        rmap = json.load(handle).get("retarget_map") or {}
    head_bone = rmap.get("Head")
    if not head_bone:
        raise Refused(f"{contract} maps no Head bone")
    bpy.ops.wm.open_mainfile(filepath=blend)
    rigs = [o for o in bpy.data.objects if o.type == 'ARMATURE' and head_bone in o.data.bones]
    if len(rigs) != 1:
        raise Refused(f"{len(rigs)} armatures carry the bone {head_bone!r}")
    rig = rigs[0]
    is_eye = lambda o: o.type == 'MESH' and bool(o.get("parts_eye"))
    bound = [o for o in bpy.data.objects if o.type == 'MESH' and not is_eye(o) and not o.get("parts_hair")
             and any(m.type == 'ARMATURE' and m.object == rig for m in o.modifiers)]
    if not bound:
        raise Refused("no mesh is bound to the rig")
    if not any(is_eye(o) for o in bpy.data.objects):
        shutil.copy2(blend, os.path.join(rig_dir, f"{name}_arp.pre_eyes.blend"))
    mesh = max(bound, key=lambda o: len(o.data.vertices))
    co = np.empty(len(mesh.data.vertices) * 3)
    mesh.data.vertices.foreach_get("co", co)
    M = np.array(mesh.matrix_world)
    prepped = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    tmp = ap.collection("EyesTmp")
    raw_obj = ap.import_glb(rig_glb, "EyesRawRig", tmp)
    rco = np.empty(len(raw_obj.data.vertices) * 3)
    raw_obj.data.vertices.foreach_get("co", rco)
    bpy.data.objects.remove(raw_obj, do_unlink=True)
    s, t = ap.recover_prep(rco.reshape(-1, 3), prepped)
    d, _ = ap.kd_nn(prepped)(s * rco.reshape(-1, 3) + t)
    height = float(np.ptp(prepped[:, 2]))
    residual = float(d.max())
    for old in [o for o in bpy.data.objects if is_eye(o)]:
        bpy.data.objects.remove(old, do_unlink=True)
    eyes = _import_eyes(eyes_glb, mesh.users_collection[0])
    if set(eyes) != {"L", "R"}:
        raise Refused(f"{eyes_glb}: eyes {sorted(eyes)}, want L and R")
    names = {b.name for b in rig.data.bones}
    report_eyes, degraded, warnings = {}, False, []
    for side, o in eyes.items():
        ex = {k: o.get(k) for k in ("centre", "radius", "axis")}
        if ex["centre"] is None or ex["radius"] is None:
            raise Refused(f"{eyes_glb}: Eye.{side} carries no centre/radius extras (write it with eye_fit.py fit)")
        o.data.transform(Matrix.Translation(Vector(t)) @ Matrix.Scale(s, 4))
        o.data.update()
        cg = np.array(ex["centre"], float)
        c = s * np.array([cg[0], -cg[2], cg[1]]) + t
        ag = np.array(ex["axis"], float)
        ax = np.array([ag[0], -ag[2], ag[1]])
        R = s * float(ex["radius"])
        bone = rmap.get(f"Eye.{side}") or next((b for b in (f"c_eye.{side.lower()}",) if b in names), None)
        if bone is None:
            bone, degraded = head_bone, True
            warnings.append(f"no eye bone for Eye.{side} (the face was not built: autorig --facial): bound to {head_bone}")
        for vg in list(o.vertex_groups):
            o.vertex_groups.remove(vg)
        ap.add_group(o, bone)
        mod = o.modifiers.new("Armature", 'ARMATURE')
        mod.object = rig
        mw = o.matrix_world.copy()
        o.parent = rig
        o.matrix_world = mw
        o["parts_eye"] = side
        report_eyes[side] = {"object": o.name, "bone": bone, "centre": [r4(x) for x in c], "radius": r4(R),
                             "vertices": len(o.data.vertices), "c": c, "R": R, "ax": ax / np.linalg.norm(ax)}
    # the eye bone moves the ball alone: skin the rig weighted to it goes to its parent (it would turn with
    # the gaze and cut into the ball); the eye bones and everything pivoting with them move onto the ball's
    # centre (a symmetric face rig places both from one side)
    moved_skin, pivot, pivot_after = {}, {}, {}
    Wr = np.array(rig.matrix_world)
    Wi = np.linalg.inv(Wr)
    others = [o for o in bpy.data.objects if o.type == 'MESH' and not is_eye(o)
              and any(m.type == 'ARMATURE' and m.object == rig for m in o.modifiers)]
    snaps = []
    for side, e in report_eyes.items():
        bone = e["bone"]
        if bone == head_bone:
            continue
        b = rig.data.bones[bone]
        parent = b.parent.name if b.parent is not None and b.parent.use_deform else head_bone
        n = 0
        for o in others:
            src = o.vertex_groups.get(bone)
            if src is None:
                continue
            dst = o.vertex_groups.get(parent) or o.vertex_groups.new(name=parent)
            for v in o.data.vertices:
                for g in v.groups:
                    if g.group == src.index and g.weight > 0:
                        dst.add([v.index], g.weight, 'ADD')
                        n += 1
            o.vertex_groups.remove(src)
        moved_skin[side] = {"to": parent, "vertices": n}
        head_w = (Wr @ np.r_[np.array(b.head_local), 1.0])[:3]
        pivot[side] = float(np.linalg.norm(head_w - e["c"]) / e["R"])
        snaps.append((side, np.array(b.head_local), Wi[:3, :3] @ (e["c"] - head_w)))
    if snaps:
        tol = 1e-4 * height
        for o in bpy.context.selected_objects:
            o.select_set(False)
        rig.hide_set(False)
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        mirror = rig.data.use_mirror_x            # X-mirror editing would move the other eye too
        rig.data.use_mirror_x = False
        bpy.ops.object.mode_set(mode='EDIT')
        for side, old, d in snaps:
            for eb in rig.data.edit_bones:
                if (np.linalg.norm(np.array(eb.head) - old) < tol
                        or eb.name == f"c_eye_target.{side.lower()}"):
                    eb.head = Vector(np.array(eb.head) + d)
                    eb.tail = Vector(np.array(eb.tail) + d)
        bpy.ops.object.mode_set(mode='OBJECT')
        rig.data.use_mirror_x = mirror
        bpy.context.view_layer.update()
        for side, e in report_eyes.items():
            hw = (Wr @ np.r_[np.array(rig.data.bones[e["bone"]].head_local), 1.0])[:3]
            pivot_after[side] = float(np.linalg.norm(hw - e["c"]) / e["R"])
    bpy.context.view_layer.update()
    bad = 0
    for o in eyes.values():
        groups = {g.index: g.name for g in o.vertex_groups}
        bone = report_eyes[o["parts_eye"]]["bone"]
        bad += sum(1 for v in o.data.vertices if len(v.groups) != 1 or groups[v.groups[0].group] != bone
                   or abs(v.groups[0].weight - 1) > 1e-6)
    left = sum(1 for o in others for e in report_eyes.values() if e["bone"] != head_bone
               and o.vertex_groups.get(e["bone"]) is not None)
    gates = [gate("eyes.transform_residual", residual, f"<= {1e-5 * height:.3g} (1e-5 x height)",
                  residual <= 1e-5 * height),
             gate("eyes.bound", bad, 0, bad == 0),
             gate("eyes.skin_off_eye_bone", left, 0, left == 0, moved=moved_skin)]
    # turn each eye bone as Unity's LeftEye/RightEye would: its own constraints (an aim at the add-on's eye
    # target) and the lids' follow of it muted meanwhile; the ball follows rigidly, the lids stay outside it.
    # With the lids following (Blender's own face rig) the cut is reported, not gated
    follow, poke = [], {}
    rest_body = np.vstack([_evaluated(o) for o in others])
    for side, o in eyes.items():
        e = report_eyes[side]
        pb = rig.pose.bones[e["bone"]]
        c, R, ax = e["c"], e["R"], e["ax"]
        rest = _evaluated(o)
        ip = int(np.argmin(np.linalg.norm(rest - (c + R * ax), axis=1)))     # the iris centre
        near = np.linalg.norm(rest_body - c, axis=1) < 1.6 * R
        own = [(con, con.mute) for con in pb.constraints]
        follows = [(con, con.mute) for q in rig.pose.bones for con in q.constraints
                   if q is not pb and getattr(con, "subtarget", None) == e["bone"]]
        for con, _ in own + follows:
            con.mute = True
        bpy.context.view_layer.update()
        M0 = np.array(pb.matrix)
        worst, worst_follow = 0.0, 0.0
        rest_cut = max(0.0, float((R - np.linalg.norm(rest_body[near] - c, axis=1)).max())) / R if near.any() else 0.0
        for axis_w, ang in (((0, 0, 1), turn), ((0, 0, 1), -turn), ((1, 0, 0), turn), ((1, 0, 0), -turn)):
            saved = pb.matrix_basis.copy()
            a_arm = (Matrix(Wi.tolist()).to_3x3() @ Vector(axis_w)).normalized()
            p = Vector(pb.head)
            Rot = Matrix.Translation(p) @ Matrix.Rotation(math.radians(ang), 4, a_arm) @ Matrix.Translation(-p)
            pb.matrix = Rot @ pb.matrix
            bpy.context.view_layer.update()
            D = Wr @ np.array(pb.matrix) @ np.linalg.inv(M0) @ Wi           # what the bone actually did
            moved = _evaluated(o)
            dev = float(np.abs(moved - (rest @ D[:3, :3].T + D[:3, 3])).max())
            c1 = D[:3, :3] @ c + D[:3, 3]
            u0, u1 = rest[ip] - c, moved[ip] - c1
            got = math.degrees(math.acos(max(-1.0, min(1.0, float(u0 @ u1) / (np.linalg.norm(u0) * np.linalg.norm(u1))))))
            cut = lambda: max(0.0, float((R - np.linalg.norm(np.vstack([_evaluated(x) for x in others])[near] - c1,
                                                                axis=1)).max())) / R if near.any() else 0.0
            pk = cut()
            for con, m in follows:
                con.mute = m
            bpy.context.view_layer.update()
            pkf = cut()
            for con, _ in follows:
                con.mute = True
            turned = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(D[:3, :3]) - 1) / 2))))
            worst, worst_follow = max(worst, pk - rest_cut), max(worst_follow, pkf - rest_cut)
            follow.append({"eye": side, "axis": axis_w, "deg": ang, "deviation": dev, "turned_deg": round(turned, 3),
                           "iris_deg": round(got, 3), "poke": round(pk, 4), "poke_lids_follow": round(pkf, 4)})
            pb.matrix_basis = saved
            bpy.context.view_layer.update()
        for con, m in own + follows:
            con.mute = m
        e["muted_for_the_turns"] = sorted({con.name for con, _ in own + follows})
        e["poke_rest"] = round(rest_cut, 4)              # hidden vertices inside the ball count here too
        e["poke_added_lids_follow"] = round(worst_follow, 4)
        poke[side] = worst
    bpy.context.view_layer.update()
    fol_ok = all(f["deviation"] <= 1e-5 * height and abs(f["turned_deg"] - abs(f["deg"])) <= GATES["follow_deg"]
                 for f in follow)
    gates.append(gate("eyes.follows_bone", max(f["deviation"] for f in follow),
                      f"<= {1e-5 * height:.3g}, the bone turned within {GATES['follow_deg']} deg of +-{turn}", fol_ok,
                      turns=follow))
    gates.append(gate("eyes.poke_turned", {k: r4(v) for k, v in poke.items()},
                      f"what the turns add to the rest cut <= {GATES['poke']} x radius",
                      all(v <= GATES["poke"] for v in poke.values())))
    for e in report_eyes.values():
        for k in ("c", "R", "ax"):
            e.pop(k, None)
    export = {}
    if all(g["pass"] for g in gates[:3]):
        root = os.path.normpath(os.path.join(HERE, "..", ".."))
        sys.path.insert(0, os.path.join(root, "blender-retarget", "scripts"))
        import brt_arp
        export = brt_arp.run({"op": "export", "armature": rig.name, "fbx": os.path.join(out, "export", f"{name}.fbx")})
        gates += [g for g in export.get("gates", [])]
        bpy.ops.wm.save_as_mainfile(filepath=blend)
    ok = all(g["pass"] for g in gates)
    rep = {"schema": "gate/1", "tool": "eye_fit", "op": "bind", "pass": ok, "ok": ok,
           "verdict": ("degraded" if degraded else "green") if ok else "failed", "degraded": degraded,
           "name": name, "scale": s, "shift": [float(x) for x in t], "eyes": report_eyes,
           "pivot_offset": {k: r4(v) for k, v in pivot.items()},
           "pivot_offset_after": {k: r4(v) for k, v in pivot_after.items()}, "warnings": warnings,
           "export": {k: v for k, v in export.items() if k in ("export", "meshes", "refused", "reason")},
           "next": f"autorig.py deform {out}", "gates": gates}
    return (0 if ok else 2), rep


# --------------------------------------------------------------------------------------- selftest
def synthetic_head(eyes=True, mouth=True, seed=0):
    """A sphere head (radius 0.08 at y 0.40, facing +Z) with an inner shell, planar front UVs and a painted
    face: skin, two almond eyes (sclera split by a dark iris) at x +-0.03, y 0.41, teeth at y 0.36."""
    np = _np()
    import part_math as pm
    Rh, yc = 0.08, 0.40

    def sphere(r, inward=False, nu=96, nv=72):
        def prof(v):
            a = 0.02 + v * (math.pi - 0.04)
            return r * np.sin(a), yc - r * np.cos(a)
        return pm.revolve(prof, n_az=nu, n_v=nv, inward=inward)

    V1, F1 = sphere(Rh)
    if eyes:          # a generated head has the eye ball's bulge in its surface: the lids lie on it
        Re = 0.55 * 0.022
        for sx in (-1, 1):
            p = np.array([sx * 0.03, 0.41, 0.0])
            p[2] = math.sqrt(Rh ** 2 - p[0] ** 2 - (p[1] - yc) ** 2)
            n = (p - [0, yc, 0]) / Rh
            B = p - 0.7 * Re * n
            d = V1 - B
            a = d @ n
            lat = d - a[:, None] * n
            rho = np.linalg.norm(lat, axis=1)
            ab = np.sqrt(np.clip(Re ** 2 - rho ** 2, 0, None))
            up = (rho < Re) & (a > 0) & (ab > a)
            V1[up] = B + lat[up] + ab[up, None] * n
    V2, F2 = sphere(0.07, inward=True, nu=48, nv=36)
    V, F = pm.merge((V1, F1), (V2, F2))
    UV = np.c_[0.5 + V[:, 0] / (2.2 * Rh), 0.5 - (V[:, 1] - yc) / (2.2 * Rh)]
    S = 512
    g = (np.arange(S) + 0.5) / S
    X = (g - 0.5) * 2.2 * Rh
    Y = yc - (g - 0.5) * 2.2 * Rh
    XX, YY = np.meshgrid(X, Y)
    tex = np.tile(np.array([0.93, 0.74, 0.62]), (S, S, 1))
    if eyes:
        for sx in (-1, 1):
            ex, ey = sx * 0.03, 0.41
            alm = ((XX - ex) / 0.011) ** 2 + ((YY - ey) / 0.005) ** 2 < 1
            tex[alm] = (0.95, 0.95, 0.96)
            iris = np.hypot(XX - ex, YY - ey) < 0.0042
            tex[iris & alm] = (0.12, 0.10, 0.20)
    if mouth:
        teeth = (np.abs(XX) < 0.012) & (np.abs(YY - 0.36) < 0.0025)
        tex[teeth] = (0.97, 0.97, 0.97)
    return V, F, UV, tex


def contract_sample(script, case, doc):
    out = os.environ.get("UNITY_DEV_CONTRACT_OUT") or os.path.join(tempfile.gettempdir(), "unity-dev-contract-out")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{script}__{case}.gate.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1, default=str)
    print(f"selftest-output: {path}")


def _fixture_glb(path, name, V, F, UV, tex):
    """A two-primitive rig GLB: the body (a box far below) and the head, materials <c>_body / <c>_head."""
    np = _np()
    bV = np.array([[x, y, z] for x in (-0.05, 0.05) for y in (0.0, 0.2) for z in (-0.05, 0.05)], float)
    bF = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                   [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]], np.int64)
    blobs, views, acc = [], [], []
    off = 0

    def add(blob):
        nonlocal off
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(blob)})
        pad = blob + b"\0" * (-len(blob) % 4)
        blobs.append(pad)
        off += len(pad)
        return len(views) - 1

    prims, mats = [], []
    t8 = np.clip(tex * 255, 0, 255).astype(np.uint8)
    for label, (Vx, Fx, UVx) in ((f"{name}_body", (bV, bF, np.zeros((len(bV), 2)))), (f"{name}_head", (V, F, UV))):
        Vx = np.asarray(Vx, np.float32)
        ia = len(acc)
        acc.append({"bufferView": add(Vx.tobytes()), "componentType": 5126, "count": len(Vx), "type": "VEC3",
                    "min": Vx.min(0).tolist(), "max": Vx.max(0).tolist()})
        acc.append({"bufferView": add(np.asarray(UVx, np.float32).tobytes()), "componentType": 5126,
                    "count": len(Vx), "type": "VEC2"})
        acc.append({"bufferView": add(np.asarray(Fx, np.uint32).tobytes()), "componentType": 5125,
                    "count": int(np.asarray(Fx).size), "type": "SCALAR"})
        mats.append({"name": label, "pbrMetallicRoughness": {"baseColorTexture": {"index": len(mats)}}})
        prims.append({"attributes": {"POSITION": ia, "TEXCOORD_0": ia + 1}, "indices": ia + 2, "material": len(mats) - 1})
    images = [{"bufferView": add(png_rgb(t8)), "mimeType": "image/png"} for _ in mats]
    binary = b"".join(blobs)
    gltf = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": name}],
            "meshes": [{"name": name, "primitives": prims}], "materials": mats, "accessors": acc,
            "bufferViews": views, "buffers": [{"byteLength": len(binary)}], "images": images,
            "textures": [{"source": i} for i in range(len(images))]}
    with open(path, "wb") as handle:
        handle.write(_glb_bytes(gltf, binary))


def selftest():
    np = _np()
    checks, failed = [], []

    def ok(name, cond, value=None):
        checks.append({"check": name, "pass": bool(cond), "value": value})
        if not cond:
            failed.append(name)
        print(("PASS " if cond else "FAIL ") + name + ("" if value is None else f"  ({value})"))

    m = np.zeros((9, 12), bool)
    m[1:3, 1:3] = True
    m[3, 3] = True                    # diagonal: the same 8-connected component
    m[6:8, 7:11] = True
    lab, n = label(m)
    ok("label: 8-connected components", n == 2 and lab[1, 1] == lab[3, 3] != lab[6, 8], n)
    hull = convex_fill(np.array([[2, 2], [10, 2], [6, 8]]), (12, 14))
    ok("convex fill: a triangle's inside, not its outside", hull[4, 6] and not hull[7, 2] and not hull[1, 6])

    V, F, UV, tex = synthetic_head()
    res = fit_eyes(V, F, UV, tex)
    ok("fit: both eyes found, every gate passes", res["ok"], [g["name"] for g in res["gates"] if not g["pass"]])
    e = res["eyes"]
    if set(e) == {"L", "R"}:
        ok("fit: L is on +X (the character's left), R on -X", e["L"]["centre"][0] > 0.02 and e["R"]["centre"][0] < -0.02,
           [r4(e["L"]["centre"][0]), r4(e["R"]["centre"][0])])
        ok("fit: centres at the painted eyes' height, behind the skin",
           all(abs(e[s]["centre"][1] - 0.41) < 0.003 and np.linalg.norm(e[s]["centre"] - [0, 0.40, 0]) < 0.08 - 0.5 * e[s]["radius"]
               for s in e), [[r4(x) for x in e[s]["centre"]] for s in e])
        ok("fit: radius = 0.55 x the lid width (0.022), within 6 %",
           all(abs(e[s]["radius"] / (0.55 * 0.022) - 1) < 0.06 for s in e), [r4(e[s]["radius"]) for s in e])
        ok("fit: the iris splits the sclera, still one opening per eye",
           all(e[s]["opening_px"] > 0 for s in e) and res["pair"]["R"]["iris"].any(), [e[s]["opening_px"] for s in e])
        kill = res["kill"]
        cent = V[F].mean(1)
        near = np.min([np.linalg.norm(cent - e[s]["centre"], axis=1) / e[s]["radius"] for s in e], axis=0)
        ok("hollow: every removed face lies within 1.5 x radius of an eye centre (the teeth stay)",
           kill.any() and near[kill].max() < 1.5 and not kill[np.abs(cent[:, 1] - 0.36) < 0.005].any(),
           [int(kill.sum()), r4(near[kill].max()) if kill.any() else None])
        ok("hollow: the inner shell inside the ball is removed, the outer surface only in the openings",
           kill.sum() > 0 and e["R"]["removed_hidden"] > 0 and e["L"]["removed_hidden"] > 0,
           [e[s]["removed_hidden"] for s in e])
        t = e["L"]["tex"]
        ok("texture: the iris at the front pole, sclera at the edge",
           t[TEX // 2, TEX // 2].mean() < 80 and t[TEX // 2, 8].mean() > 200, [int(t[TEX // 2, TEX // 2].mean()), int(t[TEX // 2, 8].mean())])
    blank = synthetic_head(eyes=False)
    rb = fit_eyes(*blank)
    ok("no painted eyes (the teeth alone): eye.found fails, nothing removed",
       not rb["ok"] and rb["gates"][0]["name"] == "eye.found" and not rb["kill"].any(), rb.get("why"))
    with tempfile.TemporaryDirectory() as td:
        rig = os.path.join(td, "runner_rig.glb")
        _fixture_glb(rig, "runner", V, F, UV, tex)
        _fixture_glb(os.path.join(td, "runner_parts.glb"), "runner", V, F, UV, tex)
        code, rep = fit(td, render_png=False)
        ok("fit (files): exit 0, eyes GLB and gate written", code == 0 and os.path.isfile(os.path.join(td, "runner_eyes.glb"))
           and os.path.isfile(os.path.join(td, "runner.eyes.gate.json")), code)
        _, _, after = read_prims(rig)
        _, _, before = read_prims(os.path.join(td, "runner_rig.pre_eyes.glb"))
        hb, ha = (next(p for p in x if p["material"] == "runner_head") for x in (before, after))
        bb, ba = (next(p for p in x if p["material"] == "runner_body") for x in (before, after))
        ok("fit (files): the head loses exactly the removed faces, the body is untouched, the backup is the original",
           len(hb["F"]) - len(ha["F"]) == rep["faces_removed"] > 0 and np.array_equal(bb["F"], ba["F"])
           and np.array_equal(hb["V"], ha["V"]), [len(hb["F"]), len(ha["F"])])
        ok("fit (files): the parts GLB's head loses the same faces (matched by position)",
           rep.get("parts_faces_removed") == rep["faces_removed"]
           and os.path.isfile(os.path.join(td, "runner_parts.pre_eyes.glb")), rep.get("parts_faces_removed"))
        g, _, ep = read_prims(os.path.join(td, "runner_eyes.glb"))
        ok("eyes GLB: Eye.L and Eye.R, own materials, extras centre/radius/axis",
           sorted(p["mesh_name"] for p in ep) == ["Eye.L", "Eye.R"] and len({p["material"] for p in ep}) == 2
           and all("radius" in nd.get("extras", {}) for nd in g["nodes"]) and all(p["image"] for p in ep))
        code2, rep2 = fit(td, render_png=False)
        _, _, again = read_prims(rig)
        ok("fit again: starts from the backup, same result",
           code2 == 0 and rep2["faces_removed"] == rep["faces_removed"]
           and len(next(p for p in again if p["material"] == "runner_head")["F"]) == len(ha["F"]))
        _fixture_glb(rig, "runner", *synthetic_head(eyes=False))
        code3, rep3 = fit(td, render_png=False)
        ok("a fresh assemble (no eye_fit mark) replaces the backup; no eyes: exit 2, the rig GLB left as is",
           code3 == 2 and "eyes_glb" not in rep3["outputs"]
           and MARK not in (read_prims(rig)[0]["asset"].get("extras") or {}), code3)
        contract_sample("eye_fit", "fit", rep)
        try:
            fit(td, head_material="nope", render_png=False)
            ok("a missing head material is refused", False)
        except Refused:
            ok("a missing head material is refused", True)
    return (0 if not failed else 1), {"selftest": "pass" if not failed else "fail", "failed": failed, "checks": checks}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser().parse_args(argv)
    if not args.selftest and args.cmd is None:
        parser().print_usage(sys.stderr)
        sys.exit(1)
    try:
        if args.selftest:
            code, report = selftest()
        elif args.cmd == "fit":
            code, report = fit(args.assembly_dir, args.name, args.head_material, args.radius_frac, not args.no_render)
        else:
            try:
                import bpy  # noqa: F401
            except ImportError:
                print(json.dumps({"tool": "eye_fit", "error": "bind runs inside Blender: blender -b -P eye_fit.py -- bind ..."}))
                sys.exit(1)
            code, report = bind(args.autorig_out, args.eyes, args.rig_glb, args.name, args.turn)
    except Refused as exc:
        code, report = 1, {"schema": "gate/1", "tool": "eye_fit", "pass": False, "ok": False, "verdict": "failed",
                           "gates": [], "refused": str(exc)}
    except Exception as exc:              # Blender -b exits 0 on an uncaught error: make it a failure
        import traceback
        traceback.print_exc()
        code, report = 1, {"schema": "gate/1", "tool": "eye_fit", "pass": False, "ok": False, "verdict": "harness",
                           "gates": [], "error": f"{type(exc).__name__}: {exc}"}
    if getattr(args, "report", None):
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1, default=str)
    print(json.dumps(report, indent=1, default=str))
    sys.stdout.flush()
    sys.exit(code)


if __name__ == "__main__":
    main()
