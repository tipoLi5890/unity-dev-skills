# image-model — what renders the pixels, and what you can control

The image model behind the built-in tool can change without the CLI changing, so re-check §1
before trusting a number here.

## 1. Which model rendered this file

Every delivered PNG carries a signed C2PA manifest naming the model. Read it off the file rather
than believing any claim, including this one:

```bash
strings -n 4 out.png | grep -o 'dnameigpt-imagegversionc[0-9.]*'   # -> dnameigpt-imagegversionc2.0
```

The version suffix names the model: `c2.0` is **gpt-image 2.0**. The 2.5 API ids
(`gpt-image-2.5-sunburst`, `gpt-image-2.5-flare`), their extra `xhigh` / `max` quality tiers and
their `background` parameter belong to the keyed API, not to the built-in tool.

## 2. The tool takes a prompt and reference paths — nothing else

The call carries `prompt` and `referenced_image_paths` (plus an option to re-use its own previous
output). No `model`, `size`, `quality`, `background`, output path or format argument: everything you
write about size, quality or transparency is **prose inside the prompt**. And the agent rewrites
that prompt into the bundled imagegen skill's own labelled schema before the call — differently
each run (8 palette hexes in; 6 survived once, 2 the next time). Say anything load-bearing twice, in
words **and** hexes.

## 3. Size: the ratio is yours, the pixel count is not

The tool renders a fixed **~1,572,864-pixel budget** shaped to the aspect ratio asked for:

| Asked in prose | Delivered |
|---|---|
| `1024x1024` | 1254x1254 |
| `1536x1024` | 1536x1024 — exactly the budget |
| `2048x2048` | 1254x1254 — 37.5% of the pixels asked, no error |
| `2400x2880` (a 5x6 sheet) | 1145x1374 |

`sqrt(1,572,864) ≈ 1254`, and `1254 % 16 = 6`, so the API's multiple-of-16 rule does not apply
here.

**Cell arithmetic.** Ask for the *grid's own* aspect and let the budget decide the pixels:
`w = round(sqrt(1,572,864 * cols / rows))`, `h = round(1,572,864 / w)`, cell = `floor(w / cols)`.

| Frames | cols x rows | Sheet | Cell |
|---|---|---|---|
| 4 | 2 x 2 | 1254 x 1254 | 627 |
| 6 | 3 x 2 | 1536 x 1024 | **512** |
| 8 | 4 x 2 | 1774 x 887 | 443 |
| 9 | 3 x 3 | 1254 x 1254 | 418 |
| 12 | 4 x 3 | 1448 x 1086 | 362 |
| 16 | 4 x 4 | 1254 x 1254 | **313** |
| 20 | 5 x 4 | 1402 x 1122 | 280 |
| 25 | 5 x 5 | 1254 x 1254 | 250 |
| 30 | 5 x 6 | 1145 x 1374 | **229** |
| 36 | 6 x 6 | 1254 x 1254 | 209 |

The Cell column is that arithmetic. `sheet_to_frames.py` instead reports the largest cell of the
*true* grid, which is up to 1 px larger wherever the sheet does not divide evenly — a 4x4 on
1254 px reads **314** — so a report saying 314 and this table saying 313 describe the same sheet.

A 512 px frame is therefore an **upscale**, not a generation — only 3x2 lands on 512 naturally. The
agent will also resize its own copy to the size you named; slice the original
(`reference/codex-runtime.md` §4).

### The two paths, grid against cell size

| Path | What decides the cell | 3x3 | 4x4 | 5x5 | 6x6 | 7x7 | 8x8 |
|---|---|---|---|---|---|---|---|
| **Built-in `$imagegen`** | a fixed ~1,572,864 px, 1254² square | 418 | **313** | 250 | 209 | 179 | 157 |
| **CLI fallback** `gpt-image-2` at 2880x2880 | the `size` you ask for | 960 | 720 | 576 | 480 | 411 | 360 |

On the built-in path **bigger grid = smaller cells**; the way to a larger cell is fewer cells per
sheet, several sheets chained to the first, or the CLI path. The CLI row is arithmetic from the
limits in the bundled `image_gen.py` (long edge ≤ 3840, both edges multiples of 16, ratio ≤ 3:1,
655,360–8,294,400 px): 2880x2880 is the largest legal square, and a true 3840 edge needs a wider
ratio (3840x2160 hits the cap exactly). Confirm it with one generation before planning a set. It
costs an `OPENAI_API_KEY` and a user decision, and earns them when a job needs a cell the fixed
budget cannot give — 16+ frames of a detailed character in one sheet, a static set shipping above
313 px — or native transparency.
Record the adoption in `ART_DIRECTION.md`.

## 4. Transparency: chroma key stays the default

Asked for "a real alpha channel… do not paint a checkerboard", the tool returns `mode RGB` — no
alpha channel at all — and paints a grey checkerboard. Generate on a flat key field instead and key
it out — as an **opaque** image: a sheet that comes back RGBA was keyed by the agent, badly; reject
it. A binary key (alpha 0 or 255 by tolerance) is the wrong tool for anti-aliased art even when
the output is a GIF: the rim pixel is half key, stays opaque, and keeps its tint (25–40% of the rim
on 25 sheets). `key_unmix.py` un-mixes the 2 px boundary band and leaves the interior alone; the
recipe and its four traps: `reference/codex-runtime.md` §5. `gpt-image-1.5 --background transparent` through the CLI fallback
is the documented native route; it needs a key — check the alpha channel of its first output before
building on it.

## 5. Quality is not a knob on this path

No `quality` argument, and quality words in the prose do nothing. Spend the budget where it
exists: fewer, larger cells, and re-roll rather than re-word. `quality` exists only on the CLI
fallback (`low | medium | high | auto`, default `medium`).

## 6. Reference images: fixed order, roles named in prose

The tool receives a bare list of paths, so the roles have to be said in words. The order, the
labels and what they hold: `reference/animation-sheets.md` §2.

### Chaining a set to what shipped before (PHASE 3S)

A grid one-shot fixes a set *internally*; a set generated later is a fresh context and drifts from
the first unless the earlier work is chained in as an extra `-i`. Check it with
`slice_grid.py --report`: a grid one-shot should read near-0% size CV; separate generations scatter
far wider. Grid holds a set together, chaining holds sets together over time, and
`normalize_set.py` / `slice_grid.py` nail the exact pixel number afterwards.

- **Promote, then chain.** When a sheet is approved, copy it (or a representative cell) to
  `ArtDirection/anchors/sets/<family>.png` and pass *that* fixed anchor to the next set — never the
  previous raw output. A re-generated single asset needs the family anchor **and** its own previous
  version, or the design drifts even while the style holds.
- **The grid + chain call, end to end** — refs **style first**, the prompt before them, the sheet
  keyed before it is sliced:

  ```bash
  MASTER=<repo>/ArtDirection/anchors/master.png
  FAMILY=<repo>/ArtDirection/anchors/sets/<family>.png    # omit if none yet
  OUT=<scratch>/set; mkdir -p "$OUT"
  codex exec --sandbox workspace-write --skip-git-repo-check \
  '$imagegen <STYLE PREAMBLE, in ENGLISH>. <LOCKS 1-3 filled in for a 2x2 sheet>. Four <items>
   IDENTICAL in size, corner radius, outline weight, highlight and palette; one centered per
   cell (~65% of the cell), even gutters. Only <the symbol> differs — TL:..., TR:..., BL:...,
   BR:....' -i "$MASTER" -i "$FAMILY" < /dev/null
  # capture the original as "$OUT/grid.png" (codex-runtime.md §2), then key it (§5)
  PY=$HOME/.codex/imagegen-venv/bin/python
  "$PY" <skill>/scripts/key_unmix.py "$OUT/grid.png" --out "$OUT/grid_keyed.png" --key-color '#ff00ff'
  "$PY" <skill>/scripts/slice_grid.py "$OUT/grid_keyed.png" --rows 2 --cols 2 --report
  "$PY" <skill>/scripts/slice_grid.py "$OUT/grid_keyed.png" --rows 2 --cols 2 \
    --names a,b,c,d --canvas 512 --content-frac 0.72 --outdir <project asset dir>
  ```

  `--report` runs first: it warns when a cell's subject touches its edge, names the haze-only
  cells as EMPTY, and counts the stray pixels it will clear (`reference/codex-runtime.md` §8).
  After the write, `audit_set.py <outdir>/*.png --expect-frac 0.72 --key-color '#ff00ff'` is the
  gate on what shipped: centre, fill, and what the key left on each rim.
- **Extending a family in place.** An existing member can be made one of the cells — "keep image #2
  as the top-left cell unchanged; fill the rest to match" — and only the NEW cells sliced out. The
  repair limit applies: a cell the prompt says to leave alone does not come back untouched
  (`reference/animation-sheets.md` §8).
- **A template is not a placement guarantee.** A reference image drawn as a 1x1 / 2x2 / 4x4 grid
  with crosshairs or slot outlines, passed via `-i` so the model "draws in the right place", buys
  nothing the slice does not already do — and the model tends to paint the guides into the output.
  What survives an edit is *registration* (centre and baseline within a pixel), never pixels, so
  the only template worth passing is the ghost-cell variant above: the approved member in cell 1
  on the key colour, the other cells empty, and only the new cells sliced out. Exact position and
  size are the slice's job (`slice_grid.py` places the subject's core; `audit_set.py` reads it
  back), not the prompt's.

### The recipe in four steps (PHASE 3S)

1. **Pick the grid**, then **refs, style FIRST:** `-i anchors/master.png` always, plus
   `-i anchors/sets/<family>.png` when this set must match an existing family.
2. **One English prompt:** locks 1–3, pasted from `reference/animation-sheets.md` §1, then the
   per-cell differences named by position — items IDENTICAL in size / corners / outline /
   highlight / palette, one centered per cell (~65% of the cell), even gutters. Prompt first, `-i`
   last, one generation.
3. **Capture the original → chroma-key → `slice_grid.py --report` → slice and normalize** to the
   asset class's project-wide `--canvas` / `--content-frac` — the call above (keying:
   `reference/codex-runtime.md` §5; slice flags: §8).
4. **Gate, promote, register:** `audit_set.py --key-color` on the written files (centre ≤ 2 px,
   fill within 0.02 of `--content-frac`, rim fringe ≤ 0.5% and tint ≤ 2%, exit 1 otherwise); approve the sheet, copy it (or a representative
   cell) to `anchors/sets/<family>.png` so the NEXT set chains to it, and log each asset in
   `manifest.md` ("from sheet <name>").

## 7. Choosing an engine per style — and what this skill implements

`$imagegen` is strong on illustrations, concept and key art, textures, skyboxes and icons, and
**weak at true pixel art**: a full pixel-art brief still returns tens of thousands of distinct
colours per cell and almost no uniform blocks — post-process it (`reference/animation-sheets.md`
§9).

| Choice | What it is | Who does it |
|---|---|---|
| codex `$imagegen` | ChatGPT auth, no API key, fixed pixel budget | this skill, PHASE 3 / 3S / 3A |
| `$imagegen` + **pixelation post-process** | downscale NEAREST + quantise palette + snap to grid, applied to the WHOLE sheet at once | this skill, via `sheet_to_frames.py --pixelate/--palette/--upscale` |
| **external pixel-specialised generator** | PixelLab, Retro Diffusion, Scenario — own API key, not codex | the spec's recipe; this skill follows it |
| **curated CC0 / licensed packs** | Kenney, itch.io, OpenGameArt | a valid non-generative choice |
| **hand-authoring** | Aseprite / LibreSprite | a valid non-generative choice |
| **CLI fallback** `gpt-image-2` / `gpt-image-1.5` | a real `size` and `quality` argument, and the only documented native-transparency route | needs `OPENAI_API_KEY` + a user decision; §3, §5 |

**The candidate-board call** (PHASE 1 step 3) — one composite per style option, each captured out
of `generated_images` under its own name:

```bash
CAND=<repo>/ArtDirection/candidates
codex exec --sandbox workspace-write --skip-git-repo-check \
'$imagegen Produce a 1600x900 style reference board: theme <SCENARIO>. Show the hero, 2-3 key
objects, one obstacle and a slice of environment side by side, with a palette swatch strip along
the bottom. Render it in <STYLE A>. No text except the swatch labels.' < /dev/null
cp "$(ls -t "$HOME/.codex/generated_images"/*/*.png | head -1)" "$CAND/optionA.png"
# repeat per <STYLE> for optionB.png / optionC.png
```

The `1600x900` is an aspect ask, not a size ask (§3). On the pack / external-engine path, present
curated samples instead of generating.

> **Reality check:** never promise clean **true pixel art** from `$imagegen` alone. Recommend the
> post-process, an external pixel engine, or packs — and record the choice in `ART_DIRECTION.md`.
