#!/usr/bin/env python3
"""overview_sheet.py — themed overview sheets: captioned cells, the source path under each caption.

Groups the reference images a project already has (style anchors, flow
screens, game-screen mockups) into a few captioned pages a person reads in
one sitting, and records which file each cell showed. Sources are only read,
never moved or copied: the sheets point at them.

usage:
    overview_sheet.py SPEC.json --out DIR [--cell 480]
    overview_sheet.py --selftest            (or: overview_sheet.py selftest)

SPEC.json:
    {"font": "fonts/NotoSansTC-Regular.otf",      optional; a TTF/OTF for non-Latin captions
     "bg": "#202020",                            optional sheet colour
     "sheets": [{"name": "flow_screens",          letters, digits, '.', '_', '-'
                 "title": "Flow screens, launch to run summary",   optional
                 "cols": 3,                       optional, default 3
                 "cell": [480, 270],              optional; a side or [w, h], default --cell
                 "items": [{"path": "ArtDirection/candidates/title.png",
                            "caption": "Title screen"}, ...]}]}

  `path` and `font` are relative to the spec's folder (an absolute `path` is
  refused, so the outputs do not depend on where the project sits). Each sheet becomes
  DIR/<name>.png: a title band, then one cell per item with its caption and,
  under it, the path as the spec wrote it. A path that is not a file becomes a
  red "missing" cell; a file Pillow cannot open (corrupt, or over Pillow's
  pixel limit), a red "unreadable" cell. A sheet with fewer items than `cols`
  is as wide as its items.

  DIR/overview.json: {"sheets": [{"name", "title", "png", "png_sha256",
  "items": [{"path", "caption", "status": "ok"|"missing"|"unreadable",
  "sha256"?, "size"?}]}], "missing": [...]}. Every present item carries the
  sha256 of its bytes, so a later look can tell which version a cell showed.
  The same spec and the same files give the same bytes in every output.

Exit codes: 0 written; 2 written, but an item is missing or unreadable (or a
usage error); 3 the spec or the font cannot be read, or DIR cannot be written
(the folder is left as it was). The grid is contact_sheet.py's. Pillow only.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contact_sheet import NAME, WHITE, SpecError, cell_size, colour, commit, font, lay_out  # noqa: E402

GREY = (170, 170, 170)
RED = (170, 40, 40)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def red_cell(size: tuple[int, int], word: str, face_for) -> Image.Image:
    cell = Image.new("RGBA", size, RED + (255,))
    draw = ImageDraw.Draw(cell)
    face = face_for(max(16, min(48, size[1] // 8)))
    w = draw.textlength(word, font=face)
    draw.text(((size[0] - w) / 2, size[1] / 2 - size[1] // 16), word, fill=WHITE, font=face)
    return cell


def tail(text: str, width: int, face) -> str:
    """A long path keeps its end, the file name: "...art/round2/title.png"."""
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    if probe.textlength(text, font=face) <= width:
        return text
    while text and probe.textlength("..." + text, font=face) > width:
        text = text[1:]
    return "..." + text


def load_spec(spec_path: Path) -> dict[str, Any]:
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SpecError(f"cannot read {spec_path}: {exc.strerror or exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpecError(f"{spec_path} is not JSON: {exc}") from exc
    if not isinstance(spec, dict) or not isinstance(spec.get("sheets"), list) or not spec["sheets"]:
        raise SpecError(f"{spec_path}: the spec is an object with a non-empty sheets list")
    return spec


def face_maker(spec: dict[str, Any], base: Path):
    if spec.get("font") is None:
        return font
    if not isinstance(spec["font"], str):
        raise SpecError("font must be a path")
    path = Path(spec["font"])
    path = path if path.is_absolute() else base / path
    try:
        ImageFont.truetype(str(path), 16)
    except OSError as exc:
        raise SpecError(f"font {spec['font']}: cannot load: {exc}") from exc
    return lambda px: ImageFont.truetype(str(path), px)


def build(spec_path: Path, default_cell: int) -> tuple[list[tuple[str, bytes]], dict[str, Any]]:
    """Every output file as (name, bytes), and the overview record."""
    spec = load_spec(spec_path)
    base = spec_path.resolve().parent
    face_for = face_maker(spec, base)
    bg = colour(spec.get("bg", "#202020"))
    files: list[tuple[str, bytes]] = []
    record: dict[str, Any] = {"sheets": [], "missing": []}
    names: set[str] = set()
    for k, sheet in enumerate(spec["sheets"]):
        if not isinstance(sheet, dict) or not isinstance(sheet.get("name"), str) or not NAME.match(sheet["name"]):
            raise SpecError(f"sheet {k}: needs a name of letters, digits, '.', '_' or '-'")
        name = sheet["name"]
        if name in names:
            raise SpecError(f"sheet {k}: the name {name} is used twice")
        names.add(name)
        cols = sheet.get("cols", 3)
        if isinstance(cols, bool) or not isinstance(cols, int) or cols < 1:
            raise SpecError(f"sheet {name}: cols must be a whole number from 1")
        cw, ch = cell_size(sheet.get("cell", default_cell))
        title = sheet.get("title")
        if title is not None and not isinstance(title, str):
            raise SpecError(f"sheet {name}: title must be text")
        items = sheet.get("items")
        if not isinstance(items, list) or not items:
            raise SpecError(f"sheet {name}: needs at least one item")
        cells, rows = [], []
        path_face = face_for(max(14, min(32, ch // 20)))   # contact_sheet's label size
        for n, item in enumerate(items):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"]:
                raise SpecError(f"sheet {name}, item {n}: needs a path")
            caption = item.get("caption", "")
            if not isinstance(caption, str):
                raise SpecError(f"sheet {name}, item {n}: caption must be text")
            row: dict[str, Any] = {"path": item["path"], "caption": caption}
            if Path(item["path"]).is_absolute():
                raise SpecError(f"sheet {name}, item {n}: path must be relative to the spec")
            path = base / item["path"]
            picture = None
            if not path.is_file():
                row["status"] = "missing"
            else:
                row["sha256"] = sha256(path)
                try:
                    with Image.open(path) as im:
                        picture = im.convert("RGBA")
                    row["status"], row["size"] = "ok", list(picture.size)
                except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
                    row["status"] = "unreadable"
            if picture is None:
                picture = red_cell((cw, ch), row["status"], face_for)
                record["missing"].append({"sheet": name, "path": item["path"], "status": row["status"]})
            cells.append((picture, [(caption, WHITE), (tail(item["path"], cw - 16, path_face), GREY)]))
            rows.append(row)
        png = io.BytesIO()
        lay_out(cells, min(cols, len(cells)), (cw, ch), bg, title, face_for).save(png, format="PNG")
        data = png.getvalue()
        files.append((f"{name}.png", data))
        record["sheets"].append({"name": name, "title": title, "png": f"{name}.png",
                                 "png_sha256": hashlib.sha256(data).hexdigest(), "items": rows})
    files.append(("overview.json", (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")))
    return files, record


def write_all(out: Path, files: list[tuple[str, bytes]]) -> None:
    """Every file under a temporary name first, then contact_sheet's commit: a failure part way
    removes this run's files and puts back what an earlier run had written under the same names."""
    staged: list[tuple[Path, Path]] = []
    try:
        out.mkdir(parents=True, exist_ok=True)
        for name, data in files:
            temp = out / f".{name}.part"
            staged.append((temp, out / name))
            temp.write_bytes(data)
        commit(staged)
    except OSError:
        for temp, _ in staged:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def run(spec: Path, out: Path, cell: int = 480) -> tuple[int, dict[str, Any]]:
    if isinstance(cell, bool) or not isinstance(cell, int) or cell < 1:
        return 2, {"error": "--cell must be a whole number from 1"}
    try:
        files, record = build(spec, cell)
    except SpecError as exc:
        return 3, {"error": str(exc)}
    try:
        write_all(out, files)
    except OSError as exc:
        return 3, {"error": f"cannot write {out}: {exc}"}
    result = {"written": [str(out / name) for name, _ in files], "sheets": len(record["sheets"]),
              "items": sum(len(s["items"]) for s in record["sheets"]), "missing": record["missing"]}
    return (2 if record["missing"] else 0), result


def selftest() -> int:
    checks: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "art").mkdir()
        for k, name in enumerate(("anchor", "title", "lanes", "gate")):
            Image.new("RGB", (640, 360), (40 * k + 30, 160, 60)).save(t / "art" / f"{name}.png")
        (t / "art" / "broken.png").write_bytes(b"not an image")
        good = {"sheets": [
            {"name": "style_and_brand", "title": "Style and brand", "cols": 2,
             "items": [{"path": "art/anchor.png", "caption": "Style anchor"},
                       {"path": "art/title.png", "caption": "Title screen"}]},
            {"name": "game_screens", "cols": 1, "cell": [320, 180],
             "items": [{"path": "art/lanes.png", "caption": "Three lanes, Runner centre"}]}]}
        (t / "good.json").write_text(json.dumps(good))
        code, res = run(t / "good.json", t / "o1", 240)
        checks.append(("all present: exit 0", code == 0 and res["missing"] == []))
        record = json.loads((t / "o1" / "overview.json").read_text(encoding="utf-8"))
        hashes = {i["path"]: i.get("sha256") for s in record["sheets"] for i in s["items"]}
        checks.append(("sha256 of every item", all(hashes[p] == hashlib.sha256((t / p).read_bytes()).hexdigest()
                                                   for p in hashes)))
        checks.append(("png sha256", all(s["png_sha256"] == hashlib.sha256((t / "o1" / s["png"]).read_bytes())
                                         .hexdigest() for s in record["sheets"])))
        sheet = Image.open(t / "o1" / "style_and_brand.png").convert("RGB")
        label_px = max(14, min(32, 240 // 20))
        title_h, strip = label_px + 18, label_px + 10 + label_px + 6
        checks.append(("two-line strip, 2 cols", sheet.size == (480, title_h + 240 + strip)))
        checks.append(("cell placed", sheet.getpixel((240 + 120, title_h + strip + 120)) == (70, 160, 60)))
        face = font(label_px)
        cut = tail("ArtDirection/candidates/round2/" * 4 + "title.png", 200, face)
        checks.append(("long path keeps its file name", cut.startswith("...") and cut.endswith("/title.png")))
        checks.append(("cell override", Image.open(t / "o1" / "game_screens.png").width == 320))

        bad = {"sheets": [{"name": "flow", "title": "Flow screens", "cols": 3, "items": [
            {"path": "art/title.png", "caption": "Title"},
            {"path": "art/results.png", "caption": "Results (not drawn yet)"},
            {"path": "art/broken.png", "caption": "Pause"}]}]}
        (t / "bad.json").write_text(json.dumps(bad))
        code, res = run(t / "bad.json", t / "o2", 200)
        checks.append(("missing: exit 2", code == 2 and [m["status"] for m in res["missing"]]
                       == ["missing", "unreadable"]))
        checks.append(("still written", (t / "o2" / "flow.png").is_file() and (t / "o2" / "overview.json").is_file()))
        flow = Image.open(t / "o2" / "flow.png").convert("RGB")
        label_px = max(14, min(32, 200 // 20))
        top = label_px + 18 + label_px + 10 + label_px + 6
        checks.append(("red missing cell", flow.getpixel((200 + 6, top + 6)) == RED))
        checks.append(("red unreadable cell", flow.getpixel((400 + 6, top + 6)) == RED))
        items = json.loads((t / "o2" / "overview.json").read_text(encoding="utf-8"))["sheets"][0]["items"]
        checks.append(("present items hashed", "sha256" in items[0] and "sha256" in items[2]
                       and "sha256" not in items[1]))
        checks.append(("sources untouched", sorted(p.name for p in (t / "art").iterdir())
                       == ["anchor.png", "broken.png", "gate.png", "lanes.png", "title.png"]))

        run(t / "bad.json", t / "o3", 200)
        checks.append(("deterministic", all((t / "o2" / n).read_bytes() == (t / "o3" / n).read_bytes()
                                            for n in ("flow.png", "overview.json"))))
        (t / "copy").mkdir()
        (t / "copy" / "art").mkdir()
        for p in (t / "art").iterdir():
            (t / "copy" / "art" / p.name).write_bytes(p.read_bytes())
        (t / "copy" / "bad.json").write_text(json.dumps(bad))
        run(t / "copy" / "bad.json", t / "o4", 200)
        checks.append(("same bytes from another folder", all((t / "o2" / n).read_bytes() == (t / "o4" / n)
                                                              .read_bytes() for n in ("flow.png", "overview.json"))))

        for label, spec in (("duplicate name", {"sheets": [good["sheets"][0], good["sheets"][0]]}),
                            ("bad name", {"sheets": [{"name": "a/b", "items": good["sheets"][0]["items"]}]}),
                            ("no items", {"sheets": [{"name": "x", "items": []}]}),
                            ("item without path", {"sheets": [{"name": "x", "items": [{"caption": "c"}]}]}),
                            ("missing font", {"font": "nope.ttf", "sheets": good["sheets"]})):
            (t / "s.json").write_text(json.dumps(spec))
            code, _ = run(t / "s.json", t / "o5", 200)
            checks.append((f"{label}: exit 3, nothing written", code == 3 and not (t / "o5").exists()))
        (t / "blocked").write_text("a file where a folder should be")
        checks.append(("unwritable out", run(t / "good.json", t / "blocked", 200)[0] == 3))
        checks.append(("bad --cell", run(t / "good.json", t / "o6", 0)[0] == 2))
        (t / "o10" / "overview.json").mkdir(parents=True)        # the last rename fails on it
        (t / "o10" / "style_and_brand.png").write_bytes(b"an earlier run")
        code, _ = run(t / "good.json", t / "o10", 240)
        checks.append(("failed re-run keeps the earlier page", code == 3 and sorted(
            p.name for p in (t / "o10").iterdir()) == ["overview.json", "style_and_brand.png"]
            and (t / "o10" / "style_and_brand.png").read_bytes() == b"an earlier run"))
        absolute = {"sheets": [{"name": "x", "items": [{"path": str(t / "art" / "title.png")}]}]}
        (t / "s.json").write_text(json.dumps(absolute))
        checks.append(("absolute path: exit 3", run(t / "s.json", t / "o7", 200)[0] == 3
                       and not (t / "o7").exists()))
        narrow = Image.open(t / "o2" / "flow.png").width
        one = {"sheets": [{"name": "one", "cols": 3, "items": [{"path": "art/title.png"}]}]}
        (t / "s.json").write_text(json.dumps(one))
        run(t / "s.json", t / "o8", 200)
        checks.append(("fewer items than cols: narrower", narrow == 600
                       and Image.open(t / "o8" / "one.png").width == 200))
        Image.new("1", (1200, 1200)).save(t / "art" / "huge.png")
        (t / "s.json").write_text(json.dumps({"sheets": [{"name": "one", "items": [{"path": "art/huge.png"}]}]}))
        limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = 200_000       # 1200x1200 is over twice this: Pillow refuses it as a bomb
        try:
            code, res = run(t / "s.json", t / "o9", 200)
        finally:
            Image.MAX_IMAGE_PIXELS = limit
        bomb = Image.open(t / "o9" / "one.png").convert("RGB") if (t / "o9" / "one.png").is_file() else None
        checks.append(("over the pixel limit: exit 2, red cell", code == 2 and bomb is not None
                       and [m["status"] for m in res["missing"]] == ["unreadable"]
                       and bomb.getpixel((6, bomb.height - 6)) == RED))
    failed = [name for name, ok in checks if not ok]
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": len(checks), "failed": failed}))
    return 0 if not failed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("spec", nargs="?", type=Path, help="The overview spec (JSON), or `selftest`")
    parser.add_argument("--out", type=Path, help="The folder for <name>.png and overview.json")
    parser.add_argument("--cell", type=int, default=480, help="Default cell side in px (default 480)")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest or (str(args.spec) == "selftest" and args.out is None):
        return selftest()
    if args.spec is None or args.out is None:
        parser.error("SPEC.json and --out are required (or --selftest)")
    code, result = run(args.spec, args.out, args.cell)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
