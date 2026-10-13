# Spawners and waves — a budget spent from a seed, where the camera is not looking

> Part of the `unity-game-ai` skill. `resources/WaveSpawner.cs` in full: a wave is a number of
> budget points spent on a table of entries, released one at a time at hidden spawn points, under
> a cap on how many are alive, from a seeded generator. Worked settings: the **depot**, where
> sentries arrive between the shelving, and the **lane run**, where hazards come down three lanes.

## 1. A wave is data

```csharp
[Serializable] public sealed class SpawnEntry      { public GameObject prefab; public int cost = 1, weight = 1, fromWave = 1; }
[Serializable] public sealed class WaveDefinition  { public int budget = 6; public float spawnInterval = 0.5f, restBefore = 3f; }
```

| Piece | Is | Not |
|---|---|---|
| **Entry** | A prefab, what it costs, how likely it is, the first wave it may appear in | A count per wave |
| **Wave** | A budget, a spawn interval, a rest | A list of exact spawns |
| **The table** | One list of entries for the whole level | One list per wave |

Authoring budgets and costs, not counts, is what lets one table serve every wave: wave 1 with a
budget of 6 is six sentries; wave 5 with 14 is some mix of sentries (cost 1) and heavy ones
(cost 3, `fromWave` 3) that nobody listed by hand. A new enemy is one new row.

Exact scripted waves still fit: give an entry `fromWave` equal to the wave it belongs to and a
weight high enough to dominate, or author `waves` with budgets that only one entry can spend.
For a wave that must be precisely "three sentries then one heavy", skip the planner and fill the
queue yourself — that is a set piece, not a wave.

## 2. Spending the budget

`WavePlanner.Fill(entries, wave, budget, random, into)` is plain C#:

1. Among entries whose `fromWave` has come and whose `cost` fits the budget left, sum the weights.
2. Draw one by weight; append its index; subtract its cost.
3. Repeat until nothing affordable is left. Return what could not be spent.

| Entry | cost | weight | fromWave |
|---|---|---|---|
| Sentry | 1 | 6 | 1 |
| Fast sentry | 2 | 3 | 2 |
| Heavy sentry | 3 | 1 | 3 |

With that table, budget 6 on wave 1 is always six sentries; budget 10 on wave 3 averages seven
spawns — 4.5 sentries, 1.9 fast ones, 0.55 heavy ones, with a heavy one in just under half the
waves. Because the planner has no scene, print the waves in an edit-mode test and read the mix
before anyone plays it:

```csharp
var random = new System.Random(12345);
var picks = new List<int>();
for (int wave = 1; wave <= 10; wave++)
{
    picks.Clear();
    int left = WavePlanner.Fill(entries, wave, 6 + 2 * (wave - 1), random, picks);
    TestContext.WriteLine("wave " + wave + ": " + string.Join(",", picks) + " left=" + left);
}
```

## 3. Pacing — a budget that grows

| Number | Default | Is |
|---|---|---|
| `firstBudget` | 6 | Wave 1 when no wave is authored |
| `budgetGrowth` | 2 | Added per generated wave: 6, 8, 10, 12 … |
| `spawnInterval` | 0.5 s | Between two spawns of a wave: a wave of 10 takes 5 s to arrive |
| `restBefore` | 3 s | The breath between waves |
| `waitForClear` | on | The rest starts only when the last spawn is gone |
| `endless` | on | After the authored waves, keep generating from the last one's numbers |

- **Linear growth, and a ceiling from the cap.** Growth of 2 a wave doubles the first wave by
  wave 4. Beyond what `liveCap` lets on the field, more budget only makes a wave longer — which
  is a pacing tool: late waves become sieges, not swarms.
- **Authored first, generated after.** Three hand-tuned `waves` teach the game; `endless` takes
  over with the last authored interval and rest and a budget that continues from the last one.
- **`waitForClear` off** makes waves overlap on a timer — pressure that does not wait for the
  player. Pair it with a `liveCap` the player can survive, because nothing else limits it.
- **Rest is where the player collects pickups and reads the room.** Under 2 s it is not a rest;
  over 6 s the game has stopped.
- **Difficulty is the budget, not the entry stats.** One number to scale, and the wave log shows
  what it produced.

## 4. Where: hidden spawn points

A spawn point is usable when it is **not in view** and **not next to the runner**:

```csharp
bool Hidden(Vector3 position)
{
    if (avoid != null && (position - avoid.position).sqrMagnitude < minDistance * minDistance) return false;
    if (hideFrom == null) return true;
    Vector3 v = hideFrom.WorldToViewportPoint(position);
    bool inView = v.z > 0f && v.x > -viewMargin && v.x < 1f + viewMargin && v.y > -viewMargin && v.y < 1f + viewMargin;
    return !inView;
}
```

| Number | Default | Why |
|---|---|---|
| `viewMargin` | 0.1 | A tenth of the screen beyond each edge still counts as visible: a sentry's body is wider than its pivot, and the camera moves |
| `minDistance` | 6 | The sentry's own sight range. Nearer, a spawn is an ambush with no counter |

- **A viewport test, not a renderer's `isVisible`.** The point has no renderer, and `isVisible`
  is also true for the Scene view's camera.
- **No valid point is a postponement, not a fallback.** The spawner counts it in `Postponed`,
  waits one interval and tries again. Spawning "at the least bad point" puts a sentry on screen.
  `Postponed` climbing without end means the level has no hidden point from where the runner
  stands — add points behind shelving, in side aisles, beyond doors.
- **Four to eight points round an arena**, so at least two are hidden from anywhere. In a level
  that scrolls, parent the points to a rig ahead of the camera, outside the margin.
- **A spawn point is on walkable ground.** On a NavMesh, a point off the surface produces an
  agent that never moves — `unity-navigation`. On a board, spawn on a free cell and tell the
  occupancy map — `unity-2d-grid` → `reference/occupancy-and-turns.md`.
- **Arrival is feedback.** A sentry that appears from a door, a hatch or the edge of the view
  reads as arriving; one that pops into an empty aisle reads as a bug even off screen, because
  the player turns round. The entrance effect: `unity-game-feel` → `reference/feedback-stack.md`.

**Lane run.** Spawn points are the three lane positions (x = −1.3, 0, 1.3) at a fixed distance
ahead of the runner, beyond the far edge of the view; `avoid` is unused and `hideFrom` is the
game camera. A lane that already has a hazard within the reaction distance is skipped by the
game's own rule in a `Create` hook that returns null — the spawner counts that as a postponement.

## 5. The live cap

`liveCap` (12) is the most spawns alive at once. A wave larger than the cap trickles: the next
spawn waits for a slot.

| The cap protects | Because |
|---|---|
| The frame | Each sentry is a decision tick, a mover and possibly a cast — `reference/perception.md` §4 |
| The player | Twelve sentries in a 20 × 11 unit view is already one per 18 square units |
| The pool | Its size is the cap, known before the level loads |

A slot frees in two ways, and both are needed:

```csharp
health.Died += () => spawner.Despawn(gameObject);    // told: removed through Remove, at once
```

and `Prune()`, which every step drops entries that are destroyed or inactive. An enemy removed
by a kill volume, a scene unload or a pool that was not told still frees its slot, so the cap
can never leak shut. Register the count: `GameProbe.Count("sentries", () => spawner.Live)` — a
journey can then assert `Never(s => s.CountOf("sentries") > 12)`.

## 6. Pooling

`Instantiate` and `Destroy` per enemy is a spike per spawn and garbage per death. The spawner
calls two delegates and does not know what is behind them:

```csharp
spawner.Create = (prefab, position, rotation) => pool.Take(prefab, position, rotation);
spawner.Remove = instance => pool.Return(instance);
spawner.Spawned += (instance, wave) =>
{
    var sentry = instance.GetComponent<SentryBrain>();
    sentry.SetTarget(runner);
    sentry.Restart();                  // a pooled sentry starts again from where it was placed
};
```

- Until they are assigned, `Create` is `Instantiate` and `Remove` is `Destroy` — correct, and
  fine for a prototype.
- **A pooled sentry must be reset.** State back to Patrol, alert and memory cleared, home
  re-read from where it was placed — or the third wave inherits the first wave's grudges.
  `SentryBrain` builds its machine in `Start`, which a pooled object runs once, so the
  `Spawned` handler calls `sentry.Restart()` after the pool has placed it; before the first
  `Start` the call does nothing, because `Start` does the same work.
- **Pool size is `liveCap`** per prefab that can fill a wave alone, warmed while the level loads.
- The pool itself, warm-up and what "returned" must undo: `unity-scene-flow` →
  `reference/pooling.md`.

## 7. Seeded, so a run repeats

`seed` (12345) feeds one `System.Random` that makes every choice the spawner makes: what a wave
contains and which hidden point each spawn uses.

- **Same seed, same waves.** What each wave contains depends on the seed alone.
- **Which point each spawn uses** also depends on which points were hidden, which depends on
  where the runner stood. A journey that drives the same scripted input gets the same points; a
  human replaying the seed gets the same waves at different doors.
- **`System.Random`, never `UnityEngine.Random`.** The engine's generator is one global stream
  shared with particles, audio and every other script; anything else drawing from it shifts
  every wave after.
- **One generator per system.** The spawner's does not serve loot or level generation; each has
  its own, seeded from the run's seed plus a constant.
- **Spawn on the fixed step.** `WaveSpawner` runs in `FixedUpdate`, so its timers count
  simulation steps: a slow frame does not shift a wave, and pausing with `timeScale` 0 pauses it.
- **Print the seed** in the HUD's debug line and in every bug report:
  `GameProbe.Register("seed", () => spawner.seed)`.

## 8. Checks

| Check | How |
|---|---|
| The wave table produces the mix intended | The edit-mode loop in §2 |
| Nothing spawns in view | A journey that samples `spawner.SpawnedTotal` and, in a `Spawned` handler, records `WorldToViewportPoint` of each spawn: none inside 0..1 |
| The cap holds | `JourneyAsserts.Never(samples, s => s.CountOf("sentries") > liveCap, "over-cap")` |
| The level has hidden points | `spawner.Postponed` at the end of a journey that stands the runner in each room: flat |
| A run repeats | Two runs of one journey with one seed: identical `wave` and `sentries` columns in both timelines |
| The spawner pauses | Set `Time.timeScale` to 0 for 2 s mid-wave: `SpawnedTotal` does not move |

## Where each need is answered

| Need | Answer |
|---|---|
| The pool behind `Create` and `Remove` | `unity-scene-flow` → `reference/pooling.md` |
| Pause, and what stops with it | `unity-scene-flow` → `reference/game-state-and-pause.md` |
| What each spawned sentry costs per frame | `reference/perception.md` |
| What tells the spawner an enemy died | `unity-combat` → `reference/damage-contract.md` |
| Spawn timelines for a scrolling shooter | `unity-gameplay` → `reference/genre-2d-fixed-screen.md` |
| Counts in the probe, journeys | `unity-play-harness` → `reference/probe-contract.md` |
| Seeds and determinism in the simulation | `unity-game-brief` → `reference/sim-presentation-split.md` |
