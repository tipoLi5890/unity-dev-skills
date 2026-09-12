# Type sized for the distance it is read from

Most UI scale factors encode **handheld ergonomics** — "a phone held in either orientation gets the
same button size in millimetres". If the game is not held at arm's length, that factor is wrong for
text and nobody will report it as a bug; they will just find the game hard to read.

## Do the arithmetic, do not estimate

A 6.5in phone in landscape is 14.4 cm wide. At 2 m it subtends
`2·atan(7.2/200) = 4.1°`, so on a 1607 px render **one pixel = 0.154 arcmin**.

Cap height ≈ 0.72 × font size. Against that:

| | px | cap ′ at 2 m |
|---|---|---|
| Countdown digit | 159 | 17.6′ |
| Clock / score | 38 | 4.2′ |
| Instruction lines | 22 | 2.4′ |
| Card data | 17 | 1.9′ |

**5′ is the 20/20 limit for identifying an isolated high-contrast letter.** Comfortable *reading*
wants 16–22′. **Dense CJK glyphs need ≥ 8′** — a Han character carries several times the stroke
detail of a Latin letter at the same cap height, so the Latin figure does not transfer. (8′ is a
working floor, not a published threshold — confirm CJK legibility at the real distance before
committing a scale to it.)

So everything except the countdown is at or below the resolving power of the eye reading it — not
"a bit small", physically unresolvable.

Run this calculation for the real device and distance before choosing any size.

## Split geometry from type

Keep the existing scale for **rects, hit targets, borders, slants, gaps** — it is correct there.
Add a separate function for type.

```csharp
public static float Scale => Mathf.Max(0.4f, Mathf.Min(Screen.width, Screen.height) / 1080f);
public static int Type(float designPx) => Mathf.Max(8, Mathf.RoundToInt(designPx * Scale * DistanceBoost));
```

## The correction is PER ROLE, never a blanket multiplier

A blanket multiplier fails in every direction at once: a global 2.2× makes the countdown digit
absurd, overruns buttons that have single-digit-percent headroom, bursts the result cards — and
still does not rescue the thing it was aimed at. What a role needs depends on whether it is read
**mid-run, on the move** or **leaning in once before the run**.

Collapse the sixteen ad-hoc sizes a screen accumulates onto a handful of roles, each with its own
correction baked in. Worked example, for a game played at 2 m from a propped-up tablet
(design px on a 1920×1080 reference canvas rendered
1607 px wide, so one design px spans `0.154 × 1607/1920 = 0.129′` at 2 m, and with cap ≈ 0.72 ×
size that is **0.093′ of cap height per design px of font size** — two thirds of that at 3 m):

| Role | design px | cap ′ at 2 m | cap ′ at 3 m | For |
|---|---|---|---|---|
| `Display` | 150 | 13.9′ | 9.3′ | countdown digit, result headline |
| `Head` | 80 | 7.4′ | 5.0′ | **numbers a moving player glances at** — biggest correction |
| `Title` | 78 | 7.2′ | 4.8′ | screen headings, read once on arrival |
| `Body` | 44 | 4.1′ | 2.7′ | instructions — and therefore SHORT |
| `Caption` | 26 | 2.4′ | 1.6′ | dense card data; deliberately **not** corrected |

**Then accept what the table tells you.** The honest reading is not "inflate `Body` until it
clears 5′" — that overruns the layout, as the blanket 2.2× above does. It is:

- `Body` at 2 m is **below the recognition floor**. Instructional text must therefore be short, and
  it must **never be the only channel** carrying the information: position, shape, a lit cell or a
  glyph has to say the same thing.
- At 3 m only `Display`, `Head` and `Title` survive at all, and `Head`/`Title` only just.
  **Any interaction that requires reading before acting is a design error at that distance.**
- `Caption` staying uncorrected is a decision, not an oversight: six rows of stats in a 300 px
  card cannot be made legible at 2 m by any size that still fits the card, so growing it breaks
  the layout without buying legibility. Say that out loud rather than pretending the whole screen
  is covered.

Keep `DistanceBoost` as a global trim (default 1.0 once the roles carry the correction) so a seated
player or a tablet at arm's length can dial it back.

## One project, two viewing distances → add a named step

The same build often has a screen read from somewhere else: a post-run report someone picks the
tablet up to read at arm's length, a lobby someone leans into, a settings page nobody plays from.
Its prose wants a size between `Body` and `Caption` — and that is exactly the moment sixteen ad-hoc
sizes start growing back.

**Add a named step and record the distance it serves; never type an ad-hoc number.** For example,
add one role at 36 design px (≈3.3′ at 2 m, comfortable at arm's length) with a comment naming the
viewing distance, and every later screen for that distance picks it up. The rule for new text:
pick an existing role; if none fits, add a role with its viewing distance written next to it, so
the scale stays auditable instead of turning back into a pile of numbers.

## Fit before you grow, always

Growing type in a system with no fit-to-width ships overflowing buttons. Extract the fit first:

```csharp
public static int FitSize(string text, int size, float usable, float trackingRatio)
{
    if (string.IsNullOrEmpty(text) || usable <= 0f) return size;
    float w = TrackedWidth(text, size, size * trackingRatio);
    return w <= usable ? size : Mathf.Max(8, Mathf.RoundToInt(size * usable / w));
}
```

- **Usable width is the FLAT part of a blade**, not its bounding box: subtract the slanted ends.
- **Button widths are screen-WIDTH fractions while type follows Scale (height)**, so the ink-to-
  button ratio changes with aspect. A label with 18% headroom at 16:9 overruns its blade outright
  at 4:3 — and Android's Roboto Bold sets wider than the editor's Arial, so 16:9 on device is not safe
  either. Measure, never assume.
- Widgets that derive size from `r.height * ratio` need a **floor** from the role scale and a
  **ceiling** from `FitSize`; without the floor they stay handheld-sized while body copy grows past
  them, which inverts the hierarchy.
- Multi-segment headings must fit as a **whole** and share one size — fitting the segments
  independently breaks the shared baseline.

## Cut words, never shrink them

At a size that survives the distance, a sentence spans the frame. This is a forcing function, not
an inconvenience:

- 43 characters of "Pick a side — it fires the moment you choose" becomes **`LEFT · MIDDLE · RIGHT`**
  — shorter, readable, and it fixes a correctness bug on the way: the long copy denies a lane that
  is actually the best one.
- Then even that goes, because the three on-screen buttons below are laid out left-middle-right in
  a row: **their positions are the mapping**, and unlike a caption a position cannot contradict
  what it describes.

A player mid-stride cannot read a paragraph. When legibility and completeness conflict, cut.
