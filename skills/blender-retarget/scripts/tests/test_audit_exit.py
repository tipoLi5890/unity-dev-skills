"""test_audit_exit.py — brt_audit's exit codes and what it counts, run in Blender.

    Blender --background --factory-startup --python tests/test_audit_exit.py

Prints `PASS <name>` or `FAIL <name>: <why>` per case and exits 1 when any case
fails. Saves a small library file ("RunnerRig", two library clips, one test take
that is no library action, "Mallet" on Hand.R) to a temporary folder and audits
it in a second Blender process:

- `--expect '{}'`, no `--expect`, and an `--expect` that is no JSON object exit 2;
- `actions` counts the two library clips, not the test take, which is listed
  in `unregistered_actions`: exit 0;
- a wrong count, and a prop on the wrong bone (`audit.props_parented`), exit 1;
- there is no `audit.exit_code` gate.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)

import brt_common as C  # noqa: E402
import brt_library as L  # noqa: E402

RESULTS: list[bool] = []
TMP = tempfile.mkdtemp(prefix="brt_audit_test_")
BLEND = os.path.join(TMP, "RunnerLibrary.blend")


def check(name, fn):
    try:
        fn()
    except Exception as exc:          # a failed assert or anything else: report and go on
        print(f"FAIL {name}: {type(exc).__name__}: {exc}", flush=True)
        RESULTS.append(False)
    else:
        print(f"PASS {name}", flush=True)
        RESULTS.append(True)


def build():
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    scene = bpy.context.scene
    arm = bpy.data.armatures.new("RunnerRig")
    rig = bpy.data.objects.new("RunnerRig", arm)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    for name, head, tail, parent in (("Spine", (0, 0, 0.6), (0, 0, 0.9), None),
                                     ("Hand.R", (-0.2, 0, 0.9), (-0.35, 0, 0.9), "Spine")):
        bone = arm.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        if parent:
            bone.parent = arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.update()

    pb = rig.pose.bones["Hand.R"]
    pb.rotation_mode = 'QUATERNION'
    for name in ("RunnerIdle", "Runner_HurdleVault", "TestTake"):
        action = bpy.data.actions.new(name)
        C.assign_slot(rig, action)
        for frame, w in ((1, 1.0), (12, 0.9)):
            pb.rotation_quaternion = (w, (1 - w * w) ** 0.5, 0, 0)
            pb.keyframe_insert("rotation_quaternion", frame=frame)
        rig.animation_data.action = None
        action.use_fake_user = True
    pb.rotation_quaternion = (1, 0, 0, 0)

    mallet = bpy.data.objects.new("Mallet", None)
    scene.collection.objects.link(mallet)
    mallet.parent, mallet.parent_type, mallet.parent_bone = rig, 'BONE', "Hand.R"

    r = L.run({"armature": "RunnerRig", "actions": ["RunnerIdle", "Runner_HurdleVault"]})
    assert r["ok"], r["gates"]
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)


def audit(*args) -> tuple[int, dict]:
    cmd = [bpy.app.binary_path, "--background", BLEND, "--factory-startup",
           "--python", os.path.join(SCRIPTS, "brt_audit.py"), "--", *args]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    line = next((x for x in done.stdout.splitlines() if x.startswith("BRT_AUDIT_JSON ")), None)
    assert line is not None, done.stdout[-2000:] + done.stderr[-2000:]
    return done.returncode, json.loads(line[len("BRT_AUDIT_JSON "):])


PROP_OK = json.dumps([{"object": "Mallet", "parent": "RunnerRig", "parent_bone": "Hand.R"}])
PROP_BAD = json.dumps([{"object": "Mallet", "parent": "RunnerRig", "parent_bone": "Spine"}])


def main() -> int:
    build()

    def empty_expect_exits_2():
        for args in (("--expect", "{}"), (), ("--expect", "[1, 2]"), ("--expect", "{not json")):
            code, result = audit(*args)
            assert code == 2 and result["ok"] is False, (args, code, result)

    def library_actions_only():
        code, result = audit("--expect", json.dumps({"actions": 2, "unregistered_actions_include": ["TestTake"],
                                                     "finite": True}), "--props", PROP_OK)
        assert code == 0, (code, result.get("gates"), result.get("error"))
        m = result["metrics"]
        assert m["library_actions"] == ["RunnerIdle", "Runner_HurdleVault"], m["library_actions"]
        assert m["actions_in_file"] == 3, m["actions_in_file"]
        names = [g["name"] for g in result["gates"]]
        assert names == ["audit.expect_matches", "audit.props_parented"], names

    def wrong_count_exits_1():
        code, result = audit("--expect", json.dumps({"actions": 3}))
        assert code == 1 and not result["ok"], (code, result.get("gates"))

    def wrong_parent_bone_exits_1():
        code, result = audit("--expect", json.dumps({"actions": 2}), "--props", PROP_BAD)
        failing = [g["name"] for g in result["gates"] if not g["pass"]]
        assert code == 1 and failing == ["audit.props_parented"], (code, failing)

    check("empty_expect_exits_2", empty_expect_exits_2)
    check("library_actions_only", library_actions_only)
    check("wrong_count_exits_1", wrong_count_exits_1)
    check("wrong_parent_bone_exits_1", wrong_parent_bone_exits_1)
    print(f"test_audit_exit: {sum(RESULTS)}/{len(RESULTS)} passed", flush=True)
    return 0 if RESULTS and all(RESULTS) else 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        print(f"FAIL setup: {type(exc).__name__}: {exc}", flush=True)
        code = 1
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
