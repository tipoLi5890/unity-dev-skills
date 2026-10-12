#!/usr/bin/env python3
"""tiled_to_level.py — convert a Tiled orthogonal map (.tmj / .json) into the level JSON.

Handles a documented subset and stops on anything outside it, naming the feature:

  map       orthogonal, finite, square tiles
  layers    tile layers (plain array, or base64 with no / zlib / gzip compression) and object
            layers; no groups, no layer offsets; image layers only with --skip-image-layers
  tiles     global ids with the three flip flags decoded into the level's "flips" array
  objects   rectangles, points and tile objects, unrotated, each with a class (the "type" or
            "class" key); custom properties of type string, int, float, bool, color, file, object

Tile layer names must be Background, Ground, Walls, OneWay, Front or Markers (case-insensitive),
or be renamed with --layer Tiled=Level. Rows are flipped so row 0 is the bottom of the level, and
object pixels become cells. An object of class "spawn" becomes the spawn, "gate" the gate,
"pickup" a pickup; every other class becomes an entity. Mapping: `reference/external-editors.md`.

Prints the level JSON on stdout, or writes it with --out.

Exit codes: 0 converted · 1 the map converts but breaks a level rule (no spawn, two gates, an
object with no class, a duplicate id) · 2 usage error, unreadable file, or an unsupported
feature.

Examples:
  tiled_to_level.py maps/side-run-01.tmj --out Assets/Levels/side-run-01.json
  tiled_to_level.py maps/depot-01.tmj --view topdown --layer Floor=Ground --layer Shelves=Walls
  tiled_to_level.py maps/side-run-01.tmj --skip-image-layers | level_validate.py /dev/stdin \\
      --jump-height 2.85 --jump-distance 5.17 --fall-multiplier 1.5
"""
import argparse
import base64
import gzip
import json
import math
import os
import struct
import sys
import zlib

FLIP_H, FLIP_V, FLIP_D, ROT_HEX = 0x80000000, 0x40000000, 0x20000000, 0x10000000
GID_MASK = 0x0FFFFFFF
LAYER_NAMES = ("Background", "Ground", "Walls", "OneWay", "Front", "Markers")
SIMPLE_PROPERTIES = ("string", "int", "float", "bool", "color", "file", "object")
EPS = 1e-6


class Unsupported(Exception):
    """The map uses something outside the documented subset (exit 2)."""


def decode_gid(raw):
    """Split a Tiled global id into (tile id, flips): flips bit 1 horizontal, 2 vertical, 4 diagonal."""
    flips = (1 if raw & FLIP_H else 0) | (2 if raw & FLIP_V else 0) | (4 if raw & FLIP_D else 0)
    return raw & GID_MASK, flips


def layer_gids(layer, count):
    data, encoding = layer.get("data"), layer.get("encoding") or "csv"
    if "chunks" in layer:
        raise Unsupported("infinite map (layer '%s' is stored in chunks)" % layer.get("name"))
    if encoding == "base64":
        compression = layer.get("compression") or ""
        try:
            blob = base64.b64decode(data)
            if compression == "zlib":
                blob = zlib.decompress(blob)
            elif compression == "gzip":
                blob = gzip.decompress(blob)
            elif compression:
                raise Unsupported("'%s' compression on layer '%s' (use zlib, gzip or none)"
                                  % (compression, layer.get("name")))
            data = list(struct.unpack("<%dI" % (len(blob) // 4), blob))
        except (ValueError, OSError, zlib.error, struct.error) as e:
            raise Unsupported("undecodable data on layer '%s': %s" % (layer.get("name"), e))
    elif encoding != "csv" or not isinstance(data, list):
        raise Unsupported("'%s' encoding on layer '%s'" % (encoding, layer.get("name")))
    if len(data) != count:
        raise Unsupported("layer '%s' holds %d tiles, the map is %d: per-layer sizes"
                          % (layer.get("name"), len(data), count))
    return data


def tileset_names(tilesets):
    """[(firstgid, name)] sorted by firstgid, for naming the ids a map uses."""
    out = []
    for ts in tilesets:
        name = ts.get("name") or os.path.splitext(os.path.basename(ts.get("source") or "tiles"))[0]
        out.append((int(ts.get("firstgid", 1)), name))
    return sorted(out)


def tile_name(sets, gid):
    owner = None
    for first, name in sets:
        if first <= gid:
            owner = (first, name)
    return "%s#%d" % (owner[1], gid - owner[0]) if owner else "tile#%d" % gid


def fields_of(obj):
    fields = []
    for prop in obj.get("properties") or []:
        kind = prop.get("type") or "string"
        if kind not in SIMPLE_PROPERTIES:
            raise Unsupported("'%s'-typed property '%s' on object %s"
                              % (kind, prop.get("name"), obj.get("id")))
        value = prop.get("value")
        text = ("true" if value else "false") if kind == "bool" else str(value)
        fields.append({"key": prop.get("name"), "type": kind, "value": text})
    return fields


def convert(tiled, args):
    if tiled.get("orientation") != "orthogonal":
        raise Unsupported("'%s' orientation (orthogonal only; cell boards are built from "
                          "coordinates, not from this file)" % tiled.get("orientation"))
    if tiled.get("infinite"):
        raise Unsupported("infinite map (turn off Infinite in Map Properties)")
    w, h = int(tiled["width"]), int(tiled["height"])
    tw, th = int(tiled["tilewidth"]), int(tiled["tileheight"])
    if tw != th:
        raise Unsupported("non-square tiles (%d x %d px)" % (tw, th))

    rename = {}
    for pair in args.layer or []:
        if "=" not in pair:
            raise Unsupported("--layer wants Tiled=Level, got '%s'" % pair)
        src, dst = pair.split("=", 1)
        rename[src.lower()] = dst
    canonical = {n.lower(): n for n in LAYER_NAMES}

    sets = tileset_names(tiled.get("tilesets") or [])
    layers, used, snapped = {}, set(), 0
    spawns, gates, pickups, entities, problems, seen_ids = [], [], [], [], [], set()

    for layer in tiled.get("layers") or []:
        kind, name = layer.get("type"), layer.get("name") or ""
        if kind == "group":
            raise Unsupported("group layer '%s' (move its layers to the top level)" % name)
        if kind == "imagelayer":
            if args.skip_image_layers:
                continue
            raise Unsupported("image layer '%s' (pass --skip-image-layers to leave it out)" % name)
        if layer.get("offsetx") or layer.get("offsety"):
            raise Unsupported("layer offset on '%s'" % name)

        if kind == "tilelayer":
            target = canonical.get(rename.get(name.lower(), name).lower())
            if target is None:
                raise Unsupported("tile layer '%s' has no place in the layer stack (rename it, "
                                  "or pass --layer %s=Ground)" % (name, name or "Name"))
            if target in layers:
                raise Unsupported("two tile layers map to '%s'" % target)
            cells, flips = [0] * (w * h), [0] * (w * h)
            for i, raw in enumerate(layer_gids(layer, w * h)):
                gid, flip = decode_gid(raw)
                if gid == 0:
                    continue
                at = (i % w) + (h - 1 - i // w) * w          # Tiled row 0 is the top row
                cells[at], flips[at] = gid, flip
                used.add(gid)
            layers[target] = {"name": target, "cells": cells,
                              "flips": flips if any(flips) else []}

        elif kind == "objectgroup":
            for obj in layer.get("objects") or []:
                oid = obj.get("id")
                for shape in ("ellipse", "polygon", "polyline", "text", "template"):
                    if obj.get(shape):
                        raise Unsupported("%s object %s on layer '%s'" % (shape, oid, name))
                if obj.get("rotation"):
                    raise Unsupported("rotated object %s on layer '%s'" % (oid, name))
                px, py = float(obj.get("x", 0)), float(obj.get("y", 0))
                pw, ph = float(obj.get("width", 0)), float(obj.get("height", 0))
                # A tile object is anchored at its bottom-left; every other shape at its top-left.
                top, bottom = (py - ph, py) if "gid" in obj else (py, py + ph)
                x = int(math.floor(px / tw + EPS))
                if obj.get("point") or ph == 0:
                    y = h - 1 - int(math.floor(min(py, h * th - EPS) / th))
                else:
                    y = int(math.floor((h * th - bottom) / th + EPS))
                cw = max(1, int(math.ceil(pw / tw - EPS)))
                ch = max(1, int(math.ceil((bottom - top) / th - EPS)))
                if not obj.get("point") and any(
                        abs(v / s - round(v / s)) > 0.01 for v, s in
                        ((px, tw), (bottom, th), (pw, tw), (bottom - top, th))):
                    snapped += 1
                kind_name = obj.get("type") or obj.get("class") or ""
                if not kind_name:
                    problems.append("object %s on layer '%s' has no class" % (oid, name))
                    continue
                ident = obj.get("name") or "%s-%s" % (kind_name, oid)
                if ident in seen_ids:
                    problems.append("two objects are named '%s'" % ident)
                seen_ids.add(ident)
                entity = {"id": ident, "type": kind_name, "x": x, "y": y, "w": cw, "h": ch,
                          "fields": fields_of(obj)}
                if not (0 <= x < w and 0 <= y < h):
                    problems.append("object '%s' is outside the map at cell (%d, %d)" % (ident, x, y))
                if kind_name == "spawn":
                    spawns.append(entity)
                elif kind_name == "gate":
                    gates.append(entity)
                elif kind_name == "pickup":
                    pickups.append(entity)
                else:
                    entities.append(entity)
        else:
            raise Unsupported("'%s' layer '%s'" % (kind, name))

    if len(spawns) != 1:
        problems.append("the map has %d objects of class spawn, a level has exactly 1" % len(spawns))
    if len(gates) != 1:
        problems.append("the map has %d objects of class gate, a level has exactly 1" % len(gates))
    if problems:
        return None, problems, snapped

    level = {
        "format": "courier-level", "version": 1,
        "id": args.id or os.path.splitext(os.path.basename(args.map))[0],
        "view": args.view, "width": w, "height": h, "cellSize": args.cell_size,
        "tiles": [{"id": gid, "name": tile_name(sets, gid)} for gid in sorted(used)],
        "layers": [layers[n] for n in LAYER_NAMES if n in layers],
        "spawn": {"x": spawns[0]["x"], "y": spawns[0]["y"]},
        "gate": {"x": gates[0]["x"], "y": gates[0]["y"]},
        "pickups": pickups, "entities": entities,
    }
    return level, [], snapped


def build_parser():
    p = argparse.ArgumentParser(
        prog="tiled_to_level.py",
        description="Convert a Tiled orthogonal .tmj/.json map into the level JSON.",
        epilog="Exit 0 converted, 1 the map breaks a level rule, 2 usage error or unsupported "
               "feature.",
    )
    p.add_argument("map", help="a Tiled map saved or exported as JSON (.tmj, .json)")
    p.add_argument("--out", metavar="FILE", help="write the level here instead of stdout")
    p.add_argument("--id", help="the level id (default: the map's file name)")
    p.add_argument("--view", choices=("side", "topdown"), default="side",
                   help="how the level is searched and which layers collide (default side)")
    p.add_argument("--cell-size", type=float, default=1.0, metavar="UNITS",
                   help="world units per tile (default 1)")
    p.add_argument("--layer", action="append", metavar="TILED=LEVEL",
                   help="map a Tiled tile-layer name onto a layer of the stack; repeatable")
    p.add_argument("--skip-image-layers", action="store_true",
                   help="leave image layers out instead of stopping on them")
    p.add_argument("--indent", type=int, default=None, metavar="N",
                   help="pretty-print with this indent (default: one line)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.map.lower().endswith((".tmx", ".tsx")):
        print("ERROR %s is XML: export it as JSON first (File > Export As, .tmj)" % args.map,
              file=sys.stderr)
        return 2
    try:
        with open(args.map, encoding="utf-8") as f:
            tiled = json.load(f)
        level, problems, snapped = convert(tiled, args)
    except (OSError, ValueError) as e:
        print("ERROR cannot read %s: %s" % (args.map, e), file=sys.stderr)
        return 2
    except (KeyError, TypeError) as e:
        print("ERROR %s is not a Tiled map: missing or malformed %s" % (args.map, e),
              file=sys.stderr)
        return 2
    except Unsupported as e:
        print("ERROR unsupported: %s" % e, file=sys.stderr)
        return 2
    if snapped:
        print("NOTE %d object(s) were off the grid and snapped to cells" % snapped, file=sys.stderr)
    if problems:
        for line in problems:
            print("ERROR %s" % line, file=sys.stderr)
        return 1
    text = (json.dumps(level, separators=(",", ":")) if args.indent is None
            else json.dumps(level, indent=args.indent))
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError as e:
            print("ERROR cannot write %s: %s" % (args.out, e), file=sys.stderr)
            return 2
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
