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
| Coyote time · jump buffer | 0.1 s · 0.1 s | Whether an edge jump or an early press is forgiven |
| Jump cut on release | upward velocity × 0.5 | The short hop |

Auto-runner adds: forward speed at 0 m and at 1000 m (8 → 14), and the chunk length (40 units).
Exploration adds: the screen as the room unit (20 × 11.25 units; no room is smaller in either
dimension, and neighbouring rooms share the full height or width of the edge they meet on).

## Build order for the 3C prototype

1. **Greybox strip.** One Tilemap of solid tiles with a `TilemapCollider2D` set to merge into a
   `CompositeCollider2D` on a static body, on a `Rooftop` layer: a flat run, a 5-tile gap, a
   2-tile ledge, a 3-tile drop. Palette and tiles — `unity-tilemap`.
2. **Controls.** One struct per frame (`move`, `jumpHeld`, `jumpPressed`) from `unity-input`;
   the motor never reads a device.
3. **Character.** The motor below. Register it with the probe:
   `GameProbe.SetPlayerVelocity(() => transform, () => (Vector3)_body.linearVelocity);` and
   `GameProbe.Register("grounded", () => Grounded);`
4. **Journey 1 — the jump is the designed jump.** Enter the ledge-drop situation, hold right,
   press jump on level ground, then run `scripts/jump_report.py` against the fixed-step apex.
5. **Camera.** `unity-camera` → `reference/follow-2d.md`. Journey 2: the runner stays inside
   the frame and the camera never shows past the level bounds.
6. **Journey 3 — the forgiving edges.** Jump 0.08 s after leaving the ledge (accepted) and
   0.15 s after (refused); press jump 0.08 s before landing (fires on landing).
7. **Animation last.** States follow facts the motor already exposes — `unity-animation` →
   `reference/sprite-state-graph.md`.

### The motor, in essentials

```csharp
// RunnerMotor2D.cs — drop on the runner beside a Rigidbody2D (Dynamic, Gravity Scale 0,
// Freeze Rotation Z, Interpolate) and a BoxCollider2D carrying a zero-friction PhysicsMaterial2D.
using UnityEngine;

[RequireComponent(typeof(Rigidbody2D), typeof(BoxCollider2D))]
public class RunnerMotor2D : MonoBehaviour
{
    public float runSpeed = 8f, groundAccel = 80f, airAccel = 40f;
    public float gravity = 37.5f, jumpVelocity = 15f, fallMultiplier = 1.5f, maxFallSpeed = 20f;
    public float coyoteTime = 0.1f, jumpBuffer = 0.1f, skin = 0.05f;
    public LayerMask ground;

    public bool Grounded { get; private set; }
    public float MoveInput;           // set every frame from the input struct
    public bool JumpHeld;

    Rigidbody2D _body; BoxCollider2D _box;
    readonly RaycastHit2D[] _hits = new RaycastHit2D[4];
    ContactFilter2D _filter;
    float _sinceGrounded = 99f, _sincePressed = 99f;
    bool _cut;

    void Awake()
    {
        _body = GetComponent<Rigidbody2D>(); _box = GetComponent<BoxCollider2D>();
        _filter.SetLayerMask(ground);
        _filter.SetNormalAngle(45f, 135f);       // floors only: a wall is not ground
    }

    public void PressJump() => _sincePressed = 0f;   // called on the frame; consumed on the step

    void FixedUpdate()
    {
        float dt = Time.fixedDeltaTime;
        Vector2 v = _body.linearVelocity;

        Grounded = v.y <= 0.01f && _box.Cast(Vector2.down, _filter, _hits, skin) > 0;
        _sinceGrounded = Grounded ? 0f : _sinceGrounded + dt;
        _sincePressed += dt;

        float accel = Grounded ? groundAccel : airAccel;
        v.x = Mathf.MoveTowards(v.x, MoveInput * runSpeed, accel * dt);

        bool jumped = _sincePressed <= jumpBuffer && _sinceGrounded <= coyoteTime;
        if (jumped)
        {
            v.y = jumpVelocity;                  // assign, never add: a slope must not boost it
            _sincePressed = _sinceGrounded = 99f;
            _cut = false;
        }
        if (Grounded && !jumped) v.y = 0f;
        else                                     // gravity from the take-off step on: apex 2.85
        {
            if (v.y > 0f && !JumpHeld && !_cut) { v.y *= 0.5f; _cut = true; }   // the short hop, once
            v.y -= gravity * (v.y < 0f ? fallMultiplier : 1f) * dt;
            v.y = Mathf.Max(v.y, -maxFallSpeed);
        }
        _body.linearVelocity = v;
    }
}
```

Slopes, moving platforms and wall jumps are extensions of the same loop:
project the horizontal velocity along the ground normal the cast returned; add the platform's
velocity while grounded on it; treat a wall contact as a second "grounded" with its own timer.
In Unity 6 a kinematic body moved with `Rigidbody2D.Slide` and a `Rigidbody2D.SlideMovement`
gives the same result with the engine resolving slopes — choose one model per project.

## Traps

- **Friction is why the runner sticks to walls.** The default material has friction 0.4, and
  pressing into a wall while falling holds the body there. Zero-friction `PhysicsMaterial2D` on
  the character's collider, not on the level.
- **Tile seams catch a box collider.** Individual tile colliders have internal edges; a body
  sliding across them snags at speed. Merge them through a `CompositeCollider2D` —
  `TilemapCollider2D.compositeOperation = Collider2D.CompositeOperation.Merge`.
- **Input read in `FixedUpdate` drops presses.** A press that begins and ends between two steps
  is never seen. Latch it on the frame (`PressJump()`), consume it on the step.
- **`OnCollisionEnter2D` for grounding is a frame late and wrong on walls.** Cast, with a normal
  filter.
- **One-way platforms need three settings.** `PlatformEffector2D.useOneWay`, the collider's
  `usedByEffector`, and a `surfaceArc` narrow enough (about 170°) that the sides do not count as
  top. Dropping through is `Physics2D.IgnoreCollision` for 0.25 s, not disabling the platform.
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
| Follow, dead zone, look-ahead, room confiner | `unity-camera` → `reference/follow-2d.md` |
| Camera jitter against a fixed-step body | `unity-camera` → `reference/update-order-and-jitter.md` |
| Idle / run / jump / fall as a sprite state graph | `unity-animation` → `reference/sprite-state-graph.md` |
| Frames into clips, pivots on one ground line | `unity-2d-sprites` → `reference/sprite-animation.md` |
| Tile Palette, rule tiles for the rooftops | `unity-tilemap` |
| Crisp pixels at the chosen PPU | `unity-2d-pixel-perfect` |
| Situations, journeys, the 2D never-inside invariant | `unity-play-harness` → `reference/journeys.md` |
| Jump and reach numbers | `reference/level-metrics.md` |
| The motor, one-way platforms, tilemap colliders | this file — "The motor, in essentials" and "Traps" |
| Rooms and chunks | this file: each room is at least one screen, with one `PolygonCollider2D` as its confiner bounds; chunks are prefabs with entry and exit markers at fixed height, pooled and placed end to end |
| Pickups and hazards | this file: a trigger collider on its own layer; the handler lives on the pickup and calls the game state once, then returns itself to the pool — never `Destroy` in the hot path |
| HUD: distance, pickups | `unity-game-ui` |
