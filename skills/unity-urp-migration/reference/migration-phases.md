# The five phases, and what each one has to prove

> Part of the `unity-urp-migration` skill. Each phase ends at a gate made of re-read saved
> state. A phase that cannot pass its gate is reported partial and resumed later, never repeated
> from the start — the expensive steps in it are exactly the ones a restart pays for twice.

## Classifying the request before touching anything

| The request | Default reading |
|---|---|
| "upgrade / convert / move this project to URP" | Full project, phased, 3D path |
| "move this 2D project to URP" | 2D path — another renderer, another upgrader set |
| "convert these materials" | Targeted conversion, project already on URP |
| "everything went pink" | Troubleshooting an attempt that already happened |
| "lighting looks wrong since URP" | Parity: post-processing first, then the bake |
| "do not change anything yet" | Audit and plan only: Phase 0, and stop |

A short request is not permission to skip discovery. The project, not the person asking, is
where the old post-processing stack and the second quality tier are found.

## The rollback gate

**Mutation** means: installing the package, assigning a pipeline asset at Graphics settings or a
tier, running a converter, editing a material or a scene. None of it happens before a rollback
point is confirmed out loud, and the gate sits **before** the install — a project with URP
assigned and materials unconverted renders magenta, which is not a state to park someone in
while waiting for an answer about backups.

Asked once, it covers the whole pass; ask again only when a new expensive or destructive step
arrives — a long bake, deleting legacy assets, a custom shader rewrite.

## Phase 0 — inventory

`resources/MigrationAudit.cs` answers, read-only:

- **Pipeline, in two places.** The project default and every quality tier. One is not the other.
- **Packages.** Whether URP is already present; whether the old post-processing package is.
- **Materials, in buckets**: Standard and Legacy; particle and effect; foliage (`Nature/`,
  SpeedTree names, anything carrying `_Cutoff`); custom shaders authored in the project;
  package-owned materials under `Packages/` or `Library/PackageCache/`.
- **Scenes, URP assets, profiles, lighting settings, lighting data, probes.**
- **Risk markers**, as a text scan over `.cs`, `.shader`, `.cginc` and `.hlsl`:

  `PostProcessLayer` · `OnRenderImage(` · `SetReplacementShader` · `RenderWithShader` ·
  `#pragma surface` · `GrabPass` · `CGPROGRAM` · `CommandBuffer` · `Nature/` · `SpeedTree` ·
  `_Cutoff`

  Each hit is a file to read, not a verdict — six on `CGPROGRAM` and nothing else is a small
  job; four on `#pragma surface` is a shader work package.

> **If the old post-processing package is installed but the grep finds nothing, the grep is
> wrong, not the project.** Those components live in scene YAML, which a text search does not
> reliably reach. Enumerate the open scene by `GetType().FullName` instead — which the audit
> script does, and which is why it runs with the representative scene open.

Gate: the findings are reported **and** the rollback point is confirmed.

## Phase 1 — pipeline and materials

Install, if the package is not already there:

```bash
unity command package_add -- --identifier com.unity.render-pipelines.universal --confirm true
```

Without `--confirm true` the command returns outer `success: true` and inner
`status: "rejected"` — a gate, not an error, invisible to anything reading the exit code
(`unity-debug` → `reference/editor-control.md`). **Never spin-wait on the install inside an
`eval` call**: request it, let the turn end, and verify next turn by resolving a URP type or
reading `Packages/manifest.json`.

Then the asset and its renderer. Prefer the **Rendering Settings** converter, which builds both
from the project's existing settings. Where a script has to do it, create a
`UniversalRendererData` and hand it to `UniversalRenderPipelineAsset.Create(renderer)` — confirm
both on your version — and check `postProcessData` is not null, because a null one means the
post-processing pass does not exist and Phase 2 looks broken for a Phase 1 reason.

Assign with `resources/PipelineAssignment.cs`: Graphics settings, then every tier. A console
message reading *"Default Renderer is missing"* afterwards is not a reason to stop at "setup
complete" — re-query the renderer list and repair it.

### What each converter does

| Converter | Does | Does not |
|---|---|---|
| Rendering Settings | Creates URP assets, maps old quality settings across | Touch any material |
| Material Upgrade | Converts supported built-in materials | Solve custom shaders — it never reads them |
| Animation Clip | Fixes clips animating material or post-fx properties | Help before materials convert |
| Read-only Material | The engine's own built-in materials; slow, it indexes | Anything outside that set |
| Post-processing v2 | Converts old volumes, profiles, camera data | Exist without that package |

The 2D container offers **Material and Material Reference Upgrade** instead.

Batch entry point:
`UnityEditor.Rendering.Universal.Converters.RunInBatchMode(ConverterContainerId, List<ConverterId>, ConverterFilter)`
— confirm the overload and the `ConverterId` members on your version; `ConverterId.PPv2` only
compiles where the old post-processing package is installed.

Materials go through `resources/MaterialConverter.cs` in four steps — snapshot, convert, restore,
verify — detailed in `reference/material-conversion.md`.

Gate: every tier re-queried returns the intended asset; every converted material's `shader.name`
matches its target; every material whose snapshot had an albedo texture has a non-null `_BaseMap`.

## Resuming, rather than restarting

A pass interrupted by an install, a reload or a bake resumes at the first unproven item:

1. Is the package in `manifest.json`? If yes, do not install it again.
2. Do a URP asset and a valid renderer exist?
3. Do Graphics settings **and every tier** name the intended asset?
4. Do the materials read back on URP shaders, particles included?
5. Does the profile reload with live components, and does a saved scene reference it?
6. Does the saved scene point at a URP lighting settings asset, and is the old bake still live?

The first "no" is where work resumes. Name that phase rather than re-describing the migration.

## Where the old quality settings went

Only the rows a migration actually trips over:

| Was | Now |
|---|---|
| Pipeline asset per quality level | Project Settings → Quality → Render Pipeline Asset |
| Project-wide pipeline asset | Project Settings → Graphics → Render Pipeline Asset |
| MSAA | URP asset → Quality → Anti-aliasing (MSAA) |
| Per-camera anti-aliasing | Camera → Rendering → Anti-aliasing |
| Shadow distance | URP asset → Shadows → Max Distance |
| Shadow cascades | URP asset → Shadows → Cascade Count |
| Main and additional light shadows | URP asset → Lighting → Main Light / Additional Lights |
| HDR · depth texture · opaque texture | URP asset → Quality, and → Rendering |
| Resolution scaling | Quality settings **and** URP asset → Quality → Render Scale |
| Real-time reflection probes | Project Settings → Quality → Rendering |

One list became two, and a tier with no asset of its own falls back to Graphics settings — legal,
but state it as a choice rather than report "all tiers migrated".

## Phase 4 — capture and report

Capture the representative scene with `resources/SceneCapture.cs`, before and after, under
distinct filenames — one that overwrites the other is a comparison with itself. Read the PNG;
do not ask anyone what it looks like. Then six lines, nothing narrated around them:

```
migration: <Complete | Partial migration | Manual follow-up>
pipeline:  graphics=<asset>  tiers=<n/m explicit>
materials: converted=<n/total>  on2D=<n>  nullBaseMap=<n>
post-fx:   profile=<path>  overrides=<list>  legacyEnabled=<n>
lighting:  settings=<guid|none>  bake=<idle|running|done>  probes=<n|unproven>
manual:    <named items, or none>
```

## Worked example — the courier run

Two tiers, `Runner-Low` and `Runner-High`; three 1.3-unit lanes, a gate at the end of the run,
one sentry, hazards and pickups; played on a tablet at 2–3 m with a three-button gamepad. One
line per phase:

- **0** — `pipeline=BuiltIn graphics=none tiers=Runner-Low=inherits|Runner-High=inherits
  materials=61 standard=38 particle=9 foliage=4 custom=6 packageOwned=4
  risk=GrabPass:1,CGPROGRAM:6,_Cutoff:4`. Rollback point: a branch.
- **1** — package installed (turn boundary), asset and renderer from the Rendering Settings
  converter, both tiers assigned: `explicitTiers=2/2 postProcessData=True`, then
  `converted=57/57 on2D=0 nullBaseMap=0 skippedPackage=4`. Hazard smoke and the sentry's
  scanning cone go to the effect bucket, not to Lit.
- **2** — one global Volume in the gate scene, four persisted overrides, `legacyDisabled=2/2`.
- **3** — the old bake turns out to be what was blowing out the lane markings; cleared, rebake
  started, `bake=running` at the end of the turn.
- **4** — deferred with Phase 3. `Partial migration`, the bake as the one open item, the
  `GrabPass` hit on the pickup shader as manual follow-up.
