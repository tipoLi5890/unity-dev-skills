#!/usr/bin/env python3
"""video_motion.py — measure how a generated clip moves, and repair a clip animated on twos.

A clip can pass every probe (codec, size, duration, a contact sheet of stills)
and still look sluggish on playback: a second or more of nothing at the head and
the tail, or motion "on twos", where every other frame repeats the one before it
so half the frames stand still. Neither shows on a contact sheet. This measures
both per clip, and rebuilds the held frames of a clip on twos.

usage:
    video_motion.py profile CLIP [CLIP ...] [--thr 0.6] [--curve] [--max-stall PCT] [--json]
    video_motion.py smooth IN.mp4 OUT.mp4 [--ratio 0.35] [--thr 0.6] [--to N]

profile   one line per clip: duration, the still head, the moving span and the
          still tail (seconds); stall% = frames inside the moving span that barely
          differ from the frame before; the median and peak per-frame difference
          inside the span; jerk = peak / median (one sudden jump reads high).
          --curve adds a sparkline of every per-frame difference. --max-stall
          turns stall% into a gate. --json prints one object per clip instead.
smooth    drops the held frames inside the moving span and lets ffmpeg's
          motion-compensated `minterpolate` rebuild in-betweens at the original
          timestamps, so the frame count and the duration stay the same. Audio
          is carried through, trimmed to match. --to N keeps the first N frames
          only, cutting a wobble at the end in the same pass. It re-profiles the
          result and prints stall% before and after.

The measure: every frame is scaled to 224x128 grayscale (area filter) and its
difference is the mean absolute difference from the previous frame, on 0-255.
A frame "moves" above --thr. The default 0.6 is the value one project used on
1344x768 clips of a few objects sliding across a still, evenly lit scene; it
was not swept. It is not a constant: a small subject on a large still
background moves less of the frame, noise and grain move all of it, and the
downscale changes with the source aspect. Retune it per project by running
`profile --curve` on a clip already judged by eye. A held frame (smooth) is one
whose difference is under --ratio times the larger difference beside it, with
that neighbour above --thr.

Exit codes: 0 done; 1 a clip exceeded --max-stall (profile), or ffmpeg failed
to write (smooth); 2 a clip could not be read, or ffmpeg / ffprobe is missing.

Requires Python 3.9+, numpy, and ffmpeg + ffprobe on PATH (smooth needs the
`minterpolate` filter). `assemble_segments.py` imports the measure from here.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

W, H = 224, 128


class ReadError(RuntimeError):
    """A clip that cannot be measured, or a missing tool."""


def need(tool: str) -> None:
    if shutil.which(tool) is None:
        raise ReadError(f"{tool} is not on PATH")


def frames(path) -> np.ndarray:
    """Every frame of the clip as a (n, 128, 224) float32 grayscale array."""
    need("ffmpeg")
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
           "-vf", f"scale={W}:{H}:flags=area,format=gray", "-f", "rawvideo", "-"]
    done = subprocess.run(cmd, capture_output=True)
    if done.returncode != 0 or not done.stdout:
        raise ReadError(f"{path}: ffmpeg could not decode it: "
                        f"{done.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return np.frombuffer(done.stdout, np.uint8).reshape(-1, H, W).astype(np.float32)


def probe(path, entries: str, stream: str = "v:0") -> str:
    need("ffprobe")
    done = subprocess.run(["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", entries,
                           "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    if done.returncode != 0:
        raise ReadError(f"{path}: ffprobe could not read it: {done.stderr.strip()[:200]}")
    return done.stdout.strip()


def fps_of(path) -> float:
    raw = probe(path, "stream=r_frame_rate")
    try:
        num, den = raw.split("/")
        return float(num) / float(den)
    except (ValueError, ZeroDivisionError) as exc:
        raise ReadError(f"{path}: no video frame rate ({raw!r})") from exc


def size_of(path) -> tuple[int, int]:
    raw = probe(path, "stream=width,height")
    try:
        w, h = raw.splitlines()[0].split(",")[:2]
        return int(w), int(h)
    except (ValueError, IndexError) as exc:
        raise ReadError(f"{path}: no video size ({raw!r})") from exc


def has_audio(path) -> bool:
    return bool(probe(path, "stream=index", stream="a"))


def differences(f: np.ndarray) -> np.ndarray:
    """d[i] = mean |frame i+1 - frame i|."""
    if len(f) < 2:
        return np.zeros(0, np.float32)
    return np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))


def profile(path, thr: float) -> dict:
    f = frames(path)
    fps = fps_of(path)
    d = differences(f)
    n = len(f)
    out = {"clip": str(path), "frames": n, "fps": round(fps, 3), "duration": round(n / fps, 3)}
    moving = np.where(d > thr)[0]
    if len(moving) == 0:
        return {**out, "moves": False, "d": d}
    first, last = int(moving[0]), int(moving[-1]) + 1
    span = d[first:last]
    stalls = int((span <= thr).sum())
    med = float(np.median(span[span > thr]))
    peak = float(span.max())
    return {**out, "moves": True, "d": d,
            "head_s": round(first / fps, 3), "move_s": round((last - first) / fps, 3),
            "tail_s": round((n - 1 - last) / fps, 3),
            "stall_pct": round(100.0 * stalls / max(1, len(span)), 1),
            "median": round(med, 3), "peak": round(peak, 3), "jerk": round(peak / med, 2) if med else 0.0}


def held_frames(f: np.ndarray, ratio: float, thr: float) -> list[int]:
    """Indices of frames that repeat the previous one inside motion (animation on twos)."""
    d = differences(f)
    drop = []
    for i in range(1, len(f) - 1):
        here = d[i - 1]                                   # frame i against frame i-1
        around = max(d[i - 2] if i >= 2 else 0.0, d[i])   # the steps before and after it
        if around > thr and here < ratio * around:
            drop.append(i)
    return drop


def sparkline(d: np.ndarray) -> str:
    bars = " ▁▂▃▄▅▆▇█"
    top = max(float(d.max()) if len(d) else 0.0, 1e-6)
    return "".join(bars[min(8, int(x / top * 8.999))] for x in d)


def cmd_profile(args) -> int:
    status = 0
    if not args.json:
        print(f"{'clip':40s} {'dur':>6s} {'head':>5s} {'move':>5s} {'tail':>5s} {'stall%':>6s} "
              f"{'med':>5s} {'peak':>6s} {'jerk':>5s}")
    for clip in args.clips:
        try:
            p = profile(clip, args.thr)
        except ReadError as exc:
            print(f"ERROR {exc}", file=sys.stderr)
            return 2
        over = args.max_stall is not None and p["moves"] and p["stall_pct"] > args.max_stall
        if over:
            status = max(status, 1)
        if args.json:
            row = {k: v for k, v in p.items() if k != "d"}
            if args.curve:
                row["curve"] = [round(float(x), 3) for x in p["d"]]
            if args.max_stall is not None:
                row["stall_ok"] = not over
            print(json.dumps(row))
            continue
        name = str(clip)[-40:]
        if not p["moves"]:
            print(f"{name:40s} {p['duration']:6.2f}  never moves above --thr {args.thr:g}")
        else:
            print(f"{name:40s} {p['duration']:6.2f} {p['head_s']:5.2f} {p['move_s']:5.2f} {p['tail_s']:5.2f} "
                  f"{p['stall_pct']:6.1f} {p['median']:5.2f} {p['peak']:6.2f} {p['jerk']:5.1f}"
                  f"{'  STALL over ' + format(args.max_stall, 'g') + '%' if over else ''}")
        if args.curve:
            print("   " + sparkline(p["d"]))
    return status


def cmd_smooth(args) -> int:
    try:
        f = frames(args.src)
        fps = fps_of(args.src)
        audio = has_audio(args.src)
        before = profile(args.src, args.thr)
    except ReadError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    if args.to:
        f = f[:args.to]
    n = len(f)
    drop = held_frames(f, args.ratio, args.thr)
    print(f"{Path(args.src).name}: {n} frames, dropping {len(drop)} held frames, interpolating")
    select = f"lt(n\\,{n})" + "".join(f"*not(eq(n\\,{i}))" for i in drop)
    # minterpolate holds back the last input frame; one cloned frame at the end keeps the count at n
    vf = (f"select='{select}',tpad=stop=1:stop_mode=clone,"
          f"minterpolate=fps={fps:g}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
          f"trim=end_frame={n},format=yuv420p")
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(args.src), "-vf", vf, "-r", f"{fps:g}",
           "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p"]
    cmd += ["-af", f"atrim=end={n / fps:.4f}", "-c:a", "aac", "-b:a", "192k"] if audio else ["-an"]
    done = subprocess.run(cmd + ["-movflags", "+faststart", str(args.dst)], capture_output=True, text=True)
    if done.returncode != 0:
        print(f"ERROR ffmpeg failed: {done.stderr.strip()[:400]}", file=sys.stderr)
        return 1
    after = profile(args.dst, args.thr)
    print(f"wrote {args.dst}: {after['frames']} frames, stall% {before.get('stall_pct', '-')} -> "
          f"{after.get('stall_pct', '-')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("profile", help="Measure head, tail, stall% and jerk per clip")
    p.add_argument("clips", nargs="+")
    p.add_argument("--thr", type=float, default=0.6, help="Mean difference above which a frame moves (default 0.6)")
    p.add_argument("--curve", action="store_true", help="Also print every per-frame difference")
    p.add_argument("--max-stall", type=float, metavar="PCT", help="Exit 1 when a clip's stall%% is above PCT")
    p.add_argument("--json", action="store_true", help="One JSON object per clip")
    s = sub.add_parser("smooth", help="Rebuild the held frames of a clip animated on twos")
    s.add_argument("src")
    s.add_argument("dst")
    s.add_argument("--ratio", type=float, default=0.35, help="Held = difference under RATIO x its neighbour's")
    s.add_argument("--thr", type=float, default=0.6)
    s.add_argument("--to", type=int, default=0, help="Keep only the first N frames")
    args = parser.parse_args()
    try:
        return cmd_profile(args) if args.command == "profile" else cmd_smooth(args)
    except ReadError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
