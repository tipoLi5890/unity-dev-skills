# Colour, contrast and cues

Four separate traps, none of which produces an error message: the colour space converts your
numbers (or does not, depending on which field you set), alpha does not composite the way it
reads, a palette entry that looks fine has no contrast for the role you gave it, and a state cue
built out of hue vanishes at distance.

---

## 1 · Which colour field is linear, and which is already sRGB

In a project rendering in **linear colour space** (`m_ActiveColorSpace: 1` in
`ProjectSettings.asset`) the answer is different per UI system, and getting it the wrong way round
costs you the whole palette in either direction.

| You are setting | Interpreted as | So |
|---|---|---|
| IMGUI `GUI.color`, `GUI.backgroundColor` | **linear** | convert your sRGB literal on use |
| uGUI `Image.color`, `TMP_Text.color`, any `Graphic.color` | **sRGB** — Unity converts on the way to the shader | type the hex literal and leave it alone |

In a linear-space project a hex literal assigned to `Image.color` is exactly what the screenshot
shows, and applying the IMGUI-style `srgb.linear` helper to a `Graphic` **double-converts and
darkens the entire palette**. Both rows hold; they are different fields.

### IMGUI: author in sRGB, convert on use

A near-black `#141824` typed straight into `GUI.color` comes back out as mid grey-lilac:

```
0.078 linear → 0.30 sRGB     every panel four stops too light
0.894, 0.078, 0.310 (a deep magenta) → a pale pink
```

Never type linear values — nobody can read them off an art board.

```csharp
public static Color Ui(Color srgb) =>
    QualitySettings.activeColorSpace == ColorSpace.Linear ? srgb.linear : srgb;

static Color Hex(float r, float g, float b, float a = 1f) => Ui(new Color(r, g, b, a));
public static readonly Color Panel = Hex(0.078f, 0.094f, 0.141f, 0.99f);   // #141824
```

Audit every remaining `new Color(...)` literal at a call site. Colours built by `Color.Lerp`
between already-converted values are fine (and blend more correctly in linear); colours from data
authored for materials — a hazard's paint colour, say — need converting where the **UI** uses
them. **Do not route uGUI `Graphic` colours through this helper** — see the table above.

---

## 2 · Alpha composites linearly in both systems, and this is worse

Blending happens on linear values whichever system drew the quad, so a scrim's alpha does not mean
what it says:

```
alpha 0.70  →  surviving brightness = 0.30 linear  →  0.58 sRGB
alpha 0.72  →  0.28 linear                         →  ~0.57 sRGB
```

A "70% black" overlay only darkens the *displayed* image to 58%. This is why doubling a scrim can
appear to change nothing: pushing a scrim from 0.72 to 0.80 can pass unnoticed on screen —
reaching a genuinely dark overlay needs 0.9+ or an opaque panel behind the content.

In IMGUI you can make the number mean what it reads by converting the **surviving** brightness:

```csharp
public static void Scrim(float alpha)
{
    float a = QualitySettings.activeColorSpace == ColorSpace.Linear
        ? 1f - Mathf.GammaToLinearSpace(1f - Mathf.Clamp01(alpha))
        : alpha;
    Fill(fullScreen, new Color(0f, 0f, 0f, a));
}
```

The same arithmetic applies to **tint multipliers on textures**. Ghosting a locked icon with
`GUI.color = 0.22f` — or `Image.color = new Color(0.22f, 0.22f, 0.22f, 1f)` — multiplies in linear,
so it displays at ~50% and looks barely dimmed. Use ~0.07 for a real ghost. (Write the components
out: Unity's `Color * float` scales **alpha as well**, so `new Color(1,1,1,1) * 0.22f` makes the
icon translucent too, which is a different effect over a patterned background.)

And to **panel opacity**: at alpha 0.95 over bright key art, the 5% that survives is ~24%
displayed brightness, which shows up as a coloured haze across a panel meant to be near-black.
Use 0.99 for anything that should read as opaque.

**Sample the screenshot, never the swatch.** Settle numbers like these by reading actual pixels
out of a capture, not by reasoning about the palette:

```python
px = Image.open(shot).convert("RGB").load()
print(px[x, y])   # what is ACTUALLY on screen at that point
```

---

## 3 · Transparent pixels still carry a colour

A focus ring's halo can render as a dirty grey smudge over a cream background. The usual cause:
the PNG was authored by Gaussian-blurring the whole RGBA image, so RGB blurred toward transparent
**black** — and bilinear filtering then pulls those black RGB values back into the visible edge,
because filtering averages RGB whether or not alpha said the pixel was invisible.

**Blur the alpha channel only. Keep RGB flat at the tint colour across every pixel, including the
fully transparent ones.** (On a gold `#D5A448` glow, for example, rewriting RGB in the
transparent region removes the smudge with no change to alpha.)

The rule covers every soft-edged asset in a UI kit: glow, halo, outline, soft shadow, feathered
mask. It applies to generated art the same way — a generation or post-process step that composites
onto black before saving leaves the same trap. Where a kit generates its masks in code instead
(`imgui-kit.md`), write the tint into RGB and vary only alpha, and the problem cannot
occur.

---

## 4 · Measure the palette before you assign roles

Example contrast ratios for one palette (WCAG relative-luminance formula on the sRGB values
actually rendered):

| Pair | Ratio | Verdict |
|---|---|---|
| ink on card | 11.3:1 | body text |
| ink on paper | 10.5:1 | body text |
| white on primary | 7.7:1 | button labels |
| primary on paper | 7.1:1 | headings |
| ink on accent | 5.0:1 | text on an accent plate, OK |
| inkDim on paper | 4.6:1 | at the 4.5 floor — **cannot go lighter** |
| success on paper | 2.7:1 | surface / icon only |
| warn on paper | 2.3:1 | surface / icon only |
| accent on paper | 2.1:1 | surface / icon only |

The load-bearing conclusion: **accent, warn and success are not text colours.** They are fills,
strokes and icon tints, and they may only carry words on top of a dark plate. A secondary ink that
already measures 4.6:1 has no headroom left — treat it as fixed, and solve "this looks heavy" by
changing size or spacing rather than by lightening it.

### The trap that bites: a shared component inheriting its colour

A hint bar built once and reused on every screen defaults to the body-ink colour. Over a
full-screen scrim built from the same hue, that line can fall to **3.5:1** — and it may be the only
instruction telling the player how to leave the paused screen. Nothing in the layout looks wrong;
the component is simply drawn over a ground it was never measured against.

**Any shared text component that can appear over more than one ground must take its text colour as
a parameter**, and each caller passes the colour measured against *its* background. A default that
is correct on the main surface is a latent bug on every dark overlay.

---

## 5 · A cue that differs only in hue is not a cue

Take a lane indicator whose "this one holds the pickup" fill is `#F5D98B` against an idle fill of
`#E6EDE2`: that is **1.16:1** in luminance. The two states differ almost entirely in hue. Spatial
discrimination rides the luminance channel, so at 2 m — or for a red-green colour-deficient
player — the single most important cue in the game disappears.

**No game state may be signalled by hue alone.** Either:

- add a second channel — a radial glow, a bright stroked frame, a scale pulse, an in-cell glyph; or
- darken (or lighten) the cue colour until it is **at least 3:1** against the idle colour.

Check this the day the cue is invented. Retrofitting costs one change per screen that uses it, and
the same swap usually has to be repeated in the menu indicator, the in-game stage and any
tutorial art.

```python
def lum(c):
    r, g, b = [v / 255 for v in c]
    f = lambda u: u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

def ratio(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
```

Feed it the two **states of the same widget**, not text-on-background: that comparison is the one
nobody thinks to run.

---

## 6 · Contrast against what is actually behind it

Magenta headline text over mid-green grass, for example, comes out at **1.03–1.6:1** luminance
contrast. The word survives on *hue alone* — and at any distance it dissolves into a coloured
smear.

Two rules that follow:

- **Plate anything drawn over gameplay or key art.** A dark blade behind the words costs one draw
  call and takes white-on-ink to ~19:1. A drop shadow does not substitute: at `size * 0.05` it is
  a 3 px hairline under a 60 px cap.
- **One palette entry, one meaning.** An amber that means "reward" on a score pop, "danger" on a
  clock and "defeat" on a headline means nothing. If a score pop already has a size punch, that is
  the cue — size and luminance survive distance and colour-blindness; a 0.35 s hue flash does not.
