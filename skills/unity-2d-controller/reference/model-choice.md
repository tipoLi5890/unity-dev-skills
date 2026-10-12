# Choosing the movement model — who writes the transform

> Part of the `unity-2d-controller` skill. Four ways to move a 2D character, what each one costs,
> and the constraint that picks it. The choice is made once per character and written down,
> because every bug in a controller with two models is a bug about which one moved it last.

## 1. The four models

| Model | Who writes position | The engine does | You do |
|---|---|---|---|
| **Kinematic body, your casts** — `resources/PlatformerMotor2D.cs` | `Rigidbody2D.MovePosition`, once per step, to a point your sweeps found | Answers shape casts; fires triggers | Stop at surfaces, decide what is ground, slopes, one-way platforms, platform carry |
| **Kinematic body, `Rigidbody2D.Slide`** | The engine, from a velocity and a `Rigidbody2D.SlideMovement` you hand it | Sweeps, slides along surfaces, applies the gravity you pass, reports the surface it found | Everything that is a rule: jump, coyote time, one-way filtering, carry |
| **Dynamic body, your velocity** — `resources/TopDownMotor2D.cs` | The solver, from the `linearVelocity` you assign every step | Resolves contacts, pushes the body out of walls, applies friction and restitution | Assign velocity every step; remove friction; never also write the transform |
| **Cell map** — `resources/GridStepMover.cs` | A tween between two cell centres | Nothing: no body is needed to move | Ask the map whether the cell is free; show the step |

A fifth exists and is wrong for a player character: a dynamic body left to gravity and pushed
with `AddForce`. It is a crate with a face. Use it for crates.

## 2. Which constraint picks which

| The game's constraint | Model | Because |
|---|---|---|
| Side view, gravity, jumps that must land on a designed apex | Kinematic, your casts | The jump is arithmetic you own; a solver contact, a material or a second writer cannot move the apex |
| Side view, slopes and curved ground everywhere, no one-way platforms or few | Kinematic with `Slide` | The engine's slide handles surfaces better than a two-axis sweep; you keep the rules |
| Side view, physics is the game: pushed crates, see-saws, a runner knocked about | Dynamic, your velocity | Being pushed is free on a dynamic body and laborious on a kinematic one |
| Top-down, no gravity, free movement | Dynamic, your velocity | There is no ground to decide; push-out against walls is exactly the wall slide wanted |
| Top-down, level authored to the cell, turn order or pushing blocks | Cell map | Half a cell is not a place; a body that can stand between cells is a body that snags on doorways |
| Fixed screen, a ship and a hundred bullets | Dynamic for the ship, no bodies for the bullets | The ship needs walls; a bullet needs a ray from its last position to its next |
| A runner whose forward speed the game owns | Kinematic, your casts, with horizontal input replaced | The same motor; `autoRun` on the controller |

## 3. What each one costs

**Kinematic, your casts.**
- Nothing pushes the runner. A platform that moves sideways into it passes into it; the motor
  steps out with `Collider2D.Distance` before sweeping. A crate does not stop it and is not
  pushed by it — pushing is a rule you write.
- A kinematic body reports no `OnCollisionEnter2D` against static or kinematic bodies unless
  `Rigidbody2D.useFullKinematicContacts` is on. Triggers fire either way. Take contact facts
  from the motor's own state (`Grounded`, `WallSide`, `OnCeiling`), not from callbacks.
- A two-axis sweep (along the ground, then vertical) is exact on boxes and good on slopes up to
  the limit; it is not a general solver. Concave corners tighter than the body and curved
  ground are where to move to `Slide`.

**Kinematic with `Slide`.** `Rigidbody2D.Slide(velocity, deltaTime, slideMovement)` returns a
`Rigidbody2D.SlideResults` (`position`, `remainingVelocity`, `slideHit`, `surfaceHit`,
`iterationsUsed`). The `SlideMovement` fields that decide behaviour:

| Field | Set it to | Why |
|---|---|---|
| `gravity` | `Vector2.zero` when the controller integrates its own gravity | Two gravities is the commonest `Slide` bug: the controller's and the struct's. To use the struct's instead, log `SlideResults.position` over one step from rest and confirm the distance fallen before trusting a value |
| `surfaceUp` · `surfaceSlideAngle` | `Vector2.up` · the slope limit | The reference direction and the steepest surface the velocity slides along |
| `gravitySlipAngle` | The slope limit | Above it, the gravity move slips down the surface: the slope-slide rule |
| `surfaceAnchor` | A short downward vector, e.g. `(0, -0.05)` | The direction and distance in which a nearby surface is looked for: the ground stick |
| `SetLayerMask(mask)` | The solid layers | Sets `layerMask` and `useLayerMask` together |
| `useSimulationMove` | `true` | Moves with `MovePosition`, so interpolation keeps working; `false` moves instantly |
| `maxIterations` | 3 | Slide passes per call |
| `startPosition` · `useStartPosition` · `useNoMove` | For a query that must not move the body | Ask "where would I end up" without going |

A `new Rigidbody2D.SlideMovement()` starts with `gravity` `(0, -9.81)` and `surfaceAnchor`
`(0, -1)`: left alone it falls under the project's gravity and snaps onto any surface within one
unit below. Set both. Read grounded from `surfaceHit` (a collider is present and its normal is
inside the slope limit). One-way platforms are not filtered by `Slide`: put them on a layer left out of the mask
while the runner is rising or dropping, and include it while falling.

**Dynamic, your velocity.**
- Friction is why a side-view runner sticks to a wall it is pressed against. Give the
  character's collider a `PhysicsMaterial2D` with friction 0 and `frictionCombine` set to
  `PhysicsMaterialCombine2D.Minimum`, so the level's material cannot put it back.
- The solver can add velocity you did not ask for: a slope converts a horizontal push into
  lift, a corner into a bounce. Assign the whole velocity every step; do not accumulate into it.
- The apex is the solver's as much as yours. Linear damping, a contact on the take-off step or
  gravity scale all move it — measure, do not assume (`reference/jump-maths.md`).
- Interpolation must be on for a camera that follows on the render clock.

**Cell map.** The transform lies for `stepTime` seconds on every step: the cell has already
changed. Anything that asks "where is the runner" must ask the cell, never the transform —
`reference/grid-step.md`.

## 4. One writer, checked

Whatever the model, exactly one line moves the character. Find a second one:

```bash
# Every write to a position or a velocity in gameplay code. Expect one file per character.
grep -rnE 'transform\.position\s*=|\.Translate\(|MovePosition\(|linearVelocity\s*=|\.Slide\(|AddForce\(' Assets --include='*.cs'
```

| Second writer | What it looks like in play |
|---|---|
| An `Animator` with a position curve or root motion on the body's object | The runner snaps back every frame; fine with the Animator disabled |
| `transform.position` written beside a `Rigidbody2D` | Jitter, and contacts that resolve a step late |
| A knock-back that writes velocity while the controller also writes it | The push lasts one step |
| A moving platform that parents the runner | The runner's scale and rotation follow the platform; interpolation breaks |
| A tween library moving a cell-stepped runner while the mover does too | Steps that overshoot and return |

Knock-back, a launch pad and a conveyor are all the same thing done right: they hand a velocity
to the one writer (`PlatformerController2D.Push`, `TopDownMotor2D.Push`) and it decides.

## 5. Changing your mind

Rules and collision live in separate files so the model can change under the rules:
`PlatformerController2D` calls one method, `Move(velocity, dt)`, and reads four facts
(`Grounded`, `WallSide`, `OnOneWay`, `Velocity`). A motor built on `Slide`, or on a dynamic body,
that offers the same five members drops in beneath it, and `templates/PlatformerJourneyTest.cs`
says whether the jump survived the change.

## Where each need is answered

| Need | Answer |
|---|---|
| Body types, simulation mode, interpolation, why a callback does not fire | `unity-physics-2d` → `reference/bodies-and-simulation.md` |
| Casts, contact filters, queries that miss | `unity-physics-2d` → `reference/queries-2d.md` |
| Which constraints the game has in the first place | `unity-gameplay` → `reference/perspective-fingerprint.md` |
| The camera reading a body on the wrong clock | `unity-camera` → `reference/update-order-and-jitter.md` |
