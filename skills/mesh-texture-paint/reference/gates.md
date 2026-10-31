# Gates — accepting or rejecting a painted view

A painted view is evidence, not paint. Each try is registered to the render, measured, and either
projected or thrown away. A camera gets `--tries 3` tries; seeds are `42 + 1000 × try + view
index`, and the reference alternates (`painting.md` §3). The first try that passes every gate is
used; when none passes, the best by `(passed, iou_after × filled)` is saved as `_aligned.png` for
inspection, the view is logged `rejected`, and it counts against `--max-views`. Three rejections
in a row end the main loop.

## 1. Registration first

`align_painted` searches a similarity transform on a half-resolution mask: scale **0.97–1.03**
(±3 %, five steps) and shift **±16 px** (2 px steps) at 1024, maximising silhouette IoU against
the render. The painted view is warped by the winner; every gate below reads the warped image.
The output is key-masked against `#00FF00` before and after.

## 2. The gates

| Gate | Flag (default) | Measures | Catches |
|---|---|---|---|
| Silhouette IoU | `--min-iou 0.90` | IoU of the registered painted silhouette and the render's | a redrawn pose, a turned head, a figure the model moved or resized past the search |
| Outline distance | `--max-edge 24` | p90 of the symmetric distance between the two outlines, px at 1024 | a **collage** (extra figures beside the guide put long stretches of outline far away; collages score 70+); a strap or ear drawn elsewhere |
| Painted share | `--min-share 0.3` | share of the guide's unpainted pixels that land inside the painted silhouette | an output that left the new surface empty or keyed it out |
| Brightness drift | `--max-drift 0.08` | share of already-painted pixels whose brightness changed by more than 60 levels | a view that repainted good areas in another palette or lighting |
| Dark to light | `--max-lighten 0.06` | share of already-painted pixels darker than 70 in the guide that came back over 60 levels lighter | dark hair or fabric turned **silver** |
| Background | `--max-bg-dev 40` | median max-channel distance of the background (12 px clear of the figure) from the key | a washed-out pale key — it comes with a washed-out figure |

Notes on reading them:

- **IoU and outline distance are complementary.** IoU depends on how much of the frame the figure
  fills, so a thin side view and a wide front view score differently for the same error; the
  outline p90 is on one pixel scale for both, and a collage fails it even when its IoU passes.
- **Painted share in the default `fill` context** counts unpainted pixels covered by the painted
  silhouette, because the prior already looks painted and no colour test can tell old from new.
  With a grey or magenta marker (`--context flat|clay|magenta`) it counts only pixels that no
  longer show the marker.
- The **first view** skips drift and dark-to-light (nothing is painted yet); **detail passes**
  skip drift and painted share (they repaint painted surface on purpose).

## 3. The outline-disagreement band

Pixels within **6 px** of any place where the painted silhouette and the render disagree (their
XOR, dilated) are not projected and are left out of the drift and dark-to-light tests. A strap or
a backpack flap drawn a few pixels off would otherwise smear its colour onto the body behind it
and count as drift.

## 4. Before projection

When the view passes: despill (`painting.md` §6) if the concept has no key-green, the colour match
(`projection.md` §4), then the weighted back-projection. A view where under 2 % of the visible
silhouette is unpainted is skipped before painting (`skipped: nothing unpainted in view`); detail
passes are never skipped this way.

## 5. Tuning

| Want | Change | Price |
|---|---|---|
| Thin props with holes keep failing IoU | `--min-iou 0.85`; leave `--max-edge` | the outline gate still blocks collages |
| A side view of a narrow subject fails IoU at 0.88–0.90 | `--min-iou 0.87` for that run | slightly looser registration |
| Collages slip through | `--max-edge 18`, or `--ref nearest` | more rejections, more single-view facing copies |
| Good views rejected for drift on a high-contrast subject | `--max-drift 0.12` | more palette wander between views |
| Silver hair still reaches the texture | `--max-lighten 0.03` | dark-coloured views reject more often |
| More views per camera before giving up | `--tries 4` | one more paint job per hard camera |

Change one threshold per run and read the per-view numbers in `report.json` before and after: a
gate whose rejected values sit just past the limit is a threshold question; values far past it
mean the view really is wrong.

## 6. report.json

Mid-run the file is `{"views": [...]}`, rewritten after every view — that is what `--resume`
reads. At the end it gains the totals:

| Field | Meaning |
|---|---|
| `coverage_seeable` | painted share of the seeable surface (`projection.md` §6) |
| `seam_delta` | mean colour step across neighbouring texels owned by different views |
| `views_used` | views projected |
| `minutes` | wall time of this run |
| `settings` | every flag as run |
| `views[]` | one record per camera, in order |

Per view:

| Field | Meaning |
|---|---|
| `name` | `v<NN>_y<yaw>_p<pitch>[z]`, `z` for a zoomed camera; the prefix of its files in `views/` |
| `yaw`, `pitch`, `source`, `zoom` | the camera; `source` is `anchor`, `nbv` or `detail` |
| `unpainted_share` | share of the render that was unpainted |
| `prompt_mode` | `first`, `context` or `detail` |
| `seed`, `ref`, `paint_s` | the try kept: its seed, `sheet` / `nearest` / `front`, seconds |
| `iou_before`, `iou_after`, `scale`, `shift`, `edge_p90` | registration (§1) and the outline gate |
| `filled`, `drift`, `lighten`, `bg_dev` | the other gates' values |
| `match_gain`, `match_offset` or `match` | the colour match, or why it was skipped |
| `texels`, `new_texels` | texels written; of those, newly painted |
| `coverage`, `gain` | coverage after this view and what it added |
| `status` | `used`, `rejected`, `skipped: …` or `failed: no output` (counts as a rejection) |
| `errors` | the tail of a failed paint call |

`turntable.png` is the eye check that goes with it: eight yaws at pitch 10 (`--compare GLB` adds
the original texture as a first row for a before/after).
