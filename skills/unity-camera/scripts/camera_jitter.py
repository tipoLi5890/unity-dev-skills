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

--key resolves like journey_report.py (the same pasted resolve(): pos/vel component, exact
dotted path, then custom, counts, ready, top level), so --key vel.x reads one component. A meta
line stamped "timeline/1" that lacks what the schema requires exits 2; "schema": 1 or no stamp is
read with a WARN on stderr.

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
import os
import subprocess
import sys
import tempfile

AXES = ("x", "y", "z")
MISSING = object()


# >>> shared:timeline_resolve  (tools/shared-blocks/timeline_resolve.py; edit there, paste here)
def resolve(sample, key):
    """Value of `key` in one timeline/1 sample, or MISSING. One order, pasted unchanged into
    journey_report.py, jump_report.py and camera_jitter.py: pos.x|y|z and vel.x|y|z (or .0 to .2),
    then an exact dotted path (custom.gateDist, ready.laneMesh), then custom.<key>, counts.<key>,
    ready.<key>, then a top-level field."""
    if "." in key:
        head, rest = key.split(".", 1)
        if head in ("pos", "vel"):
            vec = sample.get(head)
            idx = {"x": 0, "y": 1, "z": 2, "0": 0, "1": 1, "2": 2}.get(rest)
            if isinstance(vec, list) and idx is not None and idx < len(vec):
                return vec[idx]
            return MISSING
        container = sample.get(head)
        if isinstance(container, dict) and rest in container:
            return container[rest]
        return MISSING
    for bucket in ("custom", "counts", "ready"):
        container = sample.get(bucket)
        if isinstance(container, dict) and key in container:
            return container[key]
    if key in sample:
        return sample[key]
    return MISSING


def stamp_problems(path, meta, samples, end):
    """(warnings, errors) for the timeline/1 stamp. A meta line stamped "timeline/1" must carry
    what the schema requires (journey; n, frame and t on every sample unless it is
    {"n": k, "playing": false}; samples and milestones on the end line, samples counted right):
    a miss is a writer bug and an error. The 0.34 stamp `"schema": 1` is read as timeline/1 with
    one warning, for one release; no stamp, or another one, is read the same way with a warning."""
    stamp = meta.get("schema") if isinstance(meta, dict) else None
    if stamp == "timeline/1":
        errors = []
        if not meta.get("journey"):
            errors.append("%s: the meta line has no journey" % path)
        for s in samples:
            need = ("n",) if s.get("playing") is False else ("n", "frame", "t")
            lost = [k for k in need if k not in s]
            if lost:
                errors.append("%s: sample n=%s has no %s" % (path, s.get("n"), ", ".join(lost)))
                break
        if end is not None:
            if "samples" not in end or "milestones" not in end:
                errors.append("%s: the end line needs samples and milestones" % path)
            elif end["samples"] != len(samples):
                errors.append("%s: the end line counts %s samples, the file has %d"
                              % (path, end["samples"], len(samples)))
        return [], errors
    if stamp == 1 and not isinstance(stamp, bool):
        return ["WARN %s: old stamp \"schema\": 1, read as timeline/1" % path], []
    return ["WARN %s: no timeline/1 stamp on the meta line (schema=%r), read as timeline/1"
            % (path, stamp)], []
# <<< shared:timeline_resolve


def read_timeline(path):
    """(meta, samples, end line or None). Raises OSError or ValueError on an unreadable file, and
    ValueError on a timeline/1 file that breaks its schema; prints a WARN for an old or no stamp."""
    meta, samples, end = {}, [], None
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
                end = row
            elif "n" in row:
                samples.append(row)
    warnings, errors = stamp_problems(path, meta, samples, end)
    for w in warnings:
        print(w, file=sys.stderr)
    if errors:
        raise ValueError("; ".join(errors))
    return meta, samples, end


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
        meta, samples, end = read_timeline(args.timeline)
        ended = end is not None
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


# ---------------------------------------------------------------- selftest

SCRIPT = "camera_jitter"


def contract_out(path, case):
    """Copy a timeline a selftest wrote to where tools/check-contracts.py validates it against
    schemas/timeline-1.json: $UNITY_DEV_CONTRACT_OUT, else a fixed folder in the temp dir. Prints
    `selftest-output: PATH`. The selftest's own checks stay the gate; this is the hand-off."""
    import shutil
    out = os.environ.get("UNITY_DEV_CONTRACT_OUT") or os.path.join(tempfile.gettempdir(), "unity-dev-contract-out")
    os.makedirs(out, exist_ok=True)
    dest = os.path.join(out, "%s__%s.timeline.jsonl" % (SCRIPT, case))
    shutil.copyfile(path, dest)
    print("selftest-output: %s" % dest)


def _offsets(kind, count=120):
    """Offsets of a camera behind a runner speeding up and slowing down: `ease` lags and catches up
    smoothly; `beat` adds a push forward on every other frame, the two-clock pattern."""
    out = []
    for i in range(count):
        lag = 0.4 * (1 - abs(i - count / 2) / (count / 2))
        if kind == "beat":
            lag += 0.02 if i % 2 else -0.02
        out.append([round(lag, 3), 0.0, round(-2 * lag, 3)])
    return out


def _write(path, offsets, schema="timeline/1", key="camOffset"):
    lines = [{"meta": True, "schema": schema, "journey": "camera-side-run", "situation": "selftest"}]
    for n, off in enumerate(offsets):
        lines.append({"n": n, "frame": n, "t": round(n / 60, 4), "dt": 0.0167, "vel": [off[0], 0.0, 0.0],
                      "custom": {key: off}})
    lines.append({"end": True, "samples": len(offsets), "milestones": []})
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(x) + "\n" for x in lines))
    return path


def selftest():
    """Synthetic timelines in a temp dir: an easing camera passes, a beating one fails, a missing
    key fails, the old stamp warns, a broken timeline/1 file and bad flags are usage errors."""
    checks, failed = 0, []

    def check(name, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failed.append(name)

    def run(*args):
        r = subprocess.run([sys.executable, os.path.abspath(__file__), *args], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        run.stderr = r.stderr
        return r.returncode

    with tempfile.TemporaryDirectory(prefix="jitter-selftest-") as d:
        ease = _write(os.path.join(d, "ease.jsonl"), _offsets("ease"))
        check("an easing camera: exit 0", run(ease) == 0 and "WARN" not in run.stderr)
        contract_out(ease, "ease")
        check("a beating camera: exit 1", run(_write(os.path.join(d, "beat.jsonl"), _offsets("beat"))) == 1)
        check("a missing key: exit 1", run(ease, "--key", "noSuchKey") == 1)
        check("vel.x resolves a component", run(ease, "--key", "vel.x") == 0)
        old = _write(os.path.join(d, "old.jsonl"), _offsets("ease"), schema=1)
        check("the 0.34 stamp schema 1: exit 0, one WARN", run(old) == 0 and run.stderr.count("WARN") == 1)
        with open(ease, encoding="utf-8") as fh:
            bad = fh.read().replace('"samples": 120', '"samples": 7')
        with open(os.path.join(d, "count.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(bad)
        check("timeline/1 end line miscounts: exit 2", run(os.path.join(d, "count.jsonl")) == 2)
        with open(os.path.join(d, "broken.jsonl"), "w", encoding="utf-8") as fh:
            fh.write('{"meta": true}\nnot json\n')
        check("a line that is not JSON: exit 2", run(os.path.join(d, "broken.jsonl")) == 2)
        check("a negative --epsilon: exit 2", run(ease, "--epsilon", "-1") == 2)
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": checks, "failed": failed}))
    return 0 if not failed else 1


if __name__ == "__main__":
    if sys.argv[1:] in (["selftest"], ["--selftest"]):
        sys.exit(selftest())
    sys.exit(main())
