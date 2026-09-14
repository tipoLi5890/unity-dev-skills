#if UNITY_EDITOR
// One page, packed tallest-first so the wasted strip above each shelf stays small.
//
// Read ScriptablePackerExample.cs first: the shape of the type (Pack public, Fit protected,
// the nested data types, the NativeArray write-back) is stated there and assumed here.
//
// Two things worth knowing before reaching for this file:
//
//   * Sort by HEIGHT, not by area. Shelf packing wastes the band between a shelf's tallest
//     sprite and the shelf above it, so height is what decides the waste. Sorting by area
//     puts a wide short sprite ahead of a narrow tall one and opens exactly that gap.
//   * The built-in packer already does better than this on "make the atlas smaller".
//     Tune padding and tight packing first. A hand-written packer earns its place when the
//     LAYOUT has to be a particular shape, not when the atlas has to be tighter.
using UnityEditor.U2D;
using UnityEngine;
using Unity.Collections;

/// <summary>
/// Next-fit-decreasing-height shelf packing on a single page. Deterministic: the same set of
/// sprites produces the same layout whatever order the importer supplies them in, because the
/// sort key is the sprite's own geometry.
/// </summary>
[CreateAssetMenu(menuName = "Unity Dev/Sprite Atlas/Size Optimized Packer")]
public sealed class SizeOptimizedPacker : ScriptablePacker
{
    [SerializeField] int pageSize = 2048;
    [SerializeField] int gutter   = 4;

    public override bool Pack(SpriteAtlasPackingSettings config,
                              SpriteAtlasTextureSettings setting,
                              PackerData input)
    {
        int gap = Mathf.Max(gutter, config.padding);
        int limit = Mathf.Min(pageSize, setting.maxTextureSize);
        if (limit <= gap * 2)
        {
            Debug.LogError($"[atlas] page size {limit}px leaves no room once {gap}px of padding is applied.");
            return false;
        }

        NativeArray<SpriteData> sprites = input.spriteData;

        // Sort an index array rather than the NativeArray itself: the array is the
        // importer's, the packer only writes each element's output. Width breaks ties so the
        // order is total — two sprites of equal height must not swap between rebuilds.
        var order = new int[sprites.Length];
        for (int i = 0; i < order.Length; i++) order[i] = i;
        System.Array.Sort(order, (a, b) =>
        {
            SpriteData left = sprites[a], right = sprites[b];
            int byHeight = right.rect.height.CompareTo(left.rect.height);
            if (byHeight != 0) return byHeight;
            int byWidth = right.rect.width.CompareTo(left.rect.width);
            return byWidth != 0 ? byWidth : a.CompareTo(b);
        });

        int cursorX = gap;
        int shelfY = gap;
        int shelfHeight = 0;

        foreach (int index in order)
        {
            SpriteData sprite = sprites[index];
            int width  = sprite.rect.width;
            int height = sprite.rect.height;

            if (cursorX + width + gap > limit)      // next shelf
            {
                cursorX = gap;
                shelfY += shelfHeight + gap;
                shelfHeight = 0;
            }

            if (shelfY + height + gap > limit)
            {
                // A sprite placed off the page is not reported later — it is simply gone —
                // so refuse here, and say which of the three fixes applies.
                Debug.LogError($"[atlas] ran out of page at sprite index {index} ({width}x{height}) on a " +
                               $"{limit}px page. Raise the max texture size, split the atlas, or use " +
                               "MultiPagePacker.");
                return false;
            }

            sprite.output.x    = cursorX;
            sprite.output.y    = shelfY;
            sprite.output.page = 0;
            sprite.output.rot  = PackTransform.None;
            sprites[index] = sprite;                // the write-back

            cursorX += width + gap;
            shelfHeight = Mathf.Max(shelfHeight, height);
        }

        if (!PackerValidation.OutputsAreOnThePage(input, 1, limit)) return false;
        Debug.Log(PackerValidation.Describe(input, 1));
        return true;
    }

    /// <summary>
    /// Area against the page, which is a lower bound no shelf layout reaches. Return the
    /// honest arithmetic: the signature does not say whether the importer treats false as a
    /// refusal or as no opinion, so pack one atlas that fails this before depending on it.
    /// </summary>
    protected override bool Fit(SpriteAtlasPackingSettings config,
                                SpriteAtlasTextureSettings setting,
                                PackerData input)
    {
        int gap = Mathf.Max(gutter, config.padding);
        int limit = Mathf.Min(pageSize, setting.maxTextureSize);
        if (limit <= gap * 2) return false;

        long used = 0;
        NativeArray<SpriteData> sprites = input.spriteData;
        for (int i = 0; i < sprites.Length; i++)
        {
            SpriteData sprite = sprites[i];
            used += (long)(sprite.rect.width + gap) * (sprite.rect.height + gap);
        }
        return used <= (long)limit * limit;
    }
}
#endif
