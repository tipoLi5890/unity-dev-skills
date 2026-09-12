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
