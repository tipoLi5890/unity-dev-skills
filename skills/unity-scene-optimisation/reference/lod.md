# LOD: fewer triangles where nobody can count them

> Part of the `unity-scene-optimisation` skill. Enter from `Render/Triangles Count`: a median
> that is high while the camera looks down the lane and falls when it looks at the floor. If the
> triangle count does not change with the view, the cost is near the camera and LOD changes
> nothing: decimate the mesh instead.

## The cheapest test

Before authoring a single level, find out whether LOD is the lever. Halve
`QualitySettings.lodBias` for one window, read the triangle median, put it back — the method is
`unity-profiling` → `reference/where-the-time-goes.md` §4. A scene with no `LODGroup` does not
react at all, which is the second answer the test gives: run
`resources/Editor/SceneCostAudit.cs` and read `lod.groupTriangleShare`. Under 0.5 means most of
the scene's triangles have no lower level to fall back to, and `lod.heaviestWithout` lists the
ten meshes to start with.

## Two mechanisms, one decision

| | `LODGroup` | Mesh LOD |
|---|---|---|
| What it is | A component that enables one set of renderers per level | Index ranges inside one mesh asset, sharing its vertices |
| Authored | Several meshes, named `_LOD0` … `_LODn` | An import option: `ModelImporter.generateMeshLods` |
| Can change per level | Mesh, material, shadow casting, renderer count | Triangle count only |
| Culls at the far end | Yes — the height below the last level | No |
| Memory | Every level's vertices | One vertex buffer and a longer index buffer |
| Selected by | Screen height × `QualitySettings.lodBias` | `QualitySettings.meshLodThreshold`, `Renderer.meshLodSelectionBias` |
| Use for | Props that should drop a material, swap to a proxy, or vanish | Dense single-material meshes: generated props, terrain dressing |

They combine: a `LODGroup` whose level 0 is a mesh with Mesh LODs. Mesh LOD is a property of the
model importer: an editor whose `ModelImporter` has no `generateMeshLods` has no Mesh LOD. Read
`Mesh.lodCount` after the reimport — 1 means nothing was generated.

```csharp
var importer = (ModelImporter)AssetImporter.GetAtPath("Assets/Depot/Shelf.fbx");
importer.generateMeshLods = true;
importer.maximumMeshLod = 3;            // the cap on generated levels
importer.SaveAndReimport();
```

`Renderer.forceMeshLod` pins one level on one renderer for a screenshot; read its value before
changing it and write the same value back.

## Screen height is the unit

`LOD.screenRelativeTransitionHeight` is the share of the screen's height the object's bounds
cover. A level is drawn while the object is taller than its value; below the last value the
object is culled. Values must descend, or `SetLODs` logs an error and the group is left as it was.

Distance for a perspective camera:

```
distance = size × lodBias / (2 × height × tan(fov / 2))        fov 60°: distance = 0.866 × size × lodBias / height
```

`size` is `LODGroup.size` times the largest axis of the object's world scale.

| Hand-over height | 1 m hazard | 2 m crate | 6 m gate |
|---|---|---|---|
| 0.5 — LOD0 → LOD1 | 1.7 m | 3.5 m | 10 m |
| 0.2 — LOD1 → LOD2 | 4.3 m | 8.7 m | 26 m |
| 0.08 — LOD2 → LOD3 | 11 m | 22 m | 65 m |
| 0.01 — culled | 87 m | 173 m | 520 m |

The rule behind the table, and the one `resources/Editor/LodGroupBuilder.cs` writes: the first
hand-over at **0.5**, each later one at **0.4** of the one before, the last level culled below
**0.01** (about 11 px at 1080p). Two overrides are worth making by hand:

- **A hero object the camera rests on** — the gate at the end of the lane — keeps LOD0 to 0.25.
- **Lane furniture seen only in passing** hands over at 0.3 and culls at 0.02.

A level is worth having when it halves the triangles of the one before. The builder's plan flags
a level above that ratio: the swap costs a visible pop and saves little.

## Building the group from script

```csharp
var group = root.AddComponent<LODGroup>();
group.SetLODs(new[]
{
    new LOD(0.5f,  new Renderer[] { lod0 }),
    new LOD(0.2f,  new Renderer[] { lod1 }),
    new LOD(0.01f, new Renderer[] { lod2 }),
});
group.RecalculateBounds();      // after any change to the renderers; size drives every distance
```

`LodGroupBuilder` does this for a prefab whose children are named `_LOD0` … `_LODn`, several
renderers per level allowed. It reports the levels, their triangle counts and the heights first
and waits: `Tools/Unity Dev/Scene Optimisation/Build LODGroup From Children`, or
`LodGroupBuilder.Plan(root)` then `LodGroupBuilder.Build(root)` from an eval.

An FBX whose meshes already carry those names gets its `LODGroup` from the model importer; the
builder refuses a model asset for that reason. It is for prefabs assembled in Unity — a generated
GLB decimated to three files, a kit piece with a hand-made proxy.

The lower meshes themselves are decimation, not Unity: `unity-3d-models` →
`reference/import-and-decimate.md`. Decimate each level from the original, never from the level
above it, so errors do not compound.

## The last level

The last level wants to be a different object, not a lighter copy: one material, no normal map,
shadow casting off, a box or a card where the silhouette allows. A `LODGroup` can do all of that
because each level names its own renderers.

- Shadow casting on the far levels is paid for in `Render/Shadow Casters Count`, not in the
  triangle counter. Turn it off from LOD2 down and read that counter too.
- Baked lighting needs lightmap UVs on every level that is lightmapped. Lightmap LOD0 and light
  the others from probes — `unity-lighting` → `reference/probes.md`.

## The collider never needs a LOD

A `LODGroup` enables and disables renderers. It does not touch colliders, and physics does not
read it. Put one collider on the prefab root, sized for gameplay, and none on the level
children: a `MeshCollider` under `_LOD1` stays live at every distance and costs the same whether
its renderer is drawn or not. The builder's plan counts colliders it finds on LOD1 and below.
Choosing the proxy shape is `unity-3d-level` → `reference/collision-proxies.md`.

## Cross-fade

A swap is a pop. Cross-fade draws both levels for the length of the fade, dithered against each
other, so it hides the pop and raises the cost while it runs.

| Setting | Value | Effect |
|---|---|---|
| `LODGroup.fadeMode` | `LODFadeMode.CrossFade` | Enables the blend; `None` swaps in one frame |
| `LODGroup.animateCrossFading` | `true` | Fades over time once the hand-over height is crossed |
| `LODGroup.crossFadeAnimationDuration` | `0.5` s, static | Length of the timed fade, for every group |
| `LOD.fadeTransitionWidth` | `0.1` | With `animateCrossFading` off: the share of the level's range spent blending |
| URP Asset → LOD Cross Fade | on | Without it the shader has no fade variant and the swap pops |

Use the timed fade: a runner that stops inside a distance-based fade zone pays for two levels
until it moves. The shader must implement `LOD_FADE_CROSSFADE`; URP's Lit and Shader Graph
targets do. Leave cross-fade off on the lowest quality tier and on any prop whose swap is hidden
by speed.

## Per quality tier

`lodBias` multiplies every distance; `maximumLODLevel` discards the top levels outright.

| Tier | `lodBias` | `maximumLODLevel` | Cross-fade |
|---|---|---|---|
| Low — older phones | 0.6 | 1 | Off |
| Medium | 1.0 | 0 | Off |
| High — desktop | 2.0 | 0 | On |

Set them per level in Project Settings → Quality, or after the tier is chosen at runtime with
`QualitySettings.SetLODSettings(bias, maximumLODLevel, true)`. A level that no quality tier of the
build target can reach is left out of the build, so `maximumLODLevel = 1` on every mobile tier
also removes LOD0 meshes from the download.

## A fixed camera: pick the level by tier, and strip the group the importer adds

A broadcast camera over a court, a fixed side view, a camera on rails: every object sits at one
screen height for the whole match, so a screen-height switch never switches. Worse, scenery
exported as merged meshes (one object per material per zone) has bounds covering half the venue,
and its "screen height" means nothing. Choose the level from the quality tier instead: build both
levels into the prefab, and at scene build enable the objects whose names carry `_LOD0_` on the
high tier and `_LOD1_` on the others.

> **The FBX importer adds a `LODGroup` by itself.** Child names carrying `_LOD0`, `_LOD1` … make
> `ModelImporter` put a `LODGroup` on the root, selecting by screen height. It happened with the
> marker in the middle of the name too (`Venue_Blossom_LOD1_Main`). In a tennis game
> the trees' LOD1 set was meant for the medium and low tiers; the importer's group, seeing the
> whole venue large on screen, selected LOD0 and culled LOD1, so on those tiers the tree line
> vanished. Nothing logged it. Remove every `LODGroup` when the builder makes the prefab, and
> assert there are none:

```csharp
// builder, after instantiating the imported model and before saving the prefab
foreach (var g in inst.GetComponentsInChildren<LODGroup>(true))
{
    Debug.Log("[VENUE] removed importer LODGroup on " + g.gameObject.name);
    Object.DestroyImmediate(g);
}

// EditMode test
Assert.AreEqual(0, prefab.GetComponentsInChildren<LODGroup>(true).Length,
    "the importer's LODGroup is back: it culls the low-tier level");
Assert.AreEqual(lod0Objects > 0, lod1Objects > 0, "levels come in pairs");
```

### A per-tier triangle budget, counted from the one camera

With a fixed camera the budget can be checked without running the game: sum the index counts of
every `MeshFilter` in the prefab that the camera draws on that tier. Skip the other level, and
skip the zone behind the camera that its culling mask removes (`reference/culling-distances.md`
§"The culling mask"). The builder logs the count on every rebuild; an EditMode test fails when a
tier goes over the row chosen in the project's art direction. In the tennis game the chosen row
was 150 000 for high and 50 000 for medium and low. The densest venue measured 103 020 on high (LOD0
trees, about 6 700 triangles each) and 39 516 on medium and low (LOD1 trees, 1 434 each, the
blossom clusters replaced by fitted icosahedra grown from the same seed).

```csharp
int high = 0, low = 0;
foreach (var f in prefab.GetComponentsInChildren<MeshFilter>(true))
{
    if (f.sharedMesh == null || f.name.EndsWith("_Near0")) continue;   // behind camera 0
    int t = 0;
    for (int i = 0; i < f.sharedMesh.subMeshCount; i++) t += (int)f.sharedMesh.GetIndexCount(i) / 3;
    if (!f.name.Contains("_LOD1_")) high += t;
    if (!f.name.Contains("_LOD0_")) low += t;
}
```

Count index buffers, not `mesh.triangles.Length`: the latter allocates a copy and needs Read/Write.

## Read it again

Same situation, same camera path, three windows a side — `unity-profiling` →
`reference/compare.md`:

```bash
python3 scripts/compare_windows.py base.jsonl cand.jsonl --label approach-gate \
    --counters "Render/Triangles Count,Render/Shadow Casters Count,Render/Draw Calls Count"
```

Expect triangles down and draw calls level. Draw calls up means a far level has more renderers
or materials than the level above it; draw calls sharply down means the cull height is doing the
work, which is a culling-distance result — `reference/culling-distances.md`.

## Traps

- **Renderers added after `SetLODs` are outside the group** and are drawn at every distance.
- **A `LODGroup` on a static-batched prop** puts every level's vertices in the combined mesh.
- **A group whose bounds were computed before its children were scaled** switches at the wrong
  distances; call `RecalculateBounds`.
- **An orthographic camera selects by size on screen, not distance**: a top-down depot at a
  fixed zoom sits on one level for ever. Pick the level by hand and delete the others.
- **`LODGroup.ForceLOD(n)` survives until `ForceLOD(-1)`.** A debugging call left in a build
  pins the level for the session.
