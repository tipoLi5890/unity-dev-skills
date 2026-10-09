#!/usr/bin/env python3
"""sprite_ops.py — the numpy operations the keyer, the slicer and the gates share.

Not a command. `key_unmix.py`, `sheet_to_frames.py --register`, `audit_frames.py`
and `audit_set.py --key-color` import it, so the four cannot disagree about what
a "core", a "fringe" or "out of register" is: one definition, read by the tool
that writes a frame and by the gate that judges it. Keep it beside them — the
scripts directory travels as a whole.

Definitions (each is a number the docs quote):

  core     the solid silhouette (alpha > 127) opened by 4 px, so anything thinner
           than ~8 px — a bat, a tail, a waving arm, a motion line — drops out and
           cannot steer a registration or a measurement. A subject too thin to
           survive the opening falls back to the plain silhouette.
  feet     the lowest row of the core.
  head_x   the x centroid of the top 15% of the core's rows.
  rim      visible pixels (alpha > 0) within 2 px (4-connected) of a fully
           transparent pixel.
  fringe   rim pixels within 150 RGB of the key colour: mostly key. On a black
           outline that is a pixel more than ~57% key.
  tint     rim pixels that are the interior colour beside them MIXED with the
           key: on the straight line from that colour to the key, a quarter of
           the way along or further. Partly key — the number that sees a
           half-mixed rim (dark purple on a black outline) and a pink rim on a
           yellow spark, both of which `fringe` passes. A rim that merely differs
           from the interior (a black outline round a white fill, a white edge on
           a yellow spark) is off that line and is not counted.
  slip     the whole-frame move that would best re-seat a frame on its reference
           (maximum core IoU, by FFT cross-correlation), counted only when it
           gains at least 0.02 IoU. Registered frames read 0-2 px; frames sliced
           at their in-cell position read tens of px.

Requires Pillow and numpy (codex's imagegen venv has both: ~/.codex/imagegen-venv/bin/python).
"""
import numpy as np
from PIL import Image

SOLID = 127           # alpha above this is the silhouette
OPEN_PX = 4           # the core is the silhouette opened by this many px
HEAD_FRAC = 0.15      # the head band: the top 15% of the core's rows
RIM_PX = 2            # the rim: this many px from transparency
FRINGE_DIST = 150.0   # RGB distance to the key under which a rim pixel is "mostly key"
TINT_SHARE = 0.25     # a rim pixel this far along the interior -> key line is "partly key"
TINT_OFF_LINE = 0.35  # ...provided it sits on that line: off-line distance <= this share of the along distance (+10)
SLIP_GAIN = 0.02      # an IoU gain smaller than this is a flat optimum, not a slip

CROSS = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
SQUARE = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
RING8 = [o for o in SQUARE if o != (0, 0)]


def parse_hex(s):
    s = s.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"not a hex colour: {s!r}")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


# ------------------------------------------------------------- morphology ----
def shifted(m, dy, dx):
    """m moved by (dy, dx) along its first two axes, zeros shifted in."""
    h, w = m.shape[:2]
    out = np.zeros_like(m)
    if abs(dy) >= h or abs(dx) >= w:
        return out
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    out[yd, xd] = m[ys, xs]
    return out


def dilate(m, iterations=1, offsets=CROSS):
    for _ in range(iterations):
        acc = np.zeros_like(m)
        for dy, dx in offsets:
            acc |= shifted(m, dy, dx)
        m = acc
    return m


def erode(m, iterations=1, offsets=SQUARE):
    """Outside the image counts as empty, so a mask erodes from the canvas border too."""
    for _ in range(iterations):
        acc = np.ones_like(m)
        for dy, dx in offsets:
            acc &= shifted(m, dy, dx)
        m = acc
    return m


def core(alpha):
    m = alpha > SOLID
    c = dilate(erode(m, OPEN_PX), OPEN_PX, SQUARE)
    return c if c.sum() > 0.2 * m.sum() else m


def bottom(mask):
    ys = np.nonzero(mask.any(axis=1))[0]
    return int(ys.max()) if len(ys) else None


def head_x(c):
    ys = np.nonzero(c.any(axis=1))[0]
    if not len(ys):
        return None
    top, bot = int(ys.min()), int(ys.max())
    band = c[top:top + max(1, int(round((bot - top + 1) * HEAD_FRAC)))]
    xs = np.nonzero(band)[1]
    return float(xs.mean()) if len(xs) else None


def cut_by_canvas(alpha):
    s = alpha > SOLID
    return bool(s[0].any() or s[-1].any() or s[:, 0].any() or s[:, -1].any())


# ----------------------------------------------------------------- colour ----
def dist(rgb, key):
    return np.sqrt(((rgb - np.asarray(key, np.float32)) ** 2).sum(axis=2))


def spill(rgb, key):
    """How far a pixel leans toward the key's hue: the smallest of the key's high channels minus
    the largest of its low ones (magenta: min(R,B) - G; green: G - max(R,B)). Signed; 0 for a grey key."""
    hi = [i for i in range(3) if key[i] > 127]
    lo = [i for i in range(3) if key[i] <= 127]
    if not hi or not lo:
        return np.zeros(rgb.shape[:2], np.float32)
    return rgb[..., hi].min(axis=2) - rgb[..., lo].max(axis=2)


def nearest_fill(rgb, known, need, max_iter=256):
    """Colour for every `need` pixel from the nearest `known` ones: rings grown one pixel at a
    time, each new pixel taking the mean of its already-known 8-neighbours.
    Returns (rgb with the need pixels filled, the mask of pixels that now hold a colour)."""
    out = rgb.copy()
    known = known.copy()
    for _ in range(max_iter):
        todo = need & ~known
        if not todo.any():
            break
        ys, xs = np.nonzero(todo)
        y0, y1 = max(0, ys.min() - 1), min(rgb.shape[0], ys.max() + 2)
        x0, x1 = max(0, xs.min() - 1), min(rgb.shape[1], xs.max() + 2)
        k, c, t = known[y0:y1, x0:x1], out[y0:y1, x0:x1], todo[y0:y1, x0:x1]
        acc = np.zeros(c.shape, np.float32)
        cnt = np.zeros(k.shape, np.float32)
        for dy, dx in RING8:
            ks = shifted(k, dy, dx)
            acc += shifted(c, dy, dx) * ks[..., None]
            cnt += ks
        new = t & (cnt > 0)
        if not new.any():
            break
        c[new] = acc[new] / cnt[new][:, None]
        k[new] = True
    return out, known


def key_share(rgb, fill, key):
    """For every pixel: how far it sits along the straight line from `fill` (the interior colour
    beside it) to the key — 0 = that colour, 1 = the key — and whether it is ON that line (its
    off-line distance is at most TINT_OFF_LINE of its along distance, + 10). A rim that merely
    differs from the interior is off the line; a rim that is the interior mixed with key is on it."""
    to_key = np.asarray(key, np.float32) - fill
    step = rgb - fill
    span = np.maximum((to_key * to_key).sum(axis=2), 1.0)
    share = (step * to_key).sum(axis=2) / span
    along = share * np.sqrt(span)
    off = np.sqrt(np.maximum((step * step).sum(axis=2) - along * along, 0.0))
    return share, off <= TINT_OFF_LINE * along + 10.0


def rim_stats(rgb, alpha, key):
    """(fringe px, tint px, rim px) of one image: rgb float32 HxWx3, alpha HxW (any scale; > 0 = visible)."""
    key = np.asarray(key, np.float32)
    visible = alpha > 0
    rim = visible & dilate(~visible, RIM_PX)
    n = int(rim.sum())
    if not n:
        return 0, 0, 0
    bad = int((rim & (dist(rgb, key) < FRINGE_DIST)).sum())
    inner = visible & ~rim
    tinted = 0
    if inner.any():
        fill, got = nearest_fill(rgb, inner, rim, max_iter=8)
        share, on_line = key_share(rgb, fill, key)
        tinted = int((rim & got & on_line & (share >= TINT_SHARE)).sum())
    return bad, tinted, n


def pct(part, whole):
    return 100.0 * part / whole if whole else 0.0


def clean_tail(rgba_u8, thr, clear=False):
    """Repair the colour of the low-alpha tail a resampler leaves round a sprite.

    LANCZOS over a premultiplied image ends in a ring of alpha 1-3, and un-premultiplying a
    channel value of 1 at alpha 1 gives 255: the ring's stored colour is noise, amplified to full
    saturation (measured: (255,0,255) at alpha 1 from a near-black outline). It is invisible in
    the PNG and it is what a bilinear filter mixes into the outline. Pixels at 0 < alpha <= thr
    take the colour of the nearest content pixel (alpha > thr) and keep their alpha; with
    clear=True they are zeroed instead. Fully transparent pixels are left at RGB 0.
    Returns (rgba uint8, tail px)."""
    a = rgba_u8[..., 3]
    tail = (a > 0) & (a <= thr)
    n = int(tail.sum())
    out = rgba_u8.copy()
    if n:
        if clear:
            out[tail] = 0
        else:
            fill, got = nearest_fill(rgba_u8[..., :3].astype(np.float32), a > thr, tail, max_iter=6)
            fixed = tail & got
            out[..., :3][fixed] = np.clip(np.rint(fill[fixed]), 0, 255).astype(np.uint8)
            out[tail & ~got] = 0                      # a speck with no content near it
    out[..., :3][out[..., 3] == 0] = 0
    return out, n


# ----------------------------------------------------------- registration ----
def iou_map(ref, frame):
    """IoU of two boolean masks for EVERY whole-pixel shift of `frame`.
    Returns (iou, (oy, ox)): iou[oy + dy, ox + dx] is the overlap with frame moved by (dy, dx)."""
    H, W = ref.shape[0] + frame.shape[0] - 1, ref.shape[1] + frame.shape[1] - 1
    F = np.fft.rfft2(ref.astype(np.float32), (H, W)) * np.fft.rfft2(frame[::-1, ::-1].astype(np.float32), (H, W))
    inter = np.rint(np.fft.irfft2(F, (H, W)))
    union = float(ref.sum()) + float(frame.sum()) - inter
    return inter / np.maximum(union, 1.0), (frame.shape[0] - 1, frame.shape[1] - 1)


def best_shift(ref, frame, lock_dy=None):
    """(dx, dy, iou there, iou at no shift). lock_dy pins the vertical move (a locked feet line)."""
    iou, (oy, ox) = iou_map(ref, frame)
    here = float(iou[oy, ox])
    if lock_dy is not None:
        row = oy + lock_dy
        if not 0 <= row < iou.shape[0]:
            return 0, lock_dy, 0.0, here
        j = int(np.argmax(iou[row]))
        return j - ox, lock_dy, float(iou[row, j]), here
    i, j = np.unravel_index(int(np.argmax(iou)), iou.shape)
    return j - ox, i - oy, float(iou[i, j]), here


def slip(ref, frame, grounded):
    """How far `frame` sits from where its silhouette best overlaps `ref`, in px (0 if moving it
    would gain less than SLIP_GAIN of IoU). Grounded frames are only tested sideways."""
    ys, xs = np.nonzero(ref | frame)
    if not len(ys):
        return 0, 0
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    dx, dy, best, here = best_shift(ref[y0:y1, x0:x1], frame[y0:y1, x0:x1], 0 if grounded else None)
    return (dx, dy) if best - here >= SLIP_GAIN else (0, 0)


def scaled_alpha(alpha_u8, s):
    """An 8-bit alpha plane resampled by s (LANCZOS), as a uint8 array."""
    if s == 1.0:
        return alpha_u8
    h, w = alpha_u8.shape
    im = Image.fromarray(alpha_u8, "L").resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    return np.asarray(im)


def register(alpha_u8, ref_core, mode, scales=(1.0,)):
    """Seat one frame on the reference: (scale, dx, dy, iou).

    (dx, dy) is where the frame's cell origin goes relative to the reference cell's origin, in
    source pixels, once the frame has been resampled by `scale`. mode "ground" locks the feet —
    the lowest row of each core — to one line and searches x only; "free" searches x and y.
    A scale other than 1 is only tried when `scales` offers one, and loses 0.3 of IoU per unit
    of |scale - 1|, so the drawing's own size wins a tie."""
    best = (-1.0, 1.0, 0, 0, 0.0)
    rb = bottom(ref_core)
    for s in scales:
        fc = core(scaled_alpha(alpha_u8, s))
        if not fc.any():
            continue
        lock = (rb - bottom(fc)) if mode == "ground" else None
        dx, dy, iou, _ = best_shift(ref_core, fc, lock)
        score = iou - 0.3 * abs(s - 1.0)
        if score > best[0]:
            best = (score, float(s), int(dx), int(dy), iou)
    return best[1], best[2], best[3], best[4]


# ---------------------------------------------------------------- slicing ----
def find_cuts(profile, n, window=0.25):
    """n+1 cut positions along one axis of a content profile (content pixels per row or column),
    and for each interior cut whether it is CLEAN (it runs through no content).

    The model does not draw its rows at exact thirds. Each interior cut stays on the nominal
    equal split when that line is empty; otherwise it moves to the middle of the widest empty
    run within ±window of a cell; and when the window holds no empty line at all it goes to the
    least content nearest the nominal line and is reported not clean — the neighbours touch."""
    L = len(profile)
    cuts, clean = [0], []
    for k in range(1, n):
        nom = int(round(k * L / n))
        nom = min(max(nom, 1), L - 1)
        if profile[nom] == 0 and profile[nom - 1] == 0:
            cuts.append(nom)
            clean.append(True)
            continue
        w = max(1, int(L / n * window))
        lo, hi = max(1, nom - w), min(L - 1, nom + w)
        seg = np.asarray(profile[lo:hi])
        m = seg.min()
        idx = np.nonzero(seg <= m)[0]
        runs = np.split(idx, np.nonzero(np.diff(idx) > 1)[0] + 1)
        if m == 0:
            run = max(runs, key=lambda r: (len(r), -abs((r[0] + r[-1]) / 2 + lo - nom)))
        else:
            run = min(runs, key=lambda r: abs((r[0] + r[-1]) / 2 + lo - nom))
        cuts.append(int(lo + (run[0] + run[-1] + 1) // 2))
        clean.append(bool(m == 0))
    return cuts + [L], clean


def label(mask):
    """8-connected components of a boolean mask -> (int32 labels, 1-based; count). Run-based union-find."""
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
        a0, a1, b0, b1 = row_start[r], row_start[r + 1], row_start[r - 1], row_start[r]
        i, j = a0, b0
        while i < a1 and j < b1:
            if cs[i] <= ce[j] and cs[j] <= ce[i]:          # the runs touch, diagonals included
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
            if ce[i] < ce[j]:
                i += 1
            else:
                j += 1
    roots, ids = {}, np.zeros(n, np.int32)
    for i in range(n):
        ids[i] = roots.setdefault(find(i), len(roots) + 1)
    lab = np.zeros((h, w), np.int32)
    for i in range(n):
        lab[rs[i], cs[i]:ce[i]] = ids[i]
    return lab, len(roots)


def isolate(alpha_u8, thr):
    """The subject of one cut cell, and what was not it.

    Components are taken over the content pixels (alpha > thr); the SUBJECT is the one holding
    the most solid pixels. Any other component that touches the cell's cut border is a
    neighbour's bleed or an edge speck and is dropped. Everything else — a ball in flight, a
    spark, a sweat drop — stays, wherever it is.
    Returns (keep mask, sides the SUBJECT itself touches as [left, top, right, bottom], dropped px)."""
    content = alpha_u8 > thr
    lab, n = label(content)
    if n == 0:
        return content, [False] * 4, 0
    solid = np.bincount(lab[alpha_u8 > SOLID], minlength=n + 1)
    solid[0] = 0
    main = int(np.argmax(solid)) if solid.max() else int(np.argmax(np.bincount(lab.ravel(), minlength=n + 1)[1:])) + 1
    edge = np.zeros(n + 1, bool)
    for strip in (lab[0], lab[-1], lab[:, 0], lab[:, -1]):
        edge[np.unique(strip)] = True
    edge[0] = False
    drop = edge.copy()
    drop[main] = False
    keep = content & ~drop[lab]
    m = lab == main
    touch = [bool(m[:, 0].any()), bool(m[0].any()), bool(m[:, -1].any()), bool(m[-1].any())]
    return keep, touch, int((content & drop[lab]).sum())


if __name__ == "__main__":
    print(__doc__)
