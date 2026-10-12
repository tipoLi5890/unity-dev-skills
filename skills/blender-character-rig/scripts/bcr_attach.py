"""bcr_attach.py — put a prop in a hand: grip from its geometry, parent to the bone.

Runs inside Blender; not a command-line script (the stub is in bcr_common.py).

The grip is measured, not guessed. The handle's axis is the centroid of a thin
slice at the handle's free end — the one place nothing but handle exists. A
band further up that happens to include the head puts the axis beside the
handle; `handle_radius_ratio` shows it (a handle is a few percent of the prop's
length across, not a fifth).

    result = bcr_attach.run({
        "prop": "Mallet", "armature": "RunnerRig", "bone": "Hand.R",
        "axis": "Z",              # the prop's long axis, in its own space
        "end_slice": 0.10,        # the free end: lowest tenth along the axis
        "grip_at": 0.27,          # where the hand holds, as a fraction of the length
        "radius_band": [0.22, 0.28],   # a stretch that is certainly bare handle
        "length": 0.62,           # metres; omit to keep the prop's size
        "rotation": [["Z", -90], ["X", 15]],   # armature axes; turns the head to face front
        "position": None,         # armature-space point; default is the middle of the bone
        "max_radius_ratio": 0.15,
    })

The prop must have an identity transform with its long axis along `axis` (run
bcr_import_prep on it first, with `weld_distance: None`). This moves the
mesh's origin to the grip, scales it to `length`, places it and parents it with
parent_type BONE. Bone parenting attaches at the bone's tail, so the wanted
world matrix is assigned again after the parent is set and the view layer
updated.

Returns `head_side` — which way the head sticks out from the handle, in the
prop's own axes — so the caller knows which `rotation` faces it forward.
Gates: handle_radius_ratio <= max_radius_ratio, world drift after parenting.
"""
from __future__ import annotations

import json

import bpy
from mathutils import Matrix, Vector

import bcr_common as C

_AXES = {"X": 0, "Y": 1, "Z": 2}


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    prop = bpy.data.objects[params["prop"]]
    rig = bpy.data.objects[params["armature"]]
    bone = rig.pose.bones[params["bone"]]
    mesh = prop.data
    k = _AXES[params.get("axis", "Z")]
    a, b = [i for i in range(3) if i != k]

    limit = params.get("max_radius_ratio", 0.15)
    if prop.parent is rig and prop.parent_bone == bone.name and "bcr_attach" in prop:
        kept = json.loads(prop["bcr_attach"])            # already attached: measure nothing twice
        ratio = kept["handle_radius"] / kept["length"]
        return C.report(params, [C.gate("handle_radius_ratio", ratio, f"<= {limit}", 0 < ratio <= limit)],
                        reused=True, **kept)

    if prop.parent is not None:
        world = prop.matrix_world.copy()
        prop.parent = None
        prop.matrix_world = world
    mesh.transform(prop.matrix_world)            # origin and axes become the world's
    prop.matrix_world = Matrix.Identity(4)

    co = [v.co.copy() for v in mesh.vertices]
    low, high = min(c[k] for c in co), max(c[k] for c in co)
    length = high - low
    end = [c for c in co if c[k] <= low + length * params.get("end_slice", 0.10)]
    axis_a = sum(c[a] for c in end) / len(end)
    axis_b = sum(c[b] for c in end) / len(end)
    band_lo, band_hi = params.get("radius_band", [0.22, 0.28])
    band = [c for c in co if low + length * band_lo <= c[k] <= low + length * band_hi]
    radius = max(((c[a] - axis_a) ** 2 + (c[b] - axis_b) ** 2) ** 0.5 for c in band) if band else 0.0
    ratio = radius / length

    head = [c for c in co if c[k] >= low + length * 0.6]
    side = Vector((0.0, 0.0, 0.0))
    side[a] = max(c[a] for c in head) + min(c[a] for c in head) - 2 * axis_a
    side[b] = max(c[b] for c in head) + min(c[b] for c in head) - 2 * axis_b

    grip = Vector((0.0, 0.0, 0.0))
    grip[a], grip[b], grip[k] = axis_a, axis_b, low + length * params.get("grip_at", 0.27)
    mesh.transform(Matrix.Translation(-grip))
    scale = params["length"] / length if params.get("length") else 1.0
    mesh.transform(Matrix.Scale(scale, 4))

    if params.get("position") is not None:
        where = Vector(params["position"])
    else:
        where = (bone.bone.head_local + bone.bone.tail_local) / 2
    wanted = rig.matrix_world @ Matrix.Translation(where) @ C.rotation(params.get("rotation")).to_4x4()

    prop.parent = rig
    prop.parent_type = 'BONE'
    prop.parent_bone = bone.name
    bpy.context.view_layer.update()
    prop.matrix_world = wanted
    bpy.context.view_layer.update()
    drift = max(abs(prop.matrix_world[r][c] - wanted[r][c]) for r in range(4) for c in range(4))

    gates = [
        C.gate("handle_radius_ratio", ratio, f"<= {limit}", 0 < ratio <= limit),
        C.gate("world_drift_after_parenting", drift, "< 1e-4", drift < 1e-4),
    ]
    kept = C.safe({"prop": prop.name, "bone": bone.name, "length": length * scale, "handle_radius": radius * scale,
                   "head_side": side.normalized() if side.length else side})
    prop["bcr_attach"] = json.dumps(kept)
    return C.report(params, gates, reused=False, world_position=prop.matrix_world.translation, **kept)
