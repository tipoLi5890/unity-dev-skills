# Palette and grid — every argument, and what happens if you get it wrong

`GridPaletteUtility.CreateNewPalette` exists as two overloads, at six and eight arguments; every
parameter is either an enum with a small closed set of values or a `Vector3` whose components
mean different things per layout. This file enumerates all of them and says which combinations
are wrong.

## The two overloads

```csharp
GameObject CreateNewPalette(string folderPath, string name,
                            GridLayout.CellLayout layout, GridPalette.CellSizing cellSizing,
                            Vector3 cellSize, GridLayout.CellSwizzle swizzle);

GameObject CreateNewPalette(string folderPath, string name,
                            GridLayout.CellLayout layout, GridPalette.CellSizing cellSizing,
                            Vector3 cellSize, GridLayout.CellSwizzle swizzle,
                            TransparencySortMode sortMode, Vector3 sortAxis);
```

`CreateNewPaletteAtCurrentFolder` mirrors both at five and seven arguments — it drops
`folderPath` and reads the Project window's selection instead. That makes it unusable from a
headless run and non-deterministic from an interactive one. Pass the folder.

## Where the types live

| Type | Fully qualified | Assembly |
|---|---|---|
| `GridPaletteUtility` | `UnityEditor.Tilemaps.GridPaletteUtility` | `Unity.2D.Tilemap.Editor` |
| `GridPalette`, `GridPalette.CellSizing` | `UnityEditor.GridPalette` | `UnityEditor.TilemapModule` |
| `Grid`, `GridLayout` | `UnityEngine.*` | `UnityEngine.GridModule` |
| `GridLayout.CellLayout`, `GridLayout.CellSwizzle` | `UnityEngine.GridLayout` | `UnityEngine.GridModule` |
| `TransparencySortMode` | `UnityEngine.TransparencySortMode` | `UnityEngine.CoreModule` |
| `Tilemap`, `TileBase`, `Tile`, `Tile.ColliderType` | `UnityEngine.Tilemaps.*` | `UnityEngine.TilemapModule` |

`GridPalette` sitting in bare `UnityEditor` while the utility that consumes it sits in
`UnityEditor.Tilemaps` is the one that wastes time: a single `using UnityEditor.Tilemaps;`
compiles the call site right up to the `cellSizing` argument.

## Enum values, complete

| Enum | Members |
|---|---|
| `GridLayout.CellLayout` | `Rectangle`, `Hexagon`, `Isometric`, `IsometricZAsY` |
| `GridPalette.CellSizing` | `Automatic`, `Manual` |
| `GridLayout.CellSwizzle` | `XYZ`, `XZY`, `YXZ`, `YZX`, `ZXY`, `ZYX` |
| `TransparencySortMode` | `Default`, `Perspective`, `Orthographic`, `CustomAxis` |
| `Tile.ColliderType` | `None`, `Sprite`, `Grid` |
| `Tilemap.Orientation` | `XY`, `XZ`, `YX`, `YZ`, `ZX`, `ZY`, `Custom` |

Four layouts and no more, so there is no value to reach for when a project wants a staggered or
"2.5D" grid: it is one of these four plus a swizzle, or it is not a Unity grid.

## The four working combinations

| Layout | `cellSizing` | `cellSize` | `swizzle` | `sortMode` | `sortAxis` |
|---|---|---|---|---|---|
| `Rectangle` | `Automatic` | `(1, 1, 0)` | `XYZ` | `Default` | *(ignored)* |
| `Hexagon` | `Manual` | `(0.8659766, 1, 1)` | `XYZ` | `Default` | *(ignored)* |
| `Isometric` | `Manual` | `(1, 0.5, 1)` | `XYZ` | `CustomAxis` | `(0, 0, 1)` |
| `IsometricZAsY` | `Manual` | `(1, 0.5, 1)` | `XYZ` | `CustomAxis` | `(0, 0, 1)` |

### `cellSize` z, and why rectangular ends in 0

The z component is the cell's depth. A flat rectangular grid has none, so `(1, 1, 0)`. The
hexagonal and isometric rows carry `z = 1` because those layouts address a third axis — for
`IsometricZAsY` it is the one that fakes height, and a zero there flattens the effect silently.

### `Automatic` discards the size you passed

Automatic sizing takes the cell dimensions from the first sprite dropped into the palette. That
is correct for a rectangular grid cut from a uniformly sliced sheet, and wrong for every other
layout, where the cell is deliberately not the sprite's bounding box: a hex cell is narrower than
the sprite that draws it, and an isometric cell is half as tall. Pass `Manual` and the numbers.

The symptom of getting this backwards is a palette that looks fine until the second sprite is
dropped in and everything shifts by a few pixels.

### The hexagonal width

`0.8659766` approximates √3⁄2, the pointy-top hex width ratio. The exact value is `0.8660254`;
the difference is 4.9 × 10⁻⁵ of a unit, about two thousandths of a texel at 32 pixels per unit.
Match what the rest of the project already uses instead of changing it — a palette and the tilemaps
painted from it must agree, and a "corrected" constant introduces a mismatch that shows up as a
slow drift across a large map.

Flat-top hexagons need the ratio on the other axis. There is no separate `CellLayout` for them:
it is `Hexagon` with the swizzle changed, and the cell size transposed with it.

### The isometric sort axis is not optional

`CustomAxis` with `(0, 0, 1)` tells the renderer to order transparent geometry along z. Leave
`sortMode` at `Default` on an isometric palette and tiles further back draw over tiles in front —
an isometric scene that renders inside out. This is the argument pair the six-argument overload
cannot express, which is the whole reason to prefer the eight-argument one.

`IsometricZAsY` uses the same sort axis. What it changes is the cell addressing, not the sorting:
a tile's z coordinate also displaces it along y, which is how tile height is built. The palette
argument is identical.

## Verifying a palette after creation

`CreateNewPalette` returns the palette `GameObject`. That return value proves the call ran; it
does not prove the asset on disk is a usable palette. Two things have to be true:

1. The prefab carries a `Grid` component whose `cellLayout`, `cellSize` and `cellSwizzle` are
   what you asked for.
2. A `GridPalette` sub-asset exists inside the same asset. It is a `ScriptableObject` with a
   single public field, `cellSizing`, and it is what the Tile Palette window reads to
   decide whether to size cells from the art or from the grid. Without it the window has no
   sizing to show.

```csharp
var objs = UnityEditor.AssetDatabase.LoadAllAssetsAtPath(palettePath);
int gridPalettes = 0; string gridInfo = "no Grid";
foreach (var o in objs)
{
    if (o is UnityEditor.GridPalette) gridPalettes++;
    if (o is UnityEngine.GameObject go && go.GetComponent<UnityEngine.Grid>() is var g && g != null)
        gridInfo = g.cellLayout + " " + g.cellSize + " " + g.cellSwizzle;
}
return gridPalettes + " GridPalette(s); " + gridInfo;   // expect exactly 1
```

Run it the first time you create a palette in a project and keep the output.

`folderPath` must already exist. Creating a palette does not create its directory, and the
failure is not loud.

## One palette, one layout

The layout is serialised into the palette prefab's `Grid`. A palette cannot be converted: a
rectangular palette dropped onto a hexagonal tilemap paints, and every cell lands in the wrong
place. Projects with two grid shapes need two palettes, and the tiles are not interchangeable
either — `RuleTile`, `HexagonalRuleTile` and `IsometricRuleTile` compute neighbours differently.
