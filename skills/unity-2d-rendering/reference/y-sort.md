# Y-sort — depth from above, faked by one axis and one pivot

> Part of the `unity-2d-rendering` skill. A view from above has no depth: what is lower on
> screen is nearer, and the only thing that says so is draw order. This file is the whole
> set-up for the depot (top-down), then the differences for an isometric and a hexagonal
> sorting yard, then the point at which the axis stops being the right tool. The four keys
> themselves are in `reference/sort-order.md`.

## The set-up, in the order that fails

Everything here is key 4 — distance along the sort axis. It only decides between renderers that
are already equal on sorting layer, Order in Layer and render queue, so steps 3 and 4 matter as
much as step 1.

1. **The axis.** Sort mode `CustomAxis`, axis `(0, 1, 0)`: a larger y is further back and
   draws first. Where it is entered depends on the pipeline — the table in
   `reference/sort-order.md`; `Renderer2DSetup` has a menu command that sets it on the 2D
   Renderer in force. Run `Renderer2DSetup.Report()` afterwards and read `sortMode` back.
2. **The pivot at the feet.** Every sprite that takes part — runner, sentry, shelf, pickup,
   gate post — has its pivot where it touches the floor: `(0.5, 0)` for an upright sprite,
   slightly above the bottom edge for one drawn with a ground shadow. Setting pivots on a
   whole sheet is `unity-2d-sprites` → `reference/sprite-geometry.md`.
3. **`spriteSortPoint = Pivot`.** The default is `Center`. With `Center`, a shelf two units
   tall and a runner one unit tall swap when their centres cross, half a unit after the feet
   did: the runner's head draws behind a shelf it is standing in front of.

   ```csharp
   foreach (SpriteRenderer sr in depot.GetComponentsInChildren<SpriteRenderer>(true))
       if (sr.sortingLayerName == "Actors") sr.spriteSortPoint = SpriteSortPoint.Pivot;
   ```
4. **One sorting layer, one Order in Layer.** Everything that Y-sorts shares both. A shelf left
   on order 1 is in front of the runner at every y, and no axis will change that. The floor is
   on a layer below, overhead pieces on a layer above:

   | Sorting layer (top draws first) | Holds |
   |---|---|
   | `Floor` | Ground Tilemap, lane markings, decals |
   | `Shadows` | Blob shadows under actors |
   | `Actors` | Runner, sentries, pickups, shelves, gate posts, tall tiles |
   | `Overhead` | Gate lintel, shelf tops the runner walks under, canopies |

   The project-wide stack and the Tilemap that goes on each layer are `unity-2d-level` →
   `reference/layer-stack.md`.

Then put one shelf in the scene, walk the runner behind it and in front of it, and read both
frames. The swap must happen as the feet cross the shelf's base line.

## A character built from several sprites

A runner made of body, satchel and cap has three sort points. Without a group the cap can sort
behind a shelf while the body sorts in front of it.

- Put a `SortingGroup` on the root, on the `Actors` layer, order 0. The root's position is at
  the feet.
- Order the parts inside the group with Order in Layer: body 0, satchel 1, cap 2. These orders
  are local to the group and never compete with the shelf.
- A carried pickup becomes a child of the runner **inside** the group, with an order that puts
  it in front of or behind the body according to the facing direction.
- The blob shadow is not in the group. It sits on `Shadows`, so it never draws over another
  actor's feet.

A skeletal character is the same: one `SortingGroup` at the root, bones ordering the parts
inside it. Building that rig is `unity-2d-animation`.

## Tall objects: split the base from the top

One sprite with a foot pivot is enough for anything the runner walks around. Split only when
the runner can stand **inside** the object's footprint or walk **under** part of it.

- **The gate.** Two posts are `Actors` with foot pivots. The lintel across the top is a
  separate sprite on `Overhead`: the runner passes under it at every y.
- **A shelf run several cells deep.** The front face is `Actors`, pivot at its base. The top
  surface is `Overhead` if the runner can walk behind the run and should be hidden by it, and
  `Floor` if the runner can never be there.
- **A wide object with a slanted base** — a ramp drawn at an angle — has no single foot line.
  Cut it into columns one cell wide, each with its own pivot, or give it Order in Layer by
  hand and keep the runner off the ambiguous cells.

## Tiles that take part

A Tilemap in `Chunk` mode is in front of an actor or behind it as a whole. Put tall tiles —
shelving, pillars, crates painted as tiles — on their own Tilemap on the `Actors` layer with
`TilemapRenderer.mode = Individual`, and give those tile sprites a foot pivot. The floor
Tilemap stays in `Chunk` on `Floor`. Mode values and cost: `reference/sort-order.md`.

## Isometric

The principle is unchanged — lower on screen is nearer — and so is the axis for a plain
isometric grid: `CustomAxis`, `(0, 1, 0)`.

**Isometric Z as Y** adds height: a tile's z raises it on screen. A raised tile is higher in y
than the cell it stands on and would sort as if it were further back. The axis therefore takes
a negative z component so that height counts as nearness: start from `(0, 1, -0.26)`, then
walk a piece behind a raised tile and in front of it and read both frames. Change the z
component, not the y, if raised tiles sort early or late.

The Tile Palette has its own sort setting, separate from the scene's — a palette that draws
inside out in the palette window is fixed there, not here: `unity-tilemap` →
`reference/palette-and-grid.md`.

For the board itself:

- Tiles with any height go on a Tilemap in `Individual` mode on the same layer and order as
  the pieces; flat ground stays in `Chunk` below.
- Tile sprites pivot at the centre of their **base diamond**, not the centre of the image. A
  cube tile drawn 1 × 1 unit on a `(1, 0.5)` cell has its base centre a quarter of the way up.
- Pieces pivot at their feet and stand at the cell centre. A piece and the tile it stands on
  then share a y; the piece must win, so pieces are one Order in Layer above tall tiles
  **only if** nothing tall can be in front of a piece. When tall tiles can be in front, keep
  the same order and nudge the piece's sort position down by a small amount — a child sprite
  offset of `0.01` in y — so it never ties with its own cell.

## Hexagonal

Point-top and flat-top hexagonal boards both sort with `(0, 1, 0)`. Rows of a point-top board
are three quarters of a cell apart, so pieces in neighbouring rows never share a y. Two cases
tie:

- Two pieces in the same row have the same y. They do not overlap unless their sprites are
  wider than a cell; when they are, break the tie with x: an axis of `(0.01, 1, 0)` puts the
  piece on the right behind, consistently.
- On a flat-top board neighbouring columns are offset by half a cell in y, so a piece and the
  neighbour diagonally below it are ordered correctly by y alone.

## When to stop and use Order in Layer per row

The axis compares continuous positions. A board game has rows. Assign the order from the cell
when any of these is true:

- Pieces move cell to cell and a piece in transit should belong to its **destination** row for
  the whole tween, not swap halfway.
- Art arrives with centre pivots that cannot be changed.
- Two things on one cell must stack in a fixed order — cell highlight, pickup, runner.
- The audit reports ties that are legitimate equal positions.

```csharp
// Sorting yard: row 0 is the bottom row. Ten orders per row leave room to stack on a cell.
const int PerRow = 10;

static int OrderFor(Vector3Int cell, int stack)   // stack: 0 highlight, 1 pickup, 2 runner
{
    return -cell.y * PerRow + stack;
}
```

Set it when the piece commits to a cell, not every frame. Order in Layer spans −32768 to 32767,
so ten per row covers a board 3000 rows deep. Leave the axis on `(0, 1, 0)` anyway: it still
orders anything that was not given a row.

## Checks

- `SortingAudit.Json()` → `sortMode` is `CustomAxis`, `sortSource` names the place the pipeline
  reads, every Y-sorting sprite shows `sortPoint` `Pivot` or `GroupRoot`, `ties` is empty.
- Two screenshots per tall object: runner behind, runner in front.
- A journey that walks the depot aisle past a shelf can assert the order without a screenshot:
  record the runner's and the shelf's y and assert the runner's y is below the shelf's base
  whenever the runner is meant to be in front — recording a run is `unity-play-harness`.
