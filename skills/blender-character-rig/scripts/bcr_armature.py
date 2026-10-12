"""bcr_armature.py — build an armature from a bone spec.

Runs inside Blender; not a command-line script (the stub is in bcr_common.py).

The spec is data the agent fills from bcr_survey, in the mesh's local
coordinates. Nothing about a particular character lives in this file.

    result = bcr_armature.run({
        "name": "RunnerRig", "collection": "Character",
        "mesh": "Runner",                 # the armature takes this object's world transform
        "mirror": True,                   # every ".L" bone also makes its ".R" twin (x -> -x)
        "bones": [
            {"name": "Root", "head": [0, 0, 0], "tail": [0, 0.18, 0], "deform": False},
            {"name": "Hips", "head": [0, 0, 0.19], "tail": [0, 0, 0.27], "parent": "Root", "radius": 0.21},
            {"name": "Head", "head": [0, 0, 0.47], "tail": [0, 0, 0.82], "parent": "Chest",
             "radius": 0.30, "segment": [[0, 0, 0.58], [0, 0, 0.74]]},
            {"name": "Ear.L", "head": [0.12, 0.02, 0.82], "tail": [0.20, 0.01, 1.04], "parent": "Head",
             "radius": 0.06},
        ],
    })

Per bone: `name`, `head`, `tail`, `parent`, `deform` (default true), `radius`
(how far from the bone its surface lies; bcr_skin divides distances by it), and
optionally `segment` — the stretch of the bone that distances are measured to,
for a ball-shaped part whose bone runs past its centre.

`.L` is the character's left: +X when the character faces -Y.

The spec is kept on the armature object as the custom property `bcr_bones`, so
bcr_skin reads the radii from the rig. An armature that already has this name
gets its bones rebuilt in place. Every pose bone is set to XYZ euler.

Gates: bone_count, zero_length_bones == 0, one root, pose bones all XYZ.
"""
from __future__ import annotations

import json

import bpy
from mathutils import Vector

import bcr_common as C


def _mirror_name(name: str) -> str:
    return name[:-2] + ".R" if name.endswith(".L") else name


def expand(bones: list[dict], mirror: bool) -> list[dict]:
    out = []
    for bone in bones:
        out.append(dict(bone))
        if mirror and bone["name"].endswith(".L"):
            twin = dict(bone)
            twin["name"] = _mirror_name(bone["name"])
            twin["parent"] = _mirror_name(bone["parent"]) if bone.get("parent") else None
            for key in ("head", "tail"):
                twin[key] = [-bone[key][0], bone[key][1], bone[key][2]]
            if bone.get("segment"):
                twin["segment"] = [[-p[0], p[1], p[2]] for p in bone["segment"]]
            out.append(twin)
    return out


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    scene = C.scene_of(params)
    col = C.collection(params["collection"], scene)
    spec = expand(params["bones"], params.get("mirror", False))
    names = [b["name"] for b in spec]
    if len(set(names)) != len(names):
        raise ValueError("duplicate bone names in the spec")
    for bone in spec:
        if bone.get("parent") and bone["parent"] not in names:
            raise ValueError(f"{bone['name']}: parent {bone['parent']} is not in the spec")

    rig = bpy.data.objects.get(params["name"])
    if rig is None:
        rig = bpy.data.objects.new(params["name"], bpy.data.armatures.new(params["name"]))
        col.objects.link(rig)
    if params.get("mesh"):
        rig.matrix_world = bpy.data.objects[params["mesh"]].matrix_world.copy()

    view_layer = bpy.context.view_layer
    previous = view_layer.objects.active
    selected = [o for o in view_layer.objects if o.select_get()]
    for o in selected:
        o.select_set(False)
    view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    edit = rig.data.edit_bones
    for old in list(edit):
        edit.remove(old)
    made = {}
    for bone in spec:
        eb = edit.new(bone["name"])
        eb.head, eb.tail = bone["head"], bone["tail"]
        eb.use_deform = bone.get("deform", True)
        made[bone["name"]] = eb
    for bone in spec:
        if bone.get("parent"):
            child, parent = made[bone["name"]], made[bone["parent"]]
            child.parent = parent
            child.use_connect = (parent.tail - child.head).length < 1e-6
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.select_set(False)
    for o in selected:
        o.select_set(True)
    view_layer.objects.active = previous

    for pose_bone in rig.pose.bones:
        pose_bone.rotation_mode = 'XYZ'
    rig["bcr_bones"] = json.dumps(spec)

    zero = [b.name for b in rig.data.bones if b.length < 1e-5]
    roots = [b.name for b in rig.data.bones if b.parent is None]
    not_xyz = [p.name for p in rig.pose.bones if p.rotation_mode != 'XYZ']
    no_radius = [b["name"] for b in spec if b.get("deform", True) and not b.get("radius")]
    gates = [
        C.gate("bone_count", len(rig.data.bones), len(spec), len(rig.data.bones) == len(spec)),
        C.gate("zero_length_bones", zero, [], not zero),
        C.gate("roots", roots, "exactly one", len(roots) == 1),
        C.gate("pose_bones_not_xyz", not_xyz, [], not not_xyz),
        C.gate("deform_bones_without_radius", no_radius, [], not no_radius),
    ]
    return C.report(params, gates, armature=rig.name, bones=[b.name for b in rig.data.bones],
                    deform=[b.name for b in rig.data.bones if b.use_deform])
