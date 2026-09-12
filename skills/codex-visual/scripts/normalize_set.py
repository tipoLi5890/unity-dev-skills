#!/usr/bin/env python3
"""normalize_set.py — deterministic size/framing normalizer for an asset SET.

Makes a group of (already background-removed, RGBA) images share the SAME visual
size and centering, regardless of how large / off-center the generator drew each
one. This is the reliable backstop that reference-image chaining nudges toward
but cannot *guarantee*: a stochastic model matches style well and size only
approximately, so a final deterministic pass locks size exactly.

Per image: crop to the opaque-content box → uniformly scale so its chosen side
hits a fixed target → paste centered on a fresh transparent square canvas.

Target size comes from one of:
  --content-frac F   content side = F * canvas            (e.g. 0.72)
  --match-anchor P   reuse the content-side fraction measured from anchor P

--fit picks which side is normalized: long (default, good for icons/buttons),
height (good for characters that must share a ground-line), or width.

Examples:
  # lock all three buttons to 72% of a 512 canvas, centered
  normalize_set.py --outdir OUT --canvas 512 --content-frac 0.72 l.png r.png jump.png
  # make a set match an approved anchor's size exactly
  normalize_set.py --outdir OUT --match-anchor anchor.png a.png b.png c.png
  # measure only (no writes) — prints per-file size + set CV
  normalize_set.py --report a.png b.png c.png

Requires Pillow (use codex's imagegen venv: ~/.codex/imagegen-venv/bin/python).
"""
import argparse, os, statistics
from PIL import Image

THR = 16  # alpha considered "content" above this

def content_bbox(im):
    a = im.getchannel("A")
    return a.point(lambda p: 255 if p > THR else 0).getbbox()

def measure(path):
    im = Image.open(path).convert("RGBA")
    W, H = im.size
    bb = content_bbox(im)
    if not bb:
        return dict(path=path, W=W, H=H, cw=0, ch=0, frac=0.0)
    cw, ch = bb[2] - bb[0], bb[3] - bb[1]
    return dict(path=path, W=W, H=H, cw=cw, ch=ch, frac=max(cw, ch) / max(W, H))

def cv(xs):
    xs = [x for x in xs if x]
    return 0.0 if len(xs) < 2 else statistics.pstdev(xs) / statistics.mean(xs)

def normalize(path, canvas, target_long, fit):
    im = Image.open(path).convert("RGBA")
    bb = content_bbox(im)
    if not bb:
        return im.resize((canvas, canvas), Image.LANCZOS)
    crop = im.crop(bb)
    cw, ch = crop.size
    base = ch if fit == "height" else cw if fit == "width" else max(cw, ch)
    scale = target_long / base
    nw, nh = max(1, round(cw * scale)), max(1, round(ch * scale))
    crop = crop.resize((nw, nh), Image.LANCZOS)
    out = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    out.paste(crop, ((canvas - nw) // 2, (canvas - nh) // 2), crop)
    return out

def main():
    ap = argparse.ArgumentParser(description="Normalize an asset set to one visual size.")
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--outdir", help="write here (keeps basenames); else in place")
    ap.add_argument("--suffix", default="", help="append to basename (e.g. _norm)")
    ap.add_argument("--canvas", type=int, default=512, help="output square canvas px")
    ap.add_argument("--content-frac", type=float, help="content side as fraction of canvas")
    ap.add_argument("--match-anchor", help="reuse this image's content-side fraction")
    ap.add_argument("--fit", choices=["long", "height", "width"], default="long")
    ap.add_argument("--report", action="store_true", help="measure only; no writes")
    a = ap.parse_args()

    if a.report:
        rows = [measure(p) for p in a.inputs]
        for r in rows:
            print(f"{os.path.basename(r['path']):<30} {r['W']}x{r['H']}  "
                  f"content {r['cw']}x{r['ch']}  long-frac {r['frac']*100:5.1f}%")
        print(f"long-side fraction CV: {cv([r['frac'] for r in rows])*100:.1f}%  (lower = more consistent)")
        return

    if a.match_anchor:
        frac = measure(a.match_anchor)["frac"]
    elif a.content_frac:
        frac = a.content_frac
    else:
        ap.error("need --content-frac or --match-anchor")

    suffix = a.suffix or ("" if a.outdir else "_norm")
    if a.outdir:
        os.makedirs(a.outdir, exist_ok=True)
    target_long = round(frac * a.canvas)

    outs = []
    for p in a.inputs:
        out = normalize(p, a.canvas, target_long, a.fit)
        if a.outdir:
            dest = os.path.join(a.outdir, os.path.splitext(os.path.basename(p))[0] + suffix + ".png")
        else:
            base, ext = os.path.splitext(p)
            dest = base + suffix + ext
        out.save(dest)
        outs.append(dest)
        print(f"wrote {dest}")
    rows = [measure(o) for o in outs]
    print(f"target long side = {target_long}px ({frac*100:.1f}% of {a.canvas})")
    print(f"post-normalize long-side fraction CV: {cv([r['frac'] for r in rows])*100:.2f}%")

if __name__ == "__main__":
    main()
