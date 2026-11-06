#!/usr/bin/env python3
"""embed.py — image embeddings and pairwise cosine similarity (DINOv2, SigLIP 2), a module and a CLI.

A perceptual number for "does picture A look like picture B": each image is embedded by a vision
model and the pair's cosine similarity is reported (1 = the same embedding; higher is closer).
Two models, because they see different things:

  dinov2   facebook/dinov2-base, the CLS token (pooler output): shape, layout, parts
  siglip2  google/siglip2-base-patch16-224, get_image_features: what the picture shows, its style

Every embedding is L2-normalised. An image with alpha is composited over mid-grey (128) first, so
a transparent background never reads as black. torch and transformers are optional and imported
only when a model runs: the self-test and the missing-engine path need neither.

The CLI reads a pairs file and writes a sims file. pairs.json (plain JSON, no schema stamp):

  {"pairs": [{"id": "front", "a": "renders/front.png", "b": "views/front.png"}, ...]}

Paths are relative to the pairs file's folder, so the folder can be copied to a GPU host and run
there with any Python that has torch + transformers. sims.json:

  {"engine": {"models": {"dinov2": "facebook/dinov2-base@main", ...}, "device": "cuda",
              "torch": "2.x", "transformers": "4.x"},
   "sims": {"front": {"dinov2": 0.91, "siglip2": 0.88}, ...}}

When torch or transformers is missing (or a model cannot be loaded) nothing is measured:
sims.json is still written with "engine": null, every similarity null and a "reason", a WARN goes
to stderr and the exit code is 3. A caller reads null as "not measured", never as a pass.

  python3 embed.py --pairs pairs.json --out sims.json [--models dinov2,siglip2] [--device auto]
  python3 embed.py --selftest      no model download, no torch needed

Device auto = cuda, then mps, then cpu.

Exit codes: 0 measured, 1 usage error (a bad flag, an unreadable pairs file, a missing image),
2 selftest failed, 3 not measured (no torch/transformers, or a model failed to load or run).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Pinned models: the hub id and the revision VERSIONS.md records for each.
DINOV2_ID = "facebook/dinov2-base"
DINOV2_REV = "f9e44c814b77203eaa57a6bdbbd535f21ede1415"
SIGLIP2_ID = "google/siglip2-base-patch16-224"
SIGLIP2_REV = "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"
MODELS = {"dinov2": (DINOV2_ID, DINOV2_REV), "siglip2": (SIGLIP2_ID, SIGLIP2_REV)}
GREY = 128
BATCH = 8

# Test hooks: a string forces available() to report the engine missing with that reason; a
# callable fn(images, model, device) -> (n, d) array replaces the transformers engine.
_FORCE_UNAVAILABLE: str | None = None
_TEST_EMBEDDER = None
_LOADED: dict = {}


def available() -> tuple[bool, str]:
    """(True, "") when torch and transformers can be imported, else (False, why)."""
    if _FORCE_UNAVAILABLE:
        return False, _FORCE_UNAVAILABLE
    missing = [m for m in ("torch", "transformers") if importlib.util.find_spec(m) is None]
    if missing:
        return False, "not installed: " + ", ".join(missing)
    return True, ""


def pick_device(device: str = "auto") -> str:
    if device != "auto":
        return device
    import torch
    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


def load_rgb(path) -> Image.Image:
    """The image as RGB; alpha (RGBA, LA, P with transparency) composited over mid-grey."""
    im = Image.open(path)
    im.load()
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (GREY, GREY, GREY, 255))
        return Image.alpha_composite(bg, im).convert("RGB")
    return im.convert("RGB")


def _l2(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, np.float64)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def _engine(model: str, device: str):
    """(processor, model) for a model key, loaded once per process."""
    key = (model, device)
    if key not in _LOADED:
        import torch  # noqa: F401  (imported for its side effects on transformers)
        from transformers import AutoImageProcessor, AutoModel
        mid, rev = MODELS[model]
        proc = AutoImageProcessor.from_pretrained(mid, revision=rev)
        net = AutoModel.from_pretrained(mid, revision=rev).to(device).eval()
        _LOADED[key] = (proc, net)
    return _LOADED[key]


def _features(out):
    """A tensor from get_image_features / a model output, whichever the transformers version returns."""
    if hasattr(out, "pooler_output") and out.pooler_output is not None:
        return out.pooler_output
    if isinstance(out, (tuple, list)):
        return out[0]
    return out


def _transformers_embed(images, model: str, device: str) -> np.ndarray:
    import torch
    proc, net = _engine(model, device)
    rows = []
    with torch.inference_mode():
        for i in range(0, len(images), BATCH):
            inputs = proc(images=images[i:i + BATCH], return_tensors="pt").to(device)
            if model == "dinov2":
                f = net(**inputs).pooler_output          # the CLS token after the final layer norm
            else:
                f = _features(net.get_image_features(**inputs))
            rows.append(f.float().cpu().numpy())
    return np.concatenate(rows, 0)


def embed(paths, model: str, device: str = "auto", embedder=None) -> np.ndarray:
    """(n, d) L2-normalised embeddings of the images at paths. embedder(images, model, device)
    replaces the transformers engine (tests); otherwise torch and transformers must be present."""
    if model not in MODELS:
        raise ValueError(f"unknown model {model!r}; known: {sorted(MODELS)}")
    images = [load_rgb(p) for p in paths]
    fn = embedder or _TEST_EMBEDDER
    if fn is None:
        ok, why = available()
        if not ok:
            raise RuntimeError(why)
        device = pick_device(device)
        fn = _transformers_embed
    return _l2(fn(images, model, device))


def similarity(a_paths, b_paths, model: str, device: str = "auto", embedder=None) -> list:
    """Cosine similarity of a[i] and b[i] for each i, as floats."""
    if len(a_paths) != len(b_paths):
        raise ValueError("a and b need the same number of images")
    if not a_paths:
        return []
    e = embed(list(a_paths) + list(b_paths), model, device, embedder)
    n = len(a_paths)
    return [float(x) for x in (e[:n] * e[n:]).sum(1)]


def read_pairs(path) -> list:
    """[(id, a_path, b_path)] with paths resolved against the pairs file's folder; ValueError if bad."""
    path = Path(path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"cannot read {path}: {e}") from None
    pairs = doc.get("pairs") if isinstance(doc, dict) else None
    if not isinstance(pairs, list) or not pairs:
        raise ValueError(f'{path}: expected {{"pairs": [{{"id", "a", "b"}}, ...]}}')
    out, seen = [], set()
    for i, p in enumerate(pairs):
        if not (isinstance(p, dict) and all(isinstance(p.get(k), str) and p.get(k) for k in ("id", "a", "b"))):
            raise ValueError(f"{path}: pairs[{i}] needs string id, a and b")
        if p["id"] in seen:
            raise ValueError(f"{path}: pair id {p['id']!r} repeats")
        seen.add(p["id"])
        a, b = path.parent / p["a"], path.parent / p["b"]
        for q in (a, b):
            if not q.is_file():
                raise ValueError(f"{path}: pairs[{i}] image not found: {q}")
        out.append((p["id"], a, b))
    return out


def engine_info(models, device) -> dict:
    info = {"models": {m: f"{MODELS[m][0]}@{MODELS[m][1]}" for m in models}, "device": device}
    for mod in ("torch", "transformers"):
        try:
            info[mod] = __import__(mod).__version__
        except ImportError:
            info[mod] = None
    return info


def run_pairs(pairs, models, device="auto", embedder=None) -> tuple[dict, int]:
    """(sims document, exit code) for [(id, a, b)]: 0 measured, 3 not measured (engine null)."""
    blank = {pid: {m: None for m in models} for pid, _a, _b in pairs}
    if embedder is None and _TEST_EMBEDDER is None:
        ok, why = available()
        if not ok:
            return {"engine": None, "sims": blank, "reason": why}, 3
    try:
        dev = device if (embedder or _TEST_EMBEDDER) else pick_device(device)
        sims = {pid: {} for pid, _a, _b in pairs}
        unique = list(dict.fromkeys(str(Path(x).resolve()) for _i, a, b in pairs for x in (a, b)))
        at = {x: k for k, x in enumerate(unique)}     # each image embedded once per model
        for m in models:
            e = embed(unique, m, dev, embedder)
            for pid, a, b in pairs:
                sims[pid][m] = round(float(e[at[str(Path(a).resolve())]] @ e[at[str(Path(b).resolve())]]), 4)
    except Exception as e:  # a model that will not download, load or run: not measured
        return {"engine": None, "sims": blank, "reason": f"{type(e).__name__}: {e}"[:400]}, 3
    info = engine_info(models, dev) if not (embedder or _TEST_EMBEDDER) else {
        "models": {m: f"{MODELS[m][0]}@{MODELS[m][1]}" for m in models}, "device": dev, "torch": None,
        "transformers": None, "test_embedder": True}
    return {"engine": info, "sims": sims}, 0


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1, never 2: here 2 is a selftest verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    ap = UsageParser(prog="embed.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", type=Path, help='pairs.json: {"pairs": [{"id", "a", "b"}]}, paths relative to it')
    ap.add_argument("--out", type=Path, help="sims.json to write")
    ap.add_argument("--models", default="dinov2,siglip2", help="comma list of dinov2, siglip2")
    ap.add_argument("--device", choices=["auto", "cuda", "mps", "cpu"], default="auto")
    ap.add_argument("--selftest", action="store_true", help="synthetic checks; no model, no torch needed")
    return ap


def parse_models(text: str) -> list:
    ms = [m.strip() for m in text.split(",") if m.strip()]
    bad = [m for m in ms if m not in MODELS]
    if not ms or bad:
        raise ValueError(f"--models: unknown {bad or 'empty list'}; known: {', '.join(MODELS)}")
    return list(dict.fromkeys(ms))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.pairs or not a.out:
        ap.error("--pairs and --out are required")
    try:
        models = parse_models(a.models)
        pairs = read_pairs(a.pairs)
    except ValueError as e:
        ap.error(str(e))
    doc, code = run_pairs(pairs, models, a.device)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(doc, indent=1))
    if code:
        print(f"WARN embed.py: not measured ({doc['reason']}); {a.out} has every similarity null. Run it where "
              "torch and transformers are installed.", file=sys.stderr)
        return code
    for pid, row in doc["sims"].items():
        print(f"{pid:16s} " + "  ".join(f"{m} {v:.4f}" for m, v in row.items()))
    print(f"wrote {a.out} ({doc['engine']['device']})")
    return 0


# ----------------------------------------------------------------------------- selftest

def selftest() -> int:
    import contextlib
    import io
    import tempfile
    global _FORCE_UNAVAILABLE
    results = {}

    def check(name, cond, detail=""):
        results[name] = bool(cond)
        print(f"{'PASS' if cond else 'FAIL'} {name}" + (f"  {detail}" if detail else ""))

    def fake(images, model, device):
        """Mean colour of each image plus a model-dependent constant: a deterministic embedding."""
        off = 1.0 if model == "dinov2" else 3.0
        return np.array([np.r_[np.asarray(im, np.float64).reshape(-1, 3).mean(0) / 255.0, off] for im in images])

    def run(args):
        err, out = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            try:
                code = main(args)
            except SystemExit as e:
                code = e.code
        return code, out.getvalue() + err.getvalue()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "match"
        (root / "renders").mkdir(parents=True)
        (root / "views").mkdir()
        # a transparent image with a red square: over grey, the background is 128, never black
        rgba = np.zeros((32, 32, 4), np.uint8)
        rgba[8:24, 8:24] = (220, 30, 30, 255)
        Image.fromarray(rgba, "RGBA").save(root / "renders" / "front.png")
        comp = np.asarray(load_rgb(root / "renders" / "front.png"))
        check("alpha_over_grey", (comp[0, 0] == GREY).all() and (comp[16, 16] == (220, 30, 30)).all(),
              f"corner {comp[0, 0].tolist()}")
        half = rgba.copy()
        half[..., 3] = np.where(half[..., 3] > 0, 255, 128)
        Image.fromarray(half, "RGBA").save(root / "views" / "half.png")
        hc = np.asarray(load_rgb(root / "views" / "half.png"))
        check("half_alpha_blends_grey", abs(int(hc[0, 0, 0]) - GREY // 2) <= 1, f"{hc[0, 0].tolist()}")  # black at alpha 128
        # the same picture opaque on grey, and one on black, and a blue one
        Image.fromarray(comp).save(root / "views" / "front.png")
        black = np.zeros((32, 32, 3), np.uint8)
        black[8:24, 8:24] = (220, 30, 30)
        Image.fromarray(black).save(root / "views" / "black.png")
        blue = comp.copy()
        blue[8:24, 8:24] = (30, 30, 220)
        Image.fromarray(blue).save(root / "views" / "blue.png")
        pairs_doc = {"pairs": [{"id": "front", "a": "renders/front.png", "b": "views/front.png"},
                               {"id": "on_black", "a": "renders/front.png", "b": "views/black.png"},
                               {"id": "blue", "a": "renders/front.png", "b": "views/blue.png"}]}
        (root / "pairs.json").write_text(json.dumps(pairs_doc))

        # pair resolution: relative to the pairs file, wherever the cwd is
        pairs = read_pairs(root / "pairs.json")
        check("pairs_resolve_relative", [p[0] for p in pairs] == ["front", "on_black", "blue"]
              and pairs[0][1] == root / "renders" / "front.png")
        for bad, why in ((["x"], "not a dict"), ({"pairs": []}, "empty"),
                         ({"pairs": [{"id": "a", "a": "renders/front.png", "b": "views/none.png"}]}, "missing image"),
                         ({"pairs": [{"id": "a", "a": "renders/front.png", "b": "views/front.png"}] * 2}, "repeat id")):
            (root / "bad.json").write_text(json.dumps(bad))
            try:
                read_pairs(root / "bad.json")
                check(f"pairs_refused_{why}", False)
            except ValueError:
                check(f"pairs_refused_{why}", True)

        # cosine maths with an injected embedder
        s = similarity([pairs[0][1]], [pairs[0][2]], "dinov2", embedder=fake)
        check("identical_cosine_1", abs(s[0] - 1.0) < 1e-9, f"{s[0]:.6f}")
        s3 = similarity([p[1] for p in pairs], [p[2] for p in pairs], "siglip2", embedder=fake)
        check("transparent_equals_grey_not_black", s3[0] > s3[1] + 1e-6, f"grey {s3[0]:.4f} black {s3[1]:.4f}")
        check("other_colour_lower", s3[2] < s3[0] - 1e-3, f"{s3[2]:.4f}")
        e = embed([pairs[0][1], pairs[1][2]], "dinov2", embedder=fake)
        check("l2_normalised", np.allclose(np.linalg.norm(e, axis=1), 1.0) and e.shape == (2, 4))
        try:
            embed([pairs[0][1]], "clip", embedder=fake)
            check("unknown_model_refused", False)
        except ValueError:
            check("unknown_model_refused", True)

        # CLI with the test embedder: exit 0, sims per id and model, engine filled
        globals()["_TEST_EMBEDDER"] = fake
        try:
            code, _txt = run(["--pairs", str(root / "pairs.json"), "--out", str(root / "sims.json")])
        finally:
            globals()["_TEST_EMBEDDER"] = None
        doc = json.loads((root / "sims.json").read_text())
        check("cli_measured_exit_0", code == 0 and doc["engine"] is not None
              and set(doc["sims"]) == {"front", "on_black", "blue"}
              and set(doc["sims"]["front"]) == {"dinov2", "siglip2"} and doc["sims"]["front"]["dinov2"] == 1.0,
              f"exit {code}")
        check("engine_names_pinned_models", doc["engine"]["models"]["dinov2"] == f"{DINOV2_ID}@{DINOV2_REV}"
              and doc["engine"]["models"]["siglip2"] == f"{SIGLIP2_ID}@{SIGLIP2_REV}")

        # missing engine: a WARN, exit 3, engine null, every sim null, a reason
        _FORCE_UNAVAILABLE = "not installed: torch"
        try:
            ok, why = available()
            check("available_false_with_reason", ok is False and "torch" in why)
            code, txt = run(["--pairs", str(root / "pairs.json"), "--out", str(root / "none.json"), "--models", "siglip2"])
            nd = json.loads((root / "none.json").read_text())
            check("missing_engine_exit_3", code == 3 and "WARN" in txt, f"exit {code}")
            check("missing_engine_all_null", nd["engine"] is None and "torch" in nd["reason"]
                  and all(v == {"siglip2": None} for v in nd["sims"].values()))
            try:
                embed([pairs[0][1]], "dinov2")
                check("embed_without_engine_raises", False)
            except RuntimeError:
                check("embed_without_engine_raises", True)
        finally:
            _FORCE_UNAVAILABLE = None

        # a model that fails at run time is not measured either
        def broken(images, model, device):
            raise OSError("cannot download")
        nd, code = run_pairs(pairs, ["dinov2"], embedder=broken)
        check("engine_error_not_measured", code == 3 and nd["engine"] is None and "download" in nd["reason"])

        # usage errors exit 1
        for args, why in ((["--nope"], "unknown_flag"), (["--pairs", str(root / "pairs.json")], "no_out"),
                          (["--pairs", str(root / "pairs.json"), "--out", str(root / "x.json"), "--models", "clip"], "bad_model"),
                          (["--pairs", str(root / "missing.json"), "--out", str(root / "x.json")], "missing_pairs"),
                          (["--pairs", str(root / "pairs.json"), "--out", str(root / "x.json"), "--device", "tpu"], "bad_device")):
            code, _txt = run(args)
            check(f"usage_exit_1_{why}", code == 1, f"exit {code}")

    failed = [k for k, v in results.items() if not v]
    print(f"embed selftest: {len(results) - len(failed)}/{len(results)} passed" + (f"; FAILED {failed}" if failed else ""))
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
