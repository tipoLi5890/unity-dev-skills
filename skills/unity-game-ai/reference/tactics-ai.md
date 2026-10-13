# Tactics AI — enumerate, score, pick

> Part of the `unity-game-ai` skill. A turn-based opponent has no tick, no cone and no chase. On
> its turn it lists every cell it can end on, gives each one a number, and takes the best. This
> file is that loop, the three terms the number is made of, the threat map that makes the third
> affordable, and how to keep the result from being either stupid or perfect. All the cell maths
> is `unity-2d-grid`. Worked setting: the **sorting yard** — sentries and the runner take turns
> on cells; the runner pushes pickups onto gate cells.

## 1. The loop

| Step | What | Cost |
|---|---|---|
| 1. **Enumerate** | Every cell the unit can reach this turn: `GridPathfinder.Range(from, movePoints, cost, reach)` | One flood: the cells within the move budget |
| 2. **Score** | For each reachable cell, the best action from it and a utility number | One evaluation per cell — keep it to array lookups |
| 3. **Pick** | The highest score; ties go to the nearest cell, because `Range` lists nearest first | — |
| 4. **Execute** | As the same commands a player issues: walk `PathFromRange(cell)`, then attack | Nothing new: the board's own rules run it |

A unit with 4 move points on an open board reaches about 40 cells. Forty evaluations of three
array lookups is nothing; forty evaluations that each run their own flood is a visible pause.
The design problem is entirely step 2.

The opponent **issues commands; it does not edit the board.** An AI that calls
`occupancy.TryMove` and subtracts health directly skips every rule a player's move goes through
— push rules, reactions, undo records — and each of those skipped is a bug only the AI can
produce. Commands and occupancy: `unity-2d-grid` → `reference/occupancy-and-turns.md`.

## 2. The utility function

Three terms, each normalised to 0..1 before weighting, so a weight means the same thing on a
small board and a large one:

| Term | 0 | 1 | Weight |
|---|---|---|---|
| **Objective** — closing on the goal | No nearer than now | Standing on it | 1.0 |
| **Damage** — hurting someone this turn | No attack from this cell | The attack kills | 1.5 |
| **Exposure** — standing where opponents can hit next turn | Nobody can reach this cell | Three or more can | −1.2 |

```csharp
// TacticsBrain.cs — picks one move for one unit. Plain C#: no scene, no MonoBehaviour.
public struct TacticalMove
{
    public Vector3Int cell;         // where the unit ends its move
    public int targetId;            // who it attacks from there, or 0
    public float score;
}

[Serializable]
public sealed class TacticsWeights
{
    public float objective = 1.0f;  // closing on the goal
    public float damage = 1.5f;     // hurting someone this turn
    public float exposure = 1.2f;   // standing where enemies can hit next turn
}

public sealed class TacticsBrain
{
    public TacticsWeights weights = new TacticsWeights();

    readonly GridPathfinder _finder;
    readonly List<Vector3Int> _reach = new List<Vector3Int>(128);

    public TacticsBrain(GridPathfinder finder) { _finder = finder; }

    /// <param name="threat">Per cell: how many opposing units can attack it next turn.</param>
    /// <param name="bestAttack">From a cell: the best target's id and the damage, as a share 0..1 of its health.</param>
    public TacticalMove Choose(Vector3Int from, int movePoints, GridPathfinder.EnterCost cost, Vector3Int goal,
                               Func<Vector3Int, int> threat, Func<Vector3Int, (int id, float share)> bestAttack)
    {
        _finder.Range(from, movePoints, cost, _reach);           // every cell this unit can end on
        int farthest = Mathf.Max(1, GridCoords.Distance(_finder.Shape, from, goal));

        var best = new TacticalMove { cell = from, score = float.NegativeInfinity };
        for (int i = 0; i < _reach.Count; i++)                   // nearest first: ties keep the shorter move
        {
            Vector3Int cell = _reach[i];
            (int id, float share) attack = bestAttack(cell);

            float closing = 1f - GridCoords.Distance(_finder.Shape, cell, goal) / (float)farthest;   // 0 at the start, 1 on the goal
            float hurt = Mathf.Clamp01(attack.share);                                                // 1 is a kill
            float risk = Mathf.Min(threat(cell), 3) / 3f;                                            // three attackers is as bad as it gets

            float score = weights.objective * closing + weights.damage * hurt - weights.exposure * risk;
            if (score <= best.score) continue;
            best = new TacticalMove { cell = cell, targetId = attack.id, score = score };
        }
        return best;
    }

    /// <summary>After Choose: the cells to walk, start included.</summary>
    public bool PathTo(Vector3Int cell, List<Vector3Int> path) => _finder.PathFromRange(cell, path);
}
```

- **Normalise, then weight.** Raw distance in cells against raw damage in points makes the
  weights depend on the board's size and the units' health. With every term in 0..1 the default
  weights read directly: a kill (1.5) is worth standing in front of three opponents (−1.2); a
  step nearer the gate is not.
- **Objective distance is the board's own metric** — `GridCoords.Distance(shape, a, b)` is
  Manhattan, Chebyshev or hexagonal by the neighbour rule — and deliberately not path cost: a
  second flood per cell is the pause this design avoids. Where walls make the metric lie
  (the goal is two cells away through a wall), run **one** flood from the goal before the loop
  and read `CostTo(cell)` in place of the distance — on a second `GridPathfinder` for the same
  board, because `Choose`'s own `Range` call replaces the first finder's last flood.
- **`closing` can go negative** for a cell farther than the start. That is intended: retreating
  costs objective, and is chosen only when exposure pays for it.
- **Damage as a share of the target's health** makes finishing a wounded unit outrank scratching
  a healthy one, with no special rule for kills.
- **The cost delegate is the unit's own**: what it may enter, as a field created once —
  `unity-2d-grid` → `reference/pathfinding.md`. The start cell is always in the range, so
  "stay and attack" is one of the candidates.

## 3. The threat map

Exposure asks, for a cell, "how many opposing units can attack it next turn". Answered inside
the scoring loop that is a flood per opponent per candidate cell. Answered **once per side per
turn**, it is an array lookup:

```csharp
// Once per side per turn: for every cell, how many opposing units can attack it next turn.
Array.Clear(threat, 0, threat.Length);
foreach (Vector3Int opponent in opponents)
{
    seen.Clear();                                                  // a HashSet<Vector3Int>: count each unit once per cell
    finder.Range(opponent, move, cost, reach);                     // where it can stand
    foreach (Vector3Int stand in reach)
    {
        GridCoords.Disc(finder.Shape, stand, 1, attackRange, ring);    // what it hits from there
        foreach (Vector3Int hit in ring)
            if (finder.Contains(hit) && seen.Add(hit))
                threat[(hit.y - finder.Origin.y) * finder.Width + (hit.x - finder.Origin.x)]++;
    }
}
```

| Board | Opponents | Work per turn |
|---|---|---|
| 9 × 7, move 4, melee | 4 | 4 floods of about 40 cells, 4 neighbours each: about 640 increments |
| 20 × 15, move 6, range 3 | 8 | 8 floods of about 80 cells, 24 cells each: about 15,000 |

Both are under a millisecond and happen once, before the first unit of the side moves.

- **`Disc` is a metric, not a flood**: it is "within N cells", which is what an attack range
  is. Ranged attacks that need a clear line filter the disc with the board's line of sight —
  `unity-2d-grid` → `reference/line-of-sight.md` — and the map is still built once.
- **The map is stale after each move of the side building it** — and that is correct: it
  describes the *other* side's next turn, which this side's moves do not change. Rebuild it only
  when a unit of the other side dies or is pushed.
- **`bestAttack` works the same way.** For each opposing unit, mark the cells it can be attacked
  from, once; per candidate cell the lookup returns the best target marked there.
- Range by flood and by metric: `unity-2d-grid` → `reference/neighbours-and-range.md`.

## 4. A side is more than one unit

| Problem | Rule |
|---|---|
| Two units choose the same cell | Plan and execute one unit at a time. The first unit's move is on the board before the second scores, so its cell is no longer enterable |
| The order matters | Units that can kill go first, then the nearest to the goal, then the rest. Sort once, by each unit's best score from a first pass |
| Everyone attacks the same target, overkilling it | Subtract planned damage from the target's health as each unit commits; `bestAttack` then sees a nearly dead target as worth less than its share suggests, or already dead |
| A unit blocks a corridor the others need | Add a fourth term: cells on the shortest path between an ally and the goal cost a little (0.2). It is one more array, built with one `FindPath` per ally |
| Simultaneous resolution (both sides move at once) | Reserve, then commit: `GridOccupancy.TryReserve` and `Commit` — `unity-2d-grid` → `reference/occupancy-and-turns.md` |

Do not search several of the side's moves together. Units × cells grows as a product; one unit
at a time with the board updated in between is a greedy plan that is wrong in ways players
cannot see and right in the ways they can.

## 5. Not stupid, not perfect

A scorer that always takes the maximum plays the same game every time and never makes the
mistake a player can exploit. Three dials, in the order to reach for them:

| Dial | How | Reads as |
|---|---|---|
| **Weights per archetype** | A brawler: damage 2.0, exposure 0.4. A sniper: exposure 2.0, objective 0.3. A runner for the gate: objective 2.5 | Personality. Three weight sets make three enemies from one function |
| **Seeded noise** | Add `(float)random.NextDouble() * 0.15f` to each score, from a `System.Random` seeded with the run's seed plus the turn number | Variety. Close calls go either way; clear calls do not |
| **Top-k** | Keep the best three, pick among them by score | A lower difficulty that still looks purposeful |

- **Never lower difficulty by picking at random among all moves.** A unit that walks away from
  a kill reads as broken. Noise in the score keeps every choice defensible.
- **Seed it**, for the same reason as the spawner: the same seed and the same player moves give
  the same opponent turn, so a bug report can be replayed —
  `reference/spawners-and-waves.md` §7.
- **Say why.** Keep the three term values of the chosen move and print them in a debug overlay
  or the probe: `GameProbe.Register("aiWhy", () => "closing 0.4 hurt 1.0 risk 0.33")`. "Why did
  it do that" is the only question anyone asks about a tactics AI.

## 6. Decide at once, show over time

The choice takes under a millisecond. Showing it takes as long as the game wants:

| Beat | Time |
|---|---|
| The camera settles on the unit | 0.2 s |
| A pause that reads as thinking | 0.3 s |
| The walk | 0.12 s a cell |
| The attack | Its own animation |

- **Resolve the side's whole turn on the board first**, unit by unit, keeping the record of
  each step; then play the records. The board's rules — reactions, pushes, deaths — have already
  run, so what is shown cannot diverge from what happened.
- **A ten-unit turn shown one after another at walking pace is half a minute of waiting.** Play
  the records overlapped or at a multiple — `unity-gameplay` → `reference/genre-2d-grid.md`.
- **Never compute across frames to seem thoughtful.** A coroutine that yields between
  candidates is a turn that changes if the board does. Compute in one call; the pause is a timer.

## 7. Checks — no scene needed

Everything here is plain C#, so the opponent is tested in edit mode on boards built in code:

```csharp
[Test]
public void Sentry_TakesTheKill_OverTheSaferCell()
{
    var finder = new GridPathfinder(Vector3Int.zero, 9, 7, GridShape.Rect4);
    var brain = new TacticsBrain(finder);
    var runner = new Vector3Int(4, 3, 0);

    TacticalMove move = brain.Choose(
        from: new Vector3Int(1, 3, 0), movePoints: 4, cost: (a, b) => b == runner ? 0 : 1, goal: runner,
        threat: cell => 0,
        bestAttack: cell => GridCoords.Distance(GridShape.Rect4, cell, runner) == 1 ? (7, 1f) : (0, 0f));

    Assert.AreEqual(7, move.targetId);
    Assert.AreEqual(1, GridCoords.Distance(GridShape.Rect4, move.cell, runner));
}
```

| Check | How |
|---|---|
| It takes a kill when one exists | The test above |
| It does not walk into three opponents for a scratch | The same board with `threat` returning 3 round the runner and `share` 0.2: the chosen cell is not adjacent |
| It never chooses an unreachable cell | `PathTo(move.cell, path)` is true for every choice in a hundred seeded boards |
| It is deterministic | The same board and seed twice: identical `cell` and `targetId` |
| A turn is fast | `finder.Expanded` after `Choose`: about the number of reachable cells, once. A multiple of it means a flood inside the loop |
| The whole turn | A journey over the yard-step situation: after the opponent's turn the probe's unit cells are all distinct and none is a wall |

## Where each need is answered

| Need | Answer |
|---|---|
| Reachable cells, range by flood and by metric | `unity-2d-grid` → `reference/neighbours-and-range.md` |
| Paths and per-unit cost functions | `unity-2d-grid` → `reference/pathfinding.md` |
| Lines of sight for ranged attacks | `unity-2d-grid` → `reference/line-of-sight.md` |
| Turn order, reservations, undo | `unity-2d-grid` → `reference/occupancy-and-turns.md` |
| Hexagonal and isometric coordinates | `unity-2d-grid` → `reference/coordinates.md` |
| Showing a step as a tween | `unity-2d-controller` → `reference/grid-step.md` |
| What damage an attack deals | `unity-combat` → `reference/damage-contract.md` |
| The tactics recipe as a whole | `unity-gameplay` → `reference/genre-2d-grid.md` |
| Real-time enemies on cells | `reference/pathfinding-2d.md` |
