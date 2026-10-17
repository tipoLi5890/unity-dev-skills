#!/usr/bin/env python3
"""contact_sheet.py — compose labelled images into one review sheet, refusing when the numbers disagree.

The one composer for review sheets: the 8-view QA sheet of a generated mesh,
an animation contact sheet (one still per clip), an overview page. A sheet is
for a person to judge; it proves nothing by itself, so `--require` puts the
numeric checks first: every file named must pass, or no sheet is written.

usage:
    contact_sheet.py SPEC.json --out sheet.png [--require VALIDATION.json ...]
    contact_sheet.py --selftest

SPEC.json:
    {"title": "Runner v03 QA",              optional, a line above the cells
     "cols": 4, "cell": 512,                 cell = side in px, or [w, h]
     "bg": "#202020",                        optional sheet and cell colour
     "items": [{"image": "qa/front_00001.png", "label": "front", "frame": 12}, ...]}

  `image` is relative to the spec's folder. `label` is printed above the cell;
  `frame`, when given, is printed after it ("f12") and, for an animated file
  (GIF, APNG, WebP), picks that frame. An image larger than the cell is
  scaled down to fit, aspect kept; a smaller one stays at its own size,
  centred. Transparency is laid over `bg`.

  "sheets": [{"name": "idle", "items": [...], "title"?, "cols"?, "cell"?}, ...]
  in place of "items" writes one sheet per entry, `<out stem>-<name><ext>`,
  each taking `cols`, `cell`, `bg` from the top level unless it sets its own.

--require FILE (repeatable, or several after one flag): each must be a JSON
object whose `ok`, `all_pass` or `pass` is true, or whose `verdict` or
`record.verdict` is "green" (the producer scripts' partial ledger record);
every one of those keys it carries must pass, and it must carry at least one.
A missing, unreadable or failing file refuses the sheet.

Prints one JSON object: `written` (the sheet paths), `sheets`, `items`, and
`required` (each file with `pass` and, when it failed, `why`).

Exit codes: 0 written; 2 refused by --require (nothing written), or a usage
error (an --out suffix that names no image format Pillow writes); 3 the spec
or an image cannot be read, or a sheet cannot be written (nothing written).
Pillow only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageSequence

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class SpecError(Exception):
    """The spec or an image it names cannot be read: exit 3."""


def check_required(paths: list[Path]) -> list[dict[str, Any]]:
    """One {path, pass, why?} per --require file."""
    rows = []
    for path in paths:
        row: dict[str, Any] = {"path": str(path), "pass": False}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            row["why"] = f"cannot read: {exc.strerror or exc}"
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            row["why"] = f"not JSON: {exc}"
        else:
            if not isinstance(data, dict):
                row["why"] = "not a JSON object"
            else:
                verdicts = {key: data[key] for key in ("ok", "all_pass", "pass") if key in data}
                if "verdict" in data:
                    verdicts["verdict"] = data["verdict"]
                if isinstance(data.get("record"), dict) and "verdict" in data["record"]:
                    verdicts["record.verdict"] = data["record"]["verdict"]
                if not verdicts:
                    row["why"] = "carries none of ok, all_pass, pass, verdict, record.verdict"
                else:
                    bad = [f"{k}={json.dumps(v)}" for k, v in verdicts.items()
                           if not (v == "green" if k.endswith("verdict") else v is True)]
                    if bad:
                        row["why"] = "failing: " + ", ".join(bad)
                    else:
                        row["pass"] = True
        rows.append(row)
    return rows


def cell_size(value: Any) -> tuple[int, int]:
    if isinstance(value, bool):
        raise SpecError("cell must be a side in px or [w, h]")
    if isinstance(value, int) and value > 0:
        return value, value
    if (isinstance(value, list) and len(value) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value)):
        return value[0], value[1]
    raise SpecError(f"cell must be a side in px or [w, h], got {json.dumps(value)}")


def colour(value: Any) -> tuple[int, int, int]:
    try:
        return Image.new("RGB", (1, 1), value).getpixel((0, 0))
    except (ValueError, TypeError) as exc:
        raise SpecError(f"bg is not a colour: {json.dumps(value)}") from exc


def font(px: int):
    try:
        return ImageFont.load_default(size=px)
    except TypeError:  # Pillow before 10.1 has one bitmap size
        return ImageFont.load_default()


def load_item(item: Any, base: Path, index: int) -> tuple[Image.Image, str]:
    """The item's image (RGBA, its frame picked) and its caption."""
    if not isinstance(item, dict) or not isinstance(item.get("image"), str):
        raise SpecError(f"item {index}: needs an image path")
    label = item.get("label", "")
    frame = item.get("frame")
    if not isinstance(label, str):
        raise SpecError(f"item {index}: label must be text")
    if frame is not None and (isinstance(frame, bool) or not isinstance(frame, int) or frame < 0):
        raise SpecError(f"item {index}: frame must be a whole number from 0")
    path = Path(item["image"])
    path = path if path.is_absolute() else base / path
    try:
        with Image.open(path) as im:
            frames = getattr(im, "n_frames", 1)
            if frame is not None and frames > 1:
                if frame >= frames:
                    raise SpecError(f"item {index}: {path} has {frames} frames, not frame {frame}")
                im.seek(frame)
            picture = im.convert("RGBA")
    except SpecError:
        raise
    except (OSError, ValueError) as exc:
        raise SpecError(f"item {index}: cannot read {path}: {exc}") from exc
    caption = label + (f"  f{frame}" if frame is not None else "")
    return picture, caption.strip()


def compose(spec: dict[str, Any], items: list, base: Path) -> Image.Image:
    cols = spec.get("cols")
    if isinstance(cols, bool) or not isinstance(cols, int) or cols < 1:
        raise SpecError(f"cols must be a whole number from 1, got {json.dumps(cols)}")
    cw, ch = cell_size(spec.get("cell"))
    bg = colour(spec.get("bg", "#202020"))
    if not isinstance(items, list) or not items:
        raise SpecError("a sheet needs at least one item")
    loaded = [load_item(item, base, k) for k, item in enumerate(items)]
    label_px = max(14, min(32, ch // 20))
    strip = label_px + 10
    title = spec.get("title")
    if title is not None and not isinstance(title, str):
        raise SpecError("title must be text")
    title_h = (label_px + 18) if title else 0
    rows = -(-len(loaded) // cols)
    sheet = Image.new("RGB", (cols * cw, title_h + rows * (ch + strip)), bg)
    draw = ImageDraw.Draw(sheet)
    face, title_face = font(label_px), font(label_px + 4)
    if title:
        draw.text((10, 7), title, fill=(255, 255, 255), font=title_face)
    for k, (picture, caption) in enumerate(loaded):
        x, y = (k % cols) * cw, title_h + (k // cols) * (ch + strip)
        if picture.width > cw or picture.height > ch:
            picture.thumbnail((cw, ch), Image.LANCZOS)
        backing = Image.new("RGBA", picture.size, bg + (255,))
        backing.alpha_composite(picture)
        sheet.paste(backing.convert("RGB"), (x + (cw - picture.width) // 2, y + strip + (ch - picture.height) // 2))
        while caption and draw.textlength(caption, font=face) > cw - 16:
            caption = caption[:-1]
        draw.text((x + 8, y + 4), caption, fill=(255, 255, 255), font=face)
    return sheet


def build(spec_path: Path, out: Path) -> list[tuple[Path, Image.Image, int]]:
    """Every sheet the spec asks for, composed in memory: (path, image, item count)."""
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SpecError(f"cannot read {spec_path}: {exc.strerror or exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpecError(f"{spec_path} is not JSON: {exc}") from exc
    if not isinstance(spec, dict):
        raise SpecError(f"{spec_path}: the spec is a JSON object")
    base = spec_path.resolve().parent
    if ("items" in spec) == ("sheets" in spec):
        raise SpecError("the spec takes items or sheets, one of the two")
    if "items" in spec:
        return [(out, compose(spec, spec["items"], base), len(spec["items"]))]
    sheets = spec["sheets"]
    if not isinstance(sheets, list) or not sheets:
        raise SpecError("sheets must be a non-empty list")
    built, names = [], set()
    for k, sub in enumerate(sheets):
        if not isinstance(sub, dict) or not isinstance(sub.get("name"), str) or not NAME.match(sub["name"]):
            raise SpecError(f"sheet {k}: needs a name of letters, digits, '.', '_' or '-'")
        if sub["name"] in names:
            raise SpecError(f"sheet {k}: the name {sub['name']} is used twice")
        names.add(sub["name"])
        merged = {key: spec[key] for key in ("cols", "cell", "bg") if key in spec}
        merged.update({key: sub[key] for key in ("cols", "cell", "bg", "title") if key in sub})
        items = sub.get("items")
        path = out.with_name(f"{out.stem}-{sub['name']}{out.suffix}")
        built.append((path, compose(merged, items, base), len(items) if isinstance(items, list) else 0))
    return built


def image_format(out: Path) -> str | None:
    """The Pillow format `out`'s suffix names, when Pillow can write it."""
    fmt = Image.registered_extensions().get(out.suffix.lower())
    return fmt if fmt in Image.SAVE else None


def run(spec: Path, out: Path, required: list[Path]) -> tuple[int, dict[str, Any]]:
    fmt = image_format(out)
    if fmt is None:
        return 2, {"error": f"--out {out}: the suffix names no image format Pillow writes "
                            "(.png, .jpg, .webp)", "required": []}
    checks = check_required(required)
    if not all(row["pass"] for row in checks):
        return 2, {"error": "a --require file does not pass; no sheet written", "required": checks}
    try:
        built = build(spec, out)
    except SpecError as exc:
        return 3, {"error": str(exc), "required": checks}
    # every sheet to a temporary name first, renamed only once all are saved: a failure part
    # way leaves nothing behind
    staged: list[tuple[Path, Path]] = []
    renamed: list[Path] = []
    try:
        for path, image, _ in built:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(f".{path.name}.part")
            staged.append((temp, path))
            (image.convert("RGB") if fmt == "JPEG" else image).save(temp, format=fmt)
        for temp, path in staged:
            temp.replace(path)
            renamed.append(path)
    except (OSError, ValueError) as exc:
        for leftover in [temp for temp, _ in staged] + renamed:
            try:
                leftover.unlink(missing_ok=True)
            except OSError:
                pass
        return 3, {"error": f"cannot write {out}: {exc}", "required": checks}
    written = [str(path) for _, path in staged]
    return 0, {"written": written, "sheets": len(built), "items": sum(n for _, _, n in built), "required": checks}


def selftest() -> int:
    checks: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        views = ["front", "left", "back", "right", "top", "clay", "occlusion", "uv_atlas"]
        for k, name in enumerate(views):
            Image.new("RGB", (512, 512), (20 * k + 40, 200, 30)).save(t / f"{name}_00001.png")
        spec = {"title": "Runner QA", "cols": 4, "cell": 256,
                "items": [{"image": f"{name}_00001.png", "label": name} for name in views]}
        (t / "qa.json").write_text(json.dumps(spec))
        (t / "ok.json").write_text(json.dumps({"ok": True, "gates": []}))
        (t / "green.json").write_text(json.dumps({"verdict": "green"}))
        (t / "fail.json").write_text(json.dumps({"all_pass": False}))
        (t / "mixed.json").write_text(json.dumps({"ok": True, "verdict": "failed"}))
        (t / "none.json").write_text(json.dumps({"gates": []}))
        (t / "truthy.json").write_text(json.dumps({"ok": 1}))
        (t / "rec.json").write_text(json.dumps({"failures": [], "record": {"verdict": "green"}}))
        (t / "recfail.json").write_text(json.dumps({"record": {"verdict": "failed"}}))

        code, res = run(t / "qa.json", t / "out" / "qa.png", [t / "ok.json", t / "green.json", t / "rec.json"])
        checks.append(("written", code == 0 and Path(res["written"][0]).is_file()))
        sheet = Image.open(t / "out" / "qa.png")
        label_px = max(14, min(32, 256 // 20))
        title_h, strip = label_px + 18, label_px + 10
        checks.append(("size 4x2", sheet.size == (1024, title_h + 2 * (256 + strip))))
        centre = sheet.getpixel((256 * 2 + 128, title_h + strip + 128))   # back: k=2, scaled 512 -> 256
        checks.append(("cell placed", centre == (80, 200, 30)))
        centre = sheet.getpixel((256 * 3 + 128, title_h + 256 + strip + strip + 128))   # uv_atlas: k=7
        checks.append(("second row", centre == (180, 200, 30)))
        for name in ("fail.json", "mixed.json", "none.json", "truthy.json", "missing.json", "recfail.json"):
            out = t / "out" / f"refused-{name}.png"
            code, res = run(t / "qa.json", out, [t / "ok.json", t / name])
            checks.append((f"refused {name}", code == 2 and not out.exists() and res["required"][1]["pass"] is False))

        frames = [Image.new("RGB", (64, 64), c) for c in ((255, 0, 0), (0, 0, 255))]
        frames[0].save(t / "anim.gif", save_all=True, append_images=frames[1:], duration=100)
        Image.new("RGBA", (40, 40), (0, 0, 0, 0)).save(t / "clear.png")
        (t / "anim.json").write_text(json.dumps({"cols": 2, "cell": [128, 96], "bg": "#000000", "sheets": [
            {"name": "jog", "items": [{"image": "anim.gif", "label": "JogLaneLeft", "frame": 1},
                                      {"image": "clear.png", "label": "empty"}]},
            {"name": "vault", "cols": 1, "items": [{"image": "anim.gif", "label": "GateVault", "frame": 0}]}]}))
        code, res = run(t / "anim.json", t / "out" / "anim.png", [])
        checks.append(("two sheets", code == 0 and [Path(p).name for p in res["written"]]
                       == ["anim-jog.png", "anim-vault.png"]))
        jog = Image.open(t / "out" / "anim-jog.png").convert("RGB")
        strip = max(14, min(32, 96 // 20)) + 10
        r, g, b = jog.getpixel((64, strip + 48))
        checks.append(("frame picked", b > 200 and r < 50))
        checks.append(("small image not upscaled", jog.getpixel((128 + 10, strip + 10)) == (0, 0, 0)))
        checks.append(("sheet cols override", Image.open(t / "out" / "anim-vault.png").width == 128))

        (t / "badimg.json").write_text(json.dumps({"cols": 1, "cell": 64, "items": [{"image": "nope.png"}]}))
        code, _ = run(t / "badimg.json", t / "out" / "bad.png", [])
        checks.append(("unreadable image", code == 3 and not (t / "out" / "bad.png").exists()))
        (t / "badframe.json").write_text(json.dumps({"cols": 1, "cell": 64,
                                                     "items": [{"image": "anim.gif", "frame": 5}]}))
        checks.append(("frame out of range", run(t / "badframe.json", t / "out" / "bf.png", [])[0] == 3))
        (t / "both.json").write_text(json.dumps({"cols": 1, "cell": 64, "items": [], "sheets": []}))
        checks.append(("items or sheets", run(t / "both.json", t / "out" / "both.png", [])[0] == 3))
        for name in ("noext", "out.txt"):
            checks.append((f"--out {name}", run(t / "qa.json", t / "out" / name, [])[0] == 2
                           and not (t / "out" / name).exists()))
        (t / "blocked").write_text("a file where a folder should be")
        code, _ = run(t / "anim.json", t / "blocked" / "anim.png", [])
        checks.append(("unwritable out", code == 3))
        # the second sheet cannot be written: the first is not left behind
        (t / "out2").mkdir()
        (t / "out2" / "anim-vault.png").mkdir()
        code, _ = run(t / "anim.json", t / "out2" / "anim.png", [])
        left = sorted(p.name for p in (t / "out2").iterdir())
        checks.append(("nothing left on failure", code == 3 and left == ["anim-vault.png"]))
        code, res = run(t / "qa.json", t / "out" / "qa.jpg", [])
        checks.append(("jpeg", code == 0 and Image.open(res["written"][0]).format == "JPEG"))
    failed = [name for name, ok in checks if not ok]
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": len(checks), "failed": failed}))
    return 0 if not failed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("spec", nargs="?", type=Path, help="The sheet spec (JSON)")
    parser.add_argument("--out", type=Path, help="The sheet to write (.png, .jpg)")
    parser.add_argument("--require", nargs="+", action="extend", type=Path, default=[], metavar="VALIDATION.json",
                        help="A check file that must pass (ok / all_pass / pass true, or verdict / record.verdict green)")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.spec is None or args.out is None:
        parser.error("SPEC.json and --out are required (or --selftest)")
    code, result = run(args.spec, args.out, args.require)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
