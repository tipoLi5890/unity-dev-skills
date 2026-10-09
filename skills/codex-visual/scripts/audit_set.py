#!/usr/bin/env python3
"""audit_set.py — the geometry gate for a delivered set of sprites.

`slice_grid.py` and `normalize_set.py` promise that every asset of a set is
centred and sized to one fraction. This script checks the promise on the files
that actually shipped — the eye cannot: on a 256 px canvas a subject 36 px off
centre and 25% too small still "looks fine" until it sits next to its siblings
in a game cell, and a set scaled down by the same stray pixel is internally
consistent (identical bboxes, 0% spread) while the whole set is wrong.

Every asset gets one line; a failed gate prints its reason and the exit code is
1, so a build step or a pre-commit hook can refuse the set.

Columns
  canvas  W x H
  core    bounding box of the subject's core (alpha > --core-thr, connected to a solid pixel)
  off     core centre minus canvas centre, px      gate: |off| <= --off-max (default 2)
  fill    the --fit side of the core over the canvas   gate: within --fill-tol of --expect-frac
  strays  content pixels not connected to any solid pixel (a keyer's leftover speckle)
  sym     left/right mirror IoU of the core mask (--symmetry only; 1.00 = perfectly symmetric)
  tilt    x-centroid of the top half minus the bottom half, px (--symmetry only)
  lean    height difference of the left and right ends of the top 18% band, px (--symmetry only)
  fringe  rim pixels (visible, within 2 px of transparency) within 150 RGB of the key: mostly key
  tint    rim pixels that are the interior colour beside them mixed with the key: partly key
          (--key-color only; gate: fringe <= --fringe-max 0.5 %, tint <= --tint-max 2 %, and more than
          --rim-floor 12 px of either — a 256 px icon's rim is ~1,500 px, and a handful of alpha-1
          pixels is not a fringe). A binary key or `remove_chroma_key.py --despill` reads fringe
          5-52 %, tint 26-84 % per asset; keyed by `key_unmix.py`, 0.0-0.6 % and 0.0-1.0 %.
The set line prints the spread of core width and height across the files
(gate: <= --spread-max, default 8%) — siblings that are "not one set".

Examples
  audit_set.py Assets/Art/Shop/*.png --expect-frac 0.78
  audit_set.py Assets/Art/Chars/*.png --expect-frac 0.88 --fit height --spread-max 0.15
  audit_set.py jar_a.png jar_b.png jar_c.png --expect-frac 0.78 --symmetry   # upright containers only
  audit_set.py Assets/Art/UI/*.png --expect-frac 0.78 --key-color '#ff00ff'  # and what the key left on the rim

`--symmetry` is for single upright objects (jars, cups, poles, a front-facing
character). Scattered effects, composite icons and animals in profile are
asymmetric by design; the flag would only produce noise there.

Requires Pillow (use codex's imagegen venv: ~/.codex/imagegen-venv/bin/python); `--key-color` also
needs numpy and `sprite_ops.py` beside this script (the same venv has numpy).
"""
import argparse, os, sys
from PIL import Image, ImageChops, ImageFilter, ImageOps

THR, SOLID_THR, CORE_THR = 16, 96, 40


def subject_mask(im):
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


def centroid_x(mask):
    """x centroid of a 255/0 mask via a 1-row BOX resize (column sums)."""
    w = mask.width
    cols = list(mask.resize((w, 1), Image.BOX).tobytes())
    tot = sum(cols)
    return sum(i * v for i, v in enumerate(cols)) / tot if tot else 0.0


def measure(path, fit, symmetry):
    im = Image.open(path).convert("RGBA")
    W, H = im.size
    a = im.getchannel("A")
    soft = a.point(lambda p: 255 if p > THR else 0)
    mask = subject_mask(im)
    core = ImageChops.multiply(mask, a.point(lambda p: 255 if p > CORE_THR else 0))
    bb = core.getbbox() or mask.getbbox()
    if not bb:
        return None
    x0, y0, x1, y1 = bb
    cw, ch = x1 - x0, y1 - y0
    m = dict(W=W, H=H, cw=cw, ch=ch, off=((x0 + x1) / 2 - W / 2, (y0 + y1) / 2 - H / 2),
             fill=(ch / H if fit == "height" else cw / W if fit == "width" else max(cw, ch) / max(W, H)),
             strays=soft.histogram()[255] - mask.histogram()[255])
    if symmetry:
        box = core.crop(bb)
        mir = ImageOps.mirror(box)
        inter = ImageChops.multiply(box, mir).histogram()[255]
        union = ImageChops.lighter(box, mir).histogram()[255]
        m["sym"] = inter / max(1, union)
        top, bot = box.crop((0, 0, cw, ch // 2)), box.crop((0, ch // 2, cw, ch))
        m["tilt"] = centroid_x(top) - centroid_x(bot)
        lip = box.crop((0, 0, cw, max(2, int(ch * 0.18))))
        cols = list(lip.resize((cw, 1), Image.BOX).tobytes())
        occupied = [i for i, v in enumerate(cols) if v]
        m["lean"] = 0.0
        if len(occupied) > 4:
            k = max(1, len(occupied) // 5)
            def first_row(xs):
                sub = lip.crop((min(xs), 0, max(xs) + 1, lip.height))
                rows = list(sub.resize((1, sub.height), Image.BOX).tobytes())
                return next((i for i, v in enumerate(rows) if v), 0)
            m["lean"] = float(first_row(occupied[-k:]) - first_row(occupied[:k]))   # + = left high, right low
    return m


def main():
    global THR, SOLID_THR, CORE_THR
    ap = argparse.ArgumentParser(description="Geometry gate for a delivered sprite set.")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--expect-frac", type=float, help="the content-frac the set was normalized to")
    ap.add_argument("--fit", choices=["long", "height", "width"], default="long")
    ap.add_argument("--off-max", type=float, default=2.0, help="max |centre offset| px (default 2)")
    ap.add_argument("--fill-tol", type=float, default=0.02, help="max |fill - expect-frac| (default 0.02)")
    ap.add_argument("--spread-max", type=float, default=0.08,
                    help="max (max-min)/mean of core width and height across the set (default 0.08)")
    ap.add_argument("--symmetry", action="store_true", help="also report sym / tilt / lean (upright objects)")
    ap.add_argument("--sym-min", type=float, default=0.92)
    ap.add_argument("--tilt-max", type=float, default=8.0)
    ap.add_argument("--lean-max", type=float, default=6.0)
    ap.add_argument("--alpha-thr", type=int, default=THR)
    ap.add_argument("--solid-thr", type=int, default=SOLID_THR)
    ap.add_argument("--core-thr", type=int, default=CORE_THR)
    ap.add_argument("--key-color", help="the key colour the sheet was generated on, e.g. '#ff00ff': also report "
                                        "and gate the rim's fringe and tint")
    ap.add_argument("--fringe-max", type=float, default=0.5, help="max fringe %% of an asset's rim (default 0.5)")
    ap.add_argument("--tint-max", type=float, default=2.0, help="max tint %% of an asset's rim (default 2)")
    ap.add_argument("--rim-floor", type=int, default=12,
                    help="fewer fringe / tint pixels than this never fail an asset (default 12)")
    a = ap.parse_args()
    THR, SOLID_THR, CORE_THR = a.alpha_thr, a.solid_thr, a.core_thr
    so = key = None
    if a.key_color:
        try:
            import numpy as np
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import sprite_ops as so
        except ImportError as e:
            print(f"ERROR: --key-color needs numpy and sprite_ops.py beside this script ({e})", file=sys.stderr)
            sys.exit(1)
        key = so.parse_hex(a.key_color)

    head = f"{'name':24s} {'canvas':>9s} {'core':>9s} {'off':>13s} {'fill':>13s} {'strays':>6s}"
    if a.symmetry:
        head += f" {'sym':>5s} {'tilt':>6s} {'lean':>6s}"
    if key:
        head += f" {'fringe':>7s} {'tint':>7s}"
    print(head)
    rows, failed = [], 0
    for p in a.files:
        m = measure(p, a.fit, a.symmetry)
        name = os.path.splitext(os.path.basename(p))[0][:24]
        if m is None:
            print(f"{name:24s}  (fully transparent)  ← FAIL"); failed += 1; continue
        rows.append(m)
        flags = []
        if max(abs(m["off"][0]), abs(m["off"][1])) > a.off_max: flags.append("off-centre")
        if a.expect_frac is not None and abs(m["fill"] - a.expect_frac) > a.fill_tol: flags.append("size")
        want = f"({a.expect_frac:.2f})" if a.expect_frac is not None else ""
        line = (f"{name:24s} {m['W']:>4d}x{m['H']:<4d} {m['cw']:>4d}x{m['ch']:<4d} "
                f"({m['off'][0]:>+5.1f},{m['off'][1]:>+5.1f}) {m['fill']:>6.2f}{want:<7s} {m['strays']:>6d}")
        if a.symmetry:
            if m["sym"] < a.sym_min: flags.append("asymmetric")
            if abs(m["tilt"]) > a.tilt_max: flags.append("tilted")
            if abs(m["lean"]) > a.lean_max: flags.append("rim-not-level")
            line += f" {m['sym']:>5.2f} {m['tilt']:>+6.1f} {m['lean']:>+6.1f}"
        if key:
            arr = np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)
            bad, tinted, rim = so.rim_stats(arr[..., :3], arr[..., 3], key)
            fr, ti = so.pct(bad, rim), so.pct(tinted, rim)
            if (fr > a.fringe_max and bad > a.rim_floor) or (ti > a.tint_max and tinted > a.rim_floor):
                flags.append("key on the rim")
            line += f" {fr:>6.2f}% {ti:>6.2f}%"
        if flags:
            failed += 1
            line += "  ← " + ", ".join(flags)
        print(line)
    if len(rows) > 1:
        ws, hs = [m["cw"] for m in rows], [m["ch"] for m in rows]
        sw = (max(ws) - min(ws)) / max(1, sum(ws) / len(ws))
        sh = (max(hs) - min(hs)) / max(1, sum(hs) / len(hs))
        bad = max(sw, sh) > a.spread_max
        print(f"\nset spread: width {sw:.0%}, height {sh:.0%}" + (f"  ← not one set (> {a.spread_max:.0%})" if bad else "  ✓ one set"))
        if bad and a.fit != "long":
            failed += 1
    if failed:
        print(f"\n{failed} FAIL — gates: |off| <= {a.off_max:g} px"
              + (f", |fill - {a.expect_frac:.2f}| <= {a.fill_tol:g}" if a.expect_frac is not None else "")
              + (f", sym >= {a.sym_min:g}, |tilt| <= {a.tilt_max:g}, |lean| <= {a.lean_max:g}" if a.symmetry else "")
              + (f", fringe <= {a.fringe_max:g}%, tint <= {a.tint_max:g}% (key on the rim: re-key the sheet with "
                 f"key_unmix.py, or repair these files with key_unmix.py --defringe)" if key else ""))
        sys.exit(1)
    print("\nOK")


if __name__ == "__main__":
    main()
