#!/usr/bin/env python3
"""key_unmix.py — key a flat chroma field out of a sheet WITHOUT leaving its colour on the rim.

A binary key (alpha 0 inside a tolerance, 255 outside) is wrong on exactly one
kind of pixel: the anti-aliased rim, which the renderer painted as a MIX of the
key and the subject. On a sticker-style sheet over #FF00FF the field measures
(247,2,243), the outline (7,1,8), and the rim pixel between them (118,8,121) —
half key. A tolerance of 40 keeps that pixel fully opaque and purple. Measured
over 25 animation sheets, 25-40% of the pixels within 2 px of transparency
stayed within 150 RGB of the key; `remove_chroma_key.py --despill` on five
static sheets left 20-27% (5-52% per asset once sliced). It reads as a pink hairline around every cut-out, in the
engine and in a GIF alike, and no importer setting removes it: "Alpha Is
Transparency" repairs the RGB under TRANSPARENT pixels, and these are opaque.

What this does instead — in the BOUNDARY BAND only (pixels within --band px of
the keyed field), never in the interior:

  --edge outline (default; art with a dark outline)
      alpha runs along the key -> outline line: 0 at the key, 1 at --hi from it
      (330 by default: a near-black outline sits ~350 from #FF00FF), and the key
      is un-mixed out of the colour, c = (rgb - (1 - a) * key) / a.
  --edge fill (effects and anything with NO outline: sparks, dust, glows)
      the rim pixel is a mix of the key and the fill BESIDE it, so it is
      projected onto the key -> nearest-interior-fill line for its alpha and
      takes that fill's colour. Strongly key-tinted pockets between an effect's
      points (the model blends them) join the band wherever they sit.

then a choke: alpha under --choke (0.35) goes to 0, and so does any band pixel
the un-mix could not clean. Nothing inside the band is touched, which is the
whole point — two keys that look simpler are both wrong:

  * alpha from RGB distance EVERYWHERE cannot have both ends. A ramp long
    enough to clean the half-mixed rim (to 330) turns 36-83% of the INTERIOR
    translucent — every fill nearer the key than the outline is, white
    included. A ramp short enough to spare the interior (to 150) leaves the
    half-mixed rim opaque: 33-41% of it still partly key, and a character with
    purple fills loses a quarter of its interior anyway. `--soft-matte` fails
    the same way from the other side: it eats a subject that shares the key's
    channel.
  * alpha from the key's SPILL (min(R,B) - G for magenta) under-reads the key
    in a saturated fill: a half-magenta, half-yellow pixel reads 22% key, so it
    comes out 78% opaque and PINK — 29% of a yellow spark's rim. Blue, white
    and tan effects survive it, which is how it gets shipped.
    Hence the projection onto the neighbouring fill for outline-less art.

The band's alpha is soft (0.35..1) but its colour is clean, so the 1-bit cut a
GIF makes (alpha > 16) lands on un-mixed pixels: no halo. That is the
difference from a soft matte, whose half-keyed pixels keep the key's colour.

`--defringe` repairs sprites that are ALREADY keyed, in place of re-slicing
them — for a shipped set that has since been trimmed, 9-sliced or retouched, or
whose opaque sheet is gone. In the band next to transparency, a pixel still
tinted by the key takes the nearest clean colour and an alpha from the same
projection; the pass repeats while it finds more (choking a pixel away exposes
the one behind it). Nothing is moved or resampled: on 49 shipped sprites the
bounding box changed by at most 1 px, and what went was the outermost,
mostly-key ring. It took them from fringe 5-52 % / tint 26-84 % to 0.0-0.7 % /
0.0-0.4 %. What it cannot clean is the art's own key-hued colour on the rim (a
pink fill on a magenta key) — key a colour the art does not contain.

Every run prints two numbers about the rim (visible pixels within 2 px of
transparency), before and after, and exits 1 if either is still over its limit:
`fringe` — within 150 RGB of the key, mostly key (--fringe-max 0.5 %) — and
`tint` — the interior colour beside it mixed with the key, partly key
(--tint-max 2 %). A binary key reads 25-40 % and 43-60 %; un-mixed, 0.0-0.2 %
and 0.0-0.3 %. `tint` is the one that tells the two wrong keys above from a
right one: the short global ramp reads fringe 0.00 % and tint 33-41 %, the
spill estimate fringe 0.03 % and tint 29 % on a yellow spark.

Examples
  # an opaque sheet from the generator -> a keyed RGBA sheet for slice_grid.py / sheet_to_frames.py
  key_unmix.py raw/hero_idle.png --out keyed/hero_idle.png --key-color '#ff00ff'
  # an effect sheet: no outline to un-mix against
  key_unmix.py raw/fx_spark.png --out keyed/fx_spark.png --edge fill
  # a non-black outline: derive the ramp from its colour
  key_unmix.py raw/ui.png --out keyed/ui.png --outline-color '#081930'
  # already-keyed sprites: measure, then repair in place
  key_unmix.py --defringe Assets/Art/UI --dry-run
  key_unmix.py --defringe Assets/Art/UI --in-place

Exit codes: 0 ok · 1 fringe still above --fringe-max, the input already carries
alpha (the agent keyed it: reject the sheet and ask for an opaque one — or use
--defringe), bad args · 2 nothing was keyed (the field is not --key-color: the
transparent share is under 1%).

Requires Pillow and numpy (codex's imagegen venv has both: ~/.codex/imagegen-venv/bin/python).
"""
import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sprite_ops as so  # noqa: E402

dist, spill, dilate, nearest_fill, pct, parse_hex = so.dist, so.spill, so.dilate, so.nearest_fill, so.pct, so.parse_hex
FRINGE_DIST = so.FRINGE_DIST


def key_sheet(rgb, key, edge, lo, hi, band_px, choke):
    """rgb float32 HxWx3 on a flat `key` field -> (rgb, alpha 0..1, stats)."""
    d = dist(rgb, key)
    bg = d < lo
    band = ~bg & dilate(bg, band_px)
    if edge == "fill":
        band |= ~bg & (d < 200.0) & (spill(rgb, key) > 60.0)
        interior = ~bg & ~band
        if interior.any():
            fill, got = nearest_fill(rgb, interior, band)
            v = fill - key
            ab = np.clip(((rgb - key) * v).sum(axis=2) / np.maximum((v * v).sum(axis=2), 1.0), 0.0, 1.0)
            ab = np.where(got, ab, 0.0)          # a rim with no interior anywhere near it is field
            c = np.where(band[..., None], fill, rgb)
        else:
            ab, c = np.zeros(d.shape, np.float32), rgb
        a = np.where(bg, 0.0, np.where(band, ab, 1.0))
    else:
        ab = np.clip((d - lo * 0.5) / max(hi - lo * 0.5, 1.0), 0.0, 1.0)
        a = np.where(bg, 0.0, np.where(band, ab, 1.0))
        an = np.maximum(a, 0.02)[..., None]
        c = np.where(band[..., None], (rgb - (1.0 - a[..., None]) * key) / an, rgb)
    c = np.clip(c, 0.0, 255.0)
    choked = band & (a > 0) & (a < choke)
    still = band & (a >= choke) & (dist(c, key) < FRINGE_DIST)
    a = np.where(choked | still, 0.0, a)
    c = np.where((a > 0)[..., None], c, 0.0)      # never leave the key's colour under a transparent pixel
    return c, a, dict(field_px=int(bg.sum()), band_px=int(band.sum()),
                      choked_px=int(choked.sum()), uncleanable_px=int(still.sum()))


def defringe(rgba, key, band_px, choke, passes=3):
    """Already-keyed RGBA float32 -> (rgba, fixed px). Geometry untouched; only tinted rim pixels change.

    A rim pixel is tinted when it is near the key, leans to the key's hue, or sits on the line
    from the interior colour beside it to the key (the same test `tint` is measured with, at a
    lower share so the repair reaches further than the gate). It takes the nearest clean colour
    and an alpha from its projection on that colour -> key line. Chocking a pixel away exposes
    the one behind it, so the pass repeats until nothing more is found."""
    out, total = rgba.copy(), 0
    for _ in range(passes):
        rgb, al = out[..., :3], out[..., 3]
        solid = al > 0
        band = solid & dilate(~solid, band_px)
        bad = band & ((dist(rgb, key) < 200.0) | (spill(rgb, key) > 70.0))
        inner = solid & ~band
        if inner.any():
            beside, got = nearest_fill(rgb, inner, band, max_iter=8)
            share, on_line = so.key_share(rgb, beside, key)
            bad |= band & got & on_line & (share >= 0.15)
        clean = solid & ~bad
        if not bad.any() or not clean.any():
            break
        fill, got = nearest_fill(rgb, clean, bad)
        v = fill - key
        a = np.clip(((rgb - key) * v).sum(axis=2) / np.maximum((v * v).sum(axis=2), 1.0), 0.0, 1.0)
        fix = bad & got & (a < 0.98)                  # a pixel already on its fill has nothing to un-mix
        if not fix.any():
            break
        out[..., :3] = np.where(fix[..., None], fill, rgb)
        na = np.where(fix, al * a, al)
        na = np.where(fix & (na < choke * 255.0), 0.0, na)
        out[..., 3] = na
        out[..., :3] = np.where((na > 0)[..., None], out[..., :3], 0.0)
        total += int(fix.sum())
    return out, total


def border_median(rgb):
    ring = np.concatenate([rgb[:2].reshape(-1, 3), rgb[-2:].reshape(-1, 3),
                           rgb[:, :2].reshape(-1, 3), rgb[:, -2:].reshape(-1, 3)])
    return np.median(ring, axis=0)


def save_rgba(c, a255, path):
    out = np.dstack([np.clip(np.rint(c), 0, 255), np.clip(np.rint(a255), 0, 255)]).astype(np.uint8)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    Image.fromarray(out, "RGBA").save(path)


def main():
    ap = argparse.ArgumentParser(description="Key a flat chroma field out by un-mixing the boundary band, "
                                             "or de-fringe sprites that are already keyed.")
    ap.add_argument("inputs", nargs="+", help="an opaque sheet on a flat key field; with --defringe, keyed "
                                              "PNG files or directories of them")
    ap.add_argument("--out", help="output RGBA PNG (one input)")
    ap.add_argument("--outdir", help="output directory (several inputs, or --defringe without --in-place)")
    ap.add_argument("--key-color", default="#ff00ff",
                    help="the key colour named in the generation prompt (default #ff00ff), or 'auto' = the "
                         "median colour of the sheet's 2 px border")
    ap.add_argument("--edge", choices=["outline", "fill"], default="outline",
                    help="outline (default) = the rim is key mixed with a dark outline; fill = no outline "
                         "(effects): project each rim pixel onto the fill beside it")
    ap.add_argument("--lo", type=float, default=60.0,
                    help="RGB distance from the key still counted as the field (default 60: a painted "
                         "#FF00FF field measures up to ~45 off at the sheet corners)")
    ap.add_argument("--hi", type=float, default=None,
                    help="--edge outline: distance from the key at which a rim pixel is fully opaque "
                         "(default 330, a near-black outline; or derived from --outline-color)")
    ap.add_argument("--outline-color", help="--edge outline: the outline's colour, e.g. '#081930' — sets --hi "
                                            "to 0.94 of its distance from the key")
    ap.add_argument("--band", type=int, default=2, help="width of the boundary band in px (default 2)")
    ap.add_argument("--choke", type=float, default=0.35, help="rim alpha below this goes to 0 (default 0.35)")
    ap.add_argument("--fringe-max", type=float, default=0.5, help="exit 1 above this fringe %% (default 0.5)")
    ap.add_argument("--tint-max", type=float, default=2.0, help="exit 1 above this tint %% (default 2)")
    ap.add_argument("--defringe", action="store_true",
                    help="inputs are ALREADY keyed: repair the tinted rim without moving geometry")
    ap.add_argument("--in-place", action="store_true", help="--defringe: overwrite the inputs")
    ap.add_argument("--dry-run", action="store_true", help="measure and report only; write nothing")
    a = ap.parse_args()

    files = []
    for p in a.inputs:
        files += sorted(glob.glob(os.path.join(p, "*.png"))) if os.path.isdir(p) else [p]
    if not files:
        print("ERROR: no input files", file=sys.stderr)
        return 1
    if not a.dry_run:
        if a.defringe and not (a.in_place or a.outdir):
            print("ERROR: --defringe needs --in-place, --outdir or --dry-run", file=sys.stderr)
            return 1
        if not a.defringe and not (a.out or a.outdir):
            print("ERROR: need --out (one input) or --outdir (or --dry-run)", file=sys.stderr)
            return 1
        if a.out and len(files) != 1:
            print("ERROR: --out takes exactly one input; use --outdir for several", file=sys.stderr)
            return 1
    if a.hi is not None and a.outline_color:
        print("ERROR: give --hi or --outline-color, not both", file=sys.stderr)
        return 1

    worst_f, worst_t, rc = 0.0, 0.0, 0
    for path in files:
        src = Image.open(path)
        name = os.path.basename(path)
        has_alpha = "A" in src.getbands() and src.getchannel("A").getextrema()[0] < 255
        if a.defringe:
            rgba = np.asarray(src.convert("RGBA")).astype(np.float32)
            key = np.asarray(parse_hex("#ff00ff" if a.key_color == "auto" else a.key_color), np.float32)
            b0, t0, r0 = so.rim_stats(rgba[..., :3], rgba[..., 3], key)
            out, fixed = defringe(rgba, key, a.band, a.choke)
            b1, t1, r1 = so.rim_stats(out[..., :3], out[..., 3], key)
            print(f"defringe {name} fixed_px {fixed} rim_px {r0} fringe_pct {pct(b0, r0):.2f} -> {pct(b1, r1):.2f} "
                  f"tint_pct {pct(t0, r0):.2f} -> {pct(t1, r1):.2f}")
            worst_f, worst_t = max(worst_f, pct(b1, r1)), max(worst_t, pct(t1, r1))
            if not a.dry_run and fixed:
                save_rgba(out[..., :3], out[..., 3], path if a.in_place else os.path.join(a.outdir, name))
            continue
        if has_alpha:
            print(f"ERROR: {path} already carries alpha — the agent keyed it itself, and such a key has no "
                  f"fully opaque rim to un-mix. Reject the sheet and ask for an OPAQUE image on the flat key "
                  f"colour; for sprites that are already keyed and shipped, use --defringe.", file=sys.stderr)
            rc = 1
            continue
        rgb = np.asarray(src.convert("RGB")).astype(np.float32)
        field = border_median(rgb)
        key = field if a.key_color == "auto" else np.asarray(parse_hex(a.key_color), np.float32)
        off = float(np.sqrt(((field - key) ** 2).sum()))
        print(f"key #{int(key[0]):02x}{int(key[1]):02x}{int(key[2]):02x} painted_field "
              f"({field[0]:.0f},{field[1]:.0f},{field[2]:.0f}) off_by {off:.1f}")
        if off > a.lo:
            print(f"WARN: the sheet's border is {off:.0f} from --key-color, further than --lo {a.lo:g}: this is "
                  f"not the field the prompt named. Check the hex, or pass --key-color auto.")
        hi = a.hi
        if a.outline_color:
            oc = np.asarray(parse_hex(a.outline_color), np.float32)
            hi = 0.94 * float(np.sqrt(((oc - key) ** 2).sum()))
        hi = 330.0 if hi is None else hi
        hard = (dist(rgb, key) > 40.0) * 255.0            # what a binary key at tolerance 40 would ship
        b0, t0, r0 = so.rim_stats(rgb, hard, key)
        c, al, st = key_sheet(rgb, key, a.edge, a.lo, hi, a.band, a.choke)
        b1, t1, r1 = so.rim_stats(c, al, key)
        transparent = 100.0 * float((al == 0).mean())
        print(f"keyed {name} edge {a.edge} lo {a.lo:g}" + (f" hi {hi:g}" if a.edge == "outline" else "")
              + f" band {a.band} choke {a.choke:g} transparent_pct {transparent:.1f} band_px {st['band_px']} "
                f"choked_px {st['choked_px']} uncleanable_px {st['uncleanable_px']}")
        print(f"fringe_pct binary_key {pct(b0, r0):.2f} -> unmixed {pct(b1, r1):.2f} (rim_px {r1})")
        print(f"tint_pct binary_key {pct(t0, r0):.2f} -> unmixed {pct(t1, r1):.2f}")
        if transparent < 1.0:
            print(f"ERROR: {transparent:.2f}% of {name} was keyed — the field is not this key colour.",
                  file=sys.stderr)
            rc = max(rc, 2)
            continue
        worst_f, worst_t = max(worst_f, pct(b1, r1)), max(worst_t, pct(t1, r1))
        if not a.dry_run:
            dest = a.out or os.path.join(a.outdir, name)
            save_rgba(c, al * 255.0, dest)
            print(f"wrote {dest}")
    if worst_f > a.fringe_max or worst_t > a.tint_max:
        hint = ("what is left is the art's own key-hued colour on the rim (a pink or purple fill on a magenta "
                "key), or a mix deeper than --band: a key colour the art lacks avoids the first" if a.defringe else
                "the art itself carries the key's hue (pink / purple fills are not an effect): use --edge outline"
                if a.edge == "fill" else
                "outline-less art (sparks, dust, glows) wants --edge fill; a coloured outline wants --outline-color")
        print(f"FAIL: fringe {worst_f:.2f}% (max {a.fringe_max:g}) tint {worst_t:.2f}% (max {a.tint_max:g}) — {hint}.",
              file=sys.stderr)
        rc = max(rc, 1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
