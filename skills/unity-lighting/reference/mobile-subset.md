# The mobile subset — a starting set for a phone

Part of the `unity-lighting` skill. SKILL.md §6 states the rules in a line; this file is the
whole set, the reasons a phone build differs from the Editor, and the order to cut in.

On a phone the frame pays for every realtime light per pixel and every shadow caster once per
cascade. The subset moves everything that does not change into the bake and keeps exactly one
light alive.

## The set

| Area | Setting | Value |
|---|---|---|
| Lights | Directional | One, Mode **Mixed**, assigned as Sun Source |
| | Every other light that never changes | Mode **Baked** |
| | Realtime point and spot lights | Two at most in view, no shadows, a short Range |
| Lighting Settings | Lighting Mode | **Shadowmask** where far shadows matter; **Subtractive** for the lowest tier |
| | Lightmap Resolution | 20 texels per unit, Max Lightmap Size 1024 |
| | Directional Mode | Non-Directional: half the lightmap memory |
| Quality | `QualitySettings.shadowmaskMode` | `ShadowmaskMode.Shadowmask`: static casters stay out of the shadow map |
| URP asset — lights | Main Light | Per Pixel, Cast Shadows on |
| | Additional Lights | Per Pixel, Per Object Limit 2 — or Per Vertex on the lowest tier |
| | Additional Lights → Cast Shadows | **Off** |
| | Mixed Lighting | On |
| URP asset — shadows | Max Distance | 25 to 40 |
| | Cascade Count | 1; 2 for a third-person camera that sees the horizon |
| | Main Light Shadow Resolution | 1024; 2048 with two cascades |
| | Soft Shadows | Off, or on at quality Low |
| URP asset — probes | Light Probe System | Light Probe Groups |
| | Reflection Probes | Baked only; Probe Blending off; Box Projection on only for an interior the camera rests in |
| Renderer | Rendering Path | Forward. Forward+ when the level needs more than a handful of realtime lights |
| | Screen Space Shadows feature | Not added |
| Static geometry | Everything that never moves | Contribute GI; Receive GI Lightmaps for large surfaces, Light Probes for props |
| Moving objects | The runner, sentries, pickups, the gate | Light probes, with one anchor per character |
| Environment | Reflection resolution | 128 |
| | Fog | Linear, ending before the far clip plane; Fog Modes set to Custom in Graphics settings if code switches it |

From script, the writable half:

```csharp
var urp = (UniversalRenderPipelineAsset)GraphicsSettings.currentRenderPipeline;
urp.shadowDistance = 30f;
urp.shadowCascadeCount = 1;
urp.mainLightShadowmapResolution = 1024;
urp.maxAdditionalLightsCount = 2;
QualitySettings.shadowmaskMode = ShadowmaskMode.Shadowmask;
```

The `supports…` switches, the light rendering modes and the reflection-probe toggles are
get-only; set them in the inspector of the asset the mobile tier uses.

## Shadowmask or Subtractive

| | Shadowmask | Subtractive |
|---|---|---|
| Static geometry lit by the sun | Realtime direct, with specular | Baked, no specular |
| The runner's shadow on the ground | Realtime, blended with the baked shadows | Realtime, darkened to one flat colour |
| The sun can change intensity or colour | Yes, for the direct part | No — it is in the lightmap |
| Extra memory | One shadowmask texture per lightmap | None |
| Realtime light cost on static pixels | One light | None |

Take Shadowmask unless the lowest device in the matrix cannot hold it. Subtractive's runner
shadow is `RenderSettings.subtractiveShadowColor` multiplied over the lightmap: set it to the
colour of a baked shadow on the same floor, or the runner's shadow reads as a different
material.

## Why the phone differs from the Editor

Work down. First match wins.

1. **A different quality tier is in force.** `Project Settings → Quality` maps each platform to
   a default tier, and each tier can name its own URP asset. The Editor shows the tier selected
   in that window; the phone boots into its platform default. Read which asset the Android or
   iOS tier names — `unity-render-urp` → `reference/resolve-active-pipeline.md` — and run the
   audit with that tier selected.
2. **The light limit is lower.** `UniversalRenderPipeline.maxVisibleAdditionalLights` is 32 on
   mobile graphics APIs and 16 on OpenGL ES 3.0, against 256 on desktop. Lights past the limit
   are not shaded.
3. **Shader variants were stripped.** The URP asset and its renderers decide which lighting
   variants reach the build: a feature that is off on every asset in the build is compiled out.
   Additional-light shadows that only the desktop tier's asset enables, soft shadows switched on
   at runtime, fog enabled from script — each works in the Editor and is missing in the player.
   Turn the feature on in an asset that the build includes.
4. **Lightmaps are compressed differently.** Blotchy or banded baked lighting on device only is
   the lightmap texture format: set the Lighting Settings asset's Lightmap Compression to High
   Quality, or lower it knowingly for memory.
5. **HDR is off on the mobile asset.** Baked and realtime light above 1 clips to white; emissive
   surfaces stop blooming. That is the URP asset's HDR switch and the post-processing chain —
   `unity-render-urp`.
6. **Soft shadows fall back.** On the lowest tiers a Soft light with Soft Shadows off on the
   asset renders hard. That is the configuration, not a device fault.
7. **The lighting data is not in the build.** The scene was baked, not saved, and built from
   CI's checkout: no `LightingData.asset` reference in the scene file. Check the scene text for
   `m_LightingDataAsset: {fileID: 0}`.

## The order to cut in

When the frame is over budget and lighting is suspected, measure first — a 90-frame window
before and after each cut, in the same situation, with `unity-profiling` →
`reference/frame-windows.md`. Then cut in this order; each step is cheaper to undo than the one
after it.

| # | Cut | Saves | Loses |
|---|---|---|---|
| 1 | Shadows off on every additional light | A shadow atlas and its passes | Almost nothing a player reads |
| 2 | Max Distance down to 25; one cascade | Casters per shadow pass, passes | Far shadows — bake them with Shadowmask |
| 3 | Realtime lights to Baked, or to a Per Object Limit of 2 | Per-pixel light loops | Lights that switch or move |
| 4 | Soft Shadows off | Shadow samples per pixel | Edge quality |
| 5 | Main shadow resolution 2048 → 1024 | Shadow fill and memory | Edge sharpness |
| 6 | Realtime reflection probes to Baked; Probe Blending off | Scene renders; a second cubemap sample | Reflections of moving things |
| 7 | Shadowmask → Subtractive | A realtime light on every static pixel | Specular and a changeable sun |
| 8 | The runner's shadow to a blob quad; main light shadows off | The whole shadow pass | Everything but the grounding cue |

What is left after step 3 is rarely lighting. Draw calls, overdraw, LOD and culling distances
are `unity-scene-optimisation` → `reference/batching.md` and `unity-scene-optimisation` →
`reference/culling-distances.md`;
full-screen post-processing is `unity-render-urp`.

## Worked example — the gate room on a phone

Situation id gate-room. The runner walks 12 units from the door to the switch; the gate opens;
a sentry watches from the far wall.

- Sun through the doorway: Mixed, Sun Source, Soft off. Six ceiling strips: Baked. The switch's
  indicator: Realtime point, Range 2, no shadows.
- Lighting Mode Shadowmask, resolution 20, one 1024 lightmap and its shadowmask.
- Walls, floor and ceiling contribute GI and receive lightmaps; pipes and the switch housing
  contribute and receive probes; the gate, the runner, the body under `SentryBrain` and the pickups
  do not contribute.
- 32 light probes in two layers, with pairs either side of the doorway's sun patch and either
  side of the gate.
- One Baked reflection probe, box matched to the room, resolution 128.
- URP asset for the mobile tier: Max Distance 25, one cascade, 1024, additional shadows off,
  Per Object Limit 2.

The audit on that scene reports `"ok":true`, `bake.lightmaps` 1, `bake.shadowMask` true,
`probes.baked` 32, and every Mixed or Baked light with `bakedAs` equal to `mode`.

## Related skills

Each setting in depth: `reference/light-modes.md`, `reference/bake-setup.md`,
`reference/probes.md`, `reference/shadows.md`. Running the build on the phone and reading its
log is `unity-device-testing`; the Android artifact and its stripping settings are
`unity-android-release`. Measuring each cut is `unity-profiling`; the cuts that are not lighting
are `unity-scene-optimisation`.
