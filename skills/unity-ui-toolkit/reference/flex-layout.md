# Flex is the layout model

Moved out of SKILL.md §3: flex layout, sizing, a `UIDocument` with no `PanelSettings`, and fonts.

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
one: [`reference/panel-settings-and-text.md`](panel-settings-and-text.md).

**Editor UI needs none of this** — an `EditorWindow`, a custom inspector or a property drawer has
its own panel. §6.

**Text here is TextCore, not TextMeshPro.** A UI Toolkit label takes
`UnityEngine.TextCore.Text.FontAsset`; `TMPro.TMP_FontAsset` is **not** assignable to it. From USS
the property is `-unity-font-definition`; from C#,
`style.unityFontDefinition = FontDefinition.FromSDFFont(fontAsset)`. A CJK or multi-locale project
needs a real font pipeline — `unity-localization` → `reference/font-pipeline.md` — plus the
TextCore asset built alongside it. Type hierarchy, settings assets and the TextCore generator:
[`reference/panel-settings-and-text.md`](panel-settings-and-text.md).
