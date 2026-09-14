// Cut a diamond (isometric) tile sheet into sprite rects through the importer's
// data provider, and give each tile a diamond outline.
//
// Same shape as SliceSheet.cs, and the same two gates in the same order: a null
// data provider first, the edit-capability check second. Read that file before
// this one — everything it says about com.unity.2d.sprite, the asmdef reference
// "Unity.2D.Sprite.Editor", and SpriteRect / SpriteNameFileIdPair living under
// UnityEditor rather than UnityEditor.U2D.Sprites applies here unchanged.
//
// Three things this file adds over the grid slicer:
//   1. rows step by half a cell height and alternate a half-cell horizontal
//      offset, which is what makes the diamonds tessellate;
//   2. a cell whose diamond area is almost entirely transparent is dropped, so a
//      sparse sheet does not publish dozens of empty sprites;
//   3. rects can replace, update or be added beside what the sheet already has —
//      see RectMode. Only rects this run created or moved get a pivot and an
//      outline written; the rest of the sheet is carried through untouched.
//
// Signatures this depends on, read off the assembly rather than recalled:
//   ISpriteOutlineDataProvider.SetOutlines(UnityEngine.GUID, List<Vector2[]>)
//   ITextureDataProvider.GetTextureActualWidthAndHeight(out int, out int)
// It compiles against the Editor assemblies plus Unity.2D.Sprite.Editor. A compile is not
// a slice: check the first real isometric sheet against SKILL.md §6's acceptance test.
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.U2D.Sprites;
using UnityEngine;

public static class IsometricSliceSheet
{
    /// <summary>What to do about rects the sheet already carries.</summary>
    public enum RectMode
    {
        /// <summary>Throw the old rects away. Every sprite gets a new identity.</summary>
        ReplaceAll,
        /// <summary>
        /// Move an overlapping existing rect onto the new cell, add the rest. Each existing
        /// rect can be claimed by one cell only — isometric cells overlap each other, so
        /// without that the same rect would be emitted twice under two names.
        /// </summary>
        UpdateOverlapping,
        /// <summary>
        /// Keep every existing rect exactly as the sheet holds it — geometry, name, pivot
        /// and outline — and add only cells that hit nothing.
        /// </summary>
        AddNonOverlapping,
    }

    /// <param name="assetPath">e.g. "Assets/Art/tiles.png"</param>
    /// <param name="cell">diamond bounding box in pixels — width is the full diagonal</param>
    /// <param name="offset">where the first cell starts, measured from the top-left</param>
    /// <param name="pivot">normalised pivot inside each rect</param>
    /// <param name="mode">how to treat rects that are already there</param>
    /// <param name="namePrefix">cells become "<prefix>_000"; name them now, not later</param>
    /// <param name="staggerFirstRow">start row 0 half a cell to the right</param>
    /// <param name="keepEmptyCells">publish cells whose diamond is transparent</param>
    /// <param name="overlapTolerance">a candidate smaller than this area is not a cell at all</param>
    public static void Run(string assetPath, Vector2 cell, Vector2 offset, Vector2 pivot,
                           RectMode mode, string namePrefix,
                           bool staggerFirstRow = false, bool keepEmptyCells = false,
                           float overlapTolerance = 0.00001f)
    {
        var importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
        if (importer == null) throw new System.Exception($"No TextureImporter at {assetPath}");

        // textureType and spriteImportMode both, then re-fetch: a plain .png arrives
        // as Default/None and setting the mode alone changes nothing.
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
        // The factory hands back null for anything that is not a sprite asset. This is
        // the check that fires first in practice; without it the next line is an NRE.
        if (dp == null)
            throw new System.Exception($"{assetPath} has no sprite data provider — aborted.");
        dp.InitSpriteEditorDataProvider();

        // TextureImporter answers true to every capability, so this gate is quiet here.
        // It earns its four lines on PSBImporter and custom importers, where an edit the
        // importer does not support is accepted and corrupts the data instead of failing.
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
        var texture = ReadableAtSourceSize(texProvider, out bool ownsTexture);
        if (texture == null)
            throw new System.Exception($"{assetPath} yielded no readable texture — aborted.");

        List<Rect> cells;
        try
        {
            cells = new List<Rect>(DiamondCells(texture, cell, offset, staggerFirstRow, keepEmptyCells));
        }
        finally
        {
            // The blit copy is ours; the provider's own readable texture is not. Leaking it
            // costs a full-resolution texture per run in a long-lived Editor session.
            if (ownsTexture) UnityEngine.Object.DestroyImmediate(texture);
        }

        var touched = new List<SpriteRect>();       // created or moved by this run
        var rects = Merge(dp, cells, mode, namePrefix, overlapTolerance, touched);
        // Pivot goes on the touched subset only. SpriteRect is a reference type (a class, not
        // a struct), so writing over the whole list would reach into the rects the provider
        // still holds and flatten the hand-tuned pivots AddNonOverlapping exists to preserve.
        foreach (var r in touched)
        {
            r.alignment = SpriteAlignment.Custom;   // enum, never the raw number
            r.pivot     = pivot;                    // ignored unless alignment is Custom
        }
        dp.SetSpriteRects(rects.ToArray());

        // A diamond render outline, expressed around the centre of the cell, so the
        // renderer stops drawing the transparent corners each tile carries.
        var outlineProvider = dp.GetDataProvider<ISpriteOutlineDataProvider>();
        if (outlineProvider != null)
        {
            var diamond = new List<Vector2[]>(1)
            {
                new[]
                {
                    new Vector2(0f, -cell.y / 2f),
                    new Vector2(cell.x / 2f, 0f),
                    new Vector2(0f, cell.y / 2f),
                    new Vector2(-cell.x / 2f, 0f),
                }
            };
            // Same subset as the pivot: a rect the run did not place keeps its own outline.
            foreach (var r in touched) outlineProvider.SetOutlines(r.spriteID, diamond);
        }

        // 2021.2+: the name<->fileID map moves with the rects, or serialised
        // references rebind to whichever sprite now sits at that id.
        var nameMap = dp.GetDataProvider<ISpriteNameFileIdDataProvider>();
        if (nameMap != null)
        {
            var pairs = new List<SpriteNameFileIdPair>(rects.Count);
            foreach (var r in rects) pairs.Add(new SpriteNameFileIdPair(r.name, r.spriteID));
            nameMap.SetNameFileIdPairs(pairs);
        }

        dp.Apply();
        importer.SaveAndReimport();     // nothing above survives without this

        // Rects in the provider are not sprites. Count the sub-assets that exist now.
        int made = 0;
        foreach (var o in AssetDatabase.LoadAllAssetsAtPath(assetPath))
            if (o is Sprite) made++;
        if (made != rects.Count)
            throw new System.Exception(
                $"[IsometricSliceSheet] wrote {rects.Count} rects but the asset has {made} sprites.");
        Debug.Log($"[IsometricSliceSheet] {assetPath}: {made} tiles at {cell.x}x{cell.y} ({mode})");
    }

    // --- the diamond walk -------------------------------------------------------

    /// <summary>
    /// Walk the sheet in diamond order: full-width steps across a row, half-height
    /// steps down, alternating a half-width shift so neighbouring rows interlock.
    /// </summary>
    static IEnumerable<Rect> DiamondCells(Texture2D tex, Vector2 cell, Vector2 offset,
                                          bool staggerFirstRow, bool keepEmptyCells)
    {
        // One bool per pixel beats a GetPixels32 call per cell; the sheets this runs
        // over are large and the cells overlap in y.
        var pixels = tex.GetPixels32();
        var opaque = new bool[pixels.Length];
        for (int i = 0; i < pixels.Length; i++) opaque[i] = pixels[i].a != 0;

        float slope = (cell.x / 2f) / (cell.y / 2f);   // pixels of inset per row of the diamond
        bool stagger = staggerFirstRow;
        float x = offset.x + (stagger ? cell.x / 2f : 0f);
        float y = tex.height - offset.y;

        while (y - cell.y >= 0)
        {
            while (x + cell.x <= tex.width)
            {
                var rect = new Rect(x, y - cell.y, cell.x, cell.y);
                if (keepEmptyCells || DiamondHasInk(tex, opaque, rect, cell, slope))
                    yield return rect;
                x += cell.x;
            }
            stagger = !stagger;
            x = offset.x + (stagger ? cell.x / 2f : 0f);
            y -= cell.y / 2f;                          // rows overlap by half a cell
        }
    }

    /// <summary>
    /// Sample only the pixels inside the diamond, top and bottom half together, and
    /// report whether more than 1% of them are non-transparent. A grid slicer would
    /// count the transparent corners and keep every empty cell.
    /// </summary>
    static bool DiamondHasInk(Texture2D tex, bool[] opaque, Rect rect, Vector2 cell, float slope)
    {
        int sx = (int)rect.x, sy = (int)rect.y;
        int w = (int)cell.x;
        int odd = ((int)cell.y) % 2;
        int topRow = ((int)cell.y / 2) - 1;
        int bottomRow = topRow + odd;
        int sampled = 0, inked = 0;

        for (int row = 0; row <= topRow; row++)
        {
            int inset = Mathf.CeilToInt(slope * row);   // the diamond narrows as it rises
            for (int col = inset; col < w - inset; col++)
            {
                if (HasAlpha(opaque, tex.width, sx + col, sy + topRow - row)) inked++;
                if (HasAlpha(opaque, tex.width, sx + col, sy + bottomRow + row)) inked++;
                sampled += 2;
            }
        }

        if (odd > 0)                                    // an odd height leaves one middle row
        {
            int row = topRow + 1;
            for (int col = 0; col < w; col++)
            {
                if (HasAlpha(opaque, tex.width, sx + col, sy + row)) inked++;
                sampled++;
            }
        }

        return sampled > 0 && (float)inked / sampled > 0.01f;
    }

    static bool HasAlpha(bool[] opaque, int width, int x, int y)
    {
        int i = y * width + x;
        return i >= 0 && i < opaque.Length && opaque[i];
    }

    // --- rect management --------------------------------------------------------

    /// <summary>
    /// Fold the freshly walked cells into whatever the sheet already holds, under one of
    /// the three modes. UpdateOverlapping is the one that keeps identities: an existing
    /// rect that overlaps a new cell is moved onto it, spriteID intact. Returns the whole
    /// list to write back, and appends to <paramref name="touched"/> the subset this run
    /// created or moved — the caller writes pivots and outlines to that subset only.
    /// </summary>
    static List<SpriteRect> Merge(ISpriteEditorDataProvider dp, List<Rect> cells, RectMode mode,
                                  string namePrefix, float overlapTolerance,
                                  List<SpriteRect> touched)
    {
        var existing = new List<SpriteRect>(dp.GetSpriteRects());
        var taken = new HashSet<string>();
        var claimed = new HashSet<int>();       // indices of existing rects already moved
        var result = new List<SpriteRect>();
        int index = 0;

        if (mode == RectMode.AddNonOverlapping)
        {
            foreach (var r in existing) { taken.Add(r.name); result.Add(r); }
        }

        string NextName()
        {
            string n;
            do { n = $"{namePrefix}_{index:D3}"; index++; } while (taken.Contains(n));
            taken.Add(n);
            return n;
        }

        foreach (var cellRect in cells)
        {
            if (cellRect.width * cellRect.height < overlapTolerance) continue;

            int hit = mode == RectMode.ReplaceAll
                ? -1
                : FirstOverlapping(existing, cellRect, claimed);

            if (mode == RectMode.AddNonOverlapping)
            {
                if (hit == -1) result.Add(NewRect(NextName(), cellRect, touched));
                continue;                           // an existing rect is not read, not written
            }

            if (mode == RectMode.UpdateOverlapping && hit != -1)
            {
                var kept = existing[hit];
                claimed.Add(hit);                   // one cell per old rect, or it ships twice
                kept.rect = cellRect;               // identity survives; geometry moves
                // A kept name can still collide with the generated series (an old
                // "tile_003" beside a fresh prefix of "tile"), and duplicate names break
                // the name↔fileID map as surely as duplicate ids do.
                if (!taken.Add(kept.name)) kept.name = NextName();
                result.Add(kept);
                touched.Add(kept);
                continue;
            }

            result.Add(NewRect(NextName(), cellRect, touched));
        }

        return result;
    }

    static SpriteRect NewRect(string name, Rect rect, List<SpriteRect> touched)
    {
        var made = new SpriteRect { name = name, rect = rect, spriteID = GUID.Generate() };
        touched.Add(made);
        return made;
    }

    /// <summary>
    /// First existing rect that overlaps the candidate and has not already been moved onto
    /// another cell. The claimed set is the whole point: DiamondCells steps rows by half a
    /// cell height, so two neighbouring cells routinely hit one old rect, and returning it
    /// twice would put the same object — same spriteID — into the written list twice.
    /// </summary>
    static int FirstOverlapping(List<SpriteRect> existing, Rect candidate, HashSet<int> claimed)
    {
        for (int i = 0; i < existing.Count; i++)
            if (!claimed.Contains(i) && existing[i].rect.Overlaps(candidate)) return i;
        return -1;
    }

    // --- texture ----------------------------------------------------------------

    /// <summary>
    /// Slice against the source image's dimensions, not the imported texture's. A
    /// Max Size of 2048 on a 4096 sheet halves every coordinate, and the cells come
    /// out at half the size the artist authored. Blit back up when they differ.
    /// <paramref name="owned"/> comes back true only for the copy made here, which the
    /// caller must destroy; the provider's own texture belongs to the provider.
    /// </summary>
    static Texture2D ReadableAtSourceSize(ITextureDataProvider provider, out bool owned)
    {
        owned = false;
        provider.GetTextureActualWidthAndHeight(out int width, out int height);
        var readable = provider.GetReadableTexture2D();
        if (readable == null || (readable.width == width && readable.height == height))
            return readable;

        // The blit needs rectangular render-texture support. Where it is missing the copy
        // cannot be made at all, and silently carrying on would cut the sheet at the
        // imported size — half-size cells that look like a bad cell argument.
        if (!ShaderUtil.hardwareSupportsRectRenderTexture)
            throw new System.Exception(
                "Cannot blit this sheet back up to its source size on this Editor. Raise the " +
                "texture's Max Size to the source resolution and re-run.");

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
        // The empty-cell test reads alpha, so carry the source flag onto the copy: one that
        // lost it publishes cells the artist left blank.
        scaled.alphaIsTransparency = readable.alphaIsTransparency;

        RenderTexture.active = previous;
        RenderTexture.ReleaseTemporary(rt);
        owned = true;
        return scaled;
    }
}
