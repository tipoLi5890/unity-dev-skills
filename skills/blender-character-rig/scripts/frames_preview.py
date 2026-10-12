#!/usr/bin/env python3
"""frames_preview.py — turn rendered frames into a GIF and a contact sheet of key frames.

An action is judged twice: moving, and pose by pose. The GIF shows whether the
swing reads; the contact sheet puts the key frames side by side so an occluded
target, a prop through a face or a pose that never changed is plain.

    python3 scripts/frames_preview.py preview/ --prefix f_ --fps 24 \\
        --gif out/swing.gif --sheet out/swing_keys.png --keys 1,8,13,15,17,18,20,23,27,34

    # crop every sheet cell to the middle 60% of the frame width
    python3 scripts/frames_preview.py preview/ --sheet out/keys.png --keys 1,13,18 --crop 0.6

Frames are `<prefix><number>.png`; the number is the frame. An output that
already exists is deleted before anything is written, so a failed run cannot
leave the previous preview in its place.

Prints one JSON object. Exit codes: 0 written; 1 a requested key frame is not
among the frames, or the frames are not one size; 2 no frames, unreadable
input or bad usage.

Needs Pillow. Run it with an interpreter that has it; when none does, open the
key-frame PNGs directly instead of installing anything.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                     epilog="Exit codes: 0 written, 1 a gate failed, 2 unreadable input or usage.")
    parser.add_argument("frames_dir", type=Path)
    parser.add_argument("--prefix", default="f_")
    parser.add_argument("--fps", type=float, default=24.0)
    parser.add_argument("--gif", type=Path)
    parser.add_argument("--sheet", type=Path)
    parser.add_argument("--keys", default="", help="Comma-separated frame numbers for the sheet")
    parser.add_argument("--columns", type=int, default=5)
    parser.add_argument("--crop", type=float, default=1.0, help="Fraction of the frame width each sheet cell keeps")
    parser.add_argument("--cell-width", type=int, default=480)
    args = parser.parse_args()
    if not args.gif and not args.sheet:
        parser.error("nothing to write: pass --gif and/or --sheet")

    try:
        from PIL import Image
    except ImportError:
        print(json.dumps({"error": "Pillow is not available in this interpreter"}))
        return 2

    pattern = re.compile(re.escape(args.prefix) + r"(\d+)\.png$")
    found = {}
    if args.frames_dir.is_dir():
        for path in args.frames_dir.iterdir():
            match = pattern.match(path.name)
            if match:
                found[int(match.group(1))] = path
    if not found:
        print(json.dumps({"error": f"no {args.prefix}<number>.png frames in {args.frames_dir}"}))
        return 2

    for out in (args.gif, args.sheet):
        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.unlink(missing_ok=True)

    numbers = sorted(found)
    images = {n: Image.open(found[n]).convert("RGB") for n in numbers}
    sizes = {im.size for im in images.values()}
    report = {"frames": len(numbers), "range": [numbers[0], numbers[-1]], "size": list(next(iter(sizes)))}
    gaps = [n for n in range(numbers[0], numbers[-1] + 1) if n not in found]
    if len(sizes) != 1 or gaps:
        report["error"] = "frames differ in size" if len(sizes) != 1 else f"missing frames: {gaps}"
        print(json.dumps(report))
        return 1

    if args.gif:
        ordered = [images[n] for n in numbers]
        ordered[0].save(args.gif, save_all=True, append_images=ordered[1:],
                        duration=round(1000 / args.fps), loop=0)
        report["gif"] = str(args.gif)

    if args.sheet:
        keys = [int(k) for k in args.keys.split(",") if k.strip()] or numbers[:: max(1, len(numbers) // 10)]
        absent = [k for k in keys if k not in images]
        if absent:
            report["error"] = f"key frames not rendered: {absent}"
            print(json.dumps(report))
            return 1
        width, height = next(iter(sizes))
        keep = max(1, round(width * min(1.0, max(0.05, args.crop))))
        left = (width - keep) // 2
        cell_w = min(args.cell_width, keep)
        cell_h = round(height * cell_w / keep)
        columns = min(args.columns, len(keys))
        rows = -(-len(keys) // columns)
        sheet = Image.new("RGB", (cell_w * columns, cell_h * rows))
        for i, key in enumerate(keys):
            cell = images[key].crop((left, 0, left + keep, height)).resize((cell_w, cell_h))
            sheet.paste(cell, ((i % columns) * cell_w, (i // columns) * cell_h))
        sheet.save(args.sheet)
        report["sheet"] = str(args.sheet)
        report["keys"] = keys

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
