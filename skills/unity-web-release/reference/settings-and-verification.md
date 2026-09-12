# Applying the web settings, proving they landed, and profiling what shipped

> **A value you just assigned reads back correctly whether or not it was ever written.** Player
> Settings are objects in memory until something saves them. Every "applied successfully" report
> that skipped the save was accurate about the object and wrong about the project.

Connecting to a live Editor: `unity-debug` → `reference/editor-control.md`. `eval` compiles a
statement block, not a file — no `using` directives, and qualify anything ambiguous.

## Read the whole picture in one call

Seventeen values, one round trip, before touching anything:

```csharp
var target = UnityEditor.Build.NamedBuildTarget.WebGL;
var w = new System.Collections.Generic.List<string>();
w.Add($"activeBuildTarget={UnityEditor.EditorUserBuildSettings.activeBuildTarget}");
w.Add($"compressionFormat={UnityEditor.PlayerSettings.WebGL.compressionFormat}");
w.Add($"decompressionFallback={UnityEditor.PlayerSettings.WebGL.decompressionFallback}");
w.Add($"stripEngineCode={UnityEditor.PlayerSettings.stripEngineCode}");
w.Add($"stripUnusedMeshComponents={UnityEditor.PlayerSettings.stripUnusedMeshComponents}");
w.Add($"managedStrippingLevel={UnityEditor.PlayerSettings.GetManagedStrippingLevel(target)}");
w.Add($"il2cppCodeGeneration={UnityEditor.PlayerSettings.GetIl2CppCodeGeneration(target)}");
w.Add($"apiCompatibilityLevel={UnityEditor.PlayerSettings.GetApiCompatibilityLevel(target)}");
w.Add($"exceptionSupport={UnityEditor.PlayerSettings.WebGL.exceptionSupport}");
w.Add($"debugSymbolMode={UnityEditor.PlayerSettings.WebGL.debugSymbolMode}");
w.Add($"dataCaching={UnityEditor.PlayerSettings.WebGL.dataCaching}");
w.Add($"wasm2023={UnityEditor.PlayerSettings.WebGL.wasm2023}");
w.Add($"initialMemorySize={UnityEditor.PlayerSettings.WebGL.initialMemorySize}");
w.Add($"maximumMemorySize={UnityEditor.PlayerSettings.WebGL.maximumMemorySize}");
w.Add($"memoryGrowthMode={UnityEditor.PlayerSettings.WebGL.memoryGrowthMode}");
w.Add($"targetFrameRate={UnityEngine.Application.targetFrameRate}");
w.Add($"vSyncCount={UnityEngine.QualitySettings.vSyncCount}");
return string.Join("\n", w);
```

`UnityEditor.WebGL.UserBuildSettings.codeOptimization` is deliberately **not** in that list. Keep it
in a call of its own, so that a project without the Web build-support module fails on one line
instead of losing the other seventeen to a type-resolution error.

That block compiles and runs as written against a live Editor. The `PlayerSettings.WebGL.*` rows
below read their factory value on a project that has never targeted the web — nothing has touched
them. The per-target rows hold whatever the project's WebGL target carries, and the last two rows
are global project state; read those rather than assume them.

| Value read | Factory value | Release wants |
|---|---|---|
| `compressionFormat` | `Brotli` | Brotli — already right |
| `decompressionFallback` | `False` | Off — already right |
| `dataCaching` | `True` | On — already right |
| `debugSymbolMode` | `Off` | Off — already right |
| `memoryGrowthMode` | `Geometric` | Geometric — already right |
| `maximumMemorySize` | `2048` | 2048 — already right |
| `initialMemorySize` | `32` | tuned to real peak |
| `wasm2023` | `False` | On, if the browser baseline allows |
| `exceptionSupport` | `ExplicitlyThrownExceptionsOnly` | `None` |
| `managedStrippingLevel` (WebGL) | per target — read it | `High` |
| `il2cppCodeGeneration` (WebGL) | per target — read it | `OptimizeSize` |
| `apiCompatibilityLevel` (WebGL) | per target — read it | `NET_Standard` — in the batch; see below |
| `stripEngineCode` † | project state — read it | `True` |
| `stripUnusedMeshComponents` † | project state — read it | `True` |

† Both are bare static properties on `PlayerSettings` with no build-target argument — declared
static, with no `Get…`/`Set…` pair. So they hold the project's global state, not a factory value,
and a write to either lands on every platform it ships. Read them, do not assume them.

> **The enum member for ".NET Standard 2.1" is `ApiCompatibilityLevel.NET_Standard`, with no
> version in the name.** `NET_Standard_2_0`, which is what the name-matching instinct reaches for,
> is the older 2.0 profile. The full member list is `NET_2_0`, `NET_2_0_Subset`, `NET_4_6`,
> `NET_Unity_4_8`, `NET_Web`, `NET_Micro`, `NET_Standard_2_0`, `NET_Standard`.

Reading `ProjectSettings/ProjectSettings.asset` directly gets you a rough picture in a pinch; do not
write it that way. The serialised names are not the API names, several of these values exist once
per build target, and a hand-edited file disagrees silently with the Editor that is about to build.

## The property surface, enumerated rather than recalled

`PlayerSettings.WebGL` carries 31 public properties (enumerate the nested type by reflection to
re-check on your version; the Inspector labels in `SKILL.md` §2 map onto these):

`analyzeBuildSize`, `closeOnQuit`, `compressionFormat`, `dataCaching`, `debugSymbolMode`,
`debugSymbols`, `decompressionFallback`, `emscriptenArgs`, `enableSubmoduleStrippingCompatibility`,
`exceptionSupport`, `geometricMemoryGrowthStep`, `initialMemorySize`, `linearMemoryGrowthStep`,
`linkerTarget`, `maximumMemorySize`, `memoryGeometricGrowthCap`, `memoryGrowthMode`, `memorySize`,
`modulesDirectory`, `nameFilesAsHashes`, `powerPreference`, `showDiagnostics`, `template`,
`threadsSupport`, `useEmbeddedResources`, `useWasm`, `wasm2023`, `wasmArithmeticExceptions`,
`wasmStreaming`, `webAssemblyBigInt`, `webAssemblyTable`. The legacy `memorySize` sits alongside
`initialMemorySize`/`maximumMemorySize` — set the latter two.

**Three of those are deprecated and one of the three stops the build.** Read off the `[Obsolete]`
attributes on the type:

| Property | Obsolete as | Replacement, in Unity's own words |
|---|---|---|
| `wasmStreaming` | **error** | Streaming is chosen for you: it is used when `decompressionFallback` is off, and not used when it is on |
| `debugSymbols` | warning | `debugSymbolMode` |
| `useWasm` | warning | `linkerTarget` |

> **`wasmStreaming` is obsolete-as-error, not obsolete-as-warning.** A reference to it does not
> compile — and Editor scripts compile as one assembly, so it takes every other Editor script down
> with it and aborts any `-executeMethod` in the project with a compile-error message that names
> nothing about the web. `AudioImporter.preloadAudioData` has the same shape (`unity-audio`).
> If a headless command starts failing right after someone touched web settings, read the compile
> errors, not the method that was invoked.

The enum values, so nobody guesses a member name:

| Enum | Members |
|---|---|
| `Il2CppCodeGeneration` | `OptimizeSpeed`, `OptimizeSize` |
| `ManagedStrippingLevel` | `Disabled`, `Low`, `Medium`, `High`, `Minimal` |
| `WebGLCompressionFormat` | `Brotli`, `Gzip`, `Disabled` |
| `WebGLExceptionSupport` | `None`, `ExplicitlyThrownExceptionsOnly`, `FullWithoutStacktrace`, `FullWithStacktrace` |
| `WebGLDebugSymbolMode` | `Off`, `External`, `Embedded` |
| `WebGLMemoryGrowthMode` | `None`, `Linear`, `Geometric` |

`ManagedStrippingLevel.Minimal` exists and `Aggressive` does not — the same list as on Android
(`unity-android-release`), and the same place people reach for a member that was never there.

## Applying is a batch, and a batch is a file

[`../templates/WebOptimizer.cs`](../templates/WebOptimizer.cs) applies the ten release settings,
saves, and logs every value back. It is a **project file, not `eval` input**: a class declaration
cannot live inside a statement block, so keep its `using` directives — they are correct in a file —
drop it under `Assets/Scripts/Editor/`, let Unity compile, then fire it in one line:

```csharp
UnityEditor.EditorApplication.ExecuteMenuItem("Tools/Unity Dev/Apply Web Release Settings");
```

Single knobs — one quality level, a frame-rate flip — stay inline. It is the ten-at-once case that
earns a file, because that set is the thing a reviewer needs to see in a diff.

`initialMemorySize` is deliberately absent from the batch: every other value in it is a fixed
choice, and that one is a number from a measured peak. Set it in its own call once you have the
peak, and say which number you used.

The template needs the Web build-support module for its last setting: `UnityEditor.WebGL` resolves
only when the module is installed. **The module test: without the module,
`UnityEditor.WebGL.UserBuildSettings` is absent from every loaded assembly** — scanning
`AppDomain.CurrentDomain.GetAssemblies()` finds it nowhere, and `Type.GetType` on it returns
`null`. That absence is also why the template's header says to delete the `codeOptimization`
assignment and its read-back line rather than fight the resulting CS0234.
`GetManagedStrippingLevel`, `SetManagedStrippingLevel` and `GetIl2CppCodeGeneration` are methods
on `PlayerSettings`, and the bare `PlayerSettings.managedStrippingLevel` property does not exist.
`PlayerSettings.WebGL` itself is present with or without the module, so its presence is not the
module test; `UserBuildSettings` is.

## The trap this file exists for

Assign, read back, report, done — and nothing reached disk.

1. **Save.** `UnityEditor.AssetDatabase.SaveAssets()`. The template does it; an inline `eval` write
   has to do it by hand.
2. **Report the values, not the verb.** Print what is stored, so the reader can see it, rather than
   the word "applied".
3. **Name the target you read.** Stripping level and IL2CPP code generation exist once per build
   target. A value that is right for Android and unset for WebGL looks identical to a value that
   took, unless the report says which target it came from.

> **A green batch-mode run is not evidence that the save is unnecessary.** A batch Editor launched
> with `-quit` writes settings out on exit, so a script that never calls `SaveAssets` persists
> anyway and passes. Saving and non-saving versions both go green there. The defect only shows in a
> live session, which is why this skill drives a live Editor.

The file-editing route has the mirror-image failure: a hand-edited `ProjectSettings.asset` reads
back exactly as edited while the running Editor and the build it produces keep using the old value.
Saving, then re-reading through the API, is the one check that catches both directions.

## `codeOptimization` does not travel

It is the only setting in this skill that is not stored in the project. It persists to
`Library/EditorUserBuildSettings.asset`, and every standard Unity `.gitignore` excludes `Library/`.
Two consequences worth writing on the release checklist:

- **Do not grep `ProjectSettings.asset` for it.** It is absent there even after a completely
  successful apply, so its absence proves nothing. The API read-back is the only confirmation.
- **It is per-machine.** A teammate's clone and a fresh CI runner both start without it. If the
  release build runs in CI, applying it has to be a step in the pipeline, not an assumption about
  what the repository carries.

## Profiling in the browser

The Editor's Play Mode is not a browser and never was. Measure in the browser — in at least two of
them, because GC and JIT behaviour differ between Chromium and Safari.

| Tool | What it is for | Note |
|---|---|---|
| Chrome DevTools → Performance | Main-thread flamegraph | First stop for a hitch; shows Wasm frames |
| Chrome DevTools → Memory | Heap snapshots, allocation timeline | Snapshot before and after a scene load, then diff |
| Firefox Profiler | Native plus Wasm view, shareable profile links | Often symbolicates Wasm better; the link is how you hand a profile to someone else |
| Safari Web Inspector | The only way into iOS and macOS Safari | Safari's WebGL and Wasm runtimes are not Chromium's |
| Unity Profiler over WebSocket | Unity-side markers — GC, rendering, scripts | Development build only; it sees nothing of the browser's own overhead |

| Symptom | Start here | Then |
|---|---|---|
| Hitch or stutter | Chrome DevTools → Performance | Firefox Profiler |
| Memory climbing over minutes | Chrome DevTools → Memory | Unity Memory Profiler over WebSocket |
| Slow first load | Chrome DevTools → Network | The build report |
| Rendering wrong in Safari only | Safari Web Inspector | Diff against Chrome |

**Readable names in the flamegraph.** Wasm functions are mangled by default, so a profile of a
release build names nothing. Either turn on Debug Symbols for a development build, or emit profiling
symbols from a build processor:

```csharp
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;

public class WebProfilingSymbols : IPreprocessBuildWithReport
{
    public int callbackOrder => 0;

    public void OnPreprocessBuild(BuildReport report)
    {
        PlayerSettings.SetAdditionalIl2CppArgs("--compiler-flags=--profiling-funcs");
    }
}
```

`PlayerSettings.SetAdditionalIl2CppArgs` exists with a single overload, so the processor compiles.
Confirm on one development build that the flag reaches emscripten and the flamegraph shows named
frames before relying on it.

**Emscripten's own overlays** go through `PlayerSettings.WebGL.emscriptenArgs` (in the property
list above). Enable exactly one at a time; they instrument the build and each one
distorts what the others would have measured.

| Argument | Overlay |
|---|---|
| `--cpuprofiler` | CPU timeline drawn over the canvas |
| `--memoryprofiler` | Heap map — allocated-but-unused, stack, dynamic, fragmented, by colour |
| `--threadprofiler` | Per-thread activity |

**GPU work has no Frame Debugger on the web.** Capture draw calls and WebGL state with
[Spector.js](https://spector.babylonjs.com/) in the browser instead.

**Firefox `about:memory`** is the fastest read on where the bytes went: open it as a URL, press
Measure, and read the per-tab breakdown — Wasm code, Wasm heap, the `.data` file, web audio. **A
Wasm heap over ~300 MB is the crash-risk line**, first on older iOS Safari. Web audio over ~100 MB
almost always means clips are shipping uncompressed (`unity-audio`).

## Serving a build locally

Loading `index.html` off the filesystem does not work; the build needs an HTTP origin and correct
MIME types.

```bash
python3 -m http.server 55553 -d path/to/build     # nothing to install
npx serve path/to/build -l 3001                   # Node, if it is already there
```

Neither of these speaks Brotli. The browser only accepts `Content-Encoding: br` in a secure context,
so testing a Brotli build locally means HTTPS — a self-signed certificate is enough — or a host that
sets the header. Testing Brotli over plain `http://` and concluding the build is broken is the
common wasted afternoon here.

## KTX2 encoding with `toktx`

The web is the platform that needs this most: the target GPU is unknown until the page loads, so a
format chosen at build time is either wrong somewhere or shipped several times over. What KTX2 /
Basis is, which textures it applies to and which gain nothing from it: `unity-3d-models` (SKILL, the
KTX2/Basis paragraph). What follows is only the encoder side.

`com.unity.cloud.ktx` and `com.unity.web.stripping-tool` are both Unity registry package ids; read
the version that resolved off `Packages/packages-lock.json`.

Encode offline, never at runtime:

```bash
# Albedo and diffuse — ETC1S, lossy, the smallest option
toktx --bcmp --genmipmap --lower_left_maps_to_s0t0 out.ktx2 albedo.png

# Normals, masks, UI — UASTC, near-lossless
toktx --encode uastc --uastc_quality 2 --t2 --genmipmap --lower_left_maps_to_s0t0 out.ktx2 normal.png

# Colour data whose source has no ICC profile: state the transfer function
toktx --bcmp --assign_oetf srgb --lower_left_maps_to_s0t0 out.ktx2 albedo.png

# Data textures — normals, masks, packed channels — must not be treated as sRGB
toktx --bcmp --assign_oetf linear --lower_left_maps_to_s0t0 out.ktx2 mask.png
```

Three flags carry most of the mistakes:

- `--lower_left_maps_to_s0t0` on **every** encode. Without it the texture arrives flipped, because
  Unity's UV origin is not KTX's.
- `--assign_oetf linear` for anything that is data rather than colour. Left off, the transcode
  applies an sRGB conversion to values that never were sRGB, and normals go subtly wrong in a way
  that reads as a lighting bug.
- `--genmipmap` at encode time. Generating mips in the browser costs load time for a result you
  could have shipped.

Transcoded textures are ordinary GPU textures: memory cost follows the **target format**, not the
size of the `.ktx2` file. A small download is not a small texture in the heap.
