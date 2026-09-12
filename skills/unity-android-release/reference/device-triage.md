# When it works in the editor and not on the device

The editor is a different GPU, a different graphics API, a different quality level and a different
scripting backend. A fault that only appears on the device is not mysterious — it is one of those
four, and each has a way of being narrowed down without guessing.

## Narrow it with what is NOT broken

The single most useful observation is which parts of the frame survived.

Example: the 3D scene renders as a dozen bands of flat colour while **the IMGUI HUD is
pixel-perfect** — sharp type, correct panel colours, correct borders. That one contrast localises
the fault immediately:

> IMGUI draws **after** post-processing, straight to the final target. The 3D scene renders to an
> intermediate and passes through the post-process chain. So "UI clean, scene wrecked" means the
> fault is in the **intermediate target or the post-process chain**, and nowhere else.

Generalise it: list what renders correctly, and keep only the pipeline stages that the broken thing
passes through and the intact thing does not.

| What survives | What that rules in |
|---|---|
| UI fine, 3D banded/wrong colour | Intermediate target format, colour grading LUT, tonemapping |
| Everything magenta | Shader missing from the build — variant stripping, or a runtime `Shader.Find` |
| Everything black but audio plays | Camera/culling, or a failed render target allocation |
| Geometry right, textures wrong | Compression format unsupported for the ABI/API |
| Instant crash on launch | Native plugin ABI (see the main skill), or managed stripping |

## Before changing a setting, prove that setting is the one in effect

A setting changed on the wrong asset costs whole round trips of "build, install, still broken" —
e.g. HDR turned off in `Assets/Settings/Mobile_RPAsset.asset` while the pipeline actually runs on
`Assets/New Universal Render Pipeline Asset.asset`, with different HDR, MSAA and renderer. The
dormant-decoy pattern — `PC_RPAsset.asset`, Android's quality level 0 named "Mobile", and the
`renderPipeline: none` fall-through to `GraphicsSettings.m_CustomRenderPipeline` — is in
`unity-debug` → `reference/harness-trust.md`. So: **follow the reference chain from the thing that
actually runs, and print what you find.**

```bash
# 1. Which pipeline asset does the project actually use?
grep -n "m_CustomRenderPipeline" ProjectSettings/GraphicsSettings.asset      # guid -> the real one

# 2. Do the quality levels override it?  `renderPipeline: none` means they do NOT.
grep -nE "name:|renderPipeline:" ProjectSettings/QualitySettings.asset
grep -n "m_PerPlatformDefaultQuality" -A6 ProjectSettings/QualitySettings.asset

# 3. Resolve a guid to a file
find . -name "*.meta" -not -path "./Library/*" -exec grep -l "^guid: <GUID>" {} \;

# 4. Now read the settings off the asset you PROVED is live
grep -nE "m_SupportsHDR|m_MSAA|m_RenderScale|m_RendererDataList" "<the real asset>"
```

The same trap exists for renderers, volume profiles, input settings and quality tiers. A file with
the right name is not evidence; a reference chain is.

## Volume profiles apply from two places, and one ignores layers

Post-processing arrives from **two** independent sources:

- the **scene's** volumes, filtered by the camera's `m_VolumeLayerMask`;
- the pipeline's **global default profile**
  (`UniversalRenderPipelineGlobalSettings.m_DefaultVolumeProfile`), which applies to **every**
  camera **regardless of layer**.

A camera mask of layer 0 with the scene's Global Volume on layer 3 means the scene's
carefully-tuned Bloom/Vignette/Tonemapping has **never once applied** — and nobody notices,
because it is invisible either way. Meanwhile the global default profile can carry active
components nobody chose: a template can leave Unity's own internal test components in it
(`CopyPasteTestComponent1/2/3`, `TestVolume`, `TestAnimationCurveVolumeComponent`) beside colour
grading, which URP bakes into a single 32³ LUT.

That LUT is the prime suspect for device-only colour quantisation: neutral grading still means the
image passes through a lookup table, and if that table is sampled without interpolation on a given
driver, every smooth gradient collapses into 32 steps — exactly the banding in the example above.

```bash
# What does the global default profile actually contain and override?
grep -n "m_DefaultVolumeProfile" -A2 Assets/Settings/UniversalRenderPipelineGlobalSettings.asset
# Per component: is it active, and how many values does it override?
grep -n "m_VolumeLayerMask" -A3 <the camera's prefab or the scene>
```

If nothing in the project wants post-processing, turn it off at the camera
(`m_RenderPostProcessing: 0`). It removes the LUT, the extra full-screen pass and the intermediate
target in one move, and on a flat-shaded mobile game it costs nothing — **verify that claim by
screenshotting the flow with it on and off and diffing, rather than asserting it.**

## Graphics API is often pinned, not automatic

```bash
grep -n "m_BuildTargetGraphicsAPIs" -A6 ProjectSettings/ProjectSettings.asset
```

`m_Automatic: 0` means someone chose. The `m_APIs` blob is little-endian 4-byte enum values —
`15000000` = 21 = Vulkan, `0b000000` = 11 = OpenGLES3. Vulkan plus native render passes plus MSAA
plus a floating-point intermediate is a stack of mobile-fragile features; dropping to GLES3 is a
legitimate bisection step, not a defeat.

## Then read the device's log

There is no Editor.log on a phone.

```bash
adb logcat -c && adb logcat -s Unity AndroidRuntime DEBUG
```

An `adb devices` entry marked `offline` is a stale wireless pairing, not a connected phone —
`adb disconnect && adb connect <ip>`, or plug in a cable.

## Bisect one variable at a time

Each round trip costs a build plus an install plus someone playing it. Make each one answer a
question: change **one** thing, and say out loud what each possible outcome would prove. Better
still, reproduce it in the editor first — switching the editor's quality level, graphics API or
colour space is seconds, and a fault you can reproduce there costs nothing per attempt.
