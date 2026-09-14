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

### Translating from a Canvas 2D sketch

The API is shaped like the HTML Canvas 2D context, so a drawing prototyped in a browser ports
almost mechanically. Almost — the rows in bold are where the translation stops being mechanical:

| Canvas 2D | Here | Note |
|---|---|---|
| `beginPath()` | `BeginPath()` | required before **every** path, not just the first |
| `moveTo(x, y)` / `lineTo(x, y)` | `MoveTo(new Vector2(x, y))` / `LineTo(…)` | coordinates are content-rect local |
| `closePath()` | `ClosePath()` | |
| `arc(cx, cy, r, a0, a1)` | `Arc(center, radius, Angle, Angle, ArcDirection)` | **angles are `Angle`, direction is an enum** |
| `arcTo(x1, y1, x2, y2, r)` | `ArcTo(p1, p2, radius)` | the fillet used for rounded corners |
| `bezierCurveTo(…)` / `quadraticCurveTo(…)` | `BezierCurveTo(c1, c2, end)` / `QuadraticCurveTo(c, end)` | |
| `rect(x, y, w, h)` | **nothing** | trace it yourself — see below |
| `fill()` / `stroke()` | `Fill(FillRule)` / `Stroke()` | both may run on one path |
| `fillStyle` | `fillColor` · `fillGradient` · `fillTexture` | three properties, not one |
| `strokeStyle` | `strokeColor` · `strokeGradient` · `strokeFillGradient` | |
| `lineWidth` / `lineJoin` | `lineWidth` / `lineJoin` | `LineJoin` is `Miter` (default), `Bevel`, `Round` |
| `lineCap` | `lineCap` | **`Butt` or `Round` only — there is no square cap** |
| `setLineDash([…])` / `lineDashOffset` | `SetDashPattern(…)` / `dashOffset` | |
| `fillText(…)` | `ctx.DrawText(…)` | **on the context, not on the painter** |
| `drawImage(…)` | `fillTexture`, or a child element with a USS `background-image` | no direct call |

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

### The rounded rectangle you have to write

Since there is no `Rect()`, every plate, card and badge starts from the same helper: four straight
runs, four fillets, and the radius clamped inside the helper so no caller can invert a short box.
Take the box as a `Rect` — the element hands you one already.

```csharp
static void TraceRoundedRect(Painter2D p, Rect box, float radius)
{
    var r = Mathf.Min(radius, Mathf.Min(box.width, box.height) * 0.5f);
    float left = box.xMin, top = box.yMin, right = box.xMax, bottom = box.yMax;

    p.MoveTo(new Vector2(left + r, top));
    p.LineTo(new Vector2(right - r, top));
    p.ArcTo(new Vector2(right, top), new Vector2(right, top + r), r);          // top-right
    p.LineTo(new Vector2(right, bottom - r));
    p.ArcTo(new Vector2(right, bottom), new Vector2(right - r, bottom), r);    // bottom-right
    p.LineTo(new Vector2(left + r, bottom));
    p.ArcTo(new Vector2(left, bottom), new Vector2(left, bottom - r), r);      // bottom-left
    p.LineTo(new Vector2(left, top + r));
    p.ArcTo(new Vector2(left, top), new Vector2(left + r, top), r);            // top-left
    p.ClosePath();
}
```

Each `ArcTo` takes the corner point and the point the path continues to, which is why the two
arguments read as "the corner" and "just past the corner". `y` grows downward here, so `yMin` is
the top edge — the same convention as every other UI Toolkit coordinate.

### A whole element, end to end

A plate the courier HUD uses behind a lane callout: vertical gradient, rounded corners, optional
border, every knob authorable from UXML.

```csharp
using UnityEngine;
using UnityEngine.UIElements;

[UxmlElement]
public partial class LanePlate : VisualElement
{
    Color m_Top = new Color(0.13f, 0.16f, 0.22f);
    Color m_Bottom = new Color(0.07f, 0.08f, 0.11f);
    Color m_Edge = Color.white;
    float m_EdgeWidth = 1f;
    float m_Radius = 8f;
    float m_Opacity = 1f;

    [UxmlAttribute] public Color top       { get => m_Top;       set { m_Top = value;       MarkDirtyRepaint(); } }
    [UxmlAttribute] public Color bottom    { get => m_Bottom;    set { m_Bottom = value;    MarkDirtyRepaint(); } }
    [UxmlAttribute] public Color edge      { get => m_Edge;      set { m_Edge = value;      MarkDirtyRepaint(); } }
    [UxmlAttribute] public float edgeWidth { get => m_EdgeWidth; set { m_EdgeWidth = value; MarkDirtyRepaint(); } }
    [UxmlAttribute] public float radius    { get => m_Radius;    set { m_Radius = value;    MarkDirtyRepaint(); } }
    [UxmlAttribute] public float opacity   { get => m_Opacity;   set { m_Opacity = Mathf.Clamp01(value); MarkDirtyRepaint(); } }

    public LanePlate() => generateVisualContent += Draw;

    void Draw(MeshGenerationContext ctx)
    {
        var w = contentRect.width;
        var h = contentRect.height;
        if (w < 1f || h < 1f) return;                       // not laid out yet

        var top = m_Top;    top.a *= m_Opacity;
        var bot = m_Bottom; bot.a *= m_Opacity;

        var p = ctx.painter2D;
        p.fillGradient = FillGradient.MakeLinearGradient(
            top, bot, new Vector2(0f, 0f), new Vector2(0f, h), AddressMode.Clamp);
        p.BeginPath();
        TraceRoundedRect(p, new Rect(0f, 0f, w, h), m_Radius);
        p.Fill();

        if (m_EdgeWidth <= 0f) return;

        var inset = m_EdgeWidth * 0.5f;                     // a stroke straddles its path
        p.strokeColor = m_Edge;
        p.lineWidth = m_EdgeWidth;
        p.lineJoin = LineJoin.Round;
        p.BeginPath();
        TraceRoundedRect(p, new Rect(inset, inset, w - m_EdgeWidth, h - m_EdgeWidth),
                         Mathf.Max(0f, m_Radius - inset));
        p.Stroke();
    }
}
```

```xml
<ui:UXML xmlns:ui="UnityEngine.UIElements" xmlns:hud="Project.UI.Hud">
  <hud:LanePlate class="lane-callout" top="#222A38" bottom="#11141B"
                 radius="12" edge-width="1" edge="#FFFFFF" opacity="0.9">
    <ui:Label text="Lane 2 — hazard" class="callout-title" />
  </hud:LanePlate>
</ui:UXML>
```

Three things that example is carrying:

- **The gradient is filled first, the border stroked second, on two separate paths.** One path
  cannot be both — `BeginPath()` between them is what keeps the fill from swallowing the stroke.
- **A stroke straddles the path it follows**, so a 1 px border traced on the element's exact
  bounds loses half of itself off the edge. Inset by half the line width, and shrink the radius
  by the same amount or the corner thickens.
- **The element still behaves like any other.** It sits in flex, takes children (they draw over
  the gradient), and its size, padding and margin come from USS — the C# owns the pixels inside
  the box and nothing about the box.

## Editing an attribute with something other than a text field

A `[UxmlAttribute]` gets a default editor in the visual authoring tool based on its type. When a
number wants a slider instead of a field, the lever is a `PropertyDrawer` returning a
`VisualElement` — the same `CreatePropertyGUI` shape as any inspector drawer, applied to a marker
attribute:

```csharp
// Runtime assembly, beside the element.
using UnityEngine;
using UnityEngine.UIElements;

public class LaneIndexAttribute : PropertyAttribute { }

[UxmlElement]
public partial class LaneBadge : VisualElement
{
    [UxmlAttribute, LaneIndex] public int lane { get; set; } = 1;
}
```

```csharp
// Editor assembly.
using UnityEditor;
using UnityEditor.UIElements;   // BindProperty lives here, not in UnityEngine.UIElements
using UnityEngine.UIElements;

[CustomPropertyDrawer(typeof(LaneIndexAttribute))]
public class LaneIndexDrawer : PropertyDrawer
{
    public override VisualElement CreatePropertyGUI(SerializedProperty property)
    {
        var slider = new SliderInt(1, 3) { label = property.displayName };
        slider.BindProperty(property);
        return slider;
    }
}
```

The same lever re-skins an attribute a **base class** already declares: derive from the control,
declare your own property under the base attribute's UXML name, and forward to `value`.

```csharp
[UxmlElement]
public partial class LaneField : IntegerField
{
    [UxmlAttribute("value"), LaneIndex]
    internal int laneValue { get => this.value; set => this.value = value; }
}
```

This changes only how the attribute is *authored*; the element's runtime behaviour is untouched.
Confirm the re-declaration resolves on your Editor version before building a set of elements on
it — a name collision with a base attribute is the kind of thing that changes between versions.

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
  <path d="M9 5 L17 12 L9 19" stroke="currentColor" stroke-width="2" fill="none"
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

### A starter set, all on one 24-unit box

Drop each into the same wrapper as the chevron above — `viewBox="0 0 24 24"`,
`stroke="currentColor"`, `stroke-width="2"`, `fill="none"`, `stroke-linecap="round"` — and the
whole set shares one optical weight. Adjust the inset (these sit 5 units from the edge) once,
across all of them, rather than per icon.

| Icon | `d` |
|---|---|
| Chevron left | `M15 5 L7 12 L15 19` |
| Chevron down | `M5 9 L12 16 L19 9` |
| Chevron up | `M5 15 L12 8 L19 15` |
| Check | `M5 13 L10 18 L19 6` |
| Close | `M6 6 L18 18 M18 6 L6 18` |
| Plus | `M12 5 V19 M5 12 H19` |
| Minus | `M5 12 H19` |
| Menu | `M4 7 H20 M4 12 H20 M4 17 H20` |
| Pause | `M9 5 V19 M15 5 V19` |

Two need a second element beside the path:

```svg
<!-- settings -->
<circle cx="12" cy="12" r="3.5" stroke="currentColor" stroke-width="2" fill="none"/>
<path d="M12 2 V5 M12 19 V22 M2 12 H5 M19 12 H22 M5.2 5.2 L7.3 7.3
         M16.7 16.7 L18.8 18.8 M18.8 5.2 L16.7 7.3 M7.3 16.7 L5.2 18.8"
      stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>

<!-- search -->
<circle cx="10.5" cy="10.5" r="5.5" stroke="currentColor" stroke-width="2" fill="none"/>
<path d="M14.4 14.4 L19.4 19.4" stroke="currentColor" stroke-width="2" fill="none"
      stroke-linecap="round"/>
```

Keep paths this simple. A detailed illustration is an image generator's job, not a path's — and
a path with hundreds of segments defeats the reason to use a vector in the first place.

### The import setting that decides whether it draws at all

A `.svg` dropped into `Assets/` imports, shows a preview, and still resolves to nothing from USS
if it was imported as a sprite. In the Inspector for the asset, the generated asset type has to
be set to the UI Toolkit vector image rather than a texture or sprite, then applied. The failure
mode is the one §0 of the skill warns about: a clean Console, a valid-looking `url()`, and an
empty box on screen. **Confirm the exact field label and options on your Editor version** — this
importer's inspector has changed shape before — but the check is the same either way: reimport,
then look at the element.

Two costs to keep in view: the import is a **tessellation**, so a detailed SVG becomes a lot of
triangles — simplify at the source, the same argument as `unity-3d-models`. And the imported asset
has to be set to produce a UI Toolkit vector image rather than a texture, or the USS reference
resolves to something that will not draw.
