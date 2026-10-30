#!/usr/bin/env python3
"""key_unmix.py — key a flat chroma field out of a sheet WITHOUT leaving its colour on the rim.

A binary key (alpha 0 inside a tolerance, 255 outside) is wrong on exactly one
kind of pixel: the anti-aliased rim, which the renderer painted as a MIX of the
key and the subject. On a sticker-style sheet over #FF00FF the field measures
(247,2,243), the outline (7,1,8), and the rim pixel between them (118,8,121) —
half key. A tolerance of 40 keeps that pixel fully opaque and purple. Measured
over 25 animation sheets, 25-40% of the pixels within 2 px of transparency
stayed within 150 RGB of the key; `remove_chroma_key.py --despill` on five
static sheets left 20-27% (5-52% per asset once sliced). It reads as a pink hairline around every cut-out, in the
engine and in a GIF alike, and no importer setting removes it: "Alpha Is
Transparency" repairs the RGB under TRANSPARENT pixels, and these are opaque.

What this does instead — in the BOUNDARY BAND only (pixels within --band px of
the keyed field), never in the interior:

  --edge outline (default; art with a dark outline)
      alpha runs along the key -> outline line: 0 at the key, 1 at --hi from it
      (330 by default: a near-black outline sits ~350 from #FF00FF), and the key
      is un-mixed out of the colour, c = (rgb - (1 - a) * key) / a.
  --edge fill (effects and anything with NO outline: sparks, dust, glows)
      the rim pixel is a mix of the key and the fill BESIDE it, so it is
      projected onto the key -> nearest-interior-fill line for its alpha and
      takes that fill's colour. Strongly key-tinted pockets between an effect's
      points (the model blends them) join the band wherever they sit.

  --edge tint (a field painted off the named key: video frames, a generator that paints
      #00FF00 as (3,240,2) or #FF00FF as (216,46,147); and art whose rim mixes the key
      with fills of every colour)
      the key is cut at --lo (96 here) around the named key AND around the colour the
      border was actually painted, but that second ball only takes pixels carrying the
      key's hue signature and what is 8-connected to them inside the ball: a hot-pink
      patch inside the subject that sits near the painted magenta stays. Each pixel's
      key share is k = min(tint / key_tint, 1), tint = mean(key channels) - mean(other
      channels); its colour becomes (rgb - k * painted) / (1 - k) and its alpha 1 - k.
      Where the material past ring --band is itself key-tinted (tint >= 18: a teal jacket
      on green), k = (tint - base) / (key_tint - base) against that material's tint, so
      the rim keeps its hue (baseline_px counts them). Only rings 1..--band (4 here) from the cut are un-mixed — every key-tinted pixel
      farther than 180 from the key, and the nearer (in-band) ones only in rings 1-2;
      tint under 18 is subject and never touched. --despill (on) then recolours small
      trapped spill: 8-connected clusters of still-tinted pixels, at most max(32, 0.5 %
      of the subject) px, one of them tinted past 40, keep their alpha and lose the key;
      a larger key-tinted region is the art's own colour and stays. No choke.

outline and fill then choke: alpha under --choke (0.35) goes to 0, and so does any band pixel
the un-mix could not clean. Nothing inside the band is touched, which is the
whole point — two keys that look simpler are both wrong:

  * alpha from RGB distance EVERYWHERE cannot have both ends. A ramp long
    enough to clean the half-mixed rim (to 330) turns 36-83% of the INTERIOR
    translucent — every fill nearer the key than the outline is, white
    included. A ramp short enough to spare the interior (to 150) leaves the
    half-mixed rim opaque: 33-41% of it still partly key, and a character with
    purple fills loses a quarter of its interior anyway. `--soft-matte` fails
    the same way from the other side: it eats a subject that shares the key's
    channel.
  * alpha from the key's SPILL (min(R,B) - G for magenta) under-reads the key
    in a saturated fill: a half-magenta, half-yellow pixel reads 22% key, so it
    comes out 78% opaque and PINK — 29% of a yellow spark's rim. Blue, white
    and tan effects survive it, which is how it gets shipped.
    Hence the projection onto the neighbouring fill for outline-less art.

The band's alpha is soft (0.35..1) but its colour is clean, so the 1-bit cut a
GIF makes (alpha > 16) lands on un-mixed pixels: no halo. That is the
difference from a soft matte, whose half-keyed pixels keep the key's colour.

`--defringe` repairs sprites that are ALREADY keyed, in place of re-slicing
them — for a shipped set that has since been trimmed, 9-sliced or retouched, or
whose opaque sheet is gone. In the band next to transparency, a pixel still
tinted by the key takes the nearest clean colour and an alpha from the same
projection; the pass repeats while it finds more (choking a pixel away exposes
the one behind it). Nothing is moved or resampled: on 49 shipped sprites the
bounding box changed by at most 1 px, and what went was the outermost,
mostly-key ring. It took them from fringe 5-52 % / tint 26-84 % to 0.0-0.7 % /
0.0-0.4 %. What it cannot clean is the art's own key-hued colour on the rim (a
pink fill on a magenta key) — key a colour the art does not contain.

Every run prints two numbers about the rim (visible pixels within 2 px of
transparency), before and after, and exits 1 if either is still over its limit:
`fringe` — within 150 RGB of the key, mostly key (--fringe-max 0.5 %) — and
`tint` — the interior colour beside it mixed with the key, partly key
(--tint-max 2 %). A binary key reads 25-40 % and 43-60 %; un-mixed, 0.0-0.2 %
and 0.0-0.3 %. `tint` is the one that tells the two wrong keys above from a
right one: the short global ramp reads fringe 0.00 % and tint 33-41 %, the
spill estimate fringe 0.03 % and tint 29 % on a yellow spark.

Examples
  # an opaque sheet from the generator -> a keyed RGBA sheet for slice_grid.py / sheet_to_frames.py
  key_unmix.py raw/hero_idle.png --out keyed/hero_idle.png --key-color '#ff00ff'
  # an effect sheet: no outline to un-mix against
  key_unmix.py raw/fx_spark.png --out keyed/fx_spark.png --edge fill
  # a non-black outline: derive the ramp from its colour
  key_unmix.py raw/ui.png --out keyed/ui.png --outline-color '#081930'
  # video frames or a field painted off the key: signature-grown painted ball + tint un-mix
  key_unmix.py raw/runner_run_012.png --out keyed/runner_run_012.png --key-color '#00ff00' --edge tint
  # already-keyed sprites: measure, then repair in place
  key_unmix.py --defringe Assets/Art/UI --dry-run
  key_unmix.py --defringe Assets/Art/UI --in-place

Exit codes: 0 ok · 1 fringe still above --fringe-max, the input already carries
alpha (the agent keyed it: reject the sheet and ask for an opaque one — or use
--defringe), bad args · 2 nothing was keyed (the field is not --key-color: the
transparent share is under 1%).

  key_unmix.py --selftest    synthetic sheets in a temp dir; `verdict OK|FAIL`, exit 0 or 1

Requires Pillow and numpy (codex's imagegen venv has both: ~/.codex/imagegen-venv/bin/python).
"""
import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sprite_ops as so  # noqa: E402

dist, spill, dilate, nearest_fill, pct, parse_hex = so.dist, so.spill, so.dilate, so.nearest_fill, so.pct, so.parse_hex
FRINGE_DIST = so.FRINGE_DIST

# Between the shared:chroma_unmix markers: a copy of tools/shared-blocks/chroma_unmix.py in the
# repository, which tools/check-consistency.py keeps equal to it. Edit that file, then copy it
# here and into every other file its first line names.
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


def key_sheet(rgb, key, edge, lo, hi, band_px, choke):
    """rgb float32 HxWx3 on a flat `key` field -> (rgb, alpha 0..1, stats)."""
    d = dist(rgb, key)
    bg = d < lo
    band = ~bg & dilate(bg, band_px)
    if edge == "fill":
        band |= ~bg & (d < 200.0) & (spill(rgb, key) > 60.0)
        interior = ~bg & ~band
        if interior.any():
            fill, got = nearest_fill(rgb, interior, band)
            v = fill - key
            ab = np.clip(((rgb - key) * v).sum(axis=2) / np.maximum((v * v).sum(axis=2), 1.0), 0.0, 1.0)
            ab = np.where(got, ab, 0.0)          # a rim with no interior anywhere near it is field
            c = np.where(band[..., None], fill, rgb)
        else:
            ab, c = np.zeros(d.shape, np.float32), rgb
        a = np.where(bg, 0.0, np.where(band, ab, 1.0))
    else:
        ab = np.clip((d - lo * 0.5) / max(hi - lo * 0.5, 1.0), 0.0, 1.0)
        a = np.where(bg, 0.0, np.where(band, ab, 1.0))
        an = np.maximum(a, 0.02)[..., None]
        c = np.where(band[..., None], (rgb - (1.0 - a[..., None]) * key) / an, rgb)
    c = np.clip(c, 0.0, 255.0)
    choked = band & (a > 0) & (a < choke)
    still = band & (a >= choke) & (dist(c, key) < FRINGE_DIST)
    a = np.where(choked | still, 0.0, a)
    c = np.where((a > 0)[..., None], c, 0.0)      # never leave the key's colour under a transparent pixel
    return c, a, dict(field_px=int(bg.sum()), band_px=int(band.sum()),
                      choked_px=int(choked.sum()), uncleanable_px=int(still.sum()))


def defringe(rgba, key, band_px, choke, passes=3):
    """Already-keyed RGBA float32 -> (rgba, fixed px). Geometry untouched; only tinted rim pixels change.

    A rim pixel is tinted when it is near the key, leans to the key's hue, or sits on the line
    from the interior colour beside it to the key (the same test `tint` is measured with, at a
    lower share so the repair reaches further than the gate). It takes the nearest clean colour
    and an alpha from its projection on that colour -> key line. Chocking a pixel away exposes
    the one behind it, so the pass repeats until nothing more is found."""
    out, total = rgba.copy(), 0
    for _ in range(passes):
        rgb, al = out[..., :3], out[..., 3]
        solid = al > 0
        band = solid & dilate(~solid, band_px)
        bad = band & ((dist(rgb, key) < 200.0) | (spill(rgb, key) > 70.0))
        inner = solid & ~band
        if inner.any():
            beside, got = nearest_fill(rgb, inner, band, max_iter=8)
            share, on_line = so.key_share(rgb, beside, key)
            bad |= band & got & on_line & (share >= 0.15)
        clean = solid & ~bad
        if not bad.any() or not clean.any():
            break
        fill, got = nearest_fill(rgb, clean, bad)
        v = fill - key
        a = np.clip(((rgb - key) * v).sum(axis=2) / np.maximum((v * v).sum(axis=2), 1.0), 0.0, 1.0)
        fix = bad & got & (a < 0.98)                  # a pixel already on its fill has nothing to un-mix
        if not fix.any():
            break
        out[..., :3] = np.where(fix[..., None], fill, rgb)
        na = np.where(fix, al * a, al)
        na = np.where(fix & (na < choke * 255.0), 0.0, na)
        out[..., 3] = na
        out[..., :3] = np.where((na > 0)[..., None], out[..., :3], 0.0)
        total += int(fix.sum())
    return out, total


def key_tint(src, name, a):
    """--edge tint for one opaque sheet: print the report, write the output. -> (fringe %, tint %), or
    None when under 1 % was keyed (the caller exits 2)."""
    rgb8 = np.asarray(src.convert("RGB"))
    rgb = rgb8.astype(np.float32)
    key = border_median(rgb) if a.key_color == "auto" else np.asarray(parse_hex(a.key_color), np.float32)
    key = tuple(int(round(float(v))) for v in key)
    out, st = key_tint_unmix(rgb8, key, key_threshold=a.lo, unmix_reach=a.band, despill=a.despill)
    pk = st["painted_key"]
    off = float(np.sqrt(sum((p - k) ** 2 for p, k in zip(pk, key))))
    print(f"key #{key[0]:02x}{key[1]:02x}{key[2]:02x} painted_key ({pk[0]},{pk[1]},{pk[2]}) off_by {off:.1f} "
          f"key_tint {st['key_tint']:g}")
    if not key_channel_split(key)[0]:
        print("WARN: this key has no tint axis (it needs a channel >= 192 and one < 64): only the hard cut ran.")
    c, al = out[..., :3].astype(np.float32), out[..., 3].astype(np.float32)
    hard = (dist(rgb, np.asarray(key, np.float32)) > 40.0) * 255.0
    b0, t0, r0 = so.rim_stats(rgb, hard, key)
    b1, t1, r1 = so.rim_stats(c, al, key)
    transparent = 100.0 * float((al == 0).mean())
    print(f"keyed {name} edge tint lo {a.lo:g} band {a.band} despill {'on' if a.despill else 'off'} "
          f"transparent_pct {transparent:.1f} keyed_px {st['keyed_px']} unmixed_px {st['unmixed_px']} "
          f"baseline_px {st['baseline_px']} "
          f"spill_px {st['spill_px']} spill_clusters {st['spill_clusters']}")
    print(f"fringe_pct binary_key {pct(b0, r0):.2f} -> unmixed {pct(b1, r1):.2f} (rim_px {r1})")
    print(f"tint_pct binary_key {pct(t0, r0):.2f} -> unmixed {pct(t1, r1):.2f}")
    if transparent < 1.0:
        print(f"ERROR: {transparent:.2f}% of {name} was keyed — the field is not this key colour.", file=sys.stderr)
        return None
    if not a.dry_run:
        dest = a.out or os.path.join(a.outdir, name)
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        Image.fromarray(out, "RGBA").save(dest)
        print(f"wrote {dest}")
    return pct(b1, r1), pct(t1, r1)


def border_median(rgb):
    ring = np.concatenate([rgb[:2].reshape(-1, 3), rgb[-2:].reshape(-1, 3),
                           rgb[:, :2].reshape(-1, 3), rgb[:, -2:].reshape(-1, 3)])
    return np.median(ring, axis=0)


def save_rgba(c, a255, path):
    out = np.dstack([np.clip(np.rint(c), 0, 255), np.clip(np.rint(a255), 0, 255)]).astype(np.uint8)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    Image.fromarray(out, "RGBA").save(path)


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main():
    ap = UsageParser(description="Key a flat chroma field out by un-mixing the boundary band, "
                                             "or de-fringe sprites that are already keyed.")
    ap.add_argument("inputs", nargs="+", help="an opaque sheet on a flat key field; with --defringe, keyed "
                                              "PNG files or directories of them")
    ap.add_argument("--out", help="output RGBA PNG (one input)")
    ap.add_argument("--outdir", help="output directory (several inputs, or --defringe without --in-place)")
    ap.add_argument("--key-color", default="#ff00ff",
                    help="the key colour named in the generation prompt (default #ff00ff), or 'auto' = the "
                         "median colour of the sheet's 2 px border")
    ap.add_argument("--edge", choices=["outline", "fill", "tint"], default="outline",
                    help="outline (default) = the rim is key mixed with a dark outline; fill = no outline "
                         "(effects): project each rim pixel onto the fill beside it; tint = un-mix the key's "
                         "share from its tint, with a second cut around the colour the border was painted")
    ap.add_argument("--lo", type=float, default=None,
                    help="RGB distance from the key still counted as the field (default 60: a painted "
                         "#FF00FF field measures up to ~45 off at the sheet corners; --edge tint: 96, the "
                         "radius of both balls)")
    ap.add_argument("--hi", type=float, default=None,
                    help="--edge outline: distance from the key at which a rim pixel is fully opaque "
                         "(default 330, a near-black outline; or derived from --outline-color)")
    ap.add_argument("--outline-color", help="--edge outline: the outline's colour, e.g. '#081930' — sets --hi "
                                            "to 0.94 of its distance from the key")
    ap.add_argument("--band", type=int, default=None,
                    help="width of the boundary band in px (default 2; --edge tint: 4 rings un-mixed)")
    ap.add_argument("--despill", action=argparse.BooleanOptionalAction, default=True,
                    help="--edge tint: recolour small trapped key spill inside the subject (default on)")
    ap.add_argument("--choke", type=float, default=0.35, help="rim alpha below this goes to 0 (default 0.35)")
    ap.add_argument("--fringe-max", type=float, default=0.5, help="exit 1 above this fringe %% (default 0.5)")
    ap.add_argument("--tint-max", type=float, default=2.0, help="exit 1 above this tint %% (default 2)")
    ap.add_argument("--defringe", action="store_true",
                    help="inputs are ALREADY keyed: repair the tinted rim without moving geometry")
    ap.add_argument("--in-place", action="store_true", help="--defringe: overwrite the inputs")
    ap.add_argument("--dry-run", action="store_true", help="measure and report only; write nothing")
    a = ap.parse_args()
    if a.lo is None:
        a.lo = 96.0 if a.edge == "tint" else 60.0
    if a.band is None:
        a.band = 4 if a.edge == "tint" and not a.defringe else 2

    files = []
    for p in a.inputs:
        files += sorted(glob.glob(os.path.join(p, "*.png"))) if os.path.isdir(p) else [p]
    if not files:
        print("ERROR: no input files", file=sys.stderr)
        return 1
    if not a.dry_run:
        if a.defringe and not (a.in_place or a.outdir):
            print("ERROR: --defringe needs --in-place, --outdir or --dry-run", file=sys.stderr)
            return 1
        if not a.defringe and not (a.out or a.outdir):
            print("ERROR: need --out (one input) or --outdir (or --dry-run)", file=sys.stderr)
            return 1
        if a.out and len(files) != 1:
            print("ERROR: --out takes exactly one input; use --outdir for several", file=sys.stderr)
            return 1
    if a.hi is not None and a.outline_color:
        print("ERROR: give --hi or --outline-color, not both", file=sys.stderr)
        return 1

    worst_f, worst_t, rc = 0.0, 0.0, 0
    for path in files:
        src = Image.open(path)
        name = os.path.basename(path)
        has_alpha = "A" in src.getbands() and src.getchannel("A").getextrema()[0] < 255
        if a.defringe:
            rgba = np.asarray(src.convert("RGBA")).astype(np.float32)
            key = np.asarray(parse_hex("#ff00ff" if a.key_color == "auto" else a.key_color), np.float32)
            b0, t0, r0 = so.rim_stats(rgba[..., :3], rgba[..., 3], key)
            out, fixed = defringe(rgba, key, a.band, a.choke)
            b1, t1, r1 = so.rim_stats(out[..., :3], out[..., 3], key)
            print(f"defringe {name} fixed_px {fixed} rim_px {r0} fringe_pct {pct(b0, r0):.2f} -> {pct(b1, r1):.2f} "
                  f"tint_pct {pct(t0, r0):.2f} -> {pct(t1, r1):.2f}")
            worst_f, worst_t = max(worst_f, pct(b1, r1)), max(worst_t, pct(t1, r1))
            if not a.dry_run and fixed:
                save_rgba(out[..., :3], out[..., 3], path if a.in_place else os.path.join(a.outdir, name))
            continue
        if has_alpha:
            print(f"ERROR: {path} already carries alpha — the agent keyed it itself, and such a key has no "
                  f"fully opaque rim to un-mix. Reject the sheet and ask for an OPAQUE image on the flat key "
                  f"colour; for sprites that are already keyed and shipped, use --defringe.", file=sys.stderr)
            rc = 1
            continue
        if a.edge == "tint":
            got = key_tint(src, name, a)
            if got is None:
                rc = max(rc, 2)
                continue
            worst_f, worst_t = max(worst_f, got[0]), max(worst_t, got[1])
            continue
        rgb = np.asarray(src.convert("RGB")).astype(np.float32)
        field = border_median(rgb)
        key = field if a.key_color == "auto" else np.asarray(parse_hex(a.key_color), np.float32)
        off = float(np.sqrt(((field - key) ** 2).sum()))
        print(f"key #{int(key[0]):02x}{int(key[1]):02x}{int(key[2]):02x} painted_field "
              f"({field[0]:.0f},{field[1]:.0f},{field[2]:.0f}) off_by {off:.1f}")
        if off > a.lo:
            print(f"WARN: the sheet's border is {off:.0f} from --key-color, further than --lo {a.lo:g}: this is "
                  f"not the field the prompt named. Check the hex, or pass --key-color auto.")
        hi = a.hi
        if a.outline_color:
            oc = np.asarray(parse_hex(a.outline_color), np.float32)
            hi = 0.94 * float(np.sqrt(((oc - key) ** 2).sum()))
        hi = 330.0 if hi is None else hi
        hard = (dist(rgb, key) > 40.0) * 255.0            # what a binary key at tolerance 40 would ship
        b0, t0, r0 = so.rim_stats(rgb, hard, key)
        c, al, st = key_sheet(rgb, key, a.edge, a.lo, hi, a.band, a.choke)
        b1, t1, r1 = so.rim_stats(c, al, key)
        transparent = 100.0 * float((al == 0).mean())
        print(f"keyed {name} edge {a.edge} lo {a.lo:g}" + (f" hi {hi:g}" if a.edge == "outline" else "")
              + f" band {a.band} choke {a.choke:g} transparent_pct {transparent:.1f} band_px {st['band_px']} "
                f"choked_px {st['choked_px']} uncleanable_px {st['uncleanable_px']}")
        print(f"fringe_pct binary_key {pct(b0, r0):.2f} -> unmixed {pct(b1, r1):.2f} (rim_px {r1})")
        print(f"tint_pct binary_key {pct(t0, r0):.2f} -> unmixed {pct(t1, r1):.2f}")
        if transparent < 1.0:
            print(f"ERROR: {transparent:.2f}% of {name} was keyed — the field is not this key colour.",
                  file=sys.stderr)
            rc = max(rc, 2)
            continue
        worst_f, worst_t = max(worst_f, pct(b1, r1)), max(worst_t, pct(t1, r1))
        if not a.dry_run:
            dest = a.out or os.path.join(a.outdir, name)
            save_rgba(c, al * 255.0, dest)
            print(f"wrote {dest}")
    if worst_f > a.fringe_max or worst_t > a.tint_max:
        hint = ("what is left is the art's own key-hued colour on the rim (a pink or purple fill on a magenta "
                "key), or a mix deeper than --band: a key colour the art lacks avoids the first" if a.defringe else
                "the art itself carries the key's hue (pink / purple fills are not an effect): use --edge outline"
                if a.edge == "fill" else
                "a key-tinted mix deeper than --band, or a field that is not this key: check --key-color, widen "
                "--band" if a.edge == "tint" else
                "outline-less art (sparks, dust, glows) wants --edge fill; a coloured outline wants --outline-color")
        print(f"FAIL: fringe {worst_f:.2f}% (max {a.fringe_max:g}) tint {worst_t:.2f}% (max {a.tint_max:g}) — {hint}.",
              file=sys.stderr)
        rc = max(rc, 1)
    return rc


# --------------------------------------------------------------- selftest ----
def _disc(h, w, cy, cx, r):
    y, x = np.mgrid[0:h, 0:w] + 0.5
    return np.clip(r - np.sqrt((y - cy) ** 2 + (x - cx) ** 2) + 0.5, 0.0, 1.0)


def _over(img, cover, colour):
    return img * (1.0 - cover[..., None]) + np.asarray(colour, np.float64) * cover[..., None]


def _identity_sheet():
    """Outline art and an outline-less spark on #FF00FF, anti-aliased, no randomness."""
    h, w = 64, 128
    img = np.ones((h, w, 3)) * (255.0, 0.0, 255.0)
    img = _over(img, _disc(h, w, 32, 32, 26), (8, 4, 10))
    img = _over(img, _disc(h, w, 32, 32, 22), (240, 200, 40))
    img = _over(img, _disc(h, w, 30, 92, 15), (120, 220, 255))
    img = _over(img, _disc(h, w, 50, 116, 6), (255, 255, 255))
    return np.rint(img).astype(np.float32)


# sha256 of the uint8 RGBA key_sheet() returns on _identity_sheet(): outline and fill must never move.
IDENTITY = {"outline": "b5dabd4136d82ff2606acab1718ae64b4b9b3adb8547f4f4ca25c7dfa0fec5a3", "fill": "d6bb309aacb81c21e94a54093bd9348762180071fbe94ef9791d77c62ae10695"}


def _identity_hash(edge):
    import hashlib
    c, al, _ = key_sheet(_identity_sheet(), np.asarray((255.0, 0.0, 255.0), np.float32), edge, 60.0, 330.0, 2, 0.35)
    out = np.dstack([np.clip(np.rint(c), 0, 255), np.clip(np.rint(al * 255.0), 0, 255)]).astype(np.uint8)
    return hashlib.sha256(out.tobytes()).hexdigest()


def selftest():
    import subprocess
    import tempfile
    fails = []

    def check(ok, what):
        print(("ok    " if ok else "FAIL  ") + what)
        if not ok:
            fails.append(what)

    for edge in ("outline", "fill"):
        check(_identity_hash(edge) == IDENTITY[edge], f"--edge {edge} output is byte-identical on the fixed sheet")

    # a magenta key painted dim, a blue subject with a dark outline, and three interior features
    h = w = 96
    painted = (216, 46, 147)
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.ones((h, w, 3)) * painted + ((xx + yy) % 3 - 1)[..., None]
    img = _over(img, _disc(h, w, 48, 48, 40), (8, 4, 10))
    img = _over(img, _disc(h, w, 48, 48, 36), (60, 140, 230))
    hot, big, trap = (slice(24, 32), slice(44, 52)), (slice(40, 60), slice(52, 72)), (slice(66, 69), slice(30, 33))
    img[hot] = (250, 77, 150)              # near the painted colour, lacks its signature (G lit)
    img[big] = (170, 90, 200)              # a key-tinted region of the art's own, too large to be spill
    img[trap] = np.rint(0.5 * np.asarray((60, 140, 230)) + 0.5 * np.asarray(painted))
    src = np.clip(np.rint(img), 0, 255).astype(np.uint8)
    key = (255, 0, 255)
    out, st = key_tint_unmix(src, key)
    tint = lambda px: (px[..., 0].astype(np.float64) + px[..., 2]) / 2.0 - px[..., 1]  # noqa: E731
    check(all(abs(a - b) <= 2 for a, b in zip(st["painted_key"], painted)),
          f"painted key read from the border {tuple(st['painted_key'])} ~ {painted}")
    outside = np.sqrt((yy + 0.5 - 48) ** 2 + (xx + 0.5 - 48) ** 2) > 41.0
    check(bool((out[outside][:, 3] == 0).all()), "the whole painted field is keyed (second ball)")
    plain, _ = key_tint_unmix(src, key, painted_key=key)
    check(float((plain[..., 3] == 0).mean()) < 0.05, "without the painted ball the dim field survives (control)")
    check(float(np.sqrt(((np.asarray((250, 77, 150)) - painted) ** 2).sum())) <= 96.0
          and bool((out[hot] == np.dstack([src[hot], np.full(src[hot].shape[:2], 255, np.uint8)])).all()),
          "an interior hot-pink patch inside the painted ball, not grown from the field, survives untouched")
    check(bool((out[big][..., :3] == src[big]).all() and (out[big][..., 3] == 255).all()),
          "a key-tinted region larger than the spill limit stays untouched")
    tr = out[trap]
    check(bool((tr[..., 3] == 255).all()) and float(tint(tr).max()) < 18.0
          and float(np.abs(tr[..., :3].astype(int) - (60, 140, 230)).max()) <= 6,
          f"trapped spill recoloured to the fill, alpha kept (tint {float(tint(tr).max()):.1f})")
    vis = out[..., 3] > 0
    rim = vis & so.dilate(~vis, 2)
    check(st["unmixed_px"] > 0 and float(tint(out[rim]).max()) < 18.0,
          f"rim un-mixed: every visible pixel within 2 px of transparency has tint < 18 "
          f"({float(tint(out[rim]).max()):.1f})")
    soft = rim & (out[..., 3] < 255)
    check(bool(soft.any()), "the rim carries partial alpha")
    nosp, _ = key_tint_unmix(src, key, despill=False)
    check(bool((nosp[trap][..., :3] == src[trap]).all()), "--no-despill leaves the trapped spill as it was")

    # a teal disc (key-tinted material) on a painted green field, its rim blended into the field
    gp, teal = np.asarray((3, 240, 4), np.float64), np.asarray((0, 130, 160), np.float64)
    r = np.sqrt((yy + 0.5 - 48) ** 2 + (xx + 0.5 - 48) ** 2)
    cov = np.clip(36.0 - r, 0.0, 1.0)
    cov = np.where((r > 35) & (r < 37), np.clip((37.0 - r) / 2.0, 0.0, 1.0), cov)
    gsrc = np.clip(np.rint(cov[..., None] * teal + (1 - cov[..., None]) * gp), 0, 255).astype(np.uint8)
    gk = (0, 255, 0)
    gout, gst = key_tint_unmix(gsrc, gk)
    graw, _ = key_tint_unmix(gsrc, gk, material_baseline=False)
    grim = (gout[..., 3] > 64) & (r > 33) & (r < 37)
    err = lambda o: float(np.abs(o[grim][:, :3].astype(int) - teal.astype(int)).max())  # noqa: E731
    check(gst["baseline_px"] > 0 and bool(grim.any()) and err(gout) <= 24,
          f"a teal rim on green keeps the teal (max channel error {err(gout):.0f})")
    check(err(graw) > err(gout), f"control: without the material baseline the rim drifts ({err(graw):.0f})")

    with tempfile.TemporaryDirectory() as tmp:
        sheet, grey = os.path.join(tmp, "sentry.png"), os.path.join(tmp, "grey.png")
        Image.fromarray(src).save(sheet)
        Image.fromarray(np.full((32, 32, 3), 128, np.uint8)).save(grey)
        me = os.path.abspath(__file__)
        r = subprocess.run([sys.executable, me, sheet, "--out", os.path.join(tmp, "o.png"), "--edge", "tint"],
                           capture_output=True, text=True)
        check(r.returncode == 0 and os.path.isfile(os.path.join(tmp, "o.png")), f"CLI --edge tint exits 0 ({r.returncode})")
        r = subprocess.run([sys.executable, me, grey, "--out", os.path.join(tmp, "g.png"), "--edge", "tint"],
                           capture_output=True, text=True)
        check(r.returncode == 2, f"CLI --edge tint on a field that is not the key exits 2 ({r.returncode})")
    print("verdict " + ("FAIL" if fails else "OK"))
    return 1 if fails else 0


if __name__ == "__main__":
    if sys.argv[1:] in (["--selftest"], ["selftest"]):
        sys.exit(selftest())
    sys.exit(main())
