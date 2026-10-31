"""test_arp_pipeline.py — markers -> Auto-Rig Pro -> contract -> deform gate on a procedural runner, in Blender.

    Blender --background --python tests/test_arp_pipeline.py [-- <scratch dir>]
    Blender --background --factory-startup --python tests/test_arp_pipeline.py

Uses the user's installed Auto-Rig Pro when it is enabled (run without --factory-startup, which
turns add-ons off). Without it, only the refusal is checked and every case that needs the add-on
prints `SKIP <name>`. Prints `PASS <name>` / `FAIL <name>: <why>` per case; exits 1 when any fails.

With the add-on: arp_markers measures the metaball runner; brt_arp `pipeline` appends the human
preset, sets three spine bones, places the reference bones, matches, binds, limits influences to
4, exports for Unity (humanoid, master trajectory) and writes the skeleton of the re-imported FBX;
contract_map maps it on the contract tier with 30 fingers; deform_gate gates the exported FBX;
brt_arp `export` writes the bound rig again with the same skeleton.
A face: markers with `facial` true and every facial reference of the add-on's head limb (eyes
on, no teeth, tongue or eye targets) plus the ears, placed on the runner's head, with `ref_rolls`
on some finger and face bones: the face and ears are added, every reference lands, the given
rolls are written as they are (.r mirrored), and the export carries the jaw.
Failing cases: two spine bones fail the contract tier (UpperChest missing, exit 2); a bind left at
the add-on's own influence count fails arp.export_max_influences; a reference bone the preset
lacks fails arp.refs_placed and rolls the rig back; markers without a required bone refuse; a
ref_rolls entry for a bone arp_refs does not place refuses; a second run onto the same rig name refuses.
"""
import math
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
SKILLS = os.path.dirname(os.path.dirname(SCRIPTS))
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(SKILLS, "blender-retarget", "scripts"))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import autorig_blender as A  # noqa: E402
import arp_markers as AM  # noqa: E402
import brt_arp as B  # noqa: E402
import deform_gate as D  # noqa: E402

CONTRACT_MAP = os.path.join(SKILLS, "unity-rigged-character", "scripts", "contract_map.py")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
TMP = argv[0] if argv else tempfile.mkdtemp(prefix="autorig_pipeline_")
os.makedirs(TMP, exist_ok=True)
RESULTS = []
OPTS = {"spine_bones": 3, "fingers": "auto", "adjust": None, "arm_angle": (30.0, 60.0),
        "arm_ratios": (0.42, 0.75), "symmetry_max": 0.02, "no_window_gate": False}


def case(name, cond, why=""):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f": {why}"))


def gate(result, name):
    return next((g for g in result.get("gates", []) if g["name"] == name), None)


def runner(name, spine_bones=3):
    body, _ = A.build_runner(name)
    V, F = A.mesh_arrays(body)
    markers = AM.build_report(V, F, dict(OPTS, spine_bones=spine_bones))
    path = os.path.join(TMP, f"{name}.markers.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(markers, handle)
    return body, markers, path


# the head limb's facial references with the face on (eyes, no teeth, tongue or eye targets), .l and
# .x; the pipeline mirrors .l to .r. Plus the ears, a limb of their own.
FACE = ("cheek_inflate_ref.l", "cheek_smile_ref.l", "chin_01_ref.x", "chin_02_ref.x", "eye_offset_ref.l",
        "eyebrow_01_end_ref.l", "eyebrow_01_ref.l", "eyebrow_02_ref.l", "eyebrow_03_ref.l", "eyebrow_full_ref.l",
        "eyelid_bot_01_ref.l", "eyelid_bot_02_ref.l", "eyelid_bot_03_ref.l", "eyelid_bot_ref.l",
        "eyelid_corner_01_ref.l", "eyelid_corner_02_ref.l", "eyelid_top_01_ref.l", "eyelid_top_02_ref.l",
        "eyelid_top_03_ref.l", "eyelid_top_ref.l", "jaw_ref.x", "lips_bot_01_ref.l", "lips_bot_ref.l",
        "lips_bot_ref.x", "lips_corner_mini_ref.l", "lips_roll_bot_ref.x", "lips_roll_top_ref.x",
        "lips_smile_ref.l", "lips_top_01_ref.l", "lips_top_ref.l", "lips_top_ref.x", "nose_01_ref.x",
        "nose_02_ref.x", "nose_03_ref.x", "ear_01_ref.l", "ear_02_ref.l")
FACE_Z = {"eyebrow": 0.35, "eye": 0.2, "nose": 0.05, "cheek": -0.05, "ear": 0.1, "lips": -0.25, "chin": -0.45,
          "jaw": -0.4}


def with_face(markers):
    """The runner's markers with a face on the front of its head and rolls on some bones."""
    lm = markers["landmarks"]
    base, top = Vector(lm["head_base"]), Vector(lm["head_top"])
    r = 0.5 * (top - base).length
    centre = base + 0.5 * (top - base)
    refs, rolls = dict(markers["arp_refs"]), {}
    for i, name in enumerate(FACE):
        side = 0.0 if name.endswith(".x") else 0.35 + 0.04 * (i % 4)
        dz = next(v for k, v in FACE_Z.items() if name.startswith(k)) + 0.015 * (i % 3)
        if name.startswith("ear"):
            head = centre + Vector((0.9 * r, 0.0, dz * r))
        else:
            head = centre + Vector((side * r, -0.8 * r - 0.004 * (i % 5), dz * r))
        tail = head + Vector((0.0, -0.12 * r, 0.03 * r))
        refs[name] = {"head": list(head), "tail": list(tail)}
        rolls[name] = round(-0.9 + 0.3 * (i % 7), 5)
    rolls.update({"index1_ref.l": 0.9, "thumb1_ref.l": -2.9, "hand_ref.l": 0.61})
    return dict(markers, arp_refs=refs, ref_rolls=rolls, facial=True)


def roll_misses(rig, markers) -> dict:
    """Degrees between each rolled reference's Z axis and the one its given roll (.r: mirrored) asks for."""
    out = {}
    mw = rig.matrix_world.to_3x3()
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        bones = rig.data.edit_bones
        for name, roll in markers["ref_rolls"].items():
            ends = markers["arp_refs"][name]
            d = (Vector(ends["tail"]) - Vector(ends["head"])).normalized()
            z = bpy.types.Bone.MatrixFromAxisRoll(d, roll).col[2]
            out[name] = math.degrees((mw @ bones[name].z_axis).angle(z, 0.0))
            if name.endswith(".l"):
                twin = name[:-2] + ".r"
                zr = Vector((-z.x, z.y, z.z))                 # mirrored across X
                out[twin] = math.degrees((mw @ bones[twin].z_axis).angle(zr, 0.0))
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
    return out


def contract(skeleton, *extra):
    report = os.path.join(TMP, os.path.basename(skeleton) + ".map.json")
    proc = subprocess.run([sys.executable, CONTRACT_MAP, "map", skeleton, "--map", "arp", "--out", report,
                           *extra], capture_output=True, text=True)
    with open(report, encoding="utf-8") as handle:
        return proc.returncode, json.load(handle), report


A.clear_scene()
probe = B.run({"op": "probe"})
if not probe["addon_present"]:
    body, _, path = runner("RunnerA")
    r = B.run({"op": "pipeline", "mesh": body.name, "markers": path, "fbx": os.path.join(TMP, "a.fbx")})
    case("no add-on: pipeline refuses addon_missing", not r["ok"] and r.get("reason") == "addon_missing", r.get("reason"))
    for name in ("pipeline on the runner", "contract tier", "deform gate on the export", "export op",
                 "two spine bones", "facial references", "given rolls", "ref_rolls for an unplaced bone",
                 "influences not limited", "unknown reference bone", "markers missing a bone",
                 "rig name taken"):
        print(f"SKIP {name}: Auto-Rig Pro is not enabled in this Blender")
else:
    print(f"Auto-Rig Pro {probe['version']} as {probe['module']}, Blender {'.'.join(map(str, bpy.app.version))}")
    body, markers, path = runner("RunnerA")
    fbx = os.path.join(TMP, "runner_a.fbx")
    r = B.run({"op": "pipeline", "mesh": body.name, "markers": path, "fbx": fbx})
    case("pipeline on the runner: ok", r["ok"], [g for g in r["gates"] if not g["pass"]] or r.get("reason"))
    case("pipeline: licence on the record", r["record"].get("licence", {}).get("source") == "auto-rig-pro")
    case("pipeline: influences limited to 4", (gate(r, "arp.export_max_influences") or {}).get("value", 99) <= 4)
    if r.get("skeleton"):
        code, rep, map_report = contract(r["skeleton"], "--require", "contract", "--min-fingers", "30")
        case("contract tier: exit 0, 53 bones, 30 fingers", code == 0 and rep["mapped"] == 53 and
             rep["fingers_mapped"] == 30, (code, rep.get("missing_optional"), [g for g in rep["gates"] if not g["pass"]]))
        case("contract tier: Root is c_traj and non-deform",
             rep["retarget_map"].get("Root") == "c_traj" and
             not next(b for b in json.load(open(r["skeleton"]))["bones"] if b["name"] == "c_traj")["deform"])
        args = D.parser().parse_args(["--fbx", fbx, "--map", map_report, "--render", os.path.join(TMP, "poses")])
        dcode, drep = D.run(args)
        print("deform gate:", json.dumps({g["name"]: g["value"] for g in drep.get("gates", [])}),
              json.dumps(drep.get("volume_loss_max")), json.dumps(drep.get("self_intersection")))
        case("deform gate on the export: measured, exit 0 or 2", dcode in (0, 2) and len(drep.get("poses", {})) == 6,
             drep.get("error"))
        again = os.path.join(TMP, "runner_a_again.fbx")
        rx = B.run({"op": "export", "armature": r["armature"], "fbx": again})
        names = lambda path: [b["name"] for b in json.load(open(path))["bones"]]  # noqa: E731
        case("export op re-exports the bound rig: ok, licence, the same skeleton",
             rx["ok"] and rx["record"].get("licence", {}).get("source") == "auto-rig-pro"
             and rx.get("skeleton") and names(rx["skeleton"]) == names(r["skeleton"]),
             [g for g in rx.get("gates", []) if not g["pass"]] or rx.get("reason"))
    body2, _, path2 = runner("RunnerB", spine_bones=2)
    r2 = B.run({"op": "pipeline", "mesh": body2.name, "markers": path2, "fbx": os.path.join(TMP, "runner_b.fbx")})
    if r2.get("skeleton"):
        code, rep, _ = contract(r2["skeleton"], "--require", "contract")
        case("two spine bones: contract tier fails, UpperChest missing", code == 2 and "UpperChest" in
             next(g for g in rep["gates"] if g["name"] == "contract").get("missing", []), code)
        code, rep, _ = contract(r2["skeleton"], "--require", "unity")
        case("two spine bones: Unity tier still passes", code == 0, code)
    else:
        case("two spine bones: pipeline ran", False, r2.get("reason") or r2.get("stopped_at"))
    bodyf, markersf, _ = runner("RunnerF")
    markersf = with_face(markersf)
    rf = B.run({"op": "pipeline", "mesh": bodyf.name, "markers": markersf, "fbx": os.path.join(TMP, "runner_f.fbx")})
    rig_f = bpy.data.objects.get(rf.get("armature") or "")
    names_f = {b.name for b in rig_f.data.bones} if rig_f else set()
    face_all = {n for n in FACE} | {n[:-2] + ".r" for n in FACE if n.endswith(".l")}
    skel_f = [b for b in json.load(open(rf["skeleton"]))["bones"]] if rf.get("skeleton") else []
    jaw = [b["name"] for b in skel_f if "jaw" in b["name"].lower() and b.get("deform")]
    print("face:", json.dumps({"face_refs_added": rf.get("face_refs_added"), "refs": rf.get("refs"),
                               "jaw_deform": jaw, "warnings": rf.get("warnings")}))
    case("facial references: pipeline ok, face and ears added, all 58+4 placed, none left unplaced, jaw deforms",
         rf["ok"] and (gate(rf, "arp.face_added") or {}).get("pass") and face_all <= names_f
         and not any("which the markers do not place" in w for w in rf.get("warnings", [])) and jaw,
         [g for g in rf.get("gates", []) if not g["pass"]] or rf.get("reason") or rf.get("warnings"))
    misses = roll_misses(rig_f, markersf) if rig_f else {}
    worst = max(misses.values(), default=99.0)
    case("given rolls: written as given, .r mirrored, within 0.1 degrees after the match",
         rig_f is not None and len(misses) > len(markersf["ref_rolls"]) and worst <= 0.1
         and rf.get("refs", {}).get("rolls_given", 0) == len(misses),
         sorted(misses.items(), key=lambda kv: -kv[1])[:4])
    odd = dict(markersf, ref_rolls={"tail_00_ref.x": 0.5})
    rr = B.run({"op": "pipeline", "mesh": bodyf.name, "markers": odd, "fbx": os.path.join(TMP, "g.fbx"),
                "armature": "RunnerGRig"})
    case("ref_rolls for a bone arp_refs does not place: refused", rr.get("reason") == "markers_invalid", rr.get("reason"))
    body4, _, path4 = runner("RunnerD")
    r6 = B.run({"op": "pipeline", "mesh": body4.name, "markers": path4, "fbx": os.path.join(TMP, "runner_d.fbx"),
                "limit_influences": False})
    most = gate(r6, "arp.export_max_influences")
    case("influences not limited: export_max_influences fails", most is not None and not most["pass"]
         and not r6["ok"], most)
    body3, markers3, _ = runner("RunnerC")
    markers3["arp_refs"]["tail_00_ref.x"] = {"head": [0, 0.1, 1.0], "tail": [0, 0.2, 0.9]}
    r3 = B.run({"op": "pipeline", "mesh": body3.name, "markers": markers3, "fbx": os.path.join(TMP, "c.fbx")})
    placed = gate(r3, "arp.refs_placed")
    case("unknown reference bone: refs_placed fails, rig rolled back",
         not r3["ok"] and placed is not None and not placed["pass"] and bpy.data.objects.get("RunnerCRig") is None,
         (placed, r3.get("stopped_at")))
    bad = dict(markers3, arp_refs={k: v for k, v in markers3["arp_refs"].items() if k != "hand_ref.l"})
    r4 = B.run({"op": "pipeline", "mesh": body3.name, "markers": bad, "fbx": os.path.join(TMP, "d.fbx")})
    case("markers missing hand_ref.l: refused", r4.get("reason") == "markers_invalid", r4.get("reason"))
    r5 = B.run({"op": "pipeline", "mesh": body3.name, "markers": markers, "fbx": os.path.join(TMP, "e.fbx"),
                "armature": "RunnerARig"})
    case("rig name taken: refused", r5.get("reason") == "rig_exists", r5.get("reason"))

print(f"{sum(RESULTS)}/{len(RESULTS)} passed")
sys.exit(0 if all(RESULTS) else 1)
