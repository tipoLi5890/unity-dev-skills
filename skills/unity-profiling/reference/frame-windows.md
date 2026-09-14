# Frame windows: ninety frames, one row, one line

> Part of the `unity-profiling` skill. One frame time is an anecdote. A window is a measurement
> you can put next to another one.

A **window** is a fixed number of consecutive frames, sampled after a warm-up, summarised into
one JSONL record and one `[PERF]` log line. `resources/FrameSampler.cs` is the whole mechanism.

## What a window is made of

- **Warm-up, 30 frames by default.** The first frames after entering a situation carry shader
  compilation, pool growth and first-touch page faults; including them measures starting rather
  than playing.
- **Deliberately zero warm-up** when the *first* appearance is what you are chasing. Label that
  window with a `-cold` suffix so nobody compares it against a warmed one.
- **90 frames by default.** Long enough for a stable median, short enough that a driven situation
  can produce three of them.
- **Sampled in `LateUpdate` at `[DefaultExecutionOrder(int.MaxValue)]`**, after every other script.
- **`Stopwatch` is the clock.** `Time.deltaTime` is scaled and smoothed; the interval between two
  `LateUpdate` calls on a `Stopwatch` is the number to report. `Time.frameCount` is recorded
  alongside as `firstFrame` and `lastFrame`, so a window can be located in a log.

## The statistics, and why each one is there

| Number | Says |
|---|---|
| `median` | What the frame normally costs |
| `mean` | Drags toward the spikes — the gap between mean and median *is* the unevenness |
| `p90` / `p95` | Where the bad frames start |
| `p99` / `max` | The single worst frame; at n=90 read them as "the worst one", not a tail estimate |
| `min` | A floor that sits exactly at 16.67 or 8.33 is vsync, not your code |
| `n` | Fewer frames than asked for means the run ended early |
| `hitches` | Count of frames over **2× median** — one spike and a constant vibration are different faults |

Counters are summarised by kind:

- **perFrame** (draw calls, bytes allocated this frame) — median/p95/max/min/mean **and `sum`**.
  The sum is what matters for allocation: 2 KB a frame is 184 KB across a window.
- **level** (total used memory) — the same statistics, **no sum**; summing a level counts the same
  bytes ninety times.
- **cumulative** (work counters) — `start`, `end`, `delta`. Only the delta belongs to the window.
- **markerMs** (thread times) — nanoseconds converted to milliseconds, then summarised.

## Run modes are five different instruments

`run.mode` is written into every record and `scripts/compare_windows.py` refuses to compare across
it unless told to.

| Mode | What it is good for | What it lies about |
|---|---|---|
| `batchmode-nographics` | Logic, allocation, work counters, in CI | Every render counter is honestly zero |
| `batchmode` | Same, with a real device | No presentation, no end of frame |
| `editor-windowed` | Iterating on a change you can also see | Editor overhead is in every number |
| `player-dev` | The closest measurable thing to the shipped game | Development build costs are included |
| `player-release` | What the player gets | Counters are absent; needs its own catalogue run |

`RunInfo.Detect()` also records the graphics device, pipeline, platform, screen size, vsync,
`targetFrameRate` and GC mode — the settings that silently change the answer. A window taken at
vsync 1 has a floor that has nothing to do with your change.

## FrameTimingManager, for the CPU/GPU split

Counters say how much work was submitted, not whether the frame waited on the CPU or on the GPU.
`FrameTimingManager` says that, where the platform supports it:

```csharp
FrameTimingManager.CaptureFrameTimings();
var buf = new FrameTiming[1];
uint got = FrameTimingManager.GetLatestTimings(1, buf);
// buf[0].cpuFrameTime · cpuMainThreadFrameTime · cpuRenderThreadFrameTime · gpuFrameTime
```

Three rules, each of which costs a round otherwise:

1. **It needs Frame Timing Stats enabled in Player Settings.** Confirm the setting name on your
   version before assuming a build has it.
2. **The first few frames return zeros** — the manager is filling its history; warm-up covers it.
3. **All-zero is "unavailable", not "instant".** A `gpuFrameTime` of 0 means the platform reported
   none. FrameSampler writes `"frameTiming": "unavailable"` rather than a row of zeros, because a
   zero in a comparison table reads as a 100% improvement.

## The line and the record

One greppable line per window:

```
[PERF] window=hazard-lane mode=editor-windowed frames=90 ft_med=8.31 ft_p95=12.90 ft_max=41.2
       hitches=2 draw_med=412 tris_med=51200 gc_sum=184320 disc[pickup-pool]=214
       missing=1 zero=0 path=/tmp/perf/windows.jsonl
```

And one JSONL record, `schema: "perf-window/1"`, appended to `$UNITY_PERF_OUT` or
`<persistentDataPath>/perf/windows.jsonl` — one line, wrapped here, three counters kept, and
`cpuMain`/`cpuRender` beside `cpu` and `gpu` in the same shape:

```json
{"schema":"perf-window/1","label":"hazard-lane","utc":"2026-01-05T10:00:00Z","frames":90,
 "warmup":30,"firstFrame":412,"lastFrame":501,
 "run":{"mode":"editor-windowed","batchmode":false,"editor":true,"devBuild":true,
        "graphicsDevice":"Vulkan","nullGraphics":false,"pipeline":"UniversalRenderPipelineAsset",
        "unity":"6000.0.30f1","platform":"WindowsEditor","vsync":0,"targetFrameRate":-1,
        "screen":"1920x1200","gcMode":"Enabled","frameTimingStats":true,"profilerEnabled":false},
 "situation":{"name":"hazard-lane","seed":7},
 "frameTime":{"unit":"ms","mean":9.12,"median":8.31,"p90":11.4,"p95":12.9,"p99":38.0,
              "max":41.2,"min":7.8,"n":90,"hitches":2},
 "frameTiming":{"unit":"ms",
   "cpu":{"mean":9.0,"median":8.2,"p90":11.0,"p95":12.4,"p99":36.0,"max":40.0,"min":7.6,"n":90},
   "gpu":{"mean":6.1,"median":5.9,"p90":7.0,"p95":7.4,"p99":9.0,"max":9.6,"min":5.5,"n":90}},
 "counters":{
   "Render/Draw Calls Count":{"unit":"Count","kind":"perFrame","median":412,"p95":455,"max":470,
                              "min":390,"mean":415,"sum":37350},
   "Memory/GC Allocated In Frame":{"unit":"Bytes","kind":"perFrame","median":1024,"p95":9200,
                                   "max":40960,"min":0,"mean":2048,"sum":184320},
   "Game/pickup-pool.discarded":{"unit":"Count","kind":"cumulative","start":0,"end":214,
                                 "delta":214}},
 "missing":["Render/Shadow Casters Count"],"zeroAll":[]}
```

**Delete the JSONL before a run.** It is appended to, and a stale window compared against a fresh
one is the quietest wrong answer this skill can produce.

## Three ways to start a window

**1 — Inside a driven run**, which is the one to prefer, because the window then covers a named
moment rather than whatever the game happened to be doing:

```csharp
FrameSampler.SituationName = "hazard-lane";
FrameSampler.SituationSeed = 7;
yield return FrameSampler.Sample("hazard-lane", frames: 90, warmup: 30);
```

Booting straight into that moment and waiting for it to be ready, rather than sleeping, is
`unity-play-harness` → `reference/situations.md`.

**2 — Against a live Editor**, no recompile:

```bash
unity command eval 'return UnityDev.Perf.PerfProbe.Begin("hazard-lane");'
unity command eval 'return UnityDev.Perf.PerfProbe.LastLine();'   # "running" until it is done
```

Or register it as a project command, in an **Editor** assembly, so it is one call:

```csharp
[CliCommand("perf_window", "Sample a frame window", MainThreadRequired = true)]
public static string PerfWindow([CliArg("label", "Window label")] string label = "window",
                                [CliArg("frames", "Frames to sample")] int frames = 90)
    => UnityDev.Perf.PerfProbe.Begin(label, frames);
```

The assembly that file belongs in, and the recompile-then-confirm loop that proves the name
registered, are `unity-debug` → `reference/editor-control.md`.

**3 — In a player build**, which is where the answer for a device lives:

```bash
<player> -perf-window hazard-lane -perf-frames 90 -perf-warmup 30 \
         -situation hazard-lane -perf-out /tmp/perf/windows.jsonl
```

Whatever starts it, take **three windows** before believing a 10% change, then
`reference/compare.md`.
