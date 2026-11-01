#!/usr/bin/env python3
"""secondary_chains.py — spring-chain bones for the loose parts of a fused image-to-3D body.

An image-to-3D character is one shell: the hood, the bag, the jacket hem, the shorts hems and the
hair spikes are not separate meshes, so there is no cloth to simulate. This finds those regions on
the bound mesh, adds a short chain of plain `cc_` bones for each (parented to the contract bone it
hangs from, plus an unweighted tip bone), gives each chain a share of the existing skin weights
inside its region only, sizes body colliders, and writes `secondary/1` for the Unity spring
runtime (unity-rigged-character SecondaryMotionSetup). Auto-Rig Pro's exporter keeps any bone
named `cc_*` as a deform custom bone with its name and parent, so the rig's bind (and any weight
repair) is kept: no Match to Rig, no rebind.

usage (Blender, headless; not --factory-startup when it exports, the exporter is Auto-Rig Pro's):
    blender -b RIG.blend -P secondary_chains.py -- --mesh Runner [--armature RunnerRig] \
        [--map arp|ROLE_MAP.json|CONTRACT_REPORT.json] [--kinds auto|hood,bag,hem,shorts_hem,hair] \
        [--require KINDS] [--markers MARKERS.json] [--save OUT.blend] [--fbx OUT.fbx] \
        [--out OUT.secondary.json] [--report GATE.json] [--render DIR] [--detect-only] \
        [--hair-mesh auto|NAME|none] [--hair-chains] [--skirt MARKERS.json]
    blender -b --factory-startup -P secondary_chains.py -- --selftest [--render DIR]

--armature defaults to the armature the mesh's Armature modifier uses. --kinds auto (default) looks
for every kind below; a kind not found is reported (detect.found), not failed, so a body with no
loose parts writes an empty chain list and passes. --require names the kinds that must be found.
The export goes through blender-retarget's brt_arp `export` op, found beside this skill.

Regions (each found from the mesh in the body frame: metres, +Z up, facing -Y; thresholds scale
with the body height H; any of them replaced by a marker chain, reference/secondary-chains.md):
  hood        a bulge behind the upper back: back depth (behind the spine line, central strip) above
              a morphological opening of its own profile by > 0.02 H, in a connected component
              reaching >= 0.04 H off it (buttocks and shoulder blades do not) whose centroid lies
              above UpperChest; one chain from the nape down its middle. A component spanning more than
              BACK_SPAN degrees round the spine line wraps the body (a belt read against a vented coat
              back) and is neither; a hood narrower than HOOD_WIDTH x H across is hair or a tie
  bag         the same test, a component centred between Hips - 0.08 H and UpperChest and at least
              BAG_WIDTH x H across (a hank of hair or a strap lying on the back is narrower); one bone
              from the top attachment (body side) to the bottom, rigid below its top quarter; its
              share fades smoothly from 0.012 H outside the bulge to 0.04 H inside it, so a swing
              stretches a band of skin, not the one edge between the bag and the jacket below
  bag on a hip or a side (bagL, bagR) the back rule turned 90 degrees: per side, skin of the hips, spine,
              chest and that thigh (never an arm) standing >= BULGE x H out of the opened lateral profile
              (the farthest sideways reach in a strip round the mid-plane), centred between Hips - 0.08 H
              and UpperChest, at least BAG_WIDTH x H deep front to back, no taller than SIDE_TALL x H
              (a cape's or a long coat's side edge is taller) and not wrapping the body; one bone, its
              share from the hips, spine and that thigh. A bag set back behind the hip's widest point
              stands out of neither profile: a marker chain
  hem         the jacket's bottom edge: the z where horizontal skin (|normal z| > 0.5, the hem's
              underside) peaks within Hips +- 0.06 H, outside the bag and hood; six sectors (FL, L,
              BL, FR, R, BR), each live when the skin 0.012 H above the edge stands >= 0.004 H
              further out than the skin below it and the bag does not cover it; at least four
              live, else no hem; one one-bone chain per live sector, neighbours fading to zero
              towards a dead one; the sectors blend round one ring and share its skin (a region each
              would leave the last sector nothing)
  hem, --skirt (an arp_markers --body skirt report: a long coat, a skirt, a robe) the hem is the markers'
              one, wherever it hangs: the skirt's own skin (arp_markers.skirt_region) in six sectors round
              the hips, a sector live with >= 30 vertices within 0.03 H of the hem; one two-bone chain per
              live sector from the hip down the skirt's surface to the hem, hung from the bone holding
              most of its skin (the thigh it covers, after the skirt bind; else Hips) and taking its share
              from that bone first, so a pose moves the skirt as the bind did; the share rises to
              SKIRT_SHARE at the hem (then from Hips and both thighs), fading to 0 within
              SKIRT_FADE x H of the legs' own skin (a skirt joined to them); the six blend round the ring and
              share its skin (one ring, not one region each). Fewer than four live sectors is no hem, unless
              both back sectors are live and neither front one: a cape, chained on its live sectors, each half
              hung from the thigh behind which it hangs (as the skirt bind moves it). A back
              bulge mostly of the skirt's own skin is its drape, not a bag; shorts_hem is not searched (the skirt
              covers the thighs)
  shorts_hem  per leg, the largest drop of the median skin radius around the thigh axis (hip to
              knee and on), kept when the radius above is >= 1.35 x and >= 0.01 H more than below
              (a thigh tapering to the knee is not a hem); 3 one-bone chains (front, outer, back), one
              ring per leg; the inner side fades to zero. Both legs find it within SHORTS_PAIR x H of each other, or
              neither leg gets a chain (one leg alone is a skirt's or a coat's hem: detect.shorts.unpaired)
  hair        head-dominant skin outside the face cone; the farthest fifth from the head centre
              clustered by direction (k-means, at most 6, merged under 25 degrees); a cluster is a
              spike when >= 0.12 of its skin faces sideways (|normal . radial| < 0.5: a smooth skull
              has none) and those sides face round it: when one axis holds more than SPIKE_PLATE of
              its own skin's side normals it is a plate (a cap brim, a visor: detect.hair_rejected), and
              when under SPIKE_OUTER of its skin on the outer envelope (within 1 % of the farthest skin in
              its direction from the head centre, weighted by the share) faces sideways (|normal . radial| <
              OUTER_SIDE) it is a crown (a cap, a helmet: rigid on Head; its side-facing
              skin hides under the rim); one
              chain per spike from the hair mass to its tips, two bones when longer than 0.04 H. A
              marker chain of kind hair (a ponytail) may skin the head and the torso within its
              region radius and takes its share from them, hung from Head (so it turns with the head);
              one that hangs below the neck gets the hood's Back sphere beside the Head one
  strap       not detected: fixed at both ends, a free-tip spring is the wrong tool. A marker chain
              of kind strap gets one stiff bone whose share peaks mid-span (a sag).
A separate hair object (--hair-mesh, default auto: the mesh assemble_parts.py bind leaves, marked
parts_hair and named Hair, bound to the rig): the body is not searched for hair, and the hair stays
rigid on Head unless --hair-chains runs the hair kind on that object (the head centre from the
body's head skin and the hair together, thresholds from the body's H; weights on the hair object
only). A spike too small to give each bone 50 vertices is left rigid (detect.dropped_small).

Weights: inside a region a chain's share ramps from 0 at its root to s_max along it, feathered at
the region border and blended between neighbouring chains of a ring; the share is taken from the
chain's parent first, then from the region's other source bones (spine bones for the torso, the
thigh's own bones for the shorts, head and neck for the hair, head and torso for a marker hair chain) in proportion; limb bones are never
touched for torso chains. Every vertex keeps at most 4 deform weights (a fifth drops the smallest
body weight, not a chain weight) and sums to 1, so the exporter's own limit pass trims nothing.
Each vertex belongs to one region (bag > hood > hair > hem > shorts_hem > strap).

Colliders: capsules Hips, Spine, Chest, UpperChest, UpperLeg.L/R, LowerLeg.L/R and the Head sphere,
radii from the skin around them; each kind tests its own group (a shorts hem: both thighs, its own
included), and a collider is shrunk (or dropped from that chain, under half its radius) until no
chain joint below the root starts inside it. A hood rests on the back, inside the torso capsules, so
those drop out of its group; it gets a Back sphere instead (radius 0.5 H on UpperChest, centre in front
of the chain) whose surface runs just under its rest joints: it never starts inside it and stops the
hood sinking into the back further than it rests.

Gates (gate/1 report, each failing one makes exit 2):
  secondary.chains_placed          every --require kind got a chain (hem: >= 4); [] without --require
  secondary.weighted_vertices      every weighted chain bone holds >= 50 vertices
  secondary.max_influences         <= 4 deform weights on every vertex
  secondary.weight_sum             every vertex's deform weights sum to 1 (1e-4)
  secondary.body_weights_unchanged outside every region, every weight is unchanged
  secondary.tip_unweighted         no tip bone carries a weight
  secondary.leak                   each chain's bones turned 25 degrees: no vertex outside its
                                   region moves more than 1 mm (value: worst, m)
  secondary.rest_penetration       no chain joint below the root lies inside a collider of its
                                   group after shrinking (shrunk / dropped are listed)
  with --fbx (after the brt_arp export, which runs its own arp.* gates):
  secondary.export_bones           every cc_ bone is in the re-imported FBX with its parent
  secondary.export_weights         every re-imported vertex weighted to a cc_ bone lies in that
                                   chain's region, and the weights match (0.01): nothing trimmed
With no chain found, no bone is added and nothing is exported: the rig and its FBX stay as they were.

Writes: --save the rig with the chains; --fbx through brt_arp `export` (Unity, humanoid, c_traj
root) and its <fbx>.skeleton.json; --out secondary/1 (bones as exported, joints and parent_head in
the skeleton/1 frame); --render before/after pictures. Then, outside Blender: contract_map.py map
<skeleton> --map arp --require contract (cc_ bones are extras) and deform_gate.py --fbx <fbx> --map
<contract>, which reads the bones the chains hang from as without them. autorig.py's `secondary`
stage runs all three.

Prints one JSON object (the gate report). Exit codes: 0 every gate passed; 2 a gate failed;
1 refused input, a usage error or a failed --selftest. Requires Blender (bpy, mathutils) and
numpy; the export step also needs Auto-Rig Pro enabled.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile

import numpy as np

try:
    import bpy
    from mathutils import Matrix, Quaternion, Vector
    from mathutils.kdtree import KDTree
except ImportError:  # outside Blender only the argument check runs (usage errors exit 1)
    bpy = None

TOOL = "secondary_chains.py"
HERE = os.path.dirname(os.path.abspath(__file__))
BRT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "blender-retarget", "scripts")   # brt_arp

# Auto-Rig Pro export names -> contract roles (the arp preset of contract_map.py, body only).
ARP_ROLES = {"Hips": "root.x", "Spine": "spine_01.x", "Chest": "spine_02.x", "UpperChest": "spine_03.x",
             "Neck": "neck.x", "Head": "head.x"}
for _s, _S in (("l", "L"), ("r", "R")):
    ARP_ROLES.update({f"Shoulder.{_S}": f"shoulder.{_s}", f"UpperArm.{_S}": f"arm_stretch.{_s}",
                      f"LowerArm.{_S}": f"forearm_stretch.{_s}", f"Hand.{_S}": f"hand.{_s}",
                      f"UpperLeg.{_S}": f"thigh_stretch.{_s}", f"LowerLeg.{_S}": f"leg_stretch.{_s}",
                      f"Foot.{_S}": f"foot.{_s}"})
LIMB_ROLES = ("Shoulder", "UpperArm", "LowerArm", "Hand", "UpperLeg", "LowerLeg", "Foot")
TORSO = ("Hips", "Spine", "Chest", "UpperChest", "Neck", "Shoulder.L", "Shoulder.R")
PONYTAIL = ("Head",) + TORSO   # a marker hair chain's skin and sources: a ponytail hangs onto the neck and back

# Defaults per kind: stiffness, drag, gravity, wind, inertia, max angle, particle radius (x H),
# share s_max, colliders.
KINDS = {
    "hood":       dict(stiffness=0.35, drag=0.35, gravity=0.6, wind=0.2, inertia=1.0, max_angle_deg=40,
                       radius=0.023, s_max=0.85, colliders=["Chest", "UpperChest"]),
    "bag":        dict(stiffness=0.25, drag=0.45, gravity=1.0, wind=0.0, inertia=1.0, max_angle_deg=30,
                       radius=0.034, s_max=0.9, colliders=["Hips", "Spine", "UpperLeg.L", "UpperLeg.R"]),
    "hem":        dict(stiffness=0.55, drag=0.40, gravity=0.3, wind=0.2, inertia=1.0, max_angle_deg=25,
                       radius=0.011, s_max=0.8, colliders=["UpperLeg.L", "UpperLeg.R", "Hips"]),
    "shorts_hem": dict(stiffness=0.65, drag=0.40, gravity=0.2, wind=0.1, inertia=1.0, max_angle_deg=20,
                       radius=0.009, s_max=0.7, colliders=[]),
    "hair":       dict(stiffness=0.75, drag=0.30, gravity=0.1, wind=0.3, inertia=1.0, max_angle_deg=20,
                       radius=0.006, s_max=0.75, colliders=["Head"]),
    "strap":      dict(stiffness=0.85, drag=0.5, gravity=0.3, wind=0.0, inertia=1.0, max_angle_deg=10,
                       radius=0.006, s_max=0.5, colliders=["Chest", "UpperChest"]),
}
PRIORITY = ["bag", "hood", "hair", "hem", "shorts_hem", "strap"]
DETECTED = ("hood", "bag", "hem", "shorts_hem", "hair")      # --kinds auto
# what tells a loose part from anatomy (x H): a smooth body without clothes passes none of these
BULGE = 0.04          # hood, bag: deepest point off the opened back profile
LIP = 0.004           # hem: the skin just above the edge stands out from the skin just below
HEM_RING = 4          # hem: live sectors needed, or no hem at all
SKIRT_SHARE = 0.6     # hem --skirt: the chains' share at the hem (the thighs keep the rest of theirs)
SKIRT_FADE = 0.04     # hem --skirt: the share fades to 0 over this distance (x H) towards the legs' own skin
SHORTS_RATIO, SHORTS_DROP = 1.35, 0.01   # shorts hem: radius above / below the drop, and the drop
BAG_BORDER = (0.012, 0.04)   # bag: its share fades from this far outside its bulge to this far inside (x H)
BACK_SPHERE = 0.5     # hood: the back sphere's radius (x H), flat across the hood's span
SPIKE_SIDES = 0.12    # hair: share of a cluster's skin facing sideways (|normal . radial| < 0.5)
SPIKE_PLATE = 0.72    # hair: a spike's side normals turn around it; a plate's (a cap brim) share one axis above this
BACK_SPAN = 180.0     # hood, bag: a component spanning more of the circle round the spine line wraps the body (a belt)
HOOD_WIDTH, BAG_WIDTH = 0.12, 0.08   # x H across: narrower is a hank of hair or a tie lying on the back
SIDE_TALL = 0.25      # bag on a hip or side: a lateral bulge taller than this (x H) is a cape's or a coat's edge
SIDE_PARTS = ("Hips", "Spine", "Chest")   # a side bag's skin (and its side's thigh): never an arm or the chest top
OUTER_SIDE = 0.6      # hair, on the outer envelope: skin facing sideways when |normal . radial| < this
SPIKE_OUTER = 0.24    # hair: share of a spike's skin on the outer envelope (seen from the head centre) facing sideways;
                      # a crown (a cap, a helmet) is a smooth dome there, its side-facing skin hidden under the rim
SHORTS_PAIR = 0.03    # shorts hem: both legs find it within this height (x H), or neither leg is a shorts hem
HUMAN = {"Hips": "Hips", "Spine": "Spine", "Chest": "Chest", "UpperChest": "UpperChest", "Neck": "Neck",
         "Head": "Head"}
for _S, _w in (("L", "Left"), ("R", "Right")):
    for _r in LIMB_ROLES:
        HUMAN[f"{_r}.{_S}"] = _w + _r


class Refused(Exception):
    pass


# ----------------------------------------------------------------------------- small numeric helpers

def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def r6(v):
    return [round(float(x), 6) for x in v]


def _kd(points):
    kd = KDTree(len(points))
    for i, p in enumerate(points):
        kd.insert(p, i)
    kd.balance()
    return kd


def nearest_dist(points, queries):
    """Distance from each query to the nearest of `points`."""
    points, queries = np.asarray(points, float), np.asarray(queries, float)
    if len(points) == 0:
        return np.full(len(queries), np.inf)
    kd = _kd(points)
    return np.array([kd.find(q)[2] for q in queries])


def nearest_index(points, queries):
    kd = _kd(np.asarray(points, float))
    res = [kd.find(q) for q in np.asarray(queries, float)]
    return np.array([r[1] for r in res]), np.array([r[2] for r in res])


def components(mask, edges):
    """Connected components of the vertices in `mask` over `edges`: label per vertex (-1 outside)."""
    n = len(mask)
    lab = np.where(mask, np.arange(n), -1)
    e = edges[mask[edges[:, 0]] & mask[edges[:, 1]]]
    if len(e) == 0:
        return lab
    while True:
        a, b = lab[e[:, 0]], lab[e[:, 1]]
        m = np.minimum(a, b)
        new = lab.copy()
        np.minimum.at(new, e[:, 0], m)
        np.minimum.at(new, e[:, 1], m)
        idx = np.where(new >= 0)[0]
        new[idx] = new[new[idx]]          # pointer jumping
        if np.array_equal(new, lab):
            return lab
        lab = new


def erode_dilate(prof, half):
    """Morphological opening of a 1-D profile (NaN-free) with a window of +-half samples."""
    n = len(prof)
    er = np.array([prof[max(0, i - half):i + half + 1].min() for i in range(n)])
    return np.array([er[max(0, i - half):i + half + 1].max() for i in range(n)])


def seg_project(p, a, b):
    """(t in [0,1], distance) of points p to segment a-b."""
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    return t, np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def polyline_u(p, joints):
    """Arc-length parameter u in [0,1] of the nearest point on the polyline, and the distance."""
    joints = np.asarray(joints, float)
    lens = np.linalg.norm(np.diff(joints, axis=0), axis=1)
    total = max(lens.sum(), 1e-9)
    best_d = np.full(len(p), np.inf)
    best_u = np.zeros(len(p))
    acc = 0.0
    for i in range(len(joints) - 1):
        t, d = seg_project(p, joints[i], joints[i + 1])
        better = d < best_d
        best_d[better] = d[better]
        best_u[better] = (acc + t[better] * lens[i]) / total
        acc += lens[i]
    return best_u, best_d


def split_bones(u, joints):
    """Per-vertex weight split between the chain's bones (linear blend across inner joints)."""
    joints = np.asarray(joints, float)
    k = len(joints) - 1
    if k == 1:
        return np.ones((len(u), 1))
    lens = np.linalg.norm(np.diff(joints, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(lens)]) / lens.sum()
    mids = (cum[:-1] + cum[1:]) / 2
    w = np.zeros((len(u), k))
    for i in range(k):
        left = mids[i - 1] if i > 0 else -1.0
        right = mids[i + 1] if i < k - 1 else 2.0
        up = np.clip((u - left) / max(mids[i] - left, 1e-9), 0, 1) if i > 0 else np.ones_like(u)
        down = np.clip((right - u) / max(right - mids[i], 1e-9), 0, 1) if i < k - 1 else np.ones_like(u)
        w[:, i] = np.minimum(up, down)
    return w / np.maximum(w.sum(1, keepdims=True), 1e-9)


def ring_blend(az, anchors, period=360.0):
    """Weights per anchor for angles `az` (degrees): linear between the two neighbouring anchors.
    anchors: list of (angle, live) — a dead anchor takes its share to zero."""
    order = sorted(range(len(anchors)), key=lambda i: anchors[i][0] % period)
    angs = [anchors[i][0] % period for i in order]
    w = np.zeros((len(az), len(anchors)))
    a = az % period
    for j in range(len(order)):
        i0, i1 = order[j], order[(j + 1) % len(order)]
        a0, a1 = angs[j], angs[(j + 1) % len(order)]
        span = (a1 - a0) % period or period
        rel = (a - a0) % period
        inside = rel < span
        f = rel[inside] / span
        w[inside, i0] += 1 - f
        w[inside, i1] += f
    for i, (_, live) in enumerate(anchors):
        if not live:
            w[:, i] = 0
    return w


# ----------------------------------------------------------------------------- the body model

class Body:
    """The bound mesh in the body frame: positions, edges, normals, dense deform weights, and the
    contract bones' rest positions."""

    def __init__(self, co, edges, nrm, W, names, heads, tails, roles):
        self.co, self.nrm, self.W = co, nrm, W
        # image-to-3D meshes split every UV seam: weld by position so connectivity follows the skin
        q = np.round(np.asarray(co) / 1e-5).astype(np.int64)
        _, wid = np.unique(q, axis=0, return_inverse=True)
        self.wid = wid.ravel()
        we = self.wid[np.asarray(edges)]
        self.edges = we[we[:, 0] != we[:, 1]]
        self.first = np.zeros(self.wid.max() + 1, int)      # a vertex at each welded position
        self.first[self.wid[::-1]] = np.arange(len(self.wid))[::-1]
        self.names = list(names)
        self.col = {n: i for i, n in enumerate(self.names)}
        self.heads = {n: np.asarray(h, float) for n, h in zip(names, heads)}
        self.tails = {n: np.asarray(t, float) for n, t in zip(names, tails)}
        self.roles = {r: b for r, b in roles.items() if b in self.col}
        self.role_of = {b: r for r, b in self.roles.items()}
        zmin, zmax = co[:, 2].min(), co[:, 2].max()
        self.H = float(zmax - zmin)
        self.zmin = float(zmin)
        self.around = None     # a separate hair mesh: the body's head skin under it (detect_hair's centre)
        self.families = self._families()
        fam_w = np.stack([W[:, [self.col[b] for b in bones]].sum(1) for bones in self.families.values()], 1)
        keys = list(self.families)
        self.part = np.array(keys, dtype=object)[fam_w.argmax(1)]
        self.part[fam_w.max(1) <= 0] = ""

    def _families(self):
        """role -> deform bones that move with it: the role's bone, and for a limb role the deform
        bones with the same stem and side (Auto-Rig Pro's thigh_twist.l beside thigh_stretch.l)."""
        def stem(name):
            base = name[2:] if name.startswith("c_") else name
            side = base.rsplit(".", 1)[1] if "." in base else ""
            return base.split(".")[0].split("_")[0], side
        fam = {r: [b] for r, b in self.roles.items()}
        claimed = set(self.roles.values())
        for r, b in self.roles.items():
            if r.split(".")[0] not in LIMB_ROLES:
                continue
            s = stem(b)
            for n in self.names:
                if n not in claimed and stem(n) == s:
                    fam[r].append(n)
                    claimed.add(n)
        return fam

    def bone(self, role):
        return self.roles.get(role)

    def head(self, role):
        return self.heads[self.roles[role]]

    def in_parts(self, roles):
        return np.isin(self.part, [r for r in roles if r in self.families])

    def spine_line(self, z):
        pts = []
        for r in ("Hips", "Spine", "Chest", "UpperChest", "Neck"):
            if r in self.roles:
                pts += [self.heads[self.roles[r]], self.tails[self.roles[r]]]
        pts = np.array(sorted(pts, key=lambda p: p[2]))
        return np.interp(z, pts[:, 2], pts[:, 0]), np.interp(z, pts[:, 2], pts[:, 1])


def chain_dict(name, kind, joints, share, parent, sources, side="x", **extra):
    """A chain: joints root..tip (the last is the tip bone's head), per-vertex share per bone."""
    k = len(joints) - 1
    bones = [f"cc_{name}_{i + 1:02d}.{side}" for i in range(k)] + [f"cc_{name}_end.{side}"]
    return dict(name=name, kind=kind, joints=[list(map(float, j)) for j in joints], share=share,
                parent=parent, sources=sources, bones=bones, side=side, **extra)


def pick_parent(body, share_total, candidates):
    """The candidate contract bone holding the most weight under the chain's share."""
    best, score = None, -1.0
    for r in candidates:
        b = body.bone(r)
        if b is None:
            continue
        s = float((body.W[:, body.col[b]] * share_total).sum())
        if s > score:
            best, score = r, s
    return best


def source_bones(body, roles):
    out = []
    for r in roles:
        out += body.families.get(r, [])
    return out


# ----------------------------------------------------------------------------- detection

def wrap_span(az):
    """Degrees of the circle the azimuths cover (10-degree bins, 360 less the widest empty arc): a bag or a
    hood hangs behind the spine line, a belt or a coat's waist read against a vented back wraps the body."""
    occ = np.histogram(np.asarray(az, float), bins=36, range=(-180, 180))[0] > 0
    run = gap = 0
    for v in np.concatenate([occ, occ]):
        run = 0 if v else run + 1
        gap = max(gap, run)
    return 360.0 - 10.0 * min(gap, 36)


def back_regions(body, taken):
    """Hood and bag: components of skin bulging behind the back."""
    co, H = body.co, body.H
    T = body.in_parts(TORSO) & ~taken
    xs, ys = body.spine_line(co[:, 2])
    dy = co[:, 1] - ys
    dz = 0.01
    zb = np.floor((co[:, 2] - body.zmin) / dz).astype(int)
    nb = zb.max() + 1
    central = T & (np.abs(co[:, 0] - xs) < 0.035 * H)
    B = np.full(nb, np.nan)
    for k in np.unique(zb[central]):
        B[k] = dy[central & (zb == k)].max()
    ok = ~np.isnan(B)
    if ok.sum() < 5:
        return None, None, {}
    idx = np.arange(nb)
    lo, hi = idx[ok].min(), idx[ok].max()
    Bf = np.interp(idx, idx[ok], B[ok])[lo:hi + 1]
    base = np.full(nb, np.nan)
    base[lo:hi + 1] = erode_dilate(Bf, int(round(0.125 * H / dz)))
    base = np.interp(idx, idx[ok], base[ok]) if np.isnan(base).any() else base
    excess = dy - base[np.clip(zb, 0, nb - 1)]
    cand = T & (excess > 0.02 * H)
    wmask = np.zeros(body.wid.max() + 1, bool)
    wmask[body.wid[cand]] = True
    lab = components(wmask, body.edges)[body.wid]
    lab[~cand] = -1
    comps = []
    for l in np.unique(lab[lab >= 0]):
        m = lab == l
        # a bag or hood stands >= 0.04 H off the back; buttocks and shoulder blades stay under it
        if m.sum() < max(50, 0.002 * len(co)) or excess[m].max() < BULGE * H:
            continue
        comps.append((m.sum(), m, float(co[m, 2].mean())))
    z_uc = body.head("UpperChest")[2]
    z_hips = body.head("Hips")[2]
    info = {"back_profile_base": [round(float(x), 4) for x in base[lo:hi + 1:5]],
            "components": [(int(c[0]), round(c[2], 3)) for c in comps], "rejected": []}

    span = lambda m: wrap_span(np.degrees(np.arctan2(co[m, 0] - xs[m], dy[m])))
    width = lambda m: float(np.ptp(co[m, 0]))
    behind = []
    for c in comps:
        sp = span(c[1])
        if sp > BACK_SPAN:
            info["rejected"].append({"vertices": int(c[0]), "z": round(c[2], 3), "span_deg": sp, "why": "wraps the body"})
        else:
            behind.append(c)

    def union(cs):
        if not cs:
            return None
        m = np.zeros(len(co), bool)
        for c in cs:
            m |= c[1]
        return m
    hood = union([c for c in behind if c[2] >= z_uc])
    if hood is not None and width(hood) < HOOD_WIDTH * H:
        info["rejected"].append({"vertices": int(hood.sum()), "z": round(float(co[hood, 2].mean()), 3),
                                 "width_H": round(width(hood) / H, 4), "why": "hood: too narrow (hair or a tie?)"})
        hood = None
    bag = []
    for c in behind:
        if not z_hips - 0.08 * H <= c[2] < z_uc:
            continue
        if width(c[1]) < BAG_WIDTH * H:
            info["rejected"].append({"vertices": int(c[0]), "z": round(c[2], 3), "width_H": round(width(c[1]) / H, 4),
                                     "why": "bag: too narrow (hair or a strap?)"})
        else:
            bag.append(c)
    pick = lambda cs: max(cs, key=lambda c: c[0])[1] if cs else None
    return hood, pick(bag), dict(info, excess=excess, base_dy=base, zb=zb, ys=ys, xs=xs)


def grow(body, core, allowed, dist):
    """Region = allowed skin within `dist` of the core; feather 1 in the core to 0 at `dist`."""
    cand = allowed & ~core
    near = np.zeros(len(core))
    near[core] = 1.0
    if cand.any():
        d = nearest_dist(body.co[core], body.co[cand])
        near[np.where(cand)[0]] = np.clip(1 - d / dist, 0, 1)
    return near


def detect_hood(body, core, info, taken):
    co, H = body.co, body.H
    allowed = body.in_parts(TORSO) & ~taken
    feather = grow(body, core, allowed, 0.012 * H)
    region = feather > 0
    p = co[core]
    z_top, z_bot = p[:, 2].max(), p[:, 2].min()
    # the middle of the bulge's thickness, slice by slice, from the nape down
    pts = []
    for z in np.linspace(z_top - 0.1 * (z_top - z_bot), z_bot + 0.08 * (z_top - z_bot), 7):
        xs, ys = body.spine_line(np.array([z]))
        s = core & (np.abs(co[:, 2] - z) < 0.008 * H) & (np.abs(co[:, 0] - xs[0]) < 0.04 * H)
        if s.sum() < 5:
            continue
        back = ys[0] + np.interp(z, body.zmin + 0.01 * np.arange(len(info["base_dy"])), info["base_dy"])
        pts.append([float(np.median(co[s, 0])), float((back + co[s, 1].max()) / 2), float(z)])
    if len(pts) < 3:
        return None
    pts = np.array(pts)
    u = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    u /= u[-1]
    joints = np.array([[np.interp(t, u, pts[:, i]) for i in range(3)] for t in (0, 0.5, 1)])
    return finish_chain(body, "hood", "hood", joints, region, feather,
                        ramp=0.35, parents=["Neck", "UpperChest"], sources=["UpperChest", "Neck", "Chest"])


def soft_border(body, core, allowed, out, inner):
    """A feather across the core's border: 0 at `out` outside it, 1 at `inner` inside, smoothstep between. A
    fused shell has no seam to hide a swing in: the stretch spreads over the band instead of the one edge
    between a full share and none (a bag's bottom against the jacket)."""
    co = body.co
    t = np.zeros(len(co))
    rim = allowed & ~core
    if rim.any():
        t[rim] = (out - nearest_dist(co[core], co[rim])) / (out + inner)
    if (~core).any():
        t[core] = (out + nearest_dist(co[~core], co[core])) / (out + inner)
    return smoothstep(t)


def detect_bag(body, core, info, taken):
    co, H = body.co, body.H
    allowed = body.in_parts(TORSO) & ~taken
    feather = soft_border(body, core, allowed, BAG_BORDER[0] * H, BAG_BORDER[1] * H)
    region = feather > 0
    p = co[core]
    z_top, z_bot = p[:, 2].max(), p[:, 2].min()
    h = z_top - z_bot
    top = core & (co[:, 2] > z_top - 0.2 * h)
    bot = core & (co[:, 2] < z_bot + 0.2 * h)
    xs, ys = body.spine_line(np.array([z_top - 0.1 * h]))
    back_top = ys[0] + np.interp(z_top - 0.1 * h, body.zmin + 0.01 * np.arange(len(info["base_dy"])),
                                 info["base_dy"])
    j0 = [float(np.median(co[top, 0])), float(back_top + 0.01 * H), float(z_top - 0.1 * h)]
    j1 = [float(np.median(co[bot, 0])), float((co[bot, 1].min() + co[bot, 1].max()) / 2 + 0.25 *
                                              (co[core, 1].max() - co[bot, 1].max())), float(z_bot + 0.1 * h)]
    j1[1] = float(np.median(co[core, 1]))
    return finish_chain(body, "bag", "bag", np.array([j0, j1]), region, feather,
                        ramp=0.25, parents=["Spine", "Hips", "Chest"], sources=["Hips", "Spine", "Chest", "UpperChest"])


def side_regions(body, taken):
    """Bag on a hip or side: per side, components of skin bulging out of the opened lateral profile (the
    skin's farthest reach from the spine line, sideways, in a strip around the body's mid-plane), the back
    rule turned 90 degrees. Kept when it stands >= BULGE x H out, is centred between Hips - 0.08 H and
    UpperChest, is at least BAG_WIDTH x H deep front to back, is no taller than SIDE_TALL x H (a cape's
    or a long coat's side edge is) and does not wrap the body. Arm skin is never searched."""
    co, H = body.co, body.H
    xs, ys = body.spine_line(co[:, 2])
    dz = 0.01
    zb = np.floor((co[:, 2] - body.zmin) / dz).astype(int)
    nb = zb.max() + 1
    z_uc, z_hips = body.head("UpperChest")[2], body.head("Hips")[2]
    out, info = [], {"rejected": []}
    for S, sgn in (("L", 1.0), ("R", -1.0)):
        T = body.in_parts(SIDE_PARTS + (f"UpperLeg.{S}",)) & ~taken
        lat = sgn * (co[:, 0] - xs)
        strip = T & (np.abs(co[:, 1] - ys) < 0.035 * H) & (lat > 0)
        B = np.full(nb, np.nan)
        for k in np.unique(zb[strip]):
            B[k] = lat[strip & (zb == k)].max()
        ok = ~np.isnan(B)
        if ok.sum() < 5:
            continue
        idx = np.arange(nb)
        lo, hi = idx[ok].min(), idx[ok].max()
        base = np.interp(idx, idx[ok], B[ok])
        base[lo:hi + 1] = erode_dilate(base[lo:hi + 1], int(round(0.125 * H / dz)))
        excess = lat - base[np.clip(zb, 0, nb - 1)]
        cand = T & (lat > 0) & (excess > 0.02 * H) & (zb >= lo) & (zb <= hi)
        wmask = np.zeros(body.wid.max() + 1, bool)
        wmask[body.wid[cand]] = True
        lab = components(wmask, body.edges)[body.wid]
        lab[~cand] = -1
        best = None
        for l in np.unique(lab[lab >= 0]):
            m = lab == l
            if m.sum() < max(50, 0.002 * len(co)) or excess[m].max() < BULGE * H:
                continue
            z, tall, deep = float(co[m, 2].mean()), float(np.ptp(co[m, 2])), float(np.ptp(co[m, 1]))
            span = wrap_span(np.degrees(np.arctan2(co[m, 0] - xs[m], co[m, 1] - ys[m])))
            why = ("not between the hips and the chest" if not z_hips - 0.08 * H <= z < z_uc else
                   "too shallow front to back (a strap or a tie?)" if deep < BAG_WIDTH * H else
                   "too tall (a cape's or a coat's edge)" if tall > SIDE_TALL * H else
                   "wraps the body" if span > BACK_SPAN else None)
            if why:
                info["rejected"].append({"side": S, "vertices": int(m.sum()), "z": round(z, 3),
                                         "tall_H": round(tall / H, 3), "deep_H": round(deep / H, 3), "why": why})
            elif best is None or m.sum() > best.sum():
                best = m
        if best is not None:
            out.append((S, best, base))
            info.setdefault("found", []).append({"side": S, "vertices": int(best.sum()),
                                                 "out_H": round(float(excess[best].max()) / H, 3)})
    return out, info


def detect_side_bag(body, S, core, taken):
    """One bone from the bag's top, at the hip's own skin, to its bottom; the share comes from the hips
    and spine and from the thigh on its side (a hip bag lies on both), hung from Hips or Spine."""
    co, H = body.co, body.H
    allowed = body.in_parts(SIDE_PARTS + (f"UpperLeg.{S}",)) & ~taken
    feather = soft_border(body, core, allowed, BAG_BORDER[0] * H, BAG_BORDER[1] * H)
    region = feather > 0
    p = co[core]
    z_top, z_bot = p[:, 2].max(), p[:, 2].min()
    h = z_top - z_bot
    top = core & (co[:, 2] > z_top - 0.2 * h)
    bot = core & (co[:, 2] < z_bot + 0.2 * h)
    sgn = 1.0 if S == "L" else -1.0
    j0 = [float(np.quantile(co[top, 0], 0.5 - 0.3 * sgn)), float(np.median(co[top, 1])), float(z_top - 0.1 * h)]
    j1 = [float(np.median(co[core, 0])), float(np.median(co[bot, 1])), float(z_bot + 0.1 * h)]
    return finish_chain(body, f"bag{S}", "bag", np.array([j0, j1]), region, feather, ramp=0.25,
                        parents=["Hips", "Spine"], sources=["Hips", "Spine", "Chest", f"UpperLeg.{S}"], side=S.lower())


def finish_chain(body, name, kind, joints, region, feather, ramp, parents, sources, side="x", marker=False):
    p = body.co[region]
    u, _ = polyline_u(p, joints)
    s = KINDS[kind]["s_max"] * smoothstep(u / ramp) * feather[region]
    split = split_bones(u, joints)
    share = np.zeros((len(body.co), len(joints) - 1))
    share[region] = s[:, None] * split
    parent = pick_parent(body, share.sum(1), parents)
    return chain_dict(name, kind, joints, share, parent, source_bones(body, sources), side=side,
                      marker=marker)


def detect_hem(body, taken, skip=()):
    co, nrm, H = body.co, body.nrm, body.H
    torso = body.in_parts(("Hips", "Spine", "Chest", "UpperLeg.L", "UpperLeg.R"))
    z_h = body.head("Hips")[2]
    win = (co[:, 2] > z_h - 0.06 * H) & (co[:, 2] < z_h + 0.06 * H)
    xs, ys = body.spine_line(co[:, 2])
    sel = torso & win & ~taken
    if sel.sum() < 100:
        return [], {"hem": "no skin around the hips"}
    cx = float(np.median(co[sel, 0]))
    cy = float((co[sel, 1].min() + co[sel, 1].max()) / 2)
    az = np.degrees(np.arctan2(co[:, 0] - cx, -(co[:, 1] - cy)))     # 0 front, +90 the left side
    r = np.hypot(co[:, 0] - cx, co[:, 1] - cy)
    horiz = sel & (np.abs(nrm[:, 2]) > 0.5) & (body.in_parts(("Hips", "Spine", "Chest")))
    bins = np.arange(z_h - 0.06 * H, z_h + 0.06 * H + 1e-9, 0.01)

    def peak(m):
        h, e = np.histogram(co[m, 2], bins)
        return (float(e[h.argmax()] + 0.005), int(h.max())) if h.max() > 0 else (None, 0)
    z_hem, count = peak(horiz)
    if z_hem is None:
        return [], {"hem": "no horizontal skin"}
    info = {"hem_z": round(z_hem, 4), "hem_peak_count": count, "hem_centre": [round(cx, 4), round(cy, 4)]}

    def sector_lip(sec, z):
        """Outer radius just above the edge minus just below it (the jacket over the shorts)."""
        def q(zz):
            m = sec & (np.abs(co[:, 2] - zz) < 0.004 * H)
            return float(np.quantile(r[m], 0.9)) if m.sum() >= 5 else None
        up, lo = q(z + 0.012 * H), q(z - 0.012 * H)
        return None if up is None or lo is None else up - lo
    names = {30: "hemFL", 90: "hemL", 150: "hemBL", -30: "hemFR", -90: "hemR", -150: "hemBR"}
    top_off, inset = 0.045 * H, 0.006 * H
    anchors, chains_spec = [], []
    for a, nm in names.items():
        d = ((az - a + 180) % 360) - 180
        sector = torso & win & (np.abs(d) < 20)
        covered = (sector & taken).sum() / max(sector.sum(), 1)
        sz, sc = peak(horiz & (np.abs(d) < 30))
        zh = sz if sz is not None and sc >= 20 and abs(sz - z_hem) < 0.03 else z_hem
        lip = sector_lip(torso & ~taken & (np.abs(d) < 15), zh)
        live = covered < 0.25 and nm not in skip and lip is not None and lip >= LIP * H
        anchors.append((a, live))
        chains_spec.append((a, nm, zh, live, round(float(covered), 3), lip))
    info["hem_sectors"] = [{"name": nm, "az": a, "z": round(zh, 4), "live": live, "covered": cov,
                            "lip": None if lip is None else round(lip, 4)} for a, nm, zh, live, cov, lip in chains_spec]
    if sum(c[3] for c in chains_spec) < HEM_RING:
        info["hem"] = f"fewer than {HEM_RING} sectors with a lip of {LIP} H: no hem"
        return [], info
    chains_spec = [c[:5] for c in chains_spec]
    band = torso & ~taken & (co[:, 2] > z_hem - 0.008 * H) & (co[:, 2] < z_hem + top_off + 0.008 * H)
    if band.sum() < 50:
        return [], info
    bw = ring_blend(az[band], anchors)
    out = []
    for i, (a, nm, zh, live, cov) in enumerate(chains_spec):
        if not live:
            continue
        d = ((az - a + 180) % 360) - 180
        sec = sel & (np.abs(d) < 15)
        def surf(z, q):
            m = sec & (np.abs(co[:, 2] - z) < 0.006 * H)
            return float(np.quantile(r[m], q)) if m.sum() >= 5 else None
        rt, rb = surf(zh + top_off, 0.9), surf(zh + 0.004 * H, 0.9)
        if rt is None or rb is None:
            continue
        dirv = np.array([math.sin(math.radians(a)), -math.cos(math.radians(a)), 0])
        j0 = np.array([cx, cy, zh + top_off]) + dirv * (rt - inset)
        j1 = np.array([cx, cy, zh]) + dirv * (rb - 0.5 * inset)
        joints = np.array([j0, j1])
        idx = np.where(band)[0]
        zrel = (zh + top_off - co[idx, 2]) / top_off
        s = KINDS["hem"]["s_max"] * smoothstep(zrel / 0.8) * bw[:, i]
        share = np.zeros((len(co), 1))
        share[idx, 0] = s
        parent = pick_parent(body, share[:, 0], ["Hips", "Spine"])
        out.append(chain_dict(nm, "hem", joints, share, parent, source_bones(body, ["Hips", "Spine", "Chest"]),
                              az=a, ring="hem"))
    return out, info


def detect_skirt_hem(body, taken, skirt, skip=()):
    """The hem of a long coat or skirt at the markers' height (arp_markers --body skirt), wherever it hangs."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import arp_markers
    co, H = body.co, body.H
    region = arp_markers.skirt_region(co, skirt) & ~taken
    hem_z, top_z, hip_z = float(skirt["hem_z"]), float(skirt["top_z"]), float(skirt["hip_z"])
    info = {"hem_z": round(hem_z, 4), "hem_from": "skirt markers", "skirt_vertices": int(region.sum())}
    if region.sum() < 100:
        info["hem"] = "too little skirt skin"
        return [], info
    cx = float(skirt["midline_x"])
    cy = float(body.spine_line(np.array([hip_z]))[1][0])
    az = np.degrees(np.arctan2(co[:, 0] - cx, -(co[:, 1] - cy)))
    r = np.hypot(co[:, 0] - cx, co[:, 1] - cy)
    names = {30: "hemFL", 90: "hemL", 150: "hemBL", -30: "hemFR", -90: "hemR", -150: "hemBR"}
    anchors, spec = [], []
    for a, nm in names.items():
        d = ((az - a + 180) % 360) - 180
        sec = region & (np.abs(d) < 20)
        near = sec & (np.abs(co[:, 2] - hem_z) < 0.03 * H)
        live = int(near.sum()) >= 30 and nm not in skip
        anchors.append((a, live))
        spec.append((a, nm, live, int(near.sum())))
    info["hem_sectors"] = [{"name": nm, "az": a, "live": live, "vertices": n} for a, nm, live, n in spec]
    live = {nm for _, nm, lv, _ in spec if lv}
    if len(live) < HEM_RING:
        if not ({"hemBL", "hemBR"} <= live and not live & {"hemFL", "hemFR"}):
            info["hem"] = f"fewer than {HEM_RING} sectors reach the hem"
            return [], info
        info["hem"] = "a cape: only the back reaches the hem (both back sectors, neither front one)"
    idx = np.where(region)[0]
    bw = ring_blend(az[idx], anchors)
    u = np.clip((top_z - co[idx, 2]) / max(top_z - hem_z, 1e-6), 0, 1)
    # the chains fade out towards the legs' own skin (a skirt joined to them at its hem): a leg moves all of its skin
    legs = body.in_parts(("UpperLeg.L", "UpperLeg.R", "LowerLeg.L", "LowerLeg.R")) & ~region & (co[:, 2] < top_z)
    fade = smoothstep(nearest_dist(co[legs], co[idx]) / (SKIRT_FADE * H)) if legs.any() else np.ones(len(idx))
    info["faded"] = int((fade < 0.99).sum())
    out = []
    for i, (a, nm, live, _) in enumerate(spec):
        if not live:
            continue
        d = ((az - a + 180) % 360) - 180
        sec = region & (np.abs(d) < 15)
        dirv = np.array([math.sin(math.radians(a)), -math.cos(math.radians(a)), 0])
        joints = []
        for z in (hip_z, 0.5 * (hip_z + hem_z), hem_z):
            m = sec & (np.abs(co[:, 2] - z) < 0.01 * H)
            rad = float(np.quantile(r[m], 0.9)) if m.sum() >= 5 else None
            joints.append(None if rad is None else np.array([cx, cy, z]) + dirv * (rad - 0.006 * H))
        if any(j is None for j in joints):
            continue
        joints = np.array(joints)
        s = SKIRT_SHARE * smoothstep(u / 0.8) * bw[:, i] * fade
        su, _ = polyline_u(co[idx], joints)
        share = np.zeros((len(co), 2))
        share[idx] = s[:, None] * split_bones(su, joints)
        cape = info.get("hem", "").startswith("a cape")   # a cape's halves hang behind their own legs: as the bind
        parent = pick_parent(body, share.sum(1), [f"UpperLeg.{nm[-1]}"] if cape else ["UpperLeg.L", "UpperLeg.R", "Hips"])
        out.append(chain_dict(nm, "hem", joints, share, parent,
                              source_bones(body, ["Hips", "Spine", "UpperLeg.L", "UpperLeg.R"]), az=a, ring="skirt"))
    return out, info


def detect_shorts(body, taken, skip=()):
    co, H = body.co, body.H
    out, info = [], {}
    for S, sgn in (("L", 1.0), ("R", -1.0)):
        ul, ll = f"UpperLeg.{S}", f"LowerLeg.{S}"
        if ul not in body.roles or ll not in body.roles:
            info[f"shorts{S}"] = "no leg bones"
            continue
        fam = body.families[ul]
        hip = max((body.heads[b] for b in fam), key=lambda p: p[2])
        knee = body.head(ll)
        L = float(np.linalg.norm(knee - hip))
        u = (knee - hip) / L
        leg = body.in_parts((ul, ll)) & ~taken
        rel = co - hip
        a = rel @ u
        radial = rel - np.outer(a, u)
        rad = np.linalg.norm(radial, axis=1)
        t = a / L
        ts = np.arange(0.2, 1.4, 0.02)
        med = np.array([np.median(rad[leg & (np.abs(t - x) < 0.03)]) if (leg & (np.abs(t - x) < 0.03)).sum() >= 15
                        else np.nan for x in ts])
        ok = ~np.isnan(med)
        if ok.sum() < 10:
            info[f"shorts{S}"] = "leg profile too sparse"
            continue
        med = np.interp(ts, ts[ok], med[ok])
        step = np.full(len(ts), -1.0)
        for i in range(3, len(ts) - 3):
            above, below = med[i - 3:i].mean(), med[i + 1:i + 4].mean()
            if 0.35 <= ts[i] <= 1.35 and above > below * 1.15:
                step[i] = above - below
        if step.max() <= 0:
            info[f"shorts{S}"] = "no hem drop found"
            continue
        ih = int(step.argmax())
        th = float(ts[ih])
        r_short = float(med[max(0, ih - 4):ih - 1].mean())
        r_leg = float(med[ih + 2:ih + 5].mean())
        if r_short < SHORTS_RATIO * r_leg or r_short - r_leg < SHORTS_DROP * H:   # a thigh tapering to the knee
            info[f"shorts{S}"] = {"no hem drop": {"r_above": round(r_short, 4), "r_below": round(r_leg, 4)}}
            continue
        ah = th * L
        info[f"shorts{S}"] = {"t": round(th, 3), "z": round(float((hip + u * ah)[2]), 4),
                              "r_shorts": round(r_short, 4), "r_leg": round(r_leg, 4)}
        fwd = np.array([0, -1.0, 0]) - u * (u @ np.array([0, -1.0, 0]))
        fwd /= np.linalg.norm(fwd)
        outv = np.cross(u, fwd) * (-1)          # +x for the left leg
        if outv[0] * sgn < 0:
            outv = -outv
        az = np.degrees(np.arctan2(radial @ outv, radial @ fwd))      # 0 front, 90 outer
        top_off = 0.035 * H
        band = leg & (a > ah - top_off - 0.006 * H) & (a < ah + 0.006 * H) & (rad > (r_short + r_leg) / 2)
        anchors = [(0, True), (90, True), (180, True), (270, False)]
        names = [("F", 0), ("O", 90), ("B", 180)]
        bw = ring_blend(az[band], anchors)
        idx = np.where(band)[0]
        for i, (tag, ang) in enumerate(names):
            nm = f"shorts{S}{tag}"
            if nm in skip:
                continue
            d = ((az - ang + 180) % 360) - 180
            sec = leg & (np.abs(d) < 35)
            def surf(ax, q):
                m = sec & (np.abs(a - ax) < 0.008 * H)
                return float(np.quantile(rad[m], q)) if m.sum() >= 5 else None
            rt, rb = surf(ah - top_off, 0.5), surf(ah - 0.004 * H, 0.5)
            if rt is None or rb is None:
                continue
            dirv = fwd * math.cos(math.radians(ang)) + outv * math.sin(math.radians(ang))
            j0 = hip + u * (ah - top_off) + dirv * (rt - 0.005 * H)
            j1 = hip + u * ah + dirv * (rb - 0.004 * H)
            frac = (a[idx] - (ah - top_off)) / top_off
            s = KINDS["shorts_hem"]["s_max"] * smoothstep(frac / 0.8) * bw[:, i]
            share = np.zeros((len(co), 1))
            share[idx, 0] = s
            out.append(chain_dict(nm, "shorts_hem", np.array([j0, j1]), share, ul,
                                  list(fam), side=S.lower(), az=ang, ring=f"shorts{S}"))
    hems = {S: info[f"shorts{S}"]["z"] for S in ("L", "R") if "z" in (info.get(f"shorts{S}") or {})}
    if len(hems) == 1 or (len(hems) == 2 and abs(hems["L"] - hems["R"]) > SHORTS_PAIR * H):
        # shorts end on both legs at one height; a drop on one leg alone is a skirt's or a coat's hem
        info["shorts"] = {"unpaired": {S: round(z, 4) for S, z in hems.items()}, "dropped": [c["name"] for c in out]}
        out = []
    return out, info


def outer_envelope(d, r, mask, bin_deg=2.0, eps=0.01):
    """The skin of `mask` seen from the centre: within eps of the farthest skin in its direction (bins of
    about bin_deg on the sphere). A lock's flanks are on it; the rim and the hair under a cap's crown are not."""
    idx = np.where(mask)[0]
    th = np.degrees(np.arccos(np.clip(d[idx, 2], -1, 1)))
    ph = np.degrees(np.arctan2(d[idx, 1], d[idx, 0])) + 180
    key = np.floor(th / bin_deg).astype(int) * 1000 + np.floor(ph * np.maximum(np.sin(np.radians(th)), 0.05) /
                                                               bin_deg).astype(int)
    _, inv = np.unique(key, return_inverse=True)
    far = np.zeros(inv.max() + 1 if len(inv) else 0)
    np.maximum.at(far, inv, r[idx])
    out = np.zeros(len(d), bool)
    out[idx] = r[idx] >= far[inv] * (1 - eps)
    return out


def detect_hair(body, taken, max_chains=6):
    co, H = body.co, body.H
    head = body.in_parts(("Head",)) & ~taken
    if head.sum() < 200:
        return [], {"hair": "no head skin"}
    p = co[head] if body.around is None else np.vstack([co[head], body.around])   # hair object: skull too
    c = (p.min(0) + p.max(0)) / 2
    face = unit(np.array([0, -1.0, -0.6]))
    v = co - c
    r = np.linalg.norm(v, axis=1)
    d = unit(v)
    cap = head & (d @ face < math.cos(math.radians(55))) & (co[:, 2] > c[2] - 0.35 * (p[:, 2].max() - c[2]))
    if cap.sum() < 100:
        return [], {"hair": "no hair cap"}
    tips = cap & (r > np.quantile(r[cap], 0.8))
    ew = body.edges[cap[body.first[body.edges[:, 0]]] & cap[body.first[body.edges[:, 1]]]]
    step = np.median(np.linalg.norm(co[body.first[ew[:, 0]]] - co[body.first[ew[:, 1]]], axis=1)) if len(ew) else 0.0
    outer = outer_envelope(d, r, cap, bin_deg=max(2.0, 1.5 * math.degrees(step / max(np.median(r[cap]), 1e-9))))
    D = d[tips]
    # deterministic k-means on directions, farthest-point initialisation from the top
    centres = [D[np.argmax(D[:, 2])]]
    while len(centres) < max_chains:
        sim = np.max(D @ np.array(centres).T, axis=1)
        centres.append(D[np.argmin(sim)])
    C = np.array(centres)
    for _ in range(20):
        lab = np.argmax(D @ C.T, axis=1)
        C = np.array([unit(D[lab == k].mean(0)) if (lab == k).any() else C[k] for k in range(len(C))])
    # merge clusters closer than 25 degrees, drop tiny ones
    keep = []
    for k in np.argsort([-(lab == k).sum() for k in range(len(C))]):
        if (lab == k).sum() < 0.03 * len(D):
            continue
        if all(C[k] @ C[j] < math.cos(math.radians(25)) for j in keep):
            keep.append(k)
    C = C[keep]
    lab = np.argmax(d[cap] @ C.T, axis=1)
    info = {"hair_centre": r6(c), "hair_cap": int(cap.sum()), "hair_tips": int(tips.sum()), "clusters": len(C)}
    out = []
    cap_idx = np.where(cap)[0]
    ang = np.degrees(np.arccos(np.clip(d[cap] @ C.T, -1, 1)))         # cap x clusters
    # soft assignment to the two nearest cluster directions
    order = np.argsort(ang, axis=1)
    a1 = ang[np.arange(len(ang)), order[:, 0]]
    a2 = ang[np.arange(len(ang)), order[:, 1]] if len(C) > 1 else np.full(len(ang), 180.0)
    w1 = np.where(len(C) > 1, a2 / np.maximum(a1 + a2, 1e-9), 1.0)
    W = np.zeros_like(ang)
    W[np.arange(len(ang)), order[:, 0]] = w1
    if len(C) > 1:
        W[np.arange(len(ang)), order[:, 1]] = 1 - w1
    for k in range(len(C)):
        near = ang[:, k] < 40
        members = cap_idx[(lab == k) & near]
        if len(members) < 50:
            continue
        r_tip = float(np.quantile(r[members], 0.95))
        r_root = float(np.quantile(r[cap_idx[near]], 0.25))
        if r_tip - r_root < 0.012 * H:
            continue
        nb = 2 if r_tip - r_root > 0.04 * H else 1
        js = [c + C[k] * (r_root + (r_tip - r_root) * f) for f in np.linspace(0, 1, nb + 1)]
        radial = (r[cap_idx] - r_root) / (r_tip - r_root)
        s = KINDS["hair"]["s_max"] * smoothstep(radial / 0.7) * W[:, k] * (1 - smoothstep((ang[:, k] - 30) / 20))
        share1 = np.zeros(len(co))
        share1[cap_idx] = s
        region = share1 > 1e-4
        sides = float((np.abs((body.nrm[region] * d[region]).sum(1)) < 0.5).mean()) if region.any() else 0.0
        info.setdefault("hair_sides", []).append(round(sides, 3))
        if sides < SPIKE_SIDES:      # a smooth skull or a bun: no spike sides, nothing to swing
            continue
        env = region & outer        # weighted by the share: the lock itself, not the bare skull between locks
        osides = float((share1[env] * (np.abs((body.nrm[env] * d[env]).sum(1)) < OUTER_SIDE)).sum() /
                       max(share1[env].sum(), 1e-12)) if env.any() else 0.0
        info.setdefault("hair_outer_sides", []).append(round(osides, 3))
        if osides < SPIKE_OUTER:     # its outer skin is a smooth dome: a cap's or a helmet's crown, rigid on Head
            info.setdefault("hair_rejected", []).append({"dir": r6(C[k]), "outer_sides": round(osides, 3),
                                                         "why": "crown"})
            continue
        own = body.nrm[members][np.abs((body.nrm[members] * d[members]).sum(1)) < 0.5]   # its own skin, not a neighbour's
        plate = float(np.linalg.eigvalsh(own.T @ own / len(own))[-1]) if len(own) else 0.0   # the main normal axis's share
        info.setdefault("hair_plate", []).append(round(plate, 3))
        if plate > SPIKE_PLATE:      # its sides face one way: a cap brim or a visor, not a lock of hair
            info.setdefault("hair_rejected", []).append({"dir": r6(C[k]), "plate": round(plate, 3)})
            continue
        u, _ = polyline_u(co[region], js)
        u = np.clip(radial[np.isin(cap_idx, np.where(region)[0])], 0, 1)
        split = split_bones(u, js)
        share = np.zeros((len(co), nb))
        share[region] = share1[region][:, None] * split
        out.append(chain_dict(f"hair{len(out) + 1}", "hair", np.array(js), share, "Head",
                              source_bones(body, ["Head", "Neck"]), centre=c.tolist(), r_root=r_root))
    return out, info


def marker_chain(body, m, taken):
    kind = m["kind"]
    joints = np.array(m["joints"], float)
    allowed = {"hood": TORSO, "bag": TORSO, "hem": ("Hips", "Spine", "Chest", "UpperLeg.L", "UpperLeg.R"),
               "hair": PONYTAIL, "strap": TORSO}.get(kind, TORSO)
    if kind == "shorts_hem":
        S = "L" if joints[0][0] > 0 else "R"
        allowed = (f"UpperLeg.{S}", f"LowerLeg.{S}")
    rr = float(m.get("region_radius", 0.03 * body.H))
    ok = body.in_parts(allowed) & ~taken
    u, dist = polyline_u(body.co, joints)
    feather = np.where(ok, np.clip(1 - dist / rr, 0, 1), 0) ** 0.5
    region = feather > 0
    parents = {"hood": ["Neck", "UpperChest"], "bag": ["Spine", "Hips"], "hem": ["Hips", "Spine"],
               "hair": ["Head"], "strap": ["UpperChest", "Chest"]}.get(kind, list(allowed))
    sources = {"hood": ["UpperChest", "Neck", "Chest"], "bag": ["Hips", "Spine", "Chest", "UpperChest"],
               "hem": ["Hips", "Spine", "Chest"], "hair": list(PONYTAIL),
               "strap": ["UpperChest", "Chest", "Spine"]}.get(kind, list(allowed))
    ramp = 0.0001 if kind == "strap" else 0.35
    ch = finish_chain(body, m["name"], kind, joints, region, feather, ramp, parents, sources,
                      side=m.get("side", "x"), marker=True)
    if kind == "strap":   # a mid-sag bone: share peaks mid-span, zero at both fixed ends
        ch["share"][region] *= (np.sin(np.pi * u[region]) ** 2)[:, None]
    return ch


def detect_all(body, kinds, markers=None, required=(), skirt=None):
    """Chains for `kinds` (and every marker chain); `missing` lists the `required` kinds not found. `skirt`
    (the markers' skirt block): the hem is the skirt's, and no shorts hem is searched."""
    markers = markers or {}
    skip = set(markers.get("skip", []))
    mk = {m["name"]: m for m in markers.get("chains", [])}
    taken = np.zeros(len(body.co), bool)
    chains, info, missing = [], {}, []

    rings = {}     # chains blended round one ring (a hem, a skirt's hem, one leg's shorts) share their skin

    def take(ch):
        reg = ch["share"].sum(1) > 0
        ring = ch.get("ring")
        ch["region"] = reg & ~(taken & ~rings[ring]) if ring in rings else reg & ~taken
        ch["share"][~ch["region"]] = 0
        if ch["region"].sum() < 20:
            info.setdefault("dropped_empty", []).append(ch["name"])
            return False
        if ch["kind"] == "hair" and not ch.get("marker"):     # a spike too small for 50 per bone stays rigid
            live = ch["share"].sum(1) >= 0.002
            if min(int(((ch["share"][:, j] > 1e-4) & live).sum()) for j in range(ch["share"].shape[1])) < 50:
                info.setdefault("dropped_small", []).append(ch["name"])
                return False
        taken[ch["region"]] = True
        if ring:
            rings[ring] = rings.get(ring, np.zeros(len(taken), bool)) | ch["region"]
        chains.append(ch)
        return True

    by_kind = {k: [m for m in mk.values() if m["kind"] == k] for k in KINDS}
    hood_core = bag_core = None
    back_info = {}
    if {"hood", "bag"} & set(kinds) and not (by_kind["hood"] and by_kind["bag"]):
        hood_core, bag_core, back_info = back_regions(body, taken)
        info["back"] = {k: v for k, v in back_info.items() if not isinstance(v, np.ndarray)}
        if skirt and bag_core is not None:   # a long coat's or a cape's own drape bulging off the back is no bag
            if HERE not in sys.path:
                sys.path.insert(0, HERE)
            import arp_markers
            inside = float((bag_core & arp_markers.skirt_region(body.co, skirt)).sum() / max(bag_core.sum(), 1))
            if inside >= 0.5:
                info["back"].setdefault("rejected", []).append(
                    {"vertices": int(bag_core.sum()), "skirt_share": round(inside, 3),
                     "why": "bag: the coat's or cape's own skin (the skirt region)"})
                bag_core = None
    for kind in PRIORITY:
        if kind not in kinds and not by_kind.get(kind):
            continue
        found = []
        for m in by_kind.get(kind, []):
            if take(marker_chain(body, m, taken)):
                found.append(m["name"])
        if kind in kinds and not by_kind.get(kind):
            if kind == "bag" and "bag" not in skip:
                if bag_core is not None:
                    ch = detect_bag(body, bag_core & ~taken, back_info, taken)
                    if ch and take(ch):
                        found.append(ch["name"])
                sides, info["side_bag"] = side_regions(body, taken)
                for S, core, _ in sides:
                    if f"bag{S}" not in skip and take(detect_side_bag(body, S, core & ~taken, taken)):
                        found.append(f"bag{S}")
            elif kind == "hood" and hood_core is not None and "hood" not in skip:
                ch = detect_hood(body, hood_core & ~taken, back_info, taken)
                if ch:
                    if take(ch):
                        found.append(ch["name"])
            elif kind == "hair":
                cs, i = detect_hair(body, taken)
                info.update(i)
                for ch in cs:
                    if ch["name"] not in skip:
                        if take(ch):
                            found.append(ch["name"])
            elif kind == "hem":
                cs, i = detect_skirt_hem(body, taken, skirt, skip) if skirt else detect_hem(body, taken, skip)
                info.update(i)
                for ch in cs:
                    if take(ch):
                        found.append(ch["name"])
            elif kind == "shorts_hem" and skirt:
                cs, i = [], {"shorts": "not searched: a skirt covers the thighs (--skirt)"}
            elif kind == "shorts_hem":
                cs, i = detect_shorts(body, taken, skip)
                info.update(i)
                for ch in cs:
                    if take(ch):
                        found.append(ch["name"])
            elif kind == "strap":
                info["strap"] = ("not chained: fixed at both ends; a marker chain of kind strap adds one "
                                 "stiff mid-sag bone")
        need = 4 if kind == "hem" else 1
        if kind in required and len(found) < need:
            missing.append(kind)
        info.setdefault("found", {})[kind] = found
    for ch in chains:
        if ch["parent"] is None:
            ch["parent"] = "Hips"
        ch["parent_bone"] = body.bone(ch["parent"])
    return chains, info, missing


# ----------------------------------------------------------------------------- weights

def apply_shares(body, chains, limit=4):
    """New dense weights (vertices x [deform bones + chain bones]); the share is taken from the
    chain's parent first, then from its other source bones in proportion."""
    W = body.W.astype(np.float64).copy()
    cols = list(body.names)
    extra = {}
    for ch in chains:
        for b in ch["bones"][:-1]:
            extra[b] = len(cols)
            cols.append(b)
    W = np.concatenate([W, np.zeros((len(W), len(extra)))], 1)
    deform_n = len(body.names)
    stats = {}
    for ch in chains:
        tiny = ch["region"] & (ch["share"].sum(1) < 0.002)     # feather noise: no chain weight there
        ch["share"][tiny] = 0
        ch["region"] = ch["region"] & ~tiny
        reg = np.where(ch["region"])[0]
        share = ch["share"][reg]                     # region x bones
        want = share.sum(1)
        pcol = body.col[ch["parent_bone"]]
        scols = [body.col[b] for b in ch["sources"] if b in body.col and body.col[b] != pcol]
        wp = W[reg, pcol]
        from_p = np.minimum(want, wp)
        W[reg, pcol] -= from_p
        rest = want - from_p
        if scols:
            ws = W[np.ix_(reg, scols)]
            tot = ws.sum(1)
            take = np.minimum(rest, tot)
            frac = np.where(tot > 0, take / np.maximum(tot, 1e-12), 0)
            W[np.ix_(reg, scols)] = ws * (1 - frac[:, None])
        else:
            take = np.zeros_like(rest)
        got = from_p + take
        scale = np.where(want > 0, got / np.maximum(want, 1e-12), 0)
        for j, b in enumerate(ch["bones"][:-1]):
            W[reg, extra[b]] += share[:, j] * scale
        stats[ch["name"]] = {"vertices": int((got > 1e-4).sum()), "share_max": round(float(got.max()), 3) if len(got) else 0.0,
                             "from_parent": round(float(from_p.sum() / max(got.sum(), 1e-9)), 3)}
    # at most `limit` weights, resolved in the order that changes the body's own deformation least:
    #  1 merge the smaller of two chain weights into the larger (spring only),
    #  2 move the smallest other source weight into the chain's parent (same body part),
    #  3 move the parent's remainder into the chain bone (its rigid child: same body deformation),
    #  4 drop the smallest body weight and rescale the rest (counted; limb bones lose last)
    touched = np.zeros(len(W), bool)
    for ch in chains:
        touched |= ch["region"]
    W[(W < 1e-5) & touched[:, None]] = 0
    owner = {}
    for ch in chains:
        for b in ch["bones"][:-1]:
            owner[extra[b]] = ch
    nnz = (W > 1e-9).sum(1)
    steps = [0, 0, 0, 0, 0]
    W0 = body.W.astype(np.float64)
    for i in np.where(nnz > limit)[0]:
        row = W[i]
        if row[deform_n:].sum() < 0.05:              # a faint edge share is not worth a body change
            row[:] = 0
            row[:deform_n] = W0[i]
            for ch in chains:
                ch["region"][i] = False
                ch["share"][i] = 0
            steps[4] += 1
            continue
        over = lambda: int((row > 1e-9).sum()) - limit
        cc = [j for j in range(deform_n, len(cols)) if row[j] > 1e-9]
        hung = {owner[j]["parent_bone"] for j in cc}
        if over() > 0 and len(cc) > 1 and len(hung) > 1:
            # chains of one ring hung from different bones (a skirt's, from each thigh): merge only within one
            # parent, then each parent's remainder into its own chain (its rigid child): the body moves as before
            for pb in hung:
                same = sorted((j for j in cc if owner[j]["parent_bone"] == pb), key=lambda j: row[j])
                while over() > 0 and len(same) > 1:
                    j = same.pop(0)
                    row[same[-1]] += row[j]
                    row[j] = 0
                    steps[0] += 1
            for pb in hung:
                pc = body.col[pb]
                live = [j for j in cc if owner[j]["parent_bone"] == pb and row[j] > 1e-9]
                if over() > 0 and live and row[pc] > 1e-9:
                    row[max(live, key=lambda j: row[j])] += row[pc]
                    row[pc] = 0
                    steps[2] += 1
            cc = [j for j in cc if row[j] > 1e-9]
        if over() > 0 and len(cc) > 1 and len(hung) == 1:
            cc.sort(key=lambda j: row[j])
            while over() > 0 and len(cc) > 1:
                j = cc.pop(0)
                row[cc[-1]] += row[j]
                row[j] = 0
            steps[0] += 1
        ch = owner[max((j for j in range(deform_n, len(cols)) if row[j] > 1e-9), key=lambda j: row[j])]
        pcol = body.col[ch["parent_bone"]]
        srcs = sorted((body.col[b] for b in ch["sources"] if b in body.col and body.col[b] != pcol
                       and row[body.col[b]] > 1e-9), key=lambda j: row[j])
        if over() > 0 and srcs:
            while over() > 0 and srcs:
                j = srcs.pop(0)
                row[pcol] += row[j]
                row[j] = 0
            steps[1] += 1
        if over() > 0 and row[pcol] > 1e-9:
            jc = max((j for j in range(deform_n, len(cols)) if row[j] > 1e-9), key=lambda j: row[j])
            row[jc] += row[pcol]
            row[pcol] = 0
            steps[2] += 1
        if over() > 0:
            body_idx = [j for j in np.argsort(row) if row[j] > 1e-9 and j < deform_n]
            chain_sum = row[deform_n:].sum()
            for j in body_idx[:over()]:
                row[j] = 0
            bs = row[:deform_n].sum()
            if bs > 0:
                row[:deform_n] *= (1 - chain_sum) / bs
            steps[3] += 1
    trimmed = {"merged_chains": steps[0], "source_into_parent": steps[1], "parent_into_chain": steps[2],
               "dropped_body_weight": steps[3], "faint_share_reverted": steps[4]}
    touched = np.zeros(len(W), bool)
    for ch in chains:
        touched |= ch["region"]
    s = W[touched].sum(1, keepdims=True)
    W[touched] = np.where(s > 0, W[touched] / np.maximum(s, 1e-12), W[touched])   # untouched rows stay bit-identical
    return W, cols, extra, dict(stats, _limit=trimmed)


# ----------------------------------------------------------------------------- Blender side

def read_body(rig, me, roles):
    mw = np.array(me.matrix_world)
    n = len(me.data.vertices)
    co = np.empty(n * 3, np.float32)
    me.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]
    nrm = np.empty(n * 3, np.float32)
    me.data.vertices.foreach_get("normal", nrm)
    nrm = unit(nrm.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T)
    ed = np.empty(len(me.data.edges) * 2, np.int32)
    me.data.edges.foreach_get("vertices", ed)
    deform = [b.name for b in rig.data.bones if b.use_deform and not b.name.startswith("cc_")]
    W = read_weights(me, deform)
    rmw = rig.matrix_world
    heads = [list(rmw @ rig.data.bones[b].head_local) for b in deform]
    tails = [list(rmw @ rig.data.bones[b].tail_local) for b in deform]
    return Body(co, ed.reshape(-1, 2), nrm, W, deform, heads, tails, roles)


def read_weights(me, names):
    gidx = {g.name: i for i, g in enumerate(me.vertex_groups)}
    col = {gidx[b]: j for j, b in enumerate(names) if b in gidx}
    W = np.zeros((len(me.data.vertices), len(names)))
    for v in me.data.vertices:
        for g in v.groups:
            j = col.get(g.group)
            if j is not None:
                W[v.index, j] = g.weight
    return W


def add_bones(rig, chains, H):
    inv = rig.matrix_world.inverted()
    bpy.context.view_layer.objects.active = rig
    for o in bpy.context.selected_objects:
        o.select_set(False)
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = rig.data.edit_bones
    for b in [b for b in eb if b.name.startswith("cc_")]:
        eb.remove(b)                                            # re-runnable: rebuild from clean
    for ch in chains:
        prev = eb[ch["parent_bone"]]
        J = [Vector(j) for j in ch["joints"]]
        for i in range(len(J) - 1):
            b = eb.new(ch["bones"][i])
            b.head, b.tail = inv @ J[i], inv @ J[i + 1]
            b.parent, b.use_connect, b.use_deform = prev, i > 0, True
            prev = b
        d = (J[-1] - J[-2]).normalized() * max(0.25 * (J[-1] - J[-2]).length, 0.004 * H)
        t = eb.new(ch["bones"][-1])
        t.head, t.tail = inv @ J[-1], inv @ (J[-1] + d)
        t.parent, t.use_connect, t.use_deform = prev, True, True
    bpy.ops.object.mode_set(mode='OBJECT')


def write_weights(me, W, cols, body):
    old = body.W
    deform_n = len(body.names)
    changed = np.where((np.abs(W[:, :deform_n] - old) > 0).any(1) | (W[:, deform_n:] > 0).any(1))[0]
    groups = {}

    def group(j):     # made only when a weight needs it: a rigid hair object gets no empty groups
        if j not in groups:
            groups[j] = me.vertex_groups.get(cols[j]) or me.vertex_groups.new(name=cols[j])
        return groups[j]
    for i in changed:
        i = int(i)
        for j in range(len(cols)):
            w = float(W[i, j])
            if w > 0:
                group(j).add([i], w, 'REPLACE')
            elif j < deform_n and old[i, j] > 0:
                group(j).remove([i])
    return len(changed)


def pose_leak(rig, meshes, chains, angle=25.0):
    """Turn each chain's bones and measure how far skin outside its region moves: on the mesh the
    chain is weighted on (`meshes[chain["on"]]`) outside its region, on every other mesh anywhere."""
    dg = bpy.context.evaluated_depsgraph_get()

    def positions(me):
        ev = me.evaluated_get(dg)
        m = ev.to_mesh()
        a = np.empty(len(m.vertices) * 3, np.float32)
        m.vertices.foreach_get("co", a)
        ev.to_mesh_clear()
        return a.reshape(-1, 3).astype(np.float64)
    dg.update()
    rest = {t: positions(me) for t, me in meshes.items()}
    out = {}
    for ch in chains:
        pbs = [rig.pose.bones[b] for b in ch["bones"][:-1]]
        for pb in pbs:
            pb.rotation_mode = 'QUATERNION'
            pb.rotation_quaternion = Quaternion((1, 0, 0), math.radians(angle))
        dg.update()
        worst, inside = 0.0, 0.0
        for t, me in meshes.items():
            moved = np.linalg.norm(positions(me) - rest[t], axis=1)
            own = ch.get("on", "body") == t
            outside = ~ch["region"] if own else np.ones(len(moved), bool)
            if outside.any():
                worst = max(worst, float(moved[outside].max()))
            if own and ch["region"].any():
                inside = float(moved[ch["region"]].max())
        for pb in pbs:
            pb.rotation_quaternion = (1, 0, 0, 0)
        out[ch["name"]] = {"outside_max": worst, "inside_max": inside}
    dg.update()
    return out


def export_fbx(rig, fbx):
    sys.dont_write_bytecode = True
    if not os.path.isfile(os.path.join(BRT, "brt_arp.py")):
        raise Refused(f"--fbx needs blender-retarget beside this skill ({BRT}/brt_arp.py)")
    if BRT not in sys.path:
        sys.path.insert(0, BRT)
    import brt_arp
    return brt_arp.run({"op": "export", "armature": rig.name, "fbx": fbx, "acknowledge_destructive": True})


def reimport_check(fbx, chains, sources):
    """sources: {tag: (body, weights, cols)}; each re-imported mesh is read against the source nearest it
    (the body, or a separate hair), and a cc_ weight on a mesh its chain is not on counts as outside."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=fbx)
    objs = [o for o in bpy.data.objects if o not in before]
    try:
        arm = next(o for o in objs if o.type == 'ARMATURE')
        meshes = [o for o in objs if o.type == 'MESH']
        bones = {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}
        missing, wrong_parent = [], []
        for ch in chains:
            prev = ch["parent_bone"]
            for b in ch["bones"]:
                if b not in bones:
                    missing.append(b)
                elif bones[b] != prev:
                    wrong_parent.append([b, bones[b], prev])
                prev = b
        cc = [b for ch in chains for b in ch["bones"][:-1]]
        outside, mismatch, counted = 0, 0.0, {b: 0 for b in cc}
        unmatched = 0
        chain_of = {b: ch for ch in chains for b in ch["bones"][:-1]}
        for m in meshes:
            n = len(m.data.vertices)
            co = np.empty(n * 3, np.float32)
            m.data.vertices.foreach_get("co", co)
            mw = np.array(m.matrix_world)
            co = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
            probe = co[:: max(1, n // 500)]
            tag = min(sources, key=lambda t: float(np.median(nearest_dist(sources[t][0].co, probe))))
            src, W_new, cols = sources[tag]
            idx, dist = nearest_index(src.co, co)
            gi = {g.index: g.name for g in m.vertex_groups}
            for v in m.data.vertices:
                for g in v.groups:
                    name = gi.get(g.group)
                    if name in chain_of and g.weight > 1e-4:
                        k = idx[v.index]
                        if dist[v.index] > 1e-3:
                            unmatched += 1
                            continue
                        counted[name] += 1
                        ch = chain_of[name]
                        if ch.get("on", "body") != tag or not ch["region"][k]:
                            outside += 1
                            continue
                        mismatch = max(mismatch, abs(g.weight - W_new[k, cols.index(name)]))
        return {"bones": len(bones), "missing": missing, "wrong_parent": wrong_parent, "outside_region": outside,
                "weight_mismatch_max": round(float(mismatch), 5), "unmatched": unmatched, "weighted": counted}
    finally:
        for o in objs:
            data = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Armature):
                bpy.data.armatures.remove(data)


# ----------------------------------------------------------------------------- colliders

COLLIDERS = [  # name, shape, role a, role b, parts measured
    ("Hips", "capsule", "UpperLeg.L", "UpperLeg.R", ("Hips",)),
    ("Spine", "capsule", "Spine", "Chest", ("Spine", "Hips")),
    ("Chest", "capsule", "Chest", "UpperChest", ("Chest", "Spine")),
    ("UpperChest", "capsule", "UpperChest", "Neck", ("UpperChest", "Chest")),
    ("Head", "sphere", "Head", None, ("Head",)),
    ("UpperLeg.L", "capsule", "UpperLeg.L", "LowerLeg.L", ("UpperLeg.L",)),
    ("UpperLeg.R", "capsule", "UpperLeg.R", "LowerLeg.R", ("UpperLeg.R",)),
    ("LowerLeg.L", "capsule", "LowerLeg.L", "Foot.L", ("LowerLeg.L",)),
    ("LowerLeg.R", "capsule", "LowerLeg.R", "Foot.R", ("LowerLeg.R",)),
]


def size_colliders(body, chains, heads):
    """Radii from the skin around each collider (exported bone origins), then shrunk so no chain
    joint below its root starts inside a collider of its group."""
    cols, report = {}, {"shrunk": [], "dropped": []}
    hair = [c for c in chains if c["kind"] == "hair" and "centre" in c]   # detected; a marker chain has no centre
    for name, shape, ra, rb, parts in COLLIDERS:
        a = body.bone(ra)
        b = body.bone(rb) if rb else None
        if a not in heads or (rb and b not in heads):
            continue
        A = np.asarray(heads[a])
        skin = body.in_parts(parts)
        if shape == "sphere":
            centre = np.asarray(hair[0]["centre"]) if hair else body.co[skin].mean(0)
            d = np.linalg.norm(body.co[skin] - centre, axis=1)
            radius = float(np.quantile(d, 0.2))
            if hair:
                radius = min(radius, min(c["r_root"] for c in hair))
            cols[name] = dict(name=name, shape="sphere", a=a, a_role=HUMAN.get(ra, ra), center=r6(centre),
                              radius=radius, _A=centre, _B=centre)
            continue
        B = np.asarray(heads[b])
        t, d = seg_project(body.co[skin], A, B)
        mid = (t > 0.15) & (t < 0.85)
        if mid.sum() < 20:
            continue
        radius = float(np.quantile(d[mid], 0.3))
        inset = 0.1 if name.startswith("UpperLeg") else 0.0
        cols[name] = dict(name=name, shape="capsule", a=a, b=b, a_role=HUMAN.get(ra, ra), b_role=HUMAN.get(rb, rb),
                          inset=inset, radius=radius, _A=A + (B - A) * inset, _B=B - (B - A) * inset)
    for ch in chains:
        group = list(KINDS[ch["kind"]]["colliders"])
        if ch["kind"] == "shorts_hem":       # the other thigh, and its own (shrunk off the hem's joints)
            left = ch["joints"][0][0] > 0                                   # +X is the left side
            group = ["UpperLeg." + ("R" if left else "L"), "UpperLeg." + ("L" if left else "R")]
        ch["colliders"] = [g for g in group if g in cols]
    for _ in range(2):
        for ch in chains:
            pr = KINDS[ch["kind"]]["radius"] * body.H
            for g in list(ch["colliders"]):
                c = cols[g]
                for j in np.asarray(ch["joints"])[1:]:
                    _, d = seg_project(j[None, :], c["_A"], c["_B"])
                    if d[0] < c["radius"] + pr:
                        new = float(d[0] - pr - 0.002)
                        if new < 0.5 * c.get("_orig", c["radius"]) or new <= 0.005:
                            ch["colliders"].remove(g)
                            report["dropped"].append([ch["name"], g])
                            break
                        c.setdefault("_orig", c["radius"])
                        report["shrunk"].append([g, round(c["radius"], 4), round(new, 4), ch["name"]])
                        c["radius"] = new
    z_neck = body.head("Neck")[2] if body.bone("Neck") else -np.inf
    for ch in chains:     # a hood, or hair hanging below the neck (a ponytail), rests on the back
        if ch["kind"] == "hood" or (ch["kind"] == "hair" and min(j[2] for j in ch["joints"]) < z_neck):
            back_sphere(body, ch, cols, heads, report)
    inside = 0
    for ch in chains:
        pr = KINDS[ch["kind"]]["radius"] * body.H
        for g in ch["colliders"]:
            c = cols[g]
            for j in np.asarray(ch["joints"])[1:]:
                _, d = seg_project(j[None, :], c["_A"], c["_B"])
                inside += int(d[0] < c["radius"] + pr - 1e-6)
    return cols, report, inside


def back_sphere(body, ch, cols, heads, report):
    """A hood rests on the back, inside the torso capsules, which shrinking drops from its group. This gives it a
    large sphere on the UpperChest bone, its centre in front, whose surface runs just under the chain's rest joints
    below the root: through the first and the last of them less their particle radius + 2 mm (a middle one under
    it moves the sphere forward). The hood cannot sink into the back further than it rests, and nothing starts
    inside it."""
    a = body.bone("UpperChest")
    J = np.asarray(ch["joints"], float)[1:]
    if a not in heads or not len(J):
        return
    pr, R = KINDS[ch["kind"]]["radius"] * body.H, BACK_SPHERE * body.H
    q = J[:, 1:] - [pr + 0.002, 0.0]                     # (y, z) of each joint, its particle radius in front
    a_, b_ = q[0], q[-1]
    half = 0.5 * float(np.linalg.norm(b_ - a_))
    if half > 1e-6:                                        # the surface through the first and the last
        t = (b_ - a_) / (2 * half)
        n = np.array([-t[1], t[0]])
        n = n if n[0] < 0 else -n                          # toward the front (-Y)
        c = 0.5 * (a_ + b_) + n * np.sqrt(max(R * R - half * half, 0.0))
    else:
        c = a_ + np.array([-R, 0.0])
    for _ in range(20):                                    # a joint under the surface: move it forward
        reach = float((np.linalg.norm(J[:, 1:] - c, axis=1) - (R + pr + 0.002)).min())
        if reach >= 0:
            break
        c = c + np.array([reach - 1e-4, 0.0])
    centre = np.array([J[:, 0].mean(), c[0], c[1]])
    name = "Back" if "Back" not in cols else f"Back.{ch['name']}"
    cols[name] = dict(name=name, shape="sphere", a=a, a_role=HUMAN.get("UpperChest"), center=r6(centre), radius=R,
                      _A=centre, _B=centre)
    ch["colliders"].append(name)
    report.setdefault("added", []).append([name, ch["name"]])


def secondary_json(name, chains, cols, heads, stats):
    out_chains = []
    for ch in chains:
        k = KINDS[ch["kind"]]
        out_chains.append({
            "name": ch["name"], "kind": ch["kind"], "parent": ch["parent_bone"],
            "parent_role": HUMAN.get(ch["parent"], ch["parent"]), "bones": ch["bones"],
            "joints": [r6(j) for j in ch["joints"]],
            "parent_head": r6(heads[ch["parent_bone"]]) if ch["parent_bone"] in heads else None,
            "radius": round(k["radius"] * stats["H"], 4), "stiffness": k["stiffness"], "drag": k["drag"],
            "gravity": k["gravity"], "wind": k["wind"], "inertia": k["inertia"],
            "max_angle_deg": k["max_angle_deg"], "colliders": ch.get("colliders", []),
            "weighted_vertices": int(stats["weighted"].get(ch["name"], 0))})
        if out_chains[-1]["parent_head"] is None:
            del out_chains[-1]["parent_head"]
    out_cols = []
    for c in cols.values():
        d = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in c.items() if not k.startswith("_")}
        if d.get("inset") == 0.0:
            del d["inset"]
        out_cols.append(d)
    return {"schema": "secondary/1", "tool": TOOL,
            "producer": {"skill": "character-autorig", "script": TOOL},
            "character": name, "units": "m", "up": "+Z", "forward": "-Y",
            "chains": out_chains, "colliders": out_cols}


# ----------------------------------------------------------------------------- renders

PALETTE = [(0.95, 0.35, 0.1), (0.1, 0.55, 0.95), (0.95, 0.8, 0.1), (0.6, 0.2, 0.9), (0.1, 0.8, 0.4),
           (0.95, 0.2, 0.55), (0.3, 0.85, 0.9), (0.85, 0.5, 0.95), (0.55, 0.75, 0.15), (1.0, 0.6, 0.6)]


def render_set(out_dir, prefix, me, chains, views, mode, W=None, cols=None, size=900, focus=None, keep=None):
    """Workbench renders: mode 'texture' (the mesh's own material), 'regions' (vertex colours per
    chain, brighter = more share) with the chain bones drawn as rods over the mesh."""
    scene = bpy.context.scene
    render, shading = scene.render, scene.display.shading
    saved = (render.engine, render.resolution_x, render.resolution_y, render.filepath, scene.camera,
             shading.light, shading.color_type, render.film_transparent)
    added, attr = [], None
    hidden = [o for o in scene.objects if o.type == 'MESH' and o != me and o != keep and not o.hide_render]
    for o in hidden:
        o.hide_render = True
    paths = {}
    world = scene.world
    saved_bg = tuple(world.color) if world else None
    try:
        if world:
            world.color = (0.82, 0.83, 0.86)
        render.engine = 'BLENDER_WORKBENCH'
        shading.light = 'STUDIO'
        render.film_transparent = False
        render.resolution_percentage = 100
        if mode == "regions":
            attr = me.data.color_attributes.new("_sec_regions", 'FLOAT_COLOR', 'POINT')
            base = np.tile(np.array([0.72, 0.72, 0.74, 1.0]), (len(me.data.vertices), 1))
            for k, ch in enumerate(chains):
                tot = W[:, [cols.index(b) for b in ch["bones"][:-1]]].sum(1)
                m = tot > 0
                colr = np.array(PALETTE[k % len(PALETTE)] + (1.0,))
                f = np.clip(tot[m] / 0.8, 0, 1)[:, None] * 0.85 + 0.15
                base[m] = base[m] * (1 - f) + colr * f
            attr.data.foreach_set("color", base.astype(np.float32).ravel())
            me.data.color_attributes.active_color = attr
            shading.color_type = 'VERTEX'
            for k, ch in enumerate(chains):
                J = [Vector(j) for j in ch["joints"]]
                for i, j in enumerate(J):
                    added.append(_marker_sphere(j, 0.006, PALETTE[k % len(PALETTE)] if i else (1, 1, 1)))
                for a, b in zip(J[:-1], J[1:]):
                    added.append(_marker_rod(a, b, 0.0035, (0.05, 0.05, 0.05)))
            shading.color_type = 'VERTEX'
        else:
            shading.color_type = 'TEXTURE'
        corners = [me.matrix_world @ Vector(c) for c in me.bound_box]
        lo = Vector([min(c[i] for c in corners) for i in range(3)])
        hi = Vector([max(c[i] for c in corners) for i in range(3)])
        if focus:
            lo, hi = Vector(focus[0]), Vector(focus[1])
        centre, ext = (lo + hi) / 2, hi - lo
        for view in views:
            cd = bpy.data.cameras.new("_sec_cam")
            cam = bpy.data.objects.new("_sec_cam", cd)
            scene.collection.objects.link(cam)
            added.append(cam)
            cd.type, cd.clip_end, cd.sensor_fit = 'ORTHO', 100, 'VERTICAL'
            rot = {"front": (math.pi / 2, 0, 0), "back": (math.pi / 2, 0, math.pi),
                   "side": (math.pi / 2, 0, math.pi / 2), "threeq": (math.radians(80), 0, math.radians(145))}[view]
            cam.rotation_euler = rot
            fwd = cam.rotation_euler.to_matrix() @ Vector((0, 0, -1))
            cam.location = centre - fwd * 10
            width = max(ext.x, ext.y)
            render.resolution_y = size
            render.resolution_x = int(size * min(max(width / ext.z, 0.45), 1.5))
            cd.ortho_scale = max(ext.z, width / (render.resolution_x / size)) * 1.05
            scene.camera = cam
            path = os.path.join(out_dir, f"{prefix}{view}.png")
            render.filepath = path
            bpy.ops.render.render(write_still=True)
            paths[view] = path
    finally:
        for o in hidden:
            o.hide_render = False
        if world and saved_bg:
            world.color = saved_bg
        for o in added:
            data = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif data is not None and isinstance(data, bpy.types.Camera):
                bpy.data.cameras.remove(data)
        if attr is not None:
            me.data.color_attributes.remove(me.data.color_attributes["_sec_regions"])
        (render.engine, render.resolution_x, render.resolution_y, render.filepath, scene.camera,
         shading.light, shading.color_type, render.film_transparent) = saved
    return paths


def _marker_sphere(p, r, colr):
    import bmesh
    m = bpy.data.meshes.new("_sec_mk")
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=r)
    bm.to_mesh(m)
    bm.free()
    o = bpy.data.objects.new("_sec_mk", m)
    bpy.context.scene.collection.objects.link(o)
    o.location = p
    o.show_in_front = True
    mat = bpy.data.materials.new("_sec_mk")
    mat.diffuse_color = colr + (1,)
    m.materials.append(mat)
    m.color_attributes.new("_sec_regions", 'FLOAT_COLOR', 'POINT').data.foreach_set(
        "color", np.tile(np.array(colr + (1,), np.float32), len(m.vertices)))
    return o


def _marker_rod(a, b, r, colr):
    import bmesh
    m = bpy.data.meshes.new("_sec_mk")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=r, radius2=r, depth=(b - a).length)
    bm.to_mesh(m)
    bm.free()
    o = bpy.data.objects.new("_sec_mk", m)
    bpy.context.scene.collection.objects.link(o)
    o.location = (a + b) / 2
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(b - a)
    o.show_in_front = True
    m.color_attributes.new("_sec_regions", 'FLOAT_COLOR', 'POINT').data.foreach_set(
        "color", np.tile(np.array(colr + (1,), np.float32), len(m.vertices)))
    return o


def pose_swing(rig, chains, deg=30.0):
    """Swing every chain as a hard stop would: hood, back bag and hem back/out, a hip bag out, hair back."""
    for ch in chains:
        J = np.asarray(ch["joints"])
        bone_dir = unit(J[1] - J[0])
        push = {"hood": np.array([0, 1.0, 0.3]), "bag": np.array([0, 1.0, 0]), "hair": np.array([0, 1.0, 0]),
                "strap": np.array([0, -1.0, 0])}.get(ch["kind"])
        if ch["kind"] == "bag" and ch["side"] in ("l", "r"):     # a hip bag swings out, away from the leg
            push = np.array([1.0 if ch["side"] == "l" else -1.0, 0, 0])
        if push is None:     # hems flare outward
            out = J[1] - J[0]
            out[2] = 0
            push = unit(out) if np.linalg.norm(out) > 1e-6 else np.array([0, 1.0, 0])
        axis_w = np.cross(bone_dir, unit(push))
        if np.linalg.norm(axis_w) < 1e-6:
            continue
        for b in ch["bones"][:-1]:
            pb = rig.pose.bones[b]
            m = (rig.matrix_world @ pb.bone.matrix_local).to_3x3().inverted()
            ax = (m @ Vector(unit(axis_w))).normalized()
            pb.rotation_mode = 'QUATERNION'
            pb.rotation_quaternion = Quaternion(ax, math.radians(deg / max(1, len(ch["bones"]) - 1)))


def clear_pose(rig, chains):
    for ch in chains:
        for b in ch["bones"][:-1]:
            rig.pose.bones[b].rotation_quaternion = (1, 0, 0, 0)


# ----------------------------------------------------------------------------- the run

def gate(name, value, limit, ok):
    return {"name": name, "value": value, "limit": limit, "pass": bool(ok)}


def load_roles(spec):
    if not spec or spec == "arp":
        return dict(ARP_ROLES)
    with open(spec, encoding="utf-8") as f:
        data = json.load(f)
    if "retarget_map" in data:
        return {r: b for r, b in data["retarget_map"].items() if r in HUMAN}
    if "bones" in data:
        return {r: (b[0] if isinstance(b, list) else b) for r, b in data["bones"].items() if r in HUMAN}
    raise Refused(f"{spec}: neither a contract_map report nor a role map")


def kind_list(text, what):
    if text in (None, "", "none"):
        return []
    kinds = list(DETECTED) if text == "auto" else [k.strip() for k in text.split(",") if k.strip()]
    bad = [k for k in kinds if k not in KINDS]
    if bad:
        raise Refused(f"{what}: unknown kinds {bad}; use auto or {', '.join(KINDS)}")
    return kinds


def find_hair(a, me, rig):
    """The separate hair bound to the same rig: --hair-mesh NAME, or (auto) the one object
    assemble_parts.py bind leaves (marked `parts_hair`, named `Hair`); --hair-mesh none ignores it."""
    if a.hair_mesh == "none":
        if a.hair_chains:
            raise Refused("--hair-chains with --hair-mesh none: no hair object to chain")
        return None
    bound = lambda o: o.type == 'MESH' and o != me and any(m.type == 'ARMATURE' and m.object == rig
                                                          for m in o.modifiers)
    if a.hair_mesh not in (None, "auto"):
        o = bpy.data.objects.get(a.hair_mesh)
        if o is None or not bound(o):
            raise Refused(f"--hair-mesh {a.hair_mesh!r}: no mesh of that name bound to {rig.name!r}")
        return o
    found = [o for o in bpy.data.objects if bound(o) and (o.get("parts_hair") or o.name.split(".")[0] == "Hair")]
    if len(found) > 1:
        raise Refused(f"{len(found)} hair objects bound to {rig.name!r}: pass --hair-mesh NAME")
    if a.hair_chains and not found:
        raise Refused("--hair-chains needs a separate hair object bound to the rig (assemble_parts.py bind)")
    return found[0] if found else None


def run(a) -> tuple[dict, int]:
    me = bpy.data.objects.get(a.mesh or "")
    if me is None or me.type != 'MESH':
        raise Refused(f"no mesh object {a.mesh!r}")
    bound = [m.object for m in me.modifiers if m.type == 'ARMATURE' and m.object is not None]
    rig = bpy.data.objects.get(a.armature) if a.armature else (bound[0] if len(bound) == 1 else None)
    if rig is None or rig.type != 'ARMATURE':
        raise Refused(f"need the armature: --armature, or a mesh bound to one ({[o.name for o in bound]})")
    if not any(m.type == 'ARMATURE' and m.object == rig for m in me.modifiers):
        raise Refused(f"{me.name!r} is not bound to {rig.name!r}")
    if any(b.name.startswith("cc_") for b in rig.data.bones):
        raise Refused("the rig already has cc_ bones: start from the rig without chains")
    roles = load_roles(a.map)
    body = read_body(rig, me, roles)
    missing_roles = [r for r in ("Hips", "Spine", "Chest", "UpperChest", "Neck", "Head") if r not in body.roles]
    if missing_roles:
        raise Refused(f"the role map finds no deform bone for {missing_roles}")
    try:
        markers = json.load(open(a.markers, encoding="utf-8")) if a.markers else {}
    except (OSError, ValueError) as e:
        raise Refused(f"--markers: {e}")
    if not isinstance(markers, dict) or not all(isinstance(m, dict) and m.get("kind") in KINDS and m.get("name")
                                                and len(m.get("joints") or []) >= 2
                                                for m in markers.get("chains", [])):
        raise Refused("--markers: {\"chains\": [{\"kind\", \"name\", \"joints\": [[x, y, z], >= 2]}], \"skip\": []}")
    kinds, required = kind_list(a.kinds, "--kinds"), kind_list(a.require, "--require")
    hair_obj = find_hair(a, me, rig)
    hair_body, hchains = None, []
    skirt = None
    if a.skirt:
        try:
            skirt = json.load(open(a.skirt, encoding="utf-8")).get("skirt")
        except (OSError, ValueError) as e:
            raise Refused(f"--skirt: {e}")
        if not skirt:
            raise Refused(f"--skirt: {a.skirt} carries no skirt (arp_markers.py --body skirt)")
    if hair_obj is None:
        chains, info, missing = detect_all(body, kinds, markers, required, skirt=skirt)
    else:   # a separate hair (assemble_parts bind): the body has none; spikes, if asked, go on the hair object
        split = lambda keep: dict(markers, chains=[m for m in markers.get("chains", []) if keep(m["kind"])])
        chains, info, missing = detect_all(body, [k for k in kinds if k != "hair"], split(lambda k: k != "hair"),
                                           [k for k in required if k != "hair"], skirt=skirt)
        hair_body = read_body(rig, hair_obj, roles)
        hair_body.H, hair_body.zmin = body.H, body.zmin      # every threshold scales with the body's height
        hair_body.around = body.co[body.in_parts(("Head",))]
        hk = ["hair"] if a.hair_chains and "hair" in kinds else []
        hchains, hinfo, _ = detect_all(hair_body, hk, split(lambda k: k == "hair"))
        for ch in hchains:
            ch["on"] = "hair"
        if "hair" in required and not hchains:
            missing.append("hair")
        info.setdefault("found", {})["hair"] = (hinfo.get("found") or {}).get("hair", [])
        info["hair_object"] = {"name": hair_obj.name, "vertices": len(hair_obj.data.vertices),
                               "mode": "chains" if hchains else f"rigid on {body.bone('Head')}",
                               "detect": {k: v for k, v in hinfo.items() if k != "found"}}
    for ch in chains:
        ch["on"] = "body"
    allc = chains + hchains
    gates = [gate("secondary.chains_placed", missing, [], not missing)]
    report = {"schema": "gate/1", "tool": TOOL, "armature": rig.name, "mesh": me.name, "height": round(body.H, 4),
              "detect": info,
              "chains": [{"name": c["name"], "kind": c["kind"], "parent": c["parent_bone"], "bones": c["bones"],
                          "joints": [r6(j) for j in c["joints"]], "region_vertices": int(c["region"].sum()),
                          "mesh": hair_obj.name if c["on"] == "hair" else me.name,
                          "marker": bool(c.get("marker"))} for c in allc]}
    if hair_obj is not None:
        report["hair_mesh"] = hair_obj.name
    pics = {}
    if a.render:
        os.makedirs(a.render, exist_ok=True)
        pics["before"] = render_set(a.render, "before_", me, [], ("side", "back", "threeq"), "texture", keep=hair_obj)
    W, cols, extra, wstats = apply_shares(body, chains)
    if hair_body is not None:
        Wh, colsh, _, wstats_h = apply_shares(hair_body, hchains)
        wstats = dict(wstats, **{k: v for k, v in wstats_h.items() if k != "_limit"}, _limit_hair=wstats_h["_limit"])
    if a.detect_only:
        if a.render:
            pics["regions"] = render_set(a.render, "regions_", me, chains, ("side", "back", "front"), "regions",
                                         W=W, cols=cols)
            if hchains:
                pics["hair_regions"] = render_set(a.render, "hair_regions_", hair_obj, hchains,
                                                  ("side", "back", "front"), "regions", W=Wh, cols=colsh)
        report.update(gates=gates, weights=wstats, renders=pics)
        return finish(report, gates)
    if not allc:      # nothing loose: no bone, no export; the rig and its FBX stay as they were
        spec = secondary_json(os.path.splitext(os.path.basename(a.fbx or a.save or me.name))[0], [], {}, {},
                              {"H": body.H, "weighted": {}})
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump(spec, f, indent=1)
            report["secondary"] = os.path.abspath(a.out)
        report.update(weights=wstats, renders=pics, export={"skipped": "no chain: the rig is unchanged"})
        return finish(report, gates)
    lo, hi = body.co.min(0), body.co.max(0)
    upper = [[lo[0] * 0.55, lo[1], body.zmin + 0.3 * body.H], [hi[0] * 0.55, hi[1], hi[2]]]
    add_bones(rig, allc, body.H)
    parts = [("body", me, body, chains, W, cols)]
    if hchains:      # a rigid hair is left as it is: no group added, nothing rewritten
        parts.append(("hair", hair_obj, hair_body, hchains, Wh, colsh))
    nnz_max, sum_err, unchanged, per_bone, tip_w, Wread = 0, 0.0, 0.0, {}, [], {}
    for tag, obj, b_, cs, W_, cols_ in parts:
        write_weights(obj, W_, cols_, b_)
        # read back what Blender holds and gate it
        Wb_ = Wread[tag] = read_weights(obj, cols_)
        deform_n = len(b_.names)
        any_region = np.zeros(len(b_.co), bool)
        for c in cs:
            any_region |= c["region"]
        nnz = (Wb_ > 1e-6).sum(1)
        sums = Wb_.sum(1)
        outside = ~any_region
        if outside.any():
            unchanged = max(unchanged, float(np.abs(Wb_[outside, :deform_n] - b_.W[outside]).max()),
                            float(Wb_[outside, deform_n:].max()) if Wb_.shape[1] > deform_n else 0.0)
        nnz_max = max(nnz_max, int(nnz.max()))
        sum_err = max(sum_err, float(np.abs(sums[nnz > 0] - 1).max()) if (nnz > 0).any() else 0.0)
        per_bone.update({b: int((Wb_[:, cols_.index(b)] > 1e-4).sum()) for c in cs for b in c["bones"][:-1]})
        tip_w += [f"{obj.name}:{c['bones'][-1]}" for c in allc if obj.vertex_groups.get(c["bones"][-1]) is not None]
    Wb = Wread["body"]
    low = {b: n for b, n in per_bone.items() if n < 50}
    gates += [gate("secondary.weighted_vertices", low or min(per_bone.values(), default=0), ">= 50 per chain bone",
                   not low and per_bone),
              gate("secondary.max_influences", nnz_max, 4, nnz_max <= 4),
              gate("secondary.weight_sum", round(sum_err, 6), 1e-4, sum_err <= 1e-4),
              gate("secondary.body_weights_unchanged", round(unchanged, 7), 0, unchanged == 0),
              gate("secondary.tip_unweighted", tip_w, [], not tip_w)]
    leak = pose_leak(rig, {"body": me, **({"hair": hair_obj} if hair_obj is not None else {})}, allc)
    worst = max((v["outside_max"] for v in leak.values()), default=0.0)
    gates.append(gate("secondary.leak", round(worst, 6), 0.001, worst <= 0.001))
    report.update(weights=dict(wstats, per_bone=per_bone), leak={k: {kk: round(vv, 5) for kk, vv in v.items()}
                                                                for k, v in leak.items()})
    if a.render:
        pics["regions"] = render_set(a.render, "regions_", me, chains, ("side", "back", "front"), "regions",
                                     W=Wb, cols=cols)
        pics["regions_close"] = render_set(a.render, "regions_close_", me, chains, ("side", "back", "threeq"),
                                           "regions", W=Wb, cols=cols, focus=upper)
        if hchains:
            pics["hair_regions"] = render_set(a.render, "hair_regions_", hair_obj, hchains, ("side", "back", "front"),
                                              "regions", W=Wread["hair"], cols=colsh)
        pics["before_close"] = render_set(a.render, "before_close_", me, [], ("side", "threeq"), "texture",
                                          focus=upper, keep=hair_obj)
        pose_swing(rig, allc)
        bpy.context.view_layer.update()
        pics["after_swing"] = render_set(a.render, "swing_", me, allc, ("side", "back", "threeq"), "texture",
                                         keep=hair_obj)
        pics["after_swing_close"] = render_set(a.render, "swing_close_", me, allc, ("side", "threeq"), "texture",
                                               focus=upper, keep=hair_obj)
        clear_pose(rig, allc)
        bpy.context.view_layer.update()
    if a.save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.save), copy=True)
        report["saved"] = os.path.abspath(a.save)
    heads = {b: body.heads[b].tolist() for b in body.names}
    if a.fbx:
        fbx = os.path.abspath(a.fbx)
        res = export_fbx(rig, fbx)
        report["export"] = {k: res.get(k) for k in ("pass", "gates", "warnings", "skeleton", "refused", "error")}
        gates += [dict(g, name=g["name"]) for g in res.get("gates", [])]
        if not res.get("pass"):
            gates.append(gate("secondary.export", res.get("refused") or res.get("error"), None, False))
        sk_path = res.get("skeleton") or fbx[:-4] + ".skeleton.json"
        if os.path.exists(sk_path):
            sk = json.load(open(sk_path, encoding="utf-8"))
            heads = {b["name"]: b["head"] for b in sk["bones"]}
            report["skeleton"] = sk_path
        sources = {"body": (body, Wb, cols)}
        if hair_body is not None:
            sources["hair"] = (hair_body, Wread.get("hair", hair_body.W), colsh if hchains else list(hair_body.names))
        chk = reimport_check(fbx, allc, sources)
        report["reimport"] = chk
        gates.append(gate("secondary.export_bones", {"missing": chk["missing"], "wrong_parent": chk["wrong_parent"]},
                          "all present, parents kept", not chk["missing"] and not chk["wrong_parent"]))
        gates.append(gate("secondary.export_weights", {"outside_region": chk["outside_region"],
                                                       "weight_mismatch_max": chk["weight_mismatch_max"],
                                                       "unmatched": chk["unmatched"]},
                          {"outside_region": 0, "weight_mismatch_max": 0.01},
                          chk["outside_region"] == 0 and chk["weight_mismatch_max"] <= 0.01))
    cols_d, pen, inside = size_colliders(body, allc, heads)
    gates.append(gate("secondary.rest_penetration", inside, 0, inside == 0))
    report["colliders"] = {"shrunk": pen["shrunk"], "dropped": pen["dropped"], "added": pen.get("added", []),
                           "radii": {k: round(v["radius"], 4) for k, v in cols_d.items()}}
    weighted = {}
    for tag, _, _, cs, _, cols_ in parts:
        weighted.update({c["name"]: int((Wread[tag][:, [cols_.index(b) for b in c["bones"][:-1]]].sum(1) > 1e-4).sum())
                         for c in cs})
    spec = secondary_json(os.path.splitext(os.path.basename(a.fbx or a.save or me.name))[0], allc, cols_d, heads,
                          {"H": body.H, "weighted": weighted})
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=1)
        report["secondary"] = os.path.abspath(a.out)
    report["renders"] = pics
    return finish(report, gates)


def finish(report, gates):
    ok = bool(gates) and all(g["pass"] for g in gates)
    report.update(gates=gates, **{"pass": ok, "ok": ok, "verdict": "green" if ok else "failed"})
    return report, 0 if ok else 2


def args_after_dashes():
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else argv[1:]


class Parser(argparse.ArgumentParser):
    def error(self, message):   # a usage error is a refusal (exit 1), never a gate's exit 2
        raise Refused(f"{self.prog}: {message}")


def parser():
    p = Parser(prog=TOOL, allow_abbrev=False)
    p.add_argument("--armature", help="default: the armature the mesh is bound to")
    p.add_argument("--mesh")
    p.add_argument("--map", default="arp", help="arp, a contract_map report or a role map")
    p.add_argument("--kinds", default="auto", help="auto, or a comma list of kinds to look for")
    p.add_argument("--require", default="", help="kinds that must be found (comma list, or auto)")
    p.add_argument("--markers", help="manual chains: reference/secondary-chains.md")
    p.add_argument("--save")
    p.add_argument("--fbx")
    p.add_argument("--out")
    p.add_argument("--report")
    p.add_argument("--render")
    p.add_argument("--detect-only", action="store_true")
    p.add_argument("--hair-mesh", help="auto (default: the parts_hair object), a mesh name, or none")
    p.add_argument("--hair-chains", action="store_true", help="spike chains on the separate hair object")
    p.add_argument("--skirt", help="an arp_markers.py --body skirt report: the hem is the skirt's")
    p.add_argument("--selftest", action="store_true")
    return p


def main():
    a, report, code = None, None, 1
    try:
        a = parser().parse_args(args_after_dashes())
        if a.selftest:
            if bpy is None:
                raise Refused("run the selftest inside Blender: blender -b --factory-startup -P "
                              "secondary_chains.py -- --selftest")
            report, code = selftest(a)
        else:
            if bpy is None:
                raise Refused("run inside Blender: blender -b RIG.blend -P secondary_chains.py -- ...")
            report, code = run(a)
    except Refused as e:
        report, code = {"schema": "gate/1", "tool": TOOL, "pass": False, "ok": False, "verdict": "failed",
                        "gates": [], "refused": str(e)}, 1
    text = json.dumps(report, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    if a is not None and a.report:
        os.makedirs(os.path.dirname(os.path.abspath(a.report)), exist_ok=True)
        with open(a.report, "w", encoding="utf-8") as f:
            f.write(text)
    print(text if not (a is not None and a.report) else
          json.dumps({k: report.get(k) for k in ("pass", "gates", "refused")}, indent=1, default=str))
    if bpy is None:
        sys.exit(code)
    sys.stdout.flush()
    if code:
        os._exit(code)


# ----------------------------------------------------------------------------- selftest (no Auto-Rig Pro)

SHELL_BONES = [  # a fused shell's armature with Auto-Rig Pro's export names: name, head, tail, parent
    ("root.x", (0, 0.0, 1.0), (0, 0.0, 0.88), None),
    ("spine_01.x", (0, 0.0, 1.0), (0, 0.0, 1.15), "root.x"),
    ("spine_02.x", (0, 0.0, 1.15), (0, 0.0, 1.3), "spine_01.x"),
    ("spine_03.x", (0, 0.0, 1.3), (0, 0.0, 1.45), "spine_02.x"),
    ("neck.x", (0, 0.0, 1.45), (0, 0.0, 1.52), "spine_03.x"),
    ("head.x", (0, 0.0, 1.52), (0, 0.0, 1.75), "neck.x"),
    ("thigh_stretch.l", (0.1, 0, 0.9), (0.1, 0, 0.5), "root.x"),
    ("leg_stretch.l", (0.1, 0, 0.5), (0.1, 0, 0.1), "thigh_stretch.l"),
    ("foot.l", (0.1, 0, 0.1), (0.1, -0.12, 0.02), "leg_stretch.l"),
    ("thigh_stretch.r", (-0.1, 0, 0.9), (-0.1, 0, 0.5), "root.x"),
    ("leg_stretch.r", (-0.1, 0, 0.5), (-0.1, 0, 0.1), "thigh_stretch.r"),
    ("foot.r", (-0.1, 0, 0.1), (-0.1, -0.12, 0.02), "leg_stretch.r"),
]


def _clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def _tube(bm, x, y, z0, z1, r, segs=40, rings=None):
    import bmesh
    rings = rings or max(2, int((z1 - z0) / 0.01))
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r, depth=z1 - z0,
                          matrix=Matrix.Translation((x, y, (z0 + z1) / 2)))
    side = [e for e in bm.edges if e.is_valid and abs(e.verts[0].co.z - e.verts[1].co.z) > 0.011
            and abs(e.verts[0].co.x - e.verts[1].co.x) < 1e-6 and abs(e.verts[0].co.y - e.verts[1].co.y) < 1e-6]
    if side:      # rings along the side, so slices find skin at every height
        bmesh.ops.subdivide_edges(bm, edges=side, cuts=rings - 1, use_grid_fill=True)


def build_shell(hair_apart=False, extra=()):
    """A torso tube with a jacket hem lip, a box bag on the back, shorts tubes over thinner legs, a head
    sphere with five pointed spikes; each vertex bound to its two nearest bones. hair_apart: the spikes
    are their own object `Hair` (marked parts_hair, bound rigidly to head.x), as assemble_parts.py bind
    leaves a character in parts. extra, the look-alikes: "brim" a flat plate out of the head's side, "pony" a thick hank hanging from the back of the
    head down the back, "one_leg" shorts on the left leg only, "cap" a smooth dome over the head top with the spikes
    under it (a cap's or a helmet's crown), "hip_bag" a pouch on the right hip, "side_panel" a tall flap on the left
    side behind the mid-plane (a cape's or a coat's edge)."""
    import bmesh
    _clear()
    bm = bmesh.new()
    if "brim" in extra:          # flat, out of the front-right of the head (the face cone and the spikes clear)
        bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=16, radius=1, matrix=Matrix.Translation(
            (0.077, -0.046, 1.64)) @ Matrix.Diagonal((0.1, 0.1, 0.006, 1)))
    if "cap" in extra:           # a dome over the head top, open below: the spikes stay under it
        bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=0.19, matrix=Matrix.Translation((0, 0, 1.62)))
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < 1.6], context='VERTS')
    if "pony" in extra:
        for k in range(12):
            t = k / 11
            bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=10, radius=0.045, matrix=Matrix.Translation(
                (0.0, 0.1 + 0.095 * t, 1.56 - 0.3 * t)))
    _tube(bm, 0, 0, 1.0, 1.45, 0.15)                     # jacket body
    _tube(bm, 0, 0, 0.94, 1.02, 0.165, segs=96, rings=8)     # hem lip
    for k in range(8):                                   # its underside: the horizontal skin of the edge
        r0, r1 = 0.13 + 0.035 * k / 8, 0.13 + 0.035 * (k + 1) / 8
        ring = [[bm.verts.new((r * math.cos(t), r * math.sin(t), 0.94)) for t in np.linspace(0, 2 * math.pi, 41)[:-1]]
                for r in (r0, r1)]
        for i in range(40):
            bm.faces.new((ring[0][i], ring[0][(i + 1) % 40], ring[1][(i + 1) % 40], ring[1][i]))
    _tube(bm, 0, 0, 0.86, 0.95, 0.13, segs=96, rings=9)      # shorts waist
    _tube(bm, 0, 0, 1.45, 1.53, 0.05, rings=8)           # neck
    for sx in (1, -1):
        if sx > 0 or "one_leg" not in extra:
            _tube(bm, 0.1 * sx, 0, 0.55, 0.9, 0.09, rings=35)     # shorts leg
        _tube(bm, 0.1 * sx, 0, 0.0, 0.56, 0.055, rings=56)    # bare leg
    bmesh.ops.create_cube(bm, size=1, matrix=Matrix.Translation((0, 0.2, 1.1)) @ Matrix.Diagonal((0.16, 0.1, 0.22, 1)))
    bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if e.verts[0].co.y > 0.14 and e.verts[1].co.y > 0.14
                                         and e.verts[0].co.z < 1.22], cuts=10, use_grid_fill=True)
    if "hip_bag" in extra:
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1, matrix=Matrix.Translation(
            (-0.205, 0, 1.03)) @ Matrix.Diagonal((0.055, 0.085, 0.1, 1)))
    if "side_panel" in extra:
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=32, radius=1, matrix=Matrix.Translation(
            (0.2, 0.15, 1.1)) @ Matrix.Diagonal((0.055, 0.085, 0.38, 1)))
    bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=24, radius=0.1, matrix=Matrix.Translation((0, 0, 1.62)))
    bh = bmesh.new() if hair_apart else bm
    for d in ((0, 0, 1), (0, 0.8, 0.6), (0.8, 0.2, 0.55), (-0.8, 0.2, 0.55), (0, -0.6, 0.8)):
        d = Vector(d).normalized()
        rot = Vector((0, 0, 1)).rotation_difference(d).to_matrix().to_4x4()
        M = Matrix.Translation(Vector((0, 0, 1.62)) + d * 0.11) @ rot @ Matrix.Diagonal((0.025, 0.025, 0.06, 1))
        for v in bmesh.ops.create_uvsphere(bh, u_segments=24, v_segments=14, radius=1)["verts"]:
            if v.co.z > 0:       # the outer half drawn to a point: a lock's flanks, not a round knob
                v.co.x, v.co.y = (v.co.x, v.co.y) if v.co.z > 0.999 else \
                    (v.co.x * (1 - v.co.z) / math.sqrt(1 - v.co.z ** 2), v.co.y * (1 - v.co.z) / math.sqrt(1 - v.co.z ** 2))
            v.co = M @ v.co
    me = bpy.data.meshes.new("Shell")
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("Shell", me)
    bpy.context.scene.collection.objects.link(obj)
    arm = bpy.data.armatures.new("ShellRig")
    rig = bpy.data.objects.new("ShellRig", arm)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    for n, h, t, par in SHELL_BONES:
        b = arm.edit_bones.new(n)
        b.head, b.tail = h, t
        if par:
            b.parent = arm.edit_bones[par]
    bpy.ops.object.mode_set(mode='OBJECT')
    co = np.array([v.co[:] for v in me.vertices])
    D = np.stack([seg_project(co, np.array(h), np.array(t))[1] for _, h, t, _ in SHELL_BONES], 1)
    groups = [obj.vertex_groups.new(name=n) for n, _, _, _ in SHELL_BONES]
    order = np.argsort(D, 1)
    for i in range(len(co)):
        ia, ib = order[i, 0], order[i, 1]
        da, db = D[i, ia], D[i, ib]
        wa = 1.0 if db > 2.5 * max(da, 1e-4) else db / (da + db)
        groups[ia].add([i], wa, 'REPLACE')
        if wa < 1:
            groups[ib].add([i], 1 - wa, 'REPLACE')
    obj.modifiers.new("Armature", 'ARMATURE').object = rig
    obj.parent = rig
    if hair_apart:
        hm = bpy.data.meshes.new("Hair")
        bh.to_mesh(hm)
        bh.free()
        hair = bpy.data.objects.new("Hair", hm)
        bpy.context.scene.collection.objects.link(hair)
        hair.vertex_groups.new(name="head.x").add(list(range(len(hm.vertices))), 1.0, 'REPLACE')
        hair.modifiers.new("Armature", 'ARMATURE').object = rig
        hair.parent = rig
        hair["parts_hair"] = True
    return rig, obj


def build_plain(tmp):
    """deform_gate's selftest body (a smooth metaball humanoid, nothing loose), skinned on contract bones;
    returns (mesh, role map path)."""
    sys.dont_write_bytecode = True
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import arp_markers as AM
    import autorig_blender as A
    import deform_gate as DG
    A.clear_scene()
    body, _ = A.build_runner()
    V, F = A.mesh_arrays(body)
    opts = {"spine_bones": 3, "fingers": "fixed", "adjust": None, "arm_angle": (30.0, 60.0),
            "arm_ratios": (0.42, 0.75), "symmetry_max": 0.02, "no_window_gate": False}
    spec = DG.spec_both_sides(AM.build_report(V, F, opts)["contract_bones"])
    rig = A.build_armature("PlainRig", spec)
    body.parent = rig
    DG.skin(body, rig, spec, "good")
    path = os.path.join(tmp, "plain.roles.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"bones": {r: r for r in HUMAN if r in rig.data.bones}}, f)
    return body, path


def hand_off(doc, path):
    """Name a sample for tools/check-contracts.py, which validates it against schemas/ by its stamp."""
    out = os.environ.get("UNITY_DEV_CONTRACT_OUT") or os.path.join(tempfile.gettempdir(), "unity-dev-contract-out")
    os.makedirs(out, exist_ok=True)
    dst = os.path.join(out, path)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print(f"selftest-output: {dst}")


def selftest(a):
    tmp = a.render or tempfile.mkdtemp(prefix="secondary_selftest_")
    os.makedirs(tmp, exist_ok=True)
    checks = {}

    def args(*extra):
        return parser().parse_args(list(extra))
    # 1 the shell: every kind but the hood is there
    rig, obj = build_shell()
    out = os.path.join(tmp, "Shell.secondary.json")
    rep, code = run(args("--mesh", obj.name, "--out", out, *(["--render", a.render] if a.render else [])))
    found = rep["detect"].get("found", {})
    spec = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else {}
    shorts = [c for c in spec.get("chains", []) if c["kind"] == "shorts_hem"]
    live = sorted(s["name"] for s in rep["detect"].get("hem_sectors", []) if s["live"])
    rv = {c["name"]: c.get("region_vertices") for c in rep.get("chains", [])}
    swap = {"L": "R", "R": "L"}
    twin = lambda n: "shorts" + swap[n[6]] + n[7:] if n.startswith("shorts") else n[:-1] + swap[n[-1]]
    checks.update({
        "shell: every live hem sector is a chain (the ring shares its blend, none dropped) and each sector's skin "
        "mirrors its twin's, the hem's and the shorts'":
            len(live) >= 4 and sorted(found.get("hem", [])) == live and not rep["detect"].get("dropped_empty")
            and all(rv.get(n) and rv.get(n) == rv.get(twin(n)) for n in live + found.get("shorts_hem", [])),
        "shell: the armature found from the mesh's modifier, exit 0, every gate green":
            code == 0 and rep["armature"] == "ShellRig" and all(g["pass"] for g in rep["gates"]),
        "shell: no hood, one bag, a hem ring of >= 4, 3 shorts chains per leg, >= 3 hair chains":
            found.get("hood") == [] and len(found.get("bag", [])) == 1 and len(found.get("hem", [])) >= 4
            and len(found.get("shorts_hem", [])) == 6 and len(found.get("hair", [])) >= 3,
        "shell: secondary/1 written, every chain ends in its tip bone":
            spec.get("schema") == "secondary/1" and spec["chains"]
            and all(c["bones"][-1].startswith(f"cc_{c['name']}_end.") for c in spec["chains"]),
        "shell: each shorts hem tests both thighs, its own included":
            len(shorts) == 6 and all(sorted(c["colliders"]) == ["UpperLeg.L", "UpperLeg.R"] or
                                     any(d[0] == c["name"] for d in rep["colliders"]["dropped"]) for c in shorts),
    })
    if spec:
        hand_off(spec, "secondary_chains__shell.secondary.json")
    hand_off(rep, "secondary_chains__shell.gate.json")
    # 2 --require names a kind the shell does not have: chains_placed fails, exit 2
    rig, obj = build_shell()
    rep, code = run(args("--mesh", obj.name, "--require", "hood,bag", "--detect-only"))
    placed = next(g for g in rep["gates"] if g["name"] == "secondary.chains_placed")
    checks["--require hood,bag on the shell: chains_placed names the hood, exit 2"] = (
        code == 2 and placed["value"] == ["hood"] and not placed["pass"])
    # 3 a manual strap: one stiff bone whose share peaks mid-span, nothing detected
    rig, obj = build_shell()
    mk = os.path.join(tmp, "strap.markers.json")
    with open(mk, "w", encoding="utf-8") as f:
        json.dump({"chains": [{"kind": "strap", "name": "strap1", "region_radius": 0.03,
                               "joints": [[0.09, -0.12, 1.42], [-0.1, -0.15, 1.08]]}]}, f)
    rep, code = run(args("--mesh", obj.name, "--kinds", "none", "--markers", mk, "--detect-only"))
    ch = rep.get("chains", [])
    checks["a strap marker alone: one marker chain strap1 of one bone and its tip, exit 0"] = (
        code == 0 and [c["name"] for c in ch] == ["strap1"] and ch[0]["marker"]
        and ch[0]["bones"] == ["cc_strap1_01.x", "cc_strap1_end.x"])
    body = read_body(rig, obj, load_roles("arp"))          # --detect-only left the rig as it was
    chains, _, _ = detect_all(body, [], json.load(open(mk, encoding="utf-8")))
    u, _ = polyline_u(body.co, [[0.09, -0.12, 1.42], [-0.1, -0.15, 1.08]])
    share = chains[0]["share"][:, 0] if chains else np.zeros(len(u))
    mid, ends = share[(u > 0.4) & (u < 0.6)], share[(u < 0.1) | (u > 0.9)]
    checks["the strap's share peaks mid-span and fades to zero at both fixed ends"] = (
        obj.vertex_groups.get("cc_strap1_01.x") is None and mid.size > 0 and ends.size > 0
        and mid.max() > 0.3 and ends.max() < 0.25 * mid.max())
    # 3b a manual hair chain along the back spike: the full stage runs (colliders sized without a detected
    # head centre) and the chain is there
    rig, obj = build_shell()
    mk = os.path.join(tmp, "pony.markers.json")
    with open(mk, "w", encoding="utf-8") as f:
        json.dump({"chains": [{"kind": "hair", "name": "pony", "region_radius": 0.05,
                               "joints": [[0, 0.08, 1.68], [0, 0.108, 1.701], [0, 0.136, 1.722]]}]}, f)
    rep, code = run(args("--mesh", obj.name, "--kinds", "none", "--markers", mk,
                         "--out", os.path.join(tmp, "Pony.secondary.json")))
    checks["a hair marker chain alone: the full stage runs, chain pony placed, exit 0"] = (
        code == 0 and [c["name"] for c in rep.get("chains", [])] == ["pony"] and rep["chains"][0]["marker"])
    # 4 a smooth body with nothing loose: an empty chain list, every gate green
    body_obj, roles = build_plain(tmp)
    out = os.path.join(tmp, "Plain.secondary.json")
    rep, code = run(args("--mesh", body_obj.name, "--map", roles, "--out", out))
    spec = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else {}
    checks["a plain body: no chain, no bone added, an empty secondary/1, exit 0"] = (
        code == 0 and rep.get("chains") == [] and spec.get("chains") == []
        and not any(b.name.startswith("cc_") for b in body_obj.parent.data.bones)
        and "skipped" in rep.get("export", {}))
    if spec:
        hand_off(spec, "secondary_chains__plain.secondary.json")
    # 5 a rig that already carries chains is refused
    rig, obj = build_shell()
    run(args("--mesh", obj.name, "--kinds", "bag"))
    try:
        again = run(args("--mesh", obj.name, "--kinds", "bag"))[1]
    except Refused:
        again = 1
    checks["a rig that already has cc_ bones is refused, exit 1"] = again == 1
    # 6 a character in parts: the spikes are a separate hair object bound rigidly to Head
    rig, obj = build_shell(hair_apart=True)
    hair = bpy.data.objects["Hair"]
    rep, code = run(args("--mesh", obj.name))
    found = rep["detect"].get("found", {})
    hair_groups = sorted(g.name for g in hair.vertex_groups)
    checks["hair apart: found and left rigid on Head (no hair chain, nothing on the body's smooth skull, its "
           "groups untouched); the body's bag, hem and shorts as before, exit 0"] = (
        code == 0 and rep.get("hair_mesh") == "Hair" and found.get("hair") == []
        and rep["detect"]["hair_object"]["mode"] == "rigid on head.x" and hair_groups == ["head.x"]
        and len(found.get("bag", [])) == 1 and len(found.get("hem", [])) >= 4 and len(found.get("shorts_hem", [])) == 6
        and not any(b.name.startswith("cc_hair") for b in rig.data.bones))
    rig, obj = build_shell(hair_apart=True)
    hair = bpy.data.objects["Hair"]
    out = os.path.join(tmp, "Parts.secondary.json")
    rep, code = run(args("--mesh", obj.name, "--hair-chains", "--kinds", "hair", "--require", "hair", "--out", out))
    hc = [c for c in rep.get("chains", []) if c["kind"] == "hair"]
    hb = [b for c in hc for b in c["bones"][:-1]]
    hw = {b: (hair.vertex_groups.get(b) is not None) for b in hb}
    sums = read_weights(hair, [g.name for g in hair.vertex_groups]).sum(1)
    spec = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else {}
    checks["hair apart, --hair-chains: >= 3 spike chains weighted on the hair object only (the body gets no "
           "cc_hair group), its weights sum to 1, every gate green incl. leak, exit 0"] = (
        code == 0 and len(hc) >= 3 and all(c["mesh"] == "Hair" for c in hc) and hb and all(hw.values())
        and not any(obj.vertex_groups.get(b) is not None for b in hb)
        and float(np.abs(sums - 1).max()) < 1e-4 and all(g["pass"] for g in rep["gates"])
        and [c["kind"] for c in spec.get("chains", [])].count("hair") == len(hc))
    rig, obj = build_shell(hair_apart=True)
    rep, code = run(args("--mesh", obj.name, "--require", "hair", "--detect-only"))
    placed = next(g for g in rep["gates"] if g["name"] == "secondary.chains_placed")
    try:
        refused = run(args("--mesh", obj.name, "--hair-chains", "--hair-mesh", "none", "--detect-only"))[1]
    except Refused:
        refused = 1
    checks["hair apart: --require hair without --hair-chains fails chains_placed (exit 2); --hair-chains with "
           "--hair-mesh none is refused (exit 1)"] = code == 2 and placed["value"] == ["hair"] and refused == 1
    # 7 the hood's back sphere: under every rest joint by the particle radius, its centre in front of them
    from types import SimpleNamespace
    fake = SimpleNamespace(H=1.75, bone=lambda role: "spine_03.x")
    hood = {"name": "hood", "kind": "hood", "colliders": [],
            "joints": [[0.0, 0.12, 1.47], [0.012, 0.13, 1.37], [0.011, 0.095, 1.256]]}
    cols, rep7 = {}, {}
    back_sphere(fake, hood, cols, {"spine_03.x": [0.0, 0.0, 1.27]}, rep7)
    b, pr = cols.get("Back"), KINDS["hood"]["radius"] * 1.75
    gap = [np.linalg.norm(np.subtract(j, b["center"])) - b["radius"] - pr for j in hood["joints"][1:]] if b else [-1]
    checks["hood: a Back sphere on UpperChest, centre in front, every joint below the root outside it by < 1 cm"] = (
        b is not None and hood["colliders"] == ["Back"] and b["center"][1] < 0.095 - 0.5 * b["radius"]
        and all(0 <= g < 0.01 for g in gap))
    # 8 the bag's border: a smooth fade from outside the bulge into it, not one edge from full share to none
    line = np.c_[np.linspace(0, 0.2, 201), np.zeros(201), np.zeros(201)]
    core = line[:, 0] >= 0.1
    f = soft_border(SimpleNamespace(co=line), core, np.ones(201, bool), 0.02, 0.03)
    checks["bag border: 0 well outside, 1 well inside, rising smoothly through the border"] = (
        f[line[:, 0] < 0.079].max() == 0 and f[line[:, 0] > 0.131].min() == 1 and np.all(np.diff(f) >= 0)
        and np.abs(np.diff(f)).max() < 0.1)
    # 9 look-alikes, each caught by its own rule (and found as the kind it mimics with that rule off)
    g = globals()

    def look(extra, kinds, **off):
        res = []
        for knobs in ({}, off):
            saved = {k: g[k] for k in knobs}
            g.update(knobs)
            try:
                _, ob = build_shell(extra=extra)
                res.append(detect_all(read_body(ob.parent, ob, load_roles("arp")), kinds)[:2])
            finally:
                g.update(saved)
        return res
    ring = np.linspace(-180, 180, 200, endpoint=False)
    checks["back span: a band all round the spine line spans 360, a block behind 80 (the bag/hood rule)"] = (
        wrap_span(ring) == 360 and wrap_span(ring[np.abs(ring) < 40]) == 80 and wrap_span(ring) > BACK_SPAN)
    (ch, inf), (ch0, _) = look(("pony",), ["bag", "hood"], HOOD_WIDTH=0.0, BAG_WIDTH=0.0)
    hank = lambda cs: [c for c in cs if c["kind"] in ("hood", "bag") and np.asarray(c["joints"])[-1][2] > 1.15]
    checks["a hank hanging down the back is no hood or bag (too narrow; the box bag stays); with the width rules off "
           "it is one"] = (not hank(ch) and any("narrow" in r["why"] for r in inf["back"]["rejected"]) and hank(ch0))
    (ch, inf), (ch0, _) = look(("brim",), ["hair"], SPIKE_PLATE=1.01)
    brim = lambda cs: [c for c in cs if np.asarray(c["joints"])[-1][0] > 0.15]
    checks["a flat brim out of the head is no hair spike (its sides face one way); the spikes stay; with the plate rule "
           "off it is one"] = (not brim(ch) and len(ch) >= 3 and inf.get("hair_rejected") and brim(ch0))
    (ch, inf), (ch0, _) = look(("cap",), ["hair"], SPIKE_OUTER=0.0)
    crown = [r for r in inf.get("hair_rejected", []) if r.get("why") == "crown"]
    checks["a smooth dome over the spikes (a cap's crown) is no hair spike: its outer skin faces round the head, the "
           "flanks hide under the rim; with the crown rule off it is one"] = (not ch and crown and len(ch0) >= 1)
    (ch, inf), (ch0, _) = look(("hip_bag", "side_panel"), ["bag"], SIDE_TALL=1.01)
    sb = lambda cs, S: [c for c in cs if c["name"] == f"bag{S}"]
    rj = inf.get("side_bag", {}).get("rejected", [])
    checks["a box on the right hip is a side bag (one bone, its joints in the box); a tall flap on the left side is "
           "no bag (too tall: a cape's edge), the back bag stays; with the height rule off the flap is one"] = (
        len(sb(ch, "R")) == 1 and -0.27 < sb(ch, "R")[0]["joints"][0][0] < -0.14 and not sb(ch, "L")
        and any(r["side"] == "L" and "tall" in r["why"] for r in rj) and len([c for c in ch if c["name"] == "bag"]) == 1
        and len(sb(ch0, "L")) == 1)
    rig, obj = build_shell(extra=("hip_bag",))
    rep, code = run(args("--mesh", obj.name, "--kinds", "bag", "--require", "bag"))
    hb = next((c for c in rep.get("chains", []) if c["name"] == "bagR"), None)
    checks["a hip bag through the run: hung from the hips or the spine, part of its share from the right thigh, "
           "every gate green"] = (code == 0 and hb is not None and hb["parent"] in ("root.x", "spine_01.x")
                                  and hb["region_vertices"] >= 50 and rep["weights"]["bagR"]["from_parent"] < 0.9
                                  and hb["bones"][0] == "cc_bagR_01.r" and all(g_["pass"] for g_ in rep["gates"]))
    (ch, inf), _ = look(("one_leg",), ["shorts_hem"])
    checks["shorts on one leg only: no shorts chain, the drop reported unpaired"] = (
        not ch and "L" in inf.get("shorts", {}).get("unpaired", {}))
    rig, obj = build_shell(extra=("pony",))
    mk = os.path.join(tmp, "hank.markers.json")
    with open(mk, "w", encoding="utf-8") as f:
        json.dump({"chains": [{"kind": "hair", "name": "pony", "region_radius": 0.06,
                               "joints": [[0, 0.1, 1.56], [0, 0.148, 1.41], [0, 0.195, 1.26]]}]}, f)
    rep, code = run(args("--mesh", obj.name, "--kinds", "none", "--markers", mk,
                         "--out", os.path.join(tmp, "Hank.secondary.json")))
    pony = [c for c in rep.get("chains", []) if c["name"] == "pony"]
    sp = json.load(open(os.path.join(tmp, "Hank.secondary.json"), encoding="utf-8")) if code == 0 else {}
    cols = next((c.get("colliders") for c in sp.get("chains", []) if c["name"] == "pony"), None)
    checks["a ponytail as a hair marker chain: hung from head.x, skinned on the neck and back below the head, a "
           "Back sphere beside the Head one, every gate green"] = (
        code == 0 and pony and pony[0]["parent"] == "head.x" and pony[0]["region_vertices"] > 100
        and rep["weights"]["pony"]["from_parent"] < 0.9 and cols is not None and "Back" in str(cols)
        and all(g_["pass"] for g_ in rep["gates"]))
    ok = all(bool(v) for v in checks.values())
    return {"schema": "gate/1", "tool": TOOL, "pass": ok, "ok": ok, "verdict": "green" if ok else "failed",
            "gates": [{"name": f"selftest: {k}", "value": bool(v), "limit": True, "pass": bool(v)}
                      for k, v in checks.items()], "found_on_shell": found}, 0 if ok else 1


if __name__ == "__main__":
    main()
