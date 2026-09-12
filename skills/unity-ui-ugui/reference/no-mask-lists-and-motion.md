# Lists without a mask, and screen motion that survives a pause

> Part of the `unity-ui-ugui` skill. Read when a screenshot comes back one flat colour, when a
> carousel or long list needs clipping, or when transitions freeze on the pause screen.

## 1 · A flat-colour screenshot is a shader-variant symptom, not a layout bug

`RectMask2D` and `Mask` need the UI shader's **clipping variants**. When the Editor cannot compile
those variants — e.g. because the platform shader toolchain component is absent — the failure mode
is not an error: a PlayMode screenshot containing a `RectMask2D` comes back **one flat colour
(e.g. solid cyan) with the masked content blank**. It looks exactly like a colour or alpha bug.

Two things follow:

- **If a screenshot walk returns a flat frame, suspect a missing shader variant or a clipping
  material before touching your layout.** `[Assert] m_Shader == nullptr` logged from the Editor's
  own UI shaders is a strong tell.
- **A UI that never masks cannot hit this at all.** Banning `RectMask2D`/`Mask` in new UI and
  building the screens that need clipping without them (§2) is a design choice with a real cost —
  it constrains how lists are built — but it removes a whole class of environment dependency.

Other platforms or driver setups may show pink, black or a hard error instead of cyan: treat the
colour as a hint, not a diagnosis.

## 2 · Two mask-free list patterns

### Infinite carousel — a fixed slot pool with modular mapping

For a PS5-style ring of cards with the focus fixed at centre:

- Create a fixed pool of `2 · half + 1` slots. Slot `k` always shows item `(selected + k) mod N`,
  so the list never reaches an end and no item is ever instantiated mid-animation.
- On a selection change, **re-map the slot contents first**, then set `scroll = delta · Step` and
  ease it back to `0` over 0.12 s with an out-cubic curve. The content jumps, the offset animates,
  and what the eye sees is a continuous slide.
- Clipping is replaced by a per-slot `CanvasGroup.alpha` that falls off with distance from centre.
- Slots that end up outside the viewport are simply `SetActive(false)` — cheaper than clipping them.

### Paged list — repaint the page, do not scroll it

For a history or settings list, keep N row widgets (e.g. 8) and repaint all of
them on a page change. No mask, no `ScrollRect`, no content-size arithmetic, and it maps directly
onto page-forward/page-back input from a device that has no analogue axis.

## 3 · The uGUI mechanics of a screen transition

What a transition should *look* like — durations, direction, and the "hidden but still running"
bug an exit fade introduces — is `unity-game-ui` → `reference/screen-transitions.md`. What follows
is only the part that is specific to Canvas UI.

- **`Time.unscaledDeltaTime` everywhere in UI animation.** A pause screen runs at `timeScale = 0`,
  and any transition on scaled time freezes on exactly the screen where the user is most likely to
  be looking at it.
- **Exponential easing is the cheap frame-rate-independent glide:**
  `t = 1 − Mathf.Exp(−speed · Time.unscaledDeltaTime)`, then `Vector2.Lerp`/`Mathf.Lerp` by `t`.
  At `speed = 18` that reaches ~90 % in 0.12 s — used for a focus ring's `offsetMin`/`offsetMax`;
  at `speed = 14` for a moving HUD element. Snap to the target below a small threshold so it settles.
- **Set `CanvasGroup.blocksRaycasts = false` on the outgoing view for the whole fade-out**, then
  `SetActive(false)` at the end. It is still visually present during the fade, and without this a
  fast second tap lands on the screen the user just left.
- **Fade with a `CanvasGroup`, not by tinting graphics.** One alpha on the group is one value to
  animate and it composites the subtree correctly; walking children and multiplying their colours
  fights every `ColorTint` transition underneath (§5 of the SKILL).

## 4 · An element that outlives the screen must replicate the transition

A persistent widget parented outside the view stack (a HUD indicator, a status bar) stays nailed to
the screen while everything else cross-fades, and the transition reads as broken. Run the *same*
motion on the element itself, driven by its own `CanvasGroup`: fade out over the outgoing view's
0.12 s, then fade in over the incoming 0.22 s with the same 24 px directional slide.

Three deliberate exclusions:

- If the element's **placement changes** between the two screens, glide only — never stack a slide
  on top of a move.
- Never blink it while it is an **active input surface** (countdown, playing, paused).
- No scale, bounce or blur; the persistent element must not become the most animated thing on screen.
