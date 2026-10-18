# Which phase allocates: GC.Alloc per Update and LateUpdate

> Part of the `unity-profiling` skill. Enter when `Memory/GC Allocated In Frame` has a non-zero
> median (`reference/where-the-time-goes.md` §2) and the next question is whose code it is. Worked
> setting: a tennis game whose simulation and input run in `Update` and whose presentation (ball,
> characters, camera, effects, HUD) runs in `LateUpdate`.

## The instrument that reads zero

`System.GC.GetAllocatedBytesForCurrentThread()` is the obvious tool: read it before and after a
phase, subtract. **Under Unity's Mono it is not implemented and returns 0 every time.** A test built
on it passes on every run and measures nothing. The tennis game's first probe used it, and the
self-calibration below is what exposed it.

## The instrument that works

The Profiler emits a `GC.Alloc` sample for every managed allocation. A `Recorder` on that marker,
filtered to the main thread, counts them, and can be switched on and off within a frame:

```csharp
var rec = UnityEngine.Profiling.Recorder.Get("GC.Alloc");
rec.FilterToCurrentThread();
rec.enabled = true;   /* the code being measured */   rec.enabled = false;
// next frame: rec.sampleBlockCount = allocation calls inside the window last frame
```

`resources/GcAllocProbe.cs` (with `GcAllocProbeOpener.cs`) packages it: an opener at execution
order −32000 and a closer at +32000 bracket one phase per frame, alternating, Update on odd frames
and LateUpdate on even ones. Test coroutines run between the two phases and are outside both
windows. It counts allocation **calls**, not bytes; for bytes, the frame-wide counter is still the
one in `reference/counters.md`.

## Calibrate before believing a zero

Have the probe allocate 64 bytes inside its own next window and read the count back: it must be at
least 1. Assert it in the test (`GC.Alloc recorder does not see allocations: the measurement is
blind`). Only then is "0 frames with allocation" a result. This is the same discipline as the
audio spectrum test's 17 kHz calibration tone: every gate first proves it can fail.

## What the tennis game found

| Phase | Before | After | Where it came from |
|---|---|---|---|
| LateUpdate (presentation) | 419 of 419 frames | 3 to 4 of about 420 frames (two measurements: 4/418 and 3/420) | Strings built every frame in the HUD, effects created on demand. Fixed by formatting only on change and building every effect into pools at match start |
| Update (simulation events, autoplay, Editor) | about 10 KB a frame | unchanged, out of scope | Event objects from the match layer; an owner's decision, recorded |

The test asserts LateUpdate frames with an allocation ≤ 5% of LateUpdate frames, with the
calibration first. Splitting by phase is what made the 10 KB a frame someone else's line item
rather than the presentation's failure.

## Traps

- **A Recorder reports the previous frame.** Read at the start of the next frame, not at the end
  of the window.
- **Two windows in one frame on one Recorder merge.** Alternate frames instead.
- **The Editor allocates too.** Inspector repaint, the Game view, logging. Measure with the
  inspectors closed, and compare Editor with Editor only (`reference/frame-hygiene.md`).
- **`Debug.Log` allocates.** Log once at the end of the window, not per frame.
