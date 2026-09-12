#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.Build;
using UnityEngine;

/// <summary>
/// The ten release settings for a web artifact, applied as one reviewable batch. Drop into
/// <c>Assets/Scripts/Editor/</c>.
///
/// Why a file and not an inline snippet: a class declaration cannot be flattened into the
/// statement block that <c>eval</c> compiles, and these ten values are worth pinning in the diff
/// rather than retyping. Once compiled, one line runs it:
///
///   UnityEditor.EditorApplication.ExecuteMenuItem("Tools/Unity Dev/Apply Web Release Settings");
///
/// Requires the Web build-support module. Without it, <c>UnityEditor.WebGL</c> does not resolve and
/// the whole Editor assembly fails with CS0234 — which does not just break this file, it aborts
/// every <c>-executeMethod</c> in the project. On a machine that is only staging the other nine
/// settings, delete the codeOptimization assignment and its read-back line first.
///
/// Adapt before running:
///   - Gzip instead of Brotli if the host is plain HTTP;
///   - ExplicitlyThrownExceptionsOnly instead of None if the game genuinely catches;
///   - drop the wasm2023 line if the target browser baseline predates Wasm 2023 exception
///     handling — it is the one setting here with a prerequisite outside the project.
///
/// Not here: initialMemorySize. Every value below is a fixed choice; that one comes from the
/// game's own measured peak, so set it in its own call and say which number you used.
/// </summary>
public static class WebOptimizer
{
    [MenuItem("Tools/Unity Dev/Apply Web Release Settings")]
    public static void ApplyReleaseSettings()
    {
        var target = NamedBuildTarget.WebGL;

        // Per-target. The same project can hold a different value for Android, and reading the
        // wrong target is how a setting looks unset when it is merely elsewhere.
        PlayerSettings.SetIl2CppCodeGeneration(target, Il2CppCodeGeneration.OptimizeSize);
        PlayerSettings.SetManagedStrippingLevel(target, ManagedStrippingLevel.High);
        PlayerSettings.SetApiCompatibilityLevel(target, ApiCompatibilityLevel.NET_Standard);

        // Global, not per-target: this write lands on every platform the project ships.
        PlayerSettings.stripUnusedMeshComponents = true;
        PlayerSettings.WebGL.dataCaching = true;
        PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Brotli;
        PlayerSettings.WebGL.exceptionSupport = WebGLExceptionSupport.None;
        PlayerSettings.WebGL.debugSymbolMode = WebGLDebugSymbolMode.Off;
        PlayerSettings.WebGL.wasm2023 = true;

        // The odd one out: it is not a Player Setting and does not reach ProjectSettings.asset.
        UnityEditor.WebGL.UserBuildSettings.codeOptimization =
            UnityEditor.WebGL.WasmCodeOptimization.DiskSizeLTO;

        // Everything above this line changed objects held in memory and nothing else. Skip the
        // save and the log below still prints the new values, the run still reports success, and
        // the file on disk is untouched — the edit dies with the Editor session. A batch Editor
        // launched with -quit saves on exit and hides the omission, so a green headless run is not
        // evidence that this call is unnecessary.
        AssetDatabase.SaveAssets();

        // Report values, never "applied successfully". Nine of the ten are now in
        // ProjectSettings.asset; codeOptimization lives in Library/EditorUserBuildSettings.asset,
        // which is gitignored, so this log is the only place it can be confirmed and CI has to
        // re-apply it as its own step.
        Debug.Log(
            "Web release settings applied and saved:\n"
            + $"  il2cppCodeGeneration      = {PlayerSettings.GetIl2CppCodeGeneration(target)}\n"
            + $"  managedStrippingLevel     = {PlayerSettings.GetManagedStrippingLevel(target)}\n"
            + $"  apiCompatibilityLevel     = {PlayerSettings.GetApiCompatibilityLevel(target)}\n"
            + $"  stripUnusedMeshComponents = {PlayerSettings.stripUnusedMeshComponents}\n"
            + $"  dataCaching               = {PlayerSettings.WebGL.dataCaching}\n"
            + $"  compressionFormat         = {PlayerSettings.WebGL.compressionFormat}\n"
            + $"  exceptionSupport          = {PlayerSettings.WebGL.exceptionSupport}\n"
            + $"  debugSymbolMode           = {PlayerSettings.WebGL.debugSymbolMode}\n"
            + $"  wasm2023                  = {PlayerSettings.WebGL.wasm2023}\n"
            + $"  codeOptimization          = {UnityEditor.WebGL.UserBuildSettings.codeOptimization}");
    }
}
#endif
