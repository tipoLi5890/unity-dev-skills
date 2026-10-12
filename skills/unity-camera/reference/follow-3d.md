# 3D rigs — orbit, shoulder, lock-on, first person, fixed

> Part of the `unity-camera` skill. `SKILL.md` §4 picks the rig; this file holds the component
> lists and numbers for each perspective rig, the deocclusion choices, and how look input reaches
> an axis. Names are Cinemachine 3.x — `reference/version-and-names.md` translates.
> `resources/Editor/CameraRigBuilder.cs` builds the orbit rig and the fixed rig in one command.

## Track a pivot, not the runner's feet

Every rig below tracks a Transform. The runner's root is at ground level; a camera aimed there
frames the floor. Either give the components a `TargetOffset` of `(0, 1.5, 0)`, or add an empty
child at chest height and track that. A child is the better choice when the rig must rotate with
something the game controls: the shoulder rig and first person both read the pivot's rotation.

The pivot inherits the runner's clock. A runner on a `Rigidbody` needs interpolation on before
any of these rigs is tuned — `reference/update-order-and-jitter.md`.

## Third-person orbit

```
CM Third Person   CinemachineCamera               Target.TrackingTarget = the runner (or its pivot)
                  CinemachineOrbitalFollow        Position Control: where on the orbit
                  CinemachineRotationComposer     Rotation Control: keep the runner framed
                  CinemachineInputAxisController  feeds the orbit's axes
                  CinemachineDeoccluder           keeps the runner visible
```

| `CinemachineOrbitalFollow` | Value |
|---|---|
| `OrbitStyle` | `Sphere` with `Radius` 5 for a single distance; `ThreeRing` with `Orbits.Top` / `.Center` / `.Bottom` (each a `Radius` and a `Height`) when looking down should pull the camera in |
| `TargetOffset` | `(0, 1.5, 0)` when tracking the root |
| `HorizontalAxis` | Range −180 to 180, wraps |
| `VerticalAxis` | Range −10 to 45, rests at 17.5. Widen to −30 for a game with ledges below |
| `RadialAxis` | Range 1 to 1: zoom is off until the range is widened |
| `TrackerSettings.BindingMode` | `WorldSpace` (default): the orbit does not turn when the runner turns. `LazyFollow` measures the offset in camera-local axes, so the camera trails the runner without swinging round behind it |
| `TrackerSettings.PositionDamping` | `(1, 1, 1)` by default; `(0.2, 0.4, 0.2)` for an action game |

`CinemachineRotationComposer`: `TargetOffset` equal to the orbit's, `Damping = (0.5, 0.5)`,
composition centred. Give it a dead zone of `(0.1, 0.1)` when small steps should not turn the
camera.

**Recentering** is per axis: `HorizontalAxis.Recentering.Enabled`, `.Wait` (1 s after the last
input) and `.Time` (2 s to return). `RecenteringTarget` picks what "behind" means: `AxisCenter`,
`ParentObject`, `TrackingTarget` (behind the runner's facing) or `LookAtTarget`.

**Reset() does not run for components added from code at run time.** The inspector shows radius
5 and obstacle avoidance on because Reset set them; the same `AddComponent` in play mode leaves
radius at 10 and `AvoidObstacles.Enabled` false. Assign every field in a builder — the shipped
one does.

## Over the shoulder

For aiming games. `CinemachineThirdPersonFollow` as Position Control and **no Rotation Control**:
the camera takes its rotation from the tracking target.

| Field | Default set by Reset | Meaning |
|---|---|---|
| `ShoulderOffset` | `(0.5, -0.4, 0)` | Shoulder pivot, in the target's local space |
| `VerticalArmLength` | 0.4 | Hand above the shoulder; changes framing as the pitch changes |
| `CameraSide` | 1 | 1 right shoulder, 0 left, 0.5 centred. Animate it to swap shoulders |
| `CameraDistance` | 2 | Behind the hand |
| `Damping` | `(0.1, 0.5, 0.3)` | Camera-local, seconds |
| `AvoidObstacles` | Its own built-in collision: `Enabled`, `CollisionFilter`, `IgnoreTag`, `CameraRadius`, `DampingIntoCollision`, `DampingFromCollision` |

This component reads no input. The game turns the pivot: yaw on the runner, pitch on a child
pivot clamped to ±70°, both from the look action, and the camera follows. That keeps aim and
camera identical by construction. Add `CinemachineThirdPersonAim` (`AimCollisionFilter`,
`IgnoreTag`, `AimDistance`) to read `AimTarget`: the world point a shot from the runner would
hit, which differs from the screen centre because the camera is off to one side.

Do not add a `CinemachineDeoccluder` to this rig; it has its own obstacle handling and two
resolvers fight.

## Deocclusion: which of the two

| | `CinemachineDeoccluder` | `CinemachineDecollider` |
|---|---|---|
| Promise | The target stays **visible** | The camera stays **outside geometry** |
| When a pillar passes between camera and runner | Moves the camera to see past it | Does nothing: the camera is not inside anything |
| Use for | Orbit rigs in built-up levels | Open terrain, fixed-angle cameras, anything where a moment behind a pillar is fine |

Deoccluder settings that matter:

| Field | Value |
|---|---|
| `CollideAgainst` | The level geometry layers only. Not the runner, not triggers' layer, not pickups |
| `IgnoreTag` | The runner's tag. The runner's own collider is the nearest thing to the runner |
| `TransparentLayers` | Layers the camera may look through: foliage, glass, the sentry |
| `MinimumDistanceFromTarget` | 0.3; obstacles closer than this to the pivot are ignored |
| `AvoidObstacles.CameraRadius` | 0.2. Larger than the near clip plane's half-diagonal, or walls clip |
| `AvoidObstacles.Strategy` | `PullCameraForward` for corridors; `PreserveCameraHeight` outdoors; `PreserveCameraDistance` for the least zoom change and the most sliding |
| `AvoidObstacles.MinimumOcclusionTime` | 0.1 to 0.2 s. Zero makes the camera jump for a lamp post passing through frame |
| `AvoidObstacles.SmoothingTime` | 0.2. Holds the nearest distance for this long, so a row of pillars is one pull-in and not five |
| `AvoidObstacles.Damping` / `.DampingWhenOccluded` | 0.4 returning, 0.2 pulling in: in fast, out slow |

A camera that pumps in and out along a wall has `SmoothingTime` at 0 or `CameraRadius` smaller
than the gap it is trying to fit through. A camera that clips through a wall for one frame has a
target on the physics clock and the deoccluder resolving against last step's position.

## Lock-on is a second target

The runner stays the tracking target; the sentry becomes the look-at target.

```csharp
// Engage. Setting LookAt also switches Target.CustomLookAtTarget on.
vcam.LookAt = sentry;
// Release: back to one target for both jobs.
vcam.Target.CustomLookAtTarget = false;
```

That alone turns the camera to the sentry while the orbit stays where the stick left it, and the
runner can end up between camera and sentry or out of frame. Two additions make it a rig:

- **Swing the orbit behind the runner, facing the sentry.** `orbit.RecenteringTarget =
  LookAtTarget`, with `HorizontalAxis.Recentering` enabled, `Wait` 0 and `Time` 0.3 while locked.
- **Frame both.** Look at a `CinemachineTargetGroup` holding the runner (weight 1) and the sentry
  (weight 1) rather than at the sentry itself. The composer then keeps the midpoint on screen,
  and the runner cannot leave the frame by circling.

Build the locked rig as a **second `CinemachineCamera`** with those settings and a higher
priority, enabled on lock and disabled on release. The Brain blends in and out, the free rig
keeps its own tuning, and a lost target is one line: disable the lock camera.

## First person

```
Runner (yaw from look input)
└─ Head              empty, at eye height (1.6)
CM First Person      CinemachineCamera               Target.TrackingTarget = Head
                     CinemachineHardLockToTarget     Position Control, Damping 0
                     CinemachinePanTilt              Rotation Control
                     CinemachineInputAxisController  feeds Pan and Tilt
```

| `CinemachinePanTilt` | Value |
|---|---|
| `PanAxis` | −180 to 180, wraps |
| `TiltAxis` | −70 to 70. Never ±90: straight up loses the heading |
| `ReferenceFrame` | `ParentObject` with the Cinemachine camera at the scene root, which makes the angles world angles |

The camera owns the look angles and the body copies the yaw, never the other way round:

```csharp
void Update() { runner.rotation = Quaternion.Euler(0f, panTilt.PanAxis.Value, 0f); }
```

`ReferenceFrame = TrackingTarget` together with that line is a feedback loop: the camera turns
relative to a body that turns to match the camera, and the view spins.

- **No damping on position or rotation.** A first-person view that lags the head reads as input
  lag.
- **Near clip plane 0.05 to 0.1** on the lens, and the capsule radius at least three times that,
  or the camera sees through walls it is pressed against.
- **The runner's own mesh** goes on a layer the output camera does not render, or only arms are
  shown.
- **A head on a `Rigidbody` body shivers** unless the body is interpolated. This is the rig where
  two clocks are most visible, because every pixel on screen moves with the error.
- **Field of view** is `Lens.FieldOfView`, vertical degrees. 60 vertical is about 90 horizontal at
  16:9.

## Fixed rigs and switching by priority

A fixed camera is a `CinemachineCamera` with no Position Control. It stays where its Transform
is. Add a `CinemachineRotationComposer` and a tracking target to make it turn and follow from a
fixed post; leave both off for a locked shot.

The Brain shows the enabled camera with the highest `Priority`. Among equals, the most recently
enabled wins, and `vcam.Prioritize()` moves a camera to the front of its equals without changing
a number.

| Switch | How |
|---|---|
| Room or zone cameras (the gate room, a corridor) | A trigger volume per camera: priority 20 on enter, 10 on exit |
| A moment (the gate opens, the launch) | Enable a camera with a higher priority; disable it when the moment ends |
| By animation state | `CinemachineStateDrivenCamera`: a manager with child cameras mapped to Animator states |
| The best unobstructed view of several posts | `CinemachineClearShot` with a deoccluder on each child |

Three rules keep fixed-camera games playable:

- **Movement stays relative to the camera that was live when the stick was pushed.** Re-read the
  camera's forward only when the stick returns to rest, or every cut reverses the runner.
- **Trigger volumes overlap by the runner's width and no more**, and the exit handler lowers the
  priority only if this camera is the one live — otherwise the doorway flickers between two
  shots.
- **Cuts between posts, blends within a room.** Set the pair in the Brain's `CustomBlends`
  asset; the default blend is 2 s ease in-out and is almost never what a cut wants.

The lane run's camera is the smallest fixed rig: one `CinemachineCamera`, no controls, the lens
copied from the scene. Its follow-on-rails variant is in `reference/follow-2d.md`.

## Look input through the Input System

`CinemachineInputAxisController` sits on the camera object, discovers every input axis its
siblings expose, and holds one controller per axis:

| Axis name | Exposed by |
|---|---|
| `Look Orbit X`, `Look Orbit Y`, `Orbit Scale` | `CinemachineOrbitalFollow` |
| `Look X (Pan)`, `Look Y (Tilt)` | `CinemachinePanTilt` |

Each controller has `Enabled`, `Input.InputAction` (an `InputActionReference`), `Input.Gain`,
`Input.CancelDeltaTime` and a `Driver` with `AccelTime` and `DecelTime` (0.2 s each).

- **Assign the project's own Look action.** Added in the Editor, the controller points at the
  package's `CM Default/Look`; that asset is a placeholder, and rebinding and device switching
  apply only to the project's actions — `unity-input` → `reference/action-asset.md`.
- **The reader takes `float` and `Vector2` actions only.** For a `Vector2` it takes x for an X
  axis and y for a Y axis, so one Look action feeds both.
- **Invert with a negative `Gain`.** The Editor default already inverts Y.
- **Mouse delta is per frame; a stick is a rate.** Enable `CancelDeltaTime` for a pure
  mouse-delta action, or normalise the two in the action's processors so one gain serves both.
- **`AutoEnableInputs` enables the action for you.** With a `PlayerInput` component managing
  maps, turn it off and let the map switch own it, or the look action stays live in menus.
- **`PlayerIndex`** stays −1 for one player; for split screen it selects that player's copy of
  the actions.
- **`SuppressInputWhileBlending`** is on by default: the stick is ignored during a blend.
- **Paused**: `IgnoreTimeScale` on the controller, and on the Brain —
  `reference/update-order-and-jitter.md`.

When gameplay already reads one input struct per frame, skip the controller and write the axis:

```csharp
orbit.HorizontalAxis.Value += look.x * yawSpeed * Time.deltaTime;
orbit.VerticalAxis.Value = orbit.VerticalAxis.ClampValue(orbit.VerticalAxis.Value - look.y * pitchSpeed * Time.deltaTime);
```

A scripted journey then drives the camera through the same struct it drives the runner with, and
a camera test needs no device.

## Related skills

Actions, control schemes, pointer and stick aim: `unity-input`. Layers and why a cast misses the
wall: `unity-physics-3d`. Animator states that pick a camera: `unity-animation`. Recording a rig's
behaviour as a journey: `unity-play-harness`.
