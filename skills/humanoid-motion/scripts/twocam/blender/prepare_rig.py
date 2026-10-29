"""prepare_rig.py — make a rigged contract character ready for the two cameras: rig_info.json, limb paint, twocam.blend.

Replaces the rig-writing half of patch-gg/anymove's blender/build_rig.py (write_rig_info, paint_legs, the save),
commit 7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0. Upstream built the armature from a
hand-written rig.json; here the character is already rigged (character-autorig or the hand-built route) on the
humanoid contract, so this reads its armature: every body bone's rest matrix with its roll, parent, head and tail,
mapped to the contract by name or by a role map, and hands them to ../skeleton.py, which adds the keypoints, feet,
limits in each bone's anatomical frame, limb pairs and paint groups. The limbs are painted from the contract's
left and right arms and legs. Fingers are not solved and Root stays at rest.

usage:
    Blender -b --factory-startup -P prepare_rig.py -- RIGGED.blend OUT_DIR [--rig NAME] [--body NAME]
            [--map ROLE_MAP.json] [--character CHARACTER.json] [--height 1.7]
    Blender -b --factory-startup -P prepare_rig.py -- --selftest
Writes OUT_DIR/rig_info.json and OUT_DIR/twocam.blend (the painted copy the dataset, reference and capture renders
use; RIGGED.blend is not changed). The layout is the character.json "layout", else the 1376 x 768 humanoid frame
scaled to the mesh's height.
Prints one line `TWOCAM_JSON {...}`. Gates: rig.at_origin (the armature object has an identity transform, so armature
space is world space), body.skinned (the mesh has an Armature modifier on the rig), rig.required_bones, rig.sides,
rig.upright (from skeleton.py), rig.paint (every limb has painted vertices).
Exit codes: 0 every gate passed (or the selftest passed), 2 a gate failed (nothing written), 1 an error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

if __name__ == "__main__" and globals().get("__file__"):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import bcommon as B  # noqa: E402
from layout import Layout  # noqa: E402
from skeleton import build_rig_info  # noqa: E402


def find_objects(rig_name=None, body_name=None):
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    rig = bpy.data.objects.get(rig_name) if rig_name else (arms[0] if len(arms) == 1 else None)
    if rig is None or rig.type != "ARMATURE":
        raise ValueError(f"armature: name it with --rig (found {[o.name for o in arms]})")
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and
              any(m.type == "ARMATURE" and m.object == rig for m in o.modifiers)]
    if body_name:
        body = bpy.data.objects.get(body_name)
    else:
        body = max(meshes, key=lambda o: len(o.data.vertices)) if meshes else None
    if body is None or body.type != "MESH":
        raise ValueError(f"body mesh: name it with --body (skinned to {rig.name}: {[o.name for o in meshes]})")
    return rig, body


def dump(rig) -> dict:
    return {b.name: {"parent": b.parent.name if b.parent else None, "head": np.array(b.head_local),
                     "tail": np.array(b.tail_local), "matrix_local": [list(r) for r in b.matrix_local]}
            for b in rig.data.bones}


def prepare(p: dict) -> tuple:
    if p.get("blend"):
        bpy.ops.wm.open_mainfile(filepath=p["blend"])
    rig, body = find_objects(p.get("rig"), p.get("body"))
    role = None
    if p.get("map"):
        with open(p["map"], encoding="utf-8") as f:
            role = json.load(f).get("bones")
    mw = np.array(rig.matrix_world)
    gates = [B.gate("rig.at_origin", float(np.abs(mw - np.eye(4)).max()), "identity within 1e-5",
                    np.abs(mw - np.eye(4)).max() < 1e-5),
             B.gate("body.skinned", body.name, f"Armature modifier on {rig.name}",
                    any(m.type == "ARMATURE" and m.object == rig for m in body.modifiers))]
    character = {}
    if p.get("character"):
        with open(p["character"], encoding="utf-8") as f:
            character = json.load(f)
    if "layout" in character:
        L = Layout.from_dict(character["layout"])
    else:
        top = p.get("height") or max((body.matrix_world @ v.co).z for v in body.data.vertices)
        L = Layout.humanoid(float(top))
    info, g2 = build_rig_info(dump(rig), role, L.as_dict())
    gates += g2
    out = {"rig": rig.name, "body": body.name, "layout": L.as_dict()}
    if info is None or not all(g["pass"] for g in gates):
        return B.report("prepare_rig.py", p, gates, **out), 2
    info["twocam"]["objects"] = {"rig": rig.name, "body": body.name}
    painted = B.paint_limbs(body, info["twocam"]["paint"])
    gates.append(B.gate("rig.paint", painted, "> 0 vertices per limb", all(v > 0 for v in painted.values())))
    out.update({"painted": painted, "bones": len(info["bones"]), "keypoints": len(info["keypoints"])})
    if not all(g["pass"] for g in gates):
        return B.report("prepare_rig.py", p, gates, **out), 2
    os.makedirs(p["out_dir"], exist_ok=True)
    ri = os.path.join(p["out_dir"], "rig_info.json")
    with open(ri, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1)
    blend = os.path.join(p["out_dir"], "twocam.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, copy=True)
    out.update({"rig_info": ri, "blend": blend})
    return B.report("prepare_rig.py", p, gates, **out), 0


def selftest() -> tuple:
    checks = []
    with tempfile.TemporaryDirectory() as td:
        rig, body = B.demo_scene()
        r, code = prepare({"out_dir": td})
        checks.append({"name": "demo contract character passes, exit 0", "pass": code == 0 and r["ok"]})
        info = B.load_info(os.path.join(td, "rig_info.json")) if code == 0 else {"bones": []}
        bone_ok = True
        for bi in info["bones"]:   # the roll Blender stored is the one written
            bone_ok &= np.allclose(bi["matrix_local"], [list(x) for x in rig.data.bones[bi["name"]].matrix_local], atol=1e-6)
        checks.append({"name": "rest matrices read from Blender", "pass": bool(info["bones"]) and bone_ok})
        checks.append({"name": "every limb painted", "pass": code == 0 and all(v > 0 for v in r["painted"].values())})
        checks.append({"name": "twocam.blend written", "pass": os.path.exists(os.path.join(td, "twocam.blend"))})
        bpy.ops.mesh.primitive_cube_add(size=0.2)
        loose = bpy.context.object
        r, code = prepare({"out_dir": os.path.join(td, "s"), "body": loose.name})
        checks.append({"name": "a mesh without the Armature modifier fails body.skinned, exit 2",
                       "pass": code == 2 and not r["gates"][1]["pass"]})
        bpy.data.objects.remove(loose)
        rig.location.x = 0.5
        bpy.context.view_layer.update()
        r, code = prepare({"out_dir": os.path.join(td, "b")})
        checks.append({"name": "a moved armature object fails rig.at_origin, exit 2",
                       "pass": code == 2 and not r["gates"][0]["pass"]})
        rig.location.x = 0
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode="EDIT")
        rig.data.edit_bones.remove(rig.data.edit_bones["Toes.L"])
        bpy.ops.object.mode_set(mode="OBJECT")
        r, code = prepare({"out_dir": os.path.join(td, "c")})
        checks.append({"name": "a missing Toes.L fails rig.required_bones, exit 2",
                       "pass": code == 2 and not next(g for g in r["gates"] if g["name"] == "rig.required_bones")["pass"]})
        B.demo_scene()
        for vg in list(bpy.data.objects["body"].vertex_groups):
            if vg.name.endswith(".R") and vg.name.startswith(("UpperLeg", "LowerLeg", "Foot", "Toes")):
                bpy.data.objects["body"].vertex_groups.remove(vg)
        r, code = prepare({"out_dir": os.path.join(td, "d")})
        checks.append({"name": "an unweighted right leg fails rig.paint, exit 2",
                       "pass": code == 2 and not next(g for g in r["gates"] if g["name"] == "rig.paint")["pass"]})
    ok = all(c["pass"] for c in checks)
    return {"tool": "prepare_rig.py", "selftest": "pass" if ok else "fail", "checks": len(checks),
            "failed": [c["name"] for c in checks if not c["pass"]]}, 0 if ok else 1


def main():
    args = B.script_args()
    if "--selftest" in args:
        return selftest()
    ap = argparse.ArgumentParser(prog="prepare_rig.py")
    ap.add_argument("blend"); ap.add_argument("out_dir")
    ap.add_argument("--rig"); ap.add_argument("--body"); ap.add_argument("--map"); ap.add_argument("--character")
    ap.add_argument("--height", type=float)
    a = ap.parse_args(args)
    return prepare(vars(a))


if __name__ == "__main__":
    B.guarded(main)
