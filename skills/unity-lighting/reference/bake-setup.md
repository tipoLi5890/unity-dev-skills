# Bake set-up — what must be true before Generate Lighting writes anything

Part of the `unity-lighting` skill. SKILL.md §1 is the ladder; this file is each rung in full.

A bake needs four things at once: a light that asks to be baked, a renderer that contributes, a
UV set to write into, and enough texels to show the result. Missing any one, the bake finishes
without an error and the scene looks the same.

## 1. The Lighting Settings asset

`Window → Rendering → Lighting → Scene → Lighting Settings`. The asset is a `LightingSettings`
(`.lighting`), and **the reference to it is scene state**: assigning it and saving assets does
not save the scene. With none assigned the scene bakes with the project defaults
(`Lightmapping.lightingSettingsDefaults`), which nobody chose.

```csharp
// The plain getter throws when the scene has no asset; this one does not.
if (!Lightmapping.TryGetLightingSettings(out LightingSettings settings))
    settings = Lightmapping.lightingSettingsDefaults;
```

Creating one and making the scene keep it — the save order and the read-back from the scene
file — is `unity-urp-migration` → `reference/lighting-and-probes.md`.

Unity 6 has no Auto Generate. Nothing bakes until someone presses Generate Lighting or code
calls the API, and a scene that was never baked renders with the default environment data.

## 2. The lightmapper

`LightingSettings.lightmapper`:

| Value | Needs | Use |
|---|---|---|
| `LightingSettings.Lightmapper.ProgressiveGPU` | A graphics device with compute support and enough video memory | Iteration on a workstation |
| `LightingSettings.Lightmapper.ProgressiveCPU` | Nothing | CI, `-nographics` batch mode, a result that does not depend on the machine's GPU |

Under `-batchmode -nographics` there is no graphics device
(`SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null`), so the CPU lightmapper is the
path. `resources/Editor/BakeAndReadBack.cs` bakes with it for that run and reports `requested`
and `ran`.

## 3. Who contributes and who receives

Two settings on every static mesh, and they are not the same question.

| Setting | API | Meaning |
|---|---|---|
| Static → Contribute GI | `StaticEditorFlags.ContributeGI` | The mesh takes part in the bake: it blocks, bounces and (if emissive) emits |
| Mesh Renderer → Lighting → Receive Global Illumination | `MeshRenderer.receiveGI`: `ReceiveGI.Lightmaps` or `ReceiveGI.LightProbes` | Where its own lighting comes from |

| Contribute GI | Receive GI | Result |
|---|---|---|
| On | Lightmaps | Gets texels in a lightmap. Needs a second UV set and a Scale In Lightmap above 0 |
| On | Light Probes | Blocks and bounces light, is lit from probes. For small or detailed static props: no UVs, no texels |
| Off | — | Invisible to the bake; lit from probes. Everything that moves |

Rules of thumb for the gate room: walls, floor and ceiling → Lightmaps. Pipes, railings, the
switch housing → Light Probes. The gate, the runner, the sentry, the pickups → Contribute GI off.

The Static dropdown's "Everything" also sets batching, occlusion and navigation flags. For
lighting, set Contribute GI alone and let `unity-scene-optimisation` and `unity-navigation`
decide the rest.

```csharp
GameObjectUtility.SetStaticEditorFlags(wall, GameObjectUtility.GetStaticEditorFlags(wall) | StaticEditorFlags.ContributeGI);
wall.GetComponent<MeshRenderer>().receiveGI = ReceiveGI.Lightmaps;
```

## 4. Lightmap UVs

Lightmaps are written through the mesh's second UV set (`Mesh.uv2`,
`VertexAttribute.TexCoord1`). With no second set the bake falls back to the first, which is
right only when the first has no overlap, no mirroring and stays inside 0–1 — rare on a model
textured from a tiling material.

| Mesh comes from | Get a second UV set by |
|---|---|
| A model file | Model Importer → Model → Generate Lightmap UVs (`ModelImporter.generateSecondaryUV`), then Apply |
| ProBuilder | With the Auto Lightmap UVs preference on, a mesh with Contribute GI gets them when it is optimised; otherwise the ProBuilder Mesh inspector shows "Lightmap UVs are missing" with a Generate Lightmap UVs button |
| Code | `Unwrapping.GenerateSecondaryUVSet(mesh)` in the Editor, before saving the mesh asset |
| A DCC tool | Author UV2 there; leave Generate Lightmap UVs off so the import does not replace it |

When Generate Lightmap UVs is on and the result is still wrong:

- **Seams of light or dark along hard edges**: widen the margin between charts. With Margin
  Method Calculate (`ModelImporterSecondaryUVMarginMethod.Calculate`), set Min Lightmap
  Resolution (`secondaryUVMinLightmapResolution`) to the lowest texels per unit the mesh is baked
  at — Lightmap Resolution × its smallest Scale In Lightmap; with Manual, raise Pack Margin
  (`secondaryUVPackMargin`) from 4 to 8. Then turn on Stitch Seams
  (`MeshRenderer.stitchLightmapSeams`).
- **Charts that bleed into each other**: the mesh gets too few texels for the margin; raise its
  Scale In Lightmap or the scene's Lightmap Resolution.
- **A mesh made of thousands of islands**: an unwelded or photogrammetry-dense mesh. Weld and
  decimate it first — `unity-3d-models`.
- **Nothing changed after ticking the box**: the scene uses a mesh copy saved before the
  reimport, or a combined mesh. Read the audit's `contributes-gi-without-uv2` list.

`resources/Editor/LightingAudit.cs` lists every renderer with Contribute GI and Receive GI
Lightmaps whose mesh has no second UV set, with the importer's setting beside it.

## 5. Texel density

`LightingSettings.lightmapResolution` is texels per world unit for the whole scene (40 in a new
asset). `MeshRenderer.scaleInLightmap` multiplies it per renderer. Texels are the bake's time,
its memory and its file size, and they grow with the square of the number.

| Surface | Scale In Lightmap |
|---|---|
| Floor and walls the runner stands next to | 1 |
| Ceiling, high walls | 0.5 |
| Geometry never seen closer than 20 units | 0.25 |
| Small props | Receive GI → Light Probes instead |
| 0 | No texels at all: the renderer bakes black. The audit reports `scale-in-lightmap-zero` |

Budget from the output, not the input: bake, read `bake.lightmaps` and `bake.largest` from the
audit, and halve the resolution until the count fits. One 1024 lightmap for a gate room is
plenty; four 2048 ones on a phone are not. Look at the result in the Scene view's Baked Lightmap
draw mode, where the checker shows one texel per square.

## 6. A draft pair and a final pair

Keep two Lighting Settings assets and swap the reference; never edit one back and forth.

| Field | `GateRoom-Draft.lighting` | `GateRoom-Final.lighting` |
|---|---|---|
| `lightmapper` | `ProgressiveGPU` | `ProgressiveCPU` on CI, either locally |
| `lightmapResolution` | 10 | 20 on mobile, 40 on desktop |
| `lightmapMaxSize` | 1024 | 1024 on mobile, 2048 on desktop |
| `directSampleCount` | 16 | 32 |
| `indirectSampleCount` | 64 | 512 |
| `environmentSampleCount` | 64 | 256 |
| `maxBounces` | 2 | 4 |
| `ao` | false | true only if contact shadows read as missing |
| `filteringMode` | `LightingSettings.FilterMode.Auto` | `LightingSettings.FilterMode.Auto` |
| `mixedBakeMode` | Same as final | Per `reference/light-modes.md` |

`mixedBakeMode` must match between the two: a draft baked as Baked Indirect says nothing about
how Shadowmask will look. The draft answers "is everything lit that should be"; the final
answers "is it clean".

## 7. Bake from script and read the result back

`Tools/Unity Dev/Lighting/Bake And Read Back` reports the plan and waits for confirmation. From
an eval:

```csharp
return BakeAndReadBack.Plan();      // text; changes nothing
return BakeAndReadBack.Start();     // {"status":"started", "before":{…}}
return BakeAndReadBack.Status();    // {"status":"running","progress":0.42} … then the report
```

The report, when the bake ends (abridged):

```json
{"status":"baked","requested":"ProgressiveGPU","ran":"ProgressiveGPU","graphicsDevice":"Metal","bakeSeconds":38.2,
 "before":{"lightmaps":0,"largest":"0x0","probes":0,"contributeGI":14,"bakedOrMixedLights":3,"lightingData":"none"},
 "after":{"lightmaps":1,"largest":"1024x1024","probes":36,"contributeGI":14,"bakedOrMixedLights":3,
          "lightingData":"Assets/Scenes/GateRoom/LightingData.asset"},
 "detail":"the lighting data asset was written after the bake started and the scene has baked output"}
```

| `status` | Meaning |
|---|---|
| `baked` | The lighting data asset was written after the start, and the scene has lightmaps or probes |
| `baked-empty` | The bake ran and wrote neither. `detail` says which input was missing |
| `nothing-written` | The lighting data asset is older than the start: cancelled, failed, or Baked Global Illumination is off |
| `refused` | Not started: unsaved scene, Play mode, a bake already running, or no graphics device for the default lightmapper |

Then **save the scene**: the reference to the new lighting data lives in it.

In batch mode, with no `-quit`, because the bake outlives the method call:

```bash
Unity -batchmode -nographics -projectPath . \
  -executeMethod BakeAndReadBack.BatchBake -bakeScene Assets/Scenes/GateRoom.unity -logFile bake.log
# exit 0 baked · 1 nothing written · 2 refused; the report is the [LIGHTING-BAKE] line in bake.log
```

The method behind it — start asynchronously, poll `Lightmapping.isRunning`, treat a bake still
running at the end of a turn as a boundary and not a result, count evidence on disk — is
`unity-urp-migration` → `resources/Editor/LightingMigration.cs`. Related calls:

| Call | Does |
|---|---|
| `Lightmapping.BakeAsync()` | Starts a full bake; returns false when it could not start |
| `Lightmapping.Bake()` | The same, blocking |
| `Lightmapping.Cancel()` | Stops a running bake |
| `Lightmapping.Clear()` | Drops the baked data from the loaded scene |
| `Lightmapping.ClearLightingDataAsset()` | Drops the scene's lighting data asset reference |
| `Lightmapping.ClearDiskCache()` | Empties the bake cache: the next bake recomputes everything |

## Related skills

Light and Lighting Mode choices: `reference/light-modes.md`. Probes for what does not get
texels: `reference/probes.md`. Modelling a kit whose pieces unwrap cleanly is `unity-3d-level` →
`reference/modular-kit.md`; decimating a dense mesh is `unity-3d-models`. A stale bake after a
pipeline switch is `unity-urp-migration`.
