#!/usr/bin/env python3
"""merge_results.py — merge the NUnit3 reports of one suite split across test lanes into one verdict.

Each shard is the file one Editor wrote with -testResults: a `test-run` root carrying total,
passed, failed, inconclusive and skipped, and a `test-case` element per test with `fullname` and
`result`. The merge refuses to call a split run green unless every piece of it is accounted for:

  * every shard file exists, parses, and was written by THIS run (mtime >= --since);
  * every shard ran at least one test (total=0 means its filter or category matched nothing);
  * no test fullname appears in more than one shard (the split overlaps);
  * with --inventory, every test in the full-run report ran in some shard (the split has a gap);
  * no test ended inconclusive: Assert.Inconclusive keeps failed="0", and a gate that did not
    run verified nothing (the raw Editor itself exits 2 on an inconclusive test).

Any of those is the harness failing, and it outranks a red test: a merge with a missing piece
cannot give a verdict either way. Failures are still listed, because they are still real.
Inconclusive and skipped are counted and named beside failed, never folded into passed.
Skipped (an [Ignore]) is listed only: somebody chose it.

Prints the per-shard counts, the failures with the first line of each message, then ONE line:

  [MERGE] shards=N total=.. passed=.. failed=.. inconclusive=.. skipped=.. missing=.. dup=.. verdict=green|failed|harness

Exit codes: 0 every shard fresh, complete and green · 2 tests really failed (a verdict — do not
retry) · 3 the harness failed (a shard missing, unreadable, stale or empty; a duplicate; a test in
the inventory that ran nowhere; an inconclusive test; bad arguments) — nothing was verified as a
whole.

--allow-inconclusive lists inconclusive tests without failing the merge, for a suite where one
is expected (a platform-gated test). It is a decision about those tests, not a retry.

Examples:
  START=$(date +%s)          # before launching the first shard
  ...                        # the shards run, each writing its own -testResults file
  merge_results.py --since "$START" "$RUN/edit.xml" "$RUN/play-smoke.xml" "$RUN/play-full.xml"
  merge_results.py --since "$START" --inventory /tmp/courier_full_play.xml "$RUN"/play-*.xml

--inventory takes a report from an earlier unsplit run; give it once per platform when the shards
cover EditMode and PlayMode. Tests added since that run show up as extra= (information only);
tests deleted since that run show up as missing, so refresh the inventory after a full run.
"""
import argparse
import os
import sys
import xml.etree.ElementTree as ET

COUNTS = ("total", "passed", "failed", "inconclusive", "skipped")
LIST_LIMIT = 10          # names printed per category before "... and N more"
FAIL_LIMIT = 50


class Usage(argparse.ArgumentParser):
    """argparse exits 2 on a usage error, which here means "tests failed". Make it 3."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print("merge_results.py: error: " + message, file=sys.stderr)
        print("[MERGE] shards=0 total=0 passed=0 failed=0 inconclusive=0 skipped=0 missing=0 dup=0 "
              "verdict=harness")
        sys.exit(3)


def first_line(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:300]
    return ""


def case_message(case):
    for tag in ("failure/message", "reason/message"):
        node = case.find(tag)
        if node is not None and node.text and node.text.strip():
            return first_line(node.text)
    return ""


def read_report(path):
    """Returns (counts, cases) where cases is a list of (fullname, result, message)."""
    root = ET.parse(path).getroot()
    if root.tag != "test-run":
        raise ValueError("root element is <%s>, not <test-run>: not an NUnit3 report "
                         "(a JUnit conversion?)" % root.tag)
    cases = []
    for c in root.iter("test-case"):
        name = c.get("fullname") or c.get("name") or "?"
        cases.append((name, c.get("result") or "?", case_message(c)))
    counts = {}
    for k in COUNTS:
        v = root.get(k)
        if v is None:
            # Not Unity's shape; count the cases instead of trusting a missing attribute as zero.
            if k == "total":
                counts[k] = len(cases)
            else:
                counts[k] = sum(1 for _, r, _ in cases if r.lower() == k)
        else:
            counts[k] = int(v)
    return counts, cases


def inventory_names(paths, problems):
    names = set()
    for p in paths:
        if not os.path.isfile(p):
            problems.append("inventory %s: no such file" % p)
            continue
        try:
            _, cases = read_report(p)
        except (ET.ParseError, ValueError) as e:
            problems.append("inventory %s: unreadable (%s)" % (p, e))
            continue
        if not cases:
            problems.append("inventory %s: lists no test cases" % p)
        names.update(n for n, _, _ in cases)
    return names


def show(label, items, limit):
    for line in items[:limit]:
        print("  %s %s" % (label, line))
    if len(items) > limit:
        print("  %s ... and %d more" % (label, len(items) - limit))


def main():
    ap = Usage(description="Merge NUnit3 shard reports into one verdict (exit 0 / 2 / 3).")
    ap.add_argument("shards", nargs="+", help="the -testResults file of each shard")
    ap.add_argument("--since", type=int, default=None,
                    help="epoch seconds the run started; a shard older than this is stale")
    ap.add_argument("--inventory", action="append", default=[],
                    help="a full unsplit report whose tests must all appear in some shard "
                         "(repeat per platform)")
    ap.add_argument("--allow-inconclusive", action="store_true",
                    help="list inconclusive tests without failing the merge (default: exit 3, "
                         "a gate that did not run verified nothing)")
    args = ap.parse_intermixed_args()      # shard paths may come before or after the options

    problems = []                      # harness failures: each one forces verdict=harness
    totals = {k: 0 for k in COUNTS}
    seen = {}                          # fullname -> [shard paths]
    failures, inconclusive, skipped = [], [], []
    real = {}
    read = 0

    for path in args.shards:
        rp = os.path.realpath(path)
        if rp in real:
            problems.append("%s: the same file as %s, given twice" % (path, real[rp]))
            continue
        real[rp] = path
        if not os.path.isfile(path):
            problems.append("%s: no such file — that shard never wrote a report "
                            "(Unity did not start, or a test assembly did not compile)" % path)
            continue
        mtime = os.path.getmtime(path)
        if args.since is not None and mtime < args.since:
            problems.append("%s: stale — written %ds before this run started; it is a previous "
                            "run's report" % (path, int(args.since - mtime)))
            continue
        try:
            counts, cases = read_report(path)
        except ET.ParseError as e:
            problems.append("%s: unreadable (%s) — a report cut off mid-write?" % (path, e))
            continue
        except ValueError as e:
            problems.append("%s: %s" % (path, e))
            continue
        read += 1
        print("[SHARD] %s total=%d passed=%d failed=%d inconclusive=%d skipped=%d"
              % (path, counts["total"], counts["passed"], counts["failed"],
                 counts["inconclusive"], counts["skipped"]))
        if counts["total"] == 0:
            problems.append("%s: total=0 — its filter, category or assembly list matched no test"
                            % path)
        for k in COUNTS:
            totals[k] += counts[k]
        for name in sorted(set(n for n, _, _ in cases)):
            seen.setdefault(name, []).append(path)
        for name, result, msg in cases:
            r = result.lower()
            entry = "%s%s  [%s]" % (name, ("  — " + msg) if msg else "", os.path.basename(path))
            if r == "failed":
                failures.append(entry)
            elif r == "inconclusive":
                inconclusive.append(entry)
            elif r == "skipped":
                skipped.append(entry)

    dups = sorted(n for n, where in seen.items() if len(where) > 1)
    for n in dups:
        problems.append("duplicate: %s ran in %s" % (n, ", ".join(seen[n])))

    missing, extra = [], []
    if args.inventory:
        inv = inventory_names(args.inventory, problems)
        if inv:
            missing = sorted(inv - set(seen))
            extra = sorted(set(seen) - inv)
            if missing:
                problems.append("%d test(s) in the inventory ran in no shard — the split has a gap"
                                % len(missing))

    if totals["inconclusive"] > 0 and not args.allow_inconclusive:
        problems.append("%d test(s) inconclusive — a gate that did not run verified nothing "
                        "(--allow-inconclusive only when that is expected)"
                        % totals["inconclusive"])

    if args.since is None:
        print("  note: no --since — a previous run's report would pass for this run's")
    show("FAILED      ", failures, FAIL_LIMIT)
    show("INCONCLUSIVE", inconclusive, LIST_LIMIT)
    show("SKIPPED     ", skipped, LIST_LIMIT)
    show("MISSING     ", missing, LIST_LIMIT)
    if extra:
        print("  note: %d test(s) ran that the inventory does not list (added since it was "
              "written?) — information only" % len(extra))
    for p in problems:
        print("  HARNESS     " + p)

    red = totals["failed"] > 0
    if problems:
        verdict, code = "harness", 3
        if failures:
            print("  note: the %d failure(s) above are real; fix the harness and they will "
                  "still be there" % len(failures))
    elif red:
        verdict, code = "failed", 2
    else:
        verdict, code = "green", 0

    print("[MERGE] shards=%d total=%d passed=%d failed=%d inconclusive=%d skipped=%d missing=%d "
          "dup=%d verdict=%s" % (len(args.shards), totals["total"], totals["passed"],
                                 totals["failed"], totals["inconclusive"], totals["skipped"],
                                 len(missing), len(dups), verdict))
    return code


if __name__ == "__main__":
    sys.exit(main())
