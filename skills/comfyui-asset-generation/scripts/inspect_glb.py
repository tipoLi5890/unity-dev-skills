#!/usr/bin/env python3
"""inspect_glb.py — the acceptance gate for a generated GLB.

A finished job proves a file exists, not that it is a game asset. This reads
the GLB container directly and checks what an engine import depends on:
triangle count against the budget the graph was asked for, one material, UVs
and normals on every primitive, the texture slots that were supposed to be
baked, texture dimensions, and sane bounds.

Stdlib only. Prints one gate/1 report (schemas/gate-1.json: `pass`, and `ok`,
its old name, equal to it for one release); exit 0 = pass, 1 = a gate failed,
2 = the file could not be read (with --budgets: nor the budget row).

Examples
  inspect_glb.py crate.glb --max-triangles 20000
  inspect_glb.py crate.glb --max-triangles 20000 --texture-size 2048 \
      --require base,normal,occlusion,metallic-roughness
  inspect_glb.py crate.glb --max-triangles 20000 --extract maps/   # write the embedded images out
  inspect_glb.py mallet.glb --class hero-prop --budgets ART_DIRECTION.md --json-out mallet.json

Gates
  triangles   over --max-triangles x 1.05 fails; under x --min-fraction (default 0.5)
              fails too — a mesh far below its target collapsed somewhere upstream
  materials   more than --max-materials (default 1): each one is a draw call
  attributes  any primitive without TEXCOORD_0 or NORMAL
  slots       any slot named in --require that no material carries
  textures    any embedded image larger than --texture-size on either side
  bounds      a non-finite or zero extent
  size        over --max-bytes, when given
`double_sided` is reported, not gated: a material exported double-sided is
drawn without back-face culling until the importing side says otherwise.
`extensions_required` is reported, not gated: a Draco- or meshopt-compressed
file needs the matching decoder on the importing side.

Every check that ran is also one entry of `gates` ({name, value, limit, pass});
`failures` keeps the same reasons as text. `sha256` pins the file, and
`record` is the partial ledger record for skill art-asset-registry; its file
path is the one given, so a JSON kept in the project carries no machine path
(run from the project root: a relative path is read against --root there). A
bound that is not a finite number prints as null.

--budgets FILE --class CLASS reads that class's row of the `3D budgets` table
in FILE (the project's ART_DIRECTION.md: the first table under a heading named
"3D budgets" whose first column is `class`). The default rows live in skill
unity-3d-models, reference/budgets.md; a project copies them into its own file,
and this script reads no other. FILE without that table: reported only, with a
warning. A class the table does not list, a numeric cell that is not a plain
number, or a `calibrated` cell that is neither a YYYY-MM-DD date nor `-`: exit 2.
On a calibrated row, ceiling_tris and ceiling_tex_px fail when exceeded,
max_bones and max_mb (MB of 2^20 bytes) fail when set and exceeded, and
max_materials replaces the default material limit; over target_tris or
target_tex_px x 1.25 is a line in `warnings`, never a failure. An uncalibrated
row (`calibrated` is `-`) only reports, in `warnings`. An explicit
--max-triangles, --texture-size, --max-materials or --max-bytes wins: that
quantity's class columns are not read. --json-out PATH writes the printed
object to PATH as well.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import re
import struct
import sys
from pathlib import Path

SLOTS = {
    "base": lambda m: m.get("pbrMetallicRoughness", {}).get("baseColorTexture"),
    "metallic-roughness": lambda m: m.get("pbrMetallicRoughness", {}).get("metallicRoughnessTexture"),
    "normal": lambda m: m.get("normalTexture"),
    "occlusion": lambda m: m.get("occlusionTexture"),
    "emissive": lambda m: m.get("emissiveTexture"),
}
MIME_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
# The flags a class row can stand in for, and the value each has when neither sets it.
DEFAULTS = {"max_triangles": 0, "max_materials": 1, "texture_size": 0, "max_bytes": 0}
TARGET_SLACK = 1.25
MB = 1024 * 1024

# ------------------------------------------------------------------ the `3D budgets` table
BUDGET_SECTION = "3d budgets"
NUMERIC = ("target_tris", "target_tex_px", "ceiling_tris", "ceiling_tex_px", "max_materials",
           "max_bones", "max_mb", "lod_ratio")
TEXT = ("preset", "calibrated", "note")
UNSET = ("", "-", "–", "—")
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
RULE_ROW = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
NUMBER = re.compile(r"^[+]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def _unfenced(lines: list[str]) -> list[str]:
    """`lines` with every line inside a ``` or ~~~ fence (the fences too) blanked: a `# 3D budgets`
    shell comment in a code block is not the section, and a table there is not the table."""
    out, fence = [], None
    for line in lines:
        mark = FENCE.match(line)
        if fence is None and mark:
            fence = mark.group(1)
            out.append("")
        elif fence is not None:
            if mark and mark.group(1)[0] == fence[0] and len(mark.group(1)) >= len(fence) \
                    and not line.strip()[len(mark.group(1)):].strip():
                fence = None
            out.append("")
        else:
            out.append(line)
    return out


def _plain(cell: str) -> str:
    return re.sub(r"[`*]", "", cell).strip()


def _cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [_plain(cell.replace("\\|", "|")) for cell in re.split(r"(?<!\\)\|", line)]


def read_budget_table(path: Path) -> dict | None:
    """{class: row} from the `3D budgets` table in `path`, or None when it has no such table.

    ValueError: a class listed twice, a numeric cell that is not a plain number, a `calibrated`
    cell that is neither a YYYY-MM-DD date nor unset."""
    lines = _unfenced(path.read_text(encoding="utf-8-sig").splitlines())
    body = None
    for i, line in enumerate(lines):
        heading = HEADING.match(line)
        if heading and " ".join(_plain(heading.group(2)).lower().rstrip(":").split()) == BUDGET_SECTION:
            level, body = len(heading.group(1)), []
            for nxt in lines[i + 1:]:
                other = HEADING.match(nxt)
                if other and len(other.group(1)) <= level:
                    break
                body.append(nxt)
            break
    if body is None:
        return None
    for i in range(len(body) - 1):
        if "|" in body[i] and RULE_ROW.match(body[i + 1]):
            header = [cell.lower() for cell in _cells(body[i])]
            if header and header[0] == "class":
                break
    else:
        return None
    where = {name: header.index(name) for name in NUMERIC + TEXT if name in header}
    table: dict = {}
    for line in body[i + 2:]:
        if "|" not in line:
            break
        cells = _cells(line)
        cls = cells[0]
        if cls in UNSET:
            continue
        if cls in table:
            raise ValueError(f"{path}: class {cls!r} is listed twice under '3D budgets'")
        row: dict = {}
        for name in NUMERIC + TEXT:
            j = where.get(name)
            raw = cells[j] if j is not None and j < len(cells) else ""
            if raw in UNSET:
                row[name] = None
            elif name in NUMERIC:
                if not NUMBER.match(raw):
                    raise ValueError(f"{path}: class {cls!r}: {name} is {raw!r}, not a plain number")
                value = float(raw)
                row[name] = int(value) if value.is_integer() else value
            else:
                row[name] = raw
        stamp = row["calibrated"]
        if stamp is not None:
            try:
                ok = bool(DATE.match(stamp)) and datetime.date.fromisoformat(stamp) is not None
            except ValueError:
                ok = False
            if not ok:
                raise ValueError(f"{path}: class {cls!r}: calibrated is {stamp!r}, "
                                 "not a YYYY-MM-DD date or -")
        table[cls] = row
    return table


def load_budget(cls: str | None, budgets: Path | None) -> tuple[str | None, dict | None, list[str]]:
    """(class as the table spells it, row or None, warnings).

    OSError or ValueError: unreadable file, bad cell, a class the table does not list."""
    if budgets is None:
        if cls:
            return cls, None, [f"class {cls}: no --budgets file, so no budget row was read"]
        return cls, None, []
    table = read_budget_table(budgets)
    if table is None:
        return cls, None, [f"{budgets.name} has no '3D budgets' table starting with a `class` column: "
                           "reported, not gated"]
    if cls in table:
        return cls, table[cls], []
    folded = {key.casefold(): key for key in table}
    if cls.casefold() in folded:
        return folded[cls.casefold()], table[folded[cls.casefold()]], []
    raise ValueError(f"class {cls!r} is not in the '3D budgets' table of {budgets} "
                     f"(it lists: {', '.join(table) or 'nothing'})")


# ------------------------------------------------------------------ the GLB
def parse_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise ValueError("not a GLB container")
    version, _total = struct.unpack_from("<II", data, 4)
    if version != 2:
        raise ValueError(f"only glTF 2.0 is supported (found {version})")
    gltf, binary, off = None, b"", 12
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8 : off + 8 + clen]
        if ctype == 0x4E4F534A:  # 'JSON'
            gltf = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:  # 'BIN\0'
            binary = chunk
        off += 8 + clen + (-clen % 4)
    if gltf is None:
        raise ValueError("no JSON chunk")
    if not isinstance(gltf, dict):
        raise ValueError("the JSON chunk is not an object")
    return gltf, binary


def image_bytes(gltf: dict, binary: bytes, image: dict) -> bytes:
    view = gltf["bufferViews"][image["bufferView"]]
    start = view.get("byteOffset", 0)
    return binary[start : start + view["byteLength"]]


def image_size(blob: bytes) -> tuple[int, int] | None:
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack_from(">II", blob, 16)
    if blob[:2] == b"\xff\xd8":
        off = 2
        while off + 9 < len(blob):
            if blob[off] != 0xFF:
                off += 1
                continue
            marker = blob[off + 1]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                height, width = struct.unpack_from(">HH", blob, off + 5)
                return width, height
            off += 2 + struct.unpack_from(">H", blob, off + 2)[0]
    return None  # WebP, KTX2: reported with unknown size


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(values: list) -> list:
    """JSON has no Infinity or NaN: a bound that is not a finite number prints as null."""
    return [v if isinstance(v, (int, float)) and math.isfinite(v) else None for v in values]


def inspect(path: Path, args: argparse.Namespace, budget: dict | None = None,
            explicit: frozenset = frozenset()) -> tuple[dict, list[str]]:
    gltf, binary = parse_glb(path)
    accessors = gltf.get("accessors", [])
    materials = gltf.get("materials", [])
    failures: list[str] = []
    gates: list[dict] = []
    warnings: list[str] = []

    def gate(name, value, limit, ok):
        gates.append({"name": name, "value": value, "limit": limit, "pass": bool(ok)})

    triangles, primitives, missing_attrs = 0, 0, set()
    used_materials: set[int] = set()
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if prim.get("mode", 4) != 4:
                continue
            primitives += 1
            attrs = prim.get("attributes", {})
            position = accessors[attrs["POSITION"]]
            count = accessors[prim["indices"]]["count"] if "indices" in prim else position["count"]
            triangles += count // 3
            missing_attrs.update(name for name in ("TEXCOORD_0", "NORMAL") if name not in attrs)
            if "material" in prim:
                used_materials.add(prim["material"])
            for axis in range(3):
                lo[axis] = min(lo[axis], position.get("min", [math.nan] * 3)[axis])
                hi[axis] = max(hi[axis], position.get("max", [math.nan] * 3)[axis])
    extents = [hi[axis] - lo[axis] for axis in range(3)]
    bounded = all(math.isfinite(e) and e > 0 for e in extents)

    images = []
    for index, image in enumerate(gltf.get("images", [])):
        if "bufferView" not in image:
            images.append({"index": index, "uri": image.get("uri", "")[:60], "size": None})
            continue
        blob = image_bytes(gltf, binary, image)
        size = image_size(blob)
        images.append(
            {"index": index, "mime": image.get("mimeType"), "size": list(size) if size else None, "bytes": len(blob)}
        )
        if args.extract:
            args.extract.mkdir(parents=True, exist_ok=True)
            ext = MIME_EXT.get(image.get("mimeType"), ".bin")
            (args.extract / f"image{index}{ext}").write_bytes(blob)

    slots = sorted(
        name for name, pick in SLOTS.items() if any(pick(materials[i]) for i in used_materials if i < len(materials))
    )
    sides = [max(image["size"]) for image in images if image["size"]]
    largest_side = max(sides) if sides else None

    # A class row: gated when calibrated, only reported when not; an explicit flag wins.
    cls = args.asset_class
    calibrated = budget is not None and budget.get("calibrated") is not None
    if budget is not None and not calibrated:
        warnings.append(f"class {cls}: its 3D budgets row is not calibrated, so it is reported, not "
                        "gated; set its budget (unity-3d-models reference/budgets.md) or pass "
                        "explicit limits")

    def from_class(column, flag):
        """The row's value for `column`, or None: no row, the cell is empty, or `flag` was given."""
        if budget is None or flag in explicit:
            return None
        return budget.get(column)

    materials_limit = args.max_materials
    class_materials = from_class("max_materials", "max_materials")
    if class_materials is not None:
        if calibrated:
            materials_limit = class_materials
        elif len(used_materials) > class_materials:
            warnings.append(f"{len(used_materials)} materials, over max_materials {class_materials} "
                            "(not calibrated: reported, not gated)")

    if args.max_triangles:
        over = triangles > args.max_triangles * 1.05
        under = triangles < args.max_triangles * args.min_fraction
        if over:
            failures.append(f"triangles {triangles} over budget {args.max_triangles}")
        gate("max_triangles", triangles, round(args.max_triangles * 1.05, 3), not over)
        if under:
            failures.append(f"triangles {triangles} under {args.min_fraction:g} x budget: collapsed mesh")
        gate("min_triangles", triangles, round(args.max_triangles * args.min_fraction, 3), not under)
    if triangles == 0:
        failures.append("no triangles")
    gate("triangles", triangles, 1, triangles != 0)
    if len(used_materials) > materials_limit:
        failures.append(f"{len(used_materials)} materials, limit {materials_limit}")
    gate("max_materials", len(used_materials), materials_limit, not len(used_materials) > materials_limit)
    if missing_attrs:
        failures.append(f"primitive without {', '.join(sorted(missing_attrs))}")
    gate("attributes", sorted(missing_attrs), [], not missing_attrs)
    for name in args.require:
        if name not in slots:
            failures.append(f"missing texture slot: {name}")
        gate(f"slot.{name}", name in slots, True, name in slots)
    if args.texture_size:
        over = False
        for image in images:
            if image["size"] and max(image["size"]) > args.texture_size:
                failures.append(f"image {image['index']} is {image['size']}, limit {args.texture_size}")
                over = True
        gate("texture_size", largest_side, args.texture_size, not over)
    if not bounded:
        failures.append(f"degenerate bounds {finite(extents)}")
    gate("bounds", finite(extents), 0, bounded)
    size_bytes = path.stat().st_size
    if args.max_bytes:
        if size_bytes > args.max_bytes:
            failures.append(f"file is {size_bytes} bytes, limit {args.max_bytes}")
        gate("max_bytes", size_bytes, args.max_bytes, not size_bytes > args.max_bytes)

    def over_limit(name, value, limit, ok, reason):
        """A ceiling or max_* column: a gate on a calibrated row, a warning on one that is not."""
        if calibrated:
            gate(name, value, limit, ok)
            if not ok:
                failures.append(f"{reason} (class {cls})")
        elif not ok:
            warnings.append(f"{reason} (not calibrated: reported, not gated)")

    def over_target(what, column, value, target):
        if value is not None and value > target * TARGET_SLACK:
            warnings.append(f"{what} {value} is over {column} {target} x {TARGET_SLACK:g}"
                            + ("" if calibrated else " (not calibrated)"))

    tri_ceiling = from_class("ceiling_tris", "max_triangles")
    if tri_ceiling is not None:
        over_limit("ceiling_tris", triangles, tri_ceiling, triangles <= tri_ceiling,
                   f"triangles {triangles} over ceiling_tris {tri_ceiling}")
    tri_target = from_class("target_tris", "max_triangles")
    if tri_target is not None:
        over_target("triangles", "target_tris", triangles, tri_target)
    tex_ceiling = from_class("ceiling_tex_px", "texture_size")
    if tex_ceiling is not None:
        over_limit("ceiling_tex_px", largest_side, tex_ceiling,
                   largest_side is None or largest_side <= tex_ceiling,
                   f"texture side {largest_side} over ceiling_tex_px {tex_ceiling}")
    tex_target = from_class("target_tex_px", "texture_size")
    if tex_target is not None:
        over_target("texture side", "target_tex_px", largest_side, tex_target)
    if tex_ceiling is not None or tex_target is not None:
        unknown = [image["index"] for image in images if not image["size"]]
        if unknown:
            warnings.append(f"images {unknown}: size not readable (not PNG or JPEG), not compared "
                            "with the class row")
    bone_limit = from_class("max_bones", None)
    if bone_limit is not None:
        bones = len({joint for skin in gltf.get("skins", []) if isinstance(skin, dict)
                     for joint in skin.get("joints", []) if isinstance(joint, int)})
        over_limit("max_bones", bones, bone_limit, bones <= bone_limit,
                   f"{bones} bones over max_bones {bone_limit}")
    mb_limit = from_class("max_mb", "max_bytes")
    if mb_limit is not None:
        megabytes = round(size_bytes / MB, 3)
        over_limit("max_mb", megabytes, mb_limit, size_bytes <= mb_limit * MB,
                   f"file is {megabytes} MB, over max_mb {mb_limit}")

    sha256 = sha256_file(path)
    params = {"max_triangles": args.max_triangles, "min_fraction": args.min_fraction,
              "max_materials": materials_limit, "texture_size": args.texture_size,
              "require": args.require, "max_bytes": args.max_bytes}
    if budget is not None:
        params.update(budgets=str(args.budgets), calibrated=budget.get("calibrated"),
                      preset=budget.get("preset"))
    record = {"tool": {"skill": "comfyui-asset-generation", "script": "inspect_glb.py"}, "kind": "mesh"}
    if cls:
        record["class"] = cls
    record.update({
        "params": params,
        "files": [{"path": str(path), "sha256": sha256, "bytes": size_bytes}],
        "gates": gates,
        "warnings": warnings,
        "verdict": "failed" if failures else "green",
    })

    passed = not failures and all(g["pass"] is True for g in gates)
    report = {
        "schema": "gate/1",
        "pass": passed,
        "ok": passed,
        "file": str(path),
        "bytes": size_bytes,
        "triangles": triangles,
        "primitives": primitives,
        "materials": len(used_materials),
        "double_sided": any(materials[i].get("doubleSided") for i in used_materials if i < len(materials)),
        "texture_slots": slots,
        "images": images,
        "bounds_min": finite(lo),
        "bounds_max": finite(hi),
        "extents": finite(extents),
        "extensions_required": gltf.get("extensionsRequired", []),
        "failures": failures,
        "gates": gates,
        "warnings": warnings,
        "sha256": sha256,
        "record": record,
    }
    return report, failures


def harness(path: Path, error: str) -> dict:
    """A gate/1 report for a file that could not be measured: pass false, no gates."""
    return {"schema": "gate/1", "pass": False, "ok": False, "gates": [], "file": str(path), "error": error}


def finish(obj: dict, code: int, json_out: Path | None, **dump) -> int:
    """Print the one JSON object, copy it to --json-out when given, pass the exit code through."""
    text = json.dumps(obj, allow_nan=False, **dump)
    print(text)
    if json_out is not None:
        try:
            json_out.parent.mkdir(parents=True, exist_ok=True)
            json_out.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"inspect_glb: --json-out {json_out} not written: {exc}", file=sys.stderr)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate a generated GLB against a game budget.")
    parser.add_argument("glb", type=Path)
    parser.add_argument("--max-triangles", type=int, default=None,
                        help="The face budget the graph was asked for (default 0: not checked)")
    parser.add_argument("--min-fraction", type=float, default=0.5)
    parser.add_argument("--max-materials", type=int, default=None, help="Default 1")
    parser.add_argument("--texture-size", type=int, default=None,
                        help="Largest allowed image side, px (default 0: not checked)")
    parser.add_argument(
        "--require",
        type=lambda value: [item for item in value.split(",") if item],
        default=[],
        help=f"Comma-separated slots that must be present: {', '.join(SLOTS)}",
    )
    parser.add_argument("--max-bytes", type=int, default=None, help="Default 0: not checked")
    parser.add_argument("--extract", type=Path, help="Write the embedded images into this directory")
    parser.add_argument("--class", dest="asset_class", metavar="CLASS",
                        help="The asset's class: labels the record; with --budgets, selects the row")
    parser.add_argument("--budgets", type=Path, metavar="FILE",
                        help="The project's ART_DIRECTION.md, holding the '3D budgets' table")
    parser.add_argument("--json-out", type=Path, help="Also write the printed object to this file")
    args = parser.parse_args()
    unknown = [name for name in args.require if name not in SLOTS]
    if unknown:
        parser.error(f"unknown slot(s): {', '.join(unknown)}")
    if args.budgets is not None and not args.asset_class:
        parser.error("--budgets needs --class")
    explicit = frozenset(name for name in DEFAULTS if getattr(args, name) is not None)
    for name, value in DEFAULTS.items():
        if getattr(args, name) is None:
            setattr(args, name, value)

    try:
        args.asset_class, budget, notes = load_budget(args.asset_class, args.budgets)
    except (OSError, ValueError) as exc:
        return finish(harness(args.glb, f"--budgets: {exc}"), 2, args.json_out)

    try:
        report, failures = inspect(args.glb, args, budget, explicit)
    except (OSError, ValueError, struct.error) as exc:
        return finish(harness(args.glb, str(exc)), 2, args.json_out)
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        return finish(harness(args.glb, f"malformed glTF: {type(exc).__name__}: {exc}"), 2, args.json_out)
    report["warnings"][:0] = notes
    return finish(report, 1 if failures else 0, args.json_out, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
