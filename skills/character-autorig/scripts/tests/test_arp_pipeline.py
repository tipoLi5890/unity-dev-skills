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
Failing cases: two spine bones fail the contract tier (UpperChest missing, exit 2); a bind left at
the add-on's own influence count fails arp.export_max_influences; a reference bone the preset
lacks fails arp.refs_placed and rolls the rig back; markers without a required bone refuse; a
second run onto the same rig name refuses.
"""
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
                 "two spine bones",
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
