// Resolve which render pipeline is actually rendering, then hand back the matching
// PixelPerfectCamera type. URP and the standalone package both publish a component
// with that name and they are not interchangeable, so every setup or diagnostic path
// starts here.
//
// Drop into an Editor or runtime folder, or strip the usings and fully qualify to run
// the body through `unity command eval`.
//
// The URP component's assembly:
//   UnityEngine.Rendering.Universal.PixelPerfectCamera
//     -> Unity.RenderPipelines.Universal.2D.Runtime
//
// UnityEngine.U2D.PixelPerfectCamera is reported to live in Unity.2D.PixelPerfect (asmdef
// name; the sources sit in Runtime/, the assembly carries no Runtime suffix). Where
// com.unity.2d.pixel-perfect is absent — the right state on URP — the lookup returns null
// whatever the string says. Confirm it by reflection on a project that genuinely runs the
// built-in pipeline before relying on it.
using UnityEngine;
using UnityEngine.Rendering;

public enum ActivePipeline { BuiltIn, Universal, HighDefinition, Other }

public static class PipelineDetection
{
    const string UrpCameraType =
        "UnityEngine.Rendering.Universal.PixelPerfectCamera, Unity.RenderPipelines.Universal.2D.Runtime";
    // Confirm this assembly name — see the header.
    const string BuiltInCameraType =
        "UnityEngine.U2D.PixelPerfectCamera, Unity.2D.PixelPerfect";

    /// <summary>
    /// Which pipeline is in force. Safe to call before the first frame.
    /// </summary>
    public static ActivePipeline Resolve()
    {
        // currentRenderPipeline folds in the quality-tier override; defaultRenderPipeline
        // does not. With an empty project default and every quality level carrying an
        // override, defaultRenderPipeline reads null while currentRenderPipeline names the URP
        // asset. RenderPipelineManager.currentPipeline is a third answer again: it holds the
        // pipeline instance, which does not exist until a frame has rendered, so at that same
        // instant it can return null while URP is in force.
        var asset = GraphicsSettings.currentRenderPipeline;
        if (asset == null) return ActivePipeline.BuiltIn;

        // Match on FullName. Name alone drops the namespace, and both pipelines end their
        // asset type with "RenderPipelineAsset".
        var fullName = asset.GetType().FullName ?? string.Empty;
        if (fullName.Contains("Universal")) return ActivePipeline.Universal;
        if (fullName.Contains("HighDefinition")) return ActivePipeline.HighDefinition;
        return ActivePipeline.Other;
    }

    /// <summary>
    /// The PixelPerfectCamera type to add for a given pipeline, or null when this project
    /// cannot supply one. Null under Universal means URP is in force but the 2D runtime is
    /// missing; null under BuiltIn means com.unity.2d.pixel-perfect is not installed, which
    /// is the correct state for a URP project and a blocker for a built-in one.
    /// </summary>
    public static System.Type CameraTypeFor(ActivePipeline pipeline)
    {
        if (pipeline == ActivePipeline.HighDefinition) return null;   // unsupported, no component exists

        if (pipeline == ActivePipeline.Universal)
        {
            var urp = System.Type.GetType(UrpCameraType);
            if (urp != null) return urp;
            Debug.LogWarning("URP is in force but PixelPerfectCamera did not resolve. " +
                             "Check that the 2D renderer is present and assigned.");
            return null;
        }

        return System.Type.GetType(BuiltInCameraType);
    }

    /// <summary>
    /// The migration case: URP renders the project but a camera still carries the standalone
    /// component. It compiles, it does not warn, and it half-works, so nothing surfaces it
    /// except this check. See SKILL.md section 9 for what to do about a positive result.
    /// </summary>
    public static bool HasWrongComponent(Camera camera)
    {
        if (camera == null || Resolve() != ActivePipeline.Universal) return false;
        var standalone = System.Type.GetType(BuiltInCameraType);
        return standalone != null && camera.GetComponent(standalone) != null;
    }

    /// <summary>
    /// One line to report before changing anything: pipeline, component type, and whether the
    /// wrong implementation is already on the camera.
    /// </summary>
    public static string Describe(Camera camera)
    {
        var pipeline = Resolve();
        var type = CameraTypeFor(pipeline);
        return $"pipeline={pipeline} component={(type == null ? "<none available>" : type.FullName)} " +
               $"mismatch={HasWrongComponent(camera)}";
    }
}
