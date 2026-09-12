# animation-sheets — the prompt template, the failure table, the scripts

One sheet is not evidence about a prompt: the same prompt run twice can differ several-fold on every
metric (e.g. 2 vs 13 near-duplicate pairs), and a palette that holds in one run can turn a uniform
navy in the next. Generate, **measure**, and expect to re-roll. Everything below exists to make the
re-roll decision cheap and mechanical.

Use a sheet for a short loop (idle, breathe, hover, blink, walk), a one-shot performance (attack,
cast, pick up, celebrate), a transformation or reveal, and UI feedback (a button's
press-and-settle).

## 1. The template

Seven blocks, in this order, in English, one prompt string: the style preamble, the **four locks**
(named in `SKILL.md`, "Decide the shape of the job"; the block below is the **only** paste-verbatim
copy — locks 1-3 for a static set, all four for an animation sheet), then the two job-specific
blocks, identity and time. The preamble goes first because the agent rewrites whatever follows it
before the model sees it (`reference/image-model.md` §2) — so anything that must survive is said in
words **and** hexes, and in more than one block.

### The four locks — paste this prefix unaltered, with the placeholders filled in

```text
<STYLE PREAMBLE from ART_DIRECTION.md, copied unaltered>

LOCK 1 — FIXED SHEET STRUCTURE
This image is a SPRITE SHEET, not a single subject. One image, <cols> columns x <rows> rows =
<N> equal cells, all the same size. Read the cells left to right along each row, then row by row
from the top: row 1 is frames 1-<cols>, row 2 is frames <cols+1>-<2*cols>, … The entire
background, inside every cell and everywhere between cells, is one flat uniform <key colour +
hex> with no shading, no gradient and no tint of that colour on the subject. Do not draw grid
lines, cell borders, frames, separators, gutters of another colour, checkerboard, drop shadows,
ground lines, frame numbers, labels, captions, arrows, UI, scenery, or any text of any kind.

LOCK 2 — SUBJECT POSITION AND SCALE ARE LOCKED
In every cell the body centre sits at the same point of that cell and the soles rest on the same
horizontal baseline, the same distance above the cell's bottom edge. Camera distance, framing and
eye level are identical in every cell: do not zoom, pan, crop or rotate between cells, and the
subject is the same apparent size in every cell. Anchor on the body, never on a prop, a hair
strand, a hem or an effect — never re-centre or rescale a cell because something sticks out
further. Feet do not slide sideways and do not leave the baseline.

LOCK 3 — NOTHING CROSSES A CELL
Every part of the subject, including <the parts that stick out: hair, cloth, weapon, particles,
afterglow>, stays fully inside its own cell with at least <M> pixels of empty background on all
four sides — about 3% of the cell's width, so <M> is 10 px on a 300 px cell and larger on a larger
cell. Nothing crosses a cell boundary and nothing touches the outer edge of the image. If a pose
would not fit, make the motion or the effect smaller — never make the character smaller.

LOCK 4 — ONE CONTINUOUS ACTION (animation sheets only)
The <N> cells are <N> consecutive moments of ONE continuous <duration> <action>. Neighbouring
cells differ only slightly and evenly, so that the cells read as motion. This is NOT a collection
of different poses, not a turnaround, not a selection of variants and not <N> separate drawings.
<For a full-cycle loop:> frame <N> leads straight back into frame 1. <For a half-cycle loop — the
kind `--reverse-loop` plays back out:> frame 1 is one extreme of the motion and frame <N> is the
other, the return is NOT drawn anywhere on this sheet, and no frame repeats. <For a one-shot:> the
last three or four frames are nearly identical to each other, so the sequence settles and can hold
on its last frame.
Do not repeat a pose exactly, and do not jump from a small pose to a large pose between
neighbouring frames.
```

A static set uses locks 1-3 with "each cell holds a different item, at the same scale and framing"
in place of lock 4 (`SKILL.md`, PHASE 3S).

### Then the two job-specific blocks

```text
IDENTITY LOCK (highest priority, obeyed in every cell)
Image 1 is the project style anchor. Image 2 is the character: use <which figure> of Image 2 as
the one and only character. Keep every one of these identical in all <N> cells: <enumerate —
head shape and proportions, hair colour and cut, skin tone, eye shape and colour, mouth,
garment by garment with its hex, trim and bands, gloves, footwear, every held prop and which
hand holds it, outline weight, apparent size>. He is the same drawing in <N> slightly
different moments, not <N> different characters.

TIME STRUCTURE
<For a loop:> These are one single continuous <action> loop of the same character. Frames
1-<N/2> are <the first half>, frames <N/2+1>-<N> <the second half>, and frame <N> leads straight
back into frame 1. Adjacent frames differ only slightly and evenly: <name the two or three parts
that move and by how much>. No <the things that must not happen: step, turn, blink, prop change>.
Do not repeat a pose exactly.
<For a one-shot: use stages — §3c.>
```

The two clauses that close lock 4 — "do not repeat a pose exactly" and "do not jump from a small
pose to a large pose" — are there because the two commonest failures are repetition and
discontinuity, in that order.

## 2. Anchors: order and role labels

`-i` is variadic and the prompt must come first. Pass anchors in this order and **name each one in
the prose**, because the tool receives a bare list of paths:

```bash
codex exec … "$PROMPT" -i anchors/master.png -i anchors/characters/<name>.png -i anchors/sets/<family>.png
#                         1 style anchor        2 identity reference            3 family anchor (omit if none)
```

"Image 1 is the project style anchor. Image 2 is the character whose identity must hold. Image 3 is
the previously approved sheet this one must match." With that labelling, identity holds across every
cell of a 16-frame sheet even when the palette drifts — the labels carry *who*, not *which colours*:
restate the palette as hexes in the prompt. Before passing more than these three, confirm on one
test sheet that the extra reference changes the result.

## 3. Three worked prompts

Only the blocks that change are shown; the preamble and the locks are as in §1.

### 3a. 8-frame idle loop, 3 columns x 3 rows — authored as a HALF cycle

A 3x3 sheet buys 418 px cells against a 4x4's 313 px, so prefer 9 cells to 16 whenever the motion
allows. Eight frames leave one cell over — commission it as empty. The eight frames buy a 14-step
loop because they are **half** a breath and `--reverse-loop` plays the other half; commission a full
cycle here and the flag would run the inhale and the exhale twice each (§5):

```text
LAYOUT … 3 columns x 3 rows = 9 cells. Frames 1-8 occupy the first eight cells in reading order.
The ninth cell, bottom right, holds nothing at all: flat background only, no character, no shape.

TIME STRUCTURE
Frames 1-8 are the FIRST HALF of one continuous idle-breathing cycle of the same standing
character: the slow inhale and rise, and nothing else. Frame 1 is the bottom of the breath and
frame 8 is the top of it; the exhale is NOT drawn on this sheet. Between neighbouring frames the
chest and shoulders rise about 2% of the cell height, the head follows a frame later, and <the
loose prop> sways a few pixels. No step, no turn, no blink, no gesture, no change of expression.
Do not repeat a pose exactly, and do not begin to fall back towards frame 1 at the end.
```

Then slice 3x3 and read `metric empty_cells idle_008` — the script names the cell after `--names` —
as the expected result. Build the preview from the eight real frames:

```bash
"$PY" "$S/sheet_to_frames.py" /abs/idle.png --rows 3 --cols 3 --bg-color '#ff00ff' \
  --outdir /abs/out/idle --names idle --canvas 512 512 --pivot bottom-center --fps-hint 10
rm /abs/out/idle/idle_008.png     # the deliberately empty cell
"$PY" "$S/frames_to_anim.py" /abs/out/idle/idle_00[0-7].png --fps 10 --reverse-loop \
  --out /abs/out/idle/idle.gif --apng --webp
```

`--reverse-loop` is right **only because the sheet is a half cycle**. Record "loop, half cycle" in
`ART_DIRECTION.md`'s animation row — the flag and the prompt have to agree, and the sheet alone
cannot say which was commissioned.

### 3b. 16-frame attack, 4 columns x 4 rows

16 cells is where the row wrap shows: on a 4x4 the largest frame-to-frame change tends to land on
the three row boundaries (e.g. 1.7x and 2.5x the within-row step), so a 4x4 is read as four strips
of four unless the prompt says otherwise. Number the rows and give each a job:

```text
TIME STRUCTURE
Row 1 (frames 1-4) is the wind-up: … Row 2 (frames 5-8) is the strike: … Row 3 (frames 9-12) is
the follow-through: … Row 4 (frames 13-16) is the recovery back to the neutral stand of frame 1.
The last frame of each row leads straight into the first frame of the next row with the same size
of change as inside a row: the four rows are one movement, not four movements.
```

An attack is a one-shot: it needs a stable tail, not a return to frame 1. Preview it with
`--hold-last`, never `--reverse-loop`:

```bash
"$PY" "$S/frames_to_anim.py" --frames-json /abs/out/attack/frames.json --fps 12 --hold-last 6 \
  --out /abs/out/attack/attack.gif --apng
```

12 fps is not a GIF-safe rate (§5) — the GIF is for a glance, the APNG for the review.

### 3c. 30-frame staged transformation, 5 columns x 6 rows

The staged shape is what makes a long sequence work: six stages of five frames, and each stage says
what must **not** have happened yet. Check it on the delivered sheet: the new outfit's colours stay
near zero on the body until the stage that brings them in, then rise and never go back.

```text
TIME STRUCTURE (six stages of five frames)
Frames 1-5, WIND-UP, <starting outfit>: <what the body does>. Frame 1 is a calm neutral stand; by
frame 5 he is <the extreme>. Nothing glows yet. Absolutely no <target-outfit part>, and no sparkle
of any kind, may appear anywhere in frames 1-5.
Frames 6-10, GATHERING, still <starting outfit> and nothing else: <the rise> while <the effect>
grows from two or three marks in frame 6 to a ring of eight or nine in frame 10. The change has
not started: no <part>, no <part>, not even a partial one, appears in frames 6-10.
Frames 11-15, THE CHANGE UNDER LIGHT: a soft light sweeps UPWARD over the body and hides the swap
so the old outfit is never cut off by a hard edge. Frame 11 the light covers the shins and <the
footwear> inside it has already changed; frame 12 <the legs>; frame 13 <the torso>; frame 14 <the
head>; frame 15 the light has shrunk to a thin rim and the whole <outfit> is in place. At no point
is a bare patch of the old outfit left beside a finished piece with a hard edge between them. The
change only ever moves upward: nothing that has already changed goes back in a later frame.
Frames 16-20, SHOWN, <new outfit> complete and identical in all five: <the pose beat>.
Frames 21-25, PEAK: <the biggest pose>, still inside the cell — shrink the motion, not the
character.
Frames 26-30, SETTLE: back to a calm stand. Frames 28, 29 and 30 differ only very slightly from
each other so the sequence can hold on its last frame.
```

That last sentence builds the tail: the last steps come out the smallest in the sheet, and
near-duplicate pairs inside those last frames are the tail doing its job, not a defect. Read
duplicates by **where** they are. A transformation also reads worse on a single CV because the
silhouette legitimately gains parts (e.g. a helmet and a jacket: height CV 5.34%, width CV 17.57% on
229 px cells) — judge it stage by stage.

### 3d. Frame count -> grid -> cell -> split: worked examples

The chain is always frames -> grid -> cell px -> style floor -> split (`SKILL.md`, "Decide the shape
of the job"). Conventional counts decide the grid first: idle 3-8, walk 6-12, attack 4-12. **Fewer,
larger frames win** — a 16-frame breath tends to come back as one live half plus eight near-static
cells, with the flagged duplicate pairs inside the dead half. Commission 8 frames on a 3x3 **as a
half cycle** and ping-pong them (§3a) before you commission 16.

| The ask | Grid on ONE built-in sheet | Cell | Against the style floor | Ship it as |
|---|---|---|---|---|
| 24-frame attack, normal (flat / cartoon / painterly) style | 6 x 4 -> 1536x1024 | 256 px | below the normal-style floor (<= 4x4, 313 px) | **two chained 4x3 sheets** (1448x1086, 362 px cells — frames 1-12 and 13-24) or **three chained 3x3 sheets** (1254x1254, 418 px cells — 8 frames each, the ninth cell empty) |
| 36-frame walk, pixel style | 6 x 6 -> 1254x1254 | 209 px | clears the 128 px pixel working floor (§9) | **one built-in sheet**, with one `--palette` / `--pixelate` pass over all 36 cells (§9) |
| 30-frame transformation, pixel style | 5 x 6 -> 1145x1374 | 229 px | clears the floor | **one sheet**, staged in six blocks of five (§3c) |
| 30-frame transformation, normal style | 5 x 6 -> 1145x1374 | 229 px | below the floor | **two chained 5x3 sheets** (1619x972, 323 px cells — frames 1-15 and 16-30) |

Splitting is not free, so it has rules:

- **Every later sheet chains to the FIRST sheet** (`-i` the approved sheet 1), never to the sheet
  before it — drift compounds down a chain.
- **Same grid aspect and same cell size on every sheet**, so the frames concatenate into one
  timeline instead of changing scale halfway.
- **Say where the seam is.** Sheet 2's prompt states that its frame 1 continues from the pose sheet
  1 ended on, and repeats the same four locks verbatim.
- **Measure each sheet on its own** (`--report`), then concatenate the frame directories in play
  order and renumber — a seam shows as one oversized step between sheets.

## 4. Failure modes

| What you see | What it is | Fix |
|---|---|---|
| Two cells hold the same pose (`near-duplicate pairs`) | The model padded the sheet — the same prompt can give 2 pairs in one run and 13 in the next | Re-roll. If the pairs are the last 3–4 frames of a one-shot, keep them — that is the stable tail |
| Half the sheet is static | "One continuous loop over 16 cells" read as one arc plus filler | Fewer, larger frames — 8 half-cycle frames on a 3x3 plus `--reverse-loop` (§3a) |
| Each row is its own little cycle | Row wrap read as a new movement | Give every row a named job and state that the row seam is an ordinary step (§3b) |
| Left and right limbs swap between frames | Screen-left read as the character's left | Say "his own left arm (the one on the right side of the picture)" once, then only ever refer to picture sides |
| The costume changes before its stage | No forbidden-event clause in the earlier stages | Write "absolutely no <part> appears anywhere in frames a-b" into every stage before the change (§3c) |
| The character grows across the sheet (bbox width 173 → 189 px) | Camera creep | Re-roll. No script may rescale a frame |
| A colour left the palette (a green uniform turned navy) | The agent's rewrite dropped the palette hexes | Identity colours as words **and** hexes inside the identity lock; check the delivered sheet's dominant colours |
| Soles 1 px above the cell bottom although the prompt asked for a margin, and `bleed: none` | The margin clause is still ignored at the ground line; bleed only fires on contact | Read the reported `baseline y` minimum, not just `bleed` |
| Frames are individually fine but the character hops | Registration, not motion — drift is structured by grid position (per-column creep, per-row baseline steps) | `--align baseline` (or `both`) with `--max-shift` — e.g. a baseline drift of 6.5 px of a 314 px cell (2.07 %) goes to 0.00 px |
| After `--align`, every frame looks the same and the duplicate count explodes | The only difference between the frames **was** the translation | Read it as the diagnosis and re-roll; always re-read the duplicate count after aligning |
| Frames look re-centred and the arc is gone | `slice_grid.py` was used — it re-centres each cell | Re-slice with `sheet_to_frames.py`, which keeps each cell's internal position |
| The GIF has a green or grey halo | A soft matte: GIF alpha is one bit, so half-keyed edges snap to opaque | Key hard (drop `--soft-matte`, or let `--bg-color` do the binary key); ship APNG/WebP for a soft edge |
| The subject's own fills came back half-transparent | `--soft-matte` against a key sharing the subject's dominant channel | Key a hue the palette lacks (`#FF00FF`) and drop `--soft-matte` (`reference/codex-runtime.md` §5) |
| A frame is missing (`metric empty_cells frame_011`) | The model skipped a cell — or you commissioned an empty one (§3a) | Re-roll unless it was deliberate; the cell is excluded from every statistic either way |

## 5. Preview formats

| | Alpha | fps | Use |
|---|---|---|---|
| GIF | 1 bit | delays are centiseconds: 10 fps (100 ms) and 20 fps (50 ms) survive; 24 fps is stored as 40 ms, so a 16-frame set runs 640 ms instead of 667 ms | Pasting into a review; the one format everything renders |
| APNG | 8 bit | exact | The real review copy, and anything not at 10/20 fps |
| WebP | 8 bit | exact | Chat windows — `--webp-quality 80` when lossless is too big |

All three keep the source PNGs' bounding boxes frame for frame — GIF disposal is right and nothing
ghosts. `--ffmpeg <path>` routes the GIF through palettegen/paletteuse for a better, smaller file.

Sequence order is frames → `--reverse-loop` (ping-pong, endpoints not repeated) → `--hold-last N`. A
loop gets `--reverse-loop` only if it was authored as a half cycle; a loop that already returns to
frame 1 gets neither flag. A one-shot gets `--hold-last`.

> **An APNG is a `.png`, so a preview left in the frame directory is the next glob's extra frame.**
> A bare `--apng` writes `<stem>_apng.png`, animated inputs are skipped with a printed line, and an
> unrequested merge prints a WARN — but a one-frame preview still slips through. Prefer
> `--frames-json`, and write previews outside the frame directory.

## 6. Script usage

```bash
PY=$HOME/.codex/imagegen-venv/bin/python
S=<repo>/skills/codex-visual/scripts
```

### sheet_to_frames.py

```bash
# 1. the acceptance gate: measure the delivered sheet, key it in place, write nothing
"$PY" "$S/sheet_to_frames.py" /abs/sheet.png --rows 4 --cols 4 --bg-color '#ff00ff' --report

# 2. the same measurement on an already-keyed RGBA sheet
"$PY" "$S/sheet_to_frames.py" /abs/sheet_keyed.png --rows 4 --cols 4 --report

# 3. canonical write: 16 equal frames + the frames.json sidecar
"$PY" "$S/sheet_to_frames.py" /abs/sheet.png --rows 4 --cols 4 --bg-color '#ff00ff' \
  --outdir /abs/out/idle --names idle --canvas 512 512 --pivot bottom-center --fps-hint 10

# 4. repair a bobbing ground line (whole-frame vertical translation), refusing a broken sheet
"$PY" "$S/sheet_to_frames.py" /abs/sheet_keyed.png --rows 4 --cols 4 \
  --align baseline --max-shift 24 --outdir /abs/out/idle

# 5. repair a sideways slide as well
"$PY" "$S/sheet_to_frames.py" /abs/sheet_keyed.png --rows 4 --cols 4 \
  --align both --max-shift 24 --outdir /abs/out/idle

# 6. pixel-art post-process: one shared palette for the whole sheet, 64 px cells back up at 4x
"$PY" "$S/sheet_to_frames.py" /abs/sheet_keyed.png --rows 5 --cols 6 \
  --palette 24 --pixelate 64 --upscale 4 --outdir /abs/out/morph --names morph

# 7. the strict duplicate test, and no sub-threshold tail left behind for a trimmer
"$PY" "$S/sheet_to_frames.py" /abs/sheet_keyed.png --rows 5 --cols 6 \
  --dup-metric pixel --dup-threshold 22 --clear-below-thr --report
```

Full flag set: `sheet --rows --cols [--bg-color HEX] [--bg-tol 40] [--force-key]
[--alpha-thr 16] [--clear-below-thr] [--inset-frac 0] [--names frame]
[--align none|baseline|centroid|both] [--max-shift PX] [--outdir DIR] [--canvas W H]
[--pivot bottom-center|center] [--fps-hint 10] [--pixelate N] [--palette K]
[--dither none|floydsteinberg] [--upscale F] [--dup-metric signature|pixel]
[--dup-threshold 2.0] [--json PATH] [--report]`.
Exit codes: 0 ok · 1 the cells cannot be formed / bad args / missing `--outdir` / `--bg-color` on
an input that already carries alpha · 2 `--align` needed a shift larger than `--max-shift`, and
nothing was written.

**`--bg-color` on an already-keyed RGBA sheet is refused** (exit 1; `--force-key` overrides): it
would re-key a finished matte and report a sheet that reads flawless and broken at once
(`transparent_pct 0.0`, bleed on 16 of 16 cells). Recipe 2 — no `--bg-color` — is the only correct
call for a keyed sheet.

Traps worth knowing before you argue with a number:

- **Two alpha cutoffs, both reported.** Content is measured at `alpha > --alpha-thr` (default 16).
  A soft matte leaves a faint haze invisible at 16 and real to anything using a lower cutoff (e.g.
  one frame's bbox `(151,216,340,504)` at > 16 against `(99,216,340,512)` at > 8). So every frame
  line carries `bbox_alpha0` beside `bbox`, the metric block carries `alpha0_tail_count` /
  `alpha0_tail_max_px` / `baseline_drift_max_px_alpha0`, and `--clear-below-thr` removes the haze at
  the source.
- **`--align` shifts whole pixels to a whole-pixel target** and prints the residual instead of
  assuming it: a sheet with median bottom 311.5 aligns to 312 and reports `align residual
  baseline_drift_max_px 0.000`. A centroid target cannot be snapped (e.g. 0.549 px after
  `--align both`).
- **When `--align` moves anything, the metrics are measured twice** — the `metric` lines describe
  the delivered sheet, a `post_align metric` block the frames written; `frames.json` carries the
  written set in `set_metrics` and the delivered one in `set_metrics_pre_align`.
- **`--dup-threshold` belongs to one metric.** On the default `signature` metric 2.0 flags only a
  true stall (a 1 px shift reads ≈ 1.12, 2 px ≈ 2.24) and 4.0 a suspicious pair; `--dup-metric
  pixel` is the strict per-pixel test and its numbers are levels, not signature units. Read either
  against the printed `dup_step_median`. The signature is scale-sensitive: the same aligned sheet
  reads 61 pairs on a 512 px canvas and 4 on its 314 px cells.

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
```

Full flag set: `[frames…] [--frames-json PATH] [--out PATH] [--gif [PATH]] [--apng [PATH]]
[--webp [PATH]] [--fps 10] [--duration-ms MS] [--loop 0] [--hold-last N] [--reverse-loop]
[--webp-quality Q] [--gif-optimize] [--ffmpeg PATH]`. A bare `--gif`/`--apng`/`--webp` derives its
path from `--out`'s stem. Exit 1 on: no frames, a missing frame file, frames of unequal size, an
unknown `--out` extension, or a bare format flag with no `--out`.

The `wrote` line is arithmetic — `sequence N = stored_frames X + merged_into_delays Y` — because the
encoder folds a frame identical to its predecessor into a longer delay; that is not a lost frame. A
merge with **no** `--hold-last` prints a WARN: two consecutive inputs are identical, which is a
repeated pose or a stray file in the glob. The GIF matte is cut at the alpha threshold the sidecar
records, so the preview and the report agree about where a sprite ends.

## 7. Acceptance thresholds — read the report in this order

`--report` writes nothing, so it is the gate: run it on the delivered sheet before anything is
written. Keying moves drift and CV by hundredths, so a raw-sheet reading is trustworthy — except
baseline, which can move by half a pixel because the key decides where the sole stops; re-measure
it on the keyed sheet before quoting it to the tenth. When `--align` moved anything, **gate on the
`post_align metric` block** and quote the pre-align numbers when describing the generation.

| Reported | Accept | Why |
|---|---|---|
| `empty cells` | none, unless you commissioned one | a skipped cell is dropped from every other statistic, so the rest of the report flatters the sheet |
| `near-duplicate pairs` (signature, threshold 2.0) | ≤2 on a 16-frame loop; on a one-shot, only in the last 3–4 frames | the same prompt can swing from 2 pairs to 13; the scale is the script's own `--dup-threshold` help |
| `bleed` | none — read it on the **keyed** sheet | a raw sheet can show bleed that keying removes |
| `baseline y` drift | ≤3% of cell height before `--align`; **0 px** after, unless a frame clipped | a baseline align lands on a whole pixel, so a non-zero `align residual` is a finding |
| `centroid x` drift | ≤3% of cell width before `--align` | on 229 px cells a sheet at the 3% limit still has 17 px of headroom under `--max-shift 24` |
| `content width CV` | ≤1% for a loop | a character that grows across the sheet shows here first — re-roll, no script may rescale |
| `content height CV` | ≤2% for a loop; per stage for a transformation | a transformation legitimately gains parts (§3c) |
| `--align` exit 2 | a refusal, not a tuning problem | the needed shift exceeded `--max-shift`; nothing was written |

**`--align` repairs registration, not motion.** A sheet whose frames differ *only* by a translation
collapses under it: drift goes to near zero and the duplicate count jumps (e.g. 0 → 120 pairs on a
synthetic 3 px-per-frame sheet) — there was no animation in the sheet. A real idle can jump too
(e.g. 2 → 61 pairs) when most of what separates the frames is the bob. Re-read the duplicate count
after aligning, every time.

## 8. One cell is wrong

> **"Change only that cell, keep the other 15 pixel-identical" is not a capability.** A repair
> request against a delivered sheet, however precisely it names the target cell and forbids every
> other change, re-renders the whole canvas: no untouched cell comes back unchanged.

What *does* survive an edit is registration: the untouched cells keep their silhouettes, centroids
and baseline to within a pixel, while a fresh re-roll is a different drawing. Registration survives,
pixels don't. So an edit is worth one call when the sheet's registration is worth keeping, on two
conditions:

1. **Treat the result as a NEW sheet.** Re-key it — the background comes back at a different value —
   and re-run `--report`. Ship it only if the report passes on its own merits. Never chain repairs.
2. **If the other cells must stay bit-identical** (already reviewed, or already imported), splice
   instead of trusting the edit: the splice leaves the other 15 cells at mean absolute difference
   **0.000** and changes only the target cell.

```python
from PIL import Image                       # $HOME/.codex/imagegen-venv/bin/python
R, C, r, c = 4, 4, 2, 3                     # grid, then the 1-indexed target cell
base, fix = Image.open(BASE), Image.open(EDIT)
assert fix.size == base.size                # if it is not, the edit is not a repair — re-roll
W, H = base.size
box = (round((c-1)*W/C), round((r-1)*H/R), round(c*W/C), round(r*H/R))
base.paste(fix.crop(box), box); base.save(OUT)
```

The same rule holds for a static SET sheet: one cell wrong → **re-gen the whole sheet** (one call,
stays coherent), never patch a single cell separately.

## 9. Pixel art is a post-process, and it belongs to the whole sheet

> **The generator does not make pixel art, and asking harder does not change that.** A cell from a
> full pixel-art brief holds tens of thousands of distinct colours, almost no uniform 4x4 blocks, an
> effective pixel size of 1 px and mostly soft anti-aliased neighbour transitions.

`--palette 24 --pixelate 128 --upscale 4` turns the same sheet into **24 distinct colours**, every
4x4 block uniform and an effective pixel size of 4 px, and leaves drift and CV where they were. Do it
in `sheet_to_frames.py` so the quantisation happens once, on the whole sheet, and every frame shares
one palette — quantising frame by frame is how a pixel loop starts to shimmer.

Two consequences. Pixelating snaps the ground line to the block lattice (e.g. baseline drift
1.5 → 4.0 px, exactly one 4 px block): **align after pixelating**, with `--max-shift` a multiple of
the block. And it invents no motion: a nearly static sheet flags the same duplicate pairs before and
after. Post-processing cannot rescue a dead sheet.

**The pixel-style cell floor.** Take **128 px** per cell as the working floor for a big-head
character — a starting point, the size the post-process above reduces a 314 px cell *to*: confirm
legibility on one test sheet before committing a set to it. The floor is why 5x5 (250 px), 6x6
(209 px) and even 7x7 (179 px) are workable on one built-in sheet and 8x8 (157 px) is the edge.
Normal styles need far more: ≤ 4x4 (313 px) per sheet, ≤ 3x3 (418 px) for a detailed character.

## 10. Outputs, and the handoff to `unity-2d-sprites`

A passing sheet produces four things: **equal-canvas RGBA frames** (`<name>_000.png` …), the
**`frames.json` sidecar** (order, cell size, canvas, pivot, fps hint and every metric above), the
**keyed sheet** — promote it to `anchors/sets/<action>.png` if the next animation must match it —
and the **GIF / APNG / WebP previews**, which are review artefacts only.

The handoff contract, which `unity-2d-sprites` relies on to build an `AnimationClip`:

| | |
|---|---|
| Equal canvas | every frame the same `W x H` (`--canvas`), no per-frame trim, no per-frame rescale |
| One ground line | `--pivot bottom-center` recorded in `frames.json`, `align residual baseline_drift_max_px` 0.000 (a non-zero residual means a frame clipped) |
| Naming | `<name>_000`, `_001`, … zero-padded to three digits, row-major — the sort order is the play order |
| Timing | fps lives in `frames.json` (`fps_hint`), never in a filename |
| Alpha | hard-keyed, no soft matte, so the importer's alpha and the GIF preview agree. `frames.json` records the `alpha_threshold` and each frame's bare `alpha > 0` bbox beside its thresholded one, so a Unity auto-trim and the report can be reconciled — `--clear-below-thr` removes the difference at the source |

Unity plays no GIF, APNG or WebP. The game wants the frames plus a clip, and that is where
`codex-visual` stops.

Register the whole animation as one `manifest.md` row, its notes column carrying the shape the
next re-generation needs:
`| <date> | Assets/…/hero_idle_000.png…_007.png | animation | 512x512 | v1 | animation: frames=8 fps=10 loop=yes grid=3x3 sheet=<keyed sheet path> report=pass |`
