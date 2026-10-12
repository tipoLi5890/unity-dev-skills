# 2D seen from the side — platformer, exploration platformer, auto-runner

> Part of the `unity-gameplay` skill. Three types that share a view and a movement model and
> differ in what the camera and the level do. Worked setting: the **side run** — the runner
> crosses rooftops, drops off a ledge, and reaches the gate.

## The constraints

| Constraint | Platformer | Exploration platformer (gated rooms, backtracking) | Auto-runner |
|---|---|---|---|
| View · projection | Side · orthographic | Side · orthographic | Side · orthographic |
| Movement model | Free on X, gravity on Y | The same, plus abilities that change reach | Forward speed is given; the player owns jump and duck only |
| Transform owner | A motor writing a `Rigidbody2D` | The same motor; abilities are states of it | The same motor with the horizontal input replaced by a speed curve |
| Camera | Follows with a dead zone and look-ahead, clamped to the level | Confined to the current room; blends or cuts on the room boundary | Fixed horizontal offset ahead of the runner; never follows Y jitter |
| Level unit | Tile | Tile, grouped into rooms no smaller than one screen | Chunk: a pre-built strip several screens long |
| Level is | Hand-built, linear | Hand-built, a graph of rooms with gates keyed to abilities | Chunks stitched at runtime, difficulty by distance |

The one decision underneath all three: **the character is not simulated by the physics engine; it
asks the engine where the ground is and decides its own velocity.** A body left to the solver
slides on slopes, sticks to walls by friction and bounces off corners. A motor that owns velocity
does none of that.

## Numbers to decide first

| Number | Side-run start | Decides |
|---|---|---|
| Pixels per unit · tile size | 16 px sprites at 16 PPU → 1 tile = 1 unit | Every other number's unit |
| Orthographic size | 5.625 → 20 × 11.25 units at 16:9 (320 × 180 px at 16 PPU) | How far ahead the player sees: half a screen at run speed 8 is 1.25 s |
| Runner collider | 0.8 wide × 1.8 tall | Door and ceiling sizes |
| Apex height · time to apex | 3 units · 0.4 s → gravity 37.5, jump velocity 15 | The whole reach table — `reference/level-metrics.md` |
| Run speed · time to top speed | 8 units/s · 0.1 s on ground, 0.2 s in air | Gap widths, how precise landings feel |
| Fall multiplier · max fall speed | 1.5 · 20 units/s | Weight; how readable a long drop is |
| Coyote time · jump buffer | 0.1 s · 0.12 s | Whether an edge jump or an early press is forgiven |
| Jump cut on release | upward velocity × 0.5 | The short hop |

Auto-runner adds: forward speed at 0 m and at 1000 m (8 → 14), and the chunk length (40 units).
Exploration adds: the screen as the room unit (20 × 11.25 units; no room is smaller in either
dimension, and neighbouring rooms share the full height or width of the edge they meet on).

## Build order for the 3C prototype

1. **Greybox strip.** One Tilemap of solid tiles on a `Rooftop` layer: a flat run, a 5-tile gap,
   a 2-tile ledge, a 3-tile drop. Palette and tiles — `unity-tilemap`; which Tilemap carries the
   collider — `unity-2d-level` → `reference/layer-stack.md`; merging the tile colliders into one
   outline — `unity-physics-2d` → `reference/tilemap-colliders.md`.
2. **Controls.** One struct per frame (`move`, `jumpHeld`, `jumpPressed`) from `unity-input`;
   the motor never reads a device.
3. **Character.** The motor from `unity-2d-controller`, chosen below. Register it with the probe:
   `GameProbe.SetPlayerVelocity(() => transform, () => (Vector3)_body.linearVelocity);` and
   `GameProbe.Register("grounded", () => Grounded);`
4. **Journey 1 — the jump is the designed jump.** Enter the ledge-drop situation, hold right,
   press jump on level ground, then run `scripts/jump_report.py` against the fixed-step apex.
5. **Camera.** `unity-camera` → `reference/follow-2d.md`. Journey 2: the runner stays inside
   the frame and the camera never shows past the level bounds.
6. **Journey 3 — the forgiving edges.** Jump 0.08 s after leaving the ledge (accepted) and
   0.15 s after (refused); press jump 0.08 s before landing (fires on landing).
7. **Animation last.** States follow facts the motor already exposes — `unity-2d-controller` →
   `reference/facing-and-animator-bridge.md`, then `unity-animation` →
   `reference/sprite-state-graph.md`.

### The motor — which file

The motor, its scripts and its journey template are `unity-2d-controller`. Three reads, in order:

- **Which body model.** A kinematic body the motor slides, or a dynamic body whose velocity the
  motor assigns — one per project, and neither is left to the solver:
  `unity-2d-controller` → `reference/model-choice.md`.
- **The numbers above as gravity and jump velocity**, and what the fixed step does to the apex:
  `unity-2d-controller` → `reference/jump-maths.md`.
- **Grounding, slopes, one-way and moving platforms, coyote time, buffer, the short hop, dash,
  wall jump:** `unity-2d-controller` → `reference/platformer.md`.

The auto-runner is the same motor with the horizontal input replaced by a speed curve; an
exploration ability is a state of it, never a second motor.

## Traps

- **A runner that sticks to walls, snags on tile seams or lands on the side of a one-way
  platform** has a physics set-up fault, not a genre one: `unity-physics-2d` →
  `reference/tilemap-colliders.md` for seams, `unity-physics-2d` →
  `reference/effectors-and-joints.md` for one-way platforms, and `unity-2d-controller` →
  `reference/platformer.md` for a grounded flag that is late or true on walls.
- **A jump press that sometimes does nothing** is input read on the fixed step — `unity-input` →
  `reference/reading-input.md`.
- **The camera following Y makes every jump nauseous.** Follow X tightly and Y only when the
  runner lands on a new height — `unity-camera` → `reference/follow-2d.md`.
- **Pixel art with a damped camera shimmers.** Sub-pixel camera positions resample every sprite —
  `unity-camera` → `reference/pixel-perfect-follow.md`, then `unity-2d-pixel-perfect`.
- **Exploration: a new ability changes the reach table.** A double jump is a second apex stacked
  on the first; re-run `scripts/level_metrics.py` per ability set, and check every gate against
  the set the player is guaranteed to have there — a gate reachable one ability early is a
  sequence break, deliberate or not.
- **Exploration: a room smaller than the screen.** A confined camera has no legal position in a
  room narrower or shorter than its view, and shows the neighbour. Keep every room at least one
  screen in both dimensions, and put room edges on tile boundaries.
- **Runner: chunks that are individually fair and jointly impossible.** The exit of one chunk and
  the entry of the next form a gap nobody measured. Give every chunk a flat run-in and run-out
  at least `run speed × 0.4 s` long, and check the stitched pair, not the chunk.
- **Runner: the world moving instead of the runner** breaks the probe's `pos` and every journey
  that reads it. Move the runner; recentre the world every 1000 units if precision demands it.

## Where each need is answered

| Need | Answer |
|---|---|
| Action asset, the input struct, a scripted driver for journeys | `unity-input` → `reference/reading-input.md` |
| Touch buttons for jump and duck | `unity-input` → `reference/touch-and-on-screen.md` |
| The motor: grounding, slopes, platforms, coyote time, buffer, dash, wall jump | `unity-2d-controller` → `reference/platformer.md` |
| Gravity and jump velocity from apex and time to apex | `unity-2d-controller` → `reference/jump-maths.md` |
| Body type, interpolation, the simulation step | `unity-physics-2d` → `reference/bodies-and-simulation.md` |
| Ground casts and overlap queries that miss | `unity-physics-2d` → `reference/queries-2d.md` |
| Tilemap colliders, composites, tile seams | `unity-physics-2d` → `reference/tilemap-colliders.md` |
| One-way platforms, moving platforms, conveyor surfaces | `unity-physics-2d` → `reference/effectors-and-joints.md` |
| Which layers collide: runner, rooftop, hazard, pickup | `unity-physics-2d` → `reference/layers-and-matrix.md` |
| Follow, dead zone, look-ahead, room confiner | `unity-camera` → `reference/follow-2d.md` |
| Camera jitter against a fixed-step body | `unity-camera` → `reference/update-order-and-jitter.md` |
| Skyline layers that scroll slower than the rooftops | `unity-2d-rendering` → `reference/parallax.md` |
| What draws in front of what; sorting layers | `unity-2d-rendering` → `reference/sort-order.md` |
| 2D lights, shadows on the rooftops | `unity-2d-rendering` → `reference/lights-2d.md` |
| Facing and the motor's facts as Animator parameters | `unity-2d-controller` → `reference/facing-and-animator-bridge.md` |
| Idle / run / jump / fall as a sprite state graph | `unity-animation` → `reference/sprite-state-graph.md` |
| Frames into clips, pivots on one ground line | `unity-2d-sprites` → `reference/sprite-animation.md` |
| A runner drawn as bones and weights instead of frames | `unity-2d-animation` → `reference/skeletal-vs-frames.md` |
| Tile Palette, rule tiles for the rooftops | `unity-tilemap` |
| Background, solid and decoration Tilemaps as one stack | `unity-2d-level` → `reference/layer-stack.md` |
| Rooms as data, room bounds, chunks stitched at runtime | `unity-2d-level` → `reference/rooms-and-chunks.md` |
| Levels from a file; LDtk or Tiled as the editor | `unity-2d-level` → `reference/level-data.md`, then `unity-2d-level` → `reference/external-editors.md` |
| Curved rooftops and slopes from a spline | `unity-2d-level` → `reference/sprite-shape.md` |
| Crisp pixels at the chosen PPU | `unity-2d-pixel-perfect` |
| Situations, journeys, the 2D never-inside invariant | `unity-play-harness` → `reference/journeys.md` |
| Jump and reach numbers a level may contain | `reference/level-metrics.md` |
| Pickups and hazards | this file: a trigger collider on its own layer; the handler lives on the pickup and calls the game state once, then returns itself to the pool — never `Destroy` in the hot path |
| HUD: distance, pickups | `unity-game-ui` |
