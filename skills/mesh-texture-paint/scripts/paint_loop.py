#!/usr/bin/env python3
"""Repaint the base colour of an image-to-3D mesh view by view, guided by concept art.

Each step renders the mesh from one camera and has the edit model paint that view (picture 1
the render, picture 2 one reference). The first view is a plain clay render with the
turnaround sheet. Every later view is a context render: what is painted so far in colour,
unpainted surface showing a prior (by default the GLB's own texture, brightness-matched to the
painted texels), which the model repaints to match the reference. The output is registered to
the render silhouette, gated (silhouette IoU, outline distance, painted share, brightness drift,
dark-to-light share, background deviation) and its painted pixels are projected into the UV
texture. Anchor cameras go first, then the camera that sees the most unpainted surface
(zoomed onto it unless the mesh is thin), until coverage, the view budget or three rejections
in a row stop the loop; optional detail passes follow. Up to --tries seeds per camera, the
reference alternating between the sheet and the nearest concept view.

Writes <out>/basecolor.png, <out>/<glb-stem>_painted.glb (the input GLB with only the base
colour image replaced), <out>/coverage.png, <out>/turntable.png, <out>/report.json,
<out>/views/ (guides, outputs, aligned) and <out>/state.npz (continue with --resume).

  python3 paint_loop.py runner.glb --concept concept/ --sheet turnaround.png --out paint/
  python3 paint_loop.py --selftest      the whole loop offline on a cube with a fake painter

Exit codes: 0 done or selftest passed, 1 usage error (also a GLB whose base colour cannot be
written, caught before any paint job), 2 selftest failed, 3 no view painted or the paint server
unreachable / not configured (the run stops at the first such error; views painted before it are
written out and --resume continues).
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

import mvtex as M
import qwen_paint as Q

CONCEPT_YAW = {"front": 0, "left": 90, "back": 180, "right": 270}
# client errors no retry can fix: the run stops at the first one (exit 3)
FATAL = ("Cannot reach the configured ComfyUI server", "No ComfyUI server URL")

P_FIRST = ("Picture 1 is a grey clay 3D render of a {subject} on a pure green background, seen from the {label}. "
           "Picture 2 is {refdesc}. Paint the clay {subject} in Picture 1 as this {subject}: the same {details} as "
           "in Picture 2. Keep the exact pose, silhouette, size and position of Picture 1, pixel for pixel; only add "
           "colour and surface detail. Flat even lighting with no cast shadows and no highlights. Keep the pure green "
           "background. Draw only this one {subject}, no other views or copies.")
P_DETAIL = ("Picture 1 is a close-up 3D render of part of a coloured {subject} on a pure green background, seen "
            "from the {label}. Picture 2 is {refdesc}. Repaint Picture 1 with clean, sharp detail so it matches the "
            "{subject} in Picture 2: the same {details}. Keep the colours already there, and the exact silhouette, size "
            "and position of Picture 1, pixel for pixel. Flat even lighting with no cast shadows and no highlights. Keep "
            "the pure green background.")
P_CONTEXT = ("Picture 1 is a partly coloured 3D render of a {subject} on a pure green background, seen from the "
             "{label}. The {grey} areas are not painted yet. Picture 2 is {refdesc}. Paint the {grey} areas so they "
             "match the {subject} in Picture 2 and continue the existing colours smoothly. Keep the already coloured "
             "areas, the pose, silhouette, size and position of Picture 1 exactly. Flat even lighting with no cast "
             "shadows and no highlights. Keep the pure green background. Draw only this one {subject}, no other views or "
             "copies.")
P_FILL = ("Picture 1 is a 3D render of a {subject} on a pure green background, seen from the {label}. Parts of it "
          "are only rough colour blocks without the right details. Picture 2 is {refdesc}. Repaint the {subject} in "
          "Picture 1 so it matches Picture 2 everywhere: the same {details}, in the right places for this view. Keep "
          "the well-painted areas, and the exact pose, silhouette, size and position of Picture 1, pixel for pixel. "
          "Flat even lighting with no cast shadows and no highlights. Keep the pure green background. Draw only this "
          "one {subject}, no other views or copies.")
DETAILS = {"character": "face, hair, outfit, colours, materials and details",
           "object": "colours, materials, markings and details"}


def view_label(yaw, pitch, zoomed):
    y = yaw % 360
    d = min(y, 360 - y)
    lab = ("front" if d < 22.5 else "front three-quarter" if d < 67.5 else "side" if d < 112.5
           else "back three-quarter" if d < 157.5 else "back")
    if pitch > 30:
        lab += ", looking down from above"
    elif pitch < -30:
        lab += ", looking up from below"
    return ("close-up of part of it, " + lab) if zoomed else lab


def nearest_concept(yaw):
    return min(CONCEPT_YAW, key=lambda k: min(abs(yaw - CONCEPT_YAW[k]) % 360, 360 - abs(yaw - CONCEPT_YAW[k]) % 360))


def make_cam(mesh, plan, size, fill):
    return M.Camera.orbit(mesh.center, plan["radius"], plan["yaw"], plan["pitch"], size=size, fill=fill,
                          target=plan.get("target"))


def turntable(mesh, radius, fill, texs, labels, path, tile=320):
    yaws = [0, 45, 90, 135, 180, 225, 270, 315]
    sheet = Image.new("RGB", (len(yaws) * tile, len(texs) * (tile + 20)), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for j, (t, lab) in enumerate(zip(texs, labels)):
        d.text((6, j * (tile + 20) + 4), lab, fill=(255, 255, 255))
        for i, yw in enumerate(yaws):
            c = M.Camera.orbit(mesh.center, radius, yw, 10, size=640, fill=fill)
            img, _ = M.render_texture(mesh, c, t, bg=np.array([40, 40, 40], np.uint8))
            sheet.paste(Image.fromarray(img).resize((tile, tile), Image.LANCZOS), (i * tile, j * (tile + 20) + 20))
    sheet.save(path)


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1, never 2."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    ap = UsageParser(prog="paint_loop.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("glb", type=Path, help="image-to-3D mesh with UVs (TEXCOORD_0) and a base-colour texture")
    ap.add_argument("--concept", type=Path, required=True, help="folder with front/left/back/right.png")
    ap.add_argument("--sheet", type=Path, help="turnaround sheet (one image with all four views)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--kind", choices=list(DETAILS), default="character")
    ap.add_argument("--subject", default=None, help="noun used in prompts (default: the kind)")
    ap.add_argument("--ref", choices=["sheet", "nearest"], default="sheet",
                    help="picture 2: the whole turnaround sheet or the concept view nearest in yaw")
    ap.add_argument("--context", choices=["fill", "flat", "clay", "magenta"], default="fill",
                    help="how unpainted surface is shown: fill = the --prior texture (default the GLB's own, "
                         "brightness-matched; nearest painted colour without one); flat/clay grey reads as grey "
                         "material, magenta bleeds into purple")
    ap.add_argument("--anchors", default="0:0,45:0,315:0,90:0,270:0,135:0,225:0,180:0",
                    help="yaw:pitch cameras painted first, in order")
    ap.add_argument("--max-views", type=int, default=16)
    ap.add_argument("--pitch-range", type=float, nargs=2, default=(-40.0, 50.0),
                    help="cameras stay in this pitch band: steeper views come back as eye-level drawings")
    ap.add_argument("--target", type=float, default=0.97, help="stop at this share of the seeable surface")
    ap.add_argument("--min-gain", type=float, default=0.003, help="skip a camera that adds less than this")
    ap.add_argument("--no-zoom", action="store_true")
    ap.add_argument("--no-nbv", action="store_true", help="paint the anchors only")
    ap.add_argument("--min-iou", type=float, default=0.90)
    ap.add_argument("--max-edge", type=float, default=24.0, help="outline distance p90 (px at 1024) to accept a view")
    ap.add_argument("--min-share", type=float, default=0.3, help="share of the unpainted pixels the painted view covers (fill) or repaints "
                                                                   "(grey/magenta markers) to accept a view")
    ap.add_argument("--tries", type=int, default=3, help="seeds per camera before giving up on it")
    ap.add_argument("--refine", type=float, default=1.5, help="0 blends every view")
    ap.add_argument("--detail", default="", help="character: 'head' adds zoomed repaint passes on the head")
    ap.add_argument("--detail-ref", type=Path, help="picture 2 for detail passes (default: front concept)")
    ap.add_argument("--no-match", action="store_true")
    ap.add_argument("--prior", default="self",
                    help="texture shown on unpainted surface (fill context): 'self' = the GLB's own base colour "
                         "(an image-to-3D bake: right layout, dull colours), a GLB or image path, or '' for "
                         "the nearest painted colour")
    ap.add_argument("--max-lighten", type=float, default=0.06,
                    help="reject a view that turns this share of dark guide pixels light (silver hair)")
    ap.add_argument("--max-bg-dev", type=float, default=40.0,
                    help="reject a view whose background drifted this far from the key (washed-out output)")
    ap.add_argument("--max-drift", type=float, default=0.08,
                    help="reject a view that changes the brightness of this share of already-painted pixels")
    ap.add_argument("--res", type=int, default=2048)
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--fill", type=float, default=0.92)
    ap.add_argument("--server", default=os.environ.get("COMFYUI_SERVER_URL"),
                    help="ComfyUI URL (default: the COMFYUI_SERVER_URL environment variable)")
    ap.add_argument("--models", help="JSON file or inline JSON mapping unet/clip/vae/lora to the server's "
                                     "model file names (see qwen_paint.py)")
    ap.add_argument("--compare", type=Path, help="GLB whose texture goes in the turntable's first row")
    ap.add_argument("--resume", action="store_true", help="continue from <out>/state.npz and report.json")
    ap.add_argument("--selftest", action="store_true", help="run the loop offline on a cube; no network")
    return ap


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv in (["--selftest"], ["selftest"]):
        return selftest()
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.glb.is_file():
        ap.error(f"GLB not found: {a.glb}")
    if not a.concept.is_dir():
        ap.error(f"concept folder not found: {a.concept}")
    if a.sheet and not a.sheet.is_file():
        ap.error(f"turnaround sheet not found: {a.sheet}")
    if a.resume and (a.out / "state.npz").exists() and not (a.out / "report.json").exists():
        ap.error(f"--resume: {a.out / 'state.npz'} has no report.json beside it")
    try:
        models = Q.load_models(a.models)
    except (ValueError, OSError) as e:
        ap.error(str(e))

    try:
        mesh = M.load_glb(str(a.glb))
        with tempfile.TemporaryDirectory() as td:  # fail before any paint job, not at the final write
            M.write_glb_basecolor(str(a.glb), str(Path(td) / "probe.glb"), Image.new("RGB", (4, 4)))
    except (KeyError, IndexError, TypeError, ValueError, OSError, struct.error) as e:
        ap.error(f"cannot read the GLB or write its base colour: {type(e).__name__}: {e}")
    subject = a.subject or a.kind
    out = a.out
    (out / "views").mkdir(parents=True, exist_ok=True)
    radius = float((mesh.v.max(0) - mesh.v.min(0)).max() / 2)
    acc = M.Accumulator(mesh, a.res)
    lo_p, hi_p = a.pitch_range
    seeable = []
    for d in M.fibonacci_dirs(128):
        yw, pt = M.dir_to_yaw_pitch(d)
        if lo_p <= pt <= hi_p:
            seeable.append(M.Camera.orbit(mesh.center, radius, yw, pt, size=256, fill=a.fill))
    acc.mark_seeable(seeable)
    log, used = [], []
    if a.resume and (out / "state.npz").exists():
        acc.load(out / "state.npz")
        st = json.loads((out / "report.json").read_text())
        log = st["views"]
        used = [(v["yaw"], v["pitch"]) for v in log]
    anchors = [tuple(float(x) for x in s.split(":")) for s in a.anchors.split(",") if s]
    refs = {k: a.concept / f"{k}.png" for k in CONCEPT_YAW}
    stale = 0
    prior = None
    if a.prior:
        src = a.glb if a.prior == "self" else Path(a.prior)
        try:
            pimg = M.glb_image(str(src)) if src.suffix.lower() == ".glb" else Image.open(src).convert("RGB")
            prior = acc.prior_colors(np.asarray(pimg))
        except (KeyError, TypeError, IndexError, OSError):
            print("no prior texture found; unpainted surface shows the nearest painted colour", file=sys.stderr)
    use_despill = not M.palette_has_key_hue([Image.open(p) for p in refs.values() if p.exists()])
    details = []
    if a.detail == "head":
        h = mesh.v[:, 1].max() - mesh.v[:, 1].min()
        top = mesh.v[mesh.v[:, 1] > mesh.v[:, 1].max() - 0.16 * h]
        tgt = (top.max(0) + top.min(0)) / 2
        tgt[1] -= 0.02 * h  # face sits below the middle of hair + head
        tgt = tgt.tolist()
        r = float((top.max(0) - top.min(0)).max() / 2) * 1.3
        details = [{"yaw": yw, "pitch": 5.0, "radius": r, "target": tgt, "source": "detail"} for yw in (0.0, 40.0, 320.0)]
    if log:  # --resume: detail passes already run are not repeated; a trailing run of rejections still counts
        done = {(v["yaw"], v["pitch"]) for v in log if v.get("source") == "detail"}
        details = [d for d in details if (d["yaw"], d["pitch"]) not in done]
        for v in reversed(log):
            if v.get("status") not in ("rejected", "failed: no output"):
                break
            stale += 1
    t_start = time.time()
    main_done = False
    fatal = None
    while True:
        plan = None
        if not main_done and (acc.views >= a.max_views or acc.coverage() >= a.target or stale >= 3):
            main_done = True
        while not main_done and plan is None and anchors:
            yw, pt = anchors.pop(0)
            if (yw, pt) not in used:
                plan = {"yaw": yw, "pitch": pt, "radius": radius, "target": None, "source": "anchor"}
        if not main_done and plan is None and a.no_nbv:
            main_done = True
        if not main_done and plan is None:
            nb = M.next_best_view(acc, radius, a.fill, used, pitch=(lo_p, hi_p), zoom=not a.no_zoom)
            if nb is None or nb["gain"] < a.min_gain:
                main_done = True
            else:
                plan = {**nb, "source": "nbv"}
        if plan is None:
            if not details:
                break
            plan = details.pop(0)
        used.append((plan["yaw"], plan["pitch"]))
        cam = make_cam(mesh, plan, a.size, a.fill)
        tex = acc.texture(fill=a.context == "fill", gutter=True, prior=prior if a.context == "fill" else None)
        first = not (acc.wsum > 0).any()
        detail = plan["source"] == "detail"
        img, rmask, unp, base, tri, dep = M.render_context(mesh, cam, tex, acc.painted_texmask(),
                                                           "clay" if first else a.context)
        share_unp = float(unp.sum() / max(1, rmask.sum()))
        name = f"v{len(log):02d}_y{int(plan['yaw']) % 360:03d}_p{int(round(plan['pitch'])):+03d}" + ("z" if plan.get("target") else "")
        rec = {"name": name, **{k: plan[k] for k in ("yaw", "pitch", "source")}, "zoom": bool(plan.get("target")),
               "unpainted_share": round(share_unp, 3)}
        if share_unp < 0.02 and not detail:
            rec["status"] = "skipped: nothing unpainted in view"
            log.append(rec)
            continue
        guide = out / "views" / f"{name}_guide.png"
        Image.fromarray(img).save(guide)
        zoomed = bool(plan.get("target"))
        k = nearest_concept(plan["yaw"])
        options = {"sheet": (a.sheet, f"a turnaround sheet of that {subject} (front, left, back and right views)"),
                   "nearest": (refs[k], f"the concept art of that {subject} seen from the "
                                        f"{k if k in ('front', 'back') else 'side'}")}
        if not a.sheet:
            options.pop("sheet")
        # the other reference is the fallback: a whole sheet can make the model paint a collage of
        # several figures, a single view can make it copy that view's facing
        order = [a.ref, "nearest" if a.ref == "sheet" else "sheet"] if a.ref in options else ["nearest"]
        order = [o for o in order if o in options]
        fmt = {"subject": subject, "label": view_label(plan["yaw"], plan["pitch"], zoomed),
               "details": DETAILS[a.kind], "grey": {"clay": "plain grey clay", "flat": "flat grey", "magenta": "magenta", "fill": ""}[a.context]}
        rec["prompt_mode"] = "detail" if detail else "first" if first else "context"
        best = None
        for t in range(a.tries):
            if detail:
                ref, refdesc, rname = a.detail_ref or refs["front"], f"concept art of that {subject}", "front"
            else:
                rname = order[t % len(order)]
                ref, refdesc = options[rname]
            ctx_prompt = P_FILL if a.context == "fill" else P_CONTEXT
            prompt = (P_DETAIL if detail else P_FIRST if first else ctx_prompt).format(refdesc=refdesc, **fmt)
            seed = 42 + 1000 * t + len(log)
            raw = out / "views" / f"{name}_s{seed}.png"
            t0 = time.time()
            try:
                Q.paint(guide, ref, prompt, raw, a.server, seed=seed, models=models)
            except RuntimeError as e:
                rec.setdefault("errors", []).append(str(e)[-200:])
                if any(f in str(e) for f in FATAL):
                    fatal = str(e)[-400:]
                    break
                continue
            pim = Image.open(raw).convert("RGB")
            if pim.size != (cam.width, cam.height):
                pim = pim.resize((cam.width, cam.height), Image.LANCZOS)
            bg_dev = M.background_deviation(np.asarray(pim), rmask)
            warped, wm, al = M.align_painted(np.asarray(pim), rmask)
            if use_despill:
                warped = M.despill(warped, rmask)
            changed = np.ones_like(rmask) if (a.context == "fill" and not first) else M.painted_pixels(warped, base)
            # stay clear of places where the drawn outline disagrees with the render (a strap moved)
            near_miss = ndimage.binary_dilation(rmask ^ wm, iterations=6)
            pm = rmask & wm & (~unp | changed) & ~near_miss
            drift = 0.0 if first or detail else M.drift_share(warped, img, rmask & wm & ~unp & ~near_miss)
            filled = 1.0 if detail else float((unp & wm & changed).sum() / max(1, unp.sum()))
            cand = {"seed": seed, "ref": rname, "paint_s": round(time.time() - t0, 1), **al, "filled": round(filled, 3)}
            light = 0.0 if first else M.lighten_share(warped, img, rmask & wm & ~unp & ~near_miss)
            cand.update({"drift": round(drift, 3), "lighten": round(light, 3), "bg_dev": round(bg_dev, 1)})
            cand["ok"] = (al["iou_after"] >= a.min_iou and al["edge_p90"] <= a.max_edge and filled >= a.min_share
                          and drift <= a.max_drift and light <= a.max_lighten and bg_dev <= a.max_bg_dev)
            key = (cand["ok"], al["iou_after"] * filled)
            if best is None or key > best[0]:
                best = (key, cand, warped, pm)
            if cand["ok"]:
                break
        if best is None:
            ok = False
            rec["status"] = "failed: no output"
        else:
            _, cand, warped, pm = best
            ok = cand.pop("ok")
            rec.update(cand)
            Image.fromarray(warped).save(out / "views" / f"{name}_aligned.png")
        if fatal:
            log.append(rec)
            (out / "report.json").write_text(json.dumps({"views": log}, indent=1))
            break
        if best is None:
            acc.views += 1  # a view that produced nothing counts as a rejection
            stale += 1
        elif ok:
            cov0 = acc.coverage()
            # closer cameras put more pixels on each texel: weight them up so they win the refine test
            vw = min(3.0, radius / plan["radius"])
            rec.update(acc.add_view(cam, warped, pm, vw, tri, dep, refine=a.refine if a.refine > 0 else None,
                                    match=not a.no_match))
            rec["status"] = "used"
            rec["coverage"] = round(acc.coverage(), 4)
            rec["gain"] = round(rec["coverage"] - cov0, 4)
            stale = 0
        else:
            rec["status"] = "rejected"
            acc.views += 1  # counts against the budget
            stale += 1
        log.append(rec)
        print(json.dumps(rec), flush=True)
        acc.save(out / "state.npz")
        (out / "report.json").write_text(json.dumps({"views": log}, indent=1))

    painted_any = any(v.get("status") == "used" for v in log)
    if fatal or not painted_any:
        print(f"paint server error, run stopped: {fatal}" if fatal else
              "no view was painted; check --server / COMFYUI_SERVER_URL and --models", file=sys.stderr)
        if not painted_any:
            return 3
    # surface no camera reached keeps the (brightness-matched) prior, else the nearest painted colour
    tex = acc.texture(prior=prior)
    Image.fromarray(tex).save(out / "basecolor.png")
    Image.fromarray(acc.painted_mask_image()).save(out / "coverage.png")
    M.write_glb_basecolor(str(a.glb), str(out / f"{a.glb.stem}_painted.glb"), Image.fromarray(tex))
    rows, labels = [tex], [f"painted  coverage {acc.coverage():.3f}"]
    if a.compare:
        rows.insert(0, np.asarray(M.glb_image(str(a.compare))))
        labels.insert(0, "comparison texture")
    turntable(mesh, radius, a.fill, rows, labels, out / "turntable.png")
    rep = {"coverage_seeable": round(acc.coverage(), 4), "seam_delta": round(acc.seam_delta(), 2),
           "views_used": sum(v.get("status") == "used" for v in log), "minutes": round((time.time() - t_start) / 60, 1),
           "settings": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(a).items()}, "views": log}
    (out / "report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: rep[k] for k in ("coverage_seeable", "seam_delta", "views_used", "minutes")}))
    return 3 if fatal else 0



def selftest() -> int:
    """Run the whole loop on a textured cube with a fake painter that colours the guide."""
    import tempfile
    t0 = time.time()
    real_paint = Q.paint
    calls = []

    def fake_paint(guide, ref, prompt, out_png, server=None, seed=42, models=None, **_kw):
        # a model that paints the view: figure pixels warm up a little, background stays key
        g = np.asarray(Image.open(guide).convert("RGB")).astype(np.float64)
        fg = M.key_mask(g.astype(np.uint8))
        o = g.copy()
        o[fg] = np.clip(0.8 * g[fg] + np.array([50.0, 20.0, 0.0]), 0, 255)
        Path(out_png).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(o.astype(np.uint8)).save(out_png)
        calls.append({"ref": Path(ref).name, "prompt": prompt, "models": models})
        return {}

    checks = {}
    try:
        Q.paint = fake_paint
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            mesh = M.cube_mesh()
            yy, xx = np.mgrid[0:256, 0:256]
            dull = np.stack([90 + (xx % 64), 80 + (yy % 48), np.full_like(xx, 70)], -1).astype(np.uint8)
            glb = td / "parcel.glb"
            M.write_glb(mesh, Image.fromarray(dull), glb)
            concept = td / "concept"
            concept.mkdir()
            for k in CONCEPT_YAW:
                im = np.zeros((128, 128, 3), np.uint8)
                im[24:104, 32:96] = (180, 90, 40)  # an orange parcel on black
                Image.fromarray(im).save(concept / f"{k}.png")
            sheet = td / "sheet.png"
            Image.fromarray(np.concatenate([np.asarray(Image.open(concept / f"{k}.png"))
                                            for k in ("front", "left", "back", "right")], 1)).save(sheet)
            out = td / "out"
            code = main([str(glb), "--concept", str(concept), "--sheet", str(sheet), "--out", str(out),
                         "--kind", "object", "--subject", "parcel bag", "--anchors", "0:0,90:0",
                         "--max-views", "5", "--size", "256", "--res", "256", "--detail", "head",
                         "--models", '{"unet": "custom_unet.safetensors"}'])
            checks["exit_0"] = code == 0
            rep = json.loads((out / "report.json").read_text())
            used = [v for v in rep["views"] if v.get("status") == "used"]
            covs = [v["coverage"] for v in used if "coverage" in v]
            checks["report_keys"] = all(k in rep for k in ("coverage_seeable", "seam_delta", "views_used", "views"))
            checks["coverage_rises"] = (len(covs) >= 3 and covs[-1] > covs[0]
                                        and all(b >= a - 1e-9 for a, b in zip(covs, covs[1:])))
            checks["nbv_and_detail_ran"] = ({"anchor", "nbv", "detail"}
                                            <= {v["source"] for v in rep["views"]})
            checks["no_ok_key"] = all("ok" not in v for v in rep["views"])
            painted = out / "parcel_painted.glb"
            pm = M.load_glb(painted)
            new = np.asarray(M.glb_image(painted))
            checks["painted_glb"] = (np.allclose(pm.v, mesh.v) and (pm.f == mesh.f).all()
                                     and float(np.abs(new.astype(int) - dull.astype(int)).mean()) > 5)
            checks["outputs"] = all((out / n).exists() for n in ("basecolor.png", "coverage.png",
                                                                 "turntable.png", "state.npz"))
            checks["prompts"] = (len(calls) > 0 and all(c["models"]["unet"] == "custom_unet.safetensors" for c in calls)
                                 and all("Draw only this one parcel bag" in c["prompt"]
                                         for c in calls if "close-up" not in c["prompt"]))
            import contextlib
            import io
            base = [str(glb), "--concept", str(concept), "--sheet", str(sheet), "--kind", "object",
                    "--subject", "parcel bag", "--size", "256", "--res", "256"]
            # --resume with a larger budget does not repeat the detail passes
            n0 = len(calls)
            main(base + ["--out", str(out), "--anchors", "0:0,90:0", "--max-views", "7", "--detail", "head",
                         "--resume"])
            rep2 = json.loads((out / "report.json").read_text())
            checks["resume_no_repeat_detail"] = (sum(v["source"] == "detail" for v in rep2["views"]) == 3
                                                 and len(rep2["views"]) >= len(rep["views"])
                                                 and not any("close-up" in c["prompt"] and "front" == c["ref"][:5]
                                                             for c in calls[n0:]))
            # an unzoomed next-best-view camera is not labelled or named as a close-up
            n0 = len(calls)
            main(base + ["--out", str(td / "nz"), "--anchors", "0:0", "--max-views", "3", "--no-zoom"])
            nz = [v for v in json.loads((td / "nz" / "report.json").read_text())["views"] if v["source"] == "nbv"]
            checks["no_zoom_label"] = (len(nz) > 0 and not any(v["zoom"] or v["name"].endswith("z") for v in nz)
                                       and not any("close-up" in c["prompt"] for c in calls[n0:]))
            # a GLB without a base-colour texture paints and gets one; a GLB that cannot be written is exit 1
            bare = td / "bare.glb"
            M.edit_glb_json(glb, lambda js: js["materials"][0]["pbrMetallicRoughness"].pop("baseColorTexture"), bare)
            with contextlib.redirect_stderr(io.StringIO()):
                code = main([str(bare)] + base[1:] + ["--out", str(td / "bare"), "--anchors", "0:0,90:0",
                                                      "--no-nbv"])
            checks["textureless_glb"] = bool(code == 0 and np.asarray(M.glb_image(td / "bare" / "bare_painted.glb")).std() > 0)
            junk = td / "junk.glb"
            junk.write_bytes(b"glTF" + b"\0" * 40)
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    main([str(junk)] + base[1:] + ["--out", str(td / "junk")])
                checks["bad_glb_exit_1"] = False
            except SystemExit as e:
                checks["bad_glb_exit_1"] = e.code == 1 and not (td / "junk").exists()
            # a painter that never returns: the loop stops after 3 failed views (exit 3); a connection error stops at once
            for tag, msg, limit in (("fail_stops", "paint job failed (exit 1): model missing", 9),
                                    ("unreachable_stops", "Cannot reach the configured ComfyUI server: refused", 1)):
                def broken(*_a, _m=msg, **_k):
                    calls.append({"ref": "", "prompt": "", "models": None})
                    raise RuntimeError(_m)
                Q.paint = broken
                n0 = len(calls)
                with contextlib.redirect_stderr(io.StringIO()):
                    code = main(base + ["--out", str(td / tag), "--max-views", "16"])
                checks[tag] = (code == 3 and 0 < len(calls) - n0 <= limit
                               and not (td / tag / "parcel_painted.glb").exists())
            Q.paint = fake_paint
            # usage errors exit 1
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    build_parser().parse_args(["x.glb"])
                checks["usage_exit_1"] = False
            except SystemExit as e:
                checks["usage_exit_1"] = e.code == 1
            summary = {k: rep[k] for k in ("coverage_seeable", "views_used")}
    finally:
        Q.paint = real_paint
    ok = all(checks.values())
    print(json.dumps({"checks": checks, **summary, "paint_calls": len(calls),
                      "seconds": round(time.time() - t0, 1), "pass": ok}))
    return 0 if ok else 2

if __name__ == "__main__":
    sys.exit(main())
