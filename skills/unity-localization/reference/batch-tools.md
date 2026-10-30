# The two runnable pieces, and the rule before running them

> Part of the `unity-localization` skill (SKILL.md §5). The batch label wirer and the per-locale font
> swap that ship under `resources/`.

Two runnable pieces go with it:

- `resources/Editor/L10nBatchProcessor.cs` — wires both `Text` and
  `TMP_Text` across every scene under `Assets/` and **returns the labels it could not match**, as
  `scene :: object :: text`; print that list. It matches the mapping **longest key first**, so a
  substring key cannot win inside a longer sentence.
- `resources/LocalizedFontAsset.cs` — the per-locale font swap
  from §1, driven by an Asset Table.

> **Report the scene list, then wait.** The batch processor opens every scene under `Assets/` and
> saves the ones it changed, and nothing undoes that automatically. Say how many scenes and which
> mapping, and get confirmation before running it.
