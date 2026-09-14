---
name: unity-debug
description: >-
  Verify and diagnose a Unity game the agent cannot see: read Editor.log,
  drive Unity from the CLI or a live Editor, and take screenshots it reads
  itself. Use whenever a change needs verifying in the running game or
  something misbehaves at runtime: "the player won't move", "nothing happens
  when I press Play", "verify the fix works", "the UI is shaking /
  flickering", "why does this only break on device", "exit 0 but no results
  file", "which test failed", "the tests are green but nothing was verified".
  Above all, prove the harness is telling the truth before believing a number
  it prints. Installing editors, licences and the CLI's own surface are
  unity-cli.
---

# unity-debug — verify it yourself, and check the instrument first

The agent cannot see the Game view. **Never iterate via "add a log → ask for a screenshot →
guess".** Unity will run itself, report to a log, and hand you PNGs you can read.

There is one rule above all the technique, and it is the one that costs the most when broken:

> **A number is worthless until you know the run that produced it happened.**
> Exit code 0 does not mean Unity started. A results file does not mean it is *this* run's results
> file. A measurement does not mean the thing measured moved.

Four consecutive "6/6 passed" reports once came from a 36-minute-old XML while Unity failed to
start every time. Start at `reference/harness-trust.md` and the guard is one line of `rm`.

---

## The four loops

**0 · Live-Editor loop** — fastest of all when the project has the Pipeline package: a running
Editor answers `unity command` without recompiling or reloading the domain. Everything below
pays a cold start; this one does not. → `reference/editor-control.md`

**1 · Log loop** — fastest when a human is at the keyboard. Instrument with a grep-able prefix, ask
for one Play, read Editor.log. → `reference/log-triage.md`

**2 · CLI loop** — no human needed. `-batchmode` for compile and logic, ~20 s warm.
→ `reference/cli-harness.md`

**3 · Visual loop** — windowed `-runTests`, walk the whole flow, drop numbered PNGs, read them.
Catches everything assertions cannot: overlap, clipping, contrast, wrong aspect.
→ `reference/visual-checks.md`

Batchmode **cannot** screenshot (no end of frame). Windowed can, and IMGUI shows up in the capture.
A live Editor can too, via `unity command screenshot` — which is loop 0's answer to loop 3.

---

## Load what the situation needs

| The situation | Read |
|---|---|
| About to trust a test result, or something reads as impossible | `reference/harness-trust.md` |
| A run's verdict: which test failed, `failed=0` that checked nothing, state leaking between runs | `reference/test-verdicts.md` |
| Running Unity headless; tests not found; asmdef errors | `reference/cli-harness.md` |
| Iterating more than twice; want to poke a live Editor; `unity command` won't connect; Safe Mode | `reference/editor-control.md` |
| Need to SEE a screen; layout, contrast or cropping suspected | `reference/visual-checks.md` |
| "It shakes / flickers / shimmers"; anything temporal | `reference/motion-and-timing.md` |
| Runtime misbehaviour with a human pressing Play; device triage | `reference/log-triage.md` |
| Phantom collisions, invisible objects, hitboxes, import weirdness | `reference/unity-gotchas.md` |
| The game cannot boot into the moment under test; nothing readable says what state it is in; a feel report with nothing to measure | skill `unity-play-harness` |
| "It is slow", hitches, draw calls or GC — numbers you can compare across a change | skill `unity-profiling` |
| A collision or trigger that never fires, tunnelling, a raycast that misses | skill `unity-physics-3d` |
| Post-processing set but not visible; reviewing a renderer feature | skill `unity-render-urp` |
| A Scene-view or camera PNG for a before/after comparison, outside a test run | skill `unity-urp-migration` → `resources/SceneCapture.cs` |
| "Find / where is / what references X" — one query over project assets or the loaded scenes, rather than a script | skill `unity-search` |
| Installing editors, licences, templates, MCP wiring, CI invocation | skill `unity-cli` |
| An agent that will not move or path around something | skill `unity-navigation` |
| Building the game's UI rather than debugging it | skill `unity-game-ui` |

`resources/DevDebug.cs` is a project-agnostic drop-in probe. Copy into `Assets/`, attach,
**delete when finished.** A permanent, contract-shaped probe that ships with the game and every run
can read is a different thing — that one is `unity-play-harness`.

---

## Discipline

- **List, never recall.** Command names, template ids and package ids are defined by the Editor
  and the registry, not by your memory of them. `unity command --format json`, `unity templates
  list`, `Client.SearchAll()` — one call is cheaper than one wrong guess.
- **Delete the results file before every run.** A missing file is an obvious failure; a stale one
  is a silent lie.
- **Never pipe a test driver into `tail` or `head`.** The shell then reports the *pipe's* exit
  status, so a driver that printed `exit=2 … failed="2"` comes back to you as "exited with code 0".
- **Read `inconclusive=` next to `failed=`.** `Assert.Inconclusive` leaves `failed="0"`, so a whole
  test class can skip itself — usually exactly when the assets it guards are missing — and the run
  still reads green. → `reference/test-verdicts.md`.
- **Reset PlayerPrefs and persistent data in `[SetUp]`.** They survive between PlayMode runs, which
  is how a suite passes on CI and fails on the developer's machine, and how "the same test" produces
  two different screenshots.
- **Log the state next to every screenshot** (`[SHOT] 04_countdown state=Countdown`) so a capture
  that photographed the wrong moment cannot pass unnoticed.
- **Print the numbers a test asserts on.** A green tick says a test passed; a logged
  `world width=0.50 laneSpacing=1.30` says why, and keeps saying it after the next change.
- **Median and worst, never just worst** — one spike and a constant vibration are different faults.
- **When a measurement contradicts the code, suspect the measurement.** Dump the pixels. Take a
  whole-frame diff. The constants are rarely the liar.
- **Re-run before calling a failure a regression.** Timing-sensitive tests exist, and a graphics
  change can tip one over without touching gameplay. Say so plainly rather than inventing a cause.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Installing editors, licences, templates, CI invocation | `unity-cli` |
| Building or signing an artifact | `unity-android-release` · `unity-web-release` |
| A collision or trigger that never fires | `unity-physics-3d` |
| An agent that will not move | `unity-navigation` |
| Post-processing that will not appear | `unity-render-urp` |
| Designing the UI rather than verifying it | `unity-game-ui` |
| Building the game so an agent can drive and read it: probes, named situations, journey tests | `unity-play-harness` |
| Frame-time windows, profiler counters, a before/after table | `unity-profiling` |
| Deciding what to build first: the brief, the constraints, the first interaction | `unity-game-brief` |
| "Find / where is / what references X" answered as a Unity Search query rather than a scripted audit | `unity-search` |

## Running PlayMode tests edits your project

Side effects that all get committed if nobody looks:

> **The test framework flips `runInBackground` to 1 in `ProjectSettings.asset` and does not put
> it back.** A `git status` after a green test run is not clean, and the diff has nothing to do
> with what you were testing.

> **Restore that one LINE, never the whole file.** `git checkout -- ProjectSettings/ProjectSettings.asset`
> is the obvious cleanup and it is destructive: it silently discards any Player Settings written
> since the last commit — a setup step's target SDK level and app icons, say — which then have to
> be regenerated. Restore surgically instead — and note that any *other* script running the suite
> (a release build that tests before packaging) needs the same restore:
>
> ```bash
> grep -q "^  runInBackground: 1$" ProjectSettings/ProjectSettings.asset && \
>   sed -i '' 's/^  runInBackground: 1$/  runInBackground: 0/' ProjectSettings/ProjectSettings.asset
> ```
>
> (BSD `sed` on macOS needs the empty `''` after `-i`; GNU `sed` takes `-i` alone.)

> **A crashed run leaves files in the project.** `Assets/InitTestScene<guid>.unity` plus its `.meta`
> (the runner's temp scene) and a `mono_crash.mem.<pid>.<n>.blob` dump in the project root — both
> swept up by the next `git add -A`. Ignore `Assets/InitTestScene*` and `mono_crash.*`.

> **Killing an Editor before a test run leaves `Temp/` in a state that aborts the next one** with
> *"Scripts have compiler errors"* and **no `error CS` line in the log** — the compiler never ran.
> → `reference/editor-control.md`.

So the run protocol is: delete the results file, run, **then `git status`** — and revert what the
harness changed before reporting anything as done.

## Cleanup before handing back a "clean" build

- Remove `[RUN]`/`[DBG]` logs and per-frame dumps; remove `DevDebug.cs` and detach it.
- Remove on-screen debug panels and debug-only serialized fields.
- Keep the **fixes** found while debugging; delete only the **instrumentation**.
- Leave the harness in a green, honestly-verified state — and say which parts you could not verify.
