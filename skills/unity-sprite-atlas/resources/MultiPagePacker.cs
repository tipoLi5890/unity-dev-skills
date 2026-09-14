#if UNITY_EDITOR
// A custom packer that spills onto a second page instead of failing, and the page break
// is geometric: a new page starts when the next shelf would run off the bottom, not after
// a fixed number of sprites. A per-sprite cap is the version that looks right and packs
// badly — 64 small sprites fill a fraction of a 2048 page, 64 large ones never fitted.
//
// Read ScriptablePackerExample.cs first: the shape of the type (Pack public, Fit protected,
// the nested data types, the NativeArray write-back) is stated there and assumed here.
// Attach an instance the same way, with SpriteAtlasAsset.SetScriptablePacker.
//
// Multi-page output is what the built-in packer does when content exceeds the page size,
// so reach for this only when the page split itself has to be predictable — a page per
// character, a page per locale, a page an external tool indexes by number.
using UnityEditor.U2D;
using UnityEngine;
using Unity.Collections;

/// <summary>
/// Shelf-packs sprites in the order the importer supplies them, opening a new page when the
/// current one is full. Predictable rather than tight: sprite order decides the layout, so a
/// stable input order gives a stable atlas across rebuilds.
/// </summary>
[CreateAssetMenu(menuName = "Unity Dev/Sprite Atlas/Multi-page Packer")]
public sealed class MultiPagePacker : ScriptablePacker
{
    [SerializeField] int pageSize = 2048;
    [SerializeField] int gutter   = 4;
    [SerializeField] int maxPages = 4;

    public override bool Pack(SpriteAtlasPackingSettings config,
                              SpriteAtlasTextureSettings setting,
                              PackerData input)
    {
        // The importer's own padding is a setting, not something it applies to a custom
        // packer's output — whatever this method writes is the final position. Honour the
        // larger of the two so a project that raised padding to stop bleeding still gets it.
        int gap = Mathf.Max(gutter, config.padding);

        // maxTextureSize is read-only on the texture settings struct and is the per-platform
        // cap the atlas will actually be built at; never lay out past it.
        int limit = Mathf.Min(pageSize, setting.maxTextureSize);
        if (limit <= gap * 2)
        {
            Debug.LogError($"[atlas] page size {limit}px leaves no room once {gap}px of padding is applied.");
            return false;
        }

        NativeArray<SpriteData> sprites = input.spriteData;

        int page = 0;
        int cursorX = gap;
        int shelfY = gap;
        int shelfHeight = 0;

        for (int i = 0; i < sprites.Length; i++)
        {
            // The indexer hands back a copy. Edit the local, then write it back — forgetting
            // the write-back is the silent half of this API.
            SpriteData sprite = sprites[i];
            int width  = sprite.rect.width;
            int height = sprite.rect.height;

            if (width + gap * 2 > limit || height + gap * 2 > limit)
            {
                Debug.LogError($"[atlas] sprite {i} is {width}x{height}, larger than a {limit}px page " +
                               "once padding is applied; no page split can hold it.");
                return false;
            }

            if (cursorX + width + gap > limit)      // next shelf
            {
                cursorX = gap;
                shelfY += shelfHeight + gap;
                shelfHeight = 0;
            }

            if (shelfY + height + gap > limit)      // next page
            {
                page++;
                if (page >= maxPages)
                {
                    Debug.LogError($"[atlas] content needs more than {maxPages} pages at {limit}px. " +
                                   "Raise the page count, raise the page size, or split the atlas.");
                    return false;
                }
                cursorX = gap;
                shelfY = gap;
                shelfHeight = 0;
            }

            sprite.output.x    = cursorX;
            sprite.output.y    = shelfY;
            sprite.output.page = page;
            sprite.output.rot  = PackTransform.None;
            sprites[i] = sprite;                    // the write-back

            cursorX += width + gap;
            shelfHeight = Mathf.Max(shelfHeight, height);
        }

        int pages = page + 1;
        if (!PackerValidation.OutputsAreOnThePage(input, pages, limit)) return false;
        Debug.Log(PackerValidation.Describe(input, pages));
        return true;
    }

    /// <summary>
    /// The cheap pre-check. Area is a lower bound and shelf packing never reaches it, so this
    /// answers "could these possibly fit" rather than "will they". The base member is
    /// protected and virtual: an override cannot widen access to public.
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
        return used <= (long)limit * limit * maxPages;
    }
}
#endif
