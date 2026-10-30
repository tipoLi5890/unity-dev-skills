#!/usr/bin/env python3
"""courier_run_preview.py — a simulated-gameplay preview of the courier run, written from its rules.

The Runner launches down one of three lanes, past pickups and a patrolling
sentry, through gates that open and close on a fixed rhythm. Every position,
every switch and every sound follows from ../../resources/Sim/courier_rules.json
and nothing else. Its `sim` block is the C# skeleton's RunConfig, field for
field (RunSimulationTests fails when they differ), and this script moves the
Runner with RunSimulation.Tick's rules: launch, acceleration to LaunchSpeed,
ShiftSpeedFactor off per lane pressed, LaneSpacing between lanes, pickups on
rows RowSpacing apart. Its `preview` block is staging the skeleton does not
simulate yet: the gates' rhythm, the sentry, where things sit and the lanes the
player picks. Change a rule and the preview changes with it, which is the point
of making it before the code.

usage:
    courier_run_preview.py --out DIR [--duration S] [--rules courier_rules.json]
    courier_run_preview.py selftest            (or --selftest)

Writes into DIR: sprites/*.png and sfx/*.wav (placeholder shapes and tones it
makes itself), timeline.json, then runs ../preview_compose.py on it, giving
preview.mp4, preview.events.json and preview.contact.png. Prints one JSON line
with `triggers` (gate and pickup triggers counted from the rules) next to the
compositor's result, so the two can be compared.

Exit codes: those of preview_compose.py, and 2 for a rules file it cannot read. Python, Pillow,
numpy, ffmpeg.
"""
from __future__ import annotations

import functools
import json
import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# ------------------------------------------------------------------ presentation: only here
FPS = 30
SIZE = (1024, 576)
DURATION = 8.0              # s of preview
LANE_PX = 80                # screen width of one lane; the camera is top-down and follows the Runner
RUNNER_SCREEN_Y = 470       # px, where the Runner's feet stay on screen
LANE_TWEEN = 0.25           # s the Runner's sprite takes to slide over; the sim changes lane at once
# ------------------------------------------------- the game's rules: ../../resources/Sim/courier_rules.json
RULES_PATH = Path(__file__).resolve().parents[2] / "resources" / "Sim" / "courier_rules.json"
SIM_KEYS = ("LaneCount", "LaneSpacing", "GateDistance", "LaunchSpeed", "Acceleration", "ShiftSpeedFactor",
            "RowSpacing", "LookAhead", "TickSeconds")
PREVIEW_KEYS = ("LanePlan", "PickupRows", "GateDistances", "GatePeriod", "GateOpenWindow", "SentryDistance",
                "SentryPeriod")
TRACK_CAP = 60.0            # s; INV-3 puts a whole run at 20-40 s
SIM: dict = {}
STAGE: dict = {}

COLORS = {"ground": "#2b3240", "lane": "#39414f", "mark": "#8a93a3", "runner": "#3fa7ff",
          "pickup": "#ffd23f", "gate_open": "#42d77d", "gate_closed": "#ff5a4f", "sentry": "#c45bff"}


def use_rules(path: Path = RULES_PATH) -> None:
    """Load the shared rules file: `sim` is RunConfig field for field, `preview` is staging."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [k for k in SIM_KEYS if k not in doc.get("sim", {})] + \
              [k for k in PREVIEW_KEYS if k not in doc.get("preview", {})]
    if missing:
        raise ValueError(f"{path}: missing {', '.join(missing)}")
    SIM.clear()
    SIM.update(doc["sim"])
    STAGE.clear()
    STAGE.update(doc["preview"])
    _track.cache_clear()


def px_per_m() -> float:
    return LANE_PX / SIM["LaneSpacing"]


def lane_x(lane: float) -> float:
    return SIZE[0] / 2 + (lane - (SIM["LaneCount"] - 1) / 2) * LANE_PX


@functools.lru_cache(maxsize=None)
def _track() -> tuple:
    """RunSimulation.Tick ported: Launch before the first tick, the lane plan as presses drained on
    the first tick at or after their time, acceleration up to LaunchSpeed, ShiftSpeedFactor per
    shift, a stop at GateDistance. One (t, distance, lane) per tick, tick 0 included, up to the gate
    or TRACK_CAP seconds."""
    dt, lanes = SIM["TickSeconds"], SIM["LaneCount"]
    plan = [(float(t), int(lane)) for t, lane in STAGE["LanePlan"]]
    lane, speed, dist, nxt = plan[0][1], 0.0, 0.0, 1
    rows = [(0.0, 0.0, lane)]
    for n in range(1, int(TRACK_CAP / dt) + 2):
        t = n * dt
        while nxt < len(plan) and plan[nxt][0] <= t + 1e-9:
            target = plan[nxt][1]
            while lane != target and 0 <= lane + (1 if target > lane else -1) < lanes:
                lane += 1 if target > lane else -1           # one press per lane, each scrubs speed
                speed *= SIM["ShiftSpeedFactor"]
            nxt += 1
        speed = min(SIM["LaunchSpeed"], speed + SIM["Acceleration"] * dt)
        dist = min(SIM["GateDistance"], dist + speed * dt)
        rows.append((t, dist, lane))
        if dist >= SIM["GateDistance"]:
            break
    return tuple(rows)


def _state(t: float) -> tuple:
    rows = _track()
    n = min(len(rows) - 1, int(t / SIM["TickSeconds"] + 1e-3))   # the last tick at or before t
    return rows[n]


def distance_at(t: float) -> float:
    return _state(t)[1]


def lane_at(t: float) -> int:
    return _state(t)[2]


def time_at(distance: float) -> float:
    """The tick on which the Runner reaches `distance`, as RunSimulation resolves a crossing."""
    for t, d, _ in _track():
        if d >= distance - 1e-9:
            return t
    return math.inf


def screen_y(distance: float, t: float) -> float:
    return RUNNER_SCREEN_Y - (distance - distance_at(t)) * px_per_m()


def gate_open(t: float) -> bool:
    return (t % STAGE["GatePeriod"]) < STAGE["GateOpenWindow"] - 1e-9


def pickups() -> list:
    """(index, lane, distance): pickups sit on hazard rows, RowSpacing apart, as TrackGen puts them."""
    return [(n, int(lane), row * SIM["RowSpacing"]) for n, (row, lane) in enumerate(STAGE["PickupRows"])]


def triggers(duration: float) -> list:
    """Every rule trigger in [0, duration): a gate reached (open or closed) and a pickup collected."""
    out = []
    for g in STAGE["GateDistances"]:
        t = time_at(g)
        if t < duration:
            out.append({"t": round(t, 4), "kind": "gate_pass" if gate_open(t) else "gate_hit", "gate": g})
    for n, lane, d in pickups():
        t = time_at(d)
        if t < duration and lane_at(t) == lane:
            out.append({"t": round(t, 4), "kind": "pickup", "pickup": n})
    return sorted(out, key=lambda e: e["t"])


def make_sprites(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    w = round(SIM["LaneCount"] * LANE_PX)
    img = Image.new("RGBA", SIZE, COLORS["ground"])
    dr = ImageDraw.Draw(img)
    x0 = (SIZE[0] - w) / 2
    dr.rectangle((x0, 0, x0 + w, SIZE[1]), fill=COLORS["lane"])
    img.save(d / "ground.png")
    mark = Image.new("RGBA", (4, SIZE[1] * 2), (0, 0, 0, 0))
    md = ImageDraw.Draw(mark)
    ppm = px_per_m()
    for k in range(math.ceil(mark.height / (2 * ppm))):   # one 1 m dash every 2 m
        md.rectangle((0, round(k * 2 * ppm), 3, round(k * 2 * ppm + ppm) - 1), fill=COLORS["mark"])
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


def frame_times(duration: float) -> list:
    return [k / FPS for k in range(math.ceil(duration * FPS) + 1)]


def timeline(duration: float) -> dict:
    """Every moving layer is keyed on every frame, so it is exact at frame times: the track scrolls
    at the simulated speed, which is not constant (launch, scrub on each shift)."""
    trig = triggers(duration)
    ts = frame_times(duration)
    ppm = px_per_m()
    layers = [{"asset": "ground", "z": 0, "keys": [{"t": 0}]}]
    for edge in range(SIM["LaneCount"] + 1):               # lane edges scroll with the track
        x = lane_x(edge) - LANE_PX / 2
        keys = [{"t": t, "x": x, "y": SIZE[1] / 2 + (distance_at(t) % 4) * ppm} for t in ts]  # repeats every 4 m
        layers.append({"asset": "mark", "z": 1, "keys": keys})
    hit = {e["pickup"]: e["t"] for e in trig if e["kind"] == "pickup"}
    for n, lane, d in pickups():
        layer = {"asset": "pickup", "z": 4, "keys": [{"t": t, "x": lane_x(lane), "y": screen_y(d, t)} for t in ts]}
        if n in hit:
            layer["t1"] = hit[n]                           # collected: gone from that frame on
        layers.append(layer)
    for g in STAGE["GateDistances"]:                       # one layer per gate state
        for state, want in (("gate_open", True), ("gate_closed", False)):
            keys = [{"t": t, "x": SIZE[0] / 2, "y": screen_y(g, t), "alpha": 1.0 if gate_open(t) == want else 0.0}
                    for t in ts]
            layers.append({"asset": state, "z": 3, "keys": keys})
    sweep = LANE_PX * (SIM["LaneCount"] - 1) / 2           # across the lanes and back, eased at each end
    half = STAGE["SentryPeriod"] / 2

    def sentry_x(t: float) -> float:
        k, u = divmod(t / half, 1.0)
        a, b = (-sweep, sweep) if k % 2 == 0 else (sweep, -sweep)
        return SIZE[0] / 2 + a + (b - a) * u * u * (3 - 2 * u)
    layers.append({"asset": "sentry", "z": 5,
                   "keys": [{"t": t, "x": sentry_x(t), "y": screen_y(STAGE["SentryDistance"], t)} for t in ts]})
    rkeys = []                                             # the sprite slides; the sim's lane changed at once
    for t0, lane in STAGE["LanePlan"]:
        if rkeys:
            rkeys.append({"t": t0, "x": rkeys[-1]["x"]})
        rkeys.append({"t": t0 + (LANE_TWEEN if rkeys else 0), "x": lane_x(lane), "y": RUNNER_SCREEN_Y})
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
                 {"t0": 0, "t1": duration,
                  "text": f"gate open {STAGE['GateOpenWindow']:g} s of every {STAGE['GatePeriod']:g} s",
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

    check("rules file holds every RunConfig field", set(SIM) == set(SIM_KEYS))
    check("gate rhythm", gate_open(0.1) and not gate_open(STAGE["GateOpenWindow"]) and gate_open(STAGE["GatePeriod"]))
    dt = SIM["TickSeconds"]
    check("lane changes on the press tick", lane_at(1.4 - dt) == 1 and lane_at(1.4 + dt) == 0)
    cruise = (distance_at(1.3) - distance_at(0.8)) / 0.5    # past the launch ramp, before the first shift
    check("cruise at LaunchSpeed after the ramp", abs(cruise - SIM["LaunchSpeed"]) < 1e-3
          and distance_at(0.5) < SIM["LaunchSpeed"] * 0.5)
    rows = _track()
    i = next(n for n, r in enumerate(rows) if r[0] >= 1.4)  # the tick that drains the 1.4 s press
    scrub = (rows[i][1] - rows[i - 1][1]) / dt
    check("a shift scrubs speed by ShiftSpeedFactor", abs(scrub - (SIM["LaunchSpeed"] * SIM["ShiftSpeedFactor"]
                                                                  + SIM["Acceleration"] * dt)) < 1e-3)
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
        # worked from courier_rules.json: a 0.73 s ramp to 4.4 m/s, 10% off per lane pressed
        # (1.4 s: one, 3.3 s: two, 4.9 s and 6.4 s: one each). Gate 1 (17 m) is reached on the
        # 4.25 s tick, 4.25 % 2 < 0.8, open; gate 2 (29 m) at 6.98 s, 0.98 >= 0.8, closed.
        # Pickups 0 (6 m, 1.73 s, lane 0), 2 (18 m, 4.47 s, lane 2) and 3 (24 m, 5.83 s, lane 1)
        # are in the Runner's lane; pickup 1 (12 m, lane 1) is not
        ev = [(e["sfx"], e["t"]) for e in logs[0]["events"]]
        check("triggers worked by hand", [(k, t) for k, t in ev] == [
            ("pickup", 1.7333), ("gate_pass", 4.25), ("pickup", 4.4667), ("pickup", 5.8333), ("gate_hit", 6.9833)])
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
        use_rules()
        return selftest()
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--duration", type=float, default=DURATION)
    ap.add_argument("--rules", type=Path, default=RULES_PATH, help="a copy of courier_rules.json")
    a = ap.parse_args(argv)
    try:
        use_rules(a.rules)
    except (OSError, ValueError) as e:
        print(f"ERROR cannot use the rules file: {e}", file=sys.stderr)
        return 2
    code, result = build(a.out, a.duration)
    print(json.dumps(result))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
