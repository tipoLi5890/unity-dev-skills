#!/usr/bin/env python3
"""audit_pixel.py — the gate for delivered PIXEL ART: is every file on one lattice, on the palette?

`audit_set.py` reads a set's geometry back off its files and `audit_frames.py`
what happens between frames; this reads the property neither sees. A sprite can
be centred, in register and cleanly keyed and still not be pixel art: resized
once after the pixel step, its blocks carry blended rows; keyed softly, its rim
is half-transparent; quantised per sheet, two sheets of one character disagree
on the skin colour. Only the OUTPUT files are opened, so the gate says the same
thing whatever the source looked like and whichever tool wrote them.

Every file gets one line, every set one more, then `verdict`.

  block    `pixel_ops.integer_block`: the GCD of the spacings between the columns
           (rows) where anything changes, as XxY. A clean xF NEAREST upscale
           reads F — or a multiple of F on a frame whose every edge happens to
           fall on an even cell — and one resampled row reads 1.
           gate: a multiple of --block F in every file, and F for the set.
  phase    where that lattice starts, modulo F. gate: 0,0 in every file.
  canvas   W x H. gate: both are multiples of F.
  uniform  `pixel_ops.block_stats`: the share of non-empty F x F tiles, laid
           from the file's own phase, whose pixels are all one RGBA value.
           gate: >= --uniform-min (100).
  partial  pixels with 0 < alpha < 255. gate: 0, unless --alpha soft.
  colours  distinct colours of the opaque (alpha 255) pixels; the set line
           carries the union. gate: <= --max-colours K, for the union too.
  off_pal  opaque pixels whose colour is not a palette entry (further than
           --palette-tol on some channel; 0 = exact). gate: 0.
  single   share of opaque blocks with no 4-neighbour of their own colour —
           isolated specks, or dithering. Printed, never gated: a highlight is
           one block by intent.

`phase` and `canvas` are gated only for a set written on a block lattice: the
sidecar says `pixel.method` "snap", or --block was passed. A "nearest" sidecar
has its frames cut from an upscaled sheet and seated wherever the cell put
them, so each keeps F px blocks at its own offset: both are printed, neither
gated, and `uniform` is measured from that offset either way. A frame with no
lattice to read (blank, or one flat colour) prints `-` and fits any.

A set is a directory holding `frames.json`, a `frames.json` path (its frames,
relative to it), a directory of PNGs, or the PNG files named on the command
line together. Expectations come from the sidecar's `pixel` block —
`block_px`, `alpha`, the palette's colours and their count — and a flag
overrules it for every set given. A set with no `pixel` block and none of
--block / --max-colours / --palette-file has nothing to be checked against and
is not measured.

Examples
  audit_pixel.py out/courier_run                                  # the sidecar says what was promised
  audit_pixel.py Assets/Art/Props/*.png --block 4 --palette-file ART_DIRECTION.md
  audit_pixel.py out/courier_run out/courier_idle --palette-file palette.hex --csv pixel.csv
  audit_pixel.py Assets/Art/Lanes/ --block 4 --max-colours 24 --no-gate

Exit codes
  0  every set passes
  1  a gate failed, bad arguments, or an unreadable file, sidecar or palette file
  2  nothing to read, or a set with nothing to check against — a gate that
     measured nothing must not read as a pass

This is the pipeline measuring its own output. The engine can still undo it:
import with Point filtering and no compression, at a pixels-per-unit that keeps
blocks square on screen.

Requires Pillow and numpy (codex's imagegen venv has both: ~/.codex/imagegen-venv/bin/python),
and `pixel_ops.py` beside this script.
"""
import argparse
import csv
import glob
import json
import os
import sys

try:
    import numpy as np
    from PIL import Image
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pixel_ops as po  # noqa: E402
except ImportError as e:
    print(f"ERROR: audit_pixel.py needs Pillow, numpy and pixel_ops.py beside this script ({e})", file=sys.stderr)
    sys.exit(1)

ALPHA = ("binary", "soft")
FIELDS = ["set", "file", "canvas_w", "canvas_h", "block_x", "block_y", "phase_x", "phase_y", "block_uniform_pct",
          "blocks", "mixed_blocks", "alpha_partial_px", "opaque_colours", "off_palette_px", "single_block_pct",
          "result"]


def find_set(arg):
    """(name, frame paths, sidecar dict or None, sidecar path or None) for a directory or a frames.json."""
    side = None
    if os.path.isdir(arg):
        d = arg.rstrip("/")
        if os.path.isfile(os.path.join(d, "frames.json")):
            side = os.path.join(d, "frames.json")
    else:
        d, side = os.path.dirname(arg) or ".", arg
    name = os.path.basename(os.path.abspath(d))
    if side:
        with open(side, encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict):
            raise ValueError("not a frames.json sidecar")
        files = [os.path.join(os.path.dirname(side), f["file"]) for f in doc.get("frames", [])
                 if isinstance(f, dict) and f.get("file") and not f.get("empty")]
        return name, files, doc, side
    stills = []
    for f in sorted(glob.glob(os.path.join(d, "*.png"))):
        try:
            with Image.open(f) as im:
                if getattr(im, "n_frames", 1) > 1:   # an APNG preview left beside the frames is not a frame
                    continue
        except OSError:
            pass                                     # kept: it is reported as unreadable, not dropped
        stills.append(f)
    return name, stills, None, None


def parse_colours(values):
    """Sidecar palette colours ('#rrggbb') -> uint8 (K, 3)."""
    out = []
    for v in values:
        s = str(v).strip().lstrip("#")
        if len(s) != 6:
            raise ValueError(f"not a #rrggbb colour: {v!r}")
        out.append([int(s[i:i + 2], 16) for i in (0, 2, 4)])
    return np.array(out, np.uint8).reshape(-1, 3)


def expectations(doc, a, flag_palette):
    """What a set is held to: flags first, then the sidecar's `pixel` block. None when there is neither."""
    px = (doc or {}).get("pixel")
    px = px if isinstance(px, dict) else {}
    block = a.block
    if block is None and isinstance(px.get("block_px"), (int, float)) and px["block_px"] >= 1:
        if float(px["block_px"]) != int(px["block_px"]):
            raise ValueError(f"pixel.block_px {px['block_px']} is not a whole number of pixels")
        block = int(px["block_px"])
    palette, source = flag_palette, a.palette_file
    side_pal = px.get("palette") if isinstance(px.get("palette"), dict) else {}
    side_cols = side_pal.get("colours") if side_pal.get("source") != "none" else None
    side_cols = parse_colours(side_cols) if isinstance(side_cols, list) and side_cols else None
    if palette is None and side_cols is not None:
        palette, source = side_cols, "sidecar"
    max_colours = a.max_colours if a.max_colours is not None else (len(side_cols) if side_cols is not None else None)
    if block is None and palette is None and max_colours is None and not px:
        return None
    return dict(block=block, palette=palette, palette_source=source, max_colours=max_colours,
                alpha=a.alpha or (px.get("alpha") if px.get("alpha") in ALPHA else "binary"),
                method=px.get("method") or "-",
                gate_lattice=a.block is not None or px.get("method") == "snap")


def off_palette(colours, counts, palette, tol):
    """Pixels whose colour is further than `tol` (largest channel difference) from every palette entry."""
    if not len(colours):
        return 0
    far = np.abs(colours[:, None, :].astype(np.int16) - palette[None, :, :].astype(np.int16)).max(axis=2).min(axis=1)
    return int(counts[far > tol].sum())


def single_blocks(u8, block, phase):
    """Share (%) of opaque blocks with no 4-neighbour of the same colour, read at one pixel per block."""
    bx, by = block
    cells = u8[(phase[1] + by // 2) % by::by, (phase[0] + bx // 2) % bx::bx]
    solid = cells[..., 3] == 255
    if not solid.any():
        return 0.0
    paired = np.zeros(solid.shape, bool)
    for axis in (0, 1):
        lead, tail = [slice(None)] * 2, [slice(None)] * 2
        lead[axis], tail[axis] = slice(0, -1), slice(1, None)
        lead, tail = tuple(lead), tuple(tail)
        same = solid[lead] & solid[tail] & np.all(cells[lead][..., :3] == cells[tail][..., :3], axis=-1)
        paired[lead] |= same
        paired[tail] |= same
    return 100.0 * float((solid & ~paired).sum()) / float(solid.sum())


def measure(path, want):
    """One file's numbers. `want` carries the block to lay tiles at and the palette, either possibly None."""
    with Image.open(path) as im:
        u8 = np.asarray(im.convert("RGBA"))
    H, W = u8.shape[:2]
    alpha = u8[..., 3]
    colours, counts = np.unique(u8[alpha == 255][:, :3], axis=0, return_counts=True)
    m = dict(file=os.path.basename(path), canvas_w=W, canvas_h=H, block_x="", block_y="", phase_x="", phase_y="",
             block_uniform_pct="", blocks="", mixed_blocks="", single_block_pct="",
             alpha_partial_px=int(((alpha > 0) & (alpha < 255)).sum()), opaque_colours=int(len(colours)),
             off_palette_px="" if want["palette"] is None else off_palette(colours, counts, want["palette"],
                                                                            want["palette_tol"]),
             colour_set={tuple(int(v) for v in c) for c in colours})
    found = po.integer_block(u8)
    if found is None:                                # blank or one flat colour: no lattice, and it fits any
        return m
    bx, by, px, py = found
    F = want["block"]
    tile = (F, F) if F else (bx, by)
    phase = (px % tile[0], py % tile[1])
    m.update(block_x=bx, block_y=by, phase_x=phase[0], phase_y=phase[1],
             single_block_pct=single_blocks(u8, tile, phase))
    if F:
        st = po.block_stats(u8, F, phase)
        if st["blocks"]:
            m.update(block_uniform_pct=st["uniform_pct"], blocks=st["blocks"], mixed_blocks=st["mixed_blocks"])
    return m


def judge(m, want, uniform_min):
    """The gates one file fails, as short flags."""
    flags, F = [], want["block"]
    if F and m["block_x"] != "":
        if m["block_x"] % F or m["block_y"] % F:
            flags.append("block")
        if m["block_uniform_pct"] != "" and m["block_uniform_pct"] < uniform_min:
            flags.append("uniform")
        if want["gate_lattice"] and (m["phase_x"] or m["phase_y"]):
            flags.append("phase")
    if F and want["gate_lattice"] and (m["canvas_w"] % F or m["canvas_h"] % F):
        flags.append("canvas")
    if want["alpha"] == "binary" and m["alpha_partial_px"]:
        flags.append("alpha")
    if want["max_colours"] is not None and m["opaque_colours"] > want["max_colours"]:
        flags.append("colours")
    if m["off_palette_px"] != "" and m["off_palette_px"] > 0:
        flags.append("off-palette")
    return flags


def hints(failing, want, union):
    """One line per failed metric: what it means and the repair."""
    F, K = want["block"], want["max_colours"]
    snap = f"sheet_to_frames.py --pixel-method snap --upscale {F}, or pixel_snap.py --upscale {F}"
    text = dict([
        ("block", f"block_px is not {F}: something resized the art after the pixel step, or it was upscaled by "
                  f"another factor — make the pixel step the last one ({snap}) and resize by NEAREST only"),
        ("uniform", f"block_uniform_pct: {F} px tiles hold more than one colour — a resample blended them; "
                    f"re-run the pixel step last ({snap})"),
        ("phase", f"lattice_phase: blocks do not start at 0,0 — the art was padded or shifted by a distance that "
                  f"is not a multiple of {F}; re-slice with --pixel-method snap, or move it by whole blocks"),
        ("canvas", f"canvas_multiple: width or height is not a multiple of {F} — choose a --canvas that is, "
                   f"or the last block is cut"),
        ("alpha", "alpha_partial_px: the rim is half-transparent — re-run the pixel step with binary alpha "
                  "(a later resize or defringe brings it back), or pass --alpha soft if that is the style"),
        ("colours", f"opaque_colours over {K}: quantise the whole set to ONE palette (--palette-file, or "
                    f"--palette {K} with --palette-out on the first sheet and --palette-file on the rest)"),
        ("off-palette", f"off_palette_px: colours outside the palette ({want['palette_source']}) — re-run the "
                        f"pixel step with --palette-file; a resize, a tint or a per-sheet --palette after it adds colours"),
    ])
    if "set-block" in failing and "block" not in failing:
        failing = failing | {"block"}
    if "set-colours" in failing and "colours" not in failing:
        text["colours"] = (f"opaque_colours: each file is within {K} but the set uses {union} — the files were "
                           f"quantised one by one; build ONE palette (--palette-out) and apply it to all "
                           f"(--palette-file)")
        failing = failing | {"colours"}
    return [f"fix {k}: {text[k]}" for k in text if k in failing]


def cell(v, spec="d"):
    return "-" if v == "" else format(v, spec)


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main():
    ap = UsageParser(description="Gate delivered pixel art: one block lattice, binary alpha, "
                                             "the colour count and the palette, read off the files.")
    ap.add_argument("targets", nargs="+",
                    help="PNG files (together one set), directories holding frames.json or PNGs, or frames.json paths")
    ap.add_argument("--block", type=int, metavar="F",
                    help="the block size the art was upscaled by, px (default: the sidecar's pixel.block_px). "
                         "Passing it also gates the canvas and the lattice phase")
    ap.add_argument("--max-colours", type=int, metavar="K",
                    help="max distinct opaque colours per file and over the set (default: the length of the "
                         "sidecar's palette)")
    ap.add_argument("--palette-file", metavar="PATH",
                    help="the fixed palette every opaque pixel must be on: .md (the --palette-section table), "
                         ".hex / .txt (one colour per line) or .png (default: the sidecar's palette colours)")
    ap.add_argument("--palette-section", default="Palette", metavar="NAME",
                    help="heading of the palette in a markdown --palette-file (default Palette)")
    ap.add_argument("--palette-tol", type=int, default=0, metavar="N",
                    help="largest per-channel distance still read as on the palette (default 0: exact)")
    ap.add_argument("--uniform-min", type=float, default=100.0,
                    help="min %% of non-empty block tiles that are one colour (default 100)")
    ap.add_argument("--alpha", choices=ALPHA,
                    help="binary: no pixel with 0 < alpha < 255 (default, or the sidecar's); soft: not gated")
    ap.add_argument("--csv", help="also write one row per file here")
    ap.add_argument("--no-gate", action="store_true",
                    help="print everything, exit 0 (still 2 if nothing was measured)")
    a = ap.parse_args()
    if a.block is not None and a.block < 1:
        print("ERROR: --block must be >= 1", file=sys.stderr)
        return 1
    if a.max_colours is not None and a.max_colours < 1:
        print("ERROR: --max-colours must be >= 1", file=sys.stderr)
        return 1
    if a.palette_tol < 0:
        print("ERROR: --palette-tol must be >= 0", file=sys.stderr)
        return 1
    flag_palette = None
    if a.palette_file:
        try:
            flag_palette, _ = po.read_palette(a.palette_file, section=a.palette_section)
        except (ValueError, OSError) as e:
            print(f"ERROR: --palette-file: {e}", file=sys.stderr)
            return 1

    sets, loose, bad_sidecars = [], [], 0
    for arg in a.targets:
        if os.path.isdir(arg) or arg.lower().endswith(".json"):
            try:
                sets.append(find_set(arg))
            except (OSError, ValueError, KeyError) as e:
                print(f"{os.path.basename(arg.rstrip('/'))[:24]:24s}  (sidecar not readable: {e})  ← FAIL")
                bad_sidecars += 1
        else:
            loose.append(arg)
    if loose:
        dirs = {os.path.dirname(os.path.abspath(f)) for f in loose}
        sets.insert(0, (os.path.basename(dirs.pop()) if len(dirs) == 1 else "files", loose, None, None))

    print(f"{'file':28s} {'canvas':>9s} {'block':>7s} {'phase':>7s} {'uniform':>8s} {'partial':>7s} "
          f"{'colours':>7s} {'off_pal':>7s} {'single':>7s}  result")
    out_rows, measured, unchecked, files_read, files_failed, sets_failed = [], 0, 0, 0, 0, bad_sidecars
    for name, files, doc, side in sets:
        if not files:
            print(f"{name[:28]:28s}  (no frames found)")
            continue
        try:
            want = expectations(doc, a, flag_palette)
        except ValueError as e:
            print(f"{name[:28]:28s}  (sidecar pixel block not readable: {e})")
            sets_failed += 1
            continue
        if want is None:
            unchecked += 1
            print(f"{name[:28]:28s}  (nothing to check against: "
                  + ("the sidecar has no pixel block" if side else "no sidecar")
                  + " — pass --block, --max-colours or --palette-file)")
            continue
        want["palette_tol"] = a.palette_tol
        F = want["block"]
        rows, failing, unreadable = [], set(), 0
        for f in files:
            try:
                m = measure(f, want)
            except (OSError, ValueError) as e:
                unreadable += 1
                print(f"{os.path.basename(f)[:28]:28s}  (not readable: {e})  ← FAIL")
                continue
            flags = judge(m, want, a.uniform_min)
            failing |= set(flags)
            m["result"] = ",".join(flags) if flags else "ok"
            rows.append(m)
            blk = "-" if m["block_x"] == "" else f"{m['block_x']}x{m['block_y']}"
            pha = "-" if m["phase_x"] == "" else f"{m['phase_x']},{m['phase_y']}"
            print(f"{m['file'][:28]:28s} {m['canvas_w']:>4d}x{m['canvas_h']:<4d} {blk:>7s} {pha:>7s} "
                  f"{cell(m['block_uniform_pct'], '.2f'):>8s} {m['alpha_partial_px']:>7d} "
                  f"{m['opaque_colours']:>7d} {cell(m['off_palette_px']):>7s} "
                  f"{cell(m['single_block_pct'], '.1f'):>7s}  "
                  + ("ok" if not flags else "← " + ", ".join(flags)))
        if not rows and not unreadable:
            continue
        measured += 1
        files_read += len(rows) + unreadable
        latticed = [m for m in rows if m["block_x"] != ""]
        set_block = int(np.gcd.reduce([v for m in latticed for v in (m["block_x"], m["block_y"])])) if latticed else 0
        phases = sorted({(m["phase_x"], m["phase_y"]) for m in latticed})
        union = len(set().union(*(m["colour_set"] for m in rows))) if rows else 0
        canvas_bad = sum(1 for m in rows if F and (m["canvas_w"] % F or m["canvas_h"] % F))
        tiles = sum(m["blocks"] for m in rows if m["blocks"] != "")
        mixed = sum(m["mixed_blocks"] for m in rows if m["blocks"] != "")
        if F and latticed and set_block != F:
            failing.add("set-block")
        if want["max_colours"] is not None and union > want["max_colours"]:
            failing.add("set-colours")
        gated = "" if want["gate_lattice"] else " (not gated)"
        print(f"set {name} files {len(rows)} method {want['method']} alpha {want['alpha']} "
              f"palette {want['palette_source'] or 'none'}")
        print(f"metric block_px {set_block if latticed else 'n/a'}" + (f" expect {F}" if F else " (not gated: no --block)"))
        if F:
            print(f"metric canvas_multiple {'yes' if not canvas_bad else f'no ({canvas_bad} file(s))'}{gated}")
            print("metric lattice_phase "
                  + ("n/a" if not phases else f"{phases[0][0]},{phases[0][1]}" if len(phases) == 1
                     else f"mixed ({len(phases)} offsets)") + gated)
            print(f"metric block_uniform_pct {(100.0 * (tiles - mixed) / tiles) if tiles else 0.0:.2f} "
                  f"mixed_blocks {mixed} of {tiles} min {a.uniform_min:g}")
        print(f"metric alpha_partial_px {sum(m['alpha_partial_px'] for m in rows)}"
              + ("" if want["alpha"] == "binary" else " (not gated: alpha soft)"))
        print(f"metric opaque_colours {union}"
              + (f" max {want['max_colours']}" if want["max_colours"] is not None else " (not gated: no --max-colours)"))
        if want["palette"] is not None:
            print(f"metric off_palette_px {sum(m['off_palette_px'] for m in rows)} "
                  f"palette_colours {len(want['palette'])} tol {a.palette_tol}")
        else:
            print("metric off_palette_px n/a (no palette to check against)")
        singles = [m["single_block_pct"] for m in rows if m["single_block_pct"] != ""]
        print("metric single_block_pct " + (f"{sum(singles) / len(singles):.1f}" if singles else "n/a") + " (not gated)")
        for line in hints(failing, want, union):
            print(line)
        bad = sum(1 for m in rows if m["result"] != "ok") + unreadable
        files_failed += bad
        sets_failed += bool(failing or unreadable)
        for m in rows:
            out_rows.append(dict({k: m[k] for k in FIELDS if k in m}, set=name))
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(out_rows)
        print(f"wrote {a.csv}")
    if not measured and not sets_failed:
        print("verdict NOTHING MEASURED — "
              + ("no set had anything to be checked against" if unchecked else "no set held a frame")
              + "; this is not a pass", file=sys.stderr)
        return 2
    print(f"verdict {'FAIL' if sets_failed else 'OK'} sets {measured} files {files_read} failed {files_failed}"
          + (f" unchecked {unchecked}" if unchecked else ""))
    if sets_failed and not a.no_gate:
        return 1
    if unchecked:
        print(f"{unchecked} set(s) had nothing to be checked against; this is not a pass", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
