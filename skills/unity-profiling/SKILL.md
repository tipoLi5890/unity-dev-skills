---
name: unity-profiling
description: >-
  Measure the work behind a slow or uneven frame in a Unity 6 game as numbers an
  agent can compare across changes: ProfilerRecorder counters without the
  Profiler window, 90-frame windows with median/p95/worst, work-accounting
  counters (scheduled / completed / discarded) for streaming and pooling, and a
  before/after table. Load for "the frame rate drops when…", "it hitches when
  the third pickup spawns", "how many draw calls is this", "is it the GC", "did
  my change actually help", "it is slow only on the phone", "which counters
  exist on my version". A driven run is not a hardware benchmark. Turning a feel
  complaint into a reproducible situation is unity-play-harness.
---

# unity-profiling — measure the work, then compare the table

"It feels smoother now" survives exactly until someone else plays it. A frame time on its own is
barely better: one number, from one moment, on one machine, with nothing to hold it against.

What settles a performance question is a **window** — a fixed number of frames of a named
situation, summarised into one row — taken twice, with one thing changed in between.

> **A driven run is not a hardware benchmark.**
> `batchmode-nographics`, `editor-windowed` and a player build are three different instruments.
> Each is internally consistent and none of their numbers mean anything against another's. Every
> window records which instrument produced it, and the comparison script refuses to subtract
> across them. And a human playing the actual build still decides shader compilation, GPU upload
> and whether the thing feels good — measurement narrows the question, it does not answer it.

---

## The loop

**1 · List the counters this build exposes.** Never recall them. Names differ by render pipeline,
graphics backend, platform and version, and a wrong name produces a recorder that reads `0` —
indistinguishable from "this build draws nothing". `resources/CounterCatalog.cs`, then
`reference/counters.md`.

**2 · Sample a window.** 90 frames after 30 warm-up frames, sampled in `LateUpdate` at the end of
the execution order with a `Stopwatch` as the clock. Out comes one greppable `[PERF]` line and one
JSONL record. `resources/FrameSampler.cs`, then `reference/frame-windows.md`.

**3 · Change exactly one thing.** Two changes in one window cannot be attributed, and the wrong
one gets kept.

**4 · Re-run the same situation and compare.** Same seed, same instrument, three windows a side.
`scripts/compare_windows.py`, then `reference/compare.md`.

### One turn of the loop

The complaint is *"it hitches when the third pickup spawns in the hazard lane"*. Booted into that
situation with a fixed seed, one window says:

```
[PERF] window=hazard-lane mode=editor-windowed frames=90 ft_med=8.31 ft_p95=12.90 ft_max=41.2
       hitches=2 draw_med=412 tris_med=51200 gc_sum=184320 disc[pickup-pool]=214 missing=1 zero=0
```

Read it in that order. The median is fine, so the game is not uniformly heavy; `ft_p95` at 12.90
against a median of 8.31 is unevenness. Draw calls and triangles are the same as the run before,
so it is not a rendering cost at all. The last number is the finding: the pickup pool **threw away
214 units of work** during those ninety frames while completing seventeen. The lane selector is
flipping across a 1.3-unit lane boundary and cancelling the set it was building each time.

A 0.2-unit dead band on that boundary, then the same window again: discarded 214 → 7, `ft_p95`
12.90 → 9.10 ms, hitches 2 → 0, triangles unchanged. One parameter, two numbers that moved
together, and a table that says why.

---

## Load what the situation needs

| The situation | Read |
|---|---|
| Starting from nothing; "which counters exist on my version"; a counter reads zero | `reference/counters.md` |
| Taking the measurement: warm-up, window size, run modes, the log line and the JSONL schema | `reference/frame-windows.md` |
| Hitches around spawning, streaming or pooling; a system that builds the same thing twice | `reference/work-counters.md` |
| "did my change actually help"; building the before/after table; a comparison that refuses | `reference/compare.md` |
| A window in hand and no cause yet: first-appearance hitch, GC, synchronous loads, distant geometry | `reference/where-the-time-goes.md` |
| No counter names the cost and you need the marker inside the frame | `reference/raw-capture.md` |
| Booting straight into the moment to be measured, and driving it identically twice | skill `unity-play-harness` |
| Running Unity, reading Editor.log, screenshots, proving the harness told the truth | skill `unity-debug` |
| Deciding what the budget should be in the first place | skill `unity-game-brief` |

Four files to copy into `Assets/` — namespace `UnityDev.Perf`, Runtime, no package required:
`resources/CounterCatalog.cs`, `resources/FrameSampler.cs`, `resources/WorkCounters.cs`,
`resources/ProfilerRawCapture.cs`. They are instrumentation, not gameplay; keep them behind a
development-build check before shipping.

---

## Where the time goes

A router, read against a window you already have. Depth for the first four rows is in
`reference/where-the-time-goes.md`; the rest belong to the skill that owns the subsystem.

| The window says | Go to |
|---|---|
| One large `ft_max` the first time something appears, never again | first-appearance section, then `unity-render-urp` |
| `Memory/GC Allocated In Frame` has a non-zero median; spikes on a period | GC section, then `unity-game-ui` for per-frame string building |
| A spike lined up with a jump in a completed-work counter | synchronous-loads section, then `unity-audio` when it is a clip |
| Triangles high while looking at distance, draw calls ordinary | distant-geometry section, then `unity-3d-models` |
| Discarded work climbing while scheduled climbs | `reference/work-counters.md` |
| Draw calls and SetPass calls high, triangles ordinary | `unity-sprite-atlas` · `unity-render-urp` · `unity-game-ui` |
| GPU frame time much larger than the CPU times | `unity-render-urp` |
| Shadow caster count high | `unity-render-urp` |
| Pixel art shimmering as well as slow | `unity-2d-pixel-perfect` |
| Slow only in the browser | `unity-web-release` |
| Slow only on the device | `unity-android-release`, after a development-player window taken on it |
| Frame time is fine and it still feels wrong | `unity-play-harness` |

---

## Discipline

- **List, never recall.** Counter names are defined by the build, not by your memory of them. One
  catalogue call is cheaper than one wrong name, and a wrong name reports zero rather than failing.
- **A counter that reads zero on every frame of a window is an absence, not a measurement of
  nothing.** The window separates the two: `missing[]` is "not exposed on this build",
  `zeroAll[]` is "exposed and flat". Report both; never quietly average a zero into a result.
- **Same situation, same instrument, or do not compare.** Different run mode, graphics device,
  screen size, vsync or warm-up makes two numbers that subtract cleanly and mean nothing.
- **Median and worst, never just worst** — one spike and a constant vibration are different faults
  — with p95 between them to say where the bad frames start.
- **Warm up 30 frames by default.** The first frames after entering a situation measure starting,
  not playing. Set warm-up to 0 deliberately when a first-appearance hitch *is* the subject, and
  put a `-cold` suffix on that window's label so nobody compares it against a warmed one.
- **Three windows a side before believing a 10% change.** Below that, one window each way is a
  coin toss, and the comparison script will tell you when the spread makes the change unreadable.
- **Delete the JSONL before every run.** It is appended to. A stale window compared against a
  fresh one is the quietest wrong answer this skill can produce.
- **Print the numbers the judgement rests on.** "The hitch is gone" ages badly; "discarded 214 → 7,
  p95 12.90 → 9.10 ms" keeps saying the same thing after the next change.
- **Check whether the candidate is faster because it does less.** Fewer things built is not the
  same as things built more cheaply. Read the scheduled and completed counters before celebrating.
- **Every report names its run mode and what it did not cover.** A report that omits the
  instrument invites the reader to assume it was the shipped game.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Booting into a moment, a readable state line, a feel complaint with nothing to measure | `unity-play-harness` |
| Driving Unity, exit codes, screenshots, proving a harness told the truth | `unity-debug` |
| Installing editors, licences, CI invocation | `unity-cli` |
| Atlasing sprites, decimating meshes | `unity-sprite-atlas` · `unity-3d-models` |
| Configuring post-processing and renderer features | `unity-render-urp` |
| Browser download size, headers and memory ceilings | `unity-web-release` |
| Building, signing and reading a device artifact back | `unity-android-release` |
| Audio memory, load types and mixer cost | `unity-audio` |
| Deciding what the budget should be | `unity-game-brief` |
