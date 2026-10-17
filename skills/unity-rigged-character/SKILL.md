---
name: unity-rigged-character
description: >-
  The Unity-side contract for a rigged character: FBX import → Avatar (Generic
  for clips retargeted in Blender, Humanoid when the game needs it) → Animator →
  gameplay rig, whichever route made the FBX (Auto-Rig Pro, a Blender rig,
  Mixamo, an auto-rig service). Load for rig type and Configure, Copy From
  Other Avatar, `@Clip` naming and loopPose, a prop socket under Optimize Game
  Objects, a 1D blend tree with an upper-body mask, PBR maps an FBX drops, a
  hitbox. Symptoms: T-poses in place, clips named mixamo.com, a held prop off
  the hand, a white mannequin or plastic look, a hitbox far wider than the body. Props:
  unity-3d-models; rigging: blender-character-rig; clip libraries:
  blender-retarget.
---

# unity-rigged-character — the Unity-side character contract

A skinned FBX reaches Unity; this skill makes it a character the game can drive:
**import → Avatar → Animator → gameplay rig**. Where the FBX came from is upstream, and each
upstream route has its own skill. An asset with no skeleton belongs to `unity-3d-models`.

> **Unity never retargets across skeletons here.** Every clip arrives already on the character's
> skeleton — retargeted in Blender, or by Mixamo on that route — so the rig type follows from what
> the game needs. Generic reproduces the Blender pose; on a test rig, Humanoid moved bones by up
> to 20° and a hand socket by 13–15 cm on the same clip. Choose Humanoid only for a body-part mask, IK or
> other avatars, and measure it first (`reference/unity-import.md` §1).
>
> **A GLB has no Rig tab** (glTFast uses its own importer). It takes Humanoid clips through an
> Avatar built from bone names with `AvatarBuilder.BuildHumanAvatar` (`reference/unity-import.md`
> §1); otherwise the character comes in as FBX.

---

## Which route brought the FBX

| Route | Unity receives | Read first |
|---|---|---|
| **Auto-Rig Pro and a clip library** — standard humanoid, Auto-Rig Pro installed | a deform skeleton with clips baked onto it | skill `blender-retarget` (`blender-retarget` → `reference/unity-handoff.md`), then `reference/unity-import.md` |
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
| 1 | Rig type (Generic, Humanoid, Legacy), the Avatar, Configure, a GLB's Avatar | `reference/unity-import.md` §1 |
| 2 | `<name>@<Clip>.fbx` naming, Copy From Other Avatar, `loopPose`, root motion off | `reference/unity-import.md` §2 |
| 3 | Optimize Game Objects and a prop socket; Skin Weights | `reference/unity-import.md` §3 |
| — | A Blender FBX: scale, a socket bone, a held prop's shape key | `reference/unity-import.md` §4 |
| 4 | Animator: 1D blend tree, upper-body mask on an override layer | `reference/unity-import.md` §5 |
| 5 | PBR maps back onto URP Lit — a Blender or Mixamo FBX never arrives with metallic bound | `reference/textures.md` |
| 6 | Hit box, culling bounds, the Animator to drive, pooling | `reference/gameplay-rig.md` |
| — | It went wrong | `reference/troubleshooting.md` |

## Editor scripts

`resources/Editor/` — copy into an `Editor` folder of the project. Config file, arguments, the
prefab snippet and an API cheat sheet: `reference/editor-scripts.md`. Menu
`Tools/Unity Dev/Rigged Character/<Step>`; each step logs `[RIGGED-CHAR] {json}`.

| File | Step |
|---|---|
| `CharacterImportSettings.cs` | Postprocessor: rig type, Avatar, `@Clip` renames, `loopPose`, map import types, from `character-pipeline.json`. Reimport Character Folder |
| `CharacterAvatarLinker.cs` | Link Animation Avatars: Copy From Other Avatar for every `<name>@<Clip>.fbx` |
| `CharacterAnimatorBuilder.cs` | Build Animator: the controller, with parameter names from the config |
| `MixamoTextures.cs` | Apply Mixamo Textures: the URP Lit material from the source maps, on any FBX route (needs URP) |

Stdlib Python: `scripts/fbx2mixamo.py` and `scripts/glb2mixamo.py` (Mixamo route: cleanup,
axes, a Mixamo-ready OBJ); `scripts/fbx_textures.py` (maps out of any FBX, the original export on
the Mixamo route).

---

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

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| The whole character route, stage by stage, and which skill owns each | `game-character-pipeline` |
| Static props — coins, obstacles, environment; triangle and texture budgets | `unity-3d-models` |
| Generating the reference art, T-pose or A-pose | `codex-visual` |
| Turning the image into a mesh | `comfyui-asset-generation` |
| Rigging, skinning and keying an action in Blender | `blender-character-rig` |
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
