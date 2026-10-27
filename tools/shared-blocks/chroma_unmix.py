# targets: skills/codex-visual/scripts/key_unmix.py, skills/sprite-from-video/scripts/video_frames.py
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
