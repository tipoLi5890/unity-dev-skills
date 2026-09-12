# Trust the harness before you trust its numbers

The most expensive failures in an autonomous loop are not wrong fixes. They are **right
conclusions drawn from an instrument that was lying**, because those cost you every decision made
downstream before anyone notices.

Two real ones:

- Unity failed to start for **four consecutive runs**. Each time the command exited 0, and each
  time `grep total=` on the results XML printed `total="6" passed="6"`. That XML was **36 minutes
  old**. Four rounds of edits were reported as verified and had never been compiled.
- A frame-to-frame pixel measurement said a HUD panel was churning **32% per frame**. Three rounds
  went into finding what was vibrating. Nothing was: `CaptureScreenshotAsTexture()` had been called
  without waiting for end of frame, so it was returning the framebuffer mid-draw and the region
  flipped between "UI drawn" and "UI not yet drawn". With the wait added, the same probe read
  **0.00%**.

---

## Before reading any output, prove the run happened

Never `grep` a results file without checking it belongs to this run.

```bash
UNITY="/Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/MacOS/Unity"
rm -f /tmp/results.xml                      # so a stale file cannot be mistaken for a fresh one
"$UNITY" -projectPath "$PWD" -runTests -testPlatform PlayMode \
  -testResults /tmp/results.xml -logFile /tmp/tests.log; echo "EXIT=$?"
echo "log $(wc -l < /tmp/tests.log) lines"  # a real run is thousands; a failed start is ~45
```

Three independent signals, and you want all three:

| Signal | Healthy | Failed to start |
|---|---|---|
| exit code | 0 (pass) or 2 (test failure) | 0 — **it lies** |
| log length | thousands of lines | ~45, ending at `[Package Manager] Server process was shutdown` |
| results file | exists, mtime = now | missing, or hours old |

**Deleting the results file first is the cheapest guard you will ever write.** With it, a failed
start is an obvious missing file instead of a silently stale success.

Two refinements:

- **A long log is not proof of a run either.** An 866-line log with exit 0, no results file and no
  `error CS` line turned out to be a native crash during startup, with a 0-byte `Temp/UnityLockfile`
  left behind and no editor process holding it. `tail -30` on the log showed the native stack.
- **Check that the exit code you are reading is your driver's.** A pipeline (`./run-tests.sh | tail`)
  reports the pipe's status, and a driver can also die before invoking Unity at all.

Both, with log-length thresholds to calibrate on your own project, are in `test-verdicts.md`.

## Why Unity refuses to start

Almost always a stale `Temp/UnityLockfile` — left behind when a previous run was killed. Every
subsequent run then exits immediately.

```bash
ls Temp/UnityLockfile 2>/dev/null && echo "locked"
pgrep -fl "Contents/MacOS/Unity( -|$)"   # the EDITOR binary, bare or Hub-launched, not its helpers
```

`pgrep -f "Hub/Editor/<version>"` matches `VBCSCompiler.dll` and `Unity.Licensing.Client` too, and
both live for days — seeing output from that pattern does **not** mean an editor is running. Match
the editor binary itself. If nothing holds it, the lockfile is a corpse; delete it and re-run.

---

## Instruments that create the artefact they measure

| Instrument | The lie | The fix |
|---|---|---|
| `CaptureScreenshotAsTexture()` after `yield return null` | Reads mid-draw; regions flip between drawn and not-drawn | `yield return new WaitForEndOfFrame()` first — required outright once MSAA is on, because the colour target only resolves then |
| Same, under `-batchmode` | There is no end of frame; it throws | Run windowed for anything visual |
| A region computed from `Screen.width` | Silently points somewhere else if the capture is a different size | Log `tex.width x tex.height` beside `Screen.width x Screen.height`, and **dump the cropped pixels** before believing a number about them |
| Per-frame GPU readback in a loop | Frames sampled ~0.5 s apart, so a once-a-second counter changes between nearly every sample | Report the **median**, not just the worst (below) |

## Retries must report flakiness, not launder it

A retry flag is only honest if the first result survives it. The rule to hold, whatever runner
you use:

- The **first** run's report is never overwritten. A rerun writes a *second* artefact.
- A test that failed then passed is reported as **flaky**, not as passed.
- A run with no verdict at all (the Editor died, the file was never written) is **not** a
  retry candidate — it is the harness failing, and re-running hides that.

A suite that silently reruns until green is indistinguishable from a suite with no assertions.

## Median versus worst

One number cannot tell a spike from a vibration. Report both:

- worst high, median ≈ 0 → a **one-off event** inside the region (a clock digit ticking, a coin
  collected). Not a defect.
- worst high, median high → something is genuinely moving every frame.

Real readings from the same probe, before and after the capture fix:

```
clock panel, icon side : median 32.18%  worst 33.61%   ← instrument broken
clock panel, icon side : median  0.00%  worst  0.00%   ← same code, correct capture
clock digit only       : median  0.90%  worst  0.99%   ← the digit ticking. Correct behaviour.
```

## The same doubt applies to CONFIGURATION, not just to measurements

"I changed that setting" means a file on disk differs. It does not mean the project loads that file.

A rendering fault was traced to the render pipeline. The project had
`Assets/Settings/Mobile_RPAsset.asset` and `PC_RPAsset.asset`; `QualitySettings` said the platform
used quality level 0, which was named **"Mobile"**. Every name agreed. The setting was changed, a
build shipped, a human installed it — and nothing had changed, because **neither asset was in use**.
Both quality levels had `renderPipeline: none`, so the pipeline fell through to
`GraphicsSettings.m_CustomRenderPipeline`, which pointed at a third asset with a default name loose
in the project root. The two well-named ones were dormant decoys.

Before changing any setting you intend to draw a conclusion from, **follow the reference chain from
the thing that actually runs, and print what you find**:

```bash
grep -n "m_CustomRenderPipeline" ProjectSettings/GraphicsSettings.asset   # the real asset's guid
grep -nE "name:|renderPipeline:" ProjectSettings/QualitySettings.asset    # `none` = no override
find . -name "*.meta" -not -path "./Library/*" -exec grep -l "^guid: <GUID>" {} \;
```

The same trap exists for renderers, volume profiles, input settings and quality tiers, and it is
worse in a project grown from a template: templates leave behind plausibly-named assets that
nothing references. **A file with the right name is not evidence. A reference chain is.**

## When a number disagrees with the code, suspect the number

The code says a panel is drawn at a fixed rect from constants. The probe says it moves. One of
those is wrong, and it is almost never the constants. Escalate like this:

1. **Log the instrument's own dimensions** — capture size vs `Screen` size.
2. **Dump the pixels you are measuring** to a PNG and look at them. A crop "of the clock panel"
   can turn out to contain the pause button and the roadside scenery.
3. **Stop doing region arithmetic** — take a whole-frame difference image instead. Amplify it
   (`|a-b| * 4`) and view it. It answers *what moves* with no coordinates to get wrong, and it is
   how the real culprit — texture aliasing across the entire track — was finally found.

---

## Sources of non-determinism to neutralise in tests

- **Simulated input devices inject real events.** A microphone-driven input running in
  editor-simulated mode listens to the machine's microphone, so ambient noise produces genuine
  input events. Harmless while a screen ignores most input; fatal once a screen advances on *any*
  input. Disable the input manager at the top of tests that are about layout or motion:

  ```csharp
  var sensor = Object.FindFirstObjectByType<SensorInputManager>();
  if (sensor != null) sensor.enabled = false;
  ```

- **PlayerPrefs and `persistentDataPath` survive between runs**, so a test that assumes a fresh
  install passes on CI and fails on a developer's machine — and a screenshot run photographs
  whatever state the previous run left behind. Delete the keys and files the test depends on in
  `[SetUp]`, and assert the *transition* rather than an absolute value. → `test-verdicts.md`.

- **Rendering settings change frame timing.** Enabling 4× MSAA lengthened frames enough to tip a
  timing-sensitive collision test from passing to failing; it passed again on re-run. If a
  gameplay test starts flaking right after a *graphics* change, that is why. Re-run before
  investigating, and say plainly that the test is timing-sensitive rather than reporting a
  regression that is not there.

- **Animation settle time.** See `visual-checks.md`: a screenshot taken mid-transition is not a
  layout bug, and a wait long enough for menus will step straight over a transient state.
