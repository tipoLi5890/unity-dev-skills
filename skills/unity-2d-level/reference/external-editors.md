# External editors — Tiled and LDtk into the level data

> Part of the `unity-2d-level` skill. What each editor writes, how its layers, tiles and objects
> map onto `reference/level-data.md`, the axis flip, how a Tiled tile id is decoded, and when to
> convert the file and when to install an importer. `scripts/tiled_to_level.py` is the Tiled
> converter; the subset it handles is listed in full below.

Both editors are better at placing things than the Tile Palette is, and both write files a
script can read. The file is the source; the level data is what the game loads; the conversion
is one command in between, run again whenever the file changes.

## What each editor writes

| | Tiled | LDtk |
|---|---|---|
| Native file | `.tmx` — XML | `.ldtk` — JSON, one project holding every level; or one `.ldtkl` per level with "separate level files" on |
| JSON form | `.tmj` (maps) and `.tsj` (tilesets): **File ▸ Export As**, or `tiled --export-map json in.tmx out.tmj` | The native file already is JSON |
| A level is | One map file | One entry of `levels[]`, with `pxWid`, `pxHei` and its place in the world (`worldX`, `worldY`) |
| Tile layers | `layers[]` of `type: "tilelayer"`: a flat `data` array of global tile ids, row by row from the top | `layerInstances[]`: `gridTiles[]` on a `Tiles` layer, `autoLayerTiles[]` on an `AutoLayer` or a ruled `IntGrid` layer; each tile has `px` (pixel position), `t` (tile id) and `f` (flip bits) |
| Collision as data | A tile layer you name for it, or a property on tiles | An `IntGrid` layer: `intGridCsv`, one integer per cell, 0 empty |
| Entities | `type: "objectgroup"` layers: objects with a class, a pixel rectangle and typed `properties[]` | An `Entities` layer: `entityInstances[]` with `__identifier`, `__grid` (cell), `px`, `width`, `height` and `fieldInstances[]` |
| Rows run | Top to bottom, y down | Top to bottom, y down |
| Neighbouring levels | Separate maps; a world file lists them | `__neighbours[]` on each level: the adjacent level's id and a direction |

**Both count rows from the top; the level data counts from the bottom.** The flip happens once,
in the converter: `level index = x + (height − 1 − row) × width`. Nothing downstream flips again.
A level that loads upside down was flipped zero times or twice.

## Tiled: the mapping

| Tiled | Level data |
|---|---|
| Map `width`, `height` | `width`, `height` |
| `tilewidth` (= `tileheight`) pixels | one cell; `cellSize` comes from `--cell-size`, 1.0 by default |
| Tile layer named `Background`, `Ground`, `Walls`, `OneWay`, `Front` or `Markers` (any case) | The layer of that name; another name is mapped with `--layer Tiled=Level` |
| A global tile id in `data` | The same number as the tile id, flags removed; listed in `tiles` as `tileset#local` |
| The three flip flags on a global id | The cell's entry in `flips` |
| Object of class `spawn` · `gate` | `spawn` · `gate` (exactly one of each) |
| Object of class `pickup` | An entry in `pickups` |
| Object of any other class | An entry in `entities`, `type` = the class |
| Object name | The entity `id`; unnamed objects get `class-objectid` |
| Custom properties | `fields`: name → `key`, Tiled type → `type`, value as a string (`true`/`false` for bool) |

### Decoding a global tile id

Every entry of a tile layer is a 32-bit number: a tile id in the low 28 bits and flags in the
high four.

| Bit | Mask | Meaning |
|---|---|---|
| 31 | `0x80000000` | Flipped horizontally |
| 30 | `0x40000000` | Flipped vertically |
| 29 | `0x20000000` | Flipped diagonally — the tile's x and y axes swap; applied before the other two |
| 28 | `0x10000000` | Rotated 120° — hexagonal maps only; cleared and ignored on an orthogonal map |

```python
gid   = raw & 0x0FFFFFFF          # 0 means the cell is empty
flips = (1 if raw & 0x80000000 else 0) | (2 if raw & 0x40000000 else 0) | (4 if raw & 0x20000000 else 0)
```

A raw value above 2 147 483 647 that is used as an id without masking is the classic bug: one
flipped tile becomes an id of two billion and "has no binding". Rotations are combinations: a
quarter turn clockwise is diagonal + horizontal (`flips` 5), a half turn is horizontal +
vertical (3), a quarter turn anticlockwise is diagonal + vertical (6). The loader turns `flips`
into a tile transform matrix; a flipped tile turns about the tile anchor, so its sprite wants a
centred pivot.

**The id is Tiled's global id**: a tileset's `firstgid` plus the tile's index in it. It is
stable while the map's tilesets keep their order and size. Adding a tileset **before** another,
or widening a tileset image, renumbers every tile after it — and the loader's id table with it.
Keep one tileset per map where that is possible, append new tilesets at the end, and treat a
changed `firstgid` in a diff as a change to the binding table.

### Object positions

Object coordinates are pixels with y down, and the anchor depends on the kind of object:

| Object | Anchor | Becomes |
|---|---|---|
| Rectangle | top-left corner | the cells it covers: `x`, `y` of its bottom-left cell, `w`, `h` rounded up |
| Point | the point | the cell containing it, 1 × 1 |
| Tile object (has a `gid`) | **bottom-left** corner | the cells it covers, counted up from `y` |

An object off the grid is snapped to cells and counted in a `NOTE` line on stderr. Turn on
**View ▸ Snapping ▸ Snap to Grid** in Tiled so the count stays 0. The converter reads the class
written on the object itself; when it reports a tile object with no class, set the class on the
object, not only on its tile.

### What the converter handles

`scripts/tiled_to_level.py` reads this subset and exits 2, naming the feature, on anything else:

| Area | Handled | Stops with exit 2 |
|---|---|---|
| Map | `.tmj` / `.json`, orthogonal, finite, square tiles | `.tmx` (export it), isometric, staggered and hexagonal maps, infinite maps, non-square tiles |
| Tile layers | Plain arrays; base64 with no compression, zlib or gzip | Zstandard compression, layer offsets, a layer whose size differs from the map's, two layers mapped to one name, a name outside the stack with no `--layer` |
| Other layers | Object layers | Group layers; image layers unless `--skip-image-layers` |
| Tilesets | Embedded or external — only `firstgid` and the name are read | — (tile properties, animations, collision shapes and Wang sets are not read and do not stop it) |
| Objects | Rectangles, points, tile objects, unrotated, with a class | Ellipses, polygons, polylines, text, rotated objects, template instances |
| Properties | `string`, `int`, `float`, `bool`, `color`, `file`, `object` | `class`-typed (nested) properties |

Exit 1 is a different statement: the map converted but is not a level — no `spawn`, two gates,
an object with no class, two objects with one name, an object outside the map.

```bash
python3 scripts/tiled_to_level.py maps/side-run-01.tmj --layer Platforms=OneWay \
    --out Assets/Levels/side-run-01.json \
  && python3 scripts/level_validate.py Assets/Levels/side-run-01.json --metrics metrics.json
```

Run the pair in CI over every map. A map that converts and fails validation is a level bug found
before anyone played it.

## LDtk: the mapping

No converter ships here for LDtk; the mapping is short enough to write against the project's own
layer names, and it is the same five steps.

| LDtk | Level data |
|---|---|
| Layer `__cWid`, `__cHei`, `__gridSize` | `width`, `height`; one cell is `__gridSize` pixels |
| `IntGrid` layer, `intGridCsv[i]` | The collision layers: decide which value means `Ground`, `Walls`, `OneWay` and write one layer for each, with a placeholder tile id |
| Each `gridTiles[]` or `autoLayerTiles[]` entry | Cell `(px[0] / gridSize, height − 1 − px[1] / gridSize)`; tile id `t + 1` (LDtk ids start at 0, and 0 means empty here); `f` bit 0 → horizontal, bit 1 → vertical |
| `entityInstances[]`, `__identifier` | `type`; `Spawn`, `Gate`, `Pickup` go to `spawn`, `gate`, `pickups` |
| `px`, `__pivot`, `width`, `height` | The entity's pixel rectangle: its left is `px[0] − __pivot[0] × width`, its top `px[1] − __pivot[1] × height`. Convert that rectangle as a Tiled rectangle is converted: bottom-left cell, size rounded up |
| `iid` | `id` — already unique and stable across edits |
| `fieldInstances[]`: `__identifier`, `__type`, `__value` | `fields`: `key`, `type`, `value` as a string |
| `__neighbours[]` | `door` entities, or the room graph — `reference/rooms-and-chunks.md` |

Three things that differ from Tiled: an LDtk entity's `px` is its **pivot**, not a corner
(`__pivot` `[0, 0]` is top-left, `[0.5, 1]` bottom-centre), several tiles can stack in one cell of an auto-layer (keep the
last, which draws on top), and LDtk has no diagonal flip, so `flips` is 0 to 3. LDtk's "super
simple export" writes a PNG per layer and a small JSON per level; it suits a game that draws the
level as images and needs only the entities.

## Converter or importer package

| Use | When |
|---|---|
| **The converter into level data** | The game loads levels through `resources/TilemapLevelLoader.cs`; levels are validated in CI; levels are generated, downloaded or modded; the tiles are Unity tile assets (rule tiles included) and the external editor only says which id goes where |
| **An importer package** (community importers exist for both: SuperTiled2Unity for Tiled, LDtkToUnity for LDtk) | The external editor is the art pipeline too — its tilesets, animations, auto-layers and collision shapes should arrive as Unity assets without a binding table; the level is a prefab placed in a scene and never read as data |

They combine: an importer for what the level looks like, and the converter over the same file
for what the game and the validator need to know — spawn, gate, pickups, solid cells. What does
not work is an importer alone plus a reachability check, because the imported prefab is not
data any script outside the Editor can read.

Before adopting an importer, read its supported Unity versions against
`ProjectSettings/ProjectVersion.txt`, and import one real map: a package that lags the editor
format by a version fails on files saved by a newer editor.

## Checks

- Convert `templates/sample-level.json`'s layout drawn in the editor and diff the result against
  the template: `cells` identical means the flip and the layer mapping are right.
- Paint one tile flipped each way and one rotated a quarter turn clockwise; after `Load` they
  face the way the editor shows.
- Place a point, a rectangle and a tile object in the same cell; the converter reports the same
  `x`, `y` for all three.
