#!/usr/bin/env python3
"""pick_key.py — choose the chroma key a base image can be keyed on without losing part of it.

A key erases every pixel within 96 RGB of it (`key_unmix.py --edge tint`'s cut,
the same radius in both of its balls). So the key for a character's sheets or
clips is picked from the base still BEFORE anything is generated on it: the one
whose nearest subject pixel is farther than that radius, and among those the one
the subject stays farthest from.

How the subject is found (on a copy shrunk to 256 px with NEAREST, so no blend
colour is invented between the field and the subject):

  background  the border ring, bucketed at 16 levels per channel: the largest
              bucket's mean is the field when 75 % of the opaque border lies
              within 48 of it (flat); under 25 % opaque border = transparent;
              otherwise heterogeneous (nothing is excluded but alpha, and a
              warning says the distances may count the background).
  field       pixels within 48 of the field, flood-filled 8-connected from the
              border and from transparency. An enclosed key-coloured region is
              a hole when 60 % of it is within 16 of the field (flat fill) and the
              art's own material otherwise (shaded), which stays subject.
  rim         the field grown 2 px (4-connected) swallows the anti-aliased rim.
  specks      near-white pixels (every channel > 244) and pixels with fewer than
              3 of 8 neighbours within 40 of them are dropped: one pixel is not
              a feature.

Candidates, in order of preference: magenta #FF00FF, green #00FF00, cyan #00FFFF,
blue #004DFF. Each scores (1st-percentile subject distance, nearest subject
distance, -preference); eligible only when the nearest subject pixel is farther
than --min-distance (96). The highest eligible score wins; ties go to magenta,
then green, cyan, blue.

Output: one JSON object — the pick, the background read, and every candidate's
p1 / nearest distance / eligibility, the nearest subject pixel (x, y, rgb in the
source image) and the bounding box of the subject pixels inside its radius.

Examples
  pick_key.py refs/runner_base.png
  pick_key.py refs/sentry_base.png --min-distance 110 > keys/sentry.json
  pick_key.py --selftest

Exit codes: 0 a key is eligible (also when the base yields no subject pixels:
magenta, `selection: fallback`, with a warning) · 1 no candidate clears the
radius (stderr names, for the best-scoring one, the subject feature it would
erase and where it sits: recolour it in the base or accept losing it), an
unreadable image, bad arguments, or a failed --selftest.

Requires Pillow and numpy (codex's imagegen venv has both: ~/.codex/imagegen-venv/bin/python).
"""
# ---------------------------------------------------------------------------
# Third-party code. Portions are ported, with identifiers and structure
# adapted, from sprite-gen
#   https://github.com/aldegad/sprite-gen
#   commit dddcc1013f7b5587a5eabd8609a5b42dd8aa7c26
#   Apache License 2.0 — see THIRD_PARTY_NOTICES.md.
#
#   gen/prepare.py  CHROMA_CANDIDATES, _border_coordinates (border_ring),
#                   detect_reference_background (read_background),
#                   _background_mask (background_mask), _subject_pixels
#                   (subject_pixels), analyze_reference (analyze), the
#                   scoring and eligibility rule of choose_chroma_key (score /
#                   choose), and the constants REFERENCE_SAMPLE_SIZE,
#                   BACKGROUND_TOLERANCE, BACKGROUND_MIN_OPAQUE_BORDER,
#                   BACKGROUND_BORDER_COVERAGE, BACKGROUND_EDGE_DILATION,
#                   BACKGROUND_FLAT_TOLERANCE, ENCLOSED_FLAT_FRACTION,
#                   SPECKLE_NEIGHBOR_TOLERANCE, SPECKLE_MIN_SIMILAR_NEIGHBORS,
#                   MIN_SUBJECT_KEY_DISTANCE
#
# Changes: the flood fill, the dilation and the speck test are numpy array
# passes (components from sprite_ops.label) instead of per-pixel Python loops;
# subject pixels keep their positions, so every candidate reports the nearest
# subject pixel and the bounding box of the pixels inside its radius in source
# coordinates; a manual key and the request plumbing are not carried; when no
# candidate is eligible the script exits 1 instead of falling back to the raw
# ranking with a warning.
# ---------------------------------------------------------------------------
import argparse
import json
import math
import os
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sprite_ops as so  # noqa: E402

CANDIDATES = [("magenta", (255, 0, 255)), ("green", (0, 255, 0)), ("cyan", (0, 255, 255)), ("blue", (0, 77, 255))]
SAMPLE = 256              # the base is shrunk to this (NEAREST) before it is read
BG_TOL = 48.0             # within this of the border colour = field
BG_MIN_OPAQUE = 0.25      # less opaque border than this = a transparent base
BG_COVERAGE = 0.75        # the border colour must cover this share of the opaque border
EDGE_GROW = 2             # the field is grown this many px (4-connected) over the rim
FLAT_TOL = 16.0           # an enclosed region within this of the field...
ENCLOSED_FLAT = 0.60      # ...for this share of its pixels is a hole, else drawn material
SPECK_TOL = 40.0          # a subject pixel needs neighbours within this of it...
SPECK_MIN = 3             # ...at least this many of its 8
MIN_DISTANCE = 96.0       # the erase radius: a key must clear every subject pixel by more
NEAR_WHITE = 244          # every channel above this = near-white, not counted as subject

N8 = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
N4 = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def hexof(rgb):
    return "#%02X%02X%02X" % tuple(int(v) for v in rgb)


def sqdist(rgb, c):
    d = rgb.astype(np.int64) - np.asarray(c, np.int64)
    return (d * d).sum(axis=-1)


def shift(m, dy, dx, fill=False):
    """m moved by (dy, dx) with no wrap: out[y, x] = m[y - dy, x - dx]."""
    out = np.full(m.shape, fill, m.dtype)
    h, w = m.shape[:2]
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = m[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def border_ring(w, h):
    if w < 2 or h < 2:
        return [(x, y) for y in range(h) for x in range(w)]
    ring = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
    return ring + [(0, y) for y in range(1, h - 1)] + [(w - 1, y) for y in range(1, h - 1)]


def read_background(rgba):
    """{mode: flat|transparent|heterogeneous, ...} from the border ring of an HxWx4 uint8 array."""
    h, w = rgba.shape[:2]
    ring = border_ring(w, h)
    opaque = [(x, y) for x, y in ring if rgba[y, x, 3] > 16]
    frac = len(opaque) / len(ring) if ring else 0.0
    if frac < BG_MIN_OPAQUE:
        return {"mode": "transparent", "opaque_border_fraction": round(frac, 3)}
    buckets = {}
    for x, y in opaque:
        c = tuple(int(v) for v in rgba[y, x, :3])
        buckets.setdefault(tuple(v // 16 for v in c), []).append(c)
    members = max(buckets.values(), key=len)
    bg = tuple(round(sum(m[i] for m in members) / len(members)) for i in range(3))
    within = sum(1 for x, y in opaque if math.sqrt(sum((int(rgba[y, x, i]) - bg[i]) ** 2 for i in range(3))) <= BG_TOL)
    cover = within / len(opaque)
    if cover < BG_COVERAGE:
        return {"mode": "heterogeneous", "opaque_border_fraction": round(frac, 3), "border_coverage": round(cover, 3),
                "note": f"the border is not a flat fill (its largest colour covers {cover:.0%}, needs "
                        f"{BG_COVERAGE:.0%}); no background was excluded, so the distances may count it"}
    return {"mode": "flat", "hex": hexof(bg), "rgb": list(bg), "opaque_border_fraction": round(frac, 3),
            "border_coverage": round(cover, 3)}


def background_mask(rgba, bg):
    """Bool HxW: the base's background (field, holes, transparency) grown over the rim."""
    transparent = rgba[..., 3] <= 16
    mask = transparent.copy()
    if bg["mode"] == "flat":
        key = bg["rgb"]
        sd = sqdist(rgba[..., :3], key)
        near = transparent | (np.sqrt(sd.astype(np.float64)) <= BG_TOL)
        lab, n = so.label(near)
        edge = np.zeros(near.shape, bool)
        edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
        grounded = np.zeros(n + 1, bool)
        grounded[np.unique(lab[(edge | transparent) & near])] = True
        size = np.bincount(lab.ravel(), minlength=n + 1)
        flat = np.bincount(lab.ravel(), weights=(np.sqrt(sd.astype(np.float64)) <= FLAT_TOL).ravel(), minlength=n + 1)
        hole = ~grounded & (flat >= ENCLOSED_FLAT * np.maximum(size, 1))
        material = ~grounded & ~hole
        material[0] = hole[0] = False
        keep = grounded | hole
        keep[0] = False
        mask |= keep[lab]
        bg["enclosed_background_pixels"] = int(size[hole].sum())
        bg["enclosed_material_pixels"] = int(size[material].sum())
    for _ in range(EDGE_GROW):
        grown = mask.copy()
        for dy, dx in N4:
            grown |= shift(mask, dy, dx)
        mask = grown
    return mask


def subject_pixels(rgba, bg):
    """Bool HxW of the subject pixels that count: not background, not near-white, not a speck."""
    rgb = rgba[..., :3]
    cand = ~background_mask(rgba, bg) & ~(rgb > NEAR_WHITE).all(axis=-1)
    similar = np.zeros(cand.shape, np.int32)
    for dy, dx in N8:
        nb_c = shift(cand, dy, dx)
        nb = shift(rgb, dy, dx)
        similar += nb_c & (np.sqrt(sqdist_pair(rgb, nb)) <= SPECK_TOL)
    return cand & (similar >= SPECK_MIN)


def sqdist_pair(a, b):
    d = a.astype(np.int64) - b.astype(np.int64)
    return (d * d).sum(axis=-1).astype(np.float64)


def analyze(path):
    """(subject HxW bool, sampled RGBA, background dict, (sx, sy) sample -> source scale, source size)."""
    with Image.open(path) as im:
        src_size = im.size
        img = im.convert("RGBA")
        img.thumbnail((SAMPLE, SAMPLE), Image.Resampling.NEAREST)
    rgba = np.asarray(img)
    bg = read_background(rgba)
    subj = subject_pixels(rgba, bg)
    bg["subject_pixels"] = int(subj.sum())
    scale = (src_size[0] / rgba.shape[1], src_size[1] / rgba.shape[0])
    return subj, rgba, bg, scale, src_size


def to_source(x0, y0, x1, y1, scale, size):
    """A sample-pixel box (inclusive) -> the source-pixel box [left, top, right, bottom) it covers."""
    sx, sy = scale
    return [int(math.floor(x0 * sx)), int(math.floor(y0 * sy)),
            min(size[0], int(math.ceil((x1 + 1) * sx))), min(size[1], int(math.ceil((y1 + 1) * sy)))]


def score(subj, rgba, scale, size, min_distance=MIN_DISTANCE):
    """Every candidate's numbers, in preference order."""
    ys, xs = np.nonzero(subj)
    cols = rgba[ys, xs, :3]
    out = []
    for pref, (name, rgb) in enumerate(CANDIDATES):
        d = np.sqrt(sqdist(cols, rgb).astype(np.float64))
        order = np.argsort(d, kind="stable")
        p1 = float(d[order[max(0, min(len(d) - 1, int(len(d) * 0.01)))]])
        i = int(order[0])
        inside = d <= min_distance
        entry = {"name": name, "hex": hexof(rgb), "rgb": list(rgb), "p1_distance": round(p1, 2),
                 "min_subject_distance": round(float(d[i]), 2),
                 "clears_erase_radius": bool(float(d[i]) > min_distance),
                 "nearest_subject_pixel": {"xy": to_source(int(xs[i]), int(ys[i]), int(xs[i]), int(ys[i]), scale,
                                                           size)[:2],
                                           "rgb": [int(v) for v in cols[i]]},
                 "within_radius_px": int(inside.sum()),
                 "_key": (p1, float(d[i]), -pref)}
        if inside.any():
            entry["within_radius_bbox"] = to_source(int(xs[inside].min()), int(ys[inside].min()),
                                                    int(xs[inside].max()), int(ys[inside].max()), scale, size)
        out.append(entry)
    return out


def choose(scored):
    """(winner, eligible?) — the highest (p1, nearest, -preference) among those clearing the radius, else overall."""
    safe = [e for e in scored if e["clears_erase_radius"]]
    pool = safe or scored
    return max(pool, key=lambda e: e["_key"]), bool(safe)


def pick(path, min_distance=MIN_DISTANCE):
    """-> (result dict, exit code)."""
    subj, rgba, bg, scale, size = analyze(path)
    res = {"image": path, "size": list(size), "sample_size": [rgba.shape[1], rgba.shape[0]], "background": bg,
           "min_distance": min_distance}
    if not subj.any():
        res.update(pick="magenta", hex="#FF00FF", rgb=[255, 0, 255], selection="fallback", eligible=True,
                   warning="the base yields no subject pixels once its background is excluded; magenta by default")
        return res, 0
    scored = score(subj, rgba, scale, size, min_distance)
    win, ok = choose(scored)
    res.update(pick=win["name"], hex=win["hex"], rgb=win["rgb"], selection="auto", eligible=ok,
               p1_distance=win["p1_distance"], min_subject_distance=win["min_subject_distance"],
               candidates=[{k: v for k, v in e.items() if k != "_key"} for e in scored])
    if bg["mode"] == "heterogeneous":
        res["warning"] = bg["note"]
    if not ok:
        res["erased_feature"] = {"key": win["hex"], "nearest_subject_pixel": win["nearest_subject_pixel"],
                                 "within_radius_px_sampled": win["within_radius_px"],
                                 "bbox": win.get("within_radius_bbox")}
    return res, 0 if ok else 1


# --------------------------------------------------------------- selftest ----
def _base(h, w, field, blobs):
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = field
    for (y0, y1, x0, x1), c in blobs:
        img[y0:y1, x0:x1] = c
    return img


def selftest():
    fails = []

    def check(ok, what):
        print(("ok    " if ok else "FAIL  ") + what)
        if not ok:
            fails.append(what)

    with tempfile.TemporaryDirectory() as tmp:
        def run(img, name):
            p = os.path.join(tmp, name)
            Image.fromarray(img).save(p)
            return pick(p)

        body = ((20, 108, 40, 88), (60, 140, 230))         # a blue runner body
        skin = ((24, 44, 52, 76), (230, 180, 140))
        # 1. a blue-and-skin subject on magenta: the eligible candidate with the highest p1 wins
        r, rc = run(_base(128, 128, (255, 0, 255), [body, skin]), "runner.png")
        cands = {c["name"]: c for c in r["candidates"]}
        best = max((c for c in r["candidates"] if c["clears_erase_radius"]), key=lambda c: c["p1_distance"])
        check(rc == 0 and r["pick"] == best["name"] and r["background"]["mode"] == "flat",
              f"blue/skin subject on magenta -> the eligible key with the highest p1 ({r['pick']}, rc {rc})")
        check(not cands["blue"]["clears_erase_radius"], "the blue candidate is refused (the body is near it)")
        check(r["background"]["subject_pixels"] > 0 and cands["magenta"]["min_subject_distance"] > 96,
              "the magenta field itself is not counted as subject")
        # 2. a magenta gem on the subject of a green-field base: magenta is refused, green kept
        gem = ((60, 66, 60, 66), (240, 20, 230))
        r, rc = run(_base(128, 128, (0, 255, 0), [((20, 108, 40, 88), (200, 120, 60)), gem]), "sentry.png")
        cands = {c["name"]: c for c in r["candidates"]}
        check(rc == 0 and not cands["magenta"]["clears_erase_radius"] and r["pick"] != "magenta",
              f"a magenta gem refuses magenta ({r['pick']})")
        bb = cands["magenta"].get("within_radius_bbox")
        check(bb is not None and bb[0] <= 60 and bb[1] <= 60 and bb[2] >= 66 and bb[3] >= 66,
              f"the gem's box is reported where it sits ({bb})")
        # 3. a lone key-coloured speck is not a feature
        r, rc = run(_base(128, 128, (0, 255, 0), [((20, 108, 40, 88), (200, 120, 60)),
                                                  ((64, 65, 64, 65), (250, 5, 250))]), "speck.png")
        cands = {c["name"]: c for c in r["candidates"]}
        check(cands["magenta"]["clears_erase_radius"], "a one-pixel magenta speck does not refuse magenta")
        # 4. a flat hole showing the green field is background; a shaded green patch is material
        ring = _base(128, 128, (0, 255, 0), [((20, 108, 30, 98), (120, 70, 40))])
        ring[50:78, 50:78] = (0, 255, 0)
        r, rc = run(ring, "hole.png")
        cands = {c["name"]: c for c in r["candidates"]}
        check(cands["green"]["clears_erase_radius"] and r["background"]["enclosed_background_pixels"] > 0,
              "an enclosed flat hole of the field is background, so green stays eligible")
        shaded = ring.copy()
        g = np.linspace(215, 255, 28).astype(np.uint8)      # within 48 of the field, mostly not within 16
        shaded[50:78, 50:78] = np.stack([np.zeros((28, 28)), np.tile(g, (28, 1)), np.zeros((28, 28))], -1)
        r, rc = run(shaded, "material.png")
        cands = {c["name"]: c for c in r["candidates"]}
        check(not cands["green"]["clears_erase_radius"] and r["background"]["enclosed_material_pixels"] > 0,
              "an enclosed shaded green region is the art's own material, so green is refused")
        # 5. features near every candidate: exit 1 and the erased feature is named
        feats = [((30, 40, 50, 60), (240, 20, 240)), ((45, 55, 50, 60), (20, 240, 20)),
                 ((60, 70, 50, 60), (20, 240, 240)), ((75, 85, 50, 60), (20, 80, 240))]
        r, rc = run(_base(128, 128, (128, 128, 128), [((20, 108, 40, 88), (120, 90, 70))] + feats), "all.png")
        check(rc == 1 and not r["eligible"] and r.get("erased_feature", {}).get("bbox"),
              f"nothing eligible -> exit 1 with the erased feature named (rc {rc})")
        # 6. a tie goes to magenta, then green, cyan, blue
        tie = [{"name": n, "clears_erase_radius": True, "_key": (200.0, 150.0, -i)} for i, (n, _) in
               enumerate(CANDIDATES)]
        check(choose(list(reversed(tie)))[0]["name"] == "magenta", "equal scores: magenta wins")
        # 7. the sample is read at 256 px and boxes come back in source coordinates
        big = np.kron(_base(128, 128, (0, 255, 0), [((20, 108, 40, 88), (200, 120, 60)), gem]),
                      np.ones((4, 4, 1), np.uint8))
        r, rc = run(big, "big.png")
        cands = {c["name"]: c for c in r["candidates"]}
        bb = cands["magenta"].get("within_radius_bbox")
        check(r["sample_size"] == [256, 256] and bb is not None and bb[0] <= 240 and bb[2] >= 264,
              f"a 512 px base is sampled at 256 and the gem box is in source px ({bb})")
    print("verdict " + ("FAIL" if fails else "OK"))
    return 1 if fails else 0


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main():
    ap = UsageParser(description="Choose the chroma key (magenta, green, cyan, blue) a base image can be "
                                             "keyed on without erasing any of its subject.")
    ap.add_argument("image", help="the base still: the subject on a flat field, or on transparency")
    ap.add_argument("--min-distance", type=float, default=MIN_DISTANCE,
                    help="the erase radius a key must clear every subject pixel by (default 96, the key_unmix.py "
                         "--edge tint cut)")
    a = ap.parse_args()
    try:
        res, rc = pick(a.image, a.min_distance)
    except (OSError, ValueError) as e:
        print(f"ERROR: cannot read {a.image}: {e}", file=sys.stderr)
        return 1
    print(json.dumps(res, indent=2))
    if res.get("warning"):
        print(f"WARN: {res['warning']}", file=sys.stderr)
    if rc:
        f = res["erased_feature"]
        px = f["nearest_subject_pixel"]
        print(f"FAIL: no key clears the {a.min_distance:g} erase radius. Best is {f['key']}, whose nearest subject "
              f"pixel rgb{tuple(px['rgb'])} at x,y {px['xy'][0]},{px['xy'][1]} lies inside it; the pixels it would "
              f"erase sit in box {f['bbox']} (left, top, right, bottom). Recolour that feature in the base, or key "
              f"it anyway knowing it goes.", file=sys.stderr)
    return rc


if __name__ == "__main__":
    if sys.argv[1:] in (["--selftest"], ["selftest"]):
        sys.exit(selftest())
    sys.exit(main())
