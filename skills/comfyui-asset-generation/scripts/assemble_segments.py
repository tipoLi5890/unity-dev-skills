#!/usr/bin/env python3
"""assemble_segments.py — join generated segments into one clip that flows: still ends trimmed, short crossfades.

A segment generated between a first and a last keyframe usually stands still
for a while at both ends. Joined end to end, those pauses read as hesitation.
This trims every segment to its moving span (keeping a few still frames either
side), crossfades neighbours over a few frames and writes one H.264 / AAC MP4.

usage:
    assemble_segments.py OUT.mp4 SEG [SEG ...] [| SEG ...] [options]

SEG is a clip path, optionally followed by suffixes in any order:
    :keep    use the whole clip, untrimmed (a segment already right as it is)
    :xN      play N times faster after trimming; N < 1 slows it down, with the
             in-betweens motion-compensated (`minterpolate`) so no frame is
             simply shown twice
    :toN     use frames 0..N-1 only (cuts a wobble at the end), then trim
    :holdS   freeze the first frame for S seconds before the segment plays; the
             hold is silent, so the sound stays in sync with the motion
    :rA-B    use frames A..B-1 exactly, no auto-trim; list one clip twice with
             two ranges to cut a still middle out of it
A lone `|` between two segments is a chapter break: a longer crossfade there.

options:
    --head 4 --tail 6      still frames kept before and after the moving span
    --fade 6               crossfade length in frames between segments
    --chapter-fade 12      crossfade length at a `|`
    --thr 0.6 --rel 0.15   a frame moves when its difference (video_motion.py's
                           measure) is above max(thr, rel x the clip's peak)
    --timeline FILE        JSON list of where each segment starts and ends in
                           the output, in seconds, for captions or a re-score

Every segment must have the first one's frame size and frame rate (`xfade`
needs both). A segment with no audio stream gets silence; with none anywhere,
the output has no audio. Never crossfade a segment generated from one version of
a keyframe into a segment generated from another: the moved objects show twice.

Exit codes: 0 written; 1 ffmpeg failed to render; 2 bad arguments, an
unreadable clip, mismatched segments, or ffmpeg / ffprobe missing.

Requires Python 3.9+, numpy, ffmpeg and ffprobe on PATH; imports
`video_motion.py` from this directory.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_motion import ReadError, differences, fps_of, frames, has_audio, need, size_of  # noqa: E402


class Usage(ValueError):
    """A segment argument that cannot be parsed or used."""


def parse_segment(text: str) -> dict:
    seg = {"path": text, "keep": False, "speed": 1.0, "to": None, "range": None, "hold": 0.0}
    path = text
    while ":" in Path(path).name:
        path, opt = path.rsplit(":", 1)
        try:
            if opt == "keep":
                seg["keep"] = True
            elif opt.startswith("hold"):
                seg["hold"] = float(opt[4:])
            elif opt.startswith("x"):
                seg["speed"] = float(opt[1:])
            elif opt.startswith("to"):
                seg["to"] = int(opt[2:])
            elif opt.startswith("r") and "-" in opt:
                a, b = (int(x) for x in opt[1:].split("-"))
                seg["range"] = (a, b)
            else:
                raise Usage(f"unknown option :{opt} in {text}")
        except ValueError as exc:
            if isinstance(exc, Usage):
                raise
            raise Usage(f"bad value in :{opt} of {text}") from exc
    if seg["speed"] <= 0 or seg["hold"] < 0:
        raise Usage(f"speed must be > 0 and hold >= 0 in {text}")
    seg["path"] = path
    return seg


def trim_points(path, thr: float, rel: float, head: int, tail: int, limit: int) -> tuple[int, int]:
    f = frames(path)[:limit]
    d = differences(f)
    n = len(f)
    if len(d) == 0:
        return 0, n
    cut = max(thr, rel * float(d.max()))
    moving = [i for i, x in enumerate(d) if x > cut]
    if not moving:
        return 0, n
    return max(0, moving[0] - head), min(n, moving[-1] + 2 + tail)


def frame_count(path) -> int:
    need("ffprobe")
    done = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                           "stream=nb_read_frames", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return int(done.stdout.strip().split(",")[0])
    except ValueError as exc:
        raise ReadError(f"{path}: could not count its frames") from exc


def build(args) -> tuple[list[str], list[tuple[float, float]], list[dict], float]:
    segments, fades, chapter = [], [], False
    for token in args.segs:
        if token == "|":
            chapter = True
            continue
        seg = parse_segment(token)
        if not Path(seg["path"]).is_file():
            raise Usage(f"no such clip: {seg['path']}")
        if segments:
            fades.append(args.chapter_fade if chapter else args.fade)
        chapter = False
        segments.append(seg)
    if not segments:
        raise Usage("no segments given")

    fps = fps_of(segments[0]["path"])
    size = size_of(segments[0]["path"])
    for seg in segments[1:]:
        if abs(fps_of(seg["path"]) - fps) > 1e-3 or size_of(seg["path"]) != size:
            raise Usage(f"{seg['path']}: {size_of(seg['path'])} at {fps_of(seg['path']):g} fps, but the first "
                        f"segment is {size} at {fps:g} fps; xfade needs one size and one frame rate")
    any_audio = any(has_audio(seg["path"]) for seg in segments)

    inputs, filters, durations = [], [], []
    for i, seg in enumerate(segments):
        n = frame_count(seg["path"])
        if seg["to"] is not None:
            n = min(n, seg["to"])
        if seg["range"] is not None:
            s, e = seg["range"][0], min(n, seg["range"][1])
            kind = "range"
        elif seg["keep"]:
            s, e, kind = 0, n, "keep"
        else:
            s, e = trim_points(seg["path"], args.thr, args.rel, args.head, args.tail, n)
            kind = "trim"
        if e - s < 2:
            raise Usage(f"{seg['path']}: frames {s}-{e} leave nothing to play")
        speed, hold = seg["speed"], seg["hold"]
        dur = (e - s) / fps / speed + hold
        durations.append(dur)
        print(f"{kind} {Path(seg['path']).name}: frames {s}-{e} of {n}"
              f"{f' x{speed:g}' if speed != 1 else ''}{f' hold {hold:g}s' if hold else ''} -> {dur:.2f}s")
        inputs += ["-i", seg["path"]]
        if speed > 1:
            vs = f",setpts=PTS/{speed:g},fps={fps:g}"
        elif speed < 1:
            vs = f",setpts=PTS/{speed:g},minterpolate=fps={fps:g}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
        else:
            vs = ""
        hv = f",tpad=start_mode=clone:start_duration={hold:g}" if hold else ""
        filters.append(f"[{i}:v]trim=start_frame={s}:end_frame={e},setpts=PTS-STARTPTS{vs}{hv},"
                       f"format=yuv420p,settb=AVTB[v{i}]")
        if any_audio:
            norm = f"aformat=sample_rates=48000:channel_layouts=stereo,atrim=end={dur:.4f}[a{i}]"
            if has_audio(seg["path"]):
                tempo = f",atempo={speed:g}" if speed != 1 else ""
                delay = f",adelay={round(hold * 1000)}:all=1" if hold else ""
                filters.append(f"[{i}:a]atrim=start={s / fps:.4f},asetpts=PTS-STARTPTS{tempo}{delay},apad,{norm}")
            else:
                filters.append(f"anullsrc=channel_layout=stereo:sample_rate=48000,{norm}")

    for k, fade in enumerate(fades):
        fd = fade / fps
        if fd >= durations[k] or fd >= durations[k + 1]:
            raise Usage(f"a {fade}-frame crossfade is longer than segment {k + 1} or {k + 2}")

    vlast, alast, acc = "v0", "a0", durations[0]
    spans = [(0.0, durations[0])]
    for k in range(1, len(segments)):
        fd = fades[k - 1] / fps
        spans.append((acc - fd, acc - fd + durations[k]))
        filters.append(f"[{vlast}][v{k}]xfade=transition=fade:duration={fd:.4f}:offset={acc - fd:.4f}[x{k}]")
        if any_audio:
            filters.append(f"[{alast}][a{k}]acrossfade=d={fd:.4f}[y{k}]")
        vlast, alast, acc = f"x{k}", f"y{k}", acc + durations[k] - fd

    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
           "-map", f"[{vlast}]"]
    cmd += ["-map", f"[{alast}]", "-c:a", "aac", "-b:a", "192k"] if any_audio else ["-an"]
    cmd += ["-r", f"{fps:g}", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(args.out)]
    return cmd, spans, segments, acc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("out")
    parser.add_argument("segs", nargs="+", help="CLIP[:keep][:xN][:toN][:holdS][:rA-B], or | for a chapter break")
    parser.add_argument("--head", type=int, default=4)
    parser.add_argument("--tail", type=int, default=6)
    parser.add_argument("--fade", type=int, default=6)
    parser.add_argument("--chapter-fade", type=int, default=12)
    parser.add_argument("--thr", type=float, default=0.6)
    parser.add_argument("--rel", type=float, default=0.15)
    parser.add_argument("--timeline", help="Write a JSON list of each segment's start and end in the output")
    args = parser.parse_args()
    try:
        need("ffmpeg")
        cmd, spans, segments, total = build(args)
    except (Usage, ReadError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        print(f"ERROR ffmpeg failed: {done.stderr.strip()[:600]}", file=sys.stderr)
        return 1
    print(f"wrote {args.out} ~{total:.2f}s")
    if args.timeline:
        rows = [{"clip": Path(seg["path"]).name, "path": seg["path"], "start": round(a, 3), "end": round(b, 3)}
                for seg, (a, b) in zip(segments, spans)]
        Path(args.timeline).write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {args.timeline}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
