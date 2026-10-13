#!/usr/bin/env python3
"""pixel_snap.py — snap a finished static image, or a set of them, onto a pixel lattice.

A generated "pixel art" icon is drawn in blocks of several source pixels, uneven
and anti-aliased, and `slice_grid.py` / `normalize_set.py` then rescale it by a
fraction, so what sits on the final canvas has no lattice at all. This is the
last step of the static path: it reads each finished RGBA image, fits a lattice
of a FIXED number of cells to the image's own colour edges, takes one colour per
cell, puts the whole set on one palette and writes every cell as an F x F block.

Run it on images that already sit on their final canvas (after `slice_grid.py` /
`normalize_set.py`), never before: their rescale would resample any lattice made
earlier. The output canvas is cells x --upscale, so choose the two to multiply
to the canvas the engine expects (64 cells x 4 = 256 px).

Per image: fit the cut lines (`pixel_ops.fit_cells`; each cut may move onto the
nearest edge unless --snap-warp off) -> one colour per cell, the centre sample
unless it is an isolated impulse, alpha made binary -> the set's palette -> an
integer NEAREST upscale -> write -> re-measure the written file.

The cell count is the caller's, from the art bible's Pixel spec. --cells N is
the count along the image's LONG side; the short side gets round(N * short /
long). Two aids for choosing it, neither of which decides anything:

  native_block_px  the commonest gap between neighbouring colour edges in the
                   source, px. `implied_cells` is the long side over it.
  --sweep LO HI    edge_fit and unit_gaps of every cell count whose spacing is
                   LO..HI px. The count the image was drawn at is where the
                   smaller of the two peaks; a fraction of it reads a high
                   edge_fit and a low unit_gaps.

Lines printed
  snap   per input: source size, cells, lattice (warped = cuts moved onto edges,
         fitted = one phase for the whole image, uniform = the equal split),
         edge_fit and unit_gaps of the unwarped fit (0-1; how much of a lattice
         the source really carries at this count), native_block_px,
         implied_cells, colours before the palette.
  set    palette source (none | built | file), colours, metric, and the furthest
         any colour moved.
  wrote  per output: canvas, block and phase read back off the file, uniform
         (share of F x F tiles that are one colour), alpha_partial_px, colours.
  verdict OK | FAIL

Gates, read back from the written files: the canvas is cells x F; the block
and its phase are both multiples of F (flat art whose neighbouring cells share
a colour reads 2F or more, which is still on the F lattice); uniform is 100%; no pixel has
an alpha other than 0 or 255; something is left visible (a subject whose every
cell is under half opaque is cleared by binary alpha); with a palette, the
opaque colours of the whole set are at most its size.

One palette for the set: --palette K builds at most K colours from every
snapped image together; --palette-file takes them from a file (.md: the hexes
under the `Palette` heading, .hex / .txt: one per line, .png: its colours);
both together keep the K file colours the set uses most. --key-color drops the
chroma key from a palette file that lists it. --palette-out writes the palette
used, so the next set can be given the same one.

Snapping moves a subject by up to half a block, so gate the result with
`audit_set.py --off-max` at half the block or more.

Examples
  # which cell count? measure, write nothing
  pixel_snap.py Icons/satchel.png --sweep 3 12
  pixel_snap.py Icons/*.png --cells 64 --report
  # a courier's three pickup icons: 64 cells at 4x on one 16-colour palette
  pixel_snap.py Icons/satchel.png Icons/crate.png Icons/token.png --cells 64 --upscale 4 \
      --palette 16 --palette-out Icons/pickups.hex --outdir Assets/Art/Pickups
  # the same lattice on the art bible's palette
  pixel_snap.py Icons/*.png --cells 64 --upscale 4 --palette-file ART_DIRECTION.md \
      --key-color '#ff00ff' --outdir Assets/Art/Pickups
  # a 3:2 lane banner at an explicit count
  pixel_snap.py lane_banner.png --cells-wh 96 64 --upscale 2

Exit codes
  0  every output passes (or --report / --sweep: measured, nothing written)
  1  bad arguments, an unreadable or opaque input, a cell count larger than the
     source, an unusable palette file (and --report with a failing measure)
  3  files written, the read-back failed a gate (--no-gate turns this into 0)

Requires Pillow and numpy (codex's imagegen venv has both: ~/.codex/imagegen-venv/bin/python),
and `pixel_ops.py` beside this script.
"""
import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import numpy as np
    import pixel_ops as po
except ImportError as e:
    print(f"ERROR: pixel_snap.py needs numpy and pixel_ops.py beside this script ({e})", file=sys.stderr)
    sys.exit(1)


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_hex(s):
    s = s.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"not a hex colour: {s!r}")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def load(path):
    """float HxWx4 of a keyed image; exits on an unreadable, opaque or empty one."""
    try:
        im = Image.open(path).convert("RGBA")
    except (OSError, ValueError) as e:
        die(f"{path}: cannot read ({e})")
    lo, hi = im.getchannel("A").getextrema()
    if lo == 255:
        die(f"{path}: opaque — there is no alpha to measure. Key it first (key_unmix.py), then snap.")
    if hi == 0:
        die(f"{path}: fully transparent — nothing to snap")
    return po.to_float(im)


def cell_counts(w, h, cells, cells_wh):
    """(nx, ny): --cells-wh as given, else N on the long side and its share on the short one."""
    if cells_wh:
        return cells_wh[0], cells_wh[1]
    if w >= h:
        return cells, max(1, round(cells * h / w))
    return max(1, round(cells * w / h)), cells


def colour_codes(u8):
    """One integer per visible pixel: its RGB packed as 0xRRGGBB."""
    rgb = u8[u8[..., 3] > 0, :3].astype(np.uint32)
    return (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]


def most_used(palette, images, count, metric):
    """The `count` palette entries that cover the most pixels of the set, in palette order."""
    codes = (palette[:, 0].astype(np.uint32) << 16) | (palette[:, 1].astype(np.uint32) << 8) | palette[:, 2]
    hits = np.zeros(len(palette), np.int64)
    for u8 in images:
        mapped, _ = po.apply_palette(u8, palette, metric)
        found, n = np.unique(colour_codes(mapped), return_counts=True)
        for code, k in zip(found, n):
            hits[np.flatnonzero(codes == code)[0]] += int(k)
    keep = sorted(np.argsort(-hits, kind="stable")[:count])
    return palette[keep]


def read_back(u8, factor, want):
    """What a written image measures as, and the gates it fails."""
    h, w = u8.shape[:2]
    found = po.integer_block(u8)
    stats = po.block_stats(u8, factor, (0, 0))
    alpha = u8[..., 3]
    partial = int(((alpha > 0) & (alpha < 255)).sum())
    codes = np.unique(colour_codes(u8))
    flags = []
    if (w, h) != want or w % factor or h % factor:
        flags.append("canvas")
    if found is not None and (found[0] % factor or found[1] % factor or found[2] % factor or found[3] % factor):
        flags.append("block")
    if stats["blocks"] and stats["uniform_pct"] < 100.0:
        flags.append("mixed blocks")
    if partial:
        flags.append("partial alpha")
    if not (alpha == 255).any():
        flags.append("empty")    # the input had content (load checks); binary alpha cleared all of it
    return dict(w=w, h=h, block=found, uniform=stats["uniform_pct"], partial=partial, codes=codes), flags


def main():
    ap = argparse.ArgumentParser(description="Snap finished static images onto a pixel lattice: a fixed cell "
                                             "count, one colour per cell, one palette for the set.")
    ap.add_argument("inputs", nargs="+", help="keyed RGBA images on their final canvas")
    ap.add_argument("--cells", type=int, metavar="N",
                    help="cell count along each image's LONG side; the short side gets round(N * short / long)")
    ap.add_argument("--cells-wh", type=int, nargs=2, metavar=("NX", "NY"), help="explicit cell counts per axis")
    ap.add_argument("--upscale", type=int, default=1, metavar="F",
                    help="write every cell as an F x F block, integer NEAREST (default 1)")
    ap.add_argument("--snap-warp", choices=["on", "off"], default="on",
                    help="on (default) = each cut may move onto the nearest colour edge; off = one phase per "
                         "image, or the equal split when the source carries too little of a lattice")
    ap.add_argument("--palette", type=int, metavar="K",
                    help="at most K colours for the whole set, built from every snapped image together; with "
                         "--palette-file, keep the K file colours the set uses most")
    ap.add_argument("--palette-file", metavar="PATH",
                    help="a fixed palette: .md (hexes under the --palette-section heading), .hex / .txt (one per "
                         "line) or .png (its colours)")
    ap.add_argument("--palette-section", default="Palette", metavar="NAME",
                    help="heading a .md palette is read from (default Palette)")
    ap.add_argument("--palette-out", metavar="PATH", help="write the palette used as a .hex file")
    ap.add_argument("--colour-metric", choices=po.METRICS, default="lab",
                    help="how colour distance is measured: lab (CIEDE2000, default) or rgb")
    ap.add_argument("--key-color", metavar="HEX",
                    help="the key colour the art was generated on, e.g. '#ff00ff': never taken from a palette file")
    ap.add_argument("--outdir", help="write here; else beside each input")
    ap.add_argument("--suffix", default="_px", help="append to the basename (default _px)")
    ap.add_argument("--in-place", action="store_true", help="overwrite the inputs (no suffix)")
    ap.add_argument("--report", action="store_true", help="measure and print; no writes")
    ap.add_argument("--sweep", type=float, nargs=2, metavar=("LO", "HI"),
                    help="print edge_fit / unit_gaps for every cell count whose spacing is LO..HI source px, "
                         "and native_block_px; no writes")
    ap.add_argument("--no-gate", action="store_true", help="exit 0 even when the read-back fails")
    a = ap.parse_args()

    if a.sweep:
        if not 0 < a.sweep[0] <= a.sweep[1]:
            die("--sweep needs 0 < LO <= HI (cell spacing in source px)")
        for p in a.inputs:
            rgba = load(p)
            h, w = rgba.shape[:2]
            bx, by = po.block_estimate(rgba)
            rows = po.sweep_counts(rgba, a.sweep[0], a.sweep[1])
            print(f"sweep {os.path.basename(p)} source {w}x{h} native_block_px {bx:.2f}x{by:.2f}")
            print(f"  {'cells_x':>7s} {'spacing':>8s} {'edge_fit':>8s} {'unit_gaps':>9s} {'evidence':>8s}")
            for n, ef, ug in rows:
                print(f"  {n:>7d} {w / n:>8.2f} {ef:>8.3f} {ug:>9.3f} {min(ef, ug):>8.3f}")
            if rows:
                best = max(rows, key=lambda r: min(r[1], r[2]))
                print(f"  best cells_x {best[0]} evidence {min(best[1], best[2]):.3f}")
            else:
                print("  no cell count has a spacing in that range")
        return

    if (a.cells is None) == (a.cells_wh is None):
        die("need exactly one of --cells N or --cells-wh NX NY (or --sweep LO HI)")
    if min(a.cells_wh or [a.cells]) < 1:
        die("a cell count must be at least 1")
    if a.upscale < 1:
        die("--upscale must be >= 1")
    if a.palette is not None and a.palette < 1:
        die("--palette must be >= 1")
    if a.palette_out and a.palette is None and not a.palette_file:
        die("--palette-out needs a palette: --palette K or --palette-file PATH")
    if a.in_place and a.outdir:
        die("--in-place writes over the inputs; drop --outdir")
    try:
        key = parse_hex(a.key_color) if a.key_color else None
    except ValueError as e:
        die(f"--key-color: {e}")

    def dest_for(p):
        if a.in_place:
            return p
        stem = os.path.splitext(os.path.basename(p))[0] + a.suffix + ".png"
        return os.path.join(a.outdir if a.outdir else os.path.dirname(p), stem)

    dests = [dest_for(p) for p in a.inputs]
    if not a.report:
        real = [os.path.abspath(d) for d in dests]
        if len(set(real)) != len(real):
            die("two inputs would be written to one file; rename them or snap them separately")
        if not a.in_place and set(real) & {os.path.abspath(p) for p in a.inputs}:
            die("an output would overwrite an input; keep a --suffix, use --outdir, or say --in-place")

    palette, source = None, "none"
    if a.palette_file:
        try:
            palette, _ = po.read_palette(a.palette_file, section=a.palette_section, exclude=[key] if key else ())
        except (ValueError, OSError) as e:
            die(f"palette: {e}")
        source = f"file {a.palette_file}"
        if key:
            print("key #%02x%02x%02x excluded from the palette file" % key)

    # ---- fit and recover every image before any palette is chosen ----
    snapped = []   # (path, cells uint8 (ny, nx, 4))
    for p in a.inputs:
        rgba = load(p)
        h, w = rgba.shape[:2]
        nx, ny = cell_counts(w, h, a.cells, a.cells_wh)
        if nx > w or ny > h:
            die(f"{p}: {nx}x{ny} cells is more than the source's {w}x{h} px — a cell needs at least one pixel")
        try:
            fit = po.fit_cells(rgba, nx, ny, warp=a.snap_warp == "on")
            cells, _, _ = po.recover_cells(rgba, fit["x_lines"], fit["y_lines"], method="robust", alpha="binary")
        except ValueError as e:
            die(f"{p}: {e}")
        u8 = po.to_u8(cells)
        bx, by = po.block_estimate(rgba)
        native = bx if w >= h else by
        implied = str(round(max(w, h) / native)) if native else "-"
        print(f"snap {os.path.basename(p)} source {w}x{h} cells {nx}x{ny} lattice {fit['lattice']} "
              f"edge_fit {fit['edge_fit']:.3f} unit_gaps {fit['unit_gaps']:.3f} "
              f"native_block_px {bx:.2f}x{by:.2f} implied_cells {implied} colours {len(np.unique(colour_codes(u8)))}")
        snapped.append((p, u8))

    # ---- one palette for the set ----
    if palette is not None and a.palette is not None and len(palette) > a.palette:
        listed = len(palette)
        palette = most_used(palette, [u8 for _, u8 in snapped], a.palette, a.colour_metric)
        source += f" (the {len(palette)} most used of {listed})"
    elif palette is None and a.palette is not None:
        palette = po.build_palette([u8 for _, u8 in snapped], a.palette, a.colour_metric)
        source = "built"
        if not len(palette):     # binary alpha left nothing visible: there is no colour to build from
            palette, source = None, "none"
            if a.palette_out:
                die("--palette-out: no image kept a visible cell, so there is no palette to write")
    moved = 0.0
    if palette is not None:
        for i, (p, u8) in enumerate(snapped):
            u8, stats = po.apply_palette(u8, palette, a.colour_metric)
            moved = max(moved, stats["max_distance"])
            snapped[i] = (p, u8)
    line = f"set files {len(snapped)} palette {source}"
    if palette is not None:
        line += f" colours {len(palette)} metric {a.colour_metric} max_distance {moved:.2f}"
    print(line)

    # ---- upscale, write, read back ----
    if not a.report:
        if a.outdir:
            os.makedirs(a.outdir, exist_ok=True)
        if a.palette_out:
            try:
                po.write_palette(a.palette_out, palette)
            except OSError as e:
                die(f"--palette-out: {e}")
            print(f"wrote {a.palette_out} colours {len(palette)}")
    failed, used = 0, []
    for (p, u8), dest in zip(snapped, dests):
        ny, nx = u8.shape[:2]
        out = np.repeat(np.repeat(u8, a.upscale, axis=0), a.upscale, axis=1)
        if not a.report:
            Image.fromarray(out).save(dest)
            out = np.asarray(Image.open(dest).convert("RGBA"))   # the gate reads the file, not the array
        m, flags = read_back(out, a.upscale, (nx * a.upscale, ny * a.upscale))
        used.append(m["codes"])
        block = "%dx%d phase %d,%d" % m["block"] if m["block"] else "- phase -"
        line = (f"{'would write' if a.report else 'wrote'} {dest} canvas {m['w']}x{m['h']} block {block} "
                f"uniform {m['uniform']:.2f} alpha_partial_px {m['partial']} colours {len(m['codes'])}")
        if flags:
            failed += 1
            line += "  ← " + ", ".join(flags)
        print(line)
    total = len(np.unique(np.concatenate(used)))
    over = palette is not None and total > len(palette)
    print(f"set colours {total}" + (f" palette {len(palette)}" if palette is not None else "")
          + ("  ← more colours than the palette" if over else ""))
    if failed or over:
        print(f"verdict FAIL files failed {failed}" + (" set over its palette" if over else ""))
        sys.exit(1 if a.report else 0 if a.no_gate else 3)
    print("verdict OK")


if __name__ == "__main__":
    main()
