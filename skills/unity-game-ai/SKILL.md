---
name: unity-game-ai
description: >-
  Enemy behaviour in 2D and 3D that perceives on a budget, decides on a tick
  and leaves movement to whoever owns the transform: a code state machine, a
  small behaviour tree, a vision cone as distance, angle and one cast,
  hearing, memory, patrol and chase, 2D pathfinding, wave spawners,
  turn-based move scoring, and a journey proving the sentry chases only after
  it sees. Load for: "the enemy sees me through walls", "the guard never
  gives up", "it flickers between two states", "every enemy raycasts every
  frame", "enemies spawn on top of me", "the AI picks a dumb move".
  Baking and agents are unity-navigation; grid A* is unity-2d-grid; damage is
  unity-combat; doors are unity-interaction.
---

# unity-game-ai — perception on a budget, decisions on a tick, movement by whoever owns the transform

> **An enemy that re-plans every frame and moves itself is slow, and it jitters.** Slow, because
> twenty sentries casting a ray and re-issuing a path sixty times a second do twelve hundred of
> each for decisions that change twice a second. Jittery, because a brain that writes
> `transform.position` is a second writer beside the agent, the motor or the cell map that
> already owns it. Neither is fixed by a cleverer brain. Both are fixed by three layers on three
> clocks.

```
perceive ───────────► decide ─────────────► act ──────────────────► IMover
10 Hz, cast budget    10 Hz, same tick      every simulation step    owns the transform
Perception.cs         StateMachine.cs       the current state        NavMeshAgent · 2D motor · cells
writes the            reads the blackboard, timers, arrival,         MoveTo(point, speed, stop)
blackboard            changes state         a re-path interval       Position · Velocity · Arrived
```

| Layer | May | Never |
|---|---|---|
| Perceive — `resources/Perception.cs` | Test range and angle, spend one cast from the shared budget, remember | Change state, move anything |
| Decide — `resources/StateMachine.cs` | Evaluate transitions against the blackboard, at most one per tick | Cast, read the target's transform |
| Act — the states in `resources/SentryBrain.cs` | Run timers, ask the mover for a destination at an interval | Assign `transform.position`, `linearVelocity` or a rotation |
| Move — an `IMover` | Own the transform, path, steer, collide | Know why it was asked |

The seam is the blackboard on one side and `IMover` on the other. That is what lets a journey
prove the sentry's decisions with no NavMesh in the scene, and lets the same brain walk a 3D
gate room, a 2D depot and a board of cells.

---

## 0. Pick who moves the enemy

One owner per enemy, chosen by the world it walks on, before any state is written.

| The world is | The mover | The enemy's brain calls | Route |
|---|---|---|---|
| 3D ground with a baked surface | `NavMeshAgent` | `resources/NavMeshAgentMover.cs` | `unity-navigation` |
| 2D from above, free movement | The same dynamic-body motor the runner uses, fed a direction | An adapter over `TopDownMotor2D` | `reference/patrol-and-chase.md` §6 |
| 2D side view under gravity | The kinematic motor, with the sentry's own rules in place of the player's | `PlatformerMotor2D.Move` | `reference/patrol-and-chase.md` §6 |
| Cells, real time or turn-based | The cell map; the transform is a tween | One step along a path of cells | `reference/pathfinding-2d.md`, `reference/tactics-ai.md` |
| An open arena with a few pillars | A velocity steered round obstacle casts | The same adapter, with steering | `reference/pathfinding-2d.md` §3 |

## 1. Start here — the gate room sentry

1. **Decide the numbers** before the room exists. They are fairness, not tuning:

| Number | Start | Decides |
|---|---|---|
| Sight range · cone | 6 units · 70° | Whether the player sees the cone before it sees them; keep it inside the camera's view |
| Keep range · cone | 7.5 units · 100° | Hysteresis: a runner on the cone's edge is not seen and lost every tick |
| Decision interval | 0.1 s | Worst-case delay before anything is noticed; the cost of every sentry |
| Reaction time | 0.4 s | How long the player has to break sight after the sentry turns |
| Memory | 3 s | How long hiding takes to work |
| Patrol · chase speed | 2 · 4 (the runner is 5) | Whether a seen runner can still get away |
| Stopping distance · attack range | 1 · 1.5 | Where the chase ends and combat begins |
| Leash | 15 units from home | How far a sentry can be dragged off its post |

2. **Build the sentry.** `SentryBrain` + one mover (`NavMeshAgentMover` beside a
   `NavMeshAgent`) + a target. Cover goes on its own layer and into `blockers`; the sentry and the
   runner never sit on a cover layer. In 2D set `plane` to XY, both heights to 0, and add
   `resources/Perception2D.cs`.
3. **Register with the probe**, where the game wires its harness:

```csharp
GameProbe.Register("sentry", () => sentry.StateName);     // Patrol · Suspicious · Chase · Return
GameProbe.Register("sentryAlert", () => sentry.Alert);    // 0..1
```

4. **Prove it** with `templates/SentryJourneyTest.cs`, which builds a post, a wall and a runner
   from primitives and needs no NavMesh:

| Test | Asserts |
|---|---|
| `Sentry_DoesNotReact_OutsideTheConeOrBehindAWall` | With the runner in range behind the sentry, then behind cover, the state never leaves Patrol and alert stays 0 |
| `Sentry_NoticesWithinOneDecisionTick_AndChasesAfterItsReactionTime` | Never before the room says the runner is visible; out of Patrol within 0.1 s of it; Chase 0.4 s after, give or take a tick; closes to the stopping distance and no nearer |
| `Sentry_ReturnsToPatrol_AfterLosingTheRunnerForTheMemoryTime` | The chase is held for 3 s after the runner vanishes, not less and not more; then Return, then Patrol at the post |

5. **Show the gate can fail.** `SENTRY_JOURNEY_BREAK=los` (the cast is skipped) turns the first
   two tests red, `=cone` (360°) the first, `=memory` (30 s) the third. A journey nobody has
   seen fail proves nothing.
6. **Then add the world**: the surface and the agent (`unity-navigation`), the attack
   (`unity-combat`), the gate the sentry cannot pass (`unity-interaction`).

## Load what the situation needs

| The situation | Read |
|---|---|
| States as objects, the decision tick, the blackboard, hysteresis, a state that flickers, debugging by the state name | `reference/state-machine.md` |
| Selector, sequence, decorator; when a tree beats a state machine; running-node memory; when to add the Behavior package | `reference/behaviour-tree.md` |
| The cone as distance, dot and one cast; staggering and the cast budget; hearing; memory; teams; 2D and 3D | `reference/perception.md` |
| Waypoints and waits, chase with a re-path interval, the leash, losing the target, searching, the hand-off to an attack, the mover adapters | `reference/patrol-and-chase.md` |
| Pathfinding in 2D: grid A*, a NavMesh on the XY plane, steering — and how to choose | `reference/pathfinding-2d.md` |
| Waves as data, hidden spawn points, the live cap, pacing by budget, a seeded run | `reference/spawners-and-waves.md` |
| Turn-based opponents: reachable cells, scoring a move, picking one | `reference/tactics-ai.md` |
| Baking, agent settings, links, obstacles, an agent that will not move | `unity-navigation` |
| Chase, patrol and click-to-move scripts on an agent; agent and Animator coupling | `unity-navigation` → `reference/recipes.md` |
| A* on a board, corner rules, per-unit passability | `unity-2d-grid` → `reference/pathfinding.md` |
| Movement range by flood | `unity-2d-grid` → `reference/neighbours-and-range.md` |
| Sight between cells, with no cast | `unity-2d-grid` → `reference/line-of-sight.md` |
| Who stands where, reservations, turn order | `unity-2d-grid` → `reference/occupancy-and-turns.md` |
| The 2D motors the sentry is moved by | `unity-2d-controller` → `reference/topdown-free.md`, `unity-2d-controller` → `reference/platformer.md` |
| One cell per step shown as a tween | `unity-2d-controller` → `reference/grid-step.md` |
| The 3D body an enemy shares with the player | `unity-3d-controller` → `reference/model-choice.md` |
| A linecast that misses or hits the caster, in 2D · in 3D | `unity-physics-2d` → `reference/queries-2d.md` · `unity-physics-3d` → `reference/queries.md` |
| Which layers are cover | `unity-physics-2d` → `reference/layers-and-matrix.md` |
| What happens inside attack range: windows, one hit per swing | `unity-combat` → `reference/attack-windows.md` |
| Health, damage events, who can hurt whom | `unity-combat` → `reference/damage-contract.md` |
| A gate or door that blocks a sentry until a switch opens it | `unity-interaction` → `reference/doors-and-switches.md` |
| Pooling what the spawner creates | `unity-scene-flow` → `reference/pooling.md` |
| Pause, and what stops ticking with it | `unity-scene-flow` → `reference/game-state-and-pause.md` |
| The alert bark, the flash on noticing | `unity-game-feel` → `reference/feedback-stack.md` |
| The Animator shows the sentry's state | `unity-animation` → `reference/parameter-contract.md` |
| A sentry's cone drawn as a 2D light | `unity-2d-rendering` → `reference/lights-2d.md` |
| Journeys, the probe, proving a gate fails | `unity-play-harness` → `reference/journeys.md` |
| Where the frame time goes with a crowd on screen | `unity-profiling` → `reference/where-the-time-goes.md` |

Copy `StateMachine.cs`, `Perception.cs` and `SentryBrain.cs` into a Runtime assembly; add
`NavMeshAgentMover.cs` when an agent moves the sentry and `Perception2D.cs` in a 2D game;
`WaveSpawner.cs` stands alone. The journey goes into a PlayMode test assembly that also holds
the harness and `RunInput.cs` (`unity-input` → `resources/`). No behaviour package is needed:
`com.unity.behavior` is not in the editor's default set, and `reference/behaviour-tree.md` says
when it earns its place.

---

## Discipline

- **The brain never writes the transform.** It calls `MoveTo`, `Stop` and `Face` on one `IMover`.
  Grep the enemy's scripts for `transform.position =`, `linearVelocity =` and `MovePosition`:
  outside the mover, every hit is a second writer.
- **Perceive and decide on a tick, act on the step.** 10 Hz is the default; 5 Hz for anything off
  screen. A decision made 0.1 s late is invisible; a cast every frame per enemy is not.
- **Cheapest test first, one cast last.** Squared distance, then a dot product against a cosine,
  then a single linecast — and only when the first two pass.
- **Casts come out of one budget.** `PerceptionBudget.CastsPerStep` caps the whole crowd; a
  refused sentry keeps what it knew and asks on the next step. Watch `Deferred`.
- **Stagger.** Sentries created together start their clocks at different phases, or the crowd's
  whole cost lands on one step in ten.
- **Every transition has hysteresis.** A wider cone to keep than to notice, a meter that fills
  and drains, a dwell time, a leash with two radii. One threshold used in both directions is a
  state that flickers.
- **Chase where the target was seen, never where it is.** A brain that reads the runner's
  transform while it cannot see it is reading the player's mind, and players notice.
- **Do not re-issue a destination every step.** A re-path interval (0.25 s) and a minimum
  goal movement (0.5 units); a destination set each frame discards the corridor each frame.
- **Draw what is tested.** The cone gizmo, mesh or light reads the same range and angle fields
  the test does. A cone drawn wider than it tests is a complaint with no bug behind it.
- **The state is a string a probe can read.** `Register("sentry", …)` before the first bug
  report; "it sometimes ignores me" becomes a timeline with the state in every sample.
- **AI does not deal damage.** `InAttackRange` is where this skill stops.
- **Spawning is seeded and capped.** Print the seed with every report; never spawn where the
  camera looks.
- **The human keeps the fun verdict.** The journey shows the sentry noticed in 0.1 s and gave up
  after 3 s; whether 3 s is tense or tedious is a judgement.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Which perspective and movement model the game has; genre recipes | `unity-gameplay` |
| Baking a NavMesh, agent types, links, obstacles, carving, agent and Animator coupling | `unity-navigation` |
| A* over cells, range floods, cell line of sight, occupancy, turn order | `unity-2d-grid` |
| The 2D motors, grounding, the Animator bridge | `unity-2d-controller` |
| The 3D character body, grounding and slopes | `unity-3d-controller` |
| Damage, hitboxes, attack windows, knock-back, projectiles | `unity-combat` |
| Doors, switches, pickups, prompts | `unity-interaction` |
| Pools, scene loading, pause, saving which sentries are alive | `unity-scene-flow` |
| Hit-stop, flashes, particles, the alert sound | `unity-game-feel` |
| A cast or a trigger that does not fire, in 3D · in 2D | `unity-physics-3d` · `unity-physics-2d` |
| Animator graphs and events | `unity-animation` |
| The probe, situations and journeys this skill's checks rely on | `unity-play-harness` |
| Frame time and counters | `unity-profiling` |
| Reading input for the player | `unity-input` |

Learned behaviour, planners and navigation for flying or swimming volumes are different tools:
this skill is the hand-written brain most games ship, and the discipline that keeps it cheap.
