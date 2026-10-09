# geometry-gate — position and size are never the model's job

A generation model places a subject *approximately*; the exact centre and the exact size come from
the deterministic pass after it (`slice_grid.py` / `normalize_set.py`), and from the gate that reads
them back off the files that shipped (`audit_set.py`). Symptoms that look like the model's fault and
are not:

| Symptom | Cause | Fix |
|---|---|---|
| "Some sprites come back off-centre" — and the offset differs per asset | the keyer can leave 1–2 pixels at alpha ~20 in a canvas **corner**; a plain `alpha > 16` bbox reaches for them, so the subject is scaled down and pushed to the far side (a set asked at 78% can land at 58–68%, up to 14% of the canvas off) | the set scripts isolate the **subject** (solid pixels grown through their connected soft pixels) and place its **core**; `--raw-bbox` gives the plain-bbox placement for comparison; `normalize_set.py --recenter` repairs a shipped set by translation only |
| a set is internally consistent (identical bboxes, 0% spread) yet everything sits small and high | the same stray pixel, the same way, in every cell — consistency is not correctness | `audit_set.py --expect-frac F` on the shipped files: centre offset and fill against the number the set was normalised to, exit 1 |
| soft rims look thinner after slicing than on the sheet | `paste(im, box, im)` onto a transparent canvas **squares** the alpha of every semi-transparent pixel | both scripts paste mask-free |
| "Can I give the model a 1x1 / 2x2 / 4x4 template with crosshairs so it draws in the right place?" | it paints the crosshairs, and still places the subject approximately — "keep this cell unchanged" is not a capability (`animation-sheets.md` §8) | the grid belongs on the **output** side: one sheet per family (PHASE 3S), then the deterministic slice; a template as *input* is only useful as the ghost-cell variant (`image-model.md` §6) |
| three siblings generated one at a time are three different objects (bboxes 15–25% apart) | each single generation is a fresh context; chaining to a lead nudges style, not geometry | the family is the unit — one sheet; the same three on one 2x2 came back identical to the pixel. A single member regenerated alone drifts: regenerate the family sheet, or chain the single to the family sheet **and** its own previous version |
| an animation cell reports `edge yes`, `baseline 0` or a bbox at the sheet edge while the drawing is fine | the corner stray again, landing in one cell of the sheet | `sheet_to_frames.py --drop-strays` before measuring; `--clear-below-thr` for the alpha ≤ 16 haze it reports as `alpha0_tail` |
| "the character jitters / teleports between frames" — and every frame is fine on its own | animation frames kept at the position the model drew them in the cell. That position follows the model's **grid**, not the action: the column explains 81–100% of the sideways spread on 18 of 21 sheets (`metric incell_x_grid_r2`), and a frame sits 23–119 px from register (`seat metric slip_max_px`) | `sheet_to_frames.py --register ground \| free` seats every frame on one reference by its core silhouette (slip 0 px on all 21); `audit_frames.py` is the gate on the files. Not a regeneration (`animation-sheets.md` §4a) |
| a pink or green hairline round every sprite, static or animated | a binary key or `--despill`: the anti-aliased rim is half key and stays opaque (fringe 5–52%, tint 26–84% per asset) | `key_unmix.py` before slicing; `key_unmix.py --defringe` on files already shipped; `audit_set.py --key-color` / `audit_frames.py --key-color` read it back |
| a sliced asset's rim holds a few pixels of pure key colour at alpha 1–3 | the resampler: LANCZOS over a premultiplied image ends in an alpha 1–3 ring, and un-premultiplying a value of 1 at alpha 1 gives 255 — noise at full saturation (6–9 px on a 256 px icon) | invisible in the PNG and what a bilinear filter mixes into the outline: `key_unmix.py --defringe` clears it; `audit_set.py --key-color` ignores fewer than 12 such pixels (`--rim-floor`) |

## The gate

After every set, before it is registered in `manifest.md`:

```bash
PY=$HOME/.codex/imagegen-venv/bin/python
"$PY" <skill>/scripts/audit_set.py <asset dir>/*.png --expect-frac <F> --fit <long|height|width>
"$PY" <skill>/scripts/audit_set.py jar_a.png jar_b.png jar_c.png --expect-frac 0.78 --symmetry   # upright objects
```

One line per asset: canvas, core bbox, centre offset, fill against `F`, strays; the set's
width/height spread; with `--symmetry` mirror IoU, tilt and rim level. Exit 1 on a centre offset
over 2 px, a fill more than 0.02 off `F`, or with `--symmetry` an IoU below 0.92, a tilt over 8 px,
a rim more than 6 px off level. `--symmetry` is for single upright objects (jars, cups, poles, a
front-facing character); scattered effects, composite icons and animals in profile are asymmetric
by design.

Run it too on any shipped set someone says "looks a bit off": on a 256 px canvas a subject 36 px
off centre and 25% too small still looks fine alone, and a set shrunk the same way in every cell
reads 0% spread. Repair without a regeneration: keyed source still present → re-run the
normaliser from it; gone → `normalize_set.py --recenter` (translation only; the size waits for the
next regeneration).

The animation counterpart is `audit_frames.py <sequence dirs> --key-color HEX`: per sequence the
feet-line spread, the slip from the reference, the rim's fringe and tint, and frames cut by the
canvas — exit 1 on any of them, 2 when it read nothing. Its numbers are defined once, in
`scripts/sprite_ops.py`, which the keyer and the slicer read too.

## Thresholds the scripts share

| | Default | Meaning |
|---|---|---|
| `--alpha-thr` | 16 | above this a pixel is content |
| `--solid-thr` | 96 | at or above this a pixel can seed the subject; a stray at alpha ~20 never does |
| `--core-thr` | 40 | above this, and inside the subject, is the core that sets scale and centre |

The animation scripts use a different core, because a frame has limbs and props where an icon has
a glow: the solid silhouette (alpha > 127) **opened by 4 px**, so anything thinner than ~8 px — a
bat, a tail, a waving arm — drops out and cannot steer a registration or a measurement.

The subject grows from the seeds through connected content pixels (2 px per pass), so a feathered
glow or a thin straw stays whole and an isolated speck is cleared. An image with no solid pixel is
haze: `slice_grid.py` reports the cell EMPTY rather than scaling the haze up.
