#!/usr/bin/env python3
"""courier_run_preview.py — a simulated-gameplay preview of the courier run, written from its rules.

The Runner carries a parcel down one of three lanes toward a gate that opens
and closes on a fixed rhythm, past pickups and a patrolling sentry. Every
position, every switch and every sound in the preview follows from the
constants block below and nothing else: change a rule and the preview changes
with it, which is the point of making it before the code.

usage:
    courier_run_preview.py --out DIR [--duration S]
    courier_run_preview.py selftest            (or --selftest)

Writes into DIR: sprites/*.png and sfx/*.wav (placeholder shapes and tones it
makes itself), timeline.json, then runs ../preview_compose.py on it, giving
preview.mp4, preview.events.json and preview.contact.png. Prints one JSON line
with `triggers` (gate and pickup triggers counted from the rules) next to the
compositor's result, so the two can be compared.

Exit codes: those of preview_compose.py. Python, Pillow, numpy, ffmpeg.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# ------------------------------------------------------------------ the game's rules: only here
FPS = 30
SIZE = (1024, 576)
DURATION = 8.0              # s of preview
LANES = 3
LANE_WIDTH = 2.0            # m
RUN_SPEED = 9.0             # m/s, constant along the track
PX_PER_M = 40               # screen scale of the preview camera (top-down, follows the Runner)
RUNNER_SCREEN_Y = 470       # px, where the Runner's feet stay on screen
LANE_SWITCH_TIME = 0.25     # s for one lane change; the lane counts as changed half-way
LANE_PLAN = [(0.0, 1), (1.4, 0), (3.1, 2), (4.9, 1), (6.4, 0)]   # (t, lane) the player chooses
PICKUP_START = 10.0         # m from the start line
PICKUP_SPACING = 6.0        # m between pickups
PICKUP_LANES = [1, 0, 0, 2, 2, 1, 1, 0, 0, 2]                     # lane of each pickup, in order
GATE_DISTANCES = [36.0, 63.0]                                      # m from the start line
GATE_PERIOD = 2.0           # s, one open-and-closed cycle
GATE_OPEN_WINDOW = 0.8      # s open at the start of each cycle
SENTRY_DISTANCE = 45.0      # m, the sentry patrols across the lanes here
SENTRY_PERIOD = 1.6         # s for one sweep across and back
# --------------------------------------------------------------------------------------------

COLORS = {"ground": "#2b3240", "lane": "#39414f", "mark": "#8a93a3", "runner": "#3fa7ff",
          "pickup": "#ffd23f", "gate_open": "#42d77d", "gate_closed": "#ff5a4f", "sentry": "#c45bff"}


def lane_x(lane: int) -> float:
    return SIZE[0] / 2 + (lane - (LANES - 1) / 2) * LANE_WIDTH * PX_PER_M


def screen_y(distance: float, t: float) -> float:
    return RUNNER_SCREEN_Y - (distance - RUN_SPEED * t) * PX_PER_M


def lane_at(t: float) -> int:
    lane = LANE_PLAN[0][1]
    for ts, ln in LANE_PLAN:
        if ts + LANE_SWITCH_TIME / 2 <= t:
            lane = ln
    return lane


def gate_open(t: float) -> bool:
    return (t % GATE_PERIOD) < GATE_OPEN_WINDOW - 1e-9


def triggers(duration: float) -> list:
    """Every rule trigger in [0, duration): a gate reached (open or closed) and a pickup collected."""
    out = []
    for g in GATE_DISTANCES:
        t = g / RUN_SPEED
        if t < duration:
            out.append({"t": round(t, 4), "kind": "gate_pass" if gate_open(t) else "gate_hit", "gate": g})
    for n, lane in enumerate(PICKUP_LANES):
        t = (PICKUP_START + n * PICKUP_SPACING) / RUN_SPEED
        if t < duration and lane_at(t) == lane:
            out.append({"t": round(t, 4), "kind": "pickup", "pickup": n})
    return sorted(out, key=lambda e: e["t"])


def make_sprites(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    w = round(LANES * LANE_WIDTH * PX_PER_M)
    img = Image.new("RGBA", SIZE, COLORS["ground"])
    dr = ImageDraw.Draw(img)
    x0 = (SIZE[0] - w) / 2
    dr.rectangle((x0, 0, x0 + w, SIZE[1]), fill=COLORS["lane"])
    img.save(d / "ground.png")
    mark = Image.new("RGBA", (4, SIZE[1] * 2), (0, 0, 0, 0))
    md = ImageDraw.Draw(mark)
    for y in range(0, mark.height, PX_PER_M * 2):          # one dash every 2 m
        md.rectangle((0, y, 3, y + PX_PER_M - 1), fill=COLORS["mark"])
    mark.save(d / "mark.png")
    r = Image.new("RGBA", (36, 44), (0, 0, 0, 0))
    ImageDraw.Draw(r).polygon([(18, 0), (35, 43), (0, 43)], fill=COLORS["runner"])
    r.save(d / "runner.png")
    p = Image.new("RGBA", (22, 22), (0, 0, 0, 0))
    ImageDraw.Draw(p).ellipse((0, 0, 21, 21), fill=COLORS["pickup"])
    p.save(d / "pickup.png")
    for state in ("gate_open", "gate_closed"):
        g = Image.new("RGBA", (w + 24, 18), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        gd.rectangle((0, 0, 11, 17), fill=COLORS[state])
        gd.rectangle((w + 12, 0, w + 23, 17), fill=COLORS[state])
        if state == "gate_closed":
            gd.rectangle((12, 5, w + 11, 12), fill=COLORS[state])
        g.save(d / f"{state}.png")
    s = Image.new("RGBA", (34, 34), (0, 0, 0, 0))
    ImageDraw.Draw(s).polygon([(17, 0), (33, 17), (17, 33), (0, 17)], fill=COLORS["sentry"])
    s.save(d / "sentry.png")


def make_sfx(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    rate = 48000
    for name, hz, sec in (("pickup", 1320, 0.12), ("gate_pass", 660, 0.25), ("gate_hit", 140, 0.35)):
        t = np.arange(int(sec * rate)) / rate
        pcm = (0.5 * np.sin(2 * np.pi * hz * t) * np.exp(-t * 12) * 32767).astype("<i2")
        with wave.open(str(d / f"{name}.wav"), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(rate)
            f.writeframes(pcm.tobytes())


def timeline(duration: float) -> dict:
    trig = triggers(duration)
    layers = [{"asset": "ground", "z": 0, "keys": [{"t": 0}]}]
    for lane in range(LANES + 1):                          # lane edges scroll with the track
        x = lane_x(lane) - LANE_WIDTH * PX_PER_M / 2
        cycle = 2 * PX_PER_M * 2 / (RUN_SPEED * PX_PER_M)  # the dash pattern repeats every 4 m
        keys = []
        for k in range(math.ceil(duration / cycle) + 1):
            keys += [{"t": k * cycle, "x": x, "y": SIZE[1] / 2}, {"t": (k + 1) * cycle - 1e-6, "x": x,
                                                                 "y": SIZE[1] / 2 + 4 * PX_PER_M}]
        layers.append({"asset": "mark", "z": 1, "keys": keys})
    hit = {e["pickup"]: e["t"] for e in trig if e["kind"] == "pickup"}
    for n, lane in enumerate(PICKUP_LANES):
        d = PICKUP_START + n * PICKUP_SPACING
        keys = [{"t": 0, "x": lane_x(lane), "y": screen_y(d, 0), "alpha": 1},
                {"t": duration, "x": lane_x(lane), "y": screen_y(d, duration), "alpha": 1}]
        layer = {"asset": "pickup", "z": 4, "keys": keys}
        if n in hit:
            layer["t1"] = hit[n]                           # collected: gone from that frame on
        layers.append(layer)
    for g in GATE_DISTANCES:              # one layer per gate state, keyed on every frame: exact at frame times
        for state, want in (("gate_open", True), ("gate_closed", False)):
            keys = [{"t": k / FPS, "x": SIZE[0] / 2, "y": screen_y(g, k / FPS),
                     "alpha": 1.0 if gate_open(k / FPS) == want else 0.0}
                    for k in range(math.ceil(duration * FPS) + 1)]
            layers.append({"asset": state, "z": 3, "ease": "linear", "keys": keys})
    sweep = (LANE_WIDTH * PX_PER_M) * (LANES - 1) / 2
    skeys = [{"t": k * SENTRY_PERIOD / 2, "x": SIZE[0] / 2 + (sweep if k % 2 else -sweep),
              "y": screen_y(SENTRY_DISTANCE, k * SENTRY_PERIOD / 2)}
             for k in range(math.ceil(duration / (SENTRY_PERIOD / 2)) + 1)]
    layers.append({"asset": "sentry", "z": 5, "ease": "in_out", "keys": skeys})
    rkeys = []
    for ts, lane in LANE_PLAN:
        if rkeys:
            rkeys.append({"t": ts, "x": rkeys[-1]["x"]})
        rkeys.append({"t": ts + (LANE_SWITCH_TIME if rkeys else 0), "x": lane_x(lane), "y": RUNNER_SCREEN_Y})
    layers.append({"asset": "runner", "z": 10, "ease": "in_out", "keys": rkeys})
    sfx = {"pickup": 0.8, "gate_pass": 0.9, "gate_hit": 1.0}
    return {
        "fps": FPS, "size": list(SIZE), "duration": duration, "bg": COLORS["ground"], "safe": 0.05,
        "assets": {"ground": {"path": "sprites/ground.png"}, "mark": {"path": "sprites/mark.png"},
                   "runner": {"path": "sprites/runner.png", "anchor": "bc"},
                   "pickup": {"path": "sprites/pickup.png"}, "sentry": {"path": "sprites/sentry.png"},
                   "gate_open": {"path": "sprites/gate_open.png"},
                   "gate_closed": {"path": "sprites/gate_closed.png"}},
        "layers": layers,
        "text": [{"t0": 0, "t1": 1.5, "text": "Courier run: reach the gate while it is open", "y": 40, "size": 28},
                 {"t0": 0, "t1": duration, "text": f"gate open {GATE_OPEN_WINDOW:g} s of every {GATE_PERIOD:g} s",
                  "y": SIZE[1] - 30, "size": 18}]
                + [{"t0": e["t"], "t1": e["t"] + 0.8, "x": lane_x(lane_at(e["t"])), "y": RUNNER_SCREEN_Y - 80,
                    "size": 26, **({"text": "gate open: through", "color": COLORS["gate_open"]} if e["kind"] ==
                                   "gate_pass" else {"text": "gate closed: hit", "color": COLORS["gate_closed"]})}
                   for e in trig if e["kind"] != "pickup"],         # a label says what the sound says
        "events": [{"t": e["t"], "sfx": e["kind"], "vol": sfx[e["kind"]]} for e in trig],
    }


def build(out: Path, duration: float) -> tuple[int, dict]:
    out.mkdir(parents=True, exist_ok=True)
    make_sprites(out / "sprites")
    make_sfx(out / "sfx")
    (out / "timeline.json").write_text(json.dumps(timeline(duration), indent=1) + "\n", encoding="utf-8")
    compose = Path(__file__).resolve().parents[1] / "preview_compose.py"
    r = subprocess.run([sys.executable, str(compose), str(out / "timeline.json"), "--out", str(out / "preview.mp4"),
                        "--sfx-dir", str(out / "sfx")], capture_output=True, text=True)
    try:
        result = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        result = {"ok": False, "error": (r.stderr or r.stdout).strip()[-400:]}
    return r.returncode, {"triggers": len(triggers(duration)), **result}


# ------------------------------------------------------------------------------------ selftest

def selftest() -> int:
    checks, failed = [], []

    def check(name: str, ok: bool) -> None:
        checks.append(name)
        if not ok:
            failed.append(name)

    check("gate rhythm", gate_open(0.1) and not gate_open(GATE_OPEN_WINDOW) and gate_open(GATE_PERIOD))
    check("lane counts as changed half-way", lane_at(1.4 + LANE_SWITCH_TIME / 2) == 0 and lane_at(1.4) == 1)
    dur = DURATION
    with tempfile.TemporaryDirectory() as tmp:
        runs = [build(Path(tmp) / f"run{k}", dur) for k in (0, 1)]
        logs = [json.loads((Path(tmp) / f"run{k}" / "preview.events.json").read_text()) for k in (0, 1)]
        check("compositor exit 0", all(code == 0 for code, _ in runs))
        n = round(FPS * dur)
        check("frames == fps x duration", logs[0]["frames"] == n)
        r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                            "format=duration:stream=codec_type,nb_read_frames", "-of", "json",
                            str(Path(tmp) / "run0" / "preview.mp4")], capture_output=True, text=True)
        info = json.loads(r.stdout or "{}")
        v = [s for s in info.get("streams", []) if s["codec_type"] == "video"]
        check("encoded frame count", bool(v) and int(v[0]["nb_read_frames"]) == n)
        check("ffprobe duration within 1/fps", abs(float(info.get("format", {}).get("duration", 0)) - dur) <= 1 / FPS)
        check("events == rule triggers", len(logs[0]["events"]) == runs[0][1]["triggers"] == len(triggers(dur)))
        # worked by hand from the constants above: gate 1 at 36/9 = 4.0 s, 4.0 % 2 < 0.8, open;
        # gate 2 at 63/9 = 7.0 s, 7.0 % 2 = 1.0, closed; pickups 0, 1, 2, 4 and 6 lie in the Runner's lane
        ev = [(e["sfx"], e["t"]) for e in logs[0]["events"]]
        check("triggers worked by hand", [k for k, _ in ev].count("pickup") == 5
              and [(k, t) for k, t in ev if k.startswith("gate")] == [("gate_pass", 4.0), ("gate_hit", 7.0)])
        kinds = {e["sfx"] for e in logs[0]["events"]}
        check("gate and pickup triggers present", "pickup" in kinds and kinds & {"gate_hit", "gate_pass"})
        check("contact sheet", (Path(tmp) / "run0" / "preview.contact.png").is_file())
        check("deterministic events", logs[0]["events"] == logs[1]["events"])
        check("deterministic frames", logs[0]["frames_sha256"] == logs[1]["frames_sha256"])
        check("every sfx found", logs[0]["sfx_missing"] == [] and logs[0]["audio"])
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": len(checks), "failed": failed,
                      "triggers": len(triggers(dur))}))
    return 1 if failed else 0


def main(argv: list) -> int:
    if argv in (["selftest"], ["--selftest"]):
        return selftest()
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--duration", type=float, default=DURATION)
    a = ap.parse_args(argv)
    code, result = build(a.out, a.duration)
    print(json.dumps(result))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
