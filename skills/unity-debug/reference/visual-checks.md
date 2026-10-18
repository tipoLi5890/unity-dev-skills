# Seeing the game: screenshots the agent reads

Assertions cannot catch overlapping UI, text on text, art cropped by the wrong aspect, unreadable
contrast, or an element off-screen. Every one of those passes every test and is obvious in one
image. This is the loop that closes that gap.

```bash
"$UNITY" -projectPath "<project>" -runTests -testPlatform PlayMode \
  -testResults /tmp/results.xml -logFile /tmp/tests.log     # NO -batchmode
```

**Drive the game to the screen you want** by calling flow methods directly from the test, with a
frame yield between each. One test walks the whole product and drops a numbered screenshot at every
stage. IMGUI (`OnGUI`) does appear in windowed captures, so this works even when the entire UI is
immediate-mode.

```csharp
gm.RequestStart();          yield return Capture("02_opponent_select", gm);
gm.SelectOpponent(0);       yield return Capture("03_character_select", gm);
gm.SelectCharacter(false);  yield return Capture("04_countdown", gm);
```

Log the state alongside every shot — `[SHOT] 04_countdown state=Countdown` — so you can tell at a
glance whether the frame you are looking at is the one you meant to capture.

**The same test has to survive a batch run**, because the suite gets run headless too. Bail out of
the capture rather than skipping the test, so a batch run still verifies state and simply produces
no PNGs:

```csharp
IEnumerator Capture(string name, GameManager gm, float settle = 1.0f)
{
    yield return new WaitForSeconds(settle);       // same wait in both modes, so the states match
    Debug.Log($"[SHOT] {name} state={gm.State}");
    if (Application.isBatchMode) yield break;      // no end of frame, and a fake 640×480 target
    yield return new WaitForEndOfFrame();
    Directory.CreateDirectory(OutDir);
    ScreenCapture.CaptureScreenshot(Path.Combine(OutDir, name + ".png"));
    yield return null;
}
```

Corollary: **never make "the screenshots exist" a pass condition** — a batch run passes and writes
none.

**A scene left out of Build Settings can still be photographed.** Keeping Build Settings down to one
boot scene is good hygiene, and it does not stop a PlayMode test loading the others by asset path
(inside `#if UNITY_EDITOR`):

```csharp
yield return UnityEditor.SceneManagement.EditorSceneManager.LoadSceneAsyncInPlayMode(
    "Assets/Scenes/Games/X.unity", new LoadSceneParameters(LoadSceneMode.Additive));
// ... assert SceneManager.GetSceneByName("X").isLoaded, capture, then UnloadSceneAsync
```

---

## Check the PNGs are this run's

The results file gets deleted before each run; **the screenshot directory usually does not.** After
a PlayMode run that failed part-way, `ls -la` on the shots directory showed `01`–`04` stamped 11:42
sitting next to `05`–`07` stamped 15:19 — reading them as one set describes a UI that no longer
exists. `rm -rf` the directory before the run, or trust only files whose mtime is after it started.

**The Game view's resolution is the capture's resolution.** A windowed run renders at whatever the
Game view is set to, and a canvas scaler's factor follows it — so set the Game view to the target
resolution or aspect before measuring anything about apparent size, or every number derived from
the image is about a window instead of about the product.

---

## Settle time is per-screen, and both directions bite

```csharp
IEnumerator Capture(string name, GameManager gm, float settle = 1.0f)
```

- **Too short** and you photograph a transition. At 0.35 s two character cards were still mid-slide,
  and the capture read exactly like a layout bug with both cards clipped off the screen edges.
  Chasing that wastes a round.
- **Too long** and you step over transient states entirely. Raising the default to 1.0 s silently
  turned the "countdown" shot into a second Playing frame and the "launch in flight" shot into the
  result screen — two screens quietly lost from the suite with everything still green.

So: a **default long enough for entry animations to finish**, an explicit short value for moments
that are themselves transient, and where a state is too brief to catch, lengthen the state for the
test (`gm.countdownSeconds = 2.2f`) rather than shortening the wait.

Assert what you captured, or the loss stays silent:

```
[SHOT] 04_countdown state=Countdown     ← right
[SHOT] 04_countdown state=Playing       ← the shot is worthless, and nothing failed
```

## A fixed resolution, and no shader placeholders in the shot

Two Editor-only facts decide whether a windowed capture shows what a build would:

- **The Game view's size is whatever the window was.** Set it before the first shot with the public
  `PlayModeWindow.SetCustomRenderingResolution(w, h, label)`, then read it back with
  `PlayModeWindow.GetRenderingResolution(out w, out h)` and log it. A window smaller than the
  resolution scales the view down on screen, but the render target, `Screen.width/height` and the
  capture all have the size you set.
- **Shaders compile asynchronously.** A capture taken while `ShaderUtil.anythingCompiling` is true
  shows cyan placeholders that no build draws (`unity-gotchas.md` §22). Wait until it is false,
  capped at 30 s so a stuck compile cannot hang the suite.

Both APIs live in `UnityEditor`, and the situation code that takes the shots lives in a Runtime
assembly that cannot reference it. Put static hooks in the Runtime code and fill them from an
`[InitializeOnLoad]` class in an Editor assembly, which re-runs after every domain reload:

```csharp
// Runtime assembly, next to the situations
public static Func<int, int, bool> SetResolutionHook;   // null in a player
public static Func<bool> RenderReadyHook;               // null in a player: always ready

// Editor assembly
[InitializeOnLoad] static class ShotHooks {
    static ShotHooks() {
        Shots.SetResolutionHook = (w, h) => {
            PlayModeWindow.SetCustomRenderingResolution((uint)w, (uint)h, $"shots {w}x{h}");
            PlayModeWindow.GetRenderingResolution(out uint rw, out uint rh);
            Debug.Log($"[SHOT] game view {rw}x{rh}");
            return rw == w && rh == h;
        };
        Shots.RenderReadyHook = () => !ShaderUtil.anythingCompiling;
    }
}
```

In a player the hooks are null, and the runtime falls back to `Screen.SetResolution`.

## Every image gets opened

A suite of 22 situations writes several PNGs per situation. The test can assert that each file exists and
is bigger than 10 KB (a black or failed capture is usually smaller); only reading it says the
moment is the right one. **The agent that ran the shots opens every image it reports on**, and a
hand-back that says "screens verified" names the files it opened. For a batch too big to open
one by one, tile it into a contact sheet first and open that, then open full size whatever the
sheet makes doubtful:

```bash
ffmpeg -y -pattern_type glob -i 'shots/*.png' -vf "scale=480:-1,tile=4x6" -frames:v 1 sheet.png
```

A sheet proves each frame was drawn; it cannot show motion between frames (`motion-and-timing.md`).

---

## Reading the image

Downscale before viewing — a 16:9 capture is several MB:

```bash
ffmpeg -y -i shots/01_mainmenu.png -vf "scale=900:-1" shots/preview.png
```

For anything about **edges, borders or alignment**, an overall view is not enough. Two techniques,
both cheap and both decisive:

**Crop and magnify with NEAREST** (never smooth — smoothing invents the sub-pixel detail you are
trying to judge):

```python
im.crop((500, 580, 700, 720)).resize((800, 560), Image.NEAREST).save("zoom.png")
```

**Scan a line of pixels** when you need a number rather than an impression. This settled a "the
border is uneven" suspicion in seconds — it was 3 px top, 2 px bottom against a 2.5 px setting,
i.e. correct, and the apparent thickness was a letter's antialiasing:

```python
for y in range(y0, y1):
    r, g, b = px[x, y]
    kind = "WHITE" if r > 200 and g > 200 else ("FILL" if r > 150 and g < 110 else "bg")
```

Scanning also **measures the real layout** — where each panel starts and ends — which is how to
check a computed rect against what was actually drawn instead of trusting the arithmetic twice.

---

## Comparing before and after

Two questions, two tools:

| The question | The tool |
|---|---|
| Did my change do what I meant, and by how much? | Copy the set aside, measure one property on both sides |
| Did anything change that nobody meant? | Golden images: accepted baselines, `scripts/golden_diff.py`, an exit code |

### One change, measured

Copy the screenshot set aside **before** changing anything:

```bash
cp -r /tmp/shots /tmp/shots_baseline
```

Then a change can be quantified rather than asserted. High-frequency energy is a good proxy for
aliasing and shimmer:

```python
edges = Image.open(p).convert("L").crop(box).filter(ImageFilter.FIND_EDGES)
score = sum(edges.getdata()) / (edges.width * edges.height)
```

Enabling 4× MSAA and anisotropic filtering took the distant-scenery figure from 14.3 to 10.0, a 30%
drop — a claim worth making because it has a number behind it.

### Golden images: what must not change

A golden image is a screenshot somebody looked at and accepted. Every later run is compared with
it image by image, and the comparison ends in an exit code a loop can act on.

> **A baseline is recorded on purpose, never on a first run.** With no baselines the gate exits 3,
> nothing verified; recording is a separate command, run after reading the images. A gate that
> accepts whatever it sees first has accepted whatever bug was on screen that day.

```bash
rm -rf /tmp/shots /tmp/heat; rm -f /tmp/tests.log /tmp/results.xml; START=$(date +%s)
"$UNITY" -projectPath "<project>" -runTests -testPlatform PlayMode \
  -testResults /tmp/results.xml -logFile /tmp/tests.log; echo "exit=$?"   # windowed: NO -batchmode

# once, after reading every PNG in /tmp/shots:
python3 scripts/golden_diff.py Goldens/osx-metal /tmp/shots --shots /tmp/tests.log --record

# every run after:
python3 scripts/golden_diff.py Goldens/osx-metal /tmp/shots --shots /tmp/tests.log \
  --since "$START" --heatmap-dir /tmp/heat; echo "exit=$?"
```

Delete the log with the shots: `[SHOT]` lines in last run's log describe last run's images.
`--since` refuses any image or log older than the run's start, the guard the results file gets.

```
  PASS     01_menu.png       mean=0.00 p99=0 max=0 changed=0.0000 masked=0.0%
  SHOT     04_countdown.png  state: baseline Countdown, this run Playing
  FAIL     05_run_hud.png    mean=3.41 p99=88 max=255 changed=0.0130 changed_px=26633 at=812,40,1108,136 masked=0.9%  over=mean,p99,changed
  MISSING  06_result.png     baseline has it, this run wrote no such image
  EXTRA    08_pickup.png     no baseline, not judged: look at it, then --record --only 08_pickup
[GOLDEN] files=4 passed=1 failed=1 missing=1 extra=1 invalid=1 verdict=harness
```

| Exit | `verdict=` | Means | Next |
|---|---|---|---|
| 0 | `green` | Every baseline has an image from this run, inside all three thresholds | Read the `EXTRA` lines; those were not judged |
| 2 | `failed` | An image moved past a threshold: a real verdict | Read its heatmap; fix the code or re-record that image. Never retry |
| 3 | `harness` | Nothing verified: no baselines, a missing image, a size or `[SHOT]` mismatch, a stale or unreadable file, a bad mask | Fix the capture. **Never re-record to clear a 3** |

3 wins over 2: a set with a hole in it is not a verdict. The `FAIL` lines still print.

### Same conditions, or the numbers mean nothing

A diff measures everything that differs between two runs, including what the test never meant to
vary. Pin each of these, and print each on the `[SHOT]` line so the gate checks it instead of
trusting it:

```csharp
Debug.Log($"[SHOT] {name} state={gm.State} settle={Mathf.RoundToInt(settle * 1000)}ms " +
          $"screen={Screen.width}x{Screen.height} quality={QualitySettings.GetQualityLevel()} " +
          $"gfx={SystemInfo.graphicsDeviceType}");
```

`--record --shots` stores those pairs in `shots.txt` beside the baselines. Later, an image whose
pairs differ, has no `[SHOT]` line, or has two in one log reports `SHOT` and exits 3: a
`state=Playing` frame is not a layout regression of a `state=Countdown` baseline. Values carry no
spaces and no culture-formatted decimals, hence integer ms.

| Pin | Why it moves | How |
|---|---|---|
| Resolution | The capture is the Game view's size, and the canvas scaler follows it | A fixed Game view resolution, not Free Aspect; `screen=` and the size check catch a reverted layout |
| Settle time | Too short photographs a transition; too long steps over a transient state | The settle each shot had when its baseline was recorded |
| Quality level | MSAA, shadows, LOD bias and render scale all change pixels | `QualitySettings.SetQualityLevel(i, true)` in `[SetUp]` |
| Graphics API, GPU | Metal, Vulkan and D3D rasterise and filter differently | One baseline directory per platform and API (`Goldens/osx-metal/`); confirm two machines read `mean=0.00` against it before they share it |
| Frame-dependent effects | Temporal AA and motion blur read earlier frames; film grain and particles read a seed or the clock | Off in the golden quality level or Volume; a fixed particle seed, or a mask |
| Saved state | PlayerPrefs and `persistentDataPath` survive runs (`reference/harness-trust.md`) | Reset in `[SetUp]` |

Confirm on your project before choosing thresholds: record one run into a scratch directory,
compare a second run of the same build against it, and read the lines. Anything above
`mean=0.00 p99=0` is your noise floor; find what moves before setting `--delta` above it. Confirm
too that each name appears once per log (`grep -c '\[SHOT\] 04_countdown' /tmp/tests.log`).

### Masks: the regions allowed to change

A lap timer, a sparkle on a pickup, a sentry's idle loop: they differ every run and say nothing
about layout. Declare them in `masks.json` beside the baselines (or pass `--masks`). Masked pixels
leave all three numbers; they are not counted as equal.

```json
{
  "*":              [{"box": [1760, 1048, 1920, 1080], "why": "build label"}],
  "05_run_hud.png": [{"box": [1680, 24, 1880, 88], "why": "lap timer"}],
  "07_launch.png":  [[600, 300, 1320, 700]]
}
```

- A key is a file name, a relative path or an fnmatch pattern; every matching key applies. A box
  is a bare `[x0, y0, x1, y1]` or an object with a `why`.
- Boxes are **image pixels, top-left origin, `x1`/`y1` exclusive**: the box `im.crop()` takes, not
  the bottom-up rows of a `Texture2D` (`reference/motion-and-timing.md`). A box outside the image
  was drawn for another resolution: exit 3.
- **Remove the change before masking it.** Drive the timer to a fixed value in the test; mask only
  what cannot be pinned. `masked=` on each line says how much of the frame the gate stopped
  looking at.

### Three thresholds, three shapes of change

`d` is the largest per-channel difference at a pixel, 0–255, alpha dropped.

| Number | Fails above | Catches | Lets through |
|---|---|---|---|
| `mean` of d | `--mean 2.0` | A faint change everywhere: exposure, a colour grade, a tint | Anything small, diluted by the rest of the frame |
| `p99` of d | `--p99 24` | A moderate change over more than 1% of the frame: a panel recoloured, a shadow moved | Anything under 1% of the frame |
| `changed`, the share of pixels with d > `--delta 48` | `--changed 0.005` | A strong change too small for p99: an icon gone, a label moved | Faint changes; anything under 0.5% of the frame |

- Keep `--delta` above `--p99`; at or below it p99 never fires alone, and the script warns.
- At 1920×1080, 0.5% is about a 100 px square, so a missing 48 px icon passes all three. **Goldens
  judge layout and look; a wrong digit is an assertion's job**, or a tighter `--changed` on that one
  screen with `--only`.
- Tighten masks, not thresholds. A threshold loosened for one noisy screen is loosened for all.

### Before re-recording, read the heatmap

`--heatmap-dir` writes `<name>.diff.png` per compared image: the difference ×4 in grey (black =
equal, white = changed, as in `reference/motion-and-timing.md`), masks outlined blue with their
change still drawn inside, the changed pixels' box outlined red. The `FAIL` line prints that box as
`at=`.

1. View the heatmap, downscaled: **where** is the change? Is each mask still on its timer?
2. Crop baseline and current at the `at=` box with NEAREST (above): **what** is it?
3. Unintended: fix the code and rerun. Intended: re-record **that image only**.

```bash
python3 scripts/golden_diff.py Goldens/osx-metal /tmp/shots --shots /tmp/tests.log \
  --record --only 05_run_hud
```

`--record` prints how far each replaced image had moved, merges its `[SHOT]` line into `shots.txt`
and never writes `masks.json`. Commit the new baseline with the change that moved it.

> **Re-recording to turn a red run green is a retry that launders a failure.** The first verdict
> stands until somebody has read why it failed (`reference/harness-trust.md`).

### Symptom → cause

| Symptom | Cause |
|---|---|
| Every image fails on `mean`, little `changed` | Something global moved: quality level, render scale, exposure or grading, another GPU or API |
| `SIZE` on every image | The Game view's resolution changed, or the run was on another machine |
| One image fails with a box over something mid-animation | Settle too short: the shot caught a transition |
| A small region differs every run, never the same pixels | Something unseeded: particles, a shader reading time. Pin it or mask it |
| `MISSING` on every image | A `-batchmode` run (no PNGs), or Unity never started: check the results file first |
| `MISSING` from one image onward | A test failed part-way and later captures never ran: read the test verdict first |
| `UNREAD … a git LFS pointer` | The checkout skipped LFS: `git lfs pull` |

### Where the baselines live

Never under `Assets/`: Unity imports each PNG there as a texture with a `.meta`, and the baselines
become project content. `masks.json` and `shots.txt` travel with the PNGs.

| Where | Gains | Costs |
|---|---|---|
| In the repo through git LFS (`git lfs track "Goldens/**/*.png"`) | Versioned with the code that drew them; a re-record shows in the same diff | Every clone and CI runner needs LFS, or the baselines are pointer files and the gate exits 3 |
| Outside the repo (a shared drive, an artifact store), its path the first argument | The repo stays small; many platform sets cost nothing | The look no longer moves with the commit that changed it: write `git rev-parse HEAD` into the set when recording |

Plain git suits a handful of small images; every re-record adds a full copy to history for good.

---

## What the green suite still missed

Worth having the list, because these are what the images are *for*. Two defects that pass every
EditMode and PlayMode assertion and show up in one screenshot walk:

- **A button underneath a persistent overlay.** An always-on widget reserved the bottom-right corner
  (about x ≥ 1580, y ≤ 410 of a 1920×1080 design space); a screen's primary button was anchored into
  that corner and was unreachable. **Subtract the rect of every persistent overlay before anchoring
  anything**, and check the corners in the images.
- **A panel that was semi-transparent when it needed to be opaque.** The paused game's own text bled
  through the pause panel's hint bar. No assertion can see that; one glance can.
