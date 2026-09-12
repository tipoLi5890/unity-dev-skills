# Layout arithmetic that is not obvious

Five places where "looks about right" produces artefacts that read as rendering faults.

## 1 · Insetting a slanted outline

Drawing a shape twice — border, then fill inset — needs **two** correction terms on a slanted edge,
and the second is easy to miss:

```csharp
float kL = Mathf.Sqrt(slantL * slantL + h * h) / h;      // perpendicular width on a slope
float insetL = bw * kL + Mathf.Abs(slantL) * bw / h;     // + the inner shape starts bw LOWER
var inner = new Rect(r.x + insetL, r.y + bw,
                     r.width - insetL - insetR, h - bw * 2f);
Blade(inner, slantL * inner.height / h, slantR * inner.height / h, fill);
```

- `k` — a slanted edge needs more *horizontal* inset than a vertical one to keep the border a
  constant **perpendicular** width. That factor is the edge length over its vertical run.
- `slant·bw/h` — the inner shape also starts `bw` lower, and on a slanted edge being lower means
  being further along the slant. Omitting it puts the inner shape ~0.85 px too far out, so the
  border is thinner at one end of every diagonal than the other, and on deep slants the fill spills
  past the outline at the corner.
- The inner **slant** scales by `inner.height / h` — parallel edges, shorter run.

## 2 · A glow must share the shape's edge angle

Expanding a rect while holding the slant constant flattens every layer's angle a little more than
the last. On a button whose edge sits at 18.8°, for example, four halo layers come out at
**17.3° / 16.0° / 14.9° / 13.9°** — four ghost outlines splaying away at the corners, which is
exactly what "the polygons are misaligned" looks like.

```csharp
float hh = h + w * 2f;
Blade(new Rect(r.x - w * kL, r.y - w, r.width + w * (kL + kR), hh),
      slantL * hh / h, slantR * hh / h, colour);   // slant scales with height → parallel edges
```

The horizontal spread carries `k` for the same reason as the inset: the offset is perpendicular.

## 3 · Snap to the pixel grid

IMGUI rasterises a quad at fractional coordinates by whichever pixel centres it happens to cover,
so an edge at `x.5` lands on one pixel this frame and the next after a sub-pixel nudge. Static
shapes get soft edges; **animated ones crawl**.

```csharp
static Rect Snap(Rect r)
{
    float x = Mathf.Round(r.x), y = Mathf.Round(r.y);
    float w = Mathf.Round(r.xMax) - x, h = Mathf.Round(r.yMax) - y;
    if (r.width  > 0.35f) w = Mathf.Max(1f, w);      // keep hairlines from vanishing
    if (r.height > 0.35f) h = Mathf.Max(1f, h);
    return new Rect(x, y, w, h);
}
```

Snap inside the fill and blade primitives so every caller benefits, and snap the outer rect **before**
computing an inner one so the border stays even.

### Breathe with light, not with geometry

A "pulse" that animates a button's **width** drags two high-contrast diagonal edges back and forth
across the pixel grid every frame — it reads as a shimmer, not a breath. Pulse the **glow alpha**
instead: it moves nothing, and putting it inside the button widget means no screen has to remember
to do it.

```csharp
if (enabled) BladeGlow(r, slant, -slant, fill, 0.55f * alpha * UiAnim.Pulse(2.4f, 0.45f));
```

## 4 · Camera framing is arithmetic, and it will put the camera in front of the player

A follow camera aiming a look-point ahead of its target sits at

```
camZ = target.z + lookAhead − distance · cos(pitch)
```

Tuning a cinematic push-in by eye — `lookAhead 7`, `distance 5.5`, `pitch 12°` — gives
`7 − 5.38 = +1.6`: the camera **1.6 units in front of the player**, who vanishes from the frame.
Solve for the offset you want instead: to sit 3.5 behind at distance 7 and 12°,
`lookAhead = 7·cos(12°) − 3.5 = 3.35`.

Camera height follows the same way: `groundY + distance · sin(pitch)`. Print both numbers before
running the game.


## 5 · Size a frame from the content, not the source canvas

Generated art — and plenty of hand-drawn art — arrives with transparent padding. 256×256 PNGs
from one generation batch, for example, fill only **~78%** of their canvas with actual ink.
Dropped into a 256 px box they render as ~200 px of subject, so every object looks undersized
next to geometry sized by its box — while every RectTransform matches the spec exactly. The
symptom is "the pieces look tiny", and nothing in the layout code is wrong.

Measure the opaque bounding box of a representative asset and derive the display size from the
ratio, not from the file's resolution:

```python
from PIL import Image
im = Image.open(path).convert("RGBA")
mask = im.getchannel("A").point(lambda a: 255 if a > 8 else 0)   # threshold, not > 0:
bbox = mask.getbbox()                                            # a feathered edge is not content
print(bbox, (bbox[2] - bbox[0]) / im.width)                      # → content fill ratio
```

Then `frame = wanted ink size ÷ fill ratio`. Worked example: a grid cell is
~260 px, the storyboard wants the subject at ~72% of a cell ≈ 187 px, fill ratio 0.78 → **frame
240 px**, held in one shared constant (with a second, smaller one for props). One constant per size
class is what keeps twelve screens consistent; a number typed per screen is not.

- **Scale the feedback with it.** Hit flashes, rings and bursts sized independently read smaller
  than the object they belong to. Derive them from the same constant.
- **Do not crop each PNG to its content instead.** It looks like the tidier fix and it destroys the
  relative scale the set was generated with — a small prop and a large one both become full-frame.
  Keep the padding and size from the ratio.
- Padding is per-batch: re-measure one asset from each generation run.
- The importer side of this — pivots, 9-slice borders, mesh type — is `unity-2d-sprites`.

---

## Aspect ratios: compute the budget, do not eyeball it

Fixed-width panels have a width **budget**, and a layout can be arithmetically impossible rather
than merely tight. A three-part top bar needing `width ≥ 1250 · Scale` cannot work in portrait at
**any** resolution, because `Scale` takes the shorter edge: the requirement reduces to
`1080 ≥ 1250`. That is not a tuning problem, it is a reason to lock the orientation — and locking
needs both the runtime `Screen.autorotate*` assignment **and** `ProjectSettings.asset`, because the
runtime call overrides the asset.

Work the numbers at 16:9, 20:9 and 4:3 before shipping a fixed-width layout.
