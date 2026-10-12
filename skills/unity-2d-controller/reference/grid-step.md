# Moving by the cell — the step is a picture of a move that already happened

> Part of the `unity-2d-controller` skill. `resources/GridStepMover.cs`: how a held direction
> becomes steps, what happens on the frame a step starts, how one step is buffered and what a
> refused step looks like. It covers the **showing** of a cell move. The cell truth —
> coordinates for rectangular, isometric and hexagonal boards, occupancy, turn order,
> pathfinding — is `unity-2d-grid`. Worked setting: the **sorting yard** — the runner steps a
> cell and pushes pickups onto gate cells.

## 1. Commit, then show

```
input ──► direction ──► CanEnter(from, to)? ──no──► bump (0.12 s), Blocked raised, cell unchanged
                              │ yes
                              ▼
                        Cell = to            ← the truth changes on this line
                        Committed(from, to)  ← occupancy is updated here, before anything is drawn
                        tween from → to over stepTime
                        Arrived(to)          ← pickups, gates, end of turn
```

The cell changes when the step **starts**. For `stepTime` seconds the transform is somewhere
between two cells and means nothing; everything that asks where the runner is asks `Cell`.

| Question | Ask | Never |
|---|---|---|
| Is the runner on the gate cell? | `mover.Cell == gateCell` | `Vector2.Distance(transform.position, gateCentre) < 0.1f` |
| May a sentry enter this cell? | The map's occupancy | An `OverlapPoint` at the cell centre |
| Which cell is the runner in, for a save? | `mover.Cell` | `WorldToCell(transform.position)` — wrong for half of every step |

Committing first is also what makes two movers safe: the second one to ask finds the cell
taken, however far the first one's picture has got.

## 2. The mover holds no map

Two delegates connect it to whatever owns the board:

```csharp
// occupancy is a GridOccupancy (unity-2d-grid); the mover speaks Vector2Int, the map Vector3Int.
mover.CanEnter   = (from, to) => occupancy.CanEnter((Vector3Int)to);        // the map decides
mover.CellCentre = cell => grid.GetCellCenterWorld((Vector3Int)cell);       // the map says where
mover.Committed += (from, to) => occupancy.TryMove(runnerId, (Vector3Int)to);
mover.Arrived   += cell => yard.OnRunnerArrived(cell);
mover.PlaceAt(startCell);
```

- With `CanEnter` unassigned every step is allowed; with `CellCentre` unassigned cells are a
  rectangular layout from `origin` and `cellSize`. That is enough for a greybox with walls
  tested by `Tilemap.HasTile`:
  `mover.CanEnter = (from, to) => !walls.HasTile((Vector3Int)to);`
- `Grid.GetCellCenterWorld` returns the centre for whichever layout the `Grid` has, so the same
  mover walks a rectangular, isometric or hexagonal board. What a **direction** means on each —
  six neighbours on a hexagon, the offset-row parity rule, the diamond's screen axes — is
  `unity-2d-grid` → `reference/coordinates.md`.
- Occupancy, reservations and who moves when: `unity-2d-grid` →
  `reference/occupancy-and-turns.md`.

**Pushing a pickup** is a `CanEnter` that looks one cell further and moves the pickup on yes:

```csharp
mover.CanEnter = (from, to) =>
{
    if (yard.IsWall(to)) return false;
    if (!yard.HasPickup(to)) return true;
    Vector2Int beyond = to + (to - from);
    if (yard.IsWall(beyond) || yard.HasPickup(beyond)) return false;   // one pickup, one cell
    yard.MovePickup(to, beyond);                                        // its own mover tweens it
    return true;
};
```

The pickup's cell changes inside the same call, so the board is never in a state where the
runner and the pickup share a cell.

## 3. Held input becomes steps

A step is not a button, and a held key must walk. `StepRepeater` (in `unity-input` →
`resources/RunInput.cs`) turns the `move` level into steps: one at once, then after
`repeatDelay` (0.25 s), then every `repeatInterval`.

| Number | Default | Rule |
|---|---|---|
| `stepTime` | 0.18 s | Under 0.10 a step reads as a teleport; over 0.25 as wading |
| `repeatDelay` | 0.25 s | Longer than `stepTime`, so a tap is always exactly one step |
| `repeatInterval` | 0.18 s | Equal to `stepTime` for a continuous walk; shorter fills the buffer and adds a step after release |
| Stick threshold | 0.5 | High on purpose: a diagonal must not flicker between two axes |

- **Not the OS key repeat** — it differs per machine and does not exist on a gamepad. **Not a
  Hold interaction** — it fires once.
- The repeater reads in `FixedUpdate` on the game clock, so the walk speed does not change with
  the frame rate; the tween runs in `Update`, so it is smooth.
- A diagonal on the stick resolves to its dominant axis: four directions, never a diagonal
  step. A board with diagonal or hexagonal moves quantises differently — do it in a small
  replacement for the repeater's direction, and keep the timing.
- A turn-based game sets `driveFromInput` off and calls `TryStep` from its turn code, which is
  also how a sentry or a replay moves: the same mover, a different caller.

## 4. One step of buffer

A request made during a step is kept — one, the latest. When the step arrives the buffered
direction starts on the same frame, so chained steps have no gap and a turn pressed a little
early is taken.

- **One deep, not a queue.** Three buffered steps is a runner that keeps walking after the
  player stopped pressing, into the hazard they were avoiding.
- **Latest wins.** Pressing left then up during one step goes up.
- `Arrived` is raised before the buffer is read. A handler that ends the turn, teleports the
  runner (`PlaceAt` clears the buffer) or opens a menu stops the buffered step from starting.
- With `repeatInterval` below `stepTime` the buffer is refilled by the repeater itself on every
  step, and releasing the key still walks one more cell. Keep the interval at or above the step.

## 5. A refused step

`CanEnter` false plays a bump: the transform goes `bumpDistance` (15%) of the way towards the
refused cell and back over `bumpTime` (0.12 s). `Blocked(from, to)` is raised for a sound.
`Cell` does not change and `Steps` does not count.

- The bump is feedback that the press was heard. With nothing, a player facing a wall cannot
  tell a refused step from a dropped input.
- `Facing` still turns towards the refused cell, so an interact press after bumping a gate
  targets the gate.
- A held direction into a wall bumps at the repeat rate. If that is too much, raise the bump
  once per held direction: reset a flag when `move` returns to zero.
- A turn-based game decides whether a refused step costs the turn. Usually not: `Blocked` does
  not end it, `Arrived` does.

## 6. The tween

Linear by default: chained steps then move at one constant speed with no stutter at cell
boundaries. `ease` (smoothstep) suits single deliberate steps — a tactics unit, a puzzle push —
and makes a held walk pulse.

- Speed while stepping is `cellSize / stepTime`: 5.6 units/s at the defaults. `Velocity`
  reports it for the Animator and the probe, and is zero between steps.
- The tween writes x and y and leaves z alone: z is sorting depth in a 2D scene.
- On an isometric board a step east and a step north cover different screen distances in the
  same `stepTime`. That is correct — the cell is the unit, not the pixel.
- Triggers on the way (a pickup's collider) fire from the transform, mid-step, before
  `Arrived`. Collect on `Arrived` from the cell, and keep colliders for nothing but pointer
  picking.

## 7. Checks

| Check | How |
|---|---|
| The cell leads the picture | Register `cellX`, `cellY` and `stepping` on the probe; in a journey, the cell changes on the sample the step starts and `pos` reaches the centre `stepTime` later |
| A tap is one step | `ScriptedRunInput.SetMove(right)` for 0.1 s, then zero: `Steps` is 1. A level held for a single frame can fall between two fixed steps and never be read |
| A hold walks at the repeat rate | Hold for 1 s: `Steps` is 1 + ⌊(1 − 0.25) / 0.18⌋ + 1 = 6, within one |
| A wall refuses | Step into a wall cell: `Steps` unchanged, `Cell` unchanged, `Blocked` raised once |
| The push rule | The yard-step situation: one step pushes the pickup onto the gate cell; a second pickup behind the first refuses the step |

## Where each need is answered

| Need | Answer |
|---|---|
| Cell coordinates on rectangular, isometric and hexagonal boards | `unity-2d-grid` → `reference/coordinates.md` |
| Occupancy, reservations, turn order | `unity-2d-grid` → `reference/occupancy-and-turns.md` |
| A route of several cells to a clicked cell | `unity-2d-grid` → `reference/pathfinding.md` |
| Which cell the pointer is over | `unity-2d-grid` → `reference/picking.md` |
| The repeater, the input struct | `unity-input` → `reference/reading-input.md` |
| Walk frames in four directions from `Facing` | `reference/facing-and-animator-bridge.md` |
| Grid layouts and palettes for the board | `unity-tilemap` |
