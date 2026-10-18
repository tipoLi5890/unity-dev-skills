# Measuring things a screenshot cannot show

"It shakes", "it flickers", "it stutters" are **temporal** faults. A single frame of a vibrating
panel is pixel-identical to a frame of a still one, so no screenshot can confirm or refute the
report. Comparing consecutive frames can, and it turns an impression into a number you can argue
with.

Read `harness-trust.md` first — every technique here is worthless if the capture is lying.

---

## Frame-to-frame churn

Fraction of pixels in a region that changed by more than a just-noticeable amount.

```csharp
static float Churn(Texture2D a, Texture2D b, Rect region)
{
    Color32[] pa = a.GetPixels32(), pb = b.GetPixels32();
    int w = a.width;
    int x0 = Mathf.Clamp((int)region.x, 0, w - 1), x1 = Mathf.Clamp((int)region.xMax, 0, w);
    // Screenshot rows run BOTTOM-UP; regions are given in GUI (top-down) coordinates.
    int y0 = Mathf.Clamp(a.height - (int)region.yMax, 0, a.height - 1);
    int y1 = Mathf.Clamp(a.height - (int)region.y,    0, a.height);

    int changed = 0, total = 0;
    for (int y = y0; y < y1; y++)
        for (int x = x0; x < x1; x++)
        {
            int i = y * w + x;
            total++;
            if (Mathf.Abs(pa[i].r - pb[i].r) + Mathf.Abs(pa[i].g - pb[i].g) +
                Mathf.Abs(pa[i].b - pb[i].b) > 24) changed++;
        }
    return total == 0 ? 0f : changed / (float)total;
}
```

Sample ~10 consecutive frames, **always with `WaitForEndOfFrame` before each capture**, and report
the median next to the worst.

## Choosing the region decides whether the answer means anything

A region covering a whole HUD bar read **29.75%** — and was uninterpretable, because the gaps
between panels legitimately show the scrolling track. Roughly 43% of that region was background, so
30% was consistent with "panels perfectly still".

Rules that make a reading mean something:

- Measure **strictly inside** one element, clear of its edges and of any gap.
- Watch out for slanted shapes: a rectangular probe inset from a trapezoid's bounding box still
  pokes outside it at the narrow end.
- Split an element that contains something legitimately changing. Probing the clock panel's icon
  side and its digit separately is what showed the panel was still and only the digit ticked.
- When a probe follows an element that has moved, **move the probe too** — a probe left pointing
  at empty space reports the scenery and reads like a regression.

## Whole-frame difference: what moves, with no coordinates to get wrong

When region arithmetic and intuition disagree, stop doing arithmetic.

```csharp
int d = Mathf.Abs(pa[i].r - pb[i].r) + Mathf.Abs(pa[i].g - pb[i].g) + Mathf.Abs(pa[i].b - pb[i].b);
byte v = (byte)Mathf.Clamp(d * 4, 0, 255);      // amplified so small motion is visible
out[i] = new Color32(v, v, v, 255);
```

Write it to a PNG and look at it. Black = still, white = moving. This is what finally identified a
"the timer is trembling" report as **texture aliasing across the entire track and its roadside
scenery** — the HUD panels were solid black in the diff while the road surface was a dense speckle.
Region probes had been pointing at the wrong place for three rounds; the diff needed no region at
all.

The speckle pattern is diagnostic in itself: **high-frequency random noise = aliasing**, while
smooth scrolling motion produces smooth gradients in a diff.

---

## Reading the result

| Median | Worst | Meaning |
|---|---|---|
| ≈0 | ≈0 | Still. |
| ≈0 | high | A one-off event inside the region — a counter ticking, a pickup. Not a defect. |
| high | high | Genuinely moving every frame. |
| high | high, **and the diff shows dense speckle** | Not UI at all — texture minification aliasing. |
| high | high, **and the diff shows no speckle** | Everything moves, nothing aliases: the fault is temporal, not visual. Take a frame-time window and read the counters — `unity-profiling`. |

## If it is aliasing, the fix is filtering, not code

Two settings, both wrong by default, account for nearly all of it: `m_MSAA: 1` in the
render-pipeline asset (MSAA is OFF) and **`aniso: 1` in a texture's `.meta`.** The explanation and
the `.meta` fix belong to `unity-3d-models` → `reference/texture-filtering.md`.

> **Enabling MSAA changes frame timing**, which can tip a timing-sensitive gameplay test into
> failing. It also makes `WaitForEndOfFrame` mandatory before any texture capture. Both are
> covered in `harness-trust.md`.

## Capturing costs time, so never time the frame you captured

`ScreenCapture.CaptureScreenshotAsTexture()` plus `EncodeToPNG` and a file write stalled the frame
by about 100 ms in a tennis game's situations. Any timing metric taken on that frame is wrong: the
racket measured on the frame after a shot sits a capture's worth of time past the hit tick, and
that gap is the capture, not the animation. Two rules:

- **Measure an event by interpolating between the two frames that straddle it**, not on the frame
  that happens to be drawn after it, and log which one you used (`interp` or `frame`). A test then
  rejects a late measurement only when it was not interpolated.
- **Keep shots and timing apart.** A smoke test that asserts on frame time takes no screenshots; a
  shots run asserts on nothing timing-related.

## Recording motion: one readback per frame, resampled to a fixed rate

A contact sheet cannot show a pop between frames. To review motion, record a clip from inside the
run:

1. Render the review camera into a `RenderTexture` and request `AsyncGPUReadback.Request(rt, 0,
   TextureFormat.RGBA32, callback)` once per frame after `WaitForEndOfFrame`. It does not stall the
   frame the way a PNG capture does.
2. **Resample by game time, not by frame count.** When the game's clock is real time (a simulation
   on a stopwatch), `Time.captureFramerate` cannot slow it down. Stamp each readback with the
   game's render time, and in the callback write the frame as many times as the fixed output rate
   needs (repeat when frames are sparse, drop when they are dense). Log captured frames, written
   frames and readback errors: `captured 412 frames over 7.00 s (58.9 fps), written 420, errors 0`.
3. Write raw RGBA to one file, wait for pending requests (capped) before closing it, then encode.
   **The readback comes back upside down**; flip it in ffmpeg:

```bash
ffmpeg -f rawvideo -pix_fmt rgba -s 640x360 -r 60 -i review.rgba -vf vflip \
       -c:v libx264 -pix_fmt yuv420p -crf 18 review.mp4
ffmpeg -i review.mp4 -vf "select='not(mod(n\,6))',scale=256:-1,tile=10x7" -frames:v 1 review_every6.png
```

The second command is a contact sheet of every sixth frame, which an agent can open; the clip is
for the human. Log the game tick of the first frame, so frame *n* of the video maps back to a tick
and a metric spike at tick *t* can be found in the clip.
