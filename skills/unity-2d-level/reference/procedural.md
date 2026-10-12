# Procedural levels — a seed in, a level that holds its invariants out

> Part of the `unity-2d-level` skill. The reach rule `scripts/level_validate.py` applies, how to
> generate so the invariants hold by construction, two generators in outline, and the tests that
> make "the same seed gives the same level" and "every level is completable" facts.

A generator that is right 99 times in 100 ships a level nobody can finish to one player in a
hundred, and the report says "sometimes it's impossible". The cure is the pattern
`unity-game-brief` → `resources/Sim/TrackGen.cs` uses for lane hazards, carried to two
dimensions: **build the guaranteed path first, decorate around it, then check every level
generated** — not a sample.

## The invariants

Write them in `templates/LEVEL_INVARIANTS.md` with ids, in the shapes of `unity-game-brief` →
`reference/invariants.md`. Every 2D level, built by hand or generated, holds at least these:

| Id | Invariant | Checked by |
|---|---|---|
| LVL-1 | The data is well formed: layer sizes, known tile ids, entities in bounds, unique ids | `LevelData.Problems()` · exit 1 from the validator |
| LVL-2 | The spawn cell is standable | `spawn-not-standable` |
| LVL-3 | The gate is reachable from the spawn | `gate-unreachable` |
| LVL-4 | Every pickup is reachable from the spawn | `pickup-unreachable`, one per pickup |
| LVL-5 | Every gap on the main path is inside the usable share of reach | the validator run with `--metrics`, which applies the margin |
| LVL-6 | The same seed gives the same level | a test comparing two generations as JSON |

## The reach rule

`scripts/level_validate.py` searches the level from the spawn. It is an approximation of the
motor, written down so a failure can be argued with. Everything is in cells.

**Cells.** A cell is *solid* with a tile on `Ground` or `Walls`. The level's left and right edges
are walls, above the top is open, below the bottom is a pit. A cell is *standable* when the cell
under it is solid or holds a `OneWay` tile, and the body — `--body-height` rounded up to whole
cells — fits above it with no solid cell and no `hazard`.

**Moves from a standable cell:**

1. Walk to the neighbouring cell at the same height, or up to `--step` higher.
2. Walk off an edge and fall.
3. Drop through a `OneWay` tile.
4. Jump — the full apex `H`, every hop 0.5 cells shorter, and a 0.15-cell hop that fits under a
   low ceiling. On a `launch` cell, also an arc of the pad's `apex`.

**An arc.** With rising gravity normalised to 1, an arc of apex `h` rises for `√h` and falls a
distance `d` in `√(d / m)`, where `m` is the fall multiplier. Horizontal speed is the constant
that makes the full jump cross exactly the flat jump distance `D`:

```
speed          v = D / ( √H · (1 + 1/√m) )
widest gap     D(h, R) = v · ( √h + √((h − R) / m) )        R  landing height minus take-off height
```

While airborne the runner may steer anywhere that speed allows, so the search tracks the set of
x positions the body's centre can occupy, not one parabola. Every quarter cell of height it
removes the positions where the body's box (`--body-width` × `--body-height`) overlaps a solid
or hazard cell. That one mechanism is the low ceiling that clips a jump, the ledge corner that
must be cleared before moving over it, and the hazard that must be jumped.

**Landing.** When the feet come down onto the top of a row, every position whose centre is over
a supported, standable cell reaches that cell. The centre must be over the cell: the half body
width that could overhang an edge is margin, and it is not spent — the same convention as
`unity-gameplay` → `reference/level-metrics.md`.

**Pickups and the gate.** The gate is reached when a reached cell lets the standing body cover
it. A pickup is reached from a reached cell in its own column, at most `⌊H⌋` cells plus the body
below it, with nothing solid between: stood in, or jumped straight up to.

**Where the numbers come from.** `--metrics metrics.json` reads the object that
`unity-gameplay` → `scripts/level_metrics.py` prints: `H` is the fixed-step apex, `D` the flat
jump distance times its margin (`--full-reach` uses 100%), `m` the fall multiplier. Or pass
`--jump-height`, `--jump-distance`, `--fall-multiplier`. All are world units; the level's
`cellSize` converts.

**What the rule does not model**, and what to do about each:

| Not modelled | Effect | Do |
|---|---|---|
| A fall-speed clamp | Reach on long drops is understated | Nothing: the error is on the safe side |
| The head hitting a ceiling and the jump continuing lower | Approximated by the shorter hops | A tight tunnel jump that fails here deserves a journey of its own |
| Abilities that change the jump (a second jump, a dash) | The rule is one jump | Run the validator once per ability set, with that set's numbers, on the rooms entered holding it |
| Wall jumps, moving platforms, ladders | Not seen | Keep the main path off them, or cover that stretch with a journey |
| A pickup hanging over a gap, collected mid-arc | Reported unreachable | Put it over a floor, or list it as waived in `templates/LEVEL_INVARIANTS.md` with the journey that collects it |
| Top-down levels | No jump at all | `"view": "topdown"` is a 4-neighbour flood over cells with a `Ground` tile and no `Walls` tile |

A cell board — pushing pickups onto gate cells in the sorting yard — is not a reachability
question but a search over board states: `unity-2d-grid` → `reference/pathfinding.md`.

### Seeing it pass and fail

```bash
python3 scripts/level_validate.py templates/sample-level.json \
    --jump-height 2.85 --jump-distance 5.17 --fall-multiplier 1.5 --indent 2      # exit 0
```

The sample needs its launch pad: the third roof is four cells above the second and the apex is
2.85. Delete the `launch-1` entity and run it again — exit 1, with `pickup-unreachable` for
`pickup-2` and `pickup-3`, `gate-unreachable`, and `reached_bounds.max` stopping at column 22,
which is where the path broke. Lowering `--jump-distance` to 3.5 fails it differently: the
four-cell gap after the first roof is out of reach and nothing past column 10 is reached.

## Generate so the invariant is structural

| Order | Step | Why in this order |
|---|---|---|
| 1 | **The golden path**: spawn, then a chain of landings, each one placed inside reach of the last, then the gate | LVL-3 holds before anything else exists |
| 2 | **Pickups on or beside path cells** | LVL-4 holds by construction |
| 3 | **Hazards and extra platforms off the path's landing cells and take-off run-ups** | Decoration cannot break the path |
| 4 | **Validate** | Confirms the construction instead of patrolling the output |

Step 1 needs reach as a table, not a formula. `ReachTable` (in `resources/LevelData.cs`) is the
`reach` rows of the metrics JSON: `JsonUtility.FromJson<ReachTable>(metricsText)`, then
`UsableGap(rise)` and `Allows(gap, rise)`.

### A chain of roofs (side run)

```csharp
// Every hop is taken from the reach table, so the gate is reachable by construction.
public static LevelData Generate(int seed, int width, int height, ReachTable reach)
{
    var rng = new System.Random(seed);
    LevelData level = ScriptableObject.CreateInstance<LevelData>();
    level.id = "roofs-" + seed;
    level.view = "side";
    level.width = width;
    level.height = height;
    level.tiles.Add(new LevelTile { id = 1, name = "roof" });
    var ground = new LevelLayer { name = LevelLayers.Ground, cells = new int[width * height] };
    level.layers.Add(ground);

    int x = 0, top = 1, roofs = 0;            // top: the roof's top row; the runner stands on top + 1
    while (true)
    {
        int length = 4 + rng.Next(5);         // 4 to 8 tiles: room to land and to stop
        if (x + length > width) break;
        for (int cx = x; cx < x + length; cx++)
            for (int cy = 0; cy <= top; cy++) ground.cells[level.Index(cx, cy)] = 1;

        if (roofs == 0) level.spawn = new LevelCell(x + 1, top + 1);
        else if (rng.Next(100) < 35)
            level.pickups.Add(new LevelEntity { id = "pickup-" + x, type = "pickup", x = x + length / 2, y = top + 1 });
        level.gate = new LevelCell(x + length - 2, top + 1);   // overwritten until the last roof
        roofs++;
        x += length;

        // The rise first, then a gap the table allows for that rise.
        int rise = Mathf.Clamp(rng.Next(-2, 3), 1 - top, height - 6 - top);
        int widest = Mathf.FloorToInt(reach.UsableGap(rise));
        if (widest < 2) { rise = 0; widest = Mathf.FloorToInt(reach.UsableGap(0)); }
        x += 2 + rng.Next(Mathf.Max(1, widest - 1));           // 2 to widest tiles of gap
        top += rise;
    }
    return level;
}
```

Needs `height` of 8 or more and `width` of 8 or more. Difficulty is two numbers of this loop —
the roof length and how close to `widest` the gap is allowed to go — so a ramp is a function of
`x` feeding both. The chunk form of the same idea, with hand-built strips instead of generated
roofs, is `resources/ChunkStitcher.cs` (`reference/rooms-and-chunks.md`): its structural rule is
"entry height equals the previous exit height", and its check is `SetProblems`.

### Rooms and corridors (depot, top-down)

1. Place `n` rectangular rooms at random positions; reject one that overlaps an earlier room
   grown by one cell, and retry up to a fixed count. Keep them in the order placed.
2. Connect room `i` to room `i − 1` with an L-shaped corridor between their centres: across,
   then up or down. Each room is joined to an earlier one, so the whole depot is connected by
   construction.
3. Paint `Ground` under rooms and corridors and `Walls` on every other cell: aisles and shelving.
4. Spawn in room 0; the gate in the room whose centre is furthest from it; pickups on floor
   cells of the rooms between; sentries only in rooms at least 6 × 6, never in a corridor.
5. Check with a flood from the spawn — the same rule the validator applies to a top-down level:

```csharp
public static HashSet<int> Reached(LevelData level)
{
    var seen = new HashSet<int>();
    var open = new Stack<LevelCell>();
    open.Push(level.spawn);
    while (open.Count > 0)
    {
        LevelCell c = open.Pop();
        if (!level.InBounds(c.x, c.y) || level.IsSolid(c.x, c.y)) continue;
        if (level.TileAt(LevelLayers.Ground, c.x, c.y) == 0) continue;     // no floor
        if (!seen.Add(level.Index(c.x, c.y))) continue;
        open.Push(new LevelCell(c.x + 1, c.y)); open.Push(new LevelCell(c.x - 1, c.y));
        open.Push(new LevelCell(c.x, c.y + 1)); open.Push(new LevelCell(c.x, c.y - 1));
    }
    return seen;
}
```

The gate and every pickup must have their cell index in the result. Corridors two cells wide
keep the runner's collider from catching on corners (`2 × body width`, from the level metrics);
paths for sentries across the result are `unity-2d-grid` → `reference/pathfinding.md`.

## Determinism

The same seed gives the same level only when nothing else feeds the generator.

- **One `System.Random(seed)` per generation, passed down.** Never `UnityEngine.Random`: it is
  one global stream, and any other script drawing from it shifts every number after.
- **Never decide by iterating a `Dictionary` or a `HashSet`.** Their order is unspecified.
  Decide over lists and arrays; use sets only to ask "is it in".
- **No time, no frame count, no physics query in the generator.** It is a function of its
  arguments. It runs in one call, before anything is painted, and touches no scene object.
- **Integers for layout.** Cells, lengths and heights are integers; floats enter only when the
  reach table is read, and are floored at once.
- **`System.Random` is stable for a seed within one runtime, not promised across runtimes.**
  When players on different builds must get the same level — a daily seed, a shared code — use
  a small explicit generator and keep the call shape, as `TrackGen` notes.
- **The seed is part of the level's identity**: put it in `id` and in every bug report.

## The tests

| Test | Asserts | Where it runs |
|---|---|---|
| `LVL6_SameSeedSameLevel` | `Generate(7).ToJson() == Generate(7).ToJson()`, and differs from seed 8 | Edit Mode |
| `LVL1_ShapeHolds_Seeds1To1000` | `Problems()` is empty for every seed | Edit Mode |
| `LVL3_LVL4_Reachable_Seeds1To200` | Write each level's JSON to a temp folder; `level_validate.py --metrics` exits 0 on every file | Edit Mode writes, CI runs the script over the folder |
| The top-down flood | Gate and pickups are in `Reached(level)` for seeds 1 to 1000 | Edit Mode |

```bash
for f in "$LEVEL_OUT"/*.json; do
  python3 scripts/level_validate.py "$f" --metrics metrics.json > /dev/null \
    || { echo "INVARIANT BROKEN: $f"; exit 1; }
done
```

Print the seed in the failure. One failing seed in a thousand is a generator bug to fix at
step 1, not a level to patch.

**At runtime**, a generator that is structural needs only the cheap check after each level:
`Problems()` and, for the top-down case, the flood. If either fails in a shipped build, do not
repair the level — derive the next seed (`seed × 31 + attempt`), try again up to eight times,
then load a hand-built fallback, and log the seed that failed.
