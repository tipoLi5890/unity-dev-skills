# Third person — the stick is relative to the camera

> Part of the `unity-3d-controller` skill. What `resources/ThirdPersonController.cs` does with
> the stick, the three ways the body can face, and where the controller stops and the camera
> begins. The camera rig itself — orbit, boom collision, lock-on framing — is
> `unity-camera` → `reference/follow-3d.md`.

## 1. Camera-relative movement

"Forward" on the stick means "away from the camera, along the ground". Three lines, and each
one is a bug when shortened:

```csharp
Vector3 forward = Vector3.ProjectOnPlane(view.forward, Vector3.up).normalized;   // the heading, flattened
Vector3 right   = Vector3.Cross(Vector3.up, forward);
Vector3 wish    = Vector3.ClampMagnitude(forward * move.y + right * move.x, 1f);
```

| Shortcut | What goes wrong |
|---|---|
| `view.forward` unflattened | A camera pitched 30° down turns stick-up into 0.87 along the ground and 0.5 into the floor: forward is slower than sideways, and slower the steeper the camera looks |
| `view.TransformDirection(move)` | The same, plus the runner tries to climb when the camera looks up |
| `.normalized` on `wish` | A half-pushed stick is a full run, and stick drift just outside the dead zone is a full run in whatever direction it points |
| Not clamping | A keyboard diagonal is 41% faster than a cardinal |
| Flattening a camera that looks straight down | The projection is zero; the controller falls back to the camera's up, which is the heading on the ground |

`view` is a `Transform`, not a `Camera`: with Cinemachine it is the output camera (the one with
the Brain), which is where the picture is taken from this frame. Left empty, the stick uses
world axes.

**Order in the frame.** The controller runs in `Update` and reads the camera's pose from the
end of the previous frame; the Brain moves the camera in `LateUpdate`, after the runner. One
frame of heading lag is invisible. The reverse order — camera before runner — is the jitter
case; `unity-camera` → `reference/update-order-and-jitter.md`.

## 2. Speed

| Field | Default | Reads as |
|---|---|---|
| `runSpeed` | 5 | A 10-unit room in 2 s |
| `speedScale` | 1 | 0.4 walks at 2, 1.4 sprints at 7. Set it from the game's own rule — a held button, stamina, a carried pickup |
| `groundAccel` | 33 | Run speed in 0.15 s |
| `groundDecel` | 50 | A stop in 0.1 s and 0.25 units |
| `airAccel` | 15 | `reference/jump-and-air.md`, section 6 |

Acceleration is `Vector3.MoveTowards` on the planar velocity, so a reversal passes through zero
and takes `2 × runSpeed / groundAccel` (0.3 s). Raise `groundAccel` when a reversal feels like
ice; lower `groundDecel` when a stop feels like a wall.

The stick's magnitude is the pace: no walk button is needed on a gamepad. On a keyboard the
stick is 0 or 1, and `speedScale` is where a walk key lands.

## 3. Facing — three modes

`facing` chooses what the body turns towards. In every mode the turn is
`Quaternion.RotateTowards` at `turnRate` degrees per second, and the source is **intent, never
velocity**: a runner sliding along a wall, carried by a platform or knocked back keeps facing
where the player pointed it.

| `FacingMode3D` | Faces | Use |
|---|---|---|
| `Movement` | The wish direction. Keeps the last facing when the stick is at rest | Free roaming: the runner crossing the gate room |
| `Strafe` | The view's heading, always | Aiming over the shoulder; the stick side-steps and back-pedals |
| `LockOn` | `lockTarget`, flattened | Circling the sentry. Falls back to `Movement` while the target is null |

**Turn rate.** 720°/s reverses in a quarter of a second: quick, with a visible arc. 360 reads as
a heavy character, 1440 as an arcade one, 0 snaps. The body turns while the velocity is already
going the new way; that slide through the turn is correct and is what the turn animation
covers. Slowing movement until the body has turned (a "tank" start) is a different design —
scale `wish` by `Vector3.Dot(transform.forward, wish.normalized)` clamped to 0..1.

**Strafe and the animation.** With the body locked to the view, the legs need a 2D blend
(forward/back × left/right) fed from the velocity in the body's own space:

```csharp
Vector3 local = transform.InverseTransformDirection(run.Velocity);
// local.z forward speed, local.x sideways speed → the directional tree
```

`unity-animation` → `reference/blend-trees.md` builds the tree.

**Lock-on is two parts, and only one is here.** The controller turns the body to the target and
moves the stick relative to the view, which the camera rig has swung behind the runner — so
stick-left circles. The camera part (a second target, the swing, framing both) is
`unity-camera` → `reference/follow-3d.md`, the lock-on section. Choosing and dropping the target
is the game's rule:

```csharp
run.lockTarget = sentry.transform;  run.facing = FacingMode3D.LockOn;      // engage
run.lockTarget = null;              run.facing = FacingMode3D.Movement;    // release, or the target is gone
```

Release when the target leaves a range (12 units) or line of sight for more than a second; a
lock that survives a wall drags the camera through it.

## 4. Where the camera ends

| The camera rig decides | The controller decides |
|---|---|
| Orbit angles from look input, distance, pivot height (1.5 above the feet) | Nothing about the camera |
| Boom collision and what it does at a wall | The capsule radius, which sets how close the body gets to that wall |
| Recentering behind the runner | Which way the body faces |
| Which camera is live | That movement follows `view` — reassign `view` only if the output camera object changes |

Two numbers cross the boundary: a corridor is at least as wide as the boom is long (4 units),
and the pivot is a child of the runner at chest height, not the runner's root at its feet.

## 5. Knock-back, launches, respawns

```csharp
run.Push(away * 6f + Vector3.up * 4f, 0.25f);    // a hazard: velocity replaced, stick ignored for 0.25 s
motor.Teleport(spawn.position);  run.ResetMotion();  // a respawn: both, in that order
```

`Push` is the only way anything outside the controller changes its velocity. A push with an
upward part takes the runner off the ground on that frame and ends coyote time.

## 6. Checks

| Check | Expect |
|---|---|
| `ThirdPerson_Stick_IsRelativeToTheView` | The view yawed 90° and pitched 30°: stick up moves along +X, more than 2 units in 0.6 s, under 0.1 of drift on Z, body within 5° of +X |
| Speed, stick-up against stick-right, camera pitched 40° | Equal. Unequal means the heading was not flattened |
| Probe `speed` on a keyboard diagonal | 5, not 7.07 |
| Stick at rest after a run | The body keeps its heading; it does not swing to world +Z |
| Orbit the camera with the stick held | The runner curves smoothly; a snap each frame is the camera being read before it moved |
