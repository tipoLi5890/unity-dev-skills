---
name: unity-ui-toolkit
description: >-
  UI Toolkit (UXML, USS, UIDocument): flex layout, binding, custom elements, editor windows.
---

# unity-ui-toolkit — USS is a subset of CSS, and it fails quietly

> **An unsupported USS property is not an error. It is ignored.** No console warning in many
> cases, no visual difference, nothing to grep for. Writing `gap`, `z-index` or `box-shadow`
> out of CSS habit produces a stylesheet that parses cleanly and lays out wrong — which is why
> §1 is a list of things that do not exist rather than a list of things that do.

Not sure the project is UI Toolkit? `unity-game-ui` §0 has the detection ladder.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Authoring `.uxml` / `.uss`, a `UIDocument`, `VisualElement` or `Manipulator` from scratch | §0, then §1–§4 |
| Nothing renders at all, and the Console is clean | [`reference/flex-layout.md`](reference/flex-layout.md) — a `UIDocument` with no `PanelSettings` |
| "The USS property does nothing" — a style property has no effect | §1 — it probably does not exist |
| A rule loses to another rule; tokens, hover states, 9-slice | `reference/uss-patterns.md` |
| The hover transition only animates one way: in, then snaps back out | §2 |
| "The layout ignores my width" — elements ignore the width/height you set | [`reference/flex-layout.md`](reference/flex-layout.md) |
| The layout is right but nothing responds to clicks | §4 |
| It parses but renders wrong | §2 |
| Need a gradient, a custom shape, a meter | §5 |
| Drag-and-drop between inventory or crafting slots | §4 |
| The bound label never updates, or updates one way only | §4 |
| A custom element does not resolve from UXML | §5 |
| An editor window, custom inspector or property drawer | §6 |
| Text needs a font asset, or shows tofu | [`reference/flex-layout.md`](reference/flex-layout.md), then `unity-localization` |

**There is no automated design-file import in this toolchain.** A link to a mockup in a
browser-based design tool converts to nothing here. Say that plainly rather than promising a
conversion, then ask for a description or a screenshot and build the screen the ordinary way.

## 0. You cannot validate these files from outside the Editor

UXML and USS are parsed on import. There is no offline linter, so mistakes cost a round trip
through a human or a live Editor. Two consequences:

- **Write complete files, never partial ones.** A half-written UXML file is a parse error the
  instant the Editor picks it up — and if the Editor is watching, it picks it up mid-save.
- **Finish every file before asking for a check**, so one reimport covers the whole change.
- **Build only what was asked.** "Proper buttons" and "a menu screen" are styling and layout, not
  behaviour — add scripts only when the request does. Full rule: `unity-game-ui` §0.

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

Two near-misses that belong in neither column — `filter`, which does exist, and
`transition-property`, which exists but ignores a named property value — are in
[`reference/uss-patterns.md`](reference/uss-patterns.md).

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

## 3. Flex is the layout model → `reference/flex-layout.md`

Why elements ignore the width you set, grow and shrink, a `UIDocument` that renders nothing
without `PanelSettings`, and text that needs a font asset.

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

Two things bite before the first line of layout: editor code must live in an `Editor` folder or an
editor-only assembly, and `CreateGUI` / `OnGUI` are called by name rather than declared. Both, with
their failure shapes, plus templates for all three entry points, the undo contract
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
  here (`reference/flex-layout.md`).
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

- [`reference/flex-layout.md`](reference/flex-layout.md) — §3: flex layout, `PanelSettings`, fonts
- [`reference/runtime-binding.md`](reference/runtime-binding.md) — data binding
- [`reference/manipulators-and-drag-drop.md`](reference/manipulators-and-drag-drop.md) — drags,
  drop targets, inventory and crafting
- [`reference/painter2d-and-custom-elements.md`](reference/painter2d-and-custom-elements.md) —
  custom elements, attribute converters, Painter2D, vector icons
- [`reference/editor-tooling.md`](reference/editor-tooling.md) — editor windows, inspectors,
  property drawers
- [`reference/panel-settings-and-text.md`](reference/panel-settings-and-text.md) — `PanelSettings`
  and TextCore font assets
- [`reference/uss-patterns.md`](reference/uss-patterns.md) — tokens, state tints, wrapping,
  9-slice, selector cost, specificity
