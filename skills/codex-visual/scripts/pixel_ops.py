#!/usr/bin/env python3
"""pixel_ops.py — the numpy operations the pixel-art path shares.

Not a command (only `--selftest`). `sheet_to_frames.py --pixel-method snap`,
`pixel_snap.py` and `audit_pixel.py` import it, so the tool that writes a
pixel-art frame and the gate that judges it read one definition of a "cell", a
"block" and "on the palette". Keep it beside them — the scripts directory
travels as a whole.

A generated "pixel art" image is not pixel art: each intended pixel is a block
of several source pixels, the blocks are uneven, their edges are anti-aliased
and the lattice starts at an arbitrary phase. Three steps turn it into one
pixel per cell:

  fit      the CELL COUNT is the caller's (the art bible's Pixel spec); the cut
           lines are fitted to the image's own colour edges. `fit_axis` finds the
           global phase of an exact number of cells, and with `warp` moves each
           cut by at most 45% of the nominal spacing onto the nearest edge while
           penalising uneven gaps. Every cut is an integer source coordinate and
           the cuts always cover the whole image.
  recover  one colour per cell. `robust` keeps the cell's centre sample exactly
           unless it is an isolated impulse (no two neighbours agree with it),
           in which case the median of a 5 x 5 sample grid replaces it; cells are
           never averaged, so an edge blend cannot become a new colour.
  palette  colours are counted on the recovered cells, not on the source:
           `build_palette` picks at most K real colours from every image of a
           set together, `apply_palette` maps each colour to its nearest entry
           (CIEDE2000 on sRGB/D65 Lab by default, plain RGB on request).

Definitions (each is a number the scripts print):

  profile       per axis, the mean over the other axis of the largest
                premultiplied channel step between neighbouring pixels, capped at
                0.35 and smoothed 1-2-1. Its peaks are where colours change.
  edge_fit      how much of the profile's peak weight sits on the cut lines, less
                what a random lattice of that spacing would catch: 0 none, 1 all.
  unit_gaps     how many neighbouring peaks are one cell apart (weighted): 0-1.
                `edge_fit` alone reads high on an image with few edges and for
                any spacing that divides the true one; `unit_gaps` alone ignores
                the phase. Lattice evidence is min(edge_fit, unit_gaps), and it
                is always read from the UNWARPED fit — a warped fit moves its
                cuts onto the peaks, so its own score flatters a wrong count.
  native block  `block_estimate`: the most common gap between neighbouring peaks,
                in source px. Advisory: cell count ~ cell px / native block.
  block         `integer_block`, on an OUTPUT image: the GCD of the spacings
                between the columns (rows) where anything changes. A clean xF
                NEAREST upscale reads F; one resampled row reads 1.
  uniform       `block_stats`: the share of non-empty block x block tiles whose
                pixels are all one RGBA value.

Images are float32 HxWx4 in [0, 1], non-premultiplied, RGB zero where alpha is 0
(`to_float`), except where a name says `_u8`. Profiles are computed on every
pixel; an image is never resized to be measured.

  pixel_ops.py --selftest      synthetic images in memory; `verdict OK|FAIL`

Exit codes (--selftest)
  0  every check passed
  1  a check failed, or bad arguments

Requires Pillow and numpy (codex's imagegen venv has both: ~/.codex/imagegen-venv/bin/python).
"""
# ---------------------------------------------------------------------------
# Third-party code. The following functions are ported, with identifiers and
# return types adapted, from Real-PixelArt
#   https://github.com/Bocchi-The-Glock/Real-PixelArt
#   commit 17ce487597dbc6c04c630226a0f499108a0e20ac
#
#   grid.py      smooth, peaks, _phase, _target_axis (here _fit_axis / fit_axis),
#                the gradient and profile part of extract_features
#                (edge_profiles), the edge_fit and unit_gaps formulas of _measure
#                (lattice_evidence, which applies them to the peaks _target_axis
#                fits rather than to _axis's), the edge-gap density proposal of _axis
#                (block_estimate), and the idea of _exact_integer_grid
#                (integer_block, re-targeted to measure an output image)
#   sampling.py  _resolve_alpha_mode, _cell_sums, _sample_positions,
#                recover_cells, rgb_to_lab, delta_e_2000, distances, nearest,
#                _representatives, _select_palette; process_colors is rewritten
#                as build_palette / apply_palette
#
# CIEDE2000 equations and reference pairs: G. Sharma, W. Wu and E. N. Dalal,
# "The CIEDE2000 color-difference formula: implementation notes, supplementary
# test data, and mathematical observations", Color Research & Application 30(1),
# 2005.
#
# MIT License
#
# Copyright (c) 2026 Sixiang Wang
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ---------------------------------------------------------------------------
import math
import os
import re
import sys

import numpy as np
from PIL import Image

STEP_CAP = 0.35        # a channel step above this counts as this much in a profile
PEAK_SHARE = 0.16      # a profile peak must clear this share of the profile's range
PEAK_FLOOR = 0.0008    # ...and the range itself must be at least this
WARP_REACH = 0.45      # a cut may move this share of the nominal spacing
MIN_PEAKS = 4          # fewer peaks than this is no lattice evidence
EVIDENCE_FLOOR = 0.30  # below this an unwarped fit falls back to the equal split
BLOCK_RANGE = (2.0, 64.0)   # native block sizes `block_estimate` looks for, source px
SOLID = 127            # alpha above this is "opaque" when a palette is read from a PNG
PALETTE_PNG_MAX = 256  # a PNG with more distinct colours than this is not a palette
METRICS = ("lab", "rgb")
SAMPLING = ("robust", "center", "median")


# ------------------------------------------------------------ conversion ----
def to_float(im):
    """PIL image (or uint8 HxWx3/4 array) -> float32 HxWx4 in [0, 1], non-premultiplied,
    RGB zeroed where alpha is 0 so hidden colour can never vote."""
    if isinstance(im, Image.Image):
        a = np.asarray(im.convert("RGBA"))
    else:
        a = np.asarray(im)
        if a.dtype != np.uint8 or a.ndim != 3 or a.shape[2] not in (3, 4):
            raise ValueError("to_float takes a PIL image or a uint8 HxWx3/4 array")
        if a.shape[2] == 3:
            a = np.dstack((a, np.full(a.shape[:2], 255, np.uint8)))
    out = a.astype(np.float32)
    out /= 255.0
    out[out[..., 3] == 0, :3] = 0
    return np.ascontiguousarray(out)


def to_u8(rgba):
    """float HxWx4 -> uint8 (rint), RGB zeroed where the written alpha is 0."""
    out = np.rint(np.clip(rgba, 0, 1) * 255).astype(np.uint8)
    out[out[..., 3] == 0, :3] = 0
    return out


def to_image(rgba):
    return Image.fromarray(to_u8(rgba), "RGBA")


def _need_float(rgba):
    """Refuse anything but a float HxWx4 array: a uint8 or RGB array would be measured wrongly, not loudly."""
    if not isinstance(rgba, np.ndarray) or rgba.ndim != 3 or rgba.shape[2] != 4 or rgba.dtype.kind != "f":
        raise ValueError("expected a float HxWx4 array (pass the image through to_float)")


def _clean_u8(rgba_u8):
    """uint8 HxWx4 with the RGB under alpha 0 zeroed — a PNG's hidden colour is not a change."""
    a = np.asarray(rgba_u8)
    if a.dtype != np.uint8 or a.ndim != 3 or a.shape[2] != 4:
        raise ValueError("expected a uint8 HxWx4 array")
    out = a.copy()
    out[out[..., 3] == 0, :3] = 0
    return out


# -------------------------------------------------------------- profiles ----
def smooth(values, radius=1):
    kernel = np.array([1., 2., 1.]) if radius == 1 else np.ones(2 * radius + 1)
    return np.convolve(np.pad(values, (radius, radius), mode="edge"), kernel / kernel.sum(), "valid")


def peaks(values, threshold=0.):
    """Local maxima of a 1-D signal; a flat top is represented by its midpoint."""
    if len(values) < 3:
        return np.empty(0, int)
    changes = np.flatnonzero(np.diff(values) != 0) + 1
    starts, ends = np.r_[0, changes], np.r_[changes, len(values)]
    inside = (starts > 0) & (ends < len(values))
    starts, ends = starts[inside], ends[inside]
    valid = ((values[starts] > values[starts - 1]) & (values[starts] > values[ends])
             & (values[starts] >= threshold))
    return ((starts[valid] + ends[valid] - 1) // 2).astype(int)


def edge_profiles(rgba):
    """(profile_x, profile_y): where colours change along each axis.

    The step between pixel i-1 and pixel i is stored AT i (column 0 and row 0
    hold nothing), on premultiplied colour and on alpha, the largest channel
    winning. A cut line at i therefore sits exactly on the step it explains;
    shifting this by one pixel shifts every fit.
    """
    _need_float(rgba)
    alpha = rgba[..., 3]
    gx = np.zeros(alpha.shape, np.float32)
    gy = np.zeros_like(gx)
    for channel in range(4):
        v = rgba[..., channel] * alpha if channel < 3 else alpha
        target = gx[:, 1:]
        np.maximum(target, np.abs(np.diff(v, axis=1)), out=target)
        target = gy[1:]
        np.maximum(target, np.abs(np.diff(v, axis=0)), out=target)
    return (smooth(np.minimum(gx, STEP_CAP).mean(axis=0)),
            smooth(np.minimum(gy, STEP_CAP).mean(axis=1)))


def _profile_peaks(profile):
    """(peak positions, baseline, amplitude): the peaks a fit is allowed to use."""
    baseline = float(np.min(profile))
    amplitude = float(np.max(profile)) - baseline
    positions = [int(p) for p in peaks(profile, baseline + max(PEAK_FLOOR, amplitude * PEAK_SHARE))]
    return positions, baseline, amplitude


# ------------------------------------------------------------ cut fitting ----
def _phase(axis, spacing):
    pos, weights = axis["pos"], axis["weights"]
    if not len(pos):
        return 0.
    phases = np.linspace(0, spacing, min(64, max(12, int(spacing * 4))), endpoint=False)
    distance = np.abs((pos[None] - phases[:, None] + spacing / 2) % spacing - spacing / 2)
    fit = np.sum(weights * np.exp(-.5 * (distance / max(.6, .12 * spacing)) ** 2), axis=1)
    best = phases[int(np.argmax(fit))]
    for _ in range(2):
        residual = (pos - best + spacing / 2) % spacing - spacing / 2
        keep = np.abs(residual) < max(.8, .2 * spacing)
        if keep.any():
            best = (best + np.average(residual[keep], weights=weights[keep])) % spacing
    return 0. if min(best, spacing - best) < 1e-7 else float(best)


def _alignment(positions, evidence, lines, spacing):
    """edge_fit: the peak weight within reach of a cut line, less what chance would catch."""
    count = len(lines) - 1
    tolerance = max(.65, .14 * spacing)
    total, weight = 0., 0.
    line_values = np.array(lines, dtype=float)
    for position in positions:
        upper = min(count, max(1, int(np.searchsorted(line_values, position))))
        distance = min(abs(position - lines[upper]), abs(position - lines[upper - 1]))
        total += evidence[position] * math.exp(-.5 * (distance / tolerance) ** 2)
        weight += evidence[position]
    chance = min(.85, 2.5066 * tolerance / spacing)
    return min(1., max(0., (total / weight - chance) / (1 - chance)))


def _fit_axis(profile, count, allow_warp):
    """Fit an exact number of cells with bounded, edge-aware source cuts.

    A global phase initialises the cuts. A small dynamic program can then move
    each cut by at most 45% of nominal spacing while penalising uneven gaps.
    All cuts are integer source coordinates; endpoints keep the full image.
    """
    length = len(profile)
    spacing = length / count
    regular = [round(k * spacing) for k in range(count + 1)]
    positions, baseline, amplitude = _profile_peaks(profile)
    empty = dict(lines=regular, phase=0., edge_fit=0., peaks=len(positions), mean_shift=0., warped=False)
    if count == 1 or count == length or amplitude <= PEAK_FLOOR or not positions:
        return empty
    evidence = [(float(value) - baseline) / amplitude for value in profile]
    position_values = np.array(positions, dtype=float)
    axis = dict(pos=position_values, weights=np.array([evidence[p] for p in positions]))
    radius = WARP_REACH * spacing

    def gap_cost(left, right):
        return .35 * ((right - left - spacing) / spacing) ** 2

    def node_cost(position, anchor):
        return -evidence[position] + .12 * ((position - anchor) / spacing) ** 2

    def bounds(k):
        # Rounding must leave a valid position even when spacing is near one.
        return (max(k, min(regular[k], math.ceil(k * spacing - radius))),
                min(length - count + k, max(regular[k], math.floor(k * spacing + radius))))

    phase = _phase(axis, spacing)
    fitted = min(radius, max(-radius, round((phase - spacing if phase > spacing / 2 else phase) * 8) / 8))
    shifts = sorted(set([0., fitted] + [float(v) for v in np.linspace(-radius, radius, 17)]))
    best_cost, global_cuts, global_phase = math.inf, regular, 0.
    for shift in shifts:
        cuts, cost = [0], 0.
        for k in range(1, count):
            lo, hi = bounds(k)
            position = min(hi, max(lo, round(k * spacing + shift)))
            cuts.append(position)
            cost += node_cost(position, k * spacing) + gap_cost(cuts[k - 1], position)
        cost += gap_cost(cuts[-1], length)
        if cost < best_cost - 1e-12:
            best_cost, global_cuts, global_phase = cost, cuts + [length], shift
    lines = global_cuts
    if allow_warp and spacing >= 2:
        candidates, parents, previous_cost = [[0]], [[-1]], [0.]
        for k in range(1, count):
            lo, hi = bounds(k)
            if hi - lo < 17:
                choices = list(range(lo, hi + 1))
            else:
                left, right = np.searchsorted(position_values, [lo, hi + 1])
                local = sorted(positions[left:right], key=lambda p: (-evidence[p], p))[:7]
                choices = sorted(set([round(float(p)) for p in np.linspace(lo, hi, 9)]
                                     + local + [global_cuts[k]]))
            scores, back = [math.inf] * len(choices), [-1] * len(choices)
            for j, position in enumerate(choices):
                unary = node_cost(position, global_cuts[k])
                for i, previous in enumerate(candidates[k - 1]):
                    if previous >= position:
                        continue
                    score = previous_cost[i] + unary + gap_cost(previous, position)
                    if score < scores[j] - 1e-12:
                        scores[j], back[j] = score, i
            candidates.append(choices)
            parents.append(back)
            previous_cost = scores
        last, best_cost = 0, math.inf
        for i, cost in enumerate(previous_cost):
            score = cost + gap_cost(candidates[-1][i], length)
            if score < best_cost - 1e-12:
                best_cost, last = score, i
        lines = [0] * count + [length]
        for k in range(count - 1, -1, -1):
            lines[k], last = candidates[k][last], parents[k][last]
    return dict(lines=lines, phase=global_phase, edge_fit=_alignment(positions, evidence, lines, spacing),
                peaks=len(positions),
                mean_shift=sum(abs(v - regular[k + 1]) for k, v in enumerate(lines[1:-1])) / (count - 1),
                warped=lines != global_cuts)


def fit_axis(profile, count, warp=False):
    """Cut one axis into exactly `count` cells along its own colour edges.

    Returns dict(lines, phase, edge_fit, peaks, mean_shift, warped):
      lines       count + 1 ints, first 0, last len(profile), strictly increasing
      phase       the global shift of the lattice against the equal split, px
      edge_fit    0-1, of THESE lines — so with warp it flatters; gate on the
                  unwarped value (`fit_cells` does)
      peaks       profile peaks the fit could use
      mean_shift  mean |cut - equal-split cut|, px
      warped      the cuts left the globally shifted lattice
    A flat profile, one cell, or one cell per pixel returns the equal split.
    """
    count = int(count)
    if not 1 <= count <= len(profile):
        raise ValueError(f"cell count {count} does not fit {len(profile)} px (need 1..{len(profile)})")
    out = _fit_axis(np.asarray(profile, dtype=float), count, bool(warp))
    out["lines"] = [int(v) for v in out["lines"]]
    return out


def lattice_evidence(profile, spacing, lines):
    """dict(edge_fit, unit_gaps, peaks) for cut `lines` of nominal `spacing` on one axis.

    Both terms read the same peaks `fit_axis` fits to. `unit_gaps` weights each
    gap between neighbouring peaks by the weaker of the two and scores it by how
    close it is to one spacing. Fewer than MIN_PEAKS peaks is no evidence: 0, 0.
    """
    profile = np.asarray(profile, dtype=float)
    positions, baseline, amplitude = _profile_peaks(profile)
    if len(positions) < MIN_PEAKS or amplitude <= PEAK_FLOOR:
        return dict(edge_fit=0., unit_gaps=0., peaks=len(positions))
    evidence = [(float(value) - baseline) / amplitude for value in profile]
    pos = np.array(positions, dtype=float)
    weights = np.interp(pos, np.arange(len(profile)), profile)
    gaps, gap_weights = np.diff(pos), np.minimum(weights[:-1], weights[1:])
    units = float(np.average(np.exp(-.5 * ((gaps - spacing) / max(.7, .12 * spacing)) ** 2),
                             weights=gap_weights))
    return dict(edge_fit=float(_alignment(positions, evidence, [int(v) for v in lines], spacing)),
                unit_gaps=units, peaks=len(positions))


def _equal_split(length, count):
    spacing = length / count
    return [round(k * spacing) for k in range(count + 1)]


def fit_cells(rgba, nx, ny, warp=True, floor=EVIDENCE_FLOOR):
    """Cut an image into nx x ny cells along its own edges.

    Returns dict(x_lines, y_lines, edge_fit, unit_gaps, peaks, evidence, lattice).
    edge_fit / unit_gaps / peaks are the weaker axis of the UNWARPED fit and
    evidence = min(edge_fit, unit_gaps), whatever `warp` says. `lattice` names
    the lines returned:
      warped    warp is on and the cuts moved off the globally shifted lattice
      fitted    the unwarped phase fit, its evidence at or above `floor`
      uniform   the equal split — what an unwarped fit below the floor returns,
                since a phase read from too few edges is worse than none
    """
    h, w = rgba.shape[:2]
    axes = list(zip(edge_profiles(rgba), (int(nx), int(ny))))
    plain, measured = [], []
    for profile, count in axes:
        fit = fit_axis(profile, count, False)
        plain.append(fit)
        measured.append(lattice_evidence(profile, len(profile) / count, fit["lines"]))
    edge_fit = min(m["edge_fit"] for m in measured)
    unit_gaps = min(m["unit_gaps"] for m in measured)
    evidence = min(edge_fit, unit_gaps)
    lines, lattice = None, "uniform"
    if warp:
        moved = [fit_axis(profile, count, True) for profile, count in axes]
        if any(fit["warped"] for fit in moved):
            lines, lattice = [fit["lines"] for fit in moved], "warped"
    if lines is None and evidence >= floor:
        lines, lattice = [fit["lines"] for fit in plain], "fitted"
    if lines is None:
        lines = [_equal_split(w, int(nx)), _equal_split(h, int(ny))]
    return dict(x_lines=lines[0], y_lines=lines[1], edge_fit=edge_fit, unit_gaps=unit_gaps,
                peaks=min(m["peaks"] for m in measured), evidence=evidence, lattice=lattice)


def sweep_counts(rgba, lo, hi):
    """[(n, edge_fit, unit_gaps)] for every cell count whose spacing is lo..hi px, unwarped.

    n counts cells along x; y takes the count of the same spacing. Each value is
    the weaker axis. The count the image was drawn at is where min(edge_fit,
    unit_gaps) peaks; integer fractions of it read a high edge_fit and a low
    unit_gaps.
    """
    px, py = edge_profiles(rgba)
    if not 0 < lo <= hi:
        raise ValueError("sweep needs 0 < lo <= hi (cell spacing in px)")
    out = []
    for n in range(max(1, math.ceil(len(px) / hi)), min(len(px), math.floor(len(px) / lo)) + 1):
        m = min(len(py), max(1, round(n * len(py) / len(px))))
        fits = [lattice_evidence(p, len(p) / c, fit_axis(p, c, False)["lines"]) for p, c in ((px, n), (py, m))]
        out.append((n, min(f["edge_fit"] for f in fits), min(f["unit_gaps"] for f in fits)))
    return out


def _gap_peak(profile, minimum, maximum):
    """The densest gap between neighbouring profile peaks, in px; 0.0 without evidence."""
    pos = peaks(profile, max(float(profile.max()) * PEAK_SHARE, PEAK_FLOOR))
    # A blurred edge quantises into several near-equal maxima. A run with no real
    # valley between its members is ONE edge at its midpoint; counted separately
    # the ripple would vote for half-sized blocks.
    groups = []
    for p in pos:
        if groups and np.min(profile[groups[-1][-1]:p + 1]) >= .90 * min(profile[groups[-1][-1]], profile[p]):
            groups[-1].append(p)
        else:
            groups.append([p])
    pos = np.array([(g[0] + g[-1]) / 2 for g in groups], dtype=float)
    weights = np.interp(pos, np.arange(len(profile)), profile)
    gaps = np.diff(pos).astype(float)
    gap_weights = np.minimum(weights[:-1], weights[1:])
    if not len(gaps) or maximum < minimum:
        return 0.
    steps = np.arange(minimum, maximum + .125, .25)
    density = np.array([np.sum(gap_weights * np.exp(-.5 * ((gaps - s) / max(.65, .09 * s)) ** 2))
                        for s in steps])
    ix = peaks(np.r_[-1., density, -1.]) - 1
    if not len(ix):
        return 0.
    return float(steps[ix[np.argsort(density[ix], kind="stable")[-1]]])


def block_estimate(rgba):
    """(bx, by): the native block size of a source image, px, quarter-px steps; 0.0 = no evidence.

    Advisory only. Blocks are uneven inside one image, so this is the commonest
    gap, not a lattice: choose the cell count near cell px / block and let the
    fit place the cuts.
    """
    return tuple(_gap_peak(p, BLOCK_RANGE[0], min(BLOCK_RANGE[1], len(p) / 2)) for p in edge_profiles(rgba))


# ------------------------------------------------------------- recovery ----
def _resolve_alpha_mode(alpha, requested):
    if requested not in ("auto", "sample", "binary", "coverage"):
        raise ValueError("alpha must be binary, coverage or sample")
    visible = np.count_nonzero(alpha > 0)
    near_opaque = np.count_nonzero(alpha >= .94) / max(visible, 1)
    return ("sample" if requested == "auto" else requested), float(near_opaque)


def _cell_sums(values, xs, ys):
    """Sum half-open source cells, reducing rows before columns for stable rounding."""
    return np.add.reduceat(np.add.reduceat(values, ys[:-1], axis=0), xs[:-1], axis=1)


def _sample_positions(cuts, fractions):
    """Locate fractional samples inside each cell without crossing its right edge."""
    widths = np.diff(cuts)
    return np.minimum(cuts[:-1, None] + (widths[:, None] * fractions).astype(int),
                      cuts[1:, None] - 1)


def recover_cells(rgba, x_lines, y_lines, method="robust", alpha="binary", alpha_cut=0.5):
    """One RGBA value per cell -> (cells float32 ny x nx x 4, confidence ny x nx, stats).

    method   robust  the centre sample, kept exactly; replaced by the median of a
                     5 x 5 sample grid only when it is an unsupported impulse
                     (fewer than three of the 3 x 3 pixels round the centre agree
                     with it, and it differs from the median)
             center  the centre sample
             median  the per-channel median of the 5 x 5 samples
    alpha    binary    the selected sample's alpha cut at `alpha_cut`: 0 or 1
             sample    the selected sample's alpha as it is
             coverage  the cell's mean alpha (a soft edge; never use it for a
                       sheet a pixel gate will read)
    confidence is the share of samples that agree with the colour chosen.
    stats: supported_central_strokes, rejected_central_impulses, samples_per_cell,
    alpha, source_near_opaque_fraction.
    """
    if method not in SAMPLING:
        raise ValueError("method must be robust, center or median")
    _need_float(rgba)
    resolved_alpha, near_opaque = _resolve_alpha_mode(rgba[..., 3], alpha)
    h, w = rgba.shape[:2]
    for lines, length in ((x_lines, w), (y_lines, h)):
        lines = np.asarray(lines)
        if (lines.ndim != 1 or len(lines) < 2 or not np.isfinite(lines).all()
                or lines[0] != 0 or lines[-1] != length or np.any(np.diff(lines) <= 0)):
            raise ValueError("cut lines must be finite, increasing and cover the complete input")
    xs, ys = np.rint(x_lines).astype(int), np.rint(y_lines).astype(int)
    widths, heights = np.diff(xs), np.diff(ys)
    if np.any(widths < 1) or np.any(heights < 1):
        raise ValueError("cut lines must cover at least one source pixel")
    ny, nx = len(heights), len(widths)
    area = heights[:, None] * widths[None]
    coverage = _cell_sums(rgba[..., 3], xs, ys) / area
    result = np.zeros((ny * nx, 4), np.float32)
    confidence = np.zeros(ny * nx, np.float32)
    fractions = np.array([.18, .34, .50, .66, .82]) if method != "center" else np.array([.5])
    xp = _sample_positions(xs, fractions)
    yp = _sample_positions(ys, fractions)
    detail_count = rejected_count = 0
    for start in range(0, ny * nx, 1024):
        ids = np.arange(start, min(start + 1024, ny * nx))
        ids = ids[coverage.ravel()[ids] > 0]
        if not len(ids):
            continue
        yy, xx = ids // nx, ids % nx
        samples = rgba[yp[yy, :, None], xp[xx, None, :]].reshape(len(ids), -1, 4)
        rgb, a = samples[..., :3], samples[..., 3]
        valid = a > 1e-6
        centre = samples[:, len(fractions)**2 // 2].copy()
        centre[centre[:, 3] == 0, :3] = 0
        colour, selected_alpha = centre[:, :3].copy(), centre[:, 3].copy()
        support = np.ones(len(ids), np.float32)
        if method != "center":
            median_alpha = np.median(a, axis=1)
            count = valid.sum(axis=1)
            sorted_rgb = np.sort(np.where(valid[..., None], rgb, np.inf), axis=1)
            median = sorted_rgb[np.arange(len(ids)), np.maximum(0, (count - 1) // 2)]
            median[count == 0] = 0
            near_median = valid & (np.max(abs(rgb - median[:, None]), axis=2) < .12)
            if method == "median":
                colour = median
                selected_alpha = median_alpha
                support = near_median.sum(axis=1) / np.maximum(count, 1)
            else:
                # Compare premultiplied colour AND alpha. Hidden transparent RGB
                # cannot turn a transparent centre into a spurious colour outlier.
                cx, cy = xs[xx] + widths[xx] // 2, ys[yy] + heights[yy] // 2
                px = np.clip(cx[:, None] + [-1, 0, 1], xs[xx, None], xs[xx + 1, None] - 1)
                py = np.clip(cy[:, None] + [-1, 0, 1], ys[yy, None], ys[yy + 1, None] - 1)
                patch = rgba[py[:, :, None], px[:, None, :]].reshape(-1, 9, 4)
                central_pm = centre[:, :3] * centre[:, 3, None]
                distance = np.maximum(np.max(abs(patch[..., :3] * patch[..., 3, None]
                                                - central_pm[:, None]), axis=2),
                                      abs(patch[..., 3] - centre[:, 3, None]))
                near = distance < .10
                # Two adjacent supporters retain a one-source-pixel-wide line;
                # a 2x2 highlight also passes. A single impulse does not.
                coherent = near.sum(axis=1) >= 3
                tiny = (widths[xx] <= 2) | (heights[yy] <= 2)
                deviation = np.max(abs(centre[:, :3] - median), axis=1) > .10
                reject = ~coherent & ~tiny & (deviation | (abs(centre[:, 3] - median_alpha) > .10))
                colour[reject] = median[reject]
                selected_alpha[reject] = median_alpha[reject]
                rejected_count += int(reject.sum())
                detail_count += int(np.count_nonzero(coherent & deviation & (centre[:, 3] > 0)))
                support = np.where(reject, near_median.sum(axis=1) / np.maximum(count, 1),
                                   near.sum(axis=1) / 9)
                # Deliberately keep the supported centre exactly: averaging the
                # whole colour cluster reintroduces edge blends and blurs lines.
        result[ids, :3], result[ids, 3] = colour, selected_alpha
        confidence[ids] = support
    if resolved_alpha == "coverage":
        missing = (coverage.ravel() > 0) & (result[:, 3] == 0)
        result[:, 3] = coverage.ravel()
        # Exact premultiplied fallback only for explicitly requested coverage:
        # a tiny corner fragment must not become a whole opaque output cell.
        if missing.any():
            for c in range(3):
                sums = _cell_sums(rgba[..., c] * rgba[..., 3], xs, ys)
                means = sums / np.maximum(coverage * area, 1e-8)
                result[missing, c] = means.ravel()[missing]
    elif resolved_alpha == "binary":
        result[:, 3] = result[:, 3] >= alpha_cut
    result[result[:, 3] <= 0, :3] = 0
    return (result.reshape(ny, nx, 4), confidence.reshape(ny, nx),
            dict(supported_central_strokes=detail_count, rejected_central_impulses=rejected_count,
                 samples_per_cell=len(fractions)**2, alpha=resolved_alpha,
                 source_near_opaque_fraction=near_opaque))


# ---------------------------------------------------------------- colour ----
def rgb_to_lab(rgb):
    """Encoded sRGB in [0, 255] -> CIE Lab (D65). No display or ICC calibration."""
    rgb = np.asarray(rgb, dtype=np.float64) / 255.
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    xyz = linear @ np.array([[.4124564, .2126729, .0193339],
                             [.3575761, .7151522, .1191920],
                             [.1804375, .0721750, .9503041]])
    xyz /= [.95047, 1., 1.08883]
    d = 6 / 29
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4 / 29)
    x, y, z = np.moveaxis(f, -1, 0)
    return np.stack((116 * y - 16, 500 * (x - y), 200 * (y - z)), axis=-1)


def delta_e_2000(first, second):
    """CIEDE2000 (kL = kC = kH = 1) between broadcast arrays ending in three Lab components."""
    l1, a1, b1 = np.moveaxis(np.asarray(first, dtype=np.float64), -1, 0)
    l2, a2, b2 = np.moveaxis(np.asarray(second, dtype=np.float64), -1, 0)
    cbar = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    g = .5 * (1 - np.sqrt(cbar ** 7 / (cbar ** 7 + 25 ** 7)))
    ap1, ap2 = (1 + g) * a1, (1 + g) * a2
    c1, c2 = np.hypot(ap1, b1), np.hypot(ap2, b2)
    h1 = np.mod(np.degrees(np.arctan2(b1, ap1)), 360)
    h2 = np.mod(np.degrees(np.arctan2(b2, ap2)), 360)
    zero = c1 * c2 == 0
    dh = h2 - h1
    # Tolerance makes exactly opposite hues stable under floating-point rounding.
    dh = np.where(dh > 180 + 1e-12, dh - 360, np.where(dh < -180 - 1e-12, dh + 360, dh))
    dh = np.where(zero, 0, dh)
    dl, dc = l2 - l1, c2 - c1
    dh_term = 2 * np.sqrt(c1 * c2) * np.sin(np.radians(dh / 2))
    lm, cm = (l1 + l2) / 2, (c1 + c2) / 2
    hm = np.where(np.abs(h1 - h2) <= 180 + 1e-12, (h1 + h2) / 2,
                  np.where(h1 + h2 < 360, (h1 + h2 + 360) / 2, (h1 + h2 - 360) / 2))
    hm = np.where(zero, h1 + h2, hm)
    t = (1 - .17 * np.cos(np.radians(hm - 30)) + .24 * np.cos(np.radians(2 * hm))
         + .32 * np.cos(np.radians(3 * hm + 6)) - .20 * np.cos(np.radians(4 * hm - 63)))
    sl = 1 + .015 * (lm - 50) ** 2 / np.sqrt(20 + (lm - 50) ** 2)
    sc, sh = 1 + .045 * cm, 1 + .015 * cm * t
    rt = -2 * np.sqrt(cm ** 7 / (cm ** 7 + 25 ** 7)) * np.sin(
        np.radians(60 * np.exp(-((hm - 275) / 25) ** 2)))
    vl, vc, vh = dl / sl, dc / sc, dh_term / sh
    return np.sqrt(np.maximum(0, vl * vl + vc * vc + vh * vh + rt * vc * vh))


def distances(first, second, metric):
    """Squared distances; inputs already transformed to the selected space."""
    if metric == "lab":
        return delta_e_2000(first, second) ** 2
    return np.sum((first - second) ** 2, axis=-1)


def nearest(points, palette, metric):
    """Exact full-palette search, bounded temporary memory; stable first-index ties."""
    result = np.empty(len(points), dtype=np.int32)
    chunk = max(32, 32768 // max(1, len(palette)))
    for start in range(0, len(points), chunk):
        result[start:start + chunk] = np.argmin(
            distances(points[start:start + chunk, None], palette[None], metric), axis=1)
    return result


def _space(rgb, metric):
    if metric not in METRICS:
        raise ValueError("metric must be lab or rgb")
    return rgb_to_lab(rgb) if metric == "lab" else np.asarray(rgb, dtype=np.float64)


def _representatives(rgb, weights, budget=2048):
    """Bound adaptive clustering using RGB bins, each represented by a real input colour."""
    if len(rgb) <= budget:
        return rgb, weights
    for shift in (3, 4, 5):
        bins, inv = np.unique(rgb >> shift, axis=0, return_inverse=True)
        inv = inv.ravel()
        if len(bins) <= budget:
            break
    # Highest-support real colour per bin, with original RGB order breaking ties.
    order = np.lexsort((np.arange(len(rgb)), -weights, inv))
    first = np.r_[True, inv[order][1:] != inv[order][:-1]]
    return rgb[order[first]], np.bincount(inv, weights=weights)


def _select_palette(rgb, weights, count, metric):
    """Deterministic weighted, constrained clustering; at most eight refinement rounds.

    Frequency/diversity seeds keep small contrasting colours eligible. Centres are
    snapped to real members; a move is accepted only if it lowers the selected
    metric. A bounded heuristic, not an optimal K-colour solution.
    """
    if len(rgb) <= count:
        return rgb
    points = _space(rgb, metric)
    selected = [int(np.argmax(weights))]
    best = distances(points, points[selected[0]], metric)
    log_weights = np.log1p(weights)
    for _ in range(1, count):
        priority = best * log_weights
        priority[selected] = -1
        index = int(np.argmax(priority))
        selected.append(index)
        best = np.minimum(best, distances(points, points[index], metric))
    selected = np.array(selected)
    for _ in range(8):
        assignment = nearest(points, points[selected], metric)
        previous = selected.copy()
        for cluster in range(count):
            members = np.flatnonzero(assignment == cluster)
            if not len(members):
                continue
            mean = np.average(points[members], axis=0, weights=weights[members])
            candidate = members[np.argmin(distances(points[members], mean, metric))]
            old_cost = np.dot(weights[members], distances(points[members], points[selected[cluster]], metric))
            new_cost = np.dot(weights[members], distances(points[members], points[candidate], metric))
            if new_cost < old_cost - 1e-9:
                selected[cluster] = candidate
        if np.array_equal(previous, selected):
            break
    return rgb[np.unique(selected)]


def _visible_colours(rgba_u8):
    """(distinct RGB of the visible pixels, inverse index per visible pixel, coverage weight per colour)."""
    visible = rgba_u8[..., 3] > 0
    rgb, inv = np.unique(rgba_u8[visible, :3], axis=0, return_inverse=True)
    inv = inv.ravel()
    weights = np.bincount(inv, weights=rgba_u8[visible, 3].astype(float) / 255., minlength=len(rgb))
    return rgb, inv, weights


def build_palette(rgba_u8_list, count, metric="lab"):
    """At most `count` colours for a whole set -> uint8 (K', 3), K' <= count.

    Built from the visible pixels of every image together (each weighted by its
    alpha, so a binary-alpha sheet votes with its opaque pixels and transparent
    ones never vote). Every entry is a colour that occurs in the set, and the
    same set always gives the same palette, whatever order its images come in.
    """
    count = int(count)
    if count < 1:
        raise ValueError("palette size must be at least 1")
    if metric not in METRICS:
        raise ValueError("metric must be lab or rgb")
    pixels, alphas = [], []
    for image in rgba_u8_list:
        a = np.asarray(image)
        if a.dtype != np.uint8 or a.ndim != 3 or a.shape[2] != 4:
            raise ValueError("build_palette takes uint8 HxWx4 arrays")
        visible = a[..., 3] > 0
        pixels.append(a[visible, :3])
        alphas.append(a[visible, 3].astype(float) / 255.)
    if not pixels or not sum(len(p) for p in pixels):
        return np.zeros((0, 3), np.uint8)
    rgb, inv = np.unique(np.concatenate(pixels), axis=0, return_inverse=True)
    weights = np.bincount(inv.ravel(), weights=np.concatenate(alphas), minlength=len(rgb))
    if len(rgb) > count:
        rgb = _select_palette(*_representatives(rgb, weights), count, metric)
    return np.ascontiguousarray(rgb, dtype=np.uint8)


def apply_palette(rgba_u8, palette, metric="lab"):
    """Map every visible colour to its nearest palette entry -> (rgba_u8, stats).

    Alpha is untouched; RGB under alpha 0 is written as 0. stats:
      colours_in     distinct visible colours before
      colours_used   distinct palette entries the image ends up with
      used           their indices into `palette`, ascending
      max_distance   the furthest any colour moved, and
      mean_distance  the per-pixel mean — in CIEDE2000 units for `lab`
                     (about 1 is just noticeable), 0-441 RGB units for `rgb`
    """
    palette = np.asarray(palette)
    if palette.ndim != 2 or palette.shape[1] != 3 or not len(palette):
        raise ValueError("palette must be a non-empty (K, 3) array")
    if palette.dtype.kind not in "iu" or palette.min() < 0 or palette.max() > 255:
        raise ValueError("palette entries must be integers 0-255")
    palette = palette.astype(np.uint8)
    out = _clean_u8(rgba_u8)
    rgb, inv, _ = _visible_colours(out)
    stats = dict(metric=metric, colours_in=int(len(rgb)), colours_used=0, used=[],
                 max_distance=0., mean_distance=0.)
    if not len(rgb):
        _space(palette, metric)
        return out, stats
    points, targets = _space(rgb, metric), _space(palette, metric)
    matched = nearest(points, targets, metric)
    moved = np.sqrt(distances(points, targets[matched], metric))
    out[out[..., 3] > 0, :3] = palette[matched][inv]
    used = np.unique(matched)
    stats.update(colours_used=int(len(used)), used=[int(i) for i in used],
                 max_distance=float(moved.max()),
                 mean_distance=float(np.average(moved, weights=np.bincount(inv, minlength=len(rgb)))))
    return out, stats


# ---------------------------------------------------------- palette files ----
_HEX = re.compile(r"(?<![0-9A-Za-z&])#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9A-Za-z])")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_BOLD_ITEM = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(?:\*\*|__)(.+?)(?:\*\*|__)")
_RULE_ROW = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _hex_rgb(digits):
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))


def _is_section(title, section):
    """A heading or bold label names the section: `Palette`, `3. Palette`, `Palette (locked)`."""
    title = re.sub(r"[*_`]", "", title).strip().lower()
    title = re.sub(r"^[\d.]+\s*", "", title)
    section = section.strip().lower()
    return title == section or (title.startswith(section) and not title[len(section)].isalnum())


def _markdown_section(text, section):
    """The lines under the heading or bold list item named `section`, or None."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        heading, item = _HEADING.match(line), _BOLD_ITEM.match(line)
        if heading and _is_section(heading.group(2), section):
            level, body = len(heading.group(1)), []
            for nxt in lines[i + 1:]:
                h = _HEADING.match(nxt)
                if h and len(h.group(1)) <= level:
                    break
                body.append(nxt)
            return body
        if item and _is_section(item.group(2), section):
            indent, body = len(item.group(1)), [line[item.end():]]
            for nxt in lines[i + 1:]:
                other = _BOLD_ITEM.match(nxt)
                if _HEADING.match(nxt) or (other and len(other.group(1)) <= indent):
                    break
                body.append(nxt)
            return body
    return None


def _markdown_colours(body):
    found = []
    for line in body:
        if _RULE_ROW.match(line):
            continue
        hexes = _HEX.findall(line)
        if not hexes:
            continue
        if "|" in line:                      # a table row: the first column is the role
            name = line.strip().strip("|").split("|")[0]
        else:                                # a plain line: whatever precedes the colour
            name = line[:_HEX.search(line).start()]
        name = re.sub(r"[*_`]", "", name).strip().strip("-+:—–=").strip()
        found += [(_hex_rgb(h), name) for h in hexes]
    return found


def _hex_file_colours(text, path):
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.split(";")[0]
        line = re.split(r"(?:^|\s)#\s", line)[0].strip()      # "# comment" — not "#ff00ff"
        if not line:
            continue
        digits = line.lstrip("#")
        if not re.fullmatch(r"[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8}", digits):
            raise ValueError(f"{path}:{number}: not a hex colour: {line!r}")
        found.append((_hex_rgb(digits[-6:] if len(digits) == 8 else digits), ""))   # 8 digits: AARRGGBB
    return found


def _png_colours(path):
    a = np.asarray(Image.open(path).convert("RGBA"))
    rgb = a[a[..., 3] > SOLID][:, :3]
    distinct, first = np.unique(rgb, axis=0, return_index=True)
    if len(distinct) > PALETTE_PNG_MAX:
        raise ValueError(f"{path}: {len(distinct)} distinct opaque colours — more than "
                         f"{PALETTE_PNG_MAX}, so this is a picture, not a palette")
    return [(tuple(int(v) for v in rgb[i]), "") for i in np.sort(first)]     # in reading order


def read_palette(path, section="Palette", exclude=()):
    """A fixed palette from a file -> (uint8 (K, 3), names).

    .md          the heading, or the bold list item, named `section` (case does
                 not matter); read to the next heading of the same or a higher
                 level. #RRGGBB / #RGB are taken in order from table rows (the
                 first column is the role name) and from plain lines.
    .hex / .txt  one colour per line, the leading # optional; `;` and `# ` start
                 a comment. Eight digits are read as AARRGGBB.
    .png         its distinct opaque colours in reading order, at most 256.
    Duplicates keep their first place. `exclude` is an iterable of (r, g, b) to
    drop — the chroma key, which a palette extracted from a keyed sheet's brief
    tends to list. A colour without a role is named by its hex.
    ValueError: an unknown extension, a missing section, fewer than 2 colours.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".png":
        found = _png_colours(path)
    elif ext in (".md", ".markdown", ".hex", ".txt"):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        if ext in (".hex", ".txt"):
            found = _hex_file_colours(text, path)
        else:
            body = _markdown_section(text, section)
            if body is None:
                raise ValueError(f"{path}: no heading or bold list item named {section!r}")
            found = _markdown_colours(body)
    else:
        raise ValueError(f"{path}: a palette file is .md, .hex, .txt or .png")
    drop = {tuple(int(v) for v in colour) for colour in exclude}
    colours, names = [], []
    for colour, name in found:
        if colour in drop or colour in colours:
            continue
        colours.append(colour)
        names.append(name or "#%02x%02x%02x" % colour)
    if len(colours) < 2:
        where = f" under {section!r}" if ext in (".md", ".markdown") else ""
        raise ValueError(f"{path}: {len(colours)} colour(s){where} — a palette needs at least 2")
    return np.array(colours, np.uint8), names


def write_palette(path, palette):
    """Write a .hex palette: one rrggbb per line, the order kept."""
    with open(path, "w", encoding="utf-8") as handle:
        for r, g, b in np.asarray(palette).reshape(-1, 3):
            handle.write("%02x%02x%02x\n" % (int(r), int(g), int(b)))


# ------------------------------------------------- measuring an output ----
def _change_positions(clean, axis):
    """Columns (axis 1) or rows (axis 0) that differ from the one before them, anywhere."""
    step = np.diff(clean.astype(np.int16), axis=axis)
    return np.flatnonzero(np.any(step != 0, axis=(1 - axis, 2))) + 1


def integer_block(rgba_u8):
    """(bx, by, phase_x, phase_y) of an output image, or None when no lattice can be read.

    Per axis: the GCD of the spacings between the columns (rows) where colour or
    alpha changes, and the offset of that lattice (first change modulo the
    block). RGB under alpha 0 is not a change. One stray resampled column makes
    the GCD 1, which is the point. An axis with fewer than two changes carries
    no spacing and takes the other axis's block; None when that leaves neither.
    """
    clean = _clean_u8(rgba_u8)
    found = []
    for axis in (1, 0):
        positions = _change_positions(clean, axis)
        block = int(np.gcd.reduce(np.diff(positions))) if len(positions) >= 2 else 0
        found.append((block, positions))
    fallback = max(block for block, _ in found)
    if not fallback:
        return None
    out = []
    for block, positions in found:
        block = block or fallback
        out.append((block, int(positions[0] % block) if len(positions) else 0))
    return out[0][0], out[1][0], out[0][1], out[1][1]


def _tile_cuts(length, block, phase):
    start = int(phase) % block
    return np.array(([0] if start else []) + list(range(start, length, block)))


def block_stats(rgba_u8, block, phase=(0, 0)):
    """dict(uniform_pct, blocks, mixed_blocks) for `block` px tiles laid from `phase`.

    `block` is one int or (bx, by). The strip before the phase and a partial
    tile at the far edge count as tiles. A tile is non-empty when any of its
    pixels is visible, and uniform when all of them are one RGBA value;
    uniform_pct is over the non-empty ones (0.0 when there are none).
    """
    clean = _clean_u8(rgba_u8)
    bx, by = (int(block), int(block)) if np.isscalar(block) else (int(block[0]), int(block[1]))
    if bx < 1 or by < 1:
        raise ValueError("block must be at least 1 px")
    xs, ys = _tile_cuts(clean.shape[1], bx, phase[0]), _tile_cuts(clean.shape[0], by, phase[1])
    low = np.minimum.reduceat(np.minimum.reduceat(clean, ys, axis=0), xs, axis=1)
    high = np.maximum.reduceat(np.maximum.reduceat(clean, ys, axis=0), xs, axis=1)
    occupied = high[..., 3] > 0
    mixed = occupied & np.any(low != high, axis=2)
    blocks, bad = int(occupied.sum()), int(mixed.sum())
    return dict(uniform_pct=100.0 * (blocks - bad) / blocks if blocks else 0.0,
                blocks=blocks, mixed_blocks=bad)


# --------------------------------------------------------------- selftest ----
def _courier_cells(rng, nx=20, ny=24, colours=6):
    """A stand-in sprite at one pixel per cell: a noisy blob of a few flat colours, transparent round it."""
    palette = rng.integers(30, 226, size=(colours, 3)).astype(np.uint8)
    cells = np.zeros((ny, nx, 4), np.uint8)
    yy, xx = np.mgrid[0:ny, 0:nx]
    body = ((xx - nx / 2 + .5) / (nx / 2 - 2)) ** 2 + ((yy - ny / 2 + .5) / (ny / 2 - 2)) ** 2 <= 1
    cells[body, :3] = palette[rng.integers(0, colours, size=int(body.sum()))]
    cells[body, 3] = 255
    return cells, palette


def _fake_pixels(cells, block, shift):
    """What a generator returns for it: each cell a `block` px square, the lattice `shift` px off, edges blurred."""
    big = np.repeat(np.repeat(cells, block, axis=0), block, axis=1)
    big = np.roll(big, (shift, shift), axis=(0, 1)).astype(np.float32) / 255.
    pm = np.dstack((big[..., :3] * big[..., 3:], big[..., 3]))
    for axis in (0, 1):
        pad = np.pad(pm, [(1, 1) if a == axis else (0, 0) for a in range(3)], mode="edge")
        lead = [slice(None)] * 3
        mid, tail = list(lead), list(lead)
        lead[axis], mid[axis], tail[axis] = slice(0, -2), slice(1, -1), slice(2, None)
        pm = (pad[tuple(lead)] + 2 * pad[tuple(mid)] + pad[tuple(tail)]) / 4
    alpha = pm[..., 3]
    rgb = np.where(alpha[..., None] > 0, pm[..., :3] / np.maximum(alpha[..., None], 1e-6), 0)
    return to_float(np.rint(np.clip(np.dstack((rgb, alpha)), 0, 1) * 255).astype(np.uint8))


def selftest():
    """Synthetic images in memory; prints one `metric` line per check, then the verdict."""
    import tempfile
    failed = []

    def check(name, value, ok):
        print(f"metric {name} {value}")
        if not ok:
            failed.append(name)

    rng = np.random.default_rng(7)
    block, shift = 6, 2
    truth, colours = _courier_cells(rng)
    ny, nx = truth.shape[:2]
    source = _fake_pixels(truth, block, shift)

    for warp in (False, True):
        fit = fit_cells(source, nx, ny, warp=warp)
        cells, _, _ = recover_cells(source, fit["x_lines"], fit["y_lines"])
        same = 100.0 * float(np.all(to_u8(cells) == truth, axis=2).mean())
        tag = "warp" if warp else "plain"
        check(f"recovered_cells_pct_{tag}", f"{same:.2f}", same == 100.0)
        check(f"lattice_{tag}", fit["lattice"], fit["lattice"] in (("warped", "fitted") if warp else ("fitted",)))
        check(f"evidence_{tag}", f"{fit['evidence']:.3f}", fit["evidence"] >= EVIDENCE_FLOOR)
    plain = fit_axis(edge_profiles(source)[0], nx, False)
    check("phase_px", f"{plain['phase']:+.3f}", abs(plain["phase"] - shift) <= 0.5)
    check("lines_cover", f"{plain['lines'][0]}..{plain['lines'][-1]}",
          plain["lines"][0] == 0 and plain["lines"][-1] == source.shape[1]
          and all(b > a for a, b in zip(plain["lines"], plain["lines"][1:])))

    sweep = sweep_counts(source, 3, 12)
    best = max(sweep, key=lambda row: min(row[1], row[2]))[0]
    check("sweep_peak_cells", best, best == nx)
    bx, by = block_estimate(source)
    check("native_block_px", f"{bx:.2f} {by:.2f}", abs(bx - block) <= 0.5 and abs(by - block) <= 0.5)

    flat = np.zeros((48, 48, 4), np.float32)
    flat[..., 3] = 1
    flat[..., :3] = 0.4
    fit = fit_cells(flat, 8, 8)
    check("flat_lattice", fit["lattice"], fit["lattice"] == "uniform" and fit["x_lines"] == list(range(0, 49, 6)))
    check("flat_block_estimate", block_estimate(flat), block_estimate(flat) == (0.0, 0.0))

    # CIEDE2000 reference pairs: Lab 1, Lab 2, expected difference
    pairs = [((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
             ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
             ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
             ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082)]
    worst = max(abs(float(delta_e_2000(np.array(a), np.array(b))) - want) for a, b, want in pairs)
    check("ciede2000_max_error", f"{worst:.5f}", worst < 1e-4)

    for metric in METRICS:
        small = build_palette([truth, truth[:, ::-1]], 3, metric)
        again = build_palette([truth[:, ::-1], truth], 3, metric)
        inside = all(any(np.array_equal(c, p) for p in colours) for c in small)
        check(f"palette_{metric}_colours", len(small),
              len(small) == 3 and inside and np.array_equal(small, again))
        mapped, stats = apply_palette(truth, small, metric)
        left = {tuple(int(v) for v in c) for c in mapped[mapped[..., 3] > 0][:, :3]}
        check(f"palette_{metric}_applied", f"{stats['colours_in']}->{stats['colours_used']}",
              left <= {tuple(int(v) for v in c) for c in small} and stats["colours_used"] == len(left)
              and np.array_equal(mapped[..., 3], truth[..., 3]) and stats["max_distance"] > 0)
    same, stats = apply_palette(truth, colours)
    check("palette_identity_max_distance", f"{stats['max_distance']:.3f}",
          stats["max_distance"] == 0 and np.array_equal(same, truth))

    up = np.repeat(np.repeat(truth, 4, axis=0), 4, axis=1)
    check("integer_block_x4", integer_block(up), integer_block(up) == (4, 4, 0, 0))
    stats = block_stats(up, 4)
    check("block_uniform_pct_x4", f"{stats['uniform_pct']:.2f}", stats["uniform_pct"] == 100.0 and stats["blocks"] > 0)
    padded = np.zeros((up.shape[0] + 3, up.shape[1] + 3, 4), np.uint8)
    padded[1:1 + up.shape[0], 3:3 + up.shape[1]] = up
    found = integer_block(padded)
    check("integer_block_offset", found, found == (4, 4, 3, 1))
    stats = block_stats(padded, 4, found[2:])
    check("block_uniform_pct_offset", f"{stats['uniform_pct']:.2f}", stats["uniform_pct"] == 100.0)
    stats = block_stats(padded, 4)
    check("block_uniform_pct_wrong_phase", f"{stats['uniform_pct']:.2f}", stats["uniform_pct"] < 100.0)
    soft = np.asarray(Image.fromarray(truth, "RGBA").resize((up.shape[1], up.shape[0]), Image.Resampling.LANCZOS))
    stats = block_stats(soft, 4)
    check("block_uniform_pct_resampled", f"{stats['uniform_pct']:.2f}", stats["uniform_pct"] < 100.0)
    check("integer_block_resampled", integer_block(soft), integer_block(soft) != (4, 4, 0, 0))
    blank = np.zeros((16, 16, 4), np.uint8)
    blank[..., :3] = rng.integers(0, 255, size=(16, 16, 3))
    check("integer_block_blank", integer_block(blank), integer_block(blank) is None)

    with tempfile.TemporaryDirectory() as tmp:
        hex_path = os.path.join(tmp, "courier.hex")
        write_palette(hex_path, colours)
        back, names = read_palette(hex_path)
        check("palette_hex_roundtrip", len(back), np.array_equal(back, colours) and len(names) == len(back))
        md_path = os.path.join(tmp, "ART_DIRECTION.md")
        with open(md_path, "w", encoding="utf-8") as handle:
            handle.write("# Courier run\n\n## Palette\n\n| role | hex | usage |\n|---|---|---|\n"
                         "| outline | #1a1c2c | every silhouette |\n| satchel | #B13E53 | the courier's bag |\n"
                         "| crate | `#ef7d57` | supply crates |\n| key | #FF00FF | never in art |\n\n"
                         "- lane paint: #fc0\n- outline again #1A1C2C\n\n## Pixel spec\n\n- not a colour #123456\n")
        back, names = read_palette(md_path, exclude=[(255, 0, 255)])
        want = [(0x1a, 0x1c, 0x2c), (0xb1, 0x3e, 0x53), (0xef, 0x7d, 0x57), (0xff, 0xcc, 0x00)]
        check("palette_md_colours", len(back), [tuple(int(v) for v in c) for c in back] == want
              and names == ["outline", "satchel", "crate", "lane paint"])
        png_path = os.path.join(tmp, "swatch.png")
        Image.fromarray(np.repeat(colours[None], 4, axis=0), "RGB").save(png_path)
        back, _ = read_palette(png_path)
        check("palette_png_colours", len(back), np.array_equal(back, colours))
        try:
            read_palette(md_path, section="Mood")
            refused = False
        except ValueError:
            refused = True
        check("palette_missing_section_refused", refused, refused)

    print(f"verdict {'FAIL' if failed else 'OK'} checks failed {len(failed)}"
          + (f" ({', '.join(failed)})" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    print("pixel_ops.py is a module: import it, or run `pixel_ops.py --selftest`", file=sys.stderr)
    sys.exit(1)
