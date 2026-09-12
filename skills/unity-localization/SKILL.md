---
name: unity-localization
description: >-
  Ship a Unity game in more than one language, with the CJK font pipeline
  where it actually goes wrong. Load for: adding languages, translating UI,
  boxes/tofu instead of Chinese, Japanese or Korean glyphs, TMP fallback chain
  versus per-locale font swap, String/Asset Tables and their Addressables
  rules, font assets that lose their atlas on reimport, a font builder that
  throws with no message, a key missing from one table or a raw key on
  screen, a language switch that appears to do nothing, Traditional Chinese
  in Simplified glyph shapes, font assets modified in git after every test
  run, or layout that breaks on a longer translation. Type sizing and HUD
  layout live in unity-game-ui.
---

# unity-localization — the asset pipeline, and the CJK part that bites

> **Adding a language is easy; adding a script is not.** Latin locales mostly work by
> substitution. The moment a CJK locale ships, font assets, atlas modes, Addressables and
> layout all have to be right *together* — and the failure mode is a screen of empty boxes that
> looks like a rendering bug rather than a missing asset.
>
> The failures that survive review are the quiet ones: text that renders in the **wrong region's
> glyph shapes**, a **raw key** that reads as deliberate English, a button that fits Chinese and
> splits in Japanese. None of them tofu. None of them fail an assertion.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Boxes / tofu instead of Chinese, Japanese or Korean | §2, then `reference/font-pipeline.md` §4 |
| Text renders fine, but one locale shows the wrong regional glyph shapes | §1 |
| Deciding how CJK fonts should be wired at all | §1 |
| Building font assets from a script; a NullReferenceException with no message | `reference/font-pipeline.md` §1 |
| The font worked, then went blank after a reimport | §3 |
| `Failed to load sub-asset` at runtime | §3 Addressables |
| Font assets modified in `git status` after every Editor or test run | §3, then `reference/font-pipeline.md` §5 |
| A raw key on screen; a key that exists in one table only | §5, then `reference/string-tables.md` |
| Whether the Localization package is actually usable in this project | `reference/string-tables.md` §6.1 |
| A `LocalizeStringEvent` is wired and the label never updates while authoring | §5, then `reference/string-tables.md` §6.6 |
| A script wrote table entries and the Localization window still shows the old ones | `reference/string-tables.md` §6.4 |
| A locale switch moves some labels and leaves others behind | `reference/string-tables.md` §6.5 |
| Localising an existing project: which labels and which strings the pass missed | §5, then `reference/string-tables.md` §6.9 |
| Which language a fresh install picks; "follow system" looks broken | `reference/string-tables.md` §3 |
| The language switch appears to do nothing | §4 |
| A translated string overflows or clips its box | §4, then `reference/per-locale-layout.md` |
| How big the text should be, and whether it is readable | skill `unity-game-ui` |

## 1. The two standard answers for CJK contradict each other. Pick deliberately.

| Approach | Argument for | Choose it when |
|---|---|---|
| **TMP fallback chain** (the TMP-optimisation answer) | Bounded, predictable atlas memory; one font asset stack for all languages | Memory is the binding constraint; text is mostly UI chrome; the language set is fixed and small |
| **Per-locale font swap via Asset Table** (the Localization-package answer) | Predictable and debuggable — a missing glyph points at one locale's asset, not into a chain | Languages ship independently; you need per-language typography; a designer must be able to change one language's font without touching the others |

**Write down which one the project uses**, because the debugging paths diverge completely.
Default when nobody has decided: **per-locale swap.** Tofu is then a one-asset question.

> **A per-locale primary and a fallback chain combine fine.** A common belief is that the
> combination gives both failure modes; it is wrong, provided you are explicit about **which layer
> decides the language**: the per-locale primary decides regional glyph shapes, and the chain only
> catches a glyph the primary genuinely lacks. Letting the *chain* answer "which language is this"
> stays incompatible, because it silently succeeds: e.g. all 335 distinct characters of a Traditional
> Chinese UI table can exist in Noto Sans SC, so an SC-primary build with a TC fallback shows **no
> tofu at all** and renders every Traditional string in Simplified shapes.

So: **"no tofu" is not evidence the font wiring is right.** Coverage was never the question.
Character-coverage numbers, the mutual-fallback registration, and the same trap in font metadata
(a CJK font advertising `ja` is not a Japanese font) are in `reference/font-pipeline.md` §3.

## 2. CJK font assets — two flags, and they are not optional

```csharp
fontAsset.atlasPopulationMode        = AtlasPopulationMode.Dynamic;
fontAsset.isMultiAtlasTexturesEnabled = true;
```

Both are properties of `TMPro.TMP_FontAsset`. `AtlasPopulationMode` carries **`Static`** and
**`Dynamic`**, plus **`DynamicOS`** from TMP 3.2.0-pre.3 — so `Dynamic OS` is reachable from script
where your TMP version has it. `GlyphRenderMode` includes `SDF8`, `SDF16` and `SDF32`, which is
where the SDF16 recommendation in `unity-game-ui` → `reference/text-and-cjk.md` lands. A CJK
character set will not fit a static atlas, and a single atlas texture overflows almost immediately.
Both flags, every time.

> **Never substitute a Western font when a CJK font is missing.** Arial and Liberation Sans have
> no CJK glyphs — the result is a screen of tofu boxes that looks like a rendering bug rather than
> a missing asset. If copying a system font fails, **stop and report it.** Silently falling back
> converts a clear one-line failure into a visual mystery. The same applies to a **null** font
> reference in a theme or table: TMP falls back to the built-in Liberation Sans, which is solid
> tofu for CJK.

Before suspecting the atlas, check the two cheapest causes: **the source font file is a Git LFS
pointer** (empty font assets, no error anywhere), and **one label built outside the factory that
assigns the per-locale font** (one tofu box, everything else correct). Full ladder:
`reference/font-pipeline.md` §4.

Named system fonts are a *development* stopgap only: **shipping one is a licensing question, not a
technical one** — macOS PingFang and Hiragino are not redistributable, nor are the Windows faces.
Ship an open-licensed family and put it on the credits screen. Named fonts, file sizes, LFS and
`Dynamic OS` on device: `reference/font-pipeline.md` §6. Sizing numbers (padding ratio, sampling
point size per script), which apply to every font asset here: `unity-game-ui` →
`reference/text-and-cjk.md`.

## 3. Three ways the pipeline loses work silently

> **A generated font asset's atlas and material must be stored as sub-assets or they vanish on
> reimport.**

```csharp
foreach (var tex in fontAsset.atlasTextures)                // the array, not atlasTexture
    AssetDatabase.AddObjectToAsset(tex, fontAsset);
AssetDatabase.AddObjectToAsset(fontAsset.material, fontAsset);
fontAsset.material.mainTexture = fontAsset.atlasTexture;    // wire it explicitly
```

Loop the array: with multi-atlas on (§2), `atlasTexture` is only the first texture, and adding it
alone loses the rest once the set outgrows the first 1024². Mark dirty and save, then confirm with
`AssetDatabase.LoadAllAssetsAtPath` — in-memory references stay non-null whether or not anything
was written. Otherwise the font works today and is blank next week: `reference/font-pipeline.md` §2.

> **Addressables: everything an Asset Table references must be marked Addressable, and must not
> live in `Resources/`.**

A `Resources/` asset raises `OperationException: Failed to load sub-asset` at runtime, not at
build time — copy it into `Assets/Fonts/` first. A font asset deleted and rebuilt gets a new
**GUID**: the Asset Table still points at the old one, so repoint it by hand and re-add it to
Addressables. Any change here needs `AddressableAssetSettings.BuildPlayerContent()` before a build
sees it. The GUID rule also sets the build **order**: whatever writes font references into a theme
or settings asset runs *after* the fonts exist, or it writes nulls.

> **A dynamic atlas rewrites its own `.asset` on every Editor run, and that lands in the
> diffable half of the repo.**

Every `-batchmode -executeMethod` call and PlayMode run that renders a new CJK glyph bakes it into
the atlas, so `git status --short` shows the font asset modified — text YAML, not LFS, growing to
megabytes. Revert the assets as a fixed pre-commit step, or bake a static atlas; `Clear Dynamic Data
On Build` does **not** help, since it acts at build time on what ships and the churn comes from
Editor and test runs. Both options: `reference/font-pipeline.md` §5.

## 4. Layout survives a longer translation, or it does not

German and Finnish run long; CJK runs short but tall. For uGUI text that must absorb both:
`VerticalLayoutGroup` (Child Control Height on, Child Force Expand Height off), one
`ContentSizeFitter` per label (Vertical Fit = Preferred Size), TMP word wrapping on and
Overflow = Overflow. After setting text programmatically,
`LayoutRebuilder.ForceRebuildLayoutImmediate(parent)` — otherwise the box is sized for the
previous string.

Two rules that only appear once a second script ships:

- **Size fixed-width controls from measured text, never from the source language.**
  `label.GetPreferredValues(text).x` gives the width at the component's current font and size
  without a layout rebuild. Where a fixed width is unavoidable, size it against the **longest**
  locale and put the reason in a comment (260 px pills fit Chinese and split on Japanese
  `キャンセル`; 320 px fixed it), and add `NoWrap` + `TextOverflowModes.Ellipsis` so the next
  surprise degrades instead of reflowing the screen.
- **If the per-locale font is bound when a label is constructed, changing locale does nothing
  until the UI is rebuilt.** Expose one public "rebuild and re-enter the current screen" entry
  point rather than a locale-changed event nothing can usefully handle.

Worked numbers, the two-line-row remedy, and the automated per-locale screenshot sweep:
`reference/per-locale-layout.md`.

Use the public `LocalizeStringEvent`, never reflection into the Editor-side TMP convenience
component: it is `internal` and breaks on a package upgrade with no deprecation warning. Wiring
and read-backs: `reference/string-tables.md` §6.6, §6.7.

## 5. Keys, and the register each table is written in

Three failures that no font work prevents:

- **A key present in one table only renders as the raw key** — which reads as intentional English
  debug text, not as a bug. Pin key-set parity with an EditMode test that iterates the **locale
  list** (not a hardcoded pair) and prints the first few missing keys on each side. A `grep -c`
  pre-flight over the table files catches the common case before Unity even starts.
- **zh-Hans and zh-Hant are different vocabularies, not a character conversion.** Never
  machine-convert one into the other: Traditional *wording* written in simplified characters is
  the entry no converter can catch — every character is already correct. Same rule for any
  per-locale text the game sends to a service.
- **A string composed in code is invisible to every component scan.** `label.text = $"EXP {value}"`
  sits on no component at edit time, so it survives the pass that declared localisation finished.
  Grep the C# as a separate sweep: `reference/string-tables.md` §6.9.

The test shape, the JSON table format that survives a later migration to String Tables (including
the `GetLocalizedString` miss contract — a documented **non-null** "No translation found" string),
system-language detection with its three Chinese values, and the wording table:
`reference/string-tables.md`.

**Once `com.unity.localization` is resolved**, the Editor-side half is `reference/string-tables.md`
§6: presence checks, `FindAssets` scoped to `Assets`, populating by `Locale.Identifier.Code`, a
write that survives the session, preview versus runtime locale, `LocalizeStringEvent` and the
listener `AddPersistentListener` leaves asleep at `RuntimeOnly`, and a completeness check whose
third state is `INCONCLUSIVE`.

Two runnable pieces go with it:

- [`resources/L10nBatchProcessor.cs`](resources/L10nBatchProcessor.cs) — wires both `Text` and
  `TMP_Text` across every scene under `Assets/` and **returns the labels it could not match**, as
  `scene :: object :: text`; print that list. It matches the mapping **longest key first**, so a
  substring key cannot win inside a longer sentence.
- [`resources/LocalizedFontAsset.cs`](resources/LocalizedFontAsset.cs) — the per-locale font swap
  from §1, driven by an Asset Table.

> **Report the scene list, then wait.** The batch processor opens every scene under `Assets/` and
> saves the ones it changed, and nothing undoes that automatically. Say how many scenes and which
> mapping, and get confirmation before running it.

Report gaps rather than closing them with the source language; some are decisions —
`reference/string-tables.md` §6.8.

## 6. Acceptance — the tofu check, and what it misses

Not "localisation added". Per release:

1. Switch to **each** locale in turn and look at the screens. **Any tofu box is a failure.**
2. Confirm each CJK locale's table entry points at that locale's own font asset, not at another
   region's — the check that "no tofu" cannot make for you (§1).
3. Confirm `isMultiAtlasTexturesEnabled == true` on those assets.
4. Confirm no screen shows a raw key, and that the key-parity test is green (§5).
5. Confirm no button, chip or list row has wrapped or clipped in the longest locale (§4).
6. Before committing: check `git status --short` for dynamic font assets the run modified (§3).

Automate 1, 4 and 5 as a screenshot sweep — set locale, rebuild, capture, restore — and **read
the images**; capture mechanics are `unity-debug`. Assertions do not see tofu, and they do not see
a two-line button either.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Type size, contrast, HUD placement, per-frame text cost | `unity-game-ui` → `reference/text-and-cjk.md` |
| Canvas layout that must absorb a longer string | `unity-ui-ugui` §3 |
| Whether font assets belong in LFS at all, and how fast they grow | `unity-new-project` → `reference/version-control-setup.md` |
| Driving the Editor to take the per-locale screenshots | `unity-debug` |
| Producing the translations | A translator. Machine output ships as a draft, not as a release |
| Right-to-left scripts | A different layout problem, and not covered here — say so rather than guessing |
