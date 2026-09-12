// Survey and then repair the four texture import settings that decide whether pixel art
// stays sharp: filter mode, mipmaps, compression and pixels-per-unit.
//
// Editor-only. Drop into an Editor folder, or strip the usings and fully qualify to run a
// body through `unity command eval`.
//
// Surveying is free; fixing is not. A reimport rewrites .meta files and can take minutes
// over an art folder, so Survey() exists to be run and reported first. Nothing here sweeps
// the project on its own — the caller supplies the assets.
//
// Why these four: FilterMode.Bilinear is the import default, so every untouched sprite is
// on it — the default nobody chose and the most common reason pixel art looks soft. Mipmaps,
// compression and a mixed pixels-per-unit each blur or misalign the grid in their own way
// (SKILL.md section 2).
#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

public static class SpriteImportFix
{
    public struct Finding
    {
        public string path;
        public FilterMode filterMode;
        public bool mipmaps;
        public TextureImporterCompression compression;
        public float pixelsPerUnit;

        public bool NeedsWork(int targetPPU) =>
            filterMode != FilterMode.Point
            || mipmaps
            || compression != TextureImporterCompression.Uncompressed
            || !Mathf.Approximately(pixelsPerUnit, targetPPU);

        public override string ToString() =>
            $"{path}  filter={filterMode} mip={mipmaps} compression={compression} ppu={pixelsPerUnit}";
    }

    /// <summary>
    /// Read the current state of one texture. Returns false when the asset has no
    /// TextureImporter at all — a non-texture, or a path that does not exist.
    /// </summary>
    public static bool Survey(string assetPath, out Finding finding)
    {
        finding = default;
        var importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
        if (importer == null) return false;

        finding = new Finding
        {
            path = assetPath,
            filterMode = importer.filterMode,
            mipmaps = importer.mipmapEnabled,
            compression = importer.textureCompression,
            pixelsPerUnit = importer.spritePixelsPerUnit,
        };
        return true;
    }

    /// <summary>
    /// Apply the four settings and reimport. Returns false when there was nothing to import
    /// or nothing to change, so a batch can report a count that means something.
    /// </summary>
    public static bool Apply(string assetPath, int targetPPU)
    {
        var importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
        if (importer == null)
        {
            Debug.LogWarning($"No TextureImporter at {assetPath} — skipped.");
            return false;
        }

        if (Survey(assetPath, out var before) && !before.NeedsWork(targetPPU)) return false;

        importer.filterMode = FilterMode.Point;                            // bilinear is the default and the usual culprit
        importer.mipmapEnabled = false;                                    // a mip level is a pre-blurred texture
        importer.textureCompression = TextureImporterCompression.Uncompressed;  // block compression invents colours
        importer.spritePixelsPerUnit = targetPPU;                          // one value across the scene, or sprites disagree about pixel size

        // SaveAndReimport is where it becomes real; an assignment alone lives in memory and
        // evaporates. Re-fetch the importer before asserting on anything afterwards.
        importer.SaveAndReimport();
        return true;
    }

    /// <summary>
    /// Batch entry point. Survey everything, apply, then flush once — flushing per asset turns
    /// a slow pass into a much slower one.
    /// </summary>
    public static int ApplyAll(string[] assetPaths, int targetPPU)
    {
        int changed = 0;
        try
        {
            AssetDatabase.StartAssetEditing();
            foreach (var path in assetPaths)
                if (Apply(path, targetPPU)) changed++;
        }
        finally
        {
            AssetDatabase.StopAssetEditing();
        }

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        return changed;
    }

    /// <summary>
    /// Pivots are not set here — that is unity-2d-sprites' job, through the sprite data
    /// provider. This only flags the case that produces a half-pixel offset: a sprite whose
    /// pixel dimensions are odd, where a centre pivot lands between two pixels.
    /// </summary>
    public static bool HasOddDimensions(string assetPath)
    {
        var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(assetPath);
        return texture != null && (texture.width % 2 != 0 || texture.height % 2 != 0);
    }
}
#endif
