# Designing a runtime UI that holds up in the room it is played in

> Part of the `unity-game-ui` skill. A game's UI is read from wherever the game is actually played —
> a metre away on a couch, three metres away from a projector, or in the hand. That distance, not
> thumb ergonomics, sets the type scale. The two questions, the build order and the principles.

## Why a runtime `OnGUI` HUD is this skill's own

uGUI and UI Toolkit each have their own skill. What is left is the case neither covers: **a runtime
`OnGUI` HUD.** Immediate-mode UI is
normally documented as editor tooling, and that documentation carries no DPI scaling, no pixel
snapping, no event swallowing, no `GUI.skin` construction and no contrast method — all of which
decide whether a runtime HUD is readable. That gap is this skill.

Choosing IMGUI for a runtime HUD is a real trade, not a default: it survives a scene reload with
nothing to re-wire, and it costs you the layout system. Make it deliberately.

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

## Build order

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
