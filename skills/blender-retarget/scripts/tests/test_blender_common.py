"""test_blender_common.py — the shared block of bcr_common/brt_common, run in Blender.

    Blender --background --factory-startup --python tests/test_blender_common.py

Prints `PASS <name>` or `FAIL <name>: <why>` per case and exits 1 when any case
fails. Covers: every result carries file, warnings and record, and a gated one is a
gate/1 report (schema, pass, ok equal to pass) while one with no gates carries no
schema or pass; an extra
named `file` cannot replace the file state; destructive_guard on a clean file,
a dirty file, with acknowledge_destructive and with strict; brt_weights transfer,
normalize and restore warn on a dirty file without raising; strict raises before
any weight is written.

Headless Blender marks the file dirty on an undo push and nothing else, so the
clean cases run first and `bpy.ops.ed.undo_push()` makes the file dirty after them.
"""
import json
import os
import shutil
import sys
import tempfile

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)

import brt_common as C  # noqa: E402
import brt_weights as W  # noqa: E402

RESULTS: list[bool] = []
TMP = tempfile.mkdtemp(prefix="brt_common_test_")
WARN = "on a dirty file: pass acknowledge_destructive or strict"


def check(name, fn):
    try:
        fn()
    except Exception as exc:          # a failed assert or anything else: report and go on
        print(f"FAIL {name}: {type(exc).__name__}: {exc}", flush=True)
        RESULTS.append(False)
    else:
        print(f"PASS {name}", flush=True)
        RESULTS.append(True)


def build(subdivisions: int = 40):
    """A standing grid "Runner" (x across, z up) skinned to "RunnerRig"."""
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
        "Chest": np.clip(1 - 2 * np.abs(z - 1.35), 0, 1) * (1 - 0.5 * np.abs(x)),
        "UpperArm.L": np.clip(3 * (x - 0.1), 0, 1),
        "UpperArm.R": np.clip(3 * (-x - 0.1), 0, 1),
        "GripMask": np.where(x > 0.3, 0.5, 0.0),          # not a bone: never touched
    }
    for name, w in weights.items():
        group = mesh.vertex_groups.new(name=name)
        q = np.round(w * 64) / 64
        keep_zero = name == "Chest"                          # zero-weight memberships too
        for value in np.unique(q):
            if value > 0 or keep_zero:
                group.add(np.flatnonzero(q == value).tolist(), float(value), 'REPLACE')
    return mesh, rig


def region(**extra) -> dict:
    return {"mesh": "Runner", "armature": "RunnerRig", "axis": "X",
            "mask": {"inner": 0.4, "outer": 0.05}, "z_band": [1.0, 1.8], "feather": 0.05,
            "from_bones": ["UpperArm.L", "UpperArm.R"], "to_bones": ["Hips", "Chest"], **extra}


def weights_of(mesh) -> list:
    return W._read(mesh, range(len(mesh.data.vertices)))


def main() -> int:
    mesh, _rig = build()
    assert not bpy.data.is_dirty, "a fresh factory session should start clean"
    snap = os.path.join(TMP, "runner_back.npz")
    report_path = os.path.join(TMP, "probe.json")

    def result_keys_retarget():
        r = W.run(region(op="probe", backup_path=snap, report_path=report_path))
        assert r["schema"] == "gate/1" and r["pass"] is r["ok"] is True, (r.get("schema"), r.get("pass"))
        assert all("ok" not in g and isinstance(g["pass"], bool) for g in r["gates"]), r["gates"]
        assert r["file"] == {"path": "", "saved": False, "dirty": False}, r["file"]
        assert r["warnings"] == [], r["warnings"]
        rec = r["record"]
        assert rec["tool"] == {"skill": "blender-retarget", "script": "brt_weights"}, rec["tool"]
        assert "report_path" not in rec["params"] and rec["params"]["backup_path"] == snap, rec["params"]
        assert rec["params"]["mesh"] == "Runner" and rec["gates"] == r["gates"], rec
        assert rec["verdict"] == ("green" if r["ok"] else "failed") == "green", rec["verdict"]
        with open(report_path, encoding="utf-8") as handle:
            written = json.load(handle)
        assert {"schema", "file", "warnings", "record"} <= set(written), sorted(written)

    def result_keys_character_rig():
        path = os.path.join(os.path.dirname(os.path.dirname(SCRIPTS)), "blender-character-rig", "scripts")
        if not os.path.isfile(os.path.join(path, "bcr_common.py")):
            print("SKIP result_keys_character_rig: blender-character-rig is not installed next to this skill")
            return
        sys.path.insert(0, path)
        import bcr_common
        r = bcr_common.report({"mesh": "Runner", "fbx_path": "/x/Runner.fbx"},
                              [bcr_common.gate("skin.max_influences", 5, "<= 4", False)], bones=4)
        assert r["schema"] == "gate/1" and r["pass"] is False and r["ok"] is False and r["bones"] == 4, r
        assert set(r["file"]) == {"path", "saved", "dirty"}, r["file"]
        assert r["record"]["tool"] == {"skill": "blender-character-rig",
                                       "script": "test_blender_common"}, r["record"]["tool"]
        assert r["record"]["params"] == {"mesh": "Runner"}, r["record"]["params"]
        assert r["record"]["verdict"] == "failed", r["record"]

    def extras_cannot_replace_file_state():
        r = C.report({}, [], file="Runner.blend", warnings=["one", "two"], schema=1, ok=False)
        assert r["file"] == C.file_state() and isinstance(r["file"], dict), r["file"]
        assert r["warnings"] == ["one", "two"] and r["ok"] is True, r
        assert "schema" not in r and "pass" not in r, r       # no gates: a result, not a gate/1 report

    def guard_clean_file():
        assert C.destructive_guard({}, "op") is None
        assert C.destructive_guard({"strict": True}, "op") is None
        W.run(region(op="snapshot", backup_path=snap))
        r = W.run(region(op="transfer", backup_path=snap, amount=0.5))
        assert r["ok"] and r["warnings"] == [], (r["ok"], r["warnings"])

    check("result_keys_retarget", result_keys_retarget)
    check("result_keys_character_rig", result_keys_character_rig)
    check("extras_cannot_replace_file_state", extras_cannot_replace_file_state)
    check("guard_clean_file", guard_clean_file)

    bpy.ops.ed.undo_push(message="unsaved edit")          # from here on the file is dirty

    def file_state_dirty():
        r = C.report({}, [])
        assert r["file"] == {"path": "", "saved": False, "dirty": True}, r["file"]

    def guard_dirty_file():
        assert C.destructive_guard({}, "op") == f"op {WARN}"
        assert C.destructive_guard({"acknowledge_destructive": True}, "op") is None
        assert C.destructive_guard({"acknowledge_destructive": True, "strict": True}, "op") is None
        try:
            C.destructive_guard({"strict": True}, "op")
        except RuntimeError:
            return
        raise AssertionError("strict on a dirty file did not raise")

    def dirty_ops_warn_without_raising():
        before = weights_of(mesh)
        r = W.run(region(op="transfer", backup_path=snap, amount=0.6))
        assert r["ok"] and r["changed_vertices"] > 0, (r["ok"], r["changed_vertices"])
        assert r["warnings"] == [f"brt_weights transfer {WARN}"], r["warnings"]
        assert weights_of(mesh) != before, "the transfer wrote nothing"
        r = W.run(region(op="normalize"))
        assert r["ok"] and r["warnings"] == [f"brt_weights normalize {WARN}"], (r["ok"], r["warnings"])
        r = W.run(region(op="restore", backup_path=snap))
        assert r["ok"] and r["warnings"] == [f"brt_weights restore {WARN}"], (r["ok"], r["warnings"])

    def acknowledged_is_silent():
        r = W.run(region(op="transfer", backup_path=snap, amount=0.65, acknowledge_destructive=True))
        assert r["ok"] and r["warnings"] == [], (r["ok"], r["warnings"])
        W.run(region(op="restore", backup_path=snap, acknowledge_destructive=True))

    def strict_raises_before_writing():
        for op, extra in (("transfer", {"amount": 0.7}), ("normalize", {}), ("restore", {})):
            before, applied = weights_of(mesh), mesh.get(W._GUARD)
            try:
                W.run(region(op=op, backup_path=snap, strict=True, **extra))
            except RuntimeError as exc:
                assert "strict" in str(exc), str(exc)
            else:
                raise AssertionError(f"strict {op} on a dirty file did not raise")
            assert weights_of(mesh) == before, f"strict {op} changed weights before refusing"
            assert mesh.get(W._GUARD) == applied, f"strict {op} changed {W._GUARD}"

    check("file_state_dirty", file_state_dirty)
    check("guard_dirty_file", guard_dirty_file)
    check("dirty_ops_warn_without_raising", dirty_ops_warn_without_raising)
    check("acknowledged_is_silent", acknowledged_is_silent)
    check("strict_raises_before_writing", strict_raises_before_writing)

    print(f"test_blender_common: {sum(RESULTS)}/{len(RESULTS)} passed", flush=True)
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
