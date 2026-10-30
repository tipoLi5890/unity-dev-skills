#!/usr/bin/env python3
"""layout_map.py — draw each keyframe's arrangement through one fixed camera, and test the moves between them.

A keyframe prompt carries a layout map as its second image: which object,
roughly where, which colour, which way it faces. Drawn by program from ground
coordinates, it cannot disagree with itself, and the same coordinates test
whether the straight-line moves between two keyframes cross.

usage:
    layout_map.py SCENE.json --out DIR [--check-paths] [--margin 0]
    layout_map.py selftest            (or --selftest)

SCENE.json:
    {"size": [1344, 768],                                     pixels
     "camera": {"fov": 50, "height": 4, "pitch": 20, "target": [0, 6]},
     "ground": {"color": "#8a8f7a"}, "sky": {"color": "#d9dde3"},   optional
     "objects": {"runner": {"color": "#e05a2a", "shape": "figure", "size": [0.4, 1.7]},
                 "gate":   {"color": "#3a6fd8", "shape": "box",    "size": [3, 0.4, 2]},
                 "pickup": {"color": "#f2c230", "shape": "disc",   "size": 0.35}},
     "frames": [{"name": "k01", "place": {"runner": [0, 1, 90], "gate": [0, 8, 0]}}, ...]}

  Ground coordinates are metres: x to the right, y away from the camera, z up.
  `place` is [x, y] or [x, y, facing_deg]; facing 0 points along +x, 90 along
  +y (away from the camera), counter-clockwise seen from above. Sizes: box
  [width, depth, height], width along the facing and depth across it (the gate
  above, facing 0, spans 3 m of x); disc radius; figure [radius, height] (a standing
  cylinder). Camera: vertical fov in degrees, eye height in metres, pitch in
  degrees below horizontal, and the ground point the view centre lands on;
  defaults 50, 4, 20, [0, 0]. Keep pitch under fov / 2 so the horizon is in
  frame: it is the line camera_gate.py reads. An object a frame does not place is absent.

Writes DIR/<frame>.png per frame (flat colours, no text: sky, ground, then the
objects far to near, each with a lighter top, and a dark triangle on that top
and a dark wedge on the ground pointing the way it faces) and DIR/layouts.json:
the resolved camera, the drawn horizon row, and per frame each placed object's
pixel box [x0, y0, x1, y1] (inclusive, clipped to the image; geometric, not
occlusion-aware), centre, depth, `visible` and `clipped`. Every mark drawn for
an object, the ground wedge included, lies inside its box.

--check-paths moves every object placed in two consecutive frames in a straight
line from one to the next and reports each pair whose swept footprints touch:
segment-to-segment distance < ra + rb + --margin, timing ignored (a video model
does not keep it). A footprint radius is half the smaller ground side of a box,
or the radius of a disc or figure. Two objects moving by the same displacement
move as one group and are reported only if they already overlap; pairs where
neither moves are skipped. Reports go in
layouts.json `paths` with `clearance_m` (negative = how deep the overlap).

Prints one JSON line: frames written, crossings found. Exit codes: 0 written,
no crossings; 2 written, crossings found (--check-paths); 3 the scene cannot be
read or is invalid (a wrong type, a non-finite number, a coordinate past 1e4 m),
or DIR cannot be written (every frame is drawn before the first file is written);
1 a usage error or a failed selftest.

Requires Python 3.9+, Pillow and numpy.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor, ImageDraw

SHAPES = ("box", "disc", "figure")
REACH = 1e4                                    # metres: a coordinate or size beyond this is a typo
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class SceneError(ValueError):
    pass


# ------------------------------------------------------------------------------------ camera
class Camera:
    def __init__(self, size, fov=50.0, height=4.0, pitch=20.0, target=(0.0, 0.0)):
        if not 0 < pitch < 90 or not 1 < fov < 170 or height <= 0:
            raise SceneError("camera needs 0 < pitch < 90, 1 < fov < 170, height > 0")
        self.w, self.h = size
        p = math.radians(pitch)
        self.f = (self.h / 2) / math.tan(math.radians(fov) / 2)
        tx, ty = float(target[0]), float(target[1])
        self.pos = np.array([tx, ty - height / math.tan(p), height])
        self.fwd = np.array([0.0, math.cos(p), -math.sin(p)])
        self.up = np.array([0.0, math.sin(p), math.cos(p)])
        self.desc = {"fov": fov, "height": height, "pitch": pitch, "target": [tx, ty],
                     "position": [round(float(v), 4) for v in self.pos]}
        self.horizon = self.h / 2 - self.f * math.tan(p)

    def depth(self, pt):
        return float((np.asarray(pt, float) - self.pos) @ self.fwd)

    def project(self, pts):
        d = np.asarray(pts, float) - self.pos
        z = d @ self.fwd
        if (z <= 0.05).any():
            return None
        u = self.w / 2 + self.f * d[:, 0] / z
        v = self.h / 2 - self.f * (d @ self.up) / z
        return np.stack([u, v], axis=1)


# ------------------------------------------------------------------------------------ scene
def colour(s, where):
    try:
        return ImageColor.getrgb(s)[:3]
    except (ValueError, TypeError):
        raise SceneError(f"{where}: not a colour: {s!r}")


def shade(rgb, k):
    return tuple(max(0, min(255, int(round(c * k)))) for c in rgb)


def load_scene(path):
    try:
        s = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SceneError(f"cannot read {path}: {e.__class__.__name__}")
    try:
        return validate(s)
    except (AttributeError, TypeError, IndexError, KeyError) as e:   # a shape validate() did not foresee
        raise SceneError(f"invalid scene: {e.__class__.__name__}: {e}")


def num(v):
    """A finite JSON number within REACH (bools are not numbers here)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and abs(v) <= REACH


def table(v, where):
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise SceneError(f"{where} must be a JSON object")
    return v


def validate(s):
    if not isinstance(s, dict):
        raise SceneError("scene must be a JSON object")
    size = s.get("size")
    if not (isinstance(size, list) and len(size) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) and 15 < v <= 16384 for v in size)):
        raise SceneError("size must be [width, height] in pixels, each 16 to 16384")
    cam = table(s.get("camera"), "camera")
    for k in ("fov", "height", "pitch"):
        if k in cam and not num(cam[k]):
            raise SceneError(f"camera {k} must be a finite number")
    target = cam.get("target", [0, 0])
    if not (isinstance(target, list) and len(target) == 2 and all(num(v) for v in target)):
        raise SceneError("camera target must be [x, y] in metres")
    camera = Camera(size, cam.get("fov", 50), cam.get("height", 4), cam.get("pitch", 20), target)
    objs = {}
    for oid, o in table(s.get("objects"), "objects").items():
        if not isinstance(o, dict):
            raise SceneError(f"object {oid}: must be a JSON object")
        shape = o.get("shape")
        if shape not in SHAPES:
            raise SceneError(f"object {oid}: shape must be one of {SHAPES}")
        sz = o.get("size")
        sz = [sz] if isinstance(sz, (int, float)) else sz
        need = {"box": 3, "disc": 1, "figure": 2}[shape]
        if not (isinstance(sz, list) and len(sz) == need and all(num(v) and v > 0 for v in sz)):
            raise SceneError(f"object {oid}: {shape} size needs {need} positive number(s)")
        objs[oid] = {"shape": shape, "size": [float(v) for v in sz], "rgb": colour(o.get("color"), f"object {oid}")}
    if not objs:
        raise SceneError("no objects")
    frames, seen = [], set()
    if not isinstance(s.get("frames") or [], list):
        raise SceneError("frames must be a list")
    for i, fr in enumerate(s.get("frames") or []):
        if not isinstance(fr, dict):
            raise SceneError(f"frame {i}: must be a JSON object")
        name = fr.get("name")
        if not isinstance(name, str) or not NAME.match(name) or name in seen:
            raise SceneError(f"frame {i}: name must be a unique plain filename stem, got {name!r}")
        seen.add(name)
        place = {}
        for oid, p in table(fr.get("place"), f"frame {name}: place").items():
            if oid not in objs:
                raise SceneError(f"frame {name}: unknown object {oid!r}")
            if not (isinstance(p, list) and len(p) in (2, 3) and all(num(v) for v in p)):
                raise SceneError(f"frame {name}: {oid} needs [x, y] or [x, y, facing_deg], "
                                 f"finite and within {REACH:g} m")
            place[oid] = (float(p[0]), float(p[1]), float(p[2]) if len(p) == 3 else 0.0)
        frames.append({"name": name, "place": place})
    if not frames:
        raise SceneError("no frames")
    return {"size": size, "camera": camera, "objects": objs, "frames": frames,
            "ground": colour(table(s.get("ground"), "ground").get("color", "#8a8f7a"), "ground"),
            "sky": colour(table(s.get("sky"), "sky").get("color", "#d9dde3"), "sky")}


def footprint(o):
    sz = o["size"]
    return min(sz[0], sz[1]) / 2 if o["shape"] == "box" else sz[0]


# ------------------------------------------------------------------------------------ drawing
def ring(cx, cy, r, z, n=48):
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return np.stack([cx + r * np.cos(a), cy + r * np.sin(a), np.full(n, z)], axis=1)


def hull(pts):
    pts = sorted(set(map(tuple, pts)))
    if len(pts) < 3:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                                     - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(p)
        return out
    lo, hi = half(pts), half(pts[::-1])
    return lo[:-1] + hi[:-1]


def geometry(o, x, y, facing):
    """Return (body points, top-face points, top mark, ground nose) in world space."""
    a = math.radians(facing)
    c, s = math.cos(a), math.sin(a)
    rot = lambda lx, ly, z: (x + lx * c - ly * s, y + lx * s + ly * c, z)  # noqa: E731
    if o["shape"] == "box":
        w, d, h = o["size"]
        loc = [(-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)]
        body = [rot(lx, ly, 0.0) for lx, ly in loc] + [rot(lx, ly, h) for lx, ly in loc]
        top = [rot(lx, ly, h) for lx, ly in loc]
        reach, half = w / 2, min(w, d) * 0.3
    else:
        r = o["size"][0]
        h = 0.02 if o["shape"] == "disc" else o["size"][1]
        top = ring(x, y, r, h).tolist()
        body = ring(x, y, r, 0.0).tolist() + top
        w, d, reach, half = 2 * r, 2 * r, r, r * 0.6
    # a triangle on the top face and a wedge on the ground, both pointing along local +x
    mark = [rot(w * 0.4, 0, h), rot(-w * 0.15, d * 0.3, h), rot(-w * 0.15, -d * 0.3, h)]
    nose_len = max(0.3, 0.8 * min(w, d) / 2)
    nose = [rot(reach * 0.5, half, 0.0), rot(reach + nose_len, 0, 0.0), rot(reach * 0.5, -half, 0.0)]
    return np.array(body), np.array(top), np.array(mark), np.array(nose)


def background(scene):
    w, h = scene["size"]
    im = Image.new("RGB", (w, h), scene["ground"])
    hz = scene["camera"].horizon
    if hz > 0:
        ImageDraw.Draw(im).rectangle([0, 0, w - 1, min(h - 1, int(math.floor(hz)))], fill=scene["sky"])
    return im


def render(scene, frame):
    cam, objs = scene["camera"], scene["objects"]
    w, h = scene["size"]
    im = background(scene)
    dr = ImageDraw.Draw(im)
    report, order = {}, []
    for oid, (x, y, fa) in frame["place"].items():
        order.append((cam.depth((x, y, 0.0)), oid, x, y, fa))
    for depth, oid, x, y, fa in sorted(order, key=lambda t: (-t[0], t[1])):
        o = objs[oid]
        body, top, mark, nose = geometry(o, x, y, fa)
        pa = cam.project(np.vstack([body, nose]))
        rec = {"center": None, "depth": round(depth, 4), "box": None, "visible": False, "clipped": False}
        report[oid] = rec
        if pa is None:
            continue
        pa = np.rint(pa).astype(int)
        pb, pn = pa[:len(body)], pa[len(body):]
        pt = np.rint(cam.project(top)).astype(int)
        pm = np.rint(cam.project(mark)).astype(int)
        dr.polygon([tuple(p) for p in pn.tolist()], fill=shade(o["rgb"], 0.35))
        dr.polygon([tuple(p) for p in hull(pb.tolist())], fill=shade(o["rgb"], 0.72))
        dr.polygon([tuple(p) for p in hull(pt.tolist())], fill=o["rgb"])
        dr.polygon([tuple(p) for p in pm.tolist()], fill=shade(o["rgb"], 0.35))
        x0, y0 = pa.min(axis=0)
        x1, y1 = pa.max(axis=0)
        cx, cy = np.rint(cam.project([(x, y, 0.0)])[0]).astype(int)
        rec["center"] = [int(cx), int(cy)]
        if x1 < 0 or y1 < 0 or x0 >= w or y0 >= h:
            continue
        box = [max(0, int(x0)), max(0, int(y0)), min(w - 1, int(x1)), min(h - 1, int(y1))]
        rec.update(box=box, visible=True, clipped=box != [int(x0), int(y0), int(x1), int(y1)])
    return im, report


# ------------------------------------------------------------------------------------ paths
def seg_dist(p0, p1, q0, q1):
    p0, p1, q0, q1 = (np.asarray(v, float) for v in (p0, p1, q0, q1))

    def pt_seg(p, a, b):
        ab = b - a
        L = ab @ ab
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((p - a) @ ab) / L))
        return float(np.linalg.norm(p - (a + t * ab)))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1, d2 = cross(q0, q1, p0), cross(q0, q1, p1)
    d3, d4 = cross(p0, p1, q0), cross(p0, p1, q1)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return 0.0
    return min(pt_seg(p0, q0, q1), pt_seg(p1, q0, q1), pt_seg(q0, p0, p1), pt_seg(q1, p0, p1))


def check_paths(scene, margin=0.0):
    out, objs, frs = [], scene["objects"], scene["frames"]
    for a, b in zip(frs, frs[1:]):
        ids = sorted(set(a["place"]) & set(b["place"]))
        for i, m in enumerate(ids):
            for n in ids[i + 1:]:
                pm0, pm1 = a["place"][m][:2], b["place"][m][:2]
                pn0, pn1 = a["place"][n][:2], b["place"][n][:2]
                need = footprint(objs[m]) + footprint(objs[n]) + margin
                dm = np.subtract(pm1, pm0)
                if np.allclose(dm, np.subtract(pn1, pn0), atol=1e-6):
                    if not dm.any():
                        continue                      # neither moves
                    gap = float(np.linalg.norm(np.subtract(pm0, pn0)))  # moving as one group
                else:
                    gap = seg_dist(pm0, pm1, pn0, pn1)
                if gap < need - 1e-9:
                    out.append({"from": a["name"], "to": b["name"], "a": m, "b": n,
                                "clearance_m": round(gap - need, 4)})
    return out


def run(scene, out_dir, paths=False, margin=0.0):
    """Every frame is drawn before the first file is written."""
    out_dir = Path(out_dir)
    frames, images = [], []
    for fr in scene["frames"]:
        im, rep = render(scene, fr)
        images.append((f"{fr['name']}.png", im))
        frames.append({"name": fr["name"], "image": f"{fr['name']}.png", "objects": rep})
    crossings = check_paths(scene, margin) if paths else None
    cam = scene["camera"]
    doc = {"size": scene["size"], "camera": cam.desc, "horizon_row": round(cam.horizon, 2),
           "frames": frames, "paths": crossings}
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, im in images:
        im.save(out_dir / name)
    (out_dir / "layouts.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


# ------------------------------------------------------------------------------------ selftest
def selftest() -> int:
    checks, failed = [], []

    def check(name, ok, info=None):
        checks.append(name)
        if not ok:
            failed.append({"check": name, "info": info})

    base = {"size": [640, 360], "camera": {"fov": 50, "height": 4, "pitch": 20, "target": [0, 6]},
            "objects": {"crate": {"color": "#c04020", "shape": "box", "size": [1.2, 0.8, 1.0]},
                        "coin": {"color": "#f0c020", "shape": "disc", "size": 0.5},
                        "runner": {"color": "#2060e0", "shape": "figure", "size": [0.4, 1.7]},
                        "mallet": {"color": "#20a050", "shape": "box", "size": [1, 1, 0.5]}}}
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # 1. each drawn object sits exactly inside its reported box
        frames = [{"name": f"solo_{k}", "place": {k: [x, y, fa]}}
                  for k, x, y, fa in (("crate", 1, 5, 30), ("coin", -2, 4, 120), ("runner", 0.5, 7, 250))]
        sc = validate(dict(base, frames=frames))
        doc = run(sc, d / "solo")
        bg = np.asarray(background(sc), dtype=int)
        for fr in doc["frames"]:
            img = np.asarray(Image.open(d / "solo" / fr["image"]).convert("RGB"), dtype=int)
            ys, xs = np.nonzero(np.abs(img - bg).sum(axis=2))
            (oid, rec), = fr["objects"].items()
            drawn = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
            ok = rec["visible"] and all(abs(p - q) <= 1 for p, q in zip(drawn, rec["box"]))
            check(f"box matches drawn {oid}", ok, {"drawn": drawn, "box": rec["box"]})
        # 2. projection: the target lands at the image centre; the horizon row is drawn there
        cam = sc["camera"]
        c = cam.project([(0, 6, 0)])[0]
        check("target projects to centre", abs(c[0] - 320) < 1e-6 and abs(c[1] - 180) < 1e-6, c.tolist())
        hz = int(math.floor(cam.horizon))
        img = np.asarray(Image.open(d / "solo" / "solo_coin.png").convert("RGB"))
        check("sky above the horizon, ground below",
              tuple(img[hz, 5]) == sc["sky"] and tuple(img[hz + 1, 5]) == sc["ground"], hz)
        # 3. paths: a swap crosses; a group sliding together does not; a mover through a still one does
        def paths(frames):
            return check_paths(validate(dict(base, frames=frames)))
        swap = paths([{"name": "a", "place": {"crate": [-2, 5], "runner": [2, 5]}},
                      {"name": "b", "place": {"crate": [2, 5], "runner": [-2, 5]}}])
        check("swap reported", len(swap) == 1 and {swap[0]["a"], swap[0]["b"]} == {"crate", "runner"}, swap)
        slide = paths([{"name": "a", "place": {"mallet": [-2, 5], "crate": [-0.6, 5]}},
                       {"name": "b", "place": {"mallet": [1, 5], "crate": [2.4, 5]}}])
        check("adjacent group sliding together not reported", slide == [], slide)
        par = paths([{"name": "a", "place": {"runner": [-2, 4], "coin": [-2, 7]}},
                     {"name": "b", "place": {"runner": [2, 4], "coin": [2, 7]}}])
        check("parallel lanes not reported", par == [], par)
        through = paths([{"name": "a", "place": {"runner": [-3, 5], "crate": [0, 5.2]}},
                         {"name": "b", "place": {"runner": [3, 5], "crate": [0, 5.2]}}])
        check("mover through a still object reported", len(through) == 1, through)
        beside = paths([{"name": "a", "place": {"runner": [-3, 3], "crate": [0, 5.2]}},
                        {"name": "b", "place": {"runner": [3, 3], "crate": [0, 5.2]}}])
        check("mover passing clear of a still object not reported", beside == [], beside)
        # 4. invalid scenes refuse
        ok_frames = [{"name": "a", "place": {"coin": [0, 5]}}]
        for name, bad in (("unknown object", dict(base, frames=[{"name": "a", "place": {"ghost": [0, 0]}}])),
                          ("unsafe frame name", dict(base, frames=[{"name": "../x", "place": {"coin": [0, 5]}}])),
                          ("objects as a list", dict(base, objects=[1], frames=ok_frames)),
                          ("an object that is a number", dict(base, objects={"coin": 3}, frames=ok_frames)),
                          ("camera as a list", dict(base, camera=[], frames=ok_frames)),
                          ("fov as text", dict(base, camera={"fov": "wide"}, frames=ok_frames)),
                          ("target of one number", dict(base, camera={"target": [1]}, frames=ok_frames)),
                          ("frames of numbers", dict(base, frames=[1])),
                          ("a NaN coordinate", dict(base, frames=[{"name": "a", "place": {"coin": [math.nan, 5]}}])),
                          ("a coordinate past reach", dict(base, frames=[{"name": "a", "place": {"coin": [0, 1e300]}}]))):
            try:
                validate(json.loads(json.dumps(bad)))
                check(f"refuses {name}", False)
            except SceneError:
                check(f"refuses {name}", True)
            except Exception as e:  # noqa: BLE001 - any other error is the failure this checks for
                check(f"refuses {name}", False, repr(e))
        # 5. the same scene twice gives the same bytes
        run(sc, d / "again")
        same = all((d / "solo" / f).read_bytes() == (d / "again" / f).read_bytes()
                   for f in ("solo_crate.png", "layouts.json"))
        check("deterministic", same)
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": len(checks), "failed": failed}))
    return 0 if not failed else 1


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["selftest"], ["--selftest"]):
        return selftest()
    p = UsageParser(description=__doc__.split("\n")[0])
    p.add_argument("scene", help="SCENE.json")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--check-paths", action="store_true", help="report moves whose swept footprints touch")
    p.add_argument("--margin", type=float, default=0.0, help="extra clearance in metres")
    a = p.parse_args(argv)
    try:
        if not math.isfinite(a.margin):
            raise SceneError("--margin must be a finite number")
        scene = load_scene(a.scene)
    except SceneError as e:
        print(json.dumps({"written": 0, "error": str(e)}))
        return 3
    try:
        doc = run(scene, a.out, a.check_paths, a.margin)
    except OSError as e:
        print(json.dumps({"written": 0, "error": f"cannot write {a.out}: {e.__class__.__name__}"}))
        return 3
    n = len(doc["paths"] or [])
    print(json.dumps({"written": len(doc["frames"]), "layouts": str(Path(a.out) / "layouts.json"),
                      "crossings": n if a.check_paths else None}))
    return 2 if n else 0


if __name__ == "__main__":
    sys.exit(main())
