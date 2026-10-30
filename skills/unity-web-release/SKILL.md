---
name: unity-web-release
description: >-
  Ship a WebGL/WebGPU build: shrink the download, Brotli server headers, Safari and iPhone memory.
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
| "The web build is huge" | [`reference/release-settings.md`](reference/release-settings.md) §2, then §3 |
| "It takes forever to load", size looks fine; "Brotli isn't working"; configure the server for a Unity web build | §1 — compression is not being delivered |
| "It stutters in Safari but not Chrome" | §5 |
| "It crashes on iPhone", or reloads | §4 |
| Memory climbs until it dies | §4 |
| "Which one of these actually helped?" | §6 |
| Setting up web player settings for release | [`reference/release-settings.md`](reference/release-settings.md) §2 |
| Settings were applied, the build ignores them | [`reference/release-settings.md`](reference/release-settings.md) §0 — the save, not the assignment |
| CI builds bigger than the local build | [`reference/release-settings.md`](reference/release-settings.md) §0 — `codeOptimization` never left the machine |
| `-executeMethod` aborts on compile errors after web work | [`reference/release-settings.md`](reference/release-settings.md) §0 — `wasmStreaming` is obsolete-as-error |
| Which browser tool to open | [`reference/settings-and-verification.md`](reference/settings-and-verification.md#profiling-in-the-browser) |

## 0. Reading and writing the settings → `reference/release-settings.md` §0

Applying settings by script: a value assigned and never saved is ignored — save, then quote the
stored values; `codeOptimization` lives under ignored `Library/`, so it never reaches CI; and
`wasmStreaming` is obsolete-as-error under `-executeMethod`.

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

## 2. Player settings for release → `reference/release-settings.md` §2

The release value for each player setting — compression, stripping, code optimisation,
exceptions, memory, frame pacing — and which six are already the factory value.

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

Record size and cold-load time before and after, on the same connection. **At most
three adjust-and-verify rounds** — past that the remaining wins are architectural (what loads
first) rather than settings.

Firefox's `about:memory` breaks a tab into Wasm code, heap, `.data` and web audio — read the heap
against §4's ceilings. That, and why `python3 -m http.server` can never show a Brotli win:
[`reference/settings-and-verification.md`](reference/settings-and-verification.md#serving-a-build-locally).

**Report after each round, then wait** before the next. Say the size delta per file, which settings changed
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
