---
name: unity-ui-toolkit
description: >-
  Author UI Toolkit interfaces in Unity 6: UXML, USS, flex layout, custom
  elements, Painter2D, manipulators and runtime binding. Load for requests
  naming .uxml, .uss, UI Toolkit, UIElements, UIDocument, PanelSettings,
  VisualElement or Manipulator, and for "the USS property does nothing", "the
  hover transition only animates one way", "the layout ignores my width", "the
  bound label never updates", drag-and-drop between inventory or crafting
  slots, a custom element that will not resolve from UXML, or an editor
  window, custom inspector or property drawer. Canvas-based UI is
  unity-ui-ugui; runtime IMGUI HUDs are unity-game-ui.
---

# unity-ui-toolkit — USS is a subset of CSS, and it fails quietly

> **An unsupported USS property is not an error. It is ignored.** No console warning in many
> cases, no visual difference, nothing to grep for. Writing `gap`, `z-index` or `box-shadow`
> out of CSS habit produces a stylesheet that parses cleanly and lays out wrong — which is why
> §1 is a list of things that do not exist rather than a list of things that do.

Not sure the project is UI Toolkit? `unity-game-ui` §0 has the detection ladder.

**There is no automated design-file import in this toolchain.** A link to a mockup in a
browser-based design tool converts to nothing here. Say that plainly rather than promising a
conversion, then ask for a description or a screenshot and build the screen the ordinary way.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Nothing renders at all, and the Console is clean | §3 — a `UIDocument` with no `PanelSettings` |
| A style property has no effect | §1 — it probably does not exist |
| Hover animates in but snaps back out | §2 |
| Elements ignore the width/height you set | §3 |
| The layout is right but nothing responds to clicks | §4 |
| It parses but renders wrong | §2 |
| Need a gradient, a custom shape, a meter | §5 |
| Drag-and-drop, an inventory or crafting slot | §4 |
| A bound value never updates, or updates one way only | §4 |
| A custom element does not resolve from UXML | §5 |
| An editor window, custom inspector or property drawer | §6 |
| Text needs a font asset, or shows tofu | §3, then `unity-localization` |

## 0. You cannot validate these files from outside the Editor

UXML and USS are parsed on import. There is no offline linter, so mistakes cost a round trip
through a human or a live Editor. Two consequences:

- **Write complete files, never partial ones.** A half-written UXML file is a parse error the
  instant the Editor picks it up — and if the Editor is watching, it picks it up mid-save.
- **Finish every file before asking for a check**, so one reimport covers the whole change.

Best case, drive a live Editor and trigger the reimport yourself —
`unity-debug` → `reference/editor-control.md`. Failing that, ask the user to focus the Editor
and report the Console: UXML parse errors name file and line; USS problems appear as warnings
about unknown properties or selectors. **The mistakes in §2 survive the parse and appear
nowhere in the Console** — those need eyes on the UI.

## 1. Properties that do not exist in USS

| Reach for | Use instead |
|---|---|
| `border` shorthand | `border-width`, `border-color` separately |
| `gap` | `margin` on the children |
| `z-index` | Document order, or nest under a different parent |
| `pointer-events` | `picking-mode` — a UXML attribute, not a style |
| `outline` | `border-*` |
| `box-shadow` | A nested element, or a background image |
| `:first-child`, `:last-child`, `:nth-child` | Explicit classes |
| `[attribute]` selectors | Explicit classes |
| `linear-gradient()`, `radial-gradient()` | `FillGradient` on a Painter2D element — §5 |

Enumerating `UnityEngine.UIElements.IStyle` shows `gap`, `zIndex`, `boxShadow`, `outline`,
`pointerEvents` and the shorthand `borderWidth` all **absent**, while `borderTopWidth`,
`backgroundImage` and `flexGrow` are present. `picking-mode` takes exactly `Position` or `Ignore`.

> **`filter` does exist.** A common belief is that USS lacks it; it is wrong. Check what it
> actually does on your version before using it; "it exists" is not "it behaves like the CSS one".

**`transition-property` also exists**, so it is not in the table above. The restriction is on its
**values**: naming a specific property is ignored. Use `none` / `initial` / `inherit`, or leave it
out and let the other `transition-*` properties do the work.

Three more absolutes:

- **Never `style="…"` in UXML.** Inline styles carry per-element memory overhead and put styling
  somewhere no stylesheet can override.
- **Never `url()` with an external path.** Only `url("project://database/Assets/…")`.
- **Do not reference `UnityDefaultRuntimeTheme.tss`** or built-in theme icons; build styles from
  project assets instead, or the UI inherits an editor look that will change under you.

## 2. Things that parse and still render wrong

**Transitions belong on the base selector, not the state.** On the state, the property is only
defined while hovering — so it animates in and snaps back out.

```uss
/* wrong — no animation on hover-out */
.button:hover { background-color: blue; transition-duration: 0.2s; }

/* right */
.button       { background-color: white; transition-duration: 0.2s; }
.button:hover { background-color: blue; }
```

**An unclosed brace swallows the next rule** rather than erroring where you left it — the
symptom is "the rule after the broken one stopped applying".

**Hardcoded percentage widths** are the flex equivalent of absolute positioning: `width: 33%`
breaks the moment padding, margin or a scrollbar exists. `flex-grow: 1` is what you meant.

## 3. Flex is the layout model — let it be

- Use `flex-grow`, `flex-shrink` and percentages; set explicit pixel sizes only on a root
  container or where a fixed size is genuinely required.
- Children should adapt to available space rather than declare their own dimensions. An element
  that "ignores" its width is usually being sized by a flex parent that was told to.
- `flex-direction: column` is already the default — writing it is noise.
- `flex: 1` already sets grow, shrink and basis; adding them separately is a contradiction
  waiting to happen.
- Do not add `min-width` / `max-width` around a fixed `width` that is already fixed.
- Use the simplest selector that works, and never define the same selector twice.

**Every UXML file:** declares its namespace, links its stylesheet, has exactly one top-level
container, and carries no `style` attributes.

```uxml
<ui:UXML xmlns:ui="UnityEngine.UIElements">
  <ui:Style src="Panel.uss" />
  <ui:VisualElement name="root" class="panel">
    <!-- content -->
  </ui:VisualElement>
</ui:UXML>
```

**Naming, and it is not one convention but two:** the `name` attribute is camelCase
(`submitButton`); classes and USS selectors are kebab-case (`.submit-button`). Files live in
feature folders (`Assets/UI/Inventory/`), not in a global `Scripts/UI/`. Match whatever the
project already does before applying any of this.

### Getting it on screen: `UIDocument` needs a `PanelSettings`

> **A `UIDocument` with no `PanelSettings` assigned renders nothing.** The symptom is exactly the
> one §0 cannot catch: the file imported, the Console is clean, the hierarchy looks right, and the
> screen is empty. Check the field first, before doubting the markup — and look in a windowed
> Editor, since nothing renders under `-batchmode` either way.

Runtime UI is a `UIDocument` component holding a `VisualTreeAsset` plus a `PanelSettings` asset.
`UIDocument.panelSettings` and `UIDocument.visualTreeAsset` are both settable properties, so a
scripted setup assigns both. Reuse the project's existing `PanelSettings` rather than adding a
second scale mode and theme. Its properties, which parallel a Canvas Scaler's, and where to create
one: [`reference/panel-settings-and-text.md`](reference/panel-settings-and-text.md).

**Editor UI needs none of this** — an `EditorWindow`, a custom inspector or a property drawer has
its own panel. §6.

**Text here is TextCore, not TextMeshPro.** A UI Toolkit label takes
`UnityEngine.TextCore.Text.FontAsset`; `TMPro.TMP_FontAsset` is **not** assignable to it. From USS
the property is `-unity-font-definition`; from C#,
`style.unityFontDefinition = FontDefinition.FromSDFFont(fontAsset)`. A CJK or multi-locale project
needs a real font pipeline — `unity-localization` → `reference/font-pipeline.md` — plus the
TextCore asset built alongside it. Type hierarchy, settings assets and the TextCore generator:
[`reference/panel-settings-and-text.md`](reference/panel-settings-and-text.md).

## 4. Interactivity, and the data behind it

Attach a **PointerManipulator** to the element rather than wiring callbacks from the outside —
it keeps the behaviour with the thing that has it, and it is how drag-and-drop is expressed at
all. A plain click is `Button`'s own `clicked` event, or a `Clickable` attached from C#: there is
**no UXML attribute that attaches one** — `Button`'s only UXML attribute of its own sets its icon
image, and `Clickable` is an ordinary `PointerManipulator` subclass with no UXML-object attribute.
Reach for explicit C# event callbacks only when the interaction genuinely spans elements.

Anything drag-shaped needs four events, a pointer capture and a decision about `picking-mode` on
the item being dragged; moving it with `translate` rather than `left`/`top` is what keeps a
fifty-slot inventory smooth. Full pattern, drop-target detection, and the questions to ask before
building an inventory or crafting screen at all:
[`reference/manipulators-and-drag-drop.md`](reference/manipulators-and-drag-drop.md).

**Values that should follow game state get a binding, not an `Update`.** The member on the far end
of a binding has to be a property carrying `[CreateProperty]` — a public field resolves to nothing,
silently, and the label simply never changes. `BindingMode` has **four** values, not the three
usually quoted: `TwoWay`, `ToSource`, `ToTarget`, `ToTargetOnce`. Modes, `nameof` paths, the UXML
`<Bindings>` form, the root `data-source` that makes design-time preview work, the enable/disable
lifecycle, and when binding is the wrong tool:
[`reference/runtime-binding.md`](reference/runtime-binding.md).

## 5. Drawing what USS cannot, and elements of your own

Gradients, custom shapes, meters, graphs: a custom `VisualElement` with `generateVisualContent`
and Painter2D. Gradients have a real API — `FillGradient.MakeLinearGradient` /
`MakeRadialGradient` assigned to `painter2D.fillGradient` — so this is not "hand-build the ramp".
Reusable elements: `[UxmlElement]` needs `partial`, the old factory attributes are obsolete, the
UXML namespace declaration must carry no assembly name, C# camelCase becomes UXML kebab-case, and
an element that *draws* derives from `VisualElement` directly. The factories, `AddressMode`, the
`Arc` / `Angle` / `ArcDirection` signatures, `Fill(FillRule)`, `ctx.DrawText`, attribute
converters and where icons should come from:
→ [`reference/painter2d-and-custom-elements.md`](reference/painter2d-and-custom-elements.md)

## 6. Editor windows, inspectors and property drawers

Editor UI is the one place immediate-mode `OnGUI` is still a legitimate choice, and the rule is
narrow: **anything new defaults to UI Toolkit** — `CreateGUI` on an `EditorWindow`,
`CreateInspectorGUI` on an `Editor`, `CreatePropertyGUI` on a `PropertyDrawer`. Immediate mode
only when maintaining code that already has `OnGUI` in it, when every editor tool in the project
is immediate-mode, or when the request names `OnGUI` directly.

A script touching `UnityEditor` must sit in an `Editor` folder or an editor-only assembly, or it
breaks the **player** build rather than the Editor. Neither `CreateGUI` nor `OnGUI` is declared on
`EditorWindow` at all — they are called by name, so `override` will not compile and a misspelling
opens an empty window with a clean Console. Templates for all three, the undo contract
(`serializedObject.Update()` … `ApplyModifiedProperties()`), and the immediate-mode cost rules:
[`reference/editor-tooling.md`](reference/editor-tooling.md).

## 7. What costs performance

In descending order — the first is usually the whole answer:

1. **Hierarchy size.** Depth and element count dominate everything else.
2. **`:hover` on a parent with many children** invalidates the whole subtree on every enter and
   leave.
3. **Many classes per element** — selector matching degrades linearly.
4. **Inline styles** — per-element memory, and they defeat sharing.
5. **Layout writes in a pointer-move handler.** Setting `left`/`top` per frame runs a layout pass
   per frame; `translate` is applied after layout and skips it.

## 8. Verify

The Console catches parse errors; nothing catches §2. So:

- Confirm the reimport actually happened — a silent Console can mean "no errors" or "the Editor
  never picked the file up", and those look identical.
- If nothing appears at all, check the `UIDocument`'s Panel Settings field before anything else:
  a missing `PanelSettings` gives an empty screen, a clean Console, and passes every other check
  here (§3).
- Read back the properties you set. A property that does not exist was accepted, ignored, and
  reported nowhere.
- Look at the screen at two window sizes. A layout that only works at one size is the usual
  symptom of hardcoded percentages.
- Hover, click and drag anything interactive. `picking-mode` and a missing manipulator both
  produce a perfect-looking, inert UI.
- Change the value behind a binding and watch the element. A binding that resolved to nothing is
  indistinguishable from one that works until the number moves.

## Scope — what this skill does NOT do

Canvas/uGUI (`unity-ui-ugui`), runtime `OnGUI` HUDs and the UI-system detection ladder
(`unity-game-ui`), type scale and viewing distance (`unity-game-ui` →
`reference/type-scale.md`), multi-language pipelines (`unity-localization`). Editor tooling is in
scope only as UI — build automation and headless invocation are `unity-cli`, and connecting to a
live Editor to reimport what you wrote is `unity-debug`.

## Reference

- [`reference/runtime-binding.md`](reference/runtime-binding.md) — data binding
- [`reference/manipulators-and-drag-drop.md`](reference/manipulators-and-drag-drop.md) — drags,
  drop targets, inventory and crafting
- [`reference/painter2d-and-custom-elements.md`](reference/painter2d-and-custom-elements.md) —
  custom elements, attribute converters, Painter2D, vector icons
- [`reference/editor-tooling.md`](reference/editor-tooling.md) — editor windows, inspectors,
  property drawers
- [`reference/panel-settings-and-text.md`](reference/panel-settings-and-text.md) — `PanelSettings`
  and TextCore font assets
