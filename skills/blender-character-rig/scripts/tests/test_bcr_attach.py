"""test_bcr_attach.py — bcr_attach on a procedural rig and body, in Blender: the hand grip and the forearm mount.

    Blender -b --factory-startup --python-exit-code 1 -P tests/test_bcr_attach.py -- --selftest

The body is tubes along an A-pose rig built with bcr_armature, so whether a prop cuts the skin is
checked here against the tubes' own axes and radii, not with bcr_attach's measurement. Cases: a
domed slab mounts on the outer side of the left forearm, its dome facing out and up along the
bone; the same slab turned round mounts on the right forearm still facing out; a slab longer than
the forearm clears the thicker upper arm; a second call is reused; a negative clearance fails the
skin gates; a mallet fails flat_ratio; a mallet in the hand keeps its grip, ratio and head side;
a refused forearm mount (an outward along the bone, an up along the normal) leaves the prop's
vertices, matrix and parent as they were; an unknown mount and a mount switch refuse, each with
its own message; a body skinned to a posed rig is measured at rest and the pose is put back.
Prints PASS / FAIL per case; exits 1 when any fails.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import bcr_armature  # noqa: E402
import bcr_attach  # noqa: E402

RESULTS = []
# A-pose: the arm leaves the shoulder 45 degrees down; armature space, the character faces -Y
SHOULDER, UPPER, FORE, HAND = Vector((0.20, 0.0, 1.42)), 0.28, 0.27, 0.09
DOWN = Vector((math.cos(math.radians(45)), 0.0, -math.sin(math.radians(45))))
RADII = {"upper": 0.055, "fore": 0.045, "hand": 0.035}


def case(name, cond, why=""):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f": {why}"))


def gate(result, name):
    return next((g for g in result.get("gates", []) if g["name"] == name), None)


def joints(side):
    m = Vector((side, 1.0, 1.0))
    s = SHOULDER * 1
    s.x *= side
    dn = Vector((DOWN.x * m.x, DOWN.y, DOWN.z))
    e = s + dn * UPPER
    w = e + dn * FORE
    return s, e, w, w + dn * HAND


def tubes():
    """(start, end, radius) of every limb tube, both sides."""
    out = []
    for side in (1, -1):
        s, e, w, t = joints(side)
        out += [(s, e, RADII["upper"]), (e, w, RADII["fore"]), (w, t, RADII["hand"])]
    return out


def tube(bm, a, b, r, segs=24, step=0.01):
    """A closed tube from a to b with a ring every `step` metres."""
    axis = (b - a)
    n = max(2, int(axis.length / step) + 1)
    rot = Vector((0, 0, 1)).rotation_difference(axis.normalized()).to_matrix()
    rings = []
    for i in range(n):
        c = a + axis * (i / (n - 1))
        rings.append([bm.verts.new(c + rot @ Vector((r * math.cos(2 * math.pi * k / segs),
                                                     r * math.sin(2 * math.pi * k / segs), 0)))
                      for k in range(segs)])
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(segs):
            bm.faces.new((r0[k], r0[(k + 1) % segs], r1[(k + 1) % segs], r1[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def build_body():
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, 0, 1.15)) @ Matrix.Diagonal((0.30, 0.20, 0.60, 1)))
    for a, b, r in tubes():
        tube(bm, a, b, r)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new("Courier")
    bm.to_mesh(mesh)
    bm.free()
    body = bpy.data.objects.new("Courier", mesh)
    bpy.context.scene.collection.objects.link(body)
    bones = [{"name": "Root", "head": [0, 0, 0], "tail": [0, 0.1, 0], "deform": False},
             {"name": "Spine", "head": [0, 0, 0.9], "tail": [0, 0, 1.42], "parent": "Root", "radius": 0.2}]
    s, e, w, t = joints(1)
    bones += [{"name": "UpperArm.L", "head": list(s), "tail": list(e), "parent": "Spine", "radius": 0.055},
              {"name": "Forearm.L", "head": list(e), "tail": list(w), "parent": "UpperArm.L", "radius": 0.045},
              {"name": "Hand.L", "head": list(w), "tail": list(t), "parent": "Forearm.L", "radius": 0.035}]
    rig = bcr_armature.run({"name": "CourierRig", "collection": "Courier", "mirror": True, "bones": bones})
    assert rig["pass"], rig["gates"]
    return body


def slab(name, tall=0.22, wide=0.18, dome=0.04, back=0.008, turned=False):
    """A shield standing up: its dome faces -Y (or +Y when turned round about Z), its top is +Z."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
    for v in bm.verts:
        x, y, z = v.co
        v.co = Vector((x * wide / 2, y * (dome if y < 0 else back), z * tall / 2))
    if turned:
        bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(math.pi, 3, "Z"))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    apex = max(range(len(mesh.vertices)), key=lambda i: -mesh.vertices[i].co.y * (-1 if turned else 1))
    return obj, apex


def mallet(name):
    """A handle along +Z (0 to 0.45, radius 0.015) with a head beside it toward +X."""
    bm = bmesh.new()
    tube(bm, Vector((0, 0, 0)), Vector((0, 0, 0.45)), 0.015, segs=16)
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0.03, 0, 0.525)) @ Matrix.Diagonal((0.12, 0.06, 0.15, 1)))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def seg_dist(p, a, b):
    ab = b - a
    k = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (p - (a + ab * k)).length


def cuts(obj):
    """Prop vertices inside any tube (the true cylinder, which holds the 24-sided one)."""
    mw = obj.matrix_world
    return sum(1 for v in obj.data.vertices for a, b, r in tubes() if seg_dist(mw @ v.co, a, b) < r - 1e-6)


def mount(prop, bone, **extra):
    return bcr_attach.run({"prop": prop, "armature": "CourierRig", "bone": bone, "mount": "forearm",
                           "mesh": "Courier", **extra})


def failing(r):
    return [(g["name"], g["value"]) for g in r["gates"] if not g["pass"]]


def refused(call):
    """The refusal's message, or "" when the call returned."""
    try:
        call()
        return ""
    except RuntimeError as exc:
        return str(exc)


def selftest():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_body()

    # the left forearm: dome out, top along the bone
    shield, apex = slab("Buckler")
    r = mount("Buckler", "Forearm.L")
    case("forearm: every gate passes", r["pass"], failing(r))
    s, e, w, _ = joints(1)
    point = e.lerp(w, 0.5)
    out = Vector(r["outward"])
    tip = shield.matrix_world @ shield.data.vertices[apex].co
    case("forearm: the outward direction is away from the midline and across the bone",
         out.x > 0.5 and abs(out.dot((w - e).normalized())) < 1e-6, list(out))
    case("forearm: the dome's apex is on the outer side", (tip - point).dot(out) > RADII["fore"] + 0.03 and tip.x > point.x,
         [list(tip), list(point)])
    case("forearm: no prop vertex inside a limb", cuts(shield) == 0, cuts(shield))
    up = (shield.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    case("forearm: the prop's top runs along the bone toward the wrist", up.dot((w - e).normalized()) > 0.999, list(up))
    case("forearm: parented to the forearm bone", shield.parent_type == 'BONE' and shield.parent_bone == "Forearm.L")
    case("forearm: skin radius is the forearm's", abs(r["skin_radius"] - RADII["fore"]) < 0.002, r["skin_radius"])
    case("forearm: the back sits clearance off the skin",
         abs(gate(r, "skin_clearance_min")["value"] - 0.005) < 0.002, gate(r, "skin_clearance_min"))
    again = mount("Buckler", "Forearm.L")
    case("forearm: a second call is reused", again["reused"] is True and again["pass"]
         and (shield.matrix_world @ shield.data.vertices[apex].co - tip).length < 1e-6)

    # the right forearm, the slab turned round: still faces out
    turned, apex2 = slab("BucklerTurned", turned=True)
    r2 = mount("BucklerTurned", "Forearm.R")
    s2, e2, w2, _ = joints(-1)
    point2 = e2.lerp(w2, 0.5)
    tip2 = turned.matrix_world @ turned.data.vertices[apex2].co
    case("turned slab, right forearm: every gate passes", r2["pass"], failing(r2))
    case("turned slab: the front was found on the prop's +Y", r2["front_side"][1] > 0.99, r2["front_side"])
    case("turned slab: the dome's apex is on the outer side", tip2.x < point2.x and (tip2 - point2).dot(Vector(r2["outward"])) > 0.07,
         [list(tip2), list(point2)])
    case("turned slab: no prop vertex inside a limb", cuts(turned) == 0, cuts(turned))

    # longer than the forearm: its ends lie over the elbow and the thicker upper arm
    long_, _ = slab("Pavise", tall=0.40)
    r3 = mount("Pavise", "Forearm.L")
    case("long slab: every gate passes", r3["pass"], failing(r3))
    case("long slab: clears the upper arm", cuts(long_) == 0 and r3["skin_radius"] > RADII["fore"] + 0.005,
         [cuts(long_), r3["skin_radius"]])

    # pressed into the arm: the skin gates fail
    bad, _ = slab("Pressed")
    r4 = mount("Pressed", "Forearm.R", clearance=-0.02)
    case("pressed into the arm: the skin gates fail",
         not r4["pass"] and not gate(r4, "skin_clearance_min")["pass"] and not gate(r4, "skin_overlap_pairs")["pass"]
         and cuts(bad) > 0, failing(r4))

    # not flat: refused by flat_ratio
    mallet("Club")
    r5 = mount("Club", "Forearm.R")
    case("a mallet on the forearm fails flat_ratio", not gate(r5, "flat_ratio")["pass"], gate(r5, "flat_ratio"))

    # the hand grip is unchanged
    tool = mallet("Mallet")
    r6 = bcr_attach.run({"prop": "Mallet", "armature": "CourierRig", "bone": "Hand.R", "rotation": [["Z", -90]]})
    _, _, w6, t6 = joints(-1)
    case("hand: every gate passes", r6["pass"], failing(r6))
    case("hand: handle_radius_ratio is the handle's", abs(gate(r6, "handle_radius_ratio")["value"] - 0.015 / 0.6) < 0.002,
         gate(r6, "handle_radius_ratio"))
    case("hand: the head side is +X", r6["head_side"][0] > 0.99, r6["head_side"])
    case("hand: the grip sits at the middle of the bone", (Vector(r6["world_position"]) - (w6 + t6) / 2).length < 1e-5,
         r6["world_position"])
    case("hand: the origin is the grip", abs(min(v.co.z for v in tool.data.vertices) + 0.27 * 0.6) < 1e-4)
    case("hand: a second call is reused", bcr_attach.run({"prop": "Mallet", "armature": "CourierRig",
                                                           "bone": "Hand.R"})["reused"] is True)

    # a refused forearm mount leaves the prop as it was: vertices, matrix, parent
    loose, _ = slab("Loose")
    loose.location = (1.0, 2.0, 0.5)
    bpy.context.view_layer.update()
    co0, mw0 = [v.co.copy() for v in loose.data.vertices], loose.matrix_world.copy()
    for name, extra, says in (("an outward along the bone", {"outward": list(DOWN)}, "runs along the outward direction"),
                              ("an up along the prop's normal", {"up": "Y"}, "lies along the prop's normal")):
        why = refused(lambda: mount("Loose", "Forearm.L", **extra))
        bpy.context.view_layer.update()
        moved = max((v.co - c).length for v, c in zip(loose.data.vertices, co0))
        case(f"refused, {name}: the reason given, the prop untouched", says in why and moved == 0
             and all(loose.matrix_world[i][j] == mw0[i][j] for i in range(4) for j in range(4))
             and loose.parent is None and "bcr_attach" not in loose, [why, moved, list(loose.matrix_world.translation)])

    for name, params, says in (("an unknown mount refuses", {"prop": "Loose", "mount": "belt"}, "mount 'belt': one of"),
                               ("a mount switch refuses", {"prop": "Mallet", "mount": "forearm", "mesh": "Courier"},
                                "Mallet is attached with another mount")):
        why = refused(lambda: bcr_attach.run({"armature": "CourierRig", "bone": "Forearm.R", **params}))
        case(name, says in why, why)

    # the skin is read with the rig at rest: a body skinned to a posed rig is still measured where the bones are read
    rig = bpy.data.objects["CourierRig"]
    body = bpy.data.objects["Courier"]
    body.vertex_groups.new(name="Spine").add(range(len(body.data.vertices)), 1.0, 'REPLACE')
    body.modifiers.new("Armature", 'ARMATURE').object = rig
    rig.pose.bones["Spine"].location = (0.25, 0.25, 0.25)
    bpy.context.view_layer.update()
    slab("Posed")
    try:
        r7 = mount("Posed", "Forearm.L")
        case("posed rig: the skin is the rest pose's (skin radius the forearm's), every gate passes",
             r7["pass"] and abs(r7["skin_radius"] - RADII["fore"]) < 0.002, [failing(r7), r7["skin_radius"]])
    except RuntimeError as exc:
        case("posed rig: the skin is the rest pose's (skin radius the forearm's), every gate passes", False, exc)
    case("posed rig: the rig is back in its pose after the read", rig.data.pose_position == 'POSE', rig.data.pose_position)

    print(f"{sum(RESULTS)}/{len(RESULTS)} passed")
    return all(RESULTS)


if __name__ == "__main__":
    sys.exit(0 if selftest() else 1)
