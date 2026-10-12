# Neighbours and range — who is next to whom, how far, and what a unit can reach

> Part of the `unity-2d-grid` skill. The neighbour rule, the distance that belongs to it, and the
> two kinds of range a board game needs: where a unit can **move** (a flood) and what it can
> **reach** (a metric). Code is in `resources/GridCoords.cs` and `resources/GridPathfinder.cs`.

## One neighbour function

```csharp
int n = GridCoords.NeighbourCount(shape);                 // 4, 8 or 6
for (int i = 0; i < n; i++)
{
    Vector3Int next = GridCoords.Neighbour(shape, cell, i);
    …
}
```

A direction is an **index**, not a vector. That is the whole trick: `cell + new Vector3Int(1, 1, 0)`
means something on a rectangle and something different on every second hexagonal row, while
"direction 1 from this cell" means the same thing everywhere. Commands, undo records, facing
and animation parameters all carry the index.

| Shape | Indices | Order | Opposite of `i` |
|---|---|---|---|
| `Rect4` | 0–3 | E, N, W, S | `(i + 2) % 4` |
| `Rect8` | 0–7 | E, N, W, S, then NE, NW, SW, SE | `GridCoords.Opposite(shape, i)` |
| `Hex` | 0–5 | E, NE, NW, W, SW, SE on point-top (anticlockwise from +q) | `(i + 3) % 6` |

`GridCoords.DirectionTo(shape, from, to)` gives the index between two adjacent cells, or −1 —
the way to turn two consecutive path cells into a facing.

The order is fixed and it is behaviour: a search visits neighbours in index order, so the four
cardinals of `Rect8` come first and a path prefers a straight run when costs tie.

### Four or eight

| | 4 neighbours | 8 neighbours |
|---|---|---|
| Range shape | Diamond | Square (diagonal = 1 step) or octagon (diagonal = 1.4) |
| Reads as | A board game; every step is the same length | Free movement snapped to cells |
| Blocking | A wall of single cells is solid | A diagonal line of walls leaks unless corners are closed — `reference/pathfinding.md` |
| Push puzzle | Yes | No: a diagonal push has no clean "cell beyond" for a player to read |
| Input | Four keys or a D-pad | Needs a real diagonal: two keys together or a stick |

Start with four. Add diagonals only when a specific rule needs them, and then price them.

### Six

Hexagonal neighbours are computed in cube space: convert, add one of the six cube steps,
convert back. `GridCoords.Neighbour` does that; the offset tables it replaces are in
`reference/coordinates.md`. On a flat-top board the same six indices point N, NE, SE, S, SW, NW.

## A distance per neighbour rule

| Neighbour rule | Distance | Function | `(0,0)` → `(5, −4)` |
|---|---|---|---|
| 4 | Manhattan: `|dx| + |dy|` | `GridCoords.Manhattan` | 9 |
| 8, diagonal = 1 | Chebyshev: `max(|dx|, |dy|)` | `GridCoords.Chebyshev` | 5 |
| 8, diagonal = 14, straight = 10 | Octile: `14·min + 10·(max − min)` | `GridCoords.Octile` | 66 |
| 6 | Cube: `(|dq| + |dr| + |ds|) / 2`, equal to the largest of the three | `GridCoords.HexDistance` (offset in), `CubeDistance` (cube in) | — |

`GridCoords.Distance(shape, a, b)` picks the first, second or fourth by shape.

A distance is the number of steps on an **empty** board. It answers "could this ever be within
N" and "which is nearer"; it never answers "can the unit get there", because it does not know
about walls. Three uses that are right:

- **Attack reach**: a sentry with reach 3 threatens every cell at distance ≤ 3, wall or no wall
  (sight is a separate test — `reference/line-of-sight.md`).
- **A heuristic** for A*.
- **A cheap reject**: do not flood for a target whose distance already exceeds the budget.

### The mismatch that looks like a feature

Diagonal steps with a Manhattan budget: the unit steps `(+1, +1)` for one move point, so with 4
points it reaches `(4, 4)` — eight cells away by its own metric — while straight ahead it reaches
only `(4, 0)`. Players read that as "bishops are faster". Either diagonals are not neighbours
(`Rect4`), or they are one step and the range is a square (`Rect8`, weight 10), or they cost
more (`Rect8`, weight 14).

## Movement range — a flood

Where a unit can go this turn is every cell whose **cheapest route** costs no more than its
move points. That is a search, not a distance:

```csharp
// Fields, created once: the delegate and the list are reused every turn.
GridPathfinder _finder;                     // new GridPathfinder(origin, width, height, shape)
GridPathfinder.EnterCost _runnerCost;       // set in the constructor, below
readonly List<Vector3Int> _reachable = new List<Vector3Int>();

int RunnerCost(Vector3Int from, Vector3Int to)
{
    if (!_cells.CanEnter(to)) return 0;     // wall or occupied: cannot enter
    return _slow.Contains(to) ? 2 : 1;      // slow ground costs two move points
}

void ShowRange(int runnerId, int movePoints)
{
    _finder.Range(_cells.CellOf(runnerId), movePoints, _runnerCost, _reachable);
    // _reachable[0] is the start; the rest are nearest first.
}
```

`_runnerCost = RunnerCost;` in the constructor converts the method to a delegate once. Passing
`RunnerCost` or a capturing lambda at the call site allocates a new delegate on every call.

With every cost equal to 1 this is a breadth-first flood; with terrain costs it is Dijkstra with
the same stopping rule, and `Range` is the second (a binary heap makes the two the same code).
After a `Range`:

- `CostTo(cell)` is the cost in tenths of a move point, or −1 if the cell is out of range —
  the number for a "3 / 4" label on a hovered cell;
- `PathFromRange(cell, path)` is the route to it, with no second search — the preview arrow.

Expected sizes on an open field, for a quick sanity check and for the tests:

| Move points `r` | 4 neighbours | 8, diagonal = 1 | 6 |
|---|---|---|---|
| formula | `2r² + 2r + 1` | `(2r + 1)²` | `3r² + 3r + 1` |
| 1 | 5 | 9 | 7 |
| 2 | 13 | 25 | 19 |
| 3 | 25 | 49 | 37 |
| 4 | 41 | 81 | 61 |

A flood on a board with walls that returns exactly these numbers is ignoring the walls.

### Passing through is not stopping on

Two different questions hide in "can enter":

| Rule | Cost delegate says | After the flood |
|---|---|---|
| Nobody shares or passes through a cell | occupied → 0 | use the list as it is |
| Allies can be walked through, not stopped on | ally → normal cost, enemy → 0 | drop every reached cell that holds an occupant other than the mover |
| Enemies exert a zone: entering a cell next to one ends the move | cost as normal | for each reached cell take `PathFromRange` and drop the cell if any cell before the last is adjacent to an enemy |

The second row is the common one and the common bug: the highlight shows an ally's cell as a
destination. Filter the *result*, not the *cost*, or the flood stops dead behind every ally.

### Height and one-way steps

The delegate receives both cells because a step can depend on where it comes from:

```csharp
int Climb(Vector3Int from, Vector3Int to)
{
    int rise = _height[to] - _height[from];
    if (rise > 1) return 0;                 // too high to climb
    return rise == 1 ? 2 : 1;               // up costs double; down is free
}
```

A cost that depends on direction makes distances asymmetric: A reaches B, B does not reach A.
That is fine for the flood. It also means "who can reach the runner" is one flood per sentry, or
one flood from the runner with the cost function **reversed** (swap `from` and `to` inside it).

## Attack range — a metric, a ring, a line

Reach ignores walls, so it is plain arithmetic:

```csharp
_cells.Clear();
GridCoords.Disc(shape, sentryCell, 1, 3, _cells);     // reach 1 to 3, nearest ring first
GridCoords.Ring(shape, sentryCell, 2, _cells);        // exactly 2: a ranged unit's minimum
```

| Pattern | How |
|---|---|
| Reach 1–N (melee, a spear) | `Disc(shape, centre, 1, N, into)` |
| Minimum range (cannot fire at adjacent cells) | `Disc(shape, centre, 2, N, into)` |
| A straight line in a facing | step `Neighbour(shape, cell, direction)` N times, stopping at the first wall |
| The four or six straight lines (a rook, a beam) | the previous row for every direction |
| A cone | a `Disc` filtered by the offset from the centre, written for facing 0 and rotated for the others. Rectangle, 90°: keep `dx > 0 && |dy| <= dx`. Hexagon, 120°: in cube offsets keep `q >= 0 && s <= 0`, centre excluded |
| A blast around a target cell | `Disc(shape, target, 0, radius, into)` |
| A template that turns with the unit | stored as cube or rect offsets facing direction 0, rotated to the facing — `reference/coordinates.md` |

Cells a `Ring` or `Disc` returns may be off the board or inside walls: filter with the board's
bounds, and then with line of sight if the attack needs it.

**Reach from every cell you can move to** is the "threat range" overlay: flood the movement
range, then take the union of the reach disc around each reachable, stoppable cell. Reuse one
`HashSet<Vector3Int>` for the union; with 40 reachable cells and reach 3 that is about 1,000
set insertions, well under a millisecond, and it only runs when the selection changes.

## Checks

- **Symmetry.** For every cell in a block that includes negative coordinates and both row
  parities: each neighbour is at distance 1, all are distinct, and stepping back with
  `Opposite` returns to the cell. `Neighbours_are_distinct_at_distance_one_and_mutual` in
  `resources/Tests/GridCoordsTests.cs`.
- **Range size on an open field** equals the closed form above;
  `An_open_field_range_has_the_closed_form_size`.
- **A wall stops the flood**: a corridor with one wall cell — nothing beyond it is reached
  however large the budget; `A_range_stops_at_walls_and_prices_slow_ground`.
- **In play**: register `GameProbe.Count("reachable", () => _reachable.Count)` and assert it
  against the hand count for the sorting-yard situation's first board.
