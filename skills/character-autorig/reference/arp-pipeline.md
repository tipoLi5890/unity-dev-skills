# The Auto-Rig Pro pipeline — markers to a contract skeleton in one call

> Part of the `character-autorig` skill. The op lives in `blender-retarget` → `scripts/brt_arp.py`
> (its docstring has every parameter); `blender-retarget` → `reference/arp-route.md` covers the
> add-on's other ops: probe, Smart markers, retargeting clips onto its controls; the AI step that
> runs before the markers is `reference/arp-ai.md`. The `export` op
> (below) writes a bound rig again after a weight repair.

`brt_arp.run({"op": "pipeline", ...})` takes a normalised mesh and an `arp_markers.py` result and
leaves an Auto-Rig Pro rig bound to the mesh, a Unity FBX, and the FBX's skeleton as JSON for the
contract check. It needs no window: the AI ran before, in stage `smart`, and reaches the pipeline
only through the markers file's `arp_refs`, `ref_rolls` and `facial`.

```python
import sys; sys.path[:0] = ["<skills>/blender-retarget/scripts"]
import brt_arp
r = brt_arp.run({"op": "pipeline", "mesh": "Runner", "markers": "rig/runner.markers.json",
                 "fbx": "export/Runner.fbx"})
```

## Before the call

- **Probe.** `brt_arp.run({"op": "probe"})` lists the operators the installed add-on registers;
  the pipeline needs `arp.append_arp`, `arp.show_limb_params`, `arp.match_to_rig`,
  `arp.bind_to_rig` and `arp.arp_export_fbx_panel`, and refuses with `operator_missing` naming any
  that is absent; markers with ear references need `arp.add_limb` too.
- **The Blender version.** The add-on lists support up to Blender 5.2. On a newer Blender, run
  `blender -b --python <skill>/scripts/tests/test_arp_pipeline.py` (no `--factory-startup`) once:
  it builds a procedural runner and runs every step below; it must end `16/16 passed`. If a step
  fails, rig in Blender 5.2 with the same scripts, or take the hand-built route.
- **Save first, work on a copy.** A failure before the bind removes the rig it appended; after the
  bind the mesh keeps its vertex groups and Armature modifier.
- **One body mesh.** Join the body's parts, and separate a held prop before the call: the voxel
  bind weights every island to the nearest bones, so a prop left in the mesh bends with the hand
  instead of riding a bone (`blender-character-rig` → `reference/prop-on-bone.md`). The markers
  refuse a prop held beside an arm (`held_prop`).

## Steps

| # | Step | Gate |
|---|---|---|
| 1 | Refusals, changing nothing: mesh missing or already carrying an Armature modifier (`already_bound`); scale or rotation not applied (`transform_not_applied`); markers without `arp_refs` or one of root, neck, head, shoulder, arm, forearm, hand, thigh, leg, foot, toes (`markers_invalid`); no `fbx` path (`export_path_missing`); a rig of that name exists (`rig_exists`); a bind or export setting the add-on lacks | `arp.precondition` |
| 2 | Append the human preset (`arp.append_arp`), rename it `<mesh>Rig` (or `armature`) | `arp.rig_appended` |
| 3 | Spine Count through the add-on's limb options on `root_ref.x`, when the preset's differs | `arp.spine_bones` == Count − 1 |
| 4 | With `facial` true, the face turned on at the head limb (`arp.show_limb_params`: eyes when eye references are placed, no teeth, tongue or eye targets, the set Go! makes), and with ear references the ears added (`arp.add_limb`); a face bone the markers do not place is named in `warnings`. Each reference bone's head and tail from `arp_refs`, world → rig space; a `.l` bone without its `.r` twin is mirrored. A bone in `ref_rolls` takes that roll as is (its `.r` twin the mirror); any other keeps the preset's roll direction, and hand and finger bones turn it with the hand (preset hand frame → the measured one), so palm-in hands get palm-in fingers | `arp.face_added` (with a face or ears); `arp.refs_placed`: every name exists on the rig, the face's included, each end within 1e-4 m, each given roll within 0.1° |
| 5 | Match to Rig | `arp.bone_count` > 0 |
| 6 | Bind, Voxelized, resolution 7, the other settings as `bind` (scene settings set for the call, put back) | |
| 7 | Every vertex limited to `max_influences` (4) deform weights and normalised over deform bones | `arp.vertices_without_group` == 0 |
| 8 | Export with the add-on's FBX exporter: engine Unity, rig type Humanoid, the master trajectory exported, Units ×100 as the add-on's default, and for a rig with a face its Full Facial on (otherwise the exporter folds the secondary face weights onto `head.x` and the jaw, over 4 influences) (scene settings set for the call, put back) | `arp.export_written` |
| 9 | Import the FBX again, read its skeleton and skin, take the import back | `arp.export_armatures` == 1, `arp.export_unweighted` == 0, `arp.export_max_influences` ≤ 4 |
| 10 | Write `<fbx>.skeleton.json` (or `skeleton_out`) | — |

The result has `refs`, `bone_count`, `deform_bone_count`, `bind`, `export`, `reimport` (armature
scale, per-mesh vertex counts, unweighted, max influences), `skeleton`, and `next`: the contract
command. Its `record` carries `licence: {source: "auto-rig-pro", territory: "worldwide"}` for
`art-asset-registry`.

## The spine Count counts the root

The add-on's spine option *Count* includes its root bone. The human preset is Count 3: `root.x`
plus `spine_01.x` and `spine_02.x`, which maps Hips, Spine and Chest and leaves the contract's
**UpperChest** missing (contract tier fails, Unity tier passes). **Count 4** gives `spine_01.x` to
`spine_03.x`. `arp_markers.py` writes `arp_spine_count` = spine bones + 1 = 4 by default, and the
pipeline sets it.

## What the export holds

Names under engine Unity are the add-on's own, not its *Rename for UE* names; that is
`contract_map.py`'s `arp` preset:

| Contract | Exported | Contract | Exported |
|---|---|---|---|
| Root | `c_traj` (with the master trajectory exported) | UpperArm.L | `arm_stretch.l` |
| Hips | `root.x` | LowerArm.L | `forearm_stretch.l` |
| Spine, Chest, UpperChest | `spine_01.x`, `spine_02.x`, `spine_03.x` | Hand.L | `hand.l` |
| Neck, Head | `neck.x`, `head.x` | Index1–3.L … | `c_index1.l` … `c_index3.l` (`c_pinky…` for Little) |
| Shoulder.L | `shoulder.l` | UpperLeg.L, LowerLeg.L | `thigh_stretch.l`, `leg_stretch.l` |
| Toes.L | `toes_01.l` | Foot.L | `foot.l` |

The twist bones (`arm_twist.l`, `forearm_twist.l`, `thigh_twist.l`, `leg_twist.l`) sit inside the
chains: the contract check reports them as extra and walks past them. `forearm_stretch.l` ends at
the twist bone, short of the wrist, so `deform_gate` sizes a joint's patch joint to joint, not by
bone length. A rig with a face exports the face bones too (the runner: 123 bones instead of 84),
with the jaw as `c_jawbone.x`, which the `arp` preset maps to the extra role `Jaw`; `autorig.py`
then adds the `jaw_open` pose.

**Deform in the skeleton JSON comes from the weights.** Blender's FBX importer marks every bone it
reads as deforming, `c_traj` included, which would fail the contract's "Root non-deform". The
pipeline sets `deform` true only for a bone some vertex is weighted to, which is what a skin in the
file means.

**Units ×100.** The add-on's default for Unity writes centimetres, so Blender reads the file back
with the armature at scale 0.01; positions in the skeleton JSON are in metres either way. Check in
Unity once, on the first character: the imported model's root reads scale 1 with File Scale 1
(`unity-rigged-character` → `reference/unity-import.md`). If it reads 100 or 0.01, rerun with
`units_x100: False` and keep that for every character of the project.

## The contract check

```bash
python3 <skills>/unity-rigged-character/scripts/contract_map.py map export/Runner.skeleton.json \
  --map arp --require contract --min-fingers 30 --out rig/runner.contract.json
```

Exit 0: 53 bones mapped, Root non-deform at the origin, the origin between the feet, the upper arm
30–60° below horizontal, sides and axes right. The report's `retarget_map` is the role map for
`deform_gate.py --map` and for `brt_retarget`. A mitten character drops `--min-fingers`, and
`fist` from `deform_gate.py --poses` (`reference/gates.md`); its 30 finger bones are still
exported, so every clip binds.

## Two rigs in one file

Each call appends a new preset with its own name; a second character in the same file is a second
`pipeline` call with another `armature` name. The add-on's scene settings (bind, export) are put
back after each call, so a person's own export settings survive.

## Re-export after a weight repair: `export`

`brt_arp.run({"op": "export", "armature": "RunnerRig", "fbx": "export/Runner.fbx"})` runs steps
7–10 again on a rig the pipeline bound: limit and normalise to `max_influences` (a transfer can add
a fifth weight), export with the same scene settings, read the file back, write the skeleton JSON,
and put the same `licence` on the `record`. It refuses `not_bound` when no mesh holds a deform
weight of the rig. The skeleton is the pipeline's, so the contract report and its `retarget_map`
stay valid; run `contract_map.py` again only if bones changed.

## A hand's weight on the skin beside it: `autorig.py arp`

The voxel bind can leave a hand hanging beside a coat or a thigh holding a little of that skin
(a thumb tip's weight on a greatcoat's back): curling the fingers then drags the coat, and the fist and elbow poses count those folds as self-intersections, more or fewer with
where the AI put the thumb. After the pipeline passes, `autorig.py arp` keeps each side's hand
(`hand.l` and every deform bone under it) on its own skin (`hand_reach`): the distance runs over
the mesh's edges from the skin within `HAND_CORE` (0.2) × wrist → hand_tip of those bones, and
a vertex farther than `HAND_REACH` (1.0) × wrist → hand_tip loses the hand's weight, the rest of
its row rescaled; a piece of the mesh the walk never reaches (a separate cuff) is measured
straight to the bones. Changed vertices mean one more `export` (gate `arp.hand_reach_export`, `reexport: true`; with none
changed the gate is still written, `reexport: false`, the pipeline's FBX standing);
the arp report's `hand_reach` lists them per side.

## An elbow or knee that loses volume: gate, repair, re-export, re-gate

`deform_gate.py` reports `deform.volume_loss_max` at `LowerArm.*` (elbow) or `LowerLeg.*` (knee)
over 0.35: the bind blended the two bones over too long a stretch of skin. The ladder, one rung at a
time, each on a copy, re-gating after each, stopping at the first that passes both deformation
gates; no rung loosens a limit:

1. **The weights** (automated: `scripts/autorig.py deform`, or `all`; `--no-repair` turns it off).
   Only when `deform.volume_loss_max` is the one failing gate and every joint over the limit is an
   elbow or a knee. Each attempt opens `rig/<Name>_arp.blend`, runs the transfers below for that
   hinge on both sides at amount 1.0, `brt_arp` `export`, saves a copy into `repair/aN/` and gates
   that FBX. Next attempt: a hinge that only now fails is added at the same amount; volume held but
   `deform.self_intersection_p95` failed → amount 0.8, then 0.6; anything else ends the ladder with
   exit 2 and every attempt listed. The bands come from the markers, measured along the limb from
   the plane square to it at the joint (`repair_regions`: its normal the mean of shoulder → elbow and
   elbow → wrist, or hip → knee and knee → ankle), and for an elbow a mask from the shoulder
   marker's |x|, the offsets scaled with the height. A band on world Z cuts an arm held at 45° on a
   slant, one side of a thick sleeve handed over above the crease, and that side folds into the
   upper arm in `elbow_120`.
   `deform.cross_side_weight` failing (alone or with that volume loss) is a rung too: the report's
   `skin.cross_side` names the other side's bones holding each side's skin, and past its `band_m`
   from the midline (faded in from half of it) each one's weight there goes in full to its mirrored
   twin (`brt_weights` `transfer`, share `reach`, so its own side keeps it). A sole bound to the
   other foot is that case. Still failing after the move: rebind.
   **Near the limit.** The ladder also runs when every deform gate passed but an elbow's or knee's
   volume margin is under `--repair-near` (default 0.05, a loss past 0.35 × 0.95 = 0.3325): those
   hinges at amount 1.0, then the rungs above. The bind kept is the one with the larger worst
   margin over the deform gates, the original or an attempt that passed every gate (an attempt
   that fails any gate never is); the stage still exits 0. The summary's `repair` block says
   `trigger` `near_limit` (`failed` on a failed gate), `result` `kept_repair` (its files are taken
   on, as after a failed gate) or `kept_original`, and both worst margins. Why 0.05: a wrist that
   moved by millimetres from run to run moved one elbow's loss by about ±0.01 (margin ±0.03), and
   `--min-margin 0.05` is the room asked of a repeated run; an elbow inside that band passes or
   fails by chance, and at 120° a 34 % loss shows where 8 % does not. It takes 0 up to (not
   including) 1; `0` turns it off:

   ```bash
   python3 scripts/autorig.py deform out/runner --repair-near 0
   ```
2. **A finer bind** (by hand). `pipeline` (or `bind`) again from the unrigged file with a higher
   `resolution`, one step at a time (`autorig.py arp OUT --resolution 8`, then `contract` and `deform`):
   each step costs much more memory and time, and the top of the range may not finish.
3. **The marker** (by hand). Move it along the limb to the crease (`arp_markers.py --adjust` with
   `elbow.L` or `knee.L`; the right side follows; `autorig.py markers OUT --adjust FILE`) and run
   `pipeline` again.

A loose sleeve hides the crease: the bind's blend then follows the cloth, not the arm, a finer
voxel grid or a moved marker shifts it little, and the weight transfer is the fix that holds; that
is why it is the first rung. The weight repair, step by step:

1. **Gate.** `deform_gate.py` on the export; read which joint, which pose, and `joints_measured`.
2. **Bones.** The weights sit on Auto-Rig Pro's deform bones, not contract names: take them from
   the contract report's `retarget_map` (`UpperArm.L` → `arm_stretch.l`, `LowerArm.L` →
   `forearm_stretch.l`). Twist bones are deform on some rigs and not others: list the rig's
   deform bones and keep only those; `brt_weights` refuses a bone that is not deform.
3. **Regions** from the markers: `autorig.repair_regions(markers, "elbow")` gives per side the
   joint, the seam's normal and the radius round the limb's axis, the two bands as distances from
   the seam, and for an elbow the |x| mask just outside the torso's half width (0 inside `inner`,
   full past `outer`), so the torso never changes. A knee needs no X mask.
4. **A snapshot** (`brt_weights` `snapshot`, with the elbow's mask), then **two transfers per side**
   (`autorig.hinge_transfer` on the mesh's weights): in the band below the seam (forearm or shin
   side) the upper bones' weight moves to the lower bone; in the band above it, the lower bones'
   weight moves to the upper bone. A narrow band at the crease itself stays blended; four-value
   bands fade each end.
5. **`brt_arp` `export`**, then **`deform_gate.py` again** on the new file. `restore` puts the
   snapshot back if the gate reads worse.

`autorig.py`'s `_inside repair` is that recipe (`--hinges elbow --amount 1.0`); its summary lists the
`regions` of each attempt. A sharper hand-over keeps more volume but folds more: watch
`deform.self_intersection_p95` in `elbow_120` move the other way, and look at its render. The whole
amount (1.0) hands each band over completely and leaves the crease band blended; take it down
toward 0.8 or 0.6 when the intersections climb. When the two gates cannot both pass, go back to the
marker and the views, not a looser limit.

## The stages by hand

What `autorig.py all` runs, one stage at a time (paths relative to the character's folder; the
rig to chain is the passing or kept repair's `repair/aN/Runner_arp.blend` when there was one). Relative paths
are read from the working directory (`//` from the .blend).

```bash
python3 scripts/mesh_check.py Runner.glb --out rig/runner.mesh.json
blender -b Runner.blend -P scripts/arp_markers.py -- --mesh Runner \
  --out rig/runner.markers.json --preview-dir rig/markers/
blender -b Runner.blend --python-expr "$(cat <<'PY'
import sys; sys.path[:0] = ['<skills>/blender-retarget/scripts']
import bpy, brt_arp
r = brt_arp.run({'op': 'pipeline', 'mesh': 'Runner', 'markers': 'rig/runner.markers.json',
                 'fbx': 'export/Runner.fbx', 'report_path': 'rig/runner.arp.json'})
bpy.ops.wm.save_as_mainfile(filepath='rig/Runner_arp.blend')
sys.exit(0 if r.get('pass') is True else 2)
PY
)"
python3 <skills>/unity-rigged-character/scripts/contract_map.py map export/Runner.skeleton.json \
  --map arp --require contract --min-fingers 30 --out rig/runner.contract.json
# a character in parts (Runner_hair.glb beside Runner.glb): bind the hair to Head before the deformation gate
blender -b -P <skills>/blender-character-rig/scripts/assemble_parts.py -- bind . --hair Runner_hair.glb \
  --rig-glb Runner.glb --name Runner --report rig/Runner.bind.json
# eyeballs (eye_fit.py fit's Runner_eyes.glb): each rigid on its eye bone (c_eye.l/.r with --facial, else Head)
blender -b -P <skills>/blender-character-rig/scripts/eye_fit.py -- bind . --eyes Runner_eyes.glb \
  --rig-glb Runner.glb --name Runner --report rig/Runner.eyes_bind.json
blender -b -P scripts/deform_gate.py -- --fbx export/Runner.fbx --map rig/runner.contract.json \
  --render rig/poses/ --out rig/runner.deform.json
# fingers.mode "fixed" (a mitten): add --poses arms_up,deep_squat,torso_twist,leg_raise,elbow_120
blender -b rig/Runner_arp.blend -P scripts/secondary_chains.py -- --mesh Runner --map rig/runner.contract.json \
  --save secondary/Runner_sec.blend --fbx secondary/Runner.fbx --out secondary/Runner.secondary.json \
  --report secondary/Runner.secondary.gate.json
# then contract_map.py and deform_gate.py again on secondary/Runner.skeleton.json and secondary/Runner.fbx
```
