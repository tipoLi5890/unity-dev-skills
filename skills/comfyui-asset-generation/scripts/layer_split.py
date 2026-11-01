#!/usr/bin/env python3
"""layer_split.py — cut a front- or side-view 2D character into rig layers: the occlusion fills
(Qwen-Image-Edit-2511 on square-padded crops), a geometric part split, joints, meshes, weights
and the gates. Writes the layer PNGs, a psd_write.py manifest and rig2d.json (rig2d/1).

  layer_split.py fills CONCEPT.png --view front|side [--facing right|left] --out FILLS_DIR
                       [--seeds 1,2,3] [--hint TEXT] [--cubism] [--server URL]
                       [--props "pole=the long wooden pole;shield=the round shield"] [--only a,b]
  layer_split.py split KEYED.png --fills FILLS_DIR/fills.json --out OUT_DIR [--overlap 22]
                       [--psb NAME.psb]
  layer_split.py --selftest          offline: synthetic front and side figures, gates, template

The concept is drawn for cutting (codex-visual reference/layered-2d-source.md): front or side
view, limbs apart, eyes open, mouth closed, a held prop only with --props, a flat key background. KEYED.png is the
same picture keyed (codex-visual key_unmix.py).

`fills` (network, one job at a time, an empty queue first): templates/qwen_image_edit_2511_fill_api.json,
4 Lightning steps, picture 1 is also the latent so the layout is kept. Every edit starts from the
SOURCE (never an edit of an edit: a second-generation edit drifts). Inputs are padded to a square
with the painted key colour and scaled to 1024 (a non-square input drifts the geometry):
  noarms        the whole canvas, both arms removed, the body drawn closed under them
  bald          the head crop: hair removed, the scalp drawn
  eyes_closed   the head crop: eyes shut
  mouth_open    the head crop: mouth open
  face_blank    (--cubism) the head crop: hair, eyes, brows and mouth removed in ONE edit
  prop_<name>   (--props, first) the whole canvas: only that held prop, complete, in place
  noprop_<name> (--props) the whole canvas: that prop removed, the hand empty, what it covered
                drawn whole (one per prop: an edit asked to remove two removes one); noarms also
                removes them
Each result is keyed (key_unmix.py --edge tint) and placed back on the canvas. Gates per fill,
in the zone that must not change (noarms: the head and lower legs; bald, face_blank: the chin and
collar; eyes, mouth: the whole head): fill.aligned (75th percentile |RGB|) <= 12; fill.iou (the
silhouettes there) >= 0.95; fill.inside (head fills: outside the source silhouette grown 4 px)
<= 0.03; fill.changed (eyes_closed, mouth_open: share of the head changed by more than 40) >= 0.01;
prop_<name>: fill.inside <= 0.03 and fill.present >= 0.2 % of the canvas; noprop_<name>: fill.removed
(the prop's pixels changed) >= 0.7; noarms and noprop_<name> leave the props out of their keep zones. The head
box is found without the props. --only redoes the named fills and keeps the rest.
A failing fill retries the next seed. The armless fill may widen the clothes into the
gaps beside the arms: split clips it to the source. Writes FILLS_DIR/fills.json, the placed
fills, source_keyed.png and head_crop/*.png (1024 px crops for cubism_psd.py's eye split).

`split` (offline), cut by geometry, never by a body-part map:
  landmarks  from the armless fill's silhouette: neck = the narrowest row in the top 8-30 %,
             crotch = where the two legs merge, followed up from the shins,
             hem = the row where the most of the trunk's width changes colour at once, ankle =
             each leg's narrowest row near its bottom, knee = halfway hip to ankle.
  arms       below the armpit row (the first with three runs) each arm is an island of its
             own; the shoulder joint sits 27 % of the way from the neck to the crotch on the
             armless fill's edge (front) or where the two arms' axes meet (side); a capsule from
             it to the hand, with a round cap, takes the upper arm over the body, and sleeve left
             over beside it joins the arm. Over the body the capsule also takes what is drawn
             there (a strap, a buckle, a chest stripe): pixels unlike the free forearm's colours,
             or dark and wider than two outlines, are repainted from the sleeve around them, so
             they stay on the torso when the arm swings. The wrist is the narrowest
             cross-section at 50-80 %, the elbow halfway. Front: _R is the character's right
             (screen left), _L its left. Side: _near is the limb forward in the facing
             direction, _far the one behind; the far arm keeps what shows and is swept on under
             the torso to the shoulder.
  torso      the armless fill clipped to the source; where an arm hides the torso's side, a
             straight segment bridges the visible edge above and below; the shoulder is rounded
             and outlined in the source's outline colour where the new edge has none, so a raised
             arm shows a round, outlined shoulder, never a straight cut.
  head/hair  the bald fill is the head; the hair is what differs from it; eyes and mouth are the
             patches the eyes_closed and mouth_open fills changed, with the thin strokes joined
             to them (a mouth line's ends), as open/closed pairs for swaps. The torso is cut
             away from both: drawn over the head from the neck row, it would hide them.
  pivot      the head bone pivots at the bottom of the neck skin under the mouth (the chin when no
             neck shows); the chin and neck go to the head layer, cut from the torso.
  props      (fills with --props) the body is cut from the source with the props replaced by the
             noprop_<name> fills; each prop is the layer prop_<name>_<side> (visible pixels from the
             source, hidden ones from its own fill), rigid on the hand or forearm it touches most,
             at the depth where the stack recomposites the source best.
  overlap    each lower layer runs --overlap px under the one above at its joint.
  rig        bones in image pixels (y down), a Delaunay mesh per part that draws every pixel of
             its layer (a triangle the edge test drops is given back when it holds one),
             two-bone smoothstep weights across each joint; rig2d.json, manifest.json,
             debug.png, pose.png (rest and the arms raised 120 degrees: look at the shoulders).
Gates (split.gate.json, gate/1): split.composite_iou >= 0.99 and split.composite_px40 <= 0.005
(the layers against the source, outside what the sleeve fill repainted); split.sleeve_fill (the
share of an arm repainted) <= 0.25; split.mesh_cover (layer pixels no triangle draws: each
renders as background, a sliver along the edge) == 0; split.swap_visible (the share of what each
swap changes that still shows under the layers above it at rest; bangs may hide the eyes) >= 0.9;
split.alpha_clean (semi-transparent pixels 3 px or more inside
any layer) <= 0.01; split.joint_overlap >= 0.5 x --overlap px at every joint; split.names (the
view's full set, unique); split.limbs (two arms, two legs); split.shoulder_notch: where an arm
moves away, the body left behind has no notch (closing with a 12 px disc adds <= 0.1 % of the
silhouette) and its exposed edge is outlined (>= 0.7 of that edge as dark as the source outline);
split.head_pivot: the pivot >= 0.5 eye-to-mouth distances below the mouth and above the armpit, and
the torso draws <= 0.05 of the chin and neck skin; split.prop_layer (--props): each prop is a layer
on one bone, the body under it keeps <= 0.1 of its pixels in its colours and leaves <= 0.02 bare.

Exit codes: 0 done (gates passed); 1 usage error or a refused input; 2 a gate failed (outputs
are still written, to look at); 3 a server or job failure.
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
TEMPLATE = SKILL / "templates" / "qwen_image_edit_2511_fill_api.json"
TEMPLATE_ARGS = ("REPLACE_WITH_SQUARE_INPUT.png", "REPLACE_WITH_PROMPT")
KEY_UNMIX = SKILL.parent / "codex-visual" / "scripts" / "key_unmix.py"
EDIT_SIZE = 1024
FILL_CHANGED_MIN = 0.01   # share of the head an eyes_closed or mouth_open fill must change
SWAP_VISIBLE_MIN = 0.9    # share of what the open mouth changes that must show at rest
SLEEVE_FILL_MAX = 0.25    # a quarter of an arm repainted: the capsule took the body, not a sleeve

MODELS = {
    "unet": "qwen_image_edit_2511_int8_convrot.safetensors",
    "clip": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
    "vae": "qwen_image_vae.safetensors",
    "lora": "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
}

KEEP = ("Keep everything else exactly the same and in exactly the same place, pixel for pixel. "
        "Same drawing style, same outlines. Keep the flat background colour.")
KEEP_PROP = "Same drawing style, same outlines, same position, size and angle. Keep the flat background colour."
PROMPTS = {
    "noprops": "Picture 1 shows a 2D character holding {what}. Redraw the same image with {what} completely "
               "removed: the hands stay where they are as empty gripping hands, and the arms, body, clothing, "
               "legs and feet are drawn complete and closed where they were covered. Everything else stays. ",
    "prop": "Picture 1 shows a 2D character with {what}. Redraw the image showing ONLY {what}, whole and "
            "complete, its hidden parts drawn too, in exactly the same place, size and angle: it covers "
            "the same pixels as in Picture 1 plus its hidden part; do not enlarge it, centre it or turn it "
            "to face the viewer. The character and everything else are removed, leaving only the flat "
            "background colour. ",
    "noarms_front": "Picture 1 shows a 2D character from the front. Redraw the same image with both arms "
                    "completely removed, from the shoulders to the fingertips: draw the body and its clothing "
                    "complete and closed where the arms covered it, with rounded shoulders and the outline of "
                    "the body's sides. The head, hair, body, clothing, straps, legs and feet stay. ",
    "noarms_side": "Picture 1 shows a 2D character in side view. Redraw the same image with both arms "
                   "completely removed, the near arm and the far arm, from the shoulders to the fingertips: "
                   "draw the body and its clothing complete where the near arm covered it, with a rounded "
                   "shoulder and the outline of the chest and back. The head, hair, body, clothing, bag, legs "
                   "and feet stay. ",
    "bald": "Picture 1 is a close-up of a 2D character's head. Redraw it with all the hair removed: a smooth "
            "bald head, the bare skin of the forehead and scalp shown where the hair was, in the same skin "
            "tone, with the same outline. The face, eyes, eyebrows, nose, mouth, ears, neck and collar stay. ",
    "eyes_closed": "Picture 1 is a close-up of a 2D character's head. Redraw it with the eyes gently closed: "
                   "each eye becomes one curved dark eyelid line with its lashes, the lid skin in the same skin "
                   "tone. The hair, eyebrows, nose, mouth, ears and neck stay. ",
    "mouth_open": "Picture 1 is a close-up of a 2D character's head. Redraw it with the mouth open as if "
                  "saying 'ah' while talking: a small open mouth with a dark inside and a hint of teeth and "
                  "tongue. The hair, eyes, eyebrows, nose, ears and neck stay. ",
    "face_blank": "Picture 1 is a close-up of a 2D character's head. Redraw it with all the hair removed (a "
                  "smooth bald scalp in the skin tone, same outline) AND the eyes, eyebrows and mouth removed: "
                  "smooth blank skin where they were. Keep only the nose, the ears, the face outline, the neck "
                  "and the collar. ",
}


class Refused(Exception):
    pass


class JobFailed(Exception):
    pass


def graph(image: str, prompt: str, seed=1, prefix="layer_split/fill", models=MODELS) -> dict:
    """Qwen-Image-Edit-2511 + Lightning, one picture that is also the latent (layout kept)."""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": models["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": models["lora"], "strength_model": 1.0}},
        "3": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["2", 0], "shift": 3.1}},
        "4": {"class_type": "CFGNorm", "inputs": {"model": ["3", 0], "strength": 1.0}},
        "5": {"class_type": "CLIPLoader", "inputs": {"clip_name": models["clip"], "type": "qwen_image", "device": "default"}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": models["vae"]}},
        "7": {"class_type": "LoadImage", "inputs": {"image": image}},
        "9": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["5", 0], "prompt": prompt, "vae": ["6", 0], "image1": ["7", 0]}},
        "10": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["5", 0], "prompt": "", "vae": ["6", 0], "image1": ["7", 0]}},
        "11": {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {"conditioning": ["9", 0], "reference_latents_method": "index_timestep_zero"}},
        "12": {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {"conditioning": ["10", 0], "reference_latents_method": "index_timestep_zero"}},
        "13": {"class_type": "VAEEncode", "inputs": {"pixels": ["7", 0], "vae": ["6", 0]}},
        "14": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler",
                                                    "scheduler": "simple", "positive": ["11", 0], "negative": ["12", 0],
                                                    "latent_image": ["13", 0], "denoise": 1.0}},
        "15": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["6", 0]}},
        "16": {"class_type": "SaveImage", "inputs": {"images": ["15", 0], "filename_prefix": prefix}},
    }


# ------------------------------------------------------------------------------------- arrays
def _np():
    import numpy as np
    return np


def _ndi():
    from scipy import ndimage as ndi
    return ndi


def load(p):
    np = _np()
    from PIL import Image
    return np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)


def save(a, p):
    np = _np()
    from PIL import Image
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(p)


def resize_rgba(a, w, h):
    """Premultiplied resize, so a keyed edge does not pick up the colour under alpha 0."""
    np = _np()
    from PIL import Image
    al = a[..., 3:4] / 255
    pm = np.concatenate([a[..., :3] * al, a[..., 3:4]], -1)
    chans = [np.asarray(Image.fromarray(pm[..., c].astype(np.float32), "F").resize((w, h), Image.LANCZOS))
             for c in range(4)]
    out = np.stack(chans, -1).clip(0, 255)
    al2 = out[..., 3:4] / 255
    out[..., :3] = np.where(al2 > 1e-3, out[..., :3] / np.maximum(al2, 1e-3), 0)
    return out.clip(0, 255)


def runs(row):
    np = _np()
    d = np.diff(np.r_[0, row.astype(np.int8), 0])
    return list(zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]))


def disk(r):
    np = _np()
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    return x * x + y * y <= r * r


def largest(m, keep_frac=0.0):
    np, ndi = _np(), _ndi()
    lab, n = ndi.label(m)
    if n <= 1:
        return m
    sz = ndi.sum(m, lab, range(1, n + 1))
    if keep_frac <= 0:
        return lab == (int(np.argmax(sz)) + 1)
    return np.isin(lab, [i + 1 for i, v in enumerate(sz) if v >= keep_frac * sz.max()])


def smooth(m, r=2):
    ndi = _ndi()
    m = ndi.binary_opening(m, structure=disk(r))
    return ndi.binary_closing(m, structure=disk(r))


def luma(rgb):
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


# --------------------------------------------------------------------------------- landmarks
def landmarks(A, T, view):
    """Rows and centres from the source silhouette A and the armless silhouette T."""
    np = _np()
    H, W = A.shape
    rows = np.nonzero(A.any(1))[0]
    if len(rows) < 50:
        raise Refused("the source silhouette is empty or tiny; is KEYED.png keyed?")
    y_top, y_bot = int(rows[0]), int(rows[-1])
    h = y_bot - y_top
    width = T.sum(1).astype(float)
    lo, hi = y_top + int(0.08 * h), y_top + int(0.30 * h)
    band = [y for y in range(lo, hi) if width[y] > 0]
    if not band:
        raise Refused("no neck row: the armless fill has no pixels below the head")
    y_neck = int(min(band, key=lambda y: width[y]))
    nr = [(s, e) for s, e in runs(T[y_neck]) if e - s > 2]
    x_mid = float(np.mean([(s + e) / 2 for s, e in nr])) if nr else float(np.nonzero(T[y_neck])[0].mean())
    neck_w = float(max((e - s for s, e in nr), default=width[y_neck]))
    minrun = max(3, int(0.01 * W))
    # the crotch: follow the two legs up from the shins until their runs merge (runs that are not
    # the legs, such as what the armless fill left beside the arms, are never followed)
    y = y_bot - int(0.15 * h)
    legs = sorted([r for r in runs(T[y]) if r[1] - r[0] >= minrun], key=lambda r: r[0] - r[1])[:2]
    y_crotch = None
    if len(legs) == 2:
        while y > y_neck:
            y -= 1
            rr = [r for r in runs(T[y]) if r[1] - r[0] >= 2]
            nxt = []
            for a, b in legs:
                hit = [r for r in rr if r[0] < b and r[1] > a]
                if not hit:
                    break
                nxt.append(max(hit, key=lambda r: r[1] - r[0]))
            if len(nxt) < 2:
                break
            if nxt[0] == nxt[1]:
                y_crotch = y + 1
                break
            legs = nxt
    if y_crotch is None:
        raise Refused("no crotch row: the legs never separate in the armless fill (draw the legs apart)")
    return {"y_top": y_top, "y_bot": y_bot, "h": h, "y_neck": y_neck, "x_mid": x_mid,
            "neck_w": neck_w, "y_crotch": int(y_crotch)}


def hem_row(B, T, y0, y1):
    """The row where the largest share of the trunk's width changes colour at once."""
    np = _np()
    best, by = 0.0, None
    rgb = B[..., :3]
    for y in range(max(y0, 4), y1):
        m = T[y - 3] & T[y + 3]
        if m.sum() < 10:
            continue
        d = np.abs(rgb[y + 3] - rgb[y - 3]).max(-1)
        frac = float(((d > 40) & m).sum() / m.sum())
        if frac > best:
            best, by = frac, y
    return by, best


# -------------------------------------------------------------------------------------- split
SHOULDER = 0.27        # the shoulder joint's row, as a share of neck -> crotch


def find_arms(A, S, T, L, view, facing, ov):
    """Each arm: below the armpit row (the first with three runs) it is an island of its own,
    which gives the hand's tip and the width. The shoulder joint sits SHOULDER of the way from the
    neck to the crotch on the armless fill's edge (front view), or where the two arms' axes meet
    (side view). A capsule from the joint to the tip, with a round cap, takes the upper arm over
    the body; finish_arms() gives the arm whatever sleeve is left over beside it."""
    np, ndi = _np(), _ndi()
    H, W = A.shape
    yy, xx = np.mgrid[:H, :W]
    minrun = max(3, int(0.006 * W))
    y_pit = None
    for y in range(L["y_neck"] + 4, L["y_crotch"]):
        if all(len([r for r in runs(A[y_]) if r[1] - r[0] >= minrun]) >= 3 for y_ in range(y, min(y + 6, H))):
            y_pit = y
            break
    xm = int(round(L["x_mid"]))
    comps = []
    if y_pit is not None:
        lab, n = ndi.label(A & (yy >= y_pit))
        for k in range(1, n + 1):
            m = lab == k
            if m[y_pit:L["y_crotch"], max(xm - 2, 0):xm + 3].any():
                continue                                      # the trunk (and the legs below it)
            if m.sum() >= max(150, 0.002 * A.sum()):
                comps.append(m)
        comps = sorted(comps, key=lambda m: -m.sum())[:2]
    level = not comps
    if level:
        # no arm island below an armpit row: an arm held out level (a prop held in front) never
        # leaves a gap below it. Its core is what stands clear of the armless fill instead.
        out_ = A & ~ndi.binary_dilation(T, iterations=3) & (yy > L["y_neck"]) & (yy < L["y_crotch"])
        lab, n = ndi.label(ndi.binary_opening(out_, iterations=2))
        comps = [lab == k for k in range(1, n + 1)]
        comps = sorted([m for m in comps if m.sum() >= max(150, 0.002 * A.sum())], key=lambda m: -m.sum())[:2]
        if not comps:
            raise Refused("no armpit row and no arm clear of the armless fill: draw the arms clear of the body")
        y_pit = int(min(np.nonzero(m.any(1))[0].min() for m in comps))
    L["y_armpit"] = y_pit
    y_sh = L["y_neck"] + SHOULDER * (L["y_crotch"] - L["y_neck"])
    row = int(round(y_sh))
    trs = runs(T[row]) or [(xm - 1, xm + 1)]
    tr = min(trs, key=lambda r: 0 if r[0] <= xm < r[1] else min(abs(r[0] - xm), abs(r[1] - xm)))
    PP = np.dstack([xx, yy]).astype(np.float64)
    axes = []
    for core in comps:
        cy, cx_ = np.nonzero(core)
        pts = np.c_[cx_, cy].astype(np.float64)
        c = pts.mean(0)
        _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
        axes.append((c, vt[0] if vt[0][1] > 0 else -vt[0]))
    meet = None
    if view == "side" and len(axes) == 2:                     # side: the two arms' axes meet at the
        (c1, u1), (c2, u2) = axes                             # shoulder (an inverted V from there)
        try:
            t = np.linalg.solve(np.array([u1, -u2]).T, c2 - c1)
            P = c1 + t[0] * u1
            if L["y_neck"] - 0.05 * L["h"] < P[1] < y_pit:
                meet = P
        except np.linalg.LinAlgError:
            meet = None
    arms = []
    for core, (c, ua) in zip(comps, axes):
        edt = ndi.distance_transform_edt(core)
        cy, cx_ = np.nonzero(core)
        sgn = 1 if cx_.mean() > L["x_mid"] else -1
        w = 2 * float(np.percentile(edt[core], 97))
        if level:                                           # the arm's axis where it meets the trunk
            P0 = np.array([(tr[0] + tr[1]) / 2, y_sh])
            J = c + float((P0 - c) @ ua) * ua
        elif view == "front":
            J = np.array([(tr[1] - 1 if sgn > 0 else tr[0]) - sgn * 0.5 * w, y_sh])
        elif meet is not None:
            J = meet + 0.3 * w * ua
        else:
            J = c + ((y_sh - c[1]) / ua[1]) * ua if abs(ua[1]) > 1e-3 else np.array([(tr[0] + tr[1]) / 2, y_sh])
        d = np.hypot(cx_ - J[0], cy - J[1])
        Tip = np.array([cx_[np.argmax(d)], cy[np.argmax(d)]], float)
        u = (Tip - J) / max(np.linalg.norm(Tip - J), 1e-6)
        nrm = np.array([-u[1], u[0]])
        tt, ss = (PP - J) @ u, (PP - J) @ nrm
        t1 = float(np.linalg.norm(Tip - J))
        cap = (tt < 0) & (np.hypot(xx - J[0], yy - J[1]) > 0.62 * w)
        capsule = (np.abs(ss) <= 0.5 * w + 3) & (tt >= -0.62 * w) & (tt <= t1 + 2) & ~cap
        mask = ((A & capsule & (yy > L["y_neck"])) | core)
        mask = largest(ndi.binary_closing(mask, structure=disk(2)) & A)
        tm, sm = tt[mask], ss[mask]
        best, tW = 1e9, 0.65 * t1
        for a_ in np.linspace(0.5 * t1, 0.8 * t1, 16):     # the wrist: the narrowest cross-section
            sel = np.abs(tm - a_) < max(2.0, 0.02 * t1)
            if sel.sum() > 5:
                wv = float(np.percentile(sm[sel], 97) - np.percentile(sm[sel], 3))
                if wv < best:
                    best, tW = wv, float(a_)
        Wr = J + tW * u
        arms.append({"J": J, "E": (J + Wr) / 2, "W": Wr, "Tip": Tip, "u": u, "w": w, "tW": tW, "level": level,
                     "tt": tt, "ss": ss, "full": mask, "core": core})
    sides = {}
    if view == "front":
        for g in arms:
            sides["R" if g["Tip"][0] < L["x_mid"] else "L"] = g
    else:
        fwd = 1 if facing == "right" else -1
        for name, g in zip(("near", "far"), sorted(arms, key=lambda g: -fwd * (g["Tip"][0] - L["x_mid"]))):
            sides[name] = g
    return sides


def finish_arms(geo, A, S, torso, taken, view, ov):
    """Leftover sleeve beside an arm joins it; a far arm (side view) keeps only what shows and is
    swept on under the torso to the shoulder, so a swing never opens a gap. Returns the arm and
    hand masks and the picture each arm layer takes its pixels from."""
    np, ndi = _np(), _ndi()
    left = A & ~torso & ~taken
    for g in geo.values():
        left &= ~g["full"]
    lab, n = ndi.label(left)
    rest = np.zeros_like(A)
    for k in range(1, n + 1):
        m = lab == k
        ring = ndi.binary_dilation(m, iterations=2)
        best = max(geo.values(), key=lambda g: (ring & g["full"]).sum(), default=None)
        if best is not None and (ring & best["full"]).any():
            # sleeve beside the arm joins it; beside an arm held out level, a sliver behind the
            # shoulder cap or off to the side (a hood's edge above it) stays on the body
            tt, ss = best["tt"][m], best["ss"][m]
            if not best.get("level") or (float(np.median(tt)) >= -0.62 * best["w"] and
                                         float(np.median(np.abs(ss))) <= 0.75 * best["w"]):
                best["full"] = best["full"] | m
            else:
                rest |= m
    for name, g in geo.items():
        img = S.copy()
        if view == "side" and name == "far":
            hidden = g["full"] & torso
            shown = g["full"] & ~torso
            if shown.any() and hidden.any():
                t_b = float(np.percentile(g["tt"][shown], 1)) + 3
                ys, xs = np.nonzero(hidden)
                dt = np.maximum(t_b - g["tt"][ys, xs], 0)
                qx = np.clip(np.round(xs + dt * g["u"][0]), 0, A.shape[1] - 1).astype(int)
                qy = np.clip(np.round(ys + dt * g["u"][1]), 0, A.shape[0] - 1).astype(int)
                img[ys, xs] = S[qy, qx]
        if not (view == "side" and name == "far"):
            g["occluders"] = sleeve_fill(img, g, A)
        g["img"] = img
        g["arm"] = g["full"] & (g["tt"] <= g["tW"] + 2)
        g["hand"] = g["full"] & (g["tt"] > g["tW"] - ov)
    return rest


def sleeve_fill(img, g, A):
    """Where the upper arm lies over the body, the capsule also takes what is drawn there: a
    strap, a buckle, a chest stripe, drawstrings. Those belong to the body and would swing with
    the arm. Pixels unlike the sleeve (its colours, measured on the free forearm) or dark and
    thick (a strap, not a 1-3 px outline) are repainted in place from the sleeve around them.
    Returns the repainted mask; the torso layer keeps what was there."""
    np, ndi = _np(), _ndi()
    sleeve = g["core"] & (g["tt"] <= g["tW"])          # the forearm clear of the body
    if sleeve.sum() < 200:
        sleeve = g["core"]                              # a short forearm: the hand's colours join in
    over = g["full"] & ~ndi.binary_dilation(g["core"], iterations=2) & (g["tt"] <= g["tW"])
    if sleeve.sum() < 200 or not over.any():
        return np.zeros_like(A)
    rgb = img[..., :3]
    # the sleeve's colours: 16 levels a channel, a bin counts when 0.05 % of the forearm is in it
    q = lambda c: (np.clip(c, 0, 255) // 16).astype(int)
    hist = np.zeros((16, 16, 16), np.int64)
    qs = q(rgb[sleeve])
    np.add.at(hist, (qs[:, 0], qs[:, 1], qs[:, 2]), 1)
    known_bins = ndi.binary_dilation(hist >= max(3, 0.0005 * sleeve.sum()), iterations=1)
    qo = q(rgb)
    unlike = over & ~known_bins[qo[..., 0], qo[..., 1], qo[..., 2]]
    lum = luma(rgb)
    dark_lim, _, width = outline_style(img, A)
    # dark and wider than two outlines side by side (an arm's edge on the body's edge): a strap
    thick = ndi.binary_opening((lum < dark_lim) & over, structure=disk(width + 1))
    occ = (unlike | thick) & over
    occ = ndi.binary_opening(occ, iterations=1)
    lab_, n = ndi.label(occ)
    if n:
        sizes = ndi.sum(occ, lab_, range(1, n + 1))
        occ = np.isin(lab_, 1 + np.nonzero(sizes >= 30)[0])
    # a band of the sleeve's own (an armband) stays on the arm: a piece that spans the arm's whole
    # width and does not continue onto the body beside it, with what it encloses (its badge). A
    # strap spans the arm and continues; a drawstring ends on the arm but does not span it.
    occ &= ~own_pattern(occ, rgb, A & ~g["full"], g["ss"], g["w"])
    dark = (lum < dark_lim) & over                      # an occluder's own outline goes with it
    occ |= dark & ndi.binary_dilation(occ, iterations=4)
    occ = ndi.binary_dilation(occ, iterations=2) & over
    if not occ.any():
        return occ
    known = g["full"] & ~occ & (g["tt"] <= g["tW"]) & (lum >= dark_lim)   # sleeve, not its outline
    todo = occ.copy()
    for sig in (2, 4, 8, 16, 32, 64):                   # normalised convolution, finest scale first
        w = ndi.gaussian_filter(known.astype(np.float32), sig)
        ok = todo & (w > 1e-3)
        if ok.any():
            for c in range(3):
                v = ndi.gaussian_filter(np.where(known, rgb[..., c], 0).astype(np.float32), sig)
                img[..., c][ok] = (v / np.maximum(w, 1e-6))[ok]
            todo &= ~ok
        if not todo.any():
            break
    return occ


CROSS_MIN = 0.2           # share of the body just beside an occluder that must share its colour
SLEEVE_OWN_MAX = 0.05     # share of an arm's repainted pixels that were the sleeve's own pattern


def own_pattern(occ, rgb, body, ss, w, r=8):
    """The pieces of occ that are the sleeve's own band: each colour of a piece (light and dark
    apart) that spans >= 0.75 of the arm's width w across the arm (ss) and does not continue onto
    `body` (< CROSS_MIN of the body pixels within r px share its median colour, within 45), plus
    whatever such a band encloses."""
    np, ndi = _np(), _ndi()
    own = np.zeros_like(occ)
    lum = luma(rgb)
    gap = max(2, int(0.2 * w))            # a band's ends just past the capsule are still sleeve
    body = body & ~ndi.binary_dilation(~body & ndi.binary_dilation(occ, iterations=gap + r), iterations=gap)
    for part in (occ & (lum < 70), occ & (lum >= 70)):
        lab, n = ndi.label(part)
        for k in range(1, n + 1):
            c = lab == k
            if c.sum() < 30 or float(np.ptp(ss[c])) < 0.75 * w:
                continue
            ring = ndi.binary_dilation(c, iterations=r + gap) & body
            med = np.median(rgb[c], 0)
            if ring.sum() >= 10 and float((np.abs(rgb[ring] - med).max(-1) < 45).mean()) >= CROSS_MIN:
                continue                                  # it runs on over the body: a strap
            own |= c
    if own.any():
        own = ndi.binary_fill_holes(ndi.binary_dilation(own, iterations=3)) & occ
        lab, n = ndi.label(occ)                           # a badge inside the band goes with it
        inside = ndi.binary_fill_holes(ndi.binary_closing(own, iterations=6))
        for k in range(1, n + 1):
            c = lab == k
            if (c & ~inside).sum() < 0.1 * c.sum():
                own |= c
    return own


def sleeve_own(layers, S, A, sides, geo=None):
    """split.sleeve_own: of the arm pixels repainted away from the source (> 40), the share that is
    the sleeve's own band (own_pattern: spans the arm, does not continue onto the body)."""
    np, ndi = _np(), _ndi()
    tot, own, per = 0, 0, {}
    for k in sides:
        a = layers.get(f"arm_{k}")
        if a is None or k == "far":                    # a far arm's hidden part is swept on purpose
            continue
        on = a[..., 3] > 127
        rep = on & (np.abs(a[..., :3] - S[..., :3]).max(-1) > 40) & A
        rep = ndi.binary_opening(rep, iterations=1)
        if not rep.any():
            continue
        g = (geo or {}).get(k)
        if g is None:
            continue
        own_m = own_pattern(rep, S[..., :3], A & ~ndi.binary_dilation(on, iterations=1), g["ss"], g["w"])
        n_own = int(own_m.sum())
        tot += int(rep.sum())
        own += n_own
        per[f"arm_{k}"] = {"repainted": int(rep.sum()), "own": n_own}
    v = own / max(tot, 1)
    return gate("split.sleeve_own", round(v, 4), SLEEVE_OWN_MAX, v <= SLEEVE_OWN_MAX, per_arm=per)


def split(src_path: Path, fills_path: Path, out: Path, overlap=22, far_arm="shown") -> dict:
    np, ndi = _np(), _ndi()
    fills = json.loads(fills_path.read_text(encoding="utf-8"))
    fd = fills_path.parent
    view, facing = fills["view"], fills.get("facing", "front")
    S = load(src_path)
    H, W = S.shape[:2]
    if [W, H] != fills["canvas"]:
        raise Refused(f"KEYED.png is {W}x{H}; the fills were made for {fills['canvas']}")
    props = list(fills.get("props") or [])
    need = ["noarms", "bald", "eyes_closed", "mouth_open"] + [f"{k}_{p}" for p in props for k in ("prop", "noprop")]
    for k in need:
        if k not in fills["fills"]:
            raise Refused(f"fills.json has no {k!r} fill")
    F = {k: load(fd / v["png"]) for k, v in fills["fills"].items()}
    S0 = S
    A0 = A = S[..., 3] > 127
    P = {}
    if props:                         # held props: the body is cut from the picture with them removed
        ok_iso = {p: fills["fills"][f"prop_{p}"].get("pass", True) is not False for p in props}
        ok_np = {p: fills["fills"][f"noprop_{p}"].get("pass", True) is not False for p in props}
        S, P = body_without_props(S0, A0, {p: F[f"noprop_{p}"] if ok_np[p] else None for p in props},
                                  {p: F[f"prop_{p}"] if ok_iso[p] else None for p in props})
        A = S[..., 3] > 127
    PA = np.zeros_like(A0)
    for v in P.values():
        PA |= v["vis"]
    PA = ndi.binary_dilation(PA, iterations=3) if PA.any() else PA
    Tfill = F["noarms"]
    T = smooth((Tfill[..., 3] > 127) & ndi.binary_dilation(A, iterations=1), 2)
    T = largest(T)                    # the fill may widen into the gaps beside the arms: clipped
    L = landmarks(A, T, view)
    ov = int(overlap)
    yy, xx = np.mgrid[:H, :W]
    sd = ("R", "L") if view == "front" else ("near", "far")
    geo = find_arms(A, S, T, L, view, facing, ov)
    hidden = {}
    if far_arm == "hidden" and view == "side" and "near" in geo and "far" not in geo:
        # chosen by a person: the far arm is wholly behind the body (or a shield). It gets bones,
        # hanging from the near arm's shoulder a little forward, and no layers.
        g = geo["near"]
        fwd = 1 if facing == "right" else -1
        ln = float(np.linalg.norm(g["W"] - g["J"]))
        u = np.array([0.26 * fwd, 0.966])
        hidden["far"] = {"J": g["J"].copy(), "E": g["J"] + 0.5 * ln * u, "W": g["J"] + ln * u,
                         "Tip": g["J"] + 1.3 * ln * u, "hand": np.zeros_like(A), "arm": np.zeros_like(A)}
    allarms = np.zeros_like(A)
    for g in geo.values():
        allarms |= g["full"]
    # the body picture: the source, and the armless fill wherever an arm covered the body
    B = S.copy()
    under = T & np.any([g["full"] for k, g in geo.items() if k != "far"] or [np.zeros_like(A)], axis=0)
    B[under] = Tfill[under]
    y_lo = L["y_neck"] + int(0.55 * (L["y_crotch"] - L["y_neck"]))
    y_hem, hem_frac = hem_row(B, T, y_lo, L["y_crotch"] - 4)
    if y_hem is None or hem_frac < 0.5:
        y_hem = int(L["y_crotch"] - 0.2 * (L["y_crotch"] - L["y_neck"]))
    L["y_hem"], L["hem_edge"] = int(y_hem), round(hem_frac, 3)
    h = L["h"]
    bones, parts, joints = [], {}, {}

    def bone(name, parent, head, tail):
        bones.append({"name": name, "parent": parent or "", "hx": float(head[0]), "hy": float(head[1]),
                      "tx": float(tail[0]), "ty": float(tail[1])})

    x_mid, y_neck, y_top, y_crotch = L["x_mid"], L["y_neck"], L["y_top"], L["y_crotch"]
    y_hip = (y_hem + y_crotch) / 2
    y_mid = (y_neck + y_hem) / 2
    trunk_x = lambda y: float(np.mean(np.nonzero(T[int(y)])[0])) if T[int(y)].any() else x_mid
    bone("hips", None, (trunk_x(y_hip), y_hip), (trunk_x(y_mid), y_mid))
    bone("chest", "hips", (trunk_x(y_mid), y_mid), (x_mid, y_neck + 8))
    bone("head", "chest", (x_mid, y_neck + 8), (x_mid, y_top))
    y_eye = y_top + 0.62 * (y_neck - y_top)
    bone("face", "head", (x_mid, y_eye), (x_mid, y_eye - 0.2 * (y_neck - y_top)))
    bone("hair", "head", (x_mid, y_top + 0.35 * (y_neck - y_top)), (x_mid, y_top))
    for k, g in geo.items():
        bone(f"upperarm_{k}", "chest", g["J"], g["E"])
        bone(f"forearm_{k}", f"upperarm_{k}", g["E"], g["W"])
        bone(f"hand_{k}", f"forearm_{k}", g["W"], g["Tip"])
        joints[f"shoulder_{k}"], joints[f"elbow_{k}"], joints[f"wrist_{k}"] = g["J"], g["E"], g["W"]
    for k, g in hidden.items():
        bone(f"upperarm_{k}", "chest", g["J"], g["E"])
        bone(f"forearm_{k}", f"upperarm_{k}", g["E"], g["W"])
        bone(f"hand_{k}", f"forearm_{k}", g["W"], g["Tip"])
    torso, torso_img = shape_torso(S, A, T, B, geo, allarms, L, yy, xx)
    parts["torso"] = {"mask": torso, "img": torso_img, "bones": ["hips", "chest"], "bw": 0.04 * h}
    rest = finish_arms(geo, A, S, torso, ~((yy > y_neck) & (yy <= y_hem)), view, ov)
    parts["torso"]["mask"] = parts["torso"]["mask"] | rest
    for k, g in geo.items():
        parts[f"arm_{k}"] = {"mask": g["arm"], "img": g["img"], "bones": [f"upperarm_{k}", f"forearm_{k}"], "bw": 0.35 * g["w"]}
        parts[f"hand_{k}"] = {"mask": g["hand"], "img": g["img"], "bones": [f"forearm_{k}", f"hand_{k}"], "bw": 0.6 * ov}
    lower = T & (yy > y_crotch - ov)
    lab, n = ndi.label(T & (yy > y_crotch))
    comps = sorted([(lab == i + 1) for i in range(n)], key=lambda m: -m.sum())[:2]
    legs = {}
    if len(comps) == 2:
        cx = [float(np.nonzero(m)[1].mean()) for m in comps]
        if view == "front":
            keys = ["R", "L"] if cx[0] < cx[1] else ["L", "R"]
        else:
            fwd = 1 if facing == "right" else -1
            keys = ["near", "far"] if fwd * cx[0] > fwd * cx[1] else ["far", "near"]
        rr = sorted(runs(T[y_crotch + 2]), key=lambda r: -(r[1] - r[0]))[:2]
        rr.sort()
        x_split = (rr[0][1] + rr[1][0]) / 2 if len(rr) == 2 else (cx[0] + cx[1]) / 2
        for k, m, x in zip(keys, comps, cx):
            sel = (xx < x_split) if x == min(cx) else (xx >= x_split)
            legm = (m | (lower & sel & (yy <= y_crotch))) & T
            ly = np.nonzero(legm.any(1))[0]
            y_b = int(ly.max())
            ll = y_b - y_crotch
            ws = {y: int(legm[y].sum()) for y in range(int(y_b - 0.22 * ll), int(y_b - 0.03 * ll))}
            y_ank = min(ws, key=lambda y: ws[y]) if ws else int(y_b - 0.1 * ll)
            lx = lambda y, m_=legm: float(np.nonzero(m_[int(y)])[0].mean()) if m_[int(y)].any() else x_split
            hipj = (lx(y_crotch + 4), y_hip)
            aj = (lx(y_ank), y_ank)
            ky = (y_crotch + y_ank) / 2
            kj = (lx(ky), ky)
            foot = legm & (yy >= y_ank - 4)
            fy, fx = np.nonzero(foot)
            if view == "front":
                toe = (float(fx.mean()), float(fy.max()))
            else:
                toe = (float(fx.max() if facing == "right" else fx.min()), float(fy.mean()))
            legs[k] = legm
            bone(f"thigh_{k}", "hips", hipj, kj)
            bone(f"shin_{k}", f"thigh_{k}", kj, aj)
            bone(f"foot_{k}", f"shin_{k}", aj, toe)
            joints[f"hip_{k}"], joints[f"knee_{k}"], joints[f"ankle_{k}"] = hipj, kj, aj
            parts[f"leg_{k}"] = {"mask": legm & (yy < y_ank + ov) & (yy > y_crotch - ov), "img": B,
                                 "bones": [f"thigh_{k}", f"shin_{k}"], "bw": 0.026 * h}
            parts[f"foot_{k}"] = {"mask": foot, "img": B, "bones": [f"shin_{k}", f"foot_{k}"], "bw": 0.008 * h}
    legmask = np.zeros_like(A)
    for k in legs:
        legmask |= parts[f"leg_{k}"]["mask"] & (yy > y_crotch + 6)
    parts["pelvis"] = {"mask": T & (yy > y_hem - ov) & (yy <= y_crotch + 6) & ~legmask, "img": B, "bones": ["hips"]}
    # head, hair, face
    HB = F["bald"]
    hbA = HB[..., 3] > 127
    head = hbA & (yy < y_neck + ov) & ((yy < y_neck) | (np.abs(xx - x_mid) < 0.5 * L["neck_w"] + 4))
    diff = np.abs(S[..., :3] - HB[..., :3]).max(-1)
    hair = A & (yy < y_neck) & (~hbA | (diff > 45)) & ~PA
    hair = ndi.binary_opening(hair, iterations=1)
    hair = largest(hair, keep_frac=0.02)
    hair = ndi.binary_closing(hair, iterations=2) & A
    parts["head"] = {"mask": head, "img": HB, "bones": ["head"]}
    parts["hair_front"] = {"mask": hair, "img": S, "bones": ["head", "hair"], "bw": 0.033 * h, "flip": True}

    def patch(variant, y0, y1):
        d2 = np.abs(variant[..., :3] - S[..., :3]).max(-1)
        m0 = (d2 > 40) & (yy > y0) & (yy < y1) & A & ~hair & (variant[..., 3] > 127) & ~PA
        m = ndi.binary_opening(m0, iterations=1)
        m = largest(m, keep_frac=0.15) if m.any() else m
        if m.any():                           # thin strokes joined to it (a mouth line's ends) belong too
            lab, _ = ndi.label(m0 | m, structure=np.ones((3, 3)))
            m |= np.isin(lab, np.unique(lab[m]))
        m = ndi.binary_dilation(m, iterations=6)
        return ndi.binary_fill_holes(m) & A & ~hair & (variant[..., 3] > 127)

    hh = y_neck - y_top                        # eyes in the face's middle band, the mouth below them
    em = patch(F["eyes_closed"], y_top + 0.35 * hh, y_top + 0.85 * hh)
    eb = int(np.nonzero(em.any(1))[0].max()) if em.any() else int(y_top + 0.7 * hh)
    mm = patch(F["mouth_open"], eb + 0.02 * hh, y_neck + 0.05 * hh) & ~em
    parts["eyes_open"] = {"mask": em, "img": S, "bones": ["face"]}
    parts["eyes_closed"] = {"mask": em, "img": F["eyes_closed"], "bones": ["face"], "hidden": True}
    parts["mouth_closed"] = {"mask": mm, "img": S, "bones": ["face"]}
    parts["mouth_open"] = {"mask": mm, "img": F["mouth_open"], "bones": ["face"], "hidden": True}
    # the torso is drawn over the head (a collar or hood over the neck) and starts at the neck
    # row, which on a hooded figure can sit as high as the mouth: it must never cover a face swap
    parts["torso"]["mask"] = parts["torso"]["mask"] & ~ndi.binary_dilation(em | mm, iterations=2)
    # the head pivots at the bottom of the neck, not at the cut row: the chin and neck go to the
    # head layer, which runs --overlap px under the collar below the pivot
    dark_lim, _, o_w = outline_style(S, A)
    piv = neck_pivot(S, A, em, mm, L, dark_lim, o_w)
    if piv is not None and piv["y"] > y_neck + 8:
        reg = piv["region"]
        col = (yy >= piv["y"]) & (yy < piv["y"] + ov) & (xx >= piv["x0"] - 4) & (xx <= piv["x1"] + 4) & A
        # a margin round the chin runs under the torso, so a turned head never opens the cut
        margin = ndi.binary_dilation(reg, iterations=max(2, ov // 2)) & A & (yy >= y_neck)
        parts["head"]["mask"] = (head & (yy < y_neck)) | reg | col | margin | \
            (head & (yy >= y_neck) & ~parts["torso"]["mask"])
        himg = HB.copy()
        himg[yy[:, 0] >= y_neck] = S[yy[:, 0] >= y_neck]
        parts["head"]["img"] = himg
        parts["torso"]["mask"] = parts["torso"]["mask"] & ~reg
        bm = {b["name"]: b for b in bones}
        bm["chest"]["tx"], bm["chest"]["ty"] = piv["x"], float(piv["y"])
        bm["head"]["hx"], bm["head"]["hy"] = piv["x"], float(piv["y"])
    if piv is not None:
        L["y_neck_pivot"], L["y_mouth"], L["y_eye"] = int(piv["y"]) if piv["y"] > y_neck + 8 else y_neck + 8, \
            round(piv["y_mouth"], 1), round(piv["y_eye"], 1)
    face = ["hair_front", "eyes_open", "eyes_closed", "mouth_closed", "mouth_open", "head"]
    if view == "front":
        order = ["hand_R", "arm_R", "hand_L", "arm_L", "torso"] + face + ["pelvis", "foot_R", "leg_R", "foot_L", "leg_L"]
    else:
        order = ["hand_near", "arm_near", "torso"] + face + ["pelvis", "foot_near", "leg_near", "foot_far", "leg_far",
                                                            "hand_far", "arm_far"]
    out.mkdir(parents=True, exist_ok=True)
    if P:
        order = place_props(P, parts, order, geo, S0, A0, view, hidden, fills.get("prop_sides") or {})
    layers = {}
    bidx = {b["name"]: i for i, b in enumerate(bones)}
    rig_parts, manifest_layers = [], []
    for name in order:
        if name not in parts:
            continue
        p = parts[name]
        m = p["mask"]
        if m.any() and not name.startswith("prop_"):      # a held prop may show in pieces
            m = largest(m, keep_frac=0.6 if name.startswith(("eyes", "mouth")) else 0.05)
        a = np.zeros((H, W, 4), np.float32)
        a[m] = p["img"][m]
        layers[name] = a
        save(a, out / f"{name}.png")
        manifest_layers.append({"name": name, "png": f"{name}.png", "hidden": bool(p.get("hidden", False))})
        rig_parts.append(mesh_for(name, a[..., 3] > 8, p, bones, bidx))
    present = [n for n in order if n in layers]
    # ---- gates ----
    gates = []
    shown = [n for n in present if not parts[n].get("hidden")]
    comp = over([layers[n] for n in reversed(shown)])
    cA = comp[..., 3] > 127
    iou = float((cA & A0).sum() / max((cA | A0).sum(), 1))
    both = cA | A0
    d = np.abs(comp[..., :3] * (comp[..., 3:4] / 255) - S0[..., :3] * (S0[..., 3:4] / 255)).max(-1)
    # what sleeve_fill repainted on purpose is measured by its own gate, not as a split error
    painted = np.zeros_like(A)
    share = {}
    for k, g in geo.items():
        occ = g.get("occluders")
        if occ is not None and occ.any() and f"arm_{k}" in layers:
            on = layers[f"arm_{k}"][..., 3] > 8
            painted |= occ & on
            share[f"arm_{k}"] = round(float((occ & on).sum() / max(on.sum(), 1)), 4)
    px40 = float(((d > 40) & both & ~painted).sum() / max(both.sum(), 1))
    gates.append(gate("split.composite_iou", round(iou, 4), 0.99, iou >= 0.99))
    gates.append(gate("split.composite_px40", round(px40, 4), 0.005, px40 <= 0.005,
                      repainted_px=int(painted.sum())))
    worst_fill = max(share.values(), default=0.0)
    gates.append(gate("split.sleeve_fill", worst_fill, SLEEVE_FILL_MAX, worst_fill <= SLEEVE_FILL_MAX, per_arm=share))
    worst, per = 0.0, {}
    for n, a in layers.items():
        al = a[..., 3]
        core = ndi.binary_erosion(al > 8, iterations=3)
        v = float(((al > 8) & (al < 247) & core).sum() / max(core.sum(), 1))
        per[n] = round(v, 4)
        worst = max(worst, v)
    gates.append(gate("split.alpha_clean", round(worst, 4), 0.01, worst <= 0.01, per_layer=per))
    uncovered = {}                             # layer pixels no triangle of the mesh draws
    for rp in rig_parts:
        al = layers[rp["name"]][..., 3] > 8
        v = np.array(rp["verts"], np.float64).reshape(-1, 2)
        t = np.array(rp["indices"], int).reshape(-1, 3)
        n_un = int((al & ~tri_cover(v, t, al.shape)).sum()) if len(t) else int(al.sum())
        if n_un:
            uncovered[rp["name"]] = n_un
    n_unc = sum(uncovered.values())
    gates.append(gate("split.mesh_cover", n_unc, 0, n_unc == 0, per_layer=uncovered))
    jo = joint_overlaps(layers, joints, bones, view, sd, ov, L)
    jmin = min(jo.values()) if jo else 0.0
    gates.append(gate("split.joint_overlap", round(jmin, 1), 0.5 * ov, bool(jo) and jmin >= 0.5 * ov, per_joint=jo))
    # a held prop is in order only when the fills name it; a hidden far arm has no layers
    expect = [n for n in order if not (hidden and n in (f"arm_{k}" for k in hidden) or n in (f"hand_{k}" for k in hidden))]
    missing = [n for n in expect if n not in layers or not (layers[n][..., 3] > 8).any()]
    gates.append(gate("split.names", len(present) - len(missing), len(expect),
                      not missing and len(set(present)) == len(present), missing=missing))
    gates.append(gate("split.limbs", len(geo) + len(hidden) + len(legs), 4,
                      len(geo) + len(hidden) == 2 and len(legs) == 2, arms=sorted(geo), legs=sorted(legs),
                      hidden=sorted(hidden)))
    sv = swap_visible(layers, present, parts)
    gates.append(gate("split.swap_visible", sv["worst"], SWAP_VISIBLE_MIN, sv["worst"] >= SWAP_VISIBLE_MIN, **sv))
    notch = shoulder_notch(layers, S, A, geo, L)
    gates.append(gate("split.shoulder_notch", notch["notch_share"], 0.001,
                      notch["notch_share"] <= 0.001 and notch["outlined"] >= 0.7, **notch))
    if P:
        gates.append(prop_gate(layers, present, parts, P, S0))
    gates.append(sleeve_own(layers, S, A, sd, geo))
    head_hy = next(b["hy"] for b in bones if b["name"] == "head")
    gates.append(head_pivot_gate(layers, head_hy, piv, L.get("y_armpit", L["y_crotch"])))
    ok = all(g["pass"] for g in gates)
    W_, H_ = W, H
    rig = {"schema": "rig2d/1", "tool": "layer_split", "view": view, "facing": facing, "width": W_, "height": H_,
           "y_down": True, "sides": list(sd), "layers": present, "bones": bones, "parts": rig_parts,
           "swaps": [{"category": "eyes", "labels": ["open", "closed"], "layers": ["eyes_open", "eyes_closed"]},
                     {"category": "mouth", "labels": ["closed", "open"], "layers": ["mouth_closed", "mouth_open"]}],
           "joints": [{"name": k, "x": float(v[0]), "y": float(v[1])} for k, v in joints.items()],
           "landmarks": {k: (float(v) if not isinstance(v, int) else v) for k, v in L.items() if v is not None}}
    (out / "rig2d.json").write_text(json.dumps(rig), encoding="utf-8")
    man = {"width": W_, "height": H_, "ids": "ids.json", "layers": manifest_layers}
    (out / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    rep = {"schema": "gate/1", "tool": "layer_split", "pass": ok, "gates": gates, "view": view}
    (out / "split.gate.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    debug(S, parts, present, bones, out / "debug.png")
    pose_preview(layers, present, geo, out / "pose.png",
                 prop_side={n: parts[n]["side"] for n in present if n.startswith("prop_")})
    return rep


PROP_BAKED_MAX = 0.1      # share of a held prop's pixels a body layer may still draw in the prop's colours
PROP_HOLE_MAX = 0.02      # share of a held prop's pixels left with nothing behind them once it moves


def body_without_props(S, A, NPs, isos):
    """The body picture: the source with each held prop replaced by its own removal fill
    noprop_<name> (the hand as an empty grip, the body behind drawn whole). An edit asked to remove
    two props removes one, so each has its own, made from the source. A prop's visible pixels are
    where the source differs from its removal fill near its own fill (the prop alone, complete);
    its hidden pixels are where that fill lies inside the silhouette behind the body."""
    np, ndi = _np(), _ndi()
    out, P, taken = S.copy(), {}, np.zeros_like(A)
    # props with a removal fill first, then those inpainted (from the picture with the others
    # already removed, so a pole across a shield is not filled with shield); within each, props
    # with a fill of their own first. One without (its fill failed its gates) takes what its
    # removal fill changed that no other prop explains, and shows only its visible part.
    for name, iso in sorted(isos.items(), key=lambda kv: (NPs[kv[0]] is None, kv[1] is None)):
        NP = NPs[name]
        region = None
        if NP is None:                    # its removal fill failed (re-posed the arm): a thin prop's
            if iso is None:               # track is inpainted from round it instead
                raise Refused(f"prop {name!r}: neither its own fill nor its removal fill passed")
            im = ndi.binary_opening(iso[..., 3] > 127, iterations=2)
            im = largest(im, keep_frac=0.05) if im.any() else im
            like = np.abs(S[..., :3] - iso[..., :3]).max(-1) < 40      # the fingers over it stay
            vis = ndi.binary_closing(im & A & like, iterations=1) & im & A & ~taken
            thick = 2 * float(ndi.distance_transform_edt(vis).max()) if vis.any() else 0.0
            if thick > PROP_INPAINT_MAX:
                raise Refused(f"prop {name!r}: its removal fill failed and it is {thick:.0f} px thick, "
                              f"too wide to inpaint (<= {PROP_INPAINT_MAX}); redo noprop_{name}")
            region = ndi.binary_dilation(im, iterations=3) & ~taken    # its soft edge goes too
            NP = inpaint_track(out, region)
            NPs[name] = NP
        npA = NP[..., 3] > 127
        diff = (np.abs(S[..., :3] - NP[..., :3]).max(-1) > 40) | ~npA
        diff = ndi.binary_closing(ndi.binary_opening(diff & A, iterations=1), iterations=2) & A
        if iso is None:
            vis = diff & ~taken
            if vis.any():                 # the prop, split by what crosses it; not the edit's crumbs
                main = largest(vis)
                lab, n = ndi.label(vis)
                near = ndi.binary_dilation(main, iterations=40)
                sz = ndi.sum(vis, lab, range(1, n + 1))
                vis = np.isin(lab, [k + 1 for k in range(n) if sz[k] >= 0.02 * main.sum() and (near & (lab == k + 1)).any()])
            full = vis.copy()
            iso = np.zeros(S.shape, np.float32)
        else:
            im = ndi.binary_opening(iso[..., 3] > 127, iterations=2)
            if im.any():
                im = largest(im, keep_frac=0.05)
            vis = diff & ndi.binary_dilation(im, iterations=4) & ~taken
            lab, n = ndi.label(vis)                          # crumbs the edit changed elsewhere stay body
            if n:
                sz = ndi.sum(vis, lab, range(1, n + 1))
                vis = np.isin(lab, 1 + np.nonzero(sz >= 50)[0])
            full = im & (A | vis)
        taken |= vis
        region = vis if region is None else (region | vis)
        out[region] = NP[region]
        out[region & ~npA, 3] = 0
        P[name] = {"vis": vis, "iso": iso, "full": full, "np": NP}
    return out, P


PROP_INPAINT_MAX = 40     # px: a prop this thin can be inpainted when its removal fill fails


def inpaint_track(S, todo):
    """The picture with the pixels in `todo` filled from round them by normalised convolution,
    finest scale first, on premultiplied RGBA, so a pole across a gap between the legs leaves
    background there and one across a jacket leaves jacket."""
    np, ndi = _np(), _ndi()
    out = S.copy()
    al = S[..., 3:4] / 255
    pm = np.concatenate([S[..., :3] * al, S[..., 3:4]], -1)
    known = ~todo
    left = todo.copy()
    for sig in (2, 4, 8, 16, 32):
        w = ndi.gaussian_filter(known.astype(np.float32), sig)
        ok = left & (w > 1e-3)
        if ok.any():
            for c in range(4):
                v = ndi.gaussian_filter(np.where(known, pm[..., c], 0).astype(np.float32), sig)
                pm[..., c][ok] = (v / np.maximum(w, 1e-6))[ok]
            left &= ~ok
        if not left.any():
            break
    a = pm[..., 3]
    out[..., 3] = np.where(todo, np.where(a > 127, 255, 0), S[..., 3])
    rgb = pm[..., :3] / np.maximum(a[..., None] / 255, 1e-3)
    out[..., :3] = np.where(todo[..., None], np.clip(rgb, 0, 255), S[..., :3])
    return out


def place_props(P, parts, order, geo, S0, A0, view, hidden_arms=None, sides=None):
    """Each held prop becomes the layer prop_<name>_<side>: its visible pixels from the source, its hidden
    ones (inside the silhouette, behind the body) from its own fill, bound rigidly to the hand or
    forearm it touches most. It goes at the depth where the layers recomposite the source best."""
    np, ndi = _np(), _ndi()
    order = list(order)
    for name, v in P.items():
        vis, full = v["vis"], v["full"]
        hidden = full & ~vis & A0
        img = S0.copy()
        img[hidden] = v["iso"][hidden]
        img[..., 3] = np.where(vis | hidden, 255, 0)
        mask = vis | hidden
        near = ndi.binary_dilation(vis, iterations=6)
        best, side, bone = -1, None, None
        want = (sides or {}).get(name)
        for k, g in geo.items():
            if want and k != want:
                continue
            for b, m in ((f"hand_{k}", g.get("hand")), (f"forearm_{k}", g.get("arm"))):
                if m is None:
                    continue
                o = int((near & m).sum())
                if o > best:
                    best, side, bone = o, k, b
        if want and want in (hidden_arms or {}):       # held by the hidden arm a person named
            side, bone = want, f"forearm_{want}"
        elif best <= 0 and hidden_arms:                # touching no arm that shows: the hidden one
            side = next(iter(hidden_arms))
            bone = f"forearm_{side}"
        elif best <= 0 and want in geo:
            side, bone = want, f"hand_{want}"
        elif best <= 0:                                # touching nothing: the nearest wrist
            ys, xs = np.nonzero(vis)
            k = min(geo, key=lambda k: np.min(np.hypot(xs - geo[k]["W"][0], ys - geo[k]["W"][1])))
            side, bone = k, f"hand_{k}"
        lay = v["layer"] = f"prop_{name}_{side}"
        parts[lay] = {"mask": mask, "img": img, "bones": [bone], "side": side}
        # the depth: try it above each layer and keep the one that recomposites the source best
        ys, xs = np.nonzero(ndi.binary_dilation(mask, iterations=8))
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        crop = lambda a: a[y0:y1, x0:x1]

        def stack_err(ordr):
            ls_ = []
            for n in reversed(ordr):
                p = parts.get(n)
                if p is None or p.get("hidden"):
                    continue
                a = np.zeros(crop(S0).shape, np.float32)
                m = crop(p["mask"])
                a[m] = crop(p["img"])[m]
                ls_.append(a)
            c = over(ls_)
            dd = np.abs(c[..., :3] * (c[..., 3:4] / 255) - crop(S0)[..., :3] * (crop(S0)[..., 3:4] / 255)).max(-1)
            return int(((dd > 40) & ((c[..., 3] > 127) | crop(A0))).sum())
        cands = []
        for i in range(len(order) + 1):
            o2 = order[:i] + [lay] + order[i:]
            cands.append((stack_err(o2), i, o2))
        err = min(c[0] for c in cands)
        # among the best (within 0.5 % of the prop), the one nearest its hand in the stack
        # (a hidden arm is the bottom of a side view's stack)
        hand_i = order.index(f"hand_{side}") if f"hand_{side}" in order else \
            (len(order) if side in (hidden_arms or {}) else 0)
        ok = [c for c in cands if c[0] <= err + 0.005 * mask.sum()]
        order = min(ok, key=lambda c: abs(c[1] - hand_i))[2]
    return order


def prop_gate(layers, present, parts, P, S0):
    """split.prop_layer: each held prop is a layer of its own bound to one arm bone, the body
    layers under it do not still draw it (<= PROP_BAKED_MAX of its pixels within 30 of the
    source there) and leave no hole behind it where its removal fill shows body (<= PROP_HOLE_MAX)."""
    np = _np()
    body = [n for n in present if not parts[n].get("hidden") and not n.startswith("prop_")]
    comp = over([layers[n] for n in reversed(body)])
    per, ok = {}, True
    for name, v in P.items():
        lay = v.get("layer", f"prop_{name}")
        vis = v["vis"]
        n = max(int(vis.sum()), 1)
        same = (np.abs(comp[..., :3] - S0[..., :3]).max(-1) < 30) & (comp[..., 3] > 127) & vis
        hole = vis & (v["np"][..., 3] > 127) & (comp[..., 3] <= 127)
        baked, holes = float(same.sum() / n), float(hole.sum() / n)
        has = lay in layers and bool((layers[lay][..., 3] > 8).any())
        bones = parts[lay]["bones"] if has and lay in parts else []
        per[lay] = {"layer": has, "baked": round(baked, 4), "holes": round(holes, 4), "bones": bones,
                    "px": int(vis.sum())}
        ok &= has and baked <= PROP_BAKED_MAX and holes <= PROP_HOLE_MAX and len(bones) == 1
    worst = max((x.get("baked", 1.0) for x in per.values()), default=1.0)
    return gate("split.prop_layer", round(worst, 4), PROP_BAKED_MAX, ok, per_prop=per, hole_max=PROP_HOLE_MAX)


HEAD_PIVOT_MIN = 0.5      # the head pivot sits this many eye-to-mouth distances below the mouth
CHIN_ON_TORSO_MAX = 0.05  # share of the chin and neck skin the torso layer may still draw


def face_skin(S, A, em, mm, dark_lim, width):
    """The face's skin and the outlines inside it: a pixel near the colour of the skin round the
    closed mouth (its chroma, and 0.55..1.2 of its luma, so the shaded tone counts), connected to
    the mouth. A jaw line between face and neck is bridged; hair and clothing are not skin."""
    np, ndi = _np(), _ndi()
    rgb = S[..., :3]
    lum = luma(rgb)
    ref_m = mm & (lum >= dark_lim)
    if ref_m.sum() < 20:
        return None, None
    ref = np.median(rgb[ref_m], 0)
    ref_l = float(luma(ref[None])[0])
    tot = np.maximum(rgb.sum(-1), 1)
    rt = ref.sum() + 1e-6
    c1, c2 = (rgb[..., 0] - rgb[..., 1]) / tot, (rgb[..., 1] - rgb[..., 2]) / tot
    r1, r2 = (ref[0] - ref[1]) / rt, (ref[1] - ref[2]) / rt
    skin = A & (np.abs(c1 - r1) < 0.11) & (np.abs(c2 - r2) < 0.08) & (lum > 0.55 * ref_l) & (lum < 1.2 * ref_l + 20)
    skin = ndi.binary_opening(skin, iterations=1)
    bridge = A & (lum < dark_lim) & ndi.binary_dilation(skin, iterations=width + 2)
    lab, n = ndi.label(skin | bridge | em | mm)
    seeds = np.unique(lab[mm & (lab > 0)])
    comp = np.isin(lab, seeds[seeds > 0]) & skin
    return comp, ref


def neck_pivot(S, A, em, mm, L, dark_lim, width):
    """The head's pivot: the bottom of the neck skin below the mouth (the last skin row before the
    collar), at most 1.2 eye-to-mouth distances below the mouth; the chin when no neck shows. The
    narrowest-row cut can sit at mouth height on a hooded figure (the hood flares under the chin),
    which pivots the head about its mouth and leaves the chin on the torso layer."""
    np, ndi = _np(), _ndi()
    if not em.any() or not mm.any():
        return None
    my = np.nonzero(mm.any(1))[0]
    ey = np.nonzero(em.any(1))[0]
    y_m, y_e = float(my.mean()), float(ey.mean())
    d = max(y_m - y_e, 4.0)
    comp, ref = face_skin(S, A, em, mm, dark_lim, width)
    if comp is None:
        return None
    y_lim = int(min(my.max() + 1.2 * d, L.get("y_armpit", L["y_crotch"]) - 4))
    rows = [y for y in range(int(my.max()), y_lim + 1) if comp[y].sum() >= 3]
    y_piv = int(rows[-1]) if rows else int(my.max())
    yy = np.arange(A.shape[0])[:, None]
    # the chin and the neck down to the pivot, with the outlines round them
    low = comp & (yy > y_m) & (yy <= y_piv)
    reg = ndi.binary_fill_holes(ndi.binary_dilation(low, iterations=width + 1)) & A & (yy > y_m) & (yy <= y_piv)
    xs = np.nonzero(low[max(y_piv - 3, 0):y_piv + 1].any(0))[0]
    if not len(xs):
        xs = np.nonzero(comp[int(y_m):y_piv + 1].any(0))[0]
    if not len(xs):
        return None
    return {"y": y_piv, "x": float((xs.min() + xs.max()) / 2), "x0": int(xs.min()), "x1": int(xs.max()),
            "y_mouth": y_m, "y_eye": y_e, "d": d, "region": reg, "skin": comp & (yy > y_m) & (yy <= y_piv)}


def head_pivot_gate(layers, head_hy, piv, y_armpit):
    """split.head_pivot: the head bone's pivot is >= HEAD_PIVOT_MIN eye-to-mouth distances below
    the mouth and above the armpit, and the torso layer draws <= CHIN_ON_TORSO_MAX of the chin and
    neck skin (a chin on the torso stays put when the head turns)."""
    if piv is None:
        return gate("split.head_pivot", None, HEAD_PIVOT_MIN, True, skipped="no face skin below the mouth")
    v = (head_hy - piv["y_mouth"]) / piv["d"]
    t = layers.get("torso")
    sk = piv["skin"]
    share = float((sk & (t[..., 3] > 127)).sum() / max(sk.sum(), 1)) if t is not None and sk.any() else 0.0
    return gate("split.head_pivot", round(float(v), 3), HEAD_PIVOT_MIN,
                v >= HEAD_PIVOT_MIN and share <= CHIN_ON_TORSO_MAX and head_hy < y_armpit,
                pivot_y=round(float(head_hy), 1), neck_bottom_y=int(piv["y"]), mouth_y=round(piv["y_mouth"], 1),
                eye_mouth_px=round(piv["d"], 1), chin_on_torso=round(share, 4), chin_on_torso_max=CHIN_ON_TORSO_MAX)


def outline_style(S, A):
    """The source outline: its luminance limit, colour and width in px."""
    np, ndi = _np(), _ndi()
    lum = luma(S[..., :3])
    ring = A & ~ndi.binary_erosion(A, iterations=3)
    dark = float(np.percentile(lum[ring], 20)) + 45 if ring.any() else 90.0
    near = A & ~ndi.binary_erosion(A, iterations=8)
    dr = near & (lum < dark)
    perim = max(int((A & ~ndi.binary_erosion(A)).sum()), 1)
    width = int(np.clip(round(dr.sum() / perim), 2, 6))
    colour = np.median(S[..., :3][dr], 0) if dr.any() else np.array([20.0, 20, 25])
    return dark, colour, width


def shape_torso(S, A, T, B, geo, allarms, L, yy, xx):
    """The torso layer: the armless fill clipped to the source silhouette; where an arm hid the
    torso's side, that side is bounded by the line of its visible edge below, the shoulder is
    rounded, and an outline is drawn where the new edge has none, so a raised arm never leaves a
    straight, unoutlined cut."""
    np, ndi = _np(), _ndi()
    y_neck, y_hem = L["y_neck"], L["y_hem"]
    sil = T & ndi.binary_dilation(A, iterations=1) & (yy >= y_neck) & (yy <= y_hem)
    visible = A & ~allarms
    y_pit = L.get("y_armpit") or y_neck
    for y in range(int(y_pit), int(y_hem) + 1):                # below the armpit the torso is one run
        rr = runs(sil[y])
        if len(rr) > 1:
            keep = min(rr, key=lambda r: 0 if r[0] <= L["x_mid"] < r[1] else min(abs(r[0] - L["x_mid"]), abs(r[1] - L["x_mid"])))
            sil[y, :keep[0]] = False
            sil[y, keep[1]:] = False
    R = np.zeros_like(A)
    for g in geo.values():
        sgn = 1 if g["Tip"][0] > L["x_mid"] else -1          # the torso edge this arm hides
        R |= ndi.binary_dilation(g["full"], iterations=max(3, int(0.5 * g["w"])))
        edge, vis = {}, {}
        for y in range(int(y_neck), int(y_hem)):
            rr = [r for r in runs(sil[y]) if r[0] <= L["x_mid"] < r[1]] or runs(sil[y])
            if not rr:
                continue
            xe = rr[0][1] - 1 if sgn > 0 else rr[0][0]
            xo = int(np.clip(xe + sgn * 3, 0, A.shape[1] - 1))
            xi = int(np.clip(xe - sgn * 2, 0, A.shape[1] - 1))
            edge[y], vis[y] = xe, (not A[y, xo]) and bool(visible[y, xi])
        # the rows where the arm hides this edge: bridge them with the straight segment from the
        # last visible edge point above to the first one below, and cut what lies beyond it
        ys = sorted(edge)
        arm_rows = np.nonzero(g["full"].any(1))[0]
        if not len(arm_rows):
            continue
        a0, a1 = int(arm_rows.min()), int(arm_rows.max())
        best = None
        i = 0
        while i < len(ys):
            if vis[ys[i]] or ys[i] < a0 or ys[i] > a1:
                i += 1
                continue
            j = i
            while j + 1 < len(ys) and not vis[ys[j + 1]]:
                j += 1
            if best is None or ys[j] - ys[i] > best[1] - best[0]:
                best = (ys[i], ys[j])
            i = j + 1
        if best is None:
            continue
        above = [y for y in ys if y < best[0] and vis[y]]
        below = [y for y in ys if y > best[1] and vis[y]]
        if not below:
            continue
        y1 = below[0]
        y0 = above[-1] if above else max(int(g["J"][1] - 0.62 * g["w"]), int(y_neck))
        x0 = edge.get(y0, edge[min(edge, key=lambda y: abs(y - y0))])
        x1 = edge[y1]
        line = x0 + (x1 - x0) * (yy - y0) / max(y1 - y0, 1)
        cut = (yy > y0) & (yy < y1) & (sgn * (xx - line) > 1)
        sil &= ~cut
    r = max(3, int(0.25 * np.median([g["w"] for g in geo.values()]))) if geo else 3
    opened = ndi.binary_opening(sil, structure=disk(r))
    sil = (sil & ~R) | (opened & R)
    sil = largest(sil)
    img = B.copy()
    dark, colour, width = outline_style(S, A)
    ring = sil & ~ndi.binary_erosion(sil, iterations=width) & allarms & ~ndi.binary_dilation(visible & ~T, iterations=1)
    ring &= luma(img[..., :3]) >= dark
    ring &= ~(A & ~allarms & ~ndi.binary_erosion(A, iterations=width + 1))  # the source's own edge stays
    img[ring, :3] = colour
    img[ring, 3] = 255
    return sil, img


def gate(name, value, limit, ok, **extra):
    return {"name": name, "value": value, "limit": limit, "pass": bool(ok), **extra}


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


def joint_overlaps(layers, joints, bones, view, sd, ov, L):
    """Depth (px along the bone) of the overlap between the two layers that meet at each joint."""
    np = _np()
    pairs = []
    for k in sd:
        pairs += [(f"shoulder_{k}", f"arm_{k}", "torso"), (f"wrist_{k}", f"hand_{k}", f"arm_{k}"),
                  (f"hip_{k}", f"leg_{k}", "pelvis"), (f"ankle_{k}", f"foot_{k}", f"leg_{k}")]
    out = {}
    for j, a, b in pairs:
        if j not in joints or a not in layers or b not in layers:
            continue
        both = (layers[a][..., 3] > 8) & (layers[b][..., 3] > 8)
        ys, xs = np.nonzero(both)
        if not len(ys):
            out[j] = 0.0
            continue
        J = np.array(joints[j], float)
        r = np.hypot(xs - J[0], ys - J[1])
        near = r < 3 * ov + 40
        if near.sum() < 5:
            out[j] = 0.0
            continue
        out[j] = round(float(np.ptp(_proj(xs[near], ys[near], j, joints, bones))), 1)
    for j, a, b in (("neck", "head", "torso"), ("hem", "pelvis", "torso")):
        if a in layers and b in layers:
            both = (layers[a][..., 3] > 8) & (layers[b][..., 3] > 8)
            ys = np.nonzero(both.any(1))[0]
            out[j] = float(len(ys))
    return out


def _proj(xs, ys, j, joints, bones):
    """Projection of points on the bone that starts or ends at joint j."""
    np = _np()
    J = np.array(joints[j], float)
    best = None
    for end in ("t", "h"):                       # the bone that ends at j, else the one that starts there
        for b in bones:
            p = np.array([b[end + "x"], b[end + "y"]])
            v = np.array([b["tx"] - b["hx"], b["ty"] - b["hy"]])
            if best is None and np.hypot(*(p - J)) < 1e-3 and np.linalg.norm(v) > 1e-6:
                best = v / np.linalg.norm(v)
    if best is None:
        best = np.array([0.0, 1.0])
    return (np.c_[xs, ys] - J) @ best


def swap_visible(layers, present, parts):
    """Each swap state against its default, composited under every layer above it at rest: the
    share of the pixels the swap changes (|RGB| > 40) that still change in the picture, and the
    mean change there. A layer above that covers the mouth leaves a swap no one sees."""
    np = _np()
    out, worst = {}, 1.0
    for default, alt in (("eyes_open", "eyes_closed"), ("mouth_closed", "mouth_open")):
        if default not in layers or alt not in layers:
            continue
        a, b = layers[default], layers[alt]
        changed = (np.abs(a[..., :3] - b[..., :3]).max(-1) > 40) & ((a[..., 3] > 127) | (b[..., 3] > 127))
        if not changed.any():
            out[alt] = {"visible": 0.0, "changed_px": 0, "mean_delta": 0.0}
            worst = 0.0
            continue

        def stack(state):
            shown = [n for n in present if not parts[n].get("hidden") and n != default] + [state]
            order = [n for n in present if n in shown]
            return over([layers[n] for n in reversed(order)])
        ca, cb = stack(default), stack(alt)
        d = np.abs(ca[..., :3] - cb[..., :3]).max(-1)
        vis = float(((d > 40) & changed).sum() / changed.sum())
        hair = any(n.startswith("hair") for n in present[:present.index(default)])
        out[alt] = {"visible": round(vis, 3), "changed_px": int(changed.sum()),
                    "mean_delta": round(float(d[changed].mean()), 1)}
        if alt.startswith("mouth") or not hair:   # bangs may hide the eyes; nothing hides the mouth
            worst = min(worst, vis)
    return {"worst": round(worst, 3), "per_swap": out}


def shoulder_notch(layers, S, A, geo, L):
    """Where an arm moves away, the body left behind must be whole and outlined."""
    np, ndi = _np(), _ndi()
    body = np.zeros_like(A)
    for n, a in layers.items():
        if not n.startswith(("arm_", "hand_", "prop_")) and n not in ("eyes_closed", "mouth_open"):
            body |= a[..., 3] > 127
    region, under = np.zeros_like(A), np.zeros_like(A)
    for g in geo.values():
        region |= ndi.binary_dilation(g["arm"], iterations=6)
        under |= ndi.binary_dilation(g["arm"], iterations=2)
    yy = np.arange(A.shape[0])[:, None]
    region &= yy <= L.get("y_hem", A.shape[0])
    closed = ndi.binary_closing(body, structure=disk(12))
    notch = closed & ~body & region
    edge = body & ~ndi.binary_erosion(body, iterations=2) & under & region   # the edge the arm hid
    ring = A & ~ndi.binary_erosion(A, iterations=3)
    dark = float(np.percentile(luma(S[..., :3])[ring], 20)) + 45 if ring.any() else 90.0
    lum = luma(S[..., :3])
    torso_img = layers.get("torso")
    if torso_img is not None:
        lum = np.where(torso_img[..., 3] > 127, luma(torso_img[..., :3]), lum)
    # an edge pixel counts as outlined when it or a neighbour within 2 px is outline-dark
    darkm = ndi.binary_dilation((lum < dark) & body, iterations=2)
    outlined = float((edge & darkm).sum() / max(edge.sum(), 1)) if edge.any() else 1.0
    return {"notch_share": round(float(notch.sum() / max(A.sum(), 1)), 5), "notch_px": int(notch.sum()),
            "outlined": round(outlined, 3), "edge_px": int(edge.sum()), "dark_luma": round(dark, 1)}


def tri_cover(pts, tris, shape):
    """Pixels whose centre lies in any of the triangles, as a GPU rasterises them."""
    np = _np()
    out = np.zeros(shape, bool)
    H, W = shape
    for s in tris:
        a, b, c = pts[s[0]], pts[s[1]], pts[s[2]]
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-9:
            continue
        x0, x1 = max(0, int(np.floor(min(a[0], b[0], c[0])))), min(W - 1, int(np.ceil(max(a[0], b[0], c[0]))))
        y0, y1 = max(0, int(np.floor(min(a[1], b[1], c[1])))), min(H - 1, int(np.ceil(max(a[1], b[1], c[1]))))
        if x1 < x0 or y1 < y0:
            continue
        py, px = np.mgrid[y0:y1 + 1, x0:x1 + 1] + 0.5
        l1 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / den
        l2 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / den
        out[y0:y1 + 1, x0:x1 + 1] |= (l1 >= -1e-4) & (l2 >= -1e-4) & (1 - l1 - l2 >= -1e-4)
    return out


def mesh_for(name, mask, p, bones, bidx, step=22):
    """Grid and contour vertices inside the grown mask, Delaunay, triangles kept inside; two-bone
    smoothstep weights across the joint the part's two bones share."""
    np, ndi = _np(), _ndi()
    from scipy.spatial import Delaunay
    empty = {"name": name, "bones": p["bones"], "verts": [], "indices": [], "bw": []}
    if not mask.any():
        return empty
    grown = ndi.binary_dilation(mask, iterations=3)
    ys, xs = np.nonzero(grown)
    step = int(np.clip(np.sqrt(mask.sum()) / 12, 4, step))     # small parts (eyes, mouth) get a finer grid
    pts = [(x, y) for y in range(ys.min(), ys.max() + 1, step) for x in range(xs.min(), xs.max() + 1, step) if grown[y, x]]
    edge = grown & ~ndi.binary_erosion(grown)
    ey, ex = np.nonzero(edge)
    taken = np.zeros_like(grown)
    for i in np.argsort(ey * 100000 + ex):
        y, x = ey[i], ex[i]
        r_ = max(2, step // 3)
        if not taken[max(0, y - r_):y + r_ + 1, max(0, x - r_):x + r_ + 1].any():
            taken[y, x] = True
            pts.append((x, y))
    H, W = grown.shape
    for _ in range(3):
        pts = np.unique(np.array(pts, np.float64), axis=0)
        if len(pts) < 3:
            return empty
        try:
            tri = Delaunay(pts)
        except Exception:
            return empty
        keep, dropped = [], []
        for s in tri.simplices:
            q = [pts[s].mean(0)] + [(pts[s[i]] + pts[s[(i + 1) % 3]]) / 2 for i in range(3)]
            inside = all(grown[min(H - 1, int(round(v[1]))), min(W - 1, int(round(v[0])))] for v in q)
            (keep if inside else dropped).append(s)
        # a triangle the test above drops along a wavy edge leaves a sliver of the layer uncovered,
        # which renders as background: give back every dropped triangle that holds a layer pixel
        miss = mask & ~tri_cover(pts, keep, mask.shape)
        for s in dropped:
            if not miss.any():
                break
            r = tri_cover(pts, [s], mask.shape)
            if (r & miss).any():
                keep.append(s)
                miss &= ~r
        if not miss.any():
            break
        my, mx = np.nonzero(miss)                 # outside every triangle (a thin tip): add the
        corners = [np.c_[mx + dx, my + dy] for dx in (0, 1) for dy in (0, 1)]   # pixels' corners
        pts = np.vstack([pts] + corners).astype(np.float64)
    if not keep:
        return empty
    keep = np.array(keep)
    used = np.unique(keep)
    remap = {int(o): i for i, o in enumerate(used)}
    verts = pts[used]
    idx = [remap[int(v)] for s in keep for v in s]
    bw = []
    if len(p["bones"]) == 1:
        for _ in verts:
            bw += [0, 1.0, 0, 0.0]
    else:
        b0, b1 = bones[bidx[p["bones"][0]]], bones[bidx[p["bones"][1]]]
        J = np.array([b1["hx"], b1["hy"]])
        u = np.array([b1["tx"] - b0["hx"], b1["ty"] - b0["hy"]])
        u = u / max(np.linalg.norm(u), 1e-6)
        bwid = max(float(p.get("bw", 20)), 2.0)
        for v in verts:
            f = float(np.clip(((v - J) @ u + bwid) / (2 * bwid), 0, 1))
            f = f * f * (3 - 2 * f)
            bw += [0, round(1 - f, 4), 1, round(f, 4)]
    return {"name": name, "bones": p["bones"], "verts": [round(float(c), 2) for c in verts.ravel()],
            "indices": idx, "bw": bw}


def debug(S, parts, present, bones, path):
    np, ndi = _np(), _ndi()
    from PIL import Image, ImageDraw
    bg = Image.new("RGBA", (S.shape[1], S.shape[0]), (40, 40, 40, 255))
    bg.alpha_composite(Image.fromarray(np.clip(S, 0, 255).astype(np.uint8)))
    ov = np.zeros(S.shape[:2] + (4,), np.uint8)
    rng = np.random.RandomState(3)
    for n in present:
        m = parts[n]["mask"]
        e = m & ~ndi.binary_erosion(m, iterations=2)
        ov[e] = list(rng.randint(80, 255, 3)) + [255]
    bg.alpha_composite(Image.fromarray(ov))
    d = ImageDraw.Draw(bg)
    for b in bones:
        d.line([(b["hx"], b["hy"]), (b["tx"], b["ty"])], fill=(255, 255, 0, 255), width=4)
        d.ellipse([b["hx"] - 7, b["hy"] - 7, b["hx"] + 7, b["hy"] + 7], outline=(255, 0, 0, 255), width=3)
    bg.convert("RGB").save(path)


def pose_preview(layers, present, geo, path, angle=120, prop_side=None):
    """Rest, and every arm raised by rotating its arm and hand layers about the shoulder joint."""
    np = _np()
    from PIL import Image
    H, W = next(iter(layers.values())).shape[:2]

    def compose(rot):
        acc = Image.new("RGBA", (W, H), (205, 210, 220, 255))
        for n in reversed(present):
            if n in ("eyes_closed", "mouth_open"):
                continue
            im = Image.fromarray(np.clip(layers[n], 0, 255).astype(np.uint8))
            side = n.split("_", 1)[1] if n.startswith(("arm_", "hand_")) else (prop_side or {}).get(n)
            if rot and side in geo:
                J = geo[side]["J"]
                sgn = -1 if (geo[side]["Tip"][0] < J[0]) else 1
                im = im.rotate(sgn * angle, resample=Image.BICUBIC, center=(float(J[0]), float(J[1])))
            acc.alpha_composite(im)
        return acc.convert("RGB")

    a, b = compose(False), compose(True)
    s = Image.new("RGB", (W * 2 + 16, H), (40, 40, 40))
    s.paste(a, (0, 0))
    s.paste(b, (W + 16, 0))
    s.resize(((W * 2 + 16) // 2, H // 2), Image.LANCZOS).save(path)


# -------------------------------------------------------------------------------------- fills
def client_mod():
    sys.path.insert(0, str(HERE))
    import comfy_asset_client as cac
    return cac


def wait_idle(base: str, seconds: float) -> None:
    cac = client_mod()
    end = time.monotonic() + seconds
    while not cac.queue_empty(base):
        if time.monotonic() > end:
            raise JobFailed("the ComfyUI queue stayed busy; nothing submitted")
        time.sleep(15)


def key_colour(rgb):
    np = _np()
    border = np.concatenate([rgb[:8].reshape(-1, 3), rgb[-8:].reshape(-1, 3), rgb[:, :8].reshape(-1, 3),
                             rgb[:, -8:].reshape(-1, 3)])
    return np.median(border, 0)


def pad_square(rgb, box, key, size=EDIT_SIZE):
    """Crop box (x0,y0,x1,y1, may leave the canvas) -> a square filled with the key colour."""
    np = _np()
    from PIL import Image
    x0, y0, x1, y1 = box
    side = max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    sx0, sy0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    sq = np.empty((side, side, 3), np.float32)
    sq[:] = key
    H, W = rgb.shape[:2]
    ax0, ay0, ax1, ay1 = max(sx0, 0), max(sy0, 0), min(sx0 + side, W), min(sy0 + side, H)
    sq[ay0 - sy0:ay1 - sy0, ax0 - sx0:ax1 - sx0] = rgb[ay0:ay1, ax0:ax1, :3]
    im = Image.fromarray(sq.clip(0, 255).astype(np.uint8)).resize((size, size), Image.LANCZOS)
    return im, (sx0, sy0, side)


def place(rgba_sq, square, W, H):
    """A keyed square edit back onto the canvas."""
    np = _np()
    sx0, sy0, side = square
    big = resize_rgba(rgba_sq, side, side)
    c = np.zeros((H, W, 4), np.float32)
    ax0, ay0, ax1, ay1 = max(sx0, 0), max(sy0, 0), min(sx0 + side, W), min(sy0 + side, H)
    c[ay0:ay1, ax0:ax1] = big[ay0 - sy0:ay1 - sy0, ax0 - sx0:ax1 - sx0]
    return c


def key_rgba(png: Path, out: Path, key) -> Path:
    """Key an edit's flat background with codex-visual's key_unmix.py; a plain distance key when
    that skill is not installed beside this one."""
    np = _np()
    hexkey = "#%02x%02x%02x" % tuple(int(round(v)) for v in key)
    if KEY_UNMIX.is_file():
        r = subprocess.run([sys.executable, str(KEY_UNMIX), str(png), "--out", str(out), "--edge", "tint",
                            "--key-color", "#ff00ff" if np.abs(np.array(key) - [255, 0, 255]).max() < 60 else hexkey],
                           capture_output=True, text=True)
        if out.is_file():
            return out
    a = load(png)
    d = np.abs(a[..., :3] - np.array(key)).max(-1)
    a[..., 3] = np.where(d < 80, 0, 255)
    save(a, out)
    return out


def head_box(A, W, H):
    """A square around the head: from the top of the hair to just below the neck."""
    np = _np()
    rows = np.nonzero(A.any(1))[0]
    y_top, y_bot = int(rows[0]), int(rows[-1])
    h = y_bot - y_top
    width = A.sum(1)
    lo, hi = y_top + int(0.08 * h), y_top + int(0.30 * h)
    y_neck = int(lo + np.argmin(width[lo:hi]))
    top = largest(A[y_top:y_neck]) if y_neck > y_top + 4 else A[y_top:y_neck]   # the head, not a stray tip
    cols = np.nonzero(top.any(0))[0]
    x0, x1 = int(cols[0]), int(cols[-1])
    side = int(max(y_neck - y_top, x1 - x0) * 1.2) + 16
    cx = (x0 + x1) / 2
    top = y_top - int(0.06 * side)
    return [int(cx - side / 2), top, int(cx - side / 2) + side, top + side]


def keep_zone(name, A, box):
    """Where a fill must not have changed: the head and the lower legs for noarms; the chin,
    neck and collar (the box's bottom 30 %) for bald and face_blank; the whole box for eyes and
    mouth (a small change, so the 75th percentile ignores it)."""
    np = _np()
    H, W = A.shape
    yy, xx = np.mgrid[:H, :W]
    rows = np.nonzero(A.any(1))[0]
    y_top, h = int(rows[0]), int(rows[-1] - rows[0])
    if name == "noarms":
        return (yy < y_top + 0.15 * h) | (yy > y_top + 0.72 * h)
    if name.startswith("noprop_"):        # a held prop can cross the legs: only the head must hold
        return yy < y_top + 0.15 * h
    x0, y0, x1, y1 = box
    inbox = (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)
    if name in ("bald", "face_blank"):
        return inbox & (yy >= y1 - 0.3 * (y1 - y0))
    return inbox


PROP_REMOVED_MIN = 0.7    # share of a prop's pixels its removal fill must change


def removed_gate(fill, S, A, props_mask):
    """fill.removed: where the prop's own fill lies on the character, its removal fill changed
    >= PROP_REMOVED_MIN of the pixels (by more than 40, or to background). An edit can keep the
    prop it was asked to remove."""
    np = _np()
    if props_mask is None or not props_mask.any():
        return gate("fill.removed", None, PROP_REMOVED_MIN, True, note="unmeasured: the prop's own fill failed")
    m = props_mask & A
    ch = (np.abs(fill[..., :3] - S[..., :3]).max(-1) > 40) | (fill[..., 3] <= 127)
    v = float((ch & m).sum() / max(m.sum(), 1))
    return gate("fill.removed", round(v, 4), PROP_REMOVED_MIN, v >= PROP_REMOVED_MIN)


def fill_gates(name, fill, S, A, box, ignore=None):
    """fill.aligned: 75th percentile |RGB| in the keep zone; fill.iou: silhouettes agree there;
    fill.inside (head fills): the fill stays inside the source silhouette grown 4 px; fill.changed
    (eyes, mouth): the share of the head the fill changes by more than 40. The armless fill may
    widen into the gaps beside the arms; split clips it to the source."""
    np, ndi = _np(), _ndi()
    fA = fill[..., 3] > 127
    if name.startswith("prop_"):          # the prop alone: inside the source, and drawn at all
        grown = ndi.binary_dilation(A, iterations=4)
        inside = float((fA & ~grown).sum() / max(fA.sum(), 1))
        share = float(fA.mean())
        return [gate("fill.inside", round(inside, 4), 0.03, inside <= 0.03),
                gate("fill.present", round(share, 4), 0.002, share >= 0.002)]
    kz = keep_zone(name, A, box)
    if ignore is not None:                # where a held prop was: the fill removed it on purpose
        kz = kz & ~ignore
    both = fA & A & kz
    d = np.abs(fill[..., :3] - S[..., :3]).mean(-1)[both]
    p75 = float(np.percentile(d, 75)) if len(d) else 999.0
    iou = float((fA & A & kz).sum() / max(((fA | A) & kz).sum(), 1))
    gs = [gate("fill.aligned", round(p75, 2), 12, p75 <= 12),
          gate("fill.iou", round(iou, 4), 0.95, iou >= 0.95)]
    if name != "noarms":
        x0, y0, x1, y1 = box
        inb = np.zeros_like(fA)
        inb[max(y0, 0):y1, max(x0, 0):x1] = True
        grown = ndi.binary_dilation(A, iterations=4)
        inside = float((fA & ~grown & inb).sum() / max((fA & inb).sum(), 1))
        gs.append(gate("fill.inside", round(inside, 4), 0.03, inside <= 0.03))
    if name in ("eyes_closed", "mouth_open"):
        # the swap must read at a glance: lips that only part (a hint of teeth) change well under
        # 1 % of the head; a mouth open with its dark inside, or shut eyes, 2-3 %
        x0, y0, x1, y1 = box
        inb = np.zeros_like(fA)
        inb[max(y0, 0):y1, max(x0, 0):x1] = True
        head = A & inb
        ch = (np.abs(fill[..., :3] - S[..., :3]).max(-1) > 40) & head & fA
        share = float(ch.sum() / max(head.sum(), 1))
        gs.append(gate("fill.changed", round(share, 4), FILL_CHANGED_MIN, share >= FILL_CHANGED_MIN))
    return gs


SIDES = {}                                # prop name -> the side a person said holds it


def parse_props(text):
    """'pole=a long wooden pole;shield=a round shield' -> {'pole': ..., 'shield': ...}."""
    out = {}
    for kv in (text or "").split(";"):
        if not kv.strip():
            continue
        k, eq, v = kv.partition("=")
        k = k.strip().lower()
        k, at, side = k.partition("@")
        if at:                            # name@side: the person says which arm holds it
            if side not in ("near", "far", "l", "r"):
                raise ValueError(f"--props side must be near, far, L or R, got {side!r}")
            SIDES[k] = side.upper() if side in ("l", "r") else side
        if not eq or not k.isidentifier() or not v.strip():
            raise ValueError(f"--props wants name=description;..., got {kv!r}")
        out[k] = v.strip()
    return out


def cmd_fills(a) -> int:
    np = _np()
    from PIL import Image
    out = a.out
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "head_crop").mkdir(exist_ok=True)
    rgb = np.asarray(Image.open(a.concept).convert("RGB")).astype(np.float32)
    H, W = rgb.shape[:2]
    key = key_colour(rgb)
    src_keyed = out / "source_keyed.png"
    key_rgba(a.concept, src_keyed, key)
    S = load(src_keyed)
    A = S[..., 3] > 127
    hb = head_box(A, W, H)                # recomputed without the props before the first head fill
    cac = client_mod()
    base = cac.resolve_server(a.server, cac.load_config(cac.DEFAULT_CONFIG))
    hint = (a.hint.strip() + " ") if a.hint else ""
    props = parse_props(a.props)
    gone = ""
    if props:
        what = " and ".join(props.values())
        gone = f"Also remove {what} completely, and draw what they covered. "
    jobs = []
    for k, v in props.items():            # first: each prop's own fill gates its removal fill
        jobs += [(f"prop_{k}", [0, 0, W, H], PROMPTS["prop"].format(what=v)),
                 (f"noprop_{k}", [0, 0, W, H], PROMPTS["noprops"].format(what=v) + hint)]
    jobs.append(("noarms", [0, 0, W, H], PROMPTS["noarms_" + a.view] + gone + hint))
    jobs += [(k, "HEAD", PROMPTS[k]) for k in ("bald", "eyes_closed", "mouth_open")]
    if a.cubism:
        jobs.append(("face_blank", "HEAD", PROMPTS["face_blank"]))
    seeds = [int(s) for s in a.seeds.split(",")]
    doc = {"tool": "layer_split", "view": a.view, "facing": a.facing if a.view == "side" else "front",
           "canvas": [W, H], "key": [round(float(v), 1) for v in key], "head_box": hb, "edit_size": EDIT_SIZE,
           "source": src_keyed.name, "fills": {}, "props": list(props), "prop_sides": dict(SIDES)}
    if a.only:                            # redo some fills, keep the others from fills.json
        only = [x.strip() for x in a.only.split(",") if x.strip()]
        old = json.loads((out / "fills.json").read_text(encoding="utf-8")) if (out / "fills.json").is_file() else {}
        doc["fills"] = {k: v for k, v in old.get("fills", {}).items() if k not in only}
        jobs = [j for j in jobs if j[0] in only]

    def head_now():
        """The head box, found once the props' own fills exist: a pole above the head would
        otherwise widen the box to the whole upper body."""
        m = A.copy()
        for k in props:
            pf = out / f"prop_{k}.png"
            if pf.is_file() and doc["fills"].get(f"prop_{k}", {}).get("pass"):
                m &= ~(load(pf)[..., 3] > 127)
        b = head_box(m, W, H)
        doc["head_box"] = b
        sq_src, _ = pad_square(S[..., :3] * (S[..., 3:4] / 255) + key * (1 - S[..., 3:4] / 255), b, key)
        sq_src.save(out / "head_crop" / "source.png")
        return b
    hb = None
    failed = []
    for name, box, prompt in jobs:
        if box == "HEAD":
            hb = hb or head_now()
            box = hb
        sq, square = pad_square(rgb, box, key)
        rec = None
        for seed in seeds:
            with tempfile.TemporaryDirectory() as td:
                t = Path(td)
                inp = t / "in.png"
                sq.save(inp)
                h = hashlib.sha256(inp.read_bytes()).hexdigest()[:10]
                up = t / f"layer_split_{name}_{h}.png"
                shutil.copyfile(inp, up)
                wf = t / "graph.json"
                wf.write_text(json.dumps({"client_id": "layer-split", "prompt": graph(
                    up.name, prompt + (KEEP_PROP if name.startswith("prop_") else KEEP), seed,
                    f"layer_split/{name}_{h}")}), encoding="utf-8")
                wait_idle(base, a.wait_idle)
                cmd = [sys.executable, str(CLIENT), "--workflow", str(wf), "--output-dir", str(t / "o"),
                       "--upload", str(up), "--timeout-seconds", str(a.timeout), "--server", base, "--keep-loaded"]
                r = subprocess.run(cmd, capture_output=True, text=True)
                pngs = sorted((t / "o").glob("**/*.png")) if (t / "o").exists() else []
                if r.returncode != 0 or not pngs:
                    raise JobFailed(f"{name}: client exit {r.returncode}: {r.stderr[-400:]}")
                raw = out / "raw" / f"{name}_s{seed}.png"
                shutil.copyfile(pngs[0], raw)
            keyed = key_rgba(raw, out / "raw" / f"{name}_s{seed}_keyed.png", key)
            ks = load(keyed)
            placed = place(ks, square, W, H)
            ign = None
            if (name == "noarms" or name.startswith("noprop_")) and props:
                import scipy.ndimage as ndi_
                ign = np.zeros_like(A)
                for k in (props if name == "noarms" else [name[len("noprop_"):]]):
                    pf = out / f"prop_{k}.png"
                    if pf.is_file() and doc["fills"].get(f"prop_{k}", {}).get("pass"):
                        ign |= load(pf)[..., 3] > 127
                pm, ign = ign, ndi_.binary_dilation(ign, iterations=8)
            gs = fill_gates(name, placed, S, A, box, ign)
            if name.startswith("noprop_"):
                gs.append(removed_gate(placed, S, A, pm))
            rec = {"png": f"{name}.png", "raw": f"raw/{name}_s{seed}.png", "seed": seed, "box": box,
                   "pass": all(g["pass"] for g in gs), "gates": gs}
            print(json.dumps({"fill": name, "seed": seed, "pass": rec["pass"],
                              "gates": {g["name"]: g["value"] for g in gs}}), flush=True)
            if rec["pass"]:
                break
        save(placed, out / f"{name}.png")
        if box == hb:
            save(ks, out / "head_crop" / f"{name}.png")
        doc["fills"][name] = rec
        if not rec["pass"]:
            failed.append(name)
    failed = [n for n, r in doc["fills"].items() if not r.get("pass")]
    (out / "fills.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    rep = {"schema": "gate/1", "tool": "layer_split", "pass": not failed,
           "gates": [dict(g, name=f"{g['name']}.{n}") for n, r in doc["fills"].items() for g in r["gates"]]}
    (out / "fills.gate.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    if not a.keep_loaded and cac.queue_empty(base):
        cac.request(base, "/free", {"unload_models": True, "free_memory": True})
    print(json.dumps({"fills": str(out / "fills.json"), "pass": not failed, "failed": failed}))
    return 0 if not failed else 2


# ----------------------------------------------------------------------------------- selftest
def synth(view="front", facing="right", notch=False, strap=False, hood=False, pole=False):
    """A flat, outlined figure on the canvas plus its four fills, as split() expects them."""
    np = _np()
    from PIL import Image, ImageDraw
    W, H = 360, 540
    OUT = (20, 20, 25, 255)

    def figure(arms=True, hair=True, eyes="open", mouth="closed", bite=False, strap=strap, pole=pole, only=False):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        cx = 180
        s_ = 1 if facing == "right" else -1
        ends = [(cx + s_ * 155, 235), (cx - s_ * 70, 440)]      # through the near hand, across hips and legs
        if only:
            d.line(ends, fill=OUT, width=16)
            d.line(ends, fill=(200, 140, 70, 255), width=10)
            return np.asarray(im).astype(np.float32)
        skin, jacket, shorts, sock = (235, 190, 160, 255), (30, 170, 180, 255), (60, 60, 66, 255), (25, 25, 30, 255)
        if view == "front":
            arm_pts = [((132, 142), (84, 300)), ((228, 142), (276, 300))]
        else:
            s = 1 if facing == "right" else -1
            arm_pts = [((cx, 140), (cx + s * 95, 290)), ((cx, 140), (cx - s * 95, 290))]
        if arms and view == "side":                         # the far arm is behind the body
            p, q = arm_pts[1]
            d.line([p, q], fill=OUT, width=34)
            d.line([p, q], fill=jacket, width=26)
            d.ellipse([q[0] - 16, q[1] - 16, q[0] + 16, q[1] + 16], fill=OUT)
            d.ellipse([q[0] - 12, q[1] - 12, q[0] + 12, q[1] + 12], fill=skin)
        legs = [(152, 140), (208, 220)] if view == "front" else [(cx - 10, cx - 50), (cx + 10, cx + 50)]
        for x_top, x_bot in legs:
            d.line([(x_top, 330), (x_bot, 490)], fill=OUT, width=36)
            d.line([(x_top, 330), (x_bot, 490)], fill=sock, width=28)
            d.ellipse([x_bot - 26, 482, x_bot + 26, 512], fill=OUT)
            d.ellipse([x_bot - 22, 486, x_bot + 22, 508], fill=(240, 240, 240, 255))
        tw = 64 if view == "front" else 44
        d.rounded_rectangle([cx - tw - 4, 116, cx + tw + 4, 344], 22, fill=OUT)
        d.rounded_rectangle([cx - tw, 120, cx + tw, 270], 18, fill=jacket)
        d.rectangle([cx - tw, 270, cx + tw, 340], fill=shorts)
        if bite:                                            # a straight, unoutlined cut at the shoulder
            d.rectangle([cx - tw - 4, 116, cx - tw + 22, 170], fill=(0, 0, 0, 0))
            d.rectangle([cx + tw - 22, 116, cx + tw + 4, 170], fill=(0, 0, 0, 0))
        if hood:                                            # a hood down round the neck, wider than the jaw
            d.rounded_rectangle([cx - 74, 92, cx + 74, 160], 30, fill=OUT)
            d.rounded_rectangle([cx - 70, 96, cx + 70, 156], 26, fill=jacket)
        d.rectangle([cx - 13, 100, cx + 13, 124], fill=OUT)
        d.rectangle([cx - 9, 100, cx + 9, 124], fill=skin)
        d.ellipse([cx - 52, 10, cx + 52, 112], fill=OUT)
        d.ellipse([cx - 48, 14, cx + 48, 108], fill=skin)
        if hair:
            d.chord([cx - 54, 4, cx + 54, 84], 180, 360, fill=OUT)
            d.chord([cx - 50, 8, cx + 50, 80], 180, 360, fill=(130, 80, 40, 255))
        ex = [cx - 20, cx + 20] if view == "front" else [cx + (22 if facing == "right" else -22)]
        for x in ex:
            if eyes == "open":
                d.ellipse([x - 8, 56, x + 8, 72], fill=(250, 250, 250, 255), outline=OUT, width=2)
                d.ellipse([x - 4, 59, x + 4, 69], fill=(90, 50, 20, 255))
            else:
                d.line([(x - 9, 66), (x + 9, 66)], fill=OUT, width=3)
        mx = cx if view == "front" else cx + (24 if facing == "right" else -24)
        if mouth == "closed":
            d.line([(mx - 10, 90), (mx + 10, 90)], fill=OUT, width=3)
        else:
            d.ellipse([mx - 9, 84, mx + 9, 98], fill=(120, 20, 30, 255), outline=OUT, width=2)
        if pole:                                            # a held pole, the near hand drawn over it
            d.line(ends, fill=OUT, width=16)
            d.line(ends, fill=(200, 140, 70, 255), width=10)
        if arms:
            for i, (p, q) in enumerate(arm_pts):
                if view == "side" and i == 1:
                    continue
                d.line([p, q], fill=OUT, width=34)
                d.line([p, q], fill=jacket, width=26)
                d.ellipse([p[0] - 17, p[1] - 17, p[0] + 17, p[1] + 17], fill=OUT)
                d.ellipse([p[0] - 13, p[1] - 13, p[0] + 13, p[1] + 13], fill=jacket)
                d.ellipse([q[0] - 16, q[1] - 16, q[0] + 16, q[1] + 16], fill=OUT)
                d.ellipse([q[0] - 12, q[1] - 12, q[0] + 12, q[1] + 12], fill=skin)
        if strap:                                           # a bag strap drawn across arm and chest
            d.line([(cx - 40, 215), (cx + 50, 150)], fill=(50, 50, 55, 255), width=14)
        return np.asarray(im).astype(np.float32)

    src = figure()
    fills = {"noarms": figure(arms=False, bite=notch, pole=False), "bald": figure(hair=False),
             "eyes_closed": figure(eyes="closed"), "mouth_open": figure(mouth="open")}
    if pole:
        fills["noprop_pole"] = figure(pole=False)
        fills["prop_pole"] = figure(only=True)
    return src, fills


def selftest() -> int:
    np = _np()
    checks = {}
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        for view, facing in (("front", "front"), ("side", "right"), ("side", "left")):
            src, fills = synth(view, facing)
            d = t / f"{view}_{facing}"
            d.mkdir()
            save(src, d / "src.png")
            doc = {"tool": "layer_split", "view": view, "facing": facing, "canvas": [src.shape[1], src.shape[0]],
                   "fills": {}}
            for k, v in fills.items():
                save(v, d / f"{k}.png")
                doc["fills"][k] = {"png": f"{k}.png"}
            (d / "fills.json").write_text(json.dumps(doc), encoding="utf-8")
            rep = split(d / "src.png", d / "fills.json", d / "out", overlap=10)
            g = {x["name"]: x for x in rep["gates"]}
            failing = [n for n, x in g.items() if not x["pass"]]
            checks[f"{view}_{facing}_gates"] = rep["pass"]
            if failing:
                print(json.dumps({view + "_" + facing: {n: g[n] for n in failing}}, default=str), file=sys.stderr)
            rig = json.loads((d / "out" / "rig2d.json").read_text(encoding="utf-8"))
            sums = [rig_p["bw"][i + 1] + rig_p["bw"][i + 3] for rig_p in rig["parts"] for i in range(0, len(rig_p["bw"]), 4)]
            checks[f"{view}_{facing}_weights"] = bool(sums) and max(abs(s - 1) for s in sums) < 1e-3
            names = set(rig["layers"])
            sides = ("R", "L") if view == "front" else ("near", "far")
            checks[f"{view}_{facing}_names"] = {f"arm_{s}" for s in sides} <= names and "eyes_closed" in names
            if view == "side":
                bones = {b["name"]: b for b in rig["bones"]}
                fwd = 1 if facing == "right" else -1
                checks[f"side_{facing}_near_forward"] = fwd * (bones["hand_near"]["tx"] - bones["hand_far"]["tx"]) > 0
            if view == "front":
                bones = {b["name"]: b for b in rig["bones"]}
                checks["front_right_on_screen_left"] = bones["hand_R"]["tx"] < bones["hand_L"]["tx"]
                man = json.loads((d / "out" / "manifest.json").read_text(encoding="utf-8"))
                checks["manifest_hidden_swaps"] = {x["name"] for x in man["layers"] if x["hidden"]} == {"eyes_closed", "mouth_open"}
                req = ("schema", "width", "height", "bones", "parts", "layers", "swaps", "view")
                checks["rig2d_keys"] = all(k in rig for k in req) and rig["schema"] == "rig2d/1"
                contract_out("selftest.rig2d.json", rig)
        src, fills = synth("front", notch=True)                 # the straight shoulder cut is caught
        d = t / "notch"
        d.mkdir()
        save(src, d / "src.png")
        doc = {"view": "front", "facing": "front", "canvas": [src.shape[1], src.shape[0]], "fills": {}}
        for k, v in fills.items():
            save(v, d / f"{k}.png")
            doc["fills"][k] = {"png": f"{k}.png"}
        (d / "fills.json").write_text(json.dumps(doc), encoding="utf-8")
        rep = split(d / "src.png", d / "fills.json", d / "out", overlap=10)
        notch = next(x for x in rep["gates"] if x["name"] == "split.shoulder_notch")
        checks["notch_caught"] = not notch["pass"]
        man = json.loads((t / "front_front" / "out" / "manifest.json").read_text(encoding="utf-8"))["layers"]
        lay = {x["name"]: load(t / "front_front" / "out" / x["png"]) for x in man}
        hid = {x["name"]: {"hidden": x["hidden"]} for x in man}
        order = [x["name"] for x in man]
        ok_before = swap_visible(lay, order, hid)["worst"] >= SWAP_VISIBLE_MIN
        ys, xs = np.nonzero(lay["mouth_open"][..., 3] > 127)          # the torso drawn over the mouth
        lay["torso"][ys, xs] = lay["head"][ys, xs]
        lay["torso"][ys, xs, 3] = 255
        rp = next(p for p in json.loads((t / "front_front" / "out" / "rig2d.json").read_text(encoding="utf-8"))["parts"]
                  if p["name"] == "torso")
        v, tri = np.array(rp["verts"]).reshape(-1, 2), np.array(rp["indices"]).reshape(-1, 3)
        al = load(t / "front_front" / "out" / "torso.png")[..., 3] > 8
        checks["mesh_gap_caught"] = bool(not (al & ~tri_cover(v, tri, al.shape)).any() and
                                         (al & ~tri_cover(v, tri[np.arange(len(tri)) % 3 != 0], al.shape)).any())
        checks["swap_hidden_caught"] = bool(ok_before and swap_visible(lay, order, hid)["worst"] < SWAP_VISIBLE_MIN)
        src, fills = synth("side", "right", strap=True)         # a strap across the near arm
        d = t / "strap"
        d.mkdir()
        save(src, d / "src.png")
        doc = {"view": "side", "facing": "right", "canvas": [src.shape[1], src.shape[0]], "fills": {}}
        for k, v in fills.items():
            save(v, d / f"{k}.png")
            doc["fills"][k] = {"png": f"{k}.png"}
        (d / "fills.json").write_text(json.dumps(doc), encoding="utf-8")
        rep = split(d / "src.png", d / "fills.json", d / "out", overlap=10)
        arm = load(d / "out" / "arm_near.png")
        on = arm[..., 3] > 127
        strap_left = (on & (np.abs(arm[..., :3] - np.array([50, 50, 55])).max(-1) < 12)).sum()
        sf = next(x for x in rep["gates"] if x["name"] == "split.sleeve_fill")
        checks["strap_off_the_sleeve"] = bool(rep["pass"] and strap_left < 20 and sf["value"] > 0)
        src, fills = synth("front", hood=True)                  # a hood flaring under the chin
        d = t / "hood"
        d.mkdir()
        save(src, d / "src.png")
        doc = {"view": "front", "facing": "front", "canvas": [src.shape[1], src.shape[0]], "fills": {}}
        for k, v in fills.items():
            save(v, d / f"{k}.png")
            doc["fills"][k] = {"png": f"{k}.png"}
        (d / "fills.json").write_text(json.dumps(doc), encoding="utf-8")
        rep = split(d / "src.png", d / "fills.json", d / "out", overlap=10)
        hp = next(x for x in rep["gates"] if x["name"] == "split.head_pivot")
        rig = json.loads((d / "out" / "rig2d.json").read_text(encoding="utf-8"))
        lay = {n: load(d / "out" / f"{n}.png") for n in rig["layers"]}
        Ls = rig["landmarks"]
        A_ = src[..., 3] > 127
        dk, _, w_ = outline_style(src, A_)
        pv = neck_pivot(src, A_, lay["eyes_open"][..., 3] > 8, lay["mouth_closed"][..., 3] > 8, Ls, dk, w_)
        old = {k: v.copy() for k, v in lay.items()}               # the 0.42.1 cut: pivot on the cut row,
        ys, xs = np.nonzero(pv["region"]) if pv else (np.array([], int), np.array([], int))
        old["torso"][ys, xs] = src[ys, xs]                        # the chin left on the torso
        old_g = head_pivot_gate(old, Ls["y_neck"] + 8, pv, Ls["y_armpit"])
        src, fills = synth("side", "right", pole=True)          # a pole held across the body
        res = {}
        for tag, props in (("pole", ["pole"]), ("pole_baked", [])):
            d = t / tag
            d.mkdir()
            save(src, d / "src.png")
            fl = dict(fills) if props else {k: v for k, v in fills.items() if not k.startswith(("noprop_", "prop_"))}
            doc = {"view": "side", "facing": "right", "canvas": [src.shape[1], src.shape[0]], "fills": {}, "props": props}
            for k, v in fl.items():
                save(v, d / f"{k}.png")
                doc["fills"][k] = {"png": f"{k}.png"}
            (d / "fills.json").write_text(json.dumps(doc), encoding="utf-8")
            res[tag] = split(d / "src.png", d / "fills.json", d / "out", overlap=10)
        g = {x["name"]: x for x in res["pole"]["gates"]}
        rig = json.loads((t / "pole" / "out" / "rig2d.json").read_text(encoding="utf-8"))
        pp = next((p for p in rig["parts"] if p["name"].startswith("prop_pole")), None)
        # the same picture through the 0.42.1 route: the pole stays in the body layers
        man = json.loads((t / "pole_baked" / "out" / "manifest.json").read_text(encoding="utf-8"))["layers"]
        lay = {x["name"]: load(t / "pole_baked" / "out" / x["png"]) for x in man}
        _, Pb = body_without_props(src, src[..., 3] > 127, {"pole": fills["noprop_pole"]}, {"pole": fills["prop_pole"]})
        old_g = prop_gate(lay, [x["name"] for x in man], {x["name"]: {"hidden": x["hidden"]} for x in man}, Pb,
                          src)
        checks["prop_layer"] = bool(res["pole"]["pass"] and g["split.prop_layer"]["pass"] and pp is not None
                                    and pp["name"] == "prop_pole_near" and pp["bones"] in (["hand_near"], ["forearm_near"])
                                    and not old_g["pass"])
        checks["hood_head_pivot"] = bool(hp["pass"] and hp["value"] is not None and rep["pass"] and not old_g["pass"])
    keep = dict(SIDES)
    try:
        pr = parse_props("pole=a long pole; shield@far=a round shield")
        checks["props_side"] = pr == {"pole": "a long pole", "shield": "a round shield"} and SIDES.get("shield") == "far"
        try:
            parse_props("shield@back=a shield")
            checks["props_side"] = False
        except ValueError:
            pass
    finally:
        SIDES.clear()
        SIDES.update(keep)
    try:
        tpl = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        checks["template_matches"] = set(tpl) == {"client_id", "prompt"} and tpl["prompt"] == graph(*TEMPLATE_ARGS)
    except (OSError, json.JSONDecodeError):
        checks["template_matches"] = False
    g = graph("a.png", "p", seed=5)
    links = [v for n in g.values() for v in n["inputs"].values() if isinstance(v, list)]
    checks["graph"] = all(v[0] in g for v in links) and g["13"]["inputs"]["pixels"] == ["7", 0] and \
        g["14"]["inputs"]["steps"] == 4 and g["14"]["inputs"]["seed"] == 5
    im, sq = pad_square(np.zeros((300, 200, 3), np.float32), [0, 0, 200, 300], np.array([255, 0, 255.0]), size=64)
    checks["square_pad"] = im.size == (64, 64) and sq == (-50, 0, 300)
    ok = all(checks.values())
    print(json.dumps({"checks": checks, "pass": ok}))
    return 0 if ok else 2


def contract_out(name: str, doc: dict) -> None:
    """Hand a sample to tools/check-contracts.py when it asks (UNITY_DEV_CONTRACT_OUT)."""
    d = os.environ.get("UNITY_DEV_CONTRACT_OUT")
    if not d:
        return
    p = Path(d) / f"layer_split.{name}"
    p.write_text(json.dumps(doc), encoding="utf-8")
    print(f"selftest-output: {p}")


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1, never 2."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["--selftest"], ["selftest"]):
        return selftest()
    ap = UsageParser(prog="layer_split.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd", parser_class=UsageParser)
    f = sub.add_parser("fills")
    f.add_argument("concept", type=Path, help="the opaque concept on its flat key field")
    f.add_argument("--view", choices=["front", "side"], required=True)
    f.add_argument("--facing", choices=["right", "left"], default="right", help="side view: where the face points")
    f.add_argument("--out", type=Path, required=True)
    f.add_argument("--seeds", default="1,2,3")
    f.add_argument("--hint", help="one sentence on the clothing under the arms, added to the noarms prompt")
    f.add_argument("--cubism", action="store_true", help="also the blank face cubism_psd.py needs")
    f.add_argument("--props", help="held props, name=description;...: each becomes the layer prop_<name>, "
                                   "bound to the hand that holds it, the body drawn whole behind it")
    f.add_argument("--server", default=os.environ.get("COMFYUI_SERVER_URL"))
    f.add_argument("--wait-idle", type=float, default=900)
    f.add_argument("--timeout", type=float, default=900)
    f.add_argument("--keep-loaded", action="store_true", help="skip the /free after the last fill")
    f.add_argument("--only", help="comma-separated fills to redo; the others are kept from OUT/fills.json")
    s = sub.add_parser("split")
    s.add_argument("keyed", type=Path, help="the keyed source (RGBA) on the fills' canvas")
    s.add_argument("--fills", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--overlap", type=int, default=22, help="px a lower layer runs under the one above")
    s.add_argument("--psb", help="also write OUT/NAME.psb with psd_write.py")
    s.add_argument("--far-arm", choices=["shown", "hidden"], default="shown",
                   help="side view: 'hidden' when a person sees the far arm wholly behind the body or a "
                        "shield; it gets bones and no layers, and split.limbs counts it")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.cmd:
        ap.error("choose fills or split")
    if a.cmd == "fills":
        if not a.concept.is_file():
            ap.error(f"concept not found: {a.concept}")
        try:
            parse_props(a.props)
        except ValueError as e:
            ap.error(str(e))
        try:
            return cmd_fills(a)
        except (JobFailed, OSError, json.JSONDecodeError) as e:
            print(f"layer_split.py: {e}", file=sys.stderr)
            return 3
    for p in (a.keyed, a.fills):
        if not p.is_file():
            ap.error(f"not found: {p}")
    try:
        rep = split(a.keyed, a.fills, a.out, a.overlap, a.far_arm)
    except Refused as e:
        print(f"layer_split.py: refused: {e}", file=sys.stderr)
        return 1
    if a.psb:
        sys.path.insert(0, str(HERE))
        import psd_write
        psd_write.write_manifest(a.out / "manifest.json", a.out / a.psb)
    print(json.dumps({"pass": rep["pass"], "out": str(a.out),
                      "gates": {g["name"]: g["value"] for g in rep["gates"]}}))
    return 0 if rep["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
