---
name: game-character-pipeline
description: >-
  START HERE for a rigged game character made from an image or turnaround: the
  stage order from views to an approved character in Unity, each stage's owner
  and its gate.
---

# game-character-pipeline — one character, image to Unity, in order

A rigged character crosses nine skills. Each owns its stages and their method; this skill owns
only the order, the gate between two stages, and what each stage leaves on disk for the next.
It ships no scripts and copies no method: every row points at the file that does the work.

## Start here — the request, and where it is answered

| The request | Go to |
|---|---|
| Starting a character from an image, a turnaround sheet or a generated model; unsure what comes next | [G0](#g0--the-start-gate-once-per-character), then [the stages](#the-stages) in order |
| The quality target (camera distance, the shots, the parts that must hold up) | G0 step 1; `reference/start-gate.md` |
| Which route: rig locally onto the humanoid contract, or fit the mesh to one clip pack's skeleton | G0 step 2; `reference/routes.md` |
| Preview, ship or upgrade track (a cloud mesh after the demo, chosen by a person) | G0 step 3 |
| Which skill owns a stage, what it enters with and leaves on disk, its gate | [the stages](#the-stages), S0–S13 |
| Something upstream changed; a worked example (the Runner with a Mallet) | `reference/upstream-changes.md` |
| A 2D character, a prop, moving the character in the game | [Scope](#scope--what-this-skill-does-not-do) |

> **The preview-track rig is not the shipping rig.** The preview track rigs the dense generated
> mesh as it is and never ships. The ship track picks the budget, builds the game mesh at it, and
> **rigs that mesh once**. Every decimation, retopology and rebake of a mesh that will be skinned
> happens before the rig: done after, it breaks the weights and the UVs and invalidates everything
> taken on the old vertices (weight snapshots, the wrist correction, the grip point).
>
> **Rigging is local; the cloud only remakes a mesh.** S3 generates locally, S6 rigs locally onto
> the humanoid contract, and no cloud rigging service is used. A paid cloud mesh enters only on the
> upgrade track, which a person chooses after the demo; the quality target never selects it.
>
> **Unity never retargets across skeletons.** Clips reach it already playable on the character's
> skeleton: made on the contract (`humanoid-motion`), retarget-baked in Blender
> (`blender-retarget`), or played unchanged on a pack skeleton fitted to the mesh (the fit route).

## G0 — the start gate, once per character

A person decides three answers before the first image is generated, and they are written down
(the brief or the ledger's `note`). In full: `reference/start-gate.md`.

1. **The quality target, first.** Camera distance, the shots that matter, the body parts that
   must hold up under them; every stop decision is taken against it (`blender-retarget` →
   `reference/defect-triage-and-stop.md`). It sets how far S3 and S10 go, not where the mesh is made.
2. **The route** — it decides the art, so it comes before S1 (`reference/routes.md`):

   | The body | Rig (S6, local) | Clips | S1 draws |
   |---|---|---|---|
   | Standard adult — **default** | `character-autorig` (Auto-Rig Pro; hand-built fallback) onto the contract | `humanoid-motion` two-camera; packs retargeted | A-pose, straight elbows, legs apart |
   | Custom: short limbs, big head, ears, tail, mittens | `character-autorig` hand-built, else `blender-character-rig` positional skin | `humanoid-motion` two-camera; keyed; retargeted | the mascot A-pose, thin parts thick |
   | Adult, every motion from **one** pack | the fit route (`blender-character-rig` → `reference/fit-to-clip-skeleton.md`) | the pack's files unchanged | A-pose, straight elbows |

3. **The track.**

   | Track | Stages | For |
   |---|---|---|
   | **Preview** | S1–S4, S6–S13 (no S0, S5) | a prototype, pitch or reel; the dense mesh rigged as it is |
   | **Ship** | S0–S13 | the shipping character: budget, game mesh, one rig |
   | **Upgrade** | S3 in the cloud (mesh only) → S4 → S5 (ship) → S6 → S9 → S11–S13 | a demo-approved character a **person** picks for a paid mesh; rig local, same contract and gates; the demo's clips carry over |

   A preview that becomes the shipping character goes back to S0 and S5 and is rigged again.

## The stages

A stage is done when its exit gate passes; where the gate says **person**, someone has looked at
the named image and said yes. Every artefact is recorded in the ledger as it is made (S13).

| # | Stage | Owner | Enters with | Exits when — and leaves | Read |
|---|---|---|---|---|---|
| S0 | Budget — ship track, once per class | `unity-3d-models` | the class's `instances` and `frame_ms`; one asset with approved views (S1) | the asset at every preset up to the class's baseline (Small → Showcase), **static** copies under the game camera, one sheet, one `perf-window/1` per rung; a **person** picks; the `3D budgets` row with its `calibrated` date | `unity-3d-models` → `reference/budgets.md`; `unity-profiling` → `reference/frame-windows.md` |
| S1 | Four views | `codex-visual` | G0 answered; `ART_DIRECTION.md` locked | the three-quarter image approved by a **person**, then FRONT, LEFT, BACK, RIGHT at one scale, true sides, empty hands, limbs clear of the body; the prop its own sheet; `audit_3d_source.py --views` passes | `codex-visual` → `reference/image-to-3d-input.md` (§9) |
| S2 | Background removal | `comfyui-asset-generation` | the approved views | per view an RGBA cut-out, a mask preview, a black composite; polarity checked on the first view; thin parts survived; upload names unique | `comfyui-asset-generation` → `reference/image-to-3d.md` (Background removal for four views) |
| S3 | Generate, locally | `comfyui-asset-generation` | the black composites; the graph diffed against the official template | the local Pixal3D multi-view GLB, `inspect_glb.py --json-out` green, its 8-view sheet accepted by a **person**. One change per run, never an identical resend; "adopt the usable baseline and record its limits" is a valid exit. Upgrade track: a paid cloud mesh from the same views, recorded with its licence | `comfyui-asset-generation` → `reference/image-to-3d-tuning.md`; `codex-visual` → `reference/review-sheets.md` |
| S4 | Normalise | `blender-character-rig` | a green GLB | one object at its height, Z up, facing −Y, soles on Z 0, scale applied; the weld check read; an Auto-Rig Pro rig imports with `weld_distance: None`. Leaves `ArtDirection/sources/Runner.blend` | `blender-character-rig` → `reference/import-and-survey.md` |
| S5 | Game mesh — ship track | `blender-character-rig` | a `calibrated` budget row; the S4 file | regenerated at the row's preset (back through S2–S4's gates), or retopology, UVs and a rebake from the showcase; budget, silhouette, UV, bake and joint gates; a **person** approves the side-by-side. Leaves `Runner_game.blend` and its maps | `blender-character-rig` → `reference/game-mesh.md` |
| S6 | Rig, locally | `character-autorig`; fallback `blender-character-rig` | the mesh to rig (ship: `Runner_game.blend`); **`mesh_check.py` exit 0** — fused limbs or a same-facing double layer go back to S1 or S3, never into a rig; a back-to-back inner shell (Pixal3D's fixed artefact) is reported and kept | markers' two pictures accepted by a **person**; `brt_arp` `pipeline` gates; `contract_map.py --require contract` exit 0; `deform_gate.py` exit 0 and its renders looked at by a **person**; weight sum 1 | `character-autorig` → `reference/arp-pipeline.md`; `character-autorig` → `reference/gates.md`; `character-autorig` → `reference/hand-built-route.md` |
| S7 | Clip sources | `humanoid-motion`; `blender-retarget` | a rig | per move a source: two-camera video solved onto the rig, or a pack (a manifest before any download, names unique, fps the scene's); each source recorded with its `licence`; loop speeds and contact points measured before gameplay numbers freeze (`unity-gameplay` → `reference/genre-timing-sports.md` §0) | `humanoid-motion` → `reference/pipeline.md`; `humanoid-motion` → `reference/two-camera.md`; `blender-retarget` → `reference/clip-sources.md` |
| S8 | Retarget and clean — in Blender | `humanoid-motion`; `blender-retarget` | the sources; one clip's skeleton probed | packs: rotations by conjugation and translation scaled by the hip-height ratio (`retarget.translation_kept`); a two-camera solve is on the rig already. Then contact bake, loop cut, `motion_metrics.py` exit 0; one clip first (a dry run, then the real run), its rest and wrist stills seen by a **person**, then the batch, whose report counts bake and metadata separately | `humanoid-motion` → `reference/pipeline.md`; `blender-retarget` → `reference/rest-pose-and-conjugation.md` |
| S9 | Library, prop, weights | `blender-retarget`, `blender-character-rig` | every clip baked | actions found by custom properties; the grip read from the prop's shape; drift in position **and** rotation; a weight move capped at about 25% of its feature; the worst frame looked at | `blender-retarget` → `reference/action-library.md`; `blender-character-rig` → `reference/prop-on-bone.md`; `blender-retarget` → `reference/weight-repair.md` |
| S10 | Stop at the target | `blender-retarget` | a defect someone saw | the layer named (geometry, skinning, animation, material), fixed there only, same camera and frame; stopped at the G0 target. Geometry wrong at the source goes back to S3, or S5 | `blender-retarget` → `reference/defect-triage-and-stop.md` |
| S11 | Export and round trip | `blender-retarget`, `blender-character-rig` | the `.blend` passes `brt_audit` | the deform skeleton only, scale applied; the character, prop, idle and one action exported and read back (names, parents, scale 1, ≤ 4 influences, ranges) before the rest | `blender-retarget` → `reference/unity-handoff.md`; `blender-character-rig` → `reference/fbx-export.md` |
| S12 | Unity import | `unity-rigged-character` | the round trip green | in a throwaway project: Generic; Humanoid only for a mask or IK, built from an explicit map with Chest and fingers; `avatar.isValid`, File Scale 1, three bones matching Blender to the mm, the socket kept, PBR maps rebuilt; a screenshot under the game camera and a frame window; a **person** approves | `unity-rigged-character` → `reference/unity-import.md`; `unity-rigged-character` → `reference/humanoid-contract.md`; `unity-rigged-character` → `reference/textures.md`; `unity-profiling` → `reference/frame-windows.md` |
| S13 | The ledger, at every gate | `art-asset-registry` | any artefact | each artefact with its hash and `licence` (source, territory), `links` to its job and the art-direction version; a person's gate as `status ID approved`; `check` refuses an excluded territory; `stale` after any upstream change | `art-asset-registry` → `reference/workflow.md`; `art-asset-registry` → `reference/ledger-schema.md`; `art-asset-registry` → `reference/licences.md` |

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| How to perform any stage | the skill and file in that stage's row (S0–S13 name the owner of each) |
| Props and anything with no skeleton | `unity-3d-models` |
| A 2D character: sprite sheets, frames, Unity sprite animation | `codex-visual` · `sprite-from-video` · `unity-2d-sprites` |
| Moving the character in the game: controller, Animator bridge | `unity-3d-controller` |
| States, events, root motion and IK on the clips in Unity | `unity-animation` |
| The game's visual direction and its locked decisions | `unity-game-brief` |
