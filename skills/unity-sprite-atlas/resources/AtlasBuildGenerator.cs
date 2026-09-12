#if UNITY_EDITOR
// Rebuilds the project's sprite atlases as part of every build.
//
// Drop into Assets/Scripts/Editor/. Nothing else has to run it: IPreprocessBuildWithReport
// fires before the player is built, so an atlas cannot go stale by somebody forgetting to
// click something. Edit Rules() below; leave the rest.
//
// Both delivery modes live here. includeInBuild: true packs the atlas into the player.
// includeInBuild: false hands delivery to Addressables, which needs two more files —
// AtlasContentBuild.cs (content build) and AtlasSupplier.cs (runtime supplier). All three,
// or none: an excluded atlas with nobody to deliver it is a build with invisible sprites
// and no error.
//
// The V2 authoring/configuration split is not optional: the asset has to be saved and imported
// before an importer exists to configure. See the skill's §3.
//
// SpritePackerMode.Disabled is the enum's zero value, so a project nobody configured packs
// nothing while looking entirely healthy. That is why OnPreprocessBuild reads the mode,
// corrects it only when it is not already a V2 value, and logs both readings. On the first
// build in a fresh clone that correction rewrites the tracked file
// ProjectSettings/EditorSettings.asset — expect a dirty working tree, and commit the new
// mode rather than reverting it, or the next build dirties it again.
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.U2D;
using UnityEngine;
using UnityEngine.U2D;
using Object = UnityEngine.Object;

#if UNITY_ADDRESSABLES
using UnityEditor.AddressableAssets;
using UnityEditor.AddressableAssets.Settings;
#endif

public sealed class AtlasBuildGenerator : IPreprocessBuildWithReport
{
    public int callbackOrder => 0;   // atlases first; the content build claims a higher order

    /// <summary>One atlas per rule. Source folder in, atlas path out.</summary>
    readonly struct Rule
    {
        public readonly string SourceFolder;
        public readonly string AtlasPath;
        public readonly string NamePrefix;   // null or empty means "every sprite in the folder"
        public readonly bool IncludeInBuild;

        public Rule(string sourceFolder, string atlasPath, bool includeInBuild, string namePrefix = null)
        {
            SourceFolder = sourceFolder;
            AtlasPath = atlasPath;
            NamePrefix = namePrefix;
            IncludeInBuild = includeInBuild;
        }
    }

    // ---- edit this, and only this ------------------------------------------------------------
    static IEnumerable<Rule> Rules()
    {
        yield return new Rule("Assets/Art/UI", "Assets/Atlases/UI.spriteatlasv2", includeInBuild: true);
        yield return new Rule("Assets/Art/Characters", "Assets/Atlases/Characters.spriteatlasv2", includeInBuild: true);
        yield return new Rule("Assets/Art/Items", "Assets/Atlases/Items.spriteatlasv2", includeInBuild: false, namePrefix: "item_");
    }
    // -------------------------------------------------------------------------------------------

    readonly List<string> _lateBound = new List<string>();

    public void OnPreprocessBuild(BuildReport report)
    {
        _lateBound.Clear();

        // Read before writing. Assigning spritePackerMode rewrites ProjectSettings/EditorSettings.asset,
        // so a build that only needed to check the setting should not dirty a tracked file.
        var before = EditorSettings.spritePackerMode;
        if (before != SpritePackerMode.SpriteAtlasV2 && before != SpritePackerMode.SpriteAtlasV2Build)
            EditorSettings.spritePackerMode = SpritePackerMode.SpriteAtlasV2;

        var mode = EditorSettings.spritePackerMode;          // read back; never trust the write
        if (mode == SpritePackerMode.Disabled)
            throw new BuildFailedException("Sprite packing is still Disabled — every atlas below would be empty.");
        Log(mode == before
            ? $"packer mode already {mode}; project settings untouched"
            : $"packer mode {before} -> {mode}; ProjectSettings/EditorSettings.asset was rewritten");

        foreach (var rule in Rules())
            Generate(rule);

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();

        if (_lateBound.Count > 0)
            RegisterWithAddressables();
    }

    void Generate(Rule rule)
    {
        var sprites = CollectSprites(rule.SourceFolder, rule.NamePrefix);
        if (sprites.Length == 0)
        {
            Debug.LogWarning($"[atlas] no sprites under {rule.SourceFolder} — {rule.AtlasPath} not written");
            return;
        }

        SpriteAtlasAsset asset;
        if (File.Exists(rule.AtlasPath))
        {
            // Rebuild from scratch each time, or a renamed source file lingers in the atlas
            // forever. Packables come off the runtime atlas: GetPackables is an Editor extension
            // on SpriteAtlas (UnityEditor.U2D.SpriteAtlasExtensions), not a member of
            // SpriteAtlasAsset — which has no equivalent at all.
            asset = SpriteAtlasAsset.Load(rule.AtlasPath);
            var existing = AssetDatabase.LoadAssetAtPath<SpriteAtlas>(rule.AtlasPath);
            if (existing != null) asset.Remove(existing.GetPackables());
        }
        else
        {
            asset = new SpriteAtlasAsset();
            Directory.CreateDirectory(Path.GetDirectoryName(rule.AtlasPath));
        }

        asset.Add(sprites);
        SpriteAtlasAsset.Save(asset, rule.AtlasPath);
        AssetDatabase.ImportAsset(rule.AtlasPath);   // an importer exists only after this
        Configure(rule.AtlasPath, rule.IncludeInBuild);

        if (!rule.IncludeInBuild) _lateBound.Add(rule.AtlasPath);
        Log($"{rule.AtlasPath}: {sprites.Length} sprites, includeInBuild={rule.IncludeInBuild}");
    }

    static Object[] CollectSprites(string folder, string namePrefix)
    {
        // Two overloads of FindAssets exist and only one is scoped. Unscoped, this reaches into
        // every installed package; the sprites it finds there cannot be packed anyway.
        return AssetDatabase.FindAssets("t:Sprite", new[] { folder })
            .Select(AssetDatabase.GUIDToAssetPath)
            .Where(IsProjectAsset)
            .Select(AssetDatabase.LoadAssetAtPath<Sprite>)
            .Where(s => s != null && (string.IsNullOrEmpty(namePrefix) || s.name.StartsWith(namePrefix)))
            .Cast<Object>()
            .ToArray();
    }

    /// <summary>
    /// Keeps the array to the project's own assets. Package and Editor built-in assets are
    /// read-only imports, so anything downstream that wants to reimport them cannot.
    /// </summary>
    static bool IsProjectAsset(string path) => path.StartsWith("Assets/");

    static void Configure(string atlasPath, bool includeInBuild)
    {
        // GetAtPath takes the path alone — there is no overload that accepts a type.
        var importer = AssetImporter.GetAtPath(atlasPath) as SpriteAtlasImporter;
        if (importer == null)
            throw new BuildFailedException($"no SpriteAtlasImporter at {atlasPath} — the import did not take");

        // Both settings properties hand back a struct. Editing a member through the property
        // edits a temporary; the assign-back is what persists it.
        var texture = importer.textureSettings;
        texture.filterMode      = FilterMode.Bilinear;   // point filtering is a pixel-art choice, not a default
        texture.generateMipMaps = false;                 // UI atlases are drawn at 1:1
        texture.readable        = false;
        importer.textureSettings = texture;

        var packing = importer.packingSettings;
        packing.padding             = 4;
        packing.enableRotation      = false;             // rotation breaks tooling that assumes upright sprites
        packing.enableTightPacking  = false;
        packing.enableAlphaDilation = true;              // kills the halo at sprite edges
        importer.packingSettings = packing;

        SetPlatform(importer, "Android", TextureImporterFormat.ASTC_6x6);
        SetPlatform(importer, "iOS", TextureImporterFormat.ASTC_4x4);

        importer.includeInBuild = includeInBuild;
        importer.SaveAndReimport();                      // nothing above is on disk until this runs
    }

    static void SetPlatform(SpriteAtlasImporter importer, string platform, TextureImporterFormat format)
    {
        importer.SetPlatformSettings(new TextureImporterPlatformSettings
        {
            name           = platform,
            overridden     = true,        // without this the rest of the struct is ignored
            maxTextureSize = 2048,
            // format is a property typed TextureImporterFormat. A cast to int does not compile;
            // the fix is to remove the cast.
            format         = format,
        });
    }

    void RegisterWithAddressables()
    {
#if UNITY_ADDRESSABLES
        var settings = AddressableAssetSettingsDefaultObject.Settings;
        if (settings == null)
            throw new BuildFailedException(
                "Addressables is installed but not initialised — atlases excluded from the build would have no delivery path.");

        var group = settings.DefaultGroup;
        if (group == null)
            throw new BuildFailedException("Addressables has no default group to put the atlases in.");

        foreach (var atlasPath in _lateBound)
        {
            var guid = AssetDatabase.AssetPathToGUID(atlasPath);
            if (string.IsNullOrEmpty(guid))
                throw new BuildFailedException($"no GUID for {atlasPath} — it is not in the asset database");

            if (settings.FindAssetEntry(guid) != null)
            {
                Log($"{atlasPath} already addressable");
                continue;
            }

            var entry = settings.CreateOrMoveEntry(guid, group, readOnly: false, postEvent: false);
            // Address == file name, so the runtime supplier can use the requested tag directly
            // and no mapping asset has to be kept in sync.
            entry.address = Path.GetFileNameWithoutExtension(atlasPath);
            Log($"addressable: {entry.address} -> {atlasPath}");
        }

        settings.SetDirty(AddressableAssetSettings.ModificationEvent.EntryAdded, null, true);
#else
        throw new BuildFailedException(
            "Atlases are set to load through Addressables, but UNITY_ADDRESSABLES is not defined for this build.");
#endif
    }

    static void Log(string message) => Debug.Log($"[atlas] {message}");
}
#endif
