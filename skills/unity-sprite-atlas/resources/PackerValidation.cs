#if UNITY_EDITOR
// The checks a custom packer runs on its own output before returning true.
//
// A ScriptablePacker reports success by returning a bool, and the importer takes that
// answer at its word: a sprite left at a negative coordinate, on a page that does not
// exist, or overlapping its neighbour produces an atlas that imports cleanly and draws
// the wrong pixels. Nothing downstream re-checks the layout, so check it here.
//
// Used by MultiPagePacker.cs and SizeOptimizedPacker.cs; drop it beside any packer of
// your own. Read ScriptablePackerExample.cs for the shape of the nested types these
// methods take — PackerData, SpriteData and SpritePack are all ScriptablePacker.<Name>.
using System.Text;
using UnityEngine;
using Unity.Collections;
using PackerData = UnityEditor.U2D.ScriptablePacker.PackerData;
using SpriteData = UnityEditor.U2D.ScriptablePacker.SpriteData;

public static class PackerValidation
{
    /// <summary>
    /// Every sprite sits at a non-negative position, on a page inside the range the packer
    /// says it used, and inside the page. Logs each failure with the sprite's index — the
    /// only handle the pack operation gives you, since SpriteData.guid is an int local to
    /// the operation and not something AssetDatabase can look up.
    /// </summary>
    /// <param name="pages">how many pages the packer opened; page indices run 0..pages-1</param>
    /// <param name="limit">the page size the packer laid out against, in pixels</param>
    public static bool OutputsAreOnThePage(PackerData input, int pages, int limit)
    {
        NativeArray<SpriteData> sprites = input.spriteData;
        int bad = 0;

        for (int i = 0; i < sprites.Length; i++)
        {
            SpriteData sprite = sprites[i];
            var output = sprite.output;

            if (output.x < 0 || output.y < 0)
                bad += Report(i, $"negative position ({output.x}, {output.y})");
            if (output.page < 0 || output.page >= pages)
                bad += Report(i, $"page {output.page} outside the {pages} page(s) packed");
            if (output.x + sprite.rect.width > limit || output.y + sprite.rect.height > limit)
                bad += Report(i, $"runs off a {limit}px page at ({output.x}, {output.y}) " +
                                 $"with size {sprite.rect.width}x{sprite.rect.height}");
        }

        return bad == 0;
    }

    /// <summary>
    /// Pairwise overlap, which catches the cursor arithmetic that forgot to advance. It is
    /// quadratic, so it is skipped above <paramref name="maxSprites"/> — run it while
    /// developing a packer and raise the cap deliberately, rather than shipping an import
    /// step that scans 4000 sprites against each other on every reimport.
    /// </summary>
    public static bool NoOverlaps(PackerData input, int maxSprites = 512)
    {
        NativeArray<SpriteData> sprites = input.spriteData;
        if (sprites.Length > maxSprites)
        {
            Debug.Log($"[atlas] overlap check skipped: {sprites.Length} sprites is over the {maxSprites} cap.");
            return true;
        }

        int bad = 0;
        for (int i = 0; i < sprites.Length; i++)
        for (int j = i + 1; j < sprites.Length; j++)
        {
            SpriteData a = sprites[i], b = sprites[j];
            if (a.output.page != b.output.page) continue;
            bool apart = a.output.x + a.rect.width  <= b.output.x ||
                         b.output.x + b.rect.width  <= a.output.x ||
                         a.output.y + a.rect.height <= b.output.y ||
                         b.output.y + b.rect.height <= a.output.y;
            if (!apart) bad += Report(i, $"overlaps sprite {j} on page {a.output.page}");
        }

        return bad == 0;
    }

    /// <summary>
    /// One line to log once a pack succeeds: how many sprites landed, how many pages they
    /// landed on, and the count per page. A pack that quietly put everything on page 0 and
    /// a pack that spread evenly both "succeed"; this is how you tell them apart.
    /// </summary>
    public static string Describe(PackerData input, int pages)
    {
        NativeArray<SpriteData> sprites = input.spriteData;
        var perPage = new int[Mathf.Max(pages, 1)];
        for (int i = 0; i < sprites.Length; i++)
        {
            int page = sprites[i].output.page;
            if (page >= 0 && page < perPage.Length) perPage[page]++;
        }

        var line = new StringBuilder($"[atlas] packed={sprites.Length} pages={pages} perPage=");
        for (int p = 0; p < perPage.Length; p++)
        {
            if (p > 0) line.Append(',');
            line.Append(perPage[p]);
        }
        return line.ToString();
    }

    static int Report(int index, string what)
    {
        Debug.LogError($"[atlas] sprite {index}: {what}.");
        return 1;
    }
}
#endif
