---
name: unity-lighting
description: >-
  Diagnose and set up 3D lighting and global illumination on URP in Unity 6: a
  symptom ladder over light modes, the bake, probes, shadows and the
  environment, with a read-only scene audit and a bake that reads its result
  back. Load for: "the bake did nothing", "the character is black beside the
  baked walls", "reflections show the sky indoors", "shadows flicker when the
  camera turns", "stripes on lit surfaces", "shadows stop a few metres away",
  "the scene looks flat", "lighting is right in the editor and wrong on the
  phone". Lights for sprites are unity-2d-rendering; post-processing is
  unity-render-urp; a stale bake after a pipeline switch is
  unity-urp-migration; frame cost is unity-profiling.
---

# unity-lighting — a light's mode decides what it can ever light

> **Most lighting reports are not a value to tune.** "The bake did nothing" and "the character
> is black" are a light's Mode, a static flag or a missing probe: a Baked light does not exist
> at runtime, a lightmap lights only the surface it is painted on, and nothing warns when
> either leaves an object dark. Read the scene first; change one switch; read it again.

URP on Unity 6, 3D scenes. Worked example: the gate room — baked walls, one Mixed sun through
the doorway, the runner and a sentry on probes.

## Symptom → where to look

First match wins. **Stop at the first cause you confirm.**

| Symptom | Go to |
|---|---|
| Any lighting complaint, before touching a setting | §0 |
| Generate Lighting finishes and the scene looks the same | §1 |
| Lightmaps are blotchy, seamed, or black on one mesh | §1 steps 4–5 |
| The runner is black, flat or the wrong colour beside baked walls | §2 |
| A light affects the walls and not the character, or the reverse | §2 |
| A fifth light flickers or drops out as the camera moves | §2 — the per-object limit |
| Metal is black; a floor reflects the sky indoors; reflections slide | §3 |
| No shadow; stripes; a shadow detached from its caster; crawling edges | §4 |
| Shadows end a few metres from the camera | §4 — Max Distance |
| A point or spot light casts no shadow | §4 — additional-light shadows |
| Everything is lit and the scene is flat, or too dark with the lights right | §5 |
| Changing the skybox changed nothing | §5 — ambient is baked |
| Right in the Editor, wrong on the phone | §6 |
| Lighting costs too much on the phone | §6 — the order to cut in |

## 0. Read the scene before changing it

Drop `resources/Editor/LightingAudit.cs` into an Editor folder and run
`Tools/Unity Dev/Lighting/Audit Open Scene`, or `return LightingAudit.Audit();` from an eval
(`unity-debug` → `reference/editor-control.md`). It changes nothing and prints one JSON object:

| Block | Holds |
|---|---|
| `pipeline` | The URP asset in force and its tier, the renderer and its rendering path, light modes and limits, the probe system, the reflection-probe toggles, every shadow field |
| `settings` | The Lighting Settings asset (or `defaults`), lightmapper, Lighting Mode |
| `lights` | Each light's type, `mode`, `bakedAs`, shadows |
| `static` | Renderers that contribute GI, receive lightmaps or probes, lack a second UV set |
| `bake`, `probes` | Lightmap count and size, shadowmask, baked probe count, Adaptive Probe Volume state |
| `reflectionProbes`, `environment` | Each probe's mode and box projection; sky, sun, ambient, fog |
| `findings` | Named candidates: `baked-light-never-baked`, `dynamic-without-probes`, … |

- **`pipeline.active` is `not-urp`**: stop. `unity-render-urp` →
  `reference/resolve-active-pipeline.md`.
- **Judge in the Game view.** The Scene view has its own lighting toggle.
- **Each finding is a candidate.** Confirm it against the symptom before changing anything, and
  restore what you change while testing.

## 1. The bake changed nothing

A bake needs a light that asks, a renderer that contributes, a UV set and texels. Work down.

1. **No light asks.** Every light's Mode is Realtime (`Light.lightmapBakeType`). Set the lights
   that never change to Baked and the sun to Mixed.
2. **Nothing contributes.** No renderer has the **Contribute GI** static flag
   (`StaticEditorFlags.ContributeGI`): `nothing-contributes-gi`. Flag the walls and floor —
   never the gate or anything else that moves.
3. **The mode changed after the bake.** `mode` and `bakedAs` differ, or the Lighting Mode does:
   `light-mode-changed-since-bake`. A Mixed light with no bake renders as Realtime; a Baked one
   lights nothing. Bake again.
4. **Contributes, receives no texels.** Receive Global Illumination is Light Probes
   (`MeshRenderer.receiveGI`), or Scale In Lightmap is 0. Large surfaces want
   `ReceiveGI.Lightmaps`.
5. **No lightmap UVs.** `contributes-gi-without-uv2`: tick Generate Lightmap UVs on the model
   importer and Apply; a mesh built in code needs `Unwrapping.GenerateSecondaryUVSet`.
6. **Baked Global Illumination is off**, or the scene has no Lighting Settings asset and bakes
   with defaults nobody chose.
7. **It baked and was not saved.** The reference to the lighting data is scene state.

Bake with evidence: `Tools/Unity Dev/Lighting/Bake And Read Back`
(`resources/Editor/BakeAndReadBack.cs`) reports the plan, waits for confirmation, bakes
asynchronously and prints lightmap count, probe count and bake time before and after.
`"status":"baked-empty"` means it ran and wrote nothing, with the missing input in `detail`. A
GPU bake needs a graphics device: under `-nographics` the CPU lightmapper is the path, and the
report says which ran.

Settings assets, UV failures, texel density, a draft and a final pair, batch baking:
[`reference/bake-setup.md`](reference/bake-setup.md).

## 2. Dynamic objects are black or unlit beside baked ones

| The runner is | Cause |
|---|---|
| Black or flat everywhere | No baked probes: `dynamic-without-probes`. A lightmap lights only its own surface |
| Right at spawn, wrong by the gate | No probe pair at the lighting change |
| Unlit by one particular light | That light is Baked. Make it Mixed, or accept probes |
| Lit differently per body part | Several renderers, several sample points: one Anchor Override (`Renderer.probeAnchor`) |
| One flat colour along a long moving object | One sample per renderer. Adaptive Probe Volumes sample per pixel; URP has no proxy volume |
| Unlit, with Light Probe Groups in the scene | The URP asset's Light Probe System is Adaptive Probe Volumes: `probe-groups-ignored` |

- **Light Probe Groups**: two layers (0.3 and 2.0 above the floor), every 2–3 units where things
  move, a pair either side of every lighting change, none inside geometry. Read
  `LightmapSettings.lightProbes.count` after the bake.
- **Mixed lights follow the Lighting Mode** (`LightingSettings.mixedBakeMode`): Baked Indirect
  keeps direct light and shadows realtime; Shadowmask bakes static shadows; Subtractive bakes
  direct light too and keeps one sun's shadow. Mixed Lighting must also be ticked on the URP
  asset (`mixed-lighting-off`).
- **A light that drops out** is Forward's Per Object Limit — 4 by default, 8 at most, plus the
  main light. Bake the lights that never change, split the long mesh, raise the limit, or move
  the renderer to Forward+, which has none.

Modes, the receive table and the limits: [`reference/light-modes.md`](reference/light-modes.md).
Placement, anchors and Adaptive Probe Volumes: [`reference/probes.md`](reference/probes.md).

## 3. Reflections are wrong or missing

1. **No probe encloses the object**: it reflects the environment — the sky, indoors. Add one
   Baked Reflection Probe per room, its box matched to the walls.
2. **The probe baked a cubemap of sky**: a Baked probe captures only objects with the
   Reflection Probe Static flag. `baked-probe-without-texture` is one never baked at all.
3. **Reflections slide with the camera**: Box Projection is ticked on the probe and off on the
   URP asset (`box-projection-off-in-asset`). Lighting → Reflection Probes on the asset.
4. **Reflections pop at a doorway**: Probe Blending is off on the asset
   (`probe-blending-off-in-asset`); Forward blends two probes per object.
5. **Metal is black everywhere**: the environment reflection is empty
   (`no-environment-reflection`) — §5.
6. **A Realtime probe costs a frame**: `EveryFrame` renders the scene six more times. Use
   `ViaScripting` and `RenderProbe()` when the gate finishes opening.

Modes, the asset's three toggles, sizing and blending: [`reference/probes.md`](reference/probes.md).

## 4. Shadows

Realtime shadows are one texture stretched over Max Distance. Settings live on the URP asset the
active tier uses, not in Quality settings.

| You see | Cause | First move |
|---|---|---|
| No shadow | A switch | The eight-step list in the reference: light type and mode, the asset, distance, the renderer, the material, the camera |
| Stripes on lit surfaces (acne) | Bias under one texel | Normal Bias 1 → 1.5, then Depth Bias |
| Shadow detached from the feet | Bias too high | Depth Bias 1 → 0.5; give thin casters thickness |
| Edges crawl when the camera turns | Texels too large | Max Distance down (default 50), then a cascade, then resolution |
| Shadows end at a distance | Max Distance, faded by Last Border | Raise it, or bake far shadows with Shadowmask |
| A point or spot light casts none | Additional Lights → Cast Shadows is off by default | `additional-shadows-off`; Per Pixel or Forward+ as well |
| The far player has no shadow under a fixed long view; split screen doubles the shadow cost | Distance too short for the view; one shadow map per camera | Per-tier table in the reference, "A long fixed view" |
| A second directional casts none | Only the main light has cascades | Assign the sun as Sun Source |

All point and spot shadows share one atlas (2048); a point light takes six slices. When they do
not fit URP shrinks them and logs it — read the Console before raising anything.

Every field with its default, per-light settings, the atlas, the Screen Space Shadows feature and
the artefact table: [`reference/shadows.md`](reference/shadows.md).

## 5. Flat or too dark with no light wrong

Ambient light and the environment reflection come from the sky, are scene state in
`RenderSettings`, and are **baked**: a new skybox changes neither until lighting is generated.

- **Flat**: sky ambient fills every shadow. Lower `RenderSettings.ambientIntensity` to 0.5–0.8,
  bake bounce light, turn shadows on — before adding lights.
- **An interior lit like outdoors**: `AmbientMode.Flat` with a dark colour; let the bake and the
  probes carry the room.
- **Too dark with lights present**: the only light is Baked and unbaked; Main Light is Disabled
  on the asset; the light's Culling Mask or Rendering Layers exclude the object.
- **A runtime sky change**: `DynamicGI.UpdateEnvironment()` afterwards.
- **An additively loaded room** takes its environment from the active scene.
- **Dark overall with correct lighting** is exposure — `unity-render-urp`.

Every field, the sun source, fog and the ten-row checklist:
[`reference/environment.md`](reference/environment.md).

## 6. Fine in the Editor, wrong on the phone

1. **Another tier, another URP asset.** The phone boots into its platform's default quality
   tier. Select that tier and run the audit again.
2. **A lower light limit**: 32 visible additional lights on mobile, 16 on OpenGL ES 3.0, 256
   on desktop.
3. **Stripped variants**: a feature off on every URP asset in the build — soft shadows,
   additional shadows, a fog mode enabled from code — is compiled out.
4. **Lightmap compression** blotches baked light on device only.
5. **The lighting data never reached the build**: baked, not saved.

Start a phone from: one Mixed directional, Shadowmask (Subtractive on the lowest tier), Max
Distance 25–40 with one cascade, everything static baked, probes for the runner, no additional
shadows. When over budget, cut additional shadows, then distance and cascades, then realtime
lights — measuring each cut with `unity-profiling`.

The whole set, the cut order and a worked gate room:
[`reference/mobile-subset.md`](reference/mobile-subset.md).

## Scope — what this skill does NOT do

Lights, shadows and normal maps for sprites are `unity-2d-rendering`. Post-processing Volumes,
exposure, tonemapping, renderer features and whether URP is the pipeline in force are
`unity-render-urp`; moving a Built-in project to URP and the stale bake it leaves behind are
`unity-urp-migration`. HDRP is out. Shader authoring is out. Measuring what a light or a shadow
pass costs is `unity-profiling`; LOD, occlusion, batching and culling distances are
`unity-scene-optimisation`. Building the room — kits, collision proxies, terrain — is
`unity-3d-level`; importing and decimating its meshes is `unity-3d-models`. Reading the result
on a real device is `unity-device-testing`.
