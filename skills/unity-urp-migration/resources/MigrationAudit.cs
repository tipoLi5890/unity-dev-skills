// Phase 0 inventory for a Built-in -> URP migration. Read-only: it opens no scene,
// writes no asset and changes no setting, so it is safe to run before a rollback
// point exists.
//
// Put this under Assets/Editor/, let Unity compile, then call it with one line:
//   unity command eval --code 'return UnityDev.UrpMigration.MigrationAudit.Run();'
//
// Pipeline detection here is deliberately the same logic as the resolver shipped with
// the unity-2d-pixel-perfect skill (resources/PipelineDetection.cs): read the project
// default, then read every quality tier, and never infer the pipeline from a URP asset
// sitting on disk. Two detectors are already one too many -- extend one of them rather
// than adding a third to the project.
//
// Confirm on your version: PackageInfo.GetAllRegisteredPackages() is an Editor API whose
// namespace has moved between lines. If it does not resolve, the manifest fallback below
// still answers the only question this script asks of it.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace UnityDev.UrpMigration
{
    public static class MigrationAudit
    {
        // Markers whose presence changes the shape of the migration. Each one is a file-text
        // search, so a hit is a candidate to read, never a verdict.
        static readonly string[] RiskMarkers =
        {
            "PostProcessLayer", "OnRenderImage(", "SetReplacementShader", "RenderWithShader",
            "#pragma surface", "GrabPass", "CGPROGRAM", "CommandBuffer",
            "Nature/", "SpeedTree", "_Cutoff"
        };

        static readonly string[] EffectWords =
        {
            "particle", "fog", "smoke", "steam", "additive", "decal", "vfx"
        };

        static readonly string[] FoliageWords =
        {
            "grass", "tree", "leaf", "foliage", "bush", "billboard", "speedtree"
        };

        [MenuItem("Tools/Unity Dev/URP Migration/Audit")]
        public static void RunFromMenu()
        {
            Run();
        }

        /// <summary>
        /// One readback line describing the project as it is saved on disk right now.
        /// </summary>
        public static string Run()
        {
            var graphics = GraphicsSettings.defaultRenderPipeline;
            var pipeline = Classify(graphics);

            var tierNames = QualitySettings.names;
            var tiers = new List<string>();
            for (int i = 0; i < tierNames.Length; i++)
            {
                var asset = QualitySettings.GetRenderPipelineAssetAt(i);
                tiers.Add(tierNames[i] + "=" + (asset == null ? "inherits" : asset.name));
                if (asset != null && pipeline == "BuiltIn") pipeline = Classify(asset);
            }

            var packages = RegisteredPackageIds();
            var urpPackage = packages.Contains("com.unity.render-pipelines.universal");
            var ppv2Package = packages.Contains("com.unity.postprocessing");

            int materials = 0, standard = 0, particle = 0, foliage = 0, custom = 0, packageOwned = 0;
            foreach (var guid in AssetDatabase.FindAssets("t:Material"))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                materials++;
                if (IsReadOnlyPath(path)) { packageOwned++; continue; }

                var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
                var shaderName = mat != null && mat.shader != null ? mat.shader.name : string.Empty;
                var lower = (path + " " + shaderName).ToLowerInvariant();

                if (FoliageWords.Any(w => lower.Contains(w)) || shaderName.StartsWith("Nature/", StringComparison.Ordinal))
                    foliage++;
                else if (EffectWords.Any(w => lower.Contains(w)))
                    particle++;
                else if (shaderName.StartsWith("Standard", StringComparison.Ordinal) ||
                         shaderName.StartsWith("Legacy Shaders/", StringComparison.Ordinal) ||
                         shaderName.StartsWith("Mobile/", StringComparison.Ordinal))
                    standard++;
                else
                    custom++;
            }

            var risk = ScanRiskMarkers();

            // PPv2 lives in scene components, and a text search over a compressed or binary
            // scene finds nothing. Ask the open scene by type name instead.
            var ppv2InScene = UnityEngine.Object
                .FindObjectsByType<Behaviour>(FindObjectsSortMode.None)
                .Count(b => b != null && b.GetType().FullName != null &&
                            b.GetType().FullName.StartsWith("UnityEngine.Rendering.PostProcessing.", StringComparison.Ordinal));

            var lightingSettings = "none";
            try
            {
                LightingSettings settings;
                if (Lightmapping.TryGetLightingSettings(out settings) && settings != null)
                    lightingSettings = settings.name;
            }
            catch (Exception e)
            {
                lightingSettings = "unreadable:" + e.GetType().Name;
            }

            var probes = UnityEngine.Object
                .FindObjectsByType<ReflectionProbe>(FindObjectsSortMode.None).Length;

            var line = string.Join(" ", new[]
            {
                "[URP-MIG] audit",
                "pipeline=" + pipeline,
                "graphics=" + (graphics == null ? "none" : graphics.name),
                "tiers=" + (tiers.Count == 0 ? "none" : string.Join("|", tiers)),
                "urpPackage=" + urpPackage,
                "ppv2Package=" + ppv2Package,
                "ppv2InScene=" + ppv2InScene,
                "materials=" + materials,
                "standard=" + standard,
                "particle=" + particle,
                "foliage=" + foliage,
                "custom=" + custom,
                "packageOwned=" + packageOwned,
                "risk=" + (risk.Count == 0 ? "none" : string.Join(",", risk.Select(kv => kv.Key + ":" + kv.Value))),
                "lightmaps=" + LightmapSettings.lightmaps.Length,
                "lightingData=" + lightingSettings,
                "probes=" + probes,
                "scene=" + UnityEngine.SceneManagement.SceneManager.GetActiveScene().name
            });

            Debug.Log(line);
            return line;
        }

        static string Classify(RenderPipelineAsset asset)
        {
            if (asset == null) return "BuiltIn";
            var fullName = asset.GetType().FullName ?? string.Empty;
            if (fullName.Contains("Universal")) return "URP";
            if (fullName.Contains("HighDefinition")) return "HDRP";
            return "Other:" + asset.GetType().Name;
        }

        static bool IsReadOnlyPath(string path)
        {
            return path.StartsWith("Packages/", StringComparison.Ordinal) ||
                   path.StartsWith("Library/PackageCache/", StringComparison.Ordinal);
        }

        static HashSet<string> RegisteredPackageIds()
        {
            var ids = new HashSet<string>(StringComparer.Ordinal);
            try
            {
                foreach (var info in UnityEditor.PackageManager.PackageInfo.GetAllRegisteredPackages())
                    ids.Add(info.name);
            }
            catch (Exception)
            {
                // Fallback: the manifest answers "is it asked for", which is what the audit needs.
                var manifest = "Packages/manifest.json";
                if (File.Exists(manifest))
                {
                    var text = File.ReadAllText(manifest);
                    if (text.Contains("com.unity.render-pipelines.universal"))
                        ids.Add("com.unity.render-pipelines.universal");
                    if (text.Contains("com.unity.postprocessing"))
                        ids.Add("com.unity.postprocessing");
                }
            }
            return ids;
        }

        static Dictionary<string, int> ScanRiskMarkers()
        {
            var counts = new Dictionary<string, int>(StringComparer.Ordinal);
            if (!Directory.Exists("Assets")) return counts;

            var extensions = new HashSet<string>(new[] { ".cs", ".shader", ".cginc", ".hlsl", ".shadersubgraph" },
                StringComparer.OrdinalIgnoreCase);

            foreach (var file in Directory.EnumerateFiles("Assets", "*.*", SearchOption.AllDirectories))
            {
                if (!extensions.Contains(Path.GetExtension(file))) continue;

                string text;
                try { text = File.ReadAllText(file); }
                catch (IOException) { continue; }

                foreach (var marker in RiskMarkers)
                {
                    if (!text.Contains(marker)) continue;
                    int existing;
                    counts.TryGetValue(marker, out existing);
                    counts[marker] = existing + 1;
                }
            }
            return counts;
        }
    }
}
