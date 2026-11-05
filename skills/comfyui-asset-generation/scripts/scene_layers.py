#!/usr/bin/env python3
"""scene_layers.py — split a 2D scene into depth layers with Qwen-Image-Layered, gate them, and
write the strips, the props and a layered PSD for parallax.

  scene_layers.py run  SCENE.png --out DIR [--layers 4] [--max-size 1024] [--prompt TEXT]
                       [--seed 1] [--names sky,skyline,shops,road,props] [--server URL]
                       [--scroll sky=0.04,skyline=0.15,shops=0.45,road=1,props=1.35] [--no-ground-cut]
  scene_layers.py gate SCENE.png --layers-dir DIR_WITH_PNGS --out DIR [--names ...] [--scroll ...]
  scene_layers.py --selftest          offline: ordering, band and ground splits, gates, the template

`run` submits templates/qwen_image_layered_api.json (the official graph: 20 steps, cfg 2.5,
euler/simple, shift 1; LatentCut drops the composite frame) after an empty queue, downloads the
layers and runs `gate` on them. DIR/run.json pins the job: prompt_id, elapsed_seconds, overrides,
workflow_sha256 (the client's hash of the graph as submitted), seed, prompt_sha256 (of --prompt as
sent; the text is not stored), models (the unet/clip/vae file names), layers, max_size, and the
client's partial ledger `record` (its upload named by file name and sha256). The model returns the layers back to front, each RGBA with the
hidden parts filled (the sky behind the skyline, the shops behind the props). It splits a scene by
depth; it does not split a character into body parts (layer_split.py does that).

`gate`, offline:
  order    the layers as returned, back to front; an empty layer (< 0.5 % opaque) is dropped.
  split    a layer with a full-width transparent band of at least --band rows is cut in two at
           the band (sky above, road below), both at that layer's depth.
  ground   a strip with a ragged top whose bottom rows are flat (few vertical edges) is cut at
           the top of that flat band: the shopfronts above, the road below, both at that depth,
           so each gets its own --scroll (--no-ground-cut keeps it whole).
  names    --names gives the final layers back to front, after the splits; default layer0, ...
  props    the front layer's islands (>= --prop-min px) are also written one by one as
           props/<name>_<i>.png with their box: place them as sprites in the level; never tile
           or mirror the props strip (mirrored tiles put a prop beside its own copy).
  gates    scene.recomposite: mean |RGB| of the layers composited against the source scaled
           to their size <= --max-error (8); scene.coverage: opaque share of the composite >=
           0.99; scene.alpha_clean: each layer's semi-transparent share 3 px or more inside (alpha
           9..246; a ghost layer) <= 0.03;
           scene.depth_order: where a back and a front layer both cover a pixel, the source
           matches the front one on >= 0.6 of those pixels, per pair with >= 400 shared px;
           scene.ground_split: no strip left holding a built band and the ground under it;
           scene.props_whole (props mode): props clear of the left and right edges >= 2, since
           a cut prop is left out of the shuffle and one prop can only repeat. Ask the concept
           for several separate objects inside the frame, and try another --seed when the model
           leaves them on the street layer.
  writes   DIR/<name>.png (canvas-sized), scene.json (back to front: name, png, box, depth,
           role "strip" or "props", tile, and scroll from --scroll: 1 moves with the play line,
           0 stays fixed to the camera, above 1 is a foreground), scene.gate.json (gate/1), scene.psd (psd_write.py),
           sheet.png (each layer over a checker, then the composite).

Exit codes: 0 passed; 1 usage error; 2 a gate failed; 3 a server or job failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
CLIENT = HERE / "comfy_asset_client.py"
TEMPLATE = SKILL / "templates" / "qwen_image_layered_api.json"
TEMPLATE_ARGS = ("REPLACE_WITH_SCENE.png", "")

MODELS = {
    "unet": "qwen_image_layered_fp8mixed.safetensors",
    "clip": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
    "vae": "qwen_image_layered_vae.safetensors",
}


class JobFailed(Exception):
    pass


PROPS_WHOLE_MIN = 2   # props clear of the frame's left and right edges


def graph(image: str, prompt: str, layers=4, max_size=1024, seed=1, prefix="scene_layers/layer",
          models=MODELS) -> dict:
    """The official Qwen-Image-Layered graph in API form; node ids kept from the template."""
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image}},
        "2": {"class_type": "ImageScaleToMaxDimension",
              "inputs": {"image": ["1", 0], "upscale_method": "lanczos", "largest_size": max_size}},
        "37": {"class_type": "UNETLoader", "inputs": {"unet_name": models["unet"], "weight_dtype": "default"}},
        "38": {"class_type": "CLIPLoader", "inputs": {"clip_name": models["clip"], "type": "qwen_image", "device": "default"}},
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": models["vae"]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["38", 0], "text": prompt}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["38", 0], "text": ""}},
        "71": {"class_type": "VAEEncode", "inputs": {"pixels": ["2", 0], "vae": ["39", 0]}},
        "69": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["6", 0], "latent": ["71", 0]}},
        "70": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["7", 0], "latent": ["71", 0]}},
        "66": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["37", 0], "shift": 1}},
        "78": {"class_type": "GetImageSize", "inputs": {"image": ["2", 0]}},
        "118": {"class_type": "EmptyQwenImageLayeredLatentImage",
                "inputs": {"width": ["78", 0], "height": ["78", 1], "layers": layers, "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {"model": ["66", 0], "positive": ["69", 0], "negative": ["70", 0],
                                                   "latent_image": ["118", 0], "seed": seed, "steps": 20, "cfg": 2.5,
                                                   "sampler_name": "euler", "scheduler": "simple", "denoise": 1}},
        "140": {"class_type": "LatentCut", "inputs": {"samples": ["3", 0], "dim": "t", "index": 1, "amount": 16384}},
        "76": {"class_type": "LatentCutToBatch", "inputs": {"samples": ["140", 0], "dim": "t", "slice_size": 1}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["76", 0], "vae": ["39", 0]}},
        "60": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
    }


# ------------------------------------------------------------------------------------- server
def client_mod():
    sys.path.insert(0, str(HERE))
    import comfy_asset_client as cac
    return cac


def server_base(server):
    cac = client_mod()
    return cac.resolve_server(server, cac.load_config(cac.DEFAULT_CONFIG))


def wait_idle(base: str, seconds: float) -> None:
    """One job at a time on a shared server: never queue behind someone else's job."""
    cac = client_mod()
    end = time.monotonic() + seconds
    while not cac.queue_empty(base):
        if time.monotonic() > end:
            raise JobFailed("the ComfyUI queue stayed busy; nothing submitted")
        time.sleep(15)


def run_job(scene: Path, out: Path, a) -> list:
    base = server_base(a.server)
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(scene.read_bytes()).hexdigest()[:10]
    with tempfile.TemporaryDirectory() as td:
        up = Path(td) / f"scene_{h}.png"
        shutil.copyfile(scene, up)
        prefix = f"scene_layers/{scene.stem}_{h}"
        wf = Path(td) / "graph.json"
        wf.write_text(json.dumps({"client_id": "scene-layers", "prompt": graph(
            up.name, a.prompt or "", a.layers, a.max_size, a.seed, prefix)}), encoding="utf-8")
        wait_idle(base, a.wait_idle)
        cmd = [sys.executable, str(CLIENT), "--workflow", str(wf), "--output-dir", str(raw),
               "--upload", str(up), "--timeout-seconds", str(a.timeout), "--server", base]
        if a.keep_loaded:
            cmd.append("--keep-loaded")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise JobFailed(f"client exit {r.returncode}: {r.stderr[-500:]}")
        res = json.loads(r.stdout)
    files = sorted(Path(f["path"]) for f in res.get("output_files", []) if str(f.get("path", "")).endswith(".png"))
    if not files:
        raise JobFailed("the job finished without layer images")
    (out / "run.json").write_text(json.dumps(run_record(res, a.prompt or "", a.seed, a.layers, a.max_size),
                                             indent=1), encoding="utf-8")
    return files


def run_record(res: dict, prompt: str, seed: int, layers: int, max_size: int, models=MODELS) -> dict:
    """run.json: what pins one Qwen-Image-Layered job. The graph is built in code, so the client's
    workflow_sha256 (the graph file as submitted, prompt and seed included) is its hash; the
    prompt is kept as its sha256 only. The client's record names its upload by file name, since
    the upload lived in a temporary folder."""
    job = dict(res.get("record")) if isinstance(res.get("record"), dict) else None
    if job is not None:
        job["inputs"] = [{"path": Path(str(i.get("path"))).name, "sha256": i.get("sha256")}
                         for i in job.get("inputs") or [] if isinstance(i, dict)]
    return {**{k: res.get(k) for k in ("prompt_id", "elapsed_seconds", "overrides", "workflow_sha256")},
            "seed": seed, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "models": dict(models), "layers": layers, "max_size": max_size, "record": job}


# --------------------------------------------------------------------------------------- gate
def _np():
    import numpy as np
    return np


def load_rgba(p):
    np = _np()
    from PIL import Image
    return np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)


def over(layers):
    """Composite RGBA float layers (0..255), back to front."""
    np = _np()
    acc = np.zeros_like(layers[0])
    for L in layers:
        sa, da = L[..., 3:4] / 255, acc[..., 3:4] / 255
        oa = sa + da * (1 - sa)
        rgb = np.where(oa > 0, (L[..., :3] * sa + acc[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6), 0)
        acc = np.concatenate([rgb, oa * 255], -1)
    return acc


def band_split(L, band: int):
    """[L] or [upper, lower] when a full-width transparent band of >= band rows has content on
    both sides."""
    np = _np()
    occ = (L[..., 3] > 8).mean(1)
    empty = occ < 0.002
    rows = np.nonzero(~empty)[0]
    if len(rows) == 0:
        return [L]
    y = rows[0]
    best = None
    while y <= rows[-1]:
        if empty[y]:
            y1 = y
            while y1 <= rows[-1] and empty[y1]:
                y1 += 1
            if y1 - y >= band and (best is None or y1 - y > best[1] - best[0]):
                best = (y, y1)
            y = y1
        else:
            y += 1
    if best is None:
        return [L]
    cut = (best[0] + best[1]) // 2
    up, lo = L.copy(), L.copy()
    up[cut:, :, 3] = 0
    lo[:cut, :, 3] = 0
    return [up, lo]


GROUND_MIN = 0.06     # share of the canvas height a ground band must span to be cut off


def ground_cut(L, H):
    """The row where a strip's built part ends and its ground begins, or None. Qwen-Image-Layered
    can return the shopfronts and the road as one layer; they scroll at different speeds. A
    façade row is busy (many horizontal colour steps), a road or pavement row is nearly flat. The
    cut is the top of the flat band that reaches the layer's bottom, taken when that band spans
    >= GROUND_MIN of the canvas, the layer above it has a ragged top (roofs, a skyline), and the
    rows above are at least three times as busy."""
    np = _np()
    from scipy import ndimage as ndi
    al = L[..., 3] > 127
    rows = np.nonzero(al.any(1))[0]
    if len(rows) < 0.2 * H:
        return None
    y0, y1 = int(rows[0]), int(rows[-1])
    occ = al.mean(1)
    if occ[y1] < 0.98 or y1 < H - 1 - 0.02 * H:
        return None                                    # the strip does not run to the bottom
    # vertical edges that persist over a few rows (windows, doors, posts), not the model's grain;
    # the median over 16 column blocks, so a prop or two on the road do not make its rows busy
    sm = np.stack([ndi.uniform_filter(L[..., k], size=(9, 3)) for k in range(3)], -1)
    gx = np.abs(np.diff(sm, axis=1)).max(-1)
    both = al[:, 1:] & al[:, :-1]
    bz = ((gx > 24) & both).astype(np.float32)
    w = max(bz.shape[1] // 16, 1)
    busy = np.median(np.stack([bz[:, i * w:(i + 1) * w].mean(1) for i in range(16)], 1), 1)
    busy = ndi.median_filter(busy, size=9, mode="nearest")
    full = np.nonzero(occ >= 0.98)[0]
    if not len(full):
        return None
    top = int(full[0])
    if top - y0 < 0.03 * H:
        return None                                    # a flat top edge: nothing stands on the ground
    ref = float(np.percentile(busy[y0:y1 + 1], 75))
    flat = np.zeros(H, bool)
    flat[top:y1 + 1] = (busy[top:y1 + 1] < max(0.25 * ref, 0.01)) & (busy[top:y1 + 1] < 0.05)
    y = y1
    while y > top and flat[y]:
        y -= 1
    y_g = y + 1
    if y1 + 1 - y_g < GROUND_MIN * H or y_g - y0 < 0.1 * H or ref < 0.05:
        return None
    return {"row": int(y_g), "ground_rows": int(y1 + 1 - y_g), "busy_above": round(ref, 3),
            "busy_ground": round(float(np.median(busy[y_g:y1 + 1])), 3)}


def cut_at(L, y):
    up, lo = L.copy(), L.copy()
    up[y:, :, 3] = 0
    lo[:y, :, 3] = 0
    return [up, lo]


def gate(name, value, limit, ok, **extra):
    return {"name": name, "value": value, "limit": limit, "pass": bool(ok), **extra}


def analyse(source, layers, names=None, band=16, max_error=8.0, prop_min=400, props=True, ground=True):
    """source: float RGBA/RGB array; layers: back to front float RGBA, same size as each other.
    Returns (named layers, gates, props list)."""
    np = _np()
    from PIL import Image
    H, W = layers[0].shape[:2]
    if source.shape[:2] != (H, W):
        source = np.asarray(Image.fromarray(source.astype(np.uint8)).resize((W, H), Image.LANCZOS)).astype(np.float32)
    src = source[..., :3]
    dropped = []
    kept = []
    for i, L in enumerate(layers):
        if (L[..., 3] > 127).mean() < 0.005:
            dropped.append(i)
            continue
        kept.append(L)
    final, depth_of = [], []
    last = len(kept) - 1
    for d, L in enumerate(kept):
        parts = band_split(L, band)
        if ground and (d != last or not props):    # the shopfronts off the road: their own speed
            cut = []
            for P in parts:
                g = ground_cut(P, H)
                cut.extend(cut_at(P, g["row"]) if g else [P])
            parts = cut
        final.extend(parts)
        depth_of += [d] * len(parts)
    if names and len(names) != len(final):
        raise ValueError(f"--names lists {len(names)} layers; the scene has {len(final)} after splits")
    names = names or [f"layer{i}" for i in range(len(final))]
    comp = over(final) if final else np.zeros((H, W, 4), np.float32)
    err = float(np.abs(comp[..., :3] * (comp[..., 3:4] / 255) - src * (comp[..., 3:4] / 255)).mean()) if final else 1e9
    cover = float((comp[..., 3] > 127).mean()) if final else 0.0
    gates = [gate("scene.recomposite", round(err, 2), max_error, err <= max_error),
             gate("scene.coverage", round(cover, 4), 0.99, cover >= 0.99)]
    from scipy import ndimage as ndi
    partial = {}
    for n, L in zip(names, final):            # semi-transparent pixels 3 px or more inside: a ghost
        core = ndi.binary_erosion(L[..., 3] > 8, iterations=3)
        partial[n] = round(float(((L[..., 3] > 8) & (L[..., 3] < 247) & core).sum() / max(core.sum(), 1)), 4)
    gates.append(gate("scene.alpha_clean", max(partial.values()) if partial else 1.0, 0.03,
                      bool(partial) and max(partial.values()) <= 0.03, per_layer=partial))
    worst, pairs = 1.0, {}
    for i in range(len(kept)):
        for j in range(i + 1, len(kept)):
            both = (kept[i][..., 3] > 200) & (kept[j][..., 3] > 200)
            if both.sum() < 400:
                continue
            ei = np.abs(kept[i][..., :3] - src).mean(-1)[both]
            ej = np.abs(kept[j][..., :3] - src).mean(-1)[both]
            share = float((ej < ei).mean())
            pairs[f"{i}<{j}"] = round(share, 3)
            worst = min(worst, share)
    gates.append(gate("scene.depth_order", round(worst, 3), 0.6, worst >= 0.6, pairs=pairs))
    gates.append(gate("scene.layers", len(final), 2, len(final) >= 2, dropped_empty=dropped))
    # one strip holding both the built band and the ground under it scrolls them at one speed
    mixed = {n: g for k, (n, L) in enumerate(zip(names, final))
             if not (props and k == len(final) - 1) and (g := ground_cut(L, H))}
    gates.append(gate("scene.ground_split", len(mixed), 0, not mixed, mixed=mixed))
    prop_list = []
    if props and final:
        from scipy import ndimage as ndi
        F = final[-1]
        m = F[..., 3] > 127
        # padded, so the closing's border erosion keeps a prop's columns at the frame's edge
        lab, n = ndi.label(ndi.binary_closing(np.pad(m, 3), iterations=2)[3:-3, 3:-3])
        for k in range(1, n + 1):
            mk = (lab == k) & (F[..., 3] > 0)
            if mk.sum() < prop_min:
                continue
            ys, xs = np.nonzero(mk)
            prop_list.append({"mask": mk, "box": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]})
        # a prop the frame cuts shows its straight edge and is left out of the shuffle; with fewer
        # than two whole props the shuffle can only repeat one
        whole = [p for p in prop_list if p["box"][0] > 0 and p["box"][2] < W]
        gates.append(gate("scene.props_whole", len(whole), PROPS_WHOLE_MIN, len(whole) >= PROPS_WHOLE_MIN,
                          props=len(prop_list), cut_by_frame=len(prop_list) - len(whole)))
    return list(zip(names, final, depth_of)), gates, prop_list, comp


def parse_scroll(text):
    """'sky=0.04,road=1' -> {'sky': 0.04, 'road': 1.0}; ValueError on a bad pair."""
    out = {}
    for kv in (text or "").split(","):
        if not kv.strip():
            continue
        name, eq, val = kv.partition("=")
        if not eq or not name.strip():
            raise ValueError(f"--scroll wants name=value pairs, got {kv!r}")
        out[name.strip()] = float(val)
    return out


def write_outputs(out: Path, named, gates, props, comp, tool="scene_layers", scroll=None):
    np = _np()
    from PIL import Image
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for k, (name, L, depth) in enumerate(named):
        a = np.clip(L, 0, 255).astype(np.uint8)
        Image.fromarray(a).save(out / f"{name}.png")
        ys, xs = np.nonzero(a[..., 3] > 8)
        box = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1] if len(ys) else [0, 0, 0, 0]
        front = k == len(named) - 1
        entries.append({"name": name, "png": f"{name}.png", "box": box, "depth": depth,
                        "role": "props" if front and props else "strip", "tile": not (front and props)})
        if scroll and name in scroll:
            entries[-1]["scroll"] = scroll[name]
    plist = []
    if props:
        (out / "props").mkdir(exist_ok=True)
        front = named[-1]
        F = np.clip(front[1], 0, 255).astype(np.uint8)
        for i, p in enumerate(sorted(props, key=lambda q: q["box"][0])):
            x0, y0, x1, y1 = p["box"]
            crop = F[y0:y1, x0:x1].copy()
            crop[~p["mask"][y0:y1, x0:x1]] = 0
            fn = f"props/{front[0]}_{i}.png"
            Image.fromarray(crop).save(out / fn)
            plist.append({"png": fn, "x": x0, "y": y0, "box": p["box"]})
    H, W = named[0][1].shape[:2]
    scene = {"tool": tool, "width": W, "height": H, "order": "back_to_front", "layers": entries, "props": plist}
    (out / "scene.json").write_text(json.dumps(scene, indent=1), encoding="utf-8")
    ok = all(g["pass"] for g in gates)
    rep = {"schema": "gate/1", "tool": tool, "pass": ok, "gates": gates}
    (out / "scene.gate.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    man = {"width": W, "height": H, "ids": "ids.json",
           "layers": [{"name": e["name"], "png": e["png"]} for e in reversed(entries)]}
    (out / "scene.manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    sys.path.insert(0, str(HERE))
    import psd_write
    psd_write.write_manifest(out / "scene.manifest.json", out / "scene.psd")
    sheet(out / "sheet.png", [L for _, L, _ in named], comp)
    return rep, scene


def sheet(path, layers, comp, width=320):
    np = _np()
    from PIL import Image
    H, W = layers[0].shape[:2]
    h = int(width * H / W)
    tiles = []
    yy, xx = np.mgrid[:H, :W]
    chk = np.where(((yy // 16) + (xx // 16)) % 2 == 0, 200, 150).astype(np.float32)
    for L in list(layers) + [comp]:
        a = L[..., 3:4] / 255
        rgb = L[..., :3] * a + chk[..., None] * (1 - a)
        tiles.append(Image.fromarray(rgb.clip(0, 255).astype(np.uint8)).resize((width, h), Image.LANCZOS))
    s = Image.new("RGB", (width * len(tiles) + 8 * (len(tiles) - 1), h), (40, 40, 40))
    for i, t in enumerate(tiles):
        s.paste(t, (i * (width + 8), 0))
    s.save(path)


def cmd_gate(scene: Path, pngs: list, out: Path, a) -> int:
    layers = [load_rgba(p) for p in pngs]
    sizes = {L.shape[:2] for L in layers}
    if len(sizes) != 1:
        print(f"scene_layers.py: layer sizes differ: {sorted(sizes)}", file=sys.stderr)
        return 1
    names = [n.strip() for n in a.names.split(",")] if a.names else None
    try:
        scroll = parse_scroll(a.scroll)
    except ValueError as e:
        print(f"scene_layers.py: {e}", file=sys.stderr)
        return 1
    try:
        named, gates, props, comp = analyse(load_rgba(scene), layers, names, a.band, a.max_error,
                                            a.prop_min, not a.no_props, not a.no_ground_cut)
    except ValueError as e:
        print(f"scene_layers.py: {e}", file=sys.stderr)
        return 1
    if not named:
        print("scene_layers.py: every layer is empty", file=sys.stderr)
        return 2
    unknown = sorted(set(scroll) - {n for n, _, _ in named})
    if unknown:
        print(f"scene_layers.py: --scroll names no layer: {', '.join(unknown)}", file=sys.stderr)
        return 1
    rep, scene_doc = write_outputs(out, named, gates, props, comp, scroll=scroll)
    print(json.dumps({"pass": rep["pass"], "out": str(out), "layers": [e["name"] for e in scene_doc["layers"]],
                      "props": len(scene_doc["props"]), "gates": {g["name"]: g["value"] for g in gates}}))
    return 0 if rep["pass"] else 2


# ----------------------------------------------------------------------------------- selftest
def selftest() -> int:
    np = _np()
    checks = {}
    H, W = 120, 200
    yy, xx = np.mgrid[:H, :W]
    src = np.zeros((H, W, 4), np.float32)
    src[..., 3] = 255
    sky = np.zeros_like(src)
    sky[:50] = (120, 170, 230, 255)
    sky[80:] = (70, 70, 80, 255)                                   # road; rows 50..80 empty
    far = np.zeros_like(src)
    far[30:80, 20:180] = (150, 160, 190, 255)
    near = np.zeros_like(src)
    near[60:110, 40:70] = (200, 40, 40, 255)                         # a hydrant
    near[70:112, 140:180] = (180, 140, 90, 255)                     # parcels
    src = over([sky, far, near])
    src[50:80][src[50:80, :, 3] < 1] = (90, 90, 90, 255)
    named, gates, props, comp = analyse(src, [sky, far, near], None)
    g = {x["name"]: x for x in gates}
    checks["split_sky_road"] = len(named) == 4 and [d for _, _, d in named] == [0, 0, 1, 2]
    checks["clean_pass"] = all(x["pass"] for x in gates if x["name"] != "scene.coverage")
    checks["coverage_counts_gap"] = g["scene.coverage"]["pass"] is False   # the 30-row gap is uncovered
    checks["props_two"] = len(props) == 2 and g["scene.props_whole"]["pass"]
    edge = near.copy()
    edge[70:112, 140:200] = (180, 140, 90, 255)                      # the parcels cut by the frame
    _, gates4, props4, _ = analyse(over([sky, far, edge]), [sky, far, edge], None)
    checks["cut_prop_caught"] = len(props4) == 2 and not next(x for x in gates4 if x["name"] == "scene.props_whole")["pass"]
    _, gates2, _, _ = analyse(src, [sky, near, far], None)                  # wrong depth order
    checks["order_caught"] = not next(x for x in gates2 if x["name"] == "scene.depth_order")["pass"]
    soft = far.copy()
    soft[30:80, 20:180, 3] = 128
    _, gates3, _, _ = analyse(src, [sky, soft, near], None)
    checks["soft_alpha_caught"] = not next(x for x in gates3 if x["name"] == "scene.alpha_clean")["pass"]
    try:
        analyse(src, [sky, far, near], ["a", "b"])
        checks["names_count_refused"] = False
    except ValueError:
        checks["names_count_refused"] = True
    with tempfile.TemporaryDirectory() as td:
        rep, doc = write_outputs(Path(td), named, gates, props, comp,
                                 scroll=parse_scroll(f"{named[0][0]}=0.04,{named[-1][0]}=1.35"))
        checks["outputs"] = (Path(td) / "scene.psd").is_file() and len(doc["props"]) == 2 and \
            doc["layers"][-1]["tile"] is False and doc["layers"][0]["tile"] is True and rep["schema"] == "gate/1"
        checks["scroll_written"] = doc["layers"][0].get("scroll") == 0.04 and \
            doc["layers"][-1].get("scroll") == 1.35 and "scroll" not in doc["layers"][1]
    shops = np.zeros_like(src)                                      # shopfronts and the road in ONE layer
    for x0, x1, top in ((0, 70, 40), (70, 140, 52), (140, 200, 46)):
        shops[top:96, x0:x1] = (170, 90, 70, 255)
        shops[top + 4:92, x0:x1][:, (np.arange(x1 - x0) // 4) % 3 == 0] = (40, 60, 90, 255)   # windows
    shops[96:] = (80, 80, 92, 255)                                  # the road, flat
    src5 = over([sky, shops, near])
    named5, gates5, _, _ = analyse(src5, [sky, shops, near], None)
    g5 = next(x for x in gates5 if x["name"] == "scene.ground_split")
    cut = [n for n, L, _ in named5 if (L[..., 3] > 127).any()]
    _, gates6, _, _ = analyse(src5, [sky, shops, near], None, ground=False)
    checks["ground_cut"] = g5["pass"] and len(named5) == len(named) + 1 and \
        abs(int(np.nonzero((named5[3][1][..., 3] > 127).any(1))[0][0]) - 96) <= 4 and len(cut) == len(named5)
    checks["ground_mixed_caught"] = not next(x for x in gates6 if x["name"] == "scene.ground_split")["pass"]
    try:
        parse_scroll("sky")
        checks["scroll_refused"] = False
    except ValueError:
        checks["scroll_refused"] = True
    try:
        tpl = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        checks["template_matches"] = set(tpl) == {"client_id", "prompt"} and tpl["prompt"] == graph(*TEMPLATE_ARGS)
    except (OSError, json.JSONDecodeError):
        checks["template_matches"] = False
    res = {"prompt_id": "job-3", "elapsed_seconds": 41.5, "overrides": {}, "workflow_sha256": "ab" * 32,
           "record": {"tool": {"skill": "comfyui-asset-generation", "script": "comfy_asset_client.py"},
                      "params": {"workflow_sha256": "ab" * 32}, "verdict": "green",
                      "inputs": [{"path": "/tmp/job/scene_0a1b.png", "sha256": "cd" * 32}],
                      "files": [{"path": "/proj/scenes/street/raw/layer_00001_.png", "sha256": "ef" * 32, "bytes": 9}]}}
    rr = run_record(res, "a street of shops with parcels", 7, 4, 1024)
    checks["run_record"] = (rr["workflow_sha256"] == "ab" * 32 and rr["seed"] == 7 and rr["models"] == MODELS
                            and rr["prompt_sha256"] == hashlib.sha256(b"a street of shops with parcels").hexdigest()
                            and rr["prompt_id"] == "job-3" and rr["layers"] == 4
                            and rr["record"]["inputs"] == [{"path": "scene_0a1b.png", "sha256": "cd" * 32}]
                            and "parcels" not in json.dumps(rr) and "/tmp/job" not in json.dumps(rr)
                            and run_record({}, "", 1, 4, 1024)["record"] is None)
    gr = graph("s.png", "p", layers=5, max_size=640, seed=9)
    links = [v for n in gr.values() for v in n["inputs"].values() if isinstance(v, list)]
    checks["graph_links"] = all(v[0] in gr for v in links) and gr["118"]["inputs"]["layers"] == 5 \
        and gr["3"]["inputs"]["seed"] == 9 and gr["140"]["inputs"]["index"] == 1
    ok = all(checks.values())
    print(json.dumps({"checks": checks, "pass": ok}))
    return 0 if ok else 2


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1, never 2."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["--selftest"], ["selftest"]):
        return selftest()
    ap = UsageParser(prog="scene_layers.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd", parser_class=UsageParser)
    for name in ("run", "gate"):
        p = sub.add_parser(name)
        p.add_argument("scene", type=Path)
        p.add_argument("--out", type=Path, required=True)
        p.add_argument("--names", help="final layer names, back to front, comma-separated")
        p.add_argument("--band", type=int, default=16, help="rows of a transparent band that split a layer")
        p.add_argument("--max-error", type=float, default=8.0)
        p.add_argument("--prop-min", type=int, default=400, help="px; smaller islands stay in the strip only")
        p.add_argument("--no-props", action="store_true", help="the front layer is a strip, not props")
        p.add_argument("--no-ground-cut", action="store_true",
                       help="keep a strip whole even when it holds a built band and the ground under it")
        p.add_argument("--scroll", help="name=S,... scroll speed per final layer, written to scene.json")
        if name == "run":
            p.add_argument("--layers", type=int, default=4)
            p.add_argument("--max-size", type=int, default=1024)
            p.add_argument("--prompt", default="")
            p.add_argument("--seed", type=int, default=1)
            p.add_argument("--server", default=os.environ.get("COMFYUI_SERVER_URL"))
            p.add_argument("--wait-idle", type=float, default=900)
            p.add_argument("--timeout", type=float, default=1800)
            p.add_argument("--keep-loaded", action="store_true")
        else:
            p.add_argument("--layers-dir", type=Path, required=True, help="the layer PNGs, back to front by name")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.cmd:
        ap.error("choose run or gate")
    if not a.scene.is_file():
        ap.error(f"scene not found: {a.scene}")
    if a.cmd == "gate":
        pngs = sorted(a.layers_dir.glob("*.png"))
        if not pngs:
            ap.error(f"no PNGs in {a.layers_dir}")
        return cmd_gate(a.scene, pngs, a.out, a)
    if not 2 <= a.layers <= 10:
        ap.error("--layers must be 2..10")
    try:
        pngs = run_job(a.scene, a.out, a)
    except (JobFailed, OSError, json.JSONDecodeError) as e:
        print(f"scene_layers.py: {e}", file=sys.stderr)
        return 3
    return cmd_gate(a.scene, pngs, a.out, a)


if __name__ == "__main__":
    sys.exit(main())
