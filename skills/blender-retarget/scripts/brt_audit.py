"""brt_audit.py — re-open the saved .blend and check what is in it; the exit code is the verdict.

"The library call passed" is evidence about the session, not the file. This
reads the file back in a fresh Blender and compares it with what the caller
expects. Run it from the host shell:

    Blender --background RunnerLibrary.blend --factory-startup --python brt_audit.py -- \\
        --expect '{"actions": 12, "nla_strips": 12, "shape_keys_include": ["Grip"],
                   "invalid_drivers": 0, "images_unpacked": 0, "finite": true}' \\
        --props '[{"object": "MalletAnchor", "parent": "RunnerRig", "parent_bone": "Hand.R"},
                  {"object": "Mallet", "parent": "MalletAnchor"}]'
    # optional: --armature RunnerRig --mesh Runner --review-track-name "Library Review"
    #           --report-path <out>/audit.json

It prints one line, `BRT_AUDIT_JSON {...}`, and exits 0 when every gate passes,
1 when a gate fails or the audit itself raises, and 2 when it refuses its
input: `--expect` missing, empty (`{}`), not a JSON object, or `--props` not a
list of objects. An empty expectation checks nothing, so it never passes.
Blender itself exits 0 when a --python script raises, so the script catches
everything and exits on its own.

From the MCP code tool it is a module like the others (stub in brt_common.py):

    result = brt_audit.run({"armature": "RunnerRig", "expect": {"actions": 12}})

There an empty `expect` raises. It inspects the file that is loaded: it opens
nothing and never saves.

What it measures:
  actions: the library actions in the file, those the rig's `brt_library`
  property registers (brt_library writes it; a test take or a source clip
  left in the file is not counted); library_actions, library_missing
  (registered, not in the file), unregistered_actions and actions_in_file
  (every action) for reading; actions_without_slot (no slot at all),
  actions_without_rig_slot (no "OB" + rig name slot) and slots_total, over the
  library actions. With no `brt_library` property, actions is 0 and a warning
  says so;
  nla_tracks, nla_strips (every track on the rig), review_strips (the named track);
  drivers on objects, their data and shape keys; invalid_drivers: the paths of
  those whose driver.is_valid is False after one evaluation; python_drivers:
  those whose expression is not a simple one. is_valid stays True for these,
  and here they run, but a Blender with Auto Run Python Scripts off skips them;
  images_packed, images_unpacked (external file, not packed), for images with
  users; images_without_users (purge or report them before packing: an unused
  image with a path that does not resolve fails pack_all);
  shape_keys: the names on `mesh`, or on every mesh when none is named;
  finite: every pose-bone head finite at the start, middle and end of the
  review track (the scene range when there is no track), as the file plays.

`expect` keys are compared as: `<name>_include` -> every listed item is in
<name>; a number against a list -> the list's length; anything else ->
equality. A key it does not measure is a mismatch, never skipped.

`props` (optional): [{object, parent, parent_bone}], each prop's parent object
and parent bone as saved; parent_bone set means parent_type BONE, left out
means not checked (a prop on an anchor Empty: the anchor on the bone, the prop
on the anchor).

The rig is `armature`, else the only armature, else the only one carrying the
review track.

Gates: audit.expect_matches (no mismatch), audit.props_parented (no mismatch;
only when `props` is given).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

if __name__ == "__main__" and globals().get("__file__"):
    # Blender does not put a --python script's folder on sys.path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

import brt_common as C


def _rig(params: dict, track_name: str):
    if params.get("armature"):
        return bpy.data.objects[params["armature"]]
    rigs = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    if len(rigs) <= 1:
        return rigs[0] if rigs else None
    carrying = [o for o in rigs if o.animation_data and o.animation_data.nla_tracks.get(track_name)]
    if len(carrying) == 1:
        return carrying[0]
    raise ValueError(f"{len(rigs)} armatures and {len(carrying)} carry {track_name!r}: name one with --armature")


def _registered(rig) -> tuple[list[str] | None, list[str]]:
    """Action names the rig's brt_library property registers, in order (None when
    it has none). A ledger written before it listed `actions` gives the actions of
    the strips it lists."""
    raw = rig.get("brt_library") if rig is not None else None
    if raw is None:
        return None, []
    try:
        ledger = json.loads(raw)
    except (TypeError, ValueError):
        return None, [f"{rig.name}['brt_library'] is not JSON"]
    names: list[str] = []
    tracks = rig.animation_data.nla_tracks if rig.animation_data else {}
    for track_name, entry in ledger.items():
        listed = entry.get("actions")
        if listed is None:
            track = tracks.get(track_name) if tracks else None
            strips = set(entry.get("strips", []))
            listed = [s.action.name for s in (track.strips if track else [])
                      if s.name in strips and s.action is not None]
        names.extend(n for n in listed if n not in names)
    return names, []


def _props(specs) -> list[dict]:
    misses = []
    for spec in specs:
        obj = bpy.data.objects.get(spec["object"])
        if obj is None:
            misses.append({"object": spec["object"], "got": "not in the file"})
            continue
        got = {"parent": obj.parent.name if obj.parent else None,
               "parent_bone": obj.parent_bone if obj.parent_type == 'BONE' else None}
        want = {k: spec.get(k) for k in ("parent", "parent_bone") if k in spec}
        if any(got[k] != v for k, v in want.items()):
            misses.append({"object": obj.name, "expected": want, "got": got})
    return misses


def check_inputs(expect, props=None) -> tuple[dict, list]:
    """The parsed expect and props, or ValueError: expect must be a non-empty JSON
    object, props a list of objects that each name `object`."""
    if isinstance(expect, str):
        expect = json.loads(expect)
    if not isinstance(expect, dict) or not expect:
        raise ValueError("expect must be a non-empty JSON object: an empty expectation checks nothing")
    if isinstance(props, str):
        props = json.loads(props)
    props = props or []
    if not isinstance(props, list) or not all(isinstance(p, dict) and p.get("object") for p in props):
        raise ValueError("props must be a list of {object, parent, parent_bone}")
    return expect, props


def _drivers() -> tuple[int, list[str], list[str]]:
    count, invalid, python, seen = 0, [], [], set()
    blocks = [b for o in bpy.data.objects for b in (o, o.data) if b is not None] + list(bpy.data.shape_keys)
    for block in blocks:
        if block in seen:          # two objects can share one mesh or one Key
            continue
        seen.add(block)
        ad = getattr(block, "animation_data", None)
        for fc in ad.drivers if ad else []:
            count += 1
            path = f"{block.name}: {fc.data_path}[{fc.array_index}]"
            if not fc.driver.is_valid:
                invalid.append(path)
            if fc.driver.type == 'SCRIPTED' and not getattr(fc.driver, "is_simple_expression", True):
                python.append(path)
    return count, invalid, python


def _shape_keys(mesh_name):
    meshes = [bpy.data.objects[mesh_name]] if mesh_name else [o for o in bpy.data.objects if o.type == 'MESH']
    names = []
    for obj in meshes:
        keys = getattr(obj.data, "shape_keys", None)
        for block in keys.key_blocks if keys else []:
            if block.name not in names:
                names.append(block.name)
    return names


def measure(params: dict) -> dict:
    track_name = params.get("review_track_name") or "Library Review"
    rig = _rig(params, track_name)
    scene = bpy.context.scene
    if rig is not None and rig.pose is None:
        bpy.context.view_layer.update()      # build the pose before reading or sampling it
    registered, warnings = _registered(rig)
    if registered is None and not warnings:
        warnings.append(f"{rig.name if rig else 'no armature'} has no brt_library property: no action "
                        "is registered as the library; run brt_library before saving")
    registered = registered or []
    actions = [bpy.data.actions[n] for n in registered if n in bpy.data.actions]
    library = {a.name for a in actions}
    tracks = list(rig.animation_data.nla_tracks) if rig and rig.animation_data else []
    review = next((t for t in tracks if t.name == track_name), None)

    out = {
        "armature": rig.name if rig else None,
        "actions": len(actions),
        "library_actions": [a.name for a in actions],
        "library_missing": [n for n in registered if n not in bpy.data.actions],
        "unregistered_actions": sorted(a.name for a in bpy.data.actions if a.name not in library),
        "actions_in_file": len(bpy.data.actions),
        "actions_without_slot": [a.name for a in actions if not len(getattr(a, "slots", []))],
        "actions_without_rig_slot": [a.name for a in actions if rig and not any(
            s.identifier == "OB" + rig.name for s in getattr(a, "slots", []))],
        "slots_total": sum(len(getattr(a, "slots", [])) for a in actions),
        "nla_tracks": len(tracks),
        "nla_strips": sum(len(t.strips) for t in tracks),
        "review_strips": len(review.strips) if review else 0,
    }

    if review is not None and len(review.strips):
        start = min(s.frame_start for s in review.strips)
        end = max(s.frame_end for s in review.strips)
        out["finite_range"] = [start, end, "review_track"]
    else:
        start, end = scene.frame_start, scene.frame_end
        out["finite_range"] = [start, end, "scene"]
    if rig is not None:
        bones = [b.name for b in rig.pose.bones] if rig.type == 'ARMATURE' and rig.pose else None
        sample = C.sample_finite(rig, [start, (start + end) / 2, end], bone_names=bones or None)
        out["finite"], out["finite_sample"] = sample["finite"], sample
    else:
        out["finite"] = None

    # after the sampling: driver.is_valid is only set once the depsgraph has evaluated
    bpy.context.view_layer.update()
    out["drivers"], out["invalid_drivers"], out["python_drivers"] = _drivers()

    used = [i for i in bpy.data.images if i.users > 0]
    out["images_packed"] = sum(1 for i in used if i.packed_file is not None)
    out["unpacked_images"] = [i.name for i in used if i.packed_file is None and i.filepath]
    out["images_unpacked"] = len(out["unpacked_images"])
    out["images_without_users"] = sorted(i.name for i in bpy.data.images if i.users == 0)
    out["shape_keys"] = _shape_keys(params.get("mesh"))
    out["warnings"] = warnings
    return out


def compare(metrics: dict, expect: dict) -> list[dict]:
    """Every expected key that does not hold, with what was found."""
    misses = []
    for key, want in expect.items():
        if key.endswith("_include") and key[:-len("_include")] in metrics:
            have = metrics[key[:-len("_include")]] or []
            absent = [x for x in want if x not in have]
            if absent:
                misses.append({"key": key, "expected": want, "got": have, "absent": absent})
            continue
        if key not in metrics:
            misses.append({"key": key, "expected": want, "got": "not measured"})
            continue
        got = metrics[key]
        if isinstance(got, (list, dict)) and isinstance(want, int) and not isinstance(want, bool):
            got = len(got)
        if got != want:
            misses.append({"key": key, "expected": want, "got": got})
    return misses


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    expect, props = check_inputs(params.get("expect"), params.get("props"))
    metrics = measure(params)
    warnings = metrics.pop("warnings")
    misses = compare(metrics, expect)
    gates = [C.gate("audit.expect_matches", misses, [], not misses)]
    prop_misses = _props(props)
    if props:
        gates.append(C.gate("audit.props_parented", prop_misses, [], not prop_misses))
    return C.report(params, gates, expected=expect, compared=len(expect), metrics=metrics,
                    props=props, prop_misses=prop_misses, warnings=warnings)


def main(argv: list[str]) -> int:
    """Parse what follows `--`, audit, print one BRT_AUDIT_JSON line.
    0 every gate passes, 1 a gate fails or the audit raises, 2 the input is refused."""
    parser = argparse.ArgumentParser(prog="brt_audit.py", description=__doc__.split("\n")[0])
    parser.add_argument("--expect", default="{}", help="JSON object of expected metrics (required)")
    parser.add_argument("--props", default="[]", help="JSON list of {object, parent, parent_bone}")
    parser.add_argument("--armature")
    parser.add_argument("--mesh")
    parser.add_argument("--review-track-name", default="Library Review")
    parser.add_argument("--report-path")
    try:
        args = parser.parse_args(argv[argv.index("--") + 1:] if "--" in argv else [])
        expect, props = check_inputs(args.expect, args.props)
    except SystemExit as exc:
        if not exc.code:           # --help
            raise
        return _emit({"schema": "gate/1", "pass": False, "ok": False, "gates": [],
                      "refused": f"bad arguments (exit {exc.code})", "error": f"bad arguments (exit {exc.code})"}, 2)
    except ValueError as exc:      # json.JSONDecodeError included
        return _emit({"schema": "gate/1", "pass": False, "ok": False, "gates": [], "refused": str(exc),
                      "error": f"refused: {exc}"}, 2)
    try:
        result = run({"expect": expect, "props": props, "armature": args.armature, "mesh": args.mesh,
                      "review_track_name": args.review_track_name, "report_path": args.report_path})
    except Exception as exc:
        return _emit({"schema": "gate/1", "pass": False, "ok": False, "gates": [],
                      "error": f"{type(exc).__name__}: {exc}"}, 1)
    return _emit(result, 0 if result.get("pass") is True else 1)


def _emit(result: dict, code: int) -> int:
    result["exit_code"] = code
    print("BRT_AUDIT_JSON " + json.dumps(result), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
