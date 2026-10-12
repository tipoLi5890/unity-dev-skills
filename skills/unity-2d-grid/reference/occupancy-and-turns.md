# Occupancy and turns — who is where, who acts, and how to take it back

> Part of the `unity-2d-grid` skill. One map from cell to occupant, moves that resolve together,
> the sorting yard's push rule, a turn queue with initiative, and undo as a stack of reversible
> records. Code is in `resources/GridOccupancy.cs` and `resources/TurnQueue.cs`; both are plain
> C# and neither knows a scene exists.

## The rules never touch the engine

The board is a simulation: commands go in, state changes at once, and a description of what
changed comes out. The scene is a presenter that plays that description back over a few tenths
of a second. Nothing flows the other way.

```
RunInput ─► command ─► board.Step(dir) ─► StepRecord ─► presenter: tween Mover From→To,
                       (instant, total)                             tween Pushed To→Beyond
```

| The rules may | The rules may not |
|---|---|
| Read and write `GridOccupancy`, `TurnQueue`, their own fields | Read `transform.position`, `Time.time`, a collider, an `Animator` |
| Return records, raise plain C# events | Start a coroutine, wait for a tween, `await` an animation |
| Use `Vector3Int` as a value | Hold a `GameObject`, `Transform` or `MonoBehaviour` reference |

Occupants are **int ids**. The presenter keeps the only `Dictionary<int, Transform>`. That is
what lets a solver copy a board, a test build one in three lines, and a replay run with no scene.
Putting the rules in an assembly the compiler stops from seeing the engine is
`unity-game-brief` → `reference/sim-presentation-split.md`.

**Consequence for timing.** A piece "moving" for 0.12 s is, on the board, already there. A
second command arriving mid-tween is evaluated against the new board, which is correct; what the
presenter does with it (queue one, drop the rest) is `unity-2d-controller` →
`reference/grid-step.md`.

## One occupant map

```csharp
var yard = new GridOccupancy();
yard.AddWall(cell);
yard.Place(id, cell, pushable: false);   // throws on a wall, a taken cell, or a reused id
int who = yard.OccupantAt(cell);         // 0 = nobody
Vector3Int where = yard.CellOf(id);
bool free = yard.CanEnter(cell);         // no wall, no occupant, no reservation
bool moved = yard.TryMove(id, to);
yard.Remove(id);
```

It keeps two dictionaries, cell → id and id → cell, and every method updates both in the same
call, so they cannot disagree. Three rules follow:

- **One cell, one occupant.** Things that share a cell with a unit are not occupants: gates,
  hazards, slow ground and pickups that are *collected* (not pushed) are terrain sets —
  `HashSet<Vector3Int>` beside the map. In the sorting yard a pickup is pushed, so it is an
  occupant; in the depot it is collected, so it is terrain.
- **`Place` throws.** Two pieces on one cell at load is a level-data fault. Fail there, with
  the cell in the message, not three turns later as a unit that cannot be selected.
- **`CanEnter` is the delegate everything else wants.** It is the "can enter" of a cell mover
  and the core of a pathfinder cost: `(from, to) => yard.CanEnter(to) ? 1 : 0`.

A unit larger than one cell: give each cell of its footprint an id of its own and keep a
part → unit map in the board class. Move the parts with reserve-then-commit, leading part first,
so the unit never blocks itself.

## Push — the sorting yard's rule

One pickup, one cell, never into anything:

```csharp
Vector3Int to = GridCoords.Neighbour(shape, yard.CellOf(runnerId), direction);
Vector3Int beyond = GridCoords.Neighbour(shape, to, direction);
StepRecord step = yard.StepOrPush(runnerId, to, beyond);
```

| `to` holds | `beyond` | Result | Board |
|---|---|---|---|
| nothing | — | `Moved` | runner in `to` |
| a wall | — | `Blocked` | unchanged |
| a pushable occupant | free | `Pushed` | pickup in `beyond`, runner in `to` |
| a pushable occupant | wall, occupant or reserved | `Blocked` | unchanged |
| an occupant that is not pushable (a sentry) | — | `Blocked` | unchanged |

The caller computes both cells from the **same direction index**, which is why the rule is
identical on rectangular, isometric and hexagonal boards: on hexagons "the cell beyond" is the
next cell along the same cube direction, and `Neighbour` already knows that.

Variants, each a small change in the board class, not in the map:

| Variant | Change |
|---|---|
| Pickups slide until they hit something (ice) | After a `Pushed`, keep calling `TryMove(pushed, next)` along the direction; record the final cell |
| A row of pickups moves together | Walk along the direction collecting pushable occupants until a free cell or a blocker; move them far end first |
| Pull as well as push | A separate command: runner steps away, `TryMove` the pickup into the cell the runner left |
| A pickup on a gate cell locks | Remove it from the pushable set in the board class when it lands on a gate |
| Heavy pickups need two pushers | The board checks its own counter before calling `StepOrPush` |

**Blocked is a result, not an error.** Return the record anyway: the presenter plays a bump
animation toward `To`, and the journey asserts that neither the cell nor the transform changed.

## Reserve, then move

When several units move in the same instant — every sentry in one tick, or simultaneous turns —
moving them one by one makes the outcome depend on list order: sentry A is refused a cell that
sentry B is about to leave. Split it in two:

```csharp
// 1. Everyone claims, in initiative order. The first claim on a cell wins.
foreach (int id in order)
    if (!yard.TryReserve(id, Wanted(id))) Blocked(id);
// 2. Everything applies at once.
int moved = yard.Commit();
```

`TryReserve(id, to)` is refused when `to` is a wall, already claimed, or held by an occupant
that has not *already* claimed a move away. That last clause gives three properties for free:

- **A column advances together**: ask front to back, and each follower claims the cell the one
  ahead is vacating.
- **No swaps**: two units facing each other each need the other to have claimed first, so
  neither is granted. They both bump.
- **No overlaps**: `Commit` lifts every mover, then sets every mover down, so no intermediate
  board ever has two occupants in a cell.

Ask in the order the game promises (initiative, then id). Ask back to front and the column
moves one unit per tick like a traffic jam — a legitimate effect when it is chosen on purpose.

There is no cancelling a single reservation: a later claim may have been granted because of it.
`ClearReservations()` drops them all. Reservations are for one resolution step; never leave one
standing across a turn.

For real-time movement on a board (the runner and sentries stepping whenever their tween ends),
`TryMove` alone is enough: the board changes at the first instant of the step, so the
destination is taken before anyone else can ask for it.

## Turns

```csharp
var turns = new TurnQueue();
turns.Add(RunnerId, initiative: 12);
turns.Add(SentryA, 9); turns.Add(SentryB, 9);
turns.RoundStarted += round => { /* tick durations, spawn reinforcements */ };

int actor = turns.Begin();          // round 1; highest initiative first, ties to the lower id
…
actor = turns.Advance();            // end the current turn; past the last actor, a new round
```

| Event | Behaviour |
|---|---|
| Two actors with equal initiative | The lower id first, always. Nothing random decides order after set-up |
| `Remove(id)` of someone who already acted, or the one acting | Gone at once; the index steps back so the next `Advance` lands on the right actor |
| `Remove(id)` of someone still to act | Gone at once; their turn simply never comes |
| `Add(id, …)` during a round | Joins from the next round. A reinforcement never acts in the middle of someone's turn |
| `SetInitiative(id, …)` during a round | Applies from the next round; this round's order is a promise already shown in the HUD |
| `Peek(n)` | The actor `n` turns ahead, wrapping — for a turn-order strip |

If initiative is rolled, roll it once with the board's seeded random source when the unit is
added, and store the number. Order must be reproducible from the seed, or a journey cannot
replay a battle.

**Two shapes of turn**, both on this queue:

| Shape | How |
|---|---|
| Unit by unit (initiative order) | One actor per id, as above |
| Side by side (all of mine, then all of yours) | Two actors, the sides. Within a side's turn, each unit has a "has acted" flag in the board class, cleared in `RoundStarted` |

**A turn is a small state machine in the board**, not in the presenter: `AwaitingCommand` →
`Resolving` → `AwaitingCommand` or `TurnEnded`. The presenter may refuse *input* while its
tweens run; the board never waits. Register it for the harness:

```csharp
GameProbe.SetState(() => _board.Phase.ToString());
GameProbe.Register("turn", () => _board.Turns.Round);
GameProbe.Register("actor", () => _board.Turns.Current);
```

### Enemy turns

Decide on the board, then animate:

1. Flood the sentry's movement range (`GridPathfinder.Range`).
2. Score every reachable, stoppable cell with a plain function of the board — for example
   `−2 × distance to the runner + 5 if the runner is in reach from here − 3 if the cell is a
   hazard`.
3. Take the best score; break ties by the lower cost to reach, then by the lower cell
   (y, then x). A fixed tie-break is what makes the turn reproducible.
4. Apply the move and the action to the board and emit the records.

Resolve every sentry before any animation starts, then let the presenter overlap the tweens or
play them at a multiple. Ten sentries stepping four cells at 0.12 s a cell in strict sequence is
4.8 s of waiting per round.

## Undo

Undo is a stack of **what changed**, not snapshots of the board:

```csharp
readonly Stack<StepRecord> _undo = new Stack<StepRecord>();

if (step.Result != StepResult.Blocked) _undo.Push(step);     // on every successful step
…
if (_undo.Count > 0) yard.Revert(_undo.Pop());               // newest first, always
```

A `StepRecord` is two ids and three cells. Ten thousand of them is under half a megabyte, so
"unlimited undo within a level" needs no cap.

When a command changes more than a step does, make the command reversible instead of widening
the record:

```csharp
public interface IBoardCommand
{
    bool Do(YardBoard board);      // false: nothing changed, do not push
    void Undo(YardBoard board);    // exactly reverses Do, given the board Do left behind
}
```

| Rule | Why |
|---|---|
| A command stores what it needs to reverse itself **when it runs**, not when it is created | The pickup it will push is only known at `Do` |
| Undo restores **everything** the command touched: occupants, gates opened, counters, the turn index | A forgotten counter is "undo leaves the door open" |
| One player action is one stack entry | A push that triggers a slide and opens a gate is one composite command holding its parts, undone in reverse |
| Nothing random inside `Do` | Or undo then redo gives a different board. Draw random numbers before, store them in the command |
| Undo is a command to the board, not to the presenter | The presenter receives the reverted record and tweens backwards, or snaps |

**Redo** is a second stack: `Undo` pushes the command there, any new command clears it.

**Tactics undo** usually stops at information: a move can be taken back until it reveals
something (fog lifted, a trap sprung) or an action is committed. Mark such commands
`Irreversible` and clear the stack when one runs.

## Checks

- **EditMode**: `A_push_moves_one_pickup_one_cell_and_reverts_exactly`,
  `Reservations_resolve_together_and_never_swap` and
  `The_turn_order_is_by_initiative_then_id_and_survives_a_removal` in
  `resources/Tests/GridCoordsTests.cs`. Add one for your board class: apply a recorded
  solution, undo every step, and compare with the starting board cell by cell.
- **A journey over the sorting-yard situation**: after each scripted step, wait for the probe's
  `stepping` flag to clear, then assert the runner's transform is within 0.01 of
  `GetCellCenterWorld` of the cell the probe reports. A blocked step must change neither —
  `unity-play-harness` → `reference/journeys.md`.
- **Occupancy against the scene**, as a debug assertion in the presenter after every settled
  step: every id in the presenter's transform map is on the board, and no two transforms rest
  on the same cell centre.

## Traps

- **A second map.** "Enemies" in one dictionary and "crates" in another is how two things end
  on one cell. One map; kinds are a property of the id.
- **Updating occupancy when the tween ends.** For 0.12 s the destination looks free and a
  second unit takes it.
- **Deriving the cell from the transform on load or after undo.** The board is the source; set
  the transform from the cell.
- **Removing a dead unit from the scene and not from the map** (or the turn queue). The cell
  stays blocked by nobody. Remove from the board; the presenter reacts to the removal.
- **A turn that waits for an animation event.** If the clip is swapped or the event is cut, the
  game stops. The board advances; the presenter gates input on its own tweens with a timeout.
- **Undo implemented as "apply the opposite move".** Stepping back does not un-push a pickup.
  Revert the record.
