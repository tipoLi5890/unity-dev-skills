#!/usr/bin/env python3
"""audit_frames.py — the gate for a delivered ANIMATION: re-measure the frames that shipped.

`audit_set.py` reads a static set back off its files; this is the same step for
frame sequences. It opens every PNG of a sequence and measures what a player
sees BETWEEN frames, which no single frame — and no contact sheet that tiles one
frame per cell — can show:

  feet    spread of the feet line (lowest row of the core silhouette), px.
  slip    how far a frame sits from where its core best overlaps the reference
          frame's (px; 0 when moving it would gain under 0.02 IoU). This is the
          jitter number: frames seated by their silhouettes read 0-2 px, frames
          sliced at their in-cell position read 11-120 px on the same sheets,
          and at 6 fps that is a character teleporting sideways.
  head_x  spread of the head's x (centroid of the top 15% of the core), px —
          the same fault as a human names it. It also moves when the pose does,
          so it is printed, never gated.
  iou     overlap of every frame's core with the reference frame's, on the
          canvas as written (min / mean). Read with --hold.
  fringe  share of the rim (visible pixels within 2 px of transparency) still
          within 150 RGB of the key colour: mostly key. A binary key reads 25-40%.
  tint    share of the rim that is the interior colour beside it MIXED with the
          key (on the line between the two, a quarter of the way or further):
          partly key. A binary key reads 43-60%; a key that cleans `fringe` to
          0.00 without un-mixing the half-keyed rim still reads 33-41% here.
  cut     frames with a solid pixel on the canvas border — cut off, not posed.

The core, the rim and the numbers are defined once, in `sprite_ops.py`.

One line per sequence, then `verdict`. HARD gates set the exit code: each has a
deterministic repair and none is a matter of taste.

  fringe > --fringe-max (0.5 %) or tint > --tint-max (2 %)   -> re-key: key_unmix.py
  cut frames > 0, or frames of unequal size     -> re-slice on a canvas that holds them
  ground: feet > --feet-max (3 px)              -> re-slice: --register ground
  ground / free: slip > --slip-max (1 % of the reference core height, at least 3 px)
                                                -> re-slice: --register ground | free

`iou` is a CLASSIFICATION, not a gate: neither re-slicing nor re-generating
changes how the frames were drawn. With --hold (the sequence is ONE pose meant
to be cycled — an idle, a stance) it reads `hold` at min IoU >= --hold-iou
(0.90: cycle the frames) or `BOIL` below it: the frames are different drawings
of one pose and cycling them shimmers however well they are registered. Play
ONE frame and breathe it in the engine instead. The exit code is not affected.

A sequence is a directory holding `frames.json` (the sidecar names the files,
their order, the mode and the reference frame), a `frames.json` path, or a
directory of PNGs in name order. The mode comes from the sidecar's
`register.mode` (ground | free | centroid | keep). A sidecar without one — or a
bare directory — is judged as an in-place action: ground for a bottom-center
pivot, centroid for a center one. `keep` (motion authored inside the cell) and
`centroid` (effects) are not gated on feet or slip; pass `--mode` to overrule
the sidecar for every sequence given.

`--onion PATH` writes the picture that belongs beside these numbers: one onion
skin per sequence (every frame as a flat tint, stacked), each labelled with its
line. One silhouette = in register; doubled bodies = the frames jump.

Examples
  audit_frames.py Assets/Art/Characters/*/ --key-color '#ff00ff' --onion review/onion.png
  audit_frames.py out/idle --key-color '#ff00ff' --hold          # an idle that will be cycled
  audit_frames.py out/* --key-color '#ff00ff' --csv audit.csv    # one row per frame, for a table

Exit codes: 0 every sequence passes · 1 a hard gate failed · 2 nothing to read
(no sequence held a frame — a gate that measured nothing must not read as a pass).

This is the pipeline measuring its own output. Re-measure the shipped bytes in
the ENGINE too (`unity-2d-sprites` -> resources/Tests/SpriteFramesAudit.cs): a number
produced by the tool that wrote the file has a conflict of interest.

Requires Pillow and numpy (codex's imagegen venv has both: ~/.codex/imagegen-venv/bin/python),
and `sprite_ops.py` beside this script.
"""
import argparse
import csv
import glob
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sprite_ops as so  # noqa: E402

MODES = ("ground", "free", "centroid", "keep")
ONION_TINTS = [(230, 60, 60), (60, 200, 60), (60, 110, 240), (240, 210, 40), (220, 80, 220), (60, 210, 210)]
ONION_GROUND = (30, 40, 60)
TILE = 320


def onion_tile(files, label, failed):
    """One sequence as an onion skin on a TILE-wide card: every frame a flat tint at ~37% opacity."""
    ims = [Image.open(f).convert("RGBA") for f in files]
    W, H = ims[0].size
    acc, box = Image.new("RGBA", (W, H), (0, 0, 0, 0)), None
    for i, im in enumerate(ims):
        if im.size != (W, H):
            continue
        a = im.getchannel("A")
        bb = a.point(lambda v: 255 if v > 16 else 0).getbbox()
        if bb:
            box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]), max(box[2], bb[2]), max(box[3], bb[3]))
        layer = Image.new("RGBA", (W, H), ONION_TINTS[i % len(ONION_TINTS)] + (0,))
        layer.putalpha(a.point(lambda v: 95 if v > 40 else 0))
        acc.alpha_composite(layer)
    skin = acc.crop(box or (0, 0, W, H))
    skin.thumbnail((TILE - 12, TILE - 12))
    card = Image.new("RGBA", (TILE, TILE + 34), ONION_GROUND + (255,))
    card.alpha_composite(skin, ((TILE - skin.width) // 2, 34 + (TILE - skin.height) // 2))
    d = ImageDraw.Draw(card)
    d.text((6, 3), label[0], fill=(255, 255, 255))
    d.text((6, 17), label[1], fill=(255, 120, 120) if failed else (150, 230, 150))
    return card


def find_sequence(arg):
    """(name, frame paths, sidecar dict or None) for one command-line argument."""
    side = None
    if os.path.isdir(arg):
        d = arg.rstrip("/")
        if os.path.isfile(os.path.join(d, "frames.json")):
            side = os.path.join(d, "frames.json")
    elif os.path.basename(arg).endswith(".json"):
        d, side = os.path.dirname(arg) or ".", arg
    else:
        return None
    if side:
        doc = json.load(open(side, encoding="utf-8"))
        files = [os.path.join(os.path.dirname(side), f["file"]) for f in doc.get("frames", [])
                 if not f.get("empty")]
        return os.path.basename(os.path.abspath(d)), [f for f in files if os.path.isfile(f)], doc
    stills = []
    for f in sorted(glob.glob(os.path.join(d, "*.png"))):
        with Image.open(f) as im:
            if getattr(im, "n_frames", 1) == 1:      # an APNG preview left beside the frames is not a frame
                stills.append(f)
    return os.path.basename(os.path.abspath(d)), stills, None


def sidecar_mode(doc):
    """The mode a sidecar declares; without one, an in-place action (the fault this gate exists for)."""
    reg = (doc or {}).get("register")
    if isinstance(reg, dict) and reg.get("mode") in MODES:
        return reg["mode"]
    legacy = (doc or {}).get("mode")                 # sidecars that name the mode at the top level
    if legacy in ("ground", "free"):
        return legacy
    if legacy == "fx":
        return "centroid"
    return "centroid" if (doc or {}).get("pivot") == "center" else "ground"


def sidecar_ref(doc):
    reg = (doc or {}).get("register")
    if isinstance(reg, dict) and isinstance(reg.get("ref"), int):
        return reg["ref"]
    return (doc or {}).get("ref", 0) if isinstance((doc or {}).get("ref", 0), int) else 0


def measure(files, key, ref, mode):
    """Per-frame rows and the sequence's aggregates."""
    rows, cores, bad, tinted, rim, sizes = [], [], 0, 0, 0, set()
    for f in files:
        rgba = np.asarray(Image.open(f).convert("RGBA"))
        sizes.add(rgba.shape[:2])
        c = so.core(rgba[..., 3])
        cores.append(c)
        b = t = r = 0
        if key is not None:
            b, t, r = so.rim_stats(rgba[..., :3].astype(np.float32), rgba[..., 3], key)
        bad, tinted, rim = bad + b, tinted + t, rim + r
        rows.append(dict(file=os.path.basename(f), feet_y=so.bottom(c), head_x=so.head_x(c),
                         cut=so.cut_by_canvas(rgba[..., 3]), fringe_px=b, tint_px=t, rim_px=r,
                         empty=not c.any(), iou="", slip_dx=0, slip_dy=0))
    live = [i for i, r in enumerate(rows) if not r["empty"]]
    ref = ref if ref in live else (live[0] if live else 0)
    body = mode in ("ground", "free", "keep")
    ious, slips = [], []
    if len(sizes) == 1 and live and body:
        rc = cores[ref]
        for i in live:
            u = int((cores[i] | rc).sum())
            rows[i]["iou"] = round(float((cores[i] & rc).sum()) / u, 4) if u else 0.0
            if i != ref:
                ious.append(rows[i]["iou"])
                dx, dy = so.slip(rc, cores[i], mode != "free")
                rows[i]["slip_dx"], rows[i]["slip_dy"] = int(dx), int(dy)
                slips.append(max(abs(dx), abs(dy)))
    ys = np.nonzero(cores[ref].any(axis=1))[0] if live else []
    feet = [rows[i]["feet_y"] for i in live]
    heads = [rows[i]["head_x"] for i in live if rows[i]["head_x"] is not None]
    agg = dict(frames=len(rows), canvas=sorted(sizes), ref=ref,
               ref_core_h=int(ys.max() - ys.min() + 1) if len(ys) else 0,
               feet_drift_px=(max(feet) - min(feet)) if feet else 0,
               slip_max_px=max(slips) if slips else 0,
               head_x_drift_px=(max(heads) - min(heads)) if heads else 0.0,
               iou_min=min(ious) if ious else 1.0, iou_mean=(sum(ious) / len(ious)) if ious else 1.0,
               fringe_pct=so.pct(bad, rim), tint_pct=so.pct(tinted, rim), rim_px=rim,
               cut=[r["file"] for r in rows if r["cut"]], mixed_sizes=len(sizes) > 1)
    return rows, agg


def main():
    ap = argparse.ArgumentParser(description="Gate delivered animation frames: feet line, slip from the "
                                             "reference, key fringe and tint, frames cut by the canvas.")
    ap.add_argument("sequences", nargs="+", help="directories holding frames.json (or PNG frames), or frames.json paths")
    ap.add_argument("--key-color", help="the key colour the sheet was generated on, e.g. '#ff00ff' — enables "
                                        "fringe and tint; without it neither is measured or gated")
    ap.add_argument("--mode", choices=MODES,
                    help="overrule the sidecar for every sequence: ground = feet on one line, in register; "
                         "free = in register, feet may leave the floor; keep = motion authored in the cell "
                         "(feet and slip printed, not gated); centroid = an effect (no silhouette numbers)")
    ap.add_argument("--ref", type=int, help="reference frame index (default: the sidecar's, else 0)")
    ap.add_argument("--hold", action="store_true",
                    help="the sequence is ONE pose meant to be cycled: classify it hold / BOIL by its minimum IoU")
    ap.add_argument("--fringe-max", type=float, default=0.5, help="max fringe %% of rim pixels (default 0.5)")
    ap.add_argument("--tint-max", type=float, default=2.0, help="max tint %% of rim pixels (default 2)")
    ap.add_argument("--feet-max", type=float, default=3.0, help="ground: max feet-line spread, px (default 3)")
    ap.add_argument("--slip-max", type=float, default=1.0,
                    help="ground / free: max slip as %% of the reference core height, floor 3 px (default 1)")
    ap.add_argument("--hold-iou", type=float, default=0.90, help="--hold: min IoU read as a true hold (default 0.90)")
    ap.add_argument("--csv", help="also write one row per frame here")
    ap.add_argument("--onion", metavar="PATH",
                    help="also write one image holding an onion skin of every sequence, labelled with its "
                         "numbers. Must not land inside a sequence directory")
    ap.add_argument("--no-gate", action="store_true", help="print everything, exit 0 (still 2 if nothing was read)")
    a = ap.parse_args()
    key = so.parse_hex(a.key_color) if a.key_color else None

    print(f"{'sequence':24s} {'n':>3s} {'canvas':>9s} {'mode':8s} {'feet':>4s} {'slip':>4s} {'head_x':>6s} "
          f"{'iou min/mean':>12s} {'fringe':>7s} {'tint':>7s} {'cut':>3s}  result")
    out_rows, failed, read, tiles = [], 0, 0, []
    for arg in a.sequences:
        seq = find_sequence(arg)
        if not seq or not seq[1]:
            print(f"{os.path.basename(arg.rstrip('/'))[:24]:24s}  (no frames found)")
            continue
        name, files, doc = seq
        read += 1
        mode = a.mode or sidecar_mode(doc)
        rows, g = measure(files, key, a.ref if a.ref is not None else sidecar_ref(doc), mode)
        flags, notes = [], []
        if key is not None and (g["fringe_pct"] > a.fringe_max or g["tint_pct"] > a.tint_max):
            flags.append("key left on the rim: re-key with key_unmix.py")
        if g["cut"]:
            flags.append(f"{len(g['cut'])} frame(s) cut by the canvas: re-slice on a canvas that holds them")
        if g["mixed_sizes"]:
            flags.append("frames are not one canvas size")
        if mode == "ground" and g["feet_drift_px"] > a.feet_max:
            flags.append(f"feet line spreads {g['feet_drift_px']} px: re-slice with --register ground")
        limit = max(3.0, a.slip_max / 100.0 * g["ref_core_h"])
        if mode in ("ground", "free") and g["slip_max_px"] > limit:
            flags.append(f"out of register by {g['slip_max_px']} px (max {limit:.0f}): re-slice with "
                         f"--register {mode} — or --mode keep if the travel is authored")
        if mode == "keep" and g["slip_max_px"] > limit:
            notes.append(f"travels {g['slip_max_px']} px in-cell (kept by choice)")
        if a.hold and mode in ("ground", "free", "keep"):
            notes.append("hold: cycle it" if g["iou_min"] >= a.hold_iou else
                         "BOIL: play ONE frame + engine motion, do not cycle")
        ch, cw = g["canvas"][0] if g["canvas"] else (0, 0)
        body = mode in ("ground", "free", "keep")
        fr = f"{g['fringe_pct']:.2f}%" if key is not None else "n/a"
        ti = f"{g['tint_pct']:.2f}%" if key is not None else "n/a"
        res = ("FAIL: " + "; ".join(flags)) if flags else "ok"
        if notes:
            res += "  [" + "; ".join(notes) + "]"
        print(f"{name[:24]:24s} {g['frames']:>3d} {cw:>4d}x{ch:<4d} {mode:8s} "
              f"{(str(g['feet_drift_px']) if body else '-'):>4s} {(str(g['slip_max_px']) if body else '-'):>4s} "
              f"{(format(g['head_x_drift_px'], '.1f') if body else '-'):>6s} "
              f"{(format(g['iou_min'], '.2f') + '/' + format(g['iou_mean'], '.2f') if body else '-'):>12s} "
              f"{fr:>7s} {ti:>7s} {len(g['cut']):>3d}  {res}")
        failed += bool(flags)
        for r in rows:
            out_rows.append(dict(sequence=name, mode=mode, **r))
        if a.onion:
            if os.path.dirname(os.path.abspath(a.onion)) == os.path.dirname(os.path.abspath(files[0])):
                print(f"ERROR: --onion {a.onion} would land in a frame directory — the next glob takes it "
                      f"for a frame and an importer for a sprite. Write it elsewhere.", file=sys.stderr)
                return 1
            numbers = (f"slip {g['slip_max_px']} feet {g['feet_drift_px']} iou {g['iou_min']:.2f}" if body
                       else f"fringe {fr} tint {ti}")
            tiles.append(onion_tile(files, (f"{name[:30]}  {g['frames']}f {mode}",
                                            numbers + ("  FAIL" if flags else "  ok")), bool(flags)))
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["sequence", "mode", "file", "feet_y", "head_x", "iou", "slip_dx",
                                               "slip_dy", "cut", "fringe_px", "tint_px", "rim_px", "empty"])
            w.writeheader()
            w.writerows(out_rows)
        print(f"wrote {a.csv}")
    if tiles:
        cols = min(5, len(tiles))
        sheet = Image.new("RGBA", (cols * TILE, ((len(tiles) + cols - 1) // cols) * (TILE + 34)), ONION_GROUND + (255,))
        for k, t in enumerate(tiles):
            sheet.alpha_composite(t, ((k % cols) * TILE, (k // cols) * (TILE + 34)))
        os.makedirs(os.path.dirname(os.path.abspath(a.onion)), exist_ok=True)
        sheet.convert("RGB").save(a.onion)
        print(f"wrote {a.onion} onion skins {len(tiles)}")
    if not read:
        print("verdict NOTHING READ — no sequence held a frame; this is not a pass", file=sys.stderr)
        return 2
    print(f"verdict {'FAIL' if failed else 'OK'} sequences {read} failed {failed}"
          + ("" if key is not None else " (fringe and tint not measured: no --key-color)"))
    return 1 if failed and not a.no_gate else 0


if __name__ == "__main__":
    sys.exit(main())
