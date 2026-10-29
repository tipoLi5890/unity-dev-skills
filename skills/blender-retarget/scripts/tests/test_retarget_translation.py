"""test_retarget_translation.py — brt_retarget's root translation on synthetic rigs, run in Blender.

    Blender --background --factory-startup --python tests/test_retarget_translation.py

Prints `PASS <name>` or `FAIL <name>: <why>` per case and exits 1 when any case
fails. Writes nothing to disk. Ground truth is read back from Blender's own
evaluated pose, not from brt_retarget's formula: the source rig is turned 90°
about Z and the target is twice its size with a rolled hip, so at every frame
the target hip's world head must move by exactly 2 × the source hip's world
move (k = 2.0 / 1.0). Also covered: `translate: False` on a moving source fails
retarget.translation_kept; `in_place` removes the straight horizontal travel
and keeps the rise; `translation_scale` replaces k; a stray location curve on a
bone under a mapped hip is never written; a moving hip left out of the map is
warned about; a root on the floor reads k on the mapped hip below it; a clip without location curves writes none and has no
translation gate; in_place on a pure straight travel leaves nothing to keep (no gate) and
reports the travel it took out.
"""
import math
import os
import sys

import bpy
from mathutils import Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import brt_common as C  # noqa: E402
import brt_retarget as R  # noqa: E402

RESULTS: list[bool] = []
FRAMES = 6


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


def scene():
    """Source: hip 1.0 m over its toe, turned 90° about Z. Target: twice the size, hip rolled 30°."""
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    src = rig("CourierMocap", [("hips", (0, 0, 1.0), (0, 0, 1.3), 0.0, None),
                               ("spine", (0, 0, 1.3), (0, 0, 1.6), 0.0, "hips"),
                               ("foot", (0.1, 0, 0.1), (0.1, -0.1, 0.0), 0.0, "hips")],
              rotation_z=math.pi / 2)
    tgt = rig("RunnerRig", [("Hips", (0, 0, 2.0), (0, 0, 2.6), math.radians(30), None),
                            ("Spine", (0, 0, 2.6), (0, 0, 3.2), 0.0, "Hips"),
                            ("Foot", (0.2, 0, 0.2), (0.2, -0.2, 0.0), 0.0, "Hips")])
    return src, tgt


def key(action, slot, path, index, values):
    fc = C.ensure_fcurve(action, slot, path, index)
    fc.keyframe_points.add(len(values))
    fc.keyframe_points.foreach_set("co", [x for f, v in enumerate(values, 1) for x in (f, v)])
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'
    fc.update()


def clip(src, name, location=True, spine_location=False):
    """Hips: a small rotation per frame and, with `location`, a travel along the bone's local
    X and Z plus a rise along its local Y (the bone points up, so Y is world up)."""
    action = bpy.data.actions.new(name)
    slot = C.assign_slot(src, action)
    for b in ("hips", "spine"):
        src.pose.bones[b].rotation_mode = 'QUATERNION'
        qs = [Quaternion((0.2, 0.3, 1.0), 0.05 * j) for j in range(FRAMES)]
        for i in range(4):
            key(action, slot, f'pose.bones["{b}"].rotation_quaternion', i, [q[i] for q in qs])
    if location:
        key(action, slot, 'pose.bones["hips"].location', 0, [0.10 * j for j in range(FRAMES)])
        key(action, slot, 'pose.bones["hips"].location', 1, [0.02 * math.sin(j) for j in range(FRAMES)])
        key(action, slot, 'pose.bones["hips"].location', 2, [-0.05 * j for j in range(FRAMES)])
    if spine_location:
        key(action, slot, 'pose.bones["spine"].location', 1, [0.0, 1e-5, 0.0, 1e-5, 0.0, 0.0])
    return action


def head_world(obj, bone):
    return obj.matrix_world @ obj.pose.bones[bone].head


def play(obj, action):
    ad = obj.animation_data
    ad.action = action
    if getattr(ad, "action_slot", None) is None and len(action.slots):
        ad.action_slot = action.slots[0]


def moves(obj, bone, action):
    """World head offset from frame 1 at every frame, as Blender evaluates the pose."""
    play(obj, action)
    scene = bpy.context.scene
    out = []
    for f in range(1, FRAMES + 1):
        scene.frame_set(f)
        out.append(head_world(obj, bone).copy())
    return out


def rest_head(obj, bone):
    return obj.matrix_world @ obj.data.bones[bone].head_local


def base(**kw):
    p = {"source": "CourierMocap", "target": "RunnerRig", "source_action": "CourierWalk",
         "map": {"Hips": "hips", "Spine": "spine"}, "output_action": "Runner_Walk"}
    p.update(kw)
    return p


def case_world_move_is_k_times_source():
    src, tgt = scene()
    action = clip(src, "CourierWalk")
    out = R.run(base())
    assert out["ok"], out["gates"]
    assert out["translation"] == "retargeted", out["translation"]
    assert abs(out["translation_k"] - 2.0) < 1e-9, out["translation_k"]
    assert abs(out["source_hip_height_m"] - 1.0) < 1e-9 and abs(out["target_hip_height_m"] - 2.0) < 1e-9
    assert out["translation_bones"] == {"Hips": "hips"}
    assert out["hip_bones"] == {"source": "hips", "target": "Hips"}, out["hip_bones"]
    assert "retarget.translation_kept" in [g["name"] for g in out["gates"]]
    s_moves = moves(src, "hips", action)
    t_moves = moves(tgt, "Hips", bpy.data.actions["Runner_Walk"])
    s_rest, t_rest = rest_head(src, "hips"), rest_head(tgt, "Hips")
    worst = max(((t - t_rest) - 2.0 * (s - s_rest)).length for s, t in zip(s_moves, t_moves))
    assert worst < 1e-5, f"world move off by {worst:.3g} m"
    # copying the four numbers (times k) would have moved the target elsewhere: the source is
    # turned 90° and the target hip rolled, so the written location differs from 2 x the source's
    written = {fc.array_index: fc.evaluate(FRAMES) for fc in C.action_slot_fcurves(bpy.data.actions["Runner_Walk"])
               if fc.data_path == 'pose.bones["Hips"].location'}
    naive = Vector((0.10, 0.02 * math.sin(FRAMES - 1), -0.05)) * (FRAMES - 1) * 2.0
    naive.y = 2.0 * 0.02 * math.sin(FRAMES - 1)
    assert (Vector([written[i] for i in range(3)]) - naive).length > 0.1, (written, naive)


def case_translate_false_fails_gate():
    src, tgt = scene()
    clip(src, "CourierWalk")
    out = R.run(base(translate=False))
    gate = next(g for g in out["gates"] if g["name"] == "retarget.translation_kept")
    assert not gate["pass"] and not out["ok"], out["gates"]
    assert out["translation"] == "dropped" and gate["value"] == ["Hips"], (out["translation"], gate)
    action = bpy.data.actions["Runner_Walk"]
    assert not [fc for fc in C.action_slot_fcurves(action) if fc.data_path.endswith(".location")]


def case_in_place_keeps_rise():
    src, tgt = scene()
    action = clip(src, "CourierWalk")
    out = R.run(base(translate="in_place"))
    assert out["ok"] and out["translation"] == "in place", out["gates"]
    t_moves = moves(tgt, "Hips", bpy.data.actions["Runner_Walk"])
    s_moves = moves(src, "hips", action)
    t_rest, s_rest = rest_head(tgt, "Hips"), rest_head(src, "hips")
    first, last = t_moves[0] - t_rest, t_moves[-1] - t_rest
    assert abs(first.x) < 1e-5 and abs(first.y) < 1e-5 and abs(last.x) < 1e-5 and abs(last.y) < 1e-5, (first, last)
    rise = [(t - t_rest).z - 2.0 * (s - s_rest).z for s, t in zip(s_moves, t_moves)]
    assert max(abs(r) for r in rise) < 1e-5, rise


def case_translation_scale_overrides_k():
    src, tgt = scene()
    clip(src, "CourierWalk")
    out = R.run(base(translation_scale=1.5))
    assert out["ok"] and abs(out["translation_k"] - 1.5) < 1e-12, out
    assert "source_hip_height_m" not in out


def case_stray_location_below_hip_not_written():
    src, tgt = scene()
    clip(src, "CourierWalk", spine_location=True)
    out = R.run(base())
    assert out["ok"], out["gates"]
    assert out["translation_keyed"] == ["hips", "spine"] and out["translation_bones"] == {"Hips": "hips"}
    paths = {fc.data_path for fc in C.action_slot_fcurves(bpy.data.actions["Runner_Walk"])}
    assert 'pose.bones["Spine"].location' not in paths and 'pose.bones["Hips"].location' in paths, paths


def case_rotation_only_clip_unchanged():
    src, tgt = scene()
    clip(src, "CourierWalk", location=False)
    out = R.run(base())
    assert out["ok"], out["gates"]
    assert out["translation"] == "not retargeted"
    assert [g["name"] for g in out["gates"]] == ["retarget.output_is_new", "retarget.finite_keys"]
    paths = {fc.data_path for fc in C.action_slot_fcurves(bpy.data.actions["Runner_Walk"])}
    assert not [p for p in paths if p.endswith(".location")], paths


def case_root_on_floor_reads_k_on_hip():
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    src = rig("CourierMocap", [("root", (0, 0, 0), (0, 0.2, 0), 0.0, None),
                               ("hips", (0, 0, 1.0), (0, 0, 1.3), 0.0, "root")])
    rig("RunnerRig", [("Root", (0, 0, 0), (0, 0.3, 0), 0.0, None),
                      ("Hips", (0, 0, 1.5), (0, 0, 1.9), 0.0, "Root")])
    action = bpy.data.actions.new("CourierWalk")
    slot = C.assign_slot(src, action)
    for b in ("root", "hips"):
        src.pose.bones[b].rotation_mode = 'QUATERNION'
        for i in range(4):
            key(action, slot, f'pose.bones["{b}"].rotation_quaternion', i, [1.0 if i == 0 else 0.0] * FRAMES)
    key(action, slot, 'pose.bones["root"].location', 1, [0.2 * j for j in range(FRAMES)])
    # a hip bob under the travelling root: not copied, and said so
    key(action, slot, 'pose.bones["hips"].location', 1, [0.03 * math.sin(j) for j in range(FRAMES)])
    out = R.run(base(map={"Root": "root", "Hips": "hips"}))
    assert out["ok"] and out["translation_bones"] == {"Root": "root"}, out
    assert out["hip_bones"] == {"source": "hips", "target": "Hips"} and abs(out["translation_k"] - 1.5) < 1e-9, out
    assert any("['hips'] moves over 1 cm under a translation bone" in w for w in out["warnings"]), out["warnings"]


def case_in_place_pure_travel():
    """A root whose only motion is a straight travel: in_place leaves nothing, so no gate fails;
    the travel taken out is reported (k x 0.2 m per frame at the scene rate)."""
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    src = rig("CourierMocap", [("root", (0, 0, 0), (0, 0.2, 0), 0.0, None),
                               ("hips", (0, 0, 1.0), (0, 0, 1.3), 0.0, "root")])
    rig("RunnerRig", [("Root", (0, 0, 0), (0, 0.3, 0), 0.0, None),
                      ("Hips", (0, 0, 1.5), (0, 0, 1.9), 0.0, "Root")])
    action = bpy.data.actions.new("CourierWalk")
    slot = C.assign_slot(src, action)
    for b in ("root", "hips"):
        src.pose.bones[b].rotation_mode = 'QUATERNION'
        for i in range(4):
            key(action, slot, f'pose.bones["{b}"].rotation_quaternion', i, [1.0 if i == 0 else 0.0] * FRAMES)
    key(action, slot, 'pose.bones["root"].location', 1, [0.2 * j for j in range(FRAMES)])
    out = R.run(base(map={"Root": "root", "Hips": "hips"}, translate="in_place"))
    assert out["ok"] and out["translation"] == "in place", out["gates"]
    assert "retarget.translation_kept" not in [g["name"] for g in out["gates"]], out["gates"]
    fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    vx, vy = out["in_place_travel_mps"]["Root"]
    # the source root bone points +Y, so its location Y is world +Y
    assert abs(vx) < 1e-5 and abs(vy - 1.5 * 0.2 * fps) < 1e-3, out["in_place_travel_mps"]


def case_unmapped_carrier_warns():
    src, tgt = scene()
    clip(src, "CourierWalk")
    out = R.run(base(map={"Spine": "spine"}))
    assert out["ok"] and out["translation"] == "not retargeted", out
    assert not [g for g in out["gates"] if g["name"] == "retarget.translation_kept"]
    assert any("['hips'] move but are not mapped" in w for w in out["warnings"]), out["warnings"]


for name, fn in (("unmapped_moving_hip_is_warned", case_unmapped_carrier_warns),
                 ("root_on_floor_reads_k_on_hip", case_root_on_floor_reads_k_on_hip),
                 ("world_move_is_k_times_source", case_world_move_is_k_times_source),
                 ("translate_false_fails_translation_kept", case_translate_false_fails_gate),
                 ("in_place_removes_travel_keeps_rise", case_in_place_keeps_rise),
                 ("translation_scale_overrides_k", case_translation_scale_overrides_k),
                 ("stray_location_below_hip_not_written", case_stray_location_below_hip_not_written),
                 ("rotation_only_clip_writes_no_location", case_rotation_only_clip_unchanged),
                 ("in_place_pure_travel_has_nothing_to_keep", case_in_place_pure_travel)):
    check(name, fn)

print(f"{sum(RESULTS)}/{len(RESULTS)} passed", flush=True)
sys.exit(0 if all(RESULTS) else 1)
