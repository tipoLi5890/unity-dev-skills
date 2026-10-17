// MixamoTextures — the URP Lit material for a character that came in as FBX. Mixamo returns no
// materials; an FBX from Blender arrives with base colour and normal bound but the metallic and
// roughness maps dropped. Either way the material is rebuilt from the source maps (the .blend's
// images, or scripts/fbx_textures.py / glb2mixamo.py --textures on the ORIGINAL pre-upload export)
// dropped into the character folder. Maps are found by file-name keyword:
//   base colour   color, basecolor, albedo, diffuse
//   normal        normal
//   mask          metallicsmoothness only — RGB metallic, A smoothness (reference/textures.md). A raw
//                 *_Metallic image is never bound: without the composite the material gets no mask
//                 and the JSON carries a "note" naming the raw map it skipped
//
// Drop into an Editor folder with CharacterImportSettings.cs (config). Needs URP for the shader.
//
//   Tools/Unity Dev/Rigged Character/Apply Mixamo Textures    select the character folder first;
//                                                              logs "[RIGGED-CHAR] {json}"
//   MixamoTextures.Apply("Assets/Models/Runner")               returns the same JSON, for an eval
//
// WRITES the material at the config's "material" path (created when missing, every slot it sets
// overwritten when present). It does not assign the material to a renderer: the prefab step does
// that on every run, or the character reverts to the white default (reference/editor-scripts.md).
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

public static class MixamoTextures
{
    const string MenuPath = "Tools/Unity Dev/Rigged Character/Apply Mixamo Textures";

    [MenuItem(MenuPath)]
    static void Menu()
    {
        Debug.Log("[RIGGED-CHAR] " + Apply(CharacterImportSettings.SelectedFolder()));
    }

    public static string Apply(string folder)
    {
        CharacterPipelineConfig cfg = CharacterImportSettings.ForFolder(folder);
        if (cfg == null) return CharacterImportSettings.NotACharacterFolder("textures", folder);

        Texture2D baseMap = FindMap(cfg.folder, "color", "basecolor", "albedo", "diffuse");
        Texture2D normal = FindMap(cfg.folder, "normal");
        Texture2D mask = FindMap(cfg.folder, "metallicsmoothness");
        // A raw metallic map has no smoothness alpha; bound as the mask it reads as a mirror.
        Texture2D rawMetallic = mask == null ? FindMap(cfg.folder, "metallic") : null;
        if (baseMap == null)
            return Fail(cfg, "no colour map under " + cfg.folder + " — a file whose name contains color, basecolor, " +
                        "albedo or diffuse, extracted from the original pre-upload export");

        Shader shader = Shader.Find("Universal Render Pipeline/Lit");
        if (shader == null) return Fail(cfg, "URP Lit shader not found — this step needs URP");

        var material = AssetDatabase.LoadAssetAtPath<Material>(cfg.material);
        if (material == null)
        {
            EnsureFolder(Path.GetDirectoryName(cfg.material));
            material = new Material(shader);
            AssetDatabase.CreateAsset(material, cfg.material);
        }
        material.shader = shader;

        material.SetTexture("_BaseMap", baseMap);
        material.SetColor("_BaseColor", Color.white);      // the tint multiplies the map

        // Assigning a map is not enough: URP compiles the normal and metallic paths behind these
        // keywords, and without them the map loads, costs memory and is ignored.
        if (normal != null)
        {
            material.SetTexture("_BumpMap", normal);
            material.EnableKeyword("_NORMALMAP");
        }
        else material.DisableKeyword("_NORMALMAP");

        if (mask != null)
        {
            material.SetTexture("_MetallicGlossMap", mask);
            material.EnableKeyword("_METALLICSPECGLOSSMAP");
            // With a map bound, metallic comes from RGB and _Smoothness MULTIPLIES the alpha:
            // 1 means "the map as authored".
            material.SetFloat("_Metallic", 1f);
            material.SetFloat("_Smoothness", 1f);
        }
        else
        {
            material.DisableKeyword("_METALLICSPECGLOSSMAP");
            // Cloth and skin: no metal, low gloss; higher reads as wet vinyl.
            material.SetFloat("_Metallic", 0f);
            material.SetFloat("_Smoothness", 0.25f);
        }

        EditorUtility.SetDirty(material);
        AssetDatabase.SaveAssets();
        return "{\"op\":\"textures\",\"ok\":true,\"material\":" + CharacterImportSettings.Q(cfg.material) +
               ",\"base\":" + CharacterImportSettings.Q(AssetPathOf(baseMap)) +
               ",\"normal\":" + CharacterImportSettings.Q(AssetPathOf(normal)) +
               ",\"mask\":" + CharacterImportSettings.Q(AssetPathOf(mask)) +
               (rawMetallic == null ? "" : ",\"note\":" + CharacterImportSettings.Q(
                   "no <Name>_MetallicSmoothness map; raw " + AssetPathOf(rawMetallic) +
                   " not bound — composite it (reference/textures.md)")) + "}";
    }

    /// <summary>
    /// The first texture under the folder whose name contains a keyword. Keywords are tried in
    /// order, so the most specific comes first.
    /// </summary>
    static Texture2D FindMap(string folder, params string[] keywords)
    {
        var paths = new List<string>();
        foreach (string guid in AssetDatabase.FindAssets("t:Texture2D", new[] { folder.TrimEnd('/') }))
            paths.Add(AssetDatabase.GUIDToAssetPath(guid));
        foreach (string keyword in keywords)
            foreach (string p in paths)
                if (Path.GetFileNameWithoutExtension(p).ToLowerInvariant().Contains(keyword))
                    return AssetDatabase.LoadAssetAtPath<Texture2D>(p);
        return null;
    }

    static string AssetPathOf(Object o) => o == null ? null : AssetDatabase.GetAssetPath(o);

    static string Fail(CharacterPipelineConfig cfg, string error) =>
        "{\"op\":\"textures\",\"ok\":false,\"folder\":" + CharacterImportSettings.Q(cfg.folder) +
        ",\"error\":" + CharacterImportSettings.Q(error) + "}";

    static void EnsureFolder(string folder)
    {
        folder = CharacterImportSettings.Norm(folder).TrimEnd('/');
        if (string.IsNullOrEmpty(folder) || AssetDatabase.IsValidFolder(folder)) return;
        string parent = CharacterImportSettings.Norm(Path.GetDirectoryName(folder));
        EnsureFolder(parent);
        AssetDatabase.CreateFolder(parent, Path.GetFileName(folder));
    }
}
