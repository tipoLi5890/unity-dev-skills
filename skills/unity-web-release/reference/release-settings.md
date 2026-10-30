# Reading and writing the settings; player settings for release

Moved out of SKILL.md §0 and §2; same numbering. Proving a write landed, in depth: [`reference/settings-and-verification.md`](settings-and-verification.md).

## 0. Reading and writing the settings

Drive a live Editor (`unity-debug` → `reference/editor-control.md`) rather than hand-editing
`ProjectSettings.asset` — the file you edit is often not the file in force (`unity-debug` →
`reference/harness-trust.md`). Apply the ten release settings as one reviewable batch,
[`templates/WebOptimizer.cs`](../templates/WebOptimizer.cs) — a `[MenuItem]` **file**, not `eval`
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

→ [`reference/settings-and-verification.md`](settings-and-verification.md) — the
17-value read-back, all 31 properties with the deprecated three, and proving the write landed.

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
and the initial memory size. [`templates/WebOptimizer.cs`](../templates/WebOptimizer.cs) writes ten
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
