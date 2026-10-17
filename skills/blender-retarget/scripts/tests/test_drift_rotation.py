"""test_drift_rotation.py — brt_drift reads rotation as well as position, run in Blender.

    Blender --background --factory-startup --python tests/test_drift_rotation.py

Prints `PASS <name>` or `FAIL <name>: <why>` per case and exits 1 when any case
fails. A "RunnerRig" with one swinging "Hand.R" carries "Mallet", bone-parented
with its origin at the grip:

- held still in the hand, both drift.max_drift and drift.max_rotation pass;
- turning about its own grip point (keyed on the prop itself), drift.max_drift
  still passes and drift.max_rotation fails, naming the clip and the frame;
- slid along the hand, drift.max_drift fails.
"""
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import brt_drift as D  # noqa: E402

RESULTS: list[bool] = []


def check(name, fn):
    try:
        fn()
    except Exception as exc:          # a failed assert or anything else: report and go on
        print(f"FAIL {name}: {type(exc).__name__}: {exc}", flush=True)
        RESULTS.append(False)
    else:
        print(f"PASS {name}", flush=True)
        RESULTS.append(True)


def build():
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    scene = bpy.context.scene
    arm = bpy.data.armatures.new("RunnerRig")
    rig = bpy.data.objects.new("RunnerRig", arm)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    for name, head, tail, parent in (("Spine", (0, 0, 0.6), (0, 0, 0.9), None),
                                     ("Hand.R", (-0.2, 0, 0.9), (-0.35, 0, 0.9), "Spine")):
        bone = arm.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        if parent:
            bone.parent = arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.update()

    pb = rig.pose.bones["Hand.R"]
    pb.rotation_mode = 'QUATERNION'
    for frame, angle in ((1, 0.0), (10, 70.0)):
        pb.rotation_quaternion = (math.cos(math.radians(angle) / 2), math.sin(math.radians(angle) / 2), 0, 0)
        pb.keyframe_insert("rotation_quaternion", frame=frame)
    rig.animation_data.action.name = "GateLatchSwing"
    scene.frame_set(1)
    pb.rotation_quaternion = (1, 0, 0, 0)

    mallet = bpy.data.objects.new("Mallet", None)
    scene.collection.objects.link(mallet)
    mallet.parent = rig
    mallet.parent_type = 'BONE'
    mallet.parent_bone = "Hand.R"
    bpy.context.view_layer.update()
    from mathutils import Matrix
    mallet.matrix_world = Matrix.Translation((-0.3, 0.0, 0.9))   # its origin is the grip point
    bpy.context.view_layer.update()
    return rig, mallet


def gates(result) -> dict:
    return {g["name"]: g["pass"] for g in result["gates"]}


PARAMS = {"armature": "RunnerRig", "prop": "Mallet", "anchor_bone": "Hand.R", "samples_per_action": 9}


def main() -> int:
    rig, mallet = build()

    def held_prop_passes():
        r = D.run(PARAMS)
        assert r["ok"], r["gates"]
        assert list(r["per_action"]) == ["GateLatchSwing"], r["per_action"]
        assert r["per_action_rotation"]["GateLatchSwing"] < 1e-3, r["per_action_rotation"]

    def rotation_only_drift_is_caught():
        mallet.rotation_mode = 'XYZ'
        base = mallet.rotation_euler.copy()
        for frame, add in ((1, 0.0), (10, 30.0)):
            mallet.rotation_euler = (base.x, base.y, base.z + math.radians(add))
            mallet.keyframe_insert("rotation_euler", frame=frame)
        try:
            r = D.run(PARAMS)
            g = gates(r)
            assert g["drift.max_drift"], f"a turn about the grip moved the grip: {r['per_action']}"
            assert not g["drift.max_rotation"], r["per_action_rotation"]
            assert r["worst_rotation"]["action"] == "GateLatchSwing", r["worst_rotation"]
            assert 25.0 < r["worst_rotation"]["degrees"] <= 30.5, r["worst_rotation"]
            assert r["ok"] is False
        finally:
            act = mallet.animation_data.action
            mallet.animation_data_clear()
            bpy.data.actions.remove(act)
            mallet.rotation_euler = base

    def translation_drift_is_caught():
        loc = mallet.location.copy()
        for frame, dx in ((1, 0.0), (10, 0.01)):
            mallet.location = (loc.x + dx, loc.y, loc.z)
            mallet.keyframe_insert("location", frame=frame)
        try:
            r = D.run(PARAMS)
            assert not gates(r)["drift.max_drift"], r["per_action"]
        finally:
            act = mallet.animation_data.action
            mallet.animation_data_clear()
            bpy.data.actions.remove(act)
            mallet.location = loc

    check("held_prop_passes", held_prop_passes)
    check("rotation_only_drift_is_caught", rotation_only_drift_is_caught)
    check("translation_drift_is_caught", translation_drift_is_caught)
    print(f"test_drift_rotation: {sum(RESULTS)}/{len(RESULTS)} passed", flush=True)
    return 0 if RESULTS and all(RESULTS) else 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        print(f"FAIL setup: {type(exc).__name__}: {exc}", flush=True)
        code = 1
    sys.exit(code)
