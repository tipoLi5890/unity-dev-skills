#!/usr/bin/env python3
"""assemble_parts.py — put a generated head (and its hair) back onto the whole-body anchor, gated.

The anchor (the whole character from one image-to-3D job) fixes the proportions; the head part
comes from its own job (comfyui-asset-generation `part_views.py`), usually repainted with
mesh-texture-paint. This registers the head onto the anchor, splits its hair off, cuts the anchor's
head away above the neck, seams the two, checks the result against the anchor and writes the
files the rig stage takes. The geometry is `part_math.py` (same folder, numpy only).

usage (Blender, headless):
    blender -b --factory-startup -P assemble_parts.py -- assemble PLAN.parts.json --out ASSEMBLY_DIR
            [--seam overlap|bridge] [--accept-joined-hair] [--no-render]
    blender -b -P assemble_parts.py -- bind OUT --hair ASSEMBLY_DIR/<c>_hair.glb --rig-glb ASSEMBLY_DIR/<c>_rig.glb
            [--name NAME] [--report PATH]   (no --factory-startup: the FBX export needs Auto-Rig Pro)
    blender -b --factory-startup -P assemble_parts.py -- --selftest

assemble, in order:
  register   the head GLB (generated.painted, else paint/<part>/<stem>_painted.glb, else generated.glb;
             the anchor: anchor.painted_glb, else anchor.glb) starts at scale L/1024 (L = the crop box
             side), at the box centre mapped through the plan's frame fit, unrotated; then
             trimmed similarity ICP (40k part points, point-to-plane, onto up to 300k points of the
             anchor's head region above the collar). Gates part.register.scale_ratio |s/s0 - 1| <= 0.05,
             part.register.rms <= 0.03 of the region height, part.register.rotation_deg <= 6.
  split      hair = faces nearer the plan's hair colour than its skin colour, more than delta x part
             height outside the scalp-radius map, above the chin (part_math.split_hair); delta from
             the plan (0.03), then 0.05. Gates hair.islands_returned <= 0.10, hair.components 1..3,
             head.top_closed >= 0.95, hair.coverage >= 0.90. When both fail, Head keeps the hair
             (`degraded`), exit 2; --accept-joined-hair continues with exit 0 and the failed gates kept
             (marked accepted): the hair is then in the rig mesh, so the markers' height includes it.
  cut        the anchor is bisected at seam.cut_y and the components above the plane whose rim lies
             in the neck disc (1.3 x radius) are deleted, with floating islands above the collar
             (hair). A collar meeting the plane outside the disc stays. Gate part.cut.collar_kept.
  seam       overlap (default with a collar): the part's neck runs down to part_bottom_y, inside the
             anchor's neck stump and collar; the part is cut flat there. Before the hair split the
             part's neck axis is shifted onto the anchor's (fully below cut_y, nothing a neck radius
             above it; gate seam.centre <= 0.25 x radius). After the cut, where nothing covers them,
             the anchor's stump is pulled under the part's neck (fully at the rim) and the part's
             flat bottom inside the stump (fully at part_bottom_y), each to 0.97 of the other's
             outermost surface (gate seam.tuck <= 0.25 x radius; over it nothing moves). The two
             open edges are the seam: gate seam.hidden, the share of their vertices (the part's flat
             bottom edge, the anchor's rim at cut_y) with geometry outside them on the outward
             horizontal ray (the other mesh, a coincident surface counting, or a collar), worse of
             the two, >= 0.95.
             Reported: seam.gap (anchor rim to part surface, share of the neck radius) and
             neck_inside_stump (part neck vertices below cut_y inside the anchor).
             bridge (default without a collar): both cut at cut_y, the inner shell deleted locally near
             the cut on both (ray test on the uncut meshes), gates seam.loops (one loop per side) and
             seam.gap (mean <= 0.10, max <= 0.25 of the radius), then the anchor's loop is zipped to
             the part's loop with new faces on Body; never bridged when a gate fails.
  colour     the part's neck takes the anchor's skin at the seam (part_math seam_colour_field): both
             sides sampled through their UVs on a cylinder grid around the neck axis (24 angles, rows
             0.1 x radius), skin only (the plan's colours); the target is the anchor at the same place
             below cut_y and the anchor's rim at and above it; the difference (linear RGB) is added to
             the head's base-colour texels with weight 1 up to cut_y + 0.15 x radius, fading to 0 at the
             chin (at least cut_y + 0.5 x radius) and from 1.3 to 1.8 x radius off the axis (the face
             keeps its own); a cell whose two sides are two materials is left alone. Gate seam.colour,
             over the sectors where the seam is in the open (nothing of the anchor outside it but the
             neck): delta E of the part just above the cut to the anchor's rim <= 6, sharpest
             lightness step per 0.1 x radius from the rim up <= 12 (provisional); before values kept.
  coverage   part.coverage.rim: horizontal rays from the anchor's cut rim toward the neck axis hit the
             part >= 0.98 (the part fills the opening); part.coverage.sphere: 288 rays from a sphere
             (1.5 x head height) toward the head region's centre hit geometry >= 0.99.
  silhouette assembly.silhouette.<view>: whole-body IoU against the anchor, 512 px, >= 0.95 per view
             (provisional); head rows (above cut_y) reported. assembly.head_extent_ratio: the head's
             height above cut_y against the anchor's, within +-5 % (keeps H and the contract).
Outputs in ASSEMBLY_DIR: <c>_parts.blend (collection Parts: Body, Head, Hair, each its own material
and vertex group part.*), <c>_parts.glb (the three meshes), <c>_rig.glb (Body + Head joined, both
materials: what the rig stage takes; no hair), <c>_hair.glb (same frame), <c>.parts.gate.json, and
unless --no-render compare.png and compare_head.png (Workbench, clay and textured, front / left /
back / right; rows: anchor clay, assembly clay, anchor textured, assembly textured) and neck.png
(the neck close up, front and three-quarter, before and after the colour match) for a person.

bind (after autorig): opens OUT/rig/<NAME>_arp.blend, imports the hair, recovers the rig stage's
import transform from <c>_rig.glb (scale from the z extents, shift from the minima), binds the hair
rigidly (weight 1.0) to the contract's Head bone (OUT/rig/<NAME>.contract.json retarget_map), gives it
the head's material already on the rig (the import's .001 copy dropped when its images match), and
re-exports the FBX with blender-retarget brt_arp op export, after backing the blend up to
rig/<NAME>_arp.pre_parts.blend; a hair an earlier bind left is replaced. Gates
parts.transform_residual (<= 1e-5 x height), parts.hair_bound. character-autorig `autorig.py all OUT
<c>_rig.glb --hair <c>_hair.glb` runs it as its parts_bind step, after the contract and before deform;
run by hand after a rig made without --hair, run `autorig.py deform OUT` again: the FBX changed.

Report: gate/1 (schemas/gate-1.json) with `degraded`, per-part detail and the outputs; `ok`, pass's
old name, equals it. Exit codes: 0 every gate passed (or --selftest passed); 2 a gate failed;
1 usage error, refused input (a stale plan, a missing part) or a failed --selftest. The bcr headless
stages use 1 for a gate; this script follows gate/1 as character-autorig does. Arguments are parsed
before bpy or numpy is imported.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

GATES = {"scale_ratio": 0.05, "rms": 0.03, "rotation_deg": 6.0, "hidden": 0.95, "rim": 0.98, "sphere": 0.99,
         "silhouette": 0.95, "head_extent": 0.05, "bridge_gap_mean": 0.10, "bridge_gap_max": 0.25,
         "collar_kept": 0.99, "tuck": 0.25, "colour_delta": 6.0, "colour_edge": 12.0}
VIEWS = ("front", "left", "back", "right")


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parser():
    p = UsageParser(prog="assemble_parts.py", description=__doc__.split("\n")[0],
                    epilog="Exit codes: 0 pass, 2 a gate failed, 1 usage error or refused input.")
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd", parser_class=UsageParser)
    a = sub.add_parser("assemble")
    a.add_argument("plan")
    a.add_argument("--out", required=True)
    a.add_argument("--seam", choices=("overlap", "bridge"))
    a.add_argument("--accept-joined-hair", action="store_true")
    a.add_argument("--no-render", action="store_true")
    b = sub.add_parser("bind")
    b.add_argument("autorig_out")
    b.add_argument("--hair", required=True)
    b.add_argument("--rig-glb", required=True)
    b.add_argument("--name")
    b.add_argument("--report", help="also write the gate/1 report here")
    return p


# ------------------------------------------------------------------------------- blender helpers
def _np():
    import numpy as np
    return np


def to_gltf(Vb):
    np = _np()
    return np.c_[Vb[:, 0], Vb[:, 2], -Vb[:, 1]]


def to_blender(Vg):
    np = _np()
    return np.c_[Vg[:, 0], -Vg[:, 2], Vg[:, 1]]


def clear_scene():
    import bpy
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.cameras, bpy.data.lights):
        for d in list(coll):
            if d.users == 0:
                coll.remove(d)


def collection(name):
    import bpy
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def move_to(obj, col):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)


def import_glb(path, name, col):
    """One mesh object from a GLB: the importer's transform baked, helpers removed, meshes joined."""
    import bpy
    from mathutils import Matrix
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    if not meshes:
        raise ValueError(f"{path} holds no mesh")
    for o in meshes:
        w = o.matrix_world.copy()
        o.parent = None
        o.data.transform(w)
        o.matrix_world = Matrix.Identity(4)
    for o in new:
        if o not in meshes:
            bpy.data.objects.remove(o, do_unlink=True)
    obj = meshes[0]
    if len(meshes) > 1:
        with bpy.context.temp_override(active_object=obj, selected_editable_objects=meshes):
            bpy.ops.object.join()
    move_to(obj, col)
    obj.name = obj.data.name = name
    triangulate(obj)
    return obj


def triangulate(obj):
    import bmesh
    me = obj.data
    if all(len(p.vertices) == 3 for p in me.polygons):
        return
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(me)
    bm.free()


def arrays(obj, uv=False):
    """(V in the glTF frame, F, per-face UV centroid or None) of a triangle mesh with identity transform."""
    np = _np()
    me = obj.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    tri = np.empty(len(me.polygons) * 3, dtype=np.int64)
    me.polygons.foreach_get("vertices", tri)
    V = to_gltf(co.reshape(-1, 3))
    F = tri.reshape(-1, 3)
    uvf = None
    if uv and me.uv_layers.active is not None:
        u = np.empty(len(me.loops) * 2)
        me.uv_layers.active.data.foreach_get("uv", u)
        start = np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("loop_start", start)
        u = u.reshape(-1, 2)
        uvf = (u[start] + u[start + 1] + u[start + 2]) / 3.0
    return V, F, uvf


def set_coords(obj, Vg):
    np = _np()
    obj.data.vertices.foreach_set("co", to_blender(np.asarray(Vg, float)).reshape(-1))
    obj.data.update()


def delete_faces(obj, mask):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    gone = [bm.faces[i] for i in range(len(bm.faces)) if mask[i]]
    if gone:
        bmesh.ops.delete(bm, geom=gone, context='FACES_ONLY')
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def bisect(obj, y_gltf):
    """Cut every face that crosses the height y (glTF frame) so no face straddles it; triangles kept."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-9, plane_co=(0.0, 0.0, y_gltf), plane_no=(0.0, 0.0, 1.0))
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def base_colour(obj):
    """(h, w, 4) floats of the base-colour image (rows bottom-up, as Blender stores them) or None."""
    node = base_colour_node(obj)
    return None if node is None else image_array(node.image, rgb3=True)


def image_array(img, rgb3=False):
    """An image's pixels as (h, w, channels) floats, rows bottom-up; rgb3 widens a grey image to RGB."""
    np = _np()
    w, h = img.size
    px = np.empty(w * h * img.channels, dtype=np.float32)
    img.pixels.foreach_get(px)
    a = px.reshape(h, w, img.channels)
    return np.repeat(a[..., :1], 3, axis=2) if rgb3 and img.channels < 3 else a


def base_colour_node(obj, with_slot=False):
    """The image node feeding the first Principled BSDF's Base Color (through any nodes), or None;
    with_slot: (node, material slot index)."""
    for slot, mat in enumerate(obj.data.materials):
        if mat is None or not mat.node_tree:
            continue
        bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is None:
            continue
        stack = [l.from_node for l in bsdf.inputs["Base Color"].links]
        seen = set()
        while stack:
            n = stack.pop()
            if n.name in seen:
                continue
            seen.add(n.name)
            if n.type == 'TEX_IMAGE' and n.image is not None and all(n.image.size):
                return (n, slot) if with_slot else n
            for inp in n.inputs:
                stack += [l.from_node for l in inp.links]
    return (None, None) if with_slot else None


def corner_uvs(obj):
    """(m, 3, 2) UVs of each triangle's corners (the active layer), or None."""
    np = _np()
    me = obj.data
    if me.uv_layers.active is None:
        return None
    u = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", u)
    start = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("loop_start", start)
    u = u.reshape(-1, 2)
    return np.stack([u[start], u[start + 1], u[start + 2]], axis=1)


def kd_nn(Q):
    """A nearest-neighbour callable over Q through mathutils.kdtree (exact, fast inside Blender)."""
    np = _np()
    from mathutils.kdtree import KDTree
    kd = KDTree(len(Q))
    for i, p in enumerate(Q):
        kd.insert(p, i)
    kd.balance()

    def nn(X):
        d = np.empty(len(X))
        idx = np.empty(len(X), dtype=np.int64)
        for i, x in enumerate(X):
            _, j, dist = kd.find(x)
            d[i], idx[i] = dist, j
        return d, idx
    return nn


def add_group(obj, name):
    vg = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
    vg.add(list(range(len(obj.data.vertices))), 1.0, 'REPLACE')


def share_materials(obj, others):
    """The hair is split from the head and keeps its material, so its import brings a second copy of
    the head's material and images (`.001`), while the rig stage may have renamed the original
    (`RunnerMat1`): point each hair slot at the material on `others` whose images match its own, by
    name before Blender's .NNN and pixel for pixel, and drop the copy, so the FBX embeds each texture
    once. A material without such a twin stays its own. Returns the names shared."""
    import re
    import bpy
    np = _np()
    base = lambda name: re.sub(r"\.\d{3}$", "", name)

    def images(m):      # each image once, even when two nodes read it
        nodes = m.node_tree.nodes if m.node_tree else []
        uniq = {n.image.name_full: n.image for n in nodes if n.type == 'TEX_IMAGE' and n.image}
        return sorted(uniq.values(), key=lambda i: base(i.name))

    def same(a, b):
        if base(a.name) != base(b.name) or tuple(a.size) != tuple(b.size) or len(a.pixels) != len(b.pixels):
            return False
        pa, pb = np.empty(len(a.pixels), np.float32), np.empty(len(b.pixels), np.float32)
        a.pixels.foreach_get(pa)
        b.pixels.foreach_get(pb)
        return bool(np.array_equal(pa, pb))

    have = []
    for o in others:
        for m in o.data.materials:
            if m is not None and m not in have:
                have.append(m)
    shared = []
    for i, m in enumerate(list(obj.data.materials)):
        mine = images(m) if m is not None else []
        if not mine or m in have:
            continue
        twin = next((t for t in have if len(images(t)) == len(mine)
                     and all(same(a, b) for a, b in zip(mine, images(t)))), None)
        if twin is None:
            continue
        obj.data.materials[i] = twin
        shared.append(m.name)
        names = [im.name_full for im in mine]
        if m.users == 0:
            bpy.data.materials.remove(m)
        for name in names:
            im = bpy.data.images.get(name)
            if im is not None and im.users == 0:
                bpy.data.images.remove(im)
    return shared


def rename_material(obj, label):
    for i, mat in enumerate(obj.data.materials):
        if mat is None:
            continue
        mat.name = label if i == 0 else f"{label}_{i}"
        if mat.node_tree:
            for n in mat.node_tree.nodes:
                if n.type == 'TEX_IMAGE' and n.image is not None and not n.image.name.startswith(label):
                    n.image.name = f"{label}_{n.label or n.name}".replace(" ", "_")


def export_glb(path, objs):
    import bpy
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True, export_apply=True,
                              export_yup=True)
    bpy.ops.object.select_all(action='DESELECT')


def gate(name, value, limit, passed, **extra):
    return {"name": name, "value": value, "limit": limit, "pass": bool(passed), **extra}


def r4(x):
    return None if x is None else round(float(x), 4)


# ------------------------------------------------------------------------------------- assemble
class Refused(Exception):
    pass


def _resolve(base, path):
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(base, path))


def assemble(plan_path, out_dir, seam_mode=None, accept_joined=False, render=True, render_px=768):
    """Run the assembly; returns (exit code, gate/1 report)."""
    import bpy
    np = _np()
    import part_math as pm
    t_start = time.time()
    try:
        plan, base = pm.load_plan(plan_path)
    except (pm.Refused, OSError, ValueError) as exc:
        raise Refused(str(exc))
    c = plan["character"]
    if plan["tier"] == "whole":
        raise Refused("tier whole has nothing to assemble: the anchor is the character")
    by_region = {p["region"]: p for p in plan["parts"]}
    head_p, hair_p = by_region.get("head"), by_region.get("hair")
    gen = head_p.get("generated") or {}
    cands = [_resolve(base, gen[k]) for k in ("painted", "glb") if gen.get(k)]
    if gen.get("glb"):      # mesh-texture-paint run with --out paint/<part> writes <stem>_painted.glb there
        stem = os.path.splitext(os.path.basename(gen["glb"]))[0]
        cands.insert(len(cands) - 1, os.path.join(base, "paint", head_p["name"], f"{stem}_painted.glb"))
    head_glb = next((p for p in cands if os.path.isfile(p)), None)
    if head_glb is None:
        raise Refused(f"part {head_p['name']}: no generated GLB on disk (run part_views.py generate)")
    anchor = plan["anchor"]
    anchor_glb = next(_resolve(base, anchor[k]) for k in ("painted_glb", "glb")
                      if anchor.get(k) and os.path.isfile(_resolve(base, anchor[k])))
    for key in ("frame", "neck"):
        if key not in anchor:
            raise Refused(f"anchor.{key} is missing: run part_math.py plan")
    neck = anchor["neck"]
    seam = head_p.get("seam") or {}
    views = head_p.get("views") or {}
    if "cut_y" not in seam or "part_bottom_y" not in seam or "boxes" not in views:
        raise Refused(f"part {head_p['name']}: seam heights or crop boxes missing: run part_math.py plan")
    mode = seam_mode or seam.get("mode") or ("overlap" if neck.get("collar") else "bridge")
    colours = views.get("colours") or {}
    if hair_p is not None and not (colours.get("hair") and colours.get("skin")):
        raise Refused(f"part {head_p['name']}: views.colours (hair, skin) missing: part_views.py samples them")
    axis = np.array(neck["axis_xz"], float)
    radius = float(neck["radius"])
    cut_y, bottom_y = float(seam["cut_y"]), float(seam["part_bottom_y"])
    collar_top = float(neck.get("collar_top") or cut_y)
    os.makedirs(out_dir, exist_ok=True)

    clear_scene()
    parts_col = collection("Parts")
    ref_col = collection("AnchorRef")
    body = import_glb(anchor_glb, "Body", parts_col)
    head = import_glb(head_glb, "Head", parts_col)
    ref = import_glb(anchor_glb, "AnchorRef", ref_col)
    rename_material(body, f"{c}_body")
    rename_material(head, f"{c}_head")
    rename_material(ref, f"{c}_anchor_ref")
    gates, warnings, detail = [], [], {"character": c, "plan": os.path.abspath(plan_path), "seam_mode": mode,
                                       "anchor_glb": anchor_glb, "head_glb": head_glb}
    rng = np.random.default_rng(0)

    # ---- register
    Va, Fa, _ = arrays(body)
    Vaw, Faw, _ = pm.weld(Va, Fa)
    top = float(Vaw[:, 1].max())
    hw = 1.5 * (top - cut_y)
    region, _ = pm.region_faces(Vaw, Faw, cut_y, axis, radius, box=(hw, hw), float_above=collar_top)
    cy_face = Vaw[Faw].mean(1)[:, 1]
    target = region & (cy_face > collar_top)
    if target.sum() < 50:
        raise Refused("the anchor's head region above the collar is empty: check the plan's neck band")
    Q, Qn, _ = pm.sample_surface(Vaw, Faw, min(300000, max(20000, 25 * int(target.sum()))), rng, face_mask=target)
    Vh, Fh, _ = arrays(head)
    Vhw, Fhw, _ = pm.weld(Vh, Fh)
    L = float(views["box_side_px"])
    s0 = L / 1024.0
    t0 = pm.box_centre(anchor["frame"], views["boxes"])
    above = (s0 * Vhw[Fhw].mean(1) + t0)[:, 1] > collar_top        # the same region on both sides
    P, _, _ = pm.sample_surface(Vhw, Fhw, 40000, rng, face_mask=above if above.sum() > 50 else None)
    nn = kd_nn(Q)
    box = (Q.min(0), Q.max(0))
    # similarity ICP checks the crop's scale (gate); the applied fit is rigid at the crop's scale, which
    # comes from the anchor's own projection: trimmed ICP pulls the scale down on redrawn detail
    sim = pm.similarity_icp(P, Q, s0, np.eye(3), t0, nn=nn, Qn=Qn, region_box=box)
    reg = pm.similarity_icp(P, Q, s0, np.eye(3), t0, nn=nn, Qn=Qn, region_box=box, fix_scale=True)
    ratio = sim["s"] / s0
    detail["register"] = {"s0": r4(s0), "s_similarity": round(sim["s"], 6), "scale_ratio": r4(ratio),
                          "t0": [r4(x) for x in t0], "t": [r4(x) for x in reg["t"]],
                          "rotation_deg": r4(reg["rotation_deg"]), "rms_inside": r4(reg["rms_inside"]),
                          "median_inside": r4(reg["median_inside"]), "iterations": reg["iterations"],
                          "similarity": {"rotation_deg": r4(sim["rotation_deg"]), "rms_inside": r4(sim["rms_inside"])},
                          "region_height": r4(np.ptp(Q[:, 1])), "matrix": (np.r_[np.c_[reg["s"] * reg["R"], reg["t"]],
                                                                             [[0, 0, 0, 1]]]).round(6).tolist()}
    gates += [gate("part.register.scale_ratio", r4(ratio), f"|s/s0 - 1| <= {GATES['scale_ratio']}",
                   abs(ratio - 1) <= GATES["scale_ratio"]),
              gate("part.register.rms", r4(reg["rms_inside"]), f"<= {GATES['rms']} of region height",
                   reg["rms_inside"] <= GATES["rms"]),
              gate("part.register.rotation_deg", r4(reg["rotation_deg"]), f"<= {GATES['rotation_deg']}",
                   reg["rotation_deg"] <= GATES["rotation_deg"])]
    Vh = reg["s"] * Vh @ reg["R"].T + reg["t"]
    set_coords(head, Vh)

    # ---- seam cut of the part (overlap: flat at part_bottom_y; bridge: at cut_y, inner shell first)
    part_cut = bottom_y if mode == "overlap" else cut_y
    if mode == "bridge":
        Vh, Fh, _ = arrays(head)
        Vhw, Fhw, _ = pm.weld(Vh, Fh)
        inner_h = pm.inner_shell_faces(Vhw, Fhw, cut_y, 0.6 * radius, radius, axis)
        delete_faces(head, inner_h)
    bisect(head, part_cut)
    Vh, Fh, _ = arrays(head)
    delete_faces(head, Vh[Fh].mean(1)[:, 1] < part_cut)
    centred = None
    if mode == "overlap":       # the drawn neck may stand off the anchor's neck axis: centre it (head stays)
        Vh, Fh, _ = arrays(head)
        Vhw, Fhw, inv = pm.weld(Vh, Fh)
        Vc, centred = pm.centre_neck(Vhw, Fhw, axis, radius, bottom_y, cut_y, cut_y + radius, limit=GATES["tuck"])
        gates.append(gate("seam.centre", r4(centred["offset_share"]), f"<= {GATES['tuck']} of the radius (the part's "
                          "neck axis moved onto the anchor's)", centred["offset_share"] <= GATES["tuck"]))
        if centred["applied"]:
            set_coords(head, Vh + (Vc - Vhw)[inv])

    # ---- split the hair
    hair = None
    degraded = None
    if hair_p is not None:
        Vh, Fh, uvf = arrays(head, uv=True)
        Vhw, Fhw, _ = pm.weld(Vh, Fh)
        img = base_colour(head)
        if img is None or uvf is None:
            raise Refused("the head part has no base-colour texture: the hair split reads colour")
        rgb = pm.face_colours(uvf, img)
        hair_rgb, skin_rgb = pm.hex_rgb(colours["hair"]), pm.hex_rgb(colours["skin"])
        chin = float(neck["band"][1])
        tries = []
        mask = None
        for delta in sorted({float((hair_p.get("split") or {}).get("delta", 0.03)), 0.05}):
            m, st = pm.split_hair(Vhw, Fhw, rgb, hair_rgb, skin_rgb, chin, delta=delta)
            tries.append({k: v for k, v in st.items() if k != "gates"} | {"gates": st["gates"]})
            if all(g["pass"] for g in st["gates"]):
                mask = m
                break
        detail["split"] = {"tries": tries, "colours": colours}
        last = tries[-1]["gates"]
        if mask is not None:
            gates += last
            hair = head.copy()
            hair.data = head.data.copy()
            hair.name = hair.data.name = "Hair"
            parts_col.objects.link(hair)
            delete_faces(hair, ~mask)
            delete_faces(head, mask)
        else:
            degraded = "hair joined to head"
            for g in last:
                gates.append(dict(g, accepted=True) if (accept_joined and not g["pass"]) else g)
            warnings.append("hair split failed at every delta: Head keeps the hair; the rig mesh then carries "
                            "it and the markers' height includes it")

    # ---- cut the anchor
    bisect(body, cut_y)
    Vb, Fb, _ = arrays(body)
    Vbw, Fbw, _ = pm.weld(Vb, Fb)
    kill, cut_info = pm.region_faces(Vbw, Fbw, cut_y, axis, radius, box=(hw, hw), float_above=collar_top)
    if neck.get("collar"):
        ys = np.linspace(cut_y, collar_top, 5)[1:]
        kept = pm.collar_kept(Vbw, Fbw, kill, ys, axis, radius)
        gates.append(gate("part.cut.collar_kept", r4(kept), f">= {GATES['collar_kept']} of the collar's slice length "
                          "between the cut and the collar top", kept >= GATES["collar_kept"]))
    inner_b = np.zeros(len(Fbw), bool)
    if mode == "bridge":
        inner_b = pm.inner_shell_faces(Vbw, Fbw, cut_y, 0.6 * radius, radius, axis) & ~kill
    delete_faces(body, kill | inner_b)
    detail["cut"] = {"faces_deleted": int(kill.sum()), "inner_shell_deleted": int(inner_b.sum()),
                     "components": cut_info["deleted"][:6], "kept_components": cut_info["kept"][:6]}

    # ---- seam checks
    Vb, Fb, _ = arrays(body)
    Vbw, Fbw, _ = pm.weld(Vb, Fb)
    Vh, Fh, _ = arrays(head)
    Vhw, Fhw, _ = pm.weld(Vh, Fh)
    rims = pm.loops_at(Vbw, Fbw, cut_y, 0.25 * radius, axis_xz=axis, radius=radius)
    rim_v = np.unique(np.concatenate(rims)) if rims else np.zeros(0, int)
    sd = {}
    band_h = np.abs(Vhw[Fhw].mean(1)[:, 1] - cut_y) < radius
    if len(rim_v) and band_h.any():
        surf, _, _ = pm.sample_surface(Vhw, Fhw, 60000, rng, face_mask=band_h)
        d, _ = kd_nn(surf)(Vbw[rim_v])
        sd["gap_mean"], sd["gap_max"] = r4(d.mean() / radius), r4(d.max() / radius)
    if mode == "overlap":
        near_t = np.abs(Vhw[Fhw].mean(1)[:, 1] - (bottom_y + cut_y) / 2) < (cut_y - bottom_y) / 2 + 0.5 * radius
        Vt, tk = pm.tuck_stump(Vbw, Fbw, rim_v, Vhw, Fhw[near_t], axis, radius, bottom_y, cut_y,
                               limit=GATES["tuck"])
        # the part's flat bottom, where it stands outside the stump and no collar covers it, goes inside
        stump = pm.stump_faces(Vbw, Fbw, rim_v, axis, radius, bottom_y, cut_y)
        pv = np.nonzero((Vhw[:, 1] >= bottom_y - 1e-9) & (Vhw[:, 1] <= cut_y)
                        & (np.linalg.norm(Vhw[:, [0, 2]] - axis, axis=1) < 1.5 * radius))[0]
        Vpt, tp = pm.tuck_band(Vhw, pv, axis, radius, bottom_y, cut_y, (Vbw, Fbw[stump]), hide=(Vbw, Fbw[~stump]),
                               limit=GATES["tuck"])
        sd["centre"] = None if centred is None else {k: (r4(v) if isinstance(v, float) else v) for k, v in centred.items()}
        sd["tuck"] = {k: (r4(v) if isinstance(v, float) else v) for k, v in tk.items()}
        sd["tuck_part"] = {k: (r4(v) if isinstance(v, float) else v) for k, v in tp.items()}
        worst = max(tk["shift_max"], tp["shift_max"])
        gates.append(gate("seam.tuck", r4(worst), f"<= {GATES['tuck']} of the radius (the largest move pulling the "
                          "anchor's exposed stump under the part's neck, or the part's exposed bottom inside the "
                          "stump)", worst <= GATES["tuck"]))
        if tp["moved"]:
            Vh, Fh, _ = arrays(head)
            _, _, inv = pm.weld(Vh, Fh)
            set_coords(head, Vh + (Vpt - Vhw)[inv])
            Vh, Fh, _ = arrays(head)
            Vhw, Fhw, _ = pm.weld(Vh, Fh)
        if tk["moved"]:
            _, _, inv = pm.weld(Vb, Fb)
            set_coords(body, Vb + (Vt - Vbw)[inv])
            Vb, Fb, _ = arrays(body)
            Vbw, Fbw, _ = pm.weld(Vb, Fb)
            rims = pm.loops_at(Vbw, Fbw, cut_y, 0.25 * radius, axis_xz=axis, radius=radius)
            rim_v = np.unique(np.concatenate(rims)) if rims else np.zeros(0, int)
        near_b = (np.abs(Vbw[Fbw].mean(1)[:, 1] - (bottom_y + collar_top) / 2) < (collar_top - bottom_y) / 2 + 2 * radius) & \
            (np.linalg.norm(Vbw[Fbw].mean(1)[:, [0, 2]] - axis, axis=1) < 4 * radius)

        near_h = np.abs(Vhw[Fhw].mean(1)[:, 1] - cut_y) < (cut_y - bottom_y) + 2 * radius

        def outward(pts):
            D = pts - np.c_[np.full(len(pts), axis[0]), pts[:, 1], np.full(len(pts), axis[1])]
            return D / np.maximum(np.linalg.norm(D, axis=1), 1e-12)[:, None]

        def covered(pts, own_V, own_F, other_V, other_F):
            """Share of edge points with geometry outside them on the outward horizontal ray: the other
            mesh anywhere from just inside the point (a coincident surface counts), or their own mesh
            beyond 10 % of the radius (past the faces at the edge itself)."""
            if not len(pts):
                return None
            D = outward(pts)
            t1, _ = pm.ray_hits(pts - D * 0.02 * radius, D, other_V, other_F, t_min=1e-9)
            t2, _ = pm.ray_hits(pts, D, own_V, own_F, t_min=0.1 * radius)
            return float((np.isfinite(t1) | np.isfinite(t2)).mean())

        edge = pm.loops_at(Vhw, Fhw, bottom_y, 0.25 * radius, axis_xz=axis, radius=radius)
        edge_v = np.unique(np.concatenate(edge)) if edge else np.zeros(0, int)
        h_part = covered(Vhw[edge_v], Vhw, Fhw[near_h], Vbw, Fbw[near_b])
        h_rim = covered(Vbw[rim_v], Vbw, Fbw[near_b], Vhw, Fhw[near_h])
        sel = np.nonzero((Vhw[:, 1] >= bottom_y) & (Vhw[:, 1] <= cut_y))[0]
        inside = None
        if len(sel):
            D = outward(Vhw[sel])
            t, _ = pm.ray_hits(Vhw[sel] - D * 0.02 * radius, D, Vbw, Fbw[near_b], t_min=1e-9)
            inside = float(np.isfinite(t).mean())
        sd.update({"part_edge_hidden": r4(h_part), "anchor_rim_hidden": r4(h_rim), "neck_inside_stump": r4(inside)})
        hv = None if h_part is None or h_rim is None else min(h_part, h_rim)
        gates.append(gate("seam.hidden", r4(hv), f">= {GATES['hidden']} (the part's cut edge and the anchor's rim "
                          "both have geometry outside them)", hv is not None and hv >= GATES["hidden"]))
    else:
        hl = pm.loops_at(Vhw, Fhw, cut_y, 0.25 * radius, axis_xz=axis, radius=radius)
        br = pm.bridge_ready(Vbw, rims, Vhw, hl, radius)
        sd["bridge"] = {k: (r4(v) if isinstance(v, float) else v) for k, v in br.items()}
        gates.append(gate("seam.loops", br["loops"], "one loop on each side", br["loops"] == [1, 1]))
        okgap = br["gap_mean"] is not None and br["gap_mean"] <= GATES["bridge_gap_mean"] and \
            br["gap_max"] <= GATES["bridge_gap_max"]
        gates.append(gate("seam.gap", [r4(br["gap_mean"]), r4(br["gap_max"])],
                          f"mean <= {GATES['bridge_gap_mean']}, max <= {GATES['bridge_gap_max']} of the radius", okgap))
        if br["loops"] == [1, 1] and okgap:
            zip_loops(body, Vbw, rims[0], Vhw[hl[0]])
            sd["bridged"] = True
    detail["seam"] = sd

    # ---- seam colour: the part's neck takes the anchor's skin at the cut, fading out below the chin
    g, detail["seam_colour"], neck_before = seam_colour(head, ref, body, axis, radius, cut_y, bottom_y,
                                                         float(neck["band"][1]), colours, rng)
    gates.append(g)

    # ---- coverage
    Vb, Fb, _ = arrays(body)
    Vh, Fh, _ = arrays(head)
    allV, allF = pm.merge((Vb, Fb), (Vh, Fh))
    if hair is not None:
        Vr, Fr, _ = arrays(hair)
        allV, allF = pm.merge((allV, allF), (Vr, Fr))
    if mode == "overlap":
        if len(rim_v):
            O = Vbw[rim_v].copy()
            D = np.c_[axis[0] - O[:, 0], np.zeros(len(O)), axis[1] - O[:, 2]]
            D /= np.maximum(np.linalg.norm(D, axis=1), 1e-12)[:, None]
            t, _ = pm.ray_hits(O, D, Vh, Fh, t_max=2.5 * radius)
            rim_share = float(np.isfinite(t).mean())
        else:
            rim_share = 0.0
            warnings.append("no anchor rim found at the cut")
        gates.append(gate("part.coverage.rim", r4(rim_share), f">= {GATES['rim']}", rim_share >= GATES["rim"]))
    centre = np.array([axis[0], (cut_y + top) / 2, axis[1]])
    hh = float(anchor.get("head_height") or (top - neck["band"][1]))
    dirs = pm.sphere_dirs(288)
    t, _ = pm.ray_hits(centre + dirs * 1.5 * hh, -dirs, allV, allF)
    sph = float(np.isfinite(t).mean())
    gates.append(gate("part.coverage.sphere", r4(sph), f">= {GATES['sphere']}", sph >= GATES["sphere"]))

    # ---- silhouettes against the anchor
    Vr0, Fr0, _ = arrays(ref)
    ymin, ymax = float(Vr0[:, 1].min()), float(Vr0[:, 1].max())
    upp = 1.1 * (ymax - ymin) / 512
    sil = {}
    head_rows = int(round(256 - (cut_y - (ymin + ymax) / 2) / upp))
    for view in VIEWS:
        u, _ = pm.view_uv(Vr0, view)
        frame = (upp, 256 - (u.min() + u.max()) / 2 / upp, 256 + (ymin + ymax) / 2 / upp)
        a = pm.silhouette(Vr0, Fr0, view, 512, frame)
        b = pm.silhouette(allV, allF, view, 512, frame)
        sil[view] = {"iou": r4(pm.iou(a, b)), "head_rows_iou": r4(pm.iou(a[:head_rows], b[:head_rows]))}
        gates.append(gate(f"assembly.silhouette.{view}", sil[view]["iou"], f">= {GATES['silhouette']} (provisional)",
                          sil[view]["iou"] >= GATES["silhouette"]))
    head_top = max(float(Vh[:, 1].max()), float(arrays(hair)[0][:, 1].max()) if hair is not None else -1e9)
    ext = (head_top - cut_y) / max(ymax - cut_y, 1e-9)
    gates.append(gate("assembly.head_extent_ratio", r4(ext), f"1 +- {GATES['head_extent']}",
                      abs(ext - 1) <= GATES["head_extent"]))
    detail["silhouette"] = sil

    # ---- outputs
    add_group(body, "part.body")
    add_group(head, "part.head")
    if hair is not None:
        add_group(hair, "part.hair")
    ref.hide_render = True
    ref.hide_set(True)
    outputs = {}
    objs = [body, head] + ([hair] if hair is not None else [])
    outputs["parts_glb"] = os.path.join(out_dir, f"{c}_parts.glb")
    export_glb(outputs["parts_glb"], objs)
    joined = rig_mesh(body, head, c, parts_col)
    outputs["rig_glb"] = os.path.join(out_dir, f"{c}_rig.glb")
    export_glb(outputs["rig_glb"], [joined])
    outputs["rig_materials"] = [m.name for m in joined.data.materials]
    bpy.data.objects.remove(joined, do_unlink=True)
    if hair is not None:
        outputs["hair_glb"] = os.path.join(out_dir, f"{c}_hair.glb")
        export_glb(outputs["hair_glb"], [hair])
    if render:
        try:
            outputs.update(render_compare(ref, objs, out_dir, render_px))
            outputs.update(render_neck(ref, objs, neck_before, axis, radius, cut_y, out_dir, render_px))
        except Exception as exc:          # renders are evidence for a person, never a gate
            warnings.append(f"render failed: {exc}")
    for o in objs:
        o.hide_render = False
    ref.hide_set(False)
    ref.hide_render = True
    outputs["parts_blend"] = os.path.join(out_dir, f"{c}_parts.blend")
    try:
        bpy.ops.file.pack_all()
    except RuntimeError as exc:
        warnings.append(f"pack_all: {exc}")
    bpy.ops.wm.save_as_mainfile(filepath=outputs["parts_blend"], copy=True)
    detail["objects"] = {o.name: {"faces": len(o.data.polygons), "materials": [m.name for m in o.data.materials]}
                         for o in objs}

    hard = [g for g in gates if not g["pass"] and not g.get("accepted")]
    ok = all(g["pass"] for g in gates)
    report = {"schema": "gate/1", "tool": "assemble_parts", "pass": ok, "ok": ok,
              "verdict": "green" if ok else "failed", "degraded": degraded, **detail, "outputs": outputs,
              "seconds": round(time.time() - t_start, 1), "warnings": warnings, "gates": gates}
    if degraded and accept_joined:
        report["accepted_by_person"] = [g["name"] for g in gates if g.get("accepted")]
    path = os.path.join(out_dir, f"{c}.parts.gate.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    report["outputs"]["report"] = path
    return (0 if not hard else 2), report


def seam_colour(head, ref, body, axis, radius, cut_y, bottom_y, chin, colours, rng):
    """The part's neck takes the anchor's skin colour at the seam (part_math seam_colour_field):
    fully at and below cut_y, fading to nothing at fade_top (the chin, at least half a radius above the
    cut) and away from the neck axis, written into the head's base-colour image (shared with the hair,
    repacked so the exports carry it). The gate reads only the sectors where the seam is in the open
    (no anchor geometry outside it but the neck itself, e.g. a hood's collar). Returns (gate, detail,
    the image's pixels before or None)."""
    np = _np()
    import part_math as pm
    node, slot = base_colour_node(head, with_slot=True)
    anode = base_colour_node(ref)
    limit = (f"worst sector: delta E of the part just above the cut to the anchor's rim <= {GATES['colour_delta']}, "
             f"sharpest lightness step per 0.1 radius <= {GATES['colour_edge']} (provisional)")
    fade_top = max(chin, cut_y + 0.5 * radius)
    step, y_lo = 0.1 * radius, bottom_y - 0.25 * radius
    ny = int(math.ceil((fade_top + 0.25 * radius - y_lo) / step))

    def side(obj):
        V, F, _ = arrays(obj)
        UV = corner_uvs(obj)
        c = V[F]
        rho = np.linalg.norm(c[:, :, [0, 2]] - axis, axis=2).min(1)
        m = (c[:, :, 1].max(1) >= y_lo) & (c[:, :, 1].min(1) <= y_lo + ny * step) & (rho < 1.8 * radius)
        return V, F, UV, m

    def outward(P, N):
        D = P[:, [0, 2]] - axis
        D /= np.maximum(np.linalg.norm(D, axis=1), 1e-12)[:, None]
        return (D * N[:, [0, 2]]).sum(1) > 0.2

    Vh, Fh, UVh, mh = side(head)
    Va, Fa, UVa, ma = side(ref)
    if node is not None:
        idx = np.empty(len(head.data.polygons), dtype=np.int64)
        head.data.polygons.foreach_get("material_index", idx)
        mh &= idx == slot
    if node is None or anode is None or UVh is None or UVa is None or mh.sum() < 20 or ma.sum() < 4:
        return (gate("seam.colour", None, limit, True, skipped="no textured neck on both sides"),
                {"skipped": "no textured neck on both sides"}, None)
    I, Ia = image_array(node.image), image_array(anode.image, rgb3=True)
    Pp, Np, _, uvp = pm.sample_surface_uv(Vh, Fh, UVh, 40000, rng, mh)
    Pa, Na, _, uva = pm.sample_surface_uv(Va, Fa, UVa, 40000, rng, ma)
    kp, ka = outward(Pp, Np), outward(Pa, Na)
    Pp, uvp, Pa, uva = Pp[kp], uvp[kp], Pa[ka], uva[ka]
    Cp, Ca = pm.sample_texture(I, uvp), pm.sample_texture(Ia, uva)
    skin = pm.hex_rgb(colours["skin"]) if colours.get("skin") else None
    hair = pm.hex_rgb(colours["hair"]) if colours.get("hair") else None
    field, fst = pm.seam_colour_field(Pp, Cp, Pa, Ca, axis, cut_y, radius, y_lo, step, ny, skin, hair)
    detail = {"fade_top": r4(fade_top), "field": fst, "image": node.image.name}
    before = None
    Cq = Cp
    if field is not None:
        I2, n = pm.apply_seam_colour(I, UVh[mh], Vh[Fh[mh]], field, axis, radius, cut_y, fade_top, y_lo, step)
        before = I
        img = node.image
        img.pixels.foreach_set(I2.astype(np.float32).reshape(-1))
        img.update()
        img.pack()                   # else the exports and the .blend keep the imported bytes
        Cq = pm.sample_texture(image_array(img), uvp)
        detail["texels_changed"] = n
    # the seam is in the open where an outward horizontal ray from the part just above the cut meets
    # nothing of the anchor but its neck within 3 radii
    Vb, Fb, _ = arrays(body)
    cb = Vb[Fb].mean(1)
    rb = np.linalg.norm(cb[:, [0, 2]] - axis, axis=1)
    near = (rb > 1.3 * radius) & (rb < 5 * radius) & (np.abs(cb[:, 1] - cut_y) < 3 * radius)
    band = (Pp[:, 1] >= cut_y) & (Pp[:, 1] <= cut_y + 0.15 * radius)
    open_p = np.ones(len(Pp), bool)
    if band.any() and near.any():
        O = Pp[band]
        D = np.c_[O[:, 0] - axis[0], np.zeros(len(O)), O[:, 2] - axis[1]]
        D /= np.maximum(np.linalg.norm(D, axis=1), 1e-12)[:, None]
        t, _ = pm.ray_hits(O, D, Vb, Fb[near], t_min=1e-9, t_max=3 * radius)
        open_p[np.nonzero(band)[0]] = ~np.isfinite(t)
    rep = pm.seam_colour_report(Pp, Cp, Cq, Pa, Ca, axis, radius, cut_y, fade_top, skin, hair, open_p=open_p)
    detail.update(rep)
    if not rep["sectors"]:
        return (gate("seam.colour", None, limit, True, skipped="no skin seam in the open (covered, or no skin on "
                     "both sides)"), detail, before)
    da, ea = rep.get("delta_after"), rep.get("edge_L_after")
    passed = da is not None and da <= GATES["colour_delta"] and (ea is None or ea <= GATES["colour_edge"])
    return gate("seam.colour", [da, ea], limit, passed, before=[rep.get("delta_before"), rep.get("edge_L_before")]), \
        detail, before


def rig_mesh(body, head, c, col):
    """Body + Head joined into one new object (both materials kept): what the rig stage imports."""
    import bpy
    a, b = body.copy(), head.copy()
    a.data, b.data = body.data.copy(), head.data.copy()
    col.objects.link(a)
    col.objects.link(b)
    with bpy.context.temp_override(active_object=a, selected_editable_objects=[a, b]):
        bpy.ops.object.join()
    a.name = a.data.name = c
    for vg in list(a.vertex_groups):
        a.vertex_groups.remove(vg)
    return a


def zip_loops(body, Vbw, rim_loop, part_pts):
    """Bridge the anchor's rim loop to the part's loop: the part loop's points are added to Body and
    the two rings zipped with triangles (unequal counts allowed), both rings ordered the same way."""
    import bmesh
    np = _np()
    A = Vbw[rim_loop]
    B = np.asarray(part_pts, float)
    ca = A[:, [0, 2]].mean(0)
    ang_a = np.arctan2(A[:, 2] - ca[1], A[:, 0] - ca[0])
    ang_b = np.arctan2(B[:, 2] - ca[1], B[:, 0] - ca[0])
    A = A[np.argsort(ang_a)]
    B = B[np.argsort(ang_b)]
    bm = bmesh.new()
    bm.from_mesh(body.data)
    va = [bm.verts.new(tuple(p)) for p in to_blender(A)]
    vb = [bm.verts.new(tuple(p)) for p in to_blender(B)]
    i = j = 0
    na, nb = len(va), len(vb)
    while i < na or j < nb:
        ta = math.atan2(A[(i + 1) % na, 2] - ca[1], A[(i + 1) % na, 0] - ca[0]) + (2 * math.pi if i + 1 >= na else 0)
        tb = math.atan2(B[(j + 1) % nb, 2] - ca[1], B[(j + 1) % nb, 0] - ca[0]) + (2 * math.pi if j + 1 >= nb else 0)
        if (ta <= tb and i < na) or j >= nb:
            bm.faces.new((va[i % na], va[(i + 1) % na], vb[j % nb]))
            i += 1
        else:
            bm.faces.new((va[i % na], vb[(j + 1) % nb], vb[j % nb]))
            j += 1
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    bm.to_mesh(body.data)
    bm.free()


# --------------------------------------------------------------------------------------- renders
def _studio():
    """Workbench (studio light, back faces culled) and an orthographic camera: (scene, shading, camera)."""
    import bpy
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    sh = scene.display.shading
    sh.light = 'STUDIO'
    sh.show_backface_culling = True
    sh.single_color = (0.8, 0.8, 0.78)
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.color = (0.18, 0.18, 0.2)
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'
    scene.render.resolution_percentage = 100
    cam_data = bpy.data.cameras.new("PartsCam")
    cam_data.type = 'ORTHO'
    cam = bpy.data.objects.new("PartsCam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    return scene, sh, cam


def _shoot(scene, cam, d, target, path):
    """Render looking along d (Blender frame) at target; the frame as (h, w, 4) floats, top row first."""
    import bpy
    np = _np()
    from mathutils import Matrix, Vector
    z = -d
    x = Vector((0, 0, 1)).cross(z).normalized()
    y = z.cross(x)
    cam.matrix_world = Matrix(((x[0], y[0], z[0], 0), (x[1], y[1], z[1], 0), (x[2], y[2], z[2], 0), (0, 0, 0, 1)))
    cam.location = target - d * 5.0
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path)
    a = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    out = a.reshape(img.size[1], img.size[0], 4)[::-1]
    bpy.data.images.remove(img)
    return out


def _sheet(tiles, w, h, path, gap=6):
    """Save rows of (h, w, 4) frames as one PNG, white gaps between them."""
    import bpy
    np = _np()
    H = len(tiles) * h + (len(tiles) - 1) * gap
    W = len(tiles[0]) * w + (len(tiles[0]) - 1) * gap
    sheet = np.ones((H, W, 4), dtype=np.float32)
    for r, line in enumerate(tiles):
        for k, a in enumerate(line):
            sheet[r * (h + gap): r * (h + gap) + h, k * (w + gap): k * (w + gap) + w] = a
    img = bpy.data.images.new(os.path.basename(path), W, H, alpha=False)
    img.pixels.foreach_set(sheet[::-1].reshape(-1))
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    return path


# the direction each camera looks (Blender frame: the character faces -Y, its left is +X)
def _dirs():
    from mathutils import Vector
    return {"front": Vector((0, 1, 0)), "left": Vector((-1, 0, 0)), "back": Vector((0, -1, 0)),
            "right": Vector((1, 0, 0))}


def render_compare(ref, objs, out_dir, px=768):
    """compare.png (whole body) and compare_head.png: columns front / left / back / right; rows anchor
    clay, assembly clay, anchor textured, assembly textured. Workbench, back faces culled."""
    import bpy
    np = _np()
    from mathutils import Vector
    scene, sh, cam = _studio()
    Vr, _, _ = arrays(ref)
    lo, hi = to_blender(Vr).min(0), to_blender(Vr).max(0)
    centre = (lo + hi) / 2
    tmp = tempfile.mkdtemp(prefix="parts_render_")
    dirs = _dirs()
    out = {}
    head_lo_z = float(np.percentile(to_blender(arrays(objs[1])[0])[:, 2], 1))
    shots = {"compare": (Vector(centre), (hi[2] - lo[2]) * 1.06, (px // 2, px)),
             "compare_head": (Vector((centre[0], centre[1], (head_lo_z + hi[2]) / 2)), (hi[2] - head_lo_z) * 1.25, (px * 2 // 3, px * 2 // 3))}
    for name, (target, scale, (w, h)) in shots.items():
        scene.render.resolution_x, scene.render.resolution_y = w, h
        cam.data.ortho_scale = scale                     # spans the longer side of the frame
        tiles = []
        for row, (shown, colour) in enumerate(((ref, 'SINGLE'), (None, 'SINGLE'), (ref, 'TEXTURE'), (None, 'TEXTURE'))):
            ref.hide_render = shown is None
            for o in objs:
                o.hide_render = shown is not None
            sh.color_type = colour
            tiles.append([_shoot(scene, cam, dirs[v], target, os.path.join(tmp, f"{name}_{row}_{v}.png")) for v in VIEWS])
        out[name] = _sheet(tiles, w, h, os.path.join(out_dir, f"{name}.png"))
    bpy.data.objects.remove(cam, do_unlink=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def render_neck(ref, objs, before, axis, radius, cut_y, out_dir, px=768):
    """neck.png: the neck close up (4.5 radii across, centred 0.3 radius above the cut), rows front and
    front-left three-quarter, columns before and after the seam colour match. Nothing without a match."""
    import bpy
    np = _np()
    if before is None:
        return {}
    node = base_colour_node(objs[1])
    after = node.image
    w, h = after.size
    shown = []                          # both columns from arrays, read as the original is
    for name, arr in (("neck_before", before), ("neck_after", image_array(after))):
        img = bpy.data.images.new(name, w, h, alpha=arr.shape[2] == 4)
        img.colorspace_settings.name = after.colorspace_settings.name
        img.alpha_mode = after.alpha_mode
        img.pixels.foreach_set(arr.astype(np.float32).reshape(-1))
        shown.append(img)
    scene, sh, cam = _studio()
    sh.color_type = 'TEXTURE'
    ref.hide_render = True
    for o in objs:
        o.hide_render = False
    side = px * 2 // 3
    scene.render.resolution_x = scene.render.resolution_y = side
    cam.data.ortho_scale = 4.5 * radius
    from mathutils import Vector
    target = Vector(to_blender(np.array([[axis[0], cut_y + 0.3 * radius, axis[1]]]))[0])
    d = _dirs()
    tmp = tempfile.mkdtemp(prefix="parts_neck_")
    tiles = []
    try:
        for view in (d["front"], (d["front"] + d["left"]).normalized()):
            line = []
            for k, img in enumerate(shown):
                node.image = img
                line.append(_shoot(scene, cam, view, target, os.path.join(tmp, f"neck_{len(tiles)}_{k}.png")))
            tiles.append(line)
    finally:
        node.image = after
        for img in shown:
            bpy.data.images.remove(img)
        bpy.data.objects.remove(cam, do_unlink=True)
        shutil.rmtree(tmp, ignore_errors=True)
    return {"neck": _sheet(tiles, side, side, os.path.join(out_dir, "neck.png"))}


# ------------------------------------------------------------------------------------------ bind
def recover_prep(raw, prepped):
    """(s, t, residual) with prepped ~ s * raw + t, from the z extents and the minima (the rig stage's
    import moves the base to the origin and scales to a height); residual = the largest distance from
    each moved raw vertex to the nearest prepped vertex (the caller passes an nn over prepped)."""
    np = _np()
    s = float(np.ptp(prepped[:, 2]) / max(np.ptp(raw[:, 2]), 1e-12))
    t = prepped.min(0) - s * raw.min(0)
    return s, t


def bind(out, hair_glb, rig_glb, name=None):
    import bpy
    np = _np()
    out = os.path.abspath(out)
    rig_dir = os.path.join(out, "rig")
    if name is None:
        blends = [f for f in os.listdir(rig_dir) if f.endswith("_arp.blend") and not f.endswith("pre_parts.blend")] \
            if os.path.isdir(rig_dir) else []
        if len(blends) != 1:
            raise Refused(f"{rig_dir}: {len(blends)} *_arp.blend files; pass --name")
        name = blends[0][:-len("_arp.blend")]
    blend = os.path.join(rig_dir, f"{name}_arp.blend")
    contract = os.path.join(rig_dir, f"{name}.contract.json")
    for p in (blend, contract, hair_glb, rig_glb):
        if not os.path.isfile(p):
            raise Refused(f"missing {p}")
    with open(contract, encoding="utf-8") as handle:
        head_bone = (json.load(handle).get("retarget_map") or {}).get("Head")
    if not head_bone:
        raise Refused(f"{contract} maps no Head bone")
    bpy.ops.wm.open_mainfile(filepath=blend)
    rigs = [o for o in bpy.data.objects if o.type == 'ARMATURE' and head_bone in o.data.bones]
    if len(rigs) != 1:
        raise Refused(f"{len(rigs)} armatures carry the bone {head_bone!r}")
    rig = rigs[0]
    # an earlier bind's hair: marked parts_hair, or (an older file) the mesh named Hair bound to the rig
    is_hair = lambda o: o.type == 'MESH' and (o.get("parts_hair") or (o.name.split(".")[0] == "Hair" and any(
        m.type == 'ARMATURE' and m.object == rig for m in o.modifiers)))
    bound = [o for o in bpy.data.objects if o.type == 'MESH' and not is_hair(o)
             and any(m.type == 'ARMATURE' and m.object == rig for m in o.modifiers)]
    if not bound:
        raise Refused("no mesh is bound to the rig")
    if not any(is_hair(o) for o in bpy.data.objects):   # the backup is the rig before any bind, never a re-bind
        shutil.copy2(blend, os.path.join(rig_dir, f"{name}_arp.pre_parts.blend"))
    mesh = max(bound, key=lambda o: len(o.data.vertices))
    co = np.empty(len(mesh.data.vertices) * 3)
    mesh.data.vertices.foreach_get("co", co)
    M = np.array(mesh.matrix_world)
    prepped = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    tmp_col = collection("PartsTmp")
    raw_obj = import_glb(rig_glb, "PartsRawRig", tmp_col)
    rco = np.empty(len(raw_obj.data.vertices) * 3)
    raw_obj.data.vertices.foreach_get("co", rco)
    raw = rco.reshape(-1, 3)
    bpy.data.objects.remove(raw_obj, do_unlink=True)
    s, t = recover_prep(raw, prepped)
    d, _ = kd_nn(prepped)(s * raw + t)
    height = float(np.ptp(prepped[:, 2]))
    residual = float(d.max())
    for old in [o for o in bpy.data.objects if is_hair(o)]:     # bind again: replace, never add
        bpy.data.objects.remove(old, do_unlink=True)
    hair = import_glb(hair_glb, "Hair", mesh.users_collection[0])
    hair["parts_hair"] = True
    shared = share_materials(hair, bound)      # the head's material once, not a .001 copy in the FBX
    hco = np.empty(len(hair.data.vertices) * 3)
    hair.data.vertices.foreach_get("co", hco)
    hair.data.vertices.foreach_set("co", (s * hco.reshape(-1, 3) + t).reshape(-1))
    hair.data.update()
    for vg in list(hair.vertex_groups):
        hair.vertex_groups.remove(vg)
    add_group(hair, head_bone)
    mod = hair.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig
    mw = hair.matrix_world.copy()
    hair.parent = rig
    hair.matrix_world = mw
    groups = {g.index: g.name for g in hair.vertex_groups}
    bad = sum(1 for v in hair.data.vertices
              if len(v.groups) != 1 or groups[v.groups[0].group] != head_bone or abs(v.groups[0].weight - 1) > 1e-6)
    gates = [gate("parts.transform_residual", residual, f"<= {1e-5 * height:.3g} (1e-5 x height)",
                  residual <= 1e-5 * height),
             gate("parts.hair_bound", bad, 0, bad == 0)]
    export = {}
    if all(g["pass"] for g in gates):
        root = os.path.normpath(os.path.join(HERE, "..", ".."))
        sys.path.insert(0, os.path.join(root, "blender-retarget", "scripts"))
        import brt_arp
        export = brt_arp.run({"op": "export", "armature": rig.name, "fbx": os.path.join(out, "export", f"{name}.fbx")})
        gates += [g for g in export.get("gates", [])]
        bpy.ops.wm.save_as_mainfile(filepath=blend)
    ok = all(g["pass"] for g in gates)
    rep = {"schema": "gate/1", "tool": "assemble_parts", "op": "bind", "pass": ok, "ok": ok,
           "verdict": "green" if ok else "failed", "name": name, "head_bone": head_bone, "scale": s,
           "shift": [float(x) for x in t], "hair_vertices": len(hair.data.vertices), "materials_shared": shared,
           "export": {k: v for k, v in export.items() if k in ("export", "meshes", "refused", "reason")},
           "next": f"autorig.py deform {out}", "gates": gates}
    return (0 if ok else 2), rep


# --------------------------------------------------------------------------------------- selftest
def _make_mesh(name, V, F, kind, col, hair_rgb, skin_rgb):
    """A Blender mesh from glTF-frame arrays, textured hair / skin by face kind: a cylindrical map per
    corner, skin faces on the texture's left half, hair on its right half."""
    import bpy
    np = _np()
    me = bpy.data.meshes.new(name)
    me.from_pydata(to_blender(V).tolist(), [], F.tolist())
    me.update()
    uv = me.uv_layers.new(name="UVMap")
    P = V[F]
    ul = (np.arctan2(P[..., 0], P[..., 2]) + np.pi) / (2 * np.pi)
    wrap = np.repeat(np.ptp(ul, axis=1)[:, None] > 0.5, 3, axis=1) & (ul < 0.5)
    ul[wrap] += 1.0                                   # a triangle across the map's edge stays whole
    vl = (P[..., 1] - V[:, 1].min()) / max(np.ptp(V[:, 1]), 1e-9)
    hair = np.isin(kind, (1, 3))[:, None]
    per = np.stack([0.02 + 0.42 * ul + 0.5 * hair, 0.02 + 0.96 * vl], axis=-1)
    uv.data.foreach_set("uv", per.reshape(-1))
    img = bpy.data.images.new(f"{name}_tex", 128, 128, alpha=False)
    px = np.ones((128, 128, 4), np.float32)
    px[:, :64, :3] = skin_rgb
    px[:, 64:, :3] = hair_rgb
    img.pixels.foreach_set(px.reshape(-1))
    img.pack()
    mat = bpy.data.materials.new(f"{name}_mat")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = 'Closest'
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    me.materials.append(mat)
    obj = bpy.data.objects.new(name, me)
    col.objects.link(obj)
    return obj


def _fixture(tmp, tag, scale_err=1.0, neck_bottom=None, neck_r=0.0335):
    """A synthetic anchor GLB, a synthetic head part GLB (finer, in its own normalised frame, a little
    off: 2 degrees, a shift, scale_err) and a plan from part_math.plan_core."""
    import bpy
    np = _np()
    import part_math as pm
    clear_scene()
    col = collection("Fixture")
    hair_rgb, skin_rgb = (0.23, 0.16, 0.12), (0.91, 0.71, 0.55)
    V0, F0, k0 = pm.synthetic_figure(res=1)
    Vw, Fw, _ = pm.weld(V0, F0)
    frame = (1.063e-3, 512.0, 512.0)
    masks = {v: pm.silhouette(Vw, Fw, v, 1024, frame) for v in VIEWS}
    doc, _, _ = pm.plan_core(Vw, Fw, masks, "three", "testchar")
    head = next(p for p in doc["parts"] if p["region"] == "head")
    s0 = head["views"]["box_side_px"] / 1024.0
    tb = pm.box_centre(doc["anchor"]["frame"], head["views"]["boxes"])
    nb = head["seam"]["part_bottom_y"] - 0.004 if neck_bottom is None else neck_bottom
    # a drawn neck at the anchor's width (a hair wider, so it covers the anchor's rim)
    V1, F1, k1 = pm.synthetic_figure(res=2, neck_bottom=nb, neck_r=neck_r)
    Rp = pm._rot([0.2, 1.0, 0.1], 2.0)
    Vp = ((V1 - tb) @ Rp) / (s0 * scale_err) + np.array([0.01, -0.012, 0.008])
    anchor_path = os.path.join(tmp, f"{tag}_anchor.glb")
    head_path = os.path.join(tmp, f"{tag}_head.glb")
    head_skin = tuple(0.88 * x for x in skin_rgb)      # the head job's skin a shade darker: the seam colour's work
    for path, V, F, k, nm, sk in ((anchor_path, V0, F0, k0, "A", skin_rgb), (head_path, Vp, F1, k1, "H", head_skin)):
        clear_scene()
        obj = _make_mesh(nm, V, F, k, collection("Fixture"), hair_rgb, sk)
        export_glb(path, [obj])
    clear_scene()
    doc["anchor"] = {"glb": os.path.basename(anchor_path), "glb_sha256": pm.sha256(anchor_path), **doc["anchor"]}
    head["generated"] = {"glb": os.path.basename(head_path)}
    head["views"]["colours"] = {"hair": "#3b2a1f", "skin": "#e8b58c"}
    plan_path = os.path.join(tmp, f"{tag}.parts.json")
    with open(plan_path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1)
    return plan_path, doc


def selftest():
    import bpy
    np = _np()
    import part_math as pm
    checks, failed, notes = [], [], {}

    def ok(name, cond, value=None):
        checks.append({"check": name, "pass": bool(cond), **({"value": value} if value is not None else {})})
        if not cond:
            failed.append(name)

    tmp = tempfile.mkdtemp(prefix="assemble_parts_selftest_")
    try:
        plan, doc = _fixture(tmp, "good")
        code, rep = assemble(plan, os.path.join(tmp, "good_out"), render=True, render_px=192)
        notes["good"] = {g["name"]: g["value"] for g in rep["gates"]}
        ok("good: exit 0, every gate passes", code == 0 and rep["pass"] is True,
           [g["name"] for g in rep["gates"] if not g["pass"]])
        ok("good: a gate/1 report", rep.get("schema") == "gate/1" and rep.get("ok") is True
           and all("pass" in g and "ok" not in g for g in rep["gates"]))
        names = {o.name for o in bpy.data.collections["Parts"].objects}
        ok("good: Body, Head and Hair objects", {"Body", "Head", "Hair"} <= names, sorted(names))
        ok("good: the hair is its own object", len(bpy.data.objects["Hair"].data.polygons) > 0
           and rep["degraded"] is None)
        ok("good: renders written", os.path.isfile(rep["outputs"].get("compare", "")))
        clear_scene()
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=rep["outputs"]["rig_glb"])
        meshes = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
        ok("good: the rig GLB holds one mesh with two materials",
           len(meshes) == 1 and len(meshes[0].data.materials) == 2,
           [(o.name, len(o.data.materials)) for o in meshes])
        sc = rep.get("seam_colour") or {}
        ok("good: seam colour: the darker head's neck matched to the anchor's rim in the open front",
           sc.get("sectors", 0) >= 1 and sc.get("delta_before", 0) > 5 and sc.get("delta_after", 99) <= GATES["colour_delta"],
           {k: sc.get(k) for k in ("sectors", "delta_before", "delta_after", "edge_L_before", "edge_L_after")})
        changed = None
        if meshes:
            hm = next((m for m in meshes[0].data.materials if m and "head" in m.name), None)
            hn = None
            if hm is not None:
                hn = next((n for n in hm.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image is not None), None)
            if hn is not None:
                a = image_array(hn.image)[..., :3]
                ds = np.abs(a[:, :64] - [0.88 * x for x in (0.91, 0.71, 0.55)]).max(2) > 2 / 255
                dh = np.abs(a[:, 64:] - [0.23, 0.16, 0.12]).max(2) > 2 / 255
                changed = [int(ds.sum()), int(dh.sum())]
        ok("good: the rig GLB's head texture carries the match (skin half changed, hair half not)",
           changed is not None and changed[0] > 0 and changed[1] == 0, changed)
        ok("good: the collar stays", rep["gates"] and next(g for g in rep["gates"] if g["name"] == "part.cut.collar_kept")["pass"])
        contract_sample("assemble_parts", "good", rep)

        code, rep = assemble(plan, os.path.join(tmp, "bridge_out"), seam_mode="bridge", render=False)
        gv = {g["name"]: g for g in rep["gates"]}
        ok("bridge: one loop each side, gap within limits, bridged, exit 0",
           code == 0 and gv["seam.loops"]["pass"] and gv["seam.gap"]["pass"] and rep["seam"].get("bridged") is True,
           {k: gv[k]["value"] for k in ("seam.loops", "seam.gap") if k in gv})
        Vb, Fb, _ = arrays(bpy.data.objects["Body"])
        Vbw, Fbw, _ = pm.weld(Vb, Fb)
        neck = doc["anchor"]["neck"]
        open_rims = pm.loops_at(Vbw, Fbw, doc["parts"][1]["seam"]["cut_y"], 0.25 * neck["radius"],
                                axis_xz=neck["axis_xz"], radius=neck["radius"])
        Vh, Fh, _ = arrays(bpy.data.objects["Head"])
        Vhw, Fhw, _ = pm.weld(Vh, Fh)
        head_rims = pm.loops_at(Vhw, Fhw, doc["parts"][1]["seam"]["cut_y"], 0.25 * neck["radius"],
                                axis_xz=neck["axis_xz"], radius=neck["radius"])
        gap = None
        if len(open_rims) == 1 and len(head_rims) == 1:
            a, b = Vbw[open_rims[0]], Vhw[head_rims[0]]
            gap = float(np.sqrt(((a[:, None] - b[None]) ** 2).sum(-1)).min(1).max())
        ok("bridge: Body now ends exactly on the part's cut loop (they weld when joined)",
           gap is not None and gap < 1e-5, gap)

        plan, _ = _fixture(tmp, "scaled", scale_err=1.2)
        code, rep = assemble(plan, os.path.join(tmp, "scaled_out"), render=False)
        sr = next(g for g in rep["gates"] if g["name"] == "part.register.scale_ratio")
        ok("scaled 1.2: part.register.scale_ratio fails, exit 2", code == 2 and not sr["pass"], sr["value"])
        contract_sample("assemble_parts", "scaled", rep)

        plan, _ = _fixture(tmp, "slim", neck_r=0.029)
        code, rep = assemble(plan, os.path.join(tmp, "slim_out"), render=False)
        gv = {g["name"]: g for g in rep["gates"]}
        ok("a slightly slim neck: the anchor's rim is tucked under it, seam.hidden passes, exit 0",
           code == 0 and rep["seam"]["tuck"]["moved"] > 0 and gv["seam.hidden"]["pass"],
           [rep["seam"]["tuck"], gv["seam.hidden"]["value"]])

        plan, _ = _fixture(tmp, "thin", neck_r=0.022)
        code, rep = assemble(plan, os.path.join(tmp, "thin_out"), render=False)
        gv = {g["name"]: g for g in rep["gates"]}
        ok("a thin neck under an open collar: seam.tuck and seam.hidden fail, nothing moved, exit 2",
           code == 2 and not gv["seam.tuck"]["pass"] and not gv["seam.hidden"]["pass"]
           and rep["seam"]["tuck"]["moved"] == 0, [gv["seam.tuck"]["value"], gv["seam.hidden"]["value"]])

        cut = doc["parts"][1]["seam"]["cut_y"]
        plan, _ = _fixture(tmp, "short", neck_bottom=cut + 0.012)
        code, rep = assemble(plan, os.path.join(tmp, "short_out"), render=False)
        cov = next(g for g in rep["gates"] if g["name"] == "part.coverage.rim")
        ok("short neck: part.coverage.rim fails, exit 2", code == 2 and not cov["pass"], cov["value"])

        # bind's transform recovery on a synthetic prepped copy (bind itself needs Auto-Rig Pro)
        raw = np.random.default_rng(3).normal(size=(500, 3)) * [0.3, 0.1, 0.5]
        c = np.array([(raw[:, 0].min() + raw[:, 0].max()) / 2, (raw[:, 1].min() + raw[:, 1].max()) / 2, raw[:, 2].min()])
        prepped = (raw - c) * (1.2 / np.ptp(raw[:, 2]))
        s, t = recover_prep(raw, prepped)
        res = float(np.abs(s * raw + t - prepped).max())
        ok("bind: the prep transform is recovered", res < 1e-9, res)

        # bind's material sharing: the hair's copy of the head material (the rig stage renamed the
        # original) goes; one whose pixels differ stays
        def mat_obj(name, mat_name, img_name, rgba):
            img = bpy.data.images.new(img_name, 8, 8)
            img.pixels.foreach_set(np.tile(np.array(rgba, np.float32), 64))
            mat = bpy.data.materials.new(mat_name)
            mat.use_nodes = True
            for _ in range(2):      # two nodes reading one image, as a glTF material can
                mat.node_tree.nodes.new("ShaderNodeTexImage").image = img
            me = bpy.data.meshes.new(name)
            me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
            me.materials.append(mat)
            o = bpy.data.objects.new(name, me)
            bpy.context.scene.collection.objects.link(o)
            return o, mat
        head_o, head_m = mat_obj("ShareHead", "RunnerMat1", "share_head_BASE_COLOR", (0.6, 0.4, 0.3, 1.0))
        hair_o, copy_m = mat_obj("ShareHair", "share_head", "share_head_BASE_COLOR.001", (0.6, 0.4, 0.3, 1.0))
        other_o, other_m = mat_obj("ShareOther", "share_head.001", "share_head_BASE_COLOR.002", (0.1, 0.1, 0.1, 1.0))
        shared = share_materials(hair_o, [head_o])
        kept = share_materials(other_o, [head_o])
        ok("bind: the hair's copy of the head material is shared and dropped; a different one is kept",
           shared == ["share_head"] and hair_o.data.materials[0] is head_m
           and bpy.data.images.get("share_head_BASE_COLOR.001") is None
           and kept == [] and other_o.data.materials[0] is other_m, [shared, kept])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return (0 if not failed else 1), {"selftest": "pass" if not failed else "fail", "failed": failed,
                                      "checks": checks, "gate_values": notes}


def contract_sample(script, case, doc):
    """Hand one selftest report to tools/check-contracts.py: written to $UNITY_DEV_CONTRACT_OUT (else a fixed
    folder in the temp dir) as <script>__<case>.gate.json, and named on stdout as `selftest-output: <path>`."""
    out = os.environ.get("UNITY_DEV_CONTRACT_OUT") or os.path.join(tempfile.gettempdir(), "unity-dev-contract-out")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{script}__{case}.gate.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1)
    print(f"selftest-output: {path}")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser().parse_args(argv)
    if not args.selftest and args.cmd is None:
        parser().print_usage(sys.stderr)
        sys.exit(1)
    try:
        import bpy  # noqa: F401
    except ImportError:
        print(json.dumps({"tool": "assemble_parts", "error": "run inside Blender: blender -b -P assemble_parts.py -- ..."}))
        sys.exit(1)
    try:
        if args.selftest:
            code, report = selftest()
        elif args.cmd == "assemble":
            code, report = assemble(args.plan, args.out, args.seam, args.accept_joined_hair, not args.no_render)
        else:
            code, report = bind(args.autorig_out, args.hair, args.rig_glb, args.name)
    except Refused as exc:
        code, report = 1, {"schema": "gate/1", "tool": "assemble_parts", "pass": False, "ok": False,
                           "verdict": "failed", "gates": [], "refused": str(exc)}
    except Exception as exc:              # Blender -b exits 0 on an uncaught error: make it a failure
        import traceback
        traceback.print_exc()
        code, report = 1, {"schema": "gate/1", "tool": "assemble_parts", "pass": False, "ok": False,
                           "verdict": "harness", "gates": [], "error": f"{type(exc).__name__}: {exc}"}
    if getattr(args, "report", None):     # bind's report, refusals and errors included
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1, default=str)
    print(json.dumps(report, indent=1, default=str))
    sys.stdout.flush()
    sys.exit(code)


if __name__ == "__main__":
    main()
