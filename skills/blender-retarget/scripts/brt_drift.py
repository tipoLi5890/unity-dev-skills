"""brt_drift.py — does a carried prop stay in the hand in every clip?

Runs inside Blender; not a command-line script (the stub is in brt_common.py).
Reads only: the frame, the rig's action and slot, its NLA mutes and its
pose_position are put back afterwards.

A prop rides on one bone. A retarget, an IK/FK switch or a prop keyed on its
own can leave it following something else in some clips, and a slip of a few
millimetres does not show in a still. The prop's relation to the anchor bone is
read with the rig in its rest position, then checked on every sample:

    G        = inv(rig world) × prop world                  # at rest: the prop in armature space
    expected = rig world × anchor pose matrix × inv(anchor matrix_local) × G × grip_local
    actual   = prop world × grip_local
    drift    = |expected.translation - actual.translation|
    turn     = angle between the rotations of expected and actual (scale removed)

    result = brt_drift.run({
        "armature": "RunnerRig", "prop": "Mallet", "anchor_bone": "Hand.R",
        "actions": None,             # or ["RunnerJog", "RunnerSwing"]
        "samples_per_action": 9, "tolerance": 2e-5, "rotation_tolerance": 0.5,
    })

Both are read: a prop that turns about its own grip point (keyed on its own,
or a child-of that follows the wrong bone's rotation only) moves no grip
point, so the distance alone passes it.

`grip_local` is the grip point in the prop's own space, a 4x4 as nested lists:
the param, else the prop's `brt_grip_local` custom property (nested, flat 16 or
JSON), else identity, because the prop's origin is its grip point (bcr_attach
puts it there). `actions` None means every action with a slot that keys pose
bones. Each action is assigned through that slot and sampled at
`samples_per_action` evenly spaced frames over its range, both ends included,
subframes allowed, with the rig's NLA tracks muted so the action plays alone.
World matrices are read from the evaluated objects after `view_layer.update()`.

Gates: drift.max_drift, the largest distance in metres over every sample of
every action, <= tolerance (default 2e-5); drift.max_rotation, the largest
angle in degrees, <= rotation_tolerance (default 0.5). `per_action` and
`per_action_rotation` give each action's own largest, `worst` and
`worst_rotation` the action and frame where each largest was found.
"""
from __future__ import annotations

import json
import math

import bpy
from mathutils import Matrix

import brt_common as C


def _flatten(value) -> list[float]:
    if hasattr(value, "to_list"):
        value = value.to_list()
    if isinstance(value, (list, tuple)):
        return [x for item in value for x in _flatten(item)]
    return [float(value)]


def _grip(params: dict, prop) -> Matrix:
    value = params.get("grip_local")
    if value is None:
        value = prop.get("brt_grip_local")
    if value is None:
        return Matrix.Identity(4)
    flat = _flatten(json.loads(value) if isinstance(value, str) else value)
    if len(flat) != 16:
        raise ValueError(f"grip_local needs 16 numbers (a 4x4), got {len(flat)}")
    return Matrix([flat[0:4], flat[4:8], flat[8:12], flat[12:16]])


def _angle(expected: Matrix, actual: Matrix) -> float:
    """Degrees between the two rotations, scale and shear removed; inf when not finite."""
    try:
        q0 = expected.to_3x3().normalized().to_quaternion()
        q1 = actual.to_3x3().normalized().to_quaternion()
        a = math.degrees(q0.rotation_difference(q1).angle)
    except (ValueError, ZeroDivisionError):
        return math.inf
    if not math.isfinite(a):
        return math.inf
    return min(a, 360.0 - a)


def _pose_slot(action, rig):
    """Index of the action's slot that keys pose bones, the one named after the rig first."""
    found = None
    for i, slot in enumerate(getattr(action, "slots", [])):
        if slot.target_id_type not in {'OBJECT', 'UNSPECIFIED'}:
            continue
        if not any(fc.data_path.startswith("pose.bones[") for fc in C.action_slot_fcurves(action, slot)):
            continue
        if slot.name_display == rig.name:
            return i
        if found is None:
            found = i
    return found


def _plan(params: dict, rig) -> list:
    names = params.get("actions")
    if names is None:
        found = [(a, _pose_slot(a, rig)) for a in bpy.data.actions]
        return [(a, i) for a, i in found if i is not None]
    plan = []
    for name in names:
        action = bpy.data.actions[name]
        index = _pose_slot(action, rig)
        if index is None:
            raise ValueError(f"action {name!r} has no slot that keys pose bones")
        plan.append((action, index))
    return plan


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    scene = C.scene_of(params)
    rig = bpy.data.objects[params["armature"]]
    prop = bpy.data.objects[params["prop"]]
    anchor = params["anchor_bone"]
    if rig.type != 'ARMATURE':
        raise ValueError(f"{rig.name!r} is a {rig.type}, not an armature")
    if anchor not in rig.data.bones:
        raise KeyError(f"{rig.name!r} has no bone {anchor!r}")
    count = max(1, int(params.get("samples_per_action", 9)))
    tolerance = params.get("tolerance", 2e-5)
    rot_tolerance = params.get("rotation_tolerance", 0.5)
    grip = _grip(params, prop)
    plan = _plan(params, rig)
    if not plan:
        raise ValueError(f"no action to sample: none has a slot that keys pose bones for {rig.name!r}")

    layer = bpy.context.view_layer if scene == bpy.context.scene else scene.view_layers[0]
    rest_inv = rig.data.bones[anchor].matrix_local.inverted()
    state = C.save_state(scene, [rig, prop])
    position = rig.data.pose_position
    per_action, worst = {}, {"action": None, "frame": None, "distance": 0.0}
    per_turn, worst_turn = {}, {"action": None, "frame": None, "degrees": 0.0}
    try:
        ad = rig.animation_data
        for track in (ad.nla_tracks if ad else []):
            track.mute = True
        rig.data.pose_position = 'REST'
        layer.update()
        deps = layer.depsgraph
        G = rig.evaluated_get(deps).matrix_world.inverted() @ prop.evaluated_get(deps).matrix_world
        rig.data.pose_position = 'POSE'

        for action, index in plan:
            C.assign_slot(rig, action, index)
            start, end = action.frame_range
            most, most_turn = 0.0, 0.0
            for k in range(count):
                f = start + (end - start) * (k / (count - 1) if count > 1 else 0.0)
                whole = math.floor(f)
                scene.frame_set(int(whole), subframe=f - whole)
                layer.update()
                rig_ev, prop_ev = rig.evaluated_get(deps), prop.evaluated_get(deps)
                bone = rig_ev.pose.bones[anchor]
                expected = rig_ev.matrix_world @ bone.matrix @ rest_inv @ G @ grip
                actual = prop_ev.matrix_world @ grip
                d = (expected.translation - actual.translation).length
                if not math.isfinite(d):
                    d = math.inf
                most = max(most, d)
                if d > worst["distance"] or worst["action"] is None:
                    worst = {"action": action.name, "frame": f, "distance": d}
                a = _angle(expected, actual)
                most_turn = max(most_turn, a)
                if a > worst_turn["degrees"] or worst_turn["action"] is None:
                    worst_turn = {"action": action.name, "frame": f, "degrees": a}
            per_action[action.name] = most
            per_turn[action.name] = most_turn
    finally:
        rig.data.pose_position = position
        restored = C.restore_state(state)

    top, turn = max(per_action.values()), max(per_turn.values())
    gates = [C.gate("drift.max_drift", top, tolerance, top <= tolerance),
             C.gate("drift.max_rotation", turn, rot_tolerance, turn <= rot_tolerance)]
    return C.report(params, gates, armature=rig.name, prop=prop.name, anchor_bone=anchor,
                    per_action=per_action, worst=worst, per_action_rotation=per_turn,
                    worst_rotation=worst_turn, samples_per_action=count,
                    grip_rest=G.translation, restore=restored)
