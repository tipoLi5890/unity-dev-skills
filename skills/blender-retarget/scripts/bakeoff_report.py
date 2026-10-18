#!/usr/bin/env python3
"""bakeoff_report.py — one markdown table comparing character routes clip by clip.

Each route (fit and play Generic, Humanoid, a per-clip bake, ...) is measured on the same
clips by clip_metrics.py. This joins those reports into one table: a row per metric, a column per
route, each cell the clips' values in order ("0.36 / 0.84 / 0.94"), a value that misses its
limit in bold, and a footer row counting each route's failed cells.

usage:
    bakeoff_report.py --route "Fit=idle.json,forehand.json" --route "Humanoid=a1.json,a2.json"
                      [--metrics METRICS.json] [--out REPORT.md]
    bakeoff_report.py selftest            (or --selftest)

--route NAME=FILE[,FILE...]   clip_metrics.py reports, the same clips in the same order for every
                              route; a report that was refused (exit 2) is an error here too.
--metrics METRICS.json        which numbers to show, as
                              [{"label": "added slide p95", "path": "foot_slide_added_m.p95",
                                "scale": 100, "unit": "cm", "digits": 2, "limit": 1.5}, ...]
                              `path` is dotted into each report; `limit` (after `scale`) is an
                              upper bound; omit it for an ungated row. Default: added slide p95
                              and max (cm, 1.5 / 3), absolute slide p95 (cm, ungated), limb
                              direction p95 (deg, 2), arm pose error p95 (%, ungated).

The clip names come from the first route's reports (`clip`); a route whose clips differ in
number or name is refused. Exit codes: 0 written and every gated cell passed; 1 written, some cell
failed; 2 refused input (a missing or unreadable report, a refused report, clips that differ,
a metric path absent from a report). Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

DEFAULT_METRICS = [
    {"label": "added slide p95", "path": "foot_slide_added_m.p95", "scale": 100, "unit": "cm",
     "digits": 2, "limit": 1.5},
    {"label": "added slide max", "path": "foot_slide_added_m.max", "scale": 100, "unit": "cm",
     "digits": 2, "limit": 3.0},
    {"label": "absolute slide p95 (not gated)", "path": "foot_slide_m.p95", "scale": 100,
     "unit": "cm", "digits": 2},
    {"label": "limb direction error p95", "path": "limb_direction_error_deg.p95", "scale": 1,
     "unit": "°", "digits": 4, "limit": 2.0},
    {"label": "arm pose error p95", "path": "arm_pose_error_pct.p95", "scale": 1, "unit": "%",
     "digits": 2},
]


class Refused(Exception):
    pass


def dig(doc: dict, path: str):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise Refused(f"metric path {path!r} not in report for clip {doc.get('clip')!r}")
        cur = cur[part]
    if not isinstance(cur, (int, float)):
        raise Refused(f"metric path {path!r} is not a number")
    return float(cur)


def load_routes(specs: list) -> list:
    routes = []
    for spec in specs:
        if "=" not in spec:
            raise Refused(f"--route {spec!r}: expected NAME=FILE[,FILE...]")
        name, files = spec.split("=", 1)
        reports = []
        for f in [x for x in files.split(",") if x]:
            try:
                doc = json.loads(Path(f).read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise Refused(f"{f}: {e}") from e
            if "refused" in doc:
                raise Refused(f"{f}: the measurement was refused: {doc['refused']}")
            reports.append(doc)
        if not reports:
            raise Refused(f"--route {name!r} has no report")
        routes.append((name.strip(), reports))
    if not routes:
        raise Refused("no --route given")
    clips = [r.get("clip") for r in routes[0][1]]
    for name, reports in routes[1:]:
        if [r.get("clip") for r in reports] != clips:
            raise Refused(f"route {name!r} measured clips {[r.get('clip') for r in reports]}, "
                          f"expected {clips}")
    return routes


def render(routes: list, metrics: list) -> tuple:
    clips = [str(r.get("clip")) for r in routes[0][1]]
    head = ["Metric (" + " / ".join(clips) + ")"] + [n for n, _ in routes]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    fails = {n: 0 for n, _ in routes}
    for m in metrics:
        scale, digits, limit = m.get("scale", 1), m.get("digits", 2), m.get("limit")
        label = m["label"] + (f" (≤ {limit} {m.get('unit', '')})".replace(" )", ")")
                              if limit is not None else "")
        row = [label]
        for name, reports in routes:
            cells = []
            for rep in reports:
                v = dig(rep, m["path"]) * scale
                s = f"{v:.{digits}f}"
                if limit is not None and v > limit:
                    s = f"**{s}**"
                    fails[name] += 1
                cells.append(s)
            row.append(" / ".join(cells) + (f" {m['unit']}" if m.get("unit") else ""))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("| failed cells | " + " | ".join(str(fails[n]) for n, _ in routes) + " |")
    return "\n".join(lines) + "\n", fails


def run(argv) -> tuple:
    p = argparse.ArgumentParser(prog="bakeoff_report.py")
    p.add_argument("--route", action="append", default=[])
    p.add_argument("--metrics")
    p.add_argument("--out")
    a = p.parse_args(argv)
    try:
        metrics = DEFAULT_METRICS
        if a.metrics:
            try:
                metrics = json.loads(Path(a.metrics).read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise Refused(f"{a.metrics}: {e}") from e
        table, fails = render(load_routes(a.route), metrics)
    except Refused as e:
        return 2, json.dumps({"refused": str(e)})
    if a.out:
        Path(a.out).write_text(table, encoding="utf-8")
    return (1 if any(fails.values()) else 0), table


# ------------------------------------------------------------------------------------ selftest
def _rep(clip, add_p95, add_max, abs_p95, limb, arm):
    return {"clip": clip, "foot_slide_added_m": {"p95": add_p95, "max": add_max},
            "foot_slide_m": {"p95": abs_p95}, "limb_direction_error_deg": {"p95": limb},
            "arm_pose_error_pct": {"p95": arm}}


EXPECTED = """| Metric (idle / forehand) | Fit | Humanoid |
|---|---|---|
| added slide p95 (≤ 1.5 cm) | 0.36 / 0.84 cm | 1.13 / **2.71** cm |
| added slide max (≤ 3.0 cm) | 0.59 / 0.97 cm | 1.78 / **3.08** cm |
| absolute slide p95 (not gated) | 1.89 / 4.14 cm | 1.60 / 3.91 cm |
| limb direction error p95 (≤ 2.0 °) | 0.0002 / 0.0002 ° | 1.5500 / **4.3800** ° |
| arm pose error p95 | 0.28 / 0.54 % | 2.50 / 8.20 % |
| failed cells | 0 | 3 |
"""


def selftest() -> int:
    checks, failed = 0, []

    def check(name, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failed.append(name)

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        files = {
            "f1": _rep("idle", .0036, .0059, .0189, .0002, .28),
            "f2": _rep("forehand", .0084, .0097, .0414, .0002, .54),
            "h1": _rep("idle", .0113, .0178, .0160, 1.55, 2.5),
            "h2": _rep("forehand", .0271, .0308, .0391, 4.38, 8.2),
            "x2": _rep("smash", .0084, .0097, .0414, .0002, .54),
        }
        for k, v in files.items():
            (d / f"{k}.json").write_text(json.dumps(v))
        fit = f"Fit={d / 'f1.json'},{d / 'f2.json'}"
        hum = f"Humanoid={d / 'h1.json'},{d / 'h2.json'}"
        code, text = run(["--route", fit, "--route", hum, "--out", str(d / "r.md")])
        check("one route fails: exit 1", code == 1)
        check("table matches the expected text", text == EXPECTED)
        check("--out written", (d / "r.md").read_text() == EXPECTED)
        code, _ = run(["--route", fit])
        check("all pass: exit 0", code == 0)
        code, _ = run(["--route", fit, "--route", f"Other={d / 'h1.json'},{d / 'x2.json'}"])
        check("different clips: exit 2", code == 2)
        code, _ = run(["--route", f"Fit={d / 'missing.json'}"])
        check("missing report: exit 2", code == 2)
        (d / "ref.json").write_text(json.dumps({"ok": False, "refused": "toe_l missing"}))
        code, _ = run(["--route", f"Fit={d / 'ref.json'}"])
        check("refused report: exit 2", code == 2)
        (d / "m.json").write_text(json.dumps([{"label": "x", "path": "no.such"}]))
        code, _ = run(["--route", fit, "--metrics", str(d / "m.json")])
        check("absent metric path: exit 2", code == 2)
        check("no route: exit 2", run([])[0] == 2)
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": checks,
                      "failed": failed}))
    return 0 if not failed else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["selftest"], ["--selftest"]):
        return selftest()
    code, text = run(argv)
    print(text, end="" if text.endswith("\n") else "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
