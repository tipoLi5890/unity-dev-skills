"""bcr_fbx.py — export the rig as FBX and read the file back.

Runs inside Blender; not a command-line script (the stub is in bcr_common.py).

An export that returns FINISHED says a file was written, not that the rig is in
it. This takes a snapshot of the rig, exports, imports the file into a scene of
its own and takes the same snapshot there; `rig_gate.py` compares the two.

    before = bcr_fbx.run({"op": "snapshot", "armature": "RunnerRig", "meshes": ["Runner", "Mallet"],
                          "path": "/abs/path/before.json"})
    bcr_fbx.run({"op": "export", "objects": ["RunnerRig", "Runner", "Mallet"],
                 "path": "/abs/path/runner.fbx",
                 "options": {"apply_scale_options": "FBX_SCALE_ALL", "apply_unit_scale": True}})
    after = bcr_fbx.run({"op": "reimport", "fbx": "/abs/path/runner.fbx", "scene": "FbxCheck",
                         "path": "/abs/path/after.json"})
    bcr_fbx.run({"op": "discard", "created": after["created"]})

`export` selects the named objects, exports the selection and restores the
selection. Its defaults are in EXPORT below; `options` overrides any of them.
Read the exporter's parameters on your Blender before relying on one.

  - Leaf bones are off: they add an `_end` bone per chain tip.
  - Deform-only is off: it would drop a non-deform root.
  - All-actions is off: the file carries the one action assigned to the rig,
    with its frame numbers, as a take named after the scene. Switched on, it
    writes every action in the .blend onto this armature — one made for
    another object included — each named `<rig>|<action>` and starting at 0.

`reimport` creates the scene, shows it in the window while it imports and puts
the window's scene back. It imports with `anim_offset` 0, so frame numbers come
back as they went out. The same .blend still holds the originals, so what it
imports is named `Runner.001`; `rig_gate.py` ignores that suffix. `discard`
removes exactly the datablocks a `reimport` reported as created.

A snapshot holds, per bone: parent, deform flag and head position in metres
relative to the armature; per mesh: vertex count, vertex groups in use, the
largest number of influences on a vertex, unweighted vertices, world scale; the
armature's world scale; the action's name, frame range and f-curve count.
"""
from __future__ import annotations

import json

import bpy

import bcr_common as C
import bcr_pose

EXPORT = {
    "use_selection": True,
    "object_types": {'ARMATURE', 'MESH'},
    "add_leaf_bones": False,
    "use_armature_deform_only": False,
    "bake_anim": True,
    "bake_anim_use_all_bones": True,
    "bake_anim_use_nla_strips": False,
    "bake_anim_use_all_actions": False,
    "bake_anim_force_startend_keying": True,
    "bake_anim_simplify_factor": 0.0,
    "mesh_smooth_type": 'FACE',
    "path_mode": 'COPY',
    "embed_textures": True,
}


def snapshot(rig, meshes) -> dict:
    origin = rig.matrix_world.translation
    bones = {}
    for bone in rig.data.bones:
        bones[bone.name] = {
            "parent": bone.parent.name if bone.parent else None,
            "deform": bone.use_deform,
            "head": (rig.matrix_world @ bone.head_local) - origin,
        }
    out_meshes = {}
    for obj in meshes:
        names = {g.index: g.name for g in obj.vertex_groups}
        used, most, unweighted = set(), 0, 0
        for v in obj.data.vertices:
            entries = [names[g.group] for g in v.groups if g.weight > 0]
            used.update(entries)
            most = max(most, len(entries))
            unweighted += 0 if entries else 1
        out_meshes[obj.name] = {
            "vertices": len(obj.data.vertices), "faces": len(obj.data.polygons),
            "groups": sorted(used), "max_influences": most, "unweighted": unweighted,
            "scale": obj.matrix_world.to_scale(), "parent_bone": obj.parent_bone if obj.parent_type == 'BONE' else None,
        }
    action = None
    if rig.animation_data and rig.animation_data.action:
        info = bcr_pose._action_report(rig)
        info.pop("curves")
        action = info
    return C.safe({"armature": rig.name, "armature_scale": rig.matrix_world.to_scale(),
                   "bones": bones, "meshes": out_meshes, "action": action})


def _write(path, data) -> None:
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    op = params["op"]

    if op == "snapshot":
        rig = bpy.data.objects[params["armature"]]
        data = snapshot(rig, [bpy.data.objects[n] for n in params.get("meshes", [])])
        _write(params.get("path"), data)
        return C.report(params, [], snapshot=data)

    if op == "export":
        view_layer = bpy.context.view_layer
        objects = [bpy.data.objects[n] for n in params["objects"]]
        outside = [o.name for o in objects if o.name not in view_layer.objects]
        if outside:
            raise ValueError(f"not in the active view layer, cannot be selected: {outside}")
        selected = [o for o in view_layer.objects if o.select_get()]
        active = view_layer.objects.active
        options = dict(EXPORT)
        options.update(params.get("options") or {})
        if isinstance(options.get("object_types"), list):
            options["object_types"] = set(options["object_types"])
        try:
            for o in selected:
                o.select_set(False)
            for o in objects:
                o.select_set(True)
            view_layer.objects.active = next((o for o in objects if o.type == 'ARMATURE'), objects[0])
            status = bpy.ops.export_scene.fbx(filepath=params["path"], **options)
        finally:
            for o in objects:
                o.select_set(False)
            for o in selected:
                o.select_set(True)
            view_layer.objects.active = active
        import os
        size = os.path.getsize(params["path"]) if os.path.exists(params["path"]) else 0
        gates = [C.gate("finished", sorted(status), ["FINISHED"], 'FINISHED' in status),
                 C.gate("file_bytes", size, "> 0", size > 0)]
        shown = {k: (sorted(v) if isinstance(v, set) else v) for k, v in options.items()}
        return C.report(params, gates, path=params["path"], bytes=size, options=shown)

    if op == "reimport":
        window = bpy.context.window
        previous = window.scene
        scene = bpy.data.scenes.new(params.get("scene", "FbxCheck"))
        try:
            window.scene = scene
            options = {"anim_offset": 0.0}           # the importer's default shifts every key by one frame
            options.update(params.get("options") or {})
            bpy.ops.import_scene.fbx(filepath=params["fbx"], **options)
            new = tracker.new("objects")
            rigs = [o for o in new if o.type == 'ARMATURE']
            if len(rigs) != 1:
                raise ValueError(f"expected one armature in the file, found {len(rigs)}")
            bpy.context.view_layer.update()
            data = snapshot(rigs[0], [o for o in new if o.type == 'MESH'])
        finally:
            window.scene = previous
        _write(params.get("path"), data)
        gates = [C.gate("one_armature", len(rigs), 1, len(rigs) == 1)]
        return C.report(params, gates, snapshot=data, scene=scene.name)

    if op == "discard":
        removed = {}
        for kind in C._KINDS:
            for name in (params.get("created") or {}).get(kind, []):
                block = getattr(bpy.data, kind).get(name)
                if block is not None:
                    getattr(bpy.data, kind).remove(block)
                    removed.setdefault(kind, []).append(name)
        return C.report(params, [], removed=removed)

    raise ValueError(f"unknown op {op!r}")
