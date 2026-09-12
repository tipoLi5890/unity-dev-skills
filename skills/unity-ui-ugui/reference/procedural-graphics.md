# A UI kit drawn as vertices instead of sprites

> Part of the `unity-ui-ugui` skill. Read when the buttons, cards, frames, focus rings, glows and
> rules of a UI would otherwise be 9-sliced PNGs — or when a progress *outline* is needed and
> `Image.Type.Filled` will not give one.

A whole kit can move off generated 9-slice PNGs onto `MaskableGraphic` subclasses that emit
geometry in `OnPopulateMesh`. What that buys:

- No stretch wobble, and none of the halo edges background removal leaves on 9-sliced art.
- The geometry uses the **default UI material**, so no custom shader variant has to compile —
  decisive where variant compilation fails (see `no-mask-lists-and-motion.md`).
- It stays sharp at any resolution, is tintable, and every parameter (corner radius, outline width,
  glow strength) interpolates, so animation is a field assignment.
- The PNGs and their importer border/pivot metadata go away.

The cost is one file of vertex code (a few hundred lines holding the whole kit's shape classes)
and the trap in `code-built-ui.md` §2 — a `Graphic` built from
the `GameObject` constructor needs `typeof(CanvasRenderer)` named explicitly or it draws nothing.

## The four techniques that carried the kit

```csharp
protected override void OnPopulateMesh(VertexHelper vh)
{
    vh.Clear();
    var r = GetPixelAdjustedRect();          // 1 — always start here, never rectTransform.rect
    var tint = color;                        // 2 — Graphic.color multiplies fill/outline/glow
    ...
}
```

1. **`GetPixelAdjustedRect()`**, not `rectTransform.rect`: it is the rect after the Canvas's pixel
   adjustment, which is what everything else on the Canvas is aligned to.
2. **Treat `Graphic.color` as an overall tint** that multiplies your fill, outline and glow colours.
   Do that and a `Button` with `Transition.ColorTint` keeps working on your custom shape — it drives
   `CrossFadeColor` on the graphic, and a graphic that ignores `color` will not respond at all.
3. **Constant-width outlines come from offsetting the path *and* the corner radius by the same
   amount.** Generate the rounded-rect corner path at radius `r` for the outer edge and at radius
   `r − d` for the inner one, offset outward/inward by `d`; the stroke then stays `d` wide the whole
   way round, including through the corners. Offsetting only the positions pinches the corners.
4. **Antialiasing is a vertex ring, not a shader.** Emit one extra ring of vertices ~1.5 px beyond
   the edge with alpha 0; vertex colours interpolate, so the hardware fades the last pixel for you.
   Ten segments per corner is enough at card and button sizes — more is wasted vertices.

Call `SetVerticesDirty()` from every public setter, and **only when the value actually changed** —
a per-frame progress setter that dirties unconditionally rebuilds the mesh every frame for nothing.

## A progress *outline*

`Image.Type.Filled` with a radial method fills a **solid** shape. To make a cell's own border count
down, walk the rounded-rect perimeter clockwise from the centre of the top edge, accumulate arc
length, and emit a constant-thickness band up to `fill × perimeter`:

```csharp
public void SetFill(float v)
{
    v = Mathf.Clamp01(v);
    if (Mathf.Approximately(v, _fill)) return;
    _fill = v;
    SetVerticesDirty();
}
```

Starting at the top-edge centre reads as "the ring is draining" rather than "a line is growing from
a corner". This is also the mask-free way to do it — `Image.Type.Filled` on a masked outline sprite
would need the clipping variant that `no-mask-lists-and-motion.md` explains you may not have.

## Keep the shape tokens in one place

Whatever the numbers are, put them in one class so the kit coheres and a redesign is one edit. An
example set, in design px against a 1920×1080 reference:

| Token | Value |
|---|---|
| Card corner radius | 44 |
| Grid-indicator cell radius | 16 |
| Card/frame outline width | 6 |
| Cell frame outline | 10 |
| Focus ring width / its glow | 12 / 14 |
| Pill button radius | half the short side |
| Antialias fringe | 1.5 px |
| Segments per corner | 10 |

## Prove it without rendering

Vertex geometry is testable in EditMode with `canvasRenderer.GetMesh()` — see
`code-built-ui.md` §3. On a machine whose screenshots cannot be trusted, that test is the only
honest evidence the kit draws anything.

## `ColorTint` multiplies the graphic's own colour

`Selectable`'s ColorTint transition drives `Graphic.CrossFadeColor()`, which multiplies the state
colour onto the graphic's own colour — which is why the default `normalColor` is white. So
`pressedColor = Color.Lerp(fill, Color.black, 0.15f)` displays `fill × (fill × 0.85)`: a dark
primary button (e.g. #185D50) goes almost pure black when pressed while near-white secondary
buttons look fine, so it only shows on dark buttons. Use a brightness multiplier —
`new Color(0.85f, 0.85f, 0.85f, 1f)`.
