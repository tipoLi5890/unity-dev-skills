#!/usr/bin/env python3
"""train.py — teach the joint reader one character, from the rendered dataset.

Ported from patch-gg/anymove (https://github.com/patch-gg/anymove), mocap/train.py, commit
7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0. The augmentation (random backdrop, framing,
colour, blur, rescale, noise and JPEG jitter, the divider), the loss, the optimiser, the schedule and the held-out
split are upstream's. Changes from upstream: argparse options instead of positional numbers; --device (CUDA by
default; bf16 autocast only on CUDA) and a refusal on MPS: training is not supported on a Mac, train on a CUDA
machine and copy reader.pt back; --allow-cpu for a smoke run only; --workers instead of a fixed 10 / 4; the layout
(ground row, backdrop) from rig_info.json, saved in the checkpoint with the joint names so detect.py needs no other
file; a held-out error gate; --backbone stub and --selftest, which train a tiny stand-in on a synthetic dataset;
the dataset class at module level (DataLoader workers start under spawn, so Windows hosts use them) and the loaders
built once with persistent, pinned, prefetching workers (--follow rebuilds the training loader each epoch, for a
dataset still being rendered); uint8 batches normalised on the GPU; the loss read every 50 steps instead of every
step; TF32 and a fused AdamW on CUDA; the best epoch's checkpoint kept; the warmup's length an option
(--warmup-steps); an optional plateau stop counted after the warmup (--patience, off by default; --min-delta) and
--target-px for a quick preview; --cache (the renders decoded once into a uint8 memmap); --init (warm start from
another reader with the same joints, 12 epochs by default).

usage:
    train.py DATASET_DIR RIG_INFO.json OUT.pt [--epochs N] [--batch 20] [--device cuda] [--workers 8]
             [--max-val-px 8] [--patience 0] [--min-delta 0.1] [--warmup-steps 300] [--target-px 0] [--cache]
             [--init OLD.pt] [--follow] [--backbone facebook/dinov2-with-registers-base] [--allow-cpu]
    train.py --selftest
DATASET_DIR holds render_dataset.py's <i>_front.png, <i>_side.png and <i>_meta.json. Every sample gives two
training images (front and side). The renders are transparent, so each is laid on a fresh random backdrop, then
jittered in framing, colour, sharpness and compression, the ways a video model's frames differ from a clean render.
Samples whose index is a multiple of 25 (4 %) are held out; their mean joint error in layout pixels is measured
after each epoch on fixed (unaugmented) views, so the numbers stay comparable between epochs and runs.

--epochs is 20 from scratch and 12 with --init (when not given); the learning rate warms up over --warmup-steps
(300) and then follows a cosine over the epochs, which run in full by default. OUT.pt is always the best epoch's
checkpoint, and the gate reads that epoch. --patience N (0, off) stops once N evals in a row each improve the best by
less than --min-delta px (0.1), counting only evals after the warmup has ended: a warm start's held-out error rises
while its learning rate warms up, and a stop before the cosine ends leaves a reader that reads video less well.
--target-px PX stops once the held-out mean is at or under PX: for a quick preview reader only (0, the default,
turns it off).
--cache decodes every PNG once into DATASET_DIR/.twocam_cache/ (front.u8, side.u8, index.json; about 0.75 MB per
view at scale 0.6) and trains from it; a render rewritten since is decoded again. --init OLD.pt starts from another
reader whose joint names match this rig_info's exactly (a reader of another character on the same contract);
different names are refused. --follow re-reads the dataset folder every epoch, for training while it renders.
Requirements: a CUDA GPU with about 12 GB free at batch 20 (lower --batch on less); torch, transformers,
opencv-python-headless, numpy.

Gate: reader.val_mean_px (the best epoch's held-out mean over both views) <= --max-val-px (8 x H / 768 by default).
Prints one JSON object at the end (progress lines go to stderr). Exit codes: 0 trained and the gate passed (or the
selftest passed), 2 the gate failed (the checkpoint is still written), 1 refused input or an error.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import BG, FLOOR, Layout  # noqa: E402
import model as M  # noqa: E402

VIEWS = ("front", "side")
LOG_EVERY = 50
WARMUP_STEPS = 300
CACHE_DIR = ".twocam_cache"
CACHE_VERSION = 1


def backdrop(h, w, ground, rng):
    g = rng.uniform(95, 175)
    tint = rng.uniform(-6, 6, 3)
    img = np.empty((h, w, 3), np.float32)
    img[:] = g + tint
    img += np.linspace(-1, 1, h)[:, None, None] * rng.uniform(-10, 10)
    img[ground:] += rng.uniform(5, 35) * (1 if rng.random() < 0.85 else -1)
    return img


def photometric(img, rng):
    import cv2
    img = img.astype(np.float32)
    if rng.random() < 0.8:  # brightness, contrast, saturation, hue
        img = img * rng.uniform(0.75, 1.25) + rng.uniform(-20, 20)
        m = img.mean()
        img = (img - m) * rng.uniform(0.75, 1.25) + m
        hsv = cv2.cvtColor(img.clip(0, 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
        hsv[..., 0] = (hsv[..., 0] + rng.uniform(-5, 5)) % 180
        hsv[..., 1] *= rng.uniform(0.7, 1.3)
        img = cv2.cvtColor(hsv.clip(0, 255).astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)
    if rng.random() < 0.3:
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.3, 1.5))
    if rng.random() < 0.3:
        f = rng.uniform(0.4, 0.8)
        small = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        img = cv2.resize(small, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR)
    if rng.random() < 0.2:
        img = img + rng.normal(0, rng.uniform(2, 8), img.shape)
    img = img.clip(0, 255).astype(np.uint8)
    if rng.random() < 0.5:
        ok, buf = cv2.imencode(".jpg", img[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(35, 90))])
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)[..., ::-1]
    return img


def read_rgba(png) -> np.ndarray | None:
    """A render as H x W x 4 uint8 RGBA (alpha 255 when the file has none); None when unreadable."""
    import cv2
    img = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 3:
        img = np.concatenate([img, np.full(img.shape[:2] + (1,), 255, img.dtype)], -1)
    if img.dtype != np.uint8:
        img = (img >> 8).astype(np.uint8)
    return np.ascontiguousarray(img[..., [2, 1, 0, 3]])


def view_sample(meta_path, view, train, layout: Layout, i, meta=None, rgba=None):
    """One augmented view: (image 448 x 448 x 3 uint8, keypoints in SIZE px, (ox, oy, side, scale)).
    Held-out views (train False) are not augmented: the same index gives the same view every time."""
    import cv2
    rng = np.random.default_rng() if train else np.random.default_rng(i)
    meta = meta or json.loads(pathlib.Path(meta_path).read_text())
    s = meta["scale"]
    if rgba is None:
        rgba = read_rgba(str(meta_path).replace("_meta.json", f"_{view}.png"))
        if rgba is None:
            raise OSError(f"cannot read the {view} render of {meta_path}")
    rgba = rgba.astype(np.float32)
    h, w = rgba.shape[:2]
    kp = np.array(meta[f"{view}_uv"], np.float32) * s
    if train:
        bg = backdrop(h, w, round(layout.GROUND_V * s), rng)
    else:
        bg = np.empty((h, w, 3), np.float32); bg[:] = BG; bg[round(layout.GROUND_V * s):] = FLOOR
    a = rgba[..., 3:] / 255
    img = rgba[..., :3] * a + bg * (1 - a)
    if train and rng.random() < 0.7:  # the divider at the shared edge
        img[:, -2:] = 34 if view == "front" else img[:, -2:]
        img[:, :2] = 34 if view == "side" else img[:, :2]
    _, ox, oy, side = M.square(img, bg[0, 0])
    k = M.SIZE / side
    A = np.array([[k, 0, ox * k], [0, k, oy * k]], np.float32)
    if train:  # framing jitter: scale, small rotation, shift
        sc, rot = rng.uniform(0.85, 1.15), math.radians(rng.uniform(-4, 4))
        c = M.SIZE / 2
        R = cv2.getRotationMatrix2D((c, c), math.degrees(rot), sc)
        R[:, 2] += rng.uniform(-0.05, 0.05, 2) * M.SIZE
        A = R @ np.vstack([A, [0, 0, 1]])
    out = cv2.warpAffine(img, A.astype(np.float32), (M.SIZE, M.SIZE), flags=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=tuple(float(x) for x in bg[0, 0]))
    kp = kp @ A[:, :2].T + A[:, 2]
    if train:
        out = photometric(out, rng)
    return np.ascontiguousarray(out.clip(0, 255).astype(np.uint8)), kp.astype(np.float32), \
        np.array([ox, oy, side, s], np.float32)


# --- the decode cache -----------------------------------------------------------------------------------------
def _stamp(path: pathlib.Path) -> list:
    st = path.stat()
    return [st.st_size, st.st_mtime_ns]


def build_cache(data, metas, log=lambda m: None, threads=8) -> dict:
    """Decode every sample's two renders once into DATASET/.twocam_cache/{front,side}.u8 (N x h x w x 4 uint8
    memmaps) and index.json {stem: [row, stamp_front, stamp_side]}. Rows whose PNG changed are decoded again, new
    samples are appended, a change of render size starts the cache over. Returns {"dir", "shape", "rows"}."""
    from concurrent.futures import ThreadPoolExecutor
    d = pathlib.Path(data) / CACHE_DIR
    d.mkdir(exist_ok=True)
    stems = [str(m.name)[:-len("_meta.json")] for m in metas]
    first = {v: read_rgba(pathlib.Path(data) / f"{stems[0]}_{v}.png") for v in VIEWS}
    if any(x is None for x in first.values()):
        raise OSError(f"cannot read the renders of {stems[0]}")
    shape = {v: list(first[v].shape[:2]) for v in VIEWS}
    idx = {}
    try:
        old = json.loads((d / "index.json").read_text())
        if old.get("version") == CACHE_VERSION and old.get("shape") == shape and \
                all((d / f"{v}.u8").exists() for v in VIEWS):
            idx = old["rows"]
    except (OSError, ValueError, KeyError):
        idx = {}
    if not idx:
        for v in VIEWS:
            (d / f"{v}.u8").unlink(missing_ok=True)
    nrows = max([r[0] for r in idx.values()], default=-1) + 1
    todo = []
    for st in stems:
        stamps = [_stamp(pathlib.Path(data) / f"{st}_{v}.png") for v in VIEWS]
        if st in idx and idx[st][1:] == stamps:
            continue
        row = idx[st][0] if st in idx else nrows
        nrows += st not in idx
        todo.append((st, row, stamps))
    per = {v: shape[v][0] * shape[v][1] * 4 for v in VIEWS}
    for v in VIEWS:   # grow the files to nrows rows
        with open(d / f"{v}.u8", "ab") as fh:
            fh.truncate(max(nrows, 1) * per[v])
    mm = {v: np.memmap(d / f"{v}.u8", np.uint8, "r+", shape=(max(nrows, 1), *shape[v], 4)) for v in VIEWS}

    def one(job):
        st, row, stamps = job
        imgs = {v: read_rgba(pathlib.Path(data) / f"{st}_{v}.png") for v in VIEWS}
        if any(imgs[v] is None or list(imgs[v].shape[:2]) != shape[v] for v in VIEWS):
            return st, None
        for v in VIEWS:
            mm[v][row] = imgs[v]
        return st, [row] + stamps

    if todo:
        log(f"cache: decoding {len(todo)} samples into {d}")
        with ThreadPoolExecutor(max(1, threads)) as ex:
            for st, entry in ex.map(one, todo):
                if entry is None:
                    idx.pop(st, None)   # another size: read from its PNGs
                else:
                    idx[st] = entry
        for v in VIEWS:
            mm[v].flush()
    mm.clear()   # the decode closure keeps the dict alive: empty it, so no mapping outlives this call
    tmp = d / "index.json.tmp"
    tmp.write_text(json.dumps({"version": CACHE_VERSION, "shape": shape, "rows": idx}))
    os.replace(tmp, d / "index.json")
    return {"dir": str(d), "shape": shape, "rows": {k: v[0] for k, v in idx.items()}, "nrows": max(nrows, 1)}


class Views:
    """Both views of a list of samples, as a map-style dataset: (image uint8 H x W x 3, keypoints, geometry, view).
    Defined at module level and holding only paths, the layout and the cache index, so it pickles: DataLoader
    workers start under spawn (Windows, macOS). The cache memmaps open lazily in each worker."""

    def __init__(self, metas, train, layout: Layout, cache: dict | None = None):
        self.metas = [str(m) for m in metas]
        self.train = bool(train)
        self.layout = layout
        self.cache = cache
        self._mm = None
        self._meta = {}

    def __getstate__(self):
        st = dict(self.__dict__)
        st["_mm"], st["_meta"] = None, {}
        return st

    def close(self):
        """Drop the cache memmaps (every row read was copied out), so the files can be removed or rewritten: Windows
        refuses to delete a file a live mapping holds."""
        self._mm = None

    def __len__(self):
        return 2 * len(self.metas)

    def _cached(self, meta_path, view):
        if not self.cache:
            return None
        row = self.cache["rows"].get(pathlib.Path(meta_path).name[:-len("_meta.json")])
        if row is None:
            return None
        if self._mm is None:
            d = pathlib.Path(self.cache["dir"])
            self._mm = {v: np.memmap(d / f"{v}.u8", np.uint8, "r", shape=(self.cache["nrows"], *self.cache["shape"][v], 4))
                        for v in VIEWS}
        return np.array(self._mm[view][row])

    def item(self, i):
        mp, view = self.metas[i // 2], VIEWS[i % 2]
        meta = self._meta.get(mp)
        if meta is None:
            meta = self._meta[mp] = json.loads(pathlib.Path(mp).read_text())
        return view_sample(mp, view, self.train, self.layout, i, meta=meta, rgba=self._cached(mp, view))

    def __getitem__(self, i):
        import torch
        img, kp, geo = self.item(i)
        return torch.from_numpy(img), torch.from_numpy(kp), torch.from_numpy(geo), i % 2


def split(data):
    metas = sorted(pathlib.Path(data).glob("*_meta.json"))
    val = [m for m in metas if int(m.name[:5]) % 25 == 0]
    return [m for m in metas if int(m.name[:5]) % 25 != 0], val


def loader(ds, a, shuffle, cuda, workers, persistent=True):
    from torch.utils.data import DataLoader
    kw = {"batch_size": a.batch, "shuffle": shuffle, "num_workers": workers, "pin_memory": cuda,
          "drop_last": shuffle and len(ds) > a.batch}
    if workers > 0:
        kw.update(persistent_workers=persistent, prefetch_factor=4)
    return DataLoader(ds, **kw)


def to_device(x, dev):
    """uint8 B x H x W x 3 on the host -> float B x 3 x H x W in [0, 1] on the device (the copy is a quarter of
    float32's), contiguous like the per-sample tensors it replaces, so the network computes the same numbers."""
    return x.to(dev, non_blocking=True).permute(0, 3, 1, 2).contiguous().float().div_(255)


def load_init(path, names, backbone):
    import torch
    ck = torch.load(path, map_location="cpu", weights_only=True)
    if list(ck.get("names", [])) != list(names):
        theirs = list(ck.get("names", []))
        diff = sorted(set(theirs) ^ set(names))[:8]
        raise ValueError(f"refused: --init {path} reads {len(theirs)} joints, rig_info has {len(names)}; the names "
                         f"or their order differ ({diff or 'order'}): a warm start needs the same joint set")
    if ck.get("backbone", M.BACKBONE) != backbone:
        raise ValueError(f"refused: --init {path} was trained on backbone {ck.get('backbone')}, not {backbone}")
    return ck


def evaluate(net, vl, dev, autocast):
    import torch
    errs = {v: [] for v in VIEWS}
    with torch.no_grad():
        for x, kp, geo, view in vl:
            with autocast():
                pred = net(to_device(x, dev)).float()
            uv, _ = M.decode(pred)
            uv = uv.cpu() * M.SIZE / M.HM
            # back to layout pixels: undo resize, padding and the render scale
            lay = lambda p: (p * geo[:, None, 2:3] / M.SIZE - geo[:, None, :2]) / geo[:, None, 3:4]
            e = (lay(uv) - lay(kp)).norm(dim=-1)
            for r in range(len(x)):
                errs[VIEWS[int(view[r])]].append(e[r].numpy())
    return {v: float(np.mean(errs[v])) for v in VIEWS}


def train(a, log=print) -> dict:
    """One training run; every dataset it opened drops its cache memmaps when it ends (or raises), so the cache
    files are not held open after it (Windows will not remove a mapped file)."""
    import gc
    opened = []

    def views(*args):
        opened.append(Views(*args))
        return opened[-1]
    try:
        return _train(a, log, views)
    finally:
        for ds in opened:
            ds.close()
        gc.collect()


def _train(a, log, views) -> dict:
    import torch
    import torch.nn.functional as F
    info = json.loads(pathlib.Path(a.rig_info).read_text())
    layout = Layout.from_rig_info(info)
    names = [k["name"] for k in info["keypoints"]]
    backbone_id = a.backbone if a.backbone != "stub" else "stub"
    init = load_init(a.init, names, backbone_id) if a.init else None
    dev, autocast = M.device_and_autocast(a.device)
    cuda = dev == "cuda"
    if cuda:
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.benchmark = True
    tr, val = split(a.dataset)
    if not tr or not val:
        raise ValueError(f"{a.dataset}: {len(tr)} training and {len(val)} held-out samples; need both "
                         "(held out = index a multiple of 25)")
    workers = max(0, min(a.workers, os.cpu_count() or 1))
    cache = build_cache(a.dataset, tr + val, log, threads=max(1, workers)) if a.cache else None
    log(f"{len(tr)} train / {len(val)} val samples, {len(names)} joints, device {dev}, {workers} workers"
        + (f", cache {len(cache['rows'])} samples" if cache else ""))
    vl = loader(views(val, False, layout, cache), a, False, cuda, min(4, workers))
    dl = None if a.follow else loader(views(tr, True, layout, cache), a, True, cuda, workers)
    backbone = M.stub_backbone() if a.backbone == "stub" else a.backbone
    net = M.reader_class()(len(names), backbone)
    if init is not None:
        net.load_state_dict(init["state_dict"])
    net = net.to(dev)
    head = [p for n, p in net.named_parameters() if not n.startswith("backbone")]
    groups = [{"params": list(net.backbone.parameters()), "lr": 2e-5}, {"params": head, "lr": 1e-3}]
    try:
        opt = torch.optim.AdamW(groups, weight_decay=0.05, fused=cuda)
    except (TypeError, RuntimeError):
        opt = torch.optim.AdamW(groups, weight_decay=0.05)
    base = [g["lr"] for g in opt.param_groups]
    step, t0 = 0, time.time()
    warm = max(1, a.warmup_steps if a.warmup_steps is not None else WARMUP_STEPS if a.backbone != "stub" else 1)
    limit = a.max_val_px if a.max_val_px is not None else 8.0 * layout.H / 768
    target = a.target_px or 0.0   # 0: no target, the plateau or the cap ends training
    history, windows, first_loss = [], [], None
    best, best_ep, stale, stopped = math.inf, None, 0, "epochs"
    run_loss, run_n = torch.zeros((), device=dev), 0
    for ep in range(a.epochs):
        if a.follow:   # samples still being rendered join at the next epoch
            tr, _ = split(a.dataset)
            dl = loader(views(tr, True, layout, cache), a, True, cuda, workers, persistent=False)
        net.train()
        nb = len(dl)
        for bi_, (x, kp, _, _) in enumerate(dl):
            f = 0.5 * (1 + math.cos(math.pi * (ep + bi_ / nb) / a.epochs)) * min(1, (step + 1) / warm)
            for g, b0 in zip(opt.param_groups, base):
                g["lr"] = b0 * f
            x, kp = to_device(x, dev), kp.to(dev, non_blocking=True)
            with autocast():
                pred = net(x)
            loss = F.mse_loss(pred.float(), M.heatmaps(kp)) * 1000
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            step += 1
            run_loss += loss.detach()
            run_n += 1
            if first_loss is None:
                first_loss = float(loss.item())   # one sync, at the first step
            if step % LOG_EVERY == 0:   # the only other sync: the window's mean every LOG_EVERY steps
                windows.append(float(run_loss.item()) / run_n)
                run_loss.zero_(); run_n = 0
                log(f"ep {ep} step {step} loss {windows[-1]:.4f} lr {f:.3f} {time.time() - t0:.0f}s")
        net.eval()
        msg = evaluate(net, vl, dev, autocast)
        mean = float(np.mean([msg[v] for v in VIEWS]))
        history.append({**msg, "mean": round(mean, 4)})
        score = mean if math.isfinite(mean) else math.inf   # a NaN epoch never beats a real one
        # the plateau counts only once the warmup has ended: the held-out error may rise while the rate climbs
        stale = (stale + 1 if best - score < a.min_delta else 0) if step >= warm else 0
        if best_ep is None or score < best:   # the first epoch is always written: no older OUT.pt survives
            best, best_ep = score, ep
            torch.save({"state_dict": net.state_dict(), "names": names, "epoch": ep, "val": msg,
                        "layout": layout.as_dict(), "backbone": backbone_id}, a.out)
        log(f"epoch {ep} val mean px error (layout pixels) front {msg['front']:.2f} side {msg['side']:.2f}"
            f" best {best:.2f} (epoch {best_ep}) {time.time() - t0:.0f}s")
        if target > 0 and mean <= target:
            stopped = "target"
            break
        if a.patience and stale >= a.patience:
            stopped = "plateau"
            break
    if run_n:
        windows.append(float(run_loss.item()) / run_n)
    gate = {"name": "reader.val_mean_px", "value": round(best, 3), "limit": round(limit, 3), "pass": best <= limit}
    return {"tool": "train.py", "out": a.out, "epochs": a.epochs, "epochs_run": len(history), "stopped": stopped,
            "best_epoch": best_ep, "target_px": round(target, 3), "patience": a.patience, "warmup_steps": warm,
            "steps": step, "device": dev, "workers": workers,
            "cache": bool(cache), "init": a.init, "seconds": round(time.time() - t0, 1), "val": history,
            "first_loss": first_loss, "last_loss": windows[-1] if windows else None,
            "gates": [gate], "ok": gate["pass"]}


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser():
    p = UsageParser(prog="train.py", description=__doc__.split("\n")[0])
    p.add_argument("dataset"); p.add_argument("rig_info"); p.add_argument("out")
    p.add_argument("--epochs", type=int, help="the cosine schedule's span, run in full by default (20; 12 with --init)")
    p.add_argument("--batch", type=int, default=20)
    p.add_argument("--device", choices=["cuda", "mps", "cpu"], default="cuda")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--max-val-px", type=float)
    p.add_argument("--target-px", type=float, default=0.0, help="stop once the held-out mean is at or under it: quick "
                   "previews only (0, the default, is off)")
    p.add_argument("--patience", type=int, default=0, help="stop after this many evals in a row past the warmup improve "
                   "the best by less than --min-delta (0, the default, never)")
    p.add_argument("--min-delta", type=float, default=0.1)
    p.add_argument("--warmup-steps", type=int, help=f"steps of learning-rate warmup ({WARMUP_STEPS}; 1 with the stub)")
    p.add_argument("--cache", action="store_true", help="decode the renders once into a uint8 memmap")
    p.add_argument("--init", help="warm start from this reader (same joint names)")
    p.add_argument("--follow", action="store_true", help="re-read the dataset folder every epoch")
    p.add_argument("--backbone", default=M.BACKBONE, help="a Hugging Face id, or 'stub' (selftests only)")
    p.add_argument("--allow-cpu", action="store_true", help="smoke runs on the CPU (hours per epoch with DINOv2)")
    return p


def epochs_cap(a) -> int:
    """--epochs as given; else 12 for a warm start (--init), 20 from scratch."""
    return a.epochs if a.epochs is not None else 12 if a.init else 20


def run(argv, log=lambda m: print(m, file=sys.stderr, flush=True)) -> int:
    a = parser().parse_args(argv)
    a.epochs = epochs_cap(a)
    if a.device == "mps":
        print(json.dumps({"tool": "train.py", "ok": False, "error": "refused: training is not supported on a Mac "
                          "(MPS). Train on a CUDA machine and copy reader.pt back; detect.py reads on the CPU."}))
        return 1
    if a.device == "cpu" and not a.allow_cpu:
        print(json.dumps({"tool": "train.py", "ok": False, "error": "refused: training needs CUDA; --allow-cpu is "
                          "for smoke runs only"}))
        return 1
    try:
        import torch  # noqa: F401
        import cv2  # noqa: F401
    except ImportError as exc:
        print(json.dumps({"tool": "train.py", "ok": False, "error": f"refused: {exc}"})); return 1
    try:
        r = train(a, log)
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"tool": "train.py", "ok": False, "error": f"{type(exc).__name__}: {exc}"})); return 1
    print(json.dumps(r))
    return 0 if r["ok"] else 2


def make_synthetic_dataset(d: pathlib.Path, layout: Layout, names, n=26, scale=0.25, seed=0):
    """Coloured discs at random joint positions on transparent renders, with their metas: a dataset with known
    answers for the selftests."""
    import cv2
    rng = np.random.default_rng(seed)
    d.mkdir(parents=True, exist_ok=True)
    cols = [(255, 60, 60), (60, 255, 60), (60, 60, 255), (240, 240, 60)]
    for i in range(n):
        meta = {"scale": scale}
        for view, w in (("front", layout.W_FRONT), ("side", layout.W_SIDE)):
            uv = np.stack([rng.uniform(0.2 * w, 0.8 * w, len(names)),
                           rng.uniform(0.2 * layout.H, 0.8 * layout.GROUND_V, len(names))], 1)
            img = np.zeros((round(layout.H * scale), round(w * scale), 4), np.uint8)
            for j, (u, v) in enumerate(uv * scale):
                c = cols[j % len(cols)]
                cv2.circle(img, (int(round(u)), int(round(v))), max(2, int(14 * scale)), (c[2], c[1], c[0], 255), -1)
            cv2.imwrite(str(d / f"{i:05d}_{view}.png"), img)
            meta[f"{view}_uv"] = uv.round(3).tolist()
        (d / f"{i:05d}_meta.json").write_text(json.dumps(meta))


def selftest() -> int:
    checks = []

    def check(name, cond, **kw):
        checks.append({"name": name, "pass": bool(cond), **kw})

    try:
        import torch
        import cv2
    except ImportError as exc:
        print(json.dumps({"tool": "train.py", "selftest": "fail", "error": f"needs torch and opencv: {exc}"}))
        return 1
    torch.manual_seed(0)
    kp = torch.tensor([[[100.3, 200.7], [10.0, 437.0]]])
    uv, conf = M.decode(M.heatmaps(kp))
    check("heatmap peak decodes back to the keypoint", torch.allclose(uv * M.SIZE / M.HM, kp, atol=0.3))
    names = ["Hips", "Head", "Hand.L", "Hand.R"]
    L = Layout.humanoid(1.7)
    info = {"layout": L.as_dict(), "keypoints": [{"name": n} for n in names]}
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        make_synthetic_dataset(td / "ds", L, names)
        (td / "ri.json").write_text(json.dumps(info))
        metas, val = split(td / "ds")
        img, k, geo = view_sample(val[0], "front", False, L, 0)
        meta = json.loads(val[0].read_text())
        ok = True
        for j, (u, v) in enumerate(k):   # the warped disc sits on the warped keypoint
            ok &= img[int(round(v)), int(round(u))].max() > 200
        check("held-out view: discs stay on their keypoints after square and resize", ok)
        lay = (k * geo[2] / M.SIZE - geo[:2]) / geo[3]
        check("geometry undoes back to layout px", np.allclose(lay, meta["front_uv"], atol=1e-2))
        img, k, _ = view_sample(metas[0], "side", True, L, 1)
        check("augmented view is 448 square", img.shape == (448, 448, 3) and k.shape == (4, 2))
        base = ["--batch", "4", "--device", "cpu", "--workers", "0", "--backbone", "stub", "--allow-cpu"]
        quiet = lambda m: None
        import contextlib, io, pickle

        def go(out, *extra, epochs=2):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = run([str(td / "ds"), str(td / "ri.json"), str(td / out), "--epochs", str(epochs)] + base
                           + list(extra), quiet)
            return code, json.loads(buf.getvalue())

        code, r = go("r.pt", "--target-px", "0")
        check("a stand-in barely trained fails reader.val_mean_px, exit 2", code == 2 and not r["gates"][0]["pass"],
              val=r["gates"][0]["value"])
        check("loss is finite", r["last_loss"] is not None and math.isfinite(r["last_loss"]))
        ck = torch.load(td / "r.pt", map_location="cpu", weights_only=True)
        check("checkpoint carries names and layout", ck["names"] == names and ck["layout"]["H"] == L.H)
        code, r = go("r2.pt", "--max-val-px", "1e9", "--target-px", "0")
        check("the same run passes under a loose limit, exit 0", code == 0)
        # the best epoch is kept and gated, not the last
        code, r = go("best.pt", "--target-px", "0", "--patience", "0", epochs=3)
        means = [h["mean"] for h in r["val"]]
        ck = torch.load(td / "best.pt", map_location="cpu", weights_only=True)
        check("OUT.pt is the best epoch's and the gate reads it", r["epochs_run"] == 3
              and r["best_epoch"] == int(np.argmin(means)) and ck["epoch"] == r["best_epoch"]
              and abs(r["gates"][0]["value"] - min(means)) < 2e-3, means=means, best=r["best_epoch"])
        code, r = go("d.pt", "--max-val-px", "1e9", epochs=2)
        cap = lambda *x: epochs_cap(parser().parse_args(["d", "r", "o", *x]))   # noqa: E731
        check("by default no --target-px and no plateau stop: a run goes to --epochs; 20 from scratch, 12 with "
              "--init, a given --epochs wins", r["epochs_run"] == 2 and r["stopped"] == "epochs"
              and r["target_px"] == 0 and r["patience"] == 0 and parser().parse_args(["d", "r", "o"]).patience == 0
              and cap() == 20 and cap("--init", "x.pt") == 12 and cap("--init", "x.pt", "--epochs", "5") == 5)
        code, r = go("t.pt", "--target-px", "1e9", epochs=5)
        check("early stop at --target-px after the first eval", r["epochs_run"] == 1 and r["stopped"] == "target")
        code, r = go("p.pt", "--target-px", "0", "--patience", "2", "--min-delta", "1e9", epochs=6)
        check("early stop after --patience evals without a --min-delta gain", r["epochs_run"] == 3
              and r["stopped"] == "plateau", run=r["epochs_run"])
        # a warm start: the held-out error rises while the rate warms up, then falls. With the patience on, the
        # evals inside the warmup do not count, so the run reaches the fall and keeps its best epoch
        real_eval = globals()["evaluate"]

        def rising_then_falling(*a_, **k_):
            x = next(seq)
            return {v: x for v in VIEWS}
        runs = {}
        try:
            for warm in ("30", "1"):   # 12 steps an epoch: the first two evals fall inside 30 steps
                seq = iter([3.0, 3.6, 4.2, 2.5, 2.45, 2.44, 2.43, 2.42])
                globals()["evaluate"] = rising_then_falling
                runs[warm] = go(f"warm{warm}.pt", "--patience", "2", "--warmup-steps", warm, "--max-val-px", "1e9",
                                epochs=8)[1]
        finally:
            globals()["evaluate"] = real_eval
        r, r1 = runs["30"], runs["1"]
        check("--patience with a rising held-out error during the warmup: no stop inside the warmup, the best epoch "
              "after it is kept", r.get("steps", 0) // max(r.get("epochs_run", 1), 1) == 12 and r.get("epochs_run") == 6
              and r.get("stopped") == "plateau" and r.get("best_epoch") == 5
              and r1.get("epochs_run") == 3 and r1.get("best_epoch") == 0,
              run=(r.get("epochs_run"), r.get("best_epoch"), r.get("steps")), no_warmup=(r1.get("epochs_run"),
                                                                                         r1.get("best_epoch")))
        # the dataset pickles (DataLoader workers under spawn) and a spawned worker reads it
        ds = Views(metas, True, L)
        back = pickle.loads(pickle.dumps(ds))
        check("Views pickles", len(back) == len(ds) and back.item(1)[0].shape == (448, 448, 3))
        xb = torch.stack([ds[i][0] for i in (0, 1, 2)])
        xd = to_device(xb, "cpu")
        check("a uint8 batch normalised on the device = the per-sample float tensors, contiguous",
              xd.is_contiguous() and torch.equal(xd, torch.stack([x.permute(2, 0, 1).float() / 255 for x in xb])))
        real_eval = globals()["evaluate"]
        globals()["evaluate"] = lambda *a_, **k_: {v: float("nan") for v in VIEWS}
        try:
            (td / "nan.pt").write_bytes(b"an older reader")
            code, r = go("nan.pt", "--target-px", "0", epochs=2)
        finally:
            globals()["evaluate"] = real_eval
        try:
            ck = torch.load(td / "nan.pt", map_location="cpu", weights_only=True)
        except Exception:   # the older file was left in place
            ck = {}
        check("a NaN held-out error: OUT.pt is this run's, the gate fails, exit 2",
              code == 2 and not r["gates"][0]["pass"] and ck.get("names") == names and ck.get("epoch") == 0)
        code, r = go("w.pt", "--target-px", "0", "--workers", "2", "--max-val-px", "1e9", epochs=1)
        check("two spawned DataLoader workers train, exit 0", code == 0 and r["workers"] == 2, err=r.get("error"))
        # --cache: the same held-out views from the memmap as from the PNGs; a rewritten PNG is decoded again
        c = build_cache(td / "ds", metas + val)
        plain, cached = Views(val, False, L), Views(val, False, L, c)
        same = all(np.array_equal(plain.item(i)[0], cached.item(i)[0]) and np.array_equal(plain.item(i)[1], cached.item(i)[1])
                   for i in range(len(plain)))
        check("--cache round trip: cached views equal the PNG views", same and len(c["rows"]) == len(metas) + len(val))
        cached.close()
        png = td / "ds" / f"{val[0].name[:5]}_front.png"
        im = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
        im[..., :3] = 255 - im[..., :3]
        cv2.imwrite(str(png), im)
        os.utime(png, ns=(time.time_ns(), time.time_ns() + 10**9))
        sv = Views(val, False, L, c)
        stale = sv.item(0)[0]
        sv.close()
        c2 = build_cache(td / "ds", metas + val)
        fv = Views(val, False, L, c2)
        fresh = fv.item(0)[0]
        fv.close()
        check("a rewritten render is decoded again", np.array_equal(fresh, Views(val, False, L).item(0)[0])
              and not np.array_equal(stale, fresh) and c2["rows"] == c["rows"])
        code, r = go("c.pt", "--cache", "--target-px", "0", "--max-val-px", "1e9", epochs=1)
        check("training from the cache, exit 0", code == 0 and r["cache"])
        import gc
        gc.collect()
        live = [o for o in gc.get_objects() if type(o) is np.memmap and str(td) in str(getattr(o, "filename", ""))]
        check("no cache memmap is left open after training and the closed views (Windows removes the folder)",
              not live, live=len(live))
        # --init: a reader with the same joints warm-starts; other joints are refused
        code, r = go("i.pt", "--init", str(td / "r.pt"), "--target-px", "0", "--max-val-px", "1e9", epochs=1)
        check("--init from a reader with the same joints, exit 0", code == 0 and r["init"], err=r.get("error"))
        other = dict(torch.load(td / "r.pt", map_location="cpu", weights_only=True))
        other["names"] = ["Hips", "Head", "Hand.L", "Foot.R"]
        torch.save(other, td / "other.pt")
        code, r = go("i2.pt", "--init", str(td / "other.pt"), epochs=1)
        check("--init from a reader with other joint names is refused, exit 1", code == 1
              and "refused" in r.get("error", "") and not (td / "i2.pt").exists())
        code, r = go("f.pt", "--follow", "--target-px", "0", "--max-val-px", "1e9", epochs=1)
        check("--follow re-reads the folder each epoch, exit 0", code == 0)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            c_mps = run([str(td / "ds"), str(td / "ri.json"), str(td / "r3.pt"), "--device", "mps"], quiet)
            c_cpu = run([str(td / "ds"), str(td / "ri.json"), str(td / "r3.pt"), "--device", "cpu"], quiet)
            c_empty = run([str(td / "nothing"), str(td / "ri.json"), str(td / "r3.pt")] + base, quiet)
        check("MPS refused, exit 1", c_mps == 1)
        check("CPU without --allow-cpu refused, exit 1", c_cpu == 1)
        check("an empty dataset refused, exit 1", c_empty == 1)
    ok = all(c["pass"] for c in checks)
    print(json.dumps({"tool": "train.py", "selftest": "pass" if ok else "fail", "checks": len(checks),
                      "failed": [c for c in checks if not c["pass"]]}))
    return 0 if ok else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv or argv[:1] == ["selftest"]:
        return selftest()
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
