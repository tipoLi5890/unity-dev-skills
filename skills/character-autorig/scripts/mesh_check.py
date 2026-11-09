#!/usr/bin/env python3
"""mesh_check.py — is this mesh riggable? Fused limbs and double shells, before any bone is placed.

An auto-rigger, a voxel bind and a hand-built skeleton all assume the arms hang clear of the torso
and the legs part below the crotch. A generated mesh often has an arm glued along the ribs or both
legs in one tube, and no marker or weight fixes that: the views are regenerated instead. This reads
the mesh alone, in its own file, and says which.

usage:
    mesh_check.py MESH.glb|MESH.gltf|MESH.obj [--up y|z] [--out REPORT.json]
                  [--step 0.01] [--cell 0.008]
                  [--leg-band 0.12,0.38] [--leg-min-ratio 0.9]
                  [--arm-band 0.50,0.74] [--arm-min-span 0.05]
                  [--shell-gap 0.006] [--shell-max 0.25] [--shell-samples 6000]
                  [--body human|skirt|chibi]
    mesh_check.py --selftest

The mesh is read whole (every primitive of every node, node transforms applied). glTF is +Y up and
OBJ is written +Y up by most tools, so both are turned to +Z up the way Blender imports them
((x, y, z) -> (x, -z, y)); `--up z` reads a file that is already +Z up. The character faces -Y,
its left on +X. Lengths are fractions of the height H (top minus sole), so no unit is assumed.
Compressed glTF (Draco, meshopt) and sparse accessors are refused: decompress first, or export an
OBJ from Blender.

Cross sections. Every `--step` x H from the sole up, the mesh is cut by a horizontal plane; the
cut's line segments are rasterised on a grid of `--cell` x H, enclosed holes are filled (an inner
shell or a hollow torso is one part, not two), and the parts are the 8-connected regions. A part
smaller than 4 cells is dropped. The midline is the centre in X of everything below 0.4 H.

Gates (each failing one makes exit 2):
  legs_separated   in the leg band (fractions of H; default 0.12-0.38, below any crotch, above the
                   feet), the share of cuts with a part wholly left of the midline, a part wholly
                   right of it, and no part across it. >= --leg-min-ratio (0.9). Fails: both legs
                   in one tube, a long skirt, a robe, a cape behind the legs.
  arms_separated   in the arm band (default 0.50-0.74 H, between the hands of a 30-60 degree A-pose
                   and the armpit), the longest run of consecutive cuts in which a part lies wholly
                   outside the torso part on BOTH sides. >= --arm-min-span (0.05) x H. Fails: an arm
                   glued along the ribs, arms held against the body, and a T-pose (no arm crosses
                   the band; the contract wants an A-pose anyway).
  double_shell     the share of the surface (area-weighted samples) that has another sheet of the
                   mesh parallel to it within --shell-gap x H (0.006, about 1 cm on a 1.7 m body)
                   along its normal, facing the same way, or facing it from in front (two skins
                   pressed together). <= --shell-max (0.25). An outer skin over a same-facing
                   inner twin reads near 0.5. Fingers and limbs are thicker than the gap, so they
                   do not count. A sheet behind the sample facing the other way, back to back
                   with it (a thin wall: an inward-facing inner shell, which some image-to-3D
                   generators always write, a cloth flap, an ear), is reported as `inner_shell`
                   and not gated: the deformation gate measures the outward-facing side only.

--body skirt (a long coat, a skirt, a robe, a cape or cloak bridging the legs from behind: one part
across the midline from a hem down to the knees or below, the legs apart under it). The hem is the
lowest cut from which a part crosses the midline in every cut up to 0.6 H (the crotch of a body in
trousers). legs_separated is read from the leg band's foot up to 0.02 H under the hem, and a second
gate stands beside it:
  skirt_hem        a hem was found and the legs show under it for >= 0.08 x H (SKIRT_MIN_LEGS) of
                   the leg band. Fails: a floor-length robe (no legs to measure: the hand-built
                   route), both legs in one tube.
  double_shell     gated over the surface outside the skirt zone (the hem to 0.55 H); the zone's own
                   share is reported as skirt.layer: a coat over trousers is two sheets there by design.
The report gains skirt {hem_h, legs_band, hem_width_over_legs, layer}. With the default body, a hem
signature (legs apart under a part that crosses the midline from 0.22-0.42 H up, at least 1.15 x
their span) is reported as skirt_hint: rerun with --body skirt. A narrower part that crosses the
midline only behind the legs' centre in every cut from its hem up 0.04 H (CAPE_RISE; a pelvis crosses
in front too) is a cape or cloak bridging the legs from behind: skirt_hint with behind: true. The hint
is advice, never a gate.

--body chibi (a big head, about a third of H or more, on a short body with short limbs; chosen at G0, never
to rescue a body that failed the default bands). The bands follow the body type, the limits do not change:
the crotch is searched from CHIBI_CROTCH_FROM (0.10 H) up, legs_separated is read from CHIBI_LEG_FROM (0.06 H)
up to 0.02 H under that crotch, and arms_separated in CHIBI_ARM_BAND (0.35-0.65 H: the hands of a 30-60
degree A-pose on short arms hang near 0.35-0.45 H, the armpit near 0.55 H). Both limits stay 0.9 and
0.05 H. The report gains chibi {crotch_h, leg_band, arm_band}.

Report: {tool, file, body, height, triangles, vertices, midline_x, crotch_h, legs{band, cuts, separated,
ratio, first_fused_h}, arms{band, cuts, run_h, armpit_h, left, right}, double_shell{ratio, inner_shell,
samples, gap}, skirt?, skirt_hint?{hem_h, legs_below, hem_width_over_legs, behind?, why}, gates[{name, value,
limit, pass, margin?}], schema, pass}: a gate/1 report (schemas/gate-1.json). legs_separated, arms_separated (>=) and double_shell (<=) carry `margin`, the signed
distance to the limit (gate_margin: + safe, - failing); skirt_hem carries none. Heights ending in `_h` are
fractions of H.

Prints one JSON object. Exit codes: 0 every gate passed (or --selftest passed); 2 a gate failed;
1 refused input (unreadable or compressed file, no triangles) or a failed --selftest.
Requires Python 3 and numpy. arp_markers.py imports the cross-section functions from here.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np

MIN_PART_CELLS = 4
SKIRT_MIN_LEGS = 0.08     # x H of leg band that must show under a hem
SKIRT_TOP = 0.55          # the skirt zone runs from the hem up to here (x H)
HEM_CLEAR = 0.02          # the legs are read up to this far under the hem (x H)
HINT_WIDTH = 1.15         # skirt_hint: the hem at least this much wider than the legs under it
CAPE_RISE, CAPE_CUTS = 0.04, 3   # skirt_hint, a narrow hem: only behind the legs this far up (x H), over this many cuts
CHIBI_CROTCH_FROM = 0.10  # --body chibi: the crotch is searched from here up (x H; short legs part low)
CHIBI_LEG_FROM = 0.06     # --body chibi: the leg band's foot (x H), over the shoe soles
CHIBI_ARM_BAND = (0.35, 0.65)   # --body chibi: hands near 0.35-0.45 H, armpit near 0.55 H
FEET, MIDLINE_SHIFT = 0.15, 0.02   # the midline from the feet when the extent under 0.4 H is off it by more (x H)
MARGIN_OPS = {"legs_separated": ">=", "arms_separated": ">=", "double_shell": "<="}   # each limit's direction

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


# ------------------------------------------------------------------------------ loading


class Refused(Exception):
    """Input this tool will not read (exit 1)."""


def _trs(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=float).reshape(4, 4).T   # glTF is column-major
    t = np.array(node.get("translation", [0, 0, 0]), dtype=float)
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    s = np.array(node.get("scale", [1, 1, 1]), dtype=float)
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * s
    m[:3, 3] = t
    return m


_COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16,
              5125: np.uint32, 5126: np.float32}
_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _accessor(gltf: dict, buffers: list, index: int) -> np.ndarray:
    acc = gltf["accessors"][index]
    if "sparse" in acc:
        raise Refused("sparse accessors are not read; re-export the mesh without them")
    view = gltf["bufferViews"][acc["bufferView"]]
    dtype = np.dtype(_COMPONENT[acc["componentType"]])
    width = _WIDTH[acc["type"]]
    data = buffers[view["buffer"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride") or dtype.itemsize * width
    count = acc["count"]
    raw = np.frombuffer(data, dtype=np.uint8, count=stride * (count - 1) + dtype.itemsize * width,
                        offset=start)
    rows = np.lib.stride_tricks.as_strided(raw, shape=(count, dtype.itemsize * width),
                                           strides=(stride, 1))
    return np.ascontiguousarray(rows).view(dtype).reshape(count, width)


def _load_gltf(path: Path) -> tuple[np.ndarray, np.ndarray]:
    blob = path.read_bytes()
    if blob[:4] == b"glTF":
        _, _, length = struct.unpack_from("<III", blob, 0)
        offset, gltf, bin_chunk = 12, None, b""
        while offset < min(length, len(blob)):
            size, kind = struct.unpack_from("<II", blob, offset)
            chunk = blob[offset + 8: offset + 8 + size]
            if kind == 0x4E4F534A:
                gltf = json.loads(chunk.decode("utf-8"))
            elif kind == 0x004E4942:
                bin_chunk = chunk
            offset += 8 + size
        if gltf is None:
            raise Refused(f"{path}: no JSON chunk")
    else:
        gltf, bin_chunk = json.loads(blob.decode("utf-8")), b""
    required = set(gltf.get("extensionsRequired", []))
    packed = required & {"KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_meshopt_compression"}
    if packed:
        raise Refused(f"{path}: compressed ({', '.join(sorted(packed))}); decompress or export an OBJ first")
    buffers = []
    for buf in gltf.get("buffers", []):
        uri = buf.get("uri")
        if uri is None:
            buffers.append(bin_chunk)
        elif uri.startswith("data:"):
            buffers.append(base64.b64decode(uri.split(",", 1)[1]))
        else:
            buffers.append((path.parent / uri).read_bytes())
    verts, faces, base = [], [], 0

    def visit(index: int, parent: np.ndarray) -> None:
        nonlocal base
        node = gltf["nodes"][index]
        world = parent @ _trs(node)
        if "mesh" in node:
            for prim in gltf["meshes"][node["mesh"]]["primitives"]:
                if prim.get("mode", 4) != 4 or "POSITION" not in prim["attributes"]:
                    continue
                p = _accessor(gltf, buffers, prim["attributes"]["POSITION"]).astype(float)
                p = (np.c_[p, np.ones(len(p))] @ world.T)[:, :3]
                if "indices" in prim:
                    idx = _accessor(gltf, buffers, prim["indices"]).reshape(-1).astype(np.int64)
                else:
                    idx = np.arange(len(p), dtype=np.int64)
                verts.append(p)
                faces.append(idx.reshape(-1, 3) + base)
                base += len(p)
        for child in node.get("children", []):
            visit(child, world)

    scenes = gltf.get("scenes") or [{"nodes": list(range(len(gltf.get("nodes", []))))}]
    roots = scenes[gltf.get("scene", 0)].get("nodes", [])
    for root in roots:
        visit(root, np.eye(4))
    if not verts:
        raise Refused(f"{path}: no triangle primitive")
    return np.vstack(verts), np.vstack(faces)


def _load_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    verts, faces = [], []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("f "):
            idx = []
            for token in line.split()[1:]:
                i = int(token.split("/")[0])
                idx.append(i - 1 if i > 0 else len(verts) + i)
            faces.extend([idx[0], idx[k], idx[k + 1]] for k in range(1, len(idx) - 1))
    if not verts or not faces:
        raise Refused(f"{path}: no vertices or faces")
    return np.array(verts, dtype=float), np.array(faces, dtype=np.int64)


def load_mesh(path: Path, up: str = "y") -> tuple[np.ndarray, np.ndarray]:
    """(vertices (n, 3) Z-up, triangles (m, 3)), sole at z 0."""
    suffix = path.suffix.lower()
    if suffix in (".glb", ".gltf"):
        v, f = _load_gltf(path)
    elif suffix == ".obj":
        v, f = _load_obj(path)
    else:
        raise Refused(f"{path}: not .glb, .gltf or .obj")
    if up == "y":
        v = np.c_[v[:, 0], -v[:, 2], v[:, 1]]
    if len(f) == 0 or f.max() >= len(v) or f.min() < 0:
        raise Refused(f"{path}: face indices out of range")
    v = v - [0.0, 0.0, v[:, 2].min()]
    return v, f


# ------------------------------------------------------------------------------ cross sections


def section_segments(v: np.ndarray, f: np.ndarray, z: float) -> np.ndarray:
    """The cut of the mesh by the plane Z = z, as segments (k, 2, 2) in XY."""
    tri = v[f]                                    # (m, 3, 3)
    d = tri[:, :, 2] - z
    d = np.where(np.abs(d) < 1e-12, 1e-12, d)     # a vertex on the plane counts as just above it
    cross = (d.min(axis=1) < 0) & (d.max(axis=1) > 0)
    tri, d = tri[cross], d[cross]
    if not len(tri):
        return np.zeros((0, 2, 2))
    a, b = [0, 1, 2], [1, 2, 0]
    da, db = d[:, a], d[:, b]
    hit = (da < 0) != (db < 0)                    # exactly two edges per crossing triangle
    t = (da / np.where(hit, da - db, 1.0))[..., None]
    pts = tri[:, a, :2] + t * (tri[:, b, :2] - tri[:, a, :2])
    return pts[hit].reshape(-1, 2, 2)


def _label(grid: np.ndarray, eight: bool) -> tuple[np.ndarray, int]:
    """Connected regions of True cells. Returns (labels, count); 0 is background."""
    h, w = grid.shape
    labels = np.zeros((h, w), dtype=np.int32)
    steps = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if eight:
        steps += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    count = 0
    for i, j in zip(*np.nonzero(grid)):
        if labels[i, j]:
            continue
        count += 1
        labels[i, j] = count
        stack = [(i, j)]
        while stack:
            ci, cj = stack.pop()
            for di, dj in steps:
                ni, nj = ci + di, cj + dj
                if 0 <= ni < h and 0 <= nj < w and grid[ni, nj] and not labels[ni, nj]:
                    labels[ni, nj] = count
                    stack.append((ni, nj))
    return labels, count


def section_parts(segments: np.ndarray, cell: float, min_cells: int = MIN_PART_CELLS) -> list[dict]:
    """The parts of one cut: rasterised, holes filled, 8-connected.

    Each part: {cells, area, x: [lo, hi], y: [lo, hi], cx, cy}, area in the units of the mesh.
    """
    if not len(segments):
        return []
    a, b = segments[:, 0], segments[:, 1]
    n = np.maximum(1, np.ceil(np.linalg.norm(b - a, axis=1) / (cell * 0.5)).astype(int)) + 1
    seg = np.repeat(np.arange(len(segments)), n)
    t = np.concatenate([np.linspace(0, 1, k) for k in n])[:, None]
    pts = a[seg] + t * (b[seg] - a[seg])
    lo = pts.min(axis=0) - 2 * cell
    ij = np.floor((pts - lo) / cell).astype(int)
    w, h = ij[:, 0].max() + 3, ij[:, 1].max() + 3
    grid = np.zeros((h, w), dtype=bool)
    grid[ij[:, 1], ij[:, 0]] = True
    # background: empty cells reached from the border (4-connected); the rest is inside
    outside, _ = _label(~grid, eight=False)
    border = set(outside[0, :]) | set(outside[-1, :]) | set(outside[:, 0]) | set(outside[:, -1])
    border.discard(0)
    filled = grid | ~np.isin(outside, list(border))
    labels, count = _label(filled, eight=True)
    parts = []
    for k in range(1, count + 1):
        ii, jj = np.nonzero(labels == k)
        if len(ii) < min_cells:
            continue
        xs, ys = lo[0] + (jj + 0.5) * cell, lo[1] + (ii + 0.5) * cell
        parts.append({"cells": int(len(ii)), "area": float(len(ii) * cell * cell),
                      "x": [float(xs.min() - cell / 2), float(xs.max() + cell / 2)],
                      "y": [float(ys.min() - cell / 2), float(ys.max() + cell / 2)],
                      "cx": float(xs.mean()), "cy": float(ys.mean())})
    return sorted(parts, key=lambda p: p["cx"])


def profile(v: np.ndarray, f: np.ndarray, step: float = 0.01, cell: float = 0.008,
            lo: float = 0.0, hi: float = 1.0) -> dict:
    """Cuts from lo to hi (fractions of H). {height, cell, midline_x, cuts: [{h, z, parts}]}."""
    height = float(v[:, 2].max() - v[:, 2].min())
    low = v[v[:, 2] < 0.4 * height]
    mid = float((low[:, 0].min() + low[:, 0].max()) / 2) if len(low) else float(np.median(v[:, 0]))
    feet = v[v[:, 2] < v[:, 2].min() + FEET * height]
    if len(feet) and abs((feet[:, 0].min() + feet[:, 0].max()) / 2 - mid) > MIDLINE_SHIFT * height:
        mid = float((feet[:, 0].min() + feet[:, 0].max()) / 2)   # a wide asymmetric part below 0.4 H on one side
    cuts = []
    h = lo + step / 2
    while h < hi:
        z = v[:, 2].min() + h * height
        cuts.append({"h": round(h, 5), "z": float(z),
                     "parts": section_parts(section_segments(v, f, z), cell * height)})
        h += step
    return {"height": height, "cell": cell * height, "midline_x": mid, "cuts": cuts}


def spans(part: dict, x: float) -> bool:
    return part["x"][0] < x < part["x"][1]


def torso_of(parts: list[dict], mid: float) -> dict | None:
    across = [p for p in parts if spans(p, mid)]
    return max(across, key=lambda p: p["area"]) if across else None


# ------------------------------------------------------------------------------ gates


def legs(prof: dict, band: tuple[float, float]) -> dict:
    mid, rows = prof["midline_x"], []
    for cut in prof["cuts"]:
        if not band[0] <= cut["h"] <= band[1]:
            continue
        parts = cut["parts"]
        ok = (not any(spans(p, mid) for p in parts) and any(p["x"][0] > mid for p in parts)
              and any(p["x"][1] < mid for p in parts))
        rows.append((cut["h"], ok))
    fused = [h for h, ok in rows if not ok]
    sep = sum(ok for _, ok in rows)
    return {"band": list(band), "cuts": len(rows), "separated": sep,
            "ratio": sep / len(rows) if rows else 0.0, "first_fused_h": fused[0] if fused else None}


def crotch(prof: dict, lo: float = 0.2) -> float | None:
    """The lowest cut above `lo` (0.2 H) from which a part crosses the midline in every cut up to 0.6 H."""
    mid = prof["midline_x"]
    rows = [(c["h"], any(spans(p, mid) for p in c["parts"])) for c in prof["cuts"] if lo <= c["h"] <= 0.6]
    for k, (h, _) in enumerate(rows):
        if all(across for _, across in rows[k:]):
            return h
    return None


def arms(prof: dict, band: tuple[float, float], step: float) -> dict:
    mid, rows = prof["midline_x"], []
    for cut in prof["cuts"]:
        if not band[0] <= cut["h"] <= band[1]:
            continue
        torso = torso_of(cut["parts"], mid)
        left = right = False
        if torso is not None:
            left = any(p["x"][0] > torso["x"][1] for p in cut["parts"])
            right = any(p["x"][1] < torso["x"][0] for p in cut["parts"])
        rows.append((cut["h"], left, right))
    best, run, top = 0, 0, None
    for h, left, right in rows:
        run = run + 1 if (left and right) else 0
        if run > best:
            best, top = run, h
    return {"band": list(band), "cuts": len(rows), "run_h": round(best * step, 5),
            "armpit_h": top, "left": sum(r[1] for r in rows), "right": sum(r[2] for r in rows)}


def surface_samples(v: np.ndarray, f: np.ndarray, count: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Area-weighted points on the surface and their face normals."""
    tri = v[f]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(cross, axis=1)
    keep = area > 0
    tri, cross, area = tri[keep], cross[keep], area[keep]
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(tri), size=count, p=area / area.sum())
    r1, r2 = rng.random(count), rng.random(count)
    s = np.sqrt(r1)
    pts = (tri[pick, 0] * (1 - s)[:, None] + tri[pick, 1] * (s * (1 - r2))[:, None]
           + tri[pick, 2] * (s * r2)[:, None])
    return pts, cross[pick] / area[pick, None]


def double_shell(v: np.ndarray, f: np.ndarray, gap: float, samples: int, seed: int = 0, zone=None) -> dict:
    """Share of the surface with another sheet parallel to it within `gap` along its normal.

    From each sample a segment runs `gap` both ways along the face normal; a hit on another
    triangle whose normal is within 60 degrees of parallel (either facing), further than a tenth
    of the gap, marks the sample. A hit behind the sample on a sheet facing the other way is a
    back-to-back thin wall (an inward-facing inner shell, a flap): `inner_shell`. Any other hit
    (same facing on either side, or facing it from in front) marks it doubled, the gated `ratio`;
    a sample with both counts as doubled. Triangles are found through a grid of `gap` cells.
    `zone` (z0, z1): samples with z inside it leave `ratio` and are counted in `zone_ratio`.
    """
    tri = v[f]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(cross, axis=1)
    keep = np.nonzero(area > 0)[0]
    tnorm = np.zeros_like(cross)
    tnorm[keep] = cross[keep] / area[keep, None]
    rng = np.random.default_rng(seed)
    pick = keep[rng.choice(len(keep), size=samples, p=area[keep] / area[keep].sum())]
    r1, r2 = rng.random(samples), rng.random(samples)
    s = np.sqrt(r1)
    pts = (tri[pick, 0] * (1 - s)[:, None] + tri[pick, 1] * (s * (1 - r2))[:, None]
           + tri[pick, 2] * (s * r2)[:, None])
    nrm = tnorm[pick]
    cell = gap
    lo = np.floor(tri.min(axis=1)[keep] / cell).astype(np.int64)
    hi = np.floor(tri.max(axis=1)[keep] / cell).astype(np.int64)
    table: dict[tuple, list[int]] = {}
    for t, a, b in zip(keep.tolist(), lo.tolist(), hi.tolist()):
        for i in range(a[0], b[0] + 1):
            for j in range(a[1], b[1] + 1):
                for k in range(a[2], b[2] + 1):
                    table.setdefault((i, j, k), []).append(t)
    min_sep, doubled, inner = gap * 0.1, 0, 0
    in_zone = np.zeros(samples, bool) if zone is None else (pts[:, 2] >= zone[0]) & (pts[:, 2] <= zone[1])
    zone_doubled = 0
    probe = np.linspace(-1.0, 1.0, 9)
    for q in range(samples):
        p, n = pts[q], nrm[q]
        cells = {tuple(c) for c in np.floor((p + probe[:, None] * gap * n) / cell).astype(np.int64).tolist()}
        cand = sorted({t for c in cells for t in table.get(c, ())} - {int(pick[q])})
        if not cand:
            continue
        cand = np.array(cand)
        facing = tnorm[cand] @ n
        keep_c = np.abs(facing) >= 0.5
        cand, facing = cand[keep_c], facing[keep_c]
        if not len(cand):
            continue
        # Moller-Trumbore, the ray p + t n against every candidate
        a, b, c = tri[cand, 0], tri[cand, 1], tri[cand, 2]
        e1, e2 = b - a, c - a
        h = np.cross(n, e2)
        det = np.einsum("ij,ij->i", e1, h)
        good = np.abs(det) > 1e-14
        inv = np.where(good, 1.0 / np.where(good, det, 1.0), 0.0)
        sv = p - a
        u = inv * np.einsum("ij,ij->i", sv, h)
        qv = np.cross(sv, e1)
        w = inv * (qv @ n)
        t = inv * np.einsum("ij,ij->i", e2, qv)
        hit = good & (u >= 0) & (w >= 0) & (u + w <= 1) & (np.abs(t) > min_sep) & (np.abs(t) <= gap)
        if not hit.any():
            continue
        back_to_back = (t < 0) & (facing < 0)
        if (hit & ~back_to_back).any():
            if in_zone[q]:
                zone_doubled += 1
            else:
                doubled += 1
        else:
            inner += 1
    out_n, zone_n = int(samples - in_zone.sum()), int(in_zone.sum())
    rep = {"ratio": doubled / max(out_n, 1), "inner_shell": round(inner / samples, 4), "samples": samples,
           "gap": gap}
    if zone is not None:
        rep.update(zone=[round(float(zone[0]), 5), round(float(zone[1]), 5)], zone_samples=zone_n,
                   zone_ratio=round(zone_doubled / max(zone_n, 1), 4))
    return rep


def extent(parts: list[dict]) -> float:
    return max(p["x"][1] for p in parts) - min(p["x"][0] for p in parts) if parts else 0.0


def skirt_hint(prof: dict, crotch_h: float | None, leg_band, min_ratio: float, v=None, f=None) -> dict | None:
    """A hem signature on the default body: the legs apart under a part that crosses the midline from
    0.22-0.42 H up (a long coat or a skirt), so the crotch read there is a hem. The part is at least
    HINT_WIDTH x the legs' span, or (given the mesh v, f) it crosses the midline only behind the legs
    over CAPE_RISE x H from the hem: a cape or cloak bridging the legs from behind."""
    if crotch_h is None or not 0.22 <= crotch_h < 0.42:
        return None
    below = legs(prof, (leg_band[0], crotch_h - HEM_CLEAR))
    if below["cuts"] < 4 or below["ratio"] < min_ratio:
        return None
    wide = hem_width(prof, crotch_h)
    if wide is not None and wide >= HINT_WIDTH:
        return {"hem_h": crotch_h, "legs_below": round(below["ratio"], 4), "hem_width_over_legs": round(wide, 4),
                "why": f"a part crosses the midline from {crotch_h:.3f} H up with the legs apart under it: a hem, not "
                       "a crotch. A long coat, a skirt or a robe: rerun with --body skirt"}
    # as narrow as the legs: a low crotch (a pelvis crosses the midline in front and behind), or a cape
    if v is None or f is None or not cape_behind(v, f, prof, crotch_h):
        return None
    return {"hem_h": crotch_h, "legs_below": round(below["ratio"], 4),
            "hem_width_over_legs": None if wide is None else round(wide, 4), "behind": True,
            "why": f"a part crosses the midline only behind the legs from {crotch_h:.3f} H up, with the legs apart "
                   "under it: a cape's hem, not a crotch. A cape or cloak bridging the legs from behind: rerun with "
                   "--body skirt"}


def midline_y(v: np.ndarray, f: np.ndarray, z: float, x: float) -> np.ndarray:
    """Where the cut at Z = z crosses the line X = x: the Y of every crossing."""
    seg = section_segments(v, f, z)
    if not len(seg):
        return np.zeros(0)
    a, b = seg[:, 0], seg[:, 1]
    hit = (a[:, 0] >= x) != (b[:, 0] >= x)        # an end on the line counts as just right of it
    a, b = a[hit], b[hit]
    return a[:, 1] + (x - a[:, 0]) / (b[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])


def cape_behind(v: np.ndarray, f: np.ndarray, prof: dict, hem: float) -> bool:
    """In every cut from the hem up CAPE_RISE x H (at least CAPE_CUTS of them), the surface crosses the
    midline and only behind (+Y; the character faces -Y) the centre of the legs just under the hem. A
    pelvis crosses in front too; the gluteal join alone over a crotch does not last CAPE_RISE."""
    mid = prof["midline_x"]
    under = min((c for c in prof["cuts"] if c["h"] <= hem - HEM_CLEAR), key=lambda c: abs(c["h"] - (hem - HEM_CLEAR)),
                default=None)
    if not under or not under["parts"]:
        return False
    area = sum(p["area"] for p in under["parts"])
    legs_y = sum(p["cy"] * p["area"] for p in under["parts"]) / area
    window = [c for c in prof["cuts"] if hem <= c["h"] <= hem + CAPE_RISE]
    if len(window) < CAPE_CUTS:
        return False
    for c in window:
        ys = midline_y(v, f, c["z"], mid)
        if not len(ys) or ys.min() <= legs_y:
            return False
    return True


def hem_width(prof: dict, hem: float) -> float | None:
    """The widest cut within 0.04 H over the hem (every part) over the legs' span just under it."""
    below = min((c for c in prof["cuts"] if c["h"] <= hem - HEM_CLEAR), key=lambda c: abs(c["h"] - (hem - HEM_CLEAR)),
                default=None)
    leg_w = extent(below["parts"]) if below else 0.0
    hem_w = max((extent(c["parts"]) for c in prof["cuts"] if hem <= c["h"] <= hem + 0.04), default=0.0)
    return hem_w / leg_w if leg_w > 0 else None


def skirt(prof: dict, args) -> dict:
    """The skirt route's reading: the hem, the legs under it, the hem's width over the legs'."""
    hem = crotch(prof)
    lo = args.leg_band[0]
    if hem is None:
        return {"hem_h": None, "legs_band": None, "legs": legs(prof, (lo, lo)), "shown": 0.0,
                "why": "no part crosses the midline from below 0.6 H up: no hem (and no crotch)"}
    band = (lo, round(min(args.leg_band[1], hem - HEM_CLEAR), 5))
    lg = legs(prof, band)
    shown = max(0.0, band[1] - band[0])
    wide = hem_width(prof, hem)
    out = {"hem_h": hem, "legs_band": list(band), "legs": lg, "shown": round(shown, 5),
           "hem_width_over_legs": None if wide is None else round(wide, 4)}
    if shown < SKIRT_MIN_LEGS - 1e-9:
        out["why"] = (f"the legs show for {shown:.3f} H under the hem at {hem:.3f} H (< {SKIRT_MIN_LEGS}): a floor-length "
                      "robe has no legs to place markers on; take the hand-built route")
    return out


def check(v: np.ndarray, f: np.ndarray, args) -> dict:
    prof = profile(v, f, step=args.step, cell=args.cell)
    height = prof["height"]
    body = getattr(args, "body", "human")
    sk = skirt(prof, args) if body == "skirt" else None
    chibi = None
    if body == "chibi":     # a big head on short limbs: the bands follow the body type, the limits stay
        c_h = crotch(prof, CHIBI_CROTCH_FROM)
        chibi = {"crotch_h": c_h, "leg_band": [CHIBI_LEG_FROM, round(max(CHIBI_LEG_FROM, (c_h or 0.0) - HEM_CLEAR), 5)],
                 "arm_band": list(CHIBI_ARM_BAND)}
    lg = sk["legs"] if sk else legs(prof, tuple(chibi["leg_band"] if chibi else args.leg_band))
    am = arms(prof, tuple(chibi["arm_band"] if chibi else args.arm_band), args.step)
    zone = None
    if sk and sk["hem_h"] is not None:
        zone = (float(v[:, 2].min()) + sk["hem_h"] * height, float(v[:, 2].min()) + SKIRT_TOP * height)
    ds = double_shell(v, f, args.shell_gap * height, args.shell_samples, zone=zone)
    gates = [
        {"name": "legs_separated", "value": round(lg["ratio"], 4), "limit": f">= {args.leg_min_ratio}",
         "pass": bool(lg["ratio"] >= args.leg_min_ratio)},
        {"name": "arms_separated", "value": am["run_h"], "limit": f">= {args.arm_min_span}",
         "pass": bool(am["run_h"] >= args.arm_min_span - 1e-9)},
        {"name": "double_shell", "value": round(ds["ratio"], 4), "limit": f"<= {args.shell_max}",
         "pass": bool(ds["ratio"] <= args.shell_max)},
    ]
    if sk:
        gates.insert(1, {"name": "skirt_hem", "value": sk["hem_h"], "limit": f"legs shown >= {SKIRT_MIN_LEGS}",
                         "pass": bool(sk["hem_h"] is not None and "why" not in sk)})
    for g in gates:
        m = gate_margin(g["value"], float(g["limit"][2:]), MARGIN_OPS[g["name"]]) if g["name"] in MARGIN_OPS else None
        if m is not None:
            g["margin"] = m
    ds["gap"] = round(ds["gap"], 6)
    ok = all(g["pass"] is True for g in gates)
    crotch_h = chibi["crotch_h"] if chibi else crotch(prof)
    rep = {"schema": "gate/1", "tool": "mesh_check", "pass": ok, "body": body, "height": round(height, 6),
           "triangles": int(len(f)), "vertices": int(len(v)), "midline_x": round(prof["midline_x"], 6),
           "crotch_h": crotch_h, "legs": lg, "arms": am, "double_shell": ds, "gates": gates}
    if sk:
        rep["skirt"] = {k: v for k, v in sk.items() if k != "legs"}
        rep["skirt"]["layer"] = ds.get("zone_ratio")
    elif chibi:
        rep["chibi"] = chibi
    else:
        hint = skirt_hint(prof, crotch_h, args.leg_band, args.leg_min_ratio, v, f)
        if hint:
            rep["skirt_hint"] = hint
    return rep


# ------------------------------------------------------------------------------ CLI


def _pair(text: str) -> list[float]:
    a, b = (float(x) for x in text.split(","))
    return [a, b]


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser() -> argparse.ArgumentParser:
    p = UsageParser(prog="mesh_check.py", description=__doc__.split("\n")[0],
                                epilog="Exit codes: 0 pass, 2 a gate failed, 1 refused input.")
    p.add_argument("mesh", nargs="?", type=Path)
    p.add_argument("--up", choices=("y", "z"), default="y", help="the file's up axis (default y: glTF, OBJ)")
    p.add_argument("--out", type=Path)
    p.add_argument("--step", type=float, default=0.01, help="cut spacing, fraction of H (0.01)")
    p.add_argument("--cell", type=float, default=0.008, help="raster cell, fraction of H (0.008)")
    p.add_argument("--leg-band", type=_pair, default=[0.12, 0.38])
    p.add_argument("--leg-min-ratio", type=float, default=0.9)
    p.add_argument("--arm-band", type=_pair, default=[0.50, 0.74])
    p.add_argument("--arm-min-span", type=float, default=0.05)
    p.add_argument("--shell-gap", type=float, default=0.006)
    p.add_argument("--shell-max", type=float, default=0.25)
    p.add_argument("--shell-samples", type=int, default=6000)
    p.add_argument("--body", choices=("human", "skirt", "chibi"), default="human",
                   help="skirt: a long coat, skirt, robe, or a cape or cloak bridging the legs from behind; the "
                        "legs are read under its hem. chibi: a big head "
                        "on short limbs; the bands follow the body type")
    p.add_argument("--selftest", action="store_true")
    return p


def run(argv: list[str]) -> tuple[int, dict]:
    args = parser().parse_args(argv)
    if args.mesh is None:
        return 1, {"schema": "gate/1", "tool": "mesh_check", "pass": False, "gates": [],
                   "refused": "a mesh file is required (or --selftest)"}
    try:
        v, f = load_mesh(args.mesh, args.up)
    except (OSError, ValueError, KeyError, IndexError, struct.error, Refused) as exc:
        return 1, {"schema": "gate/1", "tool": "mesh_check", "pass": False, "gates": [],
                   "refused": str(exc), "error": str(exc)}
    report = check(v, f, args)
    report["file"] = str(args.mesh)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return (0 if report["pass"] is True else 2), report


# ------------------------------------------------------------------------------ selftest

def contract_sample(script: str, case: str, doc: dict) -> None:
    """Hand one selftest report to tools/check-contracts.py: written to $UNITY_DEV_CONTRACT_OUT (else a fixed
    folder in the temp dir) as <script>__<case>.gate.json, and named on stdout as `selftest-output: <path>`."""
    out = os.environ.get("UNITY_DEV_CONTRACT_OUT") or os.path.join(tempfile.gettempdir(), "unity-dev-contract-out")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{script}__{case}.gate.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1)
    print(f"selftest-output: {path}")



def tube(a, b, r, n=20, rings=8, rx=None, ry=None, flip=False):
    """A closed tube from a to b (elliptic when rx/ry are given), as (vertices, faces)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    axis = (b - a) / np.linalg.norm(b - a)
    ref = np.array([0, 0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0, 0])
    u = np.cross(axis, ref)
    u /= np.linalg.norm(u)
    w = np.cross(axis, u)
    if abs(axis[2]) >= 0.9:                       # a vertical tube: u along X, w along Y
        u, w = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]) * np.sign(axis[2])
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ex, ey = (rx or r), (ry or r)
    verts = []
    for t in np.linspace(0, 1, rings):
        c = a + t * (b - a)
        verts.extend(c + ex * np.cos(g) * u + ey * np.sin(g) * w for g in ang)
    verts += [a, b]
    faces = []
    for i in range(rings - 1):
        for j in range(n):
            p, q = i * n + j, i * n + (j + 1) % n
            faces += [[p, q, q + n], [p, q + n, p + n]]
    ca, cb = rings * n, rings * n + 1
    for j in range(n):
        faces.append([ca, (j + 1) % n, j])
        faces.append([cb, (rings - 1) * n + j, (rings - 1) * n + (j + 1) % n])
    faces = np.array(faces)
    if flip:
        faces = faces[:, ::-1]
    return np.array(verts), faces


def assemble(pieces) -> tuple[np.ndarray, np.ndarray]:
    vs, fs, base = [], [], 0
    for v, f in pieces:
        vs.append(v)
        fs.append(f + base)
        base += len(v)
    return np.vstack(vs), np.vstack(fs)


def open_tube(a, b, rx, ry, n=32, rings=12):
    """A tube from a to b along Z with no caps (a skirt open at its hem), as (vertices, faces)."""
    v, f = tube(a, b, rx, n=n, rings=rings, rx=rx, ry=ry)
    return v, f[:2 * n * (rings - 1)]


def body(fused_legs=False, fused_arms=False, t_pose=False, inner=0.0, inner_flip=True, skirt=None, open_skirt=False,
         cape=None, cape_y=0.14):
    """A 1.7 m body of tubes: A-pose by default, facing -Y. `inner` adds an inner twin shell that
    far inside, facing inward (back to back with the skin) or, with inner_flip False, outward.
    `skirt` (a fraction of 1.7 m): a skirt from the waist down to that hem around both legs, solid
    (a closed tube) or with open_skirt a sheet open at the hem with the legs inside it. `cape` (a
    fraction of 1.7 m): a flat sheet at Y cape_y (+ behind the legs, - in front) from the hips down
    to that hem, as wide as the legs (under 1.15 x their span)."""
    s45 = math.sqrt(0.5)
    parts = [((0, 0, 0.86), (0, 0, 1.42), dict(r=0.15, rx=0.15, ry=0.10)),
             ((0, 0, 1.40), (0, 0, 1.52), dict(r=0.05)),
             ((0, -0.01, 1.50), (0, -0.01, 1.70), dict(r=0.10))]
    if fused_legs:
        parts.append(((0, 0, 0.05), (0, 0, 0.92), dict(r=0.17, rx=0.17, ry=0.08)))
    else:
        for x in (0.10, -0.10):
            parts.append(((x, 0, 0.92), (x * 1.1, 0, 0.05), dict(r=0.065)))
    for side in (1, -1):
        if t_pose:
            parts.append(((side * 0.17, 0, 1.36), (side * 0.85, 0, 1.36), dict(r=0.045)))
        elif fused_arms:
            parts.append(((side * 0.18, 0, 1.38), (side * 0.18, 0, 0.80), dict(r=0.045)))
        else:
            a = np.array([side * 0.17, 0, 1.38])
            parts.append((a, a + 0.62 * np.array([side * s45, 0, -s45]), dict(r=0.045)))
        parts.append(((side * 0.11, 0.05, 0.04), (side * 0.11, -0.14, 0.04), dict(r=0.04)))
    pieces = [tube(a, b, **kw) for a, b, kw in parts]
    if skirt is not None:
        hem = skirt * 1.7
        pieces.append(open_tube((0, 0, hem), (0, 0, 1.0), 0.21, 0.14) if open_skirt else
                      tube((0, 0, hem), (0, 0, 1.0), 0.21, rx=0.21, ry=0.14))
    if cape is not None:            # its top inside the skirt zone (under 0.55 H), over the torso's foot
        pieces.append(tube((0, cape_y, cape * 1.7), (0, cape_y, 0.92), 0.17, rx=0.17, ry=0.012))
    if inner:
        for a, b, kw in parts:
            kw2 = {k: max(0.005, v - inner) for k, v in kw.items()}
            pieces.append(tube(a, b, flip=inner_flip, **kw2))
    return assemble(pieces)


def chibi_body() -> tuple[np.ndarray, np.ndarray]:
    """A 0.76 m chibi of tubes: the head 0.36 of H on a short torso, short thick legs and arms (A-pose 45 deg)."""
    s45 = math.sqrt(0.5)
    parts = [((0, 0, 0.24), (0, 0, 0.50), dict(r=0.12, rx=0.12, ry=0.09)),
             ((0, 0, 0.48), (0, 0, 0.56), dict(r=0.05)),
             ((0, -0.01, 0.64), (0, -0.01, 0.76), dict(r=0.15))]
    for x in (0.065, -0.065):
        parts.append(((x, 0, 0.27), (x * 1.1, 0, 0.04), dict(r=0.05)))
    for side in (1, -1):
        a = np.array([side * 0.12, 0, 0.47])
        parts.append((a, a + 0.24 * np.array([side * s45, 0, -s45]), dict(r=0.04)))
        parts.append(((side * 0.07, 0.04, 0.03), (side * 0.07, -0.10, 0.03), dict(r=0.03)))
    return assemble([tube(a, b, **kw) for a, b, kw in parts])


def write_obj(path: Path, v: np.ndarray, f: np.ndarray, up: str = "y") -> None:
    w = v if up == "z" else np.c_[v[:, 0], v[:, 2], -v[:, 1]]   # Z-up -> Y-up for the file
    lines = [f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in w]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in f]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_glb(path: Path, v: np.ndarray, f: np.ndarray) -> None:
    w = np.c_[v[:, 0], v[:, 2], -v[:, 1]].astype(np.float32)   # Z-up -> glTF Y-up
    idx = f.astype(np.uint32).reshape(-1)
    pos_bytes, idx_bytes = w.tobytes(), idx.tobytes()
    gltf = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0, "translation": [0, 0.5, 0]}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
            "buffers": [{"byteLength": len(pos_bytes) + len(idx_bytes)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pos_bytes)},
                            {"buffer": 0, "byteOffset": len(pos_bytes), "byteLength": len(idx_bytes)}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(w), "type": "VEC3",
                           "min": w.min(axis=0).tolist(), "max": w.max(axis=0).tolist()},
                          {"bufferView": 1, "componentType": 5125, "count": len(idx), "type": "SCALAR"}]}
    js = json.dumps(gltf).encode("utf-8")
    js += b" " * (-len(js) % 4)
    bin_ = pos_bytes + idx_bytes
    bin_ += b"\0" * (-len(bin_) % 4)
    total = 12 + 8 + len(js) + 8 + len(bin_)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js
                     + struct.pack("<II", len(bin_), 0x004E4942) + bin_)


def selftest() -> int:
    checks, failed = 0, []

    def ok(name, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failed.append(name)

    def gate(rep, name):
        return next(g for g in rep["gates"] if g["name"] == name)

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cases = {"good": body(), "legs": body(fused_legs=True), "arms": body(fused_arms=True),
                 "tpose": body(t_pose=True), "shell": body(inner=0.006),
                 "nested": body(inner=0.006, inner_flip=False)}
        reports = {}
        for name, (v, f) in cases.items():
            path = d / f"{name}.obj"
            write_obj(path, v, f)
            reports[name] = run([str(path)])
        code, rep = reports["good"]
        ok("separated body: exit 0", code == 0)
        ok("separated body: crotch found near 0.5 H", rep["crotch_h"] is not None and 0.45 <= rep["crotch_h"] <= 0.6)
        ok("separated body: height 1.7", abs(rep["height"] - 1.70) < 0.02)
        ok("separated body: a passing gate/1 report, no `ok`", rep["schema"] == "gate/1" and rep["pass"] is True
           and "ok" not in rep and len(rep["gates"]) == 3)
        ok("every gate carries a margin, + on a pass and - on a failure, in every case", all(
            isinstance(g.get("margin"), float) and (g["margin"] <= 0 or g["pass"]) and (g["margin"] >= 0 or not g["pass"])
            for _, r in reports.values() for g in r["gates"]) and gate(reports["legs"][1], "legs_separated")["margin"] < 0)
        ok("gate_margin: <=, >=, range, a zero limit, a string limit; bool, string and NaN give none",
           gate_margin(0.06, 0.08, "<=") == 0.25 and gate_margin(0.1, 0.08, "<=") == -0.25
           and gate_margin(0.95, 0.9, ">=") == 0.0556 and gate_margin(5, [0, 10], "range") == 1.0
           and gate_margin(-1, [0, 10], "range") == -0.2 and gate_margin(0.5, 0, "<=") == -0.5
           and gate_margin(0.06, "<= 0.08") == 0.25 and gate_margin(0.06, 0.08) is None
           and gate_margin(True, 1, "<=") is None and gate_margin("x", 1, "<=") is None
           and gate_margin(float("nan"), 1, "<=") is None)
        contract_sample("mesh_check", "good", rep)
        code, rep = reports["legs"]
        ok("fused legs: exit 2, legs gate fails", code == 2 and not gate(rep, "legs_separated")["pass"]
           and gate(rep, "arms_separated")["pass"])
        ok("fused legs: a failed gate/1 report", rep["schema"] == "gate/1" and rep["pass"] is False
           and "ok" not in rep and all(set(g) >= {"name", "value", "limit", "pass"} and "ok" not in g
                                          for g in rep["gates"]))
        contract_sample("mesh_check", "fused_legs", rep)
        code, rep = reports["arms"]
        ok("fused arms: exit 2, arms gate fails", code == 2 and not gate(rep, "arms_separated")["pass"]
           and gate(rep, "legs_separated")["pass"])
        code, rep = reports["tpose"]
        ok("T-pose: arms gate fails", code == 2 and not gate(rep, "arms_separated")["pass"])
        code, rep = reports["shell"]
        ok("inward-facing inner shell: exit 0, reported as inner_shell, not gated",
           code == 0 and gate(rep, "double_shell")["value"] < 0.1 and rep["double_shell"]["inner_shell"] > 0.3)
        code, rep = reports["nested"]
        ok("same-facing inner twin: exit 2, shell gate fails", code == 2 and not gate(rep, "double_shell")["pass"]
           and gate(rep, "legs_separated")["pass"])
        ok("single shell: ratio small, no inner shell", gate(reports["good"][1], "double_shell")["value"] < 0.1
           and reports["good"][1]["double_shell"]["inner_shell"] < 0.05)
        # a long skirt: the default body passes the leg band but reports a hem; --body skirt reads the legs
        # under it; a floor-length robe shows too little leg
        for name, sv in (("skirt", body(skirt=0.40)), ("robe", body(skirt=0.10))):
            write_obj(d / f"{name}.obj", *sv)
        code, rep = run([str(d / "skirt.obj")])
        ok("skirt, default body: a skirt_hint at the hem, no skirt block", rep.get("skirt_hint") is not None
           and abs(rep["skirt_hint"]["hem_h"] - 0.40) < 0.03 and "skirt" not in rep)
        code, rep = run([str(d / "skirt.obj"), "--body", "skirt"])
        ok("skirt, --body skirt: exit 0, hem near 0.40, legs read under it", code == 0
           and abs(rep["skirt"]["hem_h"] - 0.40) < 0.03 and rep["skirt"]["legs_band"][1] <= rep["skirt"]["hem_h"]
           and gate(rep, "skirt_hem")["pass"] and gate(rep, "legs_separated")["pass"] and rep["body"] == "skirt")
        contract_sample("mesh_check", "skirt", rep)
        code, rep = run([str(d / "robe.obj"), "--body", "skirt"])
        ok("floor-length robe, --body skirt: skirt_hem fails (too little leg shows)", code == 2
           and not gate(rep, "skirt_hem")["pass"] and "floor-length" in rep["skirt"]["why"])
        # a cape behind the legs, as wide as they are: no width signature, but it crosses the midline only
        # behind them; the same sheet in front (an apron) gets no hint
        for name, sv in (("cape", body(cape=0.30)), ("apron", body(cape=0.30, cape_y=-0.14))):
            write_obj(d / f"{name}.obj", *sv)
        code, rep = run([str(d / "cape.obj")])
        hint = rep.get("skirt_hint") or {}
        ok("back-only cape, default body: legs_separated fails with a cape skirt_hint at the hem", code == 2
           and not gate(rep, "legs_separated")["pass"] and hint.get("behind") is True
           and abs(hint["hem_h"] - 0.30) < 0.03 and hint["hem_width_over_legs"] < HINT_WIDTH and "cape" in hint["why"])
        code, rep = run([str(d / "cape.obj"), "--body", "skirt"])
        ok("back-only cape, --body skirt: exit 0, hem near 0.30, legs read under it", code == 0
           and abs(rep["skirt"]["hem_h"] - 0.30) < 0.03 and gate(rep, "skirt_hem")["pass"]
           and gate(rep, "legs_separated")["pass"] and gate(rep, "double_shell")["pass"])
        code, rep = run([str(d / "apron.obj")])
        ok("front-only apron, default body: legs_separated fails, no skirt_hint", code == 2
           and not gate(rep, "legs_separated")["pass"] and "skirt_hint" not in rep)
        ok("separated body, skirt and robe: no cape hint", "skirt_hint" not in reports["good"][1]
           and "behind" not in (run([str(d / "skirt.obj")])[1].get("skirt_hint") or {}))
        ok("good body, --body skirt: still passes (the hem is its crotch)", run([str(d / "good.obj"), "--body", "skirt"])[0] == 0)
        # a chibi: the default bands miss its short legs and arms; --body chibi reads them in its own bands
        write_obj(d / "chibi.obj", *chibi_body())
        code, rep = run([str(d / "chibi.obj")])
        ok("chibi, default body: legs and arms fail the adult bands", code == 2 and not gate(rep, "legs_separated")["pass"]
           and not gate(rep, "arms_separated")["pass"])
        code, rep = run([str(d / "chibi.obj"), "--body", "chibi"])
        ok("chibi, --body chibi: exit 0, the crotch read from 0.10 H, its bands reported", code == 0 and rep["body"] == "chibi"
           and rep["chibi"]["arm_band"] == list(CHIBI_ARM_BAND) and rep["chibi"]["leg_band"][1] < rep["crotch_h"]
           and gate(rep, "legs_separated")["limit"] == ">= 0.9")
        ok("fused legs, --body chibi: still fail", run([str(d / "legs.obj"), "--body", "chibi"])[0] == 2)
        # two plates 4 mm apart: facing each other is gated, back to back is an inner shell
        sq = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
        up_f, down_f = np.array([[0, 1, 2], [0, 2, 3]]), np.array([[0, 2, 1], [0, 3, 2]])
        pv = np.vstack([sq, sq + [0, 0, 0.004]])
        face = double_shell(pv, np.vstack([up_f, down_f + 4]), 0.006, 400)
        back = double_shell(pv, np.vstack([down_f, up_f + 4]), 0.006, 400)
        ok("face-to-face plates: doubled", face["ratio"] > 0.9 and face["inner_shell"] < 0.1)
        ok("back-to-back plates: inner shell, not doubled", back["ratio"] < 0.1 and back["inner_shell"] > 0.9)
        # the GLB reader gives the same mesh as the OBJ reader
        v, f = cases["good"]
        write_glb(d / "good.glb", v, f)
        code, rep = run([str(d / "good.glb")])
        ok("glb: exit 0, same height", code == 0 and abs(rep["height"] - reports["good"][1]["height"]) < 1e-4)
        vg, fg = load_mesh(d / "good.glb")
        vo, fo = load_mesh(d / "good.obj")
        ok("glb and obj read alike", vg.shape == vo.shape and np.allclose(vg, vo, atol=1e-4))
        # refused inputs
        (d / "bad.obj").write_text("# nothing\n", encoding="utf-8")
        code, rep = run([str(d / "bad.obj")])
        ok("empty obj: exit 1, a refused gate/1 report", code == 1 and rep["pass"] is False and rep["gates"] == [])
        contract_sample("mesh_check", "refused", rep)
        ok("missing file: exit 1", run([str(d / "none.glb")])[0] == 1)
        packed = {"asset": {"version": "2.0"}, "extensionsRequired": ["KHR_draco_mesh_compression"]}
        (d / "packed.gltf").write_text(json.dumps(packed), encoding="utf-8")
        ok("draco gltf: exit 1", run([str(d / "packed.gltf")])[0] == 1)
        ok("--up z reads a z-up file", True)
        write_obj(d / "zup.obj", v, f, up="z")
        ok("z-up obj with --up z: exit 0", run([str(d / "zup.obj"), "--up", "z"])[0] == 0)
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": checks, "failed": failed}))
    return 0 if not failed else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv or argv[:1] == ["selftest"]:
        return selftest()
    code, report = run(argv)
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
