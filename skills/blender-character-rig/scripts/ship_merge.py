#!/usr/bin/env python3
"""ship_merge.py — the ship track's mesh from a character in parts: one mesh, one material, one atlas per map.

Every part (body, head, hair, hands, eyeballs, ...) keeps its own UVs and its own texture; each texture
becomes a square tile of one atlas per map, and each part's UVs are scaled and offset into its tile.
Nothing is rebaked (the scale is uniform with no rotation, so tangent-space normals hold), so the
atlas is exact up to the resize. Runs before the rig: the ship track rigs once, on this mesh.

usage (Blender, headless):
    blender -b --factory-startup -P ship_merge.py -- PARTS.blend|PARTS.glb --out DIR [--name NAME]
            [--plan PLAN.parts.json] [--objects Body,Head,...] [--atlas 4096|2048] [--pad 8]
            [--separate hair,eyes] [--max-tris N] [--budgets ART_DIRECTION.md --class character]
            [--min-density 0.5] [--no-render] [--report PATH]
    blender -b --factory-startup -P ship_merge.py -- --selftest
    (the same through assemble_parts.py: `assemble_parts.py ship PARTS ...`)

input      a .blend: the mesh objects of collection Parts (assemble_parts.py's <c>_parts.blend), else
           every mesh object that renders, outside collection AnchorRef; a .glb: every mesh in it.
           --objects names them instead (comma-separated). Each part has one material.
plan       --plan (parts/1) gives each object its part (by name or region: Body -> body, Hand.R ->
           hand.R, Eye.L -> eyes) and so its budget_share; without it, shares are not checked.
tiles      one tile per distinct set of images (Head and Hair share one: the hair is split from the
           head job); a tile starts at the texture's own side (a power of two, at most the atlas).
           While the tiles do not fit, the tile with the highest texel density on the surface halves,
           mirrored pairs (L/R in the object name) together, never below atlas/16; then any tile that
           can double back to its own side without breaking the fit does, lowest density first.
           Power-of-two squares sorted by size pack a square atlas exactly. Each tile keeps --pad
           pixels (default 8) of its texture's border repeated around it, so mip levels do not bleed.
maps       base colour (sRGB); normal (flat where a part has none); ORM (R occlusion, G roughness,
           B metallic, from the part's glTF metallic-roughness and occlusion images, or its factors)
           when any part has one. --atlas is the side: 2048 or 4096; default the budget row's
           target_tex_px (a calibrated row), else 4096.
UVs        faces whose corners lie in two UV cells (a seam across 0/1) are refused (exit 1); a face
           wholly in another cell is moved back into 0..1.
merge      every part not named in --separate (by part or region: hair, eyes) joins one mesh with a
           vertex group part.<part> each; separated parts stay their own objects with the same
           material. By default the hair joins: character-autorig's secondary stage finds hair spikes
           on a fused mesh (as on the anchor alone), and Unity draws one mesh with one material.
gates      ship.materials (1); ship.uv_in_tiles (every face's UVs inside its tile, 1.0);
           ship.density (each part's tile side / its texture's side >= --min-density, default 0.5: one
           halving; the texels per unit measured on the surface before and after are reported);
           ship.triangles and ship.tris.<part> (each part <= budget_share x the limit) when a limit
           is known: --max-tris, or a calibrated row's ceiling_tris; a calibrated row's
           target_tris x 1.25 only warns, and with neither nothing is checked (counts reported);
           ship.inspect_glb: comfyui-asset-generation inspect_glb.py on the GLB (--max-materials 1,
           --require base and normal when a part had one, the row and --max-tris passed on).
outputs    DIR/<name>_ship.glb, <name>_ship.blend, atlas_basecolor.png, atlas_normal.png,
           atlas_orm.png (when any), <name>.ship.gate.json, inspect_glb.json, and unless --no-render
           merge.png (front, three-quarter, face close-up; the hands when there are hands; the atlas).

Report: gate/1 (schemas/gate-1.json). Exit codes: 0 every gate passed (or --selftest passed); 2 a
gate failed; 1 usage error or refused input (no parts, a part with two materials, straddling UVs, tiles
that cannot fit) or a failed --selftest. Arguments are parsed before bpy or numpy is imported.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
INSPECT = os.path.normpath(os.path.join(HERE, "..", "..", "comfyui-asset-generation", "scripts", "inspect_glb.py"))
ATLAS_SIDES = (2048, 4096)
MIN_TILE_DIV = 16          # no tile under atlas / 16
SIDE_TOKENS = {"l", "r", "left", "right"}
UV_TOL = 2e-3              # a corner this far past its UV cell still belongs to it (clamped back)


class Refused(Exception):
    pass


class UsageParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser(prog="ship_merge.py"):
    p = UsageParser(prog=prog, description=__doc__.split("\n")[0],
                    epilog="Exit codes: 0 pass, 2 a gate failed, 1 usage error or refused input.")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("parts", nargs="?", help="the assembly .blend or a .glb of the parts")
    p.add_argument("--out")
    p.add_argument("--name", help="default: the plan's character, else the file's stem")
    p.add_argument("--plan", help="parts/1: each object's part and budget_share")
    p.add_argument("--objects", help="comma-separated object names (default: collection Parts)")
    p.add_argument("--atlas", type=int, choices=ATLAS_SIDES)
    p.add_argument("--pad", type=int, default=8)
    p.add_argument("--separate", default="", help="parts or regions kept as their own objects, e.g. hair,eyes")
    p.add_argument("--max-tris", type=int, default=0, help="the hard triangle limit of the whole character")
    p.add_argument("--budgets", help="the project's ART_DIRECTION.md ('3D budgets' table)")
    p.add_argument("--class", dest="cls", default="character")
    p.add_argument("--min-density", type=float, default=0.5)
    p.add_argument("--no-render", action="store_true")
    p.add_argument("--report", help="also write the gate/1 report here")
    return p


def _np():
    import numpy as np
    return np


def gate(name, value, limit, passed, **extra):
    return {"name": name, "value": value, "limit": limit, "pass": bool(passed), **extra}


def r4(x):
    return None if x is None else round(float(x), 4)


def pow2_floor(n):
    return 1 << max(0, int(math.floor(math.log2(max(1, n)))))


def norm_name(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def tokens(name):
    return [t for t in re.split(r"[^a-z0-9]+", re.sub(r"\.\d{3}$", "", name).lower()) if t]


def pair_key(name):
    """The object's name without its side: Hand.R.T and Hand.L.T share 'hand t'."""
    return " ".join(t for t in tokens(name) if t not in SIDE_TOKENS)


# --------------------------------------------------------------------------------------- tiles
def plan_tiles(groups, atlas, min_tile=None):
    """groups: [{key, src, density, pair}] (density: texels per unit at the source side). Returns
    {key: tile side}. Halve the densest tile (and its mirrored pair) while the areas exceed the
    atlas, never below min_tile; then double back, lowest density first, while it still fits."""
    min_tile = min_tile or max(64, atlas // MIN_TILE_DIV)
    want = {g["key"]: min(pow2_floor(g["src"]), atlas) for g in groups}
    tile = dict(want)
    dens = {g["key"]: g["density"] for g in groups}
    src = {g["key"]: g["src"] for g in groups}
    pairs = {}
    for g in groups:
        pairs.setdefault(g["pair"], []).append(g["key"])
    mates = {k: pairs[g["pair"]] for g in groups for k in [g["key"]]}

    def area():
        return sum(t * t for t in tile.values())

    def d_now(k):
        return dens[k] * tile[k] / max(src[k], 1)

    while area() > atlas * atlas:
        cand = [k for k in tile if tile[k] > min_tile]
        if not cand:
            raise Refused(f"the tiles cannot fit a {atlas} atlas even at {min_tile} px each: fewer parts or a "
                          "larger atlas")
        k = max(cand, key=lambda q: (d_now(q), tile[q]))
        for m in mates[k]:
            if tile[m] > min_tile:
                tile[m] //= 2
    grew = True
    while grew:
        grew = False
        for k in sorted(tile, key=d_now):
            group = [m for m in mates[k] if tile[m] * 2 <= want[m]]
            if not group or len(group) != len(mates[k]):
                continue
            extra = sum(3 * tile[m] * tile[m] for m in group)
            if area() + extra <= atlas * atlas:
                for m in group:
                    tile[m] *= 2
                grew = True
                break
    return tile


def place_tiles(tile, atlas):
    """{key: side} -> {key: (x0, y0)} in pixels from the atlas's bottom-left (Blender's UV origin):
    quadtree placement, largest first; exact for power-of-two squares whose areas fit."""
    free = [(0, 0, atlas)]
    out = {}
    for k in sorted(tile, key=lambda q: (-tile[q], str(q))):
        t = tile[k]
        free.sort(key=lambda f: (f[2], f[1], f[0]))
        i = next((j for j, f in enumerate(free) if f[2] >= t), None)
        if i is None:
            raise Refused(f"no room left for a {t} px tile")
        x, y, s = free.pop(i)
        while s > t:
            s //= 2
            free += [(x + s, y, s), (x, y + s, s), (x + s, y + s, s)]
        out[k] = (x, y)
    return out


# ------------------------------------------------------------------------------- Blender reading
def _links_to(node_tree, node, socket_name):
    return [l for l in node_tree.links if l.to_node == node and l.to_socket.name == socket_name]


def _upstream_image(node_tree, start_links, want=None):
    """The first image node reached walking back from these links (through any nodes); want filters
    the node directly before the image (e.g. SEPARATE_COLOR, NORMAL_MAP)."""
    stack = [(l.from_node, l) for l in start_links]
    seen = set()
    while stack:
        n, _ = stack.pop()
        if n.name in seen:
            continue
        seen.add(n.name)
        if n.type == 'TEX_IMAGE' and n.image is not None and all(n.image.size):
            return n.image
        for inp in n.inputs:
            stack += [(l.from_node, l) for l in node_tree.links if l.to_socket == inp]
    return None


def material_maps(mat):
    """{base, normal, mr, occ: image or None; base_rgb, roughness, metallic: factors} of a material's
    first Principled BSDF, read the way the glTF importer builds it (nodes found by type)."""
    out = {"base": None, "normal": None, "mr": None, "occ": None, "base_rgb": (0.8, 0.8, 0.8),
           "roughness": 0.5, "metallic": 0.0}
    if mat is None or not mat.node_tree:
        return out
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        return out
    out["base_rgb"] = tuple(bsdf.inputs["Base Color"].default_value)[:3]
    out["roughness"] = float(bsdf.inputs["Roughness"].default_value)
    out["metallic"] = float(bsdf.inputs["Metallic"].default_value)
    out["base"] = _upstream_image(nt, _links_to(nt, bsdf, "Base Color"))
    out["normal"] = _upstream_image(nt, _links_to(nt, bsdf, "Normal"))
    out["mr"] = _upstream_image(nt, _links_to(nt, bsdf, "Roughness") + _links_to(nt, bsdf, "Metallic"))
    for n in nt.nodes:
        if n.type == 'GROUP' and "Occlusion" in n.inputs:
            out["occ"] = _upstream_image(nt, _links_to(nt, n, "Occlusion"))
    return out


def uv_density(obj, side_px):
    """Texels per unit of surface (linear: the square root of texel area over surface area, area-weighted
    over the faces) for a square texture of side side_px, and the surface area."""
    np = _np()
    me = obj.data
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    tri = np.empty(len(me.polygons) * 3, np.int64)
    me.polygons.foreach_get("vertices", tri)
    tri = tri.reshape(-1, 3)
    ls = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", ls)
    U = np.stack([uv[ls], uv[ls + 1], uv[ls + 2]], 1)
    P = co[tri]
    a3 = 0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1)
    e1, e2 = U[:, 1] - U[:, 0], U[:, 2] - U[:, 0]
    a2 = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) * side_px * side_px
    ok = a3 > 1e-14
    if not ok.any():
        return 0.0, 0.0
    return float(np.average(np.sqrt(a2[ok] / a3[ok]), weights=a3[ok])), float(a3.sum())


def wrap_uvs(obj):
    """Faces wholly in another UV cell (by their centre, corners up to UV_TOL past it) move back into
    0..1 and are clamped there; a face across a cell border is counted. Returns (faces moved, straddling)."""
    np = _np()
    me = obj.data
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    ls = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", ls)
    idx = np.stack([ls, ls + 1, ls + 2], 1)
    lo, hi = uv[idx].min(1), uv[idx].max(1)
    cell = np.floor(uv[idx].mean(1))
    fits = ((lo >= cell - UV_TOL) & (hi <= cell + 1 + UV_TOL)).all(1)   # a decimated corner just over the edge
    moved = fits & (cell != 0).any(1)
    for j in range(3):
        uv[idx[fits, j]] = np.clip(uv[idx[fits, j]] - cell[fits], 0.0, 1.0)
    me.uv_layers.active.data.foreach_set("uv", uv.reshape(-1))
    return int(moved.sum()), int((~fits).sum())


def pixels(img, size, rgb=True):
    """An image resized to size (w, h) as (h, w, 4) floats, rows bottom-up (the original untouched)."""
    np = _np()
    im = img.copy()
    if tuple(im.size) != tuple(size):
        im.scale(int(size[0]), int(size[1]))
    a = np.empty(size[0] * size[1] * im.channels, np.float32)
    im.pixels.foreach_get(a)
    ch = im.channels
    import bpy
    bpy.data.images.remove(im)
    a = a.reshape(size[1], size[0], ch)
    if ch == 4:
        return a
    out = np.ones((size[1], size[0], 4), np.float32)
    out[..., :3] = a[..., :1] if ch < 3 else a[..., :3]
    return out


def save_image(name, arr, path, colorspace):
    import bpy
    h, w = arr.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=False)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(arr.astype("float32").reshape(-1))
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    img.pack()
    return img


def gltf_output_group():
    """The node group the glTF exporter reads occlusion from ('glTF Material Output'), made when absent."""
    import bpy
    for name in ("glTF Material Output", "glTF Settings"):
        g = bpy.data.node_groups.get(name)
        if g is not None and "Occlusion" in [s.name for s in g.interface.items_tree]:
            return g
    g = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
    g.interface.new_socket("Occlusion", in_out='INPUT', socket_type='NodeSocketFloat')
    g.nodes.new("NodeGroupInput")
    return g


def atlas_material(name, img_bc, img_nm, img_orm):
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img_bc
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    if img_nm is not None:
        t2 = nt.nodes.new("ShaderNodeTexImage")
        t2.image = img_nm
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(t2.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if img_orm is not None:
        t3 = nt.nodes.new("ShaderNodeTexImage")
        t3.image = img_orm
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(t3.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
        grp = nt.nodes.new("ShaderNodeGroup")
        grp.node_tree = gltf_output_group()
        nt.links.new(sep.outputs["Red"], grp.inputs["Occlusion"])
    else:
        bsdf.inputs["Roughness"].default_value = 0.7
    return mat


# ----------------------------------------------------------------------------------- the merge
def load_parts(path, names):
    """Mesh objects of the parts file, transforms baked: (objects, source note)."""
    import bpy
    sys.path.insert(0, HERE)
    import assemble_parts as ap
    if path.lower().endswith(".blend"):
        bpy.ops.wm.open_mainfile(filepath=path)
        meshes = [o for o in bpy.data.objects if o.type == 'MESH']
        if names:
            objs = [bpy.data.objects.get(n) for n in names]
            missing = [n for n, o in zip(names, objs) if o is None or o.type != 'MESH']
            if missing:
                raise Refused(f"no mesh object named {', '.join(missing)} in {os.path.basename(path)}")
        elif bpy.data.collections.get("Parts") is not None:
            objs = [o for o in bpy.data.collections["Parts"].objects if o.type == 'MESH']
        else:
            objs = [o for o in meshes if not o.hide_render
                    and "AnchorRef" not in [c.name for c in o.users_collection]]
        for o in [o for o in meshes if o not in objs]:
            bpy.data.objects.remove(o, do_unlink=True)
        for o in objs:
            w = o.matrix_world.copy()
            o.parent = None
            o.data.transform(w)
            o.matrix_world.identity()
    elif path.lower().endswith(".glb") or path.lower().endswith(".gltf"):
        ap.clear_scene()
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        new = [o for o in bpy.data.objects if o not in before]
        objs = [o for o in new if o.type == 'MESH']
        for o in objs:
            w = o.matrix_world.copy()
            o.parent = None
            o.data.transform(w)
            o.matrix_world.identity()
        for o in new:
            if o.type != 'MESH':
                bpy.data.objects.remove(o, do_unlink=True)
        if names:
            keep = [o for o in objs if o.name in names or re.sub(r"\.\d{3}$", "", o.name) in names]
            for o in [o for o in objs if o not in keep]:
                bpy.data.objects.remove(o, do_unlink=True)
            objs = keep
    else:
        raise Refused(f"{path}: a .blend or a .glb")
    if not objs:
        raise Refused(f"no part meshes in {os.path.basename(path)}")
    for o in objs:
        ap.triangulate(o)
        if o.data.uv_layers.active is None:
            raise Refused(f"{o.name} has no UV layer")
        mats = [m for m in o.data.materials if m is not None]
        if len({m.name for m in mats}) > 1:
            raise Refused(f"{o.name} has {len(mats)} materials: one material per part")
    return objs


def match_parts(objs, plan):
    """{object name: plan part dict or None}: by part name or region, the object's name tokens
    tried longest prefix first (Hand.R.T -> hand.R; Eye.L -> eyes)."""
    out = {}
    parts = (plan or {}).get("parts") or []
    keys = []
    for p in parts:
        for k in {norm_name(p.get("name", "")), norm_name(p.get("region", ""))}:
            if k:
                keys.append((k, p))
                if k.endswith("s"):
                    keys.append((k[:-1], p))
    for o in objs:
        tk = tokens(o.name)
        hit = None
        for n in range(len(tk), 0, -1):
            cand = "".join(tk[:n])
            hit = next((p for k, p in keys if k == cand), None)
            if hit is not None:
                break
        out[o.name] = hit
    return out


def ship(parts_path, out_dir, name=None, plan_path=None, objects=None, atlas=None, pad=8, separate="",
         max_tris=0, budgets=None, cls="character", min_density=0.5, render=True):
    """Run the merge; returns (exit code, gate/1 report)."""
    import bpy
    np = _np()
    t_start = time.time()
    plan = None
    if plan_path:
        with open(plan_path, encoding="utf-8") as handle:
            plan = json.load(handle)
        if plan.get("schema") != "parts/1":
            raise Refused(f"{plan_path} is not a parts/1 plan")
    name = name or (plan or {}).get("character") or os.path.splitext(os.path.basename(parts_path))[0]
    label = re.sub(r"[^A-Za-z0-9_]", "_", name)
    warnings = []
    row = None
    if budgets:
        sys.path.insert(0, os.path.dirname(INSPECT))
        try:
            import inspect_glb
            from pathlib import Path
            _, row, w = inspect_glb.load_budget(cls, Path(budgets))
            warnings += w
        except (OSError, ValueError) as exc:
            raise Refused(f"budget row: {exc}")
    dated = bool(row and row.get("calibrated"))
    tex = (row or {}).get("target_tex_px") if dated else None
    atlas_from = "--atlas" if atlas else ("budget row target_tex_px" if tex else "default")
    if atlas is None:
        atlas = 4096 if not tex or tex >= 4096 else 2048
    if pad < 0 or pad * 4 >= atlas // MIN_TILE_DIV:
        raise Refused(f"--pad {pad} does not fit a {atlas // MIN_TILE_DIV} px tile")
    os.makedirs(out_dir, exist_ok=True)

    objs = load_parts(parts_path, [s.strip() for s in objects.split(",") if s.strip()] if objects else None)
    who = match_parts(objs, plan)
    unmatched = [o.name for o in objs if plan and who[o.name] is None]
    if unmatched:
        warnings.append(f"no plan part for {', '.join(unmatched)}: no budget share checked")
    sep = {norm_name(s) for s in separate.split(",") if s.strip()}

    def part_of(o):
        p = who[o.name]
        return (p or {}).get("name") or norm_name(o.name)

    def is_separate(o):
        p = who[o.name] or {}
        keys = {norm_name(p.get("name", "")), norm_name(p.get("region", "")), norm_name(o.name),
                norm_name(" ".join(tokens(o.name)[:1]))}
        keys |= {k[:-1] for k in keys if k.endswith("s")} | {k + "s" for k in keys if k}
        return bool(keys & sep)

    # ---- maps, UVs, density before
    info, groups = {}, {}
    mats_before = sorted({m.name for o in objs for m in o.data.materials if m is not None})
    draws_before = sum(len({m.name for m in o.data.materials if m is not None}) for o in objs)
    for o in objs:
        maps = material_maps(o.active_material)
        moved, straddle = wrap_uvs(o)
        if straddle:
            raise Refused(f"{o.name}: {straddle} faces cross a UV cell border: no tile can hold them "
                          "(re-unwrap the part, or cut the seam)")
        imgs = [maps[k] for k in ("base", "normal", "mr", "occ")]
        key = tuple(i.name_full if i is not None else None for i in imgs)
        if key == (None, None, None, None):
            key = ("factor", o.name)
        src = max([max(i.size) for i in imgs if i is not None] or [256])
        d0, area = uv_density(o, src)
        info[o.name] = {"obj": o, "maps": maps, "key": key, "src": src, "density_before": d0, "area": area,
                        "uv_moved": moved, "part": part_of(o), "tris": len(o.data.polygons)}
        g = groups.setdefault(key, {"key": key, "src": src, "members": [], "maps": maps})
        g["members"].append(o.name)
    for g in groups.values():
        ms = [info[n] for n in g["members"]]
        a = sum(m["area"] for m in ms) or 1.0
        g["density"] = sum(m["density_before"] * m["area"] for m in ms) / a
        g["pair"] = pair_key(g["members"][0])
    tile = plan_tiles(list(groups.values()), atlas)
    where = place_tiles(tile, atlas)

    # ---- atlases
    any_nm = any(g["maps"]["normal"] is not None for g in groups.values())
    any_orm = any(g["maps"]["mr"] is not None or g["maps"]["occ"] is not None for g in groups.values())
    bc = np.zeros((atlas, atlas, 4), np.float32)
    bc[..., :3], bc[..., 3] = 0.5, 1.0
    nm = orm = None
    if any_nm:
        nm = np.zeros((atlas, atlas, 4), np.float32)
        nm[...] = (0.5, 0.5, 1.0, 1.0)
    if any_orm:
        orm = np.zeros((atlas, atlas, 4), np.float32)
        orm[...] = (1.0, 0.5, 0.0, 1.0)
    tiles_rep = []
    for key, g in groups.items():
        t = tile[key]
        x0, y0 = where[key]
        inner = t - 2 * pad
        m = g["maps"]

        def put(arr, img, fill):
            if img is not None:
                a = pixels(img, (inner, inner))
            else:
                a = np.empty((inner, inner, 4), np.float32)
                a[...] = fill
            arr[y0:y0 + t, x0:x0 + t] = np.pad(a, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
        put(bc, m["base"], (*m["base_rgb"], 1.0))
        if nm is not None:
            put(nm, m["normal"], (0.5, 0.5, 1.0, 1.0))
        if orm is not None:
            if m["mr"] is not None and (m["occ"] is None or m["occ"] == m["mr"]):
                put(orm, m["mr"], None)
                if m["occ"] is None:
                    orm[y0:y0 + t, x0:x0 + t, 0] = 1.0
            else:
                mr = pixels(m["mr"], (inner, inner)) if m["mr"] is not None else None
                oc = pixels(m["occ"], (inner, inner)) if m["occ"] is not None else None
                a = np.empty((inner, inner, 4), np.float32)
                a[..., 0] = oc[..., 0] if oc is not None else 1.0
                a[..., 1] = mr[..., 1] if mr is not None else m["roughness"]
                a[..., 2] = mr[..., 2] if mr is not None else m["metallic"]
                a[..., 3] = 1.0
                orm[y0:y0 + t, x0:x0 + t] = np.pad(a, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
        tiles_rep.append({"members": g["members"], "source_px": g["src"], "tile_px": t, "at_px": [x0, y0],
                          "maps": {k: (m[k].name if m[k] is not None else None) for k in ("base", "normal", "mr", "occ")}})
    img_bc = save_image(f"{label}_atlas_basecolor", bc, os.path.join(out_dir, "atlas_basecolor.png"), "sRGB")
    del bc
    img_nm = save_image(f"{label}_atlas_normal", nm, os.path.join(out_dir, "atlas_normal.png"), "Non-Color") \
        if nm is not None else None
    img_orm = save_image(f"{label}_atlas_orm", orm, os.path.join(out_dir, "atlas_orm.png"), "Non-Color") \
        if orm is not None else None
    del nm, orm
    mat = atlas_material(f"{label}_atlas", img_bc, img_nm, img_orm)

    # ---- UVs into tiles, density after, one material
    inside_all = []
    for n, rec in info.items():
        o = rec["obj"]
        t = tile[rec["key"]]
        x0, y0 = where[rec["key"]]
        me = o.data
        uv = np.empty(len(me.loops) * 2)
        me.uv_layers.active.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        s = (t - 2 * pad) / atlas
        uv = np.c_[(x0 + pad) / atlas + uv[:, 0] * s, (y0 + pad) / atlas + uv[:, 1] * s]
        me.uv_layers.active.data.foreach_set("uv", uv.reshape(-1))
        lo = np.array([x0, y0]) / atlas - 1e-6
        hi = np.array([x0 + t, y0 + t]) / atlas + 1e-6
        inside_all.append(((uv >= lo) & (uv <= hi)).all(1))
        rec["density_after"], _ = uv_density(o, atlas)
        rec["tile_px"] = t
        me.materials.clear()
        me.materials.append(mat)
        vg = o.vertex_groups.get(f"part.{rec['part']}") or o.vertex_groups.new(name=f"part.{rec['part']}")
        vg.add(list(range(len(me.vertices))), 1.0, 'REPLACE')
    inside = float(np.concatenate(inside_all).mean()) if inside_all else 0.0

    joined = [info[n]["obj"] for n in info if not is_separate(info[n]["obj"])]
    kept = [info[n]["obj"] for n in info if is_separate(info[n]["obj"])]
    kept_names = {n for n in info if is_separate(info[n]["obj"])}
    has_hands = any(t in ("hand", "hands") for n in info for t in tokens(n))
    for rec in info.values():
        rec.pop("obj")                    # the join removes all but the first: keep no stale references
    if not joined:
        raise Refused("--separate names every part: nothing to merge")
    with bpy.context.temp_override(active_object=joined[0], selected_editable_objects=joined):
        if len(joined) > 1:
            bpy.ops.object.join()
    merged = joined[0]
    merged.name = merged.data.name = label
    for o in kept:
        o.name = o.data.name = f"{label}_{norm_name(part_of(o))}"
    outs = [merged] + kept
    for o in outs:
        o.hide_render = False
    sys.path.insert(0, HERE)
    import assemble_parts as ap
    glb = os.path.join(out_dir, f"{label}_ship.glb")
    ap.export_glb(glb, outs)
    blend = os.path.join(out_dir, f"{label}_ship.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)

    # ---- gates
    gates = []
    mats_after = sorted({m.name for o in outs for m in o.data.materials if m is not None})
    gates.append(gate("ship.materials", len(mats_after), "== 1", len(mats_after) == 1))
    gates.append(gate("ship.uv_in_tiles", r4(inside), "== 1.0 (every UV inside its part's tile)", inside >= 1.0))
    ratios = {n: (rec["density_after"] / rec["density_before"] if rec["density_before"] else None)
              for n, rec in info.items()}
    kept_res = {n: rec["tile_px"] / rec["src"] for n, rec in info.items()}
    worst = min(kept_res.values(), default=None)
    gates.append(gate("ship.density", r4(worst), f">= {min_density}: each part's tile side over its texture's side "
                      "(the worst part; measured texels per unit, the pad included, under parts)",
                      worst is not None and worst >= min_density - 1e-6))
    tris = {n: rec["tris"] for n, rec in info.items()}
    total = sum(tris.values())
    limit, kind = (max_tris, "--max-tris") if max_tris else (None, None)
    if limit is None and dated and row.get("ceiling_tris"):
        limit, kind = int(row["ceiling_tris"]), "ceiling_tris"
    by_part = {}
    for n, rec in info.items():
        p = who[n] or {}
        b = by_part.setdefault(rec["part"], {"tris": 0, "share": p.get("budget_share"), "objects": []})
        b["tris"] += rec["tris"]
        b["objects"].append(n)
    if limit:
        gates.append(gate("ship.triangles", total, f"<= {limit} ({kind})", total <= limit))
        for part, b in sorted(by_part.items()):
            if b["share"]:
                cap = int(b["share"] * limit)
                gates.append(gate(f"ship.tris.{part}", b["tris"], f"<= budget_share {b['share']} x {limit} = {cap}",
                                  b["tris"] <= cap))
    if dated and row.get("target_tris"):
        tgt = int(row["target_tris"])
        for part, b in sorted(by_part.items()):
            if b["share"] and b["tris"] > 1.25 * b["share"] * tgt:
                warnings.append(f"{part}: {b['tris']} triangles, over 1.25 x its share of target_tris "
                                f"({int(1.25 * b['share'] * tgt)}): reduce it before the merge")
    if not limit and not dated:
        warnings.append("no triangle limit (no --max-tris, no calibrated budget row): counts reported only")
    # inspect_glb on the output
    ins_json = os.path.join(out_dir, "inspect_glb.json")
    need = ["base"] + (["normal"] if any_nm else [])
    cmd = [sys.executable, "-I", INSPECT, glb, "--max-materials", "1", "--require", ",".join(need),
           "--json-out", ins_json]
    if max_tris:
        cmd += ["--max-triangles", str(max_tris), "--min-fraction", "0"]
    if budgets:
        cmd += ["--budgets", budgets, "--class", cls]
    ins = None
    if os.path.isfile(INSPECT):
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            ins = json.loads(res.stdout)
        except ValueError:
            ins = {"error": (res.stderr or res.stdout)[-400:]}
        gates.append(gate("ship.inspect_glb", ins.get("pass"), "inspect_glb.py exit 0 (" + " ".join(cmd[4:-2]) + ")",
                          res.returncode == 0, triangles=ins.get("triangles"), failures=ins.get("failures")))
    else:
        warnings.append("comfyui-asset-generation is not installed beside this skill: inspect_glb not run")

    detail = {
        "atlas": atlas, "pad": pad, "atlas_from": atlas_from,
        "tiles": tiles_rep,
        "parts": {n: {"part": rec["part"], "triangles": rec["tris"], "tile_px": rec["tile_px"],
                      "texels_per_unit_before": round(rec["density_before"], 1),
                      "texels_per_unit_after": round(rec["density_after"], 1),
                      "density_ratio": r4(ratios[n]), "uv_faces_moved": rec["uv_moved"],
                      "separate": n in kept_names} for n, rec in info.items()},
        "by_part": by_part, "triangles": total,
        "draw_calls_before": draws_before, "materials_before": mats_before,
        "draw_calls_after": sum(len({m.name for m in o.data.materials if m}) for o in outs),
        "materials_after": mats_after,
        "objects_after": [o.name for o in outs],
    }
    outputs = {"glb": glb, "blend": blend, "atlas_basecolor": os.path.join(out_dir, "atlas_basecolor.png")}
    if img_nm is not None:
        outputs["atlas_normal"] = os.path.join(out_dir, "atlas_normal.png")
    if img_orm is not None:
        outputs["atlas_orm"] = os.path.join(out_dir, "atlas_orm.png")
    if ins is not None:
        outputs["inspect_glb"] = ins_json
    if render:
        outputs["merge"] = render_merge(outs, img_bc, out_dir, has_hands)
    passed = all(g["pass"] for g in gates)
    report = {"schema": "gate/1", "tool": "ship_merge", "pass": passed, "ok": passed,
              "verdict": "green" if passed else "failed", "character": name, "parts_file": os.path.abspath(parts_path),
              "plan": os.path.abspath(plan_path) if plan_path else None, "gates": gates, "warnings": warnings,
              **detail, "outputs": outputs, "seconds": round(time.time() - t_start, 1)}
    with open(os.path.join(out_dir, f"{label}.ship.gate.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, default=str)
    return (0 if passed else 2), report


def group_centres(outs, word):
    """Centres (Blender frame) of the part.* vertex groups whose name holds `word`, e.g. the hands."""
    np = _np()
    out = []
    for o in outs:
        for vg in o.vertex_groups:
            if not vg.name.startswith("part.") or word not in vg.name:
                continue
            P = [v.co[:] for v in o.data.vertices if any(g.group == vg.index for g in v.groups)]
            if P:
                out.append(np.mean(np.array(P), axis=0))
    return out


def render_merge(outs, img_bc, out_dir, hands):
    """merge.png: the merged character textured (Workbench): front, three-quarter, the face close up,
    each hand close up (front, from its part.* group) when there are hands, and the base-colour atlas."""
    import bpy
    np = _np()
    import assemble_parts as ap
    from mathutils import Vector
    scene, sh, cam = ap._studio()
    sh.color_type = 'TEXTURE'
    for o in bpy.data.objects:
        if o.type == 'MESH':
            o.hide_render = o not in outs
    V = np.concatenate([np.array([v.co[:] for v in o.data.vertices]) for o in outs])
    lo, hi = V.min(0), V.max(0)
    h = hi[2] - lo[2]
    c = (lo + hi) / 2
    w, hh = 384, 512
    tmp = tempfile.mkdtemp(prefix="ship_render_")
    shots = [(Vector((c[0], c[1], c[2])), Vector((0, 1, 0)), h * 1.06),
             (Vector((c[0], c[1], c[2])), Vector((-0.6, 0.8, 0)).normalized(), h * 1.06),
             (Vector((c[0], c[1], hi[2] - 0.13 * h)), Vector((0, 1, 0)), 0.24 * h)]
    if hands:
        for p in sorted(group_centres(outs, "hand"), key=lambda q: q[0]):
            shots.append((Vector(p), Vector((0, 1, 0)), 0.2 * h))
    tiles = []
    try:
        for k, (tgt, d, scale) in enumerate(shots):
            scene.render.resolution_x, scene.render.resolution_y = w, hh
            cam.data.ortho_scale = scale
            tiles.append(ap._shoot(scene, cam, d, tgt, os.path.join(tmp, f"s{k}.png")))
        a = np.ones((hh, w, 4), np.float32)
        side = min(w, hh)
        thumb = pixels(img_bc, (side, side))[::-1]
        a[(hh - side) // 2:(hh - side) // 2 + side, :side] = thumb
        tiles.append(a)
    finally:
        bpy.data.objects.remove(cam, do_unlink=True)
    path = ap._sheet([tiles], w, hh, os.path.join(out_dir, "merge.png"))
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return path


# --------------------------------------------------------------------------------------- selftest
def _quad_mesh(name, centre, size, img_side, colour, col, uv_box=(0.0, 0.0, 1.0, 1.0), normal_img=False):
    """A square (two triangles, Blender frame, facing -Y, tilted) whose UVs span uv_box, with its own
    base-colour image (solid colour) and optionally a normal image (solid)."""
    import bpy
    np = _np()
    cx, cz = centre
    s = size / 2
    d = 0.2 * s                       # tilted a little: a GLB with a zero extent fails inspect_glb's bounds
    verts = [(cx - s, 0, cz - s), (cx + s, 0, cz - s), (cx + s, d, cz + s), (cx - s, d, cz + s)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], [(0, 1, 2), (0, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    u0, v0, u1, v1 = uv_box
    per = {0: (u0, v0), 1: (u1, v0), 2: (u1, v1), 3: (u0, v1)}
    uv.data.foreach_set("uv", np.array([per[me.loops[i].vertex_index] for i in range(len(me.loops))]).reshape(-1))
    mat = bpy.data.materials.new(f"{name}_mat")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    img = bpy.data.images.new(f"{name}_bc", img_side, img_side, alpha=False)
    px = np.ones((img_side, img_side, 4), np.float32)
    px[..., :3] = colour
    img.pixels.foreach_set(px.reshape(-1))
    img.pack()
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    if normal_img:
        nimg = bpy.data.images.new(f"{name}_n", img_side, img_side, alpha=False)
        nimg.colorspace_settings.name = "Non-Color"
        q = np.ones((img_side, img_side, 4), np.float32)
        q[..., :3] = (0.6, 0.4, 0.9)
        nimg.pixels.foreach_set(q.reshape(-1))
        nimg.pack()
        t2 = nt.nodes.new("ShaderNodeTexImage")
        t2.image = nimg
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(t2.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    me.materials.append(mat)
    obj = bpy.data.objects.new(name, me)
    col.objects.link(obj)
    return obj


def contract_sample(script, case, doc):
    """One selftest report for tools/check-contracts.py, named on stdout as `selftest-output: <path>`."""
    out = os.environ.get("UNITY_DEV_CONTRACT_OUT") or os.path.join(tempfile.gettempdir(), "unity-dev-contract-out")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{script}__{case}.gate.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1, default=str)
    print(f"selftest-output: {path}")


def selftest():
    import bpy
    np = _np()
    import assemble_parts as ap
    checks = []

    def ok(name, cond, value=None):
        checks.append({"check": name, "pass": bool(cond), **({} if value is None else {"value": value})})

    # tile planning on its own
    gs = [{"key": "body", "src": 2048, "density": 1000.0, "pair": "body"},
          {"key": "head", "src": 2048, "density": 2400.0, "pair": "head"},
          {"key": "hr", "src": 2048, "density": 5400.0, "pair": "hand t"},
          {"key": "hl", "src": 2048, "density": 5500.0, "pair": "hand t"},
          {"key": "er", "src": 512, "density": 17000.0, "pair": "eye"},
          {"key": "el", "src": 512, "density": 17000.0, "pair": "eye"}]
    t4 = plan_tiles(gs, 4096)
    ok("tiles 4096: body and head keep 2048, the hands halve together, the eyes keep 512",
       t4 == {"body": 2048, "head": 2048, "hr": 1024, "hl": 1024, "er": 512, "el": 512}, t4)
    pl = place_tiles(t4, 4096)
    rects = [(x, y, t4[k]) for k, (x, y) in pl.items()]
    overl = any(not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[2] <= b[1] or b[1] + b[2] <= a[1])
                for i, a in enumerate(rects) for b in rects[i + 1:])
    ok("placement: inside the atlas, no two tiles overlap", not overl and all(x + s <= 4096 and y + s <= 4096
                                                                               for x, y, s in rects), pl)
    t2 = plan_tiles(gs, 2048)
    ok("tiles 2048: every tile fits, mirrored pairs stay equal, nothing under 128",
       sum(v * v for v in t2.values()) <= 2048 * 2048 and t2["hr"] == t2["hl"] and t2["er"] == t2["el"]
       and min(t2.values()) >= 128, t2)
    try:
        plan_tiles([{"key": k, "src": 4096, "density": 1.0, "pair": str(k)} for k in range(257)], 2048)
        ok("tiles: more parts than the atlas holds at its smallest tile is refused", False)
    except Refused:
        ok("tiles: more parts than the atlas holds at its smallest tile is refused", True)

    with tempfile.TemporaryDirectory(prefix="ship_selftest_") as tmp:
        def build(tag, straddle=False):
            ap.clear_scene()
            col = ap.collection("Parts")
            a = _quad_mesh("Body", (0.0, 0.5), 1.0, 128, (0.8, 0.1, 0.1), col, normal_img=True)
            b = _quad_mesh("Head", (0.0, 1.3), 0.4, 128, (0.1, 0.8, 0.1), col, uv_box=(0.0, 0.0, 0.5, 1.0))
            c = _quad_mesh("Hair", (0.0, 1.6), 0.3, 128, (0.1, 0.8, 0.1), col, uv_box=(0.5, 0.0, 1.0, 1.0))
            c.data.materials[0] = b.data.materials[0]          # the hair shares the head's material and image
            d = _quad_mesh("Hand.R", (-0.7, 0.5), 0.1, 64, (0.1, 0.1, 0.8), col)
            e = _quad_mesh("Hand.L", (0.7, 0.5), 0.1, 64, (0.1, 0.1, 0.8), col,
                           uv_box=(0.2, 0.2, 1.4, 0.8) if straddle else (1.0, 1.0, 2.0, 2.0))
            p = os.path.join(tmp, f"{tag}.blend")
            bpy.ops.wm.save_as_mainfile(filepath=p)
            return p
        plan = {"schema": "parts/1", "character": "testchar", "tier": "fine", "parts": [
            {"name": "body", "source": "anchor", "region": "body", "budget_share": 0.5},
            {"name": "head", "source": "generate", "region": "head", "budget_share": 0.2},
            {"name": "hair", "source": "split", "region": "hair", "budget_share": 0.1},
            {"name": "hand_r", "source": "generate", "region": "hand.R", "budget_share": 0.1},
            {"name": "hand_l", "source": "generate", "region": "hand.L", "budget_share": 0.1}]}
        plan_path = os.path.join(tmp, "testchar.parts.json")
        with open(plan_path, "w", encoding="utf-8") as handle:
            json.dump(plan, handle)
        src = build("good")
        code, rep = ship(src, os.path.join(tmp, "out"), plan_path=plan_path, atlas=2048, pad=4, render=False)
        gv = {g["name"]: g for g in rep["gates"]}
        ok("good: exit 0, one material, every UV in its tile", code == 0 and gv["ship.materials"]["value"] == 1
           and gv["ship.uv_in_tiles"]["pass"], [g["name"] for g in rep["gates"] if not g["pass"]])
        ok("good: Head and Hair share one tile (one image), five parts in four tiles",
           len(rep["tiles"]) == 4 and any(sorted(t["members"]) == ["Hair", "Head"] for t in rep["tiles"]),
           [t["members"] for t in rep["tiles"]])
        ok("good: each part matched to its plan part (Hand.R -> hand_r)",
           {n: p["part"] for n, p in rep["parts"].items()} == {"Body": "body", "Head": "head", "Hair": "hair",
                                                                 "Hand.R": "hand_r", "Hand.L": "hand_l"},
           {n: p["part"] for n, p in rep["parts"].items()})
        ok("good: a part wholly in UV cell (1, 1) is moved back, not refused",
           rep["parts"]["Hand.L"]["uv_faces_moved"] == 2, rep["parts"]["Hand.L"]["uv_faces_moved"])
        ok("good: one object out, five vertex groups part.*", rep["objects_after"] == ["testchar"]
           and sorted(g.name for g in bpy.data.objects["testchar"].vertex_groups)
           == ["part.body", "part.hair", "part.hand_l", "part.hand_r", "part.head"], rep["objects_after"])
        # the atlas pixels: each tile's centre is its part's colour, the normal tile of a part without one is flat
        img = bpy.data.images.load(rep["outputs"]["atlas_basecolor"])
        A = np.empty(img.size[0] * img.size[1] * 4, np.float32)
        img.pixels.foreach_get(A)
        A = A.reshape(img.size[1], img.size[0], 4)
        nimg = bpy.data.images.load(rep["outputs"]["atlas_normal"])
        N = np.empty(nimg.size[0] * nimg.size[1] * 4, np.float32)
        nimg.pixels.foreach_get(N)
        N = N.reshape(nimg.size[1], nimg.size[0], 4)
        want = {"Body": (0.8, 0.1, 0.1), "Head": (0.1, 0.8, 0.1), "Hand.R": (0.1, 0.1, 0.8)}
        good_px = True
        for t in rep["tiles"]:
            x, y = t["at_px"]
            s = t["tile_px"]
            got = A[y + s // 2, x + s // 2, :3]
            for m in t["members"]:
                if m in want:
                    good_px &= bool(np.allclose(got, want[m], atol=0.02))
            edge = A[y, x, :3]                           # the pad ring repeats the border
            good_px &= bool(np.allclose(edge, got, atol=0.02))
            nn = N[y + s // 2, x + s // 2, :3]
            good_px &= bool(np.allclose(nn, (0.6, 0.4, 0.9) if "Body" in t["members"] else (0.5, 0.5, 1.0), atol=0.02))
        ok("good: each tile holds its part's base colour (pad included) and normal (flat where none)", good_px)
        dr = {n: p["density_ratio"] for n, p in rep["parts"].items()}
        ok("good: density ratios = (tile - 2 pad) / source side", all(
            abs(dr[n] - (rep["parts"][n]["tile_px"] - 8) / (128 if n in ("Body", "Head", "Hair") else 64)) < 0.02
            for n in dr), dr)
        contract_sample("ship_merge", "good", rep)
        # a hard triangle limit: the body's share is 0.5 x 4 = 2 triangles, it has 2; the total 10 > 4
        src = build("tris")
        code, rep = ship(src, os.path.join(tmp, "out2"), plan_path=plan_path, atlas=2048, pad=4, max_tris=4,
                         render=False)
        gv = {g["name"]: g for g in rep["gates"]}
        ok("--max-tris 4: ship.triangles fails (10), the body's share holds, exit 2",
           code == 2 and not gv["ship.triangles"]["pass"] and gv["ship.tris.body"]["pass"]
           and not gv["ship.inspect_glb"]["pass"], {k: v["pass"] for k, v in gv.items()})
        contract_sample("ship_merge", "over_budget", rep)
        src = build("sep")
        code, rep = ship(src, os.path.join(tmp, "out3"), plan_path=plan_path, atlas=2048, pad=4, separate="hair",
                         render=False)
        ok("--separate hair: two objects, still one material", code == 0 and len(rep["objects_after"]) == 2
           and rep["materials_after"] == ["testchar_atlas"], [rep["objects_after"], rep["materials_after"]])
        src = build("straddle", straddle=True)
        try:
            ship(src, os.path.join(tmp, "out4"), atlas=2048, pad=4, render=False)
            ok("a face across a UV cell border is refused (exit 1)", False)
        except Refused as exc:
            ok("a face across a UV cell border is refused (exit 1)", "cross a UV cell border" in str(exc), str(exc))
    failed = [c["check"] for c in checks if not c["pass"]]
    return (1 if failed else 0), {"tool": "ship_merge", "selftest": "fail" if failed else "pass",
                                  "failed": failed, "checks": checks}


def main(argv=None, prog="ship_merge.py"):
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser(prog).parse_args(argv)
    if not args.selftest and (not args.parts or not args.out):
        parser(prog).print_usage(sys.stderr)
        print(f"{prog}: error: PARTS and --out are required", file=sys.stderr)
        return 1
    try:
        import bpy  # noqa: F401
    except ImportError:
        print(json.dumps({"tool": "ship_merge", "error": "run inside Blender: blender -b -P ship_merge.py -- ..."}))
        return 1
    try:
        if args.selftest:
            code, report = selftest()
        else:
            code, report = ship(args.parts, args.out, args.name, args.plan, args.objects, args.atlas, args.pad,
                                args.separate, args.max_tris, args.budgets, args.cls, args.min_density,
                                not args.no_render)
    except Refused as exc:
        code, report = 1, {"schema": "gate/1", "tool": "ship_merge", "pass": False, "ok": False,
                           "verdict": "failed", "gates": [], "refused": str(exc)}
    except Exception as exc:              # Blender -b exits 0 on an uncaught error: make it a failure
        import traceback
        traceback.print_exc()
        code, report = 1, {"schema": "gate/1", "tool": "ship_merge", "pass": False, "ok": False,
                           "verdict": "harness", "gates": [], "error": f"{type(exc).__name__}: {exc}"}
    if getattr(args, "report", None):
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1, default=str)
    print(json.dumps(report, indent=1, default=str))
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
