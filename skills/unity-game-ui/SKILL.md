---
name: unity-game-ui
description: >-
  START HERE for a UI request naming no UI system: detects uGUI, UI Toolkit or
  IMGUI, routes to unity-ui-ugui or unity-ui-toolkit. Owns the runtime IMGUI
  (OnGUI) HUD with no Canvas, and what makes a UI survive real viewing
  conditions: colour, contrast, type sized by viewing distance, TextMeshPro
  font assets, SDF atlases, HUD placement, transitions. Use for "design the
  HUD", "the UI looks wrong / cheap / misaligned", "the text is too small",
  "the panels are the wrong colour", "the highlighted item does not stand
  out", "the glow is a grey smudge", "the art looks tiny in its box", "adding
  a fade broke the logic", "the buttons shimmer", "where should the timer go",
  or a multi-agent UI/UX review.
---

# unity-game-ui — a runtime UI that holds up in the room it is played in

A game's UI is read from wherever the game is actually played — a metre away on a couch, three
metres away from a projector, or in the hand. That distance, not thumb ergonomics, sets the type
scale. Everything else in this skill follows from taking it seriously.

First decide which UI system you are in.

---

## 0. Which UI system is this? (route before you build)

Not every question needs routing. **Comparative or teaching questions — "what's the difference
between UI Toolkit and uGUI", "which should I use on mobile" — get answered directly.** Route
only when the user wants to read, edit or generate actual UI.

**Explicit signals win.** If the user names a file or an API, that is the answer:

| They mention | System |
|---|---|
| `.uxml`, `.uss`, `UIDocument`, `CreateGUI()`, "UIElements" | UI Toolkit |
| `Canvas`, `RectTransform`, a `.prefab` containing UI, "legacy UI" | uGUI |
| `OnGUI`, `OnInspectorGUI`, "immediate mode" | IMGUI |
| An `EditorWindow`, a custom inspector, a `PropertyDrawer` | UI Toolkit — `unity-ui-toolkit` → `reference/editor-tooling.md` |

**No explicit signal — fingerprint the project.** Scan assets and scripts, **not
`Packages/manifest.json`**: uGUI and UI Toolkit are both built into Unity 6, so the manifest
cannot tell them apart.

```bash
# Quote every --include pattern: unquoted, zsh expands it against the CWD and
# grep never sees the flag — zsh fails with "no matches found".
find Assets \( -name '*.uxml' -o -name '*.uss' \) | head            # → UI Toolkit
grep -rl 'UIDocument\|CreateGUI' Assets --include='*.cs' | head     # → UI Toolkit
grep -rl 'RectTransform' Assets --include='*.unity' --include='*.prefab' | head   # → uGUI
grep -rl 'void OnGUI' Assets --include='*.cs' | head                # → IMGUI
```

Read the result as a whole: all four empty on a project that clearly has UI means you are
looking at the wrong directory, not that the project has no UI system.

**There is no automated Figma import in this toolchain** — no importer, no service call, nothing
to enable. The conversion people have seen exists only inside Unity's own in-Editor assistant, and
there is no client-side equivalent to call, so promising one costs a round trip and produces
nothing. A design link is therefore a reading task: ask for a description or a screenshot of the
screen and build it with the system §0 lands on.

**Still ambiguous — the default ladder:**

1. Existing project → follow whatever it already uses. Consistency beats preference.
2. New runtime UI, no preference stated → **uGUI**.
3. Mobile, or a stated performance constraint → lean **uGUI**.
4. New *editor* UI → **UI Toolkit**; IMGUI only if the project is already all-IMGUI.
5. Mixed project → match the closest existing UI of the same kind (runtime vs editor).

**Then hand off.** uGUI → `unity-ui-ugui`. UI Toolkit → `unity-ui-toolkit`. Runtime `OnGUI`
stays here. This skill does not duplicate the other two.

### And decide what kind of answer the request wants

Routing says *which* skill. This says *how much*. Three request shapes, and the output of each is
different:

| Shape | The request sounds like | What comes back |
|---|---|---|
| Understand | "what does this button do", "how is this screen laid out", "how many panels are in here" | An explanation of the components, the hierarchy and the events. **No file changes at all.** |
| Edit | "make the gate label amber", "move the hazard pip left", "this panel is too tall" | A change to exactly what was named, and nothing adjacent. |
| Generate | "build a pause screen", "make a lane-select menu" | Only the files that screen needs. |

Three phrasings read as more than they are, and all three mean *visuals*:

- **"proper buttons"** — styled buttons, not a button controller.
- **"working UI"** — markup and layout that render correctly, not wired behaviour.
- **"a menu screen"** — the arrangement of the screen, not the navigation between screens.

> **Do not add scripts unless the request asks for behaviour.** A `MonoBehaviour` nobody asked for
> is a file to review, a reference to wire, and a second owner of the layout. The signal is
> explicit — "with code", "make it functional", "hook up the logic", a named callback — and in its
> absence the honest move is to build the visuals and say plainly that nothing is wired yet.

Both system skills inherit this rather than restating it.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| uGUI Canvas hierarchies, RectTransform anchoring, Layout Groups | `unity-ui-ugui` |
| UXML / USS, flex layout, Painter2D, runtime binding | `unity-ui-toolkit` |
| Multi-language text pipelines, Asset Tables, tofu | `unity-localization` |

What is left is the case neither covers: **a runtime `OnGUI` HUD.** Immediate-mode UI is
normally documented as editor tooling, and that documentation carries no DPI scaling, no pixel
snapping, no event swallowing, no `GUI.skin` construction and no contrast method — all of which
decide whether a runtime HUD is readable. That gap is this skill.

Choosing IMGUI for a runtime HUD is a real trade, not a default: it survives a scene reload with
nothing to re-wire, and it costs you the layout system. Make it deliberately.

---

## The IMGUI primitive, and the two questions it hides

IMGUI draws **axis-aligned textured rectangles and nothing else**. No layout system, no
post-processing, no polygons. Everything — angular panels, glow, rounded glyphs, letter spacing —
is built from that one primitive, and every artefact people describe as "cheap" or "broken" comes
from one of a small number of arithmetic mistakes on top of it.

Two questions decide most of this skill, and both are usually answered wrong by default:

> **In what colour space are these numbers interpreted?** It differs by field. In a linear-space
> project IMGUI's `GUI.color` is linear — an sRGB hex typed in literally renders several stops too
> light — while uGUI's `Image.color` / `TMP_Text.color` are already sRGB and converting them
> darkens the whole palette. Alpha composites linearly either way, so `Scrim(0.7)` only darkens
> the image to 58%.
>
> **From how far away is this read?** A scale factor derived from "the same button size in
> millimetres in either orientation" encodes *handheld* ergonomics. If the game is played from
> two metres, the instruction text is below the resolving power of the eye reading it.

---

## Start here

1. **One shape, parameterised.** A rectangle with slanted left and right edges covers trapezoid,
   parallelogram and rectangle. Twelve panels built from it look like one kit; twelve bespoke
   shapes look like twelve screens. → `reference/imgui-kit.md`
2. **Know which colour field converts and which does not — and convert scrim alpha in both.**
   → `reference/colour-and-contrast.md`
3. **Derive type sizes from viewing distance, per role, and fit before you grow.**
   → `reference/type-scale.md`
4. **Snap to the pixel grid, and animate light rather than geometry.** → `reference/layout-math.md`
5. **Map the frame before placing anything.** → `reference/hud-placement.md`
6. **A screen being visible is not a screen being alive.** The day you add an exit fade, audit
   every `if (!Visible) return;`. → `reference/screen-transitions.md`

## Load what the situation needs

| The situation | Read |
|---|---|
| Which UI system this project uses; routing to the system-specific skill | §0 above |
| Runtime `OnGUI` mechanics: GUIStyle cost, DPI scaling, event swallowing | `reference/imgui-runtime.md` |
| Building the kit: shapes, glyphs, widgets, per-frame cost | `reference/imgui-kit.md` |
| CJK / mixed-script text, TMP sizing, text that costs CPU every frame | `reference/text-and-cjk.md` |
| Panels look washed out; a scrim does nothing; a highlight or glow that is not readable | `reference/colour-and-contrast.md` |
| Menu flow, fades, "it started twice", one-shot callbacks firing every frame | `reference/screen-transitions.md` |
| Choosing sizes; text overflowing a button; "too small to read" | `reference/type-scale.md` |
| "Misaligned polygons"; shimmering edges; aspect-ratio breakage; camera framing | `reference/layout-math.md` |
| Deciding WHERE things go; HUD covering gameplay; control layout per mode | `reference/hud-placement.md` |
| Running a structured multi-agent UI/UX review (only when asked) | `reference/ui-review-workflow.md` |
| Canvas / RectTransform / Layout Group work | skill `unity-ui-ugui` |
| UXML / USS / VisualElement work | skill `unity-ui-toolkit` |
| Shipping in more than one language; tofu boxes; Asset Tables | skill `unity-localization` |
| Verifying any of it — screenshots, shimmer, "it shakes" | skill `unity-debug` |

---

## Principles worth stating out loud

- **A screen spends decisions; it does not make them.** If `Fill`, `Border` and `Text` are
  redefined per screen, the screens will drift apart. That drift *is* the "cheap" look.
- **Cut words, never shrink them.** At a size that survives the viewing distance, a sentence spans
  the frame. Often the shorter replacement is also the more *correct* one.
- **Position beats caption.** Three on-screen buttons laid out left-middle-right are their own
  legend, and unlike a caption a position cannot contradict what it describes.
- **One palette entry, one meaning.** An amber that means reward, danger and defeat means nothing.
- **A colour is not a text colour until it has been measured.** Accent, warn and success hues
  often sit far below the 4.5:1 text floor against their own surface (e.g. 2.1–2.7:1): fills and
  icons, never words —
  and a shared text component must take its colour from the caller that knows the background.
- **Never let colour alone carry information.** Size and luminance survive distance and
  colour-blindness; a brief hue change does not. Measure it: a "this lane holds the pickup" cue at,
  e.g., 1.16:1 in luminance against its own idle state cannot be relied on at 2 m or by a red-green
  deficient player. Aim for 3:1 between the two states of a widget, or add a second channel.
- **A screen being visible is not a screen being alive.** The moment hiding stops being
  instantaneous, every `if (!Visible) return;` becomes a bug.
- **Anything drawn over gameplay needs a plate.** Magenta on grass, e.g., is 1.03–1.6:1
  luminance contrast — surviving on hue alone, invisible at distance.
- **Leave the vanishing point empty.** It is where everything the player must react to arrives.
- **Verify visually, not by assertion.** Overlap, clipping, contrast and cropping all pass every
  test. Screenshot the flow and read the images — `unity-debug`.
