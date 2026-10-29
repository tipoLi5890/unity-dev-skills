# The humanoid contract — one skeleton every motion source maps to

Every humanoid character in this pipeline ends on one fixed skeleton, and every motion source
reaches it through a role map: Mixamo, Auto-Rig Pro's export, a purchased clip pack, any other
dumped skeleton. A two-camera solve (`humanoid-motion`) is fitted onto the contract rig itself. A clip made for one character then plays on any other contract
character, and a character whose mesh is redone keeps every clip, because the bone names, the
hierarchy, the rest pose and the axes stay the same.

`scripts/contract_map.py` holds the table below as code: it maps a skeleton onto the contract,
lists what is missing or extra, checks the parent chain, and gates.

## Rest, axes, units

| Property | Contract |
|---|---|
| Up, facing | +Z up, the character faces −Y; `.L` is the character's left, at +X |
| Origin | on the ground (z = 0) between the feet; `Root` sits there |
| Rest pose | A-pose: upper arm 45° below horizontal by default (30–60° accepted), palms down, legs straight, feet parallel |
| Units, scale | metres; armature and meshes at scale 1, rotations applied |
| Names | the names below, case-sensitive, Blender's `.L` / `.R` suffix |
| Root | `Root`, non-deform, parent of `Hips`; carries the ground-plane motion when a clip has root motion |

## The bones

53 bones. **Unity-required** are the 15 bones Unity's Humanoid needs; the rest complete the
contract. Each bone's parent is the row above it in its chain.

| Contract bone | Parent | Unity human name (`HumanTrait.BoneName`) | Tier |
|---|---|---|---|
| `Root` | — | — (non-deform) | contract |
| `Hips` | `Root` | `Hips` | Unity-required |
| `Spine` | `Hips` | `Spine` | Unity-required |
| `Chest` | `Spine` | `Chest` | contract |
| `UpperChest` | `Chest` | `UpperChest` | contract |
| `Neck` | `UpperChest` | `Neck` | contract |
| `Head` | `Neck` | `Head` | Unity-required |
| `Shoulder.L` | `UpperChest` | `LeftShoulder` | contract |
| `UpperArm.L` | `Shoulder.L` | `LeftUpperArm` | Unity-required |
| `LowerArm.L` | `UpperArm.L` | `LeftLowerArm` | Unity-required |
| `Hand.L` | `LowerArm.L` | `LeftHand` | Unity-required |
| `Thumb1.L` … `Thumb3.L` | `Hand.L`, then the previous | `Left Thumb Proximal` / `Intermediate` / `Distal` | contract |
| `Index1.L` … `Index3.L` | `Hand.L`, then the previous | `Left Index Proximal` / … | contract |
| `Middle1.L` … `Middle3.L` | `Hand.L`, then the previous | `Left Middle Proximal` / … | contract |
| `Ring1.L` … `Ring3.L` | `Hand.L`, then the previous | `Left Ring Proximal` / … | contract |
| `Little1.L` … `Little3.L` | `Hand.L`, then the previous | `Left Little Proximal` / … | contract |
| `UpperLeg.L` | `Hips` | `LeftUpperLeg` | Unity-required |
| `LowerLeg.L` | `UpperLeg.L` | `LeftLowerLeg` | Unity-required |
| `Foot.L` | `LowerLeg.L` | `LeftFoot` | Unity-required |
| `Toes.L` | `Foot.L` | `LeftToes` | contract |

The `.R` side mirrors every `.L` row (`Right…`, `Right Thumb Proximal`, …). Unity's finger names
say **Little**, never Pinky: a map that says `Left Pinky Proximal` maps nothing, which is why
`CharacterHumanoidAvatar.cs` refuses any name not in `HumanTrait.BoneName`. Twist, bend,
helper and prop-socket bones are allowed beside the contract (a `Socket.R` under `Hand.R` for the
runner's pickup); they are reported as extra and never fail a gate.

## Role maps

Contract bone → source bone. The built-in maps are `contract_map.py presets`; `--map auto` tries
each and keeps the one that maps the most required bones. A name also matches with its namespace
stripped, so `mixamorig1:Hips` answers to `Hips`.

| Contract | Mixamo (`mixamorig:` + …) | Auto-Rig Pro `arp` | Auto-Rig Pro `arp-ue` |
|---|---|---|---|
| `Root` | — | `c_traj` | `root` |
| `Hips` | `Hips` | `root.x` | `pelvis` |
| `Spine` | `Spine` | `spine_01.x` | `spine_01` |
| `Chest` | `Spine1` | `spine_02.x` | `spine_02` |
| `UpperChest` | `Spine2` | `spine_03.x` | `spine_03` |
| `Neck` | `Neck` | `neck.x` | `neck_01` |
| `Head` | `Head` | `head.x` | `head` |
| `Shoulder.L` | `LeftShoulder` | `shoulder.l` | `clavicle_l` |
| `UpperArm.L` | `LeftArm` | `arm_stretch.l` | `upperarm_l` |
| `LowerArm.L` | `LeftForeArm` | `forearm_stretch.l` | `lowerarm_l` |
| `Hand.L` | `LeftHand` | `hand.l` | `hand_l` |
| `Thumb1–3.L` | `LeftHandThumb1–3` | `c_thumb1–3.l` | `thumb_01–03_l` |
| `Index1–3.L` (and Middle, Ring) | `LeftHandIndex1–3` | `c_index1–3.l` | `index_01–03_l` |
| `Little1–3.L` | `LeftHandPinky1–3` | `c_pinky1–3.l` | `pinky_01–03_l` |
| `UpperLeg.L` | `LeftUpLeg` | `thigh_stretch.l` | `thigh_l` |
| `LowerLeg.L` | **`LeftLeg`** | `leg_stretch.l` | `calf_l` |
| `Foot.L` | `LeftFoot` | `foot.l` | `foot_l` |
| `Toes.L` | `LeftToeBase` | `toes_01.l` | `ball_l` |

`.R` takes `Right…` (Mixamo), `.r` (`arp`) or `_r` (`arp-ue`). End joints
(`…End`, `HeadTop_End`, `…4` on Mixamo fingers) are end sites, listed apart from extra bones.

**Mixamo.** `LeftUpLeg` is the thigh and **`LeftLeg` the lower leg**: a map written for a
skeleton whose `LeftLeg` is the thigh puts the shin under the hip, and the parent-chain gate fails
it. Some skeletons carry four joints per finger, the first at the palm (a metacarpal); map their
`2–4` to the contract's `1–3` in a role-map file, and confirm which joint sits at the palm by
dumping the skeleton and checking that its head is nearer the wrist than the knuckles.

**Auto-Rig Pro.** `arp` is the humanoid export without *Rename for UE*, the shape `blender-retarget`
→ `brt_arp` produces; `arp-ue` is the same export with *Rename for UE* on (`root` exists only when
the master trajectory is exported). Both columns follow the add-on's rename code.

- Confirm the spine count before trusting `Chest` and `UpperChest`: a two-bone spine exports
  `spine_01.x`, `spine_02.x` only, `UpperChest` comes back missing, and the rig passes the Unity
  tier but not the contract tier. Set the add-on's spine *Count* to 4 (it counts its root, so
  Count 4 gives `spine_01.x`–`spine_03.x`; Count 3 gives two), or accept a rig that is Unity-tier
  only. `brt_arp`'s `pipeline` op takes the count from the markers file, 4 by default.
- Twist bones (`thigh_twist.l`, `arm_twist.l`) sit inside the chains; the chain check walks past
  them, and they are reported as extra.

**A purchased clip pack, or any skeleton without a preset.** Many packs share `arp-ue`'s mannequin
names; try `--map auto` first. Otherwise build the map once per skeleton (per level of detail, for
a skeleton whose joint count changes with it):

1. Dump the skeleton (the rig FBX imported into Blender, the snippet below).
2. `contract_map.py suggest pack.json --out pack-map.json` proposes a map from the names.
3. Review every row against the dump — a suggestion is never a map until a person has read it —
   and run `contract_map.py map pack.json --map pack-map.json --min-fingers 30`.

A pack with no finger bones maps the body only; keep it on the Unity tier and pose the fingers with
a fixed hand shape.

## Dumping a skeleton

**Blender** (armature space; the format `contract_map.py` reads; a `bcr_fbx` snapshot also reads
as is). Blender's FBX importer marks every bone deform, `Root` included, so `deform` is taken from
the weights: a bone deforms when it is marked deform and some vertex carries its group.

```python
import bpy, json
rig = bpy.data.objects["RunnerRig"]
weighted = {m.vertex_groups[g.group].name for m in bpy.data.objects
            if m.type == 'MESH' and m.find_armature() == rig
            for v in m.data.vertices for g in v.groups if g.weight > 0}
bones = [{"name": b.name, "parent": b.parent.name if b.parent else None,
          "head": list(rig.matrix_world @ b.head_local), "tail": list(rig.matrix_world @ b.tail_local),
          "deform": b.use_deform and b.name in weighted} for b in rig.data.bones]
json.dump({"schema": "skeleton/1", "source": "blender", "up": "+Z", "forward": "-Y", "units": "m",
           "bones": bones}, open("/tmp/runner-skeleton.json", "w"), indent=1)
```

**BVH**: pass the file itself; `contract_map.py` reads the HIERARCHY (head = summed `OFFSET`s,
tail = the first child or the End Site) and converts Y-up to Z-up the way Blender's importer does.
`--scale 0.01` for a file in centimetres. `contract_map.py bvh clip.bvh --out clip-skeleton.json`
writes the skeleton JSON on its own, with each joint's `channels` (a root with position channels
carries translation that the retarget must keep).

## Mapping and gating

```bash
python3 scripts/contract_map.py map runner-skeleton.json --require contract --min-fingers 30
python3 scripts/contract_map.py map walk.bvh --scale 0.01 --map mixamo --map-out walk-map.json
python3 scripts/contract_map.py map pack.json --map auto --unity-out Assets/Models/Runner/runner.human.json
```

| Gate | Fails when |
|---|---|
| `required` | any of Unity's 15 required bones is unmapped |
| `contract` (`--require contract`) | any contract bone is unmapped, `Root` deforms, `Root` is off the origin, the origin is not between the feet, or the upper arms are outside the A-pose range; a names-only skeleton (no heads) fails it too, since the rest cannot be checked |
| `fingers` (`--min-fingers N`) | fewer than N finger bones are mapped, both hands together |
| `unique` | one source bone is mapped to two contract bones |
| `parent_chain` | a mapped bone's nearest mapped source ancestor is not its nearest mapped contract ancestor: a leg under the wrong hip, a finger under the forearm, a map that takes a thigh for a shin |
| `sides` | an `.L` bone does not lie at larger x than its `.R` twin: left and right swapped, or the skeleton faces +Y |
| `axes` | Head not above Hips, Hips not above the feet (wrong up axis), or toes behind the foot (wrong facing) |

The report's `retarget_map` is `{contract_bone: source_bone}`, the orientation `blender-retarget`
→ `brt_retarget` takes for `map` (target: source); `--map-out` writes it as a role-map file.
`human` (and `--unity-out`) is `[{humanName, boneName}]` for Unity. Exit 0 every gate passed, 2 a
gate failed, 1 refused input.

## Acceptance — a character is on the contract when

1. `contract_map.py map <its dump> --map <its map> --require contract --min-fingers 30` exits 0
   (`contract` for a rig built with the contract's names, `arp` for an Auto-Rig Pro export):
   every bone present by name, chains, sides, axes, Root and the A-pose rest all pass. A character
   with mitten hands drops `--min-fingers` and keeps the finger bones unweighted, so every clip
   still binds.
2. Scale 1 and rotations applied on the armature and every mesh; the FBX is exported with *Only
   Deform Bones* off, or `Root` (non-deform) is left out of the file.
3. The body FBX carries the rest pose, not an action: Unity's default pose is the first frame of
   any action in the file.
4. A source skeleton is accepted for retargeting when `map` exits 0 on the Unity tier with its role
   map, and a person has read `missing_optional` and `extra`.

## In Unity — Generic by default

Clips arrive baked onto the contract skeleton, so the character imports **Generic**
(`character-pipeline.json` `"rig"` defaults to `Generic`): the Blender pose plays exactly.
Choose Humanoid only when the game needs foot or hand IK or a body-part AvatarMask, and then build
the Avatar from the explicit map, not Unity's automatic mapping (which can leave Chest out and maps
no finger on many rigs):

1. `"rig": "Humanoid"` in the folder's `character-pipeline.json`; for a skeleton that is not the
   contract's, also `"humanMap": "runner.human.json"` (written by `contract_map.py --unity-out`).
   Reimport Character Folder.
2. **Build Humanoid Avatar** (`CharacterHumanoidAvatar.Build(folder)`): every `HumanTrait.BoneName`
   in the map, the skeleton from the imported body, then the gate: `isValid`, `isHuman`, `Chest`
   mapped, at least `minFingerBones` (default 10) finger bones mapped.
3. **Link Animation Avatars**: the linker applies the same gate before it links any clip.
4. Open Configure once. An A-pose builds a valid Avatar; if IK reaches look wrong, use Enforce
   T-Pose there and save, then compare a hand on a Generic and a Humanoid copy
   (`reference/unity-import.md` §1).
