# 2D follow — composer, confiner, rooms, runner, top-down, isometric

> Part of the `unity-camera` skill. `SKILL.md` §2 picks the rig; this file holds the numbers for
> every orthographic follow: where the runner sits in the frame, how the camera stays inside a
> room, how it changes room, and what orthographic size means as a zoom. Names are Cinemachine
> 3.x — `reference/version-and-names.md` translates. `resources/Editor/CameraRigBuilder.cs`
> builds the first rig in one command.

## The rig

```
Main Camera            Camera (orthographic) + CinemachineBrain        at the scene root
CM Follow 2D           CinemachineCamera            Target.TrackingTarget = the runner
                       CinemachinePositionComposer  where the runner sits on screen
                       CinemachineConfiner2D        the room
```

The camera object keeps rotation identity and carries no Rotation Control: a position composer
moves the camera and never turns it. Its z is set by `CameraDistance` (10), which on an
orthographic camera changes clipping and nothing visible.

**A new `CinemachineCamera` carries its own lens — orthographic size 10, field of view 40 — and
writes it to the `Camera` when it goes live.** A scene framed at size 5 doubles its view the
moment the rig is added. Set `Lens.OrthographicSize` on the Cinemachine camera; the value on the
`Camera` component is overwritten every frame and is no longer the setting.

## Composition: dead zone, hard limits, damping

`CinemachinePositionComposer.Composition`, all in fractions of the screen:

| Field | Meaning | Side run default |
|---|---|---|
| `ScreenPosition` | Where the target rests. `(0, 0)` is the centre, `±0.5` the edges | `(-0.15, -0.1)`: left of centre and low, so the view is ahead and above |
| `DeadZone.Size` | The target moves this far before the camera reacts. Full screen is 1 | `(0.10, 0.15)` |
| `HardLimits.Size` | The target is never allowed outside this region, damping or not | `(0.6, 0.7)` |
| `Damping` | Seconds to catch up, per axis `(x, y, z)` | `(0.5, 0.3, 0)` |

Both `DeadZone` and `HardLimits` have an `Enabled` flag and are **off** by default; a size with
the flag off does nothing.

Convert to world units before tuning, because a fraction means a different distance at every
zoom: at orthographic size 5 the view is 10 units high and `10 × aspect` wide, so a dead zone of
0.10 × 0.15 is 1.78 × 1.5 units at 16:9.

- **Dead zone height at least the jump apex.** A camera that follows every hop makes the ground
  move; a dead zone taller than a standing jump keeps the horizon still and only follows a real
  change of height. With a jump of 1.2 units at size 5, `DeadZone.Size.y` is 0.15 or more.
- **Dead zone width near zero for a runner, 0.1 for a platformer.** A runner never stops, so a
  wide dead zone is only lag. A platformer turns round constantly, and the dead zone is what
  stops the camera swinging on every turn.
- **Hard limits on, always.** They are the guarantee behind "the player never leaves the
  viewport": damping is a preference, the hard limit is a rule.
- **Vertical damping shorter than horizontal.** A fall the camera cannot keep up with shows
  the player the top of the screen and nothing below.

## Look-ahead

`Lookahead.Enabled`, `.Time` (0 to 1 s, how far into the future to aim), `.Smoothing` (0 to 30),
`.IgnoreY`.

| Game | `Time` | `Smoothing` | `IgnoreY` |
|---|---|---|---|
| Side run, platformer | 0.25 | 8 | on — a jump is not a change of direction |
| Top-down, twin-stick | 0.15 | 10 | off |
| Auto-runner at constant speed | off | — | — a fixed `ScreenPosition` offset is the same thing without the noise |

Look-ahead differentiates the target's motion, so it amplifies whatever is wrong with it. Turn it
on only after `scripts/camera_jitter.py` reads the plain follow as smooth; a camera that begins
to shake when look-ahead is enabled has a target on the wrong clock —
`reference/update-order-and-jitter.md`.

## The room: `CinemachineConfiner2D`

The bounding shape is a `BoxCollider2D`, a `PolygonCollider2D` or a `CompositeCollider2D`. **Any
other collider type confines nothing and reports nothing.** Put the shape on its own object, on a
layer that collides with nothing, or tick Is Trigger; it describes where the *view* may be, so it
is the room's outline, not the walkable floor. Outlines kept as level data, one per room:
`unity-2d-level` → `reference/rooms-and-chunks.md`.

| Field | Use |
|---|---|
| `BoundingShape2D` | The shape |
| `Damping` | 0 to 5. Softens the camera coming round a concave corner. 0.5 for L-shaped rooms, 0 for boxes |
| `SlowingDistance` | The camera eases to a stop this many units before the edge. 0 stops dead; 1 to 2 feels deliberate |
| `OversizeWindow` | For a room smaller than the view on some axis. Enable it only then, and set `MaxWindowSize` to the largest orthographic size the game uses |

The confiner bakes a smaller polygon from the shape, the lens and the aspect ratio, and keeps it.
What it notices by itself and what it does not:

| Change | Handled |
|---|---|
| A different collider assigned to `BoundingShape2D` | Automatically, on the next update |
| The screen's aspect ratio changes | Automatically |
| The shape is moved, or scaled uniformly | The cache stays valid |
| The shape's points are edited, or it is rotated or scaled unevenly | **Call `InvalidateBoundingShapeCache()`** |
| The orthographic size or field of view changes (any zoom) | **Call `InvalidateLensCache()`** |

A zoom without `InvalidateLensCache()` keeps confining for the old size: zoom out and the view
shows past the wall; zoom in and the camera stops short of it.

Baking is spread over frames and gives up after five seconds of work on a shape too complex to
bake. **Until `BoundingShapeIsBaked` is true the confiner has no effect.** For the first frame
of a level, call `confiner.BakeBoundingShape(vcam, 1f)` during loading, or make
`BoundingShapeIsBaked` a readiness member (`unity-play-harness` → `reference/situations.md`). A
box bakes at once; a composite outline of a whole level may not.

The confiner assumes the camera looks straight at the shape. A tilted camera is still confined,
but not at the polygon's edges.

## Room to room

Two ways, and the first is the default:

**One camera per room.** Each room owns a `CinemachineCamera` with its own composer and its own
confiner on that room's shape, all tracking the runner. The room's trigger raises its camera's
priority on entry and lowers it on exit; the Brain blends.

```csharp
void OnTriggerEnter2D(Collider2D other) { if (other.CompareTag("Player")) roomCamera.Priority = 20; }
void OnTriggerExit2D(Collider2D other)  { if (other.CompareTag("Player")) roomCamera.Priority = 10; }
```

Every confiner is baked once and never invalidated, the transition is an ordinary blend with a
duration and a curve, and each room can have its own zoom. Set `BlendHint` to include
`InheritPosition` on the room cameras so the incoming one starts where the outgoing one was. A
blend of 0.4 s reads as a slide; `Cut` reads as a screen flip. `StandbyUpdate = Never` on the
room cameras keeps a level of forty rooms from updating forty composers.

**One camera, swapped shape.** `resources/RoomConfinerSwitch.cs` on each room's trigger assigns
that room's shape to a single shared confiner. Right for a handful of rooms that share one zoom.
Its `cut` flag sets `PreviousStateIsValid = false` so the camera appears in the new room; without
it the camera slides there on its damping, straight through the wall between.

Both need the room triggers **not to overlap**: inset each half a unit from the doorway. With
overlapping triggers the runner can stand in two rooms, turn back, and never re-enter the first.

## Runner: fixed offset and look-ahead

An auto-runner moves at a near-constant speed in one direction, so prediction adds nothing: the
look-ahead is a fixed offset.

**Side run.** Position composer with `ScreenPosition = (-0.25, -0.1)`, horizontal dead zone off,
`Damping = (0, 0.3, 0)`. Zero horizontal damping locks the runner's column on screen, and
obstacles then arrive at a constant screen speed, which is what makes them readable. The vertical
dead zone still absorbs jumps.

**Lane run** (3D, camera behind and above). Do not track the runner. Track an anchor that copies
the runner's forward position and stays on the middle lane:

```csharp
// On an empty "CameraAnchor" object; the CinemachineCamera tracks this, not the runner.
void LateUpdate()
{
    Vector3 p = runner.position;
    transform.position = new Vector3(middleLaneX + (p.x - middleLaneX) * lateralFollow, 0f, p.z);
}
```

With three lanes 1.3 units apart, `lateralFollow = 0.35` moves the camera 0.45 units for a full
lane change: enough to feel the shift, not enough to swing the horizon. `y` is held at 0 so a
jump does not lift the camera. The camera itself is a `CinemachineFollow` with
`FollowOffset = (0, 4, -7)`, binding mode `WorldSpace`, position damping `(0.2, 0, 0)`, and no
Rotation Control: its rotation is set once on the Transform. The anchor moves in `LateUpdate`
only if the runner is on the render-frame clock; if the runner is a body, interpolate it first.

## Top-down

The same position composer, a symmetric frame: `ScreenPosition = (0, 0)`, dead zone
`(0.08, 0.08)`, `Damping = (0.3, 0.3, 0)`, look-ahead 0.15 with `IgnoreY` off.

- **2D top-down** (the depot, drawn on the XY plane): identical to the side rig; the confiner is
  the depot's outline.
- **3D top-down**: rotate the Cinemachine camera's Transform to `(90, 0, 0)`, or `(60, 0, 0)` for
  a tilted view, and leave Rotation Control empty. The composer keeps the runner at the screen
  position at `CameraDistance` along the view axis. `CinemachineConfiner2D` does not apply; use
  `CinemachineConfiner3D` with a box volume.
- **Aim ahead of the cursor**, for twin-stick aiming: track a `CinemachineTargetGroup` holding the
  runner at weight 1 and an aim point at weight 0.3. The view leans toward the aim without
  leaving the runner. Reading the aim point belongs to `unity-input` →
  `reference/pointer-and-aim.md`.

## Isometric

- **2D isometric tilemap** (the sorting yard on an isometric grid): a plain orthographic camera,
  no rotation, the standard 2D rig. The isometric look is in the art and the grid; draw order by
  custom axis belongs to `unity-tilemap`.
- **3D isometric**: orthographic `Camera`, the Cinemachine camera's Transform rotated to
  `(30, 45, 0)`, or `(35.264, 45, 0)` for true isometric where the three axes foreshorten
  equally. Position composer with `CameraDistance` 30 or more: on an orthographic camera the
  distance changes nothing on screen, but geometry between the camera and the near plane is cut
  away, and a tall sorting bay disappears from the top down when the distance is short.

Moves on a grid are snaps of one cell. Give the composer `Damping` of 0.15 to 0.25 on a cell
grid: enough to turn the snap into a glide, short enough that the cursor cell never leaves the
dead zone.

## Orthographic size is the zoom

`Lens.OrthographicSize` is half the height of the view in world units. Width follows the screen.

| To show | Size |
|---|---|
| H units of height | `H / 2` |
| W units of width on any screen | `W / (2 × aspect)` — recompute when the aspect changes |
| Three lanes of 1.3 units with one lane of margin each side, in portrait 9:16 | `(5 × 1.3) / (2 × 0.5625)` = 5.78 |

- **A fixed size is a fixed height.** A wider screen sees more to the sides; a taller phone sees
  less. Decide which dimension the design protects and compute the size from that one.
- **Zoom by writing the Cinemachine camera's lens**, then tell the confiner:

```csharp
vcam.Lens.OrthographicSize = Mathf.MoveTowards(vcam.Lens.OrthographicSize, targetSize, speed * Time.deltaTime);
confiner.InvalidateLensCache();
```

- **Two zoom levels are two cameras.** A wide camera for the launch and a tight one for the gate,
  switched by priority, blends size for free and needs no script.
- **Framing several things** (runner and sentry): a `CinemachineTargetGroup` as the tracking
  target plus the `CinemachineGroupFraming` extension, `SizeAdjustment = ZoomOnly`,
  `OrthoSizeRange` set to the smallest and largest size the art survives.
- **Pixel art restricts the sizes that are legal.** `reference/pixel-perfect-follow.md`.

## Check the rig

`resources/CameraProbe.cs` plus `templates/CameraJourneyTest.cs` assert the three things a 2D
follow must hold: the runner inside the viewport on every sample, every corner of the view inside
the room, and an offset that eases. Run the journey once with the confiner removed and confirm
it fails at the far wall; a bounds check that cannot fail is not checking the bounds.

## Related skills

Tile grids and palettes: `unity-tilemap`. Isometric sorting: `unity-2d-rendering` →
`reference/y-sort.md`. Parallax layers behind the follow: `unity-2d-rendering` →
`reference/parallax.md`. Room bounds as level data, one shape per room: `unity-2d-level` →
`reference/rooms-and-chunks.md`. The pixel-perfect camera component: `unity-2d-pixel-perfect`. Which rig a game's constraints imply: `unity-gameplay` →
`reference/perspective-fingerprint.md`.
