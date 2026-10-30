#!/usr/bin/env python3
"""detect.py — read every joint in both halves of a two-camera video with a trained joint reader.

Ported from patch-gg/anymove (https://github.com/patch-gg/anymove), mocap/detect.py, commit
7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0. The calibration (an ECC affine fit of the first frame
to the reference frame), the per-view square padding, the batched read and the overlay are upstream's. Changes from
upstream: argparse; --device cuda|cpu|mps (default: CUDA when present, else the CPU) with bf16 autocast only on
CUDA; the layout comes from the reader checkpoint (train.py saves it) or --rig-info, not from module constants;
gates for the calibration and the mean confidence; an ECC failure is a failed gate instead of a printed line;
one JSON report; --selftest.

usage:
    detect.py VIDEO.mp4 READER.pt REF.png OUT.npz [--overlay OVERLAY.mp4] [--device auto|cuda|cpu|mps] [--no-calib]
              [--rig-info RIG_INFO.json] [--min-conf 0.3] [--batch 32]
    detect.py --selftest
The clip is first aligned to the reference frame (a video model may resize or crop the canvas), then each frame is
split into its front and side views. OUT.npz holds front_uv, side_uv (T x J x 2, layout pixels), front_conf,
side_conf (T x J, heatmap peaks), fps, names and calib (the 2 x 3 map from video pixels to layout pixels).
The video's audio track is never read. A Mac reads on the CPU, far slower than a GPU: time one clip (124 frames
for 5 s at 24 fps, two views each) before planning a batch. --device mps is accepted, but confirm on one clip that
its det.npz matches a CPU read within a pixel before relying on it.

Gates (exit 2 when one fails):
  detect.calibration       the ECC fit converged (skipped with --no-calib, for frames already in the layout)
  detect.mean_conf_front   mean peak confidence of the front view >= --min-conf (0.3)
  detect.mean_conf_side    the same for the side view
Exit codes: 0 every gate passed (or the selftest passed), 2 a gate failed (OUT.npz is still written, to look at),
1 refused input or an error.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import pathlib
import sys
import tempfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import MIN_CONF, Layout  # noqa: E402
import model as M  # noqa: E402


def read_frames(path):
    import cv2
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f[..., ::-1])
    cap.release()
    return np.array(frames), fps


def calibrate(first, ref, L: Layout):
    """Affine map from video pixels to layout pixels, found by aligning the first frame to the reference image.
    Returns (A, converged)."""
    import cv2
    h, w = first.shape[:2]
    S = np.array([[L.W / w, 0, 0], [0, L.H / h, 0]], np.float32)  # plain stretch to start
    hw, hh = L.W // 2, L.H // 2
    a = cv2.cvtColor(cv2.resize(ref, (hw, hh)), cv2.COLOR_RGB2GRAY).astype(np.float32)
    b = cv2.cvtColor(cv2.resize(cv2.warpAffine(first, S, (L.W, L.H)), (hw, hh)), cv2.COLOR_RGB2GRAY).astype(np.float32)
    warp = np.eye(2, 3, dtype=np.float32)
    converged = True
    try:
        _, warp = cv2.findTransformECC(a, b, warp, cv2.MOTION_AFFINE,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), None, 5)
    except cv2.error:
        converged = False
    # warp maps reference (half-size) coords to frame coords; we want frame -> layout
    W2 = np.vstack([warp, [0, 0, 1]])
    W2[:2, 2] *= 2  # half-size -> full-size translation
    A = np.linalg.inv(W2) @ np.vstack([S, [0, 0, 1]])
    return A[:2].astype(np.float32), converged


def prep(view):
    import cv2
    _, ox, oy, side = M.square(view, view[2, 2])
    k = M.SIZE / side
    A = np.array([[k, 0, ox * k], [0, k, oy * k]], np.float32)
    fill = tuple(float(x) for x in view[2, 2])
    out = cv2.warpAffine(view, A, (M.SIZE, M.SIZE), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_CONSTANT, borderValue=fill)
    return out, (ox, oy, side)


def read_views(net, views, dev, autocast, bs=32):
    import torch
    uv_all, conf_all = [], []
    with torch.no_grad():
        for i in range(0, len(views), bs):
            batch = [prep(v) for v in views[i:i + bs]]
            x = torch.from_numpy(np.stack([b[0] for b in batch])).permute(0, 3, 1, 2).float().to(dev) / 255
            with autocast():
                hm = net(x).float()
            uv, conf = M.decode(hm)
            uv = uv.cpu().numpy() * M.SIZE / M.HM
            for (_, (ox, oy, side)), u in zip(batch, uv):
                uv_all.append(u * side / M.SIZE - np.array([ox, oy]))
            conf_all.append(conf.cpu().numpy())
    return np.array(uv_all), np.concatenate(conf_all)


def load(model_path, dev, backbone=None):
    import torch
    ck = torch.load(model_path, map_location="cpu", weights_only=True)  # tensors, names, numbers: safe to load
    bb = ck.get("backbone", M.BACKBONE) if backbone is None else backbone
    bb = M.stub_backbone() if bb == "stub" else bb
    net = M.reader_class()(len(ck["names"]), bb).to(dev).eval()
    net.load_state_dict(ck["state_dict"])
    return net, ck["names"], ck.get("layout")


def overlay(frames, fuv, suv, names, path, fps, L: Layout):
    import cv2
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (L.W, L.H))
    col = lambda n: (209, 60, 245) if n.endswith((".L", "_L")) else (255, 107, 47) if n.endswith((".R", "_R")) \
        else (255, 255, 255)  # BGR
    for t, f in enumerate(frames):
        img = np.ascontiguousarray(f[..., ::-1])
        for j, n in enumerate(names):
            for (u, v), x0 in ((fuv[t, j], 0), (suv[t, j], L.W_FRONT)):
                cv2.circle(img, (int(u + x0), int(v)), 4, col(n), -1, cv2.LINE_AA)
        vw.write(img)
    vw.release()


def detect(a, net=None, names=None, ck_layout=None) -> dict:
    import cv2
    if net is None:
        dev, autocast = M.device_and_autocast(a.device)
        net, names, ck_layout = load(a.reader, dev)
    else:
        dev, autocast = M.device_and_autocast(a.device)
    if ck_layout:
        L = Layout.from_dict(ck_layout)
    elif a.rig_info:
        L = Layout.from_rig_info(json.loads(pathlib.Path(a.rig_info).read_text()))
    else:
        raise ValueError("the reader carries no layout: pass --rig-info")
    frames, fps = read_frames(a.video)
    if not len(frames):
        raise ValueError(f"{a.video}: no frames read")
    ref = cv2.imread(str(a.ref))
    if ref is None:
        raise ValueError(f"{a.ref}: cannot read the reference frame")
    ref = ref[..., ::-1]
    gates = []
    if a.no_calib:  # already a layout frame (the exam)
        A = np.array([[L.W / frames.shape[2], 0, 0], [0, L.H / frames.shape[1], 0]], np.float32)
    else:
        A, conv = calibrate(frames[0], ref, L)
        gates.append({"name": "detect.calibration", "value": "converged" if conv else "plain stretch",
                      "limit": "ECC converged", "pass": bool(conv)})
    frames = np.array([cv2.warpAffine(f, A, (L.W, L.H), flags=cv2.INTER_AREA) for f in frames])
    fuv, fconf = read_views(net, [f[:, :L.W_FRONT] for f in frames], dev, autocast, a.batch)
    suv, sconf = read_views(net, [f[:, L.W_FRONT:] for f in frames], dev, autocast, a.batch)
    np.savez(a.out, front_uv=fuv, side_uv=suv, front_conf=fconf, side_conf=sconf, fps=fps, names=np.array(names), calib=A)
    for view, c in (("front", fconf), ("side", sconf)):
        gates.append({"name": f"detect.mean_conf_{view}", "value": round(float(c.mean()), 4),
                      "limit": f">= {a.min_conf}", "pass": float(c.mean()) >= a.min_conf})
    if a.overlay:
        overlay(frames, fuv, suv, names, a.overlay, fps, L)
    ok = all(g["pass"] for g in gates)
    return {"tool": "detect.py", "out": a.out, "frames": len(frames), "fps": fps, "joints": len(names),
            "device": dev, "calib": A.round(4).tolist(), "gates": gates, "ok": ok,
            "overlay": a.overlay}


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser():
    p = UsageParser(prog="detect.py", description=__doc__.split("\n")[0])
    p.add_argument("video"); p.add_argument("reader"); p.add_argument("ref"); p.add_argument("out")
    p.add_argument("--overlay"); p.add_argument("--device", choices=["auto", "cuda", "cpu", "mps"], default="auto")
    p.add_argument("--no-calib", action="store_true"); p.add_argument("--rig-info")
    p.add_argument("--min-conf", type=float, default=MIN_CONF); p.add_argument("--batch", type=int, default=32)
    return p


def run(argv) -> int:
    a = parser().parse_args(argv)
    try:
        import torch  # noqa: F401
        import cv2  # noqa: F401
    except ImportError as exc:
        print(json.dumps({"tool": "detect.py", "ok": False, "error": f"refused: {exc}"})); return 1
    try:
        r = detect(a)
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"tool": "detect.py", "ok": False, "error": f"{type(exc).__name__}: {exc}"})); return 1
    print(json.dumps(r))
    return 0 if r["ok"] else 2


def selftest() -> int:
    checks = []

    def check(name, cond, **kw):
        checks.append({"name": name, "pass": bool(cond), **kw})

    try:
        import cv2
        import torch
    except ImportError as exc:
        print(json.dumps({"tool": "detect.py", "selftest": "fail", "error": f"needs torch and opencv: {exc}"}))
        return 1
    torch.manual_seed(0)
    L = Layout.humanoid(1.7)
    rng = np.random.default_rng(0)
    ref = np.full((L.H, L.W, 3), 128, np.uint8)
    ref[L.GROUND_V:] = 152
    for _ in range(40):   # texture for ECC to lock on
        c = tuple(int(x) for x in rng.integers(0, 255, 3))
        cv2.circle(ref, (int(rng.integers(40, L.W - 40)), int(rng.integers(40, L.H - 40))), int(rng.integers(8, 30)), c, -1)
    # a video model's canvas: the frame shrunk 2 % and shifted, at another size
    T = np.array([[0.98, 0, 9.0], [0, 0.98, -6.0]], np.float32)
    shifted = cv2.warpAffine(ref, T, (L.W, L.H), borderMode=cv2.BORDER_REPLICATE)
    frame = cv2.resize(shifted, (1280, 720), interpolation=cv2.INTER_AREA)
    A, conv = calibrate(frame, ref, L)
    # a layout point p sits at T p in the shifted frame, at T p * (1280/W, 720/H) in the video; A takes it back
    p = np.array([700.0, 300.0])
    vid = (T[:, :2] @ p + T[:, 2]) * np.array([1280 / L.W, 720 / L.H])
    back = A[:, :2] @ vid + A[:, 2]
    check("ECC recovers a shrink and shift", conv and np.abs(back - p).max() < 1.5, err_px=float(np.abs(back - p).max()))
    blank = np.full_like(frame, 128)
    _, conv2 = calibrate(blank, ref, L)
    check("a featureless frame does not converge", not conv2)
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        names = ["Hips", "Head", "Hand.L", "Hand.R"]
        net = M.reader_class()(len(names), M.stub_backbone()).eval()
        torch.save({"state_dict": net.state_dict(), "names": names, "layout": L.as_dict(), "backbone": "stub"},
                   td / "r.pt")
        cv2.imwrite(str(td / "ref.png"), ref[..., ::-1])
        vw = cv2.VideoWriter(str(td / "clip.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 24, (1280, 720))
        for _ in range(6):
            vw.write(np.ascontiguousarray(frame[..., ::-1]))
        vw.release()
        vw = cv2.VideoWriter(str(td / "blank.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 24, (1280, 720))
        for _ in range(3):
            vw.write(blank)
        vw.release()
        base = [str(td / "r.pt"), str(td / "ref.png")]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = run([str(td / "clip.mp4")] + base + [str(td / "d.npz"), "--device", "cpu", "--min-conf=-1e9"])
        r = json.loads(buf.getvalue())
        with np.load(td / "d.npz") as z:   # closed before the folder is removed (Windows)
            d = {k: z[k] for k in z.files}
        check("det.npz shapes", d["front_uv"].shape == (6, 4, 2) and d["side_conf"].shape == (6, 4)
              and list(d["names"]) == names)
        # an oracle whose heatmaps peak at (224, 300) in the 448 square: the padding is undone per view
        class Oracle(torch.nn.Module):
            def forward(self, x):
                kp = torch.tensor([[[224.0, 300.0]] * len(names)]).expand(len(x), -1, -1)
                return M.heatmaps(kp)

        uv, _ = read_views(Oracle(), [ref[:, :L.W_FRONT]] * 2, "cpu", contextlib.nullcontext)
        side = max(L.W_FRONT, L.H)
        want = np.array([224 * side / M.SIZE - (side - L.W_FRONT) // 2, 300 * side / M.SIZE - (side - L.H) // 2])
        check("decode undoes the square padding", np.abs(uv - want).max() < 0.5, err=float(np.abs(uv - want).max()))
        check("calibrated clip passes, exit 0", code == 0 and r["gates"][0]["pass"], code=code)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = run([str(td / "clip.mp4")] + base + [str(td / "d2.npz"), "--device", "cpu", "--min-conf=1e9"])
        check("low confidence fails detect.mean_conf_*, exit 2", code == 2)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = run([str(td / "blank.mp4")] + base + [str(td / "d3.npz"), "--device", "cpu", "--min-conf=-1e9"])
        r = json.loads(buf.getvalue())
        check("an uncalibrated clip fails detect.calibration, exit 2", code == 2 and not r["gates"][0]["pass"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = run([str(td / "nope.mp4")] + base + [str(td / "d4.npz"), "--device", "cpu"])
        check("a missing clip is refused, exit 1", code == 1)
    ok = all(c["pass"] for c in checks)
    print(json.dumps({"tool": "detect.py", "selftest": "pass" if ok else "fail", "checks": len(checks),
                      "failed": [c for c in checks if not c["pass"]]}))
    return 0 if ok else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv or argv[:1] == ["selftest"]:
        return selftest()
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
