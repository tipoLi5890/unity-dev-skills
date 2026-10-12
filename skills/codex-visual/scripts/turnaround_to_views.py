#!/usr/bin/env python3
"""turnaround_to_views.py — split a one-row turnaround sheet into four square views at ONE scale.

A multi-view image-to-3D model reads each view as a camera on the same rig, so
the object must have the same pixel scale in all four. A sheet cut into panels
and fitted panel by panel breaks that for anything that is not taller than it
is wide: the front of a wide crate is fitted to its width, its side to its
height, and the mesh comes back stretched along its depth.

This finds the four objects on the sheet's flat background, takes the largest
side any of them has, and cuts every view as a square of that side times
--pad, centred on its own object.

usage:
    turnaround_to_views.py SHEET.png OUT_DIR [--pad 1.1] [--size 1024] [--order front,left,back,right]

Writes OUT_DIR/front.png, left.png, back.png, right.png and prints one JSON
object with each object's box. Exit 1 when the sheet does not hold exactly
four separated objects — regenerate with wider gaps rather than loosening
--bg-tol.

Needs Pillow and numpy (the same interpreter the other scripts here use).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def object_runs(mask: np.ndarray, min_width: int) -> list[tuple[int, int]]:
    """Column spans that hold content, ignoring specks narrower than min_width."""
    runs, start = [], None
    for x, on in enumerate(list(mask.any(axis=0)) + [False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            if x - start >= min_width:
                runs.append((start, x))
            start = None
    return runs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("sheet", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--pad", type=float, default=1.1, help="Frame side over the largest object side")
    parser.add_argument("--size", type=int, default=1024, help="Output side, px")
    parser.add_argument("--order", default="front,left,back,right", help="View names, left to right on the sheet")
    parser.add_argument("--bg-tol", type=int, default=24, help="Max channel distance from the corner colour that is still background")
    args = parser.parse_args()

    names = args.order.split(",")
    if sorted(names) != ["back", "front", "left", "right"]:
        parser.error("--order must name front, left, back and right once each")

    image = Image.open(args.sheet).convert("RGB")
    pixels = np.asarray(image).astype(np.int16)
    background = pixels[0, 0]
    mask = np.abs(pixels - background).max(axis=2) > args.bg_tol

    runs = object_runs(mask, max(4, image.width // 50))
    if len(runs) != 4:
        print(json.dumps({"error": f"found {len(runs)} separated objects, need 4", "spans": runs}))
        return 1

    boxes = []
    for x0, x1 in runs:
        rows = np.where(mask[:, x0:x1].any(axis=1))[0]
        boxes.append((x0, int(rows[0]), x1, int(rows[-1]) + 1))
    side = round(args.pad * max(max(b[2] - b[0], b[3] - b[1]) for b in boxes))

    args.out.mkdir(parents=True, exist_ok=True)
    report = {"frame_side": side, "views": {}}
    for name, (x0, y0, x1, y1) in zip(names, boxes):
        frame = Image.new("RGB", (side, side), tuple(int(c) for c in background))
        frame.paste(image.crop((x0, y0, x1, y1)), ((side - (x1 - x0)) // 2, (side - (y1 - y0)) // 2))
        frame.resize((args.size, args.size), Image.LANCZOS).save(args.out / f"{name}.png")
        report["views"][name] = {"box": [x0, y0, x1, y1], "width": x1 - x0, "height": y1 - y0}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
