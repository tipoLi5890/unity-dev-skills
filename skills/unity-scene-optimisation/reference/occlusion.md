# Occlusion: not drawing what a wall already hides

> Part of the `unity-scene-optimisation` skill. Enter from `Render/Draw Calls Count` and
> `Render/Triangles Count` staying high while the camera faces a wall with the rest of the level
> behind it. Frustum culling is free and already on; occlusion culling is the second, separate
> test, and it earns its cost only where large solid things stand between the camera and most
> of the scene.

## The cheapest test

Baking takes minutes and a layout. Find the ceiling first: in the situation where the runner
faces the wall, deactivate by hand the rooms that cannot be seen, take one window, reactivate.
That window is the most occlusion culling can ever return. If the counters barely move, stop
here — the cost is in what is visible, and the lever is LOD or batching.

## Where it does nothing

| Scene | Why |
|---|---|
| The lane run: an open strip under the sky | Nothing is large enough to hide anything; the cull is all frustum and distance |
| The depot seen from above | A top-down camera sees over every shelf into every aisle |
| A yard of small props | Occluders smaller than the Smallest Occluder setting are ignored |
| Fences, grilles, glass, foliage | Anything seen through must not be an occluder, and so hides nothing |
| A level whose walls move | Baked occluders are static; a moved wall keeps hiding what it used to |

The gate room is where it works: solid walls, a doorway, a second room behind the gate.

## Baked occlusion culling

The bake cuts the scene into cells and stores which cells can see which. At runtime the camera
looks up its cell; nothing is traced.

**1. Flag the geometry.** Two static flags, set separately:

| Flag | On | Never on |
|---|---|---|
| `StaticEditorFlags.OccluderStatic` | Walls, floors, ceilings, large solid props that never move | Anything transparent, cut-out, thin, small or moving |
| `StaticEditorFlags.OccludeeStatic` | Every static renderer that could be hidden | — |

```csharp
GameObjectUtility.SetStaticEditorFlags(wall,
    GameObjectUtility.GetStaticEditorFlags(wall)
    | StaticEditorFlags.OccluderStatic | StaticEditorFlags.OccludeeStatic);
```

Moving objects need no flag: a renderer with `allowOcclusionWhenDynamic` (on by default) is
culled as an occludee from its bounds each frame. A moving object never occludes.

**2. Choose the three settings.** They are scene state — save the scene after changing them —
read and written through `StaticOcclusionCulling`:

| Setting | Default | Meaning | Gate room |
|---|---|---|---|
| `smallestOccluder` | 5 | Metres. Nothing smaller hides anything. It also sets how finely the scene is cut into cells: there is no separate cell size | 2 — the walls are 3 m tall |
| `smallestHole` | 0.25 | Metres. The narrowest gap the camera is assumed to see through | 0.25 |
| `backfaceThreshold` | 100 | 100 keeps all data; lower values drop cells that mostly see back faces | 100 |

Lowering `smallestOccluder` makes the cells finer and the bake longer. Start at the default,
lower it only when a wall that should hide the next room does not, and read `bytes` and the
bake time after each bake.

**3. Bound the camera, if the level is large.** With no `OcclusionArea` the view volume is the
bounds of the static geometry. Add one `OcclusionArea` over the space the camera can actually be
in — the corridors, not the roofs — to cut data and bake time.

**4. Bake and read back.** `resources/Editor/OcclusionBake.cs` reports the counts of flagged
renderers, the settings and the current data size, waits for confirmation, bakes, and prints one
JSON object: `Tools/Unity Dev/Scene Optimisation/Bake Occlusion`, or from an eval
`OcclusionBake.Plan()` then `OcclusionBake.Bake(2f, 0.25f, 100f)`.

```csharp
StaticOcclusionCulling.smallestOccluder = 2f;
bool ok = StaticOcclusionCulling.Compute();         // synchronous; GenerateInBackground() + isRunning to poll
long bytes = new FileInfo("Assets/Scenes/GateRoom/OcclusionCullingData.asset").Length;
```

The data lands in `OcclusionCullingData.asset`, in a folder named after the scene beside it,
and the scene file references it: commit both. Unity publishes no cell count, and
`StaticOcclusionCulling.umbraDataSize` reads 0 in batch mode even after a good bake, so the
read-back is that file: the bake's JSON gives its size as `bytes` and `written` true when this
bake rewrote it. No file after a bake means no data was produced.

**5. Confirm a camera uses it.** `Camera.useOcclusionCulling` is on by default. In the Scene
view, Window → Rendering → Occlusion Culling → Visualization shows what the selected camera
culls; `StaticOcclusionCullingVisualization.showOcclusionCulling` is the same switch from code.

## The gate is a portal

The gate between the two rooms opens, so it cannot be a static occluder. Give it an
`OcclusionPortal` and drive it from the switch:

```csharp
// GateSwitch, where the gate changes state
portal.open = gateIsOpen;       // closed: everything behind the gate is culled
```

A portal left open hides nothing; one left closed after the gate opens makes the next room
vanish.

## The bake goes stale

Baked data describes the layout at bake time. After moving, adding or deleting a static
occluder, the old data still culls by the old walls: props disappear in plain view, or stay
drawn behind new walls.

- Re-bake after every layout change to flagged geometry. `OcclusionBake.Plan()` in a pre-build
  step makes the data size visible in the log.
- Scenes loaded additively at runtime each bring their own data only if they were open together
  when baked. Open the set, bake once.
- Geometry built at runtime — a level assembled from kit prefabs in code — has no bake. Use
  culling distances, or the GPU path below.

## GPU occlusion culling (URP)

URP can test instances against the depth buffer on the GPU with no bake, as part of the GPU
Resident Drawer. It covers moving objects and levels built at runtime, and it applies only to
renderers the drawer has taken over — `reference/batching.md` lists what those are.

| Where | Setting | Value |
|---|---|---|
| URP Asset → Rendering | GPU Resident Drawer — `gpuResidentDrawerMode` | `GPUResidentDrawerMode.InstancedDrawing` |
| URP Asset → Rendering | GPU Occlusion Culling — `gpuResidentDrawerEnableOcclusionCullingInCameras` | on |
| Universal Renderer Data | Rendering Path | Forward+ or Deferred+ |
| Project Settings → Graphics | BatchRendererGroup Variants | Keep All |

```csharp
var urp = (UniversalRenderPipelineAsset)GraphicsSettings.currentRenderPipeline;
urp.gpuResidentDrawerMode = GPUResidentDrawerMode.InstancedDrawing;
urp.gpuResidentDrawerEnableOcclusionCullingInCameras = true;
bool active = GPUResidentDrawer.IsInstanceOcclusionCullingEnabled();   // false: read the console
```

`GPUResidentDrawerMode` is in the assembly `Unity.RenderPipelines.GPUDriven.Runtime`; an asmdef
that names the type references it beside `Unity.RenderPipelines.Universal.Runtime` and
`Unity.RenderPipelines.Core.Runtime`.

- **It is skipped on Qualcomm GPUs.** URP turns the occlusion test off there and logs `The GPU
  Occlusion Culling feature is currently unavailable on this device`. Do not budget an Android
  build on it; take the window on the device.
- **Game, Scene and Preview cameras only.** A reflection or custom camera draws everything.
- **It needs the depth texture**, which URP then enables for the camera.
- **Read it back** in Window → Analysis → Rendering Debugger → Rendering → GPU Resident Drawer
  Settings: Display Culling Stats shows `Visible Instances CPU | GPU` per view, and Occlusion
  Test Overlay paints what was rejected. Equal CPU and GPU numbers mean the occlusion test
  rejected nothing.

Baked data and the GPU test are two costs. Take a window with each alone before keeping both.

## Read it again

Three windows a side, the camera in the same pose facing the wall — `unity-profiling` →
`reference/compare.md`:

```bash
python3 scripts/compare_windows.py base.jsonl cand.jsonl --label gate-room \
    --counters "Render/Draw Calls Count,Render/Triangles Count,Render/Shadow Casters Count"
```

Then a second label with the camera in the doorway looking through: the counters there must not
have fallen, and the screenshot must show the far room. A culling result is accepted only with
both.

## Traps

- **The frame time went up.** The lookup costs CPU every frame. In a scene where it hides
  little, turn `Camera.useOcclusionCulling` off for that camera.
- **Shadows of hidden objects still reach the visible room.** Casters outside the view are kept
  for the shadow pass; that cost is `unity-lighting` → `reference/shadows.md`.
- **`-batchmode -nographics` cannot show the result.** Render counters read zero there; the
  bake itself is editor work, the window needs a graphics device.
