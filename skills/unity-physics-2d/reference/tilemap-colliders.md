# Tilemap colliders: from a painted tile to the shape Box2D collides with

Part of the `unity-physics-2d` skill. SKILL.md §5 states each rule in a line; this file holds the
chain from tile to shape, the composite set-up and the runtime path in full.

## Three places decide a tile's shape

| Where | Setting | Decides |
|---|---|---|
| The tile asset | `Tile.colliderType`: `Tile.ColliderType.None`, `Sprite`, `Grid` | Whether the tile contributes a shape, and whether it is the sprite's physics outline or the whole cell |
| The Tilemap's GameObject | `TilemapCollider2D` | That the Tilemap contributes shapes at all, one set per tile |
| The same GameObject | `CompositeCollider2D` + a `Rigidbody2D` | That the per-tile shapes are merged into one outline |

Setting the collider type on a tile, and what each value looks like in a palette, is
`unity-tilemap` → `reference/palette-and-grid.md`. Two consequences belong here:

- **`Grid` for solid level tiles.** The shape is the cell, so neighbours meet exactly and merge
  cleanly. `Sprite` uses the sprite's physics outline, which seldom reaches the cell edge and
  leaves slivers between tiles; keep it for slopes and half tiles whose outline was authored for
  it — `unity-2d-sprites` → `reference/sprite-geometry.md`.
- **`None` for everything decorative.** A floor Tilemap in the top-down depot has no collider
  component at all; a background Tilemap in the side run likewise. One Tilemap per role, so that
  each role has one layer and one collider decision.

`Tilemap.GetColliderType(cell)` reads what a placed tile uses and `Tilemap.SetColliderType(cell,
type)` overrides it for one cell — a rooftop tile that turns into a gap when a launch pad fires
does not need a second tile asset.

## The set-up that works

On the Tilemap's GameObject, in this order:

1. `TilemapCollider2D`, with `compositeOperation = Collider2D.CompositeOperation.Merge`.
2. `CompositeCollider2D`. Adding it adds a `Rigidbody2D`.
3. On that `Rigidbody2D`: `bodyType = RigidbodyType2D.Static`. The component arrives Dynamic, and
   a Dynamic level falls out of the scene on the first step.
4. On the composite: `geometryType = CompositeCollider2D.GeometryType.Outlines` for a static
   level; `generationType = CompositeCollider2D.GenerationType.Synchronous`.
5. The GameObject's layer: `Rooftop` in the side run, `Obstacles` in the depot.

```csharp
// From an Editor script or a level loader. tilemap is the solid Tilemap.
var tiles = tilemap.gameObject.AddComponent<TilemapCollider2D>();
tiles.compositeOperation = Collider2D.CompositeOperation.Merge;
var composite = tilemap.gameObject.AddComponent<CompositeCollider2D>();   // adds the Rigidbody2D
tilemap.GetComponent<Rigidbody2D>().bodyType = RigidbodyType2D.Static;
composite.geometryType = CompositeCollider2D.GeometryType.Outlines;
tilemap.gameObject.layer = LayerMask.NameToLayer("Rooftop");
```

Check it took: `composite.pathCount` is the number of separate outlines and `composite.pointCount`
the total vertices. A flat strip of forty tiles is one path with a handful of points.
`pathCount 0` means nothing merged — `compositeOperation` is still `None` — and one path per tile
means the tiles do not touch: the tile collider type is `Sprite` with an outline short of the cell.

`usedByComposite` is the deprecated boolean for step 1; it compiles with a warning and maps to
`Merge`.

Once merged, the composite owns the pair: `isTrigger`, `sharedMaterial`, `usedByEffector` and the
layer overrides are read from the `CompositeCollider2D`, and the same fields on the
`TilemapCollider2D` are ignored.

## Outlines or polygons

| `GeometryType` | Shapes | Interior | Use |
|---|---|---|---|
| `Outlines` | Chains of edges around each island | Hollow | A static level: fewest shapes, smooth to slide along |
| `Polygons` | Convex polygons filling each island | Solid | A composite on a Kinematic or Dynamic body; anything `OverlapPoint` must find from inside; a trigger region |

What hollow means in practice:

- A pickup pushed fully inside a wall by a spawn or a teleport stays there. Nothing pushes it out,
  because it is touching no edge.
- `Physics2D.OverlapPoint` at the centre of a solid block returns nothing. A level validator
  asking "is this cell solid" needs `Polygons`, or `Tilemap.HasTile` instead of a physics query.
- An outline composite on a moving body does not collide with another outline composite or with
  an `EdgeCollider2D`: edges have no area to overlap with.
- A trigger made of outlines fires only while something crosses its border.

`Polygons` costs shapes: a concave island is cut into several convex pieces, and
`useDelaunayMesh = true` changes how it is cut when a decomposition leaves thin slivers.

## Seams, and the ghost-vertex snag

Without a composite a Tilemap is a row of independent boxes. A box-shaped runner sliding along the
row tests each tile separately, and at the shared corner of two neighbours the nearest feature of
the next tile is its side face, not its top. The contact normal comes back sideways for a step,
and the runner stops dead on flat ground or pops upward.

Causes, in the order to rule them out:

1. **No composite**, or a composite whose child is still at `CompositeOperation.None`. Read
   `pathCount` as above.
2. **Two Tilemaps meeting on a line** — a room joined to a corridor, each with its own composite.
   Each outline is smooth; the join between them is two edge ends. Put touching solid tiles on one
   Tilemap, or overlap the two by a tile so that the seam is buried.
3. **A `Polygons` composite.** The convex pieces meet on internal edges; a body crossing one can
   catch the same way, less often. `Outlines` has no internal edges.
4. **Sub-pixel gaps between cells.** `TilemapCollider2D.extrusionFactor` grows each tile's shape
   by a small world-space amount before merging so that neighbours overlap; raise it when
   `pointCount` shows extra vertices along what should be one straight edge.
5. **A hand-built `EdgeCollider2D` meeting another.** Set `useAdjacentStartPoint` /
   `useAdjacentEndPoint` and give `adjacentStartPoint` / `adjacentEndPoint` the next edge's
   vertex; the end normal is then computed as if the two edges were one chain.

A character-side mitigation helps with all five and replaces none: a `CapsuleCollider2D`, or a
`BoxCollider2D` with a small `edgeRadius`, rides over a corner that a sharp box catches. The
motor's side of it is `unity-2d-controller` → `reference/platformer.md`.

## One-way tiles on their own Tilemap

A one-way platform is a property of a collider, and a composite is one collider. One-way tiles
therefore cannot share a Tilemap with solid ones.

| GameObject | Components | Layer |
|---|---|---|
| `Solid` Tilemap | `TilemapCollider2D` (Merge), `CompositeCollider2D` (Outlines), `Rigidbody2D` (Static) | `Rooftop` |
| `OneWay` Tilemap | `TilemapCollider2D` (Merge), `CompositeCollider2D` (Polygons, `usedByEffector = true`), `Rigidbody2D` (Static), `PlatformEffector2D` (`useOneWay`, `surfaceArc 170`) | `Platform` |

- `usedByEffector` goes on the composite. On the `TilemapCollider2D` it is ignored after the merge.
- `Polygons` here so that the platform also answers `OverlapPoint` and overlap queries.
- Paint one-way tiles one cell thick. A two-cell slab is one shape; a runner whose feet clear the
  first row is still inside it.
- A separate layer lets the motor's ground cast tell the two apart, which it must: a cast does not
  know about the effector. Settings and failure modes are in
  `reference/effectors-and-joints.md`.

## Changing tiles at runtime

`Tilemap.SetTile` marks the collider dirty. The `TilemapCollider2D` gathers the changes and
rebuilds the affected shapes later in the frame, and a `Synchronous` composite regenerates its
outline after that. Two consequences:

- **A query in the same frame sees the old shape.** After a launch pad removes a rooftop tile,
  force the update before casting; a `Synchronous` composite follows in the same call:

  ```csharp
  tilemap.SetTile(cell, null);
  if (tiles.hasTilemapChanges) tiles.ProcessTilemapChanges();
  ```

- **Many changes in one frame regenerate the outline many times.** For a level loader or a
  collapsing floor, take over the generation:

  ```csharp
  composite.generationType = CompositeCollider2D.GenerationType.Manual;
  foreach (Vector3Int cell in cells) tilemap.SetTile(cell, null);
  tiles.ProcessTilemapChanges();
  composite.GenerateGeometry();          // once, after the batch
  ```

  Leave it at `Manual` only if every code path that edits tiles ends with `GenerateGeometry()`; a
  path that forgets leaves the visible level and the collided level different, with no error.

`TilemapCollider2D.maximumTileChangeCount` is the number of pending tile changes above which the
component rebuilds everything instead of patching. Loading a whole room goes over it by design.

If a pickup that rested on a removed tile hangs in the air afterwards, it is asleep: read
`IsSleeping()` on it and call `WakeUp()` from the code that removed the tile.

Writing level data into a Tilemap, chunking and room loading:
`unity-2d-level` → `reference/runtime-tilemap.md`.

## Isometric and hexagonal grids

`Tile.ColliderType.Grid` follows the cell shape of the `Grid` component: a diamond on an isometric
layout, a hexagon on a hexagonal one. In the sorting yard nothing moves freely, so the cell map is
the collision model and physics shapes are needed only for picking — one `TilemapCollider2D` with
`Grid` tiles and `Physics2D.OverlapPoint`, or no collider and `Grid.WorldToCell`. Which of the two
is `unity-2d-grid` → `reference/picking.md`.
