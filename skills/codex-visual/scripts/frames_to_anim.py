#!/usr/bin/env python3
"""frames_to_anim.py — equal-size PNG frames -> a playable GIF / APNG / WebP preview.

These are PREVIEW and review formats. Unity cannot play any of them: the game
wants the PNG frames plus an `AnimationClip` (`unity-2d-sprites`). Build these to
show a human the loop, to paste in a review, and to prove the frame order is right.

A preview is for EYES, and it has to be a preview of the thing being judged. A
contact sheet that tiles one frame per cell proves each frame was drawn; it
cannot show what happens BETWEEN frames, so a character that jumps 100 px
sideways on every frame change photographs perfectly in it. Two outputs here do
show it, and they belong beside the numbers `audit_frames.py` prints:

- **`--onion`** — every frame as a flat tint, stacked on one dark ground. A
  sequence in register reads as ONE silhouette with coloured fans where a limb
  moves; one that is not reads as two or more whole bodies side by side.
- **`--bg`** — the frames composited on an opaque ground before encoding. A key
  fringe is invisible over a checkerboard or over white and obvious over a
  mid-tone, so review on `--bg '#808080'` or on the colour the game will put
  behind the sprite, at the real fps.

Three traps decide what you hand over:

- **A preview written next to the frames becomes a frame.** An APNG is a `.png`,
  so `out/idle/idle.png` beside `idle_000.png … idle_015.png` is picked up by the
  next `out/idle/*.png` glob and encoded as a 17th frame — and the read-back line
  merges it into a longer delay instead of complaining. Two guards here: a bare
  `--apng` derives `<stem>_apng.png`, not `<stem>.png`, and any input that is
  itself an animation (`n_frames > 1`) is skipped with a line saying so — an APNG
  written into the frame directory and re-globbed prints
  `skipped …/idle_apng.png animated 16 frames (a preview, not a frame)`, then
  `sequence 16 = stored_frames 16 + merged_into_delays 0`. Still cheaper: write
  previews to a directory that is not the frame directory. When `--out` already
  selects a format, a bare flag for that same format is redundant and says so
  rather than re-deriving the path:
  `--out x.png --apng` writes the `x.png` you asked for, not `x_apng.png`.
- **GIF alpha is one bit.** A pixel is either fully opaque or fully gone, so a
  soft matte — anything with `remove_chroma_key.py --soft-matte`, or an
  anti-aliased edge over the old background colour — leaves a fringe of
  half-keyed pixels that snap to opaque and read as a halo. Key hard for
  GIF-bound frames, or ship APNG/WebP, which carry real 8-bit alpha.
- **GIF delays are centiseconds.** Any fps whose frame time is not a multiple of
  10 ms is rounded down by the encoder, so 10 fps (100 ms) and 20 fps (50 ms)
  survive and 24 fps does not: 41.67 ms is stored as **40 ms** in the GIF and as
  41.667 ms in the APNG, so the same 16 frames run 640 ms instead of 667 ms. Ship
  10/20 fps as GIF, anything else as APNG or WebP.

Frames come from a glob (row-major order is the sort order, so name them
`name_000.png`) or from `--frames-json`, the sidecar `sheet_to_frames.py` writes —
which also carries the fps hint, so `--frames-json` alone is usually enough. All
frames must already be the same size; unequal sizes are an error, not a resize.

Sequence order: frames -> `--reverse-loop` reflection (ping-pong, endpoints not
repeated) -> `--hold-last N` (N extra copies of whatever is then last).

Output is one `wrote` line per file carrying what the file actually stored on
re-open, written as arithmetic that cannot read as a contradiction:
`sequence 34 = stored_frames 30 + merged_into_delays 4`. The GIF and WebP
encoders merge a frame identical to its predecessor into a longer delay on that
predecessor, so a stored count BELOW the sequence is normal for `--hold-last`
and `total_ms` is the number to check. Without `--hold-last`, a merge means two
consecutive INPUTS were identical — a repeated pose, or a file in the glob that
is not a frame — and that gets a WARN rather than a quiet subtraction.

The GIF matte is cut at the alpha threshold `frames.json` records, so the preview
and the measurements agree; with a bare frame glob and no sidecar it falls back
to 16, the slicer's default.

Examples:
  # the common case: sidecar in, three previews out at the recorded fps
  frames_to_anim.py --frames-json out/idle/frames.json --out out/idle/idle.gif --apng --webp

  # explicit frames and fps, one-shot that freezes on the last pose
  frames_to_anim.py out/attack/*.png --fps 12 --loop 0 --hold-last 6 --out out/attack/attack.gif

  # ping-pong idle, and a higher-quality GIF via ffmpeg palettegen/paletteuse
  frames_to_anim.py out/idle/*.png --fps 10 --reverse-loop --out out/idle/idle.gif --ffmpeg /opt/homebrew/bin/ffmpeg

  # lossy WebP when the lossless file is too big for a chat window
  frames_to_anim.py out/idle/*.png --out out/idle/idle.webp --webp-quality 80

  # the review pair: the loop on a mid-tone ground at its real fps, and the onion skin
  frames_to_anim.py --frames-json out/idle/frames.json --bg '#808080' \
      --out review/idle.gif --onion review/idle_onion.png

Exit codes: 0 ok · 1 no usable frames, a missing frame file, frames of unequal
size, an unknown `--out` extension, a bare format flag with no `--out`, two paths
for one format, a non-positive `--fps` / `--duration-ms`, a bad `--bg` colour, or
an `--onion` path inside the frame directory (it is a PNG: the next glob would
take it for a frame, and an importer for a sprite).

Requires Pillow (use codex's imagegen venv: ~/.codex/imagegen-venv/bin/python).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

THR = 16  # alpha above this counts as content (binary GIF matte cut)
EXT = {"gif": ".gif", "apng": "_apng.png", "webp": ".webp"}
ONION_TINTS = [(230, 60, 60), (60, 200, 60), (60, 110, 240), (240, 210, 40), (220, 80, 220), (60, 210, 210)]
ONION_GROUND = (30, 40, 60)


def parse_hex(s):
    s = s.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"not a hex colour: {s!r}")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def onion_skin(ims, pad=12):
    """Every frame as a flat tint at ~37% opacity on one dark ground, cropped to their union.

    In register, the bodies coincide: one silhouette, with coloured fans only where
    something moves. Out of register, whole bodies sit side by side — which no
    single frame, and no sheet of single frames, can show."""
    W, H = ims[0].size
    acc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    box = None
    for i, im in enumerate(ims):
        a = im.getchannel("A")
        bb = a.point(lambda v: 255 if v > THR else 0).getbbox()
        if bb:
            box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]),
                                          max(box[2], bb[2]), max(box[3], bb[3]))
        layer = Image.new("RGBA", (W, H), ONION_TINTS[i % len(ONION_TINTS)] + (0,))
        layer.putalpha(a.point(lambda v: 95 if v > 40 else 0))
        acc.alpha_composite(layer)
    out = Image.new("RGBA", (W, H), ONION_GROUND + (255,))
    out.alpha_composite(acc)
    box = box or (0, 0, W, H)
    box = (max(0, box[0] - pad), max(0, box[1] - pad), min(W, box[2] + pad), min(H, box[3] + pad))
    return out.crop(box).convert("RGB")


def load_json_frames(path):
    """(frame paths, fps hint, alpha threshold) out of a `sheet_to_frames.py` sidecar.

    The threshold comes along because the GIF matte is a one-bit cut and it should
    be made at the same alpha the frames were measured and aligned at — otherwise
    the preview disagrees with the report about where a sprite ends.
    """
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    base = os.path.dirname(os.path.abspath(path))
    out = []
    for f in doc.get("frames", []):
        p = f["file"] if isinstance(f, dict) else f
        out.append(p if os.path.isabs(p) else os.path.join(base, p))
    return out, doc.get("fps_hint"), doc.get("alpha_threshold")


def load_still(path):
    """Open one frame, or return None if the file is itself an animation.

    A GIF/APNG/animated-WebP in the frame list is a preview this script (or a
    previous run) wrote, never a frame: it is the same size as the frames, so the
    equal-size check cannot catch it.
    """
    im = Image.open(path)
    n = getattr(im, "n_frames", 1)
    if n > 1:
        print(f"skipped {path} animated {n} frames (a preview, not a frame)")
        im.close()
        return None
    return im.convert("RGBA")


def to_gif_frame(im):
    """RGBA -> P with a reserved transparent index 255 and a 255-colour local palette.

    GIF has no partial alpha, so the matte is cut at the same threshold the
    measuring tools use: above it opaque, at or below it transparent.
    """
    a = im.getchannel("A")
    p = im.convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT,
                                   dither=Image.Dither.NONE)
    pal = list(p.getpalette() or [])[:765]
    pal += [0] * (765 - len(pal)) + [0, 0, 0]  # index 255 = the transparent slot
    p.putpalette(pal)
    p.paste(255, a.point(lambda v: 255 if v <= THR else 0))
    return p


def build_ffmpeg_gif(ffmpeg, seq_paths, out, fps, loop):
    """Two-pass palette GIF from the PNG frames — one global palette, real alpha cut."""
    tmp = tempfile.mkdtemp(prefix="frames_to_anim_")
    try:
        for i, p in enumerate(seq_paths):
            os.symlink(os.path.abspath(p), os.path.join(tmp, f"f{i:05d}.png"))
        cmd = [ffmpeg, "-y", "-framerate", f"{fps:g}", "-i", os.path.join(tmp, "f%05d.png"),
               "-filter_complex",
               "[0:v]split[a][b];[a]palettegen=reserve_transparent=1:max_colors=255[p];"
               "[b][p]paletteuse=alpha_threshold=128:dither=none",
               "-loop", str(0 if loop == 0 else loop), out]
        print("ffmpeg cmd:", " ".join(cmd))
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"WARN: ffmpeg failed ({r.returncode}); falling back to the Pillow GIF encoder",
                  file=sys.stderr)
            print(r.stderr.strip()[-400:], file=sys.stderr)
            return False
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _webp_frame_durations(path):
    """Per-frame WebP delays, read out of the RIFF ANMF chunk headers.

    Pillow writes them but does not expose them on read (`info["duration"]` is
    absent on an animated WebP), so verification has to go to the bytes.
    """
    with open(path, "rb") as fh:
        b = fh.read()
    i, out = 12, []
    while i + 8 <= len(b):
        tag, size = b[i:i + 4], int.from_bytes(b[i + 4:i + 8], "little")
        if tag == b"ANMF":
            out.append(int.from_bytes(b[i + 20:i + 23], "little"))
        i += 8 + size + (size & 1)
    return out


def verify(path):
    """Reopen an output and read back what it actually stored.

    Frame count can be LOWER than the sequence length: the GIF and WebP encoders
    merge a frame identical to its predecessor into a longer delay on that
    predecessor, so `--hold-last 4` at 10 fps reads back as 16 frames totalling
    2000 ms rather than 20 frames — the APNG keeps all 20. Total duration is the
    number to check, not the count, and the caller prints the two as
    `sequence N = stored_frames X + merged_into_delays Y` so neither number can be
    read as contradicting the other.
    """
    with Image.open(path) as im:
        n = getattr(im, "n_frames", 1)
        loop = im.info.get("loop")
        durs = []
        for i in range(n):
            im.seek(i)
            durs.append(im.info.get("duration") or 0)
    if not any(durs) and os.path.splitext(path)[1].lower() == ".webp":
        w = _webp_frame_durations(path)
        if w:
            durs, n = w, len(w)
    return n, sum(durs), (durs[0] if durs else 0), loop


def main():
    ap = argparse.ArgumentParser(description="Turn equal-size PNG frames into GIF / APNG / WebP.")
    ap.add_argument("frames", nargs="*", help="frame PNGs (shell glob; sorted by name)")
    ap.add_argument("--frames-json", help="sidecar written by sheet_to_frames.py (supplies frames + fps hint)")
    ap.add_argument("--out", help="primary output; its extension picks the format (.gif/.png/.apng/.webp)")
    ap.add_argument("--gif", nargs="?", const=True, metavar="PATH",
                    help="also write a GIF (bare flag = --out's stem + .gif)")
    ap.add_argument("--apng", nargs="?", const=True, metavar="PATH",
                    help="also write an APNG (bare flag = --out's stem + _apng.png, which a frame "
                         "glob will not pick up as a frame)")
    ap.add_argument("--webp", nargs="?", const=True, metavar="PATH",
                    help="also write a WebP (bare flag = --out's stem + .webp)")
    ap.add_argument("--fps", type=float, help="frames per second (default 10, or the sidecar's fps hint)")
    ap.add_argument("--duration-ms", type=float, help="per-frame delay in ms; overrides --fps")
    ap.add_argument("--loop", type=int, default=0, help="loop count, 0 = forever (default 0)")
    ap.add_argument("--hold-last", type=int, default=0, metavar="N",
                    help="repeat the last frame N extra times (one-shot animations)")
    ap.add_argument("--reverse-loop", action="store_true", help="ping-pong: append the reflection")
    ap.add_argument("--webp-quality", type=int, help="lossy WebP at this quality (default lossless)")
    ap.add_argument("--gif-optimize", action="store_true", help="Pillow GIF optimize (off by default)")
    ap.add_argument("--ffmpeg", help="path to ffmpeg; builds the GIF via palettegen/paletteuse instead "
                                     "— one global palette and inter-frame diffing, for a better, smaller file")
    ap.add_argument("--bg", metavar="HEX",
                    help="composite every frame on this opaque colour before encoding — review a cut-out on a "
                         "mid-tone ('#808080') or on the game's own ground, where a key fringe shows")
    ap.add_argument("--onion", nargs="?", const=True, metavar="PATH",
                    help="also write an onion skin: every frame as a flat tint, stacked (bare flag = --out's "
                         "stem + _onion.png). Must not land in the frame directory")
    a = ap.parse_args()

    bg = None
    if a.bg:
        try:
            bg = parse_hex(a.bg)
        except ValueError as e:
            print(f"ERROR: --bg: {e}", file=sys.stderr)
            return 1

    # 0 and a negative rate are arguments, not omissions: `if a.fps` read both as
    # "not supplied" and fell back to 10 fps, and a negative --fps reached the
    # encoders as a negative delay
    if a.fps is not None and a.fps <= 0:
        print(f"ERROR: --fps {a.fps:g} must be greater than 0", file=sys.stderr)
        return 1
    if a.duration_ms is not None and a.duration_ms <= 0:
        print(f"ERROR: --duration-ms {a.duration_ms:g} must be greater than 0", file=sys.stderr)
        return 1

    # sidecar order is authoritative; a bare glob is sorted by name
    paths, hint = [], None
    if a.frames_json:
        global THR
        paths, hint, thr = load_json_frames(a.frames_json)
        if isinstance(thr, int) and 0 <= thr <= 254 and thr != THR:
            THR = thr
            print(f"gif_matte_alpha_threshold {THR} (from {a.frames_json})")
    paths = list(dict.fromkeys(paths + sorted(a.frames)))
    if not paths:
        print("ERROR: no frames — pass PNG paths or --frames-json", file=sys.stderr)
        return 1
    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        print(f"ERROR: missing frame files: {missing[:3]}", file=sys.stderr)
        return 1

    if hint is not None and hint <= 0:
        print(f"WARN: ignoring the sidecar's fps_hint {hint:g} — not a positive rate")
        hint = None
    fps = a.fps if a.fps is not None else (hint if hint else 10.0)
    dur = a.duration_ms if a.duration_ms is not None else 1000.0 / fps
    if a.duration_ms is not None:
        fps = 1000.0 / a.duration_ms

    kept, ims = [], []
    for p in paths:
        im = load_still(p)
        if im is None:
            continue
        kept.append(p)
        ims.append(im)
    paths = kept
    if not paths:
        print("ERROR: no still frames left — every input was itself an animation", file=sys.stderr)
        return 1
    sizes = {im.size for im in ims}
    if len(sizes) != 1:
        print(f"ERROR: frames are not all the same size: {sorted(sizes)[:4]} — "
              f"re-slice with sheet_to_frames.py --canvas W H", file=sys.stderr)
        return 1

    onion_path = None
    if a.onion:
        if a.onion is True and not a.out:
            print("ERROR: bare --onion needs --out to derive a path from", file=sys.stderr)
            return 1
        onion_path = os.path.splitext(a.out)[0] + "_onion.png" if a.onion is True else a.onion
        frame_dirs = {os.path.dirname(os.path.abspath(p)) for p in paths}
        if os.path.dirname(os.path.abspath(onion_path)) in frame_dirs:
            print(f"ERROR: --onion {onion_path} would land in the frame directory. It is a PNG: the next "
                  f"frame glob takes it for a frame and an engine importer for a sprite. Write it elsewhere.",
                  file=sys.stderr)
            return 1
    onion = onion_skin(ims) if onion_path else None     # from the frames as delivered, before --bg

    if bg is not None:
        flat = []
        for im in ims:
            ground = Image.new("RGBA", im.size, bg + (255,))
            ground.alpha_composite(im)
            flat.append(ground)
        ims = flat
        if a.ffmpeg:
            print("note --bg composites in Pillow, so --ffmpeg is not used for the GIF")

    seq, seq_paths = list(ims), list(paths)
    if a.reverse_loop and len(seq) > 2:
        seq += seq[-2:0:-1]
        seq_paths += seq_paths[-2:0:-1]
    if a.hold_last > 0:
        seq += [seq[-1]] * a.hold_last
        seq_paths += [seq_paths[-1]] * a.hold_last

    targets = {}
    if a.out:
        ext = os.path.splitext(a.out)[1].lower()
        fmt = {".gif": "gif", ".png": "apng", ".apng": "apng", ".webp": "webp"}.get(ext)
        if not fmt:
            print(f"ERROR: --out extension {ext!r} is not .gif/.png/.apng/.webp", file=sys.stderr)
            return 1
        targets[fmt] = a.out
    for fmt in ("gif", "apng", "webp"):
        v = getattr(a, fmt)
        if v is None:
            continue
        if v is True:
            if not a.out:
                print(f"ERROR: bare --{fmt} needs --out to derive a path from", file=sys.stderr)
                return 1
            if fmt in targets:
                # --out's own extension already picked this format; deriving a
                # second path here would leave the file the user named unwritten
                print(f"note --{fmt} is redundant — --out {a.out} already writes the {fmt}")
                continue
            targets[fmt] = os.path.splitext(a.out)[0] + EXT[fmt]
        else:
            if fmt in targets and os.path.abspath(v) != os.path.abspath(targets[fmt]):
                print(f"ERROR: --out {targets[fmt]} and --{fmt} {v} are two paths for one "
                      f"format — pass one of them", file=sys.stderr)
                return 1
            targets[fmt] = v
    if not targets and not onion_path:
        print("ERROR: nothing to write — pass --out and/or --gif/--apng/--webp (or --onion PATH)",
              file=sys.stderr)
        return 1

    for p in targets.values():
        d = os.path.dirname(os.path.abspath(p))
        os.makedirs(d, exist_ok=True)

    W, H = seq[0].size
    print(f"frames {len(paths)} size {W}x{H} sequence {len(seq)} "
          f"reverse_loop {'yes' if a.reverse_loop else 'no'} hold_last {a.hold_last}")
    print(f"timing fps {fps:g} per_frame_ms {dur:.2f} loop {a.loop} "
          f"({'forever' if a.loop == 0 else 'times'})"
          + (f" bg #{bg[0]:02x}{bg[1]:02x}{bg[2]:02x}" if bg is not None else ""))
    if onion_path:
        os.makedirs(os.path.dirname(os.path.abspath(onion_path)), exist_ok=True)
        onion.save(onion_path)
        print(f"wrote {onion_path} onion frames {len(paths)} size {onion.width}x{onion.height} — one "
              f"silhouette = in register; doubled bodies = the frames jump")

    if "gif" in targets:
        out = targets["gif"]
        done = build_ffmpeg_gif(a.ffmpeg, seq_paths, out, fps, a.loop) if (a.ffmpeg and bg is None) else False
        if not done:
            gseq = [to_gif_frame(im) for im in seq]
            gseq[0].save(out, save_all=True, append_images=gseq[1:], duration=dur,
                         loop=a.loop, disposal=2, transparency=255, optimize=a.gif_optimize)
    if "apng" in targets:
        seq[0].save(targets["apng"], format="PNG", save_all=True, append_images=seq[1:],
                    duration=dur, loop=a.loop, disposal=1, blend=0)
    if "webp" in targets:
        kw = dict(lossless=True) if a.webp_quality is None else dict(lossless=False, quality=a.webp_quality)
        seq[0].save(targets["webp"], format="WEBP", save_all=True, append_images=seq[1:],
                    duration=int(round(dur)), loop=a.loop, minimize_size=False, **kw)

    for fmt in ("gif", "apng", "webp"):
        if fmt not in targets:
            continue
        p = targets[fmt]
        n, total, first, loop = verify(p)
        merged = len(seq) - n
        # One line, stated as arithmetic: a stored count under the sequence is the
        # encoder merging identical neighbours, not a lost frame.
        print(f"wrote {p} format {fmt} bytes {os.path.getsize(p)} "
              f"sequence {len(seq)} = stored_frames {n} + merged_into_delays {merged} "
              f"first_delay_ms {first:g} total_ms {total:g} loop {loop}")
        if merged > 0 and a.hold_last == 0:
            print(f"WARN: {p} merged {merged} frame(s) although no --hold-last was asked for — two "
                  f"consecutive inputs are pixel-identical. That is a repeated pose in the sheet, or "
                  f"a file in the glob that is not one of these frames; check the frame list above.",
                  file=sys.stderr)
        elif merged < 0:
            print(f"WARN: {p} read back MORE frames than were sent ({n} > {len(seq)}) — the file was "
                  f"not written by this run", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
