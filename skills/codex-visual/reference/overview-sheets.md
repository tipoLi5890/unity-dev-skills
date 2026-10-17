# overview-sheets — the project's pictures on a few themed pages

Before code, a game exists as scattered images: an anchor, three rounds of candidates, a dozen
screen mockups in four folders. A person (and an agent reading the brief) understands the intent
faster from a few pages grouped by question than from a folder listing. `scripts/overview_sheet.py`
builds those pages from one JSON spec, captions every cell and prints the source path under
the caption, so each picture on a page can be traced to its file. Sources are only read; the pages point at them.

## 1. The call

```bash
python3 <skill>/scripts/overview_sheet.py ArtDirection/overview.json --out ArtDirection/overview [--cell 480]
python3 <skill>/scripts/overview_sheet.py --selftest
```

```json
{"font": "fonts/NotoSansTC-Regular.otf",
 "sheets": [
  {"name": "flow_screens", "title": "Flow screens, launch to run summary", "cols": 3, "cell": [480, 270],
   "items": [{"path": "candidates/r3/title.png",     "caption": "Title"},
             {"path": "candidates/r3/runner_pick.png", "caption": "Runner pick"},
             {"path": "candidates/r4/summary.png",   "caption": "Run summary, Mallet ranking"}]}]}
```

- `path` and `font` are relative to the spec's folder; an absolute `path` is refused (exit 3), so
  the outputs do not depend on where the project sits. `cols` defaults to 3 (a sheet with fewer
  items is as wide as its items); `cell` is a side
  or `[w, h]` and defaults to `--cell` (480, square). Use `[w, h]` at the screens' aspect
  (`[480, 270]` for 16:9) so a mockup fills its cell.
- Each sheet → `DIR/<name>.png`: a title band, then per cell the caption (white) and the path as
  the spec wrote it (grey; a long path keeps its file name). An image larger than the cell is
  scaled down, never up. The grid is `contact_sheet.py`'s (`reference/review-sheets.md`).
- **Captions in Chinese or Japanese need `font`:** Pillow's built-in face has Latin glyphs only
  and draws boxes for the rest. Ship the font file with the project; a system font path makes
  the pages differ between machines.
- `DIR/overview.json`: per sheet its `png` and `png_sha256`, and per item `path`, `caption`,
  `status` (`ok` · `missing` · `unreadable`) and, for every file present, `sha256` and `size`.
  Plus `missing`: each item that is not `ok`. The same spec over the same files gives the same
  bytes, so a changed `png_sha256` means a source or the spec changed.
- Exit **0** written; **2** written, but an item is missing (red `missing` cell) or cannot be
  opened, corrupt or over Pillow's pixel limit (red `unreadable` cell), or a usage error; **3** the
  spec or the font cannot be read, or `DIR` cannot be written (the folder is left as it was: an
  earlier run's pages under the same names are put back).

A red cell is a result, not a crash: the page still shows the other cells, and the exit code
tells a script that the set is incomplete. Fix the path or draw the missing screen; never point
the item at a stand-in image to turn the cell green.

## 2. How to group: one question per sheet

| Sheet | Items | What it answers |
|---|---|---|
| `style_and_brand` | the anchor from `anchors/master.png`, family anchors, the app icon, the chosen candidate next to the rejected ones | "What does this game look like, and what did we decide against?" |
| `flow_screens` | every screen from launch to the run summary **in the order a player meets them**: splash, title, Runner pick, lane briefing, run, gate fail, run summary | "Is a screen missing from the path, and does each lead to the next?" |
| `modes` | per mode its setup, its main screen and its end screen; superseded versions captioned as such | "How do the modes differ, and which version is current?" |
| `game_screens` | one mockup per playable screen at the target aspect: Runner in the lanes, the gate closing, the sentry, a pickup row, the HUD | "Does gameplay read at a glance: where the Runner is, what is coming, what scores?" |

- **Caption with what the cell shows and why it is here**, not the file name: "Gate closing,
  HUD at 2 of 3 lives", "Title (picked over r2's dark variant)". The path line already carries the file.
- **Order inside a sheet is meaning:** a flow sheet in player order; a mode sheet setup → play
  → end; a style sheet chosen first, rejected after.
- **3 to 15 cells per sheet.** More → split by question (`flow_screens_menus`,
  `flow_screens_run`), not by count.
- **One picture may appear on two sheets** (the title screen is brand and flow); the sheets
  are views, so nothing is copied.
- Keep the spec in the project (`ArtDirection/overview.json`) and re-run it after every round;
  superseded images stay on the page, captioned "superseded by …", until the user drops them.

## 3. What an overview page is not

- **Not a review sheet.** It is composed without gates and shows candidates on purpose. A
  decision that rests on numbers (a mesh QA, a preset comparison) goes through
  `contact_sheet.py --require` (`reference/review-sheets.md`).
- **Not proof of gameplay.** A polished `game_screens` page shows intent, not timing; motion is
  judged on a preview built from the same images (`unity-game-brief` → `scripts/preview_compose.py`).
- **Not the manifest.** `manifest.md` and an asset ledger stay the registry; `overview.json` records
  which bytes a page showed, so a ledger may link to it.
