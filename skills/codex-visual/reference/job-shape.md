# The shape of a job — locks, grid, cell size and style floors

Read after picking the job's shape (static single, static set, animation) in `SKILL.md`. The
canvas is fixed, so the grid decides the cell, and the style decides the smallest cell it survives.

## The four locks — every grid prompt opens with them

After the verbatim `STYLE PREAMBLE`, in English, pasted from their only full copy
(`reference/animation-sheets.md` §1): **1** fixed sheet structure · **2** position and scale
locked · **3** nothing crosses a cell (~3% of the cell width as margin) · **4** one continuous
action. **Static sets use locks 1–3; animation sheets all four.**

## Grid from frame count — the built-in path

The canvas is fixed, so **the grid alone decides the cell**: `cell = sqrt(1,572,864 / (rows *
cols))` for a square sheet; a non-square ask is honoured by *aspect* (`w = round(sqrt(1,572,864 *
cols / rows))`). The square sheet is 1254x1254:

| Grid | 3x3 | 4x4 | 5x5 | 6x6 | 7x7 | 8x8 |
|---|---|---|---|---|---|---|
| Cell (px) | 418 | **313** | 250 | 209 | 179 | 157 |

> **"Bigger grid → ask for more resolution" does NOT work here:** 2048x2048 comes back 1254x1254,
> no error. **Bigger grid = smaller cells.**

So: frame (or member) count → grid → cell → against the style floor → below it, split into sheets
of the same cell size and aspect, each at most the style's maximum grid, every later sheet chained
via `-i` to the FIRST sheet (drift compounds down a chain): `reference/animation-sheets.md` §3d.

## The CLI-fallback path — where the rule does hold

`gpt-image-2` via the bundled `image_gen.py` takes a real `size`, so the canvas scales with the grid,
for an `OPENAI_API_KEY` and a user decision; cell sizes: `reference/image-model.md` §3.

## Style floors — the smallest cell each style survives

- **Pixel style:** working floor **128 px** per cell for a big-head character, so 5x5, 6x6 and
  7x7 work on one built-in sheet; **8x8 (157 px) is the edge.** Confirm it on one test sheet
  first (`reference/animation-scripts.md` §3).
- **Normal style** (flat / cartoon / painterly): **≤ 4x4 per sheet** (313 px), **≤ 3x3** (418 px)
  for a detailed character.
- **Static sets:** 2x2 (627 px) or 3x3 (418 px); 4x4 (313 px) only for small icons that
  ship at ≤ 128 px.
