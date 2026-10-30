"""render_dataset.py — render the character in random poses from both layout cameras, with every joint's true pixel.

Ported from patch-gg/anymove (https://github.com/patch-gg/anymove), blender/render_dataset.py, commit
7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0. The sampling (half the poses uniform inside the
limits, half a narrower spread around rest; random turn, position and airtime; motion blur on about half the
samples from a random velocity keyed over three frames; random lights and world), the ground placement from the
evaluated mesh and the meta file are upstream's. Changes from upstream: angles are drawn in each bone's limit frame
and keyed as quaternions; the occasional large root pitch (upstream's rear-up) is a forward lean or a back arch of
the upright Hips; the fast limbs that get the wider blur are named from the contract (arms, legs, hands, feet);
the rig and mesh come from rig_info's twocam.objects and the layout from rig_info.json; a pose whose joints leave a
view is drawn again (up to 5 times) and counted; the Cycles device is chosen and eevee and workbench engines are
offered; each sample draws from its own generator (seed, index), so a sample is the same whichever process renders
it; render data persists between renders (the front and side of a sample, and the next sample, reuse the scene);
fewer samples (8) with the denoiser on the GPU; PNGs written uncompressed by default; one TWOCAM_JSON line with gates;
--selftest.

usage:
    Blender -b --factory-startup -P render_dataset.py -- TWOCAM.blend RIG_INFO.json OUT_DIR START COUNT SEED
            [--scale 0.6] [--samples 8] [--engine cycles|eevee|workbench] [--device auto] [--threads 4]
            [--png-compression 0]
    Blender -b --factory-startup -P render_dataset.py -- --selftest
Each sample i writes OUT_DIR/{i:05d}_front.png, _side.png (RGBA) and _meta.json (joints in metres and in full-size
layout pixels for both views, the scale, blur, turn, root and pose). A sample whose meta exists is skipped, so
several Blender processes can split one range and a stopped run resumes. Rendering 2,200 samples is the usual set
for one character: run it on a machine with a GPU Blender can render on, a few processes side by side
(`twocam.py dataset` starts them). Cycles is the default: in a comparison EEVEE rendered the set more slowly and its
reader read the same clips no better (detect confidence, reprojection); workbench is for the selftests. At
--png-compression 0 a sample takes about 1.5 MB on disk; a higher level trades render time for disk.
Prints one line `TWOCAM_JSON {...}`. Gates: dataset.in_view (at least 95 % of the samples were drawn with every
joint inside both views within 5 tries), dataset.written (every sample of the range has its three files).
Exit codes: 0 every gate passed (or the selftest passed), 2 a gate failed, 1 an error.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sys
import tempfile

if __name__ == "__main__" and globals().get("__file__"):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

import bcommon as B  # noqa: E402
from layout import Layout  # noqa: E402
from skeleton import stem  # noqa: E402

FAST = ("UpperArm", "LowerArm", "Hand", "UpperLeg", "LowerLeg", "Foot", "Toes")


def render_dataset(p: dict) -> tuple:
    if p.get("blend"):
        bpy.ops.wm.open_mainfile(filepath=p["blend"])
    scene = bpy.context.scene
    info = B.load_info(p["rig_info"])
    L = Layout.from_rig_info(info)
    rig, body = B.objects_of(info)
    out = pathlib.Path(p["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    start, count, seed = int(p["start"]), int(p["count"]), int(p["seed"])
    scale = float(p.get("scale", 0.6))
    bones = [b["name"] for b in info["bones"]]
    binfo = {b["name"]: b for b in info["bones"]}
    contract = {b["name"]: b.get("contract", b["name"]) for b in info["bones"]}
    lim = {b["name"]: np.radians(np.array(b["limits_deg"], float)) for b in info["bones"]}
    root = bones[0]
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
    dev = B.studio(scene, samples=int(p.get("samples", 8)), engine=p.get("engine", "cycles"), device=p.get("device", "auto"),
                   persistent=True)
    scene.render.image_settings.compression = int(p.get("png_compression", 0))
    if scene.render.engine == "CYCLES":
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.denoising_use_gpu = dev != "CPU"
        scene.render.threads_mode = "FIXED"
        scene.render.threads = int(p.get("threads", 4))
    cams = B.cameras(scene, L)
    key, fill, rim = (bpy.data.objects[n] for n in ("key", "fill", "rim"))
    bg = scene.world.node_tree.nodes.get("Background")
    M, H, ZC = L.M_PER_PX, L.H, L.Z_CENTER

    def sample_pose(rng):
        """Euler angles per bone (limit frame): half uniform inside the limits, half a narrower spread around rest."""
        pose = {}
        wide = rng.random() < 0.5
        for name in bones:
            lo, hi = lim[name][:, 0].copy(), lim[name][:, 1].copy()
            if name == root and rng.random() < 0.15:  # sometimes a deep forward lean or a back arch
                lo[0], hi[0] = math.radians(-35), math.radians(75)
            a = rng.uniform(lo, hi) if wide else np.clip(rng.normal(0, 0.3 * (hi - lo) / 2), lo, hi)
            pose[name] = a
        return pose

    def apply(pose, loc, yaw, frame):
        for name, a in pose.items():
            pb = rig.pose.bones[name]
            pb.rotation_quaternion = B.pose_quaternion(binfo[name], a)
            if frame is not None:
                pb.keyframe_insert("rotation_quaternion", frame=frame)
        rig.location = loc
        rig.rotation_euler = (0, 0, yaw)
        if frame is not None:
            rig.keyframe_insert("location", frame=frame)
            rig.keyframe_insert("rotation_euler", frame=frame)

    def lowest_z():
        dg = bpy.context.evaluated_depsgraph_get()
        ev = body.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        mw = np.array(body.matrix_world)
        return (co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3])[:, 2].min()

    def in_view(jw):
        f, s = L.project(jw)
        return bool((f[:, 0] > 2).all() and (f[:, 0] < L.W_FRONT - 2).all() and (s[:, 0] > 2).all()
                    and (s[:, 0] < L.W_SIDE - 2).all() and (f[:, 1] > 2).all() and (f[:, 1] < H - 2).all())

    redrawn, failed, written = 0, 0, []
    for i in range(start, start + count):
        stem_ = out / f"{i:05d}"
        if (out / f"{i:05d}_meta.json").exists():
            written.append(i)
            continue
        rng = np.random.default_rng([seed, i])   # the sample is the same in whichever process and range it falls
        for attempt in range(5):
            rig.animation_data_clear()
            for a in list(bpy.data.actions):
                bpy.data.actions.remove(a)
            for pb in rig.pose.bones:
                pb.location = (0, 0, 0)
            pose = sample_pose(rng)
            r = rng.random()
            yaw = math.radians(rng.uniform(-30, 30) if r < 0.75 else rng.uniform(-70, 70) if r < 0.85 else 0)
            loc = Vector((rng.uniform(-0.08, 0.08), rng.uniform(-0.25, 0.25), 0))
            apply(pose, loc, yaw, None)
            bpy.context.view_layer.update()
            loc.z = -lowest_z() + (rng.uniform(0.05, 0.45) if rng.random() < 0.2 else 0)
            blur = rng.random() < 0.5
            if blur:  # key the pose at frames 0, 1, 2 along a random velocity; render frame 1 with motion blur
                vel = {n: rng.normal(0, math.radians(6 if stem(contract[n]) in FAST else 2.5), 3) for n in bones}
                vloc = Vector(rng.normal(0, 0.015, 3).tolist())
                vyaw = rng.normal(0, math.radians(3))
                for f, s in ((0, -1), (1, 0), (2, 1)):
                    apply({n: pose[n] + s * vel[n] for n in bones}, loc + s * vloc, yaw + s * vyaw, f)
                scene.frame_set(1)
                scene.render.use_motion_blur = True
                scene.render.motion_blur_shutter = rng.uniform(0.5, 1.0)
            else:
                apply(pose, loc, yaw, None)
                scene.render.use_motion_blur = False
                bpy.context.view_layer.update()
            jw = B.joints_world(rig, info)
            if in_view(jw):
                break
            redrawn += 1
        else:
            failed += 1
            continue
        # lights and world
        key.rotation_euler = (math.radians(rng.uniform(20, 70)), 0, rng.uniform(-math.pi, math.pi))
        key.data.energy = rng.uniform(1.5, 4.5)
        fill.rotation_euler = (math.radians(rng.uniform(30, 80)), 0, rng.uniform(-math.pi, math.pi))
        fill.data.energy = rng.uniform(0.2, 1.5)
        rim.data.energy = rng.uniform(0.0, 2.5)
        if bg is not None:
            bg.inputs["Strength"].default_value = rng.uniform(0.3, 0.9)
            g = rng.uniform(0.4, 0.6)
            bg.inputs["Color"].default_value = (g * rng.uniform(0.9, 1.1), g, g * rng.uniform(0.9, 1.1), 1)
        front = np.stack([L.W_FRONT / 2 + jw[:, 0] / M, H / 2 - (jw[:, 2] - ZC) / M], 1)
        side = np.stack([L.W_SIDE / 2 - jw[:, 1] / M, H / 2 - (jw[:, 2] - ZC) / M], 1)
        for name, (cam, w) in cams.items():
            scene.camera = cam
            scene.render.resolution_x, scene.render.resolution_y = round(w * scale), round(H * scale)
            scene.render.resolution_percentage = 100
            scene.render.filepath = f"{stem_}_{name.split('_')[1]}.png"
            bpy.ops.render.render(write_still=True)
        meta = {"joints_world": jw.round(5).tolist(), "front_uv": front.round(3).tolist(), "side_uv": side.round(3).tolist(),
                "scale": scale, "blur": blur, "yaw": yaw, "root": list(loc),
                "pose": {n: np.round(a, 5).tolist() for n, a in pose.items()}}
        (out / f"{i:05d}_meta.json").write_text(json.dumps(meta))
        written.append(i)
        print("sample", i, flush=True)
    complete = [i for i in range(start, start + count)
                if all((out / f"{i:05d}_{k}").exists() for k in ("front.png", "side.png", "meta.json"))]
    frac = (count - failed) / max(count, 1)
    gates = [B.gate("dataset.in_view", round(frac, 4), ">= 0.95", frac >= 0.95),
             B.gate("dataset.written", len(complete), count, len(complete) == count)]
    ok = all(g["pass"] for g in gates)
    return B.report("render_dataset.py", p, gates, written=len(complete), redrawn=redrawn, failed=failed,
                    device=dev, out_dir=str(out)), 0 if ok else 2


def selftest() -> tuple:
    import prepare_rig
    checks = []
    with tempfile.TemporaryDirectory() as td:
        B.demo_scene()
        prepare_rig.prepare({"out_dir": td})
        blend, ri = os.path.join(td, "twocam.blend"), os.path.join(td, "rig_info.json")
        ds = os.path.join(td, "ds")
        r, code = render_dataset({"blend": blend, "rig_info": ri, "out_dir": ds, "start": 0, "count": 4, "seed": 3,
                                  "scale": 0.25, "engine": "workbench"})
        checks.append({"name": "four samples, exit 0", "pass": code == 0, "gates": r["gates"]})
        hits, total = 0, 0
        for i in range(4):
            meta = json.loads(pathlib.Path(ds, f"{i:05d}_meta.json").read_text())
            for view in ("front", "side"):
                a = B.read_png_rgba(os.path.join(ds, f"{i:05d}_{view}.png"))[..., 3] > 0
                for u, v in np.array(meta[f"{view}_uv"]) * meta["scale"]:
                    total += 1
                    y0, x0 = int(round(v)), int(round(u))
                    hits += bool(a[max(0, y0 - 2):y0 + 3, max(0, x0 - 2):x0 + 3].any())
        checks.append({"name": "every joint's pixel lands on the character (within 2 px)", "pass": hits == total,
                       "hits": hits, "total": total})
        meta = json.loads(pathlib.Path(ds, "00000_meta.json").read_text())
        L = Layout.from_rig_info(B.load_info(ri))
        f, s = L.project(np.array(meta["joints_world"]))
        checks.append({"name": "meta pixels = the layout projection", "pass": np.allclose(f, meta["front_uv"], atol=1e-2)
                       and np.allclose(s, meta["side_uv"], atol=1e-2)})
        alone = os.path.join(td, "alone")   # sample 3 by itself, in a fresh scene, against sample 3 after 0-2
        r, code = render_dataset({"blend": blend, "rig_info": ri, "out_dir": alone, "start": 3, "count": 1, "seed": 3,
                                  "scale": 0.25, "engine": "workbench"})
        same_meta = json.loads(pathlib.Path(alone, "00003_meta.json").read_text()) == \
            json.loads(pathlib.Path(ds, "00003_meta.json").read_text())
        diff = max(float(np.abs(B.read_png_rgba(os.path.join(alone, f"00003_{v}.png")).astype(int)
                                - B.read_png_rgba(os.path.join(ds, f"00003_{v}.png")).astype(int)).max())
                   for v in ("front", "side"))
        checks.append({"name": "a sample rendered alone matches it rendered after others (no pose carried over)",
                       "pass": code == 0 and same_meta and diff <= 2, "max_diff": diff})
        checks.append({"name": "this Blender names an EEVEE engine", "pass": B.eevee_engine().startswith("BLENDER_EEVEE"),
                       "engine": B.eevee_engine()})
        bogus = os.path.join(td, "ds3")
        os.makedirs(bogus)
        pathlib.Path(bogus, "00000_meta.json").write_text("{}")   # a meta left behind without its renders
        r, code = render_dataset({"blend": blend, "rig_info": ri, "out_dir": bogus, "start": 0, "count": 1, "seed": 3,
                                  "scale": 0.25, "engine": "workbench"})
        checks.append({"name": "a sample without its renders fails dataset.written, exit 2",
                       "pass": code == 2 and not r["gates"][1]["pass"]})
        info = B.load_info(ri)
        info["layout"]["M_PER_PX"] = 0.0008     # a frame far too small for the character
        tight = os.path.join(td, "tight.json")
        with open(tight, "w") as fh:
            json.dump(info, fh)
        r, code = render_dataset({"blend": blend, "rig_info": tight, "out_dir": os.path.join(td, "ds2"), "start": 0,
                                  "count": 2, "seed": 3, "scale": 0.25, "engine": "workbench"})
        checks.append({"name": "joints out of view fail dataset.in_view, exit 2", "pass": code == 2 and not r["gates"][0]["pass"]})
    ok = all(c["pass"] for c in checks)
    return {"tool": "render_dataset.py", "selftest": "pass" if ok else "fail", "checks": len(checks),
            "failed": [c for c in checks if not c["pass"]]}, 0 if ok else 1


def main():
    args = B.script_args()
    if "--selftest" in args or args[:1] == ["selftest"]:
        return selftest()
    if len(args) < 6:
        raise ValueError("usage: -- TWOCAM.blend RIG_INFO.json OUT_DIR START COUNT SEED [options]")
    p = dict(zip(("blend", "rig_info", "out_dir", "start", "count", "seed"), args[:6]))
    for k in ("scale", "samples", "engine", "device", "threads", "png-compression"):
        if f"--{k}" in args:
            p[k.replace("-", "_")] = args[args.index(f"--{k}") + 1]
    if p.get("engine", "cycles") not in ("cycles", "eevee", "workbench"):
        raise ValueError(f"--engine {p['engine']}: cycles, eevee or workbench")
    if len(args) > 6 and not args[6].startswith("--"):   # upstream's positional [scale]
        p["scale"] = args[6]
    return render_dataset(p)


if __name__ == "__main__":
    B.guarded(main)
