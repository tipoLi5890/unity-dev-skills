# The ink is not the rect — transparent margins, pivots that carry weight, stretched sprites

> Part of the `unity-2d-sprites` skill. The parent file says where pivots and borders are written;
> this file is about choosing their values from something you measured, and about the one bug that
> looks like layout maths and is not.

## 1. Generated art carries transparent padding, and it silently shortens everything

> Symptom: an effect sprite stretched between two points visibly **stops short of its target**,
> while the length computed from the two positions is provably correct. Nothing in the layout is
> wrong. The drawn ink simply does not fill the rect it was given.

Worked example — a water-jet PNG, **96 × 512**, alpha bounding box `(20, 75) – (76, 438)` in the
half-open form an image library prints: the ink is **70.9 % of the height** and **58 % of the
width**, roughly 15 % transparent margin at each end of the stretch axis. Generated art, and
hand-authored art drawn with a safe margin, can carry padding like this; measure rather than
assume either way. The rect you position is the *canvas*, not the drawing.

Two ways out, and they are not equal:

- **Tighten the sprite rect to the alpha box.** One edit in the importer, and afterwards the rect
  and the ink agree everywhere — every call site, forever. It also changes the on-screen size of
  every existing use of the sprite, so it is cheap before the art is placed and a re-layout after.
  Prefer it unless the padding is load-bearing (frames of one strip that must stay registered to
  each other, or art whose margin encodes spacing).
- **Correct at the call site**, when the padding must stay. Divide the required on-screen length by
  the measured ink ratio, and write the measurement into the comment so the number is not a mystery
  constant later:

```csharp
// the sprite has ~15% transparent margin at each end, so only ~70% of the rect is ink
float len = (target - origin).magnitude / 0.7f;
```

Do not eyeball the factor. A ratio that is guessed is re-guessed by the next person.

## 2. Measuring the alpha box without leaving the project

Load the file's bytes into a throwaway `Texture2D`. This works regardless of the asset's
`isReadable` setting, because it is a new texture rather than the imported one:

```csharp
var t = new UnityEngine.Texture2D(2, 2);
UnityEngine.ImageConversion.LoadImage(t, System.IO.File.ReadAllBytes("Assets/Art/beam.png"));
var px = t.GetPixels32();
int minX = t.width, minY = t.height, maxX = -1, maxY = -1;
for (int y = 0; y < t.height; y++)
for (int x = 0; x < t.width;  x++)
    if (px[y * t.width + x].a > 8) {                       // 8/255 ignores near-empty fringe
        if (x < minX) minX = x;  if (x > maxX) maxX = x;
        if (y < minY) minY = y;  if (y > maxY) maxY = y;
    }
return $"{t.width}x{t.height}  ink {(maxX - minX + 1) / (float)t.width:P1} wide, " +
       $"{(maxY - minY + 1) / (float)t.height:P1} tall";
```

> **Check the printed numbers against the sprite before trusting them.** This is the arithmetic an
> image library outside Unity would do, expressed through the Editor so that no extra tooling is
> needed. The row order differs between the two — Unity's texture rows run bottom-up — which flips
> *which* edge a margin belongs to but never changes the ratio. The loop also counts inclusive
> pixel indices, so it reads one pixel wider on each axis than a half-open box like §1's: a
> fraction of a percent at these sizes, never enough to move the factor you divide by.

**Express the result as a ratio, not as pixels.** `maxTextureSize` and platform compression can
downscale the imported texture, so a pixel box measured on the file does not survive to runtime;
a ratio does.

## 3. Pivot follows the motion, not the picture

The parent skill's `(0.5, 0)` for characters is the common case. The general rule is that the pivot
goes wherever the sprite is *anchored while it moves* — because that is the point rotation and
scaling leave fixed:

| Sprite | Pivot | Why |
|---|---|---|
| A character standing on ground | `(0.5, 0)` | Feet stay on the floor at any height |
| A beam / jet that grows from an emitter | `(0.5, 0)` | Grows away from the nozzle, rotates about it |
| A swipe that sweeps out from its left edge | `(0, 0.5)` | The start of the stroke stays put |
| A pop or burst | `(0.5, 0.5)` | Expands about its own centre |

Writing `pivot` alone does nothing — `alignment` must be `SpriteAlignment.Custom` as well, or the
importer keeps using the named alignment and your vector is ignored. This bites hardest on a
re-run, where the rect already exists with `alignment = Center` from a previous pass.

## 4. A sprite that stretches to an arbitrary length wants a 9-slice border

A beam, jet, rope or progress fill has to reach a distance decided at runtime. Scaling the whole
sprite stretches its cap and its texture detail with it. A configuration that holds, for the
96 × 512 jet above: pivot `(0.5, 0)` at the emitter end, **border `(0, 16, 0, 16)`** — sixteen
pixels held at the bottom and top, i.e. across the stretch axis — drawn in a sliced draw mode with
aspect preservation turned **off**. Only the middle band stretches; the ends keep their shape.

Border is `Vector4(left, bottom, right, top)` in pixels of the sprite rect. A border across the
axis you are *not* stretching costs nothing and prevents the sprite from ever being distorted the
other way, so pin both if the sprite may be used in both orientations.

The caveat from §1 still applies on top of this: a 9-sliced sprite with transparent margin stretches
its *transparent* band too. Borders fix distortion, not reach.
