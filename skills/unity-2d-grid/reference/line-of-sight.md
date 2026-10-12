# Line of sight — which cells a line touches, and what a unit can see

> Part of the `unity-2d-grid` skill. Sight on a board is a question about cells, answered with
> integer arithmetic: no raycast, no collider, the same answer on every machine. The line
> functions are in `resources/GridCoords.cs`.

## Two questions, two tools

| Question | Tool | Cost |
|---|---|---|
| Can **this** cell see **that** one? (a sentry aiming at the runner) | One line between the two cells | Tens of cells |
| What can this unit see **at all**? (fog of war, a vision cone) | A field-of-view sweep | Every cell within the radius, once |

Running the first for every cell in a radius answers the second, slowly and with artefacts: a
cell far behind a pillar flickers in and out as the line's rounding changes. Use the sweep.

## A line between two rectangular cells

Three candidates, and they disagree at corners:

```
Bresenham (0,0)→(4,2)      Supercover (0,0)→(4,2)       X = in the line
. . . . X                  . . . X X
. . X X .                  . X X X .
X X . . .                  X X . . .
5 cells                    7 cells
```

| Line | Function | Cells | Use for |
|---|---|---|---|
| **Bresenham** | `GridCoords.Line(a, b, into)` | Exactly `max(|dx|, |dy|) + 1`: one per step along the long axis | A projectile's cells, a beam drawn cell by cell, the cells an area effect travels through |
| **Supercover** | `GridCoords.Supercover(a, b, into)` | Every cell the segment between the two centres passes through | Line of sight: a wall the segment grazes blocks it |
| **Supercover, corners closed** | `GridCoords.Supercover(a, b, into, includeCornerCells: true)` | The above plus both cells at any corner the segment passes exactly through | Line of sight when a diagonal gap between two walls must be opaque |

Bresenham steps diagonally between two cells that only touch at a corner, so a sentry "sees"
through the joint of two walls set diagonally. That is right for an arrow's path across open
floor and wrong for vision.

```csharp
readonly List<Vector3Int> _line = new List<Vector3Int>(32);

bool CanSee(Vector3Int from, Vector3Int to)
{
    _line.Clear();
    GridCoords.Supercover(from, to, _line, includeCornerCells: true);
    for (int i = 1; i < _line.Count - 1; i++)          // the ends never block themselves
        if (_cells.IsWall(_line[i])) return false;
    return true;
}
```

### The corner rule is a design decision

A line from `(0, 0)` to `(2, 2)` passes exactly through the corner shared by `(1, 0)` and
`(0, 1)`. Decide what that means and write it in the recipe:

| Rule | With `includeCornerCells` | Reads as |
|---|---|---|
| Blocked if **either** corner cell is a wall | `true`, any wall blocks | Strict; no peeking round a corner. Matches `CutCorners = false` in the pathfinder |
| Blocked only if **both** are walls | `true`, then count: block when both corner cells of one crossing are walls | A unit at a corner sees along the wall; a diagonal wall is still solid |
| Never blocked by corners | `false` | Permissive; a diagonal wall leaks |

Whatever the choice, **movement and sight use the same one**. A unit that can step somewhere
it cannot see, or see through a gap it cannot step through, reads as a bug every time.

### Symmetry

If A sees B, B must see A, or a sentry shoots a runner who cannot shoot back. Both functions
are symmetric as cell **sets**: `Line` always traces from the lesser endpoint and reverses the
result when asked for the other direction, and `Supercover` is exact integer arithmetic on one
segment. A hand-rolled Bresenham traced
from `a` each time is not — for some pairs the two directions round a tie different ways and
differ by a cell.

`Lines_connect_their_ends_and_read_the_same_both_ways` in `resources/Tests/GridCoordsTests.cs`
checks both over a block of endpoints.

## A line between two hexagons

Convert both to cube, step `distance` times along the straight line between them, round each
sample to the nearest hexagon — `GridCoords.HexLine(a, b, into)`:

```csharp
int n = CubeDistance(ca, cb);
for (int i = 0; i <= n; i++)
{
    double t = (double)i / n;
    cube = CubeRound(Lerp(ca.q, cb.q, t) + 1e-6, Lerp(ca.r, cb.r, t) + 2e-6, Lerp(ca.s, cb.s, t) - 3e-6);
}
```

The result is `distance + 1` hexagons, each a neighbour of the last. The three small constants
are the **nudge**: a line that runs exactly along the edge between two hexagons puts a sample
at equal distance from both, and floating-point noise would then pick differently on different
runs. The nudge pushes every such sample to the same side. It sums to zero so the point stays
on the cube plane.

Two consequences to know:

- Along an edge, the line picks **one** of the two hexagons. `otherSide: true` nudges the
  opposite way and returns the second candidate. For strict sight require both lines clear; for
  a generous rule, either. Lines that never run along an edge come out identical.
- The nudge is the same whichever end the line starts from, so `HexLine(a, b)` and
  `HexLine(b, a)` hold the same cells and sight is symmetric.

Offset `(0, 0)` to `(3, 2)` gives `(0,0) (0,1) (1,1) (2,2) (3,2)`.

## Field of view — symmetric shadowcasting, in outline

The sweep that answers "what can this unit see" in one pass, with the property that A sees B
exactly when B sees A. On a rectangular board:

1. **Split the surroundings into four quadrants** (N, E, S, W), each a 90° wedge. A quadrant
   maps `(depth, col)` to a cell: depth is the distance out along the quadrant's axis, col runs
   across it from `−depth` to `+depth`.
2. **Scan row by row outward**, each row carrying a start slope and an end slope (initially −1
   and +1). A row at depth `d` covers the columns from `floor(d · start + 0.5)` to
   `ceil(d · end − 0.5)`.
3. **For each cell in the row:**
   - it is **visible** if it is a wall, or if it is floor and its centre lies inside the
     slopes: `col ≥ d · start` and `col ≤ d · end`. That centre test is what makes the result
     symmetric;
   - when the scan passes from a wall to floor, the row's start slope becomes the slope of the
     floor cell's near edge: `(2·col − 1) / (2·d)`;
   - when it passes from floor to a wall, a **child scan** starts at depth `d + 1` with the
     current start slope and an end slope of the wall's near edge, `(2·col − 1) / (2·d)`.
4. **If the row ends on floor**, continue to depth `d + 1` with the row's slopes. Stop at the
   vision radius or the board's edge.

Keep slopes as **fractions of integers** (numerator and denominator), not floats: a float slope
makes one cell flicker at long range. Use an explicit stack of `(depth, start, end)` rather than
recursion so a long corridor cannot overflow, and reuse the stack and the output set.

The output is a `HashSet<Vector3Int>` of visible cells. Cost is proportional to the cells
inside the radius; radius 8 is about 200 cells, so every unit can recompute when it moves.

| Variant | Change |
|---|---|
| A vision cone (the depot sentry) | Run the sweep, then keep cells whose direction from the sentry is inside the cone — or scan only the quadrants the cone touches and clamp the first row's slopes |
| A vision radius that is round, not square | Drop cells with `dx² + dy² > (r + 0.5)²` from the result |
| Tall cover that blocks sight but not shots | Two wall predicates, two sweeps |
| Hexagonal board | The same idea in six 60° sextants is workable and fiddly. For radii up to about 6, a `HexLine` from the unit to every hexagon on the ring at the radius, marking cells until the first wall, is simpler and good enough; it costs `6r` lines of `r` cells |

## Fog of war is a set of cells

Three states per cell, held in two sets — nothing about fog lives in the renderer:

| State | Membership | Drawn |
|---|---|---|
| Unseen | in neither set | black |
| Remembered | in `_explored`, not in `_visible` | dimmed; shows terrain, hides units |
| Visible | in `_visible` | normal |

```csharp
readonly HashSet<Vector3Int> _visible = new HashSet<Vector3Int>(), _explored = new HashSet<Vector3Int>();

void RecomputeVision()                       // when any friendly unit changes cell, never per frame
{
    _visible.Clear();
    foreach (int id in _friendlyIds) FieldOfView(_cells.CellOf(id), radius: 6, _visible);
    _explored.UnionWith(_visible);
}
```

- **Rules read the sets**: an enemy outside `_visible` cannot be targeted, and the enemy's own
  planner reads *its* side's set. Never ask the fog Tilemap what is hidden.
- **The presenter draws the difference.** A fog Tilemap above the board: an opaque tile on
  unseen cells, a half-transparent one on remembered cells, none on visible ones. Update only
  the cells whose state changed since the last recompute — keep the previous `_visible` and
  diff — or one move repaints the whole map.
- **Units on remembered cells are hidden**: the presenter disables the renderer of any piece
  whose cell is not in `_visible`. Its occupancy is unchanged; the board never lies to itself.
- **Save `_explored`** with the level's progress; `_visible` is recomputed on load.
- **Expose it**: `GameProbe.Count("visibleCells", () => _visible.Count)` lets a journey assert
  that stepping round a corner raised the count.

Soft edges, a blurred mask or a light cookie on top of the cell set are drawing choices —
`unity-2d-rendering` → `reference/lights-2d.md`.

## Traps

- **Line of sight by raycast against colliders.** It works until a wall tile's collider is
  composite-merged, a piece's collider blocks its own ray, or the result changes with the
  physics step. The board already knows which cells are walls.
- **Testing the two end cells.** The viewer's own cell and the target's cell never block the
  line; start at index 1 and stop before the last.
- **One rule for movement, another for sight** — see the corner table.
- **Recomputing field of view every frame.** It only changes when a unit changes cell or a wall
  changes. Recompute on those events.
- **A vision radius measured with the wrong metric.** A radius-6 Chebyshev square reaches 8.5
  cells into the corners. Clip with the board's own distance or with the round test above.
