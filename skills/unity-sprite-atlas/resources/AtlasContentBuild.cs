#if UNITY_EDITOR
// Builds the Addressables content that late-bound atlases live in.
//
// Drop into Assets/Scripts/Editor/, beside AtlasBuildGenerator.cs. It is the second of
// the three pieces late binding needs; on its own it does nothing useful.
//
// callbackOrder is above the generator's so the content build sees freshly written atlases.
// The two run at different points of the build anyway — this one is a postprocess — but keeping
// the order explicit makes the dependency visible to whoever reads the file next.
//
// The Addressables API shapes this relies on (enumerate them on your version):
// AddressableAssetSettings.BuildPlayerContent exists both with no arguments and with an
// out AddressablesPlayerBuildResult; that result carries Error and Duration.
// AddressableAssetSettingsDefaultObject.Settings is a static property and is null until the
// project has actually initialised Addressables.
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

#if UNITY_ADDRESSABLES
using UnityEditor.AddressableAssets;
using UnityEditor.AddressableAssets.Settings;
#endif

public sealed class AtlasContentBuild : IPostprocessBuildWithReport
{
    public int callbackOrder => 1;

    public void OnPostprocessBuild(BuildReport report)
    {
#if UNITY_ADDRESSABLES
        var settings = AddressableAssetSettingsDefaultObject.Settings;
        if (settings == null)
        {
            // Loud, because the player that was just built has entries nothing will satisfy.
            Debug.LogError("[atlas] Addressables is not initialised — no content was built for the late-bound atlases.");
            return;
        }

        AddressableAssetSettings.BuildPlayerContent(out var result);

        if (!string.IsNullOrEmpty(result.Error))
        {
            Debug.LogError($"[atlas] Addressables content build failed: {result.Error}");
            return;
        }

        // Report the duration: a content build that finishes implausibly fast is usually one that
        // found nothing to do, which looks identical to success from here.
        Debug.Log($"[atlas] Addressables content built in {result.Duration:0.0}s");
#else
        Debug.LogWarning("[atlas] UNITY_ADDRESSABLES is not defined — skipping the content build.");
#endif
    }
}
#endif
