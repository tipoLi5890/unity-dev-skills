#!/usr/bin/env python3
"""preview_compose.py — render a timed, simulated-gameplay preview from layered sprites and a timeline.

A preview is how a game's timing is seen before code exists: sprites move by
keys written from the game's own rules, text says what is happening, and every
sound the game would play is logged as an event. The timings in the timeline
are the numbers the brief and the first build are later checked against.

usage:
    preview_compose.py TIMELINE.json --out preview.mp4 [--sfx-dir DIR] [--guides]
    preview_compose.py selftest            (or --selftest)

TIMELINE.json (paths relative to the timeline's folder):
    {"fps": 30, "size": [1024, 576], "duration": 6.0,
     "bg": "#1d2430",                       optional, the opaque colour under every layer
     "safe": 0.05,                          optional, title-safe inset as a fraction of each side;
                                            text is kept inside it, --guides draws it
     "assets": {"runner": {"path": "sprites/runner.png", "anchor": "bc", "scale": 1.0,
                           "frames": 1}},   frames = cells in a horizontal strip
     "layers": [{"asset": "runner", "z": 10, "ease": "in_out", "t0": 0, "t1": 6,
                 "keys": [{"t": 0, "x": 512, "y": 480, "scale": 1, "alpha": 1,
                           "rot": 0, "frame": 0}, ...]}],
     "text": [{"t0": 0, "t1": 1.5, "text": "Run to the gate", "x": 512, "y": 60, "size": 32, "color": "#fff"}],
     "events": [{"t": 2.4, "sfx": "pickup", "vol": 0.8}]}

  anchor `c` puts the sprite's centre on (x, y), `bc` its bottom centre. A key
  may leave any property out; it then keeps the value of the key before it
  (defaults: centre of the frame, scale 1, alpha 1, rot 0, frame 0). Between
  two keys a property is eased by the layer's `ease`: linear | in_out
  (smoothstep) | out (quadratic) | step (hold until the next key). Before the
  first key and after the last the end values hold. `frame` always steps.
  `rot` is degrees, counter-clockwise. `t0`/`t1`, when given, limit when the
  layer is drawn (t0 <= t < t1). Layers draw in ascending `z`, ties in order.

Frame i is drawn at t = i / fps; there are round(fps x duration) >= 1 frames and
every event needs 0 <= t < frames / fps. Raw RGB frames go to ffmpeg (libx264 -crf 18, yuv420p).

Writes next to the video: `<stem>.events.json` (fps, size, frames, duration,
events with their frame numbers, and `frames_sha256`, one digest over every raw
frame, so two runs of the same timeline can be compared) and
`<stem>.contact.png` (8 frames, evenly spaced, each with its time).

--sfx-dir DIR: each event's `sfx` is DIR/<sfx> or DIR/<sfx>.wav|.ogg|.mp3|.flac;
the events are placed with adelay, mixed with amix (normalize=0) over a silent
track of the exact video length, loudness-normalised to -16 LUFS integrated,
-1.5 dBTP, and muxed as AAC. Normalising is two passes: measure, then linear
loudnorm; when the peaks leave no room for linear gain (loudnorm would go
dynamic, which misses on short clips) a fixed gain and a -2 dBFS limiter.
An event whose file is missing is still logged and listed under `sfx_missing`.

Prints one JSON line. Exit codes: 0 written; 2 the timeline is invalid; 3 an
input cannot be read, or ffmpeg failed. Python, Pillow, numpy, ffmpeg.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

EASES = ("linear", "in_out", "out", "step")
DEFAULTS = {"scale": 1.0, "alpha": 1.0, "rot": 0.0, "frame": 0}
SFX_EXT = ("", ".wav", ".ogg", ".mp3", ".flac")


class TimelineError(Exception):
    """The timeline is invalid: exit 2."""


class InputError(Exception):
    """An input cannot be read or ffmpeg failed: exit 3."""


def ease(u: float, kind: str) -> float:
    u = min(1.0, max(0.0, u))
    if kind == "in_out":
        return u * u * (3 - 2 * u)
    if kind == "out":
        return 1 - (1 - u) * (1 - u)
    if kind == "step":
        return 0.0
    return u


def resolve_keys(keys: list, w: int, h: int) -> list:
    """Fill every key with every property, carrying the previous key's values forward."""
    cur = {"x": w / 2, "y": h / 2, **DEFAULTS}
    out = []
    for k in sorted(keys, key=lambda k: float(k["t"])):
        cur = {**cur, **{p: k[p] for p in cur if p in k}}
        out.append({"t": float(k["t"]), **cur})
    return out


def sample(keys: list, t: float, kind: str) -> dict:
    if t <= keys[0]["t"]:
        return keys[0]
    if t >= keys[-1]["t"]:
        return keys[-1]
    for a, b in zip(keys, keys[1:]):
        if a["t"] <= t < b["t"]:
            span = b["t"] - a["t"]
            e = ease((t - a["t"]) / span if span > 0 else 1.0, kind)
            v = {p: a[p] + (b[p] - a[p]) * e for p in ("x", "y", "scale", "alpha", "rot")}
            v["frame"] = a["frame"]
            return v
    return keys[-1]


def load_timeline(path: Path) -> dict:
    try:
        tl = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InputError(f"cannot read {path.name}: {e}")
    if not isinstance(tl, dict):
        raise TimelineError("the timeline is not a JSON object")
    try:
        fps, (w, h), dur = float(tl["fps"]), (int(v) for v in tl["size"]), float(tl["duration"])
    except (KeyError, TypeError, ValueError):
        raise TimelineError("fps, size [w, h] and duration are required numbers")
    if not (math.isfinite(fps) and math.isfinite(dur)) or min(fps, dur, w, h) <= 0 or w % 2 or h % 2:
        raise TimelineError("fps and duration must be > 0; width and height positive and even (yuv420p)")
    if round(fps * dur) < 1:
        raise TimelineError("round(fps x duration) is 0: the preview needs at least one frame")
    try:
        check_fields(tl, round(fps * dur) / fps)
    except (KeyError, TypeError, ValueError, AttributeError) as e:   # a shape check_fields did not foresee
        raise TimelineError(f"invalid timeline: {e.__class__.__name__}: {e}")
    tl.update(fps=fps, size=[w, h], duration=dur)
    return tl


def isnum(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def check_fields(tl: dict, end: float) -> None:
    """Every field compose() reads has the type it needs; `end` = frames / fps, the last instant shown."""
    def objects(key: str) -> list:
        v = tl.get(key) or []
        if not isinstance(v, list) or not all(isinstance(e, dict) for e in v):
            raise TimelineError(f"{key} must be a list of objects")
        return v
    def numbers(where: str, d: dict, names: tuple) -> None:
        if any(k in d and not isnum(d[k]) for k in names):
            raise TimelineError(f"{where}: {', '.join(k for k in names if k in d)} must be numbers")
    colour(tl.get("bg", "#000"), "bg")
    numbers("timeline", tl, ("safe",))
    assets = tl.get("assets") or {}
    if not isinstance(assets, dict):
        raise TimelineError("assets must map each id to an object")
    for aid, a in assets.items():
        if not isinstance(a, dict) or not isinstance(a.get("path"), str) or not a["path"]:
            raise TimelineError(f"asset {aid!r} needs a string path")
        numbers(f"asset {aid!r}", a, ("scale", "frames"))
        if a.get("anchor", "c") not in ("c", "bc") or a.get("scale", 1) <= 0 or a.get("frames", 1) < 1:
            raise TimelineError(f"asset {aid!r}: anchor must be c or bc, scale > 0, frames >= 1")
    for layer in objects("layers"):
        if not isinstance(layer.get("asset"), str) or layer["asset"] not in assets:
            raise TimelineError(f"layer names an unknown asset: {layer.get('asset')!r}")
        if layer.get("ease", "linear") not in EASES:
            raise TimelineError(f"unknown ease {layer.get('ease')!r}; one of {', '.join(EASES)}")
        if not isinstance(layer.get("keys"), list) or not layer["keys"]:
            raise TimelineError(f"layer {layer['asset']!r} has no keys")
        numbers(f"layer {layer['asset']!r}", layer, ("z", "t0", "t1"))
        for k in layer["keys"]:
            if not isinstance(k, dict) or not isnum(k.get("t")):
                raise TimelineError(f"layer {layer['asset']!r}: every key needs a numeric t")
            numbers(f"layer {layer['asset']!r}, key t={k['t']}", k, ("x", "y", "scale", "alpha", "rot", "frame"))
    for tx in objects("text"):
        numbers("text", tx, ("t0", "t1", "x", "y", "size"))
        if "text" not in tx or tx.get("size", 28) < 1:
            raise TimelineError(f"a text entry needs `text` and a size >= 1: {tx}")
        colour(tx.get("color", "#fff"), "text color")
    for ev in objects("events"):
        if not isinstance(ev.get("sfx"), str) or not isnum(ev.get("t")) or not 0 <= ev["t"] < end:
            raise TimelineError(f"an event needs a string sfx and 0 <= t < frames / fps ({end:g} s): {ev}")
        numbers("event", ev, ("vol",))


def colour(v, where: str) -> None:
    try:
        ImageColor.getrgb(v)
    except (ValueError, TypeError, AttributeError):
        raise TimelineError(f"{where}: not a colour: {v!r}")



def load_sprites(tl: dict, base: Path) -> dict:
    cells = {}
    for aid, a in tl.get("assets", {}).items():
        p = base / a["path"]
        try:
            img = Image.open(p).convert("RGBA")
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as e:
            raise InputError(f"asset {aid!r}: cannot read {a['path']}: {e}")
        n = max(1, int(a.get("frames", 1)))
        cw = img.width // n
        cells[aid] = [img.crop((i * cw, 0, (i + 1) * cw, img.height)) for i in range(n)]
    return cells


def font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


class Renderer:
    def __init__(self, tl: dict, cells: dict):
        self.tl, self.cells = tl, cells
        self.w, self.h = tl["size"]
        self.bg = tl.get("bg", "#1d2430")
        self.layers = sorted(
            [(float(l.get("z", 0)), i, l, resolve_keys(l["keys"], self.w, self.h))
             for i, l in enumerate(tl.get("layers") or [])], key=lambda r: (r[0], r[1]))
        self.cache: dict = {}
        s = float(tl.get("safe", 0) or 0)
        self.safe = (round(self.w * s), round(self.h * s), self.w - round(self.w * s), self.h - round(self.h * s))

    def sprite(self, aid: str, frame: int, scale: float, rot: float) -> Image.Image:
        key = (aid, frame, round(scale, 3), round(rot, 1))
        if key not in self.cache:
            if len(self.cache) > 512:
                self.cache.clear()
            cells = self.cells[aid]
            img = cells[min(max(0, int(frame)), len(cells) - 1)]
            sw, sh = max(1, round(img.width * key[2])), max(1, round(img.height * key[2]))
            if (sw, sh) != img.size:
                img = img.resize((sw, sh), Image.BILINEAR)
            if key[3]:
                img = img.rotate(key[3], resample=Image.BICUBIC, expand=True)
            self.cache[key] = img
        return self.cache[key]

    def frame(self, t: float, guides: bool = False) -> Image.Image:
        canvas = Image.new("RGBA", (self.w, self.h), self.bg)
        for _, _, layer, keys in self.layers:
            if not float(layer.get("t0", -math.inf)) <= t < float(layer.get("t1", math.inf)):
                continue
            v = sample(keys, t, layer.get("ease", "linear"))
            if v["alpha"] <= 0:
                continue
            a = self.tl["assets"][layer["asset"]]
            img = self.sprite(layer["asset"], v["frame"], float(a.get("scale", 1.0)) * v["scale"], v["rot"])
            if v["alpha"] < 1:
                img = img.copy()
                img.putalpha(img.getchannel("A").point(lambda p, k=min(1.0, v["alpha"]): round(p * k)))
            x = round(v["x"] - img.width / 2)
            y = round(v["y"] - (img.height if a.get("anchor", "c") == "bc" else img.height / 2))
            layer_img = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            layer_img.paste(img, (x, y))
            canvas.alpha_composite(layer_img)
        draw = ImageDraw.Draw(canvas)
        for tx in self.tl.get("text") or []:
            if float(tx.get("t0", 0)) <= t < float(tx.get("t1", math.inf)):
                f = font(int(tx.get("size", 28)))
                l, tp, r, b = draw.textbbox((0, 0), str(tx["text"]), font=f, stroke_width=2)
                x = float(tx.get("x", self.w / 2)) - (r - l) / 2
                y = float(tx.get("y", self.h * 0.1)) - (b - tp) / 2
                x = min(max(x, self.safe[0]), max(self.safe[0], self.safe[2] - (r - l)))
                y = min(max(y, self.safe[1]), max(self.safe[1], self.safe[3] - (b - tp)))
                draw.text((x - l, y - tp), str(tx["text"]), font=f, fill=tx.get("color", "#ffffff"),
                          stroke_width=2, stroke_fill="#000000")
        if guides:
            draw.rectangle(self.safe, outline="#ffcc00")
        return canvas.convert("RGB")


def run(cmd: list, what: str) -> subprocess.CompletedProcess:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as e:
        raise InputError(f"{what}: {e}")
    if r.returncode != 0:
        raise InputError(f"{what} failed: {r.stderr.strip()[-400:]}")
    return r


def loudnorm_args(src: list, filt: str, label: str, target: float = -16.0) -> str:
    """Two-pass loudnorm: measure what `filt` makes, then return the linear-mode filter for pass 2."""
    norm = f"loudnorm=I={target}:TP=-1.5:LRA=11"
    r = run(["ffmpeg", "-hide_banner", "-nostats", *src, "-filter_complex",
             f"{filt}[pre];[pre]{norm}:print_format=json[{label}]", "-map", f"[{label}]",
             "-f", "null", "-"], "loudness measure")
    m = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr)
    stats = json.loads(m[-1]) if m else {}
    if not m or stats.get("input_i") in ("-inf", "inf") or float(stats["input_i"]) < -70:
        return f"{filt},aresample=48000[{label}]"   # silence: nothing to normalise
    gain = target - float(stats["input_i"])
    if float(stats["input_tp"]) + gain > -1.5:
        # linear mode cannot reach the target under the peak ceiling and loudnorm would go dynamic,
        # which misses on short clips: apply the gain, then hold peaks under -2 dBFS with a limiter
        return (f"{filt},volume={gain:.2f}dB,alimiter=limit={10 ** (-2 / 20):.4f}:level=false,"
                f"aresample=48000[{label}]")
    return (f"{filt}[pre];[pre]{norm}:measured_I={stats['input_i']}:measured_TP={stats['input_tp']}"
            f":measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}"
            f":offset={stats['target_offset']}:linear=true,aresample=48000[{label}]")


def mix_sfx(events: list, sfx_dir: Path, duration: float, out_wav: Path) -> list:
    """Place every event's sound and write a normalised 48 kHz stereo WAV of exactly `duration`."""
    files, missing, placed = [], [], []
    for ev in events:
        hit = next((sfx_dir / (ev["sfx"] + e) for e in SFX_EXT if (sfx_dir / (ev["sfx"] + e)).is_file()), None)
        if hit is None:
            missing.append(ev["sfx"])
            continue
        if hit not in files:
            files.append(hit)
        placed.append((files.index(hit) + 1, ev))
    src = ["-f", "lavfi", "-t", f"{duration:.6f}", "-i", "anullsrc=r=48000:cl=stereo"]
    for f in files:
        src += ["-i", str(f)]
    parts, labels = ["[0:a]atrim=0:%.6f[base]" % duration], ["[base]"]
    for n, (idx, ev) in enumerate(placed):
        ms = round(float(ev["t"]) * 1000)
        parts.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                     f"volume={float(ev.get('vol', 1.0)):.4f},adelay={ms}:all=1[e{n}]")
        labels.append(f"[e{n}]")
    filt = ";".join(parts) + ";" + "".join(labels) + \
        f"amix=inputs={len(labels)}:duration=first:normalize=0,atrim=0:{duration:.6f}"
    final = loudnorm_args(src, filt, "out")
    run(["ffmpeg", "-y", "-hide_banner", *src, "-filter_complex", final, "-map", "[out]",
         "-c:a", "pcm_s16le", "-ar", "48000", str(out_wav)], "sfx mix")
    return sorted(set(missing))


def contact_sheet(thumbs: list, out: Path, w: int, h: int) -> None:
    tw = 320
    th = round(h * tw / w)
    sheet = Image.new("RGB", (4 * tw + 5 * 8, 2 * (th + 24) + 3 * 8), "#202020")
    d = ImageDraw.Draw(sheet)
    for n, (t, img) in enumerate(thumbs):
        cx, cy = 8 + (n % 4) * (tw + 8), 8 + (n // 4) * (th + 24 + 8)
        d.text((cx, cy), f"t={t:.2f}s", font=font(16), fill="#e0e0e0")
        sheet.paste(img.resize((tw, th), Image.BILINEAR), (cx, cy + 22))
    sheet.save(out)


def compose(timeline: Path, out: Path, sfx_dir: Path | None = None, guides: bool = False) -> dict:
    tl = load_timeline(timeline)
    cells = load_sprites(tl, timeline.parent)
    fps, (w, h), dur = tl["fps"], tl["size"], tl["duration"]
    n = round(fps * dur)
    events = sorted(({"t": float(e["t"]), "frame": math.floor(float(e["t"]) * fps + 1e-9), "sfx": e["sfx"],
                      "vol": float(e.get("vol", 1.0))} for e in tl.get("events") or []),
                    key=lambda e: (e["t"], e["sfx"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    stem = out.with_suffix("")
    with tempfile.TemporaryDirectory() as tmp:
        wav, missing = None, []
        if sfx_dir is not None:
            wav = Path(tmp) / "sfx.wav"
            missing = mix_sfx(events, sfx_dir, n / fps, wav)
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{w}x{h}", "-r", f"{fps:g}", "-i", "-"]
        if wav:
            cmd += ["-i", str(wav)]
        cmd += ["-map", "0:v"] + (["-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"] if wav else [])
        cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", "-fflags", "+bitexact", "-flags", "+bitexact", str(out)]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as e:
            raise InputError(f"ffmpeg: {e}")
        r = Renderer(tl, cells)
        picks = {round(k * (n - 1) / 7) for k in range(8)} if n >= 8 else set(range(n))
        digest, thumbs = hashlib.sha256(), []
        try:
            for i in range(n):
                img = r.frame(i / fps, guides)
                raw = img.tobytes()
                digest.update(hashlib.sha256(raw).digest())
                proc.stdin.write(raw)
                if i in picks:
                    thumbs.append((i / fps, r.frame(i / fps, True) if not guides else img))
            proc.stdin.close()
        except BrokenPipeError:
            pass
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise InputError(f"ffmpeg encode failed: {err.strip()[-400:]}")
    contact = Path(f"{stem}.contact.png")
    contact_sheet(thumbs, contact, w, h)
    log = {"timeline": timeline.name, "video": out.name, "fps": fps, "size": [w, h], "frames": n,
           "duration": n / fps, "events": events, "frames_sha256": digest.hexdigest(),
           "contact": contact.name, "audio": bool(wav), "sfx_missing": missing}
    Path(f"{stem}.events.json").write_text(json.dumps(log, indent=1) + "\n", encoding="utf-8")
    return log


# ------------------------------------------------------------------------------------ selftest

def tone_wav(path: Path, seconds: float, hz: float, rate: int = 48000) -> None:
    import wave
    import numpy as np
    t = np.arange(int(seconds * rate)) / rate
    pcm = (0.4 * np.sin(2 * np.pi * hz * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(pcm.tobytes())


def probe(path: Path) -> dict:
    r = run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
             "format=duration:stream=codec_type,nb_read_frames", "-of", "json", str(path)], "ffprobe")
    return json.loads(r.stdout)


def selftest() -> int:
    checks, failed = [], []

    def check(name: str, ok: bool) -> None:
        checks.append(name)
        if not ok:
            failed.append(name)

    check("ease ends", ease(0, "in_out") == 0 and ease(1, "in_out") == 1 and ease(0.5, "out") == 0.75)
    keys = resolve_keys([{"t": 1, "x": 10}, {"t": 0, "x": 0, "alpha": 0.5}], 64, 48)
    check("keys sorted and carried", keys[1]["alpha"] == 0.5 and keys[1]["y"] == 24)
    check("linear midpoint", sample(keys, 0.5, "linear")["x"] == 5)
    check("step holds", sample(keys, 0.9, "step")["x"] == 0)
    check("ends hold", sample(keys, -1, "linear")["x"] == 0 and sample(keys, 9, "linear")["x"] == 10)
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        Image.new("RGBA", (8, 8), (255, 200, 0, 255)).save(d / "dot.png")
        tone_wav(d / "blip.wav", 0.2, 880)
        tl = {"fps": 10, "size": [64, 48], "duration": 1.0, "safe": 0.05,
              "assets": {"dot": {"path": "dot.png", "anchor": "bc"}},
              "layers": [{"asset": "dot", "z": 1, "ease": "in_out", "keys": [{"t": 0, "x": 8, "y": 40},
                                                                            {"t": 1, "x": 56, "rot": 90}]},
                         {"asset": "dot", "z": 0, "t0": 0.5, "keys": [{"t": 0, "alpha": 0.5}]}],
              "text": [{"t0": 0, "t1": 0.5, "text": "go", "size": 12}],
              "events": [{"t": 0.3, "sfx": "blip"}, {"t": 0.7, "sfx": "blip", "vol": 0.5},
                         {"t": 0.8, "sfx": "absent"}]}
        (d / "tl.json").write_text(json.dumps(tl))
        logs = [compose(d / "tl.json", d / f"run{k}" / "p.mp4", d if k == 0 else None) for k in (0, 1)]
        check("frames == fps x duration", logs[0]["frames"] == 10)
        check("every event logged", len(logs[0]["events"]) == 3 and logs[0]["events"][0]["frame"] == 3)
        check("missing sfx listed", logs[0]["sfx_missing"] == ["absent"] and logs[0]["audio"])
        check("deterministic frames", logs[0]["frames_sha256"] == logs[1]["frames_sha256"])
        check("contact sheet", (d / "run0" / "p.contact.png").is_file())
        info = probe(d / "run0" / "p.mp4")
        v = [s for s in info["streams"] if s["codec_type"] == "video"]
        check("encoded frame count", int(v[0]["nb_read_frames"]) == 10)
        check("duration within 1/fps", abs(float(info["format"]["duration"]) - 1.0) <= 0.1)
        check("audio muxed", any(s["codec_type"] == "audio" for s in info["streams"]))
        dot = lambda key: {"layers": [{"asset": "dot", "keys": [key]}]}  # noqa: E731
        for name, bad in (("odd size", {"size": [63, 48]}), ("no frames", {"duration": 0.01}),
                          ("key without t", dot({"x": 1})), ("x as text", dot({"t": 0, "x": "a"})),
                          ("layers as an object", {"layers": {"a": 1}}), ("text without text", {"text": [{"t0": 0}]}),
                          ("asset without path", {"assets": {"dot": {"anchor": "c"}}}),
                          ("event past the last frame", {"duration": 0.94, "events": [{"t": 0.92, "sfx": "b"}]}),
                          ("event t as text", {"events": [{"t": "x", "sfx": "blip"}]})):
            (d / "bad.json").write_text(json.dumps({**tl, **bad}))
            try:
                load_timeline(d / "bad.json")
                check(f"refused: {name}", False)
            except TimelineError:
                check(f"refused: {name}", True)
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": len(checks), "failed": failed}))
    return 1 if failed else 0


def main(argv: list) -> int:
    if argv in (["selftest"], ["--selftest"]):
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("timeline", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sfx-dir", type=Path)
    ap.add_argument("--guides", action="store_true", help="draw the title-safe rectangle into the video")
    a = ap.parse_args(argv)
    try:
        log = compose(a.timeline, a.out, a.sfx_dir, a.guides)
    except TimelineError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 2
    except InputError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 3
    print(json.dumps({"ok": True, **{k: log[k] for k in ("video", "frames", "duration", "frames_sha256",
                                                         "audio", "sfx_missing")}, "events": len(log["events"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
