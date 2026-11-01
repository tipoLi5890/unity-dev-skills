#!/usr/bin/env python3
"""hand_views.py — the hand parts of a character in parts (tier fine): guides, redraws, gates, the
generate-and-register loop and the paint step. part_views.py runs this for every part whose region is
hand.L or hand.R; the commands and flags are part_views.py's.

  part_views.py views    PLAN.parts.json --views CLEAN_DIR --part hand_r
  part_views.py generate PLAN.parts.json --part hand_r [--hand-seeds 3] [--paint]
  hand_views.py --selftest          no network: guide, prior, band gates, mirror, prompt, seeds

The plan's hand part comes from blender-character-rig `part_math.py plan --tier fine` (hand_parts.py
there): its `wrist` (forearm axis, wrist plane, bottom plane, forearm and sleeve radii), its crop boxes and
keep masks, and `views.hidden` (the view the body hides and the view it mirrors).

views, per hand:
  guide    the box crop of the clean view where the keep mask holds (the sleeve near the cuff removed by
           geometry); the forearm the sleeve hid painted as a shaded skin cylinder (0.8 x r_fore, Lambert
           0.75-1 of the visible forearm's colour) with a flat end at the bottom plane, from there to
           1.5 x r_fore past the wrist plane, only where the keep mask dropped pixels; Lanczos to 1024.
  redraw   Qwen 2511 + Lightning at denoise 1.0, the guide as both pictures; the prompt asks for black
           gaps between the fingers (cloth between them is background) and a smooth bare forearm cut flat
           at its end, no sleeve. Only the visible views are redrawn: the hidden view is the mirrored
           redraw of its source (asking the model for a palm keeps the back of the hand and can leave a
           ghost hand). The redraw is clipped to an 8 px band around the guide and the stub's corridor.
  gates    part.redraw_inside >= 0.98 (the redraw's silhouette inside a 6 px band of the guide's, the
           forearm stub's corridor, one sleeve radius around the prior, not counted: the assembly cuts the
           stub at its bottom plane and seam.sleeve_clearance gates its width) and
           part.redraw_cover >= 0.85 (the guide's covered by a 6 px band of the redraw's): a thin part over
           clothing loses the cloth between its fingers, which an IoU punishes; part.redraw_colour
           <= 0.06 of the cells inside both silhouettes, the forearm prior left out (a ghost hand, a
           recoloured glove; a cell on a finger's edge mixes in the background the redraw rightly gives
           the gaps, and the prior is a stand-in the redraw repaints); part.sharpness >= --sharpness-factor. A failing
           view retries the next seed.
  clean    the four views through the background-removal template; part.bg_area in [0.95, 1.05];
           views/<hand>/{front,left,back,right}.png, sheet.png, part_views.gate.json, views.colours.skin.

generate, per hand: the Pixal3D multi-view job at the part's preset with its face target set to
--hand-ratio (0.2) x the anchor's triangles (the job decimates before it unwraps and bakes; a collapse in
Blender afterwards must weld first, or it tears the textured mesh open along its UV seams), then
hand_parts.py gate (the registration and finger gates, blender-character-rig); on exit 2 the job runs again with every sampler
seed moved (up to --hand-seeds jobs): a gate is never loosened. --paint then runs mesh-texture-paint's
paint_loop.py on the passing GLB (--kind object, --prior '': the bake's own texture streaks and tints the
context) into paint/<hand>/, so the glove keeps the concept's colour (the multi-view bake darkens it).

Exit codes are part_views.py's: 0 done; 1 usage or refused plan; 2 a gate failed after every seed; 3 a
server or job failure.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
HAND_PARTS = SKILL.parent / "blender-character-rig" / "scripts" / "hand_parts.py"
PAINT_LOOP = SKILL.parent / "mesh-texture-paint" / "scripts" / "paint_loop.py"

VIEWS = ("front", "left", "back", "right")
TOWARD = {"front": (2, 1.0), "back": (2, -1.0), "left": (0, 1.0), "right": (0, -1.0)}   # axis, sign toward the camera
PRIOR_SCALE, PRIOR_PAST = 0.8, 1.5       # stub radius x r_fore; how far past the wrist plane it is painted
BAND_PX, INSIDE_MIN, COVER_MIN, CLIP_PX = 6, 0.98, 0.85, 8
SAMPLERS = (3, 12, 18, 23)               # the Pixal3D template's KSampler nodes
HAND_RATIO = 0.2                         # each hand's triangles: this x the anchor's (the job decimates to it)
SEED_STEP = 1000
SIDE = {"hand.R": "right", "hand.L": "left"}
LABEL = {"front": "front", "left": "left side", "back": "back", "right": "right side"}
PROMPT = ("Picture 1 is a low-resolution close-up of the {side} hand and bare forearm of a stylized 3D game character"
          "{hint}, on a pure black background, seen from the {label}. Picture 2 is the same image. Redraw it as a "
          "sharp, high-resolution, finely detailed image of the same hand: the same colours, the same finger shapes, "
          "nails and skin tone. Keep the exact view angle, silhouette, finger positions, size and position of "
          "Picture 1, pixel for pixel; only add sharp detail. Show clear gaps of pure black background between the "
          "fingers; any cloth between or around the fingers is background and must be painted pure black. The plain "
          "skin-coloured column is the bare forearm: paint it as a smooth straight forearm with the same skin tone, "
          "cut off flat at its end like a mannequin part, no sleeve, no cloth. Soft even lighting, no cast shadows. "
          "Keep the pure black background. Draw only this one hand with its forearm, no other views or copies.")


def _np():
    import numpy as np
    return np


def pv():
    sys.path.insert(0, str(HERE))
    import part_views
    return part_views


def prompt_for(part, view):
    hint = part.get("prompt_hint")
    return PROMPT.format(side=SIDE[part["region"]], label=LABEL[view], hint=f" wearing {hint}" if hint else "")


# ---------------------------------------------------------------------------------------- geometry
def _basis(a):
    np = _np()
    ref = np.array([0.0, 0.0, 1.0]) if abs(a[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(a, ref)
    u /= np.linalg.norm(u)
    return u, np.cross(a, u)


def project(plan, part, view, P):
    """Anchor points -> (col, row) in the view's box pixels (the plan's frame fit)."""
    np = _np()
    fr = plan["anchor"]["frame"]
    upp = float(fr["units_per_px"])
    off = fr["offset_px"][view]
    box = part["views"]["boxes"][view]
    u = {"front": P[:, 0], "back": -P[:, 0], "left": -P[:, 2], "right": P[:, 2]}[view]
    return np.c_[off[0] + u / upp - box[0], off[1] - P[:, 1] / upp - box[1]]


def forearm_prior(plan, part, view):
    """The forearm stub as the view sees it: (mask, shade) in box pixels. A cylinder of PRIOR_SCALE x
    r_fore from the bottom plane to PRIOR_PAST x r_fore past the wrist plane, with a flat end disc."""
    np = _np()
    from scipy import ndimage as ndi
    w = part["wrist"]
    a = np.asarray(w["axis"], float)
    rim, bottom = np.asarray(w["rim"], float), np.asarray(w["bottom"], float)
    rf = float(w["r_fore"])
    r = PRIOR_SCALE * rf
    L = int(part["views"]["box_side_px"])
    u, v = _basis(a)
    length = float((bottom - rim) @ a) + PRIOR_PAST * rf
    ts = np.linspace(0, length, 90)
    th = np.linspace(0, 2 * math.pi, 180, endpoint=False)
    T, TH = np.meshgrid(ts, th)
    N = np.cos(TH)[..., None] * u + np.sin(TH)[..., None] * v
    P = bottom - T[..., None] * a + r * N
    rr = np.linspace(0, r, 24)
    TH2, RR = np.meshgrid(th, rr)
    Pc = bottom + RR[..., None] * (np.cos(TH2)[..., None] * u + np.sin(TH2)[..., None] * v)
    P = np.r_[P.reshape(-1, 3), Pc.reshape(-1, 3)]
    N = np.r_[N.reshape(-1, 3), np.broadcast_to(a, Pc.shape).reshape(-1, 3)]
    ax, sg = TOWARD[view]
    cam = np.zeros(3)
    cam[ax] = sg
    lam = N @ cam
    vis = lam > 0
    q = project(plan, part, view, P[vis])
    depth = P[vis] @ cam
    mask = np.zeros((L, L), bool)
    shade = np.zeros((L, L))
    zb = np.full((L, L), -np.inf)
    qi = np.floor(q).astype(int)
    order = np.argsort(depth)              # far first: the nearest sample is written last
    for dx in (0, 1):
        for dy in (0, 1):
            x, y = qi[order, 0] + dx, qi[order, 1] + dy
            ok = (x >= 0) & (y >= 0) & (x < L) & (y < L)
            d = depth[order][ok]
            xx, yy, ll = x[ok], y[ok], lam[vis][order][ok]
            upd = d >= zb[yy, xx]
            zb[yy[upd], xx[upd]] = d[upd]
            shade[yy[upd], xx[upd]] = 0.75 + 0.25 * ll[upd]
            mask[yy[upd], xx[upd]] = True
    mask = ndi.binary_closing(mask, iterations=2)
    shade = ndi.grey_closing(shade, size=3)
    return mask, shade


def forearm_colour(plan, part, view, rgb, keep):
    """Median colour of the kept pixels around the visible forearm (half a forearm radius past the wrist
    plane): the stub is painted in it, so a glove up the wrist gives a glove-coloured stub."""
    np = _np()
    w = part["wrist"]
    p = np.asarray(w["rim"], float) - np.asarray(w["axis"], float) * 0.5 * float(w["r_fore"])
    c = project(plan, part, view, p[None])[0]
    fr = plan["anchor"]["frame"]
    rad = max(3.0, 1.2 * float(w["r_fore"]) / float(fr["units_per_px"]))
    yy, xx = np.mgrid[0:keep.shape[0], 0:keep.shape[1]]
    near = keep & ((xx + 0.5 - c[0]) ** 2 + (yy + 0.5 - c[1]) ** 2 <= rad * rad)
    if near.sum() < 6:
        return None
    return np.median(rgb[near].astype(float), axis=0)


def build_guide(plan, part, view, rgb, keep, colour):
    """(guide, silhouette, prior) in box pixels."""
    np = _np()
    mask, shade = forearm_prior(plan, part, view)
    prior = mask & ~keep
    guide = np.zeros_like(rgb)
    guide[keep] = rgb[keep]
    guide[prior] = np.clip(np.asarray(colour, float)[None] * shade[prior][:, None], 0, 255).astype(np.uint8)
    return guide, keep | prior, prior


# ------------------------------------------------------------------------------------------- gates
def hand_silhouette(rgb, thr=20):
    """max channel > thr, opened once, every piece at least 2 % of the largest (fingers drawn apart stay)."""
    np = _np()
    from scipy import ndimage as ndi
    m = np.asarray(rgb).max(2) > thr
    m = ndi.binary_opening(m, iterations=1)
    lab, n = ndi.label(m)
    if n == 0:
        return m
    sz = ndi.sum(m, lab, range(1, n + 1))
    return np.isin(lab, [i + 1 for i, s in enumerate(sz) if s >= 0.02 * sz.max()])


def corridor(prior1024, reach_px):
    """Pixels within reach_px (the sleeve's radius) of the forearm prior: the stub the assembly cuts at
    its bottom plane and whose width seam.sleeve_clearance checks after the assembly."""
    np = _np()
    from scipy import ndimage as ndi
    if prior1024 is None or not prior1024.any():
        return None
    return ndi.distance_transform_edt(~prior1024) <= reach_px


def band_gates(m, sil, view, px=BAND_PX, stub=None):
    """(inside, cover) of a redraw silhouette m against the guide's sil (1024 px); inside does not count
    the forearm stub's corridor (stub), where the redraw may draw the forearm at its natural width."""
    np = _np()
    from scipy import ndimage as ndi
    disk = np.hypot(*np.mgrid[-px:px + 1, -px:px + 1]) <= px
    allowed = ndi.binary_dilation(sil, disk) if stub is None else ndi.binary_dilation(sil, disk) | stub
    inside = float((m & allowed).sum() / max(m.sum(), 1))
    cover = float((sil & ndi.binary_dilation(m, disk)).sum() / max(sil.sum(), 1))
    P = pv()
    return [P.gate(f"part.redraw_inside.{view}", inside, f">= {INSIDE_MIN} within {px} px of the guide", inside >= INSIDE_MIN),
            P.gate(f"part.redraw_cover.{view}", cover, f">= {COVER_MIN} of the guide within {px} px", cover >= COVER_MIN)]


def colour_moved(redraw, guide, m, sil, cells=32, full=0.9):
    """part_views.colour_moved over the content only: the share of cells (cells x cells), each at least
    `full` inside both silhouettes, whose mean colour over the pixels in both moved more than dE 20. A
    thin part loses the cloth between its fingers, so a cell on a finger's edge mixes background into
    its mean and would count as a colour change; a ghost hand or a recoloured glove still moves the
    cells it covers."""
    np = _np()
    P = pv()
    both = m & sil
    h, w = both.shape
    k = h // cells
    B = both[:k * cells, :k * cells].reshape(cells, k, cells, k)
    cov = B.mean((1, 3))
    use = cov >= full
    if not use.any():
        return 1.0

    def means(img):
        a = img[:k * cells, :k * cells].astype(float).reshape(cells, k, cells, k, 3)
        wsum = B.sum((1, 3))[..., None]
        return (a * B[..., None]).sum((1, 3)) / np.maximum(wsum, 1)
    d = np.linalg.norm(P.srgb_lab(means(redraw)) - P.srgb_lab(means(guide)), axis=2)[use]
    return float((d > P.COLOUR_DE).mean())


def view_gates(redraw, guide1024, sil1024, factor, view, prior1024=None, stub=None):
    """The band, colour and sharpness gates of one redraw; the colour gate leaves out the forearm prior
    (a stand-in the redraw is asked to repaint), the inside gate its corridor (stub)."""
    np = _np()
    from scipy import ndimage as ndi
    P = pv()
    m = hand_silhouette(redraw)
    gates = band_gates(m, sil1024, view, stub=stub)
    own = sil1024 if prior1024 is None else sil1024 & ~ndi.binary_dilation(prior1024, iterations=4)
    moved = colour_moved(redraw, guide1024, m, own)
    gates.append(P.gate(f"part.redraw_colour.{view}", moved, f"<= {P.COLOUR_SHARE}", moved <= P.COLOUR_SHARE))
    both = m & sil1024
    lr, lg = P.lapvar(redraw, both), P.lapvar(guide1024, both)
    ratio = lr / max(lg, 1e-6)
    gates.append(P.gate(f"part.sharpness.{view}", ratio, f">= {factor}", ratio >= factor,
                        redraw_lapvar=round(lr, 2), guide_lapvar=round(lg, 2)))
    return gates, m


def clip_to_band(redraw, sil1024, px=CLIP_PX, stub=None):
    np = _np()
    from scipy import ndimage as ndi
    disk = np.hypot(*np.mgrid[-px:px + 1, -px:px + 1]) <= px
    keep = ndi.binary_dilation(sil1024, disk) if stub is None else ndi.binary_dilation(sil1024, disk) | stub
    out = redraw.copy()
    out[~keep] = 0
    return out


# ------------------------------------------------------------------------------------------- views
def views(a, plan, hands, qp, models, base):
    """part_views.py views for the hand parts; returns (exit code, gates, work) with work as
    part_views keeps it ({name: (part, folder, {view: (redraw, mask)}, guides)})."""
    np = _np()
    from PIL import Image
    P = pv()
    root = a.plan.parent
    clean = {v: (P.find_view(a.views, v, "black"), P.find_view(a.views, v, "mask")) for v in VIEWS}
    seeds = [int(s) for s in a.seeds.split(",")]
    all_gates, work = [], {}
    for part in hands:
        if "wrist" not in part or "hidden" not in part["views"]:
            raise P.Refused(f"part {part['name']}: no wrist or views.hidden: run part_math.py plan --tier fine")
        vd = root / "views" / part["name"]
        vd.mkdir(parents=True, exist_ok=True)
        hidden, src = part["views"]["hidden"]["view"], part["views"]["hidden"]["mirror_of"]
        crops, keeps = {}, {}
        for v in VIEWS:
            if v == hidden:
                continue
            rgb = np.asarray(Image.open(clean[v][0]).convert("RGB"))
            crops[v] = P.crop_box(rgb, part["views"]["boxes"][v])
            kp = root / (part["views"].get("keep") or {}).get(v, f"views/{part['name']}/keep_{v}.png")
            if not kp.is_file():
                raise P.Refused(f"keep mask missing: {kp} (part_math.py plan writes it)")
            keeps[v] = np.asarray(Image.open(kp).convert("L")) > 127
            if keeps[v].shape != crops[v].shape[:2]:
                raise P.Refused(f"{kp}: {keeps[v].shape} is not the box")
        cols = [c for c in (forearm_colour(plan, part, v, crops[v], keeps[v]) for v in ("front", src)) if c is not None]
        if not cols:
            raise P.Refused(f"part {part['name']}: no visible forearm pixels to take the skin colour from")
        colour = np.median(np.array(cols), axis=0)
        guides, res, priors, stubs = {}, {}, {}, {}
        for v in crops:
            g, sil, pr = build_guide(plan, part, v, crops[v], keeps[v], colour)
            g1024, s1024 = P.upscale(g), P.upscale(sil, mask=True)
            Image.fromarray(g1024).save(vd / f"guide_{v}.png")
            guides[v] = (g1024, s1024)
            priors[v] = P.upscale(pr, mask=True)
            stubs[v] = corridor(priors[v], float(part["wrist"]["r_sleeve"]) / float(plan["anchor"]["frame"]["units_per_px"])
                                * 1024.0 / float(part["views"]["box_side_px"]))
        for v in crops:
            g1024, s1024 = guides[v]
            best = None
            for seed in seeds:
                out = vd / f"redraw_{v}_s{seed}.png"
                P.wait_idle(base, a.wait_idle)
                t0 = time.time()
                try:
                    qp.paint(vd / f"guide_{v}.png", vd / f"guide_{v}.png", prompt_for(part, v), out, base, seed,
                             keep_loaded=True, models=models)
                except RuntimeError as e:
                    raise P.JobFailed(str(e))
                rd = np.asarray(Image.open(out).convert("RGB")).copy()
                if rd.shape[:2] != (1024, 1024):
                    rd = np.asarray(Image.fromarray(rd).resize((1024, 1024), Image.LANCZOS)).copy()
                gates, m = view_gates(rd, g1024, s1024, a.sharpness_factor, v, priors[v], stubs[v])
                passed = all(x["pass"] for x in gates)
                print(json.dumps({"part": part["name"], "view": v, "seed": seed, "seconds": round(time.time() - t0, 1),
                                  "gates": {x["name"]: x["value"] for x in gates}, "pass": passed}), flush=True)
                score = (passed, sum(x["value"] for x in gates[:2]))
                if best is None or score > best[0]:
                    best = (score, seed, rd, gates, m)
                if passed:
                    break
            _, seed, rd, gates, m = best
            for x in gates:
                x["seed"] = seed
            rd = clip_to_band(rd, s1024, stub=stubs[v])
            Image.fromarray(rd).save(vd / f"redraw_{v}.png")
            res[v] = (rd, hand_silhouette(rd))
            all_gates += gates
            if not best[0][0]:
                P.save_report(vd, P.report(all_gates, part=part["name"], failed_view=v,
                                           note=f"every seed {seeds} failed"))
                return 2, all_gates, work
        rd = res[src][0][:, ::-1].copy()
        Image.fromarray(rd).save(vd / f"redraw_{hidden}.png")
        Image.fromarray(guides[src][0][:, ::-1].copy()).save(vd / f"guide_{hidden}.png")
        res[hidden] = (rd, res[src][1][:, ::-1].copy())
        guides[hidden] = (guides[src][0][:, ::-1].copy(), guides[src][1][:, ::-1].copy())
        part["views"]["colours"] = {"skin": "#%02x%02x%02x" % tuple(int(round(x)) for x in colour)}
        work[part["name"]] = (part, vd, res, guides)
    return 0, all_gates, work


# ---------------------------------------------------------------------------------------- generate
def seed_sets(k):
    """--set arguments moving every Pixal3D sampler seed for attempt k (0 = the template's)."""
    return [] if k == 0 else [f"{n}.seed={s}" for n, s in zip(SAMPLERS, (56, 43, 42, 42))
                             for s in [s + SEED_STEP * k]]


def glb_triangles(path):
    """Triangles in a GLB (indexed triangle primitives, else vertex count / 3)."""
    sys.path.insert(0, str(HERE))
    from inspect_glb import parse_glb
    gltf, _ = parse_glb(Path(path))
    acc = gltf.get("accessors", [])
    n = 0
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if prim.get("mode", 4) != 4:
                continue
            idx = prim.get("indices")
            n += (acc[idx]["count"] if idx is not None else acc[prim["attributes"]["POSITION"]]["count"]) // 3
    return n


def hand_faces(plan_path, plan, ratio):
    """A hand's face target: ratio x the anchor's triangles (all reduction before the rig binds, and in
    the job itself: a collapse in Blender tears a textured mesh open along its UV seams)."""
    return max(2000, int(round(ratio * glb_triangles(Path(plan_path).parent / plan["anchor"]["glb"]))))


def gate_hand(plan_path, name, glb, out_json):
    if not HAND_PARTS.is_file():
        raise RuntimeError("blender-character-rig is not installed beside this skill (its hand_parts.py gates the hands)")
    r = subprocess.run([sys.executable, str(HAND_PARTS), "gate", str(plan_path), "--part", name, "--glb", str(glb),
                        "--json-out", str(out_json)], capture_output=True, text=True)
    return r.returncode, (r.stdout[-2000:] + r.stderr[-500:])


def generate_part(a, plan, part, i_last, base):
    """One hand: Pixal3D jobs until hand_parts.py gate passes (at most a.hand_seeds jobs); returns the
    exit code (0 pass, 2 every attempt failed a gate)."""
    P = pv()
    root = a.plan.parent
    name = part["name"]
    vd = root / (part["views"].get("dir") or f"views/{name}")
    vs = {v: vd / f"{v}.png" for v in VIEWS}
    missing = [str(p) for p in vs.values() if not p.is_file()]
    if missing:
        raise P.Refused(f"part {name}: run `views` first ({missing[0]} is missing)")
    gd = root / "gen" / name
    up, sets = [], []
    for v, p in vs.items():
        u = P.unique_copy(p, gd / "upload", f"{plan['character']}_{name}_{v}")
        up.append(u)
        sets.append(f"{P.MV_NODES[v]}.image={u.name}")
    if part["preset"] != P.TEMPLATE_PRESET:
        f, res, t = P.PRESETS[part["preset"]]
        sets += [f"241.resolution={res}", f"288.value={t}"]
    faces = hand_faces(a.plan, plan, getattr(a, "hand_ratio", HAND_RATIO))
    sets.append(f"186.target_face_count={faces}")      # the preset's grid and texture, the hand's budget
    attempts = []
    code = 2
    for k in range(max(1, a.hand_seeds)):
        out = gd / f"out_{k}"
        if out.exists():
            shutil.rmtree(out)
        P.wait_idle(base, a.wait_idle)
        t0 = time.time()
        r = P.run_client(P.MV_TEMPLATE, out, up, sets + seed_sets(k) + [f"322.filename_prefix=parts/{plan['character']}_{name}_{k}"],
                         a.server or base, keep_loaded=True, timeout=a.timeout)
        glbs = [Path(p) for p in r.get("outputs", []) if str(p).endswith(".glb")]
        if len(glbs) != 1:
            raise P.JobFailed(f"part {name}: expected one GLB, got {len(glbs)}")
        glb = gd / f"{name}_{k}.glb"
        shutil.copyfile(glbs[0], glb)
        rc, log = gate_hand(a.plan, name, glb, gd / f"gate_{k}.json")
        att = {"attempt": k, "glb": str(glb.relative_to(root)), "faces": faces, "seconds": round(time.time() - t0, 1),
               "server_seconds": r.get("elapsed_seconds"), "gate_exit": rc}
        try:
            rep = json.loads((gd / f"gate_{k}.json").read_text())
            att["failed"] = [g["name"] for g in rep["gates"] if not g["pass"]]
            att["gates"] = {g["name"]: g["value"] for g in rep["gates"]}
        except (OSError, ValueError, KeyError):
            att["log"] = log
        print(json.dumps({"part": name, **att}), flush=True)
        attempts.append(att)
        if rc == 0:
            shutil.copyfile(glb, gd / f"{name}.glb")
            part["generated"] = {"glb": f"gen/{name}/{name}.glb", "attempts": attempts}
            code = 0
            break
        if rc != 2:
            raise P.Refused(f"part {name}: hand_parts.py gate exit {rc}: {log[-300:]}")
    if code:
        part["generated"] = {**(part.get("generated") or {}), "attempts": attempts}
    return code


def paint_part(a, plan, part, base):
    """mesh-texture-paint on one generated part (hands: --kind object) into paint/<name>/."""
    P = pv()
    if not PAINT_LOOP.is_file():
        raise P.Refused("mesh-texture-paint is not installed beside this skill (paint_loop.py paints the parts)")
    root = a.plan.parent
    name = part["name"]
    glb = root / part["generated"]["glb"]
    vd = root / (part["views"].get("dir") or f"views/{name}")
    hand = part["region"] in SIDE
    cmd = [sys.executable, str(PAINT_LOOP), str(glb), "--concept", str(vd), "--sheet", str(vd / "sheet.png"),
           "--out", str(root / "paint" / name), "--kind", "object" if hand else "character",
           "--subject", f"{SIDE[part['region']]} hand and forearm" if hand else "character's head"]
    if hand:     # the hand job's own bake streaks the forearm grey and tints the palm olive; shown as context the
        cmd += ["--prior", ""]       # model continues them and redraws steep views: the nearest painted colour
    if a.server or base:
        cmd += ["--server", a.server or base]
    P.wait_idle(base, a.wait_idle)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise P.JobFailed(f"paint_loop exit {r.returncode} on {name}: {r.stderr[-400:]}")
    stem = glb.stem
    part["generated"]["painted"] = f"paint/{name}/{stem}_painted.glb"
    return 0


# ---------------------------------------------------------------------------------------- selftest
def _synthetic(tmp):
    """A plan with one hand part over a synthetic clean front view: a skin forearm leaving a teal sleeve,
    a palm and four fingers on a grey background stripe (cloth seen between the fingers)."""
    np = _np()
    from PIL import Image, ImageDraw
    upp = 0.001
    off = [512.0, 512.0]
    a = np.array([0.55, 0.83, 0.0])
    a /= np.linalg.norm(a)
    rim = np.array([-0.25, 0.10, 0.0])
    rf = 0.019
    wrist = {"tip": [-0.37, -0.08, 0.0], "axis": a.round(5).tolist(), "rim": rim.tolist(), "normal": a.round(5).tolist(),
             "bottom": (rim + a * 1.8 * rf).round(5).tolist(), "r_fore": rf, "r_sleeve": 0.038, "rim_threshold": 0.0285,
             "plane": "perpendicular", "tilt_deg": 0.0, "sectors": 16}
    px = lambda p: (off[0] + p[0] / upp, off[1] - p[1] / upp)
    im = Image.new("RGB", (1024, 1024))
    d = ImageDraw.Draw(im)
    d.rectangle([60, 640, 420, 700], fill=(110, 110, 110))                        # cloth behind the fingers
    d.line([px(rim + a * 0.12), px(rim)], fill=(40, 170, 190), width=76)            # sleeve
    hand = rim - a * 0.10
    d.line([px(rim), px(hand)], fill=(214, 160, 125), width=36)                    # forearm
    d.ellipse([px(hand)[0] - 40, px(hand)[1] - 40, px(hand)[0] + 40, px(hand)[1] + 40], fill=(230, 120, 40))
    tipdir = -a
    side = np.array([a[1], -a[0], 0.0])
    for k in range(4):
        s = hand + side * (-0.025 + 0.017 * k)
        d.line([px(s), px(s + tipdir * 0.07)], fill=(214, 160, 125), width=11)
    rgb = np.asarray(im)
    L = 200
    c = px(rim - a * 0.06)
    box = [int(c[0] - L / 2), int(c[1] - L / 2), int(c[0] - L / 2) + L, int(c[1] - L / 2) + L]
    keep_full = (np.abs(rgb.astype(int) - [40, 170, 190]).sum(2) > 30) & (rgb.max(2) > 0) & \
        (np.abs(rgb.astype(int) - [110, 110, 110]).sum(2) > 30)
    part = {"name": "hand_r", "source": "generate", "region": "hand.R", "preset": "Template",
            "prompt_hint": "a fingerless orange glove", "wrist": wrist, "seam": {"mode": "overlap"},
            "views": {"source": "clean-views", "box_side_px": L, "boxes": {v: box for v in VIEWS},
                      "hidden": {"view": "left", "mirror_of": "right"}}}
    plan = {"schema": "parts/1", "character": "courier", "tier": "fine",
            "anchor": {"frame": {"units_per_px": upp, "offset_px": {v: off for v in VIEWS}}}, "parts": [part]}
    return plan, part, rgb, keep_full, box


def selftest() -> int:
    np = _np()
    from scipy import ndimage as ndi
    P = pv()
    checks = {}
    with tempfile.TemporaryDirectory() as td:
        plan, part, rgb, keep_full, box = _synthetic(Path(td))
        crop = P.crop_box(rgb, box)
        keep = P.crop_box(keep_full, box)
        colour = forearm_colour(plan, part, "front", crop, keep)
        checks["forearm_colour_is_skin"] = colour is not None and np.abs(colour - [214, 160, 125]).max() < 12
        guide, sil, prior = build_guide(plan, part, "front", crop, keep, colour)
        checks["prior_fills_under_the_sleeve"] = prior.sum() > 200
        teal = np.abs(guide.astype(int) - [40, 170, 190]).sum(2) < 30
        checks["no_sleeve_in_guide"] = not teal.any()
        bottom_px = project(plan, part, "front", np.asarray(part["wrist"]["bottom"])[None])[0]
        pr = np.argwhere(prior)
        a2 = np.asarray(project(plan, part, "front", np.asarray(part["wrist"]["bottom"])[None] +
                                np.asarray(part["wrist"]["axis"])[None] * 0.01)[0]) - bottom_px
        a2 /= np.linalg.norm(a2)
        reach = (pr[:, ::-1] + 0.5 - bottom_px) @ a2
        checks["prior_ends_flat_at_the_bottom"] = reach.max() <= 2.5
        g1024, s1024 = P.upscale(guide), P.upscale(sil, mask=True)
        rng = np.random.default_rng(1)
        tex = rng.integers(-50, 50, size=(1024, 1024, 1))
        ideal = np.where(s1024[..., None], np.clip(g1024.astype(int) + tex, 25, 255), 0).astype(np.uint8)
        cloth = np.abs(g1024.astype(int) - [110, 110, 110]).sum(2) < 40
        ideal[cloth] = 0                         # the redraw drops the cloth between the fingers
        gates, _ = view_gates(ideal, g1024, s1024, 5.0, "front")
        checks["ideal_passes_band_gates"] = all(x["pass"] for x in gates)
        grown = ndi.binary_dilation(s1024, iterations=30) & ~s1024
        fat = ideal.copy()
        fat[grown] = (200, 150, 120)
        gates_f, _ = view_gates(fat, g1024, s1024, 5.0, "front")
        checks["a fattened redraw fails inside"] = not gates_f[0]["pass"]
        stub = corridor(P.upscale(prior, mask=True), 40)
        gates_s, _ = view_gates(fat, g1024, s1024, 5.0, "front", P.upscale(prior, mask=True), stub)
        checks["the stub corridor does not excuse a fat hand"] = not gates_s[0]["pass"]
        wide = ideal.copy()
        wide[stub & ~s1024] = (200, 150, 120)
        gates_w, _ = view_gates(wide, g1024, s1024, 5.0, "front", P.upscale(prior, mask=True), stub)
        checks["a forearm wider than the stub passes inside"] = gates_w[0]["pass"]
        half = ideal.copy()
        yy, xx = np.mgrid[0:1024, 0:1024]
        half[xx < 560] = 0
        gates_h, _ = view_gates(half, g1024, s1024, 5.0, "front")
        checks["a cut-off redraw fails cover"] = not gates_h[1]["pass"]
        recol = ideal.copy()
        orange = (np.abs(g1024.astype(int) - [230, 120, 40]).sum(2) < 60) & s1024
        recol[orange] = (120, 70, 40)
        gates_c, _ = view_gates(recol, g1024, s1024, 5.0, "front")
        checks["a recoloured glove fails colour"] = not gates_c[2]["pass"]
        clipped = clip_to_band(fat, s1024)
        disk = np.hypot(*np.mgrid[-CLIP_PX - 1:CLIP_PX + 2, -CLIP_PX - 1:CLIP_PX + 2]) <= CLIP_PX + 1
        checks["clip_to_band"] = not (clipped.max(2) > 0)[~ndi.binary_dilation(s1024, disk)].any() \
            and (clipped.max(2) > 0).sum() > (ideal.max(2) > 0).sum()
        m = hand_silhouette(ideal)
        lab, n = ndi.label(m)
        checks["finger gaps stay open"] = n >= 1 and not m[cloth & ~ndi.binary_dilation(~cloth, iterations=3)].any()
        p = prompt_for(part, "left")
        checks["prompt"] = "right hand" in p and "left side" in p and "orange glove" in p and "{" not in p
        sets = seed_sets(2)
        checks["seed_sets"] = seed_sets(0) == [] and len(sets) == 4 and all(s.split("=")[0].endswith(".seed") for s in sets) \
            and len({s.split("=")[1] for s in sets}) >= 2
        checks["hand_parts_beside"] = HAND_PARTS.is_file()
        import struct
        gl = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 0}],
              "accessors": [{"count": 30, "componentType": 5126, "type": "VEC3"}, {"count": 3000, "componentType": 5125, "type": "SCALAR"}],
              "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}]}
        js = json.dumps(gl).encode()
        js += b" " * (-len(js) % 4)
        blob = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js)) + struct.pack("<II", len(js), 0x4E4F534A) + js
        gp = Path(td) / "a.glb"
        gp.write_bytes(blob)
        checks["glb_triangles"] = glb_triangles(gp) == 1000
        rep = P.report(gates, part="hand_r")
        P.contract_out("hand_views__views.gate.json", rep)
    checks = {k: bool(v) for k, v in checks.items()}
    ok = all(checks.values())
    print(json.dumps({"checks": checks, "pass": ok}))
    return 0 if ok else 2


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["--selftest"], ["selftest"]):
        return selftest()
    print(__doc__.split("\n\n")[0] + "\nusage: hand_views.py --selftest  (the commands are part_views.py's)",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
