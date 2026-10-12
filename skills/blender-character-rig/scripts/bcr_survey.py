"""bcr_survey.py — read where the joints are from the mesh itself.

Runs inside Blender; not a command-line script (the stub is in bcr_common.py).
Reads only; changes nothing.

Bones placed by eye on a generated mesh land beside the limb. This slices the
mesh and reports numbers to place them from: where the body narrows (neck,
waist), where a slice splits in two (legs, ears), how far the arms reach.

    result = bcr_survey.run({
        "mesh": "Runner",
        "z_slices": 20,                  # horizontal slabs, feet to top
        "x_slices": 14,                  # vertical slabs across the width
        "x_band": [0.0, 0.5],            # height range the x slabs look at, as fractions
        "boxes": {                       # centroid of the vertices inside a box, mesh-local
            "hand_l": [[0.30, None], [None, None], [None, 0.60]],
            "ear_tip_l": [[0.0, None], [None, None], [1.13, None]],
        },
    })

Coordinates are mesh-local: after bcr_import_prep the origin is between the
feet, +Z is up and a character that faces -Y has its left side on +X.

Each z slice: `z`, `x` and `y` ranges, `count`, and `parts` — how many separate
runs of vertices the slice has along X (2 at the legs and the ears, 3 where the
arms hang beside the body). Each box: `centroid`, `count`, `min`, `max`.
"""
from __future__ import annotations

import bpy
from mathutils import Vector

import bcr_common as C


def _parts(xs: list[float], gap: float) -> int:
    xs = sorted(xs)
    return 1 + sum(1 for a, b in zip(xs, xs[1:]) if b - a > gap)


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    obj = bpy.data.objects[params["mesh"]]
    co = [v.co.copy() for v in obj.data.vertices]
    low = Vector((min(c.x for c in co), min(c.y for c in co), min(c.z for c in co)))
    high = Vector((max(c.x for c in co), max(c.y for c in co), max(c.z for c in co)))
    size = high - low
    gap = size.x * params.get("gap", 0.04)

    n = params.get("z_slices", 20)
    z_slices = []
    for i in range(n):
        z0, z1 = low.z + size.z * i / n, low.z + size.z * (i + 1) / n
        pts = [c for c in co if z0 <= c.z < z1 or (i == n - 1 and c.z == z1)]
        if not pts:
            continue
        z_slices.append({
            "z": [z0, z1], "x": [min(c.x for c in pts), max(c.x for c in pts)],
            "y": [min(c.y for c in pts), max(c.y for c in pts)],
            "count": len(pts), "parts": _parts([c.x for c in pts], gap),
        })

    n = params.get("x_slices", 14)
    band = params.get("x_band", [0.0, 1.0])
    zlo, zhi = low.z + size.z * band[0], low.z + size.z * band[1]
    x_slices = []
    for i in range(n):
        x0, x1 = low.x + size.x * i / n, low.x + size.x * (i + 1) / n
        pts = [c for c in co if x0 <= c.x < x1 and zlo <= c.z <= zhi]
        if not pts:
            continue
        x_slices.append({
            "x": [x0, x1], "z": [min(c.z for c in pts), max(c.z for c in pts)],
            "y": [min(c.y for c in pts), max(c.y for c in pts)], "count": len(pts),
        })

    boxes = {}
    for name, box in (params.get("boxes") or {}).items():
        def inside(c):
            return all((lo is None or c[k] >= lo) and (hi is None or c[k] <= hi) for k, (lo, hi) in enumerate(box))
        pts = [c for c in co if inside(c)]
        if pts:
            boxes[name] = {
                "centroid": sum(pts, Vector()) / len(pts), "count": len(pts),
                "min": [min(c[k] for c in pts) for k in range(3)], "max": [max(c[k] for c in pts) for k in range(3)],
            }
        else:
            boxes[name] = {"centroid": None, "count": 0}

    empty = [name for name, box in boxes.items() if not box["count"]]
    gates = [
        C.gate("has_vertices", len(co), "> 0", len(co) > 0),
        C.gate("empty_boxes", empty, [], not empty),
    ]
    return C.report(params, gates, mesh=obj.name, min=low, max=high, size=size,
                    z_slices=z_slices, x_slices=x_slices, boxes=boxes)
