# Level data — one shape, as an asset and as a file

> Part of the `unity-2d-level` skill. The schema every other file here reads or writes: what a
> level holds, how cells are indexed, why it carries ids instead of asset references, how a
> version changes, and when the level lives in a ScriptableObject and when in JSON.
> `resources/LevelData.cs` is the type; `templates/sample-level.json` is a level in it.

A level that exists only as painted Tilemaps can be looked at and played, and nothing else. It
cannot be diffed, generated, validated outside the Editor, converted from another tool, or
loaded by a build that was shipped last month. So the level is a small data structure, and the
Tilemaps are painted from it.

## The shape

```json
{
  "format": "courier-level",
  "version": 1,
  "id": "side-run-01",
  "view": "side",
  "width": 40, "height": 12, "cellSize": 1.0,
  "tiles":  [ {"id": 1, "name": "roof"}, {"id": 2, "name": "ledge"} ],
  "layers": [ {"name": "Ground", "cells": [1,1,1, 0,0,0], "flips": []},
              {"name": "OneWay", "cells": [0,0,0, 0,2,0], "flips": []} ],
  "spawn": {"x": 2, "y": 2},
  "gate":  {"x": 38, "y": 2},
  "pickups":  [ {"id": "pickup-1", "type": "pickup", "x": 18, "y": 5, "w": 1, "h": 1, "fields": []} ],
  "entities": [ {"id": "launch-1", "type": "launch", "x": 22, "y": 3, "w": 1, "h": 1,
                 "fields": [ {"key": "apex", "type": "float", "value": "5"} ]} ]
}
```

The two `cells` arrays above are cut short for the page; a real one holds `width × height`
entries.

| Key | Holds | Rule |
|---|---|---|
| `format` · `version` | `"courier-level"` · an integer | A reader refuses a file with another format, and a version newer than it knows |
| `id` | The level's name in code and in file names | Unique per game; a save file stores it |
| `view` | `"side"` or `"topdown"` | Decides which layers are solid (below) and how the level is searched |
| `width` · `height` | Cells | Every layer is exactly this size |
| `cellSize` | World units per cell | Equal to the Grid's cell size; 1.0 when sprites are authored at one tile per unit |
| `tiles` | The id table: `id` (1 or more) and a `name` for people | 0 is never listed: it means empty |
| `layers[].name` | One of `Background`, `Ground`, `Walls`, `OneWay`, `Front`, `Markers` | At most one layer per name; a missing layer is empty — `reference/layer-stack.md` |
| `layers[].cells` | `width × height` tile ids | Index `x + y × width`; **cell (0, 0) is the bottom-left, y grows upwards** |
| `layers[].flips` | Empty, or one integer per cell | Bit 1 horizontal, 2 vertical, 4 diagonal (applied first) |
| `spawn` · `gate` | One cell each | Exactly one of each; both are invariants' anchors, so they are not entities |
| `pickups` | Entities of type `pickup` | Kept apart because "every pickup is reachable" is checked over this list |
| `entities` | Everything else placed in the level | `type` picks the prefab; `x`, `y` is the bottom-left cell it covers; `w`, `h` its size in cells |
| `fields` | `key`, `type`, `value` — the value is always a string | `type` (`int`, `float`, `bool`, `string`) says what it parses as |

Solid cells by view — the one place the two views differ:

| View | Stops the runner | Is floor | One-way |
|---|---|---|---|
| `side` | a tile on `Ground` or `Walls` | the top of a solid cell | a tile on `OneWay`: stood on, passed from below |
| `topdown` | a tile on `Walls` | a cell with a `Ground` tile and no `Walls` tile | not used |

## Why it is this shape

- **Row 0 is the bottom.** That is Tilemap cell space, so `cells[x + y·width]` paints at
  `Vector3Int(x, y, 0)` and nothing that reads a level flips a row. Editors that count rows from
  the top are flipped once, by the converter (`reference/external-editors.md`). A flat array in
  that order is also exactly what `Tilemap.SetTilesBlock` takes — `reference/runtime-tilemap.md`.
- **Ids, not asset references.** A level that stores `TileBase` references is a Unity asset and
  nothing else: no script outside the Editor reads it, renaming a tile asset rewrites every
  level, and a level downloaded after release cannot name an asset the build does not have. An
  integer id is bound to a tile in one table on `resources/TilemapLevelLoader.cs`, shared by
  every level. Entities work the same way: `type` is a string the spawn delegate maps to a
  prefab or a pool.
- **Flat and shallow, because `JsonUtility` reads it.** No dictionaries, no nested arrays, no
  entity subclasses — `JsonUtility` serialises none of them. Fields are a list of key/value
  strings with typed accessors (`GetInt`, `GetFloat`, `GetBool`, `GetString`), parsed with the
  invariant culture so a comma-decimal machine reads `2.5` as 2.5.
- **`w` and `h` written out.** A key missing from a file reads as 0 in `JsonUtility`, not as the
  field's initial value; `LevelEntity.Width` and `Height` clamp to 1, and writers emit both.
- **Entity ids are stable names.** `pickup-1` is what a save file records as collected and what
  a failing check prints. Generate them from type and cell (`pickup-18-5`) when nothing better
  exists; never from list position, which changes when an entity is inserted.

## Entity types the courier levels use

| `type` | Cells | Fields |
|---|---|---|
| `pickup` | 1 × 1, in `pickups` | `value` (int) |
| `hazard` | any rectangle; touching it ends the run | — |
| `launch` | 1 × 1, on the floor cell the runner stands in | `apex` (float, world units the pad throws the runner) |
| `sentry` | 1 × 1 at its start cell | `patrolMinX`, `patrolMaxX` (int cells), `speed` (float); in a depot, `facing`, `coneAngle`, `coneRange` |
| `room` | the room's rectangle | `id` (string) — `reference/rooms-and-chunks.md` |
| `door` | the doorway's cells | `to` (room id), `requires` (ability or key, empty for none) |

`hazard` and `launch` change what is reachable, so `scripts/level_validate.py` reads them; it
ignores every other type.

## Versioning

`version` is an integer, starts at 1 and goes up by one whenever a reader would misread an old
file: a key renamed, a unit changed, a layer's meaning changed. Adding an optional key is not a
version change.

- A file **older** than the code is upgraded in memory, one step per version, in order —
  `LevelData.Upgrade()` is where each step is written. Steps are never edited after release;
  a new change is a new step.
- A file **newer** than the code is refused with a message naming both numbers. Reading it with
  old rules drops whatever the new version added and reports nothing.
- Shipped levels are re-saved at the new version in the same change that adds the step, so the
  upgrade path is exercised only by files the project does not control: a level made with an
  older build of a level editor, a downloaded level.

Put one level of every past version in the test assets and load each in an Edit Mode test. That
is the whole regression suite for the format.

## ScriptableObject or JSON

`LevelData` is a `ScriptableObject`, and `LevelData.FromJson` / `ToJson` move the same fields
through `JsonUtility`, so the choice is where the level is edited, not what it is.

| Keep the level as | When | Costs |
|---|---|---|
| A `.json` file under `Assets/` (imported as a `TextAsset`) | It comes from Tiled, LDtk or a generator; a script outside Unity must read it; it should diff in review | Parsed at load; a missing or malformed file is a runtime error, so it needs the checks below in CI |
| A `LevelData` asset (**Create ▸ Unity Dev ▸ Level Data**) | It is edited in the Inspector, or referenced directly by a level-select list | Not readable by `scripts/level_validate.py` until exported; the YAML diff of an 8000-entry array is unreadable |
| JSON outside the build (downloaded, user-made) | Levels arrive after release | Treat it as untrusted: run `Problems()` and refuse on any entry before `Load` |

Whichever holds it, **run both checks before the level is trusted**: `LevelData.Problems()` for
the shape (layer sizes, unknown tile ids, entities out of bounds, duplicate ids), then
`scripts/level_validate.py` for reachability. A hand-painted level reaches the script through
**Tools ▸ Unity Dev ▸ 2D Level ▸ Export Level JSON**, which reads the stack back through the same
id table and the marker layer.

## Checks

- `python3 scripts/level_validate.py templates/sample-level.json --jump-height 2.85
  --jump-distance 5.17 --fall-multiplier 1.5` exits 0 with three pickups and the gate reachable.
- Round trip: `LevelData.FromJson(level.ToJson()).ToJson()` equals `level.ToJson()` in an Edit
  Mode test. A field that does not survive is one `JsonUtility` cannot serialise.
- After `TilemapLevelLoader.Load`, `Verify(level)` returns 0 mismatched cells.
