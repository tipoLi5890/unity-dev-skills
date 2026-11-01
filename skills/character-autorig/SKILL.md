---
name: character-autorig
description: >-
  Rig a humanoid with a licensed Auto-Rig Pro in one command: its AI plus mesh
  markers, gates.
---

# character-autorig — a humanoid rig from the mesh, locally, gated

A generated humanoid mesh reaches this skill normalised (`blender-character-rig` →
`reference/import-and-survey.md`: +Z up, facing −Y, soles on Z 0, scale applied). It leaves as an
FBX on the **humanoid contract** (`unity-rigged-character` → `reference/humanoid-contract.md`),
so every clip made for any contract character plays on it.

## Start here — the request, and where it is answered

| The request or symptom | Read |
|---|---|
| "Auto-rig this character", "rig this character": the default route, one command | [The stages](#the-stages), `scripts/autorig.py` |
| "Auto-Rig Pro without the UI": the `pipeline` op step by step (append, reference bones, Match, bind, Unity humanoid FBX), export settings, the read-back skeleton, refusals | `reference/arp-pipeline.md` |
| Is the mesh riggable — "arms fused to the body", legs one tube, a double shell; what mesh_check and deform_gate measure | `reference/gates.md` |
| "How good is the rig", scoring a change: known-joint bodies, planted faults | `reference/rig-exam.md` |
| "Use Auto-Rig Pro's AI", gloved or closed fingers, face bones, hair pushing a marker out of its window: the `smart` stage, options, gates, fallbacks | `reference/arp-ai.md` |
| "Markers are off": how each marker is found from slices, the windows, the front/side pictures for a person, `--adjust`, the output file | `reference/markers.md` |
| "Elbow collapses when bent", "skin pokes through in a squat", or any failed gate | `reference/failures.md`; the elbow/knee weight repair in `reference/arp-pipeline.md` |
| "The hood, bag, hem or hair should swing": spring-chain bones for a fused shell, `secondary/1` for Unity | `reference/secondary-chains.md`; the Unity side: `unity-rigged-character` → `reference/secondary-motion.md` |
| No add-on, or a chibi outside the marker windows: the hand-built fallback from the markers | [Which route](#which-route); `reference/hand-built-route.md` |
| Auto-Rig Pro's other ops (probe, retarget clips onto its controls) | `blender-retarget` → `reference/arp-route.md` |
| The contract skeleton, role maps, Unity Avatar | `unity-rigged-character` → `reference/humanoid-contract.md` |

> **Rigging is always local.** The default route drives the user's own Auto-Rig Pro; the
> fallback builds the skeleton by hand from the same markers (`blender-character-rig`). No cloud
> rigging service is used at any stage; one may regenerate the **mesh** (upgrade track below).

> **No marker is placed by eye.** Markers are read from horizontal slices of the mesh. With the
> add-on's AI files, its AI places body, finger and face markers too: the body is cross-checked
> against the slices, fingers and face come from the AI, and the slices are the fallback.

## Working contract

- **A genuine Auto-Rig Pro licence.** It is a paid add-on by Artell: please buy it from the
  author's own stores, [Gumroad](https://artell.gumroad.com/l/auto-rig-pro) or
  [Superhive](https://superhivemarket.com/products/auto-rig-pro), which funds its development and
  brings updates ([docs](https://www.lucky3d.fr/auto-rig-pro/doc/)). The optional AI files come with
  the licence, one device each: install them with the add-on's Preferences › Install AI Files…
  (it also clears macOS quarantine), and never copy them into a project, this repository, CI or
  another machine.
- **The user's Blender, the user's add-on.** Installing Blender or Auto-Rig Pro is the user's, on
  request. `brt_arp` finds the enabled add-on and refuses with `addon_missing` when there is
  none; nothing of the add-on lives in this repository.
- **One stage, one command, files in and files out.** Every script prints one JSON object.
  `mesh_check.py`, `arp_smart.py`, `arp_markers.py` and `deform_gate.py` exit **0** pass, **2** a
  gate failed, **1** refused input, like `contract_map.py`. `blender-character-rig`'s `rig_gate.py`
  keeps its own codes (1 a gate failed, 2 unreadable): a stage runner reads each tool's own table.
- **Headless, except the AI.** `blender -b` has no window; `brt_arp` takes the 3D view from the
  file's own screens, so append, Match, bind and export run without the UI. The AI reads pictures
  of the 3D view, so `smart` opens a Blender window and closes it itself. `--factory-startup` turns
  add-ons off: run `smart` and `arp` without it.
- **Save before the rig stage.** A failed gate before the bind removes the rig it appended; after
  the bind the mesh keeps its vertex groups. Work on a copy of the normalised file.
- **A gate failure is fixed locally** (`reference/failures.md`), never by loosening the limit for one
  character.

## The stages

| # | Stage | Tool | Passes when | On failure |
|---|---|---|---|---|
| 1 | Riggable mesh | `scripts/mesh_check.py` (host, numpy) | legs part below the crotch, both arms hang clear in the arm band, double shell ≤ 0.25 (an inward-facing inner shell is reported as `inner_shell`, kept, not gated) | regenerate: back to the views or the 3D generation (`game-character-pipeline` S1/S3) |
| 2 | AI markers (optional) | `scripts/arp_smart.py` (a Blender window) | `smart.*`: body markers, fingers, face, Go!'s reference bones | `reference/arp-ai.md`; stage 3 goes on from slices |
| 3 | Markers | `scripts/arp_markers.py` (Blender or host), `--smart` with stage 2's file | heights in their windows (a near miss passes when the AI's marker is in: `confirmed_by`), left/right within 0.02 H, upper arm 30–60° below horizontal; a **person** accepts the two pictures | `--adjust` the marker that is off; outside the windows → the hand-built route |
| 4 | Auto-Rig Pro | `blender-retarget` → `brt_arp` op `pipeline` | the preset appended, three spine bones, every reference bone placed, Match, bind with no unweighted vertex, ≤ 4 influences, the Unity FBX written and read back | read the failing gate; the rig is rolled back before the bind |
| 5 | Contract | `unity-rigged-character` → `contract_map.py map … --map arp --require contract --min-fingers 30` | 53 bones, chains, sides, axes, Root non-deform at the origin, A-pose | two spine bones: Count 4 (`reference/failures.md`); mitten hands: drop `--min-fingers` |
| 6 | Skin | the pipeline's weight gates; `blender-retarget` → `brt_weights` `probe` | deform weight sum 1 everywhere | `blender-retarget` → `reference/weight-repair.md` |
| 7 | Deformation | `scripts/deform_gate.py` (Blender) | six poses (five without `fist` when the markers say `fingers.mode` `fixed`; `jaw_open` added for a face), on the outward-facing skin: volume loss ≤ 0.35 at hinge and spine joints, every bent elbow and knee measured, new self-intersection p95 ≤ 8 % | `reference/failures.md`; look at `--render` |
| 8 | FBX | the pipeline's export and read-back (Auto-Rig Pro); `bcr_fbx` + `rig_gate.py` (hand-built) | names, parents, weights and influences read back from the file | re-export; never hand-edit the FBX |
| 9 | Spring chains (optional) | `scripts/secondary_chains.py` (Blender) on the rig to take on, then stages 5 and 7 again on its export | `secondary.*`: hood, bag, hem, shorts and hair spikes get `cc_` chains weighted inside their regions only, nothing else moves, colliders clear of every joint; nothing loose = no chain, a pass | `reference/secondary-chains.md`; a missed or wrong region: a marker chain |

Then `unity-rigged-character` (import, Generic by default) and `art-asset-registry` (record the rig
with `licence: {source: "auto-rig-pro", territory: "worldwide"}`; the pipeline puts it on its
`record`).

**One command.** `scripts/autorig.py` runs the stages in order into one folder and prints one
JSON summary (each step's exit code, seconds, log, report and failed gates), exit 0/2/1:

```bash
python3 scripts/autorig.py all out/runner Runner.glb --name Runner [--height 1.75] [--threads 4] \
  [--no-smart] [--facial] [--fingers 5] [--no-render] [--no-repair] [--no-secondary] [--dry-run] \
  [--hair Runner_hair.glb [--hair-chains]] [--eyes Runner_eyes.glb]
# or one stage: prep | check | smart | markers | arp | contract | deform | secondary
python3 scripts/autorig.py --selftest
```

It picks `--min-fingers` and the `fist` pose from the markers' `fingers.mode` (`ai` counts as
found). A failed `smart` never stops `all` (exit 2): the markers fall back to slices. When the
deformation gate fails on elbow or knee volume loss alone, it runs the weight transfer from
`reference/arp-pipeline.md` on a copy (`repair/aN/`) and gates again; the limits never change.
Then the spring chains go on the rig to take on (`secondary/`: its FBX, `NAME.secondary.json`, the
contract and deformation gates again, which read the same as without the chains). A character in
parts has its hair (`--hair`) and eyeballs (`--eyes`) bound after the contract. The summary
lists every attempt and the files to take on. Each stage by hand: `reference/arp-pipeline.md` →
"The stages by hand".

The contract report's `retarget_map` feeds `deform_gate.py --map` and `blender-retarget` → `brt_retarget`'s `map`.

## Which route

| Take Auto-Rig Pro (default) when | Take the hand-built route when |
|---|---|
| the add-on is installed and its probe finds `append_arp`, `match_to_rig`, `bind_to_rig`, `arp_export_fbx_panel` | the add-on is absent, or Match/bind fails on the Blender in use |
| adult proportions: every marker inside its window, or confirmed by the AI | a marker outside its window: a chibi, a giant head, short limbs |
| one body mesh, limbs clear of the torso | (both need stage 1 to pass: no route rigs fused limbs well) |

**Check the Blender version first.** Auto-Rig Pro lists support up to Blender 5.1. On any newer
Blender, run `blender -b --python scripts/tests/test_arp_pipeline.py` (without
`--factory-startup`) before the first character: it must end `16/16 passed`. If append, Match,
bind or export fails there, rig in Blender 5.1 (same scripts, same gates) or take the hand-built
route.

The hand-built route builds `contract_bones` from the same markers with `blender-character-rig`'s
modules and gates it the same way (`reference/hand-built-route.md`).

## Fingers

`arp_markers.py --fingers auto` (default) finds index to little where the hand splits into four
parts across its length; the thumb, and every finger when the hand does not split (a mitten,
fingers together, too few triangles), use a fixed hand shape scaled to wrist → fingertip and
turned to the hand's own plane. `fingers.mode` says which. A mitten character keeps its finger
bones (every clip still binds), drops `--min-fingers` in stage 5 and the `fist` pose in stage 7.
With stage 2, Go!'s finger references replace a `fixed` hand (`fingers.mode` `ai`, their own rolls).

## Upgrade track — after the demo, decided by a person

A person, never a gate, picks an approved demo character; a paid cloud service regenerates
**only its mesh**, which is normalised and comes back to stage 1 and the same local stages. The
skeleton is the contract, so the demo's clips play on it unchanged. Record the new mesh in
`art-asset-registry` with its own licence; the rig keeps `auto-rig-pro`.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Normalising the mesh first: import, height, facing, soles on Z 0 | `blender-character-rig` → `reference/import-and-survey.md` |
| A positional skin for a mascot body, a mesh fitted to one clip pack's skeleton | `blender-character-rig` |
| A mesh that fails stage 1: new views or a new generation | `game-character-pipeline` (S1/S3) · `codex-visual` · `comfyui-asset-generation` |
| The contract itself, `contract_map.py`, the Unity import (Generic by default) | `unity-rigged-character` |
| Clips onto the rig: packs retargeted, a clip library, a held prop | `blender-retarget` |
| Clips from two-camera video onto the contract | `humanoid-motion` |
| Recording the rig and its licence | `art-asset-registry` |
| The character's stage order and tracks | `game-character-pipeline` |
| A cloud rigging service | Never used: rigging is always local |
