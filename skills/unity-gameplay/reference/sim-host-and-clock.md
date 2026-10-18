# A fixed-step simulation on its own thread, and the clock it runs to

> Part of the `unity-gameplay` skill. The split itself (a rules assembly with
> `noEngineReferences`, commands in, state out, an accumulator in `Update`) is
> `unity-game-brief` → `reference/sim-presentation-split.md`; read that first. This page is the
> next layer, for a simulation that is **heavy on some ticks** and **judged against a real
> clock**: a tennis game whose 120 Hz rally sim solves a shot and predicts a trajectory on the
> tick a ball is struck, and whose player is graded on when they pressed. Code:
> `resources/SimClock.cs`, `resources/SimHost.cs`.

## When the accumulator in `Update` is no longer enough

| Sign | Why it matters |
|---|---|
| One tick costs tens of milliseconds (a solver, a prediction, a planner) | On the main thread that tick is a dropped frame, and the ball visibly stops at the moment of contact |
| Input is graded in milliseconds against the sim's timeline | Frame-time jitter in the accumulator becomes timing error the player is blamed for |
| Device timestamps arrive from another thread or another timeline | They have to be converted to match time, across pauses, by something every thread can read |

Otherwise stay with the accumulator: a thread buys these three and costs a buffer, a queue and a
race to think about.

## The clock: absolute, thread-safe, pause-aware

```
target tick = floor((HostNow − start − paused) × 120)      HostNow = Stopwatch, any thread
```

- **Absolute, never accumulated.** Summing per-frame `dt` drifts; recomputing from start time
  cannot. The sim thread steps until its tick reaches the target.
- **`Stopwatch`, not `Time.unscaledTimeAsDouble`.** Unity's clock may only be read on the main
  thread. The main thread calls `SyncExternalTime(Time.unscaledTimeAsDouble)` once a frame, and
  `ExternalToMatchUs` converts any timestamp on Unity's timeline through that offset.
- **A timestamp subtracts only the pauses that ended before it.** The first version subtracted the
  total pause time, so a press stamped before a pause, converted after it, came out early by the
  whole pause. A timestamp inside a pause is pinned to the pause's start (input is refused while
  paused anyway). Timers that must not run while paused (the gap before the next point) read
  `MatchSeconds`, not frame time.
- **120 Hz** divides 60 and 30, so every display rate interpolates evenly.

## The host: one queue in, one snapshot out, one event queue out

| Door | Direction | Rule |
|---|---|---|
| `Post(command)` | main → sim | Drained **before** each step, so a command lands on the current tick, and that tick is what a replay records as its ingest tick |
| `SwapInLatest()` | sim → main | **Exactly once per frame, from one place.** Everyone else reads `Current`. A second caller can swap the buffer the first one is still reading |
| `TryDequeueEvent` | sim → main | In order. An event can be up to 16 ticks (133 ms) older than `Current` |
| `Stop()` | main | Joins the thread. Only after it may anything read the sim directly, e.g. to serialise the replay |
| `Fault` | sim → main | The sim thread's exception. The main thread logs it and ends the match |

- **Triple buffer, swap under a lock.** The sim writes `back`, publishes by swapping `back` and
  `middle`; the main thread swaps `middle` and `front` when a new one is waiting. Neither side ever
  touches the buffer the other is using, and the lock is held for two reference swaps.
- **Cap the catch-up at 16 ticks per advance.** After a stall the sim catches up over a few
  advances instead of one long burst.
- **Events carry their own tick and position.** A contact event can arrive with a snapshot 100 ms
  newer than the contact. Dust, sound and the hit flash go where the event says, never where the
  snapshot's ball is now.
- **`threaded: false` runs the same code from `Pump()`**: tests and single-threaded platforms.

## What the presentation draws: RenderTick = clock − 1 tick

`RenderTicks = MatchTicks − 1`: one tick behind the clock, so there are always two states to
interpolate between. The ball keeps every substep of its newest tick (9 points at 8 substeps), and
the drawn ball is interpolated between those, so a bounce's corner is never cut off.

**Do not clamp the render tick to the snapshot's tick.** It is tempting when the sim lags: the drawn
time then never runs ahead of the data. But every cue the player times against (a ring that closes
at the ideal press, a filling timing bar) is drawn at render time, while the press is stamped on the
real clock. Clamping slows the cues whenever the sim lags and biases every press late. Keep the
render clock honest; when the snapshot is behind, extrapolate the ball in free flight from its
newest state, for at most 1.5 ticks and never below the ground (`unity-game-feel` →
`reference/sports-readability.md` §2).

## The first-tick stall, and the warmup race

Symptom: in the Editor the ball sat on the racket for 25 to 50 ms on the first few strikes, then
behaved. Cause: Mono JIT-compiles a method the first time it runs, and the solver and predictor
first run on the strike tick, so the sim fell behind the clock exactly there. IL2CPP has no JIT; it
is an Editor artefact, but it is the Editor where people judge feel.

Fix: before the match, run a throwaway bot-vs-bot match through the same code paths until a few
strikes have happened (about 40 ms), once per process. Then **`clock.Restart()`, then construct the
host.** The first attempt warmed up after the host existed: the thread was already stepping against
the old clock while the warmup ran, and the match started with a backlog. Measured after the fix:
maximum lag 1 tick over 22 s, zero frames lagging more than 2 ticks.

## The smoke gate: count frames with sim lag

`SwapInLatest` records `target − snapshot tick` on every unpaused frame. A play-mode smoke test of
an autoplayed match asserts `MaxLagTicks` and `LagFrames` (frames with lag > 2 ticks, allowed ≤ 3).
It caught the JIT stall above. It also failed once, 5 > 3, while another process was running
Blender and a second Editor on the same machine; the rerun on a quiet machine was green with
maximum lag 1. A background sim thread is the first thing CPU contention starves: rerun on a
quiet machine before calling it a regression, and measure on the target phone before release.

## Determinism that survives the thread

- **The thread changes when ticks run, never what they compute.** Same commands at the same ticks
  give the same bits; that is what a replay records (each human command with its ingest tick).
  Bots' commands are re-derived from the seed.
- **Only + − × ÷ and sqrt in the rules assemblies.** No `Math.Sin/Cos/Tan/Atan/Exp/Log/Pow`:
  directions are vectors and cross products, spin decay is `ω *= (1 − dt/τ)`. A test scans the
  rules folders (comments stripped) and fails on any call.
- **What "equal" means across runtimes.** The no-Editor runner (CoreCLR), the Editor (Mono) and
  IL2CPP on ARM64 (which may fuse multiply-adds) are held to the **discrete event log, exactly**,
  and on continuous state within 1e-6 m. Bit-identical is only promised within one build.
- **Random streams per purpose.** One seeded generator per stream (bot timing, bot choice, landing
  scatter, mishit); presentation has its own and the sim never reads it.
- **Hash the tuning into the replay header.** The balance file, the venue colliders and every
  geometry constant the rules read go into hashes in the header, so a replay against changed
  numbers fails loudly instead of diverging quietly.
- **The predictor and the sim share one function and one step.** A test asserts the ball's actual
  state equals the predicted trajectory on every tick in flight; animation and AI plan on the
  prediction.

## Running the rules tests without the Editor

The rules assemblies reference nothing from Unity, so their tests can run in about two seconds
from a terminal while an Editor is busy elsewhere. Every tool needed ships with the Editor:

| Need | Where it is |
|---|---|
| Runtime and compiler | `<Editor>/Unity.app/Contents/Resources/Scripting/NetCoreRuntime/dotnet` running `…/Scripting/DotNetSdkRoslyn/csc.dll` with `-langversion:9.0`; the Editor version comes from `ProjectSettings/ProjectVersion.txt`, so an upgrade moves the runner with it |
| Framework references | `…/NetCoreRuntime/shared/Microsoft.NETCore.App/<version>/*.dll`, plus a `<name>.runtimeconfig.json` naming that version |
| NUnit | `Library/PackageCache/com.unity.ext.nunit@*/net40/unity-custom/nunit.framework.dll`, the dll the Editor's runner loads. Exactly one cache folder, or fail: two means a stale cache |

The rules that keep its verdict honest:

- **One output assembly per asmdef, named exactly like it.** One merged assembly would let a test
  see `internal` members that `InternalsVisibleTo` refuses in the Editor.
- **Run NUnit's own runner** (`NUnitTestAssemblyRunner` with `DefaultTestAssemblyBuilder`) so
  `[TestCase]`, `[Values]` and `[TestCaseSource]` expand as NUnit expands them.
- **Exclude a test file only by rule, and print the reason every run:** its code, with comments
  stripped, names `UnityEngine`, `UnityEditor` or a non-rules namespace, or it uses a type declared
  in an excluded file. **A compile error is never "fixed" by excluding the file.**
- **Exit 0 green, 2 a test failed, 3 the harness failed** (no Editor, a compile error, zero tests
  ran), and a fresh output folder per run, so a dll from the last run cannot become today's verdict.
- **It is not Mono.** Maths comes from CoreCLR. A tolerance tighter than the two runtimes agree
  belongs to the Editor leg, which stays the arbiter. Long gates (a 10 000-case solver grid) are
  `[Explicit]` and run by filter; a 1 000-case version runs every time.

## Checklist

- [ ] Clock target from absolute time; Stopwatch on the sim thread; Unity time only on the main thread
- [ ] Timestamps convert subtracting only earlier pauses; a test pauses between press and conversion
- [ ] One `SwapInLatest` per frame; events handled with their own tick and position
- [ ] Render tick = clock − 1, not clamped to the snapshot
- [ ] Warmup → `Restart()` → host, in that order
- [ ] Smoke test asserts sim-lag frames; failures rerun on a quiet machine before being believed
- [ ] Banned-maths scan, per-stream seeds, tuning hashes in the replay header, prediction == sim test
