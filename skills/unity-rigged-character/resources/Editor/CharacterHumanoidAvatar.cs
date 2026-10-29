// CharacterHumanoidAvatar — builds a Humanoid Avatar from an explicit HumanDescription, so Chest,
// UpperChest, the toes and every finger are mapped instead of left to Unity's automatic mapping
// (which can leave an optional bone such as Chest out, and maps no finger on many rigs).
//
// Only for a character folder whose config says "rig": "Humanoid" — the contract skeleton plays
// Generic by default; Humanoid is built when the game needs IK or a body-part mask.
//
// Drop into an Editor folder with CharacterImportSettings.cs (it reads that file's config and
// naming contract). No package needed.
//
//   Tools/Unity Dev/Rigged Character/Build Humanoid Avatar    select the character folder first;
//                                                             logs "[RIGGED-CHAR] {json}"
//   CharacterHumanoidAvatar.Build("Assets/Models/Runner")      returns the same JSON, for an eval
//
// The map: humanName (a HumanTrait.BoneName string) -> bone name in the FBX.
//   no "humanMap" in the config     the humanoid contract's own names (Hips, UpperArm.L, Thumb1.L, …),
//                                   the skeleton reference/humanoid-contract.md defines
//   "humanMap": "<path>.json"       the file contract_map.py --unity-out writes for another
//                                   skeleton (Mixamo, Auto-Rig Pro, a clip pack), schema
//                                   unity-human-map/1: {"human":[{"humanName":"Hips","boneName":"pelvis"}, …]}
//
// The skeleton (the pose the Avatar is built on) is every transform of the imported body at its
// default pose. Unity's default pose is the clip's first frame when the body FBX carries an action,
// so export the body at its rest pose. An A-pose rest builds a valid Avatar; Configure may still
// report "Character not in T-Pose" — Enforce T-Pose there when IK reaches look wrong.
//
// A command, not part of the postprocessor: the skeleton is read from the imported model, which
// does not exist yet during its own preprocess. Re-run after every re-export and after Reimport
// Character Folder; it rebuilds the description from scratch each time.
//
// Gate (also used by CharacterAvatarLinker when the rig is Humanoid): the Avatar isValid and
// isHuman, Chest is mapped, and at least "minFingerBones" (default 10) finger bones are mapped.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;

[Serializable]
public class CharacterHumanMapEntry
{
    public string humanName;
    public string boneName;
}

[Serializable]
public class CharacterHumanMapFile
{
    public string schema;
    public string preset;
    public CharacterHumanMapEntry[] human;
}

public static class CharacterHumanoidAvatar
{
    const string MenuPath = "Tools/Unity Dev/Rigged Character/Build Humanoid Avatar";

    static readonly string[] Centre = { "Hips", "Spine", "Chest", "UpperChest", "Neck", "Head" };
    static readonly string[] Limbs = { "Shoulder", "UpperArm", "LowerArm", "Hand", "UpperLeg", "LowerLeg", "Foot", "Toes" };
    static readonly string[] Fingers = { "Thumb", "Index", "Middle", "Ring", "Little" };   // Unity says Little, not Pinky
    static readonly string[] Phalanges = { "Proximal", "Intermediate", "Distal" };

    [MenuItem(MenuPath)]
    static void Menu()
    {
        Debug.Log("[RIGGED-CHAR] " + Build(CharacterImportSettings.SelectedFolder()));
    }

    /// <summary>humanName -> contract bone name: "LeftUpperArm" -> "UpperArm.L", "Left Thumb Proximal" -> "Thumb1.L".</summary>
    public static Dictionary<string, string> ContractMap()
    {
        var map = new Dictionary<string, string>();
        foreach (string c in Centre) map[c] = c;
        foreach (string side in new[] { "L", "R" })
        {
            string word = side == "L" ? "Left" : "Right";
            foreach (string limb in Limbs) map[word + limb] = limb + "." + side;
            foreach (string finger in Fingers)
                for (int i = 0; i < Phalanges.Length; i++)
                    map[word + " " + finger + " " + Phalanges[i]] = finger + (i + 1) + "." + side;
        }
        return map;
    }

    /// <summary>The map in force for a config, or null with the reason in error.</summary>
    public static Dictionary<string, string> MapFor(CharacterPipelineConfig cfg, out string source, out string error)
    {
        error = null;
        if (string.IsNullOrEmpty(cfg.humanMap))
        {
            source = "humanoid-contract";
            return ContractMap();
        }
        source = cfg.humanMap;
        string path = cfg.humanMap;
        if (!File.Exists(path) && !string.IsNullOrEmpty(cfg.folder)) path = cfg.folder.TrimEnd('/') + "/" + cfg.humanMap;
        if (!File.Exists(path))
        {
            error = "humanMap " + cfg.humanMap + " not found (a project path, or a path inside the character folder)";
            return null;
        }
        CharacterHumanMapFile file;
        try
        {
            file = JsonUtility.FromJson<CharacterHumanMapFile>(File.ReadAllText(path));
        }
        catch (Exception e)
        {
            error = path + " does not parse: " + e.Message;
            return null;
        }
        if (file == null || file.human == null || file.human.Length == 0)
        {
            error = path + " has no \"human\" entries — write it with contract_map.py map … --unity-out";
            return null;
        }
        var map = new Dictionary<string, string>();
        foreach (CharacterHumanMapEntry e in file.human)
            if (e != null && !string.IsNullOrEmpty(e.humanName) && !string.IsNullOrEmpty(e.boneName))
                map[e.humanName] = e.boneName;
        return map;
    }

    public static string Build(string folder)
    {
        CharacterPipelineConfig cfg = CharacterImportSettings.ForFolder(folder);
        if (cfg == null) return CharacterImportSettings.NotACharacterFolder("humanoid", folder);
        folder = CharacterImportSettings.Norm(folder).TrimEnd('/');
        if (!cfg.Humanoid)
            return Fail(folder, "rig is " + cfg.rig + ": set \"rig\": \"Humanoid\" in " + cfg.source +
                                " only when the game needs IK or a body-part mask, then Reimport Character Folder");

        Dictionary<string, string> map = MapFor(cfg, out string mapSource, out string mapError);
        if (map == null) return Fail(folder, mapError);

        // Every name must be one Unity knows; a misspelt name ("Left Pinky Proximal") maps nothing silently.
        var known = new HashSet<string>(HumanTrait.BoneName);
        var unknown = new List<string>();
        foreach (string h in map.Keys) if (!known.Contains(h)) unknown.Add(h);
        if (unknown.Count > 0) return Fail(folder, "not HumanTrait.BoneName strings: " + string.Join(", ", unknown));

        var reports = new List<string>();
        bool allOk = true;
        int bodies = 0;
        foreach (string guid in AssetDatabase.FindAssets("t:Model", new[] { folder }))
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (!CharacterImportSettings.IsFbx(path) || CharacterImportSettings.ClipText(path) != null) continue;
            bodies++;
            string r = BuildOne(path, map, cfg, out bool ok);
            allOk &= ok;
            reports.Add(r);
        }

        var sb = new StringBuilder(512);
        sb.Append("{\"op\":\"humanoid\",\"ok\":").Append(allOk && bodies > 0 ? "true" : "false");
        sb.Append(",\"folder\":").Append(CharacterImportSettings.Q(folder));
        sb.Append(",\"map\":").Append(CharacterImportSettings.Q(mapSource));
        sb.Append(",\"bodies\":").Append(bodies);
        if (bodies == 0) sb.Append(",\"error\":").Append(CharacterImportSettings.Q("no body FBX (a name without '@') in the folder"));
        sb.Append(",\"results\":[").Append(string.Join(",", reports)).Append("]}");
        return sb.ToString();
    }

    static string BuildOne(string path, Dictionary<string, string> map, CharacterPipelineConfig cfg, out bool ok)
    {
        ok = false;
        var importer = AssetImporter.GetAtPath(path) as ModelImporter;
        var model = AssetDatabase.LoadAssetAtPath<GameObject>(path);
        if (importer == null || model == null) return Entry(path, false, "not an imported model", 0, 0, null);

        Transform[] all = model.GetComponentsInChildren<Transform>(true);
        var byName = new Dictionary<string, Transform>();
        foreach (Transform t in all)
        {
            if (!byName.ContainsKey(t.name)) byName[t.name] = t;
            int colon = t.name.LastIndexOf(':');                 // "mixamorig:Hips" also answers to "Hips"
            if (colon >= 0 && !byName.ContainsKey(t.name.Substring(colon + 1))) byName[t.name.Substring(colon + 1)] = t;
        }

        var human = new List<HumanBone>();
        var absent = new List<string>();
        foreach (string humanName in HumanTrait.BoneName)
        {
            if (!map.TryGetValue(humanName, out string bone)) continue;
            if (!byName.TryGetValue(bone, out Transform t))
            {
                absent.Add(humanName + "=" + bone);
                continue;
            }
            var hb = new HumanBone { humanName = humanName, boneName = t.name };
            hb.limit.useDefaultValues = true;
            human.Add(hb);
        }

        var missingRequired = new List<string>();
        for (int i = 0; i < HumanTrait.BoneCount; i++)
        {
            if (!HumanTrait.RequiredBone(i)) continue;
            string n = HumanTrait.BoneName[i];
            if (!human.Exists(h => h.humanName == n)) missingRequired.Add(n);
        }
        if (missingRequired.Count > 0)
            return Entry(path, false, "required bones not in the FBX: " + string.Join(", ", missingRequired), human.Count, 0, absent);

        var skeleton = new SkeletonBone[all.Length];
        for (int i = 0; i < all.Length; i++)
            skeleton[i] = new SkeletonBone
            {
                name = all[i].name, position = all[i].localPosition,
                rotation = all[i].localRotation, scale = all[i].localScale
            };

        HumanDescription desc = importer.humanDescription;      // a struct: edit a copy, assign it back
        desc.human = human.ToArray();
        desc.skeleton = skeleton;
        desc.upperArmTwist = 0.5f; desc.lowerArmTwist = 0.5f;
        desc.upperLegTwist = 0.5f; desc.lowerLegTwist = 0.5f;
        desc.armStretch = 0.05f; desc.legStretch = 0.05f;
        desc.feetSpacing = 0f;
        desc.hasTranslationDoF = false;

        importer.animationType = ModelImporterAnimationType.Human;
        importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
        importer.humanDescription = desc;
        importer.SaveAndReimport();

        Avatar avatar = FindAvatar(path);
        string reason = Gate(avatar, cfg, out int fingers);
        ok = reason == null;
        return Entry(path, ok, reason, human.Count, fingers, absent);
    }

    /// <summary>Null when the Avatar is a usable Humanoid; otherwise the reason.</summary>
    public static string Gate(Avatar avatar, CharacterPipelineConfig cfg, out int fingers)
    {
        fingers = 0;
        if (avatar == null) return "produced no Avatar — open its Rig tab and read the import message";
        bool chest = false;
        foreach (HumanBone hb in avatar.humanDescription.human)
        {
            if (hb.humanName == "Chest" && !string.IsNullOrEmpty(hb.boneName)) chest = true;
            foreach (string f in Fingers)
                if (hb.humanName.Contains(" " + f + " ") && !string.IsNullOrEmpty(hb.boneName)) { fingers++; break; }
        }
        if (!avatar.isValid || !avatar.isHuman)
            return "Avatar is not a valid Humanoid (isHuman=" + avatar.isHuman + ", isValid=" + avatar.isValid +
                   ") — run Build Humanoid Avatar, or Rig tab → Configure and find the unmapped bone";
        if (!chest) return "Chest is not mapped — the automatic mapping leaves it out; run Build Humanoid Avatar";
        if (fingers < cfg.minFingerBones)
            return fingers + " finger bones mapped, " + cfg.minFingerBones +
                   " required (minFingerBones; 0 for a rig with no finger bones) — run Build Humanoid Avatar";
        return null;
    }

    static string Entry(string path, bool ok, string reason, int mapped, int fingers, List<string> absent)
    {
        var sb = new StringBuilder(256);
        sb.Append("{\"body\":").Append(CharacterImportSettings.Q(path));
        sb.Append(",\"ok\":").Append(ok ? "true" : "false");
        sb.Append(",\"mapped\":").Append(mapped).Append(",\"fingers\":").Append(fingers);
        if (reason != null) sb.Append(",\"error\":").Append(CharacterImportSettings.Q(reason));
        sb.Append(",\"absent\":[");
        if (absent != null)
            for (int i = 0; i < absent.Count; i++) sb.Append(i > 0 ? "," : "").Append(CharacterImportSettings.Q(absent[i]));
        sb.Append("]}");
        return sb.ToString();
    }

    static string Fail(string folder, string error) =>
        "{\"op\":\"humanoid\",\"ok\":false,\"folder\":" + CharacterImportSettings.Q(folder) +
        ",\"error\":" + CharacterImportSettings.Q(error) + "}";

    /// <summary>The Avatar is a sub-asset of the imported body, not a file of its own.</summary>
    public static Avatar FindAvatar(string modelPath)
    {
        foreach (UnityEngine.Object asset in AssetDatabase.LoadAllAssetsAtPath(modelPath))
            if (asset is Avatar avatar) return avatar;
        return null;
    }
}
