# pixel-grid — snapping generated art to a pixel lattice, one palette, and the gate that reads it back

Pixel style is a post-process on a keyed sheet or a finished image, never a property of the
generation. This file is that post-process: the spec it reads, the two commands (animation sheets,
static sets), the palette a project shares, and `audit_pixel.py`, the gate on the files. The older
point-sampled path is `reference/animation-scripts.md` §3 and stays the default of `--pixelate`.

## 1. What "pixel art" means to the gate

Five properties, all read off the delivered PNGs:

| Property | In numbers |
|---|---|
| One block size | every colour change falls on a multiple of F px; an F x F tile holds one colour |
| Canvas a multiple of the block | width and height divide by F, so no block is cut by the edge |
| One lattice phase across the set | blocks start at 0,0 in every file — a frame shifted 1 px shimmers against its neighbours |
| Binary alpha | every pixel is at alpha 0 or 255; a soft rim is a second, finer resolution |
| A bounded palette shared by the set | at most K opaque colours over **all** the files together, each one on the palette |

A sprite can be centred, in register and cleanly keyed and fail all five. `audit_set.py` and
`audit_frames.py` do not look at any of them.

## 2. The generator draws a fake grid

A full pixel-art brief returns blocks of a few source pixels — about 5–6 px on a 314 px cell — that
are **uneven and anti-aliased**: neighbouring blocks differ by a pixel, their edges are blended, and
the lattice sits at a different phase in every cell of a sheet. Point-sampling that at a fixed step
lands on block edges as often as on block centres, and reads the blend.

Snapping fits a **fixed number of cells** to those edges instead: it cuts each frame (or image) into
N cells along its own colour edges, takes each cell's centre colour — the median of the cell only
when the centre is an isolated speck — makes alpha binary, and applies the palette to that small
image. An integer NEAREST upscale by F then writes each cell as one block.

**N is the caller's, and it is not free.** Choose it near `cell_px / native_block_px`, which both
scripts print: the generator's blocks 5.25 px wide on a 314 px cell are about 60 cells, so 64 is a
sound choice and 32 or 128 is not. A much coarser or finer N aliases against the drawn grid — two
drawn blocks merge into one cell here and split across two there — and no setting repairs it
afterwards. Nothing picks N automatically.

## 3. The Pixel spec in `ART_DIRECTION.md`

Three numbers and a table, recorded once (`reference/art-direction-schema.md`):

| Entry | Example | Becomes |
|---|---|---|
| Cells per frame **N** | 64 | `--pixelate 64` · `pixel_snap.py --cells 64` |
| Block scale **F** | 4 (a 256 px frame) | `--upscale 4` · `audit_pixel.py --block 4` |
| Palette | the fixed `Palette` table, **or** K colours (16) | `--palette-file ART_DIRECTION.md` · `--palette 16` |

N x F is the canvas an un-registered frame or a static asset ships at. The `Palette` section is a
`role | hex | usage` table; every `#RRGGBB` in it is read in order, the first column naming the role:

```markdown
## Palette
| role | hex | usage |
|---|---|---|
| outline | #150521 | every silhouette |
| jacket | #227881 | the courier's jacket, lane markings |
| satchel | #c14016 | satchel, supply crate straps |
| key | #ff00ff | never in art |
```

## 4. Animation sheets

```bash
PY=$HOME/.codex/imagegen-venv/bin/python
S=<repo>/skills/codex-visual/scripts

# 1. measure: the lattice the sheet carries, the palette it would get; nothing written
"$PY" "$S/sheet_to_frames.py" /abs/courier_run_keyed.png --rows 4 --cols 4 --key-color '#ff00ff' \
  --pixelate 64 --pixel-method snap --upscale 4 --palette 16 --register ground --report

# 2. write: snapped, on 16 colours, registered by whole blocks
"$PY" "$S/sheet_to_frames.py" /abs/courier_run_keyed.png --rows 4 --cols 4 --key-color '#ff00ff' \
  --pixelate 64 --pixel-method snap --upscale 4 --palette 16 --palette-out /abs/ArtDirection/courier.hex \
  --register ground --outdir /abs/out/courier_run --names courier_run

# 3. the gates, then the previews
"$PY" "$S/audit_pixel.py" /abs/out/courier_run
"$PY" "$S/audit_frames.py" /abs/out/courier_run --key-color '#ff00ff'
"$PY" "$S/frames_to_anim.py" --frames-json /abs/out/courier_run/frames.json --bg '#808080' \
  --out /abs/review/courier_run.gif --onion /abs/review/courier_run_onion.png
```

`--pixel-method snap` needs `--pixelate N`, numpy and `pixel_ops.py` beside the script, and is
refused (exit 1) with `--dither floydsteinberg`, with more cells than the frame has pixels, and with
a `--canvas` that is not a multiple of F. Under it every cut, pad, canvas and paste offset is a
multiple of F, so registration moves frames by whole blocks: the fitted canvas carries one spare
block, `--align centroid` can leave up to F/2 px, and the feet line still reads 0. The order is key
→ snap each cell → palette on the small sheet → upscale → cut and register.

What the run prints, on the worked example:

```
snapped cell 314x314 -> 64x64 sheet 1254x1254 -> 256x256 (an exact 4x4 grid)
pixel metric lattice warped 16 fitted 0 uniform 0
pixel metric edge_fit 0.089
pixel metric unit_gaps 0.480
pixel metric native_block_px 5.25 5.50
pixel metric native_cells 60x57
pixel metric palette_source built
pixel metric colours_in 12878
pixel metric colours_used 16
pixel metric colour_move_max 19.97
```

| Line | Reading |
|---|---|
| `lattice` | cells by how they were cut: `warped` = cuts moved onto the edge beside them, `fitted` = one phase for the cell, `uniform` = the equal split (also every empty cell). The label says what was done, not how good the source was |
| `edge_fit` | 0–1: how much of the edge weight sits on evenly spaced cuts at N, less what chance would catch. Always the **unwarped** fit, median over cells with content |
| `unit_gaps` | 0–1: how many neighbouring edges are one cell apart. High `edge_fit` with low `unit_gaps` is an N that divides the drawn count |
| `native_block_px` | the commonest gap between neighbouring edges, x then y — the generator's own block |
| `native_cells` | the cell over that block: the N the sheet was drawn near. **Compare it with N**; near is fine, half or double is the aliasing of §2 |
| `colours_in` / `colours_used` | distinct colours before the palette, and palette entries the sheet touched |
| `colour_move_max` / `_mean` | how far the palette moved a colour (ΔE2000 under `--colour-metric lab`); a large maximum on a small K is a colour the palette has no place for |

Generator sheets read a low `edge_fit` and a middling `unit_gaps` — uneven blocks do not sit on any
evenly spaced lattice, which is why the cuts are warped onto them. None of these lines is gated; the
gate is on the output (§7).

**`--snap-warp off`** when the source's blocks really are evenly spaced — art that was upscaled by
NEAREST, a hand-authored sheet, a previous pixel pass: one phase per cell then reads it exactly and
a warped cut can only move off it. `fitted` then dominates with both numbers high. A cell whose
evidence — the smaller of the two numbers — is under 0.30 falls back to `uniform`, the equal split:
on a generator sheet that is every cell, and warp off is then plain cell-centre sampling.

`frames.json` gains a `pixel` block whenever `--pixelate` is used: `method`, `cells`, `block_px`,
`alpha` (`binary`, or `soft` for a nearest run without `--palette`), `lattice`, `edge_fit`,
`unit_gaps`, `native_block_px` and `palette {source, path, colours}`. `audit_pixel.py` takes its
expectations from it.

## 5. Static sets and singles

A static asset is rescaled by a fraction when it is normalised, so the lattice is made **last**, on
the canvas the asset already sits on:

```bash
# 1. slice and normalise to the final canvas (N x F = 64 x 4 = 256), as for any set
"$PY" "$S/slice_grid.py" /abs/pickups_keyed.png --rows 2 --cols 2 --names satchel,crate,token,badge \
  --canvas 256 --content-frac 0.78 --outdir /abs/out/pickups

# 2. measure: the block the images carry now, and the count it implies
"$PY" "$S/pixel_snap.py" /abs/out/pickups/*.png --cells 64 --report

# 3. snap the set onto one lattice and one palette
"$PY" "$S/pixel_snap.py" /abs/out/pickups/*.png --cells 64 --upscale 4 \
  --palette-file /abs/ArtDirection/courier.hex --outdir /abs/Assets/Art/Pickups --suffix ''

# 4. the two gates
"$PY" "$S/audit_set.py" /abs/Assets/Art/Pickups/*.png --expect-frac 0.78 --off-max 2 --fill-tol 0.02
"$PY" "$S/audit_pixel.py" /abs/Assets/Art/Pickups/*.png --block 4 --palette-file /abs/ArtDirection/courier.hex
```

`normalize_set.py` takes the place of step 1 for loose files. `--cells N` is the count along the
long side (the short side gets `round(N * short / long)`; `--cells-wh NX NY` sets both), and the
output canvas is cells x `--upscale` whatever the input measured. Output goes beside each input with
`--suffix _px` unless `--outdir`, another `--suffix` or `--in-place` says otherwise.

- **Normalising changes the native block.** The scale that brings a subject to its content fraction
  scales its blocks too, so `native_block_px` and `implied_cells` are read on the normalised image
  (step 2), not on the sheet. If `implied_cells` is far from N, change the canvas or the content
  fraction until the drawn block lands near F — not N alone.
- **`--sweep LO HI`** prints `edge_fit` / `unit_gaps` for every cell count whose spacing is LO..HI
  source px and names the best. It is sharp on an evenly spaced source and flat on generator
  output, where `native_block_px` is the better guide.
- **The half-block budget.** Snapping rounds the subject's edges to the lattice, so a core centre
  can sit up to half a block off the canvas centre and a core side can change by a block. Gate with
  `audit_set.py --off-max` of at least F/2 and `--fill-tol` of at least F / canvas: the defaults
  (2 px, 0.02) cover F ≤ 4 on a 256 px canvas; F 8 needs `--off-max 4 --fill-tol 0.04`.
- **Never normalise after snapping.** `slice_grid.py` and `normalize_set.py` rescale by a fraction
  and undo the lattice. Their `--resample nearest` keeps hard edges for art that is already pixel
  art and warns when the scale is not an integer; it does not make a lattice.
- An opaque or fully transparent input is refused (exit 1); a read-back that fails after writing
  exits 3 (`--no-gate`: 0).

## 6. One palette across sheets

Quantising sheet by sheet gives every sheet its own 16 colours, and the courier's jacket changes
shade between the idle and the run. Two ways to hold one palette:

- **Authored** — the `Palette` table of `ART_DIRECTION.md` (§3) is the palette:
  `--palette-file /abs/ART_DIRECTION.md` on every `sheet_to_frames.py` and `pixel_snap.py` call.
  `--palette-section NAME` reads another heading; a `.hex` / `.txt` (one colour per line) or a
  palette `.png` works the same way.
- **Derived** — the first sheet builds it and writes it down; every later sheet reads it:

```bash
# the first sheet of the courier decides the 16 colours
"$PY" "$S/sheet_to_frames.py" /abs/courier_idle_keyed.png --rows 3 --cols 3 --key-color '#ff00ff' \
  --pixelate 64 --pixel-method snap --upscale 4 --palette 16 --palette-out /abs/ArtDirection/courier.hex \
  --register ground --outdir /abs/out/courier_idle --names courier_idle
# every later sheet, and the static sets, are held to them
"$PY" "$S/sheet_to_frames.py" /abs/courier_run_keyed.png --rows 4 --cols 4 --key-color '#ff00ff' \
  --pixelate 64 --pixel-method snap --upscale 4 --palette-file /abs/ArtDirection/courier.hex \
  --register ground --outdir /abs/out/courier_run --names courier_run
```

Promote the derived `.hex` beside the anchors and record it in the spec; a first sheet that never
shows the supply crate's red has no red to give the sheet that does, so derive from the sheet with
the widest range, or author the table.

**The key colour is left out automatically**: a palette file that lists `#ff00ff` loses it when
`--key-color` (or `--bg-color`) names it, and the run prints `key_excluded`. `--palette K` together
with `--palette-file` keeps the K file colours the sheet or set uses most. `--palette-out` writes
the palette the art was held to, not only the entries it touched. A built palette holds colours
taken from the art itself, in the builder's order — not sorted by role.

## 7. The gate — `audit_pixel.py`

```bash
"$PY" "$S/audit_pixel.py" /abs/out/courier_run                      # a snap sidecar says what was promised
"$PY" "$S/audit_pixel.py" /abs/out/courier_idle /abs/out/courier_run \
  --palette-file /abs/ArtDirection/courier.hex --csv /abs/review/pixel.csv   # two sheets, ONE palette
"$PY" "$S/audit_pixel.py" /abs/Assets/Art/Pickups/*.png --block 4 --max-colours 16   # no sidecar: say what to expect
```

Full flag set: `targets… [--block F] [--max-colours K] [--palette-file PATH]
[--palette-section Palette] [--palette-tol 0] [--uniform-min 100] [--alpha binary|soft] [--csv PATH]
[--no-gate]`. A target is a directory holding `frames.json`, a `frames.json` path, a directory of
PNGs, or PNG files (all of them together one set). Expectations come from the sidecar's `pixel`
block — `block_px`, `alpha`, the palette's colours and their count — and a flag overrules it for
every set given. Exit 0 every set passes · 1 a gate failed, bad arguments or an unreadable file ·
**2 nothing to read, or a set with nothing to check against** (no `pixel` block and none of
`--block` / `--max-colours` / `--palette-file`) — `--no-gate` turns 1 into 0, never 2.

One line per file, then per set:

| Metric | Reads | Gate |
|---|---|---|
| `block_px` | the GCD of the spacings between columns (rows) where anything changes | a multiple of F in every file, and F over the set — a frame whose edges all fall on even cells reads 2F and is still on the lattice |
| `canvas_multiple` | width and height against F | both divide by F |
| `lattice_phase` | where the blocks start, modulo F | 0,0 in every file |
| `block_uniform_pct` | share of non-empty F x F tiles, laid from the file's own phase, that are one colour | ≥ `--uniform-min` (100) |
| `alpha_partial_px` | pixels with 0 < alpha < 255 | 0, unless `--alpha soft` |
| `opaque_colours` | distinct colours at alpha 255, per file and as the set's union | ≤ K, the union too |
| `off_palette_px` | opaque pixels further than `--palette-tol` per channel from every palette entry | 0 |
| `single_block_pct` | opaque blocks with no 4-neighbour of their own colour — specks, or dithering | printed, never gated |

`canvas_multiple` and `lattice_phase` are gated only for art written on a block lattice: the sidecar
says `method` `snap`, or `--block` was passed. Frames from the point-sampled path keep F px blocks
at their own offset, so both are printed and neither is gated. A blank or one-colour frame has no
lattice to read: it prints `-` and fits any. A sidecar's own palette is the one *that sheet* was
held to, so two sheets with two built palettes each pass alone — pass `--palette-file` to hold
several sets to one. There is no `--key-color` here: give it the `.hex` that `--palette-out` wrote,
or a table without the key.

| Symptom | Cause | Fix |
|---|---|---|
| `block_px` reads 1 (or 1x4), `block_uniform_pct` far under 100 | something resized, rotated or re-normalised the art after the pixel step | make the pixel step the last one; resize afterwards by an integer NEAREST factor only |
| `block_px` reads 8 on every file where 4 was expected | upscaled by another factor, or N was halved | re-run with the spec's N and F |
| `lattice_phase` not 0,0, or `canvas_multiple no` | padded, cropped or shifted by a distance that is not a multiple of F; a `--canvas` that does not divide by F | re-slice with `--pixel-method snap` (it refuses such a canvas) or move the art by whole blocks |
| `alpha_partial_px` > 0 | a soft key, a defringe or a resize after the pixel step | re-run the pixel step; `--alpha soft` only if the style keeps a soft rim |
| each file within K, the set's `opaque_colours` over K | the files were quantised one by one | one palette for all: `--palette-out` on the first, `--palette-file` on the rest (§6) |
| `off_palette_px` > 0 | a tint, a resize or a per-sheet `--palette` after the palette was applied; the wrong palette file | re-run the pixel step with `--palette-file`; `--palette-tol` only for a known re-encode |
| `single_block_pct` high and the art looks noisy | N finer than the drawn grid, so one drawn block's blended edge became its own cell; or K too large | lower N toward `native_cells`; lower K |
| every gate passes and the art still reads soft in the engine | the import filters it | Point filtering, no compression, and a PPU of `reference_core_height_px / world height` chosen so `PPU / pixel.block_px` (F) is whole (`unity-2d-sprites`) |
| exit 2 on a set that has files | no sidecar `pixel` block and no expectation flag | pass `--block F` and `--max-colours K` or `--palette-file` |

## 8. One size per pixel character

`--subject-px` and `--scale-search` resample, and are refused with `--pixelate`: a pixel character
cannot be brought to size after the fact. Its size is decided by **the same N and the same F for
every sheet of the character**, with the same neutral stand as the reference frame and the same
share of the cell filled (lock 2). `frames.json` records `register.reference_core_height_px` — with
N 64 and F 4 a courier 51 cells tall reads 204 in the idle and in the run. A sheet that reads a block
or more off was drawn at another size: re-generate it chained to the first sheet; do not rescale it.
One PPU then draws every sheet at one size, and every block is the same size on screen. The core
height is in px of the written files, so F is already inside it: PPU = `reference_core_height_px`
/ the courier's height in world units, with that height chosen so PPU / F is a whole number — the
art-pixel PPU the tiles and the Pixel Perfect Camera use.

## 9. What this does not do

- **No dithering under snap** — `--dither floydsteinberg` is refused; each cell takes its nearest
  palette colour.
- **No outline redraw.** A line thinner than a cell — a 1 px outline at a coarse N — can still
  break or double; choose N so the outline is at least a cell wide, or repair by hand.
- **No tileable-edge check.** A tileset's seams are not measured.
- **No automatic choice of N**, and no rescue for an N far from the drawn grid (§2).
- **No judgement of the drawing.** A dead or drifting sheet snaps into a dead or drifting pixel
  sheet; the animation gates are still `reference/animation-faults.md`.
