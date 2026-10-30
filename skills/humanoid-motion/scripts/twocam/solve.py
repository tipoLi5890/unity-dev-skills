#!/usr/bin/env python3
"""solve.py — fit the rig to the joints read from both views: one pose per frame, smooth, inside the joint limits.

Ported from patch-gg/anymove (https://github.com/patch-gg/anymove), mocap/solve.py, commit
7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0. The fit (forward kinematics in torch, the
sigmoid-bounded Euler angles, the analytic IK start, the Kabsch root, the annealed Cauchy loss, the time warp,
the swap fix, the agreement and sync scores) is upstream's, with its constants and its order of operations.
Changes from upstream:
- The layout comes from rig_info.json's "layout" block, not from module constants or MOCAP_CREATURE.
- Feet, ground joints and limb pairs come from rig_info's "twocam" block, which skeleton.py and
  blender/prepare_rig.py write from the humanoid contract (Foot / Toes / ToesTip, sides from the .L/.R suffix),
  instead of the wolf and dragon names (LEGS, fpaw/ftoe/hpaw/htoe). The ground term takes each foot joint's
  rest height as its floor clearance (a heel or a ball does not sink below where it stands at rest).
- A bone may carry a limit_frame (its anatomical frame): its Euler angles and limits are then read in that
  frame, so the limits mean the same whatever the bone's roll. Upstream rigs carry none and fit as before.
- --compat-anymove CREATURE.json reads an upstream rig_info.json with upstream's names (feet from the
  creature.json, ground on fpaw/ftoe/hpaw/htoe, LEGS for --fix-swaps): the same fit as upstream.
- The joint-acceleration weight is 0.005 for the humanoid (--acc-weight; upstream's 0.02 with --compat-anymove):
  upstream's weight trades a fast arm swing for a smoother, different arm pose.
- --device cpu|cuda|auto (upstream picked CUDA when present, as auto does). The fit runs in float64, which MPS does not have, so a
  Mac fits on the CPU.
- The two-view agreement and the reprojection error per frame become gates (the same names and defaults as
  skills/blender-retarget/scripts/motion_metrics.py), and --samples-out writes motion-samples/1 for
  motion_metrics with the two_view block. One JSON report replaces upstream's prints; motion.json keeps
  upstream's keys and adds local_quat (per-bone pose rotation, for rigs with limit frames), the per-frame errors,
  gates and a record carrying the source video as an input. The samples carry sole_offsets (each foot joint's
  rest height, so motion_metrics finds plants on a sole, not an ankle) and reading_joints (the joints triangulated
  straight from the readings, so motion_metrics tells a pop the video has from one the fit added).
- --despike (on by default; --no-despike): after the fit, a single- or two-frame pop on a bone's segment that the
  readings do not show (motion_metrics' pop test, the readings' speed as the reference, 3 cm move floor) is
  replaced by the slerp of the bone's local rotation between the frames around it, inside the limits, and the
  joints and errors are recomputed; the report lists {"despiked": [{"bone", "frames"}]}.

usage:
    solve.py DET.npz RIG_INFO.json OUT_MOTION.json [--samples-out SAMPLES.json] [--no-align] [--fix-swaps]
             [--iters 1500] [--acc-weight 0.005] [--device cpu|cuda|auto] [--agreement-min 0.8] [--reproj-p95-px 8]
             [--no-despike] [--compat-anymove CREATURE.json] [--video CLIP.mp4] [--verbose]
    solve.py --selftest
Before fitting, the side view's left and right limbs can be checked against the front view (--fix-swaps): a joint
has the same height in both halves, so if swapping a pair in the side view makes the heights agree better, the
side reader mixed up the near and far limb. Painted limbs make the labels trustworthy, so this is off by default.
The same height test gives the sync score and the best lag; when re-timing cuts the height gap by more than 15 %,
the front view is time-warped onto the side view's timeline (--no-align skips it).

Gates (exit 2 when one fails):
  two_view_agreement            mean correlation of the feet's heights between the views over the clip
                                (rig_info twocam.agreement_joints), >= --agreement-min (0.8), on the frames where
                                the joint reads with confidence >= 0.3 in both views (detect's --min-conf default;
                                a foot hidden in one view reads low there, somewhere else); paw_agreement.frames_used
                                says how many. A foot with fewer than 8 such frames or a quarter of the clip, or
                                under 0.5 px of spread on them, gives no correlation. With none left the gate
                                fails (value null, `unread` names the feet) when a foot lacked confident frames,
                                --agreement-min -1 turns it off; when every foot simply stayed still it is left
                                out and the clip is judged by reprojection (a warning says which case).
  two_view_reprojection_p95_px  per frame, the median over joints of the distance between the fitted joints'
                                projections and the readings, on the axes the fit trusts (front: left-right; side:
                                both), averaged over the two views; p95 over frames <= --reproj-p95-px x H / 768
                                (8 px at 768). The per-view means are reported beside it (reproj_px).
Exit codes: 0 every gate passed (or the selftest passed), 2 a gate failed, 1 refused input or an error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from layout import MIN_CONF, Layout  # noqa: E402
from skeleton import mat_to_quat, mirror_name, side_of  # noqa: E402

torch = None  # imported by need_torch(), so --help and py_compile work without it

AGREEMENT_MIN, REPROJ_P95_PX, REPROJ_REF_HEIGHT = 0.8, 8.0, 768
AGREE_MIN_FRAMES = 8   # confident frames a foot needs before its correlation counts
# weight of the joint-acceleration term: upstream's 0.02 smooths a fast hand away (a strike's hand accelerates at
# tens of m/s^2); the humanoid default keeps it. Raise it for jittery readings, lower it for fast strikes.
ACC_UPSTREAM, ACC_HUMANOID = 0.02, 0.005
# upstream's wolf/dragon names, used only with --compat-anymove
LEGACY_LEGS = {"F": ["scap", "shoulder", "elbow", "wrist", "fpaw", "ftoe"], "H": ["hip", "knee", "hock", "hpaw", "htoe"]}
LEGACY_GROUND = ("fpaw", "ftoe", "hpaw", "htoe")
LEGACY_FEET = ["fpaw_L", "fpaw_R", "hpaw_L", "hpaw_R"]
DESPIKE_MIN_MOVE = 0.03  # m: the pop floor capture gates with (motion_metrics --pops-min-move)
METRICS_DIR = Path(__file__).resolve().parents[3] / "blender-retarget" / "scripts"


def need_torch():
    global torch
    if torch is None:
        import torch as _t
        torch = _t
    return torch


class Spec:
    """What the fit needs besides the rig: the layout, feet, ground clearances and limb pairs."""

    def __init__(self, info: dict, compat: dict | None = None):
        self.layout = Layout.from_rig_info(info)
        names = [k["name"] for k in info["keypoints"]]
        tc = info.get("twocam") or {}
        if compat is not None:
            self.feet = compat.get("feet", LEGACY_FEET)
            self.ground = {n: 0.0 for n in names if any(n.startswith(p) for p in LEGACY_GROUND)}
            self.pairs = {}
            for k, stems in LEGACY_LEGS.items():
                self.pairs[k] = [(f"{s}_L", f"{s}_R") for s in stems if f"{s}_L" in names]
        else:
            self.feet = tc.get("agreement_joints", [])
            self.ground = {n: float(h) for n, h in (tc.get("ground") or {}).items() if n in names}
            self.pairs = {k: [tuple(p) for p in v] for k, v in (tc.get("limb_pairs") or {}).items()}


def leg_pairs(names, spec):
    """Index pairs (left, right) of every limb joint, grouped per limb pair."""
    return {k: [(names.index(a), names.index(b)) for a, b in v if a in names and b in names]
            for k, v in spec.pairs.items()}


def fix_swaps(d, names, spec, margin=4.0):
    """Swap near/far limbs in the side view where the heights say the reader mixed them up."""
    fv, sv = d["front_uv"][..., 1], d["side_uv"][..., 1]
    c = np.minimum(d["front_conf"], d["side_conf"]).clip(0, 1)
    swapped = {}
    for k, pairs in leg_pairs(names, spec).items():
        if not pairs:
            continue
        L, R = np.array(pairs).T
        same = (c[:, L] * np.abs(sv[:, L] - fv[:, L]) + c[:, R] * np.abs(sv[:, R] - fv[:, R])).sum(1)
        swap = (c[:, L] * np.abs(sv[:, R] - fv[:, L]) + c[:, R] * np.abs(sv[:, L] - fv[:, R])).sum(1)
        gain = (same - swap) / len(pairs)
        gain = np.array([np.median(gain[max(0, t - 2):t + 3]) for t in range(len(gain))])
        do = gain > margin
        for t in np.where(do)[0]:
            d["side_uv"][t, L], d["side_uv"][t, R] = d["side_uv"][t, R].copy(), d["side_uv"][t, L].copy()
            d["side_conf"][t, L], d["side_conf"][t, R] = d["side_conf"][t, R].copy(), d["side_conf"][t, L].copy()
        swapped[k] = int(do.sum())
    return swapped


def height_features(uv, conf, names):
    """Per-frame heights that do not care about left/right labels: middle joints as they are, each limb pair as its
    mean height and its height difference. Returns (T, K) features and (T, K) weights."""
    v = uv[..., 1]
    feats, w = [], []
    for i, n in enumerate(names):
        s = side_of(n)
        if not s:
            feats.append(v[:, i]); w.append(conf[:, i])
        elif s == "L":
            a, b = i, names.index(mirror_name(n))
            c = np.minimum(conf[:, a], conf[:, b])
            feats += [(v[:, a] + v[:, b]) / 2, np.abs(v[:, a] - v[:, b])]
            w += [c, c]
    return np.stack(feats, 1), np.stack(w, 1).clip(0, 1)


def align_views(d, names, band=48, step_penalty=1.0):
    """Video models often play the two halves out of step (one view runs ahead). Match the halves frame to frame
    with dynamic time warping on joint heights, which both views share, and resample the front view onto the side
    view's timeline. Returns how far each side frame's match was moved, in frames."""
    F, Fw = height_features(d["front_uv"], d["front_conf"], names)
    S, Sw = height_features(d["side_uv"], d["side_conf"], names)
    T = len(F)
    C = np.full((T, T), np.inf)
    for i in range(T):
        lo, hi = max(0, i - band), min(T, i + band + 1)
        w = np.minimum(Fw[i][None], Sw[lo:hi])
        C[i, lo:hi] = (w * np.abs(F[i][None] - S[lo:hi])).sum(1) / w.sum(1).clip(1e-6)
    D = np.full((T, T), np.inf)
    D[0, 0] = C[0, 0]
    for i in range(T):
        for j in range(max(0, i - band), min(T, i + band + 1)):
            if i == j == 0:
                continue
            best = min(D[i - 1, j - 1] if i and j else np.inf, D[i - 1, j] + step_penalty if i else np.inf,
                       D[i, j - 1] + step_penalty if j else np.inf)
            D[i, j] = C[i, j] + best
    i, j, path = T - 1, T - 1, [(T - 1, T - 1)]
    while i or j:
        cands = [(D[i - 1, j - 1], i - 1, j - 1) if i and j else (np.inf, 0, 0),
                 (D[i - 1, j], i - 1, j) if i else (np.inf, 0, 0), (D[i, j - 1], i, j - 1) if j else (np.inf, 0, 0)]
        _, i, j = min(cands)
        path.append((i, j))
    path = np.array(path[::-1])
    match = np.array([path[path[:, 1] == j, 0].mean() for j in range(T)])  # front frame for each side frame
    match = np.convolve(np.pad(match, 3, mode="edge"), np.ones(7) / 7, mode="valid")  # no stair steps
    t = np.arange(T)
    for k in ("front_uv", "front_conf"):
        a = d[k].reshape(T, -1)
        d[k] = np.stack([np.interp(match, t, a[:, c]) for c in range(a.shape[1])], 1).reshape(d[k].shape)
    return match - t


def paw_agreement(d, names, feet, min_conf=MIN_CONF):
    """Correlation of each foot's height between the two views over the clip: +1 when both halves show the same
    footfalls, near 0 or negative when the video model animated the views differently. Only the frames where the
    joint is read with confidence >= min_conf in both views count (a foot hidden behind the other leg in the side
    view reads at low confidence, somewhere else); a joint needs AGREE_MIN_FRAMES of them and a quarter of the
    clip, else it is left out. frames_used says how many frames each joint's correlation read."""
    out, used = {}, {}
    T = len(d["front_uv"])
    need = max(AGREE_MIN_FRAMES, -(-T // 4))
    for k in feet:
        if k in names:
            j = names.index(k)
            m = np.minimum(d["front_conf"][:, j], d["side_conf"][:, j]) >= min_conf
            used[k] = int(m.sum())
            a, b = d["front_uv"][m, j, 1], d["side_uv"][m, j, 1]
            out[k] = float(np.corrcoef(a, b)[0, 1]) if used[k] >= need and a.std() > 0.5 and b.std() > 0.5 else None
    vals = [v for v in out.values() if v is not None]
    out["score"] = float(np.mean(vals)) if vals else None
    out["frames_used"] = used
    out["frames_needed"] = need
    out["min_conf"] = min_conf
    return out


def sync_report(d):
    """Mean height disagreement between the halves (layout px) and the lag (frames) that minimises it."""
    fv, sv = d["front_uv"][..., 1], d["side_uv"][..., 1]
    c = np.minimum(d["front_conf"], d["side_conf"]).clip(0, 1)
    err = (c * np.abs(fv - sv)).sum(1) / c.sum(1).clip(1e-6)
    best = None
    T = len(fv)
    for lag in range(-12, 13):
        a = fv[max(0, lag):T + min(0, lag)]
        b = sv[max(0, -lag):T + min(0, -lag)]
        e = np.abs(a - b).mean()
        if best is None or e < best[1]:
            best = (lag, e)
    return {"mean_height_gap_px": float(err.mean()), "worst_frame_gap_px": float(err.max()),
            "per_frame_gap_px": err.round(2).tolist(), "best_lag_frames": best[0], "gap_at_best_lag_px": float(best[1])}


def euler_xyz(a):
    """Blender Euler XYZ (applied X, then Y, then Z) to rotation matrices: Rz @ Ry @ Rx."""
    x, y, z = a.unbind(-1)
    cx, sx, cy, sy, cz, sz = x.cos(), x.sin(), y.cos(), y.sin(), z.cos(), z.sin()
    o, l = torch.zeros_like(x), torch.ones_like(x)
    Rx = torch.stack([l, o, o, o, cx, -sx, o, sx, cx], -1).view(*x.shape, 3, 3)
    Ry = torch.stack([cy, o, sy, o, l, o, -sy, o, cy], -1).view(*x.shape, 3, 3)
    Rz = torch.stack([cz, -sz, o, sz, cz, o, o, o, l], -1).view(*x.shape, 3, 3)
    return Rz @ Ry @ Rx


def axis_angle(v):
    th = v.norm(dim=-1, keepdim=True).clamp(min=1e-8)
    k = v / th
    K = torch.zeros(*v.shape[:-1], 3, 3, dtype=v.dtype, device=v.device)
    K[..., 0, 1], K[..., 0, 2], K[..., 1, 0] = -k[..., 2], k[..., 1], k[..., 2]
    K[..., 1, 2], K[..., 2, 0], K[..., 2, 1] = -k[..., 0], -k[..., 1], k[..., 0]
    th = th[..., None]
    return torch.eye(3, dtype=v.dtype, device=v.device) + th.sin() * K + (1 - th.cos()) * K @ K


class Rig:
    def __init__(self, info, dev="cpu"):
        need_torch()
        self.names = [b["name"] for b in info["bones"]]
        self.parent = [b["parent"] for b in info["bones"]]
        B = torch.tensor([b["matrix_local"] for b in info["bones"]], dtype=torch.float64, device=dev)
        self.B = B
        self.L = torch.tensor([b["length"] for b in info["bones"]], dtype=torch.float64, device=dev)
        # rest offset of each bone in its parent's frame
        self.off = torch.stack([B[i] if p < 0 else torch.linalg.inv(B[p]) @ B[i] for i, p in enumerate(self.parent)])
        lim = np.radians(np.array([b["limits_deg"] for b in info["bones"]], float))
        self.lo = torch.tensor(lim[..., 0], device=dev)
        self.hi = torch.tensor(lim[..., 1], device=dev)
        # limit frames (anatomical -> local); None for upstream rigs, whose Euler angles are local
        if any("limit_frame" in b for b in info["bones"]):
            self.C = torch.tensor([b.get("limit_frame", np.eye(3).tolist()) for b in info["bones"]],
                                  dtype=torch.float64, device=dev)
        else:
            self.C = None
        self.kp = [(k["bone"], k["end"]) for k in info["keypoints"]]
        self.kp_names = [k["name"] for k in info["keypoints"]]
        self.rest_kp = torch.tensor([k["rest"] for k in info["keypoints"]], dtype=torch.float64, device=dev)

    def local(self, R):
        """Rotations read in each bone's limit frame to its local frame: C R C^T."""
        return R if self.C is None else self.C @ R @ self.C.transpose(-1, -2)

    def forward(self, trans, root_rot, eul):
        """trans (T,3) world offset, root_rot (T,3,3) root basis, eul (T,nb,3) Euler for every bone (root ignored)."""
        T, nb = eul.shape[:2]
        R = self.local(euler_xyz(eul))
        P = [None] * nb
        for i, p in enumerate(self.parent):
            basis = torch.zeros(T, 4, 4, dtype=eul.dtype, device=eul.device)
            basis[:, :3, :3] = root_rot if p < 0 else R[:, i]
            basis[:, 3, 3] = 1
            if p < 0:
                M = self.off[i].expand(T, 4, 4) @ basis
                M = M.clone()
                M[:, :3, 3] += trans
            else:
                M = P[p] @ self.off[i] @ basis
            P[i] = M
        P = torch.stack(P, 1)
        joints = []
        for b, end in self.kp:
            if end == "head":
                joints.append(P[:, b, :3, 3])
            else:
                joints.append(P[:, b, :3, 1] * self.L[b] + P[:, b, :3, 3])
        return torch.stack(joints, 1), P


def project(J, L: Layout):
    v = L.H / 2 - (J[..., 2] - L.Z_CENTER) / L.M_PER_PX
    f = torch.stack([L.W_FRONT / 2 + J[..., 0] / L.M_PER_PX, v], -1)
    s = torch.stack([L.W_SIDE / 2 - J[..., 1] / L.M_PER_PX, v], -1)
    return f, s


def triangulate(d, L: Layout, front_height_weight=0.25):
    """Joints in metres: x from the front view, y from the side view, height mostly from the side view."""
    fx = (d["front_uv"][..., 0] - L.W_FRONT / 2) * L.M_PER_PX
    sy = -(d["side_uv"][..., 0] - L.W_SIDE / 2) * L.M_PER_PX
    fz = L.Z_CENTER + (L.H / 2 - d["front_uv"][..., 1]) * L.M_PER_PX
    sz = L.Z_CENTER + (L.H / 2 - d["side_uv"][..., 1]) * L.M_PER_PX
    w1, w2 = front_height_weight * d["front_conf"].clip(1e-3), d["side_conf"].clip(1e-3)
    return np.stack([fx, sy, (fz * w1 + sz * w2) / (w1 + w2)], -1)


def root_from_triangulation(tri, conf, rig, names, info):
    """Per-frame root rotation (as the basis of the root bone, axis-angle) from the points that ride rigidly on it
    (its two ends and the heads of the bones hung straight off it), by weighted Kabsch against the rest pose;
    smoothed over time."""
    bones = info["bones"]
    ride = {bones[0]["head_joint"], bones[0]["tail_joint"]} | {b["head_joint"] for b in bones if b["parent"] == 0}
    body = sorted(names.index(n) for n in ride if n in names)
    h = names.index(bones[0]["head_joint"])
    rest = rig.rest_kp.cpu().numpy()
    a = rest[body] - rest[h]
    Brot = rig.B[0, :3, :3].cpu().numpy()
    out = []
    for t in range(len(tri)):
        b = tri[t, body] - tri[t, h]
        w = conf[t, body]
        U, _, Vt = np.linalg.svd((a * w[:, None]).T @ b)
        D = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))])
        W = Vt.T @ D @ U.T
        R = Brot.T @ W @ Brot
        ang = np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))
        axis = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
        out.append(axis / max(np.linalg.norm(axis), 1e-8) * ang if ang > 1e-6 else np.zeros(3))
    out = np.array(out)
    k = np.ones(5) / 5
    return np.stack([np.convolve(np.pad(out[:, i], 2, mode="edge"), k, mode="valid") for i in range(3)], 1)


def euler_from_matrix(R):
    """Inverse of euler_xyz for one 3x3 matrix (Blender XYZ: R = Rz Ry Rx)."""
    b = -np.arcsin(np.clip(R[2, 0], -1, 1))
    return np.array([np.arctan2(R[2, 1], R[2, 2]), b, np.arctan2(R[1, 0], R[0, 0])])


def rot_between(a, b):
    """Smallest rotation taking unit vector a to unit vector b."""
    v, c = np.cross(a, b), float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K / (1 + c)


def ik_init(tri, root_aa, info, rig):
    """Point every bone at its triangulated child joint, down the hierarchy, with no twist and inside its limits:
    a starting pose close to the answer, so the fit does not have to find a crouch or a leap from a standing pose."""
    names = rig.kp_names
    bones = info["bones"]
    off = rig.off.cpu().numpy()
    Brot = rig.B[0, :3, :3].cpu().numpy()
    lo, hi = rig.lo.cpu().numpy(), rig.hi.cpu().numpy()
    C = None if rig.C is None else rig.C.cpu().numpy()
    T, nb = len(tri), len(bones)
    eul = np.zeros((T, nb, 3))
    y = np.array([0.0, 1.0, 0.0])
    for t in range(T):
        aa = root_aa[t]
        ang = np.linalg.norm(aa)
        k = aa / ang if ang > 1e-9 else np.array([1.0, 0, 0])
        K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
        W = [None] * nb
        W[0] = Brot @ (np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K)
        for i in range(1, nb):
            p = bones[i]["parent"]
            base = W[p] @ off[i][:3, :3]
            if bones[i]["head_joint"] not in names or bones[i]["tail_joint"] not in names:
                W[i] = base  # a bone whose ends are not tracked: start at rest
                continue
            d = tri[t, names.index(bones[i]["tail_joint"])] - tri[t, names.index(bones[i]["head_joint"])]
            if np.linalg.norm(d) < 1e-6:
                W[i] = base
                continue
            R = rot_between(y, base.T @ (d / np.linalg.norm(d)))
            if C is None:
                e = np.clip(euler_from_matrix(R), lo[i], hi[i])
                eul[t, i] = e
                W[i] = base @ euler_xyz(torch.tensor(e)).numpy()
            else:
                e = np.clip(euler_from_matrix(C[i].T @ R @ C[i]), lo[i], hi[i])
                eul[t, i] = e
                W[i] = base @ (C[i] @ euler_xyz(torch.tensor(e)).numpy() @ C[i].T)
    return eul


def fit(d, info, spec: Spec, iters=1500, dev="cpu", log=False, front_height_weight=0.25, lr=(0.01, 0.03, 0.05),
        sigma0=40.0, acc_weight=0.02):
    need_torch()
    L = spec.layout
    rig = Rig(info, dev)
    names = rig.kp_names
    T = len(d["front_uv"])
    f_obs = torch.tensor(d["front_uv"], dtype=torch.float64, device=dev)
    s_obs = torch.tensor(d["side_uv"], dtype=torch.float64, device=dev)
    f_c = torch.tensor(d["front_conf"], dtype=torch.float64, device=dev).clamp(0, 1) ** 2
    s_c = torch.tensor(d["side_conf"], dtype=torch.float64, device=dev).clamp(0, 1) ** 2
    tri_np = triangulate(d, L, front_height_weight)
    tri = torch.tensor(tri_np, dtype=torch.float64, device=dev)
    hips = names.index(info["bones"][0]["head_joint"])
    trans = (tri[:, hips] - rig.rest_kp[hips]).clone().requires_grad_(True)
    conf = np.minimum(d["front_conf"], d["side_conf"]).clip(1e-3, 1)
    root0 = root_from_triangulation(tri_np, conf, rig, names, info) + 1e-4
    root = torch.tensor(root0, dtype=torch.float64, device=dev).requires_grad_(True)
    # Euler = lo + (hi - lo) * sigmoid(phi), starting from the analytic IK pose
    e0 = torch.tensor(ik_init(tri_np, root0, info, rig), dtype=torch.float64, device=dev)
    z = ((e0 - rig.lo) / (rig.hi - rig.lo)).clamp(1e-3, 1 - 1e-3)
    phi = torch.logit(z).clone().requires_grad_(True)
    paws = [names.index(n) for n in names if n in spec.ground]
    clear = [spec.ground[names[j]] for j in paws]
    h0 = None if not any(clear) else torch.tensor(clear, dtype=torch.float64, device=dev)
    sigma = 6.0  # px, robust scale (annealed down from 40 px so far-off joints still pull early on)
    # The side view sees limbs swing and the hips clearly; the front view foreshortens forward moves, and video
    # models animate it less faithfully. So heights come mostly from the side view and the front view mainly
    # supplies left-right position.
    f_axis = torch.tensor([1.0, front_height_weight], dtype=torch.float64, device=dev)

    def loss_fn(stage):
        nonlocal sigma
        eul = rig.lo + (rig.hi - rig.lo) * torch.sigmoid(phi)
        J, _ = rig.forward(trans, axis_angle(root), eul)
        pf, ps = project(J, L)
        rf = ((pf - f_obs) ** 2 * f_axis).sum(-1)
        rs = ((ps - s_obs) ** 2).sum(-1)
        data = (f_c * torch.log1p(rf / sigma ** 2)).sum() + (s_c * torch.log1p(rs / sigma ** 2)).sum()
        acc = ((J[2:] - 2 * J[1:-1] + J[:-2]) ** 2).sum() / L.M_PER_PX ** 2 * acc_weight
        vel = ((eul[1:] - eul[:-1]) ** 2).sum() * 2.0 + ((root[1:] - root[:-1]) ** 2).sum() * 2.0
        prior = (eul ** 2).sum() * 0.05
        if h0 is None:
            ground = (torch.relu(-J[:, paws, 2]) ** 2).sum() / L.M_PER_PX ** 2 * 0.5
        else:
            ground = (torch.relu(h0 - J[:, paws, 2]) ** 2).sum() / L.M_PER_PX ** 2 * 0.5
        total = data + acc + vel + prior + ground
        return total, {"data": data.item(), "acc": acc.item(), "vel": vel.item(), "prior": prior.item(),
                       "ground": ground.item()}, J, pf, ps, eul

    opt = torch.optim.Adam([{"params": [trans], "lr": lr[0]}, {"params": [root], "lr": lr[1]}, {"params": [phi], "lr": lr[2]}])
    for it in range(iters):
        sigma = 6.0 + (sigma0 - 6.0) * max(0.0, 1 - it / (0.6 * iters))
        if it == int(iters * 0.7):
            for g in opt.param_groups:
                g["lr"] *= 0.3
        total, parts, J, pf, ps, eul = loss_fn(it)
        opt.zero_grad()
        total.backward()
        opt.step()
        if log and it % 250 == 0:
            print(f"  iter {it} loss {total.item():.1f}", {k: round(v, 1) for k, v in parts.items()},
                  file=sys.stderr, flush=True)
    sigma = 6.0
    with torch.no_grad():
        total, parts, J, pf, ps, eul = loss_fn(iters)
        err_f = (pf - f_obs).norm(dim=-1)
        err_fx = (pf - f_obs)[..., 0].abs()
        err_s = (ps - s_obs).norm(dim=-1)
        local = rig.local(euler_xyz(eul))
    return {"trans": trans.detach().cpu().numpy(), "root_rotmat": axis_angle(root).detach().cpu().numpy(),
            "euler": eul.detach().cpu().numpy(), "joints": J.cpu().numpy(),
            "local_rotmat": None if rig.C is None else local.cpu().numpy(),
            "reproj_px": {"front": float(err_f.mean()), "front_x_only": float(err_fx.mean()), "side": float(err_s.mean())},
            "err": {"front": err_f.cpu().numpy(), "front_x": err_fx.cpu().numpy(), "side": err_s.cpu().numpy()},
            "bones": rig.names, "joint_names": names}


def to_quat(Rm):
    q = []
    for R in Rm:
        w = np.sqrt(max(0, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
        x = np.copysign(np.sqrt(max(0, 1 + R[0, 0] - R[1, 1] - R[2, 2])) / 2, R[2, 1] - R[1, 2])
        y = np.copysign(np.sqrt(max(0, 1 - R[0, 0] + R[1, 1] - R[2, 2])) / 2, R[0, 2] - R[2, 0])
        z = np.copysign(np.sqrt(max(0, 1 - R[0, 0] - R[1, 1] + R[2, 2])) / 2, R[1, 0] - R[0, 1])
        q.append([w, x, y, z])
    return np.array(q)


def quat_to_mat(q):
    w, x, y, z = np.moveaxis(q / np.linalg.norm(q, axis=-1, keepdims=True), -1, 0)
    return np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y),
                     2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x),
                     2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], -1).reshape(q.shape[:-1] + (3, 3))


def slerp(q0, q1, t):
    q1 = q1 if np.dot(q0, q1) >= 0 else -q1
    c = float(np.clip(np.dot(q0, q1), -1, 1))
    if c > 0.9995:
        q = q0 + t * (q1 - q0)
    else:
        th = np.arccos(c)
        q = (np.sin((1 - t) * th) * q0 + np.sin(t * th) * q1) / np.sin(th)
    return q / np.linalg.norm(q)


def evaluate(rig, d, L, trans, root_rotmat, eul, dev="cpu"):
    """The fit's outputs for given parameters: joints, per-view errors, local rotations (as fit() returns them)."""
    t = lambda x: torch.tensor(np.asarray(x), dtype=torch.float64, device=dev)  # noqa: E731
    with torch.no_grad():
        e = t(eul)
        J, _ = rig.forward(t(trans), t(root_rotmat), e)
        pf, ps = project(J, L)
        f_obs, s_obs = t(d["front_uv"]), t(d["side_uv"])
        err_f = (pf - f_obs).norm(dim=-1)
        err_fx = (pf - f_obs)[..., 0].abs()
        err_s = (ps - s_obs).norm(dim=-1)
        local = rig.local(euler_xyz(e))
    return {"joints": J.cpu().numpy(), "euler": np.asarray(eul, float),
            "local_rotmat": None if rig.C is None else local.cpu().numpy(),
            "reproj_px": {"front": float(err_f.mean()), "front_x_only": float(err_fx.mean()), "side": float(err_s.mean())},
            "err": {"front": err_f.cpu().numpy(), "front_x": err_fx.cpu().numpy(), "side": err_s.cpu().numpy()}}


def metrics_module():
    """skills/blender-retarget/scripts/motion_metrics.py (the pop test), or None when it is not beside us."""
    if str(METRICS_DIR) not in sys.path:
        sys.path.insert(0, str(METRICS_DIR))
    try:
        import motion_metrics
    except ImportError:
        return None
    return motion_metrics


def despike(res, d, info, spec, tri, fps, dev="cpu", min_move=DESPIKE_MIN_MOVE, passes=3):
    """Replace the fit's own pops (spikes the readings `tri` do not show) by the slerp of the bone's local rotation
    between the frames around them. Returns (res, [{"bone", "frames"}], warnings)."""
    mm = metrics_module()
    if mm is None:
        return res, [], [f"despike skipped: motion_metrics.py not found in {METRICS_DIR}"]
    rig = Rig(info, dev)
    names, bones = rig.kp_names, info["bones"]
    lo, hi = rig.lo.cpu().numpy(), rig.hi.cpu().numpy()
    C = None if rig.C is None else rig.C.cpu().numpy()
    trans, root_R, eul = res["trans"], res["root_rotmat"].copy(), np.array(res["euler"], float)
    J = res["joints"]
    T = len(J)

    def local_of(e, bi):
        R = euler_xyz(torch.tensor(e)).numpy()
        return R if C is None else C[bi] @ R @ C[bi].T

    def bone_pops(J, bi):
        h, t = names.index(bones[bi]["head_joint"]), names.index(bones[bi]["tail_joint"])
        seg = float(np.median(np.linalg.norm(J[:, t] - J[:, h], axis=1)))
        floor = float(np.degrees(min_move / max(seg, 1e-6)))
        w = mm.segment_speed_deg(J[:, h], J[:, t], fps)
        return mm.pops(w, fps, clip=mm.segment_speed_deg(tri[:, h], tri[:, t], fps), min_excess_deg=floor)

    def replaced(bi, frames, root_R, eul):
        a, b = frames[0] - 1, frames[-1] + 1
        root_R, eul = root_R.copy(), eul.copy()
        if bi == 0:
            q0, q1 = to_quat(root_R[[a, b]])
            for f in frames:
                root_R[f] = quat_to_mat(slerp(q0, q1, (f - a) / (b - a)))
        else:
            q0, q1 = to_quat(local_of(eul[[a, b], bi], bi))
            for f in frames:
                R = quat_to_mat(slerp(q0, q1, (f - a) / (b - a)))
                eul[f, bi] = np.clip(euler_from_matrix(R if C is None else C[bi].T @ R @ C[bi]), lo[bi], hi[bi])
        return root_R, eul

    fixed = {}
    tracked = [i for i, b in enumerate(bones) if b["head_joint"] in names and b["tail_joint"] in names
               and b["head_joint"] != b["tail_joint"]]
    for _ in range(passes):
        changed = False
        for bi in tracked:
            for f, kind in bone_pops(J, bi):
                n_before = len(bone_pops(J, bi))
                # the speed spike at f (and f+1) is the step into those frames: the pose frame off the path is f
                # (two-frame: f, or f-1 and f for a jump that came back late); keep the one that clears the most
                best = None
                for frames in ([f], [f - 1, f], [f, f + 1]) if kind == "wide" else ([f], [f - 1]):
                    if frames[0] < 1 or frames[-1] > T - 2:
                        continue
                    r2, e2 = replaced(bi, frames, root_R, eul)
                    J2 = evaluate(rig, d, spec.layout, trans, r2, e2, dev)["joints"]
                    n_after = len(bone_pops(J2, bi))
                    score = (n_after, float(np.abs(J2 - tri).sum()))
                    if n_after < n_before and (best is None or score < best[0]):
                        best = (score, frames, r2, e2, J2)
                if best is not None:
                    _, frames, root_R, eul, J = best
                    fixed.setdefault(bones[bi]["name"], set()).update(frames)
                    changed = True
                    break  # this bone's pops are listed again on the new joints next pass
        if not changed:
            break
    if fixed:
        res = dict(res, root_rotmat=root_R, **evaluate(rig, d, spec.layout, trans, root_R, eul, dev))
    return res, [{"bone": b, "frames": sorted(int(f) for f in fr)} for b, fr in fixed.items()], []


# --- gates and the motion_metrics hand-over -------------------------------------------------------------------
def frame_reprojection(err) -> np.ndarray:
    """Per frame: the median over joints of the front left-right error and of the side error, averaged over the two
    views. The median, because the robust loss is meant to ignore a stray reading (a joint the reader lost for a
    frame); a limb that is wrong throughout shows in the agreement and in the overlay instead."""
    return 0.5 * (np.median(err["front_x"], 1) + np.median(err["side"], 1))


def gates_for(agreement, reproj, H, a, unread=None) -> list:
    """unread: the feet read confidently on too few frames when no agreement could be scored. The gate then
    fails (value None): a clip whose feet the readers lost is not a clip the agreement passed. --agreement-min
    -1 or lower turns it off."""
    out = []
    if agreement is not None:
        out.append({"name": "two_view_agreement", "value": round(agreement, 4), "limit": f">= {a.agreement_min}",
                    "ok": agreement >= a.agreement_min})
    elif unread:
        out.append({"name": "two_view_agreement", "value": None, "limit": f">= {a.agreement_min}",
                    "ok": a.agreement_min <= -1, "unread": unread})
    p95 = float(np.percentile(reproj, 95))
    lim = a.reproj_p95_px * H / REPROJ_REF_HEIGHT
    out.append({"name": "two_view_reprojection_p95_px", "value": round(p95, 3), "limit": f"<= {round(lim, 3)}",
                "ok": p95 <= lim})
    return out


def samples_doc(motion, info, clip, readings=None) -> dict:
    """motion-samples/1 for skills/blender-retarget/scripts/motion_metrics.py, two_view block inline; the feet's
    sole_offsets from twocam.ground, and the joints triangulated from the readings (`readings`, T x J x 3)."""
    names = motion["joint_names"]
    J = np.asarray(motion["joints"])
    tc = info.get("twocam") or {}
    doc = {"schema": "motion-samples/1", "clip": clip, "fps": motion["fps"],
           "joints": {n: J[:, i].round(5).tolist() for i, n in enumerate(names)},
           "root": info["bones"][0]["head_joint"], "two_view": motion["two_view"]}
    if all(n in names for n in ("Foot.L", "Toes.L", "Foot.R", "Toes.R")):
        doc["feet"] = {"l": ["Foot.L", "Toes.L"], "r": ["Foot.R", "Toes.R"]}
        ground = tc.get("ground") or {}
        offs = {n: round(float(ground[n]), 6) for s in ("l", "r") for n in doc["feet"][s] if n in ground}
        if offs:
            doc["sole_offsets"] = offs
    if readings is not None:
        doc["reading_names"] = list(names)
        doc["reading_joints"] = np.asarray(readings).round(4).tolist()
    segs = [[b["head_joint"], b["tail_joint"]] for b in info["bones"]
            if b["head_joint"] in names and b["tail_joint"] in names and b["head_joint"] != b["tail_joint"]]
    doc["segments"] = segs
    if tc.get("schema"):
        doc["limits"] = [{"name": f"knee.{s}", "chain": [f"UpperLeg.{s}", f"LowerLeg.{s}", f"Foot.{s}"],
                          "min_deg": 0, "max_deg": 155} for s in ("L", "R")] + \
                        [{"name": f"elbow.{s}", "chain": [f"UpperArm.{s}", f"LowerArm.{s}", f"Hand.{s}"],
                          "min_deg": 0, "max_deg": 155} for s in ("L", "R")]
        doc["limits"] = [l for l in doc["limits"] if all(c in names for c in l["chain"])]
    return doc


def solve(det: dict, info: dict, a, compat=None) -> dict:
    """The whole stage on loaded inputs. Returns {motion, report}."""
    spec = Spec(info, compat)
    names = [k["name"] for k in info["keypoints"]]
    det_names = [str(n) for n in det.get("names", names)]
    if list(det_names) != names:
        raise ValueError(f"det.npz joints {det_names[:4]}... are not rig_info's keypoints {names[:4]}...")
    d = {k: np.array(det[k], dtype=np.float64 if k.endswith("uv") else np.float32).copy()
         for k in ("front_uv", "side_uv", "front_conf", "side_conf")}
    for k in ("front_uv", "side_uv"):
        if d[k].ndim != 3 or d[k].shape[1:] != (len(names), 2):
            raise ValueError(f"{k} has shape {d[k].shape}, expected (T, {len(names)}, 2)")
    warnings = []
    before = sync_report(d)
    paws = paw_agreement(d, names, spec.feet)
    shift = None
    align = {"applied": False}
    if not a.no_align:
        trial = {k: v.copy() for k, v in d.items()}
        s = align_views(trial, names)
        gain = 1 - sync_report(trial)["mean_height_gap_px"] / max(before["mean_height_gap_px"], 1e-6)
        align["height_gap_cut"] = round(float(gain), 4)
        if gain > 0.15:  # only re-time when the halves really were out of step
            d.update(trial)
            shift = s
            align.update({"applied": True, "mean_shift_frames": float(np.abs(shift).mean()),
                          "max_shift_frames": float(np.abs(shift).max())})
    swapped = fix_swaps(d, names, spec) if a.fix_swaps else {}
    sync = sync_report(d)
    sync["before"] = {k: v for k, v in before.items() if k != "per_frame_gap_px"}
    sync["paw_agreement"] = paws
    sync["front_shift_frames"] = None if shift is None else shift.round(2).tolist()
    acc = a.acc_weight if a.acc_weight is not None else (ACC_UPSTREAM if compat is not None else ACC_HUMANOID)
    res = fit(d, info, spec, iters=a.iters, dev=a.device, log=a.verbose, acc_weight=acc)
    fps = float(det["fps"])
    readings = triangulate(d, spec.layout)  # the joints the readings alone give, for the pop reference
    despiked = []
    if getattr(a, "despike", True):
        res, despiked, w = despike(res, d, info, spec, readings, fps, a.device)
        warnings += w
    reproj = frame_reprojection(res["err"])
    agreement = paws["score"]
    unread = None
    if agreement is None:
        few = [k for k, n in paws["frames_used"].items() if n < paws["frames_needed"]]
        if few:
            unread = few
            warnings.append(f"{', '.join(few)} not read with confidence >= {paws['min_conf']} in both views on "
                            f"{paws['frames_needed']} frames: two_view_agreement fails (no score); look at the "
                            "overlay, and reshoot or pass --agreement-min -1 to accept the clip without it")
        else:
            warnings.append("no foot moved more than 0.5 px in both views (on its confident frames): the agreement "
                            "gate is left out; judge the clip by reprojection and look at the overlay")
    two_view = {"reprojection_px": reproj.round(3).tolist(), "frame_height_px": spec.layout.H,
                "reprojection_basis": "per frame, median over joints of the front left-right and the side error, "
                                      "averaged over the views"}
    if agreement is not None:
        two_view["agreement"] = round(agreement, 4)
    gates = gates_for(agreement, reproj, spec.layout.H, a, unread)
    motion = {"fps": fps, "bones": res["bones"], "trans": res["trans"].round(5).tolist(),
              "root_quat": to_quat(res["root_rotmat"]).round(6).tolist(), "euler": res["euler"].round(5).tolist(),
              "joints": res["joints"].round(4).tolist(), "joint_names": res["joint_names"],
              "reproj_px": res["reproj_px"], "sync": sync, "swaps": swapped}
    if res["local_rotmat"] is not None:
        lr = res["local_rotmat"]
        motion["local_quat"] = mat_to_quat(lr).round(7).tolist()
    motion["two_view"] = two_view
    motion["gates"] = gates
    ok = all(g["ok"] for g in gates)
    report = {"tool": "solve.py", "frames": len(reproj), "fps": fps, "joints": len(names), "bones": len(res["bones"]),
              "paw_agreement": paws, "sync_before": sync["before"],
              "sync_after": {k: v for k, v in sync.items() if k in ("mean_height_gap_px", "worst_frame_gap_px")},
              "align": align, "swaps": swapped, "reproj_px": {k: round(v, 3) for k, v in res["reproj_px"].items()},
              "reproj_frame_p95_px": round(float(np.percentile(reproj, 95)), 3), "despiked": despiked,
              "gates": gates, "ok": ok, "warnings": warnings}
    return {"motion": motion, "report": report, "readings": readings}


def sha256(path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser() -> argparse.ArgumentParser:
    p = UsageParser(prog="solve.py", description=__doc__.split("\n")[0])
    p.add_argument("det"); p.add_argument("rig_info"); p.add_argument("out")
    p.add_argument("--samples-out"); p.add_argument("--no-align", action="store_true")
    p.add_argument("--fix-swaps", action="store_true"); p.add_argument("--iters", type=int, default=1500)
    p.add_argument("--acc-weight", type=float, help=f"acceleration term weight (default {ACC_HUMANOID}; "
                   f"{ACC_UPSTREAM} with --compat-anymove)")
    p.add_argument("--device", choices=["auto", "cpu", "cuda"], default="cpu",
                   help="auto: CUDA when present, else the CPU")
    p.add_argument("--agreement-min", type=float, default=AGREEMENT_MIN)
    p.add_argument("--reproj-p95-px", type=float, default=REPROJ_P95_PX)
    p.add_argument("--compat-anymove", metavar="CREATURE.json")
    p.add_argument("--video", help="the clip the readings came from: pinned as the record's input")
    p.add_argument("--clip", help="clip name for the samples file (default: the output's folder)")
    p.add_argument("--despike", action=argparse.BooleanOptionalAction, default=True,
                   help="replace pops the fit added (not in the readings) by a slerp (default on)")
    p.add_argument("--verbose", action="store_true")
    return p


def run(argv) -> int:
    a = parser().parse_args(argv)
    try:
        need_torch()
    except ImportError:
        print(json.dumps({"tool": "solve.py", "ok": False, "error": "refused: torch is not installed (see "
                          "reference/two-camera.md for the venv)"})); return 1
    if a.device == "auto":
        a.device = "cuda" if torch.cuda.is_available() else "cpu"
    if a.device == "cuda" and not torch.cuda.is_available():
        print(json.dumps({"tool": "solve.py", "ok": False, "error": "refused: --device cuda but CUDA is not available"}))
        return 1
    try:
        with np.load(a.det) as raw:
            det = {k: raw[k] for k in raw.files}
        info = json.loads(Path(a.rig_info).read_text(encoding="utf-8"))
        compat = None
        if a.compat_anymove:
            compat = json.loads(Path(a.compat_anymove).read_text(encoding="utf-8"))
            compat = {"feet": compat.get("feet", LEGACY_FEET)}
        out = solve(det, info, a, compat)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"tool": "solve.py", "ok": False, "error": f"refused: {type(exc).__name__}: {exc}"}))
        return 1
    motion, report = out["motion"], out["report"]
    inputs = [{"path": str(Path(a.det).resolve()), "sha256": sha256(a.det)},
              {"path": str(Path(a.rig_info).resolve()), "sha256": sha256(a.rig_info)}]
    if a.video:
        inputs.insert(0, {"path": str(Path(a.video).resolve()), "sha256": sha256(a.video)})
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(motion), encoding="utf-8")
    files = [{"path": str(Path(a.out).resolve()), "sha256": sha256(a.out)}]
    if a.samples_out:
        clip = a.clip or Path(a.out).resolve().parent.name
        Path(a.samples_out).write_text(json.dumps(samples_doc(motion, info, clip, out["readings"])), encoding="utf-8")
        files.append({"path": str(Path(a.samples_out).resolve()), "sha256": sha256(a.samples_out)})
        report["samples_out"] = a.samples_out
    report["out"] = a.out
    # the solved clip inherits the video's licence through a parent / depends-on link when it is recorded
    report["record"] = {"tool": {"skill": "humanoid-motion", "script": "twocam/solve.py"},
                        "params": {"iters": a.iters, "align": not a.no_align, "fix_swaps": a.fix_swaps,
                                   "acc_weight": a.acc_weight if a.acc_weight is not None else
                                   (ACC_UPSTREAM if a.compat_anymove else ACC_HUMANOID),
                                   "compat_anymove": bool(a.compat_anymove), "despike": a.despike},
                        "inputs": inputs, "files": files,
                        "gates": [{"name": g["name"], "value": g["value"], "limit": g["limit"], "pass": g["ok"]}
                                  for g in report["gates"]],
                        "verdict": "green" if report["ok"] else "failed"}
    print(json.dumps(report))
    return 0 if report["ok"] else 2


# --- selftest -------------------------------------------------------------------------------------------------
def selftest() -> int:
    try:
        need_torch()
    except ImportError:
        print(json.dumps({"tool": "solve.py", "selftest": "fail", "error": "torch is not installed"})); return 1
    import contextlib
    import io
    import exam
    from skeleton import build_rig_info, demo_skeleton, read_skeleton
    checks = []
    quiet = lambda argv: (lambda buf: (lambda code: code)(_quiet_run(argv, buf)))(io.StringIO())

    buf_last = []

    def _quiet_run(argv, buf):
        with contextlib.redirect_stdout(buf):
            code = run(argv)
        buf_last[:] = [buf.getvalue()]
        return code

    def check(name, cond, **extra):
        checks.append({"name": name, "pass": bool(cond), **extra})

    info, _ = build_rig_info(read_skeleton(demo_skeleton()))
    info["layout"] = Layout.humanoid(1.7).as_dict()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ri = td / "rig_info.json"; ri.write_text(json.dumps(info))
        truth = exam.make_motion(info, seed=3, T=48, fps=24)
        tj = exam.fk_joints(info, truth)
        # FK in numpy (exam) and torch (solve) agree
        rig = Rig(info)
        eul = torch.tensor(np.asarray(truth["euler"]))
        rq = torch.tensor(np.asarray(exam.quat_to_mat(np.asarray(truth["root_quat"]))))
        Jt, _ = rig.forward(torch.tensor(np.asarray(truth["trans"])), rq, eul)
        check("numpy and torch FK agree", np.abs(Jt.numpy() - tj).max() < 1e-9)
        det = exam.perfect_det(info, tj, fps=24, noise_px=0.3, seed=1)
        np.savez(td / "det.npz", **det)
        code = quiet([str(td / "det.npz"), str(ri), str(td / "motion.json"), "--samples-out", str(td / "s.json"),
                    "--iters", "600"])
        m = json.loads((td / "motion.json").read_text()) if (td / "motion.json").exists() else None
        check("clean readings pass, exit 0", code == 0, code=code)
        if m:
            err = np.linalg.norm(np.asarray(m["joints"]) - tj, axis=-1)
            check("joints within 2 cm (mean) of the truth", err.mean() < 0.02, mean_cm=round(float(err.mean() * 100), 3))
            check("local_quat written for limit frames", np.asarray(m["local_quat"]).shape == (48, 22, 4))
            s = json.loads((td / "s.json").read_text())
            check("samples file for motion_metrics", s["schema"] == "motion-samples/1" and "two_view" in s
                  and s["feet"]["l"] == ["Foot.L", "Toes.L"] and len(s["two_view"]["reprojection_px"]) == 48)
            ground = info["twocam"]["ground"]
            check("samples carry the feet's sole_offsets from twocam.ground",
                  s.get("sole_offsets") == {n: round(ground[n], 6) for n in ("Foot.L", "Toes.L", "Foot.R", "Toes.R")},
                  sole_offsets=s.get("sole_offsets"))
            rj = np.asarray(s.get("reading_joints", []))
            check("samples carry reading_joints (T x J x 3) within 1 cm of the truth",
                  s.get("reading_names") == [k["name"] for k in info["keypoints"]] and rj.shape == tj.shape
                  and np.linalg.norm(rj - tj, axis=-1).mean() < 0.01, shape=list(rj.shape))
            rep0 = json.loads(buf_last[0]) if buf_last else {}
            check("clean readings: nothing despiked", rep0.get("despiked") == [], despiked=rep0.get("despiked"))
        # a pop the fit adds (the elbow thrown 0.5 rad for one frame) that the readings do not have
        real_fit = globals()["fit"]
        bone = "LowerArm.L"
        bi = [b["name"] for b in info["bones"]].index(bone)
        lim = np.radians(np.array(info["bones"][bi]["limits_deg"], float))
        ax = 0  # the elbow's bend (Y is the twist, which a segment's direction does not see)

        def spiked_fit(d, info_, spec, **kw):
            res = real_fit(d, info_, spec, **kw)
            e = np.array(res["euler"])
            e[20, bi, ax] += 0.5 if e[20, bi, ax] + 0.5 <= lim[ax, 1] else -0.5
            return dict(res, **evaluate(Rig(info_), d, spec.layout, res["trans"], res["root_rotmat"], e))

        mm = metrics_module()
        globals()["fit"] = spiked_fit
        try:
            runs = {}
            for flag in ("--despike", "--no-despike"):
                code = quiet([str(td / "det.npz"), str(ri), str(td / f"sp{flag}.json"), "--samples-out",
                               str(td / f"ss{flag}.json"), "--iters", "600", flag])
                mo = json.loads((td / f"sp{flag}.json").read_text())
                rp = json.loads(buf_last[0])
                _, mrep, _ = mm.run([str(td / f"ss{flag}.json"), "--pops-min-move", "0.03"])
                runs[flag] = (code, np.linalg.norm(np.asarray(mo["joints"]) - tj, axis=-1), rp, mrep)
        finally:
            globals()["fit"] = real_fit
        code, err, rp, mrep = runs["--despike"]
        hand = [k["name"] for k in info["keypoints"]].index("Hand.L")
        check("a pop the fit added is despiked: the bone and frame listed",
              code == 0 and any(x["bone"] == bone and 20 in x["frames"] for x in rp.get("despiked", [])),
              despiked=rp.get("despiked"))
        n_code, n_err, n_rp, n_mrep = runs["--no-despike"]
        check("despiked joints are no further from the truth than the clean fit's",
              m is not None and err.mean() <= np.linalg.norm(np.asarray(m["joints"]) - tj, axis=-1).mean() + 0.002
              and err[20, hand] < 0.25 * n_err[20, hand],
              mean_cm=round(float(err.mean() * 100), 3), hand_cm=round(float(err[20, hand] * 100), 2),
              kept_hand_cm=round(float(n_err[20, hand] * 100), 2))
        check("despiked samples: motion_metrics gates no pop",
              mrep.get("pops", {}).get("count") == 0, pops=mrep.get("pops"))
        check("--no-despike keeps the pop: nothing listed, motion_metrics gates it",
              n_rp.get("despiked") == [] and n_mrep["pops"]["count"] >= 1
              and any(g["name"] == "pops" and not g["ok"] for g in n_mrep["gates"]),
              pops=n_mrep.get("pops", {}).get("count"))
        # a desynced pair of views: the side view plays a different motion -> agreement fails
        other = exam.fk_joints(info, exam.make_motion(info, seed=11, T=48, fps=24))
        bad = exam.perfect_det(info, tj, fps=24, noise_px=0.3, seed=2, side_joints=other)
        np.savez(td / "bad.npz", **bad)
        code = quiet([str(td / "bad.npz"), str(ri), str(td / "m2.json"), "--iters", "300", "--no-align"])
        rep = json.loads((td / "m2.json").read_text())
        g = {x["name"]: x for x in rep["gates"]}
        check("views that disagree fail two_view_agreement, exit 2",
              code == 2 and not g.get("two_view_agreement", {"ok": True})["ok"], code=code,
              agreement=g.get("two_view_agreement", {}).get("value"))
        # a left foot hidden in the side view for 20 frames: read at confidence 0.04, on the hand. Masked by
        # confidence the agreement passes; the same points read confidently are a real mismatch and fail
        kn = [k["name"] for k in info["keypoints"]]
        hid = np.arange(4, 24)
        occ = {k: np.array(v).copy() for k, v in det.items()}
        for jn in ("Foot.L", "Toes.L"):
            j = kn.index(jn)
            occ["side_uv"][hid, j] = occ["side_uv"][hid[::-1], kn.index("Hand.L")]
            occ["side_conf"][hid, j] = 0.04
        feet = Spec(info).feet
        unmasked = paw_agreement(occ, kn, feet, min_conf=0.0)["score"]
        masked = paw_agreement(occ, kn, feet)
        np.savez(td / "occ.npz", **occ)
        code = quiet([str(td / "occ.npz"), str(ri), str(td / "m6.json"), "--iters", "300", "--no-align"])
        g = {x["name"]: x for x in json.loads((td / "m6.json").read_text())["gates"]}
        check("a foot hidden at low confidence: masked out (frames_used 28), agreement passes",
              unmasked < AGREEMENT_MIN <= masked["score"] and masked["frames_used"]["Toes.L"] == 28
              and g["two_view_agreement"]["ok"], unmasked=round(unmasked, 3), masked=round(masked["score"], 3),
              code=code)
        for jn in ("Foot.L", "Toes.L"):
            occ["side_conf"][hid, kn.index(jn)] = 0.9
        np.savez(td / "occ2.npz", **occ)
        code = quiet([str(td / "occ2.npz"), str(ri), str(td / "m7.json"), "--iters", "300", "--no-align"])
        g = {x["name"]: x for x in json.loads((td / "m7.json").read_text())["gates"]}
        check("the same wrong points read confidently fail two_view_agreement, exit 2",
              code == 2 and not g["two_view_agreement"]["ok"], agreement=g["two_view_agreement"]["value"])
        low = {k: np.array(v).copy() for k, v in det.items()}
        for jn in feet:
            low["side_conf"][:, kn.index(jn)] = 0.1
        pl = paw_agreement(low, kn, feet)
        np.savez(td / "low.npz", **low)
        code = quiet([str(td / "low.npz"), str(ri), str(td / "m8.json"), "--iters", "300", "--no-align"])
        g = {x["name"]: x for x in json.loads((td / "m8.json").read_text())["gates"]}
        ga = g.get("two_view_agreement", {"ok": True})
        check("no foot read confidently: no score, two_view_agreement fails (not left out), exit 2",
              pl["score"] is None and all(n == 0 for n in pl["frames_used"].values()) and code == 2
              and not ga["ok"] and ga.get("value") is None and sorted(ga.get("unread", [])) == sorted(feet),
              code=code, gate=ga)
        code = quiet([str(td / "low.npz"), str(ri), str(td / "m9.json"), "--iters", "300", "--no-align",
                      "--agreement-min", "-1"])
        g = {x["name"]: x for x in json.loads((td / "m9.json").read_text())["gates"]}
        check("no foot read confidently with --agreement-min -1: the gate is off, exit 0",
              code == 0 and g["two_view_agreement"]["ok"], code=code)
        # readings 20 px off at random: reprojection fails
        noisy = exam.perfect_det(info, tj, fps=24, noise_px=20.0, seed=4)
        np.savez(td / "noisy.npz", **noisy)
        code = quiet([str(td / "noisy.npz"), str(ri), str(td / "m3.json"), "--iters", "300", "--agreement-min", "-1"])
        rep = json.loads((td / "m3.json").read_text())
        g = {x["name"]: x for x in rep["gates"]}
        check("20 px noise fails reprojection, exit 2", code == 2 and not g["two_view_reprojection_p95_px"]["ok"],
              code=code)
        # refused inputs
        np.savez(td / "wrong.npz", **{**det, "front_uv": det["front_uv"][:, :5]})
        check("wrong joint count refused, exit 1", quiet([str(td / "wrong.npz"), str(ri), str(td / "m4.json")]) == 1)
        check("missing file refused, exit 1", quiet([str(td / "nope.npz"), str(ri), str(td / "m5.json")]) == 1)
    ok = all(c["pass"] for c in checks)
    print(json.dumps({"tool": "solve.py", "selftest": "pass" if ok else "fail", "checks": len(checks),
                      "failed": [c for c in checks if not c["pass"]],
                      "notes": {c["name"]: {k: v for k, v in c.items() if k not in ("name", "pass")} for c in checks
                                if len(c) > 2}}))
    return 0 if ok else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv or argv[:1] == ["selftest"]:
        return selftest()
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
