// CharacterImportSettings — makes a rigged character's FBX files and texture maps game-ready on
// import, driven by one small JSON file instead of constants edited in the script.
//
// Drop into an Editor folder together with CharacterAvatarLinker.cs, CharacterAnimatorBuilder.cs,
// CharacterHumanoidAvatar.cs and MixamoTextures.cs (any FBX route; it needs URP). No package needed.
//
//   on import (AssetPostprocessor)        every .fbx and texture inside a character folder
//   Tools/Unity Dev/Rigged Character/Reimport Character Folder
//                                         select the folder first; re-applies after a config edit
//   CharacterImportSettings.Reimport("Assets/Models/Runner")    the same, for an eval
//   CharacterImportSettings.Describe("Assets/Models/Runner")    the config in force, as JSON
//
// A character folder is the nearest folder above a file that holds character-pipeline.json; else
// the "folder" named in Assets/Editor/character-pipeline.json; else, with neither file,
// Assets/Models/Character. Every field is optional:
//   rig             "Generic" (default) or "Humanoid" — Generic plays every clip on the skeleton it
//                   was baked on (the humanoid contract, a clip pack's own, Mixamo's); Humanoid only
//                   when the game needs IK or a body-part mask, and then the Avatar is built from an
//                   explicit map by CharacterHumanoidAvatar.cs (Build Humanoid Avatar)
//   humanMap        Humanoid only: the unity-human-map/1 file contract_map.py --unity-out wrote for a
//                   skeleton that is not the contract's; absent: the contract's own bone names
//   minFingerBones  Humanoid only: finger bones the Avatar gate requires (default 10; 0 for a rig
//                   with no finger bones)
//   clipRules       [{"keyword":"runfast","clip":"RunFast","loop":true}, ...] — replaces the
//                   built-in list; first match wins, so a specific keyword precedes a general one
//   maxTextureSize  Max Size for every texture in the folder; 0 or absent: the importer's own value
//                   (2048 on a fresh importer) is left alone — set 512 for a 512 cap
//   targetTexPx     target_tex_px of the character row of the 3D budgets table; used as Max Size
//                   when maxTextureSize is not set; 0 or absent: left alone
//   material        the URP Lit material MixamoTextures writes
//   animator        controller and mask paths, clip names, parameter names (CharacterAnimatorBuilder)
//
// File naming contract — the one thing to get right by hand:
//   <name>.fbx          the body: carries the mesh and creates the Avatar. No '@' in the name.
//                       Its clips keep the names the exporter gave them.
//   <name>@<Clip>.fbx   animation only: no materials; its Avatar is linked by CharacterAvatarLinker.
//                       The text after '@' is matched against clipRules (case-insensitive
//                       substring); with no match the clip is named that text and does not loop.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;

[Serializable]
public class CharacterClipRule
{
    public string keyword;
    public string clip;
    public bool loop;

    public CharacterClipRule() { }
    public CharacterClipRule(string keyword, string clip, bool loop)
    {
        this.keyword = keyword;
        this.clip = clip;
        this.loop = loop;
    }
}

[Serializable]
public class CharacterAnimatorConfig
{
    public string controller = "Assets/Animations/Character.controller";
    public string mask = "Assets/Animations/UpperBody.mask";
    public string slowClip = "RunSlow";
    public string fastClip = "RunFast";
    public string singleClip = "Run";
    public string jumpClip = "Jump";
    public string hurtClip = "Hurt";
    // The four names AnimatorBridge3D (skill unity-3d-controller) writes by default. Empty: the
    // parameter, and what hangs off it, is left out of the controller.
    public string grounded = "Grounded";
    public string moveBlend = "MoveBlend";
    public string moveSpeed = "MoveSpeed";
    public string hurt = "Hurt";
}

[Serializable]
public class CharacterPipelineConfig
{
    public string folder = CharacterImportSettings.DefaultFolder;
    public string rig = "Generic";
    public string humanMap = "";
    public int minFingerBones = 10;
    public CharacterClipRule[] clipRules;
    public int maxTextureSize;
    public int targetTexPx;
    public string material = "Assets/Materials/Character.mat";
    public CharacterAnimatorConfig animator = new CharacterAnimatorConfig();

    [NonSerialized] public string source = "built-in defaults";

    // Only the word Humanoid (any case) turns Humanoid on: a typo stays Generic rather than silently re-solving every pose.
    public bool Humanoid => string.Equals(rig, "Humanoid", StringComparison.OrdinalIgnoreCase);

    /// <summary>Max Size to write, or 0 to leave the importer's value alone.</summary>
    public int EffectiveMaxTextureSize
    {
        get
        {
            int px = maxTextureSize > 0 ? maxTextureSize : targetTexPx;
            if (px <= 0) return 0;
            int p = 32;                          // the importer takes powers of two, 32..16384
            while (p < px && p < 16384) p <<= 1;
            return p;
        }
    }

    /// <summary>The first rule whose keyword the clip text contains, or null.</summary>
    public CharacterClipRule Match(string clipText)
    {
        string lower = clipText.ToLowerInvariant();
        foreach (CharacterClipRule r in clipRules)
            if (r != null && !string.IsNullOrEmpty(r.keyword) && lower.Contains(r.keyword.ToLowerInvariant()))
                return r;
        return null;
    }
}

public class CharacterImportSettings : AssetPostprocessor
{
    public const string ConfigFile = "character-pipeline.json";
    public const string DefaultConfigPath = "Assets/Editor/" + ConfigFile;
    public const string DefaultFolder = "Assets/Models/Character";
    const string MenuPath = "Tools/Unity Dev/Rigged Character/Reimport Character Folder";

    /// <summary>
    /// File-name keyword → clip name + whether it loops. ORDER MATTERS — first match wins, so
    /// "runfast" precedes "run", or the fast and the slow run both end up named "Run".
    /// </summary>
    public static CharacterClipRule[] DefaultClipRules() => new[]
    {
        new CharacterClipRule("runfast", "RunFast", true),
        new CharacterClipRule("fastrun", "RunFast", true),
        new CharacterClipRule("runslow", "RunSlow", true),
        new CharacterClipRule("slowrun", "RunSlow", true),
        new CharacterClipRule("run",     "Run",     true),
        new CharacterClipRule("walk",    "Walk",    true),
        new CharacterClipRule("idle",    "Idle",    true),
        new CharacterClipRule("jump",    "Jump",    false),
        new CharacterClipRule("hurt",    "Hurt",    false),
        new CharacterClipRule("hit",     "Hurt",    false),   // Mixamo calls it "Hit Reaction"
        new CharacterClipRule("fall",    "Fall",    false),
    };

    // ---------------------------------------------------------------- config

    /// <summary>The config that applies to an asset, or null when it is not in a character folder.</summary>
    public static CharacterPipelineConfig For(string assetPath)
    {
        string path = Norm(assetPath);
        CharacterPipelineConfig near = Nearest(Norm(Path.GetDirectoryName(path)));
        if (near != null) return near;
        CharacterPipelineConfig d = LoadDefault();
        return Inside(path, d.folder) ? d : null;
    }

    /// <summary>The config for a folder the commands act on, or null when it is not a character folder.</summary>
    public static CharacterPipelineConfig ForFolder(string folder)
    {
        folder = Norm(folder).TrimEnd('/');
        CharacterPipelineConfig near = Nearest(folder);
        if (near != null) return near;
        CharacterPipelineConfig d = LoadDefault();
        string f = Norm(d.folder).TrimEnd('/');
        return folder == f || Inside(folder, f) ? d : null;
    }

    /// <summary>The selected Project-window folder, else the default config's folder.</summary>
    public static string SelectedFolder()
    {
        string p = Selection.activeObject != null ? AssetDatabase.GetAssetPath(Selection.activeObject) : null;
        if (!string.IsNullOrEmpty(p) && AssetDatabase.IsValidFolder(p)) return p;
        return Norm(LoadDefault().folder).TrimEnd('/');
    }

    public static CharacterPipelineConfig LoadDefault()
    {
        if (File.Exists(DefaultConfigPath)) return Read(DefaultConfigPath, null);
        var c = new CharacterPipelineConfig();
        c.clipRules = DefaultClipRules();
        return c;
    }

    // Walks up from a folder to Assets/; the first character-pipeline.json found makes its folder
    // the character folder. The default-path file is not a folder marker.
    static CharacterPipelineConfig Nearest(string dir)
    {
        while (!string.IsNullOrEmpty(dir) && (dir == "Assets" || dir.StartsWith("Assets/")))
        {
            string candidate = dir + "/" + ConfigFile;
            if (candidate != DefaultConfigPath && File.Exists(candidate)) return Read(candidate, dir);
            if (dir == "Assets") break;
            dir = Norm(Path.GetDirectoryName(dir));
        }
        return null;
    }

    // File.ReadAllText, not the AssetDatabase: on a fresh clone the JSON may not be imported yet.
    static CharacterPipelineConfig Read(string path, string folder)
    {
        var c = new CharacterPipelineConfig();
        try
        {
            JsonUtility.FromJsonOverwrite(File.ReadAllText(path), c);
        }
        catch (Exception e)
        {
            Debug.LogError("[RIGGED-CHAR] " + path + " does not parse (" + e.Message + ") — using the defaults");
            c = new CharacterPipelineConfig();
        }
        if (c.clipRules == null || c.clipRules.Length == 0) c.clipRules = DefaultClipRules();
        if (c.animator == null) c.animator = new CharacterAnimatorConfig();
        if (folder != null) c.folder = folder;
        if (string.IsNullOrEmpty(c.folder)) c.folder = DefaultFolder;
        c.source = path;
        return c;
    }

    // ---------------------------------------------------------------- naming contract

    public static bool IsFbx(string path) => path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase);

    /// <summary>The text after '@' in the file name, or null for the body.</summary>
    public static string ClipText(string path)
    {
        string file = Path.GetFileNameWithoutExtension(path);
        int at = file.LastIndexOf('@');
        return at < 0 ? null : file.Substring(at + 1);
    }

    /// <summary>The text before '@' — the body this file belongs to.</summary>
    public static string BodyName(string path)
    {
        string file = Path.GetFileNameWithoutExtension(path);
        int at = file.IndexOf('@');
        return at < 0 ? file : file.Substring(0, at);
    }

    // ---------------------------------------------------------------- import

    void OnPreprocessModel()
    {
        if (!IsFbx(assetPath)) return;
        CharacterPipelineConfig cfg = For(assetPath);
        if (cfg == null) return;
        var importer = (ModelImporter)assetImporter;

        // Generic (the default) plays the clip on the bones it was keyed on, extra bones included.
        // Humanoid buys the body-part AvatarMask and IK; its explicit map is written afterwards by
        // CharacterHumanoidAvatar.Build, because the skeleton is only readable once imported.
        importer.animationType = cfg.Humanoid ? ModelImporterAnimationType.Human
                                              : ModelImporterAnimationType.Generic;

        if (ClipText(assetPath) == null)
            importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
        else
            // Animation only: no materials. Its Avatar is linked by CharacterAvatarLinker — import
            // order is not guaranteed, so linking here could run before the body's Avatar exists.
            importer.materialImportMode = ModelImporterMaterialImportMode.None;
    }

    void OnPreprocessAnimation()
    {
        if (!IsFbx(assetPath)) return;
        string clipText = ClipText(assetPath);
        if (clipText == null) return;
        CharacterPipelineConfig cfg = For(assetPath);
        if (cfg == null) return;

        var importer = (ModelImporter)assetImporter;
        ModelImporterClipAnimation[] clips = importer.defaultClipAnimations;
        if (clips == null || clips.Length == 0) return;

        CharacterClipRule rule = cfg.Match(clipText);
        string name = rule != null ? rule.clip : clipText;
        bool loop = rule != null && rule.loop;
        for (int i = 0; i < clips.Length; i++)
        {
            // Off the exporter's default ("mixamo.com", "Take 001") so the Animator can find it.
            clips[i].name = clips.Length == 1 ? name : name + "_" + i;
            clips[i].loopTime = loop;
            // loopPose matches the first and last frames; a one-frame mismatch in a short run
            // cycle reads as a hitch twice a second.
            clips[i].loopPose = loop;
        }
        importer.clipAnimations = clips;
    }

    void OnPreprocessTexture()
    {
        CharacterPipelineConfig cfg = For(assetPath);
        if (cfg == null) return;
        var importer = (TextureImporter)assetImporter;

        int max = cfg.EffectiveMaxTextureSize;
        if (max > 0) importer.maxTextureSize = max;
        importer.textureCompression = TextureImporterCompression.Compressed;

        // Only the colour map is colour. The others carry data, and imported as sRGB every value
        // is gamma-warped. Matched on the file name, so any character's maps work the same.
        string file = Path.GetFileNameWithoutExtension(assetPath).ToLowerInvariant();
        if (file.Contains("normal"))
        {
            importer.textureType = TextureImporterType.NormalMap;
        }
        else if (file.Contains("metallic") || file.Contains("smoothness") || file.Contains("roughness"))
        {
            importer.textureType = TextureImporterType.Default;
            importer.sRGBTexture = false;                                 // linear: raw values
            importer.alphaSource = TextureImporterAlphaSource.FromInput;  // smoothness lives in A
            importer.alphaIsTransparency = false;                         // a material value, not opacity
        }
    }

    // ---------------------------------------------------------------- commands

    [MenuItem(MenuPath)]
    static void Menu()
    {
        Debug.Log("[RIGGED-CHAR] " + Reimport(SelectedFolder()));
    }

    /// <summary>Re-imports every FBX and texture in a character folder; returns a JSON report.</summary>
    public static string Reimport(string folder)
    {
        CharacterPipelineConfig cfg = ForFolder(folder);
        if (cfg == null) return NotACharacterFolder("reimport", folder);

        var paths = new List<string>();
        foreach (string guid in AssetDatabase.FindAssets("t:Model t:Texture2D", new[] { Norm(folder).TrimEnd('/') }))
        {
            string p = AssetDatabase.GUIDToAssetPath(guid);
            if (!paths.Contains(p)) paths.Add(p);
        }
        AssetDatabase.StartAssetEditing();
        try
        {
            foreach (string p in paths) AssetDatabase.ImportAsset(p, ImportAssetOptions.ForceUpdate);
        }
        finally
        {
            AssetDatabase.StopAssetEditing();
        }
        return "{\"op\":\"reimport\",\"ok\":true,\"folder\":" + Q(folder) + ",\"config\":" + Q(cfg.source) +
               ",\"assets\":" + paths.Count + "}";
    }

    /// <summary>The config in force for a folder, as JSON — what the importer will do there.</summary>
    public static string Describe(string folder)
    {
        CharacterPipelineConfig cfg = ForFolder(folder);
        if (cfg == null) return NotACharacterFolder("describe", folder);
        return "{\"op\":\"describe\",\"ok\":true,\"config\":" + Q(cfg.source) + ",\"effectiveMaxTextureSize\":" +
               cfg.EffectiveMaxTextureSize + ",\"settings\":" + JsonUtility.ToJson(cfg) + "}";
    }

    // ---------------------------------------------------------------- helpers

    public static string NotACharacterFolder(string op, string folder) =>
        "{\"op\":" + Q(op) + ",\"ok\":false,\"folder\":" + Q(folder) + ",\"error\":" +
        Q("not a character folder: put " + ConfigFile + " in it, or name it as \"folder\" in " + DefaultConfigPath) + "}";

    public static string Norm(string p) => string.IsNullOrEmpty(p) ? "" : p.Replace('\\', '/');

    static bool Inside(string path, string folder)
    {
        string f = Norm(folder).TrimEnd('/');
        return f.Length > 0 && Norm(path).StartsWith(f + "/");
    }

    /// <summary>A JSON string literal.</summary>
    public static string Q(string s)
    {
        if (s == null) return "null";
        var sb = new StringBuilder(s.Length + 2);
        sb.Append('"');
        foreach (char ch in s)
        {
            if (ch == '"' || ch == '\\') sb.Append('\\').Append(ch);
            else if (ch < 0x20) sb.Append("\\u").Append(((int)ch).ToString("x4"));
            else sb.Append(ch);
        }
        return sb.Append('"').ToString();
    }
}
