#!/usr/bin/env python3
"""slice_grid.py — cut a generated GRID / contact-sheet image into per-asset PNGs.

The most consistent way to get a *set* of assets (UI buttons, pickups, a row of
enemies) is to generate them all in ONE image laid out on a square-ish grid: the
model then enforces a single style, scale, outline weight and lighting across
every cell — zero cross-generation drift. This script does the deterministic
back half: slice the grid into R×C cells, trim each to its opaque content, make
every asset one uniform visual size, and save with your names.

ANIMATION frames do NOT belong here: this script re-centres every cell, so use
`sheet_to_frames.py`, which keeps each cell's internal position and measures the
drift instead.

INPUT should already have a transparent background — key the WHOLE grid first,
e.g. with remove_chroma_key.py from codex's bundled imagegen skill (this skill
ships no keyer; reference/codex-runtime.md section 5 has the full path), then
feed the keyed RGBA image here.
Pick a key colour the art does not contain (magenta `#FF00FF` for most palettes)
and pass `--despill` WITHOUT `--soft-matte`: a soft matte derives alpha from how
far the key's channel dominates, so a subject sharing that channel goes
translucent in its fills — a leaf-green (93,169,106) fill against a #00ff00 key
comes back at alpha 147/255 with `--despill --soft-matte` and 255/255 with
`--despill` alone.

Per cell: crop the cell rectangle → optionally inset to drop gutter/neighbour
bleed → find the alpha content box → (unless --no-normalize) scale the content's
chosen side to content-frac × canvas and center it on a fresh transparent
canvas → save. Row-major order maps to --names.

Examples:
  # key the sheet, then slice a 2x2 into four named, uniformly-sized 512 assets
  remove_chroma_key.py --input grid.png --out grid_keyed.png --key-color '#ff00ff' --despill --force
  slice_grid.py grid_keyed.png --rows 2 --cols 2 --canvas 512 --content-frac 0.72 \
      --names left,right,jump,pause --outdir Assets/Resources/UI
  # inspect alignment / catch bleed before committing (no writes)
  slice_grid.py grid_keyed.png --rows 2 --cols 2 --report

Requires Pillow (use codex's imagegen venv: ~/.codex/imagegen-venv/bin/python).
"""
import argparse, os, statistics
from PIL import Image

THR = 16  # alpha above this counts as content

def alpha_bbox(im):
    a = im.getchannel("A")
    return a.point(lambda p: 255 if p > THR else 0).getbbox()

def cv(xs):
    xs = [x for x in xs if x]
    return 0.0 if len(xs) < 2 else statistics.pstdev(xs) / statistics.mean(xs)

def cell_rects(W, H, rows, cols, inset):
    """Row-major list of (r, c, x0, y0, x1, y1) cell rects, inset inward by frac."""
    rects = []
    for r in range(rows):
        for c in range(cols):
            x0, x1 = round(c * W / cols), round((c + 1) * W / cols)
            y0, y1 = round(r * H / rows), round((r + 1) * H / rows)
            dx, dy = round((x1 - x0) * inset), round((y1 - y0) * inset)
            rects.append((r, c, x0 + dx, y0 + dy, x1 - dx, y1 - dy))
    return rects

def main():
    ap = argparse.ArgumentParser(description="Slice a keyed grid sheet into per-asset PNGs.")
    ap.add_argument("grid", help="keyed (transparent-bg) RGBA grid image")
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--cols", type=int, required=True)
    ap.add_argument("--outdir")
    ap.add_argument("--names", help="comma list, row-major; else cell_r{r}c{c}")
    ap.add_argument("--canvas", type=int, default=512, help="output square canvas px")
    ap.add_argument("--content-frac", type=float, default=0.72,
                    help="content side as fraction of canvas (uniform size)")
    ap.add_argument("--fit", choices=["long", "height", "width"], default="long")
    ap.add_argument("--inset-frac", type=float, default=0.06,
                    help="shrink each cell inward before trimming (drops gutter/bleed)")
    ap.add_argument("--no-normalize", action="store_true",
                    help="just trim+center each cell; keep relative content sizes")
    ap.add_argument("--report", action="store_true", help="measure only; no writes")
    a = ap.parse_args()

    grid = Image.open(a.grid).convert("RGBA")
    W, H = grid.size
    rects = cell_rects(W, H, a.rows, a.cols, a.inset_frac)
    names = a.names.split(",") if a.names else None

    cells = []  # (label, cropped-to-content image, cw, ch)
    warnings = []
    for i, (r, c, x0, y0, x1, y1) in enumerate(rects):
        sub = grid.crop((x0, y0, x1, y1))
        bb = alpha_bbox(sub)
        label = names[i] if names and i < len(names) else f"cell_r{r}c{c}"
        if not bb:
            warnings.append(f"{label}: EMPTY cell (no content)")
            continue
        cw, ch = bb[2] - bb[0], bb[3] - bb[1]
        cw_cell, ch_cell = x1 - x0, y1 - y0
        if bb[0] <= 1 or bb[1] <= 1 or bb[2] >= cw_cell - 1 or bb[3] >= ch_cell - 1:
            warnings.append(f"{label}: content touches cell edge — raise --inset-frac / gutters (possible bleed/clip)")
        cells.append((label, sub.crop(bb), cw, ch))

    for w in warnings:
        print("WARN:", w)

    if a.report or not cells:
        print(f"grid {W}x{H}  {a.rows}x{a.cols}  inset={a.inset_frac}")
        for label, _, cw, ch in cells:
            print(f"  {label:<16} content {cw}x{ch}  long-frac {max(cw,ch)/max(W//a.cols,H//a.rows)*100:5.1f}%")
        longs = [max(cw, ch) for _, _, cw, ch in cells]
        print(f"pre-normalize content long-side CV across cells: {cv(longs)*100:.1f}%")
        if a.report:
            return

    if not a.outdir:
        ap.error("need --outdir to write (or use --report)")
    os.makedirs(a.outdir, exist_ok=True)

    target = round(a.content_frac * a.canvas)
    outs = []
    for label, content, cw, ch in cells:
        if a.no_normalize:
            canvas_px = max(a.canvas, cw, ch)
            out = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
            out.paste(content, ((canvas_px - cw) // 2, (canvas_px - ch) // 2), content)
        else:
            base = ch if a.fit == "height" else cw if a.fit == "width" else max(cw, ch)
            scale = target / base
            nw, nh = max(1, round(cw * scale)), max(1, round(ch * scale))
            content = content.resize((nw, nh), Image.LANCZOS)
            out = Image.new("RGBA", (a.canvas, a.canvas), (0, 0, 0, 0))
            out.paste(content, ((a.canvas - nw) // 2, (a.canvas - nh) // 2), content)
        dest = os.path.join(a.outdir, f"{label}.png")
        out.save(dest)
        outs.append(dest)
        print(f"wrote {dest}")

    # verify uniformity
    def measure(p):
        im = Image.open(p).convert("RGBA"); bb = alpha_bbox(im)
        return max(bb[2] - bb[0], bb[3] - bb[1]) if bb else 0
    print(f"post long-side CV across {len(outs)} assets: {cv([measure(o) for o in outs])*100:.2f}%")

if __name__ == "__main__":
    main()
