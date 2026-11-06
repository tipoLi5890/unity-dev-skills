#!/usr/bin/env python3
"""shell_strip.py — remove an image-to-3D mesh's inward-facing inner shell before rigging and retopology.

Some image-to-3D generators (a flexible-dual-grid mesh extraction) write every surface twice: the outer
skin, and a second sheet a few thousandths of the size behind it facing the other way (back to back),
joined to the outer skin where the two fold over at a hem, a cuff or a sole. It is about half the
triangles and half the used UV space, it is never seen, it takes weights of its own, and a remesher
that needs a manifold mesh with consistent normals refuses it. This removes it on the host (numpy, and
Pillow and scipy through mvtex.py); what it leaves is still not manifold where the shells were joined.

usage:
    shell_strip.py IN.glb --out OUT.glb [--views 512] [--size 256] [--report R.json]
    shell_strip.py --selftest

How a triangle is read (one mesh, one primitive, triangles):
  seen      triangle ids are rendered from --views directions (a Fibonacci sphere, orthographic, the
            bounding sphere filling --size px), both faces drawn; a triangle frontmost in any pixel of
            any view is seen. Seen triangles are always kept.
  partner   from each triangle's centroid a ray runs behind it (along -normal) for 0.006 x the
            largest extent (SHELL_GAP, the mesh_check.py double_shell gap); the first triangle it hits
            facing the other way (normals more than 120 degrees apart) is its back-to-back partner.
  inner     an unseen triangle whose partner is seen: it sits right behind the visible skin, back to
            back with it. Removed.
  the rest  unseen triangles with no seen partner (the skin deep in a crevice, a sub-pixel sliver, the
            inner shell behind them) take the label of the nearest labelled triangle across shared
            edges that do not fold over (adjacent normals less than ~105 degrees apart), outer winning a
            tie: a crevice continues the skin around it, the shell behind it continues the shell.
            Anything still unlabelled is kept and counted (`unresolved`).
A thin flap, a cape or an ear is seen from both sides and kept whole; a notch seen from a few
directions only is kept.

Output: OUT.glb, the same file with only the geometry changed: every vertex attribute (POSITION,
TEXCOORD_0, NORMAL, TANGENT, ...) is cut to the vertices still used and the indices renumbered; the
material, samplers, textures and every image are written byte for byte. Written even when a gate fails
(exit 2): read the report before using it.

Report (gate/1, `--report` and stdout). The checks re-read OUT.glb from disk:
  shell.seen_kept             share of seen triangles still in OUT; >= 1.0 (seen is never removed: this and
                              texture_coverage check the write, the check views check the classification)
  shell.silhouette_iou_min    10 check views that are not among the strip views (yaw 22.5 + 45k at
                              pitch +-15, and pitch -75 and +75; at least CHECK_SIZE px), IoU of the
                              silhouette before and after, the lowest; >= 0.995
  shell.view_match_min        in the same views, share of the silhouette whose frontmost triangle is
                              the same triangle after, the lowest; >= 0.995 (a removed triangle that
                              was visible from a new direction shows here)
  shell.texture_coverage      share of the texels the seen triangles used (UV raster, TEX_RES) that OUT
                              still uses; >= 0.99 (a broken UV write shows here)
  shell.images_identical      every image's bytes are unchanged; true
  shell.removed_share         removed / triangles before; report only
  shell.uv_freed_share        share of the used texels no triangle uses after; report only
  shell.unresolved_share      unlabelled triangles kept / triangles before; report only
Extras: triangles and vertices before and after, seen, inner, unresolved, views, size, gap, seconds.
A file this does not read (no TEXCOORD_0, several meshes or primitives, morph targets, Draco or meshopt,
sparse accessors) is refused: pass false, exit 2.

Needs the mesh-texture-paint skill beside this one (scripts/mvtex.py: the GLB reader and fibonacci_dirs).

Exit codes: 0 every gate passed, 2 a gate failed or the input was refused, 1 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MVTEX_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "mesh-texture-paint", "scripts"))

SHELL_GAP = 0.006          # x largest extent: how far behind a triangle its back-to-back partner may sit
PARTNER_COS = -0.5         # partner normals at least 120 degrees apart
FOLD_COS = -0.25           # a shared edge whose normals turn more than ~105 degrees is a fold: no labels cross
TEX_RES = 1024             # UV raster for the texture gates
CHECK_SIZE = 512           # check views render at least this size
IOU_MIN = 0.995
MATCH_MIN = 0.995
TEXTURE_MIN = 0.99
OUTER, INNER = 1, 2


def _mvtex():
    if MVTEX_DIR not in sys.path:
        sys.path.insert(0, MVTEX_DIR)
    try:
        import mvtex
    except ImportError as e:
        raise SystemExit(f"shell_strip.py: mesh-texture-paint is not installed beside this skill "
                         f"({MVTEX_DIR}): {e}") from None
    return mvtex


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


def gate(name, value, limit, ok, op=None):
    g = {"name": name, "value": value, "limit": limit, "pass": bool(ok)}
    m = gate_margin(value, limit, op)
    if m is not None:
        g["margin"] = m
    return g


def report_only(name, value):
    return {"name": name, "value": value, "limit": None, "pass": True, "report_only": True}


# ----------------------------------------------------------------------------- raster

def raster_ids(xy, z, f, width, height, chunk=2_000_000):
    """Orthographic z-buffer of triangle ids (both faces). xy (n,2) pixel coords, z (n,) depth, nearer
    is smaller. Returns tri (H,W) int64 (-1 empty) and depth (H,W)."""
    p = xy[f].astype(np.float64)
    zz = z[f]
    lo = np.floor(p.min(1)).astype(np.int64)
    hi = np.floor(p.max(1)).astype(np.int64)
    lo = np.maximum(lo, 0)
    hi[:, 0] = np.minimum(hi[:, 0], width - 1)
    hi[:, 1] = np.minimum(hi[:, 1], height - 1)
    a, b, c = p[:, 0], p[:, 1], p[:, 2]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    ext = hi - lo + 1
    ok = (ext > 0).all(1) & (np.abs(area) > 1e-12)
    ids = np.nonzero(ok)[0]
    tri = np.full(width * height, -1, np.int64)
    dep = np.full(width * height, np.inf)
    if not ids.size:
        return tri.reshape(height, width), dep.reshape(height, width)
    bw = 1 << np.ceil(np.log2(ext[ids, 0])).astype(np.int64)
    bh = 1 << np.ceil(np.log2(ext[ids, 1])).astype(np.int64)
    code = bw * (1 << 20) + bh
    order = np.argsort(code, kind="stable")
    ids, code, bw, bh = ids[order], code[order], bw[order], bh[order]
    cuts = np.nonzero(np.diff(code))[0] + 1
    inv_area = np.zeros_like(area)
    inv_area[ok] = 1.0 / area[ok]
    out = []
    for g0, g1 in zip(np.r_[0, cuts], np.r_[cuts, ids.size]):
        g = ids[g0:g1]
        wb, hb = int(bw[g0]), int(bh[g0])
        oy, ox = np.divmod(np.arange(wb * hb), wb)
        step = max(1, chunk // (wb * hb))
        for s0 in range(0, g.size, step):
            t = g[s0:s0 + step]
            px = lo[t, 0, None] + ox[None]
            py = lo[t, 1, None] + oy[None]
            cx, cy = px + 0.5, py + 0.5
            A, B, C = a[t], b[t], c[t]
            ia = inv_area[t][:, None]
            w0 = ((B[:, 0, None] - cx) * (C[:, 1, None] - cy) - (B[:, 1, None] - cy) * (C[:, 0, None] - cx)) * ia
            w1 = ((C[:, 0, None] - cx) * (A[:, 1, None] - cy) - (C[:, 1, None] - cy) * (A[:, 0, None] - cx)) * ia
            w2 = 1 - w0 - w1
            ins = ((w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
                   & (px <= hi[t, 0, None]) & (py <= hi[t, 1, None]))
            ti, si = np.nonzero(ins)
            if not ti.size:
                continue
            tz = zz[t[ti]]
            d = w0[ti, si] * tz[:, 0] + w1[ti, si] * tz[:, 1] + w2[ti, si] * tz[:, 2]
            out.append((py[ti, si] * width + px[ti, si], d, t[ti]))
    if out:
        pix = np.concatenate([o[0] for o in out])
        d = np.concatenate([o[1] for o in out])
        tt = np.concatenate([o[2] for o in out])
        o = np.lexsort((tt, d, pix))
        pix, d, tt = pix[o], d[o], tt[o]
        first = np.ones(pix.size, bool)
        first[1:] = pix[1:] != pix[:-1]
        tri[pix[first]] = tt[first]
        dep[pix[first]] = d[first]
    return tri.reshape(height, width), dep.reshape(height, width)


def ortho_ids(v, f, d, center, radius, size):
    """Triangle ids seen from direction d (unit, from the centre toward the camera)."""
    d = np.asarray(d, float)
    d = d / np.linalg.norm(d)
    fwd = -d
    up = np.array([0.0, 1.0, 0.0]) if abs(d[1]) < 0.99 else np.array([0.0, 0.0, 1.0])
    r = np.cross(fwd, up)
    r /= np.linalg.norm(r)
    u = np.cross(r, fwd)
    q = v - center
    s = size / 2 / (radius * 1.02)
    xy = np.stack([size / 2 + s * np.einsum("ij,j->i", q, r), size / 2 - s * np.einsum("ij,j->i", q, u)], 1)
    return raster_ids(xy, np.einsum("ij,j->i", q, fwd) + 2 * radius, f, size, size)[0]


def check_dirs():
    """10 directions off the Fibonacci strip set: yaw 22.5 + 45k at pitch +15 / -15 alternating, and two
    steep ones (yaw 22.5 pitch -75, yaw 202.5 pitch +75): the inside of a hem, a cuff or a collar is seen
    along the opening's axis only."""
    out = [(22.5 + 45 * k, 15 if k % 2 == 0 else -15) for k in range(8)] + [(22.5, -75), (202.5, 75)]
    return np.array([[math.sin(math.radians(y)) * math.cos(math.radians(p)), math.sin(math.radians(p)),
                      math.cos(math.radians(y)) * math.cos(math.radians(p))] for y, p in out])


def uv_texels(uv, f, res=TEX_RES):
    tri, _ = raster_ids(uv * res, np.ones(len(uv)), f, res, res)
    return tri


# ----------------------------------------------------------------------------- classify

def face_normals(v, f):
    n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)


def behind_partner(v, f, fn, gap):
    """For each triangle, the first triangle hit by a ray from its centroid along -normal within gap that
    faces the other way (-1 when none), and the hit distance."""
    nf = len(f)
    tri = v[f]
    cen = tri.mean(1)
    cell = gap
    lo = np.floor(tri.min(1) / cell).astype(np.int64)
    hi = np.floor(tri.max(1) / cell).astype(np.int64)
    base = np.minimum(lo.min(0), np.floor((cen - fn * gap).min(0) / cell).astype(np.int64)) - 1
    ext = hi - lo + 1
    span = np.maximum(hi.max(0), np.floor((cen + gap).max(0) / cell).astype(np.int64)) - base + 2
    cnt = ext.prod(1)
    owner = np.repeat(np.arange(nf), cnt)
    k = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    ex, ey = ext[owner, 0], ext[owner, 1]
    cx = lo[owner, 0] + k % ex - base[0]
    cy = lo[owner, 1] + (k // ex) % ey - base[1]
    cz = lo[owner, 2] + k // (ex * ey) - base[2]
    keys = (cx * span[1] + cy) * span[2] + cz
    o = np.argsort(keys, kind="stable")
    keys, owner = keys[o], owner[o]
    steps = np.linspace(0.0, 1.0, 9)
    pts = cen[:, None, :] - fn[:, None, :] * (steps[None, :, None] * gap)
    pc = np.floor(pts / cell).astype(np.int64) - base
    qk = (pc[..., 0] * span[1] + pc[..., 1]) * span[2] + pc[..., 2]
    qi = np.repeat(np.arange(nf), len(steps))
    qk = qk.ravel()
    pair = np.unique(qi * (span.prod() + 1) + qk)
    qi, qk = pair // (span.prod() + 1), pair % (span.prod() + 1)
    s0 = np.searchsorted(keys, qk, "left")
    s1 = np.searchsorted(keys, qk, "right")
    n = s1 - s0
    q = np.repeat(qi, n)
    c = owner[np.repeat(s0, n) + (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n))]
    keep = (q != c) & (np.einsum("ij,ij->i", fn[q], fn[c]) < PARTNER_COS)
    q, c = q[keep], c[keep]
    pc2 = np.unique(q.astype(np.int64) * nf + c)
    q, c = pc2 // nf, pc2 % nf
    partner = np.full(nf, -1, np.int64)
    dist = np.full(nf, np.nan)
    if not q.size:
        return partner, dist
    o_, dvec = cen[q], -fn[q]
    a = tri[c, 0]
    e1, e2 = tri[c, 1] - a, tri[c, 2] - a
    h = np.cross(dvec, e2)
    det = np.einsum("ij,ij->i", e1, h)
    good = np.abs(det) > 1e-18
    inv = np.where(good, 1.0 / np.where(good, det, 1.0), 0.0)
    sv = o_ - a
    u = inv * np.einsum("ij,ij->i", sv, h)
    qv = np.cross(sv, e1)
    w = inv * np.einsum("ij,ij->i", dvec, qv)
    t = inv * np.einsum("ij,ij->i", e2, qv)
    eps = 1e-6
    hit = good & (u >= -eps) & (w >= -eps) & (u + w <= 1 + eps) & (t > 0.05 * gap) & (t <= gap)
    q, c, t = q[hit], c[hit], t[hit]
    o = np.lexsort((t, q))
    q, c, t = q[o], c[o], t[o]
    first = np.ones(q.size, bool)
    first[1:] = q[1:] != q[:-1]
    partner[q[first]] = c[first]
    dist[q[first]] = t[first]
    return partner, dist


def smooth_edges(v, f, fn):
    """Triangle pairs sharing a manifold edge (exactly two triangles, vertices welded by position) whose
    normals do not fold over."""
    scale = max(float(np.abs(v).max()), 1e-12)
    _, iv = np.unique(np.round(v / scale, 7), axis=0, return_inverse=True)
    iv = iv.ravel()
    F = iv[f]
    nf = len(f)
    E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
    T = np.tile(np.arange(nf), 3)
    key = E[:, 0].astype(np.int64) * (int(iv.max()) + 1) + E[:, 1]
    o = np.argsort(key, kind="stable")
    ks, ts = key[o], T[o]
    _, st, cnt = np.unique(ks, return_index=True, return_counts=True)
    two = cnt == 2
    A, B = ts[st[two]], ts[st[two] + 1]
    ok = (A != B) & (np.einsum("ij,ij->i", fn[A], fn[B]) > FOLD_COS)
    return A[ok], B[ok]


def classify(v, f, views=512, size=256):
    """Label every triangle OUTER (kept) or INNER (removed); 0 = unresolved (kept)."""
    v = np.asarray(v, np.float64)
    f = np.asarray(f, np.int64)
    nf = len(f)
    mvtex = _mvtex()
    lo, hi = v.min(0), v.max(0)
    center = (lo + hi) / 2
    radius = float(np.linalg.norm(v - center, axis=1).max())
    gap = SHELL_GAP * float((hi - lo).max())
    fn = face_normals(v, f)
    seen = np.zeros(nf, bool)
    for d in mvtex.fibonacci_dirs(views):
        ids = ortho_ids(v, f, d, center, radius, size)
        seen[ids[ids >= 0]] = True
    partner, dist = behind_partner(v, f, fn, gap)
    label = np.where(seen, OUTER, 0)
    has = partner >= 0
    label[(~seen) & has & seen[np.where(has, partner, 0)]] = INNER
    A, B = smooth_edges(v, f, fn)
    while True:
        un = label == 0
        if not un.any():
            break
        new = np.zeros(nf, np.int64)
        for lab in (INNER, OUTER):          # outer written last: it wins a tie
            m1 = (label[A] == lab) & un[B]
            new[B[m1]] = lab
            m2 = (label[B] == lab) & un[A]
            new[A[m2]] = lab
        if not new.any():
            break
        label[new > 0] = new[new > 0]
    return {"label": label, "seen": seen, "partner": partner, "gap": gap, "center": center, "radius": radius,
            "partner_dist_median": float(np.nanmedian(dist)) if has.any() else None}


# ----------------------------------------------------------------------------- GLB write

class Refused(Exception):
    pass


def _read(path):
    mvtex = _mvtex()
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        js, binc = mvtex._glb_chunks(data)
    except (ValueError, struct.error) as e:
        raise Refused(f"not a GLB: {e}") from None
    if js is None:
        raise Refused("no JSON chunk")
    for ext in ("KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_meshopt_compression"):
        if ext in (js.get("extensionsUsed") or []):
            raise Refused(f"compressed geometry ({ext}): decompress first")
    meshes = js.get("meshes") or []
    if len(meshes) != 1 or len(meshes[0].get("primitives") or []) != 1:
        raise Refused("one mesh with one primitive is read; this file has "
                      f"{len(meshes)} meshes / {sum(len(m.get('primitives') or []) for m in meshes)} primitives")
    prim = meshes[0]["primitives"][0]
    if prim.get("mode", 4) != 4:
        raise Refused(f"primitive mode {prim.get('mode')} is not triangles")
    if prim.get("targets"):
        raise Refused("morph targets are not stripped")
    if "indices" not in prim or "TEXCOORD_0" not in prim.get("attributes", {}) or "POSITION" not in prim["attributes"]:
        raise Refused("needs indices, POSITION and TEXCOORD_0")
    for i in list(prim["attributes"].values()) + [prim["indices"]]:
        a = js["accessors"][i]
        if "sparse" in a or "bufferView" not in a:
            raise Refused("sparse accessors are not read")
        if a.get("componentType") not in (5126, 5125, 5123, 5121) or a.get("normalized"):
            raise Refused(f"accessor {i}: component type {a.get('componentType')}"
                          f"{' normalized' if a.get('normalized') else ''} is not read (a quantized mesh)")
    if binc is None:
        raise Refused("no BIN chunk")
    return js, binc


def image_hashes(js, binc):
    out = []
    for im in js.get("images") or []:
        if "bufferView" in im:
            bv = js["bufferViews"][im["bufferView"]]
            o = bv.get("byteOffset", 0)
            out.append(hashlib.sha256(bytes(binc[o:o + bv["byteLength"]])).hexdigest())
        else:
            out.append("uri:" + str(im.get("uri", "")))
    return out


def write_stripped(src, dst, keep):
    """Copy the GLB at src to dst keeping only the triangles where keep is true. Vertex attributes are cut
    to the vertices still used and the indices renumbered; every other buffer view (images) is copied
    byte for byte and nothing else in the JSON changes but accessors, buffer views and the buffer length."""
    mvtex = _mvtex()
    js, binc = _read(src)
    prim = js["meshes"][0]["primitives"][0]
    acc = js["accessors"]
    idx = np.asarray(mvtex._accessor(js, binc, prim["indices"])).astype(np.int64).reshape(-1, 3)
    keep = np.asarray(keep, bool)
    if keep.shape != (len(idx),):
        raise ValueError(f"keep has {keep.shape} entries for {len(idx)} triangles")
    kf = idx[keep]
    used = np.unique(kf)
    remap = np.full(int(idx.max()) + 1 if idx.size else 1, -1, np.int64)
    remap[used] = np.arange(used.size)
    views = js.setdefault("bufferViews", [])
    datas = [bytes(binc[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]) for bv in views]

    def put(acc_i, arr, target):
        views.append({"buffer": 0, "byteLength": arr.nbytes, "target": target})
        datas.append(np.ascontiguousarray(arr).tobytes())
        a = acc[acc_i]
        a["bufferView"] = len(views) - 1
        a.pop("byteOffset", None)
        a["count"] = int(arr.shape[0])
        if "min" in a or "max" in a or acc_i == prim["attributes"]["POSITION"]:
            flat = arr.reshape(arr.shape[0], -1)
            if arr.shape[0]:
                a["min"] = [float(x) if arr.dtype.kind == "f" else int(x) for x in flat.min(0)]
                a["max"] = [float(x) if arr.dtype.kind == "f" else int(x) for x in flat.max(0)]

    done = {}
    for name, ai in prim["attributes"].items():
        if ai in done:
            continue
        arr = np.asarray(mvtex._accessor(js, binc, ai))
        if arr.shape[0] < remap.size:
            raise Refused(f"attribute {name} has {arr.shape[0]} entries for index {remap.size - 1}")
        put(ai, arr[used], 34962)
        done[ai] = name
    ct = acc[prim["indices"]]["componentType"]
    dt = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32}[ct]
    if used.size > np.iinfo(dt).max:
        dt, acc[prim["indices"]]["componentType"] = np.uint32, 5125
    acc[prim["indices"]].pop("min", None)
    acc[prim["indices"]].pop("max", None)
    put(prim["indices"], remap[kf].ravel().astype(dt), 34963)
    # drop buffer views nothing points at any more (the old geometry), renumber the rest
    live = sorted({a["bufferView"] for a in acc if "bufferView" in a}
                  | {im["bufferView"] for im in js.get("images") or [] if "bufferView" in im})
    new_i = {o: n for n, o in enumerate(live)}
    js["bufferViews"] = [views[o] for o in live]
    datas = [datas[o] for o in live]
    for a in acc:
        if "bufferView" in a:
            a["bufferView"] = new_i[a["bufferView"]]
    for im in js.get("images") or []:
        if "bufferView" in im:
            im["bufferView"] = new_i[im["bufferView"]]
    out = bytearray()
    for bv, data in zip(js["bufferViews"], datas):
        while len(out) % 4:
            out.append(0)
        bv["byteOffset"] = len(out)
        bv["byteLength"] = len(data)
        out += data
    while len(out) % 4:
        out.append(0)
    js["buffers"] = [{**(js.get("buffers") or [{}])[0], "byteLength": len(out)}]
    js["buffers"][0].pop("uri", None)
    jb = json.dumps(js, separators=(",", ":")).encode()
    jb += b" " * (-len(jb) % 4)
    with open(dst, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(out)))
        fh.write(struct.pack("<I4s", len(jb), b"JSON") + jb)
        fh.write(struct.pack("<I4s", len(out), b"BIN\x00") + bytes(out))
    return int(used.size)


# ----------------------------------------------------------------------------- run

def strip(src, dst, views=512, size=256):
    """Classify, write dst and measure it. Returns the gate/1 report."""
    mvtex = _mvtex()
    t0 = time.time()
    js, binc = _read(src)
    mesh = mvtex.load_glb(src)
    v, f, uv = mesh.v, mesh.f, mesh.uv
    nv_before = int(len(v))
    cl = classify(v, f, views, size)
    label, seen = cl["label"], cl["seen"]
    keep = label != INNER
    t_cls = time.time() - t0
    write_stripped(src, dst, keep)
    # every check re-reads what was written
    js2, binc2 = _read(dst)
    after = mvtex.load_glb(dst)
    kept_idx = np.nonzero(keep)[0]
    same_rows = (len(after.f) == len(kept_idx)
                 and np.array_equal(after.v[after.f], v[f[kept_idx]])
                 and np.array_equal(after.uv[after.f], uv[f[kept_idx]]))
    seen_kept = float(keep[seen].mean()) if seen.any() else 1.0
    if not same_rows:
        seen_kept = 0.0          # the written triangles are not the kept ones: nothing below can be trusted
    center, radius = cl["center"], cl["radius"]
    ious, matches = [], []
    csize = max(size, CHECK_SIZE)
    for d in check_dirs():
        b = ortho_ids(v, f, d, center, radius, csize)
        a = ortho_ids(after.v, after.f, d, center, radius, csize)
        a_orig = np.where(a >= 0, kept_idx[np.maximum(a, 0)] if len(kept_idx) else -1, -1)
        mb, ma = b >= 0, a >= 0
        ious.append(float((mb & ma).sum() / max((mb | ma).sum(), 1)))
        matches.append(float((a_orig[mb] == b[mb]).sum() / max(mb.sum(), 1)))
    tex_seen = uv_texels(uv, f[seen]) >= 0 if seen.any() else np.zeros((TEX_RES, TEX_RES), bool)
    tex_all = uv_texels(uv, f) >= 0
    tex_after = uv_texels(after.uv, after.f) >= 0 if len(after.f) else np.zeros_like(tex_all)
    coverage = float((tex_seen & tex_after).sum() / max(tex_seen.sum(), 1))
    freed = float(1 - (tex_after & tex_all).sum() / max(tex_all.sum(), 1))
    h_before, h_after = image_hashes(js, binc), image_hashes(js2, binc2)
    images_same = h_before == h_after
    nf = len(f)
    gates = [
        gate("shell.seen_kept", round(seen_kept, 6), ">= 1.0", seen_kept >= 1.0),
        gate("shell.silhouette_iou_min", round(min(ious), 5), f">= {IOU_MIN}", min(ious) >= IOU_MIN),
        gate("shell.view_match_min", round(min(matches), 5), f">= {MATCH_MIN}", min(matches) >= MATCH_MIN),
        gate("shell.texture_coverage", round(coverage, 5), f">= {TEXTURE_MIN}", coverage >= TEXTURE_MIN),
        gate("shell.images_identical", images_same, True, images_same),
        report_only("shell.removed_share", round(float((~keep).mean()), 4)),
        report_only("shell.uv_freed_share", round(freed, 4)),
        report_only("shell.unresolved_share", round(float((label == 0).mean()), 4)),
    ]
    ok = all(g["pass"] for g in gates)
    return {
        "schema": "gate/1", "tool": "shell_strip", "pass": ok, "verdict": "green" if ok else "failed",
        "gates": gates, "input": os.path.abspath(src), "output": os.path.abspath(dst),
        "triangles_before": nf, "triangles_after": int(keep.sum()),
        "vertices_before": nv_before, "vertices_after": int(len(after.v)),
        "seen": int(seen.sum()), "inner": int((label == INNER).sum()), "unresolved": int((label == 0).sum()),
        "views": views, "size": size, "check_size": csize, "gap": round(cl["gap"], 6),
        "partner_dist_median": None if cl["partner_dist_median"] is None else round(cl["partner_dist_median"], 6),
        "silhouette_iou": [round(x, 5) for x in ious], "view_match": [round(x, 5) for x in matches],
        "seconds": {"classify": round(t_cls, 1), "total": round(time.time() - t0, 1)},
    }


def refused_report(src, why):
    return {"schema": "gate/1", "tool": "shell_strip", "pass": False, "verdict": "failed", "gates": [],
            "input": os.path.abspath(src), "refused": why}


# ----------------------------------------------------------------------------- selftest fixtures

def grid_box(lo, hi, n=4, inward=False):
    """A closed box tessellated n x n per face, outward winding (inward=True flips it)."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    V, F = [], []
    for axis in range(3):
        for side in (0, 1):
            a1, a2 = [x for x in range(3) if x != axis]
            base = len(V)
            for i in range(n + 1):
                for j in range(n + 1):
                    p = np.empty(3)
                    p[axis] = hi[axis] if side else lo[axis]
                    p[a1] = lo[a1] + (hi[a1] - lo[a1]) * i / n
                    p[a2] = lo[a2] + (hi[a2] - lo[a2]) * j / n
                    V.append(p)
            for i in range(n):
                for j in range(n):
                    q = [base + i * (n + 1) + j, base + (i + 1) * (n + 1) + j,
                         base + (i + 1) * (n + 1) + j + 1, base + i * (n + 1) + j + 1]
                    F += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    V, F = np.array(V), np.array(F)
    n_ = face_normals(V, F)
    out = np.einsum("ij,ij->i", n_, V[F].mean(1) - (lo + hi) / 2) > 0
    F[~out] = F[~out][:, ::-1]
    if inward:
        F = F[:, ::-1]
    return V, F


def voxel_surface(filled, h=0.1):
    """Boundary quads of a voxel solid (shared corner vertices), outward winding, and vertex normals."""
    nx, ny, nz = filled.shape
    pad = np.pad(filled, 1)
    verts, F = {}, []

    def vid(p):
        if p not in verts:
            verts[p] = len(verts)
        return verts[p]
    for (i, j, k) in zip(*np.nonzero(filled)):
        for axis in range(3):
            for s in (-1, 1):
                nb = [i + 1, j + 1, k + 1]
                nb[axis] += s
                if pad[tuple(nb)]:
                    continue
                a1, a2 = [x for x in range(3) if x != axis]
                corners = []
                for du, dv in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    c = [i, j, k]
                    c[axis] += 1 if s > 0 else 0
                    c[a1] += du
                    c[a2] += dv
                    corners.append(vid(tuple(c)))
                F += [(corners[0], corners[1], corners[2]), (corners[0], corners[2], corners[3])]
    V = np.zeros((len(verts), 3))
    for p, n in verts.items():
        V[n] = p
    V *= h
    F = np.array(F)
    # orient outward: the face normal points from the filled voxel to the empty one
    cen = V[F].mean(1)
    fn = face_normals(V, F)
    probe = np.floor((cen - fn * h * 0.5) / h).astype(int) + 1
    inside = pad[tuple(np.clip(probe, 0, np.array(pad.shape) - 1).T)]
    F[~inside] = F[~inside][:, ::-1]
    fn = face_normals(V, F)
    vn = np.zeros_like(V)
    np.add.at(vn, F.ravel(), np.repeat(fn, 3, axis=0))
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
    return V, F, vn


def with_inner(V, F, vn, offset):
    """The surface plus an inward-facing copy `offset` behind it (Pixal3D's inner shell)."""
    Vi = V - vn * offset
    return np.vstack([V, Vi]), np.vstack([F, F[:, ::-1] + len(V)]), len(F)


def box_uv(V):
    """A simple planar UV per vertex (only so the GLB has TEXCOORD_0)."""
    lo, hi = V.min(0), V.max(0)
    q = (V - lo) / np.maximum(hi - lo, 1e-9)
    return np.stack([0.02 + 0.96 * (q[:, 0] * 0.5 + q[:, 2] * 0.5), 0.02 + 0.96 * q[:, 1]], 1)


def pixal_like_glb(V, F, uv, path, split_uv=None):
    """A GLB laid out like an image-to-3D file: POSITION, indices, TEXCOORD_0, NORMAL, TANGENT, three
    embedded images, a sampler, a doubleSided material."""
    import io
    from PIL import Image
    nrm = np.zeros_like(V)
    np.add.at(nrm, F.ravel(), np.repeat(face_normals(V, F), 3, axis=0))
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    tan = np.concatenate([np.tile([1.0, 0, 0], (len(V), 1)), np.ones((len(V), 1))], 1)
    imgs = []
    for k, col in enumerate(((200, 120, 60), (255, 255, 255), (128, 128, 255))):
        b = io.BytesIO()
        im = Image.new("RGB", (64, 64), col)
        im.putpixel((k, k), (k, 0, 0))
        im.save(b, "PNG")
        imgs.append(b.getvalue())
    blobs = [(V.astype(np.float32).tobytes(), 34962), (F.astype(np.uint32).ravel().tobytes(), 34963),
             (uv.astype(np.float32).tobytes(), 34962), (nrm.astype(np.float32).tobytes(), 34962),
             (tan.astype(np.float32).tobytes(), 34962)] + [(b, None) for b in imgs]
    out, views = bytearray(), []
    for b, target in blobs:
        while len(out) % 4:
            out.append(0)
        bv = {"buffer": 0, "byteOffset": len(out), "byteLength": len(b)}
        if target:
            bv["target"] = target
        views.append(bv)
        out += b
    while len(out) % 4:
        out.append(0)
    p32 = V.astype(np.float32)
    js = {
        "asset": {"version": "2.0", "generator": "shell_strip selftest"}, "buffers": [{"byteLength": len(out)}],
        "bufferViews": views,
        "accessors": [
            {"bufferView": 0, "byteOffset": 0, "componentType": 5126, "count": len(V), "type": "VEC3",
             "max": p32.max(0).tolist(), "min": p32.min(0).tolist()},
            {"bufferView": 1, "byteOffset": 0, "componentType": 5125, "count": int(F.size), "type": "SCALAR"},
            {"bufferView": 2, "byteOffset": 0, "componentType": 5126, "count": len(V), "type": "VEC2"},
            {"bufferView": 3, "byteOffset": 0, "componentType": 5126, "count": len(V), "type": "VEC3"},
            {"bufferView": 4, "byteOffset": 0, "componentType": 5126, "count": len(V), "type": "VEC4"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 2, "NORMAL": 3, "TANGENT": 4},
                                    "indices": 1, "mode": 4, "material": 0}]}],
        "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0,
        "images": [{"bufferView": 5 + k, "mimeType": "image/png"} for k in range(3)],
        "samplers": [{"magFilter": 9729, "minFilter": 9729, "wrapS": 33071, "wrapT": 33071}],
        "textures": [{"source": k, "sampler": 0} for k in range(3)],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0, "texCoord": 0},
                                                "metallicRoughnessTexture": {"index": 1, "texCoord": 0}},
                       "doubleSided": True, "normalTexture": {"index": 2, "texCoord": 0}}],
    }
    jb = json.dumps(js, separators=(",", ":")).encode()
    jb += b" " * (-len(jb) % 4)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(out)))
        fh.write(struct.pack("<I4s", len(jb), b"JSON") + jb)
        fh.write(struct.pack("<I4s", len(out), b"BIN\x00") + bytes(out))


def contract_sample(script, case, doc, suffix=".gate.json"):
    out = os.environ.get("UNITY_DEV_CONTRACT_OUT") or os.path.join(tempfile.gettempdir(), "unity-dev-contract-out")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{script}__{case}{suffix}")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1)
    print(f"selftest-output: {path}")


def selftest():
    mvtex = _mvtex()
    results, failed = {}, []

    def check(name, cond, detail=None):
        results[name] = {"pass": bool(cond), **({"detail": detail} if detail is not None else {})}
        if not cond:
            failed.append(name)

    off = 0.003   # shell spacing on a unit-sized mesh: under SHELL_GAP x extent
    # 1. a double-shell box: the inner copy removed, the outer kept
    Vo, Fo = grid_box([-0.5, -0.5, -0.3], [0.5, 0.5, 0.3], n=6)
    Vi, Fi = grid_box([-0.5 + off, -0.5 + off, -0.3 + off], [0.5 - off, 0.5 - off, 0.3 - off], n=6, inward=True)
    V = np.vstack([Vo, Vi])
    F = np.vstack([Fo, Fi + len(Vo)])
    no = len(Fo)
    cl = classify(V, F, views=48, size=160)
    lab = cl["label"]
    check("double box: every outer triangle kept", (lab[:no] != INNER).all(), int((lab[:no] == INNER).sum()))
    check("double box: every inner triangle removed", (lab[no:] == INNER).all(), int((lab[no:] != INNER).sum()))
    # 2. the same, welded at one edge: the inner box's edge vertices moved onto the outer's and shared
    Vw, Fw = V.copy(), F.copy()
    edge_o = np.nonzero((np.abs(Vo[:, 0] - 0.5) < 1e-9) & (np.abs(Vo[:, 1] - 0.5) < 1e-9))[0]
    edge_i = np.nonzero((np.abs(Vi[:, 0] - (0.5 - off)) < 1e-9) & (np.abs(Vi[:, 1] - (0.5 - off)) < 1e-9))[0]
    for vi in edge_i:
        j = edge_o[np.argmin(np.abs(Vo[edge_o, 2] - Vi[vi, 2]))]
        Fw[Fw == vi + len(Vo)] = j
    clw = classify(Vw, Fw, views=48, size=160)
    lw = clw["label"]
    check("welded box: every outer triangle kept", (lw[:no] != INNER).all(), int((lw[:no] == INNER).sum()))
    check("welded box: >= 95% of the inner shell removed", (lw[no:] == INNER).mean() >= 0.95,
          round(float((lw[no:] == INNER).mean()), 3))
    # 3. a thin flap: a slab 0.003 thick (two back-to-back faces) and a single open sheet, both seen
    #    from both sides, beside a double-shell body: kept whole
    Vs, Fs = grid_box([0.7, -0.4, -0.0015], [1.3, 0.4, 0.0015], n=6)
    gx, gy = np.meshgrid(np.linspace(-1.3, -0.7, 7), np.linspace(-0.4, 0.4, 7), indexing="ij")
    Vsh = np.stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)], 1)
    Fsh = []
    for i in range(6):
        for j in range(6):
            a, b, c, d = i * 7 + j, (i + 1) * 7 + j, (i + 1) * 7 + j + 1, i * 7 + j + 1
            Fsh += [(a, b, c), (a, c, d)]
    Fsh = np.array(Fsh)
    V3 = np.vstack([V, Vs, Vsh])
    F3 = np.vstack([F, Fs + len(V), Fsh + len(V) + len(Vs)])
    cl3 = classify(V3, F3, views=48, size=200)
    l3 = cl3["label"]
    flap = slice(len(F), len(F3))
    check("thin slab and open sheet: nothing removed", (l3[flap] != INNER).all(), int((l3[flap] == INNER).sum()))
    check("thin slab and open sheet: the body's inner shell still removed", (l3[no:len(F)] == INNER).all())
    # 4. a blind well seen from few directions: its walls and floor kept, the shell behind them removed
    solid = np.ones((10, 10, 10), bool)
    solid[4:6, 3:, 4:6] = False
    Vn, Fn, vn = voxel_surface(solid, h=0.1)
    Vn = Vn - Vn.mean(0)
    V4, F4, n_out = with_inner(Vn, Fn, vn, off)
    cl4 = classify(V4, F4, views=24, size=160)
    l4, s4 = cl4["label"], cl4["seen"]
    cen4 = V4[F4[:n_out]].mean(1)
    well = (np.abs(cen4[:, 0]) < 0.1 + 1e-9) & (np.abs(cen4[:, 2]) < 0.1 + 1e-9) & (cen4[:, 1] < 0.5 - 1e-9)
    check("well: some of its surface unseen at 24 views", (~s4[:n_out][well]).any(),
          int((~s4[:n_out][well]).sum()))
    check("well: every outer triangle kept", (l4[:n_out] != INNER).all(), int((l4[:n_out] == INNER).sum()))
    check("well: >= 95% of the inner shell removed", (l4[n_out:] == INNER).mean() >= 0.95,
          round(float((l4[n_out:] == INNER).mean()), 3))
    # 5. end to end on an image-to-3D-shaped GLB: gates, byte-identical images, attributes cut together
    with tempfile.TemporaryDirectory() as td:
        src, dst = os.path.join(td, "in.glb"), os.path.join(td, "out.glb")
        uv = box_uv(V)
        uv[len(Vo):, 0] = uv[len(Vo):, 0] * 0.5           # the inner shell on its own UV island
        uv[:len(Vo), 0] = 0.5 + uv[:len(Vo), 0] * 0.5
        pixal_like_glb(V, F, uv, src)
        rep = strip(src, dst, views=48, size=160)
        g = {x["name"]: x for x in rep["gates"]}
        check("glb: report passes", rep["pass"], {k: x["value"] for k, x in g.items()})
        check("glb: inner shell removed, outer kept", rep["triangles_after"] == no and rep["inner"] == len(F) - no,
              [rep["triangles_after"], rep["inner"]])
        check("glb: silhouette IoU 1", g["shell.silhouette_iou_min"]["value"] == 1.0, g["shell.silhouette_iou_min"]["value"])
        check("glb: images byte-identical", g["shell.images_identical"]["value"] is True)
        check("glb: about half the UV space freed", 0.4 < g["shell.uv_freed_share"]["value"] < 0.6,
              g["shell.uv_freed_share"]["value"])
        js_a, bin_a = _read(dst)
        acc = js_a["accessors"]
        prim = js_a["meshes"][0]["primitives"][0]
        counts = {k: acc[i]["count"] for k, i in prim["attributes"].items()}
        nrm_a = np.asarray(mvtex._accessor(js_a, bin_a, prim["attributes"]["NORMAL"]))
        pos_a = np.asarray(mvtex._accessor(js_a, bin_a, prim["attributes"]["POSITION"]))
        js_b, bin_b = _read(src)
        pb = js_b["meshes"][0]["primitives"][0]
        nrm_b = np.asarray(mvtex._accessor(js_b, bin_b, pb["attributes"]["NORMAL"]))
        check("glb: every attribute cut to the same vertices", len(set(counts.values())) == 1
              and counts["POSITION"] == len(Vo), counts)
        check("glb: normals follow their vertices", np.array_equal(nrm_a, nrm_b[:len(Vo)])
              and np.allclose(pos_a, Vo.astype(np.float32)))
        check("glb: POSITION min/max rewritten", np.allclose(acc[prim["attributes"]["POSITION"]]["min"], pos_a.min(0)))
        check("glb: material, textures and samplers unchanged",
              all(js_a[k] == js_b[k] for k in ("materials", "textures", "samplers"))
              and [{**i, "bufferView": 0} for i in js_a["images"]] == [{**i, "bufferView": 0} for i in js_b["images"]])
        img = mvtex.glb_image(dst)
        check("glb: mvtex reads the base colour", img.size == (64, 64))
        # 5b. planted: a classifier that also removes every 7th seen triangle fails the gates, exit 2
        real = globals()["classify"]

        def planted(*a, **k):
            out = real(*a, **k)
            hit = np.nonzero(out["seen"])[0][::7]
            out["label"] = out["label"].copy()
            out["label"][hit] = INNER
            return out
        globals()["classify"] = planted
        try:
            bad_out, bad_rep = os.path.join(td, "planted.glb"), os.path.join(td, "planted.json")
            code = _exit_code([src, "--out", bad_out, "--report", bad_rep, "--views", "48", "--size", "160"])
        finally:
            globals()["classify"] = real
        gb = {x["name"]: x for x in json.load(open(bad_rep))["gates"]}
        check("planted: seen triangles removed fail seen_kept, silhouette and view match, exit 2",
              code == 2 and not gb["shell.seen_kept"]["pass"] and not gb["shell.silhouette_iou_min"]["pass"]
              and not gb["shell.view_match_min"]["pass"] and gb["shell.view_match_min"]["margin"] < 0,
              [code] + [gb[n]["value"] for n in ("shell.seen_kept", "shell.silhouette_iou_min", "shell.view_match_min")])
        # 6. nothing to strip: a single box comes back whole
        src2, dst2 = os.path.join(td, "one.glb"), os.path.join(td, "one_out.glb")
        pixal_like_glb(Vo, Fo, box_uv(Vo), src2)
        rep2 = strip(src2, dst2, views=32, size=128)
        check("single shell: nothing removed", rep2["pass"] and rep2["triangles_after"] == len(Fo), rep2["triangles_after"])
        # 7. a refused input and the CLI
        bad = os.path.join(td, "bad.glb")
        with open(bad, "wb") as fh:
            fh.write(b"not a glb at all")
        check("refused: not a GLB exits 2", _exit_code([bad, "--out", os.path.join(td, "x.glb"),
                                                        "--report", os.path.join(td, "x.json")]) == 2
              and json.load(open(os.path.join(td, "x.json")))["refused"].startswith("not a GLB"))
        check("cli: unknown flag exits 1", _exit_code([src, "--out", dst, "--bogus"]) == 1)
        check("cli: missing --out exits 1", _exit_code([src]) == 1)
        check("cli: --views 0 exits 1", _exit_code([src, "--out", dst, "--views", "0"]) == 1)
        check("report: no ok key, numeric gates carry margin",
              all("ok" not in x for x in rep["gates"]) and "ok" not in rep
              and all("margin" in x for x in rep["gates"] if isinstance(x["value"], float) and x["limit"] is not None))
        contract_sample("shell_strip", "double_box", rep)
    print(json.dumps({"selftest": "pass" if not failed else "fail", "failed": failed, "checks": results}, indent=1))
    return 0 if not failed else 2


# ----------------------------------------------------------------------------- cli

class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1, never 2: here 2 is a gate verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _positive(lo):
    def conv(s):
        try:
            x = int(s)
        except ValueError:
            raise argparse.ArgumentTypeError(f"not an integer: {s}") from None
        if x < lo:
            raise argparse.ArgumentTypeError(f"must be >= {lo}")
        return x
    return conv


def parser():
    p = UsageParser(prog="shell_strip.py", description=__doc__.split("\n")[0],
                    formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mesh", nargs="?", help="IN.glb")
    p.add_argument("--out", help="OUT.glb")
    p.add_argument("--views", type=_positive(8), default=512, help="strip view directions (default 512)")
    p.add_argument("--size", type=_positive(64), default=256, help="strip render size in px (default 256)")
    p.add_argument("--report", help="write the gate/1 report here too")
    p.add_argument("--selftest", action="store_true")
    return p


def _exit_code(argv):
    import contextlib
    import io
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            return main(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1


def main(argv=None):
    p = parser()
    a = p.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.mesh or not a.out:
        p.error("IN.glb and --out OUT.glb are required")
    if not os.path.isfile(a.mesh):
        p.error(f"no such file: {a.mesh}")
    if os.path.abspath(a.mesh) == os.path.abspath(a.out):
        p.error("--out must not be the input")
    try:
        rep = strip(a.mesh, a.out, a.views, a.size)
    except Refused as e:
        rep = refused_report(a.mesh, str(e))
    text = json.dumps(rep, indent=1)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    if argv is None:
        print(text)
    return 0 if rep["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
