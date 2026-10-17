"""test_library_resolve.py — which action brt_library catalogs, run in Blender.

    Blender --background --factory-startup --python tests/test_library_resolve.py

Prints `PASS <name>` or `FAIL <name>: <why>` per case and exits 1 when any case
fails. On a "RunnerRig" with clips keyed through its slot:

- a library holding a `.NNN` name passes its gates and says so in `warnings`;
- a name that is no action resolves through the `brt_source_file` property,
  and two actions carrying the same value are an error;
- a manifest entry resolves through its `action` field, else its `file`
  against the property;
- the rig's `brt_library` property lists the registered actions;
- with `provenance_key: "brt_clip"`, a clip name resolves to the stamped
  `.001` take, and a stale unstamped take of that exact name beside it is an
  error, never picked; with the default key a clip name matches nothing.
"""
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import brt_common as C  # noqa: E402
import brt_library as L  # noqa: E402

RESULTS: list[bool] = []


def check(name, fn):
    try:
        fn()
    except Exception as exc:          # a failed assert or anything else: report and go on
        print(f"FAIL {name}: {type(exc).__name__}: {exc}", flush=True)
        RESULTS.append(False)
    else:
        print(f"PASS {name}", flush=True)
        RESULTS.append(True)


def build_rig():
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    arm = bpy.data.armatures.new("RunnerRig")
    rig = bpy.data.objects.new("RunnerRig", arm)
    bpy.context.scene.collection.objects.link(rig)
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
    return rig


def clip(rig, name: str, source_file: str | None = None):
    """An action keyed on Hand.R through the rig's slot, then unassigned."""
    action = bpy.data.actions.new(name)
    C.assign_slot(rig, action)
    pb = rig.pose.bones["Hand.R"]
    pb.rotation_mode = 'QUATERNION'
    for frame, w in ((1, 1.0), (12, 0.9)):
        pb.rotation_quaternion = (w, (1 - w * w) ** 0.5, 0, 0)
        pb.keyframe_insert("rotation_quaternion", frame=frame)
    pb.rotation_quaternion = (1, 0, 0, 0)
    rig.animation_data.action = None
    action.use_fake_user = True
    if source_file:
        action["brt_source_file"] = source_file
    return action


def main() -> int:
    rig = build_rig()
    clip(rig, "RunnerIdle", "/clips/stock/RunnerIdle.fbx")
    clip(rig, "Runner_JogLaneLeft", "/clips/stock/JogLaneLeft.fbx")
    clip(rig, "Runner_GateLatchSwing.001", "/clips/pack/no_root/GateLatchSwing.fbx")

    def suffix_is_a_warning():
        r = L.run({"armature": "RunnerRig", "actions": ["RunnerIdle", "Runner_GateLatchSwing.001"]})
        assert r["ok"], r["gates"]
        assert "library.no_duplicate_suffix" not in {g["name"] for g in r["gates"]}, r["gates"]
        assert r["duplicate_suffixes"] == ["Runner_GateLatchSwing.001"], r["duplicate_suffixes"]
        assert any(".NNN" in w for w in r["warnings"]), r["warnings"]

    def name_resolves_through_property():
        r = L.run({"armature": "RunnerRig", "actions": ["RunnerIdle", "/clips/stock/JogLaneLeft.fbx"]})
        assert r["ok"], r["gates"]
        assert r["resolved"] == {"RunnerIdle": "RunnerIdle",
                                 "/clips/stock/JogLaneLeft.fbx": "Runner_JogLaneLeft"}, r["resolved"]
        assert [e["name"] for e in r["catalog"]] == ["RunnerIdle", "Runner_JogLaneLeft"], r["catalog"]

    def ledger_lists_actions():
        ledger = json.loads(rig["brt_library"])
        assert ledger["Library Review"]["actions"] == ["RunnerIdle", "Runner_JogLaneLeft"], ledger

    def manifest_resolves():
        manifest = [{"name": "JogLaneLeft", "file": "stock/JogLaneLeft.fbx", "action": None},
                    {"name": "GateLatchSwing", "file": "pack/no_root/GateLatchSwing.fbx",
                     "action": "Runner_GateLatchSwing.001"},
                    {"name": "RunnerIdle", "file": "stock/RunnerIdle.fbx", "action": None}]
        r = L.run({"armature": "RunnerRig", "manifest": manifest})
        assert r["ok"], r["gates"]
        assert r["resolved"] == {"JogLaneLeft": "Runner_JogLaneLeft",
                                 "GateLatchSwing": "Runner_GateLatchSwing.001",
                                 "RunnerIdle": "RunnerIdle"}, r["resolved"]

    def ambiguous_property_raises():
        clip(rig, "Runner_JogLaneLeft.001", "/clips/stock/JogLaneLeft.fbx")   # a rerun of the batch
        try:
            L.run({"armature": "RunnerRig", "manifest": [{"name": "JogLaneLeft",
                                                          "file": "stock/JogLaneLeft.fbx"}]})
        except RuntimeError as exc:
            assert "2 actions match" in str(exc), str(exc)
            return
        raise AssertionError("two actions with one brt_source_file did not raise")

    def stale_take_never_wins():
        stamped = clip(rig, "HurdleVault.001", "/clips/stock/HurdleVault.fbx")
        stamped["brt_clip"] = "HurdleVault"
        r = L.run({"armature": "RunnerRig", "actions": ["HurdleVault"], "provenance_key": "brt_clip"})
        assert r["ok"] and r["resolved"] == {"HurdleVault": "HurdleVault.001"}, r["resolved"]
        clip(rig, "HurdleVault")                     # a stale test take, no property
        try:
            L.run({"armature": "RunnerRig", "actions": ["HurdleVault"], "provenance_key": "brt_clip"})
        except RuntimeError as exc:
            assert "HurdleVault.001" in str(exc) and "stale" in str(exc), str(exc)
        else:
            raise AssertionError("the stale same-name take was picked")
        bpy.data.actions.remove(bpy.data.actions["HurdleVault"])
        try:
            L.run({"armature": "RunnerRig", "actions": ["HurdleVault"]})
        except RuntimeError as exc:
            assert "brt_source_file" in str(exc), str(exc)
        else:
            raise AssertionError("a clip name resolved through brt_source_file")

    check("suffix_is_a_warning", suffix_is_a_warning)
    check("name_resolves_through_property", name_resolves_through_property)
    check("ledger_lists_actions", ledger_lists_actions)
    check("manifest_resolves", manifest_resolves)
    check("ambiguous_property_raises", ambiguous_property_raises)
    check("stale_take_never_wins", stale_take_never_wins)
    print(f"test_library_resolve: {sum(RESULTS)}/{len(RESULTS)} passed", flush=True)
    return 0 if RESULTS and all(RESULTS) else 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        print(f"FAIL setup: {type(exc).__name__}: {exc}", flush=True)
        code = 1
    sys.exit(code)
