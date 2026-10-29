"""brt_arp.py — drive the user's own Auto-Rig Pro: Smart markers, match, bind, retarget, pipeline, export.

Runs inside Blender; not a command-line script (the stub is in brt_common.py).

Nothing of Auto-Rig Pro (ARP) lives in this repository: no add-on source, no
operator body, no AI model file. Each call finds the copy the user installed and
enabled, by scanning the enabled add-ons for a module whose name contains
`auto_rig_pro` (a legacy folder, or an extension such as
`bl_ext.<repo>.auto_rig_pro`), and drives it only through the operators it
registered and, for markers, through its own marker helper looked up by name.
An operator, an operator property or a scene property that is not found is
reported and the call refuses; no name is guessed. Every op but `probe` and
`source_bones` runs the probe first and refuses, changing nothing, when the add-on or an operator
it needs is missing.

    brt_arp.run({"op": "probe"})
    brt_arp.run({"op": "markers", "armature": "RunnerRig",
                 "landmarks": {"neck": [0, 0, 1.5], "chin": [0, -0.08, 1.58],
                               "shoulder": [0.16, 0, 1.42], "hand": [0.7, 0, 1.4],
                               "root": [0, 0, 1.0], "foot": [0.1, -0.05, 0.05]}})
    brt_arp.run({"op": "match", "armature": "RunnerRig", "mesh": "Runner"})
    brt_arp.run({"op": "bind", "armature": "RunnerRig", "mesh": "Runner"})
    brt_arp.run({"op": "source_bones", "fbx": ["//clips/jog_lane_left.fbx"],
                 "map": {"c_arm_fk.l": "LeftArm", "c_forearm_fk.l": "LeftForeArm"}})
    brt_arp.run({"op": "pipeline", "mesh": "Runner", "markers": "//rig/runner.markers.json",
                 "fbx": "//export/runner.fbx"})
    brt_arp.run({"op": "export", "armature": "RunnerRig", "fbx": "//export/runner.fbx"})
    brt_arp.run({"op": "retarget", "armature": "RunnerRig", "dry_run": True,
                 "map": {"c_root_master.x": "Hips", "c_arm_fk.l": "LeftArm", "c_forearm_fk.l": "LeftForeArm"},
                 "exclude": ["LeftHand", "RightHand"], "family": "courier-pack",
                 "metadata_fields": {"brt_description": "description"},
                 "clips": [{"name": "JogLaneLeft", "fbx": "//clips/jog_lane_left.fbx",
                            "description": "jog, one lane to the left"}]})

probe     reads only. addon_present, module, version (bl_info, or the
          blender_manifest.toml beside the module), ai_files (an AI folder named
          in the add-on's preferences, or its extension user folder, holds an
          `inference` folder; the path itself is never reported), ai_version, and
          `operators` {"arp.match_to_rig": bool, ...}. A name the add-on
          registers under another prefix counts as found; `operator_idnames`
          says where, `operator_properties` lists what each one declares.
          Gate arp.addon_present.
markers   needs Smart started in the add-on on the mesh first (it picks the body
          the marker helper sizes from); refuses with smart_not_started until
          then. `landmarks`: the add-on's marker name -> [x, y, z] in the
          armature's space (world space without `armature`; `mesh`, optional,
          is selected first). Each name goes to
          the add-on's own `_add_marker`, found by name in its loaded modules
          (reason smart_marker_api_not_found without it), with `mirror` (True)
          as its mirror switch, inside a 3D-viewport override; the marker it makes
          or reuses, `<name>_loc`, is moved there and read back evaluated. A limb
          marker sits on +X: the add-on's limit holds one placed on -X, and it
          counts as not placed (`miss`). Gate arp.markers_placed.
match     Match to Rig. Refuses while a mesh child of the rig (or `mesh`) holds
          weights for one of its deform bones: a re-match after bind moves the
          rest pose under those weights. Gate arp.bone_count (== `expected_bones`
          when given, else > 0); reports bone_count and deform_bone_count.
bind      Bind with pseudo_voxels True, resolution 7 (a starting value), split False, preserve
          True, chin False, scale_fix False. Each goes to an operator property of
          that name if the operator declares one, else to the scene property the
          add-on keeps it in (pseudo_voxels picks the engine), set for the call
          and restored after. `option_names` points a key elsewhere ("name" or
          "scene.name"); a value of None leaves the add-on's setting alone; a key
          that matches nothing refuses and lists what exists. Refuses a mesh that
          already has groups named after deform bones. Gate
          arp.vertices_without_group (no deform weight > 0; limit 0).
source_bones  stock Blender only, no add-on. Imports each `fbx` (one path or a
          list), reads its skeleton and takes the import back. Per file:
          armatures, bones [{name, parent}], skeleton (a hash of the bone names:
          equal hashes share one map), frame_range, and with a {target: source}
          `map` the source names it lacks (`map_missing`). Gates
          arp.source_skeleton_found (one armature per file), arp.map_sources_found
          (with `map`: 0 missing). Build the map from these names, never from
          another skeleton's map.
retarget  `clips`: [{"name", "fbx", "map"?, "frame_start"?, "frame_end"?, "align"?,
          "exclude"?, "switches"?, "origin"?, "family"?, "metadata"?}]; each
          key but name/fbx/frames may sit at the top level for every clip.
          `map`: an add-on preset name, a saved config path (.bmap), or
          {target_bone: source_bone | {"source": bone, <field>: value}} where each
          <field> must be one the installed bones-list entry declares (refused
          otherwise, listing them),
          written into the add-on's bones list after build_bones_list and checked
          against the skeleton just imported (a source bone it lacks fails the
          clip before any rest changes). Before any change every clip is checked:
          the file, the map, the switches, and the metadata of every clip (any
          missing `metadata_fields` key refuses with metadata_invalid: nothing is
          baked). Then, per clip: clear the rig's active action (its fake user
          kept) and set every pose bone's matrix_basis to identity; set the IK/FK
          `switches` ({bone: value}; default, from the rig's own bones carrying
          ik_fk_switch: c_hand_ik.* 1 FK, c_foot_ik.* 0 IK, the add-on's value
          convention; {} sets none); import the FBX (the user's own file, read
          only); point `target_prop` then `source_prop` (default target_rig,
          source_rig) at the two skeletons; freeze_armature(arm='source'), the
          source re-read by name; build_bones_list; the map; drop the `exclude`
          source bones and every bone below them (hands take their fingers) from
          the bones list; delete `rest_transf_offset`, which the clip before left
          and redefine_rest_pose would reuse; redefine_rest_pose(preserve=True,
          rest_pose='REST'); select the bones to align (`align`, else those the
          list maps onto the rig); copy_bone_rest, save_pose_rest,
          retarget(frame_start, frame_end, fake_user_action=True). The new action
          takes the clip's name (a suffix Blender adds is listed in
          duplicate_suffixes), fake user on, every switch keyed at its first
          frame. Then, as a separate phase, the action's custom properties:
          brt_clip, brt_source_file, brt_origin and brt_family (when given), then
          `metadata` and `metadata_fields` ({property: clip key}). Look actions up
          by property, never by name: brt_library with `provenance_key:
          "brt_clip"` and the clip names in `actions`, or with `manifest`,
          whose `file` is matched against brt_source_file. The imported skeleton is removed unless
          `keep_source`: then it stays hidden as `<name>_Source`, stamped
          brt_clip, for brt_retarget `into_action`. Each clip reports
          `bake` {ok, stage, error} and `metadata` {ok, error, written}; a bake
          the add-on fails (a preset bone the source lacks) is rolled back alone.
          When the first clip fails either phase the rest are skipped
          (`stop_if_first_fails`, default True). `dry_run: True` runs only the
          first clip end to end and rolls it back: the datablocks it made, the
          active action, every pose bone's matrix_basis, the switch values and
          the rest_transf_offset properties are put back (any other edit the
          add-on's operators make to existing data is not). `pause_deform` (default True)
          turns off the viewport display of the armature modifiers the rig
          drives for the batch and turns it back on after. `progress_path`
          rewrites the clip results as JSON after each clip. Gates
          arp.retarget_clips (bakes that left an action with a slot and curves),
          arp.metadata_clips (metadata written), each == the clips run.
pipeline  one call from a prepared mesh to a skeleton JSON, no Smart and no window
          (`blender -b` works: the 3D view comes from the file's own screens). `mesh`, `markers`
          (an arp_markers.py result from the character-autorig skill, or its path), `fbx` (the
          file the export writes); optional `armature` (default "<mesh>Rig"; an existing
          object of that name refuses with rig_exists), `preset` ("human"), `spine_count`
          (the add-on's Count, which includes its root: 4 = three spine bones; default the
          markers' arp_spine_count), the bind keys and `option_names` as for `bind`,
          `max_influences` (4) and `limit_influences` (True), `units_x100` (True, the add-on's
          default for Unity), `skeleton_out` (default <fbx>.skeleton.json). Refuses, changing
          nothing, a mesh with an Armature modifier (already_bound), one whose scale or
          rotation is not applied (transform_not_applied), markers without arp_refs or a
          required reference bone (markers_invalid), and an exporter scene setting the add-on
          lacks (export_setting_missing). Steps: append the preset (arp.append_arp); set the
          spine Count through arp.show_limb_params on root_ref.x when it differs; write each
          reference bone's head and tail from arp_refs (world -> rig space; a .l bone without
          its .r twin is mirrored), keeping the preset's roll direction, turned with the hand
          for hand and finger bones; Match to Rig; bind as `bind` does; limit every vertex to
          `max_influences` deform weights and normalise (Unity keeps 4 by default); export
          with the add-on's FBX exporter for Unity, humanoid, the master trajectory c_traj as
          the root bone (scene settings set for the call and put back); import the file again,
          write its skeleton (skeleton/1, armature space in metres, Z up; `deform` is true for a
          bone some vertex is weighted to, since the FBX importer marks every bone deform) and
          take the import back. Gates arp.rig_appended, arp.spine_bones (== Count - 1),
          arp.refs_placed (every name exists on the preset, each end within 1e-4 m),
          arp.bone_count, arp.vertices_without_group, arp.export_written,
          arp.export_armatures (1), arp.export_unweighted (0), arp.export_max_influences
          (<= max_influences). A failed gate before the bind stops the call and removes the rig
          it appended (rolled_back); after the bind the mesh keeps its groups. `next` is the
          contract check: contract_map.py map <skeleton> --map arp --require contract
          --min-fingers 30 (unity-rigged-character). The record carries
          licence {source: "auto-rig-pro", territory: "worldwide"}.
export    the pipeline's export and read-back again, for a rig it bound whose weights were
          repaired since (brt_weights): `armature` (the bound rig), `fbx`, optional `mesh` (one
          name or a list; default every mesh whose Armature modifier targets the rig),
          `max_influences` (4), `limit_influences` (True: limit and normalise again, as a
          transfer can add a fifth weight), `units_x100` (True), `skeleton_out`. The same
          scene settings (Unity, humanoid, c_traj root), the same skeleton/1 file and the same
          record licence as `pipeline`. Refuses export_path_missing, not_bound (no mesh holds a
          deform weight of the rig), export_setting_missing and no_view3d_area, changing
          nothing. Gates arp.vertices_without_group, arp.export_written, arp.export_armatures,
          arp.export_unweighted, arp.export_max_influences.

Selection, active object, mode and frame are put back after every op. Without a window (a
`blender -b` run) markers, match, bind, pipeline and export use the first 3D view area of the file's
screens; they refuse with no_view3d_area only when the file has none. A
failure removes the datablocks the call created, but not ARP's own edits to
datablocks that existed before (the rig's bones after match, the mesh's groups
after bind, the body's applied rotation after markers): save the file first.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib
import inspect
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

import brt_common as C

_NAME = "auto_rig_pro"
OPERATORS = ("arp.go_detect", "arp.match_to_rig", "arp.bind_to_rig", "arp.retarget",
             "arp.freeze_armature", "arp.build_bones_list", "arp.redefine_rest_pose",
             "arp.copy_bone_rest", "arp.save_pose_rest", "arp.import_config_preset",
             "arp.import_config", "arp.append_arp", "arp.show_limb_params",
             "arp.arp_export_fbx_panel")
_REMAP = ("arp.freeze_armature", "arp.build_bones_list", "arp.redefine_rest_pose",
          "arp.copy_bone_rest", "arp.save_pose_rest", "arp.retarget")
# keyword arguments retarget hands each operator; checked against its RNA before any change
_REMAP_KWARGS = {"arp.freeze_armature": ("arm",),
                 "arp.redefine_rest_pose": ("preserve", "rest_pose"),
                 "arp.retarget": ("frame_start", "frame_end", "fake_user_action")}
_BIND_DEFAULTS = {"pseudo_voxels": True, "resolution": 7, "split": False,
                  "preserve": True, "chin": False, "scale_fix": False}
# the bind operator declares none of these; the add-on keeps them on the scene
_BIND_SCENE = {"pseudo_voxels": "arp_bind_engine", "resolution": "arp_pseudo_voxels_resolution",
               "split": "arp_bind_split", "preserve": "arp_bind_preserve",
               "chin": "arp_bind_chin", "scale_fix": "arp_bind_scale_fix"}
_ENGINE = {True: 'PSEUDO_VOXELS', False: 'HEAT_MAP'}  # pseudo_voxels on the engine enum
_OFFSET_KEY = "rest_transf_offset"
_SWITCH = "ik_fk_switch"
# ARP's value convention for its switch bones: 1 FK, 0 IK. Arms bake onto FK controls, feet stay IK.
_SWITCH_CONVENTION = {"c_hand_ik": 1.0, "c_foot_ik": 0.0}
_BONES_LIST = "bones_map_v2"
_NO_VIEW = "a 3D view: neither a window nor this file's screens have one"
_CLIP_KINDS = ("objects", "meshes", "armatures", "materials", "images", "textures",
               "actions", "collections")


# --- finding the add-on ------------------------------------------------------

def _op(idname: str):
    space, name = idname.split(".", 1)
    return getattr(getattr(bpy.ops, space), name)


def _registered(idname: str) -> bool:
    # hasattr(bpy.ops.arp, name) is True for any name: bpy.ops builds a wrapper on
    # attribute access. Only the RNA lookup fails for an operator nobody registered.
    try:
        _op(idname).get_rna_type()
        return True
    except (KeyError, AttributeError, ValueError):
        return False


def _op_props(idname: str) -> dict:
    return {p.identifier: p for p in _op(idname).get_rna_type().properties
            if p.identifier != "rna_type"}


def _addon_modules() -> list[str]:
    """Enabled add-ons whose module name contains auto_rig_pro, the plain package first."""
    names = [a.module for a in bpy.context.preferences.addons if _NAME in a.module.lower()]
    return sorted(names, key=lambda n: (not n.lower().rsplit(".", 1)[-1].startswith(_NAME), len(n)))


def _owned_operators(module: str) -> dict[str, str]:
    """Function name -> idname of each operator class the add-on registered."""
    out, stack = {}, list(bpy.types.Operator.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        owner, idname = getattr(cls, "__module__", "") or "", getattr(cls, "bl_idname", "") or ""
        if (owner == module or owner.startswith(module + ".")) and "." in idname and _registered(idname):
            out.setdefault(idname.split(".", 1)[1], idname)
    return out


def _resolve(module: str | None) -> dict[str, str | None]:
    """Each wanted name -> the idname it is registered under, or None.

    `arp.<name>` first; otherwise an operator of the same function name that the
    add-on itself registered under another prefix.
    """
    out, owned = {}, None
    for name in OPERATORS:
        if _registered(name):
            out[name] = name
            continue
        if owned is None:
            owned = _owned_operators(module) if module else {}
        out[name] = owned.get(name.split(".", 1)[1])
    return out


def _version(module: str) -> str | None:
    mod = sys.modules.get(module)
    info = getattr(mod, "bl_info", None)
    if isinstance(info, dict) and info.get("version"):
        return ".".join(str(x) for x in info["version"])
    path = getattr(mod, "__file__", None)
    if not path:
        return None
    try:
        import tomllib
        with open(os.path.join(os.path.dirname(path), "blender_manifest.toml"), "rb") as handle:
            value = tomllib.load(handle).get("version")
    except (OSError, ValueError, ImportError):
        return None
    return str(value) if value else None


def _listdir(folder: str) -> list[str]:
    try:
        return sorted(os.listdir(folder))
    except OSError:
        return []


def _first_line(folder: str) -> str | None:
    """The first line of a version file in `folder`, if there is one."""
    for file in _listdir(folder):
        if file.lower().startswith("version") and os.path.isfile(os.path.join(folder, file)):
            with contextlib.suppress(OSError, UnicodeDecodeError):
                with open(os.path.join(folder, file), encoding="utf-8") as handle:
                    return handle.readline().strip()[:64] or None
    return None


def _ai_files(module: str) -> tuple[bool, str | None]:
    """(an AI `inference` folder exists, its version string). Paths stay internal."""
    addon = bpy.context.preferences.addons.get(module)
    prefs = getattr(addon, "preferences", None)
    folders, version = [], None
    if prefs is not None:
        for prop in prefs.bl_rna.properties:
            tokens = prop.identifier.lower().split("_")
            if prop.type != 'STRING' or "ai" not in tokens:
                continue
            value = getattr(prefs, prop.identifier, "") or ""
            if "version" in tokens:
                version = value.strip()[:64] or version
            elif value:
                folders.append(bpy.path.abspath(value))
    with contextlib.suppress(ValueError, AttributeError):  # a legacy add-on has no extension folder
        folders.append(bpy.utils.extension_path_user(module, create=False))
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        if os.path.basename(os.path.normpath(folder)) == "inference":
            folder = os.path.dirname(os.path.normpath(folder))
        roots = [folder] + [os.path.join(folder, d) for d in _listdir(folder)]
        root = next((r for r in roots if os.path.isdir(os.path.join(r, "inference"))), None)
        if root is not None:
            return True, version or _first_line(root)
    return False, None


def _probe() -> dict:
    found = _addon_modules()
    module = found[0] if found else None
    info = {"addon_present": module is not None, "module": module, "version": None,
            "ai_files": False, "ai_version": None}
    if module is None:
        import addon_utils
        installed = [m.__name__ for m in addon_utils.modules(refresh=False) if _NAME in m.__name__.lower()]
        info["installed_not_enabled"] = installed[0] if installed else None
    else:
        info["version"] = _version(module)
        info["ai_files"], info["ai_version"] = _ai_files(module)
        if len(found) > 1:
            info["modules_found"] = found
    idnames = _resolve(module)
    info["operators"] = {name: idname is not None for name, idname in idnames.items()}
    info["operator_idnames"] = {name: idname for name, idname in idnames.items() if idname}
    info["operator_properties"] = {name: sorted(_op_props(idname))
                                   for name, idname in idnames.items() if idname}
    return info


# --- running it --------------------------------------------------------------

def _view3d_override() -> dict | None:
    """window, screen, area, region and space of a 3D viewport, for bpy.context.temp_override.

    Headless (`blender -b`) there is no window, but the file's screens still hold their 3D view
    areas: the first one is used without a window. The add-on's operators read
    `context.space_data` (append reads its overlay), so the space is always in the override.
    """
    windows = [bpy.context.window] if bpy.context.window else []
    windows += [w for w in bpy.context.window_manager.windows if w not in windows]
    screens = [(w, w.screen) for w in windows] + [(None, s) for s in bpy.data.screens]
    for window, screen in screens:
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if region is not None:
                out = {"screen": screen, "area": area, "region": region, "space_data": area.spaces.active}
                if window is not None:
                    out["window"] = window
                return out
    return None


def _call(idname: str, override: dict | None, **kwargs) -> None:
    """Run an operator with checked keywords. An ERROR it reports raises RuntimeError."""
    unknown = sorted(set(kwargs) - set(_op_props(idname)))
    if unknown:
        raise ValueError(f"{idname} declares no {unknown}; it has {sorted(_op_props(idname))}")
    scope = bpy.context.temp_override(**override) if override else contextlib.nullcontext()
    with scope:
        result = _op(idname)('EXEC_DEFAULT', **kwargs)
    if 'FINISHED' not in result:
        raise RuntimeError(f"{idname} returned {sorted(result)}")


def _refuse(params: dict, info: dict, reason: str, message: str, **extra) -> dict:
    gates = [C.gate("arp.addon_present", info["addon_present"], True, info["addon_present"]),
             C.gate("arp.precondition", reason, "met", False)]
    return C.report(params, gates, op=params.get("op"), reason=reason, message=message,
                    module=info["module"], version=info["version"], **extra)


def _objects(params: dict, key: str, kind: str) -> tuple[list, str | None]:
    """The objects named by params[key] (a name or a list), all of type `kind`."""
    value = params.get(key)
    names = [value] if isinstance(value, str) else list(value or [])
    if not names:
        return [], f"params[{key!r}] names no object"
    out = []
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != kind:
            return [], f"{name!r} is not a {kind} object in this file"
        out.append(obj)
    return out, None


def _object_mode() -> None:
    obj = bpy.context.object
    if obj is not None and obj.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def _select_only(objects: list, active) -> None:
    _object_mode()
    layer = bpy.context.view_layer
    for obj in layer.objects:
        obj.select_set(obj in objects)
    layer.objects.active = active


def _deform_groups(rig, meshes: list, weighted: bool) -> dict[str, list[str]]:
    """Per mesh, its groups named after a deform bone of `rig` (holding a weight > 0 if `weighted`)."""
    deform = {b.name for b in rig.data.bones if b.use_deform}
    out = {}
    for obj in meshes:
        groups = {g.index: g.name for g in obj.vertex_groups if g.name in deform}
        if weighted and groups:
            names = {groups[g.group] for v in obj.data.vertices for g in v.groups
                     if g.weight > 0 and g.group in groups}
        else:
            names = set(groups.values())
        if names:
            out[obj.name] = sorted(names)
    return out


def _unweighted(obj, deform: set) -> int:
    index = {g.index for g in obj.vertex_groups if g.name in deform}
    return sum(1 for v in obj.data.vertices
               if not any(g.group in index and g.weight > 0 for g in v.groups))


# --- markers -----------------------------------------------------------------

def _marker_helper(module: str):
    """(the add-on's own `_add_marker`, the module it lives in), or (None, None).

    Its loaded submodules first; then its installed source is read to find the
    file that defines the function, and that submodule is imported. Nothing is
    copied out of it.
    """
    prefix = module + "."
    for name in sorted(n for n in list(sys.modules) if n == module or n.startswith(prefix)):
        fn = getattr(sys.modules[name], "_add_marker", None)
        if callable(fn):
            return fn, name
    base = os.path.dirname(getattr(sys.modules.get(module), "__file__", None) or "")
    if not base:
        return None, None
    for folder, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "__")))
        for file in sorted(f for f in files if f.endswith(".py")):
            path = os.path.join(folder, file)
            try:
                with open(path, encoding="utf-8", errors="ignore") as handle:
                    if "def _add_marker(" not in handle.read():
                        continue
                rel = os.path.relpath(path[:-3], base).replace(os.sep, ".")
                dotted = module if rel == "__init__" else f"{module}.{rel.removesuffix('.__init__')}"
                fn = getattr(importlib.import_module(dotted), "_add_marker", None)
            except Exception:  # a file that cannot be read or imported holds no usable helper
                continue
            if callable(fn):
                return fn, dotted
    return None, None


def _marker_call(fn) -> tuple:
    """(call(name, mirror) into the helper, or None when its parameters are unknown; its signature).

    The first required parameter takes the marker name. A second one is accepted
    only when its name says it is the mirror switch (the add-on's own button
    passes True there); anything else required is not filled by guesswork.
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return None, "?"
    kind = inspect.Parameter
    required = [p for p in sig.parameters.values() if p.default is p.empty
                and p.kind not in (kind.VAR_POSITIONAL, kind.VAR_KEYWORD)]
    if not required or required[0].kind is kind.KEYWORD_ONLY or len(required) > 2:
        return None, str(sig)
    if len(required) == 1:
        return (lambda name, mirror: fn(name)), str(sig)
    switch = required[1]
    if "mirror" not in switch.name.lower():
        return None, str(sig)
    if switch.kind is kind.KEYWORD_ONLY:
        return (lambda name, mirror: fn(name, **{switch.name: mirror})), str(sig)
    return (lambda name, mirror: fn(name, mirror)), str(sig)


def _marker_object(name: str, new: list):
    """The marker the helper made or reused for `name`: `<name>_loc`, else the only new object.

    Limb markers get a mirrored `<name>_loc_sym` that follows by constraint;
    it is never the one to move.
    """
    return bpy.data.objects.get(f"{name}_loc") or (new[0] if len(new) == 1 else None)


def _markers(params: dict, info: dict) -> dict:
    helper, where = _marker_helper(info["module"])
    if helper is None:
        return _refuse(params, info, "smart_marker_api_not_found",
                       "the installed add-on exposes no _add_marker helper; place the markers in its Smart panel")
    call, signature = _marker_call(helper)
    if call is None:
        return _refuse(params, info, "smart_marker_signature_unsupported",
                       f"{where}._add_marker{signature}: parameters this op cannot fill without guessing",
                       signature=signature)
    landmarks = params.get("landmarks") or {}
    bad = [k for k, v in landmarks.items() if not (isinstance(v, (list, tuple)) and len(v) == 3)]
    if not landmarks or bad:
        return _refuse(params, info, "landmarks_invalid", f"landmarks need name -> [x, y, z]; bad: {bad}")
    meshes, err = _objects(params, "mesh", 'MESH') if params.get("mesh") else ([], None)
    if err:
        return _refuse(params, info, "object_missing", err)
    scene = bpy.context.scene
    # the helper sizes markers from the body Smart picked and finds it by this name
    if "arp_body_name" in scene.bl_rna.properties and not bpy.data.objects.get(scene.arp_body_name or ""):
        smart = _owned_operators(info["module"]).get("get_selected_objects") or "the Smart button"
        return _refuse(params, info, "smart_not_started",
                       f"Smart has no body yet (scene.arp_body_name is empty or stale): select the mesh "
                       f"and start Smart in the add-on ({smart}) first, then place markers")
    space = Matrix.Identity(4)
    if params.get("armature"):
        rigs, err = _objects(params, "armature", 'ARMATURE')
        if err:
            return _refuse(params, info, "object_missing", err)
        space = rigs[0].matrix_world.copy()
    override = _view3d_override()
    if override is None:
        return _refuse(params, info, "no_view3d_area", "markers need " + _NO_VIEW)

    state = C.save_state(scene, meshes)
    placed, markers = 0, {}
    try:
        if meshes:
            _select_only(meshes, meshes[0])
        for name, xyz in landmarks.items():
            before = set(bpy.data.objects)
            with bpy.context.temp_override(**override):
                call(name, bool(params.get("mirror", True)))
            marker = _marker_object(name, [o for o in bpy.data.objects if o not in before])
            if marker is None:
                markers[name] = {"placed": False, "reason": "the helper left no marker object"}
                continue
            goal = space @ Vector(xyz)
            world = marker.matrix_world.copy()
            world.translation = goal
            marker.matrix_world = world
            # read it back evaluated: the add-on limits limb markers to one side of X
            bpy.context.view_layer.update()
            reached = marker.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation
            miss = (reached - goal).length
            placed += miss <= 1e-4
            markers[name] = {"placed": miss <= 1e-4, "object": marker.name, "miss": miss}
    finally:
        C.restore_state(state)
    gates = [C.gate("arp.markers_placed", placed, len(landmarks), placed == len(landmarks))]
    return C.report(params, gates, op="markers", helper_module=where, markers=markers)


# --- match and bind ----------------------------------------------------------

def _match(params: dict, info: dict) -> dict:
    rigs, err = _objects(params, "armature", 'ARMATURE')
    if err:
        return _refuse(params, info, "object_missing", err)
    rig = rigs[0]
    named, err = _objects(params, "mesh", 'MESH') if params.get("mesh") else ([], None)
    if err:
        return _refuse(params, info, "object_missing", err)
    meshes = [c for c in rig.children if c.type == 'MESH'] + named
    bound = _deform_groups(rig, list(dict.fromkeys(meshes)), weighted=True)
    if bound:
        return _refuse(params, info, "already_bound",
                       "meshes already hold weights for this rig's deform bones; matching again "
                       "changes the rest pose under them. Unbind first, or match before bind.",
                       bound=bound)
    override = _view3d_override()
    if override is None:
        return _refuse(params, info, "no_view3d_area", "match needs " + _NO_VIEW)

    state = C.save_state(bpy.context.scene, [rig])
    try:
        _select_only([rig], rig)
        _call(info["operator_idnames"]["arp.match_to_rig"], override)
        _object_mode()  # bone data is read in object mode, where edits are flushed
        bones = len(rig.data.bones)
        deform = sum(1 for b in rig.data.bones if b.use_deform)
    finally:
        C.restore_state(state)
    expected = params.get("expected_bones")
    gates = [C.gate("arp.bone_count", bones, expected if expected is not None else "> 0",
                    bones == expected if expected is not None else bones > 0)]
    return C.report(params, gates, op="match", armature=rig.name, bone_count=bones,
                    deform_bone_count=deform)


def _scene_value(prop, key: str, value):
    """`value` as the scene property takes it, or None when it cannot take it."""
    if prop.type != 'ENUM':
        return value
    if key == "pseudo_voxels" and isinstance(value, bool):
        value = _ENGINE[value]
    return value if value in {item.identifier for item in prop.enum_items} else None


def _bind_options(params: dict, idname: str) -> tuple[dict, dict, list]:
    """(operator kwargs, scene property values, keys that match nothing).

    Per key: `option_names[key]` when given; else an operator property of the
    key's own name, then the scene property the add-on keeps that setting in.
    Each candidate is checked against the installed RNA before it is used.
    """
    declared, scene_props = _op_props(idname), bpy.types.Scene.bl_rna.properties
    names = params.get("option_names") or {}
    kwargs, scene_values, unmatched = {}, {}, []
    for key, default in _BIND_DEFAULTS.items():
        value = params.get(key, default)
        if value is None:
            continue
        candidates = [names[key]] if key in names else [key, "scene." + _BIND_SCENE[key]]
        for target in candidates:
            if target.startswith("scene."):
                prop = scene_props.get(target[6:])
                fitted = _scene_value(prop, key, value) if prop is not None else None
                if fitted is not None:
                    scene_values[target[6:]] = fitted
                    break
            elif target in declared:
                kwargs[target] = value
                break
        else:
            unmatched.append(key)
    return kwargs, scene_values, unmatched


def _bind(params: dict, info: dict) -> dict:
    rigs, err = _objects(params, "armature", 'ARMATURE')
    meshes, err2 = _objects(params, "mesh", 'MESH')
    if err or err2:
        return _refuse(params, info, "object_missing", err or err2)
    rig = rigs[0]
    deform = {b.name for b in rig.data.bones if b.use_deform}
    if not deform:
        return _refuse(params, info, "no_deform_bones", f"{rig.name!r} has no deform bones: run match first")
    bound = _deform_groups(rig, meshes, weighted=False)
    if bound:
        return _refuse(params, info, "already_bound",
                       "meshes already have groups named after this rig's deform bones", bound=bound)
    idname = info["operator_idnames"]["arp.bind_to_rig"]
    kwargs, scene_values, unmatched = _bind_options(params, idname)
    if unmatched:
        return _refuse(params, info, "bind_option_not_found",
                       f"bind options {unmatched} match no operator or scene property; map them with "
                       "option_names, or pass None to leave the add-on's setting",
                       operator_properties=sorted(_op_props(idname)),
                       scene_properties=sorted(p.identifier for p in bpy.types.Scene.bl_rna.properties
                                               if "bind" in p.identifier.lower()))
    override = _view3d_override()
    if override is None:
        return _refuse(params, info, "no_view3d_area", "bind needs " + _NO_VIEW)

    scene = bpy.context.scene
    state = C.save_state(scene, [rig, *meshes])
    previous = {name: getattr(scene, name) for name in scene_values}
    try:
        for name, value in scene_values.items():
            setattr(scene, name, value)
        _select_only(meshes, rig)
        _call(idname, override, **kwargs)
    finally:
        for name, value in previous.items():
            with contextlib.suppress(AttributeError, TypeError, ValueError):
                setattr(scene, name, value)
        C.restore_state(state)
    counts = {m.name: _unweighted(m, deform) for m in meshes}
    total = sum(counts.values())
    gates = [C.gate("arp.vertices_without_group", total, 0, total == 0)]
    return C.report(params, gates, op="bind", armature=rig.name, vertices_without_group=counts,
                    operator_kwargs=kwargs, scene_settings=scene_values)


# --- retarget ----------------------------------------------------------------

def _map_of(value) -> tuple[str, object] | None:
    """("bones", {target: {"source", ...}}) for a dict, ("config", path) for a saved config,
    ("preset", name) otherwise."""
    if isinstance(value, dict) and value:
        return "bones", {t: dict(v) if isinstance(v, dict) else {"source": v} for t, v in value.items()}
    if not isinstance(value, str) or not value.strip():
        return None
    if value.lower().endswith(".bmap") or "/" in value or "\\" in value:
        return "config", bpy.path.abspath(value)
    return "preset", value


def _preset_property(idname: str) -> str | None:
    declared = _op_props(idname)
    named = [k for k in declared if "preset" in k.lower()]
    if len(named) == 1:
        return named[0]
    text = [k for k, p in declared.items() if p.type in ('STRING', 'ENUM')]
    return text[0] if len(text) == 1 else None


def _bones_list_fields() -> set | None:
    """What one entry of the add-on's bones list declares, or None without the list."""
    prop = bpy.types.Scene.bl_rna.properties.get(_BONES_LIST)
    fixed = getattr(prop, "fixed_type", None)
    return {p.identifier for p in fixed.properties} if fixed is not None else None


def _default_switches(rig) -> dict[str, float]:
    """The switch bones the rig carries, set by ARP's value convention (1 FK, 0 IK)."""
    out = {}
    for bone in rig.pose.bones:
        if _SWITCH in bone.keys():
            value = _SWITCH_CONVENTION.get(bone.name.split(".", 1)[0])
            if value is not None:
                out[bone.name] = value
    return out


def _set_switch(rig, name: str, value: float) -> None:
    bone = rig.pose.bones[name]
    current = bone[_SWITCH]
    bone[_SWITCH] = type(current)(value) if isinstance(current, (int, float)) else float(value)


def _key_switch(rig, name: str, frame: int) -> str:
    bone = rig.pose.bones[name]
    if not bone.keyframe_insert(data_path=f'["{_SWITCH}"]', frame=frame):
        raise RuntimeError(f"could not key {_SWITCH} on {name}")
    return name


def _set_rig(scene, prop: str, obj) -> None:
    pointer = scene.bl_rna.properties[prop].type == 'POINTER'
    setattr(scene, prop, obj if pointer else obj.name)


def _drop_offsets(scene, rig) -> int:
    """Delete rest_transf_offset wherever the clip before left it, so offsets do not carry over."""
    removed = 0
    for holder in (scene, rig, rig.data, *rig.pose.bones):
        if _OFFSET_KEY in holder.keys():
            del holder[_OFFSET_KEY]
            removed += 1
    return removed


def _reset_target(rig) -> str | None:
    """Clear the rig's active action (its fake user kept) and put every pose bone at rest.

    Without this the clip before leaves its last pose and its action under the
    next redefine_rest_pose and bake. Returns the name of the action cleared.
    """
    ad = rig.animation_data
    cleared = None
    if ad is not None and ad.action is not None:
        ad.action.use_fake_user = True
        cleared = ad.action.name
        ad.action = None
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    return cleared


def _apply_bone_map(scene, source, entries: dict) -> int:
    """Write a {target: {"source", ...}} map into the bones list built from `source`.

    Checked against the skeleton just imported: a source bone it lacks raises
    before any rest is touched. Entries for other source bones get no target.
    """
    by_source = {spec["source"]: (target, spec) for target, spec in entries.items()}
    missing = sorted(s for s in by_source if s not in source.data.bones)
    if missing:
        raise KeyError(f"the map names source bone(s) this skeleton lacks: {missing}")
    items = getattr(scene, _BONES_LIST)
    unlisted = sorted(set(by_source) - {item.source_bone for item in items})
    if unlisted:
        raise RuntimeError(f"the add-on's bones list has no entry for {unlisted}")
    for item in items:
        target, spec = by_source.get(item.source_bone, ("", {}))
        item.name = target
        for key, value in spec.items():
            if key != "source":
                setattr(item, key, value)
    return len(by_source)


def _excluded(source, names) -> list[str]:
    """`names` and every bone below them in the source skeleton (a hand takes its fingers)."""
    bones = source.data.bones
    unknown = sorted(n for n in names if n not in bones)
    if unknown:
        raise KeyError(f"exclude names bone(s) this skeleton lacks: {unknown}")
    out = set()
    for name in names:
        out.add(name)
        out.update(child.name for child in bones[name].children_recursive)
    return sorted(out)


def _drop_entries(scene, names) -> int:
    items = getattr(scene, _BONES_LIST)
    drop = [i for i, item in enumerate(items) if item.source_bone in set(names)]
    for i in reversed(drop):
        items.remove(i)
    return len(drop)


def _mapped_bones(scene, source, rig) -> list[str] | None:
    """Source bones the loaded bones list maps onto a bone of the rig; None if it is unreadable."""
    try:
        return [item.source_bone for item in getattr(scene, _BONES_LIST)
                if item.source_bone in source.pose.bones and item.name in rig.pose.bones]
    except AttributeError:
        return None


def _select_bones(source, names) -> int:
    """Select exactly `names` on the source. The add-on aligns the selected pose bones."""
    bones = source.pose.bones
    wanted = set(names)
    unknown = sorted(wanted - {b.name for b in bones})
    if unknown:
        raise KeyError(f"source skeleton has no bone(s) {unknown}")
    for bone in bones:
        if "select" in bone.bl_rna.properties:  # 5.x keeps selection on the pose bone
            bone.select = bone.name in wanted
        else:
            bone.bone.select = bone.name in wanted
    return len(wanted)


def _produced(rig, before: set):
    new = [a for a in bpy.data.actions if a not in before]
    ad = rig.animation_data
    if ad is not None and ad.action is not None and ad.action in new:
        return ad.action
    if len(new) == 1:
        return new[0]
    raise RuntimeError(f"cannot tell which action the retarget made; new: {sorted(a.name for a in new)}")


def _source_of(scene, prop: str):
    """The source skeleton the add-on points at now: freezing it may replace the object."""
    value = getattr(scene, prop)
    obj = bpy.data.objects.get(value) if isinstance(value, str) else value
    if obj is None:
        raise RuntimeError(f"scene.{prop} names no object")
    return obj


def _metadata_plan(clip: dict, params: dict) -> tuple[dict, list[str]]:
    """(custom properties for the clip's action, problems). Read before any bake.

    Provenance first: brt_clip, brt_source_file, then brt_origin and brt_family
    when the clip or the call gives `origin` / `family`; then `metadata` (the
    call's, then the clip's); then `metadata_fields` {property: clip key}, each
    key required in every clip.
    """
    label = clip.get("name") or "?"
    out = {k: v for k, v in (("brt_clip", clip.get("name")), ("brt_source_file", clip.get("fbx"))) if v}
    for key in ("origin", "family"):
        value = clip.get(key, params.get(key))
        if value is not None:
            out[f"brt_{key}"] = value
    out.update(params.get("metadata") or {})
    out.update(clip.get("metadata") or {})
    problems = []
    for prop, field in (params.get("metadata_fields") or {}).items():
        if field in clip:
            out[prop] = clip[field]
        else:
            problems.append(f"clip {label}: no {field!r} for metadata {prop!r}")
    for key, value in out.items():
        if not isinstance(key, str) or not key or len(key.encode()) > 63:
            problems.append(f"clip {label}: {key!r} cannot name a custom property (1-63 bytes)")
        elif not isinstance(value, (str, int, float)):     # bool is an int
            problems.append(f"clip {label}: metadata {key!r} is a {type(value).__name__}; "
                            "give a string or a number")
        elif isinstance(value, float) and not math.isfinite(value):
            problems.append(f"clip {label}: metadata {key!r} is not finite")
    return out, problems


def _cleanup(tracker, keep: set) -> None:
    """Remove what the clip's import brought, except the datablocks in `keep`."""
    held = [c for c in tracker.new("collections") if any(o in keep for o in c.all_objects)]
    gone = [d for kind in _CLIP_KINDS for d in tracker.new(kind) if d not in keep and d not in held]
    if gone:
        bpy.data.batch_remove(gone)


def _clip(plan: dict, rig_name: str, ids: dict, preset_key, override, props: tuple,
          keep_source: bool) -> dict:
    scene = bpy.context.scene
    tracker = C.Tracker()
    rig = bpy.data.objects[rig_name]
    out = {"name": plan["name"], "action": None,
           "bake": {"ok": False, "stage": None, "error": None},
           "metadata": {"ok": None, "error": None, "written": []}}
    stage = "reset"
    try:
        _object_mode()
        out["cleared_action"] = _reset_target(rig)
        for name, value in plan["switches"].items():
            _set_switch(rig, name, value)
        stage = "import"
        bpy.ops.import_scene.fbx(filepath=plan["fbx"])
        sources = [o for o in tracker.new("objects") if o.type == 'ARMATURE']
        if len(sources) != 1:
            raise RuntimeError(f"the FBX holds {len(sources)} armatures; one source skeleton is needed")
        source_action = sources[0].animation_data.action if sources[0].animation_data else None
        if plan["frames"] is not None:
            start, end = plan["frames"]
        elif source_action is not None:
            start, end = (int(round(f)) for f in source_action.frame_range)
        else:
            raise RuntimeError("the FBX skeleton carries no action and the clip gives no frame range")
        stage = "source/target"
        # target first: setting the source runs the add-on's update, which reads the target
        _set_rig(scene, props[1], rig)
        _set_rig(scene, props[0], sources[0])

        stage = "freeze_armature"
        _call(ids["arp.freeze_armature"], override, arm='source')
        source = _source_of(scene, props[0])    # freezing may replace the object: re-read it
        stage = "build_bones_list"
        _call(ids["arp.build_bones_list"], override)
        kind, value = plan["map"]
        stage = f"import {kind}"
        if kind == "config":
            _call(ids["arp.import_config"], override, filepath=value)
        elif kind == "preset":
            _call(ids["arp.import_config_preset"], override, **{preset_key: value})
        else:
            _apply_bone_map(scene, source, value)
        stage = "exclude"
        excluded = _excluded(source, plan["exclude"]) if plan["exclude"] else []
        out["excluded"] = _drop_entries(scene, excluded) if excluded else 0
        stage = "check map"
        mapped = _mapped_bones(scene, source, rig)
        if mapped is not None and not mapped:
            raise RuntimeError("the bones list maps no bone of this source skeleton onto the rig")
        out["mapped"] = len(mapped) if mapped is not None else None
        stage = "offsets"
        out["offsets_removed"] = _drop_offsets(scene, rig)
        stage = "redefine_rest_pose"
        _call(ids["arp.redefine_rest_pose"], override, preserve=True, rest_pose='REST')
        stage = "align"
        source = _source_of(scene, props[0])
        align = plan["align"] if plan["align"] is not None else mapped
        if align is None:
            raise RuntimeError("the add-on's bones list cannot be read; give the clip an `align` list")
        out["aligned"] = _select_bones(source, [b for b in align if b not in excluded])
        stage = "copy_bone_rest"
        _call(ids["arp.copy_bone_rest"], override)
        stage = "save_pose_rest"
        _call(ids["arp.save_pose_rest"], override)
        stage = "retarget"
        before = set(bpy.data.actions)
        _object_mode()
        bpy.context.view_layer.objects.active = rig
        _call(ids["arp.retarget"], override, frame_start=start, frame_end=end, fake_user_action=True)

        stage = "action"
        rig = bpy.data.objects[rig_name]          # re-fetch: operators may replace objects
        action = _produced(rig, before)
        action.name = plan["name"]
        action.use_fake_user = True
        ad = rig.animation_data
        if ad is None or ad.action != action or getattr(ad, "action_slot", True) is None:
            C.assign_slot(rig, action)
        out["switches_keyed"] = [_key_switch(rig, name, start) for name in plan["switches"]]
        if hasattr(action, "slots") and not len(action.slots):
            raise RuntimeError(f"action {action.name!r} has no slot")
        if not C.action_slot_fcurves(action):
            raise RuntimeError(f"action {action.name!r} has no curves")
        out.update(action=action.name, frames=[start, end])
        stage = "cleanup"
        _object_mode()
        source = _source_of(scene, props[0])
        keep = {action}
        if keep_source:
            keep |= {source, source.data}
            keep |= {a for a in ([source.animation_data.action] if source.animation_data else []) if a}
            source.name = f"{plan['name']}_Source"
            source["brt_clip"] = plan["name"]
            source.hide_render = True
            with contextlib.suppress(RuntimeError):
                source.hide_set(True)
            out["source_object"] = source.name
        _cleanup(tracker, keep)
        out["bake"].update(ok=True, stage="done")
    except Exception as exc:  # one clip fails alone; the batch goes on
        with contextlib.suppress(RuntimeError):
            _object_mode()
        tracker.rollback()
        out.update(action=None)
        out["bake"].update(stage=stage, error=f"{stage}: {type(exc).__name__}: {exc}")
        out["metadata"]["error"] = "not run: the bake failed"
        return out

    # a separate phase: a failure here keeps the bake and says so
    try:
        action = bpy.data.actions[out["action"]]
        for key, value in plan["metadata"].items():
            action[key] = value
            out["metadata"]["written"].append(key)
        out["metadata"]["ok"] = True
    except Exception as exc:
        out["metadata"].update(ok=False, error=f"{type(exc).__name__}: {exc}")
    return out


def _armature_modifiers(rig) -> list[tuple[str, str]]:
    """(mesh, modifier) of every armature modifier driven by `rig` that shows in the viewport."""
    return [(obj.name, mod.name) for obj in bpy.data.objects if obj.type == 'MESH'
            for mod in obj.modifiers if mod.type == 'ARMATURE' and mod.object == rig and mod.show_viewport]


def _show_modifiers(pairs, visible: bool) -> None:
    for obj_name, mod_name in pairs:
        obj = bpy.data.objects.get(obj_name)
        mod = obj.modifiers.get(mod_name) if obj is not None else None
        if mod is not None:
            mod.show_viewport = visible


def _write_progress(params: dict, results: list) -> None:
    path = params.get("progress_path")
    if path:
        with open(bpy.path.abspath(path), "w", encoding="utf-8") as handle:
            json.dump(C.safe({"clips": results}), handle, indent=2)


def _plans(params: dict, rig) -> tuple[list, list, list, list]:
    """(one plan per clip, problems, metadata problems, warnings): everything
    checked before any change. Metadata problems are the ones _metadata_plan finds."""
    plans, problems, meta_problems, warnings = [], [], [], []
    fields = _bones_list_fields()
    top_switches = params.get("switches")
    for i, clip in enumerate(params.get("clips") or []):
        name, fbx = clip.get("name"), clip.get("fbx") or ""
        label = name or i
        mapping = _map_of(clip.get("map", params.get("map")))
        path = bpy.path.abspath(fbx)
        if not name:
            problems.append(f"clip {i}: no name")
        if "://" in fbx or not os.path.isfile(path):
            problems.append(f"clip {label}: fbx is not a local file")
        if mapping is None:
            problems.append(f"clip {label}: no map (a preset name, a config path, or {{target: source}})")
        elif mapping[0] == "config" and not os.path.isfile(mapping[1]):
            problems.append(f"clip {label}: map config is not a file")
        elif mapping[0] == "bones":
            entries = mapping[1]
            absent = sorted(t for t in entries if t not in rig.pose.bones)
            bad = sorted(t for t, spec in entries.items() if not isinstance(spec.get("source"), str))
            sources = [spec.get("source") for spec in entries.values()]
            twice = sorted({s for s in sources if sources.count(s) > 1 and isinstance(s, str)})
            extras = {k for spec in entries.values() for k in spec if k != "source"}
            if fields is None:
                problems.append(f"clip {label}: a {{target: source}} map needs the add-on's "
                                f"scene.{_BONES_LIST}, which this scene lacks")
            elif extras - fields:
                problems.append(f"clip {label}: bones list entries declare no {sorted(extras - fields)}; "
                                f"they have {sorted(fields)}")
            if absent:
                problems.append(f"clip {label}: the rig has no bone(s) {absent}")
            if bad:
                problems.append(f"clip {label}: map entries without a source bone name: {bad}")
            if twice:
                problems.append(f"clip {label}: source bones mapped twice: {twice}")
        frames = (clip["frame_start"], clip["frame_end"]) if "frame_start" in clip and "frame_end" in clip else None
        if ("frame_start" in clip) != ("frame_end" in clip):
            problems.append(f"clip {label}: give both frame_start and frame_end, or neither")
        exclude = clip.get("exclude", params.get("exclude")) or []
        if isinstance(exclude, str) or not all(isinstance(n, str) for n in exclude):
            problems.append(f"clip {label}: exclude is a list of source bone names")
            exclude = []
        given = clip.get("switches", top_switches)
        if given is None:
            switches = _default_switches(rig)
        elif isinstance(given, dict):
            switches = {}
            for bone, value in given.items():
                if bone not in rig.pose.bones or _SWITCH not in rig.pose.bones[bone].keys():
                    problems.append(f"clip {label}: no {_SWITCH} property on {bone!r}")
                elif isinstance(value, bool) or not isinstance(value, (int, float)):
                    problems.append(f"clip {label}: switch {bone!r} needs a number (1 FK, 0 IK)")
                else:
                    switches[bone] = float(value)
        else:
            problems.append(f"clip {label}: switches is {{bone: value}}, {{}} or None")
            switches = {}
        metadata, bad_meta = _metadata_plan(clip, params)
        meta_problems += bad_meta
        if name and bpy.data.actions.get(name) is not None:
            warnings.append(f"an action named {name!r} exists: this clip's action will get a suffix. "
                            "Delete test actions or bake under a staging name first.")
        plans.append({"name": name, "fbx": path, "map": mapping, "frames": frames,
                      "align": clip.get("align", params.get("align")), "exclude": list(exclude),
                      "switches": switches, "metadata": metadata})
    names = [p["name"] for p in plans if p["name"]]
    twice = sorted({n for n in names if names.count(n) > 1})
    if twice:
        problems.append(f"clip names used twice: {twice}")
    if plans and top_switches is None and not any(p["switches"] for p in plans):
        warnings.append(f"no pose bone of {rig.name!r} carries {_SWITCH}: no IK/FK switch is set or keyed")
    return plans, problems, meta_problems, warnings


def _snapshot(scene, rig) -> dict:
    """What a clip changes on datablocks that already exist: every pose bone's
    matrix_basis, the IK/FK switch values and the rest_transf_offset properties.
    A dry run puts these back; a real batch keeps the changes."""
    holders = {"scene": scene, "rig": rig, "data": rig.data,
               **{f"bone:{b.name}": b for b in rig.pose.bones}}
    offsets = {}
    for key, holder in holders.items():
        if _OFFSET_KEY in holder.keys():
            value = holder[_OFFSET_KEY]
            offsets[key] = value.to_dict() if hasattr(value, "to_dict") else \
                (value.to_list() if hasattr(value, "to_list") else value)
    return {"basis": {b.name: b.matrix_basis.copy() for b in rig.pose.bones},
            "switches": {b.name: b[_SWITCH] for b in rig.pose.bones if _SWITCH in b.keys()},
            "offsets": offsets}


def _restore_snapshot(snap: dict, scene, rig) -> None:
    """Put a _snapshot back. Best effort, so it is safe in a `finally:`."""
    with contextlib.suppress(ReferenceError):
        holders = {"scene": scene, "rig": rig, "data": rig.data,
                   **{f"bone:{b.name}": b for b in rig.pose.bones}}
        for key, holder in holders.items():
            if key in snap["offsets"]:
                holder[_OFFSET_KEY] = snap["offsets"][key]
            elif _OFFSET_KEY in holder.keys():
                del holder[_OFFSET_KEY]
        for name, value in snap["switches"].items():
            if name in rig.pose.bones:
                rig.pose.bones[name][_SWITCH] = value
        for name, basis in snap["basis"].items():
            if name in rig.pose.bones:
                rig.pose.bones[name].matrix_basis = basis


def _retarget(params: dict, info: dict) -> dict:
    rigs, err = _objects(params, "armature", 'ARMATURE')
    if err:
        return _refuse(params, info, "object_missing", err)
    rig = rigs[0]
    if not params.get("clips"):
        return _refuse(params, info, "no_clips", "params['clips'] lists no clip")
    if rig.animation_data is not None and rig.animation_data.use_tweak_mode:
        return _refuse(params, info, "nla_tweak_mode", f"{rig.name!r} is in NLA tweak mode: exit it first")
    plans, problems, meta_problems, warnings = _plans(params, rig)
    if meta_problems:
        return _refuse(params, info, "metadata_invalid",
                       "the metadata step would fail; no clip was baked: " + "; ".join(meta_problems),
                       problems=meta_problems + problems)
    if problems:
        return _refuse(params, info, "clip_invalid", "; ".join(problems))

    kinds = {p["map"][0] for p in plans}
    needed = list(_REMAP) + (["arp.import_config"] if "config" in kinds else []) \
        + (["arp.import_config_preset"] if "preset" in kinds else [])
    missing = [n for n in needed if not info["operators"][n]]
    if missing:
        return _refuse(params, info, "operator_missing", f"the installed add-on registers no {missing}")
    if not _registered("import_scene.fbx"):
        return _refuse(params, info, "fbx_importer_missing", "enable Blender's FBX importer")
    ids = info["operator_idnames"]
    wanted = {**_REMAP_KWARGS, **({"arp.import_config": ("filepath",)} if "config" in kinds else {})}
    absent = {n: [k for k in keys if k not in _op_props(ids[n])] for n, keys in wanted.items()}
    absent = {n: keys for n, keys in absent.items() if keys}
    preset_key = _preset_property(ids["arp.import_config_preset"]) if "preset" in kinds else None
    if "preset" in kinds and preset_key is None:
        absent["arp.import_config_preset"] = ["<preset name>"]
    if absent:
        return _refuse(params, info, "operator_property_missing",
                       f"the installed operators lack {absent}", operator_properties=info["operator_properties"])
    props = (params.get("source_prop", "source_rig"), params.get("target_prop", "target_rig"))
    scene_props = bpy.types.Scene.bl_rna.properties
    if any(p not in scene_props for p in props):
        return _refuse(params, info, "scene_property_missing",
                       f"the scene has no {[p for p in props if p not in scene_props]}; "
                       "name the add-on's source/target properties with source_prop / target_prop",
                       scene_properties=sorted(p.identifier for p in scene_props if "rig" in p.identifier.lower()))

    dry_run = bool(params.get("dry_run", False))
    todo = plans[:1] if dry_run else plans
    scene = bpy.context.scene
    override = _view3d_override()  # used when there is one; the remap operators are not drawn
    state = C.save_state(scene, [rig])
    previous = {p: getattr(scene, p) for p in props}
    paused = _armature_modifiers(rig) if params.get("pause_deform", True) else []
    trial = C.Tracker() if dry_run else None
    snap = _snapshot(scene, rig) if dry_run else None
    results = []
    try:
        _show_modifiers(paused, False)
        for i, plan in enumerate(todo):
            if i and params.get("stop_if_first_fails", True) and not (
                    results[0]["bake"]["ok"] and results[0]["metadata"]["ok"]):
                results.append({"name": plan["name"], "action": None,
                                "bake": {"ok": False, "stage": None, "error": "skipped: the first clip failed"},
                                "metadata": {"ok": None, "error": "skipped", "written": []}})
                continue
            results.append(_clip(plan, rig.name, ids, preset_key, override, props,
                                 params.get("keep_source", False)))
            _write_progress(params, results)
    finally:
        _show_modifiers(paused, True)
        for prop, value in previous.items():
            with contextlib.suppress(AttributeError, TypeError, ValueError, ReferenceError):
                setattr(scene, prop, value)
        C.restore_state(state)
        if trial is not None:
            trial.rollback()               # a dry run leaves no action and no import behind
        if snap is not None:
            _restore_snapshot(snap, scene, rig)   # nor a changed pose, switch or offset
    baked = sum(1 for r in results if r["bake"]["ok"])
    stamped = sum(1 for r in results if r["metadata"]["ok"])
    duplicates = [{"clip": r["name"], "action": r["action"]} for r in results
                  if r["action"] and r["action"] != r["name"]]
    gates = [C.gate("arp.retarget_clips", baked, len(todo), baked == len(todo)),
             C.gate("arp.metadata_clips", stamped, len(todo), stamped == len(todo))]
    if dry_run:
        warnings.append(f"dry run: the first of {len(plans)} clip(s) ran end to end and was rolled back")
    return C.report(params, gates, op="retarget", armature=rig.name, clips=results, dry_run=dry_run,
                    clips_planned=len(plans), duplicate_suffixes=duplicates,
                    switches={p["name"]: p["switches"] for p in todo},
                    paused_modifiers=len(paused), warnings=warnings)


# --- source skeletons --------------------------------------------------------

def _source_bones(params: dict) -> dict:
    """Import each FBX, read its skeleton, take the import back. Needs no add-on."""
    value = params.get("fbx")
    files = [value] if isinstance(value, str) else list(value or [])
    mapping = _map_of(params.get("map")) if params.get("map") else None
    if mapping is not None and mapping[0] != "bones":
        mapping = None
    wanted = sorted({spec.get("source") for spec in mapping[1].values()}) if mapping else []
    bad = [f for f in files if "://" in f or not os.path.isfile(bpy.path.abspath(f))]
    if not files or bad:
        gates = [C.gate("arp.precondition", "clip_invalid", "met", False)]
        return C.report(params, gates, op="source_bones", reason="clip_invalid",
                        message=f"fbx must name local files; not files: {len(bad)} of {len(files)}")
    if not _registered("import_scene.fbx"):
        gates = [C.gate("arp.precondition", "fbx_importer_missing", "met", False)]
        return C.report(params, gates, op="source_bones", reason="fbx_importer_missing",
                        message="enable Blender's FBX importer")
    state = C.save_state(bpy.context.scene, [])
    out = []
    try:
        for f in files:
            tracker = C.Tracker()
            entry = {"fbx": os.path.basename(f)}
            try:
                _object_mode()
                bpy.ops.import_scene.fbx(filepath=bpy.path.abspath(f))
                arms = [o for o in tracker.new("objects") if o.type == 'ARMATURE']
                entry["armatures"] = len(arms)
                if len(arms) == 1:
                    arm = arms[0]
                    names = [b.name for b in arm.data.bones]
                    action = arm.animation_data.action if arm.animation_data else None
                    entry.update(
                        bones=[{"name": b.name, "parent": b.parent.name if b.parent else None}
                               for b in arm.data.bones],
                        skeleton=hashlib.sha1("\n".join(sorted(names)).encode()).hexdigest()[:12],
                        frame_range=list(action.frame_range) if action else None)
                    if mapping:
                        entry["map_missing"] = [s for s in wanted if s not in arm.data.bones]
            except Exception as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                with contextlib.suppress(RuntimeError):
                    _object_mode()
                tracker.rollback()
            out.append(entry)
    finally:
        C.restore_state(state)
    one = sum(1 for e in out if e.get("armatures") == 1)
    gates = [C.gate("arp.source_skeleton_found", one, len(files), one == len(files))]
    if mapping:
        lacking = sum(len(e.get("map_missing", wanted)) for e in out)
        gates.append(C.gate("arp.map_sources_found", lacking, 0, lacking == 0))
    return C.report(params, gates, op="source_bones", files=out,
                    skeletons=len({e["skeleton"] for e in out if "skeleton" in e}))

# --- pipeline: markers -> match -> bind -> export -> skeleton ---------------------

# reference bones the markers must place (the .r side is mirrored from .l)
_REQUIRED_REFS = ("root_ref.x", "neck_ref.x", "head_ref.x", "shoulder_ref.l", "arm_ref.l",
                  "forearm_ref.l", "hand_ref.l", "thigh_ref.l", "leg_ref.l", "foot_ref.l", "toes_ref.l")
# scene settings of the add-on's exporter: Unity, humanoid, the master trajectory as the root bone
_EXPORT_SCENE = {"arp_engine_type": 'UNITY', "arp_export_rig_type": 'HUMANOID', "arp_ge_master_traj": True}
_LICENCE = {"source": "auto-rig-pro", "territory": "worldwide"}


def _mirror_name(name: str) -> str:
    return name[:-2] + ".r" if name.endswith(".l") else name


def _load_markers(value) -> tuple[dict | None, str | None]:
    if isinstance(value, str):
        try:
            with open(os.path.abspath(bpy.path.abspath(value)), encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, ValueError) as exc:
            return None, f"markers file unreadable: {exc}"
    if not isinstance(value, dict) or not isinstance(value.get("arp_refs"), dict):
        return None, "markers need an arp_markers.py result (an `arp_refs` object)"
    bad = [k for k, v in value["arp_refs"].items()
           if not (isinstance(v, dict) and all(isinstance(v.get(e), (list, tuple)) and len(v[e]) == 3
                                               for e in ("head", "tail")))]
    missing = [k for k in _REQUIRED_REFS if k not in value["arp_refs"]]
    if bad or missing:
        return None, f"arp_refs malformed {bad} or missing {missing}"
    return value, None


def _spine_refs(rig) -> list[str]:
    return sorted(b.name for b in rig.data.bones if b.name.startswith("spine_") and b.name.endswith("_ref.x"))


def _set_spine(rig, count: int, override: dict, idname: str) -> None:
    """Auto-Rig Pro's spine Count (its root counts: 4 = root + three spine bones)."""
    _select_only([rig], rig)
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        bones = rig.data.edit_bones
        for eb in bones:
            eb.select = eb.select_head = eb.select_tail = False
        root = bones["root_ref.x"]
        root.select = root.select_head = root.select_tail = True
        bones.active = root
        with bpy.context.temp_override(selected_editable_bones=[root], active_bone=root, **override):
            result = _op(idname)('EXEC_DEFAULT', limb_type="spine", spine_count=count)
        if 'FINISHED' not in result:
            raise RuntimeError(f"{idname} returned {sorted(result)}")
    finally:
        _object_mode()


def _hand_turn(rig_space: Matrix, refs: dict, frames: dict, old: dict):
    """The rotation taking the preset's left hand frame to the measured one, or None."""
    frame = frames.get(".L") if isinstance(frames, dict) else None
    if not frame or "hand_ref.l" not in old:
        return None
    head, tail, z = old["hand_ref.l"]
    x_p = (tail - head).normalized()
    z_p = (z - x_p * z.dot(x_p)).normalized()
    p = Matrix((x_p, z_p.cross(x_p), z_p)).transposed()
    to_rig = rig_space.to_3x3()
    x_n = (to_rig @ Vector(frame["x"])).normalized()
    z_n = to_rig @ Vector(frame["z"])
    z_n = (z_n - x_n * z_n.dot(x_n)).normalized()
    n = Matrix((x_n, z_n.cross(x_n), z_n)).transposed()
    return n @ p.transposed()


def _place_refs(rig, refs: dict, frames: dict) -> dict:
    """Write each ref bone's head and tail (world -> rig space), .l mirrored to .r.

    A bone keeps the preset's roll direction (align_roll to its old Z); hand and finger bones
    turn that Z with the hand, so a palm-in hand gets palm-in finger rolls. Returns
    {placed, missing, worst_miss_m}.
    """
    inv = rig.matrix_world.inverted()
    wanted = {}
    for name, ends in refs.items():
        head, tail = Vector(ends["head"]), Vector(ends["tail"])
        wanted[name] = (inv @ head, inv @ tail)
        if name.endswith(".l") and _mirror_name(name) not in refs:
            wanted[_mirror_name(name)] = (inv @ Vector((-head.x, head.y, head.z)),
                                          inv @ Vector((-tail.x, tail.y, tail.z)))
    _select_only([rig], rig)
    bpy.ops.object.mode_set(mode='EDIT')
    missing, worst = [], 0.0
    try:
        bones = rig.data.edit_bones
        old = {n: (bones[n].head.copy(), bones[n].tail.copy(), bones[n].z_axis.copy())
               for n in wanted if n in bones}
        turn = _hand_turn(inv, refs, frames, old)
        mirror = Matrix.Scale(-1, 3, Vector((1, 0, 0)))
        # parents first, so a connected child's head lands where its parent's tail was put
        order = sorted((n for n in wanted if n in bones), key=lambda n: len(bones[n].parent_recursive))
        for name in order:
            eb = bones[name]
            z_old = old[name][2]
            head, tail = wanted[name]
            eb.head, eb.tail = head, tail
            stem = name.split("_", 1)[0].rstrip("0123456789")
            if turn is not None and stem in ("hand", "thumb", "index", "middle", "ring", "pinky"):
                z_new = turn @ (mirror @ z_old) if name.endswith(".r") else turn @ z_old
                z_old = mirror @ z_new if name.endswith(".r") else z_new
            eb.align_roll(z_old)
        missing = sorted(n for n in wanted if n not in bones)
        for name in order:
            eb = bones[name]
            worst = max(worst, (eb.head - wanted[name][0]).length, (eb.tail - wanted[name][1]).length)
    finally:
        _object_mode()
    return {"placed": len(wanted) - len(missing), "missing": missing, "worst_miss_m": worst}


def _weighted(rig, meshes) -> tuple[set, dict]:
    """(bone names some vertex holds a weight > 0 for, per mesh {vertices, unweighted, max_influences})."""
    bones = {b.name for b in rig.data.bones}
    used, stats = set(), {}
    for obj in meshes:
        names = {g.index: g.name for g in obj.vertex_groups if g.name in bones}
        unweighted, most = 0, 0
        for v in obj.data.vertices:
            hits = [names[g.group] for g in v.groups if g.group in names and g.weight > 0]
            used.update(hits)
            unweighted += not hits
            most = max(most, len(hits))
        stats[obj.name] = {"vertices": len(obj.data.vertices), "unweighted": unweighted,
                           "max_influences": most}
    return used, stats


def _reimport(fbx: str) -> tuple[dict | None, dict, str | None]:
    """Import the FBX, read its skeleton and skin, take the import back. (skeleton, stats, error)."""
    sub = C.Tracker()
    try:
        bpy.ops.import_scene.fbx(filepath=fbx)
        objects = sub.new("objects")
        rigs = [o for o in objects if o.type == 'ARMATURE']
        if len(rigs) != 1:
            return None, {"armatures": len(rigs)}, f"the file holds {len(rigs)} armatures, 1 expected"
        rig = rigs[0]
        meshes = [o for o in objects if o.type == 'MESH'
                  and any(m.type == 'ARMATURE' and m.object == rig for m in o.modifiers)]
        used, stats = _weighted(rig, meshes)
        mw = rig.matrix_world
        bones = [{"name": b.name, "parent": b.parent.name if b.parent else None,
                  "head": [round(x, 6) for x in mw @ b.head_local],
                  "tail": [round(x, 6) for x in mw @ b.tail_local],
                  "deform": b.name in used} for b in rig.data.bones]
        skeleton = {"schema": "skeleton/1", "source": "auto-rig-pro export (FBX re-import)",
                    "up": "+Z", "forward": "-Y", "units": "m", "bones": bones}
        return skeleton, {"armatures": 1, "armature_scale": list(rig.scale), "meshes": stats}, None
    finally:
        sub.rollback()


def _scene_settings(scene, wanted: dict) -> tuple[dict, list]:
    """(previous values, names the scene does not have) for the add-on's scene settings."""
    props = scene.bl_rna.properties
    missing = [k for k in wanted if k not in props]
    return {k: getattr(scene, k) for k in wanted if k in props}, missing


def _export_and_read(params: dict, ids: dict, override: dict, scene, export: dict, rig, meshes: list,
                     fbx: str, limit: int, gates: list, out: dict) -> None:
    """Export the rig and its meshes with the add-on's FBX exporter (the scene settings in
    `export` set for the call and put back), import the file again, write its skeleton and take
    the import back. Appends the export gates to `gates` and the results to `out`."""
    previous, _ = _scene_settings(scene, export)
    try:
        for name, value in export.items():
            setattr(scene, name, value)
        if os.path.exists(fbx):
            os.remove(fbx)
        _select_only([rig, *meshes], rig)
        _call(ids["arp.arp_export_fbx_panel"], override, filepath=fbx)
    finally:
        for name, value in previous.items():
            with contextlib.suppress(AttributeError, TypeError, ValueError):
                setattr(scene, name, value)
        _object_mode()
    size = os.path.getsize(fbx) if os.path.exists(fbx) else 0
    gates.append(C.gate("arp.export_written", size, "> 0", size > 0))
    out["export"] = {"fbx": fbx, "bytes": size, "scene_settings": export}
    if not size:
        return
    skeleton, stats, err = _reimport(fbx)
    out["reimport"] = stats
    gates.append(C.gate("arp.export_armatures", stats.get("armatures"), 1, err is None))
    if err is not None:
        return
    loose = sum(m["unweighted"] for m in stats["meshes"].values())
    most = max((m["max_influences"] for m in stats["meshes"].values()), default=0)
    gates.append(C.gate("arp.export_unweighted", loose, 0, loose == 0))
    gates.append(C.gate("arp.export_max_influences", most, limit, most <= limit))
    out["skeleton_bones"] = len(skeleton["bones"])
    path = os.path.abspath(bpy.path.abspath(params.get("skeleton_out") or fbx[:-4] + ".skeleton.json"))
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(skeleton, handle, indent=1)
    out["skeleton"] = path
    out["next"] = (f"python3 <unity-rigged-character>/scripts/contract_map.py map {path} "
                   "--map arp --require contract --min-fingers 30")


def _limit_influences(meshes: list, limit: int) -> None:
    """Unity keeps 4 weights per vertex by default and renormalises; do it here, where the deform
    gate sees it, over deform bones only."""
    for mesh in meshes:
        _select_only([mesh], mesh)
        bpy.ops.object.vertex_group_limit_total(group_select_mode='BONE_DEFORM', limit=limit)
        bpy.ops.object.vertex_group_normalize_all(group_select_mode='BONE_DEFORM', lock_active=False)


def _export(params: dict, info: dict) -> dict:
    """Re-export a rig the pipeline bound (after a weight repair) with the pipeline's settings."""
    rigs, err = _objects(params, "armature", 'ARMATURE')
    if err:
        return _refuse(params, info, "object_missing", err)
    rig = rigs[0]
    if params.get("mesh"):
        meshes, err = _objects(params, "mesh", 'MESH')
        if err:
            return _refuse(params, info, "object_missing", err)
    else:
        meshes = [o for o in bpy.data.objects if o.type == 'MESH'
                  and any(m.type == 'ARMATURE' and m.object == rig for m in o.modifiers)]
    fbx = os.path.abspath(bpy.path.abspath(params.get("fbx") or "")) if params.get("fbx") else ""
    if not fbx.lower().endswith(".fbx"):
        return _refuse(params, info, "export_path_missing", "`fbx` names the FBX file the export writes")
    used, _ = _weighted(rig, meshes)
    if not meshes or not used & {b.name for b in rig.data.bones if b.use_deform}:
        return _refuse(params, info, "not_bound",
                       f"no mesh holds weights for a deform bone of {rig.name!r}: bind it first (op pipeline)")
    scene = bpy.context.scene
    export = dict(_EXPORT_SCENE, arp_units_x100=bool(params.get("units_x100", True)))
    _, missing = _scene_settings(scene, export)
    if missing:
        return _refuse(params, info, "export_setting_missing",
                       f"the installed add-on keeps no scene setting {missing}; read its export panel")
    override = _view3d_override()
    if override is None:
        return _refuse(params, info, "no_view3d_area", "the export needs " + _NO_VIEW)
    limit = int(params.get("max_influences", 4))
    gates, out = [], {"op": "export", "armature": rig.name, "meshes": [m.name for m in meshes]}
    state = C.save_state(scene, meshes)
    try:
        _object_mode()
        if params.get("limit_influences", True):
            _limit_influences(meshes, limit)
        deform = {b.name for b in rig.data.bones if b.use_deform}
        loose = sum(_unweighted(m, deform) for m in meshes)
        gates.append(C.gate("arp.vertices_without_group", loose, 0, loose == 0))
        out["influences_limited_to"] = limit if params.get("limit_influences", True) else None
        _export_and_read(params, info["operator_idnames"], override, scene, export, rig, meshes, fbx, limit,
                         gates, out)
    finally:
        C.restore_state(state)
    result = C.report(params, gates, **out)
    result["record"]["licence"] = dict(_LICENCE)
    return result


def _pipeline(params: dict, info: dict, tracker: C.Tracker) -> dict:
    meshes, err = _objects(params, "mesh", 'MESH')
    if err:
        return _refuse(params, info, "object_missing", err)
    mesh = meshes[0]
    markers, err = _load_markers(params.get("markers"))
    if err:
        return _refuse(params, info, "markers_invalid", err)
    fbx = os.path.abspath(bpy.path.abspath(params.get("fbx") or "")) if params.get("fbx") else ""
    if not fbx.lower().endswith(".fbx"):
        return _refuse(params, info, "export_path_missing", "`fbx` names the FBX file the export writes")
    rig_name = params.get("armature") or f"{mesh.name}Rig"
    if bpy.data.objects.get(rig_name) is not None:
        return _refuse(params, info, "rig_exists",
                       f"an object named {rig_name!r} exists: rename or remove it")
    if any(m.type == 'ARMATURE' for m in mesh.modifiers):
        return _refuse(params, info, "already_bound", f"{mesh.name!r} already has an Armature modifier")
    if any(abs(x - 1) > 1e-4 for x in mesh.scale) or any(abs(x) > 1e-4 for x in mesh.rotation_euler):
        return _refuse(params, info, "transform_not_applied",
                       f"{mesh.name!r} has scale {tuple(mesh.scale)} / "
                       f"rotation {tuple(mesh.rotation_euler)}: "
                       "apply them first (the contract wants scale 1)")
    scene = bpy.context.scene
    export = dict(_EXPORT_SCENE, arp_units_x100=bool(params.get("units_x100", True)))
    _, missing = _scene_settings(scene, export)
    if missing:
        return _refuse(params, info, "export_setting_missing",
                       f"the installed add-on keeps no scene setting {missing}; read its export panel")
    idname = info["operator_idnames"]["arp.bind_to_rig"]
    kwargs, scene_values, unmatched = _bind_options(params, idname)
    if unmatched:
        return _refuse(params, info, "bind_option_not_found",
                       f"bind options {unmatched} match no operator or scene property")
    override = _view3d_override()
    if override is None:
        return _refuse(params, info, "no_view3d_area", "the pipeline needs " + _NO_VIEW)
    spine_count = int(params.get("spine_count") or markers.get("arp_spine_count") or 4)
    ids = info["operator_idnames"]
    gates, out, warnings = [], {"op": "pipeline", "armature": rig_name, "mesh": mesh.name}, []
    state = C.save_state(scene, [mesh])
    before = set(bpy.data.objects)

    def stop(reason: str) -> dict:
        removed = tracker.rollback() if not out.get("bound") else {}
        return C.report(params, gates, stopped_at=reason, rolled_back=removed, warnings=warnings, **out)
    try:
        _object_mode()
        _call(ids["arp.append_arp"], override, rig_preset=params.get("preset", "human"))
        _object_mode()
        rigs = [o for o in bpy.data.objects if o not in before and o.type == 'ARMATURE']
        if len(rigs) != 1:
            gates.append(C.gate("arp.rig_appended", len(rigs), 1, False))
            return stop("append")
        rig = rigs[0]
        rig.name = rig_name
        out["armature"] = rig.name
        gates.append(C.gate("arp.rig_appended", 1, 1, True))
        if len(_spine_refs(rig)) != spine_count - 1:
            _set_spine(rig, spine_count, override, ids["arp.show_limb_params"])
        spines = len(_spine_refs(rig))
        gates.append(C.gate("arp.spine_bones", spines, spine_count - 1, spines == spine_count - 1))
        placed = _place_refs(rig, markers["arp_refs"], markers.get("hand_frames") or {})
        out["refs"] = placed
        ok = not placed["missing"] and placed["worst_miss_m"] <= 1e-4
        gates.append(C.gate("arp.refs_placed", placed["missing"] or placed["worst_miss_m"],
                            "all, <= 1e-4 m", ok))
        if not all(g["pass"] for g in gates):
            return stop("refs")
        _select_only([rig], rig)
        _call(ids["arp.match_to_rig"], override)
        _object_mode()
        out["bone_count"] = len(rig.data.bones)
        out["deform_bone_count"] = sum(1 for b in rig.data.bones if b.use_deform)
        gates.append(C.gate("arp.bone_count", out["bone_count"], "> 0", out["bone_count"] > 0))
        previous = {name: getattr(scene, name) for name in scene_values}
        try:
            for name, value in scene_values.items():
                setattr(scene, name, value)
            _select_only([mesh], rig)
            _call(idname, override, **kwargs)
            out["bound"] = True
        finally:
            for name, value in previous.items():
                with contextlib.suppress(AttributeError, TypeError, ValueError):
                    setattr(scene, name, value)
            _object_mode()
        limit = int(params.get("max_influences", 4))
        if params.get("limit_influences", True):
            _limit_influences([mesh], limit)
        deform = {b.name for b in rig.data.bones if b.use_deform}
        loose = _unweighted(mesh, deform)
        gates.append(C.gate("arp.vertices_without_group", loose, 0, loose == 0))
        out["bind"] = {"operator_kwargs": kwargs, "scene_settings": scene_values,
                       "influences_limited_to": limit if params.get("limit_influences", True) else None}
        _export_and_read(params, ids, override, scene, export, rig, [mesh], fbx, limit, gates, out)
    finally:
        C.restore_state(state)
    result = C.report(params, gates, warnings=warnings, **out)
    result["record"]["licence"] = dict(_LICENCE)
    return result


_OPS = {"markers": (_markers, ()), "match": (_match, ("arp.match_to_rig",)),
        "bind": (_bind, ("arp.bind_to_rig",)), "retarget": (_retarget, _REMAP),
        "pipeline": (_pipeline, ("arp.append_arp", "arp.show_limb_params", "arp.match_to_rig",
                                 "arp.bind_to_rig", "arp.arp_export_fbx_panel")),
        "export": (_export, ("arp.arp_export_fbx_panel",))}


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    op = params.get("op", "probe")
    if op == "source_bones":            # stock Blender only: no add-on needed
        return _source_bones(params)
    info = _probe()
    if op == "probe":
        gates = [C.gate("arp.addon_present", info["addon_present"], True, info["addon_present"])]
        return C.report(params, gates, op=op, **info)
    if op not in _OPS:
        return _refuse(params, info, "unknown_op",
                       f"op {op!r} is not one of probe, source_bones, {', '.join(_OPS)}")
    if not info["addon_present"]:
        hint = (f" It is installed as {info['installed_not_enabled']!r} but not enabled."
                if info.get("installed_not_enabled") else "")
        return _refuse(params, info, "addon_missing",
                       "Auto-Rig Pro is not enabled in this Blender: install and enable your own copy "
                       f"(Preferences > Add-ons), then probe again.{hint} Nothing was changed.")
    fn, needed = _OPS[op]
    missing = [n for n in needed if not info["operators"][n]]
    if missing:
        return _refuse(params, info, "operator_missing",
                       f"the installed add-on (version {info['version']}) registers no {missing}. "
                       "Nothing was changed.")
    if op == "pipeline":
        return fn(params, info, tracker)
    return fn(params, info)
