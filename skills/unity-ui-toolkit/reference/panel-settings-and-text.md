# PanelSettings, and text in UI Toolkit

> Part of the `unity-ui-toolkit` skill. Read when a runtime `UIDocument` needs its panel set up, or
> when a label needs a font asset. SKILL.md §3 holds the rules; this file holds the surface.

## `PanelSettings`

Search the project for an existing `PanelSettings` first and reuse it — a second one is a second
scale mode and a second theme to keep in sync. If there is none, create one (`Assets/UI/` is the
usual home) and assign it to the document's Panel Settings field.

`PanelSettings` is a `ScriptableObject` whose properties parallel a Canvas Scaler's:
`scaleMode` (`ConstantPixelSize`, `ConstantPhysicalSize`, `ScaleWithScreenSize`), `screenMatchMode`
(`MatchWidthOrHeight`, `Shrink`, `Expand`), `referenceResolution`, `match`, `sortingOrder`,
`renderMode` (`ScreenSpaceOverlay`, `WorldSpace`), `targetTexture`, `themeStyleSheet` and
`bindingLogLevel`. The trade between `MatchWidthOrHeight` and `Expand` is the one
`unity-ui-ugui` → `reference/canvas-scaler-and-anchors.md` works through for a 4:3 tablet, and the
same answer applies. `bindingLogLevel` is the binding debugger — `reference/runtime-binding.md`
has it.

## Text is TextCore, not TextMeshPro

A UI Toolkit label takes `UnityEngine.TextCore.Text.FontAsset`; `TMPro.TMP_FontAsset` is a
different type in a different assembly and is **not** assignable to it — the two hierarchies do not
meet (`FontAsset : UnityEngine.TextCore.Text.TextAsset` vs `TMP_FontAsset : TMPro.TMP_Asset`).
`TextSettings`, `PanelTextSettings` and `TextStyleSheet` are the TextCore spellings of the settings
assets. From USS the property is `-unity-font-definition`; from C#,
`style.unityFontDefinition = FontDefinition.FromSDFFont(fontAsset)` (`FromFont` takes the legacy
`Font`).

A CJK or multi-locale project needs a real font pipeline — that is `unity-localization` →
`reference/font-pipeline.md`, whose scripts build `TMP_FontAsset`s for Canvas text. A UXML screen in
the same project needs the TextCore asset built alongside them, and the generator has the same
shape: `FontAsset.CreateFontAsset(Font, samplingPointSize, atlasPadding, GlyphRenderMode,
atlasWidth, atlasHeight, AtlasPopulationMode, enableMultiAtlasSupport)` is a static overload on the
TextCore type, so the atlas-size and dynamic-population reasoning in that file carries over
unchanged — only the type name differs.
