// Phase 1: put a URP asset in force at the project default AND at every quality tier,
// then prove it from the saved settings file rather than from the objects in memory.
//
// Put this under Assets/Editor/, let Unity compile, then call it with one line:
//   unity command eval --code 'return UnityDev.UrpMigration.PipelineAssignment.Run("Assets/Settings/Runner-URP.asset");'
//
// There is no per-index setter for the quality tiers. The supported route is to walk the
// tiers with SetQualityLevel, assign QualitySettings.renderPipeline at each one, then put
// the original level back -- which is what this does. Never reach for an invented
// SetRenderPipelineAssetAt; it does not exist and a guess here silently assigns nothing.
//
// Confirm on your version: UniversalRenderPipelineAsset.rendererDataList and
// UniversalRendererData.postProcessData are the members this reads. If either does not
// resolve, report the renderer check as unproven rather than skipping it quietly.
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace UnityDev.UrpMigration
{
    public static class PipelineAssignment
    {
        const string QualityFile = "ProjectSettings/QualitySettings.asset";

        [MenuItem("Tools/Unity Dev/URP Migration/Assign Pipeline")]
        public static void RunFromMenu()
        {
            var path = EditorUtility.OpenFilePanel("Pick the URP asset", "Assets", "asset");
            if (string.IsNullOrEmpty(path)) return;
            var index = path.IndexOf("Assets/", StringComparison.Ordinal);
            Run(index >= 0 ? path.Substring(index) : path);
        }

        /// <summary>
        /// Assign <paramref name="urpAssetPath"/> at Graphics settings and, when
        /// <paramref name="allTiers"/> is true, at every quality level. Returns one readback
        /// line built from the re-queried tiers and from the saved settings text.
        /// </summary>
        public static string Run(string urpAssetPath, bool allTiers = true)
        {
            var asset = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(urpAssetPath);
            if (asset == null)
                throw new Exception("No UniversalRenderPipelineAsset at " + urpAssetPath +
                                    " -- create the asset and its renderer first, then re-run.");

            GraphicsSettings.defaultRenderPipeline = asset;

            var originalLevel = QualitySettings.GetQualityLevel();
            var tierNames = QualitySettings.names;
            if (allTiers)
            {
                try
                {
                    for (int i = 0; i < tierNames.Length; i++)
                    {
                        QualitySettings.SetQualityLevel(i);
                        QualitySettings.renderPipeline = asset;
                    }
                }
                finally
                {
                    // Leaving the project on a different quality level is a side effect the
                    // migration did not ask for, so restore it even when an assignment throws.
                    QualitySettings.SetQualityLevel(originalLevel);
                }
            }

            AssetDatabase.SaveAssets();

            // Readback 1: ask the tiers again, one by one.
            var tiers = new List<string>();
            int assignedTiers = 0;
            for (int i = 0; i < tierNames.Length; i++)
            {
                var at = QualitySettings.GetRenderPipelineAssetAt(i);
                if (at == asset) assignedTiers++;
                tiers.Add(tierNames[i] + "=" + (at == null ? "inherits" : at.name));
            }

            // Readback 2: count explicit tier overrides in the file that was just written.
            // A tier reading "inherits" in memory and carrying no line here is the trap that
            // makes a migration look finished while one tier still renders built-in.
            int explicitTiers = 0;
            if (File.Exists(QualityFile))
            {
                var text = File.ReadAllText(QualityFile);
                var needle = "renderPipeline: {fileID: 11400000";
                int at = text.IndexOf(needle, StringComparison.Ordinal);
                while (at >= 0)
                {
                    explicitTiers++;
                    at = text.IndexOf(needle, at + needle.Length, StringComparison.Ordinal);
                }
            }

            // Renderers: a null postProcessData on any renderer the project can switch to
            // produces "post-processing set but nothing appears" later in the migration.
            var renderers = new List<string>();
            bool postProcessDataOk = true;
            var dataList = asset.rendererDataList;
            for (int i = 0; i < dataList.Length; i++)
            {
                var data = dataList[i] as UniversalRendererData;
                var hasPost = data != null && data.postProcessData != null;
                if (data != null && !hasPost) postProcessDataOk = false;
                renderers.Add((dataList[i] == null ? "null" : dataList[i].name) + ":post=" + hasPost);
            }
            if (dataList.Length == 0) postProcessDataOk = false;

            var graphicsOk = GraphicsSettings.defaultRenderPipeline == asset;
            var tiersOk = !allTiers || assignedTiers == tierNames.Length;
            var status = graphicsOk && tiersOk && explicitTiers >= (allTiers ? tierNames.Length : 0) && postProcessDataOk
                ? "complete"
                : "partial";

            var line = "[URP-MIG] pipeline status=" + status +
                       " graphics=" + (graphicsOk ? asset.name : "MISMATCH") +
                       " tiers=" + string.Join("|", tiers) +
                       " explicitTiers=" + explicitTiers + "/" + tierNames.Length +
                       " renderers=" + (renderers.Count == 0 ? "none" : string.Join(",", renderers)) +
                       " postProcessData=" + postProcessDataOk;

            Debug.Log(line);
            return line;
        }
    }
}
