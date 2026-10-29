"""test_retarget_conjugation.py — brt_retarget on synthetic two-bone rigs, run in Blender.

    Blender --background --factory-startup --python tests/test_retarget_conjugation.py

Prints `PASS <name>` or `FAIL <name>: <why>` per case and exits 1 when any case
fails. Writes nothing to disk. Covers: with the source rig turned 90° about Z
and a target rolled differently, every written key equals K·q·K⁻¹ within 1e-6,
K computed here from the rests alone; a correct clip stepping about 1 rad per
frame passes, with max_step reported and no max_step gate; into_action adds
exactly the mapped quaternion curves and leaves every other curve's keys as they
were; a mapped bone that already has a rotation curve refuses without replace
and is replaced with it; a clip without location curves reports translation as
not retargeted, and into_action keeps the hip location an action already has
(translation is covered in test_retarget_translation.py); with a
T-pose source arm against an A-pose target arm whose hand tail is off the arm
line, a hand converted alone with the arm in `reference_map` (or the arm mapped
and the hand in `no_aim`) gets the K computed here by walking the source with
the arm aimed and the hand not, and differs from aiming the hand.
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import brt_common as C  # noqa: E402
import brt_retarget as R  # noqa: E402

RESULTS: list[bool] = []
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


def rig(name, bones, rotation_z=0.0):
    """An armature object; bones are (name, head, tail, roll, parent)."""
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.rotation_euler = (0.0, 0.0, rotation_z)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    for bone, head, tail, roll, parent in bones:
        eb = data.edit_bones.new(bone)
        eb.head, eb.tail, eb.roll = Vector(head), Vector(tail), roll
        if parent:
            eb.parent = data.edit_bones[parent]
            eb.use_connect = False
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.update()
    return obj


def key_rotations(obj, action_name, per_bone):
    """per_bone: bone -> list of quaternions, one per frame from 1."""
    action = bpy.data.actions.new(action_name)
    slot = C.assign_slot(obj, action)
    for bone, quats in per_bone.items():
        obj.pose.bones[bone].rotation_mode = 'QUATERNION'
        path = f'pose.bones["{bone}"].rotation_quaternion'
        for i in range(4):
            fc = C.ensure_fcurve(action, slot, path, i, group_name=bone)
            fc.keyframe_points.add(len(quats))
            fc.keyframe_points.foreach_set("co", [x for f, q in enumerate(quats, 1) for x in (f, q[i])])
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'
            fc.update()
    return action


def scene():
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    # same shape, bones up +Z; the source is turned 90° about Z, the target rolled 30° / -50°
    src = rig("CourierMocap", [("hips", (0, 0, 1), (0, 0, 1.3), 0.0, None),
                               ("spine", (0, 0, 1.3), (0, 0, 1.7), 0.4, "hips")], rotation_z=math.pi / 2)
    tgt = rig("RunnerRig", [("Hips", (0, 0, 1), (0, 0, 1.3), math.radians(30), None),
                            ("Spine", (0, 0, 1.3), (0, 0, 1.7), math.radians(-50), "Hips")])
    return src, tgt


def rest_world(obj, bone):
    return (obj.matrix_world.to_3x3().normalized().to_quaternion()
            @ obj.data.bones[bone].matrix_local.to_3x3().normalized().to_quaternion())


def expected_K(src, tgt, s, t):
    """K = inv(T) × S. Both rests point along world +Z, so the swing is the identity and
    S is the source's world rest: the walk ref[child] = ref[parent] inv(R[parent]) R[child]
    with ref[root] = W R[root] reduces to W R[b]."""
    return (rest_world(tgt, t).inverted() @ rest_world(src, s)).normalized()


def written(action, bone):
    path = f'pose.bones["{bone}"].rotation_quaternion'
    fcs = {fc.array_index: fc for fc in C.action_slot_fcurves(action) if fc.data_path == path}
    assert sorted(fcs) == [0, 1, 2, 3], f"{bone}: curves {sorted(fcs)}"
    n = len(fcs[0].keyframe_points)
    return [Quaternion([fcs[i].keyframe_points[j].co[1] for i in range(4)]) for j in range(n)]


def close(q, e):
    return min(max(abs(a - b) for a, b in zip(q, e)), max(abs(a + b) for a, b in zip(q, e)))


def clip_quats(n, axis, step):
    return [Quaternion(axis, step * j) for j in range(n)]


def snapshot(action):
    out = {}
    for fc in C.action_slot_fcurves(action):
        co = [0.0] * (2 * len(fc.keyframe_points))
        fc.keyframe_points.foreach_get("co", co)
        ip = [0] * len(fc.keyframe_points)
        fc.keyframe_points.foreach_get("interpolation", ip)
        out[(fc.data_path, fc.array_index)] = (tuple(co), tuple(ip))
    return out


def case_conjugation():
    src, tgt = scene()
    hips = [Quaternion((1, 0.3, -0.2), 0.25 * j).normalized() for j in range(6)]
    spine = [Quaternion((0.2, 1, 0.5), -0.3 * j) for j in range(6)]
    key_rotations(src, "CourierJog", {"hips": hips, "spine": spine})
    out = R.run({"source": "CourierMocap", "target": "RunnerRig", "source_action": "CourierJog",
                 "map": {"Hips": "hips", "Spine": "spine"}, "output_action": "Runner_Jog"})
    assert out["ok"], out["gates"]
    names = [g["name"] for g in out["gates"]]
    assert names == ["retarget.output_is_new", "retarget.finite_keys"], names
    assert out["translation"] == "not retargeted"
    action = bpy.data.actions["Runner_Jog"]
    worst = 0.0
    for t, s, quats in (("Hips", "hips", hips), ("Spine", "spine", spine)):
        K = expected_K(src, tgt, s, t)
        assert abs(K.angle) > 0.1, "K must not be trivial"
        got = written(action, t)
        assert len(got) == len(quats)
        for q, qs in zip(got, quats):
            worst = max(worst, close(q, (K @ qs @ K.inverted()).normalized()))
    assert worst <= TOL, f"largest deviation {worst:.3g} > {TOL}"
    assert tgt.animation_data.action == action


def case_fast_clip():
    src, tgt = scene()
    fast = clip_quats(8, Vector((1, 0, 0)), 1.0)          # 1 rad per frame, a correct clip
    key_rotations(src, "CourierSpin", {"hips": fast})
    out = R.run({"source": "CourierMocap", "target": "RunnerRig", "source_action": "CourierSpin",
                 "map": {"Hips": "hips"}, "output_action": "Runner_Spin", "max_step_rad": 0.35})
    assert out["ok"], out["gates"]
    assert not any(g["name"] == "retarget.max_step" for g in out["gates"])
    assert abs(out["max_step"] - 1.0) < 1e-4, out["max_step"]
    assert abs(out["source_max_step"] - 1.0) < 1e-4, out["source_max_step"]
    assert out["max_step_at"]["bone"] == "Hips"
    assert any("max_step_rad is ignored" in w for w in out["warnings"]), out["warnings"]


def into_fixture():
    src, tgt = scene()
    quats = clip_quats(5, Vector((0, 1, 0)), 0.2)
    clip = key_rotations(src, "CourierLane", {"hips": quats, "spine": quats})
    loc = C.ensure_fcurve(clip, None, 'pose.bones["hips"].location', 2)
    loc.keyframe_points.insert(1, 0.0)
    loc.keyframe_points.insert(5, 0.4)
    # the action another tool baked: Spine rotation, Hips location, plus an unrelated custom curve
    baked = bpy.data.actions.new("JogLaneLeft")
    baked.use_fake_user = True
    slot = baked.slots.new(id_type='OBJECT', name=tgt.name)
    for path, idx, values in (('pose.bones["Spine"].rotation_quaternion', 0, (1.0, 0.9, 0.8, 0.9, 1.0)),
                              ('pose.bones["Spine"].rotation_quaternion', 1, (0.0, 0.1, 0.2, 0.1, 0.0)),
                              ('pose.bones["Hips"].location', 0, (0.0, 0.1, 0.2, 0.3, 0.4)),
                              ('pose.bones["Hips"]["custom"]', 0, (1.0, 1.0, 0.0, 0.0, 1.0))):
        fc = C.ensure_fcurve(baked, slot, path, idx)
        for f, v in enumerate(values, 1):
            fc.keyframe_points.insert(f, v)
    other = bpy.data.actions.new("Idle")       # what the target plays, untouched by into_action
    C.assign_slot(tgt, other)
    return src, tgt, baked, other


def case_into_action():
    src, tgt, baked, other = into_fixture()
    before = snapshot(baked)
    out = R.run({"source": "CourierMocap", "target": "RunnerRig", "source_action": "CourierLane",
                 "map": {"Hips": "hips"}, "into_action": "JogLaneLeft"})
    assert out["ok"], out["gates"]
    assert [g["name"] for g in out["gates"]] == ["retarget.channels_free", "retarget.finite_keys",
                                                 "retarget.translation_kept"], out["gates"]
    after = snapshot(baked)
    added = set(after) - set(before)
    want = {('pose.bones["Hips"].rotation_quaternion', i) for i in range(4)}
    assert added == want, sorted(added)
    assert set(before) <= set(after), "a curve was removed"
    for key, value in before.items():
        assert after[key] == value, f"{key} changed"
    assert len(after[('pose.bones["Hips"].rotation_quaternion', 0)][0]) == 10    # frames 1-5
    assert tgt.animation_data.action == other, "into_action changed what the target plays"
    assert out["translation"] == "present in into_action" and out["translation_keyed"] == ["hips"]
    assert [g["pass"] for g in out["gates"] if g["name"] == "retarget.translation_kept"] == [True]
    assert "brt_retarget" in baked.keys()


def case_into_refuses_then_replaces():
    src, tgt, baked, other = into_fixture()
    before = snapshot(baked)
    out = R.run({"source": "CourierMocap", "target": "RunnerRig", "source_action": "CourierLane",
                 "map": {"Spine": "spine"}, "into_action": "JogLaneLeft"})
    assert not out["ok"] and out["reason"] == "channels_exist", out
    assert snapshot(baked) == before, "a refusal changed the action"
    out = R.run({"source": "CourierMocap", "target": "RunnerRig", "source_action": "CourierLane",
                 "map": {"Spine": "spine"}, "into_action": "JogLaneLeft", "replace": True})
    assert out["ok"], out["gates"]
    after = snapshot(baked)
    for key, value in before.items():
        if key[0] != 'pose.bones["Spine"].rotation_quaternion':
            assert after[key] == value, f"{key} changed"
    spine = {k: v for k, v in after.items() if k[0] == 'pose.bones["Spine"].rotation_quaternion'}
    assert sorted(i for _, i in spine) == [0, 1, 2, 3]
    assert all(len(co) == 10 for co, _ in spine.values())
    # the merged record keeps both bones once the second conversion lands
    out = R.run({"source": "CourierMocap", "target": "RunnerRig", "source_action": "CourierLane",
                 "map": {"Hips": "hips"}, "into_action": "JogLaneLeft"})
    assert out["ok"], out["gates"]
    import json
    record = json.loads(baked["brt_retarget"])
    assert set(record["map"]) == {"Hips", "Spine"}, record["map"]


def case_into_rejects_output_action():
    into_fixture()
    try:
        R.run({"source": "CourierMocap", "target": "RunnerRig", "source_action": "CourierLane",
               "map": {"Hips": "hips"}, "into_action": "JogLaneLeft", "output_action": "X"})
    except RuntimeError as exc:
        assert "into_action" in str(exc)
    else:
        raise AssertionError("output_action with into_action was accepted")


def aim_scene():
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    s = math.sqrt(0.5)
    src = rig("CourierMocap", [("arm", (0.2, 0, 1.5), (0.5, 0, 1.5), 0.0, None),            # T-pose
                               ("hand", (0.5, 0, 1.5), (0.6, 0, 1.5), 0.3, "arm")])
    elbow = (0.2 + 0.3 * s, 0, 1.5 - 0.3 * s)
    tgt = rig("RunnerRig", [("c_arm_fk.r", (0.2, 0, 1.5), elbow, 0.2, None),                # A-pose
                            ("c_hand_fk.r", elbow, (elbow[0] + 0.1, 0.02, elbow[2] - 0.03), -0.4,
                             "c_arm_fk.r")])                     # hand tail off the arm line
    quats = [Quaternion((0.3, 0.2, 1), 0.2 * j).normalized() for j in range(5)]
    key_rotations(src, "CourierSwing", {"arm": quats, "hand": quats})
    return src, tgt, quats


def walked_K(src, tgt, aimed, s, t):
    """K = inv(T) × S with S from the source walked root first, each bone in `aimed`
    ({source: target}) swung from its +Y onto its target's head→tail direction."""
    rests = {b.name: b.matrix_local.to_quaternion().normalized() for b in src.data.bones}
    world = src.matrix_world.to_quaternion().normalized()
    ref = {}
    for b in src.data.bones:                  # parents come first in this two-bone rig
        rot = (ref[b.parent.name] @ rests[b.parent.name].conjugated() @ rests[b.name]) if b.parent \
            else world @ rests[b.name]
        if b.name in aimed:
            tb = tgt.data.bones[aimed[b.name]]
            d = tgt.matrix_world.to_3x3() @ (tb.tail_local - tb.head_local)
            rot = (rot @ Vector((0, 1, 0))).rotation_difference(d.normalized()) @ rot
        ref[b.name] = rot.normalized()
    return (rest_world(tgt, t).conjugated() @ ref[s]).normalized()


def case_reference_map_aims_ancestors():
    src, tgt, quats = aim_scene()
    want = walked_K(src, tgt, {"arm": "c_arm_fk.r"}, "hand", "c_hand_fk.r")
    hand_aimed = walked_K(src, tgt, {"arm": "c_arm_fk.r", "hand": "c_hand_fk.r"}, "hand", "c_hand_fk.r")
    assert math.degrees(want.rotation_difference(hand_aimed).angle) > 5, "the fixture does not separate them"
    base = {"source": "CourierMocap", "target": "RunnerRig", "source_action": "CourierSwing"}
    out = R.run({**base, "map": {"c_hand_fk.r": "hand"}, "reference_map": {"c_arm_fk.r": "arm"},
                 "output_action": "Runner_SwingHand"})
    assert out["ok"], out["gates"]
    assert out["aimed"] == ["c_arm_fk.r"], out["aimed"]
    assert close(Quaternion(out["K"]["c_hand_fk.r"]), want) <= 1e-4, (out["K"], list(want))   # reported rounded
    got = written(bpy.data.actions["Runner_SwingHand"], "c_hand_fk.r")
    worst = max(close(q, (want @ qs @ want.inverted()).normalized()) for q, qs in zip(got, quats))
    assert worst <= TOL, f"largest deviation {worst:.3g}"
    import json
    record = json.loads(bpy.data.actions["Runner_SwingHand"]["brt_retarget"])
    assert record["aim"] == {"c_hand_fk.r": {"c_arm_fk.r": "arm"}}, record
    # the same K with both bones written and the hand left unaimed
    out = R.run({**base, "map": {"c_arm_fk.r": "arm", "c_hand_fk.r": "hand"}, "no_aim": ["c_hand_fk.r"],
                 "output_action": "Runner_SwingBoth"})
    assert out["ok"], out["gates"]
    assert close(Quaternion(out["K"]["c_hand_fk.r"]), want) <= 1e-4, out["K"]
    arm = walked_K(src, tgt, {"arm": "c_arm_fk.r"}, "arm", "c_arm_fk.r")
    assert abs(arm.angle) > 0.1 and close(Quaternion(out["K"]["c_arm_fk.r"]), arm) <= 1e-4, out["K"]
    # the map alone aims the hand onto its fitted tail: a different K
    out = R.run({**base, "map": {"c_hand_fk.r": "hand"}, "output_action": "Runner_SwingAimed"})
    assert close(Quaternion(out["K"]["c_hand_fk.r"]), walked_K(src, tgt, {"hand": "c_hand_fk.r"},
                                                                "hand", "c_hand_fk.r")) <= 1e-4, out["K"]


for name, fn in (("conjugation_matches_K_q_Kinv", case_conjugation),
                 ("reference_map_aims_ancestors_not_hand", case_reference_map_aims_ancestors),
                 ("fast_correct_clip_passes", case_fast_clip),
                 ("into_action_adds_only_mapped_curves", case_into_action),
                 ("into_action_refuses_then_replaces", case_into_refuses_then_replaces),
                 ("into_action_rejects_output_action", case_into_rejects_output_action)):
    check(name, fn)

print(f"{sum(RESULTS)}/{len(RESULTS)} passed", flush=True)
sys.exit(0 if all(RESULTS) else 1)
