#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

/// <summary>
/// The committed, reproducible Android build. Drop into <c>Assets/Scripts/Editor/</c>.
///
/// Clicking through Build Settings is not a procedure: it cannot be repeated or reviewed, it cannot
/// be run by CI, and it silently inherits whatever the last person left in the dialog.
///
/// The split is deliberate. Everything that decides what the artifact IS — scenes, scripting
/// backend, architecture, stripping — is pinned HERE, in code, in the diff. Everything that differs
/// per artifact — output path, versionCode, signing — arrives on the command line. Nothing secret is
/// committed: the keystore password comes from an argument or the environment and is never written
/// into the project.
///
///   Unity -quit -batchmode -nographics -projectPath . -buildTarget Android \
///         -executeMethod BuildScript.BuildAndroid -logFile build.log \
///         -output Builds/game.apk -versionCode 3
///
/// Add -aab for a store bundle, and -keystore/-keystorePass/-keyalias/-keyaliasPass to sign.
/// Pairs with build-android.sh from the same skill, which supplies all of those and then reads the
/// finished artifact back.
/// </summary>
public static class BuildScript
{
    [MenuItem("Tools/Build/Android APK")]
    public static void BuildAndroidFromMenu() => Run(DefaultOutput("apk"), aab: false);

    /// <summary>CLI entry point. Reads its configuration from the command line.</summary>
    public static void BuildAndroid()
    {
        bool aab = HasFlag("-aab");
        string output = Arg("-output") ?? DefaultOutput(aab ? "aab" : "apk");

        string versionCode = Arg("-versionCode");
        if (!string.IsNullOrEmpty(versionCode) && int.TryParse(versionCode, out int vc))
        {
            // Monotonic per artifact handed to ANYONE, not just per store upload. A store rejects a
            // re-used code; a device treats a lower one as a downgrade and refuses to install over
            // what is already there — which testers report as "your app is broken".
            //
            // This assignment holds for THIS build; nothing guarantees it is serialised back into
            // ProjectSettings.asset, so an auto-bump that reads the asset can compute the same
            // number twice. Pass -versionCode explicitly, or bump and commit the asset, and let the
            // build history refuse a re-use. See reference/signing-and-versioning.md.
            PlayerSettings.Android.bundleVersionCode = vc;
            Log($"versionCode = {vc}");
        }

        ApplySigning();
        Run(output, aab);
    }

    static string DefaultOutput(string ext)
    {
        string slug = (PlayerSettings.productName ?? "app").ToLowerInvariant().Replace(' ', '-');
        foreach (char c in Path.GetInvalidFileNameChars()) slug = slug.Replace(c, '-');
        return $"Builds/{slug}.{ext}";
    }

    static void Run(string output, bool aab)
    {
        string[] scenes = EnabledScenes();
        if (scenes.Length == 0)
        {
            // BuildPipeline fails with "Result: Unknown" and NO error line when handed an empty
            // scene list, which in a headless log is indistinguishable from a crash. Fail loudly.
            Fail("no enabled scenes in Build Settings — nothing to build");
            return;
        }

        // Pinned here rather than trusted from the project file, so a CLI build cannot quietly
        // differ from the one that was tested. Stores require 64-bit; ARMv7 and Mono are dead ends.
        EditorUserBuildSettings.buildAppBundle = aab;
        PlayerSettings.SetScriptingBackend(NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
        PlayerSettings.stripEngineCode = true;

        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output)));

        Log($"scenes: {string.Join(", ", scenes)}");
        Log($"package={PlayerSettings.applicationIdentifier} version={PlayerSettings.bundleVersion} " +
            $"code={PlayerSettings.Android.bundleVersionCode} " +
            $"signed={(PlayerSettings.Android.useCustomKeystore ? "release keystore" : "DEBUG KEY")}");

        var options = new BuildPlayerOptions
        {
            scenes = scenes,
            locationPathName = output,
            target = BuildTarget.Android,
            targetGroup = BuildTargetGroup.Android,
            options = BuildOptions.None,   // never Development for a handout: the watermark and
        };                                 // profiler sockets read as a broken build to everyone else

        BuildReport report = BuildPipeline.BuildPlayer(options);
        BuildSummary s = report.summary;

        // totalSize counts symbols and intermediates, NOT the shipped file — e.g. 844 MB reported
        // for a 69 MB APK. The driver reports the artifact's own size; this number is a
        // diagnostic only, and is labelled as one.
        Log($"result={s.result} reportSize(not the artifact)={s.totalSize / (1024 * 1024)} MB " +
            $"errors={s.totalErrors} time={s.totalTime:mm\\:ss} -> {output}");

        if (s.result != BuildResult.Succeeded) { Fail($"build {s.result}"); return; }
        if (Application.isBatchMode) EditorApplication.Exit(0);
    }

    /// <summary>
    /// Signing comes from arguments or the environment, never from the project file — a committed
    /// keystore password is a leaked keystore password.
    /// </summary>
    static void ApplySigning()
    {
        string store = Arg("-keystore") ?? Environment.GetEnvironmentVariable("UNITY_KEYSTORE");
        if (string.IsNullOrEmpty(store))
        {
            PlayerSettings.Android.useCustomKeystore = false;
            Log("no keystore supplied — the artifact will be DEBUG-SIGNED. Installable for testing, " +
                "rejected by stores, and NOT updatable later with a different key.");
            return;
        }
        if (!File.Exists(store)) { Fail($"keystore not found: {store}"); return; }

        PlayerSettings.Android.useCustomKeystore = true;
        PlayerSettings.Android.keystoreName = store;
        PlayerSettings.Android.keystorePass =
            Arg("-keystorePass") ?? Environment.GetEnvironmentVariable("UNITY_KEYSTORE_PASS");
        PlayerSettings.Android.keyaliasName =
            Arg("-keyalias") ?? Environment.GetEnvironmentVariable("UNITY_KEY_ALIAS");
        PlayerSettings.Android.keyaliasPass =
            Arg("-keyaliasPass") ?? Environment.GetEnvironmentVariable("UNITY_KEY_ALIAS_PASS");
        Log($"signing with {Path.GetFileName(store)} alias={PlayerSettings.Android.keyaliasName}");
    }

    static string[] EnabledScenes()
    {
        var list = new List<string>();
        foreach (EditorBuildSettingsScene s in EditorBuildSettings.scenes)
            if (s.enabled && !string.IsNullOrEmpty(s.path)) list.Add(s.path);
        return list.ToArray();
    }

    static string Arg(string name)
    {
        string[] args = Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == name) return args[i + 1];
        return null;
    }

    static bool HasFlag(string name) => Array.IndexOf(Environment.GetCommandLineArgs(), name) >= 0;

    static void Log(string m) => Debug.Log($"[BUILD] {m}");

    static void Fail(string m)
    {
        Debug.LogError($"[BUILD] FAILED: {m}");
        if (Application.isBatchMode) EditorApplication.Exit(1);
    }
}
#endif
