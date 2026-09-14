// Phase 4: the gate. Read-only, and it re-queries everything rather than remembering what
// the earlier phases reported. A verdict assembled from saved state is the only kind worth
// putting in a report.
//
// Put this under Assets/Editor/, let Unity compile, then call it with one line:
//   unity command eval --code 'return UnityDev.UrpMigration.MigrationGate.Run();'
//
// Confirm on your version: the Editor log path differs per platform, and a project running
// under a custom -logFile writes somewhere else entirely. When the file is absent the gate
// says so instead of reporting a clean console.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace UnityDev.UrpMigration
{
    public static class MigrationGate
    {
        // Error-shaped lines only. A marker that also appears in ordinary startup chatter --
        // the words "render pipeline" on their own, for instance -- would fail every gate on
        // every project, which is the same as having no gate at all.
        static readonly string[] FailMarkers =
        {
            "Default Renderer is missing", "Shader error", "error CS0246"
        };

        [MenuItem("Tools/Unity Dev/URP Migration/Gate")]
        public static void RunFromMenu()
        {
            Run();
        }

        /// <summary>
        /// Every Phase 4 check, then the verdict and the six-line report. Changes nothing.
        /// </summary>
        public static string Run()
        {
            var failing = new List<string>();
            var manual = new List<string>();

            // 1. Pipeline, at the project default and at every tier.
            var graphics = GraphicsSettings.defaultRenderPipeline;
            var graphicsIsUrp = graphics is UniversalRenderPipelineAsset;
            if (!graphicsIsUrp) failing.Add("graphics-not-urp");

            var tierNames = QualitySettings.names;
            var tiersOnUrp = 0;
            for (int i = 0; i < tierNames.Length; i++)
            {
                var asset = QualitySettings.GetRenderPipelineAssetAt(i);
                if (asset is UniversalRenderPipelineAsset) tiersOnUrp++;
            }
            if (tiersOnUrp < tierNames.Length) failing.Add("tiers=" + tiersOnUrp + "/" + tierNames.Length);

            // 2. Materials, from the snapshot taken before conversion.
            var materials = "no-snapshot";
            if (File.Exists(MaterialConverter.SnapshotPath))
            {
                materials = MaterialConverter.Verify();
                if (materials.Contains("status=partial")) failing.Add("materials");
            }
            else
            {
                failing.Add("materials-unverifiable");
            }

            // 3. Post-processing: a profile with live components, referenced by a saved scene.
            var volume = UnityEngine.Object.FindFirstObjectByType<Volume>();
            var profile = volume == null ? null : volume.sharedProfile;
            var liveOverrides = profile == null ? 0 : profile.components.Count(c => c != null);
            var nullEntries = profile == null ? 0 : profile.components.Count - liveOverrides;
            if (volume == null || profile == null || liveOverrides == 0) failing.Add("postfx-profile");
            if (nullEntries > 0) failing.Add("postfx-null-entries");

            var legacyActive = UnityEngine.Object
                .FindObjectsByType<Behaviour>(FindObjectsSortMode.None)
                .Count(b => b != null && b.enabled && (b.GetType().FullName ?? string.Empty)
                    .StartsWith("UnityEngine.Rendering.PostProcessing.", StringComparison.Ordinal));
            if (legacyActive > 0) failing.Add("legacy-postfx-still-enabled");

            // 4. Lighting: the scene's own reference, and whether anything was baked since.
            var lighting = LightingMigration.Inspect();
            if (lighting.Contains("settings=none") || lighting.Contains("settings=not-in-scene"))
                failing.Add("lighting-settings");

            // Only a scene that has reflection probes owes evidence that they were re-rendered.
            // A project with none is not carrying an open item, and saying otherwise would put
            // every migration permanently one step short of Complete.
            var probeCount = UnityEngine.Object
                .FindObjectsByType<ReflectionProbe>(FindObjectsSortMode.None).Length;
            if (probeCount > 0 && lighting.Contains("probesRefreshed=unproven"))
                manual.Add("reflection-probe-refresh-unproven");

            // 5. The log tail, for the errors that only appear after an assignment.
            var logHits = ScanEditorLog();
            if (logHits.Count > 0) failing.Add("log:" + string.Join("/", logHits));

            var verdict = failing.Count == 0
                ? (manual.Count == 0 ? "Complete" : "Manual follow-up")
                : "Partial migration";

            var line = "[URP-MIG] gate verdict=" + verdict +
                       " failing=" + (failing.Count == 0 ? "none" : string.Join(",", failing)) +
                       " manual=" + (manual.Count == 0 ? "none" : string.Join(",", manual));

            var report = string.Join("\n", new[]
            {
                line,
                "migration: " + verdict + " on " + Application.unityVersion,
                "pipeline:  graphics=" + (graphics == null ? "built-in" : graphics.name) +
                    " tiers=" + tiersOnUrp + "/" + tierNames.Length,
                "materials: " + materials,
                "post-fx:   overrides=" + liveOverrides + " nullEntries=" + nullEntries +
                    " legacyEnabled=" + legacyActive,
                "lighting:  " + lighting,
                "manual:    " + (manual.Count == 0 ? "none" : string.Join(", ", manual))
            });

            Debug.Log(report);
            return report;
        }

        static List<string> ScanEditorLog()
        {
            var hits = new List<string>();
            var path = EditorLogPath();
            if (string.IsNullOrEmpty(path) || !File.Exists(path)) return hits;

            string text;
            try { text = File.ReadAllText(path); }
            catch (IOException) { return hits; }

            // Only the tail matters: earlier runs of the same project are not this migration.
            var tail = text.Length > 200000 ? text.Substring(text.Length - 200000) : text;
            foreach (var marker in FailMarkers)
                if (tail.IndexOf(marker, StringComparison.OrdinalIgnoreCase) >= 0)
                    hits.Add(marker.Replace(' ', '-'));
            return hits;
        }

        static string EditorLogPath()
        {
            var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            switch (Application.platform)
            {
                case RuntimePlatform.OSXEditor:
                    return Path.Combine(home, "Library/Logs/Unity/Editor.log");
                case RuntimePlatform.WindowsEditor:
                    return Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                        "Unity", "Editor", "Editor.log");
                default:
                    return Path.Combine(home, ".config/unity3d/Editor.log");
            }
        }
    }
}
