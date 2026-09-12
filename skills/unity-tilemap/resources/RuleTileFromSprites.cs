// Turn a folder of terrain sprites into a RuleTile that autotiles.
//
// The pipeline, per sprite: read its 3x3 pattern (SpriteGridAnalysis), keep it only if
// it is one of the known configurations, drop it if another sprite already claimed the
// same one, build a TilingRule from it, then sort the rules so the most constrained is
// tested first and hand the least constrained one's sprite to the tile as its default.
//
// REQUIRES com.unity.2d.tilemap.extras. Without it RuleTile does not exist and this
// file does not compile — that is not a runtime failure you can catch. On a project
// that did not ask for the package, RuleTile, UnityEngine.Tilemaps.RuleTile,
// HexagonalRuleTile and IsometricRuleTile all resolve to nothing across every loaded
// assembly.
//
// The field names this file uses are the package's serialised names; confirm them
// against the installed version before trusting a silent result.
//
// Creating a rule tile writes an asset. Report the rules you would generate — count,
// order and which sprite becomes the default — and wait for confirmation.
using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
// ColliderType is nested in UnityEngine.Tilemaps.Tile, and RuleTile comes from the extras
// package. A bare `using UnityEngine;` reaches neither: without the line below this file
// is CS0246 on the tile types, and the error reads as a missing package rather than a
// missing namespace.
using UnityEngine.Tilemaps;

public static class RuleTileFromSprites
{
    /// <summary>Pattern cell index to grid offset. Index 4 is the tile itself.</summary>
    static readonly Dictionary<int, Vector3Int> k_CellOffsets = new Dictionary<int, Vector3Int>
    {
        { 0, new Vector3Int(-1,  1, 0) },   // top-left
        { 1, new Vector3Int( 0,  1, 0) },   // top
        { 2, new Vector3Int( 1,  1, 0) },   // top-right
        { 3, new Vector3Int(-1,  0, 0) },   // left
                                            // 4 is the centre, never a neighbour
        { 5, new Vector3Int( 1,  0, 0) },   // right
        { 6, new Vector3Int(-1, -1, 0) },   // bottom-left
        { 7, new Vector3Int( 0, -1, 0) },   // bottom
        { 8, new Vector3Int( 1, -1, 0) },   // bottom-right
    };

    /// <summary>
    /// The tile configurations worth generating rules for, most constrained first.
    /// Anything else a sprite reports is noise — a decoration, a prop, an off-palette
    /// variant — and becomes a rule that fires on real geometry.
    ///
    /// There are 47 of them, and 47 is not a convention: any subset of the four edges
    /// may be required, and a corner only where both its adjacent edges already are,
    /// which enumerates to 1 + 4 + 8 + 2 + 16 + 16.
    /// The table in circulation mistypes one row — an inverse L pointing up, written
    /// "X . X / . * . / . . X" instead of "X . X / . * X / . . X" — and a set built
    /// from the typo rejects a real N/S/W-plus-SW sprite as unknown.
    /// </summary>
    static readonly HashSet<string> k_KnownPatterns = new HashSet<string>
    {
        // 8 required neighbours
        ". . . / . * . / . . .",
        // 7 required neighbours
        ". . . / . * . / . . X",
        ". . . / . * . / X . .",
        ". . X / . * . / . . .",
        "X . . / . * . / . . .",
        // 6 required neighbours
        ". . . / . * . / X . X",
        ". . X / . * . / . . X",
        ". . X / . * . / X . .",
        "X . . / . * . / . . X",
        "X . . / . * . / X . .",
        "X . X / . * . / . . .",
        // 5 required neighbours
        ". . . / . * . / X X X",
        ". . X / . * . / X . X",
        ". . X / . * X / . . X",
        "X . . / . * . / X . X",
        "X . . / X * . / X . .",
        "X . X / . * . / . . X",
        "X . X / . * . / X . .",
        "X X X / . * . / . . .",
        // 4 required neighbours
        ". . X / . * . / X X X",
        ". . X / . * X / X . X",
        "X . . / . * . / X X X",
        "X . . / X * . / X . X",
        "X . X / . * . / X . X",
        "X . X / . * X / . . X",
        "X . X / X * . / X . .",
        "X X X / . * . / . . X",
        "X X X / . * . / X . .",
        // 3 required neighbours
        ". . X / . * X / X X X",
        "X . . / X * . / X X X",
        "X . X / . * . / X X X",
        "X . X / . * X / X . X",
        "X . X / X * . / X . X",
        "X X X / . * . / X . X",
        "X X X / . * X / . . X",
        "X X X / X * . / X . .",
        // 2 required neighbours
        "X . X / . * X / X X X",
        "X . X / X * . / X X X",
        "X . X / X * X / X . X",
        "X X X / . * . / X X X",
        "X X X / . * X / X . X",
        "X X X / X * . / X . X",
        // 1 required neighbour
        "X . X / X * X / X X X",
        "X X X / . * X / X X X",
        "X X X / X * . / X X X",
        "X X X / X * X / X . X",
        // 0 required neighbours
        "X X X / X * X / X X X",
    };

    /// <summary>True if a pattern is one of the configurations above.</summary>
    public static bool IsKnownPattern(string pattern) => k_KnownPatterns.Contains(pattern);

    /// <summary>
    /// Analyse, filter, deduplicate and order in one call. Returns the rules ready to
    /// apply; nothing is written until <see cref="Apply"/>.
    /// </summary>
    /// <param name="sprites">Sprites to read. Their texture must be readable.</param>
    /// <param name="matchThreshold">See SpriteGridAnalysis.</param>
    /// <param name="colorTolerance">See SpriteGridAnalysis.</param>
    /// <param name="filterToKnownPatterns">
    /// Leave on. Turning it off keeps whatever the analysis reported, including patterns
    /// no tile set has a shape for — make it an explicit request, not a default.
    /// </param>
    public static List<RuleTile.TilingRule> Build(
        IEnumerable<Sprite> sprites,
        float matchThreshold = 0.75f,
        float colorTolerance = 0.04f,
        bool filterToKnownPatterns = true)
    {
        var built = new List<(RuleTile.TilingRule rule, int required)>();
        var claimed = new HashSet<string>();

        foreach (var sprite in sprites)
        {
            string pattern = SpriteGridAnalysis.Analyze(sprite, matchThreshold, colorTolerance);
            if (pattern == null)
                continue;

            if (filterToKnownPatterns && !k_KnownPatterns.Contains(pattern))
            {
                Debug.Log($"[tilemap] '{sprite.name}' -> {pattern}: not a known configuration, skipped.");
                continue;
            }

            // First sprite wins. Several sprites analysing to the same pattern is normal
            // — variants of one edge — and a second rule with an identical neighbour set
            // could never fire anyway.
            if (!claimed.Add(pattern))
            {
                Debug.Log($"[tilemap] '{sprite.name}' -> {pattern}: already claimed, skipped.");
                continue;
            }

            built.Add(FromPattern(pattern, sprite));
        }

        // Most constrained first. An 8-neighbour rule placed below a 0-neighbour rule
        // never runs, and the whole tile paints one sprite.
        // OrderByDescending is stable, List.Sort is not: with a stable order the rules
        // that share a count keep the input order the dedup above promised, and the
        // generated asset is reproducible instead of re-diffing on every run.
        return built.OrderByDescending(x => x.required).Select(x => x.rule).ToList();
    }

    /// <summary>
    /// One rule from one pattern. The count returned is how many neighbours the rule
    /// asserts — always derived from the pattern, never taken from a table column.
    /// </summary>
    public static (RuleTile.TilingRule rule, int required) FromPattern(string pattern, Sprite sprite)
    {
        var cells = ParsePattern(pattern);
        var neighbors = new List<int>();
        var positions = new List<Vector3Int>();

        for (int i = 0; i < 9; i++)
        {
            if (i == 4) continue;                       // the tile itself
            // 'X' is don't-care, and don't-care is not a constant: the cell is
            // don't-care because its position never enters the lists at all.
            if (cells[i] != ".") continue;
            // Neighbor is declared on TilingRule, not on the TilingRuleOutput it derives
            // from; naming it through TilingRule resolves either way.
            neighbors.Add(RuleTile.TilingRule.Neighbor.This);
            positions.Add(k_CellOffsets[i]);
        }

        // One sprite per rule, single output. More than one sprite is animation —
        // a different feature, and not what an autotile wants.
        var rule = new RuleTile.TilingRule
        {
            m_Neighbors = neighbors,
            m_NeighborPositions = positions,
            m_Sprites = new[] { sprite },
            m_Output = RuleTile.TilingRuleOutput.OutputSprite.Single,
            m_ColliderType = Tile.ColliderType.Sprite,
            m_RuleTransform = RuleTile.TilingRuleOutput.Transform.Fixed,
        };

        return (rule, neighbors.Count);
    }

    /// <summary>Splits "T T T / L * R / B B B" into nine cells, top-left first.</summary>
    public static string[] ParsePattern(string pattern)
    {
        var rows = pattern.Split(new[] { " / " }, StringSplitOptions.None);
        if (rows.Length != 3)
            throw new ArgumentException($"Expected 3 rows, got {rows.Length}: {pattern}");

        var cells = new string[9];
        for (int row = 0; row < 3; row++)
        {
            var parts = rows[row].Split(' ');
            if (parts.Length != 3)
                throw new ArgumentException($"Row {row} needs 3 cells, got {parts.Length}: {rows[row]}");
            for (int col = 0; col < 3; col++)
                cells[row * 3 + col] = parts[col];
        }
        return cells;
    }

    /// <summary>
    /// Write the ordered rules onto a tile and give it a default sprite.
    /// </summary>
    public static void Apply(RuleTile tile, List<RuleTile.TilingRule> rules)
    {
        tile.m_TilingRules.Clear();
        tile.m_TilingRules.AddRange(rules);

        // What paints when nothing matched. After the sort that is the last rule — the
        // least constrained one — which is where the most generic art in the set ends up.
        var last = rules.Count > 0 ? rules[rules.Count - 1] : null;
        if (last != null && last.m_Sprites != null && last.m_Sprites.Length > 0)
            tile.m_DefaultSprite = last.m_Sprites[0];
    }

    /// <summary>
    /// The two-step form, for when the patterns need looking at before any rule exists.
    /// Log this, read it, then feed the sprites you kept back through <see cref="Build"/>.
    /// </summary>
    public static List<(string pattern, Sprite sprite)> Survey(
        IEnumerable<Sprite> sprites, float matchThreshold = 0.75f, float colorTolerance = 0.04f)
    {
        var found = new List<(string, Sprite)>();
        foreach (var sprite in sprites)
        {
            string pattern = SpriteGridAnalysis.Analyze(sprite, matchThreshold, colorTolerance);
            if (pattern != null) found.Add((pattern, sprite));
        }
        return found;
    }
}
