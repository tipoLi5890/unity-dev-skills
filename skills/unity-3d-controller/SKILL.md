---
name: unity-3d-controller
description: >-
  Move a 3D character: CharacterController grounding, slopes, steps,
  third/first-person, lane runner.
---

# unity-3d-controller — choose who owns the transform before writing a line of movement

> **Most 3D controller bugs are two components moving one object.** A `CharacterController`
> beside a non-kinematic `Rigidbody`, a `NavMeshAgent` beside a `CharacterController`, root motion
> under a script that calls `Move`: each pair jitters, rubber-bands or sinks, and no tuning of
> either half fixes it. The first decision is not speed or gravity. It is which one component
> writes the position — and everything else then hands that owner a velocity.

## The situation → what to read

| The situation | Read |
|---|---|
| The first runner, step by step, and the journey that proves it | §1; `reference/gate-room.md` |
| Which component owns the transform; what each costs; two owners; handing over to an agent | `reference/model-choice.md` |
| "`isGrounded` flickers", "the capsule slides down the ramp", "can't climb the step"; the ground cast and its normal; slope limit; sliding off steep ground; sticking going downhill; step offset, skin width and the jump; moving and turning platforms; pushing bodies | `reference/grounding-and-slopes.md` |
| "Jump height changes with frame rate": gravity and jump velocity from apex and time; why the apex changes and the two fixes; coyote time, the buffer, variable height, air control | `reference/jump-and-air.md` |
| "Forward flips when the camera cuts": camera-relative movement; turn rate; facing by movement, strafing and locking on to a target | `reference/third-person.md` |
| "The pitch doesn't clamp": yaw on the body and pitch on the head; pointer counts against stick rates; eye height; crouch; footstep cadence | `reference/first-person.md` |
| World-axis movement under a fixed or overhead camera; pointer aim; click-to-move; the lane runner ("the lane change overshoots") | `reference/topdown-and-fixed.md` |
| The script that writes `Grounded`, `MoveBlend`, `MoveSpeed` and `Hurt`; damping; root motion off | `reference/animator-bridge.md` |
| Feet skate only at top speed because the mover outruns every clip; a swing that starts while the body still slides to a stop; what the mover must expose (acceleration, predicted stop) | `reference/animator-bridge.md` §2 |
| Stride and orientation warping, pelvis drop, foot lock — the animation side of a fast mover | `unity-animation` → `reference/sim-driven-animation.md` |
| Reach tables, door and corridor numbers, the measuring scripts | `unity-gameplay` → `reference/level-metrics.md` |
| The input struct, the press latch and its buffer, a scripted driver; action assets, rebinding | `unity-input` → `reference/reading-input.md` |
| Pointer and stick aim; mouse delta against stick rate | `unity-input` → `reference/pointer-and-aim.md` |
| Swipes and on-screen sticks for the lane run | `unity-input` → `reference/touch-and-on-screen.md` |
| Camera rigs: orbit, first-person and fixed; look axes; boom collision; lock-on framing | `unity-camera` → `reference/follow-3d.md` |
| A camera that jitters behind the runner | `unity-camera` → `reference/update-order-and-jitter.md` |
| Casts, layer masks, a query that misses; collider set-up, the layer matrix, a callback that never fires, ragdolls | `unity-physics-3d` → `reference/queries.md` |
| NavMesh baking, agents, destinations, patrols, click-to-move scripts | `unity-navigation` → `reference/recipes.md` |
| The parameter contract the bridge follows | `unity-animation` → `reference/parameter-contract.md` |
| Locomotion and strafe blend trees | `unity-animation` → `reference/blend-trees.md` |
| Root motion as the mover; Animator graphs, events, IK | `unity-animation` → `reference/root-motion.md` |
| Importing a rigged character; the Animator asset the bridge feeds | `unity-rigged-character` → `reference/editor-scripts.md` |
| A greybox room built to these numbers; kits, prefabs, terrain | `unity-3d-level` → `reference/greybox.md` |
| Ramp colliders over stairs | `unity-3d-level` → `reference/collision-proxies.md` |
| Journeys proving ramp, step, apex and lane change; recorders, situations, the probe, the never-inside invariant | `unity-play-harness` → `reference/journeys.md` |

Copy the `resources/` files the owner needs into a Runtime assembly beside `RunInput.cs`
(`unity-input` → `resources/`); every controller and the bridge need `CharacterMotor3D.cs`,
which holds `IMoveFacts3D`, and the motor needs `MovingPlatform3D.cs`. The journey goes from
`templates/` into a PlayMode test assembly that also references the harness. The runtime files need no package — physics and animation are
built-in modules; the journey needs `com.unity.test-framework`.

Once the owner is a `CharacterController`, the controller is two halves that never mix:

```
RunInput ──► rules ───────────────────► collision ──────────► CharacterController
(struct)     ThirdPersonController       CharacterMotor3D       Move, once per frame
             FirstPersonController       what the level allows
             TopDownController3D         ground, slope, step, carry
             what the runner wants
```

| Half | Knows | Never knows |
|---|---|---|
| Rules — one of the three controllers | Input levels and presses, the view, timers, gravity, jump velocity, facing | Layers, casts, normals |
| Collision — `resources/CharacterMotor3D.cs` | The capsule, what is ground, the slope under the feet, the platform carrying them | Input, gravity, what a jump is |

The rules call `Move(velocity, dt)` and read back `Grounded`, `OnCeiling`, `Velocity` and
`PlatformLaunch`. That seam is what a journey proves, and what lets a sentry reuse the motor
with rules of its own.

---

## 0. Pick the owner

One per character, chosen by constraint, written down before any code. If the project has not
named its view and movement model, `unity-gameplay` does that first.

| The game is | Owner of the transform | Files |
|---|---|---|
| A person on foot, seen from behind | `CharacterController`, through `CharacterMotor3D` | `CharacterMotor3D.cs`, `ThirdPersonController.cs` |
| The same, seen through its eyes | The same | `CharacterMotor3D.cs`, `FirstPersonController.cs` |
| Seen from above or from fixed cameras, moved by stick | The same | `CharacterMotor3D.cs`, `TopDownController3D.cs` |
| A lane runner: lane index plus forward speed | A kinematic `Rigidbody`, moved by `MovePosition` | `LaneRunnerController.cs` |
| Moved by destinations: click-to-move, followers | A `NavMeshAgent` — `unity-navigation` | — |
| Shoved and carried by other bodies | A dynamic `Rigidbody`, velocity assigned each step | `reference/model-choice.md` |

The built-in `CharacterController` needs no package. `com.unity.charactercontroller` is an
Entities package and is not this. What each owner gives and costs, the pairs that fight, and the
grep that finds a second writer: `reference/model-choice.md`.

## 1. The gate room — the first runner, in order

Decide the capsule (1.8 × 0.4, skin 0.04), slope 45°, step 0.3, run 5, apex 1.2 in 0.35 s — gravity
and jump velocity derived. Build `CharacterController` + `RunInputReader` + `CharacterMotor3D` +
`ThirdPersonController`, no `Rigidbody`; register velocity, the motor's `grounded` and the state
with the probe; prove ramp, step, apex, view-relative stick, pitch clamp and lane change with
`templates/Controller3DJourneyTest.cs`; turn each test red once with
`CONTROLLER3D_JOURNEY_BREAK`; measure the jump with `unity-gameplay` → `scripts/jump_report.py`;
then the bridge and the camera. First person, top-down and the lane run swap one component. Every
step, the probe lines and the test table: `reference/gate-room.md`.

## Discipline

- **One writer of the transform.** `Move` is called from one place, once per frame; nothing
  else assigns `transform.position`, a velocity or a root-motion delta on that object.
  Knock-back and launch pads call `Push`; a respawn calls `Teleport`.
- **No `Rigidbody` and no enabled agent beside a `CharacterController`.** A handover disables
  one owner before enabling the other, in the same frame.
- **Rules and collision stay in separate files.** A coyote timer in the motor or a layer mask
  in a controller is the first step back to one file nobody can test.
- **Ground is the motor's cast and a surface normal — never `isGrounded`, a tag or a ray from
  the centre.** And never while rising.
- **A `CharacterController` moves in `Update`.** It has no interpolation; moved in
  `FixedUpdate` it stutters. A kinematic `Rigidbody` moves in `FixedUpdate` with `MovePosition`.
- **Author what the player sees.** Apex height and time to apex are the tunables; gravity and
  jump velocity are computed, and the project's gravity is for props.
- **Assign the jump, never add it; move by the mean of the velocity before and after
  gravity.** The first keeps the jump the same on every surface, the second at every frame rate.
- **Condition first, then `TryUse`.** `canJump && input.TryUse(Launch)` buffers a press; the
  reverse spends it in mid-air.
- **Flatten the view before using it, clamp the stick, never normalise it.**
- **Yaw on the body, pitch on the head.** Pitch is a stored, clamped number, never read back
  from Euler angles.
- **A pointer delta is never multiplied by `deltaTime`; a stick always is.**
- **Facing comes from intent, never from velocity,** and keeps its value at rest.
- **In the lane run the lane index is the position.** It changes when the change starts.
- **Only the bridge writes the Animator,** and root motion is off on a script-moved character.
- **Step offset, slope limit, apex and coyote time are level-design numbers.** Fix them before
  rooms are built; re-run the reach table when one moves.
- **The human keeps the feel verdict.** The journey shows the apex is 1.2 and the ramp holds;
  whether 0.35 s to the apex feels right is a judgement.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Which perspective and movement model the game has; genre recipes; reach tables | `unity-gameplay` |
| Lights, baking, probes, shadows | `unity-lighting` |
| Draw calls, LOD, occlusion | `unity-scene-optimisation` |
| Pressing use on a switch, a gate or a pickup | `unity-interaction` |
| Health, hurt, invincibility frames and when a hit asks for knock-back | `unity-combat` |
| 2D characters | `unity-2d-controller` |

Enemy behaviour, damage and switches are not controllers. A sentry that walks uses
`CharacterMotor3D` with its own rules in place of a player controller, or an agent; a hazard
calls `Push` and the bridge's `Hurt()`; what a sentry decides is `unity-game-ai`.
