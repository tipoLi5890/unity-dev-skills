# Canvas and CanvasScaler; text and components

Moved out of SKILL.md §1 and §4; same numbering. Scaler arithmetic in depth: [`reference/canvas-scaler-and-anchors.md`](canvas-scaler-and-anchors.md); text traps: [`reference/text-and-image-traps.md`](text-and-image-traps.md).

## 1. Canvas and CanvasScaler

```
Canvas  (Screen Space - Overlay, or Screen Space - Camera)
├─ CanvasScaler
└─ GraphicRaycaster
```

> **Set `renderMode` explicitly, always.** `AddComponent<Canvas>()` gives `renderMode = WorldSpace`,
> not the menu's Screen Space Overlay — an invisible quad at the origin. `CanvasScaler`'s default is
> not a decision either: [`reference/code-built-ui.md`](code-built-ui.md) §1.

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
> [`reference/canvas-scaler-and-anchors.md`](canvas-scaler-and-anchors.md).

`Screen Space - Camera`: read the camera's setup first — a Canvas can land behind or in front of
world geometry. Prefer anchors and Layout Groups to absolute positions; convert a position into a
new anchor's space *before* animating across regions, or it teleports (same reference, §4).

## 4. Text and components

- **TextMeshPro for all text**, worldspace included; legacy `Text` is not the current path. Sizing,
  contrast, CJK: `unity-game-ui` → `reference/text-and-cjk.md`.
- Text set from code: `LayoutRebuilder.ForceRebuildLayoutImmediate(parent)`, or the box keeps the
  old string's size. Active child swapped: `LayoutRebuilder.MarkLayoutForRebuild(column)`.
- **`NoWrap` + `TextOverflowModes.Ellipsis` in a short box renders nothing at all** — use
  `TextOverflowModes.Overflow` and clamp with layout. **`Image.preserveAspect = true` overrides the
  RectTransform** — set it false, use `Image.Type.Sliced`
  ([`reference/text-and-image-traps.md`](text-and-image-traps.md) §2, §4).
- **`Raycast Target = false` on every non-interactive Graphic** — it defaults to **`true`**;
  each is tested on every pointer event, and one left on is a common cause of "the
  button under it doesn't work" ([`reference/code-built-ui.md`](code-built-ui.md) §4).
- **A widget that caches "what I last drew" must invalidate that cache in `OnEnable`**
  ([`reference/code-built-ui.md`](code-built-ui.md) §5).
- **Rebuilds are per-Canvas**: per-frame values get their own child Canvas; every extra Canvas gets
  an explicit `sortingOrder`, since equal orders guarantee nothing about which is on top.
- Sprite atlases for more than a handful of sprites — unless the kit is geometry (§6).
- **Importing TMP essentials headlessly:** `TMP_PackageResourceImporter.ImportResources()`, never
  the menu item — [`reference/code-built-ui.md`](code-built-ui.md) §7.
