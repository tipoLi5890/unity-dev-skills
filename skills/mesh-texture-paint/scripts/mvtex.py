#!/usr/bin/env python3
"""Multi-view texture projection core: render a mesh, project painted views into its UV texture.

numpy + scipy + Pillow only. One mesh primitive (the shape image-to-3D GLBs carry).

Pieces:
  load_glb / glb_image             read positions, UVs, indices and a material image
  write_glb_basecolor / write_glb  swap the base-colour image of a GLB / write a minimal textured GLB
  Camera                           perspective look-at camera (OpenGL convention, Y up)
  rasterize                        vectorised z-buffer: triangle id, depth, perspective barycentrics
  uv_maps                          per-texel 3D position and face normal from the UV layout
  render_clay / render_texture     guide and review renders on a flat key colour
  render_context                   the painted texture with unpainted surface shown as a prior or marker
  align_painted                    register a painted view to the render silhouette
  gate measures                    painted_pixels, drift_share, lighten_share, background_deviation,
                                   silhouette_edge_p90; despill for key-green bled into the figure
  Accumulator                      weighted back-projection, coverage, prior fill and gutter
  next_best_view                   the orbit camera that sees the most unpainted seeable surface

  python3 mvtex.py --selftest      synthetic checks, no network; exit 0 pass, 2 fail, 1 usage
"""
from __future__ import annotations

import io
import json
import math
import struct
from dataclasses import dataclass

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree

KEY = np.array([0, 255, 0], np.uint8)
MARK = np.array([255, 0, 255], np.uint8)  # unpainted surface in context renders


# ----------------------------------------------------------------------------- GLB

def _glb_chunks(data: bytes):
    magic, _ver, _len = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError("not a GLB")
    off, js, binc = 12, None, None
    while off < len(data):
        clen, ctype = struct.unpack_from("<I4s", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == b"JSON":
            js = json.loads(chunk)
        elif ctype == b"BIN\x00":
            binc = chunk
        off += 8 + clen
    return js, binc


_CT = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _accessor(js, binc, i):
    a = js["accessors"][i]
    bv = js["bufferViews"][a["bufferView"]]
    dt = np.dtype(_CT[a["componentType"]])
    n, k = a["count"], _NC[a["type"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0) or dt.itemsize * k
    raw = np.frombuffer(binc, np.uint8, count=stride * (n - 1) + dt.itemsize * k, offset=start)
    if stride == dt.itemsize * k:
        return raw.view(dt).reshape(n, k) if k > 1 else raw.view(dt)
    rows = np.lib.stride_tricks.as_strided(raw, (n, dt.itemsize * k), (stride, 1))
    out = np.ascontiguousarray(rows).view(dt).reshape(n, k)
    return out if k > 1 else out[:, 0]


@dataclass
class Mesh:
    v: np.ndarray      # (n,3) float64 positions
    uv: np.ndarray     # (n,2) float64, glTF convention (0,0) top-left of the image
    f: np.ndarray      # (m,3) int64
    path: str = ""

    @property
    def fn(self):
        a, b, c = self.v[self.f[:, 0]], self.v[self.f[:, 1]], self.v[self.f[:, 2]]
        n = np.cross(b - a, c - a)
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)

    @property
    def diag(self):
        return float(np.linalg.norm(self.v.max(0) - self.v.min(0)))

    @property
    def center(self):
        return (self.v.max(0) + self.v.min(0)) / 2


def load_glb(path) -> Mesh:
    js, binc = _glb_chunks(open(path, "rb").read())
    prim = js["meshes"][0]["primitives"][0]
    v = _accessor(js, binc, prim["attributes"]["POSITION"]).astype(np.float64)
    uv = _accessor(js, binc, prim["attributes"]["TEXCOORD_0"]).astype(np.float64)
    f = _accessor(js, binc, prim["indices"]).astype(np.int64).reshape(-1, 3)
    node = js["nodes"][js["scenes"][js.get("scene", 0)]["nodes"][0]]
    if "matrix" in node:
        m = np.array(node["matrix"], np.float64).reshape(4, 4).T
        v = v @ m[:3, :3].T + m[:3, 3]
    return Mesh(v, uv, f, str(path))


def glb_image(path, which="baseColorTexture") -> Image.Image:
    js, binc = _glb_chunks(open(path, "rb").read())
    mat = js["materials"][0]
    tex = (mat.get("pbrMetallicRoughness", {}).get(which) or mat.get(which))["index"]
    bv = js["bufferViews"][js["images"][js["textures"][tex]["source"]]["bufferView"]]
    o = bv.get("byteOffset", 0)
    return Image.open(io.BytesIO(binc[o:o + bv["byteLength"]])).convert("RGB")


def _texture_refs(js):
    """Texture indices referenced by material slots (core slots and pbrMetallicRoughness)."""
    refs = []
    for m in js.get("materials", []):
        for d in (m, m.get("pbrMetallicRoughness", {})):
            refs += [v["index"] for k, v in d.items() if k.endswith("Texture") and isinstance(v, dict) and "index" in v]
    return refs


def write_glb_basecolor(src, dst, image: Image.Image):
    """Copy a GLB, replacing the base-colour image with image (PNG); geometry and other maps untouched.

    The image bytes are replaced in place when the material owns an embedded base-colour image.
    Otherwise (no base-colour texture, an external uri, an image or texture shared with another
    slot) a new embedded image and texture are added and the base-colour slot points at them.
    """
    js, binc = _glb_chunks(open(src, "rb").read())
    buf = io.BytesIO()
    image.convert("RGB").save(buf, "PNG")
    new = buf.getvalue()
    views = js.setdefault("bufferViews", [])
    datas = [binc[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]] for bv in views]
    mats = js.setdefault("materials", [])
    if not mats:
        mats.append({})
    for mesh in js.get("meshes", []):
        for prim in mesh.get("primitives", []):
            prim.setdefault("material", 0)
    pbr = mats[0].setdefault("pbrMetallicRoughness", {})
    slot = pbr.get("baseColorTexture")
    textures, images = js.setdefault("textures", []), js.setdefault("images", [])
    img_i = None
    if slot is not None and 0 <= slot.get("index", -1) < len(textures):
        t = textures[slot["index"]]
        s = t.get("source")
        owned = (s is not None and 0 <= s < len(images) and "bufferView" in images[s]
                 and "extensions" not in t
                 and sum(x.get("source") == s for x in textures) == 1
                 and _texture_refs(js).count(slot["index"]) == 1)
        if owned:
            img_i = s
            datas[images[s]["bufferView"]] = new
    if img_i is None:  # give the base colour its own embedded image and texture
        views.append({"buffer": 0, "byteLength": len(new)})
        datas.append(new)
        images.append({"bufferView": len(views) - 1})
        img_i = len(images) - 1
        tex = {"source": img_i}
        if slot is not None and 0 <= slot.get("index", -1) < len(textures) and "sampler" in textures[slot["index"]]:
            tex["sampler"] = textures[slot["index"]]["sampler"]
        textures.append(tex)
        pbr["baseColorTexture"] = {**(slot or {}), "index": len(textures) - 1}
    images[img_i].pop("uri", None)
    images[img_i]["mimeType"] = "image/png"  # the bytes are PNG whatever the source carried
    out = bytearray()
    for bv, data in zip(views, datas):
        while len(out) % 4:
            out.append(0)
        bv["byteOffset"] = len(out)
        bv["byteLength"] = len(data)
        out += data
    while len(out) % 4:
        out.append(0)
    if not js.get("buffers"):
        js["buffers"] = [{}]
    js["buffers"][0]["byteLength"] = len(out)
    jb = json.dumps(js, separators=(",", ":")).encode()
    jb += b" " * (-len(jb) % 4)
    total = 12 + 8 + len(jb) + 8 + len(out)
    with open(dst, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, total))
        fh.write(struct.pack("<I4s", len(jb), b"JSON") + jb)
        fh.write(struct.pack("<I4s", len(out), b"BIN\x00") + bytes(out))


# ----------------------------------------------------------------------------- camera

@dataclass
class Camera:
    eye: np.ndarray
    target: np.ndarray
    fov_deg: float = 20.0
    width: int = 1024
    height: int = 1024
    up: tuple = (0.0, 1.0, 0.0)

    def basis(self):
        fwd = self.target - self.eye
        fwd = fwd / np.linalg.norm(fwd)
        up = np.array(self.up, float)
        if abs(np.dot(up, fwd)) > 0.999:
            up = np.array([0.0, 0.0, -1.0 if fwd[1] > 0 else 1.0])
        right = np.cross(fwd, up)
        right /= np.linalg.norm(right)
        true_up = np.cross(right, fwd)
        return right, true_up, fwd

    @property
    def f(self):
        return (self.height / 2) / math.tan(math.radians(self.fov_deg) / 2)

    def project(self, p):
        """World points -> (x, y) pixel coords and view depth (positive in front)."""
        r, u, fw = self.basis()
        d = p - self.eye
        z = d @ fw
        zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
        x = self.width / 2 + self.f * (d @ r) / zs
        y = self.height / 2 - self.f * (d @ u) / zs
        return np.stack([x, y], 1), z

    def to_json(self):
        r, u, fw = self.basis()
        return {"type": "persp", "eye": self.eye.tolist(), "target": self.target.tolist(),
                "fov_deg": self.fov_deg, "res": [self.width, self.height],
                "f": self.f, "R": [r.tolist(), u.tolist(), fw.tolist()]}

    @staticmethod
    def orbit(mesh_center, radius, yaw_deg, pitch_deg=0.0, fov_deg=20.0, size=1024, fill=0.9, target=None):
        """Camera on a sphere around target; yaw 0 sits on +Z looking toward -Z."""
        t = np.asarray(mesh_center if target is None else target, float)
        dist = radius / math.tan(math.radians(fov_deg) / 2) / fill
        yw, pt = math.radians(yaw_deg), math.radians(pitch_deg)
        d = np.array([math.sin(yw) * math.cos(pt), math.sin(pt), math.cos(yw) * math.cos(pt)])
        return Camera(t + d * dist, t, fov_deg, size, size)


# ----------------------------------------------------------------------------- raster

def rasterize(xy, z, tris, width, height, perspective=True, max_batch=6_000_000):
    """Vectorised z-buffer. xy: (n,2) pixel coords, z: (n,) depth (>0 visible).

    Returns tri (H,W) int (-1 empty), depth (H,W), bary (H,W,3) (perspective-correct if asked).
    """
    p = xy[tris]                      # (m,3,2)
    zz = z[tris]                      # (m,3)
    keep = (zz > 1e-6).all(1)
    x0 = np.floor(p[..., 0].min(1)).astype(np.int64)
    x1 = np.ceil(p[..., 0].max(1)).astype(np.int64)
    y0 = np.floor(p[..., 1].min(1)).astype(np.int64)
    y1 = np.ceil(p[..., 1].max(1)).astype(np.int64)
    keep &= (x1 >= 0) & (y1 >= 0) & (x0 < width) & (y0 < height)
    a, b, c = p[:, 0], p[:, 1], p[:, 2]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    keep &= np.abs(area) > 1e-12
    size = np.maximum(x1 - x0, y1 - y0) + 1
    ids = np.nonzero(keep)[0]
    cand = []
    S = 1
    while ids.size:
        sel = ids[size[ids] <= S]
        ids = ids[size[ids] > S]
        if sel.size:
            oy, ox = np.mgrid[0:S, 0:S]
            oy, ox = oy.ravel(), ox.ravel()
            step = max(1, max_batch // (S * S))
            for s0 in range(0, sel.size, step):
                t = sel[s0:s0 + step]
                px = x0[t, None] + ox[None]
                py = y0[t, None] + oy[None]
                cx, cy = px + 0.5, py + 0.5
                A, B, C = a[t], b[t], c[t]
                ar = area[t][:, None]
                w0 = ((B[:, 0, None] - cx) * (C[:, 1, None] - cy) - (B[:, 1, None] - cy) * (C[:, 0, None] - cx)) / ar
                w1 = ((C[:, 0, None] - cx) * (A[:, 1, None] - cy) - (C[:, 1, None] - cy) * (A[:, 0, None] - cx)) / ar
                w2 = 1 - w0 - w1
                ins = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6) & (px >= 0) & (py >= 0) & (px < width) & (py < height)
                if not ins.any():
                    continue
                ti, si = np.nonzero(ins)
                W = np.stack([w0[ti, si], w1[ti, si], w2[ti, si]], 1)
                tz = zz[t[ti]]
                if perspective:
                    inv = W / tz
                    depth = 1.0 / inv.sum(1)
                    W = inv * depth[:, None]
                else:
                    depth = (W * tz).sum(1)
                cand.append((py[ti, si] * width + px[ti, si], depth, t[ti], W))
        S *= 2
    tri = np.full(height * width, -1, np.int64)
    dep = np.full(height * width, np.inf)
    bar = np.zeros((height * width, 3))
    if cand:
        pix = np.concatenate([c[0] for c in cand])
        dd = np.concatenate([c[1] for c in cand])
        tt = np.concatenate([c[2] for c in cand])
        ww = np.concatenate([c[3] for c in cand])
        order = np.lexsort((dd, pix))
        pix, dd, tt, ww = pix[order], dd[order], tt[order], ww[order]
        first = np.ones(pix.size, bool)
        first[1:] = pix[1:] != pix[:-1]
        tri[pix[first]] = tt[first]
        dep[pix[first]] = dd[first]
        bar[pix[first]] = ww[first]
    return tri.reshape(height, width), dep.reshape(height, width), bar.reshape(height, width, 3)


def render_buffers(mesh: Mesh, cam: Camera):
    """Triangle id, depth and barycentrics of the mesh seen from cam."""
    xy, z = cam.project(mesh.v)
    return rasterize(xy, z, mesh.f, cam.width, cam.height)


def uv_maps(mesh: Mesh, res: int):
    """Per-texel triangle id, 3D position and face normal, rasterised in UV space."""
    xy = mesh.uv * res
    tri, _d, bar = rasterize(xy, np.ones(len(mesh.v)), mesh.f, res, res, perspective=False)
    valid = tri >= 0
    t = tri[valid]
    pos = (mesh.v[mesh.f[t]] * bar[valid][..., None]).sum(1)
    nrm = mesh.fn[t]
    return valid, t, pos, nrm


# ----------------------------------------------------------------------------- render

def _shade(mesh, cam, tri, light_up=0.35):
    r, u, fw = cam.basis()
    L = -fw + light_up * u
    L /= np.linalg.norm(L)
    n = mesh.fn[np.maximum(tri, 0)]
    # face toward the camera for shading (double-sided look like a clay viewport)
    n = np.where(((n @ -fw) < 0)[..., None], -n, n)
    return 0.30 + 0.70 * np.clip(n @ L, 0, 1)


def render_clay(mesh: Mesh, cam: Camera, grey=0.78):
    tri, dep, bar = render_buffers(mesh, cam)
    m = tri >= 0
    img = np.empty((cam.height, cam.width, 3), np.uint8)
    img[:] = KEY
    s = _shade(mesh, cam, tri)
    v = np.clip(s * grey * 255, 0, 255).astype(np.uint8)
    img[m] = v[m][:, None]
    return img, m, tri, dep


def sample_bilinear(img, x, y):
    h, w = img.shape[:2]
    x = np.clip(x - 0.5, 0, w - 1.001)
    y = np.clip(y - 0.5, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    a = img[y0, x0].astype(np.float64)
    b = img[y0, x0 + 1].astype(np.float64)
    c = img[y0 + 1, x0].astype(np.float64)
    d = img[y0 + 1, x0 + 1].astype(np.float64)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def render_texture(mesh: Mesh, cam: Camera, tex: np.ndarray, bg=KEY):
    tri, dep, bar = render_buffers(mesh, cam)
    m = tri >= 0
    img = np.empty((cam.height, cam.width, 3), np.uint8)
    img[:] = bg
    t = tri[m]
    uv = (mesh.uv[mesh.f[t]] * bar[m][..., None]).sum(1)
    h, w = tex.shape[:2]
    img[m] = np.clip(sample_bilinear(tex, uv[:, 0] * w, uv[:, 1] * h), 0, 255).astype(np.uint8)
    return img, m


# ----------------------------------------------------------------------------- align

def key_mask(img: np.ndarray):
    """Foreground of an image on the key green (green clearly above red and blue is background)."""
    a = img.astype(np.int16)
    g = a[..., 1] - np.maximum(a[..., 0], a[..., 2])
    bg = (g > 45) & (a[..., 1] > 70)
    fgm = ~bg
    return ndimage.binary_opening(fgm, iterations=1)


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


def align_painted(painted: np.ndarray, render_mask: np.ndarray, max_shift=16, scales=(0.97, 0.985, 1.0, 1.015, 1.03)):
    """Similarity-register a painted view to the render silhouette (search on a half-res mask).

    Returns warped image, its key mask, and a report {iou_before, iou_after, scale, shift}.
    """
    H, W = render_mask.shape
    pm = key_mask(painted)
    before = iou(pm, render_mask)
    small_r = render_mask[::2, ::2]
    pim = Image.fromarray(pm.astype(np.uint8) * 255)
    best = (before, 1.0, 0, 0)
    cy, cx = H / 2, W / 2
    for s in scales:
        for dy in range(-max_shift, max_shift + 1, 2):
            for dx in range(-max_shift, max_shift + 1, 2):
                # inverse map: out(x) = in((x - c - d)/s + c)
                a = 1 / s
                M = (a, 0, cx - (cx + dx) * a, 0, a, cy - (cy + dy) * a)
                w = np.asarray(pim.transform((W, H), Image.AFFINE, M, Image.NEAREST))[::2, ::2] > 127
                v = iou(w, small_r)
                if v > best[0] + 1e-6:
                    best = (v, s, dx, dy)
    _, s, dx, dy = best
    a = 1 / s
    M = (a, 0, cx - (cx + dx) * a, 0, a, cy - (cy + dy) * a)
    warped = np.asarray(Image.fromarray(painted).transform((W, H), Image.AFFINE, M, Image.BILINEAR, fillcolor=tuple(int(x) for x in KEY)))
    wm = key_mask(warped)
    return warped, wm, {"iou_before": round(before, 4), "iou_after": round(iou(wm, render_mask), 4),
                        "edge_p90": round(silhouette_edge_p90(wm, render_mask), 1), "scale": s, "shift": [dx, dy]}


def silhouette_edge_p90(a, b):
    """90th percentile of the symmetric distance (px) between two masks' outlines.

    Unlike IoU it does not depend on how much area the figure covers: a thin side view and a
    wide front view are judged on the same pixel scale, and an extra figure drawn beside the
    guide (a collage) puts a long stretch of outline far from the render's.
    """
    ea = a & ~ndimage.binary_erosion(a)
    eb = b & ~ndimage.binary_erosion(b)
    if not ea.any() or not eb.any():
        return 1e9
    d = np.concatenate([ndimage.distance_transform_edt(~eb)[ea], ndimage.distance_transform_edt(~ea)[eb]])
    return float(np.percentile(d, 90))


def edge_distance(mask, depth, depth_jump):
    """Pixel distance to the silhouette or to a depth discontinuity inside it."""
    d = np.where(np.isfinite(depth), depth, 0)
    jump = np.zeros_like(mask)
    jump[:, 1:] |= np.abs(np.diff(d, axis=1)) > depth_jump
    jump[1:, :] |= np.abs(np.diff(d, axis=0)) > depth_jump
    jump &= mask
    border = mask & ~ndimage.binary_erosion(mask)
    return ndimage.distance_transform_edt(~(border | jump))


# ----------------------------------------------------------------------------- accumulate

class Accumulator:
    def __init__(self, mesh: Mesh, res=2048):
        self.mesh, self.res = mesh, res
        self.valid, self.tri, self.pos, self.nrm = uv_maps(mesh, res)
        n = self.pos.shape[0]
        self.wsum = np.zeros(n)
        self.csum = np.zeros((n, 3))
        self.best = np.zeros(n)          # best single-view weight seen
        self.owner = np.full(n, -1, np.int32)  # view that gave the best weight
        self.seeable = np.zeros(n, bool)
        self.views = 0

    def visibility(self, cam: Camera, tri=None, dep=None, max_angle=75.0):
        if tri is None:
            tri, dep, _ = render_buffers(self.mesh, cam)
        xy, z = cam.project(self.pos)
        x, y = xy[:, 0], xy[:, 1]
        inb = (x >= 0) & (y >= 0) & (x < cam.width - 1) & (y < cam.height - 1) & (z > 0)
        xi = np.clip(x.astype(int), 0, cam.width - 1)
        yi = np.clip(y.astype(int), 0, cam.height - 1)
        eps = 0.004 * self.mesh.diag
        vis = inb & (z <= dep[yi, xi] + eps)
        to_cam = cam.eye - self.pos
        to_cam /= np.linalg.norm(to_cam, axis=1, keepdims=True)
        cos = (self.nrm * to_cam).sum(1)
        vis &= cos > math.cos(math.radians(max_angle))
        return vis, cos, x, y

    def mark_seeable(self, cams):
        for c in cams:
            vis, _, _, _ = self.visibility(c)
            self.seeable |= vis

    def add_view(self, cam: Camera, painted: np.ndarray, paint_mask: np.ndarray, view_weight=1.0,
                 tri=None, dep=None, edge_lo=2.0, edge_hi=8.0, power=4.0, refine=1.5, match=True):
        """Back-project one painted view.

        refine: a texel that is already painted only takes this view when the view's weight beats
        the best earlier weight by this factor (None blends every view). match: fit a per-channel
        gain/offset from this view's colours to the texture on texels both already cover, so a
        view painted a shade off does not leave a seam.
        """
        if tri is None:
            tri, dep, _ = render_buffers(self.mesh, cam)
        rmask = tri >= 0
        vis, cos, x, y = self.visibility(cam, tri, dep)
        ed = edge_distance(rmask & paint_mask, dep, 0.01 * self.mesh.diag)
        xi = np.clip(x.astype(int), 0, cam.width - 1)
        yi = np.clip(y.astype(int), 0, cam.height - 1)
        ok = vis & paint_mask[yi, xi]
        we = np.clip((ed[yi, xi] - edge_lo) / (edge_hi - edge_lo), 0, 1)
        w = np.where(ok, view_weight * np.clip(cos, 0, 1) ** power * we, 0.0)
        had = self.wsum > 0
        rep = {}
        if match:
            pair = np.nonzero(had & (w > 0) & (cos > 0.5))[0]
            fit = fit_color_transfer(sample_bilinear(painted, x[pair], y[pair]),
                                     self.csum[pair] / self.wsum[pair, None])
            if fit is None:
                pass
            elif fit == "implausible":
                rep["match"] = "skipped: fit out of range"
            else:
                g, o = fit
                painted = np.clip(painted.astype(np.float64) * g + o, 0, 255)
                rep["match_gain"] = [round(float(v), 3) for v in g]
                rep["match_offset"] = [round(float(v), 1) for v in o]
        if refine is not None:
            w = np.where(had & (w < refine * self.best), 0.0, w)
        idx = np.nonzero(w > 0)[0]
        col = sample_bilinear(painted, x[idx], y[idx])
        self.wsum[idx] += w[idx]
        self.csum[idx] += w[idx, None] * col
        better = w > self.best
        self.owner[better] = self.views
        self.best = np.maximum(self.best, w)
        self.views += 1
        rep.update({"texels": int(idx.size), "new_texels": int((~had[idx]).sum())})
        return rep

    def painted_texmask(self):
        """(res, res) float mask of painted texels with a gutter, for context renders."""
        m = np.zeros((self.res, self.res), np.float64)
        m[self.valid] = (self.wsum > 0).astype(np.float64)
        _, (iy, ix) = ndimage.distance_transform_edt(~self.valid, return_indices=True)
        return m[iy, ix]

    def seam_delta(self):
        """Mean colour step across UV-adjacent painted texels whose best view differs."""
        img = np.zeros((self.res, self.res, 3))
        own = np.full((self.res, self.res), -1, np.int32)
        p = self.wsum > 0
        col = np.zeros((self.pos.shape[0], 3))
        col[p] = self.csum[p] / self.wsum[p, None]
        img[self.valid] = col
        own[self.valid] = np.where(p, self.owner, -1)
        out = []
        for a, b in (((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                     ((slice(1, None), slice(None)), (slice(None, -1), slice(None)))):
            oa, ob = own[a], own[b]
            m = (oa >= 0) & (ob >= 0) & (oa != ob)
            if m.any():
                out.append(np.abs(img[a][m] - img[b][m]).mean(1))
        return float(np.concatenate(out).mean()) if out else 0.0

    def save(self, path):
        np.savez_compressed(path, wsum=self.wsum, csum=self.csum.astype(np.float32), best=self.best,
                            owner=self.owner, seeable=self.seeable, views=self.views)

    def load(self, path):
        d = np.load(path)
        self.wsum, self.csum, self.best = d["wsum"], d["csum"].astype(np.float64), d["best"]
        self.owner, self.seeable, self.views = d["owner"], d["seeable"], int(d["views"])

    def coverage(self):
        painted = self.wsum > 0
        s = self.seeable if self.seeable.any() else np.ones_like(painted)
        return float((painted & s).sum() / max(1, s.sum()))

    def prior_colors(self, image: np.ndarray):
        """Per-texel colours of another texture on the same UV layout (e.g. the mesh's own)."""
        iy, ix = np.nonzero(self.valid)
        h, w = image.shape[:2]
        return sample_bilinear(image, (ix + 0.5) / self.res * w, (iy + 0.5) / self.res * h)

    def texture(self, fill=True, gutter=True, prior=None):
        """Painted colours; unpainted texels from prior (colour-matched to the painted ones) when
        given, else from the nearest painted surface (fill)."""
        n = self.pos.shape[0]
        col = np.zeros((n, 3))
        painted = self.wsum > 0
        col[painted] = self.csum[painted] / self.wsum[painted, None]
        if prior is not None and (~painted).any():
            p = prior.astype(np.float64)
            if painted.sum() > 2000:
                # one brightness gain/offset for all channels: a per-channel fit is dominated by
                # the main colours and tints the neutral greys (dark fabric turns olive)
                sq = np.percentile(p[painted].mean(1), [10, 50, 90])
                dq = np.percentile(col[painted].mean(1), [10, 50, 90])
                g = float(np.clip((dq[2] - dq[0]) / max(sq[2] - sq[0], 8.0), 0.6, 1.8))
                p = np.clip(p * g + (dq[1] - g * sq[1]), 0, 255)
            col[~painted] = p[~painted]
        elif fill and painted.any() and (~painted).any():
            tree = cKDTree(self.pos[painted])
            _, j = tree.query(self.pos[~painted], k=4)
            col[~painted] = col[painted][j].mean(1)
        tex = np.zeros((self.res, self.res, 3))
        tex[self.valid] = col
        if gutter:
            _, (iy, ix) = ndimage.distance_transform_edt(~self.valid, return_indices=True)
            tex = tex[iy, ix]
        return np.clip(tex, 0, 255).astype(np.uint8)

    def painted_mask_image(self):
        img = np.zeros((self.res, self.res), np.uint8)
        img[self.valid] = np.where(self.wsum > 0, 255, np.where(self.seeable, 80, 30))
        return img


def fit_color_transfer(src, dst, min_pairs=2000, gain=(0.85, 1.18), max_offset=25.0):
    """Per-channel gain/offset that maps src colours onto dst (same texels), from robust quantiles.

    None when too few texels overlap; "implausible" when the fit needs more than a small
    correction: then the view painted different content there, and bending all its colours
    toward the texture would spread the error rather than remove a tint.
    """
    if len(src) < min_pairs:
        return None
    sq = np.percentile(src, [10, 50, 90], axis=0)
    dq = np.percentile(dst, [10, 50, 90], axis=0)
    g = (dq[2] - dq[0]) / np.maximum(sq[2] - sq[0], 8.0)
    o = dq[1] - g * sq[1]
    if (g < gain[0]).any() or (g > gain[1]).any() or (np.abs(o) > max_offset).any():
        return "implausible"
    return g, o


def render_context(mesh: Mesh, cam: Camera, tex: np.ndarray, painted_tex: np.ndarray, mode="flat", grey=128,
                   min_area=400):
    """Render the current texture and mark the surface no view has painted yet.

    painted_tex: (res, res) float mask of painted texels (Accumulator.painted_texmask). Unpainted
    surface shows, by mode: "fill" the texture as given (the prior or nearest painted colour the
    caller baked into tex), "flat" a flat grey, "clay" clay shading, "magenta" a marker colour.
    Unpainted specks under min_area pixels show the nearest painted colour instead.

    Returns image, render mask, unpainted mask, the base values under the unpainted mask,
    triangle ids and depth.
    """
    tri, dep, bar = render_buffers(mesh, cam)
    m = tri >= 0
    img = np.empty((cam.height, cam.width, 3), np.uint8)
    img[:] = KEY
    t = tri[m]
    uv = (mesh.uv[mesh.f[t]] * bar[m][..., None]).sum(1)
    h, w = tex.shape[:2]
    ux, uy = uv[:, 0] * w, uv[:, 1] * h
    img[m] = np.clip(sample_bilinear(tex, ux, uy), 0, 255).astype(np.uint8)
    pw = sample_bilinear(painted_tex[..., None], ux, uy)[:, 0]
    unp = np.zeros_like(m)
    unp[m] = pw < 0.5
    if min_area and unp.any() and (m & ~unp).any():
        # specks of unpainted surface (edge slivers between views) are shown in the nearest
        # painted colour: the model sees clean context, the final fill colours those texels
        lab, k = ndimage.label(unp)
        area = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, k + 1))
        small = np.isin(lab, np.nonzero(area < min_area)[0] + 1)
        if small.any():
            _, (iy, ix) = ndimage.distance_transform_edt(~(m & ~unp), return_indices=True)
            img[small] = img[iy[small], ix[small]]
            unp &= ~small
    base = np.empty((cam.height, cam.width, 3))
    if mode == "clay":
        base[:] = np.clip(_shade(mesh, cam, tri) * 0.78 * 255, 0, 255)[..., None]
    elif mode == "magenta":
        base[:] = MARK
    elif mode == "fill":
        base[:] = img  # tex already carries the prior (or nearest-colour fill): show it as is
    else:
        base[:] = grey
    img[unp] = base[unp].astype(np.uint8)
    return img, m, unp, base, tri, dep


def painted_pixels(out: np.ndarray, base: np.ndarray, chroma_min=20, value_min=40, mark_min=90):
    """Pixels of a model output that no longer show the grey, clay or magenta they were given.

    base: the per-pixel values the guide showed (render_context's base). Grey or clay bases count
    a pixel as painted when it gained colour or moved in brightness; a magenta base when the pixel
    moved far from it and no longer leans toward its hue."""
    a = out.astype(np.float64)
    bchroma = base.max(2) - base.min(2)
    chroma = a.max(2) - a.min(2)
    grey_test = (chroma > chroma_min) | (np.abs(a.mean(2) - base.mean(2)) > value_min)
    # a pixel still leaning toward the marker hue (pink, purple) is the marker bleeding through
    lean = np.minimum(a[..., 0], a[..., 2]) - a[..., 1]
    mark_test = (np.linalg.norm(a - base, axis=2) > mark_min) & (lean < 40)
    return np.where(bchroma > 100, mark_test, grey_test)


def palette_has_key_hue(images, margin=25, share=0.02):
    """True when the concept art itself uses the key's hue (green over red and blue)."""
    hits = tot = 0
    for im in images:
        a = np.asarray(im.convert("RGB")).astype(np.int16)
        fg = a.max(2) > 24  # concept views sit on black
        g = a[..., 1] - np.maximum(a[..., 0], a[..., 2])
        hits += int((fg & (g > margin)).sum())
        tot += int(fg.sum())
    return hits > share * max(1, tot)


def despill(img: np.ndarray, mask: np.ndarray, allow=8):
    """Pull key-green that the model bled into the figure back to neutral (only inside mask)."""
    a = img.astype(np.int16).copy()
    cap = np.maximum(a[..., 0], a[..., 2]) + allow
    g = np.minimum(a[..., 1], cap)
    a[..., 1] = np.where(mask, g, a[..., 1])
    return a.clip(0, 255).astype(np.uint8)


def drift_share(out: np.ndarray, guide: np.ndarray, region: np.ndarray, lum=60):
    """Share of region pixels whose brightness the model changed by more than lum."""
    if not region.any():
        return 0.0
    d = np.abs(out.astype(np.float64).mean(2) - guide.astype(np.float64).mean(2))
    return float((d[region] > lum).mean())


def lighten_share(out: np.ndarray, guide: np.ndarray, region: np.ndarray, dark=70, lum=60):
    """Share of region pixels that were dark in the guide and came back much lighter.

    Catches the edit model's habit of turning dark hair or fabric silver in some views."""
    if not region.any():
        return 0.0
    g = guide.astype(np.float64).mean(2)
    d = out.astype(np.float64).mean(2) - g
    return float(((g < dark) & (d > lum))[region].mean())


def background_deviation(out: np.ndarray, render_mask: np.ndarray, margin=12):
    """Median distance (max channel) of the output's background from the key colour.

    A washed-out, pale key comes with a washed-out figure."""
    bg = ~ndimage.binary_dilation(render_mask, iterations=margin)
    if not bg.any():
        return 0.0
    return float(np.median(np.abs(out[bg].astype(np.int16) - KEY.astype(np.int16)).max(1)))


def dir_to_yaw_pitch(d):
    return float(np.degrees(np.arctan2(d[0], d[2]))) % 360, float(np.degrees(np.arcsin(np.clip(d[1], -1, 1))))


def yaw_pitch_to_dir(yaw, pitch):
    yw, pt = math.radians(yaw), math.radians(pitch)
    return np.array([math.sin(yw) * math.cos(pt), math.sin(pt), math.cos(yw) * math.cos(pt)])


def next_best_view(acc: "Accumulator", radius, fill, used, n=128, min_sep=20.0, pitch=(-60.0, 65.0),
                   size=256, zoom=True, min_frame=0.25, min_view_share=0.05):
    """Pick the orbit direction that sees the most unpainted seeable surface (cos-weighted).

    used: list of (yaw, pitch) already painted. Returns dict(yaw, pitch, gain, target, radius)
    or None. With zoom, the camera frames the unpainted surface it sees (never tighter than
    min_frame of the mesh's largest extent); target is None when the camera is not zoomed.
    """
    need = acc.seeable & (acc.wsum <= 0)
    if not need.any():
        return None
    U = [yaw_pitch_to_dir(*u) for u in used]
    cosmin = math.cos(math.radians(min_sep))
    best = None
    for d in fibonacci_dirs(n):
        yw, pt = dir_to_yaw_pitch(d)
        if not (pitch[0] <= pt <= pitch[1]) or any(float(d @ u) > cosmin for u in U):
            continue
        cam = Camera.orbit(acc.mesh.center, radius, yw, pt, size=size, fill=fill)
        vis, cos, _, _ = acc.visibility(cam)
        hit = vis & need
        if hit.sum() < min_view_share * max(1, vis.sum()):
            continue  # too little of what this camera sees is unpainted to be worth a paint job
        score = float((np.clip(cos[hit], 0, 1) ** 2).sum())
        if best is None or score > best[0]:
            best = (score, yw, pt, hit)
    if best is None or best[0] <= 0:
        return None
    score, yw, pt, hit = best
    out = {"yaw": round(yw, 1), "pitch": round(pt, 1), "gain": round(float(hit.sum() / max(1, acc.seeable.sum())), 4),
           "target": None, "radius": radius}
    ext3 = acc.mesh.v.max(0) - acc.mesh.v.min(0)
    if zoom and ext3.min() >= 0.15 * ext3.max():  # zoomed crops of thin meshes come back unrecognisable
        p = acc.pos[hit]
        lo, hi = np.percentile(p, 2, axis=0), np.percentile(p, 98, axis=0)
        ext = float(np.linalg.norm(hi - lo)) / 2
        full = float((acc.mesh.v.max(0) - acc.mesh.v.min(0)).max()) / 2
        r = max(ext, min_frame * full)
        if r < 0.7 * full:
            out.update({"target": ((lo + hi) / 2).tolist(), "radius": r})
    return out


def fibonacci_dirs(n):
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = math.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(th) * np.sin(phi), np.cos(phi), np.sin(th) * np.sin(phi)], 1)


# ----------------------------------------------------------------------------- test fixtures

def cube_mesh():
    """Unit cube centred at the origin, one UV cell per face (3x2 grid), outward winding."""
    v = np.array([[x, y, z] for x in (-.5, .5) for y in (-.5, .5) for z in (-.5, .5)], float)
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    V, UV, F = [], [], []
    for k, q in enumerate(faces):
        cx, cy = (k % 3) / 3, (k // 3) / 2
        base = len(V)
        for j, (du, dv) in zip(q, ((0.02, 0.02), (0.31, 0.02), (0.31, 0.48), (0.02, 0.48))):
            V.append(v[j])
            UV.append((cx + du, cy + dv))
        a, b, c = v[q[0]], v[q[1]], v[q[2]]
        if np.dot(np.cross(b - a, c - a), a) < 0:
            F += [(base, base + 2, base + 1), (base, base + 3, base + 2)]
        else:
            F += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    return Mesh(np.array(V), np.array(UV), np.array(F))


def write_glb(mesh: Mesh, image: Image.Image, path):
    """Write a minimal GLB: one primitive (POSITION, TEXCOORD_0, indices) and one material whose
    base colour is image. Enough for load_glb, glb_image and write_glb_basecolor."""
    png = io.BytesIO()
    image.convert("RGB").save(png, "PNG")
    pos = mesh.v.astype(np.float32)
    blobs = [pos.tobytes(), mesh.uv.astype(np.float32).tobytes(),
             mesh.f.astype(np.uint32).ravel().tobytes(), png.getvalue()]
    out, views = bytearray(), []
    for b in blobs:
        while len(out) % 4:
            out.append(0)
        views.append({"buffer": 0, "byteOffset": len(out), "byteLength": len(b)})
        out += b
    while len(out) % 4:
        out.append(0)
    js = {
        "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}]}],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0.0}}],
        "textures": [{"source": 0}], "images": [{"bufferView": 3, "mimeType": "image/png"}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3",
             "min": pos.min(0).tolist(), "max": pos.max(0).tolist()},
            {"bufferView": 1, "componentType": 5126, "count": len(pos), "type": "VEC2"},
            {"bufferView": 2, "componentType": 5125, "count": int(mesh.f.size), "type": "SCALAR"}],
        "bufferViews": views, "buffers": [{"byteLength": len(out)}],
    }
    jb = json.dumps(js, separators=(",", ":")).encode()
    jb += b" " * (-len(jb) % 4)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(out)))
        fh.write(struct.pack("<I4s", len(jb), b"JSON") + jb)
        fh.write(struct.pack("<I4s", len(out), b"BIN\x00") + bytes(out))


def edit_glb_json(path, fn, dst=None):
    """Test fixture: rewrite a GLB's JSON chunk with fn(js) (in place unless dst), keeping the binary chunk."""
    js, binc = _glb_chunks(open(path, "rb").read())
    fn(js)
    jb = json.dumps(js, separators=(",", ":")).encode()
    jb += b" " * (-len(jb) % 4)
    binc = bytes(binc) + b"\0" * (-len(binc) % 4)
    with open(dst or path, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(binc)))
        fh.write(struct.pack("<I4s", len(jb), b"JSON") + jb)
        fh.write(struct.pack("<I4s", len(binc), b"BIN\x00") + binc)


# ----------------------------------------------------------------------------- selftest

def selftest():
    """Synthetic checks on a cube and constructed arrays; no network, no model."""
    import tempfile
    import time
    t0 = time.time()
    results = {}

    def check(name, cond, detail=None):
        results[name] = bool(cond) if detail is None else {"pass": bool(cond), **detail}

    # 1. projection round trip: six views of a known texture rebuild it
    mesh = cube_mesh()
    res = 256
    yy, xx = np.mgrid[0:res, 0:res]
    truth = np.stack([(xx * 7) % 256, (yy * 5) % 256, ((xx + yy) * 3) % 256], -1).astype(np.uint8)
    acc = Accumulator(mesh, res)
    cams = [Camera.orbit(mesh.center, 0.87, yw, pt, size=256) for yw, pt in
            ((0, 0), (90, 0), (180, 0), (270, 0), (0, 89), (0, -89))]
    acc.mark_seeable(cams)
    for c in cams:
        img, m = render_texture(mesh, c, truth)
        acc.add_view(c, img, m)
    tex = acc.texture()
    err = float(np.abs(tex[acc.valid].astype(int) - truth[acc.valid].astype(int)).mean())
    cov = acc.coverage()
    check("round_trip", cov > 0.9 and err < 12, {"coverage": round(cov, 4), "mean_abs_err": round(err, 2)})

    # 2. GLB write / read / base-colour swap
    with tempfile.TemporaryDirectory() as td:
        a_p, b_p = f"{td}/a.glb", f"{td}/b.glb"
        write_glb(mesh, Image.fromarray(truth), a_p)
        m2 = load_glb(a_p)
        write_glb_basecolor(a_p, b_p, Image.fromarray(255 - truth))
        m3 = load_glb(b_p)
        swapped = np.asarray(glb_image(b_p))
        check("glb_io", np.allclose(m2.v, mesh.v) and np.allclose(m3.uv, mesh.uv)
              and (m3.f == mesh.f).all() and (swapped == 255 - truth).all())
        # a JPEG-declared source comes out declared as the PNG it now holds
        edit_glb_json(a_p, lambda js: js["images"][0].update(mimeType="image/jpeg"), f"{td}/j.glb")
        write_glb_basecolor(f"{td}/j.glb", f"{td}/j2.glb", Image.fromarray(truth))
        mime = _glb_chunks(open(f"{td}/j2.glb", "rb").read())[0]["images"][0].get("mimeType")
        check("glb_png_mime", mime == "image/png")
        # no base-colour texture, an external image, a texture shared with another slot: a new image is added
        cases = {"none": lambda js: js["materials"][0]["pbrMetallicRoughness"].pop("baseColorTexture"),
                 "uri": lambda js: js["images"][0].update(uri="base.png") or js["images"][0].pop("bufferView"),
                 "shared": lambda js: js["materials"][0].update(emissiveTexture={"index": 0})}
        ok_cases = {}
        for k, fn in cases.items():
            edit_glb_json(a_p, fn, f"{td}/{k}.glb")
            write_glb_basecolor(f"{td}/{k}.glb", f"{td}/{k}_out.glb", Image.fromarray(255 - truth))
            js4 = _glb_chunks(open(f"{td}/{k}_out.glb", "rb").read())[0]
            ok_cases[k] = ((np.asarray(glb_image(f"{td}/{k}_out.glb")) == 255 - truth).all()
                           and np.allclose(load_glb(f"{td}/{k}_out.glb").v, mesh.v)
                           and (k != "shared" or js4["materials"][0]["emissiveTexture"]["index"] == 0))
        check("glb_new_basecolor", all(ok_cases.values()), {k: bool(v) for k, v in ok_cases.items()})

    # 3. colour transfer: a small tint fits, a large offset is implausible, too few pairs is None
    rng = np.random.default_rng(0)
    src = rng.uniform(30, 220, (5000, 3))
    fit = fit_color_transfer(src, src * 1.05 + 4)
    sane = isinstance(fit, tuple) and np.allclose(fit[0], 1.05, atol=0.03) and np.allclose(fit[1], 4, atol=4)
    check("color_transfer", sane and fit_color_transfer(src, np.clip(src + 60, 0, 255)) == "implausible"
          and fit_color_transfer(src[:100], src[:100]) is None)

    # 4. gate measures on constructed arrays
    H = W = 64
    grey = np.full((H, W, 3), 128.0)
    out = np.full((H, W, 3), 128, np.uint8)
    out[:, :32] = (200, 120, 60)  # left half gained colour
    pp = painted_pixels(out, grey)
    mag = np.empty((H, W, 3))
    mag[:] = MARK
    out_m = np.empty((H, W, 3), np.uint8)
    out_m[:] = (240, 20, 230)       # still magenta
    out_m[:, :32] = (200, 150, 90)  # repainted
    pm = painted_pixels(out_m, mag)
    check("painted_pixels", pp[:, :32].all() and not pp[:, 32:].any() and pm[:, :32].all() and not pm[:, 32:].any())

    region = np.ones((H, W), bool)
    g_dark = np.full((H, W, 3), 30, np.uint8)
    o_light = g_dark.copy()
    o_light[:H // 2] = 160
    check("lighten_drift", abs(lighten_share(o_light, g_dark, region) - 0.5) < 1e-6
          and abs(drift_share(o_light, g_dark, region) - 0.5) < 1e-6
          and drift_share(g_dark, g_dark, region) == 0.0)

    rmask = np.zeros((128, 128), bool)
    rmask[40:88, 40:88] = True
    clean = np.empty((128, 128, 3), np.uint8)
    clean[:] = KEY
    pale = clean.copy()
    pale[:] = (190, 255, 190)
    check("background_deviation", background_deviation(clean, rmask) == 0.0
          and abs(background_deviation(pale, rmask) - 190) < 1e-6)

    collage = rmask.copy()
    collage[40:88, 100:124] = True  # a second figure beside the first
    check("silhouette_edge_p90", silhouette_edge_p90(rmask, rmask) == 0.0
          and silhouette_edge_p90(rmask, collage) > 24)

    spill = np.zeros((4, 4, 3), np.uint8)
    spill[:] = (100, 200, 90)
    dm = np.zeros((4, 4), bool)
    dm[:2] = True
    ds = despill(spill, dm)
    check("despill", (ds[:2, :, 1] == 108).all() and (ds[2:, :, 1] == 200).all()
          and (ds[..., 0] == 100).all() and (ds[..., 2] == 90).all())

    # 5. context render and next best view after painting the front face only
    acc = Accumulator(mesh, res)
    ring = [Camera.orbit(mesh.center, 0.87, yw, pt, size=128)
            for yw, pt in ((0, 0), (90, 0), (180, 0), (270, 0), (0, 60), (0, -60))]
    acc.mark_seeable(ring)
    front = Camera.orbit(mesh.center, 0.87, 0, 0, size=256)
    img, m = render_texture(mesh, front, truth)
    acc.add_view(front, img, m)
    texc = acc.texture(fill=False, gutter=True)
    ptm = acc.painted_texmask()
    _, m0, unp0, _, _, _ = render_context(mesh, front, texc, ptm, "flat")
    side = Camera.orbit(mesh.center, 0.87, 90, 0, size=256)
    img1, m1, unp1, _, _, _ = render_context(mesh, side, texc, ptm, "flat")
    # the painted face keeps only its outline band unpainted (edge falloff); the side is all unpainted
    check("render_context", unp0.sum() < 0.15 * m0.sum() and unp1.sum() > 0.9 * m1.sum()
          and (img1[unp1] == 128).all())

    nb = next_best_view(acc, 0.5, 0.9, [(0.0, 0.0)], n=64, size=128)
    ok = nb is not None and nb["gain"] > 0
    if ok:
        d = yaw_pitch_to_dir(nb["yaw"], nb["pitch"])
        ok = float(d @ np.array([0.0, 0.0, 1.0])) < math.cos(math.radians(45))
    nz = next_best_view(acc, 0.5, 0.9, [(0.0, 0.0)], n=64, size=128, zoom=False)
    ok = ok and nz is not None and nz["target"] is None and nz["radius"] == 0.5  # unzoomed: no target
    check("next_best_view", ok, {"view": None if nb is None else [nb["yaw"], nb["pitch"], nb["gain"]]})

    passed = all(v if isinstance(v, bool) else v["pass"] for v in results.values())
    print(json.dumps({"checks": results, "seconds": round(time.time() - t0, 1), "pass": passed}))
    return 0 if passed else 2


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if args in (["selftest"], ["--selftest"]):
        sys.exit(selftest())
    if args in ([], ["-h"], ["--help"]):
        print(__doc__)
        sys.exit(0)
    print(f"usage: mvtex.py [--selftest]  (unknown arguments: {' '.join(args)})", file=sys.stderr)
    sys.exit(1)
