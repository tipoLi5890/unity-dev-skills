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
| `motion.loop_seam_ratio` | the wrap's distance over the mean ordinary step | far above 1 (a pop) or far below 1 (a stall) | a loop of 3+ frames |
| `motion.flicker_share` | the largest share of a frame's stable silhouette that flashes A → B → A. `frame` names it | higher | 3+ frames |
| `motion.limb_swap_frames` | how many frames have their leg colours on the wrong sides. `frames` lists them | more | 3+ frames, legs of two colours |

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
uneven makes 1.5 at the seam ordinary. The distance saturates once two frames barely overlap: in a
cycle of few frames with big moves (a 10-frame side walk), every pair of frames is about as far
apart as one step, so a skipped stretch reads like an ordinary wrap. Check such a seam on the
onion skin.

**Flicker.** For each frame `i`, the stable silhouette is where the cores of `i-1`, `i` and `i+1`
all overlap. A pixel flickers when frame `i` differs from both neighbours by more than CIE76 10,
while the neighbours agree within 10. The share is over the stable silhouette; the gate reports the
largest share and its frame. A loop wraps its neighbours. A one-frame pose pop also reads here
(a head that tilts for one frame of an idle and is back on the next), and so does a limb that
truly swings back and forth on alternate frames: look at the named frame beside its neighbours.

**Limb swap.** The leg band is the lower 45% of each frame's core, split at the torso's axis (the
mean x of the core between 20% and 55% of its height). Each half gets a signature, the median
L\*a\*b\* colour of its pixels. The frame whose halves differ most is the reference. Every frame is
then read as straight, crossed, or unread (the legs overlap) by which pairing of its halves is
closer to the reference's. A swap is a read frame that is the opposite of both neighbours. Legs
that cross in a side-view walk change sides for several frames, through an unread frame, so they
are not a swap.

Limits of the limb read:

- Legs of one colour cannot be told apart: the gate is null and listed as not measured.
- Opaque frames (the background not cut) have no silhouette to split: the same.
- A cycle that changes sides on every frame reads every frame as a swap. Check it with the onion
  skin (`audit_frames.py --onion`).
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
| `detail.limbs` | the reference frame, the two sides' CIE76 separation, each frame's state (1 straight, -1 crossed, 0 unread) |
| `warnings` | embeddings asked for (`--sims` / `--embed`) and not measured |

Exit codes: 0 the report was written · 1 usage · 2 no frame to read (the report has
`pass: false` and `refused`).
