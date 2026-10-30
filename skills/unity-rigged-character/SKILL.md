---
name: unity-rigged-character
description: >-
  Rigged FBX into Unity: Avatar (Generic or Humanoid), Animator, prop sockets, T-pose fixes.
---

# unity-rigged-character — the Unity-side character contract

A skinned FBX reaches Unity; this skill makes it a character the game can drive:
**import → Avatar → Animator → gameplay rig**. Where the FBX came from is upstream, and each
upstream route has its own skill. An asset with no skeleton belongs to `unity-3d-models`.

## Request or symptom → where to look

| Request or symptom | Go to |
|---|---|
| Rig type and Configure: Generic by default, Humanoid for a body-part mask or IK | `reference/unity-import.md` §1 |
| Humanoid built from an explicit map — Chest and fingers mapped; role maps for Mixamo, Auto-Rig Pro, clip packs | `reference/humanoid-contract.md` |
| An upper-body mask | `reference/unity-import.md` §1 (Generic masks list transform paths) |
| Every clip is named `mixamo.com` (or `Take 001`) and clips overwrite each other; `@Clip` naming; `loopPose` | below, then `reference/unity-import.md` |
| The character T-poses in place | below, then `reference/unity-import.md` |
| A held prop is left behind or sits off the hand; a prop socket under Optimize Game Objects | below, then `reference/unity-import.md` §3 |
| A white mannequin; PBR maps an FBX drops | below, then `reference/textures.md` |
| A hitbox far wider than the character | below, then `reference/gameplay-rig.md` |
| Curveless bones, root aliases, sampling and skinning in batchmode on a clip pack's skeleton | `reference/shared-skeleton-generic.md` |
| Which Editor script automates which step | [Editor scripts](#editor-scripts), `reference/editor-scripts.md` |
| Anything else that looks wrong after import | `reference/troubleshooting.md` |

## The five things that go wrong, and where they are answered

- **Every clip is named `mixamo.com`** (or `Take 001`, or after the Blender scene) and clips
  overwrite each other → one FBX per clip, named `<name>@<Clip>.fbx`; the importer renames.
  `reference/unity-import.md`
- **The character T-poses in place** → each animation file built its own Avatar: Copy From Other
  Avatar, re-run as a command. `reference/unity-import.md`
- **A held prop is left behind, or sits off the hand** → Optimize Game Objects removed the
  socket (expose it), or a Blender-retargeted clip plays through Humanoid (import it Generic).
  `reference/unity-import.md`
- **A white mannequin, or uniform plastic** → maps not reattached; a Blender or Mixamo FBX never
  arrives with its metallic map bound, and smoothness is not roughness. `reference/textures.md`
- **The hit box is far wider than the character** → it was sized from the skinned renderer,
  whose box is fixed at import and looser than the body. `reference/gameplay-rig.md`

> **Unity never retargets across skeletons here.** Every clip arrives already on the character's
> skeleton — retargeted in Blender, by Mixamo on that route, or played as bought on a character
> fitted to the clip pack's own skeleton (`reference/shared-skeleton-generic.md`) — so the rig
> type follows from what the game needs. Generic (the config default) reproduces the Blender pose; Humanoid
> re-solves it through muscle space, so bone rotations and socket positions can drift from the source on the same
> clip. Choose Humanoid only for a body-part mask, IK or other avatars; measure it first — play one clip under both
> rig types, sample the same frames, and compare each bone's rotation and each socket's world position against the
> Blender pose and against the limits the game tolerates (`reference/unity-import.md` §1) — and build the Avatar from
> the explicit contract map, Chest and fingers included (`reference/humanoid-contract.md`).
>
> **A GLB has no Rig tab** (glTFast uses its own importer). It takes Humanoid clips through an
> Avatar built from bone names with `AvatarBuilder.BuildHumanAvatar` (`reference/unity-import.md`
> §1); otherwise the character comes in as FBX.

---

## Which route brought the FBX

| Route | Unity receives | Read first |
|---|---|---|
| **Auto-Rig Pro and a clip library** — standard humanoid, Auto-Rig Pro installed | a deform skeleton with clips baked onto it | skill `blender-retarget` (`blender-retarget` → `reference/unity-handoff.md`), then `reference/unity-import.md` |
| **Fitted to a clip pack's skeleton** — one pack supplies the motion | character FBX on the pack's skeleton; the pack's own clip files, unedited | `reference/shared-skeleton-generic.md` |
| **A custom Blender rig** — chibi or short limbs, extra bones (ears, a tail), a custom action | one FBX: mesh, armature, the action | skill `blender-character-rig`, then `reference/unity-import.md` §4 |
| **Mixamo** — optional; standard humanoid, stock clips | `<name>.fbx` with skin, one `<name>@<Clip>.fbx` per clip | `reference/mixamo-route.md` |
| **An auto-rig service's export** — rigged by the image-to-3D or rigging service | one skinned FBX, sometimes with clips | `reference/unity-import.md` §1: check the mapping before anything else |

The route is chosen once per character, in `game-character-pipeline`, before the art is
commissioned: Mixamo wants a T-pose mesh in one piece, auto-rig services a T- or A-pose, the
Blender routes an A-pose that keeps every piece (`game-character-pipeline` G0); what each route
hands Unity: `reference/source-art-and-3d.md`.

## The contract

Each stage has a reference file. Read the one you are standing in, not all of them.

| # | Stage | Read |
|---|---|---|
| 0 | The humanoid contract: bones, rest and axes, role maps from Mixamo, Auto-Rig Pro and a clip pack, `contract_map.py`, acceptance | `reference/humanoid-contract.md` |
| 1 | Rig type (Generic, Humanoid, Legacy), the Avatar, Configure, a GLB's Avatar | `reference/unity-import.md` §1 |
| 2 | `<name>@<Clip>.fbx` naming, Copy From Other Avatar, `loopPose`, root motion off | `reference/unity-import.md` §2 |
| 3 | Optimize Game Objects and a prop socket; Skin Weights | `reference/unity-import.md` §3 |
| — | A Blender FBX: scale, a socket bone, a held prop's shape key | `reference/unity-import.md` §4 |
| 4 | Animator: 1D blend tree, upper-body mask on an override layer | `reference/unity-import.md` §5 |
| 5 | PBR maps back onto URP Lit — a Blender or Mixamo FBX never arrives with metallic bound | `reference/textures.md` |
| 6 | Hit box, culling bounds, the Animator to drive, pooling | `reference/gameplay-rig.md` |
| — | Characters sharing a clip pack's skeleton: RemapRoot, StripNonRootPositions, BakeNodeDefaults, `display_scale` on the prefab root, sampling and skinning in batchmode | `reference/shared-skeleton-generic.md` |
| — | It went wrong | `reference/troubleshooting.md` |

## Editor scripts

`resources/Editor/` — copy into an `Editor` folder of the project. Config file, arguments, the
prefab snippet and an API cheat sheet: `reference/editor-scripts.md`. Menu
`Tools/Unity Dev/Rigged Character/<Step>`; each step logs `[RIGGED-CHAR] {json}`.

| File | Step |
|---|---|
| `CharacterImportSettings.cs` | Postprocessor: rig type, Avatar, `@Clip` renames, `loopPose`, map import types, from `character-pipeline.json`. Reimport Character Folder |
| `CharacterHumanoidAvatar.cs` | Build Humanoid Avatar (`"rig": "Humanoid"` only): an explicit HumanDescription from the contract map or a `humanMap` file; gate: valid, human, Chest, ≥ `minFingerBones` fingers |
| `CharacterAvatarLinker.cs` | Link Animation Avatars: Copy From Other Avatar for every `<name>@<Clip>.fbx`; on Humanoid, the same gate first |
| `CharacterAnimatorBuilder.cs` | Build Animator: the controller, with parameter names from the config |
| `MixamoTextures.cs` | Apply Mixamo Textures: the URP Lit material from the source maps, on any FBX route (needs URP) |
| `SharedSkeletonClipImporter.cs` | Postprocessor for the fit route, two folders only: Generic characters and the pack's clips, then root aliases renamed, non-root positions stripped, curveless bones given the file's default. Keep `CharacterImportSettings` off those folders |

Stdlib Python: `scripts/fbx2mixamo.py` and `scripts/glb2mixamo.py` (Mixamo route: cleanup,
axes, a Mixamo-ready OBJ); `scripts/fbx_textures.py` (maps out of any FBX, the original export on
the Mixamo route). `scripts/contract_map.py` (numpy): a skeleton JSON or BVH header mapped onto
the humanoid contract, missing and extra bones, chain, side and axis gates, the retarget map and
Unity's human map (`reference/humanoid-contract.md`).

---

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| The whole character route, stage by stage, and which skill owns each | `game-character-pipeline` |
| Static props — coins, obstacles, environment; triangle and texture budgets | `unity-3d-models` |
| Generating the reference art, T-pose or A-pose | `codex-visual` |
| Turning the image into a mesh | `comfyui-asset-generation` |
| Rigging the character — the default one-command Auto-Rig Pro route | `character-autorig` |
| A hand-built Blender rig (the fallback), skinning, keying an action in Blender | `blender-character-rig` |
| Retargeting a clip library onto a rig; a grip held across clips; the export Unity receives | `blender-retarget` |
| Tracking which FBX, clip and map is current, approved or superseded | `art-asset-registry` |
| What the character costs per frame | `unity-profiling` |
| PhysX triage that is not rig-shaped | `unity-physics-3d` |
| Moving the character in play: the controller, grounding, the Animator bridge | `unity-3d-controller` |
| Pathfinding, and who owns the transform when an agent drives it | `unity-navigation` |
| Animation events, attack windows, IK, override controllers, 2D blend trees, Timeline | `unity-animation` |
| 2D sprite characters | `unity-2d-sprites` · skeletal: `unity-2d-animation` |

## Related skills

- `game-character-pipeline` — the stages from source art to an approved character in Unity.
- `unity-3d-models` — props, GLB import, layers and culling, the budget table the maps follow.
- `unity-3d-controller` — `AnimatorBridge3D`, which writes the four parameters the built
  controller declares.
- `unity-animation` — what the base controller leaves out: thresholds, 2D trees, events, IK.
- `art-asset-registry` — the ledger that records which character files are approved.
- `unity-profiling` — the frame cost of a character, as a number rather than a guess.
- `unity-debug` — verifying any of this in the running game, with screenshots the agent reads.
- `unity-game-ui` — the character-select screen the rig ends up on.
