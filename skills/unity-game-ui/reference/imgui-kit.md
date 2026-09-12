# A design system in IMGUI

IMGUI draws **axis-aligned textured rectangles and nothing else**. No layout system, no
post-processing, no polygons. Everything below is built from that one primitive.

## Why IMGUI at all

For a game whose retry path reloads the scene, `OnGUI` with **no scene Canvas** is a real choice,
not a legacy one: there is nothing to wire up, nothing to break when the scene is edited, and the
UI survives a `SceneManager.LoadScene` that destroys every MonoBehaviour. The cost is that layout,
motion and shape are all yours.

Trade-off to state plainly when someone asks: you give up the layout engine and any post-processing
(so glow, blur and rounded corners must be drawn), and you gain immunity to scene churn.

## One shape

Resist inventing shapes per screen. One parameterised primitive is what makes twelve panels look
like one kit:

```csharp
/// A rectangle with slanted left and right edges.
/// slant > 0 cuts the BOTTOM corner on that side; slant < 0 cuts the TOP one.
///   (+k, +k) trapezoid   (+k, -k) parallelogram   (0, 0) rectangle
public static void Blade(Rect r, float slantL, float slantR, Color fill)
```

Composed as `[left cap][body][right cap]`, where the caps are stretched **triangle alpha masks**
generated once at startup — three draw calls, exact edges at any size, no meshes. Generate four
corner variants (TL/TR/BL/BR filled) rather than flipping texture coordinates; explicit beats
clever when the mapping is what you are debugging.

```csharp
float gx = (x + 0.5f) / N, gy = 1f - (y + 0.5f) / N;   // flip Y once: GUI is top-down
float d;
switch (corner) {
    case 0:  d = (1f - gx - gy) * 0.7071f; break;      // top-left filled
    case 1:  d = (gx - gy)      * 0.7071f; break;      // top-right
    case 2:  d = (gy - gx)      * 0.7071f; break;      // bottom-left
    default: d = (gx + gy - 1f) * 0.7071f; break;      // bottom-right
}
alpha = Mathf.Clamp01(d * N * 0.5f + 0.5f);            // ~1px feathered edge at any size
```

Which cap survives follows from which corner was cut: cutting the bottom-left leaves the top-right
half of that cap. Get it wrong and the shape inverts — visible immediately, so no need to agonise.

## Everything else is that shape plus a mask

- **Discs, rings, haloes** — radial alpha textures, generated the same way. A halo needs a **power
  curve** falloff (`pow(1 - d/0.5, 2.6)`); a linear one has a visible hard rim where it reaches
  zero and reads as a second ring.
- **Glyphs the font does not have** — a padlock, an arrow, a stopwatch. Bake them as alpha masks
  with 2×2 supersampling. Do **not** type `✔` (U+2714): it is outside WGL4 and outside Roboto, and
  renders only where the host OS happens to have a fallback. One texture rotated with
  `GUIUtility.RotateAroundPivot` gives left/right/up arrows that are exact mirrors.
- **Outlines** — draw the shape twice, border first, fill inset. The inset arithmetic is not
  obvious; see `layout-math.md`.

## Never trust a cube's per-face UVs

Applying a texture to a stretched `PrimitiveType.Cube` and reasoning about which axis is U will
cost you rounds. Both wrong answers look like plausible bugs: one lays the content on its side, the
other smears it into stripes.

**Use a Quad when the mapping matters.** Its mapping *is* defined — local XY plane, facing local
−Z, U along +X and V along +Y — so orienting it by hand fixes the content's up-axis with nothing to
guess:

```csharp
Vector3 up     = /* along the surface, the direction content should stand */;
Vector3 normal = /* the face the camera can see */;
quad.transform.SetPositionAndRotation(centre, Quaternion.LookRotation(-normal, up));
quad.transform.localScale = new Vector3(spanU, spanV, 1f);
```

Keep a solid box behind it for thickness and occlusion; the Quad is only the skin.

## Per-frame cost

`OnGUI` runs every frame and immediate-mode text measurement is not free. Letter-spaced text
measures **and** draws each glyph, so the naive path is 2 `CalcSize` + 2 `GUIContent` + 2 `string`
per character per frame — e.g. ~118 `CalcSize` calls and ~240 allocations per invocation on one
static menu, i.e. megabytes a second of garbage on a screen where nothing moves. Memoise:

```csharp
static readonly Dictionary<int, float> glyphWidths = new(512);
static readonly GUIContent[] glyphContent = new GUIContent[128];

static float GlyphWidth(char ch, int size)
{
    int key = (size << 8) | (ch < 128 ? ch : 0);   // size matters: CalcSize reads style.fontSize
    if (ch < 128 && glyphWidths.TryGetValue(key, out float w)) return w;
    w = Style(size).CalcSize(Glyph(ch)).x;
    if (ch < 128) glyphWidths[key] = w;
    return w;
}
```

The GC hitches land on exactly the screens where the player is watching for a highlight to answer
their input.
