"""render_baked.py — render a baked clip from the layout's front and side cameras, and encode it beside the take.

Not in upstream (anymove renders its showcase differently). Opens nothing itself: Blender opens the baked .blend
(`twocam.py bake --render` passes clips/NAME/baked.blend), and every frame of the scene's range is rendered from
bcommon.cameras (the layout's two orthographic cameras) under bcommon.studio, on the studio grey instead of a
transparent film, so the clip reads like the H3 take it came from. With ffmpeg on the PATH the two views are encoded
side by side, front | side, the take's own layout.

usage:
    Blender -b --factory-startup BAKED.blend -P render_baked.py -- RIG_INFO.json OUT_DIR [--samples 32]
            [--engine cycles|eevee|workbench] [--device auto]
    Blender -b --factory-startup -P render_baked.py -- --selftest
Writes OUT_DIR/front/f_####.png and OUT_DIR/side/f_####.png (frames earlier runs left there are removed first) and,
when ffmpeg is found, OUT_DIR.mp4 (H.264, yuv420p, the scene's frame rate). Prints one line `TWOCAM_JSON {...}`.
Gates: render.frames (every frame of the range written in both views), render.mp4 (only when ffmpeg is found: it
exited 0 and wrote the file).
Exit codes: 0 every gate passed (or the selftest passed), 2 a gate failed, 1 an error.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

if __name__ == "__main__" and globals().get("__file__"):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

import bcommon as B  # noqa: E402
from layout import Layout  # noqa: E402


def encode(out_dir, start, fps, ffmpeg) -> dict:
    """front | side into OUT_DIR.mp4; returns {"mp4", "returncode", "error"}."""
    mp4 = out_dir.rstrip("/\\") + ".mp4"
    src = []
    for v in ("front", "side"):
        src += ["-framerate", f"{fps:g}", "-start_number", str(start), "-i", os.path.join(out_dir, v, "f_%04d.png")]
    cmd = [ffmpeg, "-y", "-v", "error", *src, "-filter_complex",
           "[0:v][1:v]hstack=inputs=2,pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "18", mp4]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return {"mp4": mp4, "returncode": r.returncode, "error": r.stderr.strip()[-400:] or None}


def render(p: dict) -> tuple:
    scene = bpy.context.scene
    L = Layout.from_rig_info(B.load_info(p["rig_info"]))
    dev = B.studio(scene, samples=int(p.get("samples") or 32), engine=p.get("engine") or "cycles",
                   device=p.get("device") or "auto", persistent=True)
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"
    scene.render.resolution_percentage = 100
    start, end = scene.frame_start, scene.frame_end
    fps = scene.render.fps / scene.render.fps_base
    out = p["out_dir"]
    written = {}
    for v, (cam, w) in ((n.split("_")[1], c) for n, c in B.cameras(scene, L).items()):
        d = os.path.join(out, v)
        os.makedirs(d, exist_ok=True)
        for old in glob.glob(os.path.join(d, "f_*.png")):
            os.remove(old)
        scene.camera = cam
        scene.render.resolution_x, scene.render.resolution_y = w, L.H
        scene.render.filepath = os.path.join(d, "f_####")
        bpy.ops.render.render(animation=True)
        written[v] = len(glob.glob(os.path.join(d, "f_*.png")))
    n = end - start + 1
    gates = [B.gate("render.frames", written, n, all(k == n for k in written.values()))]
    extra = {"device": dev, "frames": [start, end], "fps": round(fps, 4), "out_dir": out, "mp4": None}
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        extra["ffmpeg"] = "not found: PNG frames only"
    elif gates[0]["pass"]:
        enc = encode(out, start, fps, ffmpeg)
        ok = enc["returncode"] == 0 and os.path.isfile(enc["mp4"])
        gates.append(B.gate("render.mp4", enc["returncode"], 0, ok))
        extra.update(mp4=enc["mp4"] if ok else None, ffmpeg_error=None if ok else enc["error"])
    ok = all(g["pass"] for g in gates)
    return B.report("render_baked.py", p, gates, **extra), 0 if ok else 2


def selftest() -> tuple:
    import apply_motion
    import exam
    import prepare_rig
    checks = []
    with tempfile.TemporaryDirectory() as td:
        B.demo_scene()
        prepare_rig.prepare({"out_dir": td})
        ri = os.path.join(td, "rig_info.json")
        with open(os.path.join(td, "m.json"), "w") as f:
            json.dump(exam.make_motion(B.load_info(ri), seed=5, T=4, fps=24), f)
        keyed = os.path.join(td, "keyed.blend")
        apply_motion.apply({"blend": os.path.join(td, "twocam.blend"), "rig_info": ri, "motion": os.path.join(td, "m.json"),
                            "out_dir": os.path.join(td, "o"), "save": keyed})
        bpy.ops.wm.open_mainfile(filepath=keyed)
        out = os.path.join(td, "baked")
        os.makedirs(os.path.join(out, "front"))
        open(os.path.join(out, "front", "f_0099.png"), "w").close()   # an older, longer run's frame
        r, code = render({"rig_info": ri, "out_dir": out, "engine": "workbench"})
        checks.append({"name": "four frames in each view, the older frame gone, exit 0",
                       "pass": code == 0 and r["gates"][0]["value"] == {"front": 4, "side": 4}, "gates": r["gates"]})
        L = Layout.from_rig_info(B.load_info(ri))
        a = B.read_png_rgba(os.path.join(out, "side", "f_0002.png"))
        checks.append({"name": "frames at the layout size, opaque (the studio grey, not a transparent film)",
                       "pass": a.shape[:2] == (L.H, L.W_SIDE) and int(a[..., 3].min()) == 255})
        checks.append({"name": "with ffmpeg on the PATH an mp4, without it the frames alone",
                       "pass": (r["mp4"] is not None and os.path.getsize(r["mp4"]) > 0) if shutil.which("ffmpeg")
                       else (r["mp4"] is None and "ffmpeg" in r)})
    ok = all(c["pass"] for c in checks)
    return {"tool": "render_baked.py", "selftest": "pass" if ok else "fail", "checks": len(checks),
            "failed": [c for c in checks if not c["pass"]]}, 0 if ok else 1


def main():
    args = B.script_args()
    if "--selftest" in args or args[:1] == ["selftest"]:
        return selftest()
    if len(args) < 2:
        raise ValueError("usage: Blender -b BAKED.blend -P render_baked.py -- RIG_INFO.json OUT_DIR [options]")
    p = {"rig_info": args[0], "out_dir": os.path.abspath(args[1])}
    for k in ("samples", "engine", "device"):
        if f"--{k}" in args:
            p[k] = args[args.index(f"--{k}") + 1]
    return render(p)


if __name__ == "__main__":
    B.guarded(main)
