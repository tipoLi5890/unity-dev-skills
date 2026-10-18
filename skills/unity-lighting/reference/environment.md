# Environment — the light that comes from no Light

Part of the `unity-lighting` skill. SKILL.md §5 states the rules in a line; this file holds the
`RenderSettings` fields, the sun source, fog and the checklist for a scene that looks unlit.

Every lit surface receives two things no Light component provides: **ambient light** (diffuse,
from the sky) and the **environment reflection** (specular, from the sky). Both are scene
state, both are set in `Window → Rendering → Lighting → Environment`, both are in
`RenderSettings`, and both are **baked data** — changing the skybox changes neither until
lighting is generated again.

## The fields

| Lighting window | `RenderSettings` | Default in a new scene | Notes |
|---|---|---|---|
| Skybox Material | `skybox` | The procedural default sky | What the camera draws behind everything, and the source of the two rows below |
| Sun Source | `sun` | None | The directional light the procedural sky draws its disc for — and URP's main light |
| Environment Lighting → Source | `ambientMode` | `AmbientMode.Skybox` | `Skybox`, `Trilight` (Gradient), `Flat` (Color) |
| → Intensity Multiplier | `ambientIntensity` | 1 | For the Skybox source |
| → Colours | `ambientLight` / `ambientSkyColor`, `ambientEquatorColor`, `ambientGroundColor` | — | For Flat and Trilight |
| Environment Reflections → Source | `defaultReflectionMode` | `DefaultReflectionMode.Skybox` | `Custom` reads `customReflectionTexture` |
| → Resolution | `defaultReflectionResolution` | 128 | Of the sky cubemap |
| → Intensity Multiplier | `reflectionIntensity` | 1 | 0 turns every smooth surface black outside a probe |
| → Bounces | `reflectionBounces` | 1 | Reflections of reflections between baked probes |
| Realtime Shadow Color | `subtractiveShadowColor` | — | Subtractive Lighting Mode only |

`resources/Editor/LightingAudit.cs` prints all of them under `environment`.

## Ambient is baked

The ambient term a renderer reads is a probe (`RenderSettings.ambientProbe`) computed from the
sky. It is refreshed by Generate Lighting, and it is stored with the scene's lighting data.

- **New skybox, same lighting**: generate lighting. Until then the scene is lit by the old sky.
- **A scene that was never baked** uses the default lighting data — the default sky's ambient,
  whatever skybox is assigned.
- **A sky that changes at runtime** (a day cycle, a switch from outdoors to a tunnel): call
  `DynamicGI.UpdateEnvironment()` after changing `RenderSettings.skybox` or the sun, at most
  once every few seconds — it recomputes the probe.
- **An interior**: sky ambient lights a sealed room as if it had no roof. Use
  `AmbientMode.Flat` with a dark colour (`ambientLight` around 0.05 grey) and let baked bounce
  and probes carry the room, or keep Skybox and lower `ambientIntensity`.
- **Additively loaded scenes**: environment settings come from the **active** scene
  (`SceneManager.SetActiveScene`). A gate room loaded additively under a bootstrap scene is lit
  by the bootstrap scene's sky until it is made active.

## The sun source

URP's main light is chosen each frame: `RenderSettings.sun` when it is a visible directional
light, otherwise the brightest directional light. Only the main light gets cascaded shadows; any
other directional is an additional light and casts none.

- One directional light: leave Sun Source empty or assign it; the result is the same.
- Two directional lights (a sun and a fill): assign the sun. Otherwise raising the fill's
  intensity past the sun's swaps them, and the shadows jump to the fill.
- No directional light and `mainLightRenderingMode` `PerPixel`: there is no main light; the
  scene is lit by ambient, probes and additional lights only.

## Fog

`RenderSettings.fog` with `fogMode`:

| `FogMode` | Controlled by | Reads as |
|---|---|---|
| `Linear` | `fogStartDistance`, `fogEndDistance` | A wall of fog at a known distance. Predictable; the one to hide a far clip plane |
| `Exponential` | `fogDensity` | Haze that thickens smoothly |
| `ExponentialSquared` | `fogDensity` | Clear near, dense far. The usual outdoor choice, density 0.01–0.03 |

- `fogColor` should match the sky at the horizon, or distant geometry shows a silhouette
  against it.
- Fog is applied in the material's shader. URP's own shaders and Shader Graph targets apply
  it; a hand-written shader that omits the fog step is not fogged.
- **Fog that is on in the Editor and missing in a build** is variant stripping:
  `Project Settings → Graphics → Shader Stripping → Fog Modes` on Automatic keeps only the modes
  used by scenes in the build. Fog enabled from code, or a mode switched at runtime, is
  stripped. Set Fog Modes to Custom and tick the modes the code uses.
- Fog is not volumetric: it does not light shafts and it ignores shadows.
- **Keep fog off the play area.** Linear fog with its start beyond the far edge of play (60 m and
  more for a tennis venue seen from 16 m behind the baseline) tints only the scenery. Paint a
  procedural gradient sky whose horizon colour equals `fogColor`, so the fogged hills meet the sky
  without a line. A fog particle effect ("mist over the lake") obeys the same rule: place it from
  known limits, not from the bounds of a merged water mesh; one tennis venue's two lake halves
  merged into one mesh whose bounds centre was the court, and the mist covered the match until
  the emitter was split into one system per half, starting 38 m out.

## A scene that looks unlit — the checklist

Work down. First match wins. The audit answers the rows marked A.

| # | Check | How |
|---|---|---|
| 1 | The Scene view's lighting toggle is off | The lightbulb in the Scene view toolbar. Judge in the Game view |
| 2 | The pipeline in force is not the one being edited | A — `pipeline.active`; `unity-render-urp` → `reference/resolve-active-pipeline.md` |
| 3 | The material is Unlit, or magenta | The material's shader. Magenta after a pipeline switch is `unity-urp-migration` |
| 4 | Main Light is Disabled on the URP asset | A — `pipeline.mainLight` |
| 5 | The only light is Baked and nothing was baked | A — `baked-light-never-baked` |
| 6 | The light's Culling Mask or Rendering Layers exclude the object | The Light component; the renderer's Rendering Layer Mask |
| 7 | Ambient is zero | A — `environment.ambientIntensity`, or `ambientMode` Flat with a black colour |
| 8 | The mesh has no normals, or they point inwards | Model Importer → Normals; flipped faces from a DCC export |
| 9 | Everything is lit and flat | No shadows (`reference/shadows.md`), no bounce (nothing baked), ambient too high: lower `ambientIntensity` to 0.5–0.8 before adding lights |
| 10 | It is lit and dark overall | Exposure, not lighting: post-processing Volumes are `unity-render-urp` |

A scene lit by one directional light, the default sky and no bake is flat by construction: the
sky fills every shadow with the same blue. Depth comes from baked bounce, baked ambient
occlusion and a darker ambient — not from more lights.

## Camera background

`Camera.clearFlags` — Skybox or Solid Color (URP camera → Environment → Background Type). A
solid-colour background does not change the ambient or the reflections: those still come from
`RenderSettings.skybox`. An interior with a black background and the default sky assigned still
reflects blue.

## Related skills

Probes that override the environment locally: `reference/probes.md`. The main light's shadows:
`reference/shadows.md`. Exposure, tonemapping and colour grading are `unity-render-urp`. Which
scene is active after an additive load is decided where the project loads its scenes; set it
before judging the lighting.
