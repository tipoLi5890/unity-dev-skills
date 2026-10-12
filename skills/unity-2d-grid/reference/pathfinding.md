# Pathfinding — A* on a board

> Part of the `unity-2d-grid` skill. How `resources/GridPathfinder.cs` finds the cheapest path,
> why its heuristic must match the neighbour rule, what stops a diagonal clipping a wall, how
> passability differs per unit, and how to ask whether a push puzzle can be solved at all.

A board path is a list of cells, each a neighbour of the last. That is the finished product: the
unit visits every one of them, each step is a rule the board checks, and the presenter tweens
between cell centres. NavMesh paths, steering and agents are a different tool for continuous
space — `unity-navigation`.

## Using it

```csharp
// Once per board. Cells outside origin .. origin + (width, height) are impassable.
_finder = new GridPathfinder(origin, width: 9, height: 7, GridShape.Rect4);
_cost = (from, to) => _cells.CanEnter(to) ? 1 : 0;     // a field: the delegate is created once
_path = new List<Vector3Int>(64);

// Per query.
if (_finder.FindPath(runnerCell, gateCell, _cost, _path))
{
    // _path[0] is runnerCell, the last entry is gateCell; _finder.PathCost is in tenths of a move point
}
```

| Member | Meaning |
|---|---|
| `FindPath(start, goal, cost, path)` | Cheapest path, both ends included. `false` and an empty list when there is none |
| `Range(start, movePoints, cost, reached)` | Every cell reachable within the budget, nearest first — `reference/neighbours-and-range.md` |
| `CostTo(cell)`, `PathFromRange(goal, path)` | After a `Range`: cost and route with no second search |
| `PathCost` | Cost of the last path: 10 per straight step on cost-1 terrain |
| `DiagonalWeight` | `Rect8` only: 14 (default) or 10; keep within 10–20 |
| `CutCorners` | `Rect8` only: `false` (default) closes wall corners |
| `Expanded` | Cells examined by the last search; watch it, do not assert it |

The **start cell's cost is never asked for** — a unit stands where it stands, even on a cell
its own cost function would refuse. The **goal's is**: a path to an occupied cell does not
exist. To walk *up to* an occupied target, search to each free neighbour of the target and keep
the cheapest, or run one `Range` from the mover and read `CostTo` for those neighbours.

## How it works

A* keeps an **open set** of cells it has reached but not expanded, ordered by `f = g + h`:
`g` is the cost paid from the start, `h` an estimate of the cost still to pay. It expands the
cell with the smallest `f`, relaxes its neighbours, and stops when it expands the goal.

1. **A flat array per board, not a dictionary per search.** The board is a rectangle, so a cell
   is the index `(y − originY) · width + (x − originX)`, and `g`, `h`, `f`, the parent and the
   heap position are arrays of that length.
2. **A generation stamp instead of clearing.** Each search increments a counter; a cell whose
   stamp is not the current counter is unvisited. Starting a search costs nothing, whatever the
   board size.
3. **An indexed binary heap.** The open set is a binary min-heap of cell indices plus, per
   cell, its position in the heap. When a cheaper route to an open cell is found, its key drops
   and it sifts up in place — no duplicate entries, and the heap never holds more than one entry
   per cell, so its array is the size of the board.
4. **A total order.** The heap compares `f`, then `h` (the cell nearer the goal first), then the
   cell index. Ties are common on a board — every route round an obstacle with the same number
   of steps has the same `f` — and without the last two the result depends on insertion order.

A sorted `List` as the open set works on a 9 × 7 board and is the reason a 64 × 64 one hitches:
insertion is linear. The heap is 40 lines; it is in the file.

## The heuristic must match the neighbour rule

`h` must never exceed the true remaining cost (it must be **admissible**), and it should be as
large as it can while staying so:

| Board | Heuristic | If you use the wrong one |
|---|---|---|
| `Rect4` | Manhattan × 10 | Chebyshev or Euclidean here are admissible and weak: correct paths, several times the work |
| `Rect8`, diagonal 10 | Chebyshev × 10 | Manhattan overestimates a diagonal: **wrong paths**, staircases where a diagonal was cheaper |
| `Rect8`, diagonal 14 | Octile: `14·min + 10·(max − min)` | Manhattan overestimates; Chebyshev underestimates and is slower |
| `Hex` | Cube distance × 10 | Manhattan on offset coordinates overestimates on half the directions: wrong paths |

An overestimating heuristic does not crash or return nothing. It returns a plausible path that
is a step or two longer than the best, on some boards, in some directions — which nobody notices
until a player counts cells. `GridPathfinder` chooses the heuristic from its shape and
`DiagonalWeight`, so there is one place to get it right, and
`A_star_agrees_with_the_flood_on_every_shape` compares every A* cost against Dijkstra, which has
no heuristic to get wrong.

**Terrain costs must be 1 or more.** The heuristic assumes the cheapest possible step costs 10;
a road that costs 0.5 needs every cost doubled so the road becomes 1, and every budget with it.

Scaling `h` up on purpose (×1.5, "weighted A*") trades shortest for faster. On a board where
the player counts steps, do not.

## Corners

On `Rect8` a diagonal step passes between two cells. If one of them is a wall, the piece is
drawn sliding through the wall's corner; if both are, it passes through a closed diagonal wall.

```
. G      (0,0) → (1,1) squeezes between (1,0) and (0,1).
S #      With the wall at (1,0): CutCorners false → S, (0,1), G    cost 20
                                 CutCorners true  → S, G           cost 14
```

`CutCorners = false`, the default, allows a diagonal only when **both** side cells can be
entered. Pick the rule that matches what the pieces look like:

| Rule | Use when |
|---|---|
| Both sides open (the default) | Pieces fill their cell; walls are full cells |
| At least one side open | Pieces are small against the cell and walls have rounded corners. Change the test in `StepCost` from "either blocked" to "both blocked" |
| Always (`CutCorners = true`) | Walls are thin edges between cells, not cells |

Apply the **same rule to line of sight**, or a unit can walk where it cannot see —
`reference/line-of-sight.md`.

## Passability is per unit

The cost delegate *is* the unit's view of the board. Build one per kind of unit and keep them
as fields:

```csharp
_runnerCost = (from, to) => _cells.IsWall(to) || _cells.OccupantAt(to) != 0 ? 0 : _slow.Contains(to) ? 2 : 1;
_sentryCost = (from, to) => _cells.IsWall(to) || _hazards.Contains(to) ? 0 : 1;   // sentries avoid hazards, ignore slow ground
_flyerCost  = (from, to) => _cells.OccupantAt(to) != 0 ? 0 : 1;                   // over walls, not through pieces
```

| Need | Put it in |
|---|---|
| Walls, pits, a unit that flies or swims | the delegate: 0 or a cost |
| Slow ground, roads | the delegate: 2, or everything doubled and the road 1 |
| A step up that costs more, a drop that cannot be climbed back | the delegate, using both `from` and `to` |
| Walking through allies but not stopping on them | the delegate lets allies through; the *destination* is filtered afterwards |
| Avoiding danger without forbidding it | a higher cost on threatened cells (5), not a 0 |
| A unit two cells wide | the delegate tests every cell the footprint would cover at `to` |

Occupants move, so a path is true for the board it was computed on. Recompute at the start of
each action; do not cache a path across turns.

## No smoothing

String-pulling, funnel smoothing and spline fitting exist to straighten a path in continuous
space. On a board they remove cells, and each removed cell is a step the rules never validated —
the piece then moves through a cell it was never granted. The path is the list. If it *looks*
jagged:

- **Prefer straight runs on ties**: the cardinal-first neighbour order already does, and the
  `h` tie-break pulls toward the goal.
- **Smooth the picture, not the path**: the presenter may ease through a corner cell on a curve
  as long as the board steps through every cell.
- **Zig-zags on a `Rect4` board are correct.** Every monotone staircase between two cells has
  the same length; the tie-break only picks which one is shown.

## Reusing buffers

After the constructor, a search allocates nothing provided the caller does three things:

1. **Keep the delegate** in a field (`_cost = Cost;` once). An instance method group, or a
   lambda that captures anything, allocates a new delegate every time the call site runs.
2. **Keep the result list** and let the pathfinder clear it. Give it a capacity near the longest
   path (`width + height` covers every open board).
3. **Do not capture per-call values in the delegate.** If the cost depends on which unit is
   moving, set a field (`_mover = id;`) before the call and read it inside.

Check it in an EditMode test, after one warm-up search so the result list has its capacity:

```csharp
using UnityEngine.TestTools.Constraints;               // AllocatingGCMemory is an extension here
using Is = UnityEngine.TestTools.Constraints.Is;       // the Test Framework's overlay of NUnit's Is

_finder.FindPath(start, goal, _cost, _path);                                   // warm-up
Assert.That(() => { _finder.FindPath(start, goal, _cost, _path); }, Is.Not.AllocatingGCMemory());
```

The profiler's GC Alloc column for the frame shows the same thing by eye.

One instance holds one search's state. `CostTo` and `PathFromRange` read the last `Range`; a
`FindPath` in between invalidates them (both then report "not reached"). For a board larger than
about 128 × 128 with many queries per frame, spread the queries over frames before reaching for
threads: the instance is not thread-safe.

## Many units, one target

Twelve sentries converging on the runner is twelve A* searches, or **one flood from the
runner**: `Range(runnerCell, 999, cost, reached)` computes the cost from the runner to every
cell, and each sentry steps to whichever neighbour has the lowest `CostTo`. It is exact when the
cost is symmetric; with one-way steps, reverse `from` and `to` inside the delegate for this
flood. Recompute when the runner changes cell, not per sentry.

## Is this push puzzle solvable

A sorting-yard level must be solvable before it ships, and a human testing by hand proves only
that one human solved it. The check is a breadth-first search over **board states**, not cells:

- **State**: the runner's cell plus the pickup cells **sorted** (pickups are interchangeable, so
  two boards that differ only in which pickup is where are one state). Hash it to a `string` or
  a `long` — on a 9 × 7 board each cell index fits in 6 bits.
- **Moves**: the four steps, applied with the real rule (`GridOccupancy.StepOrPush`), reverted
  after each with `Revert`. The solver and the game cannot disagree because they run the same
  code.
- **Goal**: every gate cell holds a pickup.
- **Prune dead states** or the search explodes: a pickup in a corner that is not a gate can
  never move again; the same for a pickup against a wall with no gate along that wall.

```csharp
// Outline — run it from an EditMode test or an Editor menu, never at run time.
var seen = new HashSet<string> { Key(board) };
var frontier = new Queue<(string key, int depth)>();          // plus the moves that led there
frontier.Enqueue((Key(board), 0));
while (frontier.Count > 0)
{
    var (key, depth) = frontier.Dequeue();
    Restore(board, key);
    if (board.Solved) return depth;                           // the shortest solution, in steps
    for (int d = 0; d < 4; d++)
    {
        StepRecord step = board.Cells.StepOrPush(YardBoard.RunnerId, To(d), Beyond(d));
        if (step.Result == StepResult.Blocked) continue;
        if (!Dead(board) && seen.Add(Key(board))) frontier.Enqueue((Key(board), depth + 1));
        board.Cells.Revert(step);
    }
}
return -1;                                                    // unsolvable
```

Budget it: stop at 2,000,000 states and report "undecided", which is a third verdict, not a
pass. A level that hits the budget has so much free floor that it is a room, not a puzzle:
add walls until the search finishes. Store the solution's move list beside the level — it is
the scripted input for the solve journey. Level files and their validation are
`unity-2d-level` → `reference/level-data.md`.

## Checks

- **A known board, a known length**: `A_known_board_has_a_known_shortest_path` — a wall with one
  gap, 12 steps, 13 cells, cost 120, and the same list on a second run.
- **No path is `false` with an empty list**, including a goal off the board:
  `An_unreachable_goal_returns_no_path`.
- **The corner rule**: `A_diagonal_does_not_cut_a_corner_unless_asked`.
- **In play**: draw the path with `Debug.DrawLine` between `GetCellCenterWorld` of consecutive
  cells for a few seconds; a segment that crosses a wall tile is a cost delegate that disagrees
  with the Tilemap.
