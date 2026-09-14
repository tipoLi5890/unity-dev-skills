#!/usr/bin/env python3
"""Compare two perf-window JSONL files and say whether the change helped.

Reads the records FrameSampler.cs appends (schema "perf-window/1"), aligns
baseline and candidate windows by label, and prints one row per metric with the
delta, the percentage and a flag.

Exit codes, so a script can gate on this:

  0  compared, nothing regressed beyond the threshold
  1  usage error, missing file, or a line that is not a perf window
  2  at least one metric regressed beyond the threshold
  3  the two sides are not comparable (different run mode, graphics device,
     screen size, vsync or warm-up) and --allow-mode-mismatch was not given

Examples:

  python3 compare_windows.py --show after.jsonl
  python3 compare_windows.py before.jsonl after.jsonl
  python3 compare_windows.py before.jsonl after.jsonl --label hazard-lane \\
      --counters "Render/*,Game/*" --threshold 5 --format md

Standard library only.
"""

import argparse
import fnmatch
import json
import statistics
import sys

FRAME_STATS = ("median", "p95", "max")
COMPARABILITY_KEYS = ("mode", "nullGraphics", "screen", "vsync")


# ---------------------------------------------------------------- loading


def load(path):
    """Return the list of perf-window records in one JSONL file."""
    records = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError as exc:
                    raise SystemExit(
                        "%s:%d is not JSON: %s" % (path, lineno, exc))
                if not isinstance(rec, dict) or "frameTime" not in rec:
                    raise SystemExit(
                        "%s:%d is not a perf window (no frameTime); delete the "
                        "file and re-run rather than comparing mixed content"
                        % (path, lineno))
                records.append(rec)
    except IOError as exc:
        raise SystemExit("cannot read %s: %s" % (path, exc))
    if not records:
        raise SystemExit("%s holds no windows — the run wrote nothing" % path)
    return records


def by_label(records, label):
    if label:
        picked = [r for r in records if r.get("label") == label]
        if not picked:
            raise SystemExit(
                "no window labelled %r; the file has: %s"
                % (label, ", ".join(sorted({r.get("label", "") for r in records}))))
        return {label: picked}
    grouped = {}
    for rec in records:
        grouped.setdefault(rec.get("label", ""), []).append(rec)
    return grouped


def fingerprint(rec):
    run = rec.get("run", {})
    parts = ["%s=%s" % (k, run.get(k)) for k in COMPARABILITY_KEYS]
    parts.append("warmup=%s" % rec.get("warmup"))
    return " ".join(parts)


def comparability_errors(name, windows):
    """A side whose own windows disagree is already not one measurement."""
    prints = {fingerprint(w) for w in windows}
    if len(prints) > 1:
        return ["%s mixes instruments across its own windows: %s"
                % (name, " | ".join(sorted(prints)))]
    return []


# ---------------------------------------------------------------- values


def frame_value(rec, stat):
    return rec.get("frameTime", {}).get(stat)


def counter_value(rec, key, wanted):
    """Return (value, stat-actually-used) for one counter in one window."""
    entry = rec.get("counters", {}).get(key)
    if not isinstance(entry, dict):
        return None, wanted
    if entry.get("kind") == "cumulative":
        return entry.get("delta"), "delta"
    stat = wanted
    if stat not in entry:
        stat = "median" if "median" in entry else None
    if stat is None:
        return None, wanted
    return entry.get(stat), stat


def aggregate(values):
    """Median across windows of the same label, plus the spread between them."""
    clean = [v for v in values if isinstance(v, (int, float))]
    if not clean:
        return None, 0.0
    middle = statistics.median(clean)
    # The median of an even number of windows is their mean, which turns counts
    # into floats. Keep a count looking like a count.
    if all(isinstance(v, int) for v in clean) and float(middle).is_integer():
        middle = int(middle)
    return middle, max(clean) - min(clean)


def counter_keys(windows, globs):
    keys = set()
    for rec in windows:
        keys.update(rec.get("counters", {}).keys())
    if not globs:
        return sorted(keys)
    return sorted(k for k in keys
                  if any(fnmatch.fnmatch(k, g) for g in globs))


def split_globs(text):
    return [g.strip() for g in (text or "").split(",") if g.strip()]


# ---------------------------------------------------------------- compare


def flag_for(base, cand, higher_better, threshold):
    if base is None and cand is None:
        return "missing-both", None
    if base is None:
        return "missing-left", None
    if cand is None:
        return "missing-right", None
    if base == 0 and cand == 0:
        return "zero-both", 0.0
    if base == 0:
        return ("better" if higher_better else "REGRESSION"), None
    pct = (cand - base) / abs(base) * 100.0
    if pct == 0:
        return "same", 0.0
    improved = pct > 0 if higher_better else pct < 0
    if abs(pct) <= threshold:
        return ("same" if improved else "worse"), pct
    return ("better" if improved else "REGRESSION"), pct


def compare_label(label, left, right, args):
    """Build the metric rows for one label. Returns (rows, notes)."""
    rows, notes = [], []
    higher = split_globs(args.higher_better)

    for stat in FRAME_STATS:
        base, base_spread = aggregate([frame_value(r, stat) for r in left])
        cand, cand_spread = aggregate([frame_value(r, stat) for r in right])
        flag, pct = flag_for(base, cand, False, args.threshold)
        rows.append({"counter": "frameTime", "stat": stat, "unit": "ms",
                     "baseline": base, "candidate": cand,
                     "delta": None if base is None or cand is None else cand - base,
                     "pct": pct, "flag": flag,
                     "spread": max(base_spread, cand_spread)})

    base_hitch, _ = aggregate([r.get("frameTime", {}).get("hitches") for r in left])
    cand_hitch, _ = aggregate([r.get("frameTime", {}).get("hitches") for r in right])
    flag, pct = flag_for(base_hitch, cand_hitch, False, args.threshold)
    rows.append({"counter": "frameTime", "stat": "hitches", "unit": "n",
                 "baseline": base_hitch, "candidate": cand_hitch,
                 "delta": None if base_hitch is None or cand_hitch is None
                          else cand_hitch - base_hitch,
                 "pct": pct, "flag": flag, "spread": 0.0})

    globs = split_globs(args.counters)
    keys = sorted(set(counter_keys(left, globs)) | set(counter_keys(right, globs)))
    for key in keys:
        left_vals, used = [], args.stat
        for rec in left:
            value, used = counter_value(rec, key, args.stat)
            left_vals.append(value)
        right_vals = []
        for rec in right:
            value, used_r = counter_value(rec, key, args.stat)
            right_vals.append(value)
            if value is not None:
                used = used_r
        base, base_spread = aggregate(left_vals)
        cand, cand_spread = aggregate(right_vals)
        is_higher_better = any(fnmatch.fnmatch(key, g) for g in higher)
        flag, pct = flag_for(base, cand, is_higher_better, args.threshold)
        rows.append({"counter": key, "stat": used, "unit": "",
                     "baseline": base, "candidate": cand,
                     "delta": None if base is None or cand is None else cand - base,
                     "pct": pct, "flag": flag,
                     "spread": max(base_spread, cand_spread)})

    if len(left) > 1 or len(right) > 1:
        notes.append("%d baseline window(s) and %d candidate window(s) for %s — "
                     "each number is the median across them" % (len(left), len(right), label))
    wide = [r for r in rows if r["spread"] and r["baseline"] and
            r["spread"] > abs(r["baseline"]) * 0.10]
    for row in wide:
        notes.append("%s %s varies by %s across windows on one side — the run is not "
                     "repeatable enough to read a %s%% change"
                     % (row["counter"], row["stat"], fmt(row["spread"]), plain(args.threshold)))
    return rows, notes


# ---------------------------------------------------------------- output


def fmt(value):
    if value is None:
        return "-"
    if isinstance(value, float):
        if abs(value) >= 1000:
            return "%.0f" % value
        return "%.2f" % value
    return str(value)


def plain(value):
    """A threshold reads as `10`, not `10.00`, when it appears inside a sentence."""
    return ("%g" % value) if isinstance(value, float) else str(value)


def fmt_pct(pct):
    if pct is None:
        return "-"
    return "%+.1f%%" % pct


def render_table(rows, markdown):
    head = ["counter", "stat", "baseline", "candidate", "delta", "%", "flag"]
    body = [[r["counter"], r["stat"], fmt(r["baseline"]), fmt(r["candidate"]),
             fmt(r["delta"]), fmt_pct(r["pct"]), r["flag"]] for r in rows]
    widths = [max(len(head[i]), *(len(row[i]) for row in body)) if body else len(head[i])
              for i in range(len(head))]
    out = []
    if markdown:
        out.append("| " + " | ".join(head) + " |")
        out.append("|" + "|".join("---" for _ in head) + "|")
        for row in body:
            out.append("| " + " | ".join(row) + " |")
    else:
        out.append("  ".join(head[i].ljust(widths[i]) for i in range(len(head))))
        out.append("  ".join("-" * widths[i] for i in range(len(head))))
        for row in body:
            out.append("  ".join(row[i].ljust(widths[i]) for i in range(len(head))))
    return "\n".join(out)


def summary_line(rows):
    ft = next((r for r in rows if r["counter"] == "frameTime" and r["stat"] == "p95"), None)
    parts = []
    if ft and ft["baseline"] is not None and ft["candidate"] is not None:
        parts.append("frameTime p95 %s → %s ms (%s)"
                     % (fmt(ft["baseline"]), fmt(ft["candidate"]), fmt_pct(ft["pct"])))
    movers = [r for r in rows
              if r["counter"] != "frameTime" and r["pct"] is not None and abs(r["pct"]) > 0]
    movers.sort(key=lambda r: abs(r["pct"]), reverse=True)
    for row in movers[:2]:
        parts.append("%s %s %s → %s"
                     % (row["counter"], row["stat"], fmt(row["baseline"]), fmt(row["candidate"])))
    return " · ".join(parts) if parts else "nothing moved"


def show(path):
    for rec in load(path):
        run = rec.get("run", {})
        ft = rec.get("frameTime", {})
        print("%-16s mode=%-18s frames=%-4s warmup=%-3s ft_med=%s ft_p95=%s ft_max=%s "
              "hitches=%s counters=%d missing=%d zero=%d"
              % (rec.get("label", ""), run.get("mode"), rec.get("frames"),
                 rec.get("warmup"), fmt(ft.get("median")), fmt(ft.get("p95")),
                 fmt(ft.get("max")), ft.get("hitches"),
                 len(rec.get("counters", {})), len(rec.get("missing", [])),
                 len(rec.get("zeroAll", []))))
    return 0


# ---------------------------------------------------------------- main


def build_parser():
    p = argparse.ArgumentParser(
        description="Compare two perf-window JSONL files and flag regressions.",
        epilog="exit 0 clean · 1 usage · 2 regression · 3 not comparable")
    p.add_argument("baseline", nargs="?", help="JSONL written before the change")
    p.add_argument("candidate", nargs="?", help="JSONL written after the change")
    p.add_argument("--show", metavar="FILE",
                   help="print one line per window in FILE and exit")
    p.add_argument("--label", help="compare only windows with this label")
    p.add_argument("--stat", default="median",
                   choices=["mean", "median", "p90", "p95", "p99", "max", "min",
                            "sum", "delta"],
                   help="counter statistic to compare (default: median); cumulative "
                        "counters always compare their delta")
    p.add_argument("--threshold", type=float, default=10.0,
                   help="percent change treated as noise (default: 10)")
    p.add_argument("--counters", default="",
                   help='comma-separated globs, e.g. "Render/*,Game/*" (default: all)')
    p.add_argument("--higher-better", default="",
                   help="comma-separated globs whose increase is an improvement")
    p.add_argument("--format", default="table", choices=["table", "md", "json"])
    p.add_argument("--allow-mode-mismatch", action="store_true",
                   help="compare anyway when the two sides used different instruments")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.show:
        return show(args.show)
    if not args.baseline or not args.candidate:
        build_parser().print_usage(sys.stderr)
        sys.stderr.write("give BASELINE and CANDIDATE, or --show FILE\n")
        return 1

    left_all = load(args.baseline)
    right_all = load(args.candidate)
    left_groups = by_label(left_all, args.label)
    right_groups = by_label(right_all, args.label)

    problems = (comparability_errors("baseline", left_all) +
                comparability_errors("candidate", right_all))
    left_print = fingerprint(left_all[0])
    right_print = fingerprint(right_all[0])
    if left_print != right_print:
        problems.append("baseline  %s" % left_print)
        problems.append("candidate %s" % right_print)
    if problems and not args.allow_mode_mismatch:
        print("NOT COMPARABLE — these are two different instruments, not two "
              "measurements of one thing:")
        for problem in problems:
            print("  " + problem.replace("\n", "\n  "))
        print("Re-run the baseline on the instrument you are using now, or pass "
              "--allow-mode-mismatch and say so in the report.")
        return 3

    shared = [lbl for lbl in left_groups if lbl in right_groups]
    if not shared:
        print("no label appears in both files: baseline has %s, candidate has %s"
              % (sorted(left_groups), sorted(right_groups)))
        return 1

    regressed = False
    payload = []
    for label in sorted(shared):
        rows, notes = compare_label(label, left_groups[label], right_groups[label], args)
        if any(r["flag"] == "REGRESSION" for r in rows):
            regressed = True
        payload.append({"label": label, "rows": rows, "notes": notes,
                        "summary": summary_line(rows)})

    if args.format == "json":
        print(json.dumps({"baseline": args.baseline, "candidate": args.candidate,
                          "instrument": right_print, "threshold": args.threshold,
                          "regressed": regressed, "labels": payload},
                         indent=2, sort_keys=True))
        return 2 if regressed else 0

    for block in payload:
        print("== %s  (%s)" % (block["label"], right_print))
        print(render_table(block["rows"], args.format == "md"))
        for note in block["notes"]:
            print("note: " + note)
        print("[COMPARE] " + block["summary"])
        print("")

    print("[COMPARE] result=%s threshold=%s%%"
          % ("REGRESSION" if regressed else "clean", plain(args.threshold)))
    return 2 if regressed else 0


if __name__ == "__main__":
    sys.exit(main())
