"""apply_motion.py — put a solved (or made-up) motion on the rig: keyframes, true joint positions, renders, a GLB.

Ported from patch-gg/anymove (https://github.com/patch-gg/anymove), blender/apply_motion.py, commit
7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0. The keying (root quaternion and location in the root
bone's rest frame, Euler or quaternion per bone, linear interpolation), the joints.json read back from Blender, the
views, the 3/4 camera with its shadow catcher and the GLB export are upstream's. Changes from upstream: bones of a
rig with limit frames are keyed from motion.json's local_quat (quaternions), upstream rigs from euler; the
armature and mesh come from rig_info's twocam.objects (or --rig / --body); the limb paint attribute is limbpaint;
the layout comes from rig_info.json; the Cycles device is chosen (--device, default auto) instead of forced CUDA;
the fur springs (--springs) were not ported; one TWOCAM_JSON line with gates; --selftest. A motion's frame count
must match its bones' (gate).

usage:
    Blender -b --factory-startup -P apply_motion.py -- TWOCAM.blend RIG_INFO.json MOTION.json OUT_DIR [options]
      --views front,side,persp   which cameras to render (default none)
      --engine cycles|workbench|ghost  (default cycles)  --samples 32  --device auto|cpu|cuda|optix|metal|hip
      --paint                    keep the limb paint (the exam needs it; a showcase does not)
      --blur                     motion blur from the keyframes, like a video model's fast limbs
      --glb                      export OUT_DIR/animation.glb
      --frames 10,40,80          render only these frames (stills)
      --scale 0.75               render at this fraction of the layout size
      --cam x,y,z --target x,y,z --lens mm --res WxH   the persp camera
      --save OUT.blend           keep the keyed file
    Blender -b --factory-startup -P apply_motion.py -- --selftest
Always writes OUT_DIR/joints.json, every joint's world position per frame from Blender itself, and for every
rendered view OUT_DIR/cam_<view>.json, its pixel projection.
Prints one line `TWOCAM_JSON {...}`. Gates: motion.bones_match (every motion bone is on the rig),
motion.frames_consistent (trans, root_quat and the rotations have one row per frame).
Exit codes: 0 every gate passed (or the selftest passed), 2 a gate failed, 1 an error.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

if __name__ == "__main__" and globals().get("__file__"):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Quaternion, Vector  # noqa: E402

import bcommon as B  # noqa: E402
from layout import Layout  # noqa: E402


def key_motion(rig, info, motion) -> dict:
    scene = bpy.context.scene
    names = motion["bones"]
    T = len(motion["trans"])
    fps = motion.get("fps", 24)
    scene.render.fps = round(fps)
    scene.render.fps_base = round(fps) / fps
    scene.frame_start, scene.frame_end = 0, T - 1
    root = names[0]
    Bm = rig.data.bones[root].matrix_local.to_3x3()
    local = motion.get("local_quat")
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION" if local is not None else "XYZ"
    rig.pose.bones[root].rotation_mode = "QUATERNION"
    for t in range(T):
        pr = rig.pose.bones[root]
        pr.rotation_quaternion = Quaternion(motion["root_quat"][t])
        pr.location = Bm.transposed() @ Vector(motion["trans"][t])
        pr.keyframe_insert("rotation_quaternion", frame=t)
        pr.keyframe_insert("location", frame=t)
        for i, n in enumerate(names[1:], 1):
            pb = rig.pose.bones[n]
            if local is not None:
                pb.rotation_quaternion = Quaternion(local[t][i])
                pb.keyframe_insert("rotation_quaternion", frame=t)
            else:
                pb.rotation_euler = motion["euler"][t][i]
                pb.keyframe_insert("rotation_euler", frame=t)
    act = rig.animation_data.action
    fcurves = []
    if hasattr(act, "fcurves"):
        fcurves = list(act.fcurves)
    else:   # Blender 5 layered actions
        for layer in act.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    fcurves += list(bag.fcurves)
    for fc in fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
    joints = []
    for t in range(T):
        scene.frame_set(t)
        joints.append(B.joints_world(rig, info).tolist())
    return {"names": [k["name"] for k in info["keypoints"]], "joints": joints, "fps": fps}


def render(p, scene, rig, body, L, out):
    opt = p.get
    views = [v for v in (opt("views") or "").split(",") if v]
    if not views:
        return []
    engine = opt("engine") or "cycles"
    if engine == "ghost":
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "FLAT"
        scene.display.shading.color_type = "SINGLE"
        scene.display.shading.single_color = (0.55, 0.56, 0.6)
        scene.display.shading.show_xray = True
        scene.display.shading.xray_alpha = 0.18
        scene.render.film_transparent = True
    else:
        B.studio(scene, samples=int(opt("samples") or 32), engine=engine, device=opt("device") or "auto")
    scene.render.use_motion_blur = bool(opt("blur"))
    scene.render.motion_blur_shutter = 0.5
    cams = B.cameras(scene, L)
    if "persp" in views:
        cam = bpy.data.objects.new("cam_persp", bpy.data.cameras.new("cam_persp"))
        scene.collection.objects.link(cam)
        cam.data.lens = float(opt("lens") or 50)
        vec = lambda s: Vector([float(x) for x in s.split(",")])
        target = vec(opt("target") or "0,0,0.9")
        cam.location = vec(opt("cam") or "-3.2,-3.0,1.6")
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.clip_end = 200
        pw, ph = (int(x) for x in (opt("res") or "1280x720").split("x"))
        cams["cam_persp"] = (cam, (pw, ph))
    floor = None
    if "persp" in views and engine == "cycles":   # a shadow catcher, so the character stands on the ground
        bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0))
        floor = bpy.context.object
        floor.is_shadow_catcher = True
    done = []
    for v in views:
        cam, w = cams[f"cam_{v}"]
        scene.camera = cam
        if floor is not None:
            floor.hide_render = v != "persp"
        k = float(opt("scale") or 1.0)
        w, hgt = w if isinstance(w, tuple) else (w, L.H)
        scene.render.resolution_x = round(w * k)
        scene.render.resolution_y = round(hgt * k)
        with open(out / f"cam_{v}.json", "w") as f:
            json.dump(B.camera_json(cam, scene.render.resolution_x, scene.render.resolution_y), f)
        d = out / v
        d.mkdir(exist_ok=True)
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        if opt("frames"):
            for fr in [int(x) for x in opt("frames").split(",")]:
                scene.frame_set(fr)
                scene.render.filepath = str(d / f"f_{fr:04d}.png")
                bpy.ops.render.render(write_still=True)
        else:
            scene.render.filepath = str(d / "f_")
            bpy.ops.render.render(animation=True)
        done.append(v)
    return done


def apply(p: dict) -> tuple:
    if p.get("blend"):
        bpy.ops.wm.open_mainfile(filepath=p["blend"])
    scene = bpy.context.scene
    info = B.load_info(p["rig_info"])
    with open(p["motion"], encoding="utf-8") as f:
        motion = json.load(f)
    L = Layout.from_rig_info(info)
    rig, body = B.objects_of(info, p.get("rig"), p.get("body"))
    out = pathlib.Path(p["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    missing = [n for n in motion["bones"] if n not in rig.pose.bones]
    T = len(motion["trans"])
    rot = motion.get("local_quat") or motion["euler"]
    rows = {len(motion["root_quat"]), len(rot), T}
    gates = [B.gate("motion.bones_match", missing, "every motion bone on the rig", not missing),
             B.gate("motion.frames_consistent", sorted(rows), "one count", len(rows) == 1)]
    if not all(g["pass"] for g in gates):
        return B.report("apply_motion.py", p, gates), 2
    if not p.get("paint"):
        B.clear_paint(body)
    rig.animation_data_clear()
    joints = key_motion(rig, info, motion)
    with open(out / "joints.json", "w") as f:
        json.dump(joints, f)
    views = render(p, scene, rig, body, L, out)
    extra = {"frames": T, "joints_json": str(out / "joints.json"), "views": views}
    if p.get("glb"):
        bpy.ops.object.select_all(action="DESELECT")
        rig.select_set(True)
        body.select_set(True)
        bpy.ops.export_scene.gltf(filepath=str(out / "animation.glb"), use_selection=True, export_animations=True,
                                  export_force_sampling=True, export_frame_range=True)
        extra["glb"] = str(out / "animation.glb")
    if p.get("save"):
        bpy.ops.wm.save_as_mainfile(filepath=p["save"], copy=True)
        extra["saved"] = p["save"]
    return B.report("apply_motion.py", p, gates, **extra), 0


def selftest() -> tuple:
    import exam
    import prepare_rig
    checks = []
    with tempfile.TemporaryDirectory() as td:
        B.demo_scene()
        r, code = prepare_rig.prepare({"out_dir": td})
        info = B.load_info(os.path.join(td, "rig_info.json"))
        m = exam.make_motion(info, seed=5, T=20, fps=24)
        with open(os.path.join(td, "m.json"), "w") as f:
            json.dump(m, f)
        r, code = apply({"blend": os.path.join(td, "twocam.blend"), "rig_info": os.path.join(td, "rig_info.json"),
                         "motion": os.path.join(td, "m.json"), "out_dir": os.path.join(td, "o"), "glb": True})
        checks.append({"name": "keyed, exit 0", "pass": code == 0})
        J = np.array(B.load_info(os.path.join(td, "o", "joints.json"))["joints"])
        err = float(np.abs(J - exam.fk_joints(info, m)).max())
        checks.append({"name": "Blender's joints = the solve's forward kinematics (< 0.1 mm)", "pass": err < 1e-4,
                       "max_err_m": err})
        checks.append({"name": "GLB written", "pass": os.path.exists(os.path.join(td, "o", "animation.glb"))})
        m2 = dict(m, bones=m["bones"] + ["Tail1"])
        with open(os.path.join(td, "m2.json"), "w") as f:
            json.dump(m2, f)
        r, code = apply({"blend": os.path.join(td, "twocam.blend"), "rig_info": os.path.join(td, "rig_info.json"),
                         "motion": os.path.join(td, "m2.json"), "out_dir": os.path.join(td, "o2")})
        checks.append({"name": "a bone not on the rig fails motion.bones_match, exit 2", "pass": code == 2})
        m3 = dict(m, trans=m["trans"][:-1])
        with open(os.path.join(td, "m3.json"), "w") as f:
            json.dump(m3, f)
        r, code = apply({"blend": os.path.join(td, "twocam.blend"), "rig_info": os.path.join(td, "rig_info.json"),
                         "motion": os.path.join(td, "m3.json"), "out_dir": os.path.join(td, "o3")})
        checks.append({"name": "a short trans fails motion.frames_consistent, exit 2", "pass": code == 2})
    ok = all(c["pass"] for c in checks)
    return {"tool": "apply_motion.py", "selftest": "pass" if ok else "fail", "checks": len(checks),
            "failed": [c for c in checks if not c["pass"]],
            "fk_max_err_m": next(c.get("max_err_m") for c in checks if "max_err_m" in c)}, 0 if ok else 1


def main():
    args = B.script_args()
    if "--selftest" in args or args[:1] == ["selftest"]:
        return selftest()
    if len(args) < 4:
        raise ValueError("usage: -- TWOCAM.blend RIG_INFO.json MOTION.json OUT_DIR [options]")
    p = {"blend": args[0], "rig_info": args[1], "motion": args[2], "out_dir": args[3]}
    opts = args[4:]
    for flag in ("paint", "blur", "glb"):
        p[flag] = f"--{flag}" in opts
    if "--ghost" in opts:
        p["engine"] = "ghost"
    for k in ("views", "engine", "samples", "device", "frames", "scale", "cam", "target", "lens", "res", "save", "rig", "body"):
        if f"--{k}" in opts:
            p[k] = opts[opts.index(f"--{k}") + 1]
    return apply(p)


if __name__ == "__main__":
    B.guarded(main)
