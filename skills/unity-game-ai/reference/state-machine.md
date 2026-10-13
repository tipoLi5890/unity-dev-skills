# State machine — states as objects, transitions on a decision tick

> Part of the `unity-game-ai` skill. `resources/StateMachine.cs` in full: what a state owns, why
> transitions are data evaluated on a slower clock than the state's own tick, what the blackboard
> is for, how the sentry's four states are wired, and the three kinds of hysteresis that stop a
> state flickering. Worked setting: the **gate room** — a sentry at its post, a wall, a runner.

## 1. Two clocks

```csharp
void FixedUpdate()
{
    float dt = Time.fixedDeltaTime;
    if (_clock.Due(dt)) { Perceive(); _machine.Decide(); }   // 10 Hz: may change state
    _machine.Tick(dt);                                       // every step: never changes state
}
```

| Call | Rate | Does | Costs |
|---|---|---|---|
| `Decide()` | The decision tick: 0.1 s (10 Hz); 0.2 s (5 Hz) for anything off screen | Asks each transition out of the current state, in the order added; the first that holds fires | A handful of comparisons on the blackboard |
| `Tick(dt)` | Every simulation step | Runs the current state: timers, an arrival check, a destination at a re-path interval | What the state does — keep it to arithmetic |

Why two: a transition asks "has the world changed enough to do something else", and the world
of a sentry changes a few times a second. Asked every frame, the answer is the same fifty-nine
times and costs a perception pass each time. A timer or an arrival check, in contrast, is wrong
if it runs late — a wait of 1 s measured at 10 Hz is 1.0 to 1.1 s.

`Decide` fires **at most one** transition per call. A state entered on this tick is therefore
current for at least one whole interval, which puts a floor of 0.1 s under any flicker and makes
every state visible in a timeline sampled per frame.

`DecisionClock` carries a phase. `SentryBrain` gives each sentry one of five phases, so
sentries placed together decide on different steps and the crowd's cost is spread, not stacked.

## 2. What a state owns

```csharp
public interface IState<TContext>
{
    void Enter(TContext context);
    void Tick(TContext context, float dt);
    void Exit(TContext context);
}
```

| A state owns | A state does not own |
|---|---|
| What happens while it is current: the request to the mover, its own timers | When it ends — that is a transition |
| Its private memory: how long it has waited, when it last asked for a path | Facts about the world — those are on the blackboard |
| Undoing itself in `Exit`: stop the mover, clear its flags | Knowledge of which state comes next |

A state that calls `machine.Go("Chase")` from its own `Tick` has taken a transition inside
itself: the graph is no longer readable from the list of `AddTransition` calls, and the change
happens on the step clock, not the decision clock. Set a fact on the blackboard and let a
transition read it — `ReturnState` sets `returned`, and `Return → Patrol` is `c => c.Board.returned`.

`Enter` and `Exit` are where one-off requests go. `SuspiciousState.Enter` stops the mover once;
`ChaseState.Exit` stops it, zeroes the alert and forgets the last sighting, so the walk home
starts calm whichever transition ended the chase.

## 3. The blackboard

The blackboard is everything transitions and states read, written in one place — perception,
on the decision tick.

```csharp
public sealed class SentryBlackboard
{
    public float now;
    public Vector3 home, homeFacing;
    public int waypoint;
    public SightResult sight;        // why the target is or is not seen
    public bool sees;
    public float targetDistance;
    public float alert;              // 0..1
    public TargetMemory memory;      // last-seen position and when
    public Vector3 interest;         // where Suspicious looks
    public bool returned;
}
```

- **Typed fields, not a string dictionary.** `board.alert` misspelt is a compile error;
  `board["alrt"]` is a sentry that never chases. A dictionary earns its place only when the keys
  are authored outside code, which is when a behaviour-tree package is the right tool.
- **Transitions read the blackboard and nothing else.** No cast, no `target.position`, no
  `Time.time` — `now` is on the board. A condition that does its own perception runs once per
  transition per tick and is invisible to the cast budget.
- **One writer per field.** Perception writes `sees`, `alert`, `memory`; a state writes only the
  flags it owns. Two writers of `alert` is the same bug as two writers of a transform.
- **Keep the reason, not only the answer.** `sight` says `OutOfRange`, `OutOfCone`,
  `OutOfTerritory` or `Blocked`. Registered with the probe, "it ignored me" names its own cause.

## 4. The sentry's graph

```
            alert > 0                  sees and alert = 1
  Patrol ─────────────► Suspicious ─────────────────────► Chase
    ▲                    │    ▲                             │
    │ returned           │    │ alert > 0                   │ last sighting older than memory,
    │        alert = 0   ▼    │                             │ or outside the leash
    └──────────────────  Return ◄───────────────────────────┘
```

```csharp
_machine.AddTransition(Patrol, Suspicious, c => c.Board.alert > 0f);
_machine.AddTransition(Return, Suspicious, c => c.Board.alert > 0f);
_machine.AddTransition(Suspicious, Chase,  c => c.Board.sees && c.Board.alert >= 1f - 1e-4f);
_machine.AddTransition(Suspicious, Return, c => c.Board.alert <= 0f);
_machine.AddTransition(Chase, Return,      c => c.Board.memory.Expired(c.Board.now, c.memorySeconds)
                                             || !c.InTerritory(c.Board.memory.position, true));
_machine.AddTransition(Return, Patrol,     c => c.Board.returned);
```

| State | `Enter` | `Tick` | Ends when |
|---|---|---|---|
| Patrol | Head for the current waypoint, or the post | On arrival wait `waitSeconds` (1 s), advance; with no waypoints, turn back to the post's facing | Anything raises the alert |
| Suspicious | Stop | Turn towards the point of interest at 360°/s | 0.4 s of sight fills the alert → Chase; the alert drains → Return |
| Chase | — | Every 0.25 s, ask the mover for the **last-seen** position at chase speed; arrived and blind, sweep the facing at 90°/s | The last sighting is 3 s old, or lies outside the leash |
| Return | Head for the waypoint it left | Flag arrival | Arrived → Patrol; a fresh sighting → Suspicious |

Order is priority: `AddTransition` calls are evaluated top to bottom, so put the urgent one
first. `AddAnyTransition("Stunned", c => c.Board.stunned)` leaves every state except its own
target — the form for a hit reaction, a death, the run ending — without one arrow per state.

## 5. Hysteresis — three forms, use at least one per transition pair

A pair of transitions `A → B` and `B → A` on one threshold flips whenever the value sits on it.
A runner standing 6.0 units from a sentry with a 6-unit range is seen and lost ten times a
second, and the sentry twitches. Every pair in the graph has a guard:

| Form | In the sentry | General rule |
|---|---|---|
| **Two thresholds** | Notice inside 6 units and 70°; keep out to 7.5 units and 100° (`SightCone.keepRange`, `keepAngle`). Notice inside 90% of the leash; keep to all of it | The exit threshold is 20–40% looser than the entry |
| **A meter** | `alert` fills at `1 / reactionSeconds` per second of sight and drains at `1 / calmSeconds`. One blocked tick costs 0.07 of it, not the chase | Integrate a noisy signal; transition on the integral |
| **A dwell time** | `AddTransition(from, to, when, minTimeInFrom)`; and one transition per decision tick is a built-in dwell of 0.1 s | A state must have been current for N seconds before its exits are asked |

Keep `calmSeconds` no longer than `memorySeconds`, and the leash at least twice the sight range:
a chase that the leash ends inside sight range is noticed again from where it stopped.

**Reading a flicker.** `StateMachine.Changes` counts state changes, and the sentry raises
`StateChanged` on each one. Count them into the probe (§6); a sentry whose count climbs by more
than about two a second is flapping, and the timeline's `sentry` column
shows between which two states. The fix is always one of the three rows above on that pair —
never a longer decision interval, which slows the flicker without removing it.

## 6. Debugging by the state name

```csharp
GameProbe.Register("sentry", () => sentry.StateName);
GameProbe.Register("sentryAlert", () => sentry.Alert);
GameProbe.Register("sentrySight", () => sentry.Board.sight.ToString());
int changes = 0;
sentry.StateChanged += (from, to) => changes++;
GameProbe.Count("sentryChanges", () => changes);
```

| Report | Read |
|---|---|
| "It sometimes ignores me" | `sentrySight` at the samples where the runner stood in view: `OutOfCone` is facing, `Blocked` is a cover layer, `OutOfTerritory` is the leash, and `Seen` with `sentry` still Patrol is the cast budget — check `PerceptionBudget.Deferred` |
| "It twitches" | `sentry` alternating between two names; §5 |
| "It chases forever" | `sentry` stays Chase with `sentrySight` not `Seen`: memory is being refreshed by something other than sight — a second writer of `memory` |
| "It reacts late" | Time from the first `Seen` sample to the first non-Patrol one. Over one decision interval plus a step: the clock, or a refused cast |

The state is a `string` on purpose. An `enum` needs a table to print and a recompile to add a
state; the names are compared only on a state change and in tests, never per frame in a hot
loop — the machine works on indices internally.

## 7. A state machine without a scene

`StateMachine<TContext>` is plain C#, so a graph can be tested in an edit-mode test with a fake
context and no frame:

```csharp
var board = new SentryBlackboard();
var machine = new StateMachine<SentryBlackboard>(board);
machine.Add("Patrol", new DelegateState<SentryBlackboard>());
machine.Add("Suspicious", new DelegateState<SentryBlackboard>());
machine.AddTransition("Patrol", "Suspicious", b => b.alert > 0f);
machine.AddTransition("Suspicious", "Patrol", b => b.alert <= 0f, minTimeInFrom: 0.5f);
machine.Start("Patrol");

board.alert = 0.25f; machine.Decide();
Assert.AreEqual("Suspicious", machine.Current);
board.alert = 0f; machine.Tick(0.1f); machine.Decide();
Assert.AreEqual("Suspicious", machine.Current);            // the dwell time holds it
machine.Tick(0.5f); machine.Decide();
Assert.AreEqual("Patrol", machine.Current);
```

That is the cheapest test of a graph; the journey in `templates/SentryJourneyTest.cs` is the test
of the graph, perception and mover together.

## 8. When the graph outgrows the file

| Sign | Move to |
|---|---|
| The same three states appear inside two others (a patrol that can be interrupted by reload, flee, call for help) | A hierarchy: a state whose `Tick` runs its own `StateMachine`, entered and exited with it |
| More transitions than states squared can be read; priorities argued about | A behaviour tree — `reference/behaviour-tree.md` |
| "Which of six things should it do" with no fixed order | A utility score per option — the method in `reference/tactics-ai.md` works in real time too, on the decision tick |

## Where each need is answered

| Need | Answer |
|---|---|
| What perception writes on the blackboard | `reference/perception.md` |
| What Patrol, Chase and Return ask of the mover | `reference/patrol-and-chase.md` |
| The Animator shows the state, one writer per parameter | `unity-animation` → `reference/parameter-contract.md` |
| Registering values, reading a timeline | `unity-play-harness` → `reference/probe-contract.md` |
| A game-wide state machine: menu, playing, paused | `unity-scene-flow` → `reference/game-state-and-pause.md` |
