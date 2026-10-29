#!/usr/bin/env python3
"""contact_bake.py — lock each foot where the clip says it is planted and bake the legs, offline.

A two-bone IK on each leg (thigh, shin) moves the ankle so the foot point holds still through every
plant; the foot keeps its world rotation, the hips and everything above them are not touched. The
same numpy core runs on a BVH (host, numpy) or on an action in Blender (headless).

usage:
    contact_bake.py CLIP.bvh --out BAKED.bvh [--contacts C.json|C.npz] [--legs auto|contract|mixamo|
                    arp-ue|l=THIGH,SHIN,FOOT[,TOE] --legs r=...] [--up y|z] [--unit-m 1.0]
                    [--floor 0.0|auto] [--rig-info RIG_INFO.json|SAMPLES.json] [--blend 3]
                    [--contacts-offset 0] [--readings SAMPLES.json] [--readings-offset 0]
                    [--samples-out S.npz] [--report R.json] [--allow-no-plants] [gate options]
    blender -b RIG.blend -P contact_bake.py -- --armature RunnerRig [--action RunnerWalk]
                    [--frame-range A B] --out BAKED.blend [the options above]
    contact_bake.py --selftest
    blender -b --factory-startup -P contact_bake.py -- --selftest-blender

Plants. With --contacts (a "contacts/1" JSON {"l": [...], "r": [...]}, a JSON with a
"contacts" object of the same shape, or an NPZ `contacts` (F, 2) l, r), a plant is a run of at
least 3 frames whose probability is >= 0.5. Without, it is the one plant definition of
motion_metrics.py (sole under 4 cm, ground-relative speed under 0.15 m/s, 3 frames), imported from
skills/blender-retarget/scripts. Contact index 0 is the first baked frame (--contacts-offset N
shifts it).

Sole offsets. A foot joint stands above its sole (an ankle about 7 cm at rest), so the sole height is
each foot joint's height minus its rest height, the lowest of them. --rig-info reads those rest
heights from a rig_info.json (twocam.ground) or a samples file (sole_offsets); joints are matched by
name (a namespace prefix ignored), and the ones used are reported. A rig_info.json's
twocam.contract_names ({rig bone: contract name}, written by the two-camera prepare stage) maps the
contract onto a rig whose bones carry other names (Auto-Rig Pro's thigh_stretch.l, leg_stretch.l,
foot.l, toes_01.l), for --legs contract and for the contract-named ground offsets. The plant detector, the lock
height, contact_height_m and penetration all read this sole, and --samples-out carries the offsets
on to motion_metrics. Without them the sole is the lowest joint.

The lock. The foot point is the mean of the foot and toe joints (motion_metrics' foot point). In a
plant it is held at the plant's median horizontal position; the ankle target is the ankle moved by
that offset, raised by any depth the sole has under the floor. The offset fades in and out over
--blend frames on each side (smoothstep). The knee stays in the plane the leg already bends in
(the clip's median knee direction when the leg is straight). The leg chain is solved
analytically; a target out of reach is clamped and reported.

BVH mode: rotations are written back to the thigh, shin and foot channels in each joint's own
channel order; positions are not written. --up names the file's up axis (y for a BVH from
Blender's exporter), --unit-m the metres per file unit (0.01 for centimetres).
Blender mode: the action is sampled through the depsgraph (pose bone world matrices), the new
rotations are keyed on every frame of the range in each bone's rotation mode, the result is
sampled again for the report, and the file is saved to --out (never over the opened file unless
--out names it). Leg bones with constraints or without full rotation inheritance are warned about.

Readings. --readings takes a samples file with reading_joints / reading_names (the two-camera
capture's samples.json, or baked samples that carry them) and writes them into --samples-out under
this skeleton's names (by name, or through contract_names), so motion_metrics still tells a pop the
source has (pops_in_source) from one the bake made. A joint with no reading of its own that lies on
the segment between two read joints in every frame (a twist bone) is read at its place along it.
Reading index 0 is the first baked frame (--readings-offset N shifts it).

--sample-only bakes nothing: it measures the clip as it is, gates it the same way, and writes
--samples-out (the loop-cut step samples the cut range with it). Its exit code is the gates'.

Gates (exit 2 when one fails):
  plants_found        the plants on both feet together (the report's `plants_found`, beside
                      `plants_per_foot`, as motion_metrics reports them) at least 1 (--allow-no-plants passes a
                      clip with none)
  contact_height_m    with --contacts: in every plant the median sole height is under
                      --contact-h-max (0.08 m); contacts that disagree with the pose fail. Not a
                      second plant height: the contacts define the plant, and this only checks
                      that the pose agrees, loosely, since a model's contact also spans heel
                      strike and toe-off, when the sole is above the detector's 4 cm
  reach_m             the largest distance a clamped ankle stays short of its target, <= --reach-tol (0.01 m)
  foot_slide_p95_m    after the bake, motion_metrics' slide p95 <= --slide-p95 (0.015 m)
  foot_slide_max_m    and max <= --slide-max (0.03 m)
  penetration_max_m   after the bake, <= --penetration-max (0.01 m) in plants
The report has slide before and after, plants per side, the frames changed, and `outside_change_deg`
(the largest rotation change outside every plant and blend: round-off only, since those frames
are written back unchanged).
Prints one JSON report. Exit codes: 0 pass; 2 a gate failed; 1 refused input (unreadable file, leg
bones not found, contacts or readings shorter than the clip, motion_metrics.py not found) or a failed
selftest.
Requires numpy (and Blender for the Blender mode).
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
METRICS_DIR = HERE.parents[1] / "blender-retarget" / "scripts"

SIDES = ("l", "r")
LEG_PRESETS = {
    "contract": {"l": ["UpperLeg.L", "LowerLeg.L", "Foot.L", "Toes.L"], "r": ["UpperLeg.R", "LowerLeg.R", "Foot.R", "Toes.R"]},
    "mixamo": {"l": ["LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase"], "r": ["RightUpLeg", "RightLeg", "RightFoot", "RightToeBase"]},
    "arp-ue": {"l": ["thigh_l", "calf_l", "foot_l", "ball_l"], "r": ["thigh_r", "calf_r", "foot_r", "ball_r"]},
}
CONTACT_H_MAX = 0.08
REACH_TOL = 0.01
BLEND = 3
Y_TO_Z = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])   # (x, y, z) -> (x, -z, y)


class Refused(Exception):
    pass


def metrics():
    if str(METRICS_DIR) not in sys.path:
        sys.path.insert(0, str(METRICS_DIR))
    try:
        import motion_metrics as mm
    except ImportError as e:
        raise Refused(f"motion_metrics.py not found in {METRICS_DIR} ({e}): keep humanoid-motion beside "
                      "blender-retarget") from None
    return mm


def gate(name, value, limit, ok) -> dict:
    return {"name": name, "value": value, "limit": limit, "ok": bool(ok)}


def _r(x, d=5):
    return None if x is None else round(float(x), d)


def _strip(n: str) -> str:
    return n.split(":")[-1]


def read_rig_info(path: str | None):
    """The --rig-info document (a rig_info.json or a samples file), or None without one."""
    if not path:
        return None
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refused(f"cannot read sole offsets {path}: {e}") from None
    if not isinstance(doc, dict):
        raise Refused(f"{path}: not a JSON object")
    return doc


def contract_of(doc) -> dict:
    """{rig bone: contract name} from a rig_info.json's twocam.contract_names (prepare_rig.py writes it for a rig
    whose bones carry other names, e.g. Auto-Rig Pro's thigh_stretch.l for UpperLeg.L); {} otherwise."""
    m = ((doc or {}).get("twocam") or {}).get("contract_names") if isinstance(doc, dict) else None
    return {str(k): str(v) for k, v in m.items()} if isinstance(m, dict) else {}


def _index(names: list, alias: dict | None = None) -> dict:
    by = {}
    for i, n in enumerate(names):
        by.setdefault(n, i)
        by.setdefault(_strip(n), i)
    for i, n in enumerate(names):   # the contract names a rig_info maps onto the rig's own bones
        c = (alias or {}).get(n, (alias or {}).get(_strip(n)))
        if c:
            by.setdefault(c, i)
    return by


def resolve_legs(names: list, spec: list | None, alias: dict | None = None) -> dict:
    """{side: [thigh, shin, foot, toe|None] as indices}. alias {rig bone: contract name} lets the contract preset
    (and l=/r= lists in contract names) find a rig whose bones carry other names."""
    by = _index(names, alias)
    spec = spec or ["auto"]
    if len(spec) == 1 and "=" not in spec[0]:
        key = spec[0]
        presets = LEG_PRESETS if key == "auto" else {key: LEG_PRESETS.get(key)}
        if None in presets.values():
            raise Refused(f"unknown --legs preset {key!r}: auto, {', '.join(LEG_PRESETS)}, or l=THIGH,SHIN,FOOT[,TOE]")
        for pname, p in presets.items():
            if all(n in by for s in SIDES for n in p[s][:3]):
                return {s: [by[n] for n in p[s][:3]] + [by.get(p[s][3])] for s in SIDES}, pname
        hint = "" if alias or key not in ("auto", "contract") else (
            "; a rig whose bones carry other names (Auto-Rig Pro's thigh_stretch.l) needs --rig-info with "
            "twocam.contract_names (the two-camera prepare stage writes it), and this run has none")
        raise Refused(f"no leg chain found with --legs {key} (tried {', '.join(presets)}){hint}; or name them with "
                      "--legs l=THIGH,SHIN,FOOT,TOE --legs r=...")
    out = {}
    for item in spec:
        side, _, lst = item.partition("=")
        parts = [x for x in lst.split(",") if x]
        if side not in SIDES or len(parts) not in (3, 4):
            raise Refused(f"--legs {item!r}: use l=THIGH,SHIN,FOOT[,TOE]")
        miss = [n for n in parts if n not in by]
        if miss:
            raise Refused(f"--legs {item!r}: not in the skeleton: {miss}")
        out[side] = [by[n] for n in parts[:3]] + [by[parts[3]] if len(parts) == 4 else None]
    if set(out) != set(SIDES):
        raise Refused("--legs needs both l= and r=")
    return out, "custom"


def load_contacts(path: str, n: int, offset: int = 0) -> dict:
    p = Path(path)
    try:
        if p.suffix.lower() == ".npz":
            with np.load(p, allow_pickle=False) as z:
                c = np.asarray(z["contacts"], float)
            doc = {"l": c[:, 0], "r": c[:, 1]}
        else:
            j = json.loads(p.read_text())
            doc = j.get("contacts", j) if isinstance(j, dict) else None
            if not isinstance(doc, dict) or not all(s in doc for s in SIDES):
                raise Refused(f"{path}: no l/r contact lists")
            doc = {s: np.asarray(doc[s], float) for s in SIDES}
    except (OSError, ValueError, KeyError) as e:
        raise Refused(f"cannot read contacts {path}: {e}") from None
    out = {}
    for s in SIDES:
        v = doc[s][offset:offset + n]
        if len(v) < n:
            raise Refused(f"contacts {path}: {len(doc[s])} values for side {s}, the clip needs {n} from offset {offset}")
        if not np.all(np.isfinite(v)):
            raise Refused(f"contacts {path}: non-finite value")
        out[s] = v
    return out


def load_offsets(path: str | None, names: list, legs: dict, doc=None, alias: dict | None = None) -> dict:
    """{joint index: rest height over the sole} for the legs' foot and toe joints, from a rig_info.json
    (twocam.ground, in contract names: matched through alias {rig bone: contract name}) or a samples file
    (sole_offsets)."""
    if not path:
        return {}
    if doc is None:
        doc = read_rig_info(path)
    src = doc.get("sole_offsets") if isinstance(doc, dict) else None
    if src is None and isinstance(doc, dict):
        src = (doc.get("twocam") or {}).get("ground")
    if not isinstance(src, dict):
        raise Refused(f"{path}: no twocam.ground (rig_info.json) or sole_offsets (samples file)")
    by = {_strip(k): v for k, v in src.items()}
    out = {}
    alias = alias or {}
    for s in SIDES:
        for j in legs[s][2:]:
            if j is None:
                continue
            key = next((k for k in (_strip(names[j]), alias.get(names[j]), alias.get(_strip(names[j]))) if k in by),
                       None)
            if key is not None:
                h = by[key]
                if not isinstance(h, (int, float)) or not math.isfinite(h):
                    raise Refused(f"{path}: sole offset of {names[j]} is not a number")
                out[j] = float(h)
    if not out:
        raise Refused(f"{path}: no sole offset names a foot or toe joint of the legs "
                      f"({', '.join(names[j] for s in SIDES for j in legs[s][2:] if j is not None)})")
    return out


def load_readings(path: str, n: int, offset: int, names: list, P, alias: dict | None = None,
                  parents: list | None = None) -> tuple:
    """The joints read straight from the source (a motion-samples file's reading_joints / reading_names, e.g. the
    two-camera capture's samples.json, or a samples .npz carrying them), cut to the n baked frames from `offset`
    and put on this skeleton's joints, so motion_metrics keeps telling a pop in the source from one the bake made.
    A joint is matched by name, a namespace prefix ignored, or through alias {rig bone: contract name}. A joint
    with no reading of its own (a twist bone of the rig) gets one when its positions P (F, J, 3) lie on the segment
    from its nearest matched ancestor to one of that ancestor's matched descendants in every frame (within 1 cm,
    the same fraction along it): the readings of those two ends interpolated at that fraction.
    Returns ({joint index: (n, 3)}, report)."""
    p = Path(path)
    try:
        if p.suffix.lower() == ".npz":
            with np.load(p, allow_pickle=False) as z:
                doc = json.loads(str(z["meta"])) if "meta" in z.files else {}
                if "reading_joints" in z.files:
                    doc["reading_joints"] = np.asarray(z["reading_joints"], float)
                    doc["reading_names"] = [str(x) for x in z["reading_names"]]
        else:
            doc = json.loads(p.read_text(encoding="utf-8"))
        R = np.asarray(doc["reading_joints"], float)
        rn = [str(x) for x in doc["reading_names"]]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise Refused(f"cannot read readings {path}: {type(e).__name__}: {e} (a samples file with reading_joints "
                      "and reading_names)") from None
    if R.ndim != 3 or R.shape[1:] != (len(rn), 3):
        raise Refused(f"readings {path}: reading_joints must be (frames, {len(rn)} reading_names, 3), got {list(R.shape)}")
    if str(doc.get("up", "z")).lower() == "y":
        R = R[..., [0, 2, 1]] * [1, -1, 1]
    R = R[offset:offset + n]
    if len(R) < n:
        raise Refused(f"readings {path}: {len(R) + offset} frames, the clip needs {n} from offset {offset}")
    if not np.all(np.isfinite(R)):
        raise Refused(f"readings {path}: non-finite value")
    ri = {}
    for k, nm in enumerate(rn):
        ri.setdefault(nm, k)
        ri.setdefault(_strip(nm), k)
    alias = alias or {}
    src = {}
    for j, nm in enumerate(names):
        for key in (nm, _strip(nm), alias.get(nm), alias.get(_strip(nm))):
            if key is not None and key in ri:
                src[j] = ri[key]
                break
    out = {j: R[:, k] for j, k in src.items()}
    between = {}
    if parents is not None:
        def anc(j):
            q = parents[j]
            while q >= 0 and q not in src:
                q = parents[q]
            return q
        for j in range(len(names)):
            a = anc(j)
            if j in src or a < 0:
                continue
            best = None
            for b in src:
                if b == a or anc(b) != a:
                    continue
                d = P[:, b] - P[:, a]
                L2 = np.sum(d * d, axis=1)
                if np.median(L2) < 1e-6:
                    continue
                t = np.sum((P[:, j] - P[:, a]) * d, axis=1) / np.maximum(L2, 1e-12)
                res = np.linalg.norm(P[:, j] - (P[:, a] + t[:, None] * d), axis=1)
                tm = float(np.median(t))
                if res.max() <= 0.01 and float(np.abs(t - tm).max()) <= 0.02 and -0.05 <= tm <= 1.05 and \
                        (best is None or res.max() < best[0]):
                    best = (float(res.max()), b, tm)
            if best is not None:
                _, b, tm = best
                out[j] = R[:, src[a]] + tm * (R[:, src[b]] - R[:, src[a]])
                between[names[j]] = [names[a], names[b], round(tm, 4)]
    rep = {"file": str(path), "offset": offset, "matched": len(src), "between": between,
           "unread": len(names) - len(out)}
    return out, rep


# ----------------------------------------------------------------------------- the core

def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _frame(t, n):
    t = t / np.maximum(np.linalg.norm(t, axis=-1, keepdims=True), 1e-12)
    n = n - np.sum(n * t, axis=-1, keepdims=True) * t
    n = n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-12)
    return np.stack([t, n, np.cross(t, n)], axis=-1)


def foot_point(P, legs, s, offsets=None):
    """The foot point (mean of the foot and toe joints) and the sole: the lowest of their heights, each
    minus its rest height over the sole when `offsets` {joint index: m} names it."""
    th, sh, ft, toe = legs[s]
    js = [ft] + ([toe] if toe is not None else [])
    off = np.array([(offsets or {}).get(j, 0.0) for j in js])
    return np.mean(P[:, js], axis=1), np.min(P[:, js, 2] - off, axis=1)


def bake(Wr, Wp, legs, fps, contacts=None, floor="0.0", blend=BLEND, a=None, offsets=None):
    """Wr (F,J,3,3), Wp (F,J,3): world rotations and positions, metres, Z up; offsets {joint: m}.
    Returns new world rotations for the leg bones {joint: (F,3,3)} and the report pieces."""
    mm = metrics()
    import bvh_io
    F = Wp.shape[0]
    h_max = getattr(a, "h_max", mm.PLANT_H_MAX)
    v_max = getattr(a, "v_max", mm.PLANT_V_MAX)
    min_frames = getattr(a, "min_frames", mm.PLANT_MIN_FRAMES)

    def foot_pts(P, s):
        return foot_point(P, legs, s, offsets)

    soles = {s: foot_pts(Wp, s)[1] for s in SIDES}
    fl = float(np.percentile(np.concatenate(list(soles.values())), 5)) if floor == "auto" else float(floor)

    new_rot, info, weights = {}, {}, {}
    for s in SIDES:
        th, sh, ft, toe = legs[s]
        fp, sole = foot_pts(Wp, s)
        if contacts is not None:
            ranges = mm.runs(contacts[s] >= mm.CONTACT_MIN, min_frames)
            src = "contacts"
        else:
            ranges = mm.plants(sole - fl, fp[:, :2], fps, h_max, v_max, min_frames)
            src = "detector"
        # the per-frame offset of the foot point, faded in and out
        off = np.zeros((F, 2))
        w = np.zeros(F)
        heights = []
        for (b, e) in ranges:
            lock = np.median(fp[b:e + 1, :2], axis=0)
            heights.append(float(np.median(sole[b:e + 1] - fl)))
            for f in range(max(0, b - blend), min(F, e + blend + 1)):
                if f < b:
                    wf, ref = _smooth((f - (b - blend - 1)) / (blend + 1)), b
                elif f > e:
                    wf, ref = _smooth(((e + blend + 1) - f) / (blend + 1)), e
                else:
                    wf, ref = 1.0, f
                if wf > w[f]:
                    w[f] = wf
                    off[f] = (lock - fp[ref, :2]) if f != ref else (lock - fp[f, :2])
        H, K, A = Wp[:, th], Wp[:, sh], Wp[:, ft]
        target = A.copy()
        target[:, :2] += off * w[:, None]
        lift = np.maximum(0.0, fl - sole)
        inplant = np.zeros(F, bool)
        for b, e in ranges:
            inplant[b:e + 1] = True
        target[:, 2] += np.where(w > 0, lift * np.maximum(w, inplant), 0.0)

        l1 = np.linalg.norm(K - H, axis=1)
        l2 = np.linalg.norm(A - K, axis=1)
        dv = target - H
        d = np.linalg.norm(dv, axis=1)
        dmax = (l1 + l2) * 0.9999
        dmin = np.abs(l1 - l2) * 1.0001 + 1e-6
        dc = np.clip(d, dmin, dmax)
        short = np.where(w > 0, np.abs(d - dc), 0.0)
        u = dv / np.maximum(d, 1e-12)[:, None]
        # the knee's side: its offset from the hip-ankle line, the clip's median when straight
        u0 = (A - H) / np.maximum(np.linalg.norm(A - H, axis=1), 1e-12)[:, None]
        k0 = (K - H) - np.sum((K - H) * u0, axis=1)[:, None] * u0
        kn = np.linalg.norm(k0, axis=1)
        good = kn > 0.02 * l1
        fallback = np.median(k0[good] / kn[good, None], axis=0) if np.any(good) else np.array([0, -1.0, 0])
        pole = np.where(good[:, None], k0 / np.maximum(kn, 1e-12)[:, None], fallback)
        pole = pole - np.sum(pole * u, axis=1)[:, None] * u
        pole /= np.maximum(np.linalg.norm(pole, axis=1), 1e-12)[:, None]
        ca = (l1 ** 2 - l2 ** 2 + dc ** 2) / (2 * dc)
        hh = np.sqrt(np.maximum(l1 ** 2 - ca ** 2, 0.0))
        K2 = H + ca[:, None] * u + hh[:, None] * pole
        A2 = H + dc[:, None] * u
        n0 = np.cross(K - H, A - K)
        n1 = np.cross(K2 - H, A2 - K2)
        # a straight leg has no bend plane: use the pole's normal
        n0 = np.where((np.linalg.norm(n0, axis=1) > 1e-9)[:, None], n0, np.cross(u0, pole))
        n1 = np.where((np.linalg.norm(n1, axis=1) > 1e-9)[:, None], n1, np.cross(u, pole))
        D_t = _frame(K2 - H, n1) @ np.swapaxes(_frame(K - H, n0), -1, -2)
        D_s = _frame(A2 - K2, n1) @ np.swapaxes(_frame(A - K, n0), -1, -2)
        moved = w > 0
        eye = np.broadcast_to(np.eye(3), (F, 3, 3))
        D_t = np.where(moved[:, None, None], D_t, eye)
        D_s = np.where(moved[:, None, None], D_s, eye)
        new_rot[th] = bvh_io.polar(D_t @ Wr[:, th])
        new_rot[sh] = bvh_io.polar(D_s @ Wr[:, sh])
        new_rot[ft] = Wr[:, ft]
        weights[s] = w
        info[s] = {"source": src, "ranges": [[int(b), int(e)] for b, e in ranges],
                   "plant_sole_median_m": [_r(h, 4) for h in heights],
                   "frames_changed": int(moved.sum()), "reach_short_m": _r(short.max() if F else 0.0, 5)}
    return new_rot, info, fl, weights


def slide_report(Wp, legs, info, fl, mm, offsets=None):
    out = {}
    allv, pen = [], []
    for s in SIDES:
        fp, sole = foot_point(Wp, legs, s, offsets)
        rng = [tuple(r) for r in info[s]["ranges"]]
        v = mm.slide(fp[:, :2], rng)
        allv.append(v)
        for b, e in rng:
            pen.append(np.maximum(0.0, fl - sole[b:e + 1]))
        out[s] = {k: _r(x, 5) for k, x in mm.summary(v).items()}
    v = np.concatenate(allv) if allv else np.zeros(0)
    p = np.concatenate(pen) if pen else np.zeros(1)
    return {"per_side": out, **{k: _r(x, 5) for k, x in mm.summary(v).items()}}, float(p.max())


def plant_counts(info) -> dict:
    """The plants per foot and their total, named as motion_metrics names them."""
    per = {s: len(info[s]["ranges"]) for s in SIDES}
    return {"plants_per_foot": per, "plants_found": sum(per.values())}


def finish(before, after, pen_after, info, a, any_contacts) -> tuple:
    gates = []
    n_pl = plant_counts(info)["plants_found"]
    gates.append(gate("plants_found", n_pl, ">= 1 (or --allow-no-plants)", n_pl >= 1 or a.allow_no_plants))
    if any_contacts:
        worst = max([h for s in SIDES for h in info[s]["plant_sole_median_m"]] or [0.0])
        gates.append(gate("contact_height_m", _r(worst, 4), f"<= {a.contact_h_max}", worst <= a.contact_h_max))
    reach = max(info[s]["reach_short_m"] or 0.0 for s in SIDES)
    gates.append(gate("reach_m", _r(reach, 5), f"<= {a.reach_tol}", reach <= a.reach_tol))
    gates.append(gate("foot_slide_p95_m", after["p95"], f"<= {a.slide_p95}", after["p95"] <= a.slide_p95))
    gates.append(gate("foot_slide_max_m", after["max"], f"<= {a.slide_max}", after["max"] <= a.slide_max))
    gates.append(gate("penetration_max_m", _r(pen_after, 5), f"<= {a.penetration_max}", pen_after <= a.penetration_max))
    return gates, all(g["ok"] for g in gates)


def _rot_change_deg(A, B):
    c = (np.trace(np.swapaxes(A, -1, -2) @ B, axis1=-2, axis2=-1) - 1) / 2
    return np.degrees(np.arccos(np.clip(c, -1, 1)))


def pelvis_name(names, parents, legs) -> str:
    """The samples' root for motion_metrics: the thighs' parent (Hips on the contract, whose Root
    above it never moves), else the skeleton's root."""
    p = parents[legs["l"][0]]
    if p >= 0 and p == parents[legs["r"][0]]:
        return names[p]
    return names[[j for j, q in enumerate(parents) if q < 0][0]]


def write_samples(path, names, parents, Pz, fps, legs, contacts, clip, root, offsets=None, readings=None):
    segs = [[names[p], names[j]] for j, p in enumerate(parents) if p >= 0]
    feet = {s: [names[legs[s][2]]] + ([names[legs[s][3]]] if legs[s][3] is not None else []) for s in SIDES}
    meta = {"clip": clip, "root": root, "feet": feet, "segments": segs}
    if offsets:
        meta["sole_offsets"] = {names[j]: h for j, h in offsets.items()}
    extra = {"contacts": np.stack([contacts["l"], contacts["r"]], axis=1)} if contacts is not None else {}
    if readings:   # motion_metrics reads them as the source's own joints, for pops_in_source
        js = sorted(readings)
        extra["reading_joints"] = np.stack([readings[j] for j in js], axis=1)
        extra["reading_names"] = np.array([names[j] for j in js])
    np.savez(path, positions=Pz, names=np.array(names), fps=np.array(float(fps)), meta=json.dumps(meta), **extra)


# ----------------------------------------------------------------------------- BVH mode

def run_bvh(a) -> tuple:
    import bvh_io
    mm = metrics()
    try:
        b = bvh_io.load(a.clip)
    except bvh_io.BvhError as e:
        raise Refused(str(e)) from None
    if b.n_frames < 2 or b.fps <= 0:
        raise Refused("the BVH needs at least 2 frames and a frame time")
    doc = read_rig_info(a.rig_info)
    alias = contract_of(doc)
    legs, preset = resolve_legs(b.names, a.legs, alias)
    C = Y_TO_Z if a.up == "y" else np.eye(3)
    Wr, Wp = b.fk()
    Wr_z = C @ Wr @ C.T
    Wp_z = (Wp * a.unit_m) @ C.T
    contacts = load_contacts(a.contacts, b.n_frames, a.contacts_offset) if a.contacts else None
    offsets = load_offsets(a.rig_info, b.names, legs, doc, alias)
    readings, rrep = (load_readings(a.readings, b.n_frames, a.readings_offset, b.names, Wp_z, alias, b.parents)
                      if a.readings else (None, None))
    new_rot, info, fl, weights = bake(Wr_z, Wp_z, legs, b.fps, contacts, a.floor, a.blend, a, offsets)
    before, _ = slide_report(Wp_z, legs, info, fl, mm, offsets)

    W_new = Wr.copy()
    for j, R in new_rot.items():
        W_new[:, j] = C.T @ R @ C
    L = b.local_rotations()
    touched = sorted(new_rot)
    for j in touched:
        p = b.parents[j]
        L[:, j] = W_new[:, j] if p < 0 else np.swapaxes(W_new[:, p], -1, -2) @ W_new[:, j]
    out_b = bvh_io.parse(b.dump())
    if not a.sample_only:
        out_b.set_rotations(L, joints=touched)
    Wr2, Wp2 = bvh_io.parse(out_b.dump()).fk()
    Wp2_z = (Wp2 * a.unit_m) @ C.T
    after, pen_after = slide_report(Wp2_z, legs, info, fl, mm, offsets)

    still = np.ones(b.n_frames, bool)
    for s in SIDES:
        still &= weights[s] == 0
    outside = float(max((_rot_change_deg(Wr[still, j], Wr2[still, j]).max() if still.any() else 0.0) for j in touched))
    gates, ok = finish(before, after, pen_after, info, a, contacts is not None)
    rep = {"tool": "contact_bake", "mode": "bvh" + (" sample-only" if a.sample_only else ""), "ok": ok, "clip": str(a.clip), "frames": b.n_frames,
           "fps": round(b.fps, 4), "legs": preset, "leg_joints": {s: [b.names[j] if j is not None else None for j in legs[s]] for s in SIDES},
           "floor_m": _r(fl, 4), "sole_offsets": {b.names[j]: h for j, h in offsets.items()}, "plants": info,
           **plant_counts(info),
           "slide_before_m": before, "slide_after_m": after, "outside_change_deg": _r(outside, 4), "gates": gates}
    if rrep is not None:
        rep["readings"] = rrep
    if ok or a.write_on_fail or a.sample_only:
        if not a.sample_only:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            out_b.save(a.out)
            rep["output"] = str(a.out)
        if a.samples_out:
            root = pelvis_name(b.names, b.parents, legs)
            write_samples(a.samples_out, b.names, b.parents, Wp2_z, b.fps, legs, contacts, Path(a.clip).stem, root,
                          offsets, readings)
            rep["samples"] = a.samples_out
    return rep, (0 if ok else 2)


# ----------------------------------------------------------------------------- Blender mode

def run_blender(a) -> tuple:
    import bpy
    from mathutils import Matrix
    mm = metrics()
    obj = bpy.data.objects.get(a.armature or "")
    if obj is None or obj.type != "ARMATURE":
        raise Refused(f"no armature object {a.armature!r}")
    act = bpy.data.actions.get(a.action) if a.action else (obj.animation_data.action if obj.animation_data else None)
    if act is None:
        raise Refused(f"no action {a.action!r} (and none assigned to {obj.name})")
    if obj.animation_data is None:
        obj.animation_data_create()
    if obj.animation_data.action != act:
        obj.animation_data.action = act
        if hasattr(obj.animation_data, "action_slot") and len(getattr(act, "slots", [])):
            obj.animation_data.action_slot = act.slots[0]
    scene = bpy.context.scene
    if a.frame_range:
        f0, f1 = a.frame_range
    else:
        f0, f1 = (int(round(x)) for x in act.frame_range)
    frames = list(range(f0, f1 + 1))
    pbs = list(obj.pose.bones)
    names = [pb.name for pb in pbs]
    index = {n: i for i, n in enumerate(names)}
    parents = [index[pb.parent.name] if pb.parent else -1 for pb in pbs]
    # pose bones in parent-first order for FK-free sampling (positions come from Blender)
    doc = read_rig_info(a.rig_info)
    alias = contract_of(doc)
    legs, preset = resolve_legs(names, a.legs, alias)
    warnings = []
    for s in SIDES:
        for j in legs[s][:3]:
            pb = pbs[j]
            if len(pb.constraints):
                warnings.append(f"{pb.name} has constraints: the bake writes its rotation keys under them")
            if not pb.bone.use_inherit_rotation:
                warnings.append(f"{pb.name} does not inherit rotation: the solve assumes it does")
    Mw = obj.matrix_world.copy()
    Rw_obj = np.array(Mw.to_3x3().normalized())

    def sample():
        F, J = len(frames), len(pbs)
        Wr = np.empty((F, J, 3, 3))
        Wp = np.empty((F, J, 3))
        Ar = np.empty((F, J, 3, 3))
        for fi, f in enumerate(frames):
            scene.frame_set(f)
            for j, pb in enumerate(pbs):
                M = Mw @ pb.matrix
                Wp[fi, j] = M.translation
                Wr[fi, j] = np.array(M.to_3x3().normalized())
                Ar[fi, j] = np.array(pb.matrix.to_3x3().normalized())
        return Wr, Wp, Ar

    Wr, Wp, Ar = sample()
    fps = scene.render.fps / scene.render.fps_base
    contacts = load_contacts(a.contacts, len(frames), a.contacts_offset) if a.contacts else None
    offsets = load_offsets(a.rig_info, names, legs, doc, alias)
    readings, rrep = (load_readings(a.readings, len(frames), a.readings_offset, names, Wp * a.unit_m, alias, parents)
                      if a.readings else (None, None))
    new_rot, info, fl, weights = bake(Wr, Wp * a.unit_m, legs, fps, contacts, a.floor, a.blend, a, offsets)
    before, _ = slide_report(Wp * a.unit_m, legs, info, fl, mm, offsets)

    # armature-space rotation of each bone, the new ones for the leg chain
    A_new = Ar.copy()
    for j, R in new_rot.items():
        A_new[:, j] = Rw_obj.T @ R
    touched = sorted(new_rot)
    for j in ([] if a.sample_only else touched):
        pb = pbs[j]
        rest_b = np.array(pb.bone.matrix_local.to_3x3().normalized())
        if pb.parent:
            rest_p = np.array(pb.parent.bone.matrix_local.to_3x3().normalized())
            rel = rest_p.T @ rest_b
        else:
            rel = rest_b
        prev_q = None
        prev_e = None
        for fi, f in enumerate(frames):
            Ap = A_new[fi, parents[j]] if parents[j] >= 0 else np.eye(3)
            basis = rel.T @ Ap.T @ A_new[fi, j]
            M3 = Matrix(basis.tolist())
            mode = pb.rotation_mode
            if mode == "QUATERNION":
                q = M3.to_quaternion()
                if prev_q is not None and q.dot(prev_q) < 0:
                    q.negate()
                pb.rotation_quaternion = q
                prev_q = q.copy()
                pb.keyframe_insert("rotation_quaternion", frame=f, group=pb.name)
            elif mode == "AXIS_ANGLE":
                ax, ang = M3.to_quaternion().to_axis_angle()
                pb.rotation_axis_angle = (ang, ax[0], ax[1], ax[2])
                pb.keyframe_insert("rotation_axis_angle", frame=f, group=pb.name)
            else:
                e = M3.to_euler(mode, prev_e) if prev_e is not None else M3.to_euler(mode)
                pb.rotation_euler = e
                prev_e = e.copy()
                pb.keyframe_insert("rotation_euler", frame=f, group=pb.name)
    Wr2, Wp2, _ = (Wr, Wp, None) if a.sample_only else sample()
    after, pen_after = slide_report(Wp2 * a.unit_m, legs, info, fl, mm, offsets)
    still = np.ones(len(frames), bool)
    for s in SIDES:
        still &= weights[s] == 0
    outside = float(max((_rot_change_deg(Wr[still, j], Wr2[still, j]).max() if still.any() else 0.0) for j in touched))
    gates, ok = finish(before, after, pen_after, info, a, contacts is not None)
    rep = {"tool": "contact_bake", "mode": "blender" + (" sample-only" if a.sample_only else ""), "ok": ok, "armature": obj.name, "action": act.name,
           "frame_range": [f0, f1], "frames": len(frames), "fps": round(fps, 4), "legs": preset,
           "leg_joints": {s: [names[j] if j is not None else None for j in legs[s]] for s in SIDES},
           "floor_m": _r(fl, 4), "sole_offsets": {names[j]: h for j, h in offsets.items()}, "plants": info,
           **plant_counts(info),
           "slide_before_m": before, "slide_after_m": after,
           "outside_change_deg": _r(outside, 4), "gates": gates, "warnings": warnings,
           "blender": list(bpy.app.version)}
    if rrep is not None:
        rep["readings"] = rrep
    if ok or a.write_on_fail or a.sample_only:
        if a.out and not a.sample_only:
            bpy.ops.wm.save_as_mainfile(filepath=str(Path(a.out).resolve()))
            rep["output"] = str(a.out)
        if a.samples_out:
            root = pelvis_name(names, parents, legs)
            write_samples(a.samples_out, names, parents, Wp2 * a.unit_m, fps, legs, contacts, act.name, root, offsets,
                          readings)
            rep["samples"] = a.samples_out
    rep["record"] = {"kind": "clip"}
    return rep, (0 if ok else 2)


# ----------------------------------------------------------------------------- CLI

class _ArgError(Exception):
    pass


def parser() -> argparse.ArgumentParser:
    # the defaults are motion_metrics'; without it --help still works and any run exits 1
    mmv = dict.fromkeys(("slide_p95", "slide_max", "penetration_max", "h_max", "v_max", "min_frames"))
    try:
        mm = metrics()
        mmv = {"slide_p95": mm.SLIDE_P95, "slide_max": mm.SLIDE_MAX, "penetration_max": mm.PENETRATION_MAX,
               "h_max": mm.PLANT_H_MAX, "v_max": mm.PLANT_V_MAX, "min_frames": mm.PLANT_MIN_FRAMES}
    except Refused:
        pass
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.error = lambda m: (_ for _ in ()).throw(_ArgError(m))
    p.add_argument("clip", nargs="?")
    p.add_argument("--out")
    p.add_argument("--armature")
    p.add_argument("--action")
    p.add_argument("--frame-range", nargs=2, type=int)
    p.add_argument("--contacts")
    p.add_argument("--contacts-offset", type=int, default=0)
    p.add_argument("--legs", action="append")
    p.add_argument("--up", choices=("y", "z"), default="y")
    p.add_argument("--unit-m", type=float, default=1.0)
    p.add_argument("--floor", default="0.0")
    p.add_argument("--rig-info", "--sole-offsets", dest="rig_info",
                   help="rig_info.json (twocam.ground) or a samples file (sole_offsets): foot joints' rest heights")
    p.add_argument("--readings", help="a samples file with reading_joints (the capture's samples.json): carried "
                   "into --samples-out for motion_metrics' pops_in_source")
    p.add_argument("--readings-offset", type=int, default=0)
    p.add_argument("--blend", type=int, default=BLEND)
    p.add_argument("--samples-out")
    p.add_argument("--report")
    p.add_argument("--allow-no-plants", action="store_true")
    p.add_argument("--write-on-fail", action="store_true")
    p.add_argument("--sample-only", action="store_true", help="measure and write --samples-out, bake nothing")
    p.add_argument("--contact-h-max", type=float, default=CONTACT_H_MAX)
    p.add_argument("--reach-tol", type=float, default=REACH_TOL)
    p.add_argument("--slide-p95", type=float, default=mmv["slide_p95"])
    p.add_argument("--slide-max", type=float, default=mmv["slide_max"])
    p.add_argument("--penetration-max", type=float, default=mmv["penetration_max"])
    p.add_argument("--h-max", type=float, default=mmv["h_max"])
    p.add_argument("--v-max", type=float, default=mmv["v_max"])
    p.add_argument("--min-frames", type=int, default=mmv["min_frames"])
    return p


def in_blender() -> bool:
    try:
        import bpy  # noqa: F401
        return True
    except ImportError:
        return False


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if argv and argv[0] in ("--selftest", "selftest"):
        return selftest()
    if argv and argv[0] == "--selftest-blender":
        return selftest_blender()
    try:
        a = parser().parse_args(argv)
        if a.floor != "auto":
            float(a.floor)
        if a.armature:
            if not in_blender():
                raise Refused("--armature needs Blender: blender -b RIG.blend -P contact_bake.py -- --armature ...")
            rep, code = run_blender(a)
        else:
            if not a.clip or not (a.out or a.sample_only):
                raise Refused("give CLIP.bvh and --out (or --armature inside Blender)")
            rep, code = run_bvh(a)
    except (_ArgError, Refused, ValueError) as e:
        print(json.dumps({"tool": "contact_bake", "ok": False, "refused": str(e)}))
        return 1
    text = json.dumps(rep, indent=1)
    if a.report:
        Path(a.report).write_text(text)
    print(text)
    return code


# ----------------------------------------------------------------------------- synthetic gait

THIGH, SHIN = 0.45, 0.43


def _leg_angles(dz, dy):
    """Sagittal two-bone leg, BVH Y up, +Z forward: ankle at (dz forward, dy up) from the hip ->
    (hip pitch, knee bend) in degrees about +X. Independent of the bake's solver."""
    d = min(math.hypot(dz, dy), (THIGH + SHIN) * 0.9995)
    knee = math.pi - math.acos(np.clip((THIGH ** 2 + SHIN ** 2 - d ** 2) / (2 * THIGH * SHIN), -1, 1))
    alpha = math.acos(np.clip((THIGH ** 2 + d ** 2 - SHIN ** 2) / (2 * THIGH * d), -1, 1))
    ang = math.atan2(dz, -dy)                   # angle of the hip->ankle line from straight down
    # +X rotation turns -Y (down) toward... -Z; forward (+Z) needs a negative pitch
    hip = -(ang + alpha)
    return math.degrees(hip), math.degrees(knee)


MIXAMO = {"UpperLeg": "UpLeg", "LowerLeg": "Leg", "Foot": "Foot", "Toes": "ToeBase"}


def synthetic_gait(F=90, fps=30.0, creep=0.02, period=30, speed=0.8, lift=0.08, hang=False, drag=False,
                   with_root=False, raise_m=0.0, mixamo=False):
    """A BVH walk: the hips travel at `speed`, each foot stands for 60 % of a stride and creeps
    `creep` metres forward over its stance (a slide to remove). The ankle (Foot) stands 7 cm over
    the floor, the ball (Toes) on it; `raise_m` lifts the whole body (joints that far over their
    soles). `mixamo` names the bones LeftUpLeg... Returns (Bvh, contacts {l, r})."""
    import bvh_io
    names = ["Hips", "UpperLeg.L", "LowerLeg.L", "Foot.L", "Toes.L", "UpperLeg.R", "LowerLeg.R", "Foot.R", "Toes.R"]
    parents = [-1, 0, 1, 2, 3, 0, 5, 6, 7]
    foot_h = 0.07
    hip_h = THIGH + SHIN + foot_h - 0.08
    offsets = np.array([[0, 0, 0], [0.1, -0.0, 0], [0, -THIGH, 0], [0, -SHIN, 0], [0, -foot_h, 0.12],
                        [-0.1, 0, 0], [0, -THIGH, 0], [0, -SHIN, 0], [0, -foot_h, 0.12]], float)
    ch = [["Xposition", "Yposition", "Zposition", "Zrotation", "Xrotation", "Yrotation"]] + [["Zrotation", "Xrotation", "Yrotation"]] * 8
    stride = speed * period / fps
    stance = 0.6
    frames = np.zeros((F, 6 + 24))
    cont = {"l": np.zeros(F), "r": np.zeros(F)}
    for f in range(F):
        t = f / fps
        hz = speed * t
        hy = hip_h + (0.25 if hang else 0.0)
        frames[f, 0:3] = [0, hy, hz]
        for s, side, phase0 in (("l", 1, 0.0), ("r", 5, 0.5)):
            ph = ((f / period) + phase0) % 1.0
            cyc = math.floor((f / period) + phase0)
            if drag:
                az, ay, on = hz + 0.05, foot_h, True
            elif ph < stance:
                plant_z = (cyc + 0.5 - phase0) * stride - stride * 0.3
                az = plant_z + creep * (ph / stance)
                ay, on = foot_h, True
            else:
                q = (ph - stance) / (1 - stance)
                start = (cyc + 0.5 - phase0) * stride - stride * 0.3 + creep
                az = start + (stride - creep) * (3 * q * q - 2 * q ** 3)
                ay, on = foot_h + lift * math.sin(math.pi * q) ** 2, False
            cont[s][f] = 1.0 if on else 0.0
            dz, dy = az - hz, ay - hy
            hip, knee = _leg_angles(dz, dy)
            c = 6 + (side - 1) * 3
            frames[f, c + 1] = hip
            frames[f, c + 4] = knee
            frames[f, c + 7] = -(hip + knee)            # foot stays level
    frames[:, 1] += raise_m
    if mixamo:
        names = [n if "." not in n else ("Left" if n.endswith(".L") else "Right") + MIXAMO[n[:-2]] for n in names]
    if with_root:   # the contract's static, non-deform Root on the ground above Hips
        names = ["Root"] + names
        parents = [-1] + [p + 1 for p in parents]
        offsets = np.vstack([[0, 0, 0], offsets])
        ch = [["Xposition", "Yposition", "Zposition", "Zrotation", "Xrotation", "Yrotation"]] + ch
        frames = np.hstack([np.zeros((F, 6)), frames])
        return bvh_io.Bvh(names, parents, offsets, ch, {5: [0, 0, 0.05], 9: [0, 0, 0.05]}, frames, 1 / fps), cont
    return bvh_io.Bvh(names, parents, offsets, ch, {4: [0, 0, 0.05], 8: [0, 0, 0.05]}, frames, 1 / fps), cont


def selftest() -> int:
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    me = Path(__file__).resolve()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        def cli(*args):
            r = subprocess.run([sys.executable, str(me), *map(str, args)], capture_output=True, text=True)
            try:
                return r.returncode, json.loads(r.stdout)
            except ValueError:
                return r.returncode, {"stdout": r.stdout[-400:], "stderr": r.stderr[-800:]}

        def gate_of(rep, name):
            return next((g for g in rep.get("gates", []) if g["name"] == name), {})

        b, cont = synthetic_gait(creep=0.04)
        b.save(td / "walk.bvh")
        (td / "c.json").write_text(json.dumps({"schema": "contacts/1", "l": cont["l"].tolist(), "r": cont["r"].tolist()}))
        _, Wp = b.fk()
        hips_before = Wp[:, 0].copy()

        code, rep = cli(td / "walk.bvh", "--out", td / "baked.bvh", "--contacts", td / "c.json",
                        "--samples-out", td / "s.npz", "--legs", "contract")
        sb, sa = rep.get("slide_before_m", {}), rep.get("slide_after_m", {})
        check("sliding feet fail the slide gate before the bake", sb.get("p95", 0) > 0.015, sb)
        check("and pass after it (exit 0)", code == 0 and sa.get("p95", 1) <= 0.002 and sa.get("max", 1) <= 0.005, (code, sa, rep.get("gates")))
        check("plants come from the contacts, both feet", all(rep["plants"][s]["source"] == "contacts"
              and len(rep["plants"][s]["ranges"]) >= 2 for s in SIDES), rep.get("plants"))
        check("nothing changes outside the plants and blends", (rep.get("outside_change_deg") or 0) < 1e-6, rep.get("outside_change_deg"))
        import bvh_io
        b2 = bvh_io.load(td / "baked.bvh")
        _, Wp2 = b2.fk()
        check("the hips are not moved", np.abs(Wp2[:, 0] - hips_before).max() < 1e-6)
        check("bone lengths kept", abs(np.linalg.norm(Wp2[:, 2] - Wp2[:, 1], axis=1) - THIGH).max() < 1e-6)
        mm = METRICS_DIR / "motion_metrics.py"
        legs_c, _ = resolve_legs(b.names, ["contract"])
        write_samples(td / "src.npz", b.names, b.parents, Wp @ Y_TO_Z.T, b.fps, legs_c, cont, "src", "Hips")

        def metrics_of(path):
            r = subprocess.run([sys.executable, str(mm), str(path), "--state", "walk"], capture_output=True, text=True)
            try:
                m = json.loads(r.stdout)
            except ValueError:
                m = {}
            return r.returncode, m, {g["name"]: g["ok"] for g in m.get("gates", [])}

        c0, m0, g0 = metrics_of(td / "src.npz")
        c1, m1, g1 = metrics_of(td / "s.npz")
        check("motion_metrics: the source fails foot_slide_p95_m, the baked samples pass it (contacts used)",
              g0.get("foot_slide_p95_m") is False and g1.get("foot_slide_p95_m") is True and g1.get("foot_slide_max_m") is True
              and m1.get("plants", {}).get("l", {}).get("source") == "contacts", (c0, c1, m1.get("foot_slide_m")))
        check("the bake adds no pop and no penetration", m1.get("pops", {}).get("count") == m0.get("pops", {}).get("count")
              and g1.get("penetration_max_m") is True, (m0.get("pops", {}).get("count"), m1.get("pops", {}).get("count")))

        br, _ = synthetic_gait(creep=0.04, with_root=True)
        br.save(td / "rooted.bvh")
        code, rep = cli(td / "rooted.bvh", "--out", td / "rb.bvh", "--contacts", td / "c.json", "--samples-out", td / "rs.npz")
        with np.load(td / "rs.npz") as z:
            meta = json.loads(str(z["meta"]))
        c2, m2, _ = metrics_of(td / "rs.npz")
        check("a static Root above Hips: samples name Hips as root, the loop is found",
              code == 0 and meta.get("root") == "Hips" and m2.get("root") == "Hips"
              and m2.get("loop", {}).get("period") is not None, (code, meta.get("root"), m2.get("loop")))

        code, rep = cli(td / "walk.bvh", "--sample-only", "--contacts", td / "c.json", "--samples-out", td / "so.npz")
        check("--sample-only measures the slide, writes samples, bakes nothing (exit 2 on the sliding walk)",
              code == 2 and rep["slide_after_m"]["p95"] == rep["slide_before_m"]["p95"] and (td / "so.npz").is_file()
              and "output" not in rep, (code, rep.get("slide_after_m")))
        code, rep = cli(td / "baked.bvh", "--sample-only", "--contacts", td / "c.json")
        check("--sample-only on the baked walk passes (exit 0)", code == 0, rep.get("gates"))

        code, rep = cli(td / "walk.bvh", "--out", td / "det.bvh")
        check("without contacts the detector finds the plants and the bake passes",
              code == 0 and rep["plants"]["l"]["source"] == "detector" and rep["slide_after_m"]["p95"] <= 0.015,
              (code, rep.get("slide_after_m"), rep.get("plants", {}).get("l")))

        # failures
        bs, cs = synthetic_gait(creep=0.04, lift=0.3)
        bs.save(td / "high.bvh")
        bad = {s: np.clip(1.0 - cs[s], 0, 1).tolist() for s in SIDES}            # contact on the swing
        (td / "swing.json").write_text(json.dumps(bad))
        code, rep = cli(td / "high.bvh", "--out", td / "x.bvh", "--contacts", td / "swing.json")
        check("contacts on the swing fail contact_height (exit 2)", code == 2 and gate_of(rep, "contact_height_m").get("ok") is False,
              gate_of(rep, "contact_height_m"))
        bd, cd = synthetic_gait(drag=True)
        bd.save(td / "drag.bvh")
        (td / "all.json").write_text(json.dumps({s: [1.0] * bd.n_frames for s in SIDES}))
        code, rep = cli(td / "drag.bvh", "--out", td / "x.bvh", "--contacts", td / "all.json")
        check("a foot locked while the hips travel 3 m fails reach (exit 2)", code == 2 and gate_of(rep, "reach_m").get("ok") is False,
              gate_of(rep, "reach_m"))
        bh, _ = synthetic_gait(hang=True, creep=0.0)
        bh.save(td / "hang.bvh")
        code, rep = cli(td / "hang.bvh", "--out", td / "x.bvh")
        check("no plant anywhere fails plants_found (exit 2)", code == 2 and gate_of(rep, "plants_found").get("ok") is False,
              gate_of(rep, "plants_found"))
        code, rep = cli(td / "hang.bvh", "--out", td / "x.bvh", "--allow-no-plants")
        check("--allow-no-plants passes it", code == 0, rep.get("gates"))
        code, rep = cli(td / "walk.bvh", "--out", td / "x.bvh", "--legs", "mixamo")
        check("leg bones not found: exit 1", code == 1 and "no leg chain" in rep.get("refused", ""), rep)
        (td / "short.json").write_text(json.dumps({"l": [1.0] * 10, "r": [1.0] * 10}))
        code, rep = cli(td / "walk.bvh", "--out", td / "x.bvh", "--contacts", td / "short.json")
        check("contacts shorter than the clip: exit 1", code == 1, rep)
        (td / "junk.bvh").write_text("HIERARCHY\nROOT A\n{\n OFFSET 0 0\n")
        code, rep = cli(td / "junk.bvh", "--out", td / "x.bvh")
        check("a malformed BVH: exit 1", code == 1, rep)
        # sole offsets: joints 6 cm over their soles find no plant; with the rest heights they do
        br6, _ = synthetic_gait(creep=0.04, raise_m=0.06)
        br6.save(td / "raised.bvh")
        ground = {"Foot.L": 0.13, "Toes.L": 0.06, "Foot.R": 0.13, "Toes.R": 0.06, "ToesTip.L": 0.06}
        (td / "rig_info.json").write_text(json.dumps({"twocam": {"ground": ground}}))
        code, rep = cli(td / "raised.bvh", "--out", td / "x.bvh")
        check("joints 6 cm over the sole, no offsets: no plant, exit 2",
              code == 2 and gate_of(rep, "plants_found").get("ok") is False, gate_of(rep, "plants_found"))
        code, rep = cli(td / "raised.bvh", "--out", td / "r6.bvh", "--rig-info", td / "rig_info.json",
                        "--samples-out", td / "r6.npz")
        check("with --rig-info: the detector plants both feet, the bake passes (exit 0)",
              code == 0 and all(len(rep["plants"][s]["ranges"]) >= 2 for s in SIDES)
              and rep["slide_after_m"]["p95"] <= 0.015 and len(rep.get("sole_offsets", {})) == 4,
              (code, rep.get("slide_after_m"), rep.get("sole_offsets"), rep.get("gates")))
        c6, m6, g6 = metrics_of(td / "r6.npz")
        check("the baked samples carry the offsets: motion_metrics plants and passes the slide",
              g6.get("plants_min_per_foot") is True and g6.get("foot_slide_p95_m") is True
              and len(m6.get("sole_offsets", {})) == 4,
              (c6, m6.get("sole_offsets"), m6.get("plants", {}).get("l", {}).get("ranges")))
        check("plants_found is the total in both reports, beside the same plants_per_foot; the bake's gate reads it",
              rep.get("plants_per_foot") == {s_: len(rep["plants"][s_]["ranges"]) for s_ in SIDES}
              and rep.get("plants_found") == sum(rep["plants_per_foot"].values()) == gate_of(rep, "plants_found").get("value")
              and m6.get("plants_per_foot") == rep["plants_per_foot"] and m6.get("plants_found") == rep["plants_found"],
              (rep.get("plants_per_foot"), rep.get("plants_found"), m6.get("plants_per_foot"), m6.get("plants_found")))
        # ... the lock height: joints 4 cm up whose rest heights say 6 cm stand 2 cm in the floor; the lock lifts them
        br4, c4 = synthetic_gait(creep=0.04, raise_m=0.04)
        br4.save(td / "sunk.bvh")
        code, rep = cli(td / "sunk.bvh", "--out", td / "s4.bvh", "--rig-info", td / "rig_info.json")
        b4 = bvh_io.load(td / "s4.bvh")
        _, W4 = b4.fk()
        rng = rep.get("plants", {}).get("l", {}).get("ranges", [[0, 0]])
        z_in = np.array([W4[f, 3, 1] for a_, e_ in rng for f in range(a_, e_ + 1)])
        check("sole under the floor by its offset: the lock lifts the ankle 2 cm, penetration passes (exit 0)",
              code == 0 and gate_of(rep, "penetration_max_m").get("ok") is True and np.abs(z_in - 0.13).max() < 2e-3,
              (code, gate_of(rep, "penetration_max_m"), z_in.min() if z_in.size else None))
        (td / "nomatch.json").write_text(json.dumps({"sole_offsets": {"Heel.L": 0.02}}))
        code, rep = cli(td / "walk.bvh", "--out", td / "x.bvh", "--rig-info", td / "nomatch.json")
        check("offsets naming no foot joint: exit 1", code == 1 and "no sole offset" in rep.get("refused", ""), rep)
        # mixamo names: the preset, and offsets from a samples file's sole_offsets
        bm, _ = synthetic_gait(creep=0.04, raise_m=0.06, mixamo=True)
        bm.save(td / "mixamo.bvh")
        (td / "mx.json").write_text(json.dumps({"schema": "motion-samples/1", "sole_offsets": {
            "LeftFoot": 0.13, "LeftToeBase": 0.06, "RightFoot": 0.13, "RightToeBase": 0.06}}))
        code, rep = cli(td / "mixamo.bvh", "--out", td / "mx.bvh", "--legs", "mixamo", "--sole-offsets", td / "mx.json")
        check("--legs mixamo with a samples file's sole_offsets bakes (exit 0)",
              code == 0 and rep.get("legs") == "mixamo" and rep["slide_after_m"]["p95"] <= 0.015, (code, rep.get("gates")))
        code, rep = cli(td / "mixamo.bvh", "--out", td / "mx.bvh", "--contacts", td / "c.json")
        check("--legs auto finds the mixamo chain", code == 0 and rep.get("legs") == "mixamo", (code, rep.get("legs")))

        # a rig whose bones carry other names (Auto-Rig Pro's), with a twist bone half way down each shin;
        # rig_info's twocam.contract_names maps them, its ground is keyed by contract names
        arp = {"Hips": "root.x", "UpperLeg.L": "thigh_stretch.l", "LowerLeg.L": "leg_stretch.l", "Foot.L": "foot.l",
               "Toes.L": "toes_01.l", "UpperLeg.R": "thigh_stretch.r", "LowerLeg.R": "leg_stretch.r",
               "Foot.R": "foot.r", "Toes.R": "toes_01.r"}

        def arp_gait(src, spike=False):
            names = [arp[n] for n in src.names] + ["leg_twist.l", "leg_twist.r"]
            parents = src.parents + [2, 6]
            offs = np.vstack([src.offsets, [[0, -SHIN / 2, 0]] * 2])
            fr = np.hstack([src.frames, np.zeros((src.n_frames, 6))])
            if spike:   # the left knee snaps for one frame in the swing (frame 22)
                fr[22, 6 + 3 * 2 + 1] += 25.0
            return bvh_io.Bvh(names, parents, offs, src.channels + [["Zrotation", "Xrotation", "Yrotation"]] * 2,
                              {**src.ends, 9: [0, -0.05, 0], 10: [0, -0.05, 0]}, fr, src.frame_time)

        ba = arp_gait(br6, spike=True)
        ba.save(td / "arp.bvh")
        arp_info = {"twocam": {"ground": ground, "contract_names": {v: k for k, v in arp.items()}}}
        (td / "arp_info.json").write_text(json.dumps(arp_info))
        code, rep = cli(td / "arp.bvh", "--out", td / "a0.bvh", "--legs", "contract")
        check("rig bone names without the map: --legs contract finds no chain, exit 1, contract_names named",
              code == 1 and "no leg chain" in rep.get("refused", "") and "contract_names" in rep["refused"], rep)
        (td / "arp_nomap.json").write_text(json.dumps({"twocam": {"ground": ground}}))
        code, rep = cli(td / "arp.bvh", "--out", td / "a0.bvh", "--legs", "contract", "--rig-info",
                        td / "arp_nomap.json")
        check("--rig-info without twocam.contract_names on Auto-Rig Pro names: exit 1, contract_names named",
              code == 1 and "contract_names" in rep.get("refused", ""), rep)
        code, rep = cli(td / "arp.bvh", "--out", td / "a1.bvh", "--legs", "contract", "--rig-info", td / "arp_info.json",
                        "--samples-out", td / "a1.npz")
        check("with twocam.contract_names: --legs contract and the contract-named sole offsets reach the rig's "
              "bones, the bake passes (exit 0)",
              code == 0 and rep["leg_joints"]["l"] == ["thigh_stretch.l", "leg_stretch.l", "foot.l", "toes_01.l"]
              and sorted(rep.get("sole_offsets", {})) == ["foot.l", "foot.r", "toes_01.l", "toes_01.r"],
              (code, rep.get("leg_joints"), rep.get("sole_offsets"), rep.get("refused")))
        _, ca, ga = metrics_of(td / "a1.npz")
        # readings: the source's joints in contract names (Z up, metres), the knee snap in them too
        _, Wa = arp_gait(br6, spike=True).fk()
        rn = list(arp)
        rd = (Wa[:, [ba.names.index(arp[n]) for n in rn]]) @ Y_TO_Z.T
        (td / "readings.json").write_text(json.dumps({"reading_names": rn, "reading_joints": rd.tolist()}))
        code, rep = cli(td / "arp.bvh", "--out", td / "a2.bvh", "--legs", "contract", "--rig-info", td / "arp_info.json",
                        "--readings", td / "readings.json", "--samples-out", td / "a2.npz")
        with np.load(td / "a2.npz") as z:
            rnames = [str(x) for x in z["reading_names"]]
        r2 = subprocess.run([sys.executable, str(mm), str(td / "a2.npz"), "--pops-min-move", "0.03"],
                            capture_output=True, text=True)
        m2 = json.loads(r2.stdout) if r2.stdout.strip() else {}
        r1 = subprocess.run([sys.executable, str(mm), str(td / "a1.npz"), "--pops-min-move", "0.03"],
                            capture_output=True, text=True)
        m1 = json.loads(r1.stdout) if r1.stdout.strip() else {}
        check("without --readings the source's knee snap is a gated pop (shin and twist segments)",
              (m1.get("pops", {}).get("count") or 0) >= 1 and (m1.get("pops", {}).get("segments") or 0) >= 2
              and "pops_in_source" not in m1, m1.get("pops"))
        check("--readings: mapped through the contract names, the twist bone read half way down the shin; the snap "
              "is pops_in_source and no pop is gated",
              code == 0 and "leg_twist.l" in rnames and "foot.l" in rnames
              and rep["readings"]["between"].get("leg_twist.l", [None, None, 0])[:2] == ["leg_stretch.l", "foot.l"]
              and m2.get("pops", {}).get("count") == 0 and (m2.get("pops_in_source", {}).get("count") or 0) >= 2,
              (code, rep.get("readings"), m2.get("pops"), m2.get("pops_in_source")))
        # with no move floor the twist segment, which turns with the shin, shows each of the shin's pops again:
        # pops_in_source lists both and counts one event per frame and joint
        r0 = subprocess.run([sys.executable, str(mm), str(td / "a2.npz")], capture_output=True, text=True)
        ps = (json.loads(r0.stdout) if r0.stdout.strip() else {}).get("pops_in_source", {})
        on = lambda seg: {e["frame"] for e in ps.get("list", []) if e["segment"] == seg}   # noqa: E731
        twist, shin = on("leg_stretch.l>leg_twist.l"), on("leg_stretch.l>foot.l")
        check("pops_in_source: a pop on the shin and on the twist segment beside it is one event, both listed",
              twist and twist == shin and ps.get("segments", 0) > ps.get("count", 0) > 0
              and ps["count"] == len({(e["frame"], e["segment"].split(">")[0]) for e in ps["list"]}),
              (ps.get("count"), ps.get("segments"), sorted(twist), sorted(shin)))
        (td / "readings_calm.json").write_text(json.dumps({"reading_names": rn, "reading_joints": (
            (arp_gait(br6).fk()[1][:, [ba.names.index(arp[n]) for n in rn]]) @ Y_TO_Z.T).tolist()}))
        code, rep = cli(td / "arp.bvh", "--out", td / "a3.bvh", "--legs", "contract", "--rig-info", td / "arp_info.json",
                        "--readings", td / "readings_calm.json", "--samples-out", td / "a3.npz")
        r3 = subprocess.run([sys.executable, str(mm), str(td / "a3.npz"), "--pops-min-move", "0.03"],
                            capture_output=True, text=True)
        m3 = json.loads(r3.stdout) if r3.stdout.strip() else {}
        check("readings without the snap: the pop is not the source's, it stays gated (exit 2)",
              r3.returncode == 2 and (m3.get("pops", {}).get("count") or 0) >= 1, m3.get("pops"))
        code, rep = cli(td / "arp.bvh", "--out", td / "a4.bvh", "--legs", "contract", "--rig-info", td / "arp_info.json",
                        "--readings", td / "readings.json", "--readings-offset", "5")
        check("readings shorter than the clip from the offset: exit 1", code == 1 and "readings" in rep.get("refused", ""),
              rep)

        # centimetres: the same walk scaled x100 bakes the same
        bc, _ = synthetic_gait(creep=0.04)
        bc.offsets *= 100
        bc.ends = {k: v * 100 for k, v in bc.ends.items()}
        bc.frames[:, 0:3] *= 100
        bc.save(td / "cm.bvh")
        code, rep = cli(td / "cm.bvh", "--out", td / "cmb.bvh", "--contacts", td / "c.json", "--unit-m", "0.01")
        check("a centimetre BVH with --unit-m 0.01 bakes the same", code == 0 and rep["slide_after_m"]["p95"] <= 0.002,
              (code, rep.get("slide_after_m")))

    ok = all(c["ok"] for c in checks)
    print(json.dumps({"selftest": "pass" if ok else "fail", "checks": len(checks),
                      "failed": [c for c in checks if not c["ok"]]}, indent=1))
    return 0 if ok else 1


def selftest_blender() -> int:
    """Inside Blender: import the synthetic walk as an armature, bake it there, check the result."""
    import bpy
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        b, cont = synthetic_gait(creep=0.04, with_root=True)
        b.save(td / "walk.bvh")
        (td / "c.json").write_text(json.dumps({"l": cont["l"].tolist(), "r": cont["r"].tolist()}))
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        scene.render.fps = 30
        bpy.ops.import_anim.bvh(filepath=str(td / "walk.bvh"), global_scale=1.0, frame_start=1,
                                use_fps_scale=False, update_scene_fps=True, update_scene_duration=True,
                                rotate_mode="NATIVE", axis_forward="-Z", axis_up="Y")
        arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
        act = arm.animation_data.action
        args = parser().parse_args(["--armature", arm.name, "--action", act.name, "--frame-range", "1", str(b.n_frames),
                                    "--contacts", str(td / "c.json"), "--legs", "contract", "--out", str(td / "baked.blend"),
                                    "--samples-out", str(td / "s.npz")])
        code_rep, code = run_blender(args)
        sb, sa = code_rep.get("slide_before_m", {}), code_rep.get("slide_after_m", {})
        check("Blender: slide before fails, after passes, exit 0",
              code == 0 and sb.get("p95", 0) > 0.015 and sa.get("p95", 1) <= 0.003, (code, sb, sa, code_rep.get("gates")))
        check("Blender: the file is saved", (td / "baked.blend").is_file())
        with np.load(td / "s.npz") as z:
            meta = json.loads(str(z["meta"]))
        check("Blender: the samples' root is Hips, not the static Root above it", meta.get("root") == "Hips", meta.get("root"))
        check("Blender: nothing changes outside the plants", (code_rep.get("outside_change_deg") or 0) < 0.01,
              code_rep.get("outside_change_deg"))
        r = subprocess.run(["python3", str(METRICS_DIR / "motion_metrics.py"), str(td / "s.npz"), "--state", "walk"],
                           capture_output=True, text=True)
        try:
            g = {x["name"]: x["ok"] for x in json.loads(r.stdout)["gates"]}
        except (ValueError, KeyError):
            g = {}
        check("Blender: motion_metrics passes the slide and penetration gates on the samples",
              g.get("foot_slide_p95_m") and g.get("foot_slide_max_m") and g.get("penetration_max_m")
              and g.get("plants_min_per_foot"),
              r.stdout[-400:])

        def import_bvh(bvh):
            bpy.ops.wm.read_factory_settings(use_empty=True)
            bpy.context.scene.render.fps = 30
            bpy.ops.import_anim.bvh(filepath=str(bvh), global_scale=1.0, frame_start=1, use_fps_scale=False,
                                    update_scene_fps=True, update_scene_duration=True, rotate_mode="NATIVE",
                                    axis_forward="-Z", axis_up="Y")
            arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
            return arm, arm.animation_data.action

        # the contract rig 6 cm over its soles: no plant without the rest heights, a clean bake with them
        b6, _ = synthetic_gait(creep=0.04, with_root=True, raise_m=0.06)
        b6.save(td / "raised.bvh")
        (td / "rig_info.json").write_text(json.dumps({"twocam": {"ground": {
            "Foot.L": 0.13, "Toes.L": 0.06, "Foot.R": 0.13, "Toes.R": 0.06}}}))
        arm, act = import_bvh(td / "raised.bvh")
        base = ["--armature", arm.name, "--action", act.name, "--frame-range", "1", str(b6.n_frames), "--legs", "contract"]
        rep0, code0 = run_blender(parser().parse_args(base + ["--out", str(td / "r0.blend")]))
        check("Blender: joints 6 cm over the sole without offsets find no plant (exit 2)",
              code0 == 2 and not next(x for x in rep0["gates"] if x["name"] == "plants_found")["ok"], rep0.get("gates"))
        arm, act = import_bvh(td / "raised.bvh")
        rep1, code1 = run_blender(parser().parse_args(base + ["--rig-info", str(td / "rig_info.json"),
                                                            "--out", str(td / "r6.blend")]))
        check("Blender: --rig-info plants both feet and the bake passes (exit 0)",
              code1 == 0 and all(len(rep1["plants"][s]["ranges"]) >= 2 for s in SIDES)
              and rep1["slide_after_m"]["p95"] <= 0.015 and len(rep1["sole_offsets"]) == 4,
              (code1, rep1.get("slide_after_m"), rep1.get("gates")))
        # mixamo names, the preset, and contacts
        bm, _ = synthetic_gait(creep=0.04, with_root=True, mixamo=True)
        bm.save(td / "mixamo.bvh")
        arm, act = import_bvh(td / "mixamo.bvh")
        rep2, code2 = run_blender(parser().parse_args(["--armature", arm.name, "--action", act.name, "--frame-range", "1",
                                                       str(bm.n_frames), "--legs", "mixamo", "--contacts",
                                                       str(td / "c.json"), "--out", str(td / "mx.blend")]))
        check("Blender: --legs mixamo bakes (exit 0)", code2 == 0 and rep2["legs"] == "mixamo"
              and rep2["slide_after_m"]["p95"] <= 0.003, (code2, rep2.get("slide_after_m")))
        # Auto-Rig Pro's bone names, mapped by rig_info's contract_names; readings in contract names
        arp = {"Root": "c_traj", "Hips": "root.x", "UpperLeg.L": "thigh_stretch.l", "LowerLeg.L": "leg_stretch.l",
               "Foot.L": "foot.l", "Toes.L": "toes_01.l", "UpperLeg.R": "thigh_stretch.r",
               "LowerLeg.R": "leg_stretch.r", "Foot.R": "foot.r", "Toes.R": "toes_01.r"}
        b6.names = [arp[n] for n in b6.names]
        b6.save(td / "arp.bvh")
        (td / "arp_info.json").write_text(json.dumps({"twocam": {
            "ground": {"Foot.L": 0.13, "Toes.L": 0.06, "Foot.R": 0.13, "Toes.R": 0.06},
            "contract_names": {v: k for k, v in arp.items() if k != "Root"}}}))
        _, Wb = b6.fk()
        rn = [k for k in arp if k != "Root"]
        (td / "readings.json").write_text(json.dumps({"reading_names": rn, "reading_joints": (
            Wb[:, [b6.names.index(arp[n]) for n in rn]] @ Y_TO_Z.T).tolist()}))
        arm, act = import_bvh(td / "arp.bvh")
        rep3, code3 = run_blender(parser().parse_args(["--armature", arm.name, "--action", act.name, "--frame-range", "1",
                                                       str(b6.n_frames), "--legs", "contract", "--rig-info",
                                                       str(td / "arp_info.json"), "--readings", str(td / "readings.json"),
                                                       "--out", str(td / "arp.blend"), "--samples-out",
                                                       str(td / "arp.npz")]))
        with np.load(td / "arp.npz") as z:
            rnames = [str(x) for x in z["reading_names"]] if "reading_names" in z.files else []
        check("Blender: Auto-Rig Pro names through contract_names bake, the samples carry the readings (exit 0)",
              code3 == 0 and rep3["leg_joints"]["l"][0] == "thigh_stretch.l" and len(rep3["sole_offsets"]) == 4
              and "foot.l" in rnames and rep3["readings"]["matched"] == 9,
              (code3, rep3.get("gates"), rep3.get("readings"), rep3.get("refused")))
    ok = all(c["ok"] for c in checks)
    print(json.dumps({"selftest_blender": "pass" if ok else "fail", "checks": len(checks),
                      "failed": [c for c in checks if not c["ok"]]}, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    code = main()
    if in_blender():
        sys.stdout.flush()
        import os
        os._exit(code)
    sys.exit(code)
