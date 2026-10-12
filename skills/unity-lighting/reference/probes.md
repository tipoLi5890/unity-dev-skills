# Probes — how anything that moves is lit

Part of the `unity-lighting` skill. SKILL.md §2 and §3 state the rules in a line; this file holds
Light Probe Groups, Adaptive Probe Volumes and Reflection Probes in full.

A lightmap lights the surface it is painted on and nothing else. Everything without lightmap
texels — the runner, the sentry, the gate, a pickup, a small static prop — reads baked light from
**light probes**, and reads its reflections from **reflection probes**. Two systems, two bakes,
two sets of mistakes.

## Light probes: pick one system

The URP asset chooses, under Lighting → Light Probe System
(`UniversalRenderPipelineAsset.lightProbeSystem`):

| | Light Probe Groups (`LightProbeSystem.LegacyLightProbes`) | Adaptive Probe Volumes (`LightProbeSystem.ProbeVolumes`) |
|---|---|---|
| Probes are placed | By hand, in `LightProbeGroup` components | Automatically, inside `ProbeVolume` boxes, denser near geometry |
| An object samples | One interpolated value for the whole renderer | Per pixel (or per vertex) |
| A long or large moving object | One colour end to end | Lit correctly along its length |
| Runtime cost | Lowest | Volume textures in memory; a sample per pixel |
| Baked count is read from | `LightmapSettings.lightProbes.count` | The baking set — the audit's `probes.apv` block |
| Choose for | Phones, small rooms, a handful of moving objects | Desktop and console, large or many scenes, big dynamic objects |

They do not mix. With Adaptive Probe Volumes selected, Light Probe Groups in the scene are not
sampled (`probe-groups-ignored`); with Light Probe Groups selected, a Probe Volume does nothing
(`probe-volume-ignored`). URP has no Light Probe Proxy Volume: `LightProbeUsage.UseProxyVolume`
on a renderer has no effect, and a large moving object under Light Probe Groups is the reason to
move to Adaptive Probe Volumes.

## Light Probe Groups

`GameObject → Light → Light Probe Group`. The group's `probePositions` are local to its
Transform; the bake turns all groups into one tetrahedral mesh.

Placement, for the gate room:

- **Two layers, always.** One at 0.3 above the floor, one at 2.0 — above the runner's head. A
  single flat layer makes no volume, and the runner is lit from below.
- **Along where things move**, every 2 to 3 units: the corridor, the switch, both sides of the
  gate's travel.
- **Either side of every lighting change**: 0.5 inside and 0.5 outside the doorway's sun patch,
  either side of a shadow edge, either side of a coloured light. A probe pair is how a boundary
  gets sharp; a single probe in the middle of it averages both sides.
- **Never inside geometry.** A probe in a wall bakes black and drags its neighbours down. Keep
  probes 0.2 off every surface.
- **Enclose the playable volume.** A runner outside the outermost probes is extrapolated from
  the nearest face, which is usually wrong.

Twenty to forty probes light a gate room. Counts in the thousands are a sign the scene wanted
Adaptive Probe Volumes.

What a renderer does with them:

| `Renderer.lightProbeUsage` | Result |
|---|---|
| `LightProbeUsage.BlendProbes` | Interpolates at the anchor point. The default |
| `LightProbeUsage.Off` | The ambient probe only |
| `LightProbeUsage.CustomProvided` | Code supplies the values through a `MaterialPropertyBlock` |

The sample point is the centre of the renderer's bounds, or `Renderer.probeAnchor` when set
(Mesh Renderer → Probes → Anchor Override). Set an anchor when:

- **A character is made of several renderers** — body, visor, pack — and each one samples a
  different point, so the parts disagree across a shadow edge. Point all of them at one
  Transform at chest height.
- **The bounds centre is inside something**: a sentry whose base sits in the floor.

The anchor also picks the reflection probe.

## Adaptive Probe Volumes

1. URP asset → Lighting → Light Probe System → **Adaptive Probe Volumes**. The public property is
   get-only; from script the field is `m_LightProbeSystem` through `SerializedObject`. Do this
   on every URP asset a quality tier uses.
2. `GameObject → Light → Adaptive Probe Volume`. The component is `ProbeVolume`
   (`UnityEngine.Rendering`); its `mode` is `ProbeVolume.Mode.Local` (a box you size),
   `Scene` (fits the scene's renderers) or `Global` (fits every scene of the baking set). Start
   with one volume in `Scene` mode.
3. `Window → Rendering → Lighting → Adaptive Probe Volumes`. A scene belongs to exactly one
   **baking set** (`ProbeVolumeBakingSet`); scenes that load together belong to the same one.
   `minDistanceBetweenProbes` (1 in a new set) is the densest spacing, `simplificationLevels`
   (3) how far it coarsens away from geometry.
4. Generate Lighting bakes lightmaps and the volumes together. Probes alone:
   `AdaptiveProbeVolumes.BakeAsync()`, polled with `AdaptiveProbeVolumes.isRunning`.
5. Read it back: the audit's `probes.apv` — `enabledOnAsset`, `volumes`, `bakingSet`,
   `hasBakedData`, `loaded`.

Only geometry with Contribute GI attracts probes. Light leaking through a thin wall is fixed
with a `Probe Adjustment Volume` (`GameObject → Light → Probe Adjustment Volume`) or a thicker
wall, not with more probes.

## Reflection probes

A smooth or metallic surface shows the nearest reflection probe's cubemap; outside every probe
it shows the environment reflection (`reference/environment.md`). A room with no probe reflects
the sky through its ceiling.

| `ReflectionProbe.mode` | Captures | Cost | Use |
|---|---|---|---|
| `ReflectionProbeMode.Baked` | Objects with the Reflection Probe Static flag, at bake time | A cubemap in memory | Every room. The default answer |
| `ReflectionProbeMode.Realtime` | Everything, per `refreshMode` | Six scene renders per refresh | One hero surface, on desktop |
| `ReflectionProbeMode.Custom` | The cubemap you assign | A cubemap in memory | A hand-made or shared cubemap |

- A Baked probe sees only `StaticEditorFlags.ReflectionProbeStatic` objects. A room whose walls
  lack the flag bakes a cubemap of sky.
- A Realtime probe with `ReflectionProbeRefreshMode.EveryFrame` renders the scene six more times
  a frame. Use `ViaScripting` and call `RenderProbe()` when the gate finishes opening;
  `timeSlicingMode = ReflectionProbeTimeSlicingMode.IndividualFaces` spreads a refresh over
  frames.
- Rebaking probes alone: the Lighting window's Generate Lighting dropdown → Bake Reflection
  Probes. The evidence that it ran is the probe `.exr` files' write time —
  `unity-urp-migration` → `reference/lighting-and-probes.md`.

### The three switches on the URP asset

Lighting → Reflection Probes. All three are get-only in script; the serialised fields are
`m_ReflectionProbeBlending`, `m_ReflectionProbeBoxProjection` and `m_ReflectionProbeAtlas`.

| Toggle | Property | Off means |
|---|---|---|
| Probe Blending | `reflectionProbeBlending` | Each renderer uses one probe; reflections pop when it crosses a boundary |
| Box Projection | `reflectionProbeBoxProjection` | Every probe reflects as if its walls were infinitely far: the reflection slides with the camera. The probe's own Box Projection tick is ignored |
| Probe Atlas Blending | `reflectionProbeAtlas` | Forward+ falls back to two probes per object. Needs Probe Blending on as well; Deferred+ uses the atlas whatever this says |

The first two are off in an asset created from code and may be on in one created from a
template; Probe Atlas Blending is on by default. Read them — the audit prints all three and
raises `box-projection-off-in-asset` and `probe-blending-off-in-asset`. With the GPU Resident
Drawer on, URP forces probe blending and the atlas on whatever the toggles say.

Under Forward a renderer blends at most two probes, chosen per object at its anchor. Under
Forward+ with Probe Blending and Probe Atlas Blending both on, probes are chosen per pixel from
the atlas, so a long floor crossing three rooms reflects each room correctly.

### Sizing a probe

- **One probe per room, its box matching the room's inner walls**, with Box Projection on. Box
  projection assumes the reflected surfaces lie on the box; a box that is larger than the room
  slides, one that is smaller cuts the reflection off.
- **`blendDistance` 1** where two rooms meet, with the boxes overlapping by that much.
- **`importance`** breaks ties: the small probe around the switch alcove gets 2, the room
  keeps 1.
- **`resolution` 128** for a room, 256 for the one surface the camera rests on. Each step up is
  four times the memory.
- Place the probe's origin at head height in the middle of the room, not on the floor and not
  inside the gate.

## Checks

- `LightmapSettings.lightProbes` is null or `count` 0 after a bake with groups in the scene: the
  groups are disabled, or the asset is on Adaptive Probe Volumes.
- The runner is correctly lit at spawn and wrong by the gate: there is no probe pair at the
  gate. Select the runner in the Scene view — the tetrahedron it samples is drawn.
- A reflection shows the sky indoors: no probe encloses the anchor, or the probe was baked
  before the walls had the Reflection Probe Static flag.

## Related skills

Modes that decide what a probe stores: `reference/light-modes.md`. The environment reflection
behind every probe: `reference/environment.md`. A character made of several renderers is
`unity-rigged-character`. Memory taken by cubemaps and volume textures is measured with
`unity-profiling`.
