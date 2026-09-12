# Custom elements, Painter2D, and vector icons

> Part of the `unity-ui-toolkit` skill. Read when USS cannot express the thing: a gradient, a
> non-rectangular shape, a meter or graph, or a reusable component with its own UXML attributes.
> Drag interactions are in `reference/manipulators-and-drag-drop.md`.

## A custom VisualElement

Three pieces, and the third is what makes it draw:

```csharp
[UxmlElement]                                   // makes it usable from UXML
public partial class RadialMeter : VisualElement
{
    [UxmlAttribute] public float value { get; set; }   // exposed as a UXML attribute

    public RadialMeter() => generateVisualContent += Draw;

    void Draw(MeshGenerationContext ctx) { /* Painter2D work */ }
}
```

- **`generateVisualContent` runs on repaint, not every frame.** Call
  `MarkDirtyRepaint()` when the data behind the drawing changes; nothing redraws on its own.
- Read the element's own box from `contentRect` — never a hardcoded size. It is laid out by
  flex, so its size is not yours to assume.
- A custom element still participates in layout: give it a flex size from USS like anything
  else.

### Four requirements, and one of them is a language keyword

1. `[UxmlElement]` on the class.
2. **`partial`.** The attribute drives generated code; a non-partial class has nowhere for it to
   go, and the failure is a compile error rather than a missing element.
3. Derive from the right base, and *which* base depends on what the element does. An element
   that only **composes** existing controls can derive from `Label`, `Button` or any other
   subclass. An element that **draws** through `generateVisualContent` derives from
   `VisualElement` directly: the reason given upstream is that Painter2D content does not render
   correctly on a built-in control, whose own generated mesh occupies the same slot. Treat
   "derive straight from `VisualElement` when you draw" as the safe shape and test before doing
   otherwise.
4. `[UxmlAttribute]` on each property you want authorable from UXML. A public property without it
   is invisible to the markup.

> **The factory path is the old one.** `UxmlFactory<T>` and `UxmlTraits` both still exist and both
> carry `[Obsolete]` — code using them compiles with a warning. `[UxmlElement]` and
> `[UxmlAttribute]` are the current spelling and resolve in `UnityEngine.UIElements`
> (`UnityEngine.UIElementsModule`). Do not write a new element with the factory pair, and when
> touching one that has it, migrating is a small, contained change.

### Attribute names change case at the boundary

C# is camelCase, UXML is kebab-case, and the conversion is automatic:

| C# property | UXML attribute |
|---|---|
| `myStringValue` | `my-string-value` |
| `maxHealth` | `max-health` |
| `value` | `value` |

`[UxmlAttribute("hp")]` overrides the derived name when the markup should read differently from
the code. Give every attribute a default in the property initialiser — an element dropped into a
layout with no attributes set should still draw something.

### Types an attribute can be

`string`, `int`, `float`, `bool`, `Color`; `Texture2D`, `Sprite`, `Font`; any enum; `List<T>` and
`T[]` of those. Beyond that the markup needs a converter, and the converter is an editor-side
thing even when the element is runtime UI.

Both `UxmlAttributeConverter<T>` and the
static registry `UxmlAttributeConverter` live in `UnityEditor.UIElements`
(`UnityEditor.UIElementsModule`). The registry is keyed on the **converted type** —
`HasConverter(Type)` and `TryGetConverterType(Type, out Type)` are the whole lookup, and there is
**no registration attribute**: a scan of both UIElements modules finds no attribute type whose
name contains `Converter` other than the internal `ConverterDrawerAttribute`.
`HasConverter(typeof(Vector2))` and `HasConverter(typeof(Rect))` return `true`;
`HasConverter(typeof(GradientAlphaKey))` returns `false`.

So the arrangement resolves itself — nothing in runtime code points at editor code:

```csharp
// Runtime assembly, beside the element.
[System.Serializable]
public struct HealthRange { public float min, max; }

[UxmlElement]
public partial class HealthBar : VisualElement
{
    [UxmlAttribute] public HealthRange range { get; set; }   // no converter reference here
}
```

```csharp
// Editor assembly (an `Editor` folder, or an .asmdef with includePlatforms: ["Editor"]).
using UnityEditor.UIElements;

public class HealthRangeConverter : UxmlAttributeConverter<HealthRange>
{
    public override HealthRange FromString(string value)
    {
        var parts = value.Split(',');
        return new HealthRange { min = float.Parse(parts[0]), max = float.Parse(parts[1]) };
    }

    public override string ToString(HealthRange v) => $"{v.min},{v.max}";
}
```

The element's property carries only `[UxmlAttribute]`; the converter is found by its `T`. That is
why the split works: the runtime assembly never names an editor type, so the player build has
nothing to strip and nothing to fail on. The converter is what turns the UXML attribute string
into a value, which happens in the Editor — attribute values reach the player already resolved on
the `UxmlSerializedData` object the importer bakes into the `VisualTreeAsset` (that type is public
in `UnityEngine.UIElementsModule`). Where the types live implies this; if you ship an element with a
converted attribute, confirm it in a real build.

`[Range]` and `[Tooltip]` on an attribute property are honoured by the visual authoring tool's
inspector, which is free constraint documentation for whoever uses the element next.

**Static image → USS. Per-instance image → `[UxmlAttribute]`.** An icon that is always the same
belongs in a `background-image` rule; a portrait that differs per character belongs on the
element as a `Sprite` attribute. Putting the first in C# scatters art references through code,
and putting the second in USS multiplies selectors.

## The namespace declaration, and the one thing that breaks it

```xml
<ui:UXML xmlns:ui="UnityEngine.UIElements"
         xmlns:hud="Project.UI.Hud">
  <hud:RadialMeter value="0.6" />
</ui:UXML>
```

> **The namespace only — never the assembly.** `xmlns:hud="Project.UI.Hud, Assembly-CSharp"` is
> the mistake, and the comma is the tell. It is also case-sensitive and has to match the C#
> namespace exactly, and it is the namespace, not the class: `Project.UI.Hud.RadialMeter` as the
> `xmlns` value fails the same way. The result of any of these is an element that does not
> resolve at import, reported as an unknown element rather than as a namespace problem.

Declare one prefix per namespace; several in one file is normal and costs nothing.

## Painter2D

`ctx.painter2D` is a retained path API: set the paint, `BeginPath()`, trace, then `Fill()` and/or
`Stroke()`. Both can run on the same path. Every coordinate is local to the element's content rect.

The whole shape, in `UnityEngine.UIElementsModule`:

| Need | Call |
|---|---|
| Start a path | `BeginPath()`, and again before every path |
| Straight segments | `MoveTo(Vector2)`, `LineTo(Vector2)`, `ClosePath()` |
| Arc | `Arc(Vector2 center, float radius, Angle start, Angle end, ArcDirection dir)` |
| Fillet between two points | `ArcTo(Vector2 p1, Vector2 p2, float radius)` |
| Curves | `BezierCurveTo(Vector2 c1, Vector2 c2, Vector2 end)`, `QuadraticCurveTo(Vector2 c, Vector2 end)` |
| Paint it | `Fill(FillRule rule = NonZero)`, `Stroke()` |
| Clip a subtree of drawing | `PushClip()` / `PopClip()` |
| Bake the path to an asset | `SaveToVectorImage(VectorImage)` |

Paint properties, all set **before** `BeginPath()`: `fillColor`, `fillGradient`, `fillTexture`,
`strokeColor`, `strokeGradient`, `strokeFillGradient`, `lineWidth`, `lineJoin`, `lineCap`,
`miterLimit`, `dashPattern` / `dashOffset` (`SetDashPattern(float dash, float gap)` or
`SetDashPattern(ReadOnlySpan<float>)`).

Angles are a struct, not a float: `Angle.Degrees()`, `Angle.Radians()`, `Angle.Turns()` —
`Angle.Gradians()` also exists. `ArcDirection` is `Clockwise` or `CounterClockwise`. `FillRule` is
`NonZero` (default) or `OddEven`; `OddEven` is how a shape gets a hole.

**There is no rectangle call.** No `Rect()`, no `RoundRect()` — trace it with
`MoveTo`/`LineTo`/`ClosePath`, and use `ArcTo` for the corners of a rounded one. Every rounded-rect
helper you see in UI Toolkit code is somebody's own function for exactly this reason.

**Text is on the context, not on the painter.**
`ctx.DrawText(string text, Vector2 pos, float fontSize, Color color, FontAsset font = null)` —
declared on `MeshGenerationContext`, and `font` is a TextCore `FontAsset` (see §3 of the skill).
`null` falls back to the element's USS font. `MeshGenerationContext` also carries
`DrawVectorImage(VectorImage, Vector2 offset, Angle rotation, Vector2 scale)` and
`DrawMesh(...)`; the only two properties on it are `painter2D` and `visualElement`.

### Gradients

USS has no `linear-gradient()` / `radial-gradient()`, and the answer is not "hand-build the
ramp" — assign a `FillGradient` and fill normally. Four factories:

```csharp
FillGradient.MakeLinearGradient(Color start, Color end, Vector2 p0, Vector2 p1, AddressMode mode)
FillGradient.MakeLinearGradient(Gradient g, Vector2 p0, Vector2 p1, AddressMode mode)
FillGradient.MakeRadialGradient(Color start, Color end, Vector2 c, float r, Vector2 focus, AddressMode mode)
FillGradient.MakeRadialGradient(Gradient g, Vector2 c, float r, Vector2 focus, AddressMode mode)
```

The `Color, Color` pair is the two-stop shorthand; pass a `UnityEngine.Gradient` for more stops.
`AddressMode` decides what happens outside the ramp and has exactly three values —
**`Wrap`, `Clamp`, `Mirror`**. `Clamp` extends the end
colours and is what a card background wants. Note the name: the tiling mode is `Wrap`, not
`Repeat`.

Confirm that `FillGradient` and `painter2D.fillGradient` resolve on your Editor version before
building a screen around them; where they do not, emit the ramp yourself as vertex colours from
`generateVisualContent`.

Direction is the two points, in content-rect coordinates:

| Direction | Start | End |
|---|---|---|
| Top → bottom | `(0, 0)` | `(0, height)` |
| Left → right | `(0, 0)` | `(width, 0)` |
| Diagonal | `(0, 0)` | `(width, height)` |

On a radial gradient, moving `focus` off `center` shifts the bright spot — that is the whole
control for a highlight.

```csharp
void Draw(MeshGenerationContext ctx)
{
    var w = contentRect.width;
    var h = contentRect.height;
    if (w < 1f || h < 1f) return;               // not laid out yet

    var p = ctx.painter2D;
    p.fillGradient = FillGradient.MakeLinearGradient(
        m_Top, m_Bottom, new Vector2(0f, 0f), new Vector2(0f, h), AddressMode.Clamp);
    p.BeginPath();
    p.MoveTo(new Vector2(0f, 0f));
    p.LineTo(new Vector2(w, 0f));
    p.LineTo(new Vector2(w, h));
    p.LineTo(new Vector2(0f, h));
    p.ClosePath();
    p.Fill();
}
```

`strokeGradient` takes a plain `Gradient` and `strokeFillGradient` takes a `FillGradient`; they are
different types on two different properties, which is easy to get wrong once and never again.

### Rules that come from the API's shape

- **Guard a zero-size content rect.** An element gets a draw before it gets a layout; `w < 1f ||
  h < 1f → return` is the standard first line.
- **`BeginPath()` before each path.** Omitting it silently merges the new path into the last one.
- **Never mutate the element inside the callback** — no style writes, no adding children, no
  `MarkDirtyRepaint()` from inside a repaint.
- **`LineCap` is `Butt` or `Round` only** — there is no
  `Square`. `Butt` is the default and the one that gives an arc a precise endpoint; `Round` extends
  past it by half the line width, which reads as a progress ring that overshoots.
- **Rebuilding a large path every repaint costs.** If only the colour changes, drive the colour
  through USS and leave the mesh alone.
- **Antialiasing is in the mesh.** A shape with hundreds of segments is hundreds of segments;
  approximate an arc with as few as the size justifies.

## Manipulators

Interaction logic belongs on the element, in a `PointerManipulator` subclass with mirrored
register and unregister methods. The full pattern, the four events of a drag, drop-target
detection and the inventory questions to ask first are in
`reference/manipulators-and-drag-drop.md`.

## Vector icons

Vector assets import as `VectorImage` — the type resolves in `UnityEngine.UIElements`
(`UnityEngine.UIElementsModule`) — and can be used as a
`background-image` like any texture. They scale without resampling, which is the reason to prefer
them for icons.

**Where an icon should come from, in order:**

1. **An icon already in the project.** Search before generating anything; a second near-identical
   chevron is a style bug that ships.
2. **A hand-authored SVG path.** A chevron, an X, a plus, a magnifier: each is one `<path>` and
   costs nothing to produce or to review.
3. **An image generator**, last, for illustration and artwork that paths cannot express.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <path d="M8 4l8 8-8 8" stroke="currentColor" stroke-width="2" fill="none"
        stroke-linecap="round" stroke-linejoin="round"/>
</svg>
```

```uss
.icon-next {
  background-image: url("project://database/Assets/UI/Icons/chevron-right.svg");
  width: 24px;
  height: 24px;
}
```

A shared `viewBox` across an icon set is what makes the set line up at one USS size. `fill="none"`
with a stroke gives an outline family; `currentColor` keeps the icon tintable.

Two costs to keep in view: the import is a **tessellation**, so a detailed SVG becomes a lot of
triangles — simplify at the source, the same argument as `unity-3d-models`. And the imported asset
has to be set to produce a UI Toolkit vector image rather than a texture, or the USS reference
resolves to something that will not draw.
