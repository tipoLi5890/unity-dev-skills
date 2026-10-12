---
name: unity-2d-controller
description: >-
  Move a 2D character with one owner of its transform: a kinematic platformer
  motor that asks physics where the ground is (slopes, one-way and moving
  platforms, coyote time, variable jump, dash, wall jump), free top-down
  movement with aim split from move, cell steps shown as tweens, the Animator
  bridge, and journeys that prove apex, coyote and buffer. Load for: "the
  character slides down slopes", "it sticks to walls", "the jump feels floaty",
  "can't jump right at the edge", "falls through the moving platform",
  "diagonal movement is faster", "the sprite faces the wrong way". Colliders,
  layers and callbacks are unity-physics-2d; cell maths is unity-2d-grid;
  reading the device is unity-input.
---

# unity-2d-controller — a platformer character asks physics where the ground is; it is not simulated by it

> **A character left to the solver is a crate with a face.** A dynamic body under gravity slides
> down slopes, sticks to walls by friction, bounces off corners and jumps a different height
> every time a contact lands on the take-off step. None of those are bugs in the physics. The
> fix is not a setting: the character stops being simulated, decides its own velocity, and uses
> the engine only to ask what is in the way.

So every controller here is two halves that never mix:

```
RunInput ──► rules ──────────────► collision ─────────────► Rigidbody2D
(struct)     PlatformerController2D  PlatformerMotor2D        MovePosition, once per step
             what the runner wants   what the level allows
             coyote, cut, dash       ground, slope, one-way, carry
```

| Half | Knows | Never knows |
|---|---|---|
| Rules — `resources/PlatformerController2D.cs` | Input levels and presses, timers, abilities, gravity, jump velocity | Layers, casts, normals |
| Collision — `resources/PlatformerMotor2D.cs` | Layers, the body's shape, what is ground, the platform under the feet | Input, gravity, what a jump is |

The rules call one method — `Move(velocity, dt)` — and read back four facts: `Grounded`,
`WallSide`, `OnOneWay`, `Velocity`. That seam is what lets a journey prove the jump, and lets the
collision half be replaced without touching a rule.

---

## 0. Pick the movement model

One model per character, chosen by constraint, written down before any code. If the project has
not named its view and movement model, `unity-gameplay` does that first.

| The game is | Model | Transform owner | Files |
|---|---|---|---|
| Side view under gravity: platformer, gated exploration, auto-runner | Kinematic body, moved to where casts allow | `PlatformerMotor2D` | `PlatformerMotor2D.cs`, `PlatformerController2D.cs`, `MovingPlatform2D.cs` |
| Seen from above, free movement: action-adventure, twin-stick, fixed-screen shooter | Dynamic body, gravity scale 0, velocity assigned every step | The solver, from one writer | `TopDownMotor2D.cs` |
| Cells: tactics, tile puzzle, RPG authored to the tile | The cell map; the transform is a tween | `GridStepMover` | `GridStepMover.cs` |

Why each, what each costs, and the grep that finds a second writer: `reference/model-choice.md`.

## 1. Start here — the side run

1. **Decide four numbers** before the level exists: apex height 3, time to apex 0.4 s, run speed
   8, coyote time 0.1 s. Gravity (37.5) and jump velocity (15) are derived, never typed in.
2. **Build the runner.** `Rigidbody2D` (Interpolate) + one `BoxCollider2D` (0.8 × 1.8) +
   `RunInputReader` + `PlatformerMotor2D` + `PlatformerController2D`. The motor makes the body
   kinematic. Set `solid` to the rooftop layer and `oneWay` to the platform layer — two layers,
   never one.
3. **Register with the probe**, where the game wires its harness:

```csharp
GameProbe.SetPlayerVelocity(() => run.transform, () => (Vector3)run.Velocity);
GameProbe.Register("grounded", () => run.Grounded);
GameProbe.SetState(() => run.State);          // Grounded · Rising · Falling · WallSlide · Dash
```

4. **Prove it** with `templates/PlatformerJourneyTest.cs`, which builds its own rooftops:

| Test | Asserts |
|---|---|
| `Jump_ReachesTheConfiguredApex` | A held jump peaks at `apexHeight − jumpVelocity·dt/2` (2.85), within 0.05 |
| `Press_JustAfterTheLedge_StillJumps` | A press spent 0.08 s after the last grounded step jumps |
| `Press_LongAfterTheLedge_IsRefused` | A press at 0.16 s does not: coyote time is not a double jump |
| `Press_JustBeforeLanding_JumpsOnLanding` | With a 0.15 s buffer, a press 0.10 s before the feet touch jumps from the roof |
| all four | `JourneyInvariants2D.NeverInside2D` reports nothing |

5. **Show the gate can fail.** `PLATFORMER_JOURNEY_BREAK=coyote`, `=buffer` and `=tap` each turn
   one test red. A journey nobody has seen fail proves nothing.
6. **Measure the jump** with `unity-gameplay` → `scripts/jump_report.py` against the
   timeline the first test wrote, then build the level to the number it prints.

The depot is the same loop with `TopDownMotor2D` and `templates/TopDownJourneyTest.cs`
(diagonal speed, wall slide with `NeverInside2D`, stopping distance); the sorting yard with
`GridStepMover` and two delegates.

## Load what the situation needs

| The situation | Read |
|---|---|
| Kinematic or dynamic; `Rigidbody2D.Slide`; who owns the transform; a second writer | `reference/model-choice.md` |
| Grounding, slopes, sliding downhill, one-way platforms and dropping through, moving platforms, coyote time, buffer, short hop, apex hang, dash, wall slide and wall jump, auto-run, abilities as data | `reference/platformer.md` |
| Gravity and jump velocity from height and time; rise and fall gravity; why the apex is 2.85 and not 3; measuring it | `reference/jump-maths.md` |
| Four-way, eight-way, analogue; the fast diagonal; acceleration and stopping; wall slide; twin-stick aim; screen clamp; knock-back | `reference/topdown-free.md` |
| One cell per step: commit then tween, key repeat, one buffered step, a refused step, pushing a pickup | `reference/grid-step.md` |
| Which way the sprite faces; flipping against directional clips; the bridge that writes the Animator | `reference/facing-and-animator-bridge.md` |
| Reach tables, gap and ledge checks, the measuring script | `unity-gameplay` → `reference/level-metrics.md` |
| The input struct, the press latch and its buffer, a scripted driver | `unity-input` → `reference/reading-input.md` |
| Stick and pointer aim resolved to a direction | `unity-input` → `reference/pointer-and-aim.md` |
| Body types, simulation mode, interpolation | `unity-physics-2d` → `reference/bodies-and-simulation.md` |
| Casts, contact filters, a query that misses | `unity-physics-2d` → `reference/queries-2d.md` |
| Tile seams that catch the runner; composite colliders | `unity-physics-2d` → `reference/tilemap-colliders.md` |
| Platform effectors for dynamic bodies | `unity-physics-2d` → `reference/effectors-and-joints.md` |
| Which layers, and which pairs collide | `unity-physics-2d` → `reference/layers-and-matrix.md` |
| Cell coordinates on rectangular, isometric and hexagonal boards | `unity-2d-grid` → `reference/coordinates.md` |
| Occupancy, reservations, turn order | `unity-2d-grid` → `reference/occupancy-and-turns.md` |
| Following the runner; a camera that jitters behind it | `unity-camera` → `reference/follow-2d.md` |
| The state graph the bridge feeds, side-on | `unity-animation` → `reference/sprite-state-graph.md` |
| Directional trees fed by the facing | `unity-animation` → `reference/blend-trees.md` |
| Journeys, the probe, the never-inside invariant | `unity-play-harness` → `reference/journeys.md` |

Copy the `resources/` files the model needs into a Runtime assembly beside `RunInput.cs`
(`unity-input` → `resources/`), and the journey from `templates/` into a PlayMode test assembly
that also references the harness. The runtime files need no package — 2D physics and animation are
built-in modules; the journeys need `com.unity.test-framework`.

---

## Discipline

- **One writer of the transform.** `Move` is called from one place; nothing else assigns
  `transform.position`, `linearVelocity` or a root-motion curve on that object. Launch pads,
  hazards and conveyors hand a velocity to the controller (`Push`); they do not move the body.
- **Rules and collision stay in separate files.** A coyote timer in the motor or a layer mask in
  the controller is the first step back to one file nobody can test.
- **Author what the player sees.** Apex height and time to apex are the tunables; gravity and
  jump velocity are computed. Do not use the project's gravity for the jump.
- **Assign the jump, never add it.** `v.y = jumpVelocity`. Added to a slope's or a lift's upward
  velocity it is a different jump on every surface.
- **Velocity first, then position, gravity from the take-off step.** That is the integrator the
  level numbers assume; the apex sits `v0·dt/2` under the designed one. Change the order and
  every ledge in the game moves.
- **Ground is a cast of the body's own shape and a normal, not a callback, a tag or a ray from
  the centre.** And never while rising.
- **Condition first, then `TryUse`.** `canJump && input.TryUse(Launch)` buffers a press;
  the reverse spends it in mid-air. The buffer length lives on the input source.
- **Read levels with `Peek`, presses with `TryUse`, both in `FixedUpdate`.** Never a device, and
  never a press rebuilt from `held && !wasHeld`.
- **A held jump and a tapped jump are different jumps.** Measure the apex with the button held;
  a driver that taps is measuring the short hop.
- **Clamp a move vector, do not normalise it.** Clamped, a keyboard diagonal is not 41% fast and
  a half-pushed stick is still half speed.
- **Facing comes from intent, never from velocity,** and keeps its value at rest.
- **In a cell game the cell is the position.** It changes when the step starts; the transform
  catches up. Game logic that reads the transform is wrong for half of every step.
- **Coyote time, buffer, apex hang and extra jumps are level-design numbers.** Each changes
  reach; fix them before rooms are drawn and re-run the reach table when one moves.
- **The human keeps the feel verdict.** The journey shows the apex is 2.85 and the press was
  honoured at 0.08 s; whether 0.4 s to the apex feels right is a judgement.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Which perspective and movement model the game has; genre recipes; reach tables | `unity-gameplay` |
| Action assets, the reader, touch controls, rebinding | `unity-input` |
| Body and collider set-up, the layer matrix, effectors, a callback that never fires | `unity-physics-2d` |
| Cell coordinates, neighbours, pathfinding, occupancy, turn order | `unity-2d-grid` |
| Tilemap layers, rooms, chunks, level data | `unity-2d-level` |
| Sort order, sorting from above, 2D lights | `unity-2d-rendering` |
| Animator graphs, blend trees, events | `unity-animation` |
| Bones, skinned sprites, swapping parts | `unity-2d-animation` |
| Frames into clips, pivots | `unity-2d-sprites` |
| Follow cameras, confiners, jitter | `unity-camera` |
| Recorders, situations, the probe contract | `unity-play-harness` |
| NavMesh agents and click-to-move | `unity-navigation` |
| 3D characters and PhysX | `unity-physics-3d` |

Enemy behaviour, combat and interaction are not controllers: a sentry that patrols a ledge uses
`PlatformerMotor2D` with its own rules in place of `PlatformerController2D`, and what it decides
is the game's.
