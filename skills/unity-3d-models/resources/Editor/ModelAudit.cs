// ModelAudit.cs — a read-only audit of the 3D models in one folder against a class budget,
// printed as one JSON object. It changes nothing: no import setting, no asset, no scene.
//
// Drop into an Editor folder. No package needed (a .glb/.gltf row needs glTFast to load).
//
//   Tools/Unity Dev/3D Models/Audit Folder      the selected folder, or one picked in a dialog;
//                                               report only; logs "[MODEL-AUDIT] {json}"
//   ModelAudit.Audit("Assets/Models/Pickup")    the same JSON returned, for an eval or a test
//   ModelAudit.Audit("Assets/Models/Pickup", 7900, 12000, 1024, 2048, 2, 0, 3f)
//       target tris, ceiling tris, target texture px, ceiling texture px, max materials,
//       max bones, max MB — the columns of one row of the "3D budgets" table
//   -executeMethod ModelAudit.AuditBatch        the same from the command line, numbers from
//                                               MODEL_AUDIT_* environment variables; exits
//                                               0 green, 2 a gate failed, 3 harness error
//
// Any number <= 0 is not checked. A ceiling or a max is a gate: over it, the model fails. A
// target is never a gate: past target x 1.25 the model gets a warning. With no number at all
// the audit only reports; the numbers are the class's row, picked from the generation preset
// ladder (reference/budgets.md).
//
// Every .fbx .glb .gltf .prefab under the folder, recursively, is one row:
//
//   tris        LOD0 triangles over the MeshFilter and SkinnedMeshRenderer meshes, from the
//               index count (= Mesh.triangles.Length / 3 without allocating it, and readable
//               with Read/Write off); lower LOD levels are not added
//   materials   distinct materials on the model's renderers; slots = LOD0 material slots
//   texPx       longest side of the largest Texture2D the model uses, as imported: after Max
//               Size, on the active build target; not the source file's size
//   bones       the most bones one skinned mesh is bound to; its bind poses when Optimize Game
//               Objects has stripped the bone transforms
//   mb          the asset file on disk, in MB of 2^20 bytes
//   animationType, humanBones, clips, import    read from the ModelImporter; empty for a
//               prefab or a glTF, which have none
//   record      the row as a partial ledger record for art-asset-registry: the file, its
//               gates, warnings and verdict; the class and source are the caller's to add
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

public static class ModelAudit
{
    const string MenuPath = "Tools/Unity Dev/3D Models/Audit Folder";
    const string Tag = "[MODEL-AUDIT] ";

    /// <summary>A target is exceeded past target x this. Over it is a warning, never a failure.</summary>
    public const float TargetSlack = 1.25f;

    static readonly string[] Extensions = { ".fbx", ".glb", ".gltf", ".prefab" };

    [MenuItem(MenuPath)]
    static void Menu()
    {
        string folder = AssetDatabase.GetAssetPath(Selection.activeObject);
        if (string.IsNullOrEmpty(folder) || !AssetDatabase.IsValidFolder(folder))
        {
            string picked = EditorUtility.OpenFolderPanel("Audit the models under", Application.dataPath, "");
            if (string.IsNullOrEmpty(picked)) return;
            folder = ToAssetPath(picked);
            if (folder == null)
            {
                Debug.LogWarning(Tag + "pick a folder inside this project's Assets");
                return;
            }
        }
        Audit(folder);
    }

    /// <summary>Audit every model under <paramref name="folder"/>, log the JSON, write it to
    /// <paramref name="outPath"/> when given, and return it. Any number &lt;= 0 is not checked.</summary>
    public static string Audit(string folder, int targetTris = 0, int ceilingTris = 0, int targetTexPx = 0,
                               int ceilingTexPx = 0, int maxMaterials = 0, int maxBones = 0, float maxMb = 0f,
                               string outPath = null)
    {
        var budget = new Budget
        {
            TargetTris = targetTris, CeilingTris = ceilingTris, TargetTexPx = targetTexPx,
            CeilingTexPx = ceilingTexPx, MaxMaterials = maxMaterials, MaxBones = maxBones, MaxMb = maxMb
        };
        return Run(folder, budget, outPath, out _, out _);
    }

    /// <summary>Batch entry point. Reads MODEL_AUDIT_FOLDER (default Assets), MODEL_AUDIT_OUT and
    /// MODEL_AUDIT_TARGET_TRIS, _CEILING_TRIS, _TARGET_TEX_PX, _CEILING_TEX_PX, _MAX_MATERIALS,
    /// _MAX_BONES, _MAX_MB (default 0, not checked). Exits 0 green, 2 failed, 3 harness.</summary>
    public static void AuditBatch()
    {
        int code = 3;
        try
        {
            var budget = new Budget
            {
                TargetTris = EnvInt("MODEL_AUDIT_TARGET_TRIS"),
                CeilingTris = EnvInt("MODEL_AUDIT_CEILING_TRIS"),
                TargetTexPx = EnvInt("MODEL_AUDIT_TARGET_TEX_PX"),
                CeilingTexPx = EnvInt("MODEL_AUDIT_CEILING_TEX_PX"),
                MaxMaterials = EnvInt("MODEL_AUDIT_MAX_MATERIALS"),
                MaxBones = EnvInt("MODEL_AUDIT_MAX_BONES"),
                MaxMb = EnvFloat("MODEL_AUDIT_MAX_MB")
            };
            string folder = Env("MODEL_AUDIT_FOLDER") ?? "Assets";
            Run(folder, budget, Env("MODEL_AUDIT_OUT"), out string verdict, out bool wrote);
            code = !wrote ? 3 : verdict == "green" ? 0 : verdict == "failed" ? 2 : 3;
        }
        catch (Exception e)
        {
            Log(Tag + "ERROR " + e.Message);
            code = 3;
        }
        EditorApplication.Exit(code);
    }

    // ------------------------------------------------------------------ the run

    struct Budget
    {
        public int TargetTris, CeilingTris, TargetTexPx, CeilingTexPx, MaxMaterials, MaxBones;
        public float MaxMb;
        public bool Any => TargetTris > 0 || CeilingTris > 0 || TargetTexPx > 0 || CeilingTexPx > 0 ||
                           MaxMaterials > 0 || MaxBones > 0 || MaxMb > 0f;
    }

    static string Run(string folder, Budget budget, string outPath, out string verdict, out bool wrote)
    {
        folder = (folder ?? "").Replace('\\', '/').TrimEnd('/');
        var sb = new StringBuilder(4096);
        sb.Append("{\"schema\":1,\"tool\":\"ModelAudit\"");
        sb.Append(",\"unity\":").Append(Quote(Application.unityVersion));
        sb.Append(",\"folder\":").Append(Quote(folder));
        sb.Append(",\"budget\":{\"target_tris\":").Append(budget.TargetTris);
        sb.Append(",\"ceiling_tris\":").Append(budget.CeilingTris);
        sb.Append(",\"target_tex_px\":").Append(budget.TargetTexPx);
        sb.Append(",\"ceiling_tex_px\":").Append(budget.CeilingTexPx);
        sb.Append(",\"max_materials\":").Append(budget.MaxMaterials);
        sb.Append(",\"max_bones\":").Append(budget.MaxBones);
        sb.Append(",\"max_mb\":").Append(F(budget.MaxMb)).Append('}');

        var topWarnings = new List<string>();
        if (!AssetDatabase.IsValidFolder(folder))
        {
            verdict = "harness";
            sb.Append(",\"error\":").Append(Quote("not a folder in this project: '" + folder + "'"));
            sb.Append(",\"models\":[],\"warnings\":[],\"verdict\":\"harness\"}");
            return Finish(sb.ToString(), outPath, out wrote);
        }
        if (!budget.Any)
            topWarnings.Add("no budget given: report only. Pick the class's row first (unity-3d-models reference/budgets.md)");

        var seen = new HashSet<string>();
        var paths = new List<string>();
        foreach (string guid in AssetDatabase.FindAssets("", new[] { folder }))
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            string ext = Path.GetExtension(path).ToLowerInvariant();
            if (Array.IndexOf(Extensions, ext) >= 0 && seen.Add(path)) paths.Add(path);
        }
        paths.Sort(StringComparer.Ordinal);
        if (paths.Count == 0) topWarnings.Add("no .fbx .glb .gltf or .prefab under " + folder);

        bool allPass = true;
        sb.Append(",\"models\":[");
        for (int i = 0; i < paths.Count; i++)
        {
            if (i > 0) sb.Append(',');
            allPass &= AppendModel(sb, paths[i], budget);
        }
        verdict = allPass ? "green" : "failed";
        sb.Append("],\"count\":").Append(paths.Count);
        sb.Append(",\"warnings\":").Append(Arr(topWarnings));
        sb.Append(",\"verdict\":").Append(Quote(verdict)).Append('}');
        return Finish(sb.ToString(), outPath, out wrote);
    }

    static string Finish(string json, string outPath, out bool wrote)
    {
        Log(Tag + json);
        wrote = true;
        if (string.IsNullOrEmpty(outPath)) return json;
        try
        {
            string dir = Path.GetDirectoryName(Path.GetFullPath(outPath));
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllText(outPath, json + "\n");
        }
        catch (Exception e)
        {
            Log(Tag + "ERROR could not write " + outPath + ": " + e.Message);
            wrote = false;
        }
        return json;
    }

    // One model row. Returns whether every gate passed.
    static bool AppendModel(StringBuilder sb, string path, Budget budget)
    {
        AssetImporter assetImporter = AssetImporter.GetAtPath(path);
        var importer = assetImporter as ModelImporter;
        var root = AssetDatabase.LoadAssetAtPath<GameObject>(path);
        var warnings = new List<string>();

        long tris = 0;
        int slots = 0, bones = 0, lodLevels = 0;
        var materials = new HashSet<Material>();
        if (root == null)
        {
            warnings.Add("no GameObject at this path (a .glb/.gltf needs glTFast): tris, materials and bones not read");
        }
        else
        {
            // The first LOD level each grouped renderer belongs to; level 0 is the cost up close.
            var level = new Dictionary<Renderer, int>();
            foreach (LODGroup group in root.GetComponentsInChildren<LODGroup>(true))
            {
                LOD[] lods = group.GetLODs();
                lodLevels = Mathf.Max(lodLevels, lods.Length);
                for (int l = 0; l < lods.Length; l++)
                    foreach (Renderer r in lods[l].renderers)
                        if (r != null && !level.ContainsKey(r)) level[r] = l;
            }

            var shared = new List<Material>();
            foreach (Renderer r in root.GetComponentsInChildren<Renderer>(true))
            {
                Mesh mesh;
                if (r is SkinnedMeshRenderer skinned)
                {
                    mesh = skinned.sharedMesh;
                    int bound = skinned.bones != null ? skinned.bones.Length : 0;
                    if (mesh != null) bound = Mathf.Max(bound, mesh.bindposes.Length);
                    bones = Mathf.Max(bones, bound);
                }
                else if (r is MeshRenderer && r.TryGetComponent(out MeshFilter filter)) mesh = filter.sharedMesh;
                else continue;   // particles, lines, sprites: not part of a model's budget

                r.GetSharedMaterials(shared);
                foreach (Material m in shared) if (m != null) materials.Add(m);
                if (level.TryGetValue(r, out int l) && l > 0) continue;
                slots += shared.Count;
                if (mesh != null) tris += Triangles(mesh);
            }
        }

        // Textures: on the materials, in the dependencies, and embedded as sub-assets.
        var textures = new HashSet<Texture2D>();
        foreach (Material m in materials)
            foreach (int id in m.GetTexturePropertyNameIDs())
                if (m.GetTexture(id) is Texture2D t) textures.Add(t);
        foreach (string dep in AssetDatabase.GetDependencies(path, true))
            if (dep != path && AssetDatabase.GetMainAssetTypeAtPath(dep) == typeof(Texture2D))
            {
                var t = AssetDatabase.LoadAssetAtPath<Texture2D>(dep);
                if (t != null) textures.Add(t);
            }
        foreach (Object o in AssetDatabase.LoadAllAssetRepresentationsAtPath(path))
            if (o is Texture2D t) textures.Add(t);
        int texPx = 0;
        string texPath = "";
        foreach (Texture2D t in textures)
        {
            int side = Mathf.Max(t.width, t.height);
            if (side <= texPx) continue;
            texPx = side;
            texPath = AssetDatabase.GetAssetPath(t);
        }

        var clips = new List<string>();
        foreach (Object o in AssetDatabase.LoadAllAssetsAtPath(path))
            if (o is AnimationClip clip && !clip.name.StartsWith("__preview__", StringComparison.Ordinal))
                clips.Add(clip.name);
        clips.Sort(StringComparer.Ordinal);

        string full = Path.Combine(ProjectRoot, path);
        float mb = File.Exists(full) ? (float)(new FileInfo(full).Length / 1048576.0) : 0f;

        int humanBones = importer != null && importer.animationType == ModelImporterAnimationType.Human
            ? importer.humanDescription.human.Length : 0;

        // Gates, then target warnings. A value that could not be read fails a gate set on it.
        bool read = root != null;
        var gates = new StringBuilder(256);
        bool pass = true;
        Gate(gates, ref pass, "ceiling_tris", read, tris, budget.CeilingTris);
        Gate(gates, ref pass, "ceiling_tex_px", true, texPx, budget.CeilingTexPx);
        Gate(gates, ref pass, "max_materials", read, materials.Count, budget.MaxMaterials);
        Gate(gates, ref pass, "max_bones", read, bones, budget.MaxBones);
        if (budget.MaxMb > 0f)
        {
            bool ok = mb <= budget.MaxMb;
            AppendGate(gates, "max_mb", F(mb), F(budget.MaxMb), ok);
            pass &= ok;
        }
        if (read) Target(warnings, "tris", tris, budget.TargetTris);
        Target(warnings, "texPx", texPx, budget.TargetTexPx);

        sb.Append("{\"path\":").Append(Quote(path));
        sb.Append(",\"importer\":").Append(Quote(assetImporter != null ? assetImporter.GetType().Name : ""));
        sb.Append(",\"loaded\":").Append(Bool(read));
        sb.Append(",\"tris\":").Append(tris);
        sb.Append(",\"lodLevels\":").Append(lodLevels);
        sb.Append(",\"materials\":").Append(materials.Count);
        sb.Append(",\"slots\":").Append(slots);
        sb.Append(",\"texPx\":").Append(texPx);
        sb.Append(",\"texPath\":").Append(Quote(texPath));
        sb.Append(",\"bones\":").Append(bones);
        sb.Append(",\"humanBones\":").Append(humanBones);
        sb.Append(",\"mb\":").Append(F(mb));
        sb.Append(",\"animationType\":").Append(Quote(importer != null ? importer.animationType.ToString() : ""));
        sb.Append(",\"clips\":").Append(Arr(clips));
        sb.Append(",\"import\":");
        if (importer == null) sb.Append("null");
        else
        {
            sb.Append("{\"globalScale\":").Append(F(importer.globalScale));
            sb.Append(",\"meshCompression\":").Append(Quote(importer.meshCompression.ToString()));
            sb.Append(",\"readWrite\":").Append(Bool(importer.isReadable));
            sb.Append(",\"importBlendShapes\":").Append(Bool(importer.importBlendShapes));
            sb.Append(",\"materialImportMode\":").Append(Quote(importer.materialImportMode.ToString()));
            sb.Append(",\"optimizeGameObjects\":").Append(Bool(importer.optimizeGameObjects)).Append('}');
        }
        string verdict = Quote(pass ? "green" : "failed");
        sb.Append(",\"gates\":[").Append(gates).Append(']');
        sb.Append(",\"warnings\":").Append(Arr(warnings));
        sb.Append(",\"verdict\":").Append(verdict);

        // The row as a partial ledger record (art-asset-registry): one model, one record.
        bool clipFile = Path.GetExtension(path).ToLowerInvariant() == ".fbx" && Path.GetFileName(path).Contains("@");
        sb.Append(",\"record\":{\"kind\":").Append(Quote(clipFile ? "clip" : "mesh"));
        sb.Append(",\"files\":[{\"path\":").Append(Quote(path)).Append(",\"role\":\"shipped\"}]");
        sb.Append(",\"tool\":{\"skill\":\"unity-3d-models\",\"script\":\"ModelAudit.cs\"}");
        sb.Append(",\"gates\":[").Append(gates).Append(']');
        sb.Append(",\"warnings\":").Append(Arr(warnings));
        sb.Append(",\"verdict\":").Append(verdict).Append("}}");
        return pass;
    }

    static void Gate(StringBuilder gates, ref bool pass, string name, bool read, long value, int limit)
    {
        if (limit <= 0) return;
        bool ok = read && value <= limit;
        AppendGate(gates, name, read ? value.ToString(CultureInfo.InvariantCulture) : "null",
                   limit.ToString(CultureInfo.InvariantCulture), ok);
        pass &= ok;
    }

    static void AppendGate(StringBuilder gates, string name, string value, string limit, bool ok)
    {
        if (gates.Length > 0) gates.Append(',');
        gates.Append("{\"name\":").Append(Quote(name)).Append(",\"value\":").Append(value)
             .Append(",\"limit\":").Append(limit).Append(",\"pass\":").Append(Bool(ok)).Append('}');
    }

    static void Target(List<string> warnings, string name, long value, int target)
    {
        if (target <= 0 || value <= target * (double)TargetSlack) return;
        warnings.Add(name + " " + value + " is over target " + target + " x " + F(TargetSlack));
    }

    // ------------------------------------------------------------------ parts

    // Works on a mesh that is not readable: the index count is metadata.
    static long Triangles(Mesh mesh)
    {
        long indices = 0;
        for (int s = 0; s < mesh.subMeshCount; s++)
            if (mesh.GetTopology(s) == MeshTopology.Triangles) indices += mesh.GetIndexCount(s);
        return indices / 3;
    }

    static string ProjectRoot => Path.GetDirectoryName(Application.dataPath);

    static string ToAssetPath(string absolute)
    {
        string full = Path.GetFullPath(absolute).Replace('\\', '/').TrimEnd('/');
        string assets = Path.GetFullPath(Application.dataPath).Replace('\\', '/').TrimEnd('/');
        if (full == assets) return "Assets";
        return full.StartsWith(assets + "/", StringComparison.Ordinal) ? "Assets" + full.Substring(assets.Length) : null;
    }

    static string Env(string name)
    {
        string v = Environment.GetEnvironmentVariable(name);
        return string.IsNullOrWhiteSpace(v) ? null : v.Trim();
    }

    static int EnvInt(string name)
    {
        string v = Env(name);
        if (v == null) return 0;
        if (int.TryParse(v, NumberStyles.Integer, CultureInfo.InvariantCulture, out int n)) return n;
        throw new FormatException(name + "='" + v + "' is not a whole number");
    }

    static float EnvFloat(string name)
    {
        string v = Env(name);
        if (v == null) return 0f;
        if (float.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out float n)) return n;
        throw new FormatException(name + "='" + v + "' is not a number");
    }

    // One line, no stack trace, so a grep of the log gets the whole JSON.
    static void Log(string line) => Debug.LogFormat(LogType.Log, LogOption.NoStacktrace, null, "{0}", line);

    static string Bool(bool b) => b ? "true" : "false";
    static string F(float v) => v.ToString("0.###", CultureInfo.InvariantCulture);

    static string Arr(List<string> items)
    {
        var sb = new StringBuilder("[");
        for (int i = 0; i < items.Count; i++) sb.Append(i > 0 ? "," : "").Append(Quote(items[i]));
        return sb.Append(']').ToString();
    }

    static string Quote(string s)
    {
        if (s == null) return "\"\"";
        var sb = new StringBuilder(s.Length + 2).Append('"');
        foreach (char ch in s)
        {
            if (ch == '"' || ch == '\\') sb.Append('\\').Append(ch);
            else if (ch == '\n') sb.Append("\\n");
            else if (ch == '\r') sb.Append("\\r");
            else if (ch == '\t') sb.Append("\\t");
            else if (ch < ' ') sb.Append("\\u").Append(((int)ch).ToString("x4"));
            else sb.Append(ch);
        }
        return sb.Append('"').ToString();
    }
}
