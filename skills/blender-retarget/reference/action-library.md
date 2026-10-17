# Action libraries: layered actions, NLA review tracks, and assets

> Part of the `blender-retarget` skill. How a `brt_*` module is called and what every `run`
> returns are in `SKILL.md`.

A batch of retargeted clips is a library only when every clip plays on the rig through its slot,
survives a save, can be found, and can be watched in order. `brt_library` builds that from a list
of action names and gates it, `brt_audit` checks the saved file, and this file is the method.
`brt_library` takes `armature`, `actions` (None: every action with the rig's slot) or `manifest`
(a path or the list), `provenance_key` (default `brt_source_file`), `catalog_path`,
`review_track_name`, `start_frame`, `gap_frames`, `frame_step`, `fps`, `fake_user` and
`descriptions` (action name → asset description); its docstring has a full call.

## WARNING: two calls that crash Blender 5.2.1

- **Do not call `ActionSlot.users()`.** On Blender 5.2.1 it crashes Blender (it rebuilds a cache
  over every ID). `brt_library` finds the rig's slot by identifier instead: `"OB"` + the rig's
  name, the slot Blender picks for that object.
- **Do not set `NlaStrip.action_slot` on a rig whose pose is not built yet** (`rig.pose` is None):
  on Blender 5.2.1 that crashes Blender. `brt_library` builds the pose first (`view_layer.update()`)
  before any slot is assigned, and sets a strip's slot only when Blender did not pick the rig's.

Either takes the whole Blender process down: nothing is rolled back, unsaved work is lost.

## The layered action

Since Blender 4.4 every action is layered, and Blender 5 knows no other kind.

| Level | Holds | Reached by |
|---|---|---|
| Action | `layers`, `slots`, `frame_range` | `bpy.data.actions` |
| Layer | `strips` | `action.layers`: one layer per action for now |
| Keyframe strip | one channelbag per slot | `layer.strips`: one strip per layer for now |
| Channelbag | `fcurves`, `groups` of one slot | `strip.channelbag(slot)` |
| Slot | `identifier` (`OBRunnerRig`), `target_id_type` | what an object or an NLA strip plays |

- **Never read `action.fcurves`.** A Blender 5 action has no such attribute; the line raises. Walk
  layers → strips → channelbags: `brt_common.action_slot_fcurves`, or
  `bpy_extras.anim_utils.action_get_channelbag_for_slot`.
- **Assign with an explicit slot**: `animation_data.action`, then `animation_data.action_slot`.
  `brt_common.assign_slot` does both, and raises in NLA tweak mode, where the action is read-only.
  Assigned without a slot, an action moves nothing: the rig stands at rest, with no error.
- An action with several slots (a rig and its prop keyed together): pick by `identifier` from
  `animation_data.action_suitable_slots`, never by position. (`is_action_legacy` is true only on
  an empty action; it is not a test for an old file.)

## Names are not identifiers

A `brt_arp` batch that runs a second time creates `GateLatchSwing.001` beside
`GateLatchSwing`: Blender suffixes rather than overwrites. (`brt_retarget` refuses a taken
name instead, unless `overwrite_action: True`.) A preview that builds the name it expects then
raises `KeyError`, or quietly plays the stale first take.

1. **Before a batch**, delete the test actions of earlier trial runs, or bake each trial to a
   staging name (`Staging_GateLatchSwing`) that the batch never produces. A trial take left under
   the final name turns the real bake into `.001`.
2. Write the name the call reports (`clips[].action`, `output_action`), never a predicted one,
   into the manifest entry's `action` field. `brt_arp` also stamps custom properties on each
   action it bakes (`brt_clip`, the clip's name; `brt_source_file`, its file) that identify it
   whatever it is called. `brt_retarget` stamps none: its identifier is the `output_action` it
   returns, written into the manifest's `action`.
3. Look actions up by a property or by the manifest's `action`, never by a prefix plus a clip
   name. `brt_library` does: a listed name resolves through `provenance_key` (default
   `brt_source_file`; pass `provenance_key: "brt_clip"` for clip names), falling back to the exact
   name only when no action carries that value; with `manifest`, an entry's `action` names it,
   else its `file` is matched against `brt_source_file`. No match, two actions with one value (the
   batch ran twice), or a stale action of the exact name beside the property match is an error.
   `resolved` maps what was given to the action used.
4. A library name ending in `.NNN` is legitimate when it is the take you mean: it is reported in
   `duplicate_suffixes` and in `warnings`, never as a failed gate. `suffix_siblings` lists the
   `.NNN` copies of library names that sit beside them.
5. Two copies mean the batch ran twice. Keep the one the manifest names; remove the other only
   when this batch created it and nothing plays it, and never one the batch did not create.

## Keeping actions in the file

An action no object plays has zero users and is dropped when the file is saved and reopened.

- `use_fake_user` is set at the bake (both retarget modules) and by `brt_library` (`fake_user`).
- Clearing the rig's active action after a preview is then safe: the action stays in the file.
- A source skeleton kept for a re-bake (`keep_source` in `brt_arp`) stays hidden in place as
  `<clip>_Source`, stamped `brt_clip`.

## Assets and the catalog

`brt_library` marks each action as an asset (`asset_mark()`, when it is not one yet) and sets its
description from `descriptions`. It assigns no asset catalog; to file the actions under one:

```python
import uuid
catalog = str(uuid.uuid5(uuid.NAMESPACE_URL, "courier-run/Runner/Moves"))
action.asset_data.catalog_id = catalog
```

- The asset catalog is defined in `blender_assets.cats.txt`: a `VERSION 1` line, then one
  `UUID:path:simple name` line per catalog (`<uuid>:Runner/Moves:Runner-Moves`), at the root of
  the asset library, or beside a .blend outside any library. **Derive the UUID from the path**
  (uuid5): a rerun reuses the catalog, never adds a twin. A path uses `/`, never `:` or `\`.
- The Asset Browser lists them under its "Current File" source: open it and look before telling
  anyone to use it. This asset catalog is not the module's catalog file below.

## The review track

One NLA track on the rig plays every clip once, in the order of `actions`, with a timeline marker
where each starts. It is the library's table of contents, in time.

| Setting | Value | Why |
|---|---|---|
| Track | `review_track_name`, default `Library Review` | a rerun replaces only what the last run put on it |
| Strips | `track.strips.new(action.name, start, action)`, one per action with the rig's slot | an action without that slot gets no strip |
| `strip.action_slot` | the rig's slot, set only when Blender did not pick it | a strip without a slot plays nothing |
| First start | `start_frame` (default the scene's start), rounded up to a whole frame | NLA strips start on whole frames |
| Next start | `ceil(previous start + length + gap_frames)` | strips never overlap; a clip ending between frames pushes the next one on |
| A pose (under one frame long) | held `frame_step` frames through the strip's `repeat` | so it can be seen |
| Marker | `scene.timeline_markers.new(action.name, frame=start)` | named after the clip |

- **A rerun takes back only its own.** The rig's `brt_library` property records, per review track,
  the strips and markers this module made and the actions it registered; only those strips and
  markers are removed. Other strips and markers stay; a strip of someone else's in the way of the
  new ones raises before anything is removed. The registered actions are what `brt_audit` counts.
- Blend type, extrapolation and auto-blend stay at Blender's defaults. The track plays under the
  rig's active action, which the module leaves as it was: clear that action to watch the track.
- The scene range and rate are not changed. `review_range` gives the first strip's start and the
  last strip's end to set them from; `fps` only feeds `duration_s`.
- **Order** the `actions` list: rest or idle first, then locomotion, then the actions the game
  depends on, then the rest. The catalog rows follow it: the catalog is the playlist.
- A clip in which the prop is not held: key the prop's visibility on a review-only action on the
  prop, over that strip's range. The clip itself stays clean.
- Gates: `library.every_action_has_slot` (`missing_slot` names any listed action without the
  rig's slot) and `library.strips_equal_clips` (track strips playing a library action == listed).
- A dense mesh that plays below the clip's rate in the viewport is display load, not lost keys.

## Previewing one action alone

The active action is evaluated on top of the NLA. With the review track live, every channel the
action does not key takes the track's value, and the pose on screen belongs to two clips.

1. Mute the review track: `track.mute = True`.
2. Assign the action with its slot, by the name the catalog gives.
3. Preview or edit.
4. Clear the active action (`animation_data.action = None`) and unmute the track.

A skipped step 4 is the usual cause of "the library looks wrong after I checked one clip".

## Finite sampling at three frames

Before any picture, one cheap check per clip, played on the rig alone (NLA muted, through the
rig's slot) at its first, middle and last frame: the world head of **every** pose bone
(`brt_common.sample_finite`) and every F-curve value of the slot. A leaf bone's rotation moves no
head, so a NaN in its keys is caught by the curves. Mutes and the active action are put back.
Gate `library.finite_at_3_frames`; `not_finite` splits `pose` and `curves` per failing clip.

| Reading | Means |
|---|---|
| NaN or inf | a failed rest conversion or a degenerate bone matrix in the bake |
| finite, far beyond the bound | a scale or unit mismatch between source and target, or travel in a clip meant to be in place |
| finite, inside the bound | numerically sane, not that it looks right |

The gate reads finiteness only. A bound is a separate read of `sample_finite(...)["max_abs"]`
against the clip's expected travel plus a few character heights: metres, for the 1.2 m `Runner`.

## The catalog file

The manifest says what should exist; the catalog says what does, in review order. With
`catalog_path` it is written as `<catalog_path>.json` and `.csv` from one list in one call (the
folder must exist); without it, it is only returned. Neither is edited by hand.

| Column | Holds |
|---|---|
| `index` | position in `actions`, from 0 |
| `name` | the action's name, `Runner_GateLatchSwing` |
| `start`, `end` | its strip on the review timeline |
| `action_start`, `action_end` | the action's own `frame_range` |
| `frames`, `duration_s` | `action_end − action_start`; that over `fps` |
| `slot` | the rig's slot identifier, `OBRunnerRig` |
| `finite` | the sampling result |
| `description` | present only when `descriptions` gives one |

"The library call passed" is evidence about the session, not the file. After saving, check the
file itself in a fresh Blender with `brt_audit`, from the host shell:

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background RunnerLibrary.blend \
    --factory-startup --python <skill>/scripts/brt_audit.py -- \
    --expect '{"actions": 12, "nla_strips": 12, "finite": true}' \
    --props '[{"object": "MalletAnchor", "parent": "RunnerRig", "parent_bone": "Hand.R"},
              {"object": "Mallet", "parent": "MalletAnchor"}]'
```

That is the anchor-Empty grip: the anchor on the bone, the prop on the anchor. A prop parented
straight to the bone takes the one-entry form `{"object": "Mallet", "parent": "RunnerRig",
"parent_bone": "Hand.R"}`.

It prints one line, `BRT_AUDIT_JSON {...}`, and exits 0 when every gate passes, 1 when a gate
fails or the audit raises, and 2 when it refuses its input: no `--expect`, `{}`, or anything but a
JSON object (an empty expectation checks nothing, so it never passes). Flags: `--expect`,
`--props`, `--armature`, `--mesh`, `--review-track-name`, `--report-path`. Gates
`audit.expect_matches`, and `audit.props_parented` when `--props` is given (each prop's parent
object and parent bone as saved). In `expect`, `<name>_include` needs every listed item in
`<name>`, a number against a list compares its length, else equality; an unmeasured key is a
mismatch. The Armature modifier is not checked.

- `actions` counts the library: the actions the rig's `brt_library` property registers. A test
  take or a source clip left in the file is listed in `unregistered_actions` and not counted;
  `actions_in_file` is every action. A file saved before `brt_library` ran has no library, and
  the result says so in `warnings`.
- `images_without_users` lists images nothing uses. Purge them, or report them, before
  `bpy.ops.file.pack_all()`: an unused image whose path points at a file that is not there makes
  the pack fail.

## Rendering checks

A check render changes the camera, the frame, the mutes and the assigned action. All of it goes
back, whatever happens in between:

```python
state = brt_common.save_state(scene, ["RunnerRig", "Runner", "Mallet"])
cam = scene.camera
kept = (cam.matrix_world.copy(), cam.data.ortho_scale, scene.render.filepath)
try:
    ...   # mute tracks, assign one action with its slot, frame the camera, set the frame, render
finally:
    cam.matrix_world, cam.data.ortho_scale, scene.render.filepath = kept
    restored = brt_common.restore_state(state)
```

`save_state` keeps frame, selection, active object, mode, resolution, and per object its action,
slot, NLA tweak state, NLA mutes and visibility. The camera and output path are kept beside it.

**Pick the still by a metric, not by scrubbing.** Sample about 20 evenly spaced frames per clip:

| Clip kind | Metric | Frame kept |
|---|---|---|
| overhead reach or throw | height of the working hand | highest |
| strike or swing (`GateLatchSwing`) | distance from the working hand to the hips | farthest |
| jump or vault (`HurdleVault`) | height of the hips | highest |
| anything else | distance from the middle frame | the middle |

Frame the camera from the evaluated meshes' world bounds at that frame, not a stored position that
crops a clip whose peak leaves the box: one fixed direction for every clip, aimed at the bounds'
centre, ortho scale from the projected bounds plus a 15–20% margin.

## What the library proves

| Proves | Does not prove |
|---|---|
| every clip exists under a name that resolves, after save and reopen (`brt_audit`) | that any frame looks right: that is the review, by eye |
| each clip plays on the rig through a slot | transitions: strips butt end to end and nothing blends |
| finite pose and curves at three frames | a state machine, input windows or game timing |
| one order to watch, with markers | contact, foot planting, a second actor's placement |
| the clips are findable as assets | real-time playback of the final mesh |
