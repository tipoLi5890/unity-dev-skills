// Configure a camera for pixel-perfect 2D under the built-in pipeline — the bool-style
// component from com.unity.2d.pixel-perfect (assembly Unity.2D.PixelPerfect).
//
// Correct only when PipelineDetection.Resolve() returns BuiltIn. Do not add that package
// to a URP project: nothing fails loudly, and the project is left carrying two different
// components under one name. Under URP use CameraSetupURP.cs, whose component URP
// already ships.
//
// This file needs the package installed to compile at all. The types are absent otherwise
// and the error names a missing assembly reference rather than a missing package.
//
// Confirm the assembly name above and the API shape below by reflection on a genuine
// built-in project — never by installing this package into a URP project, which is the
// mistake the skill warns about.
using UnityEngine;
using UnityEngine.U2D;

public static class CameraSetupBuiltIn
{
    /// <param name="camera">the camera to configure; a component is added if absent</param>
    /// <param name="refResX">reference width, e.g. 320 — see SKILL.md section 3</param>
    /// <param name="refResY">reference height, e.g. 180</param>
    /// <param name="assetsPPU">pixels per unit; must match every sprite in the scene</param>
    public static PixelPerfectCamera Configure(Camera camera, int refResX, int refResY, int assetsPPU)
    {
        if (camera == null) throw new System.ArgumentNullException(nameof(camera));
        if (assetsPPU <= 0) throw new System.ArgumentOutOfRangeException(nameof(assetsPPU));

        var pp = camera.GetComponent<PixelPerfectCamera>()
                 ?? camera.gameObject.AddComponent<PixelPerfectCamera>();

        // Identical to the URP path: the camera half is the same problem in both pipelines.
        camera.orthographic = true;
        camera.orthographicSize = (refResY / 2f) / assetsPPU;
        camera.allowHDR = false;
        camera.allowMSAA = false;
        camera.allowDynamicResolution = false;

        pp.assetsPPU = assetsPPU;
        pp.refResolutionX = refResX;
        pp.refResolutionY = refResY;

        // Where the two implementations diverge: five booleans instead of two enums, and the
        // combinations are not all meaningful.
        //
        //   pixelSnapping is ignored while upscaleRT is true — silently, no warning
        //   cropFrameX + cropFrameY both true is the Windowbox equivalent
        //   stretchFill does nothing unless BOTH crop axes are true
        pp.pixelSnapping = true;
        pp.upscaleRT = false;
        pp.cropFrameX = true;
        pp.cropFrameY = true;
        pp.stretchFill = false;

        // Read-only: pp.pixelRatio (int), the whole-number scale actually applied.
        //
        // Absent here and present under URP: RoundToPixel, CorrectCinemachineOrthoSize,
        // requiresUpscalePass, and the component's computed orthographicSize. A camera
        // controller ported from URP has to round world positions itself, and the Cinemachine
        // extension has no size-correction call to make.

        return pp;
    }

    /// <summary>
    /// Project-level settings, separated for the same reason as in the URP file: they belong
    /// to the active quality level, not to this camera.
    /// </summary>
    public static void ApplyQualitySettings()
    {
        QualitySettings.antiAliasing = 0;
        QualitySettings.anisotropicFiltering = AnisotropicFiltering.Disable;
    }

    /// <summary>Report values, not intentions.</summary>
    public static string Describe(PixelPerfectCamera pp)
    {
        return $"ppu={pp.assetsPPU} ref={pp.refResolutionX}x{pp.refResolutionY} " +
               $"pixelSnapping={pp.pixelSnapping} upscaleRT={pp.upscaleRT} " +
               $"crop={pp.cropFrameX}/{pp.cropFrameY} stretchFill={pp.stretchFill} " +
               $"pixelRatio={pp.pixelRatio}";
    }
}
