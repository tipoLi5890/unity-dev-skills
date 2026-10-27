#!/usr/bin/env python3
"""video_loop.py — keyed clip frames -> one clean loop or one-shot: equal-canvas frames + frames.json.

Reads the keyed frames video_frames.py wrote (DIR/keyed/ and the source fps in
DIR/frames.report.json; or any folder of RGBA PNGs with --source-fps), finds
the cut, takes the body's drift out, subsamples to --fps and writes the frames
codex-visual's handoff contract describes (reference/animation-scripts.md §4).

Distances. Every frame is shrunk to fit 96 px (PIL thumbnail), its colour
multiplied by its alpha; D[i, j] is the mean absolute difference of two such
thumbnails (RGBA, 0..1). The lag profile is P[L] = mean over j = 0, 2, 4 … of
D[j, j+L], for L from half the window floor to its ceiling.

Loop (--mode loop, and auto first):
  window     walk 0.5–1.6 s, run 0.3–1.2 s (ceiling capped at half the clip);
             idle 60–95 % of the clip; jump, attack and anything else
             10/11–45 % (attack: ceiling 2.5 s, with half a second of context).
  period     the smallest local minimum of P inside the window that is within
             15 % of the deepest one (exact repeats also dip at 2x and 3x).
  half step  a walk under 0.6 s (run 0.35 s) is one step: the minimum within
             3 frames of 2P is taken when P[2P] <= 1.25·P[P], else refused.
             Above that floor, a minimum at 2P±1 about as deep (and a repeat
             not near-exact) is also taken — two phase occurrences rather than
             one stride on one leg — and recorded as a fault (exit 3).
  periodicity (mean P − P[period]) / mean P >= 0.15, else refused (exit 2;
             idle is exempt; in auto a jump/attack/other state fails over to
             the one-shot detector instead).
  screen     at half and a third of the period, the deepest local minimum
             within a frame: one that repeats (periodicity >= 0.15) and is no
             shorter than the window floor (gait floor) makes the loop a
             multi-cycle suspect — a fault, exit 3, never cut shorter.
  start      over L in {P−1, P, P+1} and every start i, the least
             |log(D[i+L−1, i] / mean adjacent step inside the cut)| (for a gait
             plus how far the quarter-cycle around the cut is from the same
             poses one cycle later, over a step).
  seam       the cut's wrap over its mean step, read on the subsampled frames and
             again at the source rate (on the moved frames when the drift ramp
             moved them): either over --seam-max (2.0) refused, exit 2.

One-shot (--mode oneshot, and auto's failover): a rest -> action -> rest cut
whose end poses match (return within a quarter of the departure), whose peak
stands 3 MADs over the departure curve's median (or moved 0.4 of the body's
mass), whose action spans at least 4 frames with two rest frames kept on each
side and departs at least 3 ordinary steps; of those within 95 % of the
strongest departure, the shortest. `loop: false`, `hold_last: false`.

Once (--mode once): an action that ends in a held pose. The steps D[k, k+1]
are read against the clip's own rest level (10th percentile) and range (90th):
the action starts at the first step past a quarter of that range (two rest
frames kept before it), and the cut ends on the first frame after the largest
step from which every step stays under a tenth of that range for 0.2 s.
`loop: false`, `hold_last: true`.

Drift. A loop: the last frame's top 60 % (head and torso, from the first
frame's box) is registered against the first's over ±24 px, and that offset is
spread as a whole-pixel ramp round(dx·k/L) across the cycle. A one-shot or once:
a straight line fitted to the body's horizontal centre is removed (horizontal
only; the vertical travel is the action).

Output (OUT = --out-dir, NAME = --name):
  OUT/NAME/NAME_000.png …  one canvas (the frames' union box + --margin on every
                           side, so the floor line sits --margin above the
                           bottom), no resampling; under `ground` each frame
                           moved up or down whole pixels onto frame 0's feet
                           line
  OUT/NAME/frames.json     tool, producer, source{file, sha256, fps}, canvas,
                           pivot, pivot_norm (the first frame's foot centre from
                           the bottom-left), fps_hint (frames / cycle seconds),
                           loop, hold_last, register{mode ground: the feet line
                           (the core silhouette's lowest row, as audit_frames
                           reads it) spreads by at most max(3 px, 2 % of the
                           body) and every frame is seated on frame 0's; keep:
                           more (a jump, a run's flight), nothing seated},
                           verdict{ok, faults[]},
                           cycle_frames, cycle_seconds, cut, period, seam,
                           drift, subsample{indices, steps: the source frames
                           between shipped ones, even}, frames[{index, file,
                           source_frame}]
  OUT/NAME.gif             preview, beside the frame folder (never in it)
  OUT/NAME.report.json     the whole decision, written on every run

Examples
  video_loop.py work/runner_walk --state walk --name runner_walk --out-dir out
  video_loop.py work/sentry_idle --state idle --name sentry_idle --out-dir out --fps 10
  video_loop.py work/runner_launch --state jump --name runner_launch --out-dir out
  video_loop.py work/runner_launch --state jump --mode once --name runner_land --out-dir out
  video_loop.py --selftest

stdout: one JSON object (the summary). Exit codes:
  0  frames and frames.json written, verdict ok (or --selftest passed)
  1  bad arguments, unreadable frames, no source fps, or a failed --selftest
  2  refused, nothing handed over: no period (flat profile), only a half
     stride (nothing near twice a too-short period repeats), no one-shot
     return, no settled end, or a seam over --seam-max
  3  uncertain: frames and frames.json written with verdict.ok false and the
     faults named (a multi-cycle suspect, or a cut that holds two phase
     occurrences) — look at the preview and re-run with --max-len to settle it

Requires numpy and Pillow (~/.codex/imagegen-venv/bin/python).
"""
# ---------------------------------------------------------------------------
# Third-party code. Portions are ported, with identifiers and structure
# adapted, from sprite-gen
#   https://github.com/aldegad/sprite-gen
#   commit dddcc1013f7b5587a5eabd8609a5b42dd8aa7c26
#   Apache License 2.0 — see THIRD_PARTY_NOTICES.md.
#
#   video/loop.py    ANALYSIS_SIZE, SEAM_RATIO_MAX, PERIODICITY_MIN, the
#                    ONE_SHOT_* constants, GAIT_DOUBLE_TOL, GAIT_DOUBLE_SEARCH,
#                    GAIT_NEAR_EXACT_STEP_FRACTION, BODY_ANCHOR_BAND,
#                    BODY_ANCHOR_SEARCH, LoopProfile and its window(),
#                    STATE_PROFILES, _small_features (small_features),
#                    frame_masses, _distances (distances), _repeat_context
#                    (repeat_context), detect_cycle, periodicity_floor,
#                    detect_one_shot, body_centre, foot_centre,
#                    body_wrap_offset, ramp_frames (the ramp in drift_loop),
#                    the cycle subsampling of build_strip and the
#                    resampled-seam reading and re-read on the moved cells of
#                    the seam gate
#   video/period.py  DIVISORS, NEAR, EXACT, _returns, local_minima, measure
#                    (pose only), verdict and screen
#
# Changes: arrays instead of PIL images after loading; a strip and its WebP
# are replaced by equal-canvas frames + frames.json; the above-floor
# ambiguous-harmonic doubling and the screen's suspects are faults with exit 3
# instead of a review flag; the leg-signal evidence, motion-auto anchoring,
# RIFE repair, seam bridge, wrap blend, size hold, pinned and once-return
# cycles, --cycle fixed and the step screen are not carried; the one-shot
# search ceiling is the failover's in --mode oneshot too; the one-shot drift
# is a fitted horizontal trend of the body centre removed; the seam is read
# at the source rate as well as on the subsampled frames; the feet line is
# read on codex-visual's core silhouette and seated onto one line, or the set
# is `keep`; `once` is this
# file's own (sprite-gen's nonloop cut is not ported); refusals exit 2.
# ---------------------------------------------------------------------------
import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

ANALYSIS_SIZE = 96          # thumbnail edge for the distance matrix
SEAM_RATIO_MAX = 2.0        # loop wrap / mean step inside the cycle
PERIODICITY_MIN = 0.15      # the period must dip this far below the profile mean
GAIT_DOUBLE_TOL = 0.25      # half-step guard: 2P taken when P[2P] <= (1 + this) * P[P]
GAIT_DOUBLE_SEARCH = 3      # frames either side of 2P where the full gait's own minimum may sit
GAIT_NEAR_EXACT_STEP_FRACTION = 0.10  # a repeat this close (in steps) is exact: no ambiguity
ONE_SHOT_MIN_CONTRAST = 3.0  # peak over the departure curve's median, in MADs
ONE_SHOT_MIN_MOVED = 0.4     # ... or departure over the end poses' mean mass
ONE_SHOT_MIN_COHERENCE = 3.0  # departure at least this many ordinary steps
ONE_SHOT_MIN_ACTIVE = 4      # frames the action spans at least
ONE_SHOT_PAD = 2             # rest frames kept on each side of the action
ONE_SHOT_MIN_LEN = 4
ONE_SHOT_CEILING = 0.9       # one-shot search ceiling: this share of the clip (or the window's, if longer)
ONCE_SETTLE_SECONDS = 0.2    # once: the end pose holds this long
ONCE_ACTIVE_SHARE = 0.25     # once: a step past rest + this share of the step range is action
ONCE_SETTLE_SHARE = 0.10     # once: steps under rest + this share of the range are settled
BODY_ANCHOR_BAND = 0.6       # top share of the first frame's box registered for the wrap offset
BODY_ANCHOR_SEARCH = 24      # px either side searched
FOOT_BAND = 0.2              # foot centre: the lowest share of the frame's own box
ALPHA_SOLID = 8              # alpha at or over this counts for centres and boxes
CORE_SOLID = 127             # feet line: alpha above this is the silhouette ...
CORE_OPEN_PX = 4             # ... opened by this many px (codex-visual audit_frames' core)
FEET_MAX_PX = 3              # ground: the feet line spreads at most this much (audit_frames --feet-max)
DIVISORS = (2, 3)            # screen: a half and a third of the period
NEAR = 1.0                   # frames either side of period/divisor
EXACT = 0.05                 # a lag closer than this (in steps) returns the same picture
SPANS = ((-1, 0), (0, 1), (-2, 0), (-1, 1), (0, 2))
CROP_PAD = 64                # px kept round the cut's union box while it is moved
PRODUCER = {"skill": "sprite-from-video", "script": "video_loop.py"}
MODES = ("auto", "loop", "oneshot", "once")


class Refused(Exception):
    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


@dataclass(frozen=True)
class LoopProfile:
    min_frac: float
    max_frac: float
    why: str
    periodic: bool = True          # the profile must show a real period (idle is exempt)
    one_shot_ok: bool = False      # auto may fail over to the one-shot detector
    gait: bool = False             # the half-step guard applies
    min_seconds: float = 0.0       # gait floor
    window_seconds: tuple = None   # gait period bounds in seconds
    action_seconds: float = None   # attack: ceiling in seconds with context kept

    def window(self, n, fps):
        if self.action_seconds is not None:
            lo = max(4, round(n * self.min_frac))
            context = max(8, math.ceil(fps * 0.5))
            return lo, min(round(self.action_seconds * fps), n - context)
        if self.window_seconds is not None:
            lo = max(4, round(self.window_seconds[0] * fps))
            return lo, max(lo + 2, min(n // 2, round(self.window_seconds[1] * fps)))
        lo = max(4, round(n * self.min_frac))
        return lo, max(lo + 2, round(n * self.max_frac))


STATE_PROFILES = {
    "idle": LoopProfile(0.60, 0.95, "breathing is slow and not strictly periodic; the lowest seam is a long window",
                        periodic=False),
    "walk": LoopProfile(0.06, 0.31, "full gait = two steps", gait=True, min_seconds=0.6, window_seconds=(0.5, 1.6)),
    "run": LoopProfile(0.07, 0.23, "faster gait", gait=True, min_seconds=0.35, window_seconds=(0.3, 1.2)),
    "jump": LoopProfile(0.11, 0.45, "crouch-spring-land-return", one_shot_ok=True),
    "attack": LoopProfile(0.11, 0.45, "swing and return to ready; half a second of repeat context kept",
                          one_shot_ok=True, action_seconds=2.5),
    "default": LoopProfile(0.10, 0.45, "generic in-place action", one_shot_ok=True),
}


def profile_for(state):
    return STATE_PROFILES.get((state or "").strip().lower(), STATE_PROFILES["default"])


# ---------------------------------------------------------------- distances ----

def small_features(im):
    """96-px thumbnail, colour premultiplied by alpha, flattened RGBA in 0..1."""
    t = im.copy()
    t.thumbnail((ANALYSIS_SIZE, ANALYSIS_SIZE))
    a = np.asarray(t, dtype=np.float32) / 255.0
    rgb = a[..., :3] * a[..., 3:4]
    return np.concatenate([rgb, a[..., 3:4]], axis=-1).reshape(-1)


def distances(flat):
    n = len(flat)
    D = np.zeros((n, n), np.float32)
    for i in range(n):
        D[i] = np.abs(flat - flat[i]).mean(axis=1)
    return D


def lag_profile(D, lo, hi):
    n = len(D)
    return {L: float(np.mean([D[j, j + L] for j in range(0, n - L, 2)])) for L in range(max(2, lo // 2), hi + 1)}


def repeat_context(D, start, length, step):
    """A quarter cycle round the cut against the same poses one cycle later, over a playback step."""
    radius = max(1, length // 4)
    first = max(0, start - radius)
    stop = min(len(D) - length, start + radius + 1)
    if stop <= first:
        return {"context_pair_range": [first, stop], "context_repeat_error": None, "context_repeat_over_step": 0.0}
    error = float(np.mean([D[j, j + length] for j in range(first, stop)]))
    return {"context_pair_range": [first, stop], "context_repeat_error": error,
            "context_repeat_over_step": error / step if step > 0 else math.inf}


# ---------------------------------------------------------- the period screen ----

def local_minima(prof):
    return [L for L in prof if L - 1 in prof and L + 1 in prof and prof[L] <= prof[L - 1] and prof[L] <= prof[L + 1]]


def _returns(D, lag):
    """(off the motion's path, the lag's own distance), both in playback steps, or None."""
    n = len(D)
    reach = max(abs(v) for span in SPANS for v in span)
    js = np.arange(reach, n - lag)
    js = js[(js >= reach) & (js + lag < n)]
    if js.size == 0:
        return None
    x = js + lag
    extra = np.minimum.reduce([D[js + a, x] + D[x, js + b] - D[js + a, js + b] for a, b in SPANS])
    step = float(D[js, js + 1].mean())
    return (float(extra.mean()) / step, float(D[js, x].mean()) / step) if step > 0 else None


def screen(period, D, prof, mean, lowest, floor_why):
    """Candidates at a half and a third of `period`; the ones that repeat are suspects. Nothing is chosen."""
    record = {"period": period, "checked": [], "suspects": []}
    minima = local_minima(prof)
    for k in DIVISORS:
        near = [q for q in minima if abs(q - period / k) <= NEAR and q < period]
        if not near:
            continue
        q = min(near, key=lambda lag: prof[lag])
        row = {"period": q, "of": period, "divisor": k, "cycles": k}
        record["checked"].append(row)
        if q < lowest:
            row.update(verdict=None, why=f"shorter than {floor_why} ({lowest} frames)")
            continue
        row["periodicity"] = round((mean - prof[q]) / mean if mean > 0 else 0.0, 4)
        found = _returns(D, q)
        if found is not None:
            off, dist = found
            row.update(off_path=round(off, 3), distance=round(dist, 3), pose=round(0.0 if dist < EXACT else off / dist, 3))
        if row["periodicity"] < PERIODICITY_MIN:
            row.update(verdict=None, why=f"dips {row['periodicity']:.2f} below the profile mean, under "
                                         f"{PERIODICITY_MIN:.2f}: not a repeat")
        else:
            row.update(verdict="suspect", why=f"repeats {row['periodicity']:.2f} below the profile mean: one cycle of a "
                                              f"loop that holds {k}, or one step of a stride whose steps look alike")
            record["suspects"].append(row)
    return record


# ----------------------------------------------------------------- detectors ----

def periodicity_floor(n, period, partial_repeat):
    coverage = min(1.0, max(0, n - period) / period)
    return PERIODICITY_MIN + (1 - PERIODICITY_MIN) * (1 - coverage) if partial_repeat else PERIODICITY_MIN


def detect_cycle(D, min_len, max_len, gait_floor=None):
    """Global period, the half-step guard, the screen, then the wrap-compatible start."""
    n = len(D)
    max_len = min(max_len, n - 2)
    if min_len < 2 or max_len < min_len:
        raise Refused(f"the window [{min_len}, {max_len}] is empty for {n} frames", {"kind": "periodic"})
    adjacent = np.array([D[i, i + 1] for i in range(n - 1)])
    prof = lag_profile(D, min_len, max_len)
    cands = local_minima({L: prof[L] for L in prof}) if prof else []
    cands = [L for L in cands if min_len <= L <= max_len] or list(range(min_len, max_len + 1))
    deepest = min(prof[L] for L in cands)
    period = min(L for L in cands if prof[L] <= deepest * 1.15 + 1e-4)
    minima_rec = [[L, round(prof[L], 5)] for L in sorted(cands, key=lambda L: prof[L])[:6]]
    guard = {"applied": False}
    if gait_floor is not None and period < gait_floor:
        doubles = [L for L in cands if abs(L - 2 * period) <= GAIT_DOUBLE_SEARCH and L <= max_len]
        if not doubles:
            doubles = [L for L in (2 * period - 1, 2 * period, 2 * period + 1) if L in prof and L <= max_len]
        L2 = min(doubles, key=lambda L: prof[L]) if doubles else None
        if L2 is not None and prof[L2] <= prof[period] * (1 + GAIT_DOUBLE_TOL) + 1e-4:
            guard = {"applied": True, "from": period, "to": L2, "gait_floor": gait_floor,
                     "depth_ratio": round(prof[L2] / prof[period], 3) if prof[period] > 0 else None}
            period = L2
        else:
            ratio = round(prof[L2] / prof[period], 2) if L2 is not None and prof[period] > 0 else None
            guard = {"applied": False, "below_floor": period, "gait_floor": gait_floor, "double_candidate": L2,
                     "double_depth_ratio": ratio}
            raise Refused(
                f"no periodic cycle — the only repeat is one step ({period} frames, under the gait floor of "
                f"{gait_floor}) and nothing near twice that ({2 * period - GAIT_DOUBLE_SEARCH}.."
                f"{2 * period + GAIT_DOUBLE_SEARCH}) repeats within {round(GAIT_DOUBLE_TOL * 100)} % of it"
                + (f" (best {L2}: {ratio}x worse)" if ratio is not None else "")
                + "; the clip shows a half stride, regenerate it",
                {"kind": "periodic", "period_global": period, "half_period_guard": guard, "profile_minima": minima_rec})
    mean = float(np.mean(list(prof.values())))
    if gait_floor is not None and period >= gait_floor and not guard["applied"]:
        step = float(adjacent.mean())
        repeat_fraction = prof[period] / step if step > 0 else math.inf
        doubles = [L for L in cands if abs(L - 2 * period) <= 1]
        if doubles and repeat_fraction > GAIT_NEAR_EXACT_STEP_FRACTION:
            L2 = min(doubles, key=lambda L: prof[L])
            if (prof[L2] <= prof[period] * (1 + GAIT_DOUBLE_TOL) + 1e-4 and mean > 0
                    and (mean - prof[L2]) / mean >= PERIODICITY_MIN):
                guard = {"applied": True, "from": period, "to": L2, "gait_floor": gait_floor,
                         "reason": "ambiguous-harmonic", "depth_ratio": round(prof[L2] / prof[period], 3),
                         "repeat_error_over_step": round(repeat_fraction, 3)}
                period = L2
    periodicity = (mean - prof[period]) / mean if mean > 0 else 0.0
    lowest = max(min_len, gait_floor or 0)
    fundamental = screen(period, D, prof, mean, lowest,
                         "the gait floor" if gait_floor is not None and gait_floor >= min_len else "the window")
    best, best_score = None, math.inf
    for L in (period - 1, period, period + 1):
        if L < min_len or L > max_len:
            continue
        for i in range(0, n - L):
            seam = float(D[i + L - 1, i])
            inner = float(adjacent[i:i + L - 1].mean())
            ratio = seam / inner if inner > 0 else math.inf
            score = abs(math.log(ratio)) if 0 < ratio < math.inf else math.inf
            sel = None
            if gait_floor is not None:
                sel = repeat_context(D, i, L, inner)
                sel["wrap_log_error"] = score
                score += sel["context_repeat_over_step"]
                sel["score"] = score
            if best is None or score < best_score:
                best_score = score
                best = {"start": i, "length": L, "seam": seam, "inner_mean_adjacent": inner, "ratio": ratio}
                if sel is not None:
                    best["selection"] = sel
    best.update(kind="loop", period_global=period, periodicity=round(periodicity, 4), half_period_guard=guard,
                fundamental=fundamental, profile_minima=minima_rec, profile_mean=round(mean, 6),
                window=[min_len, max_len])
    return best


def detect_one_shot(D, min_len, max_len, frame_mass):
    """An observed return pair enclosing a complete excursion (rest -> action -> rest)."""
    n = len(D)
    adjacent = np.diag(D, 1)
    candidates, max_moved = [], 0.0
    shortest = max(ONE_SHOT_MIN_LEN, min_len)
    for start in range(n - ONE_SHOT_MIN_LEN + 1):
        for end in range(start + shortest - 1, min(n, start + max_len)):
            seam = float(D[start, end])
            e = (D[start] + D[end]) / 2
            peak_at = start + int(np.argmax(e[start:end + 1]))
            peak = float(e[peak_at])
            departure = peak - seam / 2
            if departure <= 0 or seam > departure * 0.25:
                continue
            med = float(np.median(e))
            mad = float(np.median(np.abs(e - med))) or 1e-6
            contrast = (peak - med) / mad
            mass = float((frame_mass[start] + frame_mass[end]) / 2)
            moved = departure / mass if mass > 0 else None
            max_moved = max(max_moved, moved or 0)
            if contrast >= ONE_SHOT_MIN_CONTRAST:
                rule, active = "contrast", e > med + ONE_SHOT_MIN_CONTRAST * mad
            elif moved is not None and moved >= ONE_SHOT_MIN_MOVED:
                rule, active = "moved", e > seam / 2 + 0.5 * departure
            else:
                continue
            if not active[peak_at]:
                continue
            a = b = peak_at
            while a > 0 and active[a - 1]:
                a -= 1
            while b + 1 < n and active[b + 1]:
                b += 1
            if b - a + 1 < ONE_SHOT_MIN_ACTIVE or not (start <= a - ONE_SHOT_PAD and end >= b + ONE_SHOT_PAD):
                continue
            inner = float(adjacent[start:end].mean())
            if inner <= 0 or departure < ONE_SHOT_MIN_COHERENCE * inner:
                continue
            candidates.append({"kind": "oneshot", "start": start, "length": end - start + 1, "end": end,
                               "seam": seam, "inner_mean_adjacent": inner, "ratio": seam / inner,
                               "return_distance_over_departure": round(seam / departure, 4),
                               "excursion": [a, b], "excursion_peak": peak_at,
                               "excursion_contrast": round(contrast, 2),
                               "excursion_moved": round(moved, 3) if moved is not None else None,
                               "excursion_rule": rule, "departure": departure,
                               "excursion_over_step": round(departure / inner, 3)})
    if not candidates:
        raise Refused(f"no complete one-shot return — the clip never leaves its rest pose and returns with observed "
                      f"endpoints (moved {max_moved:.2f}, need {ONE_SHOT_MIN_MOVED})", {"kind": "oneshot"})
    strongest = max(c["departure"] for c in candidates)
    eligible = [c for c in candidates if c["departure"] >= strongest * 0.95]
    best = min(eligible, key=lambda c: (c["length"], c["ratio"], c["start"]))
    return {**best, "candidates": len(candidates), "window": [shortest, max_len]}


def detect_once(D, fps):
    """An action that ends in a held pose: from just before the first active step to the first frame after the
    largest step where the steps stay at rest level for ONCE_SETTLE_SECONDS."""
    n = len(D)
    s = np.diag(D, 1).astype(np.float64)
    rest, top = float(np.percentile(s, 10)), float(np.percentile(s, 90))
    line = rest + ONCE_ACTIVE_SHARE * (top - rest)
    settle = rest + ONCE_SETTLE_SHARE * (top - rest)
    active = s > line
    moving = s > settle
    departure = float(D[0].max())
    rec = {"kind": "once", "rest_step": round(rest, 6), "top_step": round(top, 6), "active_line": round(line, 6),
           "settle_line": round(settle, 6), "departure": round(departure, 6)}
    if active.sum() < ONE_SHOT_MIN_ACTIVE or departure < ONE_SHOT_MIN_COHERENCE * float(s.mean()):
        raise Refused(f"no action to cut once — {int(active.sum())} active steps (need {ONE_SHOT_MIN_ACTIVE}) and a "
                      f"departure of {departure / max(float(s.mean()), 1e-9):.1f} steps (need "
                      f"{ONE_SHOT_MIN_COHERENCE:g})", rec)
    onset = int(np.argmax(active))
    peak = int(np.argmax(s))
    hold = max(2, round(ONCE_SETTLE_SECONDS * fps))
    end = None
    for k in range(peak + 1, n - hold):
        if not moving[k:k + hold].any():
            end = k
            break
    rec.update(onset_step=onset, peak_step=peak, hold_steps=hold)
    if end is None:
        raise Refused(f"the action never settles — no {hold}-step window under the settle line after its largest step "
                      f"(frame {peak + 1}); regenerate with the end pose held still for the last second", rec)
    start = max(0, onset - ONE_SHOT_PAD)
    adjacent = s[start:end]
    rec.update(start=start, end=end, length=end - start + 1, event_frame=peak + 1,
               inner_mean_adjacent=float(adjacent.mean()) if adjacent.size else 0.0)
    return rec


# --------------------------------------------------------------------- drift ----

def box(alpha):
    ys, xs = np.nonzero(alpha >= ALPHA_SOLID)
    if xs.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def body_centre(rgba):
    xs = np.nonzero(rgba[..., 3] >= ALPHA_SOLID)[1]
    return float(xs.mean()) if xs.size else rgba.shape[1] / 2


def foot_centre(rgba):
    b = box(rgba[..., 3])
    if b is None:
        return rgba.shape[1] / 2
    band = max(1, round((b[3] - b[1]) * FOOT_BAND))
    ys, xs = np.nonzero(rgba[b[3] - band:b[3], b[0]:b[2], 3] >= ALPHA_SOLID)
    return float(b[0] + xs.mean()) if xs.size else (b[0] + b[2]) / 2


def body_wrap_offset(first, last, band=BODY_ANCHOR_BAND, search=BODY_ANCHOR_SEARCH):
    """The horizontal offset that best lays the last frame's head and torso over the first's."""
    f, l = first.astype(np.float32), last.astype(np.float32)
    b = box(first[..., 3])
    if b is None:
        return 0
    mask = np.zeros(first.shape[:2], bool)
    mask[b[1]:b[1] + max(1, int((b[3] - 1 - b[1]) * band)), b[0]:b[2]] = True
    ref = f[mask]
    return min(range(-search, search + 1), key=lambda dx: float(np.abs(ref - np.roll(l, dx, axis=1)[mask]).mean()))


def _moved(m, dy, dx):
    h, w = m.shape
    out = np.zeros_like(m)
    out[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] = m[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
    return out


def core_rows(alpha):
    """(top, bottom) rows of the core silhouette: alpha > CORE_SOLID opened by CORE_OPEN_PX (a 3x3
    erosion, then a cross dilation), or the unopened mask when opening leaves under a fifth of it —
    the feet line codex-visual's audit_frames gates. None when the frame is empty."""
    m = alpha > CORE_SOLID
    c = m
    for _ in range(CORE_OPEN_PX):
        acc = np.ones_like(c)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                acc &= _moved(c, dy, dx)
        c = acc
    for _ in range(CORE_OPEN_PX):
        acc = c.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            acc |= _moved(c, dy, dx)
        c = acc
    if c.sum() <= 0.2 * m.sum():
        c = m
    ys = np.nonzero(c.any(axis=1))[0]
    return (int(ys.min()), int(ys.max())) if ys.size else None


def shift_y(rgba, dy):
    if dy == 0:
        return rgba
    out = np.zeros_like(rgba)
    if dy > 0:
        out[dy:] = rgba[:-dy]
    else:
        out[:dy] = rgba[-dy:]
    return out


def shift(rgba, dx):
    if dx == 0:
        return rgba
    out = np.zeros_like(rgba)
    if dx > 0:
        out[:, dx:] = rgba[:, :-dx]
    else:
        out[:, :dx] = rgba[:, -dx:]
    return out


# ------------------------------------------------------------------- loading ----

def resolve_input(path, source_fps):
    """-> (keyed dir, PNG files, source dict). Reads video_frames.py's report when there is one."""
    p = Path(path)
    if (p / "keyed").is_dir():
        keyed, report = p / "keyed", p / "frames.report.json"
    else:
        keyed, report = p, p.parent / "frames.report.json"
    files = sorted(f for f in keyed.glob("*.png"))
    if not files:
        raise ValueError(f"no PNG frames in {keyed}")
    source = {"file": None, "sha256": None, "fps": None}
    if report.is_file():
        try:
            rep = json.loads(report.read_text(encoding="utf-8"))
            src = rep.get("source") or {}
            source = {"file": src.get("file"), "sha256": src.get("sha256"), "fps": src.get("fps")}
        except (OSError, ValueError):
            pass
    if source_fps:
        source["fps"] = float(source_fps)
    if not source["fps"]:
        raise ValueError(f"no source fps: {report} is missing or has none — pass --source-fps")
    return keyed, files, source


def load_features(files):
    feats, boxes, masses = [], [], []
    size = None
    for f in files:
        im = Image.open(f).convert("RGBA")
        if size is None:
            size = im.size
        elif im.size != size:
            raise ValueError(f"{f.name} is {im.size[0]}x{im.size[1]}, the first frame {size[0]}x{size[1]}")
        v = small_features(im)
        feats.append(v)
        masses.append(float(np.abs(v).mean()))
        boxes.append(box(np.asarray(im.getchannel("A"))))
    if any(b is None for b in boxes):
        empty = [files[i].name for i, b in enumerate(boxes) if b is None]
        raise ValueError(f"{len(empty)} frame(s) hold no subject (first {empty[0]})")
    return np.stack(feats), boxes, np.array(masses, np.float32), size


def load_cut(files, boxes, idx, size):
    """The cut's frames cropped to their union box + CROP_PAD -> (arrays, crop origin)."""
    x0 = max(0, min(boxes[i][0] for i in idx) - CROP_PAD)
    y0 = max(0, min(boxes[i][1] for i in idx) - CROP_PAD)
    x1 = min(size[0], max(boxes[i][2] for i in idx) + CROP_PAD)
    y1 = min(size[1], max(boxes[i][3] for i in idx) + CROP_PAD)
    return [np.asarray(Image.open(files[i]).convert("RGBA"))[y0:y1, x0:x1].copy() for i in idx], (x0, y0)


# -------------------------------------------------------------------- output ----

def sample_indices(L, src_fps, out_fps, loop):
    if not out_fps or out_fps >= src_fps:
        return list(range(L))
    if loop:
        cap = min(L, max(4, round(L * out_fps / src_fps)))
        return sorted({min(L - 1, round(k * L / cap)) for k in range(cap)})
    cap = min(L, max(2, round(L * out_fps / src_fps)))
    return sorted({round(k * (L - 1) / (cap - 1)) for k in range(cap)})


def compose(frames, margin):
    """One canvas: the union box of every frame + margin on every side -> (frames, (W, H), union box)."""
    bs = [box(f[..., 3]) for f in frames]
    bs = [b for b in bs if b is not None]
    x0, y0 = min(b[0] for b in bs), min(b[1] for b in bs)
    x1, y1 = max(b[2] for b in bs), max(b[3] for b in bs)
    # alpha 1..7 tails count too, so nothing visible is cut
    for f in frames:
        ys, xs = np.nonzero(f[..., 3] > 0)
        if xs.size:
            x0, y0, x1, y1 = min(x0, int(xs.min())), min(y0, int(ys.min())), max(x1, int(xs.max()) + 1), max(y1, int(ys.max()) + 1)
    W, H = x1 - x0 + 2 * margin, y1 - y0 + 2 * margin
    out = []
    for f in frames:
        c = np.zeros((H, W, 4), np.uint8)
        c[margin:margin + y1 - y0, margin:margin + x1 - x0] = f[y0:y1, x0:x1]
        out.append(c)
    return out, (W, H), (x0, y0, x1, y1)


def write_gif(frames, path, fps):
    bg = np.empty_like(frames[0][..., :3], dtype=np.float32)
    bg[:] = (128, 128, 128)
    ims = []
    for f in frames:
        a = f[..., 3:4].astype(np.float32) / 255
        rgb = (f[..., :3] * a + bg * (1 - a)).astype(np.uint8)
        ims.append(Image.fromarray(rgb, "RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT))
    duration = max(20, int(round(100 / fps)) * 10)
    ims[0].save(path, save_all=True, append_images=ims[1:], duration=duration, loop=0, disposal=1)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------- run ----

def run(frames_dir, out_dir, name, *, state=None, mode="auto", fps=12.0, source_fps=None, min_len=None,
        max_len=None, seam_max=SEAM_RATIO_MAX, margin=8, drift=True, gif=True):
    """-> (exit code, report)."""
    out_dir = Path(out_dir)
    frame_dir, gif_path, report_path = out_dir / name, out_dir / f"{name}.gif", out_dir / f"{name}.report.json"
    report = {"tool": "video_loop.py", "producer": PRODUCER, "name": name, "state": state, "mode": mode}

    def finish(code, extra):
        report.update(extra)
        report["status"] = {0: "passed", 2: "refused", 3: "uncertain"}.get(code, "failed")
        if code in (1, 2):
            shutil.rmtree(frame_dir, ignore_errors=True)
            if gif_path.exists():
                gif_path.unlink()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            report["report"] = str(report_path)
        except OSError as exc:
            report["report_error"] = str(exc)
        return code, report

    if mode not in MODES:
        return 1, {**report, "ok": False, "error": f"unknown --mode {mode!r}"}
    try:
        keyed, files, source = resolve_input(frames_dir, source_fps)
        flat, boxes, masses, size = load_features(files)
    except (OSError, ValueError) as exc:
        return 1, {**report, "ok": False, "error": str(exc)}
    src_fps = float(source["fps"])
    report.update(frames_dir=str(keyed), source=source, source_frames=len(files))
    n = len(files)
    D = distances(flat)
    prof = profile_for(state)
    lo, hi = prof.window(n, src_fps)
    lo = min_len if min_len is not None else lo
    hi = max_len if max_len is not None else max(lo + 2, hi)
    gait_floor = round(prof.min_seconds * src_fps) if prof.gait and prof.min_seconds > 0 else None
    one_shot_hi = max(hi, round(n * ONE_SHOT_CEILING)) if max_len is None else max_len
    one_shot_lo = ONE_SHOT_MIN_LEN if min_len is None else min_len
    faults, periodic_attempt = [], None
    try:
        if mode == "once":
            cut = detect_once(D, src_fps)
        elif mode == "oneshot":
            cut = detect_one_shot(D, one_shot_lo, one_shot_hi, masses)
        else:
            cut = detect_cycle(D, lo, hi, gait_floor)
            floor = periodicity_floor(n, cut["period_global"], prof.action_seconds is not None)
            cut["periodicity_min"] = round(floor, 4)
            cut["periodicity_gate"] = "on" if prof.periodic else "exempt"
            if prof.periodic and cut["periodicity"] < floor:
                flat_why = (f"the period profile is flat (periodicity {cut['periodicity']:.2f} < {floor:.3f}) in "
                            f"window [{lo}, {hi}]")
                if mode == "auto" and prof.one_shot_ok:
                    periodic_attempt = {k: v for k, v in cut.items() if k != "fundamental"}
                    periodic_attempt["why_rejected"] = flat_why
                    cut = detect_one_shot(D, one_shot_lo, one_shot_hi, masses)
                else:
                    raise Refused(f"no periodic cycle — {flat_why}; the motion does not repeat: regenerate the clip, "
                                  "or pass --mode oneshot for a single performed action", cut)
    except Refused as exc:
        return finish(2, {"ok": False, "error": str(exc), "cut": exc.diagnostics, "periodic_attempt": periodic_attempt})

    loop = cut["kind"] == "loop"
    start, L = cut["start"], cut["length"]
    if loop:
        guard = cut["half_period_guard"]
        if guard.get("reason") == "ambiguous-harmonic":
            faults.append({"kind": "ambiguous-harmonic",
                           "message": f"the profile repeats about as well at {guard['from']} and {guard['to']} frames; "
                                      f"the cut holds {guard['to']} (two phase occurrences). If the preview shows two "
                                      f"full strides, re-run with --max-len {guard['from'] + 1}"})
        for s in cut["fundamental"]["suspects"]:
            faults.append({"kind": "multi-cycle-suspect",
                           "message": f"the {cut['period_global']}-frame loop may hold {s['cycles']} cycles: "
                                      f"{s['period']} frames repeats {s['periodicity']:.2f} below the profile mean. "
                                      f"Count the cycles in the preview; if it holds {s['cycles']}, re-run with "
                                      f"--max-len {s['period'] + 1}"})
    idx_cut = list(range(start, start + L))
    frames, origin = load_cut(files, boxes, idx_cut, size)
    drift_rec = {"applied": bool(drift)}
    if drift and loop:
        dx = body_wrap_offset(frames[0], frames[-1])
        frames = [shift(f, int(round(dx * k / L))) for k, f in enumerate(frames)]
        drift_rec.update(anchor="body-ramp", wrap_dx_px=int(dx), band=BODY_ANCHOR_BAND, search_px=BODY_ANCHOR_SEARCH)
    elif drift:
        centres = np.array([body_centre(f) for f in frames])
        t = np.arange(L, dtype=float)
        slope = float(np.polyfit(t, centres, 1)[0]) if L > 1 else 0.0
        frames = [shift(f, -int(round(slope * k))) for k, f in enumerate(frames)]
        drift_rec.update(anchor="trend", slope_px_per_frame=round(slope, 4),
                         drift_removed_px=round(abs(slope * (L - 1)), 2))
    else:
        drift_rec["anchor"] = "none"
    idx = sample_indices(L, src_fps, fps, loop)
    picked = [frames[k] for k in idx]
    cycle_seconds = L / src_fps
    fps_hint = round(len(idx) / cycle_seconds, 4)
    gaps = [b - a for a, b in zip(idx, idx[1:])] + ([L - idx[-1] + idx[0]] if loop and len(idx) > 1 else [])
    steps_taken = sorted(set(gaps)) or [1]     # source frames between shipped frames (a loop: the wrap too)

    seam = None
    if loop:
        read = [start + k for k in idx]
        adj = float(np.mean([D[read[k], read[k + 1]] for k in range(len(read) - 1)])) if len(read) > 1 else 0.0
        wrap = float(D[read[-1], read[0]])
        ratio = wrap / adj if adj > 0 else math.inf
        seam = {"read_on": "source-frames", "ratio": round(ratio, 4), "max": seam_max,
                "cut_ratio": round(cut["ratio"], 4) if math.isfinite(cut["ratio"]) else None}
        if ratio > seam_max and drift_rec.get("wrap_dx_px"):
            cells = np.stack([small_features(Image.fromarray(f, "RGBA")) for f in picked])
            steps = np.abs(cells[1:] - cells[:-1]).mean(axis=1)
            c_adj, c_wrap = float(steps.mean()), float(np.abs(cells[-1] - cells[0]).mean())
            seam.update(source_ratio=seam["ratio"], cells_ratio=round(c_wrap / c_adj, 4) if c_adj > 0 else None,
                        cells_largest_step_ratio=round(float(steps.max()) / c_adj, 4) if c_adj > 0 else None)
            if c_adj > 0 and c_wrap / c_adj <= seam_max and float(steps.max()) / c_adj <= seam_max:
                seam.update(read_on="moved-cells", ratio=seam["cells_ratio"])
                ratio = c_wrap / c_adj
        if ratio > seam_max:
            return finish(2, {"ok": False, "cut": _public(cut), "seam": seam,
                              "error": f"the loop's wrap is {ratio:.2f} mean steps (over --seam-max {seam_max:g}): the "
                                       "loop pops at the seam — regenerate the clip, or widen the window with "
                                       "--min-len/--max-len"})
        # the same wrap at the source rate: subsampling can step over a pop between the cut's last frame and its first
        src_ratio = cut["ratio"]
        if src_ratio > seam_max and drift_rec.get("wrap_dx_px"):
            cells = np.stack([small_features(Image.fromarray(f, "RGBA")) for f in frames])
            c_adj = float(np.abs(cells[1:] - cells[:-1]).mean(axis=1).mean())
            src_ratio = float(np.abs(cells[-1] - cells[0]).mean()) / c_adj if c_adj > 0 else math.inf
            seam["source_rate_read_on"] = "moved-frames"
        seam["source_rate_ratio"] = round(src_ratio, 4) if math.isfinite(src_ratio) else None
        if src_ratio > seam_max:
            return finish(2, {"ok": False, "cut": _public(cut), "seam": seam,
                              "error": f"the loop's wrap is {src_ratio:.2f} mean steps at the source rate (over "
                                       f"--seam-max {seam_max:g}; {ratio:.2f} on the subsampled frames): the loop pops "
                                       "at the seam — widen the window with --min-len/--max-len, or regenerate the clip"})

    # the feet line, read on the core silhouette as audit_frames reads it: within max(3 px, 2 % of the body)
    # every frame is seated on frame 0's line and the set is `ground`; past it (a jump, a run's flight) `keep`
    rows = [core_rows(f[..., 3]) for f in picked]
    feet = [r[1] for r in rows if r is not None]
    body_h = max((r[1] - r[0] + 1 for r in rows if r is not None), default=0)
    src_spread = max(feet) - min(feet) if feet else 0
    seated = bool(feet) and src_spread <= max(FEET_MAX_PX, round(0.02 * body_h))
    mode_reg = "ground" if seated else "keep"
    pad = 0
    if seated and src_spread:
        ref = rows[0][1] if rows[0] is not None else feet[0]
        dys = [ref - r[1] if r is not None else 0 for r in rows]
        pad = max(abs(d) for d in dys)
        picked = [shift_y(np.pad(f, ((pad, pad), (0, 0), (0, 0))), d) for f, d in zip(picked, dys)]
    out_frames, (W, H), union = compose(picked, margin)
    bottoms = [box(f[..., 3])[3] for f in out_frames]
    out_feet = [r[1] for r in (core_rows(f[..., 3]) for f in out_frames) if r is not None]
    floor_spread = max(out_feet) - min(out_feet) if out_feet else 0
    fx = foot_centre(out_frames[0])
    pivot_norm = [round(fx / W, 6), round((H - bottoms[0]) / H, 6)]
    name_fmt = [f"{name}_{i:03d}.png" for i in range(len(out_frames))]
    verdict = {"ok": not faults, "faults": faults}
    cut_pub = _public(cut)
    cut_pub["end_frame"] = start + L - 1
    doc = {
        "tool": "video_loop.py",
        "producer": PRODUCER,
        "source": source,
        "frames_dir": str(keyed),
        "canvas": [W, H],
        "pivot": "foot-center",
        "pivot_norm": pivot_norm,
        "fps_hint": fps_hint,
        "loop": loop,
        "hold_last": cut["kind"] == "once",
        "register": {"mode": mode_reg, "ref": 0, "anchor": drift_rec["anchor"], "margin_px": margin,
                     "floor_spread_px": int(floor_spread), "source_floor_spread_px": int(src_spread),
                     "seated_max_px": int(pad), "crop_origin": [origin[0] + union[0] - margin,
                                                                origin[1] - pad + union[1] - margin]},
        "verdict": verdict,
        "cycle_frames": L,
        "cycle_seconds": round(cycle_seconds, 4),
        "state": state,
        "cut": cut_pub,
        "seam": seam,
        "drift": drift_rec,
        "subsample": {"fps": fps, "source_fps": src_fps, "indices": [start + k for k in idx],
                      "steps": steps_taken, "even": len(steps_taken) == 1},
        "periodic_attempt": periodic_attempt,
        "preview": str(gif_path) if gif else None,
        "frames": [{"index": i, "file": f, "source_frame": start + idx[i]} for i, f in enumerate(name_fmt)],
    }
    try:
        shutil.rmtree(frame_dir, ignore_errors=True)
        frame_dir.mkdir(parents=True, exist_ok=True)
        for f, fn in zip(out_frames, name_fmt):
            Image.fromarray(f, "RGBA").save(frame_dir / fn)
        (frame_dir / "frames.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
        if gif:
            write_gif(out_frames, gif_path, fps_hint)
    except OSError as exc:
        return finish(1, {"ok": False, "error": f"cannot write to {out_dir}: {exc}"})
    code = 3 if faults else 0
    return finish(code, {"ok": code == 0, "frames_json": str(frame_dir / "frames.json"), "written": len(out_frames),
                         "canvas": [W, H], "fps_hint": fps_hint, "loop": loop, "hold_last": doc["hold_last"],
                         "register": doc["register"], "verdict": verdict, "cut": cut_pub, "seam": seam,
                         "drift": drift_rec, "subsample": doc["subsample"], "periodic_attempt": periodic_attempt,
                         "preview": doc["preview"]})


def _public(cut):
    out = {k: v for k, v in cut.items()}
    for k in ("seam", "inner_mean_adjacent", "ratio", "departure"):
        if isinstance(out.get(k), float):
            out[k] = round(out[k], 6) if math.isfinite(out[k]) else None
    return out


def summary_of(rep):
    keep = ("ok", "status", "error", "frames_json", "preview", "report", "written", "canvas", "fps_hint", "loop",
            "hold_last", "verdict", "seam", "drift")
    out = {k: rep[k] for k in keep if k in rep}
    cut = rep.get("cut") or {}
    out["cut"] = {k: cut[k] for k in ("kind", "start", "length", "end_frame", "period_global", "periodicity",
                                      "excursion", "excursion_peak", "event_frame", "window") if k in cut}
    if "half_period_guard" in cut:
        out["cut"]["half_period_guard"] = cut["half_period_guard"]
    if cut.get("fundamental"):
        out["cut"]["screen_suspects"] = len(cut["fundamental"]["suspects"])
    if rep.get("periodic_attempt"):
        out["periodic_attempt"] = {k: rep["periodic_attempt"].get(k) for k in ("period_global", "periodicity",
                                                                               "why_rejected")}
    return out


# ----------------------------------------------------------------- selftest ----

def _figure(phase, h=160, w=120, colour=(200, 60, 40), dx=0, dy=0, legs_alike=False):
    """A side-view figure: head, torso and two legs swinging with `phase` (radians); the far leg darker."""
    a = np.zeros((h, w, 4), np.uint8)
    cx, hip = 60 + dx, h - 60 + dy
    a[hip - 50:hip, cx - 10:cx + 10] = (*colour, 255)
    a[hip - 66:hip - 50, cx - 7:cx + 7] = (235, 195, 160, 255)
    for k, sign in ((0, 1), (1, -1)):
        swing = int(round(14 * math.sin(phase + k * math.pi)))
        leg = (40, 40, 160, 255) if (k == 0 or legs_alike) else (20, 20, 90, 255)
        for t in range(0, 44):
            x = cx + int(round(swing * t / 44))
            a[hip + t, x - 6:x + 6] = leg
    return a


def _write(frames, d, fps=24.0):
    keyed = Path(d) / "keyed"
    keyed.mkdir(parents=True)
    for i, f in enumerate(frames):
        Image.fromarray(f, "RGBA").save(keyed / f"frame-{i + 1:04d}.png")
    (Path(d) / "frames.report.json").write_text(json.dumps({"source": {"file": "synthetic.mp4", "sha256": "0" * 64,
                                                                       "fps": fps}}))
    return Path(d)


def selftest():
    checks = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # 1. a walk with a 20-frame stride, drifting 6 px over the clip
        walk = [_figure(2 * math.pi * i / 20, dx=int(round(6 * i / 100))) for i in range(100)]
        code, rep = run(_write(walk, tmp / "walk"), tmp / "out", "runner_walk", state="walk")
        cut = rep.get("cut") or {}
        checks.append(("walk: period 20, exit 0", code == 0 and cut.get("period_global") == 20 and cut["length"] in (19, 20, 21)))
        doc = json.loads((tmp / "out" / "runner_walk" / "frames.json").read_text()) if code == 0 else {}
        checks.append(("walk: frames.json contract", doc.get("register", {}).get("mode") == "ground"
                       and doc.get("loop") is True and doc.get("hold_last") is False
                       and doc.get("producer") == PRODUCER and list(doc)[-1] == "frames"
                       and len(doc.get("pivot_norm", [])) == 2 and doc.get("verdict", {}).get("ok") is True))
        checks.append(("walk: subsampled to 12 fps", code == 0 and doc["fps_hint"] == round(len(doc["frames"]) / (cut["length"] / 24), 4)
                       and len(doc["frames"]) == round(cut["length"] / 2)))
        files = sorted((tmp / "out" / "runner_walk").glob("runner_walk_*.png"))
        sizes = {Image.open(f).size for f in files}
        checks.append(("walk: one canvas, nothing on its border", len(sizes) == 1 and all(
            not (np.asarray(Image.open(f))[[0, -1], :, 3].any() or np.asarray(Image.open(f))[:, [0, -1], 3].any())
            for f in files)))
        checks.append(("walk: preview beside the frames", (tmp / "out" / "runner_walk.gif").is_file()
                       and not list((tmp / "out" / "runner_walk").glob("*.gif"))))
        checks.append(("walk: wrap drift read", rep.get("drift", {}).get("anchor") == "body-ramp"))

        # 1b. the same walk bobbing 2 px: seated on frame 0's feet line, `ground` with no spread left;
        #     hopping 19 px every step: past max(3 px, 2 % of the body), `keep`, nothing seated
        bob = [_figure(2 * math.pi * i / 20, dy=int(round(1.5 * math.sin(4 * math.pi * i / 20)))) for i in range(100)]
        code, rep = run(_write(bob, tmp / "bob"), tmp / "out", "bob", state="walk")
        reg = rep.get("register") or {}
        checks.append(("bobbing walk: seated, ground", code == 0 and reg.get("mode") == "ground"
                       and reg.get("source_floor_spread_px", 0) >= 2 and reg.get("floor_spread_px") == 0))
        hop = [_figure(2 * math.pi * i / 20, dy=-int(round(20 * abs(math.sin(2 * math.pi * i / 20)))))
               for i in range(100)]
        code, rep = run(_write(hop, tmp / "hop_loop"), tmp / "out", "hop_loop", state="run")
        reg = rep.get("register") or {}
        checks.append(("hopping loop: keep, not seated", code in (0, 3) and reg.get("mode") == "keep"
                       and reg.get("seated_max_px") == 0))

        # 2. legs alike, a 26-frame stride: the picture repeats every 13 frames, inside the walk window
        #    (12..) but under its 0.6 s floor (14) -> doubled to the stride
        alike = [_figure(2 * math.pi * i / 26, legs_alike=True) for i in range(110)]
        code, rep = run(_write(alike, tmp / "alike"), tmp / "out", "alike", state="walk")
        g = (rep.get("cut") or {}).get("half_period_guard", {})
        checks.append(("half step doubled to the stride", code == 0 and g.get("applied") and g.get("from") == 13
                       and g.get("to") == 26))

        # 2b. the same half step with a slow colour drift: nothing near 26 repeats as well -> half stride refused
        half = [_figure(2 * math.pi * i / 26, legs_alike=True, colour=(200, 60 + i, 40)) for i in range(110)]
        code, rep = run(_write(half, tmp / "half"), tmp / "out", "half", state="walk")
        checks.append(("half stride refused (2)", code == 2 and "half stride" in rep.get("error", "")))

        # 2c. legs alike, a 32-frame stride, colour noise: 16 frames is over the floor and 32 repeats as well
        #     -> the cut holds 32 (two phase occurrences), recorded as a fault, exit 3 with the frames written
        rng, amb = np.random.default_rng(5), []
        for i in range(124):
            f = _figure(2 * math.pi * i / 32, legs_alike=True)
            m = f[..., 3] > 0
            f[..., :3][m] = np.clip(f[..., :3][m].astype(int) + rng.integers(-6, 7, (int(m.sum()), 3)), 0, 255)
            amb.append(f)
        code, rep = run(_write(amb, tmp / "amb"), tmp / "out", "amb", state="walk")
        g = (rep.get("cut") or {}).get("half_period_guard", {})
        checks.append(("ambiguous harmonic -> 2P, fault, exit 3", code == 3 and g.get("reason") == "ambiguous-harmonic"
                       and g.get("to") == 32 and (tmp / "out" / "amb" / "frames.json").is_file()
                       and any(f["kind"] == "ambiguous-harmonic" for f in rep["verdict"]["faults"])))

        # 3. a still clip: no period -> refused 2, nothing handed over
        still = [_figure(0.0) for _ in range(60)]
        code, rep = run(_write(still, tmp / "still"), tmp / "out", "still", state="walk")
        checks.append(("still clip refused (2)", code == 2 and not (tmp / "out" / "still").exists()
                       and (tmp / "out" / "still.report.json").is_file()))

        # 4. a one-shot: rest, a 12-frame crouch, a 40-frame hop, rest; drifting 8 px; colour noise every frame
        rng, seq = np.random.default_rng(3), []
        for i in range(100):
            t = (i - 20) / 40
            up = int(round(90 * math.sin(math.pi * t))) if 0 <= t <= 1 else 0
            crouch = int(round(8 * math.sin(math.pi * (i - 8) / 12))) if 8 <= i < 20 else 0
            f = _figure(0.6 if 0 <= t <= 1 else 0.0, h=260, dx=int(round(8 * i / 100)), dy=crouch - up)
            m = f[..., 3] > 0
            f[..., :3][m] = np.clip(f[..., :3][m].astype(int) + rng.integers(-6, 7, (int(m.sum()), 3)), 0, 255)
            seq.append(f)
        code, rep = run(_write(seq, tmp / "hop"), tmp / "out", "runner_launch", state="jump")
        cut = rep.get("cut") or {}
        doc = json.loads((tmp / "out" / "runner_launch" / "frames.json").read_text()) if code == 0 else {}
        checks.append(("auto: one-shot after a flat profile", code == 0 and cut.get("kind") == "oneshot"
                       and rep.get("periodic_attempt") is not None
                       and cut["start"] <= 30 and cut["start"] + cut["length"] - 1 >= 50))
        checks.append(("one-shot: keep, no loop, trend removed", doc.get("register", {}).get("mode") == "keep"
                       and doc.get("loop") is False and doc.get("hold_last") is False
                       and doc.get("drift", {}).get("anchor") == "trend"))

        # 5. once: rest, a move into a new pose, held
        once = []
        for i in range(70):
            u = min(max((i - 20) / 12, 0.0), 1.0)
            once.append(_figure(0.0, dy=int(round(10 * u)), colour=(200, 60 + int(120 * u), 40)))
        code, rep = run(_write(once, tmp / "once"), tmp / "out", "runner_land", state="land", mode="once")
        cut = rep.get("cut") or {}
        checks.append(("once: ends at the settled pose, hold_last", code == 0 and cut.get("kind") == "once"
                       and 31 <= cut["start"] + cut["length"] - 1 <= 36 and rep.get("hold_last") is True))
        code, rep = run(_write(still, tmp / "once_still"), tmp / "out", "x", mode="once")
        checks.append(("once: no action refused (2)", code == 2))

        # 6. two alternating cycles that differ: the detector takes 2P, the screen suspects P -> exit 3
        alt = [_figure(2 * math.pi * i / 16, colour=(200, 60, 40) if (i // 16) % 2 == 0 else (170, 90, 60))
               for i in range(128)]
        code, rep = run(_write(alt, tmp / "alt"), tmp / "out", "alt", state="default", mode="loop")
        faults = (rep.get("verdict") or {}).get("faults") or []
        checks.append(("multi-cycle suspect -> exit 3, frames written", code == 3
                       and any(f["kind"] == "multi-cycle-suspect" for f in faults)
                       and (tmp / "out" / "alt" / "frames.json").is_file()
                       and json.loads((tmp / "out" / "alt" / "frames.json").read_text())["verdict"]["ok"] is False))

        code, _ = run(tmp / "nowhere", tmp / "out", "x")
        checks.append(("no frames -> 1", code == 1))
        empty = _write(walk[:10], tmp / "nofps")
        (empty / "frames.report.json").unlink()
        code, _ = run(empty, tmp / "out", "x")
        checks.append(("no source fps -> 1", code == 1))
    fails = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {name}")
    print(f"verdict {'FAIL' if fails else 'OK'}")
    return 1 if fails else 0


class ArgParser(argparse.ArgumentParser):
    """argparse with usage errors on exit 1, so exit 2 and 3 stay this script's refusals."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"FAIL {message}", file=sys.stderr)
        sys.exit(1)


def main(argv=None):
    ap = ArgParser(description="Cut keyed clip frames into one loop or one-shot: equal-canvas frames, "
                                             "frames.json and a preview GIF.")
    ap.add_argument("frames", help="video_frames.py's --out-dir (keyed/ + frames.report.json) or a folder of RGBA PNGs")
    ap.add_argument("--out-dir", required=True, help="writes NAME/ (frames + frames.json), NAME.gif, NAME.report.json")
    ap.add_argument("--name", required=True, help="frame and file name stem, e.g. runner_walk")
    ap.add_argument("--state", help="walk, run, idle, jump, attack or another action (selects the window)")
    ap.add_argument("--mode", choices=MODES, default="auto",
                    help="auto (default): a loop, failing over to a one-shot for jump/attack/other; loop; oneshot "
                         "(rest -> action -> rest); once (an action ending in a held pose)")
    ap.add_argument("--fps", type=float, default=12.0, help="subsample to this rate (default 12; 0 keeps every frame)")
    ap.add_argument("--source-fps", type=float, help="the clip's frame rate when there is no frames.report.json")
    ap.add_argument("--min-len", type=int, help="shortest cut in source frames (overrides the state window)")
    ap.add_argument("--max-len", type=int, help="longest cut in source frames (overrides the state window)")
    ap.add_argument("--seam-max", type=float, default=SEAM_RATIO_MAX, help="largest wrap / mean step (default 2.0)")
    ap.add_argument("--margin", type=int, default=8, help="transparent px round the union box (default 8)")
    ap.add_argument("--no-drift", action="store_true", help="leave every frame where it was filmed")
    ap.add_argument("--no-gif", action="store_true", help="skip the preview GIF")
    args = ap.parse_args(argv)
    if args.margin < 1 or (args.min_len is not None and args.min_len < 2) or args.fps < 0:
        print("FAIL --margin must be >= 1, --min-len >= 2, --fps >= 0", file=sys.stderr)
        return 1
    code, rep = run(args.frames, args.out_dir, args.name, state=args.state, mode=args.mode, fps=args.fps,
                    source_fps=args.source_fps, min_len=args.min_len, max_len=args.max_len, seam_max=args.seam_max,
                    margin=args.margin, drift=not args.no_drift, gif=not args.no_gif)
    print(json.dumps(summary_of(rep), indent=2))
    if code == 3:
        for f in rep["verdict"]["faults"]:
            print(f"UNCERTAIN {f['kind']}: {f['message']}", file=sys.stderr)
    elif code:
        print(f"FAIL {rep.get('error')}", file=sys.stderr)
    return code


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    sys.exit(main())
