"""render_ref.py — render the rest pose from both layout cameras and compose the video model's first frame, ref.png.

Ported from patch-gg/anymove (https://github.com/patch-gg/anymove), blender/render_ref.py and tools/compose_ref.py,
commit 7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0. Changes from upstream: the two renders are
composed here (layout.compose, the grey wall, floor band and divider) instead of in a separate PIL step; the rig and
mesh come from rig_info's twocam.objects; the layout from rig_info.json; the Cycles device is chosen (--device) and
a workbench engine is offered for checks; poses are reset with quaternions too; gates on the framing; --selftest.

usage:
    Blender -b --factory-startup -P render_ref.py -- TWOCAM.blend RIG_INFO.json OUT_DIR [--samples 128]
            [--engine cycles|workbench] [--device auto]
    Blender -b --factory-startup -P render_ref.py -- --selftest
Writes OUT_DIR/ref_front.png, ref_side.png (RGBA) and ref.png (the 1376 x 768 two-camera frame; upload it as the
image-to-video first frame). Keep the layout of this frame for every clip of the character: the reader, the
calibration and the solve all assume it.
Prints one line `TWOCAM_JSON {...}`. Gates: ref.inside_frame (no opaque pixel on a view's left, right or top edge:
the character is not cut off), ref.on_ground (the lowest opaque row is within 3 px of the ground row).
Exit codes: 0 every gate passed (or the selftest passed), 2 a gate failed (the images are still written), 1 an error.
"""
from __future__ import annotations

import os
import sys
import tempfile

if __name__ == "__main__" and globals().get("__file__"):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import bcommon as B  # noqa: E402
from layout import Layout  # noqa: E402


def framing_gates(paths, L: Layout, scale=1.0) -> list:
    inside, ground = [], []
    for view, path in paths.items():
        a = B.read_png_rgba(path)[..., 3] > 32
        inside.append(bool(not a[:, 0].any() and not a[:, -1].any() and not a[0].any()))
        rows = np.where(a.any(1))[0]
        ground.append(float(rows.max() + 1 - L.GROUND_V * scale) if len(rows) else None)
    return [B.gate("ref.inside_frame", inside, "no opaque pixel on the left, right or top edge", all(inside)),
            B.gate("ref.on_ground", ground, "lowest opaque row within 3 px of the ground row",
                   all(g is not None and abs(g) <= 3 for g in ground))]


def render_ref(p: dict) -> tuple:
    if p.get("blend"):
        bpy.ops.wm.open_mainfile(filepath=p["blend"])
    info = B.load_info(p["rig_info"])
    L = Layout.from_rig_info(info)
    rig, body = B.objects_of(info)
    rig.animation_data_clear()
    for pb in rig.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()
    os.makedirs(p["out_dir"], exist_ok=True)
    scene = bpy.context.scene
    dev = B.studio(scene, samples=int(p.get("samples", 128)), engine=p.get("engine", "cycles"), device=p.get("device", "auto"))
    paths = B.render_views(p["out_dir"], "ref", L)
    front, side = B.read_png_rgba(paths["front"]), B.read_png_rgba(paths["side"])
    ref = os.path.join(p["out_dir"], "ref.png")
    B.write_png_rgb(L.compose(front, side), ref)
    gates = framing_gates(paths, L)
    ok = all(g["pass"] for g in gates)
    return B.report("render_ref.py", p, gates, ref=ref, views=paths, device=dev, size=[L.W, L.H]), 0 if ok else 2


def selftest() -> tuple:
    import prepare_rig
    checks = []
    with tempfile.TemporaryDirectory() as td:
        B.demo_scene()
        prepare_rig.prepare({"out_dir": td})
        blend, ri = os.path.join(td, "twocam.blend"), os.path.join(td, "rig_info.json")
        r, code = render_ref({"blend": blend, "rig_info": ri, "out_dir": os.path.join(td, "ref"), "engine": "workbench"})
        checks.append({"name": "rest pose framed and on the ground, exit 0", "pass": code == 0, "gates": r["gates"]})
        img = B.read_png_rgba(r["ref"])
        L = Layout.from_rig_info(B.load_info(ri))
        checks.append({"name": "ref.png is the layout frame", "pass": img.shape[:2] == (L.H, L.W)})
        checks.append({"name": "divider drawn", "pass": tuple(img[5, L.W_FRONT][:3]) == (34, 34, 38)})
        bpy.ops.wm.open_mainfile(filepath=blend)
        bpy.data.objects["rig"].location.z = 0.3
        r, code = render_ref({"rig_info": ri, "out_dir": os.path.join(td, "ref2"), "engine": "workbench"})
        checks.append({"name": "a character in the air fails ref.on_ground, exit 2",
                       "pass": code == 2 and not r["gates"][1]["pass"]})
        bpy.ops.wm.open_mainfile(filepath=blend)
        bpy.data.objects["rig"].scale = (2.2, 2.2, 2.2)
        r, code = render_ref({"rig_info": ri, "out_dir": os.path.join(td, "ref3"), "engine": "workbench"})
        checks.append({"name": "a character too big for the frame fails ref.inside_frame, exit 2",
                       "pass": code == 2 and not r["gates"][0]["pass"]})
    ok = all(c["pass"] for c in checks)
    return {"tool": "render_ref.py", "selftest": "pass" if ok else "fail", "checks": len(checks),
            "failed": [c for c in checks if not c["pass"]]}, 0 if ok else 1


def main():
    args = B.script_args()
    if "--selftest" in args or args[:1] == ["selftest"]:
        return selftest()
    if len(args) < 3:
        raise ValueError("usage: -- TWOCAM.blend RIG_INFO.json OUT_DIR [--samples N] [--engine E] [--device D]")
    p = {"blend": args[0], "rig_info": args[1], "out_dir": args[2]}
    for k in ("samples", "engine", "device"):
        if f"--{k}" in args:
            p[k] = args[args.index(f"--{k}") + 1]
    return render_ref(p)


if __name__ == "__main__":
    B.guarded(main)
