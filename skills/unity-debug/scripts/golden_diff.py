#!/usr/bin/env python3
"""golden_diff.py — judge this run's screenshots against baselines somebody accepted.

A golden image is a screenshot that was looked at and recorded on purpose. This
compares every PNG under BASELINE_DIR with the PNG at the same relative path
under CURRENT_DIR and judges each on three numbers, because each catches a
shape of change the other two let through:

  d        per-pixel difference: the largest |baseline - current| over R, G, B,
           0-255. Alpha is dropped: a screenshot's alpha is not what the player sees.
  mean     mean d over the compared pixels.          fails above --mean (2.0)
           a faint change everywhere: exposure, a colour grade, a tint.
  p99      99th percentile of d.                     fails above --p99 (24)
           a moderate change over more than 1% of the frame.
  changed  share of pixels with d above --delta (48). fails above --changed (0.005)
           a strong change too small for p99: an icon gone, a label moved.

--delta must sit above --p99. At or below it, every p99 failure is also a
`changed` failure and the p99 gate never fires on its own; the script warns.

Masks. A region allowed to change (a lap timer, particles) leaves all three
numbers: its pixels are dropped from the denominator, not counted as equal.
Masks live in a JSON file, by default BASELINE_DIR/masks.json:

  {
    "*":               [[0, 0, 160, 40]],
    "05_run_hud.png":  [[1680, 24, 1880, 88]],
    "07_launch.png":   [{"box": [600, 300, 1320, 700], "why": "launch trail particles"}]
  }

A key is a relative path, a file name or an fnmatch pattern; every matching key
applies. A box is [x0, y0, x1, y1] in image pixels, top-left origin, x1 and y1
exclusive: the box PIL's crop() takes. A box outside the image was drawn for
another resolution, so the file is not compared.

[SHOT] lines (--shots LOG). The capture logs `[SHOT] <name> key=value ...` per
image. --record writes the pairs of each recorded image to BASELINE_DIR/shots.txt.
A comparison then requires every pair the baseline recorded to match this run's
line for the same name (the file name without .png); otherwise the two images
are not of the same moment and are not compared. Under --shots, an image with no
[SHOT] line, or with two in one log, is not compared either.

--record copies CURRENT_DIR's PNGs (all, or the --only ones) into BASELINE_DIR
and exits 0 listing what it wrote and how far each replaced file had moved. It
never writes masks.json and merges shots.txt by name. It refuses, writing
nothing, when there is nothing to record or a [SHOT] line is missing or doubled.
Recording is the act of accepting an image: do it after looking at the image
and its heatmap, never to turn a red run green.

--heatmap-dir DIR writes <name>.diff.png per compared image: d x 4 in grey
(black = equal, white = changed), masks outlined blue, the box around the
changed pixels outlined red. Old *.diff.png files in DIR are deleted first.

Output: one line per image, then

  [GOLDEN] files=N passed=N failed=N missing=N extra=N invalid=N verdict=green|failed|harness

Exit codes
  0  every baseline has a current image within all three thresholds; current
     images with no baseline are listed as EXTRA and not judged
  2  at least one image exceeded a threshold: a real verdict, do not retry
  3  the harness failed and nothing was verified: no baselines, a baseline with
     no current image, a size mismatch, a [SHOT] mismatch, a stale or unreadable
     file, a bad mask, BASELINE_DIR = CURRENT_DIR, bad arguments, no Pillow.
     3 wins over 2: a set with a hole in it is not a verdict.

Examples
  golden_diff.py Goldens/osx-metal /tmp/shots --shots /tmp/tests.log --record
  golden_diff.py Goldens/osx-metal /tmp/shots --shots /tmp/tests.log \\
      --since "$START" --heatmap-dir /tmp/heat
  golden_diff.py Goldens/osx-metal /tmp/shots --shots /tmp/tests.log \\
      --record --only 05_run_hud

Python 3 standard library plus Pillow.
"""
import argparse
import fnmatch
import json
import os
import re
import shutil
import sys

PASS, FAIL, HARNESS = 0, 2, 3
COUNT_KEYS = ("files", "passed", "failed", "missing", "extra", "invalid")


def summary(counts=None, verdict="harness"):
    counts = counts or {}
    print("[GOLDEN] " + " ".join("%s=%d" % (k, counts.get(k, 0)) for k in COUNT_KEYS)
          + " verdict=" + verdict)


def harness_exit(message, counts=None):
    sys.stdout.flush()
    print("golden_diff: " + message, file=sys.stderr)
    summary(counts, "harness")
    sys.exit(HARNESS)


try:
    from PIL import Image, ImageChops, ImageDraw
except ImportError:
    harness_exit("needs Pillow (python3 -m pip install Pillow); nothing was compared")


class Parser(argparse.ArgumentParser):
    """argparse exits 2 on a bad argument, and 2 here means "the images differ"."""

    def error(self, message):
        self.print_usage(sys.stderr)
        harness_exit("bad arguments: " + message)


# ---------------------------------------------------------------- inputs


def list_pngs(root):
    """Relative POSIX paths of every *.png under root, sorted; hidden dirs skipped."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fn in filenames:
            if fn.lower().endswith(".png"):
                found.append(os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/"))
    return sorted(found)


def shot_name(rel):
    base = rel.rsplit("/", 1)[-1]
    return base[:-4] if base.lower().endswith(".png") else base


def only_patterns(values):
    pats = []
    for value in values or []:
        for tok in value.split(","):
            tok = tok.strip()
            if tok:
                pats.append(tok if tok.lower().endswith(".png") else tok + ".png")
    return pats


def matches(rel, pattern):
    return fnmatch.fnmatchcase(rel, pattern) or fnmatch.fnmatchcase(rel.rsplit("/", 1)[-1], pattern)


def apply_only(rels, pats, used):
    if not pats:
        return rels
    kept = []
    for rel in rels:
        hit = [p for p in pats if matches(rel, p)]
        used.update(hit)
        if hit:
            kept.append(rel)
    return kept


def load_masks(path):
    """[(key, [((x0, y0, x1, y1), why), ...]), ...] from a masks JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("the top level must be an object: {\"name.png\": [[x0, y0, x1, y1], ...]}")
    masks = []
    for key, entries in data.items():
        if not isinstance(entries, list):
            raise ValueError("%s: expected a list of boxes, got %r" % (key, entries))
        boxes = []
        for entry in entries:
            why = ""
            if isinstance(entry, dict):
                why = str(entry.get("why", ""))
                entry = entry.get("box")
            if not (isinstance(entry, list) and len(entry) == 4
                    and all(isinstance(v, int) and not isinstance(v, bool) for v in entry)):
                raise ValueError("%s: a box is [x0, y0, x1, y1] in whole pixels, got %r" % (key, entry))
            x0, y0, x1, y1 = entry
            if x1 <= x0 or y1 <= y0:
                raise ValueError("%s: box %r is empty; x1 and y1 are exclusive ends, not a size"
                                 % (key, entry))
            boxes.append(((x0, y0, x1, y1), why))
        masks.append((key, boxes))
    return masks


SHOT_RE = re.compile(r"\[SHOT\]\s+(\S+)(.*)$")
KV_RE = re.compile(r"([A-Za-z_][\w.\-]*)=(\S+)")


def parse_shots(path):
    """name -> list of {key: value}, one per [SHOT] line, in log order."""
    shots = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = SHOT_RE.search(line)
            if m:
                shots.setdefault(shot_name(m.group(1)), []).append(dict(KV_RE.findall(m.group(2))))
    return shots


def shot_line(name, kv):
    return " ".join(["[SHOT]", name] + ["%s=%s" % item for item in kv.items()])


def parse_since(value):
    try:
        return float(value)
    except ValueError:
        pass
    if os.path.exists(value):
        return os.path.getmtime(value)
    raise ValueError("--since takes epoch seconds or an existing file whose mtime marks the run start")


def open_rgb(path):
    try:
        with Image.open(path) as im:
            im.load()
            return im.convert("RGB"), None
    except Exception as exc:  # unreadable for whatever reason: say which
        try:
            with open(path, "rb") as fh:
                head = fh.read(64)
        except OSError:
            head = b""
        if head.startswith(b"version https://git-lfs"):
            return None, "a git LFS pointer, not an image (git lfs pull)"
        return None, "unreadable: %s" % exc


def inside(child, parent):
    child, parent = os.path.realpath(child), os.path.realpath(parent)
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


# ---------------------------------------------------------------- measuring


LUT_X4 = [min(255, v * 4) for v in range(256)]


def measure(a, b, boxes, delta):
    """Metrics for two same-size RGB images, the d image and the include mask."""
    r, g, bl = ImageChops.difference(a, b).split()
    d = ImageChops.lighter(ImageChops.lighter(r, g), bl)
    include = Image.new("L", a.size, 255)
    for box, _ in boxes:
        include.paste(0, box)
    hist = d.histogram(mask=include)
    n = sum(hist)
    m = {"n": n, "masked": 1.0 - n / float(a.size[0] * a.size[1])}
    if n == 0:
        return m, d, None
    m["mean"] = sum(i * c for i, c in enumerate(hist)) / float(n)
    cum, target = 0, 0.99 * n
    for i, c in enumerate(hist):
        cum += c
        if cum >= target:
            m["p99"] = i
            break
    m["max"] = max(i for i, c in enumerate(hist) if c)
    m["changed_px"] = sum(hist[delta + 1:])
    m["changed"] = m["changed_px"] / float(n)
    over = d.point([255 if v > delta else 0 for v in range(256)])
    m["bbox"] = ImageChops.darker(over, include).getbbox() if m["changed_px"] else None
    return m, d, include


def write_heatmap(path, d, boxes, bbox):
    amp = d.point(LUT_X4)
    heat = Image.merge("RGB", (amp, amp, amp))
    draw = ImageDraw.Draw(heat)
    for (x0, y0, x1, y1), _ in boxes:
        draw.rectangle([x0, y0, x1 - 1, y1 - 1], outline=(40, 120, 255), width=2)
    if bbox:
        draw.rectangle([bbox[0], bbox[1], bbox[2] - 1, bbox[3] - 1], outline=(255, 40, 40), width=2)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    heat.save(path)


def describe(m):
    text = "mean=%.2f p99=%d max=%d changed=%.4f" % (m["mean"], m["p99"], m["max"], m["changed"])
    if m["changed_px"]:
        text += " changed_px=%d at=%s" % (m["changed_px"], ",".join(str(v) for v in m["bbox"]))
    return text


# ---------------------------------------------------------------- modes


def boxes_for(rel, masks, used):
    boxes = []
    for key, entries in masks:
        if matches(rel, key):
            used.add(key)
            boxes.extend(entries)
    return boxes


def check_shot(name, cur_shots, base_shots):
    """None when the [SHOT] lines agree, else the reason they do not."""
    lines = cur_shots.get(name, [])
    if not lines:
        return "this run logged no [SHOT] line for %s" % name
    if len(lines) > 1:
        return "%d [SHOT] lines for %s in one log: which capture is this?" % (len(lines), name)
    want = base_shots.get(name)
    if not want:
        return None
    have = lines[0]
    diffs = ["%s: baseline %s, this run %s" % (k, v, have.get(k, "(absent)"))
             for k, v in want[-1].items() if have.get(k) != v]
    return "; ".join(diffs) or None


def run_compare(args, base, cur, masks, cur_shots, base_shots, since):
    used_only = set()
    pats = only_patterns(args.only)
    base_all = list_pngs(base)
    base_files = apply_only(base_all, pats, used_only)
    cur_files = apply_only(list_pngs(cur), pats, used_only) if os.path.isdir(cur) else []
    for p in pats:
        if p not in used_only:
            harness_exit("--only %s matches no image in either directory" % p)
    if not base_all:
        harness_exit("no baseline PNG under %s: nothing to compare against. Look at this run's "
                     "images, then record them with --record. A first run never passes."
                     % base, {"extra": len(cur_files)})
    if not cur_files:
        print("golden_diff: no PNG under %s; a -batchmode run writes none, and a capture that "
              "bailed early writes some" % cur, file=sys.stderr)

    counts = dict.fromkeys(COUNT_KEYS, 0)
    counts["files"] = len(base_files)
    width = max(len(r) for r in base_files + cur_files)
    cur_set, base_set, used_masks = set(cur_files), set(base_files), set()

    def line(tag, rel, text):
        print("  %-8s %-*s  %s" % (tag, width, rel, text))

    for rel in base_files:
        if rel not in cur_set:
            counts["missing"] += 1
            line("MISSING", rel, "baseline has it, this run wrote no such image")
            continue
        cpath = os.path.join(cur, rel)
        if since is not None and os.path.getmtime(cpath) < since:
            counts["invalid"] += 1
            line("STALE", rel, "older than --since: a previous run's image")
            continue
        if cur_shots is not None:
            why = check_shot(shot_name(rel), cur_shots, base_shots)
            if why:
                counts["invalid"] += 1
                line("SHOT", rel, why)
                continue
        a, err_a = open_rgb(os.path.join(base, rel))
        b, err_b = open_rgb(cpath)
        if a is None or b is None:
            counts["invalid"] += 1
            line("UNREAD", rel, ("baseline " + err_a) if a is None else ("this run's image " + err_b))
            continue
        if a.size != b.size:
            counts["invalid"] += 1
            line("SIZE", rel, "baseline %dx%d, this run %dx%d" % (a.size + b.size))
            continue
        boxes = boxes_for(rel, masks, used_masks)
        bad = [box for box, _ in boxes
               if box[0] < 0 or box[1] < 0 or box[2] > a.size[0] or box[3] > a.size[1]]
        if bad:
            counts["invalid"] += 1
            line("MASK", rel, "box %s lies outside the %dx%d image: drawn for another resolution?"
                 % (list(bad[0]), a.size[0], a.size[1]))
            continue
        m, d, _ = measure(a, b, boxes, args.delta)
        if m["n"] == 0:
            counts["invalid"] += 1
            line("MASK", rel, "every pixel is masked: nothing was compared")
            continue
        over = [k for k, lim in (("mean", args.mean), ("p99", args.p99), ("changed", args.changed))
                if m[k] > lim]
        text = describe(m) + " masked=%.1f%%" % (100 * m["masked"])
        if over:
            counts["failed"] += 1
            line("FAIL", rel, text + "  over=" + ",".join(over))
        else:
            counts["passed"] += 1
            line("PASS", rel, text)
        if args.heatmap_dir:
            write_heatmap(os.path.join(args.heatmap_dir, rel[:-4] + ".diff.png"), d, boxes, m["bbox"])

    for rel in cur_files:
        if rel not in base_set:
            counts["extra"] += 1
            line("EXTRA", rel, "no baseline, not judged: look at it, then --record --only %s"
                 % shot_name(rel))

    if masks and not pats:
        for key, _ in masks:
            if key not in used_masks:
                print("  NOTE     mask key %r matches no compared image" % key)
    if base_shots and cur_shots is None:
        print("  NOTE     the baseline recorded [SHOT] lines; pass --shots LOG to check them")

    if not base_files:
        print("  NOTE     --only selected no baseline image: nothing was judged")
    if counts["missing"] or counts["invalid"] or not base_files:
        verdict, code = "harness", HARNESS
    elif counts["failed"]:
        verdict, code = "failed", FAIL
    else:
        verdict, code = "green", PASS
    summary(counts, verdict)
    return code


def run_record(args, base, cur, cur_shots, since):
    used_only = set()
    pats = only_patterns(args.only)
    files = apply_only(list_pngs(cur) if os.path.isdir(cur) else [], pats, used_only)
    for p in pats:
        if p not in used_only:
            harness_exit("--only %s matches no image under %s" % (p, cur))
    if not files:
        harness_exit("no PNG under %s: nothing to record. A -batchmode run writes no images." % cur)

    problems, images = [], {}
    for rel in files:
        path = os.path.join(cur, rel)
        if since is not None and os.path.getmtime(path) < since:
            problems.append("%s is older than --since: a previous run's image" % rel)
        im, err = open_rgb(path)
        if im is None:
            problems.append("%s is %s" % (rel, err))
        images[rel] = im
        if cur_shots is not None:
            lines = cur_shots.get(shot_name(rel), [])
            if len(lines) != 1:
                problems.append("%s has %d [SHOT] lines in the log; record needs exactly one"
                                % (rel, len(lines)))
    if problems:
        for p in problems:
            print("  REFUSE   " + p)
        harness_exit("nothing recorded: %d problem(s) above" % len(problems))

    width = max(len(r) for r in files)
    new = replaced = 0
    for rel in files:
        dst = os.path.join(base, rel)
        note = "new"
        if os.path.exists(dst):
            replaced += 1
            old, _ = open_rgb(dst)
            if old is None:
                note = "replaced an unreadable file"
            elif old.size != images[rel].size:
                note = "replaced, size %dx%d -> %dx%d" % (old.size + images[rel].size)
            else:
                m, _, _ = measure(old, images[rel], [], args.delta)
                note = "replaced, moved " + describe(m)
        else:
            new += 1
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copyfile(os.path.join(cur, rel), dst)
        state = shot_line(shot_name(rel), cur_shots[shot_name(rel)][0]) if cur_shots is not None \
            else "no [SHOT] line recorded"
        print("  RECORD   %-*s  %dx%d  %s  | %s" % ((width, rel) + images[rel].size + (note, state)))

    if cur_shots is not None:
        shots_path = os.path.join(base, "shots.txt")
        merged = {}
        if os.path.exists(shots_path):
            merged = {k: v[-1] for k, v in parse_shots(shots_path).items()}
        for rel in files:
            merged[shot_name(rel)] = cur_shots[shot_name(rel)][0]
        with open(shots_path, "w", encoding="utf-8") as fh:
            for name in sorted(merged):
                fh.write(shot_line(name, merged[name]) + "\n")
        print("  WROTE    %s (%d [SHOT] lines)" % (shots_path, len(merged)))
    if not pats:
        for rel in list_pngs(base):
            if rel not in files:
                print("  KEPT     %s  baseline only; delete it by hand if that screen is gone" % rel)
    print("[GOLDEN] files=%d recorded=%d new=%d replaced=%d verdict=recorded"
          % (len(files), len(files), new, replaced))
    return PASS


def main():
    ap = Parser(description=__doc__.split("\n\n")[0],
                formatter_class=argparse.RawDescriptionHelpFormatter,
                epilog="Masks, [SHOT] lines, exit codes: see the header of this file.")
    ap.add_argument("baseline_dir", metavar="BASELINE_DIR")
    ap.add_argument("current_dir", metavar="CURRENT_DIR")
    ap.add_argument("--masks", help="masks JSON (default: BASELINE_DIR/masks.json if present)")
    ap.add_argument("--mean", type=float, default=2.0, help="fail above this mean d (default 2.0)")
    ap.add_argument("--p99", type=float, default=24, help="fail above this p99 of d (default 24)")
    ap.add_argument("--changed", type=float, default=0.005,
                    help="fail above this share of pixels with d > --delta (default 0.005)")
    ap.add_argument("--delta", type=int, default=48,
                    help="d above which a pixel counts as changed, 0-255 (default 48)")
    ap.add_argument("--heatmap-dir", help="write <name>.diff.png per compared image here")
    ap.add_argument("--shots", metavar="LOG", help="this run's log holding the [SHOT] lines")
    ap.add_argument("--since", metavar="EPOCH|FILE",
                    help="images (and the --shots log) older than this are a previous run's")
    ap.add_argument("--only", action="append", metavar="NAME",
                    help="limit to these names or patterns, .png optional; repeat or comma-separate")
    ap.add_argument("--record", action="store_true",
                    help="accept CURRENT_DIR's images as the new baselines, then exit 0")
    args = ap.parse_args()

    if not 0 <= args.delta <= 255:
        ap.error("--delta is a 0-255 difference")
    if args.mean < 0 or args.p99 < 0 or not 0 <= args.changed <= 1:
        ap.error("--mean and --p99 are >= 0, --changed is a share between 0 and 1")
    base, cur = args.baseline_dir, args.current_dir
    if os.path.realpath(base) == os.path.realpath(cur):
        harness_exit("BASELINE_DIR and CURRENT_DIR are the same directory: that compares nothing")
    if args.heatmap_dir and (inside(args.heatmap_dir, base) or inside(args.heatmap_dir, cur)):
        harness_exit("--heatmap-dir must sit outside both image directories, or the next run "
                     "reads its heatmaps as screenshots")
    if args.delta <= args.p99 and not args.record:
        print("  WARN     --delta %d <= --p99 %g: every p99 failure is also a changed failure, so "
              "the p99 gate never fires on its own" % (args.delta, args.p99))

    since = None
    if args.since:
        try:
            since = parse_since(args.since)
        except ValueError as exc:
            harness_exit(str(exc))

    cur_shots = None
    if args.shots:
        if not os.path.isfile(args.shots):
            harness_exit("--shots %s does not exist: did the run write its log there?" % args.shots)
        if since is not None and os.path.getmtime(args.shots) < since:
            harness_exit("--shots %s is older than --since: a previous run's log" % args.shots)
        cur_shots = parse_shots(args.shots)

    if args.record:
        return run_record(args, base, cur, cur_shots, since)

    masks_path = args.masks or os.path.join(base, "masks.json")
    masks = []
    if args.masks or os.path.exists(masks_path):
        try:
            masks = load_masks(masks_path)
        except (OSError, ValueError) as exc:
            harness_exit("masks %s: %s" % (masks_path, exc))
    shots_txt = os.path.join(base, "shots.txt")
    base_shots = parse_shots(shots_txt) if os.path.exists(shots_txt) else {}
    if args.heatmap_dir and os.path.isdir(args.heatmap_dir):
        for rel in list_pngs(args.heatmap_dir):
            if rel.endswith(".diff.png"):
                os.remove(os.path.join(args.heatmap_dir, rel))

    print("golden_diff: baseline=%s current=%s masks=%s shots=%s  fail above mean %g, p99 %g, "
          "changed %g (d > %d)" % (base, cur, masks_path if masks else "none",
                                   args.shots or "unchecked", args.mean, args.p99,
                                   args.changed, args.delta))
    return run_compare(args, base, cur, masks, cur_shots, base_shots, since)


if __name__ == "__main__":
    sys.exit(main())
