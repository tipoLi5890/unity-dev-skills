---
name: unity-2d-level
description: >-
  Put a 2D level together as data: a serialisable level (tile ids, spawn,
  gate, pickups, entities) painted into a fixed stack of Tilemap layers,
  runtime tile edits, rooms and doors, chunks stitched into an endless run,
  Tiled and LDtk import, SpriteShape terrain, seeded generation with
  reachability checked per level. Load for: "load this level from JSON",
  "import my Tiled map", "which Tilemap layers do I need", "no floor collider
  right after SetTile", "generate a level from a seed", "a pickup is
  unreachable", "stitch chunks for an endless runner". Palettes and rule tiles
  are unity-tilemap; collider settings are unity-physics-2d; draw order is
  unity-2d-rendering; cell boards are unity-2d-grid.
---

# unity-2d-level — a level is data with invariants, and the Tilemap is one renderer of it

> **A level that exists only as painted Tilemaps can be looked at and played, and nothing
> else.** It cannot be diffed, generated, converted from another editor, validated outside the
> Editor, or asked "can the runner reach that pickup". Asking a Tilemap "is this cell solid" is
> a native call per cell; its bounds grow when painted and never shrink when erased; and its
> collider catches up with its tiles later in the frame. None of that is a bug — a Tilemap is a
> renderer. The level is the small data structure it was painted from.

```
Tiled .tmj ── tiled_to_level.py ──┐
a generator, from a seed ─────────┼──► level JSON ══ LevelData ──► level_validate.py   exit 1: unreachable
a painted stack ── Export JSON ───┘                      │
                                                         └──► TilemapLevelLoader ──► six Tilemaps + entities
```

| Piece | Knows about | Never knows about |
|---|---|---|
| `resources/LevelData.cs` | size, layers of tile ids, spawn, gate, pickups, entities with fields, its version | `TileBase`, prefabs, scenes |
| `scripts/level_validate.py` | the level file and three jump numbers | Unity |
| `resources/TilemapLevelLoader.cs` | the id → tile table, the six layer names, a spawn delegate | what a sentry does |
| the game's `PickupObjectPool` (`unity-scene-flow`), `SentryBrain` (`unity-game-ai`) | an entity's type, position and fields | which editor the level came from |

Everything that holds levels to their word — "every pickup is reachable", "the same seed gives
the same level", "the gate is never behind a gap wider than the jump" — is a statement about
the data, checked without opening a scene.

---

## 1. Start here

1. **Build the layer stack.** `resources/Editor/TilemapLayerStackBuilder.cs` →
   **Tools ▸ Unity Dev ▸ 2D Level ▸ Build Layer Stack (Side View)** or **(Top-Down)**. It reports
   the Grid, the six Tilemaps, their colliders and sorting, names any sorting or physics layer
   the project lacks, and waits. → `reference/layer-stack.md`
2. **Get one level into data.** Start from `templates/sample-level.json` (a 40 × 12 side run:
   four roofs, a hazard, a ledge, a launch pad, a sentry, three pickups, a gate); or convert a
   Tiled map; or paint the stack and export it. → `reference/level-data.md`
3. **Validate it before it is ever loaded:**

   ```bash
   python3 scripts/level_validate.py templates/sample-level.json \
       --jump-height 2.85 --jump-distance 5.17 --fall-multiplier 1.5
   ```

   Exit 0 with `"verdict":"ok"`. Delete the `launch-1` entity and it exits 1 naming `pickup-2`,
   `pickup-3` and the gate — the third roof is four cells up and the apex is 2.85. The jump
   numbers come from the controller, never from the level: `--metrics metrics.json` reads what
   `unity-gameplay` → `scripts/level_metrics.py` prints.
4. **Load it:**

   ```csharp
   loader.spawnEntity = (entity, position) => _spawner.Spawn(entity.type, position, entity);
   loader.Load(LevelData.FromJson(levelJson.text));    // throws on a bad shape or an unbound tile id
   _runner.position = loader.SpawnPosition;
   ```

   One `SetTilesBlock` per layer, colliders synchronised before `Load` returns, the marker layer
   hidden. → `reference/runtime-tilemap.md`
5. **Prove the rendering is the data**: `loader.Verify(level)` returns 0 mismatched cells. Then
   write the level's rules into `templates/LEVEL_INVARIANTS.md`, one id each.

## 2. Pick the branch

| The level is | What is different | Read |
|---|---|---|
| Hand-built and linear (side run) | Nothing — the five steps above | `reference/layer-stack.md` |
| A graph of rooms with gated doors | Rooms are rectangles at least one screen large; doors are data; the camera listens to a room event | `reference/rooms-and-chunks.md` |
| An endless run | Chunks whose entry height equals the last exit height, pooled, ordered by a seed | `reference/rooms-and-chunks.md` |
| Seen from above (depot) | `Ground` is floor and carries no collider; `Walls` is the only solid layer; reachability is a flood fill | `reference/layer-stack.md` |
| Drawn in Tiled or LDtk | The editor's file is the source; a converter flips the rows once and decodes tile flags | `reference/external-editors.md` |
| Generated | The path is built first and decorated after; every level is checked, not a sample | `reference/procedural.md` |
| Curved, organic ground | A spline with a generated collider, outside the cell search | `reference/sprite-shape.md` |
| A board of rect, isometric or hexagonal cells (sorting yard) | Cells are the gameplay, not just the art | `unity-2d-grid` |

## Load what the situation needs

| The situation | Read |
|---|---|
| Which Tilemaps a level needs, which collide, where each sorts; painting entities as marker tiles | `reference/layer-stack.md` |
| The level file's keys, cell indexing, ids instead of asset references, versions, asset or JSON | `reference/level-data.md` |
| `SetTile` or `SetTiles` or `SetTilesBlock`; a block that painted nothing; bounds that will not shrink; cell to world; the floor missing for one step after a load; breaking tiles in play | `reference/runtime-tilemap.md` |
| Rooms and their enter event, a room graph, soft locks, chunk stitching, the difficulty ramp, additive room scenes | `reference/rooms-and-chunks.md` |
| Tiled and LDtk: what they export, the row flip, global tile ids and flip bits, object anchors, converter or importer package | `reference/external-editors.md` |
| Hills, caves and bridges as splines; corner sprites; the collider a shape generates | `reference/sprite-shape.md` |
| The reach rule the validator applies; generating so the gate is reachable by construction; seeds and determinism | `reference/procedural.md` |
| Creating a Tile Palette, building a rule tile, hex and isometric grid sizing | `unity-tilemap` |
| Composite and tilemap collider settings, one-way effectors, a body that snags on seams | `unity-physics-2d` → `reference/tilemap-colliders.md` |
| Sorting layers and order across the stack; the runner behind and in front of one wall | `unity-2d-rendering` → `reference/sort-order.md` |
| Confining the camera to the current room; a runner camera | `unity-camera` → `reference/follow-2d.md` |
| Gap, ledge, step and door sizes from the controller's numbers | `unity-gameplay` → `reference/level-metrics.md` |
| The motor that walks the level: grounding, slopes, one-way drop-through | `unity-2d-controller` → `reference/platformer.md` |
| Cell coordinates, neighbours, paths and turn order on a board | `unity-2d-grid` → `reference/coordinates.md` |
| Invariant shapes and ids; the seeded generator this pattern extends | `unity-game-brief` → `reference/invariants.md` |
| A journey that plays the level; the 2D never-inside invariant | `unity-play-harness` → `reference/journeys.md` |
| Tiles with gaps or shimmer between them | `unity-2d-pixel-perfect` |

Copy `resources/LevelData.cs`, `TilemapLevelLoader.cs`, `RoomBounds.cs` and `ChunkStitcher.cs`
into a Runtime assembly, and `resources/Editor/TilemapLayerStackBuilder.cs` into an Editor one.
They need the built-in Tilemap and 2D physics modules and no package. The two scripts are
Python 3, standard library only.

---

## Discipline

- **The data is the truth; the Tilemap is painted from it.** Gameplay asks `LevelData.IsSolid`,
  not `Tilemap.GetTile`. A runtime change goes through `TilemapLevelLoader.SetCell`, which
  writes the data and then the tile, so the two cannot drift.
- **Ids, never asset references.** A tile is an integer bound in one table; an entity is a type
  string the game maps to a prefab. A level that references assets cannot be read by a script,
  survive a rename, or arrive after release.
- **Row 0 is the bottom.** That is Tilemap cell space. A converter from an editor that counts
  rows downwards flips once; a level that loads upside down was flipped zero times or twice.
- **Six layers, fixed names.** Collision, drawing in front of the runner and one-way behaviour
  are properties of a layer, not of a tile. A seventh Tilemap is one the loader never paints
  and the validator never reads.
- **Validate the file, then load it.** `LevelData.Problems()` for the shape and
  `scripts/level_validate.py` for reachability, in CI, over every level and every generated
  seed. A level that loads with a hole is found by a player.
- **The jump belongs to the controller.** The validator takes its numbers from the metrics
  file. A level that passes only with a wider jump is a level bug, not a reason to widen it.
- **Paint in blocks, then synchronise the collider.** One `SetTilesBlock` per layer, a z size
  of 1, `ProcessTilemapChanges()` before a body is placed on the result.
- **Generate the path first.** Reachability that holds by construction needs no repair pass;
  the check confirms the construction. One failing seed in a thousand is a generator bug.
- **One seeded `System.Random`, passed down.** Never `UnityEngine.Random`, never the iteration
  order of a set, never the clock. The seed goes in the level id and in every bug report.
- **Check the pair, not the chunk.** Two fair chunks form a join nobody checked; every chunk
  has a flat run-in and run-out, and entry height equals the previous exit height.
- **A room is at least one screen, on tile boundaries, and names no camera.** It raises one
  event; the camera, the spawner and the checkpoint listen.
- **What the cell search cannot see gets a journey.** Curved ground, a wall jump, a pickup
  collected mid-arc: list it as waived with the journey that proves it.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Tile Palettes, rule tiles and their rule order, hexagonal and isometric palette sizing | `unity-tilemap` |
| Slicing the tileset, pivots, 9-slice borders | `unity-2d-sprites` |
| Why the composite is set as it is, effector arcs, bodies that tunnel or snag | `unity-physics-2d` |
| Sorting priority, sorting by position, 2D lights and shadows, parallax | `unity-2d-rendering` |
| The motor that runs and jumps on the level | `unity-2d-controller` |
| Cell coordinates, hexagonal and isometric maths, pathfinding, occupancy, turn order | `unity-2d-grid` |
| Camera rigs, confiners, blends between rooms | `unity-camera` |
| Deriving reach from apex, time to apex and run speed | `unity-gameplay` → `reference/level-metrics.md` |
| Writing the brief's invariants; the lane-run generator | `unity-game-brief` |
| Recorders, situations, journeys that play a level | `unity-play-harness` |
| Hairline gaps between tiles, pixel snapping | `unity-2d-pixel-perfect` |
| Frame cost of a load or a tile edit | `unity-profiling` |

What is left is the part no single-system skill holds: **what a level is when nothing is
drawing it, and the checks that can therefore run on it.**
