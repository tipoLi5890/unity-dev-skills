# 2D seen from above — action-adventure, twin-stick shooter, RPG

> Part of the `unity-gameplay` skill. Three types with one view and no gravity, which differ in
> what the second input does and whether movement is free or by the cell. Worked setting: the
> **depot** — aisles between shelving, pickups to collect, a sentry with a vision cone.

## The constraints

| Constraint | Action-adventure from above | Twin-stick shooter | RPG from above |
|---|---|---|---|
| View · projection | Top-down or three-quarter · orthographic | Top-down · orthographic | Three-quarter · orthographic |
| Movement model | Free, 8-way or analogue | Free, analogue; aim is independent of movement | Free, **or** one cell per step — decide once |
| Transform owner | A motor writing a `Rigidbody2D` with no gravity | The same | The same, or the cell map with the transform tweened |
| Facing | Last non-zero move direction, snapped to 4 or 8 | The aim direction, continuous | Last move direction, snapped to 4 |
| Camera | Follows; confined per room or per region | Follows the midpoint of player and aim, pulled back with speed | Follows; confined to the map |
| Level unit | Tile; a room is a screen or a few | Tile; an arena is one confined space | Tile; a map is larger than the screen, with interiors as separate maps |
| Draw order | Y-sort: lower on screen draws in front | Mostly flat; Y-sort only against tall cover | Y-sort throughout |

Underneath all three: **there is no "up" in the physics, so there is no ground check — and
depth is faked entirely by draw order.** Most of what goes wrong here is sorting, not movement.

## Numbers to decide first

| Number | Depot start | Decides |
|---|---|---|
| Pixels per unit · tile size | 16 PPU → 1 tile = 1 unit | The unit of everything else |
| Orthographic size | 5.625 → 20 × 11.25 tiles at 16:9 | How much of an aisle is visible; sentry sight has to fit inside it |
| Runner collider | A circle of radius 0.3 at the **feet**, not a box around the sprite | Whether a 1-tile aisle is passable; corner feel |
| Move speed · time to top speed · time to stop | 5 units/s · 0.08 s · 0.05 s | Responsiveness; anything above 0.15 s reads as ice |
| Aisle width | 2 tiles; 1 tile is a deliberate squeeze | Whether two bodies pass |
| Sentry sight | 6 units, 70° cone, 0.4 s to react | Fairness: the player sees the cone before it sees them |
| Shooter: fire rate · projectile speed · lifetime | 8 /s · 14 units/s · 1.2 s | Pool size = rate × lifetime × shooters (10 for one player) |
| RPG, by the cell: step time | 0.18 s per cell | Walk feel; input held longer than a step repeats it |

## Build order for the 3C prototype

1. **Greybox depot.** Two Tilemaps: a floor with no collider, and shelving on an `Obstacles`
   layer with a merged composite collider — `unity-2d-level` → `reference/layer-stack.md`,
   `unity-physics-2d` → `reference/tilemap-colliders.md`. One aisle 2 wide, one 1 wide, one dead
   end.
2. **Controls.** A struct with `move` (a `Vector2`) and, for the shooter, `aim` (a `Vector2`
   direction) and `fireHeld` — `unity-input`. Aim comes from the right stick **or** from the
   pointer converted to a direction from the player; gameplay sees one field either way.
3. **Character.** The motor from `unity-2d-controller`, chosen below; register with
   `GameProbe.SetPlayerVelocity(() => transform, () => (Vector3)_body.linearVelocity);`.
4. **Journey 1 — the aisle.** Enter the depot-aisle situation, drive along the 1-wide aisle and
   round a corner; assert the runner is never inside `Obstacles` and that speed never exceeds
   the designed top speed (a diagonal that is 41% fast shows up here).
5. **Camera.** `unity-camera` → `reference/follow-2d.md`; journey 2 asserts the confiner.
6. **Sorting.** Set the sort axis — `unity-2d-rendering` → `reference/y-sort.md` — put one tall
   shelf in the scene, walk behind and in front of it. This is a visual check: screenshot both —
   `unity-debug` → `reference/visual-checks.md`.
7. **Animation.** A direction parameter pair and a speed — `unity-2d-controller` →
   `reference/facing-and-animator-bridge.md`, then `unity-animation` →
   `reference/blend-trees.md`.

### The motor — which file

Decide free or by the cell before opening anything: `unity-2d-controller` →
`reference/model-choice.md`. A map authored to the cell is moved on by the cell.

- **Free movement** — a `Rigidbody2D` with gravity scale 0 on the body, not in Project Settings,
  a circle at the feet, input clamped rather than normalised:
  `unity-2d-controller` → `reference/topdown-free.md`.
- **By the cell** (the RPG option) — the map owns the position and the transform is tweened to
  it: `unity-2d-controller` → `reference/grid-step.md`; who stands on which cell is
  `unity-2d-grid` → `reference/occupancy-and-turns.md`.

### Draw order from above

Depth is draw order and nothing else: a sort axis of `(0, 1, 0)`, pivots at the feet, one sorting
layer for everything that Y-sorts, tall tiles sorted individually, a multi-sprite character
grouped. The method and the audit are `unity-2d-rendering` → `reference/y-sort.md`; when two
things still draw in the wrong order, the precedence is `unity-2d-rendering` →
`reference/sort-order.md`.

## Traps

- **Snagging on corners, an analogue stick that is always full speed, a facing that flickers
  against a wall** are controller faults with one fix each — `unity-2d-controller` →
  `reference/topdown-free.md`.
- **Twin-stick aim from the mouse in screen space.** A camera that leads the aim moves the
  pointer's world position every frame, so smooth the camera, not the aim —
  `unity-input` → `reference/pointer-and-aim.md`.
- **Fast projectiles tunnel through thin walls.** A 14 units/s projectile moves 0.28 units per
  step; continuous detection or a cast from the previous position to the next —
  `unity-physics-2d` → `reference/bodies-and-simulation.md`.
- **`Instantiate` per shot.** Pool projectiles (`UnityEngine.Pool.ObjectPool<T>`); size from the
  numbers table.
- **The sentry's cone drawn wider than it tests.** Draw the cone mesh from the same angle and
  range the test uses. The test: distance under range, then angle between sentry facing and the
  direction to the runner under half the cone, then one `Physics2D.Linecast` against `Obstacles`
  for cover — cheapest check first, and at a fixed interval (0.1 s), not every frame.
- **Rooms that scroll one tile.** A room 1 tile wider than the screen scrolls by that one tile
  and reads as a bug. Either lock it to the screen or make it at least 1.5 screens.
- **RPG: free movement on a tile-authored map without sub-tile collision** leaves the player
  snagging on every half-open doorway. If the map is authored to the cell, move by the cell.
- **Interiors as additive geometry on the same map** put two rooms' sorting in one space. Give
  each interior its own scene or its own far-away region and cut the camera.

## Where each need is answered

| Need | Answer |
|---|---|
| Move and aim actions, the input struct, a scripted driver | `unity-input` → `reference/reading-input.md` |
| Pointer to world, stick aim, aim assist | `unity-input` → `reference/pointer-and-aim.md` |
| On-screen sticks for touch | `unity-input` → `reference/touch-and-on-screen.md` |
| The free motor: acceleration, diagonals, corners, facing | `unity-2d-controller` → `reference/topdown-free.md` |
| One cell per step, buffered input, hold-to-repeat | `unity-2d-controller` → `reference/grid-step.md` |
| Body type, gravity scale, continuous detection | `unity-physics-2d` → `reference/bodies-and-simulation.md` |
| Shelving colliders from a Tilemap | `unity-physics-2d` → `reference/tilemap-colliders.md` |
| Linecasts, overlap queries, a query that misses | `unity-physics-2d` → `reference/queries-2d.md` |
| Which layers collide: runner, obstacles, projectiles, pickups | `unity-physics-2d` → `reference/layers-and-matrix.md` |
| Y-sort, feet pivots, tall tiles, sorting groups | `unity-2d-rendering` → `reference/y-sort.md` |
| 2D lights, a sentry's lit cone, shadows from shelving | `unity-2d-rendering` → `reference/lights-2d.md`, then `unity-2d-rendering` → `reference/shadows-and-normals.md` |
| Follow, confiner per room, group framing of player and aim | `unity-camera` → `reference/follow-2d.md` |
| Pixel-perfect follow | `unity-camera` → `reference/pixel-perfect-follow.md` |
| Facing as Animator parameters | `unity-2d-controller` → `reference/facing-and-animator-bridge.md` |
| Four- and eight-direction blend trees | `unity-animation` → `reference/blend-trees.md` |
| A sprite state graph per direction | `unity-animation` → `reference/sprite-state-graph.md` |
| Slicing directional sheets, feet pivots | `unity-2d-sprites` |
| Floor and shelving palettes, rule tiles | `unity-tilemap` |
| Floor, shelving and overhead Tilemaps as one stack | `unity-2d-level` → `reference/layer-stack.md` |
| Rooms and regions as data; maps from LDtk or Tiled | `unity-2d-level` → `reference/rooms-and-chunks.md`, then `unity-2d-level` → `reference/external-editors.md` |
| A sentry that paths round shelving | `unity-2d-grid` → `reference/pathfinding.md` |
| Sight blocked by shelving, cell by cell | `unity-2d-grid` → `reference/line-of-sight.md` |
| Journeys; the 2D never-inside invariant | `unity-play-harness` → `reference/journeys.md` |
| Sentry: patrol, see, chase | this file, "Traps" for the sight test; the state machine is three states — Patrol (waypoints), Alert (hold and face for the reaction time), Chase (steer at the last seen position) — with the state exposed to the probe through `GameProbe.Register` |
| Pickups | a trigger on its own layer; the pickup reports once and returns to `PickupPool` |
| Dialogue boxes, inventory screens, HUD | `unity-game-ui` |
| Text in more than one language | `unity-localization` |
