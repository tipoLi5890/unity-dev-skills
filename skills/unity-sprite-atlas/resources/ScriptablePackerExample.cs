#if UNITY_EDITOR
// A custom atlas packer, and how to attach one.
//
// Reach for this only when the built-in packer cannot produce the layout something downstream
// requires — a fixed grid a shader indexes into, a page split you control, an ordering an external
// tool expects. For "make the atlas smaller", tune padding and tight packing first; a hand-written
// packer will not beat the built-in one at that and it runs on every import.
//
// The shape of the type, which the code below depends on:
//
//   * ScriptablePacker derives from ScriptableObject, so instances come from CreateInstance<T>().
//   * Pack is public abstract; Fit is PROTECTED virtual. The accessibility is not symmetric, and
//     C# will not let an override widen it, so "public override bool Fit" does not compile.
//   * PackerData, SpriteData, SpritePack, TextureData and PackTransform are NESTED inside
//     ScriptablePacker. They are not free types in UnityEditor.U2D, and qualifying them as if
//     they were is the usual reason a packer will not resolve.
//   * SpriteData.guid is an int, not a GUID — a handle inside this pack operation, not something
//     AssetDatabase can look up.
//   * TextureData carries width, height AND bufferOffset, the index where that texture's pixels
//     begin inside PackerData.colorData. Reading colorData without it reads the wrong texture.
//   * SpriteAtlasAsset.SetScriptablePacker takes a ScriptablePacker, not a plain Object.
using UnityEditor;
using UnityEditor.U2D;
using UnityEngine;
using Unity.Collections;
using Object = UnityEngine.Object;

/// <summary>
/// Lays every sprite out on a fixed grid, in the order the importer supplies them. Predictable
/// rather than tight: a cell index maps to a position with arithmetic, which is what makes this
/// worth writing at all.
/// </summary>
[CreateAssetMenu(menuName = "Unity Dev/Sprite Atlas/Grid Packer")]
public sealed class GridAtlasPacker : ScriptablePacker
{
    [SerializeField] int columns  = 8;
    [SerializeField] int cellSize = 128;
    [SerializeField] int gutter   = 2;

    public override bool Pack(SpriteAtlasPackingSettings config,
                              SpriteAtlasTextureSettings setting,
                              PackerData input)
    {
        if (columns <= 0 || cellSize <= 0) return false;

        NativeArray<SpriteData> sprites = input.spriteData;
        int limit = setting.maxTextureSize;

        for (int i = 0; i < sprites.Length; i++)
        {
            // The indexer hands back a copy. Assigning into sprites[i].output directly is a
            // compile error; copying into a local and forgetting the write-back below is worse,
            // because that one is silent.
            SpriteData sprite = sprites[i];

            int column = i % columns;
            int row    = i / columns;

            int x = gutter + column * (cellSize + gutter);
            int y = gutter + row    * (cellSize + gutter);

            // A sprite placed off the page is not reported as an error later — it is simply gone.
            if (x + sprite.rect.width > limit || y + sprite.rect.height > limit)
            {
                Debug.LogError($"[atlas] grid packer overflowed {limit}px at sprite {i}; widen the atlas or shrink the cell.");
                return false;
            }

            sprite.output.x    = x;
            sprite.output.y    = y;
            sprite.output.page = 0;
            sprite.output.rot  = PackTransform.None;

            sprites[i] = sprite;   // the write-back
        }

        return true;
    }

    /// <summary>
    /// The optional cheap pre-check: answer whether the sprites fit without laying them out.
    /// The base member is virtual, protected, and returns bool over these three parameters.
    /// The signature does not say what the importer does with the answer — whether false means
    /// "will not fit, refuse" or "no opinion, pack anyway" — so return the honest arithmetic and
    /// do not lean on either reading.
    /// </summary>
    protected override bool Fit(SpriteAtlasPackingSettings config,
                                SpriteAtlasTextureSettings setting,
                                PackerData input)
    {
        int perPage = Mathf.Max(1, setting.maxTextureSize / (cellSize + gutter));
        return input.spriteData.Length <= perPage * columns;
    }
}

/// <summary>Attaching a packer to an atlas — the two-pass V2 shape, with one extra call.</summary>
public static class GridAtlasPackerSetup
{
    public static void Build(string atlasPath, string spriteFolder, GridAtlasPacker packer)
    {
        var sprites = System.Array.ConvertAll(
            AssetDatabase.FindAssets("t:Sprite", new[] { spriteFolder }),   // scoped: see common-errors.md
            guid => (Object)AssetDatabase.LoadAssetAtPath<Sprite>(AssetDatabase.GUIDToAssetPath(guid)));

        var asset = new SpriteAtlasAsset();
        asset.Add(sprites);
        asset.SetScriptablePacker(packer);     // before the save, or it is not part of the asset

        SpriteAtlasAsset.Save(asset, atlasPath);
        AssetDatabase.ImportAsset(atlasPath);

        var importer = AssetImporter.GetAtPath(atlasPath) as SpriteAtlasImporter;
        if (importer == null)
            throw new System.Exception($"no SpriteAtlasImporter at {atlasPath}");

        importer.includeInBuild = true;
        importer.SaveAndReimport();
    }

    /// <summary>
    /// Persist the packer as an asset and reference that. A CreateInstance instance is not saved
    /// anywhere, so it does not survive a domain reload and the atlas is left holding a dead
    /// packer reference — saving it costs one line.
    /// </summary>
    public static GridAtlasPacker CreatePackerAsset(string packerPath)
    {
        var packer = ScriptableObject.CreateInstance<GridAtlasPacker>();
        AssetDatabase.CreateAsset(packer, packerPath);
        AssetDatabase.SaveAssets();
        return packer;
    }
}
#endif
