#!/usr/bin/env python3
"""sheet_to_frames.py — cut an ANIMATION sheet into equal frames, keeping each cell's internal position.

This is the opposite of `slice_grid.py`. That script trims every cell to its
content and re-centres it, which is right for an icon set and **destroys an
animation**: in a sheet of frames the motion arc *is* the cell-to-cell offset,
so per-cell re-centring flattens a jump into sixteen identical hops and pins a
walk cycle's feet to one spot. Nothing here ever re-centres or rescales a single
frame. The only correction on offer is a **whole-set translation** (`--align`),
and it is off by default.

Per sheet: (optionally key a flat background, quantise to one shared palette,
pixelate) → slice rows × cols → **measure** every frame → optionally shift whole
frames so the set shares a ground line → write equal-size canvases plus a
`frames.json` sidecar that `frames_to_anim.py` and the Unity clip builder read.

INPUT is either RGBA that is already keyed, or RGB plus `--bg-color` for a hard
distance key done here. Key a colour the art does not contain: with
`remove_chroma_key.py --soft-matte`, alpha comes from how far the key's channel
dominates the other two, so a subject that shares that channel goes translucent
in its fills — a leaf-green (93,169,106) fill against a #00ff00 key comes back at
alpha 147/255 under `--despill --soft-matte` and 255/255 under `--despill` alone.
Magenta `#FF00FF` is the safer key for most palettes, and for GIF-bound frames the
hard binary key here is usually right anyway. `--bg-color` on an input that
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
`bleed_cells` (content is clipped by the cell) → `baseline_drift_max_px` (the
character bobs off the floor) → `centroid_x_drift_max_px` (it slides sideways).
The first three mean re-generate; the last two are what `--align` can repair.

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
  sheet_to_frames.py sheet_keyed.png --rows 4 --cols 4 --report

  # key a magenta sheet here, then write 16 equal 512x512 frames + frames.json
  sheet_to_frames.py sheet.png --rows 4 --cols 4 --bg-color '#ff00ff' \
      --outdir out/idle --names idle --canvas 512 512 --pivot bottom-center --fps-hint 10

  # the frames share a pose but bob: pin them to the median ground line, on a
  # canvas with room for the shift (cell 128 + 4 px of headroom here)
  sheet_to_frames.py sheet_keyed.png --rows 4 --cols 4 --align baseline --max-shift 24 \
      --canvas 128 132 --outdir out/idle

  # pixel-art post-process: one palette for the whole sheet, then 64px cells at 4x
  sheet_to_frames.py sheet_keyed.png --rows 5 --cols 6 --palette 24 --pixelate 64 --upscale 4 --outdir out/morph

  # the strict duplicate test, and no sub-threshold tail left for a trimmer
  sheet_to_frames.py sheet_keyed.png --rows 5 --cols 6 --dup-metric pixel --dup-threshold 22 \
      --alpha-thr 16 --clear-below-thr --report

Exit codes: 0 ok · 1 rows × cols cells cannot be formed, bad args, a missing
`--outdir`, or `--bg-color` on an input that already carries alpha (see
`--force-key`) · 2 `--align` needed a shift larger than `--max-shift` (nothing
written).

Requires Pillow (use codex's imagegen venv: ~/.codex/imagegen-venv/bin/python).
"""
import argparse
import json
import os
import statistics
import sys

from PIL import Image, ImageChops

THR = 16  # alpha above this counts as content; --alpha-thr overrides it in main()


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

    Keyed pixels keep the chroma colour in their RGB — only alpha changes. That
    is invisible in a PNG and in every preview format here, and it bleeds a
    fringe of the key colour the moment an engine filters or mip-maps the
    texture. Unity's importer setting **Alpha Is Transparency** repairs it on
    import (`unity-2d-sprites`); `remove_chroma_key.py --despill` repairs it in
    the file — with `--despill` alone, never `--soft-matte` (see the module
    docstring: a soft matte eats a subject that shares the key's channel).
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
               baseline_drift_max_px=b_max, centroid_x_drift_max_px=dx_max)
    return ([(n, p) for n, p, _ in rows], {n: j for n, _, j in rows}, aux)


def main():
    ap = argparse.ArgumentParser(
        description="Slice an animation sheet into equal frames, keeping each cell's internal position.")
    ap.add_argument("sheet", help="animation sheet: RGBA already keyed, or RGB + --bg-color")
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--cols", type=int, required=True)
    ap.add_argument("--bg-color", help="flat background to key out here, e.g. '#ff00ff' (hard/binary key). "
                                       "Refused on an input that already carries alpha — see --force-key")
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
    ap.add_argument("--inset-frac", type=float, default=0.0,
                    help="shrink each cell inward before measuring (default 0 — animation cells have no gutters)")
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
    ap.add_argument("--pivot", choices=["bottom-center", "center"], default="bottom-center",
                    help="where the cell sits on a larger canvas, and what is recorded in frames.json. "
                         "bottom-center stands the cell on the canvas floor, so extra canvas height "
                         "becomes headroom above it — which is what an --align shift needs")
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

    rects = cell_rects(W, H, a.rows, a.cols, a.inset_frac)
    if any(x1 - x0 < 1 or y1 - y0 < 1 for _, _, x0, y0, x1, y1 in rects):
        print(f"ERROR: --inset-frac {a.inset_frac} leaves an empty cell rect", file=sys.stderr)
        return 1

    # With --inset-frac the measured cell is the inset rect, so re-read the size
    # from these rects — still `cell_rects`, still the largest cell: the metric
    # denominators, the default --canvas, the baseline reference and the paste
    # offset all take it, and a short cell then keeps a transparent edge pixel
    # instead of a taller one being cropped to fit cell 0.
    cell_ws = [x1 - x0 for _, _, x0, _, x1, _ in rects]
    cell_hs = [y1 - y0 for _, _, _, y0, _, y1 in rects]
    cw, ch = max(cell_ws), max(cell_hs)
    if min(cell_ws) != cw or min(cell_hs) != ch:
        print(f"WARN: {W}x{H} does not divide evenly into a {a.rows}x{a.cols} grid — cell widths "
              f"{min(cell_ws)}..{cw}, heights {min(cell_hs)}..{ch}. Cells keep their true grid "
              f"boundaries and every frame is written on the largest cell, so a short cell ends "
              f"with a transparent pixel at its right or bottom edge, never a cropped one. A "
              f"width divisible by {a.cols} and a height divisible by {a.rows} avoids it "
              f"(--pixelate N also resizes the sheet to an exact grid).")

    pad = max(3, len(str(len(rects) - 1)))
    frames = []
    for i, (r, c, x0, y0, x1, y1) in enumerate(rects):
        sub = sheet.crop((x0, y0, x1, y1))
        name = f"{a.names}_{i:0{pad}d}"
        m = dict(index=i, row=r, col=c, name=name, file=f"{name}.png")
        m.update(measure_cell(sub, ch))
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
    for name, value in rows:
        print(f"metric {name} {value}")

    # ---- output geometry, needed here because --align is checked against it
    CW, CH = (a.canvas if a.canvas else [cw, ch])
    if CW < cw or CH < ch:
        print(f"WARN: --canvas {CW}x{CH} is smaller than the largest cell {cw}x{ch} — content "
              f"will be cropped")
    ox = (CW - cw) // 2
    oy = (CH - ch) if a.pivot == "bottom-center" else (CH - ch) // 2

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
                print("REFUSED: a frame that far out of register is a broken sheet, not a misaligned one — "
                      "re-generate it; do not translate it into place.", file=sys.stderr)
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
        need_w = max(cw, CW + 2 * max(worst[0], worst[2]))
        need_h = max(ch, CH + (worst[1] if a.pivot == "bottom-center"
                               else 2 * max(worst[1], worst[3])))
        print(f"WARN: {len(clipped)} of {len(live)} frames cropped, and the `metric` lines above "
              f"describe the sheet before the shift. --canvas {need_w} {need_h} gives the shift room; "
              f"the post_align block below measures what would actually be written.")

    # ---- the canvases the run would write, built even under --report so the
    # residual of an --align can be read without producing a file
    canvases = [(m, None) for m in metas]
    for i, (m, sub) in enumerate(frames):
        sx, sy = shifts[m["name"]]
        canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        canvas.paste(sub, (ox + sx, oy + sy))
        canvases[i] = (m, canvas)

    # With no --align and nothing to write, the frames are the cells and a second
    # measuring pass would only cost time — the gate is run over and over.
    if a.align == "none" and a.report:
        return 0

    post_metas = []
    for m, canvas in canvases:
        pm = dict(index=m["index"], row=m["row"], col=m["col"], name=m["name"], file=m["file"])
        pm.update(measure_cell(canvas, CH))
        post_metas.append(pm)
    post_dup = duplicates([(pm["name"], c) for pm, (_, c) in zip(post_metas, canvases)
                           if not pm["empty"]], a.dup_threshold, a.dup_metric)
    post_rows, post_doc, post_aux = metric_rows(post_metas, CW, CH, a.dup_threshold,
                                                a.dup_metric, post_dup)

    if a.align != "none":
        print(f"post_align frames {len(post_metas)} canvas {CW}x{CH} — re-measured after the shifts, "
              f"so these are the numbers the written frames have")
        for name, value in post_rows:
            print(f"post_align metric {name} {value}")
        print(f"align residual baseline_drift_max_px {post_aux['baseline_drift_max_px']:.3f} "
              f"centroid_x_drift_max_px {post_aux['centroid_x_drift_max_px']:.3f} "
              f"target_bottom {tgt_bot:.0f} (integer, so every shift was a whole pixel and the "
              f"baseline residual is 0.000 unless a frame was clipped)")

    if a.report:
        return 0
    if not a.outdir:
        print("ERROR: need --outdir to write (or use --report)", file=sys.stderr)
        return 1

    lost_px = {name: list(loss) for name, loss in clipped}
    os.makedirs(a.outdir, exist_ok=True)
    out_frames = []
    for (m, canvas), pm in zip(canvases, post_metas):
        dest = os.path.join(a.outdir, m["file"])
        canvas.save(dest)
        rec = dict(m)
        rec["shift"] = list(shifts[m["name"]])
        rec["canvas_offset"] = [ox + shifts[m["name"]][0], oy + shifts[m["name"]][1]]
        rec["clipped_px"] = lost_px.get(m["name"], [0, 0, 0, 0])
        # what the file on disk measures, beside what its cell measured
        rec["written"] = {k: v for k, v in pm.items()
                          if k not in ("index", "row", "col", "name", "file")}
        out_frames.append(rec)
        print(f"wrote {dest}")

    side = a.json or os.path.join(a.outdir, "frames.json")
    doc = dict(
        tool="sheet_to_frames.py", sheet=os.path.abspath(a.sheet),
        rows=a.rows, cols=a.cols, cell=[cw, ch], canvas=[CW, CH], pivot=a.pivot,
        fps_hint=a.fps_hint, align=a.align, base_offset=[ox, oy], alpha_threshold=THR,
        alpha_cleared_below_thr=bool(a.clear_below_thr), dup_metric=a.dup_metric,
        clipped_count=len(clipped),
        # `set_metrics` describes the frames in this directory; the delivered
        # sheet's own numbers are kept beside it rather than overwritten.
        set_metrics_stage=("post_align" if a.align != "none" else "as_delivered"),
        set_metrics=post_doc,
        set_metrics_pre_align=pre_doc,
        frames=out_frames)
    with open(side, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    print(f"wrote {side}")
    print(f"wrote_frames {len(out_frames)} canvas {CW}x{CH} pivot {a.pivot} "
          f"fps_hint {a.fps_hint:g} align {a.align} "
          f"set_metrics_stage {'post_align' if a.align != 'none' else 'as_delivered'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
