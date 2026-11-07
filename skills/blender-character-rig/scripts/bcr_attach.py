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

`"mount": "forearm"` straps a flat prop with no handle (a shield) to the outer
side of a forearm bone instead; `mesh` is the character, read for the skin:

    result = bcr_attach.run({
        "prop": "Buckler", "armature": "CourierRig", "bone": "Forearm.L",
        "mount": "forearm", "mesh": "Courier",
        "at": 0.5,                # where along the bone, head 0 to tail 1
        "clearance": 0.005,       # metres between the prop's back and the skin
        "up": "Z",                # the prop's own axis laid along the bone, toward the tail
        "roll": 0,                # degrees about the prop's normal
        "front": "auto",          # or the prop's own axis that is its front, e.g. "-Y"
        "size": None,             # metres across the largest extent; omit to keep the size
        "outward": None,          # armature-space direction; default away from x = 0
    })

The prop is read from points spread evenly over its surface (so a dense boss
outweighs nothing): its normal is the thinnest principal axis, its front the
side its centre bulges toward, its back centre the middle of its backmost
slice. The back centre goes on the outward ray from the bone point, past the
outermost skin under the prop's footprint by `clearance`, the skin read with
the rig at rest. Every refusal comes before the prop is changed. Gates: flat_ratio,
world drift, normal_off_outward_deg, front_away_from_midline,
back_centre_offset, skin_clearance_min >= 0, skin_overlap_pairs == 0.
"""
from __future__ import annotations

import json
import math

import bpy
from mathutils import Matrix, Vector

import bcr_common as C

_AXES = {"X": 0, "Y": 1, "Z": 2}
_MOUNTS = ("hand", "forearm")


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    prop = bpy.data.objects[params["prop"]]
    rig = bpy.data.objects[params["armature"]]
    bone = rig.pose.bones[params["bone"]]
    mount = params.get("mount", "hand")
    if mount not in _MOUNTS:
        raise ValueError(f"mount {mount!r}: one of {_MOUNTS}")
    if "bcr_attach" in prop and json.loads(prop["bcr_attach"]).get("mount", "hand") != mount:
        raise ValueError(f"{prop.name} is attached with another mount: put it back first")
    if mount == "forearm":
        return _forearm(params, prop, rig, bone)
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


# ---- the forearm mount: a flat prop on the outer side of a forearm --------------------------

def _axis(name: str) -> Vector:
    """"Z", "-Y" ... -> a unit vector in the prop's own axes."""
    v = Vector((0.0, 0.0, 0.0))
    v[_AXES[name.lstrip("+-")]] = -1.0 if name.startswith("-") else 1.0
    return v


def _surface(co, tris, count: int, seed: int = 0):
    """`count` points spread evenly over the triangles' area: (triangle vertex ids, barycentrics)."""
    import numpy as np
    a, b, c = co[tris[:, 0]], co[tris[:, 1]], co[tris[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    if area.sum() <= 0:
        raise ValueError("the mesh has no area")
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(tris), count, p=area / area.sum())
    uv = rng.random((count, 2))
    over = uv.sum(axis=1) > 1
    uv[over] = 1 - uv[over]
    return tris[pick], uv


def _points(co, picked, uv):
    a = co[picked[:, 0]]
    return a + (co[picked[:, 1]] - a) * uv[:, :1] + (co[picked[:, 2]] - a) * uv[:, 1:]


def _arrays(mesh, matrix=None):
    """(vertex coordinates, triangles) as numpy arrays; `matrix` maps the coordinates."""
    import numpy as np
    co = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    if matrix is not None:
        m = np.array(matrix)
        co = co @ m[:3, :3].T + m[:3, 3]
    mesh.calc_loop_triangles()
    tris = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get("vertices", tris)
    return co, tris.reshape(-1, 3)


def flat_frame(points, hint=None) -> dict:
    """A flat prop's frame from surface points: thinnest principal axis, front by its bulge.

    The front is the side the centre (in-plane radius <= 0.25 of the outline) stands out
    toward against the rim (>= 0.75): a dome, a boss. `hint`, a direction, overrides it.
    The back centre is the in-plane middle of the backmost 15 % of the thickness, at the
    backmost depth, so a hollow back puts its rim, not its hollow, on the skin.
    """
    import numpy as np
    mu = points.mean(axis=0)
    q = points - mu
    w, vec = np.linalg.eigh(np.cov(q.T))
    n, a2, a1 = vec[:, 0], vec[:, 1], vec[:, 2]
    x, y, t = q @ a1, q @ a2, q @ n
    rr = np.sqrt((x / max(np.abs(x).max(), 1e-12)) ** 2 + (y / max(np.abs(y).max(), 1e-12)) ** 2)
    inner, rim = t[rr <= 0.25], t[rr >= 0.75]
    bulge = float(inner.mean() - rim.mean()) if len(inner) and len(rim) else 0.0
    sign = (1.0 if float(np.dot(n, hint)) >= 0 else -1.0) if hint is not None else (1.0 if bulge >= 0 else -1.0)
    n, t, bulge = n * sign, t * sign, bulge * sign
    thickness = float(t.max() - t.min())
    back = t <= t.min() + 0.15 * thickness
    centre = mu + a1 * x[back].mean() + a2 * y[back].mean() + n * t.min()
    return {"normal": n, "back_centre": centre, "bulge": bulge, "thickness": thickness,
            "flat_ratio": float(math.sqrt(max(w[0], 0.0) / max(w[1], 1e-18))),
            "extent": float(max(np.ptp(x), np.ptp(y)))}


def _forearm_gates(m: dict, lim: dict) -> list:
    gates = [
        C.gate("flat_ratio", m["flat_ratio"], f"<= {lim['flat']}", m["flat_ratio"] <= lim["flat"]),
        C.gate("world_drift_after_parenting", m["drift"], "< 1e-4", m["drift"] < 1e-4),
        C.gate("normal_off_outward_deg", m["normal_off_outward_deg"], f"<= {lim['normal']}",
               m["normal_off_outward_deg"] <= lim["normal"]),
        C.gate("back_centre_offset", m["back_centre_offset"], "< 1e-4", m["back_centre_offset"] < 1e-4),
        C.gate("skin_clearance_min", m["skin_clearance_min"], ">= 0", m["skin_clearance_min"] >= 0),
        C.gate("skin_overlap_pairs", m["skin_overlap_pairs"], "== 0", m["skin_overlap_pairs"] == 0),
    ]
    if m.get("front_lateral_dot") is not None:
        gates.insert(3, C.gate("front_away_from_midline", m["front_lateral_dot"], "> 0", m["front_lateral_dot"] > 0))
    return gates


def _skin(body, rig):
    """The character at the rest pose, in world space: (vertices, triangles, BVH).

    The bone points are read from rest, so the rig is put at its rest position for the read
    and back to what it was after."""
    from mathutils.bvhtree import BVHTree
    was = rig.data.pose_position
    rig.data.pose_position = 'REST'
    try:
        bpy.context.view_layer.update()
        ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = ev.to_mesh()
        try:
            co, tris = _arrays(mesh, ev.matrix_world)
        finally:
            ev.to_mesh_clear()
    finally:
        rig.data.pose_position = was
        bpy.context.view_layer.update()
    return co, tris, BVHTree.FromPolygons([Vector(v) for v in co], tris.tolist())


def _clearance(points, co, tris, skin) -> tuple:
    """(the least signed distance from the prop's points to the skin, triangle pairs that cross)."""
    from mathutils.bvhtree import BVHTree
    least = float("inf")
    for p in points:
        p = Vector(p)
        hit = skin.find_nearest(p)
        if hit[0] is None:
            continue
        away = p - hit[0]
        d = away.length
        side = away.dot(hit[1])
        if abs(side) < 0.9 * d:      # nearest on an edge or a corner: sign by every face that meets there
            side = away.dot(sum((h[1] for h in skin.find_nearest_range(p, d * 1.001 + 1e-7)), Vector()))
        least = min(least, d if side >= 0 else -d)
    prop_tree = BVHTree.FromPolygons([Vector(v) for v in co], tris.tolist())
    return least, len(skin.overlap(prop_tree))


def _forearm(params: dict, prop, rig, bone) -> dict:
    import numpy as np
    body = bpy.data.objects[params["mesh"]]
    lim = {"flat": params.get("max_flat_ratio", 0.5), "normal": params.get("max_normal_deg", 1.0)}
    if prop.parent is rig and prop.parent_bone == bone.name and "bcr_attach" in prop:
        kept = json.loads(prop["bcr_attach"])            # already mounted: measure nothing twice
        return C.report(params, _forearm_gates(kept["measured"], lim), reused=True, **kept)

    # read in world space without touching the prop: every refusal below comes before the first change
    mesh = prop.data
    placed_from = prop.matrix_world.copy()
    co, tris = _arrays(mesh, placed_from)
    picked, uv = _surface(co, tris, params.get("samples", 20000))
    front = params.get("front", "auto")
    hint = None if front in (None, "auto") else np.array(_axis(front))
    frame = flat_frame(_points(co, picked, uv), hint)
    warnings = []
    if abs(frame["bulge"]) < 0.05 * frame["thickness"] and hint is None:
        warnings.append("the front side is ambiguous (the prop barely bulges): pass `front`")
    f = Vector(frame["normal"].tolist())
    up = _axis(params.get("up", "Z"))
    u = up - f * up.dot(f)
    if u.length < 0.3:
        raise ValueError(f"up {params.get('up', 'Z')} lies along the prop's normal: pass another `up`")
    u.normalize()
    r = u.cross(f)

    scale = params["size"] / frame["extent"] if params.get("size") else 1.0
    to_back = Matrix.Scale(scale, 4) @ Matrix.Translation(-Vector(frame["back_centre"].tolist()))
    local = _points((co - frame["back_centre"]) * scale, picked, uv)   # the mesh as to_back will leave it

    mw = rig.matrix_world
    head, tail = mw @ bone.bone.head_local, mw @ bone.bone.tail_local
    d = (tail - head).normalized()
    at = params.get("at", 0.5)
    point = head.lerp(tail, at)
    side = (bone.bone.head_local + bone.bone.tail_local).x / 2
    lateral = (mw.to_3x3() @ Vector((math.copysign(1.0, side), 0.0, 0.0))).normalized() if abs(side) > 1e-4 else None
    if params.get("outward") is not None:
        out = (mw.to_3x3() @ Vector(params["outward"])).normalized()
    elif lateral is not None:
        out = lateral
    else:
        raise ValueError(f"{bone.name} lies on the midline: pass `outward`")
    F = out - d * out.dot(d)
    if F.length < 0.3:
        raise ValueError(f"{bone.name} runs along the outward direction: pass `outward` across the bone")
    F.normalize()
    U = Matrix.Rotation(math.radians(params.get("roll", 0.0)), 3, F) @ d
    R = U.cross(F)
    turn = Matrix((R, U, F)).transposed() @ Matrix((r, u, f))

    # the outermost skin under the prop's footprint, measured from the bone line
    skin_co, skin_tris, skin = _skin(body, rig)
    picked_skin, uv_skin = _surface(skin_co, skin_tris, params.get("skin_samples", 40000), seed=1)
    near = np.vstack([skin_co, _points(skin_co, picked_skin, uv_skin)]) - np.array(point)
    clearance = params.get("clearance", 0.005)
    margin = max(clearance, 0.0)
    pr, pu = local @ np.array(r), local @ np.array(u)
    a, b, h = near @ np.array(U), near @ np.array(R), near @ np.array(F)
    under = ((a >= pu.min() - margin) & (a <= pu.max() + margin) & (b >= pr.min() - margin) & (b <= pr.max() + margin))
    if not under.any() or h[under].max() <= 0:
        raise ValueError(f"no skin of {body.name} outward of {bone.name}: wrong mesh or bone")
    skin_radius = float(h[under].max())
    target = point + F * (skin_radius + clearance)
    wanted = Matrix.Translation(target) @ turn.to_4x4()

    # nothing left to refuse: bake the world placement and the back centre into the mesh, then parent
    prop.parent = None
    mesh.transform(to_back @ placed_from)        # origin and axes the world's, the back centre at the origin
    prop.matrix_world = Matrix.Identity(4)
    co, _ = _arrays(mesh)
    local = _points(co, picked, uv)              # measured below from the mesh as it now is
    prop.parent = rig
    prop.parent_type = 'BONE'
    prop.parent_bone = bone.name
    bpy.context.view_layer.update()
    prop.matrix_world = wanted
    bpy.context.view_layer.update()
    drift = max(abs(prop.matrix_world[i][j] - wanted[i][j]) for i in range(4) for j in range(4))

    # measured again from the placed mesh, not from the matrix that placed it
    placed = np.array(prop.matrix_world)
    world = local @ placed[:3, :3].T + placed[:3, 3]
    again = flat_frame(world, None if hint is None else np.array(prop.matrix_world.to_3x3() @ _axis(front)))
    n_w = Vector(again["normal"].tolist())
    prop_co, prop_tris = _arrays(mesh, prop.matrix_world)
    least, pairs = _clearance(np.vstack([prop_co, world]), prop_co, prop_tris, skin)
    measured = {
        "flat_ratio": frame["flat_ratio"], "drift": drift,
        "normal_off_outward_deg": math.degrees(n_w.angle(F, 0.0)),
        "front_lateral_dot": n_w.dot(lateral) if lateral is not None else None,
        "back_centre_offset": (Vector(again["back_centre"].tolist()) - target).length,
        "skin_clearance_min": least, "skin_overlap_pairs": pairs,
    }
    kept = C.safe({"prop": prop.name, "bone": bone.name, "mount": "forearm", "at": at,
                   "clearance": clearance, "skin_radius": skin_radius, "size": frame["extent"] * scale,
                   "thickness": frame["thickness"] * scale, "bulge": frame["bulge"] * scale,
                   "front_side": f, "outward": F, "requested_point": target, "measured": measured}, 6)
    prop["bcr_attach"] = json.dumps(kept)
    return C.report(params, _forearm_gates(measured, lim), reused=False, warnings=warnings,
                    world_position=prop.matrix_world.translation, **kept)
