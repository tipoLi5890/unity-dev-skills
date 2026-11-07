#!/usr/bin/env python3
"""Repaint the base colour of an image-to-3D mesh view by view, guided by concept art.

Each step renders the mesh from one camera and has the edit model paint that view (picture 1
the render, picture 2 one reference). The first view is a plain clay render with the
turnaround sheet. Every later view is a context render: what is painted so far in colour,
unpainted surface showing a prior (by default the GLB's own texture, brightness-matched to the
painted texels), which the model repaints to match the reference. The output is registered to
the render silhouette, gated (silhouette IoU, outline distance, painted share, brightness drift,
dark-to-light share, background deviation; colours off the concept's palette when --max-off-palette
is set, else only reported) and its painted
pixels are projected into the UV texture. Anchor cameras go first, then the camera that sees the most unpainted surface
(zoomed onto it unless the mesh is thin or, for objects, the view is steep; never within 35
degrees of a next-best camera whose paint was rejected), until coverage, the view budget, three
next-best views rejected in a row (a rejected anchor does not count) or three next-best views in a
row with nothing unpainted stop the loop; optional detail passes follow.
Up to --tries seeds per camera: the sheet (composed from the concept views when --sheet is not
given) first and again after a try that failed other gates, the nearest concept view, fitted onto
the guide's silhouette box, after a try that failed IoU or the outline; an unzoomed camera within
45 degrees of the back and 15 of level starts with the back view and falls back to the sheet. --detail-tries seeds per
head detail pass, alternating between the front concept view and that view cut to the head (a
--detail-ref is used as given). report.json lists every try with its gate values and the gates it
failed.

Writes <out>/basecolor.png, <out>/<glb-stem>_painted.glb (the input GLB with only the base
colour image replaced), <out>/coverage.png, <out>/turntable.png, <out>/report.json,
<out>/gates.json, <out>/views/ (guides, outputs, aligned) and <out>/state.npz (continue with
--resume).

gates.json is a gate/1 report (schemas/gate-1.json) that `art-asset-registry` ingests: gates
paint.coverage (coverage_seeable >= --min-coverage, with its margin; the default floor follows
--coverage-for: character 0.85, prop 0.75, part none, so a part's coverage is only reported),
paint.seam_delta and paint.views_refused (reported only). A reported-only gate has limit null,
pass true and "report_only": true. Its `path` is the painted GLB and its `record` names the tool,
the painted files, the inputs (the GLB, the sheet, the concept views) and the params (the seed of
every used view, the models). A failed gate shows in gates.json and on one stderr line; the exit
code stays the run's. --min-coverage takes a share in (0, 1]. A run removes an earlier gates.json
from --out first, so a run that paints nothing (exit 3) leaves none.

  python3 paint_loop.py runner.glb --concept concept/ --sheet turnaround.png --out paint/
  python3 paint_loop.py --selftest      the whole loop offline on a cube with a fake painter

Exit codes: 0 done or selftest passed, 1 usage error (also a GLB whose base colour cannot be
written, caught before any paint job), 2 selftest failed, 3 no view painted (stderr says when every try
failed a gate) or the paint server unreachable / not configured (the run stops at the first such error; views painted before it are
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


# Between the shared:gate_margin markers: a copy of tools/shared-blocks/gate_margin.py;
# check-consistency keeps every copy equal.
# >>> shared:gate_margin
def gate_margin(value, limit, op=None):
    """A gate's signed distance to its limit (gate/1 `margin`, schemas/README.md): positive is safe,
    negative is failing, 0 sits on the limit. op "<=": (L - v) / |L|; ">=": (v - L) / |L|; "range"
    (limit [lo, hi]): min(v - lo, hi - v) / ((hi - lo) / 2). A zero |L| or hi - lo keeps the plain
    difference. With op None a string limit such as "<= 0.08" or ">= 0.9" gives both. None when the
    value or limit is a bool, a string, not finite, or the op is not known: write no margin then."""
    import math

    def num(x):
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            return None
        return float(x) if math.isfinite(x) else None

    if op is None and isinstance(limit, str):
        s = limit.strip()
        for o in ("<=", ">="):
            if s.startswith(o):
                try:
                    op, limit = o, float(s[len(o):].strip())
                except ValueError:
                    return None
                break
    v = num(value)
    if v is None:
        return None
    if op == "range":
        if not isinstance(limit, (list, tuple)) or len(limit) != 2:
            return None
        lo, hi = num(limit[0]), num(limit[1])
        if lo is None or hi is None or hi < lo:
            return None
        d = min(v - lo, hi - v)
        half = (hi - lo) / 2
        m = d / half if half > 0 else d
    elif op in ("<=", ">="):
        lim = num(limit)
        if lim is None:
            return None
        d = lim - v if op == "<=" else v - lim
        m = d / abs(lim) if lim != 0 else d
    else:
        return None
    return round(m, 4) if math.isfinite(m) else None
# <<< shared:gate_margin


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


def figure_on_black(path, tol=12):
    """(RGB on black, figure mask) of a concept view: an RGBA cut-out over black, else everything but
    the background, the pixels within tol of the border's median colour that connect to the border
    (a white shirt on a white page stays figure)."""
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
        rgba = np.asarray(im.convert("RGBA")).astype(np.float64)
        rgb = rgba[..., :3] * rgba[..., 3:] / 255.0
        return rgb.astype(np.uint8), rgba[..., 3] > 127
    a = np.asarray(im.convert("RGB")).astype(np.float64)
    bg = np.median(np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]), 0)
    near = np.abs(a - bg).max(2) <= tol
    lab, _ = ndimage.label(near)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    m = ndimage.binary_opening(~np.isin(lab, edge[edge > 0]), iterations=1)
    return np.where(m[..., None], a, 0).astype(np.uint8), m


def compose_sheet(paths, dst, height=512, pad=24):
    """A turnaround sheet from the concept views (front, left, back, right in that order): each
    figure cut to its own width and to the views' common top and bottom, all at one scale, side by
    side on black with a gap. For a run without --sheet: a single concept view as picture 2 makes
    the edit model redraw that drawing (its framing and scale) instead of painting the guide in
    place, so the sheet stays the first reference. Returns dst, or None with fewer than two views."""
    paths = [p for p in paths if Path(p).is_file()]
    size = Image.open(paths[0]).size if paths else None
    figs = []
    for p in paths:   # one pixel grid for all views, so the common top and bottom mean the same rows
        rgb, m = figure_on_black(p)
        if rgb.shape[1::-1] != size:
            rgb = np.asarray(Image.fromarray(rgb).resize(size, Image.LANCZOS))
            m = np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize(size, Image.NEAREST)) > 127
        figs.append((rgb, m))
    figs = [(rgb, m) for rgb, m in figs if m.any()]
    if len(figs) < 2:
        return None
    top = min(int(np.nonzero(m.any(1))[0][0]) for _, m in figs)
    bot = max(int(np.nonzero(m.any(1))[0][-1]) + 1 for _, m in figs)
    s = (height - 2 * pad) / max(1, bot - top)
    cells = []
    for rgb, m in figs:
        xs = np.nonzero(m.any(0))[0]
        crop = Image.fromarray(rgb[top:bot, xs[0]:xs[-1] + 1])
        cells.append(crop.resize((max(1, round(crop.width * s)), max(1, round(crop.height * s))), Image.LANCZOS))
    sheet = Image.new("RGB", (sum(c.width for c in cells) + pad * (len(cells) + 1), height))
    x = pad
    for c in cells:
        sheet.paste(c, (x, pad))
        x += c.width + pad
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dst)
    return Path(dst)


def fit_reference(concept, guide_mask, dst):
    """The concept view scaled and placed so its figure's box matches the guide silhouette's box (one
    scale, from the box's longer side), on black at the guide's size. A single view as picture 2 makes
    the model redraw that drawing at the drawing's own framing; framed like the guide, the redraw
    lands on the render instead of beside it. For unzoomed views. Returns dst, or None when either
    image holds no figure."""
    rgb, m = figure_on_black(concept)
    if not m.any() or not guide_mask.any():
        return None
    ys, xs = np.nonzero(m)
    gy, gx = np.nonzero(guide_mask)
    ch, cw = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
    gh, gw = gy.max() - gy.min() + 1, gx.max() - gx.min() + 1
    s = gh / ch if ch >= cw else gw / cw
    crop = Image.fromarray(rgb[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
    crop = crop.resize((max(1, round(cw * s)), max(1, round(ch * s))), Image.LANCZOS)
    canvas = Image.new("RGB", (guide_mask.shape[1], guide_mask.shape[0]))
    cx, cy = (gx.min() + gx.max() + 1) / 2, (gy.min() + gy.max() + 1) / 2
    canvas.paste(crop, (round(cx - crop.width / 2), round(cy - crop.height / 2)))
    canvas.save(dst)
    return Path(dst)


HEAD_TOP, HEAD_DROP, HEAD_MARGIN = 0.16, 0.02, 1.3   # the head detail camera, on the mesh and on the drawing


def head_reference(concept, dst, size=1024, fill=0.92):
    """The concept view cut to the frame the head detail camera sees: the top HEAD_TOP of the figure's
    height, its centre HEAD_DROP of the height lower, HEAD_MARGIN x its half-extent over fill. Picture 2
    for every other head detail try: a whole-body view makes the model redraw the head larger and
    higher, a head framed like the guide often lands on it. Returns dst, or None without a figure."""
    rgb, m = figure_on_black(concept)
    if not m.any():
        return None
    rows = np.nonzero(m.any(1))[0]
    y0, h = int(rows[0]), int(rows[-1] + 1 - rows[0])
    sy, sx = np.nonzero(m[y0:y0 + max(1, int(round(HEAD_TOP * h)))])
    cy = y0 + (sy.min() + sy.max() + 1) / 2 + HEAD_DROP * h
    cx = (sx.min() + sx.max() + 1) / 2
    half = max(sy.max() - sy.min() + 1, sx.max() - sx.min() + 1) / 2 * HEAD_MARGIN / fill
    box = tuple(int(round(v)) for v in (cx - half, cy - half, cx + half, cy + half))
    Image.fromarray(rgb).crop(box).resize((size, size), Image.LANCZOS).save(dst)
    return Path(dst)


OUTLINE_GATES = {"iou", "edge"}   # failed by a collage or a figure the model moved
BACK_SECTOR = 45.0                # degrees from the back within which an unzoomed camera starts with the back view
BACK_PITCH = 15.0                 # ... when it looks within this many degrees of level


def back_camera(yaw, zoomed, pitch=0.0):
    """An unzoomed, near-level camera within BACK_SECTOR of the back: its first reference is the back
    concept view framed like the guide, not the sheet. Given the sheet, the edit model often paints the
    front (face, buttons, emblem) onto a render seen from behind; the colours match, so no gate catches
    it. A steep camera keeps the sheet first: the level back drawing does not fit its silhouette (IoU
    about 0.6), so every try of it is refused."""
    d = abs(yaw % 360 - 180)
    return not zoomed and d < BACK_SECTOR and abs(pitch) <= BACK_PITCH


def next_reference(order, t, tries):
    """Picture 2 for try t of a main view: the first reference again after a try of it that failed only
    other gates (a washed-out key, drift, silver: another seed fixes those); the other reference after
    a try of the first that failed IoU or the outline (a collage, a moved figure), and the first again
    after that. tries: this camera's earlier tries (report.json tries)."""
    if t == 0 or len(order) < 2:
        return order[0]
    last = tries[-1] if tries else None
    return order[1] if last and last["ref"] == order[0] and OUTLINE_GATES & set(last["fails"]) else order[0]


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


OFFPAL_PICTURE = 0.015   # a try flagging more than this leaves views/<name>_s<seed>_offpal.png
# report.json views[].tries[]: every paint try of a camera with its gate values and the gates it failed
TRY_KEYS = ("seed", "ref", "iou_after", "edge_p90", "scale", "shift", "filled", "drift", "lighten", "bg_dev",
            "off_palette", "fails")
COVERAGE_FLOOR = {"character": 0.85, "prop": 0.75, "part": None}   # gates.json paint.coverage; None: reported


def coverage_floor(text):
    """--min-coverage: a share in (0, 1]; a floor of 0 or below could never fail."""
    import math
    try:
        v = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
    if not (math.isfinite(v) and 0.0 < v <= 1.0):
        raise argparse.ArgumentTypeError(f"{text} is not a share in (0, 1]")
    return v


def count_arg(text):
    """argparse type: a whole number of tries, at least 1."""
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from None
    if n < 1:
        raise argparse.ArgumentTypeError(f"{n} is under 1")
    return n


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
    ap.add_argument("--max-views", type=int, default=None,
                    help="cameras tried, rejections included (default: 20 for a character, 16 for an object)")
    ap.add_argument("--pitch-range", type=float, nargs=2, default=(-40.0, 50.0),
                    help="cameras stay in this pitch band: steeper views come back as eye-level drawings")
    ap.add_argument("--target", type=float, default=0.97, help="stop at this share of the seeable surface")
    ap.add_argument("--min-gain", type=float, default=0.003, help="skip a camera that adds less than this")
    ap.add_argument("--no-zoom", action="store_true")
    ap.add_argument("--zoom-max-pitch", type=float, default=None,
                    help="no zoom on cameras steeper than this (default: 30 for an object, none for a character)")
    ap.add_argument("--no-nbv", action="store_true", help="paint the anchors only")
    ap.add_argument("--min-iou", type=float, default=0.90)
    ap.add_argument("--max-edge", type=float, default=24.0, help="outline distance p90 (px at 1024) to accept a view")
    ap.add_argument("--min-share", type=float, default=0.3, help="share of the unpainted pixels the painted view covers (fill) or repaints "
                                                                   "(grey/magenta markers) to accept a view")
    ap.add_argument("--tries", type=count_arg, default=3, help="seeds per camera before giving up on it")
    ap.add_argument("--refine", type=float, default=1.5, help="0 blends every view")
    ap.add_argument("--detail", default="", help="character: 'head' adds zoomed repaint passes on the head")
    ap.add_argument("--detail-ref", type=Path, help="picture 2 for detail passes (default: front concept)")
    ap.add_argument("--detail-tries", type=count_arg, default=6,
                    help="seeds per detail pass; picture 2 alternates between the front concept view and that "
                         "view cut to the head as the detail camera frames it (a --detail-ref is used as given)")
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
    ap.add_argument("--max-off-palette", type=float, default=1.0,
                    help="reject a view whose figure has this share of colours that are in none of the concept "
                         "views (a navy palm on a black glove, a silver hand). Default 1: measured and reported, "
                         "not gated (hair sheen and small tints on whole characters and objects read off the "
                         "flat concept); the parts route (hand_views.py) sets 0.03")
    ap.add_argument("--coverage-for", choices=list(COVERAGE_FLOOR), default=None,
                    help="what is painted, for the coverage gate in gates.json: character (floor 0.85), prop "
                         "(0.75) or part (reported only; a hand or a head painted alone). Default: character "
                         "for --kind character, prop for --kind object")
    ap.add_argument("--min-coverage", type=coverage_floor, default=None,
                    help="the paint.coverage floor in gates.json (coverage_seeable, a share in (0, 1]); default "
                         "from --coverage-for")
    ap.add_argument("--seed", type=int, default=42, help="first seed: try t of view i paints with seed + 1000 t + i")
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


def kind_defaults(a):
    """Defaults that depend on --kind: a character has more surface worth a camera (20 views);
    a steep zoomed crop of an object comes back as an eye-level drawing (no zoom past 30 degrees)."""
    if a.max_views is None:
        a.max_views = 20 if a.kind == "character" else 16
    if a.zoom_max_pitch is None and a.kind == "object":
        a.zoom_max_pitch = 30.0
    if a.coverage_for is None:
        a.coverage_for = "character" if a.kind == "character" else "prop"
    if a.min_coverage is None:
        a.min_coverage = COVERAGE_FLOOR[a.coverage_for]
    return a


def report_gate(name, value):
    """A gate that is measured and written, never failed."""
    return {"name": name, "value": value, "limit": None, "pass": True, "report_only": True}


def gates_doc(rep, a, out, log, models):
    """gates.json: the run as gate/1, with a partial ledger record for art-asset-registry."""
    cov = rep["coverage_seeable"]
    if a.min_coverage is None:
        gates = [report_gate("paint.coverage", cov)]
    else:
        g = {"name": "paint.coverage", "value": cov, "limit": f">= {a.min_coverage:g}",
             "pass": bool(cov >= a.min_coverage)}
        m = gate_margin(cov, a.min_coverage, ">=")
        if m is not None:
            g["margin"] = m
        gates = [g]
    gates += [report_gate("paint.seam_delta", rep["seam_delta"]), report_gate("paint.views_refused", rep["rejected"])]
    if rep.get("stop") == "fatal":   # a paint server error cut the run short: its coverage is not a verdict
        gates.append({"name": "paint.run_complete", "value": "fatal", "limit": "not fatal", "pass": False})
    painted = (out / f"{a.glb.stem}_painted.glb").resolve()
    inputs = [{"path": str(a.glb.resolve())}]
    if a.sheet:
        inputs.append({"path": str(a.sheet.resolve())})
    inputs += [{"path": str((a.concept / f"{k}.png").resolve())} for k in CONCEPT_YAW if (a.concept / f"{k}.png").is_file()]
    record = {"tool": {"skill": "mesh-texture-paint", "script": "paint_loop.py"}, "kind": "mesh", "source": "generated",
              "files": [{"path": str(painted), "role": "shipped"},
                        {"path": str((out / "basecolor.png").resolve()), "role": "derived"},
                        {"path": str((out / "report.json").resolve()), "role": "derived"}],
              "inputs": inputs,
              "params": {"kind": a.kind, "coverage_for": a.coverage_for, "models": models,
                         "seeds": [v["seed"] for v in log if v.get("status") == "used" and "seed" in v]}}
    ok = all(g["pass"] is True for g in gates)
    return {"schema": "gate/1", "tool": "paint_loop", "pass": ok, "path": str(painted), "gates": gates,
            "record": dict(record, verdict="green" if ok else "failed")}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv in (["--selftest"], ["selftest"]):
        return selftest()
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    kind_defaults(a)
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
    (out / "gates.json").unlink(missing_ok=True)   # rewritten at the end; never an earlier run's verdict
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
    sheet, sheet_src = a.sheet, "given" if a.sheet else None
    if sheet is None:   # no --sheet: one composed from the concept views, so picture 2 is never only one view
        sheet = compose_sheet([refs[k] for k in CONCEPT_YAW], out / "views" / "sheet_composed.png")
        sheet_src = "composed" if sheet else None
    stale = 0
    prior = None
    if a.prior:
        src = a.glb if a.prior == "self" else Path(a.prior)
        try:
            pimg = M.glb_image(str(src)) if src.suffix.lower() == ".glb" else Image.open(src).convert("RGB")
            prior = acc.prior_colors(np.asarray(pimg))
        except (KeyError, TypeError, IndexError, OSError):
            print("no prior texture found; unpainted surface shows the nearest painted colour", file=sys.stderr)
    concept_imgs = [Image.open(p) for p in refs.values() if p.exists()]
    use_despill = not M.palette_has_key_hue(concept_imgs)
    palette = M.concept_palette(concept_imgs)
    details = []
    if a.detail == "head":
        h = mesh.v[:, 1].max() - mesh.v[:, 1].min()
        top = mesh.v[mesh.v[:, 1] > mesh.v[:, 1].max() - HEAD_TOP * h]
        tgt = (top.max(0) + top.min(0)) / 2
        tgt[1] -= HEAD_DROP * h  # face sits below the middle of hair + head
        tgt = tgt.tolist()
        r = float((top.max(0) - top.min(0)).max() / 2) * HEAD_MARGIN
        details = [{"yaw": yw, "pitch": 5.0, "radius": r, "target": tgt, "source": "detail"} for yw in (0.0, 40.0, 320.0)]
    detail_full = a.detail_ref or refs["front"]
    # every other detail try: the front view cut to the head as the detail camera frames it (a
    # --detail-ref is used as given: it may be a close-up already)
    detail_head = (head_reference(detail_full, out / "views" / "detail_ref_head.png", size=a.size, fill=a.fill)
                   if details and not a.detail_ref and Path(detail_full).is_file() else None)
    if log:  # --resume: detail passes already run are not repeated; a trailing run of rejections still counts
        done = {(v["yaw"], v["pitch"]) for v in log if v.get("source") == "detail"}
        details = [d for d in details if (d["yaw"], d["pitch"]) not in done]
        for v in reversed(log):
            if v.get("status") == "rejected" and v.get("source") != "nbv":
                continue    # a rejected anchor or detail pass neither counts nor ends the run
            if v.get("status") not in ("rejected", "failed: no output"):
                break
            stale += 1
    t_start = time.time()
    main_done = False
    stop = None
    skips = 0  # views in a row skipped with nothing unpainted
    fatal = None
    while True:
        plan = None
        if not main_done:
            stop = ("target" if acc.coverage() >= a.target else "max_views" if acc.views >= a.max_views
                    else "rejections" if stale >= 3 else "nothing_unpainted" if skips >= 3 else None)
            main_done = stop is not None
        while not main_done and plan is None and anchors:
            yw, pt = anchors.pop(0)
            if (yw, pt) not in used:
                plan = {"yaw": yw, "pitch": pt, "radius": radius, "target": None, "source": "anchor"}
        if not main_done and plan is None and a.no_nbv:
            main_done, stop = True, "anchors_done"
        if not main_done and plan is None:
            nb = M.next_best_view(acc, radius, a.fill, used, pitch=(lo_p, hi_p), zoom=not a.no_zoom,
                                  zoom_max_pitch=a.zoom_max_pitch, render_size=a.size,
                                  avoid=[(v["yaw"], v["pitch"]) for v in log
                                         if v.get("status") == "rejected" and v.get("source") == "nbv"])
            if nb is None or nb["gain"] < a.min_gain:
                main_done, stop = True, "no_view" if nb is None else "min_gain"
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
        if share_unp < M.SKIP_SHARE and not detail:
            rec["status"] = "skipped: nothing unpainted in view"
            log.append(rec)
            skips += plan["source"] == "nbv"   # an anchor seen already painted is not a re-pick
            continue
        skips = 0
        guide = out / "views" / f"{name}_guide.png"
        Image.fromarray(img).save(guide)
        zoomed = bool(plan.get("target"))
        k = nearest_concept(plan["yaw"])
        options = {"sheet": (sheet, f"a turnaround sheet of that {subject} (front, left, back and right views)"),
                   "nearest": (refs[k], f"the concept art of that {subject} seen from the "
                                        f"{k if k in ('front', 'back') else 'side'}")}
        if not sheet:
            options.pop("sheet")
        # the other reference is the fallback: a whole sheet can make the model paint a collage of
        # several figures, a single view can make it copy that view's facing
        order = [a.ref, "nearest" if a.ref == "sheet" else "sheet"] if a.ref in options else ["nearest"]
        if back_camera(plan["yaw"], zoomed, plan["pitch"]):   # with the sheet the model paints the front onto a back render
            order = ["nearest", "sheet"]
        order = [o for o in order if o in options]
        fmt = {"subject": subject, "label": view_label(plan["yaw"], plan["pitch"], zoomed),
               "details": DETAILS[a.kind], "grey": {"clay": "plain grey clay", "flat": "flat grey", "magenta": "magenta", "fill": ""}[a.context]}
        rec["prompt_mode"] = "detail" if detail else "first" if first else "context"
        best = None
        fitted = None
        for t in range(a.detail_tries if detail else a.tries):
            if detail:
                head = t % 2 == 1 and detail_head is not None
                ref, refdesc, rname = (detail_head if head else detail_full), f"concept art of that {subject}", \
                    ("front_head" if head else "front")
            else:
                rname = next_reference(order, t, rec.get("tries"))
                ref, refdesc = options[rname]
                if rname == "nearest" and not zoomed:   # framed like the guide (a zoomed crop has no figure box)
                    fitted = fitted or fit_reference(ref, rmask, out / "views" / f"{name}_ref_nearest.png")
                    ref = fitted or ref
            ctx_prompt = P_FILL if a.context == "fill" else P_CONTEXT
            prompt = (P_DETAIL if detail else P_FIRST if first else ctx_prompt).format(refdesc=refdesc, **fmt)
            seed = a.seed + 1000 * t + len(log)
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
            offpal, offm = M.off_palette(warped, rmask & wm & ~near_miss, palette)
            cand.update({"drift": round(drift, 3), "lighten": round(light, 3), "bg_dev": round(bg_dev, 1),
                         "off_palette": round(offpal, 4)})
            fails = [g for g, bad in (("iou", al["iou_after"] < a.min_iou), ("edge", al["edge_p90"] > a.max_edge),
                                      ("filled", filled < a.min_share), ("drift", drift > a.max_drift),
                                      ("lighten", light > a.max_lighten), ("bg_dev", bg_dev > a.max_bg_dev),
                                      ("off_palette", offpal > a.max_off_palette)) if bad]
            cand["fails"] = fails
            cand["ok"] = not fails
            rec.setdefault("tries", []).append({k: cand[k] for k in TRY_KEYS if k in cand})
            if offpal > OFFPAL_PICTURE:   # the colours it flagged, magenta on the view (gated or not)
                Image.fromarray(np.where(offm[..., None], M.MARK, warped)).save(raw.with_name(raw.stem + "_offpal.png"))
            key = (cand["ok"], al["iou_after"] * filled * (1.0 - offpal))
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
            if not cand["fails"]:
                cand.pop("fails")
            rec.update(cand)
            Image.fromarray(warped).save(out / "views" / f"{name}_aligned.png")
        if fatal:
            log.append(rec)
            stop = "fatal"
            (out / "report.json").write_text(json.dumps({"views": log}, indent=1))
            break
        if best is None:
            acc.views += 1  # a view that produced nothing counts as a rejection
            stale += 1      # whatever the camera: a server that returns nothing fails every camera
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
            # only next-best views end the loop by rejections: the anchors are a fixed list, and a
            # rejected anchor leaves the next anchor and the next-best views their turn
            stale += plan["source"] == "nbv"
        log.append(rec)
        print(json.dumps(rec), flush=True)
        acc.save(out / "state.npz")
        (out / "report.json").write_text(json.dumps({"views": log}, indent=1))

    painted_any = any(v.get("status") == "used" for v in log)
    if fatal or not painted_any:
        gated = any(v.get("status") == "rejected" for v in log)
        print(f"paint server error, run stopped: {fatal}" if fatal else
              "no view was painted: every try failed a gate (report.json, views/)" if gated else
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
    rep = {"coverage_seeable": round(acc.coverage(), 4),
           "coverage_screen": round(acc.screen_coverage(radius, a.fill), 4),
           "seam_delta": round(acc.seam_delta(), 2),
           "views_used": sum(v.get("status") == "used" for v in log),
           "rejected": sum(v.get("status") in ("rejected", "failed: no output") for v in log),
           "stop": stop, "minutes": round((time.time() - t_start) / 60, 1), "sheet": sheet_src,
           "settings": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(a).items()}, "views": log}
    (out / "report.json").write_text(json.dumps(rep, indent=1))
    gdoc = gates_doc(rep, a, out, log, models)
    (out / "gates.json").write_text(json.dumps(gdoc, indent=1))
    print(json.dumps({**{k: rep[k] for k in ("coverage_seeable", "coverage_screen", "seam_delta", "views_used",
                                             "rejected", "stop", "minutes")}, "gates_pass": gdoc["pass"]}))
    if not gdoc["pass"]:
        print("gates.json: paint.coverage is under its floor (" + gdoc["gates"][0]["limit"] + "); "
              "paint more views (--resume --max-views) or check the turntable", file=sys.stderr)
    return 3 if fatal else 0



def contract_sample(case: str, doc: dict) -> None:
    """Hand one selftest gates.json to tools/check-contracts.py: written to $UNITY_DEV_CONTRACT_OUT
    (else a fixed folder in the temp dir) as paint_loop__<case>.gate.json, and named on stdout as
    `selftest-output: <path>`."""
    folder = Path(os.environ.get("UNITY_DEV_CONTRACT_OUT") or Path(tempfile.gettempdir()) / "unity-dev-contract-out")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"paint_loop__{case}.gate.json"
    path.write_text(json.dumps(doc, indent=1))
    print(f"selftest-output: {path}")


def selftest() -> int:
    """Run the whole loop on a textured cube with a fake painter that colours the guide."""
    import tempfile
    t0 = time.time()
    real_paint = Q.paint
    calls = []

    tint = [np.array([180.0, 90.0, 40.0])]   # the parcel's orange; a navy painter is off the palette
    schedule = []                             # per-call tints that override tint[0] while they last

    def fake_paint(guide, ref, prompt, out_png, server=None, seed=42, models=None, **_kw):
        # a model that paints the view in one colour shaded by the guide, background stays key
        g = np.asarray(Image.open(guide).convert("RGB")).astype(np.float64)
        fg = M.key_mask(g.astype(np.uint8))
        o = g.copy()
        col = schedule.pop(0) if schedule else tint[0]
        col, cut = col if isinstance(col, tuple) else (col, 0)   # (tint, px): the figure drawn px narrower
        o[fg] = np.clip(col * np.clip(g[fg].mean(1, keepdims=True) / 150.0, 0.7, 1.2), 0, 255)
        o[:, :cut] = M.KEY
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
                im[24:104, 32:96] = (np.array([180, 90, 40]) * np.linspace(0.6, 1.25, 80)[:, None, None]).clip(0, 255)
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
            checks["report_keys"] = all(k in rep for k in ("coverage_seeable", "coverage_screen", "seam_delta",
                                                           "views_used", "rejected", "stop", "views"))
            checks["coverage_screen"] = 0.0 < rep["coverage_screen"] <= 1.0
            ch = kind_defaults(build_parser().parse_args(["x.glb", "--concept", "c", "--out", "o"]))
            ob = kind_defaults(build_parser().parse_args(["x.glb", "--concept", "c", "--out", "o", "--kind", "object"]))
            pt = kind_defaults(build_parser().parse_args(["x.glb", "--concept", "c", "--out", "o",
                                                          "--coverage-for", "part"]))
            checks["kind_defaults"] = (ch.max_views == 20 and ch.zoom_max_pitch is None
                                       and ob.max_views == 16 and ob.zoom_max_pitch == 30.0
                                       and (ch.coverage_for, ch.min_coverage) == ("character", 0.85)
                                       and (ob.coverage_for, ob.min_coverage) == ("prop", 0.75)
                                       and (pt.coverage_for, pt.min_coverage) == ("part", None))
            # gates.json: gate/1 beside report.json, the coverage floor with its margin, the rest reported
            gd = json.loads((out / "gates.json").read_text())
            gg = {g["name"]: g for g in gd["gates"]}
            cg = gg["paint.coverage"]
            checks["gates_json"] = (gd["schema"] == "gate/1" and "ok" not in gd and isinstance(gd["pass"], bool)
                                    and list(gg) == ["paint.coverage", "paint.seam_delta", "paint.views_refused"]
                                    and all("ok" not in g and isinstance(g["pass"], bool) for g in gd["gates"])
                                    and cg["value"] == rep["coverage_seeable"] and cg["limit"] == ">= 0.75"
                                    and cg["pass"] == (rep["coverage_seeable"] >= 0.75)
                                    and isinstance(cg.get("margin"), float) and (cg["margin"] >= 0) == cg["pass"]
                                    and gd["pass"] == cg["pass"]
                                    and all(gg[n]["report_only"] is True and gg[n]["pass"] is True
                                            and gg[n]["limit"] is None and "margin" not in gg[n]
                                            for n in ("paint.seam_delta", "paint.views_refused"))
                                    and gg["paint.seam_delta"]["value"] == rep["seam_delta"]
                                    and gg["paint.views_refused"]["value"] == rep["rejected"])
            gr = gd["record"]
            checks["gates_record"] = (gd["path"] == str((out / "parcel_painted.glb").resolve())
                                      and gr["files"][0]["path"] == gd["path"]
                                      and gr["tool"] == {"skill": "mesh-texture-paint", "script": "paint_loop.py"}
                                      and gr["inputs"][0]["path"] == str(glb.resolve())
                                      and len(gr["inputs"]) == 6 and gr["params"]["coverage_for"] == "prop"
                                      and gr["params"]["models"]["unet"] == "custom_unet.safetensors"
                                      and gr["params"]["seeds"] == [v["seed"] for v in used]
                                      and gr["verdict"] == ("green" if gd["pass"] else "failed"))
            contract_sample("cube_prop", gd)
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
            main(base + ["--out", str(td / "nz"), "--anchors", "0:0", "--max-views", "3", "--no-zoom",
                         "--coverage-for", "part"])
            nz = [v for v in json.loads((td / "nz" / "report.json").read_text())["views"] if v["source"] == "nbv"]
            checks["no_zoom_label"] = (len(nz) > 0 and not any(v["zoom"] or v["name"].endswith("z") for v in nz)
                                       and not any("close-up" in c["prompt"] for c in calls[n0:]))
            # a part's coverage is reported, never failed
            pg = json.loads((td / "nz" / "gates.json").read_text())
            checks["part_coverage_reported"] = (pg["pass"] is True and pg["gates"][0]["report_only"] is True
                                                and pg["gates"][0]["limit"] is None and "margin" not in pg["gates"][0])
            contract_sample("part_reported", pg)
            # a painter that paints the parcel navy: every view is off the palette and rejected
            tint[0] = np.array([30.0, 34.0, 90.0])
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = main(base + ["--out", str(td / "navy"), "--anchors", "0:0", "--no-nbv", "--tries", "2",
                                    "--seed", "7", "--max-off-palette", "0.03"])
            nv = json.loads((td / "navy" / "report.json").read_text())["views"]
            checks["off_palette_rejects"] = (code == 3 and "every try failed a gate" in err.getvalue()
                                             and len(nv) == 1 and nv[0]["status"] == "rejected"
                                             and nv[0]["off_palette"] > 0.5 and nv[0]["seed"] in (7, 1007)
                                             and any((td / "navy" / "views").glob("*_offpal.png")))
            # without --max-off-palette it is measured and reported, never a rejection
            with contextlib.redirect_stderr(io.StringIO()):
                code_d = main(base + ["--out", str(td / "navy_d"), "--anchors", "0:0", "--no-nbv", "--tries", "1"])
            nd = json.loads((td / "navy_d" / "report.json").read_text())["views"]
            checks["off_palette_default_reports_only"] = (code_d == 0 and len(nd) == 1 and nd[0]["status"] == "used"
                                                          and nd[0]["off_palette"] > 0.5
                                                          and any((td / "navy_d" / "views").glob("*_offpal.png")))
            tint[0] = np.array([180.0, 90.0, 40.0])
            # three anchors in a row rejected (navy, gated) no longer end the run: the next-best views
            # still paint; each rejected anchor names its failed gate in its tries
            orange, navy = np.array([180.0, 90.0, 40.0]), np.array([30.0, 34.0, 90.0])
            schedule[:] = [orange, navy, navy, navy]
            with contextlib.redirect_stderr(io.StringIO()):
                code_a = main(base + ["--out", str(td / "anch"), "--anchors", "0:0,90:0,180:0,270:0", "--tries", "1",
                                      "--max-views", "6", "--no-zoom", "--max-off-palette", "0.03"])
            schedule.clear()
            ra = json.loads((td / "anch" / "report.json").read_text())
            rej = [v for v in ra["views"] if v.get("status") == "rejected" and v["source"] == "anchor"]
            checks["anchor_rejections_do_not_stop"] = (
                code_a == 0 and ra["stop"] != "rejections" and len(rej) == 3
                and all(v["source"] == "anchor" and v["fails"] == ["off_palette"] and len(v["tries"]) == 1
                        and v["tries"][0]["fails"] == ["off_palette"] for v in rej)
                and any(v["source"] == "nbv" and v.get("status") == "used" for v in ra["views"])
                and all("fails" not in v and v["tries"][-1]["fails"] == [] for v in ra["views"] if v.get("status") == "used"))
            # a sheet try that failed another gate retries with the sheet; one that failed the outline (the
            # figure drawn 60 px narrower) retries with the nearest view framed like the guide; a failed head
            # detail try retries with the front drawing cut to the head
            n0 = len(calls)
            schedule[:] = [orange, navy, (orange, 60), orange, navy, orange]
            with contextlib.redirect_stderr(io.StringIO()):
                code_f = main(base + ["--out", str(td / "fit"), "--anchors", "0:0,90:0", "--no-nbv", "--tries", "3",
                                      "--detail", "head", "--detail-tries", "2", "--max-off-palette", "0.03"])
            schedule.clear()
            rf = {v["name"]: v for v in json.loads((td / "fit" / "report.json").read_text())["views"]}
            seq = [(c["ref"], "close-up" in c["prompt"]) for c in calls[n0:n0 + 6]]
            v1 = rf["v01_y090_p+00"]
            checks["fallback_references"] = (
                code_f == 0 and seq == [("sheet.png", False), ("sheet.png", False), ("sheet.png", False),
                                        ("v01_y090_p+00_ref_nearest.png", False), ("front.png", True),
                                        ("detail_ref_head.png", True)]
                and [t["ref"] for t in v1["tries"]] == ["sheet", "sheet", "nearest"]
                and v1["tries"][0]["fails"] == ["off_palette"] and "iou" in v1["tries"][1]["fails"]
                and v1["ref"] == "nearest" and v1["status"] == "used"
                and [t["ref"] for t in rf["v02_y000_p+05z"]["tries"]] == ["front", "front_head"]
                and rf["v02_y000_p+05z"]["status"] == "used" and rf["v02_y000_p+05z"]["ref"] == "front_head"
                and next_reference(["nearest", "sheet"], 1, [{"ref": "nearest", "fails": ["drift"]}]) == "nearest"
                and next_reference(["nearest", "sheet"], 1, [{"ref": "nearest", "fails": ["iou"]}]) == "sheet"
                and back_camera(180, False) and back_camera(144, False) and back_camera(-160, False)
                and not back_camera(135, False) and not back_camera(225, False) and not back_camera(180, True)
                and back_camera(170, False, -10) and not back_camera(144, False, -37)
                and not back_camera(198, False, 48)
                and next_reference(["nearest"], 2, None) == "nearest")
            # no --sheet: a sheet composed from the concept views is picture 2 first, never one view alone
            n0 = len(calls)
            with contextlib.redirect_stderr(io.StringIO()):
                code_c = main([b for i, b in enumerate(base) if b != "--sheet" and base[i - 1] != "--sheet"]
                              + ["--out", str(td / "comp"), "--anchors", "0:0", "--no-nbv", "--tries", "1"])
            rc = json.loads((td / "comp" / "report.json").read_text())
            comp = td / "comp" / "views" / "sheet_composed.png"
            cw, ch = Image.open(comp).size if comp.exists() else (0, 0)
            checks["composed_sheet"] = (code_c == 0 and rc["sheet"] == "composed" and rep["sheet"] == "given"
                                        and rc["views"][0]["ref"] == "sheet" and cw > 3 * ch
                                        and calls[n0]["ref"] == "sheet_composed.png"
                                        and "turnaround sheet" in calls[n0]["prompt"])
            # a camera seen from behind starts with the back view framed like the guide, not the sheet
            n0 = len(calls)
            with contextlib.redirect_stderr(io.StringIO()):
                code_b = main(base + ["--out", str(td / "back"), "--anchors", "180:0", "--no-nbv", "--tries", "1"])
            rb = json.loads((td / "back" / "report.json").read_text())
            checks["back_view_first"] = (code_b == 0 and rb["views"][0]["ref"] == "nearest"
                                         and calls[n0]["ref"] == "v00_y180_p+00_ref_nearest.png"
                                         and "seen from the back" in calls[n0]["prompt"])
            # a GLB without a base-colour texture paints and gets one; a GLB that cannot be written is exit 1
            bare = td / "bare.glb"
            M.edit_glb_json(glb, lambda js: js["materials"][0]["pbrMetallicRoughness"].pop("baseColorTexture"), bare)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = main([str(bare)] + base[1:] + ["--out", str(td / "bare"), "--anchors", "0:0,90:0",
                                                      "--no-nbv", "--min-coverage", "0.999"])
            checks["textureless_glb"] = bool(code == 0 and np.asarray(M.glb_image(td / "bare" / "bare_painted.glb")).std() > 0)
            # two anchors cannot reach a 0.999 floor: gates.json fails with a negative margin, the exit stays 0
            bg = json.loads((td / "bare" / "gates.json").read_text())
            checks["coverage_floor_fails"] = (code == 0 and bg["pass"] is False and bg["gates"][0]["pass"] is False
                                              and bg["gates"][0]["limit"] == ">= 0.999" and bg["gates"][0]["margin"] < 0
                                              and bg["record"]["verdict"] == "failed"
                                              and "paint.coverage is under its floor" in err.getvalue())
            contract_sample("coverage_under_floor", bg)
            checks["stop_reason"] = (rep["stop"] == "max_views"
                                     and json.loads((td / "bare" / "report.json").read_text())["stop"] == "anchors_done")
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
                (td / tag).mkdir()          # an earlier run's green gates.json must not outlive this one
                (td / tag / "gates.json").write_text(json.dumps({"schema": "gate/1", "pass": True, "gates": []}))
                with contextlib.redirect_stderr(io.StringIO()):
                    code = main(base + ["--out", str(td / tag), "--max-views", "16"])
                checks[tag] = (code == 3 and 0 < len(calls) - n0 <= limit
                               and not (td / tag / "parcel_painted.glb").exists()
                               and not (td / tag / "gates.json").exists())
            Q.paint = fake_paint
            # fit_reference: a small figure off in a corner of its drawing lands on the guide's silhouette box
            fig = np.zeros((256, 256, 3), np.uint8)
            fig[30:90, 20:40] = (200, 120, 60)
            Image.fromarray(fig).save(td / "small.png")
            gm = np.zeros((256, 256), bool)
            gm[53:203, 103:153] = True
            fr = fit_reference(td / "small.png", gm, td / "small_fit.png")
            fy, fx = np.nonzero(np.asarray(Image.open(fr).convert("L")) > 40)
            checks["fit_reference"] = (fr is not None and abs(int(fy.min()) - 53) <= 2 and abs(int(fy.max()) - 202) <= 2
                                       and abs(int(fx.min()) - 103) <= 2 and abs(int(fx.max()) - 152) <= 2)
            # head_reference: the crop is the head (red) over little of the body (blue)
            fig = np.zeros((400, 200, 3), np.uint8)
            yy2, xx2 = np.mgrid[0:400, 0:200]
            fig[(yy2 - 60) ** 2 + (xx2 - 100) ** 2 < 32 ** 2] = (220, 40, 40)
            fig[92:380, 60:140] = (40, 40, 220)
            Image.fromarray(fig).save(td / "body.png")
            hc = np.asarray(Image.open(head_reference(td / "body.png", td / "body_head.png", size=128)).convert("RGB")).astype(int)
            red = ((hc[..., 0] > 150) & (hc[..., 2] < 90)).mean()
            blue = ((hc[..., 2] > 150) & (hc[..., 0] < 90)).mean()
            checks["head_reference"] = bool(red > 0.3 and blue < red / 2)
            # a concept without alpha on a white page: a white shirt inside the figure stays figure
            page = np.full((300, 200, 3), 255, np.uint8)
            page[40:260, 60:140] = (30, 60, 160)
            page[80:160, 70:130] = 255
            Image.fromarray(page).save(td / "white_page.png")
            _, wm = figure_on_black(td / "white_page.png")
            # concept views of two sizes compose onto one baseline at one scale
            big = np.zeros((600, 400, 3), np.uint8)
            big[80:520, 120:280] = 200
            Image.fromarray(big).save(td / "big.png")
            Image.fromarray(big[::2, ::2].copy()).save(td / "half.png")
            sh = np.asarray(Image.open(compose_sheet([td / "half.png", td / "big.png"], td / "mixed.png")).convert("L"))
            rows = [np.nonzero(sh[:, x] > 40)[0] for x in (60, sh.shape[1] - 60)]
            checks["figure_mask_and_mixed_sizes"] = bool(
                wm[120, 100] and not wm[5, 5] and all(len(r) for r in rows)
                and abs(int(rows[0][0]) - int(rows[1][0])) <= 1 and abs(int(rows[0][-1]) - int(rows[1][-1])) <= 1)
            # usage errors exit 1
            checks["usage_exit_1"] = True
            for bad in (["x.glb"], ["x.glb", "--concept", "c", "--out", "o", "--tries", "0"],
                        ["x.glb", "--concept", "c", "--out", "o", "--detail-tries", "0"], ["x.glb", "--concept", "c", "--out", "o", "--coverage-for", "hand"],
                        ["x.glb", "--concept", "c", "--out", "o", "--min-coverage", "most"],
                        ["x.glb", "--concept", "c", "--out", "o", "--min-coverage", "0"],
                        ["x.glb", "--concept", "c", "--out", "o", "--min-coverage", "1.5"],
                        ["x.glb", "--concept", "c", "--out", "o", "--min-coverage", "nan"]):
                try:
                    with contextlib.redirect_stderr(io.StringIO()):
                        build_parser().parse_args(bad)
                    checks["usage_exit_1"] = False
                except SystemExit as e:
                    checks["usage_exit_1"] &= e.code == 1
            summary = {k: rep[k] for k in ("coverage_seeable", "views_used")}
    finally:
        Q.paint = real_paint
    ok = all(checks.values())
    print(json.dumps({"checks": checks, **summary, "paint_calls": len(calls),
                      "seconds": round(time.time() - t0, 1), "pass": ok}))
    return 0 if ok else 2

if __name__ == "__main__":
    sys.exit(main())
