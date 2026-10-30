#!/usr/bin/env python3
"""twocam.py — the two-camera route's stages for one character, in upstream's folder layout, on Windows, macOS or Linux.

Ported from patch-gg/anymove (https://github.com/patch-gg/anymove), tools/_env.sh, tools/dataset.sh,
tools/train.sh, tools/film.sh and tools/capture.sh, commit 7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e,
Apache License 2.0. Changes from upstream: one pure-Python script with a subcommand per stage (no bash, so a
Windows GPU host runs it as is); the character's files live under RUNS/<character>/ (rig/, ref/, dataset/,
reader.pt, prompts/, videos/, clips/) instead of assets/; filming goes through film.py (local MiniMax H3 on
ComfyUI) instead of fal; the dataset is split over a few Blender processes with the CPU threads shared between them
and a log per process; capture solves with the despike on, runs motion_metrics on the solve, carries on past a
failed gate (exit 2) so the overlay, fit and GLB are there to look at, and stops on an error (exit 1); a bake stage
keys the rig, locks the feet, measures the result and, with --render, renders it from the layout's cameras; the
showcase video was not ported.

usage (in this order; look at the first H3 take before rendering a dataset):
    twocam.py prepare CHAR RIGGED.blend [--rig NAME --body NAME --height 1.7 ...]  -> rig/{rig_info.json,twocam.blend}
    twocam.py ref     CHAR [--engine cycles] [--samples 128] [--device auto]       -> ref/ref.png
    twocam.py film    CHAR MOVE SEED --server-label NAME [--object-info OI.json]   -> videos/MOVE/sSEED/h3.mp4
    twocam.py dataset CHAR [--count 2200] [--procs 3] [--seed 500] [--engine cycles] [--device auto]
                      [--samples 8] [--scale 0.6] [--threads N] [--png-compression 0] -> dataset/, dataset_<k>.log
    twocam.py train   CHAR [--epochs N] [--batch 20] [--workers 8] [--cache] [--init OLD.pt] [--follow]
                      [--target-px PX] [--patience N]                               -> reader.pt, train.log (CUDA)
    twocam.py capture CHAR VIDEO.mp4 NAME [--device auto] [--state walk|run|idle]  -> clips/NAME/
    twocam.py bake    CHAR NAME [--render [--samples 32] [--engine cycles] [--device auto]]
                                                                     -> clips/NAME/baked.blend [baked/, baked.mp4]
    twocam.py --selftest
Every stage takes --runs DIR (env RUNS, default ./runs), --blender PATH (env BLENDER, default blender on PATH, else
the usual install folder), --python PATH (env PYTHON, default this interpreter: a venv with torch,
opencv-python-headless, transformers, numpy) and --dry-run (print the commands, run nothing). The prompt for `film`
is RUNS/CHAR/prompts/MOVE.txt (make_prompt.py). Children run with PYTHONIOENCODING=utf-8, so a console in a legacy
code page does not stop a script on a non-ASCII character. train passes --epochs and --patience only when given,
so train.py's own defaults hold: 20 epochs from scratch, 12 with --init, no plateau stop.

capture: detect.py (det.npz, overlay.mp4, detect.json) -> solve.py --samples-out --device (motion.json,
samples.json, solve.json; despike on; --device mps fits on the CPU) -> motion_metrics.py samples.json
--pops-min-move 0.03 (metrics.json) -> apply_motion.py --glb (render/animation.glb, blender.log). bake:
apply_motion.py --save keyed.blend -> contact_bake.py in Blender on the keyed rig (--legs contract --rig-info
rig_info.json, whose twocam.contract_names maps the contract onto a rig's own bone names; --readings samples.json,
so the baked samples keep the capture's readings; baked.blend, baked_samples.npz, bake.json) -> motion_metrics.py
on baked_samples.npz (bake_metrics.json) -> with --render, render_baked.py on baked.blend (baked/front, baked/side
PNG frames; baked.mp4, front | side, when ffmpeg is on the PATH; render.json). capture exits 2 on the solve's
foot_slide gates by design: the feet are locked in bake.
Prints one JSON summary (each step's exit code, seconds, log, report and failed gates, read from the file a step
writes or else from its printed JSON, indented or not); the children's progress goes to stderr.
Exit codes: 0 every step passed, 2 a gate failed in some step (the stage carries on where it can), 1 refused input
or an error (the stage stops at the step that raised).
"""
from __future__ import annotations

import argparse
import glob as globmod
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BL = HERE / "blender"
CONTACT_BAKE = HERE.parent / "contact_bake.py"
MM = HERE.parents[2] / "blender-retarget" / "scripts" / "motion_metrics.py"
MAC_BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
WIN_BLENDER_GLOB = r"C:\Program Files\Blender Foundation\Blender*\blender.exe"
TRAIN_DEFAULTS = {"batch": 20, "workers": 8}   # --epochs and --patience: train.py's own (20, or 12 with --init; 0)
DATASET_DEFAULTS = {"count": 2200, "procs": 3, "seed": 500, "engine": "cycles", "device": "auto", "samples": 8,
                    "scale": 0.6, "png_compression": 0}
POPS_MIN_MOVE = "0.03"
ECHO = {"blender": re.compile(r"^(TWOCAM_JSON|Error|Traceback|.*Exception)"),
        "train": re.compile(r"^(epoch |cache:|\d+ train / |Traceback)"), "all": re.compile(r"")}


class Refused(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):   # usage errors are refusals (exit 1), never a gate's exit 2
        raise Refused(f"{self.prog}: {message}")


# --- the environment ------------------------------------------------------------------------------------------
def default_blender(osname=None, env=None, which=shutil.which, exists=os.path.exists, glob=globmod.glob) -> str:
    """--blender, else $BLENDER, else blender on PATH, else the usual install (macOS app, newest Windows folder)."""
    osname = osname or os.name
    env = os.environ if env is None else env
    if env.get("BLENDER"):
        return env["BLENDER"]
    found = which("blender")
    if found:
        return found
    if osname == "nt":
        hits = sorted(glob(WIN_BLENDER_GLOB), key=lambda p: [int(x) for x in re.findall(r"\d+", p)] or [0])
        if hits:
            return hits[-1]
    elif exists(MAC_BLENDER):
        return MAC_BLENDER
    return "blender"


def child_env(base=None) -> dict:
    e = dict(os.environ if base is None else base)
    e["PYTHONIOENCODING"] = "utf-8"
    e["PYTHONUNBUFFERED"] = "1"
    return e


OVERRIDE = {}   # the selftest's stand-ins for Blender and Python: {"blender": [...], "python": [...]}


class Ctx:
    def __init__(self, a, osname=None, env=None):
        env = os.environ if env is None else env
        self.runs = Path(os.path.abspath(a.runs or env.get("RUNS") or "runs"))   # Blender resolves from its own cwd
        self.blender = OVERRIDE.get("blender") or ([a.blender] if a.blender else [default_blender(osname, env)])
        self.python = OVERRIDE.get("python") or [a.python or env.get("PYTHON") or sys.executable]
        self.dry = a.dry_run
        self.R = self.runs / a.char
        self.env = child_env(env)


def blender_cmd(c: Ctx, script: Path, *args, blend=None) -> list:
    return c.blender + ["-b", "--factory-startup"] + ([str(blend)] if blend else []) + ["-P", str(script), "--"] \
        + [str(x) for x in args]


def py_cmd(c: Ctx, script: Path, *args) -> list:
    return c.python + [str(script)] + [str(x) for x in args]


def need(c: Ctx, path: Path, stage: str):
    if not c.dry and not Path(path).exists():
        raise Refused(f"missing {path} (run the '{stage}' stage first)")


def step(name, cmd, log=None, report=None, carry=True, kind="python", echo=None, report_file=None) -> dict:
    return {"name": name, "cmd": [str(x) for x in cmd], "log": str(log) if log else None,
            "report": str(report) if report else None, "carry": carry, "kind": kind,
            "echo": echo or ("all" if kind == "python" else "blender"),
            "report_file": str(report_file) if report_file else None}


def solve_device(device: str) -> str:
    """capture's --device for the fit: auto and cuda as given, the CPU for mps (the fit runs in float64)."""
    return "cpu" if device == "mps" else device


_WARNED: set = set()


def gate_failed(g: dict) -> bool:
    """A gate/1 gate passes only on `pass: true`; one without a boolean `pass` has failed. The 0.34 dialect's
    `ok` is read in its place for one release, only when `pass` is absent, with one WARN."""
    if not isinstance(g, dict):
        return True
    if "pass" in g:
        return g["pass"] is not True
    if "ok" in g:
        if "gate-ok" not in _WARNED:
            _WARNED.add("gate-ok")
            print("WARN a gate carries the old key `ok`, read as `pass` (gate/1 names it `pass`)", file=sys.stderr)
        return g["ok"] is not True
    return True


def last_json(lines: list):
    """The report a script printed: the whole stdout when it is one JSON value (indented or not), else the last
    object that starts at the beginning of a line and runs to the end of the output."""
    text = "".join(lines)
    try:
        v = json.loads(text)
        return v if isinstance(v, dict) else None
    except ValueError:
        pass
    dec = json.JSONDecoder()
    starts, pos = [], 0
    for line in lines:
        if line.startswith("{"):
            starts.append(pos)
        pos += len(line)
    for at in reversed(starts):
        try:
            v, end = dec.raw_decode(text, at)
        except ValueError:
            continue
        if isinstance(v, dict) and not text[end:].strip():
            return v
    return None


def rig_name(c: Ctx) -> str:
    try:
        info = json.loads((c.R / "rig" / "rig_info.json").read_text(encoding="utf-8"))
        return ((info.get("twocam") or {}).get("objects") or {}).get("rig", "rig")
    except (OSError, ValueError):
        return "rig"


# --- the stages: each returns a list of steps (or, for dataset, one parallel step) -------------------------------
def plan(a, c: Ctx) -> list:
    R, rig, ri = c.R, c.R / "rig", c.R / "rig" / "rig_info.json"
    s = a.stage
    if s == "prepare":
        need(c, Path(a.blend), "prepare (the rigged .blend)")
        return [step("prepare", blender_cmd(c, BL / "prepare_rig.py", a.blend, rig, *a.extra), R / "prepare.log",
                     R / "prepare.json", kind="blender")]
    if s == "ref":
        need(c, rig / "twocam.blend", "prepare")
        opts = ["--engine", a.engine, "--samples", a.samples, "--device", a.device]
        return [step("ref", blender_cmd(c, BL / "render_ref.py", rig / "twocam.blend", ri, R / "ref", *opts),
                     R / "ref.log", R / "ref.json", kind="blender")]
    if s == "film":
        need(c, R / "ref" / "ref.png", "ref")
        need(c, R / "prompts" / f"{a.move}.txt", "make_prompt.py")
        out = R / "videos" / a.move / f"s{a.seed}"
        oi = a.object_info or c.env.get("OBJECT_INFO")
        cmd = py_cmd(c, HERE / "film.py", "run", R / "ref" / "ref.png", R / "prompts" / f"{a.move}.txt", out,
                     "--seed", a.seed, "--server-label", a.server_label, "--licence-id", f"{a.char}-{a.move}-s{a.seed}",
                     *(["--object-info", oi] if oi else []))
        return [step("film", cmd, None, out / "film_report.json")]
    if s == "dataset":
        need(c, rig / "twocam.blend", "prepare")
        procs = max(1, a.procs)
        threads = a.threads or max(1, (os.cpu_count() or 4) // procs)
        per = -(-a.count // procs)
        steps = []
        for k in range(procs):
            start, count = k * per, min(per, a.count - k * per)
            if count <= 0:
                continue
            steps.append(step(f"dataset_{k}", blender_cmd(
                c, BL / "render_dataset.py", rig / "twocam.blend", ri, R / "dataset", start, count, a.seed,
                "--engine", a.engine, "--device", a.device, "--samples", a.samples, "--scale", a.scale,
                "--threads", threads, "--png-compression", a.png_compression), R / f"dataset_{k}.log", None, kind="blender"))
        return [{"name": "dataset", "parallel": steps}]
    if s == "train":
        need(c, R / "dataset", "dataset")
        opts = ["--batch", a.batch, "--workers", a.workers]
        for flag in ("cache", "follow"):
            if getattr(a, flag):
                opts.append(f"--{flag}")
        for k in ("epochs", "init", "target_px", "patience", "device"):
            if getattr(a, k) is not None:
                opts += [f"--{k.replace('_', '-')}", getattr(a, k)]
        return [step("train", py_cmd(c, HERE / "train.py", R / "dataset", ri, R / "reader.pt", *opts, *a.extra),
                     R / "train.log", R / "train.json", echo="train")]
    if s == "capture":
        need(c, R / "reader.pt", "train"); need(c, R / "ref" / "ref.png", "ref"); need(c, Path(a.video), "film")
        out = R / "clips" / a.name
        return [
            step("detect", py_cmd(c, HERE / "detect.py", a.video, R / "reader.pt", R / "ref" / "ref.png", out / "det.npz",
                                  "--overlay", out / "overlay.mp4", "--device", a.device), None, out / "detect.json"),
            step("solve", py_cmd(c, HERE / "solve.py", out / "det.npz", ri, out / "motion.json", "--samples-out",
                                 out / "samples.json", "--video", a.video, "--device", solve_device(a.device)), None,
                 out / "solve.json"),
            step("metrics", py_cmd(c, MM, out / "samples.json", "--pops-min-move", POPS_MIN_MOVE, "--out",
                                   out / "metrics.json", *(["--state", a.state] if a.state else [])), None, None,
                 report_file=out / "metrics.json"),
            step("apply", blender_cmd(c, BL / "apply_motion.py", rig / "twocam.blend", ri, out / "motion.json",
                                      out / "render", "--glb"), out / "blender.log", None, carry=False, kind="blender"),
        ]
    if s == "bake":
        out = R / "clips" / a.name
        need(c, out / "motion.json", "capture")
        need(c, out / "samples.json", "capture")
        return [
            step("keyed", blender_cmd(c, BL / "apply_motion.py", rig / "twocam.blend", ri, out / "motion.json",
                                      out / "keyed", "--save", out / "keyed.blend"), out / "keyed.log", None,
                 carry=False, kind="blender"),
            step("contact_bake", blender_cmd(c, CONTACT_BAKE, "--armature", rig_name(c), "--legs", "contract",
                                             "--rig-info", ri, "--readings", out / "samples.json",
                                             "--out", out / "baked.blend", "--samples-out",
                                             out / "baked_samples.npz", "--report", out / "bake.json",
                                             "--write-on-fail", blend=out / "keyed.blend"),
                 out / "bake.log", None, kind="blender-report", report_file=out / "bake.json"),
            step("bake_metrics", py_cmd(c, MM, out / "baked_samples.npz", "--pops-min-move", POPS_MIN_MOVE, "--out",
                                        out / "bake_metrics.json"), None, None, report_file=out / "bake_metrics.json"),
        ] + ([step("render", blender_cmd(c, BL / "render_baked.py", ri, out / "baked", "--samples", a.samples,
                                         "--engine", a.engine, "--device", a.device, blend=out / "baked.blend"),
                   out / "render.log", out / "render.json", kind="blender")] if a.render else [])
    raise Refused(f"unknown stage {s}")


# --- running ----------------------------------------------------------------------------------------------------
def _pump(stream, sinks, echo, keep, proc=None):
    for line in iter(stream.readline, ""):
        for f in sinks:
            f.write(line)
            f.flush()
        if echo is not None and echo.match(line):
            sys.stderr.write(line)
            sys.stderr.flush()
        if keep is not None:
            keep.append(line)
    stream.close()
    if proc is not None:   # the end of its stdout: when the step ended, also for steps that run side by side
        proc.t_end = time.perf_counter()


def launch(st: dict, env: dict):
    """Start a step: stdout and stderr go to its log (if any); returns (proc, threads, stdout lines, log file)."""
    if st["log"]:
        Path(st["log"]).parent.mkdir(parents=True, exist_ok=True)
    if st.get("report_file"):   # an older run's report must not stand in for this one's
        Path(st["report_file"]).unlink(missing_ok=True)
    logf = open(st["log"], "w", encoding="utf-8") if st["log"] else None
    t0 = time.perf_counter()
    p = subprocess.Popen(st["cmd"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True,
                         encoding="utf-8", errors="replace", bufsize=1)
    p.t0 = t0
    out_lines = []
    sinks = [logf] if logf else []
    echo = None if st.get("quiet") else ECHO[st["echo"]]
    # a Python script's stdout is its JSON report (kept, not echoed); a Blender run's stdout is its log
    t_out = threading.Thread(target=_pump, args=(p.stdout, sinks, None if st["kind"] == "python" else echo, out_lines, p))
    t_err = threading.Thread(target=_pump, args=(p.stderr, sinks, echo, None))
    for t in (t_out, t_err):
        t.daemon = True
        t.start()
    return p, (t_out, t_err), out_lines, logf


def finish(st: dict, p, threads, out_lines, logf) -> tuple:
    code = p.wait()
    for t in threads:
        t.join()
    if logf:
        logf.close()
    rep = None
    if st["kind"].startswith("blender"):
        for line in reversed(out_lines):
            if line.startswith("TWOCAM_JSON "):
                try:
                    rep = json.loads(line[len("TWOCAM_JSON "):])
                except ValueError:
                    pass
                break
        if st["kind"] == "blender-report" and st.get("report_file") and Path(st["report_file"]).exists():
            try:
                rep = json.loads(Path(st["report_file"]).read_text(encoding="utf-8"))
            except ValueError:
                rep = None
        if st["kind"] == "blender":
            if rep is None:      # the script never reported: Blender failed to open the file or to run it
                code = code or 1
            elif code == 0 and rep.get("exit_code") not in (None, 0):
                code = int(rep["exit_code"])   # a Blender that drops the script's exit code
    else:
        rep = last_json(out_lines)
        if st.get("report_file") and Path(st["report_file"]).exists():   # the file the script wrote itself
            try:
                rep = json.loads(Path(st["report_file"]).read_text(encoding="utf-8"))
            except ValueError:
                pass
    if rep is not None and st["report"]:
        Path(st["report"]).parent.mkdir(parents=True, exist_ok=True)
        Path(st["report"]).write_text(json.dumps(rep, indent=1), encoding="utf-8")
    if code not in (0, 1, 2):
        code = 1   # a crash or a signal is an error
    return code, rep, round(getattr(p, "t_end", time.perf_counter()) - p.t0, 1)


def execute(steps: list, env: dict) -> tuple:
    rc, done = 0, []
    for st in steps:
        if "parallel" in st:
            started = [(s, *launch({**s, "quiet": True}, env)) for s in st["parallel"]]
            codes = []
            for s, p, th, lines, logf in started:
                code, rep, sec = finish(s, p, th, lines, logf)
                codes.append(code)
                done.append({"name": s["name"], "exit_code": code, "seconds": sec, "log": s["log"],
                             "gates": [g for g in (rep or {}).get("gates", []) if gate_failed(g)]})
            code = 1 if 1 in codes else 2 if 2 in codes else 0
        else:
            code, rep, sec = finish(st, *launch(st, env))
            done.append({"name": st["name"], "exit_code": code, "seconds": sec, "log": st["log"],
                         "report": st["report"] or st.get("report_file"),
                         "failed_gates": [g.get("name") for g in (rep or {}).get("gates", []) if gate_failed(g)],
                         "error": (rep or {}).get("error")})
        if code == 1 or (code == 2 and not st.get("carry", True)):
            return code, done
        rc = max(rc, code)
    return rc, done


# --- the command line -------------------------------------------------------------------------------------------
def parser() -> Parser:
    common = Parser(add_help=False, allow_abbrev=False)
    common.add_argument("--runs"); common.add_argument("--blender"); common.add_argument("--python")
    common.add_argument("--dry-run", action="store_true")
    ap = Parser(prog="twocam.py", description=__doc__.split("\n")[0], allow_abbrev=False)
    sub = ap.add_subparsers(dest="stage", required=True, parser_class=Parser)
    p = sub.add_parser("prepare", parents=[common], allow_abbrev=False); p.add_argument("char"); p.add_argument("blend")
    p = sub.add_parser("ref", parents=[common]); p.add_argument("char")
    p.add_argument("--engine", default="cycles"); p.add_argument("--samples", type=int, default=128)
    p.add_argument("--device", default="auto")
    p = sub.add_parser("film", parents=[common]); p.add_argument("char"); p.add_argument("move")
    p.add_argument("seed", type=int); p.add_argument("--server-label", required=True); p.add_argument("--object-info")
    p = sub.add_parser("dataset", parents=[common]); p.add_argument("char")
    for k, v in DATASET_DEFAULTS.items():
        p.add_argument(f"--{k.replace('_', '-')}", type=type(v), default=v)
    p.add_argument("--threads", type=int, help="Cycles threads per process (default: the CPUs / --procs)")
    p = sub.add_parser("train", parents=[common], allow_abbrev=False); p.add_argument("char")
    for k, v in TRAIN_DEFAULTS.items():
        p.add_argument(f"--{k}", type=int, default=v)
    p.add_argument("--epochs", type=int, help="train.py's default when not given: 20, or 12 with --init")
    p.add_argument("--cache", action="store_true"); p.add_argument("--follow", action="store_true")
    p.add_argument("--init"); p.add_argument("--target-px", type=float); p.add_argument("--patience", type=int)
    p.add_argument("--device")
    p = sub.add_parser("capture", parents=[common]); p.add_argument("char"); p.add_argument("video")
    p.add_argument("name"); p.add_argument("--device", default="auto"); p.add_argument("--state")
    p = sub.add_parser("bake", parents=[common]); p.add_argument("char"); p.add_argument("name")
    p.add_argument("--render", action="store_true", help="render baked.blend front and side (baked/, baked.mp4)")
    p.add_argument("--samples", type=int, default=32); p.add_argument("--engine", default="cycles")
    p.add_argument("--device", default="auto")
    return ap


def parse(argv) -> argparse.Namespace:
    a, extra = parser().parse_known_args(argv)
    if extra and a.stage not in ("prepare", "train"):
        raise Refused(f"twocam.py {a.stage}: unrecognised arguments {extra}")
    a.extra = [x for x in extra if x != "--"]
    return a


def main(argv=None, osname=None, env=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv or argv[:1] == ["selftest"]:
        return selftest()
    for stream in (sys.stdout, sys.stderr):   # a legacy-code-page console must not stop on a child's line
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    try:
        a = parse(argv)
        c = Ctx(a, osname, env)
        steps = plan(a, c)
    except Refused as exc:
        print(json.dumps({"tool": "twocam.py", "ok": False, "exit_code": 1, "error": f"refused: {exc}"}))
        return 1
    out = {"tool": "twocam.py", "stage": a.stage, "character": a.char, "runs": str(c.runs)}
    if c.dry:
        out.update({"dry_run": True, "steps": steps, "exit_code": 0, "ok": True})
        print(json.dumps(out))
        return 0
    c.R.mkdir(parents=True, exist_ok=True)
    if a.stage == "dataset":
        (c.R / "dataset").mkdir(parents=True, exist_ok=True)
    if a.stage in ("capture", "bake"):
        (c.R / "clips" / a.name).mkdir(parents=True, exist_ok=True)
    try:
        code, done = execute(steps, c.env)
    except OSError as exc:   # the Blender or Python executable is missing
        print(json.dumps({**out, "ok": False, "exit_code": 1, "error": f"{type(exc).__name__}: {exc}"}))
        return 1
    out["steps"] = done
    if a.stage == "dataset":
        out["samples"] = len(list((c.R / "dataset").glob("*_meta.json")))
    out.update({"exit_code": code, "ok": code == 0})
    print(json.dumps(out))
    return code


# --- selftest -----------------------------------------------------------------------------------------------------
FAKE = r'''
import json, os, sys, time
argv = sys.argv[1:]
blender = "-P" in argv
script = os.path.basename(argv[argv.index("-P") + 1] if blender else argv[0])
codes = json.loads(os.environ.get("FAKE_CODES", "{}"))
code = codes.get(script, 0)
args = argv[argv.index("--") + 1:] if blender and "--" in argv else argv[1:]
if script == "render_dataset.py":
    start, count = int(args[3]), int(args[4])
    os.makedirs(args[2], exist_ok=True)
    for i in range(start, start + count):
        open(os.path.join(args[2], "%05d_meta.json" % i), "w").write("{}")
    if os.environ.get("FAKE_FAIL_START") == str(start):
        code = int(os.environ.get("FAKE_FAIL_CODE", "2"))
with open(os.environ["FAKE_TRACE"], "a", encoding="utf-8") as f:
    f.write(json.dumps({"script": script, "blender": blender, "args": args}) + "\n")
print("progress \u00e9\u4e2d", file=sys.stderr)
if script == "train.py":
    print("epoch 0 val mean px error (layout pixels) front 3.0 side 3.0", file=sys.stderr)
key = "ok" if os.environ.get("FAKE_OLD_DIALECT") == script else "pass"
rep = {"schema": "gate/1", "tool": script, "pass": code == 0, "ok": code == 0,
       "gates": [{"name": "fake.gate", key: code == 0}], "exit_code": code}
if key == "ok":
    del rep["schema"], rep["pass"]
if script == "contact_bake.py" and "--report" in args:
    open(args[args.index("--report") + 1], "w").write(json.dumps(rep))
if script == "motion_metrics.py" and "--out" in args and not os.environ.get("FAKE_NO_OUT"):
    open(args[args.index("--out") + 1], "w").write(json.dumps(rep, indent=1))
silent = os.environ.get("FAKE_SILENT") == script
if blender and not silent:
    print("Blender 5.2 noise line")
    print("TWOCAM_JSON " + json.dumps(rep))
elif script == "motion_metrics.py" and not silent:
    print("a progress line {not json}")
    print(json.dumps(rep, indent=1))   # motion_metrics prints indented JSON
elif not silent:
    print(json.dumps(rep))
sys.exit(int(os.environ.get("FAKE_BLENDER_EXIT", code)) if blender else code)
'''


def selftest() -> int:
    import contextlib
    import io
    checks = []

    def check(name, cond, **kw):
        checks.append({"name": name, "pass": bool(cond), **kw})

    def go(argv, osname=None, env=None):
        buf = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = main(argv, osname, env)
        try:
            return code, json.loads(buf.getvalue().strip().splitlines()[-1]), err.getvalue()
        except (ValueError, IndexError):
            return code, {}, err.getvalue()

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        runs = td / "runs"
        R = runs / "runner"
        for f in ("rig/twocam.blend", "rig/rig_info.json", "ref/ref.png", "prompts/jump_punch.txt", "reader.pt",
                  "clips/jump_punch/motion.json", "clips/jump_punch/samples.json", "videos/jump_punch/s1/h3.mp4"):
            (R / f).parent.mkdir(parents=True, exist_ok=True)
            (R / f).write_text("{}" if f.endswith(".json") else "x")
        (R / "rig" / "rig_info.json").write_text(json.dumps({"twocam": {"objects": {"rig": "RunnerRig"}}}))
        (R / "dataset").mkdir()
        (td / "runner.blend").write_text("x")
        video = str(R / "videos" / "jump_punch" / "s1" / "h3.mp4")
        stages = {
            "prepare": ["prepare", "runner", str(td / "runner.blend"), "--height", "1.6"],
            "ref": ["ref", "runner"],
            "film": ["film", "runner", "jump_punch", "1", "--server-label", "studio-gpu"],
            "dataset": ["dataset", "runner"],
            "train": ["train", "runner", "--cache"],
            "capture": ["capture", "runner", video, "jump_punch"],
            "bake": ["bake", "runner", "jump_punch"],
        }
        # 1. dry-run command construction for every stage, as Windows and as POSIX would build it
        for osname, env in (("posix", {"RUNS": str(runs), "BLENDER": "/opt/blender/blender"}),
                            ("nt", {"RUNS": str(runs), "BLENDER": r"C:\Blender\blender.exe"})):
            plans = {}
            for st, argv in stages.items():
                code, r, _ = go(argv + ["--dry-run"], osname, env)
                plans[st] = r.get("steps", [])
                check(f"{osname}: {st} dry run, exit 0", code == 0 and plans[st], code=code, err=r.get("error"))
            bl = env["BLENDER"]
            flat = lambda st: [s for x in plans[st] for s in (x.get("parallel") or [x])]
            ok = all(s["cmd"][:3] == [bl, "-b", "--factory-startup"] for st in ("prepare", "ref", "dataset")
                     for s in flat(st))
            check(f"{osname}: Blender stages start with $BLENDER -b --factory-startup", ok)
            pr = flat("prepare")[0]["cmd"]
            check(f"{osname}: prepare passes its extra options on", pr[-2:] == ["--height", "1.6"]
                  and pr[pr.index("--") + 2] == str(R / "rig"))
            ds = flat("dataset")
            ranges = [(int(s["cmd"][s["cmd"].index("--") + 4]), int(s["cmd"][s["cmd"].index("--") + 5])) for s in ds]
            check(f"{osname}: dataset = 3 processes covering 2,200 samples exactly", len(ds) == 3
                  and sorted(i for a, n in ranges for i in range(a, a + n)) == list(range(2200)), ranges=ranges)
            o = ds[0]["cmd"]
            check(f"{osname}: dataset passes engine, device, samples, scale, threads and PNG compression",
                  o[o.index("--engine") + 1] == "cycles" and o[o.index("--device") + 1] == "auto"
                  and o[o.index("--samples") + 1] == "8" and o[o.index("--scale") + 1] == "0.6"
                  and o[o.index("--png-compression") + 1] == "0"
                  and int(o[o.index("--threads") + 1]) >= 1 and all(s["log"].endswith(f"dataset_{k}.log")
                                                                     for k, s in enumerate(ds)))
            t = flat("train")[0]["cmd"]
            check(f"{osname}: train --batch 20, --cache passed; no --epochs, --patience or --target-px unless given "
                  "(train.py's own defaults: 20 epochs, 12 with --init, no plateau stop)",
                  t[t.index("--batch") + 1] == "20" and "--cache" in t
                  and not {"--epochs", "--patience", "--target-px"} & set(t))
            _, rw, _ = go(stages["train"] + ["--init", "old.pt", "--dry-run"], osname, env)
            _, rg, _ = go(stages["train"] + ["--epochs", "7", "--patience", "3", "--dry-run"], osname, env)
            tw, tg = rw["steps"][0]["cmd"], rg["steps"][0]["cmd"]
            check(f"{osname}: train --init leaves --epochs to train.py (12); a given --epochs and --patience pass",
                  "--epochs" not in tw and tw[tw.index("--init") + 1] == "old.pt"
                  and tg[tg.index("--epochs") + 1] == "7" and tg[tg.index("--patience") + 1] == "3")
            cap = flat("capture")
            names = [os.path.basename(s["cmd"][s["cmd"].index("-P") + 1] if "-P" in s["cmd"] else s["cmd"][1]) for s in cap]
            m = cap[2]["cmd"]
            check(f"{osname}: capture = detect, solve --samples-out (despike on), metrics --pops-min-move 0.03, apply --glb",
                  names == ["detect.py", "solve.py", "motion_metrics.py", "apply_motion.py"]
                  and "--samples-out" in cap[1]["cmd"] and "--no-despike" not in cap[1]["cmd"]
                  and m[m.index("--pops-min-move") + 1] == "0.03" and cap[3]["cmd"][-1] == "--glb", names=names)
            sv = cap[1]["cmd"]
            check(f"{osname}: capture passes --device to solve (auto by default)", sv[sv.index("--device") + 1] == "auto"
                  and cap[0]["cmd"][cap[0]["cmd"].index("--device") + 1] == "auto")
            devs = {}
            for dv in ("mps", "cuda", "cpu"):
                _, rr, _ = go(stages["capture"] + ["--device", dv, "--dry-run"], osname, env)
                sc = rr["steps"][1]["cmd"]
                devs[dv] = (rr["steps"][0]["cmd"][rr["steps"][0]["cmd"].index("--device") + 1], sc[sc.index("--device") + 1])
            check(f"{osname}: --device mps reads on MPS and fits on the CPU; cuda and cpu go to both",
                  devs == {"mps": ("mps", "cpu"), "cuda": ("cuda", "cuda"), "cpu": ("cpu", "cpu")}, devs=devs)
            bk = flat("bake")
            cb = bk[1]["cmd"]
            check(f"{osname}: bake = apply --save keyed.blend, contact_bake on it (--legs contract, --rig-info), metrics",
                  "--save" in bk[0]["cmd"] and cb[3] == str(R / "clips" / "jump_punch" / "keyed.blend")
                  and cb[cb.index("--legs") + 1] == "contract" and "--rig-info" in cb
                  and cb[cb.index("--armature") + 1] == "RunnerRig" and "baked_samples.npz" in bk[2]["cmd"][2])
            check(f"{osname}: bake passes the capture's samples.json as --readings, bake_metrics writes --out",
                  cb[cb.index("--readings") + 1] == str(R / "clips" / "jump_punch" / "samples.json")
                  and bk[2]["cmd"][bk[2]["cmd"].index("--out") + 1] == str(R / "clips" / "jump_punch" / "bake_metrics.json"))
            _, rr, _ = go(stages["bake"] + ["--render", "--samples", "16", "--dry-run"], osname, env)
            rs = rr["steps"]
            rc = rs[-1]["cmd"] if len(rs) == 4 else []
            clip = R / "clips" / "jump_punch"
            check(f"{osname}: bake is 3 steps; bake --render adds render_baked.py on baked.blend into baked/",
                  len(bk) == 3 and [x["name"] for x in rs] == ["keyed", "contact_bake", "bake_metrics", "render"]
                  and rc[:4] == [bl, "-b", "--factory-startup", str(clip / "baked.blend")]
                  and os.path.basename(rc[rc.index("-P") + 1]) == "render_baked.py"
                  and rc[rc.index("--") + 1:rc.index("--") + 3] == [str(R / "rig" / "rig_info.json"), str(clip / "baked")]
                  and rc[rc.index("--samples") + 1] == "16" and rc[rc.index("--engine") + 1] == "cycles"
                  and rs[-1]["report"] == str(clip / "render.json"), rc=rc)
            f = flat("film")[0]["cmd"]
            check(f"{osname}: film names the server by label, the prompt by move",
                  f[f.index("--server-label") + 1] == "studio-gpu" and str(R / "prompts" / "jump_punch.txt") in f)
        # 2. finding Blender on each system
        none = lambda name: None
        win = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
        check("nt: the newest Blender Foundation install when not on PATH",
              default_blender("nt", {}, none, lambda p: False, lambda g: [win.replace("5.2", "4.5"), win]) == win)
        check("posix: the macOS app when not on PATH", default_blender("posix", {}, none, lambda p: p == MAC_BLENDER,
                                                                       lambda g: []) == MAC_BLENDER)
        check("$BLENDER wins over PATH", default_blender("nt", {"BLENDER": "B"}, lambda n: "P") == "B")
        code, r, _ = go(["ref", "runner", "--dry-run", "--blender", "X"], "posix", {"RUNS": str(runs), "BLENDER": "B"})
        check("--blender wins over $BLENDER", r["steps"][0]["cmd"][0] == "X")
        check("children get PYTHONIOENCODING=utf-8", child_env({})["PYTHONIOENCODING"] == "utf-8")
        # 3. the defaults agree with train.py's own
        sys.path.insert(0, str(HERE))
        import train as T
        tp = T.parser().parse_args(["d", "r", "o"])
        check("train defaults agree with train.py; train.py picks the epochs (20, 12 with --init) and no plateau stop",
              all(getattr(tp, k) == v for k, v in TRAIN_DEFAULTS.items()) and tp.epochs is None and tp.patience == 0
              and T.epochs_cap(tp) == 20 and T.epochs_cap(T.parser().parse_args(["d", "r", "o", "--init", "x"])) == 12)
        # 4. exit codes through real child processes (a stand-in for Blender and for every script)
        (td / "fake.py").write_text(FAKE, encoding="utf-8")
        trace = td / "trace.jsonl"
        fake = [sys.executable, str(td / "fake.py")]

        def real(argv, codes=None, **extra):
            trace.write_text("")
            env = {**os.environ, "RUNS": str(runs), "FAKE_TRACE": str(trace), "FAKE_CODES": json.dumps(codes or {}),
                   **{k: str(v) for k, v in extra.items()}}
            OVERRIDE.update(blender=fake, python=fake)
            try:
                code, r, err = go(argv, None, env)
            finally:
                OVERRIDE.clear()
            ran = [json.loads(x)["script"] for x in trace.read_text().splitlines() if x.strip()]
            return code, r, err, ran

        code, r, err, ran = real(stages["capture"])
        check("capture: every step passes, exit 0, four steps", code == 0 and ran == ["detect.py", "solve.py",
              "motion_metrics.py", "apply_motion.py"], code=code, ran=ran, err=r.get("error"))
        check("capture: reports saved, non-ASCII child output survives",
              (R / "clips" / "jump_punch" / "detect.json").exists() and "\u4e2d" in err)
        rs = {s_["name"]: s_ for s_ in r.get("steps", [])}
        check("capture: every step has its seconds; the metrics step names the file it wrote as its report",
              all(isinstance(s_.get("seconds"), float) and s_["seconds"] >= 0 for s_ in rs.values())
              and rs.get("metrics", {}).get("report") == str(R / "clips" / "jump_punch" / "metrics.json")
              and rs.get("apply", {}).get("report") is None, steps=list(rs.values()))
        code, r, err, ran = real(stages["capture"], {"detect.py": 2})
        check("capture: a detect gate fails, the rest still runs, exit 2", code == 2 and len(ran) == 4, ran=ran)
        code, r, err, ran = real(stages["capture"], {"solve.py": 1})
        check("capture: a solve error stops it, exit 1", code == 1 and ran == ["detect.py", "solve.py"], ran=ran)
        code, r, err, ran = real(stages["capture"], {"motion_metrics.py": 2})
        fg = {s_["name"]: s_["failed_gates"] for s_ in r.get("steps", [])}
        check("capture: a metrics gate fails, exit 2, its gate named from the --out file",
              code == 2 and len(ran) == 4 and fg.get("metrics") == ["fake.gate"], fg=fg)
        code, r, err, ran = real(stages["capture"], {"motion_metrics.py": 2}, FAKE_NO_OUT=1)
        fg = {s_["name"]: s_["failed_gates"] for s_ in r.get("steps", [])}
        check("capture: no --out file, the indented JSON on stdout still names the failed gate",
              code == 2 and fg.get("metrics") == ["fake.gate"], fg=fg)
        code, r, err, ran = real(stages["capture"], {"solve.py": 2})
        fg = {s_["name"]: s_["failed_gates"] for s_ in r.get("steps", [])}
        check("capture: a solve gate is named", code == 2 and fg.get("solve") == ["fake.gate"], fg=fg)
        code, r, err, ran = real(stages["capture"], {"solve.py": 2}, FAKE_OLD_DIALECT="solve.py")
        fg = {s_["name"]: s_["failed_gates"] for s_ in r.get("steps", [])}
        check("capture: an old-dialect gate ('ok' key) is still read", code == 2 and fg.get("solve") == ["fake.gate"], fg=fg)
        check("last_json: indented after noise, one line, and trailing noise",
              last_json(["noise {x}\n", "{\n", ' "a": {\n', '  "b": 1\n', " }\n", "}\n"]) == {"a": {"b": 1}}
              and last_json(['{"a": 1}\n']) == {"a": 1} and last_json(['{"a": 1}\n', "Traceback\n"]) is None
              and gate_failed({"ok": False}) and gate_failed({"pass": False}) and not gate_failed({"ok": True})
              and gate_failed({"name": "x"}) and gate_failed({}) and gate_failed({"pass": None})
              and gate_failed({"pass": False, "ok": True}) and not gate_failed({"pass": True}))
        code, r, err, ran = real(stages["capture"], {"apply_motion.py": 1})
        check("capture: an apply error, exit 1", code == 1)
        code, r, err, ran = real(stages["ref"], {"render_ref.py": 2}, FAKE_BLENDER_EXIT=0)
        check("a Blender that exits 0 under a TWOCAM_JSON exit_code 2 gives 2", code == 2, code=code)
        code, r, err, ran = real(stages["ref"], None, FAKE_SILENT="render_ref.py")
        check("a Blender run that never reports is an error, exit 1", code == 1)
        code, r, err, ran = real(stages["dataset"] + ["--count", "30"])
        logs = [R / f"dataset_{k}.log" for k in range(3)]
        check("dataset: three processes, a log each, every sample, exit 0", code == 0 and ran.count("render_dataset.py") == 3
              and all(p.exists() for p in logs) and r.get("samples", 0) >= 30, code=code)
        code, r, err, ran = real(stages["dataset"] + ["--count", "30", "--seed", "1"], None, FAKE_FAIL_START=10)
        check("dataset: one process's gate fails, exit 2", code == 2)
        code, r, err, ran = real(stages["dataset"] + ["--count", "30"], None, FAKE_FAIL_START=20, FAKE_FAIL_CODE=1)
        check("dataset: one process errors, exit 1", code == 1)
        code, r, err, ran = real(stages["bake"], {"contact_bake.py": 2})
        fg = {s_["name"]: s_["failed_gates"] for s_ in r.get("steps", [])}
        check("bake: a failed foot-lock gate still measures the bake, exit 2, the gate named",
              code == 2 and ran == ["apply_motion.py", "contact_bake.py", "motion_metrics.py"]
              and fg.get("contact_bake") == ["fake.gate"], ran=ran, fg=fg)
        (R / "clips" / "jump_punch" / "bake_metrics.json").write_text(json.dumps({"gates": [{"name": "stale", "ok": False}]}))
        code, r, err, ran = real(stages["bake"], {"motion_metrics.py": 1}, FAKE_NO_OUT=1)
        fg = {s_["name"]: s_["failed_gates"] for s_ in r.get("steps", [])}
        check("bake: an older run's bake_metrics.json is not read as this run's report", code == 1
              and fg.get("bake_metrics") == ["fake.gate"], fg=fg)
        code, r, err, ran = real(stages["bake"] + ["--render"])
        rs = {s_["name"]: s_ for s_ in r.get("steps", [])}
        clip = R / "clips" / "jump_punch"
        check("bake --render: keyed, contact_bake, bake_metrics, render; exit 0; contact_bake and bake_metrics name "
              "their report files, render.json saved, every step timed",
              code == 0 and ran == ["apply_motion.py", "contact_bake.py", "motion_metrics.py", "render_baked.py"]
              and rs["contact_bake"]["report"] == str(clip / "bake.json")
              and rs["bake_metrics"]["report"] == str(clip / "bake_metrics.json")
              and (clip / "render.json").exists() and all("seconds" in s_ for s_ in rs.values()), ran=ran, code=code)
        code, r, err, ran = real(stages["bake"], {"apply_motion.py": 2})
        check("bake: keying the rig must pass before the bake, exit 2 stops", code == 2 and ran == ["apply_motion.py"])
        code, r, err, ran = real(stages["train"], {"train.py": 2})
        check("train: the log holds the progress, the gate's exit 2 comes through", code == 2
              and "epoch 0" in (R / "train.log").read_text(encoding="utf-8") and "epoch 0" in err
              and (R / "train.json").exists())
        code, r, err, ran = real(["capture", "nobody", video, "x"])
        check("capture without a reader is refused before anything runs, exit 1", code == 1 and ran == [])
        code, r, err, ran = real(["fly", "runner"])
        check("an unknown stage is refused, exit 1 (not argparse's 2)", code == 1)
        code, r, err, ran = real(["ref", "runner", "--bogus"])
        check("an unknown option is refused, exit 1", code == 1)
        code, r, _ = go(["ref", "runner", "--blender", str(td / "no-such-blender")], None, {"RUNS": str(runs)})
        check("a missing Blender executable is an error, exit 1", code == 1)
    ok = all(c["pass"] for c in checks)
    print(json.dumps({"tool": "twocam.py", "selftest": "pass" if ok else "fail", "checks": len(checks),
                      "failed": [c for c in checks if not c["pass"]]}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
