# Layout Groups and ScrollView — who owns size, and the parts

> Part of the `unity-ui-ugui` skill. Read when a Layout Group, a ContentSizeFitter or a ScrollView
> sizes something wrong. SKILL.md §3 holds the rules and the ScrollView hierarchy; this file holds
> the details and the parts.

## 1 · The fitter-and-group fight

> **A `ContentSizeFitter` on the same object as a `VerticalLayoutGroup` does not fight it on a
> single rebuild.** With three children at `preferredHeight = 40`, one forced rebuild gives the
> right answer — panel `120`, child `40` — with `Control Child Height` both on and off: no
> oscillation, no collapse. The reported fight, if it happens, needs repeated layout passes to show;
> **a single rebuild is not evidence of it.** Treat the combination as suspicious, not as broken,
> and measure before rearranging someone's hierarchy.

`Control Child Size` off → children keep their own size. **They do not collapse to zero**: a child
with no `LayoutElement` and no explicit size under a Layout Group with Control Child Height off
keeps the RectTransform's own height, not `0`. If something did
collapse, the cause is elsewhere (a zero preferred size reported up the chain, or a fitter on an
empty container) — find it rather than assuming this rule. `Child Force Expand` decides whether
children stretch to fill leftover space; it is not the same switch as Control Child Size and the two
are frequently confused.

`GridLayoutGroup` sizes children to `Cell Size` — it must be set explicitly; `Constraint` bounds
rows or columns. `ContentSizeFitter` needs something that reports a preferred size (a text component
or a `LayoutElement`); on an empty container it resolves to zero.

## 2 · ScrollView: the parts, and the three failures

Content is the one place where a Layout Group and a ContentSizeFitter belong on the same object:
the group sizes the children, the fitter sizes Content itself, so the scrollable height follows
whatever is in it. They act on different objects, which is why this is not the conflict in §1.
`ContentSizeFitter.FitMode` is `Unconstrained, MinSize, PreferredSize` — `PreferredSize` is the
one that grows.

**Wire the references; they are not inferred from the hierarchy.** `ScrollRect` exposes `content`
and `viewport` as `RectTransform`, and `horizontalScrollbar` / `verticalScrollbar` as `Scrollbar`.
A ScrollRect whose `content` is still null builds, inspects and lays out correctly, and never
moves.

**`Mask` does not bring an `Image` with it.** The only `[RequireComponent]` on `Mask` is
`RectTransform` — adding the component adds no Graphic — while `Mask.graphic` is typed `Graphic`.
The mask stencils the Graphic sitting on its own object, so a Viewport carrying a Mask and no Image
has nothing to stencil with. `RectMask2D` also requires only a `RectTransform` and needs no Image at
all — at the cost of the clipping shader variants in SKILL.md §6.

**Populating Content at runtime starts by emptying it.** Otherwise the second time the panel opens
the list is twice as long, and nobody reads that as a UI bug:

```csharp
for (int i = content.childCount - 1; i >= 0; i--)
    UnityEngine.Object.Destroy(content.GetChild(i).gameObject);   // DestroyImmediate in Editor code
```

`Destroy` is deferred to the end of the frame, so do not count `childCount` to prove the clear
worked in the same frame — add the new items and assert after the next layout pass.

| Failure | Cause |
|---|---|
| Items duplicate on every reopen | Content populated without clearing it first |
| Nothing scrolls however much content there is | No ContentSizeFitter on Content, Vertical Fit left `Unconstrained`, or `ScrollRect.content` never assigned |
| The list jitters or flickers while it settles | Usually a fitter one level up, fighting an outer Layout Group over Content's size. The same-object combination does **not** oscillate on a single rebuild (§1) — find the outer owner rather than deleting the fitter |
