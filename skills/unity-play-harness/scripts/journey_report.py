#!/usr/bin/env python3
"""journey_report.py — check a journey timeline against invariants, and compare two runs.

Reads the JSONL a JourneyRecorder wrote (`reference/timeline-format.md`): one meta line, one
line per sampled frame, one end line. Prints `[REPORT] violations=N`, one line per violation
with the frame and the value that broke it, and a median/p95/max table for every numeric key.
With --before it adds a two-run comparison table.

Exit codes: 0 clean · 1 at least one violation · 2 usage or parse error.
A key that does not exist counts as a violation rather than crashing or being skipped — a
report that silently checks nothing is worse than no report.

Key paths resolve in this order, so the short name usually works:
  exact dotted path (pos.y, custom.gateDist, ready.laneMesh) → custom.<name> → counts.<name>
  → ready.<name> → the top-level key

Examples:
  journey_report.py --after run/timeline.jsonl --max speed:12 --window 'gateDist<2'
  journey_report.py --after run/timeline.jsonl --monotonic state:Idle,Launched,Approach,AtGate \\
      --ready-before arrival --together laneMesh,laneCollider --no-null cam
  journey_report.py --before before/timeline.jsonl --after after/timeline.jsonl --max speed:12
"""
import argparse
import json
import sys

MISSING = object()


# ---------------------------------------------------------------- loading


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


# ---------------------------------------------------------------- key access


def resolve(sample, key):
    """Value of `key` in one sample, or MISSING."""
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


def as_number(value):
    if isinstance(value, bool) or value is MISSING or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


# ---------------------------------------------------------------- windows


def parse_window(expr):
    """'gateDist<2' → a predicate over one sample. Also ==, !=, <=, >=, >."""
    for op in ("<=", ">=", "==", "!=", "<", ">"):
        if op in expr:
            key, raw = expr.split(op, 1)
            key, raw = key.strip(), raw.strip()
            try:
                wanted = float(raw)
                numeric = True
            except ValueError:
                wanted, numeric = raw.strip("'\""), False

            def predicate(sample, key=key, op=op, wanted=wanted, numeric=numeric):
                value = resolve(sample, key)
                if value is MISSING:
                    return False
                if numeric:
                    value = as_number(value)
                    if value is None:
                        return False
                else:
                    value = str(value)
                if op == "<":
                    return value < wanted
                if op == "<=":
                    return value <= wanted
                if op == ">":
                    return value > wanted
                if op == ">=":
                    return value >= wanted
                if op == "==":
                    return value == wanted
                return value != wanted

            return predicate
    raise ValueError("window %r has no comparison operator" % expr)


def split_window(spec, default_window):
    """'speed:12@gateDist<2' → ('speed:12', predicate)."""
    if "@" in spec:
        body, expr = spec.split("@", 1)
        return body, parse_window(expr)
    return spec, default_window


# ---------------------------------------------------------------- checks


def violation(sample, rule, detail):
    return {
        "rule": rule,
        "n": sample.get("n", -1) if sample else -1,
        "frame": sample.get("frame", -1) if sample else -1,
        "t": sample.get("t", 0.0) if sample else 0.0,
        "detail": detail,
    }


def check_bound(samples, spec, window, kind, label=None):
    key, _, raw = spec.partition(":")
    key = key.strip()
    if not key or not raw:
        raise ValueError("--%s wants KEY:VALUE, got %r" % (kind, spec))
    try:
        limit = float(raw)
    except ValueError:
        raise ValueError("--%s wants a number after the colon, got %r" % (kind, spec))
    spec = label or spec
    bad, seen = [], 0
    for sample in samples:
        if window and not window(sample):
            continue
        seen += 1
        value = resolve(sample, key)
        if value is MISSING:
            bad.append(violation(sample, "%s %s" % (kind, spec), "key %r is not in the sample" % key))
            continue
        number = as_number(value)
        if number is None:
            bad.append(violation(sample, "%s %s" % (kind, spec), "%s=%r is not a number" % (key, value)))
            continue
        if (kind == "max" and number > limit) or (kind == "min" and number < limit):
            bad.append(violation(sample, "%s %s" % (kind, spec), "%s=%.3f" % (key, number)))
    if seen == 0:
        bad.append(violation(None, "%s %s" % (kind, spec), "no sample matched the window"))
    return bad


def check_monotonic(samples, spec):
    key, _, raw = spec.partition(":")
    key, order = key.strip(), [v.strip() for v in raw.split(",") if v.strip()]
    if not key or not order:
        raise ValueError("--monotonic wants KEY:A,B,C, got %r" % spec)
    bad, highest = [], -1
    for sample in samples:
        value = resolve(sample, key)
        if value is MISSING or value is None:
            bad.append(violation(sample, "monotonic " + spec, "%s is missing" % key))
            continue
        text = str(value)
        if text not in order:
            bad.append(violation(sample, "monotonic " + spec,
                                 "%s=%r is not in [%s]" % (key, text, ",".join(order))))
            continue
        idx = order.index(text)
        if idx < highest:
            bad.append(violation(sample, "monotonic " + spec,
                                 "%s went back to %r after %r" % (key, text, order[highest])))
        else:
            highest = idx
    return bad


def ready_members(sample):
    ready = sample.get("ready")
    return ready if isinstance(ready, dict) else {}


def check_ready_before(samples, milestone, window):
    at = next((i for i, s in enumerate(samples) if s.get("milestone") == milestone), None)
    if at is None:
        return [violation(None, "ready-before " + milestone,
                          "milestone never happened in %d samples" % len(samples))]
    bad = []
    for sample in samples[: at + 1]:
        if window and not window(sample):
            continue
        members = ready_members(sample)
        if not members:
            bad.append(violation(sample, "ready-before " + milestone, "no readiness members in the sample"))
            continue
        allready = sample.get("allReady")
        if allready is None:
            allready = all(bool(v) for v in members.values())
        if allready:
            continue
        missing = sorted(name for name, ok in members.items() if not ok)
        bad.append(violation(sample, "ready-before " + milestone, "missing " + ",".join(missing)))
    return bad


def check_together(samples, spec):
    names = [n.strip() for n in spec.split(",") if n.strip()]
    if len(names) < 2:
        raise ValueError("--together wants at least two member names, got %r" % spec)
    bad = []
    for sample in samples:
        members = ready_members(sample)
        absent = [n for n in names if n not in members]
        if absent:
            bad.append(violation(sample, "together " + spec, "not a readiness member: " + ",".join(absent)))
            continue
        values = {n: bool(members[n]) for n in names}
        if len(set(values.values())) > 1:
            bad.append(violation(sample, "together " + spec,
                                 " ".join("%s=%s" % (n, str(v).lower()) for n, v in values.items())))
    return bad


def check_no_null(samples, key):
    bad = []
    for sample in samples:
        value = resolve(sample, key)
        if value is MISSING:
            bad.append(violation(sample, "no-null " + key, "key %r is not in the sample" % key))
        elif value is None:
            bad.append(violation(sample, "no-null " + key, "%s is null" % key))
    return bad


# ---------------------------------------------------------------- statistics


def percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = fraction * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def numeric_series(samples):
    """{display key: [values]} for every numeric key that appears in the samples."""
    series = {}
    skip = {"n", "frame", "schema"}
    for sample in samples:
        for key, value in sample.items():
            if key in skip or isinstance(value, dict) or isinstance(value, list):
                continue
            number = as_number(value)
            if number is not None:
                series.setdefault(key, []).append(number)
        for bucket in ("custom", "counts"):
            container = sample.get(bucket)
            if not isinstance(container, dict):
                continue
            for key, value in container.items():
                number = as_number(value)
                if number is not None:
                    label = key if key not in sample else "%s.%s" % (bucket, key)
                    series.setdefault(label, []).append(number)
    return series


def stats_of(values):
    return {
        "median": percentile(values, 0.5),
        "p95": percentile(values, 0.95),
        "max": max(values),
        "min": min(values),
        "n": len(values),
    }


# ---------------------------------------------------------------- output


def print_table(rows, headers):
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    line = "  " + "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line.rstrip())
    for row in rows:
        print(("  " + "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))).rstrip())


def report_violations(violations, per_rule):
    shown = {}
    for v in violations:
        count = shown.get(v["rule"], 0)
        if count < per_rule:
            print("  %-28s n=%-5s frame=%-7s t=%-8s %s"
                  % (v["rule"], v["n"], v["frame"], format_t(v["t"]), v["detail"]))
        shown[v["rule"]] = count + 1
    for rule, count in shown.items():
        if count > per_rule:
            print("  %-28s … %d more" % (rule, count - per_rule))


def format_t(value):
    try:
        return "%.3f" % float(value)
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------- main


def build_parser():
    p = argparse.ArgumentParser(
        prog="journey_report.py",
        description="Check a journey timeline against invariants, and compare two runs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit 0 clean, 1 violations, 2 usage or parse error.",
    )
    p.add_argument("--after", required=True, metavar="TIMELINE.jsonl",
                   help="the run to check (required)")
    p.add_argument("--before", metavar="TIMELINE.jsonl",
                   help="a previous run of the SAME journey, for the comparison table")
    p.add_argument("--monotonic", action="append", default=[], metavar="KEY:A,B,C",
                   help="the key only ever moves forward through these values (repeatable)")
    p.add_argument("--max", action="append", default=[], dest="maxima", metavar="KEY:VALUE[@WINDOW]",
                   help="upper bound on a numeric key (repeatable)")
    p.add_argument("--min", action="append", default=[], dest="minima", metavar="KEY:VALUE[@WINDOW]",
                   help="lower bound on a numeric key (repeatable)")
    p.add_argument("--window", metavar="EXPR",
                   help="restrict --max/--min/--ready-before to matching samples, e.g. 'gateDist<2'")
    p.add_argument("--ready-before", action="append", default=[], dest="ready_before", metavar="MILESTONE",
                   help="every readiness member is true at every sample up to this milestone")
    p.add_argument("--together", action="append", default=[], metavar="A,B",
                   help="these readiness members are never in disagreement (repeatable)")
    p.add_argument("--no-null", action="append", default=[], dest="no_null", metavar="KEY",
                   help="the key is never null and never absent (repeatable)")
    p.add_argument("--per-rule", type=int, default=5, metavar="N",
                   help="violations printed per rule before the count (default 5)")
    p.add_argument("--no-stats", action="store_true", help="skip the median/p95/max table")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        window = parse_window(args.window) if args.window else None
        meta, samples, end = load(args.after)
    except (OSError, ValueError) as e:
        print("ERROR %s" % e, file=sys.stderr)
        return 2

    violations = []
    try:
        for spec in args.monotonic:
            violations += check_monotonic(samples, spec)
        for spec in args.maxima:
            body, per_check = split_window(spec, window)
            violations += check_bound(samples, body, per_check, "max", label=spec)
        for spec in args.minima:
            body, per_check = split_window(spec, window)
            violations += check_bound(samples, body, per_check, "min", label=spec)
        for milestone in args.ready_before:
            violations += check_ready_before(samples, milestone, window)
        for spec in args.together:
            violations += check_together(samples, spec)
        for key in args.no_null:
            violations += check_no_null(samples, key)
    except ValueError as e:
        print("ERROR %s" % e, file=sys.stderr)
        return 2

    if not samples:
        violations.append(violation(None, "samples", "the timeline has no samples"))

    print("[REPORT] violations=%d samples=%d journey=%s situation=%s end=%s"
          % (len(violations), len(samples), meta.get("journey", "?"),
             meta.get("situation", "?"), "ok" if end else "missing"))
    if meta.get("params"):
        print("  params: " + " ".join("%s=%s" % (k, v) for k, v in sorted(meta["params"].items())))
    report_violations(violations, max(0, args.per_rule))

    series = numeric_series(samples)
    if series and not args.no_stats:
        rows = []
        for key in sorted(series):
            s = stats_of(series[key])
            rows.append([key, "%.3f" % s["median"], "%.3f" % s["p95"],
                         "%.3f" % s["max"], "%.3f" % s["min"], str(s["n"])])
        print()
        print_table(rows, ["key", "median", "p95", "max", "min", "n"])

    if args.before:
        try:
            before_meta, before_samples, _ = load(args.before)
        except (OSError, ValueError) as e:
            print("ERROR %s" % e, file=sys.stderr)
            return 2
        if before_meta.get("journey") and meta.get("journey") \
                and before_meta["journey"] != meta["journey"]:
            print("ERROR --before is journey %r, --after is %r — not comparable"
                  % (before_meta["journey"], meta["journey"]), file=sys.stderr)
            return 2
        before_series = numeric_series(before_samples)
        rows = []
        for key in sorted(set(before_series) & set(series)):
            a, b = stats_of(before_series[key]), stats_of(series[key])
            for stat in ("median", "p95", "max"):
                rows.append([key, stat, "%.3f" % a[stat], "%.3f" % b[stat],
                             "%+.3f" % (b[stat] - a[stat])])
        if rows:
            print()
            print_table(rows, ["key", "stat", "before", "after", "delta"])
        else:
            print("\n  no numeric key is present in both runs")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
