# Light modes — what each one can ever light

Part of the `unity-lighting` skill. SKILL.md §1 and §2 state the rules in a line; this file holds
the two mode settings, what each combination gives a moving character, and URP's light-count
limits.

## Two settings with nearly the same name

| Setting | Where | API | Decides |
|---|---|---|---|
| **Mode** of a light | The Light component | `Light.lightmapBakeType`: `LightmapBakeType.Realtime`, `Mixed`, `Baked` | Whether this light exists at runtime, in the bake, or both |
| **Lighting Mode** of the scene | The Lighting Settings asset → Mixed Lighting | `LightingSettings.mixedBakeMode`: `MixedLightingMode.IndirectOnly` (Baked Indirect), `Shadowmask`, `Subtractive` | What every **Mixed** light in the scene keeps realtime |

The Lighting Mode does nothing for a Realtime or a Baked light. A light's Mode does nothing until
a bake has run under it: `Light.bakingOutput` records what the last bake did, and the two
disagree as soon as the dropdown changes.

```csharp
LightBakingOutput baked = sun.bakingOutput;
// isBaked false                  -> no bake holds this light
// baked.lightmapBakeType         -> the Mode it was baked as
// baked.mixedLightingMode        -> the Lighting Mode it was baked under
```

`resources/Editor/LightingAudit.cs` prints `mode` beside `bakedAs` for every light and raises
`light-mode-changed-since-bake` when they differ.

## What each light Mode means

| | Realtime | Mixed | Baked |
|---|---|---|---|
| Direct light on static geometry | Every frame | Every frame (Baked Indirect, Shadowmask) or in the lightmap (Subtractive) | In the lightmap |
| Bounce light | None | In the lightmap and the probes | In the lightmap and the probes |
| Direct light on a moving object | Every frame | Every frame | From probes only |
| Specular highlight | Yes | Yes (not on static geometry under Subtractive) | No |
| Can move, change colour, switch off | Yes | Move no; intensity and colour change the direct part only | No — it does not exist at runtime |
| Frame cost | Full | Full for the direct part | None |
| Before any bake | Works | Renders as Realtime, no bounce | Lights nothing |

A Baked light is not a cheaper Realtime light. At runtime it is absent: the switch in the gate
room cannot turn it off, and the runner standing under it is lit only if a probe is nearby.

## What each Lighting Mode keeps realtime for a Mixed light

| | Baked Indirect | Shadowmask | Subtractive |
|---|---|---|---|
| Direct light | Realtime | Realtime | Baked on static geometry; realtime on moving objects |
| Shadows from static geometry on static geometry | Realtime shadow map, inside Shadow Distance | Baked into the shadowmask texture | Baked into the lightmap |
| Shadows from static geometry on a moving object | Realtime shadow map, inside Shadow Distance | From probe occlusion; with `ShadowmaskMode.DistanceShadowmask` a realtime shadow map inside Shadow Distance | Through light probes only |
| Shadows from a moving object on static geometry | Realtime | Realtime, merged with the shadowmask | Main directional light only, darkened to `RenderSettings.subtractiveShadowColor` |
| Shadows beyond Shadow Distance | None | Baked ones remain | Baked ones remain |
| Extra textures | None | One shadowmask per lightmap, four overlapping lights per texel | None |
| Use it for | Indoor, short view, desktop | Open view where far shadows must survive | The cheapest phone tier, one sun |

`QualitySettings.shadowmaskMode` chooses between `Shadowmask` (static casters never enter the
realtime shadow map: cheapest) and `DistanceShadowmask` (realtime shadows near, baked far). It is
a quality-tier setting, so two tiers can differ with the same bake.

Changing the Lighting Mode invalidates the bake: the shadowmask textures either exist or do not.

**The URP asset has its own switch.** Lighting → Mixed Lighting
(`UniversalRenderPipelineAsset.supportsMixedLighting`, default on). Unticked, the shadowmask and
subtractive paths are never selected and Mixed lights shade as plain realtime lights over the
lightmap. The audit reports `mixed-lighting-off`.

## Which object receives what

Gate room: walls and floor are static with Contribute GI; the runner and the sentry move.

| Light | Walls and floor | Runner, sentry | Gate (moves, so not static) |
|---|---|---|---|
| Sun through the doorway, Mixed, Shadowmask | Realtime direct, baked bounce, baked shadows | Realtime direct, probe bounce, realtime shadow cast onto the floor | Realtime direct, probe bounce |
| Ceiling strips, Baked | Fully baked | Probes only — black where no probe reaches | Probes only |
| Switch indicator, Realtime point | Realtime, no bounce | Realtime | Realtime |
| Sky (environment) | Baked into the lightmap | Ambient probe, or baked probes | Ambient probe, or baked probes |

The gate is the object that usually goes wrong: it looks static, it moves, so it must not carry
Contribute GI and it needs probes on both sides of its travel.

## How many lights URP shades

URP has **one main light** — `RenderSettings.sun` when that is an active directional light,
otherwise the brightest directional light — and **additional lights**: everything else,
including a second directional.

| Limit | Forward | Forward+ | Source |
|---|---|---|---|
| Additional lights per object | Per Object Limit on the URP asset: `maxAdditionalLightsCount`, default 4, clamped to `UniversalRenderPipeline.maxPerObjectLights` = 8 | No per-object limit; the asset field is ignored | URP asset → Lighting → Additional Lights |
| Additional lights visible per camera | `UniversalRenderPipeline.maxVisibleAdditionalLights`: 16 on OpenGL ES 3.0, 32 on other mobile, OpenGL Core and WebGPU, 256 on desktop | Same number | Compiled into the shaders |
| Additional lights per vertex | `LightRenderingMode.PerVertex` available; no shadows from them | Per pixel only | `additionalLightsRenderingMode` |
| Reflection probes blended | 2 per object | Per pixel from the probe atlas, when Probe Atlas Blending is on | `reference/probes.md` |

The rendering path is on the renderer asset, not the URP asset: Universal Renderer Data →
Rendering Path (`UniversalRendererData.renderingMode`: `RenderingMode.Forward`, `ForwardPlus`,
`Deferred`, `DeferredPlus`). The audit prints it as `pipeline.renderingMode` with
`perObjectLimitApplies`.

**A fifth light that flickers is the per-object limit.** Under Forward the lights affecting one
renderer are sorted per object, and the list is cut at the limit; a long floor mesh touched by
six point lights drops two, and which two changes as the camera moves. Fix in this order:

1. Bake the lights that never change (Mode Baked): they cost nothing and leave the list.
2. Split the long mesh, so each piece is touched by fewer lights.
3. Raise Per Object Limit, to 8 at most.
4. Switch the renderer to Forward+.

A light also skips an object when the light's Culling Mask excludes the object's layer, or when
the light's Rendering Layers and the renderer's Rendering Layer Mask share no bit.

## Checks

- Count what the audit calls `mode: Mixed` with `bakedAs: not-baked`: each one is rendering as
  a Realtime light.
- Before committing to a Lighting Mode, walk the runner into a static wall's baked shadow in
  the Game view, inside and beyond Shadow Distance, and compare what it receives with the table
  above.
- Read the per-object count in `Window → Analysis → Rendering Debugger → Lighting`, with the
  lighting debug mode that isolates additional lights.
- Read `pipeline.maxVisibleAdditionalLights` from the audit on the build target, not on the
  desktop: the Editor reports the desktop number until the platform is switched.

## Related skills

Probes for the runner and the gate: `reference/probes.md`. Shadow settings for the realtime
part: `reference/shadows.md`. Lights for sprites are `unity-2d-rendering` →
`reference/lights-2d.md`. What a light costs per frame is measured with `unity-profiling`.
