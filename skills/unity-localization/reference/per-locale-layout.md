# When the translation arrives and the layout does not move

> Part of the `unity-localization` skill. How big text should be at all, and the type scale it
> comes from, are `unity-game-ui`; this file is only about what changes when the *same* screen has
> to hold four languages. Canvas mechanics are `unity-ui-ugui`.

Locale set throughout: zh-Hans / zh-Hant / ja / en.

## 1. Auto-size off means nothing rescues you

Labels built at a fixed design-px size with `enableAutoSizing = false` — the right choice for a HUD
whose type scale was derived from viewing distance — will not shrink to fit anything. Two
consequences:

- CJK is full-width, so its rendered width tracks character *count* closely, and a panel tuned
  against Chinese has no idea how wide the English or Japanese version is.
- The only invariant left is that the tables stay **per-key length-comparable**. Keep a diff over
  all keys reporting where two locales' lengths diverge (e.g. 4 keys of ~250), and treat a new
  divergence as something to look at, not as noise.

## 2. Size the control from measured text, not from the source string

TMP will tell you how wide a string is at the component's current font and size, without a layout
rebuild, so you can set `sizeDelta` in the same frame you set the text:

```csharp
float w = Mathf.Max(MinWidth, Mathf.Ceil(label.GetPreferredValues(text).x) + Padding);
```

A tab-chip strip built this way — e.g. `MinWidth = 160`, `Padding = 56`, gap `16` — accumulates x
as it goes and sizes the focus ring per chip. Fixed-width chips instead wrap "Whack-a-Mole" onto two
lines inside the pill — in English, on a screen that is perfect in Chinese.

Where a fixed width genuinely cannot move, **size it against the longest locale and write down
why**, in the code:

```csharp
const float ButtonW = 320f;   // 260 fits the Chinese labels; Japanese "↓ キャンセル" measures ~290
```

260 px pills overflow in Japanese; widening both buttons to 320 and re-laying the row fixes it. A
set of buttons whose per-label widths diverge across locales (four difficulty buttons, say) can
instead be re-laid as equal-width, equal-height pills — equal widths do not care which language is
longest.

Two more moves worth having in the kit:

- **`NoWrap` + `TextOverflowModes.Ellipsis` on every fixed-width label**, so a translation nobody
  anticipated degrades visibly at one end instead of silently reflowing the screen.
- **Give a row two lines instead of one wide one.** A history row that packs a game name and a
  difficulty onto one line fits in Chinese only; as name-above-difficulty, with the list column
  widened, it stops depending on name length at all.

## 3. Switching locale at runtime does nothing until the UI is rebuilt

If the per-locale font is applied when a label is *constructed* — which is the shape
`reference/font-pipeline.md` §3 argues for — then changing the locale changes neither the strings
already on screen nor their font. A `LocaleChanged` event ends up dead code for exactly this
reason: nothing can usefully subscribe, because the answer is always "tear the screen down and
build it again".

So make that the supported operation: **one public entry point that rebuilds the UI and re-enters
the current screen.** It starts as a private pair of calls duplicated inside the language screen
(`BuildUi(); ReEnter(currentState);`); collapse it into a public method the moment a second caller
appears. The second caller is the test in §4.

## 4. Acceptance is a screenshot per locale, taken by the test

Assertions do not see a button whose label has wrapped onto two lines. The pass that finds layout
bugs like the two above is automated, and it is short:

```
for each locale:
    set locale  →  RebuildUi()  →  walk to the screen  →  capture "<screen>_<locale>.png"
finally: restore the original locale
```

Then **read the images**. Capture and screenshot mechanics are `unity-debug`; what matters here is
that the sweep covers every locale rather than the one the developer reads, and that it restores
the language afterwards so the next test does not inherit it.

Worth capturing per locale, at minimum: any screen with a fixed-width button or chip, any list row
built from content names, and the language screen itself.
