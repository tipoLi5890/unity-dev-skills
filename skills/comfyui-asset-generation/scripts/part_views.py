#!/usr/bin/env python3
"""Part views for a character in parts (a parts/1 plan): crop each generated part from the four
clean views, paint the hidden neck as a shaded cylinder, redraw it sharp with Qwen-Image-Edit-2511,
gate it, remove the background, then run one Pixal3D multi-view job per part.

  part_views.py views    PLAN.parts.json --views CLEAN_DIR [--server URL] [--seeds 42,43,44] [--part head]
  part_views.py generate PLAN.parts.json [--server URL] [--part head]
  part_views.py --selftest          no network: plan rules, guide, gates, the Qwen graph

The plan comes from blender-character-rig `part_math.py plan`, which measures the anchor (neck band,
frame fit, crop boxes, keep masks). This script only reads those and writes its own keys: each part's
`views.dir`, `views.sheet`, `views.colours` and `generated`. It refuses a plan whose anchor file no
longer matches `anchor.glb_sha256` (a new anchor means `plan` again).

`views`, per part with `source: generate`:
  guide    the box crop of the clean view, kept where the keep mask says (the hood is removed by
           geometry, never by colour); the neck the hood hid is painted as a shaded cylinder from the
           anchor's neck slice; rows below the part's bottom (`clip_row`) are black; Lanczos to 1024.
  redraw   Qwen 2511 + Lightning at denoise 1.0 with the guide as both pictures (mesh-texture-paint's
           qwen_paint). Never a full-body reference (it re-proportions the face) and never partial
           denoise (it returns the blur). The back view has a prompt of its own (no face, no
           prompt_hint). The redraw is clipped flat at clip_row.
  gates    part.redraw_iou >= 0.90 against the guide's own silhouette; part.redraw_colour <= 0.06 of
           32x32 cells moved more than dE 20 from the guide (a face on the back of the head);
           part.neck_reach >= 0.85 of the neck span on the last row; part.neck_width in [0.8, 1.25]
           of the neck diameter; part.sharpness >= --sharpness-factor x the guide's. A failing view
           retries the next seed.
  clean    the four redraws through templates/four_view_background_removal_api.json; part.bg_area in
           [0.95, 1.05]. Writes views/<part>/{front,left,back,right}.png (the Pixal3D inputs and
           mesh-texture-paint's --concept), sheet.png (its --sheet), the gate report
           part_views.gate.json (gate/1) and the sampled hair and skin colours.

`generate`: templates/pixal3d_multiview_to_model_api.json per part at the plan's preset, then
inspect_glb.py. A part that carries hair (region head, or the source of a hair split) never takes
Large: its spikes shrink.

Exit codes: 0 done or selftest passed; 1 usage error or refused plan; 2 a gate failed (after the
seeds); 3 a server or job failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
CLIENT = HERE / "comfy_asset_client.py"
INSPECT = HERE / "inspect_glb.py"
BG_TEMPLATE = SKILL / "templates" / "four_view_background_removal_api.json"
MV_TEMPLATE = SKILL / "templates" / "pixal3d_multiview_to_model_api.json"
QWEN_DIR = SKILL.parent / "mesh-texture-paint" / "scripts"     # qwen_paint.py, one Qwen graph for both skills

VIEWS = ("front", "left", "back", "right")
BG_NODES = {"front": 10, "left": 20, "back": 30, "right": 40}       # LoadImage; +4 rgba, +6 mask, +8 black
MV_NODES = {"front": 801, "left": 802, "back": 803, "right": 804}
# image-to-3d-tuning.md presets: (186.target_face_count, 241.resolution, 288.value)
PRESETS = {"Small": (2000, 128, 1024), "Medium": (4000, 256, 1024), "Compact": (8000, 384, 1024),
           "Large": (20000, 768, 2048), "Template": (70000, 768, 2048), "Showcase": (700000, 768, 4096)}
TEMPLATE_PRESET = "Template"
TIERS = ("whole", "three", "fine", "custom")
REGIONS = ("body", "head", "hair", "hand.L", "hand.R", "eyes", "accessory")
REGIONS_BUILT = {"whole": {"body"}, "three": {"body", "head", "hair"}}
NAME = re.compile(r"^[a-z0-9_-]+$")

IOU_MIN, REACH_MIN, WIDTH_RANGE, BG_RANGE = 0.90, 0.85, (0.8, 1.25), (0.95, 1.05)
COLOUR_DE, COLOUR_SHARE = 20.0, 0.06      # 32x32 cells whose colour moved more than this; their share

LABEL = {"front": "front",
         "left": "left side (a true 90-degree profile; the face points to the left edge of the image)",
         "right": "right side (a true 90-degree profile; the face points to the right edge of the image)"}
NECK = ("Paint the shaded column under the head as a straight bare neck of the same skin, as wide as the column, "
        "reaching the bottom edge and cut flat there. No hood, no clothes. Keep the pure black background.")
# One prompt per region; the back view has its own, without the hint: a guide of hair over a skin column,
# asked for "the same face", is redrawn as a face.
PROMPT = {
    "head": ("Picture 1 is a blurry, low-resolution close-up of the head and hair of a stylized 3D game character "
             "on a pure black background, seen from the {label}. Picture 2 is the same image. Redraw Picture 1 as "
             "a sharp, high-resolution, finely detailed image of the same character's head{hint}: the same face, "
             "eyes, eyebrows, ears, skin tone and hair. Keep the exact view angle, silhouette, size and position of "
             "Picture 1, pixel for pixel; only add sharp detail. Same four-view turnaround style, soft even lighting, "
             "no cast shadows, no highlights. " + NECK + " Draw only this one head with its neck, no other views "
             "or copies."),
    "head/back": ("Picture 1 is a blurry, low-resolution view of the back of the head of a stylized 3D game character, "
                  "seen from directly behind, on a pure black background: the back of the hair, the backs of the ears "
                  "and the back of the neck. Picture 2 is the same image. Redraw Picture 1 as a sharp, high-resolution, "
                  "finely detailed image of the same back of the head: the same hair, ears and skin tone. The face is "
                  "on the other side of the head and is not visible: draw no face, no eyes, no nose, no mouth. Keep the "
                  "exact silhouette, size and position of Picture 1, pixel for pixel; only add sharp detail. Same "
                  "four-view turnaround style, soft even lighting, no cast shadows, no highlights. " + NECK +
                  " Draw only this one head, no other views or copies."),
}


def prompt_for(region: str, view: str, hint) -> str | None:
    if view == "back" and f"{region}/back" in PROMPT:
        return PROMPT[f"{region}/back"]
    tpl = PROMPT.get(region)
    return None if tpl is None else tpl.format(label=LABEL[view], hint=f", with {hint}" if hint else "")


class Refused(Exception):
    """The plan or an input is refused: exit 1."""


class JobFailed(Exception):
    """A server or job failure: exit 3."""


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1, never 2 (2 is a failed gate)."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


# ------------------------------------------------------------------------------------------ plan
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def carries_hair(part: dict, parts: list) -> bool:
    return part.get("region") == "head" or any(
        p.get("source") == "split" and p.get("from") == part.get("name") and p.get("region") == "hair" for p in parts)


def check_plan(plan: dict, plan_dir: Path, check_anchor=True) -> list:
    """Every parts/1 rule the tools hold beyond the schema; returns the generated parts or raises Refused."""
    if not isinstance(plan, dict) or plan.get("schema") != "parts/1":
        raise Refused("not a parts/1 plan (schema stamp missing or different)")
    if not isinstance(plan.get("character"), str) or not NAME.match(plan["character"]):
        raise Refused("character must match ^[a-z0-9_-]+$")
    tier = plan.get("tier")
    if tier not in TIERS:
        raise Refused(f"tier {tier!r} is not one of {TIERS}")
    if tier in ("fine", "custom"):
        raise Refused(f"tier {tier} is reserved, not built yet: the tools build whole and three")
    parts = plan.get("parts")
    if not isinstance(parts, list) or not parts:
        raise Refused("parts must be a non-empty list")
    names = [p.get("name") for p in parts]
    if len(set(names)) != len(names) or not all(isinstance(n, str) and NAME.match(n) for n in names):
        raise Refused("part names must be unique and match ^[a-z0-9_-]+$")
    by = {p["name"]: p for p in parts}
    for p in parts:
        if p.get("source") not in ("anchor", "generate", "split"):
            raise Refused(f"part {p['name']}: source must be anchor, generate or split")
        if p.get("region") not in REGIONS:
            raise Refused(f"part {p['name']}: region {p.get('region')!r} is not one of {REGIONS}")
        if p["region"] not in REGIONS_BUILT["three"]:
            raise Refused(f"part {p['name']}: region {p['region']} is reserved for tier fine, not built yet")
        if p["source"] == "split" and by.get(p.get("from"), {}).get("source") != "generate":
            raise Refused(f"part {p['name']}: a split needs `from` naming a generated part")
        if p["source"] == "generate":
            if p.get("preset") not in PRESETS:
                raise Refused(f"part {p['name']}: preset {p.get('preset')!r} is not one of {tuple(PRESETS)}")
            if p["preset"] == "Large" and carries_hair(p, parts):
                raise Refused(f"part {p['name']}: Large shrinks hair spikes; use Template or Showcase")
            if (p.get("views") or {}).get("source", "clean-views") != "clean-views":
                raise Refused(f"part {p['name']}: drawn part sheets are reserved, not built yet; the tools crop the clean views")
        mode = (p.get("seam") or {}).get("mode")
        if mode is not None and mode not in ("overlap", "bridge", "none"):
            raise Refused(f"part {p['name']}: seam.mode must be overlap, bridge or none")
        share = p.get("budget_share")
        if share is not None and not (isinstance(share, (int, float)) and 0 < share <= 1):
            raise Refused(f"part {p['name']}: budget_share must be in (0, 1]")
    if sum(1 for p in parts if p["source"] == "anchor") != 1:
        raise Refused("exactly one part has source: anchor")
    if sum(p.get("budget_share") or 0 for p in parts) > 1.0 + 1e-9:
        raise Refused("budget shares sum to more than 1")
    if {p["region"] for p in parts} != REGIONS_BUILT[tier]:
        raise Refused(f"tier {tier} takes the regions {sorted(REGIONS_BUILT[tier])}")
    gen = [p for p in parts if p["source"] == "generate"]
    if tier == "whole":
        return gen
    anchor = plan.get("anchor")
    if not isinstance(anchor, dict):
        raise Refused("anchor is required unless the tier is whole")
    for key in ("glb", "glb_sha256", "frame", "head_height", "neck"):
        if key not in anchor:
            raise Refused(f"anchor.{key} is missing: run part_math.py plan")
    if check_anchor:
        glb = plan_dir / anchor["glb"]
        if not glb.is_file():
            raise Refused(f"anchor GLB not found: {glb}")
        if sha256(glb) != anchor["glb_sha256"]:
            raise Refused("the anchor changed since the plan was made: run part_math.py plan again")
    for p in gen:
        v = p.get("views") or {}
        boxes, L = v.get("boxes"), v.get("box_side_px")
        if not isinstance(boxes, dict) or set(boxes) != set(VIEWS) or not isinstance(L, int) or L < 8:
            raise Refused(f"part {p['name']}: views.boxes and views.box_side_px come from part_math.py plan")
        rows = {(b[1], b[3]) for b in boxes.values()}
        if len(rows) != 1 or any(b[2] - b[0] != L or b[3] - b[1] != L for b in boxes.values()):
            raise Refused(f"part {p['name']}: every box is L x L on the same rows")
        if "seam" not in p or "part_bottom_y" not in p["seam"]:
            raise Refused(f"part {p['name']}: seam.part_bottom_y comes from part_math.py plan")
    return gen


def load_plan(path: Path, check_anchor=True):
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise Refused(f"cannot read the plan {path}: {e}")
    return plan, check_plan(plan, path.parent, check_anchor)


def save_plan(path: Path, plan: dict) -> None:
    path.write_text(json.dumps(plan, indent=1, sort_keys=False) + "\n", encoding="utf-8")


# ------------------------------------------------------------------------------------ geometry
def view_u(view: str, x: float, z: float) -> float:
    """Horizontal image axis of each view in the anchor's glTF frame (+Y up, front = +Z)."""
    return {"front": x, "back": -x, "left": -z, "right": z}[view]


class Frame:
    """Anchor units -> box pixels for one part and one view (part_math.py plan's frame fit)."""

    def __init__(self, plan: dict, part: dict, view: str):
        a = plan["anchor"]
        self.upp = float(a["frame"]["units_per_px"])
        self.off = a["frame"]["offset_px"][view]
        self.box = part["views"]["boxes"][view]
        self.L = int(part["views"]["box_side_px"])
        self.view = view

    def col(self, u: float) -> float:
        return self.off[0] + u / self.upp - self.box[0]

    def row(self, y: float) -> float:
        return self.off[1] - y / self.upp - self.box[1]


def part_geometry(plan: dict, part: dict, view: str, prior_lift: float) -> dict:
    """Rows and the neck span of one view, in box pixels."""
    a, seam = plan["anchor"], part["seam"]
    neck, fr = a["neck"], Frame(plan, part, view)
    r = float(neck["radius"])
    uc = view_u(view, neck["axis_xz"][0], neck["axis_xz"][1])
    top_y = neck["collar_top"] if neck.get("collar") and neck.get("collar_top") is not None else seam.get("cut_y", neck["band"][0])
    return {"clip_row": int(round(fr.row(seam["part_bottom_y"]))),
            "prior_top": int(math.floor(fr.row(top_y + prior_lift * a["head_height"]))),
            "collar_row": int(round(fr.row(top_y))),
            "chin_row": fr.row(neck["band"][1]),
            "span": (fr.col(uc - r), fr.col(uc + r)), "L": fr.L}


# --------------------------------------------------------------------------------------- images
def _np():
    import numpy as np
    return np


def crop_box(img, box):
    """Crop [x0, y0, x1, y1] from an HxW(xC) array, padding with black where the box leaves it."""
    np = _np()
    x0, y0, x1, y1 = box
    H, W = img.shape[:2]
    pad = max(0, -x0, -y0, x1 - W, y1 - H)
    widths = ((pad, pad), (pad, pad)) + ((0, 0),) * (img.ndim - 2)
    p = np.pad(img, widths)
    return p[y0 + pad:y1 + pad, x0 + pad:x1 + pad].copy()


def neck_colour(rgb, keep, g):
    """Median of the visible neck skin in the 6 rows just above the collar, inside the neck span."""
    np = _np()
    c0, c1 = int(math.floor(g["span"][0])), int(math.ceil(g["span"][1]))
    r1 = max(0, g["collar_row"])
    r0 = max(0, r1 - 6)
    sel = keep[r0:r1, max(c0, 0):max(c1, 0)]
    px = rgb[r0:r1, max(c0, 0):max(c1, 0)][sel]
    return np.median(px, axis=0) if len(px) >= 12 else None


def build_guide(rgb, keep, g, colour):
    """The Qwen guide in box pixels. Inside the neck span, from prior_top (a little above the anchor's
    collar top: the drawn hood sits higher than the low-res mesh's) to clip_row, a shaded cylinder fills
    what the keep mask dropped. Below the chin (the top of the neck band) only the neck span is kept;
    everything below clip_row is black. Returns (guide, silhouette, prior)."""
    np = _np()
    L = g["L"]
    c0, c1 = g["span"]
    cols = np.arange(L) + 0.5
    t = (cols - (c0 + c1) / 2) / max((c1 - c0) / 2, 1e-6)
    inside = np.abs(t) <= 1
    shade = 0.75 + 0.25 * np.sqrt(np.clip(1 - t * t, 0, 1))
    prior = np.zeros((L, L), bool)
    r0, r1 = max(0, g["prior_top"]), min(L, g["clip_row"])
    if r1 > r0:
        prior[r0:r1] = inside[None, :]
    prior &= ~keep                         # fill only what the keep mask dropped (the hood, the background)
    rn = max(0, int(math.ceil(g["chin_row"])))
    keep = keep.copy()
    keep[rn:, ~inside] = False             # below the chin only the neck remains: a hood the keep mask let through
    guide = rgb.copy()
    guide[~keep] = 0
    cyl = (np.asarray(colour, float)[None, :] * shade[:, None]).clip(0, 255).astype(np.uint8)
    rows = np.nonzero(prior.any(1))[0]
    for r in rows:
        guide[r, prior[r]] = cyl[prior[r]]
    sil = keep | prior
    guide[g["clip_row"]:] = 0
    sil[g["clip_row"]:] = False
    return guide, sil, prior


def upscale(arr, size=1024, mask=False):
    from PIL import Image
    np = _np()
    if mask:
        im = Image.fromarray(arr.astype(np.uint8) * 255).resize((size, size), Image.BILINEAR)
        return np.asarray(im) > 127
    return np.asarray(Image.fromarray(arr).resize((size, size), Image.LANCZOS))


def silhouette(rgb):
    """luma > 0.06, the largest component, holes filled."""
    np = _np()
    from scipy import ndimage as ndi
    f = rgb.astype(float) / 255
    m = (0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]) > 0.06
    m = ndi.binary_opening(m, iterations=1)
    lab, n = ndi.label(m)
    if n == 0:
        return m
    m = lab == (1 + int(np.argmax(ndi.sum(m, lab, range(1, n + 1)))))
    return ndi.binary_fill_holes(m)


def lapvar(rgb, mask):
    np = _np()
    from scipy import ndimage as ndi
    g = rgb.astype(float).mean(2) if rgb.ndim == 3 else rgb.astype(float)
    lap = ndi.laplace(g)
    m = ndi.binary_erosion(mask, iterations=6)
    return float(lap[m].var()) if m.sum() > 50 else 0.0


def srgb_lab(rgb):
    """CIELAB (D65) of 8-bit sRGB, shape (..., 3)."""
    np = _np()
    c = np.asarray(rgb, float) / 255
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def colour_moved(redraw, guide):
    """Share of 32x32 cells (inside both images) whose mean colour moved more than COLOUR_DE: a face
    drawn on the back of the head, hair turned to skin. Fine detail averages out at this scale."""
    np = _np()
    from PIL import Image
    r = np.asarray(Image.fromarray(redraw).resize((32, 32), Image.BOX))
    g = np.asarray(Image.fromarray(guide).resize((32, 32), Image.BOX))
    m = (r.max(2) > 40) & (g.max(2) > 40)
    if not m.any():
        return 1.0
    d = np.linalg.norm(srgb_lab(r) - srgb_lab(g), axis=2)[m]
    return float((d > COLOUR_DE).mean())


def iou(a, b):
    return float((a & b).sum() / max((a | b).sum(), 1))


def gate(name, value, limit, ok, **extra):
    return {"name": name, "value": None if value is None else round(float(value), 4), "limit": limit,
            "pass": bool(ok), **extra}


def view_gates(redraw, guide1024, sil1024, g, factor, view):
    """Gates of one redraw (already clipped) against its guide; returns (gates, mask)."""
    np = _np()
    s = 1024 / g["L"]
    clip = int(round(g["clip_row"] * s))
    m = silhouette(redraw)
    m[clip:] = False
    gates = [gate(f"part.redraw_iou.{view}", iou(m, sil1024), f">= {IOU_MIN}", iou(m, sil1024) >= IOU_MIN)]
    c0, c1 = g["span"][0] * s, g["span"][1] * s
    row = clip - 1
    a0, a1 = max(0, int(round(c0))), min(1024, int(round(c1)))
    reach = float(m[row, a0:a1].mean()) if a1 > a0 and 0 <= row < 1024 else 0.0
    gates.append(gate(f"part.neck_reach.{view}", reach, f">= {REACH_MIN}", reach >= REACH_MIN))
    width = 0.0
    centre = int(round((c0 + c1) / 2))
    if 0 <= row < 1024 and 0 <= centre < 1024 and m[row, centre]:
        line = m[row]
        lo = centre
        while lo > 0 and line[lo - 1]:
            lo -= 1
        hi = centre
        while hi < 1023 and line[hi + 1]:
            hi += 1
        width = (hi - lo + 1) / max(c1 - c0, 1e-6)
    gates.append(gate(f"part.neck_width.{view}", width, list(WIDTH_RANGE), WIDTH_RANGE[0] <= width <= WIDTH_RANGE[1]))
    moved = colour_moved(redraw, guide1024)
    gates.append(gate(f"part.redraw_colour.{view}", moved, f"<= {COLOUR_SHARE}", moved <= COLOUR_SHARE))
    both = m & sil1024
    lr, lg = lapvar(redraw, both), lapvar(guide1024, both)
    ratio = lr / max(lg, 1e-6)
    gates.append(gate(f"part.sharpness.{view}", ratio, f">= {factor}", ratio >= factor,
                      redraw_lapvar=round(lr, 2), guide_lapvar=round(lg, 2)))
    return gates, m


def colours(front, mask, chin_row_1024):
    """Hair = median of the top 10 % of silhouette rows; skin = the central 30 % of columns over
    0.55-0.70 of the head height (silhouette top to the chin)."""
    np = _np()
    rows = np.nonzero(mask.any(1))[0]
    cols = np.nonzero(mask.any(0))[0]
    if not len(rows):
        return None
    top = rows.min()
    chin = chin_row_1024 if chin_row_1024 > top else rows.max()
    hair_rows = slice(top, top + max(2, int(0.10 * (chin - top))))
    hair = np.median(front[hair_rows][mask[hair_rows]], axis=0)
    w = cols.max() - cols.min()
    cs = slice(int(cols.min() + 0.35 * w), int(cols.min() + 0.65 * w) + 1)
    rs = slice(int(top + 0.55 * (chin - top)), int(top + 0.70 * (chin - top)) + 1)
    skin = np.median(front[rs, cs][mask[rs, cs]], axis=0)
    hexc = lambda c: "#%02x%02x%02x" % tuple(int(round(x)) for x in c)
    return {"hair": hexc(hair), "skin": hexc(skin)}


def find_view(clean: Path, view: str, kind: str) -> Path:
    hits = [p for p in sorted(clean.glob("*.png")) if view in p.name.lower() and kind in p.name.lower()]
    if len(hits) != 1:
        raise Refused(f"--views: need exactly one *{view}*{kind}*.png in {clean}, found {len(hits)}")
    return hits[0]


# --------------------------------------------------------------------------------------- server
def client_mod():
    sys.path.insert(0, str(HERE))
    import comfy_asset_client as cac
    return cac


def server_base(server):
    cac = client_mod()
    return cac.resolve_server(server, cac.load_config(cac.DEFAULT_CONFIG))


def wait_idle(base: str, seconds: float) -> None:
    """Wait for an empty queue (shared servers): one job at a time, never queued behind another."""
    cac = client_mod()
    end = time.monotonic() + seconds
    while not cac.queue_empty(base):
        if time.monotonic() > end:
            raise JobFailed("the ComfyUI queue stayed busy; nothing submitted")
        time.sleep(15)


def free(base: str) -> None:
    cac = client_mod()
    if cac.queue_empty(base):
        cac.request(base, "/free", {"unload_models": True, "free_memory": True})


def run_client(workflow: Path, out_dir: Path, uploads, sets, server, keep_loaded, timeout=1800):
    cmd = [sys.executable, str(CLIENT), "--workflow", str(workflow), "--output-dir", str(out_dir),
           "--timeout-seconds", str(timeout)]
    for u in uploads:
        cmd += ["--upload", str(u)]
    for s in sets:
        cmd += ["--set", s]
    if server:
        cmd += ["--server", server]
    if keep_loaded:
        cmd.append("--keep-loaded")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise JobFailed(f"client exit {r.returncode}: {r.stderr[-500:]}")
    return json.loads(r.stdout)


def unique_copy(src: Path, dst_dir: Path, stem: str) -> Path:
    """Upload names carry a content hash: the server keeps the first file under a name."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{stem}_{sha256(src)[:8]}.png"
    shutil.copyfile(src, dst)
    return dst


# ---------------------------------------------------------------------------------------- views
def qwen():
    if not (QWEN_DIR / "qwen_paint.py").is_file():
        raise Refused("mesh-texture-paint is not installed beside this skill (its qwen_paint.py does the redraw)")
    sys.path.insert(0, str(QWEN_DIR))
    import qwen_paint
    return qwen_paint


def report(gates, **extra):
    ok = bool(gates) and all(g["pass"] for g in gates) and "refused" not in extra and "error" not in extra
    return {"schema": "gate/1", "tool": "part_views", "pass": ok, "ok": ok,
            "verdict": "green" if ok else "failed", "gates": gates, **extra}


def cmd_views(a) -> int:
    np = _np()
    from PIL import Image
    plan, gen = load_plan(a.plan)
    if a.part:
        gen = [p for p in gen if p["name"] == a.part]
        if not gen:
            raise Refused(f"--part {a.part}: no generated part of that name")
    if not gen:
        print(json.dumps({"parts": [], "note": "nothing to generate for this tier"}))
        return 0
    clean = {v: (find_view(a.views, v, "black"), find_view(a.views, v, "mask")) for v in VIEWS}
    seeds = [int(s) for s in a.seeds.split(",")]
    qp = qwen()
    models = qp.load_models(a.models)
    base = server_base(a.server)
    root = a.plan.parent
    work = {}
    all_gates = []
    # 1. guides and redraws for every part (one model family, kept loaded)
    for part in gen:
        vd = root / "views" / part["name"]
        vd.mkdir(parents=True, exist_ok=True)
        hint = part.get("prompt_hint")
        if prompt_for(part["region"], "front", hint) is None:
            raise Refused(f"part {part['name']}: no redraw prompt for region {part['region']}")
        geo, guides = {}, {}
        crops = {}
        for v in VIEWS:
            rgb = np.asarray(Image.open(clean[v][0]).convert("RGB"))
            crops[v] = crop_box(rgb, part["views"]["boxes"][v])
            g = part_geometry(plan, part, v, a.prior_lift)
            kp = root / (part["views"].get("keep") or {}).get(v, f"views/{part['name']}/keep_{v}.png")
            if not kp.is_file():
                raise Refused(f"keep mask missing: {kp} (part_math.py plan writes it)")
            keep = np.asarray(Image.open(kp).convert("L")) > 127
            if keep.shape != crops[v].shape[:2]:
                raise Refused(f"{kp}: {keep.shape} is not the box ({g['L']} px)")
            geo[v] = (g, keep)
        fg, fk = geo["front"]
        colour = neck_colour(crops["front"], fk, fg)
        if colour is None:
            colour = np.median(crops["front"][fk], axis=0)
        for v in VIEWS:
            g, keep = geo[v]
            guide, sil, prior = build_guide(crops[v], keep, g, colour)
            g1024, s1024 = upscale(guide), upscale(sil, mask=True)
            s1024[int(round(g["clip_row"] * 1024 / g["L"])):] = False
            Image.fromarray(g1024).save(vd / f"guide_{v}.png")
            guides[v] = (g1024, s1024, g)
        res = {}
        for v in VIEWS:
            g1024, s1024, g = guides[v]
            prompt = prompt_for(part["region"], v, hint)
            best = None
            for seed in seeds:
                out = vd / f"redraw_{v}_s{seed}.png"
                wait_idle(base, a.wait_idle)
                t0 = time.time()
                try:
                    qp.paint(vd / f"guide_{v}.png", vd / f"guide_{v}.png", prompt, out, base, seed,
                             keep_loaded=True, models=models)
                except RuntimeError as e:
                    raise JobFailed(str(e))
                dt = round(time.time() - t0, 1)
                rd = np.asarray(Image.open(out).convert("RGB")).copy()
                if rd.shape[:2] != (1024, 1024):
                    rd = np.asarray(Image.fromarray(rd).resize((1024, 1024), Image.LANCZOS)).copy()
                rd[int(round(g["clip_row"] * 1024 / g["L"])):] = 0
                gates, m = view_gates(rd, g1024, s1024, g, a.sharpness_factor, v)
                passed = all(x["pass"] for x in gates)
                print(json.dumps({"part": part["name"], "view": v, "seed": seed, "seconds": dt,
                                  "gates": {x["name"]: x["value"] for x in gates}, "pass": passed}), flush=True)
                score = (passed, gates[0]["value"])
                if best is None or score > best[0]:
                    best = (score, seed, rd, gates, m)
                if passed:
                    break
            _, seed, rd, gates, m = best
            for x in gates:
                x["seed"] = seed
            Image.fromarray(rd).save(vd / f"redraw_{v}.png")
            res[v] = (rd, m)
            all_gates += gates
            if not best[0][0]:
                save_report(vd, report(all_gates, part=part["name"],
                                       failed_view=v, note=f"every seed {seeds} failed"))
                free(base)
                print(f"part {part['name']} view {v}: gates failed for every seed: "
                      + ", ".join(x["name"] for x in gates if not x["pass"]), file=sys.stderr)
                return 2
        work[part["name"]] = (part, vd, res, guides)
    free(base)        # model-family switch: Qwen -> BiRefNet
    # 2. background removal, one four-view job per part
    for name, (part, vd, res, guides) in work.items():
        up, sets = [], []
        for v in VIEWS:
            u = unique_copy(vd / f"redraw_{v}.png", vd / "upload", f"{plan['character']}_{name}_{v}_r")
            up.append(u)
            n = BG_NODES[v]
            sets += [f"{n}.image={u.name}", f"{n + 4}.filename_prefix=parts/{plan['character']}_{name}_{v}_rgba",
                     f"{n + 6}.filename_prefix=parts/{plan['character']}_{name}_{v}_mask",
                     f"{n + 8}.filename_prefix=parts/{plan['character']}_{name}_{v}_black"]
        bgdir = vd / "bg"
        if bgdir.exists():
            shutil.rmtree(bgdir)
        wait_idle(base, a.wait_idle)
        run_client(BG_TEMPLATE, bgdir, up, sets, a.server or base, keep_loaded=False)
        tiles = []
        for v in VIEWS:
            outs = sorted(bgdir.rglob("*.png"))
            blk = [p for p in outs if f"_{name}_{v}_black" in p.name]
            msk = [p for p in outs if f"_{name}_{v}_mask" in p.name]
            if len(blk) != 1 or len(msk) != 1:
                raise JobFailed(f"background removal: no single black/mask output for {v}")
            bm = np.asarray(Image.open(msk[0]).convert("L")) > 127
            area = float(bm.sum() / max(res[v][1].sum(), 1))
            all_gates.append(gate(f"part.bg_area.{v}", area, list(BG_RANGE), BG_RANGE[0] <= area <= BG_RANGE[1]))
            shutil.copyfile(blk[0], vd / f"{v}.png")
            tiles.append(Image.open(blk[0]).convert("RGB"))
        sheet = Image.new("RGB", (1024 * 4, 1024))
        for i, t in enumerate(tiles):
            sheet.paste(t.resize((1024, 1024)), (1024 * i, 0))
        sheet.save(vd / "sheet.png")
        g = guides["front"][2]
        front = np.asarray(tiles[0].resize((1024, 1024)))
        col = colours(front, silhouette(front), g["chin_row"] * 1024 / g["L"])
        part["views"].update({"dir": f"views/{name}", "sheet": f"views/{name}/sheet.png", "colours": col})
    rep = report(all_gates, parts=list(work))
    for name, (part, vd, _, _) in work.items():
        save_report(vd, rep)
    save_plan(a.plan, plan)
    print(json.dumps({"pass": rep["pass"], "parts": list(work), "failed": [x["name"] for x in all_gates if not x["pass"]]}))
    return 0 if rep["pass"] else 2


def save_report(vd: Path, rep: dict) -> None:
    (vd / "part_views.gate.json").write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")


def cmd_generate(a) -> int:
    plan, gen = load_plan(a.plan)
    if a.part:
        gen = [p for p in gen if p["name"] == a.part]
        if not gen:
            raise Refused(f"--part {a.part}: no generated part of that name")
    base = server_base(a.server)
    root = a.plan.parent
    failed = []
    for i, part in enumerate(gen):
        name = part["name"]
        vd = root / (part["views"].get("dir") or f"views/{name}")
        views = {v: vd / f"{v}.png" for v in VIEWS}
        missing = [str(p) for p in views.values() if not p.is_file()]
        if missing:
            raise Refused(f"part {name}: run `views` first ({missing[0]} is missing)")
        faces, _, tex = PRESETS[part["preset"]]
        gd = root / "gen" / name
        up, sets = [], []
        for v, p in views.items():
            u = unique_copy(p, gd / "upload", f"{plan['character']}_{name}_{v}")
            up.append(u)
            sets.append(f"{MV_NODES[v]}.image={u.name}")
        if part["preset"] != TEMPLATE_PRESET:
            f, res, t = PRESETS[part["preset"]]
            sets += [f"186.target_face_count={f}", f"241.resolution={res}", f"288.value={t}"]
        sets.append(f"322.filename_prefix=parts/{plan['character']}_{name}")
        out = gd / "out"
        wait_idle(base, a.wait_idle)
        t0 = time.time()
        r = run_client(MV_TEMPLATE, out, up, sets, a.server or base, keep_loaded=i < len(gen) - 1,
                       timeout=a.timeout)
        glbs = [Path(p) for p in r.get("outputs", []) if str(p).endswith(".glb")]
        if len(glbs) != 1:
            raise JobFailed(f"part {name}: expected one GLB, got {len(glbs)}")
        glb = gd / f"{name}.glb"
        shutil.copyfile(glbs[0], glb)
        (gd / "client.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
        ins = subprocess.run([sys.executable, str(INSPECT), str(glb), "--max-triangles", str(faces),
                              "--texture-size", str(tex), "--json-out", str(gd / "inspect.gate.json")],
                             capture_output=True, text=True)
        part["generated"] = {**(part.get("generated") or {}), "glb": str(glb.relative_to(root))}
        print(json.dumps({"part": name, "preset": part["preset"], "seconds": round(time.time() - t0, 1),
                          "server_seconds": r.get("elapsed_seconds"), "vram_free_min": r.get("vram_free_min"),
                          "glb": str(glb), "inspect_exit": ins.returncode}), flush=True)
        if ins.returncode != 0:
            failed.append(name)
    save_plan(a.plan, plan)
    free(base)
    return 2 if failed else 0


# ------------------------------------------------------------------------------------- selftest
def _synthetic(tmp: Path):
    """A synthetic clean view set, anchor stand-in, plan and keep masks (the plan's job, done by hand)."""
    np = _np()
    from PIL import Image, ImageDraw
    upp, off = 0.001, [512.0, 512.0]
    head_c, head_r = 0.41, 0.075                 # anchor units
    neck = {"band": [0.33, 0.34], "axis_xz": [0.0, 0.0], "radius": 0.03, "collar": True, "collar_top": 0.345}
    head_h = 0.49 - neck["band"][1]
    cut_y = 0.332
    bottom = neck["band"][0] - 0.1 * head_h
    row = lambda y: off[1] - y / upp
    clean = tmp / "clean"
    clean.mkdir()
    keeps = {}
    for v in VIEWS:
        im = Image.new("RGB", (1024, 1024))
        d = ImageDraw.Draw(im)
        d.ellipse([512 - 120, row(0.36), 512 + 120, row(-0.45)], fill=(40, 170, 190))          # body
        d.rectangle([512 - 30, row(0.36), 512 + 30, row(0.30)], fill=(200, 150, 120))          # neck
        d.ellipse([512 - 75, row(head_c + head_r), 512 + 75, row(head_c - head_r)], fill=(225, 175, 140))
        d.pieslice([512 - 75, row(head_c + head_r), 512 + 75, row(head_c - head_r)], 180, 360, fill=(70, 50, 40))
        d.rectangle([512 - 90, row(neck["collar_top"]), 512 + 90, row(0.30)], fill=(40, 170, 190))   # collar
        rgb = np.asarray(im)
        im.save(clean / f"c_{v}_black_00001_.png")
        Image.fromarray(((rgb.max(2) > 0) * 255).astype(np.uint8)).save(clean / f"c_{v}_mask_00001_.png")
        k = Image.new("L", (1024, 1024))
        dk = ImageDraw.Draw(k)
        dk.ellipse([512 - 75, row(head_c + head_r), 512 + 75, row(head_c - head_r)], fill=255)
        dk.rectangle([512 - 90, row(neck["collar_top"]), 512 + 90, row(0.30)], fill=0)   # the plan drops the collar
        keeps[v] = np.asarray(k) > 127
    top_row = row(0.49) - 2
    bot_row = row(bottom)
    L = int(math.ceil(1.1 * max(bot_row - top_row, 150) / 2) * 2)
    cy = (top_row + bot_row) / 2
    boxes = {v: [int(round(512 - L / 2)), int(round(cy - L / 2)), int(round(512 - L / 2)) + L, int(round(cy - L / 2)) + L]
             for v in VIEWS}
    (tmp / "views" / "head").mkdir(parents=True)
    for v in VIEWS:
        k = crop_box(keeps[v], boxes[v])
        Image.fromarray((k * 255).astype(np.uint8)).save(tmp / "views" / "head" / f"keep_{v}.png")
    anchor = tmp / "anchor.glb"
    anchor.write_bytes(b"glTF synthetic anchor stand-in")
    plan = {
        "schema": "parts/1", "character": "courier", "tier": "three",
        "anchor": {"glb": "anchor.glb", "glb_sha256": sha256(anchor),
                   "frame": {"units_per_px": upp, "offset_px": {v: off for v in VIEWS},
                             "iou": {v: 0.95 for v in VIEWS}},
                   "bbox_min": [-0.36, -0.49, -0.1], "bbox_max": [0.36, 0.49, 0.1],
                   "head_height": round(head_h, 4), "neck": neck},
        "parts": [
            {"name": "body", "source": "anchor", "region": "body", "budget_share": 0.6},
            {"name": "head", "source": "generate", "region": "head", "preset": "Template",
             "prompt_hint": "short dark hair, bare neck",
             "region_box": {"y_min": round(bottom, 4), "y_max": 0.49},
             "seam": {"mode": "overlap", "cut_y": cut_y, "part_bottom_y": round(bottom, 4), "margin_frac": 0.1},
             "views": {"source": "clean-views", "box_side_px": L, "boxes": boxes,
                       "keep": {v: f"views/head/keep_{v}.png" for v in VIEWS}},
             "budget_share": 0.25},
            {"name": "hair", "source": "split", "from": "head", "region": "hair",
             "split": {"method": "scalp-radius", "delta": 0.03}, "budget_share": 0.15},
        ],
    }
    return plan, clean


def contract_out(name: str, doc: dict) -> None:
    """Hand one selftest sample to tools/check-contracts.py: written to $UNITY_DEV_CONTRACT_OUT (else a
    fixed folder in the temp dir) and named on stdout as `selftest-output: <path>`."""
    out = os.environ.get("UNITY_DEV_CONTRACT_OUT") or os.path.join(tempfile.gettempdir(), "unity-dev-contract-out")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1)
    print(f"selftest-output: {path}")


def selftest() -> int:
    np = _np()
    from PIL import Image
    from scipy import ndimage as ndi
    checks = {}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        plan, clean = _synthetic(tmp)
        pf = tmp / "courier.parts.json"
        save_plan(pf, plan)
        _, gen = load_plan(pf)
        checks["plan_valid"] = [p["name"] for p in gen] == ["head"]

        def refused(mut):
            p = json.loads(json.dumps(plan))
            mut(p)
            try:
                check_plan(p, tmp)
                return False
            except Refused:
                return True
        checks["refuse_fine"] = refused(lambda p: p.update(tier="fine"))
        checks["refuse_hand"] = refused(lambda p: p["parts"].append({"name": "hand_r", "source": "generate",
                                                                    "region": "hand.R", "preset": "Template"}))
        checks["refuse_large_hair"] = refused(lambda p: p["parts"][1].update(preset="Large"))
        checks["refuse_two_anchors"] = refused(lambda p: p["parts"][1].update(source="anchor"))
        checks["refuse_split_from_anchor"] = refused(lambda p: p["parts"][2].update({"from": "body"}))
        checks["refuse_stale_anchor"] = refused(lambda p: p["anchor"].update(glb_sha256="0" * 64))
        checks["refuse_box_rows"] = refused(lambda p: p["parts"][1]["views"]["boxes"]["left"].__setitem__(1, 3))
        checks["refuse_shares"] = refused(lambda p: p["parts"][0].update(budget_share=0.9))
        checks["refuse_drawn_sheet"] = refused(lambda p: p["parts"][1]["views"].update(source="sheet"))
        boxes = plan["parts"][1]["views"]["boxes"]
        checks["boxes_share_L_and_rows"] = len({(b[1], b[3], b[2] - b[0]) for b in boxes.values()}) == 1
        # guide: the neck prior lands inside the projected span, below the collar, above clip_row
        part = plan["parts"][1]
        rgb = np.asarray(Image.open(find_view(clean, "front", "black")).convert("RGB"))
        crop = crop_box(rgb, boxes["front"])
        keep = np.asarray(Image.open(tmp / "views/head/keep_front.png")) > 127
        g = part_geometry(plan, part, "front", 0.1)
        colour = neck_colour(crop, keep, g)
        colour = np.median(crop[keep], axis=0) if colour is None else colour
        guide, sil, prior = build_guide(crop, keep, g, colour)
        cols = np.nonzero(prior.any(0))[0]
        rows = np.nonzero(prior.any(1))[0]
        checks["prior_in_span"] = bool(len(cols)) and cols.min() >= math.floor(g["span"][0]) \
            and cols.max() <= math.ceil(g["span"][1]) and rows.max() < g["clip_row"] and rows.min() >= g["prior_top"]
        checks["prior_reaches_clip_row"] = bool(len(rows)) and rows.max() == g["clip_row"] - 1
        checks["no_collar_left"] = not (np.abs(guide.astype(int) - [40, 170, 190]).sum(2) < 30).any()
        checks["black_below_clip"] = not guide[g["clip_row"]:].any()
        # a keep mask that still holds the collar (projection without depth): below the chin only the
        # neck span is kept
        leaky = keep | (np.abs(crop.astype(int) - [40, 170, 190]).sum(2) < 30)
        guide_l, _, _ = build_guide(crop, leaky, g, colour)
        teal = np.abs(guide_l.astype(int) - [40, 170, 190]).sum(2) < 30
        c0i, c1i = int(math.floor(g["span"][0])), int(math.ceil(g["span"][1]))
        checks["leaky_keep_below_chin"] = not teal[int(math.ceil(g["chin_row"])):, :c0i].any() \
            and not teal[int(math.ceil(g["chin_row"])):, c1i + 1:].any()
        g1024, s1024 = upscale(guide), upscale(sil, mask=True)
        clip = int(round(g["clip_row"] * 1024 / g["L"]))
        s1024[clip:] = False
        # an ideal redraw: the guide with fine detail added inside its silhouette
        rng = np.random.default_rng(3)
        tex = rng.integers(-60, 60, size=(1024, 1024, 1))
        ideal = np.where(s1024[..., None], np.clip(g1024.astype(int) + tex, 30, 255), 0).astype(np.uint8)
        gates, _ = view_gates(ideal, g1024, s1024, g, 5.0, "front")
        checks["ideal_passes"] = all(x["pass"] for x in gates)
        # a C-shaped neck: the bottom clipped diagonally across the span
        cshape = ideal.copy()
        c0, c1 = g["span"][0] * 1024 / g["L"], g["span"][1] * 1024 / g["L"]
        yy, xx = np.mgrid[0:1024, 0:1024]
        cshape[(yy > clip - 1 - (xx - c0) * 0.9) & (xx > c0 + 0.3 * (c1 - c0)) & (yy < clip)] = 0
        gates_c, _ = view_gates(cshape, g1024, s1024, g, 5.0, "front")
        checks["c_neck_fails_reach"] = not next(x for x in gates_c if x["name"].startswith("part.neck_reach"))["pass"]
        faced = ideal.copy()
        hy, hx = np.nonzero(s1024)
        faced[(yy > hy.min()) & (yy < hy.min() + 0.5 * (hy.max() - hy.min())) & s1024] = (230, 180, 150)
        gates_f, _ = view_gates(faced, g1024, s1024, g, 5.0, "front")
        checks["recoloured_fails_colour"] = not next(x for x in gates_f if x["name"].startswith("part.redraw_colour"))["pass"]
        blurred = np.stack([ndi.gaussian_filter(g1024[..., c].astype(float), 2) for c in range(3)], -1).astype(np.uint8)
        gates_b, _ = view_gates(blurred, g1024, s1024, g, 5.0, "front")
        checks["blur_fails_sharpness"] = not next(x for x in gates_b if x["name"].startswith("part.sharpness"))["pass"]
        col = colours(np.asarray(Image.fromarray(ideal)), silhouette(ideal), g["chin_row"] * 1024 / g["L"])
        checks["colours_sampled"] = bool(col) and all(re.fullmatch(r"#[0-9a-f]{6}", c) for c in col.values())
        rep = report(gates, part="head")
        checks["report_gate1"] = rep["schema"] == "gate/1" and rep["pass"] is rep["ok"] is True
        # the Qwen graph: picture 1 = picture 2 = the guide, denoise 1
        if (QWEN_DIR / "qwen_paint.py").is_file():
            qp = qwen()
            gr = qp.graph("guide.png", "guide.png", "p", seed=1)
            loads = [n["inputs"]["image"] for n in gr.values() if n["class_type"] == "LoadImage"]
            ks = next(n for n in gr.values() if n["class_type"] == "KSampler")["inputs"]
            checks["qwen_self_reference"] = loads == ["guide.png", "guide.png"] and ks["denoise"] == 1.0
        else:
            print("SKIP qwen graph: mesh-texture-paint is not installed beside this skill")
        back = prompt_for("head", "back", "a young face")
        checks["back_prompt_no_face"] = "draw no face" in back and "young face" not in back \
            and "profile" in prompt_for("head", "left", None) and "{" not in prompt_for("head", "front", "x")
        sample = json.loads(json.dumps(plan))
        sample["anchor"]["glb"] = "../../sources/courier_anchor.glb"
        sample["parts"][1]["views"].update({"dir": "views/head", "sheet": "views/head/sheet.png",
                                            "colours": col})
        sample["parts"][1]["generated"] = {"glb": "gen/head/head.glb"}
        contract_out("part_views__courier.parts.json", sample)
        contract_out("part_views__views.gate.json", rep)
    checks = {k: bool(v) for k, v in checks.items()}
    ok = all(checks.values())
    print(json.dumps({"checks": checks, "pass": ok}))
    return 0 if ok else 2


# ----------------------------------------------------------------------------------------- main
def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["--selftest"], ["selftest"]):
        return selftest()
    ap = UsageParser(prog="part_views.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="plan rules, guide, gates and the Qwen graph; no network")
    sub = ap.add_subparsers(dest="cmd", parser_class=UsageParser)
    v = sub.add_parser("views", help="crops, neck prior, Qwen redraw, gates, background removal")
    v.add_argument("plan", type=Path)
    v.add_argument("--views", type=Path, required=True, help="the clean four views: *front*black*.png, *front*mask*.png, ...")
    v.add_argument("--seeds", default="42,43,44", help="a failing view retries the next seed")
    v.add_argument("--sharpness-factor", type=float, default=5.0, help="redraw Laplacian variance over the guide's")
    v.add_argument("--prior-lift", type=float, default=0.1,
                   help="the neck prior starts this fraction of head height above the collar top")
    v.add_argument("--models", help="JSON file or inline JSON: unet/clip/vae/lora file names (qwen_paint)")
    gn = sub.add_parser("generate", help="one Pixal3D multi-view job per generated part, then inspect_glb")
    gn.add_argument("plan", type=Path)
    gn.add_argument("--timeout", type=float, default=1800)
    for p in (v, gn):
        p.add_argument("--server", default=None, help="ComfyUI URL (else COMFYUI_SERVER_URL, else the client config)")
        p.add_argument("--part", help="only this part")
        p.add_argument("--wait-idle", type=float, default=900, help="seconds to wait for an empty queue before each job")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.cmd:
        ap.error("a command is required: views, generate or --selftest")
    if a.cmd == "views":
        try:
            seeds = [int(s) for s in a.seeds.split(",")]
        except ValueError:
            ap.error("--seeds takes comma-separated integers")
        if not seeds:
            ap.error("--seeds is empty")
        if not a.views.is_dir():
            ap.error(f"--views: not a folder: {a.views}")
    try:
        return cmd_views(a) if a.cmd == "views" else cmd_generate(a)
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    except JobFailed as e:
        print(f"job failed: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
