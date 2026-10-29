# The hand-built route — the same markers, no add-on

> Part of the `character-autorig` skill. The modules are `blender-character-rig`'s
> (`blender-character-rig` → `reference/armature-and-skinning.md`,
> `blender-character-rig` → `reference/fbx-export.md`); this file says how the
> markers feed them and how the result reaches the same gates.

Take this route when Auto-Rig Pro is not installed, when its Match or bind fails on the Blender in
use, or when a marker falls outside its window (a chibi, a large head, short limbs). It builds the
contract skeleton directly, so no role map is needed afterwards.

## Steps

1. **mesh_check** and **arp_markers** as in `SKILL.md`. Outside the windows, rerun
   `arp_markers.py` with `--no-window-gate` once a person has looked at the pictures, and
   `--adjust` the markers that are off. A hand with no finger geometry: add `--mitten`.
2. **Armature** from `contract_bones` (contract names, `.L` mirrored to `.R`, a radius per bone):

   ```python
   import json, bcr_armature
   m = json.load(open("rig/runner.markers.json"))
   bcr_armature.run({"name": "RunnerRig", "collection": "Character", "mesh": "Runner",
                     "mirror": m["contract_bones"]["mirror"], "bones": m["contract_bones"]["bones"]})
   ```

   The markers are world positions; after `bcr_import_prep` the mesh has an identity transform, so
   they are also the mesh-local positions `bcr_armature` takes. `Root` is non-deform at the
   ground between the feet, as the contract wants.
3. **Skin** with `bcr_skin` (positional weights; radii from the spec). Its gates: no unweighted
   vertex, ≤ 4 influences, weight sums 1, no deform bone without vertices. With finger bones on a
   mitten hand, that last gate lists them; `--mitten` in step 1 avoids it.
4. **Contract**: dump the skeleton (`unity-rigged-character` → `reference/humanoid-contract.md`,
   *Dumping a skeleton*) and run
   `contract_map.py map runner-skeleton.json --map contract --require contract --min-fingers 30`
   (drop `--min-fingers` for a mitten).
5. **Deformation**: `deform_gate.py --armature RunnerRig --mesh Runner` on the .blend directly;
   the hand-built rig has no constraints, so its bones pose as they are.
6. **FBX**: `bcr_fbx` snapshot, export, reimport, then `rig_gate.py before.json after.json`
   (exit 0 pass, 1 a gate failed, 2 unreadable). Export with *Only Deform Bones* off so `Root`
   stays in the file.

## What differs from the Auto-Rig Pro route

| | Auto-Rig Pro | Hand-built |
|---|---|---|
| Bone names in the FBX | the add-on's (`arp` role map) | the contract's (no map) |
| Weights | voxel bind, then limited to 4 | positional (`bcr_skin`) |
| Twist bones | exported inside the arm and leg chains | none |
| Control rig for hand-keying | the add-on's IK/FK controls | none: key FK with `bcr_pose` |
| FBX check | the pipeline's export read-back | `bcr_fbx` + `rig_gate.py` |

Both end on the same contract, so clips retargeted for one play on the other, and a character can
move between routes without redoing its clips.
