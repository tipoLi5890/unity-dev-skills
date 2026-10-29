// CharacterAvatarLinker — the Copy From Other Avatar step as a re-runnable command: every
// <name>@<Clip>.fbx in a character folder gets the Avatar of <name>.fbx in the same folder.
// Skip it and each animation file builds an Avatar of its own; the character then T-poses in place
// while the Animator reports nothing wrong.
//
// Drop into an Editor folder with CharacterImportSettings.cs (it reads that file's config and
// naming contract) and CharacterHumanoidAvatar.cs (its Humanoid gate). No package needed.
// On a Humanoid folder run Build Humanoid Avatar first: the link refuses a body whose Avatar is
// not human, has no Chest, or maps fewer finger bones than minFingerBones.
//
//   Tools/Unity Dev/Rigged Character/Link Animation Avatars    select the character folder first;
//                                                               logs "[RIGGED-CHAR] {json}"
//   CharacterAvatarLinker.Link("Assets/Models/Runner")          returns the same JSON, for an eval
//
// A command and not part of the import postprocessor because import order is not guaranteed: an
// animation file can import before its body, when the Avatar does not exist yet, and a link
// attempted then fails silently. Re-run after every re-export; it rewrites every link it finds.
using System.Collections.Generic;
using System.Text;
using UnityEditor;
using UnityEngine;

public static class CharacterAvatarLinker
{
    const string MenuPath = "Tools/Unity Dev/Rigged Character/Link Animation Avatars";

    [MenuItem(MenuPath)]
    static void Menu()
    {
        Debug.Log("[RIGGED-CHAR] " + Link(CharacterImportSettings.SelectedFolder()));
    }

    public static string Link(string folder)
    {
        CharacterPipelineConfig cfg = CharacterImportSettings.ForFolder(folder);
        if (cfg == null) return CharacterImportSettings.NotACharacterFolder("link", folder);
        folder = CharacterImportSettings.Norm(folder).TrimEnd('/');

        // Bodies keyed by "<dir>/<name>" in lower case; the files that need one listed separately.
        var bodies = new Dictionary<string, string>();
        var animations = new List<string>();
        foreach (string guid in AssetDatabase.FindAssets("t:Model", new[] { folder }))
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (!CharacterImportSettings.IsFbx(path)) continue;
            if (CharacterImportSettings.ClipText(path) == null) bodies[Key(path)] = path;
            else animations.Add(path);
        }

        var errors = new List<string>();
        var linked = new List<string>();
        var avatars = new Dictionary<string, Avatar>();
        foreach (string path in animations)
        {
            if (!bodies.TryGetValue(Key(path), out string body))
            {
                errors.Add(path + ": no " + CharacterImportSettings.BodyName(path) +
                           ".fbx beside it — the body carries the mesh and owns the Avatar");
                continue;
            }
            if (!avatars.TryGetValue(body, out Avatar avatar))
            {
                avatar = FindAvatar(body);
                avatars[body] = avatar;
            }
            if (avatar == null)
            {
                errors.Add(body + ": produced no Avatar — open its Rig tab and read the import message");
                continue;
            }
            if (cfg.Humanoid)
            {
                // isValid, isHuman, Chest mapped, minFingerBones fingers mapped
                string reason = CharacterHumanoidAvatar.Gate(avatar, cfg, out int fingerCount);
                if (reason != null)
                {
                    errors.Add(body + ": " + reason);
                    continue;
                }
            }
            else if (!avatar.isValid)
            {
                errors.Add(body + ": Avatar is not a valid Generic (isValid=false) — open its Rig tab and read the import message");
                continue;
            }
            if (!(AssetImporter.GetAtPath(path) is ModelImporter importer)) continue;

            importer.animationType = cfg.Humanoid ? ModelImporterAnimationType.Human
                                                  : ModelImporterAnimationType.Generic;
            importer.avatarSetup = ModelImporterAvatarSetup.CopyFromOther;
            importer.sourceAvatar = avatar;
            importer.SaveAndReimport();
            linked.Add(path);
        }

        var sb = new StringBuilder(256);
        sb.Append("{\"op\":\"link\",\"ok\":").Append(errors.Count == 0 && (linked.Count > 0 || animations.Count == 0) ? "true" : "false");
        sb.Append(",\"folder\":").Append(CharacterImportSettings.Q(folder));
        sb.Append(",\"bodies\":").Append(bodies.Count);
        sb.Append(",\"animations\":").Append(animations.Count);
        sb.Append(",\"linked\":").Append(linked.Count);
        sb.Append(",\"errors\":[");
        for (int i = 0; i < errors.Count; i++) sb.Append(i > 0 ? "," : "").Append(CharacterImportSettings.Q(errors[i]));
        sb.Append("]}");
        return sb.ToString();
    }

    static string Key(string path)
    {
        string dir = CharacterImportSettings.Norm(System.IO.Path.GetDirectoryName(path));
        return (dir + "/" + CharacterImportSettings.BodyName(path)).ToLowerInvariant();
    }

    /// <summary>The Avatar is a sub-asset of the imported body, not a file of its own.</summary>
    static Avatar FindAvatar(string modelPath)
    {
        foreach (Object asset in AssetDatabase.LoadAllAssetsAtPath(modelPath))
            if (asset is Avatar avatar) return avatar;
        return null;
    }
}
