# animation-sheets — the prompt template, the failure table, the scripts

One sheet is not evidence about a prompt: the same prompt run twice can differ several-fold on every
metric (e.g. 2 vs 13 near-duplicate pairs), and a palette that holds in one run can turn a uniform
navy in the next. Generate, **measure**, and expect to re-roll. Everything below exists to make the
re-roll decision cheap and mechanical.

Use a sheet for a short loop (idle, breathe, hover, blink, walk), a one-shot performance (attack,
cast, pick up, celebrate), a transformation or reveal, and UI feedback (a button's
press-and-settle).

> **The sheet decides the drawings. It does not decide where they sit.** The model does not put its
> cells on the grid it was asked for: over 21 character sheets the body's in-cell position wandered
> 17–119 px (3–24% of the cell), the grid **column** a frame sat in explained 81–100% of that
> sideways spread on 18 of them, and the **row** explained 90–100% of the vertical spread on 19 —
> the two exceptions being a jump and a leap. Sliced at that position, one idle pose sits 65 px
> apart on alternate frames and the character teleports at 6 fps. Position is the slicer's job
> (§6, `--register`), the key is the keyer's (`key_unmix.py`), and neither fault is repaired by
> generating again (§4a).

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

**Locks 2 and 3 are asked, not obeyed — keep them, and do not rely on them.** With lock 2 in the
prompt the in-cell position still followed the model's own grid (above). A stricter lock 3 — "the
whole subject within 60% of the cell width and 75% of its height" — came back at 64–81% of the
width and 86–98% of the height, and regenerating eleven sheets with it took the frames a subject
was cut in by the equal split from 34 of 85 to 21 of 85; cutting on the found gutters took both
takes to 0 of 85. More empty key colour helps the gutter search; it does not replace it.

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
"$PY" "$S/key_unmix.py" /abs/idle.png --out /abs/idle_keyed.png --key-color '#ff00ff'
"$PY" "$S/sheet_to_frames.py" /abs/idle_keyed.png --rows 3 --cols 3 --key-color '#ff00ff' \
  --register ground --outdir /abs/out/idle --names idle --fps-hint 10
rm /abs/out/idle/idle_008.png     # the deliberately empty cell
"$PY" "$S/frames_to_anim.py" /abs/out/idle/idle_00[0-7].png --fps 10 --reverse-loop \
  --bg '#808080' --out /abs/review/idle.gif --apng --webp --onion /abs/review/idle_onion.png
```

`--reverse-loop` is right **only because the sheet is a half cycle**. Record "loop, half cycle" in
`ART_DIRECTION.md`'s animation row — the flag and the prompt have to agree, and the sheet alone
cannot say which was commissioned.

**A drawn idle may not be cyclable at all, and no slicing changes that.** Each frame of a hold is a
separate drawing of the pose. Of ten one-pose 2x2 sheets, registered, one overlapped its reference
at 0.96 (a true hold); the three batting stances read 0.76–0.80 — four slightly different
drawings — and cycling them *boils* however well they are seated. `audit_frames.py --hold` reads
`hold` at a minimum IoU of 0.90 and `BOIL` below it. A `BOIL` ships as **one frame**, and the
breathing is the engine's (`unity-2d-sprites` → `reference/sprite-animation.md` §5); frame
animation is for the one-shot actions.

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
| The character grows across the sheet (bbox width 173 → 189 px) | Camera creep | Re-roll. No script rescales a frame by default: a per-frame scale search (`--scale-search`) gained at most 0.04 IoU on 21 sheets and its scales did not follow head width — on a crouch-to-rise it shrank the character 4–8% while the head stayed the same size. It fits a pose change with a size change |
| A colour left the palette (a green uniform turned navy) | The agent's rewrite dropped the palette hexes | Identity colours as words **and** hexes inside the identity lock; check the delivered sheet's dominant colours |
| Soles 1 px above the cell bottom although the prompt asked for a margin, and `bleed: none` | The margin clause is still ignored at the ground line; bleed only fires on contact | Read the reported `baseline y` minimum, not just `bleed` |
| Frames are individually fine but the character hops, or jumps sideways on every frame change ("it jitters wildly") | Registration, not motion — the in-cell position follows the model's grid (per-column creep, per-row baseline steps): `seat metric slip_max_px` 23–119 px on 20 of 21 sheets | `--register ground` (or `free`): slip 0 px on all 21. `--align both` is not enough — a centroid is steered by a bat, and 14 of 21 stayed 8–45 px out; `--align baseline` only moves the bbox bottom |
| Feet or a bat tip are cut off, and the next frame shows a sliver of its neighbour | The equal split: the model's rows are not at exact thirds (3–5 of 9 frames cut on six 3x3 sheets) | `--gutters search`, the default: 0 cut. Only a subject cut by the **sheet** edge needs a new sheet |
| A pink / green hairline round every cut-out, in the engine and in the GIF | A binary key (or `--despill`) leaves the anti-aliased rim opaque and key-tinted: fringe 25–40%, tint 43–60% of the rim | `key_unmix.py` (0.0–0.2% / 0.0–0.3%); shipped sprites: `key_unmix.py --defringe` |
| An idle shimmers although every number is green | The frames are different drawings of one pose (`BOIL`, §3a) | One frame + engine motion; never regenerate for it |
| An effect's last frames lost most of their shards | A slicer that keeps "the largest piece and what is near it" — right for a character, fatal for a burst (19–45% of the pixels kept in 11 frames of two effect sheets) | `--register centroid` drops nothing; `ground` / `free` drop only what touches the cut and is not the subject, and gate on losing over 5% |
| After `--register` / `--align`, every frame looks the same and the duplicate count explodes | The only difference between the frames **was** the translation — or the travel was authored in the cell (the run prints `WARN: … do NOT follow the grid`) | No animation: re-roll. Authored travel: put it on the transform in the engine, or `--register keep` |
| The body lurches whenever a prop or an arm moves | `slice_grid.py` was used — it centres each cell on its own bounding box, so a bat moves the box and the body goes the other way | Re-slice with `sheet_to_frames.py --register …`, which seats every frame on one reference by its core silhouette |
| The GIF has a green or grey halo | A soft matte: GIF alpha is one bit, so half-keyed edges — still the key's colour — snap to opaque | `key_unmix.py`: its rim alpha is soft (0.35–1) but its colour is un-mixed, so the 1-bit cut lands on clean pixels. Never `--soft-matte` |
| The subject's own fills came back half-transparent | `--soft-matte` against a key sharing the subject's dominant channel | Key a hue the palette lacks (`#FF00FF`) and drop `--soft-matte` (`reference/codex-runtime.md` §5) |
| A frame is missing (`metric empty_cells frame_011`) | The model skipped a cell — or you commissioned an empty one (§3a) | Re-roll unless it was deliberate; the cell is excluded from every statistic either way |

### 4a. Regenerate, re-slice, re-key — which fault is whose

"Regenerate it" is the reflex, it costs a generation, and for most of what a player complains
about it changes nothing: the next sheet has the same grid wander and the same anti-aliased rim.
Read the fault, then pick the one tool that owns it.

| Fault (and where it is printed) | Owner | Repair |
|---|---|---|
| Empty cell, repeated pose, a costume that changes early, a character that grows (`metric empty_cells`, `near_duplicate_pairs`, `width_cv_pct`) | the **generation** | re-roll |
| Subject cut by the **sheet** edge (`GATE cut_by_sheet_edge`) | the generation | re-roll — the only cut that needs one |
| Subject reaching a cell line with no empty gutter (`GATE cut_by_cell_line` under `--gutters search`) | the generation | re-roll with more space round the subject |
| Subject cut by the equal split (`cut_by_cell_line` under `--gutters nominal`) | the **slicer** | `--gutters search` |
| Jitter, hop, "teleports" (`seat metric slip_max_px`, `GATE grid_wander` / `out_of_register`) | the slicer | `--register ground \| free` |
| Feet on different lines (`seat metric feet_drift_px`) | the slicer | `--register ground`; a jump wants `free` |
| Frames clipped (`GATE clipped_by_canvas`) | the slicer | omit `--canvas` (it is fitted), or the size the WARN prints |
| Pink / green rim (`rim metric fringe_pct` / `tint_pct`, `GATE key_fringe`) | the **keyer** | `key_unmix.py`; already shipped: `--defringe` |
| Idle boils (`audit_frames.py --hold` → `BOIL`) | the **engine** | one frame + procedural motion |
| A jump has no rise, a lunge does not advance | the engine | travel belongs on the transform: `--register free` holds the body still and keeps what the limbs do |

An automatic retry belongs only on the rows owned by the generation. A driver that regenerates on a
gate the generation cannot fix spends its budget and ships the same fault.

Two keys that look simpler than `key_unmix.py`, and are wrong (measured on the same sheets; the
numbers are `fringe` / `tint` / interior made translucent):

| Key | Result |
|---|---|
| Binary, tolerance 40 | 25–40% / 43–60% / 0% — the rim stays key-coloured |
| Alpha from RGB distance **everywhere**, ramp to 330 | 0% / 0% / **36–83%** — every fill nearer the key than the outline goes translucent, white included |
| The same, ramp to 150 | 0% / **33–41%** / 0–27% — the half-mixed rim is past the ramp and stays opaque; `fringe` alone calls this clean |
| Effects: alpha from the key's spill (`min(R,B) − G`) | 0.03% / **29%** on a yellow spark — a pink rim; blue and tan effects pass |
| **Boundary band only**, un-mixed (`key_unmix.py`) | 0.0–0.2% / 0.0–0.3% / 0% (`--edge fill`: up to 1.6%, the blended pockets it is told to treat as mix) |

## 5. Preview formats

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
> tint, cut). Then once more in the engine, from the shipped bytes (§10).

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

### key_unmix.py — before anything is cut

```bash
# a character sheet: un-mix the 2 px boundary band along key -> outline
"$PY" "$S/key_unmix.py" /abs/sheet.png --out /abs/sheet_keyed.png --key-color '#ff00ff'
# an effect sheet (no outline): project the rim onto the fill beside it
"$PY" "$S/key_unmix.py" /abs/fx.png --out /abs/fx_keyed.png --edge fill
# an outline that is not near-black: derive the ramp from its colour
"$PY" "$S/key_unmix.py" /abs/ui.png --out /abs/ui_keyed.png --outline-color '#081930'
# sprites already keyed and shipped: measure, then repair in place
"$PY" "$S/key_unmix.py" --defringe /abs/Assets/Art/UI --dry-run
"$PY" "$S/key_unmix.py" --defringe /abs/Assets/Art/UI --in-place
```

Full flag set: `inputs… [--out PATH | --outdir DIR] [--key-color '#ff00ff'|auto]
[--edge outline|fill] [--lo 60] [--hi 330 | --outline-color HEX] [--band 2] [--choke 0.35]
[--fringe-max 0.5] [--tint-max 2] [--defringe [--in-place]] [--dry-run]`. It prints
`fringe_pct` and `tint_pct` for a binary key and for its own result, and exits 1 when either is
still over its limit, 2 when under 1% of the sheet was keyed (the field is not that colour).
**A sheet that arrives RGBA was keyed by the agent** — such a key has no opaque rim left to un-mix:
it is refused; reject the sheet and ask for an opaque image on the flat key colour.
`--edge fill` is for effects only: on art that itself carries the key's hue (a purple emblem on
magenta) it reads 4–6% fringe and fails its own gate. The two definitions, and why there are two:
`scripts/sprite_ops.py`.

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

# 7. the strict duplicate test, and no sub-threshold tail left behind for a trimmer
"$PY" "$S/sheet_to_frames.py" /abs/sheet_keyed.png --rows 5 --cols 6 \
  --dup-metric pixel --dup-threshold 22 --clear-below-thr --report
```

Full flag set: `sheet --rows --cols [--register ground|free|centroid|keep] [--ref 0]
[--subject-px PX] [--scale-search LO HI] [--foot-margin PX] [--gutters search|nominal]
[--key-color HEX] [--bg-color HEX] [--bg-tol 40] [--force-key] [--alpha-thr 16]
[--clear-below-thr] [--drop-strays] [--inset-frac 0] [--names frame]
[--align none|baseline|centroid|both] [--max-shift PX] [--outdir DIR] [--canvas W H]
[--pivot bottom-center|center] [--fps-hint 10] [--pixelate N] [--palette K]
[--dither none|floydsteinberg] [--upscale F] [--dup-metric signature|pixel]
[--dup-threshold 2.0] [--feet-max 3] [--fringe-max 0.5] [--tint-max 2] [--no-gate]
[--json PATH] [--report]`.
Exit codes: 0 ok · 1 the cells cannot be formed / bad args / missing `--outdir` / **writing without
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
margin is kept under it) and is what the importer's pivot must be (§10).

**`--bg-color` on an already-keyed RGBA sheet is refused** (exit 1; `--force-key` overrides): it
would re-key a finished matte and report a sheet that reads flawless and broken at once
(`transparent_pct 0.0`, bleed on 16 of 16 cells). On an opaque sheet `--bg-color` still makes its
binary key, and the result then fails `GATE key_fringe` on any anti-aliased art — key with
`key_unmix.py` and pass the RGBA with `--key-color`.

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
```

Full flag set: `sequences… [--key-color HEX] [--mode ground|free|centroid|keep] [--ref N] [--hold]
[--fringe-max 0.5] [--tint-max 2] [--feet-max 3] [--slip-max 1] [--hold-iou 0.90] [--csv PATH]
[--onion PATH] [--no-gate]`. Exit 0 pass · 1 a hard gate failed · 2 nothing was read. It re-opens
the PNGs — it does not read the numbers `frames.json` carries — and a sidecar with no
`register.mode` (an older slicer's) is judged as an in-place action, which is the fault it exists
for; `--mode keep` is the caller saying the travel is authored. `head_x` (the head's sideways
spread) and `iou` are printed and never gated: both move when the pose does.

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

# 7. the review pair: the loop on a mid-tone ground, and the onion skin (§5)
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

## 7. Acceptance thresholds — read the report in this order

`--report` writes nothing, so it is the gate: run it on the **keyed** sheet before anything is
written. It ends on `verdict OK | FAIL` and exits 3 on a hard fault, so a driver cannot read past
it; the soft findings above the verdict still need a reader, because whether they are faults
depends on what was commissioned. When frames were moved, **gate on the `post_register metric` /
`post_align metric` block and the `seat metric` lines**, and quote the pre-move numbers when
describing the generation.

| Reported | Accept | Why |
|---|---|---|
| `empty cells` | none, unless you commissioned one | a skipped cell is dropped from every other statistic, so the rest of the report flatters the sheet |
| `near-duplicate pairs` (signature, threshold 2.0) | ≤2 on a 16-frame loop; on a one-shot, only in the last 3–4 frames | the same prompt can swing from 2 pairs to 13; the scale is the script's own `--dup-threshold` help |
| `bleed` / `GATE cut_by_…` | none | under `--gutters search` a subject that still reaches its cut has no gutter; at the sheet edge it was drawn off the image (§4a) |
| `rim metric fringe_pct` / `tint_pct` | ≤ 0.5% / ≤ 2% | a binary key reads 25–40% / 43–60%; `key_unmix.py` 0.0–0.2% / 0.0–0.3% |
| `baseline y` drift, `centroid x` drift, `incell_*_grid_r2` | **not gated — read them as a diagnosis** | on a generated sheet they are large (3–24% of the cell) and follow the grid; they say which `--register` the sheet needs, not whether it is broken |
| `seat metric slip_max_px` (written frames) | ≤ 1% of the reference height, at least 3 px | registered frames read 0–2; the same sheets kept in-cell read 23–119 |
| `seat metric feet_drift_px` (`ground`) | ≤ 3 px | on a 470 px character that is 0.6%: resampling, not a hop. More means the lowest part of the body is not the feet in some frame — `free` |
| `seat metric iou_to_ref_min` | **not gated**; with `audit_frames.py --hold`, ≥ 0.90 to cycle a one-pose loop | below it the frames are different drawings of the pose (§3a) |
| `content width CV` | ≤1% for a loop | a character that grows across the sheet shows here first — re-roll, no script rescales by default |
| `content height CV` | ≤2% for a loop; per stage for a transformation | a transformation legitimately gains parts (§3c) |
| `--align` exit 2 | a refusal of that tool, not of the sheet | a bbox bottom or a centroid is steered by whatever sticks out, so a larger `--max-shift` only moves the fault: seat the frames with `--register ground \| free`, which is gated on what it wrote instead of on how far it moved a frame |

**Registration repairs position, not motion.** A sheet whose frames differ *only* by a translation
collapses under it: drift goes to near zero and the duplicate count jumps (e.g. 0 → 120 pairs on a
synthetic 3 px-per-frame sheet) — there was no animation in the sheet. A real idle can jump too
(e.g. 2 → 61 pairs) when most of what separates the frames is the bob. Re-read the duplicate count
in the post-move block, every time. A sheet with travel authored in the cell collapses the same
way under `ground` / `free` — a synthetic hop and a synthetic lunge both come out as nine
identical frames, with the `WARN` that the removed offsets did not follow the grid — and survives
`keep` to the pixel.

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
1.5 → 4.0 px, exactly one 4 px block): **register or align after pixelating** — the script's order —
and with `--align`, give `--max-shift` a multiple of the block. `--register` under `--upscale F`
places every frame a whole number of F-px blocks from the reference, so the set keeps one lattice;
`--subject-px` and `--scale-search` resample and are refused with `--pixelate`. And it invents no
motion: a nearly static sheet flags the same duplicate pairs before and after. Post-processing
cannot rescue a dead sheet.

**The pixel-style cell floor.** Take **128 px** per cell as the working floor for a big-head
character — a starting point, the size the post-process above reduces a 314 px cell *to*: confirm
legibility on one test sheet before committing a set to it. The floor is why 5x5 (250 px), 6x6
(209 px) and even 7x7 (179 px) are workable on one built-in sheet and 8x8 (157 px) is the edge.
Normal styles need far more: ≤ 4x4 (313 px) per sheet, ≤ 3x3 (418 px) for a detailed character.

## 10. Outputs, and the handoff to `unity-2d-sprites`

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
| Cycle or hold | a one-pose loop that `audit_frames.py --hold` calls `BOIL` ships as its reference frame; the motion is the engine's (§3a) |
| Verdict | `verdict.ok` true. The engine side re-measures the shipped PNGs anyway (`unity-2d-sprites` → `resources/Tests/SpriteFramesAudit.cs`): the slicer's numbers are the slicer's |

`frames.json` is additive: every key a reader of the older sidecar used is still there with the
same meaning (`frames[].file`, `canvas`, `pivot`, `fps_hint`, `set_metrics.*`, `shift`,
`canvas_offset`, `written`). New: `pivot_norm`, `register {mode, ref, set_scale, subject_px,
foot_margin_px, reference_core_height_px}`, `gutters`, `cell_pad`, `verdict {ok, faults[]}`, per
frame `register {scale, dx, dy, iou}`, `cut_rect`, `cut_sides`, `bleed_dropped_px`, and in
`set_metrics` the `seat` numbers (`feet_drift_px`, `slip_max_px`, `head_x_drift_px`,
`iou_to_ref_min` / `_mean`), the `rim` numbers (`fringe_pct`, `tint_pct`) and
`incell_x_grid_r2` / `incell_baseline_grid_r2`.

Unity plays no GIF, APNG or WebP. The game wants the frames plus a clip, and that is where
`codex-visual` stops.

Register the whole animation as one `manifest.md` row, its notes column carrying the shape the
next re-generation needs:
`| <date> | Assets/…/hero_idle_000.png…_007.png | animation | 352x500 | v1 | animation: frames=8 fps=10 loop=yes grid=3x3 register=ground subject_px=470 sheet=<keyed sheet path> report=pass |`
