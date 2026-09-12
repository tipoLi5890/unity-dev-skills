# Text that survives distance, mixed scripts, and a frame budget

> Part of the `unity-game-ui` skill. Sizing and layout live in `reference/type-scale.md`; this
> file is about the font assets underneath, and what they cost. For **multi-language asset
> pipelines** (Asset Tables, Addressables, per-locale fonts) go to `unity-localization`.

## Symptom → which section

| Symptom | Section |
|---|---|
| Memory Profiler shows a large atlas, or several of them | [Mixed Latin + CJK](#mixed-latin--cjk), then [Measuring it honestly](#measuring-it-honestly) |
| Glyph weight changes mid-line, or edges look fuzzy | [The numbers](#the-numbers) — padding : sampling, `Scale`, `SDF16` |
| CPU spikes whenever the text changes | [What text costs every frame](#what-text-costs-every-frame) — AutoSize, per-Canvas rebuilds |
| The build grew and the fonts are the reason | [Mixed Latin + CJK](#mixed-latin--cjk) — `Clear Dynamic Data On Build`, `Dynamic OS` |
| Latin and CJK on one line sit at different heights | [Mixed Latin + CJK](#mixed-latin--cjk) — the baseline procedure |
| Italic, outline or glow variants of one font are wanted | [What text costs every frame](#what-text-costs-every-frame) — Material Presets, not duplicated assets |

Pick the row before reading further; the file is four sections and only one of them is your bug.

## The numbers

Authoring a TMP font asset has a handful of values that are not obvious and are expensive to
get wrong, because they are baked at import:

| Setting | Value | Why |
|---|---|---|
| Padding : Sampling Point Size | **10%** (e.g. padding 9 / sampling 90) | Below this the SDF clips on outlines and glow; above it wastes atlas |
| Sampling Point Size — Latin | **70–90** | |
| Sampling Point Size — CJK | **36–50** | CJK glyphs are dense; a smaller sampling still yields a clean SDF and costs far less atlas |
| Dynamic atlas | **512 or 1024** | This is the cap on peak font memory. Pick it deliberately |
| Font asset `Scale` | **exactly 1** | |
| Atlas Render Mode | `SDF16` when a static font ≥ 72 pt looks soft | Higher precision, slightly more atlas |

> **Every fallback must use the same padding : sampling ratio as the primary font.** A mismatch
> renders the same line at visibly different stroke weights — it reads as "two fonts in one
> sentence" and it is nearly impossible to find by looking at the layout code.

> **A font asset whose `Scale` is not 1 breaks the point-size → pixel arithmetic.** Some imported
> fonts arrive at 0.9. Every size derived from a viewing-distance calculation will then be wrong
> by 10%, consistently, everywhere — which reads as "the design just looks off" rather than as a
> bug. Check it before trusting `type-scale.md`.

## Mixed Latin + CJK

The structure that keeps atlas memory bounded:

```
primary: static font asset, full Latin set baked
  └ fallback 1: dynamic (atlas 512–1024) → CJK
  └ fallback 2: dynamic → symbols / emoji
```

- **Turn on `Clear Dynamic Data On Build`.** Without it, every glyph that happened to get baked
  into the atlas while you were testing in the editor ships inside the player build. It is
  invisible in the editor and it is why a build is mysteriously larger than the last one.
- **Do not build one giant dynamic font covering every language.** The atlas grows without bound
  and the cap you chose above stops meaning anything.
- **`Dynamic OS` population mode** (TMP 3.2.0-pre.3+) leaves the source font out of the build
  entirely and resolves against the device's system fonts at runtime. Android → `NotoSans`;
  iOS → `PingFang`. On iOS the CJK families differ per language, so a single TMP setting covering
  zh/ja/ko needs its fallback chain checked on device, not in the editor.

**Baselines that do not line up** between Latin and CJK on one line: import
`Window > TextMeshPro > Settings > Import TMP Example & Extras` (once per project), add
`TMP_TextInfoDebugTool` to the offending object, enable **ShowLines** to draw ascender /
descender / baseline, then adjust ascender/descender **on the font asset** until they meet.
(That import occasionally sends a project into an import loop; restart the editor and it
usually completes the second time.)

## What text costs every frame

- **`AutoSize` recomputes on every string change.** On a timer, a score, a chat line or a live
  player name that is a permanent CPU cost for a value that never needed to resize. Lock the
  layout, then set an explicit point size and turn AutoSize off. Keep it only for genuinely
  static labels that must absorb a longer translation.
- **Canvas rebuilds are per-Canvas.** A score that changes every frame sitting on the same Canvas
  as the rest of the HUD rebuilds the whole HUD every frame. Put volatile fields on their own
  child Canvas.
- **Worldspace text uses `TextMeshPro`, not `TextMeshProUGUI`.** A worldspace Canvas is a known
  slow path.
- **Style variants come from Material Presets, not duplicated font assets.** Right-click the
  material header → Create Material Preset. Presets share one atlas texture and only override
  shader parameters; a duplicated font asset duplicates the atlas.
- **A TMP Sprite Asset's source texture must be Texture Type `Default`, not `Sprite`.** `Sprite`
  generates child sub-objects TMP never reads, and they slow mobile load.

## Measuring it honestly

`.ttf` / `.ttc` importers default to **Include Font Data = on**, so a Memory Profiler capture
taken in the editor counts the source font file — which the build may not even contain if you
are on `Dynamic OS`. Turn it off before capturing, or the number you are optimising against is
not the number on the device.
