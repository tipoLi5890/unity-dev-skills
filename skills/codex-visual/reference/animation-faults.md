# animation-faults — the failure table, whose fault it is, the acceptance thresholds

What went wrong on a delivered animation sheet, which tool owns the repair, and which numbers pass
it. The prompt that made the sheet is `reference/animation-sheets.md`; the scripts that print these
numbers, their flags and what they write are `reference/animation-scripts.md`.

## 1. Failure modes

| What you see | What it is | Fix |
|---|---|---|
| Two cells hold the same pose (`near-duplicate pairs`) | The model padded the sheet — the same prompt can give 2 pairs in one run and 13 in the next | Re-roll. If the pairs are the last 3–4 frames of a one-shot, keep them — that is the stable tail |
| Half the sheet is static | "One continuous loop over 16 cells" read as one arc plus filler | Fewer, larger frames — 8 half-cycle frames on a 3x3 plus `--reverse-loop` (`reference/animation-sheets.md` §3a) |
| Each row is its own little cycle | Row wrap read as a new movement | Give every row a named job and state that the row seam is an ordinary step (`reference/animation-sheets.md` §3b) |
| Left and right limbs swap between frames | Screen-left read as the character's left | Say "his own left arm (the one on the right side of the picture)" once, then only ever refer to picture sides |
| The costume changes before its stage | No forbidden-event clause in the earlier stages | Write "absolutely no <part> appears anywhere in frames a-b" into every stage before the change (`reference/animation-sheets.md` §3c) |
| The character grows across the sheet (bbox width 173 → 189 px) | Camera creep | Re-roll. No script rescales a frame by default: a per-frame scale search (`--scale-search`) gained at most 0.04 IoU on 21 sheets and its scales did not follow head width — on a crouch-to-rise it shrank the character 4–8% while the head stayed the same size. It fits a pose change with a size change |
| A colour left the palette (a green uniform turned navy) | The agent's rewrite dropped the palette hexes | Identity colours as words **and** hexes inside the identity lock; check the delivered sheet's dominant colours |
| Soles 1 px above the cell bottom although the prompt asked for a margin, and `bleed: none` | The margin clause is still ignored at the ground line; bleed only fires on contact | Read the reported `baseline y` minimum, not just `bleed` |
| Frames are individually fine but the character hops, or jumps sideways on every frame change ("it jitters wildly") | Registration, not motion — the in-cell position follows the model's grid (per-column creep, per-row baseline steps): `seat metric slip_max_px` 23–119 px on 20 of 21 sheets | `--register ground` (or `free`): slip 0 px on all 21. `--align both` is not enough — a centroid is steered by a bat, and 14 of 21 stayed 8–45 px out; `--align baseline` only moves the bbox bottom |
| Feet or a bat tip are cut off, and the next frame shows a sliver of its neighbour | The equal split: the model's rows are not at exact thirds (3–5 of 9 frames cut on six 3x3 sheets) | `--gutters search`, the default: 0 cut. Only a subject cut by the **sheet** edge needs a new sheet |
| A pink / green hairline round every cut-out, in the engine and in the GIF | A binary key (or `--despill`) leaves the anti-aliased rim opaque and key-tinted: fringe 25–40%, tint 43–60% of the rim | `key_unmix.py` (0.0–0.2% / 0.0–0.3%); shipped sprites: `key_unmix.py --defringe` |
| An idle shimmers although every number is green | The frames are different drawings of one pose (`BOIL`, `reference/animation-sheets.md` §3a) | One frame + engine motion; never regenerate for it |
| An effect's last frames lost most of their shards | A slicer that keeps "the largest piece and what is near it" — right for a character, fatal for a burst (19–45% of the pixels kept in 11 frames of two effect sheets) | `--register centroid` drops nothing; `ground` / `free` drop only what touches the cut and is not the subject, and gate on losing over 5% |
| After `--register` / `--align`, every frame looks the same and the duplicate count explodes | The only difference between the frames **was** the translation — or the travel was authored in the cell (the run prints `WARN: … do NOT follow the grid`) | No animation: re-roll. Authored travel: put it on the transform in the engine, or `--register keep` |
| The body lurches whenever a prop or an arm moves | `slice_grid.py` was used — it centres each cell on its own bounding box, so a bat moves the box and the body goes the other way | Re-slice with `sheet_to_frames.py --register …`, which seats every frame on one reference by its core silhouette |
| The GIF has a green or grey halo | A soft matte: GIF alpha is one bit, so half-keyed edges — still the key's colour — snap to opaque | `key_unmix.py`: its rim alpha is soft (0.35–1) but its colour is un-mixed, so the 1-bit cut lands on clean pixels. Never `--soft-matte` |
| The subject's own fills came back half-transparent | `--soft-matte` against a key sharing the subject's dominant channel | Key a hue the palette lacks (`#FF00FF`) and drop `--soft-matte` (`reference/codex-runtime.md` §5) |
| Key-coloured specks, a hole the key did not clear, or a fill the key ate into — inside the frame, not on the rim (`audit_frames.py` `resid` over 120 in a frame) | The field was painted off the key and the keyer's radius missed it, or the art carries the key's hue | Re-key with `key_unmix.py --edge tint` and the key hex named; if the residue is the art's own colour, re-generate on the key `pick_key.py` chooses from the base still |
| A frame is nearly empty, or only debris (`opaque/floor` under the floor) | An empty cell sliced as a frame, a slice that kept a neighbour's sliver instead of the subject, or a key that erased the subject | Re-slice (`--register`, `--gutters search`), drop a deliberate empty frame from the sequence, or re-generate; a subject erased by the key → `pick_key.py` first |
| A frame is missing (`metric empty_cells frame_011`) | The model skipped a cell — or you commissioned an empty one (`reference/animation-sheets.md` §3a) | Re-roll unless it was deliberate; the cell is excluded from every statistic either way |

### 1a. Regenerate, re-slice, re-key — which fault is whose

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
| Key residue in a frame (`audit_frames.py` `resid` > `--residual-max`, the frames named) | the keyer, then the generation | 1 re-key: `key_unmix.py --edge tint --key-color <hex>`; 2 the residue is the art's own key-hued colour → re-generate on a `pick_key.py` colour; 3 a neighbour's sliver → re-slice |
| A sparse frame (`audit_frames.py` `opaque/floor`, the frames named) | the slicer, then the generation | re-slice (`--register ground \| free`, `--gutters search`); a commissioned empty frame is dropped from the sequence; an empty cell or an erased subject → re-generate, on a `pick_key.py` colour when the key took it |
| Idle boils (`audit_frames.py --hold` → `BOIL`) | the **engine** | one frame + procedural motion, or `breathe.py` on that frame (`reference/animation-scripts.md` §2) |
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

## 2. Acceptance thresholds — read the report in this order

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
| `bleed` / `GATE cut_by_…` | none | under `--gutters search` a subject that still reaches its cut has no gutter; at the sheet edge it was drawn off the image (§1a) |
| `rim metric fringe_pct` / `tint_pct` | ≤ 0.5% / ≤ 2% | a binary key reads 25–40% / 43–60%; `key_unmix.py` 0.0–0.2% / 0.0–0.3% |
| `baseline y` drift, `centroid x` drift, `incell_*_grid_r2` | **not gated — read them as a diagnosis** | on a generated sheet they are large (3–24% of the cell) and follow the grid; they say which `--register` the sheet needs, not whether it is broken |
| `seat metric slip_max_px` (written frames) | ≤ 1% of the reference height, at least 3 px | registered frames read 0–2; the same sheets kept in-cell read 23–119 |
| `seat metric feet_drift_px` (`ground`) | ≤ 3 px | on a 470 px character that is 0.6%: resampling, not a hop. More means the lowest part of the body is not the feet in some frame — `free` |
| `seat metric iou_to_ref_min` | **not gated**; with `audit_frames.py --hold`, ≥ 0.90 to cycle a one-pose loop | below it the frames are different drawings of the pose (`reference/animation-sheets.md` §3a) |
| `audit_frames.py` `resid` (per frame) | ≤ 120 px at alpha > 16 within 150 RGB of the key (`--residual-max`) | counted anywhere in the frame, so it catches what the rim numbers cannot — a speck, a hole, an eaten fill. The key is `--key-color`, else the sidecar's `set_metrics.key_color`; without either it reads `n/a` and does not gate |
| `audit_frames.py` `opaque/floor` (per frame) | opaque px (alpha > 0) ≥ `ceil(sqrt(W x H))` of the canvas, half that for a `centroid` effect (`--sparse-min`) | the floor is the canvas's equivalent side, so it scales with the frame: a 256x256 canvas needs 256 px, a 576x768 one 666. A frames.json run skips frames marked empty; a bare PNG directory does not |
| `content width CV` | ≤1% for a loop | a character that grows across the sheet shows here first — re-roll, no script rescales by default |
| `content height CV` | ≤2% for a loop; per stage for a transformation | a transformation legitimately gains parts (`reference/animation-sheets.md` §3c) |
| `--align` exit 2 | a refusal of that tool, not of the sheet | a bbox bottom or a centroid is steered by whatever sticks out, so a larger `--max-shift` only moves the fault: seat the frames with `--register ground \| free`, which is gated on what it wrote instead of on how far it moved a frame |

**Registration repairs position, not motion.** A sheet whose frames differ *only* by a translation
collapses under it: drift goes to near zero and the duplicate count jumps (e.g. 0 → 120 pairs on a
synthetic 3 px-per-frame sheet) — there was no animation in the sheet. A real idle can jump too
(e.g. 2 → 61 pairs) when most of what separates the frames is the bob. Re-read the duplicate count
in the post-move block, every time. A sheet with travel authored in the cell collapses the same
way under `ground` / `free` — a synthetic hop and a synthetic lunge both come out as nine
identical frames, with the `WARN` that the removed offsets did not follow the grid — and survives
`keep` to the pixel.

## 3. One cell is wrong

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
