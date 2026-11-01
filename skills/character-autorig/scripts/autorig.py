#!/usr/bin/env python3
"""autorig.py — character-autorig's stages for one character in one command, on Windows, macOS or Linux.

usage (in this order; `all` runs them one after another):
    autorig.py prep     OUT GLB [--name NAME] [--height 1.75] [--hair HAIR.glb] [--eyes EYES.glb] -> OUT/NAME.glb, .blend
    autorig.py check    OUT [--name NAME] [--body human|skirt]      -> rig/NAME.mesh.json
    autorig.py smart    OUT [--name NAME] [--facial] [--fingers 5|4] -> rig/NAME.smart.json, rig/NAME_smart.blend
    autorig.py markers  OUT [--name NAME] [--no-render] [--no-smart] [--body human|skirt] -> rig/NAME.markers.json
    autorig.py arp      OUT [--name NAME]                           -> rig/NAME_arp.blend, export/NAME.fbx
    autorig.py contract OUT [--name NAME] [--min-fingers 30]        -> rig/NAME.contract.json [rig/NAME.bind.json]
    autorig.py deform   OUT [--name NAME] [--no-render] [--no-repair] -> rig/NAME.deform.json [repair/aN/]
    autorig.py secondary OUT [--name NAME] [--no-render] [--secondary-markers FILE] [--hair-chains] -> secondary/
    autorig.py all      OUT GLB [any of the options above] [--no-secondary]
    autorig.py --selftest
Every stage takes --blender PATH (env BLENDER, default blender on PATH, else the usual install folder),
--python PATH (env PYTHON, default this interpreter; numpy for mesh_check), --threads N (Blender -t N) and
--dry-run (print the commands, run nothing). NAME defaults to the GLB's stem (prep, all), else the one .glb in OUT.

prep: blender-character-rig bcr_import_prep (height, backface culling, no weld) -> NAME.blend. check:
mesh_check.py on NAME.glb. smart: arp_smart.py --probe (headless) asks whether Auto-Rig Pro, its operators and
its AI files are there; only then arp_smart.py runs the add-on's AI on NAME.blend in a Blender WITH a window
(--fingers, --facial or --no-facial; it quits by itself). markers: arp_markers.py --mesh NAME (--adjust FILE
when given; --preview-dir
rig/markers/ unless --no-render; --smart rig/NAME.smart.json whenever smart wrote it, passed or not: the
markers read its gates one by one and take only what passed; never with --no-smart).
arp: blender-retarget brt_arp op pipeline (--resolution N: the bind's resolution), the rig saved as
rig/NAME_arp.blend, the Unity FBX in export/.
contract: unity-rigged-character contract_map.py map --map arp --require contract, --min-fingers 30 unless the
markers say fingers.mode fixed (a mitten; `ai` counts as found).

--body skirt (a long coat, a skirt, a robe; check, markers and all take it): mesh_check and arp_markers read the
legs under the hem and inside the skirt (reference/markers.md), and the markers carry `skirt`. Whenever they do,
the contract stage ends with skirt_bind (after parts_bind and eyes_bind; this file inside Blender, no
--factory-startup): in rig/NAME_arp.blend the skirt's own skin (arp_markers.skirt_region: the hem band up to the
hip + 0.06 H, off the legs) is reweighted to Hips and both thighs, the thighs' share rising smoothly from 0 at the
band's top to SKIRT_LEG_MAX at the hem and split left/right by a smoothstep across twice the hip width (no
seam between the thighs), feathered into the bind over the band's top SKIRT_FEATHER x H; then the FBX is exported
again. A bind that fails a gate stops the run. deform and secondary get --skirt rig/NAME.markers.json: the
deform gate reads the skirt's tear, the chains find its hem. deform: deform_gate.py on the FBX with the
contract's retarget_map (--render rig/poses/ unless --no-render; without fist when fingers.mode is fixed; with
jaw_open when deform_gate knows that pose, the markers carry the face and the contract maps a Jaw).
secondary (last, after the repair; --no-secondary skips it): secondary_chains.py on the rig to take on (the
passing repair's repair/aN/NAME_arp.blend, else rig/NAME_arp.blend; run alone, the newest autorig.deform.json or
autorig.all.json says which) with the contract report as --map, writing secondary/NAME_sec.blend, NAME.fbx (the
brt_arp export), NAME.secondary.json (secondary/1) and NAME.secondary.gate.json; then contract_map.py and
deform_gate.py again on that export (secondary/NAME.contract.json, NAME.deform.json), which deform_gate reads as
without the chains: the summary's `secondary` block puts both volume readings side by side. A body with nothing
loose writes an empty chain list and adds no bone; the two re-checks are skipped and the files to take on stay.
A deform stage that failed skips it. A separate hair object (parts_bind's) stays rigid on Head unless
--hair-chains, which passes the same flag down: spikes found on the hair object get chains weighted on it.

parts_bind (a character in parts, blender-character-rig assemble_parts.py): prep and all take --hair, the
assembly's <c>_hair.glb, copied to OUT/NAME_hair.glb (prep without --hair removes an earlier copy); whenever
that file is there, the contract stage ends with `assemble_parts.py bind OUT --hair OUT/NAME_hair.glb --rig-glb
OUT/NAME.glb --name NAME --report rig/NAME.bind.json` (no --factory-startup), which binds the hair rigidly to the
contract's Head bone in rig/NAME_arp.blend and exports the FBX again, so the first deform gate, every repair
and the spring chains already have the hair. A bind that fails a gate stops the run (exit 2) before deform.
eyes_bind likewise: prep and all take --eyes, blender-character-rig eye_fit.py fit's <c>_eyes.glb, copied to
OUT/NAME_eyes.glb (removed by a prep without it); with --facial the smart stage hands them to the add-on as
its eyeballs (arp_smart.py --eyes objects --eye-glb OUT/NAME_eyes.glb --eye-frame-glb OUT/NAME.glb), and
after parts_bind the contract stage runs `eye_fit.py bind OUT --eyes OUT/NAME_eyes.glb --rig-glb OUT/NAME.glb
--name NAME --report rig/NAME.eyes_bind.json`: each eyeball rigid on its eye bone (Head without a face).

smart never stops `all`: without the add-on or its AI files it is skipped (no exit change); a smart that fails
(a gate, an error, a timeout) makes the run's exit 2, and the markers take what passed from its report (a face
that failed leaves the AI's fingers) or go on from slices alone when it wrote none. Run on its own, `smart`
refuses (exit 1) when the probe finds no add-on or AI files.

Repair ladder (deform, on unless --no-repair): when the only failing gate is deform.volume_loss_max and every
joint over the limit is an elbow (LowerArm.*) or a knee (LowerLeg.*), each attempt opens rig/NAME_arp.blend,
moves weight across that hinge with brt_weights (one snapshot, then per side: below the joint the upper bones'
weight to the lower bone, above it the lower bones' weight to the upper bone, amount 1.0, a narrow band at the
crease left blended; the elbow masked off the torso), runs brt_arp op export and saves a copy into repair/aN/,
then gates that FBX again. The bands come from the markers (the joint's height, the shoulder's width), scaled
with the height. Next attempt: a hinge that only now fails is added; volume held but self-intersection failed
-> amount 0.9; anything else stops. deform.cross_side_weight failing (alone or with that hinge loss) adds a
cross-side move to the attempt: the bones the report's skin.cross_side names give their weight past its band_m
on the other side to their mirrored twins (brt_weights, share reach; --cross-side, --cross-band); still failing
after it stops the ladder (rebind). The limits are never changed. A finer bind and a moved marker are not
automated: the failure message names them (reference/arp-pipeline.md).

Blender runs headless except smart (the AI reads pictures of the 3D view; --python-exit-code 1 closes its window
on a script error, and it is killed after its timeout plus margins); prep, markers and deform with
--factory-startup, smart, arp, parts_bind, repair and secondary without it (Auto-Rig Pro is an add-on). Commands are argument lists
(no shell, no inline Python), so a Windows path passes as is; the
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
STAGES = ("prep", "check", "smart", "markers", "arp", "contract", "deform", "secondary")
STOP_ON_GATE = {"check", "markers", "arp", "deform"}   # a later stage cannot use what these failed to make
STOP_STEPS = {"parts_bind", "eyes_bind", "skirt_bind"}   # a failed bind leaves the FBX without the part: deform would gate the wrong file
NO_FIST = "arms_up,deep_squat,torso_twist,leg_raise,elbow_120"
DEFORM_POSES = ("arms_up", "deep_squat", "torso_twist", "fist", "leg_raise", "elbow_120")   # deform_gate.POSES
SMART_KILL = 600 + 60 + 120       # arp_smart's --timeout, its watchdog's margin, then the window is killed
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
CROSS = "deform.cross_side_weight"
CROSS_BAND = 0.5          # deform_gate.CROSS_BAND: x the hip half-width either side of the Hips is left alone
MAX_ATTEMPTS = 3
SKIRT_LEG_MAX = 0.85      # skirt_bind: the thighs' share at the hem (the rest stays on Hips)
SKIRT_FEATHER = 0.03      # skirt_bind: x H under the band's top over which the new weights blend into the bind
MANUAL_RUNGS = ("by hand, one at a time, each gated again (autorig.py deform): a finer bind (autorig.py arp OUT "
                "--resolution, brt_arp pipeline 'resolution' one step up), then the joint marker moved to the "
                "crease (autorig.py markers OUT --adjust FILE, arp_markers.py --adjust); never a looser limit "
                "(reference/arp-pipeline.md)")
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
                  "repair": o / "repair", "smart": o / "rig" / f"{n}.smart.json",
                  "smart_blend": o / "rig" / f"{n}_smart.blend", "smart_probe": o / "logs" / "smart_probe.json",
                  "hair": o / f"{n}_hair.glb", "bind": o / "rig" / f"{n}.bind.json",
                  "eyes": o / f"{n}_eyes.glb", "eyes_bind": o / "rig" / f"{n}.eyes_bind.json",
                  "skirt_bind": o / "rig" / f"{n}.skirt_bind.json"}
        sec = o / "secondary"
        self.f.update({"sec_dir": sec, "sec_blend": sec / f"{n}_sec.blend", "sec_fbx": sec / f"{n}.fbx",
                       "sec_skeleton": sec / f"{n}.skeleton.json", "sec_json": sec / f"{n}.secondary.json",
                       "sec_gate": sec / f"{n}.secondary.gate.json", "sec_contract": sec / f"{n}.contract.json",
                       "sec_deform": sec / f"{n}.deform.json", "sec_pics": sec / "pics", "sec_poses": sec / "poses"})
        self.repair = None        # this run's repair block, once the deform stage ran
        self.deform_ran = False
        self.chains = None        # chains the secondary step placed (None: not run)
        self.smart = None      # this run's smart: None (not run), planned, ready, passed, failed, skipped
        self.markers_smart = []   # the --smart the markers were given
        self.smart_why = None     # the probe's failed gates, or the smart step's failed gates or error
        self.args = a


def safe_name(stem: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", stem).strip("_") or "Character"


def find_name(out: Path) -> str:
    hits = sorted(out.glob("*.glb")) if out.is_dir() else []
    if len(hits) != 1:
        raise Refused(f"pass --name: {out} holds {len(hits)} .glb files (run 'prep' first)")
    return hits[0].stem


def blender_cmd(c: Ctx, script: Path, *args, blend=None, factory=True, background=True) -> list:
    # a window stays open after a script error unless told to exit: --python-exit-code closes it
    return (c.blender + (["-b"] if background else ["--python-exit-code", "1"])
            + (["--factory-startup"] if factory else [])
            + (["-t", str(c.threads)] if c.threads else []) + ([str(blend)] if blend else [])
            + ["-P", str(script), "--"] + [str(x) for x in args])


def py_cmd(c: Ctx, script: Path, *args) -> list:
    return c.python + [str(script)] + [str(x) for x in args]


def need(c: Ctx, path: Path, stage: str):
    if not c.dry and not Path(path).exists():
        raise Refused(f"missing {path} (run the '{stage}' stage first)")


def step(name, cmd, report_file, log, kind="file", **extra) -> dict:
    return {"name": name, "cmd": [str(x) for x in cmd], "report": str(report_file), "log": str(log), "kind": kind,
            **extra}


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
    """The markers' fingers.mode is 'fixed' (a mitten); None while the markers are not written yet. 'ai'
    (Auto-Rig Pro's AI placed them) and 'auto' are fingers found."""
    m = read_json(c.f["markers"])
    return None if m is None else (m.get("fingers") or {}).get("mode") == "fixed"


def smart_args(c: Ctx, a) -> list:
    """--smart FILE for the markers whenever smart wrote an autorig-smart/1 report, passed or not: arp_markers
    reads its gates one by one (body, fingers, face, Go!) and takes only what passed. A stage run on its own
    takes an earlier report. Never with --no-smart, nor when this run skipped smart."""
    if a.no_smart or c.smart == "skipped":
        return []
    if c.smart == "planned" or (read_json(c.f["smart"]) or {}).get("schema") == "autorig-smart/1":
        return ["--smart", c.f["smart"]]
    return []


def deform_pose_names(src: Path = HERE / "deform_gate.py") -> tuple:
    """deform_gate.POSES and NAMED_ONLY (poses run only when named) read from its source (it imports bpy,
    so it is parsed, not imported)."""
    import ast
    found = {}
    try:
        for node in ast.parse(src.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if getattr(t, "id", None) in ("POSES", "NAMED_ONLY"):
                        found[t.id] = tuple(ast.literal_eval(node.value))
    except (OSError, SyntaxError, ValueError):
        pass
    return found.get("POSES", DEFORM_POSES) + found.get("NAMED_ONLY", ())


def deform_poses(known: tuple, fixed: bool | None, jaw: bool) -> str | None:
    """--poses for deform_gate: None (all) unless a mitten drops fist or a face adds jaw_open (all,jaw_open:
    `all` keeps fist's skip rule). jaw_open only when deform_gate knows it; otherwise it is never named."""
    jaw = jaw and "jaw_open" in known
    if not fixed:
        return "all,jaw_open" if jaw else None
    return ",".join([p for p in known if p != "jaw_open" and p != "fist"] + (["jaw_open"] if jaw else []))


def is_skirt(c: Ctx, a=None) -> bool:
    """--body skirt, or the markers carry a skirt (arp_markers --body skirt: a stage run alone)."""
    if getattr(a, "body", "human") == "skirt":
        return True
    return (read_json(c.f["markers"]) or {}).get("body") == "skirt"


def skirt_arg(c: Ctx, a=None) -> list:
    return ["--skirt", c.f["markers"]] if is_skirt(c, a) else []


def has_jaw(c: Ctx) -> bool:
    """The markers carry the face (facial true) and the contract maps a Jaw bone."""
    m, k = read_json(c.f["markers"]) or {}, read_json(c.f["contract"]) or {}
    return bool(m.get("facial")) and "Jaw" in (k.get("retarget_map") or {})


def take_on(c: Ctx) -> tuple:
    """(blend, deform report) of the rig to take on: a passing repair's copy, else rig/NAME_arp.blend. When the
    deform stage ran in this run its repair decides; else the newest autorig.deform.json / autorig.all.json."""
    blocks = [c.repair] if c.deform_ran else [
        (read_json(p) or {}).get("repair") for p in sorted((c.out / f"autorig.{s}.json" for s in ("deform", "all")),
                                                          key=lambda p: p.stat().st_mtime if p.exists() else 0,
                                                          reverse=True) if p.exists()][:1]
    for r in blocks:
        files = (r or {}).get("files") or {}
        if (r or {}).get("result") == "passed" and files.get("blend"):
            return Path(files["blend"]), Path(files.get("deform") or c.f["deform"])
    return c.f["arp_blend"], c.f["deform"]


# --- the stages: each a list of steps, planned when it is about to run ---------------------------------------------
def plan(c: Ctx, stage: str, a) -> list:
    f, logs = c.f, c.f["logs"]
    if stage == "prep":
        if c.glb is None:
            raise Refused("prep needs the GLB")
        if not c.dry and not c.glb.exists():
            raise Refused(f"missing {c.glb}")
        if a.hair and not c.dry and not Path(a.hair).exists():
            raise Refused(f"missing --hair {a.hair}")
        if a.eyes and not c.dry and not Path(a.eyes).exists():
            raise Refused(f"missing --eyes {a.eyes}")
        return [step("prep", blender_cmd(c, SELF, "_inside", "prep", "--glb", f["glb"], "--name", c.name,
                                         "--height", a.height, "--save", f["blend"], "--report", f["prep"]),
                     f["prep"], logs / "prep.log", kind="inner")]
    if stage == "check":
        need(c, f["glb"], "prep")
        body = ["--body", "skirt"] if a.body == "skirt" else []
        return [step("check", py_cmd(c, HERE / "mesh_check.py", f["glb"], "--out", f["mesh"], *body), f["mesh"],
                     logs / "check.log", kind="python")]
    if stage == "smart":
        need(c, f["blend"], "prep")
        if a.no_smart:
            return []
        probe = step("smart_probe", blender_cmd(c, HERE / "arp_smart.py", "--probe", "--out", f["smart_probe"],
                                                factory=False), f["smart_probe"], logs / "smart_probe.log", kind="inner")
        eyes = ["--eyes", "objects", "--eye-glb", f["eyes"], "--eye-frame-glb", f["glb"]] if a.facial and (
            f["eyes"].exists() or (c.dry and getattr(a, "eyes", None))) else []
        run = step("smart", blender_cmd(c, HERE / "arp_smart.py", "--mesh", c.name, "--out", f["smart"],
                                        "--save-blend", f["smart_blend"], "--fingers", a.fingers,
                                        "--facial" if a.facial else "--no-facial", *eyes, blend=f["blend"], factory=False,
                                        background=False), f["smart"], logs / "smart.log", kind="inner",
                   after_probe=True, timeout=SMART_KILL)
        return [probe, run]
    if stage == "markers":
        need(c, f["blend"], "prep")
        prev = [] if a.no_render else ["--preview-dir", f["previews"]]
        c.markers_smart = smart_args(c, a)
        adj = ["--adjust", Path(os.path.abspath(a.adjust))] if a.adjust else []
        adj += ["--body", "skirt"] if a.body == "skirt" else []
        return [step("markers", blender_cmd(c, HERE / "arp_markers.py", "--mesh", c.name, "--out", f["markers"],
                                            *c.markers_smart, *adj, *prev, blend=f["blend"]), f["markers"],
                     logs / "markers.log")]
    if stage == "arp":
        need(c, f["blend"], "prep"); need(c, f["markers"], "markers")
        return [step("arp", blender_cmd(c, SELF, "_inside", "arp", "--mesh", c.name, "--markers", f["markers"],
                                        "--fbx", f["fbx"], "--save", f["arp_blend"], "--report", f["arp"],
                                        *(["--resolution", a.resolution] if a.resolution else []),
                                        blend=f["blend"], factory=False), f["arp"], logs / "arp.log", kind="inner")]
    if stage == "contract":
        need(c, f["skeleton"], "arp")
        fingers = [] if fingers_fixed(c) else ["--min-fingers", a.min_fingers]
        steps = [step("contract", py_cmd(c, CONTRACT_MAP, "map", f["skeleton"], "--map", "arp", "--require",
                                         "contract", *fingers, "--out", f["contract"]), f["contract"],
                      logs / "contract.log", kind="python")]
        if f["hair"].exists() or (c.dry and getattr(a, "hair", None)):   # a character in parts: hair on Head
            steps.append(step("parts_bind", blender_cmd(c, BCR / "assemble_parts.py", "bind", c.out, "--hair",
                                                        f["hair"], "--rig-glb", f["glb"], "--name", c.name,
                                                        "--report", f["bind"], factory=False),
                              f["bind"], logs / "parts_bind.log"))
        if f["eyes"].exists() or (c.dry and getattr(a, "eyes", None)):   # eyeballs: rigid on the eye bones
            steps.append(step("eyes_bind", blender_cmd(c, BCR / "eye_fit.py", "bind", c.out, "--eyes", f["eyes"],
                                                       "--rig-glb", f["glb"], "--name", c.name,
                                                       "--report", f["eyes_bind"], factory=False),
                              f["eyes_bind"], logs / "eyes_bind.log"))
        if is_skirt(c, a):   # a long coat or skirt: its skin off the thighs' seam, before any deform gate
            steps.append(step("skirt_bind", blender_cmd(c, SELF, "_inside", "skirt", "--markers", f["markers"],
                                                        "--contract", f["contract"], "--fbx", f["fbx"],
                                                        "--save", f["arp_blend"], "--report", f["skirt_bind"],
                                                        blend=f["arp_blend"], factory=False),
                              f["skirt_bind"], logs / "skirt_bind.log", kind="inner"))
        return steps
    if stage == "deform":
        need(c, f["fbx"], "arp"); need(c, f["contract"], "contract")
        return [deform_step(c, "deform", f["fbx"], f["deform"], None if a.no_render else f["poses"], logs)]
    if stage == "secondary":
        if a.no_secondary:
            return []
        blend, _ = take_on(c)
        need(c, blend, "arp"); need(c, f["contract"], "contract")
        extra = (["--markers", Path(os.path.abspath(a.secondary_markers))] if a.secondary_markers else []) + \
            skirt_arg(c, a) + \
            (["--hair-chains"] if a.hair_chains else []) + ([] if a.no_render else ["--render", f["sec_pics"]])
        fingers = [] if fingers_fixed(c) else ["--min-fingers", a.min_fingers]
        return [step("secondary", blender_cmd(c, HERE / "secondary_chains.py", "--mesh", c.name, "--map", f["contract"],
                                              "--save", f["sec_blend"], "--fbx", f["sec_fbx"], "--out", f["sec_json"],
                                              "--report", f["sec_gate"], *extra, blend=blend, factory=False),
                     f["sec_gate"], logs / "secondary.log"),
                step("secondary_contract", py_cmd(c, CONTRACT_MAP, "map", f["sec_skeleton"], "--map", "arp", "--require",
                                                  "contract", *fingers, "--out", f["sec_contract"]), f["sec_contract"],
                     logs / "secondary_contract.log", kind="python", after_chains=True),
                dict(deform_step(c, "secondary_deform", f["sec_fbx"], f["sec_deform"],
                                 None if a.no_render else f["sec_poses"], logs, f["sec_contract"]), after_chains=True)]
    raise Refused(f"unknown stage {stage}")


def deform_step(c: Ctx, name, fbx, out, render, logs, contract=None) -> dict:
    chosen = deform_poses(deform_pose_names(), fingers_fixed(c), has_jaw(c))
    poses = ["--poses", chosen] if chosen else []
    rend = ["--render", render] if render else []
    return step(name, blender_cmd(c, HERE / "deform_gate.py", "--fbx", fbx, "--map", contract or c.f["contract"],
                                  *poses, *rend, *skirt_arg(c, c.args), "--out", out), out, logs / f"{name}.log")


def cross_arg(cross: dict | None, band=None) -> list:
    """--cross-side 'L:bone,bone;R:bone' (per side, the other side's bones whose weight there moves to their twins)
    and --cross-band, the deform report's band_m (the gate's own reach from the midline)."""
    parts = [f"{s}:{','.join(b)}" for s, b in sorted((cross or {}).items()) if b]
    return (["--cross-side", ";".join(parts)] + (["--cross-band", band] if band else [])) if parts else []


def repair_steps(c: Ctx, n: int, rung: dict, render: bool) -> tuple[list, dict]:
    d = c.f["repair"] / f"a{n}"
    files = {"dir": d, "fbx": d / f"{c.name}.fbx", "blend": d / f"{c.name}_arp.blend", "deform": d / f"{c.name}.deform.json",
             "repair": d / "repair.json"}
    fix = step(f"repair_a{n}", blender_cmd(c, SELF, "_inside", "repair", "--markers", c.f["markers"], "--contract",
                                           c.f["contract"], "--hinges", ",".join(rung["hinges"]), "--amount",
                                           rung["amount"], *cross_arg(rung.get("cross_side"), rung.get("cross_band")),
                                           "--fbx", files["fbx"], "--save", files["blend"],
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
    volume_ok = "deform.volume_loss_max" not in failed or (bool(over) and all(j.split(".")[0] in HINGE_OF for j in over))
    repairable = bool(failed) and set(failed) <= {"deform.volume_loss_max", CROSS} and volume_ok
    cross = (rep.get("skin") or {}).get("cross_side") or {}
    cross_bones = {s: sorted((cross.get(s) or {}).get("bones") or {}) for s in ("L", "R")} if CROSS in failed else {}
    if CROSS in failed and not any(cross_bones.values()):
        repairable, cross_bones = False, {}       # a report that does not name the bones: nothing to move
    return {"passed": bool(gates) and not failed, "failed_gates": failed, "over": over, "hinges": hinges,
            "cross_side": cross_bones, "cross_band": cross.get("band_m") if cross_bones else None,
            "repairable": repairable}


def _why(k: dict) -> str:
    return "; ".join((["weight across the midline on " + ", ".join(b for s in "LR" for b in k["cross_side"][s])]
                      if k["cross_side"] else []) + (["volume loss at " + ", ".join(sorted(k["over"]))] if k["over"] else []))


def next_rung(base: dict, attempts: list) -> dict | None:
    """The next attempt ({hinges, amount, cross_side, why}) or None: passed, not a hinge-only volume loss or a
    cross-side weight, or exhausted. cross_side {L, R}: the other side's bones holding each side's skin (the
    deform report names them); their weight there moves to their mirrored twins, always in full."""
    if len(attempts) >= MAX_ATTEMPTS:
        return None
    if not attempts:
        k = classify(base)
        return {"hinges": k["hinges"], "amount": AMOUNTS[0], "cross_side": k["cross_side"],
                "cross_band": k["cross_band"], "why": _why(k)} if k["repairable"] else None
    last = attempts[-1]
    k = classify(last.get("report") or {})
    if k["passed"]:
        return None
    if k["repairable"]:
        if k["cross_side"] and last.get("cross_side"):
            return None   # the move across the midline did not hold: rebind
        hinges = sorted(set(last["hinges"]) | set(k["hinges"]))
        if hinges != sorted(last["hinges"]) or k["cross_side"]:
            keep = bool(last.get("cross_side"))
            return {"hinges": hinges, "amount": last["amount"], "cross_side": last["cross_side"] if keep else k["cross_side"],
                    "cross_band": last.get("cross_band") if keep else k["cross_band"], "why": "now also " + _why(k)}
        return None   # the transfer did not hold this hinge: the manual rungs
    if k["failed_gates"] == ["deform.self_intersection_p95"] and last["hinges"] and last["amount"] in AMOUNTS:
        i = AMOUNTS.index(last["amount"])
        if i + 1 < len(AMOUNTS):
            return {"hinges": last["hinges"], "amount": AMOUNTS[i + 1], "cross_side": last.get("cross_side") or {},
                    "cross_band": last.get("cross_band"), "why": "volume held, self-intersection rose: a softer hand-over"}
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
    return {"attempt": n, "hinges": rung["hinges"], "amount": rung["amount"], "cross_side": rung.get("cross_side") or {},
            "why": rung.get("why"), "regions": regions, "exit_code": max((s["exit_code"] for s in steps_done), default=1),
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
        group = bool(st.get("timeout")) and os.name == "posix"   # a killed window takes its AI programs along
        p = subprocess.Popen(st["cmd"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True,
                             encoding="utf-8", errors="replace", bufsize=1, start_new_session=group)
        out_lines = []
        echo = None if st["kind"] == "python" else ECHO
        ts = [threading.Thread(target=_pump, args=(p.stdout, logf, echo, out_lines, p), daemon=True),
              threading.Thread(target=_pump, args=(p.stderr, logf, echo, None), daemon=True)]
        for t in ts:
            t.start()
        killed = False
        try:
            code = p.wait(timeout=st.get("timeout"))
        except subprocess.TimeoutExpired:   # a windowed Blender that never quit: killed, an error
            killed = True
            if group:
                import signal
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except OSError:
                    p.kill()
            else:
                p.kill()
            p.wait()
            code = 1
        for t in ts:
            t.join(timeout=10 if killed else None)   # a child that kept the pipe open must not hang us
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
        if rung.get("cross_side"):
            regions["cross_side"] = {"band_m": rung.get("cross_band")}
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
            p.add_argument("--hair", help="a character in parts: the assembly's <c>_hair.glb, bound after contract")
            p.add_argument("--eyes", help="eye_fit.py fit's <c>_eyes.glb: the face's eyeballs, bound after contract")
        if s in ("markers", "deform", "secondary", "all"):
            p.add_argument("--no-render", action="store_true", help="no marker pictures, no pose renders")
        if s in ("smart", "markers", "all"):
            p.add_argument("--no-smart", action="store_true", help="no Auto-Rig Pro AI: slice markers alone")
        if s in ("check", "markers", "all"):
            p.add_argument("--body", choices=("human", "skirt"), default="human",
                           help="skirt: a long coat, skirt or robe (the legs read under its hem, the skirt bound "
                                "off the thighs' seam)")
        if s in ("markers", "all"):
            p.add_argument("--adjust", help="arp_markers.py --adjust: JSON {marker: [x, y, z]} a person placed")
        if s in ("arp", "all"):
            p.add_argument("--resolution", type=int, help="the bind's voxel resolution (brt_arp; default 7): "
                                                          "one step up at a time for a finer bind")
        if s in ("smart", "all"):
            p.add_argument("--facial", action="store_true", help="the AI's face markers and references too")
            p.add_argument("--fingers", type=int, choices=(5, 4), default=5, help="fingers the AI fits (5 falls back to 4)")
        if s in ("contract", "all"):
            p.add_argument("--min-fingers", type=int, default=30)
        if s in ("deform", "all"):
            p.add_argument("--no-repair", action="store_true")
        if s in ("secondary", "all"):
            p.add_argument("--secondary-markers", help="manual chains for secondary_chains.py --markers")
            p.add_argument("--hair-chains", action="store_true", help="spring chains on the separate hair object")
        if s == "all":
            p.add_argument("--no-secondary", action="store_true", help="no spring chains")
    return ap


def parse(argv) -> argparse.Namespace:
    a = parser().parse_args(argv)
    for k, v in (("glb", None), ("height", 1.75), ("no_render", False), ("min_fingers", 30), ("no_repair", False),
                 ("no_smart", False), ("facial", False), ("fingers", 5), ("no_secondary", False),
                 ("secondary_markers", None), ("hair", None), ("hair_chains", False), ("eyes", None),
                 ("adjust", None), ("resolution", None), ("body", "human")):
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
            if "smart" in stages and not a.no_smart:
                c.smart = "planned"
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
    done, rc, repair, smart_rc = [], 0, None, 0    # smart's exit is kept apart: it never stops a later stage
    stop = False
    try:
        if "prep" in stages and c.glb and c.glb != c.f["glb"]:
            shutil.copyfile(c.glb, c.f["glb"])
        if "prep" in stages:      # the hair copy follows the prepped GLB: a whole mesh leaves none behind
            hair = Path(os.path.abspath(a.hair)) if a.hair else None
            if hair is not None and hair != c.f["hair"]:
                shutil.copyfile(hair, c.f["hair"])
            elif hair is None and c.f["hair"].exists():
                c.f["hair"].unlink()
            eyes = Path(os.path.abspath(a.eyes)) if a.eyes else None
            if eyes is not None and eyes != c.f["eyes"]:
                shutil.copyfile(eyes, c.f["eyes"])
            elif eyes is None and c.f["eyes"].exists():
                c.f["eyes"].unlink()
        if a.no_smart:
            c.smart = "skipped"
        for s in stages:
            for st in plan(c, s, a):
                if st.get("after_probe") and c.smart == "skipped":
                    continue
                if st.get("after_chains") and (not c.chains or not c.f["sec_fbx"].exists()):
                    continue          # nothing loose (the rig is unchanged), or no export to check
                code, rep, sec = run_step(st, c.env)
                done.append(done_entry(st, code, rep, sec))
                if s == "smart":
                    smart_rc = max(smart_rc, smart_outcome(c, st, code, rep, alone=a.stage == "smart"))
                    continue
                if st["name"] == "secondary":
                    c.chains = len((rep or {}).get("chains") or []) if code != 1 else None
                if s == "deform" and code == 2 and not a.no_repair and rep:
                    repair = ladder(c, a, rep, done)
                    code = 0 if repair["result"] == "passed" else 1 if repair["result"] == "error" else 2
                if s == "deform":
                    c.deform_ran, c.repair = True, repair
                if code == 1:
                    rc = 1
                    break
                rc = max(rc, code)
                if code == 2 and st["name"] in STOP_STEPS:
                    stop = True
                    break
            if rc == 1 or stop or (rc == 2 and s in STOP_ON_GATE):
                break
    except Refused as exc:
        out.update({"steps": done, "ok": False, "exit_code": 1, "error": f"refused: {exc}"})
        return _emit(c, a, out, 1)
    except OSError as exc:   # the Blender or Python executable is missing
        out.update({"steps": done, "ok": False, "exit_code": 1, "error": f"{type(exc).__name__}: {exc}"})
        return _emit(c, a, out, 1)
    rc = rc if rc == 1 else max(rc, smart_rc)
    out["steps"] = done
    out["smart"] = {"result": c.smart or "not_run",
                    "report": str(c.f["smart"]) if c.smart in ("passed", "failed") and c.f["smart"].exists() else None,
                    "markers_used_it": bool(c.markers_smart)}
    if c.smart_why:
        out["smart"]["why"] = c.smart_why
    if c.smart in ("failed", "skipped") and "markers" in stages and not a.no_smart:
        out["smart"]["note"] = ("the markers took what passed in the AI's report, slices for the rest"
                                if c.markers_smart else "the markers came from slices alone")
    if repair is not None:
        out["repair"] = repair
    files = {"blend": c.f["arp_blend"], "fbx": c.f["fbx"], "contract": c.f["contract"], "deform": c.f["deform"]}
    files.update((repair or {}).get("files") or {})
    if c.chains is not None:
        out["secondary"] = secondary_summary(c)
        files["secondary"] = c.f["sec_json"]
        if c.chains and rc == 0:
            files.update(blend=c.f["sec_blend"], fbx=c.f["sec_fbx"], contract=c.f["sec_contract"],
                         deform=c.f["sec_deform"])
    out["result"] = {k: str(v) for k, v in files.items() if Path(v).exists()}
    hint = (read_json(c.f["mesh"]) or {}).get("skirt_hint") if "check" in stages else None
    if hint:
        out["skirt_hint"] = hint
    out.update({"exit_code": rc, "ok": rc == 0})
    return _emit(c, a, out, rc)


def secondary_summary(c: Ctx) -> dict:
    """The chains placed and the deform gate's volume reading before and after them (the same skin outside the
    chains' regions: deform_gate reads the bones they hang from as without them)."""
    gate = read_json(c.f["sec_gate"]) or {}
    _, before = take_on(c)
    vol = lambda p: ((read_json(p) or {}).get("volume_loss_max") or {}).get("value")
    out = {"chains": c.chains, "found": (gate.get("detect") or {}).get("found"),
           "colliders": gate.get("colliders"), "report": str(c.f["sec_gate"])}
    if c.chains:
        out["volume_loss_max"] = {"without_chains": vol(before), "with_chains": vol(c.f["sec_deform"])}
    return out


def smart_outcome(c: Ctx, st: dict, code: int, rep: dict | None, alone: bool) -> int:
    """What a smart step adds to the run's exit code. The probe: ready runs the window, not ready skips it
    (refused when `smart` runs alone). The window: passed, or failed (exit 2 in `all`, never a stop)."""
    failed = [g.get("name") for g in (rep or {}).get("gates", []) if gate_failed(g)]
    if st["name"] == "smart_probe":
        if code == 0 and (rep or {}).get("ready") is True:
            c.smart = "ready"
            return 0
        c.smart = "skipped"
        c.smart_why = failed or (rep or {}).get("error") or f"the probe exited {code}"
        return 1 if alone else (2 if code == 1 else 0)
    c.smart = "passed" if code == 0 else "failed"
    if code:
        c.smart_why = failed or (rep or {}).get("error") or (rep or {}).get("refused") or f"exit {code}, no report"
    return code if alone else (0 if code == 0 else 2)


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
    p.add_argument("what", choices=("prep", "arp", "repair", "skirt"))
    for k in ("glb", "name", "save", "report", "mesh", "markers", "fbx", "contract", "hinges", "backup_dir",
              "cross_side"):
        p.add_argument("--" + k.replace("_", "-"))
    p.add_argument("--height", type=float); p.add_argument("--amount", type=float)
    p.add_argument("--cross-band", type=float); p.add_argument("--resolution", type=int)
    a = p.parse_args(argv)
    try:
        rep, code = {"prep": _in_prep, "arp": _in_arp, "repair": _in_repair, "skirt": _in_skirt}[a.what](a)
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
    r = brt_arp.run({"op": "pipeline", "mesh": a.mesh, "markers": a.markers, "fbx": a.fbx, "report_path": a.report,
                     **({"resolution": a.resolution} if a.resolution else {})})
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
    hair = lambda o: o.get("parts_hair") or o.name.split(".")[0] == "Hair"     # parts_bind's: rigid on Head
    bound = [(o, m.object) for o in bpy.data.objects if o.type == 'MESH' and not hair(o)
             for m in o.modifiers if m.type == 'ARMATURE' and m.object is not None and m.object.type == 'ARMATURE']
    if not bound:
        return {"ok": False, "error": "no mesh is bound to an armature in this file"}, 1
    mesh, rig = max(bound, key=lambda t: len(t[0].data.vertices))
    deform = {b.name for b in rig.data.bones if b.use_deform}
    Path(a.backup_dir).mkdir(parents=True, exist_ok=True)
    log = {"mesh": mesh.name, "armature": rig.name, "amount": a.amount, "hinges": {}}
    short = lambda r: {**{k: r.get(k) for k in ("reason", "message", "changed_vertices") if k in r},
                       "ok": bool(report_passed(r))}
    if a.cross_side:
        log["cross_side"] = _in_cross_side(brt_weights, mesh, rig, rmap, deform, parse_cross(a.cross_side),
                                           Path(a.backup_dir) / "cross_side.npz", short, a.cross_band)
        if log["cross_side"].get("error"):
            return {"ok": False, "error": log["cross_side"]["error"], **log}, 1
    for hinge in [h for h in (a.hinges or "").split(",") if h]:
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


def skirt_weights(V, W, cols: dict, sk: dict, region) -> np.ndarray:
    """skirt_bind's weights (numpy, no Blender): rows of W (vertices x groups) inside `region` become Hips and
    both thighs (cols {"Hips", "UpperLeg.L", "UpperLeg.R"}: column indices), the thighs' share alpha rising by a
    smoothstep from 0 at the band's top to SKIRT_LEG_MAX at the hem, split left/right by a smoothstep over twice
    the hip half-width around the midline; blended into the old row over SKIRT_FEATHER x H under the top. At
    most 4 weights per row (the smallest dropped), each row summing to 1."""
    import numpy as np
    W = np.array(W, dtype=float)
    sm = lambda x: (lambda y: y * y * (3 - 2 * y))(np.clip(x, 0.0, 1.0))
    idx = np.nonzero(region)[0]
    z, x = V[idx, 2], V[idx, 0]
    top, hem, H = float(sk["top_z"]), float(sk["hem_z"]), float(sk["height"])
    alpha = SKIRT_LEG_MAX * sm((top - z) / max(top - hem, 1e-6))
    lam = sm((x - float(sk["midline_x"])) / (4 * max(float(sk["half_width"]), 1e-4)) + 0.5)
    beta = sm((top - z) / (SKIRT_FEATHER * H))
    new = np.zeros((len(idx), W.shape[1]))
    new[:, cols["Hips"]] = 1 - alpha
    new[:, cols["UpperLeg.L"]] += alpha * lam
    new[:, cols["UpperLeg.R"]] += alpha * (1 - lam)
    old = W[idx]
    s = old.sum(axis=1, keepdims=True)
    old = np.divide(old, s, out=np.zeros_like(old), where=s > 1e-9)
    rows = (1 - beta)[:, None] * old + beta[:, None] * new
    if rows.shape[1] > 4:
        cut = np.argsort(-rows, axis=1)[:, 4:]
        np.put_along_axis(rows, cut, 0.0, axis=1)
    rows /= np.maximum(rows.sum(axis=1, keepdims=True), 1e-12)
    W[idx] = rows
    return W


def _in_skirt(a):
    """skirt_bind: the skirt's own skin reweighted off the thighs' seam (skirt_weights), the FBX exported again."""
    import bpy
    import numpy as np
    sys.path.insert(0, str(BRT))
    sys.path.insert(0, str(HERE))
    import brt_arp
    import arp_markers
    markers = json.loads(Path(a.markers).read_text(encoding="utf-8"))
    sk = markers.get("skirt")
    if markers.get("body") != "skirt" or not sk:
        return {"ok": False, "error": f"{a.markers} carries no skirt (arp_markers --body skirt)"}, 1
    rmap = json.loads(Path(a.contract).read_text(encoding="utf-8")).get("retarget_map") or {}
    first = lambda n: n[0] if isinstance(n, list) else n
    roles = {r: first(rmap.get(r)) for r in ("Hips", "UpperLeg.L", "UpperLeg.R")}
    if not all(roles.values()):
        return {"ok": False, "error": f"the contract maps no {[r for r, b in roles.items() if not b]}"}, 1
    skip = lambda o: o.get("parts_hair") or o.name.split(".")[0] in ("Hair", "Eye") or o.name.startswith("Eye")
    bound = [(o, m.object) for o in bpy.data.objects if o.type == 'MESH' and not skip(o)
             for m in o.modifiers if m.type == 'ARMATURE' and m.object is not None and m.object.type == 'ARMATURE']
    if not bound:
        return {"ok": False, "error": "no mesh is bound to an armature in this file"}, 1
    mesh, rig = max(bound, key=lambda t: len(t[0].data.vertices))
    deform = [b.name for b in rig.data.bones if b.use_deform]
    missing = [b for b in roles.values() if b not in deform]
    if missing:
        return {"ok": False, "error": f"no deform bones {missing} on {rig.name}"}, 1
    for b in roles.values():
        if mesh.vertex_groups.get(b) is None:
            mesh.vertex_groups.new(name=b)
    groups = [g for g in mesh.vertex_groups if g.name in deform]
    gi = {g.index: k for k, g in enumerate(groups)}
    n = len(mesh.data.vertices)
    V = np.array([tuple(mesh.matrix_world @ v.co) for v in mesh.data.vertices], dtype=float)
    W = np.zeros((n, len(groups)))
    for v in mesh.data.vertices:
        for ge in v.groups:
            if ge.group in gi:
                W[v.index, gi[ge.group]] = ge.weight
    region = arp_markers.skirt_region(V, sk)
    cols = {r: next(k for k, g in enumerate(groups) if g.name == b) for r, b in roles.items()}
    W2 = skirt_weights(V, W, cols, sk, region)
    idx = np.nonzero(region)[0]
    for k, g in enumerate(groups):
        g.remove([int(i) for i in idx])
        keep = idx[W2[idx, k] > 1e-6]
        for i in keep:
            g.add([int(i)], float(W2[i, k]), 'REPLACE')
    log = {"mesh": mesh.name, "armature": rig.name, "bones": roles, "vertices": int(len(idx)),
           "region_share": round(float(len(idx)) / max(n, 1), 4), "leg_max": SKIRT_LEG_MAX,
           "band_z": [round(float(sk["hem_z"]), 4), round(float(sk["top_z"]), 4)]}
    gates = [{"name": "skirt.region", "value": int(len(idx)), "limit": ">= 50", "pass": bool(len(idx) >= 50)}]
    Path(a.fbx).parent.mkdir(parents=True, exist_ok=True)
    x = brt_arp.run({"op": "export", "armature": rig.name, "fbx": a.fbx})
    gates.append({"name": "skirt.export", "value": bool(report_passed(x)), "limit": True, "pass": bool(report_passed(x))})
    log["export_failed_gates"] = [g.get("name") for g in x.get("gates", []) if gate_failed(g)]
    bpy.ops.wm.save_as_mainfile(filepath=a.save)
    ok = all(g["pass"] for g in gates)
    return {"ok": ok, "pass": ok, "gates": gates, **log}, 0 if ok else 2


def mirror_bone(name: str) -> str:
    """The other side's twin of a bone name (.l/.r, .L/.R, _l/_r, _L/_R at the end), else the name itself."""
    for a, b in ((".l", ".r"), (".L", ".R"), ("_l", "_r"), ("_L", "_R")):
        for x, y in ((a, b), (b, a)):
            if name.endswith(x):
                return name[: -len(x)] + y
    return name


def parse_cross(arg: str) -> dict:
    """'L:foot.r,toes_01.r;R:foot.l' -> {"L": ["foot.r", "toes_01.r"], "R": ["foot.l"]} (cross_arg's inverse)."""
    out = {}
    for part in (arg or "").split(";"):
        side, _, bones = part.partition(":")
        if side in ("L", "R") and bones:
            out[side] = [b for b in bones.split(",") if b]
    return out


def _in_cross_side(brt_weights, mesh, rig, rmap, deform, cross, backup, short, band=None) -> dict:
    """Off the midline (past the gate's band, the report's band_m, faded in from half of it), each named bone's
    weight on the other side's skin goes in full to its mirrored twin. brt_weights' reach share takes from the
    twin's side of the mirror plane only, so the bone keeps its own side's skin. Without a band: CROSS_BAND x
    the hip half-width read off this rig."""
    head = lambda role: rig.matrix_world @ rig.data.bones[(lambda n: n[0] if isinstance(n, list) else n)(rmap[role])].head_local
    if not band:
        try:
            band = CROSS_BAND * abs(float(head("UpperLeg.L").x) - float(head("Hips").x))
        except (KeyError, TypeError):
            return {"error": "cross side: no band given and the contract maps no Hips or UpperLeg.L bone in this rig"}
    base = {"mesh": mesh.name, "armature": rig.name, "acknowledge_destructive": True, "backup_path": str(backup),
            "axis": "X", "mask": {"inner": round(0.5 * band, 4), "outer": round(band, 4)}, "feather": round(0.1 * band, 4)}
    out = {"band_m": round(band, 4), "mask": base["mask"], "ops": {}}
    out["ops"]["snapshot"] = short(brt_weights.run({**base, "op": "snapshot", "overwrite": True}))
    if not out["ops"]["snapshot"].get("ok"):
        return {**out, "error": "cross side: snapshot failed"}
    for side, bones in sorted(cross.items()):
        for b in bones:
            twin = mirror_bone(b)
            if twin == b or b not in deform or twin not in deform:
                out["ops"][f"{side}:{b}"] = {"ok": False, "skipped": f"no deform twin for {b}"}
                continue
            r = short(brt_weights.run({**base, "op": "transfer", "from_bones": [b], "to_bones": [twin],
                                       "amount": 1.0, "share": "reach"}))
            out["ops"][f"{side}:{b}"] = {**r, "to": twin}
            if not r.get("ok") and r.get("changed_vertices"):
                return {**out, "error": f"cross side: moving {b} to {twin} failed"}
    return out


# --- selftest -----------------------------------------------------------------------------------------------------
FAKE = r'''
import json, os, sys
argv = sys.argv[1:]
blender = "-P" in argv
script = os.path.basename(argv[argv.index("-P") + 1] if blender else argv[0])
args = argv[argv.index("--") + 1:] if blender and "--" in argv else argv[1:]
if script == "autorig.py":
    script = "inside_" + args[1]
if script == "arp_smart.py" and "--probe" in args:
    script = "arp_smart_probe"
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
elif script in ("assemble_parts.py", "eye_fit.py"):
    touch(opt("--report"), json.dumps(rep))
elif script == "secondary_chains.py":
    n = int(os.environ.get("FAKE_CHAINS", "2"))
    rep.update(chains=[{"name": f"c{i}"} for i in range(n)], detect={"found": {"hood": ["hood"][:n]}})
    touch(opt("--out"), json.dumps({"schema": "secondary/1", "chains": []}))
    if n:
        fbx = opt("--fbx"); touch(fbx); touch(fbx[:-4] + ".skeleton.json", "{}"); touch(opt("--save"))
    touch(opt("--report"), json.dumps(rep))
elif script in ("arp_smart_probe", "arp_smart.py"):
    mode = os.environ.get("FAKE_SMART", "pass")
    if script == "arp_smart_probe":
        ready = mode != "noai"
        rep = {"schema": "gate/1", "ready": ready, "pass": ready, "ok": ready,
               "gates": [{"name": "smart.ai_files", "pass": ready}]}
        code = 0 if ready else 2
    else:
        code = {"pass": 0, "fail": 2, "error": 1}[mode]
        rep = {"schema": "autorig-smart/1", "pass": code == 0, "ok": code == 0, "exit_code": code,
               "gates": [{"name": "smart.fingers", "pass": code == 0}]}
    if mode != "error" or script == "arp_smart_probe":
        touch(opt("--out"), json.dumps(rep))
        print("AUTORIG_JSON " + json.dumps(rep))
    sys.exit(code)
elif script == "deform_gate.py":
    fbx = opt("--fbx")
    att = os.path.basename(os.path.dirname(fbx)) if "repair" in fbx else "sec" if "secondary" in fbx else "a0"
    plan = json.loads(os.environ.get("FAKE_DEFORM", "{}"))
    joint, v, si, *cross = plan.get(att, ["LowerArm.R", 0.2 if att == "sec" else 0.53, 0.04])
    vol = {"name": "deform.volume_loss_max", "value": v, "limit": 0.35, "pass": v <= 0.35}
    sig = {"name": "deform.self_intersection_p95", "value": si, "limit": 0.08, "pass": si <= 0.08}
    gates = [vol, sig] + ([{"name": "deform.cross_side_weight", "value": {"share": 0.01, "held": 9}, "pass": False}]
                          if cross else [])
    ok = all(g["pass"] for g in gates)
    rep = {"schema": "gate/1", "poses": {"p": {"samples": [{"volume_loss": {joint: v}}]}},
           "volume_loss_max": {"value": v, "joint": joint}, "self_intersection": {"p95": si}, "gates": gates,
           "skin": {"cross_side": {"band_m": 0.06, "R": {"bones": {b: 1.0 for b in (cross[0] if cross else [])}}}},
           "pass": ok, "ok": ok}
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
            order = ["prep", "check", "smart_probe", "smart", "markers", "arp", "contract", "deform", "secondary",
                     "secondary_contract", "secondary_deform"]
            check(f"{osname}: all dry run plans eleven steps in stage order, exit 0", code == 0 and list(steps) == order
                  and STAGES == ("prep", "check", "smart", "markers", "arp", "contract", "deform", "secondary"),
                  code=code, err=r.get("error"), steps=list(steps))
            sc = steps["secondary"]
            check(f"{osname}: secondary opens rig/NAME_arp.blend without --factory-startup (the export is Auto-Rig "
                  "Pro's), maps with the contract report, writes into secondary/; its contract and deform read the "
                  "chained export",
                  sc[sc.index("-P") - 1].endswith("Runner_Courier_arp.blend") and "--factory-startup" not in sc
                  and script_of(sc) == "secondary_chains.py" and sc[sc.index("--map") + 1].endswith("Runner_Courier.contract.json")
                  and os.path.basename(os.path.dirname(sc[sc.index("--fbx") + 1])) == "secondary"
                  and "--render" in sc and steps["secondary_contract"][3].endswith(os.path.join("secondary", "Runner_Courier.skeleton.json"))
                  and steps["secondary_deform"][steps["secondary_deform"].index("--map") + 1].endswith(
                      os.path.join("secondary", "Runner_Courier.contract.json"))
                  and "--factory-startup" in steps["secondary_deform"])
            check(f"{osname}: the name is the GLB stem made safe", r.get("name") == "Runner_Courier")
            code_h, rh, _ = go(["all", str(out), str(glb), "--hair", str(glb), "--hair-chains", "--threads", "4",
                                "--dry-run"], osname, {"BLENDER": bl})
            sh_ = {s_["name"]: s_["cmd"] for s_ in rh.get("steps", [])}
            pb = sh_.get("parts_bind", [])
            check(f"{osname}: with --hair, parts_bind sits between contract and deform: assemble_parts.py bind OUT, "
                  "the prepped GLB as --rig-glb, OUT/NAME_hair.glb, a report, no --factory-startup; without it there "
                  "is none; --hair-chains reaches secondary_chains.py",
                  code_h == 0 and list(sh_) == order[:7] + ["parts_bind"] + order[7:] and "parts_bind" not in steps
                  and pb[pb.index("--") + 1] == "bind" and pb[pb.index("--") + 2] == str(out)
                  and "--factory-startup" not in pb and script_of(pb) == "assemble_parts.py"
                  and pb[pb.index("--rig-glb") + 1] == str(Path(out) / "Runner_Courier.glb")
                  and pb[pb.index("--hair") + 1] == str(Path(out) / "Runner_Courier_hair.glb")
                  and pb[pb.index("--report") + 1].endswith(os.path.join("rig", "Runner_Courier.bind.json"))
                  and "--hair-chains" in sh_["secondary"] and "--hair-chains" not in steps["secondary"],
                  steps=list(sh_))
            code_e, re_, _ = go(["all", str(out), str(glb), "--hair", str(glb), "--eyes", str(glb), "--facial",
                                 "--threads", "4", "--dry-run"], osname, {"BLENDER": bl})
            se_ = {s_["name"]: s_["cmd"] for s_ in re_.get("steps", [])}
            eb, sm_e = se_.get("eyes_bind", []), se_.get("smart", [])
            _, rn, _ = go(["all", str(out), str(glb), "--eyes", str(glb), "--dry-run"], osname, {"BLENDER": bl})
            sn = {s_["name"]: s_["cmd"] for s_ in rn.get("steps", [])}
            check(f"{osname}: with --eyes, eyes_bind follows parts_bind before deform: eye_fit.py bind OUT, "
                  "OUT/NAME_eyes.glb, the prepped GLB, a report, no --factory-startup; with --facial the smart "
                  "window gets --eyes objects and both GLBs; without --facial it gets none",
                  code_e == 0 and list(se_) == order[:7] + ["parts_bind", "eyes_bind"] + order[7:]
                  and script_of(eb) == "eye_fit.py" and eb[eb.index("--") + 1] == "bind"
                  and eb[eb.index("--") + 2] == str(out) and "--factory-startup" not in eb
                  and eb[eb.index("--eyes") + 1] == str(Path(out) / "Runner_Courier_eyes.glb")
                  and eb[eb.index("--rig-glb") + 1] == str(Path(out) / "Runner_Courier.glb")
                  and eb[eb.index("--report") + 1].endswith(os.path.join("rig", "Runner_Courier.eyes_bind.json"))
                  and sm_e[sm_e.index("--eyes") + 1] == "objects"
                  and sm_e[sm_e.index("--eye-glb") + 1] == str(Path(out) / "Runner_Courier_eyes.glb")
                  and sm_e[sm_e.index("--eye-frame-glb") + 1] == str(Path(out) / "Runner_Courier.glb")
                  and "eyes_bind" in sn and "--eyes" not in sn["smart"] and "eyes_bind" not in steps,
                  steps=list(se_))
            bls = [steps[k] for k in ("prep", "smart_probe", "markers", "arp", "deform")] + \
                [s["cmd"] for s in r["repair_example"]]
            sm = steps["smart"]
            check(f"{osname}: every Blender step is [$BLENDER, -b, ...] with -t 4, no shell, no inline Python; "
                  "smart alone has a window (no -b)",
                  all(c_[:2] == [bl, "-b"] and c_[c_.index("-t") + 1] == "4" for c_ in bls)
                  and sm[0] == bl and "-b" not in sm and sm[sm.index("-t") + 1] == "4"
                  and sm[sm.index("--python-exit-code") + 1] == "1" and "--python-exit-code" not in steps["markers"]
                  and not any("--python-expr" in c_ for c_ in bls + [sm]))
            fac = {k: "--factory-startup" in steps[k] for k in ("prep", "smart_probe", "smart", "markers", "arp",
                                                                "deform")}
            fac.update({s["name"]: "--factory-startup" in s["cmd"] for s in r["repair_example"]})
            check(f"{osname}: --factory-startup on prep, markers, deform; not on smart, its probe, arp or repair "
                  "(the add-on)",
                  fac == {"prep": True, "smart_probe": False, "smart": False, "markers": True, "arp": False,
                          "deform": True, "repair_a1": False, "deform_a1": True}, fac=fac)
            o = str(out)
            check(f"{osname}: smart opens NAME.blend, writes rig/NAME.smart.json, no face, 5 fingers; the markers "
                  "get --smart; the probe opens no file",
                  sm[sm.index("-P") - 1] == str(Path(o) / "Runner_Courier.blend") and "--no-facial" in sm
                  and sm[sm.index("--fingers") + 1] == "5" and sm[sm.index("--out") + 1].endswith("Runner_Courier.smart.json")
                  and steps["markers"][steps["markers"].index("--smart") + 1] == sm[sm.index("--out") + 1]
                  and "--probe" in steps["smart_probe"] and steps["smart_probe"][steps["smart_probe"].index("-P") - 1] == "4")
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
                  and "--render" not in s2["secondary"] and "--render" not in s2["secondary_deform"]
                  and "--render" not in r2["repair_example"][1]["cmd"] and "-t" not in s2["prep"])
            code, r3, _ = go(["all", str(out), str(glb), "--no-smart", "--facial", "--fingers", "4", "--dry-run"],
                             osname, {"BLENDER": bl})
            s3 = {s["name"]: s["cmd"] for s in r3.get("steps", [])}
            check(f"{osname}: --no-smart plans no smart step and no --smart", code == 0 and "smart" not in s3
                  and "smart_probe" not in s3 and "--smart" not in s3["markers"], steps=list(s3))
            code, r5, _ = go(["all", str(out), str(glb), "--no-secondary", "--dry-run"], osname, {"BLENDER": bl})
            code6, r6, _ = go(["all", str(out), str(glb), "--secondary-markers", "m.json", "--dry-run"], osname,
                              {"BLENDER": bl})
            s6 = {s["name"]: s["cmd"] for s in r6.get("steps", [])}["secondary"]
            check(f"{osname}: --no-secondary plans no secondary step; --secondary-markers passes --markers down",
                  code == 0 and not any(s["name"].startswith("secondary") for s in r5["steps"])
                  and s6[s6.index("--markers") + 1] == os.path.abspath("m.json"))
            _, rs, _ = go(["all", str(out), str(glb), "--body", "skirt", "--dry-run"], osname, {"BLENDER": bl})
            ss = {s_["name"]: s_["cmd"] for s_ in rs.get("steps", [])}
            mk = str(out / "rig" / "Runner_Courier.markers.json")
            sb = ss.get("skirt_bind", [])
            check(f"{osname}: --body skirt reaches mesh_check and the markers; skirt_bind (this file inside Blender, "
                  "the arp blend, no --factory-startup) sits between contract and deform; deform and the chains get "
                  "--skirt MARKERS",
                  list(ss) == order[:7] + ["skirt_bind"] + order[7:] and "--body" in ss["check"]
                  and ss["markers"][ss["markers"].index("--body") + 1] == "skirt" and sb[sb.index("--") + 1:sb.index("--") + 3]
                  == ["_inside", "skirt"] and "--factory-startup" not in sb and sb[sb.index("-P") - 1].endswith("_arp.blend")
                  and all(c_[c_.index("--skirt") + 1] == mk for c_ in (ss["deform"], ss["secondary"], ss["secondary_deform"]))
                  and "--skirt" not in steps["deform"] and "--body" not in steps["check"], steps=list(ss))
            _, r7, _ = go(["all", str(out), str(glb), "--adjust", "adj.json", "--resolution", "8", "--dry-run"], osname,
                          {"BLENDER": bl})
            s7 = {s["name"]: s["cmd"] for s in r7.get("steps", [])}
            check(f"{osname}: --adjust goes to arp_markers, --resolution to the arp step; neither without the flag",
                  s7["markers"][s7["markers"].index("--adjust") + 1] == os.path.abspath("adj.json")
                  and s7["arp"][s7["arp"].index("--resolution") + 1] == "8"
                  and "--adjust" not in s3["markers"] and "--resolution" not in s3["arp"], s7=s7)
            _, r4, _ = go(["smart", str(out), "--name", "R", "--facial", "--fingers", "4", "--dry-run"], osname, {"BLENDER": bl})
            s4 = r4["steps"][-1]["cmd"]
            check(f"{osname}: smart alone passes --facial and --fingers 4 down",
                  "--facial" in s4 and s4[s4.index("--fingers") + 1] == "4" and "--no-facial" not in s4)
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
        # skirt_bind's weights on a skirt cylinder: Hips and both thighs, smooth across the midline, the bind kept at the top
        import numpy as np
        ang = np.linspace(-np.pi, np.pi, 72, endpoint=False)
        zs = np.linspace(0.55, 0.97, 22)
        V = np.array([[0.2 * np.sin(t), -0.14 * np.cos(t), z] for z in zs for t in ang])
        rng = np.random.default_rng(1)
        W0 = rng.random((len(V), 6)) * (rng.random((len(V), 6)) > 0.5)
        W0[:, 4:] = 0.0
        W0[:, 3] += 0.01
        sk = {"top_z": 0.97, "hem_z": 0.56, "height": 1.78, "midline_x": 0.0, "half_width": 0.12}
        W1 = skirt_weights(V, W0, {"Hips": 0, "UpperLeg.L": 1, "UpperLeg.R": 2}, sk, np.ones(len(V), bool))
        hem = np.isclose(V[:, 2], zs[0])
        front = hem & np.isclose(V[:, 0], 0.0, atol=1e-9) & (V[:, 1] < 0)
        lam = W1[hem, 1] / np.maximum(W1[hem, 1] + W1[hem, 2], 1e-9)
        top = np.isclose(V[:, 2], zs[-1])
        check("skirt_bind weights: rows sum to 1 with at most 4 weights; at the hem Hips holds 1 - SKIRT_LEG_MAX and the "
              "front centre is half each thigh; the left share changes by under 0.1 between neighbours round the hem; "
              "the band's top keeps the bind", np.allclose(W1.sum(1), 1) and ((W1 > 0).sum(1) <= 4).all()
              and np.allclose(W1[hem, 0], 1 - SKIRT_LEG_MAX, atol=0.02) and abs(W1[front, 1][0] - W1[front, 2][0]) < 1e-6
              and np.abs(np.diff(lam)).max() < 0.1
              and np.allclose(W1[top], W0[top] / W0[top].sum(1, keepdims=True)))
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
              next_rung(elbow, []) == {"hinges": ["elbow"], "amount": 1.0, "cross_side": {}, "cross_band": None,
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
                  "hinges": ["elbow", "knee"], "amount": 1.0, "cross_side": {}, "cross_band": None,
                  "why": "now also volume loss at LowerLeg.R"})
        r09 = next_rung(elbow, [{**a1, "report": rep({"LowerArm.R": 0.30}, si=0.09)}])
        check("volume held, self-intersection rose: amount 0.9, then stop",
              r09 and r09["amount"] == 0.9 and next_rung(elbow, [{**a1, "report": {}}, {**r09, "report": rep(
                  {"LowerArm.R": 0.30}, si=0.09)}]) is None)
        check("never more than MAX_ATTEMPTS", next_rung(elbow, [{**a1, "report": rep({"LowerLeg.R": 0.4})}] * MAX_ATTEMPTS) is None)
        def crossed(r, bones=("foot.l", "toes_01.l"), share=0.0144, held=336):
            return {**r, "skin": {"cross_side": {"band_m": 0.062, "L": {"share": 0.0, "held": 0, "bones": {}},
                                                 "R": {"share": share, "held": held, "bones": {b: 1.0 for b in bones}}}},
                    "gates": r["gates"] + [{"name": CROSS, "value": {"share": share, "held": held}, "pass": False}]}
        sole = crossed(rep({"LowerArm.L": 0.2}))
        c1 = next_rung(sole, [])
        check("a sole bound to the other foot alone: move it to the twins, no hinge",
              c1 == {"hinges": [], "amount": 1.0, "cross_side": {"L": [], "R": ["foot.l", "toes_01.l"]}, "cross_band": 0.062,
                     "why": "weight across the midline on foot.l, toes_01.l"}, c1=c1)
        both = next_rung(crossed(rep({"LowerArm.L": 0.48})), [])
        check("cross-side and an elbow: both in one attempt", both["hinges"] == ["elbow"] and both["cross_side"]["R"])
        unnamed = crossed(rep({"LowerArm.L": 0.2}), bones=())
        check("a cross-side failure that names no bones (an older gate): no repair", next_rung(unnamed, []) is None)
        check("cross-side with self-intersection failing too: no repair",
              next_rung(crossed(rep({"LowerArm.L": 0.2}, si=0.1)), []) is None)
        check("the move across the midline did not hold: stop (rebind)",
              next_rung(sole, [{**c1, "report": crossed(rep({"LowerArm.L": 0.2}))}]) is None)
        c2 = next_rung(sole, [{**c1, "report": rep({"LowerArm.L": 0.4})}])
        check("cross-side held, an elbow now fails: add the elbow, keep the cross-side move",
              c2 and c2["hinges"] == ["elbow"] and c2["cross_side"] == c1["cross_side"], c2=c2)
        check("cross-side held, self-intersection alone fails without a hinge: stop (no amount to soften)",
              next_rung(sole, [{**c1, "report": rep({"LowerArm.L": 0.2}, si=0.09)}]) is None)
        check("bone twins and the --cross-side argument round trip, the gate's band passed along",
              mirror_bone("foot.l") == "foot.r" and mirror_bone("Toes.R") == "Toes.L" and mirror_bone("hand_l") == "hand_r"
              and mirror_bone("root.x") == "root.x" and parse_cross(cross_arg(c1["cross_side"])[1]) == {"R": ["foot.l", "toes_01.l"]}
              and cross_arg({}) == [] and cross_arg({"L": [], "R": []}, 0.06) == [] and c1["cross_band"] == 0.062
              and cross_arg(c1["cross_side"], 0.062)[2:] == ["--cross-band", 0.062])
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
            OVERRIDE.update(blender=fake, python=fake)
            try:
                code, r, err = go(argv, None, env)
            finally:
                OVERRIDE.clear()
            ran = [json.loads(x)["script"] for x in trace.read_text().splitlines() if x.strip()]
            return code, r, err, ran

        clean0 = {"a0": ["LowerArm.R", 0.2, 0.04]}
        chain = ["inside_prep", "mesh_check.py", "arp_smart_probe", "arp_smart.py", "arp_markers.py", "inside_arp",
                 "contract_map.py", "deform_gate.py"]
        SEC = ["secondary_chains.py", "contract_map.py", "deform_gate.py"]
        run_dir = td / "run"
        trace_argv_all = lambda name: next((json.loads(x)["argv"] for x in trace.read_text().splitlines()
                                            if x.strip() and json.loads(x)["script"] == name), [])
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner"],
                                 FAKE_DEFORM={"a1": ["LowerArm.R", 0.3492, 0.05]})
        rs = {s_["name"]: s_ for s_ in r.get("steps", [])}
        att = (r.get("repair") or {}).get("attempts") or []
        check("all: the elbow fails, attempt 1 repairs and passes, the chains go on the repaired rig, exit 0",
              code == 0 and ran == chain + ["inside_repair", "deform_gate.py"] + SEC and r.get("repair", {}).get("result")
              == "passed" and len(att) == 1, code=code, ran=ran, err=r.get("error"))
        sa = trace_argv_all("secondary_chains.py")
        check("all: secondary opens repair/a1/NAME_arp.blend; the result points at secondary/ and its secondary/1; "
              "the summary puts both volume readings side by side",
              sa and sa[sa.index("-P") - 1].endswith(os.path.join("repair", "a1", "Runner_arp.blend"))
              and r["result"]["fbx"].endswith(os.path.join("secondary", "Runner.fbx"))
              and r["result"]["secondary"].endswith("Runner.secondary.json")
              and r["secondary"]["chains"] == 2 and r["secondary"]["volume_loss_max"] == {
                  "without_chains": 0.3492, "with_chains": 0.2}, sec=r.get("secondary"), res=r.get("result"))
        check("all: every step timed, the deform step names its failed gate, the summary written, children's noise "
              "kept in the logs",
              all(isinstance(s_["seconds"], float) for s_ in rs.values())
              and rs["deform"]["failed_gates"] == ["deform.volume_loss_max"]
              and (run_dir / "autorig.all.json").exists() and "\u4e2d" not in err)
        check("all: the attempt lists hinges, amount, bands, the gate values; the result points at repair/a1",
              att and att[0]["hinges"] == ["elbow"] and att[0]["amount"] == 1.0
              and att[0]["regions"]["elbow"]["below"] == [0.98, 1.01, 1.08, 1.095]
              and att[0]["volume_loss_max"]["value"] == 0.3492 and att[0]["self_intersection_p95"] == 0.05
              and r["repair"]["files"]["fbx"].endswith(os.path.join("repair", "a1", "Runner.fbx")), att=att)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--no-secondary"],
                                 FAKE_DEFORM={"a0": ["LowerArm.R", 0.2, 0.04, ["foot.l", "toes_01.l"]],
                                              "a1": ["LowerArm.R", 0.2, 0.04]})
        rx = trace_argv_all("inside_repair")
        att = (r.get("repair") or {}).get("attempts") or []
        check("all: a sole on the other foot's bones alone, attempt 1 moves them to the twins (no hinge) and passes",
              code == 0 and ran == chain + ["inside_repair", "deform_gate.py"] and rx
              and rx[rx.index("--cross-side") + 1] == "R:foot.l,toes_01.l" and rx[rx.index("--hinges") + 1] == ""
              and rx[rx.index("--cross-band") + 1] == "0.06"
              and att and att[0]["cross_side"] == {"L": [], "R": ["foot.l", "toes_01.l"]}
              and att[0]["regions"]["cross_side"]["band_m"] == 0.06, code=code, ran=ran, rx=rx, att=att)
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
        hair = td / "src" / "runner_hair.glb"
        hair.write_text("h")
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--no-smart", "--hair", str(hair)],
                                 FAKE_DEFORM=clean0)
        base = [x for x in chain if not x.startswith("arp_smart")]
        check("all --hair: the hair copied to OUT/NAME_hair.glb, parts_bind after the contract and before the first "
              "deform gate, then the chains; exit 0",
              code == 0 and ran == base[:-1] + ["assemble_parts.py", "deform_gate.py"] + SEC
              and (run_dir / "Runner_hair.glb").read_text() == "h"
              and [s_["name"] for s_ in r["steps"]][4:7] == ["contract", "parts_bind", "deform"], ran=ran, code=code)
        code, r, err, ran = real(["contract", str(run_dir), "--name", "Runner"])
        check("contract on its own binds again while OUT/NAME_hair.glb is there", ran == ["contract_map.py",
                                                                                         "assemble_parts.py"], ran=ran)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--no-smart", "--hair", str(hair)],
                                 {"assemble_parts.py": 2}, FAKE_DEFORM=clean0)
        check("a bind that fails a gate stops before deform (the FBX has no hair), exit 2",
              code == 2 and ran == base[:-1] + ["assemble_parts.py"] and "secondary" not in r, ran=ran, code=code)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--no-smart"], FAKE_DEFORM=clean0)
        check("all without --hair removes an earlier hair copy: no parts_bind, exit 0",
              code == 0 and "assemble_parts.py" not in ran and not (run_dir / "Runner_hair.glb").exists(), ran=ran)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--hair", str(td / "no.glb")])
        check("--hair naming no file is refused before anything runs, exit 1", code == 1 and ran == [], ran=ran)
        eyes = td / "src" / "runner_eyes.glb"
        eyes.write_text("e")
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--no-smart", "--hair", str(hair),
                                  "--eyes", str(eyes)], FAKE_DEFORM=clean0)
        check("all --eyes: the eyes copied to OUT/NAME_eyes.glb, eyes_bind after parts_bind, before deform; exit 0",
              code == 0 and ran == base[:-1] + ["assemble_parts.py", "eye_fit.py", "deform_gate.py"] + SEC
              and (run_dir / "Runner_eyes.glb").read_text() == "e"
              and [s_["name"] for s_ in r["steps"]][4:8] == ["contract", "parts_bind", "eyes_bind", "deform"],
              ran=ran, code=code)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--no-smart", "--eyes", str(eyes)],
                                 {"eye_fit.py": 2}, FAKE_DEFORM=clean0)
        check("an eyes bind that fails a gate stops before deform, exit 2",
              code == 2 and ran == base[:-1] + ["eye_fit.py"] and "secondary" not in r, ran=ran, code=code)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--no-smart"], FAKE_DEFORM=clean0)
        check("all without --eyes removes an earlier eyes copy: no eyes_bind",
              code == 0 and "eye_fit.py" not in ran and not (run_dir / "Runner_eyes.glb").exists(), ran=ran)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--eyes", str(td / "no.glb")])
        check("--eyes naming no file is refused before anything runs, exit 1", code == 1 and ran == [], ran=ran)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner"], {"mesh_check.py": 2})
        check("all: a mesh check failure stops before the rig, exit 2", code == 2 and ran == chain[:2])
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner"], {"inside_arp": 1})
        check("all: an Auto-Rig Pro error stops, exit 1", code == 1 and ran == chain[:6])
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner"], {"contract_map.py": 2})
        check("all: a contract gate failure still gates the deformation, exit 2", code == 2 and ran[:8] == chain)
        # the smart stage: passed, failed, an error, no AI, turned off
        clean = {"a0": ["LowerArm.R", 0.2, 0.04]}
        trace_argv = lambda name: next((json.loads(x)["argv"] for x in trace.read_text().splitlines()
                                        if x.strip() and json.loads(x)["script"] == name), [])
        smart_json = str(run_dir / "rig" / "Runner.smart.json")
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--facial", "--fingers", "4"],
                                 FAKE_DEFORM=clean, FAKE_SMART="pass")
        sa, ma, pa = trace_argv("arp_smart.py"), trace_argv("arp_markers.py"), trace_argv("arp_smart_probe")
        check("smart passed: the probe headless, the AI in a window without --factory-startup, the markers get "
              "--smart rig/NAME.smart.json, exit 0",
              code == 0 and ran == chain + SEC and "-b" in pa and "-b" not in sa and "--factory-startup" not in sa
              and "--facial" in sa and sa[sa.index("--fingers") + 1] == "4"
              and ma[ma.index("--smart") + 1] == smart_json and r["smart"]["result"] == "passed"
              and r["smart"]["markers_used_it"], code=code, ran=ran, smart=r.get("smart"))
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner"], FAKE_DEFORM=clean,
                                 FAKE_SMART="fail")
        ma = trace_argv("arp_markers.py")
        check("smart failed a gate: all goes on to the end, the markers still get its report (they take what "
              "passed), the summary names the failed gate, exit 2",
              code == 2 and ran == chain + SEC and ma[ma.index("--smart") + 1] == smart_json
              and r["smart"]["result"] == "failed" and r["smart"]["why"] == ["smart.fingers"]
              and r["smart"]["note"].startswith("the markers took what passed"), code=code, ran=ran, smart=r.get("smart"))
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner"], FAKE_DEFORM=clean,
                                 FAKE_SMART="error")
        check("smart wrote no report (an error): all goes on to the end, the markers without --smart, exit 2",
              code == 2 and ran == chain + SEC and "--smart" not in trace_argv("arp_markers.py")
              and r["smart"]["result"] == "failed" and r["smart"]["note"].startswith("the markers came from slices"),
              code=code, ran=ran, smart=r.get("smart"))
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner"], FAKE_DEFORM=clean,
                                 FAKE_SMART="noai")
        check("no add-on or AI files: the probe says so, no window opens, the markers without --smart, exit 0",
              code == 0 and ran == [x for x in chain if x != "arp_smart.py"] + SEC
              and "--smart" not in trace_argv("arp_markers.py")
              and r["smart"]["result"] == "skipped", code=code, ran=ran)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--no-smart"], FAKE_DEFORM=clean)
        check("--no-smart: neither the probe nor the window, exit 0",
              code == 0 and ran == [x for x in chain if not x.startswith("arp_smart")] + SEC, ran=ran)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--no-smart", "--no-secondary"],
                                 FAKE_DEFORM=clean)
        check("--no-secondary: no chains, the result is the rig's own export, exit 0",
              code == 0 and ran == [x for x in chain if not x.startswith("arp_smart")] and "secondary" not in r
              and r["result"]["fbx"].endswith(os.path.join("export", "Runner.fbx")), ran=ran)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--no-smart"], FAKE_DEFORM=clean,
                                 FAKE_CHAINS="0")
        check("nothing loose: an empty secondary/1, no re-check, the rig's own export is the result, exit 0",
              code == 0 and ran == [x for x in chain if not x.startswith("arp_smart")] + SEC[:1]
              and r["secondary"]["chains"] == 0 and "volume_loss_max" not in r["secondary"]
              and r["result"]["fbx"].endswith(os.path.join("export", "Runner.fbx"))
              and r["result"]["secondary"].endswith("Runner.secondary.json"), ran=ran, sec=r.get("secondary"))
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--no-smart"],
                                 FAKE_DEFORM={"a1": ["LowerArm.R", 0.41, 0.05]})
        check("a deform stage that failed (repair exhausted) skips the chains, exit 2",
              code == 2 and "secondary_chains.py" not in ran and "secondary" not in r, ran=ran)
        code, r, err, ran = real(["all", str(run_dir), str(glb), "--name", "Runner", "--no-smart"],
                                 FAKE_DEFORM={"a1": ["LowerArm.R", 0.3492, 0.05]})
        code, r, err, ran = real(["secondary", str(run_dir), "--name", "Runner"])
        sa = trace_argv_all("secondary_chains.py")
        check("secondary on its own takes the repaired rig the newest summary names, exit 0",
              code == 0 and ran == SEC and sa[sa.index("-P") - 1].endswith(os.path.join("repair", "a1", "Runner_arp.blend")),
              ran=ran)
        code, r, err, ran = real(["smart", str(run_dir), "--name", "Runner"], FAKE_SMART="noai")
        check("smart on its own without the AI: refused, exit 1, the probe's failed gate named",
              code == 1 and ran == ["arp_smart_probe"] and r["smart"]["why"] == ["smart.ai_files"], smart=r.get("smart"))
        code, r, err, ran = real(["smart", str(run_dir), "--name", "Runner"], FAKE_SMART="fail")
        check("smart on its own, a gate failed: exit 2", code == 2 and ran == ["arp_smart_probe", "arp_smart.py"])
        code, r, err, ran = real(["smart", str(run_dir), "--name", "Runner"], FAKE_SMART="pass")
        code, r, err, ran = real(["markers", str(run_dir), "--name", "Runner"])
        check("markers on its own takes an earlier smart.json",
              smart_json in trace_argv("arp_markers.py"))
        code, r, err, ran = real(["markers", str(run_dir), "--name", "Runner", "--no-smart"])
        check("markers --no-smart leaves it out", "--smart" not in trace_argv("arp_markers.py"))
        # fingers the AI placed count as found; jaw_open only when deform_gate knows it
        ai = td / "ai"
        (ai / "rig").mkdir(parents=True)
        (ai / "export").mkdir()
        (ai / "Runner.glb").write_text("x")
        for p_ in ("export/Runner.fbx", "export/Runner.skeleton.json"):
            (ai / p_).write_text("{}")
        (ai / "rig" / "Runner.markers.json").write_text(json.dumps({"fingers": {"mode": "ai"}, "facial": True}))
        (ai / "rig" / "Runner.contract.json").write_text(json.dumps({"retarget_map": {"Jaw": "jaw.x"}}))
        _, rc_, _ = go(["contract", str(ai), "--dry-run"], None, {"BLENDER": "B"})
        _, rd_, _ = go(["deform", str(ai), "--dry-run"], None, {"BLENDER": "B"})
        cc, dc = rc_["steps"][0]["cmd"], rd_["steps"][0]["cmd"]
        known = deform_pose_names()
        check("fingers.mode ai with a face and a mapped Jaw: contract with --min-fingers 30, deform "
              "--poses all,jaw_open (deform_gate's NAMED_ONLY read from its source)",
              "--min-fingers" in cc and "jaw_open" in known and dc[dc.index("--poses") + 1] == "all,jaw_open",
              known=known, dc=dc)
        (ai / "rig" / "Runner.contract.json").write_text(json.dumps({"retarget_map": {"Head": "head.x"}}))
        _, rd_, _ = go(["deform", str(ai), "--dry-run"], None, {"BLENDER": "B"})
        check("a face but no Jaw in the contract: no jaw_open", "--poses" not in rd_["steps"][0]["cmd"])
        check("deform poses: all by default; a mitten drops fist; a face adds jaw_open only when known",
              deform_poses(DEFORM_POSES, False, False) is None and deform_poses(DEFORM_POSES, True, False) == NO_FIST
              and deform_poses(DEFORM_POSES, False, True) is None
              and deform_poses(DEFORM_POSES + ("jaw_open",), True, True) == NO_FIST + ",jaw_open"
              and deform_poses(DEFORM_POSES + ("jaw_open",), False, True) == "all,jaw_open"
              and deform_poses(DEFORM_POSES + ("jaw_open",), False, False) is None
              and set(DEFORM_POSES) <= set(known))
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
