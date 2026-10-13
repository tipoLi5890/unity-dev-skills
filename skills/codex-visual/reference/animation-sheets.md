# animation-sheets — the prompt template, the four locks, the worked prompts

One sheet is not evidence about a prompt: the same prompt run twice can differ several-fold on every
metric (e.g. 2 vs 13 near-duplicate pairs), and a palette that holds in one run can turn a uniform
navy in the next. Generate, **measure**, and expect to re-roll. Everything below exists to make the
re-roll decision cheap and mechanical.

Use a sheet for a short loop (idle, breathe, hover, blink, walk), a one-shot performance (attack,
cast, pick up, celebrate), a transformation or reveal, and UI feedback (a button's
press-and-settle).

This file is the prompt side. What went wrong on a delivered sheet, whose fault it is and which
numbers pass it: `reference/animation-faults.md`. The scripts, the previews, the pixel post-process
and what is handed on: `reference/animation-scripts.md`.

> **The sheet decides the drawings. It does not decide where they sit.** The model does not put its
> cells on the grid it was asked for: over 21 character sheets the body's in-cell position wandered
> 17–119 px (3–24% of the cell), the grid **column** a frame sat in explained 81–100% of that
> sideways spread on 18 of them, and the **row** explained 90–100% of the vertical spread on 19 —
> the two exceptions being a jump and a leap. Sliced at that position, one idle pose sits 65 px
> apart on alternate frames and the character teleports at 6 fps. Position is the slicer's job
> (`reference/animation-scripts.md` §2, `--register`), the key is the keyer's (`key_unmix.py`), and neither fault is repaired by
> generating again (`reference/animation-faults.md` §1a).

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
test sheet that the extra reference changes the result. The same action for a whole cast of
characters, with a finished sheet as the animation reference: §4.

## 3. Three worked prompts

Only the blocks that change are shown; the preamble and the locks are as in §1.

### 3a. 8-frame idle loop, 3 columns x 3 rows — authored as a HALF cycle

A 3x3 sheet buys 418 px cells against a 4x4's 313 px, so prefer 9 cells to 16 whenever the motion
allows. Eight frames leave one cell over — commission it as empty. The eight frames buy a 14-step
loop because they are **half** a breath and `--reverse-loop` plays the other half; commission a full
cycle here and the flag would run the inhale and the exhale twice each (`reference/animation-scripts.md` §1):

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

12 fps is not a GIF-safe rate (`reference/animation-scripts.md` §1) — the GIF is for a glance, the APNG for the review.

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
| 36-frame walk, pixel style | 6 x 6 -> 1254x1254 | 209 px | clears the 128 px pixel working floor (`reference/animation-scripts.md` §3) | **one built-in sheet**, with one `--palette` / `--pixelate` pass over all 36 cells (`reference/animation-scripts.md` §3) |
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

## 4. A character family: one finished sheet as the animation authority

When several characters need the same action, finish it once — generated, keyed, registered,
approved — and pass that sheet as **Image 2, the animation reference**, for every sibling: "Copy
from Image 2 the poses, the timing, the prop, the framing, the character size in the cell and the
position of the feet exactly, but draw `{WHO}` instead." Image 1 stays the style anchor that shows
the whole cast. Keep the locks and the time structure in one template with three placeholders,
filled per character from a small file:

- `{WHO}` — "the red team's round robot"; `{FEATURES}` — the identity lock, colours in words
  and hexes (§1);
- `{KEY_HEX}` — the key colour **per character**, not per project: a character carrying the
  project key's hue gets another key. A character wearing pink was keyed on green instead of the
  project's magenta, before its first try; that one sheet went through.

One project, one run: three siblings of one approved 6-frame swing, all first try, identity steady
across the six cells, all facing the side the reference faced. That is a small sample; gate each
sheet exactly as a new one (`reference/animation-scripts.md` §2).

## 5. Static pose sheets, motion made downstream, and anchors

For a party-game or UI character that reacts more than it performs, a **3x3 sheet of nine static
poses** can replace a dozen animation sheets: idle (front), lean left, cheer, stomp, walk A and
walk B (side), freeze, pull, pull hard. Same locks 1–3 (one size, one baseline, nothing crosses a
cell), identity chained to that character's existing animation sheet as Image 2 — 4 of 4
characters first try in one project, two with a small pose slip that was accepted. The motion is
then made where the game is drawn: squash and stretch, small jumps, a lean or a wobble applied as
a transform **around the feet**, and a pose swap on the beat.

That needs two anchors per pose, measured from the keyed cell, never asked of the model:

- **Feet** — x is the mean x of the opaque pixels in the bottom 1/16 of the subject's height, y
  its lowest row. Every scale and rotation turns about it, and it is the sprite's pivot.
- **Grip**, for poses that reach forward (side view, facing right) — the rightmost opaque pixels
  in the band from 30% to 68% of the subject's height, which keeps the ears above and the feet
  below out of it. The opaque pixels within 26 px of that extreme (on a 300 px tall pose, about
  9%) give the anchor: x their mean, y their median. A held prop or rope attaches there.

**Check them on a dot sheet** — every pose with its feet and grip drawn on as dots, opened and
looked at: in that project 36 feet anchors and 8 grip anchors, all on the feet and fists by eye,
one run. Store them as proportions of the idle pose's height with the feet as origin, so they
survive any resample; in the engine the feet become the sprite pivot (`unity-2d-sprites`) and the
grip a child transform at that offset. A rope passed through the grips reads as held when it is
drawn as sagging quadratic spans between them (a slice of a generated rope stamped along each
span, turned to its direction) and a small soft-edged disc of each character is pasted back over
its grip, so the fist covers the rope.
