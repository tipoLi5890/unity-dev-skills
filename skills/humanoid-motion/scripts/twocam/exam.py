#!/usr/bin/env python3
"""exam.py — a made-up motion with known joints, filmed in the same studio, read back and scored joint by joint.

Ported from patch-gg/anymove (https://github.com/patch-gg/anymove), mocap/exam.py, commit
7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0. Changes from upstream: the root's random turn is
built in world axes (yaw about Z, pitch about X, roll about Y) and moved into the root bone's frame, so it suits an
upright Hips as well as a horizontal pelvis (upstream's axes are kept for a rig without a twocam block); the bone
angles are drawn in each bone's limit frame and written as local_quat as well; a humanoid's root is lifted
where a foot would sink below its rest height, as a real motion keeps its feet on the floor; the layout comes from rig_info.json;
the score's joint groups follow the humanoid contract (upstream's wolf groups are kept for upstream names); new:
`fk` (the rig's joints for a motion, in numpy, the same forward kinematics as solve.py), `det` (a perfect reader:
the true joints projected into both views, with optional noise and an optional different motion for the side view,
so the solve and its gates are tested without a trained reader), --selftest.

usage:
    exam.py make RIG_INFO.json MOTION.json [--seed 0] [--frames 120] [--fps 24]   random smooth motion in the limits
    exam.py fk RIG_INFO.json MOTION.json JOINTS.json                              joints per frame (names, joints, fps)
    exam.py det RIG_INFO.json JOINTS.json DET.npz [--noise-px 0] [--seed 0] [--side-joints OTHER.json]
                                                                                  a perfect reader's det.npz
    exam.py video RIG_INFO.json RENDER_DIR OUT.mp4 [--fps 24]                     front/ + side/ renders -> one video
    exam.py score TRUTH_JOINTS.json SOLVED.json [--max-mean-cm 1.0]               per-joint error in centimetres
    exam.py --selftest
TRUTH_JOINTS.json is apply_motion.py's joints.json (Blender's own joint positions) or `fk`'s output; SOLVED.json is
solve.py's motion.json (its "joints"). Prints one JSON object. Exit codes: 0 done (score: mean error within
--max-mean-cm), 2 the score's gate failed, 1 refused input or a failed selftest.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import tempfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import Layout  # noqa: E402
from skeleton import mat_to_quat  # noqa: E402


def qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def quat_to_mat(q):
    q = np.asarray(q, float)
    w, x, y, z = np.moveaxis(q / np.linalg.norm(q, axis=-1, keepdims=True), -1, 0)
    return np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], -1),
                     np.stack([2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], -1),
                     np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], -1)], -2)


def euler_xyz(e):
    """Blender Euler XYZ to matrices, numpy: Rz @ Ry @ Rx."""
    e = np.asarray(e, float)
    x, y, z = e[..., 0], e[..., 1], e[..., 2]
    cx, sx, cy, sy, cz, sz = np.cos(x), np.sin(x), np.cos(y), np.sin(y), np.cos(z), np.sin(z)
    o, l = np.zeros_like(x), np.ones_like(x)
    Rx = np.stack([l, o, o, o, cx, -sx, o, sx, cx], -1).reshape(*x.shape, 3, 3)
    Ry = np.stack([cy, o, sy, o, l, o, -sy, o, cy], -1).reshape(*x.shape, 3, 3)
    Rz = np.stack([cz, -sz, o, sz, cz, o, o, o, l], -1).reshape(*x.shape, 3, 3)
    return Rz @ Ry @ Rx


def limit_frames(info):
    if not any("limit_frame" in b for b in info["bones"]):
        return None
    return np.array([b.get("limit_frame", np.eye(3).tolist()) for b in info["bones"]], float)


def make_motion(info, seed=0, T=120, fps=24) -> dict:
    rng = np.random.default_rng(seed)
    bones = [b["name"] for b in info["bones"]]
    t = np.arange(T) / fps
    eul = np.zeros((T, len(bones), 3))

    def wave(amp):
        f = rng.uniform(0.4, 1.8, 3)
        ph = rng.uniform(0, 2 * math.pi, 3)
        w = rng.dirichlet(np.ones(3))
        return amp * (w[:, None] * np.sin(2 * math.pi * f[:, None] * t + ph[:, None])).sum(0)

    for i, b in enumerate(info["bones"]):
        if i == 0:
            continue
        lim = np.radians(np.array(b["limits_deg"], float))
        for k in range(3):
            lo, hi = lim[k]
            c = np.clip(0.0, lo + 0.25 * (hi - lo), hi - 0.25 * (hi - lo))
            amp = (0.45 if k == 0 else 0.25) * (hi - lo) / 2
            eul[:, i, k] = np.clip(c + wave(amp), lo, hi)
    yaw, pitch, roll = wave(math.radians(20)), wave(math.radians(8)), wave(math.radians(5))
    B = np.asarray(info["bones"][0]["matrix_local"], float)[:3, :3]
    quat = []
    for y, p, r in zip(yaw, pitch, roll):
        if info.get("twocam"):   # world axes, moved into the root bone's frame
            W = euler_xyz(np.array([0.0, 0, y])) @ euler_xyz(np.array([0.0, r, 0])) @ euler_xyz(np.array([p, 0, 0]))
            quat.append(mat_to_quat(B.T @ W @ B).tolist())
        else:  # upstream: pelvis basis rotation, local X = pitch, local Y (forward bone axis) = roll, local Z = yaw
            cx, sx, cy, sy, cz, sz = math.cos(p / 2), math.sin(p / 2), math.cos(r / 2), math.sin(r / 2), math.cos(y / 2), math.sin(y / 2)
            qx, qy, qz = np.array([cx, sx, 0, 0]), np.array([cy, 0, sy, 0]), np.array([cz, 0, 0, sz])
            quat.append(qmul(qz, qmul(qy, qx)).tolist())
    trans = np.stack([wave(0.05), wave(0.12), 0.03 * np.abs(np.sin(2 * math.pi * 1.2 * t))], 1)
    out = {"fps": fps, "bones": bones, "trans": trans.round(5).tolist(), "root_quat": quat,
           "euler": eul.round(5).tolist()}
    C = limit_frames(info)
    if C is not None:
        local = C[None] @ euler_xyz(np.asarray(out["euler"])) @ np.swapaxes(C, -1, -2)[None]
        out["local_quat"] = mat_to_quat(local).round(8).tolist()
    ground = (info.get("twocam") or {}).get("ground")
    if ground:   # keep the feet on or above the floor, as a real motion does, so the ground term is not an error
        names = [k["name"] for k in info["keypoints"]]
        J = fk_joints(info, out)
        idx = [names.index(n) for n in ground]
        lift = np.max(np.asarray([ground[n] for n in ground])[None] - J[:, idx, 2], 1).clip(0)
        tr = np.asarray(out["trans"])
        tr[:, 2] += lift
        out["trans"] = tr.round(5).tolist()
    return out


def fk_joints(info, motion) -> np.ndarray:
    """(T, J, 3) joints in metres: pose = parent pose x rest offset x rotation, as solve.Rig.forward."""
    bones = info["bones"]
    Bm = np.array([b["matrix_local"] for b in bones], float)
    parent = [b["parent"] for b in bones]
    off = np.stack([Bm[i] if p < 0 else np.linalg.inv(Bm[p]) @ Bm[i] for i, p in enumerate(parent)])
    eul = np.asarray(motion["euler"], float)
    T, nb = eul.shape[:2]
    C = limit_frames(info)
    R = euler_xyz(eul) if C is None else C[None] @ euler_xyz(eul) @ np.swapaxes(C, -1, -2)[None]
    root = quat_to_mat(np.asarray(motion["root_quat"], float))
    trans = np.asarray(motion["trans"], float)
    P = [None] * nb
    for i, p in enumerate(parent):
        basis = np.zeros((T, 4, 4)); basis[:, 3, 3] = 1
        basis[:, :3, :3] = root if p < 0 else R[:, i]
        if p < 0:
            M = off[i][None] @ basis
            M[:, :3, 3] += trans
        else:
            M = P[p] @ off[i][None] @ basis
        P[i] = M
    P = np.stack(P, 1)
    L = np.array([b["length"] for b in bones])
    out = []
    for k in info["keypoints"]:
        b = k["bone"]
        out.append(P[:, b, :3, 3] if k["end"] == "head" else P[:, b, :3, 1] * L[b] + P[:, b, :3, 3])
    return np.stack(out, 1)


def perfect_det(info, joints, fps=24, noise_px=0.0, seed=0, side_joints=None, conf=0.9) -> dict:
    """A det.npz a flawless reader would write, plus Gaussian noise; side_joints films a different motion on the
    side view (two halves that disagree)."""
    L = Layout.from_rig_info(info)
    rng = np.random.default_rng(seed)
    f, _ = L.project(joints)
    _, s = L.project(joints if side_joints is None else side_joints)
    f = f + rng.normal(0, noise_px, f.shape) if noise_px else f
    s = s + rng.normal(0, noise_px, s.shape) if noise_px else s
    T, J = f.shape[:2]
    names = np.array([k["name"] for k in info["keypoints"]])
    return {"front_uv": f.astype(np.float64), "side_uv": s.astype(np.float64),
            "front_conf": np.full((T, J), conf, np.float32), "side_conf": np.full((T, J), conf, np.float32),
            "fps": np.float64(fps), "names": names,
            "calib": np.array([[1, 0, 0], [0, 1, 0]], np.float32)}


def video(info, render_dir, out, fps=24):
    import cv2
    L = Layout.from_rig_info(info)
    d = pathlib.Path(render_dir)
    fr = sorted((d / "front").glob("*.png"))
    sd = sorted((d / "side").glob("*.png"))
    if not fr or len(fr) != len(sd):
        raise ValueError(f"{d}: front/ has {len(fr)} frames, side/ has {len(sd)}")
    vw = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), fps, (L.W, L.H))
    for a, b in zip(fr, sd):
        f = cv2.imread(str(a), cv2.IMREAD_UNCHANGED)[..., [2, 1, 0, 3]]
        s = cv2.imread(str(b), cv2.IMREAD_UNCHANGED)[..., [2, 1, 0, 3]]
        if f.shape[0] != L.H:  # rendered below layout size
            f = cv2.resize(f, (L.W_FRONT, L.H), interpolation=cv2.INTER_CUBIC)
            s = cv2.resize(s, (L.W_SIDE, L.H), interpolation=cv2.INTER_CUBIC)
        vw.write(np.ascontiguousarray(L.compose(f, s)[..., ::-1]))
    vw.release()
    return len(fr)


GROUPS = {"feet": ("Foot", "Toes", "ToesTip"), "legs": ("UpperLeg", "LowerLeg"),
          "arms": ("Shoulder", "UpperArm", "LowerArm", "Hand", "HandTip"), "spine": ("Hips", "Spine", "Chest", "UpperChest"),
          "head": ("Neck", "Head", "HeadTop")}
UPSTREAM_GROUPS = {"paws": ("fpaw", "ftoe", "hpaw", "htoe"),
                   "legs": ("elbow", "wrist", "knee", "hock", "shoulder", "hip_", "scap"),
                   "spine": ("hips", "spine", "chest"), "head": ("neck", "head", "nose"), "tail": ("tail",)}


def score(a: dict, b: dict) -> dict:
    names = a["names"]
    A, B = np.array(a["joints"]), np.array(b["joints"])
    if A.shape[1] != B.shape[1]:
        raise ValueError(f"truth has {A.shape[1]} joints, the solve {B.shape[1]}")
    T = min(len(A), len(B))
    e = np.linalg.norm(A[:T] - B[:T], axis=-1) * 100
    out = {"mean_cm": float(e.mean()), "median_cm": float(np.median(e)), "p95_cm": float(np.percentile(e, 95))}
    humanoid = any(n.endswith((".L", ".R")) for n in names)
    for g, keys in (GROUPS if humanoid else UPSTREAM_GROUPS).items():
        if humanoid:
            idx = [i for i, n in enumerate(names) if (n[:-2] if n.endswith((".L", ".R")) else n) in keys]
        else:
            idx = [i for i, n in enumerate(names) if any(n.startswith(k) for k in keys)]
        if idx:
            out[f"{g}_cm"] = float(e[:, idx].mean())
    worst = np.argsort(-e.mean(0))[:5]
    out["worst_joints"] = {names[i]: round(float(e[:, i].mean()), 2) for i in worst}
    return out


def selftest() -> int:
    from skeleton import build_rig_info, demo_skeleton, read_skeleton
    checks = []

    def check(name, cond):
        checks.append({"name": name, "pass": bool(cond)})

    info, _ = build_rig_info(read_skeleton(demo_skeleton()))
    info["layout"] = Layout.humanoid(1.7).as_dict()
    m = make_motion(info, seed=1, T=30)
    J = fk_joints(info, m)
    check("motion shape", np.asarray(m["euler"]).shape == (30, 22, 3) and J.shape == (30, 27, 3))
    lim = np.radians(np.array([b["limits_deg"] for b in info["bones"]]))
    e = np.asarray(m["euler"])
    check("angles inside the limits", np.all(e[:, 1:] >= lim[None, 1:, :, 0] - 1e-4) and np.all(e[:, 1:] <= lim[None, 1:, :, 1] + 1e-4))
    rest = dict(m, euler=np.zeros_like(e).tolist(), trans=np.zeros((30, 3)).tolist(), root_quat=[[1, 0, 0, 0]] * 30)
    check("rest motion lands on the rest keypoints", np.allclose(fk_joints(info, rest)[0], [k["rest"] for k in info["keypoints"]], atol=1e-6))
    lq = quat_to_mat(np.asarray(m["local_quat"]))
    C = limit_frames(info)
    check("local_quat = C E C^T", np.allclose(lq, C[None] @ euler_xyz(e) @ np.swapaxes(C, -1, -2)[None], atol=1e-6))
    check("the head stays above the hips", np.all(J[:, [k["name"] for k in info["keypoints"]].index("HeadTop"), 2] > J[:, 0, 2]))
    d = perfect_det(info, J)
    L = Layout.from_rig_info(info)
    check("perfect det reprojects exactly", np.allclose(L.unproject_front(d["front_uv"])[..., 0], J[..., 0]))
    check("same row in both views", np.allclose(d["front_uv"][..., 1], d["side_uv"][..., 1]))
    names = [k["name"] for k in info["keypoints"]]
    sc = score({"names": names, "joints": J.tolist()}, {"joints": (J + [0.005, 0, 0]).tolist()})
    check("score: a 5 mm shift reads 0.5 cm", abs(sc["mean_cm"] - 0.5) < 1e-6 and "feet_cm" in sc)
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        (td / "t.json").write_text(json.dumps({"names": names, "joints": J.tolist()}))
        (td / "s.json").write_text(json.dumps({"joints": (J + [0.02, 0, 0]).tolist()}))
        check("score gate fails on a 2 cm error, exit 2", main(["score", str(td / "t.json"), str(td / "s.json")], True) == 2)
        check("score gate passes under its limit, exit 0",
              main(["score", str(td / "t.json"), str(td / "s.json"), "--max-mean-cm", "2.5"], True) == 0)
        (td / "s.json").write_text(json.dumps({"joints": J[:, :5].tolist()}))
        check("score refuses a joint-count mismatch, exit 1", main(["score", str(td / "t.json"), str(td / "s.json")], True) == 1)
    ok = all(c["pass"] for c in checks)
    print(json.dumps({"tool": "exam.py", "selftest": "pass" if ok else "fail", "checks": len(checks),
                      "failed": [c["name"] for c in checks if not c["pass"]]}))
    return 0 if ok else 1


def main(argv=None, quiet=False) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv:
        return selftest()
    ap = argparse.ArgumentParser(prog="exam.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make"); p.add_argument("rig_info"); p.add_argument("out")
    p.add_argument("--seed", type=int, default=0); p.add_argument("--frames", type=int, default=120)
    p.add_argument("--fps", type=float, default=24)
    p = sub.add_parser("fk"); p.add_argument("rig_info"); p.add_argument("motion"); p.add_argument("out")
    p = sub.add_parser("det"); p.add_argument("rig_info"); p.add_argument("joints"); p.add_argument("out")
    p.add_argument("--noise-px", type=float, default=0.0); p.add_argument("--seed", type=int, default=0)
    p.add_argument("--side-joints", help="joints.json of a different motion for the side view (views that disagree)")
    p = sub.add_parser("video"); p.add_argument("rig_info"); p.add_argument("render_dir"); p.add_argument("out")
    p.add_argument("--fps", type=float, default=24)
    p = sub.add_parser("score"); p.add_argument("truth"); p.add_argument("solved")
    p.add_argument("--max-mean-cm", type=float, default=1.0)
    a = ap.parse_args(argv)
    emit = (lambda d: None) if quiet else (lambda d: print(json.dumps(d)))
    try:
        if a.cmd == "score":
            r = score(json.loads(pathlib.Path(a.truth).read_text()), json.loads(pathlib.Path(a.solved).read_text()))
            ok = r["mean_cm"] <= a.max_mean_cm
            r.update({"tool": "exam.py", "op": "score", "gates": [{"name": "exam.mean_cm", "value": round(r["mean_cm"], 3),
                                                                     "limit": a.max_mean_cm, "pass": ok}], "ok": ok})
            emit(r)
            return 0 if ok else 2
        info = json.loads(pathlib.Path(a.rig_info).read_text())
        if a.cmd == "make":
            m = make_motion(info, a.seed, a.frames, a.fps)
            pathlib.Path(a.out).write_text(json.dumps(m))
            emit({"tool": "exam.py", "op": "make", "out": a.out, "frames": a.frames, "ok": True})
        elif a.cmd == "fk":
            m = json.loads(pathlib.Path(a.motion).read_text())
            J = fk_joints(info, m)
            pathlib.Path(a.out).write_text(json.dumps({"names": [k["name"] for k in info["keypoints"]],
                                                       "joints": J.round(6).tolist(), "fps": m.get("fps", 24)}))
            emit({"tool": "exam.py", "op": "fk", "out": a.out, "frames": len(J), "ok": True})
        elif a.cmd == "det":
            j = json.loads(pathlib.Path(a.joints).read_text())
            if j["names"] != [k["name"] for k in info["keypoints"]]:
                raise ValueError("joints.json names are not rig_info's keypoints")
            side = None
            if a.side_joints:
                sj = json.loads(pathlib.Path(a.side_joints).read_text())
                if sj["names"] != j["names"] or len(sj["joints"]) != len(j["joints"]):
                    raise ValueError("--side-joints: names or frame count differ from JOINTS.json")
                side = np.asarray(sj["joints"])
            np.savez(a.out, **perfect_det(info, np.asarray(j["joints"]), j.get("fps", 24), a.noise_px, a.seed, side))
            emit({"tool": "exam.py", "op": "det", "out": a.out, "frames": len(j["joints"]), "ok": True})
        elif a.cmd == "video":
            n = video(info, a.render_dir, a.out, a.fps)
            emit({"tool": "exam.py", "op": "video", "out": a.out, "frames": n, "ok": True})
    except (OSError, ValueError, KeyError, json.JSONDecodeError, ImportError) as exc:
        emit({"tool": "exam.py", "ok": False, "error": f"refused: {type(exc).__name__}: {exc}"})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
