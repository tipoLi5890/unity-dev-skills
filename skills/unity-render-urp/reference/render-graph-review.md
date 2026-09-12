# Reviewing a Render Graph ScriptableRendererFeature

> Part of the `unity-render-urp` skill. Render Graph is still moving between URP versions —
> confirm a signature against the installed package before flagging its absence as a defect.

## Inputs to collect before reviewing

Unity version, URP version, the feature and pass source, the intended behaviour, the expected
inputs and outputs, and any project constraint (mobile, XR, camera stacking). **A review that
guesses at the intended behaviour finds defects that are not defects.** If a required input is
missing, list it under *Missing information* rather than inventing it.

## Output shape

Six sections, in this order. The third one is what makes the review usable:

1. **Validation summary** — one paragraph.
2. **Confirmed issues** — provable from the code as given.
3. **Likely issues, and the assumption each rests on** — kept separate, never merged upward.
4. **Recommended fixes** — minimal and targeted, not a rewrite.
5. **Corrected snippets.**
6. **Missing information.**

Every issue says *why it matters*. "Does not follow best practice" is not a finding.

## The eight checks

1. **Material binding.** Is the declared material actually used? Is the **primary input texture
   explicitly bound**? The common defect is binding the auxiliary textures — a mask, a noise map
   — and leaving the main colour input unbound, which renders something plausible and wrong.
   Shader property names must match; null material must be handled.

2. **Texture resource wiring.** `UseTexture(…)` declares a **read**; `SetRenderAttachment(…)`
   declares a **write**. Conflating them is the most common wiring defect. Source, destination
   and auxiliary textures must be distinguishable, and no texture may be assumed available
   without being declared.

3. **Execution structure.** The render function must be `static`, and **every field of
   `PassData` must be assigned on every `RecordRenderGraph` call.** `PassData` is pooled: a field
   left unassigned holds the previous frame's value, which is a stale or dangling resource
   handle. It will usually work, and then intermittently not. Never reach for instance state
   from inside the render function.

   The corrected shape is boring on purpose — one assignment per field, in the recording block,
   with nothing conditional:

   ```csharp
   class PassData
   {
       public TextureHandle source;
       public TextureHandle target;
       public Material material;
       public float intensity;
   }

   public override void RecordRenderGraph(RenderGraph renderGraph, ContextContainer frameData)
   {
       using var builder = renderGraph.AddRasterRenderPass<PassData>(k_PassName, out var passData);

       var resourceData = frameData.Get<UniversalResourceData>();

       // Every field, every recording. An `if` around one of these is the defect: on the frame
       // the branch is not taken the field keeps whatever the pooled instance last held.
       passData.source    = resourceData.activeColorTexture;
       passData.target    = renderGraph.CreateTexture(NewTargetDesc(renderGraph, resourceData));
       passData.material  = m_Material;                 // may be null — the render function checks
       passData.intensity = m_Settings.intensity;       // no default, no carry-over

       builder.UseTexture(passData.source);             // read
       builder.SetRenderAttachment(passData.target, 0); // write
       builder.SetRenderFunc((PassData data, RasterGraphContext ctx) => Execute(data, ctx));
   }

   // static, and it reads nothing but `data` and `ctx`
   static void Execute(PassData data, RasterGraphContext ctx)
   {
       if (data.material == null) { return; }
       data.material.SetFloat(k_IntensityId, data.intensity);
       Blitter.BlitTexture(ctx.cmd, data.source, new Vector4(1, 1, 0, 0), data.material, 0);
   }
   ```

   The review question for each field is not "is it assigned somewhere" but **"is it assigned on
   every path through `RecordRenderGraph`"**. A field set inside a conditional, or only when a
   settings flag is on, is the same defect as one never set — it just fails less often.

4. **Descriptors.** **Do not default to `new TextureDesc`.** Get the descriptor from the graph
   (`resourceData.activeColorTexture.GetDescriptor(renderGraph)`) and change only what must
   change. Hand-copying width and height — or reaching for `cameraTargetDescriptor` — silently
   discards MSAA sample count and graphics format, and the result is a target that is no longer
   compatible with the active one.

   The corrected shape, and note the type: **`GetDescriptor` returns `TextureDesc`, not
   `RenderTextureDescriptor`** — a review written against the older struct flags the wrong
   things. Two assignments, nothing else touched:

   ```csharp
   var resourceData = frameData.Get<UniversalResourceData>();
   var desc = resourceData.activeColorTexture.GetDescriptor(renderGraph);
   desc.depthBufferBits = DepthBits.None;    // no depth on an intermediate colour target
   desc.name = "_MyFeatureTarget";           // so it is identifiable in the Render Graph Viewer
   // format, msaaSamples, width, height, useDynamicScale and the rest carry over untouched
   passData.target = renderGraph.CreateTexture(desc);
   ```

   `depthBufferBits` is a **property of type `DepthBits`** on `TextureDesc`, not an int field
   (`DepthBits` enumerates `None, Depth8, Depth16, Depth24, Depth32`). A literal `0`
   compiles because C# converts it, so `= 0` is not a defect — but `DepthBits.None` is what the
   field means, and a review should say so rather than flag it.

5. **Manual copy passes.** A raster pass that reads one texture and writes it unchanged should be
   a built-in helper. Prefer the appropriate `AddBlitPass(…)` overload over `AddCopyPass(…)` on
   compatibility grounds.

6. **Manual blit passes.** A plain full-screen material blit is `renderGraph.AddBlitPass(…)`.
   Write a custom raster pass only for genuinely extra logic, multiple operations, or
   conditional behaviour.

7. **Global resource exposure.** **Do not expose globally by default.** When it is genuinely
   needed, `builder.SetGlobalTextureAfterPass(…)` — **not** `context.cmd.SetGlobalTexture(…)`
   inside the pass. Global exposure extends resource lifetime, defeats aliasing and raises memory
   pressure, more so downstream of `UseGlobalTexture` / `UseAllGlobalTextures`. A global with no
   identifiable consumer is itself the finding.

8. **`ConfigureInput(…)`.** Using a pipeline-provided input without declaring it is a confirmed
   issue. Declaring an input that is never used is **also** an issue — it forces extra copies and
   extra pass work — and its severity rises when that cost is measurable.

## Guardrails

- **Never invent an API.** If you cannot confirm a signature, say so.
- Prefer the smallest targeted correction over a rewrite.
- Name implicit coupling and unnecessary global state explicitly; they are the defects that
  survive review and surface as an intermittent bug later.
