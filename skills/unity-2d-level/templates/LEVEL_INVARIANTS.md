# Level invariants — <game>

Copy next to the levels. One row per rule a level must hold; an id is never reused, and it
appears in the name of the test that checks it. The numbers on the first line are the ones
every reach check runs with: change them here and re-run every level.

**Runner:** apex `2.85` units (fixed step) · flat jump `5.17` units (90% of reach) · fall
multiplier `1.5` · body `0.8 × 1.8` · walked step `0` · cell `1.0` unit
**Metrics file:** `metrics.json`, written by `level_metrics.py --apex 3 --time-to-apex 0.4
--run-speed 8 --fall-multiplier 1.5`

| Id | Invariant | Checked by | Runs |
|---|---|---|---|
| LVL-1 | The data is well formed: layer sizes, known tile ids, entities in bounds, unique ids | `LevelData.Problems()` is empty | Edit Mode, every level |
| LVL-2 | The spawn cell is standable | `level_validate.py`: no `spawn-not-standable` | CI, every level file |
| LVL-3 | The gate is reachable from the spawn | `level_validate.py`: no `gate-unreachable` | CI, every level file |
| LVL-4 | Every pickup is reachable from the spawn | `level_validate.py`: no `pickup-unreachable` | CI, every level file |
| LVL-5 | Main-path gaps use at most 90% of reach | `level_validate.py --metrics metrics.json` exits 0 | CI, every level file |
| LVL-6 | The same seed gives the same level | `LVL6_SameSeedSameLevel` | Edit Mode |
| LVL-7 | Every room is at least one screen: 20 × 11.25 units | `RoomBounds.FitsView(5.625, 16/9)` for every room | Edit Mode |
| LVL-8 | The room graph is sound: every door leads somewhere and back | `RoomBounds.GraphProblems()` is empty | Play Mode |
| LVL-9 | The chunk set cannot dead-end | `ChunkStitcher.SetProblems(chunks, startHeight)` is empty | Edit Mode |
| LVL-10 | After loading, the painted tiles are the data | `TilemapLevelLoader.Verify(level) == 0` | Play Mode, one level |

## Waived

A pickup or a stretch the cell search cannot see — collected mid-arc, reached by a wall jump or
a moving platform — is listed here with the journey that proves it instead.

| Level | What | Why the search misses it | Proved by |
|---|---|---|---|
| `side-run-03` | `pickup-7` | Hangs over the gap after the second roof | journey `ledge-drop`, assertion `pickups >= 7` |
