# Both PixelPerfectCameras, member by member

> Part of the `unity-2d-pixel-perfect` skill. `SKILL.md` §1 decides *which* component you are
> looking at. This file is what each one exposes, so a setup script can be written without
> guessing a property name that belongs to the other implementation.

Enumerate member names, types and access by reflection against a live Editor rather than
recalling them — and that is all reflection returns: the **behaviour** columns describe each
member's documented contract. The standalone component's surface, including the
standalone-equivalent column of both enum tables, is the shape to expect; confirm it by reflection
on a project that has the package.

## URP — `UnityEngine.Rendering.Universal.PixelPerfectCamera`

Assembly `Unity.RenderPipelines.Universal.2D.Runtime`. Ships with URP; there is nothing to
install.

### Current members

Declared public instance members, in the order reflection returns them:

| Member | Type | Access | Notes |
|---|---|---|---|
| `cropFrame` | `CropFrame` | get/set | Aspect-ratio policy — table below |
| `gridSnapping` | `GridSnapping` | get/set | Snapping mode — table below |
| `orthographicSize` | `float` | **get only** | The component's computed size. Not `Camera.orthographicSize`, which you set yourself |
| `assetsPPU` | `int` | get/set | Has to equal the `spritePixelsPerUnit` every sprite in the scene imported with |
| `refResolutionX` | `int` | get/set | Reference width |
| `refResolutionY` | `int` | get/set | Reference height |
| `pixelRatio` | `int` | **get only** | The whole-number scale actually applied — 6 at 1080p from a 320×180 reference |
| `requiresUpscalePass` | `bool` | **get only** | True exactly when `gridSnapping == UpscaleRenderTexture` |
| `RoundToPixel(Vector3)` | `Vector3` | method | Snaps a world position to the grid, honouring the current `gridSnapping`. Use it in a custom camera controller instead of rounding by hand |
| `CorrectCinemachineOrthoSize(float)` | `float` | method | Nearest pixel-perfect orthographic size. What the Cinemachine extension calls |

Also declared: `OnBeforeSerialize` / `OnAfterDeserialize`, the serialisation callbacks that
upgrade the deprecated fields below. Not yours to call.

### Deprecated members that still compile

| Member | Type | State |
|---|---|---|
| `pixelSnapping` | `bool` | `[Obsolete("Use gridSnapping instead #from(2021.2)")]`, **warning not error** |
| `upscaleRT` | `bool` | same |
| `cropFrameX` | `bool` | same |
| `cropFrameY` | `bool` | same |
| `stretchFill` | `bool` | same |

> **Bool-style code compiling is not evidence you are on the standalone component.** All five
> obsolete attributes are `IsError = false`, so a project can be writing
> `pp.upscaleRT = true` against the *URP* component and see only a warning. Diagnose by reading
> the type, never by reading which properties the code touches.

### `PixelPerfectFilterMode` — Inspector only

**There is no public `filterMode` property on the component.** The declared non-public serialized
field is `m_FilterMode` and reflection finds no accessor of that name, so the value has to be
authored in a prefab or scene rather than set from a setup script.

Enum members, enumerated: `RetroAA`, `Point`. It is a different thing from the per-texture
`FilterMode` that `SKILL.md` §2 sets.

With no public accessor there is no value to read back from script, so the default and the gating
below are the documented behaviour — check them in the Inspector.

- The mode is reported to take effect only under `cropFrame = StretchFill`.
- `RetroAA` — scale by the largest whole number that fits, then bilinear the remainder to the
  screen. Reported as the default, and the right choice either way: the pixel grid survives and
  only the leftover fraction is smoothed.
- `Point` — nearest-neighbour the whole way. At a fractional scale factor it is the mode that
  produces unevenly sized pixels.

### `GridSnapping`

Enumerated: `None`, `PixelSnapping`, `UpscaleRenderTexture`.

| Value | Standalone equivalent | Behaviour |
|---|---|---|
| `None` | `pixelSnapping = false`, `upscaleRT = false` | Nothing is snapped. Sub-pixel positions render as they are |
| `PixelSnapping` | `pixelSnapping = true` | Sprite renderers snap at render time; transforms keep float precision. Compatible with post-processing and UI |
| `UpscaleRenderTexture` | `upscaleRT = true` | Renders at reference resolution, then scales the buffer. Authentic, and the cause of both failures in `SKILL.md` §7 |

`PixelSnapping` snapping at *render* time rather than moving the transform is what makes it safe:
gameplay code reads the un-snapped position, so nothing downstream inherits a quantised value.

The standalone-equivalent column in this table and the next is the bool-to-enum mapping to expect;
confirm it on a project that has the standalone package before porting settings across.

### `CropFrame`

Enumerated: `None`, `Pillarbox`, `Letterbox`, `Windowbox`, `StretchFill`.

| Value | Standalone equivalent | Behaviour |
|---|---|---|
| `None` | both `cropFrame*` false | No bars. The scene stretches to whatever the screen aspect is |
| `Pillarbox` | `cropFrameX = true`, `cropFrameY = false` | Bars left and right |
| `Letterbox` | `cropFrameX = false`, `cropFrameY = true` | Bars top and bottom |
| `Windowbox` | both true, `stretchFill = false` | Bars on whichever axes need them. The safe default: no aspect is ever distorted |
| `StretchFill` | both true, `stretchFill = true` | Fills the screen keeping aspect. The only mode where `PixelPerfectFilterMode` applies |

### Combinations worth starting from

| Goal | `gridSnapping` | `cropFrame` | What you accept |
|---|---|---|---|
| Ordinary pixel art | `PixelSnapping` | `Windowbox` | Black bars on odd aspects. Post-processing and UI both work |
| Authentic low-resolution frame | `UpscaleRenderTexture` | `Windowbox` | No post-processing; UI needs its own path (§7) |
| Fewer pixels on 4K / HiDPI | `UpscaleRenderTexture` | `Windowbox` | Same UI and post-processing cost as above, bought for fill-rate |
| Edge-to-edge, no bars | `PixelSnapping` | `StretchFill` | Leave the filter mode on `RetroAA`; `Point` re-introduces uneven pixels |

## `PixelPerfectRendering.pixelSnapSpacing`

`UnityEngine.U2D.PixelPerfectRendering` is a static class with exactly one public static member,
`pixelSnapSpacing` (`float`) — the world-space size of one screen pixel, which the sprite
renderers read when they snap.

> **It lives in `UnityEngine.CoreModule`, not in the URP 2D assembly.** An assembly-qualified lookup
> against `Unity.RenderPipelines.Universal.2D.Runtime` returns null, which reads as "the API does
> not exist in this version". It does; the namespace just does not follow the assembly.

The component maintains it for you. Set it by hand only where there is no component to do it —
a custom SRP, or a render-texture fallback:

```csharp
UnityEngine.U2D.PixelPerfectRendering.pixelSnapSpacing =
    camera.orthographicSize * 2f / camera.pixelHeight;
```

`orthographicSize * 2` is the visible world height; dividing by the framebuffer height in pixels
gives the world size of one of them. Recompute it whenever the camera size or the backbuffer
changes, or snapping quantises to a stale grid.

## Standalone built-in — `UnityEngine.U2D.PixelPerfectCamera`

From `com.unity.2d.pixel-perfect`; read the version that resolved off
`Packages/packages-lock.json`.

The assembly is reported as `Unity.2D.PixelPerfect`, with no `Runtime` suffix despite the folder
layout. Treat it and the member table below as the API shape to expect, and confirm both by
reflection on a project that genuinely uses the built-in pipeline — never by installing the package
into a URP project, which `SKILL.md` §1 tells you not to do.

| Property | Type | Constraint |
|---|---|---|
| `assetsPPU` | `int` | Same meaning as URP |
| `refResolutionX` / `refResolutionY` | `int` | Same meaning as URP |
| `pixelSnapping` | `bool` | Has no effect while `upscaleRT` is true — silently, no warning |
| `upscaleRT` | `bool` | Renders at reference resolution and scales up |
| `cropFrameX` | `bool` | Bars left and right |
| `cropFrameY` | `bool` | Bars top and bottom |
| `stretchFill` | `bool` | Only functional when **both** `cropFrameX` and `cropFrameY` are true |
| `pixelRatio` | `int` read-only | Same meaning as URP |

What it does **not** have, and what a naive port therefore breaks on: `RoundToPixel`,
`CorrectCinemachineOrthoSize`, `requiresUpscalePass`, and the read-only `orthographicSize`. A
custom camera controller written for URP has to round positions itself here, and the Cinemachine
extension has nothing to call.

Setup code for each shape is `resources/CameraSetupURP.cs` and
`resources/CameraSetupBuiltIn.cs`.
