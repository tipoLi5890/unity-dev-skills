# Which pipeline is in force, and moving between the two components

> Part of the `unity-2d-pixel-perfect` skill. `SKILL.md` §1 and §9 state the rules; this file holds
> the reads behind them and the migration steps in full.

## 1. A null default pipeline does not mean built-in

A URP project whose quality tiers carry the pipeline reads:

| Read | Value |
|---|---|
| `GraphicsSettings.defaultRenderPipeline` | `null` |
| `ProjectSettings/GraphicsSettings.asset` → `m_CustomRenderPipeline` | `{fileID: 0}` |
| `GraphicsSettings.currentRenderPipeline` | `UniversalRenderPipelineAsset` at `Assets/Settings/UniversalRP.asset` |
| `QualitySettings.renderPipeline` | the same asset |
| Quality levels carrying an override | **every one**, key `customRenderPipeline:` |
| Active `scriptableRenderer` | `UnityEngine.Rendering.Universal.Renderer2D` |

The project default is empty and every quality tier overrides it, so the answer depends entirely
on which API you asked. `currentRenderPipeline` folds the tier in and is the one to trust.
Two consequences worth writing down: a **case-sensitive** disk grep for `renderPipeline:` finds
nothing in `QualitySettings.asset` because the key is spelled `customRenderPipeline:`, and a tier
override only bites on the platforms that select that tier. The full resolution procedure, disk
and Editor side, is `unity-render-urp` → `reference/resolve-active-pipeline.md`.

## 2. The two assembly names, and the package that must stay out of URP

For the URP component, `Assembly.GetName().Name` on
`UnityEngine.Rendering.Universal.PixelPerfectCamera` returns
`Unity.RenderPipelines.Universal.2D.Runtime`.

The standalone asmdef is reported as `Unity.2D.PixelPerfect`, with **no `Runtime` suffix** even
though its source sits in a `Runtime/` folder. Confirm it by reflection on a project that genuinely
runs built-in: where the package is absent — as it should be on URP — an assembly-qualified lookup
returns null whatever the name is. Guessing the suffix either way is the usual reason an
assembly-qualified `Type.GetType` returns null.

Confirm absence in `Packages/packages-lock.json` before believing a project is clean — the lockfile
is also where to read the version that resolved;
`PackageInfo.FindForAssetPath("Packages/com.unity.2d.pixel-perfect/package.json")` returns null
when the lockfile has no such entry.

## 3. Migration, case by case

**Wrong component for the pipeline.** URP is in force and the camera carries
`UnityEngine.U2D.PixelPerfectCamera`. Nothing in the Editor objects to that arrangement, which is
how it survives long enough to become a migration. Remove `com.unity.2d.pixel-perfect`, remove the
component from every camera, add the URP one, then re-enter the settings: the booleans do not
migrate into the enums. `PipelineDetection.HasWrongComponent` in `resources/PipelineDetection.cs`
finds it; [`api-and-enums.md`](api-and-enums.md) has the bool → enum mapping.

**Deprecated booleans on the right component.** The URP component still exposes `upscaleRT`,
`pixelSnapping`, `cropFrameX`, `cropFrameY` and `stretchFill`, each carrying
`[Obsolete("Use gridSnapping instead #from(2021.2)")]` as a **warning, not an error**. So
bool-style code compiling successfully proves nothing about which component you are on — it may be
the URP one, deprecated. Read the type, not the property names.

**Old URP namespace.** Compiler errors naming `UnityEngine.Experimental.Rendering.Universal` come
from code written against URP before the type moved to `UnityEngine.Rendering.Universal`. Change
the `using`, and update any assembly-qualified type string by hand — those are text and no
attribute rewrites them. Components already on GameObjects survive: the type carries a
`[MovedFrom]` attribute and serialised references resolve. Open one scene saved before the move and
check the component survived before migrating the rest.

**No 2D renderer under URP.** `PixelPerfectCamera` needs the 2D renderer to be the one in use.
Create a 2D Renderer Data asset, assign it in the URP asset's renderer list, and confirm the
result: `((UniversalRenderPipelineAsset)GraphicsSettings.currentRenderPipeline).scriptableRenderer`
must read `UnityEngine.Rendering.Universal.Renderer2D`. The 2D renderer arrives with
`com.unity.render-pipelines.universal` itself and needs **12.0 or newer**; read the version that
resolved off `Packages/packages-lock.json` rather than the manifest's range, and on anything older
say the renderer is unavailable instead of hunting for the missing menu entry.

**HDRP.** Pixel Perfect Camera is not supported. There is no component to add and no setting to
find; a project that needs pixel-perfect 2D on HDRP needs a render texture at reference
resolution with `FilterMode.Point` and a custom blit, which is a rendering project rather than a
settings change.

The shape that custom blit takes depends on the Unity version, and the two are not
interchangeable. `OnRenderImage` with `Graphics.Blit` is the built-in form, and it is
**incompatible with the render graph** — on Unity 6 the work is a `ScriptableRendererFeature2D`
and a `ScriptableRenderPass2D` injected through a `RenderPassEvent2D` value, recording into the
graph with `AddRasterRenderPass`. Confirm those names against the pipeline package the project
resolved before writing any of it, and quote the version you confirmed against in the report: a
feature built on the wrong base class is dropped from a 2D renderer without an error. Reviewing a
render-graph pass is `unity-render-urp` → `reference/render-graph-review.md`.
