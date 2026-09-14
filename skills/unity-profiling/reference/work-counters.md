# Work counters: what the game was asked to do, and what it threw away

> Part of the `unity-profiling` skill. Frame time says a frame was slow. It never says the pool
> built the same three pickups four times because a selector kept changing its mind.

Rendering counters describe what reached the GPU. Work counters describe what the game *decided*,
which is the thing you are about to change. `resources/WorkCounters.cs` is four integers per
system and three call sites.

## The four numbers

| Number | Incremented where | Reads as |
|---|---|---|
| `scheduled` | The decision point said "do this" | Demand |
| `completed` | The work finished **and something used the result** | Useful throughput |
| `discarded` | The work was cancelled, superseded, or finished into a bin | Churn |
| `inFlight` | Derived: `scheduled − completed − discarded` | Queue depth |

Plus `bytesScheduled` and `bytesCompleted`, when the system knows its own sizes — a streamer that
moves 40 MB to show 4 MB has a different problem from one that is merely slow.

Read them together:

- **`discarded` climbing while `scheduled` climbs** — churn. The frames cost real time and the
  player sees none of it. This is the shape that hides behind "it hitches sometimes".
- **`inFlight` high and flat** — a queue that never drains. Adding threads makes it worse; the
  decision point is producing faster than anything can consume.
- **`completed` flat while `scheduled` climbs** — work is being ordered and nothing is landing.
  Usually a predicate that has stopped being true.
- **`discarded / scheduled` as a ratio is unstable at low counts.** Three discards out of four is
  not worse than two hundred out of a thousand. Compare the deltas across a window, which is what
  `scripts/compare_windows.py` does, not the ratio.

## Call them at the decision point, not inside the worker

```csharp
var pool = WorkCounter.Get("pickup-pool");

// where the policy chooses:
pool.Scheduled(estimatedBytes);

// where the result is handed to the game:
pool.Completed(actualBytes);

// where the result is dropped, cancelled or superseded — count it even when it was cheap:
pool.Discarded();
```

Counting inside the worker tells you how long the worker takes, which a marker already tells you.
Counting at the decision point tells you how often the policy changed its mind, which nothing else
does. Main thread only: increment these from a job and the totals go wrong quietly.

`FrameSampler` picks up every registered counter and writes three cumulative entries per system —
`Game/<system>.scheduled`, `.completed`, `.discarded` — with `start`, `end` and `delta`. Only the
delta belongs to the window.

## Reset at the boundary you are measuring

- **`WorkCounter.ResetAll()` in a test `[SetUp]`** and on entering a situation, so a window
  measures one run rather than the whole session.
- **Do not reset inside the window.** The sampler captures `start` on the first sampled frame and
  `end` on the last; resetting between those makes the delta negative-shaped nonsense.
- **Keep the system name stable.** It becomes a JSON key. A renamed system compares as
  `missing-left` against yesterday's baseline, which looks like it vanished rather than moved.

## The courier run worked example

The complaint is "it hitches when the third pickup spawns in the hazard lane". The window says
`ft_p95` 12.90 ms against `ft_med` 8.31 — unevenness, not a uniformly heavy frame — with
`hitches=2` and:

```
Game/pickup-pool.scheduled  231
Game/pickup-pool.completed   17
Game/pickup-pool.discarded  214
```

Seventeen pickups were used. Two hundred and thirty-one were ordered. Draw calls and triangles are
flat between runs, so this is not a rendering problem at all: the lane selector sits on a 1.3-unit
lane boundary and flips between neighbouring lanes several times a second, and each flip cancels
the pickup set that was being built for the lane it just left.

Three fixes, in the order worth trying:

1. **Hysteresis.** Enter the new lane at 0.2 units past the boundary, leave it only 0.2 units back
   the other way. A dead band costs one float and removes the oscillation outright.
2. **Commit by distance or time.** Once a lane is chosen, hold it for a minimum distance travelled
   or a minimum unscaled time, whichever the game's feel tolerates. This is the right tool when
   the input itself is noisy rather than the boundary.
3. **Finish short work before switching.** When a unit of work is shorter than the time between
   two decisions, cancelling it is strictly more expensive than letting it complete. Let it land
   and discard the *result* if it is no longer wanted — `completed` then counts honestly and the
   cost shows up as throughput rather than churn.

After the 0.2-unit dead band, the same situation with the same seed:

```
Game/pickup-pool.scheduled   25
Game/pickup-pool.completed   18
Game/pickup-pool.discarded    7      ← three digits to one
frameTime p95 12.90 → 9.10 ms, hitches 2 → 0
```

Two numbers moved together and the change is one parameter. That is a result worth reporting; a
frame-time improvement on its own would not have said *why*.

## Making them visible while you play

Work counters are cheap enough to read live. Two routes, neither of which needs a window:

```csharp
Debug.Log(WorkCounter.Report());   // one "[WORK] <system> scheduled=… completed=… discarded=…" line each
```

and, where the game already exposes a one-line state snapshot for an agent to read, register the
counts into it so they appear in every sample of a journey rather than only at the end. Building
that snapshot and the named situations that drive it is `unity-play-harness` →
`reference/probe-contract.md`.

Define `PERF_PROFILING_CORE` to also mirror the totals into `ProfilerCounterValue<long>`, which
puts them in the Profiler window next to the built-in counters. That needs the profiling-core
package; without the define the file has no package dependency at all. Confirm the package is
present in `Packages/manifest.json` before adding the define, and prove the mirror with a value
you cannot mistake for real data — `reference/counters.md` has the round trip.
