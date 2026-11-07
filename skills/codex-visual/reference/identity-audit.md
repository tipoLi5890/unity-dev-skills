# identity-audit — identity and motion numbers for a 2D frame set

`audit_frames.py` gates what has one repair: feet, slip, key, cut. `audit_identity.py` puts numbers
on what a viewer says about a set that passed it: "it is not the same character", "it pops at the
loop", "it flickers", "the legs swapped". It writes one gate/1 report.

**Every number is report-only.** Each gate has `limit: null` and `pass: true`, so nothing fails on
it. There are no thresholds yet. They come later, from the numbers of many real sets. Read the
numbers, compare sets, and look at the frames the report names.

## 1. The numbers

| Gate | What it measures | Worse is | Needs |
|---|---|---|---|
| `identity.frame_to_frame_min` | lowest embedding cosine between consecutive frames; a loop includes the wrap (last → first). `at` names the pair | lower | frames, embeddings |
| `identity.still_min` | lowest cosine of a frame against the approved still. `at` names the pair (`still/6`: frame 6) | lower | `--still`, embeddings |
| `identity.still_mean` | mean cosine of every frame against the approved still | lower | `--still`, embeddings |
| `identity.front_side` | mean cosine over every (frame, side image) pair | lower | `--side`, embeddings |
| `motion.loop_seam_ratio` | the wrap's distance over the mean ordinary step; `saturated` says when a skipped stretch cannot read | far above 1 (a pop) or far below 1 (a stall) | a loop of 3+ frames |
| `motion.flicker_share` | the largest share of a frame's stable silhouette that flashes A → B → A. `frame` names it | higher | 3+ frames |
| `motion.limb_swap_frames` | how many frames have their legs' looks on the wrong sides. `frames` lists them, `method` says how they were read, `checked` how many frames could be | more | 3+ frames, legs that differ in colour or shading |

The identity gates carry the DINOv2 cosine as `value` and the SigLIP 2 cosine beside it
(`siglip2`; for a min, `siglip2_at` names its own lowest pair). DINOv2 follows shape, parts and
pose, so in a walk it moves with the pose. SigLIP 2 follows what the picture shows and its style: a
jacket that changes colour on one frame shows in `siglip2` and `siglip2_at` first. Read both.
A cosine of 1 is the same embedding.

## 2. When to run it

- After `sheet_to_frames.py` and `audit_frames.py` on a codex animation sheet: the frames are
  seated, so the numbers read the drawing, not the register.
- On `sprite-from-video` frames, after the loop is cut.
- Front against side, for a character drawn in both views: `--side` with the side set.

```bash
python3 scripts/audit_identity.py out/runner_run --still ArtDirection/runner_base.png --out review/identity.json
python3 scripts/audit_identity.py out/runner_run/frames.json --side out/runner_run_side --out review/identity.json
python3 scripts/audit_identity.py out/runner_attack --no-loop --out review/attack/identity.json
```

`FRAMES` is a folder of PNG frames (the `frames.json` order when it holds one, else name order) or
a `frames.json`. Whether the set loops comes from the sidecar's `loop`; a bare folder is a loop.
`--loop` / `--no-loop` overrule it. `--side` takes a folder or one PNG.

## 3. Embeddings on a second machine

The identity gates need torch. `embed.py` (beside this script) measures them. Every run writes
`pairs.json` next to the report, with the pairs it needs and paths relative to that folder. Give each
set its own report folder: a second run in the same folder replaces its `pairs.json`.

1. Run `audit_identity.py` here. The identity gates read `value: null` and are listed under
   `not_measured`.
2. Copy the report folder and the frames to a torch machine. Run
   `embed.py --pairs pairs.json --out sims.json` there.
3. Back here, run the same command with `--sims sims.json`.

```bash
python3 scripts/embed.py --pairs review/pairs.json --out review/sims.json
python3 scripts/audit_identity.py out/runner_run --still ArtDirection/runner_base.png --sims review/sims.json --out review/identity.json
# on the torch machine itself, in one step
python3 scripts/audit_identity.py out/runner_run --still ArtDirection/runner_base.png --embed --device auto --loop --out review/identity.json
```

On a machine with torch, `--embed` measures inline instead (`--device` is `auto`, `cuda`, `mps`
or `cpu`; auto tries them in that order, and the report records the one used). If a model fails to
load or run, its error is the reason the gates are not measured. `--sims` and `--embed` cannot be given together.

**Not measured is not a pass.** Without `--sims` or `--embed`, without an engine, with a
`sims.json` whose `engine` is null, or with a pair missing from it, the gate's `value` is null and
the gate is listed under `not_measured` with the reason. A gate is never filled from part of its
pairs.

## 4. How the motion numbers are read

**Seat.** The frames are first moved onto the reference frame's core, as `audit_frames.py` measures
slip (sideways only for a `ground` set). A `keep` or `centroid` set is read as written.

**Seam.** The distance is the one `sprite-from-video` uses for its loop cut: each frame shrunk to
fit 96 px, RGB multiplied by alpha, the mean absolute RGBA difference in 0..1. All frames share one
crop, the union of what they draw. The ratio is the wrap's distance over the mean of the
consecutive steps, so it has no unit. A wrap that is one ordinary step reads about 1.
`step_max_ratio` beside it is the largest ordinary step in the same unit: a set whose steps are
uneven makes 1.5 at the seam ordinary.

**Seam saturation.** The distance saturates once two frames barely overlap: in a cycle of few
frames with big moves (a 6-frame run, a 10-frame side walk), every pair of frames is about as far
apart as one step, so a skipped stretch reads like an ordinary wrap. `span_ratio` measures it: for
each gap of 2 to n/2 frames, the mean distance between frames that far apart (pairs that do not
cross the seam), the largest of those, in ordinary steps. Below 1.25 the gate carries
`saturated: true` and the report a warning. A cycle that repeats within itself (legs of one colour
half a cycle apart) reads the same way, and is as blind to a skip. The value stays measured: a
stall (a held or doubled frame at the wrap) still reads well under 1, and a pop larger than any
step still reads above it. Only "about 1, so the loop closes" is lost: check such a seam on the
onion skin. `overlap_median` beside it, the median IoU of consecutive frames' cores, is context and
does not decide: a small part that moves far saturates the distance while the body keeps the
overlap high.

**Flicker.** For each frame `i`, the stable silhouette is where the cores of `i-1`, `i` and `i+1`
all overlap. A pixel flickers when frame `i` differs from both neighbours by more than CIE76 10,
while the neighbours agree within 10. The share is over the stable silhouette; the gate reports the
largest share and its frame. A loop wraps its neighbours. A one-frame pose pop also reads here
(a head that tilts for one frame of an idle and is back on the next), and so does a limb that
truly swings back and forth on alternate frames: look at the named frame beside its neighbours.

**Limb swap by colour** (`method: colour`). The leg band is the lower 45% of each frame's core,
split at the torso's axis (the mean x of the core between 20% and 55% of its height). Each half gets
a signature, the median L\*a\*b\* colour of its pixels. The frame whose halves differ most is the
reference; they must differ by CIE76 12. Every frame is then read as straight, crossed, or unread
(the legs overlap) by which pairing of its halves is closer to the reference's. A swap is a read
frame that is the opposite of both neighbours. Legs that cross in a side-view walk change sides for
several frames, through an unread frame, so they are not a swap. The halves hold the whole lower
body, so an arm, a belly patch or the light can make them differ: when the legs, where they stand
apart, differ by less than 12 in every frame, the colour read is set aside for the shape read.

**Limb swap by shape** (`method: shape`), for legs of one colour. In each frame the two legs are
the two blobs of the core below the crotch: rows are added from the feet up, and the cut is the
highest row (no higher than 40% of the core from its top) where the two largest blobs are balanced
(the smaller holds a quarter of the larger) and hold 85% of what lies below, taken before they meet. A frame whose legs touch has no blobs.
Each blob is left or right by its centre and gets the median L\*a\*b\* of its pixels: on legs of
one colour that is the shading, the far leg in shadow. Two consecutive frames are compared only
when both have their legs apart, the two legs differ by CIE76 3 in both, and each leg moved less
than half the legs' spacing, so neither can have passed the other. The link is 1 when each side
keeps its look and -1 when the sides trade looks. A swap is a frame whose links to both neighbours
are -1: the far leg drawn lit and the near leg in shadow for one frame, while the legs stayed
where they were. Legs that cross meet in a frame, which breaks the links, so a crossing is not a
swap.

Limits of the limb read:

- Legs of one colour and one shade (an even light from the front) cannot be told apart: the gate
  is null and listed as not measured, never 0.
- Legs that touch in every frame, or move more than half their spacing in each step: the same.
- Opaque frames (the background not cut) have no silhouette to split: the same.
- `checked` is how many frames had both neighbours read; a 0 swaps on a few checked frames says
  little about the rest.
- A cycle that changes sides on every frame reads every frame as a swap. Check it with the onion
  skin (`audit_frames.py --onion`).
- A run whose same leg leads in every frame never trades sides: it reads 0 swaps and says nothing
  about legs that never alternate. Look at the frames.
- Only the legs are read. Arms cross the torso too often for a side split.

## 5. The report

`--out REPORT.json` is gate/1 (`schemas/gate-1.json`) with `pass: true` and all seven gates, plus:

| Key | What it holds |
|---|---|
| `not_measured` | `[{name, why}]`: each gate whose `value` is null, and why |
| `pairs_file` | the `pairs.json` this run wrote |
| `embedding` | where the cosines came from (`route`: `sims` or `inline`, the engine), or null |
| `detail.seated` | the reference frame and each frame's move, px |
| `detail.flicker_share` | the share per frame |
| `detail.limbs` | `method` (the read used, or the last tried when the gate is null), `checked`; by colour: the reference frame, the two sides' CIE76 separation, each frame's state (1 straight, -1 crossed, 0 unread); by shape also: `apart` and `contrast_de` per frame, and `links` per consecutive pair (the wrap last; 1 kept, -1 traded, 0 not compared) |
| `warnings` | embeddings asked for (`--sims` / `--embed`) and not measured; a saturated seam |

Exit codes: 0 the report was written · 1 usage · 2 no frame to read (the report has
`pass: false` and `refused`).
