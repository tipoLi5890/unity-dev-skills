#!/usr/bin/env python3
"""sheet_to_frames.py — cut an ANIMATION sheet into equal frames, and decide where each frame sits.

This is the opposite of `slice_grid.py`. That script trims every cell to its
content and re-centres it on its own bounding box, which is right for an icon
set and **destroys an animation**: a bat or a raised arm moves the box, so the
body jumps the other way. Nothing here ever centres a frame on its own box.

Where a frame sits is ONE declared choice, `--register`, and writing without it
is refused — a default would be a guess, and both guesses are wrong for somebody:

  ground    the action stays on the floor (idle, attack, swing, a walk in place).
            Every frame is seated on ONE reference frame by its core silhouette:
            feet (the lowest row of the core) locked to one line, x by maximum
            overlap. Whole frames move; a frame is never rescaled.
  free      the same, searching x and y — a jump, a flyer. The body holds still
            and the limbs do what they did; the body's own rise is not kept.
  centroid  an effect: every frame's alpha centroid on the canvas centre, one
            scale for the whole set, nothing dropped.
  keep      each cell's in-cell position is kept as drawn — for motion authored
            INSIDE the cell. `--align` (a whole-set translation by bbox bottom
            and/or alpha centroid) belongs to this mode.

`keep` was this script's only behaviour, on the belief that in a sheet of frames
the motion arc IS the cell-to-cell offset. On a hand-authored sheet it is. On a
generated one, measured over 21 character sheets, the in-cell position of the
body wandered 17-119 px (3-24% of the cell) and the grid COLUMN the frame sat in
explained 81-100% of that sideways spread on 18 of them; the ROW explained
90-100% of the vertical spread on 19 — the two exceptions were the jump and the
leap. The offset is where the model put its cells. Kept, one idle pose jumps
65 px sideways on every frame change; `--align both` (centroid) still leaves
8-45 px on 14 of 21, because a centroid is steered by a bat. Seated by
silhouette, all 21 read 0 px. So `keep` now prints how far its frames sit from
register (`seat metric slip_max_px`) and is gated: when the column explains 60%
or more of the spread and a frame is out of register, that is the grid, not
motion (`GATE grid_wander`). Travel authored across a cell reads 10%.

CELLS are cut on the FOUND gutters (`--gutters search`, the default): the model
does not draw its rows at exact thirds, and the equal split cut the subject in
3-5 of 9 frames on six 3x3 sheets where a cut in the emptiest line nearby cut
none. A cut that already falls on an empty line is not moved, so a sheet drawn
on the true grid is cut exactly as before, and in-cell positions are still
measured from the nominal grid.

GATES. The run ends on `verdict OK|FAIL` and exits 3 on a fault that has one
repair and is not a matter of taste: a subject cut by the sheet edge
(re-generate) or by a cell line with no empty gutter; pixels that are not the
subject reaching the cut; frames clipped by the canvas; a feet line or a slip
over its limit after registration; `grid_wander`; key colour left on the rim
(`--key-color`, or `--bg-color`: fringe and tint, see `sprite_ops.py`). The
faults land in `frames.json` under `verdict`, and the frames are still written
so they can be looked at. `--no-gate` prints the verdict and exits 0. Empty
cells, near-duplicates and the drift numbers stay numbers: whether they are
faults depends on what was commissioned.

Per sheet: (optionally key a flat background, quantise to one shared palette,
pixelate) → cut rows × cols → **measure** every frame → seat or shift → write
equal-size canvases plus a `frames.json` sidecar that `frames_to_anim.py`,
`audit_frames.py` and the Unity clip builder read.

INPUT is either RGBA that is already keyed, or RGB plus `--bg-color` for a hard
distance key done here. Key a colour the art does not contain: with
`remove_chroma_key.py --soft-matte`, alpha comes from how far the key's channel
dominates the other two, so a subject that shares that channel goes translucent
in its fills — a leaf-green (93,169,106) fill against a #00ff00 key comes back at
alpha 147/255 under `--despill --soft-matte` and 255/255 under `--despill` alone.
Magenta `#FF00FF` is the safer key for most palettes, and for GIF-bound frames the
hard binary key here is one bit of alpha, which a GIF wants — but it leaves the
anti-aliased rim OPAQUE and key-tinted (25-40% of the rim within 150 RGB of the
key on 25 sheets), in the GIF as in the engine, so key with `key_unmix.py` and
pass its RGBA here with `--key-color`. `--bg-color` on an input that
ALREADY carries alpha is refused, because it re-keys a finished matte instead of
keying a field: an already-keyed 4x4 sheet re-keyed this way prints
`transparent_pct 0.0` and then reports full-cell bboxes (0,0,314,314), centroid
drift 0.250 px, height CV 0.159% and bleed on 16 of 16 cells — a sheet that is
genuinely fine reading as perfect and broken at once. Drop the flag for RGBA
input; `--force-key` overrides if the alpha really is leftover.

OUTPUT of the measuring pass is one `frame` line per cell, then a `metric` block
carrying one metric per line under the same names `frames.json` uses — so
`grep '^metric baseline_drift_max_px' report.txt` is the acceptance gate, and the
skill quotes the same words the script prints. Metrics are ALWAYS printed;
`--report` measures and writes nothing. Read them in this order: `empty_cells`
(the model skipped a frame) → `near_duplicate_count` (it repeated a pose) →
`bleed_cells` (content reaches its cut line) → `baseline_drift_max_px` (the
character bobs off the floor) → `centroid_x_drift_max_px` (it slides sideways)
→ `incell_x_grid_r2` / `incell_baseline_grid_r2` (how much of that spread
follows the grid column / row rather than the play order).
The first two mean re-generate, and so does a subject cut at the SHEET edge;
the drift is registration, which `--register ground | free` repairs.

A pixel counts as content above alpha `--alpha-thr` (default 16). That cutoff is
printed as `alpha_threshold` and recorded in `frames.json`, because a different
cutoff gives different numbers on the same frames: a soft matte leaves an
alpha-10 haze over the keyed field, invisible at 16 and real to a tool cutting at
8, so one frame can give bbox (151,216,340,504) at alpha>16 against
(99,216,340,512) at alpha>8 — a 0.00 px baseline spread reading as 8 px.

So every frame line and the sidecar carry **both** bboxes: the thresholded one
this script measures and aligns on, and the bare `alpha > 0` one that Unity's
sprite auto-trim, an atlas packer or an ad-hoc `getbbox()` will see. `metric
alpha0_tail_count` and `alpha0_tail_max_px` say how far apart they are, which is
what lets a downstream trim be reconciled rather than argued about: the two can
disagree by whole pixels (e.g. an aligned baseline spread of 0.000 px
thresholded and 6.000 px at alpha > 0). `--clear-below-thr` removes the
question by zeroing every alpha at or below the threshold before slicing.

A sheet whose pixel size does not divide by rows × cols has no single cell size.
The boundaries still follow the true grid — nothing slides — so the cells
themselves differ by a pixel: 1536x1024 at 3x4 gives row heights 341/342/341,
1250x1250 at 4x4 gives column widths 312/313/313/312. Take the cell size from
cell 0, as the obvious reading of "the cell size" does, and every taller cell is
cropped to it by `paste` in silence while the report and `frames.json` go on
quoting the uncropped bbox. So every
percentage below, the default `--canvas`, the paste offset and the baseline come
from the LARGEST cell instead: a short cell ends with a transparent pixel at its
right or bottom edge, and no frame loses a real one. A sheet cropped to a
multiple of the grid never raises the question.

`--align` repairs **registration**, not motion, and the difference matters: it
removes the offset the frames SHARE, so if the only thing separating frames is
that offset — a sheet where the model translated one pose instead of animating
it — alignment collapses every frame onto the same picture. On a synthetic
sheet drifting 3 px/frame, `--align centroid` takes centroid drift from 22.50 px
to 0.50 px and the near-duplicate count from 0 pairs to 120. Read a result like
that as the diagnosis it is — there was no animation in the sheet — and
re-generate.

The metrics are measured TWICE whenever `--align` moves anything: the `metric`
lines describe the sheet as it came in, and a second `post_align metric` block
re-measures the frames that were actually written, on their own canvas. The
sidecar carries both — `set_metrics` is the written set (so a reader using it as
the acceptance gate reads the repaired number, not the pre-repair one) and
`set_metrics_pre_align` is the delivered sheet, with `set_metrics_stage` naming
which is which. The duplicate count is re-read in that second pass too, which is
the one rule alignment always forces.

`--align` pushes content **toward** the canvas edges, and a canvas exactly one
cell big has nowhere to put it — `paste` crops the overhang without a word. So
every frame's shifted bbox is tested against the canvas and any loss is printed
as `WARN: <frame> loses content off the WxH canvas: left/top/right/bottom`.
On a synthetic 4x4 128 px sheet whose content is pinned to the cell top and bobs
3 px per frame, `--align baseline` on the default (cell-sized) canvas cuts 4 rows
off frame_000 — content height 128 written as 124 — while every metric goes on
reporting the pre-shift sheet. Give `--align` a `--canvas` with headroom
(`--canvas 128 132` clears that case).
Under `--pivot bottom-center` the cell floor is the canvas floor, so the loss is
always off the top or the sides and a taller canvas is pure headroom; the warning
prints the size that clears it.

Shifts are whole pixels. `--align baseline` therefore snaps its target to a
whole-pixel median (half up), so every shift is integral and the written set
shares one exact bbox bottom — 0.00 px spread, even frame counts included. You do
not have to take that on trust: the `align residual` line prints what the written
frames measure, and a synthetic 16-cell sheet whose median bottom falls at 107.5
reads `metric baseline_drift_max_px 0.500` on the way in and `align residual
baseline_drift_max_px 0.000` on the way out.
`--align centroid` cannot be exact, because a centroid is fractional: expect up to
0.5 px per frame and up to 1 px across the set, and read the residual line for the
number instead of assuming zero.

Examples:
  # measure first, always — no writes
  sheet_to_frames.py sheet_keyed.png --rows 4 --cols 4 --key-color '#ff00ff' --report

  # an in-place action: seat every frame on frame 0, feet on one line; the canvas is
  # fitted to the registered frames, and the character is 470 px tall in every sheet of it
  sheet_to_frames.py sheet_keyed.png --rows 3 --cols 3 --key-color '#ff00ff' \
      --register ground --subject-px 470 --outdir out/swing --names swing --fps-hint 18

  # a jump; an effect
  sheet_to_frames.py jump_keyed.png --rows 3 --cols 3 --register free --subject-px 470 --outdir out/jump
  sheet_to_frames.py spark_keyed.png --rows 3 --cols 3 --register centroid --outdir out/spark

  # motion authored inside the cell, kept; and the same with a whole-set translation
  # to the median ground line (cell 128 + 4 px of headroom here)
  sheet_to_frames.py sheet_keyed.png --rows 4 --cols 4 --register keep --outdir out/hop
  sheet_to_frames.py sheet_keyed.png --rows 4 --cols 4 --align baseline --max-shift 24 \
      --canvas 128 132 --outdir out/idle

  # pixel-art post-process: one palette for the whole sheet, then 64px cells at 4x
  sheet_to_frames.py sheet_keyed.png --rows 5 --cols 6 --palette 24 --pixelate 64 --upscale 4 \
      --register ground --outdir out/morph

  # the strict duplicate test, and no sub-threshold tail left for a trimmer
  sheet_to_frames.py sheet_keyed.png --rows 5 --cols 6 --dup-metric pixel --dup-threshold 22 \
      --alpha-thr 16 --clear-below-thr --report

Exit codes: 0 ok · 1 rows × cols cells cannot be formed, bad args, a missing
`--outdir`, writing without `--register`, or `--bg-color` on an input that
already carries alpha (see `--force-key`) · 2 `--align` needed a shift larger
than `--max-shift` (nothing written) · 3 a gate failed (the frames ARE written,
`frames.json` carries the faults; `--no-gate` turns this into 0).

Requires Pillow. `--register ground | free | centroid`, `--gutters search` and the
rim measurement also need numpy and `sprite_ops.py` beside this script (codex's
imagegen venv has both: ~/.codex/imagegen-venv/bin/python); without them the
Pillow-only path — `--gutters nominal --register keep` — still runs.
"""
import argparse
import json
import math
import os
import statistics
import sys

from PIL import Image, ImageChops, ImageFilter

THR = 16  # alpha above this counts as content; --alpha-thr overrides it in main()

GRID_R2 = 0.6  # in-cell x spread explained by the grid column at or above this is the grid, not motion
_OPS = None


def ops():
    """(numpy, sprite_ops), or None when either is missing. Loaded on first use, so the
    Pillow-only paths (`--gutters nominal --register keep`) still run in a venv without numpy."""
    global _OPS
    if _OPS is None:
        try:
            import numpy
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            import sprite_ops
            _OPS = (numpy, sprite_ops)
        except ImportError as e:
            _OPS = (None, str(e))
    return _OPS if _OPS[0] is not None else None


def cv(xs):
    """Coefficient of variation (population sigma / mean) over non-zero values."""
    xs = [x for x in xs if x]
    return 0.0 if len(xs) < 2 else statistics.pstdev(xs) / statistics.mean(xs)


def spread(xs):
    """(max deviation from the median, population sigma) — 0.0 for <2 values."""
    if not xs:
        return 0.0, 0.0
    med = statistics.median(xs)
    return max(abs(x - med) for x in xs), (statistics.pstdev(xs) if len(xs) > 1 else 0.0)


def steps(xs):
    """(mean, max) absolute difference between consecutive values."""
    if len(xs) < 2:
        return 0.0, 0.0
    d = [abs(xs[i + 1] - xs[i]) for i in range(len(xs) - 1)]
    return sum(d) / len(d), max(d)


def whole(x):
    """Median rounded half UP to a whole pixel — the target an integer shift can hit exactly.

    `round()` would break ties to even (311.5 -> 312, 310.5 -> 310), which makes
    the target of an even-count set depend on its parity; this does not.
    """
    return float(int(x + 0.5))


def _flat(img):
    """Pixel sequence. Where Pillow has `get_flattened_data()`, `Image.getdata()` is
    deprecated in its favour (removal announced for Pillow 14) and warns on every
    call; the two return the same sequence, so prefer the new name where it
    exists."""
    g = getattr(img, "get_flattened_data", None)
    return g() if g else img.getdata()


def alpha_mask(im):
    return im.getchannel("A").point(lambda p: 255 if p > THR else 0)


def drop_strays(sheet, solid=96):
    """Clear every content pixel (alpha > THR) that is not connected to a pixel at alpha >= solid.

    A soft matte leaves one or two pixels at alpha ~20 in a canvas corner; a plain
    bbox reaches for them, so the corner cell reads a bottom or an edge it does not
    have. Returns (sheet, cleared_px)."""
    a = sheet.getchannel("A")
    soft = a.point(lambda p: 255 if p > THR else 0)
    seed = a.point(lambda p: 255 if p >= solid else 0)
    if seed.getbbox() is None:
        return sheet, 0
    cur = ImageChops.multiply(seed, soft)
    for _ in range(4000):
        grown = ImageChops.multiply(cur.filter(ImageFilter.MaxFilter(5)), soft)
        if ImageChops.difference(grown, cur).getbbox() is None:
            break
        cur = grown
    cleared = soft.histogram()[255] - cur.histogram()[255]
    if cleared:
        out = sheet.copy()
        # keep alpha <= THR haze as it was (it is reported as alpha0 tail), drop only the strays above it
        keep = ImageChops.lighter(cur, a.point(lambda p: 255 if p <= THR else 0))
        out.putalpha(ImageChops.multiply(a, keep))
        return out, cleared
    return sheet, 0


def alpha_bbox(im):
    return alpha_mask(im).getbbox()


def _line_sums(img):
    """Sum of pixel values per row, top to bottom."""
    w, h = img.size
    return [sum(_flat(img.crop((0, y, w, y + 1)))) for y in range(h)]


def centroid(im):
    """Alpha-weighted centroid (cx, cy) in cell-local pixel-centre coords, or None."""
    gated = im.getchannel("A").point(lambda p: p if p > THR else 0)
    rows = _line_sums(gated)
    total = sum(rows)
    if total == 0:
        return None
    cols = _line_sums(gated.transpose(Image.Transpose.TRANSPOSE))
    cx = sum((i + 0.5) * v for i, v in enumerate(cols)) / total
    cy = sum((i + 0.5) * v for i, v in enumerate(rows)) / total
    return cx, cy


def signature(im):
    """512-byte perceptual signature: 16x16 alpha-premultiplied luma + 16x16 alpha."""
    a = alpha_mask(im)
    luma = ImageChops.multiply(im.convert("L"), a)
    small = Image.Resampling.BOX
    return list(_flat(luma.resize((16, 16), small))) + list(_flat(a.resize((16, 16), small)))


def sig_diff(p, q):
    return sum(abs(x - y) for x, y in zip(p, q)) / len(p)


def premultiplied(im):
    """(alpha-premultiplied RGB, binary content mask) — the input to `pixel_diff`."""
    a = alpha_mask(im)
    return Image.merge("RGB", [ImageChops.multiply(b, a) for b in im.convert("RGB").split()]), a


def _band_sum(band):
    return sum(v * n for v, n in enumerate(band.histogram()))


def pixel_diff(p, q):
    """Mean absolute premultiplied-RGB difference over the UNION of two content masks.

    The strict comparison `--dup-metric pixel` selects. It is not diluted by the
    transparent field the way a whole-cell mean would be, and a small whole-body
    translation does not dominate it the way it dominates a 16x16 signature.
    """
    (ia, ma), (ib, mb) = p, q
    u = ImageChops.lighter(ma, mb)
    n = u.histogram()[255]
    if not n:
        return 0.0
    d = ImageChops.difference(ia, ib)
    return sum(_band_sum(ImageChops.multiply(b, u)) for b in d.split()) / (3.0 * n)


def alpha_bbox_any(im):
    """Bbox of every pixel with alpha > 0 — what a tool trimming on bare alpha sees."""
    return im.getchannel("A").getbbox()


def parse_hex(s):
    s = s.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"not a hex colour: {s!r}")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def key_flat_bg(im, rgb, tol):
    """Hard key: alpha 0 where RGB euclidean distance to rgb <= tol, else 255.

    Two different fringes come out of this, and only one of them has an importer fix:

    * the TRANSPARENT pixels keep the chroma colour in their RGB — only alpha
      changed. Invisible in a PNG, it bleeds in the moment an engine filters or
      mip-maps the texture. Unity's **Alpha Is Transparency** repairs that on
      import (`unity-2d-sprites`).
    * the OPAQUE rim does too: an anti-aliased edge pixel was painted as a mix of
      subject and key, sits further from the key than `tol`, and stays at alpha
      255 with its tint. No importer setting touches an opaque pixel, and
      `remove_chroma_key.py --despill` leaves most of it (measured 5-52% of an
      asset's rim still within 150 RGB of the key). This is the pink hairline
      round a cut-out, and it is why `key_unmix.py` exists: this function is
      kept for a sheet with no anti-aliasing to mix, and its result is gated
      (`rim metric fringe_pct` / `tint_pct`).
    """
    src = im.convert("RGB")
    kr, kg, kb = rgb
    t2 = tol * tol
    alpha = bytes(
        0 if (p[0] - kr) ** 2 + (p[1] - kg) ** 2 + (p[2] - kb) ** 2 <= t2 else 255
        for p in _flat(src)
    )
    out = im.convert("RGBA")
    out.putalpha(Image.frombytes("L", im.size, alpha))
    keyed = alpha.count(0) / len(alpha) * 100.0
    print(f"keyed #{kr:02x}{kg:02x}{kb:02x} tol {tol:g} transparent_pct {keyed:.1f}")
    return out


def quantise_sheet(im, k, dither):
    """Quantise the WHOLE sheet to k colours so every frame shares one palette.

    The palette is built from the OPAQUE pixels only, so the transparent field
    does not spend a slot; alpha is re-binarised afterwards.
    """
    a = alpha_mask(im)
    rgb = im.convert("RGB")
    opaque = [p for p, av in zip(_flat(rgb), _flat(a)) if av]
    if not opaque:
        return im
    step = max(1, len(opaque) // 1_000_000)  # cap the palette source at ~1M px
    src = opaque[::step]
    strip = Image.new("RGB", (len(src), 1))
    strip.putdata(src)
    pal = strip.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    d = Image.Dither.FLOYDSTEINBERG if dither == "floydsteinberg" else Image.Dither.NONE
    q = rgb.quantize(palette=pal, dither=d).convert("RGB").convert("RGBA")
    q.putalpha(a)
    used = len({p for p, av in zip(_flat(q.convert("RGB")), _flat(a)) if av})
    print(f"quantised sheet palette {k} distinct_opaque_colours_after {used}")
    return q


def cell_rects(W, H, rows, cols, inset):
    """Row-major (r, c, x0, y0, x1, y1) cell rects, inset inward by a fraction.

    The ONE source of cell geometry in this script: the report header, every
    percentage denominator, the pixelate factor, the default `--canvas`, the paste
    offset and the sidecar all read their cell size from here (through
    `grid_cell_size`), so no two printed numbers can disagree about the same cell.
    """
    rects = []
    for r in range(rows):
        for c in range(cols):
            x0, x1 = round(c * W / cols), round((c + 1) * W / cols)
            y0, y1 = round(r * H / rows), round((r + 1) * H / rows)
            dx, dy = round((x1 - x0) * inset), round((y1 - y0) * inset)
            rects.append((r, c, x0 + dx, y0 + dy, x1 - dx, y1 - dy))
    return rects


def grid_cell_size(W, H, rows, cols):
    """The largest cell of the true grid, read off `cell_rects` and nothing else.

    `W // cols` is the tempting shortcut and it disagrees by a pixel whenever the
    sheet does not divide evenly: a 1254 px sheet at 4 columns is 313 that way and
    314 from the rects — enough for a pixelate line to print `cell 313x313` while
    the report prints `cell 314x314` for the same sheet.
    """
    rects = cell_rects(W, H, rows, cols, 0.0)
    return (max(x1 - x0 for _, _, x0, _, x1, _ in rects),
            max(y1 - y0 for _, _, _, y0, _, y1 in rects))


def gutter_rects(sheet, rows, cols):
    """Row-major cut rects on the FOUND gutters -> (rects, interior cuts that run through content).

    The model does not draw its rows at exact thirds, nor its columns at the same x in every
    row: an equal split cuts feet and bat tips that a cut 20 px away would have missed. Rows are
    found on the whole sheet, columns inside each row band (`sprite_ops.find_cuts`); a cut stays
    on the equal split wherever that line is already empty, so a sheet drawn on the true grid is
    cut exactly as before."""
    np, so = ops()
    content = np.asarray(sheet.getchannel("A")) > THR
    ys, yclean = so.find_cuts(content.sum(axis=1), rows)
    dirty = yclean.count(False)
    rects = []
    for r in range(rows):
        xs, xclean = so.find_cuts(content[ys[r]:ys[r + 1]].sum(axis=0), cols)
        dirty += xclean.count(False)
        for c in range(cols):
            rects.append((r, c, xs[c], ys[r], xs[c + 1], ys[r + 1]))
    return rects, dirty


def touch_sides(crop):
    """[left, top, right, bottom]: which sides of its own cut rect a cell's content bbox reaches."""
    bb = alpha_bbox(crop)
    if not bb:
        return [False] * 4
    return [bb[0] <= 0, bb[1] <= 0, bb[2] >= crop.width, bb[3] >= crop.height]


def grid_r2(values, groups):
    """Share of the variance of `values` explained by `groups` (the grid column or row a frame
    sits in). Near 1.0 = the spread follows the grid, not the play order. None when there is no
    spread or every group holds one frame (nothing left to explain it against)."""
    if len(values) < 3 or len(set(groups)) < 2 or len(set(groups)) == len(values):
        return None
    mean = sum(values) / len(values)
    total = sum((v - mean) ** 2 for v in values)
    if total < 1e-9:
        return None
    resid = 0.0
    for g in set(groups):
        vs = [v for v, gg in zip(values, groups) if gg == g]
        gm = sum(vs) / len(vs)
        resid += sum((v - gm) ** 2 for v in vs)
    return 1.0 - resid / total


def measure_cell(sub, ref_h):
    """Per-frame geometry, at the content threshold AND at bare alpha > 0.

    Two bboxes, because they disagree precisely where a soft matte left a tail:
    everything measured and aligned here uses `alpha > THR`, while Unity's sprite
    auto-trim, an atlas packer and any ad-hoc `getbbox()` see `alpha > 0`.
    `ref_h` is the height the baseline is measured against — the largest cell for
    the delivered sheet, the canvas height for a written frame.
    """
    cell_w, cell_h = sub.size
    bb = alpha_bbox(sub)
    bb0 = alpha_bbox_any(sub)
    m = dict(cell=[cell_w, cell_h], empty=bb is None, bbox=None, width=0, height=0,
             centroid=None, baseline_y=None, bbox_bottom=None, touches_edge=False,
             bbox_alpha0=(list(bb0) if bb0 else None),
             baseline_y_alpha0=(ref_h - bb0[3] if bb0 else None),
             alpha0_tail_px=(bb0[3] - bb[3] if (bb0 and bb) else 0))
    if bb:
        cen = centroid(sub)
        m.update(bbox=list(bb), width=bb[2] - bb[0], height=bb[3] - bb[1],
                 centroid=[round(cen[0], 3), round(cen[1], 3)],
                 bbox_bottom=bb[3], baseline_y=ref_h - bb[3],
                 touches_edge=bool(bb[0] <= 0 or bb[1] <= 0 or bb[2] >= cell_w or bb[3] >= cell_h))
    return m


def duplicates(items, threshold, metric):
    """(pairs at or below threshold, closest pair, median consecutive step).

    The median consecutive step is the same metric over neighbouring frames, and
    it is what makes a threshold readable: a pair "close" only relative to a sheet
    that barely moves is a different finding from one close against a lively sheet.
    """
    names = [n for n, _ in items]
    if metric == "pixel":
        feats = [premultiplied(im) for _, im in items]
        diff = pixel_diff
    else:
        feats = [signature(im) for _, im in items]
        diff = sig_diff
    pairs, closest, mat = [], None, {}
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            v = diff(feats[i], feats[j])
            mat[(i, j)] = v
            if closest is None or v < closest[2]:
                closest = (names[i], names[j], v)
            if v <= threshold:
                pairs.append((names[i], names[j], round(v, 3)))
    consec = [mat[(i, i + 1)] for i in range(len(items) - 1)]
    return pairs, closest, (statistics.median(consec) if consec else 0.0)


def metric_rows(metas, cw, ch, dup_threshold, dup_metric, dup):
    """One ordered aggregate table -> (printable rows, sidecar dict, medians).

    Every metric is built once as (name, printed string, JSON value), so the words
    the report prints and the keys `frames.json` carries cannot drift apart.
    """
    pairs, closest, step_med = dup
    live = [m for m in metas if not m["empty"]]
    empties = [m["name"] for m in metas if m["empty"]]
    bleeds = [m["name"] for m in live if m["touches_edge"]]
    cxs = [m["centroid"][0] for m in live]
    cys = [m["centroid"][1] for m in live]
    bots = [float(m["bbox_bottom"]) for m in live]
    bases = [float(m["baseline_y"]) for m in live]
    heights = [m["height"] for m in live]
    widths = [m["width"] for m in live]
    a0_bases = [float(m["baseline_y_alpha0"]) for m in live if m["baseline_y_alpha0"] is not None]
    tails = [m["alpha0_tail_px"] for m in live]

    dx_max, dx_std = spread(cxs)
    dy_max, dy_std = spread(cys)
    b_max, b_std = spread(bases)
    a0_max, _ = spread(a0_bases)
    sx_mean, sx_max = steps(cxs)
    sy_mean, sy_max = steps(cys)
    med_cx = statistics.median(cxs) if cxs else 0.0
    med_cy = statistics.median(cys) if cys else 0.0
    med_base = statistics.median(bases) if bases else 0.0
    x_r2 = grid_r2(cxs, [m["col"] for m in live])
    b_r2 = grid_r2(bases, [m["row"] for m in live])

    def r2(name, v):
        return (name, "n/a" if v is None else f"{v:.3f}", None if v is None else round(v, 3))

    def f3(name, v):
        return (name, f"{v:.3f}", round(v, 3))

    def raw(name, v, j=None):
        return (name, v, v if j is None else j)

    rows = [
        raw("frames", len(metas)),
        raw("with_content", len(live)),
        raw("empty_count", len(empties)),
        raw("empty_cells", " ".join(empties) if empties else "none", empties),
        raw("cell_w", cw), raw("cell_h", ch), raw("alpha_threshold", THR),
        f3("centroid_x_median", med_cx),
        f3("centroid_x_drift_max_px", dx_max),
        f3("centroid_x_drift_max_pct_cell", dx_max / cw * 100),
        f3("centroid_x_drift_std_px", dx_std),
        f3("centroid_y_median", med_cy),
        f3("centroid_y_drift_max_px", dy_max),
        f3("centroid_y_drift_max_pct_cell", dy_max / ch * 100),
        f3("centroid_y_drift_std_px", dy_std),
        f3("centroid_step_mean_dx_px", sx_mean),
        f3("centroid_step_max_dx_px", sx_max),
        f3("centroid_step_mean_dy_px", sy_mean),
        f3("centroid_step_max_dy_px", sy_max),
        f3("baseline_median", med_base),
        f3("baseline_drift_max_px", b_max),
        f3("baseline_drift_max_pct_cell", b_max / ch * 100),
        f3("baseline_drift_std_px", b_std),
        # the same statistic a downstream alpha>0 trim would compute, beside it
        f3("baseline_drift_max_px_alpha0", a0_max),
        raw("alpha0_tail_count", sum(1 for t in tails if t)),
        raw("alpha0_tail_max_px", max(tails) if tails else 0),
        f3("height_cv_pct", cv(heights) * 100),
        f3("width_cv_pct", cv(widths) * 100),
        # how much of the in-cell spread follows the GRID (column for x, row for the baseline)
        # rather than the play order: near 1.0 it is the model's cell pitch, not motion
        r2("incell_x_grid_r2", x_r2),
        r2("incell_baseline_grid_r2", b_r2),
        raw("dup_metric", dup_metric),
        raw("dup_threshold", f"{dup_threshold:g}", dup_threshold),
        f3("dup_step_median", step_med),
        ("closest_pair",
         f"{closest[0]}~{closest[1]}:{closest[2]:.3f}" if closest else "none",
         [closest[0], closest[1], round(closest[2], 3)] if closest else None),
        raw("near_duplicate_count", len(pairs)),
        ("near_duplicate_pairs",
         (" ".join(f"{x}~{y}:{d:.3f}" for x, y, d in pairs[:12])
          + (f" +{len(pairs) - 12}-more-in-frames.json" if len(pairs) > 12 else "")) if pairs else "none",
         [[x, y, d] for x, y, d in pairs]),
        raw("bleed_count", len(bleeds)),
        raw("bleed_cells", " ".join(bleeds) if bleeds else "none", bleeds),
    ]
    aux = dict(median_cx=med_cx, median_bottom=(statistics.median(bots) if bots else 0.0),
               baseline_drift_max_px=b_max, centroid_x_drift_max_px=dx_max,
               x_r2=x_r2, baseline_r2=b_r2, x_drift_pct=(dx_max / cw * 100 if cw else 0.0))
    return ([(n, p) for n, p, _ in rows], {n: j for n, _, j in rows}, aux)


def main():
    ap = argparse.ArgumentParser(
        description="Cut an animation sheet into equal frames and seat them: by silhouette on one reference "
                    "(--register ground | free), by centroid (effects), or at their in-cell position (keep).")
    ap.add_argument("sheet", help="animation sheet: RGBA already keyed, or RGB + --bg-color")
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--cols", type=int, required=True)
    ap.add_argument("--bg-color", help="flat background to key out here, e.g. '#ff00ff' (hard/binary key: it "
                                       "leaves the anti-aliased rim opaque and key-tinted — prefer a sheet keyed "
                                       "by key_unmix.py). Refused on an input that already carries alpha — see "
                                       "--force-key")
    ap.add_argument("--key-color", metavar="HEX",
                    help="the key colour an already-keyed sheet was generated on: measures the rim's fringe and "
                         "tint on the written frames and gates them (--bg-color implies it)")
    ap.add_argument("--bg-tol", type=float, default=40.0,
                    help="RGB euclidean distance from --bg-color still counted as background (default 40)")
    ap.add_argument("--force-key", action="store_true",
                    help="key --bg-color even though the input already has an alpha channel. Only for a "
                         "file whose alpha is genuinely leftover: re-keying a finished matte reports "
                         "transparent_pct 0.0, full-cell bboxes and bleed 16/16 on a sheet that is fine")
    ap.add_argument("--alpha-thr", type=int, default=16, metavar="N",
                    help="alpha above N counts as content (default 16). Printed as alpha_threshold, "
                         "recorded in frames.json, and reported next to the bare alpha>0 bbox so a "
                         "downstream trim can be reconciled with these numbers")
    ap.add_argument("--clear-below-thr", action="store_true",
                    help="zero every alpha at or below --alpha-thr before slicing, so the written frames "
                         "carry no sub-threshold tail for an alpha>0 trimmer to find")
    ap.add_argument("--drop-strays", action="store_true",
                    help="clear content pixels (alpha > --alpha-thr) not connected to any pixel at alpha >= 96 "
                         "before measuring — a soft matte's corner speckle, which a plain bbox reaches for")
    ap.add_argument("--inset-frac", type=float, default=0.0,
                    help="shrink each cell inward before measuring (default 0). Forces --gutters nominal")
    ap.add_argument("--gutters", choices=["search", "nominal"], default="search",
                    help="search (default) = cut each row and column where the sheet is empty near the equal "
                         "split (columns found per row); nominal = the exact equal split. A cut that already "
                         "falls on an empty line is not moved")
    ap.add_argument("--register", choices=["ground", "free", "centroid", "keep"],
                    help="REQUIRED to write. Where a frame sits on the canvas: ground = seat every frame on the "
                         "reference by its core silhouette, feet locked to one line (an action that stays on "
                         "the floor); free = the same, searching x and y (a jump, a flyer); centroid = centre "
                         "each frame's alpha centroid (effects; never per-frame rescaled); keep = keep each "
                         "cell's in-cell position (ONLY for motion authored inside the cell — on a generated "
                         "sheet that position mostly follows the model's grid, not the action). "
                         "--align other than none implies keep")
    ap.add_argument("--ref", type=int, default=0, metavar="N",
                    help="reference frame for ground/free (default 0); the frame every other is seated on, "
                         "and the one --subject-px measures")
    ap.add_argument("--scale-search", type=float, nargs=2, metavar=("LO", "HI"),
                    help="ground/free: also try a per-frame scale in LO..HI (steps of 0.01), e.g. 0.92 1.08. "
                         "Off by default: scale is only identifiable when the frames are ONE pose")
    ap.add_argument("--subject-px", type=float, metavar="PX",
                    help="resample the WHOLE set by one factor so the reference frame's core is PX tall "
                         "(centroid: so the largest frame's long side is PX). One number per character, so "
                         "two sheets of it draw at one size")
    ap.add_argument("--foot-margin", type=int, metavar="PX",
                    help="ground/free: empty rows kept under the feet line (default 5%% of the placed "
                         "reference height, at least 4); recorded as pivot_norm")
    ap.add_argument("--feet-max", type=float, default=3.0,
                    help="ground: gate on the feet-line spread of the written frames, px (default 3)")
    ap.add_argument("--fringe-max", type=float, default=0.5, help="gate: max fringe %% of rim px (default 0.5)")
    ap.add_argument("--tint-max", type=float, default=2.0, help="gate: max tint %% of rim px (default 2)")
    ap.add_argument("--no-gate", action="store_true",
                    help="print the verdict but exit 0 on a failed gate (the faults stay in frames.json)")
    ap.add_argument("--names", default="frame", help="output prefix (default frame -> frame_000.png)")
    ap.add_argument("--align", choices=["none", "baseline", "centroid", "both"], default="none",
                    help="whole-frame translation only: baseline = match the whole-pixel median bbox bottom, "
                         "centroid = match median centroid x, both = both (default none)")
    ap.add_argument("--max-shift", type=float, default=None,
                    help="refuse to write if any frame needs a shift larger than this many px")
    ap.add_argument("--outdir")
    ap.add_argument("--canvas", type=int, nargs=2, metavar=("W", "H"),
                    help="output canvas px (default = the largest cell); the cell is placed at the SAME "
                         "offset in every frame, and any frame that would lose content off the canvas "
                         "is named in a WARN")
    ap.add_argument("--pivot", choices=["bottom-center", "center"],
                    help="where the cell sits on a larger canvas, and what is recorded in frames.json "
                         "(default bottom-center; center under --register centroid). bottom-center stands "
                         "the cell on the canvas floor, so extra canvas height becomes headroom above it — "
                         "which is what an --align shift needs. ground/free are always bottom-center: the "
                         "reference's feet line is the pivot")
    ap.add_argument("--fps-hint", type=float, default=10.0, help="recorded in frames.json for downstream tools")
    ap.add_argument("--pixelate", type=int, metavar="N",
                    help="downscale every cell to N px on its long side with NEAREST (after --palette). "
                         "It resizes the WHOLE sheet to cols*N x rows*N, so it also regularises a ragged "
                         "grid (a 1254 px sheet's 313.5 px cells become exact) — and --canvas must then "
                         "match N times --upscale, or the frames get padded")
    ap.add_argument("--palette", type=int, metavar="K",
                    help="quantise the WHOLE sheet to K colours once, before slicing (one shared palette)")
    ap.add_argument("--dither", choices=["none", "floydsteinberg"], default="none")
    ap.add_argument("--upscale", type=int, default=1, metavar="F",
                    help="integer NEAREST upscale after --pixelate (default 1)")
    ap.add_argument("--dup-metric", choices=["signature", "pixel"], default="signature",
                    help="how a frame pair is compared. signature (default, cheap) = a 16x16 "
                         "alpha-premultiplied luma + alpha thumbnail, which is dominated by silhouette "
                         "blocks and so amplifies a 1-2 px whole-body shift; pixel (strict, one full-cell "
                         "pass per pair) = the mean absolute premultiplied-RGB difference over the union "
                         "of the two frames' content masks. The two disagree about what is near-static, "
                         "so a threshold belongs to one metric only — read it against the printed "
                         "dup_step_median")
    ap.add_argument("--dup-threshold", type=float, default=2.0,
                    help="flag a frame pair as near-duplicate at or below this difference under "
                         "--dup-metric. SIGNATURE scale, one pose translated against itself on a 128 px "
                         "cell: identical 0.000, 1 px 1.119, 2 px 2.240, 3 px 3.373 — so the default "
                         "2.0 flags only a true stall (a repeated pose or a 1 px nudge) and passes any "
                         "real movement of 2 px or more, while 4.0 also flags a suspicious pair. Scale "
                         "it up for smaller cells, and re-pick it entirely for --dup-metric pixel, whose "
                         "numbers are levels of difference rather than signature units")
    ap.add_argument("--json", help="sidecar path (default <outdir>/frames.json)")
    ap.add_argument("--report", action="store_true", help="measure only; no writes")
    a = ap.parse_args()

    if a.rows < 1 or a.cols < 1:
        print("ERROR: --rows and --cols must be >= 1", file=sys.stderr)
        return 1
    if a.upscale < 1:
        print("ERROR: --upscale must be >= 1", file=sys.stderr)
        return 1
    if not 0 <= a.alpha_thr <= 254:
        print(f"ERROR: --alpha-thr {a.alpha_thr} must be between 0 and 254", file=sys.stderr)
        return 1
    global THR
    THR = a.alpha_thr

    if not 0 <= a.ref < a.rows * a.cols:
        print(f"ERROR: --ref {a.ref} is outside the {a.rows}x{a.cols} grid (0..{a.rows * a.cols - 1})",
              file=sys.stderr)
        return 1

    # ---- where a frame sits on the canvas is the caller's decision, made out loud
    registered = a.register in ("ground", "free", "centroid")
    if registered and a.align != "none":
        print("ERROR: --align is a whole-set translation of frames that KEEP their in-cell position "
              "(--register keep); ground / free / centroid seat every frame themselves.", file=sys.stderr)
        return 1
    if not a.report and a.register is None and a.align == "none":
        print("ERROR: say where a frame sits — pass --register:\n"
              "  ground    the action stays on the floor (idle, attack, swing, walk in place): every frame\n"
              "            is seated on the reference by its core silhouette, feet on one line\n"
              "  free      it leaves the floor (a jump, a flyer): seated by silhouette in x and y\n"
              "  centroid  an effect: centred by its alpha centroid, never rescaled per frame\n"
              "  keep      motion authored INSIDE the cell must survive: keep each cell's in-cell position\n"
              "On a generated sheet the in-cell position mostly follows the model's grid, not the action "
              "(--report prints incell_x_grid_r2), so `keep` on an in-place action is a character that "
              "jumps sideways on every frame change.", file=sys.stderr)
        return 1
    if registered and not ops():
        print(f"ERROR: --register {a.register} needs numpy and sprite_ops.py beside this script "
              f"({_OPS[1]}) — codex's imagegen venv has numpy.", file=sys.stderr)
        return 1
    pivot = a.pivot or ("center" if a.register == "centroid" else "bottom-center")
    if a.register in ("ground", "free") and pivot != "bottom-center":
        print("ERROR: ground / free stand the reference's feet line on the pivot; --pivot center goes "
              "with --register centroid or keep.", file=sys.stderr)
        return 1
    if a.register == "centroid" and pivot != "center":
        print("ERROR: --register centroid centres every frame; it has no ground line for "
              "--pivot bottom-center.", file=sys.stderr)
        return 1
    if a.pixelate and (a.scale_search or a.subject_px):
        print("ERROR: --pixelate snaps the sheet to a pixel lattice; --scale-search / --subject-px "
              "would resample it off that lattice.", file=sys.stderr)
        return 1
    if a.scale_search and not (0 < a.scale_search[0] <= 1.0 <= a.scale_search[1]):
        print("ERROR: --scale-search LO HI must bracket 1.0, e.g. 0.92 1.08", file=sys.stderr)
        return 1
    if (a.scale_search or a.subject_px or a.foot_margin is not None) and a.register not in ("ground", "free", "centroid"):
        print("ERROR: --scale-search / --subject-px / --foot-margin belong to --register ground | free "
              "(| centroid for --subject-px).", file=sys.stderr)
        return 1

    src = Image.open(a.sheet)
    had_alpha = "A" in src.getbands() and src.getchannel("A").getextrema()[0] < 255
    sheet = src.convert("RGBA")
    if a.bg_color and had_alpha and not a.force_key:
        print(f"ERROR: {a.sheet} already has an alpha channel, so --bg-color {a.bg_color} would key a "
              f"finished matte, not a flat field — an already-keyed sheet re-keyed this way reads "
              f"transparent_pct 0.0, full-cell bboxes and bleed on every cell. Drop --bg-color for "
              f"RGBA input (the sheet is already keyed), or pass --force-key if this alpha is leftover.",
              file=sys.stderr)
        return 1
    if a.bg_color:
        sheet = key_flat_bg(sheet, parse_hex(a.bg_color), a.bg_tol)
    if a.palette:
        sheet = quantise_sheet(sheet, a.palette, a.dither)
    if a.clear_below_thr:
        ach = sheet.getchannel("A")
        tail = sum(ach.histogram()[1:THR + 1])
        sheet.putalpha(ach.point(lambda p: 0 if p <= THR else p))
        print(f"cleared_below_thr {tail} px with alpha 1..{THR} set to 0")

    if a.drop_strays:
        sheet, n = drop_strays(sheet)
        print(f"dropped_strays {n} px with alpha > {THR} not connected to a solid pixel")

    if not a.bg_color and sheet.getchannel("A").getextrema() == (255, 255):
        print("WARN: the sheet is fully opaque — no alpha to measure, so every frame will read as "
              "full-cell content and bleed. Key it first (--bg-color, or remove_chroma_key.py).")

    W, H = sheet.size
    if W < a.cols or H < a.rows:
        print(f"ERROR: {W}x{H} sheet cannot be cut into {a.rows}x{a.cols} cells (cell would be under 1 px)",
              file=sys.stderr)
        return 1
    cw, ch = grid_cell_size(W, H, a.rows, a.cols)

    if a.pixelate:
        f = a.pixelate / max(cw, ch)
        ncw, nch = max(1, round(cw * f)), max(1, round(ch * f))
        sheet = sheet.resize((a.cols * ncw, a.rows * nch), Image.Resampling.NEAREST)
        print(f"pixelated cell {cw}x{ch} -> {ncw}x{nch} NEAREST sheet {W}x{H} -> "
              f"{sheet.width}x{sheet.height} (an exact {a.cols}x{a.rows} grid)")
        cw, ch = grid_cell_size(sheet.width, sheet.height, a.rows, a.cols)
    if a.upscale > 1:
        sheet = sheet.resize((sheet.width * a.upscale, sheet.height * a.upscale), Image.Resampling.NEAREST)
        # re-read the cell from the rects rather than multiplying: on a ragged
        # grid `cw * upscale` and the true upscaled cell differ by a pixel, and
        # this line has to agree with the report header
        cw, ch = grid_cell_size(sheet.width, sheet.height, a.rows, a.cols)
        print(f"upscaled {a.upscale}x NEAREST cell {cw}x{ch}")
    W, H = sheet.size

    nominal = cell_rects(W, H, a.rows, a.cols, a.inset_frac)
    if any(x1 - x0 < 1 or y1 - y0 < 1 for _, _, x0, y0, x1, y1 in nominal):
        print(f"ERROR: --inset-frac {a.inset_frac} leaves an empty cell rect", file=sys.stderr)
        return 1

    # ---- where the cells are cut. The NOMINAL grid stays the origin every in-cell
    # position is measured from; the CUT is where one cell's pixels end and the
    # next one's begin, and the model does not put that on the equal split.
    gutters = a.gutters
    if gutters == "search" and a.inset_frac:
        gutters = "nominal"
        print("gutters nominal (--inset-frac shrinks the equal split, so there is no gutter to search)")
    if gutters == "search" and not ops():
        gutters = "nominal"
        print(f"WARN: --gutters search needs numpy and sprite_ops.py beside this script ({_OPS[1]}); "
              f"cutting on the equal split instead — a subject that crosses it is cut.")
    cuts, unclean = gutter_rects(sheet, a.rows, a.cols) if gutters == "search" else (nominal, 0)
    moved = sum(1 for n, c in zip(nominal, cuts) if n[2:] != c[2:])
    # how far any cut reaches past its nominal cell: every cell is padded by this
    # much, so the nominal origin sits at the same pixel of every sub-image
    pad = [max(0, max(n[2] - c[2] for n, c in zip(nominal, cuts))),
           max(0, max(n[3] - c[3] for n, c in zip(nominal, cuts))),
           max(0, max(c[4] - n[4] for n, c in zip(nominal, cuts))),
           max(0, max(c[5] - n[5] for n, c in zip(nominal, cuts)))]

    # With --inset-frac the measured cell is the inset rect, so re-read the size
    # from these rects — still `cell_rects`, still the largest cell: the metric
    # denominators, the default --canvas, the baseline reference and the paste
    # offset all take it, and a short cell then keeps a transparent edge pixel
    # instead of a taller one being cropped to fit cell 0.
    cell_ws = [x1 - x0 for _, _, x0, _, x1, _ in nominal]
    cell_hs = [y1 - y0 for _, _, _, y0, _, y1 in nominal]
    cw, ch = max(cell_ws), max(cell_hs)
    if min(cell_ws) != cw or min(cell_hs) != ch:
        print(f"WARN: {W}x{H} does not divide evenly into a {a.rows}x{a.cols} grid — cell widths "
              f"{min(cell_ws)}..{cw}, heights {min(cell_hs)}..{ch}. Cells keep their true grid "
              f"boundaries and every frame is written on the largest cell, so a short cell ends "
              f"with a transparent pixel at its right or bottom edge, never a cropped one. A "
              f"width divisible by {a.cols} and a height divisible by {a.rows} avoids it "
              f"(--pixelate N also resizes the sheet to an exact grid).")
    if gutters == "search":
        print(f"gutters search moved_cells {moved} of {len(cuts)} unclean_cuts {unclean} "
              f"cell_pad left {pad[0]} top {pad[1]} right {pad[2]} bottom {pad[3]}")
    padded = any(pad)
    if padded:
        cw, ch = cw + pad[0] + pad[2], ch + pad[1] + pad[3]

    # One subject per cell is the rule for a character, and what lets a neighbour's bleed be told
    # from a cut subject; an effect is many pieces, so there only the bbox is read. ground / free
    # DROP what is not the subject; keep only reports it, so a kept set stays the cells as cut.
    isolating = a.register in ("ground", "free")
    one_subject = a.register != "centroid" and pivot == "bottom-center"
    digits = max(3, len(str(len(cuts) - 1)))
    frames = []
    for i, (nr, cr) in enumerate(zip(nominal, cuts)):
        r, c, x0, y0, x1, y1 = cr
        crop = sheet.crop((x0, y0, x1, y1))
        dropped, foreign = 0, 0
        content_px = alpha_mask(crop).histogram()[255]       # before anything is dropped
        sides = touch_sides(crop)
        subject_sides = sides
        if one_subject and ops():
            # the subject, and whatever reaches in that is not it: a component that touches
            # the cut and is not the subject is a neighbour's bleed, or a speck the key left
            np, so = ops()
            al = np.asarray(crop.getchannel("A"))
            keep, subject_sides, foreign = so.isolate(al, THR)
            if isolating and foreign:
                crop.putalpha(Image.fromarray(np.where(keep, al, 0).astype("uint8"), "L"))
                dropped, foreign, sides = foreign, 0, subject_sides
        if padded:
            sub = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            sub.paste(crop, (pad[0] + x0 - nr[2], pad[1] + y0 - nr[3]))
        else:
            sub = crop
        name = f"{a.names}_{i:0{digits}d}"
        m = dict(index=i, row=r, col=c, name=name, file=f"{name}.png")
        m.update(measure_cell(sub, ch))
        # `touches_edge` is read on the CUT, not on the padded cell: content that reaches
        # its own cut line has no gutter there. At the sheet's outer edge the model drew
        # it off the image; anywhere else two neighbours touch.
        at_edge = [subject_sides[0] and x0 <= 0, subject_sides[1] and y0 <= 0,
                   subject_sides[2] and x1 >= W, subject_sides[3] and y1 >= H]
        m.update(touches_edge=bool(any(sides) and not m["empty"]), cut_rect=[x0, y0, x1, y1],
                 content_px=content_px,
                 cut_sides=[n for n, t in zip(("left", "top", "right", "bottom"), subject_sides) if t],
                 at_sheet_edge=bool(any(at_edge) and not m["empty"]),
                 bleed_dropped_px=dropped, foreign_px=foreign)
        frames.append((m, sub))

    metas = [m for m, _ in frames]
    live = [m for m in metas if not m["empty"]]
    dup = duplicates([(m["name"], im) for m, im in frames if not m["empty"]],
                     a.dup_threshold, a.dup_metric)
    rows, pre_doc, aux = metric_rows(metas, cw, ch, a.dup_threshold, a.dup_metric, dup)

    # ---- report: one `frame` line per cell, then one metric per `metric` line.
    # The metric names are the frames.json keys — `metric_rows` builds both from
    # one table, so they cannot fall out of step.
    print(f"sheet {W}x{H} grid {a.rows}x{a.cols} cell {cw}x{ch} "
          f"inset {a.inset_frac:g} alpha_threshold {THR} dup_metric {a.dup_metric}")
    for m in metas:
        if m["empty"]:
            print(f"frame {m['name']} EMPTY")
            continue
        bb, bb0 = m["bbox"], m["bbox_alpha0"]
        print(f"frame {m['name']} bbox {bb[0]},{bb[1]},{bb[2]},{bb[3]} "
              f"size {m['width']}x{m['height']} "
              f"centroid {m['centroid'][0]:.2f},{m['centroid'][1]:.2f} "
              f"bottom {m['bbox_bottom']} baseline {m['baseline_y']} "
              f"edge {'yes' if m['touches_edge'] else 'no'} "
              f"bbox_alpha0 {bb0[0]},{bb0[1]},{bb0[2]},{bb0[3]} "
              f"alpha0_tail {m['alpha0_tail_px']}")
    for m in metas:
        if m["bleed_dropped_px"]:
            print(f"isolated {m['name']} dropped_bleed_px {m['bleed_dropped_px']} "
                  f"(a neighbour's pixels, or an edge speck, reaching across the cut)")
    for name, value in rows:
        print(f"metric {name} {value}")
    if not registered and aux["x_r2"] is not None and aux["x_r2"] >= GRID_R2 and aux["x_drift_pct"] > 3.0:
        print(f"WARN: in-cell x wanders up to {aux['centroid_x_drift_max_px']:.0f} px "
              f"({aux['x_drift_pct']:.1f}% of the cell) and the grid COLUMN explains "
              f"{aux['x_r2'] * 100:.0f}% of it — that is the model's cell pitch, not motion. Kept as "
              f"it is, the character jumps sideways between frames. If the action stays in place, "
              f"seat the frames by their silhouettes: --register ground (or free).")

    # ---- the hard faults: each has one repair, and none is a matter of taste
    faults = []
    cut_edge = [m["name"] for m in live if m["cut_sides"] and m["at_sheet_edge"]]
    cut_line = [m["name"] for m in live if m["cut_sides"] and not m["at_sheet_edge"]]
    foreign = [m["name"] for m in live if m["foreign_px"]]
    if foreign:
        faults.append(("foreign_pixels", f"{len(foreign)} frame(s) hold pixels that are not their subject and "
                       f"reach the cut ({' '.join(foreign)}): a neighbour's bleed, or a speck a binary key left "
                       f"where the painted field strays from the key (sheet corners do). They steer every "
                       f"bbox this run aligns on. --register ground | free drops them; key_unmix.py does not "
                       f"leave the speck"))
    if cut_edge:
        faults.append(("cut_by_sheet_edge", f"{len(cut_edge)} frame(s) run off the SHEET edge "
                       f"({' '.join(cut_edge)}): the model drew them off the image, and no cut can bring "
                       f"that back — re-generate"))
    if cut_line:
        fix = ("re-run with --gutters search" if gutters == "nominal" and not a.inset_frac else
               "there is no empty gutter between neighbours — re-generate with more space around the subject")
        faults.append(("cut_by_cell_line", f"{len(cut_line)} frame(s) reach their cell's cut line "
                       f"({' '.join(cut_line)}): {fix}"))

    def finish():
        """Print the verdict; 3 when a hard fault stands and --no-gate was not given."""
        for kind, msg in faults:
            print(f"GATE {kind}: {msg}")
        print(f"verdict {'FAIL' if faults else 'OK'} faults {len(faults)}"
              + (" (--no-gate: exit 0 anyway)" if faults and a.no_gate else ""))
        return 3 if faults and not a.no_gate else 0

    # ---- output geometry, needed here because --align is checked against it
    regs, reg_top, pivot_norm = {}, None, ([0.5, 0.0] if pivot == "bottom-center" else [0.5, 0.5])
    if registered:
        np, so = ops()
        live_i = [i for i, (m, _) in enumerate(frames) if not m["empty"]]
        if not live_i:
            print("ERROR: every cell is empty — nothing to register", file=sys.stderr)
            return 1
        if a.ref not in live_i:
            print(f"ERROR: --ref {a.ref} is not a frame with content (0..{len(frames) - 1})", file=sys.stderr)
            return 1
        place, ref_h = {}, None
        if a.register == "centroid":
            # an effect is MEANT to grow and move: one factor for the whole set, never one per frame
            longest = max(max(frames[i][0]["width"], frames[i][0]["height"]) for i in live_i)
            k = (a.subject_px / longest) if a.subject_px else 1.0
            for i in live_i:
                cx, cy = frames[i][0]["centroid"]
                place[i] = (k, -cx * k, -cy * k)
                regs[i] = dict(scale=1.0, dx=0, dy=0, iou=None)
        else:
            alphas = {i: np.asarray(frames[i][1].getchannel("A")) for i in live_i}
            ref_core = so.core(alphas[a.ref])
            ys, xs = np.nonzero(ref_core)
            ref_h, ref_cx, ref_b = int(ys.max() - ys.min() + 1), float(xs.mean()), int(ys.max())
            k = (a.subject_px / ref_h) if a.subject_px else 1.0
            scales = [1.0]
            if a.scale_search:
                scales = [round(float(v), 2) for v in np.arange(a.scale_search[0], a.scale_search[1] + 0.005, 0.01)]
            for i in live_i:
                s, dx, dy, iou = ((1.0, 0, 0, 1.0) if i == a.ref
                                  else so.register(alphas[i], ref_core, a.register, scales))
                # top-left of this frame's cell relative to the anchor: the reference core's
                # centre x and its feet row
                place[i] = (s * k, (dx - ref_cx) * k, (dy - ref_b) * k)
                regs[i] = dict(scale=round(s, 3), dx=int(dx), dy=int(dy), iou=round(float(iou), 3))
        imgs, ext, tail_px = {}, {}, 0
        for i in live_i:
            sc, x, y = place[i]
            im = frames[i][1]
            if abs(sc - 1.0) > 1e-9:
                # Pillow resamples RGBA premultiplied, so a transparent pixel's colour cannot leak
                # in — but the resample ends in an alpha 1-3 ring whose un-premultiplied colour is
                # noise at full saturation. Give that ring its neighbour's colour (or clear it).
                im = im.resize((max(1, round(im.width * sc)), max(1, round(im.height * sc))),
                               Image.Resampling.LANCZOS)
                arr, n = so.clean_tail(np.asarray(im), THR, clear=a.clear_below_thr)
                tail_px += n
                im = Image.fromarray(arr, "RGBA")
            imgs[i] = im
            bb = alpha_bbox(im) or (0, 0, 0, 0)
            ext[i] = (x + bb[0], y + bb[1], x + bb[2], y + bb[3], bb)
        room = 4   # px of clear canvas outside the furthest content
        half_w = math.ceil(max(max(-e[0], e[2]) for e in ext.values())) + room
        if a.register == "centroid":
            margin = 0
            half_h = math.ceil(max(max(-e[1], e[3]) for e in ext.values())) + room
            fit_w, fit_h = 2 * half_w, 2 * half_h
            CW, CH = (a.canvas if a.canvas else [fit_w, fit_h])
            ax, ay = CW / 2.0, CH / 2.0
            pivot_norm = [0.5, 0.5]
        else:
            margin = a.foot_margin if a.foot_margin is not None else max(4, round(0.05 * ref_h * k))
            below = math.ceil(max(e[3] for e in ext.values())) - 1     # content rows under the feet row
            fit_margin = max(margin, below + room)
            fit_w = 2 * half_w
            fit_h = math.ceil(max(-e[1] for e in ext.values())) + room + fit_margin + 1
            if a.canvas:
                CW, CH = a.canvas
            else:
                CW, CH, margin = fit_w, fit_h, fit_margin
            ax, ay = CW / 2.0, float(CH - margin - 1)
            pivot_norm = [0.5, round(margin / CH, 6)]
        offsets, clipped = {}, []
        lattice = a.upscale if a.upscale > 1 else 1      # --upscale F: every frame keeps the reference's F px lattice
        rx0, ry0 = round(ax + place[a.ref][1]), round(ay + place[a.ref][2])
        for i in live_i:
            sc, x, y = place[i]
            px, py = round(ax + x), round(ay + y)
            if lattice > 1:
                px = rx0 + round((px - rx0) / lattice) * lattice
                py = ry0 + round((py - ry0) / lattice) * lattice
            offsets[i] = (px, py)
            bb = ext[i][4]
            loss = (max(0, -(px + bb[0])), max(0, -(py + bb[1])),
                    max(0, px + bb[2] - CW), max(0, py + bb[3] - CH))
            if any(loss):
                clipped.append((frames[i][0]["name"], loss))
        if tail_px:
            print(f"resample_tail {tail_px} px at alpha 1..{THR} "
                  + ("cleared" if a.clear_below_thr else "given their neighbour's colour (alpha kept; "
                     "--clear-below-thr zeroes them)"))
        scale_txt = (f"{a.scale_search[0]:g}..{a.scale_search[1]:g}" if a.scale_search else "off")
        print(f"register {a.register} ref {frames[a.ref][0]['name']} scale_search {scale_txt} "
              f"set_scale {k:.4f} canvas {CW}x{CH}{'' if a.canvas else ' (fitted)'} "
              f"foot_margin {margin} pivot_norm {pivot_norm[0]:g},{pivot_norm[1]:g}")
        for i in live_i:
            g = regs[i]
            iou = "n/a" if g["iou"] is None else f"{g['iou']:.3f}"
            print(f"register frame {frames[i][0]['name']} scale {g['scale']:.2f} dx {g['dx']:+d} dy {g['dy']:+d} "
                  f"iou {iou} at {offsets[i][0]},{offsets[i][1]}")
        if a.register != "centroid":
            dxs = [regs[i]["dx"] for i in live_i]
            dys = [regs[i]["dy"] for i in live_i]
            rx = grid_r2([float(v) for v in dxs], [frames[i][0]["col"] for i in live_i])
            spread_x, spread_y = max(dxs) - min(dxs), max(dys) - min(dys)
            ry = grid_r2([float(v) for v in dys], [frames[i][0]["row"] for i in live_i])
            print(f"register removed dx_spread_px {spread_x} dy_spread_px {spread_y} "
                  f"dx_grid_r2 {'n/a' if rx is None else format(rx, '.3f')} "
                  f"dy_grid_r2 {'n/a' if ry is None else format(ry, '.3f')}")
            for axis, spread, r2v, size, group in (("sideways", spread_x, rx, cw, "column"),
                                                   ("vertical", spread_y, ry, ch, "row")):
                if r2v is not None and r2v < GRID_R2 and spread > 0.03 * size:
                    print(f"WARN: the {axis} offsets this registration removed ({spread} px) do NOT follow "
                          f"the grid (the {group} explains {r2v * 100:.0f}%) — they may be travel authored "
                          f"inside the cell (a lunge, a jump's rise), and it is gone from these frames. "
                          f"Travel belongs on the transform in the engine; if the frames must carry it, "
                          f"slice with --register keep.")
            resized = [frames[i][0]["name"] for i in live_i if abs(regs[i]["scale"] - 1.0) >= 0.03]
            if resized:
                print(f"WARN: --scale-search resized {len(resized)} frame(s) by 3% or more "
                      f"({' '.join(resized)}). A scale search fits a POSE change with a size change — "
                      f"a character rising from a crouch comes out 4-8% smaller while its head has not "
                      f"changed. Keep it for a hold whose frames really differ in size.")
        if clipped:
            for name, loss in clipped:
                print(f"WARN: {name} loses content off the {CW}x{CH} canvas: "
                      f"left {loss[0]} top {loss[1]} right {loss[2]} bottom {loss[3]} px")
            print(f"WARN: {len(clipped)} of {len(live)} frames cropped. --canvas {fit_w} {fit_h} holds every "
                  f"registered frame; omit --canvas and it is fitted for you.")
        shifts = {m["name"]: (0, 0) for m in metas}
        ox = oy = 0
        canvases = []
        for i, (m, _) in enumerate(frames):
            canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
            if i in imgs:
                canvas.paste(imgs[i], offsets[i])
            canvases.append((m, canvas))
        paste_at = {frames[i][0]["name"]: list(offsets[i]) for i in live_i}
        # numbers stay numbers (0 = not applicable): a typed reader — Unity's JsonUtility — maps
        # these fields to float, and a JSON null there is not a value it promises to accept
        reg_top = dict(mode=a.register, ref=a.ref,
                       scale_search=(list(a.scale_search) if a.scale_search else [1.0, 1.0]),
                       subject_px=float(a.subject_px or 0.0), set_scale=round(k, 6), foot_margin_px=margin,
                       anchor_px=[ax, ay], reference_core_height_px=(round(ref_h * k, 2) if ref_h else 0.0))
    else:
        CW, CH = (a.canvas if a.canvas else [cw, ch])
        if CW < cw or CH < ch:
            print(f"WARN: --canvas {CW}x{CH} is smaller than the largest cell {cw}x{ch} — content "
                  f"will be cropped")
        ox = (CW - cw) // 2
        oy = (CH - ch) if pivot == "bottom-center" else (CH - ch) // 2

        # ---- whole-frame alignment (translations only; never scale, never per-cell recentre)
        # The baseline target is snapped to a whole pixel so an integer shift lands on
        # it exactly; a centroid target cannot be, and keeps its <=0.5 px residual.
        tgt_bot = whole(aux["median_bottom"])
        med_cx = aux["median_cx"]
        shifts = {}
        for m in metas:
            sx = sy = 0
            if not m["empty"]:
                if a.align in ("baseline", "both"):
                    sy = round(tgt_bot - m["bbox_bottom"])
                if a.align in ("centroid", "both"):
                    sx = round(med_cx - m["centroid"][0])
            shifts[m["name"]] = (int(sx), int(sy))
        if a.align != "none":
            print(f"align {a.align} target_bottom {tgt_bot:.0f} target_centroid_x {med_cx:.3f}")
            for m in metas:
                sx, sy = shifts[m["name"]]
                print(f"shift {m['name']} {sx:+d} {sy:+d}")
            if a.max_shift is not None:
                over = [(n, s) for n, s in shifts.items() if max(abs(s[0]), abs(s[1])) > a.max_shift]
                if over:
                    for n, s in over:
                        print(f"WARN: {n} needs shift {s} > --max-shift {a.max_shift:g} px", file=sys.stderr)
                    print("REFUSED: a frame that far from the set's median is not repaired by a whole-set "
                          "translation — a bbox bottom or a centroid is steered by whatever sticks out (a bat, "
                          "a trailing foot), so a larger --max-shift only moves the fault. If the action stays "
                          "in place, seat the frames by their silhouettes instead: --register ground (feet on "
                          "one line) or --register free; that path is gated on what it wrote, not on how far it "
                          "moved a frame. Re-generate when that gate fails too, or when the sheet's own "
                          "empty / duplicate / cut findings say so.", file=sys.stderr)
                    return 2

        # `canvas.paste` crops the overhang in silence, so name every frame that
        # would lose content — the shift, or a --canvas smaller than the cell.
        clipped = []
        for m in metas:
            if m["empty"]:
                continue
            sx, sy = shifts[m["name"]]
            x0, y0, x1, y1 = m["bbox"]
            loss = (max(0, -(ox + sx + x0)), max(0, -(oy + sy + y0)),
                    max(0, ox + sx + x1 - CW), max(0, oy + sy + y1 - CH))
            if any(loss):
                clipped.append((m["name"], loss))
        if clipped:
            for name, loss in clipped:
                print(f"WARN: {name} loses content off the {CW}x{CH} canvas: "
                      f"left {loss[0]} top {loss[1]} right {loss[2]} bottom {loss[3]} px")
            worst = [max(loss[i] for _, loss in clipped) for i in range(4)]
            # A wider canvas grows ox both ways. A taller one grows oy upward only
            # under --pivot bottom-center — which is all a baseline shift needs
            # there, since the cell floor IS the canvas floor and no shift can push
            # content below it; --pivot center has to grow both ways.
            fit_w = max(cw, CW + 2 * max(worst[0], worst[2]))
            fit_h = max(ch, CH + (worst[1] if pivot == "bottom-center"
                                  else 2 * max(worst[1], worst[3])))
            print(f"WARN: {len(clipped)} of {len(live)} frames cropped, and the `metric` lines above "
                  f"describe the sheet before the shift. --canvas {fit_w} {fit_h} gives the shift room; "
                  f"the post_align block below measures what would actually be written.")

        # ---- the canvases the run would write, built even under --report so the
        # residual of an --align can be read without producing a file
        canvases = [(m, None) for m in metas]
        for i, (m, sub) in enumerate(frames):
            sx, sy = shifts[m["name"]]
            canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
            canvas.paste(sub, (ox + sx, oy + sy))
            canvases[i] = (m, canvas)
        paste_at = {m["name"]: [ox + shifts[m["name"]][0], oy + shifts[m["name"]][1]] for m in metas}

    lossy = [m["name"] for m in live if m["bleed_dropped_px"] > 0.05 * max(m["content_px"], 1)]
    if lossy:
        faults.append(("dropped_content", f"{len(lossy)} frame(s) lost over 5% of their cell's content as "
                       f"'bleed' ({' '.join(lossy)}): pixels that touched the cut and were not the largest "
                       f"piece. If they were this frame's own (a detached prop, a second figure), the cell "
                       f"has no clean gutter — re-generate with more space, or cut with --register keep and "
                       f"look"))
    if clipped:
        faults.append(("clipped_by_canvas", f"{len(clipped)} frame(s) lose content off the {CW}x{CH} canvas "
                       f"({' '.join(n for n, _ in clipped)}): --canvas {fit_w} {fit_h} holds them"))

    # ---- what the key left on the rim of the frames as written
    rim_doc = {}
    key_hex = a.key_color or a.bg_color
    if key_hex and ops():
        np, so = ops()
        key = so.parse_hex(key_hex)
        bad = tinted = rim = 0
        for m, canvas in canvases:
            if m["empty"]:
                continue
            arr = np.asarray(canvas).astype(np.float32)
            b, t, r = so.rim_stats(arr[..., :3], arr[..., 3], key)
            bad, tinted, rim = bad + b, tinted + t, rim + r
        rim_doc = dict(key_color="#%02x%02x%02x" % key, fringe_pct=round(so.pct(bad, rim), 3),
                       tint_pct=round(so.pct(tinted, rim), 3), rim_px=rim)
        print(f"rim metric key_color {rim_doc['key_color']} rim_px {rim}")
        print(f"rim metric fringe_pct {rim_doc['fringe_pct']:.3f}")
        print(f"rim metric tint_pct {rim_doc['tint_pct']:.3f}")
        if rim_doc["fringe_pct"] > a.fringe_max or rim_doc["tint_pct"] > a.tint_max:
            faults.append(("key_fringe", f"fringe {rim_doc['fringe_pct']:.2f}% (max {a.fringe_max:g}) tint "
                           f"{rim_doc['tint_pct']:.2f}% (max {a.tint_max:g}) of the rim is still key-coloured: "
                           f"a binary key leaves the anti-aliased rim opaque — key the sheet with key_unmix.py "
                           f"and pass the keyed RGBA here with --key-color"))
    elif key_hex:
        print(f"WARN: the rim's fringe was not measured — numpy / sprite_ops.py missing ({_OPS[1]})")

    # ---- are the written frames in register? Measured on the canvases, on the core
    # silhouette, for every mode that has a body to stand on — so a `keep` run prints
    # the same numbers a registered one is gated on.
    seat_doc = {}
    if a.register != "centroid" and pivot == "bottom-center" and ops() and len(live) > 1:
        np, so = ops()
        ref_i = a.ref if not metas[a.ref]["empty"] else next(i for i, m in enumerate(metas) if not m["empty"])
        cores = {i: so.core(np.asarray(c.getchannel("A"))) for i, (m, c) in enumerate(canvases) if not m["empty"]}
        cores = {i: c for i, c in cores.items() if c.any()}
        if ref_i in cores and len(cores) > 1:
            rc = cores[ref_i]
            ys = np.nonzero(rc.any(axis=1))[0]
            ref_core_h = int(ys.max() - ys.min() + 1)
            feet = [so.bottom(c) for c in cores.values()]
            heads = [so.head_x(c) for c in cores.values()]
            ious, slips = [], []
            grounded = a.register != "free"
            for i, c in cores.items():
                if i == ref_i:
                    continue
                u = int((c | rc).sum())
                ious.append(float((c & rc).sum()) / u if u else 0.0)
                sx, sy = so.slip(rc, c, grounded)
                slips.append(max(abs(sx), abs(sy)))
            seat_doc = dict(seat_reference=metas[ref_i]["name"], reference_core_height_px=ref_core_h,
                            feet_drift_px=int(max(feet) - min(feet)), slip_max_px=int(max(slips)),
                            head_x_drift_px=round(max(heads) - min(heads), 1),
                            iou_to_ref_min=round(min(ious), 3), iou_to_ref_mean=round(sum(ious) / len(ious), 3))
            print(f"seat metric reference {seat_doc['seat_reference']} core_height_px {ref_core_h}")
            for kname in ("feet_drift_px", "slip_max_px", "head_x_drift_px", "iou_to_ref_min", "iou_to_ref_mean"):
                print(f"seat metric {kname} {seat_doc[kname]}")
            slip_max = max(3.0, 0.01 * ref_core_h)
            if a.register == "ground" and seat_doc["feet_drift_px"] > a.feet_max:
                faults.append(("feet_line", f"the feet line spreads {seat_doc['feet_drift_px']} px over the "
                               f"written frames (max {a.feet_max:g}): the lowest part of the body is not the "
                               f"feet in some frame — a jump or a fall wants --register free"))
            if a.register in ("ground", "free") and seat_doc["slip_max_px"] > slip_max:
                faults.append(("out_of_register", f"a written frame still sits {seat_doc['slip_max_px']} px "
                               f"from its best overlap with the reference (max {slip_max:.0f})"))
            if not registered and seat_doc["slip_max_px"] > slip_max:
                print(f"WARN: these frames are NOT in register — one sits {seat_doc['slip_max_px']} px from "
                      f"where its silhouette overlaps the reference (a registered set reads 0-2 px), feet "
                      f"line spread {seat_doc['feet_drift_px']} px. That is right only if the action "
                      f"travels inside its cell by design; an in-place action shown like this jumps on "
                      f"every frame change. --register ground | free seats them.")
                if aux["x_r2"] is not None and aux["x_r2"] >= GRID_R2:
                    faults.append(("grid_wander", f"the kept in-cell position moves a frame {seat_doc['slip_max_px']} "
                                   f"px out of register and the grid COLUMN explains {aux['x_r2'] * 100:.0f}% of the "
                                   f"sideways spread: that is where the model put its cells, not motion (authored "
                                   f"travel across a cell reads under 20%). Seat the frames with --register ground "
                                   f"| free; --no-gate if the travel really is authored"))

    # Without numpy there is no silhouette to measure a slip on. The grid test does not need
    # one: wander that follows the column is not motion, whatever measures it.
    if (not registered and not ops() and pivot == "bottom-center" and a.align in ("none", "baseline")
            and aux["x_r2"] is not None and aux["x_r2"] >= GRID_R2 and aux["x_drift_pct"] > 3.0):
        faults.append(("grid_wander", f"the kept in-cell x wanders {aux['centroid_x_drift_max_px']:.0f} px "
                       f"({aux['x_drift_pct']:.1f}% of the cell) and the grid COLUMN explains "
                       f"{aux['x_r2'] * 100:.0f}% of it: where the model put its cells, not motion. Seating "
                       f"frames by silhouette (--register ground | free) needs numpy; --no-gate if the "
                       f"travel really is authored"))

    # With nothing moved and nothing to write, the frames are the cells and a second
    # measuring pass would only cost time — the gate is run over and over.
    if not registered and a.align == "none" and a.report:
        return finish()

    post_metas = []
    for m, canvas in canvases:
        pm = dict(index=m["index"], row=m["row"], col=m["col"], name=m["name"], file=m["file"])
        pm.update(measure_cell(canvas, CH))
        post_metas.append(pm)
    post_dup = duplicates([(pm["name"], c) for pm, (_, c) in zip(post_metas, canvases)
                           if not pm["empty"]], a.dup_threshold, a.dup_metric)
    post_rows, post_doc, post_aux = metric_rows(post_metas, CW, CH, a.dup_threshold,
                                                a.dup_metric, post_dup)

    stage = "post_register" if registered else ("post_align" if a.align != "none" else "as_delivered")
    if registered:
        print(f"post_register frames {len(post_metas)} canvas {CW}x{CH} — re-measured on the frames as "
              f"placed; the `metric` lines above describe the sheet as delivered")
        for name, value in post_rows:
            print(f"post_register metric {name} {value}")
    elif a.align != "none":
        print(f"post_align frames {len(post_metas)} canvas {CW}x{CH} — re-measured after the shifts, "
              f"so these are the numbers the written frames have")
        for name, value in post_rows:
            print(f"post_align metric {name} {value}")
        print(f"align residual baseline_drift_max_px {post_aux['baseline_drift_max_px']:.3f} "
              f"centroid_x_drift_max_px {post_aux['centroid_x_drift_max_px']:.3f} "
              f"target_bottom {tgt_bot:.0f} (integer, so every shift was a whole pixel and the "
              f"baseline residual is 0.000 unless a frame was clipped)")
    post_doc.update(seat_doc)
    post_doc.update(rim_doc)

    if a.report:
        return finish()
    if not a.outdir:
        print("ERROR: need --outdir to write (or use --report)", file=sys.stderr)
        return 1

    lost_px = {name: list(loss) for name, loss in clipped}
    os.makedirs(a.outdir, exist_ok=True)
    out_frames = []
    for i, ((m, canvas), pm) in enumerate(zip(canvases, post_metas)):
        dest = os.path.join(a.outdir, m["file"])
        canvas.save(dest)
        rec = dict(m)
        rec["shift"] = list(shifts[m["name"]])
        rec["canvas_offset"] = paste_at.get(m["name"], [ox, oy])
        rec["clipped_px"] = lost_px.get(m["name"], [0, 0, 0, 0])
        if i in regs:
            rec["register"] = regs[i]
        # what the file on disk measures, beside what its cell measured
        rec["written"] = {k: v for k, v in pm.items()
                          if k not in ("index", "row", "col", "name", "file")}
        out_frames.append(rec)
        print(f"wrote {dest}")

    side = a.json or os.path.join(a.outdir, "frames.json")
    register_doc = reg_top or dict(mode="keep", ref=a.ref)
    doc = dict(
        tool="sheet_to_frames.py", sheet=os.path.abspath(a.sheet),
        rows=a.rows, cols=a.cols, cell=[cw, ch], canvas=[CW, CH], pivot=pivot,
        # where the sprite's pivot goes, as a fraction of the canvas from its bottom-left:
        # the reference's feet line under ground/free, so a foot margin never floats the character
        pivot_norm=pivot_norm,
        fps_hint=a.fps_hint, align=a.align, register=register_doc,
        gutters=gutters, cell_pad=pad, base_offset=[ox, oy], alpha_threshold=THR,
        alpha_cleared_below_thr=bool(a.clear_below_thr), dup_metric=a.dup_metric,
        clipped_count=len(clipped),
        # `set_metrics` describes the frames in this directory; the delivered
        # sheet's own numbers are kept beside it rather than overwritten.
        set_metrics_stage=stage,
        set_metrics=post_doc,
        set_metrics_pre_align=pre_doc,
        verdict=dict(ok=not faults, faults=[dict(kind=kind, detail=msg) for kind, msg in faults]),
        frames=out_frames)
    with open(side, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    print(f"wrote {side}")
    print(f"wrote_frames {len(out_frames)} canvas {CW}x{CH} pivot {pivot} "
          f"fps_hint {a.fps_hint:g} align {a.align} set_metrics_stage {stage} "
          f"register {register_doc['mode']}")
    return finish()

if __name__ == "__main__":
    sys.exit(main())
