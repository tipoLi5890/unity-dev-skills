---
name: unity-ui-ugui
description: >-
  Canvas UI (uGUI): CanvasScaler, RectTransform anchors, Layout Groups, ScrollView, UI built from C#.
---

# unity-ui-ugui — Canvas UI, and the six ways it renders nothing

> **uGUI fails silently and looks fine doing it.** A zero-height element, a missing EventSystem,
> a custom `Graphic` with no `CanvasRenderer` and a Layout Group fighting a ContentSizeFitter all
> produce a hierarchy that inspects correctly and shows nothing. Almost every "it doesn't work"
> here is one of six checks.

Not sure the project is uGUI? `unity-game-ui` §0 has the detection ladder.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Canvas, uGUI, RectTransform, Layout Group, `CanvasRenderer`, a UI `.prefab` — working rules first | §0 |
| "The element is invisible" | §2 visibility checklist |
| "My custom Graphic draws nothing" — a `Graphic` / `MaskableGraphic` subclass | §2, then `reference/code-built-ui.md` §2 |
| "The button does nothing when I click it" | §5 interaction readiness |
| The layout collapses to zero height, or children ignore the sizes you set | §3 |
| Content won't scroll, or the list duplicates on every reopen | §3 ScrollView |
| Wrong at another resolution; "the HUD is cut off on a tablet" | [`reference/canvas-and-text.md`](reference/canvas-and-text.md) §1, then `reference/canvas-scaler-and-anchors.md` |
| Text vanishes instead of truncating | [`reference/canvas-and-text.md`](reference/canvas-and-text.md) §4 |
| Text cards overlap once real content arrives | §3, then `reference/text-and-image-traps.md` §1 |
| "The pressed button turns black" | §5 |
| "The screenshot is one flat colour" | `reference/no-mask-lists-and-motion.md` §1 |
| Transitions freeze on the pause screen | `reference/no-mask-lists-and-motion.md` §3 |
| The UI is built from C# with no prefabs | `reference/code-built-ui.md` |
| Ambiguous-type compile errors on `Image` / `Button` | §0 |
| Material count grows each rebuild; TMP outlines | `reference/text-and-image-traps.md` §6 |
| Making it readable at distance, contrast, type size | skill `unity-game-ui` |

## 0. Working rules

These are not style preferences; each one prevents a specific cascade.

- **Fully qualify UI types** (`UnityEngine.UI.Image`, `UnityEngine.UI.Button`); bare names collide,
  with `UnityEngine.UIElements` among others. **But `Canvas` and `RectTransform` are not in
  `UnityEngine.UI`** — `UnityEngine.UI.Canvas` does not exist. `Canvas` is in `UnityEngine`
  (assembly `UnityEngine.UIModule`); `Image`, `Button`, `CanvasScaler`, the Layout Groups and
  `EventSystem` are in `UnityEngine.UI` (assembly `UnityEngine.UI`).
- **Fix incrementally; never destroy and rebuild to repair.** Destroyed GameObjects take every
  inspector reference with them. **If a fix fails, revert it before the next one**, or you debug the
  sum of your attempts.
- **Apply the user's numbers exactly.** No rounding, no adjusting properties nobody asked about.
- **Build only what was asked.** "Working UI" / "proper buttons" mean visuals; scripts only when
  the request names behaviour (`unity-game-ui` §0).

Edit the hierarchy through a live Editor, not `.prefab` / `.unity` YAML — `unity-debug` →
`reference/editor-control.md`; the reasons are in `unity-cli`.

## 1. Canvas and CanvasScaler → `reference/canvas-and-text.md` §1

Render mode, the scaler's match and reference resolution, and why the HUD is cut off on a tablet.

## 2. RectTransform, anchoring, and why it is invisible

**Order matters.** Anchor preset → pivot → position/offsets. Pick **corner**, **edge** (stretch one
axis) or **fill**; set `anchorMin` / `anchorMax` (equal for a corner). **Set the pivot to match the
anchor.** A top-right element left at pivot `(0.5, 0.5)` sits half off-screen. Then offsets, which
set earlier would mean something else a moment later.

**Visibility checklist — run all six before concluding anything is wrong elsewhere:**

- Width **and** height are greater than zero.
- The element is inside its parent's bounds.
- It is not behind a sibling (later draws on top): insert mid-stack with `SetSiblingIndex(n)`;
  `SetAsFirstSibling()` puts it *under* every opaque sibling and looks like a colour bug.
- The `Image` has a sprite, or a colour with alpha > 0.
- Every ancestor is active and has non-zero scale.
- **A custom `Graphic` has a `CanvasRenderer` on the same GameObject.** The multi-`Type` `GameObject`
  constructor ignores `[RequireComponent]`, so
  `new GameObject("Card", typeof(RectTransform), typeof(MyGraphic))` logs and draws nothing — list
  `typeof(CanvasRenderer)` ([`reference/code-built-ui.md`](reference/code-built-ui.md) §2).

Non-zero size comes from exactly one of an explicit `sizeDelta`, stretch anchors with sane offsets,
or a parent Layout Group with Control Child Size on. Mixing them is §3.

## 3. Layout Groups, and the conflict that eats an afternoon

**When a parent has a Layout Group, the parent owns its children's RectTransforms.** Anchors and
`sizeDelta` are overwritten every layout pass. Decide who owns size *before* setting any number.

| Combination | Result |
|---|---|
| ContentSizeFitter on a **child** whose parent controls size | Silently overridden; the component does nothing |
| Layout Group on something that must keep a fixed size | The fixed size is gone |
| Nested Layout Groups | Legal, but every level must be configured deliberately |
| A decorative graphic parented under a Layout Group | Laid out as a row — set `LayoutElement.ignoreLayout = true` |

- A `ContentSizeFitter` **on the same object** as a `VerticalLayoutGroup` is suspicious, not
  broken; `Control Child Size` off does **not** collapse children to zero. The rebuild check,
  `Child Force Expand`, `GridLayoutGroup` and what a fitter needs:
  [`reference/layout-groups-and-scrollview.md`](reference/layout-groups-and-scrollview.md) §1.
- **Do not size a card from TMP's `preferredHeight` inside nested Layout Groups.** The first-frame
  value predates wrapping. Fixed `LayoutElement` (`min = preferred = fixed`, `flexibleHeight = 0`),
  `TextOverflowModes.Ellipsis`, an arithmetic column budget:
  [`reference/text-and-image-traps.md`](reference/text-and-image-traps.md) §1.

### ScrollView — three objects, three jobs

> **A `ScrollRect` on its own clips nothing and scrolls nothing.** Each failure is one of the three
> objects incomplete.

```
ScrollView      ScrollRect
├─ Viewport     RectTransform + Mask + Image   ← the Image is what the Mask stencils
│  └─ Content   RectTransform + VerticalLayoutGroup + ContentSizeFitter (Vertical Fit = Preferred Size)
│     └─ items — authored, or built at runtime
└─ Scrollbar    optional, a sibling of Viewport — never a child of it
```

Content is the one object where a Layout Group and a ContentSizeFitter belong together. **Wire
`content` and `viewport`** — a ScrollRect with a null `content` never moves. **`Mask` brings no
`Image`**, so a Viewport with a Mask and no Image has nothing to stencil with. **Empty Content
before populating it**, or the list doubles on every reopen. Failure table and clearing loop:
[`reference/layout-groups-and-scrollview.md`](reference/layout-groups-and-scrollview.md) §2.
Without masks, a slot pool or a repainted page replaces a `ScrollRect` —
[`reference/no-mask-lists-and-motion.md`](reference/no-mask-lists-and-motion.md) §2.

**When layout is wrong, look at the parent first.** The mistake is nearly always one level up.

## 4. Text and components → `reference/canvas-and-text.md` §4

TextMeshPro labels that render nothing instead of truncating, and the components a control needs.

## 5. Interaction readiness — the four-item gate

Before calling any interactive UI done:

1. **Exactly one `EventSystem` in the scene, with the right input module.** Zero: nothing is
   clickable; two: undefined behaviour. A fresh scene has **none** — `EventSystem.current` is `null` until something
   adds one. **With Active Input Handling (Player Settings) set to Input System (New), a
   `StandaloneInputModule` receives nothing**: use `InputSystemUIInputModule`, guarded with
   `#if ENABLE_INPUT_SYSTEM` if the project may build either way.
2. **`GraphicRaycaster` on the Canvas.**
3. **`Raycast Target = true`** on the interactive element, false on whatever is layered over it. An
   element with **no** Graphic cannot be clicked; a transparent `Image` plus `Transition.None` is the
   standard invisible hit box.
4. `Button.onClick` wired, if logic was actually requested.

Miss any of the first three and the UI is visually perfect and completely inert.

**`ColorTint` multiplies, it does not replace.** A pressed colour darkened from the fill displays
`fill × (fill × 0.85)`, and a dark button goes almost black. Use a brightness multiplier,
`new Color(0.85f, 0.85f, 0.85f, 1f)` —
[`reference/procedural-graphics.md`](reference/procedural-graphics.md).

**Animate on `Time.unscaledDeltaTime`**, or transitions freeze on a `timeScale = 0` pause screen,
and drop `blocksRaycasts` on a view fading out so a fast second tap is not swallowed
([`reference/no-mask-lists-and-motion.md`](reference/no-mask-lists-and-motion.md) §3).

## 6. Drawing the kit without sprites, and lists without masks

- **Buttons, cards, frames, focus rings, glows and rules can be vertex geometry** on
  `MaskableGraphic` subclasses instead of 9-sliced PNGs: default UI material, sharp at any
  resolution, animated by field assignment. Techniques, and a progress **outline**
  (`Image.Type.Filled` fills a solid shape, not a ring):
  [`reference/procedural-graphics.md`](reference/procedural-graphics.md).
- **`RectMask2D` / `Mask` need the UI shader's clipping variants.** Where those cannot compile, a
  PlayMode screenshot with a mask comes back one flat colour (e.g. solid cyan), content blank, no
  error: suspect a shader variant before your layout. Mask-free lists:
  [`reference/no-mask-lists-and-motion.md`](reference/no-mask-lists-and-motion.md).

## 7. When something goes wrong

**"Start fresh" destroys the working parts along with the broken one** — in a prefab hierarchy,
every reference into it. After two failed attempts, re-verify the current state: usually an
earlier change never applied, and everything since has reasoned about a hierarchy that does not
exist.

## 8. Verify

uGUI passes every assertion while rendering nothing: screenshot the screen and read the image
(`unity-debug`). Two things a screenshot cannot do have an EditMode substitute:

- **Prove a procedural `Graphic` produced geometry.** `Canvas.ForceUpdateCanvases()`, then assert
  the vertex count of `graphic.canvasRenderer.GetMesh()` (`reference/code-built-ui.md` §3).
- **Change resolution.** Assert the scaler arithmetic as a pure function across 16:9 / 16:10 / 4:3
  / 21:9 (`reference/canvas-scaler-and-anchors.md` §2); real devices stay on a manual checklist.

Before calling it done, state rather than assume: each new element's width and height as numbers;
the EventSystem count (exactly 1) and its input module; who owns size for each element touched; the
screen at a second aspect ratio — one resolution proves nothing about a CanvasScaler.

## Scope — what this skill does NOT do

A UI request whose system is not yet determined, and runtime `OnGUI` HUDs (`unity-game-ui`), UXML/USS (`unity-ui-toolkit`), type scale and contrast
(`unity-game-ui`), multi-language text pipelines (`unity-localization`), sprite import metadata and
9-slice borders (`unity-2d-sprites`), taking the screenshots this skill tells you to read
(`unity-debug`).

## Reference

- `reference/canvas-and-text.md` (§1, §4)
- `reference/code-built-ui.md`
- `reference/canvas-scaler-and-anchors.md`
- `reference/layout-groups-and-scrollview.md`
- `reference/procedural-graphics.md`
- `reference/no-mask-lists-and-motion.md`
- `reference/text-and-image-traps.md`
