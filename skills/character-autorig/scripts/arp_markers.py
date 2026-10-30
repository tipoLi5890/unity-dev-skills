#!/usr/bin/env python3
"""arp_markers.py — joint markers for Auto-Rig Pro (and the contract skeleton) measured from the mesh.

No Smart detection, no AI files, no open 3D view: the mesh is cut into horizontal slices (the
cross sections of mesh_check.py) and every marker is read from them, or placed by a stated body
proportion where the mesh shows no feature. Two front/side pictures with the markers drawn on the
body go to a person before any rig is built.

usage (in Blender, headless):
    blender -b scene.blend -P arp_markers.py -- --mesh Runner --out markers.json --preview-dir previews/
    blender -b -P arp_markers.py -- --import runner.glb --out markers.json --preview-dir previews/
usage (host Python, numpy only; no pictures):
    python3 arp_markers.py runner.glb [--up y|z] --out markers.json
options: [--spine-bones 3] [--fingers auto|fixed] [--adjust ADJUST.json] [--arm-angle 30,60]
         [--arm-ratios 0.42,0.75] [--no-window-gate] [--symmetry-max 0.02] [--mitten]
self-tests:
    python3 arp_markers.py --selftest                       (tube body, numpy only)
    blender -b --factory-startup -P arp_markers.py -- --selftest   (metaball runner, pictures)

The mesh must be prepared the way `blender-character-rig` -> import-and-survey.md says: +Z up,
facing -Y (its left on +X), soles on the ground, scale applied. Every height below is a fraction of
H (top minus sole); every position is in world metres.

How each marker is found (methods are reported per marker: measured, proportion, adjusted):
  crotch      the lowest slice above 0.2 H from which one part crosses the midline up to 0.6 H.
  hip         crotch + 0.02 H; X and Y from the leg part just below the crotch.
  ankle       the lowest slice between 0.03 and 0.13 H whose leg area is within 5 % of the least
              there (where the foot's flare ends); both legs' areas summed, one height for both.
  knee        a local narrowing of both legs' summed width 40-65 % of the way from ankle to hip, at
              least 3 % narrower than both sides; else 52 % of the way (proportion).
  ball, toe_tip, heel   the foot's vertices below the ankle: the front-most point is the toe tip,
              the rearmost the heel, the ball 70 % of the way from heel to toe.
  shoulder    the arm part's centroids below the armpit lie on the arm's axis; the shoulder is that
              axis where it is half the arm's radius outside the torso's edge at the armpit slice.
  hand_tip    the arm vertex farthest along the axis. elbow and wrist at --arm-ratios (0.42, 0.75)
              of shoulder -> hand_tip; the wrist moves to a narrowing of the arm within 0.66-0.84
              when there is one.
  neck        the narrowest central slice between the shoulders and 0.95 H; head_top the highest
              vertex; chin the lowest slice above the neck whose front reaches a quarter of the way
              from the neck's front to the face's; head_base between neck and chin.
  pelvis, spine points, neck_base   on the midline, at mid-depth of the torso slice (+10 % of the
              depth toward the back); the spine from pelvis to neck_base split evenly.
  fingers     `auto`: the hand is cut across its length; where it splits into four parts for two
              stations in a row, those are index..little, each tracked to its tip. Otherwise, and
              with `fixed`, a fixed hand shape scaled to wrist -> hand_tip and turned to the hand's
              own plane (its thinnest axis is the palm normal). The thumb is always the fixed shape.
Both sides are measured apart, compared (asymmetry), and averaged into one mirrored pair.
`--adjust` {marker: [x, y, z]} replaces measured markers after measuring (a person moved them).
An adjusted side marker (a .L or .R name) leaves the symmetry gate: a person placed it and its
mirror, so its measured difference is reported in asymmetry_accepted instead of gated.

Output (schema "autorig-markers/1"): landmarks {name: [x, y, z]} (.L/.R), methods, height,
ground_z, arm_angle_deg, asymmetry_m, asymmetry_accepted, fingers {mode, reason?}, hand_frames {.L: {x, y, z}},
arp_refs {ref bone: {head, tail}} for the .x and .l bones of Auto-Rig Pro's human preset (the
blender-retarget brt_arp `pipeline` op mirrors .l to .r), arp_spine_count (spine bones + 1, the
add-on counts its root), contract_bones (a blender-character-rig bcr_armature spec with contract
names, .L only, mirror true, radius per bone; with --mitten the finger bones are there but do
not deform), previews {front, side}, gates [{name, value, limit, ok}], ok.
Bend hints: Auto-Rig Pro reads the knee and elbow direction from the reference chain, so a leg
that is straight in the mesh gets its knee 1 % of the leg length forward (-Y) and an arm its elbow
2 % back (+Y) in arp_refs and contract_bones; landmarks stay as measured.

A marker that cannot be found refuses the call (exit 1) with the reason: no crotch, no leg parts,
no foot under the ankle, no arm hanging clear of the torso. mesh_check.py names the same faults.

Gates (each failing one makes exit 2):
  markers.windows     each height inside its window: ankle 0.02-0.13, knee 0.22-0.36, hip
                      0.42-0.60, shoulder 0.72-0.88, neck 0.78-0.93. Outside means proportions
                      this route was not made for (a chibi, a giant head): take the hand-built
                      route. --no-window-gate reports without gating.
  markers.symmetry    largest left/right difference of a marker <= --symmetry-max (0.02) x H,
                      over the markers not adjusted (see --adjust).
  markers.arm_angle   the upper arm (shoulder -> elbow) below horizontal, inside --arm-angle
                      (30-60 degrees: the contract's A-pose).
  markers.previews    (Blender, with --preview-dir) both pictures are on disk.

Prints one JSON object. Exit codes: 0 every gate passed (or a selftest passed); 2 a gate failed
(the JSON and pictures are still written, to adjust from); 1 refused input (no such mesh, an
unreadable file, a mesh with no legs to measure) or a failed selftest.
Requires numpy; Blender (bpy) only for --mesh, --import and the pictures.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import mesh_check as M  # noqa: E402

FINGERS = ("Thumb", "Index", "Middle", "Ring", "Little")
ARP_FINGER = {"Thumb": "thumb", "Index": "index", "Middle": "middle", "Ring": "ring", "Little": "pinky"}
# The fixed hand shape: per finger, knuckle then three joints ending at the tip, in the hand frame
# (x wrist -> middle tip, y across toward the little finger, z the back of the hand), in units of
# the hand length L = |hand_tip - wrist|. The thumb's first point is its base by the wrist.
HAND = {
    "Thumb": [(0.10, -0.11, -0.02), (0.30, -0.22, -0.08), (0.48, -0.24, -0.11), (0.62, -0.24, -0.12)],
    "Index": [(0.51, -0.13, 0.0), (0.675, -0.135, -0.01), (0.805, -0.14, -0.025), (0.93, -0.14, -0.04)],
    "Middle": [(0.51, 0.0, 0.0), (0.70, 0.0, -0.01), (0.86, 0.0, -0.025), (1.0, 0.0, -0.04)],
    "Ring": [(0.50, 0.085, 0.0), (0.68, 0.09, -0.01), (0.82, 0.095, -0.025), (0.94, 0.095, -0.04)],
    "Little": [(0.49, 0.19, 0.0), (0.62, 0.20, -0.01), (0.705, 0.21, -0.02), (0.78, 0.21, -0.035)],
}
HAND_REF = 0.37          # Auto-Rig Pro's hand reference bone, wrist toward the knuckles, x L
WINDOWS = {"ankle": (0.02, 0.13), "knee": (0.22, 0.36), "hip": (0.42, 0.60),
           "shoulder": (0.72, 0.88), "neck": (0.78, 0.93)}
SIDED = ("shoulder", "elbow", "wrist", "hand_tip", "hip", "knee", "ankle", "ball", "toe_tip", "heel")


class Refused(Exception):
    pass


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def mirror(p):
    return np.array([-p[0], p[1], p[2]])


# ------------------------------------------------------------------------------ measuring


def _central(cut, mid):
    return M.torso_of(cut["parts"], mid)


def _leg_part(cut, mid, s):
    cand = [p for p in cut["parts"] if not M.spans(p, mid) and s * (p["cx"] - mid) > 0]
    if not cand:
        return None
    return min(cand, key=lambda p: s * (p["x"][0] if s > 0 else p["x"][1]))


def _first_narrowing(values, lo, hi, contrast):
    """Index of a local minimum inside [lo, hi) at least `contrast` below both neighbours' maxima."""
    best = None
    for i in range(max(lo, 1), min(hi, len(values) - 1)):
        left, right = max(values[max(lo - 2, 0):i]), max(values[i + 1:min(hi + 2, len(values))])
        if values[i] <= min(values[max(i - 1, 0):i + 2]) and values[i] < (1 - contrast) * min(left, right):
            if best is None or values[i] < values[best]:
                best = i
    return best


def leg_rows(prof, s, crotch_h):
    mid = prof["midline_x"]
    rows = [(c, _leg_part(c, mid, s)) for c in prof["cuts"] if 0.02 <= c["h"] < crotch_h - 0.005]
    return [(c, p) for c, p in rows if p is not None]


def leg_heights(prof, crotch_h) -> tuple[float, float, str]:
    """(ankle h, knee h, knee method) from both legs together, so both sides share one height."""
    rows = {s: {c["h"]: p for c, p in leg_rows(prof, s, crotch_h)} for s in (1, -1)}
    hs = sorted(set(rows[1]) & set(rows[-1]))
    if len(hs) < 10:
        raise Refused("no leg parts below the crotch to measure (run mesh_check first)")
    area = [rows[1][h]["area"] + rows[-1][h]["area"] for h in hs]
    width = [np.ptp(rows[1][h]["x"]) + np.ptp(rows[-1][h]["x"]) for h in hs]
    band = [i for i, h in enumerate(hs) if 0.03 <= h <= 0.13]
    least = min(area[i] for i in band)
    ankle_h = hs[next(i for i in band if area[i] <= 1.05 * least)]   # the lowest within 5 %
    hip_h = crotch_h + 0.02
    lo_h, hi_h = ankle_h + 0.40 * (hip_h - ankle_h), ankle_h + 0.65 * (hip_h - ankle_h)
    harr = np.array(hs)
    k = _first_narrowing(width, int(np.searchsorted(harr, lo_h)), int(np.searchsorted(harr, hi_h)), 0.03)
    if k is None:
        return ankle_h, hs[int(np.argmin(np.abs(harr - (ankle_h + 0.52 * (hip_h - ankle_h)))))], "proportion"
    return ankle_h, hs[k], "measured"


def measure_side(V, prof, s, crotch_h, heights, arm_ratios, notes):
    """One side's markers (s = +1 left, -1 right) with their methods."""
    H, mid, z0 = prof["height"], prof["midline_x"], float(V[:, 2].min())
    cuts = prof["cuts"]
    out, how = {}, {}
    legs = leg_rows(prof, s, crotch_h)
    at = {c["h"]: (c, p) for c, p in legs}
    # hip: X and Y of the leg just below the crotch
    below = [lp for lp in legs if lp[0]["h"] <= crotch_h - 0.02] or legs
    c, p = below[-1]
    hip_h = crotch_h + 0.02
    out["hip"], how["hip"] = np.array([p["cx"], p["cy"], z0 + hip_h * H]), "measured"
    ankle_h, knee_h, knee_how = heights
    c, p = at[ankle_h]
    out["ankle"], how["ankle"] = np.array([p["cx"], p["cy"], c["z"]]), "measured"
    c, p = at[knee_h]
    out["knee"], how["knee"] = np.array([p["cx"], p["cy"], c["z"]]), knee_how
    # foot: vertices below the ankle, near this leg
    ax = out["ankle"]
    foot = V[(V[:, 2] < ax[2]) & (np.abs(V[:, 0] - ax[0]) < 0.08 * H)]
    if len(foot) < 8:
        raise Refused("no foot vertices under the ankle")
    front = foot[foot[:, 1] <= np.quantile(foot[:, 1], 0.03)]
    back = foot[foot[:, 1] >= np.quantile(foot[:, 1], 0.97)]
    toe_y, heel_y = float(foot[:, 1].min()), float(foot[:, 1].max())
    ball_y = heel_y + 0.70 * (toe_y - heel_y)
    near_ball = foot[np.abs(foot[:, 1] - ball_y) < 0.02 * H]
    ball_x = float(np.median(near_ball[:, 0])) if len(near_ball) else float(ax[0])
    sole = z0 + 0.35 * (ax[2] - z0)
    out["ball"] = np.array([ball_x, ball_y, sole])
    out["toe_tip"] = np.array([float(np.median(front[:, 0])), toe_y, sole])
    out["heel"] = np.array([float(np.median(back[:, 0])), heel_y, z0 + 0.25 * (ax[2] - z0)])
    out["foot_width"] = float(np.ptp(near_ball[:, 0])) if len(near_ball) else 0.06 * H
    for name in ("ball", "toe_tip", "heel"):
        how[name] = "measured"
    # arm: centroids of the part outside the torso, from the armpit down (the longest run wins:
    # a cap or a shoulder pad above the armpit makes a short run of its own)
    runs, track, armpit = [], [], None
    for c in reversed(cuts):
        if c["h"] < 0.3 or c["h"] > 0.95:
            continue
        torso = _central(c, mid)
        outside = []
        if torso is not None:
            edge = torso["x"][1] if s > 0 else torso["x"][0]
            outside = [p for p in c["parts"] if (p["x"][0] > edge if s > 0 else p["x"][1] < edge)]
        pick = None
        if outside and not track:
            pick = min(outside, key=lambda p: abs(p["cx"] - edge))
            armpit = (c, torso)
        elif outside:
            last = track[-1]
            pick = min(outside, key=lambda p: math.hypot(p["cx"] - last[0], c["z"] - last[2]))
            if math.hypot(pick["cx"] - last[0], c["z"] - last[2]) > 0.08 * H:
                pick = None
        if pick is None:
            if track:
                runs.append((track, armpit))
            track, armpit = [], None
            continue
        track.append((pick["cx"], pick["cy"], c["z"], pick["area"]))
    if track:
        runs.append((track, armpit))
    track, armpit = max(runs, key=lambda r: len(r[0])) if runs else ([], None)
    if armpit is None or len(track) < 4:
        raise Refused("no arm part hangs clear of the torso (fused arms or a T-pose: run mesh_check)")
    P = np.array([t[:3] for t in track])
    w = np.array([t[3] for t in track])
    centre = (P * w[:, None]).sum(0) / w.sum()
    _, _, vt = np.linalg.svd((P - centre) * np.sqrt(w)[:, None])
    d = _unit(vt[0])
    if d[2] > 0:
        d = -d
    if abs(d[0]) < 0.2:
        raise Refused("the arm axis is nearly vertical: arms held against the body")
    c_top, torso = armpit
    edge = torso["x"][1] if s > 0 else torso["x"][0]
    rel = V - centre
    along = rel @ d
    perp = np.linalg.norm(rel - np.outer(along, d), axis=1)
    arm = (s * (V[:, 0] - edge) > 0) & (perp < 0.12 * H)
    if arm.sum() < 8:
        raise Refused("no arm vertices along the arm axis")
    r_arm = float(np.median(perp[arm & (np.abs(along) < 0.1 * H)])) if (arm & (np.abs(along) < 0.1 * H)).any() \
        else 0.025 * H
    t = (edge + s * 0.5 * r_arm - centre[0]) / d[0]
    shoulder = centre + t * d
    out["shoulder"], how["shoulder"] = shoulder, "measured"
    rel = V - shoulder
    along = rel @ d
    perp = np.linalg.norm(rel - np.outer(along, d), axis=1)
    arm = arm & (along > 0)
    tip_t = float(along[arm].max())
    out["hand_tip"], how["hand_tip"] = shoulder + tip_t * d, "measured"   # on the axis, as far as the arm goes
    e_r, w_r = arm_ratios
    out["elbow"], how["elbow"] = shoulder + e_r * tip_t * d, "proportion"
    stations = np.linspace(0.66, 0.84, 10)
    radius = []
    for f in stations:
        sel = arm & (np.abs(along - f * tip_t) < 0.01 * H)
        radius.append(float(np.quantile(perp[sel], 0.9)) if sel.sum() >= 4 else np.inf)
    k = _first_narrowing(radius, 1, len(radius) - 1, 0.05) if np.isfinite(radius).all() else None
    if k is None:
        out["wrist"], how["wrist"] = shoulder + w_r * tip_t * d, "proportion"
    else:
        out["wrist"], how["wrist"] = shoulder + stations[k] * tip_t * d, "measured"
    out["_arm_axis"] = d
    out["_edge"] = edge
    notes.append(f"{'L' if s > 0 else 'R'} arm: {len(track)} slices below the armpit at {c_top['h']:.3f} H")
    return out, how


def hand_frame(V, wrist, tip, s):
    """(x, y, z): x wrist -> tip, z the back of the hand (its thinnest axis), y toward the little finger."""
    x = _unit(tip - wrist)
    L = float(np.linalg.norm(tip - wrist))
    rel = V - wrist
    along = rel @ x
    perp = rel - np.outer(along, x)
    sel = (along > 0.05 * L) & (along < 1.02 * L) & (np.linalg.norm(perp, axis=1) < 0.5 * L)
    if sel.sum() >= 12:
        q = perp[sel] - perp[sel].mean(0)
        _, _, vt = np.linalg.svd(q, full_matrices=True)
        z = _unit(vt[2] - (vt[2] @ x) * x)
    else:
        z = _unit(np.array([0, 0, 1.0]) - x[2] * x)
    if z @ np.array([0.5 * s, 0, 1.0]) < 0:
        z = -z
    y = _unit(np.cross(z, x))
    if y[1] < 0:
        y = -y
    return x, y, z, L


def fixed_hand(wrist, frame):
    x, y, z, L = frame
    return {f: [wrist + L * (a * x + b * y + c * z) for a, b, c in pts] for f, pts in HAND.items()}


def detect_fingers(points, wrist, frame):
    """Index..little from where the hand splits into four parts; None and a reason otherwise."""
    x, y, z, L = frame
    rel = points - wrist
    u, v, w = rel @ x / L, rel @ y / L, rel @ z / L
    stations = np.arange(0.40, 1.02, 0.02)
    groups = []
    for st in stations:
        sel = np.abs(u - st) < 0.015
        vs = np.sort(v[sel])
        if len(vs) < 8:
            groups.append([])
            continue
        cuts = np.nonzero(np.diff(vs) > 0.015)[0]
        runs = np.split(vs, cuts + 1)
        groups.append([float(r.mean()) for r in runs if len(r) >= 3])
    split = next((i for i in range(len(groups) - 1) if len(groups[i]) == 4 and len(groups[i + 1]) == 4), None)
    if split is None:
        return None, "no station splits the hand into four fingers (a mitten, or fingers held together)"
    lanes = groups[split]
    tips = [stations[split]] * 4
    for i in range(split + 1, len(groups)):
        for k, lane in enumerate(lanes):
            near = [g for g in groups[i] if abs(g - lane) < 0.06]
            if near:
                tips[k] = stations[i]
    found = {}
    knuckle_u = max(0.35, stations[split] - 0.06)
    for name, lane, tip_u in zip(("Index", "Middle", "Ring", "Little"), lanes, tips):
        tpl = np.array(HAND[name])
        frac = (tpl[:, 0] - tpl[0, 0]) / (tpl[-1, 0] - tpl[0, 0])
        tip_u = tip_u + 0.015
        found[name] = [wrist + L * ((knuckle_u + f * (tip_u - knuckle_u)) * x + lane * y + tpl[j, 2] * z)
                       for j, f in enumerate(frac)]
    return found, None


def measure(V, F, opts) -> dict:
    """Every marker of the body, both sides measured, compared and mirrored."""
    prof = M.profile(V, F, step=0.01, cell=0.008)
    H, mid, z0 = prof["height"], prof["midline_x"], float(V[:, 2].min())
    notes = []
    crotch_h = M.crotch(prof)
    if crotch_h is None:
        raise Refused("no crotch: the legs never part (run mesh_check)")
    sides = {}
    heights = leg_heights(prof, crotch_h)
    for s in (1, -1):
        sides[s] = measure_side(V, prof, s, crotch_h, heights, opts["arm_ratios"], notes)
    lm, how, asym = {}, {}, {}
    for name in SIDED:
        pl, pr = sides[1][0][name], sides[-1][0][name]
        asym[name] = float(np.linalg.norm(pl - mirror(pr)))
        avg = (pl + mirror(pr)) / 2
        lm[name + ".L"], lm[name + ".R"] = avg, mirror(avg)
        m = sides[1][1][name] if sides[1][1][name] == sides[-1][1][name] else "measured"
        how[name + ".L"] = how[name + ".R"] = m
    foot_width = (sides[1][0]["foot_width"] + sides[-1][0]["foot_width"]) / 2
    # centre line
    def central_at(z):
        c = min(prof["cuts"], key=lambda c: abs(c["z"] - z))
        return _central(c, mid)

    def mid_depth(z):
        part = central_at(z)
        if part is None:
            return 0.0
        return part["y"][0] + 0.55 * (part["y"][1] - part["y"][0])
    hip = lm["hip.L"]
    lm["pelvis"] = np.array([mid, mid_depth(hip[2]), hip[2]])
    shoulder_z = float(lm["shoulder.L"][2])
    top_z = float(V[:, 2].max())
    rows = [c for c in prof["cuts"] if shoulder_z - z0 <= (c["h"] * H) <= 0.95 * H and _central(c, mid)]
    if not rows:
        raise Refused("no central part above the shoulders")
    widths = [np.ptp(_central(c, mid)["x"]) for c in rows]
    neck_cut = rows[int(np.argmin(widths))]
    neck_part = _central(neck_cut, mid)
    lm["neck"] = np.array([mid, (neck_part["y"][0] + neck_part["y"][1]) / 2, neck_cut["z"]])
    how["neck"] = "measured"
    head_rows = [c for c in prof["cuts"] if neck_cut["z"] < c["z"] < top_z and _central(c, mid)]
    fronts = [_central(c, mid)["y"][0] for c in head_rows]
    chin_z = None
    if fronts:
        target = neck_part["y"][0] + 0.25 * (min(fronts) - neck_part["y"][0])
        chin = next((c for c, f in zip(head_rows, fronts) if f <= target), None)
        if chin is not None:
            chin_z = chin["z"]
            lm["chin"] = np.array([mid, _central(chin, mid)["y"][0], chin_z])
            how["chin"] = "measured"
    neck_z = float(lm["neck"][2])
    base_z = neck_z + (0.35 * (chin_z - neck_z) if chin_z and chin_z > neck_z else 0.02 * H)
    lm["head_base"] = np.array([mid, mid_depth(base_z), base_z])
    top_part = central_at(top_z - 0.06 * H)
    lm["head_top"] = np.array([mid, (top_part["y"][0] + top_part["y"][1]) / 2 if top_part else lm["neck"][1], top_z])
    nb_z = max(shoulder_z, neck_z - 0.03 * H)
    lm["neck_base"] = np.array([mid, mid_depth(nb_z), nb_z])
    for name in ("pelvis", "head_base", "head_top", "neck_base"):
        how[name] = "measured"
    n = opts["spine_bones"] + 1
    for i in range(1, n):
        zi = hip[2] + (nb_z - hip[2]) * i / n
        lm[f"spine{i}"] = np.array([mid, mid_depth(zi), zi])
        how[f"spine{i}"] = "proportion"
    # hands
    frames, fingers = {}, {"mode": "fixed"}
    for s, side in ((1, ".L"), (-1, ".R")):
        frames[side] = hand_frame(V, lm["wrist" + side], lm["hand_tip" + side], s)
    detected = None
    if opts["fingers"] == "auto":
        x, y, z, L = frames[".L"]
        tri = V[F]
        cen = tri.mean(axis=1)
        rel = cen - lm["wrist.L"]
        along = rel @ x
        near = (along > 0) & (along < 1.1 * L) & (np.linalg.norm(rel - np.outer(along, x), axis=1) < 0.6 * L)
        if near.sum() >= 20:
            pts, _ = M.surface_samples(V, F[near], 4000)
            detected, reason = detect_fingers(pts, lm["wrist.L"], frames[".L"])
        else:
            reason = "too few hand triangles"
        if detected:
            fingers = {"mode": "detected"}
        else:
            fingers = {"mode": "fixed", "reason": reason}
    hand = {}
    for s, side in ((1, ".L"), (-1, ".R")):
        shape = fixed_hand(lm["wrist" + side], frames[side])
        if detected:
            for f, pts in detected.items():
                shape[f] = pts if s > 0 else [mirror(p) for p in pts]
        hand[side] = shape
        for f, pts in shape.items():
            for j, p in enumerate(pts):
                lm[f"{f.lower()}{j}{side}"] = p
                how[f"{f.lower()}{j}{side}"] = "measured" if (detected and f != "Thumb") else "fixed"
    return {"height": H, "ground_z": z0, "midline_x": mid, "crotch_h": crotch_h, "landmarks": lm,
            "methods": how, "asymmetry": asym, "foot_width": foot_width, "frames": frames,
            "fingers": fingers, "notes": notes}


# ------------------------------------------------------------------------------ outputs


def _bend(a, b, c, direction, amount):
    """b moved toward `direction` so it sits at least `amount` off the line a -> c."""
    ac = _unit(c - a)
    off = (b - a) - ((b - a) @ ac) * ac
    have = float(off @ direction)
    return b + direction * max(0.0, amount - have)


def chain_points(m):
    lm, out = m["landmarks"], {}
    for side, s in ((".L", 1), (".R", -1)):
        leg = float(np.linalg.norm(lm["ankle" + side] - lm["hip" + side]))
        arm = float(np.linalg.norm(lm["wrist" + side] - lm["shoulder" + side]))
        out["knee" + side] = _bend(lm["hip" + side], lm["knee" + side], lm["ankle" + side],
                                   np.array([0, -1.0, 0]), 0.01 * leg)
        out["elbow" + side] = _bend(lm["shoulder" + side], lm["elbow" + side], lm["wrist" + side],
                                    np.array([0, 1.0, 0]), 0.02 * arm)
    return out


def arp_refs(m, spine_bones):
    lm, H, z0 = m["landmarks"], m["height"], m["ground_z"]
    bent = chain_points(m)
    refs = {}

    def put(name, a, b):
        refs[name] = {"head": a, "tail": b}
    spine = [lm["pelvis"]] + [lm[f"spine{i}"] for i in range(1, spine_bones + 1)] + [lm["neck_base"]]
    put("root_ref.x", spine[0], spine[1])
    for i in range(1, spine_bones + 1):
        put(f"spine_{i:02d}_ref.x", spine[i], spine[i + 1])
    put("neck_ref.x", lm["neck_base"], lm["head_base"])
    put("head_ref.x", lm["head_base"], lm["head_top"])
    sh, mid = lm["shoulder.L"], m["midline_x"]
    clav = np.array([mid + 0.22 * (sh[0] - mid), sh[1], sh[2]])
    put("shoulder_ref.l", clav, sh)
    put("arm_ref.l", sh, bent["elbow.L"])
    put("forearm_ref.l", bent["elbow.L"], lm["wrist.L"])
    x, y, z, L = m["frames"][".L"]
    put("hand_ref.l", lm["wrist.L"], lm["wrist.L"] + HAND_REF * L * x)
    for f in FINGERS:
        pts = [lm[f"{f.lower()}{j}.L"] for j in range(4)]
        a = ARP_FINGER[f]
        if f == "Thumb":
            for j in range(3):
                put(f"thumb{j + 1}_ref.l", pts[j], pts[j + 1])
        else:
            meta = lm["wrist.L"] + L * (0.12 * x + 0.5 * ((pts[0] - lm["wrist.L"]) @ y / L) * y)
            put(f"{a}1_base_ref.l", meta, pts[0])
            for j in range(3):
                put(f"{a}{j + 1}_ref.l", pts[j], pts[j + 1])
    put("thigh_ref.l", lm["hip.L"], bent["knee.L"])
    put("leg_ref.l", bent["knee.L"], lm["ankle.L"])
    put("foot_ref.l", lm["ankle.L"], lm["ball.L"])
    put("toes_ref.l", lm["ball.L"], lm["toe_tip.L"])
    step = 0.016 * H
    g = z0 + 0.001 * H
    heel = lm["heel.L"]
    put("foot_heel_ref.l", np.array([lm["ankle.L"][0], heel[1], g]), np.array([lm["ankle.L"][0], heel[1] - step, g]))
    half = 0.5 * m["foot_width"]
    ball = lm["ball.L"]
    put("foot_bank_01_ref.l", np.array([ball[0] + half, ball[1], g]), np.array([ball[0] + half, ball[1] - step, g]))
    put("foot_bank_02_ref.l", np.array([ball[0] - half, ball[1], g]), np.array([ball[0] - half, ball[1] - step, g]))
    return refs


def bone_radius(samples, a, b):
    """Median distance from points along a -> b to the nearest surface sample."""
    out = []
    for t in (0.25, 0.5, 0.75):
        p = a + t * (b - a)
        out.append(float(np.sqrt(((samples - p) ** 2).sum(1).min())))
    return float(np.median(out))


def contract_bones(m, spine_bones, samples, mitten=False):
    """A bcr_armature spec with contract names (.L only, mirror true). `mitten`: finger bones kept
    for the contract but not deforming, so a hand without finger geometry skins to Hand."""
    lm, mid = m["landmarks"], m["midline_x"]
    bent = chain_points(m)
    bones = []

    def put(name, a, b, parent, deform=True):
        spec = {"name": name, "head": [round(float(x), 5) for x in a], "tail": [round(float(x), 5) for x in b],
                "parent": parent, "deform": deform}
        if deform:
            spec["radius"] = round(max(bone_radius(samples, np.asarray(a), np.asarray(b)), 0.005), 4)
        bones.append(spec)
    ground = np.array([mid, 0.0, m["ground_z"]])
    put("Root", ground, ground + np.array([0, 0.1 * m["height"], 0]), None, deform=False)
    names = ["Hips", "Spine", "Chest", "UpperChest"] if spine_bones == 3 else \
        ["Hips"] + [f"Spine{i}" for i in range(1, spine_bones + 1)]
    spine = [lm["pelvis"]] + [lm[f"spine{i}"] for i in range(1, spine_bones + 1)] + [lm["neck_base"]]
    parent = "Root"
    for name, a, b in zip(names, spine[:-1], spine[1:]):
        put(name, a, b, parent)
        parent = name
    put("Neck", lm["neck_base"], lm["head_base"], parent)
    put("Head", lm["head_base"], lm["head_top"], "Neck")
    sh = lm["shoulder.L"]
    put("Shoulder.L", np.array([mid + 0.22 * (sh[0] - mid), sh[1], sh[2]]), sh, parent)
    put("UpperArm.L", sh, bent["elbow.L"], "Shoulder.L")
    put("LowerArm.L", bent["elbow.L"], lm["wrist.L"], "UpperArm.L")
    x, y, z, L = m["frames"][".L"]
    put("Hand.L", lm["wrist.L"], lm["wrist.L"] + HAND_REF * L * x, "LowerArm.L")
    for f in FINGERS:
        pts = [lm[f"{f.lower()}{j}.L"] for j in range(4)]
        prev = "Hand.L"
        for j in range(3):
            put(f"{f}{j + 1}.L", pts[j], pts[j + 1], prev, deform=not mitten)
            prev = f"{f}{j + 1}.L"
    put("UpperLeg.L", lm["hip.L"], bent["knee.L"], "Hips")
    put("LowerLeg.L", bent["knee.L"], lm["ankle.L"], "UpperLeg.L")
    put("Foot.L", lm["ankle.L"], lm["ball.L"], "LowerLeg.L")
    put("Toes.L", lm["ball.L"], lm["toe_tip.L"], "Foot.L")
    return bones


def gate(name, value, limit, ok):
    return {"name": name, "value": value, "limit": limit, "ok": bool(ok)}


def build_report(V, F, opts) -> dict:
    m = measure(V, F, opts)
    lm, H, z0 = m["landmarks"], m["height"], m["ground_z"]
    for name, xyz in (opts.get("adjust") or {}).items():
        if name not in lm:
            raise Refused(f"--adjust names {name!r}, which is not a marker")
        lm[name] = np.asarray(xyz, dtype=float)
        m["methods"][name] = "adjusted"
        if name.endswith((".L", ".R")):
            twin = name[:-2] + (".R" if name.endswith(".L") else ".L")
            if twin not in (opts.get("adjust") or {}):
                lm[twin] = mirror(lm[name])
                m["methods"][twin] = "adjusted"
    upper = lm["elbow.L"] - lm["shoulder.L"]
    arm_angle = math.degrees(math.atan2(-upper[2], math.hypot(upper[0], upper[1])))
    samples, _ = M.surface_samples(V, F, 20000)
    refs = arp_refs(m, opts["spine_bones"])
    spec = contract_bones(m, opts["spine_bones"], samples, mitten=opts.get("mitten", False))
    out_window = {}
    for name, (lo, hi) in WINDOWS.items():
        h = (float(lm[name + ".L"][2] if name + ".L" in lm else lm[name][2]) - z0) / H
        if not lo <= h <= hi:
            out_window[name] = round(h, 3)
    adjusted = {n[:-2] for n in (opts.get("adjust") or {}) if n.endswith((".L", ".R"))}
    accepted = {k: v for k, v in m["asymmetry"].items() if k in adjusted}
    asym = max((v for k, v in m["asymmetry"].items() if k not in adjusted), default=0.0)
    a_lo, a_hi = opts["arm_angle"]
    gates = [gate("markers.windows", out_window, {k: list(v) for k, v in WINDOWS.items()},
                  not out_window or opts["no_window_gate"]),
             gate("markers.symmetry", round(asym, 4), round(opts["symmetry_max"] * H, 4),
                  asym <= opts["symmetry_max"] * H),
             gate("markers.arm_angle", round(arm_angle, 2), [a_lo, a_hi], a_lo <= arm_angle <= a_hi)]

    def r(p):
        return [round(float(x), 5) for x in p]
    return {
        "schema": "autorig-markers/1", "tool": "arp_markers", "space": "world", "up": "+Z", "forward": "-Y",
        "height": round(H, 5), "ground_z": round(z0, 5), "midline_x": round(m["midline_x"], 5),
        "crotch_h": m["crotch_h"], "arm_angle_deg": round(arm_angle, 2),
        "landmarks": {k: r(v) for k, v in lm.items()}, "methods": m["methods"],
        "asymmetry_m": {k: round(v, 4) for k, v in m["asymmetry"].items()},
        "asymmetry_accepted": {k: round(v, 4) for k, v in accepted.items()},
        "fingers": m["fingers"],
        "hand_frames": {side: {"x": r(f[0]), "y": r(f[1]), "z": r(f[2]), "length": round(f[3], 5)}
                        for side, f in m["frames"].items()},
        "arp_spine_count": opts["spine_bones"] + 1,
        "arp_refs": {k: {"head": r(v["head"]), "tail": r(v["tail"])} for k, v in refs.items()},
        "contract_bones": {"mirror": True, "bones": spec},
        "notes": m["notes"], "gates": gates, "ok": all(g["ok"] for g in gates),
    }


# ------------------------------------------------------------------------------ CLI


def _pair(text):
    a, b = (float(x) for x in text.split(","))
    return (a, b)


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser():
    p = UsageParser(prog="arp_markers.py", description=__doc__.split("\n")[0],
                                epilog="Exit codes: 0 pass, 2 a gate failed, 1 refused input.")
    p.add_argument("file", nargs="?", type=Path, help="host mode: a .glb/.gltf/.obj")
    p.add_argument("--up", choices=("y", "z"), default="y")
    p.add_argument("--mesh", help="Blender: the mesh object in the open file")
    p.add_argument("--import", dest="import_path", help="Blender: import this .glb/.gltf/.fbx/.obj first")
    p.add_argument("--out")
    p.add_argument("--preview-dir")
    p.add_argument("--spine-bones", type=int, default=3)
    p.add_argument("--fingers", choices=("auto", "fixed"), default="auto")
    p.add_argument("--adjust", help="JSON {marker: [x, y, z]} applied after measuring")
    p.add_argument("--arm-angle", type=_pair, default=(30.0, 60.0))
    p.add_argument("--arm-ratios", type=_pair, default=(0.42, 0.75))
    p.add_argument("--symmetry-max", type=float, default=0.02)
    p.add_argument("--no-window-gate", action="store_true")
    p.add_argument("--mitten", action="store_true", help="contract_bones: finger bones do not deform")
    p.add_argument("--selftest", action="store_true")
    return p


def _opts(args) -> dict:
    adjust = None
    if args.adjust:
        adjust = json.loads(Path(args.adjust).read_text(encoding="utf-8"))
    return {"spine_bones": args.spine_bones, "fingers": args.fingers, "adjust": adjust,
            "arm_angle": args.arm_angle, "arm_ratios": args.arm_ratios,
            "symmetry_max": args.symmetry_max, "no_window_gate": args.no_window_gate,
            "mitten": args.mitten}


CHAINS = [("pelvis", "spine1"), ("spine1", "spine2"), ("spine2", "spine3"), ("spine3", "neck_base"),
          ("neck_base", "head_base"), ("head_base", "head_top")] + \
    [(a + s, b + s) for s in (".L", ".R") for a, b in
     (("shoulder", "elbow"), ("elbow", "wrist"), ("wrist", "hand_tip"), ("hip", "knee"), ("knee", "ankle"),
      ("ankle", "ball"), ("ball", "toe_tip"))]


def run_blender(args) -> tuple[int, dict]:
    import bpy
    import autorig_blender as A
    if args.import_path:
        path = args.import_path
        before = set(bpy.data.objects)
        ext = path.lower().rsplit(".", 1)[-1]
        if ext in ("glb", "gltf"):
            bpy.ops.import_scene.gltf(filepath=path)
        elif ext == "fbx":
            bpy.ops.import_scene.fbx(filepath=path)
        elif ext == "obj":
            bpy.ops.wm.obj_import(filepath=path)
        else:
            return 1, {"tool": "arp_markers", "error": f"cannot import {path}"}
        new = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
        if not new:
            return 1, {"tool": "arp_markers", "error": f"{path} holds no mesh"}
        obj = max(new, key=lambda o: len(o.data.vertices))
    else:
        obj = bpy.data.objects.get(args.mesh or "")
        if obj is None or obj.type != 'MESH':
            return 1, {"tool": "arp_markers", "error": f"no mesh object {args.mesh!r} in this file"}
    V, F = A.mesh_arrays(obj)
    try:
        report = build_report(V, F, _opts(args))
    except Refused as exc:
        return 1, {"tool": "arp_markers", "mesh": obj.name, "error": str(exc)}
    report["mesh"] = obj.name
    if args.preview_dir:
        os.makedirs(args.preview_dir, exist_ok=True)
        lm = report["landmarks"]
        shown = {k: v for k, v in lm.items() if not any(k.startswith(f.lower()) for f in FINGERS)}
        shown.update({k: v for k, v in lm.items() if k.endswith("3.L") or k.endswith("3.R")})
        files = A.render_views(args.preview_dir, "markers_", shown, CHAINS)
        report["previews"] = files
        ok = all(os.path.getsize(p) > 0 for p in files.values() if os.path.exists(p)) and \
            all(os.path.exists(p) for p in files.values())
        report["gates"].append(gate("markers.previews", sorted(files), ["front", "side"], ok and len(files) == 2))
        report["ok"] = all(g["ok"] for g in report["gates"])
    return (0 if report["ok"] else 2), report


def run_host(args) -> tuple[int, dict]:
    if args.file is None:
        return 1, {"tool": "arp_markers", "error": "a mesh file is required outside Blender"}
    try:
        V, F = M.load_mesh(args.file, args.up)
        report = build_report(V, F, _opts(args))
    except (OSError, ValueError, KeyError, M.Refused, Refused) as exc:
        return 1, {"tool": "arp_markers", "error": str(exc)}
    report["mesh"] = str(args.file)
    return (0 if report["ok"] else 2), report


def in_blender() -> bool:
    try:
        import bpy  # noqa: F401
        return True
    except ImportError:
        return False


# ------------------------------------------------------------------------------ selftests


def _hand_points(fingers_apart: bool):
    """A palm-down left hand at the origin pointing +X, 0.18 long: four finger tubes or a mitten."""
    pieces = [M.tube((0.0, 0, 0), (0.09, 0, 0), 0.0, rx=0.045, ry=0.012)]
    if fingers_apart:
        for y, length in ((-0.0285, 0.075), (-0.0095, 0.09), (0.0095, 0.08), (0.0285, 0.06)):
            pieces.append(M.tube((0.08, y, 0), (0.09 + length, y, 0), 0.0072))
    else:
        pieces.append(M.tube((0.09, 0, 0), (0.18, 0, 0), 0.0, rx=0.04, ry=0.012))
    v, f = M.assemble(pieces)
    pts, _ = M.surface_samples(v, f, 6000)
    return pts


def selftest_host() -> tuple[int, list, int]:
    checks, failed = 0, []

    def ok(name, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failed.append(name)
    opts = {"spine_bones": 3, "fingers": "auto", "adjust": None, "arm_angle": (30.0, 60.0),
            "arm_ratios": (0.42, 0.75), "symmetry_max": 0.02, "no_window_gate": False}
    v, f = M.body()
    rep = build_report(v, f, opts)
    lm, H = rep["landmarks"], rep["height"]
    ok("tube body: ok", rep["ok"])
    s45 = math.sqrt(0.5)
    sh_true = np.array([0.17, 0, 1.38])
    tip_true = sh_true + (0.62 + 0.045) * np.array([s45, 0, -s45])
    ok("hip height near the leg tube top", abs(lm["hip.L"][2] - 0.90) < 0.05 * H)
    ok("hip x on the leg", abs(lm["hip.L"][0] - 0.10) < 0.02)
    ok("ankle low", lm["ankle.L"][2] < 0.13 * H)
    ok("knee by proportion on a straight tube", rep["methods"]["knee.L"] == "proportion")
    ok("shoulder within 0.04 H", np.linalg.norm(np.array(lm["shoulder.L"]) - sh_true) < 0.04 * H)
    ok("hand tip within 0.03 H", np.linalg.norm(np.array(lm["hand_tip.L"]) - tip_true) < 0.03 * H)
    ok("arm angle 45 +- 3", abs(rep["arm_angle_deg"] - 45) < 3)
    ok("sides mirrored", np.allclose(lm["knee.R"], [-lm["knee.L"][0], lm["knee.L"][1], lm["knee.L"][2]]))
    ok("neck between 0.80 and 0.92 H", 0.80 * H < lm["neck"][2] < 0.92 * H)
    ok("toe in front of heel", lm["toe_tip.L"][1] < lm["ball.L"][1] < lm["heel.L"][1])
    refs = rep["arp_refs"]
    ok("refs: three spine bones and the root", all(f"spine_0{i}_ref.x" in refs for i in (1, 2, 3)))
    ok("refs: knee bent forward", refs["thigh_ref.l"]["tail"][1] < min(lm["hip.L"][1], lm["ankle.L"][1]) - 1e-4)
    ok("refs: chains connected", refs["arm_ref.l"]["tail"] == refs["forearm_ref.l"]["head"])
    names = [b["name"] for b in rep["contract_bones"]["bones"]]
    ok("contract spec: 7 centre + 23 .L bones", len(names) == 30 and "Little3.L" in names and "Root" in names)
    ok("fingers fixed on a tube arm", rep["fingers"]["mode"] == "fixed" and rep["fingers"].get("reason"))
    mit = build_report(v, f, dict(opts, mitten=True))["contract_bones"]["bones"]
    ok("--mitten: finger bones kept, not deforming", sum(1 for b in mit if b["name"][:-3] in FINGERS
                                                          and not b["deform"]) == 15)
    # failing inputs
    v2, f2 = M.body(fused_legs=True)
    try:
        build_report(v2, f2, opts)
        ok("fused legs refused", False)
    except Refused:
        ok("fused legs refused", True)
    v3, f3 = M.body(t_pose=True)
    try:
        build_report(v3, f3, opts)
        ok("T-pose refused", False)
    except Refused:
        ok("T-pose refused", True)
    rep4 = build_report(v, f, dict(opts, arm_angle=(50.0, 60.0)))
    ok("arm angle outside 50-60 fails", not rep4["ok"] and not next(g for g in rep4["gates"]
                                                                     if g["name"] == "markers.arm_angle")["ok"])
    adj = {"shoulder.L": [0.16, 0.0, 1.0]}
    rep5 = build_report(v, f, dict(opts, adjust=adj))
    ok("adjust: moved, mirrored, method adjusted", rep5["landmarks"]["shoulder.R"][0] == -0.16 and
       rep5["methods"]["shoulder.L"] == "adjusted")
    ok("adjust: a low shoulder fails the window gate", not next(g for g in rep5["gates"]
                                                                 if g["name"] == "markers.windows")["ok"])
    ok("no window gate: reported only", next(g for g in build_report(v, f, dict(opts, adjust=adj, no_window_gate=True))["gates"]
                                             if g["name"] == "markers.windows")["ok"])
    # an asymmetric body fails the symmetry gate: move the left leg out
    vs, fs = M.body()
    sel = (vs[:, 0] > 0.04) & (vs[:, 2] < 0.85)
    vs = vs.copy()
    vs[sel, 0] += 0.06
    rep6 = build_report(vs, fs, opts)
    ok("asymmetric legs fail symmetry", not next(g for g in rep6["gates"] if g["name"] == "markers.symmetry")["ok"])
    # a person adjusts the markers that differ: they leave the gate and are reported as accepted
    limit = 0.02 * rep6["height"]
    off = [k for k, val in rep6["asymmetry_m"].items() if val > limit]
    adj6 = {k + ".L": rep6["landmarks"][k + ".L"] for k in off}
    rep7 = build_report(vs, fs, dict(opts, adjust=adj6))
    sym7 = next(g for g in rep7["gates"] if g["name"] == "markers.symmetry")
    ok("adjusted markers: symmetry passes, asymmetry_accepted lists them",
       bool(off) and sym7["ok"] and set(rep7["asymmetry_accepted"]) == set(off))
    one = {off[0] + ".L": rep6["landmarks"][off[0] + ".L"]} if len(off) > 1 else {}
    rep8 = build_report(vs, fs, dict(opts, adjust=one)) if one else rep6
    ok("adjusting one of several: the others still fail symmetry",
       not next(g for g in rep8["gates"] if g["name"] == "markers.symmetry")["ok"])
    # finger detection
    frame = (np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]), 0.18)
    found, reason = detect_fingers(_hand_points(True), np.zeros(3), frame)
    ok("four fingers apart: detected", found is not None and len(found) == 4)
    if found:
        tips = {k: v[-1] for k, v in found.items()}
        ok("index tip near 0.165", abs(tips["Index"][0] - 0.165) < 0.02 and tips["Index"][1] < tips["Little"][1])
        ok("little shorter than middle", tips["Little"][0] < tips["Middle"][0])
    found, reason = detect_fingers(_hand_points(False), np.zeros(3), frame)
    ok("mitten: not detected, reason given", found is None and "four" in reason)
    # files through the CLI
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "body.obj"
        M.write_obj(path, v, f)
        code, rep = run_host(parser().parse_args([str(path)]))
        ok("cli: exit 0 on the body", code == 0)
        path2 = Path(d) / "fused.obj"
        M.write_obj(path2, v2, f2)
        ok("cli: fused legs exit 1", run_host(parser().parse_args([str(path2)]))[0] == 1)
        ok("cli: missing file exit 1", run_host(parser().parse_args([str(Path(d) / "x.glb")]))[0] == 1)
    return checks, failed, 0


def selftest_blender() -> tuple[int, list]:
    import bpy  # noqa: F401
    import autorig_blender as A
    checks, failed = 0, []

    def ok(name, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failed.append(name)
    A.clear_scene()
    body, truth = A.build_runner()
    with tempfile.TemporaryDirectory() as d:
        args = parser().parse_args(["--mesh", body.name, "--preview-dir", d, "--out", os.path.join(d, "m.json")])
        code, rep = run_blender(args)
        ok("runner: exit 0", code == 0)
        if code == 0:
            lm, H = rep["landmarks"], rep["height"]
            for name in ("hip.L", "knee.L", "ankle.L", "shoulder.L", "elbow.L", "wrist.L"):
                err = float(np.linalg.norm(np.array(lm[name]) - np.array(truth[name])))
                ok(f"runner {name} within 0.04 H ({err:.3f} m)", err < 0.04 * H)
            ok("runner neck within 0.04 H", abs(lm["neck"][2] - truth["neck"][2]) < 0.04 * H)
            ok("previews written", all(os.path.getsize(p) > 1000 for p in rep["previews"].values()))
        V, F = A.mesh_arrays(body)
        glb = os.path.join(d, "runner.glb")
        M.write_glb(Path(glb), V, F)
        A.clear_scene()
        code, rep2 = run_blender(parser().parse_args(["--import", glb]))
        ok("--import glb: exit 0, same height", code == 0 and abs(rep2["height"] - rep["height"]) < 1e-3)
        A.clear_scene()
        body, _ = A.build_runner(fused_legs=True)
        code, rep = run_blender(parser().parse_args(["--mesh", body.name]))
        ok("fused runner: exit 1", code == 1)
        ok("unknown mesh: exit 1", run_blender(parser().parse_args(["--mesh", "Nope"]))[0] == 1)
    return checks, failed


def main() -> None:
    blender = in_blender()
    argv = sys.argv[sys.argv.index("--") + 1:] if (blender and "--" in sys.argv) else \
        ([] if blender else sys.argv[1:])
    if argv[:1] == ["selftest"]:                        # `selftest` and `--selftest` are one command
        argv = ["--selftest", *argv[1:]]
    args = parser().parse_args(argv)
    if args.selftest:
        checks, failed, _ = selftest_host()
        if blender:
            c2, f2 = selftest_blender()
            checks, failed = checks + c2, failed + f2
        report = {"selftest": "pass" if not failed else "fail", "checks": checks, "failed": failed}
        code = 0 if not failed else 1
    else:
        code, report = run_blender(args) if (blender and not args.file) else run_host(args)
    text = json.dumps(report, indent=2)
    if args.out and not args.selftest:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    sys.stdout.flush()
    sys.exit(code)


if __name__ == "__main__":
    main()
