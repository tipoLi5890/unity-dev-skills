---
name: unity-game-ui
description: >-
  START HERE for any UI request: HUD, menus, text, colour, contrast, layout, a
  UI review. Detects uGUI, UI Toolkit or IMGUI and routes; owns the OnGUI HUD
  and UI design.
---

# unity-game-ui — a runtime UI that holds up in the room it is played in

A game's UI is read from wherever the game is played — a metre away on a couch, three metres from a
projector, or in the hand. That distance, not thumb ergonomics, sets the type scale. First decide
which UI system you are in; then make it survive real viewing conditions.

## Request → where to go

| The request | Go to |
|---|---|
| Any UI work, no UI system named | §0 below |
| "design the HUD", "where should the timer go", HUD covering gameplay | `reference/hud-placement.md` |
| "the UI looks wrong / cheap / misaligned", "the buttons shimmer" | `reference/layout-math.md`, `reference/design-principles.md` |
| "the text is too small", text overflowing a button | `reference/type-scale.md` |
| "the panels are the wrong colour", "the highlighted item does not stand out", "the glow is a grey smudge" | `reference/colour-and-contrast.md` |
| "the art looks tiny in its box", framing | `reference/layout-math.md` |
| "adding a fade broke the logic", "it started twice" | `reference/screen-transitions.md` |
| TextMeshPro font assets, SDF atlases, CJK text | `reference/text-and-cjk.md` |
| A runtime `OnGUI` HUD with no Canvas | `reference/imgui-runtime.md`, `reference/imgui-kit.md` |
| A structured multi-agent UI/UX review (only when asked) | `reference/ui-review-workflow.md` |
| "understand", "edit" or "build" — how much to change | `reference/routing.md` (request shape) |

## 0. Which UI system is this? (route before you build)

Teaching questions — "what's the difference between UI Toolkit and uGUI" — get answered
directly. Route only when the user wants to read, edit or generate actual UI.

**Explicit signals win.** If the user names a file or an API, that is the answer:

| They mention | System |
|---|---|
| `.uxml`, `.uss`, `UIDocument`, `CreateGUI()`, "UIElements" | UI Toolkit |
| `Canvas`, `RectTransform`, a `.prefab` containing UI, "legacy UI" | uGUI |
| `OnGUI`, `OnInspectorGUI`, "immediate mode" | IMGUI |
| An `EditorWindow`, a custom inspector, a `PropertyDrawer` | UI Toolkit — `unity-ui-toolkit` → `reference/editor-tooling.md` |

**No explicit signal** — fingerprint assets and scripts, not `Packages/manifest.json` (both
systems are built in); with nothing found, existing project → follow it, new runtime UI or mobile
→ uGUI, new editor UI → UI Toolkit. There is no automated Figma import: a design link is a reading
task. Commands, the full ladder and the request shapes: `reference/routing.md`.

**Then hand off.** uGUI → `unity-ui-ugui`. UI Toolkit → `unity-ui-toolkit`. Runtime `OnGUI` stays
here. **Do not add scripts unless the request asks for behaviour** — "proper buttons", "working
UI" and "a menu screen" all mean visuals.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| uGUI Canvas hierarchies, RectTransform anchoring, Layout Groups | `unity-ui-ugui` |
| UXML / USS, flex layout, Painter2D, runtime binding, editor tooling | `unity-ui-toolkit` |
| Multi-language text pipelines, Asset Tables, tofu | `unity-localization` |
| Verifying any of it — screenshots, shimmer, "it shakes" | `unity-debug` |

What is left: **a runtime `OnGUI` HUD**, and the design rules any UI needs to be readable —
colour space, contrast, type by viewing distance, placement, transitions
(`reference/design-principles.md`).
