---
name: unity-web-release
description: >-
  Ship a Unity WebGL/WebGPU build that loads fast enough that people wait for
  it. Load for "the web build is huge", "it takes forever to load", "it stutters
  in Safari but not Chrome", "it crashes on iPhone", "Brotli isn't working",
  "configure the server for a Unity web build", or setting up web player
  settings for release. Covers the settings that shrink the download, the server
  headers without which compression does nothing, browser-specific memory
  ceilings, and where to profile. Android artifacts are unity-android-release.
---

# unity-web-release — the download is the game's first impression

> **Half of compression lives outside Unity, and it undoes everything inside.** The format is
> chosen in the Player Settings and *delivered* by the web server: without the right
> `Content-Encoding` header the browser downloads a `.br` file it cannot read, and either the
> build fails to start or Unity's fallback decompressor runs — costing ~150 KB of JavaScript and
> a slower start, to undo work you already did. **Check the headers before touching a single
> Unity setting.**

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Build is too large | §2, then §3 |
| Slow first load, size looks fine | §1 — compression is not being delivered |
| Stutters in Safari, fine in Chrome | §5 |
| Crashes or reloads on iPhone | §4 |
| Memory climbs until it dies | §4 |
| "Which one of these actually helped?" | §6 |
| Settings were applied, the build ignores them | §0 — the save, not the assignment |
| CI builds bigger than the local build | §0 — `codeOptimization` never left the machine |
| `-executeMethod` aborts on compile errors after web work | §0 — `wasmStreaming` is obsolete-as-error |
| Which browser tool to open | [`reference/settings-and-verification.md`](reference/settings-and-verification.md#profiling-in-the-browser) |

## 0. Reading and writing the settings

Drive a live Editor (`unity-debug` → `reference/editor-control.md`) rather than hand-editing
`ProjectSettings.asset` — the file you edit is often not the file in force (`unity-debug` →
`reference/harness-trust.md`). Apply the ten release settings as one reviewable batch,
[`templates/WebOptimizer.cs`](templates/WebOptimizer.cs) — a `[MenuItem]` **file**, not `eval`
input, because a class declaration cannot live in a statement block. Drop it under
`Assets/Scripts/Editor/`, then fire it with
`EditorApplication.ExecuteMenuItem("Tools/Unity Dev/Apply Web Release Settings")`.

> **A read-back after a write is a report on an object, not on the project.** Assignment touches
> nothing on disk, so an unsaved change echoes back perfectly, reports success, and then dies with
> the Editor session — the build someone launches tomorrow still uses the old value. Call
> `AssetDatabase.SaveAssets()`, then quote the stored values instead of the word "applied".
> Headless runs conceal all of this: `-quit` flushes settings on exit, so the version that forgot
> to save goes green too.

**Three API names where the obvious spelling does not exist and will not compile:**

| Setting | Correct | Does **not** exist |
|---|---|---|
| Managed stripping | `PlayerSettings.GetManagedStrippingLevel(NamedBuildTarget.WebGL)` | `PlayerSettings.managedStrippingLevel` |
| Wasm code optimization | `UnityEditor.WebGL.UserBuildSettings.codeOptimization` | `PlayerSettings.WebGL.codeOptimization`, `…optimizationLevel` |
| IL2CPP code generation | `PlayerSettings.GetIl2CppCodeGeneration(NamedBuildTarget.WebGL)` | a bare property |

`UserBuildSettings` ships inside the **WebGL build-support module**. Read it in a call of its own,
and treat a resolution failure as *"the Web module is not installed"* rather than as a bad
snippet — getting that backwards sends you rewriting correct code.

- **`codeOptimization` is the one value here that does not travel with the repository** — it lives
  under ignored `Library/`, so its absence from `ProjectSettings.asset` proves nothing and in CI
  applying it is a pipeline step. The two checklist consequences are in the reference below.
- **`wasmStreaming` is obsolete as an error.** Touching it does not compile — and Editor scripts
  compile as one assembly, so it takes every other Editor script down and aborts any
  `-executeMethod` in the project.

> **Everything downstream of a web build is checked on a real build in a real browser (§6)** —
> Brotli over a real server, the iOS Safari ceilings in §4, the emscripten profilers,
> `--profiling-funcs` named frames. Reflection on a live Editor settles API names, enum members
> and factory values; it cannot settle any of those.

→ [`reference/settings-and-verification.md`](reference/settings-and-verification.md) — the
17-value read-back, all 31 properties with the deprecated three, and proving the write landed.

## 1. Compression, and the server half

| Compression | When | Note |
|---|---|---|
| **Brotli** | HTTPS or localhost | Best ratio. Browsers only accept it in a secure context |
| **Gzip** | Plain HTTP, legacy CDNs | Universal |
| None | Local dev only | Never ship it |

The server must:

- send `.br` as `Content-Encoding: br`, `.gz` as `Content-Encoding: gzip`;
- send `Content-Type: application/wasm` for `.wasm`;
- speak HTTP/2 or HTTP/3, so the chunks fetch in parallel.

**Decompression Fallback = Off** once that is true. Turn it on only when the host genuinely
cannot set headers — it is a cost, not a safety net.

Verify with the network, not with the setting:

```bash
curl -sI https://host/Build/app.wasm.br | grep -i 'content-encoding\|content-type'
```

## 2. Player settings for release

| Setting | Release |
|---|---|
| Compression Format | **Brotli** (HTTPS) / Gzip (HTTP) |
| Decompression Fallback | **Off** — see §1 |
| Strip Engine Code | **On** — a global property, not per-target |
| Managed Stripping Level | **High** (Medium for dev) |
| Code Optimization | **Disk Size with LTO** (Build Times for dev) |
| WebAssembly Language Features | **2023**, if your browser baseline allows |
| Enable Exceptions | **None**; Explicitly Thrown Only if the code actually catches |
| API Compatibility | **.NET Standard 2.1** — the enum member is `ApiCompatibilityLevel.NET_Standard`, not `NET_Standard_2_0` |
| IL2CPP Code Generation | **Optimize Size** |
| Debug Symbols | **Off** |
| Data Caching | **On** — IndexedDB caching makes repeat visits fast |
| Strip Unused Mesh Components | **On** — a global property, not per-target |
| Initial Memory Size | Tuned to real peak — §4 |
| Memory Growth Mode | **Geometric** |
| Maximum Memory Size | **2048 MB** default; above that Firefox and Chrome before 119 have problems |
| vSyncCount | **0** — the browser paces |
| targetFrameRate | **-1** — let `requestAnimationFrame` drive |

The Wasm 2023 exception model is cheaper than the legacy one in both size and runtime; switching
is usually free if the browser baseline permits it.

**Six of these are already the factory value**, so the apply is shorter than the table looks. On a
project that has never targeted the web, `compressionFormat` reads `Brotli`,
`decompressionFallback` `False`, `dataCaching` `True`, `debugSymbolMode` `Off`,
`memoryGrowthMode` `Geometric` and `maximumMemorySize` `2048`.

Eight values in the table need a write: managed stripping level, IL2CPP code generation, API
compatibility level, exception support, `wasm2023`, `stripUnusedMeshComponents`, `stripEngineCode`
and the initial memory size. [`templates/WebOptimizer.cs`](templates/WebOptimizer.cs) writes ten
settings — six of that eight, plus `dataCaching`, `compressionFormat` and `debugSymbolMode`
restated so the batch also repairs a project someone has already edited, plus `codeOptimization`,
which is not a Player Setting at all. **`stripEngineCode` and the initial memory size are the two
values it leaves to you** — the first because flipping it lands on every platform (below), the
second because the number comes from a measured peak rather than from a table (§4).

Read `stripEngineCode` and `stripUnusedMeshComponents` before writing them: they are project
state, not factory defaults, and flipping either changes every platform the project ships — check
the others first.

> **Stripping bites back the same way it does on Android.** IL2CPP removes types only reached by
> reflection, and the failure is a callback that never arrives with no exception. `[Preserve]` or
> `link.xml`. → `unity-android-release` → `reference/size-and-stripping.md`.

## 3. Getting the size down, in order of payoff

1. **Shader variants** (`Project Settings > Graphics`): Lightmap Modes and Fog Modes to
   Automatic, Instancing Variants to Strip Unused, Batch Renderer Group Variants to Strip All if
   you do not use BRG, and **audit Always Included Shaders** — every entry there ships all of its
   variants whether or not anything references it. Test afterwards for a shader you actually
   needed.
2. **Unused packages.** Check `Packages/manifest.json` against what the game really uses. The
   Input System is a notable contributor when it is present and unused.
3. **The Web Stripping Tool** (`com.unity.web.stripping-tool`) analyses the built Wasm and
   identifies whole engine submodules the game never touches — 3D graphics in a 2D game, for
   instance. It reaches further than Managed Stripping Level can, because it works on the binary
   rather than on managed code.
4. **Move assets out of the `.data` file** into Addressables or AssetBundles, so the first load
   fetches only what the first screen needs. Textures loaded that way should be **KTX2/Basis** —
   the target GPU is unknown at build time on the web, so one file that transcodes at load is the
   only way to ship a native format to every device. Mechanism and the encode-vs-baked rule:
   `unity-3d-models` (SKILL, the KTX2/Basis paragraph); `toktx` and the runtime load calls:
   [`reference/settings-and-verification.md`](reference/settings-and-verification.md#ktx2-encoding-with-toktx).
5. **Read/Write Enabled off** on textures and meshes: on the web it duplicates the data straight
   into the Wasm heap, so it costs download *and* memory.

Budget first: **under 30 MB to first playable**, bundles under 51 MB, canvas resolution clamped in
the template →
[`reference/settings-and-verification.md`](reference/settings-and-verification.md#the-download-budget-and-two-cache-ceilings).

## 4. Memory, and iOS Safari in particular

Web memory is not a soft limit; exceeding it kills the tab.

- **Wasm growth is a full buffer copy.** A too-small Initial Memory Size means repeated copies
  during load — visible as a stall, diagnosed as "slow loading". Set it to a realistic peak and
  use Geometric growth.
- **iOS below 18:** the WebContent process caps around 1.5 GB and the Wasm Gigacage at 2 GB, with
  typed arrays sharing the pool. On older hardware, heap growth caps far lower — but a large
  **upfront** allocation succeeds where incremental growth fails, so on iOS set Initial Memory
  Size to the target peak rather than relying on growth.
- **iOS 18+** lifts most of this.
- **Target a Wasm heap under ~200 MB** for broad compatibility; past ~300 MB, older iOS starts
  crashing rather than degrading. Confirm the ceiling on the oldest iOS you support before sizing
  the heap to it: run a real build on that device and watch the tab survive your measured peak.

Two platform facts that surprise people:

- **AudioMixer effects do not exist on the Web audio backend.** Mixers and groups work for volume
  only — confirm any effect you rely on in a browser build before designing audio around it. Set
  audio to mono to load faster, and compress the clips — Vorbis (`unity-audio`).
- **Video plays only from a URL with CORS enabled, or from StreamingAssets**, and iOS streaming
  needs the server to honour HTTP range requests. MP4/H.264.

## 5. Browser differences that are not your bug

- **Safari stutter with Chrome fine:** first check for `Application.targetFrameRate = 60`. On
  Safari that fights the browser's own pacing; `-1` is correct. Second, Safari's WebGL and Wasm
  runtimes differ from Chromium's and some GLSL constructs behave differently — that one needs a
  device.
- **Editor Play Mode does not represent a browser at all.** Measure in the browser, and in more
  than one: Chrome and Safari differ in both GC and JIT behaviour.
- Firefox caches individual files only up to roughly 50 MB, so a larger chunk is re-downloaded on
  every visit and Chrome shows nothing — the `about:config` key and safe bundle size are below.

The short version: Chrome DevTools **Performance** for hitching, **Memory** for a climbing heap,
**Network** for slow first load; Safari Web Inspector for Safari-only rendering; Unity's own
profiler over WebSocket for a development build. Symptom by symptom, and readable C# names in a
Wasm flamegraph:
[`reference/settings-and-verification.md`](reference/settings-and-verification.md#profiling-in-the-browser).

## 6. Verify — before and after, or it did not happen

Lower quality levels are the cheapest remaining win (Very Low or Low as the web default, or a
web-specific level with real-time shadows, post-processing and high particle counts disabled),
and `OnDemandRendering.renderFrameInterval` on idle screens saves a laptop's battery.

But none of it counts without a pair of numbers:

```bash
ls -l Build/*.wasm* Build/*.data*                # transferred size, per file
curl -sI https://host/Build/app.wasm.br | head   # is compression actually delivered?
```

Record size and cold-load time before and after, on the same connection. **Three
adjust-and-verify rounds, then report** rather than continuing to turn knobs — past that the
remaining wins are architectural (what loads first) rather than settings.

Firefox's `about:memory` breaks a tab into Wasm code, heap, `.data` and web audio — read the heap
against §4's ceilings. That, and why `python3 -m http.server` can never show a Brotli win:
[`reference/settings-and-verification.md`](reference/settings-and-verification.md#serving-a-build-locally).

**Report, then wait** before the next round. Say the size delta per file, which settings changed
with their before and after values, and what the server headers actually returned — not "optimised
the web build".

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Android artifacts, signing, stripping fallout | `unity-android-release` |
| The `unity` CLI, licences, CI wiring for the build itself | `unity-cli` |
| Reaching a live Editor, or one that will not start | `unity-debug` |
| Audio import settings and codecs | `unity-audio` |
| Mesh and texture optimisation at the asset level | `unity-3d-models` |
| Which render pipeline is actually in force | `unity-render-urp` |
| Sprite packing, and atlas variants for the web | `unity-sprite-atlas` |
| In-game frame windows and counters | `unity-profiling` |

## Related files

[`templates/WebOptimizer.cs`](templates/WebOptimizer.cs) — the ten release settings as one
menu item, saved and read back ·
[`reference/settings-and-verification.md`](reference/settings-and-verification.md) — proving the
write landed, browser profiling, local servers, `toktx` encoding.
