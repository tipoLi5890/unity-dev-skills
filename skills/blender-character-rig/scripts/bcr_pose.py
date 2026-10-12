"""bcr_pose.py — pose and key a rig in armature axes, not bone axes.

Runs inside Blender; not a command-line script (the stub is in bcr_common.py).

A bone's own axes depend on its roll, so "rotate the upper arm 40 degrees about
X" means something different on every bone. Here every rotation is given in the
armature's axes — for a character that faces -Y: X is its left, -Y its front, Z
up — and converted to the bone's local euler with its rest matrix. Each
rotation is relative to the parent, so a twisted chest carries the arm with it.

A rotation is a list of steps, applied in the order written:

    [["Y", 40], ["X", -85]]     # raise the arm sideways, then swing it back

    bcr_pose.run({"op": "apply", "armature": "RunnerRig",
                  "pose": {"UpperArm.R": [["Y", 100]], "Head": [["X", 10], ["Z", 30]]}})
    bcr_pose.run({"op": "reset", "armature": "RunnerRig"})

    bcr_pose.run({"op": "key", "armature": "RunnerRig", "action": "GateLatchSwing",
                  "fps": 24, "loop": True, "set_scene_range": True,
                  "frames": {"1": {...}, "13": {...}, "18": {...}, "40": {...}}})

    bcr_pose.run({"op": "key_object", "object": "GateLatch", "action": "GateLatchPop",
                  "frames": {"1": [], "18": [], "19": [["X", 3.5]], "21": [["X", -2.2]], "29": []}})

`key` is FK only. A bone named in any frame is keyed in every frame; where a
frame leaves it out it is keyed at rest. An action that already has the name is
replaced. `loop` asks for the last frame to equal the first. `key_object` keys
an object's own rotation, in world axes, for a target that reacts.

Returns the action name, whether the object's action slot is assigned (an
action without one drives nothing), the frame range, the keyed bones and the
f-curve count. Gates: slot assigned, f-curves present, first_equals_last when
`loop` is set.
"""
from __future__ import annotations

import bpy
from mathutils import Euler, Matrix

import bcr_common as C


def _local_euler(pose_bone, steps) -> Euler:
    rest = pose_bone.bone.matrix_local.to_3x3()
    local = rest.inverted() @ C.rotation(steps) @ rest
    return local.to_euler('XYZ', pose_bone.rotation_euler)   # stay near the previous value


def _apply(rig, pose: dict) -> None:
    for name, steps in pose.items():
        pose_bone = rig.pose.bones[name]
        pose_bone.rotation_euler = _local_euler(pose_bone, steps)


def _reset(rig) -> None:
    for pose_bone in rig.pose.bones:
        pose_bone.location = (0, 0, 0)
        pose_bone.rotation_euler = (0, 0, 0)
        pose_bone.scale = (1, 1, 1)


def _fresh_action(owner, name: str):
    old = bpy.data.actions.get(name)
    if old is not None:
        bpy.data.actions.remove(old)
    owner.animation_data_create()
    owner.animation_data.action = bpy.data.actions.new(name)
    return owner.animation_data.action


def _fcurves(owner) -> list:
    data = owner.animation_data
    action = data.action if data else None
    if action is None:
        return []
    slot = getattr(data, "action_slot", None)
    if slot is not None and getattr(action, "layers", None):
        out = []
        for layer in action.layers:
            for strip in layer.strips:
                bag = strip.channelbag(slot)
                if bag is not None:
                    out.extend(bag.fcurves)
        return out
    return list(getattr(action, "fcurves", []))


def _action_report(owner) -> dict:
    data = owner.animation_data
    action = data.action
    curves = _fcurves(owner)
    slotted = hasattr(data, "action_slot")
    return {
        "action": action.name, "fcurves": len(curves),
        "slot_assigned": (data.action_slot is not None) if slotted else True,
        "frame_range": [int(action.frame_range[0]), int(action.frame_range[1])],
        "curves": curves,
    }


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    op = params.get("op", "apply")
    scene = C.scene_of(params)

    if op == "key_object":
        obj = bpy.data.objects[params["object"]]
        obj.rotation_mode = 'XYZ'
        _fresh_action(obj, params["action"])
        base = obj.rotation_euler.to_matrix()
        for frame, steps in sorted(params["frames"].items(), key=lambda kv: int(kv[0])):
            obj.rotation_euler = (C.rotation(steps) @ base).to_euler('XYZ', obj.rotation_euler)
            obj.keyframe_insert("rotation_euler", frame=int(frame))
        obj.rotation_euler = base.to_euler('XYZ')
        info = _action_report(obj)
        info.pop("curves")
        gates = [C.gate("slot_assigned", info["slot_assigned"], True, info["slot_assigned"]),
                 C.gate("fcurves", info["fcurves"], "> 0", info["fcurves"] > 0)]
        return C.report(params, gates, object=obj.name, **info)

    rig = bpy.data.objects[params["armature"]]
    if op == "reset":
        _reset(rig)
        bpy.context.view_layer.update()
        one = Matrix.Identity(4)
        off = max(abs(pb.matrix_basis[r][c] - one[r][c]) for pb in rig.pose.bones for r in range(4) for c in range(4))
        return C.report(params, [C.gate("pose_is_rest", off, "< 1e-6", off < 1e-6)], armature=rig.name)

    if op == "apply":
        _apply(rig, params["pose"])
        bpy.context.view_layer.update()
        return C.report(params, [], armature=rig.name, posed=sorted(params["pose"]))

    if op != "key":
        raise ValueError(f"unknown op {op!r}")
    frames = {int(f): pose for f, pose in params["frames"].items()}
    keyed = sorted({name for pose in frames.values() for name in pose})
    _reset(rig)
    _fresh_action(rig, params["action"])
    for frame in sorted(frames):
        for name in keyed:
            pose_bone = rig.pose.bones[name]
            pose_bone.rotation_euler = _local_euler(pose_bone, frames[frame].get(name, []))
            pose_bone.keyframe_insert("rotation_euler", frame=frame)
    first, last = min(frames), max(frames)
    if params.get("fps"):
        scene.render.fps = params["fps"]
    if params.get("set_scene_range", True):
        scene.frame_start, scene.frame_end = first, last
    scene.frame_set(first)

    info = _action_report(rig)
    drift = max((abs(c.evaluate(first) - c.evaluate(last)) for c in info.pop("curves")), default=0.0)
    gates = [
        C.gate("slot_assigned", info["slot_assigned"], True, info["slot_assigned"]),
        C.gate("fcurves", info["fcurves"], f">= {3 * len(keyed)}", info["fcurves"] >= 3 * len(keyed)),
    ]
    if params.get("loop"):
        gates.append(C.gate("first_equals_last", drift, "< 1e-5", drift < 1e-5))
    return C.report(params, gates, armature=rig.name, keyed_bones=keyed, keyed_frames=sorted(frames),
                    fps=scene.render.fps, scene_range=[scene.frame_start, scene.frame_end], **info)
