// Recover a tile's shape from its own pixels.
//
// Segments a sprite into a 3x3 grid, takes the majority colour of the centre cell as
// the definition of "solid" for that sprite, and scores the other eight cells against
// it. The result is a one-line pattern that a TilingRule can be built from:
//
//     "T T T / L * R / B B B"      '.' = matches the centre   'X' = does not   '*' = centre
//
// No package beyond the built-in tilemap module is needed for this file — it only
// touches Sprite and Texture2D. It is Editor-time tooling all the same: the sprite's
// texture must have Read/Write Enabled, which doubles its memory, so turn the flag on
// for the run and off again afterwards. The rule tile it feeds stores sprite
// references, not pixels; none of this belongs in a build.
//
// This is a heuristic over pixels, not authored metadata. Log every sprite's pattern
// and read the list before applying it — reference/sprite-3x3-analysis.md has the
// three failure signatures and what each one means.
//
// The threshold and tolerance defaults below are starting points; tune them per tile set.
using System.Collections.Generic;
using UnityEngine;

public static class SpriteGridAnalysis
{
    /// <summary>
    /// Returns the 3x3 pattern for one sprite, e.g. "X X X / . * . / . . .".
    /// </summary>
    /// <param name="sprite">Sprite to read. Its texture must be readable.</param>
    /// <param name="matchThreshold">
    /// Share of a cell's pixels that must match the centre colour: 0.5 tolerates cells
    /// that are half transition, 0.75 is the working default, 0.9 suits flat-colour art.
    /// </param>
    /// <param name="colorTolerance">
    /// Per-channel RGB distance that still counts as the same colour. Raise the
    /// threshold before loosening this — a loose tolerance makes every sprite report
    /// the fully surrounded pattern, which reads as "the analysis did nothing".
    /// </param>
    public static string Analyze(Sprite sprite, float matchThreshold = 0.75f, float colorTolerance = 0.04f)
    {
        if (sprite == null) return null;
        var texture = sprite.texture;
        if (texture == null || !texture.isReadable)
        {
            Debug.LogError($"[tilemap] '{sprite.name}': texture is not " +
                           "readable. Enable Read/Write on its importer for the analysis run.");
            return null;
        }

        var rect = sprite.rect;
        int cellWidth = (int)(rect.width / 3);
        int cellHeight = (int)(rect.height / 3);
        if (cellWidth <= 0 || cellHeight <= 0)
        {
            Debug.LogError($"[tilemap] '{sprite.name}': {rect.width}x{rect.height} is too small " +
                           "to segment into a 3x3 grid.");
            return null;
        }

        // The centre cell defines "solid" for this sprite, so two terrains each analyse
        // against their own material and nothing has to be configured per tile set.
        Color centre = MajorityColor(texture,
            (int)rect.x + cellWidth, (int)rect.y + cellHeight, cellWidth, cellHeight);

        var symbols = new string[9];
        for (int row = 0; row < 3; row++)
        {
            for (int col = 0; col < 3; col++)
            {
                int index = row * 3 + col;
                if (index == 4) { symbols[index] = "*"; continue; }

                int startX = (int)rect.x + col * cellWidth;
                // Texture y grows upwards, the pattern string reads downwards. Drop this
                // inversion and every pattern comes out mirrored vertically — silently.
                int startY = (int)rect.y + (2 - row) * cellHeight;

                float share = MatchShare(texture, startX, startY, cellWidth, cellHeight,
                                         centre, colorTolerance);
                symbols[index] = share >= matchThreshold ? "." : "X";
            }
        }

        return $"{symbols[0]} {symbols[1]} {symbols[2]} / " +
               $"{symbols[3]} {symbols[4]} {symbols[5]} / " +
               $"{symbols[6]} {symbols[7]} {symbols[8]}";
    }

    /// <summary>Most frequent colour in a cell. Ties go to whichever was seen first.</summary>
    static Color MajorityColor(Texture2D texture, int startX, int startY, int width, int height)
    {
        // Keyed on the packed RGB value, alpha masked off: a struct key would fall back
        // to reflective equality and this loop runs once per pixel. Alpha is excluded so
        // that election and comparison use one notion of colour — Similar() below is RGB
        // only, and a histogram keyed on RGBA would split a fill that varies in alpha
        // across several buckets and let a minority RGB win the centre cell.
        var counts = new Dictionary<int, int>();
        int bestKey = 0, bestCount = -1;

        for (int y = startY; y < startY + height; y++)
        {
            for (int x = startX; x < startX + width; x++)
            {
                Color32 c = texture.GetPixel(x, y);
                int key = (c.r << 16) | (c.g << 8) | c.b;
                counts.TryGetValue(key, out int n);
                counts[key] = ++n;
                if (n > bestCount) { bestCount = n; bestKey = key; }
            }
        }

        return new Color32((byte)((bestKey >> 16) & 0xFF), (byte)((bestKey >> 8) & 0xFF),
                           (byte)(bestKey & 0xFF), 255);
    }

    /// <summary>Fraction of a cell's pixels within tolerance of the target colour.</summary>
    static float MatchShare(Texture2D texture, int startX, int startY, int width, int height,
                            Color target, float tolerance)
    {
        int total = 0, matching = 0;
        for (int y = startY; y < startY + height; y++)
        {
            for (int x = startX; x < startX + width; x++)
            {
                total++;
                if (Similar(texture.GetPixel(x, y), target, tolerance)) matching++;
            }
        }
        return total > 0 ? (float)matching / total : 0f;
    }

    // RGB only. That is right for terrain whose empty side is transparent, because a
    // transparent region's RGB rarely matches the material's. It is wrong for art where
    // the transparent pixels carry the material's RGB and differ only in alpha: every
    // cell then matches and every sprite reports fully surrounded. Add the alpha term
    // here if a tile set behaves that way — it is the fix, not a tolerance change.
    static bool Similar(Color a, Color b, float tolerance)
    {
        return Mathf.Abs(a.r - b.r) < tolerance
            && Mathf.Abs(a.g - b.g) < tolerance
            && Mathf.Abs(a.b - b.b) < tolerance;
    }
}
