#!/usr/bin/env python3
"""Normalize a motion-reference clip to an exact MiniMax H3 timeline."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


FPS = 24
MIN_FRAMES = 124
MAX_FRAMES = 362


class PreparationError(RuntimeError):
    pass


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)


def probe(path: Path, *, count_frames: bool = False) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate,nb_read_frames,duration",
        "-of",
        "json",
    ]
    if count_frames:
        command.insert(3, "-count_frames")
    command.append(str(path))
    return json.loads(run(command).stdout)


def has_audio(metadata: dict[str, Any]) -> bool:
    return any(stream.get("codec_type") == "audio" for stream in metadata.get("streams", []))


def duration_of(metadata: dict[str, Any], label: str) -> float:
    raw = metadata.get("format", {}).get("duration")
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise PreparationError(
            f"could not read a duration from {label}; remux it to a container "
            "ffprobe can measure, such as MP4 or MKV"
        ) from exc


def stream_duration(stream: dict[str, Any]) -> float | None:
    try:
        return float(stream.get("duration"))
    except (TypeError, ValueError):
        return None


def validate_frame_count(value: int) -> None:
    if not MIN_FRAMES <= value <= MAX_FRAMES:
        raise PreparationError(f"frames must be between {MIN_FRAMES} and {MAX_FRAMES}")
    if (value - 5) % 17:
        raise PreparationError("frames must follow the MiniMax H3 17k+5 grid")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a motion reference to 24 fps and an exact H3 frame count."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--frames", type=int, default=124)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--keep-audio",
        action="store_true",
        help="Keep the source audio track; the output is video-only by default",
    )
    args = parser.parse_args()

    validate_frame_count(args.frames)
    if not args.source.is_file():
        raise PreparationError(f"source is not a file: {args.source}")
    if args.output.suffix.lower() != ".mp4":
        raise PreparationError("output must use the .mp4 extension")
    if args.output.exists() and not args.overwrite:
        raise PreparationError(f"output already exists: {args.output}")
    for program in ("ffmpeg", "ffprobe"):
        if shutil.which(program) is None:
            raise PreparationError(f"required program is missing: {program}")

    source_metadata = probe(args.source)
    target_duration = args.frames / FPS
    required_duration = (args.frames + 2) / FPS
    source_duration = duration_of(source_metadata, "the source")
    if source_duration < required_duration:
        raise PreparationError(
            f"source is {source_duration:.3f}s but sampling {args.frames} frames at "
            f"{FPS} fps needs at least {required_duration:.3f}s of source "
            "(one frame of headroom on each end); choose a smaller valid --frames "
            "or a longer source"
        )
    keep_audio = args.keep_audio and has_audio(source_metadata)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if args.overwrite:
        command.append("-y")
    command.extend(["-i", str(args.source)])
    video_filter = f"fps={FPS},trim=end_frame={args.frames},setpts=PTS-STARTPTS"
    if keep_audio:
        command.extend(
            [
                "-filter_complex",
                f"[0:v]{video_filter}[v];"
                f"[0:a]atrim=duration={target_duration:.9f},asetpts=PTS-STARTPTS[a]",
                "-map",
                "[v]",
                "-map",
                "[a]",
            ]
        )
    else:
        command.extend(["-vf", video_filter, "-map", "0:v:0"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
        ]
    )
    if keep_audio:
        command.extend(["-c:a", "aac", "-b:a", "192k"])
    command.extend(["-movflags", "+faststart", str(args.output)])

    try:
        run(command)
    except subprocess.CalledProcessError as exc:
        raise PreparationError(exc.stderr.strip() or "ffmpeg failed") from exc

    result = probe(args.output, count_frames=True)
    video_stream = next(
        (s for s in result.get("streams", []) if s.get("codec_type") == "video"), None
    )
    if video_stream is None:
        raise PreparationError("output has no video stream")
    actual_frames = int(video_stream.get("nb_read_frames") or 0)
    if actual_frames != args.frames:
        raise PreparationError(
            f"output has {actual_frames} frames; expected exactly {args.frames}. "
            f"The source did not yield {args.frames} frames at {FPS} fps; lower "
            "--frames to a smaller valid value or use a longer source"
        )
    if video_stream.get("r_frame_rate") != f"{FPS}/1":
        raise PreparationError(f"output frame rate is not {FPS} fps")
    if args.output.stat().st_size == 0:
        raise PreparationError("output file is empty")
    if keep_audio:
        audio_stream = next(
            (s for s in result.get("streams", []) if s.get("codec_type") == "audio"), None
        )
        if audio_stream is None:
            raise PreparationError("audio was requested but the output has no audio stream")
        audio_duration = stream_duration(audio_stream)
        if audio_duration is not None and audio_duration < target_duration - 0.05:
            raise PreparationError(
                f"output audio is {audio_duration:.3f}s but the timeline is "
                f"{target_duration:.3f}s; the source audio track is shorter than the "
                "requested frame count, so rerun without --keep-audio or supply a "
                "source whose audio covers the whole clip"
            )

    print(
        json.dumps(
            {
                "output": str(args.output),
                "frames": actual_frames,
                "fps": FPS,
                "duration": duration_of(result, "the output"),
                "video_codec": video_stream.get("codec_name"),
                "has_audio": has_audio(result),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PreparationError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc))
