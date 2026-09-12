// Configure a camera for pixel-perfect 2D under URP — the enum-style component.
//
// Only correct when PipelineDetection.Resolve() returns Universal. Under the built-in
// pipeline this file does not even compile, because the type lives in URP's own assembly
// (Unity.RenderPipelines.Universal.2D.Runtime).
// Use CameraSetupBuiltIn.cs there.
//
// Nothing here is a project-wide sweep: it takes one camera and returns what it configured.
// The caller decides which cameras, and reports before applying.
using UnityEngine;
using UnityEngine.Rendering.Universal;

public static class CameraSetupURP
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

        camera.orthographic = true;

        // Half the reference height, converted from pixels to world units. 320x180 at PPU 16
        // gives 90 / 16 = 5.625. The component's own read-only orthographicSize is a separate
        // computed value — do not read one expecting the other.
        camera.orthographicSize = (refResY / 2f) / assetsPPU;

        // Three camera features that each exist to smooth or resample the frame, which is the
        // one thing this setup is protecting.
        camera.allowHDR = false;
        camera.allowMSAA = false;
        camera.allowDynamicResolution = false;

        pp.assetsPPU = assetsPPU;
        pp.refResolutionX = refResX;
        pp.refResolutionY = refResY;

        // PixelSnapping snaps sprite renderers at render time and leaves transforms alone, so
        // post-processing and UI keep working. UpscaleRenderTexture is the authentic look and
        // costs both — SKILL.md section 7.
        pp.gridSnapping = PixelPerfectCamera.GridSnapping.PixelSnapping;

        // Windowbox gives up screen edges rather than the pixel grid on aspects that do not
        // divide evenly. Alternatives: None, Pillarbox, Letterbox, StretchFill.
        pp.cropFrame = PixelPerfectCamera.CropFrame.Windowbox;

        // Read back rather than assume:
        //   pp.pixelRatio          int   whole-number scale actually applied
        //   pp.requiresUpscalePass bool  true exactly when gridSnapping is UpscaleRenderTexture
        //   pp.orthographicSize    float the component's computed size
        // Helpers a custom camera controller wants:
        //   pp.RoundToPixel(Vector3)              snap a world position to the grid
        //   pp.CorrectCinemachineOrthoSize(float) nearest valid size; the Cinemachine
        //                                         extension calls this for you

        return pp;
    }

    /// <summary>
    /// Project-level settings the camera cannot own. Separate on purpose: these belong to the
    /// active quality level, so applying them is a project change and needs its own consent.
    /// </summary>
    public static void ApplyQualitySettings()
    {
        // Anti-aliasing softens edges, which is what pixel art is made of. Anisotropic
        // filtering does the same to anything sampled at an angle. Both read back from the
        // active quality level, so confirm on the level a build actually selects.
        QualitySettings.antiAliasing = 0;
        QualitySettings.anisotropicFiltering = AnisotropicFiltering.Disable;
    }

    /// <summary>
    /// One line to report after configuring, so the result is a value rather than a claim.
    /// </summary>
    public static string Describe(PixelPerfectCamera pp)
    {
        return $"ppu={pp.assetsPPU} ref={pp.refResolutionX}x{pp.refResolutionY} " +
               $"snap={pp.gridSnapping} crop={pp.cropFrame} " +
               $"pixelRatio={pp.pixelRatio} upscalePass={pp.requiresUpscalePass}";
    }
}
