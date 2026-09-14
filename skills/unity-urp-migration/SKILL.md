---
name: unity-urp-migration
description: >-
  Move a Built-in Render Pipeline project to URP in five gated phases, and
  diagnose one that was half-moved. Load for: "migrate / upgrade / convert this
  project to URP", "everything went pink or magenta after switching to URP",
  "the Render Pipeline Converter ran but it still looks Built-in", "convert PPv2
  or PostProcessVolume to a URP Volume", "my Standard materials became
  2D/Mesh2D-Lit-Default", "lightmaps look blown out after URP", "GrabPass /
  OnRenderImage / surface shader no longer works in URP", "which quality
  settings moved into the URP asset". Post-processing that will not appear on a
  project already on URP, Render Graph review and HDRP stay out.
---

# unity-urp-migration — five phases, each one read back before the next

> **Whether a migration is finished is a property of the saved project, not of the converter
> log.** Four separate traps let this migration report success while the project still renders
> the old way, and each of them is invisible to every check except re-reading what was written.
> And nothing mutates — no package, no assignment, no material, no scene — until a rollback
> point has been confirmed out loud.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| "Migrate / upgrade this project to URP" | §1, starting at Phase 0 |
| Everything is magenta | `reference/material-conversion.md` — incomplete material conversion |
| Not magenta, but white or untextured | `reference/material-conversion.md` — the snapshot and restore steps |
| A 3D material landed on `Universal Render Pipeline/2D/Mesh2D-Lit-Default` | `reference/material-conversion.md` §trap |
| "It says it migrated" and it still looks Built-in | §3 trap 1 — check Graphics settings **and every quality tier**; resolver in `unity-render-urp` → `reference/resolve-active-pipeline.md` |
| Post-processing vanished, or the project used the old stack | `reference/ppv2-to-volumes.md` |
| Scene is blown out or far too dark | `reference/ppv2-to-volumes.md` (two stacks running) before `reference/lighting-and-probes.md` |
| Lightmaps or probes look wrong | `reference/lighting-and-probes.md` |
| `GrabPass`, `OnRenderImage`, `#pragma surface`, `SetReplacementShader` | `reference/shader-migration.md` |
| "Where did shadow distance / MSAA / HDR go?" | `reference/migration-phases.md` §quality map |
| The pass stopped right after the package installed | §1 — that is a phase boundary; resume, do not restart |
| A 2D project | §2, path B — a different renderer and a different upgrader set |
| `unity status` shows no row and no error | §4, the floor trap |
| Before-and-after pictures wanted | `resources/SceneCapture.cs` |

## 1. The five phases

| Phase | Work | Gate | Scripts |
|---|---|---|---|
| **0 · Inspect** | Pipeline at Graphics settings and at every tier; packages; risk grep; old post-processing found by component type; materials bucketed; lighting state | A report **and** a confirmed rollback point | `resources/MigrationAudit.cs` |
| **1 · Pipeline + materials** | Install or reuse URP; asset and renderer; assign at Graphics and every tier; snapshot → convert → restore → verify | `GetRenderPipelineAssetAt(i)` right on every tier; every converted material's `shader.name` matches its mapped target; every material that had `_MainTex` has a non-null `_BaseMap` | `resources/PipelineAssignment.cs` · `resources/MaterialConverter.cs` |
| **2 · Post-processing** | Persisted `VolumeProfile`; scene `Volume.sharedProfile`; camera post-processing on; legacy components disabled | After a reload, components are non-null; the **saved** scene references the profile; legacy components re-query as disabled with the scene saved clean | `resources/VolumeMigration.cs` |
| **3 · Lighting + probes** | Identify a stale bake; scene references a URP `.lighting`; rebake or declare partial; probe settings on the asset | Saved scene points at the `.lighting`; bake evidence or an explicit `partial`; `m_ReflectionProbeBlending: 1` in the asset text | `resources/LightingMigration.cs` |
| **4 · Validate + report** | Save, reload, re-query; capture; console; wording | Every gate above passes | `resources/MigrationGate.cs` · `resources/SceneCapture.cs` |

Package installs, domain reloads and bakes are **phase boundaries**. When one interrupts the
pass, resume from the first gate that did not pass — never from the beginning, because
reinstalling a package and reconverting converted materials is how a migration loses an
afternoon. The rollback confirmation covers the whole trip; ask again only when a genuinely new
expensive or destructive step arrives.

Full phase detail, the converter table, the resume checklist and the quality-settings map:
`reference/migration-phases.md`.

## 2. Before the first mutation

**Confirm the rollback point in words** — a branch, a copy, a tag, or "this is a throwaway
clone". Mutation starts at the package install, because a project with URP assigned and
materials unconverted renders magenta, and that is not a state to leave someone in while asking
about backups.

**Engine upgrade first, pipeline second** when the project is also moving Unity versions.
Two migrations at once means every later symptom has two candidate causes.

**Detect in two places, always.** The project default is `GraphicsSettings.defaultRenderPipeline`;
the tiers are a loop over `QualitySettings.names` reading `GetRenderPipelineAssetAt(i)`. A
project can be switched at one and not the other, and the one that is wrong is the one nobody
looked at.

There is **no `SetRenderPipelineAssetAt`**. Writing a tier means `SetQualityLevel(i)`, then
`QualitySettings.renderPipeline = asset`, then restoring the original level. An invented setter
assigns nothing and reports nothing.

Detecting HDRP means stopping: explain that this is a different pipeline with different Volume
components and different renderer plumbing, and that nothing here transfers.

Then pick the path: **A** standard 3D · **B** 2D, which needs the 2D renderer and the 2D
upgrader container · **C** selected materials only, on a project already on URP · **D**
troubleshooting an attempt that already happened · **E** plan only, changing nothing.

## 3. Four traps that make it look done

**1 · Assigned at Graphics settings, not at the tiers.** A tier reading `{fileID: 0}` inherits
the project default, which is legal — but say it is a choice rather than reporting "all tiers
migrated". A tier pointing at a *different* asset is worse: that is a second pipeline the
project ships with, and it renders on whichever platforms select that tier.

**2 · Converted, not magenta, and wrong.** Both the 2D and the 3D upgrader providers claim
`Standard` at equal priority, so a plain `Standard` material can land on a 2D shader in a 3D
project with nothing logged. Separately, changing a shader without a snapshot leaves `_BaseMap`
null and `_BaseColor` white while every property reads back cleanly. Read `shader.name` and
`_BaseMap` back after every conversion, whatever route ran.

**3 · The empty profile asset.** `VolumeProfile.Add<T>(true)` creates the override object but
does not make it a sub-asset. Without `AssetDatabase.AddObjectToAsset` the profile reloads as
`components: []` or `{fileID: 0}` entries. And `SaveAssets()` writes the profile but **not** the
scene that references it — that needs `MarkSceneDirty` plus `SaveScene`.

**4 · Lighting that is still Built-in.** Old lightmaps and the lighting data asset are live
data, not history; they keep lighting the scene until something clears them.
`Lightmapping.Clear()` is not evidence until the scene is saved and re-read. "Probes refreshed"
needs a bake result, not an intention.

## 4. Execution path

Getting to a connected Editor, the command catalog, and telling an absent Editor from one in
Safe Mode is `unity-cli`. Every script here goes under `Assets/Editor/`, compiles, and is then
called with one line:

```bash
unity command eval --code 'return UnityDev.UrpMigration.MigrationAudit.Run();'
```

`unity command` defaults to a 30-second timeout. A package install or a bake outrunning it is a
**phase boundary**, not a reason to raise the timeout. Each script returns a single `[URP-MIG]`
line assembled from re-read saved state, and logs the same line so it also lands in the console.

> **Floor trap.** The `com.unity.pipeline` package's manifest allows an Editor line older than
> the one it compiles on: it uses build-callback types that the earlier line never shipped, so
> the resolve succeeds and the compilation right after it does not. The symptom is misleading — `unity status`
> shows no row **and no error**, so it reads as a CLI problem. The check is the Editor log:
>
> ```bash
> grep -c 'error CS0246' <Editor.log>
> ```
>
> with hits naming `IPreprocessBuildWithContext` or `BuildCallbackContext`. That is an Editor
> too old for the package, not a broken CLI. Confirm the floor on your version by reading the
> package changelog. **This bites here more than anywhere else**: a project still on the
> built-in pipeline is often on an older Editor by the same history.

## 5. Report wording

- **`Complete`** only when every Phase 4 gate is true. Not one of them, not most of them.
- **`Partial migration`** when the pipeline and materials landed but post-processing
  persistence, legacy disablement, the bake, the probes or a saved-state check is still open.
- **`Manual follow-up`** names the items precisely: the old stack's screen-space reflections, a
  specific custom shader, a `GrabPass`, a replacement shader, a package-owned shader.

> **A report whose next steps include "rebake lighting" or "refresh probes" is partial by
> definition.** Those are the phase, not a suggestion after it. Do not pair them with
> "complete", and do not open the answer with "successfully migrated" while any gate is false.

## Load what the situation needs

| The situation | Read |
|---|---|
| Running an actual migration, or resuming one | `reference/migration-phases.md` |
| Materials: magenta, white, 2D-shader hijack, particles, foliage | `reference/material-conversion.md` |
| The old post-processing stack, empty profiles, double post-processing | `reference/ppv2-to-volumes.md` |
| Lightmaps, a stale bake, reflection probes, exposure balance | `reference/lighting-and-probes.md` |
| Custom shaders, `GrabPass`, `OnRenderImage`, replacement shaders | `reference/shader-migration.md` |
| Volume API, parameter ranges, `overrideState`, the five-switch pre-flight | `unity-render-urp` |
| Which pipeline is actually in force, including per-tier and per-platform | `unity-render-urp` → `reference/resolve-active-pipeline.md` |
| Porting a full-screen effect onto a project already on Render Graph | `unity-render-urp` → `reference/render-graph-review.md` |
| `sharedProfile` versus `profile`, and undo from `eval` | `unity-render-urp` → `reference/volume-templates.md` |
| Reaching the Editor at all; installing; the command catalog | `unity-cli` |
| Reading the command envelope; a confirm gate; screenshots | `unity-debug` → `reference/editor-control.md` |
| "It got slower after the migration" — numbers across the change | `unity-profiling` |
| A 2D project's camera, upscaling and pipeline detection | `unity-2d-pixel-perfect` |

## Discipline

- **Read it back. Never trust a log.** Every claim in a report comes from a file or an object
  reloaded after saving, not from the call that wrote it.
- **`SaveAssets` is not `SaveScene`.** Assets and scenes persist by different calls, and the
  half that was skipped reads correctly until the Editor closes.
- **Snapshot before changing a shader.** Afterwards the source values are gone, and a repair
  written from post-conversion properties preserves the broken state.
- **Read `shader.name` after every conversion**, converter or manual. It is the only check that
  catches a material that converted onto the wrong target.
- **Never claim a probe refresh from intent.** Changed probe files or nothing.
- **Package installs and bakes are boundaries.** Resume from the first failed gate.
- **Never edit materials or shaders under `Packages/` or `Library/PackageCache/`.** Local copy,
  or manual follow-up.
- **Grade custom shaders before porting any of them**, and never bulk-replace shader source.
- **Match the wording to the gate.** "Complete" is a claim about saved state, not a summary of
  effort.
- **Write captures to a temp path, not into `Assets/`** — a PNG in the project becomes an
  imported asset somebody has to clean up.
- **Never force an effect material to Lit.** Particle, fog, smoke, additive and decal materials
  keep their blend mode or the effect is gone while every check says it converted.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Post-processing that will not appear on a project already on URP | `unity-render-urp` |
| Volume parameter defaults, types and ranges; grade presets | `unity-render-urp` |
| Reviewing a Render Graph renderer feature | `unity-render-urp` |
| Installing the CLI, editors, licences; connecting to an Editor | `unity-cli` |
| Verifying a change on screen; reading logs; driving the Editor | `unity-debug` |
| What the migration cost in frame time | `unity-profiling` |
| 2D camera setup and upscaling after the move | `unity-2d-pixel-perfect` |
| Sprite import, atlases and tilemaps in their own right | `unity-2d-sprites` · `unity-sprite-atlas` · `unity-tilemap` |

**Shading maths stays out.** This skill decides *how a shader should be ported* and what
evidence proves it landed; it does not decide what the shader should compute. **HDRP stays
out** in both directions — neither migrating to it nor away from it.
