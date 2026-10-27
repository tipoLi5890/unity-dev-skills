#!/usr/bin/env python3
"""video_canvas.py — pad a base still into the canvas a motion state needs, on the exact key.

An image-to-video model keeps the input image's framing, so the room a motion
needs is decided here, on the still: a jump needs head-room above (tall), an
attack room above and in front (wide), a projectile room in front, everything
else stays square. The state table below is the one owner of that rule;
--shape overrides it (a walk or run forced wide gets room in front and behind
and none above — its feet stay on the ground).

  state                 shape   ratio  headroom lead  trail
  jump, land            tall    3:4    0.34     -     -
  attack                wide    16:9   0.20     0.28  0.20
  projectile            wide    16:9   -        0.34  -
  cheer, wave, celebrate wide   16:9   -        0.30  -
  death, fall, hurt_hold wide   16:9   0.10     0.32  0.32
  cast, transform       wide    16:9   0.25     0.25  0.25
  idle, walk, run, other square 1:1    -        -     -
  --shape wide (walk/run)       16:9   -        0.28  0.20
  --shape wide (other)          16:9   0.35     0.28  0.20
  --shape tall                  as jump

headroom is the empty share of the canvas height above the still, lead / trail
the empty share of its width in front of / behind the subject (--facing). The
still is pasted at the bottom, so the feet stay on the floor of the clip.

The field. An image model paints "#00FF00" a little off every time and the video
model reproduces the input colour almost exactly, so the still's field is
repainted to the exact declared key first (`normalize_key`): every pixel the
chroma_unmix keyer erases (alpha 0) becomes the pure key, the subject and its
un-mixed rim stay byte-identical, and the padding is that same key. Refused:
corners that disagree by more than 24 in a channel (a field that is not flat
cannot be extended), corners that are no chroma key, and a corner the keyer
would not erase.

The size. The video model takes a width and a height that are multiples of 16.
The frame is --long-side (768) on its long side and the multiple of 16 nearest
the composed canvas's ratio on the other; the composed canvas is scaled
(LANCZOS, once) to fit inside it, the rest is key (extra rows above, extra
columns split evenly), and the result is normalised once more so the field is
exact key wherever video_frames.py will erase. A square, tall and wide
row land on 768x768, 576x768 and 768x432.

stdout: one JSON object (canvas, scale, placement, key, normalised pixels and
`comfy_set`, the arguments for comfyui-asset-generation's comfy_asset_client.py,
e.g. `--set 7.width=576 --set 7.height=768`); stderr repeats that --set line on
its own, ready to paste.

Examples
  video_canvas.py refs/runner_still.png --state walk --out work/runner_walk_canvas.png
  video_canvas.py refs/runner_still.png --state jump --out work/runner_launch_canvas.png
  video_canvas.py refs/sentry_still.png --state attack --facing left --out work/sentry_attack_canvas.png
  video_canvas.py --selftest

Exit codes
  0  canvas written (or --selftest passed)
  1  bad arguments, unreadable still, an unknown state for --shape, or a failed --selftest
  2  the still's corners are not one flat colour (spread over 24 in a channel)
  3  the corners are not the chroma key, or a corner survives the key: the
     field is not one the keyer can cut (pick a key with codex-visual
     pick_key.py and regenerate the still on it)

Requires numpy and Pillow (~/.codex/imagegen-venv/bin/python); imports
video_frames.py from this directory for the keyer.
"""
# ---------------------------------------------------------------------------
# Third-party code. Portions are ported, with identifiers and structure
# adapted, from sprite-gen
#   https://github.com/aldegad/sprite-gen
#   commit dddcc1013f7b5587a5eabd8609a5b42dd8aa7c26
#   Apache License 2.0 — see THIRD_PARTY_NOTICES.md.
#
#   video/canvas.py  CanvasProfile, STATE_CANVAS, WIDE_OVERRIDE, GAIT_WIDE,
#                    STATE_SHAPE_CANVAS, SHAPE_DEFAULTS, CORNER_TOLERANCE,
#                    profile_for, corner_key, resolve_key, normalize_key and
#                    the square/tall/wide placement of pad_canvas
#
# Changes: the keyer is the chroma_unmix block (video_frames.py) instead of
# sprite-gen's cutout route; resolve_key reads the corner against magenta,
# green, cyan and blue and refuses a non-key (white) base instead of padding it
# with the corner colour; the composed canvas is scaled to --long-side, rounded
# up to multiples of 16 and normalised again; --fit tight and the effect state
# are not carried; refusals exit 2/3 instead of raising SystemExit.
# ---------------------------------------------------------------------------
import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import video_frames as vf  # noqa: E402  (the keyer: the chroma_unmix block)

SQUARE, TALL, WIDE = "square", "tall", "wide"
SHAPES = (SQUARE, TALL, WIDE)
CORNER_TOLERANCE = 24   # max per-channel spread across the four corners of a flat field
LONG_SIDE = 768         # the canvas's long side after scaling
MULTIPLE = 16           # the video model's width/height step


@dataclass(frozen=True)
class CanvasProfile:
    shape: str
    ratio: float      # width / height
    headroom: float   # empty share of the canvas height above the still
    lead: float       # empty share of the canvas width in front of the subject
    trail: float      # empty share of the canvas width behind it
    why: str


STATE_CANVAS = {
    "jump": CanvasProfile(TALL, 3 / 4, 0.34, 0.0, 0.0, "airborne frames need head-room"),
    "attack": CanvasProfile(WIDE, 16 / 9, 0.20, 0.28, 0.2, "a weapon raised overhead needs room above, a swing "
                            "extends in front, and a long weapon drawn back reaches behind"),
    "projectile": CanvasProfile(WIDE, 16 / 9, 0.0, 0.34, 0.0, "the projectile travels away from the body"),
    "cheer": CanvasProfile(WIDE, 16 / 9, 0.0, 0.30, 0.0, "arms raised and spread leave a 1:1 frame"),
    "wave": CanvasProfile(WIDE, 16 / 9, 0.0, 0.30, 0.0, "a raised waving arm leaves a 1:1 frame"),
    "celebrate": CanvasProfile(WIDE, 16 / 9, 0.0, 0.30, 0.0, "same envelope as cheer"),
    "death": CanvasProfile(WIDE, 16 / 9, 0.1, 0.32, 0.32, "room for the terminal pose"),
    "fall": CanvasProfile(WIDE, 16 / 9, 0.1, 0.32, 0.32, "room for the terminal pose"),
    "land": CanvasProfile(TALL, 3 / 4, 0.34, 0.0, 0.0, "room for the landing"),
    "cast": CanvasProfile(WIDE, 16 / 9, 0.25, 0.25, 0.25, "room for the cast"),
    "hurt_hold": CanvasProfile(WIDE, 16 / 9, 0.1, 0.32, 0.32, "room for the terminal pose"),
    "transform": CanvasProfile(WIDE, 16 / 9, 0.25, 0.25, 0.25, "room for the transform"),
    "default": CanvasProfile(SQUARE, 1.0, 0.0, 0.0, 0.0, "in-place motion fits the still's own frame"),
}
WIDE_OVERRIDE = CanvasProfile(WIDE, 16 / 9, 0.35, 0.28, 0.2, "forced wide: room in front and behind, and a "
                              "jump's head-room above, whatever the state")
GAIT_WIDE = CanvasProfile(WIDE, 16 / 9, 0.0, 0.28, 0.2, "forced wide for a walk or run: room in front and "
                          "behind, none above — its feet stay on the ground")
STATE_SHAPE_CANVAS = {("walk", WIDE): GAIT_WIDE, ("run", WIDE): GAIT_WIDE}
SHAPE_DEFAULTS = {SQUARE: STATE_CANVAS["default"], TALL: STATE_CANVAS["jump"], WIDE: WIDE_OVERRIDE}


class Refused(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def profile_for(state, shape=None):
    """An explicit shape wins (the state's own row for it, else the shape's default); else the state's row."""
    key = (state or "").strip().lower()
    if shape is not None:
        if shape not in SHAPES:
            raise Refused(1, f"unknown --shape {shape!r}; expected one of {', '.join(SHAPES)}")
        return STATE_SHAPE_CANVAS.get((key, shape), SHAPE_DEFAULTS[shape])
    return STATE_CANVAS.get(key, STATE_CANVAS["default"])


def corner_key(rgb):
    """The still's flat field colour from its four corners; refuses a non-flat one (exit 2)."""
    h, w = rgb.shape[:2]
    corners = [tuple(int(v) for v in rgb[y, x]) for y, x in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1))]
    for ch in range(3):
        vals = [c[ch] for c in corners]
        if max(vals) - min(vals) > CORNER_TOLERANCE:
            raise Refused(2, f"the still's corners are not one flat colour ({corners}); generate the base on a "
                             "flat chroma key before padding it")
    return tuple(round(sum(c[i] for c in corners) / 4) for i in range(3))


def resolve_key(corner, key):
    """The declared key the corners are: `key` given -> checked; 'auto' -> the first of magenta, green, cyan,
    blue whose hue signature the corner carries. Refuses (exit 3) a corner that is none of them."""
    cand = vf._border_candidate_field
    rgb = np.asarray([corner], np.int32)
    if key != "auto":
        k = vf.parse_key(key)
        keyed, unkeyed = vf.key_channel_split(k)
        if not keyed or not cand(rgb, keyed, unkeyed)[0]:
            raise Refused(3, f"--key {key} but the still's corners are {corner}, not that key's colour; pass "
                             "--key auto to let the corners decide")
        return k
    for name, k in vf.KEY_NAMES.items():
        keyed, unkeyed = vf.key_channel_split(k)
        if cand(rgb, keyed, unkeyed)[0]:
            return k
    raise Refused(3, f"the still's corners {corner} are no chroma key (magenta, green, cyan, blue); pick one with "
                     "codex-visual pick_key.py and regenerate the base on it")


def normalize_key(rgb, key):
    """Repaint every pixel the keyer erases to the exact `key` -> (rgb, painted key, pixels repainted).
    The subject, its un-mixed rim included, is byte-identical. Refuses (exit 3) when a corner survives."""
    rgba, st = vf.key_tint_unmix(rgb, key)
    erased = rgba[..., 3] == 0
    h, w = erased.shape
    if not all(erased[y, x] for y, x in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1))):
        raise Refused(3, f"the still's corners survive the {vf.hexrgb(key)} key (painted "
                         f"{tuple(st['painted_key'])}); the field is not a key the keyer can cut")
    out = rgb.copy()
    out[erased] = key
    return out, tuple(st["painted_key"]), int(erased.sum())


def place(w, h, profile, facing, head, front, back):
    """sprite-gen's pad_canvas placement in still pixels -> (canvas_w, canvas_h, x, y)."""
    if profile.shape == SQUARE:
        side = max(w, h)
        return side, side, (side - w) // 2, side - h
    if profile.shape == TALL:
        ch = max(h, round(h / (1 - head)), round(w / profile.ratio))
        cw = max(w, round(ch * profile.ratio))
        return cw, ch, (cw - w) // 2, ch - h
    need_h = max(h, round(h / (1 - head)))
    cw = max(w, round(w / (1 - front - back)), round(need_h * profile.ratio))
    ch = max(h, round(cw / profile.ratio))
    behind = min(round(cw * back), cw - w)
    return cw, ch, (behind if facing == "right" else cw - w - behind), ch - h


def make_canvas(rgb, *, state=None, shape=None, facing="right", headroom=None, lead=None, trail=None,
                key="auto", long_side=LONG_SIDE, multiple=MULTIPLE):
    """-> (canvas uint8 HxWx3, report dict). Raises Refused."""
    profile = profile_for(state, shape)
    head = profile.headroom if headroom is None else headroom
    front = profile.lead if lead is None else lead
    back = profile.trail if trail is None else trail
    if not (0 <= head < 0.9 and 0 <= front < 0.9 and 0 <= back < 0.9 and front + back < 0.9):
        raise Refused(1, "--headroom/--lead/--trail must be in [0, 0.9) and lead + trail below 0.9")
    if long_side < multiple or long_side % multiple:
        raise Refused(1, f"--long-side must be a positive multiple of {multiple}")
    corner = corner_key(rgb)
    k = resolve_key(corner, key)
    src, painted, normalised = normalize_key(rgb, k)
    h, w = src.shape[:2]
    cw, ch, x, y = place(w, h, profile, facing, head, front, back)
    canvas = np.empty((ch, cw, 3), np.uint8)
    canvas[:] = k
    canvas[y:y + h, x:x + w] = src
    # the frame first: long side exact, short side the nearest multiple; then the canvas fits inside it
    if cw >= ch:
        fw, fh = long_side, max(multiple, round(long_side * ch / cw / multiple) * multiple)
    else:
        fw, fh = max(multiple, round(long_side * cw / ch / multiple) * multiple), long_side
    scale = min(fw / cw, fh / ch)
    sw, sh = min(fw, max(1, round(cw * scale))), min(fh, max(1, round(ch * scale)))
    im = Image.fromarray(canvas, "RGB")
    if (sw, sh) != (cw, ch):
        im = im.resize((sw, sh), Image.LANCZOS)
    final = np.empty((fh, fw, 3), np.uint8)
    final[:] = k
    ox, oy = (fw - sw) // 2, fh - sh
    final[oy:oy + sh, ox:ox + sw] = np.asarray(im)
    final, _, renormalised = normalize_key(final, k)
    still_box = [ox + round(x * scale), oy + round(y * scale), ox + round((x + w) * scale), oy + round((y + h) * scale)]
    report = {
        "state": state, "shape": profile.shape, "why": profile.why,
        "headroom": head, "lead": front, "trail": back, "facing": facing,
        "still_px": [w, h], "composed": [cw, ch], "offset": [x, y],
        "scale": round(scale, 6), "canvas": [fw, fh], "still_box": still_box,
        "key": vf.hexrgb(k), "key_rgb": list(k), "corner_rgb": list(corner), "painted_rgb": list(painted),
        "off_by": round(float(np.linalg.norm(np.subtract(painted, k))), 2),
        "normalized_px": normalised, "normalized_pct": round(100 * normalised / (w * h), 2),
        "renormalized_px": renormalised,
        "comfy_set": f"--set 7.width={fw} --set 7.height={fh}",
    }
    return final, report


def run(still, out, **kw):
    try:
        rgb = np.asarray(Image.open(still).convert("RGB"))
    except (OSError, ValueError) as exc:
        return 1, {"ok": False, "error": f"cannot read {still}: {exc}"}
    try:
        canvas, report = make_canvas(rgb, **kw)
    except Refused as exc:
        return exc.code, {"ok": False, "error": str(exc)}
    except ValueError as exc:
        return 1, {"ok": False, "error": str(exc)}
    try:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(canvas, "RGB").save(out)
    except OSError as exc:
        return 1, {"ok": False, "error": f"cannot write {out}: {exc}"}
    return 0, {"ok": True, "still": str(Path(still).resolve()), "out": str(Path(out).resolve()), **report}


# ----------------------------------------------------------------- selftest ----

def _still(w=200, h=260, field=(10, 240, 12), seed=1):
    rng = np.random.default_rng(seed)
    img = np.empty((h, w, 3), np.int32)
    img[:] = field
    img += rng.integers(-2, 3, (h, w, 3))
    img[60:h - 10, 70:130] = (190, 50, 40)       # body
    img[30:60, 85:115] = (235, 195, 160)         # head
    img[h - 16:h - 10, 60:140] = (35, 30, 30)    # feet
    return np.clip(img, 0, 255).astype(np.uint8)


def selftest():
    checks = []
    still = _still()
    sq, r = make_canvas(still, state="walk")
    checks.append(("square walk -> 768x768", r["canvas"] == [768, 768] and r["shape"] == SQUARE))
    corners = [tuple(sq[y, x]) for y, x in ((0, 0), (0, -1), (-1, 0), (-1, -1))]
    checks.append(("corners exact key", all(c == (0, 255, 0) for c in corners)))
    rows = np.flatnonzero((np.abs(sq.astype(int) - (0, 255, 0)).max(axis=2) > 0).any(axis=1))
    checks.append(("feet on the floor", sq.shape[0] - 1 - rows[-1] <= round(10 * 768 / 260) + 2))
    checks.append(("field fully normalised", float((np.abs(sq.astype(int) - (0, 255, 0)).max(axis=2) == 0).mean()) > 0.6))
    checks.append(("--set args", r["comfy_set"] == "--set 7.width=768 --set 7.height=768"))
    tall, r = make_canvas(still, state="jump")
    checks.append(("jump -> tall 3:4, 576x768", r["canvas"] == [576, 768] and r["shape"] == TALL))
    top = r["still_box"][1] / r["canvas"][1]
    checks.append(("jump head-room ~0.34", abs(top - 0.34) < 0.02))
    wide, r = make_canvas(still, state="attack", facing="right")
    checks.append(("attack -> wide 768x432", r["canvas"] == [768, 432]))
    checks.append(("attack trail behind (left), lead in front", r["still_box"][0] < r["canvas"][0] - r["still_box"][2]))
    _, r = make_canvas(still, state="run", shape=WIDE)
    checks.append(("run forced wide has no head-room", r["headroom"] == 0.0 and r["lead"] == 0.28))
    _, r = make_canvas(still, state="idle", shape=WIDE)
    checks.append(("idle forced wide takes the override", r["headroom"] == 0.35))
    odd, r = make_canvas(_still(w=213, h=301), state="walk", long_side=640)
    checks.append(("multiples of 16", all(v % 16 == 0 for v in r["canvas"]) and max(r["canvas"]) == 640))
    # the subject is byte-identical after normalisation at source size
    norm, painted, n = normalize_key(still, (0, 255, 0))
    keep = (norm != (0, 255, 0)).any(axis=2)
    checks.append(("subject bytes unchanged", np.array_equal(norm[keep], still[keep]) and n > 0
                   and abs(painted[1] - 240) <= 4))
    bad = still.copy()
    bad[-1, -1] = (200, 200, 200)
    try:
        make_canvas(bad)
        checks.append(("non-flat corners refused", False))
    except Refused as exc:
        checks.append(("non-flat corners refused (2)", exc.code == 2))
    white = np.full((100, 80, 3), 245, np.uint8)
    white[40:90, 30:50] = (120, 40, 40)
    try:
        make_canvas(white)
        checks.append(("white base refused", False))
    except Refused as exc:
        checks.append(("white base refused (3)", exc.code == 3))
    mag = _still(field=(250, 6, 247))
    _, r = make_canvas(mag)
    checks.append(("auto reads magenta", r["key"] == "#ff00ff"))
    try:
        make_canvas(mag, key="green")
        checks.append(("wrong --key refused", False))
    except Refused as exc:
        checks.append(("wrong --key refused (3)", exc.code == 3))
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "s.png")
        Image.fromarray(still).save(p)
        code, rep = run(p, os.path.join(tmp, "o", "c.png"), state="jump")
        checks.append(("run writes the PNG", code == 0 and Image.open(rep["out"]).size == (576, 768)))
        code, _ = run(os.path.join(tmp, "nope.png"), os.path.join(tmp, "c.png"))
        checks.append(("unreadable still -> 1", code == 1))
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
    ap = ArgParser(description="Pad a base still into the canvas a motion state needs, on the exact "
                                             "key, at a size the video model takes.")
    ap.add_argument("still", help="the base still on a flat chroma field")
    ap.add_argument("--out", required=True, help="the padded PNG to hand the video model")
    ap.add_argument("--state", help="motion state: jump, attack, projectile, cheer, wave, celebrate, death, fall, "
                                    "land, cast, hurt_hold, transform; anything else (idle, walk, run) is square")
    ap.add_argument("--shape", choices=SHAPES, help="override the state's shape")
    ap.add_argument("--facing", choices=("right", "left"), default="right", help="which way the subject faces")
    ap.add_argument("--headroom", type=float, help="empty share of the canvas height above the still")
    ap.add_argument("--lead", type=float, help="wide: empty share of the width in front of the subject")
    ap.add_argument("--trail", type=float, help="wide: empty share of the width behind the subject")
    ap.add_argument("--key", default="auto", help="auto (default: the corners decide), green, magenta, cyan, blue "
                                                  "or #rrggbb")
    ap.add_argument("--long-side", type=int, default=LONG_SIDE, help=f"canvas long side, a multiple of {MULTIPLE} "
                                                                     f"(default {LONG_SIDE})")
    args = ap.parse_args(argv)
    code, rep = run(args.still, args.out, state=args.state, shape=args.shape, facing=args.facing,
                    headroom=args.headroom, lead=args.lead, trail=args.trail, key=args.key,
                    long_side=args.long_side)
    print(json.dumps(rep, indent=2))
    if code:
        print(f"FAIL {rep['error']}", file=sys.stderr)
    else:
        print(rep["comfy_set"], file=sys.stderr)
    return code


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    sys.exit(main())
