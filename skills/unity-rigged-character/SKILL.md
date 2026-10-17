---
name: unity-rigged-character
description: >-
  Turn an AI-generated character into a rigged, animated, textured Unity
  character: T-pose reference art → image-to-3D → mesh cleanup → Mixamo auto-rig
  → Humanoid Avatar → Animator (blend tree, masked reaction layer) → PBR
  materials → a gameplay object. Load for a playable character: "make the player
  a real character", "rig this model", "add run/jump animations", Mixamo's
  uploader stalls with no error, the character T-poses in place, every clip is
  named "mixamo.com", a white mannequin or uniform plastic look, a hitbox far
  wider than the character. Characters go FBX because glTFast cannot produce an
  Avatar. Props: unity-3d-models; chibi proportions or custom actions:
  blender-character-rig.
---

# unity-rigged-character — AI character → animated Unity character

A prop can be a GLB. A **character cannot**, and that single fact reshapes the whole pipeline:

> **glTFast cannot produce an Avatar.** Only Unity's native FBX importer has a Rig tab, so there is
> no Humanoid Avatar — and therefore no retargeted animation, no blend tree, no masked reaction
> layer — down the GLB route. Characters go **FBX**, end to end. Mixamo agrees: it accepts
> FBX/OBJ/ZIP and nothing else.

If the asset is scenery, stop here and use `unity-3d-models` instead.

---

## Which route

| The character | Route |
|---|---|
| Standard humanoid proportions, animated with stock clips | Mixamo — this skill, the pipeline below |
| Chibi or short limbs, non-human proportions, extra parts (ears, a tail), or a custom action | skill `blender-character-rig`; come back at stage 4 with its FBX |
| Already rigged in Blender, and must play many stock or purchased clips | skill `blender-retarget`; come back at stage 4 with its FBX |

The two routes want different inputs on purpose: Mixamo takes a T-pose and a mesh with stray
shells removed; the Blender route takes an A-pose and keeps every island and the inner shell.
Choose before commissioning the art.

## The pipeline

Each stage has a reference file. Read the one you are standing in, not all of them.

| # | Stage | Read |
|---|---|---|
| 1 | Why FBX; T-pose art that survives; choosing a service; its parameters | `reference/source-art-and-3d.md` |
| 2 | Decimate, then clean the mesh so auto-rigging succeeds | `reference/mesh-prep.md` |
| 3 | Mixamo upload, joint markers, export settings | `reference/mixamo.md` |
| 4 | Unity importer settings, Avatar linking, Animator structure | `reference/unity-import.md` |
| 5 | Reattach PBR maps — including the roughness≠smoothness trap | `reference/textures.md` |
| 6 | Collide with it, animate it, pool it | `reference/gameplay-rig.md` |
| — | It went wrong | `reference/troubleshooting.md` |

## Supporting files

| File | What it is |
|---|---|
| `reference/character-art-brief.md` | Ready-to-send brief for commissioning the T-pose reference images |
| `reference/editor-templates.md` | Re-runnable Editor scripts: importer automation, Avatar linking, Animator build |
| `scripts/fbx2mixamo.py` | Mesh cleanup so Mixamo's auto-rigger accepts the file |
| `scripts/glb2mixamo.py` | Same, entering from a GLB (position-welded connectivity — see the file) |
| `scripts/fbx_textures.py` | Rebuilds URP maps from the source PBR set |

---

## The five things that go wrong, and where they are answered

- **Mixamo's uploader stalls with no error** → the mesh is dense, multi-shell, or not a single
  watertight body. `reference/mesh-prep.md`
- **Everything is named `mixamo.com`** and clips overwrite each other → one FBX per animation, and
  the importer must rename on import. `reference/unity-import.md`
- **The character T-poses in place** → no Avatar, or the clip's Avatar was not copied from the
  skinned one. `reference/unity-import.md`
- **A white mannequin, or uniform plastic** → maps not reattached, or smoothness was fed a
  roughness map. `reference/textures.md`
- **The hitbox is far wider than the character** → `Renderer.bounds` on a skinned mesh is the
  **bind pose**, and the bind pose is a T-pose. `reference/gameplay-rig.md`

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Static props — coins, obstacles, environment | `unity-3d-models` |
| PhysX triage that is not rig-shaped | `unity-physics-3d` |
| Moving the character in play: the controller, grounding, the Animator bridge | `unity-3d-controller` |
| Pathfinding, and who owns the transform when an agent drives it | `unity-navigation` |
| Generating the reference art | `codex-visual` |
| Rigging, skinning and keying an action in Blender, for a character Mixamo cannot rig | `blender-character-rig` |
| 2D sprite characters | `unity-2d-sprites` · skeletal: `unity-2d-animation` |
| Animation events, attack windows, IK, override controllers, 2D blend trees, Timeline | `unity-animation` |

## Related skills

- `unity-3d-models` — static props, GLB decimation, layer/culling, texture filtering.
- `unity-game-ui` — the character-select screen the rig ends up on.
- `unity-debug` — verifying any of this in the running game, with screenshots the agent reads.
- `codex-visual` — generating the T-pose reference art the pipeline starts from.
- `blender-character-rig` — the other route: bones from measured landmarks, weights by position,
  a keyed action and an FBX proven by re-import, for chibi proportions or a custom action.
