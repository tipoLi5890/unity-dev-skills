# The Auto-Rig Pro pipeline — markers to a contract skeleton in one call

> Part of the `character-autorig` skill. The op lives in `blender-retarget` → `scripts/brt_arp.py`
> (its docstring has every parameter); `blender-retarget` → `reference/arp-route.md` covers the
> add-on's other ops: probe, Smart markers, retargeting clips onto its controls. The `export` op
> (below) writes a bound rig again after a weight repair.

`brt_arp.run({"op": "pipeline", ...})` takes a normalised mesh and an `arp_markers.py` result and
leaves an Auto-Rig Pro rig bound to the mesh, a Unity FBX, and the FBX's skeleton as JSON for the
contract check. It never runs Smart detection and needs no window.

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
  that is absent.
- **The Blender version.** The add-on lists support up to Blender 5.1. On a newer Blender, run
  `blender -b --python <skill>/scripts/tests/test_arp_pipeline.py` (no `--factory-startup`) once:
  it builds a procedural runner and runs every step below; it must end `13/13 passed`. If a step
  fails, rig in Blender 5.1 with the same scripts, or take the hand-built route.
- **Save first, work on a copy.** A failure before the bind removes the rig it appended; after the
  bind the mesh keeps its vertex groups and Armature modifier.
- **One body mesh.** Join the body's parts, and separate a held prop before the call: the voxel
  bind weights every island to the nearest bones, so a prop left in the mesh bends with the hand
  instead of riding a bone (`blender-character-rig` → `reference/prop-on-bone.md`).

## Steps

| # | Step | Gate |
|---|---|---|
| 1 | Refusals, changing nothing: mesh missing or already carrying an Armature modifier (`already_bound`); scale or rotation not applied (`transform_not_applied`); markers without `arp_refs` or one of root, neck, head, shoulder, arm, forearm, hand, thigh, leg, foot, toes (`markers_invalid`); no `fbx` path (`export_path_missing`); a rig of that name exists (`rig_exists`); a bind or export setting the add-on lacks | `arp.precondition` |
| 2 | Append the human preset (`arp.append_arp`), rename it `<mesh>Rig` (or `armature`) | `arp.rig_appended` |
| 3 | Spine Count through the add-on's limb options on `root_ref.x`, when the preset's differs | `arp.spine_bones` == Count − 1 |
| 4 | Each reference bone's head and tail from `arp_refs`, world → rig space; a `.l` bone without its `.r` twin is mirrored. A bone keeps the preset's roll direction; hand and finger bones turn it with the hand (preset hand frame → the measured one), so palm-in hands get palm-in fingers | `arp.refs_placed`: every name exists on the preset, each end within 1e-4 m |
| 5 | Match to Rig | `arp.bone_count` > 0 |
| 6 | Bind, Voxelized, resolution 7, the other settings as `bind` (scene settings set for the call, put back) | |
| 7 | Every vertex limited to `max_influences` (4) deform weights and normalised over deform bones | `arp.vertices_without_group` == 0 |
| 8 | Export with the add-on's FBX exporter: engine Unity, rig type Humanoid, the master trajectory exported, Units ×100 as the add-on's default (scene settings set for the call, put back) | `arp.export_written` |
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
chains: the contract check reports them as extra and walks past them.

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
   `deform.self_intersection_p95` failed → amount 0.9; anything else ends the ladder with exit 2
   and every attempt listed. The bands come from the markers: the joint's marker height (both sides'
   mean), and for an elbow a mask from the shoulder marker's |x|, the offsets scaled with the height.
2. **A finer bind** (by hand). `pipeline` (or `bind`) again from the unrigged file with a higher
   `resolution`, one step at a time: each step costs much more memory and time, and the top of the
   range may not finish.
3. **The marker** (by hand). Move it along the limb to the crease (`arp_markers.py --adjust` with
   `elbow.L` or `knee.L`; the right side follows) and run `pipeline` again.

A loose sleeve hides the crease: the bind's blend then follows the cloth, not the arm, a finer
voxel grid or a moved marker shifts it little, and the weight transfer is the fix that holds; that
is why it is the first rung. The weight repair, step by step:

1. **Gate.** `deform_gate.py` on the export; read which joint, which pose, and `joints_measured`.
2. **Bones.** The weights sit on Auto-Rig Pro's deform bones, not contract names: take them from
   the contract report's `retarget_map` (`UpperArm.L` → `arm_stretch.l`, `LowerArm.L` →
   `forearm_stretch.l`). Twist bones are deform on some rigs and not others: list the rig's
   deform bones and keep only those; `brt_weights` refuses a bone that is not deform.
3. **Probe** the region with the bones before changing anything: Z bands around the joint's marker
   height (`elbow.L` z from the markers file), and for an elbow `axis: "X"` with
   `mask: {inner, outer}` just outside the torso's half width, so the torso never changes
   (`inner` < `outer`: 0 inside `inner`, full past `outer`). A knee needs no X mask.
4. **One snapshot** covering both bands, then **two transfers per side**: in the band below the
   joint (forearm or shin side) the upper bone's weight moves to the lower bone; in the band above
   it, the lower bone's weight moves to the upper bone. Leave a narrow band at the crease itself
   blended. Four-value bands fade each end.
5. **`brt_arp` `export`**, then **`deform_gate.py` again** on the new file. `restore` puts the
   snapshot back if the gate reads worse.

```python
import brt_weights, brt_arp
base = {"mesh": "Runner", "armature": "RunnerRig", "axis": "X", "mask": {"inner": 0.22, "outer": 0.25},
        "backup_path": "rig/runner_elbows.npz"}
brt_weights.run({**base, "op": "snapshot", "z_band": [0.95, 0.97, 1.22, 1.24]})
for s in ("l", "r"):
    brt_weights.run({**base, "op": "transfer", "z_band": [0.98, 1.01, 1.08, 1.095], "amount": 1.0,
                     "from_bones": [f"arm_stretch.{s}", f"arm_twist.{s}"], "to_bones": [f"forearm_stretch.{s}"]})
    brt_weights.run({**base, "op": "transfer", "z_band": [1.103, 1.118, 1.19, 1.22], "amount": 1.0,
                     "from_bones": [f"forearm_stretch.{s}", f"forearm_twist.{s}"],
                     "to_bones": [f"arm_stretch.{s}"]})
brt_arp.run({"op": "export", "armature": "RunnerRig", "fbx": "export/Runner.fbx"})
# then: blender -b -P deform_gate.py -- --fbx export/Runner.fbx --map rig/runner.contract.json ...
```

The numbers are the runner's (elbow at z 1.10, shoulder marker at |x| 0.205, torso half width
under 0.22); read your own from the markers and the probe, or from the `regions` that
`autorig.py` lists for each attempt in its summary. A sharper hand-over keeps more volume but folds more: watch
`deform.self_intersection_p95` in `elbow_120` move the other way, and look at its render. The whole
amount (1.0) hands each band over completely and leaves the crease band blended; take it down
toward 0.9 when the intersections climb. When the two gates cannot both pass, go back to the
marker and the views, not a looser limit.
