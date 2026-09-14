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

   *Flag it when:* the pass carries a material it never draws with; the mask, noise or parameter
   textures are bound and the main colour input is left out; the shader is expected to hold a
   property nothing ever writes; the names used to bind and the names declared in the shader have
   drifted apart; an implicit main-texture binding stands in where the pattern wants an explicit one.

2. **Texture resource wiring.** `UseTexture(…)` declares a **read**; `SetRenderAttachment(…)`
   declares a **write**. Conflating them is the most common wiring defect. Source, destination
   and auxiliary textures must be distinguishable, and no texture may be assumed available
   without being declared.

   *Flag it when:* an input is attached as a write target, or a destination is sampled as an
   input, with no reason given; an auxiliary texture appears with no traceable source; a texture
   the render function uses is never declared on the builder; the read/write role of a handle
   cannot be decided from the code.

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

   *Flag it when:* the render function is an instance method where the API expects a static one;
   it reads a field of the feature or the pass instead of `data` and `ctx`; a `PassData` field is
   read but assigned on only some recordings; a resource handle in `PassData` can survive a frame
   because reassignment is partial.

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

   *Flag it when:* a fresh descriptor is built while a graph-derived one was available; width and
   height are hand-copied into it; `cameraTargetDescriptor` is the primary source; MSAA sample
   count, graphics format or dynamic-scale compatibility is dropped by the reconstruction. A
   deliberate divergence from the source resource is fine — it just has to be stated.

5. **Manual copy passes.** A raster pass that reads one texture and writes it unchanged should be
   a built-in helper. Prefer the appropriate `AddBlitPass(…)` overload over `AddCopyPass(…)` on
   compatibility grounds.

   *Flag it when:* the pass carries no material and no processing, and the render function does
   nothing a copy helper would not.

6. **Manual blit passes.** A plain full-screen material blit is `renderGraph.AddBlitPass(…)`.
   Write a custom raster pass only for genuinely extra logic, multiple operations, or
   conditional behaviour.

   *Flag it when:* one source, one destination, one material and no other logic — that is the
   blit helper written out by hand.

7. **Global resource exposure.** **Do not expose globally by default.** When it is genuinely
   needed, `builder.SetGlobalTextureAfterPass(…)` — **not** `context.cmd.SetGlobalTexture(…)`
   inside the pass. Global exposure extends resource lifetime, defeats aliasing and raises memory
   pressure, more so downstream of `UseGlobalTexture` / `UseAllGlobalTextures`. A global with no
   identifiable consumer is itself the finding.

   *Flag it when:* a texture is published globally and no downstream consumer can be named;
   `context.cmd.SetGlobalTexture(…)` mutates global state from inside a pass; global exposure
   stands in for pass-to-pass wiring that would have been shorter.

8. **`ConfigureInput(…)`.** Using a pipeline-provided input without declaring it is a confirmed
   issue. Declaring an input that is never used is **also** an issue — it forces extra copies and
   extra pass work — and its severity rises when that cost is measurable.

   *Flag it when:* the declared flags and the described effect disagree; an input is requested
   that nothing in the pass reads. **Which section it goes in is decided here, not by feel:**

   | The code shows | Section |
   |---|---|
   | A pipeline input is plainly read and never declared | **Confirmed** |
   | The effect as described needs an input, yet nothing on the page proves the shader samples it | **Likely**, with the assumption named |
   | An undeclared input whose cost is measurable — extra copies, an extra pass | Confirmed, and say what it costs |

## Guardrails

- **Never invent an API.** If you cannot confirm a signature, say so.
- Prefer the smallest targeted correction over a rewrite.
- Name implicit coupling and unnecessary global state explicitly; they are the defects that
  survive review and surface as an intermittent bug later.

## What the eight checks do not look at

A pass can clear all eight and still be wrong. These six are outside the checklist, so a review
that found nothing says **"nothing among the eight checks"** and lists what it did not examine —
never "the feature is correct":

- **Pass ordering and injection point** — where in the frame the pass is scheduled.
- **Resource lifetime and cleanup** — handles held across frames, and what releases them.
- **Read/write hazards** — two passes touching one resource in an order nothing pins down.
- **Camera depth and colour dependency** — whether the depth or colour the pass reads is the one
  the camera will have produced by then.
- **Multi-pass dependency chains** — a pass that only works because an earlier one ran.
- **Override-material correctness** — what the replacement material actually renders.

Each of them needs the frame, not the file: a Render Graph Viewer capture, or a frame debugger
session on the target. Ask for one rather than guessing from the source.
