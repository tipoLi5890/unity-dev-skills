#!/usr/bin/env python3
"""screen_smoothness.py — does a moving object stop and jump on screen?

Reads a JSONL log with one record per rendered frame and measures how evenly an object moves in
screen space. Built for a fast ball fed by snapshots from a fixed-rate simulation: when the
renderer runs ahead of the newest snapshot, plain interpolation parks the ball for a frame and it
jumps the next. Works for anything with a screen position: a ball, a character, a camera target.

Record, per frame (other keys are ignored):
  {"tick": 1234.5, "x": 812.3, "y": 401.9, "live": true, "event": false}
    tick   the render time in simulation ticks (or seconds; only differences are used)
    x, y   screen position in pixels
    live   optional, default true: the object is in play and on screen
    event  optional, default false: a hit, bounce or contact within the last ~0.1 s, where the
           speed genuinely changes; such frames are left out

The measure:
  speed[i] = |pos[i] - pos[i-1]| / (tick[i] - tick[i-1])        px per tick
  a frame counts when both it and the previous are live, neither is an event, dt > 0,
  and speed >= --min-speed (slow motion is not judged)
  dev[i]   = |speed[i] / median(counted speeds of the 2 frames either side) - 1|, needing 3 of 4
  hitch    = dev > --hitch (default 0.25)
Pass: hitches <= max(--min-allowed, samples / --per). Defaults 2 and 100.

A worked number: a tennis ball's deviation p95 went from 13.2% to about 5% once the renderer
extrapolated up to 1.5 ticks past the newest snapshot.

Examples:
  screen_smoothness.py ball.jsonl
  screen_smoothness.py ball.jsonl --min-speed 1.5 --hitch 0.25 --json
  screen_smoothness.py selftest

Prints one [SMOOTH] line, or one JSON object with --json.
Exit codes: 0 pass · 1 too many hitches or no samples · 2 usage or IO error.
"""
import argparse
import json
import math
import sys


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                rows.append((float(r["tick"]), float(r["x"]), float(r["y"]),
                             bool(r.get("live", True)), bool(r.get("event", False))))
            except (ValueError, KeyError, TypeError) as e:
                raise ValueError(f"{path}:{n}: {e}")
    return rows


def measure(rows, min_speed=1.5, hitch=0.25):
    n = len(rows)
    speed = [0.0] * n
    ok = [False] * n
    for i in range(1, n):
        t0, x0, y0, l0, e0 = rows[i - 1]
        t1, x1, y1, l1, e1 = rows[i]
        dt = t1 - t0
        if dt <= 1e-9 or not (l0 and l1) or e0 or e1:
            continue
        speed[i] = math.hypot(x1 - x0, y1 - y0) / dt
        ok[i] = speed[i] >= min_speed
    devs, hitches = [], 0
    for i in range(3, n - 2):
        if not ok[i]:
            continue
        win = sorted(speed[k] for k in range(i - 2, i + 3) if k != i and ok[k])
        if len(win) < 3:
            continue
        med = win[len(win) // 2]
        if med <= 0:
            continue
        d = abs(speed[i] / med - 1)
        devs.append(d)
        if d > hitch:
            hitches += 1
    devs.sort()
    res = {"samples": len(devs), "hitches": hitches, "p50": 0.0, "p95": 0.0, "max": 0.0}
    if devs:
        res["p50"] = devs[len(devs) // 2]
        res["p95"] = devs[min(len(devs) - 1, int(len(devs) * 0.95))]
        res["max"] = devs[-1]
    return res


def verdict(res, min_allowed=2, per=100):
    allowed = max(min_allowed, res["samples"] // per)
    res["allowed"] = allowed
    res["pass"] = res["samples"] > 0 and res["hitches"] <= allowed
    return res


def line(res):
    return ("[SMOOTH] samples={samples} hitches={hitches} allowed={allowed} "
            "dev p50={p50:.1%} p95={p95:.1%} max={max:.0%} {v}").format(
                v="PASS" if res["pass"] else "FAIL", **res)


def synth(frames=600, stall_every=0, jitter=0.0, seed=1):
    """A ball crossing the screen at 6 px per tick, sampled every 2 ticks (120 Hz sim, 60 fps).
    stall_every=k: every k-th frame shows the previous frame's position (the stale-snapshot bug),
    so that frame's speed is 0 (not counted) and the next frame's is doubled (a hitch)."""
    import random
    rnd = random.Random(seed)
    rows, prev = [], (0.0, 0.0)
    for i in range(frames):
        tick = i * 2.0
        x = 100 + 6.0 * tick + rnd.uniform(-jitter, jitter)
        y = 500 - 0.5 * tick
        if stall_every and i % stall_every == 0 and i > 0:
            x, y = prev
        rows.append((tick, x, y, True, False))
        prev = (x, y)
    return rows


def selftest():
    fails = []
    r = verdict(measure(synth()))
    if not (r["pass"] and r["hitches"] == 0 and r["p95"] < 1e-9):
        fails.append(f"even motion should pass with no hitches: {r}")
    r = verdict(measure(synth(stall_every=20)))
    if r["pass"] or r["hitches"] < 25:
        fails.append(f"a stall every 20 frames should fail with ~29 hitches: {r}")
    r = verdict(measure(synth(jitter=0.3)))
    if not r["pass"] or not (0 < r["p95"] < 0.25):
        fails.append(f"small sub-pixel noise should pass with a non-zero p95: {r}")
    stall = synth(stall_every=50)
    stall = [(t, x, y, l, i % 50 in (0, 1)) for i, (t, x, y, l, _) in enumerate(stall)]
    r = verdict(measure(stall))
    if r["hitches"] != 0:
        fails.append(f"jumps on frames flagged as events must be ignored: {r}")
    r = verdict(measure([]))
    if r["pass"]:
        fails.append("no samples must not pass")
    if fails:
        print("selftest FAILED:\n  " + "\n  ".join(fails))
        return 1
    print("selftest OK: even motion passes, stalls fail, noise is measured, events are skipped, empty fails")
    return 0


def main(argv):
    if argv[:1] == ["selftest"]:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("log")
    ap.add_argument("--min-speed", type=float, default=1.5, help="px per tick below which a frame is not judged")
    ap.add_argument("--hitch", type=float, default=0.25, help="relative deviation that counts as a hitch")
    ap.add_argument("--min-allowed", type=int, default=2)
    ap.add_argument("--per", type=int, default=100, help="one hitch allowed per this many samples")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        rows = load(a.log)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    res = verdict(measure(rows, a.min_speed, a.hitch), a.min_allowed, a.per)
    print(json.dumps(res) if a.json else line(res))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
