#!/usr/bin/env python3
"""motion_metrics.py — gates on one clip's joint positions: feet, ground, jitter, limits, loop, root, pops.

Offline and engine-free: the input is the clip's world joint positions per frame, however they were
sampled (Blender, a Unity batchmode lab, a video-to-motion model, the two-camera solve).

usage:
    motion_metrics.py SAMPLES.json|SAMPLES.npz [--out REPORT.json] [--state walk|run|idle|default]
                      [--loop] [--in-place] [--root NAME] [--feet l=FOOT,TOE --feet r=FOOT,TOE]
                      [--floor 0.0|auto] [--travel-mps VX,VY] [--two-view TWO_VIEW.json]
                      [gate options below]
    motion_metrics.py --selftest

SAMPLES.json (schema "motion-samples/1"), metres, Z up (`"up": "y"` turns a Y-up file), one row per frame:
    {"schema": "motion-samples/1", "clip": "runner_walk", "fps": 30,
     "joints": {"Hips": [[x, y, z], ...], "foot.L": [...], "toe.L": [...], ...},
     "root": "Hips",                                   default: Root, Hips, hips, pelvis, Pelvis
     "feet": {"l": ["foot.L", "toe.L"], "r": ["foot.R", "toe.R"]},
     "contacts": {"l": [p, ...], "r": [p, ...]},       optional per-frame contact probability
     "segments": [["upper_arm.L", "forearm.L"], ...],  optional parent -> child, for pops
     "limits": [{"name": "knee.L", "chain": ["thigh.L", "shin.L", "foot.L"],
                 "min_deg": 0, "max_deg": 150}, ...],  optional: bend at the middle joint
     "travel_mps": [vx, vy],                           optional: an in-place loop's travel speed
     "source": {"root": [[x, y, z], ...], "k": 1.0},   optional: the retarget's source root and the
                                                       scale it was given (translation check)
     "two_view": {...},                                optional: the two-camera route's block (below)
     "sole_offsets": {"foot.L": 0.07, ...},            optional: a foot joint's rest height over its sole
     "reading_joints": [[[x, y, z], ...], ...],        optional: frames x reading_names x 3, the joints read
     "reading_names": ["Hips", ...]}                   straight from the source (the two views), for pops
SAMPLES.npz: `positions` (frames, joints, 3), `names` (joints,), `fps`; optional `contacts`
(frames, 2: l, r), `reading_joints` with `reading_names`, and `meta`, a JSON string holding any of
the optional keys above.
--root, --feet and --travel-mps override the file (brt_retarget's `in_place_travel_mps` is the
travel an in-place retarget took out).

Plant (one definition, the same in unity-animation's motion-metrics.md and foot-lock-and-prop-ik.md):
  a foot is planted over a run of at least 3 frames where its sole is under 4 cm above the floor and
  its ground-relative horizontal speed is under 0.15 m/s; an in-place loop gets its travel speed
  (`travel_mps`) added back before the speed test, and supplied contact probabilities (>= 0.5)
  define the plant instead, the detector then reported beside them.
The foot point is the mean of the foot's joints, its sole the lowest of their heights, each minus its
`sole_offsets` entry when given (an ankle stands 7 cm over the floor at rest; without the offset its
sole never comes under 4 cm and no plant is found). The floor is Z 0 (the contract puts the origin
between the feet); `--floor auto` reads the 5th percentile of both soles (after the offsets).

Metrics and gates (a gate appears only when its input exists):
  foot slide     inside a plant, the foot point's horizontal distance from the plant's first frame.
                 Gated p95 <= --slide-p95 (0.015 m) and max <= --slide-max (0.03 m).
  plants         counted per foot (`plants_per_foot`) and in total (`plants_found`, as contact_bake
                 reports it). Gated `plants_min_per_foot` (the fewest on a foot) >= 1 with --state
                 walk or run, and on any clip where a foot's sole is under the plant height for
                 >= 20 % of the frames (`grounded`; then only those feet): a foot on the ground that
                 never plants is skating faster than the plant speed, and a detector that sees
                 nothing hides every slide. With sole_offsets, a foot that moves and finds no plant
                 is named in `warnings` (never gated).
  penetration    floor minus sole, frames under the floor. Gated max <= --penetration-max (0.01 m).
  jitter         acceleration of every joint after removing its smooth part (a centred moving
                 average over ~0.1 s, at least 3 frames), |second difference| x fps^2.
                 Gated p95 <= --jitter-p95 (20 m/s^2). The raw acceleration p95 is reported.
                 Confirm the default on a clean clip of the same capture type first: when a clean
                 clip fails, its contacts are sharp; set --jitter-p95 once for that capture type,
                 never per clip.
  joint limits   frames whose bend at a limit's middle joint (0 = straight) leaves [min, max]
                 by more than --limit-tol (2 deg). Gated 0.
  loop           the 3D period and best cut, ported from sprite-from-video's video_loop.py with
                 the mean joint distance (root's horizontal position removed) in place of the pixel
                 distance: lag profile, smallest minimum within 15 % of the deepest, half-step
                 guard for a gait, the start whose wrap is most like one ordinary step. With
                 --loop: periodicity >= 0.15 and seam <= --seam-max (2.0 mean steps), and a period
                 must exist. Reported otherwise.
  root drift     horizontal distance of the root between the first and last frame (across the
                 cut's wrap, with --loop), as sampled (travel_mps is not added), gated <=
                 --root-drift-max (0.05 m) with --in-place; the root's vertical drift across the
                 same frames, gated <= the same with --loop (a root-motion loop travels, it does
                 not climb); lateral p95 off the fitted straight path is reported.
  pops           per segment, the angular speed of its direction; a pop is a single-frame spike
                 (w > 1.8 x max(neighbours, 30 deg/s) and >= 3 deg extra in that frame) or a
                 two-frame one (both frames over 1.8 x the frames outside, >= 3 deg extra in
                 total, neither a single). Twist about the segment is invisible to positions.
                 --pops-min-move M (default 0) raises the extra to the angle that moves the
                 segment's end by M metres (median length), so reading noise on a short segment
                 is not a pop; read motion (twocam, video) passes 0.03. Gated count <= --pops-max (0).
                 With `reading_joints`, a segment whose two ends were read is held to the readings'
                 own speed (1.2 x it + the excess, as a clip reference): a spike the readings show
                 too is a fast move in the source, listed as `pops_in_source` and not gated. Both
                 `count`s are events, one per frame and joint: the segments that leave one joint
                 turn with that bone, so the shin and an Auto-Rig Pro twist segment beside it
                 (leg_stretch>foot, leg_stretch>leg_twist) are one event; `segments` counts the
                 segments that spiked and `list` names each.
  translation    with a `source` block: the output root's largest displacement (travel_mps added
                 back, for an in-place output) against k x the source root's. Gated: a source that moves over 1 cm needs at least 10 % of it
                 in the output (a retarget that dropped the root's translation fails).
  two view       with a `two_view` block (or --two-view FILE):
                 {"agreement": 0.86 | [per frame], "reprojection_px": 2.4 | [per frame] |
                  {"p95": 2.4}, "frame_height_px": 768}
                 Gated: agreement (mean) >= --agreement-min (0.8); reprojection p95 <=
                 --reproj-p95-px (8 px at a 768 px frame height, scaled to the given height).

Prints one JSON report (also to --out): per-metric p50/p95/max/n, plants, loop, gates, ok.
Exit codes: 0 every gate passed (or --selftest passed); 2 a gate failed; 1 refused input
(unreadable file, wrong schema, a named joint missing, frame counts that differ, a non-finite
value), a usage error or a failed --selftest. clip_metrics.py, which imports the plant helpers from
here, uses the same codes. Requires numpy.
"""
# ---------------------------------------------------------------------------
# Third-party code. The period and cut search (lag_profile, local_minima,
# repeat_context, detect_cycle, LoopProfile and its window, STATE_PROFILES and
# the constants named in them) is ported from
# skills/sprite-from-video/scripts/video_loop.py, itself ported from sprite-gen
#   https://github.com/aldegad/sprite-gen
#   commit dddcc1013f7b5587a5eabd8609a5b42dd8aa7c26
#   Apache License 2.0 — see THIRD_PARTY_NOTICES.md.
# Changes: the distance is the mean joint distance with the root's horizontal
# position removed, not a thumbnail difference; the half/third-period screen,
# one-shot and once detectors are not carried; a refusal is a failed gate.
# ---------------------------------------------------------------------------
from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SCHEMA = "motion-samples/1"
SIDES = ("l", "r")
ROOT_NAMES = ("Root", "root", "Hips", "hips", "pelvis", "Pelvis")

# the plant: one definition
PLANT_H_MAX = 0.04          # m above the floor
PLANT_V_MAX = 0.15          # m/s, ground-relative
PLANT_MIN_FRAMES = 3
CONTACT_MIN = 0.5           # a supplied contact probability at or over this is a plant
GROUNDED_SHARE = 0.2        # a foot whose sole is under PLANT_H_MAX this share of frames must plant

# gate defaults
SLIDE_P95 = 0.015
SLIDE_MAX = 0.03
PENETRATION_MAX = 0.01
JITTER_P95 = 20.0           # m/s^2, on the residual after the smooth part
JITTER_WINDOW_S = 0.1
LIMIT_TOL_DEG = 2.0
ROOT_DRIFT_MAX = 0.05
POPS_MAX = 0
AGREEMENT_MIN = 0.8
REPROJ_P95_PX = 8.0
REPROJ_REF_HEIGHT = 768
TRAVEL_MIN_M = 0.01         # a source root that moves less is "no translation"
TRAVEL_KEPT_SHARE = 0.10

# pops (the same constants as unity-animation's MotionMetricsSampler.cs)
SPIKE_RATIO = 1.8
SPIKE_EXCESS_DEG = 3.0      # extra degrees in one frame (180 deg/s at 60 fps)
SPEED_FLOOR = 30.0          # deg/s
CLIP_FACTOR = 1.2           # with a reference: faster than the clip by this, plus the excess
POPS_MIN_MOVE_M = 0.0       # extra endpoint travel a spike must add; > 0 for read (noisy) motion

# loop search (ported, see the header)
SEAM_RATIO_MAX = 2.0
PERIODICITY_MIN = 0.15
GAIT_DOUBLE_TOL = 0.25
GAIT_DOUBLE_SEARCH = 3
GAIT_NEAR_EXACT_STEP_FRACTION = 0.10


class Refused(Exception):
    pass


# ------------------------------------------------------------------------------- shared pieces
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


def runs(on, min_frames) -> list:
    """(start, end) inclusive of every run of True at least `min_frames` long."""
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


def plants(sole, xy, fps, h_max=PLANT_H_MAX, v_max=PLANT_V_MAX, min_frames=PLANT_MIN_FRAMES) -> list:
    """The plant definition: sole under h_max and horizontal speed under v_max for min_frames."""
    on = (np.asarray(sole) < h_max) & (speed_xy(xy, fps) < v_max)
    return runs(on, min_frames)


def slide(xy, ranges) -> np.ndarray:
    d = [np.linalg.norm(xy[a:b + 1] - xy[a], axis=1) for a, b in ranges]
    return np.concatenate(d) if d else np.zeros(0)


def segment_speed_deg(parent: np.ndarray, child: np.ndarray, fps: float) -> np.ndarray:
    """Angular speed (deg/s) of the parent -> child direction; frame i is the step into i (w[0] = w[1])."""
    d = child - parent
    d = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)
    if len(d) < 2:
        return np.zeros(len(d))
    cos = np.clip(np.sum(d[1:] * d[:-1], axis=1), -1.0, 1.0)
    w = np.degrees(np.arccos(cos)) * fps
    return np.concatenate([[w[0]], w])


def pops(w: np.ndarray, fps: float, clip=None, min_excess_deg: float = 0.0) -> list:
    """Frames of one segment's angular speed `w` that pop: [(frame, "single"|"wide")].

    single at i: w[i] > 1.8 x max(max(w[i-1], w[i+1]), 30) and (w[i] - that) / fps >= 3 deg;
    wide at i, i+1: both over 1.8 x max(max(w[i-1], w[i+2]), 30), (w[i] + w[i+1] - 2 x that) / fps
    >= 3 deg, neither a single. With `clip` (the reference's speed at the same frames) the spike
    must also beat 1.2 x clip + the excess, which separates a pop from a fast swing.
    `min_excess_deg` raises the 3 deg excess (motion_metrics sets it from --pops-min-move)."""
    out, n = [], len(w)
    excess = max(SPIKE_EXCESS_DEG, min_excess_deg) * fps
    single = np.zeros(n, bool)
    for i in range(1, n - 1):
        nb = max(w[i - 1], w[i + 1])
        if w[i] > SPIKE_RATIO * max(nb, SPEED_FLOOR) and w[i] - nb >= excess:
            if clip is None or w[i] > CLIP_FACTOR * clip[i] + excess:
                single[i] = True
                out.append((i, "single"))
    for i in range(1, n - 2):
        if single[i] or single[i + 1]:
            continue
        nb = max(w[i - 1], w[i + 2])
        lo = SPIKE_RATIO * max(nb, SPEED_FLOOR)
        if min(w[i], w[i + 1]) > lo and (w[i] + w[i + 1] - 2 * nb) >= excess:
            if clip is None or w[i] + w[i + 1] > CLIP_FACTOR * (clip[i] + clip[i + 1]) + 2 * excess:
                out.append((i, "wide"))
    return out


def bend_deg(a, b, c) -> np.ndarray:
    """Bend at b, 0 when a, b, c are in a straight line."""
    u, v = b - a, c - b
    cos = np.sum(u * v, axis=1) / np.maximum(np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1), 1e-12)
    return np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))


def gate(name, value, limit, ok) -> dict:
    return {"name": name, "value": value, "limit": limit, "ok": bool(ok)}


# ------------------------------------------------------------------- loop search (ported)
@dataclass(frozen=True)
class LoopProfile:
    min_frac: float
    max_frac: float
    gait: bool = False
    min_seconds: float = 0.0
    window_seconds: tuple = None

    def window(self, n, fps):
        if self.window_seconds is not None:
            lo = max(4, round(self.window_seconds[0] * fps))
            return lo, max(lo + 2, min(n // 2, round(self.window_seconds[1] * fps)))
        lo = max(4, round(n * self.min_frac))
        return lo, max(lo + 2, round(n * self.max_frac))


STATE_PROFILES = {
    "idle": LoopProfile(0.60, 0.95),
    "walk": LoopProfile(0.06, 0.31, gait=True, min_seconds=0.6, window_seconds=(0.5, 1.6)),
    "run": LoopProfile(0.07, 0.23, gait=True, min_seconds=0.35, window_seconds=(0.3, 1.2)),
    "default": LoopProfile(0.10, 0.45),
}


def joint_distances(P: np.ndarray, root: np.ndarray) -> np.ndarray:
    """D[i, j]: mean joint distance between frames i and j, each frame's root xy taken out."""
    Q = P.copy()
    Q[:, :, :2] -= root[:, None, :2]
    n = len(Q)
    D = np.zeros((n, n))
    for i in range(n):
        D[i] = np.linalg.norm(Q - Q[i], axis=2).mean(axis=1)
    return D


def lag_profile(D, lo, hi):
    n = len(D)
    return {L: float(np.mean([D[j, j + L] for j in range(0, n - L, 2)]))
            for L in range(max(2, lo // 2), hi + 1) if L < n}


def local_minima(prof):
    return [L for L in prof if L - 1 in prof and L + 1 in prof and prof[L] <= prof[L - 1] and prof[L] <= prof[L + 1]]


def repeat_context(D, start, length, step):
    radius = max(1, length // 4)
    first = max(0, start - radius)
    stop = min(len(D) - length, start + radius + 1)
    if stop <= first:
        return {"context_repeat_over_step": 0.0}
    error = float(np.mean([D[j, j + length] for j in range(first, stop)]))
    return {"context_repeat_over_step": error / step if step > 0 else math.inf}


def detect_cycle(D, min_len, max_len, gait_floor=None):
    """Global period, the half-step guard, then the wrap-compatible start."""
    n = len(D)
    max_len = min(max_len, n - 2)
    if min_len < 2 or max_len < min_len:
        raise Refused(f"the loop window [{min_len}, {max_len}] is empty for {n} frames")
    adjacent = np.array([D[i, i + 1] for i in range(n - 1)])
    prof = lag_profile(D, min_len, max_len)
    cands = local_minima(prof) if prof else []
    cands = [L for L in cands if min_len <= L <= max_len] or list(range(min_len, max_len + 1))
    deepest = min(prof[L] for L in cands)
    period = min(L for L in cands if prof[L] <= deepest * 1.15 + 1e-6)
    guard = {"applied": False}
    if gait_floor is not None and period < gait_floor:
        doubles = [L for L in cands if abs(L - 2 * period) <= GAIT_DOUBLE_SEARCH and L <= max_len]
        if not doubles:
            doubles = [L for L in (2 * period - 1, 2 * period, 2 * period + 1) if L in prof and L <= max_len]
        L2 = min(doubles, key=lambda L: prof[L]) if doubles else None
        if L2 is not None and prof[L2] <= prof[period] * (1 + GAIT_DOUBLE_TOL) + 1e-6:
            guard = {"applied": True, "from": period, "to": L2}
            period = L2
        else:
            raise Refused(f"no periodic cycle: the only repeat is one step ({period} frames, under the gait "
                          f"floor of {gait_floor}) and nothing near twice that repeats as well")
    mean = float(np.mean(list(prof.values())))
    if gait_floor is not None and period >= gait_floor and not guard["applied"]:
        step = float(adjacent.mean())
        repeat_fraction = prof[period] / step if step > 0 else math.inf
        doubles = [L for L in cands if abs(L - 2 * period) <= 1]
        if doubles and repeat_fraction > GAIT_NEAR_EXACT_STEP_FRACTION:
            L2 = min(doubles, key=lambda L: prof[L])
            if (prof[L2] <= prof[period] * (1 + GAIT_DOUBLE_TOL) + 1e-6 and mean > 0
                    and (mean - prof[L2]) / mean >= PERIODICITY_MIN):
                guard = {"applied": True, "from": period, "to": L2, "reason": "ambiguous-harmonic"}
                period = L2
    periodicity = (mean - prof[period]) / mean if mean > 0 else 0.0
    best, best_score = None, math.inf
    for L in (period - 1, period, period + 1):
        if L < min_len or L > max_len:
            continue
        for i in range(0, n - L):
            seam = float(D[i + L - 1, i])
            inner = float(adjacent[i:i + L - 1].mean())
            ratio = seam / inner if inner > 0 else math.inf
            score = abs(math.log(ratio)) if 0 < ratio < math.inf else math.inf
            if gait_floor is not None:
                score += repeat_context(D, i, L, inner)["context_repeat_over_step"]
            if best is None or score < best_score:
                best_score = score
                best = {"start": i, "length": L, "seam_m": seam, "inner_step_m": inner, "seam_ratio": ratio}
    if best is None:
        raise Refused("no cut fits the window")
    best.update(period=period, periodicity=round(periodicity, 4), half_period_guard=guard,
                window=[min_len, max_len])
    return best


# ---------------------------------------------------------------------------------- input
def _arr(rows, what, n=None, dims=3):
    a = np.asarray(rows, float)
    if dims and (a.ndim != 2 or a.shape[1] != dims):
        raise Refused(f"{what} must be rows of [x, y, z]")
    if not dims and a.ndim != 1:
        raise Refused(f"{what} must be a list of numbers")
    if not np.all(np.isfinite(a)):
        raise Refused(f"{what} has a non-finite value")
    if n is not None and len(a) != n:
        raise Refused(f"{what} has {len(a)} frames, expected {n}")
    return a


def load(path: str) -> dict:
    p = Path(path)
    if p.suffix.lower() == ".npz":
        try:
            with np.load(p, allow_pickle=False) as f:
                z = {k: f[k] for k in f.files}
        except (OSError, ValueError) as e:
            raise Refused(f"unreadable npz: {e}")
        for need in ("positions", "names", "fps"):
            if need not in z:
                raise Refused(f"npz has no {need!r}")
        pos = np.asarray(z["positions"], float)
        names = [str(s) for s in z["names"]]
        if pos.ndim != 3 or pos.shape[1:] != (len(names), 3):
            raise Refused("npz positions must be (frames, len(names), 3)")
        doc = json.loads(str(z["meta"])) if "meta" in z else {}
        doc.update(schema=SCHEMA, fps=float(z["fps"]),
                   joints={nm: pos[:, j].tolist() for j, nm in enumerate(names)})
        if "contacts" in z:
            c = np.asarray(z["contacts"], float)
            if c.ndim != 2 or c.shape[1] != 2:
                raise Refused("npz contacts must be (frames, 2): l, r")
            doc["contacts"] = {"l": c[:, 0].tolist(), "r": c[:, 1].tolist()}
        if "reading_joints" in z:   # the source's own joints, as arrays beside the positions
            if "reading_names" not in z:
                raise Refused("npz reading_joints without reading_names")
            doc["reading_joints"] = np.asarray(z["reading_joints"], float).tolist()
            doc["reading_names"] = [str(s) for s in z["reading_names"]]
        return doc
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refused(f"unreadable json: {e}")


def parse(doc: dict, a) -> dict:
    if doc.get("schema") != SCHEMA:
        raise Refused(f"schema is {doc.get('schema')!r}, expected {SCHEMA!r}")
    fps = doc.get("fps")
    if not isinstance(fps, (int, float)) or not fps > 0:
        raise Refused("fps missing or not positive")
    raw = doc.get("joints")
    if not isinstance(raw, dict) or not raw:
        raise Refused("joints missing")
    up = (doc.get("up") or "z").lower()
    J, n = {}, None
    for name, rows in raw.items():
        v = _arr(rows, f"joints.{name}", n)
        n = len(v)
        J[name] = v[:, [0, 2, 1]] * [1, -1, 1] if up == "y" else v
    if n < 4:
        raise Refused("fewer than 4 frames")
    feet = dict(doc.get("feet") or {})
    for spec in a.feet or []:
        side, _, names = spec.partition("=")
        feet[side.strip().lower()] = [s.strip() for s in names.split(",") if s.strip()]
    if sorted(feet) != list(SIDES) or not all(feet[s] for s in SIDES):
        raise Refused("feet must name the joints of both feet: {\"l\": [...], \"r\": [...]}")
    root = a.root or doc.get("root") or next((r for r in ROOT_NAMES if r in J), None)
    names = [j for s in SIDES for j in feet[s]] + ([root] if root else [])
    missing = [j for j in names if j not in J]
    if root is None or missing:
        raise Refused(f"joints missing: {missing or ['root']}")
    contacts = {}
    for s, rows in (doc.get("contacts") or {}).items():
        contacts[s] = _arr(rows, f"contacts.{s}", n, dims=0)
    segs = [tuple(s) for s in doc.get("segments") or []]
    if "parents" in doc:
        segs += [(p, c) for c, p in doc["parents"].items() if p]
    for s in segs:
        if len(s) != 2 or any(j not in J for j in s):
            raise Refused(f"segment {list(s)} names a missing joint")
    limits = list(doc.get("limits") or [])
    for lim in limits:
        if len(lim.get("chain", [])) != 3 or any(j not in J for j in lim["chain"]):
            raise Refused(f"limit {lim.get('name')!r} needs a chain of three present joints")
    source = doc.get("source")
    if source is not None:
        source = {"root": _arr(source.get("root"), "source.root"), "k": float(source.get("k", 1.0))}
    two_view = doc.get("two_view")
    if a.two_view:
        try:
            two_view = json.loads(Path(a.two_view).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise Refused(f"unreadable two-view file: {e}")
    offsets = {}
    for j, h in (doc.get("sole_offsets") or {}).items():
        if j not in J:
            raise Refused(f"sole_offsets names a missing joint {j!r}")
        if not isinstance(h, (int, float)) or not math.isfinite(h):
            raise Refused(f"sole_offsets.{j} is not a number")
        offsets[j] = float(h)
    readings = None
    if doc.get("reading_joints") is not None:
        rn = [str(x) for x in doc.get("reading_names") or []]
        R = np.asarray(doc["reading_joints"], float)
        if R.ndim != 3 or R.shape != (n, len(rn), 3):
            raise Refused(f"reading_joints must be ({n} frames, {len(rn)} reading_names, 3), got {list(R.shape)}")
        if not np.all(np.isfinite(R)):
            raise Refused("reading_joints has a non-finite value")
        if up == "y":
            R = R[..., [0, 2, 1]] * [1, -1, 1]
        readings = {nm: R[:, i] for i, nm in enumerate(rn)}
    travel = doc.get("travel_mps") or [0.0, 0.0]
    if a.travel_mps:
        travel = [float(v) for v in a.travel_mps.split(",")]
    travel = np.asarray(travel, float)
    if travel.shape != (2,) or not np.all(np.isfinite(travel)):
        raise Refused("travel_mps must be [vx, vy]")
    return {"fps": float(fps), "n": n, "J": J, "feet": feet, "root": root, "contacts": contacts,
            "segments": segs, "limits": limits, "source": source, "two_view": two_view, "travel": travel,
            "clip": doc.get("clip"), "offsets": offsets, "readings": readings}


def _per_frame_or_summary(v, what) -> dict:
    if isinstance(v, dict):
        if "p95" not in v:
            raise Refused(f"two_view.{what} needs p95")
        return {k: float(v[k]) for k in ("p50", "p95", "max") if k in v}
    if isinstance(v, (int, float)):
        return {"p50": float(v), "p95": float(v), "max": float(v)}
    return summary(_arr(v, f"two_view.{what}", dims=0))


# -------------------------------------------------------------------------------- measure
def measure(doc: dict, a) -> dict:
    m = parse(doc, a)
    fps, n, J = m["fps"], m["n"], m["J"]
    t = np.arange(n) / fps
    shift = np.outer(t, m["travel"])               # in-place loop: add the travel back
    names = list(J)
    P = np.stack([J[k] for k in names], 1)
    root = J[m["root"]]
    out = {"tool": "motion_metrics.py", "clip": m["clip"], "frames": n, "fps": fps, "root": m["root"]}
    gates = []

    off = m["offsets"]
    soles = {s: np.min(np.stack([J[j][:, 2] - off.get(j, 0.0) for j in m["feet"][s]]), axis=0) for s in SIDES}
    if off:
        out["sole_offsets"] = {j: off[j] for s in SIDES for j in m["feet"][s] if j in off}
    warnings = []
    if a.floor == "auto":
        floor = float(np.percentile(np.concatenate([soles["l"], soles["r"]]), 5))
    else:
        floor = float(a.floor)
    out["floor_m"] = floor

    # plants and slide
    sl, speeds, plant_rec = [], [], {}
    for s in SIDES:
        foot = np.mean(np.stack([J[j] for j in m["feet"][s]]), axis=0)
        xy = foot[:, :2] + shift
        kin = plants(soles[s] - floor, xy, fps, a.h_max, a.v_max, a.min_frames)
        rec = {"detector": len(kin), "coverage": round(sum(e - b + 1 for b, e in kin) / n, 4),
               "grounded": round(float(np.mean(soles[s] - floor < a.h_max)), 4)}
        rng = kin
        if s in m["contacts"]:
            rng = runs(m["contacts"][s] >= CONTACT_MIN, a.min_frames)
            on_c = np.zeros(n, bool)
            on_k = np.zeros(n, bool)
            for b, e in rng:
                on_c[b:e + 1] = True
            for b, e in kin:
                on_k[b:e + 1] = True
            union = np.sum(on_c | on_k)
            rec.update(source="contacts", contacts=len(rng),
                       coverage=round(float(on_c.mean()), 4),
                       detector_iou=round(float(np.sum(on_c & on_k) / union), 4) if union else None)
        else:
            rec["source"] = "detector"
        rec["ranges"] = [[int(b), int(e)] for b, e in rng]
        plant_rec[s] = rec
        if off and not rng and (np.percentile(speed_xy(xy, fps), 95) > a.v_max or np.ptp(soles[s]) > a.h_max):
            warnings.append(f"foot {s} moves but no plant was found: its slide is not measured (look at its "
                            "sole height; --state walk|run gates plants_min_per_foot)")
        sl.append(slide(xy, rng))
        for b, e in rng:
            path = float(np.sum(np.linalg.norm(np.diff(xy[b:e + 1], axis=0), axis=1)))
            speeds.append(path / max((e - b) / fps, 1e-9))
    out["plants"] = plant_rec
    out["plants_per_foot"] = {s: len(plant_rec[s]["ranges"]) for s in SIDES}
    out["plants_found"] = sum(out["plants_per_foot"].values())   # the total, as contact_bake reports it
    out["foot_slide_m"] = summary(np.concatenate(sl))
    out["plant_speed_mps"] = summary(speeds)
    v = out["foot_slide_m"]
    gates += [gate("foot_slide_p95_m", v["p95"], f"<= {a.slide_p95}", v["p95"] <= a.slide_p95),
              gate("foot_slide_max_m", v["max"], f"<= {a.slide_max}", v["max"] <= a.slide_max)]
    grounded = [s for s in SIDES if plant_rec[s]["grounded"] >= GROUNDED_SHARE]
    if a.state in ("walk", "run") or grounded:
        need = SIDES if a.state in ("walk", "run") else grounded
        fewest = min(out["plants_per_foot"][s] for s in need)
        gates.append(gate("plants_min_per_foot", fewest, ">= 1 per foot" + ("" if need == SIDES else
                          f" on the ground ({', '.join(need)})"), fewest >= 1))

    # ground penetration
    depth = np.maximum(0.0, floor - np.minimum(soles["l"], soles["r"]))
    out["penetration_m"] = summary(depth)
    out["penetration_frames"] = int(np.sum(depth > 1e-6))
    out["lowest_joint_m"] = float(P[:, :, 2].min())
    gates.append(gate("penetration_max_m", float(depth.max()), f"<= {a.penetration_max}",
                      depth.max() <= a.penetration_max))

    # jitter
    acc = np.linalg.norm(np.diff(P, 2, axis=0), axis=2) * fps * fps
    out["accel_mps2"] = summary(acc)
    w = max(3, int(round(JITTER_WINDOW_S * fps)) | 1)
    if n >= w + 2:
        kern = np.ones(w) / w
        pad = w // 2
        Pp = np.pad(P, ((pad, pad), (0, 0), (0, 0)), mode="edge")
        smooth = np.apply_along_axis(lambda x: np.convolve(x, kern, mode="valid"), 0, Pp)
        res = (P - smooth)[pad:n - pad]
        jit = np.linalg.norm(np.diff(res, 2, axis=0), axis=2) * fps * fps
    else:
        jit = acc
    out["jitter_mps2"] = summary(jit)
    out["jitter_window_frames"] = w
    jv = out["jitter_mps2"]["p95"]
    gates.append(gate("jitter_p95_mps2", jv, f"<= {a.jitter_p95}", jv <= a.jitter_p95))

    # joint limits
    if m["limits"]:
        rows = []
        for lim in m["limits"]:
            b = bend_deg(*(J[j] for j in lim["chain"]))
            lo, hi = float(lim.get("min_deg", 0.0)), float(lim.get("max_deg", 180.0))
            bad = np.flatnonzero((b < lo - a.limit_tol) | (b > hi + a.limit_tol))
            rows.append({"name": lim.get("name") or lim["chain"][1], "min_deg": float(b.min()),
                         "max_deg": float(b.max()), "frames_outside": int(bad.size),
                         "first": int(bad[0]) if bad.size else None})
        out["joint_limits"] = rows
        total = sum(r["frames_outside"] for r in rows)
        gates.append(gate("joint_limit_frames", total, 0, total == 0))

    # loop: period and cut
    prof = STATE_PROFILES.get(a.state or "default", STATE_PROFILES["default"])
    lo, hi = prof.window(n, fps)
    floor_frames = round(prof.min_seconds * fps) if prof.gait else None
    cut = None
    try:
        cut = detect_cycle(joint_distances(P, root), lo, hi, floor_frames)
        out["loop"] = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in cut.items()}
    except Refused as e:
        out["loop"] = {"refused": str(e), "window": [lo, hi]}
    if a.loop:
        gates.append(gate("loop_period_found", cut is not None, True, cut is not None))
        if cut is not None:
            gates += [gate("loop_periodicity", cut["periodicity"], f">= {PERIODICITY_MIN}",
                           cut["periodicity"] >= PERIODICITY_MIN),
                      gate("loop_seam_ratio", cut["seam_ratio"], f"<= {a.seam_max}",
                           cut["seam_ratio"] <= a.seam_max)]

    # root drift
    rxy = root[:, :2]                              # as sampled: an in-place root stays put
    b, e = (cut["start"], cut["start"] + cut["length"] - 1) if (a.loop and cut) else (0, n - 1)
    # a loop's last shipped frame is one step before the wrap: drift is read across the wrap
    e_wrap = min(e + 1, n - 1) if (a.loop and cut) else e
    drift = float(np.linalg.norm(rxy[e_wrap] - rxy[b]))
    vdrift = float(abs(root[e_wrap, 2] - root[b, 2]))
    out["root_drift_m"] = drift
    out["root_vertical_drift_m"] = vdrift
    c = rxy - rxy.mean(axis=0)
    if np.linalg.norm(c) > 1e-9:
        d = np.linalg.svd(c, full_matrices=False)[2][0]
        lateral = np.abs(c[:, 0] * d[1] - c[:, 1] * d[0])
    else:
        lateral = np.zeros(n)
    out["root_lateral_m"] = summary(lateral)
    if a.in_place:
        gates.append(gate("root_drift_m", drift, f"<= {a.root_drift_max}", drift <= a.root_drift_max))
    if a.loop:
        gates.append(gate("root_vertical_drift_m", vdrift, f"<= {a.root_drift_max}", vdrift <= a.root_drift_max))

    # pops; with readings, a spike the source shows too is listed apart and not gated
    R = m["readings"]
    if m["segments"]:
        found, in_src, events, src_events = [], [], set(), set()
        for p, ch in m["segments"]:
            seg_len = float(np.median(np.linalg.norm(J[ch] - J[p], axis=1)))
            floor = float(np.degrees(a.pops_min_move / max(seg_len, 1e-6))) if a.pops_min_move > 0 else 0.0
            w = segment_speed_deg(J[p], J[ch], fps)
            every = pops(w, fps, min_excess_deg=floor)
            kept = every
            if R is not None and p in R and ch in R:
                kept = pops(w, fps, clip=segment_speed_deg(R[p], R[ch], fps), min_excess_deg=floor)
            hit = {g for f, kind in kept for g in ((f,) if kind == "single" else (f, f + 1))}
            found += [{"segment": f"{p}>{ch}", "frame": int(f), "kind": kind} for f, kind in kept]
            events |= {(int(f), p) for f, _ in kept}   # one event per frame and joint, as in the source
            src = [(int(f), kind) for f, kind in every if f not in hit]
            in_src += [{"segment": f"{p}>{ch}", "frame": f, "kind": kind} for f, kind in src]
            src_events |= {(f, p) for f, _ in src}   # one event per frame and joint: its segments turn together
        out["pops"] = {"count": len(events), "segments": len(found), "list": found[:60]}
        if R is not None:
            out["pops_in_source"] = {"count": len(src_events), "segments": len(in_src), "list": in_src[:60]}
        gates.append(gate("pops", len(events), f"<= {a.pops_max}", len(events) <= a.pops_max))
    else:
        out["pops"] = {"count": None, "skipped": "no segments given"}

    # translation kept
    if m["source"] is not None:
        src, k = m["source"]["root"], m["source"]["k"]
        src_disp = float(np.linalg.norm(src - src[0], axis=1).max()) * k
        rg = root + np.concatenate([shift, np.zeros((n, 1))], axis=1)
        out_disp = float(np.linalg.norm(rg - rg[0], axis=1).max())
        out["translation"] = {"source_scaled_m": src_disp, "output_m": out_disp, "k": k,
                              "ratio": out_disp / src_disp if src_disp > 0 else None}
        if src_disp > TRAVEL_MIN_M:
            gates.append(gate("translation_kept", round(out_disp / src_disp, 4),
                              f">= {TRAVEL_KEPT_SHARE} of k x source", out_disp >= TRAVEL_KEPT_SHARE * src_disp))

    # two-view block
    tv = m["two_view"]
    if tv is not None:
        rec = {}
        if "agreement" in tv:
            ag = tv["agreement"]
            ag = float(ag) if isinstance(ag, (int, float)) else float(np.mean(_arr(ag, "two_view.agreement", dims=0)))
            rec["agreement"] = ag
            gates.append(gate("two_view_agreement", ag, f">= {a.agreement_min}", ag >= a.agreement_min))
        if "reprojection_px" in tv:
            rp = _per_frame_or_summary(tv["reprojection_px"], "reprojection_px")
            h = float(tv.get("frame_height_px") or REPROJ_REF_HEIGHT)
            limit = a.reproj_p95_px * h / REPROJ_REF_HEIGHT
            rec["reprojection_px"] = rp
            gates.append(gate("two_view_reprojection_p95_px", rp["p95"], f"<= {round(limit, 3)}",
                              rp["p95"] <= limit))
        out["two_view"] = rec

    if warnings:   # only with sole_offsets: an input without them reports as before
        out["warnings"] = warnings
    out["gates"] = gates
    out["ok"] = all(g["ok"] for g in gates)
    return out


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser() -> argparse.ArgumentParser:
    p = UsageParser(prog="motion_metrics.py", description=__doc__.split("\n")[0])
    p.add_argument("samples")
    p.add_argument("--out")
    p.add_argument("--state", choices=sorted(STATE_PROFILES), default=None)
    p.add_argument("--loop", action="store_true", help="gate the period, the seam and the root drift")
    p.add_argument("--in-place", action="store_true", help="gate the root drift")
    p.add_argument("--root")
    p.add_argument("--feet", action="append", help="l=FOOT,TOE (repeat for r)")
    p.add_argument("--floor", default="0.0", help="metres, or auto")
    p.add_argument("--travel-mps", help="VX,VY: an in-place loop's travel speed (replaces travel_mps)")
    p.add_argument("--two-view")
    p.add_argument("--h-max", type=float, default=PLANT_H_MAX)
    p.add_argument("--v-max", type=float, default=PLANT_V_MAX)
    p.add_argument("--min-frames", type=int, default=PLANT_MIN_FRAMES)
    p.add_argument("--slide-p95", type=float, default=SLIDE_P95)
    p.add_argument("--slide-max", type=float, default=SLIDE_MAX)
    p.add_argument("--penetration-max", type=float, default=PENETRATION_MAX)
    p.add_argument("--jitter-p95", type=float, default=JITTER_P95)
    p.add_argument("--limit-tol", type=float, default=LIMIT_TOL_DEG)
    p.add_argument("--seam-max", type=float, default=SEAM_RATIO_MAX)
    p.add_argument("--root-drift-max", type=float, default=ROOT_DRIFT_MAX)
    p.add_argument("--pops-max", type=int, default=POPS_MAX)
    p.add_argument("--pops-min-move", type=float, default=POPS_MIN_MOVE_M)
    p.add_argument("--agreement-min", type=float, default=AGREEMENT_MIN)
    p.add_argument("--reproj-p95-px", type=float, default=REPROJ_P95_PX)
    return p


def run(argv) -> tuple:
    a = parser().parse_args(argv)
    try:
        if a.floor != "auto":
            float(a.floor)
        rep = measure(load(a.samples), a)
    except (ValueError, TypeError, KeyError, Refused) as e:
        rep, code = {"ok": False, "refused": str(e)}, 1
    else:
        code = 0 if rep["ok"] else 2
    text = json.dumps(rep, indent=1)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    return code, rep, text


# --------------------------------------------------------------------------------- selftest
def _body(n=96, fps=30.0, period=32, slide_per_plant=0.0, sink=0.0, noise=0.0, travel=1.2, seed=0):
    """A walking skeleton travelling +Y at `travel` m/s: two feet that plant for half the cycle
    (each foot's stance is half a period, the feet alternate), pelvis bobbing, two arms swinging.
    A planted foot creeps `slide_per_plant` m forward over its stance; `sink` puts every sole
    that deep under the floor during stance."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    J = {}
    stride = travel * period / fps                # one full cycle covers this
    for k, s in enumerate(SIDES):
        x = 0.1 if s == "l" else -0.1
        phase = ((t + k * period // 2) % period) / period        # 0..0.5 stance, 0.5..1 swing
        cyc = (t + k * period // 2) // period
        stance = phase < 0.5
        # stance: fixed at the cycle's plant point (+ creep); swing: moves 2x forward to the next one
        base = cyc * stride
        u = np.where(stance, 0.0, (phase - 0.5) / 0.5)
        y = base + np.where(stance, slide_per_plant * phase / 0.5, slide_per_plant + (stride - slide_per_plant) * (3 * u**2 - 2 * u**3))
        y = y - k * stride / 2
        z = np.where(stance, -sink, 0.10 * np.sin(np.pi * u))
        J[f"foot.{s.upper()}"] = np.stack([np.full(n, x), y, z + 0.08], 1)
        J[f"toe.{s.upper()}"] = np.stack([np.full(n, x), y + 0.15, z + 0.01], 1)
    rootx = np.zeros(n)
    rooty = travel * t / fps
    rootz = 0.95 + 0.02 * np.cos(4 * np.pi * t / period)
    J["Hips"] = np.stack([rootx, rooty, rootz], 1)
    for k, s in enumerate(SIDES):
        sw = 0.4 * np.sin(2 * np.pi * t / period + k * np.pi)
        sh = J["Hips"] + [0.2 if s == "l" else -0.2, 0.0, 0.5]
        el = sh + np.stack([np.zeros(n), 0.3 * np.sin(sw), -0.3 * np.cos(sw)], 1)
        wr = el + np.stack([np.zeros(n), 0.25 * np.sin(sw + 0.3), -0.25 * np.cos(sw + 0.3)], 1)
        J[f"upper_arm.{s.upper()}"], J[f"forearm.{s.upper()}"], J[f"hand.{s.upper()}"] = sh, el, wr
    if noise:
        J = {k: v + rng.normal(0, noise, v.shape) for k, v in J.items()}
    doc = {"schema": SCHEMA, "clip": "runner_walk", "fps": fps, "root": "Hips",
           "joints": {k: v.tolist() for k, v in J.items()},
           "feet": {"l": ["foot.L", "toe.L"], "r": ["foot.R", "toe.R"]},
           "segments": [[f"upper_arm.{s}", f"forearm.{s}"] for s in "LR"] +
                       [[f"forearm.{s}", f"hand.{s}"] for s in "LR"],
           "limits": [{"name": f"elbow.{s}", "chain": [f"upper_arm.{s}", f"forearm.{s}", f"hand.{s}"],
                       "min_deg": 0, "max_deg": 150} for s in "LR"]}
    return doc


def selftest() -> int:
    checks, failed = 0, []

    def check(name, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failed.append(name)

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"

        def go(doc, *flags):
            p.write_text(json.dumps(doc))
            return run([str(p), *flags])

        # 1. a clean walk: every gate passes, plants cover each stance, the period is 32 frames
        code, rep, _ = go(_body(), "--state", "walk", "--loop")
        check("clean walk: exit 0", code == 0)
        check("clean walk: plants on both feet", all(len(rep["plants"][s]["ranges"]) >= 2 for s in SIDES))
        pm = next((g for g in rep["gates"] if g["name"] == "plants_min_per_foot"), {})
        check("clean walk: plants_per_foot per foot, plants_found their total, the gate the fewest",
              rep["plants_per_foot"] == {s: len(rep["plants"][s]["ranges"]) for s in SIDES}
              and rep["plants_found"] == sum(rep["plants_per_foot"].values())
              and pm.get("value") == min(rep["plants_per_foot"].values()) and pm.get("ok"))
        check("clean walk: stance coverage >= 10 %", all(rep["plants"][s]["coverage"] >= 0.10 for s in SIDES))
        check("clean walk: slide ~0", rep["foot_slide_m"]["max"] < 1e-9)
        check("clean walk: period 32", rep["loop"].get("period") == 32 and rep["loop"]["length"] in (31, 32, 33))
        check("clean walk: seam about one step", 0.5 <= rep["loop"]["seam_ratio"] <= SEAM_RATIO_MAX)
        check("clean walk: no pops", rep["pops"]["count"] == 0)

        # 2. known slide: each plant creeps 2 cm (the slow creep stays under the plant speed);
        #    the slide max reads 2 cm and the p95 gate of 1.5 cm fails
        code, rep, _ = go(_body(slide_per_plant=0.02), "--state", "walk")
        mx = rep["foot_slide_m"]["max"]
        check("known slide: max reads the creep", 0.015 < mx <= 0.02 + 1e-9)
        check("known slide: exit 2", code == 2 and not next(g for g in rep["gates"]
                                                           if g["name"] == "foot_slide_p95_m")["ok"])
        code, rep, _ = go(_body(slide_per_plant=0.04), "--state", "walk")
        sm = next(g for g in rep["gates"] if g["name"] == "foot_slide_max_m")
        check("4 cm creep: the max gate fails too", code == 2 and not sm["ok"] and abs(sm["value"] - 0.04) < 1e-9)

        # ... a body that travels 25 % faster than its legs step (a retarget with the wrong k): the
        #    stance feet skate at 0.3 m/s, no plant is found, the slide reads 0, and plants_min_per_foot
        #    fails without --state because the feet stay on the ground
        doc = _body()
        n = len(doc["joints"]["Hips"])
        extra = np.stack([np.zeros(n), 0.3 * np.arange(n) / 30.0, np.zeros(n)], 1)
        doc["joints"] = {k: (np.asarray(v) + extra).tolist() for k, v in doc["joints"].items()}
        code, rep, _ = go(doc)
        pf = next((g for g in rep["gates"] if g["name"] == "plants_min_per_foot"), None)
        check("skating on the ground: plants_min_per_foot fails without --state, exit 2",
              code == 2 and pf is not None and not pf["ok"] and rep["foot_slide_m"]["max"] == 0.0)

        # 3. penetration: the feet sink 3 cm during stance
        code, rep, _ = go(_body(sink=0.03), "--state", "walk")
        check("penetration: reads 2 cm (the toe joint sits 1 cm over the sole)",
              abs(rep["penetration_m"]["max"] - 0.02) < 1e-6)
        check("penetration: exit 2", code == 2 and any(g["name"] == "penetration_max_m" and not g["ok"]
                                                       for g in rep["gates"]))

        # 4. jitter: 6 mm of noise on every joint fails; the clean walk passed above
        code, rep, _ = go(_body(noise=0.006), "--state", "walk")
        check("jitter: exit 2", code == 2 and any(g["name"] == "jitter_p95_mps2" and not g["ok"]
                                                  for g in rep["gates"]))

        # 5. a pop: the left forearm's hand jumps for one frame
        doc = _body()
        hand = np.asarray(doc["joints"]["hand.L"])
        el = np.asarray(doc["joints"]["forearm.L"])
        hand[40] = el[40] + [0.25, 0.0, 0.0]
        doc["joints"]["hand.L"] = hand.tolist()
        code, rep, _ = go(doc)
        check("pop: exactly one", rep["pops"]["count"] == 1 and rep["pops"]["list"][0]["frame"] == 40)
        check("pop: exit 2", code == 2)
        code, rep, _ = go(doc, "--pops-min-move", "0.03")
        check("pop: still one with a 3 cm move floor", rep["pops"]["count"] == 1)
        nd = _body()
        rng = np.random.default_rng(7)
        for s in "LR":
            h = np.asarray(nd["joints"][f"hand.{s}"])
            nd["joints"][f"hand.{s}"] = (h + rng.normal(0, 0.006, h.shape)).tolist()
        code, rep, _ = go(nd)
        noisy = rep["pops"]["count"]
        code, rep, _ = go(nd, "--pops-min-move", "0.03")
        check("reading noise: pops at floor 0, none at 3 cm", noisy > 0 and rep["pops"]["count"] == 0)

        # ... the same pop in the readings is a fast move in the source: listed, not gated; a pop the
        #     readings do not have is the solve's own and fails
        names = list(doc["joints"])
        src = np.stack([np.asarray(doc["joints"][k]) for k in names], 1)
        src = src + np.random.default_rng(3).normal(0, 0.001, src.shape)
        code, rep, _ = go(dict(doc, reading_joints=src.tolist(), reading_names=names), "--pops-min-move", "0.03")
        check("pop in the readings: pops_in_source, the gate passes, exit 0",
              code == 0 and rep["pops"]["count"] == 0 and rep["pops_in_source"]["count"] == 1
              and rep["pops_in_source"]["list"][0]["frame"] == 40)
        # ... a twist joint half way down the forearm, a second segment from the elbow (as Auto-Rig Pro's
        #     forearm_twist beside the hand): both segments show the pop, and it is one event in the source
        tw = dict(doc, joints=dict(doc["joints"]), segments=doc["segments"] + [["forearm.L", "forearm_twist.L"]])
        tw["joints"]["forearm_twist.L"] = ((np.asarray(doc["joints"]["forearm.L"])
                                            + np.asarray(doc["joints"]["hand.L"])) / 2).tolist()
        tn = list(tw["joints"])
        src = np.stack([np.asarray(tw["joints"][k]) for k in tn], 1)
        src = src + np.random.default_rng(3).normal(0, 0.001, src.shape)
        code, rep, _ = go(dict(tw, reading_joints=src.tolist(), reading_names=tn), "--pops-min-move", "0.03")
        check("a pop on the hand's and the twist's segment from one joint: one event, both segments listed, exit 0",
              code == 0 and rep["pops_in_source"]["count"] == 1 and rep["pops_in_source"]["segments"] == 2
              and {e["segment"] for e in rep["pops_in_source"]["list"]} == {"forearm.L>hand.L", "forearm.L>forearm_twist.L"})
        code, rep, _ = go(tw, "--pops-min-move", "0.03")
        check("the same pop without readings: gated as one event, both segments listed, exit 2",
              code == 2 and rep["pops"]["count"] == 1 and rep["pops"]["segments"] == 2
              and {e["segment"] for e in rep["pops"]["list"]} == {"forearm.L>hand.L", "forearm.L>forearm_twist.L"})
        clean = _body()
        src = np.stack([np.asarray(clean["joints"][k]) for k in names], 1)
        code, rep, _ = go(dict(doc, reading_joints=src.tolist(), reading_names=names), "--pops-min-move", "0.03")
        check("pop the readings do not have: gated, exit 2",
              code == 2 and rep["pops"]["count"] == 1 and rep["pops_in_source"]["count"] == 0)
        check("reading_joints of the wrong shape: exit 1",
              go(dict(doc, reading_joints=src[:-1].tolist(), reading_names=names))[0] == 1)

        # 5b. feet whose joints stand 6 cm higher (an ankle over its sole): without sole_offsets no plant is
        #     found and the slide reads nothing; with them the plants come back and a 3 cm creep fails
        def raised(creep):
            doc = _body(slide_per_plant=creep)
            for s in "LR":
                for k in (f"foot.{s}", f"toe.{s}"):
                    doc["joints"][k] = (np.asarray(doc["joints"][k]) + [0, 0, 0.06]).tolist()
            return doc
        offs = {f"foot.{s}": 0.14 for s in "LR"} | {f"toe.{s}": 0.07 for s in "LR"}
        code, rep, _ = go(raised(0.03), "--state", "walk")
        pf = next(g for g in rep["gates"] if g["name"] == "plants_min_per_foot")
        check("raised feet, no offsets: no plants, slide reads 0, plants_min_per_foot fails",
              code == 2 and not pf["ok"] and rep["foot_slide_m"]["max"] == 0.0)
        code, rep, _ = go(dict(raised(0.0), sole_offsets=offs), "--state", "walk")
        check("raised feet with sole_offsets: plants on both feet, exit 0",
              code == 0 and all(len(rep["plants"][s]["ranges"]) >= 2 for s in SIDES))
        code, rep, _ = go(dict(raised(0.03), sole_offsets=offs), "--state", "walk")
        sp = next(g for g in rep["gates"] if g["name"] == "foot_slide_p95_m")
        check("raised feet with sole_offsets: a 3 cm creep fails the slide, exit 2",
              code == 2 and not sp["ok"] and abs(rep["foot_slide_m"]["max"] - 0.03) < 1e-6)
        code, rep, _ = go(dict(raised(0.0), sole_offsets=offs), "--floor", "auto")
        check("raised feet with sole_offsets: --floor auto reads the sole floor", code == 0
              and abs(rep["floor_m"]) < 1e-6)
        low = {k: v - 0.06 for k, v in offs.items()}
        code, rep, _ = go(dict(raised(0.03), sole_offsets=low))
        check("offsets too small, no --state: no plants, a warning names both feet",
              not any(rep["plants"][s]["ranges"] for s in SIDES) and len(rep["warnings"]) == 2)
        check("sole_offsets naming a missing joint: exit 1", go(dict(raised(0.0), sole_offsets={"heel.L": 0.02}))[0] == 1)

        # 6. a joint limit: an elbow bent past 150 degrees on one frame
        doc = _body()
        up = np.asarray(doc["joints"]["upper_arm.R"])
        el = np.asarray(doc["joints"]["forearm.R"])
        hand = np.asarray(doc["joints"]["hand.R"])
        hand[10] = el[10] + 0.25 * (up[10] - el[10]) / np.linalg.norm(up[10] - el[10])  # folded back: 180
        doc["joints"]["hand.R"] = hand.tolist()
        code, rep, _ = go(doc)
        lim = next(g for g in rep["gates"] if g["name"] == "joint_limit_frames")
        check("joint limit: one frame outside, exit 2", lim["value"] == 1 and code == 2)

        # 7. a loop whose end does not come back: the arms swing wider every frame -> seam or period fails
        doc = _body()
        for s in "LR":
            sh = np.asarray(doc["joints"][f"upper_arm.{s}"])
            for nm in (f"forearm.{s}", f"hand.{s}"):
                j = np.asarray(doc["joints"][nm])
                grow = 1 + np.linspace(0, 1.5, len(j))[:, None]
                doc["joints"][nm] = (sh + (j - sh) * grow).tolist()
        code, rep, _ = go(doc, "--state", "walk", "--loop")
        seam = next(g for g in rep["gates"] if g["name"] == "loop_seam_ratio")
        check("broken loop: the seam fails, exit 2", code == 2 and not seam["ok"])
        # ... a pose that only jitters has no period: periodicity fails, the seam alone would pass
        doc = _body(travel=0.0)
        noise = np.random.default_rng(2)
        doc["joints"] = {k: (np.asarray(v)[:1] + noise.normal(0, 0.05, (len(v), 3))).tolist()
                         for k, v in doc["joints"].items()}
        code, rep, _ = go(doc, "--loop")
        per = next(g for g in rep["gates"] if g["name"] == "loop_periodicity")
        check("no period: periodicity fails, exit 2", code == 2 and not per["ok"])
        # ... and a walk shorter than two strides finds no cycle at all
        code, rep, _ = go(_body(n=40), "--state", "walk", "--loop")
        found = next(g for g in rep["gates"] if g["name"] == "loop_period_found")
        check("too short for a stride: no period, exit 2", code == 2 and not found["ok"])

        # 8. in place: the same walk with the travel taken out of every joint and declared as
        #    travel_mps reads the same plants; without the declaration the feet never plant
        doc = _body()
        n = len(doc["joints"]["Hips"])
        off = np.stack([np.zeros(n), 1.2 * np.arange(n) / 30.0, np.zeros(n)], 1)
        doc["joints"] = {k: (np.asarray(v) - off).tolist() for k, v in doc["joints"].items()}
        code0, rep0, _ = go(doc, "--state", "walk")
        check("in place undeclared: no plants, plants_min_per_foot fails", code0 == 2 and any(
            g["name"] == "plants_min_per_foot" and not g["ok"] for g in rep0["gates"]))
        code, rep, _ = go(doc, "--state", "walk", "--in-place", "--travel-mps", "0,1.2")
        check("in place, travel on the command line: exit 0", code == 0)
        doc["travel_mps"] = [0.0, 1.2]
        code, rep, _ = go(doc, "--state", "walk", "--in-place")
        check("in place declared: exit 0", code == 0)
        doc_ip = dict(doc, source={"root": _body()["joints"]["Hips"], "k": 1.0})
        code, rep, _ = go(doc_ip, "--state", "walk", "--in-place")
        check("in place declared: translation_kept reads the travel back, exit 0",
              code == 0 and abs(rep["translation"]["ratio"] - 1.0) < 1e-6)
        # ... and a root that wanders 20 cm sideways over the clip fails the drift gate
        side = np.stack([0.2 * np.arange(n) / (n - 1), np.zeros(n), np.zeros(n)], 1)
        wander = dict(doc, joints={k: (np.asarray(v) + side).tolist() for k, v in doc["joints"].items()})
        code, rep, _ = go(wander, "--state", "walk", "--in-place")
        check("in place wandering: root drift fails, exit 2", code == 2 and any(
            g["name"] == "root_drift_m" and not g["ok"] for g in rep["gates"]))
        # ... and a loop whose root climbs 10 cm per cycle fails the vertical drift gate
        climb = np.stack([np.zeros(n), np.zeros(n), 0.1 * np.arange(n) / 32], 1)
        rising = dict(doc, joints={k: (np.asarray(v) + climb).tolist() for k, v in doc["joints"].items()})
        code, rep, _ = go(rising, "--state", "walk", "--loop", "--floor", "auto")
        check("climbing loop: vertical drift fails, exit 2", any(
            g["name"] == "root_vertical_drift_m" and not g["ok"] for g in rep["gates"]) and code == 2)

        # 9. a retarget that dropped the root's translation fails; one that kept it passes
        src = _body()
        doc = _body()
        doc["source"] = {"root": src["joints"]["Hips"], "k": 1.0}
        code, rep, _ = go(doc)
        check("translation kept: exit 0", code == 0 and rep["translation"]["ratio"] > 0.99)
        hips = np.asarray(doc["joints"]["Hips"])
        dropped = {k: (np.asarray(v) - (hips - hips[0])).tolist() for k, v in doc["joints"].items()}
        doc["joints"] = dropped
        code, rep, _ = go(doc)
        tk = next(g for g in rep["gates"] if g["name"] == "translation_kept")
        check("translation dropped: exit 2", code == 2 and not tk["ok"])

        # 10. contacts define the plant; a two-view block gates agreement and reprojection
        doc = _body()
        n = len(doc["joints"]["Hips"])
        ph = lambda k: ((np.arange(n) + k * 16) % 32) / 32        # noqa: E731
        doc["contacts"] = {"l": (ph(0) < 0.5).astype(float).tolist(), "r": (ph(1) < 0.5).astype(float).tolist()}
        doc["two_view"] = {"agreement": [0.9] * n, "reprojection_px": {"p95": 3.0}, "frame_height_px": 768}
        code, rep, _ = go(doc)
        check("contacts: plants from contacts, exit 0", code == 0 and rep["plants"]["l"]["source"] == "contacts"
              and rep["plants"]["l"]["detector_iou"] > 0.8)
        doc["two_view"] = {"agreement": 0.6, "reprojection_px": [12.0] * n}
        code, rep, _ = go(doc)
        tvg = [g for g in rep["gates"] if g["name"].startswith("two_view")]
        check("two view: both gates fail, exit 2", code == 2 and len(tvg) == 2 and not any(g["ok"] for g in tvg))

        # 11. npz input reads the same as json
        doc = _body()
        names = list(doc["joints"])
        pos = np.stack([np.asarray(doc["joints"][k]) for k in names], 1)
        meta = {k: doc[k] for k in ("root", "feet", "segments", "limits")}
        z = Path(d) / "s.npz"
        np.savez(z, positions=pos, names=np.array(names), fps=30.0, meta=json.dumps(meta))
        code, rep_npz, _ = run([str(z), "--state", "walk"])
        code_j, rep_j, _ = go(doc, "--state", "walk")
        check("npz: same result as json", code == code_j == 0
              and rep_npz["foot_slide_m"] == rep_j["foot_slide_m"] and rep_npz["loop"] == rep_j["loop"])
        # ... readings as npz arrays: a pop they show is in the source; without them it is gated
        hand = pos[:, names.index("hand.L")]
        hand[40] = pos[40, names.index("forearm.L")] + [0.25, 0.0, 0.0]
        np.savez(z, positions=pos, names=np.array(names), fps=30.0, meta=json.dumps(meta),
                 reading_joints=pos + np.random.default_rng(3).normal(0, 0.001, pos.shape), reading_names=np.array(names))
        code, rep_npz, _ = run([str(z), "--pops-min-move", "0.03"])
        check("npz reading_joints: the pop is in the source, exit 0", code == 0 and rep_npz["pops"]["count"] == 0
              and rep_npz["pops_in_source"]["count"] == 1)
        np.savez(z, positions=pos, names=np.array(names), fps=30.0, meta=json.dumps(meta))
        code, rep_npz, _ = run([str(z), "--pops-min-move", "0.03"])
        check("npz without readings: the same pop is gated, exit 2", code == 2 and rep_npz["pops"]["count"] == 1
              and "pops_in_source" not in rep_npz)
        np.savez(z, positions=pos, names=np.array(names), fps=30.0, meta=json.dumps(meta), reading_joints=pos)
        check("npz reading_joints without reading_names: exit 1", run([str(z)])[0] == 1)

        # 12. refused inputs exit 1
        bad = _body()
        bad["joints"]["Hips"] = bad["joints"]["Hips"][:-1]
        check("frame mismatch: exit 1", go(bad)[0] == 1)
        bad = _body()
        bad["feet"] = {"l": ["foot.L"]}
        check("one foot named: exit 1", go(bad)[0] == 1)
        check("wrong schema: exit 1", go(dict(_body(), schema="other"))[0] == 1)
        check("unreadable file: exit 1", run([str(Path(d) / "none.json")])[0] == 1)
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": checks, "failed": failed}))
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
