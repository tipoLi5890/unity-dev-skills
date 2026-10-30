# Auto-Rig Pro route: when, how, and what to check

> Part of the `blender-retarget` skill. How a `brt_*` module is called and what every `run`
> returns are in `SKILL.md`.

Auto-Rig Pro builds a control rig from a handful of markers, skins the mesh to it, and remaps
clips onto its controls. `brt_arp` drives the user's own installed copy through the MCP code tool
in six ops: `probe`, `source_bones`, `markers`, `match`, `bind`, `retarget` (parameters in its
docstring). Two more serve `character-autorig`: `pipeline` rigs a mesh onto the humanoid contract
in one call, and `export` re-exports a bound rig after a weight repair with the pipeline's settings,
4-influence limit and licence. The elbow and knee repair recipe is in `character-autorig` →
`reference/arp-pipeline.md`.

## When this route fits

| Take this route when | Take positional skinning (`blender-character-rig`) when |
|---|---|
| standard human proportions: adult limb lengths, arms and legs clear of the body | short limbs, a large head, ears or tails, mitten hands |
| the add-on is installed in the user's Blender and you can drive that session | no add-on, or no session you can run its operators in |
| you want its IK/FK control rig to remap many clips onto | a plain deform skeleton and hand-keyed actions are enough |

The Voxelized bind does not need a watertight surface, so a generated mesh alone is no reason to
leave this route; proportions are. A landmark outside its search window below says the same.

Installing is the user's, on request: the main add-on from disk in Preferences, the optional
Smart AI files from the add-on's own preferences. Nothing of the add-on lives in this skill:
`brt_arp` finds an enabled add-on whose module name contains `auto_rig_pro` and refuses with
`addon_missing` when there is none (saying so when it is installed but not enabled).

## Probe first: module name and private names

`probe` is the first call and reads only; every op but `source_bones` runs it again and refuses, changing
nothing, when the add-on or an operator it needs is missing (`operator_missing`).

- **The module name.** Under the extensions system the add-on imports as
  `bl_ext.<repository>.<package>`; the repository part depends on where it was installed. `probe`
  reports it as `module`, with `version` (`bl_info`, or `blender_manifest.toml`); by hand, filter
  `addon_utils.modules()` on `auto_rig`. Never type it from memory.

- **Operators.** `hasattr(bpy.ops.arp, name)` is True for any name: `bpy.ops` builds a wrapper on
  attribute access. Only the RNA lookup fails for an operator nobody registered, so test with
  `get_rna_type()`:

```python
def registered(idname):
    space, name = idname.split(".", 1)
    try:
        getattr(getattr(bpy.ops, space), name).get_rna_type()
        return True
    except (KeyError, AttributeError, ValueError):
        return False
props = [p.identifier for p in bpy.ops.arp.retarget.get_rna_type().properties]
```

- **Another prefix.** An add-on version may register an operator under a prefix other than
  `arp.`. `probe` tries `arp.<name>` first (Smart's detection is `arp.go_detect`), then an
  operator of the same function name that the add-on's own classes registered. `operators` says
  found or not per name, `operator_idnames` where each was found, `operator_properties` what each
  declares.
- Operators, `arp_` scene properties and functions inside the add-on are not a stable public
  interface. A missing name refuses; read the installed UI, then change the call. Never guess.

## UI operators need a 3D view

Marker placement, Match and Bind read the 3D view, and code sent through the MCP tool has none in
its context. `markers`, `match` and `bind` refuse with `no_view3d_area` when no 3D viewport is open
(ask the user to open one); `retarget` uses one when there is one. The override, by hand:

```python
win = bpy.context.window_manager.windows[0]
area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region):
    bpy.ops.arp.match_to_rig('EXEC_DEFAULT')
```

Every op sets mode, selection and the active object itself, and puts them and the frame back
after. An operator keyword the installed operator does not declare refuses before any change.

## Markers from slices

Prep the mesh as `blender-character-rig` does (`blender-character-rig` →
`reference/import-and-survey.md`): identity transform, height set to the design height, facing −Y,
Z up, soles on Z 0, **with `weld_distance: None`**. This route binds the exact source mesh: the
bind works through a voxel proxy, so open seams cost nothing, and a weld only changes the face
count of the mesh you hand off. Arms fused to the torso at the armpits or legs fused at the crotch
cannot be fixed by markers; look before placing any.

Survey in the mesh's own space, with `H` = top − sole: horizontal slices at a step of about 3 % of
`H`, split into parts at gaps along X wider than about 1 % of `H` (drop parts too small to be a
limb), and vertical bands across the arm for its top and bottom along its length.

The windows below are one adult body's landmark heights divided by its height: a one-body
example, not a standard. Measure your character and widen or move them before trusting a miss.

| Landmark | Feature in the survey | Search window (fraction of `H` from the sole; one-body example, measure your character) |
|---|---|---|
| foot | ankle: the narrowest leg slice above the shoe's flare | 0.03–0.10 |
| knee | the narrowing between thigh and calf | 0.24–0.32 |
| thigh | hip joint: just above the lowest slice where the two leg parts merge | 0.45–0.55 |
| root | pelvis centre on the midline, at about hip-joint height | 0.47–0.56 |
| shoulder | where the arm part separates from the torso; X at the torso's outer edge, moved in by half the arm's thickness | 0.75–0.85 |
| neck | the narrowest slice between shoulders and head | 0.82–0.88 |
| chin | the front-most point of the head's lowest slices | 0.85–0.92 |
| head top | the highest vertex | 1.0 |
| elbow, hand | from the arm bands: the bend at mid-length, the wrist narrowing | depends on the rest (T or A); no window |

Width from the slice part's centroid across X; depth at the middle of the part's front-to-back
extent, root and neck slightly behind it. A landmark outside its window means non-standard
proportions: take the positional route instead of forcing markers.

**`markers` places what the survey found.** Smart must be started in the add-on on the mesh first
(it picks the body the markers are sized from); until then the op refuses with
`smart_not_started`. `landmarks` maps the add-on's own marker names to `[x, y, z]` in the
armature's space (world space without `armature`); the module's example uses `neck`, `chin`,
`shoulder`, `hand`, `root`, `foot`. Pass only names the installed helper takes; the other table
rows check proportions. `mesh` (optional) is selected first. Each name goes to the add-on's own
`_add_marker` helper, found by name in its modules (`smart_marker_api_not_found` without it), with
`mirror` (default True) as its mirror switch; the marker it makes, `<name>_loc`, is moved to the
point and read back evaluated. Place limb markers on +X: the add-on holds a limb marker on one
side, so one given on −X never gets there and counts as not placed (`miss` in the result); the
mirrored `<name>_loc_sym` follows by constraint. Gate `arp.markers_placed`. Detection (Smart's Go,
`arp.go_detect`) is not run by the module.

## Smart AI is optional

The AI component estimates markers from the mesh. It is a separate download with its own
inference executable per platform; the main add-on works without it.

- `probe`'s `ai_files` and `ai_version` say only that an `inference` folder is installed (its path
  is never reported). **The success check is output**: marker objects at non-default positions
  inside their search windows. Files, a version string or a preference show nothing about it.
- **On failure, fall back** to markers from the survey. Do not lift OS protections (quarantine
  flags, signing, security settings) to make the binary run.

## Match to Rig, then bind

Have the file saved before each (ask; never save unasked): a failure removes what the call
created, not the add-on's own edits to the rig's bones, the mesh's groups or the body's rotation.

**`match`** (`armature`, optional `mesh`, `expected_bones`) runs Match to Rig. It refuses with
`already_bound` while a mesh child of the rig (or `mesh`) holds weights for one of its deform
bones: Match rebuilds the rest under those weights, invalidating every action keyed on the
controls, every `K` (`reference/rest-pose-and-conjugation.md`) and every prop placed at rest. Gate
`arp.bone_count` (== `expected_bones`, else > 0); the result also gives `deform_bone_count`.

**`bind`** (`armature`, `mesh` as one name or a list) refuses with `no_deform_bones` before
Match, and with `already_bound` on a mesh that has groups named after deform bones. Each setting
goes to an operator property of its own name if the installed bind operator declares one, else to
the add-on's scene property, set for the call and restored after:

| Param (default) | Scene property | Note |
|---|---|---|
| `pseudo_voxels` (True) | `arp_bind_engine` | True → `'PSEUDO_VOXELS'` (Voxelized), False → `'HEAT_MAP'` |
| `resolution` (7) | `arp_pseudo_voxels_resolution` | a starting value: higher is finer and slower |
| `split` (False) | `arp_bind_split` | |
| `preserve` (True) | `arp_bind_preserve` | |
| `chin` (False) | `arp_bind_chin` | |
| `scale_fix` (False) | `arp_bind_scale_fix` | |

`option_names` points a key elsewhere (`"name"` or `"scene.name"`); None leaves the add-on's
setting alone; a key that matches nothing refuses with `bind_option_not_found` and lists what
exists. Python Tooltips (Preferences → Interface → Display) over the skinning panel show which
field is which. Gate `arp.vertices_without_group` (no deform weight above 0; 0 expected).

**Right after the bind, check the weight sums over deform groups only**: `brt_weights` op `probe`
with no mask or band, whose `deform_sum` (min/mean/max) should read 1; `all_group_sum_max` is for
reading only. Groups for non-deform bones (controls, helpers) left on the mesh inflate a
plain per-vertex sum far above 1 and hide the real error; normalise over deform bones before any
pose test.

## Probe the source skeleton before mapping

A map is valid for one skeleton. A preset or config made for another fails at `import preset` with
the add-on's "some preset bones do not exist" list, one line per bone. Run `source_bones` on one
file per clip family first: it imports each `fbx`, lists its bones with their parents and a
`skeleton` hash (files with the same hash share a map), and takes the import back. Give it the map
you plan (`{target_bone: source_bone}`) and `map_missing` names the source bones the file lacks;
gate `arp.map_sources_found`. Pass that same dict as `retarget`'s `map`: it is written into the
add-on's bones list after `build_bones_list` and checked again against each imported skeleton, so a
missing bone fails that clip before any rest changes. A dict entry may also be
`{"source": bone, <field>: value}` for a field the installed bones-list entry declares; another
key refuses and lists the fields. The source bone is matched on the entry's `source_bone` and the target written
to its `name`: confirm both on your version first
(`[p.identifier for p in scene.bones_map_v2[0].bl_rna.properties]`).

## The retarget sequence

`retarget` takes `armature`, `clips`: `[{name, fbx, map?, frame_start?, frame_end?, align?,
exclude?, switches?, origin?, family?, metadata?}]` (each key but `name`, `fbx` and the frames may
also sit at the top level for every clip), `metadata_fields`, `keep_source` (default False),
`dry_run`, `stop_if_first_fails` (default True), `pause_deform` (default True), `progress_path`,
`source_prop` and `target_prop` (default `source_rig`, `target_rig`). `map` is a built-in preset
name, a saved config path (`.bmap`), or the dict above.

Before any change it checks every clip: the `fbx` is a local file, the map's target bones exist on
the rig, the switches, the operators and their keywords, the two scene properties, and the
metadata of **every** clip (below). Then, per clip:

| # | Stage | Call |
|---|---|---|
| 1 | reset | clear the rig's active action (its fake user kept), set every pose bone's `matrix_basis` to identity, set the IK/FK switches: the clip before leaves its pose and action under the next rest and bake |
| 2 | import | `bpy.ops.import_scene.fbx(filepath=…)` on the user's file, read only; exactly one armature must arrive |
| 3 | source/target | `scene.<target_prop>` first, then `scene.<source_prop>`: setting the source runs the add-on's update, which reads the target |
| 4 | freeze_armature | `arp.freeze_armature(arm='source')`; it replaces the source object, which is re-read from `scene.<source_prop>` by name |
| 5 | build_bones_list | `arp.build_bones_list()` |
| 6 | import map | `arp.import_config_preset(<its preset property>=…)`, `arp.import_config(filepath=…)`, or the dict written into the list |
| 7 | exclude | drop each `exclude` source bone and every bone below it (a hand takes its fingers) from the list |
| 8 | offsets | delete `rest_transf_offset` from the scene, the rig, its data and pose bones: left by the clip before, `redefine_rest_pose` would reuse it and bend this clip |
| 9 | redefine_rest_pose | `arp.redefine_rest_pose(preserve=True, rest_pose='REST')` |
| 10 | align | select exactly `align` on the source, else the source bones `scene.bones_map_v2` maps onto the rig |
| 11 | copy_bone_rest, save_pose_rest | `arp.copy_bone_rest()`, then `arp.save_pose_rest()` |
| 12 | retarget | `arp.retarget(frame_start=…, frame_end=…, fake_user_action=True)`: the clip's frames, else the imported action's range |
| 13 | action | the rig re-read by name; the new action takes the clip's `name`, fake user on, its slot assigned, every switch keyed at the first frame |
| 14 | cleanup | everything the import brought is removed, unless `keep_source` |
| 15 | metadata | a separate phase: the action's custom properties (below) |

- **Exclude hands and fingers in a first pass.** `exclude: ["LeftHand", "RightHand"]` keeps the
  fitted hand rests out of the bake; a hand is converted later on its own (`keep_source` below).
- **Phases are reported apart.** Each clip has `bake` `{ok, stage, error}` and `metadata`
  `{ok, error, written}`. Gates `arp.retarget_clips` (bakes that left an action with a slot and
  curves) and `arp.metadata_clips` (metadata written), each equal to the clips run. A failed bake
  is rolled back alone and the batch goes on, except that a first clip failing either phase skips
  the rest (`stop_if_first_fails`): one error repeated across a whole batch is the usual case.
- **Metadata is checked before the first bake.** Every produced action gets provenance properties:
  `brt_clip` (the clip's name), `brt_source_file` (its `fbx` as given), and `brt_origin` and
  `brt_family` when the clip or the call gives `origin` / `family`; then the call's and the clip's
  `metadata` dicts; then `metadata_fields`, `{property: clip key}`, copied from each clip. A clip
  without one of those keys, or a value that is not a string or a number, refuses the whole call
  with `metadata_invalid` before anything is imported: a post-bake step that fails on every clip
  reports a batch of good bakes as failures.
- **Dry run first.** `dry_run: True` runs the first clip through every stage, metadata included,
  reports it, and rolls it back: no action or import stays, and the pose, the switch values and
  the `rest_transf_offset` properties are put back. Run it, read the report end to end, run that
  one clip for real and look at it, then run the batch.
- **Look actions up by property, never by name.** Blender appends `.001` to a taken name (listed in
  `duplicate_suffixes`; a taken clip name also warns before the run). `brt_clip` on the action
  names its clip whatever the action is called: find it with `brt_library` and
  `provenance_key: "brt_clip"` with the clip names in `actions`, or with `manifest`, whose `file`
  is matched against `brt_source_file`. A stale action of the clip's exact name beside the stamped
  `.001` is refused, never picked. Delete test actions, or bake under staging names, before the
  batch.
- **Pause deformation for the batch.** `pause_deform` turns off the viewport display of every
  armature modifier the rig drives while the batch runs and restores it in a `finally`: the bake
  reads the rig, not the dense mesh. It is a speed-up, not an unbind.
- **`progress_path`** rewrites the clip results as JSON after every clip, so a lost connection
  still leaves a record of what finished.
- **`keep_source: True`** keeps each imported skeleton, hidden, as `<name>_Source` and stamped
  `brt_clip`, with its action. `brt_retarget` with `into_action` then converts a bone the map left
  out (a wrist) into the action the add-on baked, from that skeleton's rest and curves, without
  touching the curves already there (`reference/rest-pose-and-conjugation.md`). Its `map` is the
  wrist alone; its `reference_map` is the body map the bake used (root, spine, shoulder, arm,
  forearm), so the walk aims those bones and not the hand, whose fitted tail is off the palm.
  After the call the rig plays what it played before; the new actions stay by fake user.

  ```python
  brt_retarget.run({"source": "JogLaneLeft_Source", "target": "RunnerRig",
                    "map": {"c_hand_fk.r": "RightHand"},
                    "reference_map": {"c_root_master.x": "Hips", "c_spine_01.x": "Spine",
                                      "c_shoulder.r": "RightShoulder", "c_arm_fk.r": "RightArm",
                                      "c_forearm_fk.r": "RightForeArm"},
                    "into_action": "JogLaneLeft"})
  ```

## IK/FK is animation data

- `ik_fk_switch` is a custom property on the hand IK controls (`c_hand_ik.l`, `c_hand_ik.r`) and
  the foot IK controls (`c_foot_ik.l`, `c_foot_ik.r`). The add-on's value convention is `1.0` FK,
  `0.0` IK. It is this add-on's convention, not a universal one: **confirm it** on your version
  by toggling the value in the UI and watching which chain the limb follows.
- `switches` (default None) reads the switch bones from the rig itself, the pose bones carrying
  `ik_fk_switch`, and sets `c_hand_ik.*` to 1 (arms bake onto FK controls) and `c_foot_ik.*` to 0
  (feet stay IK) before the bake, then keys each at the clip's first frame in its action.
  `{bone: value}` sets exactly those (a bone without the property refuses with `clip_invalid`);
  `{}` sets none. Unkeyed, a switch holds whatever the last clip left.
- The switch is not on the bone that rotates: the wrist is `c_hand_fk.r`, the switch `c_hand_ik.r`.

## Before a long session

- **Smoke-test on a cube first.** One short call that adds a cube, reads its evaluated data, keys
  one channel and removes it, before an hour of batch work. It catches an API change and a
  localised UI: node and enum display names are translated, so `nodes['Background']` fails under a
  non-English interface. Look nodes up by `type` / `bl_idname`.
- **Blender 5 keeps bone selection on the pose bone.** `PoseBone.select`; `Bone.select` raises
  `AttributeError`. `brt_arp` handles both.
- **Operators replace objects.** Freeze and retarget can delete an object and make a new one of the
  same name, so a Python reference held across the call raises `StructRNA … has been removed`.
  Re-fetch by name after each operator.
- **Size the client timeout by job class**: a probe in minutes (about 3), one clip in tens of
  minutes (about 20), a batch in about an hour. On a closed connection, inspect Blender (actions,
  `progress_path`) before resubmitting: the job may still be running or may have finished.

## `brt_arp` ops and gates

| op | Does | Gate |
|---|---|---|
| `probe` | finds the module, its version, the operators and what they declare; reads only | `arp.addon_present` |
| `source_bones` | imports each FBX, lists its skeleton and what a map lacks, takes the import back; needs no add-on | `arp.source_skeleton_found`, `arp.map_sources_found` (with `map`) |
| `markers` | places `landmarks` through the add-on's marker helper | `arp.markers_placed` |
| `match` | Match to Rig; refuses on a bound mesh | `arp.bone_count` |
| `bind` | the bind with the settings above | `arp.vertices_without_group` |
| `retarget` | the sequence above, per clip | `arp.retarget_clips`, `arp.metadata_clips` |

- **A refusal changes nothing**: `pass` false, gate `arp.precondition` failing beside
  `arp.addon_present`, and a `reason` (`addon_missing`, `operator_missing`, `object_missing`,
  `no_view3d_area`, `smart_not_started`, `already_bound`, `bind_option_not_found`, `clip_invalid`,
  `metadata_invalid`, `nla_tweak_mode`, `scene_property_missing`, …) with a `message`.
- **A vertex in some group is a floor, not quality.** Next come `brt_weights`
  (`weights.weight_sum_error`, `weights.deform_only`) and a pose test at the extremes: arms up,
  a deep squat. Expect deep hip bends to compress, and no face rig from a body bind.
- Auto-fitted hands often rest with the tail off the real palm: do not rotate finger bones far.
- After a batch, `brt_library` checks the library as a whole and finds each clip's action with
  `provenance_key: "brt_clip"` and the clip names, or the manifest's `action`, else its `file`
  against `brt_source_file` (`reference/action-library.md`).
