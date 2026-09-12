# Design space, screen match mode, and anchors that move

> Part of the `unity-ui-ugui` skill. Read when a layout is correct on the development display and
> clipped on a device, or when an element has to move between screen regions.

Reference resolution 1920×1080 throughout.

## 1 · `MatchWidthOrHeight 0.5` crops; `Expand` does not

The common advice — `ScaleWithScreenSize` + `MatchWidthOrHeight` at `0.5` — **clips whatever sits
past x 1663 on a 4:3 tablet** while it looks perfect on a 16:9 phone: a right-hand stat column
spanning x 1260–1860 loses its outer 197 design px, and a bottom-right indicator can be gone
entirely.

`MatchWidthOrHeight` interpolates the two scale factors logarithmically:
`scale = (w/1920)^(1−m) · (h/1080)^m`. At `m = 0.5` on 2048×1536 that is
`√(1.0667 · 1.4222) = 1.2317`, so the design space is **1663 × 1247** — 257 design px of width
that the layout was authored to use simply do not exist.

`ScreenMatchMode.Expand` uses the **smaller** ratio instead, so the design space always *contains*
the reference and the surplus becomes letterbox margin:

```csharp
scaler.uiScaleMode         = CanvasScaler.ScaleMode.ScaleWithScreenSize;
scaler.referenceResolution = new Vector2(1920, 1080);
scaler.screenMatchMode     = CanvasScaler.ScreenMatchMode.Expand;
```

| Screen | Aspect | `Match 0.5` design space | `Expand` design space |
|---|---|---|---|
| 1920×1080 | 16:9 | 1920 × 1080 | 1920 × 1080 |
| 2560×1600 | 16:10 | 1821 × 1138 (scale 1.405) | **1920 × 1200** (scale 1.333) |
| 2048×1536 | 4:3 | **1663 × 1247** | **1920 × 1440** |
| 2560×1080 | 21:9 | 2217 × 935 | **2560 × 1080** |
| 1280×800 | 16:10 | 1821 × 1138 | **1920 × 1200** |

`ScreenMatchMode.Shrink` is the documented opposite — the design space is never *larger* than the
reference, so content is cropped rather than letterboxed. Pick `Expand` when nothing may be lost
and empty margin is acceptable; that is almost always true of a game HUD.

**The consequence you have to encode, not just the setting.** Under `Expand`, anything positioned
from the top-left is guaranteed on screen, but the extra space appears at the bottom and/or right —
so an element that must hug a corner has to *anchor* to that corner. Absolute design coordinates
that happened to reach the right edge at 16:9 will float in the middle of a 4:3 screen.

## 2 · Extract the mapping so it is testable without a Canvas

A PlayMode test window's resolution is not settable from the test, so tablet aspect ratios cannot be
screenshotted. The substitute that does catch regressions is a pure function plus an EditMode test:

```csharp
public static Vector2 DesignSize(float w, float h)
{
    var s = Mathf.Min(w / 1920f, h / 1080f);   // ScreenMatchMode.Expand
    return new Vector2(w / s, h / s);
}
```

```csharp
[Test]
public void Design_space_always_contains_the_reference_frame()
{
    foreach (var (w, h) in new[] { (1920,1080), (2560,1600), (2048,1536), (2560,1080), (1280,800) })
    {
        var d = DesignSize(w, h);
        Assert.GreaterOrEqual(d.x, 1919.9f);
        Assert.GreaterOrEqual(d.y, 1079.9f);
        // exactly one axis equals the reference
        Assert.IsTrue(Mathf.Abs(d.x - 1920f) < 0.1f || Mathf.Abs(d.y - 1080f) < 0.1f);
    }
}
```

Real-device aspect-ratio checking still belongs on a manual checklist; this test only proves the
arithmetic did not regress.

## 3 · Do not multiply design px by a second scale factor

A type-scale helper ported from an IMGUI kit exposed `Px(designPx) = designPx * ScreenDerivedScale`.
In a uGUI project the `CanvasScaler` **already** applies `scaleFactor`, so calling that helper
squares the scaling. Author in bare design px and let the scaler do the resolution work. If a
user-facing "bigger text" option is wanted, multiply by the boost factor only — and give the label a
fit-to-width pass first, because a scaled-up short label overflows a pill button that has no
shrink-to-fit protection. *(Type sizing itself is `unity-game-ui`.)*

## 4 · Changing an anchor mid-animation teleports the element

`anchoredPosition` is **relative to the anchor**, so swapping `anchorMin`/`anchorMax` while
an element is moving makes it jump. Convert the current position into the new anchor's space first,
then start easing:

```csharp
void MoveTo(Vector2 newAnchor, Vector2 target)
{
    var parent = (RectTransform)rt.parent;
    var size   = parent != null ? parent.rect.size : new Vector2(1920f, 1080f);  // defined during construction
    var abs    = rt.anchorMin * size + rt.anchoredPosition;   // point-anchored: anchorMin == anchorMax

    rt.anchorMin = rt.anchorMax = newAnchor;
    rt.anchoredPosition = abs - newAnchor * size;

    _target = target;                                          // then glide
}

// per frame, frame-rate independent, and alive while timeScale == 0
pos = Vector2.Lerp(pos, _target, 1f - Mathf.Exp(-14f * Time.unscaledDeltaTime));
if ((pos - _target).sqrMagnitude < 0.25f) pos = _target;       // snap so it settles
```

This assumes a point-anchored element (`anchorMin == anchorMax`) whose pivot is unchanged; a
stretched element needs its offsets converted instead.

## 5 · Name the placements, do not scatter the coordinates

Once the Canvas uses `Expand`, one anchor cannot serve every element: bottom-right furniture must
anchor `(1, 0)`, something that tracks a top-left panel must anchor `(0, 1)`. A small struct of
`(anchor, centre, scale)` keeps the two halves of a placement together and makes the transitions
between them explicit:

```csharp
readonly struct Placement { public readonly Vector2 Anchor, Centre; public readonly float Scale; }

static readonly Placement MenuCentre  = new(new Vector2(1, 0), new Vector2(-190,  260), 1f);
static readonly Placement StageCentre = new(new Vector2(0, 1), new Vector2(1560, -750), 1f);
static readonly Placement Mini        = new(new Vector2(1, 0), new Vector2(-96,     45), 0.24f);
```

Moving between two `Placement`s goes through §4's conversion; nothing else in the codebase then
needs to know a corner's coordinates.
