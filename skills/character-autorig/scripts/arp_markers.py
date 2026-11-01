#!/usr/bin/env python3
"""arp_markers.py — joint markers for Auto-Rig Pro (and the contract skeleton) measured from the mesh.

No open 3D view: the mesh is cut into horizontal slices (the cross sections of mesh_check.py) and
every marker is read from them, or placed by a stated body proportion where the mesh shows no
feature. `--smart` adds Auto-Rig Pro's own AI result (arp_smart.py, autorig-smart/1) on top: it
checks the body, gives the fingers the slices could not part, and gives the face. Two front/side
pictures with the markers drawn on the body go to a person before any rig is built.

usage (in Blender, headless):
    blender -b scene.blend -P arp_markers.py -- --mesh Runner --out markers.json --preview-dir previews/
    blender -b -P arp_markers.py -- --import runner.glb --out markers.json --preview-dir previews/
usage (host Python, numpy only; no pictures):
    python3 arp_markers.py runner.glb [--up y|z] --out markers.json
options: [--spine-bones 3] [--fingers auto|fixed] [--adjust ADJUST.json] [--arm-angle 30,60]
         [--arm-ratios 0.42,0.75] [--no-window-gate] [--symmetry-max 0.02] [--mitten]
         [--smart NAME.smart.json] [--smart-tol 0.03] [--body human|skirt|chibi]
self-tests:
    python3 arp_markers.py --selftest                       (tube body, numpy only)
    blender -b --factory-startup -P arp_markers.py -- --selftest   (metaball runner, pictures)

The mesh must be prepared the way `blender-character-rig` -> import-and-survey.md says: +Z up,
facing -Y (its left on +X), soles on the ground, scale applied. Every height below is a fraction of
H (top minus sole) unless it says "of the way" (ankle -> hip); every position is in world metres.

How each marker is found (methods are reported per marker: measured, proportion, adjusted):
  crotch      the lowest slice above 0.2 H from which one part crosses the midline up to 0.6 H.
  hip         crotch + the leg's half-width just below it (at least 0.02 H: thick thighs meet a thigh's
              radius under the hip joints); X and Y from that leg part. Over a measured knee the thigh is
              at most THIGH_MAX (1.1) x the shin: shorts widen the leg at the crotch, and the hip is lowered.
  ankle       the lowest slice between 0.03 and 0.13 H whose leg area is within 5 % of the least
              there (where the foot's flare ends); both legs' areas summed, one height for both.
  knee        per leg, on sections across the hip -> ankle line (every 1 % of its length; girth is
              the section's hull perimeter): a kneecap bulge 40-70 % of the way up (>= 10 % over
              the shin, >= 2 % over the leg above, 1.5 x further forward than back) at its peak;
              else the narrowing between calf and thigh 35-70 % of the way up (>= 3 % narrower than
              both sides) at its lowest point; a narrowing at a hem (a girth step >= 10 % between
              neighbouring sections) is not used; else 52 % of the way (proportion). The notes
              name the cue per side.
  ball, toe_tip, heel   the foot's vertices below the ankle: the front-most point is the toe tip,
              the rearmost the heel, the ball 70 % of the way from heel to toe.
  shoulder    the arm part's centroids below the armpit lie on the arm's axis; the shoulder is that
              axis where it is SHOULDER_OUT (a quarter) of the arm's radius outside the torso's edge at the armpit
              slice (a heavy chest there reaches past the joint).
  hand_tip    the arm vertex farthest along the axis. elbow and wrist at --arm-ratios (0.42, 0.75)
              of shoulder -> hand_tip; the wrist moves to a narrowing of the arm within 0.66-0.84
              when there is one, and the elbow keeps 0.42 / 0.75 of shoulder -> wrist (so does it
              when the AI places the wrist): the forearm keeps its length wherever the wrist lands.
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
--body skirt (a long coat, a skirt, a robe): the crotch cut is the hem. Each leg is followed up from
SKIRT_FROM under it on the cut's own loops (skirt_legs); a crotch inside the skirt places the hip as
above, a hidden one places it at HIP_KNEE x the knee's height (skirt_hip); a knee cue at the hem's lip
or outside SKIRT_KNEE_BAND is refused. The report adds body and `skirt` (skirt_block), which
skirt_region turns into the skirt's own skin for the bind, deform_gate and secondary_chains.
--body chibi (a big head, a third of H or more, on short limbs; chosen at G0): its own windows
(CHIBI_WINDOWS) and these rules, the gates' limits unchanged. The crotch is searched from 0.10 H; the hip
is the crotch + the leg's half-width just under it, with no floor or cap; the ankle is the highest cut
under the shin's narrowest whose depth reaches CHIBI_FOOT_DEPTH x the shin's (where a big shoe starts); the
arm is followed down to 0.2 H and its shoulder sits where its axis crosses the torso's edge at the
armpit (a thick arm joins there, not SHOULDER_OUT of its radius outside), the wrist is a narrowing within
CHIBI_WRIST_BAND of shoulder -> hand_tip, else CHIBI_ARM_RATIOS (0.36, 0.66: a mitten a third of the arm);
the neck is the narrowest central cut from the shoulder up to CHIBI_NECK_REACH x H, and the shoulder ->
neck gap is split in thirds: neck_base at one third, head_base at two. The spine keeps the contract's
three bones, split evenly over the short torso.
`--adjust` {marker: [x, y, z]} replaces measured markers after measuring (a person moved them); the
proportion spine points follow an adjusted pelvis or neck_base (each by its share of both ends' moves).
An adjusted side marker (a .L or .R name) leaves the symmetry gate: a person placed it and its
mirror, so its measured difference is reported in asymmetry_accepted instead of gated.

`--smart FILE` (an autorig-smart/1 result in the same frame; a file whose body markers sit over
0.10 H from the slice markers on median is another mesh or frame: nothing is taken from it, smart.rejected
is true and a note says why, and the markers are the slices' alone):
  body        stays measured. Each AI body marker is paired with its slice landmark (root pelvis,
              thigh hip, knee knee, foot ankle, shoulder shoulder, elbow elbow, hand wrist, hand_tip
              hand_tip, neck neck_base, chin chin, head_tip head_top) in smart_agreement: distance
              and height difference as fractions of H, `agrees` within --smart-tol (0.03 H). A
              near miss, a landmark outside its window by at most --smart-tol x H whose AI twin
              lies inside that window (the same H and ground), passes markers.windows, the gate
              then carrying confirmed_by "auto-rig-pro-ai", the AI heights in `ai` and
              `outside_by`; the measured heights stay its value. One further out fails whatever
              the AI says. The two methods put a joint at different depths (the AI shoulder on the
              deltoid, the slice one at the armpit), so the window, not their distance, is checked.
  fingers     when the slices give `fixed` and the AI found fingers (smart.fingers and smart.go
              passed): Go!'s hand_ref, thumb1-3_ref, <f>1_base_ref and <f>1-3_ref (.l, mirrored by
              the pipeline) replace those in arp_refs; the wrist and every finger joint landmark
              follow (method "ai"), so contract_bones and hand_frames do too, and so does a
              proportion elbow (0.42 / 0.75 of shoulder -> the new wrist). A finger the AI did
              not fit (the add-on's four-finger hand has no index) keeps the fixed shape.
              fingers {mode "ai", count, names, slices {mode, reason}}. An adjusted wrist or finger
              joint keeps the person's position.
  face        when smart.facial and smart.go passed: every facial and ear reference goes into
              arp_refs, .r included (Go! projects each side of the face on its own, so its two
              sides differ by up to a few centimetres), and `facial` is true; the pipeline turns
              the face (and the ears) on before placing them.
  ref_rolls   {ref bone: roll} for every reference taken from Go!: radians, Blender's edit-bone
              roll in world axes (Go!'s rig has no rotation; a file whose rig_matrix_world rotates
              is refused). The pipeline writes these as they are (a mirrored .r twin gets the
              mirrored roll) instead of turning them with the hand.
A smart file whose run failed (no body markers, smart.go failed) is reported in `smart` and the
slice markers carry on alone; a malformed one (not autorig-smart/1, a coordinate that is not
three numbers) is refused (exit 1).

Output (schema "autorig-markers/1"): landmarks {name: [x, y, z]} (.L/.R), methods, height,
ground_z, arm_angle_deg, asymmetry_m, asymmetry_accepted, fingers {mode, reason?}, hand_frames {.L: {x, y, z}},
facial (bool), ref_rolls {ref bone: roll}, with --smart also smart {file, used, notes} and smart_agreement,
arp_refs {ref bone: {head, tail}} for the .x and .l bones of Auto-Rig Pro's human preset (the
blender-retarget brt_arp `pipeline` op mirrors .l to .r), arp_spine_count (spine bones + 1, the
add-on counts its root), contract_bones (a blender-character-rig bcr_armature spec with contract
names, .L only, mirror true, radius per bone; with --mitten the finger bones are there but do
not deform), previews {front, side}, gates [{name, value, limit, pass}] and pass, as in a gate/1
report (schemas/gate-1.json), with `ok`, pass's old name, equal to it for one release.
Bend hints: Auto-Rig Pro reads the knee and elbow direction from the reference chain, so a leg
that is straight in the mesh gets its knee 1 % of the leg length forward (-Y) and an arm its elbow
2 % back (+Y) in arp_refs and contract_bones; landmarks stay as measured.

A marker that cannot be found refuses the call (exit 1) with the reason: no crotch, no leg parts,
no foot under the ankle, no arm hanging clear of the torso. mesh_check.py names the same faults.

Gates (each failing one makes exit 2):
  markers.windows     each height inside its window: ankle 0.02-0.13, knee 0.22-0.36, hip
                      0.42-0.60, shoulder 0.72-0.88, neck 0.78-0.93. Outside means proportions
                      this route was not made for (a chibi, a giant head): take the hand-built
                      route. --no-window-gate reports without gating. With --smart, a landmark
                      out by at most --smart-tol whose AI twin is inside passes (confirmed_by).
  markers.symmetry    largest left/right difference of a marker <= --symmetry-max (0.02) x H,
                      over the markers not adjusted (see --adjust).
  markers.arm_angle   the upper arm (shoulder -> elbow) below horizontal, inside --arm-angle
                      (30-60 degrees: the contract's A-pose).
  markers.limb_ratio  per side, shoulder -> elbow over elbow -> wrist inside 0.5-2.0 and hip -> knee over
                      knee -> ankle inside THIGH_MIN (0.85)-2.0: one segment twice the other is a joint off
                      its place (an elbow moved toward the wrist), not a style; a thigh shorter than 0.85 x
                      the shin is a hip read low at a heavy body's crotch (thick thighs meet below the hip
                      joints): move it with --adjust. Adjusted markers are gated too.
  markers.finger_lengths  the shortest finger phalanx (joint to joint, every finger with landmarks)
                      >= 0.01 x wrist -> hand_tip: a chain collapsed onto its base bends nothing.
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
LIMB_RATIO = (0.5, 2.0)    # upper over lower segment of each arm and leg: neither twice the other
THIGH_MIN = 0.85           # hip -> knee over knee -> ankle: adult thighs about the shin's length (0.245 / 0.246 H);
                           # under this the hip sits low (thick thighs meet below the hip joints)
THIGH_MAX = 1.1            # the hip read from the crotch sits no higher above a measured knee than this x the shin
HIP_ABOVE_CROTCH = 0.02    # x H: the least the hip sits over the crotch (a thin leg's half-width can be less)
SHOULDER_OUT = 0.25        # x the arm's radius: the shoulder outside the torso's edge at the armpit (a heavy chest
                           # there reaches past the joint, so not half a radius out)
PHALANX_MIN = 0.01         # x wrist -> hand_tip: the shortest finger phalanx
SIDED = ("shoulder", "elbow", "wrist", "hand_tip", "hip", "knee", "ankle", "ball", "toe_tip", "heel")
ARM_MARKERS = ("shoulder", "elbow", "wrist", "hand_tip")
# --body chibi: a body 2-4.5 heads tall (the head 0.22-0.50 of H), chosen at G0, never to rescue a failed window
CHIBI_WINDOWS = {"ankle": (0.02, 0.16), "knee": (0.10, 0.30), "hip": (0.22, 0.42),
                 "shoulder": (0.45, 0.72), "neck": (0.50, 0.78)}
CHIBI_ARM_RATIOS = (0.36, 0.66)   # elbow, wrist of shoulder -> hand_tip: a mitten is a third of a short arm
CHIBI_WRIST_BAND = (0.52, 0.80)   # of shoulder -> hand_tip: a narrowing here is the wrist
CHIBI_NECK_REACH = 0.15           # x H above the shoulder: the neck's narrowest cut lies under the head
CHIBI_FOOT_DEPTH = 1.3            # the ankle: where the leg's depth reaches this x the shin's (a big shoe)
CHIBI_ARM_FROM = 0.2              # x H: short arms are followed down to here
PROP_RETRIES = 2       # arm search: vertical tracks set aside (a held prop beside the arm) before refusing


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


def chibi_ankle(prof, crotch_h) -> float:
    """--body chibi: the highest cut under the shin's narrowest (both legs' least area in 0.03-0.20 H) whose
    depth, both legs averaged, reaches CHIBI_FOOT_DEPTH x the depth there: where a big shoe starts."""
    rows = {s: {c["h"]: p for c, p in leg_rows(prof, s, crotch_h)} for s in (1, -1)}
    hs = sorted(set(rows[1]) & set(rows[-1]))
    if len(hs) < 6:
        raise Refused("no leg parts below the crotch to measure (run mesh_check first)")
    band = [h for h in hs if 0.03 <= h <= 0.20] or hs
    shin = min(band, key=lambda h: rows[1][h]["area"] + rows[-1][h]["area"])
    depth = lambda h: (float(np.ptp(rows[1][h]["y"])) + float(np.ptp(rows[-1][h]["y"]))) / 2
    under = [h for h in hs if h < shin and depth(h) >= CHIBI_FOOT_DEPTH * depth(shin)]
    return max(under) if under else shin


def ankle_height(prof, crotch_h) -> float:
    """The ankle's h from both legs together, so both sides share one height."""
    rows = {s: {c["h"]: p for c, p in leg_rows(prof, s, crotch_h)} for s in (1, -1)}
    hs = sorted(set(rows[1]) & set(rows[-1]))
    if len(hs) < 10:
        raise Refused("no leg parts below the crotch to measure (run mesh_check first)")
    area = [rows[1][h]["area"] + rows[-1][h]["area"] for h in hs]
    band = [i for i, h in enumerate(hs) if 0.03 <= h <= 0.13]
    least = min(area[i] for i in band)
    return hs[next(i for i in band if area[i] <= 1.05 * least)]   # the lowest within 5 %


# The knee is read on sections across the leg, perpendicular to the hip -> ankle line, so a slanted
# leg reads as it is and a change of H (hair, a hat) does not move it. Stations are fractions of
# that line (0 the ankle, 1 the hip).
LEG_STATIONS = np.round(np.arange(0.05, 0.805, 0.01), 3)
KNEE_BAND = (0.40, 0.70)     # a kneecap bulge's peak lies here
VALLEY_BAND = (0.35, 0.70)   # a narrowing's lowest point lies here
SWELL_MIN = 0.10             # a kneecap rises at least this much above the shin below it
DIP_MIN = 0.02               # ... and the leg narrows at least this much above it
VALLEY_MIN = 0.03            # a narrowing is at least this much narrower than both sides
HEM_JUMP = 0.10              # girth change from one station to the next that reads as a hem or a cuff
HEM_CLEAR = (0.02, 0.06)     # a narrowing up to 0.02 above or 0.06 below a hem is the hem's, not the knee
FRONT_SHARE = 1.5            # a kneecap reaches this many times further forward than back
SPAN = 0.25                  # how far either side a bulge or a narrowing is compared
KNEE_PROPORTION = 0.52       # where neither cue is found
# The skirt route (--body skirt): the legs are followed up inside the skirt on the cut's own loops.
SKIRT_GROW = 1.8             # a loop over this x the leg's area at the cut below is the skirt around it
SKIRT_FROM = 0.06            # x H under the hem the legs are first read (their parts there are apart)
SKIRT_TRACK_TOP = 0.65       # x H: the legs are followed up to here
CROTCH_MERGE = 1.25          # a loop across the midline no wider than this x both legs' span ...
CROTCH_AREA = 1.6            # ... and under this x their areas together is their crotch (a skirt is larger)
CROTCH_LAG = 0.02            # x H: the two legs end within this of each other at a crotch
TRACK_OVERLAP = 0.3          # a leg's loop overlaps its loop on the cut below at least this much (box IoU)
HIP_KNEE = 1.86              # hip height over knee height, from the sole, where the crotch is hidden (adult
                             # anthropometry: hip joint 0.530 H, knee 0.285 H); the ankle marker sits high
HIP_PROPORTION = 0.50        # x H: the hip where neither the crotch nor a knee shows
SKIRT_TOP = 0.06             # x H above the hip: the top of the skirt band the bind and the gates read
HEM_PINCH = 0.02             # x H either side of the hem: a narrowing there is the hem's lip, not a knee
SKIRT_KNEE_BAND = (0.40, 0.65)   # of the way ankle -> hip: a knee cue outside is a clothing edge (a boot top)


def _cross2(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _hull(P):
    """Convex hull (counter-clockwise) of 2D points."""
    P = np.unique(P, axis=0)
    if len(P) < 3:
        return P
    P = P[np.lexsort((P[:, 1], P[:, 0]))]

    def half(pts):
        h = []
        for p in pts:
            while len(h) >= 2 and _cross2(h[-2], h[-1], p) <= 0:
                h.pop()
            h.append(p)
        return h
    return np.array(half(P)[:-1] + half(P[::-1])[:-1])


def _inside(h, p) -> bool:
    return len(h) >= 3 and all(_cross2(h[i], h[(i + 1) % len(h)], p) >= 0 for i in range(len(h)))


def _loops(tri, z):
    """The cut of triangles (k, 3, 3, already in the leg frame) by the plane Z = z, as loops of 2D
    points: segments joined where they share a mesh edge (keys are the edges' vertex pairs)."""
    pos, keys = tri
    d = pos[:, :, 2] - z
    d = np.where(np.abs(d) < 1e-12, 1e-12, d)
    cross = (d.min(axis=1) < 0) & (d.max(axis=1) > 0)
    if not cross.any():
        return []
    p, d, k = pos[cross], d[cross], keys[cross]
    a, b = [0, 1, 2], [1, 2, 0]
    hit = (d[:, a] < 0) != (d[:, b] < 0)                  # exactly two edges per crossing triangle
    t = (d[:, a] / np.where(hit, d[:, a] - d[:, b], 1.0))[..., None]
    pts = (p[:, a, :2] + t * (p[:, b, :2] - p[:, a, :2]))[hit].reshape(-1, 2, 2)
    ek = k[hit].reshape(-1, 2)
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for e0, e1 in ek:
        parent[find(int(e0))] = find(int(e1))
    groups = {}
    for i, e0 in enumerate(ek[:, 0]):
        groups.setdefault(find(int(e0)), []).append(i)
    return [pts[idx].reshape(-1, 2) for idx in groups.values()]


def _leg_frame(hip, ankle):
    """Rows x (outward, along world X), y (toward the back) and z (ankle -> hip)."""
    z = _unit(hip - ankle)
    x = _unit(np.array([1.0, 0, 0]) - z[0] * z)
    return np.array([x, np.cross(z, x), z])


def leg_sections(V, F, hip, ankle, stations=LEG_STATIONS, cont=False):
    """Per station: {t, girth, front, back, centre (world)} of the leg's own cross section (the
    largest loop around the hip -> ankle line, its convex hull), or None where it has none.
    cont (the skirt route): a loop over SKIRT_GROW x the area the station below chose is a skirt
    around the leg, not the leg; the largest loop under it is taken, or none (a solid skirt)."""
    R = _leg_frame(hip, ankle)
    L = float(np.linalg.norm(hip - ankle))
    Vl = (V - ankle) @ R.T
    near = np.hypot(Vl[:, 0], Vl[:, 1]) < 0.6 * L
    keep = near[F].any(axis=1)
    # split normals and UV seams duplicate vertices: join edges by position, not by index
    _, weld = np.unique(np.round(V / (1e-6 * L)), axis=0, return_inverse=True)
    weld = weld.reshape(-1)
    f, fw = F[keep], weld[F[keep]]
    n = len(V)
    a, b = fw[:, [0, 1, 2]], fw[:, [1, 2, 0]]
    tri = (Vl[f], np.minimum(a, b) * n + np.maximum(a, b))
    out, last = [], None
    for t in stations:
        best = None
        for P in _loops(tri, t * L):
            h = _hull(P)
            if len(h) >= 3 and _inside(h, (0.0, 0.0)):
                area = 0.5 * abs(float(h[:, 0] @ np.roll(h[:, 1], -1) - h[:, 1] @ np.roll(h[:, 0], -1)))
                if cont and last is not None and area > SKIRT_GROW * last:
                    continue
                if best is None or area > best[0]:
                    best = (area, h)
        if best is None:
            out.append(None)
            continue
        last = best[0]
        h = best[1]
        nxt = np.roll(h, -1, axis=0)
        cr = h[:, 0] * nxt[:, 1] - nxt[:, 0] * h[:, 1]
        c = ((h + nxt) * cr[:, None]).sum(axis=0) / (3 * cr.sum()) if abs(cr.sum()) > 1e-12 else h.mean(axis=0)
        out.append({"t": float(t), "girth": float(np.linalg.norm(nxt - h, axis=1).sum()),
                    "front": float(h[:, 1].min()), "back": float(h[:, 1].max()),
                    "centre": ankle + R.T @ np.array([c[0], c[1], t * L])})
    return out


def _vertex(t, g, i, sign):
    """Sub-station position of an extremum at i (parabola through i-1, i, i+1)."""
    if 0 < i < len(g) - 1:
        den = g[i - 1] - 2 * g[i] + g[i + 1]
        if sign * den > 0:
            return float(t[i] + 0.5 * (g[i - 1] - g[i + 1]) / den * (t[i + 1] - t[i]))
    return float(t[i])


def _until(idx, g, top):
    """The leading run of idx whose girth stays at or below top (a bulge's own flank)."""
    out = []
    for j in idx:
        if g[j] > top:
            break
        out.append(j)
    return out


def knee_on_leg(V, F, hip, ankle, cont=False, avoid_z=None, band=None):
    """(t along ankle -> hip, cue) of the knee, or (None, why). Two cues, in this order:
    kneecap  a bulge rising >= SWELL_MIN above the shin below and narrowing >= DIP_MIN above it
             (not a pinch under a hem), its rise FRONT_SHARE x more in front than at the back
             (a calf swells at the back, a thigh all round): its peak.
    valley   the narrowing between the calf and the thigh, >= VALLEY_MIN narrower than both sides,
             not at a hem (a girth step >= HEM_JUMP between neighbouring stations): its lowest point.
    Where a hem cuts a side short, that side is compared only up to the hem. avoid_z (lo, hi), world z:
    a cue there is not used (the skirt route: a skirt's hem pinches the leg under its lip); band (lo, hi):
    a cue outside that share of the way is not used (the skirt route: a boot top sits under a covered knee)."""
    rows = [r for r in leg_sections(V, F, hip, ankle, cont=cont) if r is not None]
    if len(rows) < 20:
        return None, "too few leg sections along the hip -> ankle line"
    t = np.array([r["t"] for r in rows])
    g = np.array([r["girth"] for r in rows])
    front, back = np.array([r["front"] for r in rows]), np.array([r["back"] for r in rows])
    zc = np.array([r["centre"][2] for r in rows])
    clear = np.ones(len(t), bool) if avoid_z is None else (zc < avoid_z[0]) | (zc > avoid_z[1])
    if band is not None:
        clear &= (t >= band[0]) & (t <= band[1])
    jump = np.abs(np.diff(g)) / np.minimum(g[:-1], g[1:]) >= HEM_JUMP
    hems = [(t[i] + t[i + 1]) / 2 for i in np.nonzero(jump)[0]]

    def side(i, sgn):
        """Indices on one side of i within SPAN, stopping at a hem."""
        idx = []
        j = i + sgn
        while 0 <= j < len(t) and abs(t[j] - t[i]) <= SPAN:
            if jump[min(j, j - sgn)]:
                break
            idx.append(j)
            j += sgn
        return idx
    caps, valleys = [], []
    for i in range(1, len(t) - 1):
        lo_i, hi_i = side(i, -1), side(i, 1)
        if not lo_i or not hi_i:
            continue
        win = g[max(0, i - 3):i + 4]
        if KNEE_BAND[0] <= t[i] <= KNEE_BAND[1] and g[i] >= win.max() and g[i - 1] < g[i]:
            lo_c = _until(lo_i, g, g[i])
            hi_c = _until(hi_i, g, g[i])
            fl, fr = lo_c[int(np.argmin(g[lo_c]))], hi_c[int(np.argmin(g[hi_c]))]
            rise, dip = g[i] / g[fl] - 1, g[i] / g[fr] - 1
            k = (t[i] - t[fl]) / (t[fr] - t[fl])
            fe = max(0.0, front[fl] + k * (front[fr] - front[fl]) - front[i])
            be = max(0.0, back[i] - (back[fl] + k * (back[fr] - back[fl])))
            hem_dip = any(-HEM_CLEAR[0] <= h - t[fr] <= HEM_CLEAR[1] for h in hems)
            if rise >= SWELL_MIN and dip >= DIP_MIN and fe >= FRONT_SHARE * be and not hem_dip and clear[i]:
                caps.append((min(rise, dip), _vertex(t, g, i, -1)))
        if VALLEY_BAND[0] <= t[i] <= VALLEY_BAND[1] and g[i] <= win.min() and g[i - 1] > g[i]:
            depth = min(g[lo_i].max(), g[hi_i].max()) / g[i] - 1
            at_hem = any(-HEM_CLEAR[0] <= h - t[i] <= HEM_CLEAR[1] for h in hems)
            if depth >= VALLEY_MIN and not at_hem and clear[i]:
                valleys.append((depth, _vertex(t, g, i, 1)))
    if caps:
        return max(caps)[1], "kneecap"
    if valleys:
        return max(valleys)[1], "valley"
    return None, "no kneecap and no narrowing between calf and thigh" + (" (a hem there)" if hems else "")


def cut_loops(V, F):
    """A function z -> the loops of the horizontal cut there, each {x, y (box), c (centroid), r, area, hull}:
    the cut's own loops (no hole filled), so a leg inside a skirt is a loop of its own."""
    H = float(np.ptp(V[:, 2])) or 1.0
    _, weld = np.unique(np.round(V / (1e-6 * H)), axis=0, return_inverse=True)
    fw = weld.reshape(-1)[F]
    n = len(V)
    a, b = fw[:, [0, 1, 2]], fw[:, [1, 2, 0]]
    tri = (V[F], np.minimum(a, b) * n + np.maximum(a, b))

    def at(z):
        out = []
        for P in _loops(tri, z):
            if len(P) < 6:
                continue
            h = _hull(P)
            if len(h) < 3:
                continue
            area = 0.5 * abs(float(h[:, 0] @ np.roll(h[:, 1], -1) - h[:, 1] @ np.roll(h[:, 0], -1)))
            if area < (0.004 * H) ** 2:
                continue
            c = h.mean(axis=0)
            out.append({"x": (float(h[:, 0].min()), float(h[:, 0].max())), "y": (float(h[:, 1].min()), float(h[:, 1].max())),
                        "c": c, "r": float(np.linalg.norm(h - c, axis=1).max()), "area": area, "hull": h})
        return out
    return at


def _box_iou(a, b) -> float:
    ix = max(0.0, min(a["x"][1], b["x"][1]) - max(a["x"][0], b["x"][0]))
    iy = max(0.0, min(a["y"][1], b["y"][1]) - max(a["y"][0], b["y"][0]))
    inter = ix * iy
    area = lambda q: (q["x"][1] - q["x"][0]) * (q["y"][1] - q["y"][0])
    return inter / max(area(a) + area(b) - inter, 1e-12)


def skirt_legs(V, F, prof, hem_h, notes) -> dict:
    """The skirt route: each leg followed up from SKIRT_FROM under the hem on the cut's own loops (the
    largest loop on its side overlapping its loop below, under SKIRT_GROW x its area: the skirt around it
    is larger). Where both legs end within CROTCH_LAG of each other in one loop across the midline no wider than
    CROTCH_MERGE x their span and CROTCH_AREA x their areas, that is the crotch (measured). Where a leg ends otherwise (it runs into a
    solid skirt), the crotch is hidden. Returns {hem_h, crotch_h or None, legs {1, -1: [[z, x, y, r]]}, why}."""
    H, mid, z0 = prof["height"], prof["midline_x"], float(V[:, 2].min())
    at = cut_loops(V, F)
    start = hem_h - SKIRT_FROM
    tracks, live, why = {1: [], -1: []}, {1: True, -1: True}, None
    for s in (1, -1):
        rows = leg_rows(prof, s, hem_h)
        row = min(rows, key=lambda r: abs(r[0]["h"] - start)) if rows else None
        if row is None:
            return {"hem_h": hem_h, "crotch_h": None, "legs": tracks, "why": "no leg parts under the hem"}
        c = row[0]
        cand = [lp for lp in at(c["z"]) if not lp["x"][0] < mid < lp["x"][1] and s * (lp["c"][0] - mid) > 0]
        part = {"x": tuple(row[1]["x"]), "y": tuple(row[1]["y"])}
        pick = max((lp for lp in cand if _box_iou(lp, part) >= TRACK_OVERLAP), key=lambda lp: lp["area"], default=None)
        if pick is None:
            return {"hem_h": hem_h, "crotch_h": None, "legs": tracks, "why": "no leg loop under the hem"}
        tracks[s].append((c["z"], pick))
    crotch, ended_at = None, {}
    h = round(start + 0.01, 5)
    while h <= SKIRT_TRACK_TOP + 1e-9 and (live[1] or live[-1]):
        z = z0 + h * H
        loops = at(z)
        for s in (1, -1):
            if not live[s]:
                continue
            prev = tracks[s][-1][1]
            cand = [lp for lp in loops if not lp["x"][0] < mid < lp["x"][1] and s * (lp["c"][0] - mid) > 0
                    and lp["area"] <= SKIRT_GROW * prev["area"] and _box_iou(lp, prev) >= TRACK_OVERLAP]
            if cand:
                tracks[s].append((z, max(cand, key=lambda lp: lp["area"])))
            else:
                live[s], ended_at[s] = False, h
        if len(ended_at) == 1 and h - min(ended_at.values()) > CROTCH_LAG + 1e-9:
            why = f"one leg runs into the skirt at {min(ended_at.values()):.3f} H, the other goes on"
            break
        if len(ended_at) == 2:     # both ended, within CROTCH_LAG of each other: one loop holding both is the crotch
            l, r = tracks[1][-1][1], tracks[-1][-1][1]
            span = max(l["x"][1], r["x"][1]) - min(l["x"][0], r["x"][0])
            for lp in loops:
                w = lp["x"][1] - lp["x"][0]
                if lp["x"][0] < mid < lp["x"][1] and w <= CROTCH_MERGE * span and \
                        lp["area"] <= CROTCH_AREA * (l["area"] + r["area"]) and \
                        _inside(lp["hull"], l["c"]) and _inside(lp["hull"], r["c"]):
                    crotch = min(ended_at.values())
                    break
            if crotch is None:
                why = f"the legs run into the skirt at {min(ended_at.values()):.3f} H (no loop of their own and no crotch)"
            break
        h = round(h + 0.01, 5)
    if crotch is None and why is None:
        why = f"the legs are still apart at {SKIRT_TRACK_TOP} H"
    out = {s: [[float(z), float(lp["c"][0]), float(lp["c"][1]), float(lp["r"])] for z, lp in tracks[s]] for s in (1, -1)}
    tops = [round((tracks[s][-1][0] - z0) / H, 3) for s in (1, -1)]
    # the body's box per cut (skirt and torso, holes filled): the parts centred within the hem's own reach
    # of the midline (a coat's halves either side of a vent count; an arm or a hand hanging beside it not)
    reach = max((abs(x - mid) for c in prof["cuts"] if hem_h <= c["h"] <= hem_h + 0.04
                 for p in c["parts"] for x in p["x"]), default=0.0)
    torso = []
    for c in prof["cuts"]:
        if not hem_h - SKIRT_FROM <= c["h"] <= SKIRT_TRACK_TOP + 0.1:
            continue
        kept = [p for p in c["parts"] if abs(p["cx"] - mid) <= reach]
        if kept:
            torso.append([float(c["z"]), min(p["x"][0] for p in kept), max(p["x"][1] for p in kept),
                          min(p["y"][0] for p in kept), max(p["y"][1] for p in kept)])
    notes.append(f"skirt: hem at {hem_h:.3f} H; legs followed up to {tops[0]:.3f} / {tops[1]:.3f} H; "
                 + (f"crotch inside the skirt at {crotch:.3f} H" if crotch is not None else f"crotch hidden ({why})"))
    return {"hem_h": hem_h, "crotch_h": crotch, "legs": out, "torso": torso, "why": why}


def _leg_line(track, z_lo):
    """x(z), y(z) of a leg's centre line fitted on its followed loops above z_lo (the thigh side)."""
    T = np.array([t[:3] for t in track if t[0] >= z_lo] or [t[:3] for t in track])
    if len(T) < 3:
        x, y = float(T[-1][1]), float(T[-1][2])
        return lambda z: x, lambda z: y
    px, py = np.polyfit(T[:, 0], T[:, 1], 1), np.polyfit(T[:, 0], T[:, 2], 1)
    return lambda z: float(np.polyval(px, z)), lambda z: float(np.polyval(py, z))


def skirt_hip(V, F, prof, s, skirt, ankle):
    """(hip, method, knee t, knee cue) on the skirt route. A crotch inside the skirt places the hip as in
    trousers (crotch + the leg loop's radius just under it, at least 0.02 H; X and Y of that loop). A hidden one: the hip on the leg's
    centre line at HIP_KNEE x the knee's height over the sole when a knee shows (read twice, the knee again
    on the new line), else at HIP_PROPORTION x H with the knee at its proportion. A knee cue within
    HEM_PINCH of the hem is the hem's lip, and one outside SKIRT_KNEE_BAND of the way a boot top: neither
    is the knee."""
    H, z0 = prof["height"], float(V[:, 2].min())
    track = skirt["legs"][s]
    hem_z = z0 + skirt["hem_h"] * H
    avoid = (hem_z - HEM_PINCH * H, hem_z + HEM_PINCH * H)
    if skirt["crotch_h"] is not None:
        below = [t for t in track if t[0] <= z0 + (skirt["crotch_h"] - 0.02) * H] or track
        # as in trousers: thick thighs meet a thigh's radius under the hip joints (at least HIP_ABOVE_CROTCH)
        hip = np.array([below[-1][1], below[-1][2], z0 + (skirt["crotch_h"] + max(HIP_ABOVE_CROTCH, below[-1][3] / H)) * H])
        kt, cue = knee_on_leg(V, F, hip, ankle, cont=True, avoid_z=avoid, band=SKIRT_KNEE_BAND)
        return hip, "measured", kt, cue
    fx, fy = _leg_line(track, ankle[2] + 0.5 * (hem_z - ankle[2]))
    hip_z = z0 + HIP_PROPORTION * H
    kt, cue = None, None
    for _ in range(2):
        kt, cue = knee_on_leg(V, F, np.array([fx(hip_z), fy(hip_z), hip_z]), ankle, cont=True, avoid_z=avoid, band=SKIRT_KNEE_BAND)
        if kt is None:
            break
        knee_z = ankle[2] + kt * (hip_z - ankle[2])
        hip_z = z0 + HIP_KNEE * (knee_z - z0)
    hip = np.array([fx(hip_z), fy(hip_z), hip_z])
    if kt is not None:
        kt, cue = knee_on_leg(V, F, hip, ankle, cont=True, avoid_z=avoid, band=SKIRT_KNEE_BAND)
    return hip, "proportion", kt, cue


def skirt_region(V, skirt, margin=0.006):
    """The skirt's own skin (bool per vertex): rest z from SKIRT_FROM under the hem up to the band's top,
    inside the body's box at that height (the parts centred within the hem's reach of the midline, + margin
    x H: not an arm or a hand hanging beside it) and not on a leg (within its followed loop's radius + margin x H). Shared by the bind
    (autorig.py skirt_bind), deform_gate.py --skirt and secondary_chains.py --skirt."""
    V = np.asarray(V, float)
    H = float(skirt["height"])
    lo, hi = float(skirt["hem_z"]) - SKIRT_FROM * H, float(skirt["top_z"])
    band = (V[:, 2] >= lo) & (V[:, 2] <= hi)
    T = np.array(skirt.get("torso") or [], float)
    if len(T):
        z = V[band, 2]
        x0, x1, y0, y1 = (np.interp(z, T[:, 0], T[:, k]) for k in (1, 2, 3, 4))
        m = 2 * margin * H
        inside = (V[band, 0] >= x0 - m) & (V[band, 0] <= x1 + m) & (V[band, 1] >= y0 - m) & (V[band, 1] <= y1 + m)
        band[np.nonzero(band)[0][~inside]] = False
    leg = np.zeros(len(V), bool)
    for side in ("L", "R"):
        T = np.array(skirt["legs"].get(side) or [], float)
        if len(T) < 2:
            continue
        inside = band & (V[:, 2] <= T[-1, 0])
        if not inside.any():
            continue
        z = V[inside, 2]
        cx, cy, r = (np.interp(z, T[:, 0], T[:, k]) for k in (1, 2, 3))
        leg[np.nonzero(inside)[0][np.hypot(V[inside, 0] - cx, V[inside, 1] - cy) <= r + margin * H]] = True
    return band & ~leg


def measure_side(V, F, prof, s, crotch_h, ankle_h, arm_ratios, notes, skirt=None, chibi=False):
    """One side's markers (s = +1 left, -1 right) with their methods."""
    H, mid, z0 = prof["height"], prof["midline_x"], float(V[:, 2].min())
    cuts = prof["cuts"]
    out, how = {}, {}
    legs = leg_rows(prof, s, crotch_h)
    at = {c["h"]: (c, p) for c, p in legs}
    c, p = at[ankle_h]
    out["ankle"], how["ankle"] = np.array([p["cx"], p["cy"], c["z"]]), "measured"
    if skirt is None:
        # hip: X and Y of the leg just below the crotch
        below = [lp for lp in legs if lp[0]["h"] <= crotch_h - 0.02] or legs
        c, p = below[-1]
        # thick thighs meet a thigh's radius under the hip joints: the leg's half-width there (at least 0.02 H)
        half = 0.5 * float(np.ptp(p["x"])) / H
        hip_h = crotch_h + (half if chibi else max(HIP_ABOVE_CROTCH, half))
        out["hip"], how["hip"] = np.array([p["cx"], p["cy"], z0 + hip_h * H]), "measured"
        kt, cue = knee_on_leg(V, F, out["hip"], out["ankle"])
    else:
        out["hip"], how["hip"], kt, cue = skirt_hip(V, F, prof, s, skirt, out["ankle"])
    tag = "L" if s > 0 else "R"
    if kt is None:
        kt = KNEE_PROPORTION
        notes.append(f"{tag} knee: {cue}; placed at {KNEE_PROPORTION:.2f} of ankle -> hip")
        how["knee"] = "proportion"
    else:
        notes.append(f"{tag} knee: {cue} at {kt:.3f} of ankle -> hip")
        how["knee"] = "measured"
    if skirt is None:
        sec = leg_sections(V, F, out["hip"], out["ankle"], [kt])[0]
    else:   # the station's own loop, chosen up the leg (a single section would take the skirt around it)
        secs = [r for r in leg_sections(V, F, out["hip"], out["ankle"], cont=True) if r is not None]
        sec = min(secs, key=lambda r: abs(r["t"] - kt)) if secs else None
        sec = sec if sec is not None and abs(sec["t"] - kt) <= 0.02 else None
    out["knee"] = sec["centre"] if sec is not None else out["ankle"] + kt * (out["hip"] - out["ankle"])
    shin = float(out["knee"][2] - out["ankle"][2])
    if skirt is None and not chibi and how["knee"] == "measured" and out["hip"][2] - out["knee"][2] > THIGH_MAX * shin:
        # a wide hem at the crotch (shorts, a coat's lip) widened the leg: the thigh no longer than THIGH_MAX x the shin
        out["hip"] = np.array([out["hip"][0], out["hip"][1], out["knee"][2] + THIGH_MAX * shin])
        notes.append(f"{tag} hip: lowered to {THIGH_MAX:.2f} x the shin above the knee (the leg's half-width at "
                     f"the crotch put it higher)")
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
    seen = {}

    def arm_track(skip):
        runs, track, armpit = [], [], None
        for c in reversed(cuts):
            if c["h"] < (CHIBI_ARM_FROM if chibi else 0.3) or c["h"] > 0.95:
                continue
            torso = _central(c, mid)
            outside = []
            if torso is not None:
                edge = torso["x"][1] if s > 0 else torso["x"][0]
                outside = [p for p in c["parts"] if (p["x"][0] > edge if s > 0 else p["x"][1] < edge)
                           and id(p) not in skip]
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
            track.append((pick["cx"], pick["cy"], c["z"], pick["area"], id(pick)))
            seen[id(pick)] = pick
        if track:
            runs.append((track, armpit))
        return max(runs, key=lambda r: len(r[0])) if runs else ([], None)

    def axis_of(track):
        P = np.array([t[:3] for t in track])
        w = np.array([t[3] for t in track])
        centre = (P * w[:, None]).sum(0) / w.sum()
        _, _, vt = np.linalg.svd((P - centre) * np.sqrt(w)[:, None])
        d = _unit(vt[0])
        return (-d if d[2] > 0 else d), centre

    skip = set()
    for _ in range(PROP_RETRIES + 1):
        track, armpit = arm_track(skip)
        if armpit is None or len(track) < 4:
            break
        d, centre = axis_of(track)
        if abs(d[0]) >= 0.2:
            break
        # a part hanging straight down beside the arm (a held shield, a board) ran its own vertical track from
        # above the armpit: set its slices aside and follow the arm again
        notes.append(f"{'L' if s > 0 else 'R'} arm: a vertical track of {len(track)} slices from "
                     f"{track[0][2] - z0:.3f} m set aside (a held prop beside the arm?); the arm searched again")
        out.setdefault("_prop", []).extend({"z": float(t[2]), "x": list(seen[t[4]]["x"]), "y": list(seen[t[4]]["y"])}
                                           for t in track)
        skip |= {t[4] for t in track}
    if armpit is None or len(track) < 4:
        raise Refused("no arm part hangs clear of the torso (fused arms or a T-pose: run mesh_check)")
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
    # the joint SHOULDER_OUT of an arm radius outside the torso's edge; a chibi's thick arm joins at the edge itself
    t = (edge + s * (0.0 if chibi else SHOULDER_OUT) * r_arm - centre[0]) / d[0]
    shoulder = centre + t * d
    out["shoulder"], how["shoulder"] = shoulder, "measured"
    rel = V - shoulder
    along = rel @ d
    perp = np.linalg.norm(rel - np.outer(along, d), axis=1)
    arm = arm & (along > 0)
    tip_t = float(along[arm].max())
    out["hand_tip"], how["hand_tip"] = shoulder + tip_t * d, "measured"   # on the axis, as far as the arm goes
    w_r = arm_ratios[1]
    stations = np.linspace(*(CHIBI_WRIST_BAND if chibi else (0.66, 0.84)), 10)
    radius = []
    for f in stations:
        sel = arm & (np.abs(along - f * tip_t) < 0.01 * H)
        radius.append(float(np.quantile(perp[sel], 0.9)) if sel.sum() >= 4 else np.inf)
    k = _first_narrowing(radius, 1, len(radius) - 1, 0.05) if np.isfinite(radius).all() else None
    if k is None:
        out["wrist"], how["wrist"] = shoulder + w_r * tip_t * d, "proportion"
    else:
        out["wrist"], how["wrist"] = shoulder + stations[k] * tip_t * d, "measured"
    out["elbow"], how["elbow"] = elbow_from_wrist(shoulder, out["wrist"], arm_ratios), "proportion"
    out["_arm_axis"] = d
    out["_edge"] = edge
    notes.append(f"{'L' if s > 0 else 'R'} arm: {len(track)} slices below the armpit at {c_top['h']:.3f} H")
    return out, how


def elbow_from_wrist(shoulder, wrist, arm_ratios):
    """The proportion elbow, elbow/wrist ratio of the way shoulder -> wrist (0.42 / 0.75): the upper arm keeps
    its share of the arm without the hand wherever the wrist lands (a narrowing, the AI's), so the forearm
    does not shrink. On a proportion wrist it is 0.42 of the way to hand_tip."""
    shoulder = np.asarray(shoulder, dtype=float)
    return shoulder + (arm_ratios[0] / arm_ratios[1]) * (np.asarray(wrist, dtype=float) - shoulder)


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
        # q has nothing along x, so the least singular vector is x itself: the palm normal is the
        # thinner of the two axes across the hand
        across = [vt[i] - (vt[i] @ x) * x for i in (2, 1, 0)]
        z = _unit(next(c for c in across if np.linalg.norm(c) > 0.5))
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


HAND_LOOP_STATIONS = np.round(np.arange(0.40, 1.01, 0.02), 3)   # of wrist -> hand_tip
HAND_LOOP_MIN = 0.05     # x the hand's length: a loop shorter than this round is a sliver, not a finger


def hand_loops(V, F, wrist, frame, stations=HAND_LOOP_STATIONS) -> list:
    """Per station (a fraction of the hand's length), how many closed loops the mesh cuts across the hand:
    the surface itself, not samples of it, so a mitten's sample gaps cannot read as fingers."""
    x, y, z, L = frame
    R = np.array([y, z, x])
    Vh = (V - wrist) @ R.T
    near = (Vh[:, 2] > -0.1 * L) & (Vh[:, 2] < 1.1 * L) & (np.hypot(Vh[:, 0], Vh[:, 1]) < 0.6 * L)
    keep = near[F].all(axis=1)
    _, weld = np.unique(np.round(V / (1e-6 * L)), axis=0, return_inverse=True)
    weld = weld.reshape(-1)
    f, fw = F[keep], weld[F[keep]]
    n = len(V)
    a, b = fw[:, [0, 1, 2]], fw[:, [1, 2, 0]]
    tri = (Vh[f], np.minimum(a, b) * n + np.maximum(a, b))
    out = []
    for u in stations:
        loops = _loops(tri, u * L)
        out.append(sum(1 for P in loops if len(P) >= 3 and
                       float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum()) >= HAND_LOOP_MIN * L))
    return out


def measure(V, F, opts) -> dict:
    """Every marker of the body, both sides measured, compared and mirrored."""
    prof = M.profile(V, F, step=0.01, cell=0.008)
    H, mid, z0 = prof["height"], prof["midline_x"], float(V[:, 2].min())
    notes = []
    chibi = opts.get("body") == "chibi"
    crotch_h = M.crotch(prof, M.CHIBI_CROTCH_FROM) if chibi else M.crotch(prof)
    if crotch_h is None:
        raise Refused("no crotch: the legs never part (run mesh_check)")
    skirt = skirt_legs(V, F, prof, crotch_h, notes) if opts.get("body") == "skirt" else None
    sides = {}
    ankle_h = chibi_ankle(prof, crotch_h) if chibi else ankle_height(prof, crotch_h)
    ratios = opts.get("arm_ratios") or (CHIBI_ARM_RATIOS if chibi else (0.42, 0.75))
    for s in (1, -1):
        sides[s] = measure_side(V, F, prof, s, crotch_h, ankle_h, ratios, notes, skirt=skirt, chibi=chibi)
    prop = [s for s in (1, -1) if sides[s][0].get("_prop")]
    if len(prop) == 2:     # nothing to mirror from: arms down the sides (or a prop in each hand) are no arm to read
        raise Refused("both arms read vertical first (arms held against the body, or a prop in each hand): "
                      "run mesh_check; attach props after the rig")
    if len(prop) == 1:    # a held prop on one side: that arm's slices run into it; the other arm, mirrored, is the arm
        ps = prop[0]
        for name in ARM_MARKERS:
            sides[ps][0][name], sides[ps][1][name] = mirror(sides[-ps][0][name]), sides[-ps][1][name]
        notes.append(f"{'L' if ps > 0 else 'R'} arm: shoulder, elbow, wrist and hand tip mirrored from the "
                     f"{'R' if ps > 0 else 'L'} arm (a held prop on this side)")
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
    reach = (shoulder_z - z0 + CHIBI_NECK_REACH * H) if chibi else 0.95 * H
    rows = [c for c in prof["cuts"] if shoulder_z - z0 <= (c["h"] * H) <= reach and _central(c, mid)]
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
    if chibi:   # the head sits on the shoulders: the gap up to the neck's narrowest split in thirds
        base_z = shoulder_z + (2 / 3) * (neck_z - shoulder_z)
    lm["head_base"] = np.array([mid, mid_depth(base_z), base_z])
    top_part = central_at(top_z - 0.06 * H)
    lm["head_top"] = np.array([mid, (top_part["y"][0] + top_part["y"][1]) / 2 if top_part else lm["neck"][1], top_z])
    nb_z = shoulder_z + (neck_z - shoulder_z) / 3 if chibi else max(shoulder_z, neck_z - 0.03 * H)
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
    free = ".R" if prop == [1] else ".L"      # fingers are read on a hand that holds nothing
    if opts["fingers"] == "auto":
        x, y, z, L = frames[free]
        tri = V[F]
        cen = tri.mean(axis=1)
        rel = cen - lm["wrist" + free]
        along = rel @ x
        near = (along > 0) & (along < 1.1 * L) & (np.linalg.norm(rel - np.outer(along, x), axis=1) < 0.6 * L)
        if near.sum() >= 20:
            pts, _ = M.surface_samples(V, F[near], 4000)
            detected, reason = detect_fingers(pts, lm["wrist" + free], frames[free])
            if detected:    # the samples' four lanes must be four loops of the surface too (else a mitten)
                counts = hand_loops(V, F, lm["wrist" + free], frames[free])
                if sum(c >= 4 for c in counts) < 2:
                    detected = None
                    reason = (f"the samples part into four lanes but the surface never cuts into four loops "
                              f"(at most {max(counts, default=0)}): a mitten, or fingers held together")
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
                shape[f] = pts if side == free else [mirror(p) for p in pts]
        hand[side] = shape
        for f, pts in shape.items():
            for j, p in enumerate(pts):
                lm[f"{f.lower()}{j}{side}"] = p
                how[f"{f.lower()}{j}{side}"] = "measured" if (detected and f != "Thumb") else "fixed"
    out = {"height": H, "ground_z": z0, "midline_x": mid, "crotch_h": crotch_h, "landmarks": lm,
           "methods": how, "asymmetry": asym, "foot_width": foot_width, "frames": frames,
           "fingers": fingers, "notes": notes}
    if skirt is not None:
        out["crotch_h"] = skirt["crotch_h"]
        out["skirt"] = skirt
    if len(prop) == 1:
        out["prop"] = {"side": "L" if prop[0] > 0 else "R", "slices": sides[prop[0]][0]["_prop"]}
    return out


def skirt_block(m: dict, lm: dict) -> dict:
    """The markers' `skirt` (world metres): what the bind, deform_gate and secondary_chains read."""
    sk, H, z0 = m["skirt"], m["height"], m["ground_z"]
    hip_z = float(lm["hip.L"][2])
    r = lambda x: round(float(x), 5)
    legs = {}
    for s, side in ((1, "L"), (-1, "R")):
        legs[side] = [[r(z), r(x), r(y), r(rad)] for z, x, y, rad in sk["legs"][s]]
    return {"hem_h": sk["hem_h"], "hem_z": r(z0 + sk["hem_h"] * H), "crotch_h": sk["crotch_h"],
            "hip_from": "crotch inside the skirt" if sk["crotch_h"] is not None else
            ("knee" if m["methods"].get("knee.L") == "measured" else "proportion"),
            "why": sk["why"], "hip_z": r(hip_z), "top_z": r(hip_z + SKIRT_TOP * H), "height": r(H),
            "midline_x": r(m["midline_x"]), "half_width": r(abs(float(lm["hip.L"][0]) - m["midline_x"])),
            "legs": legs, "torso": [[r(x) for x in row] for row in sk["torso"]]}


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


def proportions(lm: dict) -> tuple[dict, float | None]:
    """({arm.S: upper arm / forearm, leg.S: thigh / shin}, the shortest finger phalanx over wrist -> hand_tip, or
    None without finger landmarks): a joint far off its place shows as one segment twice the other, a finger
    chain collapsed to a point as a phalanx of nothing."""
    def d(a, b):
        return float(np.linalg.norm(np.subtract(lm[a], lm[b])))
    ratios, shortest = {}, None
    for s in ("L", "R"):
        ratios[f"arm.{s}"] = round(d(f"shoulder.{s}", f"elbow.{s}") / max(d(f"elbow.{s}", f"wrist.{s}"), 1e-9), 3)
        ratios[f"leg.{s}"] = round(d(f"hip.{s}", f"knee.{s}") / max(d(f"knee.{s}", f"ankle.{s}"), 1e-9), 3)
        hand = max(d(f"wrist.{s}", f"hand_tip.{s}"), 1e-9)
        for f in FINGERS:
            joints = [f"{f.lower()}{i}.{s}" for i in range(4) if f"{f.lower()}{i}.{s}" in lm]
            for a, b in zip(joints, joints[1:]):
                r = d(a, b) / hand
                shortest = r if shortest is None else min(shortest, r)
    return ratios, (None if shortest is None else round(shortest, 4))


def gate(name, value, limit, ok):
    return {"name": name, "value": value, "limit": limit, "pass": bool(ok)}


# ------------------------------------------------------------------------------ Auto-Rig Pro's AI (--smart)

SMART_SCHEMA = "autorig-smart/1"
CONFIRMED_BY = "auto-rig-pro-ai"
# AI body marker -> the slice landmark it is compared with
SMART_PAIRS = {"root": "pelvis", "neck": "neck_base", "chin": "chin", "head_tip": "head_top",
               **{f"{a}.{s}": f"{b}.{s}" for s in ("L", "R") for a, b in
                  (("thigh", "hip"), ("knee", "knee"), ("foot", "ankle"), ("shoulder", "shoulder"),
                   ("elbow", "elbow"), ("hand", "wrist"), ("hand_tip", "hand_tip"))}}
# window landmark -> the AI marker held to the same window
SMART_WINDOW = {"ankle": "foot.L", "knee": "knee.L", "hip": "thigh.L", "shoulder": "shoulder.L", "neck": "neck"}
SMART_FRAME_MAX = 0.10      # median AI-to-slice distance (x H) beyond which the file is another mesh or frame
ARP_FINGERS = ("thumb", "index", "middle", "ring", "pinky")
CONTRACT_FINGER = dict(zip(ARP_FINGERS, FINGERS))
_BODY_REF = ("root", "spine", "neck", "head", "shoulder", "arm", "forearm", "hand", "thigh", "leg", "foot", "toes")


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _xyz(v, where: str) -> np.ndarray:
    if not (isinstance(v, (list, tuple)) and len(v) == 3 and all(_number(c) for c in v)):
        raise Refused(f"smart file: {where} is not three numbers")
    return np.array(v, dtype=float)


def _ref_group(name: str) -> str:
    if name.startswith(ARP_FINGERS):
        return "finger"
    if name.startswith("ear_"):
        return "ear"
    return "body" if name.split("_ref")[0].rstrip("0123456789_").startswith(_BODY_REF) else "facial"


def read_smart(path) -> dict:
    """An autorig-smart/1 file, checked: body markers and refs as arrays, the gates as {name: passed}."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refused(f"smart file unreadable: {exc}") from exc
    schema = data.get("schema") if isinstance(data, dict) else type(data).__name__
    if schema != SMART_SCHEMA:
        raise Refused(f"smart file: schema {schema!r}, not {SMART_SCHEMA}")
    body, refs, fingers = (data.get(k) or {} for k in ("body_markers", "refs", "fingers"))
    if not all(isinstance(x, dict) for x in (body, refs, fingers)):
        raise Refused("smart file: body_markers, refs and fingers must be objects")
    out_refs = {}
    for name, r in refs.items():
        if not isinstance(r, dict) or not _number(r.get("roll")):
            raise Refused(f"smart file: refs.{name} needs head, tail and a numeric roll")
        out_refs[name] = {"head": _xyz(r.get("head"), f"refs.{name}.head"),
                          "tail": _xyz(r.get("tail"), f"refs.{name}.tail"), "roll": float(r["roll"]),
                          "group": r.get("group") if r.get("group") in ("body", "finger", "facial", "ear")
                          else _ref_group(name)}
    if out_refs:
        mw = data.get("rig_matrix_world")
        if not (isinstance(mw, list) and len(mw) == 4 and all(isinstance(row, list) and len(row) == 4 and
                                                              all(_number(c) for c in row) for row in mw)):
            raise Refused("smart file: refs without a 4x4 rig_matrix_world to check their rolls against")
        m3 = np.array(mw, dtype=float)[:3, :3]
        scale = np.linalg.norm(m3, axis=0)
        if scale.min() < 1e-9 or not np.allclose(m3 / scale, np.eye(3), atol=1e-4):
            raise Refused("smart file: Go!'s rig object is rotated, so its rolls are not in world axes")
    gates = {g.get("name"): g.get("pass") is True for g in data.get("gates") or [] if isinstance(g, dict)}
    count = fingers.get("count")
    return {"body": {k: _xyz(v, f"body_markers.{k}") for k, v in body.items()}, "refs": out_refs,
            "gates": gates, "count": int(count) if _number(count) else 0,
            "names": [n for n in fingers.get("names") or [] if n in ARP_FINGERS], "pass": data.get("pass") is True}


def smart_agreement(lm: dict, H: float, z0: float, smart: dict, tol: float) -> dict:
    """Per slice landmark with an AI twin: distance and height difference in H, both heights."""
    rows = {}
    for ai, name in SMART_PAIRS.items():
        if ai in smart["body"] and name in lm:
            a, b = smart["body"][ai], np.asarray(lm[name], dtype=float)
            d = float(np.linalg.norm(a - b)) / H
            rows[name] = {"ai": ai, "distance_h": round(d, 4), "dz_h": round(float(a[2] - b[2]) / H, 4),
                          "ai_h": round(float(a[2] - z0) / H, 4), "slice_h": round(float(b[2] - z0) / H, 4),
                          "agrees": d <= tol}
    return rows


def _merge_fingers(V, m: dict, smart: dict, adjusted: set, arm_ratios=(0.42, 0.75)) -> tuple[dict, str | None]:
    """Go!'s hand and finger references onto the landmarks; {ref: smart ref} taken, or a reason. A proportion
    elbow follows the AI's wrist (elbow_from_wrist)."""
    refs, lm, how = smart["refs"], m["landmarks"], m["methods"]
    present = [f for f in ARP_FINGERS if all(f"{f}{j}_ref.l" in refs for j in (1, 2, 3))
               and (f == "thumb" or f"{f}1_base_ref.l" in refs)]
    if "thumb" not in present or "hand_ref.l" not in refs:
        return {}, "Go! placed no thumb or hand reference"
    take = {}
    if not {"wrist.L", "wrist.R"} & adjusted:
        w = refs["hand_ref.l"]["head"]
        lm["wrist.L"], lm["wrist.R"] = w.copy(), mirror(w)
        how["wrist.L"] = how["wrist.R"] = "ai"
        take["hand_ref.l"] = refs["hand_ref.l"]
        if how.get("elbow.L") == "proportion" and not {"elbow.L", "elbow.R"} & adjusted:
            e = elbow_from_wrist(lm["shoulder.L"], w, arm_ratios)
            lm["elbow.L"], lm["elbow.R"] = e, mirror(e)
    for s, side in ((1, ".L"), (-1, ".R")):
        m["frames"][side] = hand_frame(V, lm["wrist" + side], lm["hand_tip" + side], s)
    for s, side in ((1, ".L"), (-1, ".R")):     # the fingers the AI does not give: the fixed shape again
        for f, pts in fixed_hand(lm["wrist" + side], m["frames"][side]).items():
            if f.lower() in (CONTRACT_FINGER[a].lower() for a in present):
                continue
            for j, p in enumerate(pts):
                if f"{f.lower()}{j}{side}" not in adjusted:
                    lm[f"{f.lower()}{j}{side}"] = p
    for a in present:
        low = CONTRACT_FINGER[a].lower()
        if any(f"{low}{j}{side}" in adjusted for j in range(4) for side in (".L", ".R")):
            continue
        r1, r2, r3 = (refs[f"{a}{j}_ref.l"] for j in (1, 2, 3))
        for j, p in enumerate((r1["head"], r1["tail"], r2["tail"], r3["tail"])):
            lm[f"{low}{j}.L"], lm[f"{low}{j}.R"] = p.copy(), mirror(p)
            how[f"{low}{j}.L"] = how[f"{low}{j}.R"] = "ai"
        for j in (1, 2, 3):
            take[f"{a}{j}_ref.l"] = refs[f"{a}{j}_ref.l"]
        if a != "thumb":
            take[f"{a}1_base_ref.l"] = refs[f"{a}1_base_ref.l"]
    return take, None


def merge_smart(V, m: dict, smart: dict, opts: dict, adjusted: set) -> tuple[dict, dict]:
    """(the Go! references taken {name: ref}, the `smart` record). Body markers are only compared."""
    H, z0, g = m["height"], m["ground_z"], smart["gates"]
    rows = smart_agreement(m["landmarks"], H, z0, smart, opts.get("smart_tol", 0.03))
    record = {"file": str(opts.get("smart_file")), "pass": smart["pass"], "gates": g, "agreement": rows,
              "used": {"window": False, "fingers": False, "facial": False}, "notes": []}
    median = float(np.median([r["distance_h"] for r in rows.values()])) if rows else 0.0
    if median > SMART_FRAME_MAX:          # another mesh or frame: nothing taken, the slices alone
        record["rejected"] = True
        record["notes"].append(f"its body markers sit {median:.3f} H from the slice markers on median (over "
                               f"{SMART_FRAME_MAX} H): another mesh, or another frame; nothing taken")
        return {}, record
    take = {}
    go = g.get("smart.go") is True and bool(smart["refs"])
    if not rows:
        record["notes"].append("no AI body markers: the window gate is the slices' alone")
    if not go:
        record["notes"].append("smart.go did not pass: no references taken from Go!")
    elif m["fingers"]["mode"] != "fixed":
        record["notes"].append(f"the slices found the fingers ({m['fingers']['mode']}): kept")
    elif g.get("smart.fingers") is not True or smart["count"] < 1:
        record["notes"].append("smart.fingers did not pass: the fixed hand stays")
    else:
        got, why = _merge_fingers(V, m, smart, adjusted, opts.get("arm_ratios") or (
            CHIBI_ARM_RATIOS if opts.get("body") == "chibi" else (0.42, 0.75)))
        if why:
            record["notes"].append(why + ": the fixed hand stays")
        else:
            take.update(got)
            names = [a for a in ARP_FINGERS if f"{a}1_ref.l" in got]
            m["fingers"] = {"mode": "ai", "count": smart["count"], "names": names, "slices": m["fingers"]}
            record["used"]["fingers"] = True
            if len(names) < len(FINGERS):
                record["notes"].append(f"the AI fitted {names}: the other fingers keep the fixed shape")
    if go and g.get("smart.facial") is True:
        face = {n: r for n, r in smart["refs"].items() if r["group"] in ("facial", "ear")}
        if face:
            take.update(face)
            record["used"]["facial"] = True
    elif go and "smart.facial" in g:
        record["notes"].append("smart.facial did not pass: no face")
    return take, record


def respine(lm: dict, how: dict, ends: dict, spine_bones: int) -> None:
    """A proportion spine point follows an adjusted pelvis or neck_base: each moves by its share of both ends'
    moves (spine i of n by (1 - i/n) of the pelvis's and i/n of neck_base's), so the spine stays between them
    and root_ref keeps pointing up. An adjusted spine point stays where the person put it."""
    n = spine_bones + 1
    dp, dn = lm["pelvis"] - ends["pelvis"], lm["neck_base"] - ends["neck_base"]
    for i in range(1, n):
        k = f"spine{i}"
        if how.get(k) == "proportion":
            lm[k] = lm[k] + dp * (1 - i / n) + dn * (i / n)


def build_report(V, F, opts) -> dict:
    m = measure(V, F, opts)
    lm, H, z0 = m["landmarks"], m["height"], m["ground_z"]
    smart = opts.get("smart")
    ends = {k: lm[k].copy() for k in ("pelvis", "neck_base")}
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
    respine(lm, m["methods"], ends, opts["spine_bones"])
    taken, record = ({}, None) if smart is None else \
        merge_smart(V, m, smart, opts, {n for n in (opts.get("adjust") or {})})
    upper = lm["elbow.L"] - lm["shoulder.L"]
    arm_angle = math.degrees(math.atan2(-upper[2], math.hypot(upper[0], upper[1])))
    samples, _ = M.surface_samples(V, F, 20000)
    refs = arp_refs(m, opts["spine_bones"])
    for name, ref in taken.items():
        refs[name] = {"head": ref["head"], "tail": ref["tail"]}
    rolls = {name: round(float(ref["roll"]), 5) for name, ref in sorted(taken.items())}
    spec = contract_bones(m, opts["spine_bones"], samples, mitten=opts.get("mitten", False))
    out_window, ai_window, outside_by = {}, {}, {}
    wins = CHIBI_WINDOWS if opts.get("body") == "chibi" else WINDOWS
    for name, (lo, hi) in wins.items():
        h = (float(lm[name + ".L"][2] if name + ".L" in lm else lm[name][2]) - z0) / H
        if not lo <= h <= hi:
            out_window[name] = round(h, 3)
            outside_by[name] = round(max(lo - h, h - hi), 4)
            twin = smart["body"].get(SMART_WINDOW[name]) if smart and not record.get("rejected") else None
            if twin is not None:
                ai_window[name] = round(float(twin[2] - z0) / H, 3)
    # the AI confirms a near miss only: each landmark out by at most --smart-tol, its AI twin inside
    near = opts.get("smart_tol", 0.03)
    confirmed = bool(out_window) and all(n in ai_window and wins[n][0] <= ai_window[n] <= wins[n][1]
                                         and outside_by[n] <= near for n in out_window)
    adjusted = {n[:-2] for n in (opts.get("adjust") or {}) if n.endswith((".L", ".R"))}
    accepted = {k: v for k, v in m["asymmetry"].items() if k in adjusted}
    asym = max((v for k, v in m["asymmetry"].items() if k not in adjusted), default=0.0)
    a_lo, a_hi = opts["arm_angle"]
    windows = gate("markers.windows", out_window, {k: list(v) for k, v in wins.items()},
                   not out_window or opts["no_window_gate"] or confirmed)
    if ai_window:
        windows.update(ai=ai_window, outside_by=outside_by, near_miss_max=near)
    if confirmed:
        windows["confirmed_by"] = CONFIRMED_BY
        if record is not None:
            record["used"]["window"] = True
    gates = [windows,
             gate("markers.symmetry", round(asym, 4), round(opts["symmetry_max"] * H, 4),
                  asym <= opts["symmetry_max"] * H),
             gate("markers.arm_angle", round(arm_angle, 2), [a_lo, a_hi], a_lo <= arm_angle <= a_hi)]
    ratios, phalanx = proportions(lm)
    lim = {"arm": list(LIMB_RATIO), "leg": [THIGH_MIN, LIMB_RATIO[1]]}
    gates += [gate("markers.limb_ratio", ratios, lim,
                   all(lim[k.split(".")[0]][0] <= v <= lim[k.split(".")[0]][1] for k, v in ratios.items())),
              gate("markers.finger_lengths", phalanx, PHALANX_MIN, phalanx is None or phalanx >= PHALANX_MIN)]

    def r(p):
        return [round(float(x), 5) for x in p]
    report = {
        "schema": "autorig-markers/1", "tool": "arp_markers", "space": "world", "up": "+Z", "forward": "-Y",
        "height": round(H, 5), "ground_z": round(z0, 5), "midline_x": round(m["midline_x"], 5),
        "body": opts.get("body", "human"), "crotch_h": m["crotch_h"], "arm_angle_deg": round(arm_angle, 2),
        "landmarks": {k: r(v) for k, v in lm.items()}, "methods": m["methods"],
        "asymmetry_m": {k: round(v, 4) for k, v in m["asymmetry"].items()},
        "asymmetry_accepted": {k: round(v, 4) for k, v in accepted.items()},
        "fingers": m["fingers"],
        "hand_frames": {side: {"x": r(f[0]), "y": r(f[1]), "z": r(f[2]), "length": round(f[3], 5)}
                        for side, f in m["frames"].items()},
        "arp_spine_count": opts["spine_bones"] + 1,
        "arp_refs": {k: {"head": r(v["head"]), "tail": r(v["tail"])} for k, v in refs.items()},
        "ref_rolls": rolls, "facial": bool(record and record["used"]["facial"]),
        "contract_bones": {"mirror": True, "bones": spec},
        "notes": m["notes"], "gates": gates, "pass": all(g["pass"] is True for g in gates),
        "ok": all(g["pass"] is True for g in gates),
    }
    if "skirt" in m:
        report["skirt"] = skirt_block(m, lm)
    if "prop" in m:     # the held prop's slices (world metres): autorig's hand_reach keeps them on the hand, rigid
        report["prop"] = {"side": m["prop"]["side"], "step": round(0.01 * H, 5), "slices": [
            {"z": round(p["z"], 5), "x": r(p["x"]), "y": r(p["y"])} for p in m["prop"]["slices"]]}
    if record is not None:
        report["smart_agreement"] = {"tolerance_h": opts.get("smart_tol", 0.03), "landmarks": record.pop("agreement")}
        report["smart"] = record
    return report


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
    p.add_argument("--arm-ratios", type=_pair, default=None, help="elbow, wrist of shoulder -> hand_tip "
                   "(default 0.42,0.75; 0.36,0.66 with --body chibi)")
    p.add_argument("--symmetry-max", type=float, default=0.02)
    p.add_argument("--no-window-gate", action="store_true")
    p.add_argument("--mitten", action="store_true", help="contract_bones: finger bones do not deform")
    p.add_argument("--body", choices=("human", "skirt", "chibi"), default="human",
                   help="skirt: a long coat, skirt or robe; the legs are followed up under and inside it. "
                        "chibi: a big head on short limbs, with its own windows (CHIBI_WINDOWS)")
    p.add_argument("--smart", help="an arp_smart.py result (autorig-smart/1) to check and complete the markers")
    p.add_argument("--smart-tol", type=float, default=0.03, help="x H: smart_agreement's agrees, and how far out of its window the AI may confirm a landmark")
    p.add_argument("--selftest", action="store_true")
    return p


def _opts(args) -> dict:
    adjust = None
    if args.adjust:
        adjust = json.loads(Path(args.adjust).read_text(encoding="utf-8"))
    return {"spine_bones": args.spine_bones, "fingers": args.fingers, "adjust": adjust,
            "arm_angle": args.arm_angle, "arm_ratios": args.arm_ratios,
            "symmetry_max": args.symmetry_max, "no_window_gate": args.no_window_gate,
            "mitten": args.mitten, "body": args.body, "smart": read_smart(args.smart) if args.smart else None,
            "smart_file": args.smart, "smart_tol": args.smart_tol}


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
        report["pass"] = report["ok"] = all(g["pass"] is True for g in report["gates"])
    return (0 if report["pass"] is True else 2), report


def run_host(args) -> tuple[int, dict]:
    if args.file is None:
        return 1, {"tool": "arp_markers", "error": "a mesh file is required outside Blender"}
    try:
        V, F = M.load_mesh(args.file, args.up)
        report = build_report(V, F, _opts(args))
    except (OSError, ValueError, KeyError, M.Refused, Refused) as exc:
        return 1, {"tool": "arp_markers", "error": str(exc)}
    report["mesh"] = str(args.file)
    return (0 if report["pass"] is True else 2), report


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


def _smart_doc(rep: dict, shoulder_z=None, go=True, facial=True, shift=0.0, four=False) -> dict:
    """A synthetic autorig-smart/1 result built on a markers report: the AI markers 1 cm above the
    slice ones, Go!'s finger references a hand of its own, three facial references and an ear."""
    lm = rep["landmarks"]
    body = {ai: [lm[sl][0] + shift, lm[sl][1], lm[sl][2] + 0.01] for ai, sl in SMART_PAIRS.items()}
    if shoulder_z is not None:
        for side in ("L", "R"):
            body[f"shoulder.{side}"][2] = shoulder_z
    w = np.array(lm["wrist.L"]) + [0.0, 0.0, 0.02]
    x = _unit(np.array(lm["hand_tip.L"]) - w)
    y = _unit(np.cross(x, [0.0, 1.0, 0.0]))
    refs = {"root_ref.x": ([0, 0, 0.9], [0, 0, 1.0], 0.0), "hand_ref.l": (w, w + 0.06 * x, 0.61)}
    for k, (a, lane) in enumerate((("thumb", -0.03), ("index", -0.015), ("middle", 0.0), ("ring", 0.015),
                                   ("pinky", 0.03))):
        base = w + 0.07 * x + lane * y
        if a != "thumb":
            refs[f"{a}1_base_ref.l"] = (w + 0.01 * x + lane * y, base, 0.4)
        for j in (1, 2, 3):
            refs[f"{a}{j}_ref.l"] = (base + 0.025 * (j - 1) * x, base + 0.025 * j * x, -2.9 if a == "thumb" else 0.9 + k)
    head = np.array(lm["head_top"])
    refs["jaw_ref.x"] = (head - [0, 0.0, 0.2], head - [0, 0.06, 0.25], 0.0)
    refs["eyelid_top_ref.l"] = (head + [0.04, -0.07, -0.12], head + [0.04, -0.12, -0.11], 3.14159)
    refs["eyelid_top_ref.r"] = (head + [-0.04, -0.07, -0.12], head + [-0.04, -0.12, -0.11], -3.14159)
    refs["ear_01_ref.l"] = (head + [0.08, 0, -0.15], head + [0.1, 0, -0.12], 1.0)
    if four:                    # the add-on's four-finger hand: thumb, middle, ring, pinky
        refs = {n: v for n, v in refs.items() if not n.startswith("index")}
    def num(v):
        return [round(float(c), 5) for c in v]
    gates = [{"name": "smart.fingers", "value": 5, "pass": True}, {"name": "smart.go", "value": go, "pass": go},
             {"name": "smart.facial", "value": 48, "pass": facial}]
    return {"schema": SMART_SCHEMA, "tool": "arp_smart", "height": rep["height"],
            "body_markers": {k: num(v) for k, v in body.items()},
            "fingers": {"count": 4 if four else 5, "names": [f for f in ARP_FINGERS if not (four and f == "index")]},
            "rig_matrix_world": [[0.95, 0, 0, 0], [0, 0.95, 0, 0], [0, 0, 0.95, 0], [0, 0, 0, 1]],
            "refs": {n: {"head": num(h), "tail": num(t), "roll": r, "group": _ref_group(n)} for n, (h, t, r) in refs.items()},
            "gates": gates, "pass": go and facial}


def selftest_smart(ok, v, f, opts, rep) -> None:
    """--smart: the window confirmed or not, the fingers and the face merged, bad files refused."""
    def win(r):
        return next(g for g in r["gates"] if g["name"] == "markers.windows")
    sh, H, z0 = rep["landmarks"]["shoulder.L"], rep["height"], rep["ground_z"]
    near_z = z0 + (WINDOWS["shoulder"][0] - 0.014) * H          # 0.014 H below the window: a near miss
    low = dict(opts, adjust={"shoulder.L": [sh[0], sh[1], near_z]})
    good = read_smart_doc(_smart_doc(rep))
    r1 = build_report(v, f, dict(low, smart=good, smart_file="s.json"))
    ok("smart: shoulder 0.014 H out of window, the AI's inside -> passes, confirmed_by",
       win(r1)["pass"] and win(r1).get("confirmed_by") == CONFIRMED_BY and win(r1)["value"].get("shoulder")
       and r1["smart"]["used"]["window"] and win(r1)["outside_by"]["shoulder"] <= 0.03)
    far = build_report(v, f, dict(opts, adjust={"shoulder.L": [sh[0], sh[1], z0 + 0.588 * H]}, smart=good))
    ok("smart: shoulder 0.13 H out of window, the AI's inside -> still fails (a near miss only)",
       not win(far)["pass"] and "confirmed_by" not in win(far) and not far["smart"]["used"]["window"]
       and win(far)["ai"]["shoulder"] > WINDOWS["shoulder"][0])
    tight = build_report(v, f, dict(low, smart=good, smart_tol=0.01))
    ok("smart: --smart-tol 0.01 makes the 0.014 H miss fail", not win(tight)["pass"])
    ok("smart: agreement per landmark, 1 cm apart agrees",
       r1["smart_agreement"]["landmarks"]["hip.L"]["agrees"] and r1["smart_agreement"]["landmarks"]["hip.L"]["ai"] == "thigh.L")
    bad_sh = read_smart_doc(_smart_doc(rep, shoulder_z=1.0))
    r2 = build_report(v, f, dict(low, smart=bad_sh))
    ok("smart: the AI's shoulder out of window too -> fails, no confirmed_by",
       not win(r2)["pass"] and "confirmed_by" not in win(r2) and not r2["pass"])
    ok("smart: fingers fixed -> Go!'s fingers, mode ai, count 5", r1["fingers"]["mode"] == "ai"
       and r1["fingers"]["count"] == 5 and r1["fingers"]["slices"]["mode"] == "fixed")
    doc = _smart_doc(rep)
    ref = doc["refs"]["index1_ref.l"]
    ok("smart: index1_ref.l, base and thumb from Go!, rolls in ref_rolls",
       r1["arp_refs"]["index1_ref.l"]["head"] == ref["head"] and "index1_base_ref.l" in r1["ref_rolls"]
       and r1["ref_rolls"]["thumb1_ref.l"] == -2.9 and r1["ref_rolls"]["hand_ref.l"] == 0.61)
    lm1 = r1["landmarks"]
    ok("smart: finger landmarks and the wrist follow, .R mirrored, method ai",
       lm1["index0.L"] == ref["head"] and lm1["index0.R"] == [-ref["head"][0], ref["head"][1], ref["head"][2]]
       and r1["methods"]["wrist.L"] == "ai" and lm1["wrist.L"] == doc["refs"]["hand_ref.l"]["head"])
    sh1, wr1 = np.array(lm1["shoulder.L"]), np.array(lm1["wrist.L"])
    ok("smart: the proportion elbow follows the AI wrist (0.42 / 0.75 of shoulder -> wrist), .R mirrored",
       np.allclose(lm1["elbow.L"], sh1 + 0.56 * (wr1 - sh1), atol=1e-4) and r1["methods"]["elbow.L"] == "proportion"
       and np.allclose(lm1["elbow.R"], [-lm1["elbow.L"][0], lm1["elbow.L"][1], lm1["elbow.L"][2]], atol=1e-6)
       and not np.allclose(lm1["elbow.L"], rep["landmarks"]["elbow.L"], atol=1e-4))
    spec = {b["name"]: b for b in r1["contract_bones"]["bones"]}
    ok("smart: contract Index1.L on Go!'s index", spec["Index1.L"]["head"] == ref["head"])
    ok("smart: facial refs carried, both sides as Go! put them, ear too, facial true",
       r1["facial"] is True and {"jaw_ref.x", "eyelid_top_ref.l", "eyelid_top_ref.r", "ear_01_ref.l"} <= set(r1["arp_refs"])
       and r1["ref_rolls"]["eyelid_top_ref.r"] == -3.14159 and "thumb1_ref.r" not in r1["arp_refs"])
    ok("smart: Go!'s body refs not taken (body stays measured)",
       r1["arp_refs"]["root_ref.x"]["head"] == rep["arp_refs"]["root_ref.x"]["head"] and "root_ref.x" not in r1["ref_rolls"])
    r3 = build_report(v, f, dict(opts, smart=read_smart_doc(_smart_doc(rep, facial=False))))
    ok("smart: smart.facial failed -> no face, fingers still taken",
       r3["facial"] is False and "jaw_ref.x" not in r3["arp_refs"] and r3["fingers"]["mode"] == "ai")
    r4 = build_report(v, f, dict(opts, smart=read_smart_doc(_smart_doc(rep, go=False, facial=False))))
    ok("smart: Go! failed -> slices alone, noted, exit 0 verdict",
       r4["fingers"]["mode"] == "fixed" and not r4["ref_rolls"] and r4["pass"] and r4["smart"]["notes"])
    r5 = build_report(v, f, dict(opts, smart=read_smart_doc(_smart_doc(rep, four=True))))
    ok("smart: four fingers -> no index from Go!, the index keeps the fixed shape, noted",
       r5["fingers"]["mode"] == "ai" and r5["fingers"]["names"] == ["thumb", "middle", "ring", "pinky"]
       and r5["methods"]["index0.L"] == "fixed" and r5["methods"]["middle0.L"] == "ai"
       and "index1_ref.l" not in r5["ref_rolls"] and any("fixed shape" in n for n in r5["smart"]["notes"]))
    ok("no smart: facial false, ref_rolls empty", rep["facial"] is False and rep["ref_rolls"] == {}
       and "smart" not in rep)
    r6 = build_report(v, f, dict(opts, smart=read_smart_doc(_smart_doc(rep, shift=0.4))))
    ok("smart: markers 0.4 m off -> nothing taken (another frame), noted, the slices alone",
       r6["smart"].get("rejected") is True and not any(r6["smart"]["used"].values())
       and r6["fingers"]["mode"] == rep["fingers"]["mode"] and r6["facial"] is False and not r6["ref_rolls"]
       and "confirmed_by" not in r6["gates"][0] and any("another frame" in n for n in r6["smart"]["notes"]))
    malformed = []
    d = _smart_doc(rep)
    d["schema"] = "autorig-smart/0"
    malformed.append(d)
    d = _smart_doc(rep)
    d["refs"]["jaw_ref.x"]["head"] = [0, 1]
    malformed.append(d)
    d = _smart_doc(rep)
    d["refs"]["jaw_ref.x"]["roll"] = "flat"
    malformed.append(d)
    d = _smart_doc(rep)
    d["rig_matrix_world"] = [[0, -1, 0, 0], [1, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    malformed.append(d)
    with tempfile.TemporaryDirectory() as tmp:
        body = Path(tmp) / "body.obj"
        M.write_obj(body, v, f)
        codes = []
        for i, doc in enumerate(malformed + ["not json"]):
            path = Path(tmp) / f"bad{i}.json"
            path.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")
            codes.append(run_host(parser().parse_args([str(body), "--smart", str(path)]))[0])
        ok("cli --smart: schema, coordinate, roll, rotated rig, not JSON -> exit 1 each", codes == [1] * 5)
        path, adj = Path(tmp) / "good.json", Path(tmp) / "adj.json"
        path.write_text(json.dumps(_smart_doc(rep)), encoding="utf-8")
        adj.write_text(json.dumps({"shoulder.L": [sh[0], sh[1], near_z]}), encoding="utf-8")
        code, rr = run_host(parser().parse_args([str(body), "--smart", str(path), "--adjust", str(adj)]))
        failed_gates = [g["name"] for g in rr.get("gates", []) if not g["pass"]]
        ok("cli --smart: the near-miss shoulder confirmed (only the arm angle it bends fails)",
           code == 2 and failed_gates == ["markers.arm_angle"] and rr["smart"]["used"]["window"])
        code, rr = run_host(parser().parse_args([str(body), "--smart", str(path), "--adjust", str(adj),
                                                 "--smart-tol", "0.01"]))
        ok("cli --smart-tol 0.01: the same shoulder fails markers.windows",
           code == 2 and not rr["gates"][0]["pass"] and not rr["smart"]["used"]["window"])
        code, rr = run_host(parser().parse_args([str(body), "--smart", str(path)]))
        ok("cli --smart: exit 0, fingers ai, facial", code == 0 and rr["fingers"]["mode"] == "ai" and rr["facial"])


def read_smart_doc(doc: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "smart.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return read_smart(path)


def _lathe(x, knots, n=24):
    """A closed vertical leg at X = x: knots [(z, outer, front, back)] give the half-width across
    (X) and the reach in front (-Y) and behind (+Y), joined linearly; a ring every 5 mm."""
    k = np.array(knots, float)
    zs = np.arange(k[0, 0], k[-1, 0] + 1e-9, 0.005)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    rings = []
    for z in zs:
        rx, rf, rb = (np.interp(z, k[:, 0], k[:, i]) for i in (1, 2, 3))
        sy = np.sin(ang)
        rings.append(np.c_[x + rx * np.cos(ang), np.where(sy < 0, rf, rb) * sy, np.full(n, z)])
    v = np.vstack(rings + [np.array([[x, 0, zs[0]], [x, 0, zs[-1]]])])
    faces, m = [], len(zs)
    for i in range(m - 1):
        for j in range(n):
            p, q = i * n + j, i * n + (j + 1) % n
            faces += [[p, q, q + n], [p, q + n, p + n]]
    for j in range(n):
        faces += [[m * n, (j + 1) % n, j], [m * n + 1, (m - 1) * n + j, (m - 1) * n + (j + 1) % n]]
    return v, np.array(faces)


def _leg_body(knots, hat=0.0):
    """The tube body (mesh_check.body) with both legs replaced by _lathe legs; `hat` raises the top."""
    s45 = math.sqrt(0.5)
    parts = [((0, 0, 0.86), (0, 0, 1.42), dict(r=0.15, rx=0.15, ry=0.10)),
             ((0, 0, 1.40), (0, 0, 1.52), dict(r=0.05)),
             ((0, -0.01, 1.50), (0, -0.01, 1.70 + hat), dict(r=0.10))]
    for side in (1, -1):
        a = np.array([side * 0.17, 0, 1.38])
        parts.append((a, a + 0.62 * np.array([side * s45, 0, -s45]), dict(r=0.045)))
        parts.append(((side * 0.11, 0.05, 0.04), (side * 0.11, -0.14, 0.04), dict(r=0.04)))
    pieces = [M.tube(a, b, **kw) for a, b, kw in parts]
    pieces += [_lathe(side * 0.11, knots) for side in (1, -1)]
    return M.assemble(pieces)


# legs, z then half-width, front, back (m): a calf swelling at the back, the knee's narrowing at
# 0.48, a thigh, and shorts whose hem (a step at 0.60) has a pinch just under it narrower still
CALF_HEM = [(0.05, 0.035, 0.035, 0.035), (0.12, 0.034, 0.034, 0.034), (0.33, 0.050, 0.042, 0.068),
            (0.48, 0.042, 0.040, 0.042), (0.56, 0.052, 0.050, 0.052), (0.585, 0.038, 0.036, 0.038),
            (0.597, 0.040, 0.040, 0.040), (0.60, 0.085, 0.085, 0.085), (0.95, 0.085, 0.085, 0.085)]
# a straight shin and a kneecap swelling in front at 0.49 under a thigh tube
KNEECAP = [(0.05, 0.036, 0.036, 0.036), (0.40, 0.042, 0.042, 0.042), (0.49, 0.050, 0.062, 0.046),
           (0.58, 0.046, 0.046, 0.046), (0.66, 0.050, 0.050, 0.050), (0.95, 0.070, 0.070, 0.070)]


def selftest_knee(ok, opts) -> None:
    """The knee on the leg's own sections: a hem above it, a change of H, a kneecap."""
    lower_hem = [(z - 0.03 if z >= 0.56 else z, *r) for z, *r in CALF_HEM]
    for name, knots, want, hat in (("calf and hem", CALF_HEM, 0.48, 0.0),
                                   ("calf and hem, taller H", CALF_HEM, 0.48, 0.12),
                                   ("calf and a lower hem", lower_hem, 0.48, 0.0),
                                   ("kneecap", KNEECAP, 0.49, 0.0)):
        v, f = _leg_body(knots, hat)
        rep = build_report(v, f, dict(opts, no_window_gate=True))
        k = rep["landmarks"]["knee.L"]
        ok(f"knee, {name}: measured within 1 cm of {want}", rep["methods"]["knee.L"] == "measured"
           and abs(k[2] - want) < 0.01)
        cue = "kneecap" if knots is KNEECAP else "valley"
        ok(f"knee, {name}: read as {cue}", any(n.startswith(f"L knee: {cue}") for n in rep["notes"]))
    # the hem alone, over a straight leg: no knee to find, and the hem is not taken for one
    v, f = _leg_body([(0.05, 0.04, 0.04, 0.04), (0.597, 0.045, 0.045, 0.045), (0.60, 0.085, 0.085, 0.085),
                      (0.95, 0.085, 0.085, 0.085)])
    rep = build_report(v, f, dict(opts, no_window_gate=True))
    ok("knee, a hem over a straight leg: proportion", rep["methods"]["knee.L"] == "proportion"
       and rep["landmarks"]["knee.L"][2] < 0.56)


def selftest_hip(ok, opts) -> None:
    """The hip over the crotch: thick thighs meeting low (a heavy body) and shorts widening the leg at the crotch."""
    knee = [(0.05, 0.036, 0.036, 0.036), (0.44, 0.042, 0.042, 0.042), (0.53, 0.050, 0.062, 0.046),
            (0.62, 0.046, 0.046, 0.046), (0.70, 0.060, 0.060, 0.060), (0.95, 0.13, 0.13, 0.13)]
    v, f = _leg_body(knee)
    o = dict(opts, no_window_gate=True)
    rep, m = build_report(v, f, o), measure(v, f, o)
    hip = rep["landmarks"]["hip.L"][2] - m["ground_z"]
    lim = next(g for g in rep["gates"] if g["name"] == "markers.limb_ratio")
    ok("thick thighs meeting low: the hip a thigh's half-width over the crotch (over 0.04 H), the thigh about the "
       "shin, markers.limb_ratio passes", hip - m["crotch_h"] * m["height"] > 0.04 * m["height"] and lim["pass"]
       and not any("hip: lowered" in n for n in rep["notes"]))
    v, f = _leg_body(CALF_HEM)          # shorts to 0.60 as wide as the thigh's top: the crotch's leg is the hem's
    rep = build_report(v, f, o)
    lm = rep["landmarks"]
    ok(f"shorts at the crotch: the hip no higher than {THIGH_MAX} x the shin over the measured knee, noted",
       lm["hip.L"][2] - lm["knee.L"][2] <= THIGH_MAX * (lm["knee.L"][2] - lm["ankle.L"][2]) + 1e-4
       and any(n.startswith("L hip: lowered") for n in rep["notes"]))


def selftest_skirt(ok, opts) -> None:
    """The tube body in a skirt to 0.40 x 1.7 m: solid, and open at the hem with the legs inside."""
    sv, sf = M.body(skirt=0.40)
    H = float(np.ptp(sv[:, 2]))
    plain = build_report(sv, sf, opts)
    ok("skirt, default body: the hip is read from the hem (its leg's half-width over it), far under the legs' top",
       0.68 < plain["landmarks"]["hip.L"][2] < 0.68 + 0.06 * H)
    rep = build_report(sv, sf, dict(opts, body="skirt"))
    lm, sk = rep["landmarks"], rep["skirt"]
    ok("skirt route: crotch hidden in a solid skirt, the hip by proportion near the leg tubes' top",
       sk["crotch_h"] is None and rep["methods"]["hip.L"] == "proportion" and abs(lm["hip.L"][2] - 0.90) < 0.06 * H)
    ok("skirt route: every window passes, the skirt block is written", rep["pass"] and rep["body"] == "skirt"
       and {"hem_z", "top_z", "legs", "torso", "half_width"} <= set(sk))
    V = np.asarray(sv, float)
    reg = skirt_region(V, sk)
    hem_z = sk["hem_z"]
    on_leg = (V[:, 2] < hem_z - 0.01 * H) & (np.abs(np.abs(V[:, 0]) - 0.10) < 0.07)
    ok("skirt region: the skirt skin, not the hands beside it nor the legs under the hem", reg.sum() > 100
       and np.abs(V[reg, 0]).max() < 0.3 and not (reg & on_leg).any() and V[reg, 2].max() <= sk["top_z"] + 1e-6)
    ov, of = M.body(skirt=0.40, open_skirt=True)
    rep2 = build_report(ov, of, dict(opts, body="skirt"))
    top = max(z for z, *_ in rep2["skirt"]["legs"]["L"])
    ok("open skirt: the legs are followed up inside it, past the hem", top > rep2["skirt"]["hem_z"] + 0.05 * H)
    # a crotch measured inside the skirt: the hip a thigh's radius over it, as in trousers (an armoured guard's tunic)
    prof, ank = M.profile(sv, sf), np.array([0.1, 0.0, 0.08])
    z0 = float(np.asarray(sv)[:, 2].min())
    legs = lambda r: {1: [[z0 + h * H, 0.1, 0.0, r] for h in np.arange(0.30, 0.49, 0.01)]}
    thick = skirt_hip(sv, sf, prof, 1, {"crotch_h": 0.5, "hem_h": 0.4, "legs": legs(0.09)}, ank)[0]
    thin = skirt_hip(sv, sf, prof, 1, {"crotch_h": 0.5, "hem_h": 0.4, "legs": legs(0.01)}, ank)[0]
    ok("skirt route, crotch inside the skirt: the hip the leg loop's radius over it (0.09 m), at least 0.02 H",
       abs(thick[2] - (z0 + 0.5 * H + 0.09)) < 1e-6 and abs(thin[2] - (z0 + 0.52 * H)) < 1e-6)


def selftest_chibi(ok, opts) -> None:
    """The chibi tube body (mesh_check.chibi_body): the adult windows refuse it, its own route reads it; an adult
    body on the chibi route fails the chibi windows (the route is a body type, not a looser gate)."""
    cv, cf = M.chibi_body()
    plain = build_report(cv, cf, opts)
    ok("chibi, default body: markers.windows fails", not next(g for g in plain["gates"] if g["name"] == "markers.windows")["pass"])
    rep = build_report(cv, cf, dict(opts, body="chibi", arm_ratios=None))
    lm, H = rep["landmarks"], rep["height"]
    h = lambda k: (lm[k][2] - rep["ground_z"]) / H
    ok("chibi route: every gate passes, body chibi, the chibi windows reported", rep["pass"] and rep["body"] == "chibi"
       and next(g for g in rep["gates"] if g["name"] == "markers.windows")["limit"]["neck"] == list(CHIBI_WINDOWS["neck"]))
    ok("chibi route: the hip a leg's radius over the crotch (legs end at 0.27 + r 0.05), the neck under the head, "
       "neck_base and head_base a third and two thirds of the way from the shoulder",
       abs(lm["hip.L"][2] - 0.31) < 0.03 and h("neck") < 0.80 and abs(lm["neck_base"][2] - (lm["shoulder.L"][2] +
       (lm["neck"][2] - lm["shoulder.L"][2]) / 3)) < 1e-4 and lm["neck_base"][2] < lm["head_base"][2] < lm["neck"][2])
    av, af = M.body()
    adult = build_report(av, af, dict(opts, body="chibi", arm_ratios=None))
    ok("adult body on the chibi route: the chibi windows fail it",
       not next(g for g in adult["gates"] if g["name"] == "markers.windows")["pass"])
    # hand_loops: four finger tubes cut into four loops, a mitten into one
    L = 0.18
    frame = (np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]), L)
    fingers = M.assemble([M.tube((0.0, 0, 0), (0.09, 0, 0), 0.02, rx=0.02, ry=0.045)] +
                         [M.tube((0.07, y, 0), (L, y, 0), 0.008) for y in (-0.03, -0.01, 0.01, 0.03)])
    mitten = M.assemble([M.tube((0.0, 0, 0), (L, 0, 0), 0.02, rx=0.02, ry=0.045)])
    fl, ml = hand_loops(*fingers, np.zeros(3), frame), hand_loops(*mitten, np.zeros(3), frame)
    ok("hand_loops: four apart fingers cut into four loops (five over the palm's end), a mitten into one",
       min(fl[-10:]) == 4 and max(ml) == 1)


def selftest_prop(ok, opts) -> None:
    """A shield held beside the left hand, standing from above the armpit to under the hand: its slices make a
    vertical track of their own. Without the retry the left arm is that track (refused, vertical axis); with it the
    arm is found, the left arm is the right one mirrored, the slices are reported as the prop, and the midline
    and the fingers come from the body, not the shield."""
    global PROP_RETRIES
    v, f = M.assemble([M.body(), M.tube((0.67, 0, 1.42), (0.67, 0, 0.64), 0.15, rx=0.015, ry=0.15)])
    plain_v, plain_f = M.body()
    base = build_report(plain_v, plain_f, opts)
    saved = PROP_RETRIES
    try:
        PROP_RETRIES = 0
        build_report(v, f, opts)
        before = "passed"
    except Refused as e:
        before = str(e)
    finally:
        PROP_RETRIES = saved
    rep = build_report(v, f, opts)
    lm = rep["landmarks"]
    ok("a held shield beside the left arm: without the retry the arm is the shield's vertical track (refused); "
       "with it every gate passes, the prop is the left side's, the arm markers match the body without the shield",
       "vertical" in before and rep["pass"] and rep.get("prop", {}).get("side") == "L"
       and len(rep["prop"]["slices"]) >= 10 and abs(rep["midline_x"]) < 0.01
       and all(np.linalg.norm(np.subtract(lm[k], base["landmarks"][k])) < 0.01 * rep["height"]
               for k in ("shoulder.L", "wrist.L", "hand_tip.L", "shoulder.R"))
       and any("mirrored from the R arm" in n for n in rep["notes"]))
    prof = M.profile(v, f)
    saved = M.MIDLINE_SHIFT
    try:
        M.MIDLINE_SHIFT = 1.0
        off = M.profile(v, f)["midline_x"]
    finally:
        M.MIDLINE_SHIFT = saved
    ok("the midline from the feet when a held prop pulls the extent under 0.4 H off them (with the rule off it "
       "is off by more than 0.05 H)", abs(prof["midline_x"]) < 0.01 and abs(off) > 0.05 * prof["height"])
    v2, f2 = M.assemble([M.body(), M.tube((0.67, 0, 1.42), (0.67, 0, 0.64), 0.15, rx=0.015, ry=0.15),
                         M.tube((-0.67, 0, 1.42), (-0.67, 0, 0.64), 0.15, rx=0.015, ry=0.15)])
    try:
        build_report(v2, f2, opts)
        both = "passed"
    except Refused as e:
        both = str(e)
    ok("a vertical track beside both arms: nothing to mirror from, refused as arms held against the body",
       "both arms read vertical" in both)


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
    ok("tube body: ok", rep["pass"])
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

    def gate_of(r, name):
        return next(g for g in r["gates"] if g["name"] == name)
    ok("limb ratio and finger lengths pass on the tube body", gate_of(rep, "markers.limb_ratio")["pass"]
       and gate_of(rep, "markers.finger_lengths")["pass"] and gate_of(rep, "markers.finger_lengths")["value"])
    el, wr = np.array(lm["elbow.L"]), np.array(lm["wrist.L"])
    shift = {"elbow.L": (el + (wr - el) / np.linalg.norm(wr - el) * 0.05 * H).tolist()}
    ok("an elbow 0.05 H toward the wrist (adjusted, mirrored) fails markers.limb_ratio",
       not gate_of(build_report(v, f, dict(opts, adjust=shift)), "markers.limb_ratio")["pass"])
    hp, kn, an = np.array(lm["hip.L"]), np.array(lm["knee.L"]), np.array(lm["ankle.L"])
    low = (kn + (hp - kn) * 0.8 * np.linalg.norm(an - kn) / np.linalg.norm(hp - kn)).tolist()
    ratio_low = build_report(v, f, dict(opts, adjust={"hip.L": low}))
    ok("a hip read low (the thigh 0.8 x the shin, a heavy body's crotch) fails markers.limb_ratio",
       not gate_of(ratio_low, "markers.limb_ratio")["pass"] and ratio_low["gates"] is not rep["gates"])
    i0, i1 = np.array(lm["index0.L"]), np.array(lm["index1.L"])
    step = (i1 - i0) / np.linalg.norm(i1 - i0) * 0.0005
    collapse = {f"index{i}.L": (i0 + step * i).tolist() for i in (1, 2, 3)}
    ok("an index chain collapsed onto its base fails markers.finger_lengths",
       not gate_of(build_report(v, f, dict(opts, adjust=collapse)), "markers.finger_lengths")["pass"])
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
    ok("arm angle outside 50-60 fails", not rep4["pass"] and not next(g for g in rep4["gates"]
                                                                     if g["name"] == "markers.arm_angle")["pass"])
    adj = {"shoulder.L": [0.16, 0.0, 1.0]}
    rep5 = build_report(v, f, dict(opts, adjust=adj))
    ok("adjust: moved, mirrored, method adjusted", rep5["landmarks"]["shoulder.R"][0] == -0.16 and
       rep5["methods"]["shoulder.L"] == "adjusted")
    ok("adjust: a low shoulder fails the window gate", not next(g for g in rep5["gates"]
                                                                 if g["name"] == "markers.windows")["pass"])
    ok("no window gate: reported only", next(g for g in build_report(v, f, dict(opts, adjust=adj, no_window_gate=True))["gates"]
                                             if g["name"] == "markers.windows")["pass"])
    # a pelvis moved up by a person: the proportion spine follows, root_ref still points up
    base = build_report(v, f, opts)
    pz = base["landmarks"]["pelvis"][2] + 0.1
    rs = build_report(v, f, dict(opts, adjust={"pelvis": [base["landmarks"]["pelvis"][0], base["landmarks"]["pelvis"][1], pz]}))
    zs = [rs["landmarks"][k][2] for k in ("pelvis", "spine1", "spine2", "spine3", "neck_base")]
    root = rs["arp_refs"]["root_ref.x"]
    ok("adjust pelvis: the proportion spine follows (evenly between pelvis and neck_base), root_ref points up",
       all(a < b for a, b in zip(zs, zs[1:])) and abs((zs[2] - zs[0]) - (zs[4] - zs[2])) < 1e-6
       and root["tail"][2] > root["head"][2] and rs["methods"]["spine1"] == "proportion"
       and rs["landmarks"]["neck_base"] == base["landmarks"]["neck_base"])
    keep = build_report(v, f, dict(opts, adjust={"pelvis": rs["landmarks"]["pelvis"], "spine2": base["landmarks"]["spine2"]}))
    ok("adjust pelvis and spine2: spine2 stays where the person put it",
       keep["landmarks"]["spine2"] == base["landmarks"]["spine2"] and keep["methods"]["spine2"] == "adjusted")
    # an asymmetric body fails the symmetry gate: move the left leg out
    vs, fs = M.body()
    sel = (vs[:, 0] > 0.04) & (vs[:, 2] < 0.85)
    vs = vs.copy()
    vs[sel, 0] += 0.06
    rep6 = build_report(vs, fs, opts)
    ok("asymmetric legs fail symmetry", not next(g for g in rep6["gates"] if g["name"] == "markers.symmetry")["pass"])
    # a person adjusts the markers that differ: they leave the gate and are reported as accepted
    limit = 0.02 * rep6["height"]
    off = [k for k, val in rep6["asymmetry_m"].items() if val > limit]
    adj6 = {k + ".L": rep6["landmarks"][k + ".L"] for k in off}
    rep7 = build_report(vs, fs, dict(opts, adjust=adj6))
    sym7 = next(g for g in rep7["gates"] if g["name"] == "markers.symmetry")
    ok("adjusted markers: symmetry passes, asymmetry_accepted lists them",
       bool(off) and sym7["pass"] and set(rep7["asymmetry_accepted"]) == set(off))
    one = {off[0] + ".L": rep6["landmarks"][off[0] + ".L"]} if len(off) > 1 else {}
    rep8 = build_report(vs, fs, dict(opts, adjust=one)) if one else rep6
    ok("adjusting one of several: the others still fail symmetry",
       not next(g for g in rep8["gates"] if g["name"] == "markers.symmetry")["pass"])
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
    hz, hx = np.array(rep["hand_frames"][".L"]["z"]), np.array(rep["hand_frames"][".L"]["x"])
    ok("hand frame: the palm normal is a unit vector across the hand", abs(np.linalg.norm(hz) - 1) < 1e-3
       and abs(hz @ hx) < 1e-3)
    fan = [np.array(lm[f"{n}0.L"]) for n in ("index", "little")]
    ok("fixed hand: index and little knuckles apart", np.linalg.norm(fan[0] - fan[1]) > 0.01)
    selftest_smart(ok, v, f, opts, rep)
    selftest_knee(ok, opts)
    selftest_hip(ok, opts)
    selftest_skirt(ok, opts)
    selftest_chibi(ok, opts)
    selftest_prop(ok, opts)
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
