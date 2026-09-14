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
