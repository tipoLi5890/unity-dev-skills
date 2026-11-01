#!/usr/bin/env python3
"""rig_exam_blender.py — the rig exam's Blender side: a cast of bodies built from known skeletons, and weight faults.

usage (Blender, headless; rig_exam.py runs these):
    blender -b --factory-startup -P rig_exam_blender.py -- cast OUT_DIR [--only standard,chibi] [--seed 0]
    blender -b --factory-startup -P rig_exam_blender.py -- weights FBX CONTRACT.json FAULT OUT.blend [--report R.json]
                                                                [--skirt MARKERS.json]
    blender -b --factory-startup -P rig_exam_blender.py -- --selftest

cast: per body of CAST below, a metaball body built around a known skeleton (A-pose, facing -Y, soles on Z 0),
turned into one mesh, decimated to about --faces triangles, written as OUT_DIR/NAME.glb with OUT_DIR/NAME.truth.json
(exam/1, kind truth: the joints it was built from, in the GLB's frame, Z up). Joints are the capsule ends the
body was built from; the ends (hand_tip, toe_tip, heel, head_top, finger tips) are the mesh's own extreme
points along the true axis; head_top is the skull's, measured before any hair is added. Each body's
proportions are jittered by at most 2 % from --seed, so a seed is one reproducible cast.

weights: the FBX of a bound rig (the pipeline's export) gets one known weight fault and is saved as a .blend
for `deform_gate.py --armature RIG --mesh MESH --map CONTRACT.json`. FAULT is one of
  none        unchanged (the control: it must read as the FBX itself does)
  leg_smear   half of each left-leg vertex's thigh and shin weight moved to the right leg's twin bones
  elbow_blend / knee_blend   every vertex of the limb within 0.6 x the shorter span of the joint split 50/50
              between the upper and the lower bone (the wide blend the volume gate is for)
  rigid       each vertex keeps only its heaviest deform bone (a hard seam at every joint)
  skirt_split (--skirt: the base's arp_markers --body skirt report) the skirt's own skin (arp_markers.skirt_region)
              on Hips and the thigh of its own side, the thigh's share rising to 1 at the hem and switching
              sides at the midline: a skirt torn between the thighs, as a plain bind leaves a long coat
Bones come from the contract report's retarget_map (an exporter's twist twin, `_stretch` -> `_twist`, counts
with its bone). The report names the armature and mesh in the saved file.

Prints one JSON object. Exit codes: 0 done, 1 refused input or a failed selftest. Requires Blender and numpy.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SCHEMA = "exam/1"
FAULTS = ("none", "leg_smear", "elbow_blend", "knee_blend", "rigid", "skirt_split")
FINGER_NAMES = ("index", "middle", "ring", "little")

# Body parameters, metres for a 1.7 m adult; `scale` sets the final size. Every body starts from STANDARD.
STANDARD = dict(scale=1.75 / 1.7, leg=1.0, torso=1.0, girth=1.0, limb=1.0, arm=1.0, head=1.0, neck=1.0,
                arm_deg=(45.0, 45.0), hands="fingers", hair=False, skirt=None, knee_dz=0.0, shoulder_dz=0.0,
                foot=1.0)
CAST = {
    "standard":   dict(),
    "chibi":      dict(scale=1.0 / 1.7, leg=0.45, torso=0.75, head=2.1, arm=0.62, limb=1.25, girth=1.15,
                       neck=0.4, hands="mitten", foot=1.1,
                       expect_fail=["legs_separated", "arms_separated", "markers.windows"]),
    "heavy":      dict(girth=1.45, limb=1.35, arm_deg=(50.0, 50.0)),
    "thin":       dict(girth=0.78, limb=0.72, arm_deg=(55.0, 55.0)),
    "long_limbs": dict(leg=1.12, arm=1.15, torso=0.95, arm_deg=(30.0, 30.0)),
    "mitten":     dict(hands="mitten"),
    "spiky_hair": dict(hair=True),
    "skirt":      dict(skirt=0.40),              # rigged with --body skirt (rig_exam.py run)
    "asym":       dict(arm_deg=(43.5, 46.5), knee_dz=0.008, shoulder_dz=0.006),
}


# --- the skeleton -------------------------------------------------------------------------------------------
def body_spec(name: str, seed: int) -> dict:
    s = dict(STANDARD, **CAST[name])
    rng = random.Random(f"{name}:{seed}")
    for k in ("leg", "torso", "girth", "limb", "arm", "head"):
        s[k] = round(s[k] * (1 + rng.uniform(-0.02, 0.02)), 4)
    s["name"], s["seed"] = name, seed
    return s


def skeleton(s: dict) -> dict:
    """The joints (left side; the right mirrors with the asymmetry), metres before `scale`."""
    leg, tor, arm = s["leg"], s["torso"], s["arm"]
    ankle_z = 0.085 * s["foot"]
    hip_z = ankle_z + 0.795 * leg
    knee_z = ankle_z + 0.395 * leg
    hip_x = 0.10 * max(s["girth"], 0.9)
    j = {"hip": (hip_x, 0.0, hip_z), "knee": (hip_x + 0.01, -0.01, knee_z), "ankle": (hip_x + 0.015, 0.015, ankle_z)}
    f = s["foot"]
    j["ball"] = (j["ankle"][0] + 0.005, -0.09 * f, 0.03 * f)
    j["toe_end"] = (j["ankle"][0] + 0.005, -0.16 * f, 0.03 * f)
    j["heel_end"] = (j["ankle"][0], 0.06 * f, 0.02 * f)
    pelvis_z = hip_z + 0.05 * tor
    shoulder_z = pelvis_z + 0.46 * tor
    sh_x = 0.10 + 0.08 * s["girth"]
    j["shoulder"] = (sh_x, 0.0, shoulder_z)
    j["clav"] = (0.10 * s["girth"], 0.0, shoulder_z - 0.03)
    j["neck_base"] = (0.0, 0.0, shoulder_z + 0.01)
    j["head_base"] = (0.0, 0.0, shoulder_z + 0.01 + 0.10 * s["neck"])
    j["pelvis_c"] = (0.0, 0.0, pelvis_z)
    j["belly_c"] = (0.0, 0.0, pelvis_z + 0.19 * tor)
    j["chest_c"] = (0.0, 0.0, pelvis_z + 0.35 * tor)
    return j


def arm_dir(deg):
    """The left arm's direction, `deg` below horizontal."""
    c, si = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([c, 0.0, -si])


# --- building -----------------------------------------------------------------------------------------------
SURFACE = 0.574      # a metaball's surface sits at this fraction of its radius (threshold 0.6, stiffness 2)


class Balls:
    """Metaballs sized by their surface: a capsule's radius and an ellipsoid's semi-axes are where the skin lands."""

    def __init__(self, name, resolution):
        import bpy
        self.mb = bpy.data.metaballs.new(f"{name}_mb")
        self.mb.resolution = self.mb.render_resolution = resolution
        self.mb.threshold = 0.6
        self.obj = bpy.data.objects.new(f"{name}_mb", self.mb)
        bpy.context.scene.collection.objects.link(self.obj)

    def capsule(self, a, b, r):
        from mathutils import Vector
        a, b = Vector(tuple(a)), Vector(tuple(b))
        el = self.mb.elements.new(type='CAPSULE')
        el.co = (a + b) / 2
        el.radius = r / SURFACE
        el.size_x = max((b - a).length / 2, 1e-4)
        el.rotation = Vector((1, 0, 0)).rotation_difference((b - a).normalized())

    def ellipsoid(self, c, sx, sy, sz, d=None):
        from mathutils import Vector
        el = self.mb.elements.new(type='ELLIPSOID')
        el.co = tuple(c)
        el.radius = 1.0
        el.size_x, el.size_y, el.size_z = sx / SURFACE, sy / SURFACE, sz / SURFACE
        if d is not None:
            el.rotation = Vector((1, 0, 0)).rotation_difference(Vector(tuple(d)))

    def to_mesh(self, name):
        import bpy
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        mesh = bpy.data.meshes.new_from_object(self.obj.evaluated_get(dg))
        mesh.name = name
        bpy.data.objects.remove(self.obj, do_unlink=True)
        bpy.data.metaballs.remove(self.mb)
        body = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(body)
        return body


def hand_axes(d, side):
    """(along, across toward the little finger, back of the hand) for a hand hanging along d."""
    along = d / np.linalg.norm(d)
    across = np.array([0.0, 1.0, 0.0])               # index in front (-Y), little behind
    across = across - (across @ along) * along
    across /= np.linalg.norm(across)
    back = np.cross(along, across) * side
    if back[0] * side < 0:
        back = -back
    return along, across, back


def build_hand(b: Balls, wrist, d, side, hands, limb):
    """Palm and fingers (or a mitten) from the wrist along d; returns the true finger joints (base -> tip end)."""
    along, across, back = hand_axes(d, side)
    r = 0.0065 * limb ** 0.25
    joints = {}
    if hands == "mitten":
        b.ellipsoid(wrist + along * 0.08, 0.085, 0.045, 0.022 * limb ** 0.5, d=along)
        return joints
    b.capsule(wrist - along * 0.01, wrist + along * 0.03, 0.03 * limb ** 0.5)
    b.ellipsoid(wrist + along * 0.05, 0.05, 0.042, 0.017 * limb ** 0.5, d=along)
    lanes = {"index": -0.0345, "middle": -0.0115, "ring": 0.0115, "little": 0.0345}
    lengths = {"index": (0.042, 0.026, 0.020), "middle": (0.046, 0.029, 0.022), "ring": (0.043, 0.027, 0.020),
               "little": (0.034, 0.021, 0.016)}
    for f, lane in lanes.items():
        p = wrist + along * (0.092 - 0.006 * abs(lane) / 0.0115) + across * lane
        pts = [p]
        for seg in lengths[f]:
            pts.append(pts[-1] + along * seg)
        for a, c in zip(pts, pts[1:]):
            b.capsule(a, c, r)
        joints[f] = pts
    t0 = wrist + along * 0.02 - across * 0.024 - back * 0.008
    tdir = along * 0.6 - across * 0.75 - back * 0.25
    tdir /= np.linalg.norm(tdir)
    tp = [t0, t0 + tdir * 0.035, t0 + tdir * 0.063, t0 + tdir * 0.085]
    for a, c in zip(tp, tp[1:]):
        b.capsule(a, c, r * 1.1)
    joints["thumb"] = tp
    return joints


def build_body(s: dict, resolution=0.006, with_hair=True):
    """(mesh object, true joints, finger joints, the skull's top or None) for a body spec, metres x `scale`."""
    import bpy  # noqa: F401
    j = skeleton(s)
    g, lm, hd = s["girth"], s["limb"], s["head"]
    skull_top = None
    if s["hair"] and with_hair:      # the skull's top, before the hair (metaballs of one name fuse: build it apart)
        body0, *_ = build_body(dict(s, hair=False, name=s["name"] + "Skull"), resolution, with_hair=False)
        V0, _ = _arrays(body0)
        skull_top = V0[np.argmax(V0[:, 2])].copy()
        _remove(body0)
    b = Balls(s["name"], resolution / s["scale"])
    pz, bz, cz = j["pelvis_c"][2], j["belly_c"][2], j["chest_c"][2]
    t = s["torso"]
    b.ellipsoid((0, 0, pz), 0.16 * g, 0.105 * g, 0.10 * t)
    b.ellipsoid((0, 0.005, bz), 0.135 * g, 0.095 * g, 0.12 * t)
    b.ellipsoid((0, 0, cz), 0.165 * g, 0.105 * g, 0.13 * t)
    b.capsule((0, 0, pz), (0, 0, cz), 0.11 * g)
    nb, hb = np.array(j["neck_base"]), np.array(j["head_base"])
    b.capsule(nb - [0, 0, 0.05], hb + [0, 0, 0.02], 0.05 * max(lm, 0.9) ** 0.5)
    head_c = hb + np.array([0, -0.01, 0.10 * hd])
    b.ellipsoid(head_c, 0.095 * hd, 0.11 * hd, 0.12 * hd)
    b.ellipsoid(hb + np.array([0, -0.055, 0.035]) * hd, 0.045 * hd, 0.045 * hd, 0.035 * hd)
    truth, fingers = {}, {}
    for side, tag in ((1, ".L"), (-1, ".R")):
        def m(p):
            return np.array([side * p[0], p[1], p[2]])
        knee = m(j["knee"]) + ([0, 0, s["knee_dz"]] if side > 0 else 0)
        hip, ankle = m(j["hip"]), m(j["ankle"])
        mid = (hip + knee) / 2
        fl = min(lm, 1.2)
        b.capsule(hip, mid, 0.07 * lm * max(g, 0.85) ** 0.5)
        b.capsule(mid, knee, 0.058 * lm)
        b.capsule(knee, ankle, 0.047 * lm)
        ball, toe, heel = m(j["ball"]), m(j["toe_end"]), m(j["heel_end"])
        b.capsule(ankle, ball, 0.04 * fl)
        b.capsule(ball, toe, 0.035 * fl)
        b.capsule(heel, ankle, 0.038 * fl)
        sh = m(j["shoulder"]) + ([0, 0, s["shoulder_dz"]] if side > 0 else 0)
        deg = s["arm_deg"][0 if side > 0 else 1]
        d = arm_dir(deg) * [side, 1, 1]
        el, wr = sh + d * 0.28 * s["arm"], sh + d * 0.52 * s["arm"]
        b.capsule(m(j["clav"]), sh, 0.06 * lm ** 0.5 * max(g, 0.9) ** 0.5)
        b.capsule(sh, el, 0.045 * lm)
        b.capsule(el, wr, 0.037 * lm)
        fingers[tag] = build_hand(b, wr, d, side, s["hands"], lm)
        truth.update({"hip" + tag: hip, "knee" + tag: knee, "ankle" + tag: ankle, "ball" + tag: ball,
                      "shoulder" + tag: sh, "elbow" + tag: el, "wrist" + tag: wr})
        truth["_dir" + tag] = d
    truth["pelvis"] = (truth["hip.L"] + truth["hip.R"]) / 2
    truth["neck_base"], truth["head_base"] = nb, hb
    if s["skirt"]:                      # a solid flared skirt from the waist to its hem (a fraction of 1.7 m)
        top_z, hem_z = pz + 0.04, s["skirt"] * 1.7
        for k in range(10):
            u = k / 9
            z = top_z + (hem_z + 0.02 - top_z) * u
            b.ellipsoid((0, 0.005, z), (0.15 + 0.07 * u) * g, (0.11 + 0.04 * u) * g, 0.04)
    if s["hair"] and with_hair:         # spikes rooted inside the skull, the middle one highest
        for k in range(7):
            ang = 2 * math.pi * k / 7
            base = head_c + np.array([0.05 * math.cos(ang), 0.05 * math.sin(ang), 0.06]) * hd
            tip = base + np.array([0.05 * math.cos(ang), 0.05 * math.sin(ang), 0.11]) * hd
            b.capsule(base, tip, 0.016 * hd)
        b.capsule(head_c + np.array([0, 0, 0.05]) * hd, head_c + np.array([0, 0.01, 0.21]) * hd, 0.018 * hd)
    body = b.to_mesh(s["name"])
    body.scale = (s["scale"],) * 3
    return body, truth, fingers, skull_top


def _arrays(obj):
    import autorig_blender as A
    return A.mesh_arrays(obj)


def _remove(obj):
    import bpy
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)


def decimate(obj, faces: int) -> None:
    import bpy
    n = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    if n <= faces:
        return
    mod = obj.modifiers.new("exam_decimate", 'DECIMATE')
    mod.ratio = faces / n
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.view_layer.objects:
        o.select_set(o == obj)
    bpy.ops.object.modifier_apply(modifier=mod.name)


def extreme(V, origin, direction, near=None, radius=None):
    """The vertex farthest along `direction` (optionally within `radius` of `near`)."""
    sel = np.ones(len(V), bool) if near is None else np.linalg.norm(V - near, axis=1) < radius
    idx = np.nonzero(sel)[0]
    k = idx[np.argmax((V[idx] - origin) @ direction)]
    return V[k].copy()


def make_truth(name: str, seed: int, faces: int) -> tuple:
    s = body_spec(name, seed)
    body, t, fingers, skull_top = build_body(s)
    decimate(body, faces)
    V, F = _arrays(body)
    k = s["scale"]
    z0 = float(V[:, 2].min())
    shift = np.array([0.0, 0.0, z0])
    lm = {}
    for key, p in t.items():
        if not key.startswith("_"):
            lm[key] = np.asarray(p) * k - shift
    for tag, side in ((".L", 1), (".R", -1)):
        d = t["_dir" + tag]
        wr = lm["wrist" + tag]
        lm["hand_tip" + tag] = extreme(V - shift, wr, d, near=wr + d * 0.1 * k, radius=0.16 * k)
        ank = lm["ankle" + tag]
        foot = (V - shift)
        on = (foot[:, 2] < ank[2]) & (np.sign(foot[:, 0]) == side)
        fv = foot[on]
        lm["toe_tip" + tag] = fv[np.argmin(fv[:, 1])].copy()
        lm["heel" + tag] = fv[np.argmax(fv[:, 1])].copy()
        for f, pts in fingers[tag].items():
            pts = [np.asarray(p) * k - shift for p in pts]
            dd = pts[-1] - pts[-2]
            dd /= np.linalg.norm(dd)
            pts[-1] = extreme(V - shift, pts[-1], dd, near=pts[-1], radius=0.02 * k)
            for i, p in enumerate(pts):
                lm[f"{f}{i}{tag}"] = p
    lm["head_top"] = (np.asarray(skull_top) - shift) if skull_top is not None else (V - shift)[np.argmax(V[:, 2])]
    H = float(np.ptp(V[:, 2]))
    # fingers count as apart only where the built surface parts into four across them (metaballs can fuse them)
    parts = 0 if s["hands"] == "mitten" else finger_parts(V - shift, F, lm)
    separate = 4 if parts == 4 else 0
    doc = {"schema": SCHEMA, "kind": "truth", "name": name, "seed": seed, "height": round(H, 5), "frame": "glb",
           "up": "+Z", "forward": "-Y", "spec": {k2: v for k2, v in s.items() if k2 != "expect_fail"},
           "landmarks": {k2: [round(float(x), 5) for x in v] for k2, v in sorted(lm.items())},
           "fingers": {"separate": separate, "thumb": separate > 0, "parts_across": parts},
           "expect_fail": list(CAST[name].get("expect_fail", [])), "triangles": int(len(F))}
    return body, V - shift, F, doc


def cast(out: str, only, seed: int, faces: int) -> dict:
    import autorig_blender as A
    import mesh_check as M
    os.makedirs(out, exist_ok=True)
    made = {}
    for name in only or CAST:
        if name not in CAST:
            raise ValueError(f"unknown body {name!r}; known {list(CAST)}")
        A.clear_scene()
        body, V, F, doc = make_truth(name, seed, faces)
        glb = os.path.join(out, f"{name}.glb")
        M.write_glb(Path(glb), V, F)
        with open(os.path.join(out, f"{name}.truth.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
        made[name] = {"glb": glb, "height": doc["height"], "triangles": doc["triangles"]}
    return {"tool": "rig_exam_blender", "op": "cast", "seed": seed, "bodies": made, "ok": True}


# --- weight faults --------------------------------------------------------------------------------------------
def _limb_groups(rmap: dict, role: str, side: str, names: set) -> list:
    name = rmap.get(f"{role}.{side}")
    name = name[0] if isinstance(name, list) else name
    if not name:
        return []
    out = [name] + ([name.replace("_stretch", "_twist")] if "_stretch" in name else [])
    return [n for n in out if n in names]


def _mirror_name(n: str) -> str:
    for a, b in ((".l", ".r"), (".L", ".R"), ("_l", "_r"), ("_L", "_R"), ("Left", "Right")):
        if n.endswith(a):
            return n[: -len(a)] + b
        if a in ("Left",) and a in n:
            return n.replace(a, b)
    return n


def weight_matrix(mesh, names):
    W = np.zeros((len(mesh.data.vertices), len(names)))
    col = {g.index: names.index(g.name) for g in mesh.vertex_groups if g.name in names}
    for v in mesh.data.vertices:
        for ge in v.groups:
            if ge.group in col:
                W[v.index, col[ge.group]] = ge.weight
    return W


def write_weights(mesh, names, W, touched):
    for c, n in enumerate(names):
        vg = mesh.vertex_groups.get(n) or mesh.vertex_groups.new(name=n)
        idx = np.nonzero(touched)[0]
        w = W[idx, c]
        zero = idx[w <= 1e-6].tolist()
        if zero:
            vg.remove(zero)
        keep = w > 1e-6
        for value in np.unique(np.round(w[keep], 6)):          # one call per distinct weight
            vg.add(idx[keep][np.isclose(w[keep], value, atol=5e-7)].tolist(), float(value), 'REPLACE')


def apply_fault(rig, mesh, rmap: dict, fault: str, skirt=None) -> dict:
    deform = [b.name for b in rig.data.bones if b.use_deform]
    names = [g.name for g in mesh.vertex_groups if g.name in deform]
    W = weight_matrix(mesh, names)
    V = np.array([mesh.matrix_world @ v.co for v in mesh.data.vertices])
    heads = {b.name: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones}
    touched = np.zeros(len(V), bool)
    info = {"fault": fault}
    if fault == "rigid":
        top = W.argmax(axis=1)
        has = W.max(axis=1) > 0
        W2 = np.zeros_like(W)
        W2[np.arange(len(W)), top] = 1.0
        W = np.where(has[:, None], W2, W)
        touched[:] = has
    elif fault == "leg_smear":
        moved = {}
        for role in ("UpperLeg", "LowerLeg"):
            for n in _limb_groups(rmap, role, "L", set(names)):
                twin = _mirror_name(n)
                if twin not in names:
                    continue
                a, b = names.index(n), names.index(twin)
                share = 0.5 * W[:, a]
                W[:, b] += share
                W[:, a] -= share
                touched |= share > 0
                moved[n] = twin
        info["moved"] = moved
        if not moved:
            raise ValueError("no left-leg groups with a right twin")
    elif fault in ("elbow_blend", "knee_blend"):
        up_role, lo_role, child = (("UpperArm", "LowerArm", "Hand") if fault == "elbow_blend"
                                   else ("UpperLeg", "LowerLeg", "Foot"))
        info["joints"] = {}
        for side in ("L", "R"):
            ups = _limb_groups(rmap, up_role, side, set(names))
            los = _limb_groups(rmap, lo_role, side, set(names))
            if not ups or not los:
                raise ValueError(f"{fault}: no {up_role}/{lo_role}.{side} groups")
            cu = [names.index(n) for n in ups]
            cl = [names.index(n) for n in los]
            jh = heads[rmap[f"{lo_role}.{side}"] if isinstance(rmap[f"{lo_role}.{side}"], str)
                       else rmap[f"{lo_role}.{side}"][0]]
            sh = heads[rmap[f"{up_role}.{side}"] if isinstance(rmap[f"{up_role}.{side}"], str)
                       else rmap[f"{up_role}.{side}"][0]]
            ch_name = rmap.get(f"{child}.{side}")
            ch = heads[ch_name if isinstance(ch_name, str) else ch_name[0]]
            span = min(np.linalg.norm(jh - sh), np.linalg.norm(ch - jh))
            limb = W[:, cu + cl].sum(axis=1)
            sel = (np.linalg.norm(V - jh, axis=1) < 0.6 * span) & (limb > 0.5)
            W[np.ix_(sel, cu + cl)] = 0.0
            W[sel, cu[0]] = 0.5 * limb[sel]
            W[sel, cl[0]] = 0.5 * limb[sel]
            touched |= sel
            info["joints"][side] = {"vertices": int(sel.sum()), "radius": round(float(0.6 * span), 4)}
    elif fault == "skirt_split":
        if not skirt:
            raise ValueError("skirt_split needs --skirt (an arp_markers --body skirt report)")
        import arp_markers
        first = lambda n: n[0] if isinstance(n, list) else n
        cols = {r: names.index(first(rmap[r])) for r in ("Hips", "UpperLeg.L", "UpperLeg.R")
                if first(rmap.get(r)) in names}
        if len(cols) < 3:
            raise ValueError("skirt_split: no Hips or thigh groups")
        sel = arp_markers.skirt_region(V, skirt)
        top, hem = float(skirt["top_z"]), float(skirt["hem_z"])
        u = np.clip((top - V[sel, 2]) / max(top - hem, 1e-6), 0, 1)
        alpha = u * u * (3 - 2 * u)
        left = V[sel, 0] > float(skirt["midline_x"])
        W[sel] = 0.0
        W[sel, cols["Hips"]] = 1 - alpha
        W[sel, cols["UpperLeg.L"]] = np.where(left, alpha, 0.0)
        W[sel, cols["UpperLeg.R"]] = np.where(left, 0.0, alpha)
        touched |= sel
        info["skirt_vertices"] = int(sel.sum())
    elif fault != "none":
        raise ValueError(f"unknown fault {fault!r}; known {list(FAULTS)}")
    if touched.any():
        write_weights(mesh, names, W, touched)
    info["changed_vertices"] = int(touched.sum())
    return info


def weights(fbx, contract, fault, out_blend, skirt_markers=None) -> dict:
    import bpy
    bpy.ops.wm.read_homefile(use_empty=True)
    if not os.path.isfile(fbx):
        raise ValueError(f"no file {fbx}")
    rmap = json.loads(Path(contract).read_text(encoding="utf-8")).get("retarget_map") or {}
    bpy.ops.import_scene.fbx(filepath=fbx)
    rigs = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    if len(rigs) != 1:
        raise ValueError(f"{fbx} holds {len(rigs)} armatures")
    rig = rigs[0]
    meshes = [o for o in bpy.data.objects if o.type == 'MESH' and any(
        m.type == 'ARMATURE' and m.object == rig for m in o.modifiers)]
    if not meshes:
        raise ValueError("no mesh is skinned to the armature")
    mesh = max(meshes, key=lambda o: len(o.data.vertices))
    skirt = json.loads(Path(skirt_markers).read_text(encoding="utf-8")).get("skirt") if skirt_markers else None
    info = apply_fault(rig, mesh, rmap, fault, skirt)
    os.makedirs(os.path.dirname(os.path.abspath(out_blend)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    return {"tool": "rig_exam_blender", "op": "weights", "armature": rig.name, "mesh": mesh.name,
            "blend": out_blend, **info, "ok": True}


def finger_parts(V, F, lm, slab=0.002, gap=0.003) -> int:
    """Parts the left hand's surface falls into across the fingers, in a thin slab through the middle finger's
    second joint, perpendicular to that finger (grounded frame, as the truth); dense samples of the triangles there."""
    import mesh_check as M
    a, b, c = (np.asarray(lm[f"middle{i}.L"], float) for i in (0, 1, 2))
    axis = (c - a) / np.linalg.norm(c - a)
    across = np.array([0.0, 1.0, 0.0]) - axis[1] * axis
    across /= np.linalg.norm(across)
    near = np.linalg.norm(V[F].mean(axis=1) - b, axis=1) < 0.09
    if not near.any():
        return 0
    pts, _ = M.surface_samples(V, F[near], 20000)
    rel = pts - b
    sel = (np.abs(rel @ axis) < slab) & (np.linalg.norm(rel, axis=1) < 0.08)
    v = np.sort(rel[sel] @ across)
    return 0 if not len(v) else int((np.diff(v) > gap).sum() + 1)


# --- selftest -------------------------------------------------------------------------------------------------
def selftest() -> tuple[int, list]:
    import autorig_blender as A
    import arp_markers as AM
    checks, failed = 0, []

    def ok(name, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failed.append(name)
    A.clear_scene()
    with tempfile.TemporaryDirectory() as d:
        rep = cast(d, ["standard", "mitten"], 0, 20000)
        doc = json.load(open(os.path.join(d, "standard.truth.json"), encoding="utf-8"))
        ok("cast: two bodies written", set(rep["bodies"]) == {"standard", "mitten"} and all(
            os.path.getsize(b["glb"]) > 10000 for b in rep["bodies"].values()))
        ok("truth: exam/1 with joints and finger joints", doc["schema"] == SCHEMA and "elbow.L" in doc["landmarks"]
           and "index3.L" in doc["landmarks"] and doc["fingers"]["separate"] == 4)
        lm = {k: np.array(v) for k, v in doc["landmarks"].items()}
        ok("truth: mirrored sides", np.allclose(lm["knee.L"] * [-1, 1, 1], lm["knee.R"], atol=1e-4))
        ok("truth: soles on 0, head on top", abs(min(p[2] for p in lm.values())) < 0.1 and
           lm["head_top"][2] > 0.95 * doc["height"])
        again = json.load(open(os.path.join(d, "standard.truth.json"), encoding="utf-8"))
        A.clear_scene()
        cast(d, ["standard"], 0, 20000)
        again = json.load(open(os.path.join(d, "standard.truth.json"), encoding="utf-8"))
        ok("same seed, same truth", again["landmarks"] == doc["landmarks"])
        import mesh_check as M
        V, F = M.load_mesh(Path(os.path.join(d, "standard.glb")))
        ok("standard: four fingers apart across the middle phalanx", finger_parts(V, F, lm) == 4)
        V2, F2 = M.load_mesh(Path(os.path.join(d, "mitten.glb")))
        mit = {k: np.array(v) for k, v in json.load(open(os.path.join(d, "mitten.truth.json"),
                                                           encoding="utf-8"))["landmarks"].items()}
        ok("mitten: no finger joints in the truth, one part across the hand",
           "index1.L" not in mit and finger_parts(V2, F2, {**mit, **{k: lm[k] for k in ("middle0.L", "middle1.L",
                                                                                     "middle2.L")}}) <= 1)
        opts = {"spine_bones": 3, "fingers": "fixed", "adjust": None, "arm_angle": (30.0, 60.0),
                "arm_ratios": (0.42, 0.75), "symmetry_max": 0.02, "no_window_gate": False}
        # a weight fault on a hand-made skin
        A.clear_scene()
        body, _ = A.build_runner()
        Vb, Fb = A.mesh_arrays(body)
        spec = AM.build_report(Vb, Fb, dict(opts, fingers="fixed"))["contract_bones"]
        import deform_gate as DG
        both = DG.spec_both_sides(spec)
        rig = A.build_armature("ExamRig", both)
        body.parent = rig
        DG.skin(body, rig, both, "good")
        rmap = {b["name"]: b["name"] for b in both}
        W0 = weight_matrix(body, [g.name for g in body.vertex_groups])
        info = apply_fault(rig, body, rmap, "leg_smear")
        W1 = weight_matrix(body, [g.name for g in body.vertex_groups])
        names = [g.name for g in body.vertex_groups]
        ok("leg_smear: moves weight to the right leg", info["changed_vertices"] > 100 and
           W1[:, names.index("UpperLeg.R")].sum() > W0[:, names.index("UpperLeg.R")].sum())
        ok("leg_smear: sums kept", np.allclose(W1.sum(axis=1), W0.sum(axis=1), atol=1e-4))
        info = apply_fault(rig, body, rmap, "elbow_blend")
        W2 = weight_matrix(body, names)
        sel = np.nonzero(W2[:, names.index("LowerArm.L")] > 0)[0]
        ok("elbow_blend: 50/50 at the elbow", info["joints"]["L"]["vertices"] > 20 and np.isclose(
            W2[:, names.index("UpperArm.L")], W2[:, names.index("LowerArm.L")]).sum() > 20)
        info = apply_fault(rig, body, rmap, "rigid")
        W3 = weight_matrix(body, names)
        ok("rigid: one bone per vertex", set(np.unique(np.round(W3[W3 > 0], 4))) <= {1.0})
        try:
            apply_fault(rig, body, rmap, "bogus")
            ok("unknown fault refused", False)
        except ValueError:
            ok("unknown fault refused", True)
    return checks, failed


def parser():
    p = argparse.ArgumentParser(prog="rig_exam_blender.py", description=__doc__.split("\n")[0])
    p.add_argument("op", nargs="?", choices=("cast", "weights"))
    p.add_argument("args", nargs="*")
    p.add_argument("--only")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--faces", type=int, default=40000)
    p.add_argument("--report")
    p.add_argument("--skirt", help="weights skirt_split: the base's arp_markers --body skirt report")
    p.add_argument("--selftest", action="store_true")
    return p


def main() -> None:
    import autorig_blender as A
    argv = A.script_args()

    class P(argparse.ArgumentParser):
        def error(self, message):
            A.finish({"tool": "rig_exam_blender", "ok": False, "error": message}, 1)
    p = parser()
    p.__class__ = P
    a = p.parse_args(argv)
    if a.selftest:
        checks, failed = selftest()
        A.finish({"tool": "rig_exam_blender", "selftest": True, "checks": checks, "failed": failed,
                  "ok": not failed}, 0 if not failed else 1)
    try:
        if a.op == "cast" and len(a.args) == 1:
            rep = cast(a.args[0], a.only.split(",") if a.only else None, a.seed, a.faces)
        elif a.op == "weights" and len(a.args) == 4:
            rep = weights(*a.args, skirt_markers=a.skirt)
        else:
            raise ValueError("usage: cast OUT_DIR | weights FBX CONTRACT FAULT OUT.blend")
    except (ValueError, OSError, KeyError) as exc:
        A.finish({"tool": "rig_exam_blender", "ok": False, "error": str(exc)}, 1, a.report)
    A.finish(rep, 0, a.report)


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
    except ImportError:
        sys.stderr.write("rig_exam_blender.py runs inside Blender: blender -b --factory-startup -P "
                         "rig_exam_blender.py -- ...\n")
        sys.exit(1)
    main()
