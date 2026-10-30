#!/usr/bin/env python3
"""deform_gate.py — six test poses on the contract skeleton: does the skin hold its volume and stay out of itself?

A bind that leaves no vertex without a weight can still fold an elbow flat, sink the belly into the
thighs in a squat or turn the waist into a candy wrapper. This poses the rig through six extremes,
reads the skinned mesh back, and measures two things against the rest pose.

usage (Blender, headless):
    blender -b scene.blend -P deform_gate.py -- --armature RunnerRig --mesh Runner [options]
    blender -b -P deform_gate.py -- --fbx runner_arp.fbx --map arp_map_report.json [options]
    blender -b --factory-startup -P deform_gate.py -- --selftest
options: [--map REPORT_OR_ROLE_MAP.json] [--poses all|arms_up,deep_squat,...] [--steps 2]
         [--volume-max 0.35] [--intersect-p95 0.08] [--out REPORT.json] [--render DIR]

Bones are named by the humanoid contract (`unity-rigged-character` -> humanoid-contract.md).
`--map` reads either a contract_map.py report (its `retarget_map`, contract bone -> rig bone) or a
role map {"bones": {contract bone: rig bone | [candidates]}}; without it the rig's bones carry the
contract names. Pose a plain skeleton: an exported FBX (`--fbx`), or a rig whose deform bones are
not driven by constraints. A control rig (Auto-Rig Pro's own) ignores rotations set on its deform
bones; gate its export instead.

The poses, each a rotation in world axes (+Z up, facing -Y) applied relative to the parent, read off
the rest skeleton so they fit any arm angle and any hand orientation:
  arms_up      both upper arms swung up to 20 degrees from vertical, the shoulders 15 degrees after them
  deep_squat   thighs 100 degrees forward, knees 120 degrees, spine and chest 10 degrees forward each
  torso_twist  spine, chest and upper chest 20 degrees each about their own axis (60 in all)
  fist         every finger phalanx 60 degrees toward the palm, the thumb 30 (skipped without fingers);
               the palm is the side away from the back of the hand, (Index1 - Hand) x (Little1 - Hand)
               on the left, mirrored on the right
  leg_raise    the left thigh 90 degrees forward, knee straight
  elbow_120    both forearms 120 degrees toward the front
Each pose is sampled at --steps evenly spaced fractions ending at the full pose (default 2: half, full).

Measures, on the outward-facing skin only. An inward-facing inner shell, back to back with the
skin (some image-to-3D generators always write one; mesh_check reports it as inner_shell), would
cancel the skin's cones and cross the skin as it folds, so it is left out of both measures: a
triangle with a sheet facing the other way right behind it (within 0.01 x the height) from which no
ray (its normal and six directions 70 degrees around it) leaves the mesh lines a closed cavity.
The skin sees out, folds included, and a single skin has no sheet behind it, so both keep every
triangle. The report gives outward_triangles and inward_triangles.
  volume loss  per rotated body joint (fingers excluded): the skin triangles within half the shorter
               adjoining bone of the joint at rest, and the volume they wrap, as the sum of the cones
               from their vertex centroid, (a - c) . ((b - c) x (d - c)) / 6. loss = 1 - posed / rest.
               A flattened elbow or a candy-wrapper waist loses it; a rigid turn keeps it. A joint
               whose patch does not wrap around it (signed volume under half the unsigned one at
               rest: a clavicle under a flat chest), or whose patch holds fewer than 8 triangles (the
               spine joints of a torso wider than half a spine bone), is listed in
               joints_not_measured: the volume gate did not run there, so read that pose's render.
               A gain (negative loss) is reported, not gated.
  new self-intersections   the outward triangles that intersect another outward triangle (sharing
               no vertex) in the pose and did not at rest, divided by the outward triangles that moved (any vertex more than
               0.1 % of the height). Counted with Blender's BVH overlap; a double shell or an
               accessory that already crosses the body at rest is not counted again.

Gates (each failing one makes exit 2):
  deform.volume_loss_max          the largest loss over every sample at the elbows, knees, wrists,
                                  ankles and spine joints <= --volume-max (0.35). Shoulders and hips
                                  are reported (ball_joint_loss_max), not gated: their patch mixes
                                  torso and limb, and an arm raised overhead reads as a loss there for
                                  any skin; look at their renders instead.
  deform.self_intersection_p95    p95 over every sample of the new-intersection ratio <= --intersect-p95 (0.08)
  deform.poses                    every requested pose was applied; with --poses all the fist may be
                                  skipped on a rig without finger bones, named in --poses it may not
  deform.joints_measured          every hinge joint a requested pose bends (LowerArm in elbow_120,
                                  LowerLeg in deep_squat) was measured by the volume gate in at
                                  least one pose; its value lists the ones never measured. A hinge
                                  the volume gate cannot read is a failure, not a silent pass.

Report: {tool, armature, mesh, height, triangles, outward_triangles, inward_triangles, poses: {name: {samples: [{t, new_intersections, moved,
ratio, volume_loss: {joint: loss}}], joints_not_measured, bent (the bones the pose turns), skipped?}}, volume_loss_max {value, pose,
joint}, ball_joint_loss_max,
self_intersection {p95, max, pose}, renders?, gates [{name, value, limit, ok}], ok}.

Prints one JSON object. Exit codes: 0 every gate passed (or --selftest passed); 2 a gate failed;
1 refused input (no such object, a body bone the map cannot find, an unreadable map or FBX) or a
failed --selftest. Requires Blender (bpy, mathutils) and numpy.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

POSES = ("arms_up", "deep_squat", "torso_twist", "fist", "leg_raise", "elbow_120")
BODY = ("Hips", "Spine", "Chest", "UpperArm.L", "UpperArm.R", "LowerArm.L", "LowerArm.R",
        "UpperLeg.L", "UpperLeg.R", "LowerLeg.L", "LowerLeg.R")
FINGERS = ("Thumb", "Index", "Middle", "Ring", "Little")
# the volume gate reads hinge and spine joints, where the patch is a tube around the joint; a ball
# joint's patch (shoulder, hip) mixes torso and limb, and a fold there reads as loss for any skin
GATED = ("LowerArm", "LowerLeg", "Spine", "Chest", "UpperChest", "Hand", "Foot")
# hinge joints the volume gate must reach whenever a requested pose bends them
HINGES = ("LowerArm", "LowerLeg")
FWD = np.array([0.0, -1.0, 0.0])
UP = np.array([0.0, 0.0, 1.0])


class Refused(Exception):
    pass


def _unit(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def _toward(d, target):
    """Axis that turns direction d toward `target` (right-hand rule, positive angle)."""
    return _unit(np.cross(d, target))


def read_map(path: str | None) -> dict:
    if not path:
        return {}
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data.get("retarget_map"), dict):
        return {k: [v] for k, v in data["retarget_map"].items()}
    bones = data.get("bones")
    if not isinstance(bones, dict):
        raise Refused(f"{path}: neither a contract_map report (retarget_map) nor a role map (bones)")
    return {k: (v if isinstance(v, list) else [v]) for k, v in bones.items()}


class Rig:
    """The armature with contract names resolved, rest geometry in world space."""

    def __init__(self, rig, mapping: dict):
        self.obj = rig
        names = {b.name for b in rig.data.bones}
        self.name = {}
        for contract in list(mapping) + [c for c in self._contract() if c not in mapping]:
            for cand in mapping.get(contract, [contract]):
                if cand in names:
                    self.name[contract] = cand
                    break
        mw = np.array(rig.matrix_world)
        self.mw = mw
        self.head, self.tail, self.rest = {}, {}, {}
        for contract, bone in self.name.items():
            b = rig.data.bones[bone]
            m = mw @ np.array(b.matrix_local)
            self.head[contract] = m[:3, 3]
            self.tail[contract] = (mw @ np.r_[np.array(b.tail_local), 1.0])[:3]
            r = m[:3, :3]
            self.rest[contract] = r / np.linalg.norm(r, axis=0)

    @staticmethod
    def _contract():
        out = ["Root", "Hips", "Spine", "Chest", "UpperChest", "Neck", "Head"]
        for s in ("L", "R"):
            out += [f"{n}.{s}" for n in ("Shoulder", "UpperArm", "LowerArm", "Hand", "UpperLeg",
                                          "LowerLeg", "Foot", "Toes")]
            out += [f"{f}{i}.{s}" for f in FINGERS for i in (1, 2, 3)]
        return out

    def d(self, c):
        return _unit(self.tail[c] - self.head[c])

    def length(self, c):
        return float(np.linalg.norm(self.tail[c] - self.head[c]))

    def has(self, *names):
        return all(n in self.name for n in names)


def pose_rotations(rig: Rig, pose: str) -> list[tuple[str, np.ndarray, float]]:
    """[(contract bone, world axis, degrees)] for one pose, read off the rest skeleton."""
    out = []
    if pose == "arms_up":
        for s in ("L", "R"):
            d = rig.d(f"UpperArm.{s}")
            angle = math.degrees(math.acos(np.clip(d @ UP, -1, 1))) - 20
            out.append((f"UpperArm.{s}", _toward(d, UP), angle))
            if rig.has(f"Shoulder.{s}"):
                out.append((f"Shoulder.{s}", _toward(rig.d(f"Shoulder.{s}"), UP), 15))
    elif pose == "deep_squat":
        for s in ("L", "R"):
            out.append((f"UpperLeg.{s}", _toward(rig.d(f"UpperLeg.{s}"), FWD), 100))
            out.append((f"LowerLeg.{s}", _toward(rig.d(f"LowerLeg.{s}"), -FWD), 120))
        for c in ("Spine", "Chest"):
            out.append((c, _toward(rig.d(c), FWD), 10))
    elif pose == "torso_twist":
        for c in ("Spine", "Chest", "UpperChest"):
            if rig.has(c):
                out.append((c, rig.d(c), 20))
    elif pose == "fist":
        for s, sign in (("L", 1.0), ("R", -1.0)):
            if not rig.has(f"Hand.{s}", f"Index1.{s}", f"Little1.{s}"):
                continue
            h = rig.head[f"Hand.{s}"]
            back = np.cross(rig.head[f"Index1.{s}"] - h, rig.head[f"Little1.{s}"] - h) * sign
            palm = -_unit(back)
            for f in FINGERS:
                for i in (1, 2, 3):
                    c = f"{f}{i}.{s}"
                    if rig.has(c):
                        out.append((c, _toward(rig.d(c), palm), 30 if f == "Thumb" else 60))
    elif pose == "leg_raise":
        out.append(("UpperLeg.L", _toward(rig.d("UpperLeg.L"), FWD), 90))
    elif pose == "elbow_120":
        for s in ("L", "R"):
            out.append((f"LowerArm.{s}", _toward(rig.d(f"LowerArm.{s}"), FWD), 120))
    return out


def axis_angle(axis, degrees) -> np.ndarray:
    a = _unit(axis)
    t = math.radians(degrees)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * k + (1 - math.cos(t)) * (k @ k)


def apply_pose(rig: Rig, rotations, fraction: float) -> None:
    from mathutils import Matrix
    for pb in rig.obj.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    for contract, axis, degrees in rotations:
        rest = rig.rest[contract]
        local = rest.T @ axis_angle(axis, degrees * fraction) @ rest
        rig.obj.pose.bones[rig.name[contract]].rotation_quaternion = Matrix(local.tolist()).to_quaternion()


def cone_volume(v, tri) -> tuple[float, float]:
    """(signed volume of the cones from the patch's vertex centroid to its triangles, the same with
    every cone counted positive). Their ratio says how well the patch wraps around its centroid."""
    c = v[np.unique(tri)].mean(axis=0)
    a, b, d = v[tri[:, 0]] - c, v[tri[:, 1]] - c, v[tri[:, 2]] - c
    cones = np.einsum("ij,ij->i", a, np.cross(b, d)) / 6.0
    return float(cones.sum()), float(np.abs(cones).sum())


def welded(v, tol: float = 1e-6) -> np.ndarray:
    """Per vertex an id shared by every vertex at the same position (within `tol` x the height).
    A glTF or FBX mesh splits its vertices at UV and normal seams; the split copies move together."""
    if not len(v):
        return np.zeros(0, dtype=np.int64)
    height = float(np.ptp(v[:, 2])) or 1.0
    key = np.round(np.asarray(v) / (tol * height)).astype(np.int64)
    return np.unique(key, axis=0, return_inverse=True)[1].ravel()


def intersecting(v, tri, ids=None) -> set:
    """Triangles that cross another triangle sharing no vertex with it. `ids` (welded()) makes two
    triangles that meet at a seam's split copies share that vertex: touching, not crossing."""
    from mathutils.bvhtree import BVHTree
    tree = BVHTree.FromPolygons(v.tolist(), tri.tolist(), all_triangles=True, epsilon=0.0)
    key = tri if ids is None else np.asarray(ids)[tri]
    out = set()
    for i, k in tree.overlap(tree):
        if i != k and not (set(key[i].tolist()) & set(key[k].tolist())):
            out.add(i)
            out.add(k)
    return out


def edge_neighbours(tri_ids) -> tuple[np.ndarray, np.ndarray]:
    """(a, b): the triangle pairs that share an edge met by exactly two triangles (welded ids)."""
    e = np.sort(np.concatenate([tri_ids[:, [0, 1]], tri_ids[:, [1, 2]], tri_ids[:, [2, 0]]]), axis=1)
    face = np.tile(np.arange(len(tri_ids)), 3)
    order = np.lexsort((e[:, 1], e[:, 0]))
    e, face = e[order], face[order]
    _, first, count = np.unique(e, axis=0, return_index=True, return_counts=True)
    two = first[count == 2]
    return face[two], face[two + 1]


def _cone(n: np.ndarray, spread: float, count: int = 6) -> list:
    """n and `count` directions `spread` radians around it."""
    ref = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = _unit(np.cross(n, ref))
    w = np.cross(n, u)
    return [n] + [math.cos(spread) * n + math.sin(spread) * (math.cos(g) * u + math.sin(g) * w)
                  for g in np.linspace(0, 2 * math.pi, count, endpoint=False)]


def evidence(v_rest, tri, wall: float = 0.01, spread: float = 70.0) -> tuple[np.ndarray, np.ndarray]:
    """(sees out, back to back) per triangle, as outward() reads them."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    sees = np.zeros(len(tri), dtype=bool)
    behind = np.zeros(len(tri), dtype=bool)
    if not len(tri):
        return sees, behind
    a, b, c = v_rest[tri[:, 0]], v_rest[tri[:, 1]], v_rest[tri[:, 2]]
    centre = (a + b + c) / 3.0
    normal = np.cross(b - a, c - a)
    length = np.linalg.norm(normal, axis=1)
    unit = normal / np.maximum(length, 1e-20)[:, None]
    height = float(np.ptp(v_rest[:, 2])) or 1.0
    far = float(np.linalg.norm(np.ptp(v_rest, axis=0))) * 2.0
    eps = 1e-5 * height
    tree = BVHTree.FromPolygons(v_rest.tolist(), tri.tolist(), all_triangles=True, epsilon=0.0)
    turn = math.radians(spread)
    for i in np.nonzero(length > 0)[0].tolist():
        origin, n = Vector(centre[i].tolist()), unit[i]
        for d in _cone(n, turn):
            ray = Vector(d.tolist())
            if tree.ray_cast(origin + ray * eps, ray, far)[0] is None:
                sees[i] = True
                break
        if sees[i]:
            continue
        back = Vector((-n).tolist())
        hit, hit_n, k, _ = tree.ray_cast(origin + back * eps, back, wall * height)
        behind[i] = hit is not None and k != i and float(np.dot(hit_n, n)) < 0
    return sees | (length <= 0), behind


def outward(v_rest, tri, wall: float = 0.01, spread: float = 70.0, ids=None, rounds: int = 50) -> np.ndarray:
    """Per triangle at rest: False for an inward-facing inner shell, True for the skin.

    Evidence per triangle: it sees out when a ray from it (its normal and six directions `spread`
    degrees around it) leaves the mesh, and it is back to back when a sheet facing the other way
    lies right behind it (within `wall` x the height along -normal). Seeing out is skin, never
    overruled: the inner shell faces a closed cavity, while the skin faces open space, folds and
    thin fingers included. Back to back without seeing out is inner shell. A triangle with neither
    (the skin farther than `wall` behind it, a crumpled patch) takes the side most of its edge
    neighbours have, spread from the known ones; a piece with no known triangle at all sees out
    nowhere, so it is hidden inside (an inner shell in a piece of its own) and is left out. Then
    every triangle that does not see out takes its neighbours' majority, so a lone triangle cannot
    sit on the wrong side of a sheet. A single skin sees out everywhere but in deep folds, whose
    triangles take their neighbours' side: it keeps every triangle. Neighbours share an edge of
    welded vertices met by two triangles (`ids`, welded()); a test on the bones alone cannot tell
    the two walls apart: they are a thin closed wall, symmetric up close."""
    out = np.ones(len(tri), dtype=bool)
    if not len(tri):
        return out
    sees, behind = evidence(v_rest, tri, wall, spread)
    if sees.all():
        return out
    # 1 skin, -1 inner shell, 0 not known yet
    side = np.where(sees, 1, np.where(behind, -1, 0))
    na, nb = edge_neighbours((welded(v_rest) if ids is None else np.asarray(ids))[tri])

    def tally(s):
        acc = np.zeros(len(tri))
        np.add.at(acc, na, s[nb])
        np.add.at(acc, nb, s[na])
        return acc

    for _ in range(rounds):                  # spread the known sides into the unknown triangles
        unknown = side == 0
        if not unknown.any():
            break
        vote = np.sign(tally(side))
        take = unknown & (tally(np.abs(side)) > 0)
        if not take.any():
            break
        side[take] = np.where(vote[take] < 0, -1, 1)   # a tie keeps the triangle; the majority settles it
    side[side == 0] = -1                     # a piece no triangle of which sees out: hidden inside
    if not (side < 0).any():
        return out
    for _ in range(rounds):                  # majority of the edge neighbours, seeing out fixed
        vote = np.sign(tally(side))
        flip = ~sees & (vote != 0) & (vote != side)
        if not flip.any():
            break
        side[flip] = vote[flip]
    return side > 0


def joint_regions(rig: Rig, v_rest, tri, rotated) -> tuple[dict, dict]:
    """Per rotated body bone, the triangles within half the shorter adjoining bone of its head,
    when they wrap around the joint (signed cone volume >= half the unsigned one at rest)."""
    regions, skipped = {}, {}
    for contract in rotated:
        if any(contract.startswith(f) for f in FINGERS):
            continue
        bone = rig.obj.data.bones[rig.name[contract]]
        parent = next((c for c, n in rig.name.items() if bone.parent is not None and n == bone.parent.name), None)
        lengths = [rig.length(contract)] + ([rig.length(parent)] if parent else [])
        near = np.linalg.norm(v_rest - rig.head[contract], axis=1) <= 0.5 * min(lengths)
        sel = np.nonzero(near[tri].all(axis=1))[0]
        if len(sel) < 8:
            skipped[contract] = "fewer than 8 triangles"
            continue
        signed, total = cone_volume(v_rest, tri[sel])
        if signed < 0.5 * total:
            skipped[contract] = "the skin there does not wrap around the joint"
            continue
        regions[contract] = (sel, signed)
    return regions, skipped


def evaluate(rig: Rig, mesh, poses, steps, render_dir=None, outer_only: bool = True) -> dict:
    import bpy
    import autorig_blender as A
    apply_pose(rig, [], 0.0)
    bpy.context.view_layer.update()
    v_rest, tri_all = A.mesh_arrays(mesh)
    height = float(np.ptp(v_rest[:, 2]))
    ids = welded(v_rest)
    outer = outward(v_rest, tri_all, ids=ids) if outer_only else np.ones(len(tri_all), dtype=bool)
    tri = tri_all[outer]
    rest_hits = intersecting(v_rest, tri, ids)
    out, renders = {}, {}
    for pose in poses:
        rotations = pose_rotations(rig, pose)
        if not rotations:
            out[pose] = {"skipped": "the bones this pose turns are not mapped", "samples": []}
            continue
        bent = [c for c, _, _ in rotations]
        regions, skipped = joint_regions(rig, v_rest, tri, bent)
        samples = []
        for k in range(1, steps + 1):
            t = k / steps
            apply_pose(rig, rotations, t)
            bpy.context.view_layer.update()
            v, _ = A.mesh_arrays(mesh)
            moved_v = np.linalg.norm(v - v_rest, axis=1) > 0.001 * height
            moved = int(moved_v[tri].any(axis=1).sum())
            new = len(intersecting(v, tri, ids) - rest_hits)
            loss = {c: round(1.0 - cone_volume(v, tri[sel])[0] / v0, 4) for c, (sel, v0) in regions.items()}
            samples.append({"t": round(t, 3), "new_intersections": new, "moved": moved,
                            "ratio": round(new / moved, 4) if moved else 0.0, "volume_loss": loss})
            if render_dir and k == steps:
                renders[pose] = A.render_views(render_dir, f"pose_{pose}_", {}, [], size=512, objects=[mesh])
        out[pose] = {"samples": samples, "joints_not_measured": skipped, "bent": bent}
    apply_pose(rig, [], 0.0)
    bpy.context.view_layer.update()
    return {"height": height, "triangles": int(len(tri_all)), "outward_triangles": int(len(tri)),
            "inward_triangles": int(len(tri_all) - len(tri)), "rest_intersecting": len(rest_hits),
            "poses": out, "renders": renders}


def gates_of(result: dict, poses, args) -> list:
    ratios, worst, ball = [], (0.0, None, None), (0.0, None, None)
    for pose, data in result["poses"].items():
        for s in data["samples"]:
            ratios.append((s["ratio"], pose))
            for joint, loss in s["volume_loss"].items():
                if joint.split(".")[0] in GATED:
                    worst = max(worst, (loss, pose, joint), key=lambda w: w[0])
                else:
                    ball = max(ball, (loss, pose, joint), key=lambda w: w[0])
    result["ball_joint_loss_max"] = {"value": round(ball[0], 4), "pose": ball[1], "joint": ball[2],
                                     "gated": False}
    vals = np.array([r for r, _ in ratios]) if ratios else np.zeros(1)
    p95 = float(np.percentile(vals, 95))
    top = max(ratios, default=(0.0, None))
    result["volume_loss_max"] = {"value": round(worst[0], 4), "pose": worst[1], "joint": worst[2]}
    result["self_intersection"] = {"p95": round(p95, 4), "max": round(top[0], 4), "pose": top[1]}
    # fist may be skipped on a rig without fingers when every pose is asked for, not when named
    skipped = [p for p, d in result["poses"].items() if d.get("skipped") and (p != "fist" or args.poses != "all")]
    hinges, measured = set(), set()
    for data in result["poses"].values():
        hinges.update(c for c in data.get("bent", []) if c.split(".")[0] in HINGES)
        for s in data["samples"]:
            measured.update(s["volume_loss"])
    unmeasured = sorted(hinges - measured)
    return [
        {"name": "deform.volume_loss_max", "value": round(worst[0], 4), "limit": args.volume_max,
         "ok": worst[0] <= args.volume_max},
        {"name": "deform.self_intersection_p95", "value": round(p95, 4), "limit": args.intersect_p95,
         "ok": p95 <= args.intersect_p95},
        {"name": "deform.poses", "value": skipped, "limit": [], "ok": not skipped},
        {"name": "deform.joints_measured", "value": unmeasured, "limit": [], "ok": not unmeasured},
    ]


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser():
    p = UsageParser(prog="deform_gate.py", description=__doc__.split("\n")[0],
                                epilog="Exit codes: 0 pass, 2 a gate failed, 1 refused input.")
    p.add_argument("--armature")
    p.add_argument("--mesh")
    p.add_argument("--fbx", help="import this FBX into the open file and gate it")
    p.add_argument("--map")
    p.add_argument("--poses", default="all")
    p.add_argument("--steps", type=int, default=2)
    p.add_argument("--volume-max", type=float, default=0.35)
    p.add_argument("--intersect-p95", type=float, default=0.08)
    p.add_argument("--out")
    p.add_argument("--render")
    p.add_argument("--selftest", action="store_true")
    return p


def run(args) -> tuple[int, dict]:
    import bpy
    try:
        mapping = read_map(args.map)
    except (OSError, ValueError, Refused) as exc:
        return 1, {"tool": "deform_gate", "error": str(exc)}
    if args.fbx:
        if not os.path.isfile(args.fbx):
            return 1, {"tool": "deform_gate", "error": f"no file {args.fbx}"}
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=args.fbx)
        new = [o for o in bpy.data.objects if o not in before]
        rigs = [o for o in new if o.type == 'ARMATURE']
        if len(rigs) != 1:
            return 1, {"tool": "deform_gate", "error": f"{args.fbx} holds {len(rigs)} armatures"}
        rig_obj = rigs[0]
        meshes = [o for o in new if o.type == 'MESH' and any(m.type == 'ARMATURE' and m.object == rig_obj
                                                             for m in o.modifiers)]
    else:
        rig_obj = bpy.data.objects.get(args.armature or "")
        mesh = bpy.data.objects.get(args.mesh or "")
        if rig_obj is None or rig_obj.type != 'ARMATURE' or mesh is None or mesh.type != 'MESH':
            return 1, {"tool": "deform_gate", "error": f"need --armature and --mesh objects ({args.armature!r}, "
                                                       f"{args.mesh!r})"}
        meshes = [mesh]
    if not meshes:
        return 1, {"tool": "deform_gate", "error": "no mesh is skinned to the armature"}
    mesh = max(meshes, key=lambda o: len(o.data.vertices))
    rig = Rig(rig_obj, mapping)
    lacking = [b for b in BODY if b not in rig.name]
    if lacking:
        return 1, {"tool": "deform_gate", "error": f"body bones not found on {rig_obj.name!r}: {lacking} "
                                                   "(pass --map)", "mapped": sorted(rig.name)}
    poses = POSES if args.poses == "all" else tuple(p.strip() for p in args.poses.split(","))
    unknown = [p for p in poses if p not in POSES]
    if unknown:
        return 1, {"tool": "deform_gate", "error": f"unknown poses {unknown}; known {list(POSES)}"}
    saved = {pb.name: (pb.rotation_mode, tuple(pb.rotation_quaternion), tuple(pb.rotation_euler),
                       tuple(pb.location), tuple(pb.scale)) for pb in rig_obj.pose.bones}
    action = rig_obj.animation_data.action if rig_obj.animation_data else None
    if action is not None:
        rig_obj.animation_data.action = None
    try:
        if args.render:
            os.makedirs(args.render, exist_ok=True)
        result = evaluate(rig, mesh, poses, max(1, args.steps), args.render,
                          outer_only=not getattr(args, "all_triangles", False))
    finally:
        for pb in rig_obj.pose.bones:
            mode, q, e, loc, sc = saved[pb.name]
            pb.rotation_mode = mode
            pb.rotation_quaternion, pb.rotation_euler, pb.location, pb.scale = q, e, loc, sc
        if action is not None:
            rig_obj.animation_data.action = action
    gates = gates_of(result, poses, args)
    report = {"tool": "deform_gate", "armature": rig_obj.name, "mesh": mesh.name, **result,
              "gates": gates, "ok": all(g["ok"] for g in gates)}
    return (0 if report["ok"] else 2), report


# ------------------------------------------------------------------------------ selftest


def skin(mesh, rig_obj, spec, mode: str) -> None:
    """Weights for the selftest. good: nearest bone by distance / radius, shared with its parent and
    children (exp falloff), smoothed over edges; hard: nearest bone only; blend: as good, then every
    arm vertex near the elbow split half and half between the upper arm and the forearm (the
    over-wide blend that collapses an elbow)."""
    import autorig_blender as A
    v, tri = A.mesh_arrays(mesh, evaluated=False)
    bones = [b for b in spec if b.get("deform", True)]
    names = [b["name"] for b in bones]
    heads = np.array([b["head"] for b in bones])
    tails = np.array([b["tail"] for b in bones])
    radius = np.array([max(b.get("radius", 0.03), 0.01) for b in bones])
    ab = tails - heads
    t = np.clip(np.einsum("vbk,bk->vb", v[:, None, :] - heads[None], ab) / (ab ** 2).sum(1), 0, 1)
    dist = np.linalg.norm(v[:, None, :] - (heads[None] + t[..., None] * ab[None]), axis=2) / radius
    near = dist.argmin(1)
    parent = {b["name"]: b.get("parent") for b in bones}
    index = {n: i for i, n in enumerate(names)}
    family = [{i} | ({index[parent[n]]} if parent[n] in index else set()) |
              {index[c] for c, p in parent.items() if p == n and c in index} for i, n in enumerate(names)]
    w = np.zeros((len(v), len(names)))
    if mode == "hard":
        w[np.arange(len(v)), near] = 1.0
    else:
        dmin = dist[np.arange(len(v)), near]
        for i in range(len(v)):
            for j in family[near[i]]:
                w[i, j] = math.exp(-(dist[i, j] - dmin[i]) / 0.35)
        edges = np.unique(np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), axis=1), axis=0)
        for _ in range(4):
            acc = w.copy()
            cnt = np.ones(len(v))
            np.add.at(acc, edges[:, 0], w[edges[:, 1]])
            np.add.at(acc, edges[:, 1], w[edges[:, 0]])
            np.add.at(cnt, edges[:, 0], 1)
            np.add.at(cnt, edges[:, 1], 1)
            w = acc / cnt[:, None]
        order = np.argsort(-w, axis=1)
        keep = np.zeros_like(w, dtype=bool)
        np.put_along_axis(keep, order[:, :4], True, axis=1)
        w = np.where(keep, w, 0.0)
    if mode == "blend":
        for s in ("L", "R"):
            lo = index[f"LowerArm.{s}"]
            elbow = heads[lo]
            arm = np.isin(near, [index[f"UpperArm.{s}"], lo]) & \
                (np.linalg.norm(v - elbow, axis=1) < 0.6 * np.linalg.norm(ab[lo]))
            w[arm] = 0.0
            w[arm, index[f"UpperArm.{s}"]] = 0.5
            w[arm, lo] = 0.5
    w /= w.sum(1, keepdims=True)
    for g in list(mesh.vertex_groups):
        mesh.vertex_groups.remove(g)
    groups = [mesh.vertex_groups.new(name=n) for n in names]
    for j, g in enumerate(groups):
        idx = np.nonzero(w[:, j] > 1e-4)[0]
        for i in idx:
            g.add([int(i)], float(w[i, j]), 'REPLACE')
    for m in list(mesh.modifiers):
        if m.type == 'ARMATURE':
            mesh.modifiers.remove(m)
    mod = mesh.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig_obj


def mesh_object(name: str, like, v, f, rig_obj):
    """A new mesh object from local vertices and triangles, placed and parented like `like`."""
    import bpy
    data = bpy.data.meshes.new(name)
    data.from_pydata(np.asarray(v).tolist(), [], np.asarray(f).tolist())
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = rig_obj
    obj.matrix_world = like.matrix_world.copy()
    return obj


def copy_weights(src, dst, index) -> None:
    """dst vertex k takes src vertex index[k]'s groups and weights."""
    weights = {}
    names = {g.index: g.name for g in src.vertex_groups}
    for v in src.data.vertices:
        weights[v.index] = [(names[g.group], g.weight) for g in v.groups]
    groups = {}
    for k, i in enumerate(index):
        for name, w in weights[int(i)]:
            if name not in groups:
                groups[name] = dst.vertex_groups.get(name) or dst.vertex_groups.new(name=name)
            groups[name].add([k], w, 'REPLACE')
    mod = dst.modifiers.new("Armature", 'ARMATURE')
    mod.object = src.modifiers["Armature"].object


def spec_both_sides(spec: dict) -> list:
    bones = []
    for b in spec["bones"]:
        bones.append(dict(b))
        if spec.get("mirror") and b["name"].endswith(".L"):
            twin = dict(b)
            twin["name"] = b["name"][:-2] + ".R"
            if b.get("parent", "") and b["parent"].endswith(".L"):
                twin["parent"] = b["parent"][:-2] + ".R"
            twin["head"] = [-b["head"][0], b["head"][1], b["head"][2]]
            twin["tail"] = [-b["tail"][0], b["tail"][1], b["tail"][2]]
            bones.append(twin)
    return bones


def outward_cases() -> dict:
    """outward() on mesh_check's tube body: {check name: passed}."""
    import mesh_check as MC
    out = {}
    skin_v, skin_f = MC.body()
    hand = np.array([0.17, 0, 1.38]) + 0.625 * np.array([math.sqrt(0.5), 0, -math.sqrt(0.5)])
    # four fingers 8 mm thick (under the wall, 0.01 x 1.7 m), 1 mm apart, held together (a mitten)
    fingers = [MC.tube(hand + [0, y, 0], hand + [0.05, y, -0.05], 0.004, n=8, rings=6)
               for y in (-0.0135, -0.0045, 0.0045, 0.0135)]
    v, f = MC.assemble([(skin_v, skin_f)] + fingers)
    keep = outward(v, f)
    # (the tubes overlap: a foot's top hidden inside the shin is left out, under 2 %)
    out["thin fingers on one skin: every finger triangle kept"] = bool(
        keep[len(skin_f):].all() and (~keep[:len(skin_f)]).mean() < 0.02)
    near_v, _ = MC.body(inner=0.006)
    far_v, shell_f = MC.body(inner=0.03)
    per = len(skin_v) // 9                         # nine tubes, the legs are tubes 3 and 4
    v = near_v.copy()
    v[(9 + 3) * per:(9 + 5) * per] = far_v[(9 + 3) * per:(9 + 5) * per]
    v, f = MC.assemble([(v, shell_f)] + fingers)
    keep = outward(v, f)
    skin_t = len(skin_f)
    finger_t = len(f) - len(shell_f)
    legs = slice(skin_t + 3 * (skin_t // 9), skin_t + 5 * (skin_t // 9))
    # the skin left out is only skin hidden inside another tube (a torso's hem inside a thigh)
    sees, _ = evidence(v, f)
    out["inner shell: fingers and every skin triangle that sees out kept"] = bool(
        keep[len(shell_f):].all() and keep[:skin_t][sees[:skin_t]].all() and (~keep[:skin_t]).mean() < 0.12)
    out["inner shell: every inner triangle left out, the far legs too"] = bool(
        not keep[skin_t:len(shell_f)].any() and finger_t > 0 and not keep[legs].any())
    return out


def selftest() -> tuple[int, dict]:
    import bpy
    import autorig_blender as A
    import arp_markers as AM
    checks, failed, notes = 0, [], {}

    def ok(name, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failed.append(name)

    A.clear_scene()
    body, _ = A.build_runner()
    V, F = A.mesh_arrays(body)
    opts = {"spine_bones": 3, "fingers": "fixed", "adjust": None, "arm_angle": (30.0, 60.0),
            "arm_ratios": (0.42, 0.75), "symmetry_max": 0.02, "no_window_gate": False}
    spec = spec_both_sides(AM.build_report(V, F, opts)["contract_bones"])
    rig_obj = A.build_armature("RunnerRig", spec)
    body.parent = rig_obj
    args = parser().parse_args(["--armature", rig_obj.name, "--mesh", body.name])
    results = {}
    for mode in ("good", "hard", "blend"):
        skin(body, rig_obj, spec, mode)
        code, rep = run(args)
        results[mode] = (code, rep)
        notes[mode] = {g["name"]: g["value"] for g in rep.get("gates", [])}
    code, rep = results["good"]
    gate = {g["name"]: g for g in rep.get("gates", [])}
    ok("good skin: exit 0", code == 0)
    ok("good skin: six poses measured", len(rep.get("poses", {})) == 6 and
       all(d["samples"] for d in rep.get("poses", {}).values()))
    code, rep = results["hard"]
    gate = {g["name"]: g for g in rep.get("gates", [])}
    ok("hard skin: exit 2, self-intersection fails", code == 2 and not gate["deform.self_intersection_p95"]["ok"])
    code, rep = results["blend"]
    gate = {g["name"]: g for g in rep.get("gates", [])}
    ok("half-and-half arm: exit 2, volume fails at the elbow", code == 2 and not gate["deform.volume_loss_max"]["ok"]
       and rep["volume_loss_max"]["joint"] in ("LowerArm.L", "LowerArm.R"))
    ok("pose put back", all(tuple(pb.rotation_quaternion) == (1, 0, 0, 0) for pb in rig_obj.pose.bones))
    ok("single skin: every triangle faces outward", rep["inward_triangles"] <= 0.01 * rep["triangles"])
    # an inward-facing inner twin 4 mm inside the skin, each vertex with its outer vertex's weights:
    # the outward mask keeps the gate on the skin, as on the single-shell body
    skin(body, rig_obj, spec, "good")
    good_p95 = results["good"][1]["self_intersection"]["p95"]
    good_loss = results["good"][1]["volume_loss_max"]["value"]
    data = body.data
    co = np.empty(len(data.vertices) * 3)
    data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    nrm = np.empty(len(data.vertices) * 3)
    data.vertices.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    _, lf = A.mesh_arrays(body, evaluated=False)
    n = len(co)
    twin = mesh_object("RunnerTwin", body, np.vstack([co, co - 0.004 * nrm]),
                       np.vstack([lf, lf[:, ::-1] + n]), rig_obj)
    copy_weights(body, twin, np.r_[np.arange(n), np.arange(n)])
    twin_args = parser().parse_args(["--armature", rig_obj.name, "--mesh", twin.name])
    code, rep = run(twin_args)
    gate = {g["name"]: g for g in rep.get("gates", [])}
    notes["inner_shell"] = {g["name"]: g["value"] for g in rep.get("gates", [])}
    notes["inner_shell"]["triangles"] = [rep.get("triangles"), rep.get("outward_triangles"), int(len(lf))]
    hinges = {"LowerArm.L", "LowerArm.R", "LowerLeg.L", "LowerLeg.R"}
    measured = {j for d in rep.get("poses", {}).values() for smp in d["samples"] for j in smp["volume_loss"]}
    ok("inner shell: exit 0, hinges measured", code == 0 and hinges <= measured and
       gate["deform.joints_measured"]["ok"])
    ok("inner shell: the inner half left out", abs(rep["outward_triangles"] - len(lf)) <= 0.02 * len(lf))
    ok("inner shell: p95 and elbow loss as on one skin",
       rep["self_intersection"]["p95"] <= good_p95 + 0.005 and abs(rep["volume_loss_max"]["value"] - good_loss) < 0.02)
    twin_args.all_triangles = True                # every triangle: the inner shell hides the hinges
    code, rep = run(twin_args)
    gate = {g["name"]: g for g in rep.get("gates", [])}
    notes["inner_shell_all_triangles"] = {g["name"]: g["value"] for g in rep.get("gates", [])}
    ok("inner shell counted whole: joints_measured fails, exit 2", code == 2 and
       not gate["deform.joints_measured"]["ok"])
    bpy.data.objects.remove(twin)
    # the same body split along a seam (every left-half triangle on its own copies of its
    # vertices, as a glTF or FBX writes UV seams): touching across the seam is not crossing
    vw0 = A.mesh_arrays(body, evaluated=False)[0]
    left = vw0[lf].mean(axis=1)[:, 0] > 0
    used = np.unique(lf[left])
    copy = np.full(n, -1)
    copy[used] = n + np.arange(len(used))
    seam_f = np.where(left[:, None], copy[lf], lf)
    seamed = mesh_object("RunnerSeam", body, np.vstack([co, co[used]]), seam_f, rig_obj)
    copy_weights(body, seamed, np.r_[np.arange(n), used])
    raw = len(intersecting(np.vstack([vw0, vw0[used]]), seam_f))
    code, rep = run(parser().parse_args(["--armature", rig_obj.name, "--mesh", seamed.name]))
    notes["seam"] = {"raw_rest_intersecting": raw, "rest_intersecting": rep.get("rest_intersecting"),
                     "p95": rep.get("self_intersection", {}).get("p95")}
    ok("seam split: the raw vertex test sees crossings at the seam", raw > 0)
    ok("seam split: welded, no rest crossings and p95 as on one skin", code == 0 and
       rep["rest_intersecting"] <= results["good"][1]["rest_intersecting"] + 2 and
       rep["self_intersection"]["p95"] <= good_p95 + 0.005)
    bpy.data.objects.remove(seamed)
    # the split itself, on tube bodies: thin single-skin fingers stay, an inner shell farther
    # from the skin than the wall at the legs is still left out
    ok_cases = outward_cases()
    notes["outward_cases"] = ok_cases
    for name, cond in ok_cases.items():
        ok(name, cond)
    # an opening at the left elbow: the hinge cannot be measured, and that fails
    elbow = np.array(rig_obj.matrix_world) @ np.r_[np.array(rig_obj.data.bones["LowerArm.L"].head_local), 1.0]
    reach = 0.5 * min(np.linalg.norm(np.subtract(b["tail"], b["head"])) for b in spec
                      if b["name"] in ("UpperArm.L", "LowerArm.L"))
    vw, _ = A.mesh_arrays(body, evaluated=False)
    far = np.linalg.norm(vw - elbow[:3], axis=1) > reach
    holed = mesh_object("RunnerHole", body, co, lf[far[lf].all(axis=1)], rig_obj)
    copy_weights(body, holed, np.arange(n))
    code, rep = run(parser().parse_args(["--armature", rig_obj.name, "--mesh", holed.name, "--poses", "elbow_120"]))
    gate = {g["name"]: g for g in rep.get("gates", [])}
    ok("elbow not measurable: joints_measured fails with LowerArm.L, exit 2", code == 2 and
       gate["deform.joints_measured"]["value"] == ["LowerArm.L"])
    code, rep = run(parser().parse_args(["--armature", rig_obj.name, "--mesh", holed.name, "--poses", "arms_up"]))
    ok("no hinge bent: joints_measured passes", next(g for g in rep["gates"]
                                                     if g["name"] == "deform.joints_measured")["ok"])
    bpy.data.objects.remove(holed)
    # refused inputs
    with tempfile.TemporaryDirectory() as d:
        bad = os.path.join(d, "map.json")
        with open(bad, "w", encoding="utf-8") as handle:
            json.dump({"bones": {"UpperArm.L": "nope"}}, handle)
        ok("map to a missing bone: exit 1", run(parser().parse_args(["--armature", rig_obj.name, "--mesh", body.name,
                                                                      "--map", bad]))[0] == 1)
        renamed = rig_obj.data.bones["LowerArm.L"]
        renamed.name = "forearm_l"
        ok("body bone missing: exit 1", run(args)[0] == 1)
        with open(bad, "w", encoding="utf-8") as handle:
            json.dump({"bones": {"LowerArm.L": "forearm_l"}}, handle)
        skin(body, rig_obj, [dict(b, name="forearm_l") if b["name"] == "LowerArm.L" else
                             (dict(b, parent="forearm_l") if b.get("parent") == "LowerArm.L" else b) for b in spec],
             "good")
        code, rep = run(parser().parse_args(["--armature", rig_obj.name, "--mesh", body.name, "--map", bad]))
        ok("role map finds the renamed bone: exit 0", code == 0)
        ok("unknown object: exit 1", run(parser().parse_args(["--armature", "Nope", "--mesh", "Nope"]))[0] == 1)
        ok("unknown pose: exit 1", run(parser().parse_args(["--armature", rig_obj.name, "--mesh", body.name,
                                                            "--map", bad, "--poses", "cartwheel"]))[0] == 1)
        with open(bad, "w", encoding="utf-8") as handle:
            json.dump({"bones": {"LowerArm.L": "forearm_l", "Index1.L": "nope", "Index1.R": "nope"}}, handle)
        fist = parser().parse_args(["--armature", rig_obj.name, "--mesh", body.name, "--map", bad, "--poses", "fist"])
        code, rep = run(fist)
        ok("fist named on a rig without index fingers: deform.poses fails, exit 2", code == 2 and
           not next(g for g in rep["gates"] if g["name"] == "deform.poses")["ok"])
        code, rep = run(parser().parse_args(["--armature", rig_obj.name, "--mesh", body.name, "--map", bad,
                                             "--poses", "all", "--steps", "1"]))
        ok("fist skipped under --poses all: deform.poses passes", next(g for g in rep["gates"]
                                                                       if g["name"] == "deform.poses")["ok"])
    return (0 if not failed else 1), {"selftest": "pass" if not failed else "fail", "checks": checks,
                                      "failed": failed, "gate_values": notes}


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if argv[:1] == ["selftest"]:                        # `selftest` and `--selftest` are one command
        argv = ["--selftest", *argv[1:]]
    args = parser().parse_args(argv)
    try:
        import bpy  # noqa: F401
    except ImportError:
        print(json.dumps({"tool": "deform_gate", "error": "run inside Blender: blender -b -P deform_gate.py -- ..."}))
        sys.exit(1)
    if args.selftest:
        code, report = selftest()
    else:
        code, report = run(args)
    text = json.dumps(report, indent=2)
    if args.out and not args.selftest:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(text)
    sys.stdout.flush()
    sys.exit(code)


if __name__ == "__main__":
    main()
