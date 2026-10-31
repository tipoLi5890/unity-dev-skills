#!/usr/bin/env python3
"""Paint one guide render with Qwen-Image-Edit-2511 (+ Lightning) on a ComfyUI server.

Picture 1 is the guide (its layout is kept), picture 2 the one reference. Exactly two
images: a third reference makes the model leave the guide almost unpainted. The guide
goes in at 1024x1024 and the latent is the guide's own VAE encoding, so the output keeps
its pixel layout. Sampling: ModelSamplingAuraFlow shift 3.1, CFGNorm 1, reference latents
index_timestep_zero, 4 steps at cfg 1 (euler / simple) with the Lightning LoRA, denoise 1.
Submission goes through comfyui-asset-generation's client.

  python3 qwen_paint.py guide.png ref.png out.png --prompt "..." [--server URL] [--models m.json]
  python3 qwen_paint.py guide.png ref.png out.png --prompt "..." --graph-only
  python3 qwen_paint.py --selftest      graph wiring and the template, no network

--models maps any of unet / clip / vae / lora to the file names on your server (a JSON file
or inline JSON). Exit codes: 0 done or selftest passed, 1 usage error, 2 selftest failed,
3 paint job failed.
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
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent.parent / "comfyui-asset-generation" / "scripts" / "comfy_asset_client.py"
TEMPLATE = HERE.parent / "templates" / "qwen_image_edit_2511_view_paint_api.json"
TEMPLATE_ARGS = ("REPLACE_WITH_GUIDE_RENDER.png", "REPLACE_WITH_REFERENCE.png", "REPLACE_WITH_PROMPT")

MODELS = {
    "unet": "qwen_image_edit_2511_int8_convrot.safetensors",
    "clip": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
    "vae": "qwen_image_vae.safetensors",
    "lora": "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
}


def load_models(spec: str | None) -> dict:
    """MODELS with overrides from a JSON file path or inline JSON object; ValueError if invalid."""
    if not spec:
        return dict(MODELS)
    text = spec if spec.lstrip().startswith("{") else Path(spec).read_text(encoding="utf-8")
    try:
        over = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"--models is not valid JSON: {e}") from None
    if not isinstance(over, dict):
        raise ValueError("--models must be a JSON object")
    bad = sorted(set(over) - set(MODELS))
    if bad:
        raise ValueError(f"--models: unknown key(s) {bad}; known: {sorted(MODELS)}")
    if not all(isinstance(v, str) and v for v in over.values()):
        raise ValueError("--models: every value must be a non-empty file name")
    return {**MODELS, **over}


def graph(guide: str, ref: str, prompt: str, seed=42, steps=4, cfg=1.0, lightning=True,
          prefix="mesh-texture-paint/view", models=MODELS) -> dict:
    """ComfyUI API graph: picture 1 = guide (also the latent), picture 2 = ref."""
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": models["unet"], "weight_dtype": "default"}},
        "5": {"class_type": "CLIPLoader", "inputs": {"clip_name": models["clip"], "type": "qwen_image", "device": "default"}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": models["vae"]}},
        "7": {"class_type": "LoadImage", "inputs": {"image": guide}},
        "8": {"class_type": "LoadImage", "inputs": {"image": ref}},
    }
    model = ["1", 0]
    if lightning:
        g["2"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": model, "lora_name": models["lora"], "strength_model": 1.0}}
        model = ["2", 0]
    imgs = {"image1": ["7", 0], "image2": ["8", 0]}
    g["3"] = {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": model, "shift": 3.1}}
    g["4"] = {"class_type": "CFGNorm", "inputs": {"model": ["3", 0], "strength": 1.0}}
    g["9"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["5", 0], "prompt": prompt, "vae": ["6", 0], **imgs}}
    g["10"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["5", 0], "prompt": "", "vae": ["6", 0], **imgs}}
    g["11"] = {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {"conditioning": ["9", 0], "reference_latents_method": "index_timestep_zero"}}
    g["12"] = {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {"conditioning": ["10", 0], "reference_latents_method": "index_timestep_zero"}}
    g["13"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["7", 0], "vae": ["6", 0]}}
    g["14"] = {"class_type": "KSampler", "inputs": {"model": ["4", 0], "seed": seed, "steps": steps, "cfg": cfg,
                                                    "sampler_name": "euler", "scheduler": "simple", "positive": ["11", 0],
                                                    "negative": ["12", 0], "latent_image": ["13", 0], "denoise": 1.0}}
    g["15"] = {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["6", 0]}}
    g["16"] = {"class_type": "SaveImage", "inputs": {"images": ["15", 0], "filename_prefix": prefix}}
    return g


def _hashed_copy(src: Path, tmp: Path, tag: str) -> Path:
    """Upload names carry a content hash: the server keeps the first file under a name."""
    h = hashlib.sha256(src.read_bytes()).hexdigest()[:10]
    dst = tmp / f"mtp_{tag}_{h}{src.suffix}"
    shutil.copyfile(src, dst)
    return dst


def paint(guide: Path, ref: Path, prompt: str, out_png: Path, server: str | None = None, seed=42,
          keep_loaded=True, timeout=900, models=MODELS) -> dict:
    """Run one paint job; writes out_png and returns the client's JSON result."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g_up = _hashed_copy(Path(guide), tmp, "guide")
        r_up = _hashed_copy(Path(ref), tmp, "ref")
        wf = tmp / "workflow.json"
        wf.write_text(json.dumps({"client_id": "mesh-texture-paint",
                                  "prompt": graph(g_up.name, r_up.name, prompt, seed=seed, models=models)}))
        cmd = [sys.executable, str(CLIENT), "--workflow", str(wf), "--output-dir", str(tmp / "out"),
               "--upload", str(g_up), "--upload", str(r_up), "--timeout-seconds", str(timeout)]
        if server:
            cmd += ["--server", server]
        if keep_loaded:
            cmd.append("--keep-loaded")
        r = subprocess.run(cmd, capture_output=True, text=True)
        outs = sorted((tmp / "out").glob("**/*.png")) if (tmp / "out").exists() else []
        if r.returncode != 0 or not outs:
            raise RuntimeError(f"paint job failed (exit {r.returncode}): {r.stderr[-400:]}")
        out_png.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(outs[0], out_png)
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            return {}


def selftest() -> int:
    """Check the graph's wiring and that the shipped template matches graph(); no network."""
    checks = {}
    g = graph("guide.png", "ref.png", "paint it", seed=7)
    loads = {k: n["inputs"]["image"] for k, n in g.items() if n["class_type"] == "LoadImage"}
    guide_id = next(k for k, v in loads.items() if v == "guide.png")
    ref_id = next(k for k, v in loads.items() if v == "ref.png")
    enc = [n for n in g.values() if n["class_type"] == "TextEncodeQwenImageEditPlus"]
    checks["two_images"] = len(loads) == 2 and len(enc) == 2 and all(
        sorted(k for k in n["inputs"] if k.startswith("image")) == ["image1", "image2"]
        and n["inputs"]["image1"] == [guide_id, 0] and n["inputs"]["image2"] == [ref_id, 0] for n in enc)
    ks = next(n for n in g.values() if n["class_type"] == "KSampler")["inputs"]
    lat = g[ks["latent_image"][0]]
    checks["latent_is_guide"] = lat["class_type"] == "VAEEncode" and lat["inputs"]["pixels"] == [guide_id, 0]
    checks["sampler"] = (ks["steps"], ks["cfg"], ks["denoise"], ks["sampler_name"], ks["scheduler"], ks["seed"]) \
        == (4, 1.0, 1.0, "euler", "simple", 7)
    shift = next(n for n in g.values() if n["class_type"] == "ModelSamplingAuraFlow")["inputs"]
    lora = [n for n in g.values() if n["class_type"] == "LoraLoaderModelOnly"]
    checks["lightning_default"] = (len(lora) == 1 and lora[0]["inputs"]["lora_name"] == MODELS["lora"]
                                   and shift["model"] == ["2", 0] and shift["shift"] == 3.1)
    g2 = graph("guide.png", "ref.png", "p", lightning=False)
    checks["lightning_off"] = not any(n["class_type"] == "LoraLoaderModelOnly" for n in g2.values()) \
        and g2["3"]["inputs"]["model"] == ["1", 0]
    refm = [n["inputs"]["reference_latents_method"] for n in g.values()
            if n["class_type"] == "FluxKontextMultiReferenceLatentMethod"]
    checks["reference_method"] = refm == ["index_timestep_zero"] * 2
    # every link points at an existing node
    links = [v for n in g.values() for v in n["inputs"].values() if isinstance(v, list)]
    checks["links_resolve"] = all(v[0] in g for v in links)
    m = load_models('{"unet": "my_unet.safetensors"}')
    gm = graph("a.png", "b.png", "p", models=m)
    checks["models_override"] = gm["1"]["inputs"]["unet_name"] == "my_unet.safetensors" \
        and gm["6"]["inputs"]["vae_name"] == MODELS["vae"]
    try:
        load_models('{"text_encoder": "x"}')
        checks["models_unknown_key"] = False
    except ValueError:
        checks["models_unknown_key"] = True
    try:
        tpl = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        checks["template_matches"] = (set(tpl) == {"client_id", "prompt"}
                                      and tpl["prompt"] == graph(*TEMPLATE_ARGS))
    except (OSError, json.JSONDecodeError):
        checks["template_matches"] = False
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
    ap = UsageParser(prog="qwen_paint.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("guide", type=Path, help="picture 1: the guide render (its layout is kept)")
    ap.add_argument("ref", type=Path, help="picture 2: the one reference image")
    ap.add_argument("out", type=Path, help="where the painted PNG is written")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--server", default=os.environ.get("COMFYUI_SERVER_URL"),
                    help="ComfyUI URL (default: the COMFYUI_SERVER_URL environment variable)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--models", help="JSON file or inline JSON mapping unet/clip/vae/lora to file names")
    ap.add_argument("--graph-only", action="store_true", help="print the API graph and exit")
    ap.add_argument("--selftest", action="store_true", help="check graph wiring and the template, no network")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        models = load_models(a.models)
    except (ValueError, OSError) as e:
        ap.error(str(e))
    if a.graph_only:
        print(json.dumps(graph(a.guide.name, a.ref.name, a.prompt, a.seed, models=models), indent=1))
        return 0
    for p in (a.guide, a.ref):
        if not p.is_file():
            ap.error(f"image not found: {p}")
    try:
        paint(a.guide, a.ref, a.prompt, a.out, a.server, a.seed, models=models)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 3
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
