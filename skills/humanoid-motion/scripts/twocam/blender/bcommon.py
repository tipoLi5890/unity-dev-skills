"""bcommon.py — Blender helpers shared by the two-camera scripts: cameras, studio, limb paint, renders, reports.

Ported from patch-gg/anymove (https://github.com/patch-gg/anymove), blender/common.py, commit
7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0. Changes from upstream: the layout is the `Layout`
of ../layout.py read from rig_info.json (no MOCAP_CREATURE, no constants mirrored here); the rig file and
write_rig_info moved to ../skeleton.py (the humanoid contract) and prepare_rig.py; paint_legs became paint_limbs,
its groups and colours from rig_info's twocam.paint, its material hook tolerant of meshes without a node tree;
studio() takes the Cycles device (auto picks the first GPU backend Blender reports, else the CPU) instead of
forcing CUDA, and an engine (cycles, eevee, or workbench, the fast one for checks), and keeps render data between
renders when asked (persistent); stick_figure and xray_views were not
ported; new: pose helpers that turn a bone's Euler angles in its limit frame into the pose quaternion, the
report/emit pair every script prints (one TWOCAM_JSON line, exit 0 / 2 / 1), and demo_scene(), a contract
armature with a stick body that the selftests build in memory.

Runs inside Blender only (bpy, mathutils, numpy).
"""
from __future__ import annotations

import json
import math
import os
import sys
import traceback

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))   # ../layout.py, ../skeleton.py
from layout import Layout  # noqa: E402

SKILL = "humanoid-motion"


# --- arguments, reports ---------------------------------------------------------------------------------------
def script_args() -> list:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def gate(name, value, limit, passed) -> dict:
    return {"name": name, "value": value, "limit": limit, "pass": bool(passed)}


def report(script: str, params: dict, gates: list, **extra) -> dict:
    ok = all(g["pass"] for g in gates)
    out = {"tool": script, "ok": ok, "gates": gates, "blender": list(bpy.app.version)}
    out.update(extra)
    out["record"] = {"tool": {"skill": SKILL, "script": f"twocam/blender/{script}"},
                     "params": {k: v for k, v in params.items() if "path" not in k and not str(k).endswith(("blend", "dir"))},
                     "gates": gates, "verdict": "green" if ok else "failed"}
    return out


def emit(result: dict, code: int) -> int:
    result["exit_code"] = code
    print("TWOCAM_JSON " + json.dumps(result, default=str), flush=True)
    return code


def guarded(main_fn):
    """Run main_fn() -> (result, code); an exception becomes exit 1 (Blender itself exits 0 on a raised script)."""
    try:
        result, code = main_fn()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - every failure must reach the exit code
        result, code = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-1500:]}, 1
    sys.exit(emit(result, code))


# --- rig_info and poses ---------------------------------------------------------------------------------------
def load_info(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def objects_of(info: dict, rig_name=None, body_name=None):
    tc = info.get("twocam") or {}
    objs = tc.get("objects") or {}
    rig = bpy.data.objects.get(rig_name or objs.get("rig", "rig"))
    body = bpy.data.objects.get(body_name or objs.get("body", "body"))
    if rig is None or rig.type != "ARMATURE":
        raise ValueError(f"no armature object '{rig_name or objs.get('rig', 'rig')}' in the file")
    if body is None or body.type != "MESH":
        raise ValueError(f"no mesh object '{body_name or objs.get('body', 'body')}' in the file")
    return rig, body


def euler_xyz(e) -> np.ndarray:
    x, y, z = e
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def pose_quaternion(bone_info: dict, e) -> Quaternion:
    """The pose rotation of a bone for Euler angles read in its limit frame (local Euler when it has none)."""
    R = euler_xyz(e)
    if "limit_frame" in bone_info:
        C = np.asarray(bone_info["limit_frame"], float)
        R = C @ R @ C.T
    return Matrix([list(r) for r in R]).to_quaternion()


def joints_world(rig, info) -> np.ndarray:
    mw = rig.matrix_world
    pts = []
    for kp in info["keypoints"]:
        pb = rig.pose.bones[info["bones"][kp["bone"]]["name"]]
        pts.append(list(mw @ (pb.head if kp["end"] == "head" else pb.tail)))
    return np.array(pts)


# --- cameras, studio, renders ---------------------------------------------------------------------------------
def cameras(scene, L: Layout):
    """The front and side orthographic cameras of the layout (created once, reused)."""
    cams = {}
    for name, loc, rot, w in (("cam_front", (0, -20, L.Z_CENTER), (math.pi / 2, 0, 0), L.W_FRONT),
                              ("cam_side", (-20, 0, L.Z_CENTER), (math.pi / 2, 0, -math.pi / 2), L.W_SIDE)):
        cam = bpy.data.objects.get(name)
        if cam is None:
            cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
            scene.collection.objects.link(cam)
        cam.location, cam.rotation_euler = loc, rot
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = L.M_PER_PX * max(w, L.H)
        cam.data.clip_end = 100
        cams[name] = (cam, w)
    return cams


def camera_json(cam, w, h):
    """The camera's pixel projection, so 2D drawings can be laid exactly over its renders:
    pc = R @ p + t; perspective u = cx + f * pc.x / -pc.z, v = cy - f * pc.y / -pc.z; ortho u = cx + f * pc.x."""
    bpy.context.view_layer.update()   # a camera placed from Python has a stale matrix_world until the next update
    mw = cam.matrix_world.normalized()
    R = mw.to_3x3().transposed()
    t = -(R @ mw.translation)
    if cam.data.type == "ORTHO":
        f = max(w, h) / cam.data.ortho_scale
    else:
        f = cam.data.lens / cam.data.sensor_width * max(w, h)
    return {"type": cam.data.type, "f": f, "cx": w / 2, "cy": h / 2, "res": [w, h],
            "R": [list(r) for r in R], "t": list(t), "location": list(cam.location)}


def cycles_device(scene, device="auto") -> str:
    """Cycles on the named backend (auto: OPTIX, CUDA, HIP, METAL, ONEAPI in that order, else the CPU)."""
    scene.render.engine = "CYCLES"
    if device == "cpu":
        scene.cycles.device = "CPU"
        return "CPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    order = ["OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"] if device == "auto" else [device.upper()]
    for backend in order:
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.get_devices()
        devs = [d for d in prefs.devices if d.type == backend]
        if devs:
            for d in prefs.devices:
                d.use = d.type == backend
            scene.cycles.device = "GPU"
            return backend
    scene.cycles.device = "CPU"
    return "CPU"


def eevee_engine() -> str:
    """This Blender's EEVEE engine identifier (BLENDER_EEVEE_NEXT in 4.2-4.x, BLENDER_EEVEE before and since)."""
    items = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    for name in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if name in items:
            return name
    raise ValueError(f"no EEVEE engine in this Blender (engines: {sorted(items)})")


def studio(scene, samples=32, engine="cycles", device="auto", persistent=False):
    """Transparent film, Standard view transform (keeps the limb paint saturated), three suns. Returns the device.
    engine: cycles (device auto|cpu|optix|cuda|hip|metal|oneapi), eevee or workbench. persistent keeps the scene's
    render data (Cycles' BVH, EEVEE's shaders) between renders, so a second camera or the next pose only updates
    what changed."""
    used = "WORKBENCH"
    if engine == "cycles":
        used = cycles_device(scene, device)
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.max_bounces = 4
    elif engine == "eevee":
        scene.render.engine = eevee_engine()
        scene.eevee.taa_render_samples = samples
        used = "EEVEE"
    elif engine == "workbench":
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "VERTEX"
    else:
        raise ValueError(f"engine {engine!r}: cycles, eevee or workbench")
    scene.render.use_persistent_data = bool(persistent)
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    world = scene.world or bpy.data.worlds.new("world")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background") or world.node_tree.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (0.5, 0.5, 0.5, 1)
    bg.inputs["Strength"].default_value = 0.55
    for name, rot, energy in (("key", (math.radians(50), 0, math.radians(-35)), 3.2),
                              ("fill", (math.radians(60), 0, math.radians(120)), 1.0),
                              ("rim", (math.radians(35), 0, math.radians(200)), 1.6)):
        ob = bpy.data.objects.get(name)
        if ob is None:
            ob = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
            scene.collection.objects.link(ob)
        ob.rotation_euler = rot
        ob.data.energy = energy
        ob.data.angle = math.radians(8)
    return used


def render_views(out, prefix, L: Layout, scale=1.0):
    """Render the front and side views as RGBA PNGs at the layout's pixel scale times `scale`."""
    scene = bpy.context.scene
    paths = {}
    for name, (cam, w) in cameras(scene, L).items():
        scene.camera = cam
        scene.render.resolution_x = round(w * scale)
        scene.render.resolution_y = round(L.H * scale)
        scene.render.resolution_percentage = 100
        view = name.split("_")[1]
        scene.render.filepath = os.path.join(str(out), f"{prefix}_{view}.png")
        bpy.ops.render.render(write_still=True)
        paths[view] = scene.render.filepath
    return paths


def read_png_rgba(path) -> np.ndarray:
    """A PNG as an H x W x 4 uint8 array, top row first."""
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return (px.reshape(h, w, 4)[::-1] * 255 + 0.5).clip(0, 255).astype(np.uint8)


def write_png_rgb(arr, path):
    h, w = arr.shape[:2]
    img = bpy.data.images.new("twocam_out", w, h, alpha=True)
    rgba = np.concatenate([arr[..., :3], np.full((h, w, 1), 255, np.uint8)], -1)[::-1].astype(np.float32) / 255
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


# --- limb paint -----------------------------------------------------------------------------------------------
def srgb_to_linear(hexcol):
    c = np.array([int(hexcol[i:i + 2], 16) / 255 for i in (1, 3, 5)])
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def paint_limbs(body, paint: dict, threshold=0.55) -> dict:
    """Colour each limb from the upper arm or thigh down to the hand or toes, as a color attribute (limbpaint)
    mixed over the material's base colour. Returns the painted vertex count per limb."""
    n = len(body.data.vertices)
    w = {limb: np.zeros(n) for limb in paint}
    for v in body.data.vertices:
        for g in v.groups:
            gname = body.vertex_groups[g.group].name
            for limb, spec in paint.items():
                if gname in spec["bones"]:
                    w[limb][v.index] += g.weight
    rgba = np.zeros((n, 4))
    for limb, spec in paint.items():
        m = w[limb] > threshold
        rgba[m, :3] = srgb_to_linear(spec["color"])
        rgba[m, 3] = 1.0
    attr = body.data.color_attributes.get("limbpaint") or body.data.color_attributes.new("limbpaint", "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", rgba.ravel())
    body.data.color_attributes.active_color = attr
    if not body.material_slots:
        mat = bpy.data.materials.new("twocam_body")
        mat.use_nodes = True
        body.data.materials.append(mat)
    for slot in body.material_slots:
        mat = slot.material
        if mat is None:
            continue
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = next((nd for nd in nt.nodes if nd.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None or any(nd.type == "VERTEX_COLOR" and nd.layer_name == "limbpaint" for nd in nt.nodes):
            continue
        src = bsdf.inputs["Base Color"].links[0].from_socket if bsdf.inputs["Base Color"].links else None
        ca = nt.nodes.new("ShaderNodeVertexColor")
        ca.layer_name = "limbpaint"
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        nt.links.new(ca.outputs["Alpha"], mix.inputs["Factor"])
        if src is not None:
            nt.links.new(src, mix.inputs["A"])
        else:
            mix.inputs["A"].default_value = bsdf.inputs["Base Color"].default_value
        nt.links.new(ca.outputs["Color"], mix.inputs["B"])
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    return {limb: int((w[limb] > threshold).sum()) for limb in w}


def clear_paint(body):
    attr = body.data.color_attributes.get("limbpaint")
    if attr is not None:
        attr.data.foreach_set("color", np.zeros(len(attr.data) * 4))


# --- a scene for the selftests --------------------------------------------------------------------------------
def demo_scene(height=1.7, radius=0.035):
    """Factory-empty scene with the contract's body bones (skeleton.demo_skeleton) as armature 'rig' and a body
    of one capsule per bone, each weighted 1 to its bone, as mesh 'body'. Returns (rig, body)."""
    import bmesh
    from skeleton import demo_skeleton
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sk = demo_skeleton(height)
    arm = bpy.data.objects.new("rig", bpy.data.armatures.new("rig"))
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = {}
    for b in sk["bones"]:
        e = arm.data.edit_bones.new(b["name"])
        e.head, e.tail, e.roll = Vector(b["head"]), Vector(b["tail"]), 0.0
        eb[b["name"]] = e
    for b in sk["bones"]:
        if b["parent"]:
            eb[b["name"]].parent = eb[b["parent"]]
            eb[b["name"]].use_connect = (eb[b["parent"]].tail - eb[b["name"]].head).length < 1e-6
    eb["Root"].use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    me = bpy.data.meshes.new("body")
    bm = bmesh.new()
    groups = []
    for b in sk["bones"]:
        if b["name"] == "Root":
            continue
        h, t = Vector(b["head"]), Vector(b["tail"])
        L = (t - h).length
        r = radius * (1.6 if b["name"] in ("Hips", "Spine", "Chest", "UpperChest") else 1.3 if b["name"] == "Head" else 1)
        if b["name"].startswith(("Foot", "Toes")):
            r = 0.016 * height / 1.7   # the sole on the ground at rest
        mat = Matrix.Translation((h + t) / 2) @ (t - h).to_track_quat("Z", "Y").to_matrix().to_4x4()
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=r, radius2=r, depth=max(L, 0.02), matrix=mat)
        groups.append((b["name"], res["verts"]))
    bm.verts.index_update()
    idx = [(name, [v.index for v in verts]) for name, verts in groups]
    bm.to_mesh(me)
    bm.free()
    body = bpy.data.objects.new("body", me)
    bpy.context.scene.collection.objects.link(body)
    for name, vids in idx:
        vg = body.vertex_groups.new(name=name)
        vg.add(vids, 1.0, "REPLACE")
    body.parent = arm
    mod = body.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    mat = bpy.data.materials.new("skin")
    mat.use_nodes = True
    me.materials.append(mat)
    return arm, body
