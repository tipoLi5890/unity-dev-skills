# Coordinates — cells, world points, and the three ways to name a hexagon

> Part of the `unity-2d-grid` skill. What a cell is on each of Unity's four layouts, how a cell
> becomes a world point and back, and the hexagonal conversions `resources/GridCoords.cs` carries
> — each with the check that proves it on the project's own `Grid`.

The `Grid` component, its four cell layouts, the cell size each one wants and the swizzle are
documented in `unity-tilemap` → `reference/palette-and-grid.md`. This file starts where that one
stops: the `Grid` exists, and the rules need to do arithmetic on its cells.

## Two spaces, one door

| Space | Type | Who uses it |
|---|---|---|
| Cell | `Vector3Int` (x, y, 0) | every rule, the occupancy map, the pathfinder, save files |
| World | `Vector3` | the presenter, the camera, the pointer |

The door between them is the `Grid`, and only the presenter walks through it:

```csharp
Vector3 centre = _grid.GetCellCenterWorld(cell);   // where a piece standing in the cell is drawn
Vector3Int cell = _grid.WorldToCell(worldPoint);   // which cell a pointer is over
```

`GridCoords` contains no world arithmetic on purpose. The `Grid` already knows its layout, cell
size, gap, swizzle, and its own position, rotation and scale; a second copy of that maths in the
rules is a second answer waiting to disagree.

## Cell origin is not cell centre

`CellToWorld(cell)` returns the cell's **origin**; `GetCellCenterWorld(cell)` returns its
**centre**. They differ by layout:

| Layout | `CellToWorld((0,0,0))` is | `GetCellCenterWorld((0,0,0))` at the default cell size |
|---|---|---|
| Rectangle `(1, 1, 0)` | the bottom-left corner | `(0.5, 0.5, 0)` |
| Isometric `(1, 0.5, 1)` | the bottom corner of the diamond | `(0, 0.25, 0.5)` — z is half the cell's z size; place by x and y |
| Hexagon | the centre of the hexagon | `(0, 0, 0)` |

Place pieces with `GetCellCenterWorld` on every layout and the difference never matters. Place
them with `CellToWorld` and a rectangular board looks right with a bottom-left sprite pivot,
then every piece stands on a corner the day the board becomes isometric.

A Tilemap draws a tile at the cell origin plus its `tileAnchor`. A `Tilemap` added from script
has `(0.5, 0.5, 0)` on every layout; a hexagonal cell's origin is already its centre, so a
hexagonal Tilemap wants `(0, 0, 0)`, which is what a hexagonal palette is created with. Read
`tilemap.tileAnchor` on the board's Tilemap: tiles drawn half a cell from the pieces are this.

Check, with the `Grid` at the origin and unscaled (run it once per board, in the Editor):

```csharp
var g = Object.FindAnyObjectByType<Grid>();
Debug.Log($"{g.cellLayout} {g.cellSwizzle} size {g.cellSize} gap {g.cellGap}"
        + $" origin {g.CellToWorld(Vector3Int.zero)} centre {g.GetCellCenterWorld(Vector3Int.zero)}");
```

## Rectangular

Cell `(x, y)` covers world `[x·w, (x+1)·w) × [y·h, (y+1)·h)` for cell size `(w, h)` plus gap.
Neighbours are plain offsets (`GridCoords.Dirs4`, `GridCoords.Dirs8`), distances are Manhattan
or Chebyshev. Nothing to convert.

## Isometric

The cell indices, the neighbours and every rule are the rectangular ones. Only the picture is
turned, so only the presenter and the picker see a difference.

For cell size `(w, h)` and no gap, local position of the cell origin:

```
x = (cx − cy) · w / 2          cx = floor(x / w + y / h)
y = (cx + cy) · h / 2          cy = floor(y / h − x / w)
```

So on the default `(1, 0.5, 1)`: cell `+x` is screen right-and-up, cell `+y` is screen
left-and-up, and screen-up is cell `(+1, +1)` — two steps, not a neighbour.

Check:

```csharp
Debug.Log($"{g.CellToWorld(new Vector3Int(1, 0, 0))} {g.CellToWorld(new Vector3Int(0, 1, 0))}");
// isometric (1, 0.5, 1) →  (0.50, 0.25, 0.00) (-0.50, 0.25, 0.00)
```

**Map the D-pad on purpose.** There are two honest choices and the recipe must name one:

| D-pad | Screen-aligned (most tactics boards) | Cell-aligned |
|---|---|---|
| Up | cell `(0, +1)`, drawn up-left | cell `(0, +1)` |
| Right | cell `(+1, 0)`, drawn up-right | cell `(+1, 0)` |
| Feels like | the stick is rotated 45° against the picture | the picture is rotated 45° against the stick |

They are the same table; the difference is whether the on-screen prompt shows diagonal arrows.
What does not work is mapping up to `(+1, +1)`: that is not a neighbour, and the piece jumps
over a cell.

### Isometric Z as Y

`IsometricZAsY` uses the cell's z as a height: a tile at `(x, y, z)` is drawn where
`(x, y, 0)` is, lifted up the screen. The board is still addressed by `(x, y)`; z is a property
of the cell (its height), not a third axis the rules walk along.

Measure the lift instead of assuming it — picking has to subtract exactly this number:

```csharp
Vector3 lift = g.GetCellCenterWorld(new Vector3Int(0, 0, 1)) - g.GetCellCenterWorld(Vector3Int.zero);
Debug.Log($"lift per level {lift}");   // the y component is the screen lift; z is the sort depth
```

Store height as its own map — `Dictionary<Vector3Int, int>` keyed by the z = 0 cell — and keep
every board cell at z = 0. A rule that compares `(3, 4, 0)` with `(3, 4, 1)` finds two
different cells where the board has one.

## Hexagonal — offset, axial, cube

Three names for the same hexagon:

| Name | Shape | Good for | Bad for |
|---|---|---|---|
| **Offset** `(x, y)` | what `Grid` and `Tilemap` use: rows and columns, odd rows shifted | storage, level files, `SetTile`, a rectangular board | any arithmetic: neighbours depend on the row |
| **Axial** `(q, r)` | two of the three cube numbers | compact storage of hexagon-shaped boards, hashing | forgetting the third number exists |
| **Cube** `(q, r, s)`, `q + r + s = 0` | three axes 120° apart | distance, lines, rings, rotation, rounding | storage: one number is redundant |

**Compute in cube, store in offset, convert at the edges.**

### Which rows Unity shifts

`GridLayout.CellLayout.Hexagon` with swizzle `XYZ` is **point-top**. Rows are 3⁄4 of the cell
height apart, and rows whose y is **odd** sit half a cell width along **+x**. That is the
"odd-r" offset layout, and it holds for negative rows: row −1 is shifted the same way as row 1.

The check, on a `Grid` at the origin, unrotated and unscaled, cell size `(w, h)`, no gap:

```csharp
var g = Object.FindAnyObjectByType<Grid>();
Vector3 row = g.GetCellCenterWorld(new Vector3Int(0, 1, 0)) - g.GetCellCenterWorld(Vector3Int.zero);
Vector3 col = g.GetCellCenterWorld(new Vector3Int(1, 0, 0)) - g.GetCellCenterWorld(Vector3Int.zero);
Debug.Log($"{g.cellSwizzle} size {g.cellSize} row {row} col {col}");
```

| Swizzle | Expected `row` | Expected `col` | At cell size |
|---|---|---|---|
| `XYZ` (point-top) | `(w/2, 0.75·h, 0)` = `(0.43, 0.75, 0)` | `(w, 0, 0)` = `(0.87, 0, 0)` | `(0.8659766, 1, 1)` |
| `YXZ` (flat-top) | `(0.75·h, w/2, 0)` = `(0.75, 0.50, 0)` | `(0, w, 0)` = `(0, 1, 0)` | `(1, 1, 1)` |

Read it as three verdicts:

1. **The half step is positive** (`row.x` on point-top, `row.y` on flat-top): odd rows are the
   shifted ones. Use `GridCoords` as shipped.
2. **The half step is negative**: even rows are the shifted ones on this `Grid`. Pass
   `oddShifted: false` to every `GridCoords` call and to the `GridPathfinder` constructor.
3. **There is no half step**: the `Grid` is not hexagonal, or `(0, 1, 0)` is not the axis that
   staggers — compare `g.cellLayout` and `g.cellSwizzle` with what the palette was created with.

Run it again after scaling or rotating the `Grid`'s transform only to see the numbers move with
the transform; the verdict (the sign in the Grid's own local space) does not change.

### Flat-top is the same cells, turned

There is no flat-top layout. Flat-top is `Hexagon` with swizzle `YXZ`: the Grid computes the
point-top position and swaps its x and y. So:

- the cell arithmetic is **identical** — same offset rule, same cube conversion, same distances,
  same neighbour function, same tests;
- cell x now runs **up** the screen and cell y runs **across** it, so "rows" in the code are
  columns on screen, and the shifted ones are shifted upward;
- direction indices keep their cube meaning and change their screen meaning:

| `GridCoords.CubeDirs` index | Cube step | Point-top reads | Flat-top reads |
|---|---|---|---|
| 0 | `(+1, 0, −1)` | E | N |
| 1 | `(0, +1, −1)` | NE | NE |
| 2 | `(−1, +1, 0)` | NW | SE |
| 3 | `(−1, 0, +1)` | W | S |
| 4 | `(0, −1, +1)` | SW | SW |
| 5 | `(+1, −1, 0)` | SE | NW |

Map input to an index from this table once, in the presenter, and the rules stay unaware.

### The conversions

`r` is the offset row itself, which is what keeps this short:

```csharp
// Offset (odd rows shifted along +x) → cube. `& 1`, not `% 2`: -1 % 2 is -1 in C#.
static Vector3Int OffsetToCube(Vector3Int c) { int q = c.x - (c.y - (c.y & 1)) / 2; return new Vector3Int(q, c.y, -q - c.y); }
static Vector3Int CubeToOffset(Vector3Int h) => new Vector3Int(h.x + (h.y - (h.y & 1)) / 2, h.y, 0);
// Axial is cube without s.
static Vector2Int CubeToAxial(Vector3Int h) => new Vector2Int(h.x, h.y);
static Vector3Int AxialToCube(Vector2Int a) => new Vector3Int(a.x, a.y, -a.x - a.y);
```

Worked values to compare against: offset `(2, 3)` is cube `(1, 3, −4)`; offset `(2, −3)` is cube
`(4, −3, −1)`; offset `(0, 0)` to offset `(3, 2)` is 4 steps.

The neighbours that fall out, as offset cells — the table a hand-written offset list has to
reproduce, and gets wrong on one of the two rows:

| Direction | From `(0, 0)` (even row) | From `(0, 1)` (odd row) |
|---|---|---|
| 0 E | `(1, 0)` | `(1, 1)` |
| 1 NE | `(0, 1)` | `(1, 2)` |
| 2 NW | `(−1, 1)` | `(0, 2)` |
| 3 W | `(−1, 0)` | `(−1, 1)` |
| 4 SW | `(−1, −1)` | `(0, 0)` |
| 5 SE | `(0, −1)` | `(1, 0)` |

### Rounding a fractional hexagon

A point between hexagons is a fractional cube coordinate. Round all three numbers, then repair
the one that moved furthest so the sum is zero again — `GridCoords.CubeRound(q, r, s)`. Rounding
only two of them, or rounding offset coordinates, picks the wrong hexagon near every edge. Lines
and picking both end in this function.

### Rotating and mirroring

In cube space a 60° turn about the origin is a rotation of the three numbers with a sign flip:
`(q, r, s)` → `(−r, −s, −q)`; apply it six times to return. A mirror swaps two numbers. To turn
about another hexagon, subtract its cube coordinate first and add it back after. An area-effect
template is stored once, as cube offsets facing direction 0, and rotated to the facing.

## `Vector3Int`, or a struct of your own

| | `UnityEngine.Vector3Int` | Your own two-int struct |
|---|---|---|
| Talks to `Grid` and `Tilemap` | Directly | Through one conversion in the presenter |
| EditMode tests | Run with no scene | Run with no scene |
| An assembly with `noEngineReferences` | Does not compile | Compiles |
| Dictionary key | Fine: it implements `IEquatable<Vector3Int>`, so no boxing | Implement `IEquatable<T>` and `GetHashCode` yourself, or every lookup boxes |
| Risk | A stray z ≠ 0 makes two keys for one cell | None, there is no z |

The resources ship on `Vector3Int` because the board talks to a `Grid` in every project that has
a scene. Two rules keep it safe: **every board cell has z = 0** (strip it where a cell enters the
rules: `new Vector3Int(c.x, c.y, 0)`), and **cube coordinates never go into a board-cell map** —
a `Vector3Int` holding `(q, r, s)` and one holding `(x, y, 0)` are the same type and mean
different things. Name the variable `cube` every time.

For a rules assembly that cannot see the engine — `unity-game-brief` →
`reference/sim-presentation-split.md` — replace `Vector3Int` and `Vector2Int` in the four
resources with structs of your own and convert in the presenter:
`new Vector3Int(cell.X, cell.Y, 0)`.

## Storing a board

- **Bounded and dense** (a 9 × 7 yard): a flat array indexed `(y − originY) · width + (x − originX)`.
  `GridPathfinder` does exactly this, which is why it takes an origin and a size.
- **Sparse or unbounded**: `Dictionary<Vector3Int, T>` and `HashSet<Vector3Int>`, as
  `GridOccupancy` does.
- **A hexagon-shaped hexagonal board** of radius N: still store by offset cell inside the
  bounding rectangle, and mark the corners outside the hexagon as walls. The rectangle wastes
  about a quarter of its cells and saves a second storage scheme.

## Traps

- **Scaling the `Grid` to fit the art.** `WorldToCell` follows the transform, so it still
  answers correctly, and every hard-coded "one cell is one unit" in a tween is now wrong. Read
  distances from `GetCellCenterWorld` differences.
- **A cell gap.** With `cellGap` set, a pointer over the gap still gets a cell from
  `WorldToCell`; if gaps must not be clickable, test the pointer against the cell's own bounds.
- **A palette and a scene `Grid` with different cell sizes.** Tiles paint; the board computed
  from one and drawn with the other drifts across the map. Compare both with the check above.
- **Storing world positions in a save file.** Save cells. A world position is a cell multiplied
  by an art decision that will change.
