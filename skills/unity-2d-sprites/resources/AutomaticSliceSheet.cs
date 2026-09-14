// Slice a sheet the way the Sprite Editor's own Slice button does — by finding
// islands of opaque pixels, or on a grid that carries padding and an offset —
// and write the result through the same data provider as SliceSheet.cs.
//
// REQUIRES the com.unity.2d.sprite package. Without it these types do not exist and
// this file does not compile. Read SliceSheet.cs first: everything it says about the
// asmdef reference "Unity.2D.Sprite.Editor", about SpriteRect and SpriteNameFileIdPair
// living under UnityEditor rather than UnityEditor.U2D.Sprites, and about the two gates
// in their fixed order applies here unchanged.
//
// What this file adds over the grid walk in SliceSheet.cs is the rect *generator*:
//   UnityEditorInternal.InternalSpriteUtility.GenerateAutomaticSpriteRectangles(
//       Texture2D texture, int minRectSize, int extrudeSize)
//   UnityEditorInternal.InternalSpriteUtility.GenerateGridSpriteRectangles(
//       Texture2D texture, Vector2 offset, Vector2 size, Vector2 padding, bool keepEmptyRects)
// Both return Rect[] in the pixel space of the texture handed to them.
//
// CONFIRM ON YOUR VERSION before running this over an art folder: UnityEditorInternal is
// not part of the documented scripting API, so check that the type and both methods are
// still there, and still return Rect[]:
//
//   unity command eval 'var t = System.Type.GetType(
//     "UnityEditorInternal.InternalSpriteUtility, UnityEditor");
//     return t == null ? "absent" : string.Join(",", System.Array.ConvertAll(
//       t.GetMethods(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static),
//       m => m.Name));'
//
// When the grid generator is gone, SliceSheet.cs computes the same cells in plain
// arithmetic and nothing else here changes; the island detection has no substitute, so
// say so rather than approximating it with a grid.
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.U2D.Sprites;
using UnityEngine;

public static class AutomaticSliceSheet
{
    /// <summary>
    /// Detect frames as islands of non-transparent pixels. Right for an irregular sheet,
    /// wrong wherever two frames touch (they merge into one rect) or a frame has a detached
    /// element such as a dropped shadow or a spark (it splits into two).
    /// </summary>
    /// <param name="assetPath">e.g. "Assets/Art/runner.png"</param>
    /// <param name="namePrefix">frames become "&lt;prefix&gt;_000"; name them here, not later</param>
    /// <param name="pivot">normalised pivot; (0.5f, 0f) puts feet on the ground</param>
    /// <param name="minRectSize">islands smaller than this in either axis are discarded</param>
    /// <param name="extrudeSize">pixels to grow each detected rect by on every side</param>
    /// <param name="rowTolerance">
    /// how far two islands' top edges may differ and still count as the same row. Islands are
    /// rarely flush, so without this the names stop reading left-to-right along a row.
    /// </param>
    /// <param name="keepExisting">reuse the identity of rects that already overlap a frame</param>
    public static void Islands(string assetPath, string namePrefix, Vector2 pivot,
                               int minRectSize = 4, int extrudeSize = 0,
                               float rowTolerance = 8f, bool keepExisting = true)
    {
        Slice(assetPath, namePrefix, pivot, keepExisting, rowTolerance,
              texture => UnityEditorInternal.InternalSpriteUtility
                         .GenerateAutomaticSpriteRectangles(texture, minRectSize, extrudeSize));
    }

    /// <summary>
    /// Cut a grid that carries padding between cells and an offset before the first one —
    /// the case SliceSheet.cs's plain arithmetic does not cover. Empty cells are dropped
    /// unless <paramref name="keepEmptyCells"/> says otherwise, which is the difference
    /// between 8 usable frames and 64 mostly-transparent ones.
    /// </summary>
    /// <param name="cell">cell size in pixels</param>
    /// <param name="padding">gap between cells, both axes</param>
    /// <param name="offset">where the first cell starts</param>
    public static void Grid(string assetPath, string namePrefix, Vector2 pivot, Vector2 cell,
                            Vector2 padding = default, Vector2 offset = default,
                            bool keepEmptyCells = false, bool keepExisting = true)
    {
        if (cell.x <= 0f || cell.y <= 0f)
            throw new System.Exception($"[AutomaticSliceSheet] cell size {cell} is not a cell.");

        Slice(assetPath, namePrefix, pivot, keepExisting, 0f,
              texture => UnityEditorInternal.InternalSpriteUtility
                         .GenerateGridSpriteRectangles(texture, offset, cell, padding, keepEmptyCells));
    }

    // --- the one code path both entry points run ---------------------------------

    static void Slice(string assetPath, string namePrefix, Vector2 pivot, bool keepExisting,
                      float rowTolerance, System.Func<Texture2D, Rect[]> generate)
    {
        var importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
        if (importer == null) throw new System.Exception($"No TextureImporter at {assetPath}");

        // Both settings, then re-fetch: a plain .png arrives as Default/None and setting
        // the mode alone leaves the texture with no sprite data to edit.
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
        // The factory returns null for an asset with no sprite data, and that is the check
        // that fires first in practice — without it the next line is a NullReferenceException.
        if (dp == null)
            throw new System.Exception($"{assetPath} has no sprite data provider — aborted.");
        dp.InitSpriteEditorDataProvider();

        // TextureImporter answers true to every capability, so this gate is quiet here. It
        // earns its lines on PSBImporter and custom importers, where an unsupported edit is
        // accepted and corrupts the data rather than failing.
        var cap = dp.GetDataProvider<ISpriteFrameEditCapability>()
                  ?? throw new System.Exception("Importer exposes no edit capability — aborted.");
        var caps = cap.GetEditCapability();
        foreach (var needed in new[] { EEditCapability.CreateAndDeleteSprite,
                                       EEditCapability.EditSpriteName,
                                       EEditCapability.EditPivot })
            if (!caps.HasCapability(needed))
                throw new System.Exception($"Importer lacks {needed} — aborted.");

        var texProvider = dp.GetDataProvider<ITextureDataProvider>()
                          ?? throw new System.Exception("No texture data provider — aborted.");
        var texture = SourceSizeCopy(texProvider, out bool ownsTexture);
        if (texture == null)
            throw new System.Exception($"{assetPath} yielded no readable texture — aborted.");

        Rect[] frames;
        try
        {
            // Generate against the SOURCE dimensions. A Max Size of 2048 on a 4096 sheet
            // halves every coordinate the importer reports, and the frames come out at half
            // the size the artist authored.
            frames = generate(texture) ?? new Rect[0];
        }
        finally
        {
            // The blit copy is ours; the provider's own readable texture is not. Leaking it
            // costs a full-resolution texture per run in a long-lived Editor session.
            if (ownsTexture) UnityEngine.Object.DestroyImmediate(texture);
        }

        if (frames.Length == 0)
            throw new System.Exception(
                $"[AutomaticSliceSheet] {assetPath}: the generator found no frames — check the " +
                "alpha channel, the minimum rect size and the cell size before re-running.");

        SortIntoReadingOrder(frames, rowTolerance);

        var touched = new List<SpriteRect>();
        var rects = Merge(dp, frames, namePrefix, keepExisting, touched);

        // Pivot goes on the subset this run created or moved. SpriteRect is a class, so a
        // loop over the whole list reaches into the rects the provider still holds and
        // flattens pivots somebody tuned by hand in the Sprite Editor.
        foreach (var r in touched)
        {
            r.alignment = SpriteAlignment.Custom;   // enum, never the raw number
            r.pivot     = pivot;                    // ignored unless alignment is Custom
        }

        dp.SetSpriteRects(rects.ToArray());

        // 2021.2+: the name<->fileID map moves with the rects, or serialised references
        // rebind to whichever sprite now sits at that id.
        var nameMap = dp.GetDataProvider<ISpriteNameFileIdDataProvider>();
        if (nameMap != null)
        {
            var pairs = new List<SpriteNameFileIdPair>(rects.Count);
            foreach (var r in rects) pairs.Add(new SpriteNameFileIdPair(r.name, r.spriteID));
            nameMap.SetNameFileIdPairs(pairs);
        }

        dp.Apply();
        importer.SaveAndReimport();     // nothing above persists without this

        // Rects in the provider are not sprites. Count the sub-assets that exist now.
        int made = 0;
        foreach (var o in AssetDatabase.LoadAllAssetsAtPath(assetPath))
            if (o is Sprite) made++;
        if (made != rects.Count)
            throw new System.Exception(
                $"[AutomaticSliceSheet] wrote {rects.Count} rects but the asset has {made} sprites.");
        Debug.Log($"[AutomaticSliceSheet] {assetPath}: {made} sprites, {touched.Count} placed by this run");
    }

    /// <summary>
    /// Top-left reading order: rows from the top down, cells left to right inside a row.
    /// The generator's own order is not part of its contract, and the names are the API
    /// surface of the sheet, so sort before naming rather than after.
    /// </summary>
    static void SortIntoReadingOrder(Rect[] frames, float rowTolerance)
    {
        System.Array.Sort(frames, (a, b) =>
        {
            // Y increases upwards, so the top row has the largest yMax.
            if (Mathf.Abs(a.yMax - b.yMax) > rowTolerance) return b.yMax.CompareTo(a.yMax);
            return a.xMin.CompareTo(b.xMin);
        });
    }

    /// <summary>
    /// Fold the generated frames into whatever the sheet already holds. With
    /// <paramref name="keepExisting"/> an existing rect that overlaps a frame is moved onto
    /// it with its spriteID intact — the identity every prefab, clip and catalogue
    /// serialised against — and each existing rect may be claimed once only. Without it,
    /// every frame is new and every sprite gets a fresh GUID, which is the rebinding
    /// failure `reference/data-provider.md` §3 describes; use that only on art nothing
    /// references yet. Taking the first overlap is order-dependent as soon as the frames
    /// themselves overlap, so say which way a run went in its report.
    /// </summary>
    static List<SpriteRect> Merge(ISpriteEditorDataProvider dp, Rect[] frames, string namePrefix,
                                  bool keepExisting, List<SpriteRect> touched)
    {
        var existing = new List<SpriteRect>(dp.GetSpriteRects());
        var claimed = new HashSet<int>();
        var taken = new HashSet<string>();
        var result = new List<SpriteRect>(frames.Length);
        int index = 0;

        string NextName()
        {
            string n;
            do { n = $"{namePrefix}_{index:D3}"; index++; } while (!taken.Add(n));
            return n;
        }

        foreach (var frame in frames)
        {
            int hit = keepExisting ? FirstFreeOverlap(existing, frame, claimed) : -1;
            if (hit >= 0)
            {
                var kept = existing[hit];
                claimed.Add(hit);
                kept.rect = frame;                  // identity survives; geometry moves
                // A kept name can still collide with the generated series, and a duplicate
                // name breaks the name<->fileID map as surely as a duplicate id does.
                if (!taken.Add(kept.name)) kept.name = NextName();
                result.Add(kept);
                touched.Add(kept);
                continue;
            }

            var made = new SpriteRect { name = NextName(), rect = frame, spriteID = GUID.Generate() };
            result.Add(made);
            touched.Add(made);
        }

        return result;
    }

    static int FirstFreeOverlap(List<SpriteRect> existing, Rect candidate, HashSet<int> claimed)
    {
        if (candidate.width * candidate.height < 0.00001f) return -1;   // not a frame at all
        for (int i = 0; i < existing.Count; i++)
            if (!claimed.Contains(i) && existing[i].rect.Overlaps(candidate)) return i;
        return -1;
    }

    // --- texture ----------------------------------------------------------------

    /// <summary>
    /// A readable texture at the source image's dimensions. <paramref name="owned"/> comes
    /// back true only for the copy made here, which the caller destroys; the provider's own
    /// texture belongs to the provider. Hardware without rectangular render-texture support
    /// cannot make the copy at all — report that rather than slicing at the wrong scale.
    /// </summary>
    static Texture2D SourceSizeCopy(ITextureDataProvider provider, out bool owned)
    {
        owned = false;
        provider.GetTextureActualWidthAndHeight(out int width, out int height);
        var readable = provider.GetReadableTexture2D();
        if (readable == null || (readable.width == width && readable.height == height))
            return readable;

        if (!ShaderUtil.hardwareSupportsRectRenderTexture)
            throw new System.Exception(
                "This Editor cannot blit the sheet back up to its source size, so the frames " +
                "would be generated at the imported size. Raise the texture's Max Size to the " +
                "source resolution and re-run.");

        var previous = RenderTexture.active;
        var rt = RenderTexture.GetTemporary(width, height, 0, RenderTextureFormat.ARGB32);
        Graphics.Blit(readable, rt);
        RenderTexture.active = rt;

        var scaled = new Texture2D(width, height, TextureFormat.RGBA32, false)
        {
            hideFlags = HideFlags.HideAndDontSave,
        };
        scaled.ReadPixels(new Rect(0f, 0f, width, height), 0, 0);
        scaled.Apply();
        // Island detection reads alpha, so carry the source flag across: a copy that lost it
        // reports frames where the artist put none.
        scaled.alphaIsTransparency = readable.alphaIsTransparency;

        RenderTexture.active = previous;
        RenderTexture.ReleaseTemporary(rt);
        owned = true;
        return scaled;
    }
}
