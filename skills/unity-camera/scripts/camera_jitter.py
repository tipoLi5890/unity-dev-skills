#!/usr/bin/env python3
"""camera_jitter.py — is the camera easing after the player, or beating against it?

Reads a journey timeline (unity-play-harness → reference/timeline-format.md), takes the
camera-to-player offset that resources/CameraProbe.cs registers as custom.camOffset, and
counts how often its frame-to-frame delta changes sign.

A camera that follows on the same clock as its target moves the offset one way for many
frames: it lags when the player accelerates and catches up afterwards. Two clocks — a body
stepped in FixedUpdate under a camera damped in LateUpdate — push the offset forward on the
frames that had a physics step and back on the frames that had none, so the delta flips
every few frames for as long as the player moves.

The measure, per axis:
  delta[i]  = offset[i] - offset[i-1]            samples with dt == 0 (paused) are skipped
  moving    = deltas with |delta| >= --epsilon   the rest is rest, and is not counted
  flip      = a moving delta whose sign differs from the previous moving delta's
  flip rate = flips / (moving - 1)               0 when moving < --min-moving

The timeline stores three decimals, so a delta of 0.001 is rounding; the default epsilon of
0.002 sits above it. The worst axis decides the exit code.

Examples:
  camera_jitter.py journeys/camera-side-run/timeline.jsonl
  camera_jitter.py timeline.jsonl --axis x --max-flip-rate 0.05
  camera_jitter.py timeline.jsonl --key custom.aimOffset --epsilon 0.01
  camera_jitter.py timeline.jsonl --json

Prints one [JITTER] line and one line per axis, or one JSON object with --json.
Exit codes: 0 fine · 1 flip rate over the limit, key missing, or no samples · 2 usage or IO error.
"""
import argparse
import json
import sys

AXES = ("x", "y", "z")
MISSING = object()


def resolve(sample, key):
    """Value of a dotted or bare key, or MISSING. Same order as journey_report.py:
    exact dotted path, then custom.<name>, counts.<name>, ready.<name>, then a top-level field."""
    if "." in key:
        head, rest = key.split(".", 1)
        container = sample.get(head)
        if isinstance(container, dict) and rest in container:
            return container[rest]
        return MISSING
    for bucket in ("custom", "counts", "ready"):
        container = sample.get(bucket)
        if isinstance(container, dict) and key in container:
            return container[key]
    return sample[key] if key in sample else MISSING


def read_timeline(path):
    """(meta, samples, ended). Raises OSError or ValueError on an unreadable file."""
    meta, samples, ended = {}, [], False
    with open(path, "r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError("line %d is not JSON: %s" % (number, e))
            if not isinstance(row, dict):
                raise ValueError("line %d is not a JSON object" % number)
            if row.get("meta"):
                meta = row
            elif row.get("end"):
                ended = True
            elif "n" in row:
                samples.append(row)
    return meta, samples, ended


def components(value):
    """A camOffset value as a list of floats: [x,y,z], [x,y] or a bare number. None if neither."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list) and value and all(
            isinstance(c, (int, float)) and not isinstance(c, bool) for c in value):
        return [float(c) for c in value]
    return None


def flip_stats(series, epsilon, min_moving):
    """flips, moving deltas, rate and the largest delta of one axis."""
    flips = moving = 0
    last_sign = 0
    largest = 0.0
    for previous, current in zip(series, series[1:]):
        delta = current - previous
        if abs(delta) < epsilon:
            continue
        sign = 1 if delta > 0 else -1
        if last_sign and sign != last_sign:
            flips += 1
        last_sign = sign
        moving += 1
        largest = max(largest, abs(delta))
    rate = 0.0 if moving < max(2, min_moving) else flips / float(moving - 1)
    return {"flips": flips, "moving": moving, "rate": round(rate, 4), "maxDelta": round(largest, 4)}


def analyse(samples, key, axes, epsilon, min_moving):
    """Per-axis stats plus the list of sample indices where the key was absent or unusable."""
    missing, rows = [], []
    for sample in samples:
        if sample.get("dt") == 0:
            continue                      # a paused frame carries no motion on either clock
        value = resolve(sample, key)
        parts = None if value is MISSING else components(value)
        if parts is None:
            missing.append(sample.get("n"))
            continue
        rows.append(parts)

    width = min((len(r) for r in rows), default=0)
    stats = {}
    for index, name in enumerate(AXES[:width]):
        if axes and name not in axes:
            continue
        stats[name] = flip_stats([r[index] for r in rows], epsilon, min_moving)
    return stats, missing, len(rows)


def build_parser():
    p = argparse.ArgumentParser(
        prog="camera_jitter.py",
        description="Count sign flips in the frame-to-frame delta of the camera-to-player offset.",
        epilog="Exit 0 fine, 1 over the limit / key missing / no samples, 2 usage or IO error.",
    )
    p.add_argument("timeline", metavar="TIMELINE", help="a timeline.jsonl written by JourneyRecorder")
    p.add_argument("--key", default="camOffset", metavar="KEY",
                   help="the sampled value to read (default: camOffset, resolved under custom{})")
    p.add_argument("--axis", action="append", choices=AXES, metavar="AXIS",
                   help="x, y or z; repeatable (default: every axis the value has)")
    p.add_argument("--max-flip-rate", type=float, default=0.1, metavar="RATE",
                   help="exit 1 when any axis flips more often than this (default 0.1)")
    p.add_argument("--epsilon", type=float, default=0.002, metavar="UNITS",
                   help="deltas smaller than this are rest, not motion (default 0.002)")
    p.add_argument("--min-moving", type=int, default=10, metavar="N",
                   help="fewer moving deltas than this reads as rate 0 (default 10)")
    p.add_argument("--json", action="store_true", help="print one JSON object instead of lines")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.max_flip_rate < 0 or args.epsilon < 0 or args.min_moving < 0:
        print("ERROR --max-flip-rate, --epsilon and --min-moving must not be negative", file=sys.stderr)
        return 2

    try:
        meta, samples, ended = read_timeline(args.timeline)
    except (OSError, ValueError) as e:
        print("ERROR could not read %s: %s" % (args.timeline, e), file=sys.stderr)
        return 2

    stats, missing, used = analyse(samples, args.key, args.axis, args.epsilon, args.min_moving)

    violations = []
    if not samples:
        violations.append("no samples in the timeline")
    if missing:
        violations.append("%s missing or not numeric in %d of %d samples (first n=%s)"
                          % (args.key, len(missing), len(samples), missing[0]))
    if samples and not missing and not used:
        violations.append("every sample has dt 0 - the run was paused throughout, nothing to measure")
    elif samples and not missing and not stats:
        violations.append("%s has no %s axis" % (args.key, "/".join(args.axis or AXES)))
    for name, s in stats.items():
        if s["rate"] > args.max_flip_rate:
            violations.append("%s.%s flip rate %.3f over %.3f (%d flips in %d moving frames)"
                              % (args.key, name, s["rate"], args.max_flip_rate, s["flips"], s["moving"]))

    worst = max((s["rate"] for s in stats.values()), default=0.0)
    result = {
        "journey": meta.get("journey"),
        "samples": len(samples),
        "used": used,
        "end": "ok" if ended else "missing",
        "key": args.key,
        "epsilon": args.epsilon,
        "maxFlipRate": args.max_flip_rate,
        "worstFlipRate": worst,
        "axes": stats,
        "violations": violations,
    }

    if args.json:
        print(json.dumps(result, separators=(",", ":")))
    else:
        print("[JITTER] violations=%d samples=%d journey=%s key=%s worstFlipRate=%.3f limit=%.3f end=%s"
              % (len(violations), len(samples), meta.get("journey"), args.key, worst,
                 args.max_flip_rate, result["end"]))
        for name, s in stats.items():
            print("  %s  flips=%d moving=%d rate=%.3f maxDelta=%.3f"
                  % (name, s["flips"], s["moving"], s["rate"], s["maxDelta"]))
        for v in violations:
            print("  VIOLATION " + v)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
