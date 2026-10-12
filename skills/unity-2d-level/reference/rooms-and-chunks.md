# Rooms and chunks — the level's unit above the tile

> Part of the `unity-2d-level` skill. Rooms as rectangles the camera and the game agree on, a
> room graph whose doors are data, chunks stitched into an endless run, and loading rooms
> additively. `resources/RoomBounds.cs` is the room; `resources/ChunkStitcher.cs` the run.

A tile is too small a unit to design or load by. Two larger ones cover almost every 2D level:
the **room** — a rectangle the camera is confined to, entered and left through doors — and the
**chunk** — a pre-built strip appended to the end of a run. Both are data first: a rectangle, a
list of exits, two heights.

## A room is a rectangle on tile boundaries

| Rule | Why |
|---|---|
| At least one screen in both dimensions: `2 × orthographic size × aspect` wide, `2 × orthographic size` tall | A confined camera has no legal position in a smaller room and shows the neighbour |
| Edges on whole tiles | A room edge through the middle of a tile shows half a tile of the next room at every door |
| Neighbours share the full height or width of the edge they meet on, or the door is a corridor room of its own | A camera sliding along a shared edge otherwise reveals the void beside the shorter room |
| Rooms do not overlap | The runner is in exactly one |

For the side run at orthographic size 5.625 and 16:9, a screen is 20 × 11.25 units: rooms are
multiples of 20 wide and at least 12 tiles tall. `RoomBounds.FitsView(orthographicSize, aspect)`
is the first rule as a function; assert it for every room in an Edit Mode test with the largest
orthographic size the game uses.

`RoomBounds` sits at the room's bottom-left corner with a `size` in world units, a trigger
`BoxCollider2D` fitted to the rectangle **inset by half a unit** on every side, and one event:

```csharp
RoomBounds.Entered += (from, to) =>
{
    spawner.Sleep(from);                 // from is null for the first room
    spawner.Wake(to);
    checkpoint.Set(to.roomId);
};
```

- **The inset is what makes the event fire once.** Two rooms that share a wall have triggers a
  unit apart, so the runner leaves one before entering the other and turning back in a doorway
  re-enters the first.
- **The room names no camera.** Each room's `onEntered` (a `UnityEvent`) is where the camera is
  told: wire it to the room's camera switch — `unity-camera` → `reference/follow-2d.md`
  describes both ways, one camera per room and one camera with a swapped confiner shape
  (`unity-camera` → `resources/RoomConfinerSwitch.cs`, whose `Apply()` is the method to wire).
  The confiner's shape is the full rectangle; the trigger is the inset one. They are two
  colliders.
- **A spawn or respawn inside a room crosses no edge.** `RoomBounds` checks in `Start` whether
  the runner is already inside; after a respawn, call `Enter()` on the checkpoint's room.

## The room graph: doors are data

An exploration level is a graph: rooms are nodes, doors are edges, and a door may need an
ability. Kept as data it can be checked; kept as trigger objects scattered in scenes it cannot.

Each `RoomBounds` lists its doors — `to` (the other room's id), `localPosition` (where the
runner arrives), `requires` (an ability or key, empty for none), `oneWay` (a ledge drop with no
way back). In a level file the same thing is two entity types, `room` and `door`
(`reference/level-data.md`).

`RoomBounds.GraphProblems()` returns the structural faults as sentences: two rooms with one id,
overlapping rooms, a door to a room that does not exist, a door with no door back that is not
marked one-way. Run it in a Play Mode test after the level scene loads and assert the list is
empty.

Two invariants need the abilities as well as the graph, and are a breadth-first search over
`(room, set of abilities held)`:

| Invariant | The search |
|---|---|
| **The gate is reachable** | From the spawn room with no abilities, crossing a door only when `requires` is held and collecting the abilities found in each room reached, the gate's room is reached |
| **No soft lock** | From every reachable `(room, abilities)` state, the gate's room is still reachable. A one-way door into a region whose exit needs an ability found only outside it fails this |

An ability that changes the jump changes what is reachable **inside** rooms too: validate each
room's tiles with the reach of the ability set the player is guaranteed to hold on entering it
(`reference/procedural.md`, "The reach rule"). A pickup reachable one ability early is a
sequence break; decide whether it is deliberate and write that down.

## Chunks: an endless run from strips

A chunk is a prefab authored from `x = 0` to `x = length`, with its floor at `entryHeight` on
the left edge and `exitHeight` on the right, in tiles. `ChunkStitcher` appends chunks to keep
`ahead` units built in front of the view and returns those more than `behind` units back to a
per-prefab pool.

**The rule that makes stitching safe: the next chunk's entry height equals the last chunk's
exit height.** Nothing else about a join is free.

| Authoring rule | Number for the side run | Why |
|---|---|---|
| Flat run-in and run-out at the entry and exit heights | at least `run speed × 0.4 s` each: 3.2 units at 8 units/s, so 4 tiles | Two fair chunks otherwise form a gap or a hazard pair nobody checked |
| Every gap and ledge inside the chunk is inside reach | 5 tiles on the level, 4 when climbing | `unity-gameplay` → `reference/level-metrics.md` |
| `length` is a whole number of tiles, at least two screens | 40 units | A shorter chunk repeats within one screen and reads as a pattern |
| `difficulty` is an integer from 0 | 0 to 4 | The stitcher unlocks one step per `unitsPerDifficulty` of run |
| For every exit height in the set, a difficulty-0 chunk enters there | — | The run can never dead-end: `ChunkStitcher.SetProblems` lists the violations |

**The difficulty ramp** is by distance, not by time: at `unitsPerDifficulty = 250`, difficulty 2
unlocks 500 units in. The stitcher prefers chunks within `difficultyWindow` steps of the
unlocked value and falls back to anything at or below it, so the run keeps its recent
difficulty but never stalls. A speed ramp (8 → 14 units/s over the first 1000 units) widens
reach as it goes: author difficulty-0 chunks against the slowest speed and validate
high-difficulty chunks against the speed at the distance they unlock.

**The order is a function of the seed.** `ChunkStitcher.Sequence(chunks, seed, count, …)` returns
the first `count` indices without a scene; a test asserts that two calls with one seed agree and
that `SetProblems` is empty. That makes a reported run reproducible: the bug report carries the
seed and the distance.

**Move the runner, not the world.** The stitcher places chunks at increasing x. Scrolling the
world past a stationary runner breaks every position-based check, the probe's `pos` first.
Floating-point precision is not a concern below tens of thousands of units; past that, shift
everything back by a whole number of chunks in one frame and tell the camera it was a teleport.

A chunk can also be a `LevelData` painted onto one long Tilemap with `SetTilesBlock` at an
offset instead of a prefab. Use that when chunks come from an external editor or need
`scripts/level_validate.py` run on each; use prefabs when a chunk carries hand-placed objects.
Either way validate the **pair**: concatenate two chunks' cells, exit to entry, and run the
validator on the result for every pair the entry rule allows.

## Loading rooms additively

A large exploration level is one scene per room (or per cluster of rooms), loaded around the
runner.

1. The persistent scene holds the runner, the camera, the room graph and the game state.
2. On `RoomBounds.Entered`, load every room the new room has a door to with
   `SceneManager.LoadSceneAsync(name, LoadSceneMode.Additive)`, and unload rooms that are two
   doors away with `SceneManager.UnloadSceneAsync`.
3. A door opens only when its target scene's load has finished. A corridor room, or a door
   animation, covers the wait.

- **Each room scene is authored at its world position**, so loading it needs no placement and
  two rooms never disagree about where the shared wall is.
- **Per-room state lives in the persistent scene**, keyed by entity id: which pickups are
  collected, which doors are open. A room scene that is unloaded and reloaded starts fresh and
  asks.
- **Never set an additively loaded room scene active.** New objects spawn into the active scene
  and vanish when that room unloads.

## Checks

- Edit Mode: `FitsView` for every room at the largest orthographic size; `SetProblems` empty;
  `Sequence(seed)` equal across two calls and different across two seeds.
- Play Mode: `GraphProblems()` empty; walk the runner through one door and back and count
  `Entered` — exactly two events.
- A journey through the first three rooms with the camera's never-outside-the-room assertion
  from `unity-camera` → `templates/CameraJourneyTest.cs`.
