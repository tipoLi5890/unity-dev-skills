---
name: blender-retarget
description: >-
  Put stock or purchased clips on a rigged character in Blender: retarget,
  clip library, weight repair.
---

# blender-retarget — map the rest pose, then move the clips

A keyed bone rotation is a turn away from that bone's own rest. Retargeting is a rest-pose and
rotation-frame problem, not a matter of rotating a bone a few degrees: two skeletons that rest
differently give the same four numbers two meanings. A clip that looks wrong on the target is
almost always the frame (a T-pose source read against an A-pose rest, a bone mapped by name
instead of by role) or the mode (an arm baked onto FK controls and played in IK), not the keys.

## Start here — the request, and where it is answered

| The request or symptom | Read |
|---|---|
| "Put these clips on my rig": the order of the steps | [Pipeline](#pipeline); one call per module, `reference/modules.md` |
| Arms twist, flare or cross; a T-pose source on an A-pose rig; the constant `K`, sign continuity, mapping by role, when `K` is recomputed | `reference/rest-pose-and-conjugation.md` |
| Auto-Rig Pro, when installed: when the route fits, the probe, markers, Match then Bind, the source skeleton probed for the map, the per-clip sequence and its dry run; a retargeted arm that still follows its IK target (IK/FK switches) | `reference/arp-route.md` |
| One pack supplies every clip — fit, not retarget: the measured bake-off, added foot slide, late-starting and missing curves, a clip from another skeleton converted once | `reference/route-bakeoff.md` |
| Clips: the manifest, a stock library in the user's browser, a purchased pack and its variants, fps, licence | `reference/clip-sources.md` |
| Actions renamed ".001"; a library of many clips that needs previews and one NLA review track; layered actions and slots, fake users, asset marks and the catalog, check renders | `reference/action-library.md` |
| A shoulder or upper back that collapses or drags when the arm lifts: probe, mask, transfer, deform-only normalising, backup and restore | `reference/weight-repair.md` |
| A prop that must stay on the hand bone in every clip | `brt_drift`, [Pipeline](#pipeline) step 9; `reference/modules.md` |
| The quality target first; which layer is wrong (geometry, skinning, animation, material), a fixed grip, stop rules, the failure log | `reference/defect-triage-and-stop.md` |
| Handing the library to Unity: which skeleton, which clips, what survives the FBX, the minimal validation | `reference/unity-handoff.md` |
| A worked example: a T-pose stock clip and a pack clip onto the runner | `reference/worked-example.md` |
| The parameters of one module | its docstring, `scripts/brt_*.py` |

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

## Pipeline

In order. A row is done when its gates pass or, where it says picture, when someone has looked.

| # | Step | Module or reference | Passes when |
|---|---|---|---|
| 1 | Probe | `brt_arp` op `probe`; the server's blend-file and objects summaries | `arp.addon_present` read, true or false; file path, save state, active object, mode and the rig's actions with their slots known before any write |
| 2 | Choose the route | `reference/route-bakeoff.md`; `reference/arp-route.md` | One pack supplies the motion: no retarget, fit the mesh to its skeleton (`blender-character-rig` → `reference/fit-to-clip-skeleton.md`). Auto-Rig Pro: standard proportions and the add-on installed. Otherwise `brt_retarget` onto the character's rig |
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
| The character's stage order, and where retargeting sits in it | `game-character-pipeline` |
| Proving the clips play in the running game | `unity-debug` |
| Purchasing content, accounts, credentials, bulk downloaders | The user's, never automated; fetching one stock clip at a time in the user's own browser is in `reference/clip-sources.md` |
