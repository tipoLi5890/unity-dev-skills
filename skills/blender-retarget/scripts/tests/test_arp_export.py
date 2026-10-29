"""test_arp_export.py — brt_arp's `export` op against a stub Auto-Rig Pro exporter, run in Blender.

    Blender --background --factory-startup --python tests/test_arp_export.py [-- <scratch dir>]

Needs no Auto-Rig Pro: the test registers a stand-in `arp.arp_export_fbx_panel` that writes the
selection with Blender's own FBX exporter and records the add-on's scene settings it saw, and those
scene properties. A small rig skins a cube with five weights on some vertices. Prints `PASS <name>`
or `FAIL <name>: <why>` per case and exits 1 when any case fails. Covers: export writes the file
with the pipeline's settings (Unity, humanoid, master trajectory, units x100) set during the call
and put back after, limits every vertex to 4 deform weights, writes the skeleton of the re-imported
file and carries the auto-rig-pro licence on the record; without the limit five weights fail
arp.export_max_influences; a rig no mesh is weighted to refuses not_bound; no `fbx` refuses
export_path_missing; a missing armature refuses object_missing.
"""
import json
import os
import sys
import tempfile

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import brt_arp as B  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
TMP = argv[0] if argv else tempfile.mkdtemp(prefix="brt_arp_export_")
os.makedirs(TMP, exist_ok=True)
RESULTS: list[bool] = []
SEEN: list = []
SETTINGS = ("arp_engine_type", "arp_export_rig_type", "arp_ge_master_traj", "arp_units_x100")


def check(name, fn):
    try:
        fn()
    except Exception as exc:          # a failed assert or anything else: report and go on
        print(f"FAIL {name}: {type(exc).__name__}: {exc}", flush=True)
        RESULTS.append(False)
    else:
        print(f"PASS {name}", flush=True)
        RESULTS.append(True)


class ARP_OT_arp_export_fbx_panel(bpy.types.Operator):
    bl_idname, bl_label = "arp.arp_export_fbx_panel", "stub"
    filepath: bpy.props.StringProperty()

    def execute(self, context):
        SEEN.append({k: getattr(context.scene, k) for k in SETTINGS})
        bpy.ops.export_scene.fbx(filepath=self.filepath, use_selection=True, add_leaf_bones=False,
                                 object_types={'ARMATURE', 'MESH'})
        return {'FINISHED'}


def register():
    bpy.types.Scene.arp_engine_type = bpy.props.StringProperty(default="GODOT")
    bpy.types.Scene.arp_export_rig_type = bpy.props.StringProperty(default="UNIVERSAL")
    bpy.types.Scene.arp_ge_master_traj = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.arp_units_x100 = bpy.props.BoolProperty(default=False)
    bpy.utils.register_class(ARP_OT_arp_export_fbx_panel)


def scene(weighted=True):
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    SEEN.clear()
    data = bpy.data.armatures.new("RunnerRig")
    rig = bpy.data.objects.new("RunnerRig", data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    names = ["root.x", "spine_01.x", "spine_02.x", "spine_03.x", "neck.x"]
    for i, name in enumerate(names):
        eb = data.edit_bones.new(name)
        eb.head, eb.tail = (0, 0, 0.2 * i), (0, 0, 0.2 * (i + 1))
        if i:
            eb.parent = data.edit_bones[names[i - 1]]
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cube_add(size=0.4, location=(0, 0, 0.5))
    mesh = bpy.context.object
    mesh.name = "Runner"
    if weighted:
        groups = [mesh.vertex_groups.new(name=n) for n in names]
        for v in mesh.data.vertices:
            for g in groups if v.index % 2 == 0 else groups[:2]:   # five weights on half the vertices
                g.add([v.index], 0.2, 'REPLACE')
    mod = mesh.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig
    return rig, mesh


def gate(result, name):
    return next((g for g in result.get("gates", []) if g["name"] == name), None)


def export(**extra):
    return B._export({"op": "export", "armature": "RunnerRig", **extra}, B._probe())


def case_export_ok():
    scene()
    fbx = os.path.join(TMP, "runner.fbx")
    out = export(fbx=fbx)
    assert out["ok"], [g for g in out["gates"] if not g["pass"]] or out.get("reason")
    assert os.path.getsize(fbx) > 0
    assert SEEN == [{"arp_engine_type": "UNITY", "arp_export_rig_type": "HUMANOID",
                     "arp_ge_master_traj": True, "arp_units_x100": True}], SEEN
    scn = bpy.context.scene
    assert (scn.arp_engine_type, scn.arp_export_rig_type, scn.arp_ge_master_traj, scn.arp_units_x100) == \
        ("GODOT", "UNIVERSAL", False, False), "scene settings not put back"
    assert gate(out, "arp.export_max_influences")["value"] <= 4
    assert out["record"]["licence"] == {"source": "auto-rig-pro", "territory": "worldwide"}
    with open(out["skeleton"], encoding="utf-8") as handle:
        skeleton = json.load(handle)
    assert skeleton["schema"] == "skeleton/1" and {b["name"] for b in skeleton["bones"]} >= {"root.x", "neck.x"}
    assert out["meshes"] == ["Runner"] and "Runner" in bpy.data.objects and len(bpy.data.armatures) == 1, \
        "the re-import was not taken back"


def case_not_limited_fails():
    scene()
    out = export(fbx=os.path.join(TMP, "five.fbx"), limit_influences=False)
    most = gate(out, "arp.export_max_influences")
    assert most is not None and not most["pass"] and most["value"] == 5 and not out["ok"], most


def case_not_bound_refuses():
    scene(weighted=False)
    out = export(fbx=os.path.join(TMP, "none.fbx"))
    assert not out["ok"] and out.get("reason") == "not_bound", out.get("reason")
    assert not os.path.exists(os.path.join(TMP, "none.fbx")) and not SEEN


def case_refusals():
    scene()
    out = export()
    assert out.get("reason") == "export_path_missing", out.get("reason")
    out = B._export({"op": "export", "armature": "Nope", "fbx": os.path.join(TMP, "x.fbx")}, B._probe())
    assert out.get("reason") == "object_missing", out.get("reason")
    assert not SEEN


register()
for name, fn in (("export_with_pipeline_settings", case_export_ok),
                 ("five_weights_fail_without_limit", case_not_limited_fails),
                 ("unbound_rig_refuses", case_not_bound_refuses),
                 ("missing_path_and_rig_refuse", case_refusals)):
    check(name, fn)

print(f"{sum(RESULTS)}/{len(RESULTS)} passed", flush=True)
sys.exit(0 if all(RESULTS) else 1)
