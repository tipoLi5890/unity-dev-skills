#!/usr/bin/env python3
"""clip_metrics.py — how far a character's playback of a clip departs from a reference body.

The reference is the same clip on the body it was captured or authored for (a purchased pack's own
body, the source rig), sampled in the same engine at the same frames. Comparing against it
measures what the route added (fit, Humanoid, a per-clip bake), not what the mocap already had.

usage:
    clip_metrics.py SAMPLES.json [--out REPORT.json] [--slide-p95 0.015] [--slide-max 0.03]
                    [--limb-p95 2.0] [--h-max 0.04] [--v-max 0.15] [--min-frames 3]
    clip_metrics.py selftest            (or --selftest)

SAMPLES.json (schema "clip-samples/1"), metres, Z up, one row per frame:
    {"schema": "clip-samples/1", "clip": "forehand", "fps": 30,
     "character": {"<role>": [[x, y, z], ...], ...},
     "reference": {"<role>": [[x, y, z], ...], ...}}
Roles, by function, never by a skeleton's own bone names (map them when you sample):
    foot_l foot_r toe_l toe_r             required: the foot point is the midpoint of foot and toe
    sole_l sole_r                         optional per-frame sole heights [z, ...]; default: the
                                          lower of the foot and toe joints' z
    upper_arm_l forearm_l hand_l (and _r) optional: limb direction and arm pose error
    thigh_l shin_l (and _r)               optional: limb direction (shin to foot is the lower leg)
Both bodies are in one space and one scale (scale the reference by the character's display scale
first). Lengths may differ: the arm pose error divides by each body's own arm length.

Definitions:
- plant: sole under --h-max above the clip's floor (the reference's lowest sole over the clip)
  and horizontal foot speed under --v-max m/s, for at least --min-frames frames, found on the
  REFERENCE; the character is judged inside the same frames.
- slide: inside a plant, the horizontal distance of the foot point from its position on the
  plant's first frame. Reported for both bodies; NOT gated (mocap drifts on its own).
- added slide: |(c(t) - c(start)) - (r(t) - r(start))| inside each plant: the slide the route
  added. Gated: p95 <= --slide-p95 and max <= --slide-max.
- limb direction error: the angle between the character's and the reference's segment direction,
  per frame, over upper arm, forearm, thigh and lower leg. Gated: p95 <= --limb-p95 degrees.
- arm pose error: |(hand - upper_arm)/arm_len| difference in % of the arm, proportion-free.

Prints one JSON report (also to --out): per-metric p50, p95, max, n; plants; gates; ok.
Exit codes: 0 every gate passed; 1 a gate failed; 2 refused input (unreadable file, wrong schema,
a required role missing, frame counts that differ, a non-finite value). Requires numpy.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

SCHEMA = "clip-samples/1"
SIDES = ("l", "r")
LIMBS = [("upper_arm", "forearm"), ("forearm", "hand"), ("thigh", "shin"), ("shin", "foot")]


class Refused(Exception):
    pass


def summary(x) -> dict:
    x = np.asarray(x, float)
    if not x.size:
        return {"p50": 0.0, "p95": 0.0, "max": 0.0, "n": 0}
    return {"p50": float(np.median(x)), "p95": float(np.percentile(x, 95)),
            "max": float(x.max()), "n": int(x.size)}


def speed_xy(xy: np.ndarray, fps: float) -> np.ndarray:
    if len(xy) < 2:
        return np.zeros(len(xy))
    v = np.linalg.norm(np.diff(xy, axis=0), axis=1) * fps
    return np.concatenate([[v[0]], v])


def plants(sole, xy, fps, h_max, v_max, min_frames) -> list:
    on = (np.asarray(sole) < h_max) & (speed_xy(xy, fps) < v_max)
    out, start = [], None
    for i, flag in enumerate(on):
        if flag and start is None:
            start = i
        if start is not None and (not flag or i == len(on) - 1):
            end = i if flag else i - 1
            if end - start + 1 >= min_frames:
                out.append((start, end))
            start = None
    return out


def slide(xy, ranges) -> np.ndarray:
    d = [np.linalg.norm(xy[a:b + 1] - xy[a], axis=1) for a, b in ranges]
    return np.concatenate(d) if d else np.zeros(0)


def added_slide(xy_c, xy_r, ranges) -> np.ndarray:
    d = [np.linalg.norm((xy_c[a:b + 1] - xy_c[a]) - (xy_r[a:b + 1] - xy_r[a]), axis=1)
         for a, b in ranges]
    return np.concatenate(d) if d else np.zeros(0)


def angle_between(u, w) -> np.ndarray:
    cos = np.sum(u * w, axis=1) / (np.linalg.norm(u, axis=1) * np.linalg.norm(w, axis=1))
    return np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))


def load(doc: dict) -> tuple:
    if doc.get("schema") != SCHEMA:
        raise Refused(f"schema is {doc.get('schema')!r}, expected {SCHEMA!r}")
    fps = doc.get("fps")
    if not isinstance(fps, (int, float)) or fps <= 0:
        raise Refused("fps missing or not positive")
    bodies = {}
    n = None
    for who in ("character", "reference"):
        raw = doc.get(who)
        if not isinstance(raw, dict):
            raise Refused(f"{who} missing")
        body = {}
        for role, rows in raw.items():
            a = np.asarray(rows, float)
            if role.startswith("sole_"):
                if a.ndim != 1:
                    raise Refused(f"{who}.{role} must be a list of heights")
            elif a.ndim != 2 or a.shape[1] != 3:
                raise Refused(f"{who}.{role} must be rows of [x, y, z]")
            if not np.all(np.isfinite(a)):
                raise Refused(f"{who}.{role} has a non-finite value")
            if n is None:
                n = len(a)
            if len(a) != n:
                raise Refused(f"{who}.{role} has {len(a)} frames, expected {n}")
            body[role] = a
        for s in SIDES:
            for need in (f"foot_{s}", f"toe_{s}"):
                if need not in body:
                    raise Refused(f"{who}.{need} missing (required)")
            if f"sole_{s}" not in body:
                body[f"sole_{s}"] = np.minimum(body[f"foot_{s}"][:, 2], body[f"toe_{s}"][:, 2])
        bodies[who] = body
    if n is None or n < 2:
        raise Refused("fewer than 2 frames")
    return float(fps), bodies["character"], bodies["reference"]


def measure(doc: dict, a) -> dict:
    fps, c, r = load(doc)
    floor = float(min(r["sole_l"].min(), r["sole_r"].min()))
    out = {"clip": doc.get("clip"), "frames": int(len(c["foot_l"])), "fps": fps,
           "clip_floor_m": floor}
    sl_c, sl_r, sl_add, n_plants = [], [], [], 0
    for s in SIDES:
        foot_r = ((r[f"foot_{s}"] + r[f"toe_{s}"]) / 2)[:, :2]
        foot_c = ((c[f"foot_{s}"] + c[f"toe_{s}"]) / 2)[:, :2]
        rng = plants(r[f"sole_{s}"] - floor, foot_r, fps, a.h_max, a.v_max, a.min_frames)
        n_plants += len(rng)
        sl_r.append(slide(foot_r, rng))
        sl_c.append(slide(foot_c, rng))
        sl_add.append(added_slide(foot_c, foot_r, rng))
    out["plants"] = n_plants
    out["foot_slide_m"] = summary(np.concatenate(sl_c))
    out["foot_slide_reference_m"] = summary(np.concatenate(sl_r))
    out["foot_slide_added_m"] = summary(np.concatenate(sl_add))
    errs = []
    for s in SIDES:
        for p, q in LIMBS:
            pa, qa = f"{p}_{s}", f"{q}_{s}"
            if all(k in c and k in r for k in (pa, qa)):
                errs.append(angle_between(c[qa] - c[pa], r[qa] - r[pa]))
    out["limb_direction_error_deg"] = summary(np.concatenate(errs) if errs else [])
    arm = []
    for s in SIDES:
        ks = [f"upper_arm_{s}", f"forearm_{s}", f"hand_{s}"]
        if all(k in c and k in r for k in ks):
            def rel(b):
                ln = (np.linalg.norm(b[ks[1]] - b[ks[0]], axis=1) +
                      np.linalg.norm(b[ks[2]] - b[ks[1]], axis=1))
                return (b[ks[2]] - b[ks[0]]) / ln[:, None]
            arm.append(100 * np.linalg.norm(rel(c) - rel(r), axis=1))
    out["arm_pose_error_pct"] = summary(np.concatenate(arm) if arm else [])
    gates = [
        {"name": "added_slide_p95_m", "value": out["foot_slide_added_m"]["p95"],
         "limit": f"<= {a.slide_p95}", "ok": out["foot_slide_added_m"]["p95"] <= a.slide_p95},
        {"name": "added_slide_max_m", "value": out["foot_slide_added_m"]["max"],
         "limit": f"<= {a.slide_max}", "ok": out["foot_slide_added_m"]["max"] <= a.slide_max},
    ]
    if errs:
        v = out["limb_direction_error_deg"]["p95"]
        gates.append({"name": "limb_direction_p95_deg", "value": v,
                      "limit": f"<= {a.limb_p95}", "ok": v <= a.limb_p95})
    out["gates"] = gates
    out["ok"] = all(g["ok"] for g in gates)
    return out


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clip_metrics.py", description=__doc__.split("\n")[0])
    p.add_argument("samples")
    p.add_argument("--out")
    p.add_argument("--slide-p95", type=float, default=0.015)
    p.add_argument("--slide-max", type=float, default=0.03)
    p.add_argument("--limb-p95", type=float, default=2.0)
    p.add_argument("--h-max", type=float, default=0.04)
    p.add_argument("--v-max", type=float, default=0.15)
    p.add_argument("--min-frames", type=int, default=3)
    return p


def run(argv) -> tuple:
    a = parser().parse_args(argv)
    try:
        doc = json.loads(Path(a.samples).read_text(encoding="utf-8"))
        rep = measure(doc, a)
    except (OSError, ValueError, Refused) as e:
        rep = {"ok": False, "refused": str(e)}
        code = 2
    else:
        code = 0 if rep["ok"] else 1
    text = json.dumps(rep, indent=1)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    return code, rep, text


# ------------------------------------------------------------------------------------ selftest
def _walk(n: int, drift: float, rot_forearm_deg: float = 0.0) -> dict:
    """Two planted feet that drift `drift` m over each plant, swinging alternately; one arm."""
    body = {}
    for k, s in enumerate(SIDES):
        x = np.full(n, 0.1 if s == "l" else -0.1)
        y = np.zeros(n)
        z = np.zeros(n)
        swing = ((np.arange(n) // 10) % 2) == k          # 10 frames planted, 10 swinging
        y += np.cumsum(np.where(swing, 0.06, drift / 10))   # fast in swing, slow drift in plant
        z += np.where(swing, 0.12, 0.0)
        body[f"foot_{s}"] = np.stack([x, y, z + 0.02], 1).tolist()
        body[f"toe_{s}"] = np.stack([x, y + 0.15, z], 1).tolist()
    sh = np.stack([np.full(n, 0.2), np.zeros(n), np.full(n, 1.4)], 1)
    el = sh + [0.0, 0.0, -0.3]
    a = np.radians(rot_forearm_deg)
    wr = el + [0.25 * np.sin(a), 0.0, -0.25 * np.cos(a)]
    body.update({"upper_arm_r": sh.tolist(), "forearm_r": el.tolist(), "hand_r": wr.tolist()})
    return body


def selftest() -> int:
    checks, failed = 0, []

    def check(name, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failed.append(name)

    fps = 30.0
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        # 1. the reference drifts 3 cm per plant: absolute slide fails 1.5 cm, added slide is 0
        doc = {"schema": SCHEMA, "clip": "walk", "fps": fps,
               "character": _walk(80, 0.03), "reference": _walk(80, 0.03)}
        p.write_text(json.dumps(doc))
        code, rep, _ = run([str(p)])
        check("drifting reference: exit 0", code == 0)
        check("plants found", rep.get("plants", 0) >= 4)
        check("absolute slide over 1.5 cm", rep["foot_slide_m"]["max"] > 0.015)
        check("added slide ~0", rep["foot_slide_added_m"]["max"] < 1e-9)
        # 2. the character drifts 6 cm per plant where the reference drifts 1 cm: added ~5 cm fails
        doc["character"] = _walk(80, 0.06)
        doc["reference"] = _walk(80, 0.01)
        p.write_text(json.dumps(doc))
        code, rep, _ = run([str(p)])
        check("added slide fails: exit 1", code == 1)
        mx = rep["foot_slide_added_m"]["max"]
        check("added slide max = 9/10 of the 5 cm extra drift", abs(mx - 0.045) < 1e-6)
        # 3. a forearm rotated by 10 degrees reads 10 degrees, and fails a 2-degree gate
        doc["character"] = _walk(80, 0.01, rot_forearm_deg=10.0)
        p.write_text(json.dumps(doc))
        code, rep, _ = run([str(p)])
        check("limb error = 10 deg", abs(rep["limb_direction_error_deg"]["max"] - 10.0) < 1e-6)
        check("limb gate fails: exit 1", code == 1)
        check("arm pose error > 0", rep["arm_pose_error_pct"]["max"] > 1.0)
        # 4. refused inputs
        bad = dict(doc, character={k: v[:-1] for k, v in doc["character"].items()})
        p.write_text(json.dumps(bad))
        check("frame mismatch: exit 2", run([str(p)])[0] == 2)
        bad = dict(doc, character={k: v for k, v in doc["character"].items() if k != "toe_l"})
        p.write_text(json.dumps(bad))
        check("missing toe_l: exit 2", run([str(p)])[0] == 2)
        p.write_text(json.dumps(dict(doc, schema="other")))
        check("wrong schema: exit 2", run([str(p)])[0] == 2)
        check("unreadable file: exit 2", run([str(Path(d) / "none.json")])[0] == 2)
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": checks,
                      "failed": failed}))
    return 0 if not failed else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["selftest"], ["--selftest"]):
        return selftest()
    code, _, text = run(argv)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
