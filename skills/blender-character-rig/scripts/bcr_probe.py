"""bcr_probe.py — where a point on an object is at a frame, and which way it faces.

Runs inside Blender; not a command-line script (the stub is in bcr_common.py).
Reads only; the current frame is restored.

A swing is judged by numbers before it is judged by a render: at the frame of
contact, is the striking edge where the target is, and is it travelling into
the target rather than into the floor? A render shows that a pose is wrong; this
shows by how much and in which direction, and it costs one call.

    result = bcr_probe.run({
        "object": "Mallet",
        "frames": [1, 15, 17, 18, 20],
        "extreme": {"axis": "X", "sign": 1, "band": 0.02},   # the far edge along local +X
        # or "point": [x, y, z] in the object's own space
        "direction": [1, 0, 0],          # a local direction to follow, e.g. where the face points
        "target": [0.12, -0.5, 0.35],    # world point; reports the distance to it
        "gate_frame": 18, "within": 0.05, "direction_z_min": -0.8,
    })

Per frame: world `position`, world `direction`, `distance` to the target.
With `gate_frame`: `within` gates the distance at that frame, and
`direction_z_min` fails a direction that points more steeply down than that.
"""
from __future__ import annotations

import bpy
from mathutils import Vector

import bcr_common as C

_AXES = {"X": 0, "Y": 1, "Z": 2}


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    scene = C.scene_of(params)
    obj = bpy.data.objects[params["object"]]
    if params.get("point") is not None:
        point = Vector(params["point"])
    elif params.get("extreme") and obj.type == 'MESH':
        spec = params["extreme"]
        k, sign = _AXES[spec.get("axis", "X")], spec.get("sign", 1)
        values = [v.co[k] * sign for v in obj.data.vertices]
        edge = [v.co for v in obj.data.vertices if v.co[k] * sign >= max(values) - spec.get("band", 0.02)]
        point = sum(edge, Vector()) / len(edge)
    else:
        point = Vector((0, 0, 0))
    direction = Vector(params.get("direction", (1, 0, 0)))
    target = Vector(params["target"]) if params.get("target") is not None else None

    current = scene.frame_current
    samples = {}
    try:
        for frame in params.get("frames", [current]):
            scene.frame_set(int(frame))
            world = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world
            position = world @ point
            facing = (world.to_3x3() @ direction).normalized()
            samples[int(frame)] = {
                "position": position.copy(), "direction": facing,
                "distance": (position - target).length if target is not None else None,
            }
    finally:
        scene.frame_set(current)

    gates = []
    frame = params.get("gate_frame")
    if frame is not None:
        at = samples[int(frame)]
        if params.get("within") is not None and target is not None:
            gates.append(C.gate("distance_to_target", at["distance"], f"<= {params['within']}",
                                at["distance"] <= params["within"]))
        if params.get("direction_z_min") is not None:
            gates.append(C.gate("direction_z", at["direction"].z, f">= {params['direction_z_min']}",
                                at["direction"].z >= params["direction_z_min"]))
    return C.report(params, gates, object=obj.name, local_point=point, frames=samples)
