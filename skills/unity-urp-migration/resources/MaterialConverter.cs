// Phase 1 materials: snapshot first, convert second, restore third, verify fourth.
// Nothing here changes a shader before the source values are on disk, because after the
// shader changes the old property values are gone and no later pass can recover them.
//
// Put this under Assets/Editor/, let Unity compile, then call the four steps in order:
//   unity command eval --code 'return UnityDev.UrpMigration.MaterialConverter.Snapshot();'
//   unity command eval --code 'return UnityDev.UrpMigration.MaterialConverter.Convert(true);'
//   unity command eval --code 'return UnityDev.UrpMigration.MaterialConverter.Restore();'
//   unity command eval --code 'return UnityDev.UrpMigration.MaterialConverter.Verify();'
//
// The snapshot lands in Library/UrpMigration/material-snapshot.json, outside Assets/ so it
// is neither imported nor committed, and it survives the domain reloads that conversion
// triggers -- which an in-memory dictionary does not.
//
// Confirm on your version: the batch entry point is
// UnityEditor.Rendering.Universal.Converters.RunInBatchMode(ConverterContainerId, List<ConverterId>,
// ConverterFilter). Overloads and ConverterId members differ between URP lines; enumerate the
// type once before relying on it, and fall back to ManualConvert below when it does not resolve.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Rendering.Universal;
using UnityEngine;

namespace UnityDev.UrpMigration
{
    [Serializable]
    public sealed class MaterialSourceRecord
    {
        public string assetPath;
        public string assetGuid;
        public string sourceShader;
        public string mainTexGuid;
        public Vector2 mainTexScale = Vector2.one;
        public Vector2 mainTexOffset = Vector2.zero;
        public Color baseColor = Color.white;
        public string bumpGuid;
        public string metallicGlossGuid;
        public string specGlossGuid;
        public string emissionGuid;
        public Color emissionColor = Color.black;
        public Color specColor = Color.black;
        public float metallic;
        public float glossiness = 0.5f;
        public float cutoff = 0.5f;
        public int renderMode;
    }

    [Serializable]
    public sealed class MaterialSourceTable
    {
        public List<MaterialSourceRecord> records = new List<MaterialSourceRecord>();

        // Materials under Packages/ or Library/PackageCache/: counted, never edited, and
        // carried through to the verify line so they surface as manual follow-up.
        public int skippedPackage;
    }

    public static class MaterialConverter
    {
        public const string SnapshotPath = "Library/UrpMigration/material-snapshot.json";

        const string LitShader = "Universal Render Pipeline/Lit";
        const string ParticleUnlitShader = "Universal Render Pipeline/Particles/Unlit";
        const string TwoDimensionalPrefix = "Universal Render Pipeline/2D/";

        static readonly string[] EffectWords =
        {
            "particle", "fog", "smoke", "steam", "additive", "decal", "vfx"
        };

        static readonly string[] FoliageWords =
        {
            "grass", "tree", "leaf", "foliage", "bush", "billboard", "speedtree", "nature/"
        };

        [MenuItem("Tools/Unity Dev/URP Migration/Materials — Snapshot, Convert, Restore, Verify")]
        public static void RunFromMenu()
        {
            Snapshot();
            Convert(true);
            Restore();
            Verify();
        }

        /// <summary>
        /// Record every project material's source values while it is still on its Built-in
        /// shader. This is the only source of truth for the restore step.
        /// </summary>
        public static string Snapshot()
        {
            var table = new MaterialSourceTable();

            foreach (var guid in AssetDatabase.FindAssets("t:Material"))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                if (IsReadOnlyPath(path)) { table.skippedPackage++; continue; }

                var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
                if (mat == null) continue;

                table.records.Add(new MaterialSourceRecord
                {
                    assetPath = path,
                    assetGuid = guid,
                    sourceShader = mat.shader != null ? mat.shader.name : string.Empty,
                    mainTexGuid = TextureGuid(mat, "_MainTex"),
                    mainTexScale = mat.HasProperty("_MainTex") ? mat.GetTextureScale("_MainTex") : Vector2.one,
                    mainTexOffset = mat.HasProperty("_MainTex") ? mat.GetTextureOffset("_MainTex") : Vector2.zero,
                    baseColor = mat.HasProperty("_Color") ? mat.GetColor("_Color") : Color.white,
                    bumpGuid = TextureGuid(mat, "_BumpMap"),
                    metallicGlossGuid = TextureGuid(mat, "_MetallicGlossMap"),
                    specGlossGuid = TextureGuid(mat, "_SpecGlossMap"),
                    emissionGuid = TextureGuid(mat, "_EmissionMap"),
                    emissionColor = mat.HasProperty("_EmissionColor") ? mat.GetColor("_EmissionColor") : Color.black,
                    specColor = mat.HasProperty("_SpecColor") ? mat.GetColor("_SpecColor") : Color.black,
                    metallic = mat.HasProperty("_Metallic") ? mat.GetFloat("_Metallic") : 0f,
                    glossiness = mat.HasProperty("_Glossiness") ? mat.GetFloat("_Glossiness") : 0.5f,
                    cutoff = mat.HasProperty("_Cutoff") ? mat.GetFloat("_Cutoff") : 0.5f,
                    renderMode = mat.HasProperty("_Mode") ? (int)mat.GetFloat("_Mode") : 0
                });
            }

            Directory.CreateDirectory(Path.GetDirectoryName(SnapshotPath));
            File.WriteAllText(SnapshotPath, JsonUtility.ToJson(table, true));

            var line = "[URP-MIG] materials status=snapshot converted=0/" + table.records.Count +
                       " on2D=0 nullBaseMap=0 effect=" + table.records.Count(r => IsEffect(r)) +
                       " foliage=" + table.records.Count(r => IsFoliage(r)) +
                       " skippedPackage=" + table.skippedPackage +
                       " snapshot=" + SnapshotPath;
            Debug.Log(line);
            return line;
        }

        /// <summary>
        /// Convert. With <paramref name="useConverter"/> the URP batch converter runs; without
        /// it, every material named in the snapshot is assigned its mapped URP shader by hand.
        /// Either way the snapshot must already exist -- a conversion without one cannot be
        /// restored and is refused.
        /// </summary>
        public static string Convert(bool useConverter = true)
        {
            var table = LoadSnapshot();

            if (useConverter)
            {
                Converters.RunInBatchMode(
                    ConverterContainerId.BuiltInToURP,
                    new List<ConverterId> { ConverterId.Material },
                    ConverterFilter.Inclusive);
            }
            else
            {
                foreach (var record in table.records)
                    ManualConvert(record);
            }

            AssetDatabase.SaveAssets();
            return Verify();
        }

        /// <summary>
        /// Copy the snapshot's source values onto the URP properties they map to. Safe to run
        /// after either conversion route, and it is what turns a white untextured material back
        /// into the material the project had.
        /// </summary>
        public static string Restore()
        {
            var table = LoadSnapshot();
            int restored = 0;

            foreach (var record in table.records)
            {
                var mat = AssetDatabase.LoadAssetAtPath<Material>(record.assetPath);
                if (mat == null) continue;

                var mainTex = LoadTexture(record.mainTexGuid);
                if (mainTex != null && mat.HasProperty("_BaseMap"))
                {
                    mat.SetTexture("_BaseMap", mainTex);
                    mat.SetTextureScale("_BaseMap", record.mainTexScale);
                    mat.SetTextureOffset("_BaseMap", record.mainTexOffset);
                }
                if (mat.HasProperty("_BaseColor"))
                    mat.SetColor("_BaseColor", record.baseColor);

                var bump = LoadTexture(record.bumpGuid);
                if (bump != null && mat.HasProperty("_BumpMap"))
                {
                    mat.SetTexture("_BumpMap", bump);
                    mat.EnableKeyword("_NORMALMAP");
                }

                var metallicGloss = LoadTexture(record.metallicGlossGuid);
                if (metallicGloss != null && mat.HasProperty("_MetallicGlossMap"))
                    mat.SetTexture("_MetallicGlossMap", metallicGloss);

                var emission = LoadTexture(record.emissionGuid);
                if (emission != null && mat.HasProperty("_EmissionMap"))
                {
                    mat.SetTexture("_EmissionMap", emission);
                    mat.SetColor("_EmissionColor", record.emissionColor);
                    mat.EnableKeyword("_EMISSION");
                }

                if (mat.HasProperty("_Cutoff"))
                    mat.SetFloat("_Cutoff", record.cutoff);

                EditorUtility.SetDirty(mat);
                restored++;
            }

            AssetDatabase.SaveAssets();
            Debug.Log("[URP-MIG] materials status=restored converted=" + restored + "/" + table.records.Count +
                      " snapshot=" + SnapshotPath);
            return Verify();
        }

        /// <summary>
        /// Reload every material from disk and read back the two things that lie quietly:
        /// which shader it actually landed on, and whether a material that had an albedo
        /// texture still has one.
        /// </summary>
        public static string Verify()
        {
            var table = LoadSnapshot();
            int converted = 0, on2D = 0, nullBaseMap = 0, effect = 0, foliage = 0;
            var offenders = new List<string>();

            foreach (var record in table.records)
            {
                var mat = AssetDatabase.LoadAssetAtPath<Material>(record.assetPath);
                if (mat == null || mat.shader == null) continue;

                var shaderName = mat.shader.name;
                if (shaderName.StartsWith("Universal Render Pipeline/", StringComparison.Ordinal)) converted++;
                if (shaderName.StartsWith(TwoDimensionalPrefix, StringComparison.Ordinal))
                {
                    on2D++;
                    if (offenders.Count < 5) offenders.Add(record.assetPath + " -> " + shaderName);
                }
                if (!string.IsNullOrEmpty(record.mainTexGuid) &&
                    mat.HasProperty("_BaseMap") && mat.GetTexture("_BaseMap") == null)
                {
                    nullBaseMap++;
                    if (offenders.Count < 5) offenders.Add(record.assetPath + " -> _BaseMap null");
                }
                if (IsEffect(record)) effect++;
                if (IsFoliage(record)) foliage++;
            }

            var status = on2D > 0 || nullBaseMap > 0 ? "partial" : "complete";
            var line = "[URP-MIG] materials status=" + status +
                       " converted=" + converted + "/" + table.records.Count +
                       " on2D=" + on2D +
                       " nullBaseMap=" + nullBaseMap +
                       " effect=" + effect +
                       " foliage=" + foliage +
                       " skippedPackage=" + table.skippedPackage +
                       " snapshot=" + SnapshotPath +
                       (offenders.Count == 0 ? string.Empty : " first=" + string.Join(";", offenders));

            Debug.Log(line);
            return line;
        }

        // The manual route names its target shader, so nothing can hijack it. It refuses
        // rather than guesses when the mapped shader is not present in the project.
        static void ManualConvert(MaterialSourceRecord record)
        {
            var mat = AssetDatabase.LoadAssetAtPath<Material>(record.assetPath);
            if (mat == null) return;

            var targetName = IsEffect(record) ? ParticleUnlitShader : LitShader;
            var target = Shader.Find(targetName);
            if (target == null)
                throw new Exception("Shader '" + targetName + "' not found -- is URP installed and compiled?");

            mat.shader = target;
            EditorUtility.SetDirty(mat);

            var mainTex = LoadTexture(record.mainTexGuid);
            if (mainTex != null && mat.HasProperty("_BaseMap"))
            {
                mat.SetTexture("_BaseMap", mainTex);
                if (mat.GetTexture("_BaseMap") == null)
                    throw new Exception("Albedo texture lost while converting " + record.assetPath);
            }
        }

        static MaterialSourceTable LoadSnapshot()
        {
            if (!File.Exists(SnapshotPath))
                throw new Exception("No snapshot at " + SnapshotPath +
                                    " -- run Snapshot() before converting. Without it the source " +
                                    "textures and colours cannot be restored after the shader changes.");
            return JsonUtility.FromJson<MaterialSourceTable>(File.ReadAllText(SnapshotPath));
        }

        static string TextureGuid(Material mat, string property)
        {
            if (!mat.HasProperty(property)) return string.Empty;
            var tex = mat.GetTexture(property);
            if (tex == null) return string.Empty;

            string guid;
            long localId;
            return AssetDatabase.TryGetGUIDAndLocalFileIdentifier(tex, out guid, out localId)
                ? guid
                : string.Empty;
        }

        static Texture LoadTexture(string guid)
        {
            if (string.IsNullOrEmpty(guid)) return null;
            var path = AssetDatabase.GUIDToAssetPath(guid);
            return string.IsNullOrEmpty(path) ? null : AssetDatabase.LoadAssetAtPath<Texture>(path);
        }

        static bool IsReadOnlyPath(string path)
        {
            return path.StartsWith("Packages/", StringComparison.Ordinal) ||
                   path.StartsWith("Library/PackageCache/", StringComparison.Ordinal);
        }

        static bool IsEffect(MaterialSourceRecord record)
        {
            var lower = (record.assetPath + " " + record.sourceShader).ToLowerInvariant();
            return EffectWords.Any(w => lower.Contains(w));
        }

        static bool IsFoliage(MaterialSourceRecord record)
        {
            var lower = (record.assetPath + " " + record.sourceShader).ToLowerInvariant();
            return FoliageWords.Any(w => lower.Contains(w));
        }
    }
}
