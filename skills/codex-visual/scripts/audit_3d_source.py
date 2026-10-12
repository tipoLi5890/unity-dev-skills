#!/usr/bin/env python3
"""audit_3d_source.py — the gate on an image before it is sent to an image-to-3D graph.

A converter masks the subject, crops it to a square and shows the model only
that crop, so what the picture gets wrong the mesh inherits: a subject cut by
the frame is a mesh cut the same way, a second object is fused into the first,
and four views at four scales come back as a stretched box. A conversion costs
minutes; this costs a second.

Two shapes of input:

  audit_3d_source.py IMAGE.png [IMAGE.png ...]      # single three-quarter sources
  audit_3d_source.py --views DIR                    # front/left/back/right.png from turnaround_to_views.py

Columns, single image
  size     W x H                                    gate: square, and >= --min-side (default 1024)
  bg       share of the outer frame that is the background colour   gate: >= 0.98 (a flat field)
  fill     the subject's larger side over the canvas side           gate: --fill-min .. --fill-max (0.50 .. 0.98)
  edge     the subject touches the canvas edge                      gate: no
  parts    connected pieces holding more than --part-min (1%) of the subject   gate: 1
  off      subject centre minus canvas centre, as a share of the canvas       reported

Columns, --views
  each view: canvas, object width and height in px, fill
  gates: four square canvases of one size; object heights within --tol (4%) of each other;
  front and back widths within --tol; left and right widths within --tol; the largest
  object side between 0.80 and 0.95 of the canvas (the model wants about 1/1.1)

The converter re-crops the subject with its own margin, so fill only has to keep the subject
large and clear of the edge. This gates the brief this skill draws to — a flat field, one
object — not everything a background remover can survive.

It cannot tell which side view is the left one: that shows only after conversion, as a hue
shift (`reference/image-to-3d-input.md` §6).

Exit 0 = pass, 1 = a gate failed, 2 = a file could not be read. An alpha PNG is read by its
alpha; an opaque one by distance from its corner colour (--bg-tol).

Requires Pillow and numpy, and `sprite_ops.py` beside this script.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sprite_ops import label  # noqa: E402

VIEW_NAMES = ("front", "left", "back", "right")


def subject_mask(path, bg_tol):
    """(mask, share of the outer frame that is background)."""
    im = Image.open(path)
    if im.mode in ("RGBA", "LA") and im.getchannel("A").getextrema()[0] < 255:
        mask = np.asarray(im.getchannel("A")) > 16
    else:
        px = np.asarray(im.convert("RGB")).astype(np.int16)
        corners = np.stack([px[0, 0], px[0, -1], px[-1, 0], px[-1, -1]])
        mask = np.abs(px - np.median(corners, axis=0)).max(axis=2) > bg_tol
    band = max(2, min(mask.shape) // 100)
    frame = np.ones(mask.shape, bool)
    frame[band:-band, band:-band] = False
    return mask, float(1.0 - mask[frame].mean())


def bbox(mask):
    rows, cols = np.where(mask.any(axis=1))[0], np.where(mask.any(axis=0))[0]
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def audit_single(path, args):
    mask, bg = subject_mask(path, args.bg_tol)
    h, w = mask.shape
    fails = []
    if not mask.any():
        return f"{os.path.basename(path)}: no subject found", ["empty"]
    lab, n = label(mask)
    sizes = np.bincount(lab.ravel(), minlength=n + 1)[1:]
    parts = int((sizes > args.part_min * sizes.sum()).sum())
    main = lab == int(np.argmax(sizes)) + 1
    x0, y0, x1, y1 = bbox(main)
    fill = max(x1 - x0, y1 - y0) / min(w, h)
    edge = bool(main[0].any() or main[-1].any() or main[:, 0].any() or main[:, -1].any())
    off = (((x0 + x1) / 2 - w / 2) / w, ((y0 + y1) / 2 - h / 2) / h)

    if w != h:
        fails.append("not square")
    if min(w, h) < args.min_side:
        fails.append(f"side under {args.min_side}")
    if bg < 0.98:
        fails.append("background not flat (shadow, floor or gradient reaches the frame)")
    if edge:
        fails.append("subject cut by the canvas")
    elif not args.fill_min <= fill <= args.fill_max:
        fails.append(f"fill {fill:.2f} outside {args.fill_min}..{args.fill_max}")
    if parts != 1:
        fails.append(f"{parts} separate pieces")
    line = (f"{os.path.basename(path)}: size {w}x{h}  bg {bg:.3f}  fill {fill:.2f}  "
            f"edge {'yes' if edge else 'no'}  parts {parts}  off {off[0]:+.2f},{off[1]:+.2f}")
    return line, fails


def audit_views(folder, args):
    lines, fails, boxes, canvases = [], [], {}, set()
    for name in VIEW_NAMES:
        path = os.path.join(folder, name + ".png")
        mask, _bg = subject_mask(path, args.bg_tol)
        h, w = mask.shape
        canvases.add((w, h))
        if not mask.any():
            fails.append(f"{name}: empty")
            continue
        x0, y0, x1, y1 = bbox(mask)
        boxes[name] = (x1 - x0, y1 - y0)
        lines.append(f"{name:5s}: canvas {w}x{h}  object {x1 - x0}x{y1 - y0}  fill {max(x1 - x0, y1 - y0) / min(w, h):.2f}")
    if len(canvases) != 1 or any(w != h for w, h in canvases):
        fails.append(f"canvases differ or are not square: {sorted(canvases)}")
    if len(boxes) == 4:
        def spread(values):
            return (max(values) - min(values)) / max(values)
        heights = [boxes[n][1] for n in VIEW_NAMES]
        if spread(heights) > args.tol:
            fails.append(f"heights differ by {spread(heights):.1%}: the views are not at one scale")
        for a, b in (("front", "back"), ("left", "right")):
            if spread([boxes[a][0], boxes[b][0]]) > args.tol:
                fails.append(f"{a} and {b} widths differ by {spread([boxes[a][0], boxes[b][0]]):.1%}")
        side = min(next(iter(canvases)))
        largest = max(max(b) for b in boxes.values()) / side
        if not 0.80 <= largest <= 0.95:
            fails.append(f"largest object side is {largest:.2f} of the canvas, want about 0.91")
    return lines, fails


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("images", nargs="*")
    parser.add_argument("--views", help="Folder holding front.png, left.png, back.png, right.png")
    parser.add_argument("--min-side", type=int, default=1024)
    parser.add_argument("--fill-min", type=float, default=0.50)
    parser.add_argument("--fill-max", type=float, default=0.98)
    parser.add_argument("--part-min", type=float, default=0.01)
    parser.add_argument("--tol", type=float, default=0.04)
    parser.add_argument("--bg-tol", type=int, default=24)
    args = parser.parse_args()
    if bool(args.images) == bool(args.views):
        parser.error("give image files, or --views DIR")

    failed = False
    try:
        if args.views:
            lines, fails = audit_views(args.views, args)
            print("\n".join(lines))
            for reason in fails:
                print(f"  FAIL {reason}")
            failed = bool(fails)
        else:
            for path in args.images:
                line, fails = audit_single(path, args)
                print(line)
                for reason in fails:
                    print(f"  FAIL {reason}")
                failed = failed or bool(fails)
    except OSError as exc:
        print(f"unreadable: {exc}")
        return 2
    print("FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
