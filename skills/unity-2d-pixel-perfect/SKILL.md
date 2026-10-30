---
name: unity-2d-pixel-perfect
description: >-
  Blurry, shimmering or seamed pixel art in Unity: Pixel Perfect Camera,
  import settings, snapping.
---

# unity-2d-pixel-perfect — two components with the same name, and only one of them is yours

> **Pixel perfect is not one Unity feature, it is two incompatible implementations of one name.**
> URP ships `UnityEngine.Rendering.Universal.PixelPerfectCamera`, driven by enums. The
> standalone `com.unity.2d.pixel-perfect` package ships `UnityEngine.U2D.PixelPerfectCamera`,
> driven by booleans. Adding the wrong one costs you nothing at compile time and everything at
> runtime, so **the pipeline in force decides the component, and you resolve it first.**

## Start here — symptom → where to look

| Symptom | Go to |
|---|---|
| "Which `PixelPerfectCamera` do I add"; the pipeline in force decides which same-named component | §1 |
| The component is on the camera and nothing snaps; it compiles but does nothing after a render-pipeline change | §1, §9 — wrong implementation for the pipeline |
| `PixelPerfectCamera` will not resolve in an Editor script | §1 — assembly names |
| Sprites are soft or washed out at every zoom | §2 |
| Sprites sharp at one zoom, soft at another; choosing a reference resolution | §3 — non-integer scale factor |
| Hairline gaps between tilemap tiles | §5 |
| Pixels crawl or shimmer while the camera pans | §4 `gridSnapping`, then §8 |
| The camera jitters and framing pops between shots; Cinemachine and the pixel camera fight over orthographic size | §6 — Cinemachine |
| UI text went soft; the scene did not | §7 |
| Post-processing blurs the entire frame | §7 |
| A physics-driven sprite stutters while everything else is smooth | §8 |
| Black bars, or the scene stretched to a wrong aspect | §4 `cropFrame`, §3 |
| Compiler errors naming `UnityEngine.Experimental.Rendering.Universal` | §9 |
| Property tables, enum values, old-bool mapping | `reference/api-and-enums.md` |

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

Code: `resources/PipelineDetection.cs` — pipeline probe,
component-type lookup for either pipeline, and the mismatch check §9 uses.

> **Report, then wait.** Fixing import settings reimports textures and rewrites `.meta` files
> across the art folder; adding or swapping a camera component changes a scene. Survey first,
> list what you would change with before/after values, and wait for confirmation. Default to the
> open scene — sweep the whole project only when asked for it.

Reaching a live Editor for any of these reads: `unity-debug` → `reference/editor-control.md`.

## 2. The four import settings that decide sharpness

Bilinear filtering is the import default and the most common cause of soft pixel art. Set
`filterMode = Point`, mipmaps off, `Uncompressed`, one `spritePixelsPerUnit` project-wide; AA 0 in
the **active** quality level, MSAA 1 on the URP asset, and `allowHDR`/`allowMSAA`/
`allowDynamicResolution` off on the camera. A centre pivot on an odd-sized sprite lands on half a
pixel ("only this one sprite is blurry"). Editor grid snapping: `1 / assetsPPU`. The table, the
why and the snapping steps: `reference/sharpness.md` §2. Code:
`resources/SpriteImportFix.cs`.

## 3. Reference resolution, chosen once

Pick it before art production: 320×180 fits 1080p, 1440p and 2160p at whole numbers (6×, 8×,
12×), which is why it is the safe default; a fractional factor ribs the art, and a screen with no
integer fit gets `cropFrame = Windowbox`, not a stretch. `Camera.orthographicSize =
(refResolutionY / 2f) / assetsPPU` (320×180 at PPU 16 → 5.625), separate from the component's own
read-only value. The table: `reference/sharpness.md` §3.

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
`pixelSnapSpacing` formula: `reference/api-and-enums.md`.

## 5. Tilemap seams — work the ladder in order

Hairline gaps have six ordinary causes and one that appears only in motion; work them top to
bottom, never a negative cell gap or PPU 31.99: atlas Tight Packing off and Padding ≥ 4 → mipmaps
off on tileset and atlas → AA and MSAA off → `Uncompressed` → even pixel dimensions → `assetsPPU`
equal to the tile's width → gaps only while the camera moves: `gridSnapping = PixelSnapping`. The
ladder with each failure: `reference/sharpness.md` §5. Rows 1 and 2 are `unity-sprite-atlas`;
authoring the tilemap is `unity-tilemap`.

## 6. Cinemachine writes orthographic size too

The pixel camera owns orthographic size, and Cinemachine writes it every frame too: jitter, plus
framing that pops between shots. Put the **`CinemachinePixelPerfect` extension** on every camera
rig, through its Add Extension dropdown. Follow, dead zones, confiners, blends and the component
names for each Cinemachine major: `unity-camera` → `reference/pixel-perfect-follow.md`.

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
`reference/motion-and-upscale.md` §3. Confirm it in play mode with a moving rigidbody. The
movement code itself is `unity-2d-controller`.

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
and rule tiles are `unity-tilemap`; §5 ends at "the seam is not the tilemap's fault". Parallax
and sorting are `unity-2d-rendering`.

Resolving the active render pipeline, URP asset and renderer configuration, Volumes and Render
Graph passes are `unity-render-urp` — §1 reads the pipeline, it does not set it. The canvas itself
— render mode, scaler, layout — is `unity-ui-ugui`, and font assets and CJK glyph coverage are
`unity-game-ui`; §7 only says which canvas mode escapes the upscale. Before/after screenshots and
connecting to a live Editor at all are `unity-debug`.

Art direction is out of scope in both directions: this skill will not tell you a resolution is
too low for your art, and it does not apply to high-resolution or hand-painted 2D, where point
filtering and snapping make smooth art look wrong.

## Reference

- `reference/api-and-enums.md` — both components member by member,
  enums with old-bool equivalents, combinations, `pixelSnapSpacing`.
- `reference/sharpness.md` — the import settings table, reference
  resolutions, the tilemap seam ladder.
- `reference/pipeline-and-migration.md` — pipeline reads,
  assembly names, migration steps.
- `reference/motion-and-upscale.md` — the Cinemachine rule, the
  upscale's side effects, physics stutter.
- Code: `PipelineDetection.cs` (resolve the pipeline, pick the
  type, detect a mismatch), `CameraSetupURP.cs` (enum-style),
  `CameraSetupBuiltIn.cs` (bool-style, standalone package),
  `SpriteImportFix.cs` (the four import settings from §2).
