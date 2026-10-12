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
   layer with a merged composite collider. One aisle 2 wide, one 1 wide, one dead end.
2. **Controls.** A struct with `move` (a `Vector2`) and, for the shooter, `aim` (a `Vector2`
   direction) and `fireHeld` — `unity-input`. Aim comes from the right stick **or** from the
   pointer converted to a direction from the player; gameplay sees one field either way.
3. **Character.** The motor below; register with
   `GameProbe.SetPlayerVelocity(() => transform, () => (Vector3)_body.linearVelocity);`.
4. **Journey 1 — the aisle.** Enter the depot-aisle situation, drive along the 1-wide aisle and
   round a corner; assert the runner is never inside `Obstacles` and that speed never exceeds
   the designed top speed (a diagonal that is 41% fast shows up here).
5. **Camera.** `unity-camera` → `reference/follow-2d.md`; journey 2 asserts the confiner.
6. **Sorting.** Set the sort axis, put one tall shelf in the scene, walk behind and in front of
   it. This is a visual check: screenshot both — `unity-debug` → `reference/visual-checks.md`.
7. **Animation.** A direction parameter pair and a speed — `unity-animation` →
   `reference/blend-trees.md`.

### The motor, in essentials

```csharp
// DepotMotor2D.cs — drop on the runner beside a Rigidbody2D (Dynamic, Gravity Scale 0,
// Linear Damping 0, Freeze Rotation Z, Interpolate) and a CircleCollider2D at the feet.
using UnityEngine;

[RequireComponent(typeof(Rigidbody2D))]
public class DepotMotor2D : MonoBehaviour
{
    public float speed = 5f, accel = 62.5f, decel = 100f;   // 5 / 0.08 s, 5 / 0.05 s
    public Vector2 MoveInput;                               // set every frame from the input struct
    public Vector2 Facing { get; private set; } = Vector2.down;

    Rigidbody2D _body;
    void Awake() => _body = GetComponent<Rigidbody2D>();

    void FixedUpdate()
    {
        // Clamp, do not normalise: a half-pushed stick must stay half speed, and a keyboard
        // diagonal of (1, 1) must not be 41% faster than a cardinal.
        Vector2 wish = Vector2.ClampMagnitude(MoveInput, 1f) * speed;
        float rate = wish.sqrMagnitude > 0.0001f ? accel : decel;
        _body.linearVelocity = Vector2.MoveTowards(_body.linearVelocity, wish,
                                                   rate * Time.fixedDeltaTime);
        if (MoveInput.sqrMagnitude > 0.04f) Facing = Snap4(MoveInput);
    }

    static Vector2 Snap4(Vector2 v) =>
        Mathf.Abs(v.x) > Mathf.Abs(v.y) ? new Vector2(Mathf.Sign(v.x), 0f)
                                        : new Vector2(0f, Mathf.Sign(v.y));
}
```

Set gravity to zero **per body** (Gravity Scale 0) rather than in Project Settings: project
gravity at zero also takes it from every prop that was meant to fall, while a body's own scale is
visible on the prefab. The fingerprint reads either.

**By the cell instead** (the RPG option): the map owns the position. On input, compute the
target cell; refuse it if the obstacle Tilemap has a tile there (`Tilemap.HasTile`) or another
actor occupies it; otherwise mark the target occupied *now* and tween the transform to
`Grid.GetCellCenterWorld(target)` over the step time. Input during a step is buffered, one deep.
Nothing in that loop needs a `Rigidbody2D` to move — keep a kinematic one only so triggers fire.

### Draw order from above

1. **Sort axis.** In the 2D Renderer Data asset (URP), Transparency Sort Mode `Custom Axis`,
   axis `(0, 1, 0)`. In the Built-in pipeline the same pair is under Project Settings → Graphics.
2. **Pivot at the feet.** Every sprite that sorts — characters, shelves, pickups — has its pivot
   where it touches the floor, and `SpriteRenderer.spriteSortPoint` set to `Pivot`. Centre pivots
   are why a character's head sorts behind a crate it is standing in front of.
3. **One sorting layer for everything that Y-sorts**, same order in layer. Floor goes on a layer
   below, overhead cover on a layer above.
4. **Tall tiles sort individually.** A Tilemap in `Chunk` mode sorts as one object; shelving the
   player walks behind needs `TilemapRenderer.mode = TilemapRenderer.Mode.Individual` on its own
   Tilemap. Keep the floor chunked — it is the cheap one.
5. **A multi-sprite character sorts as one** through a `SortingGroup` on its root, or its hat
   sorts independently of its body.

## Traps

- **A box collider around the sprite** makes a 1-tile aisle impassable and catches on every
  corner. A circle at the feet, radius about a third of a tile, slides round corners on its own.
- **Normalising the input vector** makes an analogue stick digital: any deflection is full speed.
  Clamp the magnitude.
- **Facing derived from velocity** flickers when the body is pushed or slides along a wall.
  Derive it from input, and keep the last value when input is zero.
- **Twin-stick aim from the mouse in screen space.** Convert the pointer to world with
  `Camera.ScreenToWorldPoint` and subtract the player position; a camera that leads the aim moves
  the pointer's world position every frame, so smooth the camera, not the aim —
  `unity-input` → `reference/pointer-and-aim.md`.
- **Fast projectiles tunnel through thin walls.** A 14 units/s projectile moves 0.28 units per
  step. Give it a dynamic body (Gravity Scale 0) with Collision Detection set to Continuous, or
  move it by `Physics2D.Raycast` from the previous position to the next and stop at the hit.
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
| Follow, confiner per room, group framing of player and aim | `unity-camera` → `reference/follow-2d.md` |
| Pixel-perfect follow | `unity-camera` → `reference/pixel-perfect-follow.md` |
| Four- and eight-direction blend trees | `unity-animation` → `reference/blend-trees.md` |
| A sprite state graph per direction | `unity-animation` → `reference/sprite-state-graph.md` |
| Slicing directional sheets, feet pivots | `unity-2d-sprites` |
| Floor and shelving palettes, rule tiles | `unity-tilemap` |
| Journeys; the 2D never-inside invariant | `unity-play-harness` → `reference/journeys.md` |
| The motor, cell stepping, draw order | this file |
| Sentry: patrol, see, chase | this file, "Traps" for the sight test; the state machine is three states — Patrol (waypoints), Alert (hold and face for the reaction time), Chase (steer at the last seen position) — with the state exposed to the probe through `GameProbe.Register` |
| Pickups | a trigger on its own layer; the pickup reports once and returns to `PickupPool` |
| Dialogue boxes, inventory screens, HUD | `unity-game-ui` |
| Text in more than one language | `unity-localization` |
