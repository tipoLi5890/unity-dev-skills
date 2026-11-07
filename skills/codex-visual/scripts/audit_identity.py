#!/usr/bin/env python3
"""audit_identity.py — identity and motion numbers for a 2D frame set, reported and never gated.

audit_frames.py gates what has one repair (feet, slip, key, cut). This script reads what a
viewer calls "it is not the same character", "it pops", "it flickers" or "the legs swapped",
as numbers. Every gate is report-only (gate/1 with `limit: null`, `pass: true`): the limits come
later, from the distribution of real sets.

  identity.frame_to_frame_min   lowest embedding cosine between consecutive frames (DINOv2;
                                SigLIP 2 recorded beside it). A loop includes its wrap. Lower is worse.
  identity.still_min / _mean    each frame against the approved still (--still). Lower is worse.
  identity.front_side           mean cosine over every (frame, side image) pair (--side). Lower is worse.
  motion.loop_seam_ratio        the wrap (last -> first) over the mean ordinary step: one ordinary
                                step reads 1, a pop reads well over 1, a stall well under.
                                `saturated` when frames any distance apart read about one step
                                (`span_ratio` < SEAM_SATURATED): a skipped stretch then reads like
                                an ordinary wrap; a stall still reads.
  motion.flicker_share          inside the silhouette all three frames share, the share of pixels
                                where frame i differs from i-1 and i+1 by more than FLICKER_DE
                                (CIE76) while i-1 and i+1 agree: A -> B -> A. Max over i. Higher is worse.
  motion.limb_swap_frames       frames whose legs trade looks with BOTH neighbours while neither leg
                                moved past the other (A -> B -> A on the leg sides). Legs of two
                                colours are read by colour; legs of one colour by shape: the two leg
                                blobs below the crotch, their shading, their positions. More is worse.

The seam distance is the one sprite-from-video's loop-detection reference defines: every frame
shrunk to fit 96 px, RGB multiplied by alpha, mean absolute RGBA difference in 0..1. Here the
frames are first seated on the reference frame's core (as audit_frames.py measures slip; not
for a `keep` or `centroid` set) and cropped to the union of what they draw, so the thumbnail
holds the character, not the empty canvas. The ratio has no unit. The distance saturates once
two frames barely overlap: in a coarse cycle every pair reads about one step, so a skipped
stretch at the seam reads like an ordinary wrap. The gate keeps its value and says so.

Embeddings need torch, so they are measured by embed.py (beside this script). Every run writes
OUT_DIR/pairs.json with the pairs it needs. Then either:
  --sims SIMS.json  read embed.py's answer (embed.py --pairs pairs.json --out sims.json, run on
                    a torch machine), or
  --embed           measure inline, when embed.py can load its models here.
With neither, or with no engine, the identity gates carry `value: null` and are listed under
`not_measured`: not measured is not a pass.

Examples
  audit_identity.py out/runner_run --still ArtDirection/runner_base.png --out review/identity.json
  audit_identity.py out/runner_run/frames.json --side out/runner_run_side --sims sims.json --out review/identity.json
  audit_identity.py frames/ --no-loop --embed --out review/attack/identity.json

Exit codes: 0 the report was written · 1 usage · 2 nothing to read (no frame; the report, if
written, has `pass: false` and `refused`). `--selftest`: 0 pass, 2 fail.

Requires numpy, Pillow and sprite_ops.py / audit_frames.py beside this script.
"""
import argparse
import importlib.util
import json
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_frames as af  # noqa: E402
import sprite_ops as so  # noqa: E402

TOOL = "audit_identity.py"
MODELS = ("dinov2", "siglip2")   # the gate value is the first; the second is recorded beside it
ANALYSIS_SIZE = 96               # seam thumbnails: the loop-detection distance
VISIBLE = 16                     # alpha above this is drawn (the seam crop)
FLICKER_DE = 10.0                # CIE76 difference that counts as "changed" (a measurement step, not a limit)
LEG_FROM = 0.55                  # the leg band: core rows below this share of its height, from the top
TORSO_BAND = (0.20, 0.55)        # the torso axis: mean x of the core rows in this band
LIMB_MIN_PX = 20                 # a side with fewer leg pixels is not read
LIMB_SEP_DE = 12.0               # the two sides must differ by this much (CIE76) to be told apart
LIMB_CONFIDENT = 0.25            # |assignment margin| below this: the legs overlap, side not read
LEG_TOP = 0.40                   # by shape: the crotch is looked for no higher than this share of the core
LEG_BALANCE = 0.25               # the smaller leg blob holds at least this share of the larger one's pixels
LEG_COVER = 0.85                 # the two leg blobs hold this share of the core below the cut (a hand is the rest)
LEG_MOVE = 0.5                   # a leg moving this share of the legs' spacing in one step may have passed the other
SHADE_SEP_DE = 3.0               # two leg blobs this alike (CIE76) cannot be told apart by their look
SEAM_SATURATED = 1.25            # span_ratio below this: frames any distance apart read about one step
GATES = ("identity.frame_to_frame_min", "identity.still_min", "identity.still_mean", "identity.front_side",
         "motion.loop_seam_ratio", "motion.flicker_share", "motion.limb_swap_frames")


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1, never 2: here 2 means nothing could be read."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


# ------------------------------------------------------------------ helpers ----
def report_gate(name, value, **extra):
    """A gate that is measured and written, never failed."""
    g = {"name": name, "value": value, "limit": None, "pass": True, "report_only": True}
    g.update(extra)
    return g


def lab(rgb_u8):
    """sRGB (uint8, ..., 3) -> CIE L*a*b* (D65), float32."""
    c = rgb_u8.astype(np.float32) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]], np.float32)
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883], np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16.0 / 116.0)
    return np.stack([116.0 * f[..., 1] - 16.0, 500.0 * (f[..., 0] - f[..., 1]),
                     200.0 * (f[..., 1] - f[..., 2])], axis=-1)


def de(a, b):
    return np.sqrt(((a - b) ** 2).sum(axis=-1))


def load_rgba(path):
    with Image.open(path) as im:
        return np.asarray(im.convert("RGBA"))


def image_list(arg):
    """PNG paths of a folder (frames.json order when it holds one, else name order) or one PNG."""
    if os.path.isfile(arg) and arg.lower().endswith(".png"):
        return [arg]
    seq = af.find_sequence(arg)
    return list(seq[1]) if seq else []


def align(frames, ref, grounded):
    """Each frame moved to where its core best overlaps the reference frame's (audit_frames' slip)."""
    cores = [so.core(f[..., 3]) for f in frames]
    out, moves = [], []
    for i, f in enumerate(frames):
        dx, dy = (0, 0) if i == ref else so.slip(cores[ref], cores[i], grounded)
        dx, dy = int(dx), int(dy)
        out.append(so.shifted(f, dy, dx) if (dx or dy) else f)
        moves.append([dx, dy])
    return out, moves


def thumbs(frames):
    """loop-detection's features on one shared crop: 96 px, RGB premultiplied, RGBA in 0..1."""
    vis = np.zeros(frames[0].shape[:2], bool)
    for f in frames:
        vis |= f[..., 3] > VISIBLE
    ys, xs = np.nonzero(vis)
    if not len(ys):
        return None
    h, w = vis.shape
    y0, y1, x0, x1 = max(0, ys.min() - 2), min(h, ys.max() + 3), max(0, xs.min() - 2), min(w, xs.max() + 3)
    feats = []
    for f in frames:
        t = Image.fromarray(np.ascontiguousarray(f[y0:y1, x0:x1]), "RGBA")
        t.thumbnail((ANALYSIS_SIZE, ANALYSIS_SIZE))
        a = np.asarray(t, dtype=np.float32) / 255.0
        feats.append(np.concatenate([a[..., :3] * a[..., 3:4], a[..., 3:4]], axis=-1).reshape(-1))
    return np.stack(feats)


def neighbours(i, n, loop):
    if loop:
        return (i - 1) % n, (i + 1) % n
    return (i - 1, i + 1) if 0 < i < n - 1 else None


# ------------------------------------------------------------------ motion ----
def seam_ratio(frames, loop, cores=None):
    """(gate value or None, extras, why). Beside the ratio: `span_ratio`, the farthest the frames get
    from each other (the median distance at the gap of 2..n/2 frames where it is largest, pairs that
    do not cross the seam; a median, so one odd frame does not lift it), in ordinary steps;
    `saturated` when that is below SEAM_SATURATED, so a skipped stretch at the seam cannot read above
    about one step (the frames barely overlap, or the cycle repeats within itself, as legs of one
    colour do every half cycle); `overlap_median`, the median IoU of consecutive frames' cores, for
    context: a small part that moves far saturates the distance while the body keeps it high."""
    n = len(frames)
    if not loop:
        return None, {}, "not a loop (--no-loop, or the sidecar's loop is false)"
    if n < 3:
        return None, {}, f"{n} frame(s): a seam needs at least 3"
    F = thumbs(frames)
    if F is None:
        return None, {}, "no frame draws anything"
    steps = np.abs(F[1:] - F[:-1]).mean(axis=1)
    mean = float(steps.mean())
    wrap = float(np.abs(F[-1] - F[0]).mean())
    if mean <= 0:
        return None, {}, "every ordinary step is zero (the frames are identical)"
    gaps = [float(np.median(np.abs(F[k:] - F[:-k]).mean(axis=1))) for k in range(2, n // 2 + 1)]
    span = round(max(gaps) / mean, 4) if gaps else None
    extra = {"wrap": round(wrap, 6), "mean_step": round(mean, 6),
             "step_max_ratio": round(float(steps.max()) / mean, 4),
             "span_ratio": span, "saturated": None if span is None else bool(span < SEAM_SATURATED)}
    if cores is not None:
        ious = [float((a & b).sum()) / max(1, int((a | b).sum())) for a, b in zip(cores[:-1], cores[1:])]
        extra["overlap_median"] = round(float(np.median(ious)), 4)
    return round(wrap / mean, 4), extra, ""


def flicker(frames, labs, cores, loop):
    """(max share, frame index, per-frame shares) of A -> B -> A pixels inside the stable silhouette."""
    n = len(frames)
    if n < 3:
        return None, None, [], f"{n} frame(s): flicker needs at least 3"
    shares = []
    for i in range(n):
        nb = neighbours(i, n, loop)
        if nb is None:
            shares.append(None)
            continue
        p, q = nb
        stable = cores[p] & cores[i] & cores[q]
        k = int(stable.sum())
        if not k:
            shares.append(None)
            continue
        flick = (stable & (de(labs[i], labs[p]) > FLICKER_DE) & (de(labs[i], labs[q]) > FLICKER_DE)
                 & (de(labs[p], labs[q]) <= FLICKER_DE))
        shares.append(round(float(flick.sum()) / k, 6))
    read = [(s, i) for i, s in enumerate(shares) if s is not None]
    if not read:
        return None, None, shares, "no three frames share a silhouette"
    s, i = max(read, key=lambda t: (t[0], -t[1]))
    return s, i, shares, ""


def leg_sides(core, labimg):
    """(left signature, right signature) — the median L*a*b* of each half of the leg band, split at
    the torso's axis — or None when a half holds too few pixels."""
    ys = np.nonzero(core.any(axis=1))[0]
    if not len(ys):
        return None
    top, h = int(ys.min()), int(ys.max() - ys.min() + 1)
    t0, t1 = top + int(TORSO_BAND[0] * h), top + max(int(TORSO_BAND[1] * h), int(TORSO_BAND[0] * h) + 1)
    tx = np.nonzero(core[t0:t1])[1]
    if not len(tx):
        return None
    axis = float(tx.mean())
    band = np.zeros_like(core)
    band[top + int(LEG_FROM * h):] = True
    cols = np.arange(core.shape[1])[None, :]
    left, right = core & band & (cols < axis), core & band & (cols >= axis)
    if left.sum() < LIMB_MIN_PX or right.sum() < LIMB_MIN_PX:
        return None
    return np.median(labimg[left], axis=0), np.median(labimg[right], axis=0)


def limb_swaps(labs, cores, loop):
    """(swap frame indices, per-frame states, reference, separation, why). The reference is the frame
    whose two sides differ most; each frame is +1 (sides as the reference), -1 (crossed) or 0 (not
    read: the legs overlap); a swap is a read frame whose state is the opposite of both neighbours'."""
    n = len(labs)
    if n < 3:
        return None, [], None, None, f"{n} frame(s): a swap needs two neighbours"
    sides = [leg_sides(c, lb) for c, lb in zip(cores, labs)]
    read = [(float(de(s[0], s[1])), i) for i, s in enumerate(sides) if s is not None]
    if not read:
        return None, [], None, None, "no frame has a leg band on both sides of the torso"
    sep, ref = max(read, key=lambda t: (t[0], -t[1]))
    if sep < LIMB_SEP_DE:
        return None, [], ref, round(sep, 2), (f"the two leg sides read one colour (CIE76 {sep:.1f} < "
                                              f"{LIMB_SEP_DE:g}): a swap cannot be told by colour")
    rl, rr = sides[ref]
    states = []
    for s in sides:
        if s is None:
            states.append(0)
            continue
        straight = float(de(s[0], rl) + de(s[1], rr))
        crossed = float(de(s[0], rr) + de(s[1], rl))
        m = (crossed - straight) / (2.0 * sep)
        states.append(1 if m >= LIMB_CONFIDENT else (-1 if m <= -LIMB_CONFIDENT else 0))
    swaps = []
    for i in range(n):
        nb = neighbours(i, n, loop)
        if nb and states[i] and states[nb[0]] == states[nb[1]] == -states[i]:
            swaps.append(i)
    return swaps, states, ref, round(sep, 2), ""


def checked_frames(n, loop, read):
    """How many frames could be checked: `read(i, j)` says whether frames i and j were compared."""
    return sum(1 for i in range(n) if (nb := neighbours(i, n, loop)) and read(nb[0], i) and read(i, nb[1]))


def leg_blobs(core):
    """(cut row, left mask, right mask): the two legs as the two blobs of the core below the crotch,
    or None when the legs touch. Rows are added from the feet up (components merge as they grow); the
    cut is the highest row at which the two largest blobs are balanced (LEG_BALANCE) and hold most of
    what lies below (LEG_COVER), taken before those two blobs meet."""
    ys = np.nonzero(core.any(axis=1))[0]
    if not len(ys):
        return None
    top, bot = int(ys.min()), int(ys.max())
    stop = top + int(LEG_TOP * (bot - top + 1))
    parent, area, roots = [], [], set()

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    below, best = [], None
    for y in range(bot, stop - 1, -1):
        d = np.diff(np.concatenate(([0], core[y].astype(np.int8), [0])))
        row = []
        for s, e in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]):
            k = len(parent)
            parent.append(k)
            area.append(int(e - s))
            roots.add(k)
            for ps, pe, pk in below:
                if s <= pe and ps <= e:                    # the runs touch, diagonals included
                    a, b = find(k), find(pk)
                    if a != b:
                        parent[b] = a
                        area[a] += area[b]
                        roots.discard(b)
            row.append((s, e, k))
        below = row
        if best and find(best[1]) == find(best[2]):
            break                                          # the two legs met: the crotch
        if len(roots) < 2:
            continue
        r1, r2 = sorted(roots, key=lambda r: -area[r])[:2]
        if (area[r2] >= max(LIMB_MIN_PX, LEG_BALANCE * area[r1])
                and area[r1] + area[r2] >= LEG_COVER * sum(area[r] for r in roots)):
            best = (y, r1, r2)
    if best is None:
        return None
    y = best[0]
    lab_, _ = so.label(core[y:])
    sizes = np.bincount(lab_.ravel())
    sizes[0] = 0
    k1, k2 = np.argsort(-sizes)[:2]
    blobs = []
    for k in (k1, k2):
        m = np.zeros_like(core)
        m[y:] = lab_ == k
        blobs.append((float(np.nonzero(m)[1].mean()), m))
    blobs.sort(key=lambda t: t[0])
    return y, blobs[0][1], blobs[1][1]


def limb_swaps_shape(labs, cores, loop):
    """The read for legs of one colour. (swap frame indices or None, detail, why).

    Each frame's legs are its two leg blobs (leg_blobs), left and right by their centre x, each with
    the median L*a*b* of its pixels: on legs of one colour that is the shading (the far leg in shadow).
    Two consecutive frames are compared only when both have their legs apart, each leg moved less than
    LEG_MOVE of the legs' spacing (so neither can have passed the other), and the two legs differ by
    SHADE_SEP_DE in both. The link is 1 when each side keeps its look, -1 when the sides trade looks
    (by the same margin as the colour read), 0 when not compared. A swap is a frame whose links to
    both neighbours are -1: A -> B -> A while the legs stayed where they were."""
    n = len(labs)
    legs = []
    for c, lb in zip(cores, labs):
        b = leg_blobs(c)
        if b is None:
            legs.append(None)
            continue
        _, ml, mr = b
        xs = [float(np.nonzero(m)[1].mean()) for m in (ml, mr)]
        sig = [np.median(lb[m], axis=0) for m in (ml, mr)]
        legs.append((xs, sig, float(de(sig[0], sig[1]))))
    pairs = [(i, i + 1) for i in range(n - 1)] + ([(n - 1, 0)] if loop and n > 2 else [])
    links = {}
    for p, q in pairs:
        a, b = legs[p], legs[q]
        state = 0
        if a and b and min(a[2], b[2]) >= SHADE_SEP_DE:
            spacing = min(a[0][1] - a[0][0], b[0][1] - b[0][0])
            moved = max(abs(a[0][0] - b[0][0]), abs(a[0][1] - b[0][1]))
            if moved < LEG_MOVE * spacing:
                (sl, sr), (tl, tr) = a[1], b[1]
                straight = float(de(sl, tl) + de(sr, tr))
                crossed = float(de(sl, tr) + de(sr, tl))
                m = (straight - crossed) / (a[2] + b[2])
                state = -1 if m >= LIMB_CONFIDENT else (1 if m <= -LIMB_CONFIDENT else 0)
        links[(p, q)] = state
    detail = {"apart": [x is not None for x in legs],
              "contrast_de": [None if x is None else round(x[2], 2) for x in legs],
              "links": [links[pq] for pq in pairs]}
    checked = checked_frames(n, loop, lambda i, j: links.get((i, j), 0) != 0)
    detail["checked"] = checked
    apart = [x for x in legs if x is not None]
    if not apart:
        return None, detail, "the legs touch or overlap in every frame: no two leg blobs below the crotch"
    if max(x[2] for x in apart) < SHADE_SEP_DE:
        return None, detail, (f"the two legs look alike in every frame where they are apart (CIE76 < "
                              f"{SHADE_SEP_DE:g}): neither colour nor shading tells them apart")
    if not checked:
        return None, detail, ("no frame has both neighbours compared (the legs touch, look alike, or "
                              f"move more than {LEG_MOVE:g} of their spacing in a step)")
    swaps = [i for i in range(n) if (nb := neighbours(i, n, loop))
             and links.get((nb[0], i)) == -1 and links.get((i, nb[1])) == -1]
    return swaps, detail, ""


def read_limbs(labs, cores, loop):
    """(swap frames or None, detail, why): by colour when the legs are two colours, else by shape.
    The colour read splits the whole lower body at the torso's axis, so an arm, a belly patch or the
    light can make its halves differ: where the leg blobs are apart and differ by less than
    LIMB_SEP_DE in every frame, the halves were not reading the legs and the shape read is used."""
    n = len(labs)
    swaps, states, ref, sep, why = limb_swaps(labs, cores, loop)
    detail = {"reference": ref, "separation_de": sep, "states": states}
    if n < 3:
        return None, detail, why
    s2, shape, why2 = limb_swaps_shape(labs, cores, loop)
    blob_sep = max((x for x in shape["contrast_de"] if x is not None), default=None)
    if swaps is not None:
        checked = checked_frames(n, loop, lambda i, j: bool(states[i]) and bool(states[j]))
        if not checked:
            why = "no frame and both its neighbours read by colour (the legs overlap)"
        elif blob_sep is not None and blob_sep < LIMB_SEP_DE:
            why = (f"the lower body's halves differ (CIE76 {sep:g}) but the legs, where apart, by at most "
                   f"{blob_sep:g}: the halves read an arm, a patch or the light, not the legs")
        else:
            detail.update(method="colour", checked=checked)
            return swaps, detail, ""
    detail.update(shape)
    detail["method"] = "shape"
    if s2 is None:
        return None, detail, f"by colour: {why}; by shape: {why2}"
    return s2, detail, ""


# ---------------------------------------------------------------- identity ----
def rel(path, folder):
    try:
        return os.path.relpath(os.path.abspath(path), folder).replace(os.sep, "/")
    except ValueError:           # another drive
        return os.path.abspath(path)


def build_pairs(files, still, side, loop):
    """{gate: [(id, a, b), ...]} for every identity gate whose inputs were given."""
    n, pairs = len(files), {}
    f2f = [(f"f2f/{i}-{i + 1}", files[i], files[i + 1]) for i in range(n - 1)]
    if loop and n > 2:
        f2f.append((f"f2f/{n - 1}-0", files[-1], files[0]))
    if f2f:
        pairs["identity.frame_to_frame_min"] = f2f
    if still:
        pairs["identity.still_min"] = [(f"still/{i}", f, still) for i, f in enumerate(files)]
    if side:
        pairs["identity.front_side"] = [(f"side/{i}x{j}", f, s) for i, f in enumerate(files)
                                        for j, s in enumerate(side)]
    return pairs


def load_embed():
    """embed.py beside this script, or None. The selftest replaces this loader."""
    path = os.path.join(HERE, "embed.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("embed", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EMBED_LOADER = load_embed


def sims_inline(pairs, device):
    """({id: {model: cos}}, engine, why) measured here by embed.py's similarity()."""
    try:
        mod = EMBED_LOADER()
    except Exception as e:          # an engine that cannot even import is not measured
        return {}, None, f"embed.py did not load: {type(e).__name__}: {e}"
    if mod is None:
        return {}, None, "embed.py is not beside this script"
    ok, why = mod.available()
    if not ok:
        return {}, None, f"no embedding engine here ({why}): run embed.py on a torch machine, then --sims"
    if hasattr(mod, "pick_device"):
        try:
            device = mod.pick_device(device)       # record the device torch actually uses
        except Exception as e:
            return {}, None, f"the embedding engine did not start: {type(e).__name__}: {e}"[:400]
    flat = [p for ps in pairs.values() for p in ps]
    unique = sorted({os.path.abspath(x) for _, a, b in flat for x in (a, b)})
    at = {x: k for k, x in enumerate(unique)}
    out = {pid: {} for pid, _, _ in flat}
    errors = []
    for model in MODELS:          # each image embedded once; a pair's cosine is the dot of two unit vectors
        try:
            e = np.asarray(mod.embed(unique, model, device), np.float64)
            vals = [float(e[at[os.path.abspath(a)]] @ e[at[os.path.abspath(b)]]) for _, a, b in flat]
        except Exception as ex:
            errors.append(f"{model}: {type(ex).__name__}: {ex}"[:400])
            vals = [None] * len(flat)
        for (pid, _, _), v in zip(flat, vals):
            out[pid][model] = v
    engine = {"route": "inline", "device": device}
    if hasattr(mod, "engine_info"):
        try:
            engine.update(mod.engine_info(list(MODELS), device))
        except Exception:
            pass
    if errors:
        engine["errors"] = errors
        first = [x for x in errors if x.startswith(MODELS[0] + ":")]
        if first:                  # the gate model failed: say so, not "a pair has no value"
            return out, engine, f"the embedding engine failed: {first[0]}"
    return out, engine, ""


def sims_file(path):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    sims = doc.get("sims") if isinstance(doc, dict) else None
    if not isinstance(sims, dict):
        raise ValueError(f"{path} has no `sims` object (embed.py --pairs ... --out writes one)")
    if doc.get("engine") is None:     # embed.py ran but measured nothing: every value is null
        raise LookupError(f"{path} has engine null: embed.py measured nothing ({doc.get('reason') or 'no reason given'})")
    return sims, {"route": "sims", "file": os.path.abspath(path), "engine": doc.get("engine")}


def stat(pairs, sims, model, how):
    """(value, pair id) of min / mean over the pairs, or (None, why) when any pair lacks a value."""
    vals = []
    for pid, _, _ in pairs:
        v = (sims.get(pid) or {}).get(model)
        if not isinstance(v, (int, float)) or not math.isfinite(v):
            return None, pid
        vals.append((float(v), pid))
    if how == "min":
        v, pid = min(vals, key=lambda t: t[0])
        return round(v, 6), pid
    return round(sum(v for v, _ in vals) / len(vals), 6), None


def identity_gates(pairs, sims, route_why):
    """(gates, not_measured) for the four identity gates."""
    gates, missing = [], []
    plan = [("identity.frame_to_frame_min", "identity.frame_to_frame_min", "min", "fewer than 2 frames"),
            ("identity.still_min", "identity.still_min", "min", "no --still"),
            ("identity.still_mean", "identity.still_min", "mean", "no --still"),
            ("identity.front_side", "identity.front_side", "mean", "no --side")]
    for name, key, how, absent in plan:
        ps = pairs.get(key)
        if not ps:
            gates.append(report_gate(name, None))
            missing.append({"name": name, "why": absent})
            continue
        if route_why:
            gates.append(report_gate(name, None, pairs=len(ps)))
            missing.append({"name": name, "why": route_why})
            continue
        v, at = stat(ps, sims, MODELS[0], how)
        if v is None:
            gates.append(report_gate(name, None, pairs=len(ps)))
            missing.append({"name": name, "why": f"no {MODELS[0]} value for pair {at} (re-run embed.py on "
                                                 f"this pairs.json)"})
            continue
        extra = {"pairs": len(ps)}
        v2, at2 = stat(ps, sims, MODELS[1], how)
        extra[MODELS[1]] = v2
        if how == "min":
            extra["at"] = at
            if v2 is not None:
                extra[MODELS[1] + "_at"] = at2      # SigLIP 2 can name another pair (a colour change)
        gates.append(report_gate(name, v, **extra))
    return gates, missing


# ---------------------------------------------------------------------- run ----
def run(argv):
    p = UsageParser(prog=TOOL, description=__doc__.split("\n")[0])
    p.add_argument("frames", help="a folder of PNG frames (frames.json order when it holds one) or a frames.json")
    p.add_argument("--still", metavar="PNG", help="the approved still: identity.still_min / still_mean")
    p.add_argument("--side", metavar="PATH", help="the side view, a folder of frames or one PNG: identity.front_side")
    lp = p.add_mutually_exclusive_group()
    lp.add_argument("--loop", dest="loop", action="store_true", default=None,
                    help="the set loops (default: the sidecar's loop, else a loop)")
    lp.add_argument("--no-loop", dest="loop", action="store_false", help="the set is a one-shot: no seam, no wrap")
    em = p.add_mutually_exclusive_group()
    em.add_argument("--sims", metavar="JSON", help="embed.py's sims.json for the pairs.json this run writes")
    em.add_argument("--embed", action="store_true", help="measure the embeddings here with embed.py (needs torch)")
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"],
                   help="--embed: the torch device (default auto: cuda, then mps, then cpu)")
    p.add_argument("--out", required=True, metavar="JSON", help="the gate/1 report; pairs.json goes beside it")
    a = p.parse_args(argv)

    out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(out_dir, exist_ok=True)
    seq = af.find_sequence(a.frames)
    files = list(seq[1]) if seq else []
    doc = seq[2] if seq else None
    if not files:
        why = f"no frames in {a.frames}"
        side = a.frames if a.frames.endswith(".json") else os.path.join(a.frames, "frames.json")
        if os.path.isfile(side):
            why += " (its frames.json names files that are not beside it: renamed or moved?)"
        rep = {"schema": "gate/1", "tool": TOOL, "pass": False, "gates": [], "refused": why}
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=2)
        print(f"{TOOL}: nothing to read in {a.frames}: no report gates, this is not a pass", file=sys.stderr)
        return 2, rep
    for path, what in ((a.still, "--still"),):
        if path and not os.path.isfile(path):
            print(f"{TOOL}: error: {what} {path} is not a file", file=sys.stderr)
            return 1, None
    side = image_list(a.side) if a.side else []
    if a.side and not side:
        print(f"{TOOL}: error: --side {a.side} holds no PNG", file=sys.stderr)
        return 1, None
    loop = a.loop if a.loop is not None else bool((doc or {}).get("loop", True))
    mode = af.sidecar_mode(doc)
    ref = af.sidecar_ref(doc)
    ref = ref if 0 <= ref < len(files) else 0

    # ---- motion
    frames = [load_rgba(f) for f in files]
    gates, missing, detail, seam_warning = [], [], {}, None
    if len({f.shape for f in frames}) > 1:
        why = "the frames are not one canvas size"
        for name in GATES[4:]:
            gates.append(report_gate(name, None))
            missing.append({"name": name, "why": why})
    else:
        seat = mode not in ("keep", "centroid")
        frames, moves = align(frames, ref, mode == "ground") if seat else (frames, [[0, 0]] * len(frames))
        detail["seated"] = {"on_frame": ref if seat else None, "moves_px": moves}
        cores = [so.core(f[..., 3]) for f in frames]
        labs = [lab(f[..., :3]) for f in frames]
        v, extra, why = seam_ratio(frames, loop, cores)
        gates.append(report_gate("motion.loop_seam_ratio", v, **extra))
        if why:
            missing.append({"name": "motion.loop_seam_ratio", "why": why})
        elif extra.get("saturated"):
            seam_warning = (f"motion.loop_seam_ratio is saturated: frames any distance apart read at most "
                            f"{extra['span_ratio']:g} ordinary steps (< {SEAM_SATURATED:g}), so a skipped "
                            f"stretch at the seam reads like an ordinary wrap and a value near 1 does not say "
                            f"the loop closes; a stall still reads well under 1. Check the seam on the onion skin")
        s, at, shares, why = flicker(frames, labs, cores, loop)
        gates.append(report_gate("motion.flicker_share", s, **({"frame": at} if at is not None else {})))
        detail["flicker_share"] = shares
        if why:
            missing.append({"name": "motion.flicker_share", "why": why})
        if all(f[..., 3].min() == 255 for f in frames):   # no background cut: the "core" is the canvas
            swaps, ldetail, why = None, {"reference": None, "separation_de": None, "states": []}, (
                "the frames are opaque: no silhouette to split into legs (cut the background first)")
        else:
            swaps, ldetail, why = read_limbs(labs, cores, loop)
        gates.append(report_gate("motion.limb_swap_frames", None if swaps is None else len(swaps),
                                 **({"frames": swaps, "method": ldetail["method"], "checked": ldetail["checked"]}
                                    if swaps is not None else {})))
        detail["limbs"] = ldetail
        if why:
            missing.append({"name": "motion.limb_swap_frames", "why": why})

    # ---- identity: pairs.json always; values from --sims, --embed, or not measured
    pairs = build_pairs(files, a.still, side, loop)
    pairs_path = os.path.join(out_dir, "pairs.json")
    with open(pairs_path, "w", encoding="utf-8") as fh:
        json.dump({"pairs": [{"id": pid, "a": rel(x, out_dir), "b": rel(y, out_dir)}
                             for ps in pairs.values() for pid, x, y in ps]}, fh, indent=2)
    warnings, sims, engine, route_why = [], {}, None, ""
    if not pairs:
        route_why = "no pairs"
    elif a.sims:
        try:
            sims, engine = sims_file(a.sims)
        except LookupError as e:
            route_why = str(e)
        except (OSError, ValueError) as e:
            print(f"{TOOL}: error: --sims: {e}", file=sys.stderr)
            return 1, None
    elif a.embed:
        sims, engine, route_why = sims_inline(pairs, a.device)
    else:
        route_why = (f"no --sims and no --embed: run embed.py --pairs {pairs_path} --out sims.json on a "
                     f"torch machine, then --sims sims.json")
    if route_why and pairs and (a.embed or a.sims):
        warnings.append(f"embeddings not measured: {route_why}")
    if seam_warning:
        warnings.append(seam_warning)
    ig, im = identity_gates(pairs, sims, route_why)
    gates = ig + gates
    missing = im + missing

    rep = {"schema": "gate/1", "tool": TOOL, "pass": True, "gates": gates,
           "not_measured": missing, "report_only": True,
           "sequence": seq[0], "frames": [os.path.basename(f) for f in files], "loop": loop, "mode": mode,
           "pairs_file": pairs_path, "embedding": engine, "detail": detail}
    if warnings:
        rep["warnings"] = warnings
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2)
    for g in gates:
        val = "not measured" if g["value"] is None else g["value"]
        print(f"{g['name']:30s} {val}")
    print(f"wrote {a.out} (report-only: nothing is gated) and {pairs_path}")
    return 0, rep


def main(argv=None):
    code, _ = run(sys.argv[1:] if argv is None else argv)
    return code


# ----------------------------------------------------------------- selftest ----
def selftest():
    """Synthetic courier-run sprites in a temp dir; each metric reads its planted fault and not the clean
    set. One JSON line; exit 0 pass, 2 fail."""
    import contextlib
    import io
    import tempfile
    global EMBED_LOADER

    checks, failed = [], []

    def check(name, ok):
        checks.append(name)
        if not ok:
            failed.append(name)

    def go(*args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                code, rep = run([str(x) for x in args])
            except SystemExit as e:
                code, rep = e.code, None
        return code, rep, buf.getvalue()

    def gate(rep, name):
        return next(g for g in rep["gates"] if g["name"] == name)

    RED, GREEN, TORSO, HEAD, PATCH = (200, 60, 50), (50, 160, 70), (40, 90, 210), (235, 190, 150), (250, 220, 40)
    NEAR, FAR = (185, 125, 78), (160, 106, 64)    # one leg colour, lit and in shadow: CIE76 8.4

    def runner(phase, swap=False, patch=False, cross=False, dx=0, shade=False, joined=False, twirl=None):
        """A 96x128 courier runner: head, torso, a red leg and a green leg. `phase` swings the legs;
        `cross` walks them across each other (a side view, the near leg drawn last). `shade`: legs of
        one colour, the near one lit and the far one in shadow, the near one drawn last; `joined`: the
        legs side by side with no gap; `twirl`: a baton circling the torso at that angle (turns)."""
        a = np.zeros((128, 96, 4), np.uint8)
        a[8:22, 41 + dx:55 + dx] = HEAD + (255,)
        a[22:76, 33 + dx:63 + dx] = TORSO + (255,)
        s = math.sin(2 * math.pi * phase)
        if joined:
            xr, xg = 36, 48
        elif cross:
            xr, xg = int(round(42 + 10 * s)), int(round(42 - 10 * s))
        else:                    # a triangle swing, 2 px a step: every ordinary step is the same size
            k = int(round(phase * n)) % n
            off = 2 * min(k, n - k)
            xr, xg = 26 + off, 58 - off
        two = (NEAR, FAR) if shade else (RED, GREEN)
        cr, cg = two[::-1] if swap else two
        near_last = shade or (cross and math.cos(2 * math.pi * phase) >= 0)
        order = [(xg, cg), (xr, cr)] if near_last else [(xr, cr), (xg, cg)]
        for x, col in order:
            a[76:120, x + dx:x + 12 + dx] = col + (255,)
        if patch:
            a[40:52, 42 + dx:54 + dx] = PATCH + (255,)
        if twirl is not None:    # 30 px from the torso's middle: 10 steps a turn are 18.5 px apart, the baton 12
            bx = int(round(48 + 30 * math.cos(2 * math.pi * twirl))) + dx
            by = int(round(50 + 30 * math.sin(2 * math.pi * twirl)))
            a[by - 6:by + 6, bx - 6:bx + 6] = PATCH + (255,)
        return a

    def write(d, frames, loop=True):
        os.makedirs(d, exist_ok=True)
        recs = []
        for i, f in enumerate(frames):
            Image.fromarray(f, "RGBA").save(os.path.join(d, f"runner_{i:03d}.png"))
            recs.append({"file": f"runner_{i:03d}.png"})
        doc = {"schema": "frames/1", "tool": "selftest", "canvas": [96, 128], "pivot_norm": [0.5, 8 / 128],
               "key_color": None, "fps_hint": 10.0, "loop": loop,
               "register": {"mode": "ground", "ref": 0, "reference_core_height_px": 112, "foot_margin_px": 8},
               "verdict": {"ok": True, "faults": []}, "frames": recs}
        with open(os.path.join(d, "frames.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        return d

    def has_ok(x):
        if isinstance(x, dict):
            return "ok" in x or any(has_ok(v) for v in x.values())
        return isinstance(x, list) and any(has_ok(v) for v in x)

    n = 8
    with tempfile.TemporaryDirectory() as tmp:
        clean = write(os.path.join(tmp, "clean"), [runner(k / n) for k in range(n)])
        code, rep, out = go(clean, "--out", os.path.join(tmp, "r_clean", "report.json"))
        check("clean run writes a report (0)", code == 0 and rep is not None)
        seam_clean = gate(rep, "motion.loop_seam_ratio")["value"]
        check("clean loop: seam reads about one step", seam_clean is not None and 0.5 <= seam_clean <= 1.5)
        g = gate(rep, "motion.loop_seam_ratio")
        check("a fine cycle is not saturated (span over 1.25 steps), no warning",
              g["saturated"] is False and g["span_ratio"] >= 1.25 and not rep.get("warnings"))
        check("clean loop: flicker 0", gate(rep, "motion.flicker_share")["value"] == 0.0)
        check("clean loop: no limb swap", gate(rep, "motion.limb_swap_frames")["value"] == 0)
        check("every gate is report-only", all(g["limit"] is None and g["pass"] is True and "margin" not in g
                                               for g in rep["gates"]) and rep["pass"] is True)
        check("no `ok` anywhere", not has_ok(rep))
        check("no engine route: identity gates null and listed",
              gate(rep, "identity.frame_to_frame_min")["value"] is None
              and {m["name"] for m in rep["not_measured"]} >= {"identity.frame_to_frame_min", "identity.still_min"})
        check("pairs.json written: 8 consecutive pairs with the wrap",
              len(json.load(open(os.path.join(tmp, "r_clean", "pairs.json")))["pairs"]) == n)

        # seam: the last frame jumps to the opposite pose
        popped = write(os.path.join(tmp, "seam"), [runner(k / n) for k in range(n - 1)] + [runner(0.5, dx=6)])
        _, rep, _ = go(popped, "--out", os.path.join(tmp, "r_seam", "report.json"))
        v = gate(rep, "motion.loop_seam_ratio")["value"]
        check("a popped wrap reads clearly worse (> 2x the clean)", v is not None and v > 2 * seam_clean and v > 2.0)
        # a coarse cycle: a baton 18.5 px a step, 12 px wide: consecutive frames do not overlap there,
        # so every pair reads about one step. Three frames skipped at the wrap still read about 1.
        coarse = write(os.path.join(tmp, "coarse"), [runner(0.0, twirl=k / 10) for k in range(7)])
        _, rep, _ = go(coarse, "--out", os.path.join(tmp, "r_coarse", "report.json"))
        g = gate(rep, "motion.loop_seam_ratio")
        check("coarse cycle with 3 of 10 frames skipped at the wrap: the ratio still reads about 1",
              g["value"] is not None and 0.75 <= g["value"] <= 1.3)
        check("...and the gate says it is saturated, keeps its value and warns",
              g["saturated"] is True and g["span_ratio"] < 1.25 and g["value"] is not None
              and not any(m["name"] == "motion.loop_seam_ratio" for m in rep["not_measured"])
              and any("saturated" in w for w in rep.get("warnings", [])))
        popc = write(os.path.join(tmp, "coarse_pop"), [runner(0.0, twirl=k / 10) for k in range(9)]
                     + [runner(0.5, twirl=0.9)])
        _, rep, _ = go(popc, "--out", os.path.join(tmp, "r_coarse_pop", "report.json"))
        g = gate(rep, "motion.loop_seam_ratio")
        check("saturated, a pop larger than any step still reads well over 1",
              g["saturated"] is True and g["value"] is not None and g["value"] > 2.0)
        _, rep, _ = go(popped, "--no-loop", "--out", os.path.join(tmp, "r_seam1", "report.json"))
        check("--no-loop: no seam, listed as not measured",
              gate(rep, "motion.loop_seam_ratio")["value"] is None
              and any(m["name"] == "motion.loop_seam_ratio" for m in rep["not_measured"]))

        # flicker: one frame's torso flashes a colour its neighbours do not have
        flash = write(os.path.join(tmp, "flash"), [runner(k / n, patch=(k == 3)) for k in range(n)])
        _, rep, _ = go(flash, "--out", os.path.join(tmp, "r_flash", "report.json"))
        g = gate(rep, "motion.flicker_share")
        check("a one-frame flash reads at that frame", g["value"] is not None and g["value"] > 0.02 and g["frame"] == 3)

        # limb swap: the two legs trade colours for one frame
        swapped = write(os.path.join(tmp, "swap"), [runner(k / n, swap=(k == 4)) for k in range(n)])
        _, rep, _ = go(swapped, "--out", os.path.join(tmp, "r_swap", "report.json"))
        g = gate(rep, "motion.limb_swap_frames")
        check("a one-frame leg colour swap is found at that frame", g["value"] == 1 and g["frames"] == [4])
        crossing = write(os.path.join(tmp, "cross"), [runner(k / n, cross=True) for k in range(n)])
        _, rep, _ = go(crossing, "--out", os.path.join(tmp, "r_cross", "report.json"))
        check("legs that cross over half a cycle are not a swap",
              gate(rep, "motion.limb_swap_frames")["value"] == 0
              and -1 in rep["detail"]["limbs"]["states"] and 1 in rep["detail"]["limbs"]["states"])

        def mono(k):
            f = runner(k / n)
            f[76:120][f[76:120, ..., 3] > 0] = TORSO + (255,)
            return f
        same = write(os.path.join(tmp, "same"), [mono(k) for k in range(n)])
        _, rep, _ = go(same, "--out", os.path.join(tmp, "r_same", "report.json"))
        check("legs of one colour and one shade: swap not measured, not 0, said why",
              gate(rep, "motion.limb_swap_frames")["value"] is None
              and "look alike" in {m["name"]: m["why"] for m in rep["not_measured"]}["motion.limb_swap_frames"])
        opaque = write(os.path.join(tmp, "opaque"), [np.dstack([runner(k / n)[..., :3], np.full((128, 96), 255, np.uint8)])
                                                     for k in range(n)])
        _, rep, _ = go(opaque, "--out", os.path.join(tmp, "r_opaque", "report.json"))
        check("opaque frames: swap not measured, said why",
              gate(rep, "motion.limb_swap_frames")["value"] is None
              and "opaque" in {m["name"]: m["why"] for m in rep["not_measured"]}["motion.limb_swap_frames"])

        # limb swap by shape: legs of one colour, told apart by their shading and their place
        def limbs(name, frames):
            _, r, _ = go(write(os.path.join(tmp, name), frames), "--out", os.path.join(tmp, "r_" + name, "report.json"))
            return gate(r, "motion.limb_swap_frames"), r["detail"]["limbs"], \
                {m["name"]: m["why"] for m in r["not_measured"]}.get("motion.limb_swap_frames", "")
        g, d, _ = limbs("shade", [runner(k / n, shade=True) for k in range(n)])
        check("one colour, legs apart: read by shape, every frame checked, no swap",
              g["value"] == 0 and g["method"] == "shape" and g["checked"] == n and set(d["links"]) == {1})
        g, d, _ = limbs("shade_swap", [runner(k / n, shade=True, swap=(k == 4)) for k in range(n)])
        check("one colour: a one-frame shading swap is found at that frame",
              g["value"] == 1 and g["frames"] == [4] and d["links"][3] == d["links"][4] == -1)
        g, d, _ = limbs("shade_cross", [runner(k / n, shade=True, cross=True) for k in range(n)])
        check("one colour, legs that cross through a merged frame: not a swap",
              g["value"] == 0 and g["checked"] >= 2 and d["apart"][0] is False and d["apart"][n // 2] is False
              and d["apart"][1] and d["apart"][n // 2 + 1])
        g, d, _ = limbs("shade_cross_swap", [runner(k / n, shade=True, cross=True, swap=(k == 2)) for k in range(n)])
        check("one colour, crossing walk: a swap between two read neighbours is found",
              g["value"] == 1 and g["frames"] == [2])
        g, d, why = limbs("joined", [runner(k / n, shade=True, joined=True) for k in range(n)])
        check("legs that always touch: not measured, not 0, said why",
              g["value"] is None and "touch" in why and not any(d["apart"]))

        # the seat: a frame drawn 5 px to the side is moved back by audit_frames' slip
        base = runner(0.0)
        moved, moves = align([base, runner(0.0, dx=5)], 0, True)
        check("align moves a +5 px frame back by -5", moves[1] == [-5, 0] and np.array_equal(moved[1], base))

        # identity: a still, a side set, fake sims read back
        still = os.path.join(tmp, "runner_base.png")
        Image.fromarray(runner(0.0), "RGBA").save(still)
        side = write(os.path.join(tmp, "side"), [runner(k / 4, cross=True) for k in range(4)])
        out_id = os.path.join(tmp, "r_id", "report.json")
        go(clean, "--still", still, "--side", side, "--out", out_id)
        pairs = json.load(open(os.path.join(tmp, "r_id", "pairs.json")))["pairs"]
        check("pairs.json: 8 f2f + 8 still + 32 side", len(pairs) == 8 + 8 + 32)
        check("pair paths resolve from the pairs file's folder",
              all(os.path.isfile(os.path.join(tmp, "r_id", q["a"])) for q in pairs))
        fake = {}
        for q in pairs:
            d = 0.95
            if q["id"] == "f2f/3-4":
                d = 0.60
            elif q["id"] == "still/6":
                d = 0.70
            elif q["id"].startswith("side/"):
                d = 0.80
            fake[q["id"]] = {"dinov2": d, "siglip2": d - 0.1}
        sims_path = os.path.join(tmp, "sims.json")
        with open(sims_path, "w", encoding="utf-8") as fh:
            json.dump({"engine": {"dinov2": "fake"}, "sims": fake}, fh)
        code, rep, _ = go(clean, "--still", still, "--side", side, "--sims", sims_path, "--out", out_id)
        g = gate(rep, "identity.frame_to_frame_min")
        check("fake sims: frame_to_frame_min is the planted low pair",
              code == 0 and g["value"] == 0.6 and g["at"] == "f2f/3-4" and abs(g["siglip2"] - 0.5) < 1e-9)
        check("fake sims: still_min / still_mean", gate(rep, "identity.still_min")["value"] == 0.7
              and abs(gate(rep, "identity.still_mean")["value"] - (7 * 0.95 + 0.7) / 8) < 1e-6)
        check("fake sims: front_side is the mean over every pair", gate(rep, "identity.front_side")["value"] == 0.8)
        check("fake sims: no identity gate is listed as not measured",
              not any(m["name"].startswith("identity.") for m in rep["not_measured"]))
        measured = rep
        del fake["still/2"]
        with open(sims_path, "w", encoding="utf-8") as fh:
            json.dump({"engine": {"dinov2": "fake"}, "sims": fake}, fh)
        _, rep, _ = go(clean, "--still", still, "--sims", sims_path, "--out", out_id)
        check("a pair missing from sims.json leaves its gate null, not a partial min",
              gate(rep, "identity.still_min")["value"] is None and gate(rep, "identity.frame_to_frame_min")["value"] == 0.6)
        with open(sims_path, "w", encoding="utf-8") as fh:
            json.dump({"engine": None, "sims": {k: {"dinov2": None} for k in fake}, "reason": "no torch"}, fh)
        code, rep, _ = go(clean, "--still", still, "--sims", sims_path, "--out", out_id)
        check("sims.json with engine null: not measured, its reason kept", code == 0
              and gate(rep, "identity.still_min")["value"] is None
              and "no torch" in {m["name"]: m["why"] for m in rep["not_measured"]}["identity.still_min"])

        # --embed: an injected engine, then no engine; neither needs torch
        class Fake:
            @staticmethod
            def available():
                return True, ""

            @staticmethod
            def embed(paths, model, device="auto"):      # unit vectors whose dot is 0.9 (dinov2) / 0.8
                c = 0.9 if model == "dinov2" else 0.8
                return np.array([[1.0, 0.0] if "runner_base" in p else [c, math.sqrt(1 - c * c)] for p in paths])

        class Broken(Fake):
            @staticmethod
            def embed(paths, model, device="auto"):
                raise OSError("cannot download the weights")

        class NoTorch:
            @staticmethod
            def available():
                return False, "torch is not installed"

        saved = EMBED_LOADER
        try:
            EMBED_LOADER = lambda: Fake
            code, rep, _ = go(clean, "--still", still, "--embed", "--out", out_id)
            check("--embed with an engine fills the identity gates", code == 0
                  and gate(rep, "identity.still_mean")["value"] == 0.9 and gate(rep, "identity.still_mean")["siglip2"] == 0.8)
            EMBED_LOADER = lambda: Broken
            code, rep, _ = go(clean, "--still", still, "--embed", "--out", out_id)
            nm = {m["name"]: m["why"] for m in rep["not_measured"]}
            check("--embed with an engine that fails: null, the engine's error as the reason", code == 0
                  and gate(rep, "identity.still_min")["value"] is None and "cannot download" in nm["identity.still_min"]
                  and rep.get("warnings"))
            EMBED_LOADER = lambda: NoTorch
            code, rep, _ = go(clean, "--still", still, "--embed", "--out", out_id)
            nm = {m["name"]: m["why"] for m in rep["not_measured"]}
            check("--embed without an engine: null, not measured, warned", code == 0
                  and gate(rep, "identity.still_min")["value"] is None and "torch is not installed" in nm["identity.still_min"]
                  and rep.get("warnings"))
            EMBED_LOADER = lambda: None
            _, rep, _ = go(clean, "--still", still, "--embed", "--out", out_id)
            check("--embed without embed.py: not measured", "embed.py" in
                  {m["name"]: m["why"] for m in rep["not_measured"]}["identity.still_min"])
            sample = rep
        finally:
            EMBED_LOADER = saved

        # small sets and usage
        one = write(os.path.join(tmp, "one"), [runner(0.0)])
        code, rep, _ = go(one, "--out", os.path.join(tmp, "r_one", "report.json"))
        check("one frame: a report of nulls, still pass", code == 0 and rep["pass"] is True
              and all(g["value"] is None for g in rep["gates"]))
        os.makedirs(os.path.join(tmp, "empty"))
        code, rep, _ = go(os.path.join(tmp, "empty"), "--out", os.path.join(tmp, "r_empty", "report.json"))
        check("no frames: exit 2, refused, pass false", code == 2 and rep["pass"] is False and rep["refused"])
        check("an unknown flag exits 1", go(clean, "--out", out_id, "--bogus")[0] == 1)
        check("--sims and --embed together exit 1", go(clean, "--out", out_id, "--embed", "--sims", sims_path)[0] == 1)
        check("--out is required (1)", go(clean)[0] == 1)

        # the hand-off: tools/check-contracts.py validates it against schemas/gate-1.json
        dest_dir = os.environ.get("UNITY_DEV_CONTRACT_OUT") or os.path.join(tempfile.gettempdir(),
                                                                           "unity-dev-contract-out")
        os.makedirs(dest_dir, exist_ok=True)
        for case, doc in (("measured", measured), ("not_measured", sample)):
            dest = os.path.join(dest_dir, f"audit_identity__{case}.gate.json")
            with open(dest, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2)
            print(f"selftest-output: {dest}")

    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": len(checks), "failed": failed}))
    return 0 if not failed else 2


if __name__ == "__main__":
    if sys.argv[1:] in (["--selftest"], ["selftest"]):
        sys.exit(selftest())
    sys.exit(main())
