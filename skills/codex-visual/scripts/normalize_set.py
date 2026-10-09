#!/usr/bin/env python3
"""normalize_set.py — deterministic size/framing normalizer for an asset SET.

Makes a group of (already background-removed, RGBA) images share the SAME visual
size and centering, regardless of how large / off-center the generator drew each
one. This is the reliable backstop that reference-image chaining nudges toward
but cannot *guarantee*: a stochastic model matches style well and size only
approximately, so a final deterministic pass locks size exactly. Position and
size are never asked of the model; they are decided here.

Per image: isolate the SUBJECT (alpha >= --solid-thr seeds, grown through every
connected alpha > --alpha-thr pixel; isolated specks a keyer left behind never
join and are cleared) → uniformly scale so the subject's CORE (alpha >
--core-thr) hits a fixed target on its chosen side → paste the core centred on a
fresh transparent canvas, without a mask (a masked paste onto transparency
squares the alpha of every soft pixel).

Why not a plain alpha bounding box: one stray pixel at alpha ~20 in a canvas
corner — a soft matte's usual leftover — drags that box to the canvas edge, so
the whole subject is scaled down and pushed to the far side. A set asked at 78%
can land at 58–68% and up to 14% of the canvas off-centre, and looks like the
model drew it that way. `--raw-bbox` gives the plain-bbox placement for comparison.

Target size comes from one of:
  --content-frac F   core side = F * canvas            (e.g. 0.72)
  --match-anchor P   reuse the core-side fraction measured from anchor P

--fit picks which side is normalized: long (default, good for icons/buttons),
height (good for characters that must share a ground-line), or width.

Examples:
  # lock all three buttons to 72% of a 512 canvas, centered
  normalize_set.py --outdir OUT --canvas 512 --content-frac 0.72 l.png r.png jump.png
  # make a set match an approved anchor's size exactly
  normalize_set.py --outdir OUT --match-anchor anchor.png a.png b.png c.png
  # re-centre delivered assets in place without rescaling (a pure translation)
  normalize_set.py --recenter a.png b.png c.png
  # measure only (no writes) — per-file core size, centre offset, strays, and the set CV
  normalize_set.py --report a.png b.png c.png

Requires Pillow (use codex's imagegen venv: ~/.codex/imagegen-venv/bin/python).
"""
import argparse, os, statistics
from PIL import Image, ImageChops, ImageFilter

THR = 16        # alpha above this counts as content (--alpha-thr)
SOLID_THR = 96  # a pixel this opaque can seed the subject (--solid-thr)
CORE_THR = 40   # the subject's core, which decides scale and centre (--core-thr)


def cv(xs):
    xs = [x for x in xs if x]
    return 0.0 if len(xs) < 2 else statistics.pstdev(xs) / statistics.mean(xs)


def subject_mask(im):
    """255 on the subject: alpha >= SOLID_THR seeds grown through connected alpha > THR pixels."""
    a = im.getchannel("A")
    soft = a.point(lambda p: 255 if p > THR else 0)
    seed = a.point(lambda p: 255 if p >= SOLID_THR else 0)
    if seed.getbbox() is None:
        seed = soft
    cur = ImageChops.multiply(seed, soft)
    for _ in range(4000):
        grown = ImageChops.multiply(cur.filter(ImageFilter.MaxFilter(5)), soft)
        if ImageChops.difference(grown, cur).getbbox() is None:
            break
        cur = grown
    return cur


def extract(im, raw=False):
    """(content cropped to the subject with everything else cleared, core bbox in content coords, strays)."""
    im = im.convert("RGBA")
    a = im.getchannel("A")
    soft = a.point(lambda p: 255 if p > THR else 0)
    if raw:
        bb = soft.getbbox()
        if not bb:
            return None, None, 0
        c = im.crop(bb)
        return c, (0, 0, c.width, c.height), 0
    mask = subject_mask(im)
    full = mask.getbbox()
    if not full:
        return None, None, 0
    strays = soft.histogram()[255] - mask.histogram()[255]
    cleared = im.copy()
    cleared.putalpha(ImageChops.multiply(a, mask))
    core = ImageChops.multiply(mask, a.point(lambda p: 255 if p > CORE_THR else 0)).getbbox() or full
    return (cleared.crop(full),
            (core[0] - full[0], core[1] - full[1], core[2] - full[0], core[3] - full[1]), strays)


def measure(path, raw=False):
    im = Image.open(path).convert("RGBA")
    W, H = im.size
    c, core, strays = extract(im, raw)
    if not c:
        return dict(path=path, W=W, H=H, cw=0, ch=0, frac=0.0, frac_h=0.0, frac_w=0.0, off=(0.0, 0.0), strays=strays)
    cw, ch = core[2] - core[0], core[3] - core[1]
    full = subject_mask(im).getbbox() if not raw else im.getchannel("A").point(lambda p: 255 if p > THR else 0).getbbox()
    cx = full[0] + (core[0] + core[2]) / 2 - W / 2
    cy = full[1] + (core[1] + core[3]) / 2 - H / 2
    return dict(path=path, W=W, H=H, cw=cw, ch=ch, frac=max(cw, ch) / max(W, H), frac_h=ch / H, frac_w=cw / W,
                off=(cx, cy), strays=strays)


def place(content, core, canvas_w, canvas_h, scale):
    cw, ch = content.size
    nw, nh = max(1, round(cw * scale)), max(1, round(ch * scale))
    content = content.resize((nw, nh), Image.LANCZOS) if scale != 1.0 else content
    cx0, cy0, cx1, cy1 = (v * scale for v in core)
    out = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    out.paste(content, (round(canvas_w / 2 - (cx0 + cx1) / 2), round(canvas_h / 2 - (cy0 + cy1) / 2)))  # no mask
    return out


def normalize(path, canvas_w, canvas_h, target, fit, raw):
    im = Image.open(path).convert("RGBA")
    c, core, _ = extract(im, raw)
    if not c:
        return Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    cw, ch = core[2] - core[0], core[3] - core[1]
    base = ch if fit == "height" else cw if fit == "width" else max(cw, ch)
    return place(c, core, canvas_w, canvas_h, target / max(1, base))


def recenter(path, raw):
    im = Image.open(path).convert("RGBA")
    c, core, _ = extract(im, raw)
    return place(c, core, im.width, im.height, 1.0) if c else im


def main():
    global THR, SOLID_THR, CORE_THR
    ap = argparse.ArgumentParser(description="Normalize an asset set to one visual size.")
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--outdir", help="write here (keeps basenames); else in place")
    ap.add_argument("--suffix", default="", help="append to basename (e.g. _norm)")
    ap.add_argument("--canvas", type=int, default=512, help="output canvas px (square unless --canvas-h)")
    ap.add_argument("--canvas-h", type=int, default=0, help="output canvas height for a non-square asset")
    ap.add_argument("--content-frac", type=float, help="core side as fraction of canvas")
    ap.add_argument("--match-anchor", help="reuse this image's core-side fraction")
    ap.add_argument("--fit", choices=["long", "height", "width"], default="long")
    ap.add_argument("--recenter", action="store_true",
                    help="translate each image so its core is centred on its OWN canvas; no rescale, no canvas change")
    ap.add_argument("--alpha-thr", type=int, default=THR)
    ap.add_argument("--solid-thr", type=int, default=SOLID_THR)
    ap.add_argument("--core-thr", type=int, default=CORE_THR)
    ap.add_argument("--raw-bbox", action="store_true", help="plain alpha bbox, no subject isolation, nothing cleared")
    ap.add_argument("--report", action="store_true", help="measure only; no writes")
    a = ap.parse_args()
    THR, SOLID_THR, CORE_THR = a.alpha_thr, a.solid_thr, a.core_thr

    if a.report:
        rows = [measure(p, a.raw_bbox) for p in a.inputs]
        for r in rows:
            print(f"{os.path.basename(r['path']):<30} {r['W']}x{r['H']}  core {r['cw']}x{r['ch']}  "
                  f"long-frac {r['frac'] * 100:5.1f}%  centre off ({r['off'][0]:+.1f},{r['off'][1]:+.1f})px  "
                  f"strays {r['strays']}")
        print(f"long-side fraction CV: {cv([r['frac'] for r in rows]) * 100:.1f}%  (lower = more consistent)  "
              f"max centre offset {max(max(abs(r['off'][0]), abs(r['off'][1])) for r in rows):.1f}px")
        return

    suffix = a.suffix or ("" if a.outdir else "_norm")
    if a.outdir:
        os.makedirs(a.outdir, exist_ok=True)
        names = [os.path.basename(p) for p in a.inputs]
        if len(set(names)) != len(names):
            ap.error("two inputs share a basename and would overwrite each other in --outdir; rename them first")

    def dest_for(p):
        if a.outdir:
            return os.path.join(a.outdir, os.path.splitext(os.path.basename(p))[0] + suffix + ".png")
        base, ext = os.path.splitext(p)
        return base + (suffix if not a.recenter else "") + ext

    if a.recenter:
        for p in a.inputs:
            out = recenter(p, a.raw_bbox)
            d = dest_for(p); out.save(d)
            m = measure(d)
            print(f"recentred {d}  centre off ({m['off'][0]:+.1f},{m['off'][1]:+.1f})px")
        return

    if a.match_anchor:
        m = measure(a.match_anchor)
        frac = m["frac_h"] if a.fit == "height" else m["frac_w"] if a.fit == "width" else m["frac"]
    elif a.content_frac:
        frac = a.content_frac
    else:
        ap.error("need --content-frac, --match-anchor, --recenter or --report")

    canvas_w, canvas_h = a.canvas, a.canvas_h or a.canvas
    target = round(frac * (canvas_h if a.fit == "height" else canvas_w))
    outs = []
    for p in a.inputs:
        out = normalize(p, canvas_w, canvas_h, target, a.fit, a.raw_bbox)
        d = dest_for(p); out.save(d); outs.append(d)
        print(f"wrote {d}")
    rows = [measure(o) for o in outs]
    print(f"target side = {target}px ({frac * 100:.1f}% of {canvas_h if a.fit == 'height' else canvas_w}, fit {a.fit})")
    print(f"post-normalize long-side fraction CV: {cv([r['frac'] for r in rows]) * 100:.2f}%  "
          f"max centre offset {max(max(abs(r['off'][0]), abs(r['off'][1])) for r in rows):.1f}px")


if __name__ == "__main__":
    main()
