# Custom shaders and camera effects the converter will not touch

> Part of the `unity-urp-migration` skill. The converter reads material assignments, not shader
> source. Everything here is work it walks straight past, leaving materials that either render
> magenta or render something that is not what the shader meant.

## Ground truth

- **The converter does not upgrade custom shaders.** Not partially, not with warnings.
- **URP has no `GrabPass`.** Scene colour comes from the opaque texture — a URP asset setting,
  off by default.
- **URP has no surface shaders.** `#pragma surface` has no equivalent to translate to.
- **`OnRenderImage` is not called.** Full-screen effects become a renderer feature and a pass.
- Hand-written shaders do work in URP, but Shader Graph is often cheaper where the visual intent
  is simple: it keeps compiling across versions without anyone maintaining includes.

## Grading before porting

| Risk | Shape |
|---|---|
| Low | Unlit, single pass, one or two materials, narrow obvious intent |
| Medium | Several exposed properties, hand-written lit shaders leaning on built-in lighting helpers, wide prefab use, anything batching-sensitive |
| High | Surface shaders · `GrabPass` · multi-pass · package-owned · water, foliage, toon and outline frameworks · custom lighting models · replacement shaders · XR paths · vegetation with wind or billboards |

Grade the whole set before porting any of it. The easiest shader first feels like progress and
says nothing about the two that will take the week.

## Case: surface shaders

**Indicator** `#pragma surface`, built-in lighting helper includes.
**Implication** There is no direct translation; this is a rewrite.
**First step** Pick one representative shader — the most typical, not the easiest — and rebuild
it in Shader Graph, or as a URP HLSL vertex/fragment shader where the lighting does something a
graph cannot express. Never a syntax patch.
**Validation** That one material, in the Game view, against a before capture.

## Case: `GrabPass`, refraction and distortion

**Indicator** `GrabPass`, any shader that expects to read the already-rendered frame.
**Implication** The mechanism does not exist; the replacement is the opaque texture.
**First step** Turn **Opaque Texture** on in the URP asset, then rewrite the sampling:

```hlsl
#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareOpaqueTexture.hlsl"

float2 screenUV  = input.positionCS.xy / _ScaledScreenParams.xy;
half3  sceneColor = SampleSceneColor(screenUV);
```

**Validation** In scene, not by compiling. Sorting order and the moment of capture both differ
from the old behaviour, so an effect that compiles can still sample the wrong frame content —
transparent objects behind the effect show it first.

## Case: `OnRenderImage`

**Indicator** `OnRenderImage(RenderTexture, RenderTexture)`, blit-style camera scripts.
**Implication** The callback is never invoked; the effect becomes a `ScriptableRendererFeature`
plus a pass.
**First step** The skeleton below. **Blit through a temporary target and back — never
source-to-source.** Reading and writing one texture in a single blit is undefined, and the
artefacts look like a shader bug.

```csharp
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

// Compatibility Mode shape: Execute / OnCameraSetup. On a project already on Render Graph the
// entry points are RecordRenderGraph and AddBlitPass instead — see the fork note below.
public sealed class LaneOverlayFeature : ScriptableRendererFeature
{
    sealed class LaneOverlayPass : ScriptableRenderPass
    {
        readonly ProfilingSampler _sampler = new ProfilingSampler("LaneOverlay");
        readonly Material _overlay;
        RTHandle _scratch;

        public LaneOverlayPass(Material overlay)
        {
            _overlay = overlay;
            renderPassEvent = RenderPassEvent.AfterRenderingPostProcessing;
        }

        public override void OnCameraSetup(CommandBuffer cmd, ref RenderingData data)
        {
            var descriptor = data.cameraData.cameraTargetDescriptor;
            descriptor.depthBufferBits = 0;
            RenderingUtils.ReAllocateIfNeeded(ref _scratch, descriptor, name: "_LaneOverlayScratch");
        }

        public override void Execute(ScriptableRenderContext context, ref RenderingData data)
        {
            if (_overlay == null) return;

            var cmd = CommandBufferPool.Get();
            using (new ProfilingScope(cmd, _sampler))
            {
                var camera = data.cameraData.renderer.cameraColorTargetHandle;
                Blitter.BlitCameraTexture(cmd, camera, _scratch, _overlay, 0);  // there
                Blitter.BlitCameraTexture(cmd, _scratch, camera);               // and back
            }
            context.ExecuteCommandBuffer(cmd);
            CommandBufferPool.Release(cmd);
        }

        public void ReleaseTargets() => _scratch?.Release();
    }

    [SerializeField] Material _overlayMaterial;
    LaneOverlayPass _pass;

    public override void Create() => _pass = new LaneOverlayPass(_overlayMaterial);

    public override void AddRenderPasses(ScriptableRenderer renderer, ref RenderingData data)
    {
        if (_overlayMaterial != null) renderer.EnqueuePass(_pass);
    }

    protected override void Dispose(bool disposing) => _pass?.ReleaseTargets();
}
```

Two checks before this compiles on the target project:

- **Which mode is the project in?** Graphics settings carries a Render Graph / Compatibility Mode
  switch; the file above is the Compatibility shape. On Render Graph the pass records into
  `RecordRenderGraph` and blits with `AddBlitPass` — checklist in `unity-render-urp` →
  `reference/render-graph-review.md`.
- **Which allocator name resolves?** `RenderingUtils.ReAllocateIfNeeded` and
  `ReAllocateHandleIfNeeded` are one idea under two names across URP lines. Confirm on your
  version; the wrong one is a compile error rather than a silent failure, which is the good case.

**Validation** In the Game view. Scene view has its own post-processing toggle and can show a
different answer.

## Case: replacement shaders

**Indicator** `SetReplacementShader`, `RenderWithShader`, camera-based outline or mask passes.
**Implication** These lean on built-in pass tags that URP does not drive the same way.
**First step** Ask what the replacement pass was *for* — outlines, masks, depth, normals. URP
often exposes it already: the depth and depth-normals textures are settings, not code. Only when
none fit does this become a custom pass.
**Validation** What the pass produced, isolated — one object's outline, not the whole screen.

## Case: multi-pass, custom lighting, deferred assumptions

**Indicator** Many passes in one shader; forward-add or deferred-specific code; lighting tightly
bound to built-in includes.
**Implication** Not an include swap. Decide which passes URP still needs.
**First step** Say out loud whether the shader can be forward-only; if it can, the port shrinks
by most of its size. If deferred is required, get the URP pass tags right before any shading
maths moves.
**Validation** Expect several rounds. One round means something was not checked.

## Case: package-owned and framework shaders

**Indicator** Shaders under `Packages/` or `Library/PackageCache/`; water, foliage, toon,
outline or dissolve frameworks; generated shader code.
**Implication** Not safe to rewrite, and edits there are wiped by the next resolve.
**First step** Check whether the package already ships a URP variant — most maintained ones do,
behind a version bump or a define. Otherwise copy the specific material locally and scope the
port to the materials actually needed.
**Validation** Named materials, named scenes. Never "the package works now".

## Case: foliage

**Indicator** Grass, tree, leaf, billboard, terrain-detail or SpeedTree names; `_Cutoff` and
other alpha-test properties; wind, bend or hue-variation keywords.
**Implication** A foliage material can be on a URP shader, not magenta, and completely wrong:
dropped alpha clipping turns cards into solid rectangles, lost wind turns a moving canopy still.
**First step** Split bark and other opaque meshes — plain URP Lit handles those — from cards,
billboards and terrain detail, which it does not.
**Validation** Look at it: grass that is not visible quads, leaves rendering from both sides,
cutout thresholds unchanged. Lost wind or billboard behaviour is a named partial.

## Never

- Never claim the converter handles custom shaders.
- Never bulk search-and-replace shader source across a project.
- Never promise parity from a shader that compiles.
- Never keep editing a shader while the console is filling with new errors — that is divergence,
  and the next edit costs more than the last.
- Never rewrite a package-owned shader in place.

## Stop and escalate when

Several high-risk categories overlap · the effect depends on undocumented package internals ·
the shader compiles and the difference is plainly not a parameter · the project's look rests on
replacement-shader or full-screen custom rendering · production parity is expected and the
porting strategy is still being discovered.

Stopping with a named blocker is a result. Continuing without one is how a migration becomes a
rewrite nobody scoped.
