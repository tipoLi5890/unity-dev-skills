# 2D on a fixed screen — scrolling shooter, point-and-click adventure, single-screen casual

> Part of the `unity-gameplay` skill. Three types where the camera does not follow anything, so
> the screen itself is the level unit. Worked settings: the **depot** from above with a sentry
> firing patterns; the depot office where a switch opens the gate; and the **launch** — drag,
> release, land the pickup on the gate.

## The constraints

| Constraint | Scrolling shooter | Point-and-click adventure | Single-screen casual |
|---|---|---|---|
| View · projection | Top-down or side · orthographic | A painted room, seen from wherever it was painted · orthographic | Flat · orthographic, usually portrait |
| Movement model | Free inside the playfield, no inertia | A click names a destination or a hotspot; there may be no avatar at all | One gesture: tap, drag-and-release or swipe |
| Transform owner | Direct: position += input × speed, clamped | A path follower walking to the stand point | A dynamic body after release, or the cell map |
| Camera | Fixed. The background scrolls; the playfield does not | Fixed per room; a wide room scrolls on X only | Fixed, sized from the playfield width |
| Level unit | A timeline of spawn events | A room: one background, its hotspots, its exits | One screen and a rule set |
| Level is | Waves keyed to a tick count | A graph of rooms plus a table of state flags | Generated or a list of small layouts |

Underneath all three: **the playfield is a fixed rectangle in world units, and the screen is
fitted to it — never the other way round.** A playfield that grows with the window gives a wide
monitor more warning of a bullet and a tall phone a different puzzle.

## Fit the screen to the playfield

```csharp
// PlayfieldFit.cs — drop on the camera. Keeps a fixed world rectangle fully visible on any
// aspect: bars appear on the long axis, the playfield is never cropped or stretched.
using UnityEngine;

[RequireComponent(typeof(Camera))]
public class PlayfieldFit : MonoBehaviour
{
    public Vector2 playfield = new Vector2(9f, 16f);     // world units, the designed rectangle

    void LateUpdate()
    {
        var cam = GetComponent<Camera>();
        float fitHeight = playfield.y * 0.5f;
        float fitWidth = playfield.x * 0.5f / cam.aspect;   // size needed to show the full width
        cam.orthographicSize = Mathf.Max(fitHeight, fitWidth);
    }
}
```

Outside the playfield goes art or HUD, never gameplay: clamp the player, cull the bullets and
place the hotspots against `playfield`, not against the camera's view. On a phone, inset the HUD
by `Screen.safeArea`; the playfield itself may run under a notch only if nothing interactive
sits there.

---

## Scrolling shooter

### Numbers to decide first

| Number | Depot start | Decides |
|---|---|---|
| Playfield | 9 × 16 units, portrait, pillarboxed on a wide screen | Everything; fixed for the life of the game |
| Player speed · focus speed | 7 units/s · 3 units/s, no acceleration | Whether a dense pattern can be threaded |
| Player hit radius | 0.1 units, on a 1-unit sprite | Fairness: the hit shape is far smaller than the picture |
| Bullet speed range | 2 to 8 units/s | Reaction window: the slowest crosses the field in 8 s, the fastest in 2 s |
| Bullet budget | 300 live at once | The data structure, and the frame budget |
| Tick | The fixed step, 0.02 s; every pattern is counted in ticks | Repeatability: the same run produces the same bullets |

### Build order for the 3C prototype

1. **Playfield and fit**, with four gizmo lines on its edges.
2. **Controls**: a `move` vector and `fireHeld`, `focusHeld` — `unity-input`.
3. **Character**: in `FixedUpdate`, `position += move × speed × dt`, then clamp to the playfield
   inset by half the sprite. No `Rigidbody2D` is needed to move; when the ship needs walls, the
   free motor's screen clamp — `unity-2d-controller` → `reference/topdown-free.md` §7. Register
   with `GameProbe.SetPlayerVelocity(() => transform, () => _velocity);`.
4. **Bullets** as data, below. Register `GameProbe.Count("bullets", () => _live);` and
   `GameProbe.Count("hits", () => _hits);`.
5. **Journey**: a scripted driver holds still under one aimed pattern, then repeats while
   strafing. Assert `hits` is 1 in the first run and 0 in the second, `bullets` never exceeds the
   budget, and `pos` never leaves the playfield. Run it twice and compare the timelines — they
   must match sample for sample.
6. **Camera**: nothing follows. Shake on a hit — `unity-camera` → `reference/shake-and-blends.md`,
   fired from the hit's feedback row — `unity-game-feel` → `reference/feedback-stack.md`.

### Bullets, in essentials

```csharp
// One array of structs, moved and tested in a single loop on the fixed step. No GameObject,
// collider or Rigidbody2D per bullet: the whole budget is one pass over 300 structs.
struct Bullet { public Vector2 pos, vel; public float radius; }

Bullet[] _bullets = new Bullet[300];
int _live, _hits;

void FixedUpdate()
{
    float dt = Time.fixedDeltaTime;
    Vector2 player = _runner.position;
    for (int i = _live - 1; i >= 0; i--)
    {
        ref Bullet b = ref _bullets[i];
        b.pos += b.vel * dt;
        float reach = b.radius + _playerHitRadius;
        if ((b.pos - player).sqrMagnitude <= reach * reach) { _hits++; Remove(i); continue; }
        if (!_cullRect.Contains(b.pos)) Remove(i);       // playfield grown by 1 unit
    }
}

void Remove(int i) => _bullets[i] = _bullets[--_live];   // swap with the last: order is free
```

Draw them from a pool of `SpriteRenderer` objects sized to the budget and positioned in
`LateUpdate`, or with one `Graphics.RenderMeshInstanced` call per bullet sprite. Enemies and
pickups are few: ordinary kinematic bodies with trigger colliders are fine for those. The
pattern that fills the array is four numbers — `unity-combat` → `reference/projectiles.md` §7;
the hit still ends in one damage event — `unity-combat` → `reference/damage-contract.md`; the
waves that bring the sentries are data on a seed — `unity-game-ai` →
`reference/spawners-and-waves.md`.

### Traps

- **Patterns timed with `Time.time` or `WaitForSeconds`** drift with frame rate, so no two runs
  match and no journey can assert on them. Count fixed ticks.
- **`Random.value` unseeded.** Give the stage its own `System.Random` with a seed stored in the
  stage data.
- **Bullets moved in `Update`** tunnel through the player on a slow frame. Fixed step.
- **A hit shape the size of the sprite.** The player reads the sprite and plays the hit shape;
  show the hit shape while focus is held.
- **Bullets sorted under enemies or effects.** Hostile bullets are the top sorting layer, above
  explosions, always — `unity-2d-rendering` → `reference/sort-order.md`.
- **Scrolling the world** moves every spawn point and breaks the playfield clamp. Scroll the
  background only: two tiled sprites leapfrogging, or a material offset. Layers at different
  speeds and their sorting layers — `unity-2d-rendering` → `reference/parallax.md`.

---

## Point-and-click adventure

### Numbers to decide first

| Number | Depot-office start | Decides |
|---|---|---|
| Room size | One screen; a wide room is two screens and scrolls on X | Background art size: at 1080p, 1920 × 1080 px per screen |
| Smallest hotspot | 9 mm on the target device — about 1.1 units when a 16-unit-wide room fills a 6-inch phone | Whether a thumb can hit it; pixel hunting starts below this |
| Walk speed · depth scale | 3 units/s at the front; scale 1.0 at the front edge, 0.6 at the back | How long crossing a room takes: under 3 s |
| Stand point per hotspot | One, authored | Where the character walks before acting |
| Flags | Named booleans and small ints in one table | Every puzzle; the save file is this table |

### Build order for the 3C prototype

1. **One room**: a background sprite, a `PolygonCollider2D` marking the walkable area, three
   hotspots (`BoxCollider2D`, trigger, on a `Hotspot` layer) each with a child stand point.
2. **Controls**: `pointerPosition` and `pointerPressed` — `unity-input` →
   `reference/pointer-and-aim.md`.
3. **Picking**, below. Register `GameProbe.Register("hover", () => _hover ? _hover.name : null);`
   and one probe key per flag the first puzzle uses.
4. **Walking**: walk to the stand point, then act — `unity-interaction` →
   `reference/point-and-click.md` §4. A straight line clamped inside the walkable area with
   `Collider2D.ClosestPoint` serves an open room; round an obstacle, the three 2D routes and
   how to choose — `unity-game-ai` → `reference/pathfinding-2d.md`.
5. **Journey**: scripted pointer presses on switch, then gate. Assert the flag order
   (`switchOn` before `gateOpen`), that a press on the gate *before* the switch changes nothing,
   and that a press over a UI panel reaches no hotspot.

### Picking — which file

A point overlap on the hotspot layer, the front-most by sorting layer value and then order in
layer, and nothing at all when the press began over UI — `unity-interaction` →
`reference/point-and-click.md` §3. A press is an *intent*: store the target, walk, and act on
arrival only if the intent is still the current one; a second press replaces it, which is what
cancels a walk — the same file, §5.

### Traps

- **Clicks passing through UI** open the door behind the inventory. The `EventSystem` check
  comes first, and from `Update`: called inside an Input System action callback it answers for
  the previous frame — `unity-input` → `reference/pointer-and-aim.md`.
- **Hover as the only affordance.** There is no hover on a touch screen. Provide a
  hold-to-reveal that outlines every hotspot — `unity-interaction` →
  `reference/point-and-click.md` §6.
- **State stored on scene objects** is lost when the room unloads. Hotspots read and write the
  flag table; on load, each one sets its own appearance from the flags. The table is the save —
  `unity-scene-flow` → `reference/save-format.md`.
- **Acting on press instead of on arrival** lets the player use a switch from across the room —
  `unity-interaction` → `reference/point-and-click.md` §4.
- **Depth without sorting.** A character scaled by Y must also sort by Y against props — pivot
  at the feet and a sort axis, `unity-2d-rendering` → `reference/y-sort.md`.
- **A puzzle that can be put into an unwinnable state.** Enumerate the flag table: a breadth-
  first search over flag states from the start must reach the end from every reachable state.

---

## Single-screen casual

### Numbers to decide first

| Number | Launch start | Decides |
|---|---|---|
| Playfield · aspect range | 9 × 16 units; supported from 9:16 to 9:21 | Bars or extra art above and below, never a different field |
| Time to first input | Under 3 s from app start | What may load before the first screen |
| Session length | 30 to 90 s | How fast difficulty ramps |
| Touch target | 9 mm minimum; the gesture area is the whole lower half | Reachability with one thumb |
| Launch: drag to speed | speed = drag length × 4, drag clamped to 3 units → 12 units/s at most | The reach of a full pull; put the gate inside it |
| Gravity for the launched body | 20 units/s² (gravity scale 2.04) | Arc height: a 12 units/s launch at 60° peaks 2.7 units up |

### Build order for the 3C prototype

1. **Playfield and fit**; a launch point, a gate, one wall.
2. **Controls**: `pointerPressed`, `pointerPosition`, `pointerReleased` — `unity-input` →
   `reference/touch-and-on-screen.md`.
3. **The gesture**: on press, remember the start; while held, `pull = Vector2.ClampMagnitude(
   start − current, 3)`; on release, set `body.linearVelocity = pull × 4`. Set velocity rather
   than adding force, so the result does not depend on mass.
4. **The preview**: draw dots at `p0 + v·t + ½·g·t²` for t = 0.1, 0.2 … using
   `Physics2D.gravity × body.gravityScale` for `g`. Register
   `GameProbe.Register("pull", () => _pull.magnitude);`.
5. **Journey**: scripted press, drag and release at three pull lengths. Assert the landing x
   against the preview's prediction within 0.2 units, and that the state reaches `AtGate` only
   for the pull that should.
6. **On a device.** Touch latency and thumb reach are not visible in the Editor —
   `unity-device-testing`.

### Traps

- **A preview that uses a different gravity from the body** promises an arc the pickup does not
  fly. One source for `g`; the journey in step 5 is the check.
- **Drag measured in pixels.** The same swipe is twice the pull on a denser screen. Convert to
  world units or to a fraction of the screen's shorter side first.
- **A dynamic body waiting at the launch point** sags or rolls before release, so the launch
  starts from somewhere the preview did not. Keep it Kinematic until release, then set
  `bodyType` to Dynamic and the velocity in the same step — `unity-physics-2d` →
  `reference/bodies-and-simulation.md`.
- **Gameplay under the notch or the home indicator.** Read `Screen.safeArea`.
- **Difficulty from `Time.time`** carries over a restart. Count from the session start.

---

## Where each need is answered

| Need | Answer |
|---|---|
| Move, fire and pointer actions; a scripted driver | `unity-input` → `reference/reading-input.md` |
| Pointer position, press and release; aim | `unity-input` → `reference/pointer-and-aim.md` |
| Touch gestures, on-screen controls | `unity-input` → `reference/touch-and-on-screen.md` |
| The ship as a free motor with walls; the screen clamp | `unity-2d-controller` → `reference/topdown-free.md` |
| Screen shake and impulses | `unity-camera` → `reference/shake-and-blends.md` |
| A wide room that scrolls on X inside bounds | `unity-camera` → `reference/follow-2d.md` |
| Background layers at different speeds, one sorting layer each | `unity-2d-rendering` → `reference/parallax.md` |
| Bullets over effects, a character against props | `unity-2d-rendering` → `reference/sort-order.md`, then `unity-2d-rendering` → `reference/y-sort.md` |
| Body types, a launched body, gravity scale | `unity-physics-2d` → `reference/bodies-and-simulation.md` |
| Point and overlap queries; a hotspot the query misses | `unity-physics-2d` → `reference/queries-2d.md` |
| Small layouts as data; generated layouts | `unity-2d-level` → `reference/level-data.md`, then `unity-2d-level` → `reference/procedural.md` |
| A casual game played on a board of cells | `reference/genre-2d-grid.md` |
| Character and prop state graphs | `unity-animation` → `reference/sprite-state-graph.md` |
| A painted character rigged with bones | `unity-2d-animation` → `reference/psd-to-rig.md` |
| Sprite import, slicing, pivots | `unity-2d-sprites` |
| Many sprites, few draw calls | `unity-sprite-atlas` |
| Pixel art on a fixed screen | `unity-2d-pixel-perfect` |
| HUD outside the playfield; inventory; verb bar | `unity-game-ui` → `reference/hud-placement.md` |
| Dialogue in more than one language | `unity-localization` |
| Hotspots, picking under the pointer, walk there then act, cursor verbs | `unity-interaction` → `reference/point-and-click.md` |
| A switch that opens the gate; the flag it sets | `unity-interaction` → `reference/doors-and-switches.md` |
| Pickups shot loose or landed on | `unity-interaction` → `reference/pickups.md` |
| Bullet patterns as data; pooled shots | `unity-combat` → `reference/projectiles.md` |
| The ship's hit, lives and invincibility after a hit | `unity-combat` → `reference/damage-contract.md`, then `unity-combat` → `reference/iframes-and-knockback.md` |
| Waves keyed to ticks, from a seed | `unity-game-ai` → `reference/spawners-and-waves.md` |
| A sentry that turns and fires on a state machine | `unity-game-ai` → `reference/state-machine.md` |
| Walking round an obstacle in a painted room | `unity-game-ai` → `reference/pathfinding-2d.md` |
| The flag table as the save; versions and migration | `unity-scene-flow` → `reference/save-format.md` |
| Rooms as scenes; the Boot scene; pause | `unity-scene-flow` → `reference/additive-scenes.md`, `unity-scene-flow` → `reference/bootstrap.md`, `unity-scene-flow` → `reference/game-state-and-pause.md` |
| Enemies, pickups and effects from a pool | `unity-scene-flow` → `reference/pooling.md` |
| A hit: hit stop, flash, sparks, sound, within one budget | `unity-game-feel` → `reference/feedback-stack.md`, then `unity-game-feel` → `reference/hit-stop-and-time.md` |
| The launch: squash on release, a streak in flight | `unity-game-feel` → `reference/flash-and-squash.md`, then `unity-game-feel` → `reference/trails.md` |
| Vibration on a phone | `unity-game-feel` → `reference/haptics.md` |
| Journeys; comparing two runs sample for sample | `unity-play-harness` → `reference/timeline-format.md` |
| Thumb reach and touch on a real phone | `unity-device-testing` |
| Playfield fit, bullets as one array of structs, the launch gesture | this file |
