---
name: unity-2d-pixel-perfect
description: >-
  Pixel art that renders soft, shimmering or seam-ridden in Unity 2D — camera,
  import and snapping settings across both components called
  PixelPerfectCamera. Load for: blurry or washed-out sprites at any zoom,
  pixels that crawl while the camera moves, hairline gaps between tilemap
  tiles, "which PixelPerfectCamera do I add", a component that compiles but
  does nothing after a render-pipeline change, Cinemachine and the pixel camera
  fighting over orthographic size, UI text gone soft when the scene did not,
  post-processing blurring the frame, stuttering physics sprites, or choosing
  a reference resolution. The pipeline in force decides which same-named
  component is correct, so resolve it first.
---

# unity-2d-pixel-perfect — two components with the same name, and only one of them is yours

> **Pixel perfect is not one Unity feature, it is two incompatible implementations of one name.**
> URP ships `UnityEngine.Rendering.Universal.PixelPerfectCamera`, driven by enums. The
> standalone `com.unity.2d.pixel-perfect` package ships `UnityEngine.U2D.PixelPerfectCamera`,
> driven by booleans. Adding the wrong one costs you nothing at compile time and everything at
> runtime, so **the pipeline in force decides the component, and you resolve it first.**

## Symptom → where to look

| Symptom | Go to |
|---|---|
| "Which `PixelPerfectCamera` do I add" | §1 |
| The component is on the camera and nothing snaps | §1 — wrong implementation for the pipeline |
| `PixelPerfectCamera` will not resolve in an Editor script | §1 — assembly names |
| Sprites are soft or washed out at every zoom | §2 |
| Sprites sharp at one zoom, soft at another | §3 — non-integer scale factor |
| Hairline gaps between tilemap tiles | §5 |
| Pixels crawl or shimmer while the camera pans | §4 `gridSnapping`, then §8 |
| The camera jitters and framing pops between shots | §6 — Cinemachine |
| UI text went soft; the scene did not | §7 |
| Post-processing blurs the entire frame | §7 |
| A physics-driven sprite stutters while everything else is smooth | §8 |
| Black bars, or the scene stretched to a wrong aspect | §4 `cropFrame`, §3 |
| Compiler errors naming `UnityEngine.Experimental.Rendering.Universal` | §9 |
| Property tables, enum values, old-bool mapping | [`reference/api-and-enums.md`](reference/api-and-enums.md) |

## 1. Resolve the pipeline, then pick the component

> **Read `GraphicsSettings.currentRenderPipeline`, not `RenderPipelineManager.currentPipeline`.**
> The second holds the pipeline *instance*, which does not exist until a frame has rendered, so
> it reports "built-in" on startup paths and on headless checks. On a project running URP,
> `RenderPipelineManager.currentPipeline` can be **null** while
> `GraphicsSettings.currentRenderPipeline` names the URP asset. Two APIs, opposite answers, same
> instant.

| | URP | Standalone built-in |
|---|---|---|
| Type | `UnityEngine.Rendering.Universal.PixelPerfectCamera` | `UnityEngine.U2D.PixelPerfectCamera` |
| Assembly | `Unity.RenderPipelines.Universal.2D.Runtime` | `Unity.2D.PixelPerfect` (confirm by reflection) |
| Comes from | URP itself — nothing to install | `com.unity.2d.pixel-perfect` |
| API shape | Enums: `gridSnapping`, `cropFrame` | Booleans: `pixelSnapping`, `upscaleRT`, `cropFrameX/Y`, `stretchFill` |

Confirm the standalone assembly name by reflection on a project that has the package —
`reference/pipeline-and-migration.md` §2, with why a guessed `Runtime` suffix breaks `Type.GetType`
and the lockfile check.

> **Do not add `com.unity.2d.pixel-perfect` to a URP project.** It installs and compiles without
> complaint, and leaves the project carrying two different components under one name — remove the
> package rather than working out which one wins. On a URP project the type you want is already
> there; a project that arrived with the package already on a camera is §9.

**A null default pipeline does not mean built-in.** A project can have an empty default with
every quality tier overriding it; `currentRenderPipeline` folds the tier in and is the one to
trust. The six reads and the grep trap: `reference/pipeline-and-migration.md` §1; the full
procedure: `unity-render-urp` → `reference/resolve-active-pipeline.md`.

Code: [`resources/PipelineDetection.cs`](resources/PipelineDetection.cs) — pipeline probe,
component-type lookup for either pipeline, and the mismatch check §9 uses.

> **Report, then wait.** Fixing import settings reimports textures and rewrites `.meta` files
> across the art folder; adding or swapping a camera component changes a scene. Survey first,
> list what you would change with before/after values, and wait for confirmation. Default to the
> open scene — sweep the whole project only when asked for it.

Reaching a live Editor for any of these reads: `unity-debug` → `reference/editor-control.md`.

## 2. The four import settings that decide sharpness

Bilinear filtering is the single most common cause of soft pixel art, and it is the import
default — not a setting anyone chose — so every untouched sprite is on `FilterMode.Bilinear`.

| Setting | Value | Why |
|---|---|---|
| `filterMode` | `FilterMode.Point` | Bilinear interpolates between texels; every edge in the art softens |
| `mipmapEnabled` | `false` | A mip chain hands the GPU a pre-blurred texture the moment scale drops below 1:1 |
| `textureCompression` | `Uncompressed` | Block compression invents colours that were never in the palette |
| `spritePixelsPerUnit` | one value, project-wide | Mixed PPU means two sprites disagree about the size of a pixel |

Two more that are not on the importer:

- `QualitySettings.antiAliasing = 0` and `anisotropicFiltering = Disable`, plus the URP asset's
  `msaaSampleCount = 1`: AA exists to soften edges. Read them rather than assume, since the values
  belong to the **active quality level** and another tier can differ.
- On the camera: `allowHDR`, `allowMSAA` and `allowDynamicResolution` all `false`.

> **A centre pivot on an odd-sized sprite lands on half a pixel.** A 15×15 sprite pivoted at
> `(0.5, 0.5)` anchors at 7.5 px, and the whole sprite renders half a pixel off the grid — which
> reads as "only this one sprite is blurry". Set `alignment = SpriteAlignment.Custom` and a pivot
> that resolves to a whole pixel, or author on even dimensions. Editing pivots and rects is
> `unity-2d-sprites`.

**Editor grid snapping**, so hand-placed objects land on pixels: grid size `1 / assetsPPU` on all
axes (PPU 16 → 0.0625, PPU 100 → 0.01), snapping enabled in the Grid and Snap overlay, and
*Align Selected → All Axes* to pull objects that are already off-grid back on.

Code: [`resources/SpriteImportFix.cs`](resources/SpriteImportFix.cs) — survey and fix, one
texture at a time, with the reimport that makes it real.

## 3. Reference resolution, chosen once

Pick it before art production and do not move it: it sets the pixel size of every asset, and
changing it later is a re-draw.

| Reference resolution | 1920×1080 | 2560×1440 | 3840×2160 |
|---|---|---|---|
| 320 × 180 | 6× | 8× | 12× |
| 480 × 270 | 4× | 5.33× | 8× |
| 640 × 360 | 3× | 4× | 6× |

320×180 fits the three common targets at whole numbers, which is why it is the safe default.
A fractional factor is where pixel decimation comes from: at 5.33× some source pixels occupy 5
screen pixels and their neighbours 6, and the art looks unevenly ribbed. Screens with no integer
fit at all (1366×768 against 320×180 is 4.27×) are handled by giving up the extra pixels rather
than the grid — `cropFrame = Windowbox` — not by stretching.

`Camera.orthographicSize` follows from the choice: `(refResolutionY / 2f) / assetsPPU`. At
320×180 and PPU 16 that is `90 / 16 = 5.625`. The component's own `orthographicSize` is a
separate, read-only value; do not conflate the two.

## 4. `gridSnapping` and `cropFrame`

`GridSnapping` is `None`, `PixelSnapping`, `UpscaleRenderTexture`; `CropFrame` is `None`,
`Pillarbox`, `Letterbox`, `Windowbox`, `StretchFill`; `PixelPerfectFilterMode` is `RetroAA`,
`Point` — all enumerated from the assembly. `PixelSnapping` + `Windowbox` is the default worth
reaching for: it snaps sprite renderers at render time, leaves transforms at float precision, and
stays compatible with post-processing and with UI. `UpscaleRenderTexture` renders the frame at
reference resolution and scales the whole buffer up — the authentic look, and the source of both
problems in §7.

> **`PixelPerfectFilterMode` has no public property on the URP component.** Only the serialized
> private `m_FilterMode`, so the Inspector can set it and script cannot — author it in a prefab or
> scene. It is documented to apply only under `cropFrame = StretchFill`, and it is unrelated to
> per-texture `filterMode` (§2).

Property tables for both components, the old-bool mapping, recommended combinations and the
`pixelSnapSpacing` formula: [`reference/api-and-enums.md`](reference/api-and-enums.md).

## 5. Tilemap seams — work the ladder in order

Hairline gaps between tiles have six ordinary causes and one that only appears in motion. Work
top to bottom; the popular workarounds (a negative cell gap, PPU 31.99 for a 32 px tile) break the
moment the camera moves.

| # | Check | If it fails |
|---|---|---|
| 1 | Atlas: Tight Packing **off**, Padding **≥ 4**, packing actually enabled | Neighbouring tiles bleed into each other's edge texels |
| 2 | Mipmaps off on the tileset textures **and** on the atlas | A mip level is sampled and the tile edge fades |
| 3 | AA 0 in the active quality level, MSAA off on the camera | §2 |
| 4 | Compression `Uncompressed` | Block artefacts land on the tile boundary |
| 5 | Every tile sprite has **even** pixel dimensions | Odd sizes put the grid on a half pixel — §2 |
| 6 | `assetsPPU` equals the tile's pixel width (16×16 → 16) | A PPU mismatch is a real gap in world space, not a sampling one |
| 7 | Gaps appear **only while the camera moves**, everything above passing | This is the case pixel snapping exists for: set `gridSnapping = PixelSnapping` |

Rows 1 and 2 are atlas territory — `unity-sprite-atlas` owns packing, padding and packer mode;
authoring the tilemap is `unity-tilemap`.

## 6. Cinemachine writes orthographic size too

Both Cinemachine and the pixel camera set orthographic size every frame, and the loser is
whichever ran first: jitter, plus framing that pops between shots. Add the
**`CinemachinePixelPerfect` extension** through the Add Extension dropdown on each virtual camera —
added by `AddComponent` it is not registered with the virtual camera's extension list. What it
calls, and three limits to design around rather than fix: `reference/motion-and-upscale.md` §1.

## 7. `UpscaleRenderTexture` versus UI text and post-processing

One cause, two symptoms: the scene is rendered small and then scaled up, and anything that runs
after that scale-up — or gets caught inside it — is working at the wrong resolution.
**Post-processing** then filters an enlarged image: leave `gridSnapping = PixelSnapping`, or inject a
2D renderer feature after post-processing, since a plain `ScriptableRendererFeature` on a URP 2D
renderer is **ignored without an error**. **UI text** on a Screen Space – Camera canvas softens with
the scene: set the canvas to **Screen Space – Overlay**, the route that holds. The ranked
alternatives and where canvas and font work goes: `reference/motion-and-upscale.md` §2. Confirm
either fix in a windowed run with the canvas and a volume in the scene — a headless check shows
neither symptom.

## 8. Micro-stutter is physics, not rendering

A sprite driven by `Rigidbody2D` stutters while everything else is smooth: physics advances on a
fixed timestep and rendering does not, and snapping makes the sub-pixel error visible. The fix is
`Rigidbody2D.interpolation = RigidbodyInterpolation2D.Interpolate` on every physics-driven sprite;
a matched fixed timestep and camera follow in `LateUpdate` tighten it —
`reference/motion-and-upscale.md` §3. Confirm it in play mode with a moving rigidbody.

## 9. Migration

**Wrong component for the pipeline** — URP in force, `UnityEngine.U2D.PixelPerfectCamera` on the
camera: remove the package and the component, add the URP one, re-enter the settings (booleans do
not migrate into enums). `PipelineDetection.HasWrongComponent` finds it. **Deprecated booleans on
the right component** still compile, as a **warning, not an error** — so bool-style code compiling
proves nothing about which component you are on. Read the type, not the property names.

**Old URP namespace** (`UnityEngine.Experimental.Rendering.Universal`), **no 2D renderer under
URP**, and **HDRP**, which has no Pixel Perfect Camera at all: steps for all five cases, and the
bool → enum mapping, via `reference/pipeline-and-migration.md` §3.

## Scope — what this skill does NOT do

Slicing sheets, pivots, rects, 9-slice borders and outlines are `unity-2d-sprites` — this skill
only says which pivot values keep a sprite on the grid. Atlas packing, padding, packer mode and
atlas memory are `unity-sprite-atlas`, which rows 1 and 2 of §5 hand off to. Tilemaps, palettes
and rule tiles are `unity-tilemap`; §5 ends at "the seam is not the tilemap's fault".

Resolving the active render pipeline, URP asset and renderer configuration, Volumes and Render
Graph passes are `unity-render-urp` — §1 reads the pipeline, it does not set it. The canvas itself
— render mode, scaler, layout — is `unity-ui-ugui`, and font assets and CJK glyph coverage are
`unity-game-ui`; §7 only says which canvas mode escapes the upscale. Before/after screenshots and
connecting to a live Editor at all are `unity-debug`.

Art direction is out of scope in both directions: this skill will not tell you a resolution is
too low for your art, and it does not apply to high-resolution or hand-painted 2D, where point
filtering and snapping make smooth art look wrong.

## Reference

- [`reference/api-and-enums.md`](reference/api-and-enums.md) — both components member by member,
  enums with old-bool equivalents, combinations, `pixelSnapSpacing`.
- [`reference/pipeline-and-migration.md`](reference/pipeline-and-migration.md) — pipeline reads,
  assembly names, migration steps.
- [`reference/motion-and-upscale.md`](reference/motion-and-upscale.md) — Cinemachine limits, the
  upscale's side effects, physics stutter.
- Code: [`PipelineDetection.cs`](resources/PipelineDetection.cs) (resolve the pipeline, pick the
  type, detect a mismatch), [`CameraSetupURP.cs`](resources/CameraSetupURP.cs) (enum-style),
  [`CameraSetupBuiltIn.cs`](resources/CameraSetupBuiltIn.cs) (bool-style, standalone package),
  [`SpriteImportFix.cs`](resources/SpriteImportFix.cs) (the four import settings from §2).
