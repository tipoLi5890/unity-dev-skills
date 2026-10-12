# Terrain — large outdoor ground, and when a mesh is the better ground

> Part of the `unity-3d-level` skill. What Unity's Terrain is for, the four resolutions that
> decide its cost, layers, grass and trees in brief, its collider and holes, the cases where a
> mesh beats it, and scattering props with a seed and a budget. Worked setting: the **launch
> field** — 256 m of open ground between the depot and the gate.

Terrain is a heightmap: one height per grid sample, nothing else. That makes it cheap to draw
at any distance and impossible to give an overhang, a cave or a vertical wall. Reach for it when
the ground is big and rolling; reach for a mesh when it is small, flat or has an underside.

## 1. Terrain or mesh

| The ground is | Use | Because |
|---|---|---|
| Over about 200 m across, sculpted, seen to the horizon | Terrain | Built-in distance LOD, painted layers, instanced grass and trees |
| An arena, a courtyard, a street under 100 m | A mesh, or kit floor pieces | One draw, exact silhouette, no terrain shader cost |
| Flat | Kit floors or one box | A heightmap of zeros is a costly plane |
| Overhangs, caves, arches, cliffs you walk under | Meshes — or terrain with a hole where the mesh takes over (§5) | A heightmap has one height per point |
| A lane run's track | A spline-extruded mesh — `reference/splines-and-decals.md` | The track's width and camber are the design; terrain cannot hold them |
| Stylised flat-shaded low-poly ground | A mesh | Terrain interpolates normals and blends layers; neither is wanted |

Greybox outdoor ground as a few large boxes and ramps first (`reference/greybox.md`). Sculpt a
terrain when the walk journey passes and the space has been agreed.

## 2. The four resolutions

Set them once, at creation; changing the heightmap resolution later resamples everything.

| Setting (`TerrainData`) | Launch field | Rule |
|---|---|---|
| `size` | 256 × 40 × 256 | Width and length in metres; height is the full range, not the tallest hill |
| `heightmapResolution` | 257 | Clamped to 33, 65, 129, 257, 513, 1025, 2049 or 4097. Metres per sample = `size.x / (resolution − 1)`: aim at **1 m** where the runner walks, 2–4 m for land only seen |
| `alphamapResolution` (control texture) | 256 | How finely layers are painted: 0.5–1 m per texel is enough to draw a path |
| `baseMapResolution` | 512 | The single flattened texture drawn beyond `Terrain.basemapDistance` |
| Detail resolution (`SetDetailResolution`) | 256, 16 per patch | Grass density grid; the patch size sets how grass is batched and culled |

A finer heightmap does not make a cliff: samples are still one per point, and a steep face
stretches its texture across two of them. Steepness is a mesh's job.

```csharp
// Editor. Writes an asset — report the path and wait for a yes before running it.
var data = new TerrainData { heightmapResolution = 257 };   // resolution first, then size
data.size = new Vector3(256f, 40f, 256f);
Debug.Log(data.size);                                        // read it back: it must be (256, 40, 256)
AssetDatabase.CreateAsset(data, "Assets/Terrain/LaunchField.asset");
GameObject field = Terrain.CreateTerrainGameObject(data);    // Terrain + TerrainCollider
field.layer = LayerMask.NameToLayer("World");
```

Heights are written as `float[,]` in 0…1 of `size.y`, indexed `[z, x]`:
`data.SetHeights(0, 0, heights)`; read with `data.GetHeights(0, 0, w, h)`. World height at a
point is `terrain.transform.position.y + terrain.SampleHeight(worldPoint)` — `SampleHeight` is
relative to the terrain's own origin.

## 3. Layers

A `TerrainLayer` asset is one ground material: diffuse, normal, mask, tiling. The terrain
blends them by the control texture.

- **Four layers draw in one pass.** A fifth adds a second pass over every patch of the terrain
  that uses it. The launch field has four: tarmac, gravel, grass, dirt.
- Tile each layer to world scale (`tileSize` 2–4 m) and break the repeat with a second, larger
  layer, not with a bigger texture.
- Paint paths where the level's route goes: a path is a greybox marker the player can read.
- Layer textures follow the same import rules as any ground texture: anisotropic filtering on —
  `unity-3d-models` → `reference/texture-filtering.md`.

## 4. Grass, details and trees

| | Detail (grass, pebbles) | Tree |
|---|---|---|
| Stored as | A density map per prototype (`SetDetailLayer`) | A list of `TreeInstance` (`SetTreeInstances(instances, true)` snaps them to the ground) |
| Position | Scattered inside each cell by the terrain | Normalised 0…1 across the terrain |
| Drawn | In patches; set `DetailPrototype.useInstancing` for mesh details | Mesh near, billboard beyond `Terrain.treeBillboardDistance` |
| Collides | Never | Yes, when the tree prefab has a collider and the `TerrainCollider` has tree colliders enabled |
| Draw distance | `Terrain.detailObjectDistance` — start at 60 | `Terrain.treeDistance` — start at 300 |
| Budget lever | `Terrain.detailObjectDensity` 0…1 — start at 0.5 on a phone | `Terrain.treeMaximumFullLODCount`; fewer prototypes |

Keep `Terrain.drawInstanced` on — read it on every terrain, including ones made by an older
template or by script: terrain patches then draw instanced instead of one mesh per patch. Raise `Terrain.heightmapPixelError` from 5 towards 8–10 on a
phone to shed distant triangles; lower it and the count climbs steeply. Measure either change —
`unity-profiling` → `reference/counters.md`.

A thing the runner can collide with, pick up or hide behind is not a tree or a detail. It is a
prefab instance (§6).

## 5. The collider, and holes

- `TerrainCollider` is a heightfield at the **heightmap's** resolution, whatever LOD is being
  drawn. The ground under the feet is exact; the far hills are not approximated for physics.
- Put the terrain on the `World` layer with every other static solid —
  `reference/collision-proxies.md` §4.
- Slopes come out of sculpting, not out of a sheet. Check them:
  `data.GetSteepness(u, v)` returns degrees at a normalised point; anything over the
  controller's slope limit on the intended route is a wall the eye reads as a hill. Hold routes
  to the sheet's 30°.
- **A hole removes both the surface and its collision** for the cells painted with the Paint
  Holes tool. Use it for a tunnel mouth or a cave entrance, then fit a mesh into the opening:
  the mesh carries its own proxy. From code, `data.SetHoles(x, y, bool[,])` takes `false` for a
  hole at `holesResolution`; read one cell back with `data.IsHole(x, y)` before writing a
  region.
- The edge of a hole is one cell wide and straight. Overlap the mesh's rim by a cell, or the
  seam shows sky.
- Neighbouring terrains stitch only when both have the same heightmap resolution and their
  edge heights match; `Terrain.SetNeighbors` tells LOD about the join.

For the NavMesh, the surface collects the terrain's heights like any collider on `World`.
Trees are obstacles only if they carry colliders: bake round one tree and look before
planting a forest — `unity-navigation` → `reference/recipes.md` §6.

## 6. Scattering props — seeded, with a budget

Rocks, crates and barriers on the field are prefab instances placed by a script, so the layout
is reproducible, countable and re-rollable — never three hundred hand placements.

| Number | Launch field | Why |
|---|---|---|
| Seed | 7 | The same seed gives the same field: a bug report can name it |
| Density | 0.5 per 100 m² | 328 on 256 × 256 m |
| Cap | 400 instances | The budget; a density change cannot blow it |
| Steepest ground | 25° | Props do not perch on slopes the runner cannot reach |
| Spacing | 3 m | Wider than the body (`W` 0.8) with room to pass |
| Clear of the route | Lane half-width + 1 m | Nothing spawns in the path |

```csharp
// Editor. Creates scene objects — report the count it would place and wait for a yes.
public static int Scatter(Terrain terrain, GameObject prefab, Transform parent, int seed,
                          float per100m2 = 0.5f, int cap = 400, float maxSlope = 25f, float spacing = 3f)
{
    TerrainData data = terrain.terrainData;
    Vector3 origin = terrain.transform.position, size = data.size;
    int want = Mathf.Min(cap, Mathf.RoundToInt(size.x * size.z / 100f * per100m2));
    var random = new System.Random(seed);            // its own stream: nothing else can advance it
    var placed = new List<Vector3>();

    for (int tries = 0; placed.Count < want && tries < want * 20; tries++)
    {
        float u = (float)random.NextDouble(), v = (float)random.NextDouble();
        float yaw = (float)random.NextDouble() * 360f;                 // drawn every try, so a
        if (data.GetSteepness(u, v) > maxSlope) continue;              // rejection never shifts the rest
        var p = new Vector3(origin.x + u * size.x, 0f, origin.z + v * size.z);
        p.y = origin.y + terrain.SampleHeight(p);

        bool crowded = false;
        foreach (Vector3 q in placed)
            if ((q - p).sqrMagnitude < spacing * spacing) { crowded = true; break; }
        if (crowded) continue;

        var go = (GameObject)PrefabUtility.InstantiatePrefab(prefab, parent);   // stays a prefab instance
        Undo.RegisterCreatedObjectUndo(go, "Scatter props");
        go.transform.SetPositionAndRotation(p, Quaternion.Euler(0f, yaw, 0f));
        placed.Add(p);
    }
    return placed.Count;
}
```

- **`System.Random`, not `UnityEngine.Random`.** The engine's generator is one global stream
  that any other script advances.
- **Clear the parent before a re-roll**, and keep one parent per scatter so a count is
  `parent.childCount`.
- **Keep the route clear** by rejecting points near it: with a spline track,
  `SplineLane.Project(p, out _, out float lateral)` and skip when `|lateral|` is under the
  half-width plus a metre.
- **Past a few hundred identical objects, stop making GameObjects.** Paint them as terrain
  trees or details, which are instanced and culled by the terrain, and keep GameObjects for
  the things gameplay touches.
- Each scattered prop keeps its prefab's `Collision` child. Mark the parent static once the
  layout is agreed — `unity-scene-optimisation` → `reference/batching.md`.

## Traps

- **Setting `size` before `heightmapResolution`.** Set the resolution, then the size, then log
  `data.size`; a field that came out a different width was sized before its resolution.
- **Terrain for a flat arena.** Thousands of triangles and a multi-layer shader to draw a
  plane.
- **Five layers.** One more texture, one more full pass over the ground.
- **Grass density tuned on a desktop.** Detail draw cost scales with distance squared; set
  `detailObjectDistance` on the target device.
- **Height range far larger than the hills.** Heights are 16-bit across `size.y`: a 600 m
  range on a field that rises 10 m wastes the precision and steps the slopes.
- **A terrain moved or rotated at runtime.** It is a static collider and cannot be rotated at
  all. Level it in the editor.
- **Expecting baked shadows from grass.** Details are not lightmapped —
  `unity-lighting` → `reference/bake-setup.md`.

## Where each need is answered

| Need | Answer |
|---|---|
| Blocking the outdoor space before sculpting | `reference/greybox.md` |
| A road or track across the terrain; markings on it | `reference/splines-and-decals.md` |
| Layers and proxies for the props on it | `reference/collision-proxies.md` |
| The controller's slope limit and grounding on uneven ground | `unity-3d-controller` → `reference/grounding-and-slopes.md` |
| Sun, sky, fog and ambient light over open ground | `unity-lighting` → `reference/environment.md` |
| Shadow distance and cascades outdoors | `unity-lighting` → `reference/shadows.md` |
| Per-layer cull distances, LOD for scattered props | `unity-scene-optimisation` → `reference/culling-distances.md` |
| Triangle and draw-call counters before and after | `unity-profiling` → `reference/counters.md` |
| Agents walking terrain | `unity-navigation` → `reference/recipes.md` |
