# Tilemaps at runtime — which call, which coordinates, what it costs

> Part of the `unity-2d-level` skill. The `Tilemap` calls a level loader, a digging mechanic or
> a generator uses: setting one cell, many cells and a block; bounds that only grow; cell and
> world coordinates; what a refresh does to rule tiles; and why colliders lag the tiles.
> `resources/TilemapLevelLoader.cs` uses the block path.

Everything here is `UnityEngine.Tilemaps`, in the Tilemap module that ships with the Editor.
Authoring palettes and rule tiles is `unity-tilemap`; this file starts from tile assets that
already exist.

## Setting tiles

| Call | Use it for | Notes |
|---|---|---|
| `SetTile(Vector3Int, TileBase)` | One cell: a door opening, a block broken | `null` erases |
| `SetTiles(Vector3Int[], TileBase[])` | Scattered cells in one call: a blast radius, a path carved by a generator | Arrays of equal length; one batch of refreshes and one collider change set |
| `SetTiles(TileChangeData[], bool ignoreLockFlags)` | Cells that also need a colour or a transform: a flipped tile, a tinted one | `TileChangeData` carries `position`, `tile`, `color`, `transform`; its colour and transform take precedence over the tile's own |
| `SetTilesBlock(BoundsInt, TileBase[])` | A filled rectangle: a whole level, a room, a chunk | The fastest path; `null` entries erase |
| `BoxFill` · `FloodFill` | One tile over a rectangle or a connected region | Editor-tool semantics; rarely what a loader wants |
| `SwapTile(TileBase, TileBase)` | Replace every instance of a tile: a switch that turns all hazard tiles off | Refreshes each swapped cell |
| `ClearAllTiles()` | Before loading the next level into the same stack | |

**The block is filled x first, then y.** For a `BoundsInt` at `(x0, y0, 0)` with size
`(w, h, 1)`, entry `i` lands on cell `(x0 + i % w, y0 + i / w)` — the order `LevelLayer.cells`
is stored in, which is why the loader can hand a layer straight over. Two things make it paint
nothing or the wrong thing:

- **A z size of 0.** `new BoundsInt(origin, new Vector3Int(w, h, 0))` contains no cells. The z
  size is 1.
- **An array of the wrong length.** It must be `size.x × size.y × size.z` exactly.

Do not take the order on trust in a project that changed the Grid's swizzle or layout: after the
first `Load`, `TilemapLevelLoader.Verify(level)` reads every cell back with `GetTile` and returns
the number that differ. 0 is the acceptance test.

```csharp
var bounds = new BoundsInt(0, 0, 0, level.width, level.height, 1);
for (int i = 0; i < block.Length; i++)
    block[i] = layer.cells[i] == 0 ? null : tileById[layer.cells[i]];
map.SetTilesBlock(bounds, block);
```

**Colour and transform are locked by the tile unless told otherwise.** A tile's `TileFlags`
(`LockColor`, `LockTransform`) make the Tilemap ignore `SetColor` and `SetTransformMatrix` for
that cell. Either pass `ignoreLockFlags: true` with `TileChangeData`, or clear the flag first
with `SetTileFlags(position, TileFlags.None)`. A rule tile computes its own transform every
refresh, so a transform set on it from outside does not survive the next change beside it.

## Reading tiles

| Call | Returns |
|---|---|
| `GetTile(Vector3Int)` · `GetTile<T>(Vector3Int)` | The tile asset in a cell, or `null` |
| `HasTile(Vector3Int)` | Whether the cell holds anything |
| `GetTilesBlock(BoundsInt)` | A new array in block order |
| `GetTilesBlockNonAlloc(BoundsInt, TileBase[])` | The same into your array; returns the count including `null` entries |
| `GetUsedTilesCount()` · `GetUsedTilesNonAlloc(TileBase[])` | The distinct tile assets on the map |
| `GetColliderType(Vector3Int)` | `Tile.ColliderType` of that cell |

Gameplay that asks "is this cell solid" several times a frame should ask the `LevelData`
(`IsSolid(x, y)` is an array lookup), not the Tilemap. That is the point of keeping the data:
the Tilemap is written to, rarely read.

## Bounds only grow

`cellBounds` (also `origin` and `size`) is the box of cells the Tilemap has allocated. Painting
outside it enlarges it. **Erasing does not shrink it** — a level cleared and repainted smaller
still reports the old box, and anything that iterates `cellBounds.allPositionsWithin` walks the
empty remainder.

- `CompressBounds()` shrinks the box to the cells that hold tiles. Call it after a load, after a
  large erase, and before reading `cellBounds` as "the size of the level".
- `ResizeBounds()` applies an `origin` and `size` you assigned.
- `localBounds` is the same box in local units, for a camera limit or a kill plane.

The level's size is `LevelData.width × height`; `cellBounds` is a property of the rendering.

## Cells and the world

| Call (on the `Grid`, or on any `Tilemap` under it) | Gives |
|---|---|
| `WorldToCell(Vector3)` | The cell containing a world point. It floors: `-0.2` is cell `-1`, never `0` |
| `CellToWorld(Vector3Int)` | The cell's **origin** — its bottom-left corner on a rectangular grid |
| `GetCellCenterWorld(Vector3Int)` | The cell's **centre**. On a `Tilemap` this honours its Tile Anchor; on the `Grid` it is the layout's centre |
| `CellToLocalInterpolated(Vector3)` + `LocalToWorld` | A point between cells: the centre of a 2 × 3 entity |
| `LocalToCell` · `CellToLocal` · `WorldToLocal` | The same in the Grid's local space |

- **Spawning at `CellToWorld` puts everything half a cell down and left.** An entity that
  occupies a cell goes to `GetCellCenterWorld`.
- **Zero the cell's z** for a rectangular or isometric grid. A world point with a stray z
  converts to a cell with that z, and `GetTile` on it finds nothing.
- **Keep every layer's Tile Anchor at (0.5, 0.5)** unless the art demands otherwise, and then
  change all six: layers with different anchors disagree about where a cell's centre is.
- Hexagonal and isometric cell maths — offset, axial and cube coordinates, neighbours,
  distance — is `unity-2d-grid` → `reference/coordinates.md`, not something to rebuild on
  `WorldToCell`.

## Refresh, and rule tiles

Setting a tile makes the Tilemap ask that tile for its data (`TileBase.GetTileData`) and lets
the tile say which other cells must be asked again (`TileBase.RefreshTile`). A rule tile uses
this to refresh its neighbours, which is how painting one cell re-shapes the eight around it.

- `SetTile` on a rule-tile layer already refreshes the neighbours. No manual call is needed.
- `RefreshTile(Vector3Int)` re-asks one cell. Use it when something the tile reads **outside
  the Tilemap** changed — a scripted tile that draws differently by game state.
- `RefreshAllTiles()` re-asks every cell: the whole map's rendering, animation and collider
  data. It belongs after a global change, never inside a loop.
- **Rule tiles match within one Tilemap.** A rule tile on `Ground` does not see a tile on
  `Walls`, so a wall drawn on another layer leaves the ground's edge sprite showing. Either the
  two belong on one layer, or the edge is intended.
- **A block painted in pieces refreshes each seam twice.** Stitching two chunks onto one Tilemap
  re-evaluates the rule tiles along the join, which is correct and is the reason chunk borders
  on rule-tile layers cost more than their area suggests.

`Tilemap.tilemapPositionsChanged` is a static callback carrying the Tilemap and the changed
positions. Before building on it — a minimap, a pathfinding grid kept in sync — subscribe in a
Play Mode test, call `SetTile`, and assert that the callback fired with that cell in the player
configuration you ship. Driving both from the `LevelData` change, as
`TilemapLevelLoader.SetCell` does, needs no callback.

## What a change costs

Three things follow every tile change, and the third is the expensive one.

1. **The cell and whatever it refreshes are re-queried.** Proportional to the cells touched,
   times the neighbourhood for rule tiles.
2. **The renderer rebuilds the chunks those cells are in.** `TilemapRenderer.Mode.Chunk` batches
   by chunk; `Individual` sorts each tile on its own and is the mode sorting by position needs.
3. **The collider catches up later.** A `TilemapCollider2D` accumulates tile changes and
   processes them afterwards — incrementally, or as a **full rebuild once more than
   `maximumTileChangeCount` changes have piled up**. With a `CompositeCollider2D` on top in
   `Synchronous` generation, the composite regenerates when the tilemap collider changes.

Consequences, and the calls that deal with them:

| Situation | Do |
|---|---|
| The runner is placed straight after a load and falls through the floor for a step | `tilemapCollider.ProcessTilemapChanges()` after painting (`hasTilemapChanges` says whether anything is pending). `TilemapLevelLoader.SyncColliders` does it for every layer |
| Many edits in one frame (an explosion, a generator carving) | One `SetTiles` call, not a loop of `SetTile` |
| Edits every frame for seconds (digging) | Set the composite's `generationType` to `Manual` and call `GenerateGeometry()` once per fixed step in which something changed, after `ProcessTilemapChanges()` |
| A level that never changes after load | Nothing: the cost is paid once |
| Destructible tiles in a large static level | Put them on their own Tilemap and collider, so a change regenerates a small shape and not the level's |

Measure before restructuring: `unity-profiling` reads the frame a load or an explosion lands in.
Collider settings, the composite's geometry type and one-way effectors:
`unity-physics-2d` → `reference/tilemap-colliders.md`.

## Checks

- After `Load`: `Verify(level) == 0`, and `map.cellBounds.size` equals the level's size on every
  layer that has tiles.
- After `ClearAllTiles()` and a smaller level: `cellBounds` shrank. If it did not,
  `CompressBounds()` is missing.
- Spawned entities sit in the middle of their cells in the Scene view, not on a corner.
- Break one tile under a standing runner in play: the runner falls on the same or the next
  fixed step. A longer wait means the composite is on `Manual` and nothing calls
  `GenerateGeometry()`.
