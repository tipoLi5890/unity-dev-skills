---
name: unity-2d-grid
description: >-
  Board logic for tactics games and tile puzzles on rectangular, isometric and
  hexagonal grids, as plain C# with no scene: hexagonal offset, axial and cube
  conversion for Unity's layout, movement range by flood, A* paths, lines of
  sight, one occupancy map, push rules, turn order, undo, pointer to cell.
  Load for: "the unit steps sideways on every other hex row", "the
  move range goes through walls", "the path clips the wall corner", "I clicked
  the crate and got the cell behind it", "undo leaves the pickup behind", "two
  units ended on one cell". Grid layouts and palettes are unity-tilemap;
  tweening the transform is unity-2d-controller; level files are
  unity-2d-level; NavMesh is unity-navigation.
---

# unity-2d-grid — the cell map is the truth and the transform is an animation of it

> **A piece is in its new cell from the instant the rule says so; the sprite gets there 0.12 s
> later.** Every rule — may I step, what is in range, who is hit, is it solved — reads a map of
> cells and answers at once. Nothing in the rules reads `transform.position`, waits for a tween or
> asks a collider. The scene only ever *shows* a board that has already changed.

That one decision is what makes the rest cheap: undo is a stack of small records, a solver is a
loop over board states, and the whole rule set runs in an EditMode test before a sprite exists.
Break it once — one rule that rounds a transform to find a cell — and a piece caught mid-tween is
in two cells, or in none.

```
input ──► command ──► BOARD (cells, occupants, turn) ──► what changed ──► presenter ──► transforms
          step E      GridOccupancy · TurnQueue          StepRecord       tween to GetCellCenterWorld
                      GridCoords · GridPathfinder                         highlight Tilemap
                      ▲ rules read only this                              ▲ reads the board, never the reverse
```

| Layer | Knows about | Never knows about |
|---|---|---|
| `resources/GridCoords.cs` | neighbours, distances, hexagonal conversions, rings, lines | world units, the `Grid` component |
| `resources/GridPathfinder.cs` | cheapest path, movement range, per-unit cost | who the unit is, what a turn is |
| `resources/GridOccupancy.cs` | walls, one occupant per cell, push, reservation, revert | sprites, tweens, colliders |
| `resources/TurnQueue.cs` | initiative order, the round, who acts now | what an action does |
| the game's presenter | `Grid.GetCellCenterWorld`, tweens, highlight tiles | the rules |

All four are pure C# with no `MonoBehaviour`. Cells are `UnityEngine.Vector3Int` with z = 0, the
value `Grid.WorldToCell` and `Tilemap.GetTile` already speak, so nothing is converted at the edge
and EditMode tests run them with no scene. In an assembly with `noEngineReferences`, swap it for a
struct of your own; `TurnQueue.cs` uses no engine type at all.

---

## 1. Pick the neighbour rule first

It decides the range shape, the heuristic and the line of sight, and it is expensive to change.

| Board | `GridShape` | Neighbours | Distance | A unit with 3 move points reaches |
|---|---|---|---|---|
| Rectangular, orthogonal moves | `Rect4` | 4 | Manhattan | a diamond of 25 cells |
| Rectangular, diagonal is one step | `Rect8`, `DiagonalWeight = 10` | 8 | Chebyshev | a square of 49 cells |
| Rectangular, diagonal costs more | `Rect8`, `DiagonalWeight = 14` | 8 | octile | an octagon of 29 cells |
| Isometric, isometric Z as Y | `Rect4` or `Rect8` | as above | as above | the same, drawn rotated |
| Hexagonal, point-top or flat-top | `Hex` | 6 | cube distance | a hexagon of 37 cells |

**Isometric is a drawing convention, not a neighbour rule**: the cell indices and every rule are
the rectangular ones. **Hexagonal is a neighbour rule**: Unity addresses hexagonal cells by
*offset* coordinates, so `cell + (0, 1)` is up-left on one row and up-right on the next. Route
every neighbour lookup through `GridCoords.Neighbour(shape, cell, direction)` and no rule ever
learns which grid it is on.

## 2. Prove the hexagonal layout once

Unity's `Hexagon` layout shifts rows whose y is odd half a cell along +x; flat-top is the same
layout with swizzle `YXZ`, so the same cells and the same conversion, turned. Confirm it on the
project's own `Grid` before any rule depends on it — one line in the Editor:

```csharp
var g = Object.FindAnyObjectByType<Grid>();
Debug.Log(g.GetCellCenterWorld(new Vector3Int(0, 1, 0)) - g.GetCellCenterWorld(Vector3Int.zero));
// point-top, cell size (0.866, 1, 1), Grid at the origin, unscaled →  (0.43, 0.75, 0.00)
```

A positive x (point-top) means odd rows shift toward +x, which is what `OffsetToCube` assumes by
default. A negative one means pass `oddShifted: false` everywhere. The flat-top expectation, the
cell-size layouts and the isometric checks are in `reference/coordinates.md`.

## 3. Build the board before the scene

1. **Copy the four resources** into the assembly that holds the rules, and
   `resources/Tests/GridCoordsTests.cs` into an EditMode test assembly. Run the tests; they need
   no scene.
2. **Write the board as one class** that owns a `GridOccupancy` (and a `TurnQueue` for tactics)
   and exposes commands that return what changed:

```csharp
// YardBoard — the sorting yard's rules. Plain C#; the scene is not involved.
public sealed class YardBoard
{
    public const int RunnerId = 1;
    public readonly GridOccupancy Cells = new GridOccupancy();
    public readonly HashSet<Vector3Int> Gates = new HashSet<Vector3Int>();
    public readonly GridShape Shape;
    readonly Stack<StepRecord> _undo = new Stack<StepRecord>();

    public YardBoard(GridShape shape) { Shape = shape; }

    public StepRecord Step(int direction)                     // 0 .. NeighbourCount - 1
    {
        Vector3Int to = GridCoords.Neighbour(Shape, Cells.CellOf(RunnerId), direction);
        Vector3Int beyond = GridCoords.Neighbour(Shape, to, direction);
        StepRecord step = Cells.StepOrPush(RunnerId, to, beyond);
        if (step.Result != StepResult.Blocked) _undo.Push(step);
        return step;                                          // the presenter animates exactly this
    }

    public bool Undo(out StepRecord undone)
    {
        undone = default;
        if (_undo.Count == 0) return false;
        undone = _undo.Pop();
        Cells.Revert(undone);
        return true;
    }

    public int PickupsOnGates { get { int n = 0; foreach (Vector3Int g in Gates) if (Cells.IsPushable(Cells.OccupantAt(g))) n++; return n; } }
    public bool Solved => PickupsOnGates == Gates.Count;
}
```

3. **Test the rules in EditMode**: a step into a wall changes nothing; a push moves one pickup one
   cell; two pickups in a row do not move; undo after N steps restores the first board exactly.
4. **Then the scene.** One `Grid`; load the board and the Tilemaps from one source —
   `unity-2d-level` → `reference/level-data.md`. The presenter turns each `StepRecord` into
   tweens toward `Grid.GetCellCenterWorld(cell)`. The mover in `unity-2d-controller` →
   `reference/grid-step.md` speaks `Vector2Int` and asks through delegates, so adapt at the edge:
   `mover.CanEnter = (from, to) => board.Cells.CanEnter(new Vector3Int(to.x, to.y, 0));`
5. **Expose the logical state, not the transform**, to the probe:
   `GameProbe.Register("cell", () => $"{c.x},{c.y}")`, `GameProbe.Count("pickupsOnGates", …)`,
   `GameProbe.Register("turn", …)`. A journey then asserts that the transform sits at the centre
   of the cell the probe reports whenever no tween is running, and that a blocked step changed
   neither.

## 4. Range, path, sight — three different questions

| Question | Answer | Not |
|---|---|---|
| Where can this unit move this turn? | `GridPathfinder.Range`: a flood through the unit's cost delegate, stopped by walls and budget | "every cell within distance N" — that walks through walls |
| How does it get there? | `GridPathfinder.FindPath`, or `PathFromRange` after a `Range` with no second search | a smoothed path: on a board the path *is* the list of cells |
| What can it hit or see? | `GridCoords.Ring` / `Disc` for reach, then a line (`Supercover`, `HexLine`) for sight | the movement flood: an archer shoots over a gap it cannot cross |

The heuristic must match the neighbour rule or A* returns a path that is quietly not the shortest;
`GridPathfinder` picks it from the shape, and `A_star_agrees_with_the_flood_on_every_shape` is the
test that catches a mismatch.

## Load what the situation needs

| The situation | Read |
|---|---|
| Cell vs world, cell centre vs cell origin, hexagonal offset ↔ axial ↔ cube, the flat-top turn, isometric and Z as Y, `Vector3Int` or a struct of your own | `reference/coordinates.md` |
| "It steps sideways on every other row"; 4, 8 and 6 neighbours; Manhattan, Chebyshev, octile, hex distance; movement range with terrain cost; attack rings and lines | `reference/neighbours-and-range.md` |
| A* on a board, the heap, heuristics per metric, "the path clips the corner", units that block or pass each other, reusing buffers, is this push puzzle solvable | `reference/pathfinding.md` |
| Can this cell see that one; a line through a corner; hexagonal lines; field of view; fog of war | `reference/line-of-sight.md` |
| "Two units ended on one cell"; moves that resolve together; the push rule; turn order and initiative; undo; enemy turns; keeping the rules free of the engine | `reference/occupancy-and-turns.md` |
| Pointer to cell; "I clicked the crate and got the cell behind it"; hexagonal picking; highlighting a range | `reference/picking.md` |
| Grid cell layouts, cell size per layout, swizzle, palettes | `unity-tilemap` → `reference/palette-and-grid.md` |
| Moving the transform from cell to cell, the step tween, input buffered during it | `unity-2d-controller` → `reference/grid-step.md` |
| Board layout as data, loading Tilemaps from it, validating a level file | `unity-2d-level` → `reference/level-data.md` |
| Draw order on an isometric board; a piece that draws over the tile in front of it | `unity-2d-rendering` → `reference/y-sort.md` |
| One step per press, hold to repeat, the pointer position | `unity-input` → `reference/reading-input.md` |
| Rules in an assembly that cannot see the engine | `unity-game-brief` → `reference/sim-presentation-split.md` |
| A camera that pans inside the board's bounds | `unity-camera` → `reference/follow-2d.md` |
| A journey over a scripted move list; the sorting-yard situation | `unity-play-harness` → `reference/journeys.md` |
| Which numbers a tactics game or a tile puzzle has to fix first | `unity-gameplay` |

---

## Discipline

- **Rules read the board, never a transform.** A `WorldToCell(transform.position)` inside a rule
  is the bug; mid-tween it names a cell the piece has already left.
- **The board changes in one call, at once.** A piece that takes 0.12 s to arrive holds its
  destination from the first instant and its origin not at all.
- **One occupant map.** A second dictionary "for enemies" is how two units end on one cell.
- **One neighbour function.** No rule adds an offset to a cell. On hexagons that is wrong on every
  second row; on rectangles it hard-codes a shape you will want to change.
- **Convert at the edges, compute in cube.** Hexagonal distance, lines, rings and rotation are
  cube arithmetic. Offset coordinates are for storage and for `Grid`.
- **`& 1`, not `% 2`.** `-1 % 2` is `-1` in C#; a conversion using it breaks on negative rows
  only, which is the half of the board nobody tested.
- **Movement range is a flood, attack range is a metric.** Mixing them is how a unit walks through
  a wall, or cannot shoot across a gap.
- **Diagonals: decide once.** Either they are not neighbours, or they are and the range is a
  square, or they cost 14 and the heuristic is octile. A Manhattan range with diagonal steps lets
  a unit go further diagonally than straight.
- **A fixed neighbour order.** The same board must give the same path every run; a journey that
  replays a recorded path depends on it.
- **Keep the cost delegate and the lists.** A lambda written inside the call allocates a closure
  per search; a field does not.
- **Undo stores what changed, not the board.** A step is two cells and an id. Revert newest first.
- **Resolve a turn on the board, then animate it.** Ten sentries walking four cells at 0.12 s a
  cell in sequence is 4.8 s a round; the rules finish in a frame and the presenter overlaps the
  tweens.
- **Run the EditMode tests before opening the scene.** A board bug found in play mode costs a
  domain reload per attempt.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Creating a `Grid`, palettes, cell size per layout, rule tiles | `unity-tilemap` |
| Tweening a transform between cells, step timing, platformer and free top-down movement | `unity-2d-controller` |
| Level files, loading Tilemaps at run time, external level editors | `unity-2d-level` |
| Sorting layers, the isometric sort axis, 2D lights | `unity-2d-rendering` |
| Colliders, triggers and physics queries on a Tilemap | `unity-physics-2d` |
| Step and undo actions, key repeat, touch, pointer position | `unity-input` |
| Pathfinding on a NavMesh, agents, obstacles | `unity-navigation` |
| Board camera, bounds, zoom | `unity-camera` |
| Move and action menus, the turn-order strip, range legend | `unity-game-ui` |
| Step and push as animation states | `unity-animation` |
| Skeletal 2D characters on the board | `unity-2d-animation` |
| Recorders, situations, journeys | `unity-play-harness` |
| Assembly definitions, an engine-free rules assembly | `unity-game-brief` → `reference/sim-presentation-split.md` |
| Sending turns over the network | `unity-multiplayer` |
