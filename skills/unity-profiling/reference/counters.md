# Counters: list them, then read them

> Part of the `unity-profiling` skill. Read this before typing any counter name into code.
> A counter name recalled from memory produces a recorder whose `Valid` is false and whose
> `LastValue` is `0` — which reads exactly like "this build draws nothing".

`ProfilerRecorder` reads the same counters the Profiler window shows, from ordinary game code,
with no window open and no connection to make. That is the whole reason this is the first file:
numbers arrive in a log line or a JSONL row instead of in a UI nobody can see.

## Step 1 — print the catalogue this build actually exposes

Counter names vary with the render pipeline, the graphics backend, the platform and the Unity
version. Ask the build:

```csharp
var handles = new List<ProfilerRecorderHandle>();
ProfilerRecorderHandle.GetAvailable(handles);
foreach (var h in handles)
{
    ProfilerRecorderDescription d = ProfilerRecorderHandle.GetDescription(h);
    // d.Category (ProfilerCategory) · d.Name · d.UnitType · d.DataType · d.Flags
}
```

`ProfilerRecorder` and `ProfilerCategory` come from `Unity.Profiling`; the handle and description
types above come from `Unity.Profiling.LowLevel.Unsafe`. Both are in the engine, not a package.

`resources/CounterCatalog.cs` wraps that as `All()`, `Exists(category, name)`, `Grep(substring)`
and `WriteCsv(path = null)`. Copy it into `Assets/` and call it from wherever you already have a
foothold:

```bash
unity command eval 'return UnityDev.Perf.CounterCatalog.Grep("Draw");'
unity command eval 'return UnityDev.Perf.CounterCatalog.WriteCsv();'   # returns the path
unity command eval 'return UnityDev.Perf.CounterCatalog.Probe("Render", "Draw Calls Count");'
```

Driving a live Editor, the `eval` envelope and why the return value lands at `data.result.result`
are `unity-debug` → `reference/editor-control.md`.

The catalogue is **per build**. Run it again on the player build before trusting a name there; the
Editor exposes counters a release player does not.

## Step 2 — the shortlist worth starting from

Confirm every row in the catalogue before using it. This is a starting point, not a contract.

| Category | Name | Reads as |
|---|---|---|
| Render | Draw Calls Count · SetPass Calls Count · Batches Count | How much the CPU asked the GPU to do |
| Render | Triangles Count · Vertices Count | Geometry submitted this frame |
| Render | Shadow Casters Count | The shadow pass drawing the scene a second time |
| Render | Used Buffers Bytes · Used Textures Bytes | Resident graphics memory |
| Render | Vertex Buffer Upload In Frame Bytes · Index Buffer Upload In Frame Bytes | Geometry pushed across the bus this frame |
| Memory | Total Used Memory · GC Used Memory | Levels, not per-frame work |
| Memory | GC Allocated In Frame · GC Allocation In Frame Count | The managed garbage this frame creates |
| Memory | Texture Memory · Mesh Memory | What the asset pipeline is costing at runtime |
| Internal | Main Thread · Render Thread | Thread time in **nanoseconds** |

`resources/FrameSampler.cs` ships exactly this list in `FrameSampler.Counters`; add and remove
entries there rather than scattering recorders through gameplay code.

## Step 3 — the recorder API in one block

```csharp
using var draws = ProfilerRecorder.StartNew(
    ProfilerCategory.Render, "Draw Calls Count", capacity: 1, ProfilerRecorderOptions.Default);

if (!draws.Valid) { /* not exposed on this build — record it as missing, not as zero */ }
long   value  = draws.LastValue;            // integer counters
double asReal = draws.LastValueAsDouble;    // safe for every DataType
var    unit   = draws.UnitType;             // Count · Bytes · TimeNanoseconds · Percent
```

`ProfilerCategory` also takes a string — `new ProfilerCategory("Render")` — which is what lets a
counter list be data rather than code.

Options worth knowing:

| Option | Use it for |
|---|---|
| `StartImmediately` | Begin collecting in the constructor rather than on the first `Start()` |
| `KeepAliveDuringDomainReload` | A recorder that must survive a script recompile in the Editor |
| `WrapAroundWhenCapacityReached` | A ring buffer of the last N frames instead of one value |
| `SumAllSamplesInFrame` | A marker hit many times per frame; without it you read one hit |
| `CollectOnlyOnCurrentThread` | A marker you only care about on the thread you started it from |
| `GpuRecorder` | GPU-side timing for a marker, where the platform supports it |

**Always `Dispose()`.** A recorder is a native handle; leaking one per situation entry leaks for
the session. `using` in a method, an explicit `Dispose()` in `OnDestroy` for a field.

`Internal/Main Thread` is nanoseconds: divide by 1e6 for milliseconds. FrameSampler does that
conversion and reports the counter's unit as `ms`, which is why its kind is `MarkerNs`.

## Step 4 — a counter reading zero is a question, not an answer

Work through these before concluding the work disappeared:

- **`Valid` is false.** The name is wrong for this build, or the category is. Back to step 1. The
  window records it under `missing[]` for exactly this reason.
- **Null graphics device.** `-batchmode -nographics` renders nothing, so every render counter is
  honestly zero. `SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null` is the tell, and the
  window's `run.nullGraphics` carries it into the comparison.
- **A release player.** Some counters are development-build only. Check `Debug.isDebugBuild` before
  filing "the phone has no draw calls".
- **The wrong render pipeline.** Batching and SetPass counters differ between the built-in pipeline
  and a scriptable one. `run.pipeline` in the window says which one produced the number.
- **Editor overhead is in the number.** The Editor draws its own windows and inspector. Editor
  numbers compare against Editor numbers, never against a player's.
- **A domain reload ate the recorder.** Entering Play mode or recompiling restarts the domain; a
  recorder started before it is gone unless it asked to be kept alive.

The window separates the two failures on purpose: `missing[]` is "not exposed", `zeroAll[]` is
"exposed and flat zero for ninety frames". Both are absences. Neither is a measurement of nothing.

## Step 5 — your own counters, and the round trip that proves they work

`ProfilerCounterValue<T>` publishes a game-side number into the same system, so it shows up in the
Profiler window next to the built-in ones. It needs the profiling-core package, which is why
`resources/WorkCounters.cs` puts the mirror behind `#define PERF_PROFILING_CORE` and works without
it.

Before you believe any number a custom counter reports, push a value you cannot mistake for real
data through the whole path and read it back:

```csharp
WorkCounter.Get("selftest").Reset();
for (int i = 0; i < 42; i++) WorkCounter.Get("selftest").Discarded();
Debug.Log(WorkCounter.Get("selftest").ToString());   // expect discarded=42
// then run one window and confirm "Game/selftest.discarded" delta is 42 in the JSONL
```

If 42 does not arrive at the far end, the plumbing is broken and every other number from it is
decoration. Counting the work at the decision points, and reading the three totals, is
`reference/work-counters.md`. Turning per-frame readings into a comparable window is
`reference/frame-windows.md`.
