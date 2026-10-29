"""autorig_blender.py — what the Blender scripts of this skill share. Imported, never run.

arp_markers.py and deform_gate.py run as `blender -b [file.blend] -P <script> -- <args>` and import
this from their own folder. It holds: the argument list after `--`, the mesh as numpy arrays, the
one-JSON-object print with an exit code, a Workbench render of a few views with marker spheres,
and, for the selftests, a procedural runner (a metaball body in an A-pose, facing -Y, soles on
Z 0) with its true joint positions, and an armature built from a bone list.

Nothing here edits a datablock it did not create, except `clear_scene` (selftests only).
"""
from __future__ import annotations

import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def script_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def finish(report: dict, code: int, out: str | None = None) -> None:
    """Print the report, write it to `out`, and leave Blender with `code`."""
    text = json.dumps(report, indent=2, default=_plain)
    if out:
        with open(out, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(text)
    sys.stdout.flush()
    sys.exit(code)          # under -P, Blender exits with this code


def _plain(value):
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, (np.ndarray, Vector)):
        return [round(float(x), 6) for x in value]
    return str(value)


def r6(values) -> list[float]:
    return [round(float(x), 6) for x in values]


def mesh_arrays(obj, evaluated: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """(world vertices (n, 3), triangles (m, 3)) of a mesh object, modifiers applied when evaluated."""
    if evaluated:
        dg = bpy.context.evaluated_depsgraph_get()
        src = obj.evaluated_get(dg)
        mesh = src.to_mesh()
    else:
        src, mesh = obj, obj.data
    try:
        mesh.calc_loop_triangles()
        v = np.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", v)
        f = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
        mesh.loop_triangles.foreach_get("vertices", f)
    finally:
        if evaluated:
            src.to_mesh_clear()
    v = v.reshape(-1, 3)
    mw = np.array(obj.matrix_world)
    v = v @ mw[:3, :3].T + mw[:3, 3]
    return v, f.reshape(-1, 3)


def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for kind in ("meshes", "armatures", "metaballs", "materials", "actions", "cameras", "lights"):
        coll = getattr(bpy.data, kind)
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)


# --- preview renders ---------------------------------------------------------

def render_views(out_dir: str, prefix: str, points: dict, chains: list, views=("front", "side"),
                 size: int = 768, radius: float = 0.012, focus=None, objects=None) -> dict:
    """Render the scene's meshes through orthographic cameras with a sphere per point.

    `points` {name: [x, y, z]} are drawn as spheres coloured by side (.L green, .R red, centre
    yellow); `chains` [[a, b], ...] as thin rods. front looks along +Y (the character's left is on
    the right of the image), side along -X (its front on the left). `objects` limits the render to
    those meshes (the others are hidden from it for the call). Everything added is removed and
    every render setting put back. Returns {view: path}.
    """
    scene = bpy.context.scene
    render, shading = scene.render, scene.display.shading
    saved = {"engine": render.engine, "x": render.resolution_x, "y": render.resolution_y,
             "pct": render.resolution_percentage, "path": render.filepath, "camera": scene.camera,
             "fmt": render.image_settings.file_format, "light": shading.light,
             "color": shading.color_type, "film": render.film_transparent}
    added = []
    meshes = [o for o in scene.objects if o.type == 'MESH' and o.visible_get()]
    hidden = []
    if objects is not None:
        hidden = [o for o in meshes if o not in objects and not o.hide_render]
        meshes = [o for o in meshes if o in objects]
        for o in hidden:
            o.hide_render = True
    pts = [Vector(p) for p in points.values()]
    if focus is None:
        corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box] + pts
        lo = Vector([min(c[i] for c in corners) for i in range(3)])
        hi = Vector([max(c[i] for c in corners) for i in range(3)])
    else:
        lo, hi = Vector(focus[0]), Vector(focus[1])
    centre, extent = (lo + hi) / 2, hi - lo
    out = {}
    try:
        for name, xyz in points.items():
            mesh = bpy.data.meshes.new(f"_mk_{name}")
            obj = bpy.data.objects.new(f"_mk_{name}", mesh)
            scene.collection.objects.link(obj)
            _uv_sphere(mesh, radius)
            obj.location = xyz
            obj.color = (0.1, 0.9, 0.2, 1) if name.endswith(".L") else \
                (0.95, 0.15, 0.1, 1) if name.endswith(".R") else (1.0, 0.85, 0.1, 1)
            obj.show_in_front = True
            added.append(obj)
        for a, b in chains:
            if a not in points or b not in points:
                continue
            pa, pb = Vector(points[a]), Vector(points[b])
            if (pb - pa).length < 1e-6:
                continue
            mesh = bpy.data.meshes.new("_mk_rod")
            obj = bpy.data.objects.new("_mk_rod", mesh)
            scene.collection.objects.link(obj)
            _rod(mesh, pa, pb, radius * 0.35)
            obj.color = (0.2, 0.5, 1.0, 1)
            obj.show_in_front = True
            added.append(obj)
        render.engine = 'BLENDER_WORKBENCH'
        shading.light, shading.color_type = 'STUDIO', 'OBJECT'
        render.film_transparent = False
        render.image_settings.file_format = 'PNG'
        render.resolution_percentage = 100
        for obj in meshes:
            if not obj.name.startswith("_mk_"):
                obj.color = (0.75, 0.75, 0.78, 1)
        for view in views:
            cam_data = bpy.data.cameras.new("_mk_cam")
            cam = bpy.data.objects.new("_mk_cam", cam_data)
            scene.collection.objects.link(cam)
            added.append(cam)
            cam_data.type = 'ORTHO'
            if view == "front":
                cam.location = centre + Vector((0, -10, 0))
                cam.rotation_euler = (math.pi / 2, 0, 0)
                width = extent.x
            else:
                cam.location = centre + Vector((10, 0, 0))
                cam.rotation_euler = (math.pi / 2, 0, math.pi / 2)
                width = extent.y
            cam_data.clip_end = 100
            cam_data.sensor_fit = 'VERTICAL'
            aspect = min(max(max(width, 1e-3) / max(extent.z, 1e-3), 0.4), 2.0)
            render.resolution_y = size
            render.resolution_x = max(64, int(size * aspect))
            cam_data.ortho_scale = max(extent.z, width / aspect) * 1.08
            scene.camera = cam
            path = os.path.join(out_dir, f"{prefix}{view}.png")
            if os.path.exists(path):
                os.remove(path)
            render.filepath = path
            bpy.ops.render.render(write_still=True)
            out[view] = path
    finally:
        for o in hidden:
            o.hide_render = False
        for obj in added:
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Camera):
                bpy.data.cameras.remove(data)
        render.engine, render.resolution_x, render.resolution_y = saved["engine"], saved["x"], saved["y"]
        render.resolution_percentage, render.filepath = saved["pct"], saved["path"]
        render.image_settings.file_format, scene.camera = saved["fmt"], saved["camera"]
        shading.light, shading.color_type, render.film_transparent = saved["light"], saved["color"], saved["film"]
    return out


def _uv_sphere(mesh, r: float, rings: int = 6, segs: int = 10) -> None:
    verts = [(0, 0, r)]
    for i in range(1, rings):
        t = math.pi * i / rings
        verts += [(r * math.sin(t) * math.cos(2 * math.pi * j / segs), r * math.sin(t) * math.sin(2 * math.pi * j / segs),
                   r * math.cos(t)) for j in range(segs)]
    verts.append((0, 0, -r))
    faces = [(0, 1 + (j + 1) % segs, 1 + j) for j in range(segs)]
    for i in range(rings - 2):
        for j in range(segs):
            a, b = 1 + i * segs + j, 1 + i * segs + (j + 1) % segs
            faces.append((a, b, b + segs, a + segs))
    last = len(verts) - 1
    faces += [(last, 1 + (rings - 2) * segs + j, 1 + (rings - 2) * segs + (j + 1) % segs) for j in range(segs)]
    mesh.from_pydata(verts, [], faces)


def _rod(mesh, a: Vector, b: Vector, r: float, segs: int = 6) -> None:
    axis = (b - a).normalized()
    u = axis.orthogonal().normalized()
    w = axis.cross(u)
    ring = [u * math.cos(2 * math.pi * j / segs) * r + w * math.sin(2 * math.pi * j / segs) * r for j in range(segs)]
    verts = [a + o for o in ring] + [b + o for o in ring]
    faces = [(j, (j + 1) % segs, segs + (j + 1) % segs, segs + j) for j in range(segs)]
    mesh.from_pydata(verts, [], faces)


# --- the procedural runner (selftests) ----------------------------------------

def runner_joints(arm_deg: float = 45.0, height: float = 1.7) -> dict:
    """True joint positions of the procedural runner, .L on +X, metres, for a 1.7 m body."""
    k = height / 1.7
    c, s = math.cos(math.radians(arm_deg)), math.sin(math.radians(arm_deg))
    j = {"pelvis": (0, 0, 0.93), "neck_base": (0, 0, 1.42), "neck": (0, 0.0, 1.47),
         "head_top": (0, 0, 1.70), "shoulder.L": (0.18, 0, 1.39),
         "hip.L": (0.095, 0, 0.88), "knee.L": (0.105, -0.01, 0.48), "ankle.L": (0.11, 0.015, 0.085),
         "ball.L": (0.115, -0.09, 0.03), "toe_tip.L": (0.115, -0.16, 0.03), "heel.L": (0.11, 0.06, 0.02)}
    sh = Vector(j["shoulder.L"])
    d = Vector((c, 0, -s))
    j["elbow.L"] = tuple(sh + d * 0.28)
    j["wrist.L"] = tuple(sh + d * 0.52)
    j["hand_tip.L"] = tuple(sh + d * 0.69)
    out = {}
    for name, p in j.items():
        out[name] = tuple(x * k for x in p)
        if name.endswith(".L"):
            q = out[name]
            out[name[:-2] + ".R"] = (-q[0], q[1], q[2])
    return out


def build_runner(name: str = "Runner", arm_deg: float = 45.0, resolution: float = 0.014,
                 fused_legs: bool = False) -> tuple:
    """A metaball body converted to one mesh object; returns (object, true joints)."""
    j = runner_joints(arm_deg)
    mb = bpy.data.metaballs.new(f"{name}_mb")
    mb.resolution = resolution
    mb.render_resolution = resolution
    mb.threshold = 0.6
    obj = bpy.data.objects.new(f"{name}_mb", mb)
    bpy.context.scene.collection.objects.link(obj)

    def capsule(a, b, r):
        a, b = Vector(a), Vector(b)
        el = mb.elements.new(type='CAPSULE')
        el.co = (a + b) / 2
        el.radius = r
        el.size_x = (b - a).length / 2
        el.rotation = Vector((1, 0, 0)).rotation_difference((b - a).normalized())

    def ellipsoid(c, sx, sy, sz, r=1.0):
        el = mb.elements.new(type='ELLIPSOID')
        el.co = c
        el.radius = r
        el.size_x, el.size_y, el.size_z = sx, sy, sz

    ellipsoid((0, 0, 0.93), 0.17, 0.11, 0.15)            # pelvis
    ellipsoid((0, 0, 1.12), 0.15, 0.10, 0.13)            # belly
    ellipsoid((0, 0, 1.28), 0.18, 0.11, 0.14)            # chest
    capsule((0, 0, 1.38), (0, 0.0, 1.50), 0.05)          # neck
    ellipsoid((0, -0.01, 1.60), 0.12, 0.135, 0.15)       # head
    ellipsoid((0, -0.07, 1.54), 0.05, 0.05, 0.04)        # chin
    for side in (1, -1):
        def m(p):
            return (side * p[0], p[1], p[2])
        L = {k: m(v) for k, v in j.items() if k.endswith(".L")}
        L = {k[:-2]: v for k, v in L.items()}
        if not fused_legs:
            mid_thigh = tuple((Vector(L["hip"]) + Vector(L["knee"])) / 2)
            capsule(L["hip"], mid_thigh, 0.09)
            capsule(mid_thigh, L["knee"], 0.072)
            capsule(L["knee"], L["ankle"], 0.06)
        capsule(L["ankle"], L["ball"], 0.05)
        capsule(L["ball"], L["toe_tip"], 0.045)
        capsule(L["heel"], L["ankle"], 0.045)
        capsule((side * 0.10, 0, 1.36), L["shoulder"], 0.075)
        capsule(L["shoulder"], L["elbow"], 0.06)
        capsule(L["elbow"], L["wrist"], 0.05)
        w, t = Vector(L["wrist"]), Vector(L["hand_tip"])
        d = (t - w).normalized()
        el = mb.elements.new(type='ELLIPSOID')
        el.co = w + d * 0.085
        el.radius = 1.0
        el.size_x, el.size_y, el.size_z = 0.09, 0.05, 0.025
        el.rotation = Vector((1, 0, 0)).rotation_difference(d)
    if fused_legs:
        capsule((0, 0, 0.90), (0, 0, 0.10), 0.18)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    mesh.name = name
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.metaballs.remove(mb)
    body = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(body)
    lowest = min(v.co.z for v in mesh.vertices)
    for v in mesh.vertices:
        v.co.z -= lowest
    shift = lowest
    joints = {k: (p[0], p[1], p[2] - shift) for k, p in j.items()}
    return body, joints


def build_armature(name: str, bones: list[dict], at=None):
    """An armature from [{name, head, tail, parent, deform, roll?}] in world space; returns the object."""
    arm = bpy.data.armatures.new(name)
    rig = bpy.data.objects.new(name, arm)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    for o in bpy.context.view_layer.objects:
        o.select_set(o == rig)
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        made = {}
        for spec in bones:
            eb = arm.edit_bones.new(spec["name"])
            eb.head, eb.tail = spec["head"], spec["tail"]
            if (eb.tail - eb.head).length < 1e-5:
                eb.tail = eb.head + Vector((0, 0, 0.01))
            eb.use_deform = spec.get("deform", True)
            if spec.get("roll_z") is not None:
                eb.align_roll(Vector(spec["roll_z"]))
            made[spec["name"]] = eb
        for spec in bones:
            if spec.get("parent"):
                made[spec["name"]].parent = made[spec["parent"]]
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
    return rig
