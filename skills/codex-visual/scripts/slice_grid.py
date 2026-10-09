#!/usr/bin/env python3
"""slice_grid.py — cut a generated GRID / contact-sheet image into per-asset PNGs.

The most consistent way to get a *set* of assets (UI buttons, pickups, a row of
enemies) is to generate them all in ONE image laid out on a square-ish grid: the
model then enforces a single style, scale, outline weight and lighting across
every cell — zero cross-generation drift. This script does the deterministic
back half: find the gutters, cut the grid into R×C cells, isolate the SUBJECT of
each cell, make every asset one uniform visual size, centre it, and save with
your names.

Position and size are never the model's job. They are decided here, from the
pixels, and the two things that used to go wrong are both handled:

  * A keyed sheet keeps one or two stray pixels at alpha ~20 in a canvas corner
    (a soft matte's leftover). A plain `alpha > 16` bounding box reaches for that
    pixel, so the whole cell is scaled DOWN and its subject pushed to the far
    side — a set asked at 78% of the canvas came back at 58–68%, shifted by up
    to 14% of the canvas, and looked like the model had drawn it off-centre. The
    subject is now the set of pixels at alpha >= --solid-thr grown through every
    connected pixel above --alpha-thr: feathered glows and thin straws stay,
    isolated specks never join, and everything outside the subject is cleared.
    Scale and centre are then read from the subject's CORE (alpha > --core-thr),
    so the outermost haze of a glow does not steer its placement either.
  * Pasting with the image as its own mask onto a transparent canvas SQUARES the
    alpha of every semi-transparent pixel (128 -> 64), thinning every soft rim.
    The paste is now mask-free.

ANIMATION frames do NOT belong here: this script centres every cell on its own
bounding box, so use `sheet_to_frames.py`, which seats frames on one reference by
their silhouette (or keeps their in-cell position) and gates the result.

INPUT should already have a transparent background — key the WHOLE grid first
with `key_unmix.py` (beside this script; reference/codex-runtime.md section 5),
then feed the keyed RGBA image here. A binary key, or remove_chroma_key.py
`--despill` from codex's bundled imagegen skill, leaves the anti-aliased rim
opaque and key-tinted — 5-52% of an asset's rim within 150 RGB of the key once
sliced, against 0.0-0.6% un-mixed — and `audit_set.py --key-color` reads it.
Pick a key colour the art does not contain (magenta `#FF00FF` for most palettes),
and never `--soft-matte`: a soft matte derives alpha from how far the key's
channel dominates, so a subject sharing that channel goes translucent in its
fills — a leaf-green (93,169,106) fill against a #00ff00 key comes back at alpha
147/255 with `--despill --soft-matte` and 255/255 with `--despill` alone.

Per cell: cut on the found gutters (or the nominal grid) → optionally inset →
isolate the subject → (unless --no-normalize) scale the subject's core side to
content-frac × canvas and centre the core on a fresh transparent canvas → save.
Row-major order maps to --names.

Examples:
  # key the sheet, then slice a 2x2 into four named, uniformly-sized 512 assets
  key_unmix.py grid.png --out grid_keyed.png --key-color '#ff00ff'
  slice_grid.py grid_keyed.png --rows 2 --cols 2 --canvas 512 --content-frac 0.72 \
      --names left,right,jump,pause --outdir Assets/Resources/UI
  # inspect alignment / catch bleed before committing (no writes)
  slice_grid.py grid_keyed.png --rows 2 --cols 2 --report
  # plain equal split and plain alpha bbox, to reproduce a set normalised that way
  slice_grid.py grid_keyed.png --rows 2 --cols 2 --gutters nominal --inset-frac 0.06 --raw-bbox ...

Requires Pillow (use codex's imagegen venv: ~/.codex/imagegen-venv/bin/python).
"""
import argparse, os, statistics
from PIL import Image, ImageChops, ImageFilter

THR = 16        # alpha above this counts as content (--alpha-thr)
SOLID_THR = 96  # a pixel this opaque can seed the subject (--solid-thr)
CORE_THR = 40   # the subject's core, which decides scale and centre (--core-thr)


def cv(xs):
    xs = [x for x in xs if x]
    return 0.0 if len(xs) < 2 else statistics.pstdev(xs) / statistics.mean(xs)


# ---------------------------------------------------------------- subject ----
def subject_mask(im, thr=None, solid=None):
    """255 where the pixel belongs to the subject, 0 elsewhere.

    Seeds are the pixels at alpha >= solid; the mask grows 2 px per pass through
    every alpha > thr pixel connected to a seed and stops when nothing joins.
    A speck the keyer left at alpha ~20 has no seed and never joins; a feathered
    glow or a thin straw is connected to one and stays whole. An image with no
    solid pixel at all (a pure haze) falls back to alpha > thr.
    """
    thr = THR if thr is None else thr
    solid = SOLID_THR if solid is None else solid
    a = im.getchannel("A")
    soft = a.point(lambda p: 255 if p > thr else 0)
    seed = a.point(lambda p: 255 if p >= solid else 0)
    if seed.getbbox() is None:
        seed = soft
    cur = ImageChops.multiply(seed, soft)
    for _ in range(4000):
        grown = ImageChops.multiply(cur.filter(ImageFilter.MaxFilter(5)), soft)
        if ImageChops.difference(grown, cur).getbbox() is None:
            break
        cur = grown
    return cur


def extract_subject(im, raw=False):
    """(content RGBA cropped to the subject, core bbox in content coords, stray px cleared).

    raw=True reproduces the old alpha-bbox behaviour: nothing cleared, core = bbox.
    """
    im = im.convert("RGBA")
    a = im.getchannel("A")
    soft = a.point(lambda p: 255 if p > THR else 0)
    if raw:
        bb = soft.getbbox()
        if not bb:
            return None, None, 0
        content = im.crop(bb)
        return content, (0, 0, content.width, content.height), 0
    if a.point(lambda p: 255 if p >= SOLID_THR else 0).getbbox() is None:
        return None, None, soft.histogram()[255]   # haze only, no solid pixel: an EMPTY cell, not a subject
    mask = subject_mask(im)
    full = mask.getbbox()
    strays = soft.histogram()[255] - mask.histogram()[255]
    cleared = im.copy()
    cleared.putalpha(ImageChops.multiply(a, mask))
    core_bb = ImageChops.multiply(mask, a.point(lambda p: 255 if p > CORE_THR else 0)).getbbox() or full
    content = cleared.crop(full)
    core_bb = (core_bb[0] - full[0], core_bb[1] - full[1], core_bb[2] - full[0], core_bb[3] - full[1])
    return content, core_bb, strays


def core_offset(path):
    """(core long side, |centre offset x|, |centre offset y|) of a written asset — what a trimmer sees."""
    im = Image.open(path).convert("RGBA")
    mask = subject_mask(im)
    core = ImageChops.multiply(mask, im.getchannel("A").point(lambda p: 255 if p > CORE_THR else 0)).getbbox() \
        or mask.getbbox()
    if not core:
        return 0, 0.0, 0.0
    return (max(core[2] - core[0], core[3] - core[1]),
            abs((core[0] + core[2]) / 2 - im.width / 2), abs((core[1] + core[3]) / 2 - im.height / 2))


def place(content, core, canvas_w, canvas_h, scale):
    """Scale the content, put the CORE's centre on the canvas centre, paste without a mask."""
    cw, ch = content.size
    nw, nh = max(1, round(cw * scale)), max(1, round(ch * scale))
    content = content.resize((nw, nh), Image.LANCZOS)
    cx0, cy0, cx1, cy1 = (v * scale for v in core)
    x = round(canvas_w / 2 - (cx0 + cx1) / 2)
    y = round(canvas_h / 2 - (cy0 + cy1) / 2)
    out = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    out.paste(content, (x, y))   # no mask: `paste(im, box, im)` squares the alpha of soft pixels
    return out


# ------------------------------------------------------------------- cells ----
def gutter_lines(im, n, axis):
    """n+1 cut positions along `axis` (1 = x, 0 = y): the nominal equal split, each
    interior line moved within ±1/3 of a cell to the row/column with the least
    content. A generated gutter is rarely on the exact equal split."""
    a = im.getchannel("A").point(lambda p: 255 if p > THR else 0)
    W, H = im.size
    L = W if axis == 1 else H
    prof = list((a.resize((W, 1), Image.BOX) if axis == 1 else a.resize((1, H), Image.BOX)).tobytes())
    lines = [0]
    for k in range(1, n):
        nom = round(k * L / n)
        r = round(L / n / 3)
        lo, hi = max(1, nom - r), min(L - 1, nom + r)
        floor = min(prof[lo:hi])
        # the middle of the LONGEST run at the minimum, not its first index — the
        # first empty column is flush against a subject's edge, the middle is the gutter
        best, run_start, best_len = nom, None, -1
        for i in range(lo, hi + 1):
            at_floor = i < hi and prof[i] == floor
            if at_floor and run_start is None:
                run_start = i
            if not at_floor and run_start is not None:
                if i - run_start > best_len:
                    best_len, best = i - run_start, (run_start + i) // 2
                run_start = None
        lines.append(best)
    lines.append(L)
    return lines


def cell_rects(im, rows, cols, inset, gutters):
    """Row-major list of (r, c, x0, y0, x1, y1)."""
    W, H = im.size
    if gutters == "search":
        xs, ys = gutter_lines(im, cols, 1), gutter_lines(im, rows, 0)
    else:
        xs = [round(c * W / cols) for c in range(cols + 1)]
        ys = [round(r * H / rows) for r in range(rows + 1)]
    rects = []
    for r in range(rows):
        for c in range(cols):
            x0, x1, y0, y1 = xs[c], xs[c + 1], ys[r], ys[r + 1]
            dx, dy = round((x1 - x0) * inset), round((y1 - y0) * inset)
            rects.append((r, c, x0 + dx, y0 + dy, x1 - dx, y1 - dy))
    return rects


def main():
    global THR, SOLID_THR, CORE_THR
    ap = argparse.ArgumentParser(description="Slice a keyed grid sheet into per-asset PNGs.")
    ap.add_argument("grid", help="keyed (transparent-bg) RGBA grid image")
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--cols", type=int, required=True)
    ap.add_argument("--outdir")
    ap.add_argument("--names", help="comma list, row-major; else cell_r{r}c{c}")
    ap.add_argument("--canvas", type=int, default=512, help="output canvas px (square unless --canvas-h)")
    ap.add_argument("--canvas-h", type=int, default=0, help="output canvas height for a non-square asset")
    ap.add_argument("--content-frac", type=float, default=0.72,
                    help="subject core side as fraction of canvas (uniform size)")
    ap.add_argument("--fit", choices=["long", "height", "width"], default="long")
    ap.add_argument("--gutters", choices=["search", "nominal"], default="search",
                    help="search (default) = cut where the sheet has the least content near each "
                         "equal split; nominal = the exact equal split")
    ap.add_argument("--inset-frac", type=float, default=0.0,
                    help="shrink each cell inward before isolating (default 0)")
    ap.add_argument("--alpha-thr", type=int, default=THR, help="alpha above this is content (default 16)")
    ap.add_argument("--solid-thr", type=int, default=SOLID_THR,
                    help="alpha at or above this seeds the subject (default 96)")
    ap.add_argument("--core-thr", type=int, default=CORE_THR,
                    help="alpha above this is the subject's core, which sets scale and centre (default 40)")
    ap.add_argument("--raw-bbox", action="store_true",
                    help="plain alpha bbox, no subject isolation, nothing cleared")
    ap.add_argument("--no-normalize", action="store_true",
                    help="just isolate+centre each cell; keep relative content sizes")
    ap.add_argument("--report", action="store_true", help="measure only; no writes")
    a = ap.parse_args()
    THR, SOLID_THR, CORE_THR = a.alpha_thr, a.solid_thr, a.core_thr

    grid = Image.open(a.grid).convert("RGBA")
    W, H = grid.size
    rects = cell_rects(grid, a.rows, a.cols, a.inset_frac, a.gutters)
    names = a.names.split(",") if a.names else None

    cells = []  # (label, content, core, cw, ch, strays)
    warnings = []
    for i, (r, c, x0, y0, x1, y1) in enumerate(rects):
        sub = grid.crop((x0, y0, x1, y1))
        label = names[i] if names and i < len(names) else f"cell_r{r}c{c}"
        content, core, strays = extract_subject(sub, raw=a.raw_bbox)
        if content is None:
            warnings.append(f"{label}: EMPTY cell" + (f" ({strays} px of haze, no solid pixel)" if strays else ""))
            continue
        # where the subject's core sits in the cell: flush against an edge = bleed or clip
        full = subject_mask(sub).getbbox() if not a.raw_bbox else None
        ox, oy = (full[0], full[1]) if full else (0, 0)
        cbb = (core[0] + ox, core[1] + oy, core[2] + ox, core[3] + oy)
        if cbb[0] <= 1 or cbb[1] <= 1 or cbb[2] >= (x1 - x0) - 1 or cbb[3] >= (y1 - y0) - 1:
            warnings.append(f"{label}: subject touches the cell edge — bleed or clip; re-generate with wider gutters")
        if strays:
            warnings.append(f"{label}: {strays} stray px (alpha>{THR}, not connected to a solid pixel) cleared")
        cells.append((label, content, core, core[2] - core[0], core[3] - core[1], strays))

    for w in warnings:
        print("WARN:", w)

    if a.report or not cells:
        print(f"grid {W}x{H}  {a.rows}x{a.cols}  gutters={a.gutters} inset={a.inset_frac} "
              f"alpha_thr={THR} solid_thr={SOLID_THR} core_thr={CORE_THR}")
        for label, _, _, cw, ch, strays in cells:
            print(f"  {label:<16} core {cw}x{ch}  long-frac "
                  f"{max(cw, ch) / max(W // a.cols, H // a.rows) * 100:5.1f}%  strays {strays}")
        longs = [max(cw, ch) for _, _, _, cw, ch, _ in cells]
        print(f"pre-normalize core long-side CV across cells: {cv(longs) * 100:.1f}%")
        if a.report:
            return

    if not a.outdir:
        ap.error("need --outdir to write (or use --report)")
    os.makedirs(a.outdir, exist_ok=True)

    canvas_w, canvas_h = a.canvas, a.canvas_h or a.canvas
    target = round(a.content_frac * (canvas_h if a.fit == "height" else canvas_w))
    outs = []
    for label, content, core, cw, ch, _ in cells:
        if a.no_normalize:
            scale, cw_i, ch_i = 1.0, max(canvas_w, content.width), max(canvas_h, content.height)
        else:
            base = ch if a.fit == "height" else cw if a.fit == "width" else max(cw, ch)
            scale, cw_i, ch_i = target / max(1, base), canvas_w, canvas_h
        out = place(content, core, cw_i, ch_i, scale)
        dest = os.path.join(a.outdir, f"{label}.png")
        out.save(dest)
        outs.append(dest)
        long_side, ox, oy = core_offset(dest)
        print(f"wrote {dest}  core {long_side}px  centre off ({ox:.1f},{oy:.1f})px")

    ms = [core_offset(o) for o in outs]
    print(f"post-normalize core long-side CV across {len(outs)} assets: {cv([m[0] for m in ms]) * 100:.2f}%  "
          f"max centre offset {max(max(m[1], m[2]) for m in ms):.1f}px")


if __name__ == "__main__":
    main()
