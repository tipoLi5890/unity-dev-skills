#!/usr/bin/env python3
"""psd_write.py — write a layered 8-bit RGB .psd or .psb from RGBA PNGs, without Photoshop.

Follows Adobe's "Photoshop File Formats Specification" (PSD version 1, PSB version 2: 8-byte
section lengths and 4-byte RLE row counts). Per layer: the pascal name, `luni` (the Unicode name),
`lyid` (the layer id, which Unity's PSD Importer maps on by default) and, for groups, `lsct`
section dividers, nested. Pixels are PackBits RLE. The merged composite is written as well.

  psd_write.py MANIFEST.json OUT.psb          .psd or .psb by the extension
  psd_write.py read FILE.psd                  the layer tree as JSON (this file's own reader)
  psd_write.py --selftest                     write, read back, compare; no network

MANIFEST (top to bottom, as the Layers panel lists them):
  {"width": W, "height": H, "ids": "ids.json",
   "layers": [{"name": "head", "png": "head.png", "x": 0, "y": 0, "hidden": false},
              {"name": "Face", "open": true, "group": [ ...same shape... ]}]}
A layer PNG is canvas-sized (x = y = 0) or a crop placed at x, y. Ids come from the ids file when
it names the layer, else a new id is allocated and saved back: a layer keeps its id on every
re-export, and a renamed layer is a new layer. Layer names must be unique (the importer and Cubism
both map by them). Next to OUT the merged picture is saved as OUT.composite.png.

Exit codes: 0 written, read or selftest passed; 1 usage error or refused manifest (duplicate or
empty names, a missing PNG); 2 selftest failed. Stdlib + numpy + Pillow; psd-tools is used by the
selftest only when it is installed, as a second reader.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

_LONG_KEYS_PSB = {b"LMsk", b"Lr16", b"Lr32", b"Layr", b"Mt16", b"Mt32", b"Mtrn", b"Alph", b"FMsk",
                  b"lnk2", b"FEid", b"FXid", b"PxSD"}
DIVIDER = "</Layer group>"


class Refused(Exception):
    pass


# --------------------------------------------------------------------------------- encoding
def packbits(row: bytes) -> bytes:
    """Apple PackBits, as Photoshop's RLE uses it."""
    out = bytearray()
    n, i = len(row), 0
    while i < n:
        j = i
        while j + 1 < n and row[j + 1] == row[i] and j - i < 127:
            j += 1
        if j > i:                                   # a run of row[i], length 2..128
            out.append((257 - (j - i + 1)) & 0xFF)
            out.append(row[i])
            i = j + 1
            continue
        j = i                                       # a literal stretch until a run of 3 begins
        while j < n and j - i < 128:
            if j + 2 < n and row[j] == row[j + 1] == row[j + 2]:
                break
            j += 1
        out.append(j - i - 1)
        out += row[i:j]
        i = j
    return bytes(out)


def unpackbits(data: bytes, size: int) -> bytes:
    out = bytearray()
    i = 0
    while len(out) < size and i < len(data):
        h = data[i]
        i += 1
        if h < 128:
            out += data[i:i + h + 1]
            i += h + 1
        elif h > 128:
            out += bytes([data[i]]) * (257 - h)
            i += 1
    return bytes(out[:size])


def rle_plane(plane: np.ndarray, psb: bool) -> tuple[bytes, bytes]:
    """(row byte counts, data) for one 2-D uint8 plane."""
    rows = [packbits(plane[r].tobytes()) for r in range(plane.shape[0])]
    fmt = ">%d%s" % (len(rows), "I" if psb else "H")
    return struct.pack(fmt, *[len(r) for r in rows]), b"".join(rows)


def pascal(name: str, pad: int) -> bytes:
    b = name.encode("latin-1", "replace")[:255]
    s = bytes([len(b)]) + b
    while len(s) % pad:
        s += b"\0"
    return s


def block(key: bytes, data: bytes, psb: bool) -> bytes:
    if len(data) % 2:
        data += b"\0"
    ln = struct.pack(">Q", len(data)) if (psb and key in _LONG_KEYS_PSB) else struct.pack(">I", len(data))
    return b"8BIM" + key + ln + data


def luni(name: str) -> bytes:
    u = name.encode("utf-16-be")
    d = struct.pack(">I", len(u) // 2) + u
    while len(d) % 4:
        d += b"\0"
    return d


class Layer:
    def __init__(self, name, rgba=None, x=0, y=0, hidden=False, section=0, lid=0):
        self.name, self.rgba, self.x, self.y = name, rgba, x, y
        self.hidden, self.section, self.lid = hidden, section, lid


def _alloc(ids: dict, nextid: list) -> int:
    v = nextid[0]
    nextid[0] += 1
    return v


def check_names(items, seen=None, where="layers") -> set:
    """Refuse empty or repeated names anywhere in the tree (groups included)."""
    seen = set() if seen is None else seen
    for it in items:
        name = it.get("name") if isinstance(it, dict) else None
        if not isinstance(name, str) or not name.strip():
            raise Refused(f"{where}: a layer without a name")
        if name in seen:
            raise Refused(f"{where}: the name {name!r} is used twice; names are the identity")
        if name == DIVIDER:
            raise Refused(f"{where}: {DIVIDER!r} is reserved")
        seen.add(name)
        if "group" in it:
            check_names(it["group"], seen, f"{where}/{name}")
    return seen


def flatten(items, base: Path, ids: dict, nextid: list, out: list) -> None:
    """items top to bottom; out gets records bottom to top (file order)."""
    for it in reversed(items):
        name = it["name"]
        if name not in ids:
            ids[name] = _alloc(ids, nextid)
        if "group" in it:
            key = "</" + name + ">"
            if key not in ids:
                ids[key] = _alloc(ids, nextid)
            out.append(Layer(DIVIDER, section=3, lid=ids[key]))
            flatten(it["group"], base, ids, nextid, out)
            out.append(Layer(name, section=1 if it.get("open", True) else 2, lid=ids[name],
                             hidden=bool(it.get("hidden", False))))
            continue
        png = base / it["png"]
        if not png.is_file():
            raise Refused(f"layer {name!r}: {png} not found")
        a = np.asarray(Image.open(png).convert("RGBA"))
        x, y = int(it.get("x", 0)), int(it.get("y", 0))
        ys, xs = np.nonzero(a[..., 3])
        if len(ys):                                   # crop to the opaque box: same placement, smaller file
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            a = a[y0:y1, x0:x1]
            x, y = x + int(x0), y + int(y0)
        else:
            a = a[:0, :0]
        out.append(Layer(name, a, x, y, bool(it.get("hidden", False)), lid=ids[name]))


def composite(records, w, h) -> np.ndarray:
    """Normal 'over' blend of the visible pixel layers, bottom to top; a hidden group hides its
    children."""
    acc = np.zeros((h, w, 4), np.float32)
    hidden_depth = []                                   # stack of (group hidden?) while walking
    for L in records:
        if L.section == 3:
            hidden_depth.append(None)                   # opened; the group record closes it
            continue
        if L.section in (1, 2):
            if hidden_depth:
                hidden_depth.pop()
            continue
        if L.hidden or L.rgba is None or L.rgba.size == 0:
            continue
        hh, ww = L.rgba.shape[:2]
        x0, y0, x1, y1 = max(L.x, 0), max(L.y, 0), min(L.x + ww, w), min(L.y + hh, h)
        if x1 <= x0 or y1 <= y0:
            continue
        src = L.rgba[y0 - L.y:y1 - L.y, x0 - L.x:x1 - L.x].astype(np.float32) / 255
        dst = acc[y0:y1, x0:x1]
        sa, da = src[..., 3:4], dst[..., 3:4]
        oa = sa + da * (1 - sa)
        rgb = np.where(oa > 0, (src[..., :3] * sa + dst[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6), 0)
        acc[y0:y1, x0:x1] = np.concatenate([rgb, oa], -1)
    return (acc * 255 + 0.5).clip(0, 255).astype(np.uint8)


def _hidden_groups(records) -> list:
    """Records with the children of hidden groups marked hidden, for the composite."""
    out, stack = [], []
    # walk top-down (reverse file order): a group record precedes its children
    for L in reversed(records):
        if L.section in (1, 2):
            stack.append(L.hidden or (stack[-1] if stack else False))
            out.append(L)
            continue
        if L.section == 3:
            if stack:
                stack.pop()
            out.append(L)
            continue
        if stack and stack[-1] and not L.hidden:
            L = Layer(L.name, L.rgba, L.x, L.y, True, 0, L.lid)
        out.append(L)
    return list(reversed(out))


def write(path: Path, w: int, h: int, records: list, psb: bool) -> np.ndarray:
    L4 = ">Q" if psb else ">I"
    recs, chans = bytearray(), bytearray()
    for L in records:
        flags = (0x02 if L.hidden else 0) | 0x08
        if L.rgba is None or L.rgba.size == 0:
            top = left = bottom = right = 0
            planes = [(-1, None), (0, None), (1, None), (2, None)]
        else:
            hh, ww = L.rgba.shape[:2]
            top, left, bottom, right = L.y, L.x, L.y + hh, L.x + ww
            planes = [(-1, L.rgba[..., 3]), (0, L.rgba[..., 0]), (1, L.rgba[..., 1]), (2, L.rgba[..., 2])]
        cinfo = bytearray()
        for cid, p in planes:
            if p is None:
                data = struct.pack(">H", 0)
            else:
                counts, d = rle_plane(np.ascontiguousarray(p), psb)
                data = struct.pack(">H", 1) + counts + d
            chans += data
            cinfo += struct.pack(">h", cid) + struct.pack(L4, len(data))
        extra = struct.pack(">I", 0) + struct.pack(">I", 0) + pascal(L.name, 4)
        extra += block(b"luni", luni(L.name), psb)
        extra += block(b"lyid", struct.pack(">I", L.lid), psb)
        if L.section:
            extra += block(b"lsct", struct.pack(">I", L.section), psb)
        recs += struct.pack(">iiiiH", top, left, bottom, right, len(planes)) + cinfo
        recs += b"8BIMnorm" + bytes([255, 0, flags, 0]) + struct.pack(">I", len(extra)) + extra
    info = struct.pack(">h", len(records)) + recs + chans
    if len(info) % 4:
        info += b"\0" * (4 - len(info) % 4)
    lmi = struct.pack(L4, len(info)) + info + struct.pack(">I", 0)       # + empty global mask info
    comp = composite(_hidden_groups(records), w, h)
    counts, datas = [], []
    for c in range(4):
        cnt, d = rle_plane(np.ascontiguousarray(comp[..., c]), psb)
        counts.append(cnt)
        datas.append(d)
    with open(path, "wb") as f:
        f.write(b"8BPS" + struct.pack(">H", 2 if psb else 1) + b"\0" * 6)
        f.write(struct.pack(">HIIHH", 4, h, w, 8, 3))                 # RGB + transparency, 8 bit
        f.write(struct.pack(">I", 0))                                 # colour mode data
        f.write(struct.pack(">I", 0))                                 # image resources
        f.write(struct.pack(L4, len(lmi)) + lmi)
        f.write(struct.pack(">H", 1) + b"".join(counts) + b"".join(datas))
    return comp


def write_manifest(man_path: Path, out: Path) -> dict:
    """Write OUT from a manifest; returns a summary. Raises Refused on a bad manifest."""
    m = json.loads(man_path.read_text(encoding="utf-8"))
    for k in ("width", "height", "layers"):
        if k not in m:
            raise Refused(f"manifest: missing {k!r}")
    check_names(m["layers"])
    base = man_path.parent
    ids_path = base / m["ids"] if m.get("ids") else None
    ids = json.loads(ids_path.read_text(encoding="utf-8")) if ids_path and ids_path.exists() else {}
    nextid = [max(ids.values(), default=1) + 1]
    records: list = []
    flatten(m["layers"], base, ids, nextid, records)
    comp = write(out, int(m["width"]), int(m["height"]), records, out.suffix.lower() == ".psb")
    if ids_path:
        ids_path.write_text(json.dumps(ids, indent=1, sort_keys=True), encoding="utf-8")
    Image.fromarray(comp).save(out.with_suffix(".composite.png"))
    return {"out": str(out), "layers": sum(1 for r in records if not r.section),
            "groups": sum(1 for r in records if r.section in (1, 2)), "bytes": out.stat().st_size}


# ----------------------------------------------------------------------------------- reading
def read(path: Path) -> dict:
    """Parse what this writer writes (and plain Photoshop RGB files): header, layer records with
    names, ids, flags, groups, pixels, and the merged image."""
    b = Path(path).read_bytes()
    if b[:4] != b"8BPS":
        raise ValueError("not a PSD/PSB file")
    ver = struct.unpack(">H", b[4:6])[0]
    psb = ver == 2
    nch, h, w, depth, mode = struct.unpack(">HIIHH", b[12:26])
    p = 26
    p += 4 + struct.unpack(">I", b[p:p + 4])[0]                      # colour mode data
    p += 4 + struct.unpack(">I", b[p:p + 4])[0]                      # image resources
    L4, n4 = (">Q", 8) if psb else (">I", 4)
    lmi_len = struct.unpack(L4, b[p:p + n4])[0]
    p += n4
    lmi_end = p + lmi_len
    info_len = struct.unpack(L4, b[p:p + n4])[0]
    p += n4
    layers = []
    if info_len:
        count = abs(struct.unpack(">h", b[p:p + 2])[0])
        p += 2
        for _ in range(count):
            top, left, bottom, right, nc = struct.unpack(">iiiiH", b[p:p + 18])
            p += 18
            chans = []
            for _ in range(nc):
                cid = struct.unpack(">h", b[p:p + 2])[0]
                ln = struct.unpack(L4, b[p + 2:p + 2 + n4])[0]
                chans.append((cid, ln))
                p += 2 + n4
            sig, blend = b[p:p + 4], b[p + 4:p + 8]
            opacity, _clip, flags = b[p + 8], b[p + 9], b[p + 10]
            extra_len = struct.unpack(">I", b[p + 12:p + 16])[0]
            ex = b[p + 16:p + 16 + extra_len]
            p += 16 + extra_len
            q = 4 + struct.unpack(">I", ex[0:4])[0]                   # layer mask data
            q += 4 + struct.unpack(">I", ex[q:q + 4])[0]               # blending ranges
            nlen = ex[q]
            name = ex[q + 1:q + 1 + nlen].decode("latin-1")
            q += (1 + nlen + 3) // 4 * 4
            rec = {"name": name, "box": [left, top, right, bottom], "opacity": opacity,
                   "blend": blend.decode("latin-1"), "hidden": bool(flags & 0x02), "chans": chans,
                   "section": 0, "id": None, "signature_ok": sig == b"8BIM"}
            while q + 12 <= len(ex):
                if ex[q:q + 4] not in (b"8BIM", b"8B64"):
                    break
                key = ex[q + 4:q + 8]
                if psb and key in _LONG_KEYS_PSB:
                    ln = struct.unpack(">Q", ex[q + 8:q + 16])[0]
                    q += 16
                else:
                    ln = struct.unpack(">I", ex[q + 8:q + 12])[0]
                    q += 12
                data = ex[q:q + ln]
                q += ln + (ln % 2)
                if key == b"luni":
                    nu = struct.unpack(">I", data[:4])[0]
                    rec["name"] = data[4:4 + 2 * nu].decode("utf-16-be")
                elif key == b"lyid":
                    rec["id"] = struct.unpack(">I", data[:4])[0]
                elif key in (b"lsct", b"lsdk"):
                    rec["section"] = struct.unpack(">I", data[:4])[0]
            layers.append(rec)
        for rec in layers:                                            # channel image data
            left, top, right, bottom = rec["box"]
            lw, lh = right - left, bottom - top
            planes = {}
            for cid, ln in rec.pop("chans"):
                comp = struct.unpack(">H", b[p:p + 2])[0]
                data = b[p + 2:p + ln]
                p += ln
                if lw <= 0 or lh <= 0:
                    continue
                if comp == 0:
                    planes[cid] = np.frombuffer(data[:lw * lh], np.uint8).reshape(lh, lw)
                elif comp == 1:
                    cw = 4 if psb else 2
                    counts = struct.unpack(">%d%s" % (lh, "I" if psb else "H"), data[:lh * cw])
                    o = lh * cw
                    rows = []
                    for c in counts:
                        rows.append(np.frombuffer(unpackbits(data[o:o + c], lw), np.uint8))
                        o += c
                    planes[cid] = np.stack(rows)
            if planes and lw > 0 and lh > 0:
                z = np.zeros((lh, lw), np.uint8)
                rec["rgba"] = np.dstack([planes.get(0, z), planes.get(1, z), planes.get(2, z),
                                         planes.get(-1, np.full((lh, lw), 255, np.uint8))])
            else:
                rec["rgba"] = None
    p = lmi_end
    comp = struct.unpack(">H", b[p:p + 2])[0]
    p += 2
    merged = None
    if comp == 1:
        cw = 4 if psb else 2
        counts = struct.unpack(">%d%s" % (h * nch, "I" if psb else "H"), b[p:p + h * nch * cw])
        o = p + h * nch * cw
        planes = []
        for c in range(nch):
            rows = []
            for r in range(h):
                n = counts[c * h + r]
                rows.append(np.frombuffer(unpackbits(b[o:o + n], w), np.uint8))
                o += n
            planes.append(np.stack(rows))
        merged = np.dstack(planes)
    return {"version": ver, "psb": psb, "channels": nch, "width": w, "height": h, "depth": depth,
            "mode": mode, "records": layers, "merged": merged}


def tree(doc: dict) -> list:
    """Records (file order, bottom to top) -> the top-to-bottom tree of names, ids and flags."""
    root: list = []
    stack = [root]
    for rec in reversed(doc["records"]):
        if rec["section"] in (1, 2):
            node = {"name": rec["name"], "id": rec["id"], "hidden": rec["hidden"],
                    "open": rec["section"] == 1, "group": []}
            stack[-1].append(node)
            stack.append(node["group"])
        elif rec["section"] == 3:
            if len(stack) > 1:
                stack.pop()
        else:
            stack[-1].append({"name": rec["name"], "id": rec["id"], "hidden": rec["hidden"],
                              "box": rec["box"]})
    return root


# ---------------------------------------------------------------------------------- selftest
def selftest() -> int:
    checks = {}
    rng = np.random.default_rng(3)
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        W, H = 96, 64

        def png(name, box, colour, alpha=255):
            a = np.zeros((H, W, 4), np.uint8)
            x0, y0, x1, y1 = box
            a[y0:y1, x0:x1, :3] = colour
            a[y0:y1, x0:x1, 3] = alpha
            a[y0 + 2:y0 + 4, x0:x1, :3] = rng.integers(0, 255, (2, x1 - x0, 3))   # literals for RLE
            Image.fromarray(a).save(t / f"{name}.png")
            return a

        arrays = {"head": png("head", (30, 4, 66, 30), (230, 190, 160)),
                  "hair": png("hair", (28, 2, 68, 14), (60, 40, 30)),
                  "torso": png("torso", (24, 26, 72, 60), (20, 180, 190)),
                  "mouth_inside": png("mouth_inside", (40, 20, 56, 26), (120, 20, 30)),
                  "soft": png("soft", (0, 0, 20, 20), (255, 255, 255), alpha=128)}
        man = {"width": W, "height": H, "ids": "ids.json", "layers": [
            {"name": "Head", "group": [{"name": "hair", "png": "hair.png"},
                                       {"name": "Mouth", "hidden": True,
                                        "group": [{"name": "mouth_inside", "png": "mouth_inside.png"}]},
                                       {"name": "head", "png": "head.png"}]},
            {"name": "Körper 身体", "group": [{"name": "torso", "png": "torso.png"}], "open": False},
            {"name": "soft", "png": "soft.png"}]}
        (t / "m.json").write_text(json.dumps(man), encoding="utf-8")
        docs = {}
        for ext in ("psd", "psb"):
            write_manifest(t / "m.json", t / f"a.{ext}")
            docs[ext] = read(t / f"a.{ext}")
        d = docs["psd"]
        checks["header"] = (d["version"], docs["psb"]["version"], d["channels"], d["depth"], d["mode"],
                            d["width"], d["height"]) == (1, 2, 4, 8, 3, W, H)
        tr = tree(d)
        names = [n["name"] for n in tr]
        checks["tree_order"] = names == ["Head", "Körper 身体", "soft"] and \
            [n["name"] for n in tr[0]["group"]] == ["hair", "Mouth", "head"]
        checks["unicode_name"] = tr[1]["name"] == "Körper 身体" and tr[1]["open"] is False
        checks["hidden_group"] = tr[0]["group"][1]["hidden"] is True
        ids = json.loads((t / "ids.json").read_text(encoding="utf-8"))
        checks["ids_match_file"] = tr[0]["group"][0]["id"] == ids["hair"] and tr[1]["id"] == ids["Körper 身体"]
        checks["ids_unique"] = len(set(ids.values())) == len(ids)
        ok_px = True
        for ext, doc in docs.items():
            for rec in doc["records"]:
                if rec["section"] or rec.get("rgba") is None:
                    continue
                x0, y0, x1, y1 = rec["box"]
                ok_px &= bool(np.array_equal(rec["rgba"], arrays[rec["name"]][y0:y1, x0:x1]))
        checks["pixels_roundtrip"] = ok_px
        merged = d["merged"]
        expect = np.zeros((H, W, 4), np.float32)
        for n in ("soft", "torso", "head", "hair"):           # bottom to top; mouth is hidden
            s = arrays[n].astype(np.float32) / 255
            sa, da = s[..., 3:4], expect[..., 3:4]
            oa = sa + da * (1 - sa)
            expect = np.concatenate([np.where(oa > 0, (s[..., :3] * sa + expect[..., :3] * da * (1 - sa))
                                              / np.maximum(oa, 1e-6), 0), oa], -1)
        expect = (expect * 255 + 0.5).clip(0, 255).astype(np.uint8)
        checks["merged_composite"] = merged is not None and int(np.abs(merged.astype(int) - expect).max()) <= 1
        checks["merged_psb_equal"] = docs["psb"]["merged"] is not None and np.array_equal(docs["psb"]["merged"], merged)
        # re-export keeps ids; a rename is a new id
        write_manifest(t / "m.json", t / "b.psd")
        checks["ids_stable"] = tree(read(t / "b.psd")) == tr
        man["layers"][2]["name"] = "soft_renamed"
        (t / "m.json").write_text(json.dumps(man), encoding="utf-8")
        write_manifest(t / "m.json", t / "c.psd")
        tr_c = tree(read(t / "c.psd"))
        checks["rename_new_id"] = tr_c[2]["id"] not in {v for k, v in ids.items()} and tr_c[0] == tr[0]
        man["layers"][2]["name"] = "hair"
        (t / "m.json").write_text(json.dumps(man), encoding="utf-8")
        try:
            write_manifest(t / "m.json", t / "d.psd")
            checks["duplicate_refused"] = False
        except Refused:
            checks["duplicate_refused"] = True
        checks["packbits_roundtrip"] = all(
            unpackbits(packbits(bytes(r)), len(r)) == bytes(r)
            for r in (b"", b"\x00", b"\x01" * 300, bytes(rng.integers(0, 3, 517).astype(np.uint8))))
        try:                                                  # a second reader, when installed
            from psd_tools import PSDImage
            ps = PSDImage.open(t / "a.psb")
            top = [lyr.name for lyr in ps]
            mouth = [g for g in ps.descendants() if g.name == "Mouth"]
            checks["psd_tools_reads"] = sorted(top) == sorted(names) and len(mouth) == 1 \
                and not mouth[0].visible and ps.version == 2
        except ImportError:
            pass
    ok = all(checks.values())
    print(json.dumps({"checks": checks, "pass": ok}))
    return 0 if ok else 2


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1, never 2."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["--selftest"], ["selftest"]):
        return selftest()
    if argv[:1] == ["read"]:
        ap = UsageParser(prog="psd_write.py read")
        ap.add_argument("file", type=Path)
        a = ap.parse_args(argv[1:])
        if not a.file.is_file():
            ap.error(f"not found: {a.file}")
        doc = read(a.file)
        print(json.dumps({"version": doc["version"], "width": doc["width"], "height": doc["height"],
                          "depth": doc["depth"], "mode": doc["mode"], "layers": tree(doc)}, ensure_ascii=False))
        return 0
    ap = UsageParser(prog="psd_write.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("out", type=Path, help=".psd or .psb")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.out.suffix.lower() not in (".psd", ".psb"):
        ap.error("OUT must end in .psd or .psb")
    if not a.manifest.is_file():
        ap.error(f"manifest not found: {a.manifest}")
    try:
        print(json.dumps(write_manifest(a.manifest, a.out)))
    except Refused as e:
        print(f"psd_write.py: refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
