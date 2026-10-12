# The layer stack — six Tilemaps under one Grid

> Part of the `unity-2d-level` skill. Which Tilemaps a level is painted on, what each one is
> for, which carry colliders, where each sorts, and the marker layer that is read as data and
> never drawn. `resources/Editor/TilemapLayerStackBuilder.cs` builds it;
> `resources/TilemapLevelLoader.cs` finds the layers by name.

One Tilemap holding everything forces one answer to three questions that have different answers
per tile: does it collide, does it draw in front of the runner, is it a platform. Splitting by
those answers gives a fixed stack, and a fixed stack is what lets a loader, a converter and a
validator agree without configuration.

## The stack

All six are children of one `Grid` and share its cell size. Names are exact: the loader looks
them up with `Transform.Find`.

| Layer | Holds | Collider | Sorting layer / order | Physics layer |
|---|---|---|---|---|
| `Background` | Far walls, skyline, anything the runner never touches and always covers | none | `Background` / 0 | — |
| `Ground` | Side view: the solid mass of the level. From above: the floor | Side view: solid. From above: none | `Floor` / 0 | `Rooftop` (side view) |
| `Walls` | Solid tiles that are not the walked surface: side-view pillars and ceilings; shelving and walls seen from above | solid | Side view: `Floor` / 10. From above: `Actors` / 0, drawn tile by tile | `Rooftop` · `Obstacles` from above |
| `OneWay` | Side view only: platforms stood on from above and passed from below, one cell thick | one-way | `Floor` / 20 | `Platform` |
| `Front` | Decoration drawn over the runner: foreground pipes, door frames, a gate lintel | none | `Overhead` / 0 | — |
| `Markers` | Tiles that mean "an entity goes here"; data, not art | none | `Overhead` / 100 while editing; renderer off in play | — |

The sorting layers, back to front in **Project Settings ▸ Tags and Layers**: `Background`,
`Floor`, `Shadows`, `Actors`, `Overhead`. The runner, sentries and pickups render on `Actors`,
so they draw over everything on `Floor` and under `Overhead` with no order numbers to maintain.

Seen from above, a wall is tall: the runner walks behind it and in front of it, and no fixed
order is right for both. So the top-down stack puts `Walls` on `Actors` with
`TilemapRenderer.Mode.Individual`, where each tile sorts against the runner by position — the
sort axis and pivots that make that work are `unity-2d-rendering` → `reference/y-sort.md`. The
four keys that decide any draw order: `unity-2d-rendering` → `reference/sort-order.md`.

**Sorting layers and physics layers are project settings, not scene objects.** The builder
reads which exist and names the missing ones in its plan; it does not create them. A Tilemap
whose sorting layer is absent lands on `Default`, and one whose physics layer is absent stays
on the `Default` layer — so read the plan's `MISSING` lines before pressing Create, add the
layers, and build again or reassign.

## Colliders

A layer either collides as a whole or not at all. Per-tile exceptions come from the tile asset's
collider type (`Tile.ColliderType.None` on a decorative tile that had to sit on `Ground`), not
from a seventh layer.

| Layer | Components the builder adds |
|---|---|
| Solid (`Ground` in a side view, `Walls`) | `Rigidbody2D` (`Static`) · `TilemapCollider2D` with `compositeOperation = Merge` · `CompositeCollider2D` with `geometryType = Outlines` |
| `OneWay` | the same, with `geometryType = Polygons` · `PlatformEffector2D` (`useOneWay`, `surfaceArc` 170, `useOneWayGrouping`) · `usedByEffector` on the composite |

- **Merge, always.** Unmerged, each tile is its own box and a body sliding across the seams
  catches on internal edges.
- **Solid tiles that touch belong on one Tilemap.** `Ground` and `Walls` are two composites, and
  where a surface runs from one onto the other the join is two edge ends that a body can catch
  on. Keep every surface the runner walks along on `Ground`; `Walls` is for solids it runs
  into or under.
- **An outline is hollow.** A physics query at the centre of a solid block finds nothing, so
  "is this cell solid" is asked of the data — `LevelData.IsSolid(x, y)` — not of the collider.
- **`OneWay` is its own layer because an effector applies to a whole collider.** A one-way tile
  painted on `Ground` is solid from every side.
- **Check the one-way layer once.** With the collider merged, the effector acts on the
  composite, so `usedByEffector` is set there. Prove it in play: a body dropped from above rests
  on the platform, one thrown from below passes through. If it rests both ways, the flag is on
  the wrong collider.

Why each setting is what it is, seams, composite regeneration and the effector's arcs:
`unity-physics-2d` → `reference/tilemap-colliders.md`.

## The marker layer

Painting where things go is faster than typing coordinates, and a tile is a perfectly good way
to say "a pickup here". The `Markers` layer holds one small set of marker tiles — spawn, gate,
pickup, hazard, launch, sentry — each bound to an entity type on the loader's `markers` table.

1. **Paint** markers in the cell the entity occupies.
2. **Read** them once: `TilemapLevelLoader.Capture` turns every marker tile into `spawn`, `gate`,
   an entry in `pickups`, or an entity whose id is its type and cell (`sentry-28-7`).
3. **Hide** the layer: the loader disables the `Markers` renderer on `Load`. The tiles stay in
   the scene for the next edit and never reach the screen.

A marker carries a type and a cell, nothing else. Per-entity values — a sentry's patrol range, a
launch pad's apex — are fields on the entity, edited in the exported JSON or supplied by the
prefab's defaults. When most entities need fields, the level has outgrown markers: author it in
an external editor whose objects carry properties (`reference/external-editors.md`).

Do not solve this with `Tile.gameObject` (a prefab instantiated per painted tile). It works for
ten torches; for entities it hides the level's contents inside tile assets, where no list, no
validator and no save file can see them.

## Building it

**Tools ▸ Unity Dev ▸ 2D Level ▸ Build Layer Stack (Side View)** or **(Top-Down)**. With a Grid
selected it completes that Grid — existing layers are kept untouched, missing ones are added;
with nothing selected it creates a Grid named `Level`. The plan it shows first:

```
Scene: SideRun  (side-view stack)
Create Grid 'Level', rectangular, cell size 1 x 1.
  create  Background  sorting Background / 0  no collider
  create  Ground  sorting Floor / 0  TilemapCollider2D > CompositeCollider2D (outlines) on a static body  physics layer Rooftop
  create  Walls  sorting Floor / 10  TilemapCollider2D > CompositeCollider2D (outlines) on a static body  physics layer Rooftop
  create  OneWay  sorting Floor / 20  TilemapCollider2D > CompositeCollider2D (polygons) > PlatformEffector2D (one-way, arc 170)  physics layer Default
  create  Front  sorting Overhead / 0  no collider
  create  Markers  sorting Overhead / 100  no collider
MISSING physics layer 'Platform': its Tilemaps stay on Default — add it, then set the objects' layer and the runner's ground mask.
```

From a script, `TilemapLayerStackBuilder.Plan(grid, options)` returns that text and
`Build(grid, options)` does the work without asking; `Options` carries the sorting-layer and
physics-layer names for a project that calls them something else.

The top-down stack differs in three rows: `Ground` has no collider (it is floor), `Walls` goes
on `Actors` in individual mode with the `Obstacles` physics layer, and there is no `OneWay`
layer. Hexagonal and isometric boards do not use this builder — their Grid layout,
cell size and sort axis come from `unity-tilemap` → `reference/palette-and-grid.md`, and their
cells from `unity-2d-grid` → `reference/coordinates.md`.

## Checks

- Every child of the Grid is one of the six names. A seventh Tilemap is a layer the loader
  never paints and the validator never reads.
- The runner's ground mask includes the physics layers of `Ground`/`Walls` and `OneWay`, and
  nothing else in the scene uses those layers.
- In play, the `Markers` object's `TilemapRenderer` is disabled and its tiles are still there:
  hidden, not deleted.
- A solid layer's `CompositeCollider2D.pathCount` is the number of separate islands of tiles,
  not the number of tiles.
