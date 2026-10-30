#!/usr/bin/env python3
"""autorig.py — character-autorig's stages for one character in one command, on Windows, macOS or Linux.

usage (in this order; `all` runs them one after another):
    autorig.py prep     OUT GLB [--name NAME] [--height 1.75]      -> OUT/NAME.glb, OUT/NAME.blend
    autorig.py check    OUT [--name NAME]                           -> rig/NAME.mesh.json
    autorig.py markers  OUT [--name NAME] [--no-render]             -> rig/NAME.markers.json, rig/markers/
    autorig.py arp      OUT [--name NAME]                           -> rig/NAME_arp.blend, export/NAME.fbx
    autorig.py contract OUT [--name NAME] [--min-fingers 30]        -> rig/NAME.contract.json
    autorig.py deform   OUT [--name NAME] [--no-render] [--no-repair] -> rig/NAME.deform.json [repair/aN/]
    autorig.py all      OUT GLB [any of the options above]
    autorig.py --selftest
Every stage takes --blender PATH (env BLENDER, default blender on PATH, else the usual install folder),
--python PATH (env PYTHON, default this interpreter; numpy for mesh_check), --threads N (Blender -t N) and
--dry-run (print the commands, run nothing). NAME defaults to the GLB's stem (prep, all), else the one .glb in OUT.

prep: blender-character-rig bcr_import_prep (height, backface culling, no weld) -> NAME.blend. check:
mesh_check.py on NAME.glb. markers: arp_markers.py --mesh NAME (--preview-dir rig/markers/ unless --no-render).
arp: blender-retarget brt_arp op pipeline, the rig saved as rig/NAME_arp.blend, the Unity FBX in export/.
contract: unity-rigged-character contract_map.py map --map arp --require contract, --min-fingers 30 unless the
markers say fingers.mode fixed (a mitten). deform: deform_gate.py on the FBX with the contract's retarget_map
(--render rig/poses/ unless --no-render; without fist when fingers.mode is fixed).

Repair ladder (deform, on unless --no-repair): when the only failing gate is deform.volume_loss_max and every
joint over the limit is an elbow (LowerArm.*) or a knee (LowerLeg.*), each attempt opens rig/NAME_arp.blend,
moves weight across that hinge with brt_weights (one snapshot, then per side: below the joint the upper bones'
weight to the lower bone, above it the lower bones' weight to the upper bone, amount 1.0, a narrow band at the
crease left blended; the elbow masked off the torso), runs brt_arp op export and saves a copy into repair/aN/,
then gates that FBX again. The bands come from the markers (the joint's height, the shoulder's width), scaled
with the height. Next attempt: a hinge that only now fails is added; volume held but self-intersection failed
-> amount 0.9; anything else stops. The limits are never changed. A finer bind and a moved marker are not
automated: the failure message names them (reference/arp-pipeline.md).

Blender runs headless; prep, markers and deform with --factory-startup, arp and repair without it (Auto-Rig Pro
is an add-on). Commands are argument lists (no shell, no inline Python), so a Windows path passes as is; the
Blender-side work of prep, arp and repair runs this file inside Blender (`-P autorig.py -- _inside ...`).
Children run with PYTHONIOENCODING=utf-8. Prints one JSON summary (each step's exit code, seconds, log, report,
failed gates; the repair attempts; the files to take on) and writes it to OUT/autorig.<stage>.json.
Exit codes: 0 every gate passed (after a repair that passed, too), 2 a gate failed, 1 refused input or an error.
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
SELF = Path(__file__).resolve()
SKILLS = HERE.parents[1]
BCR = SKILLS / "blender-character-rig" / "scripts"
BRT = SKILLS / "blender-retarget" / "scripts"
CONTRACT_MAP = SKILLS / "unity-rigged-character" / "scripts" / "contract_map.py"
MAC_BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
WIN_BLENDER_GLOB = r"C:\Program Files\Blender Foundation\Blender*\blender.exe"
STAGES = ("prep", "check", "markers", "arp", "contract", "deform")
STOP_ON_GATE = {"check", "markers", "arp"}       # a later stage cannot use what these failed to make
NO_FIST = "arms_up,deep_squat,torso_twist,leg_raise,elbow_120"
GATED = ("LowerArm", "LowerLeg", "Spine", "Chest", "UpperChest", "Hand", "Foot")   # deform_gate.GATED
HINGE_OF = {"LowerArm": "elbow", "LowerLeg": "knee"}
HINGE_BONES = {"elbow": ("UpperArm", "LowerArm"), "knee": ("UpperLeg", "LowerLeg")}
# the repair bands, metres for a 1.75 m character relative to the joint marker's height, scaled with the height
REF_H = 1.75
BAND_SNAPSHOT = (-0.149, -0.129, 0.121, 0.141)
BAND_BELOW = (-0.119, -0.089, -0.019, -0.004)
BAND_ABOVE = (0.004, 0.019, 0.091, 0.121)
ELBOW_MASK = (0.015, 0.045)                       # past the shoulder marker's |x|: 0 inside, full past
AMOUNTS = (1.0, 0.9)
MAX_ATTEMPTS = 3
MANUAL_RUNGS = ("by hand, one at a time on a copy of NAME.blend: a finer bind (brt_arp pipeline 'resolution' "
                "one step up), then the joint marker moved to the crease (arp_markers.py --adjust), each gated "
                "again; never a looser limit (reference/arp-pipeline.md)")
ECHO = re.compile(r"^(AUTORIG_JSON|Error|Traceback|.*Exception)")


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
        self.out = Path(os.path.abspath(a.out))
        self.blender = OVERRIDE.get("blender") or ([a.blender] if a.blender else [default_blender(osname, env)])
        self.python = OVERRIDE.get("python") or [a.python or env.get("PYTHON") or sys.executable]
        self.threads = a.threads
        self.dry = a.dry_run
        self.env = child_env(env)
        self.glb = Path(os.path.abspath(a.glb)) if getattr(a, "glb", None) else None
        self.name = a.name or (safe_name(self.glb.stem) if self.glb else find_name(self.out))
        n, o = self.name, self.out
        self.f = {"glb": o / f"{n}.glb", "blend": o / f"{n}.blend", "prep": o / "rig" / f"{n}.prep.json",
                  "mesh": o / "rig" / f"{n}.mesh.json", "markers": o / "rig" / f"{n}.markers.json",
                  "previews": o / "rig" / "markers", "arp": o / "rig" / f"{n}.arp.json",
                  "arp_blend": o / "rig" / f"{n}_arp.blend", "fbx": o / "export" / f"{n}.fbx",
                  "skeleton": o / "export" / f"{n}.skeleton.json", "contract": o / "rig" / f"{n}.contract.json",
                  "deform": o / "rig" / f"{n}.deform.json", "poses": o / "rig" / "poses", "logs": o / "logs",
                  "repair": o / "repair"}


def safe_name(stem: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", stem).strip("_") or "Character"


def find_name(out: Path) -> str:
    hits = sorted(out.glob("*.glb")) if out.is_dir() else []
    if len(hits) != 1:
        raise Refused(f"pass --name: {out} holds {len(hits)} .glb files (run 'prep' first)")
    return hits[0].stem


def blender_cmd(c: Ctx, script: Path, *args, blend=None, factory=True) -> list:
    return (c.blender + ["-b"] + (["--factory-startup"] if factory else [])
            + (["-t", str(c.threads)] if c.threads else []) + ([str(blend)] if blend else [])
            + ["-P", str(script), "--"] + [str(x) for x in args])


def py_cmd(c: Ctx, script: Path, *args) -> list:
    return c.python + [str(script)] + [str(x) for x in args]


def need(c: Ctx, path: Path, stage: str):
    if not c.dry and not Path(path).exists():
        raise Refused(f"missing {path} (run the '{stage}' stage first)")


def step(name, cmd, report_file, log, kind="file") -> dict:
    return {"name": name, "cmd": [str(x) for x in cmd], "report": str(report_file), "log": str(log), "kind": kind}


_WARNED: set = set()


def _warn_once(key: str, text: str) -> None:
    if key not in _WARNED:
        _WARNED.add(key)
        print(f"WARN {text}", file=sys.stderr)


def gate_failed(g: dict) -> bool:
    """A gate/1 gate passes only on `pass: true`; one without a boolean `pass` has failed. The 0.34 dialect's
    `ok` is read in its place for one release, only when `pass` is absent."""
    if not isinstance(g, dict):
        return True
    if "pass" in g:
        return g["pass"] is not True
    if "ok" in g:
        _warn_once("gate-ok", "a gate carries the old key `ok`, read as `pass` (gate/1 names it `pass`)")
        return g["ok"] is not True
    return True


def report_passed(rep: dict | None) -> bool | None:
    """A report's verdict: its boolean `pass`, else (an unstamped 0.34 report) its `ok`, else None for a
    report that states none. A report stamped gate/1 without a boolean `pass` has failed."""
    if not isinstance(rep, dict):
        return None
    if isinstance(rep.get("pass"), bool):
        return rep["pass"]
    if rep.get("schema") == "gate/1":
        return False
    if isinstance(rep.get("ok"), bool):
        if rep.get("gates"):
            _warn_once("report-ok", f"{rep.get('tool', 'a report')} carries no `pass`; its old key `ok` is read")
        return rep["ok"]
    return None


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def fingers_fixed(c: Ctx) -> bool | None:
    """The markers' fingers.mode is 'fixed' (a mitten); None while the markers are not written yet."""
    m = read_json(c.f["markers"])
    return None if m is None else (m.get("fingers") or {}).get("mode") == "fixed"


# --- the stages: each a list of steps, planned when it is about to run ---------------------------------------------
def plan(c: Ctx, stage: str, a) -> list:
    f, logs = c.f, c.f["logs"]
    if stage == "prep":
        if c.glb is None:
            raise Refused("prep needs the GLB")
        if not c.dry and not c.glb.exists():
            raise Refused(f"missing {c.glb}")
        return [step("prep", blender_cmd(c, SELF, "_inside", "prep", "--glb", f["glb"], "--name", c.name,
                                         "--height", a.height, "--save", f["blend"], "--report", f["prep"]),
                     f["prep"], logs / "prep.log", kind="inner")]
    if stage == "check":
        need(c, f["glb"], "prep")
        return [step("check", py_cmd(c, HERE / "mesh_check.py", f["glb"], "--out", f["mesh"]), f["mesh"],
                     logs / "check.log", kind="python")]
    if stage == "markers":
        need(c, f["blend"], "prep")
        prev = [] if a.no_render else ["--preview-dir", f["previews"]]
        return [step("markers", blender_cmd(c, HERE / "arp_markers.py", "--mesh", c.name, "--out", f["markers"],
                                            *prev, blend=f["blend"]), f["markers"], logs / "markers.log")]
    if stage == "arp":
        need(c, f["blend"], "prep"); need(c, f["markers"], "markers")
        return [step("arp", blender_cmd(c, SELF, "_inside", "arp", "--mesh", c.name, "--markers", f["markers"],
                                        "--fbx", f["fbx"], "--save", f["arp_blend"], "--report", f["arp"],
                                        blend=f["blend"], factory=False), f["arp"], logs / "arp.log", kind="inner")]
    if stage == "contract":
        need(c, f["skeleton"], "arp")
        fingers = [] if fingers_fixed(c) else ["--min-fingers", a.min_fingers]
        return [step("contract", py_cmd(c, CONTRACT_MAP, "map", f["skeleton"], "--map", "arp", "--require", "contract",
                                        *fingers, "--out", f["contract"]), f["contract"], logs / "contract.log",
                     kind="python")]
    if stage == "deform":
        need(c, f["fbx"], "arp"); need(c, f["contract"], "contract")
        return [deform_step(c, "deform", f["fbx"], f["deform"], None if a.no_render else f["poses"], logs)]
    raise Refused(f"unknown stage {stage}")


def deform_step(c: Ctx, name, fbx, out, render, logs) -> dict:
    poses = ["--poses", NO_FIST] if fingers_fixed(c) else []
    rend = ["--render", render] if render else []
    return step(name, blender_cmd(c, HERE / "deform_gate.py", "--fbx", fbx, "--map", c.f["contract"], *poses,
                                  *rend, "--out", out), out, logs / f"{name}.log")


def repair_steps(c: Ctx, n: int, rung: dict, render: bool) -> tuple[list, dict]:
    d = c.f["repair"] / f"a{n}"
    files = {"dir": d, "fbx": d / f"{c.name}.fbx", "blend": d / f"{c.name}_arp.blend", "deform": d / f"{c.name}.deform.json",
             "repair": d / "repair.json"}
    fix = step(f"repair_a{n}", blender_cmd(c, SELF, "_inside", "repair", "--markers", c.f["markers"], "--contract",
                                           c.f["contract"], "--hinges", ",".join(rung["hinges"]), "--amount",
                                           rung["amount"], "--fbx", files["fbx"], "--save", files["blend"],
                                           "--backup-dir", d, "--report", files["repair"],
                                           blend=c.f["arp_blend"], factory=False),
               files["repair"], d / "repair.log", kind="inner")
    gate = deform_step(c, f"deform_a{n}", files["fbx"], files["deform"], (d / "poses") if render else None, d)
    return [fix, gate], files


# --- the repair ladder: pure decisions on deform reports -----------------------------------------------------------
def classify(rep: dict) -> dict:
    """What a deform report failed: the failing gates, every gated joint over the volume limit, the hinges among
    them, and whether the weight transfer is the documented fix (volume loss alone, at elbows or knees alone)."""
    gates = rep.get("gates") or []
    failed = [g.get("name") for g in gates if gate_failed(g)]
    limit = next((g.get("limit") for g in gates if g.get("name") == "deform.volume_loss_max"), 0.35)
    over = {}
    for pose in (rep.get("poses") or {}).values():
        for smp in pose.get("samples") or []:
            for joint, v in (smp.get("volume_loss") or {}).items():
                if joint.split(".")[0] in GATED and v is not None and v > limit:
                    over[joint] = max(v, over.get(joint, v))
    worst = rep.get("volume_loss_max") or {}
    if not over and "deform.volume_loss_max" in failed and worst.get("joint"):
        over[worst["joint"]] = worst.get("value")
    hinges = sorted({HINGE_OF[j.split(".")[0]] for j in over if j.split(".")[0] in HINGE_OF})
    repairable = (failed == ["deform.volume_loss_max"] and bool(over)
                  and all(j.split(".")[0] in HINGE_OF for j in over))
    return {"passed": bool(gates) and not failed, "failed_gates": failed, "over": over, "hinges": hinges,
            "repairable": repairable}


def next_rung(base: dict, attempts: list) -> dict | None:
    """The next attempt ({hinges, amount, why}) or None: passed, not a hinge-only volume loss, or exhausted."""
    if len(attempts) >= MAX_ATTEMPTS:
        return None
    if not attempts:
        k = classify(base)
        return {"hinges": k["hinges"], "amount": AMOUNTS[0], "why": "volume loss at " + ", ".join(sorted(k["over"]))} \
            if k["repairable"] else None
    last = attempts[-1]
    k = classify(last.get("report") or {})
    if k["passed"]:
        return None
    if k["repairable"]:
        hinges = sorted(set(last["hinges"]) | set(k["hinges"]))
        if hinges != sorted(last["hinges"]):
            return {"hinges": hinges, "amount": last["amount"], "why": "now also " + ", ".join(sorted(k["over"]))}
        return None   # the transfer did not hold this hinge: the manual rungs
    if k["failed_gates"] == ["deform.self_intersection_p95"] and last["amount"] in AMOUNTS:
        i = AMOUNTS.index(last["amount"])
        if i + 1 < len(AMOUNTS):
            return {"hinges": last["hinges"], "amount": AMOUNTS[i + 1],
                    "why": "volume held, self-intersection rose: a softer hand-over"}
    return None


def repair_regions(markers: dict, hinge: str) -> dict:
    """The world-Z bands (and, for an elbow, the |x| mask that keeps the torso out) around a hinge, from the
    markers: the joint's height (mean of both sides), the shoulder's width, scaled with the character's height."""
    lm = markers["landmarks"]
    s = float(markers.get("height") or REF_H) / REF_H
    z = (lm[f"{hinge}.L"][2] + lm[f"{hinge}.R"][2]) / 2.0
    band = lambda offs: [round(z + o * s, 3) for o in offs]
    mask = None
    if hinge == "elbow":
        sx = (abs(lm["shoulder.L"][0]) + abs(lm["shoulder.R"][0])) / 2.0
        mask = {"inner": round(sx + ELBOW_MASK[0] * s, 3), "outer": round(sx + ELBOW_MASK[1] * s, 3)}
    return {"joint_z": round(z, 4), "snapshot": band(BAND_SNAPSHOT), "below": band(BAND_BELOW),
            "above": band(BAND_ABOVE), "mask": mask}


def hinge_bones(retarget_map: dict, hinge: str, side: str, deform: set) -> tuple[list, list]:
    """(upper bones, lower bones) of one side, deform bones only: the contract's bone, then its twist bone."""
    def chain(role):
        name = retarget_map.get(f"{role}.{side.upper()}")
        name = name[0] if isinstance(name, list) else name
        if not name:
            return []
        out = [name] + ([name.replace("_stretch", "_twist")] if "_stretch" in name else [])
        return [b for b in out if b in deform]
    up, lo = HINGE_BONES[hinge]
    return chain(up), chain(lo)


def attempt_summary(n, rung, regions, steps_done, files, rep) -> dict:
    k = classify(rep or {})
    return {"attempt": n, "hinges": rung["hinges"], "amount": rung["amount"], "why": rung.get("why"),
            "regions": regions, "exit_code": max((s["exit_code"] for s in steps_done), default=1),
            "seconds": round(sum(s["seconds"] for s in steps_done), 1),
            "volume_loss_max": (rep or {}).get("volume_loss_max"),
            "self_intersection_p95": ((rep or {}).get("self_intersection") or {}).get("p95"),
            "failed_gates": k["failed_gates"], "over_limit": k["over"], "passed": k["passed"],
            "fbx": str(files["fbx"]), "blend": str(files["blend"]), "deform": str(files["deform"])}


# --- running ----------------------------------------------------------------------------------------------------
def _pump(stream, logf, echo, keep, proc=None):
    for line in iter(stream.readline, ""):
        logf.write(line)
        logf.flush()
        if echo is not None and echo.match(line):
            sys.stderr.write(line)
            sys.stderr.flush()
        if keep is not None:
            keep.append(line)
    stream.close()
    if proc is not None:
        proc.t_end = time.perf_counter()


def run_step(st: dict, env: dict) -> tuple[int, dict | None, float]:
    """Run one step, its stdout and stderr into its log; (exit code, report, seconds)."""
    Path(st["log"]).parent.mkdir(parents=True, exist_ok=True)
    Path(st["report"]).parent.mkdir(parents=True, exist_ok=True)
    Path(st["report"]).unlink(missing_ok=True)   # an older run's report must not stand in for this one's
    with open(st["log"], "w", encoding="utf-8") as logf:
        t0 = time.perf_counter()
        p = subprocess.Popen(st["cmd"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True,
                             encoding="utf-8", errors="replace", bufsize=1)
        out_lines = []
        echo = None if st["kind"] == "python" else ECHO
        ts = [threading.Thread(target=_pump, args=(p.stdout, logf, echo, out_lines, p), daemon=True),
              threading.Thread(target=_pump, args=(p.stderr, logf, echo, None), daemon=True)]
        for t in ts:
            t.start()
        code = p.wait()
        for t in ts:
            t.join()
    rep = read_json(st["report"])
    if rep is None and st["kind"] == "inner":
        for line in reversed(out_lines):
            if line.startswith("AUTORIG_JSON "):
                try:
                    rep = json.loads(line[len("AUTORIG_JSON "):])
                except ValueError:
                    pass
                break
    if rep is None:
        code = code or 1          # the script never reported: Blender failed to open the file or to run it
    elif code == 0 and (rep.get("exit_code") not in (None, 0) or report_passed(rep) is False):
        code = int(rep.get("exit_code") or 2)   # a Blender that drops the script's exit code
    if code not in (0, 1, 2):
        code = 1                  # a crash or a signal is an error
    return code, rep, round(getattr(p, "t_end", time.perf_counter()) - t0, 1)


def done_entry(st, code, rep, sec) -> dict:
    return {"name": st["name"], "exit_code": code, "seconds": sec, "log": st["log"], "report": st["report"],
            "failed_gates": [g.get("name") for g in (rep or {}).get("gates", []) if gate_failed(g)],
            "error": (rep or {}).get("error") or (rep or {}).get("message")}


def ladder(c: Ctx, a, base: dict, done: list) -> dict:
    """The repair attempts after a failed deform gate; returns the summary's `repair` block."""
    out = {"attempts": [], "result": "not_applicable"}
    attempts = []
    markers = read_json(c.f["markers"]) or {}
    while True:
        rung = next_rung(base, attempts)
        if rung is None:
            break
        n = len(attempts) + 1
        regions = {h: repair_regions(markers, h) for h in rung["hinges"]}
        steps, files = repair_steps(c, n, rung, not a.no_render)
        sdone, rep = [], None
        for st in steps:
            code, rep, sec = run_step(st, c.env)
            sdone.append(done_entry(st, code, rep, sec))
            if code == 1:
                break
        done.extend(sdone)
        s = attempt_summary(n, rung, regions, sdone, files, rep if sdone[-1]["name"].startswith("deform") else None)
        out["attempts"].append(s)
        attempts.append({**rung, "report": rep if s["exit_code"] != 1 else {}})
        if s["exit_code"] == 1:
            out.update(result="error", message=f"attempt {n} stopped on an error: {sdone[-1]['error'] or sdone[-1]['log']}")
            return out
        if s["passed"]:
            out.update(result="passed", message=f"attempt {n} passed the deformation gates",
                       files={"fbx": s["fbx"], "blend": s["blend"], "deform": s["deform"]})
            return out
    if attempts:
        out.update(result="exhausted", message="the weight transfer did not pass the deformation gates; go on " +
                   MANUAL_RUNGS.replace("NAME", c.name))
    else:
        k = classify(base)
        out["message"] = ("not a hinge-only volume loss (" + ", ".join(k["failed_gates"]) + "; over the limit: "
                          + (", ".join(sorted(k["over"])) or "none") + "): read the failures table in SKILL.md")
    return out


# --- the command line -------------------------------------------------------------------------------------------
def parser() -> Parser:
    common = Parser(add_help=False, allow_abbrev=False)
    common.add_argument("out", help="the character's folder")
    common.add_argument("--name"); common.add_argument("--blender"); common.add_argument("--python")
    common.add_argument("--threads", type=int, help="Blender -t N")
    common.add_argument("--dry-run", action="store_true")
    ap = Parser(prog="autorig.py", description=__doc__.split("\n")[0], allow_abbrev=False)
    sub = ap.add_subparsers(dest="stage", required=True, parser_class=Parser)
    for s in STAGES + ("all",):
        p = sub.add_parser(s, parents=[common], allow_abbrev=False)
        if s in ("prep", "all"):
            p.add_argument("glb")
            p.add_argument("--height", type=float, default=1.75, help="metres (default 1.75)")
        if s in ("markers", "deform", "all"):
            p.add_argument("--no-render", action="store_true", help="no marker pictures, no pose renders")
        if s in ("contract", "all"):
            p.add_argument("--min-fingers", type=int, default=30)
        if s in ("deform", "all"):
            p.add_argument("--no-repair", action="store_true")
    return ap


def parse(argv) -> argparse.Namespace:
    a = parser().parse_args(argv)
    for k, v in (("glb", None), ("height", 1.75), ("no_render", False), ("min_fingers", 30), ("no_repair", False)):
        if not hasattr(a, k):
            setattr(a, k, v)
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
        stages = list(STAGES) if a.stage == "all" else [a.stage]
        if c.dry:
            planned = {s: plan(c, s, a) for s in stages}   # need() is off in a dry run
            rung = {"hinges": ["elbow"], "amount": AMOUNTS[0]}
            example = repair_steps(c, 1, rung, not a.no_render)[0] if "deform" in stages and not a.no_repair else []
    except Refused as exc:
        print(json.dumps({"tool": "autorig.py", "ok": False, "exit_code": 1, "error": f"refused: {exc}"}))
        return 1
    out = {"tool": "autorig.py", "stage": a.stage, "name": c.name, "out": str(c.out)}
    if c.dry:
        out.update({"dry_run": True, "steps": [s_ for s in stages for s_ in planned[s]],
                    "repair_example": example, "exit_code": 0, "ok": True})
        print(json.dumps(out))
        return 0
    c.out.mkdir(parents=True, exist_ok=True)
    done, rc, repair = [], 0, None
    try:
        if "prep" in stages and c.glb and c.glb != c.f["glb"]:
            shutil.copyfile(c.glb, c.f["glb"])
        for s in stages:
            for st in plan(c, s, a):
                code, rep, sec = run_step(st, c.env)
                done.append(done_entry(st, code, rep, sec))
                if s == "deform" and code == 2 and not a.no_repair and rep:
                    repair = ladder(c, a, rep, done)
                    code = 0 if repair["result"] == "passed" else 1 if repair["result"] == "error" else 2
                if code == 1:
                    rc = 1
                    break
                rc = max(rc, code)
            if rc == 1 or (rc == 2 and s in STOP_ON_GATE):
                break
    except Refused as exc:
        out.update({"steps": done, "ok": False, "exit_code": 1, "error": f"refused: {exc}"})
        return _emit(c, a, out, 1)
    except OSError as exc:   # the Blender or Python executable is missing
        out.update({"steps": done, "ok": False, "exit_code": 1, "error": f"{type(exc).__name__}: {exc}"})
        return _emit(c, a, out, 1)
    out["steps"] = done
    if repair is not None:
        out["repair"] = repair
    files = {"blend": c.f["arp_blend"], "fbx": c.f["fbx"], "contract": c.f["contract"], "deform": c.f["deform"]}
    files.update((repair or {}).get("files") or {})
    out["result"] = {k: str(v) for k, v in files.items() if Path(v).exists()}
    out.update({"exit_code": rc, "ok": rc == 0})
    return _emit(c, a, out, rc)


def _emit(c, a, out, code) -> int:
    try:
        (c.out / f"autorig.{a.stage}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    except OSError:
        pass
    print(json.dumps(out))
    return code


# --- inside Blender: prep, arp, repair ------------------------------------------------------------------------------
def inside(argv: list) -> None:
    p = argparse.ArgumentParser(prog="autorig.py _inside")
    p.add_argument("what", choices=("prep", "arp", "repair"))
    for k in ("glb", "name", "save", "report", "mesh", "markers", "fbx", "contract", "hinges", "backup_dir"):
        p.add_argument("--" + k.replace("_", "-"))
    p.add_argument("--height", type=float); p.add_argument("--amount", type=float)
    a = p.parse_args(argv)
    try:
        rep, code = {"prep": _in_prep, "arp": _in_arp, "repair": _in_repair}[a.what](a)
    except Exception as exc:   # noqa: BLE001 — every failure is reported, exit 1
        import traceback
        rep, code = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}, 1
    rep = {"tool": f"autorig.py {a.what}", **rep, "exit_code": code}
    text = json.dumps(rep, indent=1, default=str)
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(text, encoding="utf-8")
    print("AUTORIG_JSON " + json.dumps(rep, default=str))
    sys.stdout.flush()
    sys.exit(code)


def _in_prep(a):
    import bpy
    sys.path.insert(0, str(BCR))
    import bcr_import_prep
    bpy.ops.wm.read_homefile(use_empty=True)
    r = bcr_import_prep.run({"glb": a.glb, "name": a.name, "collection": "Character", "height": a.height,
                             "location": [0, 0, 0], "weld_distance": None, "normal_strength": 0.5,
                             "backface_culling": True})
    bpy.ops.wm.save_as_mainfile(filepath=a.save)
    return r, 0 if report_passed(r) else 2


def _in_arp(a):
    import bpy
    sys.path.insert(0, str(BRT))
    import brt_arp
    Path(a.fbx).parent.mkdir(parents=True, exist_ok=True)   # the add-on's exporter does not make the folder
    r = brt_arp.run({"op": "pipeline", "mesh": a.mesh, "markers": a.markers, "fbx": a.fbx, "report_path": a.report})
    if report_passed(r):
        Path(a.save).parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=a.save)
    refused = any(g.get("name") == "arp.precondition" and gate_failed(g) for g in r.get("gates", []))
    return r, 0 if report_passed(r) else 1 if refused else 2


def _in_repair(a):
    import bpy
    sys.path.insert(0, str(BRT))
    import brt_arp
    import brt_weights
    markers = json.loads(Path(a.markers).read_text(encoding="utf-8"))
    rmap = json.loads(Path(a.contract).read_text(encoding="utf-8")).get("retarget_map") or {}
    bound = [(o, m.object) for o in bpy.data.objects if o.type == 'MESH' for m in o.modifiers
             if m.type == 'ARMATURE' and m.object is not None and m.object.type == 'ARMATURE']
    if not bound:
        return {"ok": False, "error": "no mesh is bound to an armature in this file"}, 1
    mesh, rig = max(bound, key=lambda t: len(t[0].data.vertices))
    deform = {b.name for b in rig.data.bones if b.use_deform}
    Path(a.backup_dir).mkdir(parents=True, exist_ok=True)
    log = {"mesh": mesh.name, "armature": rig.name, "amount": a.amount, "hinges": {}}
    short = lambda r: {**{k: r.get(k) for k in ("reason", "message", "changed_vertices") if k in r},
                       "ok": bool(report_passed(r))}
    for hinge in a.hinges.split(","):
        reg = repair_regions(markers, hinge)
        base = {"mesh": mesh.name, "armature": rig.name, "acknowledge_destructive": True,
                "backup_path": str(Path(a.backup_dir) / f"{hinge}.npz")}
        if reg["mask"]:
            base.update(axis="X", mask=reg["mask"])
        h = log["hinges"][hinge] = {"regions": reg, "ops": {}}
        h["ops"]["snapshot"] = short(brt_weights.run({**base, "op": "snapshot", "z_band": reg["snapshot"],
                                                      "overwrite": True}))
        if not h["ops"]["snapshot"].get("ok"):
            return {"ok": False, "error": f"{hinge}: snapshot failed", **log}, 1
        for side in ("l", "r"):
            up, lo = hinge_bones(rmap, hinge, side, deform)
            if not up or not lo:
                return {"ok": False, "error": f"{hinge}.{side}: no deform bones ({up}, {lo})", **log}, 1
            h["bones_" + side] = {"upper": up, "lower": lo}
            for key, band, frm, to in (("below", reg["below"], up, [lo[0]]), ("above", reg["above"], lo, [up[0]])):
                r = short(brt_weights.run({**base, "op": "transfer", "z_band": band, "from_bones": frm,
                                           "to_bones": to, "amount": a.amount}))
                h["ops"][f"{key}_{side}"] = r
                if not r.get("ok"):
                    return {"ok": False, "error": f"{hinge}.{side} {key}: transfer failed", **log}, 1
    Path(a.fbx).parent.mkdir(parents=True, exist_ok=True)
    x = brt_arp.run({"op": "export", "armature": rig.name, "fbx": a.fbx})
    passed = bool(report_passed(x))
    log["export"] = {"ok": passed, **{k: x.get(k) for k in ("reason", "message")}}
    log["export_failed_gates"] = [g.get("name") for g in x.get("gates", []) if gate_failed(g)]
    bpy.ops.wm.save_as_mainfile(filepath=a.save, copy=True)
    return {"ok": passed, **log}, 0 if passed else 1


# --- selftest -----------------------------------------------------------------------------------------------------
FAKE = r'''
import json, os, sys
argv = sys.argv[1:]
blender = "-b" in argv
script = os.path.basename(argv[argv.index("-P") + 1] if blender else argv[0])
args = argv[argv.index("--") + 1:] if blender and "--" in argv else argv[1:]
if script == "autorig.py":
    script = "inside_" + args[1]
codes = json.loads(os.environ.get("FAKE_CODES", "{}"))
def opt(k):
    return args[args.index(k) + 1] if k in args else None
def touch(p, text="x"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(text)
with open(os.environ["FAKE_TRACE"], "a", encoding="utf-8") as f:
    f.write(json.dumps({"script": script, "argv": argv}) + "\n")
print("progress \u00e9\u4e2d", file=sys.stderr)
code = codes.get(script, 0)
rep = {"schema": "gate/1", "pass": code == 0, "ok": code == 0, "gates": [{"name": "fake.gate", "pass": code == 0}]}
if script == "inside_prep":
    touch(opt("--save"))
elif script == "arp_markers.py":
    rep.update(fingers={"mode": os.environ.get("FAKE_FINGERS", "auto")}, height=1.75,
               landmarks={"elbow.L": [0.37, 0.07, 1.09901], "elbow.R": [-0.37, 0.07, 1.09901],
                          "knee.L": [0.17, 0.08, 0.49875], "knee.R": [-0.17, 0.08, 0.49875],
                          "shoulder.L": [0.20523, 0.1, 1.33], "shoulder.R": [-0.20523, 0.1, 1.33]})
elif script == "inside_arp":
    fbx = opt("--fbx"); touch(fbx); touch(fbx[:-4] + ".skeleton.json", "{}"); touch(opt("--save"))
elif script == "inside_repair":
    touch(opt("--fbx")); touch(opt("--save"))
elif script == "deform_gate.py":
    fbx = opt("--fbx")
    att = os.path.basename(os.path.dirname(fbx)) if "repair" in fbx else "a0"
    plan = json.loads(os.environ.get("FAKE_DEFORM", "{}"))
    joint, v, si = plan.get(att, ["LowerArm.R", 0.53, 0.04])
    vol = {"name": "deform.volume_loss_max", "value": v, "limit": 0.35, "pass": v <= 0.35}
    sig = {"name": "deform.self_intersection_p95", "value": si, "limit": 0.08, "pass": si <= 0.08}
    rep = {"schema": "gate/1", "poses": {"p": {"samples": [{"volume_loss": {joint: v}}]}},
           "volume_loss_max": {"value": v, "joint": joint}, "self_intersection": {"p95": si}, "gates": [vol, sig],
           "pass": vol["pass"] and sig["pass"], "ok": vol["pass"] and sig["pass"]}
    code = 0 if rep["pass"] else 2
if script in ("mesh_check.py", "contract_map.py", "arp_markers.py", "deform_gate.py"):
    if not os.environ.get("FAKE_NO_OUT") == script:
        touch(opt("--out"), json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
elif script.startswith("inside_"):
    rep["exit_code"] = code
    if os.environ.get("FAKE_SILENT") != script:
        touch(opt("--report"), json.dumps(rep))
        print("Blender noise")
        print("AUTORIG_JSON " + json.dumps(rep))
sys.exit(code)
'''


def selftest() -> int:
    import contextlib
    import io
    checks = []

    def check(name, cond, **kw):
        checks.append({"name": name, "pass": bool(cond), **kw})

    def go(argv, osname=None, env=None):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = main(argv, osname, env)
        try:
            return code, json.loads(buf.getvalue().strip().splitlines()[-1]), err.getvalue()
        except (ValueError, IndexError):
            return code, {}, err.getvalue()

    def script_of(cmd):
        return os.path.basename(cmd[cmd.index("-P") + 1]) if "-P" in cmd else os.path.basename(cmd[1])

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        glb = td / "src" / "Runner Courier.glb"
        glb.parent.mkdir()
        glb.write_text("x")
        # 1. dry-run command building, as POSIX and as Windows would build it
        for osname, bl in (("posix", "/opt/blender/blender"), ("nt", r"C:\Program Files\Blender\blender.exe")):
            out = td / f"dry_{osname}"
            code, r, _ = go(["all", str(out), str(glb), "--threads", "4", "--dry-run"], osname, {"BLENDER": bl})
            steps = {s["name"]: s["cmd"] for s in r.get("steps", [])}
            check(f"{osname}: all dry run plans six steps in order, exit 0", code == 0 and list(steps) == list(STAGES),
                  code=code, err=r.get("error"))
            check(f"{osname}: the name is the GLB stem made safe", r.get("name") == "Runner_Courier")
            bls = [steps[k] for k in ("prep", "markers", "arp", "deform")] + [s["cmd"] for s in r["repair_example"]]
            check(f"{osname}: every Blender step is [$BLENDER, -b, ...] with -t 4, no shell, no inline Python",
                  all(c_[:2] == [bl, "-b"] and c_[c_.index("-t") + 1] == "4" for c_ in bls)
                  and not any("--python-expr" in c_ for c_ in bls))
            fac = {k: "--factory-startup" in steps[k] for k in ("prep", "markers", "arp", "deform")}
            fac.update({s["name"]: "--factory-startup" in s["cmd"] for s in r["repair_example"]})
            check(f"{osname}: --factory-startup on prep, markers, deform; not on arp or repair (the add-on)",
                  fac == {"prep": True, "markers": True, "arp": False, "deform": True, "repair_a1": False,
                          "deform_a1": True}, fac=fac)
            o = str(out)
            check(f"{osname}: prep and arp run this file inside Blender; arp opens NAME.blend",
                  script_of(steps["prep"]) == "autorig.py" and steps["prep"][steps["prep"].index("--") + 1:][:2]
                  == ["_inside", "prep"] and steps["arp"][steps["arp"].index("-P") - 1] == str(Path(o) / "Runner_Courier.blend"))
            check(f"{osname}: markers with --preview-dir, deform with --render, contract --min-fingers 30",
                  "--preview-dir" in steps["markers"] and "--render" in steps["deform"]
                  and steps["contract"][steps["contract"].index("--min-fingers") + 1] == "30"
                  and steps["contract"][1:5] == [str(CONTRACT_MAP), "map", steps["contract"][3], "--map"]
                  and "--poses" not in steps["deform"])
            rp = r["repair_example"][0]["cmd"]
            check(f"{osname}: the repair opens rig/NAME_arp.blend and writes into repair/a1/",
                  rp[rp.index("-P") - 1].endswith("Runner_Courier_arp.blend")
                  and os.path.basename(os.path.dirname(rp[rp.index("--fbx") + 1])) == "a1"
                  and rp[rp.index("--amount") + 1] == "1.0")
            code, r2, _ = go(["all", str(out), str(glb), "--no-render", "--dry-run"], osname, {"BLENDER": bl})
            s2 = {s["name"]: s["cmd"] for s in r2.get("steps", [])}
            check(f"{osname}: --no-render drops the marker pictures and the pose renders, no -t unless given",
                  "--preview-dir" not in s2["markers"] and "--render" not in s2["deform"]
                  and "--render" not in r2["repair_example"][1]["cmd"] and "-t" not in s2["prep"])
        # a mitten: the markers say fingers.mode fixed
        mo = td / "mitten"
        (mo / "rig").mkdir(parents=True)
        (mo / "export").mkdir()
        (mo / "Runner.glb").write_text("x")
        for p in ("export/Runner.fbx", "export/Runner.skeleton.json", "rig/Runner.contract.json"):
            (mo / p).write_text("{}")
        (mo / "rig" / "Runner.markers.json").write_text(json.dumps({"fingers": {"mode": "fixed"}}))
        _, rc_, _ = go(["contract", str(mo), "--dry-run"], None, {"BLENDER": "B"})
        _, rd_, _ = go(["deform", str(mo), "--dry-run"], None, {"BLENDER": "B"})
        cc, dc = rc_["steps"][0]["cmd"], rd_["steps"][0]["cmd"]
        check("mitten: contract without --min-fingers, deform without fist (both, repair gate too)",
              "--min-fingers" not in cc and dc[dc.index("--poses") + 1] == NO_FIST
              and NO_FIST in rd_["repair_example"][1]["cmd"] and rd_["name"] == "Runner")
        code, r, _ = go(["deform", str(td / "nowhere"), "--name", "X"], None, {"BLENDER": "B"})
        check("deform before arp is refused before anything runs, exit 1", code == 1 and "missing" in r.get("error", ""))
        # 2. finding Blender
        none = lambda name: None
        win = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
        check("nt: the newest Blender Foundation install when not on PATH",
              default_blender("nt", {}, none, lambda p: False, lambda g: [win.replace("5.2", "4.5"), win]) == win)
        check("posix: the macOS app when not on PATH", default_blender("posix", {}, none, lambda p: p == MAC_BLENDER,
                                                                       lambda g: []) == MAC_BLENDER)
        check("$BLENDER wins over PATH", default_blender("nt", {"BLENDER": "B"}, lambda n: "P") == "B")
        _, r, _ = go(["check", str(mo), "--dry-run", "--blender", "X"], None, {"BLENDER": "B"})
        _, rb, _ = go(["markers", str(mo), "--dry-run", "--blender", "X"], None, {"BLENDER": "B"})
        check("--blender wins over $BLENDER", rb["steps"][0]["cmd"][0] == "X")
        check("children get PYTHONIOENCODING=utf-8", child_env({})["PYTHONIOENCODING"] == "utf-8")
        # 3. the ladder's decisions on canned deform reports
        def rep(joints, si=0.04, lim=0.35):
            vol = max(joints.values()) if joints else 0.1
            return {"poses": {"elbow_120": {"samples": [{"volume_loss": joints}]}},
                    "volume_loss_max": {"value": vol, "joint": max(joints, key=joints.get) if joints else None},
                    "gates": [{"name": "deform.volume_loss_max", "value": vol, "limit": lim, "pass": vol <= lim},
                              {"name": "deform.self_intersection_p95", "value": si, "limit": 0.08, "pass": si <= 0.08},
                              {"name": "deform.joints_measured", "value": [], "pass": True}]}
        elbow = rep({"LowerArm.L": 0.517, "LowerArm.R": 0.5289, "UpperArm.R": 0.73})
        check("elbows over the limit (a shoulder's loss is not gated): repair the elbow at amount 1.0",
              next_rung(elbow, []) == {"hinges": ["elbow"], "amount": 1.0,
                                       "why": "volume loss at LowerArm.L, LowerArm.R"})
        check("a knee: repair the knee", next_rung(rep({"LowerLeg.L": 0.4}), [])["hinges"] == ["knee"])
        check("elbow and self-intersection both failing: no repair", next_rung(rep({"LowerArm.L": 0.5}, si=0.1), []) is None)
        check("a spine joint over the limit: no repair", next_rung(rep({"LowerArm.L": 0.5, "Spine": 0.4}), []) is None)
        check("every gate passing: no repair", next_rung(rep({"LowerArm.L": 0.2}), []) is None)
        bad = {"gates": [{"name": "deform.joints_measured", "pass": False}, {"name": "deform.volume_loss_max", "pass": True}]}
        check("an unmeasured joint: no repair", next_rung(bad, []) is None and not classify(bad)["repairable"])
        with contextlib.redirect_stderr(io.StringIO()):
            check("a gate without `pass` has failed; the old `ok` is read only when `pass` is absent",
                  gate_failed({}) and gate_failed({"name": "x"}) and gate_failed({"pass": None})
                  and gate_failed({"pass": False, "ok": True}) and not gate_failed({"pass": True})
                  and gate_failed({"ok": False}) and not gate_failed({"ok": True}))
            check("a report: pass, else the old ok, else no verdict; stamped gate/1 without pass fails",
                  report_passed({"pass": True}) is True and report_passed({"pass": False, "ok": True}) is False
                  and report_passed({"ok": True, "gates": []}) is True and report_passed({"steps": []}) is None
                  and report_passed({"schema": "gate/1", "ok": True}) is False)
            missing = {"gates": [{"name": "deform.volume_loss_max", "value": 0.1, "limit": 0.35}]}
            check("a deform report whose gate lacks `pass` is not passed", not classify(missing)["passed"])
        a1 = {"hinges": ["elbow"], "amount": 1.0}
        check("attempt passed: stop", next_rung(elbow, [{**a1, "report": rep({"LowerArm.R": 0.3492}, si=0.05)}]) is None)
        check("attempt still loses volume at the same hinge: exhausted (the manual rungs)",
              next_rung(elbow, [{**a1, "report": rep({"LowerArm.R": 0.41})}]) is None)
        check("attempt fixed the elbow, the knee now fails: add the knee, same amount",
              next_rung(elbow, [{**a1, "report": rep({"LowerLeg.R": 0.36})}]) == {
                  "hinges": ["elbow", "knee"], "amount": 1.0, "why": "now also LowerLeg.R"})
        r09 = next_rung(elbow, [{**a1, "report": rep({"LowerArm.R": 0.30}, si=0.09)}])
        check("volume held, self-intersection rose: amount 0.9, then stop",
              r09 and r09["amount"] == 0.9 and next_rung(elbow, [{**a1, "report": {}}, {**r09, "report": rep(
                  {"LowerArm.R": 0.30}, si=0.09)}]) is None)
        check("never more than MAX_ATTEMPTS", next_rung(elbow, [{**a1, "report": rep({"LowerLeg.R": 0.4})}] * MAX_ATTEMPTS) is None)
        lim40 = rep({"LowerArm.L": 0.38}, lim=0.40)
        check("the limit is read from the report, never changed", classify(lim40)["passed"] and not classify(lim40)["over"])
        mk = {"height": 1.75, "landmarks": {"elbow.L": [0.37175, 0.07, 1.09901], "elbow.R": [-0.37175, 0.07, 1.09901],
                                            "shoulder.L": [0.20523, 0.1, 1.33], "shoulder.R": [-0.20523, 0.1, 1.33],
                                            "knee.L": [0.175, 0.08, 0.49875], "knee.R": [-0.175, 0.08, 0.49875]}}
        e = repair_regions(mk, "elbow")
        check("elbow bands from the markers: the documented runner bands and mask",
              e["below"] == [0.98, 1.01, 1.08, 1.095] and e["above"] == [1.103, 1.118, 1.19, 1.22]
              and e["snapshot"] == [0.95, 0.97, 1.22, 1.24] and e["mask"] == {"inner": 0.22, "outer": 0.25}, e=e)
        k_ = repair_regions(mk, "knee")
        small = repair_regions({**mk, "height": 0.875}, "elbow")
        check("a knee has no X mask; the offsets scale with the height",
              k_["mask"] is None and k_["below"][3] == round(0.49875 - 0.004, 3)
              and abs((small["above"][3] - 1.09901) - 0.121 / 2) < 1e-3, k=k_, small=small)
        rm = {"UpperArm.L": "arm_stretch.l", "LowerArm.L": "forearm_stretch.l", "UpperLeg.R": "thigh_stretch.r",
              "LowerLeg.R": "leg_stretch.r"}
        dfm = {"arm_stretch.l", "arm_twist.l", "forearm_stretch.l", "thigh_stretch.r", "leg_stretch.r", "leg_twist.r"}
        check("hinge bones: the contract bone, then its twist bone when it deforms",
              hinge_bones(rm, "elbow", "l", dfm) == (["arm_stretch.l", "arm_twist.l"], ["forearm_stretch.l"])
              and hinge_bones(rm, "knee", "r", dfm) == (["thigh_stretch.r"], ["leg_stretch.r", "leg_twist.r"])
              and hinge_bones(rm, "elbow", "r", dfm) == ([], []))
        # 4. exit codes and the summary through real child processes (a stand-in for Blender and every script)
        (td / "fake.py").write_text(FAKE, encoding="utf-8")
        trace = td / "trace.jsonl"
        fake = [sys.executable, str(td / "fake.py")]

        def real(argv, codes=None, **extra):
            trace.write_text("")
            env = {**os.environ, "FAKE_TRACE": str(trace), "FAKE_CODES": json.dumps(codes or {}),
                   **{k: (v if isinstance(v, str) else json.dumps(v)) for k, v in extra.items()}}
            OVERRIDE.update(blender=fake + ["-b"], python=fake)
            try:
                code, r, err = go(argv, None, env)
            finally:
                OVERRIDE.clear()
            ran = [json.loads(x)["script"] for x in trace.read_text().splitlines() if x.strip()]
            return code, r, err, ran

        chain = ["inside_prep", "mesh_check.py", "arp_markers.py", "inside_arp", "contract_map.py", "deform_gate.py"]
        run_dir = td / "run"
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner"],
                                 FAKE_DEFORM={"a1": ["LowerArm.R", 0.3492, 0.05]})
        rs = {s_["name"]: s_ for s_ in r.get("steps", [])}
        att = (r.get("repair") or {}).get("attempts") or []
        check("all: six stages, the elbow fails, attempt 1 repairs and passes, exit 0",
              code == 0 and ran == chain + ["inside_repair", "deform_gate.py"] and r.get("repair", {}).get("result")
              == "passed" and len(att) == 1, code=code, ran=ran, err=r.get("error"))
        check("all: every step timed, the deform step names its failed gate, the summary written, children's noise "
              "kept in the logs",
              all(isinstance(s_["seconds"], float) for s_ in rs.values())
              and rs["deform"]["failed_gates"] == ["deform.volume_loss_max"]
              and (run_dir / "autorig.all.json").exists() and "\u4e2d" not in err)
        check("all: the attempt lists hinges, amount, bands, the gate values; the result points at repair/a1",
              att and att[0]["hinges"] == ["elbow"] and att[0]["amount"] == 1.0
              and att[0]["regions"]["elbow"]["below"] == [0.98, 1.01, 1.08, 1.095]
              and att[0]["volume_loss_max"]["value"] == 0.3492 and att[0]["self_intersection_p95"] == 0.05
              and r["result"]["fbx"].endswith(os.path.join("repair", "a1", "Runner.fbx")), att=att)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner"],
                                 FAKE_DEFORM={"a1": ["LowerArm.R", 0.41, 0.05]})
        rp = r.get("repair") or {}
        check("all: the transfer does not hold, exhausted, exit 2, the message names the manual rungs",
              code == 2 and rp.get("result") == "exhausted" and len(rp.get("attempts", [])) == 1
              and "resolution" in rp.get("message", "") and "--adjust" in rp.get("message", ""), rp=rp)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner"],
                                 FAKE_DEFORM={"a1": ["LowerArm.R", 0.30, 0.09], "a2": ["LowerArm.R", 0.33, 0.07]})
        rp = r.get("repair") or {}
        check("all: intersections rose at 1.0, 0.9 passes on attempt 2, exit 0",
              code == 0 and [x["amount"] for x in rp.get("attempts", [])] == [1.0, 0.9], rp=rp)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--no-repair"])
        check("--no-repair: the deform gate's exit 2 stands", code == 2 and "repair" not in r and ran == chain)
        code, r, err, ran = real(["deform", str(run_dir), "--name", "Runner"], FAKE_DEFORM={"a0": ["Spine", 0.4, 0.04]})
        check("deform alone: a spine loss is not repaired, exit 2, said why",
              code == 2 and r["repair"]["result"] == "not_applicable" and ran == ["deform_gate.py"])
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner"], {"mesh_check.py": 2})
        check("all: a mesh check failure stops before the rig, exit 2", code == 2 and ran == chain[:2])
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner"], {"inside_arp": 1})
        check("all: an Auto-Rig Pro error stops, exit 1", code == 1 and ran == chain[:4])
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner"], {"contract_map.py": 2})
        check("all: a contract gate failure still gates the deformation, exit 2", code == 2 and ran[:6] == chain)
        code, r, err, ran = real(["markers", str(run_dir), "--name", "Runner"], FAKE_NO_OUT="arp_markers.py")
        check("a step that writes no report is an error, exit 1", code == 1)
        code, r, err, ran = real(["prep", str(run_dir), str(glb), "--name", "Runner"], FAKE_SILENT="inside_prep")
        check("a Blender run that never reports is an error, exit 1", code == 1)
        code, r, err, ran = real(["prep", str(run_dir), str(glb), "--name", "Runner"], {"inside_prep": 2})
        check("prep: a gate that fails comes through as exit 2", code == 2)
        code, r, err, ran = real(["fly", str(run_dir)])
        check("an unknown stage is refused, exit 1 (not argparse's 2)", code == 1 and ran == [])
        code, r, err, ran = real(["check", str(run_dir), "--bogus"])
        check("an unknown option is refused, exit 1", code == 1)
        code, r, _ = go(["markers", str(run_dir), "--name", "Runner", "--blender", str(td / "no-such-blender")])
        check("a missing Blender executable is an error, exit 1", code == 1)
    ok = all(c_["pass"] for c_ in checks)
    print(json.dumps({"tool": "autorig.py", "selftest": "pass" if ok else "fail", "checks": len(checks),
                      "failed": [c_ for c_ in checks if not c_["pass"]]}))
    return 0 if ok else 1


if __name__ == "__main__":
    _argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if _argv[:1] == ["_inside"]:
        inside(_argv[1:])
    sys.exit(main())
