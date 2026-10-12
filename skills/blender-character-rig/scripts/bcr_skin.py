"""bcr_skin.py — skin weights computed from position, for a mesh bone heat cannot solve.

Runs inside Blender; not a command-line script (the stub is in bcr_common.py).

Automatic weights fail on a generated mesh: it is a double shell whose inner
vertices are hidden from every bone, in several disconnected islands. The rule
here needs no solve and gives the inner twin of a vertex the same weights as
the skin over it, because it only looks at where a vertex is:

  1. distance from the vertex to each deform bone's segment, divided by that
     bone's radius — the nearest bone by that measure owns the vertex;
  2. it shares the vertex only with its own parent and children,
     weight = exp(-(d - d_nearest) / tau), so an arm reaches the torso through
     the shoulder and never through the ribs;
  3. a chain named in `gradients` (ears, a tail, a scarf end) is weighted along
     its length instead, so a long thin part bends as a curve;
  4. the weights are averaged over mesh edges a few times, cut to the largest
     `max_influences` per vertex and renormalised.

    result = bcr_skin.run({
        "mesh": "Runner", "armature": "RunnerRig",
        "tau": 0.2, "smooth_passes": 4, "max_influences": 4,
        "gradients": [
            {"bones": ["Ear.L", "EarTip.L"], "parent": "Head", "fade_in": 0.22, "blend": 0.22},
            {"bones": ["Ear.R", "EarTip.R"], "parent": "Head"},
        ],
    })

Radii and segments come from the `bcr_bones` property bcr_armature left on the
rig. `fade_in` is the fraction of a chain's length over which its parent lets
go; `blend` is half the width of the hand-over between two bones of a chain.

It replaces every vertex group on the mesh, adds one Armature modifier and
parents the mesh to the rig. It refuses a mesh whose object scale is not 1.

Gates: unweighted vertices == 0, max influences <= max_influences, weight sums
within 1e-4 of 1, no deform bone left without vertices.
"""
from __future__ import annotations

import json
import math

import bpy
from mathutils import Vector

import bcr_common as C


def _project(p: Vector, a: Vector, b: Vector) -> tuple[float, float]:
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return t, (p - (a + ab * t)).length


def _smoothstep(e0: float, e1: float, x: float) -> float:
    if e1 <= e0:
        return 1.0 if x >= e1 else 0.0
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def _chain_weights(p: Vector, chain: dict, bones: dict) -> dict[str, float]:
    names = chain["bones"]
    lengths = [bones[n].length for n in names]
    total = sum(lengths)
    best, along, done = None, 0.0, 0.0
    for name, length in zip(names, lengths):
        t, d = _project(p, bones[name].head_local, bones[name].tail_local)
        if best is None or d < best:
            best, along = d, (done + t * length) / total
        done += length
    half = chain.get("blend", 0.22)
    joints = [sum(lengths[:k]) / total for k in range(1, len(names))]
    reach = [1.0] + [_smoothstep(j - half, j + half, along) for j in joints] + [0.0]
    weights = {name: max(0.0, reach[k] - reach[k + 1]) for k, name in enumerate(names)}
    parent = chain.get("parent")
    if parent:
        keep = 1.0 - _smoothstep(0.0, chain.get("fade_in", 0.22), along)
        weights = {name: w * (1.0 - keep) for name, w in weights.items()}
        weights[parent] = keep
    return weights


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    obj = bpy.data.objects[params["mesh"]]
    rig = bpy.data.objects[params["armature"]]
    mesh = obj.data
    if any(abs(s - 1) > 1e-6 for s in obj.scale):
        raise ValueError(f"{obj.name} has object scale {tuple(obj.scale)}: apply it into the mesh before skinning")
    spec = {b["name"]: b for b in json.loads(rig.get("bcr_bones", "[]"))}
    bones = {b.name: b for b in rig.data.bones if b.use_deform}
    missing = [n for n in bones if not spec.get(n, {}).get("radius")]
    if missing:
        raise ValueError(f"no radius in the bone spec for: {missing}")

    # the mesh and the rig share one local space (bcr_armature copied the transform)
    to_rig = rig.matrix_world.inverted() @ obj.matrix_world
    co = [to_rig @ v.co for v in mesh.vertices]

    segments = {}
    for name, bone in bones.items():
        seg = spec[name].get("segment")
        a, b = (Vector(seg[0]), Vector(seg[1])) if seg else (bone.head_local.copy(), bone.tail_local.copy())
        segments[name] = (a, b, spec[name]["radius"])
    neighbours = {name: set() for name in bones}
    for name, bone in bones.items():
        if bone.parent and bone.parent.name in bones:
            neighbours[name].add(bone.parent.name)
            neighbours[bone.parent.name].add(name)
    chains = params.get("gradients") or []
    chain_of = {name: chain for chain in chains for name in chain["bones"]}

    tau = params.get("tau", 0.2)
    weights: list[dict[str, float]] = []
    for p in co:
        nd = {name: _project(p, a, b)[1] / radius for name, (a, b, radius) in segments.items()}
        nearest = min(nd, key=nd.get)
        if nearest in chain_of:
            w = _chain_weights(p, chain_of[nearest], bones)
        else:
            w = {name: math.exp(-(nd[name] - nd[nearest]) / tau) for name in {nearest} | neighbours[nearest]}
        total = sum(w.values())
        weights.append({name: x / total for name, x in w.items() if x / total > 0.01})

    adjacent: list[list[int]] = [[] for _ in co]
    for edge in mesh.edges:
        a, b = edge.vertices
        adjacent[a].append(b)
        adjacent[b].append(a)
    for _ in range(params.get("smooth_passes", 4)):
        smoothed = []
        for i, own in enumerate(weights):
            acc = dict(own)
            for j in adjacent[i]:
                for name, x in weights[j].items():
                    acc[name] = acc.get(name, 0.0) + x
            k = 1 + len(adjacent[i])
            smoothed.append({name: x / k for name, x in acc.items()})
        weights = smoothed

    for group in list(obj.vertex_groups):
        obj.vertex_groups.remove(group)
    groups = {name: obj.vertex_groups.new(name=name) for name in bones}
    limit = params.get("max_influences", 4)
    for i, own in enumerate(weights):
        top = [(n, x) for n, x in sorted(own.items(), key=lambda kv: -kv[1])[:limit] if x > 0.01]
        total = sum(x for _, x in top)
        for name, x in top:
            groups[name].add([i], x / total, 'REPLACE')
    mesh.update()

    modifier = next((m for m in obj.modifiers if m.type == 'ARMATURE'), None) or obj.modifiers.new("Armature", 'ARMATURE')
    modifier.object = rig
    world = obj.matrix_world.copy()
    obj.parent = rig
    obj.matrix_world = world

    index_name = {g.index: g.name for g in obj.vertex_groups}
    counts = {name: 0 for name in bones}
    unweighted, most, worst, used = 0, 0, 0.0, set()
    for v in mesh.vertices:
        entries = [(index_name[g.group], g.weight) for g in v.groups if g.weight > 0]
        if not entries:
            unweighted += 1
            continue
        used.update(name for name, _ in entries)
        most = max(most, len(entries))
        worst = max(worst, abs(sum(w for _, w in entries) - 1.0))
        counts[max(entries, key=lambda e: e[1])[0]] += 1
    empty = [name for name in bones if name not in used]
    gates = [
        C.gate("unweighted_vertices", unweighted, 0, unweighted == 0),
        C.gate("max_influences", most, limit, most <= limit),
        C.gate("weight_sum_error", worst, "< 1e-4", worst < 1e-4),
        C.gate("deform_bones_without_vertices", empty, [], not empty),
    ]
    return C.report(params, gates, mesh=obj.name, armature=rig.name, vertices=len(mesh.vertices),
                    dominant_vertices=counts)
