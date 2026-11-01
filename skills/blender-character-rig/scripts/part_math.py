#!/usr/bin/env python3
"""part_math.py — the geometry of a character built from parts: the parts plan, the neck band, registration, the hair split.

A part (the head) is generated as its own image-to-3D job and put back onto the whole-body anchor.
This module measures the anchor and writes the plan (`plan`), and holds the numpy geometry the
assembly runs inside Blender (`assemble_parts.py`): slicing, the neck band, trimmed similarity ICP,
the inner-shell test, silhouettes, ray tests, the hair split and the seam colour match. Every function the assembly calls
is numpy only (stock Blender has numpy, not scipy or PIL); PIL is imported only by `plan`, to read
the clean view masks.

usage:
    part_math.py plan ANCHOR.glb --views CLEAN_DIR --tier three --character runner
                      --out ArtDirection/parts/runner/runner.parts.json [--margin-frac 0.1] [--band-step 0.002]
                      [--painted ANCHOR_painted.glb] [--hood-grow 0.08]
    part_math.py --selftest

`plan` writes a parts/1 plan (schemas/parts-1.json): the tier's parts, the anchor's neck band, collar
and head height, the seam heights, the frame fit of the anchor onto the clean views (one scale, an
offset per view, the silhouette IoU), each generated part's crop box per view and its keep masks
(`views/<part>/keep_<view>.png`: the view mask where the anchor's part region is the surface nearest
the camera, minus every other surface the view sees, grown upward by --hood-grow x head height, so a
hood in front of or behind the neck is removed by geometry, never by colour). A covered neck (the ring
goes on below the band, no wider, nested: a stand collar fused to the jaw) is reported (anchor.neck.covered,
`warnings`): the part's neck reaches the cover's foot and the column is dropped from the keep masks
without growing. Hair hanging below the cut outside the neck (a ponytail) is kept in the views
(views.hanging, `hang_<view>.png`). --painted records the S3b repaint as anchor.painted_glb (the
assembly takes it). CLEAN_DIR holds the cleaned views' masks,
`*front*mask*.png` and likewise for left, back and right. Coordinates are the anchor GLB's own
frame: +Y up, the character facing +Z (the `front` view); a view maps a point to px = cx + u / units_per_px, row = cy - y / units_per_px with
u = x (front), -x (back), -z (left), +z (right).

Tiers: `whole` (the anchor alone, no plan needed), `three` (body = the anchor, head = one generated
job, hair = split from the head), `fine` (three plus parts from FINE_REGIONS: the hands are measured by
hand_parts.py, same folder; eyeballs come from eye_fit.py, not the plan, and `eyes` / `accessory` parts are refused). `custom` is a reserved name: refused here ("reserved, not built yet").

Exit codes: 0 done (or --selftest passed); 1 usage error, refused input or a failed --selftest;
2 a measurement gate failed (no clean neck band: a raised hood or a helmet; a frame-fit IoU under
0.90: the views are not the anchor's); 3 an unreadable file. Arguments are parsed before numpy or
PIL is imported.
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
import zlib

try:
    import numpy as np
except ImportError:          # the usage probe runs without numpy; every command needs it
    np = None

VIEWS = ("front", "left", "back", "right")
VIEW_PX = 1024
REGIONS = ("body", "head", "hair", "hand.L", "hand.R", "eyes", "accessory")
REGIONS_NOW = ("body", "head", "hair")
FINE_REGIONS = ("hand.L", "hand.R")     # tier fine: three plus any of these (eyeballs: eye_fit.py, no plan part)
UNBUILT_REGIONS = ("eyes", "accessory")
PRESETS = ("Small", "Medium", "Compact", "Large", "Template", "Showcase")
TIERS = {
    "whole": [{"name": "body", "source": "anchor", "region": "body", "budget_share": 1.0}],
    "three": [{"name": "body", "source": "anchor", "region": "body", "budget_share": 0.6},
              {"name": "head", "source": "generate", "region": "head", "preset": "Template", "budget_share": 0.25},
              {"name": "hair", "source": "split", "from": "head", "region": "hair",
               "split": {"method": "scalp-radius", "delta": 0.03}, "budget_share": 0.15}],
    "fine": [{"name": "body", "source": "anchor", "region": "body", "budget_share": 0.46},
             {"name": "head", "source": "generate", "region": "head", "preset": "Template", "budget_share": 0.22},
             {"name": "hair", "source": "split", "from": "head", "region": "hair",
              "split": {"method": "scalp-radius", "delta": 0.03}, "budget_share": 0.12},
             {"name": "hand_r", "source": "generate", "region": "hand.R", "preset": "Template", "budget_share": 0.08,
              "attach": {"mode": "replace"}},
             {"name": "hand_l", "source": "generate", "region": "hand.L", "preset": "Template", "budget_share": 0.08,
              "attach": {"mode": "replace"}}],
}
RESERVED_TIERS = ("custom",)
FRAME_IOU_MIN = 0.90
HIDE_FAN_DEG = (0, -35, 35, -70, 70)     # tuck_band: covered = every ray of this horizontal fan meets the hide
COVERED_MIN = 0.1          # neck_band: the ring goes on below the band, nested, this many head heights: a covered neck


class Refused(Exception):
    """Input the tools will not take (exit 1)."""


class GateFailed(Exception):
    """A measurement gate failed (exit 2)."""


# ---------------------------------------------------------------------------------------------- glb io
_CT = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _parse_glb(path):
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:4] != b"glTF":
        raise ValueError(f"{path} is not a binary glTF")
    gltf, binary, off = None, b"", 12
    while off + 8 <= len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            gltf = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            binary = chunk
        off += 8 + clen + (-clen % 4)
    if gltf is None:
        raise ValueError(f"{path} has no JSON chunk")
    return gltf, binary


def _accessor(gltf, binary, index):
    acc = gltf["accessors"][index]
    if "sparse" in acc:
        raise Refused("sparse accessors are not read; re-export without them")
    view = gltf["bufferViews"][acc["bufferView"]]
    dt = np.dtype(_CT[acc["componentType"]])
    n = _NC[acc["type"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride", 0)
    count = acc["count"]
    if stride and stride != dt.itemsize * n:
        raw = np.frombuffer(binary, dtype=np.uint8, count=stride * count, offset=start).reshape(count, stride)
        return raw[:, : dt.itemsize * n].copy().view(dt).reshape(count, n)
    return np.frombuffer(binary, dtype=dt, count=count * n, offset=start).reshape(count, n).copy()


def _node_matrix(node):
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    t = np.eye(4)
    t[:3, 3] = node.get("translation", [0, 0, 0])
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    r = np.eye(4)
    r[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                 [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                 [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    s = np.diag(list(node.get("scale", [1, 1, 1])) + [1.0])
    return t @ r @ s


def read_glb(path):
    """{V (n,3) with node transforms applied, F (m,3), UV (n,2), image (bytes of the first base-colour
    texture or None)}. Refuses Draco, meshopt and sparse accessors, as mesh_check.py does."""
    gltf, binary = _parse_glb(path)
    used = set(gltf.get("extensionsUsed", []))
    for ext in ("KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_meshopt_compression"):
        if ext in used:
            raise Refused(f"{path} uses {ext}; export it uncompressed")
    mats = {}

    def walk(index, parent):
        node = gltf["nodes"][index]
        m = parent @ _node_matrix(node)
        if "mesh" in node:
            mats.setdefault(node["mesh"], m)
        for child in node.get("children", []):
            walk(child, m)

    scene = gltf.get("scenes", [{}])[gltf.get("scene", 0)]
    for index in scene.get("nodes", range(len(gltf.get("nodes", [])))):
        walk(index, np.eye(4))
    vs, fs, uvs, image, off = [], [], [], None, 0
    for mi, mesh in enumerate(gltf.get("meshes", [])):
        m = mats.get(mi, np.eye(4))
        for prim in mesh["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            v = _accessor(gltf, binary, prim["attributes"]["POSITION"]).astype(np.float64)
            v = v @ m[:3, :3].T + m[:3, 3]
            f = (_accessor(gltf, binary, prim["indices"]).reshape(-1, 3).astype(np.int64) if "indices" in prim
                 else np.arange(len(v)).reshape(-1, 3))
            uv = (_accessor(gltf, binary, prim["attributes"]["TEXCOORD_0"]).astype(np.float64)
                  if "TEXCOORD_0" in prim["attributes"] else np.zeros((len(v), 2)))
            vs.append(v)
            fs.append(f + off)
            uvs.append(uv)
            off += len(v)
            if image is None and "material" in prim:
                pbr = gltf["materials"][prim["material"]].get("pbrMetallicRoughness", {})
                tex = pbr.get("baseColorTexture")
                if tex is not None:
                    img = gltf["images"][gltf["textures"][tex["index"]]["source"]]
                    if "bufferView" in img:
                        bv = gltf["bufferViews"][img["bufferView"]]
                        s = bv.get("byteOffset", 0)
                        image = binary[s: s + bv["byteLength"]]
    if not vs:
        raise ValueError(f"{path} has no triangle mesh")
    return {"V": np.vstack(vs), "F": np.vstack(fs), "UV": np.vstack(uvs), "image": image}


def write_glb(path, V, F, UV=None):
    """A minimal GLB (one mesh, positions, indices, optional UVs, no material): selftest fixtures."""
    V = np.asarray(V, np.float32)
    F = np.asarray(F, np.uint32)
    blobs = [V.tobytes(), F.tobytes()]
    acc = [{"bufferView": 0, "componentType": 5126, "count": len(V), "type": "VEC3",
            "min": V.min(0).tolist(), "max": V.max(0).tolist()},
           {"bufferView": 1, "componentType": 5125, "count": F.size, "type": "SCALAR"}]
    attrs = {"POSITION": 0}
    if UV is not None:
        blobs.append(np.asarray(UV, np.float32).tobytes())
        acc.append({"bufferView": 2, "componentType": 5126, "count": len(V), "type": "VEC2"})
        attrs["TEXCOORD_0"] = 2
    views, off, body = [], 0, b""
    for blob in blobs:
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(blob)})
        pad = blob + b"\0" * (-len(blob) % 4)
        body += pad
        off += len(pad)
    gltf = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
            "meshes": [{"primitives": [{"attributes": attrs, "indices": 1}]}], "accessors": acc,
            "bufferViews": views, "buffers": [{"byteLength": len(body)}]}
    js = json.dumps(gltf).encode()
    js += b" " * (-len(js) % 4)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(body))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(body), 0x004E4942) + body
    with open(path, "wb") as handle:
        handle.write(out)


def write_png_gray(path, mask):
    """An 8-bit greyscale PNG from a boolean or uint8 array, without PIL (runs inside Blender)."""
    a = np.asarray(mask)
    a = (a.astype(np.uint8) * 255) if a.dtype == bool else a.astype(np.uint8)
    h, w = a.shape
    raw = b"".join(b"\0" + a[r].tobytes() for r in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(png)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------------------------- mesh basics
def weld(V, F, tol=1e-5):
    """(V welded by position, F re-indexed, map old vertex -> welded vertex)."""
    q = np.round(np.asarray(V) / tol).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    return np.asarray(V)[first], inv[np.asarray(F)], inv


def face_normals(V, F):
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    a = np.linalg.norm(n, axis=1)
    return n / np.maximum(a, 1e-30)[:, None], 0.5 * a


def edge_face_pairs(F):
    """(a, b): faces that share an edge (welded indices)."""
    m = len(F)
    e = np.sort(np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    key = e[:, 0] * (int(F.max()) + 1 if m else 1) + e[:, 1]
    fid = np.tile(np.arange(m), 3)
    order = np.argsort(key, kind="stable")
    k, f = key[order], fid[order]
    same = k[1:] == k[:-1]
    return f[:-1][same], f[1:][same]


def components(n, a, b):
    """Connected components over n nodes joined by the pairs (a, b): labels 0..k-1, by union-find with
    pointer jumping, all in numpy."""
    lab = np.arange(n)
    a = np.asarray(a, np.int64)
    b = np.asarray(b, np.int64)
    while True:
        la, lb = lab[a], lab[b]
        diff = la != lb
        if not diff.any():
            break
        lo = np.minimum(la[diff], lb[diff])
        hi = np.maximum(la[diff], lb[diff])
        np.minimum.at(lab, hi, lo)
        while True:
            nxt = lab[lab]
            if np.array_equal(nxt, lab):
                break
            lab = nxt
    return np.unique(lab, return_inverse=True)[1].reshape(-1)


def face_components(F, mask=None):
    """Face labels over shared edges (F welded); faces outside mask get -1."""
    m = len(F)
    mask = np.ones(m, bool) if mask is None else np.asarray(mask, bool)
    a, b = edge_face_pairs(F)
    keep = mask[a] & mask[b]
    idx = np.nonzero(mask)[0]
    pos = np.full(m, -1)
    pos[idx] = np.arange(len(idx))
    lab = components(len(idx), pos[a[keep]], pos[b[keep]])
    out = np.full(m, -1)
    out[idx] = lab
    return out


def sample_surface(V, F, n, rng, face_mask=None):
    """n points on the faces (area-weighted): (points, normals, face ids)."""
    fn, area = face_normals(V, F)
    pool = np.arange(len(F)) if face_mask is None else np.nonzero(face_mask)[0]
    p = area[pool] / area[pool].sum()
    fi = rng.choice(pool, size=n, p=p)
    r1, r2 = rng.random(n), rng.random(n)
    s = np.sqrt(r1)
    w = np.c_[1 - s, s * (1 - r2), s * r2]
    pts = (V[F[fi]] * w[:, :, None]).sum(1)
    return pts, fn[fi], fi


# ---------------------------------------------------------------------------------------- slicing
def _poly_area(p):
    return 0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def _hull_area(p):
    pts = sorted(set(map(tuple, np.round(p, 9))))
    if len(pts) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for q in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    for q in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return abs(_poly_area(np.array(lower[:-1] + upper[:-1])))


def point_in_poly(pts, poly):
    """Even-odd test of points (k,2) against one polygon (n,2)."""
    pts = np.atleast_2d(pts)
    x, y = pts[:, 0][:, None], pts[:, 1][:, None]
    xi, yi = poly[:, 0][None], poly[:, 1][None]
    xj, yj = np.roll(poly[:, 0], 1)[None], np.roll(poly[:, 1], 1)[None]
    cond = (yi > y) != (yj > y)
    xc = (xj - xi) * (y - yi) / np.where(yj - yi == 0, 1e-30, yj - yi) + xi
    return ((cond & (x < xc)).sum(1) % 2) == 1


def slice_loops(V, F, y, min_points=4):
    """Intersect a welded mesh with the plane Y = y. Each loop: {pts (k,3), xz (k,2), area (unsigned,
    XZ), centroid (x,z), closed, top (not nested in another loop), parent (index of the smallest loop
    holding it, or -1), children}. Loops under min_points are dropped."""
    d = V[:, 1] - y
    d = np.where(np.abs(d) < 1e-12, 1e-12, d)
    s = d[F] > 0
    cross = s.any(1) & ~s.all(1)
    fc = F[cross]
    if not len(fc):
        return []
    segs, keys = [], []
    for tri in fc:
        ks, ps = [], []
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            if (d[a] > 0) != (d[b] > 0):
                t = d[a] / (d[a] - d[b])
                ks.append((min(a, b), max(a, b)))
                ps.append(V[a] + t * (V[b] - V[a]))
        if len(ks) == 2:
            segs.append(ps)
            keys.append(ks)
    adj, pos = {}, {}
    for i, (ks, ps) in enumerate(zip(keys, segs)):
        for k, p in zip(ks, ps):
            adj.setdefault(k, []).append(i)
            pos[k] = p
    used = np.zeros(len(segs), bool)
    loops = []
    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        start, cur = keys[i]
        chain, closed = [start, cur], False
        while True:
            nxt = [j for j in adj[cur] if not used[j]]
            if not nxt:
                closed = cur == start
                break
            j = nxt[0]
            used[j] = True
            k2 = keys[j][1] if keys[j][0] == cur else keys[j][0]
            if k2 == start:
                closed = True
                break
            chain.append(k2)
            cur = k2
        if len(chain) >= min_points:
            p = np.array([pos[k] for k in chain])
            loops.append({"pts": p, "xz": p[:, [0, 2]], "closed": closed})
    for lp in loops:
        lp["area"] = abs(_poly_area(lp["xz"]))
        lp["centroid"] = lp["xz"].mean(0)
    order = sorted(range(len(loops)), key=lambda i: loops[i]["area"])
    for rank, i in enumerate(order):
        probe = loops[i]["xz"][:1]
        parent = -1
        for j in order[rank + 1:]:
            if loops[j]["closed"] and point_in_poly(probe, loops[j]["xz"])[0]:
                parent = j
                break
        loops[i]["parent"] = parent
        loops[i]["top"] = parent == -1
    for i, lp in enumerate(loops):
        lp["children"] = [j for j, other in enumerate(loops) if other["parent"] == i]
    return loops


# ------------------------------------------------------------------------------------- neck band
def _slice_structure(V, F, y, axis_xz, prev_area=None):
    """The neck candidate in one slice: a closed loop holding the axis that is an outer boundary (even
    nesting depth, so a turtleneck's ring around the neck does not count), the one whose area is
    nearest the previous slice's (the scan follows the head down its neck; the first slice takes the
    outermost), with its subtree."""
    loops = slice_loops(V, F, y)
    closed = [i for i, lp in enumerate(loops) if lp["closed"]]
    for i in closed:
        d, j = 0, loops[i]["parent"]
        while j != -1:
            d, j = d + 1, loops[j]["parent"]
        loops[i]["depth"] = d
    holding = [i for i in closed if loops[i]["depth"] % 2 == 0 and point_in_poly(axis_xz[None], loops[i]["xz"])[0]]
    if not holding:
        return loops, None, set()
    if prev_area is None:
        h = max(holding, key=lambda i: loops[i]["area"])
    else:
        h = min(holding, key=lambda i: abs(math.log(max(loops[i]["area"], 1e-30) / prev_area)))
    sub, stack = {h}, [h]
    while stack:
        for c in loops[stack.pop()]["children"]:
            if c not in sub:
                sub.add(c)
                stack.append(c)
    return loops, h, sub


def neck_band(V, F, step=0.002, axis_xz=None):
    """The clean neck band of a welded anchor: the run of heights where the slice holds one closed
    ring (with at most its inner shell nested) around the head's axis, convex, at the narrowest
    radius; other loops (a collar) may sit around it but not touch it. Returns {band [low, high],
    axis_xz, radius, collar, collar_top, head_top, profile}; raises GateFailed when there is no band."""
    top, bottom = float(V[:, 1].max()), float(V[:, 1].min())
    height = top - bottom
    if axis_xz is None:
        crown = V[V[:, 1] > top - 0.08 * height]
        axis_xz = np.median(crown[:, [0, 2]], axis=0)
    axis_xz = np.asarray(axis_xz, float)

    def collar_near(loops, h, sub, r_eq, centre):
        for i, lp in enumerate(loops):
            if i in sub or not lp["closed"] or lp["area"] < 0.02 * math.pi * r_eq ** 2:
                continue
            dmin = float(np.min(np.linalg.norm(lp["xz"] - centre, axis=1)))
            if 1.05 * r_eq < dmin < 2.5 * r_eq or (point_in_poly(centre[None], lp["xz"])[0]
                                                    and dmin < 2.5 * r_eq):
                return True
        return False

    profile = []
    prev = None
    for y in np.arange(top - 0.06 * height, top - 0.40 * height, -step):
        loops, h, sub = _slice_structure(V, F, float(y), axis_xz, prev)
        row = {"y": round(float(y), 5), "ok": False}
        if h is not None:
            c = loops[h]
            prev = c["area"]
            r_eq = math.sqrt(c["area"] / math.pi)
            solidity = c["area"] / max(_hull_area(c["xz"]), 1e-30)
            row.update({"r": r_eq, "solidity": round(solidity, 3), "children": len(c["children"]),
                        "centroid": c["centroid"].tolist(), "z_back": float(c["xz"][:, 1].min()),
                        "collar": collar_near(loops, h, sub, r_eq, c["centroid"]),
                        "ok": solidity >= 0.85 and len(c["children"]) <= 1})
        profile.append(row)
    ok_rows = [r for r in profile if r["ok"]]
    if not ok_rows:
        raise GateFailed("measure.neck_band: no height holds a lone convex ring around the head axis "
                         "(a raised hood, a helmet or hair fused to the shoulders)")
    r_min = min(r["r"] for r in ok_rows)
    i_min = next(i for i, r in enumerate(profile) if r["ok"] and r["r"] == r_min)

    def clean(r):
        return r["ok"] and r["r"] <= 1.2 * r_min

    lo = hi = i_min
    while hi > 0 and clean(profile[hi - 1]):          # profile runs downward: lower index = higher y
        hi -= 1
    while lo + 1 < len(profile) and clean(profile[lo + 1]):
        lo += 1
    run = profile[hi: lo + 1]
    band = [run[-1]["y"], run[0]["y"]]
    if band[1] - band[0] < step * 0.5:
        band = [band[0] - step / 2, band[1] + step / 2]
    axis = np.mean([r["centroid"] for r in run], axis=0)
    radius = float(np.mean([r["r"] for r in run]))
    collar = any(r.get("collar") for r in run)
    collar_top = None
    if collar:
        collar_top = max(r["y"] for r in run if r.get("collar"))
        for r in profile[:hi][::-1]:                     # up from the band, to band top + 0.5 radius
            if r["y"] > band[1] + 0.5 * radius:
                break
            if r.get("collar"):
                collar_top = r["y"]
    # Below the band the same ring may go on, no wider, with loops nested in it (a stand collar fused to the
    # jaw, hair fused to the nape): the band then sits on the jaw and the neck is covered. Its foot is the
    # last height before the ring passes 1.5 x the band's radius (the shoulders).
    covered, below = None, profile[lo + 1:]
    k = 0
    while k < len(below) and below[k].get("r") and below[k]["r"] <= 1.2 * r_min:
        k += 1
    nested = [r for r in below[:k] if not r["ok"]]
    if k and band[0] - below[k - 1]["y"] >= COVERED_MIN * (top - band[1]) and len(nested) * 2 >= k:
        foot = below[k - 1]["y"]
        for r in below[k:]:
            if not r.get("r") or r["r"] > 1.5 * r_min:
                break
            foot = r["y"]
        # the band ring holds the chin; the neck under it is round and its back follows the nape (the
        # ring's back): the profile views put the neck there, one diameter deep
        covered = {"to_y": round(float(below[k - 1]["y"]), 5), "foot_y": round(float(foot), 5),
                   "nested_rows": len(nested), "rows": k,
                   "children_max": max(r.get("children") or 0 for r in below[:k]),
                   "nape_z": round(float(np.mean([r["z_back"] for r in run])), 6)}
        # what covers it is a collar to the seam, and it starts at the band (a loop flagged above the band
        # is hair behind the head: a ponytail beside a jaw-high collar)
        collar, collar_top = True, band[0]
    return {"band": [round(band[0], 5), round(band[1], 5)], "axis_xz": [round(float(a), 6) for a in axis],
            "radius": round(radius, 5), "collar": bool(collar),
            "collar_top": None if collar_top is None else round(float(collar_top), 5),
            "covered": covered, "head_top": round(top, 5), "profile": profile}



def seam_heights(neck, margin_frac=0.1):
    """cut_y (the lowest height where the neck is still an isolated ring), part_bottom_y (how far the
    part's neck must reach below the band) and the head height (top - band high). Over a covered neck the
    part's neck reaches the cover's foot: the seam goes under the collar."""
    lo, hi = neck["band"]
    head_height = neck["head_top"] - hi
    bottom = lo - margin_frac * head_height
    if neck.get("covered"):
        bottom = min(bottom, neck["covered"]["foot_y"])
    return {"cut_y": round(lo + 0.2 * (hi - lo), 5), "part_bottom_y": round(bottom, 5),
            "head_height": round(head_height, 5)}


def hanging_faces(V, F, region, cut_y, bottom_y, axis_xz, radius, disc=1.3):
    """The head's own pieces hanging below the cut outside the neck (a ponytail, long locks): components of
    the faces between bottom_y and cut_y that meet the deleted head region at the cut with most of that rim
    outside the neck disc. A collar or a hood meets kept faces there, the neck meets it inside the disc.
    For the views only (the guide keeps them down to the part's bottom); the assembly keeps the anchor's."""
    cy = V[F].mean(1)[:, 1]
    band = (cy <= cut_y) & (cy > bottom_y) & ~region
    out = np.zeros(len(F), bool)
    info = []
    if not band.any() or not region.any():
        return out, info
    head_v = np.zeros(len(V), bool)
    head_v[F[region].reshape(-1)] = True
    dist = np.linalg.norm(V[:, [0, 2]] - np.asarray(axis_xz, float), axis=1)
    lab = face_components(F, band)
    for k in np.unique(lab[band]):
        faces = np.nonzero(band & (lab == k))[0]
        verts = np.unique(F[faces].reshape(-1))
        rim = verts[head_v[verts]]
        if len(rim) < 4:
            continue
        outside = float((dist[rim] > disc * radius).mean())
        if outside >= 0.5:
            out[faces] = True
            info.append({"faces": int(len(faces)), "rim_outside": round(outside, 3),
                         "bottom_y": round(float(V[verts, 1].min()), 5)})
    return out, info


def region_faces(V, F, cut_y, axis_xz, radius, box=None, disc=1.3, float_above=None):
    """The anchor faces a head part replaces (welded mesh): faces above cut_y in components (over faces
    above the plane) whose boundary at the plane lies inside the neck disc, plus floating islands above
    the plane inside the region box (x/z half widths about the axis) that lie wholly above float_above
    (the collar top) or centre in the neck disc. A collar that reaches above the plane but meets it
    outside the disc is kept. Returns (mask, info)."""
    cy = V[F].mean(1)[:, 1]
    above = cy > cut_y
    lab = face_components(F, above)
    vy = V[:, 1]
    rim = np.zeros(len(V), bool)                  # vertices shared with faces below the plane
    rim[F[~above].reshape(-1)] = True
    axis = np.asarray(axis_xz, float)
    dist = np.linalg.norm(V[:, [0, 2]] - axis, axis=1)
    kill = np.zeros(len(F), bool)
    info = {"components_above": int(lab.max() + 1) if above.any() else 0, "deleted": [], "kept": []}
    idx = np.nonzero(above)[0]
    order = np.argsort(lab[idx], kind="stable")
    labs = lab[idx][order]
    starts = np.r_[0, np.nonzero(np.diff(labs))[0] + 1, len(labs)]
    for k in range(len(starts) - 1):
        faces = idx[order[starts[k]: starts[k + 1]]]
        verts = np.unique(F[faces].reshape(-1))
        rim_v = verts[rim[verts]]
        if len(rim_v):
            inside = float((dist[rim_v] <= disc * radius).mean())
            if inside >= 0.5:
                kill[faces] = True
                info["deleted"].append({"faces": int(len(faces)), "rim_inside": round(inside, 3)})
            else:
                info["kept"].append({"faces": int(len(faces)), "rim_inside": round(inside, 3)})
        else:
            c = V[verts]
            inbox = box is None or (np.all(np.abs(c[:, 0] - axis[0]) <= box[0])
                                    and np.all(np.abs(c[:, 2] - axis[1]) <= box[1]))
            high = float_above is None or c[:, 1].min() > float_above or \
                np.linalg.norm(c[:, [0, 2]].mean(0) - axis) <= disc * radius
            if inbox and high:
                kill[faces] = True
                info["deleted"].append({"faces": int(len(faces)), "floating": True})
            else:
                info["kept"].append({"faces": int(len(faces)), "floating": True})
    return kill, info


def _loop_length(lp):
    p = lp["pts"]
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1).sum()
    return float(seg + (np.linalg.norm(p[-1] - p[0]) if lp["closed"] else 0.0))


def collar_kept(V, F, kill, ys, axis_xz, radius):
    """Share of the collar left after a cut: at each height in ys (between the cut and the collar
    top), the length of the slice loops around the neck (within 2.5 radius) that are not the neck
    itself, on the mesh before the cut, against the length of the loops left near the neck after it.
    Loops shorter than twice the radius (a chin tip, hair ends, specks) are left out of both."""
    axis = np.asarray(axis_xz, float)
    before = after = 0.0
    for y in ys:
        loops, h, sub = _slice_structure(V, F, float(y), axis)
        for i, lp in enumerate(loops):
            if i not in sub and np.min(np.linalg.norm(lp["xz"] - axis, axis=1)) < 2.5 * radius \
                    and _loop_length(lp) >= 2 * radius:
                before += _loop_length(lp)
        for lp in slice_loops(V, F[~kill], float(y)):
            if np.min(np.linalg.norm(lp["xz"] - axis, axis=1)) < 2.5 * radius and _loop_length(lp) >= 2 * radius:
                after += _loop_length(lp)
    return 1.0 if before == 0 else min(1.0, after / before)


# ----------------------------------------------------------------------------------- registration
class _Grid:
    """One level of a uniform grid over points Q: exact nearest neighbour when it lies in the 27 cells
    around the query (any hit within one cell is exact), inf when those cells are empty."""

    def __init__(self, Q, cell):
        self.Q = Q
        self.cell = cell
        self.lo = Q.min(0) - cell
        ijk = np.floor((Q - self.lo) / cell).astype(np.int64)
        self.dims = ijk.max(0) + 3
        key = (ijk[:, 0] * self.dims[1] + ijk[:, 1]) * self.dims[2] + ijk[:, 2]
        self.order = np.argsort(key, kind="stable")
        self.keys, self.start, self.count = np.unique(key[self.order], return_index=True, return_counts=True)

    def query(self, X, chunk=20000):
        best = np.full(len(X), np.inf)
        arg = np.zeros(len(X), np.int64)
        offs = np.array([(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1)])
        for c0 in range(0, len(X), chunk):
            x = X[c0:c0 + chunk]
            ijk = np.floor((x - self.lo) / self.cell).astype(np.int64)
            qs, ps = [], []
            for o in offs:
                n = ijk + o
                valid = np.all((n >= 0) & (n < self.dims), axis=1)
                key = (n[:, 0] * self.dims[1] + n[:, 1]) * self.dims[2] + n[:, 2]
                at = np.minimum(np.searchsorted(self.keys, key), len(self.keys) - 1)
                qi = np.nonzero(valid & (self.keys[at] == key))[0]
                cnt = self.count[at[qi]]
                rep = np.repeat(qi, cnt)
                first = np.repeat(self.start[at[qi]], cnt)
                within = np.arange(len(rep)) - np.repeat(np.cumsum(cnt) - cnt, cnt)
                qs.append(rep)
                ps.append(self.order[first + within])
            q, p = np.concatenate(qs), np.concatenate(ps)
            if not len(q):
                continue
            d = np.linalg.norm(x[q] - self.Q[p], axis=1)
            low = np.full(len(x), np.inf)
            np.minimum.at(low, q, d)
            at_min = d == low[q]
            pick = np.zeros(len(x), np.int64)
            pick[q[at_min]] = p[at_min]
            best[c0:c0 + len(x)] = low
            arg[c0:c0 + len(x)] = pick
        return best, arg


class GridNN:
    """Nearest neighbour in numpy (no scipy inside Blender): a fine uniform grid (about 8 points per
    occupied cell), then coarser grids over subsamples for queries the fine one cannot reach. Far
    queries get an approximate neighbour, which is all ICP needs while it closes in; queries beyond
    every level get inf (trimmed ICP drops them)."""

    def __init__(self, Q, rng=None):
        self.Q = np.asarray(Q, float)
        rng = rng or np.random.default_rng(0)
        ext = float(np.ptp(self.Q, axis=0).max())
        cell = ext / max(4.0, math.sqrt(len(self.Q)) / 2.0)
        idx = np.arange(len(self.Q))
        self.levels = []
        while True:
            self.levels.append((_Grid(self.Q[idx], cell), idx))
            if len(idx) < 2000 or cell > ext / 4:
                break
            idx = np.sort(rng.choice(idx, size=len(idx) // 9, replace=False))
            cell *= 3.0

    def __call__(self, X):
        X = np.asarray(X, float)
        best = np.full(len(X), np.inf)
        arg = np.zeros(len(X), np.int64)
        todo = np.arange(len(X))
        for grid, idx in self.levels:
            if not len(todo):
                break
            d, a = grid.query(X[todo])
            found = np.isfinite(d)
            best[todo[found]] = d[found]
            arg[todo[found]] = idx[a[found]]
            todo = todo[~found]
        return best, arg


def umeyama(A, B):
    """Similarity (s, R, t) minimising |s R A + t - B|."""
    ma, mb = A.mean(0), B.mean(0)
    a0, b0 = A - ma, B - mb
    U, S, Vt = np.linalg.svd(a0.T @ b0 / len(A))
    D = np.eye(3)
    if np.linalg.det(Vt.T @ U.T) < 0:
        D[2, 2] = -1
    R = Vt.T @ D @ U.T
    s = float(np.trace(np.diag(S) @ D) / ((a0 ** 2).sum() / len(A)))
    return s, R, mb - s * R @ ma


def rotation_deg(R):
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))))


def _rodrigues(w):
    th = float(np.linalg.norm(w))
    if th < 1e-15:
        return np.eye(3)
    k = w / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K


def similarity_icp(P, Q, s0, R0, t0, trim=0.8, iters=80, nn=None, Qn=None, region_box=None,
                   region_height=None, fix_scale=False):
    """Trimmed similarity ICP of part points P onto anchor-region points Q. Each iteration pairs every
    part point with its nearest anchor point and keeps the best `trim` share; with anchor normals Qn it
    takes a point-to-plane similarity step (a linearised rotation, scale and shift, which converges in
    a few iterations on smooth surfaces), else Umeyama on the pairs. nn(X) -> (distance, index)
    defaults to GridNN(Q); inside Blender pass a mathutils.kdtree wrapper. Returns {s, R, t,
    rms_trimmed, rms_inside, median_inside, share_inside, rotation_deg, iterations}: rms_inside is the
    RMS point distance of the part points inside the region's box (grown by 1 % of its height),
    divided by the region height. fix_scale keeps s0 (a rigid fit at the crop's scale)."""
    P = np.asarray(P, float)
    Q = np.asarray(Q, float)
    nn = nn or GridNN(Q)
    s, R, t = float(s0), np.asarray(R0, float), np.asarray(t0, float)
    lo, hi = (Q.min(0), Q.max(0)) if region_box is None else (np.asarray(region_box[0]), np.asarray(region_box[1]))
    h = region_height or float(hi[1] - lo[1])
    rms = float("nan")
    it = 0
    for it in range(1, iters + 1):
        X = s * P @ R.T + t
        d, idx = nn(X)
        fin = np.isfinite(d)
        if fin.sum() < 10:
            break
        keep = fin & (d <= np.quantile(d[fin], trim))
        rms = float(np.sqrt((d[keep] ** 2).mean()))
        if Qn is None:
            s2, R2, t2 = umeyama(P[keep], Q[idx[keep]])
            if fix_scale:
                s2 = s
                t2 = Q[idx[keep]].mean(0) - s * R2 @ P[keep].mean(0)
        else:
            x, q, n = X[keep], Q[idx[keep]], Qn[idx[keep]]
            c = x.mean(0)
            xc = x - c
            A = np.c_[np.cross(xc, n), np.zeros(len(n)) if fix_scale else (xc * n).sum(1), n]
            b = -((x - q) * n).sum(1)
            AtA = A.T @ A
            step = np.linalg.solve(AtA + 1e-9 * np.trace(AtA) * np.eye(7) + (np.diag([0, 0, 0, 1.0, 0, 0, 0])
                                   if fix_scale else 0), A.T @ b)
            Ri = _rodrigues(step[:3])
            g = 1.0 + step[3]
            s2, R2, t2 = s * g, Ri @ R, g * Ri @ (t - c) + c + step[4:]
        done = abs(s2 / s - 1) < 1e-7 and np.abs(t2 - t).max() < 1e-7 * h and np.abs(R2 - R).max() < 1e-7
        s, R, t = s2, R2, t2
        if done:
            break
    X = s * P @ R.T + t
    d, _ = nn(X)
    margin = 0.01 * h
    inside = np.all((X >= lo - margin) & (X <= hi + margin), axis=1) & np.isfinite(d)
    di = d[inside]
    return {"s": s, "R": R, "t": t, "rms_trimmed": rms, "iterations": it,
            "rms_inside": float(np.sqrt((di ** 2).mean()) / h) if len(di) else float("inf"),
            "median_inside": float(np.median(di) / h) if len(di) else float("inf"),
            "share_inside": float(inside.mean()), "rotation_deg": rotation_deg(R)}


# ------------------------------------------------------------------------------------------ rays
def ray_hits(O, D, V, F, t_min=1e-7, t_max=float("inf"), chunk=None):
    """First hit per ray (Möller–Trumbore, both sides): (t, face index); t = inf when none."""
    O = np.atleast_2d(np.asarray(O, float))
    D = np.atleast_2d(np.asarray(D, float))
    if len(D) == 1 and len(O) > 1:
        D = np.repeat(D, len(O), 0)
    if len(O) == 1 and len(D) > 1:
        O = np.repeat(O, len(D), 0)
    v0 = V[F[:, 0]]
    e1 = V[F[:, 1]] - v0
    e2 = V[F[:, 2]] - v0
    tbest = np.full(len(O), np.inf)
    fbest = np.full(len(O), -1)
    if not len(F):
        return tbest, fbest
    chunk = chunk or max(1, int(4e6 // max(len(F), 1)))
    for c0 in range(0, len(O), chunk):
        o = O[c0:c0 + chunk][:, None, :]
        d = D[c0:c0 + chunk][:, None, :]
        pv = np.cross(d, e2[None])
        det = (e1[None] * pv).sum(-1)
        ok = np.abs(det) > 1e-14
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = o - v0[None]
        u = (tv * pv).sum(-1) * inv
        qv = np.cross(tv, e1[None])
        v = (d * qv).sum(-1) * inv
        t = (e2[None] * qv).sum(-1) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > t_min) & (t < t_max)
        tt = np.where(hit, t, np.inf)
        j = tt.argmin(1)
        tb = tt[np.arange(len(j)), j]
        tbest[c0:c0 + chunk] = tb
        fbest[c0:c0 + chunk] = np.where(np.isfinite(tb), j, -1)
    return tbest, fbest


def rays_hit_share(V, F, origin, dirs):
    t, _ = ray_hits(origin, dirs, V, F)
    return float(np.isfinite(t).mean())


def dome_dirs(elev=(20, 89), n_elev=6, n_az=24):
    """Directions over the upper dome: n_elev elevations between elev[0] and elev[1] degrees, n_az
    azimuths each (default 144 rays)."""
    out = []
    for el in np.radians(np.linspace(elev[0], elev[1], n_elev)):
        for az in np.radians(np.arange(n_az) * 360.0 / n_az):
            out.append([math.cos(el) * math.sin(az), math.sin(el), math.cos(el) * math.cos(az)])
    return np.array(out)


def sphere_dirs(n=288):
    """n nearly even directions (a Fibonacci sphere)."""
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = math.pi * (1 + 5 ** 0.5) * i
    return np.c_[np.cos(th) * np.sin(phi), np.cos(phi), np.sin(th) * np.sin(phi)]


def inner_shell_faces(V, F, band_y, half_width, radius, axis_xz, reach=None):
    """Inner-shell faces near a cut (welded, UNCUT mesh): faces within band_y +- half_width and within
    1.3 radius of the axis whose normal ray crosses the axis and hits the mesh again inside the neck
    (the far wall, within 1.3 radius): the inward-facing wall of a double shell. Outer faces look out,
    into air or onto a collar on their own side. Delete them locally, never as a component."""
    axis = np.asarray(axis_xz, float)
    c = V[F].mean(1)
    fn, _ = face_normals(V, F)
    rad = np.linalg.norm(c[:, [0, 2]] - axis, axis=1)
    cand = np.nonzero((np.abs(c[:, 1] - band_y) <= half_width) & (rad <= 1.3 * radius))[0]
    out = np.zeros(len(F), bool)
    if not len(cand):
        return out
    near = (np.abs(c[:, 1] - band_y) <= half_width + 2 * radius) & (rad <= 3 * radius)
    Fn = F[near]
    o = c[cand] + fn[cand] * 1e-6 * max(radius, 1e-9)
    t, _ = ray_hits(o, fn[cand], V, Fn, t_min=1e-5 * radius, t_max=reach or 2.5 * radius)
    hp = o + fn[cand] * np.where(np.isfinite(t), t, 0)[:, None]
    across = ((hp[:, [0, 2]] - axis) * (o[:, [0, 2]] - axis)).sum(1) < 0
    inside = np.linalg.norm(hp[:, [0, 2]] - axis, axis=1) < 1.3 * radius
    out[cand] = np.isfinite(t) & inside & across
    return out


def boundary_loops(F):
    """Boundary edges (used by one face) chained into vertex loops (welded F)."""
    e = np.sort(np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    ue, cnt = np.unique(e, axis=0, return_counts=True)
    be = ue[cnt == 1]
    adj = {}
    for a, b in be:
        adj.setdefault(int(a), []).append(int(b))
        adj.setdefault(int(b), []).append(int(a))
    seen, loops = set(), []
    for a, b in be:
        a, b = int(a), int(b)
        if (a, b) in seen:
            continue
        loop, prev, cur = [a], a, b
        seen.add((min(a, b), max(a, b)))
        while cur != a:
            loop.append(cur)
            nxt = [x for x in adj[cur] if x != prev and (min(cur, x), max(cur, x)) not in seen]
            if not nxt:
                break
            seen.add((min(cur, nxt[0]), max(cur, nxt[0])))
            prev, cur = cur, nxt[0]
        loops.append(np.array(loop))
    return loops


def loops_at(V, F, y, tol, min_len=6, axis_xz=None, radius=None):
    """Boundary loops of F whose mean height is within tol of y (and, given an axis, whose centre lies
    within 1.5 radius of it): the loops a cut at y left open."""
    out = []
    for lp in boundary_loops(F):
        if len(lp) < min_len or abs(V[lp, 1].mean() - y) > tol:
            continue
        if axis_xz is not None and np.linalg.norm(V[lp][:, [0, 2]].mean(0) - axis_xz) > 1.5 * radius:
            continue
        out.append(lp)
    return out


def bridge_ready(V_a, loops_a, V_b, loops_b, radius):
    """Can the anchor's and the part's cut loops be bridged? One loop on each side, and the gap (each
    anchor loop vertex to the nearest part loop vertex, in XZ) as shares of the radius."""
    res = {"loops": [len(loops_a), len(loops_b)], "gap_mean": None, "gap_max": None}
    if len(loops_a) == 1 and len(loops_b) == 1:
        a = V_a[loops_a[0]][:, [0, 2]]
        b = V_b[loops_b[0]][:, [0, 2]]
        d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)).min(1)
        res["gap_mean"] = float(d.mean() / radius)
        res["gap_max"] = float(d.max() / radius)
    return res


def _smooth01(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def outer_radius(O_y, D, axis_xz, V, F, reach):
    """Distance from the axis (at height O_y, along the horizontal unit directions D) to the OUTERMOST
    surface of (V, F) within reach: cast inward from reach, so an inner shell never answers."""
    O = np.c_[np.full(len(D), axis_xz[0]), O_y, np.full(len(D), axis_xz[1])] + D * reach
    t, _ = ray_hits(O, -D, V, F, t_max=reach)
    return np.where(np.isfinite(t), reach - t, np.nan)


def tuck_band(V, vid, axis_xz, radius, y_full, y_zero, target, hide=None, inset=0.97, limit=0.25, flare_below=None):
    """Pull the vertices vid of V (welded) radially inside `target` (V, F: the other mesh near the seam,
    its outermost surface along the same ray from the axis) to inset x its radius, fully at height
    y_full and fading to nothing at y_zero. A vertex that some `hide` geometry (V, F: the anchor's
    collar or torso) already covers from outside, or that is inside the target, does not move.
    Nothing moves when a vertex would move more than limit x radius (that neck is a redraw failure).
    flare_below given: a vertex below that height standing more than limit x radius outside the target
    is a flare (shoulders, a collar's foot) that covers the target there: it stays and is not counted.
    Returns (V after, stats: moved, exposed, flare, need_max and shift_max as shares of the radius,
    applied)."""
    stats = {"moved": 0, "exposed": 0, "flare": 0, "need_max": 0.0, "shift_max": 0.0, "shift_mean": 0.0,
             "applied": False}
    V = np.asarray(V, float)
    if not len(vid) or y_full == y_zero:
        return V, stats
    axis_xz = np.asarray(axis_xz, float)
    rxz = np.linalg.norm(V[vid][:, [0, 2]] - axis_xz, axis=1)
    keep = rxz > 0.3 * radius
    vid, rxz = vid[keep], rxz[keep]
    D = np.c_[V[vid, 0] - axis_xz[0], np.zeros(len(vid)), V[vid, 2] - axis_xz[1]] / np.maximum(rxz, 1e-12)[:, None]
    rt = outer_radius(V[vid, 1], D, axis_xz, target[0], target[1], 2.5 * radius)
    need = np.where(np.isfinite(rt), rxz - inset * np.nan_to_num(rt), 0.0).clip(0.0, None)
    if hide is not None and len(hide[1]) and (need > 0).any():
        o = np.nonzero(need > 0)[0]
        # covered = every ray of a horizontal fan (the outward direction, +-35 and +-70 degrees) meets the
        # hide geometry: a collar far out to the side covers the radial ray but not the front view
        hit = np.ones(len(o), bool)
        for deg in HIDE_FAN_DEG:
            c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            Dr = np.c_[c * D[o, 0] + s * D[o, 2], np.zeros(len(o)), -s * D[o, 0] + c * D[o, 2]]
            t, _ = ray_hits(V[vid[o]], Dr, hide[0], hide[1], t_min=0.1 * radius, t_max=3 * radius)
            hit &= np.isfinite(t)
        need[o[hit]] = 0.0
    if flare_below is not None:
        flare = (V[vid, 1] < flare_below) & (need > limit * radius)
        stats["flare"] = int(flare.sum())
        need[flare] = 0.0
    shift = need * _smooth01((V[vid, 1] - y_zero) / (y_full - y_zero))
    move = shift > 1e-9
    stats.update(exposed=int((need > 0).sum()), need_max=float(need.max() / radius) if len(need) else 0.0,
                 shift_max=float(shift.max() / radius) if len(shift) else 0.0,
                 shift_mean=float(shift[move].mean() / radius) if move.any() else 0.0)
    if stats["shift_max"] > limit:
        return V, stats
    out = V.copy()
    out[vid[move]] -= D[move] * shift[move][:, None]
    stats.update(moved=int(move.sum()), applied=True)
    return out, stats


def crossing_height(Va, Fa, Vp, Fp, axis_xz, radius, y0, y1, n_y=33, n_theta=24, cover=None):
    """Where an overlap seam shows after the tuck: per angle around the neck axis, the highest height in
    [y0, y1] at which the anchor (Va, Fa: its faces near the neck) stands outside the part's neck (Vp, Fp);
    returns (the median over the angles that have one, else None; the per-angle heights). cover = (V, F,
    y): an angle where that geometry (a collar) stands 1.3 to 4 radii out at height y is not counted."""
    axis_xz = np.asarray(axis_xz, float)
    a = np.linspace(-math.pi, math.pi, n_theta, endpoint=False)
    D = np.c_[np.sin(a), np.zeros(n_theta), np.cos(a)]
    ys = np.linspace(y0, y1, n_y)
    best = np.full(n_theta, np.nan)
    for y in ys:
        Y = np.full(n_theta, y)
        ra = outer_radius(Y, D, axis_xz, Va, Fa, 2.5 * radius)
        rp = outer_radius(Y, D, axis_xz, Vp, Fp, 2.5 * radius)
        out = np.isfinite(ra) & (~np.isfinite(rp) | (ra > np.nan_to_num(rp)))
        best[out] = y
    have = np.isfinite(best)
    if cover is not None and len(cover[1]):
        rc = outer_radius(np.full(n_theta, float(cover[2])), D, axis_xz, cover[0], cover[1], 4 * radius)
        have &= ~(np.isfinite(rc) & (rc > 1.3 * radius))
    return (float(np.median(best[have])) if have.any() else None), best


def stump_faces(V, F, rim_v, axis_xz, radius, bottom_y, cut_y):
    """The anchor's neck stump near an overlap seam: faces between bottom_y and cut_y, inside 1.3 x
    radius of the axis, joined (within that band) to the open rim at cut_y."""
    cy = V[F].mean(1)[:, 1]
    rxz = np.linalg.norm(V[:, [0, 2]] - np.asarray(axis_xz, float), axis=1)
    band = (cy >= bottom_y - 1e-9) & (cy <= cut_y + 1e-9) & (rxz[F].max(1) < 1.3 * radius)
    lab = face_components(F, band)
    on_rim = np.zeros(len(V), bool)
    on_rim[np.asarray(rim_v, int)] = True
    keep = np.unique(lab[band & on_rim[F].any(1)])
    return band & np.isin(lab, keep[keep >= 0])


def tuck_stump(V, F, rim_v, Vp, Fp, axis_xz, radius, bottom_y, cut_y, inset=0.97, limit=0.25, ramp=1.0):
    """Overlap seam, the anchor's side: where the part's neck is slimmer than the anchor's stump, or
    about as wide, and nothing covers the stump, its open rim shows as a step or the two surfaces fight
    along a ragged line. Pull the stump under the part's neck (tuck_band) to inset x its radius: fully
    from the rim down to bottom_y + ramp x (cut_y - bottom_y), fading to nothing at bottom_y. ramp=1
    fades over the whole band; a short ramp with inset ~0.9 keeps the whole band clearly inside, so
    the two necks cross once, near bottom_y. V is welded, F its faces, (Vp, Fp) the part."""
    stump = stump_faces(V, F, rim_v, axis_xz, radius, bottom_y, cut_y)
    vid = np.unique(F[stump])
    vid = vid[V[vid, 1] >= bottom_y]
    y_full = bottom_y + float(np.clip(ramp, 1e-3, 1.0)) * (cut_y - bottom_y)
    # with a short ramp the band's foot may flare into the shoulders: left there; the rim's quarter counts
    flare = cut_y - 0.25 * (cut_y - bottom_y) if ramp < 1.0 else None
    return tuck_band(V, vid, axis_xz, radius, y_full, bottom_y, (Vp, Fp), hide=(V, F[~stump]),
                     inset=inset, limit=limit, flare_below=flare)


def neck_offset(Vp, Fp, axis_xz, radius, ys):
    """The part's neck axis against the anchor's: per height, the centroid of the part's slice loop
    around the axis (the largest within 1.5 radius); returns (median xz offset anchor - part, heights
    measured)."""
    offs = []
    for y in ys:
        best = None
        for lp in slice_loops(Vp, Fp, float(y)):
            if not lp["closed"] or np.linalg.norm(np.asarray(lp["centroid"]) - axis_xz) > 1.5 * radius:
                continue
            if best is None or lp["area"] > best["area"]:
                best = lp
        if best is not None:
            offs.append(np.asarray(axis_xz, float) - np.asarray(best["centroid"], float))
    if not offs:
        return np.zeros(2), 0
    return np.median(np.array(offs), axis=0), len(offs)


def centre_neck(Vp, Fp, axis_xz, radius, bottom_y, cut_y, fade_top, limit=0.25):
    """Overlap seam, the part's side: the generated neck column may stand off the anchor's neck axis
    (the redraw draws its own neck). Shift the part horizontally onto the axis: fully at and below
    cut_y, fading to nothing at fade_top, so the head itself does not move. Refused (nothing moves)
    when the offset is over limit x radius. Returns (V after, stats)."""
    off, n = neck_offset(Vp, Fp, np.asarray(axis_xz, float), radius, np.linspace(bottom_y, cut_y, 5)[1:-1])
    mag = float(np.linalg.norm(off) / radius)
    stats = {"offset": [float(off[0]), float(off[1])], "offset_share": mag, "heights": n, "applied": False}
    if n == 0 or mag > limit or mag < 1e-6:
        return np.asarray(Vp, float), stats
    w = _smooth01((fade_top - Vp[:, 1]) / max(fade_top - cut_y, 1e-9))
    out = np.asarray(Vp, float).copy()
    out[:, 0] += w * off[0]
    out[:, 2] += w * off[1]
    stats["applied"] = True
    return out, stats


# ---------------------------------------------------------------------------------- silhouettes
def view_uv(V, view):
    x, y, z = V[:, 0], V[:, 1], V[:, 2]
    u = {"front": x, "back": -x, "left": -z, "right": z}[view]
    return u, y


def silhouette(V, F, view, size, frame):
    """Boolean image (h, w) of the orthographic projection. size = (w, h); frame = (units_per_px, cx, cy):
    px = cx + u / units_per_px, row = cy - y / units_per_px (pixel centres at +0.5)."""
    w, h = (size, size) if np.isscalar(size) else size
    upp, cx, cy = frame
    u, y = view_uv(V, view)
    P = np.c_[cx + u / upp, cy - y / upp]
    T = P[F]
    img = np.zeros((h, w), bool)
    lo = np.floor(T.min(1) - 0.5).astype(np.int64) + 1
    hi = np.floor(T.max(1) - 0.5).astype(np.int64)
    span = np.maximum(hi - lo + 1, 0).max(1)
    on = (hi[:, 0] >= 0) & (hi[:, 1] >= 0) & (lo[:, 0] < w) & (lo[:, 1] < h) & (span > 0)
    for k in (1, 2, 4, 8, 16, 32, 64, 128, 256, 1 << 20):
        sel = np.nonzero(on & (span <= k))[0]
        on[sel] = False
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
                return (q[:, 0, None] - p[:, 0, None]) * (fy - p[:, 1, None]) - \
                       (q[:, 1, None] - p[:, 1, None]) * (fx - p[:, 0, None])

            e0, e1, e2 = edge(a, b), edge(b, c), edge(c, a)
            inside = ((e0 >= 0) & (e1 >= 0) & (e2 >= 0)) | ((e0 <= 0) & (e1 <= 0) & (e2 <= 0))
            inside &= (px <= hi[s, 0][:, None]) & (py <= hi[s, 1][:, None])
            inside &= (px >= 0) & (py >= 0) & (px < w) & (py < h)
            img[py[inside], px[inside]] = True
    return img


TOWARD = {"front": (2, 1.0), "back": (2, -1.0), "left": (0, 1.0), "right": (0, -1.0)}   # axis, sign toward the camera


def label_raster(V, F, labels, view, size, frame):
    """Per pixel, the label (> 0) of the face nearest the camera, 0 for background: the silhouette's
    raster with a depth test. Which surface a view sees (a hood in front of the neck, a collar behind
    it) is decided here, never by colour."""
    w, h = (size, size) if np.isscalar(size) else size
    upp, cx, cy = frame
    u, y = view_uv(V, view)
    ax, sg = TOWARD[view]
    P = np.c_[cx + u / upp, cy - y / upp]
    Z = sg * V[:, ax]
    T, TZ = P[F], Z[F]
    labels = np.asarray(labels)
    zbuf = np.full(h * w, -np.inf)
    out = np.zeros(h * w, np.int32)
    lo = np.floor(T.min(1) - 0.5).astype(np.int64) + 1
    hi = np.floor(T.max(1) - 0.5).astype(np.int64)
    span = np.maximum(hi - lo + 1, 0).max(1)
    on = (hi[:, 0] >= 0) & (hi[:, 1] >= 0) & (lo[:, 0] < w) & (lo[:, 1] < h) & (span > 0) & (labels > 0)
    for k in (1, 2, 4, 8, 16, 32, 64, 128, 256, 1 << 20):
        sel = np.nonzero(on & (span <= k))[0]
        on[sel] = False
        if not len(sel):
            continue
        kk = min(k, max(w, h))
        gx, gy = np.meshgrid(np.arange(kk), np.arange(kk))
        gx, gy = gx.reshape(-1), gy.reshape(-1)
        step = max(1, int(2e6 // (kk * kk)))
        for c0 in range(0, len(sel), step):
            s_ = sel[c0:c0 + step]
            px = lo[s_, 0][:, None] + gx[None]
            py = lo[s_, 1][:, None] + gy[None]
            fx, fy = px + 0.5, py + 0.5
            a, b, c = T[s_, 0], T[s_, 1], T[s_, 2]

            def edge(p, q):
                return (q[:, 0, None] - p[:, 0, None]) * (fy - p[:, 1, None]) - \
                       (q[:, 1, None] - p[:, 1, None]) * (fx - p[:, 0, None])

            e0, e1, e2 = edge(b, c), edge(c, a), edge(a, b)
            area = e0 + e1 + e2
            inside = ((e0 >= 0) & (e1 >= 0) & (e2 >= 0)) | ((e0 <= 0) & (e1 <= 0) & (e2 <= 0))
            inside &= (px <= hi[s_, 0][:, None]) & (py <= hi[s_, 1][:, None])
            inside &= (px >= 0) & (py >= 0) & (px < w) & (py < h)
            safe = np.where(np.abs(area) > 1e-12, area, 1.0)
            depth = (e0 * TZ[s_, 0, None] + e1 * TZ[s_, 1, None] + e2 * TZ[s_, 2, None]) / safe
            depth = np.where(np.abs(area) > 1e-12, depth, TZ[s_].mean(1)[:, None])
            fi, gi = np.nonzero(inside)
            if not len(fi):
                continue
            idx = py[fi, gi] * w + px[fi, gi]
            d = depth[fi, gi]
            np.maximum.at(zbuf, idx, d)
            win = d >= zbuf[idx]
            out[idx[win]] = labels[s_[fi[win]]]
    return out.reshape(h, w)


def keep_mask(V, F, region, view, mask, frame, grow_px, dilate_px=3, still=None, hang=None):
    """The view mask a part keeps: pixels where the part's region is the surface the view sees (dilated
    a little), minus every other surface the view sees in front of or around it, that surface grown
    upward by grow_px (the drawn hood or collar sits a few pixels above the low-poly anchor's). Faces in
    `still` (a covered neck's column: the jaw below the cut and the collar fused to it) are dropped but not
    grown: grown, they would take the chin and the mouth above them. Faces in `hang` (hair hanging below the
    cut) are kept like the region; with hang the return is (keep, the hanging pixels kept)."""
    h, w = mask.shape
    labels = np.where(region, 1, 2)
    if still is not None:
        labels = np.where(~region & still, 3, labels)
    if hang is not None:
        labels = np.where(~region & hang, 4, labels)
    lab = label_raster(V, F, labels, view, (w, h), frame)
    mask = mask & (lab != 3)
    hung = lab == 4
    lab = np.where(hung, 1, lab)
    other = lab == 2
    grown = other.copy()
    for dy in range(1, int(grow_px) + 1):
        grown[:-dy] |= other[dy:]
    keep = dilate(lab == 1, dilate_px) & mask & ~grown
    return keep if hang is None else (keep, dilate(hung, dilate_px) & keep)

def iou(a, b):
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 1.0


def dilate(mask, r):
    out = mask.copy()
    h, w = mask.shape
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy > r * r:
                continue
            src = mask[max(0, -dy): h - max(0, dy), max(0, -dx): w - max(0, dx)]
            out[max(0, dy): h - max(0, -dy), max(0, dx): w - max(0, -dx)] |= src
    return out


def _best_shift(sil, mask, reach):
    """The integer shift (dx, dy) of sil, within +-reach px, with the best IoU against mask (FFT
    cross-correlation of the two images, zero-padded)."""
    h, w = mask.shape
    H, W = h + 2 * reach, w + 2 * reach
    fa = np.fft.rfft2(mask.astype(float), (H, W))
    fb = np.fft.rfft2(sil.astype(float), (H, W))
    corr = np.fft.irfft2(fa * np.conj(fb), (H, W))
    best = (-1.0, 0, 0)
    a_s, a_m = float(sil.sum()), float(mask.sum())
    for dy in range(-reach, reach + 1):
        row = corr[dy % H]
        for dx in range(-reach, reach + 1):
            ov = row[dx % W]
            i = ov / max(a_s + a_m - ov, 1e-9)
            if i > best[0]:
                best = (float(i), dx, dy)
    return best


def fit_frame(V, F, masks, reach=24, scales=(0.97, 0.98, 0.99, 1.0, 1.01, 1.02, 1.03)):
    """One units_per_px for all views and a per-view offset, fitted to the clean masks: the scale from
    the silhouette area against the mask area (refined over `scales`), each offset from the centroids
    and then the shift with the best IoU. Returns {units_per_px, offset_px {view: [cx, cy]}, iou}."""
    y0, y1 = float(V[:, 1].min()), float(V[:, 1].max())
    ref = (y1 - y0) / 1800.0
    stats, upps = {}, []
    for view, m in masks.items():
        my, mx = np.nonzero(m)
        if not len(mx):
            raise GateFailed(f"part.frame_fit: the {view} mask is empty")
        sil = silhouette(V, F, view, 2048, (ref, 1024, 1024))
        sy, sx = np.nonzero(sil)
        stats[view] = ((sx.mean() + 0.5 - 1024) * ref, (1024 - sy.mean() - 0.5) * ref, mx.mean() + 0.5, my.mean() + 0.5)
        upps.append(math.sqrt(len(sx) * ref * ref / len(mx)))
    upp0 = float(np.mean(upps))
    best = None
    for k in scales:
        upp = upp0 * k
        offs, ious = {}, {}
        for view, m in masks.items():
            cu, cy_u, mcx, mcy = stats[view]
            cx, cy = mcx - cu / upp, mcy + cy_u / upp
            sil = silhouette(V, F, view, (m.shape[1], m.shape[0]), (upp, cx, cy))
            i, dx, dy = _best_shift(sil, m, reach)
            offs[view] = [round(float(cx + dx), 3), round(float(cy + dy), 3)]
            ious[view] = round(i, 4)
        score = float(np.mean(list(ious.values())))
        if best is None or score > best[0]:
            best = (score, upp, offs, ious)
    return {"units_per_px": round(best[1], 9), "offset_px": best[2], "iou": best[3]}


def crop_boxes(V, F, region, frame, part_bottom_y, view_px=VIEW_PX):
    """The crop box per view for a part region (face mask): L = ceil(1.1 x the largest extent over the
    views), even; rows centred on [projected top - 2 px, projected part_bottom_y], shared by every view;
    columns centred on the region per view. Boxes may leave the frame (pad with black)."""
    upp = frame["units_per_px"]
    pts = V[np.unique(F[region].reshape(-1))]
    top_rows, bottoms, widths, centres = [], [], {}, {}
    for view in VIEWS:
        cx, cy = frame["offset_px"][view]
        u, y = view_uv(pts, view)
        top_rows.append(cy - y.max() / upp - 2)
        bottoms.append(cy - part_bottom_y / upp)
        widths[view] = (u.max() - u.min()) / upp
        centres[view] = cx + (u.max() + u.min()) / 2 / upp
    top, bottom = min(top_rows), max(bottoms)
    ext = max([bottom - top] + list(widths.values()))
    L = int(math.ceil(1.1 * ext))
    L += L % 2
    y0 = int(round((top + bottom) / 2 - L / 2))
    boxes = {v: [int(round(centres[v] - L / 2)), y0, int(round(centres[v] - L / 2)) + L, y0 + L] for v in VIEWS}
    return {"box_side_px": L, "boxes": boxes, "clip_row_px": round(float(bottom - y0), 2)}


def box_centre(frame, boxes):
    """The anchor-frame point at the centre of a part's crop boxes: front gives x and y, left gives z."""
    upp = frame["units_per_px"]
    bf, bl = boxes["front"], boxes["left"]
    cxf, cyf = frame["offset_px"]["front"]
    cxl, _ = frame["offset_px"]["left"]
    x = ((bf[0] + bf[2]) / 2 - cxf) * upp
    y = (cyf - (bf[1] + bf[3]) / 2) * upp
    z = -((bl[0] + bl[2]) / 2 - cxl) * upp
    return np.array([x, y, z])


# ------------------------------------------------------------------------------------- hair split
def srgb_to_lab(rgb):
    """CIELAB (D65) of sRGB values in 0..1, shape (..., 3)."""
    c = np.asarray(rgb, float)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def face_colours(UVf, image, flip_v=False):
    """Base colour at each face's UV centroid. UVf (m,2); image (h, w, >=3) floats 0..1, row 0 at the top
    of the texture (glTF); flip_v for an image stored bottom-up (Blender's pixels)."""
    h, w = image.shape[:2]
    u = np.mod(UVf[:, 0], 1.0)
    v = np.mod(UVf[:, 1], 1.0)
    px = np.clip((u * (w - 1)).round().astype(int), 0, w - 1)
    row = (1 - v) if flip_v else v
    py = np.clip((row * (h - 1)).round().astype(int), 0, h - 1)
    return image[py, px, :3]


def _median_filter_wrap(a, sy=3, sx=5):
    py, px = sy // 2, sx // 2
    pad = np.concatenate([a[:, -px:], a, a[:, :px]], axis=1)
    pad = np.concatenate([np.repeat(pad[:1], py, 0), pad, np.repeat(pad[-1:], py, 0)], axis=0)
    h, w = a.shape
    stack = [pad[i:i + h, j:j + w] for i in range(sy) for j in range(sx)]
    return np.median(np.stack(stack), axis=0)


def hair_target(parts, tris):
    """The hair's triangle target from its budget_share: its share of the triangles of the parts built
    so far at most its share of their shares, i.e. share / (sum of those shares - share) x the others'
    triangles. parts: the plan's parts; tris: {region: triangles} of the parts present (hair included).
    None when the plan gives the hair no share or a present part has none."""
    by = {p.get("region"): p.get("budget_share") for p in parts}
    s = by.get("hair")
    if not s or "hair" not in tris or any(not by.get(r) for r in tris):
        return None
    others = sum(n for r, n in tris.items() if r != "hair")
    rest = sum(by[r] for r in tris) - s
    return int(s / rest * others) if rest > 0 else None


def split_hair(V, F, rgb, hair_rgb, skin_rgb, chin_y, delta=0.03, centre_frac=0.4, smooth=3,
               island_frac=0.005, face_top=0.45, face_yaw=35.0):
    """Split the hair off a registered, painted head (welded V, F; rgb per face, 0..1). Hair = faces
    nearer (CIELAB) the hair colour than the skin colour, more than delta x part height outside the
    scalp-radius map, above the chin and outside the face; majority-smoothed over neighbours; islands
    under island_frac of the hair area go back to the head. The face is decided by geometry, never by
    colour (lips and a mouth can sit nearer a dark-red or brown hair colour than the skin): in front
    (within face_yaw degrees of +Z around the head's centre) and below the brow line, face_top of the
    way from the chin to the top. hair.components counts the pieces holding >= 2 % of the hair
    (a few loose strands are hair; a split that shatters is not). Returns (hair mask, stats with gates)."""
    top = float(V[:, 1].max())
    H = top - float(V[:, 1].min())
    c = V[F].mean(1)
    _, area = face_normals(V, F)
    yc = chin_y + centre_frac * (top - chin_y)
    ring = np.abs(c[:, 1] - yc) < 0.03 * H
    cxz = c[ring][:, [0, 2]].mean(0) if ring.any() else c[:, [0, 2]].mean(0)
    centre = np.array([cxz[0], yc, cxz[1]])
    d = c - centre
    r = np.linalg.norm(d, axis=1)
    u = d / np.maximum(r, 1e-12)[:, None]
    th = np.arccos(np.clip(u[:, 1], -1, 1))
    ph = np.arctan2(u[:, 0], u[:, 2])
    NT, NP = 36, 72
    bt = np.minimum((th / math.pi * NT).astype(int), NT - 1)
    bp = ((ph + math.pi) / (2 * math.pi) * NP).astype(int) % NP
    rmin = np.full((NT, NP), np.inf)
    np.minimum.at(rmin, (bt, bp), r)
    # near the poles a row's bins are slivers: the few that hold a scalp face would leave the rest at
    # the hair's radius (the crown read as scalp), so such a row takes its smallest radius everywhere
    for t in range(NT):
        row = rmin[t][np.isfinite(rmin[t])]
        if math.sin((t + 0.5) / NT * math.pi) < 0.25 and len(row):
            rmin[t] = row.min()
    fin = np.isfinite(rmin)
    fill = np.where(fin, rmin, np.median(rmin[fin]) if fin.any() else 0.0)
    rs = _median_filter_wrap(fill)[bt, bp]
    lab = srgb_to_lab(rgb)
    dh = np.linalg.norm(lab - srgb_to_lab(hair_rgb), axis=1)
    ds = np.linalg.norm(lab - srgb_to_lab(skin_rgb), axis=1)
    haircol = dh < ds
    yaw = np.degrees(np.abs(np.arctan2(d[:, 0], d[:, 2])))
    face = (yaw < face_yaw) & (c[:, 1] < chin_y + face_top * (top - chin_y))
    haircol = haircol & ~face
    hair = haircol & (r > rs + delta * H) & (c[:, 1] > chin_y)
    a, b = edge_face_pairs(F)
    deg = np.bincount(a, minlength=len(F)) + np.bincount(b, minlength=len(F))
    for _ in range(smooth):
        h = hair.astype(float)
        nb = np.bincount(a, weights=h[b], minlength=len(F)) + np.bincount(b, weights=h[a], minlength=len(F))
        share = nb / np.maximum(deg, 1)
        hair = np.where(deg > 0, np.where(share > 0.5, True, np.where(share < 0.5, False, hair)), hair) & haircol
    lab_c = face_components(F, hair)
    total = float(area[hair].sum())
    returned = 0.0
    if total > 0:
        sizes = np.bincount(lab_c[hair], weights=area[hair])
        small = sizes < island_frac * total
        drop = hair & small[np.maximum(lab_c, 0)]
        returned = float(area[drop].sum() / total)
        hair = hair & ~drop
    comps = face_components(F, hair)
    n_comp = int(comps.max() + 1) if hair.any() else 0
    sizes = np.bincount(comps[hair], weights=area[hair]) if hair.any() else np.zeros(1)
    dirs = dome_dirs()
    t_head, _ = ray_hits(centre, dirs, V, F[~hair])
    t_hair, _ = ray_hits(centre, dirs, V, F[hair]) if hair.any() else (np.full(len(dirs), np.inf), None)
    stats = {"delta": delta, "centre": centre.round(5).tolist(), "hair_faces": int(hair.sum()),
             "hair_area_share": round(float(area[hair].sum() / area.sum()), 4),
             "hair_coloured_share": round(float(area[haircol].sum() / area.sum()), 4),
             "face_share": round(float(area[face].sum() / area.sum()), 4),
             "islands_returned": round(returned, 4), "components_all": n_comp,
             "components": int((sizes >= 0.02 * sizes.sum()).sum()) if hair.any() else 0,
             "largest_share": round(float(sizes.max() / sizes.sum()), 4) if hair.any() else 0.0,
             "head_top_closed": round(float(np.isfinite(t_head).mean()), 4),
             "hair_coverage": round(float(np.isfinite(t_hair).mean()), 4)}
    stats["gates"] = [
        {"name": "hair.islands_returned", "value": stats["islands_returned"], "limit": "<= 0.10",
         "pass": stats["islands_returned"] <= 0.10},
        {"name": "hair.components", "value": stats["components"], "limit": "1..3 holding >= 2 % of the hair each",
         "pass": 1 <= stats["components"] <= 3},
        {"name": "head.top_closed", "value": stats["head_top_closed"], "limit": ">= 0.95",
         "pass": stats["head_top_closed"] >= 0.95},
        {"name": "hair.coverage", "value": stats["hair_coverage"], "limit": ">= 0.90",
         "pass": stats["hair_coverage"] >= 0.90},
    ]
    return hair, stats


# ------------------------------------------------------------------------------------ seam colour
SEAM_HUE_MAX = 20.0     # a neck cell whose sides differ more than this in colour (CIELAB, lightness at a
                        # quarter: shade is allowed) is two materials (a scarf, a collar): left alone
SEAM_SKIN_DE = 35.0     # a sample counts as skin within this of the plan's skin colour (and nearer it than hair)


def srgb_to_linear(c):
    c = np.clip(np.asarray(c, float), 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, float), 0.0, 1.0)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


def sample_surface_uv(V, F, UVc, n, rng, face_mask=None):
    """sample_surface with the UV of each point: (points, normals, face ids, uv). UVc (m, 3, 2) per corner."""
    fn, area = face_normals(V, F)
    pool = np.arange(len(F)) if face_mask is None else np.nonzero(face_mask)[0]
    fi = rng.choice(pool, size=n, p=area[pool] / area[pool].sum())
    s, r2 = np.sqrt(rng.random(n)), rng.random(n)
    w = np.c_[1 - s, s * (1 - r2), s * r2]
    return (V[F[fi]] * w[:, :, None]).sum(1), fn[fi], fi, (UVc[fi] * w[:, :, None]).sum(1)


def sample_texture(image, uv):
    """Bilinear colour (n, 3) at UVs (n, 2); image (h, w, >=3) with rows bottom-up as Blender stores
    them (row = v x h, texel centres at (i + 0.5) / size); u and v wrap."""
    h, w = image.shape[:2]
    x = np.mod(uv[:, 0], 1.0) * w - 0.5
    y = np.mod(uv[:, 1], 1.0) * h - 0.5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    xa, xb = x0 % w, (x0 + 1) % w
    ya, yb = y0 % h, (y0 + 1) % h
    I = image[..., :3]
    return (I[ya, xa] * (1 - fx) * (1 - fy) + I[ya, xb] * fx * (1 - fy) + I[yb, xa] * (1 - fx) * fy
            + I[yb, xb] * fx * fy)


def uv_raster(uv_tri, vals, h, w):
    """Rasterise triangles in UV space onto an h x w texture (rows bottom-up, texel centres at
    (i + 0.5) / size), interpolating per-corner values: (out (h, w, k), covered (h, w)). uv_tri (m, 3, 2),
    vals (m, 3, k). A triangle is moved by whole tiles so its centroid lies in [0, 1); one smaller than a
    texel still marks the texel under its centroid."""
    vals = np.asarray(vals, float)
    out = np.zeros((h, w, vals.shape[2]))
    cov = np.zeros((h, w), bool)
    P = np.asarray(uv_tri, float).copy()
    P -= np.floor(P.mean(1, keepdims=True))
    P = P * [w, h] - 0.5
    for t in range(len(P)):
        a, b, c = P[t]
        x0, x1 = max(int(np.ceil(P[t, :, 0].min())), 0), min(int(np.floor(P[t, :, 0].max())), w - 1)
        y0, y1 = max(int(np.ceil(P[t, :, 1].min())), 0), min(int(np.floor(P[t, :, 1].max())), h - 1)
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        hit = False
        if x1 >= x0 and y1 >= y0 and abs(den) > 1e-12:
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
            l1 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / den
            l2 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / den
            l3 = 1 - l1 - l2
            ins = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
            if ins.any():
                out[gy[ins], gx[ins]] = (l1[ins, None] * vals[t, 0] + l2[ins, None] * vals[t, 1]
                                         + l3[ins, None] * vals[t, 2])
                cov[gy[ins], gx[ins]] = True
                hit = True
        if not hit:
            cx, cy = P[t].mean(0)
            xi, yi = int(np.clip(round(cx), 0, w - 1)), int(np.clip(round(cy), 0, h - 1))
            out[yi, xi] = vals[t].mean(0)
            cov[yi, xi] = True
    return out, cov


def grow_raster(out, cov, px=2):
    """Grow a raster px texels into uncovered texels (4-neighbours, wrapping), so bilinear and mip
    sampling at a UV island's edge read the new values."""
    out, cov = out.copy(), cov.copy()
    for _ in range(px):
        grown = cov.copy()
        for sh in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            take = np.roll(cov, sh, (0, 1)) & ~grown
            out[take] = np.roll(out, sh, (0, 1))[take]
            grown |= take
        cov = grown
    return out, cov


def _skin_keep(C, skin_rgb, hair_rgb, ref_lab=None):
    """Samples that read as skin: within SEAM_SKIN_DE of the plan's skin colour and nearer it than the
    hair's; without plan colours, within SEAM_SKIN_DE of ref_lab (the other side's median)."""
    lab = srgb_to_lab(C)
    if skin_rgb is None:
        return np.linalg.norm(lab - ref_lab, axis=1) <= SEAM_SKIN_DE
    ds = np.linalg.norm(lab - srgb_to_lab(np.asarray(skin_rgb, float)), axis=1)
    keep = ds <= SEAM_SKIN_DE
    if hair_rgb is not None:
        keep &= ds < np.linalg.norm(lab - srgb_to_lab(np.asarray(hair_rgb, float)), axis=1)
    return keep


def _theta(P, axis_xz):
    return np.arctan2(P[:, 0] - axis_xz[0], P[:, 2] - axis_xz[1])        # 0 = the front (+Z)


def seam_colour_field(Pp, Cp, Pa, Ca, axis_xz, cut_y, radius, y_lo, step, ny, skin_rgb=None, hair_rgb=None,
                      n_theta=24, min_n=4, blur=1):
    """The colour the part's neck should add to read as the anchor at the seam, on a cylinder grid
    (n_theta angles from the front, ny rows of `step` from y_lo), linear RGB, from each side's skin
    samples (medians). Below cut_y the target is the anchor at the same place; at and above it, the
    anchor's rim (its skin from cut_y - 0.3 x radius to cut_y, per angle): the anchor's stump is what
    shows under the part's neck, and the part must start from it. A cell with too few samples on
    either side, or whose sides differ by more than SEAM_HUE_MAX (two materials, not one skin in two
    shades), holds 0; the grid is then box-blurred `blur` times around the neck (never in height: a
    painted edge stays sharp in the field). Pp, Pa (n, 3) points; Cp, Ca (n, 3) sRGB 0..1.
    Returns (field (n_theta, ny, 3) or None, stats)."""
    axis_xz = np.asarray(axis_xz, float)
    lab_a = srgb_to_lab(Ca)
    kp = _skin_keep(Cp, skin_rgb, hair_rgb, np.median(lab_a, 0))
    ka = _skin_keep(Ca, skin_rgb, hair_rgb, np.median(srgb_to_lab(Cp), 0))
    tp = np.floor((_theta(Pp, axis_xz) + math.pi) / (2 * math.pi) * n_theta).astype(int) % n_theta
    ta = np.floor((_theta(Pa, axis_xz) + math.pi) / (2 * math.pi) * n_theta).astype(int) % n_theta
    rp = np.floor((Pp[:, 1] - y_lo) / step).astype(int)
    ra = np.floor((Pa[:, 1] - y_lo) / step).astype(int)
    rim = ka & (Pa[:, 1] >= cut_y - 0.3 * radius) & (Pa[:, 1] <= cut_y)
    lin_p, lin_a = srgb_to_linear(Cp), srgb_to_linear(Ca)
    field = np.zeros((n_theta, ny, 3))
    used, refused = 0, 0
    for t in range(n_theta):
        at, pt = ka & (ta == t), kp & (tp == t)
        rim_t = rim & (ta == t)
        for row in range(ny):
            sp = pt & (rp == row)
            above = y_lo + (row + 0.5) * step >= cut_y
            sa = rim_t if above else at & (ra == row)
            if sp.sum() < min_n or sa.sum() < min_n:
                continue
            mp, ma = np.median(lin_p[sp], 0), np.median(lin_a[sa], 0)
            d = srgb_to_lab(linear_to_srgb(ma)) - srgb_to_lab(linear_to_srgb(mp))
            if np.linalg.norm(d * [0.25, 1.0, 1.0]) > SEAM_HUE_MAX:
                refused += 1
                continue
            field[t, row] = ma - mp
            used += 1
    stats = {"cells": n_theta * ny, "cells_used": used, "cells_refused": refused,
             "skin_samples": [int(kp.sum()), int(ka.sum())]}
    if not used:
        return None, stats
    for _ in range(blur):
        field = (np.roll(field, 1, 0) + field + np.roll(field, -1, 0)) / 3.0
    return field, stats


def field_at(field, P, axis_xz, y_lo, step):
    """The field (n_theta, ny, 3) at points P, bilinear (wrapping in angle, clamped in height)."""
    n_theta, ny = field.shape[:2]
    a = (_theta(P, np.asarray(axis_xz, float)) + math.pi) / (2 * math.pi) * n_theta - 0.5
    b = np.clip((P[:, 1] - y_lo) / step - 0.5, 0, ny - 1)
    a0, b0 = np.floor(a).astype(int), np.minimum(np.floor(b).astype(int), max(ny - 2, 0))
    fa, fb = (a - a0)[:, None], np.clip(b - b0, 0, 1)[:, None]
    a1, b1 = (a0 + 1) % n_theta, np.minimum(b0 + 1, ny - 1)
    a0 %= n_theta
    return (field[a0, b0] * (1 - fa) * (1 - fb) + field[a1, b0] * fa * (1 - fb) + field[a0, b1] * (1 - fa) * fb
            + field[a1, b1] * fa * fb)


def seam_weight(P, axis_xz, radius, cut_y, fade_top):
    """How much of the anchor's neck colour a point of the part takes: 1 up to cut_y + 0.15 x radius
    (just above the anchor's rim) fading to 0 at fade_top, times 1 within 1.3 x radius of the neck
    axis fading to 0 at 1.8 x (the face keeps its own)."""
    rho = np.linalg.norm(P[:, [0, 2]] - np.asarray(axis_xz, float), axis=1)
    full = min(cut_y + 0.15 * radius, fade_top - 1e-9)
    wy = _smooth01((fade_top - P[:, 1]) / (fade_top - full))
    return wy * _smooth01((1.8 * radius - rho) / (0.5 * radius))


def apply_seam_colour(image, uv_tri, xyz_tri, field, axis_xz, radius, cut_y, fade_top, y_lo, step, grow_px=2):
    """Add the weighted field to the part's texels near the neck (linear RGB): the texels of the given
    triangles (uv_tri (m, 3, 2), their points xyz_tri (m, 3, 3)), grown grow_px. Returns (image, texels changed)."""
    h, w = image.shape[:2]
    pos, cov = uv_raster(uv_tri, xyz_tri, h, w)
    pos, cov = grow_raster(pos, cov, grow_px)
    ys, xs = np.nonzero(cov)
    P = pos[ys, xs]
    wt = seam_weight(P, axis_xz, radius, cut_y, fade_top)
    sel = wt > 1e-4
    ys, xs, P, wt = ys[sel], xs[sel], P[sel], wt[sel]
    out = np.array(image, dtype=np.float32, copy=True)
    lin = srgb_to_linear(out[ys, xs, :3]) + wt[:, None] * field_at(field, P, axis_xz, y_lo, step)
    out[ys, xs, :3] = linear_to_srgb(lin)
    return out, int(len(ys))


def seam_colour_report(Pp, Cp, Cp_after, Pa, Ca, axis_xz, radius, cut_y, fade_top, skin_rgb=None, hair_rgb=None,
                       open_p=None, n_sectors=12, min_n=20):
    """What a person sees at the seam, per 30-degree sector around the neck with enough skin on both
    sides and the seam in the open (open_p: per part sample, nothing of the anchor outside it, e.g. a
    hood's collar; None = all open); the worst sector is reported. delta = CIELAB distance between the
    part's median skin just above cut_y (to cut_y + 0.15 x radius) and the anchor's rim (cut_y - 0.3 x
    radius .. cut_y), before and after; edge_L = the sharpest lightness change going up from the
    anchor's rim through the part's rows 0.1 x radius tall to fade_top (a painted edge or a mismatched
    rim reads as one big jump)."""
    axis_xz = np.asarray(axis_xz, float)
    lab_a = srgb_to_lab(Ca)
    kp = _skin_keep(Cp, skin_rgb, hair_rgb, np.median(lab_a, 0))
    ka = _skin_keep(Ca, skin_rgb, hair_rgb, np.median(srgb_to_lab(Cp), 0))
    lab_p, lab_q = srgb_to_lab(Cp), srgb_to_lab(Cp_after)
    open_p = np.ones(len(Pp), bool) if open_p is None else np.asarray(open_p, bool)
    sp = np.floor((_theta(Pp, axis_xz) + math.pi) / (2 * math.pi) * n_sectors).astype(int) % n_sectors
    sa = np.floor((_theta(Pa, axis_xz) + math.pi) / (2 * math.pi) * n_sectors).astype(int) % n_sectors
    bp = (Pp[:, 1] >= cut_y) & (Pp[:, 1] <= cut_y + 0.15 * radius)
    ba = (Pa[:, 1] >= cut_y - 0.3 * radius) & (Pa[:, 1] <= cut_y)
    dy = 0.1 * radius
    nb = max(int(math.ceil((fade_top - cut_y) / dy)), 1)
    rp = np.floor((Pp[:, 1] - cut_y) / dy).astype(int)

    def edge(la, lab, m):
        Ls = [la[0]] + [np.median(lab[m & (rp == i), 0]) if (m & (rp == i)).sum() >= 3 else np.nan for i in range(nb)]
        d = np.abs(np.diff(np.array(Ls)[np.isfinite(Ls)]))
        return float(d.max()) if len(d) else None

    rows = []
    for s in range(n_sectors):
        mp, ma = kp & bp & (sp == s), ka & ba & (sa == s)
        if mp.sum() < min_n or ma.sum() < min_n or open_p[mp].mean() < 0.5:
            continue
        la = np.median(lab_a[ma], 0)
        rows.append({"sector_deg": int(round((s + 0.5) * 360 / n_sectors - 180)),
                     "open": float(open_p[mp].mean()),
                     "delta_before": float(np.linalg.norm(np.median(lab_p[mp], 0) - la)),
                     "delta_after": float(np.linalg.norm(np.median(lab_q[mp], 0) - la)),
                     "edge_L_before": edge(la, lab_p, kp & (sp == s)), "edge_L_after": edge(la, lab_q, kp & (sp == s))})
    rep = {"sectors": len(rows), "per_sector": [{k: (round(v, 2) if isinstance(v, float) else v)
                                                 for k, v in r.items()} for r in rows]}
    for key in ("delta_before", "delta_after", "edge_L_before", "edge_L_after"):
        vals = [r[key] for r in rows if r.get(key) is not None]
        if vals:
            rep[key] = round(max(vals), 2)
    return rep


# --------------------------------------------------------------------------------------- the plan
def check_plan(plan, for_tool="part_math"):
    """The validity rules beyond the schema; raises Refused with the reason."""
    if not isinstance(plan, dict) or plan.get("schema") != "parts/1":
        raise Refused("not a parts/1 plan")
    tier = plan.get("tier")
    if tier in RESERVED_TIERS:
        raise Refused(f"tier {tier!r} is reserved, not built yet")
    if tier not in TIERS:
        raise Refused(f"unknown tier {tier!r}; known {sorted(TIERS)}")
    parts = plan.get("parts") or []
    names = [p.get("name") for p in parts]
    if len(set(names)) != len(names):
        raise Refused("part names must be unique")
    if sum(1 for p in parts if p.get("source") == "anchor") != 1:
        raise Refused("exactly one part has source anchor")
    regions = {p.get("region") for p in parts}
    outside = regions - set(REGIONS_NOW) - (set(FINE_REGIONS) if tier == "fine" else set())
    if outside & set(UNBUILT_REGIONS):
        raise Refused(f"regions {sorted(outside & set(UNBUILT_REGIONS))} are not built from a plan: eyeballs come from blender-character-rig eye_fit.py fit, not a plan part; accessories are reserved")
    if outside:
        raise Refused(f"regions {sorted(outside)} are for tier fine" if tier != "fine" else f"unknown regions {sorted(outside)}")
    want = {p["region"] for p in TIERS[tier]}
    if tier == "fine":           # three's regions plus either hand or both
        want = set(REGIONS_NOW) | (regions & set(FINE_REGIONS))
    if regions != want:
        raise Refused(f"tier {tier} takes the regions {sorted(want)}, the plan has {sorted(regions)}")
    by = {p["name"]: p for p in parts}
    hair_sources = {p.get("from") for p in parts if p.get("source") == "split"}
    for p in parts:
        if p.get("source") == "split" and by.get(p.get("from"), {}).get("source") != "generate":
            raise Refused(f"part {p['name']}: split from {p.get('from')!r}, which is not a generated part")
        if p.get("source") == "generate":
            if p.get("preset") not in PRESETS:
                raise Refused(f"part {p['name']}: preset {p.get('preset')!r} is not one of {PRESETS}")
            if p.get("preset") == "Large" and (p.get("region") == "head" or p["name"] in hair_sources):
                raise Refused(f"part {p['name']} carries hair: preset Large shrinks the spikes; use Template or Showcase")
        mode = (p.get("seam") or {}).get("mode")
        if mode not in (None, "overlap", "bridge", "none"):
            raise Refused(f"part {p['name']}: seam mode {mode!r}")
    if sum(float(p.get("budget_share", 0)) for p in parts) > 1.0 + 1e-9:
        raise Refused("budget shares sum to more than 1")
    if tier != "whole" and "anchor" not in plan:
        raise Refused("the plan has no anchor measurements: run part_math.py plan")


def plan_core(V, F, masks, tier, character, margin_frac=0.1, band_step=0.002, hood_grow=0.08):
    """Everything `plan` derives from a welded anchor and its clean masks (bool arrays per view), as a
    dict: anchor measurements, parts, per-part crop boxes and keep masks (arrays, not yet written)."""
    if tier in RESERVED_TIERS:
        raise Refused(f"tier {tier!r} is reserved, not built yet")
    if tier not in TIERS:
        raise Refused(f"unknown tier {tier!r}")
    neck = neck_band(V, F, step=band_step)
    seam = seam_heights(neck, margin_frac)
    frame = fit_frame(V, F, masks)
    bad = {v: i for v, i in frame["iou"].items() if i < FRAME_IOU_MIN}
    anchor = {"frame": frame, "bbox_min": V.min(0).round(5).tolist(), "bbox_max": V.max(0).round(5).tolist(),
              "head_height": seam["head_height"],
              "neck": {"band": neck["band"], "axis_xz": neck["axis_xz"], "radius": neck["radius"],
                       "collar": neck["collar"], **({"collar_top": neck["collar_top"]} if neck["collar"] else {})}}
    if neck.get("covered"):
        anchor["neck"]["covered"] = neck["covered"]
    parts = json.loads(json.dumps(TIERS[tier]))
    keep = {}
    hw = 1.5 * (neck["head_top"] - seam["cut_y"])
    region, info = region_faces(V, F, seam["cut_y"], neck["axis_xz"], neck["radius"], box=(hw, hw))
    hang, hang_info = hanging_faces(V, F, region, seam["cut_y"], seam["part_bottom_y"], neck["axis_xz"],
                                    neck["radius"])
    still = None
    if neck.get("covered"):
        cy = V[F].mean(1)[:, 1]
        still = (cy <= seam["cut_y"]) & (cy > seam["part_bottom_y"]) & ~hang & \
            (np.linalg.norm(V[F].mean(1)[:, [0, 2]] - np.asarray(neck["axis_xz"]), axis=1) <= 1.5 * neck["radius"])
    warnings = []
    if neck.get("covered"):
        c = neck["covered"]
        warnings.append(f"neck: covered below the band down to y {c['to_y']} ({c['nested_rows']} of {c['rows']} rows "
                        f"hold up to {c['children_max']} nested loops: a stand collar or hair fused to the nape); the "
                        f"band sits on the jaw, the head part's neck reaches the cover's foot (y {c['foot_y']})")
    if hang_info:
        warnings.append(f"hair hangs below the cut outside the neck ({len(hang_info)} piece(s), e.g. a ponytail): the "
                        f"head views keep it down to the part's bottom; the anchor keeps the rest")
    for p in parts:
        if p["region"] != "head":
            continue
        p["region_box"] = {"y_min": seam["part_bottom_y"], "y_max": neck["head_top"]}
        p["seam"] = {"mode": "overlap" if neck["collar"] else "bridge", "cut_y": seam["cut_y"],
                     "part_bottom_y": seam["part_bottom_y"], "margin_frac": margin_frac}
        cb = crop_boxes(V, F, region | hang, frame, seam["part_bottom_y"])
        p["views"] = {"source": "clean-views", "box_side_px": cb["box_side_px"], "boxes": cb["boxes"],
                      "clip_row_px": cb["clip_row_px"], "dir": f"views/{p['name']}"}
        if hang_info:     # the views keep these below the chin, outside the neck column (hang_<view>.png)
            p["views"]["hanging"] = {"pieces": hang_info,
                                     "masks": {v: f"views/{p['name']}/hang_{v}.png" for v in VIEWS}}
        keep[p["name"]] = {}
        for view in VIEWS:
            m = masks[view]
            cx, cy = frame["offset_px"][view]
            sil = keep_mask(V, F, region, view, m, (frame["units_per_px"], cx, cy),
                            hood_grow * seam["head_height"] / frame["units_per_px"], still=still,
                            hang=hang if hang_info else None)
            x0, y0, x1, y1 = cb["boxes"][view]
            sx0, sy0 = max(x0, 0), max(y0, 0)
            sx1, sy1 = min(x1, m.shape[1]), min(y1, m.shape[0])
            for key, img in zip(("", "hang_"), sil if hang_info else (sil,)):
                out = np.zeros((y1 - y0, x1 - x0), bool)
                out[sy0 - y0: sy1 - y0, sx0 - x0: sx1 - x0] = img[sy0:sy1, sx0:sx1]
                keep[p["name"]][key + view] = out
    hands = None
    if any(p["region"] in ("hand.L", "hand.R") for p in parts):
        import hand_parts       # forearm slices, wrist planes, hand boxes and keep masks (same folder)
        hands = hand_parts.plan_hands(V, F, masks, frame, anchor, parts, keep)
    doc = {"schema": "parts/1", "character": character, "tier": tier, "anchor": anchor, "parts": parts}
    return doc, keep, {"neck_profile": neck["profile"], "region": info, "frame_bad": bad, "hands": hands,
                       "warnings": warnings}


def read_masks(views_dir):
    """The clean view masks, matched by view name (`*front*mask*.png`); ambiguity is refused."""
    from PIL import Image
    names = sorted(os.listdir(views_dir))
    masks = {}
    for view in VIEWS:
        hits = [n for n in names if view in n.lower() and "mask" in n.lower() and n.lower().endswith(".png")]
        if len(hits) != 1:
            raise Refused(f"{views_dir}: {len(hits)} masks match '{view}' ({hits[:4]}); want exactly one")
        a = np.asarray(Image.open(os.path.join(views_dir, hits[0])).convert("L"))
        masks[view] = a > 127
    return masks


def cmd_plan(args):
    if not os.path.isfile(args.anchor):
        return 3, {"error": f"no file {args.anchor}"}
    if not os.path.isdir(args.views):
        return 3, {"error": f"no folder {args.views}"}
    try:
        g = read_glb(args.anchor)
        masks = read_masks(args.views)
    except Refused as exc:
        return 1, {"refused": str(exc)}
    except (OSError, ValueError, KeyError) as exc:
        return 3, {"error": f"unreadable input: {exc}"}
    V, F, _ = weld(g["V"], g["F"])
    try:
        doc, keep, extra = plan_core(V, F, masks, args.tier, args.character, args.margin_frac, args.band_step,
                                     args.hood_grow)
    except Refused as exc:
        return 1, {"refused": str(exc)}
    except GateFailed as exc:
        return 2, {"gate_failed": str(exc)}
    out_dir = os.path.dirname(os.path.abspath(args.out))
    doc["anchor"] = {"glb": os.path.relpath(os.path.abspath(args.anchor), out_dir),
                     "glb_sha256": sha256(args.anchor), **doc["anchor"]}
    if getattr(args, "painted", None):
        if not os.path.isfile(args.painted):
            return 3, {"error": f"no file {args.painted}"}
        doc["anchor"]["painted_glb"] = os.path.relpath(os.path.abspath(args.painted), out_dir)
    check_plan(doc)
    for part, views in keep.items():
        d = os.path.join(out_dir, "views", part)
        os.makedirs(d, exist_ok=True)
        for view, m in views.items():
            write_png_gray(os.path.join(d, view + ".png" if view.startswith("hang_") else f"keep_{view}.png"), m)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1)
    code = 2 if extra["frame_bad"] else 0
    res = {"plan": args.out, "neck": doc["anchor"]["neck"], "frame": doc["anchor"]["frame"],
           "region": {"deleted": extra["region"]["deleted"][:4]}, "warnings": extra["warnings"]}
    if extra["frame_bad"]:
        res["gate_failed"] = f"part.frame_fit: IoU under {FRAME_IOU_MIN} in {extra['frame_bad']}"
    return code, res


def load_plan(path):
    """(plan dict, folder) after the validity rules; refuses a stale anchor hash."""
    with open(path, encoding="utf-8") as handle:
        plan = json.load(handle)
    check_plan(plan)
    base = os.path.dirname(os.path.abspath(path))
    if plan["tier"] != "whole":
        glb = os.path.join(base, plan["anchor"]["glb"])
        if not os.path.isfile(glb):
            raise Refused(f"the plan's anchor {glb} is missing")
        if plan["anchor"].get("glb_sha256") and sha256(glb) != plan["anchor"]["glb_sha256"]:
            raise Refused("the anchor changed since the plan was written (sha256 differs): run part_math.py plan again")
    return plan, base


# ------------------------------------------------------------------------------------- synthetic
def _grid_surface(fn, nu, nv, wrap_u=True):
    """A (nu x nv) parametric surface fn(u, v) -> (n,3) with u in [0,1) (wrapped) and v in [0,1]."""
    us = np.arange(nu) / nu if wrap_u else np.linspace(0, 1, nu)
    vs = np.linspace(0, 1, nv)
    U, Vv = np.meshgrid(us, vs, indexing="ij")
    P = fn(U.reshape(-1), Vv.reshape(-1))
    idx = np.arange(nu * nv).reshape(nu, nv)
    i1 = np.roll(idx, -1, 0) if wrap_u else idx[1:]
    i0 = idx if wrap_u else idx[:-1]
    a, b = i0[:, :-1], i1[:, :-1]
    c, d = i1[:, 1:], i0[:, 1:]
    F = np.r_[np.c_[a.reshape(-1), b.reshape(-1), c.reshape(-1)], np.c_[a.reshape(-1), c.reshape(-1), d.reshape(-1)]]
    return P, F


def revolve(profile, n_az=48, n_v=120, axis=(0.0, 0.0), inward=False):
    """A surface of revolution about the Y axis at axis (x, z): profile(v) -> (radius, y) for v in 0..1.
    inward flips the faces (an inner shell)."""
    def fn(u, v):
        r, y = profile(v)
        a = 2 * math.pi * u
        return np.c_[axis[0] + r * np.sin(a), y, axis[1] + r * np.cos(a)]
    P, F = _grid_surface(fn, n_az, n_v)
    return P, (F[:, ::-1] if inward else F)


def swept_ring(r0, r1, y0, y1, a0, a1, n):
    """A closed solid ring segment (rectangular section r0..r1 x y0..y1) swept about the Y axis from angle
    a0 to a1, ends capped: a hood's collar (open at the front when the arc leaves a gap)."""
    sec = np.array([[r1, y0], [r1, y1], [r0, y1], [r0, y0]])
    angs = np.linspace(a0, a1, n + 1)
    V = np.array([[r * math.sin(a), y, r * math.cos(a)] for a in angs for r, y in sec])
    F = []
    for i in range(n):
        for k in range(4):
            a, b = 4 * i + k, 4 * i + (k + 1) % 4
            c, d = a + 4, b + 4
            F += [[a, c, d], [a, d, b]]
    last = 4 * n
    F += [[0, 2, 1], [0, 3, 2], [last, last + 1, last + 2], [last, last + 2, last + 3]]
    return V, np.array(F)


def merge(*meshes):
    Vs, Fs, off = [], [], 0
    for V, F in meshes:
        Vs.append(V)
        Fs.append(F + off)
        off += len(V)
    return np.vstack(Vs), np.vstack(Fs)


def synthetic_figure(res=1, neck_bottom=None, head_scale=1.0, spikes=0.15, collar=True, seed=0, neck_r=0.033):
    """A test character in the anchor's frame (about 1 unit tall, +Y up, facing +Z): a revolved body,
    neck and head as one double shell (inner wall 0.005 inside), a U-shaped collar ring around the
    neck, and a hair cap (spikes `spikes` x head radius high) on the head. res multiplies the
    tessellation. neck_bottom given: only the head and neck down to that height (a part job);
    neck_r is the neck radius.
    Returns (V, F, face_kind) with kind 0 body/skin, 1 hair-coloured scalp, 2 collar, 3 the hair cap."""
    rng = np.random.default_rng(seed)
    R_head, y_head, r_neck = 0.075 * head_scale, 0.42, neck_r

    def prof(v):
        y = -0.48 + v * (0.495 - -0.48)
        r = np.where(y < 0.22, 0.15, 0.0)
        t = np.clip((y - 0.22) / 0.03, 0, 1)
        r = np.where((y >= 0.22) & (y < 0.25), 0.15 + (r_neck - 0.15) * t, r)
        r = np.where((y >= 0.25) & (y < 0.355), r_neck, r)
        dy = np.clip(y - y_head, -R_head, R_head)
        sph = np.sqrt(np.maximum(R_head ** 2 - dy ** 2, 0))
        blend = np.clip((y - 0.355) / 0.02, 0, 1)
        r = np.where(y >= 0.355, (1 - blend) * r_neck + blend * np.maximum(sph, r_neck * (1 - blend)), r)
        r = np.where(y >= y_head + R_head - 1e-6, 0.0, r)
        return np.maximum(r, 1e-4), np.minimum(y, y_head + R_head)

    def prof_part(v):                                  # a drawn neck: a straight cylinder below the head
        y0 = neck_bottom
        y = y0 + v * (y_head + R_head - y0)
        r, _ = prof((y + 0.48) / (0.495 + 0.48))
        return np.where(y < 0.355, r_neck, r), y

    p = prof if neck_bottom is None else prof_part
    n_az, n_v = 32 * res, (160 if neck_bottom is None else 60) * res
    outer = revolve(p, n_az, n_v)

    def inner_prof(v):
        r, y = p(v)
        return np.maximum(r - 0.005, 1e-4), y

    inner = revolve(inner_prof, n_az, n_v, inward=True)
    parts = [outer, inner]
    kinds = [np.zeros(len(outer[1]), int), np.zeros(len(inner[1]), int)]
    if collar and neck_bottom is None:
        co = swept_ring(0.052, 0.058, 0.265, 0.345, math.radians(30), math.radians(330), 24 * res)
        parts.append(co)
        kinds.append(np.full(len(co[1]), 2))
    if spikes is not None:
        n_sp = 30
        az = rng.uniform(0, 2 * math.pi, n_sp)
        el = rng.uniform(math.radians(15), math.radians(85), n_sp)
        hgt = rng.uniform(0.6, 1.0, n_sp) * spikes

        def cap(u, v):
            a = 2 * math.pi * u
            e = math.radians(10) + v * math.radians(80)
            d = np.c_[np.cos(e) * np.sin(a), np.sin(e), np.cos(e) * np.cos(a)]
            sd = np.c_[np.cos(el) * np.sin(az), np.sin(el), np.cos(el) * np.cos(az)]
            ang = np.arccos(np.clip(d @ sd.T, -1, 1))
            bump = (np.clip(1 - ang / 0.35, 0, 1) * hgt[None]).max(1)
            rr = R_head * (1.0 + max(spikes, 0.0) * 0.45 + bump)
            return np.c_[0 + rr * d[:, 0], y_head + rr * d[:, 1], 0 + rr * d[:, 2]]
        cp = _grid_surface(cap, 72 * res, 24 * res)
        parts.append(cp)
        kinds.append(np.full(len(cp[1]), 3))
    V, F = merge(*parts)
    kind = np.concatenate(kinds)
    # break the head's symmetry about Y (registration needs it): an oval skull and a nose
    w = np.clip((V[:, 1] - 0.355) / 0.02, 0, 1)
    V = V.copy()
    V[:, 0] *= 1 - 0.08 * w
    V[:, 2] *= 1 + 0.10 * w
    nose = np.exp(-(V[:, 0] ** 2 + (V[:, 1] - 0.405) ** 2) / 0.012 ** 2) * (V[:, 2] > 0)
    V[:, 2] += 0.014 * nose * w
    c = V[F].mean(1)
    scalp = (kind == 0) & (c[:, 1] > y_head + 0.25 * R_head) & (np.linalg.norm(c[:, [0, 2]], axis=1) < R_head * 1.05)
    front = c[:, 2] > 0.55 * R_head
    kind[scalp & ~(front & (c[:, 1] < y_head + 0.6 * R_head))] = 1
    return V, F, kind


# --------------------------------------------------------------------------------------- selftest
def contract_sample(script, case, doc, suffix=".gate.json"):
    """Hand one selftest sample to tools/check-contracts.py: written to $UNITY_DEV_CONTRACT_OUT (else a fixed
    folder in the temp dir) as <script>__<case><suffix>, and named on stdout as `selftest-output: <path>`."""
    out = os.environ.get("UNITY_DEV_CONTRACT_OUT") or os.path.join(tempfile.gettempdir(), "unity-dev-contract-out")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{script}__{case}{suffix}")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1)
    print(f"selftest-output: {path}")


def _rot(axis, deg):
    a = np.asarray(axis, float)
    a /= np.linalg.norm(a)
    t = math.radians(deg)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K


def selftest():
    checks, failed = [], []

    def ok(name, cond, value=None):
        checks.append({"check": name, "pass": bool(cond), **({"value": value} if value is not None else {})})
        if not cond:
            failed.append(name)

    rng = np.random.default_rng(7)
    pl = [{"region": "body", "budget_share": 0.46}, {"region": "head", "budget_share": 0.22},
          {"region": "hair", "budget_share": 0.12}, {"region": "hand.R", "budget_share": 0.08}]
    ht = hair_target(pl, {"body": 56666, "head": 18839, "hair": 50298})
    ok("hair target: 0.12 / (0.80 - 0.12) x the body and head (the hands not built yet)",
       ht == int(0.12 / 0.68 * (56666 + 18839)), ht)
    ok("hair target: none without a hair share or with a present part unshared",
       hair_target(pl[:2], {"body": 1, "head": 1}) is None
       and hair_target(pl[1:3], {"body": 1, "head": 1, "hair": 1}) is None)
    # 1. registration: a lumpy ellipsoid "head" with a neck stub below the region (the part's own
    #    neck, which ICP must trim), a known similarity, noise, and a crop-only start
    nu, nv = 400, 200
    uu, vv = np.meshgrid(np.linspace(0, 2 * math.pi, nu, endpoint=False), np.linspace(1e-3, math.pi - 1e-3, nv),
                         indexing="ij")
    d = np.c_[(np.sin(vv) * np.sin(uu)).ravel(), np.cos(vv).ravel(), (np.sin(vv) * np.cos(uu)).ravel()]
    rr = (1 + 0.15 * np.sin(3 * d[:, 0]) * np.cos(2 * d[:, 1]) + 0.1 * np.sin(5 * d[:, 2])
          + 0.08 * np.cos(4 * d[:, 0] + 2 * d[:, 2]))
    Vq = d * rr[:, None] * np.array([0.09, 0.11, 0.1]) + np.array([0.0, 0.42, 0.0])
    ix = np.arange(nu * nv).reshape(nu, nv)
    q0, q1, q2, q3 = ix[:, :-1], np.roll(ix, -1, 0)[:, :-1], np.roll(ix, -1, 0)[:, 1:], ix[:, 1:]
    Fq = np.r_[np.c_[q0.ravel(), q1.ravel(), q2.ravel()], np.c_[q0.ravel(), q2.ravel(), q3.ravel()]]
    Q, Qn, _ = sample_surface(Vq, Fq, 100000, rng)
    h = float(np.ptp(Q[:, 1]))
    s_true, R_true, t_true = 0.83, _rot([0.3, 1, 0.2], 7.0), np.array([0.01, -0.02, 0.015])
    Pa, _, _ = sample_surface(Vq, Fq, 6000, rng)
    n_out = int(0.15 * len(Pa))
    Pa[:n_out] = np.c_[rng.normal(scale=0.03, size=n_out), Q[:, 1].min() - 0.01 - rng.random(n_out) * 0.05,
                       rng.normal(scale=0.03, size=n_out)]
    P = ((Pa - t_true) @ R_true) / s_true                  # part frame: s R P + t = Pa
    P += rng.normal(scale=0.001 * h / s_true, size=P.shape)
    s0, t0 = s_true * 1.10, t_true + np.array([0, 0.03 * h, 0])
    r = similarity_icp(P, Q, s0, np.eye(3), t0, Qn=Qn)
    ok("register: scale within 1 %", abs(r["s"] / s_true - 1) < 0.01, round(r["s"] / s_true, 4))
    ok("register: rotation within 0.5 deg", abs(rotation_deg(r["R"] @ R_true.T)) < 0.5,
       round(rotation_deg(r["R"] @ R_true.T), 3))
    ok("register: rms inside under 0.5 % of height", r["rms_inside"] < 0.005, round(r["rms_inside"], 5))
    r_bad = similarity_icp(P, Q, s_true * 1.4, np.eye(3), t0, Qn=Qn)
    ok("register: a 40 % off start fails the scale-ratio gate", abs(r_bad["s"] / (s_true * 1.4) - 1) > 0.05,
       round(r_bad["s"] / (s_true * 1.4), 3))

    # 2. neck band, collar, the cut and the inner shell
    V0, F0, kind = synthetic_figure(res=1)
    V, F, _ = weld(V0, F0)
    neck = neck_band(V, F, step=0.002)
    ok("neck: band on the planted neck (0.25..0.355, transitions within 1.2 radius)",
       0.24 <= neck["band"][0] <= 0.26 and 0.35 <= neck["band"][1] <= 0.365, neck["band"])
    ok("neck: radius near 0.033", abs(neck["radius"] - 0.033) < 0.004, neck["radius"])
    ok("neck: collar found", neck["collar"] is True and neck["collar_top"] is not None, neck["collar_top"])
    seam = seam_heights(neck)
    cut = seam["cut_y"]
    kill, info = region_faces(V, F, cut, neck["axis_xz"], neck["radius"], box=(0.2, 0.2))
    c = V[F].mean(1)
    loops_plain = loops_at(V, F[~kill], cut, 0.01, axis_xz=neck["axis_xz"], radius=neck["radius"])
    inner = inner_shell_faces(V, F, cut, 0.6 * neck["radius"], neck["radius"], neck["axis_xz"])
    loops_del = loops_at(V, F[~kill & ~inner], cut, 0.01, axis_xz=neck["axis_xz"], radius=neck["radius"])
    ok("cut: two loops at the cut without the inner-shell deletion", len(loops_plain) == 2, len(loops_plain))
    ok("cut: one loop after deleting the inner shell near the cut", len(loops_del) == 1, len(loops_del))
    ok("cut: the collar survives", not (kill & (kind == 2)).any(), int((kill & (kind == 2)).sum()))
    ys = np.linspace(cut, neck["collar_top"], 5)[1:]
    ok("cut: collar_kept 1.0 after the cut, 0 with the collar deleted",
       collar_kept(V, F, kill, ys, neck["axis_xz"], neck["radius"]) >= 0.99
       and collar_kept(V, F, kill | (kind == 2), ys, neck["axis_xz"], neck["radius"]) < 0.5)
    ok("cut: the head and hair go", kill[(c[:, 1] > 0.40)].all(), int(kill.sum()))
    ok("neck: a bare neck is not covered", neck["covered"] is None, neck["covered"])

    # 2b. a covered neck: the neck column as thick as the jaw (a collar fused to it) holds loose shells in its
    # wall (nested loops) from 0.27 to 0.35: the band sits above them on the jaw, the run below it is reported
    # and the part's neck reaches its foot
    Vc0, Fc0, _ = synthetic_figure(res=1, collar=False, spikes=None, neck_r=0.045)
    junk = [revolve(lambda v: (np.full_like(v, 0.0015), 0.27 + 0.08 * v), 8, 20,
                    axis=(0.0425 * math.sin(t), 0.0425 * math.cos(t))) for t in (-2.6, 3.1, 2.6)]
    Vc, Fc, _ = weld(*merge((Vc0, Fc0), *junk))
    nc = neck_band(Vc, Fc, step=0.002)
    cov = nc["covered"] or {}
    ok("neck: a covered neck is reported, the band above it, the seam at its foot",
       nc["band"][0] >= 0.345 and cov.get("to_y", 1) <= 0.275 and cov.get("nested_rows", 0) >= 30
       and nc["collar"] and seam_heights(nc)["part_bottom_y"] <= cov.get("foot_y", -1) + 1e-9
       and seam_heights(nc)["part_bottom_y"] < nc["band"][0] - 0.1 * (nc["head_top"] - nc["band"][1]),
       {"band": nc["band"], "covered": nc["covered"]})

    # 2c. hair hanging below the cut: a sheet behind the neck joined to the head above the cut hangs; one at the
    # neck (inside the disc) and one joined to kept faces (a hood) do not
    def sheet(z, x0=-0.02, x1=0.02, y0=0.30, y1=0.46, n=16):
        ys_, xs_ = np.linspace(y0, y1, n), np.linspace(x0, x1, 4)
        Vq = np.array([[x, y, z] for y in ys_ for x in xs_])
        Fq = [[i * 4 + j, i * 4 + j + 1, (i + 1) * 4 + j + 1] for i in range(n - 1) for j in range(3)]
        Fq += [[i * 4 + j, (i + 1) * 4 + j + 1, (i + 1) * 4 + j] for i in range(n - 1) for j in range(3)]
        return Vq, np.array(Fq)
    Vh, Fh = merge(sheet(-0.09), sheet(0.01), sheet(0.09))
    ch = Vh[Fh].mean(1)
    head_reg = (ch[:, 1] > 0.40) & (ch[:, 2] < 0.05)          # the third sheet's top is kept (not the head's)
    hang, hinfo = hanging_faces(Vh, Fh, head_reg, 0.40, 0.32, (0.0, 0.0), 0.03)
    ok("hang: the sheet behind the neck hangs; the neck's and the hood's do not",
       hang.any() and (ch[hang, 2] < -0.05).all() and (ch[hang, 1] > 0.32).all() and len(hinfo) == 1,
       hinfo)

    # 3. silhouettes
    frame = (1.063e-3, 512.0, 512.0)
    a = silhouette(V, F, "front", 1024, frame)
    ok("silhouette: a mesh against itself", iou(a, silhouette(V, F, "front", 1024, frame)) == 1.0)
    ctr = (V.min(0) + V.max(0)) / 2
    b = silhouette((V - ctr) * 1.1 + ctr, F, "front", 1024, frame)
    ok("silhouette: scaled 1.1 gives about 1/1.21 and fails 0.95", abs(iou(a, b) - 1 / 1.21) < 0.03 and iou(a, b) < 0.95,
       round(iou(a, b), 4))

    # 3b. which surface a view sees: two overlapping squares, the second nearer the front camera
    sq = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]], float)
    Vs = np.r_[sq, sq * [0.5, 0.5, 1] + [0.5, 0, 0.3]]
    Fs = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]])
    fr2 = (0.01, 128.0, 128.0)
    lf = label_raster(Vs, Fs, [1, 1, 2, 2], "front", 256, fr2)
    lb = label_raster(Vs, Fs, [1, 1, 2, 2], "back", 256, fr2)
    ok("label raster: the nearer square wins from the front, the farther from the back",
       lf[128, 178] == 2 and lb[128, 78] == 1 and lf[128, 60] == 1 and lb[128, 240] == 0,
       [int(lf[128, 178]), int(lb[128, 78])])
    km = keep_mask(Vs, Fs, np.array([True, True, False, False]), "front", np.ones((256, 256), bool), fr2, 10, 0)
    ok("keep mask: the nearer surface is cut out and grown upward",
       not km[128, 178] and not km[70, 178] and km[50, 178] and km[128, 60], [bool(km[70, 178]), bool(km[50, 178])])

    # 3c. the overlap seam's tuck: a stump (radius 1, open rim at y 1) under a slimmer part neck
    def tube(r, y0, y1, n=64, m=21):
        a = np.linspace(0, 2 * math.pi, n, endpoint=False)
        yy = np.linspace(y0, y1, m)
        Vt = np.array([[r * math.cos(t), y, r * math.sin(t)] for y in yy for t in a])
        Ft = []
        for j in range(m - 1):
            for i in range(n):
                p0, p1, p2, p3 = j * n + i, j * n + (i + 1) % n, (j + 1) * n + (i + 1) % n, (j + 1) * n + i
                Ft += [[p0, p1, p2], [p0, p2, p3]]
        return Vt, np.array(Ft)
    Va, Fa = tube(1.0, -1.0, 1.0)
    rim = np.nonzero(np.abs(Va[:, 1] - 1.0) < 1e-9)[0]
    for case, rp, want in (("slim", 0.9, True), ("thin", 0.6, False)):
        Vp, Fp = tube(rp, -0.5, 2.0, n=96)
        Vt, st = tuck_stump(Va, Fa, rim, Vp, Fp, np.zeros(2), 1.0, 0.0, 1.0)
        r_rim = np.linalg.norm(Vt[rim][:, [0, 2]], axis=1)
        low = np.nonzero(Va[:, 1] <= 1e-9)[0]
        if want:
            ok("tuck: a slightly slimmer neck: the rim goes just inside it, below the fade nothing moves",
               st["applied"] and np.all(r_rim < rp) and np.all(r_rim > 0.85 * rp)
               and np.allclose(Vt[low], Va[low]), [round(float(r_rim.max()), 4), st["shift_max"]])
        else:
            ok("tuck: a thin neck is refused (shift over the limit), nothing moves",
               not st["applied"] and st["shift_max"] > 0.25 and np.allclose(Vt, Va), st["shift_max"])
    Vp, Fp = tube(1.0, -0.47, 2.0, n=96)          # a part neck as wide as the stump: whole band, short ramp
    c_, s_ = math.cos(0.013), math.sin(0.013)     # off the stump's vertex angles: a ray along an edge can miss
    Vp = Vp @ np.array([[c_, 0, -s_], [0, 1, 0], [s_, 0, c_]])
    Vt, st = tuck_stump(Va, Fa, rim, Vp, Fp, np.zeros(2), 1.0, 0.0, 1.0, inset=0.9, ramp=0.35)
    r_all = np.linalg.norm(Vt[:, [0, 2]], axis=1)
    above, low = Va[:, 1] >= 0.35 - 1e-9, np.nonzero(Va[:, 1] <= 1e-9)[0]
    ok("tuck: a neck as wide as the stump: the whole band above the ramp goes to 0.9 of it, below stays",
       st["applied"] and np.all(r_all[above] < 0.91) and np.allclose(Vt[low], Va[low]),
       [round(float(r_all[above].max()), 4), st["shift_max"]])

    Vp, Fp = tube(0.95, -0.5, 3.0, n=96)
    Vp = Vp + [0.15, 0, 0]
    Vc, st = centre_neck(Vp, Fp, np.zeros(2), 1.0, 0.0, 1.0, 2.0)
    lowp, highp = Vp[:, 1] <= 1.0, Vp[:, 1] >= 2.0
    ok("centre: a neck 0.15 radius off the axis is moved onto it below the cut, the head above stays",
       st["applied"] and abs(st["offset"][0] + 0.15) < 0.01 and np.allclose(Vc[highp], Vp[highp])
       and abs(Vc[lowp][:, 0].mean()) < 0.01, st["offset"])
    _, st2 = centre_neck(Vp + [0.2, 0, 0], Fp, np.zeros(2), 1.0, 0.0, 1.0, 2.0)
    ok("centre: 0.35 radius off is refused", not st2["applied"] and st2["offset_share"] > 0.25, st2["offset_share"])

    # 3d. seam colour: a neck (radius 0.03, cut at 0.32) whose part texture is painted dark at the front
    #     above 0.311 and filled light below (a hard step), against a light anchor neck
    rn, cut_c, fade_c = 0.03, 0.32, 0.335
    light, dark, anchor_skin = np.array([0.88, 0.69, 0.55]), np.array([0.60, 0.38, 0.28]), np.array([0.86, 0.66, 0.52])

    def neck_mesh(r, u0, u1):
        P, Fn = _grid_surface(lambda u, v: np.c_[r * np.sin(2 * math.pi * u - math.pi), 0.28 + 0.08 * v,
                                                 r * np.cos(2 * math.pi * u - math.pi)], 49, 41, wrap_u=False)
        us = np.repeat(np.linspace(0, 1, 49), 41)
        vs = np.tile(np.linspace(0, 1, 41), 49)
        uv = np.c_[u0 + (u1 - u0) * us, 0.05 + 0.9 * vs]
        return P, Fn, uv[Fn]

    Pn, Fn, UVn = neck_mesh(0.98 * rn, 0.05, 0.45)
    Pa_, Fa_, UVa_ = neck_mesh(rn, 0.05, 0.95)
    tex_p = np.ones((128, 128, 4), np.float32)
    rows_y = 0.28 + 0.08 * ((np.arange(128) + 0.5) / 128 - 0.05) / 0.9
    cols_t = ((np.arange(128) + 0.5) / 128 - 0.05) / 0.4 * 2 * math.pi - math.pi
    front = (np.abs(cols_t)[None, :] < math.radians(60)) & (rows_y[:, None] > cut_c - 0.009)
    tex_p[..., :3] = np.where(front[..., None], dark, light)
    tex_p[:, 70:, :3] = [0.2, 0.15, 0.1]                  # the hair's island, never touched
    tex_a = np.ones((64, 64, 4), np.float32)
    tex_a[..., :3] = anchor_skin
    skin_c, hair_c = np.array([0.75, 0.55, 0.42]), np.array([0.2, 0.15, 0.1])
    Sp, _, _, uvp = sample_surface_uv(Pn, Fn, UVn, 20000, rng)
    Sa, _, _, uva = sample_surface_uv(Pa_, Fa_, UVa_, 20000, rng)
    Cp0, Ca0 = sample_texture(tex_p, uvp), sample_texture(tex_a, uva)
    step_c, ylo_c = 0.1 * rn, 0.30
    ny_c = int(math.ceil((fade_c + step_c - ylo_c) / step_c))
    fld, fst = seam_colour_field(Sp, Cp0, Sa, Ca0, (0, 0), cut_c, rn, ylo_c, step_c, ny_c, skin_c, hair_c)
    ok("seam colour: a field from both sides' skin", fld is not None and fst["cells_used"] > 20, fst)
    tex_q, n_tx = apply_seam_colour(tex_p, UVn, Pn[Fn], fld, (0, 0), rn, cut_c, fade_c, ylo_c, step_c)
    rep_c = seam_colour_report(Sp, Cp0, sample_texture(tex_q, uvp), Sa, Ca0, (0, 0), rn, cut_c, fade_c, skin_c, hair_c)
    ok("seam colour: above the cut the front starts from the anchor's rim", rep_c.get("delta_before", 0) > 10
       and rep_c.get("delta_after", 99) < 6, [rep_c.get("delta_before"), rep_c.get("delta_after")])
    ok("seam colour: the painted edge is spread (sharpest row step under half)", rep_c.get("edge_L_after", 99)
       < 0.5 * rep_c.get("edge_L_before", 0), [rep_c.get("edge_L_before"), rep_c.get("edge_L_after")])
    covered = seam_colour_report(Sp, Cp0, Cp0, Sa, Ca0, (0, 0), rn, cut_c, fade_c, skin_c, hair_c,
                                 open_p=np.zeros(len(Sp), bool))
    ok("seam colour: a seam under a collar is not read", covered["sectors"] == 0, covered["sectors"])
    above = rows_y > fade_c + 0.002
    ok("seam colour: texels above the fade and the hair's island unchanged",
       np.array_equal(tex_q[above], tex_p[above]) and np.array_equal(tex_q[:, 70:], tex_p[:, 70:]) and n_tx > 500, n_tx)
    tri = uv_raster(np.array([[[0.1, 0.1], [0.9, 0.1], [0.1, 0.9]]]), np.ones((1, 3, 1)), 64, 64)[1]
    ok("seam colour: a raster covers the triangle's area", abs(tri.sum() / (0.32 * 64 * 64) - 1) < 0.08, int(tri.sum()))
    off = np.array([0.80, 0.40, 0.45])                     # another material on the part's neck (a scarf)
    tex_o = tex_p.copy()
    tex_o[..., :3] = np.where(np.arange(128)[None, :, None] < 70, off, tex_o[..., :3])
    Cpo = sample_texture(tex_o, uvp)
    fo, fso = seam_colour_field(Sp, Cpo, Sa, Ca0, (0, 0), cut_c, rn, ylo_c, step_c, ny_c, skin_c, hair_c)
    ok("seam colour: two materials are left alone", fo is None and fso["cells_refused"] > 0, fso)

    # 4. hair split: a closed scalp under a spiky cap; and the hugging (unredrawn) case
    hair_rgb, skin_rgb = np.array([0.23, 0.16, 0.12]), np.array([0.91, 0.71, 0.55])
    for case, spikes in (("spiky", 0.15), ("hugging", 0.01)):
        Vh0, Fh0, kh = synthetic_figure(res=1, neck_bottom=0.30, spikes=spikes)
        Vh, Fh, _ = weld(Vh0, Fh0)
        rgb = np.where(np.isin(kh, (1, 3))[:, None], hair_rgb, skin_rgb)
        mask, st = split_hair(Vh, Fh, rgb, hair_rgb, skin_rgb, chin_y=0.355, delta=0.03)
        _, area = face_normals(Vh, Fh)
        cap, scalp = kh == 3, kh == 1
        gates = {g["name"]: g["pass"] for g in st["gates"]}
        if case == "spiky":
            got = float(area[mask & cap].sum() / max(area[cap].sum(), 1e-12))
            leak = float(area[mask & scalp].sum() / max(area[scalp].sum(), 1e-12))
            ok("hair: spikes found (>= 95 % of their area)", got >= 0.95, round(got, 4))
            ok("hair: scalp kept (<= 2 % taken)", leak <= 0.02, round(leak, 4))
            ok("hair: every gate passes", all(gates.values()), st["gates"])
        else:
            ok("hair: hugging hair fails a gate", not all(gates.values()), st["gates"])
    # lips: a dark-red mouth standing out of the face reads nearer the hair colour than the skin; the
    # face (in front, below the brow line) stays the head's whatever its colour
    Vl0, Fl0, kl = synthetic_figure(res=1, neck_bottom=0.30, spikes=0.15)
    Vl0 = Vl0.copy()
    mouth_v = (np.abs(Vl0[:, 0]) < 0.025) & (np.abs(Vl0[:, 1] - 0.38) < 0.008) & (Vl0[:, 2] > 0.05)
    rho = np.linalg.norm(Vl0[:, [0, 2]], axis=1)
    mouth_v &= rho > rho[mouth_v].max() - 0.0025           # the outer shell only (the inner wall is 0.005 in)
    Vl0[mouth_v, 2] += 0.02
    Vl, Fl, _ = weld(Vl0, Fl0)
    cl = Vl[Fl].mean(1)
    lips = (np.abs(cl[:, 0]) < 0.03) & (np.abs(cl[:, 1] - 0.38) < 0.012) & (cl[:, 2] > 0.05)
    rgb = np.where(np.isin(kl, (1, 3))[:, None], hair_rgb, skin_rgb)
    rgb[lips] = (0.55, 0.22, 0.2)
    mask, st = split_hair(Vl, Fl, rgb, hair_rgb, skin_rgb, chin_y=0.355, delta=0.03)
    no_face, _ = split_hair(Vl, Fl, rgb, hair_rgb, skin_rgb, chin_y=0.355, delta=0.03, face_yaw=0.0)
    _, area = face_normals(Vl, Fl)
    ok("hair: lips stay on the head (taken without the face rule)",
       lips.any() and not (mask & lips).any() and (no_face & lips).any()
       and float(area[mask & (kl == 3)].sum() / area[kl == 3].sum()) >= 0.95,
       {"lip_faces": int(lips.sum()), "taken": int((mask & lips).sum()), "taken_no_rule": int((no_face & lips).sum())})

    # 5. plan on a synthetic anchor written as a GLB, masks from its own projection
    with tempfile.TemporaryDirectory() as tmp:
        glb = os.path.join(tmp, "anchor.glb")
        write_glb(glb, V0, F0)
        vdir = os.path.join(tmp, "clean")
        os.makedirs(vdir)
        masks_ok = True
        try:
            from PIL import Image
            for view in VIEWS:
                m = silhouette(V, F, view, 1024, frame)
                Image.fromarray((m * 255).astype(np.uint8)).save(os.path.join(vdir, f"c_{view}_mask_00001_.png"))
        except ImportError:
            masks_ok = False
        if masks_ok:
            out = os.path.join(tmp, "parts", "runner.parts.json")
            os.makedirs(os.path.dirname(out))
            ns = argparse.Namespace(anchor=glb, views=vdir, tier="three", character="runner", out=out,
                                    margin_frac=0.1, band_step=0.002, hood_grow=0.08)
            code, res = cmd_plan(ns)
            ok("plan: exit 0", code == 0, res if code else None)
            if code == 0:
                with open(out, encoding="utf-8") as handle:
                    doc = json.load(handle)
                fr = doc["anchor"]["frame"]
                ok("plan: the frame fit recovers the scale", abs(fr["units_per_px"] / frame[0] - 1) < 0.01,
                   fr["units_per_px"])
                ok("plan: frame IoU >= 0.95 in every view", min(fr["iou"].values()) >= 0.95, fr["iou"])
                head = next(p for p in doc["parts"] if p["name"] == "head")
                bx = head["views"]["boxes"]
                ok("plan: one box side and shared rows", len({b[3] - b[1] for b in bx.values()}) == 1
                   and len({b[1] for b in bx.values()}) == 1 and all(b[2] - b[0] == head["views"]["box_side_px"] for b in bx.values()))
                tc = box_centre(fr, bx)
                ok("plan: the box centre lands on the head", abs(tc[0]) < 0.01 and abs(tc[2]) < 0.01
                   and 0.30 < tc[1] < 0.46, tc.round(4).tolist())
                ok("plan: keep masks written", all(os.path.isfile(os.path.join(tmp, "parts", "views", "head", f"keep_{v}.png"))
                                                   for v in VIEWS))
                required = {"schema", "character", "tier", "parts", "anchor"}
                ok("plan: required keys", required <= set(doc) and all({"name", "source", "region"} <= set(p) for p in doc["parts"]))
                try:
                    check_plan(doc)
                    ok("plan: validity rules hold", True)
                except Refused as exc:
                    ok("plan: validity rules hold", False, str(exc))
                bad = json.loads(json.dumps(doc))
                bad["tier"] = "custom"
                try:
                    check_plan(bad)
                    ok("plan: custom is refused", False)
                except Refused as exc:
                    ok("plan: custom is refused", "reserved" in str(exc))
                bad = json.loads(json.dumps(doc))
                bad["parts"].append({"name": "hand_r", "source": "generate", "region": "hand.R", "preset": "Template"})
                try:
                    check_plan(bad)
                    ok("plan: a hand is refused in tier three", False)
                except Refused as exc:
                    ok("plan: a hand is refused in tier three", "tier fine" in str(exc))
                bad["tier"] = "fine"
                try:
                    check_plan(bad)
                    ok("plan: a hand is taken in tier fine", True)
                except Refused as exc:
                    ok("plan: a hand is taken in tier fine", False, str(exc))
                bad["parts"].append({"name": "eyes", "source": "generate", "region": "eyes", "preset": "Template"})
                try:
                    check_plan(bad)
                    ok("plan: an eyes part is refused in tier fine (eye_fit.py makes the eyeballs)", False)
                except Refused as exc:
                    ok("plan: an eyes part is refused in tier fine (eye_fit.py makes the eyeballs)",
                       "not built from a plan" in str(exc), str(exc))
                bad = json.loads(json.dumps(doc))
                next(p for p in bad["parts"] if p["name"] == "head")["preset"] = "Large"
                try:
                    check_plan(bad)
                    ok("plan: Large on hair is refused", False)
                except Refused:
                    ok("plan: Large on hair is refused", True)
                contract_sample("part_math", "plan", doc, suffix=".parts.json")
        else:
            print("SKIP plan checks (no PIL)")
    return (0 if not failed else 1), {"selftest": "pass" if not failed else "fail", "failed": failed, "checks": checks}


# ------------------------------------------------------------------------------------------- cli
class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1, never 2: here 2 is a gate verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser():
    p = UsageParser(prog="part_math.py", description=__doc__.split("\n")[0],
                    epilog="Exit codes: 0 done, 1 usage or refused input, 2 a measurement gate failed, 3 unreadable file.")
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd", parser_class=UsageParser)
    pl = sub.add_parser("plan", help="measure the anchor and write the parts/1 plan")
    pl.add_argument("anchor")
    pl.add_argument("--views", required=True)
    pl.add_argument("--tier", required=True)
    pl.add_argument("--character", required=True)
    pl.add_argument("--out", required=True)
    pl.add_argument("--margin-frac", type=float, default=0.1)
    pl.add_argument("--band-step", type=float, default=0.002)
    pl.add_argument("--painted", help="the anchor repainted by mesh-texture-paint (S3b), recorded as anchor.painted_glb")
    pl.add_argument("--hood-grow", type=float, default=0.08,
                    help="grow the surfaces kept out of a part's views upward by this share of the head height")
    return p


def main():
    args = parser().parse_args(sys.argv[1:])
    if not args.selftest and args.cmd is None:
        parser().print_usage(sys.stderr)
        sys.exit(1)
    if np is None:
        print(json.dumps({"tool": "part_math", "error": "numpy is required"}))
        sys.exit(1)
    if args.selftest:
        code, res = selftest()
    else:
        import re
        if not re.fullmatch(r"[a-z0-9_-]+", args.character):
            print(json.dumps({"tool": "part_math", "refused": "--character must match ^[a-z0-9_-]+$"}))
            sys.exit(1)
        code, res = cmd_plan(args)
    print(json.dumps({"tool": "part_math", **res}, indent=1, default=str))
    sys.exit(code)


if __name__ == "__main__":
    main()
