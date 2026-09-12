// Grid-slice a sprite sheet through the importer's data provider.
// Project-agnostic: pass the asset path and cell size, nothing is hardcoded.
//
// REQUIRES the com.unity.2d.sprite package. Without it these types do not exist
// and this file does not compile — that is not a runtime failure you can catch.
//
// Run it from a live Editor via `unity command eval` (strip the usings and fully
// qualify — note SpriteRect and SpriteNameFileIdPair are UnityEditor.*, NOT
// UnityEditor.U2D.Sprites.*, and GUID is UnityEngine.GUID), or drop it in an
// Editor folder and call SliceSheet.Run(...).
//
// If that Editor folder is covered by an .asmdef, add "Unity.2D.Sprite.Editor" to
// its references or none of these types resolve — the error reads as a missing
// package, not a missing reference.
//
// Run() ends on the acceptance test (SKILL.md §6): e.g. a 128x64 sheet cut at 32x32
// must come out as 8 named Sprite sub-assets with pivot (0.5, 0), and it throws when the
// sprite count differs from the rects written.
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.U2D.Sprites;
using UnityEngine;

public static class SliceSheet
{
    /// <param name="assetPath">e.g. "Assets/Art/hero.png"</param>
    /// <param name="cell">cell size in pixels</param>
    /// <param name="pivot">normalised pivot; (0.5f, 0f) puts feet on the ground</param>
    /// <param name="namePrefix">frames become "<prefix>_000"; name them here, not later</param>
    public static void Run(string assetPath, Vector2Int cell, Vector2 pivot, string namePrefix)
    {
        var importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
        if (importer == null) throw new System.Exception($"No TextureImporter at {assetPath}");

        // A plain .png imports as textureType Default with spriteImportMode None.
        // Setting the mode alone is not enough — both, then re-fetch.
        if (importer.textureType != TextureImporterType.Sprite ||
            importer.spriteImportMode != SpriteImportMode.Multiple)
        {
            importer.textureType      = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Multiple;
            importer.SaveAndReimport();
            importer = (TextureImporter)AssetImporter.GetAtPath(assetPath);
        }

        var factory = new SpriteDataProviderFactories();
        factory.Init();
        var dp = factory.GetSpriteEditorDataProviderFromObject(importer);
        // THIS is the check that actually fires: the factory returns null for an asset
        // with no sprite data. Skipping it turns a clear error into a NullReferenceException.
        if (dp == null)
            throw new System.Exception($"{assetPath} has no sprite data provider — aborted.");
        dp.InitSpriteEditorDataProvider();

        // --- capability gate ---
        // TextureImporter reports every capability true, so this never fires here.
        // It fires for PSBImporter and custom importers, where an unsupported edit is
        // accepted and corrupts the data. Four lines; keep them.
        var cap = dp.GetDataProvider<ISpriteFrameEditCapability>()
                  ?? throw new System.Exception("Importer exposes no edit capability — aborted.");
        var caps = cap.GetEditCapability();
        foreach (var needed in new[] { EEditCapability.CreateAndDeleteSprite,
                                       EEditCapability.EditSpriteName,
                                       EEditCapability.EditPivot })
            if (!caps.HasCapability(needed))
                throw new System.Exception($"Importer lacks {needed} — aborted.");

        // Read the real texture size from the provider; the file's size and the
        // imported size differ once max-size / compression have applied.
        var tex = dp.GetDataProvider<ITextureDataProvider>();
        tex.GetTextureActualWidthAndHeight(out int width, out int height);

        // A re-run over art that was already sliced must not hand an existing name a
        // fresh spriteID — every prefab, clip and asset serialised against it rebinds.
        // Reuse the rect the provider already holds; generate an ID only for new names.
        var existing = new Dictionary<string, SpriteRect>();
        foreach (var r in dp.GetSpriteRects()) existing[r.name] = r;

        var rects = new List<SpriteRect>();
        int index = 0;
        for (int y = height - cell.y; y >= 0; y -= cell.y)          // top-left reading order
        for (int x = 0; x + cell.x <= width; x += cell.x)
        {
            string name = $"{namePrefix}_{index:D3}";
            var rect = existing.TryGetValue(name, out var kept)
                ? kept                                              // keeps spriteID
                : new SpriteRect { name = name, spriteID = GUID.Generate() };
            rect.rect      = new Rect(x, y, cell.x, cell.y);
            rect.alignment = SpriteAlignment.Custom;                // enum, never a magic number
            rect.pivot     = pivot;                                 // ignored unless alignment is Custom
            rects.Add(rect);
            index++;
        }

        dp.SetSpriteRects(rects.ToArray());

        // Unity 2021.2+: adding/removing sprites must also update the name<->fileID map,
        // or existing references silently rebind to the wrong sprite.
        var nameMap = dp.GetDataProvider<ISpriteNameFileIdDataProvider>();
        if (nameMap != null)
        {
            var pairs = new List<SpriteNameFileIdPair>();
            foreach (var r in rects) pairs.Add(new SpriteNameFileIdPair(r.name, r.spriteID));
            nameMap.SetNameFileIdPairs(pairs);
        }

        dp.Apply();
        importer.SaveAndReimport();      // nothing above persists without this

        // Acceptance test: rects in the provider are not sprites. Count the real
        // sub-assets, and fail loudly if the asset did not end up with them.
        int made = 0;
        foreach (var o in AssetDatabase.LoadAllAssetsAtPath(assetPath))
            if (o is Sprite) made++;
        if (made != rects.Count)
            throw new System.Exception(
                $"[SliceSheet] wrote {rects.Count} rects but the asset has {made} sprites.");
        Debug.Log($"[SliceSheet] {assetPath}: {made} sprites at {cell.x}x{cell.y}");
    }
}
