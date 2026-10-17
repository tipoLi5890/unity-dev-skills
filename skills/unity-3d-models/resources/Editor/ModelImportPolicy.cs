// ModelImportPolicy.cs — import settings for a model's FIRST import, from a policy file in its
// folder. First import only, opt-in per folder, and the policy file is the only input.
//
// Drop into an Editor folder. No package needed. Then, per folder that wants it:
//
//   Assets/Models/Pickup/ParcelToken/.modelpolicy.json   applies to models imported into that folder
//                                               (not its subfolders: each folder opts in)
//
//   {"meshCompression":"medium","readWriteEnabled":false,"importBlendShapes":false}
//
// It acts only when the model has no import settings yet (AssetImporter.importSettingsMissing:
// a new file arriving without its .meta). A model that already has them, whether reimported,
// edited by hand, or copied in with its .meta, is never touched, and nothing here forces a
// reimport. No policy file, no change. Unity skips files whose name starts with a dot, so the
// policy file is not an asset and gets no .meta of its own.
//
// Commit every model's .meta. A model whose .meta is missing — deleted, not committed, or a clone
// without it — is a first import again: the policy re-applies, hand edits made since are lost,
// and the model gets a new GUID, which breaks every reference to the old one.
//
// Keys, all optional. An unknown key is ignored; an invalid value is logged and skipped; a file
// JsonUtility cannot read is skipped whole.
//
//   importBlendShapes    true | false
//   globalScale          a number > 0
//   animationType        none | generic | humanoid
//   materialImportMode   none | importStandard
//   meshCompression      off | low | medium | high
//   readWriteEnabled     true | false
//
// Logs "[MODEL-POLICY] <asset> applied key=value ..." or "[MODEL-POLICY] WARN ...". Only assets
// a ModelImporter imports reach OnPreprocessModel (.fbx .obj .dae .blend ...); a .glb or .gltf
// imported by glTFast does not, and gets nothing from this file.
using System;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

public class ModelImportPolicy : AssetPostprocessor
{
    public const string FileName = ".modelpolicy.json";
    const string Tag = "[MODEL-POLICY] ";

    // JsonUtility fills what is present; the defaults mean "not set". A bool cannot say "not
    // set", so for the two bools the raw text decides whether the key is there at all.
    [Serializable]
    class ModelPolicy
    {
        public bool importBlendShapes;
        public float globalScale = -1f;
        public string animationType = "";
        public string materialImportMode = "";
        public string meshCompression = "";
        public bool readWriteEnabled;
    }

    void OnPreprocessModel()
    {
        if (!assetImporter.importSettingsMissing) return;
        var importer = assetImporter as ModelImporter;
        if (importer == null) return;

        string folder = (Path.GetDirectoryName(assetPath) ?? "").Replace('\\', '/');
        string policyPath = folder + "/" + FileName;
        string file = Path.Combine(Path.GetDirectoryName(Application.dataPath) ?? "", policyPath);
        if (!File.Exists(file)) return;

        string text;
        ModelPolicy policy;
        try
        {
            text = File.ReadAllText(file);
            policy = JsonUtility.FromJson<ModelPolicy>(text);
        }
        catch (Exception e)
        {
            Warn(policyPath + " could not be read (" + e.Message + "): nothing applied to " + assetPath);
            return;
        }
        if (policy == null)
        {
            Warn(policyPath + " is empty: nothing applied to " + assetPath);
            return;
        }

        var applied = new StringBuilder();

        if (ReadBool(text, "importBlendShapes", policyPath, out bool blendShapes))
        {
            importer.importBlendShapes = blendShapes;
            Note(applied, "importBlendShapes", blendShapes ? "true" : "false");
        }

        if (Present(text, "globalScale"))
        {
            float s = policy.globalScale;
            if (s > 0f && !float.IsInfinity(s))
            {
                importer.globalScale = s;
                Note(applied, "globalScale", s.ToString("0.#####", CultureInfo.InvariantCulture));
            }
            else Invalid(policyPath, "globalScale", "a number > 0");
        }

        if (policy.animationType.Length > 0)
            Choose(applied, policyPath, "animationType", policy.animationType, v => importer.animationType = v,
                   ("none", ModelImporterAnimationType.None), ("generic", ModelImporterAnimationType.Generic),
                   ("humanoid", ModelImporterAnimationType.Human));

        if (policy.materialImportMode.Length > 0)
            Choose(applied, policyPath, "materialImportMode", policy.materialImportMode, v => importer.materialImportMode = v,
                   ("none", ModelImporterMaterialImportMode.None),
                   ("importStandard", ModelImporterMaterialImportMode.ImportStandard));

        if (policy.meshCompression.Length > 0)
            Choose(applied, policyPath, "meshCompression", policy.meshCompression, v => importer.meshCompression = v,
                   ("off", ModelImporterMeshCompression.Off), ("low", ModelImporterMeshCompression.Low),
                   ("medium", ModelImporterMeshCompression.Medium), ("high", ModelImporterMeshCompression.High));

        if (ReadBool(text, "readWriteEnabled", policyPath, out bool readWrite))
        {
            importer.isReadable = readWrite;
            Note(applied, "readWriteEnabled", readWrite ? "true" : "false");
        }

        if (applied.Length > 0) Log(Tag + assetPath + " applied" + applied + " (" + policyPath + ")");
    }

    // ------------------------------------------------------------------ parts

    static bool Present(string json, string key) =>
        Regex.IsMatch(json, "\"" + key + "\"\\s*:");

    // True with the value when the key holds a JSON true or false; logs a warning when the key
    // holds anything else; false when the key is absent.
    static bool ReadBool(string json, string key, string policyPath, out bool value)
    {
        value = false;
        if (!Present(json, key)) return false;
        Match m = Regex.Match(json, "\"" + key + "\"\\s*:\\s*(true|false)\\b");
        if (!m.Success)
        {
            Invalid(policyPath, key, "true | false");
            return false;
        }
        value = m.Groups[1].Value == "true";
        return true;
    }

    // Set the option whose name matches the value, ignoring case; otherwise warn and skip.
    static void Choose<T>(StringBuilder applied, string policyPath, string key, string value, Action<T> set,
                          params (string name, T option)[] options)
    {
        foreach ((string name, T option) in options)
        {
            if (!string.Equals(name, value, StringComparison.OrdinalIgnoreCase)) continue;
            set(option);
            Note(applied, key, name);
            return;
        }
        var names = new string[options.Length];
        for (int i = 0; i < options.Length; i++) names[i] = options[i].name;
        Invalid(policyPath, key, string.Join(" | ", names));
    }

    static void Note(StringBuilder applied, string key, string value) =>
        applied.Append(' ').Append(key).Append('=').Append(value);

    static void Invalid(string policyPath, string key, string expected) =>
        Warn(policyPath + ": " + key + " is not " + expected + "; skipped");

    static void Warn(string message) =>
        Debug.LogFormat(LogType.Warning, LogOption.NoStacktrace, null, "{0}", Tag + "WARN " + message);

    static void Log(string line) =>
        Debug.LogFormat(LogType.Log, LogOption.NoStacktrace, null, "{0}", line);
}
