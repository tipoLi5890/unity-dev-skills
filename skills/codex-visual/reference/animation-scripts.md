# animation-scripts — the previews, the script usage, the pixel post-process, the outputs

What is run on a delivered animation sheet, and what comes out of it for the engine. The prompt
that made the sheet is `reference/animation-sheets.md`; reading a fault off the report, and what
passes, is `reference/animation-faults.md`.

## 1. Preview formats

| | Alpha | fps | Use |
|---|---|---|---|
| GIF | 1 bit | delays are centiseconds: 10 fps (100 ms) and 20 fps (50 ms) survive; 24 fps is stored as 40 ms, so a 16-frame set runs 640 ms instead of 667 ms | Pasting into a review; the one format everything renders |
| APNG | 8 bit | exact | The real review copy, and anything not at 10/20 fps |
| WebP | 8 bit | exact | Chat windows — `--webp-quality 80` when lossless is too big |

All three keep the source PNGs' bounding boxes frame for frame — GIF disposal is right and nothing
ghosts. `--ffmpeg <path>` routes the GIF through palettegen/paletteuse for a better, smaller file.

> **A contact sheet that tiles one frame per cell is not evidence about an animation.** It proves
> each frame was drawn; what goes wrong goes wrong *between* frames, so a character that jumps
> 65 px on every frame change photographs perfectly in it. Review an animation with three things:
> the **onion skin** (`frames_to_anim.py --onion`, or one sheet of them from
> `audit_frames.py --onion`: one silhouette = in register, doubled bodies = it jumps), the **loop at
> its real fps on a mid-tone ground** (`--bg '#808080'`, or the game's own ground colour — a fringe
> is invisible over a checkerboard), and the **numbers** (`audit_frames.py`: feet, slip, fringe,
> tint, cut). Then once more in the engine, from the shipped bytes (§4).

Sequence order is frames → `--reverse-loop` (ping-pong, endpoints not repeated) → `--hold-last N`. A
loop gets `--reverse-loop` only if it was authored as a half cycle; a loop that already returns to
frame 1 gets neither flag. A one-shot gets `--hold-last`.

> **An APNG is a `.png`, so a preview left in the frame directory is the next glob's extra frame.**
> A bare `--apng` writes `<stem>_apng.png`, animated inputs are skipped with a printed line, and an
> unrequested merge prints a WARN — but a one-frame preview still slips through. Prefer
> `--frames-json`, and write previews outside the frame directory.

## 2. Script usage

```bash
PY=$HOME/.codex/imagegen-venv/bin/python
S=<repo>/skills/codex-visual/scripts
```

### key_unmix.py — before anything is cut

```bash
# a character sheet: un-mix the 2 px boundary band along key -> outline
"$PY" "$S/key_unmix.py" /abs/sheet.png --out /abs/sheet_keyed.png --key-color '#ff00ff'
# an effect sheet (no outline): project the rim onto the fill beside it
"$PY" "$S/key_unmix.py" /abs/fx.png --out /abs/fx_keyed.png --edge fill
# an outline that is not near-black: derive the ramp from its colour
"$PY" "$S/key_unmix.py" /abs/ui.png --out /abs/ui_keyed.png --outline-color '#081930'
# a field painted off the named key (video frames): two erase balls + un-mix by tint, hex named
"$PY" "$S/key_unmix.py" /abs/raw/runner_run_012.png --out /abs/keyed/runner_run_012.png \
  --key-color '#00ff00' --edge tint
# before the first sheet: which key the base still can be keyed on (codex-runtime.md §5)
"$PY" "$S/pick_key.py" /abs/ArtDirection/anchors/sets/runner_base.png
# sprites already keyed and shipped: measure, then repair in place
"$PY" "$S/key_unmix.py" --defringe /abs/Assets/Art/UI --dry-run
"$PY" "$S/key_unmix.py" --defringe /abs/Assets/Art/UI --in-place
```

Full flag set: `inputs… [--out PATH | --outdir DIR] [--key-color '#ff00ff'|auto]
[--edge outline|fill|tint] [--lo 60|96] [--hi 330 | --outline-color HEX] [--band 2|4]
[--despill | --no-despill] [--choke 0.35] [--fringe-max 0.5] [--tint-max 2] [--defringe [--in-place]]
[--dry-run] | --selftest`; `--lo` / `--band` default to 60 / 2 and to 96 / 4 under `--edge tint`,
`--despill` (on) and no choke belong to tint mode only. It prints
`fringe_pct` and `tint_pct` for a binary key and for its own result, and exits 1 when either is
still over its limit, 2 when under 1% of the sheet was keyed (the field is not that colour).
**A sheet that arrives RGBA was keyed by the agent** — such a key has no opaque rim left to un-mix:
it is refused; reject the sheet and ask for an opaque image on the flat key colour.
`--edge fill` is for effects only: on art that itself carries the key's hue (a purple emblem on
magenta) it reads 4–6% fringe and fails its own gate. The two definitions, and why there are two:
`scripts/sprite_ops.py`. What `--edge tint` cuts and un-mixes, and why it wants the hex named
rather than `auto`: `reference/codex-runtime.md` §5. `pick_key.py IMAGE [--min-distance 96]`
prints one JSON object and exits 1 when no key clears the radius.

### sheet_to_frames.py

```bash
# 1. the acceptance gate: measure the keyed sheet, write nothing
"$PY" "$S/sheet_to_frames.py" /abs/sheet_keyed.png --rows 4 --cols 4 --key-color '#ff00ff' --report

# 2. an action that stays on the floor: every frame seated on frame 0 by its core silhouette,
#    feet on one line, the canvas fitted, the character 470 px tall in every sheet of it
"$PY" "$S/sheet_to_frames.py" /abs/sheet_keyed.png --rows 3 --cols 3 --key-color '#ff00ff' \
  --register ground --subject-px 470 --outdir /abs/out/swing --names swing --fps-hint 18

# 3. a jump or a flyer: seated in x and y, feet free to leave the line
"$PY" "$S/sheet_to_frames.py" /abs/jump_keyed.png --rows 3 --cols 3 --key-color '#ff00ff' \
  --register free --subject-px 470 --outdir /abs/out/jump --names jump

# 4. an effect: centred by its alpha centroid, one scale for the set, nothing dropped
"$PY" "$S/sheet_to_frames.py" /abs/fx_keyed.png --rows 3 --cols 3 --key-color '#ff00ff' \
  --register centroid --outdir /abs/out/spark --names spark

# 5. motion AUTHORED inside the cell: keep the in-cell position (and, optionally, pin the set to
#    its median ground line by whole-set translation)
"$PY" "$S/sheet_to_frames.py" /abs/sheet_keyed.png --rows 4 --cols 4 --register keep --outdir /abs/out/hop
"$PY" "$S/sheet_to_frames.py" /abs/sheet_keyed.png --rows 4 --cols 4 \
  --align baseline --max-shift 24 --outdir /abs/out/hop

# 6. pixel-art post-process: one shared palette for the whole sheet, 64 px cells back up at 4x
"$PY" "$S/sheet_to_frames.py" /abs/sheet_keyed.png --rows 5 --cols 6 \
  --palette 24 --pixelate 64 --upscale 4 --register ground --outdir /abs/out/morph --names morph
#    the same, snapped: each cell cut along its own block edges, the palette applied to the small
#    sheet and written down for the next sheet (`reference/pixel-grid.md`)
"$PY" "$S/sheet_to_frames.py" /abs/courier_run_keyed.png --rows 4 --cols 4 --key-color '#ff00ff' \
  --pixelate 64 --pixel-method snap --upscale 4 --palette 16 --palette-out /abs/ArtDirection/courier.hex \
  --register ground --outdir /abs/out/courier_run --names courier_run

# 7. the strict duplicate test, and no sub-threshold tail left behind for a trimmer
"$PY" "$S/sheet_to_frames.py" /abs/sheet_keyed.png --rows 5 --cols 6 \
  --dup-metric pixel --dup-threshold 22 --clear-below-thr --report

# 8. a fixed frame: one scale for the set so the farthest-reaching pose fits a 256x256 canvas,
#    resampled with alpha and colour apart so a keyed rim stays clean
"$PY" "$S/sheet_to_frames.py" /abs/swing_keyed.png --rows 3 --cols 3 --key-color '#ff00ff' \
  --register ground --canvas 256 256 --scale reach --resample split --outdir /abs/out/swing --names swing
#    authored motion (keep) seated by the feet, not by a cape or a trailing arm
"$PY" "$S/sheet_to_frames.py" /abs/sheet_keyed.png --rows 4 --cols 4 \
  --align foot --max-shift 24 --outdir /abs/out/hop
```

Full flag set: `sheet --rows --cols [--register ground|free|centroid|keep] [--ref 0]
[--subject-px PX] [--scale-search LO HI] [--foot-margin PX] [--gutters search|nominal]
[--key-color HEX] [--bg-color HEX] [--bg-tol 40] [--force-key] [--alpha-thr 16]
[--clear-below-thr] [--drop-strays] [--inset-frac 0] [--names frame]
[--align none|baseline|centroid|both|foot] [--scale none|reach] [--resample lanczos|split]
[--max-shift PX] [--outdir DIR] [--canvas W H]
[--pivot bottom-center|center] [--fps-hint 10] [--pixelate N] [--pixel-method nearest|snap]
[--snap-warp on|off] [--palette K] [--palette-file PATH] [--palette-section Palette]
[--palette-out PATH] [--colour-metric lab|rgb] [--dither none|floydsteinberg] [--upscale F]
[--dup-metric signature|pixel] [--dup-threshold 2.0] [--feet-max 3] [--fringe-max 0.5] [--tint-max 2] [--no-gate]
[--json PATH] [--report] | --selftest`.
Exit codes: 0 ok · 1 the cells cannot be formed / bad args (a fit option outside its mode,
`--scale reach` without `--canvas`) / missing `--outdir` / **writing without
`--register`** / `--bg-color` on an input that already carries alpha · 2 `--align` needed a shift
larger than `--max-shift`, and nothing was written · **3 a gate failed** — the frames *are* written
and `frames.json` carries the faults under `verdict`; `--no-gate` exits 0 instead.

**`--register` is the decision, and there is no default.** Pick it from the action, not from the
sheet:

| The action | `--register` | What it does |
|---|---|---|
| stays on the floor — idle, attack, swing, cast, a walk or run in place | `ground` | seats every frame on the reference (`--ref`, frame 0) by its **core silhouette** — the solid shape opened by 4 px, so a bat or a waving arm does not steer it: feet (the core's lowest row) on one line, x by maximum overlap |
| leaves the floor — a jump, a hop, a flyer | `free` | the same, searching x and y. The body holds still and the legs tuck; the body's own rise is not in the frames — put it on the transform |
| is an effect — a burst, dust, a spark | `centroid` | alpha centroid on the canvas centre; never rescaled frame to frame (an effect is meant to grow); nothing dropped |
| travels inside its cell **by design** (hand-authored, or a sheet you composed) | `keep` | the in-cell position survives; `--align` is its whole-set translation |

On a generated sheet `keep` keeps the model's grid, not the action, and the run says so: `metric
incell_x_grid_r2` is the share of the sideways spread the grid column explains (0.64–1.00 on 20 of
21 sheets; travel authored across a cell reads 0.10), `seat metric slip_max_px` is how far a
written frame sits from register, and the two together are `GATE grid_wander`. The reverse case is
printed too: when `ground` / `free` remove offsets that do **not** follow the grid, a `WARN` says
they may have been authored travel.

`--subject-px N` resamples the **whole set** by one factor so the reference's core is N px tall —
one number per character, in every sheet of it, so the engine draws its idle and its swing at one
size from one PPU. The reference must therefore be the same neutral stand in every sheet (lock 4
already asks a one-shot to start there). Without `--canvas` the canvas is **fitted** to the
registered frames and nothing can be clipped; the sidecar records `canvas` and **`pivot_norm`** —
the reference's feet line as a fraction of the canvas, which is *not* the canvas floor (a foot
margin is kept under it) and is what the importer's pivot must be (§4).

**`--bg-color` on an already-keyed RGBA sheet is refused** (exit 1; `--force-key` overrides): it
would re-key a finished matte and report a sheet that reads flawless and broken at once
(`transparent_pct 0.0`, bleed on 16 of 16 cells). On an opaque sheet `--bg-color` still makes its
binary key, and the result then fails `GATE key_fringe` on any anti-aliased art — key with
`key_unmix.py` and pass the RGBA with `--key-color`.

**Three fit options, all off by default**, for a set that has to fit a frame the game fixes:

| Option | Mode | What it does |
|---|---|---|
| `--scale reach` | `ground` / `free` / `centroid`, with `--canvas` | one factor for the whole set, at most 1: the largest at which every placed frame's reach from the anchor (the reference core's centre x; the feet line, or the centre under `centroid`) fits the canvas, 4 px clear on each side and under the top, `--foot-margin` under the feet. A pose that reaches far out shrinks the **set**, so no pose draws smaller than its neighbour. It multiplies the `--subject-px` scale |
| `--align foot` | `keep` family (any `--align`) | each frame's x is its foot centroid — the alpha-weighted x of the bottom 20% of its content rows — moved onto the set's median; its bbox bottom onto the whole-pixel median bottom. `--max-shift` applies; prints `align foot target_bottom … target_foot_x …` and `align residual foot_x_drift_max_px` |
| `--resample split` | `ground` / `free` / `centroid` | wherever a frame is scaled, alpha by LANCZOS held to the source's alpha range under each output pixel, colour by a non-negative mix of premultiplied RGB: no rim colour the frame did not have. The low-alpha tail keeps its mixed colour (`--clear-below-thr` zeroes it) |

`--scale reach` and `--resample split` are refused with `--pixelate` (exit 1). The run prints
`fit scale_rule reach reach_factor F set_scale K resample split`. When content sits under the feet
line (thin legs or a prop below the core's lowest row) and no `--foot-margin` is given, the foot
margin becomes that depth at the chosen factor plus the 4 px room, so the set is not shrunk to keep
the default margin; a NOTE names the margin and both factors. Two WARNs are worth reading: **reach
limited by content under the feet line** (an explicit `--foot-margin` too small for it) names the
`--foot-margin` that keeps full size, or says to seat with `--register free`; **a `--subject-px`
set shrunk** prints the size it now draws at — slice every other sheet of that character with the
same `--canvas --scale reach`, or at that size, so one PPU still draws them alike.

Traps worth knowing before you argue with a number:

- **A corner speck is a bbox, too.** A soft matte leaves one or two pixels at alpha ~20 in a
  sheet corner; the cell that owns that corner then reads `edge yes`, `bottom` at the cell edge and
  a `baseline` of 0 while its drawing is fine, and the sheet's baseline drift is that one cell.
  `--drop-strays` clears every content pixel not connected to a pixel at alpha ≥ 96 before
  measuring and prints `dropped_strays N px`; the alpha ≤ 16 haze under it stays and is reported
  as the `alpha0` tail (next bullet), which `--clear-below-thr` removes. **A binary key leaves the
  same speck at alpha 255**, where `--drop-strays` cannot see it: the painted field strays from the
  key at the sheet's corners (44.6 RGB off at one corner, past a tolerance of 40), one opaque pixel
  survives, and the corner cell's bbox bottom moves a baseline shift by 12 px. `ground` / `free`
  drop it (`isolated … dropped_bleed_px`), `keep` reports it (`GATE foreign_pixels`), and
  `key_unmix.py` (field distance 60) never leaves it.
- **Two alpha cutoffs, both reported.** Content is measured at `alpha > --alpha-thr` (default 16).
  A soft matte leaves a faint haze invisible at 16 and real to anything using a lower cutoff (e.g.
  one frame's bbox `(151,216,340,504)` at > 16 against `(99,216,340,512)` at > 8). So every frame
  line carries `bbox_alpha0` beside `bbox`, the metric block carries `alpha0_tail_count` /
  `alpha0_tail_max_px` / `baseline_drift_max_px_alpha0`, and `--clear-below-thr` removes the haze at
  the source. A resample (`--subject-px`) makes a tail of its own, and its colour is noise — an
  alpha-1 pixel un-premultiplies to full saturation, `(255,0,255)` off a near-black outline — so
  the run gives that ring its neighbour's colour (`resample_tail N px`), or clears it under
  `--clear-below-thr`.
- **`--align` shifts whole pixels to a whole-pixel target** and prints the residual instead of
  assuming it: a sheet with median bottom 311.5 aligns to 312 and reports `align residual
  baseline_drift_max_px 0.000`. A centroid target cannot be snapped (e.g. 0.549 px after
  `--align both`).
- **When anything moved, the metrics are measured twice** — the `metric` lines describe the
  delivered sheet, a `post_register metric` (or `post_align metric`) block the frames written;
  `frames.json` carries the written set in `set_metrics` and the delivered one in
  `set_metrics_pre_align`, with `set_metrics_stage` naming which is which.
- **`--dup-threshold` belongs to one metric.** On the default `signature` metric 2.0 flags only a
  true stall (a 1 px shift reads ≈ 1.12, 2 px ≈ 2.24) and 4.0 a suspicious pair; `--dup-metric
  pixel` is the strict per-pixel test and its numbers are levels, not signature units. Read either
  against the printed `dup_step_median`. The signature is scale-sensitive: the same aligned sheet
  reads 61 pairs on a 512 px canvas and 4 on its 314 px cells.

### audit_frames.py — the gate on what shipped

```bash
# every sequence under a folder: one line each, exit 1 on a hard fault, one onion skin per sequence
"$PY" "$S/audit_frames.py" /abs/Assets/Art/Characters/*/ --key-color '#ff00ff' \
  --csv /abs/review/audit.csv --onion /abs/review/onion.png
# an idle that will be cycled: also classify it hold / BOIL
"$PY" "$S/audit_frames.py" /abs/out/idle --key-color '#ff00ff' --hold
# the verdicts the gates gave before resid and sparse existed
"$PY" "$S/audit_frames.py" /abs/out/* --key-color '#ff00ff' --residual-max -1 --sparse-min 0
```

Full flag set: `sequences… [--key-color HEX] [--mode ground|free|centroid|keep] [--ref N] [--hold]
[--fringe-max 0.5] [--tint-max 2] [--feet-max 3] [--slip-max 1] [--hold-iou 0.90]
[--residual-max 120] [--sparse-min N] [--csv PATH] [--onion PATH] [--no-gate] | --selftest`.
Exit 0 pass · 1 a hard gate failed · 2 nothing was read.

Two gates are on by default beside feet, slip, fringe, tint and cut. **`resid`** counts, per
frame, the pixels at alpha > 16 within 150 RGB of the key — anywhere, not only on the rim — and
fails a frame over `--residual-max` (120); the key is `--key-color`, else the sidecar's
`set_metrics.key_color`, else the column reads `n/a` and nothing is gated (fringe and tint still
need `--key-color`). **`opaque/floor`** is the frame's count of pixels at alpha > 0 against the
sparse floor `ceil(sqrt(W x H))` of its canvas — half that for a `centroid` (effect) sequence —
or `--sparse-min N`; under it the frame is empty or debris. `-1` / `0` turn them off. The table
prints the worst frame of each (`resid` the largest count, `opaque/floor` the smallest), a failing
sequence names its frames, and `--csv` gains `residual_px` and `opaque_px`. A frames.json run
skips frames the sidecar marks empty; a bare PNG directory counts them, and they fail sparse. How
to read a failure and which tool repairs it: `reference/animation-faults.md` §1a. It re-opens
the PNGs — it does not read the numbers `frames.json` carries — and a sidecar with no
`register.mode` (an older slicer's) is judged as an in-place action, which is the fault it exists
for; `--mode keep` is the caller saying the travel is authored. `head_x` (the head's sideways
spread) and `iou` are printed and never gated: both move when the pose does.

### breathe.py — an idle from one still pose

A pose that has to read as alive — the sentry waiting at the gate, the runner before the launch —
needs no sheet: `breathe.py` turns one keyed still into a breathing loop on the same canvas. A
squash-and-stretch field, strongest in the chest, zero at the feet and above the neck, plays over
a phase loop; rows are only duplicated or deleted whole and columns remapped by integers, so every
output pixel is a copy of an input pixel. The head block above the fade band (`identity_rows`) is
bit-identical in every frame and rides up and down by whole pixels (`head_dy_px`); the feet stay
on the content's bottom line; equal phases are identical frames, so the loop closes.

```bash
# the sentry's idle: 12 frames, one breath, the neck found from the width profile
"$PY" "$S/breathe.py" /abs/keyed/sentry_idle.png --out-dir /abs/out/sentry_idle --frames 12 --fps 8
# a large illustration: depth auto already keeps the breath shallow; the rigid part named by hand
"$PY" "$S/breathe.py" /abs/keyed/runner_portrait.png --out-dir /abs/out/runner_breathe \
  --rigid-from 0.35 --name runner_breathe
"$PY" "$S/frames_to_anim.py" --frames-json /abs/out/sentry_idle/frames.json --bg '#808080' \
  --out /abs/review/sentry_idle.gif --onion /abs/review/sentry_idle_onion.png
```

Full flag set: `IMAGE --out-dir DIR [--frames 12] [--breaths 1] [--depth auto] [--lag 0.10]
[--rigid-from auto|0.xx] [--rigid-fallback 0.30] [--fps 8] [--name STEM] | --selftest`.
`--depth` is the total stretch as a share of the body below the neck; the head lifts by about
depth × those rows. The default `auto` aims that lift at max(3 px, 1.5% of the content height)
and caps depth at 0.06: 0.06 on a 64 px sprite, about 0.017 on a 280 px figure (a ±4 px lift,
where a fixed 0.06 lifts it 13 px and reads as a squat). A number overrides it; the output
records `depth` and `depth_source`. `--rigid-from auto` takes the narrowest width minimum
in the top 5–60% of the content (the neck), falls back to `--rigid-fallback` when there is none (a
blob, a hooded figure), and caps the boundary at 80% of the height; `--lag` delays the upper body
by a share of a breath. Fewer than 6 frames per breath is a warning — it reads as a twitch.
Exit 0 written · 1 usage, an unreadable or empty input, a bad fraction, or a failed selftest ·
**2 refused, nothing written**: the per-row strain exceeds 0.25 (lower `--depth` or raise the
rigid boundary) or a frame pushes an opaque pixel off the canvas top, left or right (widen the
canvas margin or lower `--depth`). It prints one JSON object.

Its `frames.json` follows the §4 contract: `register {mode: keep, ref: 0}` (each frame stays where
it is drawn), `pivot_norm` at the foot centre, `fps_hint`, `loop: true`, `verdict {ok, faults}`,
`producer {skill: codex-visual, script: breathe.py}`, the input as `source` and `source_sha256`
(there is no `sheet`), a `breathe` block (the parameters, the neck and rigid rows, `identity_rows`,
`row_strain`, `period_s`, warnings) and per frame `phase` and `head_dy_px`. Its ground line is the
input's content bottom, pinned in every frame, so there is no `align residual` to read. It is the repair for
a `BOIL` idle (`reference/animation-faults.md` §1a): one approved frame, breathed.

### frames_to_anim.py

```bash
# 1. the common case: sidecar in (order + fps), three previews out
"$PY" "$S/frames_to_anim.py" --frames-json /abs/out/idle/frames.json \
  --out /abs/out/idle/idle.gif --apng --webp

# 2. explicit glob and fps
"$PY" "$S/frames_to_anim.py" /abs/out/attack/*.png --fps 12 --out /abs/out/attack/attack.gif --apng

# 3. a one-shot that freezes on its final pose
"$PY" "$S/frames_to_anim.py" --frames-json /abs/out/cast/frames.json --hold-last 6 --out /abs/out/cast/cast.gif

# 4. ping-pong idle from a half cycle
"$PY" "$S/frames_to_anim.py" --frames-json /abs/out/idle/frames.json --reverse-loop --out /abs/out/idle/idle.gif

# 5. higher-quality, much smaller GIF via ffmpeg palettegen/paletteuse
"$PY" "$S/frames_to_anim.py" --frames-json /abs/out/idle/frames.json \
  --out /abs/out/idle/idle.gif --ffmpeg /opt/homebrew/bin/ffmpeg

# 6. named per-format paths, and lossy WebP
"$PY" "$S/frames_to_anim.py" /abs/frames/*.png --fps 20 --gif /abs/a.gif --webp /abs/a.webp
"$PY" "$S/frames_to_anim.py" /abs/frames/*.png --out /abs/a.webp --webp-quality 80

# 7. the review pair: the loop on a mid-tone ground, and the onion skin (§1)
"$PY" "$S/frames_to_anim.py" --frames-json /abs/out/idle/frames.json --bg '#808080' \
  --out /abs/review/idle.gif --onion /abs/review/idle_onion.png
```

Full flag set: `[frames…] [--frames-json PATH] [--out PATH] [--gif [PATH]] [--apng [PATH]]
[--webp [PATH]] [--fps 10] [--duration-ms MS] [--loop 0] [--hold-last N] [--reverse-loop]
[--webp-quality Q] [--gif-optimize] [--ffmpeg PATH] [--bg HEX] [--onion [PATH]]`. A bare
`--gif`/`--apng`/`--webp`/`--onion` derives its path from `--out`'s stem. Exit 1 on: no frames, a
missing frame file, frames of unequal size, an unknown `--out` extension, a bare format flag with
no `--out`, or an `--onion` path inside the frame directory (it is a PNG — the next glob's extra
frame, and a sprite to an importer).

The `wrote` line is arithmetic — `sequence N = stored_frames X + merged_into_delays Y` — because the
encoder folds a frame identical to its predecessor into a longer delay; that is not a lost frame. A
merge with **no** `--hold-last` prints a WARN: two consecutive inputs are identical, which is a
repeated pose or a stray file in the glob. The GIF matte is cut at the alpha threshold the sidecar
records, so the preview and the report agree about where a sprite ends.

## 3. Pixel art is a post-process, and it belongs to the whole sheet

> **The generator does not make pixel art, and asking harder does not change that.** A cell from a
> full pixel-art brief holds tens of thousands of distinct colours, almost no uniform 4x4 blocks, an
> effective pixel size of 1 px and mostly soft anti-aliased neighbour transitions.

`--palette 24 --pixelate 128 --upscale 4` turns the same sheet into **24 distinct colours**, every
4x4 block uniform and an effective pixel size of 4 px, and leaves drift and CV where they were. Do it
in `sheet_to_frames.py` so the quantisation happens once, on the whole sheet, and every frame shares
one palette — quantising frame by frame is how a pixel loop starts to shimmer.

Two consequences. Pixelating snaps the ground line to the block lattice (e.g. baseline drift
1.5 → 4.0 px, exactly one 4 px block): **register or align after pixelating** — the script's order —
and with `--align`, give `--max-shift` a multiple of the block. `--register` under `--upscale F`
places every frame a whole number of F-px blocks from the reference, so the set keeps one lattice;
`--subject-px` and `--scale-search` resample and are refused with `--pixelate`. And it invents no
motion: a nearly static sheet flags the same duplicate pairs before and after. Post-processing
cannot rescue a dead sheet.

That is `--pixel-method nearest`, the default: it point-samples the sheet at a fixed step. The
generator's blocks are uneven and sit at a different phase in every cell, so `--pixel-method snap`
cuts each cell along its own block edges instead, makes alpha binary and applies the palette to the
small sheet; `--palette-file` / `--palette-out` hold several sheets to one palette, and
`audit_pixel.py` reads the lattice, the alpha and the colours back off the frames. The spec, both
commands, the report and the gate: `reference/pixel-grid.md`.

**The pixel-style cell floor.** Take **128 px** per cell as the working floor for a big-head
character — a starting point, the size the post-process above reduces a 314 px cell *to*: confirm
legibility on one test sheet before committing a set to it. The floor is why 5x5 (250 px), 6x6
(209 px) and even 7x7 (179 px) are workable on one built-in sheet and 8x8 (157 px) is the edge.
Normal styles need far more: ≤ 4x4 (313 px) per sheet, ≤ 3x3 (418 px) for a detailed character.

## 4. Outputs, and the handoff to `unity-2d-sprites`

A passing sheet produces four things: **equal-canvas RGBA frames** (`<name>_000.png` …), the
**`frames.json` sidecar** (order, canvas, pivot, fps hint, how the frames were seated, every metric
above and the verdict), the **keyed sheet** — promote it to `anchors/sets/<action>.png` if the next
animation must match it — and the **previews** (GIF / APNG / WebP and the onion skin), which are
review artefacts only and never live in the frame directory.

The handoff contract, which `unity-2d-sprites` relies on to build an `AnimationClip`:

| | |
|---|---|
| Equal canvas | every frame the same `W x H` — fitted to the registered set, or `--canvas`; **not** assumed to be 512 or square. No per-frame trim, no per-frame rescale |
| One ground line | `register.mode` `ground` with `seat metric feet_drift_px` ≤ 3, or `keep` with `align residual baseline_drift_max_px` 0.000 |
| The pivot | **`pivot_norm`** `[x, y]`, a fraction of the canvas from its bottom-left — the reference's feet line under `ground` / `free` (a foot margin sits under it, so `(0.5, 0)` would float the character), `[0.5, 0.5]` under `centroid`, `[0.5, 0]` for a `keep` set on `--pivot bottom-center` |
| One size per character | every sheet of a character sliced with the same `--subject-px`; `register.reference_core_height_px` is that number, and one PPU then draws them at one size |
| Naming | `<name>_000`, `_001`, … zero-padded to three digits, row-major — the sort order is the play order |
| Timing | fps lives in `frames.json` (`fps_hint`), never in a filename |
| Alpha | keyed by `key_unmix.py`: the 2 px rim carries real alpha (0.35–1) over un-mixed colour and the interior is opaque, so the importer's alpha and the GIF's 1-bit cut land on clean pixels. A resampled set (`--subject-px`) ends in a 1–5 px tail at alpha 1–16 that carries its neighbour's colour; `frames.json` records the `alpha_threshold` and each frame's bare `alpha > 0` bbox beside its thresholded one, and `--clear-below-thr` removes the tail when a trimmer has to agree with the report |
| Cycle or hold | a one-pose loop that `audit_frames.py --hold` calls `BOIL` ships as its reference frame; the motion is the engine's, or `breathe.py` on that frame (`reference/animation-sheets.md` §3a) |
| Verdict | `verdict.ok` true. The engine side re-measures the shipped PNGs anyway (`unity-2d-sprites` → `resources/Tests/SpriteFramesAudit.cs`): the slicer's numbers are the slicer's |

`frames.json` is additive: every key a reader of the older sidecar used is still there with the
same meaning (`frames[].file`, `canvas`, `pivot`, `fps_hint`, `set_metrics.*`, `shift`,
`canvas_offset`, `written`). New: `pivot_norm`, `register {mode, ref, set_scale, subject_px,
foot_margin_px, reference_core_height_px}`, `gutters`, `cell_pad`, `verdict {ok, faults[]}`, per
frame `register {scale, dx, dy, iou}`, `cut_rect`, `cut_sides`, `bleed_dropped_px`, and in
`set_metrics` the `seat` numbers (`feet_drift_px`, `slip_max_px`, `head_x_drift_px`,
`iou_to_ref_min` / `_mean`), the `rim` numbers (`fringe_pct`, `tint_pct`) and
`incell_x_grid_r2` / `incell_baseline_grid_r2`. Under the fit options only, `register` also
carries `scale_rule: "reach"`, `reach_factor` (≤ 1) and `reach_margin_px` (`--scale reach`),
`resample: "split"` (`--resample split`), and `align_x: "foot"` with `foot_band_frac: 0.2`
(`--align foot`, which also sets the top-level `align` to `"foot"`). A `breathe.py` sidecar adds
`producer`, `loop`, `source` / `source_sha256` and the `breathe` block above. A
`sprite-from-video` `video_loop.py` sidecar adds `producer`, `loop`, `hold_last`, `source {file,
sha256, fps}`, in `register` the feet-line numbers (`floor_spread_px`, `source_floor_spread_px`,
`seated_max_px`), and `cut`, `seam`, `drift` and `subsample {indices, steps, even}`.

Unity plays no GIF, APNG or WebP. The game wants the frames plus a clip, and that is where
`codex-visual` stops.

Register the whole animation as one `manifest.md` row, its notes column carrying the shape the
next re-generation needs:
`| <date> | Assets/…/hero_idle_000.png…_007.png | animation | 352x500 | v1 | animation: frames=8 fps=10 loop=yes grid=3x3 register=ground subject_px=470 sheet=<keyed sheet path> report=pass |`
