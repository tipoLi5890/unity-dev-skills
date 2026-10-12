#!/usr/bin/env python3
"""jump_report.py — measure the jump a journey actually performed, against the designed one.

Reads a timeline.jsonl written by the play harness's JourneyRecorder (one meta line, one line
per sampled frame carrying `t` and `pos`, one end line), finds every jump arc in the position
samples, and prints ONE JSON object: per arc the measured apex height and air time, and a
violation for each one outside tolerance of --apex / --air-time.

Arcs are cut on a grounded flag when the probe carries one (--grounded-key grounded), which
is the reliable way. Without it they are inferred from height alone: the body counts as
grounded while its height holds still, so a slope reads as airborne and a jump taken from one
is mis-measured. Register the flag.

Exit codes: 0 every checked arc is inside tolerance · 1 at least one violation · 2 usage,
IO or parse error.
A missing key counts as a violation, and so does a run with no jump in it or an --air-time
that no level-ground arc could be checked against: a report that measured nothing must not
read as a pass.

Examples:
  jump_report.py journeys/ledge-drop/timeline.jsonl --apex 2.85 --air-time 0.718
  jump_report.py run/timeline.jsonl --grounded-key grounded --apex 2.85 --tolerance 0.03
  jump_report.py run/timeline.jsonl --apex 1.2 --arc 2 --axis y --indent 2
  jump_report.py run/timeline.jsonl --grounded-key grounded --expect-arcs 3
"""
import argparse
import json
import sys

MISSING = object()
AXES = {"x": 0, "y": 1, "z": 2}


def load(path):
    """Return (meta, samples, end). Raises ValueError on an unreadable line."""
    meta, samples, end = {}, [], None
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError("%s:%d is not JSON: %s" % (path, lineno, e))
            if not isinstance(obj, dict):
                raise ValueError("%s:%d is not a JSON object" % (path, lineno))
            if obj.get("meta"):
                meta = obj
            elif obj.get("end"):
                end = obj
            else:
                samples.append(obj)
    return meta, samples, end


def resolve(sample, key):
    """Value of `key` in one sample, or MISSING. Same order as journey_report.py."""
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


def truthy(value):
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "grounded")
    return bool(value)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def median(values):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])


def still_mask(times, heights, still_time, still_eps):
    """True where the height holds within still_eps for still_time before OR after the sample."""
    n = len(times)
    out = [False] * n
    for k in range(n):
        lo = hi = heights[k]
        j = k
        while j + 1 < n and times[j + 1] - times[k] <= still_time:
            j += 1
            lo, hi = min(lo, heights[j]), max(hi, heights[j])
        forward = j > k and hi - lo <= still_eps
        lo = hi = heights[k]
        j = k
        while j - 1 >= 0 and times[k] - times[j - 1] <= still_time:
            j -= 1
            lo, hi = min(lo, heights[j]), max(hi, heights[j])
        backward = j < k and hi - lo <= still_eps
        out[k] = forward or backward
    return out


def find_arcs(rows, grounded, min_rise, still_eps, by_height):
    """Cut airborne runs out of the samples. rows: list of (sample, t, height)."""
    arcs, open_start, open_end = [], False, False
    n = len(rows)
    k = 0
    while k < n:
        if grounded[k]:
            k += 1
            continue
        start = k                      # first airborne sample
        while k < n and not grounded[k]:
            k += 1
        takeoff, landing = start - 1, k
        if takeoff < 0:
            open_start = True
            continue
        if landing >= n:
            open_end = True
            continue
        base = rows[takeoff][2]
        peak = max(rows[i][2] for i in range(takeoff, landing + 1))
        rise = peak - base
        descent = peak - rows[landing][2]
        delta = rows[landing][2] - base
        # Take-off and touch-down both happen between two samples, so the midpoint of each
        # bracket is the estimate and half the two intervals is what it cannot resolve.
        t_off = 0.5 * (rows[takeoff][1] + rows[takeoff + 1][1])
        t_land = 0.5 * (rows[landing - 1][1] + rows[landing][1])
        uncertainty = 0.5 * ((rows[takeoff + 1][1] - rows[takeoff][1])
                             + (rows[landing][1] - rows[landing - 1][1]))
        if rise >= min_rise and (not by_height or descent > still_eps):
            kind = "jump"
        elif by_height and rise >= min_rise:
            kind = "climb"
        elif delta <= -min_rise:
            kind = "fall"
        else:
            kind = "hop"
        sample = rows[takeoff][0]
        arcs.append({
            "kind": kind, "n": sample.get("n"), "frame": sample.get("frame"),
            "t_takeoff": round(t_off, 4), "apex_height": round(rise, 4),
            "air_time": round(t_land - t_off, 4), "air_time_uncertainty": round(uncertainty, 4),
            "landing_delta": round(delta, 4),
        })
    return arcs, open_start, open_end


def analyse(args):
    meta, samples, end = load(args.timeline)
    axis = AXES[args.axis]
    violations = []

    def violate(rule, detail, arc=None):
        violations.append({"rule": rule, "arc": arc, "detail": detail})

    rows, no_pos, no_time, no_flag, flags = [], 0, 0, 0, []
    for sample in samples:
        pos = sample.get("pos")
        height = number(pos[axis]) if isinstance(pos, list) and len(pos) > axis else None
        t = number(sample.get(args.clock))
        if height is None:
            no_pos += 1
            continue
        if t is None:
            no_time += 1
            continue
        if args.grounded_key:
            value = resolve(sample, args.grounded_key)
            if value is MISSING or value is None:
                no_flag += 1
                continue
            flags.append(truthy(value))
        rows.append((sample, t, height))

    if not samples:
        violate("samples", "the timeline has no samples")
    if no_pos:
        violate("key pos", "%d of %d samples carry no pos.%s — is the player registered with the probe?"
                % (no_pos, len(samples), args.axis))
    if no_time:
        violate("key " + args.clock, "%d of %d samples carry no %r"
                % (no_time, len(samples), args.clock))
    if no_flag:
        violate("key " + args.grounded_key,
                "%d of %d samples carry no %r — register it with GameProbe.Register"
                % (no_flag, len(samples), args.grounded_key))

    times = [row[1] for row in rows]
    heights = [row[2] for row in rows]
    intervals = [b - a for a, b in zip(times, times[1:]) if b > a]
    interval = median(intervals)

    by_height = not args.grounded_key
    grounded = still_mask(times, heights, args.still_time, args.still_eps) if by_height else flags
    arcs, open_start, open_end = find_arcs(rows, grounded, args.min_rise, args.still_eps,
                                           by_height)

    jumps = [a for a in arcs if a["kind"] == "jump"]
    for index, arc in enumerate(jumps, 1):
        arc["index"] = index
    if rows and not jumps:
        violate("arcs", "no jump arc in %d samples: nothing rose %.3g or more and came back "
                        "down — did the journey press jump?" % (len(rows), args.min_rise))
    if args.expect_arcs is not None and len(jumps) != args.expect_arcs:
        violate("expect-arcs", "found %d jump arcs, expected %d" % (len(jumps), args.expect_arcs))

    selected = jumps
    if args.arc is not None:
        selected = [a for a in jumps if a["index"] == args.arc]
        if jumps and not selected:
            violate("arc", "--arc %d but the run has %d jump arcs" % (args.arc, len(jumps)))

    air_checked = 0
    for arc in selected:
        checks = {}
        if args.apex is not None:
            allowed = args.tolerance * args.apex
            error = arc["apex_height"] - args.apex
            ok = abs(error) <= allowed + 1e-9
            checks["apex"] = {"expected": args.apex, "error": round(error, 4),
                              "allowed": round(allowed, 4), "ok": ok}
            if not ok:
                violate("apex", "measured %.3f, expected %.3f ± %.3f (frame %s)"
                        % (arc["apex_height"], args.apex, allowed, arc["frame"]), arc["index"])
        if args.air_time is not None:
            # --air-time describes a jump that lands at take-off height. An arc that lands on
            # a ledge or drops off one is a different flight, so it is not compared.
            level = abs(arc["landing_delta"]) <= max(args.still_eps * 2, 0.02 * arc["apex_height"])
            if level:
                air_checked += 1
                allowed = max(args.tolerance * args.air_time, arc["air_time_uncertainty"])
                error = arc["air_time"] - args.air_time
                ok = abs(error) <= allowed + 1e-9
                checks["air_time"] = {"expected": args.air_time, "error": round(error, 4),
                                      "allowed": round(allowed, 4), "ok": ok}
                if not ok:
                    violate("air-time", "measured %.3f s, expected %.3f ± %.3f (frame %s)"
                            % (arc["air_time"], args.air_time, allowed, arc["frame"]),
                            arc["index"])
            else:
                checks["air_time"] = {"skipped": "lands %.3f from take-off height"
                                                 % arc["landing_delta"]}
        arc["checks"] = checks
    if args.air_time is not None and selected and not air_checked:
        violate("air-time", "no selected arc lands at take-off height, so --air-time was "
                            "compared with nothing")

    return {
        "timeline": args.timeline,
        "journey": meta.get("journey"),
        "situation": meta.get("situation"),
        "end": "ok" if end else "missing",
        "samples": len(samples),
        "used_samples": len(rows),
        "sample_interval": round(interval, 4),
        "mode": "height" if by_height else "grounded-key",
        "expected": {"apex": args.apex, "air_time": args.air_time, "tolerance": args.tolerance},
        "arcs": jumps,
        "other_flights": [a for a in arcs if a["kind"] != "jump"],
        "open": {"starts_airborne": open_start, "ends_airborne": open_end},
        "violations": violations,
        "verdict": "fail" if violations else "ok",
    }


def build_parser():
    p = argparse.ArgumentParser(
        prog="jump_report.py",
        description="Find the jump arcs in a journey timeline and compare apex height and air "
                    "time with the designed values.",
        epilog="Exit 0 inside tolerance, 1 a violation (or nothing measured), 2 usage or "
               "parse error.",
    )
    p.add_argument("timeline", metavar="TIMELINE", help="a timeline.jsonl from JourneyRecorder")
    p.add_argument("--apex", type=float, default=None, metavar="H",
                   help="designed apex height above the take-off point, units")
    p.add_argument("--air-time", type=float, default=None, metavar="SECONDS",
                   help="designed air time of a jump that lands at take-off height")
    p.add_argument("--tolerance", type=float, default=0.05, metavar="FRACTION",
                   help="allowed relative error (default 0.05); air time is also allowed one "
                        "sample interval, which it cannot resolve below")
    p.add_argument("--grounded-key", default=None, metavar="KEY",
                   help="probe key that is true while grounded: grounded, custom.grounded")
    p.add_argument("--axis", choices=sorted(AXES), default="y",
                   help="which component of pos is height (default y)")
    p.add_argument("--clock", choices=("t", "ut"), default="t",
                   help="t: scaled game time, right for a jump (default); ut: unscaled")
    p.add_argument("--min-rise", type=float, default=0.2, metavar="H",
                   help="a flight rising less than this is a hop or a fall, not a jump "
                        "(default 0.2)")
    p.add_argument("--arc", type=int, default=None, metavar="N",
                   help="check only the Nth jump arc, counting from 1 (default: all)")
    p.add_argument("--expect-arcs", type=int, default=None, metavar="N",
                   help="require exactly this many jump arcs")
    p.add_argument("--still-time", type=float, default=0.15, metavar="SECONDS",
                   help="height mode: how long height must hold to count as grounded "
                        "(default 0.15)")
    p.add_argument("--still-eps", type=float, default=0.01, metavar="H",
                   help="height mode: how much height may move and still be 'holding' "
                        "(default 0.01)")
    p.add_argument("--indent", type=int, default=None, metavar="N",
                   help="pretty-print with this indent (default: one line)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.tolerance < 0:
        print("ERROR --tolerance must not be negative", file=sys.stderr)
        return 2
    for name in ("apex", "air_time"):
        value = getattr(args, name)
        if value is not None and value <= 0:
            print("ERROR --%s must be greater than zero" % name.replace("_", "-"),
                  file=sys.stderr)
            return 2
    try:
        result = analyse(args)
    except OSError as e:
        print("ERROR cannot read %s: %s" % (args.timeline, e), file=sys.stderr)
        return 2
    except ValueError as e:
        print("ERROR %s" % e, file=sys.stderr)
        return 2
    if args.indent is None:
        print(json.dumps(result, separators=(",", ":")))
    else:
        print(json.dumps(result, indent=args.indent))
    return 1 if result["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
