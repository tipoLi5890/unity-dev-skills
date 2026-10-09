---
name: unity-ui-ugui
description: >-
  Build and repair Canvas-based UI in Unity: Canvas and CanvasScaler,
  RectTransform anchors, Layout Groups, ScrollView, and UI built entirely from
  C#. Load for requests naming Canvas, uGUI, RectTransform, Layout Group,
  CanvasRenderer, a custom Graphic or a .prefab containing UI, and for "the
  button does nothing when I click it", "the element is invisible", "my custom
  Graphic draws nothing", "the layout collapses to zero height", text that
  vanishes instead of truncating, "the HUD is cut off on a tablet", "the
  pressed button turns black", "the screenshot is one flat colour".
  Undetermined UI systems and runtime IMGUI HUDs start at unity-game-ui;
  UXML/USS is unity-ui-toolkit.
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
| The element is invisible | §2 visibility checklist |
| A custom `Graphic` / `MaskableGraphic` subclass draws nothing | §2, then `reference/code-built-ui.md` §2 |
| Clicking does nothing | §5 interaction readiness |
| Layout collapses, or children ignore the sizes you set | §3 |
| Content won't scroll, or the list duplicates on every reopen | §3 ScrollView |
| Wrong at another resolution; fine on a phone, cut off on a tablet | §1, then `reference/canvas-scaler-and-anchors.md` |
| A label renders nothing at all instead of truncating | §4 |
| Text cards overlap once real content arrives | §3, then `reference/text-and-image-traps.md` §1 |
| A dark button goes almost black while pressed | §5 |
| The whole screenshot is one flat colour | `reference/no-mask-lists-and-motion.md` §1 |
| Transitions freeze on the pause screen | `reference/no-mask-lists-and-motion.md` §3 |
| The UI is built from C# with no prefabs | `reference/code-built-ui.md` |
| Ambiguous-type compile errors on `Image` / `Button` | §0 |
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

## 1. Canvas and CanvasScaler

```
Canvas  (Screen Space - Overlay, or Screen Space - Camera)
├─ CanvasScaler
└─ GraphicRaycaster
```

> **Set `renderMode` explicitly, always.** `AddComponent<Canvas>()` gives `renderMode = WorldSpace`,
> not the menu's Screen Space Overlay — an invisible quad at the origin. `CanvasScaler`'s default is
> not a decision either: [`reference/code-built-ui.md`](reference/code-built-ui.md) §1.

**CanvasScaler is the resolution answer.** `Scale With Screen Size` at the design target's reference
resolution. `Constant Pixel Size` suits only pixel-art or a fixed-resolution target; as the default,
an existing one counts as unconfigured unless the layout shows otherwise. Changing it moves every
element — say so first.

> **`MatchWidthOrHeight = 0.5` is the common default, and it crops real devices**: at reference
> 1920×1080 a 4:3 tablet (2048×1536) gets **1663 × 1247** design px, so a panel at x 1260–1860
> loses everything past 1663.
> **`ScreenMatchMode.Expand` is the safer default for a fixed design frame:** it scales by
> `min(w/1920, h/1080)`, so the design space always *contains* the reference; the surplus is
> letterbox margin. Keep Match 0.5 only when the art must fill every aspect ratio and the edges are
> verified. Under `Expand`, **anything that must hug a corner anchors to it**. Per-aspect table and
> `DesignSize(w,h)`:
> [`reference/canvas-scaler-and-anchors.md`](reference/canvas-scaler-and-anchors.md).

`Screen Space - Camera`: read the camera's setup first — a Canvas can land behind or in front of
world geometry. Prefer anchors and Layout Groups to absolute positions; convert a position into a
new anchor's space *before* animating across regions, or it teleports (same reference, §4).

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

## 4. Text and components

- **TextMeshPro for all text**, worldspace included; legacy `Text` is not the current path. Sizing,
  contrast, CJK: `unity-game-ui` → `reference/text-and-cjk.md`.
- Text set from code: `LayoutRebuilder.ForceRebuildLayoutImmediate(parent)`, or the box keeps the
  old string's size. Active child swapped: `LayoutRebuilder.MarkLayoutForRebuild(column)`.
- **`NoWrap` + `TextOverflowModes.Ellipsis` in a short box renders nothing at all** — use
  `TextOverflowModes.Overflow` and clamp with layout. **`Image.preserveAspect = true` overrides the
  RectTransform** — set it false, use `Image.Type.Sliced`
  ([`reference/text-and-image-traps.md`](reference/text-and-image-traps.md) §2, §4).
- **`Raycast Target = false` on every non-interactive Graphic** — it defaults to **`true`**;
  each is tested on every pointer event, and one left on is a common cause of "the
  button under it doesn't work" ([`reference/code-built-ui.md`](reference/code-built-ui.md) §4).
- **A widget that caches "what I last drew" must invalidate that cache in `OnEnable`**
  ([`reference/code-built-ui.md`](reference/code-built-ui.md) §5).
- **Rebuilds are per-Canvas**: per-frame values get their own child Canvas; every extra Canvas gets
  an explicit `sortingOrder`, since equal orders guarantee nothing about which is on top.
- Sprite atlases for more than a handful of sprites — unless the kit is geometry (§6).
- **Importing TMP essentials headlessly:** `TMP_PackageResourceImporter.ImportResources()`, never
  the menu item — [`reference/code-built-ui.md`](reference/code-built-ui.md) §7.

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

Runtime `OnGUI` HUDs (`unity-game-ui`), UXML/USS (`unity-ui-toolkit`), type scale and contrast
(`unity-game-ui`), multi-language text pipelines (`unity-localization`), sprite import metadata and
9-slice borders (`unity-2d-sprites`), taking the screenshots this skill tells you to read
(`unity-debug`).

## Reference

- `reference/code-built-ui.md`
- `reference/canvas-scaler-and-anchors.md`
- `reference/layout-groups-and-scrollview.md`
- `reference/procedural-graphics.md`
- `reference/no-mask-lists-and-motion.md`
- `reference/text-and-image-traps.md`
