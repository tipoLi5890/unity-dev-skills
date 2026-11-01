#!/usr/bin/env python3
"""arp_smart.py — Auto-Rig Pro's own AI markers (body, fingers, face) and Go!, driven from a script.

The AI takes its pictures from the 3D view, so this runs in a Blender WITH a window (no -b, and no
--factory-startup, which turns the add-on off). A timer on that window calls the add-on's operators
by name, inside a temp_override of its largest 3D view; the result is written and Blender quits by
itself, also on an error or a timeout. Nothing of the add-on is copied: an operator name that is not
registered refuses the run, and no other name is tried.

usage (windowed Blender, the normalised file: +Z up, facing -Y, soles on Z 0, scale applied):
    blender Runner.blend -P arp_smart.py -- --mesh Runner --out rig/Runner.smart.json \
        [--save-blend rig/Runner_smart.blend] [--fingers 5|4] [--facial|--no-facial]
        [--eyes proxy|none|auto|objects] [--eye-glb E.glb --eye-frame-glb RAW.glb] [--body-samples N] [--finger-samples N] [--timeout 600]
    blender -b -P arp_smart.py -- --probe [--out probe.json]   (headless: add-on, operators, AI files)
    python3 arp_smart.py --selftest                              (host, no Blender, no add-on)

The chain, one step per timer tick:
  setup        preferences are not saved on quit (first, before anything changes), smooth view off,
               the scene's root collection active (the add-on links its cameras to it), the view in
               Material shading (the face pictures need the paint), every operator registered, the
               AI files' info.dat version >= 1.20, the mesh present, no Auto-Rig Pro rig in the file.
  select       id.get_selected_objects (EXEC; INVOKE opens a dialog) -> the add-on's working body.
  body         arp.guess_markers -> root neck chin head_tip and shoulder elbow hand hand_tip thigh knee
               foot (_loc = .L on +X, _loc_sym = .R). It runs --body-runs times (3): the guess moves by
               millimetres from run to run (the hand marker is the wrist Go! builds on), so per marker
               the guess nearest the markers' median is put back (body_runs: runs, spread in metres; a
               later guess that fails keeps the good ones: failed_after, error).
  fingers      arp.guess_fingers with --fingers; 5 that fails is tried again with 4 (the add-on's
               four-finger hand is thumb, middle, ring, pinky: no index). A failure is a popup that
               raises nothing: judged by thumb1_loc. Both failing turns fingers off for Go!. The guess
               varies from run to run, so it runs --finger-runs times (5) and per finger the run nearest
               that finger's per-marker median is put back on the markers Go! reads (each finger stays
               one guess); fingers.runs reports the runs, the run kept per finger and the spread (metres).
               A later guess that fails and takes the markers is followed by one more (restore), else
               that count fails.
  face         (--facial) id.facial_setup, arp.guess_facial, then --eyes: proxy puts a sphere behind
               each eye from the lid markers (manual eyeball mode), none turns eyes off, auto lets the
               add-on look for eyeball objects, objects imports real eyeballs (--eye-glb, blender-character-rig
               eye_fit.py's Eye.L / Eye.R, in the frame of --eye-frame-glb, the GLB the open file was prepped
               from: scale from the z extents, shift from the minima) as the manual eyeballs, removed after
               Go! like the proxies; id.validate_facial_setup. A face that fails is
               cancelled (id.cancel_facial_setup, eyes off, proxies removed) so Go! still builds the
               body and the fingers.
  go           a copy with the markers is saved (<save-blend stem>_markers.blend), then id.go_detect
               (INVOKE: its checks and the face projection live there). Every *_ref edit bone is read
               (head and tail through the rig's matrix_world: Go! scales the rig), the proxies are
               removed, and the rig is saved to --save-blend.
Errors come two ways: a reported error raises (in the interface language: never matched), a popup
raises nothing. Every step is judged by the scene it leaves.

Output (schema "autorig-smart/1"; world space, metres, +Z up, facing -Y, .L on +X, the frame of
autorig-markers/1): mesh, height, arp {version, ai_version}, options, steps [{step, seconds, error,
ok, ...}], body_markers {root, neck, chin, head_tip, shoulder.L ... foot.R}, fingers {requested,
count, fell_back, names, markers {thumb1.L ... pinky4.R}}, facial {enabled, ok, features,
keypoints_found, keypoints_total, eye_proxies, eye_objects}, rig_matrix_world, refs {bone: {head, tail, roll,
group body|finger|facial|ear, parent}}, ref_rolls_from, warnings, blend, blend_markers, elapsed_s,
and gate/1's gates, pass, verdict (ok, pass's old name).
Gates: smart.ai_files (version >= 1.20 and keypoint files written), smart.body_markers (all 18),
smart.fingers (thumb1_loc), smart.facial (only with --facial: the face chain ran, its markers moved,
the add-on kept the mouth and, unless --eyes none, the eyes), smart.go (the has_match_to_rig key on
the rig's data; its value is False on success), smart.refs (every body reference bone, the thumb
when fingers were found, the jaw when the face passed).
The environment variable ARP_AI_DIR points this run (probe and window) at another AI folder; the
add-on's preference is set in memory only (preferences are not saved), e.g. an empty folder to try
the fallback.
In Blender the report is written to --out and printed as one line `AUTORIG_JSON {...}`.
Exit codes: 0 every gate passed; 2 a gate failed (the AI ran); 1 refused or an error (add-on, an
operator or the AI files missing, no window, a timeout, a usage error).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time

SCHEMA = "autorig-smart/1"
TAG = "AUTORIG_JSON "
MIN_AI_VERSION = 1.20
AI_DIR_ENV = "ARP_AI_DIR"       # another AI folder for this run only (preferences are never saved)
TIMEOUT = 600.0
HARD_EXTRA = 60.0               # the watchdog's margin past --timeout; it cannot touch bpy
OPERATORS = ("id.get_selected_objects", "arp.guess_markers", "arp.guess_fingers", "id.facial_setup",
             "arp.guess_facial", "id.validate_facial_setup", "id.cancel_facial_setup", "id.go_detect")
CENTRE = ("root", "neck", "chin", "head_tip")
SIDED = ("shoulder", "elbow", "hand", "hand_tip", "thigh", "knee", "foot")
FINGERS = ("thumb", "index", "middle", "ring", "pinky")
BODY_REFS = ("root_ref.x", "spine_01_ref.x", "neck_ref.x", "head_ref.x") + tuple(
    f"{b}_ref.{s}" for s in ("l", "r") for b in ("shoulder", "arm", "forearm", "hand", "thigh", "leg", "foot", "toes"))
BODY_PFX = ("root", "spine", "neck", "head", "shoulder", "arm", "forearm", "hand", "thigh", "leg",
            "foot", "toes", "bot_bend", "breast", "tail")
PROXY = "arp_smart_eyeball"
BROW_AHEAD = 0.020              # a brow more than this (x H / 1.75) in front of the eyelids: a fringe


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser() -> UsageParser:
    p = UsageParser(prog="arp_smart.py", description=__doc__.split("\n")[0],
                    epilog="Exit codes: 0 pass, 2 a gate failed, 1 refused or an error.")
    p.add_argument("--mesh", help="the mesh object in the open file (default: the largest mesh)")
    p.add_argument("--out", help="write the report here")
    p.add_argument("--save-blend", help="save the rig here, and the markers beside it (_markers.blend)")
    p.add_argument("--fingers", type=int, choices=(5, 4), default=5)
    p.add_argument("--facial", dest="facial", action="store_true", default=True)
    p.add_argument("--no-facial", dest="facial", action="store_false")
    p.add_argument("--eyes", choices=("proxy", "none", "auto", "objects"), default="proxy")
    p.add_argument("--eye-glb", help="--eyes objects: the eyeballs (eye_fit.py fit's <c>_eyes.glb)")
    p.add_argument("--eye-frame-glb", help="--eyes objects: the GLB the open file was prepped from (its frame)")
    p.add_argument("--body-samples", type=int, default=0, help="front pictures per body guess (0: the add-on's)")
    p.add_argument("--finger-samples", type=int, default=0, help="per finger guess (0: the add-on's)")
    p.add_argument("--body-runs", type=int, default=3, help="body guesses; per marker the one nearest their median")
    p.add_argument("--finger-runs", type=int, default=5, help="finger guesses; per finger the one nearest their median")
    p.add_argument("--timeout", type=float, default=TIMEOUT, help="seconds for the whole chain")
    p.add_argument("--probe", action="store_true", help="report add-on, operators and AI files; no AI run")
    p.add_argument("--selftest", action="store_true")
    return p


def eye_args_error(a) -> str | None:
    """--eyes objects needs both GLBs, and they must exist; the GLBs mean nothing without it."""
    if a.eyes == "objects":
        missing = [f for f, v in (("--eye-glb", a.eye_glb), ("--eye-frame-glb", a.eye_frame_glb)) if not v]
        if missing:
            return f"--eyes objects needs {' and '.join(missing)}"
        gone = [v for v in (a.eye_glb, a.eye_frame_glb) if not os.path.isfile(v)]
        return f"missing {gone[0]}" if gone else None
    if a.eye_glb or a.eye_frame_glb:
        return "--eye-glb and --eye-frame-glb go with --eyes objects"
    return None


def options(a) -> dict:
    return {"fingers": a.fingers, "facial": a.facial, "eyes": a.eyes if a.facial else None,
            "shading": "MATERIAL", "body_samples": a.body_samples or None,
            "finger_samples": a.finger_samples or None, "body_runs": a.body_runs, "finger_runs": a.finger_runs,
            "timeout_s": a.timeout}


# --- the report: pure functions over what the Blender side collected ---------------------------------------------
def r5(v) -> list:
    return [round(float(x), 5) for x in v]


def mat_apply(m, v) -> list:
    """A 4x4 (row-major lists) applied to a point."""
    return r5(sum(m[i][j] * (v[j] if j < 3 else 1.0) for j in range(4)) for i in range(3))


def rotation_free(m, tol=1e-4) -> bool:
    """True when the 3x3 part is a uniform scale: a roll in rig space then reads the same in world."""
    s = m[0][0]
    return all(abs(m[i][j] - (s if i == j else 0.0)) < tol for i in range(3) for j in range(3))


def side_name(loc: str) -> str | None:
    """`shoulder_loc` -> shoulder.L, `shoulder_loc_sym` -> shoulder.R, `root_loc` -> root."""
    if loc.endswith("_loc_sym"):
        base, side = loc[:-8], ".R"
    elif loc.endswith("_loc"):
        base, side = loc[:-4], ".L"
    else:
        return None
    return base if base in CENTRE else base + side


def body_markers(loc: dict) -> dict:
    out = {}
    for k, v in loc.items():
        n = side_name(k)
        if n and n.split(".")[0] in CENTRE + SIDED:
            out[n] = r5(v)
    return dict(sorted(out.items()))


def body_required() -> list:
    return list(CENTRE) + [f"{b}.{s}" for b in SIDED for s in ("L", "R")]


def medoid_run(runs: list, group=lambda k: "") -> tuple:
    """The finger guess to keep from several ({marker: xyz} each, the same markers), per group of markers
    (a finger): the run nearest the group's per-marker median, so each finger stays one guess. Returns
    ({group: run index}, spread: the worst marker's largest distance from its median, {group: [mean
    distance per run]})."""
    import statistics
    keys = sorted(set.intersection(*[set(r) for r in runs])) if runs else []
    if len(runs) < 2 or not keys:
        return {group(k): 0 for k in keys}, 0.0, {}
    med = {k: [statistics.median(r[k][i] for r in runs) for i in range(3)] for k in keys}
    dist = {k: [math.dist(r[k], med[k]) for r in runs] for k in keys}
    kept, mean = {}, {}
    for g in sorted({group(k) for k in keys}):
        ks = [k for k in keys if group(k) == g]
        mean[g] = [sum(dist[k][i] for k in ks) / len(ks) for i in range(len(runs))]
        kept[g] = min(range(len(runs)), key=lambda i: mean[g][i])
    return kept, max(max(d) for d in dist.values()), mean


def finger_of(marker: str) -> str:
    """thumb1_loc, index3_loc_sym -> thumb, index (the finger a marker belongs to)."""
    return next((f for f in FINGERS if marker.startswith(f)), marker)


def finger_block(loc: dict, tries: list, requested: int | None) -> dict:
    marks = {}
    for k, v in loc.items():
        n = side_name(k)
        if n and n.startswith(FINGERS):
            marks[n] = r5(v)
    names = [f for f in FINGERS if f"{f}1.L" in marks]
    ok = [t for t in tries if t.get("ok")]
    counts = [t.get("count") for t in tries]
    return {"requested": requested, "count": len(names) if ok else 0, "fell_back": len(set(counts)) > 1 and bool(ok),
            "names": names if ok else [], "tries": tries, "markers": dict(sorted(marks.items())) if ok else {}}


def is_ai_scratch(fn: str) -> bool:
    """A picture or keypoint file the add-on writes into its inference folder for one guess
    (front1.jpg, hand2_l_kp.py, facial1_kp.py): only these are ever removed there."""
    return re.fullmatch(r"(front|side|top|hand|facial)\d+[A-Za-z0-9_]*?(_kp\.py|\.jpg)", fn) is not None


def ref_group(name: str) -> str:
    if name.startswith(FINGERS):
        return "finger"
    if name.startswith("ear_"):
        return "ear"
    if name.startswith(BODY_PFX):
        return "body"
    return "facial"


def refs_world(refs_local: dict, m) -> dict:
    out = {}
    for n, b in sorted(refs_local.items()):
        out[n] = {"head": mat_apply(m, b["head"]), "tail": mat_apply(m, b["tail"]),
                  "roll": round(float(b["roll"]), 5), "group": ref_group(n), "parent": b.get("parent")}
    return out


def brow_warnings(refs: dict, height: float | None) -> list:
    lids = sorted(r["tail"][1] for n, r in refs.items() if n.startswith("eyelid"))
    if not lids:
        return []
    lid_y = lids[len(lids) // 2]          # the lids' median depth: the face's surface at the eyes
    tol = BROW_AHEAD * (height or 1.75) / 1.75
    out = []
    for n, r in sorted(refs.items()):
        if n.startswith("eyebrow") and lid_y - r["head"][1] > tol:
            out.append(f"{n} sits {100 * (lid_y - r['head'][1]):.1f} cm in front of the eyelids "
                       "(a hair fringe?): look at it before binding")
    return out


def gates(rep: dict, state: dict, opts: dict) -> list:
    G = []
    ver, kp = state.get("ai_version"), len(state.get("kp_files") or [])
    G.append({"name": "smart.ai_files", "value": {"version": ver, "kp_files": kp},
              "limit": f">= {MIN_AI_VERSION:.2f} and keypoint files written",
              "pass": bool(ver is not None and ver >= MIN_AI_VERSION and kp > 0)})
    bm = rep["body_markers"]
    missing = [n for n in body_required() if n not in bm]
    G.append({"name": "smart.body_markers", "value": len({n.split(".")[0] for n in bm}),
              "limit": "11 markers, the sided ones on both sides", "pass": not missing,
              **({"missing": missing} if missing else {})})
    fg = rep["fingers"]
    G.append({"name": "smart.fingers", "value": fg["count"], "limit": "thumb1_loc present",
              "pass": fg["count"] > 0 and "thumb1.L" in fg["markers"]})
    fc = rep["facial"]
    if opts.get("facial"):
        feats = fc.get("features") or {}
        need = ["mouth"] + (["eyes"] if opts.get("eyes") != "none" else [])
        dropped = [f for f in need if not feats.get(f)]
        found, total = fc.get("keypoints_found"), fc.get("keypoints_total")
        moved = bool(total) and (found or 0) >= max(1, total // 2)
        G.append({"name": "smart.facial", "value": {"keypoints": found, "of": total, "dropped": dropped},
                  "limit": "chain ran, markers moved, " + " and ".join(need) + " kept",
                  "pass": bool(fc.get("ok")) and moved and not dropped})
    go = state.get("go") or {}
    G.append({"name": "smart.go", "value": go.get("has_match_to_rig_key"), "limit": "has_match_to_rig key",
              "pass": go.get("has_match_to_rig_key") is True})
    refs = rep["refs"]
    want = list(BODY_REFS)
    if fg["count"]:
        want.append("thumb1_ref.l")
    if opts.get("facial") and G[3:4] and G[3]["name"] == "smart.facial" and G[3]["pass"]:
        want.append("jaw_ref.x")
    lost = [n for n in want if n not in refs]
    G.append({"name": "smart.refs", "value": len(refs), "limit": f"> {len(BODY_REFS)}, every body ref present",
              "pass": len(refs) > len(BODY_REFS) and not lost, **({"missing": lost} if lost else {})})
    return G


def assemble(state: dict, opts: dict) -> tuple[dict, int]:
    """The autorig-smart/1 report and its exit code from the facts the Blender side collected."""
    m = state.get("rig_matrix_world")
    refs = refs_world(state.get("refs_local") or {}, m) if m else {}
    fc = state.get("facial") or {}
    rep = {"schema": SCHEMA, "tool": "arp_smart", "mesh": state.get("mesh"), "space": "world", "up": "+Z",
           "forward": "-Y", "units": "m", "height": state.get("height"),
           "arp": {"version": state.get("arp_version"), "ai_version": state.get("ai_version")},
           "blender": state.get("blender"), "options": opts, "steps": state.get("steps") or [],
           "body_markers": body_markers(state.get("body_loc") or {}),
           **({"body_runs": state["body_runs"]} if state.get("body_runs") else {}),
           "fingers": {**finger_block(state.get("finger_loc") or {}, state.get("finger_tries") or [],
                                      opts.get("fingers")), **({"runs": state["finger_runs"]}
                                                               if state.get("finger_runs") else {})},
           "facial": {"enabled": bool(opts.get("facial")), "ok": fc.get("ok"), "cancelled": fc.get("cancelled"),
                      "features": fc.get("features"), "keypoints_found": fc.get("keypoints_found"),
                      "keypoints_total": fc.get("keypoints_total"), "eye_proxies": fc.get("eye_proxies"),
                      "eye_objects": fc.get("eye_objects")},
           "rig_matrix_world": m, "refs": refs, "ref_rolls_from": "auto-rig-pro-go" if refs else None}
    warn = list(state.get("warnings") or [])
    if m and not rotation_free(m):
        warn.append("the rig object is rotated or scaled unevenly: rolls are in rig space")
    warn += brow_warnings(refs, state.get("height"))
    rep["gates"] = gates(rep, state, opts)
    for k in ("refused", "error"):
        if state.get(k):
            rep[k] = str(state[k])
    passed = all(g["pass"] for g in rep["gates"]) and not rep.get("refused") and not rep.get("error")
    code = 1 if (rep.get("refused") or rep.get("error")) else 0 if passed else 2
    rep.update({"pass": passed, "ok": passed, "verdict": "green" if passed else "harness" if code == 1 else "failed",
                "exit_code": code, "warnings": warn, "blend": state.get("blend"),
                "blend_markers": state.get("blend_markers"), "elapsed_s": state.get("elapsed_s")})
    return rep, code


def probe_report(info: dict) -> tuple[dict, int]:
    """--probe: ready when the add-on, every operator and AI files >= 1.20 are there."""
    G = [{"name": "smart.addon", "value": info.get("module"), "limit": "Auto-Rig Pro enabled",
          "pass": bool(info.get("module"))},
         {"name": "smart.operators", "value": info.get("operators_missing") or [], "limit": "all registered",
          "pass": bool(info.get("module")) and not info.get("operators_missing")},
         {"name": "smart.ai_files", "value": info.get("ai_version"), "limit": f">= {MIN_AI_VERSION:.2f}",
          "pass": (info.get("ai_version") or 0) >= MIN_AI_VERSION}]
    ready = all(g["pass"] for g in G)
    rep = {"schema": "gate/1", "tool": "arp_smart probe", "ready": ready, **info, "gates": G, "pass": ready,
           "ok": ready, "verdict": "green" if ready else "failed", "exit_code": 0 if ready else 2}
    return rep, rep["exit_code"]


def emit(rep: dict, out: str | None) -> None:
    """Write the report to `out` (indented) and print it as one tagged line."""
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        tmp = out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=1, default=str)
        os.replace(tmp, out)
    sys.stdout.write(TAG + json.dumps(rep, default=str) + "\n")
    sys.stdout.flush()


# --- inside Blender ---------------------------------------------------------------------------------------------
def _bpy():
    import bpy
    return bpy


def addon_module() -> str | None:
    bpy = _bpy()
    hits = [a.module for a in bpy.context.preferences.addons if "auto_rig_pro" in a.module.lower()]
    return sorted(hits, key=len)[0] if hits else None


def registered(idname: str) -> bool:
    """bpy.ops builds a wrapper for any name; only the RNA lookup fails for one nobody registered."""
    bpy = _bpy()
    space, fn = idname.split(".", 1)
    try:
        getattr(getattr(bpy.ops, space), fn).get_rna_type()
        return True
    except (KeyError, AttributeError, ValueError):
        return False


def ai_info(module: str | None) -> dict:
    bpy = _bpy()
    out = {"module": module, "arp_version": None, "ai_path_set": False, "ai_version": None, "ai_binaries": {},
           "inference": None}
    if not module:
        return out
    mod = sys.modules.get(module)
    info = getattr(mod, "bl_info", None)
    if isinstance(info, dict) and info.get("version"):
        out["arp_version"] = ".".join(str(x) for x in info["version"])
    else:
        try:
            import tomllib
            with open(os.path.join(os.path.dirname(mod.__file__), "blender_manifest.toml"), "rb") as f:
                out["arp_version"] = str(tomllib.load(f).get("version"))
        except (OSError, ValueError, ImportError, AttributeError, TypeError):
            pass
    prefs = getattr(bpy.context.preferences.addons.get(module), "preferences", None)
    root = os.environ.get(AI_DIR_ENV) or (bpy.path.abspath(getattr(prefs, "ai_presets_path", "") or "") if prefs else "")
    out["ai_dir_from_env"] = bool(os.environ.get(AI_DIR_ENV))
    out["ai_path_set"] = bool(root)
    if root:
        try:
            with open(os.path.join(root, "info.dat"), encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("version="):
                        out["ai_version"] = float(line.split("=", 1)[1])
                        break
        except (OSError, ValueError):
            pass
        inf = os.path.join(root, "inference")
        out["inference"] = inf if os.path.isdir(inf) else None
        for b in ("inference_front", "inference_side", "inference_top", "inference_fingers", "inference_facial"):
            p = os.path.join(inf, b)
            out["ai_binaries"][b] = {"exists": os.path.exists(p), "executable": os.access(p, os.X_OK)}
    return out


def probe() -> dict:
    mod = addon_module()
    info = ai_info(mod)
    info["operators_missing"] = [o for o in OPERATORS if not registered(o)] if mod else list(OPERATORS)
    info.pop("inference", None)
    return info


class Run:
    """The windowed chain: one step per timer tick, a soft timeout between steps, a watchdog past it."""

    def __init__(self, a):
        bpy = _bpy()
        self.a, self.opts, self.t0 = a, options(a), time.time()
        self.S = {"mesh": a.mesh, "blender": bpy.app.version_string, "steps": [], "warnings": [],
                  "kp_files": [], "body_loc": {}, "finger_tries": [], "finger_loc": {}, "refs_local": {}}
        self.ctx, self.i, self.done, self.module, self.inf, self.prefs = {}, -1, False, None, None, {}
        self.steps = [("setup", self.setup), ("select", self.select), ("body", self.body),
                      ("fingers", self.fingers)] + ([("face", self.face)] if a.facial else []) + \
                     [("go", self.go)]
        self.hard = {"setup", "select", "body", "go"}

    # -- context
    def find_ctx(self) -> bool:
        bpy = _bpy()
        wm = bpy.context.window_manager
        if not wm.windows:
            return False
        win = wm.windows[0]
        areas = [x for x in win.screen.areas if x.type == "VIEW_3D"]
        if not areas:
            big = max(win.screen.areas, key=lambda x: x.width * x.height)
            big.type = "VIEW_3D"
            areas = [big]
        area = max(areas, key=lambda x: x.width * x.height)
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        if region is None:
            return False
        self.ctx = {"window": win, "screen": win.screen, "area": area, "region": region}
        return area.width > 50

    def ov(self):
        return _bpy().context.temp_override(**self.ctx)

    def op(self, idname, *args, **kw):
        """Call an operator under the 3D view override: (result, error text, seconds)."""
        bpy = _bpy()
        if not registered(idname):
            raise Refused(f"operator {idname} is not registered (refusing to guess another)")
        space, fn = idname.split(".", 1)
        t, res, err = time.time(), None, None
        try:
            with self.ov():
                res = getattr(getattr(bpy.ops, space), fn)(*args, **kw)
        except RuntimeError as e:            # self.report({'ERROR'}) raises; its text is localised
            err = str(e).strip()[:400]
        return (sorted(res) if res else None), err, round(time.time() - t, 2)

    # -- the inference folder: stale keypoint files out, the new ones counted
    def clear_stale(self) -> int:
        n = 0
        if self.inf:
            for fn in os.listdir(self.inf):
                if is_ai_scratch(fn):
                    try:
                        os.remove(os.path.join(self.inf, fn))
                        n += 1
                    except OSError:
                        pass
        return n

    def watch(self):
        import threading
        seen, stop = set(), threading.Event()

        def loop():
            while not stop.is_set():
                try:
                    seen.update(f for f in os.listdir(self.inf) if f.endswith("_kp.py"))
                except OSError:
                    pass
                stop.wait(0.1)
        th = threading.Thread(target=loop, daemon=True)
        if self.inf:
            th.start()

        def end():
            stop.set()
            if th.is_alive():
                th.join(timeout=2)
            return sorted(seen)
        return end

    @staticmethod
    def locs() -> dict:
        bpy = _bpy()
        return {o.name: r5(o.matrix_world.to_translation()) for o in bpy.data.objects
                if o.name.endswith("_loc") or o.name.endswith("_loc_sym")}

    # -- steps
    def setup(self):
        bpy = _bpy()
        prefs = bpy.context.preferences
        self.prefs = {"smooth_view": prefs.view.smooth_view}
        prefs.use_preferences_save = False         # first: a windowed Blender saves preferences on quit
        prefs.view.smooth_view = 0
        if os.environ.get(AI_DIR_ENV):              # this run's AI folder; never saved (above)
            mod = addon_module()
            ap = getattr(prefs.addons.get(mod), "preferences", None) if mod else None
            if ap is not None and hasattr(ap, "ai_presets_path"):
                ap.ai_presets_path = os.environ[AI_DIR_ENV]
        vl = bpy.context.view_layer
        vl.active_layer_collection = vl.layer_collection
        self.module = addon_module()
        if not self.module:
            raise Refused("Auto-Rig Pro is not enabled in this Blender (do not start with --factory-startup)")
        missing = [o for o in OPERATORS if not registered(o)]
        if missing:
            raise Refused(f"operators not registered: {missing} (refusing to guess others)")
        info = ai_info(self.module)
        self.inf = info["inference"]
        self.S.update(arp_version=info["arp_version"], ai_version=info["ai_version"],
                      ai_binaries=info["ai_binaries"])
        if not info["ai_path_set"] or info["ai_version"] is None or self.inf is None:
            raise Refused("no AI files: install them with the add-on's Install AI Files...")
        if info["ai_version"] < MIN_AI_VERSION:
            raise Refused(f"AI files {info['ai_version']} are older than {MIN_AI_VERSION:.2f}: reinstall them")
        rigs = [o.name for o in bpy.data.objects if o.type == "ARMATURE" and "arp_rig_type" in o.keys()]
        if rigs:
            raise Refused(f"the file already holds Auto-Rig Pro rig(s) {rigs}: Go! would open a dialog")
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
        m = bpy.data.objects.get(self.a.mesh) if self.a.mesh else \
            max(meshes, key=lambda o: len(o.data.vertices), default=None)
        if m is None or m.type != "MESH":
            raise Refused(f"no mesh {self.a.mesh!r} in this file")
        self.mesh = m
        zs = [(m.matrix_world @ __import__("mathutils").Vector(c)).z for c in m.bound_box]
        self.S.update(mesh=m.name, height=round(max(zs) - min(zs), 5))
        self.ctx["area"].spaces.active.shading.type = "MATERIAL"
        with self.ov():
            if bpy.context.object and bpy.context.object.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.select_all(action="DESELECT")
        m.hide_set(False)
        m.select_set(True)
        vl.objects.active = m
        return {"ok": True, "mesh": m.name}

    def select(self):
        bpy = _bpy()
        scn = bpy.context.scene
        scn.arp_smart_type = "BODY"
        res, err, dt = self.op("id.get_selected_objects", "EXEC_DEFAULT")
        ok = bpy.data.objects.get(scn.arp_body_name or "") is not None
        return {"ok": ok and not err, "error": err, "seconds": dt}

    def body(self):
        bpy = _bpy()
        scn = bpy.context.scene
        if self.a.body_samples:
            scn.arp_smart_AI_body_samples = self.a.body_samples
        stale = self.clear_stale()
        is_body = lambda k: (side_name(k) or "").split(".")[0] in CENTRE + SIDED
        runs, dt, failed = [], 0.0, None
        for r in range(max(1, self.a.body_runs)):     # the guess varies run to run: per marker the medoid
            end = self.watch()
            res, err, t = self.op("arp.guess_markers")
            kp = end()
            self.clear_stale()
            dt += t
            if r == 0:
                self.S["kp_files"] = kp
            if err:
                failed = err
                break
            runs.append({k: v for k, v in self.locs().items() if is_body(k)})
        if runs:                 # a later guess that failed: the good ones are kept, the failure reported
            kept, spread, _ = medoid_run(runs, lambda k: k)
            for name in set.intersection(*[set(x) for x in runs]):
                o = bpy.data.objects.get(name)
                if o is not None:
                    o.matrix_world.translation = runs[kept[name]][name]
            bpy.context.view_layer.update()
            self.S["body_runs"] = {"runs": len(runs), "spread_m": round(spread, 5),
                                   **({"failed_after": len(runs), "error": failed} if failed else {})}
        self.S["body_loc"] = {k: v for k, v in self.locs().items() if is_body(k)}
        missing = [n for n in body_required() if n not in body_markers(self.S["body_loc"])]
        err = failed if not runs or missing else None     # ok and error never both
        return {"ok": bool(runs) and not missing, "error": err, "seconds": round(dt, 2), "missing": missing,
                "runs": len(runs),
                "samples": scn.arp_smart_AI_body_samples, "kp_files": len(self.S["kp_files"]),
                "stale_removed": stale}

    def fingers(self):
        bpy = _bpy()
        scn = bpy.context.scene
        if self.a.finger_samples:
            scn.arp_smart_AI_samples = self.a.finger_samples
        for n in ([5, 4] if self.a.fingers == 5 else [4]):
            scn.arp_fingers_to_detect = n
            runs = []
            for _ in range(max(1, self.a.finger_runs)):     # the guess varies run to run: keep the medoid
                self.clear_stale()
                res, err, dt = self.op("arp.guess_fingers")
                self.clear_stale()
                ok = bpy.data.objects.get("thumb1_loc") is not None and not err
                self.S["finger_tries"].append({"count": n, "ok": ok, "error": err, "seconds": dt})
                if not ok:
                    break
                runs.append({k: v for k, v in self.locs().items() if k.startswith(FINGERS)})
            if runs and any(bpy.data.objects.get(k) is None for k in runs[0]):
                # a later guess failed and took the markers with it: one more guess puts them back, or none count
                self.clear_stale()
                res, err, dt = self.op("arp.guess_fingers")
                self.clear_stale()
                ok = bpy.data.objects.get("thumb1_loc") is not None and not err
                self.S["finger_tries"].append({"count": n, "ok": ok, "error": err, "seconds": dt, "restore": True})
                runs = runs + [{k: v for k, v in self.locs().items() if k.startswith(FINGERS)}] if ok else []
            if runs:
                kept, spread, _ = medoid_run(runs, finger_of)
                for name in set.intersection(*[set(r) for r in runs]):   # each finger's kept guess back
                    o = bpy.data.objects.get(name)                       # onto the markers Go! reads
                    if o is not None:
                        o.matrix_world.translation = runs[kept[finger_of(name)]][name]
                bpy.context.view_layer.update()
                self.S["finger_loc"] = {k: v for k, v in self.locs().items() if k.startswith(FINGERS)}
                self.S["finger_runs"] = {"runs": len(runs), "kept": kept, "spread_m": round(spread, 5)}
                return {"ok": True, "count": n, "runs": len(runs), "spread_m": round(spread, 5)}
        scn.arp_fingers_enable = False             # Go!'s invoke would run the finger guess again
        return {"ok": False, "count": 0, "error": "no finger markers (a popup in the add-on)"}

    def facial_markers(self):
        """The face template's keypoints {name: world}, by the add-on's own index table when it has one."""
        bpy = _bpy()
        fs = bpy.data.objects.get("arp_facial_setup")
        if fs is None:
            return {}
        table = next((getattr(m, "facial_markers") for k, m in list(sys.modules.items())
                      if k.startswith(self.module or "?") and k.endswith("auto_rig_datas")
                      and isinstance(getattr(m, "facial_markers", None), dict)), None)
        dg = bpy.context.evaluated_depsgraph_get()
        ev = fs.evaluated_get(dg)
        me = ev.to_mesh()
        try:
            idx = table.items() if table else ((str(i), i) for i in range(len(me.vertices)))
            return {n: r5(fs.matrix_world @ me.vertices[i].co) for n, i in idx if i < len(me.vertices)}
        finally:
            ev.to_mesh_clear()

    def proxy_eyes(self, fm: dict, moved: set) -> dict | None:
        """A sphere behind each eye: centre at the lid markers' centroid, radius 0.55 x the lid width,
        its front on the skin (a ray from the front). Data API only: an operator's active object read
        back after a temp_override is not the new one."""
        bpy = _bpy()
        import bmesh
        from mathutils import Vector
        out = {}
        for side in (".l", ".r"):
            keys = [k for k in fm if k.startswith("eyelid") and k.endswith(side)]
            if not keys or any(k not in moved for k in keys) or \
                    f"eyelid_corner_01{side}" not in fm or f"eyelid_corner_02{side}" not in fm:
                return None
            c = sum((Vector(fm[k]) for k in keys), Vector()) / len(keys)
            r = 0.55 * (Vector(fm[f"eyelid_corner_01{side}"]) - Vector(fm[f"eyelid_corner_02{side}"])).length
            mi = self.mesh.matrix_world.inverted()
            hit, loc, _n, _f = self.mesh.ray_cast(mi @ Vector((c.x, c.y - 5.0, c.z)),
                                                  (mi.to_3x3() @ Vector((0, 1, 0))).normalized())
            if not hit or r <= 0:
                return None
            y = (self.mesh.matrix_world @ loc).y + r
            me = bpy.data.meshes.new(PROXY + side)
            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=r)
            bm.to_mesh(me)
            bm.free()
            o = bpy.data.objects.new(PROXY + side, me)
            bpy.context.scene.collection.objects.link(o)
            o.location = (c.x, y, c.z)
            out[side[1:].upper()] = {"object": o.name, "center": r5((c.x, y, c.z)), "radius": round(r, 5)}
        return out

    def eye_objects(self) -> dict | None:
        """--eyes objects: import the fitted eyeballs and move them by the prep's transform (the frame GLB's
        extents onto the open mesh's: scale from z, shift from the minima), named as proxies so they leave
        with them."""
        bpy = _bpy()
        from mathutils import Matrix, Vector

        def imported(path):
            before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=path)
            new = [o for o in bpy.data.objects if o not in before]
            for o in new:
                if o.type == "MESH":
                    w = o.matrix_world.copy()
                    o.parent = None
                    o.data.transform(w)
                    o.matrix_world = Matrix.Identity(4)
            for o in [o for o in new if o.type != "MESH"]:
                bpy.data.objects.remove(o)
            return [o for o in new if o.type == "MESH"]

        def box(objs):
            pts = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
            return (Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)]))

        raw = imported(self.a.eye_frame_glb)
        lo, hi = box(raw)
        for o in raw:
            me = o.data
            bpy.data.objects.remove(o)
            if me.users == 0:
                bpy.data.meshes.remove(me)
        bb = [self.mesh.matrix_world @ Vector(c) for c in self.mesh.bound_box]
        plo = Vector([min(v[i] for v in bb) for i in range(3)])
        phi = Vector([max(v[i] for v in bb) for i in range(3)])
        s = (phi.z - plo.z) / max(hi.z - lo.z, 1e-12)
        t = plo - s * lo
        out = {}
        for o in imported(self.a.eye_glb):
            side = o.get("eye") or ("L" if o.name.startswith("Eye.L") else "R" if o.name.startswith("Eye.R") else None)
            if side not in ("L", "R"):
                bpy.data.objects.remove(o)
                continue
            o.data.transform(Matrix.Translation(t) @ Matrix.Scale(s, 4))
            o.name = PROXY + "." + side.lower()
            c = s * Vector(o["centre"]).xzy * Vector((1, -1, 1)) + t if o.get("centre") else None
            out[side] = {"object": o.name, "center": r5(c) if c is not None else None,
                         "radius": round(s * float(o["radius"]), 5) if o.get("radius") else None}
        self.S["eye_transform"] = {"scale": round(s, 6), "shift": r5(t)}
        if set(out) != {"L", "R"}:
            self.drop_proxies()
            return None
        return out

    def drop_proxies(self):
        bpy = _bpy()
        for o in [o for o in bpy.data.objects if o.name.startswith(PROXY)]:
            me = o.data
            bpy.data.objects.remove(o)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)

    def face(self):
        bpy = _bpy()
        scn = bpy.context.scene
        eyes = self.a.eyes
        # its execute reads these: decide before facial_setup; proxy turns eyes on after the guess
        scn.arp_smart_eyes = eyes == "auto"
        scn.arp_smart_teeth = False
        scn.arp_smart_tongue = False
        out, F = {}, {"ok": False, "cancelled": False}
        _, err, dt = self.op("id.facial_setup")
        out["facial_setup"] = {"error": err, "seconds": dt}
        before = self.facial_markers()
        self.clear_stale()
        _, err2, dt = self.op("arp.guess_facial")
        self.clear_stale()
        after = self.facial_markers()
        moved = {k for k in after if k in before and
                 sum((x - y) ** 2 for x, y in zip(after[k], before[k])) ** 0.5 > 1e-4}
        out["guess_facial"] = {"error": err2, "seconds": dt}
        F.update(keypoints_found=len(moved), keypoints_total=len(after))
        if eyes in ("proxy", "objects") and not err and not err2:
            key = "eye_proxies" if eyes == "proxy" else "eye_objects"
            F[key] = self.proxy_eyes(after, moved) if eyes == "proxy" else self.eye_objects()
            if F[key]:
                scn.arp_smart_eyes = True
                scn.arp_eyeball_mode = "MANUAL"
                scn.arp_eyeball_type = "SEPARATE"
                scn.arp_eyeball_name = F[key]["L"]["object"]
                scn.arp_eyeball_name_right = F[key]["R"]["object"]
        _, err3, dt = self.op("id.validate_facial_setup")
        out["validate_facial_setup"] = {"error": err3, "seconds": dt}
        F["features"] = {k[10:]: bool(getattr(scn, k, False)) for k in (
            "arp_smart_eyes", "arp_smart_eyebrows", "arp_smart_nose", "arp_smart_cheeks", "arp_smart_mouth",
            "arp_smart_chin", "arp_smart_ears", "arp_smart_teeth", "arp_smart_tongue")}
        F["ok"] = not (err or err2 or err3) and bool(after) and len(moved) >= max(1, len(after) // 2)
        if not F["ok"]:
            # body and fingers still: Go!'s invoke would re-validate the eyes and build nothing
            scn.arp_smart_eyes = False
            if bpy.data.objects.get("arp_facial_setup"):
                _, e4, d4 = self.op("id.cancel_facial_setup")
                out["cancel_facial_setup"] = {"error": e4, "seconds": d4}
            self.drop_proxies()
            F["cancelled"] = True
        self.S["facial"] = F
        return {"ok": F["ok"], "error": err or err2 or err3, **out}

    def go(self):
        bpy = _bpy()
        if self.a.save_blend:
            p = os.path.splitext(os.path.abspath(self.a.save_blend))[0] + "_markers.blend"
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with self.ov():
                bpy.ops.wm.save_as_mainfile(filepath=p, copy=True)
            self.S["blend_markers"] = p
        before = {o.name for o in bpy.data.objects if o.type == "ARMATURE"}
        res, err, dt = self.op("id.go_detect", "INVOKE_DEFAULT")
        rigs = [o for o in bpy.data.objects if o.type == "ARMATURE" and "arp_rig_type" in o.keys()]
        rig = next((o for o in rigs if o.name not in before), rigs[0] if rigs else None)
        G = {"rig": rig.name if rig else None, "error": err,
             "has_match_to_rig_key": bool(rig and "has_match_to_rig" in rig.data.keys())}
        self.S["go"] = G
        if rig is None:
            return {"ok": False, "error": err or "Go! built no rig", "seconds": dt}
        with self.ov():
            if bpy.context.view_layer.objects.active != rig or rig.mode != "EDIT":
                if bpy.context.object and bpy.context.object.mode != "OBJECT":
                    bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.object.select_all(action="DESELECT")
                rig.select_set(True)
                bpy.context.view_layer.objects.active = rig
                bpy.ops.object.mode_set(mode="EDIT")
        mw = rig.matrix_world
        self.S["rig_matrix_world"] = [[round(mw[i][j], 6) for j in range(4)] for i in range(4)]
        self.S["refs_local"] = {eb.name: {"head": r5(eb.head), "tail": r5(eb.tail), "roll": eb.roll,
                                          "parent": eb.parent.name if eb.parent else None}
                                for eb in rig.data.edit_bones if "_ref" in eb.name}
        self.drop_proxies()
        with self.ov():
            bpy.ops.object.mode_set(mode="OBJECT")
            if self.a.save_blend:
                os.makedirs(os.path.dirname(os.path.abspath(self.a.save_blend)), exist_ok=True)
                bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(self.a.save_blend), copy=True)
                self.S["blend"] = os.path.abspath(self.a.save_blend)
        return {"ok": G["has_match_to_rig_key"] and not err, "error": err, "seconds": dt,
                "refs": len(self.S["refs_local"])}

    # -- driving
    def report(self):
        self.S["elapsed_s"] = round(time.time() - self.t0, 1)
        return assemble(self.S, self.opts)

    def finish(self):
        bpy = _bpy()
        self.done = True
        try:
            if "smooth_view" in self.prefs:
                bpy.context.preferences.view.smooth_view = self.prefs["smooth_view"]
        except Exception:      # noqa: BLE001 — never stop the report on a preference
            pass
        rep, code = self.report()
        emit(rep, self.a.out)
        sys.stderr.flush()
        os._exit(code)         # quit_blender exits 0 whatever the gates say; nothing is saved on the way out

    def tick(self):
        try:
            if self.i < 0:
                if not self.find_ctx():
                    if time.time() - self.t0 > 60:
                        self.S["error"] = "no usable 3D view in the window after 60 s"
                        return self.finish()
                    return 0.5
                self.i = 0
                return 0.5
            if time.time() - self.t0 > self.a.timeout:
                self.S["error"] = f"timeout: {self.a.timeout:.0f} s"
                return self.finish()
            if self.i >= len(self.steps):
                return self.finish()
            name, fn = self.steps[self.i]
            t = time.time()
            try:
                info = fn() or {}
            except Refused as e:
                self.S["refused"] = str(e)
                self.S["steps"].append({"step": name, "ok": False, "error": str(e),
                                        "seconds": round(time.time() - t, 2)})
                return self.finish()
            info = {"step": name, "seconds": round(time.time() - t, 2), **info}
            self.S["steps"].append(info)
            print(f"arp_smart: {name} ok={info.get('ok')} {info['seconds']} s", flush=True)
            self.i += 1
            if not info.get("ok") and name in self.hard:
                return self.finish()
            return 0.3
        except Exception as e:  # noqa: BLE001 — every failure is reported, exit 1
            import traceback
            self.S["error"] = f"{type(e).__name__}: {e}"
            self.S["warnings"].append(traceback.format_exc()[-1200:])
            return self.finish()

    def watchdog(self):
        lim = self.a.timeout + HARD_EXTRA
        while time.time() - self.t0 < lim:
            if self.done:
                return
            time.sleep(1)
        self.S["error"] = f"hard timeout: {lim:.0f} s (an operator did not return)"
        try:
            rep, _ = self.report()
            emit(rep, self.a.out)
        finally:
            os._exit(1)


class Refused(Exception):
    pass


def run_blender(a) -> None:
    bpy = _bpy()
    if a.probe:
        info = probe()
        rep, code = probe_report(info)
        emit(rep, a.out)
        sys.exit(code)
    if bpy.app.background:
        rep, code = assemble({"refused": "the AI needs a window: run Blender without -b (and without "
                              "--factory-startup)", "steps": []}, options(a))
        emit(rep, a.out)
        sys.exit(code)
    import threading
    r = Run(a)
    threading.Thread(target=r.watchdog, daemon=True).start()
    bpy.app.timers.register(r.tick, first_interval=1.0)
    print(f"arp_smart: registered, timeout {a.timeout:.0f} s", flush=True)


# --- selftest (host, no Blender) ---------------------------------------------------------------------------------
def _fake_state(fingers=5, facial=True, **over) -> dict:
    """A run modelled on the teal runner's: Go! scaled the rig by 0.9515."""
    s = 0.951453
    body = {"root_loc": [0, 0.01, 0.922], "neck_loc": [0, 0.0, 1.397], "chin_loc": [0, -0.09, 1.494],
            "head_tip_loc": [0, 0.0, 1.702]}
    for b, p in {"shoulder": (0.17, 0.02, 1.327), "elbow": (0.33, 0.05, 1.132), "hand": (0.45, 0.02, 0.978),
                 "hand_tip": (0.52, -0.01, 0.812), "thigh": (0.1, 0.0, 0.922), "knee": (0.11, -0.01, 0.541),
                 "foot": (0.12, 0.03, 0.18)}.items():
        body[f"{b}_loc"] = list(p)
        body[f"{b}_loc_sym"] = [-p[0], p[1], p[2]]
    names = ["thumb", "index", "middle", "ring", "pinky"] if fingers == 5 else ["thumb", "middle", "ring", "pinky"]
    fl = {}
    for i, f in enumerate(names):
        for j in range(1, 5):
            fl[f"{f}{j}_loc"] = [0.48 + 0.01 * j, -0.02 + 0.01 * i, 0.9 - 0.02 * j]
            fl[f"{f}{j}_loc_sym"] = [-0.48 - 0.01 * j, -0.02 + 0.01 * i, 0.9 - 0.02 * j]
    refs = {n: {"head": [0.1, 0.0, 1.0], "tail": [0.1, 0.0, 1.1], "roll": 0.0, "parent": None} for n in BODY_REFS}
    refs["hand_ref.l"] = {"head": [0.47, 0.02, 1.03], "tail": [0.5, 0.0, 0.98], "roll": 0.612, "parent": "forearm_ref.l"}
    for f in names:
        for j in (1, 2, 3):
            refs[f"{f}{j}_ref.l"] = {"head": [0.5, 0.0, 0.9], "tail": [0.51, 0.0, 0.88], "roll": 1.0, "parent": None}
    if facial:
        for n in ("jaw_ref.x", "nose_01_ref.x", "lips_top_ref.x", "ear_01_ref.l"):
            refs[n] = {"head": [0.0, -0.08, 1.6], "tail": [0.0, -0.1, 1.6], "roll": -1.5708, "parent": "head_ref.x"}
        for sd, x in (("l", 0.04), ("r", -0.04)):
            refs[f"eyelid_top_ref.{sd}"] = {"head": [x, -0.06, 1.66], "tail": [x, -0.08, 1.67], "roll": 0.0,
                                            "parent": "head_ref.x"}
            refs[f"eyebrow_02_ref.{sd}"] = {"head": [x, -0.11, 1.69], "tail": [x, -0.11, 1.70], "roll": 1.5708,
                                            "parent": "head_ref.x"}
    st = {"mesh": "Runner", "height": 1.75, "arp_version": "3.78.63", "ai_version": 1.21, "blender": "5.2.1",
          "steps": [{"step": "setup", "ok": True}], "warnings": [],
          "kp_files": [f"front{i}_kp.py" for i in range(1, 11)] + ["side1_kp.py", "top1_kp.py"],
          "body_loc": body, "finger_tries": [{"count": fingers, "ok": True}], "finger_loc": fl,
          "facial": {"ok": True, "cancelled": False, "keypoints_found": 48, "keypoints_total": 48,
                     "features": {"eyes": True, "mouth": True, "eyebrows": True},
                     "eye_proxies": {"L": {"center": [0.038, -0.074, 1.577], "radius": 0.021}}} if facial else None,
          "go": {"rig": "rig", "has_match_to_rig_key": True},
          "rig_matrix_world": [[s, 0, 0, 0], [0, s, 0, 0], [0, 0, s, 0], [0, 0, 0, 1]],
          "refs_local": refs, "elapsed_s": 28.6}
    st.update(over)
    return st


def selftest() -> int:
    import contextlib
    import io
    checks = []

    def check(name, cond, **kw):
        checks.append({"name": name, "pass": bool(cond), **kw})

    def opts(*argv):
        return options(parser().parse_args(list(argv)))

    def gate(rep, name):
        return next((g for g in rep["gates"] if g["name"] == name), None)

    # 1. the command line
    a = parser().parse_args([])
    check("defaults: 5 fingers, face on, proxy eyes, 600 s", a.fingers == 5 and a.facial and a.eyes == "proxy"
          and a.timeout == TIMEOUT and not a.probe)
    here = os.path.abspath(__file__)
    check("--eyes objects needs --eye-glb and --eye-frame-glb (existing files); they need it",
          "--eye-frame-glb" in (eye_args_error(parser().parse_args(["--eyes", "objects", "--eye-glb", here])) or "")
          and eye_args_error(parser().parse_args(["--eyes", "objects", "--eye-glb", here, "--eye-frame-glb", here])) is None
          and "missing" in (eye_args_error(parser().parse_args(["--eyes", "objects", "--eye-glb", here + "x",
                                                                "--eye-frame-glb", here])) or "")
          and eye_args_error(parser().parse_args(["--eye-glb", here])) is not None
          and opts("--eyes", "objects")["eyes"] == "objects")
    check("--no-facial drops the eyes option", opts("--no-facial")["facial"] is False and opts("--no-facial")["eyes"] is None)
    for bad in (["--fingers", "3"], ["--eyes", "glass"], ["--no-such-flag"]):
        with contextlib.redirect_stderr(io.StringIO()):
            try:
                parser().parse_args(bad)
                code = 0
            except SystemExit as e:
                code = e.code
        check(f"usage error {bad[0]} exits 1, not 2", code == 1, code=code)
    # 2. a full pass, as the teal runner's
    rep, code = assemble(_fake_state(), opts())
    check("full run: every gate passes, exit 0, verdict green", code == 0 and rep["pass"] is True
          and rep["verdict"] == "green" and [g["name"] for g in rep["gates"]] == [
              "smart.ai_files", "smart.body_markers", "smart.fingers", "smart.facial", "smart.go", "smart.refs"],
          failed=[g for g in rep["gates"] if not g["pass"]])
    check("gate/1 shape: name and pass on each gate, no ok in a gate, pass == ok",
          all(set(g) >= {"name", "pass"} and "ok" not in g for g in rep["gates"]) and rep["ok"] == rep["pass"])
    bm = rep["body_markers"]
    check("_loc -> .L, _loc_sym -> .R, the centre markers bare; 18 in all",
          bm["shoulder.L"][0] > 0 and bm["shoulder.R"][0] < 0 and "root" in bm and "root.L" not in bm
          and len(bm) == 18 and gate(rep, "smart.body_markers")["value"] == 11)
    runs = [{"thumb1_loc": [0.5, 0.0, 0.9], "thumb2_loc": [0.5, 0.0, 0.88], "index1_loc": [0.6, 0.0, 0.9]},
            {"thumb1_loc": [0.503, 0.0, 0.9], "thumb2_loc": [0.503, 0.0, 0.88], "index1_loc": [0.62, 0.0, 0.9]},
            {"thumb1_loc": [0.52, 0.0, 0.88], "thumb2_loc": [0.52, 0.0, 0.86], "index1_loc": [0.601, 0.0, 0.9]}]
    kept, spread, _ = medoid_run(runs, finger_of)
    check("finger runs: per finger the run nearest its median (thumb from run 0 or 1, index from run 0 or 2, "
          "never the outlier), spread the worst marker's distance; one run keeps itself",
          kept["thumb"] in (0, 1) and kept["index"] in (0, 2) and abs(spread - math.dist([0.52, 0, 0.88], [0.503, 0, 0.9])) < 1e-9
          and medoid_run(runs[:1], finger_of)[0] == {"thumb": 0, "index": 0} and medoid_run(runs[:1])[1] == 0.0,
          kept=kept, spread=spread)
    rr, _ = assemble(_fake_state(finger_tries=[{"count": 5, "ok": True}] * 5,
                                 finger_runs={"runs": 5, "kept": {"thumb": 1}, "spread_m": 0.004}), opts())
    check("five runs at five fingers are no fallback; fingers.runs reported",
          rr["fingers"]["fell_back"] is False and rr["fingers"]["runs"]["kept"] == {"thumb": 1}
          and parser().parse_args([]).finger_runs == 5 and parser().parse_args([]).body_runs == 3)
    fg = rep["fingers"]
    check("five fingers: names thumb..pinky, markers 1..4 per side, no fallback",
          fg["count"] == 5 and fg["names"] == list(FINGERS) and "pinky4.R" in fg["markers"] and not fg["fell_back"])
    h = rep["refs"]["hand_ref.l"]
    check("refs: head through the rig's matrix (0.9515), roll kept, grouped",
          abs(h["head"][0] - 0.47 * 0.951453) < 1e-5 and h["roll"] == 0.612 and h["group"] == "body"
          and rep["refs"]["thumb1_ref.l"]["group"] == "finger" and rep["refs"]["jaw_ref.x"]["group"] == "facial"
          and rep["refs"]["ear_01_ref.l"]["group"] == "ear" and rep["ref_rolls_from"] == "auto-rig-pro-go")
    check("a uniform scale is rotation free; a rotation is not",
          rotation_free(rep["rig_matrix_world"]) and not rotation_free([[0, -1, 0, 0], [1, 0, 0, 0], [0, 0, 1, 0],
                                                                       [0, 0, 0, 1]]))
    check("a brow 3 cm in front of the eyelids is a warning (a fringe); one at the lids is not",
          any("eyebrow_02_ref.l" in w for w in rep["warnings"])
          and not brow_warnings({"eyelid_top_ref.l": {"tail": [0, -0.1, 0]}, "eyebrow_01_ref.l": {"head": [0, -0.11, 0]}}, 1.75),
          warnings=rep["warnings"])
    line = io.StringIO()
    with contextlib.redirect_stdout(line):
        emit(rep, None)
    txt = line.getvalue()
    check("one tagged line, valid JSON after the tag",
          txt.count("\n") == 1 and txt.startswith(TAG) and json.loads(txt[len(TAG):])["schema"] == SCHEMA)
    # 3. fingers: 5 failed, 4 found
    st = _fake_state(fingers=4, finger_tries=[{"count": 5, "ok": False}, {"count": 4, "ok": True}])
    rep, code = assemble(st, opts())
    fg = rep["fingers"]
    check("5 fails, 4 found: fell back, the four-finger hand has no index, exit 0",
          code == 0 and fg["fell_back"] and fg["count"] == 4 and fg["names"] == ["thumb", "middle", "ring", "pinky"]
          and fg["requested"] == 5)
    st = _fake_state(finger_tries=[{"count": 5, "ok": False}, {"count": 4, "ok": False}], finger_loc={})
    st["refs_local"] = {k: v for k, v in st["refs_local"].items() if not k.startswith(FINGERS)}
    rep, code = assemble(st, opts())
    check("no fingers: smart.fingers fails, the refs gate does not ask for a thumb, exit 2",
          code == 2 and not gate(rep, "smart.fingers")["pass"] and gate(rep, "smart.refs")["pass"])
    # 4. the face
    rep, code = assemble(_fake_state(facial=False), opts("--no-facial"))
    check("--no-facial: no smart.facial gate, exit 0", code == 0 and gate(rep, "smart.facial") is None
          and rep["facial"]["enabled"] is False)
    st = _fake_state()
    st["facial"]["features"]["mouth"] = False
    rep, code = assemble(st, opts())
    check("the add-on dropped the mouth (Solid shading): smart.facial fails, exit 2, no jaw demanded",
          code == 2 and not gate(rep, "smart.facial")["pass"] and gate(rep, "smart.facial")["value"]["dropped"]
          == ["mouth"] and gate(rep, "smart.refs")["pass"])
    st = _fake_state()
    st["facial"]["features"]["eyes"] = False
    _, c_proxy = assemble(st, opts())
    _, c_none = assemble(st, opts("--eyes", "none"))
    check("eyes dropped fails with --eyes proxy, not with --eyes none", c_proxy == 2 and c_none == 0)
    st = _fake_state()
    st["facial"].update(ok=False, cancelled=True)
    rep, code = assemble(st, opts())
    check("a cancelled face: smart.facial fails alone, Go! and the refs pass",
          code == 2 and [g["name"] for g in rep["gates"] if not g["pass"]] == ["smart.facial"])
    st = _fake_state()
    del st["refs_local"]["jaw_ref.x"]
    rep, code = assemble(st, opts())
    check("a face that passed but no jaw ref: smart.refs fails", code == 2 and gate(rep, "smart.refs")["missing"]
          == ["jaw_ref.x"])
    # 5. Go!, the AI files, errors
    rep, code = assemble(_fake_state(go={"rig": "rig", "has_match_to_rig_key": False}), opts())
    check("no has_match_to_rig key: smart.go fails, exit 2", code == 2 and not gate(rep, "smart.go")["pass"])
    st = _fake_state(kp_files=[], body_loc={}, finger_loc={}, finger_tries=[], facial=None, go=None,
                     rig_matrix_world=None, refs_local={})
    rep, code = assemble(st, opts())
    check("AI blocked (no keypoints written): every gate fails, exit 2, verdict failed",
          code == 2 and not any(g["pass"] for g in rep["gates"]) and rep["verdict"] == "failed")
    rep, code = assemble(_fake_state(ai_version=1.17), opts())
    check("AI files older than 1.20 fail smart.ai_files", code == 2 and not gate(rep, "smart.ai_files")["pass"])
    rep, code = assemble(_fake_state(error="timeout: 600 s"), opts())
    check("a timeout is an error: exit 1, verdict harness, pass false", code == 1 and rep["verdict"] == "harness"
          and rep["pass"] is False and rep["error"].startswith("timeout"))
    rep, code = assemble({"refused": "operators not registered: ['id.go_detect']", "steps": []}, opts())
    check("a missing operator refuses: exit 1, the report still has its gates",
          code == 1 and rep["refused"].startswith("operators") and len(rep["gates"]) == 6)
    check("only the add-on's own pictures and keypoint files count as scratch in the inference folder",
          all(is_ai_scratch(n) for n in ("front1.jpg", "side3_kp.py", "hand2_l.jpg", "hand1_r_kp.py", "facial4_kp.py"))
          and not any(is_ai_scratch(n) for n in ("inference_front", "front_model.pth", "photo.jpg", "notes_kp.py",
                                                 "front.jpg", "LICENSE.txt")))
    # 6. the probe
    pr, pc = probe_report({"module": "bl_ext.user_default.auto_rig_pro", "operators_missing": [], "ai_version": 1.21})
    pn, nc = probe_report({"module": "bl_ext.user_default.auto_rig_pro", "operators_missing": [], "ai_version": None})
    pa, ac = probe_report({"module": None, "operators_missing": list(OPERATORS), "ai_version": None})
    check("probe: ready with the add-on, its operators and AI >= 1.20 (exit 0); else not ready (exit 2)",
          pc == 0 and pr["ready"] and nc == 2 and not pn["ready"] and ac == 2 and not pa["ready"])
    ok = all(c["pass"] for c in checks)
    print(json.dumps({"tool": "arp_smart", "selftest": "pass" if ok else "fail", "checks": len(checks),
                      "failed": [c for c in checks if not c["pass"]]}))
    return 0 if ok else 1


def in_blender() -> bool:
    try:
        import bpy  # noqa: F401
        return hasattr(bpy, "app") and bool(getattr(bpy.app, "binary_path", ""))
    except ImportError:
        return False


def main() -> None:
    blender = in_blender()
    argv = sys.argv[sys.argv.index("--") + 1:] if (blender and "--" in sys.argv) else \
        ([] if blender else sys.argv[1:])
    if argv[:1] == ["selftest"]:
        argv = ["--selftest", *argv[1:]]
    a = parser().parse_args(argv)
    if a.selftest:
        sys.exit(selftest())
    if eye_args_error(a):
        parser().error(eye_args_error(a))
    if not blender:
        print(json.dumps({"tool": "arp_smart", "pass": False, "ok": False, "exit_code": 1,
                          "refused": "run inside a windowed Blender: blender FILE.blend -P arp_smart.py -- "
                                     "--mesh NAME --out NAME.smart.json (or --selftest here)"}))
        sys.exit(1)
    run_blender(a)


if __name__ == "__main__":
    main()
