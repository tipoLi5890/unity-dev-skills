---
name: unity-3d-models
description: >-
  Bring a 3D model into a Unity game and prove it fits: route by source (an
  image-to-3D `.glb` from Tripo, Meshy or ComfyUI, an FBX character, a
  Blender-authored rig, a purchased pack), inspect, decimate to the class's
  target, import (glTFast for GLB), wire into a prefab, audit the folder
  against the class's budget row. A budget is picked per class from the same
  asset generated at every preset up to a showcase baseline, seen in the game
  scene; never a fixed cap. Load when the user has a 3D model to add, 3D assets
  make the game lag, a model "shows in Scene, invisible in Game", distant
  textures shimmer, or a class needs a triangle or texture budget. Humanoid
  characters: unity-rigged-character.
---

# unity-3d-models — from a generated mesh to an audited import

Whatever made the model, it ends the same way: a file in `Assets/Models/<Class>/<Name>/`, a
prefab whose `Model` child holds it, an audit that read it against its class's row, and one
record in the project's ledger. What differs is the route there.

Two hard truths this skill exists for:

1. **Unity 6 can't import `.glb` natively** — you need the **glTFast** package. glTFast does
   not go through Unity's Model Importer and has no Rig tab; Editor-side Humanoid goes through
   FBX.
2. **AI image-to-3D output is unusable raw.** Straight off Tripo/Hunyuan/Meshy, a mesh is
   photogrammetry-dense: routinely **~1,000,000+ triangles and 40 MB each**. Pooled ×N, raw
   models will crawl the game. What a class can afford is not a number this skill hands out —
   it is the `target_tris` a person picked for the class, `reference/budgets.md`. **Always inspect first,
   then decimate what is over the target.** The exception is a check, not an assumption: a GLB
   that inspects within its target *and* carries baked normal and occlusion maps is not
   simplified again — the maps are baked from the dense mesh onto this exact surface, and
   simplifying breaks that correspondence. A mesh generated at a face target that is still over
   is regenerated at a lower target, not simplified.

## Route by source

| The model came from | Route | Read |
|---|---|---|
| ComfyUI or an image-to-3D service: a `.glb` prop | Inspect, decimate to the target unless generated at it, stage, glTFast, prefab | `reference/import-and-decimate.md` |
| A generated character for the ship track | The game mesh at the budget **before rigging**, then rig once | `blender-character-rig` → `reference/game-mesh.md`; the whole route: skill `game-character-pipeline` |
| An FBX character for a Humanoid Avatar | The Unity side: importer, Avatar, Animator, gameplay rig | skill `unity-rigged-character` |
| Built in Blender: a rig, a prop on a bone, a custom action | Build and export the FBX there, then audit it here | skill `blender-character-rig`; many stock clips onto one rig: skill `blender-retarget` |
| A purchased or third-party pack | Licence and vendor files first, then the same import | skill `art-asset-registry` |

Every route ends in the same two steps: the audit of the class folder, then the ledger record.

## Classes and budgets

Each model belongs to a class. The defaults are pickup, obstacle, env-prop, hero-prop, character
and rigged-prop; a project declares its own in the `## 3D` chapter of `ART_DIRECTION.md` (skill
`codex-visual`, its art-direction schema), in two tables: `3D asset classes` (the intent, written
by a person) and `3D budgets` (the pick, approved by a person).

| Need | Read |
|---|---|
| Pivot, scale, collision, LODs, names and the prefab per class | `reference/asset-classes.md` |
| The preset ladder, every column of both tables, the default rows, gltf-transform or Blender | `reference/budgets.md` |

The baseline is the showcase — the best the project can make, per class — and the rungs are the
generation presets below it: the same asset generated at each, placed unrigged in the real game
scene with the class's instance count, screenshotted side by side under the game camera and
timed with a frame window. A person picks the rung, biased to quality, and writes the row. Until
a class has a row with a date every tool reports its counts and fails nothing.

## The audit

`Tools/Unity Dev/3D Models/Audit Folder` (`resources/Editor/ModelAudit.cs`, read-only) reads
every model in one class folder — triangles, materials, texture sizes,
`ModelImporter.animationType`, bones, clips and the import settings that matter — and logs one
`[MODEL-AUDIT]` JSON line. It takes the class's row as numbers, 0 for an unchecked cell: over a
ceiling or a `max_*` fails, over `target × 1.25` warns. One call per class folder after every
import and before a build; the call, its arguments and the report are
`reference/model-audit.md`.

## The record

The ledger, `ArtDirection/assets.jsonl`, holds what exists, where it came from, its hashes and
its audit — skill `art-asset-registry`. The audit's rows and `inspect_glb.py`'s output each carry
a `record` the registry ingests unchanged (`art-asset-registry` → `reference/ingest.md`).

## The pipeline for a GLB, in order

| Step | What decides it | Read |
|---|---|---|
| 1 · Inspect | How dense is it really, against the class's target? AI image-to-3D output is routinely 1M+ triangles and 40 MB | `reference/import-and-decimate.md` |
| 2 · Decimate + shrink textures | This is the whole win, when step 1 says it runs. `gltf-transform simplify` before Unity ever sees the file; a mesh to be skinned is brought to budget in Blender before rigging | `reference/import-and-decimate.md` |
| 3 · Stage + import | Unity 6 has **no native GLB importer** — glTFast, and it is a UPM dependency you must add | `reference/import-and-decimate.md` |
| 4 · Wire into a prefab | An Editor script, so it is re-runnable and layer-aware | `reference/import-and-decimate.md` |
| 5 · Audit + record | The class's row; then the ledger | `reference/model-audit.md` |
| 6 · It's invisible in Game view | Almost always layer/culling, not the mesh | `reference/culling-and-layers.md` |
| 7 · It looks cheap at distance | Filtering defaults, not model quality | `reference/texture-filtering.md` |
| 8 · It runs badly | Measure it first (`unity-profiling`), then the order to attack it in | `reference/performance-budget.md` |

## Load what the situation needs

| The situation | Read |
|---|---|
| A model file to bring in; it's huge; decimation; glTFast setup | `reference/import-and-decimate.md` |
| Which class a model is; its pivot, collision, LODs and prefab name | `reference/asset-classes.md` |
| What a class may cost; a triangle or texture budget; the preset ladder; a table in the 3D chapter | `reference/budgets.md` |
| A character's game mesh: regenerate at the preset, or retopology and a rebake, before rigging | `blender-character-rig` → `reference/game-mesh.md` |
| Checking a folder of imported models against its class | `reference/model-audit.md` |
| Generate the mesh on a self-hosted ComfyUI at the class's preset, so no decimation pass is needed | skill `comfyui-asset-generation` |
| "Shows in Scene, invisible in Game"; culling masks; layers | `reference/culling-and-layers.md` |
| Distant surfaces shimmer or look blurry; aniso; MSAA | `reference/texture-filtering.md` |
| The game lags/stutters with 3D assets; draw calls; the order to fix it in | `reference/performance-budget.md` |
| Numbers for the lag before touching a mesh: triangle and draw-call counters, a before/after window | skill `unity-profiling` |
| A class's frame time on the phone itself | skill `unity-device-testing` |
| Textures and meshes are bloating memory or the build | skill `unity-android-release`, its size-and-stripping reference |
| A **rigged, animated character** rather than a prop; Humanoid or Generic rig import | skill `unity-rigged-character`, or skill `blender-character-rig` for chibi proportions, extra parts or a custom action |
| Clips retargeted onto a character already rigged in Blender | skill `blender-retarget` |
| Recording a model, its source and licence; a purchased pack's vendor files | skill `art-asset-registry` |
| The `## 3D` chapter of the art bible | skill `codex-visual` |
| 2D sprite sheets, slicing, pivots, 9-slice borders | skill `unity-2d-sprites` |
| Verifying any of it visually | skill `unity-debug` |

## Scope — what this skill does NOT do

Props are imported here and every class is audited here, characters included. A character's
Avatar, Animator and gameplay rig are `unity-rigged-character` — glTFast does not go through
Unity's Model Importer and has no Rig tab; Editor-side Humanoid goes through FBX — or
`blender-character-rig` when the rig and the action are authored in Blender. Driving the Editor
is `unity-cli` and `unity-debug`; build-wide stripping is `unity-android-release` and
`unity-web-release`. Modular-kit conventions — the grid, pivots, snapping — are `unity-3d-level`;
LOD groups and scene-level draw cost are `unity-scene-optimisation`.

## Two rules that decide everything else

> **Decimate before Unity sees the file.** AI image-to-3D output is photogrammetry-dense.
> Importing first and optimising later means every downstream asset — prefabs, colliders,
> lightmap UVs — is rebuilt from the wrong mesh. Inspect decides whether it runs (step 1). A mesh
> that will be skinned is decimated **before it is rigged**: decimating a rigged mesh breaks its
> weights and UVs.

> **Read/Write Enabled off on every mesh and texture nothing reads back.** It keeps a second,
> CPU-side copy resident for the asset's lifetime. Combine with **Strip Unused Mesh
> Components** — details in `unity-android-release`, its size-and-stripping reference.
>
> `isReadable` defaults to **`false`** on both `TextureImporter` and `ModelImporter`.
> So this is a *keep it off* rule, not a *turn it off* one — the cost appears when
> someone enables it for one script and never reverts it. Audit rather than assume.

**Anisotropic filtering defaults to `1`** — an imported texture reads `anisoLevel = 1`,
`mipmapEnabled = true`, `filterMode = Bilinear`. That combination is what makes a ground plane
shimmer into mush at grazing angles, and it is the default on every texture in the project.
→ `reference/texture-filtering.md`

For textures loaded at runtime through Addressables or AssetBundles — and only those — **KTX2 /
Basis Universal** ships one file that transcodes to the device's best GPU format (ASTC on
mobile, BC7 on desktop, ETC2 on older Android). Encode offline with `toktx`: `--genmipmap`,
`--assign_oetf linear` for normal/mask/data maps, and `--lower_left_maps_to_s0t0` to match
Unity's UV origin. ETC1S for albedo (small), UASTC for normals and UI (quality). Confirm the
project can transcode KTX2 at runtime — Unity reads it through the KTX for Unity package
(`com.unity.cloud.ktx`) — before encoding a whole texture set. Textures that
go **into the player build do not need this** — Unity already picks a format at build time.
