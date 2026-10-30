---
name: unity-render-urp
description: >-
  URP rendering: post-processing that won't show, Volume profiles and grades, Render Graph features.
---

# unity-render-urp — make it appear, then make it affordable

> **"I set the value and nothing happened" is almost never the value.** URP post-processing has
> five independent switches between a Volume and a pixel, four of them default to off or to a
> narrow default, and none of them warns. Run the pre-flight before touching a parameter.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Added bloom, tonemapping or vignette and nothing happened | §1 pre-flight, in order |
| Want the pre-flight as one paste-in call against a live Editor | [`reference/preflight-snippet.md`](reference/preflight-snippet.md) |
| Is URP actually active? A URP asset is right there, but editing it changes nothing | §1 step 1 — it may be a dormant asset |
| Works in Scene view, not in Game view | §1 — Scene view has its own post-processing toggle |
| Code compiles against `PostProcessVolume` / `GetSetting<T>` / `ColorGrading`; "ColorGrading or ColorAdjustments?" | [`reference/api-renames.md`](reference/api-renames.md) — those are the old stack |
| Need a Volume parameter's real default, type or range | [`reference/effect-reference.md`](reference/effect-reference.md) |
| A value "does not take" on an override | [`reference/api-renames.md`](reference/api-renames.md), then the parameter's range — a `Clamped*Parameter` clamps silently |
| Scripting a profile, a Global Volume or a runtime grade tween | [`reference/volume-templates.md`](reference/volume-templates.md) |
| Want a grade to start from rather than a blank profile | [`reference/volume-templates.md`](reference/volume-templates.md) — four presets |
| Effect appears, costs too much on device; which effects a mobile build can afford | §3 |
| Effect is suspected of costing too much, and no number says so | §3, then a before/after frame-time window — `unity-profiling` |
| "Review my renderer feature" — a Render Graph `ScriptableRendererFeature` | §4 |
| Turning an HLSL function into a Shader Graph node | §5 |
| A script-made material changes again after it was saved; an emissive lost its glow; every rebuild leaves a `.mat` diff | [`reference/material-validation.md`](reference/material-validation.md) |
| A see-through fence or mesh shimmers or vanishes at distance; fog missing only in the player | [`reference/material-validation.md`](reference/material-validation.md) §3–4 |
| A grade per level or venue, and bloom only on the high tier | [`reference/volume-templates.md`](reference/volume-templates.md) — per venue, per tier |
| Moving a built-in project to URP; everything went magenta; converting an old `PostProcessVolume` to a URP Volume | `unity-urp-migration` |

## 1. Pre-flight — five checks, in this order

Stop at the first failure; fix it before checking the next.

1. **URP is the active render pipeline — resolve it, do not infer it from the files.** A URP
   asset sitting in `Assets/Settings/` is not a pipeline in force; it is inert until
   `ProjectSettings/GraphicsSettings.asset` or a quality tier points at it. Read the guid out of
   `m_CustomRenderPipeline`, find the `.meta` that declares that guid, and count
   `renderPipeline: {fileID: 11400000` in `QualitySettings.asset` to see whether a tier
   overrides it:

   ```bash
   grep -m1 'm_CustomRenderPipeline:' ProjectSettings/GraphicsSettings.asset
   grep -c 'renderPipeline: {fileID: 11400000' ProjectSettings/QualitySettings.asset
   ```

   `{fileID: 0}` with zero tier overrides means **built-in renderer** and nothing below applies —
   a project created from a URP template can render on built-in this way, its URP assets
   dormant. Resolve this first: it turns "I set it and nothing happened" into a one-minute
   answer. Full resolver, the per-platform quality-tier mapping and the renderer-asset indirection:
   → `reference/resolve-active-pipeline.md`.

2. **HDR is enabled on the URP Asset.** Tonemapping requires it. Bloom still functions in SDR but
   its `threshold` must be below 1 or it has nothing to select.
3. **The camera's `renderPostProcessing` is true — it defaults to `false`.** And the renderer's
   **PostProcessData asset must not be null**: null means the post-process pass does not exist at
   all. With camera stacking, only the Base camera (or the last Overlay in the stack) should have
   it on.
4. **The Volume's GameObject layer is inside the camera's `volumeLayerMask`.** That mask defaults
   to layer 0 (`Default`) only — a Volume parked on any other layer is invisible to the camera.

> **A freshly added `UniversalAdditionalCameraData` reports** `renderPostProcessing=False`,
> `volumeLayerMask=1` (bitmask 1 = layer 0 only), `renderType=Base`, `antialiasing=None`.
> Re-check on your version in one call:
>
> ```csharp
> var d = go.AddComponent<UnityEngine.Rendering.Universal.UniversalAdditionalCameraData>();
> return d.renderPostProcessing + " " + d.volumeLayerMask.value + " " + d.renderType;
> ```
5. **The Volume is enabled, has a profile, and at least one override has
   `overrideState = true`.**

> **Forgetting `overrideState` is the number one scripting error here.** The Volume system skips
> any parameter whose `overrideState` is false, so a correctly-configured component contributes
> nothing. `profile.Add<T>(true)` turns them all on for that component.

Then: are you looking at the **Game view**? Scene view has an independent post-processing toggle,
and the camera's `renderType` must be `Base`, not `Overlay`.

All five as **one read-only `eval` block** that returns a numbered report — the fastest way to
turn "nothing happened" into a line you can act on:
→ [`reference/preflight-snippet.md`](reference/preflight-snippet.md).

## 2. The API renamed almost everything → `reference/api-renames.md`

`PostProcessVolume`, `GetSetting<T>` and `ColorGrading` are the old stack; the URP Volume names,
`TryGet<T>`, `ColorAdjustments`, and the override flag that a set value needs.

## 3. What a mobile frame can afford

Keep: `Tonemapping` (`Neutral`), a small `ColorAdjustments` exposure/contrast trim, and a
restrained `Bloom` (`threshold` 1.0, `intensity` ~0.3, `downscale = Quarter`,
`highQualityFiltering = false`, `maxIterations` reduced from the default 6).

That keep-list assumes HDR is still on (§1 step 2): Tonemapping needs it, and a `threshold` of 1.0
selects nothing in a clamped SDR buffer. A project that turns HDR off to save mobile bandwidth
drops Tonemapping and puts the Bloom threshold below 1 — otherwise both silently do nothing.

Avoid on mobile: **FilmGrain, MotionBlur, DepthOfField.** Each is full-screen and each buys
atmosphere rather than legibility.

**Read a parameter's legal range off the component, never from memory** — several are not what
they look like: `Vignette.smoothness` is **0.01–1**, so a zero reads back as 0.01;
`MotionBlur.clamp` is **0–0.2** with a 0.05 default; `Bloom.maxIterations` is **2–8** with a
default of 6, so "reduced from 6" has a floor of 2. The Volume inspector shows the range, `eval`
on the type shows it, and the full table is
→ [`reference/effect-reference.md`](reference/effect-reference.md).

A mobile grade written out as values, beside three other presets:
→ [`reference/volume-templates.md`](reference/volume-templates.md).

## 4. Reviewing a Render Graph renderer feature

→ [`reference/render-graph-review.md`](reference/render-graph-review.md) — an eight-point
checklist and a fixed output shape that keeps **confirmed defects separate from suspicions**,
plus the two corrected snippets that carry most of the checklist: a descriptor derived from
`resourceData.activeColorTexture.GetDescriptor(renderGraph)` with only the two fields that must
differ touched, and a `PassData` whose every field is assigned on every recording.

## 5. Reflected Shader Graph custom nodes

An HLSL function preceded by `UNITY_EXPORT_REFLECTION` and tagged with four `funchints` becomes a
node in the graph's search. It is metadata, not shader authoring, and **every way of getting the
metadata wrong is silent** — the file compiles and no node appears.

> **The feature needs `com.unity.shadergraph` 17.5 or newer; on 17.4 it is absent.** Check the
> installed version, and the package itself, before writing anything — both checks are the version
> gate in `reference/shader-graph-custom-node.md`. Below the floor, say so and stop.

The four required function hints, every parameter hint, where the file goes and why an existing
`ShaderInclude` needs agreement before you append to it:
→ [`reference/shader-graph-custom-node.md`](reference/shader-graph-custom-node.md). Every legal
tag combination in one compilable file:
→ [`resources/ShaderGraphHints.hlsl`](resources/ShaderGraphHints.hlsl).

## 6. Verify

Post-processing is the area where "I set it" and "it is on screen" diverge most often, and every
step of §1 fails silently.

- **Look at the Game view**, at a screenshot you actually read (`unity-debug`) — not at the
  inspector, and not at the Scene view, which has its own post-processing toggle.
- **Read the value back off the component**, not off the code you just ran. `overrideState` is
  the specific one to re-read.
- **Report before/after** in the six-line shape at the end of
  [`reference/volume-templates.md`](reference/volume-templates.md): which pipeline asset resolved
  as active, which Volume, profile and overrides, the camera's `renderPostProcessing`. "Added
  bloom" is not a result.
- On mobile, take a frame-time number before and after — the same situation, the same run mode,
  windows either side of the change (`unity-profiling`). Post-processing is full-screen work and
  the cost is not proportional to how much you can see.

## Scope — what this skill does NOT do

**Shader authoring stays out** — writing the lighting maths, hand-building a graph, debugging
what a fragment computes. The one exception is §5: **reflected Shader Graph custom nodes are in
scope**, because a reflected node is an HLSL function plus four metadata tags, and every failure
mode is a metadata failure rather than a shading one. Ask this skill to *make a function into a
node*; do not ask it what the function should compute.

**Migrating a built-in project to URP stays out** — the phased conversion of materials,
post-processing, lighting and quality tiers, and diagnosing one that was half-moved (magenta
materials, an old `PostProcessVolume` still wired up, a stale bake, `GrabPass` and
`OnRenderImage` code) is `unity-urp-migration`. This skill assumes the project already renders
with URP and asks why an effect will not appear on it.

**HDRP stays out.** It is a different pipeline with different Volume components, different
renderer plumbing and different numbers; nothing here transfers. **Lighting and GI set-up**
— light modes, the bake, probes, shadows, sky and fog — is `unity-lighting`.

Whether the pipeline in force is even URP is §1 and
[`reference/resolve-active-pipeline.md`](reference/resolve-active-pipeline.md); a project that
came from a URP template can be rendering built-in. Confirming that a change is visible on screen
is `unity-debug`. **Measuring what an effect costs stays out too** — counters, frame-time windows
and the before/after table are `unity-profiling`; §3 tells you what to suspect, that skill tells
you what it actually cost.
