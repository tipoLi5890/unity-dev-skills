# Making the artifact smaller — and the two ways stripping bites back

> Part of the `unity-android-release` skill. Read when the APK/AAB is too large, or when a build
> runs correctly in the editor and misbehaves only on device with no exception you can attribute.

## The four settings that do most of the work

Set together; they compound.

| Setting | Value | Where |
|---|---|---|
| Managed Stripping Level | **High** | Player Settings → Other |
| Strip Engine Code | **On** | Player Settings → Other |
| IL2CPP Code Generation | **Faster (smaller) builds** | Player Settings → Other |
| API Compatibility Level | **.NET Standard 2.1** | Player Settings → Other |

Setting them from script, with the enum values as they actually are — the Inspector labels and
the enum names do not match, which is where scripted settings go wrong:

| Inspector | API |
|---|---|
| Managed Stripping Level | `PlayerSettings.SetManagedStrippingLevel(NamedBuildTarget.Android, ManagedStrippingLevel.High)` — values are `Disabled, Low, Medium, High, Minimal`. **There is no "Aggressive"** |
| Strip Engine Code | `PlayerSettings.stripEngineCode` (a plain property) |
| IL2CPP Code Generation | `PlayerSettings.SetIl2CppCodeGeneration(...)` — values are only `OptimizeSpeed` and `OptimizeSize` |
| .NET Standard 2.1 | the enum member is **`ApiCompatibilityLevel.NET_Standard`**; `NET_Standard_2_0` is the older, smaller one |

**There is no bare `PlayerSettings.managedStrippingLevel` property.** The per-target
getter/setter is the only route.

Two more that cost nothing to enable and are frequently left off:

- **Read/Write Enabled off** on every texture and mesh that no script reads back. Leaving it on
  keeps a **second, CPU-side copy in memory** for the lifetime of the asset. It is the most
  common invisible memory cost in a Unity project.
- **Strip Unused Mesh Components on.**

## Shader variants are usually the largest single line

`Project Settings → Graphics`:

- Lightmap Modes: **Automatic**
- Fog Modes: **Automatic**
- Instancing Variants: **Strip Unused**
- Batch Renderer Group Variants: **Strip All** unless the project actually uses BRG
- **Audit "Always Included Shaders".** Every entry there ships every one of its variants,
  whether or not anything references it.

This shrinks the artifact *and* shortens shader compilation and load time, so it is worth doing
even when size is not the complaint.

## Stripping bites back in two specific ways

Both produce the same useless report — "works in the editor, wrong on device" — and neither
throws where the mistake is.

> **1. IL2CPP strips types nothing appears to reference.** A `MonoBehaviour` only ever
> instantiated by the engine, a class resolved by reflection, a type only named in JSON — the
> static analysis cannot see the reference, so the code is not there at runtime. Annotate with
> `[Preserve]`, or list the assembly in `link.xml`. Raise stripping to High *after* the
> annotations exist, not before.

> **2. Layer and tag lookups by string are a runtime miss, not a compile error.**
> `LayerMask.NameToLayer("Player")` returns `-1` if the layer is not in the build's tag manager,
> and `-1` used as a layer index silently matches nothing. Production code should use the
> resolved index, captured once and asserted on at startup.

Both are worth a startup assertion rather than a comment: a build that is missing a preserved
type should refuse to start with a clear message, not run wrong.

## Prove it, do not assume it

Stripping settings are exactly the kind of change that reads as applied and is not — see
`device-triage.md` on proving which settings asset is actually in effect. After a size pass:

```bash
ls -l <artifact>                       # the number that matters
unzip -l <artifact> | sort -k1 -n -r | head -20    # what is actually big inside it
```

The size Unity prints is **not** that number — `BuildReport.summary.totalSize` counts symbols and
intermediates (`artifact-verification.md`). A before/after pair taken from the build report is
therefore not evidence of anything; take both from the file.

Compare against the previous artifact's recorded size in the build history. A "size optimisation"
with no before/after pair is an assertion, not a result.
