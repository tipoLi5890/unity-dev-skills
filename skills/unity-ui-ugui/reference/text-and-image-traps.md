# Text boxes, image boxes, and the layout passes that mis-size them

> Part of the `unity-ui-ugui` skill. Read when a label vanishes instead of truncating, when a card
> of text overlaps the next one, when a decorative graphic is laid out as a row, or when a sprite
> refuses to stretch.

## 1 · TMP `preferredHeight` is unreliable inside nested Layout Groups

A `VerticalLayoutGroup` inside another `VerticalLayoutGroup`, sizing its cards from TMP's auto
height, computed the **first-frame** height *before* wrapping. With short placeholder text it looked
fine; with real, longer text the headline and body cards overflowed and the next card drew on top of
them. The bug only appeared once the screen was fed real content, which is the worst time to find it.

The fix that stuck was to stop asking TMP for a size in that layout at all:

- Give each card and each text block a `LayoutElement` with
  `minHeight = preferredHeight = <fixed>` and `flexibleHeight = 0`.
- Set `overflowMode = TextOverflowModes.Ellipsis` so overlong content is truncated, not spilled.
- **Budget the column arithmetically.** The column was a fixed ~760 px: one `80` px header
  card, three `214` px section cards, and `12` px spacing between them. Each section card was
  `12` padding top and bottom `+ 40` title row `+ 6` gap `+ 144` body — `24 + 40 + 6 + 144 = 214`.
  The point is the total is added up against the column height in advance rather than discovered at
  runtime; add the sum to the code as a comment so the next card change has to redo it.
- Cap the number of variable items (e.g. at most 2 bullets per section) so the budget
  cannot be exceeded by content.
- After swapping which child of the column is active, call
  `LayoutRebuilder.MarkLayoutForRebuild(column)`.

Content whose height genuinely may vary (a consent panel, a loading or failure state) can still be
content-driven — pin only the layout that has to be exact.

## 2 · `NoWrap` + `Ellipsis` in a short box makes the whole line disappear

A one-line list cell 43 px tall with

```csharp
tmp.textWrappingMode = TextWrappingModes.NoWrap;
tmp.overflowMode     = TextOverflowModes.Ellipsis;   // renders NOTHING
```

rendered **nothing at all**: TMP decided the single line did not fit vertically and dropped the whole
line rather than truncating it horizontally. `TextOverflowModes.Overflow` restored the text.

For a label that must stay on one line in a tight rect, use `Overflow` and clamp it visually with
layout — not with a mask, for the reason in `no-mask-lists-and-motion.md` §1.

## 3 · A decorative child of a Layout Group is laid out as a row

An accent bar meant to run down the left edge of a card was added as a child of that card, and the
card's `VerticalLayoutGroup` promptly stretched it into a horizontal stripe in the content flow,
pushing everything below it down.

```csharp
bar.gameObject.AddComponent<UnityEngine.UI.LayoutElement>().ignoreLayout = true;
bar.anchorMin = new Vector2(0f, 0f);    // its own anchors now apply
bar.anchorMax = new Vector2(0f, 1f);
```

Any purely decorative graphic parented under a Layout Group needs `ignoreLayout = true`, or it
consumes a row.

## 4 · `Image.preserveAspect` silently blocks stretching

A beam effect scaled to reach a target kept coming out squashed and short whatever the
RectTransform said. `preserveAspect` clamps the drawn rect to the sprite's own aspect ratio, and it
wins over the layout:

```csharp
jet.preserveAspect = false;
jet.type = UnityEngine.UI.Image.Type.Sliced;   // so the middle stretches, not the caps
```

Check which factory helper produced the `Image` before assuming: two helpers in one codebase can
default `preserveAspect` differently — `false` on one, `true` on its fixed-size sibling — and
divergent defaults are how this hides.

## 5 · Draw order is sibling order, and inserting into the middle needs an index

A route overlay drawn across a 3×3 grid was created with `SetAsFirstSibling()` and was therefore
painted **before** the nine opaque cell backgrounds — only slivers showed through the gaps. It
looked like a colour or alpha bug; nothing was logged. The fix was to say where it belongs:

```csharp
overlay.transform.SetSiblingIndex(9);   // after the nine cells, before objects spawned later
```

When a Canvas child is present in the hierarchy but invisible, check its sibling index against the
opaque elements *before* touching materials or colours.
