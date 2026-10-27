#!/usr/bin/env python3
"""breathe.py — turn ONE still idle pose into a breathing loop, pixel-exact, on the same canvas.

A still pose that has to read as alive (a sentry waiting at the gate, the runner
before the launch) does not need a generated sheet: one squash-and-stretch field,
strongest in the chest and zero at the feet and above the neck, played over a
phase loop, is the idle. No interpolation, no blending and no fractional scale
ever happens, so every output pixel is a copy of an input pixel:

  wave(t) = 0.86 sin 2πt + 0.14 sin 4πt
  env(u)  = smoothstep(0, 0.28·ru, u) · (1 − smoothstep(ru − band, ru + band, u))
            u = 0 at the feet, 1 at the top of the content; ru = the rigid boundary;
            band = max(1.5 px, 0.055·height)
  g(u, t) = depth · norm · wave(t − lag·min(1, u/ru)) · env(u)
            norm = basis_rows / Σ env, so `depth` is the total stretch as a fraction
            of the body below the neck, whatever the character's proportions
  sx = 1 + g        sy = 1 / (1 + g)       (area kept)

Vertical: rows are duplicated or deleted whole — row j of the content occupies
reps_j = ⌊acc_j + ½⌋ − ⌊acc_{j−1} + ½⌋ output rows, acc += 1/(1+g), counted from
the top. Horizontal: a monotone integer column map per row, density
max(0.05, 1 + g·(1 − protect(x))), output column → source column by
`searchsorted(cumsum(dens) − edge[axis_x])`, so the body's axis column never
moves; `protect` keeps a wide appendage (a raised arm, a cape) from stretching —
it is pushed, not widened. The outermost opaque source column of each row stays
on the row's outline, so a 1 px outline survives an exhale.

Invariants:
  * env fades to zero over `band` rows above the rigid boundary (the chin and
    lower face still move a little); from there up g = 0 exactly and the rows are
    copied as they are, so that head block — `identity_rows` in frames.json —
    is bit-identical in every frame. It rides on the body by whole pixels
    (`head_dy_px` per frame) — that lift is the breath;
  * the bottom row of the content is the input's bottom row, at the same place:
    the feet are pinned on the content's bottom line;
  * phases are ((i·breaths) mod n) / n, folded on integers first, so equal phases
    are bit-identical frames and frame n would be frame 0: the loop closes;
  * the colour set of every frame is a subset of the input's.

Rigid boundary, `--rigid-from`:
  auto   the neck: the alpha≥128 width of the run through the body axis is taken
         per row, smoothed, and of the local minima in the top 5–60 % that rise
         back by at least 6 % of the widest row on both sides, the narrowest is the
         neck (a waist is often the more prominent minimum, rarely the narrower). With no such
         bottleneck (a blob, a hooded figure) the boundary falls back to
         --rigid-fallback (a fraction of the content height, from the top).
  0.xx   that fraction of the content height, from the top, stays rigid.
  Either way the boundary is capped at 80 % of the height.

--depth is relative to the body below the neck, so the head lifts by about
depth × that many rows. The default, auto, aims that lift at max(3 px, 1.5 % of
the content height) and caps depth at 0.06: about 0.06 on a 64 px sprite, about
0.017 on a 280 px figure (a 4 px lift), where a fixed 0.06 lifts the head 13 px
and reads as a squat. A number overrides it.

Refusals (exit 2, nothing written): the per-row strain depth·norm·max(env)
exceeds 0.25 (the deforming band is too short for that depth — lower --depth or
raise the boundary); or a stretched frame pushes an opaque pixel outside the
canvas (top, left or right — widen the canvas margin or lower --depth). Nothing
is ever clipped quietly.

usage:
    breathe.py idle.png --out-dir DIR [--frames 12] [--breaths 1] [--depth auto]
               [--lag 0.10] [--rigid-from auto|0.xx] [--rigid-fallback 0.30]
               [--fps 8] [--name sentry_idle]
    breathe.py --selftest            (or: breathe.py selftest)

Writes DIR/<name>_000.png … (name defaults to the input's stem) on the input's
canvas, and DIR/frames.json: `register.mode` `keep` (each frame stays where it is
drawn; the feet line is the content's bottom), `pivot_norm` at the foot centre
measured from the bottom-left, `fps_hint`, `loop` true, `verdict {ok, faults}`,
`producer {skill: codex-visual, script: breathe.py}`, the `breathe` parameters
and anatomy, and per frame its `phase` and `head_dy_px`. Fewer than 6 frames per
breath is allowed and reported as a warning: the breath reads as a twitch.
Prints one JSON object.

Exit codes
  0  frames and frames.json written (or selftest passed)
  1  usage error, unreadable input, no opaque content, or a selftest check failed
  2  refused: per-row strain over 0.25, or an opaque pixel pushed off the canvas

Requires Pillow and numpy (codex's imagegen venv has both: ~/.codex/imagegen-venv/bin/python).
"""
# ---------------------------------------------------------------------------
# Third-party code. Portions are ported, with identifiers and structure
# adapted, from sprite-gen
#   https://github.com/aldegad/sprite-gen
#   commit dddcc1013f7b5587a5eabd8609a5b42dd8aa7c26
# Apache License 2.0 — see THIRD_PARTY_NOTICES.md.
#
#   effects/breathe.py   wave, smoothstep, _smoothstep_array, envelope,
#                        protect (automatic branch), row_strain, the pixel-mode
#                        _warp (top-down row accumulation, half-up rounding,
#                        density column map with searchsorted, the axis column
#                        as fixed point, the outline-end column copy, the
#                        off-canvas refusal), the per-row strain refusal of
#                        _row_refusals, MAX_ROW_STRAIN, TAPER, FOOT,
#                        DEFAULT_DEPTH, DEFAULT_LAG, SMOOTH_CYCLE_FRAMES, and the
#                        integer-folded phase formula of breathe_loop
#   effects/anatomy.py   ALPHA_SOLID, APPENDAGE_RATIO, BOTTLENECK_PROMINENCE,
#                        axis_x, center_run, width_profile,
#                        bottleneck_prominences, _best_bottleneck, the
#                        bottleneck branch of detect_neck, torso_metrics, the
#                        rigid_row / basis_row rules of analyze, rigid_u,
#                        basis_rows, has_appendage
#
# Changes: --depth defaults to auto (a head lift of max(3 px, 1.5 % of the
# height), depth at most upstream's 0.06) instead of a fixed 0.06; numpy masks
# replace per-pixel PIL access; the warped body is cropped
# and its feet pinned on the alpha>0 bounding box (anatomy still measures at
# alpha>=128), so a soft keyed rim is carried rather than dropped; the face
# (eye-pair) detector, the shoulder-gradient neck fallback, the manual torso
# band, depth_x, the smooth mode, breath_peaks / loop segments and the
# curation sidecar are not ported — with no neck bottleneck the rigid boundary
# is a height fraction; the neck is searched in the top 5-60 % (not 5-70 %) and
# the narrowest qualifying minimum wins (not the most prominent); the profile smoothing is a plain centred moving average
# of the same window; the 1 px outline-thinning pass is not ported; refusals
# raise an exception mapped to exit 2; output is equal-canvas PNG frames and a
# frames.json sidecar in this repo's format.
# ---------------------------------------------------------------------------
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ALPHA_SOLID = 128            # anatomy counts a pixel as body at alpha >= this
APPENDAGE_RATIO = 1.30       # widest half-width over torso half-width that marks an appendage
BOTTLENECK_PROMINENCE = 0.06 # a neck rises back by at least this fraction of the widest row
NECK_BAND = (0.05, 0.60)     # where a neck may sit, as fractions of the content height from the top
RIGID_CAP = 0.80             # the boundary never takes more than this much of the height
TAPER = 0.055                # half-width of the fade into the rigid region, fraction of the height
FOOT = 0.28                  # the bottom 28 % of the deforming band ramps up from zero
MAX_ROW_STRAIN = 0.25
DEFAULT_DEPTH = "auto"
MAX_DEPTH_AUTO = 0.06        # upstream's default, kept for a sprite small enough to need it
HEAD_LIFT_PX = 3             # auto depth aims the head lift at max(this, HEAD_LIFT_FRACTION x height)
HEAD_LIFT_FRACTION = 0.015
DEFAULT_LAG = 0.10
DEFAULT_FALLBACK = 0.30
SMOOTH_CYCLE_FRAMES = 6      # frames per breath below which a breath reads as a twitch


class Refused(Exception):
    """A bake that would deform or clip beyond the limits — exit 2, nothing written."""


# ---------------------------------------------------------------- anatomy ----

def axis_x(solid):
    """Body axis: x centroid of the solid pixels, relative to the box (floor)."""
    ys, xs = np.nonzero(solid)
    return int(xs.sum()) // max(1, xs.size)


def center_run(row, cx):
    """(lo, hi) inclusive of the solid run through column cx, or the run nearest to it; None when empty."""
    idx = np.flatnonzero(row)
    if idx.size == 0:
        return None
    seed = cx if row[cx] else int(idx[np.argmin(np.abs(idx - cx))])
    lo = seed
    while lo > 0 and row[lo - 1]:
        lo -= 1
    hi = seed
    while hi < row.size - 1 and row[hi + 1]:
        hi += 1
    return lo, hi


def width_profile(solid, cx):
    """Per-row width of the run through the axis — a detached appendage does not count."""
    out = []
    for row in solid:
        run = center_run(row, cx)
        out.append(0 if run is None else run[1] - run[0] + 1)
    return out


def smooth_profile(profile, window):
    """Centred moving average, the window truncated at the ends."""
    n, half = len(profile), window // 2
    c = np.concatenate(([0.0], np.cumsum(np.asarray(profile, float))))
    return [float((c[min(n, i + half + 1)] - c[max(0, i - half)]) / (min(n, i + half + 1) - max(0, i - half)))
            for i in range(n)]


def bottleneck_prominences(profile):
    """Local minima and their prominence — the smaller of the rises back on either side."""
    n = len(profile)
    out = []
    for i in range(1, n - 1):
        if profile[i] > profile[i - 1] or profile[i] > profile[i + 1]:
            continue
        out.append((i, min(max(profile[:i]), max(profile[i + 1:])) - profile[i]))
    return out


def best_bottleneck(profile, u0, u1):
    n = len(profile)
    lo, hi = int(n * u0), int(n * u1)
    peak = max(profile) if profile else 0.0
    cand = [(i, p) for i, p in bottleneck_prominences(profile) if lo <= i < hi]
    if not cand:
        return None
    cand = [(i, p) for i, p in cand if p >= BOTTLENECK_PROMINENCE * peak]
    if not cand:
        return None
    # the narrowest qualifying minimum: a waist can be more prominent than the neck, never narrower
    return min(cand, key=lambda t: (profile[t[0]], -t[1], t[0]))[0]


def detect_neck(profile):
    n = len(profile)
    smooth = smooth_profile([float(v) for v in profile], 2 * max(1, n // 40) + 1)
    return best_bottleneck(smooth, *NECK_BAND)


def torso_metrics(solid, cx, profile, row_lo):
    """(median torso half-width, widest half-width) below the boundary — their ratio marks an appendage."""
    h, w = solid.shape
    band = sorted(v for v in profile[max(0, row_lo):] if v)
    torso = band[len(band) // 2] // 2 if band else w // 4
    ys, xs = np.nonzero(solid[max(0, row_lo):])
    max_half = int(np.abs(xs - cx).max()) if xs.size else 0
    return max(1, torso), max(1, max_half)


def analyze(rgba, rigid_from="auto", fallback=DEFAULT_FALLBACK):
    """Measure the content: box (alpha>0), axis, neck, rigid boundary, normalisation basis, torso widths."""
    alpha = rgba[..., 3]
    ys, xs = np.nonzero(alpha)
    if ys.size == 0:
        raise ValueError("no opaque content")
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    solid = alpha[y0:y1, x0:x1] >= ALPHA_SOLID
    if not solid.any():
        raise ValueError(f"no pixel at alpha >= {ALPHA_SOLID}")
    cx = axis_x(solid)
    profile = width_profile(solid, cx)
    neck = detect_neck(profile)
    warnings = []
    if rigid_from == "auto":
        if neck is not None:
            rigid, source = neck, "neck"
        else:
            rigid, source = int(math.floor(fallback * h + 0.5)), "fraction-fallback"
            warnings.append(f"neck-absent: no bottleneck in the width profile; the top {fallback:g} of the "
                            f"height stays rigid (--rigid-from to set it)")
    else:
        rigid, source = int(math.floor(float(rigid_from) * h + 0.5)), "manual"
    cap = int(h * RIGID_CAP)
    if rigid > cap:
        warnings.append(f"rigid-capped: boundary {rigid} capped at {cap} ({RIGID_CAP:g} of the height)")
        rigid = cap
    if not 0 < rigid < h:
        raise ValueError(f"rigid boundary row {rigid} is outside the content height {h}")
    basis = neck if (neck is not None and source != "fraction-fallback") else rigid
    torso, max_half = torso_metrics(solid, cx, profile, rigid)
    return dict(box=box, width=w, height=h, axis_x=cx, neck_row=neck, rigid_row=rigid, rigid_source=source,
                basis_row=basis, torso_half=torso, max_half=max_half,
                has_appendage=max_half >= APPENDAGE_RATIO * torso, warnings=warnings)


def rigid_u(anat):
    return 1.0 - anat["rigid_row"] / max(1, anat["height"] - 1)


def basis_rows(anat):
    return max(1, anat["height"] - anat["basis_row"])


# ------------------------------------------------------------------- warp ----

def wave(t):
    return 0.86 * math.sin(2 * math.pi * t) + 0.14 * math.sin(4 * math.pi * t)


def smoothstep(a, b, x):
    if b <= a:
        return 1.0 if x >= b else 0.0
    u = min(1.0, max(0.0, (x - a) / (b - a)))
    return u * u * (3 - 2 * u)


def smoothstep_array(a, b, x):
    if b <= a:
        return (x >= b).astype(np.float64)
    u = np.clip((x - a) / (b - a), 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def envelope(anat, taper=TAPER, foot=FOOT):
    """(env(u), norm): env is 0 at the feet and above the boundary; norm makes Σ g = depth · basis_rows."""
    height = anat["height"]
    ru = rigid_u(anat)
    band = max(1.5, taper * height) / max(1, height)
    foot_top = foot * ru

    def env(u):
        return smoothstep(0.0, foot_top, u) * (1.0 - smoothstep(ru - band, ru + band, u))

    total = sum(env(j / max(1, height - 1)) for j in range(height))
    norm = basis_rows(anat) / total if total > 1e-6 else 0.0
    return env, norm


def protect(anat):
    """p(x) in [0, 1] per content column: 1 = that column is pushed but never widened."""
    cx = anat["axis_x"]
    if not anat["has_appendage"]:
        return lambda x: np.zeros(np.shape(x))
    t0 = anat["torso_half"] * 1.15
    t1 = max(t0 + 1.0, anat["max_half"] * 0.95)
    return lambda x: smoothstep_array(t0, t1, np.abs(np.asarray(x) - cx))


def identity_rows(anat):
    """Rows from the top of the content where env is exactly 0 — copied unchanged in every frame."""
    env, _ = envelope(anat)
    h = anat["height"]
    n = 0
    while n < h and env(1.0 - n / max(1, h - 1)) == 0.0:
        n += 1
    return n


def row_strain(anat, depth):
    env, norm = envelope(anat)
    peak = max(env(j / max(1, anat["height"] - 1)) for j in range(anat["height"]))
    return depth * norm * peak


def phases(n, breaths):
    """Integer-folded first, so equal phases are equal doubles and their frames bit-identical."""
    b = max(1, int(breaths))
    return [((i * b) % n) / n for i in range(n)]


def warp(rgba, anat, depth, lag, t):
    """One phase t of the loop: same canvas, feet pinned on the content's bottom line.

    Returns (frame, off) where off counts opaque pixels pushed past the top, left and right
    edges (a pixel past a corner counts on both sides)."""
    x0, y0, x1, y1 = anat["box"]
    body = rgba[y0:y1, x0:x1]
    height, width = body.shape[:2]
    canvas_h, canvas_w = rgba.shape[:2]
    ax = anat["axis_x"]
    anchor_x = x0 + ax
    baseline = y1
    env, norm = envelope(anat)
    keep_cols = 1.0 - protect(anat)(np.arange(width))
    ru = rigid_u(anat)

    def gain(u):
        e = env(u)
        if e <= 0.0:
            return 0.0
        return depth * norm * wave(t - lag * min(1.0, u / max(1e-6, ru))) * e

    heights, acc = [], 0.0
    for j in range(height):                          # j = 0 is the top of the content
        g = gain(1.0 - j / max(1, height - 1))
        acc += 1.0 if g == 0.0 else 1.0 / (1.0 + g)
        heights.append(acc)
    total = max(1, math.floor(acc + 0.5))

    out = np.zeros((canvas_h, canvas_w, 4), np.uint8)
    opaque = body[..., 3] != 0
    y_cursor = baseline - total
    prev = 0
    off = {"top": 0, "left": 0, "right": 0}
    for j in range(height):
        u = 1.0 - j / max(1, height - 1)
        cur = math.floor(heights[j] + 0.5)
        reps = max(0, cur - prev)
        prev = cur
        if reps == 0:
            continue
        g = gain(u)
        if g == 0.0:
            out_x = x0 + np.arange(width)            # identity: the g -> 0 limit of the axis-fixed map
            src_x = np.arange(width)
        else:
            dens = np.maximum(0.05, 1.0 + g * keep_cols)
            edge = np.concatenate(([0.0], np.cumsum(dens)))
            origin = edge[ax]                        # the axis column is the fixed point
            lo = math.floor(edge[0] - origin + 0.5)  # half-up, not banker's rounding
            hi = math.floor(edge[width] - origin + 0.5)
            ox = np.arange(lo, hi)
            src_x = np.searchsorted(edge[1:width] - origin, ox, side="right")
            out_x = anchor_x + ox
            # the row's outermost opaque source columns stay at its two opaque ends: the outline survives
            row_op = np.flatnonzero(opaque[j])
            ends = np.flatnonzero(opaque[j, src_x])
            if row_op.size and ends.size:
                src_x[ends[-1]] = row_op[-1]
                src_x[ends[0]] = row_op[0]
        pixels = body[j, src_x]
        shown = pixels[:, 3] != 0
        left = int(np.count_nonzero(shown & (out_x < 0)))
        right = int(np.count_nonzero(shown & (out_x >= canvas_w)))
        inside = shown & (out_x >= 0) & (out_x < canvas_w)
        n_shown = int(np.count_nonzero(shown))
        for r in range(reps):
            yy = y_cursor + r
            if 0 <= yy < canvas_h:
                out[yy, out_x[inside]] = pixels[inside]
            elif yy < 0:
                off["top"] += n_shown
            off["left"] += left
            off["right"] += right
        y_cursor += reps
    return out, off


# ---------------------------------------------------------------- the run ----

def foot_pivot(rgba, anat):
    """[x, y] fraction of the canvas from its bottom-left: centre of the bottom row's opaque span."""
    x0, _, _, y1 = anat["box"]
    h, w = rgba.shape[:2]
    cols = np.flatnonzero(rgba[y1 - 1, :, 3] != 0)
    foot_x = (cols.min() + cols.max() + 1) / 2.0
    return [round(foot_x / w, 6), round((h - y1) / h, 6)]


def auto_depth(anat):
    """The depth whose head lift is about max(HEAD_LIFT_PX, HEAD_LIFT_FRACTION x content height)
    px, capped at MAX_DEPTH_AUTO: upstream's 0.06 on a small sprite, a few pixels on a large one."""
    target = max(HEAD_LIFT_PX, HEAD_LIFT_FRACTION * anat["height"])
    return round(min(MAX_DEPTH_AUTO, target / basis_rows(anat)), 4)


def bake(rgba, frames, breaths, depth, lag, rigid_from="auto", fallback=DEFAULT_FALLBACK):
    """All frames in memory, or Refused. Returns (frames, phases, anat, strain, head_dy, depth)."""
    anat = analyze(rgba, rigid_from, fallback)
    if depth == "auto":
        depth = auto_depth(anat)
    strain = row_strain(anat, depth)
    if strain > MAX_ROW_STRAIN:
        raise Refused(f"per-row strain {strain:.3f} > {MAX_ROW_STRAIN} — the deforming band is too short for "
                      f"this depth (rigid row {anat['rigid_row']}/{anat['height']}, basis row "
                      f"{anat['basis_row']}); lower --depth or move --rigid-from up")
    ph = phases(frames, breaths)
    outs, head_dy = [], []
    cache = {}
    total_off = {"top": 0, "left": 0, "right": 0}
    top0 = anat["box"][1]
    for t in ph:
        if t not in cache:
            cache[t] = warp(rgba, anat, depth, lag, t)
        img, off = cache[t]
        for k in total_off:
            total_off[k] += off[k]
        outs.append(img)
        rows = np.flatnonzero((img[..., 3] != 0).any(axis=1))
        head_dy.append(int(rows[0]) - top0 if rows.size else 0)
    if any(total_off.values()):
        sides = ", ".join(f"{k} {v}" for k, v in total_off.items() if v)
        x0, y0, x1, y1 = anat["box"]
        raise Refused(f"a stretched frame pushes opaque pixels off the canvas ({sides}; canvas "
                      f"{rgba.shape[1]}x{rgba.shape[0]}, content {x0},{y0}-{x1},{y1}) — widen the canvas "
                      f"margin or lower --depth; nothing is clipped")
    return outs, ph, anat, strain, head_dy, depth


def run(src, out_dir, frames=12, breaths=1, depth=DEFAULT_DEPTH, lag=DEFAULT_LAG, rigid_from="auto",
        fallback=DEFAULT_FALLBACK, fps=8.0, name=None):
    """Returns (exit code, result dict)."""
    try:
        img = Image.open(src)
        img.load()
    except (OSError, ValueError) as exc:
        return 1, {"ok": False, "error": f"cannot read {src}: {exc}"}
    rgba = np.asarray(img.convert("RGBA")).copy()
    depth_arg = depth
    if depth != "auto":
        try:
            depth = float(depth)
        except ValueError:
            return 1, {"ok": False, "error": f"--depth {depth!r}: give auto or a number >= 0"}
    if frames < 1 or breaths < 1 or (depth != "auto" and depth < 0) or fps <= 0:
        return 1, {"ok": False, "error": "--frames and --breaths must be >= 1, --depth >= 0, --fps > 0"}
    if rigid_from != "auto":
        try:
            f = float(rigid_from)
        except ValueError:
            return 1, {"ok": False, "error": f"--rigid-from {rigid_from!r}: give auto or a fraction in (0, 1)"}
        if not 0.0 < f < 1.0:
            return 1, {"ok": False, "error": f"--rigid-from {f:g} is not inside (0, 1)"}
    try:
        outs, ph, anat, strain, head_dy, depth = bake(rgba, frames, breaths, depth, lag, rigid_from, fallback)
    except ValueError as exc:
        return 1, {"ok": False, "error": f"{src}: {exc}"}
    except Refused as exc:
        return 2, {"ok": False, "refused": str(exc)}

    name = name or Path(src).stem
    out_dir = Path(out_dir)
    warnings = list(anat["warnings"])
    per_breath = frames / breaths
    if per_breath < SMOOTH_CYCLE_FRAMES:
        warnings.append(f"few-frames: {per_breath:g} frames per breath (< {SMOOTH_CYCLE_FRAMES}) reads as a twitch")
    recs = [{"index": i, "file": f"{name}_{i:03d}.png", "phase": t, "head_dy_px": dy}
            for i, (t, dy) in enumerate(zip(ph, head_dy))]
    H, W = rgba.shape[:2]
    x0, y0, x1, y1 = anat["box"]
    doc = {
        "tool": "breathe.py",
        "producer": {"skill": "codex-visual", "script": "breathe.py"},
        "source": os.path.abspath(str(src)),
        "source_sha256": hashlib.sha256(Path(src).read_bytes()).hexdigest(),
        "canvas": [W, H],
        "pivot": "foot-center",
        "pivot_norm": foot_pivot(rgba, anat),
        "fps_hint": float(fps),
        "loop": True,
        "register": {"mode": "keep", "ref": 0},
        "verdict": {"ok": True, "faults": []},
        "breathe": {"frames": frames, "breaths": breaths, "depth": depth,
                    "depth_source": "auto" if depth_arg == "auto" else "given", "lag": lag,
                    "rigid_from": rigid_from, "rigid_row": anat["rigid_row"], "rigid_source": anat["rigid_source"],
                    "neck_row": anat["neck_row"], "basis_row": anat["basis_row"], "axis_x": anat["axis_x"],
                    "torso_half": anat["torso_half"], "max_half": anat["max_half"],
                    "has_appendage": bool(anat["has_appendage"]), "content_box": [x0, y0, x1, y1],
                    "identity_rows": identity_rows(anat), "row_strain": round(strain, 6), "max_row_strain": MAX_ROW_STRAIN,
                    "period_s": round(per_breath / fps, 4), "warnings": warnings},
        "frames": recs,
    }
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for fr, rec in zip(outs, recs):
            Image.fromarray(fr, "RGBA").save(out_dir / rec["file"])
        (out_dir / "frames.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    except OSError as exc:
        return 1, {"ok": False, "error": f"cannot write to {out_dir}: {exc}"}
    return 0, {"ok": True, "written": len(recs), "out_dir": str(out_dir), "frames_json": str(out_dir / "frames.json"),
               "rigid_row": anat["rigid_row"], "rigid_source": anat["rigid_source"], "row_strain": round(strain, 4),
               "depth": depth, "head_dy_px": [min(head_dy), max(head_dy)], "pivot_norm": doc["pivot_norm"], "warnings": warnings}


# --------------------------------------------------------------- selftest ----

def _figure(W=64, H=96, top=14, wide_arm=False, head_r=10, legs=20):
    """A sentry: round head, narrow neck, torso, two legs; outline, skin, coat, boots."""
    a = np.zeros((H, W, 4), np.uint8)
    ink, skin, coat, boot = (20, 18, 30, 255), (230, 190, 150, 255), (40, 90, 160, 255), (70, 50, 30, 255)
    cx = W // 2
    yy, xx = np.mgrid[0:H, 0:W]
    head_c, r = top + head_r, head_r
    d = np.hypot(yy - head_c, xx - cx)
    a[d <= r] = ink
    a[d <= r - 1] = skin
    neck0, neck1 = head_c + r - 1, head_c + r + 4
    a[neck0:neck1, cx - 3:cx + 3] = ink
    a[neck0:neck1, cx - 2:cx + 2] = skin
    t0, t1, half = neck1, neck1 + 30, 13
    a[t0:t1, cx - half:cx + half] = ink
    a[t0 + 1:t1 - 1, cx - half + 1:cx + half - 1] = coat
    if wide_arm:
        a[t0 + 4:t0 + 8, cx + half:cx + half + 12] = ink
    l1 = t1 + legs
    for lx in (cx - 9, cx + 3):
        a[t1:l1, lx:lx + 6] = ink
        a[t1:l1 - 1, lx + 1:lx + 5] = boot
    return a, l1


def _colours(arr):
    flat = arr.reshape(-1, 4)
    return {tuple(p) for p in flat[flat[:, 3] != 0]}


def selftest():
    checks = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        fig, feet = _figure()
        Image.fromarray(fig, "RGBA").save(t / "sentry_idle.png")
        anat = analyze(fig)
        checks.append(("auto finds the neck", anat["rigid_source"] == "neck"
                       and 19 <= anat["rigid_row"] <= 25))

        code, res = run(t / "sentry_idle.png", t / "out", frames=8, breaths=2, depth=0.06, lag=0.10, fps=8)
        checks.append(("written", code == 0 and res["written"] == 8))
        doc = json.loads((t / "out" / "frames.json").read_text())
        frames = [np.asarray(Image.open(t / "out" / r["file"]).convert("RGBA")) for r in doc["frames"]]
        x0, y0, x1, y1 = anat["box"]
        K = identity_rows(anat)
        checks.append(("identity rows above the fade", 0 < K < anat["rigid_row"] and doc["breathe"]["identity_rows"] == K))
        head = fig[y0:y0 + K]
        head_ok, feet_ok, colour_ok = True, True, True
        cols = _colours(fig)
        for fr in frames:
            rows = np.flatnonzero((fr[..., 3] != 0).any(axis=1))
            top = int(rows[0])
            head_ok &= np.array_equal(fr[top:top + K], head)
            feet_ok &= int(rows[-1]) == y1 - 1 and np.array_equal(fr[y1 - 1], fig[y1 - 1])
            colour_ok &= _colours(fr) <= cols
        checks.append(("head rows bit-identical", head_ok))
        checks.append(("foot row fixed", feet_ok))
        checks.append(("colour set within input", colour_ok))
        checks.append(("the breath moves the head", len({r["head_dy_px"] for r in doc["frames"]}) > 1))
        checks.append(("equal phases bit-identical (0 == 4)", np.array_equal(frames[0], frames[4])
                       and np.array_equal(frames[1], frames[5])))
        nth, _ = warp(fig, anat, 0.06, 0.10, phases(9, 1)[0])
        closes, _ = warp(fig, anat, 0.06, 0.10, ((8 * 2) % 8) / 8)
        checks.append(("loop closes (frame n is frame 0)", np.array_equal(closes, frames[0])
                       and np.array_equal(nth, frames[0])))
        ident, _ = warp(fig, anat, 0.06, 0.0, 0.0)
        checks.append(("zero phase without lag is the input", np.array_equal(ident, fig)))
        checks.append(("frames.json shape", doc["register"] == {"mode": "keep", "ref": 0}
                       and list(doc["verdict"]) == ["ok", "faults"] and doc["verdict"]["ok"] is True
                       and doc["producer"] == {"skill": "codex-visual", "script": "breathe.py"}
                       and doc["fps_hint"] == 8.0 and list(doc)[-1] == "frames"
                       and doc["pivot_norm"] == [0.5, round((96 - feet) / 96, 6)]))

        code, res = run(t / "sentry_idle.png", t / "manual", frames=6, rigid_from="0.3")
        checks.append(("explicit fraction", code == 0 and res["rigid_source"] == "manual"
                       and res["rigid_row"] == int(math.floor(0.3 * anat["height"] + 0.5))))

        blob = np.zeros((64, 64, 4), np.uint8)
        yy, xx = np.mgrid[0:64, 0:64]
        blob[(np.hypot((yy - 40) / 22.0, (xx - 32) / 24.0) <= 1.0) & (yy < 63)] = (90, 200, 90, 255)
        checks.append(("no neck falls back to a fraction", analyze(blob)["rigid_source"] == "fraction-fallback"))

        chibi, _ = _figure(W=96, H=96, top=4, head_r=22, legs=10)
        ca = analyze(chibi)
        checks.append(("chibi neck found", ca["rigid_source"] == "neck" and 0.45 <= ca["rigid_row"] / ca["height"] <= 0.60))
        checks.append(("unwritable out exits 1", run(t / "sentry_idle.png", t / "sentry_idle.png" / "x")[0] == 1))

        arm, _ = _figure(wide_arm=True)
        a2 = analyze(arm)
        checks.append(("appendage protected", a2["has_appendage"] and float(protect(a2)(a2["torso_half"] + 12 + a2["axis_x"])) == 1.0))

        code, res = run(t / "sentry_idle.png", t / "strain", frames=8, depth=0.9)
        checks.append(("strain refusal exits 2", code == 2 and "strain" in res["refused"]
                       and not (t / "strain").exists()))
        tight, _ = _figure(top=0)
        Image.fromarray(tight, "RGBA").save(t / "tight.png")
        code, res = run(t / "tight.png", t / "clip", frames=8, depth=0.2, lag=0.0)
        checks.append(("off-canvas refusal exits 2", code == 2 and "off the canvas" in res["refused"]
                       and not (t / "clip").exists()))
        proc = subprocess.run([sys.executable, __file__, str(t / "sentry_idle.png"), "--out-dir", str(t / "cli"),
                               "--frames", "8", "--depth", "0.9"], capture_output=True, text=True)
        checks.append(("CLI refusal exit code 2", proc.returncode == 2 and json.loads(proc.stdout)["ok"] is False))
        Image.new("RGBA", (16, 16)).save(t / "empty.png")
        checks.append(("empty input exits 1", run(t / "empty.png", t / "e")[0] == 1))
        checks.append(("bad fraction exits 1", run(t / "sentry_idle.png", t / "b", rigid_from="1.5")[0] == 1))
        big = np.asarray(Image.fromarray(fig, "RGBA").resize((fig.shape[1] * 4, fig.shape[0] * 4), Image.NEAREST))
        Image.fromarray(big, "RGBA").save(t / "big.png")
        code, res = run(t / "big.png", t / "big", frames=8)
        lift = max(abs(v) for v in res.get("head_dy_px", [99]))
        cap = max(HEAD_LIFT_PX, HEAD_LIFT_FRACTION * analyze(big)["height"]) + 1
        checks.append((f"auto depth keeps a large figure's head lift small ({lift} px <= {cap:.0f})",
                       code == 0 and res["depth"] < MAX_DEPTH_AUTO and lift <= cap))
        code, res = run(t / "big.png", t / "big06", frames=8, depth="0.06")
        checks.append(("a given --depth is used as is", code == 0 and res["depth"] == 0.06
                       and max(abs(v) for v in res["head_dy_px"]) > cap))
        checks.append(("bad --depth exits 1", run(t / "sentry_idle.png", t / "d", depth="deep")[0] == 1))
    failed = [name for name, ok in checks if not ok]
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": len(checks), "failed": failed}))
    return 0 if not failed else 1


def main():
    if sys.argv[1:] == ["selftest"]:
        return selftest()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("image", nargs="?", help="the still idle pose (RGBA, transparent background)")
    p.add_argument("--out-dir", help="where the frames and frames.json go")
    p.add_argument("--frames", type=int, default=12, help="frames in the loop (default 12)")
    p.add_argument("--breaths", type=int, default=1, help="breaths per loop (default 1)")
    p.add_argument("--depth", default=DEFAULT_DEPTH,
                   help="total stretch as a fraction of the body below the neck, or auto (default): "
                        f"the head lifts about max({HEAD_LIFT_PX} px, {HEAD_LIFT_FRACTION * 100:g}%% of the height), "
                        f"depth at most {MAX_DEPTH_AUTO}")
    p.add_argument("--lag", type=float, default=DEFAULT_LAG,
                   help=f"phase delay of the upper body, fraction of a breath (default {DEFAULT_LAG})")
    p.add_argument("--rigid-from", default="auto",
                   help="auto (the neck), or the fraction of the content height, from the top, that stays rigid")
    p.add_argument("--rigid-fallback", type=float, default=DEFAULT_FALLBACK,
                   help=f"the fraction auto uses when no neck is found (default {DEFAULT_FALLBACK})")
    p.add_argument("--fps", type=float, default=8.0, help="fps_hint written to frames.json (default 8)")
    p.add_argument("--name", help="frame file stem (default: the input's stem)")
    p.add_argument("--selftest", action="store_true")

    def usage_error(msg):                     # exit 2 means a refusal here, so a usage error is 1
        p.print_usage(sys.stderr)
        print(f"breathe.py: error: {msg}", file=sys.stderr)
        sys.exit(1)

    p.error = usage_error
    a = p.parse_args()
    if a.selftest:
        return selftest()
    if not a.image or not a.out_dir:
        p.print_usage(sys.stderr)
        print("breathe.py: error: IMAGE and --out-dir are required (or --selftest)", file=sys.stderr)
        return 1
    if not 0.0 < a.rigid_fallback < 1.0:
        print("breathe.py: error: --rigid-fallback must be inside (0, 1)", file=sys.stderr)
        return 1
    code, res = run(a.image, a.out_dir, a.frames, a.breaths, a.depth, a.lag, a.rigid_from, a.rigid_fallback,
                    a.fps, a.name)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
