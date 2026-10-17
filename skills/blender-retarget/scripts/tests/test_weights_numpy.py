"""test_weights_numpy.py — brt_weights' array path and backup format, run in Blender.

    Blender --background --factory-startup --python tests/test_weights_numpy.py

Prints `PASS <name>` or `FAIL <name>: <why>` per case and exits 1 when any case
fails. On a generated 100k-vertex "Runner" skinned to "RunnerRig":

- the arm groups' weight on the midline moves to Hips and Chest (the default
  z_split share); _transfer_arrays and run() give the tables of a per-vertex
  reference written here in plain Python (mask, share, transfer, normalise)
  within 1e-6; the same with share "reach" and its own shares;
- z_split hands over from the lower head to the upper one; z_band_fraction
  resolves against the rig's rest height; _normalize_arrays matches a plain
  per-row normalise;
- transfer through run() writes those weights and restore puts them back;
- snapshot writes format 2 with the topology hash; a format-1 backup (no hash)
  still restores, with a warning; after the faces change (same vertex count)
  restore refuses with reason topology_mismatch unless allow_topology_mismatch.
"""
import os
import shutil
import sys
import tempfile

import bmesh
import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import brt_weights as W  # noqa: E402

RESULTS: list[bool] = []
TMP = tempfile.mkdtemp(prefix="brt_weights_test_")
TOL = 1e-6


def check(name, fn):
    try:
        fn()
    except Exception as exc:          # a failed assert or anything else: report and go on
        print(f"FAIL {name}: {type(exc).__name__}: {exc}", flush=True)
        RESULTS.append(False)
    else:
        print(f"PASS {name}", flush=True)
        RESULTS.append(True)


def build(subdivisions: int):
    """A standing grid "Runner" (x across, z up) skinned to "RunnerRig"; weights do not sum to 1."""
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=subdivisions, y_subdivisions=subdivisions, size=1.0)
    mesh = bpy.context.object
    mesh.name = "Runner"
    co = np.empty(len(mesh.data.vertices) * 3, dtype=np.float32)
    mesh.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    stood = np.column_stack([co[:, 0], np.zeros(len(co)), 1.2 + 1.4 * co[:, 1]]).astype(np.float32)
    mesh.data.vertices.foreach_set("co", stood.ravel())
    mesh.data.update()

    arm = bpy.data.armatures.new("RunnerRig")
    rig = bpy.data.objects.new("RunnerRig", arm)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    for name, head, tail, parent in (("Hips", (0, 0, 0.9), (0, 0, 1.2), None),
                                     ("Chest", (0, 0, 1.2), (0, 0, 1.5), "Hips"),
                                     ("UpperArm.L", (0.15, 0, 1.4), (0.45, 0, 1.4), "Chest"),
                                     ("UpperArm.R", (-0.15, 0, 1.4), (-0.45, 0, 1.4), "Chest")):
        bone = arm.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        if parent:
            bone.parent = arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')

    x, z = stood[:, 0].astype(np.float64), stood[:, 2].astype(np.float64)
    weights = {
        "Hips": np.clip(1.3 - z, 0, 1),
        "Chest": np.clip(1.2 - np.abs(z - 1.35), 0, 1) * (1 - 0.5 * np.abs(x)),
        "UpperArm.L": np.clip(0.5 + 2 * x, 0, 1),           # reaches across the midline: the fault
        "UpperArm.R": np.clip(0.5 - 2 * x, 0, 1),
        "GripMask": np.where(x > 0.3, 0.5, 0.0),          # not a bone: never touched
    }
    for name, w in weights.items():
        group = mesh.vertex_groups.new(name=name)
        q = np.round(w * 64) / 64
        keep_zero = name == "Hips"                           # zero-weight memberships too
        for value in np.unique(q):
            if value > 0 or keep_zero:
                group.add(np.flatnonzero(q == value).tolist(), float(value), 'REPLACE')
    return mesh, rig


REGION = {"mesh": "Runner", "armature": "RunnerRig", "axis": "X",
          "mask": {"inner": 0.4, "outer": 0.05}, "z_band": [0.6, 1.8], "feather": 0.05}
BONES = {"from_bones": ["UpperArm.L", "UpperArm.R"], "to_bones": ["Hips", "Chest"]}
REACH = {"share": "reach", "mask": {"inner": 0.02, "outer": 0.2},
         "from_bones": ["Chest"], "to_bones": ["UpperArm.L", "UpperArm.R"]}
AMOUNT = 0.85


# --- the reference: plain Python, one vertex at a time ---------------------

def ss(a, b, x):
    if a == b:
        return 1.0 if x >= b else 0.0
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def ref_mask(p, region):
    m = 1.0
    if region.get("mask"):
        m *= ss(region["mask"]["inner"], region["mask"]["outer"], abs(p[0]))
    lo, hi = region["z_band"]
    f = region["feather"]
    return m * ss(lo, lo + f, p[2]) * (1.0 - ss(hi - f, hi, p[2]))


def ref_z_split(p, rig, to_bones):
    z0, z1 = (rig.data.bones[b].head_local.z for b in to_bones)   # rig at the origin
    t = ss(z0, z1, p[2])
    return [1.0 - t, t]


def ref_normalized(row, deform):
    keys = [n for n in row if n in deform]
    total = sum(row[n] for n in keys)
    if total <= 0.0:
        return None
    return {n: row[n] / total for n in keys}


def ref_transfer(mesh, rig, region, from_bones, to_bones, amount, shares=None):
    """{vertex: normalised deform row} for every vertex the transfer changes.
    `shares` (vertex -> list) replaces the z_split share when given."""
    deform = {b.name for b in rig.data.bones if b.use_deform}
    names = [g.name for g in mesh.vertex_groups]
    out = {}
    for v in mesh.data.vertices:
        p = mesh.matrix_world @ v.co
        m = ref_mask(p, region)
        if m <= 0.0:
            continue
        share = shares[v.index] if shares is not None else ref_z_split(p, rig, to_bones)
        if sum(share) <= 0.0:
            continue
        row = {names[g.group]: g.weight for g in v.groups}
        take = {n: amount * m * row[n] for n in from_bones if row.get(n, 0.0) > 0.0}
        moved = sum(take.values())
        if moved <= 0.0:
            continue
        new = dict(row)
        for n, w in take.items():
            new[n] = row[n] - w
        for k, n in enumerate(to_bones):
            if share[k] > 0.0:
                new[n] = new.get(n, 0.0) + moved * share[k]
        out[v.index] = ref_normalized(new, deform)
    return out


def inputs(mesh, rig, region, bones) -> dict:
    """What _transfer hands to the arithmetic, computed the way it does."""
    spec = W._region_spec({**region, **bones}, rig)
    pos = W._positions(mesh)
    m = W._mask(pos, spec)
    vidx = np.nonzero(m > 0)[0]
    return {"before": W._read(mesh, vidx), "vidx": vidx, "m": m,
            "share": W._shares(pos[vidx], rig, bones["to_bones"], spec),
            "from_bones": bones["from_bones"], "to_bones": bones["to_bones"],
            "amount": AMOUNT, "deform": W._deform(rig)}


def max_table_diff(a: dict, b: dict) -> float:
    assert a.keys() == b.keys(), f"{len(a)} vs {len(b)} vertices"
    worst = 0.0
    for v, row in a.items():
        other = b[v]
        assert set(row) == set(other), f"vertex {v}: groups {sorted(row)} vs {sorted(other)}"
        worst = max(worst, max((abs(row[n] - other[n]) for n in row), default=0.0))
    return worst


def main() -> int:
    mesh, rig = build(316)
    count = len(mesh.data.vertices)
    print(f"mesh Runner: {count} vertices", flush=True)
    args = inputs(mesh, rig, REGION, BONES)
    ref = {}

    def mesh_is_large():
        assert count >= 100_000, count
        assert len(args["vidx"]) > 0.5 * count, f"region {len(args['vidx'])} of {count}"

    def transfer_arrays_equal_reference():
        ref["z_split"] = ref_transfer(mesh, rig, REGION, BONES["from_bones"], BONES["to_bones"], AMOUNT)
        table, undo, changed, worst, moved = W._transfer_arrays(**args)
        assert len(changed) > 0.3 * count, f"{len(changed)} changed of {count}"
        assert len(table) == len(changed) == len(undo), (len(table), len(changed), len(undo))
        diff = max_table_diff(table, ref["z_split"])
        assert diff <= TOL, f"largest weight difference {diff:.2e}"
        assert worst > 0.0 and moved > 0.0, (worst, moved)
        print(f"  {len(changed)} vertices changed, largest difference {diff:.1e}", flush=True)

    def reach_arrays_equal_reference():
        region = {**REGION, **REACH}
        bones = {k: REACH[k] for k in ("from_bones", "to_bones")}
        a = inputs(mesh, rig, region, bones)
        shares = {int(i): list(row) for i, row in zip(a["vidx"], a["share"])}
        want = ref_transfer(mesh, rig, region, bones["from_bones"], bones["to_bones"], AMOUNT,
                            shares=shares)
        table = W._transfer_arrays(**a)[0]
        assert len(table) > 0.3 * count, len(table)
        diff = max_table_diff(table, want)
        assert diff <= TOL, f"largest weight difference {diff:.2e}"

    def z_split_hands_over():
        spec = W._region_spec(REGION, rig)
        pos = np.array([[0, 0, 0.9], [0, 0, 1.05], [0, 0, 1.2], [0, 0, 0.5], [0, 0, 1.7]], dtype=np.float64)
        s = W._shares(pos, rig, ["Chest", "Hips"], spec)      # order given does not matter
        want = np.array([[0, 1], [0.5, 0.5], [1, 0], [0, 1], [1, 0]], dtype=np.float64)
        assert np.abs(s - want).max() < 1e-6, s
        try:
            W._shares(pos, rig, ["Hips", "Chest", "UpperArm.L"], spec)
        except ValueError:
            return
        raise AssertionError("three to-bones with z_split did not raise")

    def z_band_fraction_resolves():
        spec = W._region_spec({**REGION, "z_band": None, "z_band_fraction": [0.25, 0.75],
                               "feather": 0.1}, rig)
        # RunnerRig's bones span z 0.9 to 1.5: height 0.6
        want = [1.05, 1.05 + 0.06, 1.35 - 0.06, 1.35]
        assert np.allclose(spec["z_band"], want) and abs(spec["rig_height"] - 0.6) < 1e-6, spec
        try:                       # feather 0.3 of 0.6 = 0.18 per end, the band 0.3 wide: inverted
            W._region_spec({**REGION, "z_band": None, "z_band_fraction": [0.25, 0.75],
                            "feather": 0.3}, rig)
        except ValueError as exc:
            assert "twice the feather" in str(exc), str(exc)
        else:
            raise AssertionError("a band narrower than two feathers did not raise")
        try:
            W._region_spec({**REGION, "z_band_fraction": [0.2, 0.8]}, rig)
        except ValueError:
            return
        raise AssertionError("z_band and z_band_fraction together did not raise")

    def normalize_arrays_equal_rows():
        table, undo, done, zero, worst = W._normalize_arrays(args["before"], args["vidx"], args["deform"])
        want, rows = {}, []
        for j, (i, row) in enumerate(zip(args["vidx"], args["before"])):
            new = ref_normalized(row, args["deform"])
            if new is not None:
                want[int(i)] = new
                rows.append(j)
        assert done == rows and zero == len(args["before"]) - len(rows), (len(done), len(rows), zero)
        diff = max_table_diff(table, want)
        assert diff <= TOL, f"largest weight difference {diff:.2e}"

    check("mesh_is_large", mesh_is_large)
    check("transfer_arrays_equal_reference", transfer_arrays_equal_reference)
    check("reach_arrays_equal_reference", reach_arrays_equal_reference)
    check("z_split_hands_over", z_split_hands_over)
    check("z_band_fraction_resolves", z_band_fraction_resolves)
    check("normalize_arrays_equal_rows", normalize_arrays_equal_rows)

    snap = os.path.join(TMP, "runner_back.npz")
    original = W._read(mesh, range(count))

    def run_transfer_writes_reference_weights():
        r = W.run({**REGION, "op": "snapshot", "backup_path": snap})
        assert r["ok"] and r["format"] == 2 and r["topology"] == W._topology(mesh.data), r
        r = W.run({**REGION, **BONES, "op": "transfer", "backup_path": snap, "amount": AMOUNT})
        assert r["ok"], [g for g in r["gates"] if not g["pass"]]
        table, deform = ref["z_split"], args["deform"]
        assert r["changed_vertices"] == len(table), (r["changed_vertices"], len(table))
        written = {v: {n: w for n, w in row.items() if n in deform}     # the table holds deform rows
                   for v, row in zip(table, W._read(mesh, list(table)))}
        diff = max_table_diff(written, table)
        assert diff <= TOL, f"written weights differ from the reference by {diff:.2e}"

    def snapshot_format_2():
        data = W._load(snap)
        assert int(data["format"]) == 2, data["format"]
        assert str(data["topology"]) == W._topology(mesh.data), "stored hash is not the mesh's"

    def restore_puts_back():
        r = W.run({**REGION, "op": "restore", "backup_path": snap})
        assert r["ok"] and r["warnings"] == [], (r["ok"], r["warnings"])
        assert W._read(mesh, range(count)) == original, "weights differ from before the transfer"

    def legacy_format_1_restores_with_warning():
        data = W._load(snap)
        legacy = os.path.join(TMP, "runner_back_v1.npz")
        with open(legacy, "wb") as handle:
            np.savez_compressed(handle, **{k: v for k, v in data.items() if k not in ("format", "topology")})
        W.run({**REGION, "op": "normalize", "acknowledge_destructive": True})
        assert W._read(mesh, range(count)) != original, "normalize changed nothing to restore"
        r = W.run({**REGION, "op": "restore", "backup_path": legacy})
        assert r["ok"], [g for g in r["gates"] if not g["pass"]]
        assert r["warnings"] == ["legacy snapshot format 1: topology not verified"], r["warnings"]
        assert W._read(mesh, range(count)) == original, "legacy restore did not put the weights back"

    def topology_change_refuses_restore():
        before_hash = W._topology(mesh.data)
        bm = bmesh.new()
        bm.from_mesh(mesh.data)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bm.to_mesh(mesh.data)
        bm.free()
        assert len(mesh.data.vertices) == count, "triangulating changed the vertex count"
        assert W._topology(mesh.data) != before_hash, "the hash did not see the new faces"
        W.run({**REGION, "op": "normalize", "acknowledge_destructive": True})
        changed = W._read(mesh, range(count))
        r = W.run({**REGION, "op": "restore", "backup_path": snap})
        assert r["ok"] is False and r["reason"] == "topology_mismatch", (r["ok"], r.get("reason"))
        assert [g["name"] for g in r["gates"] if not g["pass"]] == ["weights.topology"], r["gates"]
        assert r["record"]["verdict"] == "failed", r["record"]["verdict"]
        assert W._read(mesh, range(count)) == changed, "a refused restore wrote weights"
        r = W.run({**REGION, "op": "restore", "backup_path": snap, "allow_topology_mismatch": True})
        assert r["ok"] and any("topology changed" in w for w in r["warnings"]), (r["ok"], r["warnings"])
        assert W._read(mesh, range(count)) == original, "the allowed restore did not put the weights back"

    check("run_transfer_writes_reference_weights", run_transfer_writes_reference_weights)
    check("snapshot_format_2", snapshot_format_2)
    check("restore_puts_back", restore_puts_back)
    check("legacy_format_1_restores_with_warning", legacy_format_1_restores_with_warning)
    check("topology_change_refuses_restore", topology_change_refuses_restore)

    print(f"test_weights_numpy: {sum(RESULTS)}/{len(RESULTS)} passed", flush=True)
    return 0 if RESULTS and all(RESULTS) else 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        print(f"FAIL setup: {type(exc).__name__}: {exc}", flush=True)
        code = 1
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
