# Culling distances: small things stop being drawn first

> Part of the `unity-scene-optimisation` skill. Enter from `Render/Draw Calls Count` that climbs
> with how far down the lane the camera can see, while most of what it adds is a few pixels
> tall. One far plane treats a gate and a pickup alike; the gate must be visible at 150 m and
> the pickup stops mattering at 45.

## The cheapest test

Pull `Camera.farClipPlane` in to half for one window and read draw calls and triangles. A large
drop says distance is the lever. Then put the far plane back: the fix is per layer, because the
far plane also removes the gate.

## The levers, by what decides the cut

| Lever | Cuts by | Where it lives | Use for |
|---|---|---|---|
| `Camera.farClipPlane` | Distance, everything | The camera — or the Cinemachine camera's lens | The end of the world; pair with fog |
| `Camera.layerCullDistances` | Distance, per layer | The camera | Classes of small props |
| `LODGroup` cull height | Size on screen, per object | The prefab | Props that already have levels — `reference/lod.md` |
| `smallMeshScreenPercentage` | Size on screen, global | URP Asset, with the GPU Resident Drawer | Kit dressing with no `LODGroup` — `reference/batching.md` |
| `Camera.cullingMask` | Layer, entirely | The camera | A second camera that should draw a fraction of the scene |
| `Light.layerShadowCullDistances` | Shadow distance, per layer | A directional light | Small props that should stop casting first — `unity-lighting` → `reference/shadows.md` |

## Per-layer distances

```csharp
float[] distances = new float[32];                              // exactly 32, one per layer
distances[LayerMask.NameToLayer("PropSmall")]  = 45f;           // pickups, debris, lane markers
distances[LayerMask.NameToLayer("PropMedium")] = 90f;           // hazards, crates, signs
camera.layerCullDistances = distances;                          // 0 keeps the far plane for that layer
camera.layerCullSpherical = true;
```

- **The array has 32 entries or the assignment throws.** The getter returns a copy: change the
  copy and assign it back.
- **0 means "use the far plane"**. A distance must not exceed the far plane.
- **`layerCullSpherical = true` measures from the camera position.** With it off the cut is a
  plane facing the camera, and a prop at the edge of the screen pops in and out as the camera
  turns. Turn it on for any camera the player rotates.
- **`LayerMask.NameToLayer` returns -1 for a layer that does not exist**, and `distances[-1]`
  throws. Assert the layers at startup.
- **The setting is on the `Camera`**, so a Cinemachine camera does not overwrite it. The far
  plane is different: Cinemachine writes its lens to the camera every frame, so set
  `Lens.FarClipPlane` there; the lens belongs to the rig — `unity-camera`.

## Choosing the distance from the size

A thing under about 8 px tall contributes nothing a player can read. The distance at which an
object of height `size` falls to `pixels` on a screen `screenHeight` tall:

```
distance = size × screenHeight / (2 × pixels × tan(fov / 2))       fov 60°, 1080p, 8 px: distance = 117 × size
```

| Layer | Typical size | Distance at 1080p | Use |
|---|---|---|---|
| `PropSmall` | 0.4 m — a pickup | 47 m | 45 |
| `PropMedium` | 0.8 m — a hazard | 94 m | 90 |
| Default | 3 m and up — the gate, walls | Far plane | 0 |

Derive the distances at the highest resolution the tier supports, or scale them with
`Screen.height / 1080f` when the quality tier is applied. A phone at 720p can cut at two thirds
of the desktop distance and show the same thing.

Gameplay overrides size: a pickup the player steers towards from 60 m must be on a layer that
reaches 60 m, whatever its height.

## Layers are shared with physics

A layer is one number used by rendering, physics and raycasts. Moving a pickup to `PropSmall`
for culling also moves it to that layer's row of the collision matrix and out of any
`LayerMask` that named its old layer. Two ways to keep them apart:

- Put the **renderer** on a child object with the culling layer, and keep the collider and the
  script on the root with the gameplay layer.
- Or define the culling layers first and give them the same collision row as the layer they
  replace. The Layer Collision Matrix itself is `unity-physics-3d`.

## The culling mask

A second camera — a minimap, a mirror, a portrait — draws the whole scene again unless its mask
says otherwise, and every render counter doubles.

```csharp
minimap.cullingMask = LayerMask.GetMask("Lane", "Runner", "Gate");     // three layers, not all 32
minimap.farClipPlane = 60f;
minimap.useOcclusionCulling = false;                                   // overhead: nothing occludes
```

Under URP an Overlay camera in a stack culls again too. The opposite fault — a model that shows
in the Scene view and not in the Game view because its layer is missing from the mask — is
`unity-3d-models` → `reference/culling-and-layers.md`.

## Hiding the cut

- **Fog that reaches full density at the far plane** makes the far cut invisible. Per-layer cuts
  are closer than the fog and need the size rule instead: an 8 px object vanishing is not seen.
- **A `LODGroup` with cross-fade** dithers the object out rather than popping it; use it for
  the few medium props where the cut is noticed.
- **Never cut what casts a long shadow into view.** The shadow disappears with the renderer.

## Read it again

Three windows a side with the camera looking down the lane — `unity-profiling` →
`reference/compare.md`:

```bash
python3 scripts/compare_windows.py base.jsonl cand.jsonl --label approach-gate \
    --counters "Render/Draw Calls Count,Render/Triangles Count,Render/Shadow Casters Count"
```

Then play the situation once and look for the cut. A counter that fell and a pickup that pops
into existence in front of the runner is a regression the table cannot see: the same
comparison's report lists it under what was not covered.

## Traps

- **`resources/Editor/SceneCostAudit.cs` reports `layersWithCullDistance` per camera.** Zero on
  the game camera means every layer runs to the far plane. Its `triangles.byLayer` shows which
  layer is worth cutting: a layer with 3% of the triangles is not.
- **Distances set in a script's `Awake` are lost when the camera is replaced** by a new one on
  scene load. Set them where the camera is created.
