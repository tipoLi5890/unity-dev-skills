// Create a Tile Palette asset for any of the four grid layouts.
//
// Project-agnostic: the folder and the name are arguments, nothing is hardcoded.
// Drop into an Editor folder, or strip the usings and paste into `unity command eval`
// (fully qualify — GridPaletteUtility is UnityEditor.Tilemaps, but GridPalette is
// bare UnityEditor, so one using directive is never enough).
//
// Requires com.unity.2d.tilemap, which is built into the Editor installation: it
// reports version 1.0.0 / source BuiltIn even where the manifest names it.
//
// CreateNewPalette exists as a 6-argument and an 8-argument overload, and only the
// long one carries the transparency sort mode and axis that isometric layouts need.
//
//   GameObject CreateNewPalette(string folderPath, string name,
//                               GridLayout.CellLayout layout,
//                               GridPalette.CellSizing cellSizing,
//                               Vector3 cellSize,
//                               GridLayout.CellSwizzle swizzle,
//                               TransparencySortMode sortMode,   // long overload only
//                               Vector3 sortAxis);               // long overload only
//
// Creating a palette writes assets into the project. Report what you would create,
// with folder, layout and cell size, and wait for confirmation before calling this.
using UnityEditor;
using UnityEditor.Tilemaps;
using UnityEngine;

public static class CreatePaletteTemplate
{
    // Pointy-top hexagon width as a fraction of its height. sqrt(3)/2 is 0.8660254;
    // the value below is the one already in circulation and sits 4.9e-5 under it,
    // far less than a texel. Match whatever the project's existing palettes use —
    // a palette and the tilemaps painted from it have to agree.
    const float k_HexWidthRatio = 0.8659766f;

    /// <summary>Flat rectangular grid. Cell size comes from the first sprite dropped in.</summary>
    public static GameObject CreateRectangular(string folderPath, string paletteName)
    {
        return GridPaletteUtility.CreateNewPalette(
            folderPath,
            paletteName,
            GridLayout.CellLayout.Rectangle,
            GridPalette.CellSizing.Automatic,   // discards the size below and measures the art
            new Vector3(1f, 1f, 0f),            // z is 0: a flat grid has no depth
            GridLayout.CellSwizzle.XYZ,
            TransparencySortMode.Default,
            new Vector3(0f, 0f, 1f));
    }

    /// <summary>
    /// Pointy-top hexagonal grid. Manual sizing is required: a hex cell is narrower
    /// than the sprite that draws it, so Automatic measures the wrong thing.
    /// </summary>
    public static GameObject CreateHexagonal(string folderPath, string paletteName)
    {
        return GridPaletteUtility.CreateNewPalette(
            folderPath,
            paletteName,
            GridLayout.CellLayout.Hexagon,
            GridPalette.CellSizing.Manual,
            new Vector3(k_HexWidthRatio, 1f, 1f),
            GridLayout.CellSwizzle.XYZ,
            TransparencySortMode.Default,
            new Vector3(0f, 0f, 1f));
    }

    /// <summary>
    /// Isometric grid. The last two arguments are the point of this overload: without
    /// CustomAxis along z, tiles further back draw over tiles in front.
    /// </summary>
    public static GameObject CreateIsometric(string folderPath, string paletteName)
    {
        return GridPaletteUtility.CreateNewPalette(
            folderPath,
            paletteName,
            GridLayout.CellLayout.Isometric,
            GridPalette.CellSizing.Manual,
            new Vector3(1f, 0.5f, 1f),          // half as tall as it is wide
            GridLayout.CellSwizzle.XYZ,
            TransparencySortMode.CustomAxis,
            new Vector3(0f, 0f, 1f));
    }

    /// <summary>
    /// Isometric grid where a tile's z coordinate also displaces it along y — the
    /// usual way tile height is faked. Same cell size and sort axis as Isometric;
    /// what changes is the cell addressing, not the sorting.
    /// </summary>
    public static GameObject CreateIsometricZAsY(string folderPath, string paletteName)
    {
        return GridPaletteUtility.CreateNewPalette(
            folderPath,
            paletteName,
            GridLayout.CellLayout.IsometricZAsY,
            GridPalette.CellSizing.Manual,
            new Vector3(1f, 0.5f, 1f),
            GridLayout.CellSwizzle.XYZ,
            TransparencySortMode.CustomAxis,
            new Vector3(0f, 0f, 1f));
    }

    /// <summary>Every argument exposed, for the case none of the four presets fits.</summary>
    /// <param name="folderPath">Project-relative folder, e.g. "Assets/Palettes". Must already exist.</param>
    public static GameObject Create(
        string folderPath,
        string paletteName,
        GridLayout.CellLayout layout,
        GridPalette.CellSizing cellSizing,
        Vector3 cellSize,
        GridLayout.CellSwizzle swizzle,
        TransparencySortMode sortMode,
        Vector3 sortAxis)
    {
        return GridPaletteUtility.CreateNewPalette(
            folderPath, paletteName, layout, cellSizing, cellSize, swizzle, sortMode, sortAxis);
    }

    /// <summary>
    /// Read the created asset back. The returned GameObject proves the call ran; this
    /// proves the asset is a usable palette. Expect exactly one GridPalette sub-asset —
    /// it is what the Tile Palette window reads to decide how to size cells.
    /// </summary>
    public static string Describe(string palettePath)
    {
        int gridPalettes = 0;
        string gridInfo = "no Grid component";
        foreach (var o in AssetDatabase.LoadAllAssetsAtPath(palettePath))
        {
            if (o is GridPalette) gridPalettes++;
            var go = o as GameObject;
            if (go == null) continue;
            var grid = go.GetComponent<Grid>();
            if (grid != null)
                gridInfo = grid.cellLayout + " " + grid.cellSize + " " + grid.cellSwizzle;
        }
        return gridPalettes + " GridPalette sub-asset(s); " + gridInfo;
    }
}

// Enum members, complete:
//
//   GridLayout.CellLayout    Rectangle, Hexagon, Isometric, IsometricZAsY
//   GridPalette.CellSizing   Automatic, Manual
//   GridLayout.CellSwizzle   XYZ, XZY, YXZ, YZX, ZXY, ZYX
//   TransparencySortMode     Default, Perspective, Orthographic, CustomAxis
//
// Four layouts and no more. A staggered or "2.5D" grid is one of these four plus a
// swizzle, or it is not a Unity grid.
//
// GridPaletteUtility also exposes CreateNewPaletteAtCurrentFolder at 5 and 7 arguments.
// It resolves the folder from the Project window's selection, which makes it unusable
// headlessly and non-deterministic interactively. Pass the folder.
