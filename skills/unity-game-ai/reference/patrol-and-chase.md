# Patrol and chase — requests to a mover, at an interval, with a way home

> Part of the `unity-game-ai` skill. What the sentry's four states ask of `IMover`, and when:
> waypoints and waits, a chase that re-paths on a timer towards where the runner was seen, a
> leash, the search at the end of a lost chase, and the line where a chase becomes an attack.
> Then the adapters that put a `NavMeshAgent`, a 2D motor or a cell stepper behind the same
> six members. Worked settings: the **gate room** (3D) and the **depot** (2D from above).

## 1. The seam

```csharp
public interface IMover
{
    Vector3 Position { get; }
    Vector3 Velocity { get; }
    bool Arrived { get; }
    void MoveTo(Vector3 destination, float speed, float stoppingDistance);
    void Stop();
    void Face(Vector3 direction);
}
```

| The brain | The mover |
|---|---|
| Says where, how fast, and how close is close enough | Decides the path, the steering, the collision |
| Reads `Position`, `Velocity`, `Arrived` | Is the only writer of the transform |
| Calls `MoveTo` on entering a state and at a re-path interval | Ignores a destination that has not moved |
| Keeps a facing for its cone | Shows that facing while it stands; turns itself while it moves |

`SentryBrain` finds the mover with `TryGetComponent` in `Start` and disables itself with an
error when there is none: an enemy with no transform owner is a bug, not a default.

## 2. Patrol

| Number | Default | Notes |
|---|---|---|
| `waypoints` | Empty — the sentry holds its post | Visited in order, looping. Transforms, so a designer drags them |
| `waitSeconds` | 1 | At each waypoint. 0 makes a walk that never pauses |
| `patrolSpeed` | 2 | Under half the runner's 5: a patrol is something to slip past |

- **Issue the waypoint once**, on entering Patrol and after each wait. The mover holds it.
- **Arrival is the mover's word.** `Arrived` on a `NavMeshAgent` must check `pathPending`
  first — `remainingDistance` reads 0 before planning starts — which is why the brain does not
  compute its own distance. The same guard is in `unity-navigation` → `reference/recipes.md` §3.
- **A post has a facing.** With no waypoints, Patrol turns the sentry back to the facing it
  started with (`Board.homeFacing`), so a guard returning from a chase looks down its corridor
  again and not at the wall it arrived facing.
- **Ping-pong routes** (A, B, C, B, A): list the waypoints that way. A flag for it is one more
  thing to get wrong at the ends.
- **A patrol that waits at every waypoint** wants the agent to brake on arrival, which is the
  agent's default. A patrol that flows through its waypoints (`waitSeconds` 0) wants
  `autoBraking` off — `unity-navigation` → `reference/recipes.md` §3.
- **Return goes to the waypoint the sentry was heading for**, not to the nearest and not to the
  first: `Board.waypoint` is not touched by the chase. The route resumes where it broke.

## 3. Chase

```csharp
public void Tick(SentryBrain c, float dt)
{
    _untilRepath -= dt;
    if (_untilRepath <= 0f)
    {
        _untilRepath = c.repathInterval;                                       // 0.25 s
        c.Mover.MoveTo(c.Board.memory.position, c.chaseSpeed, c.stoppingDistance);
    }
    …
}
```

| Number | Default | Decides |
|---|---|---|
| `chaseSpeed` | 4 | Under the runner's 5: sight can be broken by running. Over it, only cover works |
| `repathInterval` | 0.25 s | How stale the destination may be. At 5 units/s the runner moves 1.25 units between paths |
| `stoppingDistance` | 1 | Where the sentry stands to attack; inside `attackRange` |
| `leashDistance` | 15 | How far from home a target may be and still be chased |

- **Re-path on a timer and on movement, never every step.** A destination issued each step
  makes a `NavMeshAgent` discard its corridor and plan again each step — the pause at every
  corner. `NavMeshAgentMover` also drops a destination within `reissueDistance` (0.5) of the one
  it holds, so a runner standing still costs no planning at all.
- **The destination is `memory.position`.** While the runner is seen that is refreshed every
  decision tick and is the runner's position 0.1 s ago; once sight breaks it stops moving, and
  the sentry runs to where the runner disappeared — `reference/perception.md` §6.
- **Speed is the fairness dial.** 4 against 5 opens a 1 unit/s gap: a runner seen at 4 units is
  out of the 7.5-unit keep range in 3.5 s on open ground. Faster sentries need cover in the level.
- **A chase the mover cannot complete** — a partial path, a gate in the way — still ends:
  `Arrived` comes true at the nearest reachable point, the sentry is blind there, and memory
  runs out. A sentry stuck against a closed gate for exactly `memorySeconds` is this rule
  working. Opening the gate is the gate's business: `unity-interaction` →
  `reference/doors-and-switches.md`.

### The leash

Two radii from `Board.home`, one number:

| Radius | Used for |
|---|---|
| 90% of `leashDistance` (13.5) | Noticing: a target outside it does not fill the alert |
| 100% (15) | Keeping: a chase ends when the last-seen position is outside it |

With one radius, a runner standing on the boundary drags the sentry out, releases it, and
catches it again every few seconds. With two, the runner must come 1.5 units back inside to be
noticed again. `leashDistance` 0 turns the leash off — for a pursuer that should follow across
the level, which then needs somewhere to be when the chase ends.

## 4. Losing the target, and the search

| Moment | What happens | Where |
|---|---|---|
| Sight breaks | `sees` false; the alert starts to drain; `memory` keeps the last position and time | Perception, on the decision tick |
| Still chasing | The mover carries on to the last-seen position | `ChaseState.Tick` |
| Arrived, blind | The facing sweeps at `searchTurnSpeed` (90°/s): a quarter turn each second, a full look round in 4 s | `ChaseState.Tick` |
| The runner is seen again | Memory refreshes; the chase continues with no reaction delay — the sentry is already alert | Perception |
| `memorySeconds` (3) after the last sighting | Chase → Return; the alert is zeroed and the memory forgotten | The transition, then `ChaseState.Exit` |
| Home | Return → Patrol | `ReturnState` flags arrival |

A wider search — three points round the last-seen position, visited in turn — is a state of its
own between Chase and Return, with its own budget:

```csharp
// SearchState.Enter: three points on a ring of 3 units, clockwise from the last heading.
for (int i = 0; i < 3; i++)
    _points[i] = c.Board.memory.position + Quaternion.AngleAxis(120f * i, up) * c.Facing * 3f;
// Tick: MoveTo(_points[_index]) at patrol speed; on Arrived wait 1 s, advance; after the third, flag done.
```

Add it when playtests say sentries give up too easily; the journey's third test then needs its
window widened by the search's duration, which is the point of having the number in a test.

## 5. The hand-off to an attack

```csharp
sentry.AttackRangeEntered += target => attack.Begin(target);     // the game's combat code
…
if (!sentry.InAttackRange) attack.Cancel();
```

`InAttackRange` is true while the target is **seen** and no farther than `attackRange` (1.5).
It is computed on the decision tick; `AttackRangeEntered` fires once on the tick it becomes true.

| This skill | Combat |
|---|---|
| Gets the sentry to `stoppingDistance` and keeps it facing the target | Decides what an attack is, its wind-up, its window and its recovery |
| Says "in range, and seen" | Deals damage, once per swing |
| Keeps chasing if the target leaves | Cancels or commits |

- `attackRange` is larger than `stoppingDistance`, or the sentry arrives and is never in range.
  The gap (0.5) is the attack's reach tolerance.
- An attack that roots the sentry calls `Mover.Stop()` through a state of its own — add an
  `Attack` state with `AddAnyTransition` out of it on a stun — and never by disabling the mover.
- Windows, hit detection and one damage event per swing: `unity-combat` →
  `reference/attack-windows.md` and `unity-combat` → `reference/damage-contract.md`.

## 6. Adapters

### NavMeshAgent — 3D

`resources/NavMeshAgentMover.cs`, beside a `NavMeshAgent`. The agent owns the transform; the
adapter sets `speed`, `stoppingDistance` and a destination, guards every call with
`isOnNavMesh`, and turns the body to the sentry's facing only while the agent stands. Baking
the surface, agent radius and height, an agent that will not move: `unity-navigation`. A
sentry with a walk cycle needs the agent and the Animator coupled — `unity-navigation` →
`reference/recipes.md` §5.

### The motor seen from above — 2D

`TopDownMotor2D` reads `RunInput` from the enabled source on its object. The sentry's mover is
that source: it writes a direction where the player's reader would write the stick.

```csharp
// TopDownSentryMover.cs — beside TopDownMotor2D, in place of a RunInputReader.
[RequireComponent(typeof(TopDownMotor2D))]
public sealed class TopDownSentryMover : RunInputSource, IMover
{
    TopDownMotor2D _motor;
    Rigidbody2D _body;
    Vector2 _destination;
    float _stop;
    bool _moving;

    public Vector3 Position => _body.position;
    public Vector3 Velocity => _body.linearVelocity;
    public bool Arrived => !_moving;

    void Awake()
    {
        _motor = GetComponent<TopDownMotor2D>();
        _body = GetComponent<Rigidbody2D>();
    }

    public void MoveTo(Vector3 destination, float speed, float stoppingDistance)
    {
        _destination = destination;
        _stop = Mathf.Max(stoppingDistance, 0.15f);      // never under the motor's own stopping slide
        _motor.speed = speed;
        _moving = ((Vector2)destination - _body.position).magnitude > _stop;
    }

    public void Stop()
    {
        _moving = false;
        SetMove(Vector2.zero);
    }

    public void Face(Vector3 direction) => SetAim(direction);     // shown when the motor has faceAim on

    void FixedUpdate()
    {
        if (!_moving) return;
        Vector2 to = _destination - _body.position;
        if (to.magnitude <= _stop) { Stop(); return; }
        SetMove(to.normalized);                           // the motor reads it on its next step
    }
}
```

The sentry now has the runner's acceleration, wall slide and knock-back for nothing, and one
writer of its body. This adapter walks straight at the destination; shelving in the way needs a
route — `reference/pathfinding-2d.md`. The motor: `unity-2d-controller` →
`reference/topdown-free.md`.

### The side-view motor — 2D under gravity

A sentry on a rooftop uses `PlatformerMotor2D` with its own rules where the player has
`PlatformerController2D`: walk towards the target's x, fall under gravity, stop at a ledge.

```csharp
// LedgeSentryMover.cs — beside PlatformerMotor2D, in place of PlatformerController2D.
[RequireComponent(typeof(PlatformerMotor2D))]
public sealed class LedgeSentryMover : MonoBehaviour, IMover
{
    public float gravity = 37.5f;
    [Tooltip("How far ahead of the feet the floor is looked for. Half the body width plus a little.")]
    public float ledgeProbe = 0.6f;

    PlatformerMotor2D _motor;
    readonly RaycastHit2D[] _hit = new RaycastHit2D[1];
    float _targetX, _speed, _stop, _fall;
    bool _moving;

    public Vector3 Position => _motor.Position;
    public Vector3 Velocity => _motor.Velocity;
    public bool Arrived => !_moving;

    void Awake() => _motor = GetComponent<PlatformerMotor2D>();

    public void MoveTo(Vector3 destination, float speed, float stoppingDistance)
    {
        _targetX = destination.x;                         // a walker follows along the roof, never up
        _speed = speed;
        _stop = Mathf.Max(stoppingDistance, 0.05f);
        _moving = Mathf.Abs(_targetX - _motor.Position.x) > _stop;
    }

    public void Stop() => _moving = false;
    public void Face(Vector3 direction) { }

    void FixedUpdate()
    {
        float dt = Time.fixedDeltaTime;
        float dx = _targetX - _motor.Position.x;
        if (_moving && Mathf.Abs(dx) <= _stop) _moving = false;
        float side = Mathf.Sign(dx);
        // The roof ends: stop at the edge. The sentry has "arrived" as far as it can go.
        if (_moving && _motor.Grounded && !FloorAhead(side)) _moving = false;

        _fall = _motor.Grounded ? 0f : _fall - gravity * dt;
        Vector2 v = _motor.Move(new Vector2(_moving ? side * _speed : 0f, _fall), dt);
        _fall = Mathf.Min(v.y, 0f);
    }

    bool FloorAhead(float side)
    {
        var filter = new ContactFilter2D();
        filter.SetLayerMask(_motor.solid | _motor.oneWay);
        filter.useTriggers = false;
        Vector2 from = _motor.Position + new Vector2(side * ledgeProbe, 0f);
        return Physics2D.Raycast(from, Vector2.down, filter, _hit, 1.5f) > 0;
    }
}
```

- Exactly one script calls `Move` — this one. Do not leave a `PlatformerController2D` on the
  sentry.
- Set the sentry's `plane` to XY and its cone's `angle` to taste: on a rooftop the cone is
  usually a strip along the roof, and `keepAngle` 360 lets a sentry keep a runner who jumps
  over it.
- Stopping at the ledge ends the chase by memory, 3 s later. A sentry that jumps gaps is a
  rule added here, with the reach table deciding which gaps — `unity-gameplay` →
  `reference/level-metrics.md`.
- Grounding, slopes and one-way roofs are the motor's: `unity-2d-controller` →
  `reference/platformer.md`.

### Cells

One step along a path of cells per request, the cell map told first: the adapter over
`GridStepMover` and `GridPathfinder` is in `reference/pathfinding-2d.md` §1. A turn-based
opponent does not chase at all — `reference/tactics-ai.md`.

## 7. Checks

| Check | How |
|---|---|
| The chase starts only after sight, and ends by memory | `templates/SentryJourneyTest.cs`, second and third tests |
| One writer of the sentry's transform | Grep the sentry's scripts for `transform.position =`, `linearVelocity =` and `MovePosition`: hits only inside the mover |
| Destinations are not issued every step | Count `SetDestination` calls per second with a counter in the adapter: about 4 in a chase, 0 standing |
| The runner can get away | A journey that runs the runner in a straight line from first sight: `sentry` reads Return within `(keepRange − seenDistance) / (5 − chaseSpeed) + memorySeconds` |
| The leash holds | Lead the sentry away from its post in a straight line: `sentry` reads Return on the tick the last-seen position passes 15 units from home, and does not read Chase again while the runner stands beyond 13.5 (`sentrySight` reads `OutOfTerritory`) |
| The sentry is never inside cover | Register the sentry as the probe's player in a second journey and assert `JourneyAsserts.NeverInside` (`JourneyInvariants2D.NeverInside2D` in the depot) — a mover that walks through walls is a mover bug |

## Where each need is answered

| Need | Answer |
|---|---|
| The states and their transitions | `reference/state-machine.md` |
| What "seen" and "last-seen" mean | `reference/perception.md` |
| Routes round shelving in 2D | `reference/pathfinding-2d.md` |
| Baking, agent settings, links across gaps | `unity-navigation` |
| Corner speed, patrol and click-to-move on an agent | `unity-navigation` → `reference/recipes.md` |
| The agent API that will not compile | `unity-navigation` → `reference/agent-api.md` |
| The free 2D motor and its knock-back | `unity-2d-controller` → `reference/topdown-free.md` |
| Which body the enemy should have | `unity-2d-controller` → `reference/model-choice.md` |
| The 3D body an enemy shares with the player | `unity-3d-controller` → `reference/model-choice.md` |
| Attack windows and damage | `unity-combat` → `reference/attack-windows.md` |
| Knock-back applied to a sentry | `unity-combat` → `reference/iframes-and-knockback.md` |
| A walk cycle that matches the sentry's speed | `unity-animation` → `reference/blend-trees.md` |
