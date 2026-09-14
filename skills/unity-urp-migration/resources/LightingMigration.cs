// Phase 3: lighting and reflection probes. Baked data from the old pipeline is live data,
// not history -- it keeps rendering until something clears it, and a scene that blows out
// after the pipeline switch is usually being lit by it.
//
// Put this under Assets/Editor/, let Unity compile, then call the step you need:
//   unity command eval --code 'return UnityDev.UrpMigration.LightingMigration.Inspect();'
//   unity command eval --code 'return UnityDev.UrpMigration.LightingMigration.AssignUrpLightingSettings("Assets/Settings/Runner-URP.lighting");'
//   unity command eval --code 'return UnityDev.UrpMigration.LightingMigration.ClearStaleBake();'
//   unity command eval --code 'return UnityDev.UrpMigration.LightingMigration.StartBake();'
//   unity command eval --code 'return UnityDev.UrpMigration.LightingMigration.BakeStatus();'
//   unity command eval --code 'return UnityDev.UrpMigration.LightingMigration.EnableProbeSettings("Assets/Settings/Runner-URP.asset");'
//   unity command eval --code 'return UnityDev.UrpMigration.LightingMigration.RefreshProbes();'
//
// RefreshProbes records what it observed -- how many probe EXR files changed timestamp -- to
// Library/UrpMigration/probe-refresh.txt, the same way the material step records its snapshot.
// The later read-only steps and the Phase 4 gate report that file rather than the intention of
// whoever ran the refresh, and clearing the bake deletes it, because it no longer describes
// anything that is on disk.
//
// Confirm on your version: Lightmapping.TryGetLightingSettings is the safe reader -- the
// plain lightingSettings getter throws when no settings asset is assigned to the scene, so
// an inspection pass that uses it fails on exactly the projects this skill is for.
// BakeAllReflectionProbesSnapshots is likewise version-sensitive; its return value is
// treated as a claim to check, never as evidence on its own.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

namespace UnityDev.UrpMigration
{
    public static class LightingMigration
    {
        const string BlendingField = "m_ReflectionProbeBlending";
        const string BoxProjectionField = "m_ReflectionProbeBoxProjection";
        const string ProbeEvidencePath = "Library/UrpMigration/probe-refresh.txt";

        [MenuItem("Tools/Unity Dev/URP Migration/Lighting — Inspect")]
        public static void RunFromMenu()
        {
            Inspect();
        }

        /// <summary>
        /// Read-only. Says what the saved scene points at, how much baked data is live, and
        /// whether a bake is running right now.
        /// </summary>
        public static string Inspect()
        {
            return Compose("inspect", BakeState(), ProbeEvidence(), null, null);
        }

        /// <summary>
        /// Create (or reuse) a LightingSettings asset, make it the active scene's settings,
        /// then save the scene and read the reference back out of the saved file. Assigning
        /// the property and calling SaveAssets does not write the scene, and the scene is
        /// where that reference lives.
        /// </summary>
        public static string AssignUrpLightingSettings(string settingsPath)
        {
            var settings = AssetDatabase.LoadAssetAtPath<LightingSettings>(settingsPath);
            if (settings == null)
            {
                var directory = Path.GetDirectoryName(settingsPath);
                if (!string.IsNullOrEmpty(directory) && !Directory.Exists(directory))
                    Directory.CreateDirectory(directory);

                settings = new LightingSettings { name = Path.GetFileNameWithoutExtension(settingsPath) };
                AssetDatabase.CreateAsset(settings, settingsPath);
            }

            Lightmapping.lightingSettings = settings;
            EditorUtility.SetDirty(settings);
            AssetDatabase.SaveAssets();

            var scene = SceneManager.GetActiveScene();
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);

            return Compose("settings-assigned", BakeState(), ProbeEvidence(), null, null);
        }

        /// <summary>
        /// Drop the baked data that is still lighting the scene, then save and re-read. Keep
        /// the rollback point: this is the step that proves a stale bake was the cause, and
        /// it is also the step that makes the old look unrecoverable without it.
        /// </summary>
        public static string ClearStaleBake()
        {
            Lightmapping.Clear();
            Lightmapping.ClearLightingDataAsset();
            if (File.Exists(ProbeEvidencePath)) File.Delete(ProbeEvidencePath);

            var scene = SceneManager.GetActiveScene();
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);

            return Compose("bake-cleared", BakeState(), ProbeEvidence(), null, null);
        }

        /// <summary>
        /// Start an asynchronous bake and return immediately. A bake that is still running at
        /// the end of the turn is a phase boundary, not a failure -- poll with BakeStatus().
        /// </summary>
        public static string StartBake()
        {
            Lightmapping.BakeAsync();
            return Compose("bake-started", BakeState(), ProbeEvidence(), null, null);
        }

        /// <summary>Poll a running bake without touching anything.</summary>
        public static string BakeStatus()
        {
            return Compose("bake-status", BakeState(), ProbeEvidence(), null, null);
        }

        /// <summary>
        /// Allow the URP asset to blend and box-project reflection probes, then prove it from
        /// the asset text on disk. Both public properties are get-only, so the write goes
        /// through SerializedObject and two private field names that carry no compatibility
        /// guarantee -- which is why a missing field reports blocked and hands the job to the
        /// user's inspector instead of returning success.
        /// </summary>
        public static string EnableProbeSettings(string urpAssetPath)
        {
            var urpAsset = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(urpAssetPath);
            if (urpAsset == null)
                throw new Exception("No UniversalRenderPipelineAsset at " + urpAssetPath + ".");

            var serialized = new SerializedObject(urpAsset);
            var blendProp = serialized.FindProperty(BlendingField);
            var boxProp = serialized.FindProperty(BoxProjectionField);

            if (blendProp == null || boxProp == null)
            {
                Debug.LogWarning("[URP-MIG] " + BlendingField + " / " + BoxProjectionField +
                                 " did not resolve on " + urpAsset.name +
                                 ". Tick Probe Blending and Box Projection on the URP asset under " +
                                 "Lighting > Reflection Probes by hand, then re-run this step.");
                return Compose("blocked", BakeState(), ProbeEvidence(), "field-not-found", "field-not-found");
            }

            blendProp.boolValue = true;
            boxProp.boolValue = true;

            // Apply, mark, write -- in that order, and only then read the file. Returning
            // before the save is the version of this that never reaches disk.
            serialized.ApplyModifiedProperties();
            EditorUtility.SetDirty(urpAsset);
            AssetDatabase.SaveAssets();

            var text = File.ReadAllText(urpAssetPath);
            if (!text.Contains(BlendingField + ":"))
                throw new Exception("No '" + BlendingField + ":' line in " + urpAssetPath +
                                    " -- the project is not on Force Text serialization, so nothing here " +
                                    "can be read back. Switch Asset Serialization to Force Text and re-run.");

            var savedBlending = text.Contains(BlendingField + ": 1") ? "1" : "0";
            var savedBoxProjection = text.Contains(BoxProjectionField + ": 1") ? "1" : "0";
            var status = savedBlending == "1" && savedBoxProjection == "1" ? "probes-allowed" : "partial";

            return Compose(status, BakeState(), ProbeEvidence(), savedBlending, savedBoxProjection);
        }

        /// <summary>
        /// Ask for a reflection-probe refresh and then look for evidence that one happened:
        /// which probe EXR files changed timestamp. The call's own return value is a claim.
        /// </summary>
        public static string RefreshProbes()
        {
            var before = ProbeFileTimes();
            var accepted = Lightmapping.BakeAllReflectionProbesSnapshots();
            var after = ProbeFileTimes();

            var changed = after.Count(kv =>
            {
                DateTime previous;
                return !before.TryGetValue(kv.Key, out previous) || previous != kv.Value;
            });

            var evidence = changed > 0 ? changed.ToString() : "unproven";
            RecordProbeEvidence(evidence);

            var status = changed > 0 ? "probes-refreshed" : (accepted ? "partial" : "blocked");
            return Compose(status, BakeState(), evidence, null, null);
        }

        // Evidence lives on disk, not in a field: it has to survive the domain reload that a
        // bake triggers, and a later read-only pass has to be able to report it without
        // re-running anything.
        static void RecordProbeEvidence(string evidence)
        {
            var directory = Path.GetDirectoryName(ProbeEvidencePath);
            if (!string.IsNullOrEmpty(directory) && !Directory.Exists(directory))
                Directory.CreateDirectory(directory);
            File.WriteAllText(ProbeEvidencePath, evidence);
        }

        static string ProbeEvidence()
        {
            if (!File.Exists(ProbeEvidencePath)) return "unproven";

            var recorded = File.ReadAllText(ProbeEvidencePath).Trim();
            return string.IsNullOrEmpty(recorded) ? "unproven" : recorded;
        }

        static string BakeState()
        {
            if (Lightmapping.isRunning) return "running";
            return LightmapSettings.lightmaps.Length > 0 ? "done" : "idle";
        }

        static Dictionary<string, DateTime> ProbeFileTimes()
        {
            var times = new Dictionary<string, DateTime>(StringComparer.Ordinal);
            if (!Directory.Exists("Assets")) return times;

            foreach (var file in Directory.EnumerateFiles("Assets", "*.exr", SearchOption.AllDirectories))
                times[file] = File.GetLastWriteTimeUtc(file);
            return times;
        }

        // One readback line, every field re-queried after whatever the caller just did.
        static string Compose(string status, string bake, string probesRefreshed,
                              string probeBlending, string probeBoxProjection)
        {
            var settingsName = "none";
            try
            {
                LightingSettings settings;
                if (Lightmapping.TryGetLightingSettings(out settings) && settings != null)
                    settingsName = AssetDatabase.GetAssetPath(settings);
            }
            catch (Exception e)
            {
                settingsName = "unreadable:" + e.GetType().Name;
            }

            var scene = SceneManager.GetActiveScene();
            var lightingData = "0";
            var settingsGuid = settingsName == "none" ? "none" : AssetDatabase.AssetPathToGUID(settingsName);
            if (!string.IsNullOrEmpty(scene.path) && File.Exists(scene.path))
            {
                var text = File.ReadAllText(scene.path);
                var marker = "m_LightingDataAsset: {fileID: 0}";
                lightingData = text.Contains(marker) ? "0" : "assigned";
                if (!text.Contains("m_LightingSettings:")) settingsGuid = "not-in-scene";
            }

            var line = "[URP-MIG] lighting status=" + status +
                       " settings=" + settingsGuid +
                       " lightingData=" + lightingData +
                       " lightmaps=" + LightmapSettings.lightmaps.Length +
                       " bake=" + bake +
                       " probeBlending=" + (probeBlending ?? "unread") +
                       " probeBoxProjection=" + (probeBoxProjection ?? "unread") +
                       " probesRefreshed=" + probesRefreshed;

            Debug.Log(line);
            return line;
        }
    }
}
