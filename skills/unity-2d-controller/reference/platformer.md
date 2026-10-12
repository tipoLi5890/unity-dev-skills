# The platformer character — collision asked for, rules decided

> Part of the `unity-2d-controller` skill. Everything a side-view runner does, split the way the
> code is split: `resources/PlatformerMotor2D.cs` finds out what is in the way,
> `resources/PlatformerController2D.cs` decides what the runner wants. Worked setting: the
> **side run** — rooftops, a ledge, a hazard to jump, a launch pad, a sentry on a ledge, the gate.

## 1. The step, in order

```
FixedUpdate   read input levels (Peek)                      controller
              timers: since grounded, since wall
              horizontal: move towards wish * runSpeed
              the Launch press: condition, then TryUse
              vertical: cut, gravity, fall cap
              motor.Move(velocity, dt)                      motor
                 step out of anything overlapping
                 carry sideways by the platform under the feet
                 sweep along the ground (or level, in the air)
                 sweep vertically; land or hit the ceiling
                 look for ground below; look for a wall beside
                 rise or fall with the platform now under the feet
                 MovePosition(result)
              keep the velocity Move returned
```

Gravity is applied before the move (velocity first, then position), from the take-off step.
That ordering fixes where the apex lands — `reference/jump-maths.md`.

## 2. Grounding

Two ways to know the runner is on the ground, and they fail differently.

| Method | How | Fails when |
|---|---|---|
| **Cast** (the motor's) | Sweep the body's own shape down by a skin and keep the hit whose normal is within the slope limit | The skin is larger than a step the level contains; the cast starts overlapping |
| **Contact normal** (a dynamic body) | `Rigidbody2D.GetContacts` with a `ContactFilter2D` whose `SetNormalAngle(90 − limit, 90 + limit)` keeps floors only | Read in `OnCollisionEnter2D` instead of polled: one step late, and true for walls |

Rules that hold for both:

- **The shape that moves is the shape that is cast.** A ray from the centre misses a ledge the
  box is still standing on by half its width; a narrower box says "airborne" on a roof edge.
- **A normal decides ground, never a tag or a layer.** `normal.y >= cos(maxSlopeAngle)`: 50°
  gives 0.64. The same collider is floor on top and wall at its side.
- **Not while rising.** A runner one step into a jump is still within the skin of the roof; the
  motor skips the ground look while `velocity.y > 0`, or the jump is cancelled on its first step.
- **Keep a skin.** The motor stops 0.02 short of every surface. A cast that begins touching
  reports a hit at distance 0 with a normal that says nothing about the surface.
- `OnCollisionStay2D` as a grounded flag is the usual wrong answer: it lags a step, counts
  walls, and never fires for a kinematic body against the level.

## 3. Slopes

- **Walking.** While grounded the horizontal move runs along the ground tangent
  `(normal.y, −normal.x)`, not along x. Speed along the surface stays `runSpeed`; the runner does
  not launch off a crest or stair-step down a descent.
- **The slope-slide problem.** A dynamic body at rest on a slope creeps downhill because
  gravity has a component along the surface and friction is zero (it was removed to stop wall
  sticking). The motor has no such problem by construction: grounded means vertical velocity is
  zero and no gravity move is made. On a dynamic body the fix is to set `gravityScale` to 0
  while grounded with no input, or to project gravity onto the ground normal.
- **Too steep.** A surface past `maxSlopeAngle` is a wall: horizontal movement stops at it, and
  a runner that falls onto it slides down it at its fall speed.
- **Staying on.** Running down a slope at 8 units/s the ground falls away 0.09 units per step at
  35°. The motor looks `groundSnap` (0.25) below a runner that was grounded and pulls it down;
  without that the runner is airborne on alternate steps and the jump only works half the time.
  Keep `groundSnap` below the shortest drop that should count as a ledge.
- **Jumping from a slope.** Jump velocity is assigned, not added; the horizontal velocity is
  kept as it is. A jump up a slope is not higher than a jump on the flat.

Check a slope set-up by standing still on it for two seconds with the probe running:
`pos` must not change, and `grounded` must not flicker.

## 4. One-way platforms

For a **kinematic** runner, a one-way platform is a filter in the motor's own sweep: put the
platforms on their own layer, assign it to `oneWay`, and never include it in `solid`. A hit on
that layer counts only when the sweep is a downward landing sweep, the normal points up, the
cast did not start inside it, and the feet are above the contact point. Horizontal and upward
sweeps ignore the layer, so the runner jumps up through and walks through the ends.

For a **dynamic** runner the engine does it with `PlatformEffector2D`, and three settings must
agree: the effector's `useOneWay`, the collider's `usedByEffector`, and a `surfaceArc` near 170°
so the ends are not top. Effector depth — `unity-physics-2d` → `reference/effectors-and-joints.md`.

A project with both (a kinematic runner, dynamic crates) uses both on the same platform: the
effector for the crates, the layer for the runner.

**Dropping through.** Down held and Launch pressed while `OnOneWay`:

- Kinematic: `motor.DropThrough()` ignores the layer for `dropSeconds` (0.25). The controller
  spends the press on the drop, so the same press does not also jump.
- Dynamic: `Physics2D.IgnoreCollision(runnerCollider, platformCollider, true)` for 0.25 s, then
  back to `false`. Never disable the platform's collider: everything else standing on it falls.

0.25 s is a fall of `½ · g · m · t²` = 1.76 units at the side-run numbers — more than any
platform is thick. If a platform is thicker than that, the feet check still refuses to land
inside it.

## 5. Moving platforms

A rider must move **in the same step** as the platform, by the platform's displacement for that
step. `resources/MovingPlatform2D.cs` runs before the runner (`DefaultExecutionOrder(-50)`),
works out its velocity for the step from its two positions, and exposes it; the motor adds
`Velocity * dt` to a runner that is grounded on it, then both bodies are moved by one
simulation step.

The two axes are added at different points, because every cast in the step sees the platform
where it is, not where the step takes it. The sideways part is swept first, so a wall stops a
carried runner. The vertical part is added last, after the ground look has placed the feet on
the platform's present pose: added first, a rising lift's carry is pulled straight back down
by the ground snap and the feet sink one step's travel into it. For the same reason a landing
sweep reaches further for a platform that is rising to meet the feet, or the lift overtakes a
slow fall between two steps and a one-way lift is fallen through.

| Approach | Result |
|---|---|
| Parent the runner to the platform | Scale and rotation leak in; `Rigidbody2D` interpolation breaks; un-parenting on a jump pops |
| Read the platform's `linearVelocity` | A kinematic body moved with `MovePosition` does not report a velocity a rider can use |
| Add last step's displacement | One step of lag: the feet sink into a rising platform and hover over a falling one |
| Publish this step's velocity, read it before moving | Correct — what the two files do |

**Carrying velocity off.** On the step the runner leaves a platform — a jump or a walk off the
end — the motor adds the platform's velocity to the one it returns (`inheritPlatformVelocity`),
taking only the upward part of y: a jump from a rising lift goes higher, a jump from a
descending one is not shortened. Air control then pulls x back to the wish at `airAccel`.

A **launch pad** is not a platform. It is a trigger whose handler calls
`controller.Push(new Vector2(0, 22), 0.1f)`: the velocity is replaced, the stick is ignored for
0.1 s, the jump cut is disarmed so a released button does not halve the launch, and coyote time
is cleared so the player cannot jump out of it.

## 6. The forgiving edges

**Coyote time** (`coyoteTime`, 0.1 s). A jump is a ground jump while
`TimeSinceGrounded <= coyoteTime`. The count is reset to "never" by the jump itself, so coyote
time cannot be spent twice, and by a drop through a platform.

**Jump buffer.** Not in the controller. The press is latched by the input source with its time
and stays usable for `RunInputSource.bufferSeconds` (0.12 s); the controller asks
*condition first, then* `TryUse(RunButton.Launch)`, so a press that cannot be acted on
stays pending. Reversed — `TryUse(...) && grounded` — the press is spent in the air and the
buffer does nothing. Mechanism: `unity-input` → `reference/reading-input.md`.

The window has to cover the wait: the feet touch, the motor reports it on that step, the
controller jumps on the next. A press made 0.10 s before the feet touch needs 0.10 s plus two
steps — 0.15 s at a 0.02 step. The default 0.12 s honours a press 0.08 s early.

**Both change the level.** 0.1 s of coyote time widens every gap by `runSpeed × 0.1` = 0.8
units. Decide both before rooms are drawn, and pass coyote time to the reach table
(`reference/jump-maths.md`).

## 7. Jump shape

**Variable height** (`RunAbility.VariableJump`, `jumpCutMultiplier` 0.5). Once per jump, on a
step where the runner is rising and `launchHeld` is false, upward velocity is multiplied by
0.5. Not zeroed: a zeroed cut makes the runner stop in mid-air; a halved one reads as a hop.

- The minimum hop is a tap: the cut lands on the take-off step. At the side-run numbers it
  peaks near 0.7 units against 2.85 for a full hold.
- **A scripted driver that taps gets the hop.** `ScriptedRunInput.Tap` releases in the same
  frame. A journey that measures the full apex uses `Hold` and `Release` after landing — the
  first thing to check when a measured apex is a quarter of the designed one.
- A buffered press released before landing produces the hop on landing. That is the input the
  player gave.

**Apex hang** (`apexHangSpeed`, `apexHangGravity`; off at 0). While `|velocity.y|` is under the
band, gravity is multiplied by `apexHangGravity`. A band of 2 units/s at 0.5 adds about 0.12 s
at the top, where the player aims. It raises the apex: re-measure and re-run the reach table.

**Fall** (`fallMultiplier` 1.5, `maxFallSpeed` 20). Gravity is multiplied once velocity turns
negative; the cap keeps a long drop readable and keeps a thin roof from being skipped — at 20
units/s the runner moves 0.4 units per step, so nothing solid is thinner than 0.4 unless the
motor is sweeping, which this one is.

**Double jump** (`extraJumps`). An air jump assigns the same jump velocity. It is a second apex
stacked on wherever the first one was spent, so it changes every row of the reach table.

## 8. Dash

`RunAbility.Dash`, on `dashButton` (Interact in the shipped actions): `dashSpeed` 20 for
`dashTime` 0.15 s covers about 3 units, level, with gravity suspended; `dashCooldown` 0.4 s; one air
dash, restored on landing. The runner leaves the dash at run speed, not dash speed, or every
dash becomes a long jump. Direction is the stick's x, or the facing with no stick.

A dash through a hazard is a rule about the hazard (ignore its trigger while `Dashing`), not
about collision: the motor still stops a dash at a wall.

## 9. Wall slide and wall jump

`WallSide` is −1, 0 or +1: set when the horizontal sweep is stopped by a surface too steep to
walk on, or when a `wallProbe` (0.06) to either side finds one while airborne.

- **Slide** (`RunAbility.WallSlide`): airborne, falling, and the stick pushed **towards** the
  wall → the fall cap becomes `wallSlideSpeed` (3). Requiring the push is what lets a player
  fall past a wall they are not interested in.
- **Jump** (`RunAbility.WallJump`): a Launch press within `wallCoyoteTime` (0.1 s) of touching a
  wall sets velocity to (`wallJumpPush` 9 away from the wall, jump velocity up) and ignores the
  stick for `wallJumpLock` (0.15 s). Without the lock a player holding towards the wall cancels
  the push on the next step and climbs one wall forever — which is a design decision, so make
  it with the number: 0.15 forbids it, 0 allows it.
- The ground jump is tested first, so a press beside a wall while standing jumps normally.

## 10. Runner notes

- **Auto-run.** `autoRun` replaces the stick's x with 1. The motor and every rule are the same;
  the player owns Launch and down. Raise `runSpeed` from a distance curve in the run's own
  state, not inside the controller.
- **Move the runner, not the world.** A world scrolled past a still runner leaves the probe's
  `pos` constant and every journey blind.
- **Lane hop** (a runner on three lanes, 1.3 units apart, seen from behind or above) is not this
  motor: a lane is an index, and a hop is a tween of the lane axis over `t_lane` (0.15 s) with a
  press during a hop buffered one deep. It is the cell model on one axis —
  `reference/grid-step.md` describes the same commit-then-show rule.

## 11. Ability gating as data

An exploration platformer hands out reach. Keep the set as data, not as scattered booleans:

```csharp
run.Grant(RunAbility.WallJump);          // the pickup's whole effect
run.extraJumps = 1;                      // the double jump
bool open = run.Has(gate.requires);      // a gate keyed to an ability
```

- Save the `RunAbility` value and `extraJumps`; restore both before the first step of a load.
- Every gate names the abilities it requires, and every room is checked against the set the
  player is **guaranteed** to hold there. A gate reachable one ability early is a sequence
  break, intended or not.
- A new ability is a new reach table: re-run the level check per ability set
  (`reference/jump-maths.md` §4).
- A situation that boots into a late room grants the room's set first, or the journey tests a
  runner the player never has.

## 12. Traps

| Symptom | Cause |
|---|---|
| Jumps only some of the time on a down-slope | No ground snap, or `groundSnap` smaller than the per-step descent |
| Sticks to a wall while falling (dynamic body) | Friction on the character's collider — `reference/model-choice.md` §3 |
| Catches on the seam between two tiles | Per-tile colliders: merge them — `unity-physics-2d` → `reference/tilemap-colliders.md` |
| Lands inside a one-way platform | The layer is also in `solid`, or the platform is thicker than one fall step and the feet check was removed |
| Falls through a moving platform going up | The platform runs after the runner: restore its execution order. Or it is moved by something other than `MovingPlatform2D`, so the motor has no velocity to meet |
| Jump is higher from a slope or a lift | Velocity added instead of assigned; inheritance of y without the clamp |
| Jump fires twice from one press | A press derived from `launchHeld` in `FixedUpdate` instead of `TryUse` |
| Runner vibrates on the ground | Two writers — `reference/model-choice.md` §4 |
| Head bumps stop the jump early under a low ceiling | Correct: every gap under that ceiling is shorter than the table says |

## Where each need is answered

| Need | Answer |
|---|---|
| Layers, the collision matrix, which layer a platform goes on | `unity-physics-2d` → `reference/layers-and-matrix.md` |
| Casts that miss, contact filters, `queriesStartInColliders` | `unity-physics-2d` → `reference/queries-2d.md` |
| Kinematic contacts, interpolation, simulation mode | `unity-physics-2d` → `reference/bodies-and-simulation.md` |
| The latch, the buffer, a scripted driver | `unity-input` → `reference/reading-input.md` |
| Following the runner without following every hop | `unity-camera` → `reference/follow-2d.md` |
| Rooms, chunks, the level the runner crosses | `unity-2d-level` → `reference/rooms-and-chunks.md` |
| The jump the game performed, measured | `unity-gameplay` → `reference/level-metrics.md` |
