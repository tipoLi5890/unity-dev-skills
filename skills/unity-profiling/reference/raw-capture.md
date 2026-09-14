# Raw capture: when a counter cannot name the marker

> Part of the `unity-profiling` skill. The last resort, deliberately. A window is cheap, repeatable
> and comparable; a capture is large, single-use and changes what it measures if you are careless.

Reach for this when a window has already told you *that* a frame costs 41 ms and no counter tells
you *what* inside it did. `resources/ProfilerRawCapture.cs` writes the capture from the run and
extracts it to CSV in the Editor, so the answer arrives as rows rather than as a UI nobody can see.

## Writing a capture from a driven run

```csharp
PerfRawCapture.Start("/tmp/perf/hazard-lane");   // .raw is appended
// ... drive the situation, ~200 frames is plenty ...
PerfRawCapture.Stop();                            // the file is only complete after this
```

The three properties underneath are ordinary runtime API:

```csharp
Profiler.logFile = path;        // set the path FIRST
Profiler.enableBinaryLog = true;
Profiler.enabled = true;
```

**Order matters.** Assigning `logFile` while the profiler is already enabled is how you get an
empty file and no error. Stop by setting `enabled` and `enableBinaryLog` back to false and
clearing `logFile`; reading the file before that gives a truncated capture that loads as zero
frames.

A player build can also be told to do this from the command line. The flags exist, and their exact
spelling has moved — **confirm them on your version before writing them into a script**, by running
the player with `-help` or checking the command-line arguments page for your editor version:

| Roughly | Does |
|---|---|
| `-profiler-enable` | Start the profiler with the process |
| `-profiler-log-file <path>` | Where the capture goes |
| `-profiler-capture-frame-count <n>` | Stop after n frames instead of running unbounded |
| `-deepprofiling` | Instrument every managed call |

The in-code route above needs no flags and is what the resource file uses, precisely because it
does not depend on a spelling.

**Deep profiling changes the numbers it is measuring.** Every managed call gets a marker, which
can double the frame time and reorder which marker looks expensive. Use it to find *which* method,
never to find *how much*. The amount comes from a window with deep profiling off.

## Reading a capture without the Profiler window

The Editor can load a `.raw` file and hand you per-frame data directly:

```csharp
ProfilerDriver.LoadProfile(rawPath, false);                 // false = do not append
for (int f = ProfilerDriver.firstFrameIndex; f <= ProfilerDriver.lastFrameIndex; f++)
    using (var view = ProfilerDriver.GetRawFrameDataView(f, threadIndex: 0))
    {
        if (!view.valid) continue;
        // view.frameTimeMs · view.frameGpuTimeMs
        // int id = view.GetMarkerId("Camera.Render");
        // view.GetCounterValueAsLong(id)
        // view.sampleCount · view.GetSampleMarkerId(i) · view.GetSampleTimeMs(i)
    }
```

Thread index 0 is the main thread. Other threads are enumerated per frame, and how they are
indexed is one of the things worth confirming rather than assuming.

`ProfilerDriver` and `RawFrameDataView` are Editor-only and live in different namespaces —
`UnityEditorInternal` and the Editor profiling namespace. **Confirm both on your version** before
typing a `using` for them: this is the pair that moves most often, which is why the resource file
resolves them by reflection instead.

`PerfRawExtract.ToCsv(rawPath, csvPath, counterNames, markerNames)` in the resource file does the
whole loop and writes one row per frame: frame, frame time, GPU frame time, one column per counter
and one per marker (self time summed over that thread's samples).

**Every one of those types is resolved by reflection**, and the extract returns the member it could
not find instead of throwing. These are Editor-internal-facing APIs whose shapes move between
versions; a reflective loader degrades to a partial CSV and a message, where a direct reference
degrades to a project that will not compile. Confirm the members you need on your version by
reading what the extract reports on its first run.

## What the CSV is for

Three questions it answers that a window cannot:

1. **Which marker owns the spike.** Sort by frame time, take the worst frame, read across its
   marker columns. One of them is an order of magnitude above its median.
2. **Whether the spike is one marker or all of them.** All markers up proportionally is the whole
   frame being stalled from outside — a synchronous load, a GC, or the platform. One marker up is
   a thing you can go and fix.
3. **Whether the spike moved after the fix.** Extract both captures with the same column list and
   diff the worst-frame rows.

Once the marker is named, the comparison goes back to windows: they are repeatable and the capture
is not. `reference/compare.md` is the table that settles whether the fix worked.

## Gotchas

- **Captures are large.** Hundreds of frames run to tens of megabytes, and deep profiling
  multiplies that. Capture a named situation for a bounded frame count, never "the whole session",
  and delete the file when the CSV exists.
- **Loading a capture replaces what the Profiler window is holding.** Anything a human had on
  screen is gone. Say so before doing it on someone's machine.
- **A capture written by one editor version may not load in another.** The format is not a
  long-term archive; extract to CSV and keep that instead.
- **The capture is not the measurement.** It names a cause. The number that goes into a report
  still comes from a window taken with the profiler off, because an enabled profiler costs time of
  its own — which is why `run.profilerEnabled` is recorded in every window.
- **A driven run is still not a hardware benchmark.** Everything in this file describes where time
  went on this instrument, in this mode. Which instrument, and why they do not compare, is
  `reference/frame-windows.md`.
