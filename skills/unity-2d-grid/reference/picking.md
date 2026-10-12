# Picking — from a pointer to a cell, and showing the answer

> Part of the `unity-2d-grid` skill. The pointer is a world point; the board wants a cell. On a
> flat rectangular board that is one call. On an isometric board with tall tiles the cell under
> the pointer is not the thing drawn under the pointer, and that needs a rule.

Picking is **presenter** work: it reads the camera and the `Grid`, produces a `Vector3Int`, and
hands the rules a command ("select cell", "move to cell"). The rules never see a screen position.

## Pointer to world to cell

Where the pointer is, whether it was over the UI, and how a touch becomes the same thing are
`unity-input` → `reference/pointer-and-aim.md`. With that funnel in place the world point
arrives in the input struct and the pick is one line:

```csharp
RunInput i = _input.Peek();
if (i.hasAimPoint)
{
    Vector3Int cell = _grid.WorldToCell(i.aimPoint);
    cell.z = 0;                                            // board cells are z = 0
    _hovered = _board.Contains(cell) ? cell : (Vector3Int?)null;
}
if (_hovered.HasValue && _input.TryUse(RunButton.Interact)) _board.Select(_hovered.Value);
```

The operation underneath, for an **orthographic** camera looking down −z at a board on z = 0:

```csharp
Vector3 world = _camera.ScreenToWorldPoint(screenPosition);   // x and y are right; z is the camera's
world.z = _grid.transform.position.z;                         // put the point on the board's plane
Vector3Int cell = _grid.WorldToCell(world);
```

| Detail | Rule |
|---|---|
| The z of the result | `ScreenToWorldPoint` returns the camera's z on an orthographic camera. Overwrite it with the board's plane before `WorldToCell`, or a `Grid` whose layout uses z (isometric Z as Y) reads a height out of the camera distance |
| A perspective camera | `ScreenToWorldPoint` with z = 0 returns the camera position for every pixel. Intersect the pointer ray with the board's plane instead — `RunAim.PointOnPlane` in `unity-input` → `resources/RunInput.cs` |
| A rotated or scaled `Grid` | Nothing to do: `WorldToCell` goes through the Grid's transform |
| Off the board | `WorldToCell` returns a cell for every point in the world. Test the result against the board's bounds or its floor set; hover nothing otherwise |
| Over the UI | The reader has already dropped the press; do not test it again here |
| Hover vs press | Hover updates every frame from `Peek`; the press is spent once with `TryUse` — condition first, then `TryUse` |

`WorldToCell` is exact on rectangular, isometric and hexagonal layouts for a **flat** board: it
answers "which cell's footprint contains this point". Everything below is about the cases where
the footprint is not what the player is pointing at.

## The isometric tall-tile problem

On an isometric board a crate one cell tall is drawn over the cell behind it. The player points
at the crate's face; the point lies inside the footprint of the cell **behind** the crate; and
`WorldToCell` reports that one.

```
        ◇ B          The pointer ✕ is on the face of the crate standing on A.
      ◇ ✕ ◇          Its footprint cell is B, behind A.
    ◇ ┌───┐ ◇        WorldToCell says B. The player means A.
      │ A │
      └───┘
```

The fix is to ask **what is drawn there**, front to back, before asking what the ground is.

### Pieces: pick by sprite

Pieces are few and each has a renderer. Test the candidates nearest the camera first and take
the first whose sprite contains the pointer:

```csharp
// Presenter. _pieces maps occupant id → SpriteRenderer; maxTall is the tallest sprite in cells.
int PickPiece(Vector3 world, Vector3Int footprintCell, int maxTall)
{
    // A sprite standing on (x − k, y − k) is drawn k cells further down the screen, so it is the
    // one that can cover this footprint. Nearest the camera first: largest k.
    for (int k = maxTall; k >= 0; k--)
    {
        var cell = new Vector3Int(footprintCell.x - k, footprintCell.y - k, 0);
        int id = _board.Cells.OccupantAt(cell);
        if (id == GridOccupancy.Nobody) continue;
        Bounds b = _pieces[id].bounds;
        world.z = b.center.z;                                // compare in the sprite's own plane
        if (b.Contains(world)) return id;
    }
    return GridOccupancy.Nobody;
}
```

`maxTall` is the tallest piece's sprite height divided by the cell height, rounded up: with
cells 0.5 high and sprites up to 1.5 high, 3. Checking the two side columns as well
(`(x − k, y − k + 1)` and `(x − k + 1, y − k)`) catches sprites wider than a cell.

`Renderer.bounds` is the sprite's rectangle, transparent corners included. For a crate that is
right. For a thin sentry it selects on the empty corners; then test the pixel as well: convert
the world point to the sprite's texture coordinates and read alpha from a readable texture, or
use a `PolygonCollider2D` on a pick-only layer and `Physics2D.OverlapPoint` —
`unity-physics-2d` → `reference/queries-2d.md`.

Then the rule the player feels:

1. A piece under the pointer → that piece's cell (`_board.Cells.CellOf(id)`).
2. Otherwise → the footprint cell from `WorldToCell`.

### Tiles: pick by height

With `IsometricZAsY`, raised ground is a tile at a higher cell z, drawn lifted up the screen by
a fixed amount per level. Undo the lift for each level, highest first, and take the first cell
that actually holds a tile:

```csharp
// lift = GetCellCenterWorld((0,0,1)) − GetCellCenterWorld((0,0,0)), measured once at start.
bool PickRaised(Vector3 world, int maxHeight, out Vector3Int cell)
{
    for (int z = maxHeight; z >= 0; z--)
    {
        var flat = new Vector3(world.x, world.y - z * _lift.y, _grid.transform.position.z);
        cell = _grid.WorldToCell(flat);
        cell.z = z;
        if (_ground.HasTile(cell)) return true;              // the Tilemap that holds the terrain
    }
    cell = default;
    return false;
}
```

Hand the rules `(cell.x, cell.y, 0)` and keep the height in the board's own height map — a
board cell never carries a z (`reference/coordinates.md`).

On a plain `Isometric` layout with tall wall art and no z, treat walls like pieces: a short list
of candidate cells in front, tested by the tile's sprite — `Tilemap.GetSprite(cell).bounds`
offset to `GetCellCenterWorld(cell)`.

### What to check

Stand a piece in front of an empty cell and click the piece's top half: the pick must be the
piece. Click the floor visible beside it: the pick must be that floor cell. Click the floor
directly in front of the piece: that cell, not the piece. Three clicks, three different
answers; a picker that gets all three is done.

## Hexagonal picking

`Grid.WorldToCell` already returns the right hexagon on a `Hexagon` layout — use it. Doing the
conversion by hand is needed in two cases: the rules run with no `Grid` (a headless test that
feeds world points), or the art has a gap or an overlap the Grid does not know about.

By hand, for point-top with cell size `(w, h)` and the board's origin at the centre of cell
`(0, 0)`:

```csharp
// Local point → fractional axial → nearest cube → offset cell.
static Vector3Int HexPick(float x, float y, float w, float h)
{
    double r = y / (0.75 * h);            // rows are 3/4 of a cell height apart
    double q = x / w - r / 2.0;           // each row is shifted half a cell per step of r
    return GridCoords.CubeToOffset(GridCoords.CubeRound(q, r, -q - r));
}
```

For flat-top (swizzle `YXZ`) swap the two inputs: `HexPick(y, x, w, h)`.

The work is in `CubeRound`: round all three cube numbers, then recompute the one that moved
furthest. Rounding the row first and then the column — the obvious way in offset coordinates —
treats each hexagon as a rectangle and is wrong in the four corners of every cell: about 8% of
clicks, every one of them next to an edge, where a player aiming between two units clicks.

Confirm the hand version against the engine before trusting it — in an EditMode or play-mode
test with the project's `Grid`:

```csharp
for (int i = 0; i < 2000; i++)
{
    var p = new Vector3(Random.Range(-6f, 6f), Random.Range(-6f, 6f), 0f);
    Vector3Int engine = grid.WorldToCell(p); engine.z = 0;
    Vector3 local = grid.WorldToLocal(p);
    Assert.AreEqual(engine, HexPick(local.x, local.y, grid.cellSize.x, grid.cellSize.y), $"at {p}");
}
```

A handful of mismatches exactly on cell edges is rounding and harmless. Mismatches across whole
rows mean the shift parity or the 3⁄4 spacing is not what the Grid uses — go back to the check
in `reference/coordinates.md`.

Tall pieces on a hexagonal board get the same treatment as on an isometric one: test the
sprites of the cells below the footprint first.

## Highlighting a range

Highlights are **tiles on a second Tilemap**, not sprites spawned per cell and not a tint on the
ground tiles:

```
Grid
├─ Ground      (Tilemap, the level)
├─ Highlight   (Tilemap, same Grid, order in layer above Ground and below the pieces)
└─ Pieces
```

```csharp
// Presenter. One tile asset per meaning: move, attack, path, hover.
[SerializeField] Tilemap _highlight;
[SerializeField] TileBase _moveTile, _attackTile, _pathTile;
readonly List<Vector3Int> _reachable = new List<Vector3Int>();

void ShowMoveRange(int unitId, int movePoints)
{
    _highlight.ClearAllTiles();
    _finder.Range(_board.Cells.CellOf(unitId), movePoints, _cost, _reachable);
    for (int i = 1; i < _reachable.Count; i++)               // 0 is the unit's own cell
        _highlight.SetTile(_reachable[i], _moveTile);
}

void ShowPathTo(Vector3Int hovered)
{
    if (!_finder.PathFromRange(hovered, _path)) return;      // not in range: leave the range showing
    for (int i = 1; i < _path.Count; i++) _highlight.SetTile(_path[i], _pathTile);
}
```

| Choice | Why |
|---|---|
| A separate Tilemap on the same `Grid` | It lines up on every layout for free, and `ClearAllTiles` is the whole "hide" |
| A tile per meaning, not `SetColor` on one tile | Colour alone fails for a colour-blind player: give move, attack and path different **shapes** (fill, outline, dots) |
| Clear and refill on selection change | A range is at most a few hundred cells; diffing is not worth the code |
| A third Tilemap for hover and path | Then moving the pointer redraws a handful of cells and never the range |
| Highlight below the pieces, above the ground | A highlight drawn over a unit hides which unit it is |

`SetTile` in a loop is fine up to a few hundred cells. Above that, fill two arrays and call
`SetTiles(positions, tiles)` once.

On an isometric board the highlight Tilemap needs the same sort settings as the ground it sits
on, or a highlighted cell behind a wall draws in front of it — `unity-2d-rendering` →
`reference/y-sort.md`. With `IsometricZAsY`, set the highlight at the cell's real z so it lifts
with the ground.

What the highlight shows is the board's answer, computed once: the same `_reachable` list is
what a click is validated against. A highlight computed one way and a click validated another
is "the game showed blue and refused the move".

## Traps

- **Picking from `transform.position` of the selected piece.** Mid-tween it is between cells.
  The selected unit's cell is `CellOf(id)`.
- **Hover recomputing the range.** The flood runs when the selection changes; hover only reads
  `CostTo` and `PathFromRange`.
- **A touch has no hover.** On a phone the first tap selects and shows the path, the second
  confirms. Design the command flow for that and the pointer version falls out —
  `unity-input` → `reference/touch-and-on-screen.md`.
- **Clicking through the HUD.** If a cell under a button gets selected, the UI test is missing
  from the reader, not from the picker.
- **The camera moved.** A pick cached from an earlier frame is stale after a pan or zoom;
  recompute hover from the current pointer position every frame.
