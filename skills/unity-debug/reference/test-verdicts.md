# Does the test run's verdict mean anything?

Two separate questions, and a suite can fail either one while printing a green line:

1. **Did this run happen?** — `harness-trust.md` owns that: delete the results file, then judge by
   the file, not by the exit code.
2. **Did the checks inside it actually run?** — this file. `failed="0"` is a much weaker claim
   than it looks.

---

## The driver can lie before Unity is even involved

**A pipeline reports the exit status of the last command, not of your driver.** Running
`./run-tests.sh edit 2>&1 | tail -30` reports *exited with code 0* even when the driver's own
output, further up, says `exit=1 … no results` (Unity aborted — another Editor held the project)
or `exit=2 … total="52" passed="50" failed="2"`. The `0` is `tail`'s.

```bash
./run-tests.sh edit 2>&1 | tail -30          # ← the status you get back is tail's, not yours
set -o pipefail                              # or read ${PIPESTATUS[0]} (zsh: $pipestatus[1])
```

**And the driver can die before it reaches Unity.** On macOS `/bin/bash` is 3.2, so bash-4
expansions are runtime errors: `run-tests.sh: line 15: /tmp/out/${1,,}.xml: bad substitution`
exits the script without ever invoking Unity — and `bash -n` does not catch it, because it is an
expansion-time failure, not a syntax one. Lowercase portably instead:

```bash
lower="$(printf %s "$1" | tr '[:upper:]' '[:lower:]')"
```

Either way the real guard is the same one: the results file is the verdict, the exit code is a hint.

## Raw `Unity -runTests` exit codes

The `unity` CLI's codes (`cli-harness.md`) are richer, but a script calling the editor binary
directly still gets a usable signal:

| Code | Results XML | Means |
|---|---|---|
| `0` | present, `failed="0"` | Ran, all passed |
| `2` | present, `failed="N"` | Ran, some failed — **a real verdict, do not retry** |
| `1` (EditMode leg) | **absent** | Never got as far as running: compile error in a test assembly |
| `3` (PlayMode leg) | **absent** | Same, on the PlayMode leg |
| `0` | absent or stale | Unity never started — stale lockfile, licence, another Editor |

So `0` appears at both ends of the range. Test for the file first; only then read the code.

> **A compile error in *either* test assembly kills *both* legs.** All test assemblies compile
> before either platform runs, so a typo in a PlayMode test file makes the EditMode run produce no
> results at all. When the XML is missing: `grep -E "error CS|Aborting" "$log" | sort -u | head -20`.

## Log length is the cheapest proof — and it has a blind spot

Rule of thumb (calibrate on your own project): **under ~100 lines** means Unity never started (a
stale lockfile produces ~45 lines and exit 0); **a few hundred** means it started and died
compiling; **thousands** means a real run. Print it next to the code:
`echo "exit=$rc log=$(wc -l < "$log") lines"`.

The blind spot, for example: an **866-line** log, exit 0, no results file, no `error CS`, no
licence complaint, and `pgrep -fl "Contents/MacOS/Unity( -|$)"` showing no editor running — yet
a **0-byte `Temp/UnityLockfile`** on disk. `tail -30` on the log shows a native crash in a worker
thread during startup, nothing to do with project code; `rm -f Temp/UnityLockfile` and the rerun
goes straight to green. Diagnosis order, cheapest first:

```bash
wc -l "$log"                                        # started at all?
grep -nE "error CS|No valid Unity|another instance|Lockfile|licen[cs]e" "$log"
pgrep -fl "Contents/MacOS/Unity( -|$)"              # someone actually holding it?
ls -l Temp/UnityLockfile                            # a corpse if nothing is running
tail -30 "$log"                                     # native stack, before blaming the code
```

## Which test failed: the grep that can never match

A harness that reports `failed="1"` and then lists nothing is usually running this:

```bash
grep -oE '<test-case[^>]*result="Failed"[^>]*name="[^"]+"' "$xml"     # ✗ never matches
```

NUnit3 XML emits the attributes in the order `id`, `name`, `fullname`,
… with `result=` much later, so the pattern cannot match and the run is red with no name attached.
Working forms:

```bash
grep -oE '<test-case [^>]*>' "$xml" | grep 'result="Failed"' \
  | sed -E 's/.*fullname="([^"]+)".*/FAILED: \1/'
```

```python
# python3 fails.py /tmp/editmode.xml — name, message and stack for anything not Passed
import sys, xml.etree.ElementTree as ET
for c in ET.parse(sys.argv[1]).getroot().iter('test-case'):
    if c.get('result') != 'Passed':
        print(c.get('result'), c.get('fullname'))
        for tag in ('failure/message', 'failure/stack-trace'):
            n = c.find(tag)
            if n is not None and n.text:
                print('   ', n.text.strip()[:600])
```

That turns `total="52" passed="50" failed="2"` into two lines naming the tests and their messages
in one step — the console tail carries totals only, never a cause.

> **Read the path the runner passed to `-testResults`; do not glob for it.** `R=$(ls -t
> /tmp/out/*edit*results*.xml)` can produce `zsh: no matches found:` — zsh aborts the whole command
> line on an unmatched glob, `2>/dev/null` does not help, and the next command receives an empty
> argument and raises `FileNotFoundError: ''`.

## `failed="0"` is not "the checks ran"

Four ways a suite goes green having verified nothing. Three of them are invisible to a driver that
greps `failed=`:

1. **A stale results file** — the run never happened. → `harness-trust.md`.
2. **`Assert.Inconclusive` keeps `failed="0"`.** Tests over generated content guard themselves
   (`if (catalogAsset == null) Assert.Inconclusive("run the scaffold step first");`). NUnit records
   that as `inconclusive="2"` while `failed=` stays 0, so a whole class can skip itself — exactly
   when the assets it protects are missing — and the suite still reads green. **Print
   `inconclusive=` next to `passed=`/`failed=` and treat non-zero as "a gate did not run".**
   Still prefer `Assert.Inconclusive` to an early `return`: a silent return is indistinguishable
   from a pass in the XML.
3. **`LogAssert.ignoreFailingMessages = true`** (see the Metal Toolchain entry in
   `unity-gotchas.md` for why a suite ends up with it) silences the *game's* `Debug.LogError` too.
   After that flag, "no error in the log" is not a pass condition — every expectation needs an
   explicit `Assert`. Keep it out of EditMode suites so those still redden on unexpected errors.
4. **Screenshots that were never taken.** A capture helper correctly bails out under `-batchmode`,
   so a batch run passes and produces zero PNGs. → `visual-checks.md`.

**The total includes tests that come with packages.** For example, an EditMode suite reports
`total="85" passed="85"` while the project owns 84 cases — the extra is a documentation-example
test stub from Addressables, which arrives as a dependency of the localization package. Any CI gate
pinned to an exact case count breaks the next time a package is added; that jump is not a bug.

## What a run leaves behind

| Left behind | Why it matters |
|---|---|
| `runInBackground: 1` in `ProjectSettings/ProjectSettings.asset` (every PlayMode run, not just a crashed one) | Committed by accident; see `SKILL.md` for the one-line restore and why a whole-file checkout is worse |
| `Assets/InitTestScene<guid>.unity` (+ its `.meta`) | The runner's temp scene, not cleaned up when it dies mid-run |
| `mono_crash.mem.<pid>.<n>.blob` in the project root | A crash dump `git add -A` will happily commit |
| `Temp/UnityLockfile` | Every later run exits instantly against it |

The middle two are `git add -A` bait: once committed, they come back out only with
`git rm --cached` and an amended commit. In any project whose tests run from a script, ignore
`Assets/InitTestScene*` and `mono_crash.*` up front.

---

## State that survives between runs

The Editor's `PlayerPrefs`, `Application.persistentDataPath` and static fields are shared by every
PlayMode run *and* every manual Play session. Two failures from that:

- A test that asserts an absolute value after one input step fails with `Expected: 1 But was: 2`,
  because profile data written by earlier runs is still on disk.
- The same test produces a **different lobby screenshot on the second run** when a UI display
  mode lives in `PlayerPrefs` and the previous run cycled it in the settings screen — the
  "default" state is never actually photographed.

Use both fixes:

```csharp
[SetUp] public void SetUp() {
    PlayerPrefs.DeleteKey("<hud_mode>");         // every pref the test reads or photographs
    PlayerPrefs.DeleteKey("<hud_visible>");
}
// and assert the transition, not the absolute value:
int before = ui.SelectedIndex;
PressRight();
Assert.AreEqual((before + 1) % ui.OptionCount, ui.SelectedIndex);
```

Without this, a suite passes on CI and fails on the developer's machine, and screenshots are not
comparable between runs. The same leak reaches humans: a preference written during earlier manual
play can hide a shipped fix.

**Ambient input sources are the other leak.** A project whose input comes from hardware or an
editor-side simulator needs a one-call *silence* hook that every test invokes immediately after
loading the boot scene — otherwise the environment plays the game and menu selections move on
their own. Then inject through the same funnel production uses (the input router, not a bypass),
so the test exercises the real wiring. → `harness-trust.md`.

## Tests that break for reasons unrelated to the change

- **Never navigate a menu by a hardcoded number of taps.** A smoke test tapped twice and asserted
  `ItemCount - 1`; adding one row to that menu failed it with *"last row is About / Expected: 7 /
  But was: 6"* — a red test with nothing to do with the change under review. Loop until the index
  reaches the count constant instead.
- **Never bake a step count or a fixed index into a gameplay walk.** `for (int step = 0; step < 8
  && !done; step++)` assumed a six-step level while the difficulty in effect had twelve; and tapping
  `path[1]` landed on a cell that was a no-op in that layout, giving *"Expected: greater than 0 /
  But was: 0"*. Read the bound off the live rules object (`step < rules.TotalSteps + 2`) and poll
  until the state is actionable rather than assuming the next frame is.
- **`Assert.AreEqual` on a `Vector2`/`Vector3` is exact.** NUnit's object overload uses the type's
  own `Equals` (bitwise per component), not Unity's approximate `==`, so a computed
  `(1920, 1440)` fails on float rounding. Assert per component with a delta, or compare magnitudes:

  ```csharp
  Assert.AreEqual(1920f, d.x, 0.01f);   Assert.AreEqual(1440f, d.y, 0.01f);
  Assert.Less((pos - expected).magnitude, 2f);
  ```

## Two habits that make failures self-explanatory

**Phrase the assertion message as the command that fixes it.** Where assets are wired by an Editor
generator, they go stale every time new files land — so the tests say so:
`"<id>: icon missing (run the scaffold step after generating Assets/Art/<Class>/icon_<id>.png)"`.
A failure then tells the agent exactly which Editor entry point to invoke next, with no log
reading at all.

**Assert on geometry, not on a renderer.** A procedural uGUI `Graphic` can be verified in EditMode
in seconds, with no Game view, no screenshot and no working shader compiler:

```csharp
var canvas = new GameObject("c", typeof(Canvas)).GetComponent<Canvas>();
canvas.renderMode = RenderMode.ScreenSpaceOverlay;
graphic.transform.SetParent(canvas.transform, false);
Canvas.ForceUpdateCanvases();
Assert.Greater(graphic.canvasRenderer.GetMesh().vertexCount, 0);
```

That catches the whole "the component draws nothing" family — including a `Graphic` created with
`new GameObject(name, typeof(SomeGraphic))` and therefore missing its `CanvasRenderer` — and pins
exact vertex counts for a shape generator. It still works on a machine whose Editor cannot compile
UI shaders at all (the Metal Toolchain entry in `unity-gotchas.md`).
