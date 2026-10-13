---
name: unity-3d-controller
description: >-
  Move a 3D character with one owner of its transform: a CharacterController
  motor that finds ground by its own cast (slopes, steps, moving platforms),
  third-person, first-person, top-down and lane-runner controllers reading one
  input struct, the Animator bridge, and journeys proving ramp, step, apex and
  lane change. Load for: "isGrounded flickers", "the capsule slides down the
  ramp", "can't climb the step", "jump height changes with frame rate",
  "forward flips when the camera cuts", "the pitch doesn't clamp", "the lane
  change overshoots". Greybox and kits are unity-3d-level; PhysX callbacks are
  unity-physics-3d; agents are unity-navigation; camera rigs are unity-camera.
---

# unity-3d-controller — choose who owns the transform before writing a line of movement

> **Most 3D controller bugs are two components moving one object.** A `CharacterController`
> beside a non-kinematic `Rigidbody`, a `NavMeshAgent` beside a `CharacterController`, root motion
> under a script that calls `Move`: each pair jitters, rubber-bands or sinks, and no tuning of
> either half fixes it. The first decision is not speed or gravity. It is which one component
> writes the position — and everything else then hands that owner a velocity.

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

## 1. Start here — the gate room

1. **Decide the body and six numbers** before the room exists: capsule 1.8 high, radius 0.4,
   skin 0.04; slope limit 45°, step offset 0.3; run speed 5; apex 1.2 in 0.35 s. Gravity (19.6)
   and jump velocity (6.86) are derived, never typed in.
2. **Build the runner.** `CharacterController` + `RunInputReader` + `CharacterMotor3D` +
   `ThirdPersonController`, with `view` set to the camera. No `Rigidbody`. Set the motor's
   `ground` mask to the level's layers, without the runner's own. The model and its Animator go
   on a child; an empty `Chest` child sits at the capsule's centre.
3. **Register with the probe**, where the game wires its harness:

```csharp
GameProbe.SetPlayerVelocity(() => chest, () => run.Velocity);   // the centre, not the feet
GameProbe.Register("grounded", () => run.Grounded);             // the motor's, never isGrounded
GameProbe.SetState(() => run.State);                            // Grounded · Rising · Falling
```

4. **Prove it** with `templates/Controller3DJourneyTest.cs`, which builds its own room from box
   colliders:

| Test | Asserts |
|---|---|
| `ThirdPerson_Ramp_IsClimbedGroundedAndHeld` | Every frame on a 30° ramp is grounded; over 2 units climbed in 0.8 s; at rest it slides under 0.02 in 0.5 s |
| `ThirdPerson_LowStep_IsClimbed` · `ThirdPerson_TallStep_IsRefused` | Feet on top of a 0.3 step; stopped at the face of a 0.6 one |
| `ThirdPerson_Jump_ReachesTheConfiguredApex` | A held jump peaks at 1.2 within 0.05, 0.35 s after the press |
| `ThirdPerson_Stick_IsRelativeToTheView` | With the view yawed 90°, stick up runs along +X |
| `FirstPerson_YawTurnsTheBody_PitchClampsOnTheHead` | 900 pointer counts turn the body 90°; pitch stops at 85°; the body never pitches |
| `LaneRunner_Change_LandsOnTheLaneInTheConfiguredTime` | x = ±1.3 within 0.01 after 0.15 s; a change asked for mid-change is kept; one past the edge is refused |
| the on-foot tests | `JourneyAsserts.NeverInside` reports nothing |

5. **Show the gate can fail.** `CONTROLLER3D_JOURNEY_BREAK=slope`, `=step`, `=tallstep`, `=tap`,
   `=pitch` and `=lane` each turn one test red. A journey nobody has seen fail proves nothing.
6. **Measure the jump** with `unity-gameplay` → `scripts/jump_report.py` against the timeline
   the jump test wrote, then build the room to the table `scripts/level_metrics.py
   --integrator exact` prints.
7. **Add the picture.** `AnimatorBridge3D` on the runner; the camera from `unity-camera`.

First person is step 2 with `FirstPersonController` and a `Head` child; the depot is
`TopDownController3D`; the lane run is `LaneRunnerController` alone, with no motor.

## Load what the situation needs

| The situation | Read |
|---|---|
| Which component owns the transform; what each costs; two owners; handing over to an agent | `reference/model-choice.md` |
| `isGrounded` flickering; the ground cast and its normal; slope limit; sliding off steep ground; sticking going downhill; step offset, skin width and the jump; moving and turning platforms; pushing bodies | `reference/grounding-and-slopes.md` |
| Gravity and jump velocity from apex and time; why the apex changes with frame rate and the two fixes; coyote time, the buffer, variable height, air control | `reference/jump-and-air.md` |
| Camera-relative movement; turn rate; facing by movement, strafing and locking on to a target | `reference/third-person.md` |
| Yaw on the body and pitch on the head; pointer counts against stick rates; eye height; crouch; footstep cadence | `reference/first-person.md` |
| World-axis movement under a fixed or overhead camera; pointer aim; click-to-move; the lane runner | `reference/topdown-and-fixed.md` |
| The script that writes `Grounded`, `MoveBlend`, `MoveSpeed` and `Hurt`; damping; root motion off | `reference/animator-bridge.md` |
| Reach tables, door and corridor numbers, the measuring scripts | `unity-gameplay` → `reference/level-metrics.md` |
| The input struct, the press latch and its buffer, a scripted driver | `unity-input` → `reference/reading-input.md` |
| Pointer and stick aim; mouse delta against stick rate | `unity-input` → `reference/pointer-and-aim.md` |
| Swipes and on-screen sticks for the lane run | `unity-input` → `reference/touch-and-on-screen.md` |
| Orbit, first-person and fixed rigs; boom collision; lock-on framing | `unity-camera` → `reference/follow-3d.md` |
| A camera that jitters behind the runner | `unity-camera` → `reference/update-order-and-jitter.md` |
| Casts, layer masks, a query that misses | `unity-physics-3d` → `reference/queries.md` |
| Agents, destinations, patrols | `unity-navigation` → `reference/recipes.md` |
| The parameter contract the bridge follows | `unity-animation` → `reference/parameter-contract.md` |
| Locomotion and strafe blend trees | `unity-animation` → `reference/blend-trees.md` |
| Root motion as the mover | `unity-animation` → `reference/root-motion.md` |
| The Animator asset the bridge feeds | `unity-rigged-character` → `reference/editor-templates.md` |
| A greybox room built to these numbers | `unity-3d-level` → `reference/greybox.md` |
| Ramp colliders over stairs | `unity-3d-level` → `reference/collision-proxies.md` |
| Journeys, the probe, the never-inside invariant | `unity-play-harness` → `reference/journeys.md` |

Copy the `resources/` files the owner needs into a Runtime assembly beside `RunInput.cs`
(`unity-input` → `resources/`); every controller and the bridge need `CharacterMotor3D.cs`,
which holds `IMoveFacts3D`, and the motor needs `MovingPlatform3D.cs`. The journey goes from
`templates/` into a PlayMode test assembly that also references the harness. The runtime files need no package — physics and animation are
built-in modules; the journey needs `com.unity.test-framework`.

---

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
| Action assets, the reader, touch controls, rebinding | `unity-input` |
| Camera rigs, orbit and look axes, boom collision, jitter | `unity-camera` |
| Collider set-up, the layer matrix, a callback that never fires, ragdolls | `unity-physics-3d` |
| NavMesh baking, agents, click-to-move scripts | `unity-navigation` |
| Greybox, kits, prefabs, collision proxies, terrain | `unity-3d-level` |
| Lights, baking, probes, shadows | `unity-lighting` |
| Draw calls, LOD, occlusion | `unity-scene-optimisation` |
| Animator graphs, blend trees, events, IK, root motion | `unity-animation` |
| Importing a rigged character and building its Animator asset | `unity-rigged-character` |
| Recorders, situations, the probe contract | `unity-play-harness` |
| Pressing use on a switch, a gate or a pickup | `unity-interaction` |
| Health, hurt, invincibility frames and when a hit asks for knock-back | `unity-combat` |
| 2D characters | `unity-2d-controller` |

Enemy behaviour, damage and switches are not controllers. A sentry that walks uses
`CharacterMotor3D` with its own rules in place of a player controller, or an agent; a hazard
calls `Push` and the bridge's `Hurt()`; what a sentry decides is `unity-game-ai`.
