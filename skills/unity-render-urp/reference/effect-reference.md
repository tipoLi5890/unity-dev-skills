# The sixteen Volume overrides, with their real defaults and ranges

> Part of the `unity-render-urp` skill. Every default and range below is what a freshly
> constructed instance of the component reports by reflection — the dump in the last section
> regenerates them. All sixteen types resolve in `UnityEngine.Rendering.Universal` (assembly
> `Unity.RenderPipelines.Universal.Runtime`) and all sixteen derive from `VolumeComponent`.
> Re-run the dump on your own version before trusting a range; URP moves these.

Two things that hold for every row:

- **A parameter contributes nothing until `overrideState = true`.** The default is a value the
  Volume system is ignoring. `profile.Add<T>(true)` switches them all on for that component —
  the overload is `Add(bool overrides = false)`.
- **A `Clamped*Parameter` silently clamps.** Writing 2 into a 0–1 parameter is not an error; it
  is a 1. When a value "does not take", read the range before re-reading the code.

## The rename that eats the most time

> **The class is `ColorAdjustments`. There is no `ColorGrading`.**
> `UnityEngine.Rendering.Universal.ColorGrading` does not resolve at all — the name
> belongs to the pre-URP stack, and the compile error names a missing type rather than a moved
> one, which sends people looking for a package.

Exposure, contrast, hue and saturation are all on `ColorAdjustments`. Tone curves are a separate
component, `ColorCurves`. Tonemapping is a third, `Tonemapping`. Anything that treats "color
grading" as one component is written against the old stack.

## Bloom

Glow on bright pixels. Best with HDR on the URP Asset; it still functions in SDR provided
`threshold` is below 1, or nothing is bright enough to select.

| Parameter | Type | Default | Range |
|---|---|---|---|
| `threshold` | MinFloatParameter | 0.9 | min 0 |
| `intensity` | MinFloatParameter | **0** | min 0 |
| `scatter` | ClampedFloatParameter | 0.7 | 0–1 |
| `clamp` | MinFloatParameter | 65472 | min 0 |
| `tint` | ColorParameter | white | |
| `highQualityFiltering` | BoolParameter | false | bicubic upsample |
| `filter` | BloomFilterModeParameter | `Gaussian` | `Gaussian`, `Dual`, `Kawase` |
| `downscale` | DownscaleParameter | `Half` | `Half`, `Quarter` |
| `maxIterations` | ClampedIntParameter | 6 | **2–8** |
| `skipIterations` | ClampedIntParameter | 1 | 0–16 |
| `dirtTexture` | TextureParameter | null | |
| `dirtIntensity` | MinFloatParameter | 0 | min 0 |

`intensity` defaulting to **0** is why "I added Bloom and nothing happened" is usually true even
when everything else is right: the component is present, enabled, overridden, and multiplying by
zero. `filter` and `skipIterations` are not in older write-ups of this component — check they
exist before generating code that sets them.

## Tonemapping

Maps HDR to the display range. Requires HDR on the URP Asset.

| Parameter | Type | Default | Range |
|---|---|---|---|
| `mode` | TonemappingModeParameter | `None` | `None`, `Neutral`, `ACES` |
| `neutralHDRRangeReductionMode` | NeutralRangeReductionModeParameter | `BT2390` | `Reinhard`, `BT2390` |
| `acesPreset` | HDRACESPresetParameter | `ACES1000Nits` | `ACES1000Nits`, `ACES2000Nits`, `ACES4000Nits` |
| `hueShiftAmount` | ClampedFloatParameter | 0 | 0–1 |
| `detectPaperWhite` | BoolParameter | false | |
| `paperWhite` | ClampedFloatParameter | 300 | 0–400 |
| `detectBrightnessLimits` | BoolParameter | **true** | |
| `minNits` | ClampedFloatParameter | 0.005 | 0–50 |
| `maxNits` | ClampedFloatParameter | 1000 | 0–5000 |

Everything below `hueShiftAmount` applies to HDR output displays. On an SDR target only `mode`
matters, and `mode` defaults to `None` — adding the component alone changes nothing.

## ColorAdjustments

| Parameter | Type | Default | Range |
|---|---|---|---|
| `postExposure` | FloatParameter | 0 | unbounded, EV |
| `contrast` | ClampedFloatParameter | 0 | −100–100 |
| `colorFilter` | ColorParameter | white | multiplied into the result |
| `hueShift` | ClampedFloatParameter | 0 | −180–180 |
| `saturation` | ClampedFloatParameter | 0 | −100–100 |

`postExposure` is the only unbounded parameter here, and it is in EV — 1.0 is a doubling, not a
1 % nudge.

## DepthOfField

> **The two modes use disjoint parameter sets, and the fields for the mode you are not in are
> still there, still writable, and still ignored.** Setting `focusDistance` while `mode` is
> `Gaussian` compiles, runs, reads back correctly and does nothing.

| Parameter | Type | Default | Range | Used by |
|---|---|---|---|---|
| `mode` | DepthOfFieldModeParameter | `Off` | `Off`, `Gaussian`, `Bokeh` | — |
| `gaussianStart` | MinFloatParameter | 10 | min 0 | Gaussian |
| `gaussianEnd` | MinFloatParameter | 30 | min 0 | Gaussian |
| `gaussianMaxRadius` | ClampedFloatParameter | 1 | 0.5–1.5 | Gaussian |
| `highQualitySampling` | BoolParameter | false | | Gaussian |
| `focusDistance` | MinFloatParameter | 10 | min 0.1 | Bokeh |
| `focalLength` | ClampedFloatParameter | 50 | 1–300 | Bokeh |
| `aperture` | ClampedFloatParameter | 5.6 | 1–32 | Bokeh |
| `bladeCount` | ClampedIntParameter | 5 | 3–9 | Bokeh |
| `bladeCurvature` | ClampedFloatParameter | 1 | 0–1 | Bokeh |
| `bladeRotation` | ClampedFloatParameter | 0 | −180–180 | Bokeh |

Gaussian is a near/far falloff described by two distances. Bokeh is a lens: focus distance,
focal length, aperture and an aperture-blade shape. `mode` defaults to `Off`, so a
`DepthOfField` component that has never had its mode set is inert whichever set you filled in.

## Vignette

| Parameter | Type | Default | Range |
|---|---|---|---|
| `intensity` | ClampedFloatParameter | 0 | 0–1 |
| `smoothness` | ClampedFloatParameter | 0.2 | **0.01–1** |
| `color` | ColorParameter | black | |
| `center` | Vector2Parameter | (0.5, 0.5) | |
| `rounded` | BoolParameter | false | circular rather than aspect-shaped |

`smoothness` has a **floor of 0.01, not 0** — a hard-edged vignette is not reachable by setting
it to zero, and the zero you write reads back as 0.01.

## MotionBlur

| Parameter | Type | Default | Range |
|---|---|---|---|
| `mode` | MotionBlurModeParameter | `CameraOnly` | `CameraOnly`, `CameraAndObjects` |
| `quality` | MotionBlurQualityParameter | `Low` | `Low`, `Medium`, `High` |
| `intensity` | ClampedFloatParameter | 0 | 0–1 |
| `clamp` | ClampedFloatParameter | 0.05 | **0–0.2** |

`clamp` is a fraction of the screen and its whole range is 0–0.2. `CameraAndObjects` needs
per-object motion vectors, which is renderer configuration, not a Volume setting.

## FilmGrain

| Parameter | Type | Default | Range |
|---|---|---|---|
| `type` | FilmGrainLookupParameter | `Thin1` | `Thin1`, `Thin2`, `Medium1`–`Medium6`, `Large01`, `Large02`, `Custom` |
| `intensity` | ClampedFloatParameter | 0 | 0–1 |
| `response` | ClampedFloatParameter | 0.8 | 0–1 |
| `texture` | NoInterpTextureParameter | null | required when `type` is `Custom` |

## ChromaticAberration

| Parameter | Type | Default | Range |
|---|---|---|---|
| `intensity` | ClampedFloatParameter | 0 | 0–1 |

0.05–0.15 is the band where it reads as a lens rather than as a bug.

## SplitToning

| Parameter | Type | Default | Range |
|---|---|---|---|
| `shadows` | ColorParameter | mid grey (0.5, 0.5, 0.5, 1) | |
| `highlights` | ColorParameter | mid grey (0.5, 0.5, 0.5, 1) | |
| `balance` | ClampedFloatParameter | 0 | −100–100 |

The neutral colour is **mid grey**, not white — a tint set to white is a change, not a no-op.

## LensDistortion

| Parameter | Type | Default | Range |
|---|---|---|---|
| `intensity` | ClampedFloatParameter | 0 | **−1–1** (negative barrel, positive pincushion) |
| `xMultiplier` | ClampedFloatParameter | 1 | 0–1 |
| `yMultiplier` | ClampedFloatParameter | 1 | 0–1 |
| `center` | Vector2Parameter | (0.5, 0.5) | |
| `scale` | ClampedFloatParameter | 1 | 0.01–5 |

## WhiteBalance

| Parameter | Type | Default | Range |
|---|---|---|---|
| `temperature` | ClampedFloatParameter | 0 | −100–100 (negative cool, positive warm) |
| `tint` | ClampedFloatParameter | 0 | −100–100 (negative green, positive magenta) |

## PaniniProjection

| Parameter | Type | Default | Range |
|---|---|---|---|
| `distance` | ClampedFloatParameter | 0 | 0–1 |
| `cropToFit` | ClampedFloatParameter | 1 | 0–1 |

It corrects wide-angle stretching, so below roughly 90° camera FOV there is nothing for it to
correct and the effect is invisible whatever you set.

## LiftGammaGain

Three `Vector4Parameter`s, each defaulting to **(1, 1, 1, 0)**.

| Parameter | Acts on |
|---|---|
| `lift` | shadows |
| `gamma` | midtones |
| `gain` | highlights |

> **The fourth component is not alpha.** XYZ are the RGB colour trim and **W is an intensity
> offset applied on top of them**. The neutral value is `(1,1,1,0)` — writing `(1,1,1,1)`
> because "alpha should be opaque" pushes that band a full step and is the usual cause of a
> grade that came out washed out in one tonal range only.

## ShadowsMidtonesHighlights

Same Vector4 convention — RGB trim plus a W intensity offset, neutral at (1, 1, 1, 0).

| Parameter | Type | Default |
|---|---|---|
| `shadows`, `midtones`, `highlights` | Vector4Parameter | (1, 1, 1, 0) |
| `shadowsStart` | MinFloatParameter | 0 |
| `shadowsEnd` | MinFloatParameter | 0.3 |
| `highlightsStart` | MinFloatParameter | 0.55 |
| `highlightsEnd` | MinFloatParameter | 1 |

The four boundaries are `MinFloatParameter` with min 0 and **no upper clamp and no ordering
check** — nothing stops `shadowsEnd` from exceeding `highlightsStart`, and the result is a
crossfade region rather than an error.

## ColorCurves

Eight `TextureCurveParameter`s. `master`, `red`, `green` and `blue` default to the linear ramp
(0,0)→(1,1); `hueVsHue`, `hueVsSat`, `satVsSat` and `lumVsSat` default empty and read as neutral
at 0.5. Curves are the one component here with no scalar to set — build the curve, do not
attempt to poke a number into it.

## ChannelMixer

Nine `ClampedFloatParameter`s, every one on **−200–200**. The identity matrix is the diagonal at
100 and the rest at 0:

| | red in | green in | blue in |
|---|---|---|---|
| **red out** | `redOutRedIn` 100 | `redOutGreenIn` 0 | `redOutBlueIn` 0 |
| **green out** | `greenOutRedIn` 0 | `greenOutGreenIn` 100 | `greenOutBlueIn` 0 |
| **blue out** | `blueOutRedIn` 0 | `blueOutGreenIn` 0 | `blueOutBlueIn` 100 |

Zeroing a diagonal entry drops that output channel entirely — the failure looks like a broken
shader rather than like a grade.

## Re-running this dump

One `eval` regenerates the whole table on whatever version you are on, which is faster than
checking a single value by hand and does not leave the other fifteen components stale:

```csharp
var t = System.Type.GetType("UnityEngine.Rendering.Universal.Bloom, Unity.RenderPipelines.Universal.Runtime");
var inst = UnityEngine.ScriptableObject.CreateInstance(t);
var sb = new System.Text.StringBuilder();
foreach (var f in t.GetFields(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance))
{
    if (!typeof(UnityEngine.Rendering.VolumeParameter).IsAssignableFrom(f.FieldType)) continue;
    var pv = f.GetValue(inst);
    var pt = pv.GetType();
    var min = pt.GetField("min");  var max = pt.GetField("max");
    sb.Append(f.Name).Append(" : ").Append(pt.Name)
      .Append(" = ").Append(pt.GetProperty("value").GetValue(pv))
      .Append(min != null ? " min=" + min.GetValue(pv) : "")
      .Append(max != null ? " max=" + max.GetValue(pv) : "").Append("\n");
}
UnityEngine.Object.DestroyImmediate(inst);
return sb.ToString();
```

Swap the type name for each component in turn, or loop over the sixteen names. Reading a range
off the component is the habit; the table above is a convenience that goes stale.
