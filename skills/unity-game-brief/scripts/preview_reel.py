#!/usr/bin/env python3
"""preview_reel.py — join preview clips into one reel with title cards, music and every clip's SFX.

A reel is what a person watches in one sitting to judge the game before code:
a title card, then each simulated-gameplay preview behind a card that says
what it shows. Sound is rebuilt for the whole reel, so a clip's SFX land at the
same moment they did in the clip, over one music bed, at one loudness.

usage:
    preview_reel.py REEL.json --out reel.mp4
    preview_reel.py selftest            (or --selftest)

REEL.json (paths relative to the reel's folder):
    {"title": "Courier run: previews",      optional opening card
     "title_hold": 2.0,                      seconds of the opening card
     "size": [1024, 576], "fps": 30,         optional; default: the first clip's
     "segments": [{"clip": "run/preview.mp4", "title": "Lane switch",
                   "sub": "gate open window 0.8 s", "hold": 1.5}, ...],
     "music": {"path": "music.wav", "vol": 0.5},   optional, or just a path; looped to the length
     "sfx_dir": "sfx",                       optional, see below
     "card": {"bg": "#101418", "fg": "#f0f0f0", "font": "fonts/Card.ttf"}}   font optional

  A segment with a `title` or `sub` is preceded by a card of `hold` seconds
  (default 1.5). Each clip is scaled to fit and padded to `size`, at `fps`.
  A clip's length and events come from `<clip stem>.events.json` (written by
  preview_compose.py) when it is there, else from ffprobe. Holds are rounded
  to whole frames. Without `font`, cards use Pillow's built-in face: Latin
  letters, digits and ASCII punctuation only; a typographic dash or CJK text
  draws as boxes, so give `font` (a TTF/OTF shipped with the project).

Sound: with `sfx_dir`, each clip's logged events are placed again from the
sound files in it, offset by the clip's start in the reel; without it, each
clip's own audio track (when it has one) is placed at its start. Music and SFX
are mixed (amix normalize=0), the music fades out over the last second, and the
mix is loudness-normalised to -16 LUFS integrated, -1.5 dBTP, two-pass as in
preview_compose.py.

Writes `<stem>.timeline.json`: every card and clip with start and end, every
event in reel time, `sfx_missing` (the sfx names no file in `sfx_dir` matched;
those events are silent), and the integrated loudness of the result (ebur128).

Prints one JSON line. Exit codes: 0 written; 2 the reel spec is invalid (a
wrong type, a hold <= 0, an odd or zero size); 3 an input cannot be read (a
clip, its events log, the music, `sfx_dir` not a folder), or ffmpeg failed. Python, Pillow, numpy, ffmpeg.
Uses preview_compose.py from the same folder.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preview_compose as pc  # noqa: E402

InputError, run = pc.InputError, pc.run


class ReelError(Exception):
    """The reel spec is invalid: exit 2."""


def card_image(path: Path, size: tuple, title: str, sub: str, style: dict, base: Path) -> None:
    w, h = size
    img = Image.new("RGB", (w, h), style.get("bg", "#101418"))
    d = ImageDraw.Draw(img)

    def face(px: int):
        if style.get("font"):
            try:
                return ImageFont.truetype(str(base / style["font"]), px)
            except OSError as e:
                raise InputError(f"card font: {e}")
        return pc.font(px)

    for text, px, y in ((title, max(12, h // 10), 0.45), (sub, max(10, h // 22), 0.62)):
        if text:
            f = face(px)
            l, t, r, b = d.textbbox((0, 0), text, font=f)
            d.text(((w - (r - l)) / 2 - l, h * y - (b - t) / 2 - t), text, font=f, fill=style.get("fg", "#f0f0f0"))
    img.save(path)


def clip_info(clip: Path) -> dict:
    """Length, size, fps, audio presence and events of one clip."""
    if not clip.is_file():
        raise InputError(f"clip not found: {clip.name}")
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate",
             "-of", "json", str(clip)], "ffprobe")
    info = json.loads(r.stdout)
    v = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), None)
    if v is None:
        raise InputError(f"{clip.name} has no video stream")
    num, den = (float(x) for x in v["r_frame_rate"].split("/"))
    out = {"duration": float(info["format"]["duration"]), "size": [v["width"], v["height"]], "fps": num / den,
           "audio": any(s["codec_type"] == "audio" for s in info["streams"]), "events": []}
    log = clip.with_suffix(".events.json")
    if log.is_file():
        try:
            ev = json.loads(log.read_text(encoding="utf-8"))
            out.update(duration=float(ev["duration"]), fps=float(ev["fps"]), size=list(ev["size"]),
                       events=[{"t": float(e["t"]), "sfx": str(e["sfx"]), "vol": float(e.get("vol", 1.0))}
                               for e in ev["events"]])
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            raise InputError(f"{log.name}: not a preview_compose events log: {e.__class__.__name__}: {e}")
    return out


def seconds(v, what: str) -> float:
    if not pc.isnum(v) or v <= 0:
        raise ReelError(f"{what} must be a number of seconds > 0, not {v!r}")
    return float(v)


def integrated_lufs(media: Path) -> float | None:
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(media), "-af", "ebur128", "-f", "null", "-"], "ebur128")
    m = re.findall(r"I:\s+(-?[\d.]+|-inf) LUFS", r.stderr)
    return float(m[-1]) if m and m[-1] != "-inf" else None


def build(spec_path: Path, out: Path) -> dict:
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InputError(f"cannot read {spec_path.name}: {e}")
    base = spec_path.parent
    segs = spec.get("segments") if isinstance(spec, dict) else None
    if not isinstance(segs, list) or not segs or not all(isinstance(s, dict) and isinstance(s.get("clip"), str)
                                                         and s["clip"] for s in segs):
        raise ReelError("segments: a non-empty list, each with a clip")
    for k in ("fps", "title_hold"):
        if k in spec:
            seconds(spec[k], k)
    for s in segs:
        seconds(s.get("hold", 1.5), f"segment {s['clip']}: hold")
    size = spec.get("size")
    if size is not None and not (isinstance(size, list) and len(size) == 2 and all(
            isinstance(v, int) and not isinstance(v, bool) and v > 0 and v % 2 == 0 for v in size)):
        raise ReelError("size must be [width, height], positive and even (yuv420p)")
    music = spec.get("music")
    if music is not None and not (isinstance(music, str) or isinstance(music, dict) and isinstance(
            music.get("path"), str) and pc.isnum(music.get("vol", 0.5))):
        raise ReelError("music must be a path, or {\"path\": ..., \"vol\": number}")
    style = spec.get("card") or {}
    if not isinstance(style, dict) or not all(isinstance(style.get(k, ""), str) for k in ("bg", "fg", "font")):
        raise ReelError("card must be an object of bg, fg and font strings")
    if "sfx_dir" in spec and not isinstance(spec["sfx_dir"], str):
        raise ReelError("sfx_dir must be a path")
    sfx_dir = base / spec["sfx_dir"] if spec.get("sfx_dir") else None
    if sfx_dir is not None and not sfx_dir.is_dir():
        raise InputError(f"sfx_dir is not a folder: {spec['sfx_dir']}")
    infos = [clip_info(base / s["clip"]) for s in segs]
    fps = float(spec.get("fps") or infos[0]["fps"])
    w, h = (int(v) for v in (size or infos[0]["size"]))
    if fps <= 0 or w <= 0 or h <= 0 or w % 2 or h % 2:
        raise ReelError("fps must be > 0 and size positive and even")
    pieces, t = [], 0.0

    def add(kind: str, seconds: float, **kw) -> None:
        nonlocal t
        frames = max(1, round(seconds * fps))
        pieces.append({"kind": kind, "start": round(t, 6), "end": round(t + frames / fps, 6), "frames": frames, **kw})
        t += frames / fps

    if spec.get("title"):
        add("card", float(spec.get("title_hold", 2.0)), title=spec["title"], sub=spec.get("sub", ""))
    for s, info in zip(segs, infos):
        if s.get("title") or s.get("sub"):
            add("card", float(s.get("hold", 1.5)), title=s.get("title", ""), sub=s.get("sub", ""))
        add("clip", info["duration"], clip=s["clip"], info=info)
    total = t
    events = [{"t": round(p["start"] + float(e["t"]), 6), "sfx": e["sfx"], "vol": float(e.get("vol", 1.0)),
               "clip": p["clip"]} for p in pieces if p["kind"] == "clip" for e in p["info"]["events"]]
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # ---- video: cards and clips through one concat filter
        vin, vf = [], []
        for n, p in enumerate(pieces):
            if p["kind"] == "card":
                png = tmp / f"card{n}.png"
                card_image(png, (w, h), p["title"], p["sub"], style, base)
                vin += ["-loop", "1", "-framerate", f"{fps:g}", "-t", f"{p['frames'] / fps:.6f}", "-i", str(png)]
            else:
                vin += ["-i", str(base / p["clip"])]
            vf.append(f"[{n}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                      f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={style.get('bg', '#101418')},setsar=1,"
                      f"fps={fps:g},trim=end_frame={p['frames']},setpts=PTS-STARTPTS,format=yuv420p[v{n}]")
        vf.append("".join(f"[v{n}]" for n in range(len(pieces))) + f"concat=n={len(pieces)}:v=1:a=0[vout]")
        # ---- audio: silent bed of the exact length, music, then SFX or clip audio
        ain = ["-f", "lavfi", "-t", f"{total:.6f}", "-i", "anullsrc=r=48000:cl=stereo"]
        af, labels = [f"[0:a]atrim=0:{total:.6f}[a0]"], ["[a0]"]
        if music:
            music = {"path": music} if isinstance(music, str) else music
            if not (base / music["path"]).is_file():
                raise InputError(f"music not found: {music['path']}")
            ain += ["-stream_loop", "-1", "-i", str(base / music["path"])]
            fade = max(0.0, total - 1.0)
            af.append(f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{total:.6f},"
                      f"volume={float(music.get('vol', 0.5)):.4f},afade=t=out:st={fade:.6f}:d=1[m]")
            labels.append("[m]")
        idx = 2 if music else 1   # next ffmpeg input index
        placed, missing = [], set()
        if sfx_dir:
            files = {}
            for e in events:
                hit = next((sfx_dir / (e["sfx"] + x) for x in pc.SFX_EXT if (sfx_dir / (e["sfx"] + x)).is_file()), None)
                if hit is None:
                    missing.add(e["sfx"])
                    continue
                if hit not in files:
                    files[hit] = idx
                    ain += ["-i", str(hit)]
                    idx += 1
                placed.append((files[hit], e["t"], e["vol"]))
        else:
            for p in pieces:
                if p["kind"] == "clip" and p["info"]["audio"]:
                    ain += ["-i", str(base / p["clip"])]
                    placed.append((idx, p["start"], 1.0))
                    idx += 1
        for n, (i, at, vol) in enumerate(placed):
            af.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={vol:.4f},"
                      f"adelay={round(at * 1000)}:all=1[s{n}]")
            labels.append(f"[s{n}]")
        mix = ";".join(af) + ";" + "".join(labels) + \
            f"amix=inputs={len(labels)}:duration=first:normalize=0,atrim=0:{total:.6f}"
        wav = tmp / "mix.wav"
        run(["ffmpeg", "-y", "-hide_banner", *ain, "-filter_complex", pc.loudnorm_args(ain, mix, "aout"),
             "-map", "[aout]", "-c:a", "pcm_s16le", "-ar", "48000", str(wav)], "reel audio")
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *vin, "-i", str(wav),
             "-filter_complex", ";".join(vf), "-map", "[vout]", "-map", f"{len(pieces)}:a",
             "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", f"{fps:g}",
             "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
             "-fflags", "+bitexact", "-flags", "+bitexact", str(out)], "reel encode")
    lufs = integrated_lufs(out)
    log = {"reel": out.name, "fps": fps, "size": [w, h], "duration": round(total, 6),
           "frames": sum(p["frames"] for p in pieces),
           "pieces": [{k: v for k, v in p.items() if k != "info"} for p in pieces],
           "events": events, "music": bool(music), "sfx": "events" if sfx_dir else "clip audio",
           "sfx_missing": sorted(missing), "integrated_lufs": lufs}
    out.with_suffix(".timeline.json").write_text(json.dumps(log, indent=1) + "\n", encoding="utf-8")
    return log


# ------------------------------------------------------------------------------------ selftest

def selftest() -> int:
    checks, failed = [], []

    def check(name: str, ok: bool) -> None:
        checks.append(name)
        if not ok:
            failed.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        Image.new("RGBA", (8, 8), (90, 200, 255, 255)).save(d / "dot.png")
        (d / "sfx").mkdir()
        pc.tone_wav(d / "sfx" / "blip.wav", 0.15, 1200)
        pc.tone_wav(d / "music.wav", 1.0, 220)
        for k in (0, 1):
            tl = {"fps": 10, "size": [96, 54], "duration": 2.0,
                  "assets": {"dot": {"path": "dot.png"}},
                  "layers": [{"asset": "dot", "keys": [{"t": 0, "x": 10}, {"t": 2, "x": 86}]}],
                  "events": [{"t": 0.5 + k * 0.2, "sfx": "blip"}, {"t": 1.5, "sfx": "blip", "vol": 0.6}]}
            (d / f"c{k}.json").write_text(json.dumps(tl))
            pc.compose(d / f"c{k}.json", d / f"c{k}.mp4", d / "sfx")
        reel = {"title": "Reel", "title_hold": 1.0, "music": {"path": "music.wav", "vol": 0.5}, "sfx_dir": "sfx",
                "segments": [{"clip": "c0.mp4", "title": "One", "sub": "first", "hold": 1.0},
                             {"clip": "c1.mp4"}]}
        (d / "reel.json").write_text(json.dumps(reel))
        log = build(d / "reel.json", d / "out" / "reel.mp4")
        check("pieces: card, card, clip, clip", [p["kind"] for p in log["pieces"]] == ["card", "card", "clip", "clip"])
        check("total length", abs(log["duration"] - 6.0) < 1e-6 and log["frames"] == 60)
        check("events offset by start", [e["t"] for e in log["events"]] == [2.5, 3.5, 4.7, 5.5])
        check("timeline written", (d / "out" / "reel.timeline.json").is_file())
        lufs = log["integrated_lufs"]
        check("loudness -16 +/- 1 LUFS", lufs is not None and abs(lufs + 16) <= 1.0)
        info = pc.probe(d / "out" / "reel.mp4")
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        check("encoded frame count", int(v["nb_read_frames"]) == 60)
        check("duration within 1/fps", abs(float(info["format"]["duration"]) - 6.0) <= 0.1)
        check("no sfx missing", log["sfx_missing"] == [])
        for name, bad, err in (("empty segments", {"segments": []}, ReelError),
                               ("size as text", {**reel, "size": "big"}, ReelError),
                               ("zero size", {**reel, "size": [0, 0]}, ReelError),
                               ("hold as text", {**reel, "title_hold": "long"}, ReelError),
                               ("music without path", {**reel, "music": {"vol": 1}}, ReelError),
                               ("sfx_dir not a folder", {**reel, "sfx_dir": "nowhere"}, InputError),
                               ("corrupt events log", reel, InputError)):
            (d / "bad.json").write_text(json.dumps(bad))
            if name == "corrupt events log":
                (d / "c1.events.json").write_text("{not json")
            try:
                build(d / "bad.json", d / "bad.mp4")
                check(f"refused: {name}", False)
            except err:
                check(f"refused: {name}", True)
            except Exception:  # noqa: BLE001 - the wrong exception is the failure checked for
                check(f"refused: {name}", False)
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": len(checks), "failed": failed,
                      "integrated_lufs": lufs}))
    return 1 if failed else 0


def main(argv: list) -> int:
    if argv in (["selftest"], ["--selftest"]):
        return selftest()
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("reel", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        log = build(a.reel, a.out)
    except ReelError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 2
    except InputError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 3
    print(json.dumps({"ok": True, "reel": log["reel"], "duration": log["duration"], "frames": log["frames"],
                      "events": len(log["events"]), "sfx_missing": log["sfx_missing"],
                      "integrated_lufs": log["integrated_lufs"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
