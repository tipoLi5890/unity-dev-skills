# Performance tests: a regression gate inside the suite

> Part of the `unity-profiling` skill. A window says where the time went. A performance test asks
> one question on every run — is this situation still inside the budget it had yesterday — and
> answers as a test result. `templates/PerfRegressionTest.cs` is the courier-run gate to copy.

## Two instruments, one question each

| | Performance test | FrameSampler window |
|---|---|---|
| Asks | Did this commit make a named situation slower than its recorded baseline? | Where does the time go, and did this change help? |
| Runs | In the suite, `-runTests -testCategory Perf` | A driven run, a live Editor, a player flag |
| Answers with | Pass, fail or inconclusive in the results XML | A before/after table from `scripts/compare_windows.py` |
| Reads | Frame time and named markers, as medians | Frame time to p99, counters, work counters, the CPU/GPU split |
| Lives | In the suite, permanently | Taken, compared, thrown away |

> **Do not run both for the same question.** A window inside a performance test puts its own
> `LateUpdate` and recorders into the gated frames; a performance test gives one median where an
> investigation needs the whole table. When the gate goes red, investigate with windows:
> `reference/frame-windows.md`, then `reference/compare.md`.

## The package in four calls

`com.unity.test-framework.performance`, namespace `Unity.PerformanceTesting`. The test asmdef
references `Unity.PerformanceTesting` next to `UnityEngine.TestRunner`. Every call below exists in
package 3.4; confirm on yours by reading
`Library/PackageCache/com.unity.test-framework.performance*/Runtime/Measure.cs` before copying one.

```csharp
[UnityTest, Performance, Version("1")]          // PlayMode: Frames and markers need a player loop
public IEnumerator HazardLane()
{
    // ... load the scene, enter the situation, wait on its readiness set ...
    yield return Measure.Frames()
        .WarmupCount(30).MeasurementCount(120)
        .SampleGroup(new SampleGroup("hazard-lane.frame", SampleUnit.Millisecond))
        .ProfilerMarkers(new SampleGroup("Courier.HazardUpdate", SampleUnit.Millisecond))
        .Run();
}

[Test, Performance]                             // EditMode or PlayMode
public void LanePick() =>
    Measure.Method(() => _picker.Choose(1.31f))
        .WarmupCount(10).IterationsPerMeasurement(1000).MeasurementCount(20)
        .SampleGroup(new SampleGroup("lane-pick", SampleUnit.Microsecond))
        .GC()                                   // adds "lane-pick.GC()": allocations per iteration
        .Run();

using (Measure.Scope(new SampleGroup("enter.hazard-lane", SampleUnit.Millisecond))) { /* one sample */ }
using (Measure.ProfilerMarkers(new SampleGroup("Courier.HazardUpdate", SampleUnit.Millisecond))) { /* per frame */ }
```

| Rule | Because |
|---|---|
| Give both `WarmupCount` and `MeasurementCount` | Without a count the package probes one from timing, so two runs measure different frames. `WarmupCount` alone makes `Frames` log an error and record nothing, and `Method` throw |
| Name every group and give it a unit | The default frame group is `Time` in the docs and `FrameTime` in the source. A marker named by string records nanoseconds |
| The marker exists before measuring starts | Its recorder is created after warm-up; an unknown name logs `ProfilerMarker measurement is attached to invalid marker`, which fails the test. `Profiler.BeginSample` regions are not measured: declare a `ProfilerMarker`, wrap the work in `.Auto()` |
| Compute the median from `Samples` | `SampleGroup.Median` and the other statistics are filled in after the test body returns; inside it they read 0, which passes every gate |
| No `PlayerPrefs.DeleteAll()` in a run that includes Perf | In the Editor the package keeps its run metadata in PlayerPrefs and reads it back when a perf test ends. Delete the game's own keys by name |

## The gate: a median against a recorded baseline

- **The median, never the worst frame.** The worst of 120 frames is one collection or one OS
  hiccup; a gate on it goes red at random and teaches everyone to rerun until green. The worst
  frame is an investigation number: `hitches` and `ft_max` in a window.
- **A baseline belongs to an instrument.** Keep it in the test source next to the gate, keyed by
  run mode (the names a window writes as `run.mode`), processor and editor version. A missing row
  ends the test `Inconclusive` with the row to paste. `Inconclusive` keeps `failed="0"`, so the
  driver prints `inconclusive=` and treats it as not green → `unity-debug` → `reference/test-verdicts.md`.
- **Tolerance from measured spread, not from a wish.** Run the gate five times, alone, on the gate
  machine. Take the widest distance of one run's median from the median of the five; tolerance is
  1.5× that and never below 5%. Add an absolute floor so a 0.3 ms marker cannot fail on 0.04 ms:
  `limit = baseline + max(baseline × tolerance, floor)`.
- **Faster than the band is a question.** It passes as `pass-faster` with the row to re-record,
  once you have checked it is not faster because it does less (`reference/compare.md`). Re-record
  in its own commit, both numbers in the message: a stale slow row lets the next regression in.
- **Bump `[Version]` and re-record together** whenever the test's work changes.
- **An allocation count does not depend on the machine.** Gate a `.GC()` group at its exact
  baseline, usually zero.

The template prints one line per run, and a `HARNESS:` message on anything that measured nothing:

```
[PERFGATE] test=hazard-lane mode=batchmode-nographics n=120 frame_med=2.41 frame_limit=2.76
           marker_med=0.31 marker_limit=0.36 vsync=0 fps_cap=-1 break=none verdict=pass
```

| Outcome | Means | Do |
|---|---|---|
| `verdict=pass` / `pass-faster` | Inside the band / under it | Nothing / check the work, re-record |
| `verdict=REGRESSION`, test failed | A real verdict | Investigate with windows; never rerun until green |
| `HARNESS:` failure | Too few samples, a marker that never fired, an empty lane, a run that ended mid-window | Fix the test; the baseline is not the problem |
| `verdict=no-baseline`, inconclusive | First run on this instrument | Paste the `record=` row |

Once a row is recorded, prove the gate can fail before trusting a pass: `PERF_GATE_BREAK=stall`
adds 4 ms of work to every frame, and the frame gate must turn red. Keep the stall above the
tolerance band. A break run never offers a row to record.

## Owning the machine

`[Category("Perf")]` on the class; `[Performance]` adds the category `Performance`. Test Framework
1.6 matches each `-testCategory` value as a regular expression anywhere in the name, so
`-testCategory Perf` selects both, and every other run leaves them out with `-testCategory '!Perf'`
(single quotes: an interactive shell expands `!` inside double quotes). Confirm once that no perf
test appears in that other run's XML.

> **Never run a perf test while another lane shares the machine.** Two Editors share cores, memory
> bandwidth and the thermal budget: a median taken while lane 2 compiles measures lane 2. The perf
> category runs alone, after the lanes → `unity-debug` → `reference/parallel-runs.md`

```bash
pgrep -fl "Contents/MacOS/Unity( -|$)"         # must print nothing: no Editor, no lane, no build
mkdir -p /tmp/perf && rm -f /tmp/perf/results.xml
"$UNITY" -projectPath . -batchmode -nographics -runTests -testPlatform PlayMode \
  -testCategory Perf -testResults /tmp/perf/results.xml -logFile /tmp/perf/tests.log
grep '\[PERFGATE\]' /tmp/perf/tests.log
```

## What each instrument can see

| Run | The frame time holds | Gate on it |
|---|---|---|
| `-batchmode -nographics` | Scripts, physics, animation; nothing renders | CPU-side regressions: frame median, game markers |
| `-batchmode` | Plus render submission on a real device, nothing presented | The same — confirm on your platform that cameras render |
| windowed | Plus presentation, waiting on the GPU, Editor overhead | A GPU regression shows as frame time, unattributed |
| player, `-testPlatform <BuildTarget>` | The built game | Closest to shipped → `unity-debug` → `reference/player-tests.md` |

> **The gate is CPU-side unless it runs windowed.** Under `-nographics` the GPU is not in the frame
> at all and render counters read zero honestly (`reference/counters.md`). Batchmode and windowed
> are two instruments: two baseline rows, never one compared against the other.

- The template turns vsync and the frame cap off for the measurement and restores them in
  `TearDown`. Confirm that `git status --short ProjectSettings/` is clean after a perf run; one
  that dies before `TearDown` can leave a quality setting changed.
- Windowed: confirm the medians match with the Editor focused and in the background. If not, the
  Editor is throttled and the windowed gate needs its window in front.
- With the package installed, every player build writes `PerformanceTestRunInfo.json` and
  `PerformanceTestRunSettings.json` into `Assets/Resources` and deletes them afterwards. A build
  that dies leaves them: `git status` after it. Builds belong to lane 0.

## Where the numbers land

1. **The verdict is the results XML** from `-testResults`, read like any other test's.
2. **The samples are in that XML too.** Each perf test's `<output>` carries one
   `##performancetestresult2:` line of JSON; the package builds its own file from those lines.
3. **The package's JSON** is written when the run ends: to the path after `-perfTestResults`, or
   without it, `PerformanceTestResults.json` and a second copy of the results XML in
   `Application.persistentDataPath`, which every lane shares; pass the path.
4. **No perf test ran, no JSON.** A missing file after a perf run means the filter selected nothing.

The Editor's **Window > General > Performance Test Report** reads only the `persistentDataPath`
copy; Unity's Performance Benchmark Reporter compares files over time outside the Editor. Neither
is the gate. Confirm on your version:

```bash
grep -rl perfTestResults Library/PackageCache/com.unity.test-framework.performance*/Editor/   # empty: no flag
find ~/Library/Application\ Support -name PerformanceTestResults.json -mmin -30   # macOS default copy
```

## Symptom → cause

| Symptom | Cause |
|---|---|
| The same commit goes red, then green on a rerun | Tolerance under the run-to-run spread, or something else was running |
| `ProfilerMarker measurement is attached to invalid marker` | Wrong name, or the marker's class had not run when measuring started |
| Marker median 0 on a marker that does run | It fires on a minority of frames: gate its total, or `Measure.Method` the operation |
| `Provide execution count or remove warmup count`, no frame samples | `WarmupCount` without `MeasurementCount` |
| `Trying to record samples but there is no active performance tests` | `[Performance]` missing from that test |
| Fewer samples than `MeasurementCount` asked for | A measurement-count override on the command line; 3.4 reads `-performance-measurement-count` |
| Frame median sits at 16.67 or 8.33 ms | vsync or a frame cap: the display, not the game |
| An error from the package as a perf test ends | `PlayerPrefs.DeleteAll()` earlier in the run removed the package's run metadata |
