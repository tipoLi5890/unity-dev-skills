#!/usr/bin/env python3
"""camera_gate.py — reject a keyframe whose camera moved away from the first keyframe's.

Every keyframe of a segmented clip is meant to share one camera. The cheapest
sign that the image model invented a dolly or a tilt is a fixed scene line that
moved: the row where the back wall or the sky meets the floor. This reads that
row on the reference keyframe and on a candidate, in one column no object
crosses, and passes the candidate only when the two rows agree.

usage:
    camera_gate.py --ref K1.png CAND.png [--column 0.1] [--tol 6] [--size WxH]
                   [--dist 40] [--run 3]
    camera_gate.py selftest            (or --selftest)

The horizon row: take a 3-pixel strip at column = --column x width; the median
colour of that strip over the top 5% of rows is the "upper" colour; walk down
the strip and the horizon is the first row whose mean colour lies more than
--dist (RGB Euclidean distance, 0-255 scale) from it and stays so for --run
rows in a row. Pick a column where wall or sky meets floor in a clean line and
nothing stands in front of it, on the reference, by eye.

Pass when both images have the same size (and equal --size, when given) and
|cand row - ref row| <= --tol. Keep --tol under about 1% of the image height.

Prints one JSON line: pass, delta, tol, why, and for ref and cand the path,
size and horizon row. `which` names the image a failure belongs to ("ref",
"cand" or "both"), so a retry loop can tell a bad roll from a bad setup.

Exit codes: 0 pass; 2 fail (rows differ by more than --tol, or sizes differ);
3 cannot measure (an image unreadable, or no horizon found in it); 64 a usage
error (a bad or missing option), with a JSON line whose `which` is "args". Any
other code (1: a crash) printed no verdict; a retry loop stops on it.

Requires Python 3.9+, Pillow and numpy.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


USAGE = 64


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    """Usage errors leave the 0/2/3 verdict space: one JSON line, exit 64."""

    def error(self, message):
        raise UsageError(message)


class MeasureError(RuntimeError):
    def __init__(self, which: str, why: str):
        super().__init__(why)
        self.which = which
        self.why = why


def load(path: str, which: str) -> np.ndarray:
    try:
        with Image.open(path) as im:
            return np.asarray(im.convert("RGB"), dtype=np.float64)
    except Exception as e:  # noqa: BLE001 - any decode failure is "cannot measure"
        raise MeasureError(which, f"cannot read {path}: {e.__class__.__name__}")


def horizon_row(rgb: np.ndarray, column: float, dist: float, run: int) -> int | None:
    h, w, _ = rgb.shape
    x = min(max(int(round(column * (w - 1))), 0), w - 1)
    x0, x1 = max(0, x - 1), min(w, x + 2)
    strip = rgb[:, x0:x1, :].mean(axis=1)                      # (h, 3)
    top = max(1, int(round(h * 0.05)))
    upper = np.median(rgb[:top, x0:x1, :].reshape(-1, 3), axis=0)
    far = np.sqrt(((strip - upper) ** 2).sum(axis=1)) > dist
    streak = 0
    for y in range(top, h):
        streak = streak + 1 if far[y] else 0
        if streak >= run:
            return y - run + 1
    return None


def parse_size(s: str | None):
    if not s:
        return None
    try:
        w, h = s.lower().split("x")
        return [int(w), int(h)]
    except ValueError:
        raise UsageError(f"--size must look like 1344x768, got {s!r}")


def gate(ref: str, cand: str, column=0.1, tol=6, size=None, dist=40.0, run=3):
    """Return (exit_code, report dict)."""
    rep = {"pass": False, "delta": None, "tol": tol, "column": column, "why": "",
           "ref": {"path": ref}, "cand": {"path": cand}}
    try:
        a = load(ref, "ref")
        b = load(cand, "cand")
    except MeasureError as e:
        rep.update(which=e.which, why=e.why)
        return 3, rep
    rep["ref"]["size"] = [a.shape[1], a.shape[0]]
    rep["cand"]["size"] = [b.shape[1], b.shape[0]]
    if size and rep["ref"]["size"] != size:
        rep.update(which="ref", why=f"ref size {rep['ref']['size']} != --size {size}")
        return 2, rep
    if rep["cand"]["size"] != rep["ref"]["size"]:
        rep.update(which="cand", why=f"size {rep['cand']['size']} != ref {rep['ref']['size']}")
        return 2, rep
    ra = horizon_row(a, column, dist, run)
    rb = horizon_row(b, column, dist, run)
    rep["ref"]["horizon"], rep["cand"]["horizon"] = ra, rb
    if ra is None or rb is None:
        which = "both" if ra is None and rb is None else ("ref" if ra is None else "cand")
        rep.update(which=which, why="no horizon found in the column (try another --column or --dist)")
        return 3, rep
    rep["delta"] = rb - ra
    if abs(rb - ra) <= tol:
        rep.update(**{"pass": True, "why": "ok"})
        return 0, rep
    rep.update(which="cand", why=f"horizon moved {rb - ra:+d} px (tol {tol})")
    return 2, rep


# ------------------------------------------------------------------------------------ selftest
def _two_tone(path: Path, row: int, size=(400, 600), noise=0):
    w, h = size
    a = np.zeros((h, w, 3), dtype=np.uint8)
    a[:row] = (200, 210, 225)
    a[row:] = (110, 95, 70)
    if noise:
        rng = np.random.default_rng(7)
        a = np.clip(a.astype(int) + rng.integers(-noise, noise + 1, a.shape), 0, 255).astype(np.uint8)
    a[row - 40:, int(w * 0.6):int(w * 0.8)] = (30, 120, 200)   # an object, away from the column
    Image.fromarray(a).save(path)


def selftest() -> int:
    checks, failed = [], []
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        _two_tone(d / "k300.png", 300)
        _two_tone(d / "k306.png", 306, noise=6)
        _two_tone(d / "k320.png", 320)
        _two_tone(d / "small.png", 300, size=(400, 500))
        Image.new("RGB", (400, 600), (128, 128, 128)).save(d / "flat.png")
        (d / "junk.png").write_bytes(b"not an image")

        def check(name, args, code, extra=None):
            got, rep = gate(*args)
            ok = got == code and (extra is None or extra(rep))
            checks.append(name)
            if not ok:
                failed.append({"check": name, "exit": got, "report": rep})

        r = lambda n: str(d / n)  # noqa: E731
        check("300 vs 306 passes at tol 6", (r("k300.png"), r("k306.png")), 0,
              lambda p: p["ref"]["horizon"] == 300 and p["delta"] == 6)
        check("300 vs 320 fails", (r("k300.png"), r("k320.png")), 2,
              lambda p: p["delta"] == 20 and p["which"] == "cand")
        check("tol 20 lets 320 through", (r("k300.png"), r("k320.png"), 0.1, 20), 0)
        check("flat candidate exits 3", (r("k300.png"), r("flat.png")), 3, lambda p: p["which"] == "cand")
        check("flat reference exits 3", (r("flat.png"), r("k300.png")), 3, lambda p: p["which"] == "ref")
        check("size mismatch fails", (r("k300.png"), r("small.png")), 2, lambda p: "size" in p["why"])
        check("--size mismatch fails", (r("k300.png"), r("k306.png"), 0.1, 6, [1344, 768]), 2)
        check("--size match passes", (r("k300.png"), r("k306.png"), 0.1, 6, [400, 600]), 0)
        check("unreadable exits 3", (r("k300.png"), r("junk.png")), 3, lambda p: p["which"] == "cand")
        check("column through the object reads the object", (r("k300.png"), r("k300.png"), 0.7), 0,
              lambda p: p["ref"]["horizon"] == 260)
        for name, argv in (("--size 12", ["--ref", r("k300.png"), r("k306.png"), "--size", "12"]),
                           ("--column 2", ["--ref", r("k300.png"), r("k306.png"), "--column", "2"]),
                           ("no --ref", [r("k306.png")])):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                got = main(argv)
            line = json.loads(out.getvalue())
            checks.append(f"usage error {name}: exit 64")
            if got != USAGE or line.get("which") != "args":
                failed.append({"check": checks[-1], "exit": got, "report": line})
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": len(checks), "failed": failed}))
    return 0 if not failed else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["selftest"], ["--selftest"]):
        return selftest()
    p = Parser(description=__doc__.split("\n")[0])
    p.add_argument("--ref", required=True, help="the first keyframe")
    p.add_argument("cand", help="the candidate keyframe")
    p.add_argument("--column", type=float, default=0.1, help="column as a fraction of the width")
    p.add_argument("--tol", type=int, default=6, help="allowed |row difference| in px")
    p.add_argument("--size", help="required size WxH for both images")
    p.add_argument("--dist", type=float, default=40.0, help="RGB distance that marks the horizon")
    p.add_argument("--run", type=int, default=3, help="rows the change must persist")
    try:
        a = p.parse_args(argv)
        if not 0.0 <= a.column <= 1.0 or a.run < 1 or a.tol < 0:
            raise UsageError("--column must be in [0, 1], --run >= 1, --tol >= 0")
        size = parse_size(a.size)
    except UsageError as e:
        print(json.dumps({"pass": False, "which": "args", "why": str(e)}))
        return USAGE
    code, rep = gate(a.ref, a.cand, a.column, a.tol, size, a.dist, a.run)
    print(json.dumps(rep))
    return code


if __name__ == "__main__":
    sys.exit(main())
