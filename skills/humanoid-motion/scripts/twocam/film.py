#!/usr/bin/env python3
"""film.py — one two-camera clip from the reference frame and a prompt, on local MiniMax H3 image-to-video.

Replaces patch-gg/anymove's mocap/generate.py and mocap/fal.py (the fal queue client), commit
7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0: the clip is made on a self-hosted ComfyUI through
skills/comfyui-asset-generation/scripts/comfy_asset_client.py and templates/minimax_h3_i2v_api.json instead of on
fal. The output folder keeps upstream's layout (runs/<character>/videos/<move>/s<seed>/), so the capture stages read
it unchanged; the clip is h3.mp4.

usage:
    film.py run REF.png PROMPT.txt OUT_DIR --seed 1 --server-label NAME [--width 1376 --height 768 --length 124]
            [--object-info OBJECT_INFO.json] [--licence-id ID] [--client PATH] [--workflow PATH] [--dry-run]
    film.py object-info --out OBJECT_INFO.json [--server URL] [--config PATH]
    film.py --selftest
`run` sets node 1 (the reference, uploaded under a name made from its content), node 7 (prompt, width, height, length) and node 8 (noise seed) of the
template, runs the client, keeps the downloaded video's frames and discards its audio (ffmpeg -an, stream copy;
without ffmpeg the file keeps its audio track, which detect.py never reads, and a warning says so), and writes
OUT_DIR/h3.mp4 and OUT_DIR/film.json. The server is named by --server-label, never by its address.
`object-info` saves the server's /object_info/MiniMaxH3ImageToVideo (the address comes from --server,
COMFYUI_SERVER_URL or the client's config file, and is never printed); pass it to `run --object-info` so the
width and height are checked against the node's own min, max and step before anything is submitted.

Gates (exit 2): film.size_step (width and height multiples of 32, or of the node's step when --object-info is
given), film.size_range (inside the node's min and max, with --object-info), film.aspect (16:9 within 1 %),
film.frames (the clip has --length frames, counted by opencv, else by ffprobe -count_frames; with neither the
gate is listed and fails). A size gate that fails stops the run before
submission.
The report's record (for art-asset-registry ingest) is the client's, with this script as the tool and
licence {"source": "minimax-h3-local", "territory": {"excludes": ["US", "EU", "UK", "KR"]}}: the H3 community
licence restricts outputs outside its territory. A clip solved from this video names it as its parent or a
depends-on link, so the territory rule reaches the motion too.
Exit codes: 0 done, 2 a gate failed, 1 refused input or the client failed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMFY = HERE.parents[2] / "comfyui-asset-generation"
CLIENT = COMFY / "scripts" / "comfy_asset_client.py"
WORKFLOW = COMFY / "templates" / "minimax_h3_i2v_api.json"
DEFAULT_CONFIG = Path.home() / ".codex" / "comfyui-asset-generation" / "config.json"
NODE = "MiniMaxH3ImageToVideo"
LICENCE = {"source": "minimax-h3-local", "territory": {"excludes": ["US", "EU", "UK", "KR"]}}


def sha256(path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def int_spec(object_info: dict, name: str) -> dict:
    node = object_info.get(NODE, object_info)
    req = (node.get("input") or {}).get("required") or {}
    spec = req.get(name)
    if not (isinstance(spec, list) and len(spec) > 1 and isinstance(spec[1], dict)):
        raise ValueError(f"object_info has no {NODE} input '{name}'")
    return spec[1]


def size_gates(width: int, height: int, object_info: dict | None) -> list:
    step_w = step_h = 32
    gates = []
    if object_info is not None:
        sw, sh = int_spec(object_info, "width"), int_spec(object_info, "height")
        step_w, step_h = int(sw.get("step", 32)), int(sh.get("step", 32))
        in_range = (sw.get("min", 0) <= width <= sw.get("max", 1 << 30)) and (sh.get("min", 0) <= height <= sh.get("max", 1 << 30))
        gates.append({"name": "film.size_range", "value": [width, height],
                      "limit": [[sw.get("min"), sw.get("max")], [sh.get("min"), sh.get("max")]], "pass": bool(in_range)})
    gates.insert(0, {"name": "film.size_step", "value": [width, height], "limit": [step_w, step_h],
                     "pass": width % step_w == 0 and height % step_h == 0})
    gates.append({"name": "film.aspect", "value": round(width / height, 4), "limit": "16/9 within 1 %",
                  "pass": abs(width / height / (16 / 9) - 1) <= 0.01})
    return gates


def ffprobe_frames(path) -> int | None:
    """The decoded frame count of the first video stream by ffprobe -count_frames; None without ffprobe."""
    fp = shutil.which("ffprobe")
    if not fp:
        return None
    r = subprocess.run([fp, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return int(r.stdout.strip().split(",")[0]) if r.returncode == 0 else None
    except ValueError:
        return None


def frame_count(path) -> tuple:
    """(frames, how): read with opencv, else counted by ffprobe; (None, "none") when neither can."""
    try:
        import cv2
    except ImportError:
        cv2 = None
    if cv2 is not None:
        cap = cv2.VideoCapture(str(path))
        if cap.isOpened():
            n = 0
            while cap.read()[0]:
                n += 1
            cap.release()
            return n, "opencv"
        cap.release()
    n = ffprobe_frames(path)
    return (n, "ffprobe") if n is not None else (None, "none")


def strip_audio(src: Path, dst: Path) -> bool:
    ff = shutil.which("ffmpeg")
    if ff:
        r = subprocess.run([ff, "-loglevel", "error", "-y", "-i", str(src), "-map", "0:v:0", "-c:v", "copy", "-an",
                            str(dst)], capture_output=True, text=True)
        if r.returncode == 0 and dst.exists() and dst.stat().st_size:
            return True
    shutil.copyfile(src, dst)
    return False


def upload_copy(a) -> Path:
    """The reference copied into OUT_DIR under a name made from its content (ref_<sha256 12>.png): the server
    keeps an upload whose name it already holds, so a fixed name would feed another character's frame to node 1."""
    h = sha256(a.ref)
    dst = Path(a.out_dir) / f"ref_{h[:12]}{Path(a.ref).suffix or '.png'}"
    Path(a.out_dir).mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copyfile(a.ref, dst)
    return dst


def client_cmd(a, ref: Path) -> list:
    cmd = [sys.executable, str(a.client), "--workflow", str(a.workflow), "--output-dir", str(Path(a.out_dir) / "raw"),
           "--upload", str(ref), "--set", f"1.image={ref.name}", "--set", f"7.prompt=@{a.prompt}",
           "--set", f"7.width={a.width}", "--set", f"7.height={a.height}", "--set", f"7.length={a.length}",
           "--set", f"8.noise_seed={a.seed}", "--server-label", a.server_label]
    if a.job_log:
        cmd += ["--job-log", str(a.job_log)]
    return cmd


def run_film(a) -> tuple:
    if "://" in a.server_label:
        raise ValueError("--server-label names the machine, never its address")
    for p in (a.ref, a.prompt, a.client, a.workflow):
        if not Path(p).is_file():
            raise ValueError(f"missing: {p}")
    oi = json.loads(Path(a.object_info).read_text(encoding="utf-8")) if a.object_info else None
    gates = size_gates(a.width, a.height, oi)
    out = {"tool": "film.py", "op": "run", "out_dir": str(a.out_dir), "seed": a.seed, "size": [a.width, a.height],
           "length": a.length, "server_label": a.server_label, "gates": gates, "warnings": []}
    if oi is None:
        out["warnings"].append("width/height not checked against the server's node: run `film.py object-info` once "
                               "and pass --object-info")
    if not all(g["pass"] for g in gates):
        out["ok"] = False
        return out, 2
    if a.dry_run:
        h = sha256(a.ref)
        cmd = client_cmd(a, Path(a.out_dir) / f"ref_{h[:12]}{Path(a.ref).suffix or '.png'}")
        out.update({"ok": True, "dry_run": True, "client_args": cmd[2:]})
        return out, 0
    cmd = client_cmd(a, upload_copy(a))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        out.update({"ok": False, "error": f"comfy_asset_client exited {r.returncode}: {r.stderr.strip()[-400:]}"})
        return out, 1
    try:
        rep = json.loads(r.stdout)
    except json.JSONDecodeError:
        out.update({"ok": False, "error": "comfy_asset_client printed no JSON report"})
        return out, 1
    videos = [Path(p) for p in rep.get("outputs", []) if str(p).lower().endswith((".mp4", ".webm", ".mov", ".mkv"))]
    if not videos:
        out.update({"ok": False, "error": f"no video among the outputs {rep.get('outputs')}"})
        return out, 1
    clip = Path(a.out_dir) / "h3.mp4"
    silent = strip_audio(videos[0], clip)
    if not silent:
        out["warnings"].append("ffmpeg not found or failed: h3.mp4 keeps the audio track (detect.py reads frames only)")
    n, how = frame_count(clip)
    frames = {"name": "film.frames", "value": n, "limit": a.length, "pass": n == a.length, "counted_by": how}
    if n is None:
        frames["note"] = "neither opencv nor ffprobe could count the frames: install one and run again"
    gates.append(frames)
    record = dict(rep.get("record") or {})
    record["tool"] = {"skill": "humanoid-motion", "script": "twocam/film.py"}
    record["files"] = [{"path": str(clip.resolve()), "sha256": sha256(clip), "bytes": clip.stat().st_size}]
    lic = dict(LICENCE)
    if a.licence_id:
        lic["id"] = a.licence_id
    record["licence"] = lic
    record["verdict"] = "green" if all(g["pass"] for g in gates) else "failed"
    out.update({"video": str(clip), "audio_discarded": silent, "raw_outputs": rep.get("outputs"),
                "prompt_id": rep.get("prompt_id"), "elapsed_seconds": rep.get("elapsed_seconds"),
                "workflow_sha256": rep.get("workflow_sha256"), "record": record,
                "ok": all(g["pass"] for g in gates)})
    (Path(a.out_dir) / "film.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out, 0 if out["ok"] else 2


def fetch_object_info(a) -> tuple:
    cfg = {}
    if Path(a.config).exists():
        cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    base = a.server or os.environ.get("COMFYUI_SERVER_URL") or cfg.get("server_url")
    if not base:
        return {"tool": "film.py", "ok": False, "error": "no server: --server, COMFYUI_SERVER_URL or the client config"}, 1
    try:
        with urllib.request.urlopen(base.rstrip("/") + f"/object_info/{NODE}", timeout=30) as resp:
            doc = json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:  # the address stays out of the message
        return {"tool": "film.py", "ok": False, "error": f"cannot read /object_info/{NODE}: {type(exc).__name__}"}, 1
    Path(a.out).write_text(json.dumps(doc, indent=1), encoding="utf-8")
    try:
        spec = {k: int_spec(doc, k) for k in ("width", "height", "length")}
    except ValueError as exc:
        return {"tool": "film.py", "ok": False, "out": a.out, "error": str(exc)}, 1
    return {"tool": "film.py", "op": "object-info", "out": a.out, "spec": spec, "ok": True}, 0


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser():
    ap = UsageParser(prog="film.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("ref"); r.add_argument("prompt"); r.add_argument("out_dir")
    r.add_argument("--seed", type=int, required=True); r.add_argument("--server-label", required=True)
    r.add_argument("--width", type=int, default=1376); r.add_argument("--height", type=int, default=768)
    r.add_argument("--length", type=int, default=124); r.add_argument("--object-info")
    r.add_argument("--licence-id"); r.add_argument("--client", default=str(CLIENT))
    r.add_argument("--workflow", default=str(WORKFLOW)); r.add_argument("--job-log")
    r.add_argument("--dry-run", action="store_true")
    o = sub.add_parser("object-info")
    o.add_argument("--out", required=True); o.add_argument("--server"); o.add_argument("--config", default=str(DEFAULT_CONFIG))
    return ap


FAKE_CLIENT = r'''
import argparse, json, sys, pathlib
ap = argparse.ArgumentParser(); ap.add_argument("--workflow"); ap.add_argument("--output-dir")
ap.add_argument("--upload", action="append"); ap.add_argument("--set", action="append"); ap.add_argument("--server-label")
ap.add_argument("--job-log")
a = ap.parse_args()
if any(s.startswith("8.noise_seed=13") for s in a.set):
    print("boom", file=sys.stderr); sys.exit(1)
d = pathlib.Path(a.output_dir); d.mkdir(parents=True, exist_ok=True)
sets = dict(s.split("=", 1) for s in a.set)
n = int(sets["7.length"]) - (1 if sets["8.noise_seed"] == "7" else 0)
p = d / "minimax_h3_i2v_00001_.mp4"
try:
    import cv2, numpy as np
    vw = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 24, (int(sets["7.width"]) // 8, int(sets["7.height"]) // 8))
    for i in range(n):
        vw.write(np.full((int(sets["7.height"]) // 8, int(sets["7.width"]) // 8, 3), i % 255, np.uint8))
    vw.release()
except ImportError:   # no opencv: ffmpeg's test source, else a stand-in that names its frame count
    import shutil, subprocess
    ff = shutil.which("ffmpeg")
    w, h = int(sets["7.width"]) // 8, int(sets["7.height"]) // 8
    if not ff or subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={w}x{h}:r=24",
                                 "-frames:v", str(n), "-c:v", "mpeg4", str(p)]).returncode:
        p.write_bytes(f"FAKEFRAMES {n}".encode())
(d.parent / "sets.json").write_text(json.dumps(sets))
print(json.dumps({"prompt_id": "x", "outputs": [str(p)], "record": {"tool": {"skill": "comfyui-asset-generation"},
      "params": {"server_label": a.server_label}, "inputs": [], "files": [], "verdict": "green"}}))
'''


def selftest() -> int:
    checks = []

    def check(name, cond, **kw):
        checks.append({"name": name, "pass": bool(cond), **kw})

    real = globals()["frame_count"]

    def counted(path):   # a machine with neither opencv nor ffmpeg: read the stand-in's own count
        n, how = real(path)
        data = Path(path).read_bytes()[:32] if n is None and Path(path).exists() else b""
        return (int(data.split()[1]), "stand-in") if data.startswith(b"FAKEFRAMES") else (n, how)

    globals()["frame_count"] = counted
    try:
        return _selftest(check, checks)
    finally:
        globals()["frame_count"] = real


def _selftest(check, checks) -> int:
    import contextlib
    import io
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "client.py").write_text(FAKE_CLIENT)
        (td / "ref.png").write_bytes(b"\x89PNG fake")
        (td / "prompt.txt").write_text("Animate ...\n")
        oi = {NODE: {"input": {"required": {"width": ["INT", {"min": 256, "max": 1920, "step": 32}],
                                            "height": ["INT", {"min": 256, "max": 1088, "step": 32}],
                                            "length": ["INT", {"min": 9, "max": 401, "step": 4}]}}}}
        (td / "oi.json").write_text(json.dumps(oi))
        base = ["run", str(td / "ref.png"), str(td / "prompt.txt")]
        tail = ["--server-label", "studio-gpu", "--client", str(td / "client.py"), "--workflow", str(WORKFLOW),
                "--object-info", str(td / "oi.json")]

        def go(args):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(args)
            return code, json.loads(buf.getvalue())

        out = td / "runs" / "runner" / "videos" / "jump_punch" / "s1"
        code, r = go(base + [str(out), "--seed", "1"] + tail)
        sets = json.loads((out / "sets.json").read_text()) if (out / "sets.json").exists() else {}
        check("a clip is filmed, exit 0", code == 0, code=code, err=r.get("error"))
        check("node 7 gets width, height, length and the prompt file", sets.get("7.width") == "1376" and
              sets.get("7.height") == "768" and sets.get("7.length") == "124" and sets.get("7.prompt", "").startswith("@"))
        check("node 8 gets the seed, node 1 the upload", sets.get("8.noise_seed") == "1"
              and sets.get("1.image", "").startswith("ref_") and (out / sets.get("1.image", "-")).exists())
        first = sets.get("1.image")
        (td / "ref2.png").write_bytes(b"\x89PNG another character")
        out2 = td / "runs" / "courier2" / "videos" / "jump_punch" / "s1"
        go(["run", str(td / "ref2.png"), str(td / "prompt.txt"), str(out2), "--seed", "1"] + tail)
        second = json.loads((out2 / "sets.json").read_text()).get("1.image") if (out2 / "sets.json").exists() else None
        check("two characters' references upload under different names", first and second and first != second)
        check("h3.mp4 in upstream's folder layout", (out / "h3.mp4").exists() and (out / "film.json").exists())
        check("licence carries the H3 territory", r.get("record", {}).get("licence") == LICENCE)
        check("no address in the report", "://" not in json.dumps(r))
        code, r = go(base + [str(td / "b"), "--seed", "1", "--width", "1365"] + tail)
        check("a width off the 32 step fails before submission, exit 2", code == 2 and not (td / "b").exists())
        code, r = go(base + [str(td / "c"), "--seed", "1", "--width", "2048", "--height", "1152"] + tail)
        check("a size above the node's max fails film.size_range, exit 2",
              code == 2 and not next(g for g in r["gates"] if g["name"] == "film.size_range")["pass"])
        code, r = go(base + [str(td / "d"), "--seed", "1", "--width", "768"] + tail)
        check("a square canvas fails film.aspect, exit 2", code == 2)
        n, how = globals()["frame_count"](out / "h3.mp4")
        if n is not None:
            code, r = go(base + [str(td / "e"), "--seed", "7"] + tail)
            check("a clip one frame short fails film.frames, exit 2", code == 2)
            if how == "opencv" and shutil.which("ffprobe"):
                check("ffprobe counts what opencv reads", ffprobe_frames(out / "h3.mp4") == n)
        before = globals()["frame_count"]
        globals()["frame_count"] = lambda path: (None, "none")   # no opencv, no ffprobe
        try:
            code, r = go(base + [str(td / "e2"), "--seed", "1"] + tail)
        finally:
            globals()["frame_count"] = before
        fg = [g for g in r.get("gates", []) if g["name"] == "film.frames"]
        check("with no way to count frames film.frames is listed and fails, exit 2",
              code == 2 and len(fg) == 1 and not fg[0]["pass"] and fg[0]["value"] is None)
        code, r = go(base + [str(td / "f"), "--seed", "13"] + tail)
        check("a client failure is exit 1", code == 1)
        code, r = go(base + [str(td / "g"), "--seed", "1", "--server-label", "http://example.invalid:8188",
                             "--client", str(td / "client.py"), "--workflow", str(WORKFLOW)])
        check("an address as the label is refused, exit 1", code == 1)
        code, r = go(base + [str(td / "h"), "--seed", "1", "--dry-run"] + tail)
        check("dry run lists the client arguments", code == 0 and "--server-label" in r["client_args"])
    ok = all(c["pass"] for c in checks)
    print(json.dumps({"tool": "film.py", "selftest": "pass" if ok else "fail", "checks": len(checks),
                      "failed": [c for c in checks if not c["pass"]]}))
    return 0 if ok else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv or argv[:1] == ["selftest"]:
        return selftest()
    a = parser().parse_args(argv)
    try:
        out, code = run_film(a) if a.cmd == "run" else fetch_object_info(a)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        out, code = {"tool": "film.py", "ok": False, "error": f"refused: {exc}"}, 1
    print(json.dumps(out))
    return code


if __name__ == "__main__":
    sys.exit(main())
