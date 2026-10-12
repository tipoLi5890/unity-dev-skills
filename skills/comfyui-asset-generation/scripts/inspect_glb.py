#!/usr/bin/env python3
"""inspect_glb.py — the acceptance gate for a generated GLB.

A finished job proves a file exists, not that it is a game asset. This reads
the GLB container directly and checks what an engine import depends on:
triangle count against the budget the graph was asked for, one material, UVs
and normals on every primitive, the texture slots that were supposed to be
baked, texture dimensions, and sane bounds.

Stdlib only. Prints one JSON object; exit 0 = pass, 1 = a gate failed,
2 = the file could not be read.

Examples
  inspect_glb.py crate.glb --max-triangles 20000
  inspect_glb.py crate.glb --max-triangles 20000 --texture-size 2048 \
      --require base,normal,occlusion,metallic-roughness
  inspect_glb.py crate.glb --max-triangles 20000 --extract maps/   # write the embedded images out

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
"""
from __future__ import annotations

import argparse
import json
import math
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


def inspect(path: Path, args: argparse.Namespace) -> tuple[dict, list[str]]:
    gltf, binary = parse_glb(path)
    accessors = gltf.get("accessors", [])
    materials = gltf.get("materials", [])
    failures: list[str] = []

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

    if args.max_triangles:
        if triangles > args.max_triangles * 1.05:
            failures.append(f"triangles {triangles} over budget {args.max_triangles}")
        if triangles < args.max_triangles * args.min_fraction:
            failures.append(f"triangles {triangles} under {args.min_fraction:g} x budget: collapsed mesh")
    if triangles == 0:
        failures.append("no triangles")
    if len(used_materials) > args.max_materials:
        failures.append(f"{len(used_materials)} materials, limit {args.max_materials}")
    if missing_attrs:
        failures.append(f"primitive without {', '.join(sorted(missing_attrs))}")
    for name in args.require:
        if name not in slots:
            failures.append(f"missing texture slot: {name}")
    if args.texture_size:
        for image in images:
            if image["size"] and max(image["size"]) > args.texture_size:
                failures.append(f"image {image['index']} is {image['size']}, limit {args.texture_size}")
    if not all(math.isfinite(e) and e > 0 for e in extents):
        failures.append(f"degenerate bounds {extents}")
    size_bytes = path.stat().st_size
    if args.max_bytes and size_bytes > args.max_bytes:
        failures.append(f"file is {size_bytes} bytes, limit {args.max_bytes}")

    report = {
        "file": str(path),
        "bytes": size_bytes,
        "triangles": triangles,
        "primitives": primitives,
        "materials": len(used_materials),
        "double_sided": any(materials[i].get("doubleSided") for i in used_materials if i < len(materials)),
        "texture_slots": slots,
        "images": images,
        "bounds_min": lo,
        "bounds_max": hi,
        "extents": extents,
        "extensions_required": gltf.get("extensionsRequired", []),
        "failures": failures,
    }
    return report, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate a generated GLB against a game budget.")
    parser.add_argument("glb", type=Path)
    parser.add_argument("--max-triangles", type=int, default=0, help="The face budget the graph was asked for")
    parser.add_argument("--min-fraction", type=float, default=0.5)
    parser.add_argument("--max-materials", type=int, default=1)
    parser.add_argument("--texture-size", type=int, default=0, help="Largest allowed image side, px")
    parser.add_argument(
        "--require",
        type=lambda value: [item for item in value.split(",") if item],
        default=[],
        help=f"Comma-separated slots that must be present: {', '.join(SLOTS)}",
    )
    parser.add_argument("--max-bytes", type=int, default=0)
    parser.add_argument("--extract", type=Path, help="Write the embedded images into this directory")
    args = parser.parse_args()
    unknown = [name for name in args.require if name not in SLOTS]
    if unknown:
        parser.error(f"unknown slot(s): {', '.join(unknown)}")

    try:
        report, failures = inspect(args.glb, args)
    except (OSError, ValueError, KeyError, IndexError, struct.error) as exc:
        print(json.dumps({"file": str(args.glb), "error": str(exc)}))
        return 2
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
