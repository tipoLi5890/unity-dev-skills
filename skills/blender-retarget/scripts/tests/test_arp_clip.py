"""test_arp_clip.py — brt_arp's retarget batch against stub Auto-Rig Pro operators, run in Blender.

    Blender --background --factory-startup --python tests/test_arp_clip.py [-- <scratch dir>]

Needs no Auto-Rig Pro: the test registers stand-in `arp.*` operators and the
scene properties the add-on keeps (source_rig, target_rig, bones_map_v2), each
recording what it saw. A synthetic source skeleton is exported to an FBX in the
scratch dir (a new temporary folder without one) and imported by the module.
Prints `PASS <name>` or `FAIL <name>: <why>` per case and exits 1 when any case
fails. Covers: before each clip the rig has no active action (the old one kept
by fake user) and every pose bone's matrix_basis is identity, even after a dirty
prior pose; default switches (hand 1, foot 0) are set before the bake and keyed
in the action; `exclude` drops a bone and its children from the bones list
before redefine_rest_pose; the armature modifier is paused during the batch and
restored; provenance and metadata properties land on the action; a missing
metadata key refuses before any bake; a dry run bakes one clip and leaves
nothing (pose, switches and offsets put back); a missing file under a clip name
holding "metadata", and a clip with frame_start alone, refuse as clip_invalid; a map naming a bone the skeleton lacks fails the first clip and skips
the rest; `source_bones` lists the skeleton and the map's missing names;
`keep_source` keeps the skeleton for brt_retarget `into_action`.
"""
import os
import sys
import tempfile

import bpy
from mathutils import Matrix, Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import brt_common as C  # noqa: E402
import brt_arp as B  # noqa: E402
import brt_retarget as R  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
TMP = argv[0] if argv else tempfile.mkdtemp(prefix="brt_arp_test_")
os.makedirs(TMP, exist_ok=True)
FBX = os.path.join(TMP, "jog_lane_left.fbx")
RESULTS: list[bool] = []
SEEN: dict = {}
PRESET = {"Hips": "c_root_master.x", "LeftArm": "c_arm_fk.l", "LeftForeArm": "c_forearm_fk.l"}
SWITCHES = ("c_hand_ik.l", "c_hand_ik.r", "c_foot_ik.l", "c_foot_ik.r")


def check(name, fn):
    try:
        fn()
    except Exception as exc:          # a failed assert or anything else: report and go on
        print(f"FAIL {name}: {type(exc).__name__}: {exc}", flush=True)
        RESULTS.append(False)
    else:
        print(f"PASS {name}", flush=True)
        RESULTS.append(True)


# --- stand-ins for the add-on --------------------------------------------------

class StubBoneItem(bpy.types.PropertyGroup):
    source_bone: bpy.props.StringProperty()


def _rig():
    return bpy.data.objects[bpy.context.scene.target_rig]


def _deviation(rig):
    ident = Matrix.Identity(4)
    return max(abs(a - b) for pb in rig.pose.bones for ra, rb in zip(pb.matrix_basis, ident)
               for a, b in zip(ra, rb))


class ARP_OT_freeze_armature(bpy.types.Operator):
    bl_idname, bl_label = "arp.freeze_armature", "stub"
    arm: bpy.props.StringProperty()

    def execute(self, context):
        scene, rig = context.scene, _rig()
        SEEN.setdefault("freeze", []).append({
            "deviation": _deviation(rig),
            "action": rig.animation_data.action.name if rig.animation_data and rig.animation_data.action else None,
            "switches": {n: float(rig.pose.bones[n]["ik_fk_switch"]) for n in SWITCHES}})
        old = bpy.data.objects[scene.source_rig]          # replaced, as the add-on does
        new = old.copy()
        for col in old.users_collection:
            col.objects.link(new)
        name = old.name
        bpy.data.objects.remove(old)
        new.name = name
        scene.source_rig = new.name
        return {'FINISHED'}


class ARP_OT_build_bones_list(bpy.types.Operator):
    bl_idname, bl_label = "arp.build_bones_list", "stub"

    def execute(self, context):
        items = context.scene.bones_map_v2
        items.clear()
        for bone in bpy.data.objects[context.scene.source_rig].data.bones:
            items.add().source_bone = bone.name
        return {'FINISHED'}


class ARP_OT_import_config_preset(bpy.types.Operator):
    bl_idname, bl_label = "arp.import_config_preset", "stub"
    preset_name: bpy.props.StringProperty()

    def execute(self, context):
        listed = {item.source_bone: item for item in context.scene.bones_map_v2}
        lacking = [s for s in PRESET if s not in listed]
        for source, target in PRESET.items():
            if source in listed:
                listed[source].name = target
        if lacking:
            self.report({'ERROR'}, f"some preset bones do not exist in the armature: {lacking}")
            return {'CANCELLED'}
        return {'FINISHED'}


class ARP_OT_import_config(bpy.types.Operator):
    bl_idname, bl_label = "arp.import_config", "stub"
    filepath: bpy.props.StringProperty()

    def execute(self, context):
        return {'FINISHED'}


class ARP_OT_redefine_rest_pose(bpy.types.Operator):
    bl_idname, bl_label = "arp.redefine_rest_pose", "stub"
    preserve: bpy.props.BoolProperty()
    rest_pose: bpy.props.StringProperty()

    def execute(self, context):
        SEEN.setdefault("redefine", []).append(sorted(i.source_bone for i in context.scene.bones_map_v2))
        return {'FINISHED'}


class ARP_OT_copy_bone_rest(bpy.types.Operator):
    bl_idname, bl_label = "arp.copy_bone_rest", "stub"

    def execute(self, context):
        return {'FINISHED'}


class ARP_OT_save_pose_rest(bpy.types.Operator):
    bl_idname, bl_label = "arp.save_pose_rest", "stub"

    def execute(self, context):
        return {'FINISHED'}


class ARP_OT_retarget(bpy.types.Operator):
    bl_idname, bl_label = "arp.retarget", "stub"
    frame_start: bpy.props.IntProperty()
    frame_end: bpy.props.IntProperty()
    fake_user_action: bpy.props.BoolProperty()

    def execute(self, context):
        rig = _rig()
        mods = [m.show_viewport for o in bpy.data.objects if o.type == 'MESH' for m in o.modifiers
                if m.type == 'ARMATURE']
        SEEN.setdefault("retarget", []).append({
            "modifiers_shown": mods,
            "switches": {n: float(rig.pose.bones[n]["ik_fk_switch"]) for n in SWITCHES}})
        action = bpy.data.actions.new("ArpBake")
        action.use_fake_user = self.fake_user_action
        slot = C.assign_slot(rig, action)
        for item in context.scene.bones_map_v2:
            if item.name in rig.pose.bones:
                fc = C.ensure_fcurve(action, slot, f'pose.bones["{item.name}"].location', 0, group_name=item.name)
                fc.keyframe_points.insert(self.frame_start, 0.0)
                fc.keyframe_points.insert(self.frame_end, 0.1)
        return {'FINISHED'}


STUBS = (ARP_OT_freeze_armature, ARP_OT_build_bones_list, ARP_OT_import_config_preset,
         ARP_OT_import_config, ARP_OT_redefine_rest_pose, ARP_OT_copy_bone_rest,
         ARP_OT_save_pose_rest, ARP_OT_retarget)


def register():
    bpy.utils.register_class(StubBoneItem)
    bpy.types.Scene.bones_map_v2 = bpy.props.CollectionProperty(type=StubBoneItem)
    bpy.types.Scene.source_rig = bpy.props.StringProperty()
    bpy.types.Scene.target_rig = bpy.props.StringProperty()
    for cls in STUBS:
        bpy.utils.register_class(cls)


# --- the scene -----------------------------------------------------------------

def armature(name, bones):
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    for bone, head, tail, parent in bones:
        eb = data.edit_bones.new(bone)
        eb.head, eb.tail = head, tail
        if parent:
            eb.parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    return obj


def export_source():
    """A small skeleton with a 10-frame clip, written once to FBX."""
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    src = armature("CourierMocap", [
        ("Hips", (0, 0, 1), (0, 0, 1.2), None), ("LeftArm", (0.2, 0, 1.5), (0.5, 0, 1.5), "Hips"),
        ("LeftForeArm", (0.5, 0, 1.5), (0.8, 0, 1.5), "LeftArm"),
        ("LeftHand", (0.8, 0, 1.5), (0.9, 0, 1.5), "LeftForeArm"),
        ("LeftHandIndex1", (0.9, 0, 1.5), (0.95, 0, 1.5), "LeftHand")])
    action = bpy.data.actions.new("CourierJog")
    slot = C.assign_slot(src, action)
    for bone in ("Hips", "LeftArm", "LeftForeArm"):
        src.pose.bones[bone].rotation_mode = 'QUATERNION'
        for i in range(4):
            fc = C.ensure_fcurve(action, slot, f'pose.bones["{bone}"].rotation_quaternion', i, group_name=bone)
            for f in range(1, 11):
                fc.keyframe_points.insert(f, Quaternion((1, 0, 0), 0.05 * f)[i])
    bpy.ops.object.select_all(action='DESELECT')
    src.select_set(True)
    bpy.context.view_layer.objects.active = src
    bpy.ops.export_scene.fbx(filepath=FBX, use_selection=True, object_types={'ARMATURE'},
                             bake_anim=True, add_leaf_bones=False)


def scene():
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    SEEN.clear()
    rig = armature("RunnerRig", [
        ("c_root_master.x", (0, 0, 1), (0, 0, 1.2), None),
        ("c_arm_fk.l", (0.2, 0, 1.5), (0.5, 0, 1.5), "c_root_master.x"),
        ("c_forearm_fk.l", (0.5, 0, 1.5), (0.8, 0, 1.5), "c_arm_fk.l"),
        ("c_hand_fk.l", (0.8, 0, 1.5), (0.9, 0, 1.5), "c_forearm_fk.l"),
        *[(n, (0.3, 0.3, 0.1 * i), (0.3, 0.4, 0.1 * i), None) for i, n in enumerate(SWITCHES)]])
    for n in SWITCHES:                       # the wrong way round: the defaults must fix them
        rig.pose.bones[n]["ik_fk_switch"] = 0.0 if "hand" in n else 1.0
    bpy.ops.mesh.primitive_cube_add()
    mesh = bpy.context.object
    mesh.name = "Runner"
    mod = mesh.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig
    prior = bpy.data.actions.new("PriorIdle")
    C.assign_slot(rig, prior)
    for pb in rig.pose.bones:                # a dirty pose left by the clip before
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = Quaternion((0, 0, 1), 0.7)
        pb.location = (0.1, 0.2, 0.3)
    bpy.context.view_layer.objects.active = rig
    return rig


BASE = {"op": "retarget", "armature": "RunnerRig", "exclude": ["LeftHand"], "family": "courier-pack",
        "map": {"c_root_master.x": "Hips", "c_arm_fk.l": "LeftArm", "c_forearm_fk.l": "LeftForeArm"},
        "metadata_fields": {"brt_description": "description"}}


def retarget(**extra):
    params = {**BASE, **extra}
    return B._retarget(params, B._probe())


def clip(name, **extra):
    return {"name": name, "fbx": FBX, "description": f"{name}, one lane over", **extra}


def case_reset_switches_exclude():
    rig = scene()
    objects_before = set(bpy.data.objects)
    out = retarget(clips=[clip("JogLaneLeft"), clip("JogLaneRight", map="stub_preset")])
    assert out["ok"], (out["gates"], out["clips"])
    assert [g["name"] for g in out["gates"]] == ["arp.retarget_clips", "arp.metadata_clips"]
    assert len(SEEN["freeze"]) == 2
    for seen in SEEN["freeze"]:
        assert seen["deviation"] < 1e-9, f"pose not at rest before the clip: {seen['deviation']}"
        assert seen["action"] is None, f"rig still played {seen['action']!r}"
    assert bpy.data.actions["PriorIdle"].use_fake_user, "the cleared action lost its fake user"
    for seen in SEEN["retarget"]:
        assert seen["switches"] == {"c_hand_ik.l": 1.0, "c_hand_ik.r": 1.0,
                                    "c_foot_ik.l": 0.0, "c_foot_ik.r": 0.0}, seen["switches"]
        assert seen["modifiers_shown"] == [False], "armature modifier not paused"
    assert bpy.data.objects["Runner"].modifiers["Armature"].show_viewport, "modifier not restored"
    for listed in SEEN["redefine"]:
        assert "LeftHand" not in listed and "LeftHandIndex1" not in listed, listed
        assert "LeftArm" in listed
    for name in ("JogLaneLeft", "JogLaneRight"):
        action = bpy.data.actions[name]
        assert action["brt_clip"] == name and action["brt_family"] == "courier-pack"
        assert action["brt_description"] == f"{name}, one lane over"
        assert action["brt_source_file"] == FBX
        paths = {fc.data_path for fc in C.action_slot_fcurves(action)}
        for n in SWITCHES:
            assert f'pose.bones["{n}"]["ik_fk_switch"]' in paths, f"{n} not keyed in {name}"
    for r in out["clips"]:
        assert r["bake"]["ok"] and r["metadata"]["ok"], r
        assert r["excluded"] == 2, r
    assert rig.animation_data.action.name == "PriorIdle", "the rig's action was not put back"
    assert set(bpy.data.objects) == objects_before, "the import was not cleaned up"


def case_metadata_missing_refuses():
    scene()
    actions, objects = set(bpy.data.actions), set(bpy.data.objects)
    bare = {"name": "JogLaneRight", "fbx": FBX}            # no description
    out = retarget(clips=[clip("JogLaneLeft"), bare])
    assert not out["ok"] and out["reason"] == "metadata_invalid", out
    assert "description" in out["message"]
    assert "retarget" not in SEEN and "freeze" not in SEEN, "an operator ran before the refusal"
    assert set(bpy.data.actions) == actions and set(bpy.data.objects) == objects


def case_dry_run():
    rig = scene()
    rig["rest_transf_offset"] = [0.25, 0.5]           # an offset a clip before left
    actions = set(bpy.data.actions)
    basis = {pb.name: pb.matrix_basis.copy() for pb in rig.pose.bones}
    switches = {n: rig.pose.bones[n]["ik_fk_switch"] for n in SWITCHES}
    out = retarget(dry_run=True, clips=[clip("JogLaneLeft"), clip("JogLaneRight")])
    assert out["ok"], (out["gates"], out["clips"])
    assert out["dry_run"] and out["clips_planned"] == 2 and len(out["clips"]) == 1
    assert len(SEEN["retarget"]) == 1
    assert out["clips"][0]["metadata"]["written"], out["clips"][0]
    assert set(bpy.data.actions) == actions, "a dry run left an action"
    for pb in rig.pose.bones:
        dev = max(abs(a - b) for ra, rb in zip(pb.matrix_basis, basis[pb.name]) for a, b in zip(ra, rb))
        assert dev < 1e-6, f"{pb.name}: pose not put back ({dev})"
    assert {n: rig.pose.bones[n]["ik_fk_switch"] for n in SWITCHES} == switches, "switches not put back"
    assert list(rig["rest_transf_offset"]) == [0.25, 0.5], "rest_transf_offset not put back"


def case_clip_problems_named():
    scene()
    named = {"name": "metadata_take", "fbx": os.path.join(TMP, "missing.fbx"), "description": "x"}
    out = retarget(clips=[named])
    assert not out["ok"] and out["reason"] == "clip_invalid", out
    half = clip("JogLaneLeft", frame_start=2)
    out = retarget(clips=[half])
    assert not out["ok"] and out["reason"] == "clip_invalid" and "frame_end" in out["message"], out
    assert "freeze" not in SEEN, "an operator ran before the refusal"


def case_first_failure_skips_rest():
    scene()
    bad = {**BASE["map"], "c_hand_fk.l": "RightHand"}      # a bone this skeleton does not have
    out = retarget(map=bad, clips=[clip("JogLaneLeft"), clip("JogLaneRight")])
    assert not out["ok"]
    first, second = out["clips"]
    assert not first["bake"]["ok"] and "RightHand" in first["bake"]["error"], first
    assert first["bake"]["stage"] == "import bones", first["bake"]
    assert second["bake"]["error"].startswith("skipped"), second
    assert "retarget" not in SEEN and "redefine" not in SEEN


def case_source_bones():
    scene()
    objects = set(bpy.data.objects)
    out = B.run({"op": "source_bones", "fbx": [FBX],
                 "map": {"c_arm_fk.l": "LeftArm", "c_hand_fk.l": "RightHand"}})
    names = {b["name"] for b in out["files"][0]["bones"]}
    assert {"Hips", "LeftArm", "LeftHandIndex1"} <= names, names
    assert out["files"][0]["map_missing"] == ["RightHand"], out["files"][0]
    assert not out["ok"] and [g["name"] for g in out["gates"]] == ["arp.source_skeleton_found",
                                                                    "arp.map_sources_found"]
    assert set(bpy.data.objects) == objects, "source_bones left the import behind"


def case_keep_source_then_into_action():
    scene()
    out = retarget(keep_source=True, switches={}, clips=[clip("JogLaneLeft")])
    assert out["ok"], (out["gates"], out["clips"])
    source = bpy.data.objects[out["clips"][0]["source_object"]]
    assert source.name == "JogLaneLeft_Source" and source["brt_clip"] == "JogLaneLeft"
    assert source.hide_render
    action = bpy.data.actions["JogLaneLeft"]
    paths = {fc.data_path for fc in C.action_slot_fcurves(action)}
    assert not any("ik_fk_switch" in p for p in paths), "switches: {} keyed a switch"
    conv = R.run({"source": source.name, "target": "RunnerRig", "map": {"c_hand_fk.l": "LeftForeArm"},
                  "into_action": "JogLaneLeft"})
    assert conv["ok"], conv["gates"]
    after = {fc.data_path for fc in C.action_slot_fcurves(action)}
    assert after - paths == {'pose.bones["c_hand_fk.l"].rotation_quaternion'}, after - paths


register()
export_source()
for name, fn in (("clip_reset_switches_exclude", case_reset_switches_exclude),
                 ("metadata_missing_refuses_before_bake", case_metadata_missing_refuses),
                 ("dry_run_leaves_nothing", case_dry_run),
                 ("clip_problems_named", case_clip_problems_named),
                 ("first_failure_skips_rest", case_first_failure_skips_rest),
                 ("source_bones_lists_skeleton", case_source_bones),
                 ("keep_source_then_into_action", case_keep_source_then_into_action)):
    check(name, fn)

print(f"{sum(RESULTS)}/{len(RESULTS)} passed", flush=True)
sys.exit(0 if all(RESULTS) else 1)
