// IosBuildScript — headless iOS build entry point. Drop into Assets/Editor/ (any Editor assembly).
//
//   Unity -batchmode -quit -projectPath . -buildTarget iOS \
//         -executeMethod IosBuildScript.Build -logFile /tmp/ios-unity.log
//
// Environment (nothing identifying is committed):
//   IOS_BUILD_OUT      output folder for the Xcode project   (default: Builds/ios)
//   IOS_BUNDLE_ID      bundle identifier                      (default: keep the project's)
//   IOS_TEAM_ID        Apple TEAM id (the profile's TeamIdentifier / the certificate's OU —
//                      NOT the id in the certificate's name)  (default: unset → unsigned project,
//                      still fine for the compile-only gate)
//   IOS_MIN_VERSION    minimum iOS version                    (default: 15.0)
//   IOS_DEVELOPMENT    "1" → development build                (default: 1)
//
// The output folder is deleted first: a stale Xcode project must never read as success.
// Every failure path exits non-zero — in batchmode an exception inside -executeMethod can
// otherwise still end in exit 0.
#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

public static class IosBuildScript
{
    static string Env(string name, string fallback = null)
    {
        var v = Environment.GetEnvironmentVariable(name);
        return string.IsNullOrEmpty(v) ? fallback : v;
    }

    [MenuItem("Build/iOS Xcode Project")]
    public static void Build()
    {
        try
        {
            var scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray();
            if (scenes.Length == 0) Fail("no enabled scenes in EditorBuildSettings — a build with zero scenes boots to black");
            foreach (var s in scenes) if (!File.Exists(s)) Fail("scene in EditorBuildSettings does not exist: " + s);

            if (!BuildPipeline.IsBuildTargetSupported(BuildTargetGroup.iOS, BuildTarget.iOS))
                Fail("iOS Build Support is not installed for this Editor");

            string outDir = Path.GetFullPath(Env("IOS_BUILD_OUT", "Builds/ios"));
            if (Directory.Exists(outDir)) Directory.Delete(outDir, true);
            Directory.CreateDirectory(Path.GetDirectoryName(outDir));

            string bundle = Env("IOS_BUNDLE_ID");
            if (bundle != null) PlayerSettings.SetApplicationIdentifier(NamedBuildTarget.iOS, bundle);
            if (PlayerSettings.GetApplicationIdentifier(NamedBuildTarget.iOS).StartsWith("com.DefaultCompany", StringComparison.OrdinalIgnoreCase))
                Debug.LogWarning("[IosBuild] bundle id is still Unity's template default");

            string team = Env("IOS_TEAM_ID");
            if (team != null)
            {
                PlayerSettings.iOS.appleDeveloperTeamID = team;
                PlayerSettings.iOS.appleEnableAutomaticSigning = true;   // the mode that works from a terminal
            }
            PlayerSettings.iOS.targetOSVersionString = Env("IOS_MIN_VERSION", "15.0");
            PlayerSettings.SetScriptingBackend(NamedBuildTarget.iOS, ScriptingImplementation.IL2CPP);

            var opts = new BuildPlayerOptions
            {
                scenes = scenes,
                target = BuildTarget.iOS,
                targetGroup = BuildTargetGroup.iOS,
                locationPathName = outDir,
                options = Env("IOS_DEVELOPMENT", "1") == "1" ? BuildOptions.Development : BuildOptions.None,
            };

            Debug.Log($"[IosBuild] bundle={PlayerSettings.GetApplicationIdentifier(NamedBuildTarget.iOS)} " +
                      $"team={(team ?? "(none)")} min={PlayerSettings.iOS.targetOSVersionString} out={outDir}");

            BuildReport report = BuildPipeline.BuildPlayer(opts);
            if (report.summary.result != BuildResult.Succeeded)
                Fail($"BuildPlayer result={report.summary.result} errors={report.summary.totalErrors}");
            if (!Directory.Exists(Path.Combine(outDir, "Unity-iPhone.xcodeproj")))
                Fail("BuildPlayer reported success but there is no Unity-iPhone.xcodeproj in " + outDir);

            Debug.Log("[IosBuild] OK " + outDir);
        }
        catch (BuildAbort) { throw; }
        catch (Exception e)
        {
            Debug.LogError("[IosBuild] FAILED " + e);
            if (Application.isBatchMode) EditorApplication.Exit(1);
            throw;
        }
    }

    sealed class BuildAbort : Exception { public BuildAbort(string m) : base(m) { } }

    static void Fail(string why)
    {
        Debug.LogError("[IosBuild] FAILED " + why);
        if (Application.isBatchMode) EditorApplication.Exit(1);
        throw new BuildAbort(why);
    }
}
#endif
