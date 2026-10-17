"""brt_library.py — finish an action library: slots, asset marks, one review track, a catalog.

Runs inside Blender; not a command-line script (the stub is in brt_common.py).

A retarget batch leaves one action per clip. Before the file ships, every clip
has to play on the rig, survive a save, be found in the asset browser, and be
reviewable in one pass:

  1. each action must carry the rig's slot: identifier "OB" + the rig's name,
     the slot Blender picks for that object. It gets a fake user (a save keeps
     an action no object plays) and an asset mark, with the description passed
     for it if there is one;
  2. each action plays on the rig alone (every NLA track muted) at its first,
     middle and last frame, and every F-curve value and every pose-bone head
     must be finite there;
  3. one NLA track holds one strip per clip, end to end, `gap_frames` apart,
     with a timeline marker named after the clip at each strip start;
  4. a catalog lists the clips in that order, written as JSON and CSV when
     `catalog_path` is given.

    result = brt_library.run({
        "armature": "RunnerRig",
        "actions": ["GateLatchSwing", "RunnerIdle", "RunnerSprint"],  # None: every action with the rig's slot
        # or "manifest": "<clips>/manifest.json" (a path or the list): each entry's `action`
        "catalog_path": "<out>/runner_library",    # writes .json and .csv; None returns it only
        "review_track_name": "Library Review",
        "start_frame": 1, "gap_frames": 0, "frame_step": 30, "fps": 30,
        "fake_user": True,
        "descriptions": {"GateLatchSwing": "Runner swings the gate latch open"},
    })

Which action is meant. Run a retarget batch twice and Blender names the
second copy `GateLatchSwing.001`; this module never guesses from a prefix. A
name in `actions` is the one action whose custom property `provenance_key`
(default "brt_source_file"; brt_arp stamps it and brt_clip) equals it, else,
when no action carries that value, the action of that exact name. Two
property matches, or an exact-name action that is not the property match (a
stale test take beside the stamped `.001`), is an error. For clip names pass
`provenance_key: "brt_clip"`. brt_retarget stamps no such property: write its
`output_action` into the manifest's `action`. With `manifest`, an entry's `action`
names it, else the one action whose `provenance_key` equals the entry's
`file` (or ends with it as a path). `resolved` maps each given item to the
action used. A library name ending in `.NNN` is legitimate (a deliberate second
take) and only warned about in `warnings`; `duplicate_suffixes` lists those
names and `suffix_siblings` the `.NNN` copies of library names that sit in the
file beside them.

Strip starts are whole frames (NLA strips start on one): a clip that ends
between frames pushes the next one to the following whole frame. A pose (an
action spanning less than one frame) is held for `frame_step` frames through
the strip's repeat, so it can be seen. In the catalog, `start` and `end` are
the strip on the review timeline, `action_start` and `action_end` the action's
own range, `frames` = action_end - action_start and `duration_s` = frames / fps.

Running it again replaces only what the last run put there: the rig keeps a
`brt_library` property (JSON) listing, per review track, the strips and markers
this module made and the actions it registered (`actions`); only those strips
and markers are removed, and brt_audit counts only those actions. Other strips and markers stay; a
strip of someone else's in the way of the new ones is an error raised before
anything is removed. The review track plays under the rig's active action:
clear that action to watch the track.

Edits to datablocks that already existed (kept on failure): the actions' fake
user and asset mark, the rig's `brt_library` property, its animation data.

Gates: library.every_action_has_slot, library.finite_at_3_frames,
library.strips_equal_clips (review strips playing a library action == clips).
"""
from __future__ import annotations

import csv
import json
import math
import os
import re

import bpy

import brt_common as C

LEDGER = "brt_library"            # property on the rig: what each review track got from this module
SUFFIX = re.compile(r"\.\d{3}$")  # the .001 Blender appends to a name already taken
FIELDS = ["index", "name", "start", "end", "frames", "slot", "duration_s", "finite",
          "action_start", "action_end"]


def rig_slot(action, rig):
    """The slot Blender picks for `rig` (identifier "OB" + its name), or None.

    Never ActionSlot.users(): it rebuilds a cache over every ID and has crashed
    Blender 5.2 on an armature object whose pose is not built yet.
    """
    want = "OB" + rig.name
    return next((s for s in getattr(action, "slots", []) if s.identifier == want), None)


def _by_property(key: str, value: str, file_path: bool = False) -> list:
    """Actions whose custom property `key` equals `value` (or, for a file path,
    ends with it as a path)."""
    want = os.path.normpath(value) if file_path else value
    out = []
    for action in bpy.data.actions:
        have = action.get(key)
        if not isinstance(have, str):
            continue
        if have == value or (file_path and os.path.normpath(have).endswith(os.sep + want)):
            out.append(action)
    return out


def _one(found: list, what: str) -> str:
    if len(found) != 1:
        raise KeyError(f"{what}: {len(found)} actions match"
                       + (f" ({sorted(a.name for a in found)})" if found else ""))
    return found[0].name


def _resolve(params: dict, rig, key: str) -> dict:
    """{given item: real action name}, in the order given."""
    names, manifest = params.get("actions"), params.get("manifest")
    if names is not None and manifest is not None:
        raise ValueError("give actions or manifest, not both")
    if manifest is not None:
        if isinstance(manifest, str):
            with open(manifest, encoding="utf-8") as handle:
                manifest = json.load(handle)
        out = {}
        for entry in manifest:
            label = entry.get("name") or entry.get("file") or json.dumps(entry)
            action = entry.get("action")
            if action and action in bpy.data.actions:
                out[label] = action
            elif action:
                raise KeyError(f"manifest entry {label!r} names action {action!r}, which is not in the file")
            elif entry.get("file"):
                out[label] = _one(_by_property(key, entry["file"], file_path=True),
                                  f"manifest entry {label!r} has no action, and for {key} = {entry['file']!r}")
            else:
                raise KeyError(f"manifest entry {label!r} has neither action nor file")
        return out
    if names is None:
        return {a.name: a.name for a in bpy.data.actions if rig_slot(a, rig)}
    out = {}
    for name in names:
        if name in out:
            raise KeyError(f"{name!r} is listed twice")
        found = _by_property(key, name)
        exact = bpy.data.actions.get(name)
        if not found:
            if exact is None:
                raise KeyError(f"no action named {name!r}, and for {key} = {name!r}: 0 actions match")
            out[name] = name
            continue
        real = _one(found, f"for {key} = {name!r}")
        if exact is not None and exact.name != real:
            raise KeyError(f"{name!r} names one action and {key} = {name!r} another ({real!r}): "
                           f"remove or rename the stale {name!r}, or list {real!r} itself")
        out[name] = real
    return out


def _finite(rig, action, slot, frames, bones) -> dict:
    index = next(i for i, s in enumerate(action.slots) if s.handle == slot.handle)
    C.assign_slot(rig, action, index)
    pose = C.sample_finite(rig, frames, bone_names=bones)["finite"]
    # a leaf bone's rotation never moves a head, so read the curves too
    curves = all(math.isfinite(fc.evaluate(f)) for fc in C.action_slot_fcurves(action, slot) for f in frames)
    return {"finite": pose and curves, "pose": pose, "curves": curves}


def _ledger(rig) -> dict:
    try:
        return json.loads(rig.get(LEDGER, "{}"))
    except (TypeError, ValueError):
        return {}


def _also_created(tracker: C.Tracker, extra: dict) -> None:
    """`step` fills "created" from tracker.created(), which sees datablocks only;
    add what this call made that is not one (the NLA track, strips, markers, files)."""
    datablocks = tracker.created
    tracker.created = lambda: {**datablocks(), **{k: list(v) for k, v in extra.items() if v}}


def _write(path: str, catalog: list[dict], written: list[str]) -> None:
    """`path`.json and `path`.csv; each is listed in `written` once it is open,
    so a failure halfway removes what this call wrote and nothing it could not open."""
    fields = FIELDS + (["description"] if any("description" in e for e in catalog) else [])
    with open(path + ".json", "w", encoding="utf-8") as handle:
        written.append(path + ".json")
        json.dump(catalog, handle, indent=2)
    with open(path + ".csv", "w", encoding="utf-8", newline="") as handle:
        written.append(path + ".csv")
        writer = csv.DictWriter(handle, fieldnames=fields, restval="")
        writer.writeheader()
        writer.writerows(catalog)


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    rig = bpy.data.objects[params["armature"]]
    if rig.type != 'ARMATURE':
        raise ValueError(f"{rig.name!r} is a {rig.type}, not an armature")
    if rig.animation_data is not None and rig.animation_data.use_tweak_mode:
        raise RuntimeError(f"{rig.name!r} is in NLA tweak mode; exit it first")
    if rig.pose is None:
        bpy.context.view_layer.update()   # build the pose before any slot is assigned
    scene = bpy.context.scene
    track_name = params.get("review_track_name") or "Library Review"
    fps = params.get("fps", 30)
    hold = params.get("frame_step", 30)
    gap = params.get("gap_frames", 0)
    path = params.get("catalog_path")
    descriptions = params.get("descriptions") or {}

    key = params.get("provenance_key") or "brt_source_file"
    resolved = _resolve(params, rig, key)
    names = list(resolved.values())
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated or not names:
        raise KeyError(f"listed twice (after resolving): {repeated}" if names
                       else f"no action to catalog: none given, or none has the slot OB{rig.name}")
    if path and not os.path.isdir(os.path.dirname(os.path.abspath(path))):
        raise FileNotFoundError(f"no folder for the catalog: {os.path.dirname(os.path.abspath(path))}")
    actions = [bpy.data.actions[n] for n in names]
    library = set(names)
    slots = {a.name: rig_slot(a, rig) for a in actions}

    # 1. keep every clip through a save, and list it in the asset browser
    for action in actions:
        if params.get("fake_user", True):
            action.use_fake_user = True
        if hasattr(action, "asset_mark") and getattr(action, "asset_data", None) is None:
            action.asset_mark()
        text = descriptions.get(action.name)
        if text and hasattr(getattr(action, "asset_data", None), "description"):
            action.asset_data.description = text

    # 2. each clip alone on the rig: mute every track, restore_state unmutes them
    bones = [b.name for b in rig.pose.bones] or None
    checks: dict[str, dict] = {}
    state = C.save_state(scene, [rig])
    try:
        for track in rig.animation_data.nla_tracks if rig.animation_data else []:
            track.mute = True
        for action in actions:
            if slots[action.name] is not None:
                start, end = action.frame_range
                checks[action.name] = _finite(rig, action, slots[action.name], [start, (start + end) / 2, end], bones)
    finally:
        restored = C.restore_state(state)

    # 3. plan the strips end to end, then check nobody else's strip is in the way
    ledger = _ledger(rig)
    ours = ledger.get(track_name, {})
    old = set(ours.get("strips", []))
    ad = rig.animation_data or rig.animation_data_create()
    track = ad.nla_tracks.get(track_name)
    plan, frame = [], math.ceil(params.get("start_frame", scene.frame_start))
    for action in actions:
        if slots[action.name] is None:
            continue
        start, end = action.frame_range
        length = end - start if end - start >= 1 else hold
        plan.append((action, frame, length))
        frame = math.ceil(frame + length + gap)
    if track is not None:
        blocking = [s.name for s in track.strips if s.name not in old
                    and any(s.frame_start < at + length and s.frame_end > at for _, at, length in plan)]
        if blocking:
            raise ValueError(f"strips not made by this module are in the way on {track_name!r}: {blocking}")

    extra = {"nla_tracks": [], "nla_strips": [], "timeline_markers": [], "files": []}
    _also_created(tracker, extra)
    removed = {"nla_strips": [], "timeline_markers": []}
    made_strips, made_markers = [], []
    try:
        # take back what the last run put here, and nothing else
        for strip in list(track.strips) if track is not None else []:
            if strip.name in old:
                removed["nla_strips"].append(strip.name)
                track.strips.remove(strip)
        for name, at in ours.get("markers", []):
            marker = next((m for m in scene.timeline_markers if m.name == name and m.frame == at), None)
            if marker is not None:
                removed["timeline_markers"].append(name)
                scene.timeline_markers.remove(marker)
        if track is None:
            track = ad.nla_tracks.new()
            track.name = track_name
            extra["nla_tracks"].append(track.name)

        for action, at, length in plan:
            # Blender adds .001 to the strip name when a strip on another track has it
            strip = track.strips.new(action.name, at, action)
            made_strips.append(strip)
            if strip.action_slot is None or strip.action_slot.handle != slots[action.name].handle:
                strip.action_slot = slots[action.name]
            span = strip.action_frame_end - strip.action_frame_start
            if abs(strip.frame_end - strip.frame_start - length) > 1e-4:
                strip.repeat = length / span   # a pose, held for frame_step frames
            extra["nla_strips"].append(strip.name)
            made_markers.append(scene.timeline_markers.new(action.name, frame=at))
            extra["timeline_markers"].append(action.name)

        # 4. the catalog, in strip order
        strip_of = {s.action.name: s for s in made_strips}
        catalog = []
        for index, action in enumerate(actions):
            slot, strip = slots[action.name], strip_of.get(action.name)
            start, end = action.frame_range
            entry = {
                "index": index, "name": action.name,
                "start": strip.frame_start if strip else None, "end": strip.frame_end if strip else None,
                "frames": end - start, "slot": slot.identifier if slot else None,
                "duration_s": (end - start) / fps, "finite": checks.get(action.name, {}).get("finite"),
                "action_start": start, "action_end": end,
            }
            if descriptions.get(action.name):
                entry["description"] = descriptions[action.name]
            catalog.append(C.safe(entry))
        if path:
            _write(path, catalog, extra["files"])
    except Exception:
        # roll back the NLA this call made; step then removes any new datablock
        for strip in made_strips:
            track.strips.remove(strip)
        if extra["nla_tracks"]:
            ad.nla_tracks.remove(track)
        for marker in made_markers:
            scene.timeline_markers.remove(marker)
        for written in extra["files"]:
            if os.path.isfile(written):
                os.remove(written)
        raise

    ledger[track_name] = {"strips": [s.name for s in made_strips],
                          "markers": [[m.name, m.frame] for m in made_markers],
                          "actions": list(names)}
    rig[LEDGER] = json.dumps(ledger)

    no_slot = [n for n in names if slots[n] is None]
    not_finite = {n: c for n, c in checks.items() if not c["finite"]}
    review = sum(1 for s in track.strips if s.action is not None and s.action.name in library)
    duplicates = [n for n in names if SUFFIX.search(n)]
    duplicates += [a.name for a in tracker.new("actions") if SUFFIX.search(a.name)]
    siblings = sorted(a.name for a in bpy.data.actions
                      if a.name not in library and SUFFIX.search(a.name) and SUFFIX.sub("", a.name) in library)
    gates = [
        C.gate("library.every_action_has_slot", len(no_slot), 0, not no_slot),
        C.gate("library.finite_at_3_frames", len(not_finite), 0, not not_finite),
        C.gate("library.strips_equal_clips", review, len(names), review == len(names)),
    ]
    warnings = []
    if duplicates:
        warnings.append(f"library names end in .NNN: {sorted(set(duplicates))}; confirm each is the "
                        "take you mean (a rerun of a batch makes one), and look it up by property "
                        "or manifest, never by name")
    if siblings:
        warnings.append(f".NNN copies of library actions sit beside them: {siblings}; a batch ran "
                        "twice. Remove a copy only when that batch made it and nothing plays it")
    first = min((s.frame_start for s in made_strips), default=None)
    last = max((s.frame_end for s in made_strips), default=None)
    return C.report(params, gates, armature=rig.name, track=track.name, review_range=[first, last],
                    catalog=catalog, missing_slot=no_slot, not_finite=not_finite,
                    duplicate_suffixes=duplicates, suffix_siblings=siblings, removed=removed,
                    resolved=resolved, provenance_key=key, warnings=warnings,
                    restore=restored if restored["missing"] or restored["errors"] else None)
