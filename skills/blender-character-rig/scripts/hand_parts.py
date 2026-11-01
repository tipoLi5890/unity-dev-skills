#!/usr/bin/env python3
"""hand_parts.py — the hands of a character in parts (tier fine): forearm and wrist measured on the anchor,
the hand part's registration and finger gates, and its attachment at the sleeve.

A hand is generated as its own image-to-3D job (comfyui-asset-generation `part_views.py`, which hands
hand regions to `hand_views.py`) and replaces the anchor's hand from the sleeve's cuff down. This module
holds the numpy geometry (no scipy, no PIL: it also runs inside Blender) and the Blender attachment that
`assemble_parts.py hands` runs.

usage:
    hand_parts.py gate PLAN.parts.json --part hand_r [--glb GEN.glb] [--json-out PATH]
    hand_parts.py --selftest
    (part_math.py plan --tier fine calls plan_hands; assemble_parts.py hands calls assemble_hands)

Measured per hand on the anchor (plan_hands, written to the part's `wrist`):
  axis      sections perpendicular to a first axis (the hand's outermost point toward the shoulder at
            chest height) are tracked from the hand up the arm; the axis is refitted through the
            centroids of the forearm's sections, then measured again.
  r_fore    median equivalent radius (sqrt(area / pi)) of the forearm sections, from the narrowest single
            section (the wrist) to the cuff; r_sleeve the same for the sleeve above the cuff.
  rim       the first section past the wrist wider than 1.4 x r_fore. The wrist plane is fitted through
            the cuff edge in 16 sectors around the axis (the first step outward of the mid radius), so
            a cuff cut at an angle keeps its whole lip; past 40 degrees of tilt, or under 8 sectors, the
            plane is perpendicular to the axis.
  bottom    the part's flat end: the wrist plane moved 1.8 x r_fore into the sleeve (one forearm
            diameter of overlap, hidden by the sleeve).
  region    the anchor faces past the wrist plane connected to the hand's outermost point.
  views     the crop boxes (one side L = 1.1 x the largest extent of the region and the forearm stub,
            the same rows in every view, x centred per view) and keep masks (the region where it is the
            nearest surface; the sleeve near the cuff grown 2 px and 0.5 x r_fore toward the hand). The view the body hides (the right
            hand's left view, the left hand's right view) is the mirror of the opposite side view, its
            box mirrored about the frame centre.

gate (numpy; part_views.py generate runs it after each hand job and retries the next seed on exit 2):
  part.register.*  the head's limits: the part starts at scale L/1024 at the boxes' centre, unrotated;
                   trimmed point-to-plane ICP onto the anchor's hand region; |s/s0 - 1| <= 0.05 (a
                   similarity fit), RMS <= 0.03 of the region height and rotation <= 6 degrees (a rigid
                   fit at the crop's scale, the one applied).
  hand.fingers     >= 4 separate sections in >= 30 % of 40 slices across the hand, 0.55-0.95 of its
                   length from the wrist plane along the hand's own long axis.

assemble_hands (inside Blender, on the `three` assembly's <c>_parts.blend): per hand, the painted part
(generated.painted, else paint/<part>/<stem>_painted.glb, else generated.glb) registered as above, cut
flat at the bottom plane, held to --hand-ratio x the anchor's triangles (the job is generated at that
face target; an over-budget hand is welded and collapsed here, all reduction before the rig binds), the
finger gate again; the anchor's forearm and hand deleted past the wrist plane (the
sleeve's faces past it kept: a corner past 1.2 x r_fore and connected to the sleeve above), and the opening
capped with a fan recessed 0.2 x r_fore into the sleeve, its UVs on a block of the body texture painted
a lining colour (the sleeve's darkest tenth near the cuff, at 40 % brightness). Gates:
  seam.sleeve_clearance  the part's median radius at the wrist plane <= 0.8 x the opening's radius
  seam.hidden            >= 0.95 of the part's surface inside the sleeve (from 0.5 x r_fore past the wrist
                         plane to the bottom plane; nearer the cuff the forearm is seen going in) is hidden
                         from eight cameras: front, back, left, right and four looking into the cuff 30
                         degrees off its axis (rays to the camera through the body, the cap and the part)
  hand.triangles         each hand <= --hand-ratio x the anchor's triangles
Outputs in --out: <c>_parts.blend (Body, Head, Hair, Hand.R, Hand.L; vertex groups part.*), <c>_parts.glb,
<c>_rig.glb (Body + Head + the hands joined: what the rig stage takes), <c>_hair.glb, <c>.hands.gate.json
(gate/1) and unless --no-render hands.png (per hand: anchor and assembly, clay and textured, four views).

Exit codes: 0 every gate passed (or --selftest passed); 2 a gate failed; 1 usage error, refused input or
a failed --selftest. Arguments are parsed before numpy is imported.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

HAND_REGIONS = ("hand.L", "hand.R")
SIGN = {"hand.R": -1.0, "hand.L": 1.0}         # x sign of the hand: the character faces +Z, its right is -X
HIDDEN = {"hand.R": ("left", "right"), "hand.L": ("right", "left")}    # (hidden view, mirrored from)
VIEWS = ("front", "left", "back", "right")
RIM_JUMP = 1.4          # the cuff: the first section past the wrist wider than this x r_fore
LIP_RHO = 1.2           # the cut keeps sleeve faces reaching past this x r_fore (the hem's inner fold)
BOTTOM_DEPTH = 1.8      # the part's flat end, this many r_fore past the wrist plane inside the sleeve
TILT_MAX = 40.0         # degrees between the fitted wrist plane and the axis' normal plane
SECTORS = 16
RECESS = 0.2            # the cap's centre, this many r_fore inside the sleeve
SLEEVE_GROW = 0.5       # keep masks: the sleeve near the cuff grown this many r_fore toward the hand
FINGER_ZONE, FINGER_SLICES, FINGER_MIN, FINGER_SHARE = (0.55, 0.95), 40, 4, 0.30
REG = {"scale_ratio": 0.05, "rms": 0.03, "rotation_deg": 6.0}      # the head's limits (assemble_parts.GATES)
CLEARANCE, HIDDEN_MIN, HAND_RATIO = 0.8, 0.95, 0.2
HIDDEN_DEPTH = 0.5      # seam.hidden counts the part from this many r_fore inside the wrist plane


class Refused(Exception):
    """Input the tools will not take (exit 1)."""


def _np():
    import numpy as np
    return np


def _pm():
    import part_math as pm
    return pm


def unit(v):
    np = _np()
    v = np.asarray(v, float)
    return v / max(float(np.linalg.norm(v)), 1e-12)


def basis(a):
    """Two unit vectors perpendicular to a (and to each other)."""
    np = _np()
    ref = np.array([0.0, 0.0, 1.0]) if abs(a[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = unit(np.cross(a, ref))
    return u, np.cross(a, u)


# ------------------------------------------------------------------------------------------ slicing
def slice_plane(V, F, o, n):
    """Loops (each (k, 3)) where a welded mesh crosses the plane through o with normal n."""
    np = _np()
    d = (V - o) @ n
    d = np.where(np.abs(d) < 1e-12, 1e-12, d)
    s = d[F] > 0
    fc = F[s.any(1) & ~s.all(1)]
    if not len(fc):
        return []
    E = np.stack([fc[:, [0, 1]], fc[:, [1, 2]], fc[:, [2, 0]]], 1)
    cr = (d[E[..., 0]] > 0) != (d[E[..., 1]] > 0)
    two = cr.sum(1) == 2
    E, cr = E[two], cr[two]
    Es = np.sort(E, axis=2)
    key = Es[..., 0] * (int(V.shape[0]) + 1) + Es[..., 1]
    pairs = key[cr].reshape(-1, 2)
    ea, eb = Es[cr][:, 0], Es[cr][:, 1]
    ta = d[ea] / (d[ea] - d[eb])
    pts = V[ea] + ta[:, None] * (V[eb] - V[ea])
    pos = dict(zip(key[cr].tolist(), pts))
    adj = {}
    for i, (k0, k1) in enumerate(pairs.tolist()):
        adj.setdefault(k0, []).append(i)
        adj.setdefault(k1, []).append(i)
    used = np.zeros(len(pairs), bool)
    loops = []
    P = pairs.tolist()
    for i in range(len(P)):
        if used[i]:
            continue
        used[i] = True
        start, cur = P[i]
        chain = [start, cur]
        while True:
            nxt = [j for j in adj[cur] if not used[j]]
            if not nxt:
                break
            j = nxt[0]
            used[j] = True
            k2 = P[j][1] if P[j][0] == cur else P[j][0]
            if k2 == start:
                break
            chain.append(k2)
            cur = k2
        if len(chain) >= 3:           # a decimated finger's section can be a triangle
            loops.append(np.array([pos[k] for k in chain]))
    return loops


def _loop2d(lp, o, n):
    np = _np()
    u, w = basis(n)
    q = lp - o
    return np.c_[q @ u, q @ w]


def _area(p):
    np = _np()
    return 0.5 * abs(float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])))


def top_sections(loops, o, n, reach, min_area=0.0):
    """The loops near o (centroid within reach in the plane) that no other such loop holds, as
    (2d points, area, 3d centroid), largest first."""
    np = _np()
    pm = _pm()
    two = [(_loop2d(lp, o, n), lp) for lp in loops]
    near = [(p2, lp, _area(p2)) for p2, lp in two if np.linalg.norm(p2.mean(0)) < reach]
    near = [x for x in near if x[2] >= min_area]
    out = []
    for i, (p2, lp, a) in enumerate(near):
        held = any(j != i and b > a and pm.point_in_poly(p2[len(p2) // 2: len(p2) // 2 + 1], q2)[0]
                   for j, (q2, _, b) in enumerate(near))
        if not held:
            out.append((p2, a, lp.mean(0)))
    return sorted(out, key=lambda x: -x[1])


def profile(V, F, start, a, ts, reach, track=True):
    """Sections perpendicular to a at start + a t (following the centroid when track): per t the
    largest top section's equivalent radius, centroid and how many top sections there are."""
    np = _np()
    rows = []
    o = np.asarray(start, float).copy()
    prev_t = 0.0
    for t in ts:
        o = o + a * (t - prev_t)
        prev_t = t
        secs = top_sections(slice_plane(V, F, o, a), o, a, reach)
        if not secs:
            rows.append((t, np.nan, None, 0))
            continue
        p2, ar, c = secs[0]
        rows.append((t, math.sqrt(ar / math.pi), c, len(secs)))
        if track:
            o = c - a * ((c - o) @ a)
    return rows


# ------------------------------------------------------------------------------------------ forearm
def shoulder_hint(V, F, anchor, sg):
    """A point at chest height on the hand's side: the first axis aims from the hand at it."""
    np = _np()
    pm = _pm()
    neck = anchor["neck"]
    y = float(neck["band"][0]) - 0.5 * float(anchor["head_height"])
    ax = np.asarray(neck["axis_xz"], float)
    half = None
    for lp in pm.slice_loops(V, F, y):
        if lp["closed"] and pm.point_in_poly(ax[None], lp["xz"])[0]:
            half = float((sg * lp["xz"][:, 0]).max())
            break
    if half is None:
        half = 0.15 * float(V[:, 1].max() - V[:, 1].min())
    return np.array([sg * 0.6 * half, y, ax[1]])


def measure_forearm(V, F, anchor, region):
    """The wrist geometry of one hand on the welded anchor (glTF frame): dict, or Refused."""
    np = _np()
    sg = SIGN[region]
    H = float(V[:, 1].max() - V[:, 1].min())
    tip = V[int(np.argmax(sg * V[:, 0]))]
    a = unit(shoulder_hint(V, F, anchor, sg) - tip)
    reach = 0.08 * H
    rows = profile(V, F, tip, a, np.arange(0.01, 0.42, 0.004) * H, reach)

    def find(rows, lo, hi):
        # the wrist: the narrowest single section with a wider section (the palm) within 0.08 H before it,
        # so a lone fingertip is never taken for it
        ok = [r for r in rows if lo <= r[0] <= hi and r[3] == 1 and np.isfinite(r[1])
              and any(q[0] < r[0] and q[0] >= r[0] - 0.08 * H and np.isfinite(q[1]) and q[1] >= 1.1 * r[1]
                      for q in rows)]
        if not ok:
            return None
        low = min(ok, key=lambda r: r[1])
        rim = next((r for r in rows if r[0] > low[0] and np.isfinite(r[1]) and r[1] > RIM_JUMP * low[1]), None)
        return low, rim
    got = find(rows, 0.06 * H, 0.30 * H)
    if got is None or got[1] is None:
        raise Refused(f"{region}: no wrist and cuff found along the arm (a bare arm or a glove up to the "
                      "elbow: no sleeve to hide the seam)")
    low, rim = got
    fore = [r for r in rows if low[0] - 0.02 * H <= r[0] < rim[0] and r[2] is not None and r[3] == 1]
    if len(fore) >= 3:
        C = np.array([r[2] for r in fore])
        m = C.mean(0)
        a2 = np.linalg.svd(C - m)[2][0]
        a = unit(a2 * np.sign(a2 @ a))
        start = m
    else:
        start = low[2]
    # measured again along the refitted axis, both ways from the forearm
    ts = np.arange(-0.20, 0.20, 0.002) * H
    up = profile(V, F, start, a, ts[ts >= 0], reach, track=False)
    down = profile(V, F, start, -a, -ts[ts < 0][::-1], reach, track=False)
    rows2 = [(-t, r, c, k) for t, r, c, k in down][::-1] + up
    got = find(rows2, -0.06 * H, 0.20 * H)
    if got is None or got[1] is None:
        raise Refused(f"{region}: the cuff is lost along the refitted forearm axis")
    low, rim = got
    fore_r = [r[1] for r in rows2 if low[0] <= r[0] < rim[0] and np.isfinite(r[1])]
    r_fore = float(np.median(fore_r)) if fore_r else float(low[1])
    sl = [r[1] for r in rows2 if rim[0] + 0.01 * H <= r[0] <= rim[0] + 0.05 * H and np.isfinite(r[1])]
    r_sleeve = float(np.median(sl)) if sl else float(rim[1])
    o_rim = start + a * rim[0]          # on the refitted axis (a section cut by an angled cuff is off it)
    thr = 0.5 * (r_fore + r_sleeve)
    normal, tilt, how, nsec = wrist_plane(V, F, o_rim, a, r_fore, r_sleeve, thr)
    rim_pt = o_rim          # the axis point on the plane
    if how == "fitted":
        rim_pt = o_rim + a * float(normal @ (nsec["point"] - o_rim)) / max(float(a @ normal), 1e-6)
    bottom = rim_pt + a * (BOTTOM_DEPTH * r_fore)
    return {"tip": tip, "axis": a, "rim": rim_pt, "normal": normal, "bottom": bottom, "r_fore": r_fore,
            "r_sleeve": r_sleeve, "rim_threshold": thr, "plane": how, "tilt_deg": tilt,
            "sectors": nsec["n"], "H": H}


def wrist_plane(V, F, o, a, r_fore, r_sleeve, thr, rng_seed=0):
    """The plane through the cuff edge: in SECTORS sectors around the axis, the first step (from the
    hand) of the outermost surface past thr; a least-squares plane through those points. Returns
    (normal toward the shoulder, tilt degrees, 'fitted'|'perpendicular', {n, point})."""
    np = _np()
    pm = _pm()
    rng = np.random.default_rng(rng_seed)
    u, w = basis(a)
    c = V[F].mean(1)
    t_c = (c - o) @ a
    rad_c = np.linalg.norm((c - o) - np.outer(t_c, a), axis=1)
    slab = (np.abs(t_c) < 4 * r_fore + 2 * r_sleeve) & (rad_c < 1.8 * r_sleeve)
    if slab.sum() < 30:
        return a, 0.0, "perpendicular", {"n": 0, "point": o}
    P, _, _ = pm.sample_surface(V, F, 40000, rng, face_mask=slab)
    q = P - o
    t = q @ a
    x, y = q @ u, q @ w
    rho = np.hypot(x, y)
    th = np.mod(np.arctan2(y, x), 2 * math.pi)
    sec = np.minimum((th / (2 * math.pi) * SECTORS).astype(int), SECTORS - 1)
    step = r_fore / 6
    lo = -3 * r_fore
    nb = int(round(6 * r_fore / step))
    tb = np.clip(((t - lo) / step).astype(int), -1, nb)
    ok = (tb >= 0) & (tb < nb) & (rho < 1.6 * r_sleeve)
    mx = np.full((SECTORS, nb), -1.0)
    np.maximum.at(mx, (sec[ok], tb[ok]), rho[ok])
    pts = []
    for k in range(SECTORS):
        over = mx[k] > thr
        hit = next((i for i in range(1, nb - 2) if over[i] and over[i + 1] and over[i + 2] and not over[i - 1]),
                   None)
        if hit is None:
            continue
        ang = (k + 0.5) / SECTORS * 2 * math.pi
        r_edge = float(mx[k, hit + 1])      # the cuff's own radius there (thr would steepen the plane)
        pts.append(o + a * (lo + hit * step) + r_edge * (math.cos(ang) * u + math.sin(ang) * w))
    if len(pts) < 8:
        return a, 0.0, "perpendicular", {"n": len(pts), "point": o}
    Pk = np.array(pts)
    m = Pk.mean(0)
    n = np.linalg.svd(Pk - m)[2][2]
    n = unit(n * np.sign(n @ a))
    res = np.abs((Pk - m) @ n)
    keep = res <= max(3 * np.median(res), 0.15 * r_fore)
    if keep.sum() >= 8 and keep.sum() < len(Pk):
        m = Pk[keep].mean(0)
        n = np.linalg.svd(Pk[keep] - m)[2][2]
        n = unit(n * np.sign(n @ a))
    tilt = math.degrees(math.acos(min(1.0, float(n @ a))))
    if tilt > TILT_MAX:
        return a, tilt, "perpendicular", {"n": len(pts), "point": o}
    return n, tilt, "fitted", {"n": int(keep.sum()), "point": m}


def hand_region(V, F, wr):
    """Faces past the wrist plane in pieces (connected over the faces past it) that reach no farther
    from the wrist than 1.1 x the hand's outermost point: the hand, never the thigh beside it."""
    np = _np()
    pm = _pm()
    c = V[F].mean(1)
    d = (c - wr["rim"]) @ wr["normal"]
    dist = np.linalg.norm(c - wr["rim"], axis=1)
    beyond = (d < 0) & (dist < 0.45 * wr["H"])
    lab = pm.face_components(F, beyond)
    if not beyond.any():
        return beyond
    reach = 1.1 * float(np.linalg.norm(wr["tip"] - wr["rim"]))
    far = np.full(lab.max() + 1, 0.0)
    np.maximum.at(far, lab[beyond], dist[beyond])
    return beyond & (far[np.maximum(lab, 0)] <= reach)


def anchor_cut(V, F, wr):
    """Anchor faces the hand part replaces: the hand region without the sleeve's lip, the faces past
    the wrist plane with a corner past LIP_RHO x r_fore that connect (through such faces, within
    2 x r_sleeve of the plane) to the sleeve above it; the hem's inner fold stays whole. A cuff that is not flat keeps its whole edge; the palm, reached
    from the sleeve only through the forearm, goes."""
    np = _np()
    pm = _pm()
    reg = hand_region(V, F, wr)
    c = V[F].mean(1)
    q = c - wr["rim"]
    d = q @ wr["normal"]
    qv = V - wr["rim"]
    rv = np.linalg.norm(qv - np.outer(qv @ wr["axis"], wr["axis"]), axis=1)
    rho = rv[F].max(1)                      # a hem triangle that reaches the fold stays whole
    out = (rho >= LIP_RHO * wr["r_fore"]) & (np.abs(d) < 2 * wr["r_sleeve"]) & (rho < 2.5 * wr["r_sleeve"])
    lab = pm.face_components(F, out)
    up = np.unique(lab[out & (d >= 0)])
    lip = out & (d < 0) & np.isin(lab, up[up >= 0])
    return reg & ~lip


def finger_axis(V, F, wr, region_mask):
    """The hand's own long axis: PCA of the region's points past the wrist, pointing away from the cuff."""
    np = _np()
    P = V[np.unique(F[region_mask].reshape(-1))]
    m = P.mean(0)
    ax = np.linalg.svd(P - m)[2][0]
    return unit(ax * np.sign(ax @ (m - wr["rim"])))


def finger_rows(V, F, wr, fax, length, origin):
    """Separate sections per slice across the hand, FINGER_SLICES slices over FINGER_ZONE of its length."""
    np = _np()
    out = []
    min_area = (0.003 * wr["H"]) ** 2
    for f in np.linspace(FINGER_ZONE[0], FINGER_ZONE[1], FINGER_SLICES):
        o = origin + fax * f * length
        secs = top_sections(slice_plane(V, F, o, fax), o, fax, 0.3 * length, min_area)
        out.append(len(secs))
    return out


def fingers(V, F, wr, region_mask, fax=None, frame=None):
    """hand.fingers on a mesh (the anchor's region or a registered part's faces past the wrist plane):
    (share of slices with >= FINGER_MIN sections, rows, (axis, length, origin))."""
    np = _np()
    if frame is None:
        fax = finger_axis(V, F, wr, region_mask) if fax is None else fax
        P = V[np.unique(F[region_mask].reshape(-1))]
        s = (P - wr["rim"]) @ fax
        origin = wr["rim"] + fax * float(max(s.min(), 0.0))
        length = float(s.max() - max(s.min(), 0.0))
        frame = (fax, length, origin)
    fax, length, origin = frame
    rows = finger_rows(V, F[region_mask], wr, fax, length, origin)
    return sum(r >= FINGER_MIN for r in rows) / len(rows), rows, frame


# ------------------------------------------------------------------------------------------ the plan
def wrist_json(wr):
    np = _np()
    r = lambda x: [round(float(v), 5) for v in np.asarray(x).reshape(-1)]
    return {"tip": r(wr["tip"]), "axis": r(wr["axis"]), "rim": r(wr["rim"]), "normal": r(wr["normal"]),
            "bottom": r(wr["bottom"]), "r_fore": round(wr["r_fore"], 5), "r_sleeve": round(wr["r_sleeve"], 5),
            "rim_threshold": round(wr["rim_threshold"], 5), "plane": wr["plane"],
            "tilt_deg": round(wr["tilt_deg"], 2), "sectors": int(wr["sectors"])}


def wrist_from(part, H):
    np = _np()
    w = part["wrist"]
    out = {k: np.asarray(w[k], float) for k in ("tip", "axis", "rim", "normal", "bottom")}
    out.update({k: float(w[k]) for k in ("r_fore", "r_sleeve", "rim_threshold")})
    out["H"] = float(H)
    return out


def stub_points(wr, n_len=24, n_az=32):
    """Points on the forearm stub the guide paints (0.8 x r_fore from the bottom plane to the wrist
    plane): they count toward the crop box."""
    np = _np()
    u, w = basis(wr["axis"])
    L = float((wr["bottom"] - wr["rim"]) @ wr["axis"])
    ts = np.linspace(0, L, n_len)
    th = np.linspace(0, 2 * math.pi, n_az, endpoint=False)
    T, TH = np.meshgrid(ts, th)
    r = 0.8 * wr["r_fore"]
    P = wr["rim"] + T[..., None] * wr["axis"] + r * (np.cos(TH)[..., None] * u + np.sin(TH)[..., None] * w)
    return P.reshape(-1, 3)


def hand_boxes(V, F, region_mask, wr, frame, region):
    """Crop boxes: L = 1.1 x the largest extent (region + forearm stub) over the visible views, even;
    rows shared; the hidden view's box mirrored from its source about the frame centre."""
    np = _np()
    pm = _pm()
    upp = frame["units_per_px"]
    pts = np.r_[V[np.unique(F[region_mask].reshape(-1))], stub_points(wr)]
    hidden, src = HIDDEN[region]
    tops, bots, widths, centres = [], [], {}, {}
    for view in VIEWS:
        if view == hidden:
            continue
        cx, cy = frame["offset_px"][view]
        u, y = pm.view_uv(pts, view)
        tops.append(cy - y.max() / upp)
        bots.append(cy - y.min() / upp)
        widths[view] = (u.max() - u.min()) / upp
        centres[view] = cx + (u.max() + u.min()) / 2 / upp
    top, bot = min(tops), max(bots)
    L = int(math.ceil(1.1 * max([bot - top] + list(widths.values()))))
    L += L % 2
    y0 = int(round((top + bot) / 2 - L / 2))
    boxes = {v: [int(round(c - L / 2)), y0, int(round(c - L / 2)) + L, y0 + L] for v, c in centres.items()}
    b = boxes[src]
    ctr = (b[0] + b[2]) / 2
    nc = frame["offset_px"][hidden][0] - (ctr - frame["offset_px"][src][0])
    boxes[hidden] = [int(round(nc - L / 2)), y0, int(round(nc - L / 2)) + L, y0 + L]
    return L, {v: boxes[v] for v in VIEWS}


def hand_keep(V, F, region_mask, wr, view, mask, frame):
    """The view mask where the hand (region_mask: anchor_cut's faces) is the nearest surface (dilated
    1 px), minus every other surface seen in front of it and the sleeve near the cuff, grown 2 px and
    SLEEVE_GROW x r_fore toward the hand (the drawn cuff hangs lower than the mesh's: the arm's
    analogue of the head's hood grow; the guide's forearm prior paints what it takes)."""
    np = _np()
    pm = _pm()
    c = V[F].mean(1)
    near_cuff = (np.linalg.norm(c - wr["rim"], axis=1) < 3 * wr["r_sleeve"]) & ~region_mask
    labels = np.where(region_mask, 1, np.where(near_cuff, 3, 2))
    h, w = mask.shape
    cx, cy = frame["offset_px"][view]
    upp = frame["units_per_px"]
    lab = pm.label_raster(V, F, labels, view, (w, h), (upp, cx, cy))
    sleeve = pm.dilate(lab == 3, 2)
    du, dy = pm.view_uv(-np.asarray(wr["axis"], float)[None], view)
    step = np.array([float(du[0]), -float(dy[0])])          # toward the hand in pixels (x, row)
    if np.linalg.norm(step) > 0.2:
        step /= np.linalg.norm(step)
        grown = sleeve.copy()
        for k in range(1, int(round(SLEEVE_GROW * wr["r_fore"] / upp)) + 1):
            sx, sy = int(round(step[0] * k)), int(round(step[1] * k))
            src = sleeve[max(0, -sy): h - max(0, sy), max(0, -sx): w - max(0, sx)]
            grown[max(0, sy): h - max(0, -sy), max(0, sx): w - max(0, -sx)] |= src
        sleeve = grown
    return pm.dilate(lab == 1, 1) & mask & ~sleeve & ~(lab == 2)


def _crop(m, box):
    np = _np()
    x0, y0, x1, y1 = box
    out = np.zeros((y1 - y0, x1 - x0), bool)
    sx0, sy0 = max(x0, 0), max(y0, 0)
    sx1, sy1 = min(x1, m.shape[1]), min(y1, m.shape[0])
    if sx1 > sx0 and sy1 > sy0:
        out[sy0 - y0: sy1 - y0, sx0 - x0: sx1 - x0] = m[sy0:sy1, sx0:sx1]
    return out


def plan_hands(V, F, masks, frame, anchor, parts, keep):
    """part_math.plan_core's hook for tier fine: fills each hand part's `wrist`, `seam`, `views` and its
    keep masks (keep[name][view]); returns a summary."""
    H = float(V[:, 1].max() - V[:, 1].min())
    summary = {}
    for p in parts:
        if p.get("region") not in HAND_REGIONS:
            continue
        wr = measure_forearm(V, F, anchor, p["region"])
        reg = hand_region(V, F, wr)
        L, boxes = hand_boxes(V, F, reg, wr, frame, p["region"])
        hidden, src = HIDDEN[p["region"]]
        p["wrist"] = wrist_json(wr)
        p["seam"] = {"mode": "overlap", "depth_r_fore": BOTTOM_DEPTH}
        p["views"] = {"source": "clean-views", "box_side_px": L, "boxes": boxes, "dir": f"views/{p['name']}",
                      "keep": {v: f"views/{p['name']}/keep_{v}.png" for v in VIEWS},
                      "hidden": {"view": hidden, "mirror_of": src}}
        keep[p["name"]] = {}
        own = anchor_cut(V, F, wr)          # the region without the sleeve's lip past the plane
        for view in VIEWS:
            if view == hidden:
                continue
            keep[p["name"]][view] = _crop(hand_keep(V, F, own, wr, view, masks[view], frame), boxes[view])
        keep[p["name"]][hidden] = keep[p["name"]][src][:, ::-1].copy()
        summary[p["name"]] = {"r_fore": round(wr["r_fore"], 4), "r_sleeve": round(wr["r_sleeve"], 4),
                              "plane": wr["plane"], "tilt_deg": round(wr["tilt_deg"], 1),
                              "region_faces": int(reg.sum()), "box_side_px": L}
    return summary


# ------------------------------------------------------------------------------------------ the gate
def register(part, frame, Va, Fa, wr, Vp, Fp, rng_seed=0, nn=None):
    """The hand part onto the anchor's hand region: (gates, detail, (s, R, t) applied, region mask)."""
    np = _np()
    pm = _pm()
    rng = np.random.default_rng(rng_seed)
    reg_a = hand_region(Va, Fa, wr)
    Q, Qn, _ = pm.sample_surface(Va, Fa, 20000, rng, face_mask=reg_a)
    L = float(part["views"]["box_side_px"])
    s0 = L / 1024.0
    t0 = pm.box_centre(frame, part["views"]["boxes"])
    cp = s0 * Vp[Fp].mean(1) + t0
    keepf = ((cp - wr["rim"]) @ wr["normal"]) < 0
    P, _, _ = pm.sample_surface(Vp, Fp, 20000, rng, face_mask=keepf if keepf.sum() > 50 else None)
    box = (Q.min(0), Q.max(0))
    nn = nn or pm.GridNN(Q)
    sim = pm.similarity_icp(P, Q, s0, np.eye(3), t0, nn=nn, Qn=Qn, region_box=box)
    rig = pm.similarity_icp(P, Q, s0, np.eye(3), t0, nn=nn, Qn=Qn, region_box=box, fix_scale=True)
    ratio = sim["s"] / s0
    r4 = lambda x: round(float(x), 4)
    gates = [_gate("part.register.scale_ratio", r4(ratio), f"|s/s0 - 1| <= {REG['scale_ratio']}",
                   abs(ratio - 1) <= REG["scale_ratio"]),
             _gate("part.register.rms", r4(rig["rms_inside"]), f"<= {REG['rms']} of region height",
                   rig["rms_inside"] <= REG["rms"]),
             _gate("part.register.rotation_deg", r4(rig["rotation_deg"]), f"<= {REG['rotation_deg']}",
                   rig["rotation_deg"] <= REG["rotation_deg"])]
    M = np.r_[np.c_[rig["s"] * rig["R"], rig["t"]], [[0, 0, 0, 1]]]
    detail = {"s0": r4(s0), "scale_ratio": r4(ratio), "rotation_deg": r4(rig["rotation_deg"]),
              "rms_inside": r4(rig["rms_inside"]), "iterations": rig["iterations"], "matrix": M.round(6).tolist()}
    return gates, detail, (rig["s"], rig["R"], rig["t"]), reg_a


def _gate(name, value, limit, passed, **extra):
    return {"name": name, "value": value, "limit": limit, "pass": bool(passed), **extra}


def finger_gate(V, F, wr, region_mask, frame_axes=None, label=""):
    share, rows, fr = fingers(V, F, wr, region_mask, frame=frame_axes)
    g = _gate(f"hand.fingers{label}", round(share, 4),
              f">= {FINGER_SHARE} of {FINGER_SLICES} slices with >= {FINGER_MIN} sections", share >= FINGER_SHARE,
              slices_ge4=int(sum(r >= FINGER_MIN for r in rows)), max_sections=int(max(rows) if rows else 0))
    return g, rows, fr


def placed_region(Vr, Fp, wr):
    np = _np()
    return ((Vr[Fp].mean(1) - wr["rim"]) @ wr["normal"]) < 0


def gate_part(plan, base, part, glb=None):
    """Registration and finger gates of one generated hand (numpy): gate/1 report."""
    np = _np()
    pm = _pm()
    anchor = plan["anchor"]
    ga = pm.read_glb(os.path.join(base, anchor["glb"]))
    Va, Fa, _ = pm.weld(ga["V"], ga["F"])
    H = float(Va[:, 1].max() - Va[:, 1].min())
    if "wrist" not in part:
        raise Refused(f"part {part['name']}: no wrist measurements: run part_math.py plan --tier fine")
    wr = wrist_from(part, H)
    path = glb or os.path.join(base, (part.get("generated") or {}).get("glb", ""))
    if not os.path.isfile(path):
        raise Refused(f"part {part['name']}: no generated GLB ({path}): run part_views.py generate")
    gp = pm.read_glb(path)
    Vp, Fp, _ = pm.weld(gp["V"], gp["F"])
    gates, detail, (s, R, t), reg_a = register(part, anchor["frame"], Va, Fa, wr, Vp, Fp)
    ga_, rows_a, fr = finger_gate(Va, Fa, wr, reg_a)
    Vr = s * Vp @ R.T + t
    g, rows, _ = finger_gate(Vr, Fp, wr, placed_region(Vr, Fp, wr), frame_axes=fr)
    gates.append(g)
    ok = all(x["pass"] for x in gates)
    return {"schema": "gate/1", "tool": "hand_parts", "pass": ok, "ok": ok, "verdict": "green" if ok else "failed",
            "part": part["name"], "glb": os.path.abspath(path), "register": detail,
            "fingers": {"part_rows": rows, "anchor_share": ga_["value"], "anchor_rows": rows_a,
                        "triangles": int(len(Fp))}, "gates": gates}


def cmd_gate(args):
    pm = _pm()
    try:
        plan, base = pm.load_plan(args.plan)
    except (pm.Refused, OSError, ValueError) as exc:
        return 1, {"refused": str(exc)}
    part = next((p for p in plan["parts"] if p["name"] == args.part), None)
    if part is None or part.get("region") not in HAND_REGIONS:
        return 1, {"refused": f"--part {args.part}: no hand part of that name in the plan"}
    try:
        rep = gate_part(plan, base, part, args.glb)
    except Refused as exc:
        return 1, {"refused": str(exc)}
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(rep, handle, indent=1)
    return (0 if rep["pass"] else 2), rep


# ------------------------------------------------------------------------------------------ Blender
def bisect_plane(obj, co_gl, n_gl):
    """Cut every face crossing a plane (glTF frame point and normal); triangles kept."""
    import bmesh
    from mathutils import Vector
    np = _np()
    co = np.asarray(co_gl, float)
    n = np.asarray(n_gl, float)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-9,
                           plane_co=Vector((co[0], -co[2], co[1])), plane_no=Vector((n[0], -n[2], n[1])))
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def decimate(obj, target):
    """Only when a hand came over its budget (part_views.py generate sets the job's face target): weld
    by position (an import splits vertices at UV seams, and a collapse would tear them open) and
    collapse toward target triangles. A non-manifold mesh may stop short: hand.triangles then fails and
    the hand is generated again at its budget. Returns the triangle count after."""
    import bmesh
    import bpy
    n = len(obj.data.polygons)
    if n <= target:
        return n
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    n = len(obj.data.polygons)
    if n <= target:
        return n
    mod = obj.modifiers.new("hand_decimate", 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = target / n
    mod.use_collapse_triangulate = True
    with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return len(obj.data.polygons)


def free_block(uv_tri, cells=256, margin=2):
    """A texel block of a cells x cells grid over the texture that no triangle covers, at least margin
    blocks from any covered one (the farthest such), as (i, j) or None."""
    np = _np()
    pm = _pm()
    _, cov = pm.uv_raster(uv_tri, np.zeros((len(uv_tri), 3, 1)), cells, cells)
    dist = np.where(cov, 0, cells)
    grown = cov.copy()
    for k in range(1, cells):
        if grown.all():
            break
        g = grown.copy()
        g[1:] |= grown[:-1]
        g[:-1] |= grown[1:]
        g[:, 1:] |= grown[:, :-1]
        g[:, :-1] |= grown[:, 1:]
        dist = np.where(g & ~grown, k, dist)
        grown = g
    if dist.max() < margin + 1:
        return None
    i, j = np.unravel_index(int(np.argmax(dist)), dist.shape)
    return int(i), int(j)


def lining_colour(img, uv_tri, faces):
    """The sleeve's darkest tenth near the cuff at 40 % brightness (linear floats 0..1)."""
    np = _np()
    pm = _pm()
    if not len(faces):
        return np.array([0.02, 0.02, 0.02])
    uv = uv_tri[faces].mean(1)
    col = pm.sample_texture(img, uv)
    lum = col @ [0.2126, 0.7152, 0.0722]
    dark = col[lum <= np.quantile(lum, 0.1)]
    return np.clip(dark.mean(0) * 0.4, 0, 1)


def cap_opening(body, wr, lining):
    """Fill the boundary loop the cut left at the cuff with a fan whose centre sits RECESS x r_fore inside
    the sleeve; the cap's UVs go to a block of the body texture painted the lining colour. Returns
    (opening radius median, cap faces, how the lining was placed)."""
    import bmesh
    from mathutils import Vector
    import assemble_parts as ap
    np = _np()
    node = ap.base_colour_node(body)
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bnd = [e for e in bm.edges if e.is_boundary]
    if not bnd:
        bm.free()
        return None, 0, "no opening"
    mid = np.array([[(e.verts[0].co + e.verts[1].co)[i] / 2 for i in range(3)] for e in bnd])
    mid_g = np.c_[mid[:, 0], mid[:, 2], -mid[:, 1]]
    q = mid_g - wr["rim"]
    d = q @ wr["normal"]
    rho = np.linalg.norm(q - np.outer(q @ wr["axis"], wr["axis"]), axis=1)
    near = (np.abs(d) < 1.0 * wr["r_sleeve"]) & (rho < 1.5 * wr["r_sleeve"])
    edges = [e for e, k in zip(bnd, near) if k]
    if not edges:
        bm.free()
        return None, 0, "no opening near the cuff"
    radius = float(np.median(rho[near]))
    res = bmesh.ops.holes_fill(bm, edges=edges, sides=0)
    poked = bmesh.ops.poke(bm, faces=res["faces"])
    centre = wr["rim"] + wr["axis"] * (RECESS * wr["r_fore"])
    for v in poked["verts"]:
        v.co = Vector((centre[0], -centre[2], centre[1]))
    new_faces = [f for f in poked["faces"]]
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    how = "untextured"
    uvl = bm.loops.layers.uv.active
    if uvl is not None and node is not None:
        img = node.image
        w, h = img.size
        uv_tri = np.array([[[l[uvl].uv[0], l[uvl].uv[1]] for l in f.loops] for f in bm.faces if len(f.loops) == 3
                           and f not in new_faces])
        cells = 256
        cell = free_block(uv_tri, cells)
        px = np.empty(w * h * img.channels, np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(h, w, img.channels)
        if cell is not None:
            i, j = cell
            y0, y1 = int(i * h / cells), int((i + 1) * h / cells)
            x0, x1 = int(j * w / cells), int((j + 1) * w / cells)
            px[y0:y1, x0:x1, :3] = lining
            if img.channels == 4:
                px[y0:y1, x0:x1, 3] = 1.0
            img.pixels.foreach_set(px.reshape(-1))
            img.update()
            if img.packed_file is not None or not img.filepath:
                img.pack()
            uv = ((j + 0.5) / cells, (i + 0.5) / cells)
            how = f"block {cell} of a {cells} grid"
        else:
            lum = px[..., :3] @ np.array([0.2126, 0.7152, 0.0722])
            k = int(np.argmin(np.abs(lum - float(np.dot(lining, [0.2126, 0.7152, 0.0722])))))
            uv = (((k % w) + 0.5) / w, ((k // w) + 0.5) / h)
            how = "nearest texel"
        for f in new_faces:
            if f.is_valid:
                for l in f.loops:
                    l[uvl].uv = uv
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    return radius, len(new_faces), how


def hidden_share(part_obj, occluders, wr, n=1500, seed=0):
    """Share of the part's surface inside the sleeve (from HIDDEN_DEPTH x r_fore past the wrist plane
    to its bottom) that no camera sees: front, back, left, right and four into the cuff 30 degrees off
    its axis. Just inside the cuff the forearm is seen going into the sleeve, as on the anchor; deeper,
    nothing of the overlap or its cut end may show."""
    import bmesh
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    import assemble_parts as ap
    np = _np()
    pm = _pm()
    V, F, _ = ap.arrays(part_obj)
    c = V[F].mean(1)
    d = (c - wr["rim"]) @ wr["normal"]
    inside = d > HIDDEN_DEPTH * wr["r_fore"]
    if inside.sum() < 10:
        return 1.0, 0
    rng = np.random.default_rng(seed)
    P, N, _ = pm.sample_surface(V, F, n, rng, face_mask=inside)
    bm = bmesh.new()
    for o in occluders:
        bm.from_mesh(o.data)
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    u, w = basis(wr["axis"])
    cams = [np.array(x, float) for x in ((0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0))]
    for k in range(4):
        ang = k * math.pi / 2
        cams.append(unit(-wr["axis"] * math.cos(math.radians(30)) +
                         math.sin(math.radians(30)) * (math.cos(ang) * u + math.sin(ang) * w)))
    seen = np.zeros(len(P), bool)
    for cdir in cams:            # cdir: from the point toward the camera (glTF frame)
        face = (N @ cdir) > 0
        for i in np.nonzero(face & ~seen)[0]:
            o = P[i] + cdir * 1e-4
            hit = tree.ray_cast(Vector((o[0], -o[2], o[1])), Vector((cdir[0], -cdir[2], cdir[1])), 10.0)
            if hit[0] is None:
                seen[i] = True
    return float(1 - seen.mean()), int(len(P))


def _hand_glb(base, part):
    gen = part.get("generated") or {}
    cands = [os.path.join(base, gen[k]) for k in ("painted", "glb") if gen.get(k)]
    if gen.get("glb"):
        stem = os.path.splitext(os.path.basename(gen["glb"]))[0]
        cands.insert(len(cands) - 1, os.path.join(base, "paint", part["name"], f"{stem}_painted.glb"))
    return next((p for p in cands if os.path.isfile(p)), None)


def assemble_hands(plan_path, assembly_dir, out_dir, ratio=HAND_RATIO, render=True, px=420):
    """Attach each hand part onto the three assembly (Blender); returns (exit code, gate/1 report)."""
    import bpy
    import assemble_parts as ap
    np = _np()
    pm = _pm()
    t_start = time.time()
    try:
        plan, base = pm.load_plan(plan_path)
    except (pm.Refused, OSError, ValueError) as exc:
        raise Refused(str(exc))
    c = plan["character"]
    hands = [p for p in plan["parts"] if p.get("region") in HAND_REGIONS]
    if plan["tier"] != "fine" or not hands:
        raise Refused("no hand parts: the plan's tier is not fine or it lists no hand.L / hand.R")
    blend = os.path.join(assembly_dir, f"{c}_parts.blend")
    if not os.path.isfile(blend):
        raise Refused(f"{blend} is missing: run assemble_parts.py assemble first")
    if os.path.abspath(out_dir) == os.path.abspath(assembly_dir):
        raise Refused("--out must differ from --assembly: the three assembly stays as it is")
    glbs = {p["name"]: _hand_glb(base, p) for p in hands}
    missing = [n for n, g in glbs.items() if g is None]
    if missing:
        raise Refused(f"parts {missing}: no generated GLB on disk (run part_views.py generate)")
    os.makedirs(out_dir, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=blend)
    objs = {o.name: o for o in bpy.data.objects if o.type == 'MESH'}
    body, head, hair, ref = objs.get("Body"), objs.get("Head"), objs.get("Hair"), objs.get("AnchorRef")
    if body is None or head is None:
        raise Refused(f"{blend}: no Body and Head objects")
    col = body.users_collection[0]
    anchor = plan["anchor"]
    ga = pm.read_glb(os.path.join(base, anchor["glb"]))
    Va, Fa, _ = pm.weld(ga["V"], ga["F"])
    H = float(Va[:, 1].max() - Va[:, 1].min())
    anchor_tris = int(len(Fa))
    target = max(500, int(round(ratio * anchor_tris)))
    gates, detail, warnings = [], {"character": c, "plan": os.path.abspath(plan_path), "anchor_triangles": anchor_tris,
                                   "body_triangles": len(body.data.polygons), "hand_target": target}, []
    made = {}
    for part in hands:
        side = part["region"][-1]
        wr = wrist_from(part, H)
        lab = f".{part['name']}"
        gp = pm.read_glb(_hand_glb(base, part))
        Vp_raw, Fp_raw, _ = pm.weld(gp["V"], gp["F"])
        g_reg, d_reg, (s, R, t), reg_a = register(part, anchor["frame"], Va, Fa, wr, Vp_raw, Fp_raw)
        for g in g_reg:
            g["name"] += lab
        gates += g_reg
        _, rows_a, fr = finger_gate(Va, Fa, wr, reg_a)
        h = ap.import_glb(glbs[part["name"]], f"Hand.{side}", col)
        ap.rename_material(h, f"{c}_{part['name']}")
        V, F, _ = ap.arrays(h)
        ap.set_coords(h, s * V @ R.T + t)
        bisect_plane(h, wr["bottom"], wr["normal"])
        V, F, _ = ap.arrays(h)
        ap.delete_faces(h, ((V[F].mean(1) - wr["bottom"]) @ wr["normal"]) > 0)
        before = len(h.data.polygons)
        V, F, _ = ap.arrays(h)
        Vw, Fw, _ = pm.weld(V, F)
        share_before, _, _ = fingers(Vw, Fw, wr, placed_region(Vw, Fw, wr), frame=fr)
        after = decimate(h, target)
        gates.append(_gate(f"hand.triangles{lab}", after, f"<= {ratio} x the anchor's {anchor_tris}",
                           after <= int(target * 1.02) + 10, before=before))
        V, F, _ = ap.arrays(h)
        Vw, Fw, _ = pm.weld(V, F)
        g_f, rows, _ = finger_gate(Vw, Fw, wr, placed_region(Vw, Fw, wr), frame_axes=fr, label=lab)
        gates.append(g_f)
        # the anchor's arm past the cuff, then the cap
        Vb, Fb, _ = ap.arrays(body)
        kill = anchor_cut(Vb, Fb, wr)
        img = None
        node = ap.base_colour_node(body)
        uvt = ap.corner_uvs(body)
        if node is not None and uvt is not None:
            img = ap.image_array(node.image, rgb3=True)
            cb = Vb[Fb].mean(1)
            q = cb - wr["rim"]
            dd = q @ wr["normal"]
            rho = np.linalg.norm(q - np.outer(q @ wr["axis"], wr["axis"]), axis=1)
            sleeve = np.nonzero((dd >= 0) & (dd < 2 * wr["r_fore"]) & (rho >= wr["rim_threshold"]) & ~kill)[0]
            lining = lining_colour(img, uvt, sleeve)
        else:
            lining = np.array([0.02, 0.02, 0.02])
        ap.delete_faces(body, kill)
        opening, cap_faces, how = cap_opening(body, wr, lining)
        Vh, Fh, _ = ap.arrays(h)
        q = Vh - wr["rim"]
        band = np.abs(q @ wr["normal"]) < 0.15 * wr["r_fore"]
        r_part = np.linalg.norm(q[band] - np.outer(q[band] @ wr["axis"], wr["axis"]), axis=1)
        r_med = float(np.median(r_part)) if len(r_part) else None
        clear = (r_med / opening) if (r_med is not None and opening) else None
        gates.append(_gate(f"seam.sleeve_clearance{lab}", None if clear is None else round(clear, 4),
                           f"<= {CLEARANCE} (part radius at the wrist plane / opening radius)",
                           clear is not None and clear <= CLEARANCE))
        made[part["name"]] = h
        detail[part["name"]] = {"glb": glbs[part["name"]], "register": d_reg, "triangles_before": before,
                                "fingers_before_decimation": round(share_before, 4),
                                "triangles": after, "finger_rows": rows, "anchor_finger_rows": rows_a,
                                "anchor_faces_cut": int(kill.sum()), "opening_radius": None if opening is None else round(opening, 5),
                                "part_radius_at_wrist": None if r_med is None else round(r_med, 5),
                                "cap_faces": cap_faces, "lining": [round(float(x), 4) for x in lining],
                                "lining_uv": how, "wrist": part["wrist"]}
    for part in hands:
        h = made[part["name"]]
        wr = wrist_from(part, H)
        lab = f".{part['name']}"
        share, n = hidden_share(h, [body] + list(made.values()), wr)
        gates.append(_gate(f"seam.hidden{lab}", round(share, 4), f">= {HIDDEN_MIN} of the part inside the sleeve "
                           "hidden from 8 cameras", share >= HIDDEN_MIN, samples=n))
        ap.add_group(h, f"part.{part['name']}")
    # outputs
    outputs = {}
    keep_objs = [body, head] + ([hair] if hair is not None else []) + list(made.values())
    outputs["parts_glb"] = os.path.join(out_dir, f"{c}_parts.glb")
    ap.export_glb(outputs["parts_glb"], keep_objs)
    joined = _join([body, head] + list(made.values()), c, col)
    outputs["rig_glb"] = os.path.join(out_dir, f"{c}_rig.glb")
    ap.export_glb(outputs["rig_glb"], [joined])
    outputs["rig_materials"] = [m.name for m in joined.data.materials]
    outputs["rig_triangles"] = len(joined.data.polygons)
    bpy.data.objects.remove(joined, do_unlink=True)
    if hair is not None:
        outputs["hair_glb"] = os.path.join(out_dir, f"{c}_hair.glb")
        ap.export_glb(outputs["hair_glb"], [hair])
    if render and ref is not None:
        try:
            outputs["hands_png"] = render_hands(ref, keep_objs, hands, H, out_dir, px)
        except Exception as exc:          # renders are evidence for a person, never a gate
            warnings.append(f"render failed: {exc}")
    outputs["parts_blend"] = os.path.join(out_dir, f"{c}_parts.blend")
    try:
        bpy.ops.file.pack_all()
    except RuntimeError as exc:
        warnings.append(f"pack_all: {exc}")
    bpy.ops.wm.save_as_mainfile(filepath=outputs["parts_blend"], copy=True)
    detail["objects"] = {o.name: {"faces": len(o.data.polygons), "materials": [m.name for m in o.data.materials]}
                         for o in keep_objs}
    ok = all(g["pass"] for g in gates)
    report = {"schema": "gate/1", "tool": "assemble_parts", "stage": "hands", "pass": ok, "ok": ok,
              "verdict": "green" if ok else "failed", **detail, "outputs": outputs,
              "seconds": round(time.time() - t_start, 1), "warnings": warnings, "gates": gates}
    path = os.path.join(out_dir, f"{c}.hands.gate.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    report["outputs"]["report"] = path
    return (0 if ok else 2), report


def _join(objs, name, col):
    import bpy
    copies = []
    for o in objs:
        k = o.copy()
        k.data = o.data.copy()
        col.objects.link(k)
        copies.append(k)
    with bpy.context.temp_override(active_object=copies[0], selected_editable_objects=copies):
        bpy.ops.object.join()
    a = copies[0]
    a.name = a.data.name = name
    for vg in list(a.vertex_groups):
        a.vertex_groups.remove(vg)
    return a


def render_hands(ref, objs, hands, H, out_dir, px=420):
    """hands.png: per hand two rows (anchor, assembly) x clay and textured, four views around the wrist."""
    import shutil
    import assemble_parts as ap
    np = _np()
    from mathutils import Vector
    scene, sh, cam = ap._studio()
    scene.render.resolution_x = scene.render.resolution_y = px
    tmp = tempfile.mkdtemp(prefix="hands_render_")
    tiles = []
    for part in hands:
        w = part["wrist"]
        sg = SIGN[part["region"]]
        rim, ax = np.asarray(w["rim"]), np.asarray(w["axis"])
        tgt = rim - ax * 0.06 * H
        target = Vector((tgt[0], -tgt[2], tgt[1]))
        dirs = {"front": Vector((0, 1, 0)), "q34": Vector((0.7 * sg, 0.7, 0)).normalized(),
                "side": Vector((-sg, 0, 0)), "wrist": Vector((0.0, 0.5, 0.86)).normalized()}
        cam.data.ortho_scale = 0.22 * H
        for shown, colour in (("anchor", 'SINGLE'), ("parts", 'SINGLE'), ("anchor", 'TEXTURE'), ("parts", 'TEXTURE')):
            ref.hide_render = shown != "anchor"
            for o in objs:
                o.hide_render = shown == "anchor"
            sh.color_type = colour
            tiles.append([ap._shoot(scene, cam, d, target, os.path.join(tmp, f"{part['name']}_{shown}_{colour}_{v}.png"))
                          for v, d in dirs.items()])
    for o in objs:
        o.hide_render = False
    ref.hide_render = True
    import bpy
    bpy.data.objects.remove(cam, do_unlink=True)
    path = ap._sheet(tiles, px, px, os.path.join(out_dir, "hands.png"))
    shutil.rmtree(tmp, ignore_errors=True)
    return path


# ------------------------------------------------------------------------------------------ selftest
def _tube(p0, a, length, r, n_az=24, n_len=24, end_tilt=0.0):
    """An open tube from p0 along a, radius r; its far end cut by a plane tilted end_tilt degrees."""
    np = _np()
    u, w = basis(a)
    th = np.linspace(0, 2 * math.pi, n_az, endpoint=False)
    rows = []
    for i in range(n_len):
        f = i / (n_len - 1)
        end = length + math.tan(math.radians(end_tilt)) * r * np.cos(th)
        t = f * end
        rows.append(p0 + np.outer(t, a) + r * (np.outer(np.cos(th), u) + np.outer(np.sin(th), w)))
    V = np.concatenate(rows)
    F = []
    for i in range(n_len - 1):
        for k in range(n_az):
            a0, b0 = i * n_az + k, i * n_az + (k + 1) % n_az
            F += [[a0, b0, b0 + n_az], [a0, b0 + n_az, a0 + n_az]]
    return V, np.array(F)


def _box(c, ax, side, up, size):
    """A closed box centred at c, edges along ax, side, up with lengths size."""
    np = _np()
    ax, side, up = unit(ax), unit(side), unit(up)
    corners = np.array([[i, j, k] for i in (-.5, .5) for j in (-.5, .5) for k in (-.5, .5)])
    V = c + (corners[:, :1] * size[0]) * ax + (corners[:, 1:2] * size[1]) * side + (corners[:, 2:] * size[2]) * up
    F = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                  [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    return V, F


def _subdiv(V, F, times):
    np = _np()
    for _ in range(times):
        e = np.sort(np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
        uniq, inv = np.unique(e, axis=0, return_inverse=True)
        inv = inv.reshape(-1)
        mids = (V[uniq[:, 0]] + V[uniq[:, 1]]) / 2
        base = len(V)
        V = np.r_[V, mids]
        m = len(F)
        ab, bc, ca = inv[:m] + base, inv[m:2 * m] + base, inv[2 * m:] + base
        F = np.r_[np.c_[F[:, 0], ab, ca], np.c_[ab, F[:, 1], bc], np.c_[ca, bc, F[:, 2]], np.c_[ab, bc, ca]]
    return V, F


def synthetic_arm_figure(fingers_apart=True, tilt=20.0):
    """A test character about 1 unit tall with both arms in an A pose: a revolved body and neck (part_math's
    synthetic figure, no hair), and per side a sleeve tube (r 0.038) whose cuff is cut tilt degrees off
    the axis, a forearm tube (r 0.019) from inside the sleeve to the wrist, a palm box and four fingers
    and a thumb (fingers_apart False: one mitten box). Returns (V, F, the true wrist per side)."""
    np = _np()
    pm = _pm()
    Vb, Fb, _ = pm.synthetic_figure(spikes=None, collar=False)
    meshes = [(Vb, Fb)]
    truth = {}
    for region, sg in SIGN.items():
        sh = np.array([sg * 0.17, 0.27, 0.0])
        a = unit([sg * 0.55, -0.83, 0.02])
        side = unit(np.cross(a, [0, 0, 1.0]))
        meshes.append(_tube(sh, a, 0.30, 0.038, end_tilt=tilt))
        fa0 = sh + a * 0.22
        meshes.append(_tube(fa0, a, 0.17, 0.019))
        wrist = fa0 + a * 0.17
        palm_c = wrist + a * 0.04
        pv, pf = _box(palm_c, a, side, [0, 0, 1.0], (0.085, 0.07, 0.026))
        meshes.append(_subdiv(pv, pf, 2))
        if fingers_apart:
            for k in range(4):
                base = palm_c + a * 0.0425 + side * (-0.0255 + 0.017 * k)
                fv, ff = _box(base + a * 0.035, a, side, [0, 0, 1.0], (0.07, 0.012, 0.014))
                meshes.append(_subdiv(fv, ff, 2))
        else:
            fv, ff = _box(palm_c + a * 0.0775, a, side, [0, 0, 1.0], (0.07, 0.068, 0.016))
            meshes.append(_subdiv(fv, ff, 2))
        tv, tf = _box(palm_c + side * 0.045 + a * 0.01, unit(a + side), side, [0, 0, 1.0], (0.045, 0.012, 0.014))
        meshes.append(_subdiv(tv, tf, 2))
        cuff_t = 0.30
        truth[region] = {"axis": a, "cuff": sh + a * cuff_t, "tilt": tilt, "r_fore": 0.019, "r_sleeve": 0.038}
    V, F = pm.merge(*meshes)
    return V, F, truth


def selftest():
    np = _np()
    pm = _pm()
    checks, failed = {}, []

    def ok(name, cond, info=None):
        checks[name] = bool(cond)
        if not cond:
            failed.append(name)
            print(f"FAIL {name}: {info}")

    V, F, truth = synthetic_arm_figure()
    Vw, Fw, _ = pm.weld(V, F)
    neck = {"band": [0.30, 0.32], "axis_xz": [0.0, 0.0], "radius": 0.033}
    anchor = {"neck": neck, "head_height": 0.17}
    H = float(Vw[:, 1].max() - Vw[:, 1].min())
    wrs = {}
    for region in HAND_REGIONS:
        try:
            wr = measure_forearm(Vw, Fw, anchor, region)
        except Refused as exc:
            ok(f"{region}: measured", False, str(exc))
            continue
        wrs[region] = wr
        tr = truth[region]
        ang = math.degrees(math.acos(min(1.0, abs(float(wr["axis"] @ tr["axis"])))))
        ok(f"{region}: axis within 4 degrees", ang < 4, ang)
        ok(f"{region}: r_fore within 15 %", abs(wr["r_fore"] / tr["r_fore"] - 1) < 0.15, wr["r_fore"])
        ok(f"{region}: r_sleeve within 15 %", abs(wr["r_sleeve"] / tr["r_sleeve"] - 1) < 0.15, wr["r_sleeve"])
        ok(f"{region}: the plane is fitted to the angled cuff", wr["plane"] == "fitted"
           and abs(wr["tilt_deg"] - tr["tilt"]) < 6, (wr["plane"], wr["tilt_deg"]))
        d_cuff = float((tr["cuff"] - wr["rim"]) @ wr["axis"])
        ok(f"{region}: the wrist plane sits at the cuff", abs(d_cuff) < 0.5 * tr["r_fore"], d_cuff)
        reg = hand_region(Vw, Fw, wr)
        cut = anchor_cut(Vw, Fw, wr)
        c = Vw[Fw].mean(1)
        q = c - truth[region]["cuff"]
        sleeve_f = np.linalg.norm(q - np.outer(q @ tr["axis"], tr["axis"]), axis=1) > 0.03
        sleeve_f &= np.abs(q @ tr["axis"]) < 0.05
        ok(f"{region}: the sleeve's lip is kept", not (cut & sleeve_f).any(), int((cut & sleeve_f).sum()))
        ok(f"{region}: the hand is in the region", reg[np.argmin(np.linalg.norm(c - wr["tip"], axis=1))]
           and (c[reg][:, 0] * SIGN[region] > 0).all())
        share, rows, fr = fingers(Vw, Fw, wr, reg)
        ok(f"{region}: four fingers counted", share >= FINGER_SHARE, (share, rows))
    Vm, Fm, _ = synthetic_arm_figure(fingers_apart=False)
    Vmw, Fmw, _ = pm.weld(Vm, Fm)
    if "hand.R" in wrs:
        wr = measure_forearm(Vmw, Fmw, anchor, "hand.R")
        share, rows, _ = fingers(Vmw, Fmw, wr, hand_region(Vmw, Fmw, wr))
        ok("a mitten fails the finger gate", share < FINGER_SHARE, (share, rows))
    # the plan: boxes (one side, shared rows, the hidden view mirrored) and keep masks
    upp = 0.0011
    frame = {"units_per_px": upp, "offset_px": {v: [512.0, 512.0] for v in VIEWS}}
    masks = {}
    for v in VIEWS:
        masks[v] = pm.silhouette(Vw, Fw, v, 1024, (upp, 512.0, 512.0))
    parts = [{"name": "hand_r", "source": "generate", "region": "hand.R", "preset": "Template"},
             {"name": "hand_l", "source": "generate", "region": "hand.L", "preset": "Template"}]
    keep = {}
    try:
        summ = plan_hands(Vw, Fw, masks, frame, anchor, parts, keep)
        p = parts[0]
        bx = p["views"]["boxes"]
        ok("plan: one side and shared rows", len({(b[1], b[3], b[2] - b[0]) for b in bx.values()}) == 1)
        ok("plan: the hidden view is the mirrored source", p["views"]["hidden"] == {"view": "left", "mirror_of": "right"}
           and np.array_equal(keep["hand_r"]["left"], keep["hand_r"]["right"][:, ::-1]))
        tc = pm.box_centre(frame, bx)
        ok("plan: the box centre lands on the hand", tc[0] < -0.2 and abs(tc[2]) < 0.03, tc.round(3).tolist())
        ok("plan: keep masks hold the hand", all(keep["hand_r"][v].sum() > 200 for v in VIEWS),
           {v: int(keep["hand_r"][v].sum()) for v in VIEWS})
        ok("plan: wrist json", set(p["wrist"]) >= {"axis", "rim", "normal", "bottom", "r_fore", "r_sleeve"} and summ)
        # registration: the anchor's own hand as the part (normalised frame, 3 degrees off) passes; 10 fails
        wr = wrs["hand.R"]
        reg = hand_region(Vw, Fw, wr)
        idx = np.unique(Fw[reg].reshape(-1))
        remap = -np.ones(len(Vw), int)
        remap[idx] = np.arange(len(idx))
        Vh, Fh = Vw[idx], remap[Fw[reg]]
        s0 = p["views"]["box_side_px"] / 1024.0
        t0 = pm.box_centre(frame, bx)
        for deg, want in ((3.0, True), (10.0, False)):
            Rz = pm._rot([0.3, 0.2, 1.0], deg)
            Vn = ((Vh - t0) / s0) @ Rz.T
            gates, det, _, _ = register(p, frame, Vw, Fw, wr, Vn, Fh)
            if want:
                gates_ok = gates
            rot = next(g for g in gates if g["name"] == "part.register.rotation_deg")
            ok(f"register: {deg} degrees off {'passes' if want else 'fails'}", rot["pass"] is want, det)
        sample = {"schema": "parts/1", "character": "courier", "tier": "fine",
                  "anchor": {"glb": "../../sources/courier_anchor.glb", "glb_sha256": "0" * 64,
                             "frame": {**frame, "iou": {v: 0.95 for v in VIEWS}}, "head_height": 0.17,
                             "neck": {**neck, "collar": False}},
                  "parts": json.loads(json.dumps(pm.TIERS["three"])) + parts}
        contract_sample("hand_parts", "plan", sample, suffix=".parts.json")
        good = all(g["pass"] for g in gates_ok)
        rep = {"schema": "gate/1", "tool": "hand_parts", "pass": good, "ok": good,
               "verdict": "green" if good else "failed", "gates": gates_ok}
        contract_sample("hand_parts", "gate", rep)
    except Refused as exc:
        ok("plan: hands measured", False, str(exc))
    # the lining block: a free cell is found away from used UVs
    uv = np.array([[[0.1, 0.1], [0.4, 0.1], [0.1, 0.4]], [[0.6, 0.6], [0.9, 0.6], [0.6, 0.9]]])
    cell = free_block(uv, 64)
    ok("lining: a free texture block", cell is not None and not (6 <= cell[0] <= 26 and 6 <= cell[1] <= 26)
       and not (38 <= cell[0] <= 58 and 38 <= cell[1] <= 58), cell)
    full = np.array([[[0, 0], [1, 0], [0, 1]], [[1, 0], [1, 1], [0, 1]]], float)
    ok("lining: no block on a full texture", free_block(full, 32) is None)
    return (0 if not failed else 1), {"selftest": "pass" if not failed else "fail", "failed": failed, "checks": checks}


def contract_sample(script, case, doc, suffix=".gate.json"):
    out = os.environ.get("UNITY_DEV_CONTRACT_OUT") or os.path.join(tempfile.gettempdir(), "unity-dev-contract-out")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{script}__{case}{suffix}")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1)
    print(f"selftest-output: {path}")


# ------------------------------------------------------------------------------------------ cli
class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1, never 2: here 2 is a gate verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser():
    p = UsageParser(prog="hand_parts.py", description=__doc__.split("\n")[0],
                    epilog="Exit codes: 0 pass, 2 a gate failed, 1 usage error or refused input.")
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd", parser_class=UsageParser)
    g = sub.add_parser("gate", help="register a generated hand onto the anchor and count its fingers (numpy)")
    g.add_argument("plan")
    g.add_argument("--part", required=True)
    g.add_argument("--glb", help="the generated hand (default: the part's generated.glb)")
    g.add_argument("--json-out")
    return p


def main():
    args = parser().parse_args(sys.argv[1:])
    if not args.selftest and args.cmd is None:
        parser().print_usage(sys.stderr)
        sys.exit(1)
    try:
        import numpy  # noqa: F401
    except ImportError:
        print(json.dumps({"tool": "hand_parts", "error": "numpy is required"}))
        sys.exit(1)
    code, res = selftest() if args.selftest else cmd_gate(args)
    print(json.dumps({"tool": "hand_parts", **res}, indent=1, default=str))
    sys.exit(code)


if __name__ == "__main__":
    main()
