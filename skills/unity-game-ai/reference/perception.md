# Perception — a cone as three tests, casts on a budget, hearing as events, memory with an age

> Part of the `unity-game-ai` skill. `resources/Perception.cs` and `resources/Perception2D.cs`,
> line by line: what "the sentry sees the runner" costs and in which order to pay it, how a
> crowd shares a cap on casts, why hearing is never polled, and what a sentry is allowed to know
> about a runner it can no longer see. Worked settings: the **gate room** (3D, ground on XZ) and
> the **depot** (2D from above, on XY).

## 1. Seeing is three tests, cheapest first

| Order | Test | Cost | Rejects |
|---|---|---|---|
| 1 | **Distance**: squared distance against squared range | Three multiplies | Everything far away — almost every sentry, almost every tick |
| 2 | **Angle**: dot of the facing and the direction to the target, against the cosine of half the cone | One square root | Everything behind and beside |
| 3 | **Line of sight**: one linecast against the cover layers | A physics query | Only what stands behind cover |

```csharp
SightResult result = cone.Covers(eye, facing, targetPoint, Vector3.up, tracking);   // tests 1 and 2
if (result == SightResult.Seen)
{
    if (!PerceptionBudget.TryTake()) return false;        // keep the last answer, ask next step
    if (!lineOfSight.Clear(eye, targetPoint)) result = SightResult.Blocked;         // test 3
}
```

- **Squared distance, cosine of the half angle.** No `Vector3.Distance`, no `Vector3.Angle`:
  the first hides a square root on every rejection, the second an `acos`.
- **The cast is last and conditional.** A sentry whose target is out of range or behind it
  spends nothing. In a level of forty sentries, a handful are in a position to cast on any tick.
- **Flatten onto the play plane.** `Covers` takes the plane's normal — `Vector3.up` for 3D
  ground, `Vector3.forward` for 2D on XY — and ignores height along it, so a runner on a step
  or a crate is not "above the cone". Pass `Vector3.zero` only for something that looks up and
  down: a turret on a wall, a drone.
- **The result is a reason.** `OutOfRange`, `OutOfCone`, `OutOfTerritory`, `Blocked`, `Seen`.
  Put it on the blackboard and in the probe; "it ignored me" then names its own cause.

## 2. The cone's numbers

| Field on `SightCone` | Start | Meaning |
|---|---|---|
| `range` | 6 | Notice inside this |
| `angle` | 70° | Full angle, centred on the facing |
| `keepRange` | 7.5 | Keep a target already noticed out to this |
| `keepAngle` | 100° | And inside this |
| `closeRange` | 1 | Inside this the angle is ignored — the cast is not |

- **Range fits inside the camera.** In the depot the view is 20 × 11.25 units; a 6-unit range
  means the player can always see a sentry that can see them. A range longer than half the
  view's short side is an off-screen death.
- **Two sets, always.** `tracking` selects the keep numbers. With one set, a runner on the edge
  of the cone is seen and lost on alternate ticks — `reference/state-machine.md` §5.
- **`closeRange` is the proximity sense.** A runner who brushes the sentry's back is noticed.
  Cover still hides them: the cast runs.
- **A wider, shorter second cone** is peripheral vision: test it only when the first fails, and
  fill the alert at half the rate from it. It costs one more dot product and no more casts.

## 3. The cast

One segment, from the sentry's eye to a point on the target, against cover only.

| | 3D — the gate room | 2D — the depot |
|---|---|---|
| Call | `Physics.Linecast(eye, point, blockers, QueryTriggerInteraction.Ignore)` | `Physics2D.Linecast(eye, point, filter, hits)` with a `ContactFilter2D`, in `Perception2D.cs` |
| Clear means | Returns `false` | Returns 0 |
| Eye | Pivot + 1.6 units up (`eyeHeight`) | The pivot (`eyeHeight` 0) |
| Target point | Pivot + 1.0 up (`targetHeight`) — the chest, never the feet | The pivot |
| Triggers | Ignored by the last argument | Ignored by `filter.useTriggers = false`; the plain overload obeys `Physics2D.queriesHitTriggers`, which is on by default |
| The mask | Cover only: walls, shelving, closed gates | The same |

- **The mask is cover, and neither end is on it.** A sentry or a runner whose collider sits on
  a `blockers` layer hides the target behind itself and the sentry is blind. In 2D a cast that
  starts inside a collider on the mask reports it at once (`Physics2D.queriesStartInColliders`).
- **A feet-to-feet cast is blocked by every kerb.** Cast eye to chest in 3D. A low wall that
  hides a crouching runner is then a matter of `targetHeight`, changed by the stance.
- **One point is one cast.** Head, chest and feet is three; do it only for a game about partial
  cover, and stop at the first clear one.
- **A gate that opens changes sight.** Its collider leaves the cover layer when it opens, so the
  same cast sees through it — the gate's own code does that, `unity-interaction` →
  `reference/doors-and-switches.md`.
- **On a board, there is no cast.** Sight between cells is integer arithmetic and the same on
  every machine — `unity-2d-grid` → `reference/line-of-sight.md`.

A cast that misses what is plainly in the way, or hits the caster: `unity-physics-3d` →
`reference/queries.md`, `unity-physics-2d` → `reference/queries-2d.md`.

## 4. The budget

Per sentry, per second:

| Design | Range and angle tests | Casts, worst case |
|---|---|---|
| Every frame at 60 fps | 60 | 60 |
| Every decision tick at 10 Hz | 10 | 10 |
| The same, off screen at 5 Hz | 5 | 5 |

Forty sentries that all see the runner cast 2,400 times a second the first way and 400 the
second. Three mechanisms keep even that flat:

1. **The tick.** `decisionInterval` 0.1 s. Nothing a player can perceive depends on noticing
   in 16 ms instead of 100.
2. **The stagger.** `DecisionClock` starts each sentry at one of five phases, so on a 50 Hz step
   one fifth of the crowd decides on each step instead of all of it on one.
3. **The cap.** `PerceptionBudget.CastsPerStep` (8) is shared by every agent. `TryTake()`
   returns false when the step's casts are spent; the sentry keeps its last answer, leaves its
   decision pending and asks again on the next step. Eight casts a step is 400 a second — forty
   sentries all in sight at 10 Hz — and a worse case is spread over more steps, not dropped.

```csharp
GameProbe.Count("castsDeferred", () => PerceptionBudget.Deferred);
```

`Deferred` climbing slowly under load is the budget working. `Deferred` climbing every step
with a small crowd means something casts outside the tick — grep for `Linecast` and `Raycast`
in the enemy scripts and expect to find them only behind `TryTake`.

**Lower the rate with distance.** A sentry three rooms away does not need 10 Hz:

```csharp
float d2 = (sentry.transform.position - runner.position).sqrMagnitude;
sentry.decisionInterval = d2 > 30f * 30f ? 1f : d2 > 15f * 15f ? 0.2f : 0.1f;
```

Run that from one manager once a second over the whole list, not from each sentry. Beyond the
distance at which nothing can matter, disable the component — the spawner's live cap
(`reference/spawners-and-waves.md`) is the other half of the same idea.

## 5. Hearing

Hearing is an event with a radius. The thing that makes the sound says so once; each listener
does one squared-distance test in the handler and stores the result for its next decision tick.

```csharp
NoiseEvents.Emit(runner.position, 8f, team: 0);      // the launch
```

| Source in the courier run | Radius |
|---|---|
| Walking | 0 — emit nothing |
| Running flat out | 4, at most twice a second |
| The launch | 8 |
| A pickup dropped | 5 |
| A gate opening | 12 |

- **Never poll.** "Is the runner making noise" asked by every sentry every tick is the frame
  cost hearing was meant to avoid. The emitter knows when it made a sound.
- **A noise is a place, not a target.** `SentryBrain` raises the alert to `heardAlert`
  (0.5), turns to look, and chases only if it then sees. A sentry that runs at every sound walks
  into the runner without ever having to find them.
- **Rate-limit at the source.** Footsteps emit at most twice a second; a held action emits on
  the press.
- **Teams.** `NoiseEvent.team` is who made it; a listener ignores its own. The runner is 0 and
  sentries are 1 in the worked files.
- **Walls.** The default ignores them: sound goes round corners, and it is cheap. For walls that
  muffle, spend one budgeted cast in the decision tick and halve the radius when it is blocked —
  never a cast inside the event handler, where forty listeners would run forty at once.
- **`hearingScale`** per sentry: 0 is deaf, 1.5 is alert. Difficulty settings change this and
  `reactionSeconds` before they change health.

## 6. Memory

```csharp
if (b.sees) b.memory.Remember(target.position, b.now);
// …
bool gaveUp = b.memory.Expired(b.now, memorySeconds);     // true when nothing is remembered
```

`TargetMemory` is a position and a time. It is the only thing a sentry knows about a runner it
cannot see.

| Rule | Why |
|---|---|
| Chase `memory.position`, never `target.position` | The second is the game's state, not the sentry's knowledge. The player ducks behind shelving and the sentry turns the corner straight at them: that reads as cheating because it is |
| Memory lasts `memorySeconds` (3) from the **last sighting** | Each seeing tick refreshes it; the clock starts when sight breaks |
| At the remembered position, look around | `ChaseState` sweeps the facing at 90°/s once it arrives blind; the runner hiding just round the corner is found by sight, fairly |
| When it expires, forget and go home | `ChaseState.Exit` calls `Forget()` and zeroes the alert |

**A fair guess beyond the last position**: remember the runner's velocity with the position and
head for `position + velocity × min(age, 1 s)`. One second of prediction reads as a sentry that
saw which way the runner went; more reads as tracking through walls.

## 7. More than one target

`SentryBrain` watches one `Transform`. For several candidates — two runners, decoys, a
rival team — keep a registry the candidates add themselves to, and choose on the decision tick:

```csharp
// Nearest candidate inside the cone gets this tick's one cast; the rest wait their turn.
Transform best = null; float bestSqr = float.PositiveInfinity;
foreach (Transform candidate in Candidates.OfTeam(0))
{
    float sqr = (candidate.position - eye).sqrMagnitude;
    if (sqr >= bestSqr) continue;
    if (cone.Covers(eye, facing, candidate.position, up, candidate == current) != SightResult.Seen) continue;
    best = candidate; bestSqr = sqr;
}
if (best != null && best != sentry.target) sentry.SetTarget(best);   // SetTarget forgets the memory
```

- One cast per sentry per tick, whatever the number of candidates.
- Switch only when the choice changes: `SetTarget` clears the last sighting, so calling it every
  tick with the same runner wipes the memory the chase runs on.
- Pass `tracking` true only for the current target, so it is kept in preference to a new one at
  the same distance — target choice needs hysteresis like everything else.
- Never `FindObjectsByType` on the tick: the registry is a static list written in `OnEnable`
  and `OnDisable`.

## 8. Draw what is tested

`SentryBrain.OnDrawGizmosSelected` draws the cone from `sight.range` and `sight.angle` and
the current facing. Whatever the player sees — a mesh fan, a projector, a 2D light — reads the
same two fields:

```csharp
coneLight.pointLightOuterRadius = sentry.sight.range;       // a Light2D of type Point
coneLight.pointLightOuterAngle  = sentry.sight.angle;
coneLight.transform.up = sentry.Facing;                     // XY: the light points along its up
```

A cone drawn at 90° and tested at 70° generates reports of being seen "from outside the cone"
that no code change fixes. Setting up the light: `unity-2d-rendering` → `reference/lights-2d.md`.

## 9. Checks

| Check | How |
|---|---|
| Not seen behind cover or outside the cone | `templates/SentryJourneyTest.cs`, first test; `SENTRY_JOURNEY_BREAK=los` and `=cone` each turn it red |
| Noticed within one decision tick | The second test compares the sentry's state with a visibility flag the test computes itself from the room |
| The cast is behind the budget | `PerceptionBudget.CastsPerStep = 0` in a scratch run: no sentry may ever leave Patrol by sight |
| The decision rate is what was set | `sentry.Decisions` over elapsed time: 10 per second at 0.1 s. Lower means refused casts |
| Cover layers | `sentrySight` in the probe reads `Blocked` with the runner in the open: something on the mask stands between them — usually the runner's own collider |

## Where each need is answered

| Need | Answer |
|---|---|
| What the alert and the memory drive | `reference/state-machine.md` |
| What the sentry does at the last-seen position | `reference/patrol-and-chase.md` |
| Casts, filters, a query that misses, in 2D | `unity-physics-2d` → `reference/queries-2d.md` |
| The same in 3D | `unity-physics-3d` → `reference/queries.md` |
| Layers for cover, runner, sentries | `unity-physics-2d` → `reference/layers-and-matrix.md` |
| Sight between cells | `unity-2d-grid` → `reference/line-of-sight.md` |
| Who can damage whom, by team | `unity-combat` → `reference/hit-and-hurt-layers.md` |
| Frame time with a crowd | `unity-profiling` → `reference/where-the-time-goes.md` |
