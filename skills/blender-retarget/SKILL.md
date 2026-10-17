---
name: blender-retarget
description: >-
  Retarget stock or purchased clips onto a character already rigged in
  Blender, driven through its MCP server. Load for: "put these clips on my
  rig", arms twist or flare, a T-pose source on an A-pose rig, a retargeted
  arm still follows its IK target, actions renamed ".001", a library of many
  clips that needs previews and one NLA review track, a shoulder or upper back
  that collapses when the arm lifts (local weight repair), a prop that must
  stay on the hand bone in every clip, handing the library to Unity. Auto-Rig
  Pro route when the user has it installed; building a rig by position:
  blender-character-rig; Unity import: unity-rigged-character.
---

# blender-retarget — map the rest pose, then move the clips

A keyed bone rotation is a turn away from that bone's own rest. Retargeting is a rest-pose and
rotation-frame problem, not a matter of rotating a bone a few degrees: two skeletons that rest
differently give the same four numbers two meanings. A clip that looks wrong on the target is
almost always the frame (a T-pose source read against an A-pose rest, a bone mapped by name
instead of by role) or the mode (an arm baked onto FK controls and played in IK), not the keys.

> **Convert the frame, prove one clip, then widen.** A wrong conversion is wrong in the same way
> on every clip, so a batch only multiplies it.

Every step is one call, through the MCP server of a Blender the user already has open, to a module
in `scripts/` that returns a dict of gates.

## Working contract

- **The user's Blender, the user's file.** Never save unasked; ask before Match, Bind or the first
  weight write, which are not undone. Say whether the file is saved when handing back. Installing
  Blender, the add-on or the server is the user's, on request only.
- **Probe before writing.** `brt_arp` op `probe` before any Auto-Rig Pro call; the server's
  blend-file and objects summaries, the active object, the mode, and the slots of every action on
  the rig, all read before any code writes.
- **One clip before a batch.** One bone on one clip, gated and looked at; the same bone across the
  clips; the next bone; only then the batch. Delete test takes, or bake under a staging name, first.
- **Before a long session**, smoke-test the API and UI locale on a cube; on a timeout, inspect
  Blender before resubmitting (`reference/arp-route.md`).
- **Every step returns gates.** Read a failed gate's `value` against its `limit`, change one
  parameter and rerun before the next step. The same input, parameters and error are never sent
  twice.
- **Nothing of Auto-Rig Pro is copied.** No add-on source, operator body or AI model file goes into
  a project or this repository; `brt_arp` drives the copy the user installed, through the
  operators it registers. Purchased clips stay outside the repository too.
- **Auto-Rig Pro only when the user has installed it.** `brt_retarget` and `brt_arp` op
  `source_bones` need stock Blender alone.

## Load what the situation needs

| The situation | Read |
|---|---|
| Arms flare, cross or twist; a T-pose source on an A-pose rig; the constant `K`, sign continuity, mapping by role, when `K` is recomputed | `reference/rest-pose-and-conjugation.md` |
| Auto-Rig Pro: when the route fits, the probe, markers, Match then Bind, the source skeleton probed for the map, the per-clip sequence, its dry run, IK/FK switches | `reference/arp-route.md` |
| Clips: the manifest, a stock library in the user's browser, a purchased pack and its variants, fps, licence | `reference/clip-sources.md` |
| Layered actions and slots, `.001` names, fake users, asset marks and the catalog, the review track, previewing one action alone, check renders | `reference/action-library.md` |
| A shoulder or upper back that dents or drags in a pose: probe, mask, transfer, deform-only normalising, backup and restore | `reference/weight-repair.md` |
| The quality target first; which layer is wrong (geometry, skinning, animation, material), a fixed grip, stop rules, the failure log | `reference/defect-triage-and-stop.md` |
| The export contract for Unity: which skeleton, which clips, what survives the FBX, the minimal validation | `reference/unity-handoff.md` |
| The parameters of one module | its docstring, `scripts/brt_*.py` |

| Module | Does | Gates |
|---|---|---|
| `brt_common` | shared helpers: the gate and report shape, slot assignment, layered-action F-curves, scene state saved and put back, finite sampling | — |
| `brt_arp` | drives the user's own Auto-Rig Pro: ops `probe`, `source_bones` (no add-on), `markers`, `match`, `bind`, `retarget`; a missing name fails `arp.precondition` with a `reason` and changes nothing | `arp.addon_present`, `arp.source_skeleton_found`, `arp.map_sources_found`, `arp.markers_placed`, `arp.bone_count`, `arp.vertices_without_group`, `arp.retarget_clips`, `arp.metadata_clips` |
| `brt_retarget` | the rotation of mapped bones, conjugated from a source skeleton into a new action or, with `into_action`, one that exists; translation is not retargeted | `retarget.output_is_new` or `retarget.channels_free`, `retarget.finite_keys`, `retarget.first_equals_last` (with `loop`) |
| `brt_weights` | local weight repair: ops `probe`, `snapshot`, `transfer`, `normalize`, `restore` | `weights.region_vertices`, `weights.snapshot_written`, `weights.changed_vertices`, `weights.weight_sum_error`, `weights.deform_only`, `weights.restored` |
| `brt_library` | slots, fake users, asset marks, one review track, a catalog; actions found by name, provenance property or manifest | `library.every_action_has_slot`, `library.finite_at_3_frames`, `library.strips_equal_clips` |
| `brt_drift` | a carried prop against its anchor bone, sampled over every clip, position and rotation | `drift.max_drift`, `drift.max_rotation` |
| `brt_audit` | the saved .blend read back in a fresh Blender; exit 0 pass, 1 fail, 2 refused input | `audit.expect_matches`, `audit.props_parented` (with `props`) |

**Calling a module.** Through the Blender MCP server's code tool, put this skill's `scripts`
directory on `sys.path`, import `brt_common` and the module, reload both (Blender keeps
`sys.modules` for the whole session), and assign `result = brt_<module>.run(params)`: the code tool
hands that dict back, and the worked example below is the stub. Every `run` returns `ok`, `gates`
(each with `name`, `value`, `limit`, `pass`), `created` (the datablocks it added) and `blender`,
plus the keys its docstring lists; `report_path` also writes it as JSON. A call that raises removes
what it created; edits to datablocks that already existed are not undone, and each docstring says
which it makes. When Blender cannot read the skill directory, send the sources in one call the way
`blender-character-rig` does, `brt_common` first. `brt_audit` alone also runs from the host shell:
`Blender --background <file>.blend --factory-startup --python brt_audit.py -- --expect '{...}'`.

## Pipeline

In order. A row is done when its gates pass or, where it says picture, when someone has looked.

| # | Step | Module or reference | Passes when |
|---|---|---|---|
| 1 | Probe | `brt_arp` op `probe`; the server's blend-file and objects summaries | `arp.addon_present` read, true or false; file path, save state, active object, mode and the rig's actions with their slots known before any write |
| 2 | Choose the route | `reference/arp-route.md` | Auto-Rig Pro: standard proportions and the add-on installed. Otherwise `brt_retarget` onto the rig the character has; no rig yet and short limbs, ears or a tail: `blender-character-rig` first |
| 3 | Clip sources in a manifest | `reference/clip-sources.md`; `brt_arp` op `source_bones` per skeleton | every entry's file exists and is not empty, names unique, every `fps` equals the scene's; one representative clip checked: skeleton, units, fps, range; the map built from that skeleton |
| 4 | One-clip retarget | `brt_retarget`, or `brt_arp` op `retarget` with `dry_run: True`, then that clip without it | `retarget.output_is_new`, `retarget.finite_keys` 0; `max_step` read; `retarget.first_equals_last` for a loop only. Through `brt_arp`: on the real run `arp.retarget_clips` and `arp.metadata_clips` 1 of 1 |
| 5 | Rest and wrist check | stills, target beside source; `reference/rest-pose-and-conjugation.md` | **Picture** at the first, middle and last frame, front and side: arms at the source's angle, no constant twist about a bone, an FK-baked arm keyed FK; a wrist converted alone, with `into_action`, only once its forearm is right, the hand unaimed (`reference_map`) |
| 6 | Batch retarget | `brt_arp` op `retarget` with every clip, or `brt_retarget` per clip | `arp.retarget_clips` and `arp.metadata_clips` equal the clip count, or every `brt_retarget` call passes; `duplicate_suffixes` empty; each action's real name in the manifest's `action` |
| 7 | Weight repair, when a pose dents or drags | `brt_weights` ops `probe` → `snapshot` → `transfer`; `restore` undoes | `weights.region_vertices` > 0, `weights.snapshot_written`, `weights.changed_vertices` > 0, `weights.weight_sum_error` < 1e-4, `weights.deform_only` 0; **picture** at the worst frame, one camera before and after |
| 8 | Library | `brt_library` | `library.every_action_has_slot`, `library.finite_at_3_frames`, `library.strips_equal_clips`; **picture**: the review track watched end to end |
| 9 | Prop check | `brt_drift` | over every clip, `drift.max_drift` ≤ `tolerance` (2e-5 m) and `drift.max_rotation` ≤ `rotation_tolerance` (0.5°); otherwise `worst` / `worst_rotation` name the action and frame |
| 10 | Save | the user's say-so | saved only when asked, under the name the user gives |
| 11 | Audit the saved file | `brt_audit`, host shell | exit 0: `audit.expect_matches` (`images_without_users` 0 before packing), `audit.props_parented` with `--props`; exit 2: refused input (`{}`) |
| 12 | Hand off | `reference/unity-handoff.md` | one route for the whole library; the character, the prop, the idle and one action exported and checked, back in Blender and in Unity, before the rest |

Numbers cannot close steps 5, 7 and 8: a clip passes every retarget gate with each arm pointing
the wrong way, and a repaired region passes every weight gate while it still looks hollow.

## Worked example

`Runner`, already rigged as `RunnerRig` with an A-pose rest, takes two clips: `HurdleVault` from a
T-pose stock rig and `GateLatchSwing` from a purchased pack.

1. **Probe.** `arp.addon_present` is false and the runner has short limbs anyway: the route is
   `brt_retarget` onto `RunnerRig`.
2. **Manifest.** Two entries, each with its file, fps and direction. The pack's two-person
   `GateLatchSwing` holds one file per actor; only `Courier`, the one who swings, goes onto
   `Runner`. `Partner` would be a second character, which is not covered.
3. **One clip.** `HurdleVault` is imported and its armature named `HurdleVaultRig`. Its frame 1
   stands with the arms down, near `RunnerRig`'s rest, so it is the `reference_frame`; without it
   every arm in the vault would hang lower by the difference between a T-pose and an A-pose. The
   map runs from the root outward and by role: `arm_l` is the upper arm, while `shoulder_l` is a
   clavicle `RunnerRig` does not have; the hands stay out of the first map.

   ```python
   import sys, importlib
   p = "<skill>/scripts"                      # this skill's scripts directory, absolute
   if p not in sys.path: sys.path.insert(0, p)
   import brt_common, brt_retarget; importlib.reload(brt_common); importlib.reload(brt_retarget)
   m = {"Hips": "hips", "Spine": "spine_01", "Chest": "spine_02",          # target: source
        "UpperArm.L": "arm_l", "LowerArm.L": "forearm_l", "UpperArm.R": "arm_r", "LowerArm.R": "forearm_r"}
   result = brt_retarget.run({"source": "HurdleVaultRig", "target": "RunnerRig", "map": m,
                              "reference_frame": 1, "output_action": "Runner_HurdleVault"})
   ```

   It returns `retarget.output_is_new` passing and `retarget.finite_keys` 0; `max_step` equals
   `source_max_step`: how fast the vault moves, not whether the map is right. No seam gate
   without `loop`. `translation_keyed` names `hips`: the rise over the hurdle is not
   converted, so it is keyed on `Hips` or left to the game's controller.
4. **Look.** Stills at the first, middle and last frame beside the source. The wrists hold still
   while the forearms move, and stay out of the map: `RunnerRig`'s `Hand` tails do not lie along
   the palm, so a hand aimed at its tail would swing onto the wrong direction. The grip comes from the
   prop's anchor instead.
5. **The pack clip.** `Courier`'s skeleton rests in an A-pose and names its bones differently:
   `L_Shoulder` is its upper arm and `L_Collar` its clavicle. It gets its own map and its own `K`,
   never the vault's.
6. **Batch, library, prop.** The rest of the manifest, one clip at a time; a rerun onto a kept
   name refuses (`retarget.output_is_new`) unless `overwrite_action`. Each `output_action` goes
   into the manifest's `action`, and `brt_library` runs with `manifest`. `brt_drift`
   checks `Mallet` against `Hand.R` over every clip, position and rotation; then the save when
   asked, `brt_audit` with `--props` for `Mallet`, and the minimal export: the character,
   `Mallet`, the idle and `GateLatchSwing`.

## Discipline

- **`K` belongs to one pair of rests.** A re-run of Match, a moved bone or another source skeleton
  means a new `K`; never copy one, or its curves, from another character.
- **The IK/FK switch is animation data.** Key it at the first frame of every action, or an FK-baked
  arm follows whatever IK target the last clip left.
- **A name is not an identifier.** Read the action name from the call's result, or (`brt_arp`)
  find it by its provenance property; never build it from a clip name.
- **The picture wins.** When a number improves and the still gets worse, go back to the last file
  whose still was right.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Generating the character's mesh from images | `comfyui-asset-generation` |
| Building a custom rig from measured landmarks, skinning by position, a prop attached to a hand bone | `blender-character-rig` |
| The Unity Avatar, Animator Controller, FBX importer and PBR maps | `unity-rigged-character` |
| Animator state machines, events and windows, IK in Unity | `unity-animation` |
| The controller that moves the character | `unity-3d-controller` |
| Finger capture, hand retopology | Not covered |
| Left-hand grips, two-person positioning | Not covered |
| Purchasing content, accounts, credentials, bulk downloaders | The user's, never automated; fetching one stock clip at a time in the user's own browser is in `reference/clip-sources.md` |

## Related skills

`blender-character-rig` for a rig built from measured landmarks and the FBX round trip ·
`unity-rigged-character` for the importer and the Avatar once the FBX reaches Unity ·
`unity-animation` for states, events, root motion and IK on the clips ·
`comfyui-asset-generation` for the mesh, and for a shell that is wrong at the source ·
`unity-3d-controller` for who moves the character · `unity-debug` for proving the clips play in
the running game.
