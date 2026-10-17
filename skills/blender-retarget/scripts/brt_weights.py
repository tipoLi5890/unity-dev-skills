"""brt_weights.py — local skin-weight repair: move weight between bones inside a smooth region.

Runs inside Blender; not a command-line script (the stub is in brt_common.py).

A bone that holds too much of a region (an upper arm pulling the upper back
along when the arm rises, the hips dragging a thigh) is fixed where it shows
instead of re-skinning: part of its weight moves to the bones that should carry
that region, inside a mask that fades in and out, and the region is
renormalised. Nothing about a character is assumed; the region comes from vertex
and bone positions in the params.

    region = {"mesh": "Runner", "armature": "RunnerRig", "axis": "X",
              "mask": {"inner": 0.13, "outer": 0.06},          # world distances from x = 0
              "z_band_fraction": [0.27, 0.40], "feather": 0.03,  # of the rig's rest height
              "backup_path": "<work dir>/runner_upper_back.npz"}
    bones = {"from_bones": ["UpperArm.L", "UpperArm.R"], "to_bones": ["Spine", "Chest"]}
    brt_weights.run({**region, **bones, "op": "probe"})       # read-only: choose the mask here
    brt_weights.run({**region, "op": "snapshot"})             # before any change
    brt_weights.run({**region, **bones, "op": "transfer", "amount": 0.85})
    brt_weights.run({**region, "op": "restore"})              # back to the snapshot

The limb groups give up their weight on the midline and the spine bones take it:
a weight repair moves weight off the bone that reaches too far onto the bones
the region belongs to.

Ops (`op`):

- probe: vertices inside the mask (weight > 0.5), how many a transfer would
  change, the mean weight of each from/to bone inside, the deform sum per vertex
  (min, mean, max), the largest sum over every group (non-deform ones included)
  and the mean share each to-bone would receive. Changes nothing. Without a mask,
  z band or bones it reads the whole mesh: run it right after binding.
- snapshot: writes the weights of every vertex the mask touches (every vertex
  without a mask) to `backup_path`, with the mesh's topology hash. An existing
  file is kept unless `overwrite`.
- transfer: moves `amount` x mask x each from-bone's weight to the to-bones, then
  normalises the changed vertices. Needs `mask` or a z band.
- normalize: scales the deform weights of each vertex in the region (the whole
  mesh without a mask) to sum to 1. Non-deform groups are not changed or counted.
- restore: writes the snapshot back. When the mesh's faces changed since (same
  vertex count, another topology hash) it refuses: ok False, reason
  `topology_mismatch`, nothing written, unless `allow_topology_mismatch: True`.
  A snapshot written before the hash existed (format 1) restores with the
  warning "legacy snapshot format 1: topology not verified".

transfer and normalize do their arithmetic on numpy arrays (_transfer_arrays,
_normalize_arrays); tests/test_weights_numpy.py checks them against a
per-vertex reference written in the test.

Region. World space at rest: vertices through the mesh object's matrix, bone
head_local/tail_local through the rig's. `axis` (default X) is read as |c|, so one
mask covers both sides of the plane c = 0; probe reports where the rig origin
sits on it. Mask weight = smoothstep(inner, outer, |c|) (0 inside `inner`, 1 past
`outer`; inner > outer keeps the middle band instead) x a band on world Z.
The band is `z_band_fraction` [lo, hi], fractions of the rig's rest height
(lowest to highest bone head or tail; 0 is the lowest), or `z_band` [z_lo, z_hi]
in world units; never both. Two values fade in over `feather` (default 0.05,
world units; with z_band_fraction a fraction of the height too) inside each
end, and a band narrower than twice the feather raises; four values [lo_start, lo_full, hi_full, hi_end] give each end its own
fade. Nothing outside the band changes. Only vertices with mask weight > 0 are
touched; probe reports `rig_height` and the band it resolved to (`region`).

Share (`share`). How the moved weight is split between the to-bones.

- "z_split" (default): one or two to-bones. With two, the vertex's world Z
  decides: t = smoothstep(z0, z1, z), (1 - t) to the lower to-bone and t to the
  upper, where z0 and z1 are the two bones' rest head heights, or
  `split_band` [z0, z1] (world) / `split_band_fraction` (of the rig height).
  With one, it takes everything.
- "reach" (optional, for receivers that are not stacked along Z): each to-bone
  by how close the vertex lies to its head along its rest axis,
  1 - smoothstep(0, reach, |along|); reach is the bone's length, or the distance
  to the farthest other to-bone head when that is longer. A to-bone whose head
  is off the mirror plane by more than `feather` takes only from its own side
  (faded over +-feather). Where every share is 0 the nearest to-bone on the
  vertex's side (by segment distance) takes it; a vertex with no to-bone on its
  side keeps its weights.

Deform groups are those named after bones with use_deform. Normalising divides
by their sum without clamping first, and folds the float32 rounding into the
largest weight. Missing groups for to-bones are created.

Guards. transfer refuses unless snapshot wrote `backup_path` for this mesh in this
file session (kept in bpy.app.driver_namespace, cleared on file load), unchanged
since, covering every vertex the mask touches (`require_snapshot`, default true;
normalize honours it when set). The recipe (mesh, armature, bones, the resolved
region, share, amount) is hashed into the object's `brt_weights_applied`
property; the same recipe again is a no-op with `reused: True`. restore puts that
property back as it was at snapshot time (removed when there was none).
transfer, normalize and restore overwrite weights, so on a file with unsaved edits
each adds a warning to the result's `warnings`, unless `acknowledge_destructive:
True`; with `strict: True` it raises instead, before writing anything.

Backup .npz, plain arrays: `vertices` (every vertex covered), `vidx`, `gidx`,
`weight` (one row per existing membership, zero weights included), `group_names`
(gidx indexes it), `n_vertices`, `mesh`, `applied`, `region`, `format` (2) and
`topology` (sha256 over the vertex, face and corner counts and every corner's
vertex index). It is valid only while vertex indices are: restore refuses another
vertex count, and other faces as above. restore removes deform memberships the
backup lacks on those vertices, then writes every stored row.

Edits existing data: weights and groups of `mesh`, its custom property. A failed
write puts the touched vertices back and removes the groups it created. The rig's
pose_position is REST during the call and put back after.

Gates: probe weights.region_vertices > 0. snapshot weights.snapshot_written.
transfer weights.changed_vertices > 0, weights.sum_before_normalize (info),
weights.weight_sum_error < 1e-4, weights.deform_only == 0. normalize
weights.deform_only == 0, weights.weight_sum_error < 1e-6. restore
weights.restored < 1e-6, or a failing weights.topology when it refuses.
"""
from __future__ import annotations

import array
import hashlib
import itertools
import json
import os
import sys

import bpy
import numpy as np

import brt_common as C

_GUARD = "brt_weights_applied"
_REGISTRY = "brt_weights_snapshots"   # bpy.app.driver_namespace key: {mesh: {path: mtime_ns}}
_AXES = {"X": 0, "Y": 1, "Z": 2}
_FORMAT = 2                           # backup .npz layout; 1 had no `format` or `topology`


def _e(value: float) -> str:
    # safe() rounds floats to 5 places, which would print a 3e-7 error as 0.0
    return f"{value:.2e}"


def _smoothstep(e0: float, e1: float, x) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    if e1 == e0:
        return (x >= e1).astype(np.float64)
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# --- region ----------------------------------------------------------------

def _pair(value, name: str) -> list[float]:
    pair = [float(v) for v in value]
    if len(pair) != 2 or not pair[0] < pair[1]:
        raise ValueError(f"{name} must be [lo, hi] with lo < hi, not {value}")
    return pair


def _rig_height(rig) -> tuple[float, float]:
    """(lowest Z, height) over every bone head and tail, world space at rest."""
    mw = rig.matrix_world
    zs = [(mw @ p).z for b in rig.data.bones for p in (b.head_local, b.tail_local)]
    if not zs or max(zs) - min(zs) <= 1e-9:
        raise ValueError(f"{rig.name!r} has no height at rest to take fractions of")
    return min(zs), max(zs) - min(zs)


def _region_spec(params: dict, rig=None) -> dict:
    """The region in world units. Fractions (z_band_fraction, split_band_fraction)
    are resolved against the rig's rest height, so they need `rig`."""
    axis = str(params.get("axis", "X")).upper()
    if axis not in _AXES:
        raise ValueError(f"axis must be X, Y or Z, not {params.get('axis')!r}")
    feather = float(params.get("feather", 0.05))
    if feather < 0:
        raise ValueError(f"feather must be >= 0, not {feather}")
    mask = params.get("mask")
    if mask is not None:
        if "inner" not in mask or "outer" not in mask:
            raise ValueError("mask needs both 'inner' and 'outer' distances")
        mask = {"inner": float(mask["inner"]), "outer": float(mask["outer"])}
        if mask["inner"] == mask["outer"]:
            raise ValueError("mask inner and outer must differ")
    share = str(params.get("share", "z_split"))
    if share not in ("z_split", "reach"):
        raise ValueError(f"share must be 'z_split' or 'reach', not {share!r}")

    if params.get("z_band") is not None and params.get("z_band_fraction") is not None:
        raise ValueError("give z_band (world) or z_band_fraction (of the rig height), not both")
    if params.get("split_band") is not None and params.get("split_band_fraction") is not None:
        raise ValueError("give split_band (world) or split_band_fraction, not both")
    fractions = any(params.get(k) is not None for k in ("z_band_fraction", "split_band_fraction"))
    base, height = (None, None)
    if fractions and rig is None:
        raise ValueError("fractions of the rig height need the armature")
    if rig is not None:
        try:
            base, height = _rig_height(rig)
        except ValueError:
            if fractions:
                raise

    def world(value):
        return base + float(value) * height

    band = params.get("z_band")
    if params.get("z_band_fraction") is not None:
        band = [world(v) for v in params["z_band_fraction"]]
        feather = feather * height
    if band is not None:
        band = [float(v) for v in band]
        if len(band) == 2:
            _pair(band, "z_band")
            if 2.0 * feather > band[1] - band[0]:
                raise ValueError(f"z band [{band[0]:.4g}, {band[1]:.4g}] is narrower than twice the "
                                 f"feather {feather:.4g}: the ramps would cross; widen it or lower feather")
            band = [band[0], band[0] + feather, band[1] - feather, band[1]]
        elif len(band) != 4 or any(x > y for x, y in zip(band, band[1:])) or not band[0] < band[3]:
            raise ValueError("a z band is [lo, hi] or [lo_start, lo_full, hi_full, hi_end], "
                             f"in increasing order, not {band}")
    split = params.get("split_band")
    if params.get("split_band_fraction") is not None:
        split = [world(v) for v in _pair(params["split_band_fraction"], "split_band_fraction")]
    elif split is not None:
        split = _pair(split, "split_band")
    return {"axis": axis, "mask": mask, "z_band": band, "feather": feather, "share": share,
            "split_band": split, "rig_base": base, "rig_height": height}


def _positions(obj) -> np.ndarray:
    """World-space rest positions, one row per vertex: C.world_coords without a Python loop."""
    verts = obj.data.vertices
    co = np.empty(len(verts) * 3, dtype=np.float32)
    verts.foreach_get("co", co)
    mw = np.array(obj.matrix_world, dtype=np.float64)
    return co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]


def _mask(pos: np.ndarray, spec: dict) -> np.ndarray:
    m = np.ones(len(pos))
    if spec["mask"]:
        c = np.abs(pos[:, _AXES[spec["axis"]]])
        m *= _smoothstep(spec["mask"]["inner"], spec["mask"]["outer"], c)
    if spec["z_band"]:
        a, b, c, d = spec["z_band"]
        z = pos[:, 2]
        m *= _smoothstep(a, b, z) * (1.0 - _smoothstep(c, d, z))
    return m


# --- bones -----------------------------------------------------------------

def _deform(rig) -> set[str]:
    return {b.name for b in rig.data.bones if b.use_deform}


def _bones(rig, names, role: str) -> list[str]:
    names = list(names or [])
    missing = [n for n in names if n not in rig.data.bones]
    if missing:
        raise KeyError(f"{rig.name!r} has no bone(s) {missing} ({role})")
    off = [n for n in names if not rig.data.bones[n].use_deform]
    if off:
        raise ValueError(f"{role} {off} are not deform bones; their weights move nothing")
    return names


def _shares(pos: np.ndarray, rig, to_bones: list[str], spec: dict) -> np.ndarray:
    """(vertices, to_bones) shares of the moved weight, by spec["share"]."""
    if spec.get("share", "z_split") == "reach":
        return _shares_reach(pos, rig, to_bones, spec)
    return _shares_z_split(pos, rig, to_bones, spec)


def _shares_z_split(pos: np.ndarray, rig, to_bones: list[str], spec: dict) -> np.ndarray:
    """One to-bone takes all; two split by t = smoothstep(z0, z1, z) on world Z,
    1 - t to the lower one. Every row sums to 1."""
    n, k = len(pos), len(to_bones)
    if k == 1:
        return np.ones((n, 1))
    if k != 2:
        raise ValueError(f"share 'z_split' takes one or two to-bones, not {k}; "
                         "pass share: 'reach' for more")
    mw = rig.matrix_world
    heads = [float((mw @ rig.data.bones[b].head_local).z) for b in to_bones]
    lower = 0 if heads[0] <= heads[1] else 1
    z0, z1 = spec.get("split_band") or sorted(heads)
    if z1 - z0 <= 1e-9:
        raise ValueError(f"to-bones {to_bones} have their heads at one height; "
                         "give split_band, or share: 'reach'")
    t = _smoothstep(z0, z1, pos[:, 2])
    out = np.empty((n, 2))
    out[:, lower], out[:, 1 - lower] = 1.0 - t, t
    return out


def _shares_reach(pos: np.ndarray, rig, to_bones: list[str], spec: dict) -> np.ndarray:
    """Shares by distance along each to-bone. Each row sums to 1, or is all 0 where
    no to-bone lies on the vertex's side of the mirror plane."""
    ax, f = _AXES[spec["axis"]], spec["feather"]
    n, k = len(pos), len(to_bones)
    score, side, dist = np.zeros((n, k)), np.ones((n, k)), np.zeros((n, k))
    mw = rig.matrix_world
    ends = [(np.array(mw @ rig.data.bones[b].head_local), np.array(mw @ rig.data.bones[b].tail_local))
            for b in to_bones]
    for j, (name, (head, tail)) in enumerate(zip(to_bones, ends)):
        length = float(np.linalg.norm(tail - head))
        if length < 1e-9:
            raise ValueError(f"to-bone {name!r} has zero length at rest")
        axis = (tail - head) / length
        along = (pos - head) @ axis
        # reach at least every other to-bone head, so two supports never just touch (a seam)
        reach = max([length] + [float(np.linalg.norm(other - head)) for other, _ in ends])
        score[:, j] = 1.0 - _smoothstep(0.0, reach, np.abs(along))
        if abs(head[ax]) > max(f, 1e-6):      # off the mirror plane: own side only
            side[:, j] = _smoothstep(-f, f, np.sign(head[ax]) * pos[:, ax])
        nearest = head + np.clip(along, 0.0, length)[:, None] * axis
        dist[:, j] = np.linalg.norm(pos - nearest, axis=1)
    score *= side
    total = score.sum(axis=1)
    out = np.zeros((n, k))
    some = total > 0
    out[some] = score[some] / total[some, None]
    for i in np.nonzero(~some)[0]:
        d = np.where(side[i] > 0, dist[i], np.inf)
        if np.isfinite(d).any():
            out[i, int(np.argmin(d))] = 1.0
    return out


# --- weights ---------------------------------------------------------------

def _read(obj, vidx) -> list[dict[str, float]]:
    """{group name: weight} per vertex, every membership including zero weights."""
    names = [g.name for g in obj.vertex_groups]
    verts = obj.data.vertices
    return [{names[g.group]: g.weight for g in verts[int(i)].groups if g.group < len(names)}
            for i in vidx]


def _put(obj, table: dict[int, dict[str, float]], clear: set[str], made: list[str]) -> None:
    """Write vertex -> {group: weight}. A membership in a `clear` group that the
    vertex's row does not name is removed. New groups are appended to `made`."""
    groups = {g.name: g for g in obj.vertex_groups}
    names = [g.name for g in obj.vertex_groups]
    verts = obj.data.vertices
    for i, row in table.items():
        for name in [names[g.group] for g in verts[i].groups if g.group < len(names)]:
            if name in clear and name not in row:
                groups[name].remove([i])
        for name, weight in row.items():
            group = groups.get(name)
            if group is None:
                group = groups[name] = obj.vertex_groups.new(name=name)
                names.append(name)
                made.append(name)
            group.add([i], float(weight), 'REPLACE')


def _write(obj, table: dict, before: dict, deform: set[str]) -> list[str]:
    """_put, and on failure put `before` back and drop the groups this write made."""
    made: list[str] = []
    try:
        _put(obj, table, deform, made)
    except Exception:
        _put(obj, before, deform | set(made), [])
        for name in made:
            obj.vertex_groups.remove(obj.vertex_groups[name])
        raise
    return made


def _normalized(row: dict[str, float], deform: set[str]) -> dict[str, float] | None:
    """The deform entries of `row` scaled to sum 1, as the float32 values Blender stores.
    None when they sum to 0."""
    keys = [n for n in row if n in deform]
    total = sum(row[n] for n in keys)
    if total <= 0.0:
        return None
    w = (np.array([row[n] for n in keys], dtype=np.float64) / total).astype(np.float32)
    top = int(np.argmax(w))
    w[top] = np.float32(float(w[top]) + (1.0 - float(w.astype(np.float64).sum())))
    return {n: float(x) for n, x in zip(keys, w)}


def _deform_sum(row: dict[str, float], deform: set[str]) -> float:
    return sum(w for n, w in row.items() if n in deform)


def _non_deform_changed(before: list[dict], after: list[dict], deform: set[str]) -> int:
    """How many non-deform groups differ (weight or membership) between two reads."""
    changed = set()
    for b, a in zip(before, after):
        changed.update(n for n in (set(b) | set(a)) - deform if b.get(n) != a.get(n))
    return len(changed)


# --- weight arithmetic on arrays ---------------------------------------------
# Blender reads and writes a vertex's memberships one vertex at a time (there is
# no bulk accessor for weights), so _read and _write stay per vertex. Everything
# between them runs here on flat arrays, one entry per (row, group) membership.

def _flat(before: list[dict], gid: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rows of {group: weight} as parallel arrays (row, group id, weight): rows in
    order, each row's entries in its key order."""
    flat = [(j, gid[n], w) for j, row in enumerate(before) for n, w in row.items()]
    a = np.array(flat, dtype=np.float64).reshape(-1, 3)
    return a[:, 0].astype(np.int64), a[:, 1].astype(np.int64), a[:, 2].copy()


def _normalize_flat(r: np.ndarray, w: np.ndarray, is_deform: np.ndarray, rows: int) -> tuple:
    """_normalized for every row at once. Each row's entries sit together in its key
    order, which decides the entry that takes the rounding when two weights tie.
    Returns (deform sum per row, indices of the entries to write, their float32
    weights); a row whose deform sum is <= 0 gets no entries."""
    d = np.flatnonzero(is_deform)
    totals = np.bincount(r[d], weights=w[d], minlength=rows)
    d = d[totals[r[d]] > 0.0]
    rd = r[d]
    w32 = (w[d] / totals[rd]).astype(np.float32)
    if len(d):
        first = np.r_[True, rd[1:] != rd[:-1]]
        seg = np.cumsum(first) - 1
        peak = np.maximum.reduceat(w32, np.flatnonzero(first))
        at = np.flatnonzero(w32 == peak[seg])
        top = at[np.r_[True, seg[at][1:] != seg[at][:-1]]]     # first largest entry per row
        s64 = np.bincount(rd, weights=w32.astype(np.float64), minlength=rows)
        w32[top] = (w32[top].astype(np.float64) + (1.0 - s64[rd[top]])).astype(np.float32)
    return totals, d, w32


def _table(vidx, r: np.ndarray, names: list[str], g: np.ndarray, w32: np.ndarray) -> dict:
    """{vertex index: {group: weight}} from entries grouped by row, in entry order."""
    vertex = np.asarray(vidx).tolist()
    out: dict[int, dict[str, float]] = {}
    for j, k, x in zip(r.tolist(), g.tolist(), w32.astype(np.float64).tolist()):
        out.setdefault(vertex[j], {})[names[k]] = x
    return out


def _transfer_arrays(before, vidx, m, share, from_bones, to_bones, amount, deform) -> tuple:
    """The transfer arithmetic for every region vertex at once.

    Per vertex row: each from-bone weight w > 0 gives amount * m * w; a row whose
    share row is all 0 (no to-bone on its side) or that gives nothing is left
    alone; to-bone k gains the total times share k (a missing membership is added
    after the row's own keys when the share is > 0); the deform entries are then
    normalised as _normalized does. Returns (table, undo, changed rows,
    worst |deform sum - 1| before normalising, total weight moved)."""
    names = list(dict.fromkeys(itertools.chain(itertools.chain.from_iterable(before),
                                               from_bones, to_bones)))
    gid = {n: k for k, n in enumerate(names)}
    r, g, w = _flat(before, gid)
    rows = len(before)
    m_row = np.asarray(m, dtype=np.float64)[np.asarray(vidx, dtype=np.int64)]
    eligible = share.sum(axis=1) > 0.0          # some to-bone on this side
    take = np.where(np.isin(g, [gid[n] for n in from_bones]) & (w > 0.0), amount * m_row[r] * w, 0.0)
    moved = np.bincount(r, weights=take, minlength=rows)
    active = eligible & (moved > 0.0)
    w = w - take
    for col, name in enumerate(to_bones):
        t = gid[name]
        gets = active & (share[:, col] > 0.0)
        add = moved * share[:, col]
        mine = g == t
        hit = mine & gets[r]
        w[hit] += add[r[hit]]
        has = np.zeros(rows, dtype=bool)
        has[r[mine]] = True
        new = np.flatnonzero(gets & ~has)       # a group the row lacks goes after its own keys
        r = np.concatenate([r, new])
        g = np.concatenate([g, np.full(len(new), t, dtype=np.int64)])
        w = np.concatenate([w, add[new]])
    keep = np.flatnonzero(active[r])
    keep = keep[np.argsort(r[keep], kind="stable")]   # by row; appended entries stay last
    r, g, w = r[keep], g[keep], w[keep]
    totals, d, w32 = _normalize_flat(r, w, np.isin(g, [gid[n] for n in names if n in deform]), rows)
    changed = np.flatnonzero(active)
    worst_before = float(np.abs(totals[changed] - 1.0).max()) if len(changed) else 0.0
    vertex = np.asarray(vidx).tolist()
    undo = {vertex[j]: before[j] for j in changed.tolist()}
    return (_table(vidx, r[d], names, g[d], w32), undo, changed.tolist(), worst_before,
            float(moved[changed].sum()))


def _normalize_arrays(before, vidx, deform) -> tuple:
    """Every row's deform weights scaled to sum 1, as _normalized does one row:
    (table, undo, done rows, rows whose deform sum is <= 0, worst sum before)."""
    names = list(dict.fromkeys(itertools.chain.from_iterable(before)))
    gid = {n: k for k, n in enumerate(names)}
    r, g, w = _flat(before, gid)
    totals, d, w32 = _normalize_flat(r, w, np.isin(g, [gid[n] for n in names if n in deform]),
                                     len(before))
    done = np.flatnonzero(totals > 0.0)
    worst_before = float(np.abs(totals[done] - 1.0).max()) if len(done) else 0.0
    vertex = np.asarray(vidx).tolist()
    undo = {vertex[j]: before[j] for j in done.tolist()}
    return (_table(vidx, r[d], names, g[d], w32), undo, done.tolist(), len(before) - len(done),
            worst_before)


# --- backup ----------------------------------------------------------------

def _backup_path(params: dict) -> str:
    path = params.get("backup_path")
    if not path:
        raise ValueError("backup_path is required: the caller chooses where the backup lives")
    return os.path.abspath(bpy.path.abspath(str(path)))


def _load(path: str) -> dict:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"no backup at {path}")
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def _registry() -> dict:
    return bpy.app.driver_namespace.setdefault(_REGISTRY, {})


def _topology(mesh) -> str:
    """sha256 over the vertex count, face count, corner count (the sum of the faces'
    vertex counts) and the vertex index of every corner, in order. Weights and
    positions do not enter it; a face added, removed, split or rewired does."""
    sizes = array.array("i", [0]) * len(mesh.polygons)
    mesh.polygons.foreach_get("loop_total", sizes)
    loops = getattr(mesh, "loops", None)
    if loops is not None:
        corners = array.array("i", [0]) * len(loops)
        loops.foreach_get("vertex_index", corners)
    else:
        corners = array.array("i", [v for p in mesh.polygons for v in p.vertices])
    if sys.byteorder != "little":
        corners.byteswap()
    digest = hashlib.sha256(f"{len(mesh.vertices)} {len(mesh.polygons)} {sum(sizes)}\n".encode())
    digest.update(corners.tobytes())
    return digest.hexdigest()


def _require_snapshot(params: dict, obj, vidx: np.ndarray) -> str:
    path = _backup_path(params)
    seen = _registry().get(obj.name, {})
    if path not in seen:
        raise RuntimeError(f"no snapshot of {obj.name!r} was written to {path} in this session; "
                           "run op 'snapshot' with the same mask first")
    if not os.path.isfile(path) or os.stat(path).st_mtime_ns != seen[path]:
        raise RuntimeError(f"{path} changed or vanished after the snapshot; take a new one")
    data = _load(path)
    if int(data["n_vertices"]) != len(obj.data.vertices):
        raise RuntimeError(f"{path} was taken from {int(data['n_vertices'])} vertices, "
                           f"{obj.name!r} now has {len(obj.data.vertices)}")
    uncovered = np.setdiff1d(vidx, data["vertices"])
    if len(uncovered):
        raise RuntimeError(f"the snapshot at {path} misses {len(uncovered)} vertices this mask "
                           "touches; snapshot with the same mask")
    return path


# --- ops -------------------------------------------------------------------

def _probe(params: dict, obj, rig) -> dict:
    spec = _region_spec(params, rig)
    from_bones = _bones(rig, params.get("from_bones"), "from_bones")
    to_bones = _bones(rig, params.get("to_bones"), "to_bones")
    deform = _deform(rig)
    pos = _positions(obj)
    m = _mask(pos, spec)
    touched = np.nonzero(m > 0)[0]
    rows = _read(obj, touched)
    inside = m[touched] > 0.5
    rows_in = [r for r, keep in zip(rows, inside) if keep]
    count = len(rows_in)
    mean = {n: (sum(r.get(n, 0.0) for r in rows_in) / count if count else 0.0)
            for n in from_bones + to_bones}
    sums = [_deform_sum(r, deform) for r in rows_in]
    all_groups = max((sum(r.values()) for r in rows_in), default=0.0)
    share, eligible = {}, np.ones(len(touched), dtype=bool)
    if to_bones and len(touched):
        s = _shares(pos[touched], rig, to_bones, spec)
        eligible = s.sum(axis=1) > 0
        if count:
            share = {n: float(s[inside, k].mean()) for k, n in enumerate(to_bones)}
    would = sum(1 for r, ok in zip(rows, eligible) if ok and any(r.get(n, 0.0) > 0.0 for n in from_bones))
    gates = [C.gate("weights.region_vertices", count, "> 0", count > 0)]
    return C.report(params, gates, op="probe", mesh=obj.name, armature=rig.name, region=spec,
                    inside_vertices=count, touched_vertices=len(touched), would_change=would,
                    mean_weight=mean, mean_share=share,
                    deform_sum={"min": min(sums, default=0.0), "max": max(sums, default=0.0),
                                "mean": sum(sums) / count if count else 0.0},
                    all_group_sum_max=all_groups, rig_height=spec["rig_height"],
                    rig_origin_on_axis=float(rig.matrix_world.translation[_AXES[spec["axis"]]]),
                    applied=str(obj.get(_GUARD, "")))


def _snapshot(params: dict, obj, rig) -> dict:
    path = _backup_path(params)
    if os.path.exists(path) and not params.get("overwrite"):
        raise FileExistsError(f"{path} exists; writing over it could lose the only copy of the "
                              "weights before a change. Choose a new path or pass overwrite: True")
    spec = _region_spec(params, rig)
    vidx = np.nonzero(_mask(_positions(obj), spec) > 0)[0]
    rows = _read(obj, vidx)
    names = sorted({n for r in rows for n in r})
    index = {n: k for k, n in enumerate(names)}
    flat = [(int(v), index[n], w) for v, r in zip(vidx, rows) for n, w in r.items()]
    topology = _topology(obj.data)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # through a handle: given a name, savez appends ".npz" when the name lacks it
    with open(path, "wb") as handle:
        np.savez_compressed(
            handle,
            vertices=vidx.astype(np.int64),
            vidx=np.array([f[0] for f in flat], dtype=np.int64),
            gidx=np.array([f[1] for f in flat], dtype=np.int64),
            weight=np.array([f[2] for f in flat], dtype=np.float64),
            group_names=np.array(names, dtype=str),
            n_vertices=np.int64(len(obj.data.vertices)),
            mesh=np.array(obj.name),
            applied=np.array(str(obj.get(_GUARD, ""))),
            region=np.array(json.dumps(spec)),
            format=np.int64(_FORMAT),
            topology=np.array(topology))
    stored = _load(path)
    written = (len(stored["vertices"]) == len(vidx) and len(stored["weight"]) == len(flat)
               and int(stored["n_vertices"]) == len(obj.data.vertices))
    if written:
        _registry().setdefault(obj.name, {})[path] = os.stat(path).st_mtime_ns
    gates = [C.gate("weights.snapshot_written", len(stored["vertices"]), len(vidx), written)]
    return C.report(params, gates, op="snapshot", mesh=obj.name, backup_path=path, region=spec,
                    vertices=len(vidx), rows=len(flat), groups=names, format=_FORMAT,
                    topology=topology)


def _transfer(params: dict, obj, rig) -> dict:
    spec = _region_spec(params, rig)
    if not spec["mask"] and not spec["z_band"]:
        raise ValueError("transfer needs a region: pass mask and/or a z band")
    from_bones = _bones(rig, params.get("from_bones"), "from_bones")
    to_bones = _bones(rig, params.get("to_bones"), "to_bones")
    if not from_bones or not to_bones:
        raise ValueError("from_bones and to_bones must each name at least one bone")
    if set(from_bones) & set(to_bones):
        raise ValueError(f"bones in both from_bones and to_bones: {sorted(set(from_bones) & set(to_bones))}")
    amount = float(params.get("amount", 0.85))
    if not 0.0 <= amount <= 1.0:
        raise ValueError(f"amount must be within [0, 1], not {amount}")

    recipe_text = json.dumps({"mesh": obj.name, "armature": rig.name, "from": sorted(from_bones),
                              "to": sorted(to_bones), "amount": amount, **spec},
                             sort_keys=True, separators=(",", ":"))
    recipe = hashlib.sha256(recipe_text.encode()).hexdigest()[:16]
    applied = str(obj.get(_GUARD, "")).split()
    if recipe in applied:
        gates = [C.gate("weights.already_applied", recipe, "once per recipe", True)]
        return C.report(params, gates, op="transfer", mesh=obj.name, reused=True, recipe=recipe,
                        changed_vertices=0)
    warning = C.destructive_guard(params, "brt_weights transfer")

    pos = _positions(obj)
    m = _mask(pos, spec)
    vidx = np.nonzero(m > 0)[0]
    backup = _require_snapshot(params, obj, vidx) if params.get("require_snapshot", True) else None
    deform = _deform(rig)
    before = _read(obj, vidx)
    share = _shares(pos[vidx], rig, to_bones, spec)
    table, undo, changed, worst_before, moved_total = _transfer_arrays(
        before, vidx, m, share, from_bones, to_bones, amount, deform)

    made = _write(obj, table, undo, deform)
    if changed:
        obj[_GUARD] = " ".join(applied + [recipe])

    after = _read(obj, vidx[changed])
    err = max((abs(_deform_sum(r, deform) - 1.0) for r in after), default=0.0)
    off = _non_deform_changed([before[j] for j in changed], after, deform)
    gates = [
        C.gate("weights.changed_vertices", len(changed), "> 0", len(changed) > 0),
        C.gate("weights.sum_before_normalize", _e(worst_before), "info", True),
        C.gate("weights.weight_sum_error", _e(err), "< 1e-4", err < 1e-4),
        C.gate("weights.deform_only", off, 0, off == 0),
    ]
    mean_share = {n: float(share[changed, k].mean()) if changed else 0.0 for k, n in enumerate(to_bones)}
    return C.report(params, gates, op="transfer", mesh=obj.name, armature=rig.name, reused=False,
                    recipe=recipe, region=spec, region_vertices=len(vidx), changed_vertices=len(changed),
                    moved_weight=moved_total, mean_share=mean_share, created_groups=made,
                    backup_path=backup, warnings=[warning] if warning else [])


def _normalize(params: dict, obj, rig) -> dict:
    spec = _region_spec(params, rig)
    vidx = np.nonzero(_mask(_positions(obj), spec) > 0)[0]
    if params.get("require_snapshot", False):
        _require_snapshot(params, obj, vidx)
    warning = C.destructive_guard(params, "brt_weights normalize")
    deform = _deform(rig)
    before = _read(obj, vidx)
    table, undo, done, zero, worst_before = _normalize_arrays(before, vidx, deform)
    _write(obj, table, undo, deform)

    after = _read(obj, vidx[done])
    err = max((abs(_deform_sum(r, deform) - 1.0) for r in after), default=0.0)
    old = [before[j] for j in done]
    off = _non_deform_changed(old, after, deform)
    rescaled = sum(1 for b, a in zip(old, after)
                   if any(b.get(n) != a.get(n) for n in (set(b) | set(a)) & deform))
    gates = [
        C.gate("weights.deform_only", off, 0, off == 0),
        C.gate("weights.weight_sum_error", _e(err), "< 1e-6", err < 1e-6),
    ]
    return C.report(params, gates, op="normalize", mesh=obj.name, armature=rig.name, region=spec,
                    normalized_vertices=len(done), rescaled_vertices=rescaled,
                    zero_sum_vertices=zero, error_before=_e(worst_before),
                    warnings=[warning] if warning else [])


def _restore(params: dict, obj, rig) -> dict:
    path = _backup_path(params)
    data = _load(path)
    count = len(obj.data.vertices)
    if int(data["n_vertices"]) != count:
        raise ValueError(f"{path} was taken from {int(data['n_vertices'])} vertices and {obj.name!r} "
                         f"has {count}: the vertex indices changed, so the backup no longer applies")
    if str(data["mesh"]) != obj.name:
        raise ValueError(f"{path} was taken from {str(data['mesh'])!r}, not {obj.name!r}")
    warnings = []
    if (int(data["format"]) if "format" in data else 1) < 2:
        warnings.append("legacy snapshot format 1: topology not verified")
    else:
        stored, now = str(data["topology"]), _topology(obj.data)
        if now != stored:
            if not params.get("allow_topology_mismatch"):
                gates = [C.gate("weights.topology", now[:12], stored[:12], False)]
                return C.report(params, gates, op="restore", mesh=obj.name, backup_path=path,
                                reason="topology_mismatch",
                                message=f"{obj.name!r} has the same vertex count but other faces than "
                                        "when the snapshot was taken, so its vertex indices may mean "
                                        "other points; nothing was written. Pass "
                                        "allow_topology_mismatch: True to restore anyway.")
            warnings.append("topology changed since the snapshot: restored anyway "
                            "(allow_topology_mismatch)")
    warning = C.destructive_guard(params, "brt_weights restore")
    if warning:
        warnings.append(warning)
    names = [str(n) for n in data["group_names"]]
    table: dict[int, dict[str, float]] = {int(v): {} for v in data["vertices"]}
    for v, g, w in zip(data["vidx"], data["gidx"], data["weight"]):
        table[int(v)][names[int(g)]] = float(w)
    deform = _deform(rig)
    made: list[str] = []
    _put(obj, table, deform, made)

    after = _read(obj, list(table))
    worst, extra = 0.0, 0
    for want, have in zip(table.values(), after):
        for name in set(want) | (set(have) & deform):
            worst = max(worst, abs(have.get(name, 0.0) - want.get(name, 0.0)))
        extra += sum(1 for n in have if n in deform and n not in want)
    passed = worst < 1e-6 and extra == 0
    if passed:
        prior = str(data["applied"])
        if prior:
            obj[_GUARD] = prior
        elif _GUARD in obj:
            del obj[_GUARD]
    gates = [C.gate("weights.restored", _e(worst), "< 1e-6", passed)]
    return C.report(params, gates, op="restore", mesh=obj.name, backup_path=path,
                    restored_vertices=len(table), rows=len(data["weight"]), extra_memberships=extra,
                    created_groups=made, applied=str(obj.get(_GUARD, "")), warnings=warnings)


_OPS = {"probe": _probe, "snapshot": _snapshot, "transfer": _transfer,
        "normalize": _normalize, "restore": _restore}


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    op = params.get("op")
    if op not in _OPS:
        raise ValueError(f"op must be one of {sorted(_OPS)}, not {op!r}")
    obj = bpy.data.objects[params["mesh"]]
    rig = bpy.data.objects[params["armature"]]
    if obj.type != 'MESH':
        raise ValueError(f"{obj.name!r} is a {obj.type}, not a mesh")
    if rig.type != 'ARMATURE':
        raise ValueError(f"{rig.name!r} is a {rig.type}, not an armature")
    state = C.save_state(C.scene_of(params), [obj, rig])
    pose_position = rig.data.pose_position
    try:
        # vertex_group.add raises in Edit Mode, and an edited mesh holds stale weights
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        rig.data.pose_position = 'REST'
        return _OPS[op](params, obj, rig)
    finally:
        rig.data.pose_position = pose_position
        C.restore_state(state)
