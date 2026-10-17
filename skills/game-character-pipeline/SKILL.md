---
name: game-character-pipeline
description: >-
  The stage order for a rigged game character made from an image, a turnaround
  sheet or a generated model, up to an approved character in Unity. Load before
  starting a character, or when unsure what comes next: the route chosen once
  (body proportions × rigging tool × clip source), the quality target set with
  the user first, the preview track (rig the dense mesh, prototype only) or the
  ship track (budget → game mesh → rig once), then stages S0–S13 with the skill
  that owns each, its entry and exit gates and its artefacts. Routes only: the
  methods live in codex-visual, comfyui-asset-generation, blender-character-rig,
  blender-retarget, unity-3d-models, unity-rigged-character, art-asset-registry.
---

# game-character-pipeline — one character, image to Unity, in order

A rigged character crosses seven skills. Each owns its stages and their method; this skill owns
only the order, the gate between two stages, and what each stage leaves on disk for the next.
It ships no scripts and copies no method: every row points at the file that does the work.

> **The preview-track rig is not the shipping rig.** The preview track rigs the dense generated
> mesh as it is, for a prototype or a preview, and never ships. The ship track picks the budget,
> builds the game mesh at it, and **rigs that mesh once**. Every decimation, retopology and rebake
> of a mesh that will be skinned happens before the rig: done after, it breaks the weights and the
> UVs and invalidates everything taken on the old vertices (weight snapshots, the wrist
> correction, the grip point), and the rig is built again.
>
> **All clip retargeting happens in Blender** (`blender-retarget`). Unity receives clips already
> baked onto the character's own skeleton and never retargets across skeletons.

## G0 — the start gate, once per character

A person decides the three answers below, and they are written down (the brief or the ledger's
`note`) before the first image is generated.

1. **The quality target, first.** Camera distance, the shots that matter, the body parts that
   must hold up under them. Every later stop decision is taken against it, and a request to stop
   refining stands until the user sets a new one — `blender-retarget` →
   `reference/defect-triage-and-stop.md`.
2. **The route: body proportions × rigging tool × clip source.** The route decides the art (pose,
   fingers, one piece or many), so it comes before S1.

   | The body | Rigging tool | Clips | S1 draws |
   |---|---|---|---|
   | Standard adult proportions, Auto-Rig Pro installed in the user's Blender | Auto-Rig Pro (`blender-retarget`) | stock or purchased, retargeted in `blender-retarget` | the realistic humanoid variant: A-pose, straight elbows |
   | A custom body: short limbs, a large head, ears, a tail, mitten hands | positional skinning (`blender-character-rig`) | keyed there, and stock clips retargeted onto that rig in `blender-retarget` | the mascot A-pose, thin parts drawn thick |
   | Standard humanoid, no Auto-Rig Pro — **optional** | Mixamo | Mixamo's own | a T-pose in one piece |
   | Standard humanoid, rigged by an image-to-3D or rigging service | the service | what it exports | what that service documents |

   What each route hands Unity, and the questions that settle it: `unity-rigged-character` →
   `reference/source-art-and-3d.md`; the Auto-Rig Pro test: `blender-retarget` →
   `reference/arp-route.md`; the Mixamo route: `unity-rigged-character` →
   `reference/mixamo-route.md`. The Mixamo and service routes retarget on the service's side,
   so S7–S9 are theirs; Unity still gets clips that already fit.
3. **The track.**

   | Track | Stages | For |
   |---|---|---|
   | **Preview** | S1–S4, S6–S13 (no S0, no S5) | a prototype, a pitch, a preview reel: fastest; the dense mesh is rigged as it is |
   | **Ship** | S0–S13 | the character the game ships: budget, game mesh, one rig |

   A preview that turns into the shipping character goes back to S0 and S5 and is rigged again;
   its rig, weights, wrist correction and grip do not carry over (S5 may borrow its weights as a
   starting point — `blender-character-rig` → `reference/game-mesh.md`).

## The stages

A stage is done when its exit gate passes; where the gate says **person**, someone has looked at
the named image and said yes. Every artefact is recorded in the ledger as it is made (S13).

| # | Stage | Owner | Enters with | Exits when — and leaves | Read |
|---|---|---|---|---|---|
| S0 | Budget — ship track, once per class | `unity-3d-models` | the class's `instances` and `frame_ms` filled; one asset of the class with approved views (S1) | the same asset generated at every preset up to the class's baseline (Small → Showcase), **static** copies in the real scene under the game camera, one side-by-side sheet, one `perf-window/1` window per rung; a **person** picks; the `3D budgets` row written with its `calibrated` date. Leaves `ArtDirection/budgets/character/` | `unity-3d-models` → `reference/budgets.md`; `unity-profiling` → `reference/frame-windows.md` |
| S1 | Four views | `codex-visual` | G0 answered; `ART_DIRECTION.md` locked | the three-quarter image approved by a **person**, then FRONT, LEFT, BACK, RIGHT at one scale, true sides, empty hands; the prop drawn as its own sheet; `audit_3d_source.py --views` passes | `codex-visual` → `reference/image-to-3d-input.md` (§9) |
| S2 | Background removal | `comfyui-asset-generation` | the approved views | per view an RGBA cut-out, a mask preview and a black composite; mask polarity checked on the first view; hair, hands and thin parts survived; upload names unique per asset, view and run | `comfyui-asset-generation` → `reference/image-to-3d.md` (Background removal for four views) |
| S3 | Generate and diagnose | `comfyui-asset-generation` | the black composites; the project graph diffed against the official template before any knob moves | a GLB whose `inspect_glb.py --json-out` record is green and whose 8-view QA sheet (composed only while that record is green) a **person** accepts. A fault is narrowed by stage, one change per run, never an identical resend; "adopt the usable baseline and record its limits" is a valid exit. Ship track: the class's baseline, the showcase S5 compares to | `comfyui-asset-generation` → `reference/image-to-3d-tuning.md`; `codex-visual` → `reference/review-sheets.md` |
| S4 | Normalise | `blender-character-rig` | a green GLB | one object at its height, Z up, soles on Z 0, facing the right axis; the weld check read; the Auto-Rig Pro route imports with `weld_distance: None`. Leaves `ArtDirection/sources/Runner.blend` | `blender-character-rig` → `reference/import-and-survey.md` |
| S5 | Game mesh — ship track | `blender-character-rig` | a `3D budgets` row with a `calibrated` date; the S4 file | route A (regenerate at the row's preset, back through S2–S4's gates) or route B (retopology, UVs, rebake from the showcase) when the joints deform badly; budget, silhouette, UV, bake and joint gates; a **person** approves the side-by-side. Leaves `Runner_game.blend`, its baked maps, `Runner_game_vs_showcase.png`, the inspect JSON | `blender-character-rig` → `reference/game-mesh.md` |
| S6 | Rig | `blender-retarget` (Auto-Rig Pro) or `blender-character-rig` | ship: `Runner_game.blend`; preview: the S4 file | the extreme-pose still looked at by a **person**; right after the bind, the weight sum over deform groups only reads 1 everywhere | `blender-retarget` → `reference/arp-route.md`; `blender-character-rig` → `reference/armature-and-skinning.md`; `blender-retarget` → `reference/weight-repair.md` |
| S7 | Clip sources | `blender-retarget` | a rig | a manifest written before any download; every file present, names unique, every fps the scene's; no-root or standard chosen per clip (gameplay: no-root) | `blender-retarget` → `reference/clip-sources.md` |
| S8 | Retarget — all in Blender | `blender-retarget` | the manifest; one representative clip's skeleton probed | one clip first (a dry run, then the real run), its rest and wrist stills looked at by a **person**; then the batch, whose report counts bake and metadata separately and both equal the clip count | `blender-retarget` → `reference/rest-pose-and-conjugation.md`; `blender-retarget` → `reference/arp-route.md` |
| S9 | Library, prop, weights | `blender-retarget`, `blender-character-rig` | every clip baked | actions found by their custom properties, not their names; the prop's grip read from the prop's own shape; drift over every clip checked in position **and** rotation; a weight move capped at about 25% of the feature it fits; the worst frame looked at | `blender-retarget` → `reference/action-library.md`; `blender-character-rig` → `reference/prop-on-bone.md`; `blender-retarget` → `reference/weight-repair.md` |
| S10 | Stop at the target | `blender-retarget` | a defect someone saw | the layer named (geometry, skinning, animation, material) and fixed in that layer only, same camera and frame before and after; stopped at the G0 target. Geometry wrong at the source goes back to S3, or S5 | `blender-retarget` → `reference/defect-triage-and-stop.md` |
| S11 | Export and round trip | `blender-retarget`, `blender-character-rig` | the saved `.blend` passes `brt_audit` | the deform skeleton only, scale applied, drivers baked; the character, the prop, the idle and one action exported first and read back in Blender (names, parents, scale 1, at most 4 influences, frame ranges) before the rest | `blender-retarget` → `reference/unity-handoff.md`; `blender-character-rig` → `reference/fbx-export.md` |
| S12 | Unity import | `unity-rigged-character` | the round trip green | in a throwaway project first: Generic (Humanoid only for a body-part mask or IK, its deviation checked on the real clip first), `avatar.isValid`, File Scale 1, three bones matching Blender to the millimetre, the socket kept under Optimize Game Objects, the PBR maps rebuilt; a screenshot under the game camera and a frame window; a **person** approves | `unity-rigged-character` → `reference/unity-import.md`; `unity-rigged-character` → `reference/textures.md`; `unity-profiling` → `reference/frame-windows.md` |
| S13 | The ledger, at every gate | `art-asset-registry` | any artefact above | each artefact recorded with its hash, every `.blend` version included; `links` to the job that made it and the art-direction version it was made under; a person's gate as `status ID approved` with the approver and the evidence image; `stale` run after any upstream change | `art-asset-registry` → `reference/workflow.md`; `art-asset-registry` → `reference/ledger-schema.md` |

## When something upstream changes

The ledger's `stale` names the downstream records; this table names the stage to go back to.

| What changed | Back to |
|---|---|
| The class's `instances`, `frame_ms`, the game camera or the target device | S0, then S5 and S6 if the picked rung moves |
| The budget row, after the rig exists | S5, then **S6 again**: nothing taken on the old vertices carries over |
| The views or the design | S1, and every stage after it |
| The generation graph or a preset | S3; a drift from the official template is put back before any tuning |
| One clip's map, rest frame or wrist | S8 for that clip, then S9's checks over the library, then S11 |
| A weight repair or a prop grip | S9, then S11 and S12 |

## Worked example — the Runner with a Mallet, ship track

1. **G0.** The quality target: the runner seen behind the shoulder at the lane camera's usual
   distance, the swing at the gate as the one close shot, hands and the Mallet's head must hold up.
   The Runner is a plush mascot with short limbs, long ears and a tail: the custom-body route,
   positional skinning in `blender-character-rig`, `GateLatchSwing` keyed there and stock jogs
   retargeted onto `RunnerRig` in `blender-retarget`. Ship track. The Mallet is its own asset
   (class `hero-prop`): its own views and mesh, never skinned, attached at S9.
2. **S1 → S0.** The Runner's views are approved first; the `character` ladder runs on them,
   e.g. eight static Runners in the lane under the game camera; a person picks a rung and the
   row gets its date.
3. **S2 → S5.** Clean views, a showcase GLB with a green QA sheet, `Runner.blend` normalised;
   route A regenerates at the picked preset into `Runner_game.blend`; the person approves
   `Runner_game_vs_showcase.png`.
4. **S6 → S10.** `RunnerRig` built once on the game mesh; the jog manifest; one clip, then the
   batch; the library; the Mallet on `Hand.R` with drift checked in position and rotation; a
   dented shoulder fixed as a skinning fault, same camera before and after.
5. **S11 → S12.** The Runner, the Mallet, the idle and `GateLatchSwing` exported first, read back
   in Blender, then imported Generic into a throwaway project, the socket kept, the frame window
   inside the class's `frame_ms`; a person approves the screenshot.
6. **S13 throughout.** Each file recorded as it appears, `Runner_game.blend` with the showcase
   version as its parent, every approval with its evidence image.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| How to perform any stage | the skill and file in that stage's row |
| Props and anything with no skeleton | `unity-3d-models` |
| A 2D character: sprite sheets, frames, Unity sprite animation | `codex-visual` · `unity-2d-sprites` |
| Moving the character in the game: controller, Animator bridge | `unity-3d-controller` |
| States, events, root motion and IK on the clips in Unity | `unity-animation` |
| The game's visual direction and its locked decisions | `unity-game-brief` |

## Related skills

`codex-visual` for the views (S1) · `comfyui-asset-generation` for removal and the mesh (S2–S3) ·
`unity-3d-models` for the budget (S0) · `blender-character-rig` for the normalised file, the game
mesh, a custom rig and the FBX (S4–S6, S9, S11) · `blender-retarget` for Auto-Rig Pro, the clips,
the library, triage and the hand-off (S6–S11) · `unity-rigged-character` for the import (S12) ·
`unity-profiling` for the frame windows (S0, S12) · `art-asset-registry` for the ledger (S13).
