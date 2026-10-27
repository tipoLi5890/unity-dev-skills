#!/usr/bin/env python3
"""video_frames.py — a generated clip on a flat chroma key -> keyed RGBA frames + a report.

ffprobe reads the clip's own frame rate and frame count (recorded, never
assumed); ffmpeg writes every frame of the first picture stream that is not a
cover image as PNG, audio left out (`-an`, no `-r`, passthrough timing). Each
frame is then keyed by the chroma_unmix block below — the same keyer as
`codex-visual/scripts/key_unmix.py --edge tint`:

  painted key  the field as the video model painted it, read once per clip from
               frame 0's border (`painted_key_from_border`) and reused for every
               frame, so one clip is keyed against one colour. A model that
               paints "#00FF00" as (2, 238, 3) needs that second erase ball.
  keying       hard cut within 96 of the declared key and, border-connected,
               of the painted one; un-mix 1-4 rings from the keyed region;
               trapped spill clusters despilled (`key_tint_unmix`).
  specks       a piece under max(8 px, 1 % of the largest piece — the body)
               whose every pixel lies more than 10 % of the body's height from
               it is erased (8-connected, alpha > 0). Near the body, small
               pieces are the subject's own and stay.

Gates and readings (all in DIR/frames.report.json):

  flatness     how flat the painted field is: the painted key and its distance
               from the declared key (`off_by`), and per frame the mean and the
               largest per-channel standard deviation of the keyed pixels in the
               4-px border ring (`border_std`), plus how far each frame's border
               mean wanders from frame 0's. A reading, never a gate: it says
               whether the field the next clip is generated on needs repainting
               (`video_canvas.py`).
  transparency a frame keyed to under 1 % transparent means the background is
               not this key: refused, exit 2.
  edge contact an opaque pixel in the top, left or right 4-px band (the floor is
               expected contact). Each one is classified on its raw colour:
               `residual` when it carries the key's hue signature and its opaque
               8-connected piece holds nothing else (leftover background — fix:
               normalise the still with video_canvas.py and regenerate);
               `subject` otherwise (the subject left the frame — fix: a taller or
               wider canvas, video_canvas.py --state/--shape). Refused, exit 3,
               unless --allow-edge-contact (accept both) or
               --allow-subject-edge-contact (accept the subject, still refuse a
               frame where only leftover key reaches the edge).

Output layout (DIR = --out-dir):
  DIR/raw/frame-0001.png …    every decoded frame (--drop-raw removes them)
  DIR/keyed/frame-0001.png …  keyed RGBA frames, handed over only by a passing run
  DIR/keyed.refused/          a refused run's keyed frames, to look at
  DIR/frames.report.json      tool, producer, source{file, sha256, fps}, probe,
                              key, flatness, specks, edge, rows[], status

`video_loop.py DIR` reads keyed/ and the report's source fps.

Examples
  video_frames.py clips/runner_walk.mp4 --out-dir work/runner_walk
  video_frames.py clips/sentry_idle.mp4 --out-dir work/sentry_idle --key magenta
  video_frames.py clips/runner_launch.mp4 --out-dir work/launch --allow-subject-edge-contact
  video_frames.py --selftest

stdout: one JSON object (the report's summary). Exit codes:
  0  frames keyed and handed over (or --selftest passed)
  1  bad arguments, clip unreadable, ffmpeg/ffprobe missing or failing, or a
     failed --selftest
  2  a frame keyed to under 1 % transparent: the background is not the key
  3  edge contact on the top/left/right band (stderr says residual key or
     subject out of frame, and the fix)

Requires numpy, Pillow and the ffmpeg + ffprobe binaries on PATH
(~/.codex/imagegen-venv/bin/python has numpy and Pillow).
"""
# ---------------------------------------------------------------------------
# Third-party code. Portions are ported, with identifiers and structure
# adapted, from sprite-gen
#   https://github.com/aldegad/sprite-gen
#   commit dddcc1013f7b5587a5eabd8609a5b42dd8aa7c26
#   Apache License 2.0 — see THIRD_PARTY_NOTICES.md.
#
#   video/frames.py  probe, extract, _near (near), drop_specks, _bands (bands),
#                    _edge_pixels and classify_edge_contact (classify_edge),
#                    _residual_message and _edge_contact_message (the two
#                    refusal texts), the keyed/ vs keyed.refused/ hand-over,
#                    and the constants EDGE_ROWS, SPECK_MIN_FRACTION,
#                    SPECK_MIN_PX, SPECK_APART
#   (the chroma_unmix block between the shared markers carries its own list)
#
# Changes: frames are keyed with the chroma_unmix block (one painted key per
# clip, read on frame 0) instead of sprite-gen's cutout engine; components come
# from the block's label8 instead of a run-list walk; the edge decontamination
# pass, --spill auto/full, the drawing's-own-border and body-rim acceptance,
# brightness alpha and the source manifest are not carried; a key-flatness
# reading and a 1 %-transparent floor are added; refusals exit 2/3 instead of
# raising; the report carries a source sha256 and a producer.
# ---------------------------------------------------------------------------
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

EDGE_ROWS = 4             # rows/cols read at the top, left and right edges
SPECK_MIN_FRACTION = 0.01  # a piece under this share of the body ...
SPECK_MIN_PX = 8           # ... or under this many pixels is small
SPECK_APART = 0.1          # ... and far when every pixel is this share of the body's height away
MIN_KEYED_FRACTION = 0.01  # a frame keyed to less than this is not on the key
SIDES = ("top", "left", "right")
KEY_NAMES = {"magenta": (255, 0, 255), "green": (0, 255, 0), "cyan": (0, 255, 255), "blue": (0, 77, 255)}
PRODUCER = {"skill": "sprite-from-video", "script": "video_frames.py"}


# >>> shared:chroma_unmix
# ---------------------------------------------------------------------------
# Third-party code. Portions are ported, with identifiers and structure
# adapted, from sprite-gen
#   https://github.com/aldegad/sprite-gen
#   commit dddcc1013f7b5587a5eabd8609a5b42dd8aa7c26
#   Apache License 2.0 — see THIRD_PARTY_NOTICES.md.
#
#   frames/extract.py  _key_channel_split, key_tint_score and _key_tint_field
#                      (tint_field), _key_distance_field (key_distance),
#                      despill_color and unmix_key_blend (despill_rgb), the
#                      key-family and border-candidate signatures
#                      (_key_family_field, _border_key_candidate_field,
#                      _painted_key_leans), _grow_chebyshev, _grow_into,
#                      detect_background_key_rgb (painted_key_from_border),
#                      hard_key_mask, and the classification, depth-ring
#                      unmix and trapped-spill despill passes of
#                      remove_chroma_background (key_tint_unmix)
#
# Changes: rewritten as whole-array numpy over an HxWx3/HxWx4 uint8 array
# instead of PIL images and per-pixel loops; the trapped-spill clusters come
# from a run-based 8-connected labelling instead of a per-pixel stack walk;
# the painted key is read from the whole border in one pass rather than in
# row bands; the YCbCr matte, decontam, hue-excess spill and chroma-group
# options are not carried; results come back as (rgba, stats); a rim whose
# nearest deep material is itself key-tinted is un-mixed against that
# material's tint (material_tint, material_baseline) rather than against zero.
# ---------------------------------------------------------------------------
import numpy as np

KEY_THRESHOLD = 96.0          # hard cut radius around the declared key (and the painted one)
FRINGE_DELTA = 18.0           # key tint under this = subject, never touched
FRINGE_KEY_THRESHOLD = 180.0  # key-tinted and within this of the key = in-band blend
UNMIX_REACH = 4               # rings from the keyed region that are un-mixed
IN_BAND_DEPTH = 2             # in-band blends are un-mixed only this close to the keyed region
SPILL_MIN_TINT = 40.0         # a trapped-spill cluster needs one pixel past this tint
SPILL_MAX_FRACTION = 0.005    # ...and at most max(32, this share of the subject) pixels

_CH_LIT = 192   # a channel the key saturates
_CH_DARK = 64   # a channel the key leaves dark
_FAMILY_MAX_UNKEYED_RATIO = 0.35
_FAMILY_KEYED_BALANCE = 0.8
_BORDER_MAX_LEAN_RATIO = 0.5
_DETECT_CORNER_DIV = 5
_DETECT_MIN_FRACTION = 0.12
_DETECT_BIN_SHIFT = 3
_DETECT_LEAN_LEFT_MIN_FRACTION = 0.02
_DETECT_NEIGHBOUR_BINS = 1


def key_channel_split(key):
    """(channels the key saturates, channels it leaves dark); two empty lists for a key with no tint axis."""
    keyed = [i for i, v in enumerate(key) if v >= _CH_LIT]
    unkeyed = [i for i, v in enumerate(key) if v < _CH_DARK]
    if not keyed or not unkeyed:
        return [], []
    return keyed, unkeyed


def key_tint_score(color, key):
    """Mean of the key's lit channels minus mean of its dark ones, for one colour."""
    keyed, unkeyed = key_channel_split(key)
    if not keyed:
        return 0.0
    return sum(color[i] for i in keyed) / len(keyed) - sum(color[i] for i in unkeyed) / len(unkeyed)


def tint_field(rgb, keyed, unkeyed):
    """key_tint_score for an HxWx3 (or Nx3) integer array, float64."""
    if not keyed:
        return np.zeros(rgb.shape[:-1], np.float64)
    ks = rgb[..., keyed].sum(axis=-1, dtype=np.int64)
    us = rgb[..., unkeyed].sum(axis=-1, dtype=np.int64)
    return ks / len(keyed) - us / len(unkeyed)


def key_distance(rgb, key):
    """Euclidean RGB distance to `key`, float64; squares summed in int64."""
    d = rgb.astype(np.int32) - np.asarray(key, np.int32)
    return np.sqrt((d * d).sum(axis=-1, dtype=np.int64).astype(np.float64))


def _family_field(rgb, keyed, unkeyed):
    kmin = rgb[..., keyed].min(axis=-1)
    kmax = rgb[..., keyed].max(axis=-1)
    umax = rgb[..., unkeyed].max(axis=-1)
    return (kmin >= _CH_DARK) & (umax <= kmin * _FAMILY_MAX_UNKEYED_RATIO) & (kmin >= kmax * _FAMILY_KEYED_BALANCE)


def _border_candidate_field(rgb, keyed, unkeyed, lean=True):
    """The key's hue signature at any brightness, as a painted background carries it.

    lean=False also holds the brighter dark channel under the bars (a green that does not lean
    toward cyan or yellow)."""
    kmin = rgb[..., keyed].min(axis=-1)
    kmax = rgb[..., keyed].max(axis=-1)
    umin = rgb[..., unkeyed].min(axis=-1)
    umax = rgb[..., unkeyed].max(axis=-1)
    sig = ((kmin >= _CH_DARK) & (umin < _CH_DARK) & (umin <= kmax * _FAMILY_MAX_UNKEYED_RATIO)
           & (umax < kmax * _BORDER_MAX_LEAN_RATIO))
    if not lean:
        sig &= (umax < _CH_DARK) & (umax <= kmax * _FAMILY_MAX_UNKEYED_RATIO)
    return _family_field(rgb, keyed, unkeyed) | sig


def _painted_leans(painted, keyed, unkeyed):
    rgb = np.asarray([painted], np.int32)
    return bool(_border_candidate_field(rgb, keyed, unkeyed)[0]
                and not _border_candidate_field(rgb, keyed, unkeyed, lean=False)[0])


def grow8(mask):
    """One step of 8-connected growth (no wrap at the edges)."""
    g = mask.copy()
    g[:, 1:] |= mask[:, :-1]
    g[:, :-1] |= mask[:, 1:]
    s = g.copy()
    s[1:, :] |= g[:-1, :]
    s[:-1, :] |= g[1:, :]
    return s


def grow_into(seed, allowed):
    """Every `allowed` pixel 8-connected to `seed` through `allowed` pixels."""
    reached = seed & allowed
    while True:
        grown = grow8(reached) & allowed
        if not (grown & ~reached).any():
            return reached
        reached = grown


def label8(mask):
    """8-connected components of a bool mask -> (int32 labels 1..n, n). Run-based union-find."""
    h, w = mask.shape
    pad = np.zeros((h, w + 2), np.int8)
    pad[:, 1:-1] = mask
    d = np.diff(pad, axis=1)
    rs, cs = np.nonzero(d == 1)
    _, ce = np.nonzero(d == -1)
    n = len(rs)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    row_start = np.searchsorted(rs, np.arange(h + 1))
    for r in range(1, h):
        i, a1, j, b1 = row_start[r], row_start[r + 1], row_start[r - 1], row_start[r]
        while i < a1 and j < b1:
            if cs[i] <= ce[j] and cs[j] <= ce[i]:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
            if ce[i] < ce[j]:
                i += 1
            else:
                j += 1
    roots, lab = {}, np.zeros((h, w), np.int32)
    for i in range(n):
        lab[rs[i], cs[i]:ce[i]] = roots.setdefault(find(i), len(roots) + 1)
    return lab, len(roots)


def painted_key_from_border(rgba, key, threshold=KEY_THRESHOLD):
    """The flat background colour as it was painted, read from the border, or `key` unchanged.

    Samples the 1-px border plus the w/5 x h/5 corner patches, keeps opaque pixels that carry
    the key's hue signature, and — when they are at least 12% of the samples — returns the
    floored mean of their most populated 8-wide RGB bin (the mode, so a few rim pixels on the
    border do not pull an exact-key field off the key). A green that leans toward cyan or
    yellow is read only where the declared key's own cut would leave that background behind
    (2% of the samples past `threshold`, in the mode bin or beside it) and no second
    key-coloured cluster holds 12%. Anything else, or a key with no tint axis, returns `key`."""
    key = tuple(int(v) for v in key)
    keyed, unkeyed = key_channel_split(key)
    if not keyed:
        return key
    h, w = rgba.shape[:2]
    cw, chh = w // _DETECT_CORNER_DIV, h // _DETECT_CORNER_DIV
    cw = w if cw < 2 else cw
    chh = h if chh < 2 else chh
    m = np.zeros((h, w), bool)
    m[:chh, :cw] = m[:chh, w - cw:] = m[h - chh:, :cw] = m[h - chh:, w - cw:] = True
    m[0, :] = m[-1, :] = m[:, 0] = m[:, -1] = True
    if rgba.shape[2] == 4:
        m &= rgba[..., 3] != 0
    rgb = rgba[..., :3][m].astype(np.int32)
    sampled = len(rgb)
    bits = 8 - _DETECT_BIN_SHIFT
    nslots = 1 << (3 * bits)
    before = _border_candidate_field(rgb, keyed, unkeyed, lean=False)
    lean = _border_candidate_field(rgb, keyed, unkeyed) & ~before
    left = lean & (key_distance(rgb, key) > threshold)
    counts = np.zeros((3, nslots), np.int64)
    sums = np.zeros((2, 3, nslots), np.float64)
    for row, fam in enumerate((before, lean, left)):
        c = rgb[fam]
        b = c >> _DETECT_BIN_SHIFT
        slots = (b[:, 0] << (2 * bits)) | (b[:, 1] << bits) | b[:, 2]
        counts[row] += np.bincount(slots, minlength=nslots)
        if row < 2:
            for ch in range(3):
                sums[row, ch] += np.bincount(slots, weights=c[:, ch], minlength=nslots)
    bar = sampled * _DETECT_MIN_FRACTION
    if not sampled or counts[:2].sum() < bar:
        return key
    rows = 1 if counts[0].sum() >= bar else 2
    fam_counts = counts[:rows].sum(axis=0)
    mode = int(np.argmax(fam_counts))
    if rows == 2:
        mask = (1 << bits) - 1
        slots = np.arange(nslots)
        near = np.ones(nslots, bool)
        for shift in (2 * bits, bits, 0):
            near &= np.abs(((slots >> shift) & mask) - ((mode >> shift) & mask)) <= _DETECT_NEIGHBOUR_BINS
        if counts[2][near].sum() < sampled * _DETECT_LEAN_LEFT_MIN_FRACTION or fam_counts[~near].sum() >= bar:
            return key
    members = int(fam_counts[mode])
    return tuple(int(sums[:rows, ch, mode].sum()) // members for ch in range(3))


def hard_key_mask(rgb, alpha, key, painted, threshold=KEY_THRESHOLD):
    """(keyed mask, key distance) for an HxWx3 int32 source.

    The declared key's ball erases by colour alone, wherever it sits. The painted colour's ball
    erases only what carries the key's hue signature (or sits in the declared ball) plus what is
    8-connected to that through the painted ball, so a lone subject patch that merely resembles
    the painted colour survives. The distance is lowered to the painted one on the pixels its
    ball claims."""
    keyed, unkeyed = key_channel_split(key)
    kd = key_distance(rgb, key)
    if tuple(painted) != tuple(key) and keyed:
        pd = key_distance(rgb, painted)
        in_ball = pd <= threshold
        lean = _painted_leans(painted, keyed, unkeyed)
        claim = in_ball & _border_candidate_field(rgb, keyed, unkeyed, lean=lean)
        claim |= in_ball & (kd <= threshold)
        claim = grow_into(claim, in_ball)
        kd = np.where(claim, np.minimum(kd, pd), kd)
    return (alpha == 0) | (kd <= threshold), kd


def despill_rgb(color, painted, key_tint, tint):
    """Blend model obs = (1-k)*subject + k*painted with k = min(tint/key_tint, 1).

    color Nx3 int, tint N float -> (coverage N = 1-k, subject Nx3 uint8 clamped). Where
    coverage <= 0 the colour comes back (0,0,0)."""
    k = np.minimum(tint / key_tint, 1.0)
    cov = 1.0 - k
    safe = np.where(cov > 0, cov, 1.0)
    un = (color.astype(np.float64) - k[:, None] * np.asarray(painted, np.float64)) / safe[:, None]
    out = np.clip(np.rint(un), 0, 255).astype(np.uint8)
    out[cov <= 0] = 0
    return cov, out


def material_tint(tint, depth, kmask, reach):
    """Per-pixel key tint of the nearest material deeper than `reach` rings, carried outward ring
    by ring as the 8-neighbour mean of already-filled pixels; 0 where no such material is near."""
    h, w = tint.shape
    filled = (depth > reach) & ~kmask
    val = np.where(filled, tint, 0.0)
    for ring in range(min(int(reach), 254), 0, -1):
        todo = (depth == ring) & ~filled
        if not todo.any():
            continue
        pv = np.pad(val * filled, 1)
        pf = np.pad(filled.astype(np.float64), 1)
        sv = sum(pv[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        sf = sum(pf[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        got = todo & (sf > 0)
        val = np.where(got, sv / np.where(sf > 0, sf, 1.0), val)
        filled = filled | got
    return np.where(filled, val, 0.0)


def key_tint_unmix(image, key_rgb, *, key_threshold=KEY_THRESHOLD, fringe_delta=FRINGE_DELTA,
                   fringe_key_threshold=FRINGE_KEY_THRESHOLD, unmix_reach=UNMIX_REACH,
                   in_band_depth=IN_BAND_DEPTH, despill=True, painted_key=None,
                   spill_max_fraction=SPILL_MAX_FRACTION, spill_min_tint=SPILL_MIN_TINT,
                   material_baseline=True):
    """Key a flat chroma field out of an HxWx3 or HxWx4 uint8 image -> (HxWx4 uint8, stats).

    1. hard cut: within `key_threshold` of the declared key, or of the painted key (read from
       the border unless given) through the signature-grown ball of hard_key_mask.
    2. classes on the source colours: keyed; subject (tint < fringe_delta, untouched); in-band
       blend (within fringe_key_threshold of the key); out-of-band blend.
    3. un-mix: pixels 1..unmix_reach Chebyshev rings from the keyed region (rings cross the
       subject), out-of-band blends always and in-band ones only within in_band_depth, become
       despilled colour with alpha * (1 - k). With material_baseline, a rim pixel whose nearest
       material deeper than unmix_reach is itself key-tinted (tint >= fringe_delta, e.g. a teal
       jacket on green) is un-mixed against that material: k = (tint - base) / (key_tint - base),
       so the rim keeps the material's hue instead of turning to the far side of it (teal ->
       blue). base comes from material_tint; where it is under fringe_delta the step is upstream's.
    4. trapped spill (despill=True): 8-connected clusters of still-tinted visible pixels
       (tint >= min(fringe_delta, spill_min_tint)) of at most max(32, spill_max_fraction of the
       subject) pixels with one pixel past spill_min_tint get their colour despilled and keep
       their alpha; a larger key-tinted region is the art's own material and stays."""
    img = np.asarray(image)
    h, w = img.shape[:2]
    data = np.zeros((h, w, 4), np.uint8)
    data[..., :3] = img[..., :3]
    data[..., 3] = img[..., 3] if img.shape[2] == 4 else 255
    key = tuple(int(v) for v in key_rgb)
    keyed, unkeyed = key_channel_split(key)
    painted = (painted_key_from_border(data, key, key_threshold) if painted_key is None
               else tuple(int(v) for v in painted_key))
    if not keyed:
        painted = key
    src = data[..., :3].astype(np.int32)
    kmask, kd = hard_key_mask(src, data[..., 3], key, painted, key_threshold)
    tint = tint_field(src, keyed, unkeyed)
    classes = np.select([kmask, tint < fringe_delta, kd <= fringe_key_threshold], [0, 1, 2], default=3)
    data[kmask] = 0
    key_tint = key_tint_score(painted, key)
    stats = dict(painted_key=list(painted), key_tint=round(float(key_tint), 2), keyed_px=int(kmask.sum()),
                 subject_px=int((~kmask).sum()), unmixed_px=0, baseline_px=0, spill_px=0,
                 spill_clusters=0)
    if key_tint <= 0:
        return data, stats
    if unmix_reach > 0:
        depth = np.full((h, w), 255, np.uint8)
        depth[kmask] = 0
        frontier, reached, ring = kmask, kmask, 0
        while frontier.any() and ring < min(254, unmix_reach):
            ring += 1
            frontier = grow8(frontier) & ~reached
            depth[frontier] = ring
            reached = reached | frontier
        sel = (depth > 0) & (depth <= unmix_reach) & (((classes == 2) & (depth <= in_band_depth)) | (classes == 3))
        if sel.any():
            col = data[sel][:, :3].astype(np.int64)
            al = data[sel][:, 3].astype(np.float64)
            t_sel = tint_field(col, keyed, unkeyed)
            if material_baseline:
                base = material_tint(tint, depth, kmask, unmix_reach)[sel]
                use = (base >= fringe_delta) & (key_tint - base >= fringe_delta)
                if use.any():
                    # rim = (1-k)*material + k*painted: k from the tint above the material's own
                    t_sel = np.where(use, np.maximum(t_sel - base, 0.0) * key_tint
                                     / np.where(use, key_tint - base, 1.0), t_sel)
                    stats["baseline_px"] = int(use.sum())
            cov, sub = despill_rgb(col, painted, key_tint, t_sel)
            a = np.minimum(np.rint(al * cov), 255.0)
            gone = a <= 0
            sub[gone] = 0
            data[sel] = np.column_stack([sub, np.where(gone, 0, a).astype(np.uint8)])
            stats["unmixed_px"] = int(sel.sum())
    if despill and kmask.any() and spill_max_fraction > 0:
        limit = max(32, round(stats["subject_px"] * spill_max_fraction))
        cur = tint_field(data[..., :3].astype(np.int32), keyed, unkeyed)
        cand = (data[..., 3] != 0) & (cur >= min(fringe_delta, spill_min_tint))
        if cand.any():
            lab, n = label8(cand)
            size = np.bincount(lab.ravel(), minlength=n + 1)
            top = np.full(n + 1, -np.inf)
            np.maximum.at(top, lab[cand], cur[cand])
            ok = (size <= limit) & (top > spill_min_tint)
            ok[0] = False
            fix = ok[lab]
            if fix.any():
                col = data[fix][:, :3].astype(np.int64)
                cov, sub = despill_rgb(col, painted, key_tint, cur[fix])
                rows = data[fix]
                rows[cov > 0, :3] = sub[cov > 0]
                data[fix] = rows
                stats["spill_px"] = int((cov > 0).sum())
                stats["spill_clusters"] = int(ok.sum())
    return data, stats
# <<< shared:chroma_unmix


class Refused(Exception):
    def __init__(self, code, message, part=None):
        super().__init__(message)
        self.code, self.part = code, part or {}


def parse_key(text):
    """'green' | 'magenta' | 'cyan' | 'blue' | '#rrggbb' | 'rrggbb' -> (r, g, b)."""
    t = str(text).strip().lower()
    if t in KEY_NAMES:
        return KEY_NAMES[t]
    t = t.lstrip("#")
    if len(t) != 6 or any(c not in "0123456789abcdef" for c in t):
        raise ValueError(f"--key {text!r}: expected green, magenta, cyan, blue or #rrggbb")
    return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4))


def hexrgb(rgb):
    return "#" + "".join(f"{int(v):02x}" for v in rgb)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------- ffmpeg ----

def require(binary):
    path = shutil.which(binary)
    if not path:
        raise Refused(1, f"`{binary}` not found on PATH — install ffmpeg (it ships ffprobe)")
    return path


def probe(clip):
    """The clip's picture stream (the first video stream that is not a cover image) and what else it carries."""
    proc = subprocess.run(
        [require("ffprobe"), "-v", "error", "-show_entries",
         "stream=index,codec_type,codec_name,pix_fmt,width,height,r_frame_rate,nb_frames",
         "-show_entries", "stream_disposition=attached_pic", "-show_entries", "format=duration",
         "-of", "json", str(clip)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise Refused(1, f"ffprobe failed on {clip}: {proc.stderr.strip()[:300]}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    pictures = [s for s in streams if s.get("codec_type") == "video"
                and not (s.get("disposition") or {}).get("attached_pic")]
    if not pictures:
        raise Refused(1, f"{clip} has no video stream")
    s = pictures[0]
    num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    if fps <= 0:
        raise Refused(1, f"{clip}: ffprobe reports no frame rate")
    return {"width": s.get("width"), "height": s.get("height"), "fps": round(fps, 6),
            "nb_frames": int(s["nb_frames"]) if str(s.get("nb_frames", "")).isdigit() else None,
            "duration": float((data.get("format") or {}).get("duration") or 0),
            "stream_index": s.get("index"), "codec": s.get("codec_name"), "pix_fmt": s.get("pix_fmt"),
            "audio_streams": sum(1 for x in streams if x.get("codec_type") == "audio"),
            "cover_streams": len([x for x in streams if x.get("codec_type") == "video"]) - len(pictures)}


def extract(clip, raw_dir, stream_index):
    """Every frame of the picture stream as raw_dir/frame-%04d.png: no audio, no -r, passthrough timing."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for old in raw_dir.glob("frame-*.png"):
        old.unlink()
    pick = ["-map", f"0:{stream_index}"] if stream_index is not None else []
    proc = subprocess.run([require("ffmpeg"), "-v", "error", "-y", "-i", str(clip), *pick, "-an",
                           "-fps_mode", "passthrough", str(raw_dir / "frame-%04d.png")],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise Refused(1, f"ffmpeg failed on {clip}: {proc.stderr.strip()[:300]}")
    files = sorted(raw_dir.glob("frame-*.png"))
    if not files:
        raise Refused(1, f"ffmpeg wrote no frames for {clip}")
    return files


# ------------------------------------------------------------------- specks ----

def near(mask, reach):
    """Every pixel within `reach` px of `mask`, each way and diagonally (a square of side 2*reach+1)."""
    for axis in (0, 1):
        n = mask.shape[axis]
        pad = [(reach + 1, reach) if a == axis else (0, 0) for a in (0, 1)]
        total = np.cumsum(np.pad(mask.astype(np.int32), pad), axis=axis)
        mask = (np.take(total, np.arange(2 * reach + 1, 2 * reach + 1 + n), axis=axis)
                - np.take(total, np.arange(n), axis=axis)) > 0
    return mask


def drop_specks(rgba, apart=SPECK_APART):
    """Erase the specks in place -> pieces erased. A piece is 8-connected alpha > 0; a speck is under
    max(SPECK_MIN_PX, SPECK_MIN_FRACTION of the largest piece) with no pixel within `apart` of the
    largest piece's height of it."""
    lab, n = label8(rgba[..., 3] > 0)
    if n < 2:
        return 0
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    sizes[0] = 0
    body = int(sizes.argmax())
    small = sizes < max(SPECK_MIN_PX, sizes[body] * SPECK_MIN_FRACTION)
    small[0] = small[body] = False
    if not small.any():
        return 0
    bmask = lab == body
    rows = np.flatnonzero(bmask.any(axis=1))
    reach = int(apart * (rows[-1] - rows[0] + 1))
    if reach > 0:
        close = np.zeros(n + 1, bool)
        close[np.unique(lab[near(bmask, reach) & (lab > 0)])] = True
        small &= ~close
    if not small.any():
        return 0
    rgba[small[lab]] = 0
    return int(small.sum())


# ------------------------------------------------------------- edge contact ----

def bands(h, w):
    """The top/left/right edge bands, EDGE_ROWS deep; a corner pixel is in two."""
    b = {s: np.zeros((h, w), bool) for s in SIDES}
    b["top"][:EDGE_ROWS, :] = True
    b["left"][:, :EDGE_ROWS] = True
    b["right"][:, max(0, w - EDGE_ROWS):] = True
    return b


def classify_edge(raw_rgb, keyed_rgba, key, painted):
    """{top, left, right, subject, residual} opaque edge-band pixels.

    A contact pixel is residual when its raw colour carries the key's hue signature (the leaning
    greens only when the painted key leans itself) and the opaque 8-connected piece it belongs to
    holds no pixel off that signature: background on its own. Joined to such a pixel it is the
    subject's rim, and counts as subject."""
    alpha = keyed_rgba[..., 3]
    h, w = alpha.shape
    bd = bands(h, w)
    opaque = alpha > 0
    contact = (bd["top"] | bd["left"] | bd["right"]) & opaque
    out = {s: int((bd[s] & opaque).sum()) for s in SIDES}
    out.update(subject=int(contact.sum()), residual=0)
    keyed, unkeyed = key_channel_split(key)
    if not contact.any() or not keyed:
        return out
    keyish = _border_candidate_field(raw_rgb.astype(np.int32), keyed, unkeyed,
                                     lean=_painted_leans(painted, keyed, unkeyed))
    suspect = contact & keyish
    if not suspect.any():
        return out
    lab, n = label8(opaque)
    owned = np.zeros(n + 1, bool)
    owned[np.unique(lab[opaque & ~keyish])] = True
    residual = int((suspect & ~owned[lab]).sum())
    out.update(subject=int(contact.sum()) - residual, residual=residual)
    return out


def _worst(contacts):
    c = max(contacts, key=lambda r: r["top"] + r["left"] + r["right"])
    return f"(worst {c['frame']}: top {c['top']} / left {c['left']} / right {c['right']} px)"


def residual_message(contacts, painted):
    return (f"leftover chroma background reaches the frame edge in {len(contacts)} frame(s) {_worst(contacts)} — "
            f"the field survived the key (painted {tuple(painted)}); this is background, not the subject: "
            "normalise the base still with video_canvas.py (repaints the field to the exact key) and regenerate")


def edge_message(contacts, painted):
    subject = [c for c in contacts if c["subject"] > 0]
    if not subject:
        return residual_message(contacts, painted)
    msg = (f"the subject touches the frame edge in {len(subject)} frame(s) {_worst(contacts)} — the subject left "
           "the frame: regenerate from a taller or wider canvas (video_canvas.py --state jump/attack or --shape "
           "tall/wide), or pass --allow-subject-edge-contact to accept the clipping")
    resid = [c for c in contacts if c["residual"] > 0]
    if resid:
        msg += f"; {len(resid)} frame(s) also carry leftover key at the edge (`residual` in the report)"
    return msg


# ------------------------------------------------------------------ keying ----

def border_ring(h, w, depth=EDGE_ROWS):
    m = np.zeros((h, w), bool)
    m[:depth, :] = m[-depth:, :] = m[:, :depth] = m[:, -depth:] = True
    return m


def key_frames(raw_files, keyed_dir, key, edge_policy):
    """Key every raw frame into keyed_dir -> report part. Raises Refused(2|3, message) with the part attached."""
    keyed_dir.mkdir(parents=True, exist_ok=True)
    rows, contacts, painted, ring, first_mean = [], [], None, None, None
    part = {"rows": rows}

    def summary():
        std = [r["border_std"] for r in rows if r["border_std"] is not None]
        drift = [r["border_drift"] for r in rows if r["border_drift"] is not None]
        part.update(
            frames=len(rows),
            key={"declared": hexrgb(key), "declared_rgb": list(key),
                 "painted_rgb": list(painted) if painted else None,
                 "off_by": round(float(np.linalg.norm(np.subtract(painted, key))), 2) if painted else None},
            flatness={"border_px": EDGE_ROWS,
                      "border_std_max": round(max(std), 2) if std else None,
                      "border_std_median": round(float(np.median(std)), 2) if std else None,
                      "border_mean_drift_max": round(max(drift), 2) if drift else None},
            transparent_pct_min=min(r["transparent_pct"] for r in rows) if rows else None,
            transparent_pct_max=max(r["transparent_pct"] for r in rows) if rows else None,
            specks={"dropped": sum(r["specks"] for r in rows), "frames": sum(1 for r in rows if r["specks"]),
                    "min_fraction": SPECK_MIN_FRACTION, "min_px": SPECK_MIN_PX, "apart": SPECK_APART},
            edge={"policy": edge_policy, "rows": EDGE_ROWS, "contacts": contacts})
        return part

    for k, src in enumerate(raw_files):
        raw = np.asarray(Image.open(src).convert("RGB"))
        if painted is None:
            painted = painted_key_from_border(raw, key)
            ring = border_ring(*raw.shape[:2])
        rgba, st = key_tint_unmix(raw, key, painted_key=painted)
        specks = drop_specks(rgba)
        gone = rgba[..., 3] == 0
        field = raw[ring & gone].astype(np.float64)
        bstd = bmean = drift = None
        if len(field):
            bmean = field.mean(axis=0)
            bstd = round(float(field.std(axis=0).max()), 2)
            if first_mean is None:
                first_mean = bmean
            drift = round(float(np.linalg.norm(bmean - first_mean)), 2)
        row = {"frame": src.name, "transparent_pct": round(100 * float(gone.mean()), 2),
               "keyed_px": st["keyed_px"], "unmixed_px": st["unmixed_px"], "spill_px": st["spill_px"],
               "specks": specks, "border_std": bstd, "border_drift": drift,
               "border_mean": [round(float(v), 1) for v in bmean] if bmean is not None else None}
        Image.fromarray(rgba, "RGBA").save(keyed_dir / src.name)
        if edge_policy != "off":
            edge = classify_edge(raw, rgba, key, painted)
            if edge["top"] or edge["left"] or edge["right"]:
                row["edge"] = edge
                contacts.append({"frame": src.name, **edge})
        rows.append(row)
        if gone.mean() < MIN_KEYED_FRACTION:
            raise Refused(2, f"{src.name} keyed to {100 * gone.mean():.2f}% transparent (under "
                             f"{100 * MIN_KEYED_FRACTION:g}%) — the background is not the {hexrgb(key)} key "
                             f"(painted {tuple(painted)}); pick the key with codex-visual pick_key.py "
                             "or pass --key", summary())
    summary()
    if contacts and edge_policy == "refuse":
        raise Refused(3, edge_message(contacts, painted), part)
    if contacts and edge_policy == "subject-allowed":
        alone = [c for c in contacts if c["residual"] > 0 and c["subject"] == 0]
        if alone:
            raise Refused(3, residual_message(alone, painted), part)
    return part


def run(clip, out_dir, key, edge_policy, drop_raw=False):
    """-> (exit code, report dict). Writes out_dir/raw, keyed or keyed.refused, frames.report.json."""
    clip, out_dir = Path(clip), Path(out_dir)
    if not clip.is_file():
        return 1, {"ok": False, "error": f"clip not found: {clip}"}
    head = {"tool": "video_frames.py", "producer": PRODUCER,
            "source": {"file": str(clip.resolve()), "sha256": sha256(clip), "fps": None}}
    try:
        meta = probe(clip)
        head["source"]["fps"] = meta["fps"]
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_dir, keyed_dir, refused_dir = out_dir / "raw", out_dir / "keyed", out_dir / "keyed.refused"
        shutil.rmtree(keyed_dir, ignore_errors=True)
        shutil.rmtree(refused_dir, ignore_errors=True)
        files = extract(clip, raw_dir, meta["stream_index"])
    except Refused as exc:
        return exc.code, {"ok": False, **head, "error": str(exc)}
    except OSError as exc:
        return 1, {"ok": False, **head, "error": f"cannot write to {out_dir}: {exc}"}
    warnings = []
    if meta["nb_frames"] is not None and meta["nb_frames"] != len(files):
        warnings.append(f"ffprobe counts {meta['nb_frames']} frames, ffmpeg wrote {len(files)}")
    report = {**head, "probe": meta, "extracted": len(files), "raw_dir": str(raw_dir)}
    code, error = 0, None
    try:
        part = key_frames(files, keyed_dir, tuple(key), edge_policy)
    except Refused as exc:
        part, code, error = exc.part, exc.code, str(exc)
    report.update(part)
    report["status"] = "passed" if code == 0 else "refused"
    if code:
        report["error"] = error
        if keyed_dir.exists():
            keyed_dir.rename(refused_dir)
        report["keyed_dir"], report["refused_dir"] = None, str(refused_dir)
    else:
        report["keyed_dir"] = str(keyed_dir)
    if warnings:
        report["warnings"] = warnings
    if drop_raw:
        shutil.rmtree(raw_dir, ignore_errors=True)
        report["raw_dir"] = None
    report["ok"] = code == 0
    (out_dir / "frames.report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report"] = str(out_dir / "frames.report.json")
    return code, report


def summary_of(report):
    keep = ("ok", "status", "error", "keyed_dir", "refused_dir", "report", "frames", "key", "flatness",
            "transparent_pct_min", "transparent_pct_max", "warnings")
    out = {k: report[k] for k in keep if k in report}
    if "probe" in report:
        out["probe"] = {k: report["probe"][k] for k in ("width", "height", "fps", "nb_frames", "codec",
                                                         "audio_streams")}
    if "specks" in report:
        out["specks_dropped"] = report["specks"]["dropped"]
    if "edge" in report:
        out["edge_contact_frames"] = len(report["edge"]["contacts"])
        out["edge_policy"] = report["edge"]["policy"]
    return out


# ----------------------------------------------------------------- selftest ----

def _write_clip(frames, path, fps=24):
    """Synthetic RGB frames -> an H.264 yuv420p mp4 through ffmpeg (the way a video model's clip arrives)."""
    with tempfile.TemporaryDirectory() as tmp:
        for i, fr in enumerate(frames):
            Image.fromarray(fr, "RGB").save(os.path.join(tmp, f"s{i:04d}.png"))
        proc = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-framerate", str(fps), "-i",
                               os.path.join(tmp, "s%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                               "-crf", "12", str(path)], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr[-300:])


def _scene(h=128, w=96, field=(2, 238, 3), dy=0, top_blob=False, speck=False, patch=False, seed=0):
    rng = np.random.default_rng(seed)
    img = np.empty((h, w, 3), np.uint8)
    img[:] = field
    noise = rng.integers(-1, 2, (h, w, 3))
    img = np.clip(img.astype(int) + noise, 0, 255).astype(np.uint8)
    y0 = 40 + dy
    img[y0:h - 8, 34:62] = (200, 60, 40)          # body
    img[y0 - 14:y0, 40:56] = (230, 190, 150)      # head
    img[h - 12:h - 8, 30:66] = (40, 30, 30)       # feet
    if top_blob:
        img[0:y0, 44:52] = (200, 60, 40)          # a raised arm out of the frame
    if speck:
        img[12:14, 80:82] = (250, 250, 250)       # a fleck far from the body
    if patch:
        img[30:50, 0:8] = (0, 140, 0)             # leftover darker field at the left edge
    return img


def selftest():
    checks = []
    # pure-numpy parts first: they run without ffmpeg
    a = np.zeros((60, 60, 4), np.uint8)
    a[10:50, 20:40, 3] = 255
    a[2, 2, 3] = a[2, 3, 3] = 255                  # far speck
    a[51, 41, 3] = 255                             # near speck (diagonal to the body)
    n = drop_specks(a)
    checks.append(("speck far erased, near kept", n == 1 and a[2, 2, 3] == 0 and a[51, 41, 3] == 255))
    checks.append(("near() square reach", near(np.pad(np.ones((1, 1), bool), 5), 2).sum() == 25))
    checks.append(("parse_key", parse_key("green") == (0, 255, 0) and parse_key("#FF00ff") == (255, 0, 255)))
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("SKIP the clip checks: ffmpeg/ffprobe not on PATH")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            good = [_scene(dy=int(round(3 * np.sin(i / 2))), speck=(i == 3), seed=i) for i in range(8)]
            _write_clip(good, tmp / "good.mp4")
            code, rep = run(tmp / "good.mp4", tmp / "good", (0, 255, 0), "refuse")
            pk = rep.get("key", {}).get("painted_rgb") or [0, 0, 0]
            checks.append(("clean clip passes", code == 0 and rep["frames"] == 8
                           and len(list((tmp / "good" / "keyed").glob("frame-*.png"))) == 8))
            checks.append(("probe fps and count", rep["probe"]["fps"] == 24 and rep["probe"]["nb_frames"] == 8))
            checks.append(("painted key read off the declared one", abs(pk[1] - 238) <= 6 and rep["key"]["off_by"] > 10))
            checks.append(("flatness reported", rep["flatness"]["border_std_max"] is not None
                           and rep["flatness"]["border_std_max"] < 4))
            checks.append(("speck dropped on frame 3", rep["rows"][3]["specks"] >= 1))
            k0 = np.asarray(Image.open(tmp / "good" / "keyed" / "frame-0001.png"))
            checks.append(("field keyed, body kept", k0[5, 5, 3] == 0 and k0[80, 48, 3] == 255))
            checks.append(("report written", json.loads((tmp / "good" / "frames.report.json").read_text())["status"]
                           == "passed"))

            _write_clip([_scene(top_blob=True, seed=i) for i in range(4)], tmp / "arm.mp4")
            code, rep = run(tmp / "arm.mp4", tmp / "arm", (0, 255, 0), "refuse")
            c = rep.get("edge", {}).get("contacts") or [{}]
            checks.append(("subject out of frame -> 3", code == 3 and c[0].get("subject", 0) > 0
                           and "subject" in rep["error"] and (tmp / "arm" / "keyed.refused").is_dir()
                           and not (tmp / "arm" / "keyed").exists()))
            code, _ = run(tmp / "arm.mp4", tmp / "arm2", (0, 255, 0), "subject-allowed")
            checks.append(("--allow-subject-edge-contact accepts it", code == 0))

            _write_clip([_scene(patch=True, seed=i) for i in range(4)], tmp / "patch.mp4")
            code, rep = run(tmp / "patch.mp4", tmp / "patch", (0, 255, 0), "subject-allowed")
            c = rep.get("edge", {}).get("contacts") or [{}]
            checks.append(("leftover key at the edge -> 3 residual", code == 3 and c[0].get("residual", 0) > 0
                           and c[0].get("subject", 1) == 0 and "video_canvas.py" in rep["error"]))
            code, _ = run(tmp / "patch.mp4", tmp / "patch2", (0, 255, 0), "off")
            checks.append(("--allow-edge-contact accepts it", code == 0))

            grey = [np.full((64, 64, 3), 128, np.uint8) for _ in range(3)]
            _write_clip(grey, tmp / "grey.mp4")
            code, rep = run(tmp / "grey.mp4", tmp / "grey", (0, 255, 0), "refuse")
            checks.append(("not the key -> 2", code == 2 and "not the" in rep["error"]))
            code, rep = run(tmp / "missing.mp4", tmp / "x", (0, 255, 0), "refuse")
            checks.append(("missing clip -> 1", code == 1))
    fails = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {name}")
    print(f"verdict {'FAIL' if fails else 'OK'}")
    return 1 if fails else 0


class ArgParser(argparse.ArgumentParser):
    """argparse with usage errors on exit 1, so exit 2 and 3 stay this script's refusals."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"FAIL {message}", file=sys.stderr)
        sys.exit(1)


def main(argv=None):
    ap = ArgParser(description="Key every frame of a generated clip on a flat chroma field; "
                                             "gate edge contact; report key flatness.")
    ap.add_argument("clip", help="the clip (mp4/webm/mov); audio and a cover image are left out")
    ap.add_argument("--out-dir", required=True, help="writes raw/, keyed/ (or keyed.refused/) and frames.report.json")
    ap.add_argument("--key", default="green", help="the declared key: green (default), magenta, cyan, blue or #rrggbb")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--allow-edge-contact", action="store_true",
                   help="accept any opaque pixel in the top/left/right band (subject and leftover key alike)")
    g.add_argument("--allow-subject-edge-contact", action="store_true",
                   help="accept the subject touching the band, still refuse a frame where only leftover key does")
    ap.add_argument("--drop-raw", action="store_true", help="delete raw/ after keying")
    args = ap.parse_args(argv)
    try:
        key = parse_key(args.key)
    except ValueError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    policy = "off" if args.allow_edge_contact else "subject-allowed" if args.allow_subject_edge_contact else "refuse"
    code, report = run(args.clip, args.out_dir, key, policy, args.drop_raw)
    print(json.dumps(summary_of(report), indent=2))
    if code:
        print(f"FAIL {report.get('error')}", file=sys.stderr)
    return code


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    sys.exit(main())
