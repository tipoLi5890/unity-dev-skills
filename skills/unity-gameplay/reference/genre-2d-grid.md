# 2D by the cell — tactics, tile puzzle, isometric and hexagonal boards

> Part of the `unity-gameplay` skill. Types where position is a cell index and time is a move or
> a turn. Worked setting: the **sorting yard** — the runner steps cell to cell and pushes pickups
> onto gate cells, on a rectangular, isometric or hexagonal board.

## The constraints

| Constraint | Tile puzzle | Tactics | The same on isometric or hexagonal cells |
|---|---|---|---|
| View · projection | Top-down · orthographic | Top-down or isometric · orthographic | Isometric is a drawing convention; hexagonal is a neighbour rule. Neither changes the rules engine |
| Movement model | One cell per input | A path of cells per action, limited by a range | Unchanged |
| Transform owner | **The board.** The transform is tweened to where the board already says the piece is | The same | The same |
| Time | A move; fully undoable | A turn made of actions; an order of actors | Unchanged |
| Camera | Fixed if the board fits; otherwise pans inside bounds | Pans and zooms inside bounds; recentres on the acting unit | Bounds are a diamond or a staggered rectangle in world space |
| Level unit | Cell | Cell, with height or terrain cost per cell | Cell |
| Level is | A board state plus a goal; must be solvable | A board plus spawn cells; must be connected | — |

Underneath all of them: **the board is the fact and the scene is its animation.** Every rule is
evaluated on cell coordinates, instantly; nothing in the rules waits for a tween, reads a
`transform.position`, or asks a collider. This is the simulation/presentation split in its purest
form — `unity-game-brief` → `reference/sim-presentation-split.md` — and it is what makes undo,
solvers and EditMode tests free.

## Numbers to decide first

| Number | Sorting-yard start | Decides |
|---|---|---|
| Cell layout · cell size | Rectangle `(1, 1)` · isometric `(1, 0.5)` · hexagon point-top `(0.866, 1)` | Art dimensions; set once, in the `Grid` |
| Board size | 9 × 7 cells — fits a 16:9 screen at orthographic size 4 with a HUD margin | Whether the camera ever moves |
| Step tween | 0.12 s per cell, eased out | Feel; input arriving during a tween is buffered one deep |
| Hold-to-repeat | first repeat after 0.25 s, then every 0.12 s | Whether crossing the board is one hold or nine presses |
| Neighbour rule | 4 (rectangle), 6 (hexagon); 8 only if diagonals cost the same or you price them | Range shapes, heuristics, line of sight |
| Tactics: move range · turn order | 4 cells · fixed order by initiative | Board size relative to range: about 3 × range across |
| Undo depth | Unlimited within a level | Memory is trivial: a move is two cells and a flag |

## Build order for the 3C prototype

1. **The board, with no scene.** A plain C# class holding walls, gates, pickups and the runner as
   cells, with `TryMove(direction)` returning what changed. Test it in EditMode before a single
   sprite exists.
2. **The grid in the scene.** One `Grid` with the chosen layout; a floor Tilemap and a wall
   Tilemap — `unity-tilemap`. Load the board *from* the Tilemaps once at start, or load both from
   one data file; never let them be edited independently.
3. **Controls.** A struct with one `step` direction per press and `undo` — `unity-input`. For a
   pointer: pick a cell, below.
4. **Presentation.** On each successful move, tween the affected transforms to
   `Grid.GetCellCenterWorld(cell)`. Register the *logical* state with the probe:
   `GameProbe.Register("cell", () => $"{_board.Runner.x},{_board.Runner.y}");` and
   `GameProbe.Count("pickupsOnGates", () => _board.PickupsOnGates);`
5. **Journey 1 — the step.** Enter the yard-step situation, feed a scripted move list, and
   assert after each tween settles that the transform is at the centre of the cell the probe
   reports, and that a move into a wall changed neither.
6. **Camera.** Fixed, or panning inside bounds — `unity-camera` → `reference/follow-2d.md`.
7. **Journey 2 — solve it.** Feed the known solution; assert `pickupsOnGates` reaches the gate
   count and the state becomes `Solved`.

### The board, in essentials

```csharp
// YardBoard.cs — plain C#, no MonoBehaviour, so an EditMode test can run it with no scene.
// Cells are Vector3Int with z = 0, the type Grid and Tilemap already use; in an assembly with
// noEngineReferences, swap it for a two-int struct of your own.
using System.Collections.Generic;
using UnityEngine;

public class YardBoard
{
    public readonly HashSet<Vector3Int> Walls = new(), Gates = new(), Pickups = new();
    public Vector3Int Runner;
    readonly Stack<(Vector3Int dir, bool pushed)> _undo = new();

    public int PickupsOnGates { get { int n = 0; foreach (var p in Pickups) if (Gates.Contains(p)) n++; return n; } }
    public bool Solved => PickupsOnGates == Gates.Count;

    /// <summary>One step. Returns false, changing nothing, when the move is not legal.</summary>
    public bool TryMove(Vector3Int dir)
    {
        Vector3Int to = Runner + dir;
        if (Walls.Contains(to)) return false;
        bool pushed = Pickups.Contains(to);
        if (pushed)
        {
            Vector3Int beyond = to + dir;        // one pickup, one cell, never into anything
            if (Walls.Contains(beyond) || Pickups.Contains(beyond)) return false;
            Pickups.Remove(to); Pickups.Add(beyond);
        }
        _undo.Push((dir, pushed));
        Runner = to;
        return true;
    }

    public bool Undo()
    {
        if (_undo.Count == 0) return false;
        var (dir, pushed) = _undo.Pop();
        if (pushed) { Pickups.Remove(Runner + dir); Pickups.Add(Runner); }
        Runner -= dir;
        return true;
    }
}
```

`Runner + dir` is a neighbour only on a rectangular board. On a hexagonal one the six neighbour
offsets depend on the row — route every neighbour lookup through one function, below.

### Coordinates

- **Rectangle.** `Grid.WorldToCell`, `Grid.CellToWorld`, `Grid.GetCellCenterWorld`. Neighbours
  are `(±1, 0)` and `(0, ±1)`. Distance is Manhattan: `|dx| + |dy|`.
- **Isometric.** The same cell indices and the same neighbours; only the picture is rotated.
  Rules written for the rectangle run unchanged. What changes is drawing: the `Grid` layout is
  `Isometric` with cell size `(1, 0.5, 1)`, and screen-up is cell `(+1, +1)`, so map the
  D-pad deliberately — up as `(0, +1)` (screen up-left) or as `(+1, +1)` (two cells, not a
  neighbour). Decide and write it in the recipe.
- **Hexagon.** Unity addresses hexagonal cells by **offset** coordinates: alternate rows are
  shifted half a cell, so the neighbours of a cell depend on whether its row is odd. Check which
  rows shift before writing the table: read `GetCellCenterWorld` for `(0, 0)` and `(0, 1)`; if
  the second is half a cell to the right, odd rows shift right. Then do all arithmetic in cube
  coordinates and convert at the edges:

  ```csharp
  // Offset (odd rows shifted right, point-top) → cube. q + r + s == 0 always.
  static Vector3Int ToCube(Vector3Int c) { int q = c.x - (c.y - (c.y & 1)) / 2; return new(q, c.y, -q - c.y); }
  static Vector3Int ToOffset(Vector3Int h) => new(h.x + (h.y - (h.y & 1)) / 2, h.y, 0);
  static int Distance(Vector3Int a, Vector3Int b) =>
      (Mathf.Abs(a.x - b.x) + Mathf.Abs(a.y - b.y) + Mathf.Abs(a.z - b.z)) / 2;   // cube in, cells out
  static readonly Vector3Int[] CubeDirs = { new(1,0,-1), new(1,-1,0), new(0,-1,1), new(-1,0,1), new(-1,1,0), new(0,1,-1) };
  ```

  Neighbours are `ToOffset(ToCube(c) + CubeDirs[i])`. Range is every cell with cube distance
  within N. A straight line is a linear interpolation between two cube coordinates, rounded.

### Range, paths and sight

- **Movement range** is a breadth-first flood from the unit, stopping at the range or at a
  blocked cell — not "every cell within distance N", which walks through walls. With terrain
  costs it becomes Dijkstra with the same stopping rule.
- **A path** is A*. The heuristic must match the neighbour rule or paths go wrong quietly:
  Manhattan for 4 neighbours, cube distance for hexagons, octile for 8. Visit neighbours in one
  fixed order so the same board always yields the same path — a journey depends on it.
- **Line of sight** on a rectangle is a Bresenham walk between the two cells; on hexagons, the
  cube interpolation above. Decide whether a line that passes exactly through a corner is
  blocked, write it down, and test both diagonals.
- **Occupancy** is one dictionary from cell to occupant, updated in the same call that moves the
  piece. A unit "moving" for 0.12 s occupies its destination from the first instant.
- **Solvability** of a puzzle board is a breadth-first search over board states (runner cell
  plus the sorted pickup cells), run in an EditMode test or an Editor menu, not at runtime.

### Picking a cell with a pointer

```csharp
Vector3 world = _camera.ScreenToWorldPoint(pointerScreenPosition);
world.z = 0f;                                  // an orthographic ray is parallel to z
Vector3Int cell = _grid.WorldToCell(world);
```

On an isometric board with tall tiles the cell under the pointer is not the tile drawn under
the pointer — a tall crate covers the cell behind it. Test candidates from the front row back
and take the first whose sprite bounds contain the pointer.

## Traps

- **Reading `transform.position` in a rule.** Mid-tween it names a cell the piece is not in. The
  rules read the board; only the presenter reads transforms.
- **Accepting input during a tween without a buffer** drops moves; accepting it without a limit
  queues six moves the player cannot see. One deep.
- **Isometric tiles drawn inside out.** The palette and the scene both need a custom sort axis —
  `unity-tilemap` → `reference/palette-and-grid.md` for the palette. In the scene, set the
  renderer's Transparency Sort Mode to `Custom Axis` with `(0, 1, 0)`; with Z as Y, start from
  `(0, 1, -0.26)`, then walk a sprite behind a raised tile and read the screenshot.
- **Sprites and tiles sorting separately on an isometric board.** Put the pieces and the tall
  tiles on one sorting layer, pivots at the base, and the tall-tile Tilemap in `Individual` mode.
- **Hexagon neighbours hard-coded for even rows.** Every second row then steps sideways. Convert
  to cube, add, convert back.
- **Diagonals on a rectangle with Manhattan range.** Either diagonals are not neighbours, or
  they are and the range shape is a square, not a diamond. Mixing them is how a unit moves
  further diagonally than straight.
- **A board edited in the Tilemap and a level file that disagree.** One source: the Tilemap is
  either the authoring tool that exports the data, or a view built from the data. Never both.
- **Tactics: animating a whole enemy turn in sequence at 0.12 s a cell** makes a ten-unit turn
  take half a minute. Resolve the turn on the board at once, then play the animations
  overlapped or at a multiple.

## Where each need is answered

| Need | Answer |
|---|---|
| Step and undo actions, hold-to-repeat, pointer position | `unity-input` → `reference/reading-input.md` |
| Tap and drag on a phone | `unity-input` → `reference/touch-and-on-screen.md` |
| A fixed or panning camera with bounds | `unity-camera` → `reference/follow-2d.md` |
| Palettes for rectangular, hexagonal and isometric grids | `unity-tilemap` → `reference/palette-and-grid.md` |
| Rule tiles on a hexagonal grid | `unity-tilemap` → `reference/hexagonal-rule-set.md` |
| Isometric sheets, per-cell pivots | `unity-2d-sprites` |
| A step and a push as animation states | `unity-animation` → `reference/sprite-state-graph.md` |
| Rules in an engine-free assembly, EditMode tests | `unity-game-brief` → `reference/sim-presentation-split.md` |
| Journeys over a scripted move list | `unity-play-harness` → `reference/journeys.md` |
| Coordinates, range, paths, sight, occupancy, picking | this file |
| Turn order | this file: a list of actors sorted once per round; an index advances; an actor that leaves is removed at the index, not after it. Expose `turn` and `actor` to the probe |
| Enemy turns | this file: score every reachable cell (distance to target, cover, damage dealt) on the board, pick the best with a fixed tie-break, then animate |
| Move and action menus, range highlights | `unity-game-ui`; highlights are tiles on a third Tilemap, cleared and refilled per selection |
