---
name: unity-play-harness
description: >-
  Design a Unity game so an agent can drive it and read it: a one-line GameProbe
  snapshot readable from a live Editor eval, a project command, Editor.log and
  PlayMode tests; named situations that boot straight into a moment and wait on a
  readiness set, never a sleep; journey tests that sample the probe into a timeline
  and assert invariants; and the method that turns a feel report into a repeatable
  test. Load for: "boot straight into the boss", "how would a test reach this
  screen", "comes in too fast", "disappears while it loads", "looks inconsistent",
  "I can't measure what the player felt". Verifying a fix or trusting a run is
  unity-debug; frame-time counters are unity-profiling.
---

# unity-play-harness — build the game so an agent can play it and read it

A game an agent cannot drive is a game that gets checked once, by hand, by whoever happens to be
at the keyboard. The work here is not testing; it is **making the game observable and reachable**
so that everything else — a verification, a measurement, an answer to a complaint — becomes cheap
enough to do on every change.

Four parts, each with a condition that says it is actually there:

| Part | Done when |
|---|---|
| **Probe** | `unity command eval 'return GameProbe.Json();'` returns one line carrying `state`, `pos`, `ready{}` and `allReady` |
| **Situations** | `Situations.Ids()` lists at least one id, and every one of them declares a readiness set |
| **Journeys** | one `[UnityTest]` writes `timeline.jsonl`, logs `[JOURNEY] … samples=N`, and `scripts/journey_report.py` prints `violations=0` |
| **Complaint → test** | the last feel report has a situation, a sampled quantity, a threshold with a source, and a before/after table |

None of it is instrumentation to delete afterwards. `GameProbe` and `Situations` ship with the
game, because the next complaint arrives after the debug component was removed.

---

## Readiness is a set, not a flag

The single most expensive shape of bug here, and the reason situations wait on a set:

> The visible ground, its collider and the hazard volume must become ready in the **same pass**.
> When they do not, the game looks finished and is not — the runner is drawn on a lane it can
> fall through, and the bug reproduces once in ten runs.

So: list every member the moment needs, make each one a predicate that is re-evaluated on every
poll, and wait until they are all true **with a timeout that names the ones still missing**.

```
[SITUATION] TIMEOUT approach-gate not ready after 15.0s: laneCollider, sentry
```

Never `yield return new WaitForSeconds(3f)`. A sleep that is long enough today is a flake next
month, and when it fails it tells you only that three seconds passed.

---

## Load what the situation needs

| The situation | Read |
|---|---|
| Designing the one-line snapshot; a value you need is not in it; reading it from eval, a command, the log or a test | `reference/probe-contract.md` |
| "boot straight into the boss"; "how would a test reach this screen"; a wait that times out | `reference/situations.md` |
| Writing the test that drives and samples; which invariants are worth asserting over a run | `reference/journeys.md` |
| Reading, comparing or handing over a recorded run | `reference/timeline-format.md` |
| A feel report with no number in it; deciding what stays a human judgement | `reference/complaint-to-test.md` |
| Frame-time counters, draw calls, GC, "did my change actually help" | `unity-profiling` |
| What to build first, where a threshold comes from, simulation/presentation split | `unity-game-brief` |
| A results file you are about to believe; exit codes; state leaking between runs | `unity-debug` → `reference/harness-trust.md` |
| Running the suite headless: `-runTests`, test filters, tests not found | `unity-debug` → `reference/cli-harness.md` |
| Driving a live Editor, `unity command`, Safe Mode | `unity-debug` → `reference/editor-control.md` |
| Needing to SEE the moment: windowed runs, settle time, reading the pixels | `unity-debug` → `reference/visual-checks.md` |

Copy `resources/GameProbe.cs`, `resources/Situations.cs` and `resources/JourneyRecorder.cs` into a
Runtime assembly, `resources/Editor/ProbeCommands.cs` into an Editor one, and start from
`templates/CourierSituations.cs` and `templates/JourneyTest.cs`.

---

## The probe contract in one screen

| Key | What it is |
|---|---|
| `schema` · `frame` · `t` · `ut` · `dt` · `timeScale` | Version, and the clock in both scales — a `timeScale` of 0 explains most "it froze" reports |
| `scene` · `situation` · `state` · `cam` | Where the game is, and which moment it was told to be in; a null `cam` explains a black screenshot |
| `pos` · `vel` · `speed` | The player, from `transform.position` and `Rigidbody.linearVelocity` |
| `ready{}` · `allReady` | Every readiness member, re-evaluated this frame |
| `counts{}` · `custom{}` | Named ints, and the handful of game-specific numbers a complaint could be about |
| `batch` · `playing` | Which instrument produced the line, and whether the game was running at all |

Two hooks put anything else in there, and both take a delegate rather than a value — a delegate
cannot go stale, a cached `bool` can:

```csharp
GameProbe.Ready("laneCollider", () => _lane != null && _lane.Collider.enabled);
GameProbe.Register("gateDist", () => Vector3.Distance(_runner.position, _gate.position));
```

**`state` comes from the game's own state machine**, through `SetState(() => _run.Phase.ToString())`.
A probe holding its own copy starts lying on exactly the day the two diverge — which is the day
something is broken.

---

## Discipline

- **The probe reads. It never writes.** No flag setting, no spawning, no state advancing. A probe
  that changes the run cannot be trusted about the run.
- **`Enter` calls the game's own transition.** Assigning `Phase = Approach` produces the right
  label with none of the work done, and readiness then passes on an empty moment.
- **Readiness members are predicates, re-evaluated on every poll** — never a `bool` set during a
  load that may have been cancelled. An empty set reads as *not* ready.
- **Wait on the set, with a timeout, on unscaled time.** A situation that sets `timeScale` to 0
  must still time out instead of hanging the suite.
- **Sample in `Update`.** `WaitForEndOfFrame` never resumes in batch mode, so a journey that
  samples there records everything windowed and nothing headless.
- **Assert transitions and bounds, not absolute values.** `speed < 12 within 2 units of the gate`
  survives the next tuning pass; `speed == 9.8` fails it. Print the absolute numbers underneath.
- **Assert the sample count first.** `samples=0` makes every other assertion iterate an empty list
  and pass — a green test that checked nothing.
- **Delete the journey directory before every run.** A half-overwritten timeline next to last
  run's screenshots reads as one run and describes neither.
- **The human keeps the feel verdict.** The harness proves a number moved where it was aimed; it
  cannot prove the game feels better, so the report back ends with a question.
- **Ship the probe, gate the logging.** `GameProbe` and `Situations` stay in a Runtime assembly;
  `GameProbeReporter` disables itself unless `Debug.isDebugBuild || Application.isEditor`, so a
  release player carries the probe and prints nothing; the commands are Editor-only.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Running Unity, exit codes, screenshots, proving the harness is honest | `unity-debug` |
| Frame-time counters, draw calls, GC, a before/after table of numbers | `unity-profiling` |
| The brief, the constraints, which interaction to build first | `unity-game-brief` |
| Installing editors, licences, templates, the CLI's own surface | `unity-cli` |
| Assembly definitions, folder layout, which Editor version the project is pinned to | `unity-new-project` |
| A collision or trigger that never fires, a raycast that misses | `unity-physics-3d` |
| Building the UI rather than reaching a screen of it | `unity-game-ui` |
