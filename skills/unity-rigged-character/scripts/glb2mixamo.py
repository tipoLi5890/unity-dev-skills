#!/usr/bin/env python3
"""Convert a GLB into a Mixamo-ready OBJ and pull out its embedded textures.

usage:
    glb2mixamo.py <input.glb> [output.obj] [--height=170] [--textures=DIR] [--keep-stray]

Stdlib only - no Blender, no assimp, no pip install.

Why this exists: Mixamo accepts FBX / OBJ / ZIP and **not** glb, while most
image-to-3D services hand you glb. `gltf-transform` cannot convert out of the
glTF family, and Blender or assimp are heavy installs for one format change.
glTF is a documented JSON + binary container, so reading it directly is short.

Two things it does beyond the format change:

  1. The same humanoid sanity checks as fbx2mixamo.py - connected-shell count,
     axis roles, arm-span/height and depth/height ratios - so a model that will
     defeat the auto-rigger is caught BEFORE the upload, not after it stalls.
  2. Extracts the embedded maps, with --textures=DIR; without the flag it only
     lists them. They are dead weight for the auto-rigger, but Mixamo returns no
     materials at all, so they have to be reattached in the engine afterwards -
     and they only exist inside this original file.

Note on the metallicRoughness map: glTF packs occlusion/roughness/metallic into
one image (R/G/B). Unity URP wants metallic in RGB and SMOOTHNESS in alpha, and
smoothness is 1 - roughness. That repack is an engine-side step; this tool just
gets the source image out intact.
"""
import json, struct, sys, os

COMPONENT = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2),
             5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}
NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}
MIME_EXT = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}


# ---------------------------------------------------------------- GLB reader

def parse_glb(path):
    """Return (gltf_json, binary_chunk). Also accepts a .gltf with an embedded buffer."""
    with open(path, 'rb') as fh:
        data = fh.read()

    if data[:4] != b'glTF':
        # Plain .gltf - JSON only, buffers must be data URIs (rare but cheap to allow).
        return json.loads(data.decode('utf-8')), b''

    # Header is magic(4) + version(4) + totalLength(4); magic was checked above.
    version, _total = struct.unpack_from('<II', data, 4)
    if version != 2:
        sys.exit('glb2mixamo: only glTF 2.0 is supported (found %d)' % version)

    gltf, binary, off = None, b'', 12
    while off < len(data):
        clen, ctype = struct.unpack_from('<II', data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:      # 'JSON'
            gltf = json.loads(chunk.decode('utf-8'))
        elif ctype == 0x004E4942:    # 'BIN\0'
            binary = chunk
        off += 8 + clen + (-clen % 4)

    if gltf is None:
        sys.exit('glb2mixamo: no JSON chunk found - file is not a valid GLB')
    return gltf, binary


def read_accessor(gltf, binary, index):
    """Decode one accessor into a list of tuples, honouring interleaved byteStride."""
    acc = gltf['accessors'][index]
    fmt, size = COMPONENT[acc['componentType']]
    n = NCOMP[acc['type']]

    if 'bufferView' not in acc:      # sparse-only accessor: treat as zeros
        return [(0.0,) * n] * acc['count']

    view = gltf['bufferViews'][acc['bufferView']]
    base = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
    stride = view.get('byteStride') or size * n
    layout = '<' + fmt * n

    return [struct.unpack_from(layout, binary, base + i * stride)
            for i in range(acc['count'])]


def extract_images(gltf, binary, outdir):
    """Write embedded images out under their glTF names. Returns [(name, slot, bytes)]."""
    slot_of = {}
    for mat in gltf.get('materials', []):
        pbr = mat.get('pbrMetallicRoughness', {})
        for key, label in (('baseColorTexture', 'baseColor'),
                           ('metallicRoughnessTexture', 'metallicRoughness')):
            if key in pbr:
                slot_of[pbr[key]['index']] = label
        for key, label in (('normalTexture', 'normal'),
                           ('occlusionTexture', 'occlusion'),
                           ('emissiveTexture', 'emissive')):
            if key in mat:
                slot_of[mat[key]['index']] = label

    source_slot = {}
    for tex_index, tex in enumerate(gltf.get('textures', [])):
        if 'source' in tex and tex_index in slot_of:
            source_slot[tex['source']] = slot_of[tex_index]

    written = []
    for i, img in enumerate(gltf.get('images', [])):
        if 'bufferView' not in img:
            continue                      # external URI - already a loose file
        view = gltf['bufferViews'][img['bufferView']]
        start = view.get('byteOffset', 0)
        blob = binary[start: start + view['byteLength']]

        slot = source_slot.get(i, 'image%d' % i)
        name = slot + MIME_EXT.get(img.get('mimeType', ''), '.bin')
        if outdir:
            with open(os.path.join(outdir, name), 'wb') as fh:
                fh.write(blob)
        written.append((name, slot, len(blob)))
    return written


# ------------------------------------------------------------------ topology

def weld_ids(V):
    """
    Map every vertex to a representative sharing its exact position.

    This is essential for glTF and has no equivalent in the FBX path. FBX keeps a
    de-duplicated vertex array and indexes UVs separately, but glTF binds all
    attributes to one vertex, so **every UV seam splits a vertex in two**. Run
    connectivity on raw indices and a perfectly solid body reports as thousands of
    fragments - which then trips the stray-shell filter into deleting real anatomy.
    Split vertices are still what gets written to the OBJ (they carry the UVs);
    welding is only for reasoning about topology.
    """
    seen, ids = {}, []
    for p in V:
        ids.append(seen.setdefault(p, len(seen)))
    return ids, len(seen)


def components(nverts, faces, wid, nweld):
    """Connected vertex groups, welded by position. A humanoid is one shell plus noise."""
    adj = [[] for _ in range(nweld)]
    for f in faces:
        for i in range(len(f)):
            a, b = wid[f[i]], wid[f[(i + 1) % len(f)]]
            adj[a].append(b); adj[b].append(a)

    seen, groups = [False] * nweld, []
    for s in range(nweld):
        if seen[s]:
            continue
        stack, group = [s], []
        seen[s] = True
        while stack:
            u = stack.pop(); group.append(u)
            for w in adj[u]:
                if not seen[w]:
                    seen[w] = True; stack.append(w)
        groups.append(group)

    # Expand welded groups back to original vertex indices, O(n) not O(n·groups).
    gid = [0] * nweld
    for k, g in enumerate(groups):
        for w in g:
            gid[w] = k
    out = [[] for _ in groups]
    for i in range(nverts):
        out[gid[wid[i]]].append(i)
    out.sort(key=len, reverse=True)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    if '-h' in sys.argv[1:] or '--help' in flags:
        print(__doc__); sys.exit(0)
    if not args:
        print(__doc__); sys.exit(1)

    src = args[0]
    dst = args[1] if len(args) > 1 else os.path.splitext(src)[0] + '_mixamo.obj'
    height, texdir, keep_stray = 170.0, None, '--keep-stray' in flags

    for f in flags:
        if f.startswith('--height='):
            height = float(f.split('=', 1)[1])
        elif f.startswith('--textures='):
            texdir = f.split('=', 1)[1]
        elif f not in ('--keep-stray',):
            print('unknown flag %s' % f); sys.exit(1)

    gltf, binary = parse_glb(src)
    print('=== %s ===' % os.path.basename(src))
    print('glTF 2.0, %.1f MB, generator: %s'
          % (os.path.getsize(src) / 1048576, gltf.get('asset', {}).get('generator', '?')))

    # A pre-existing skeleton is fatal: Mixamo rejects rigged uploads outright.
    if gltf.get('skins'):
        print('existing rig: %d skin(s)  <- Mixamo REJECTS pre-rigged files' % len(gltf['skins']))
    else:
        print('existing rig: none (correct for auto-rig)')
    if gltf.get('animations'):
        print('animations: %d  <- strip these before rigging' % len(gltf['animations']))

    # -- geometry: merge every primitive of every mesh into one vertex/face soup
    V, UV, faces = [], [], []
    for mesh in gltf.get('meshes', []):
        for prim in mesh.get('primitives', []):
            attrs = prim.get('attributes', {})
            if 'POSITION' not in attrs:
                continue
            offset = len(V)
            V.extend(read_accessor(gltf, binary, attrs['POSITION']))

            if 'TEXCOORD_0' in attrs:
                UV.extend(read_accessor(gltf, binary, attrs['TEXCOORD_0']))
            else:
                UV.extend([(0.0, 0.0)] * (len(V) - offset))

            if 'indices' in prim:
                idx = [i[0] for i in read_accessor(gltf, binary, prim['indices'])]
            else:
                idx = list(range(len(V) - offset))
            faces.extend([(idx[i] + offset, idx[i + 1] + offset, idx[i + 2] + offset)
                          for i in range(0, len(idx) - 2, 3)])

    if not V:
        sys.exit('glb2mixamo: no POSITION data found')
    has_uv = any(u != (0.0, 0.0) for u in UV)
    print('%d verts, %d tris, UV %s' % (len(V), len(faces), 'yes' if has_uv else 'MISSING'))

    wid, nweld = weld_ids(V)
    comps = components(len(V), faces, wid, nweld)
    body = comps[0]
    print('connected shells: %d (%d verts welded to %d positions)'
          % (len(comps), len(V), nweld))

    # -- axis roles, read off the BODY shell only. A stray shard would otherwise
    #    blow up one extent and swap the roles.
    ext = [max(V[j][i] for j in body) - min(V[j][i] for j in body) for i in range(3)]
    print('body bbox  X %.3f  Y %.3f  Z %.3f' % tuple(ext))
    order = sorted(range(3), key=lambda i: ext[i], reverse=True)
    h_ax, a_ax, d_ax = order[0], order[1], order[2]
    print('axis roles: height=%s  arm-span=%s  depth=%s'
          % ('XYZ'[h_ax], 'XYZ'[a_ax], 'XYZ'[d_ax]))

    # Facing: toes reach further forward than heels, so the feet centroid sits on
    # the front side of the body centre along the depth axis.
    hi = max(V[j][h_ax] for j in body); lo = min(V[j][h_ax] for j in body)
    feet = [V[j] for j in body if V[j][h_ax] < lo + 0.12 * (hi - lo)]
    body_c = (min(V[j][d_ax] for j in body) + max(V[j][d_ax] for j in body)) / 2
    feet_c = sum(p[d_ax] for p in feet) / len(feet)
    sz = 1.0 if feet_c >= body_c else -1.0
    print('facing: toes point %s%s' % ('+' if sz > 0 else '-', 'XYZ'[d_ax]))

    # Signed permutation (arm-span->X, height->Y, depth->Z) forced to determinant
    # +1, so the character is rotated and never mirrored.
    perm, psign = [a_ax, h_ax, d_ax], 1
    for i in range(3):
        for j in range(i + 1, 3):
            if perm[i] > perm[j]:
                psign = -psign
    sx = 1.0 if psign * sz > 0 else -1.0
    P = [(p[a_ax] * sx, p[h_ax], p[d_ax] * sz) for p in V]

    # -- drop stray shells that out-span the body on any axis
    span = max(P[j][0] for j in body) - min(P[j][0] for j in body)
    depth = max(P[j][2] for j in body) - min(P[j][2] for j in body)
    drop = set()
    for c in comps[1:]:
        xs = [P[j][0] for j in c]; zs = [P[j][2] for j in c]
        if not keep_stray and (max(xs) - min(xs) > span or max(zs) - min(zs) > depth):
            drop |= set(c)
    for i, c in enumerate(comps[:6]):
        tag = ' <- STRAY, removing' if set(c) & drop else (' <- body' if i == 0 else '')
        print('  shell %2d: %6d verts%s' % (i, len(c), tag))
    if len(comps) > 6:
        print('  ... %d more small shells (kept)' % (len(comps) - 6))

    keep = [i for i in range(len(P)) if i not in drop]
    remap = {old: new for new, old in enumerate(keep)}

    # -- scale to the requested height, feet on the origin, centred horizontally
    ys = [P[i][1] for i in keep]
    scale = height / (max(ys) - min(ys))
    xs = [P[i][0] for i in keep]; zs = [P[i][2] for i in keep]
    cx = (min(xs) + max(xs)) / 2 * scale
    cz = (min(zs) + max(zs)) / 2 * scale
    floor = min(ys) * scale
    out_v = [((P[i][0] * scale) - cx, (P[i][1] * scale) - floor, (P[i][2] * scale) - cz)
             for i in keep]

    fh_span = max(v[0] for v in out_v) - min(v[0] for v in out_v)
    fh_depth = max(v[2] for v in out_v) - min(v[2] for v in out_v)
    print('result: height %.1f  arm-span/height %.2f  depth/height %.2f'
          % (height, fh_span / height, fh_depth / height))
    if not 0.7 <= fh_span / height <= 1.1:
        print('  WARNING arm-span ratio outside 0.7-1.1 - is this really a T-pose?')
    if fh_depth / height > 0.35:
        print('  WARNING depth ratio > 0.35 - stray geometry may still be inflating the bbox')

    # -- write OBJ. glTF texture V runs top-down, OBJ/Unity run bottom-up, so V flips.
    with open(dst, 'w') as fh:
        fh.write('# %s -> Mixamo-ready OBJ (glb2mixamo.py)\n' % os.path.basename(src))
        for v in out_v:
            fh.write('v %.6f %.6f %.6f\n' % v)
        if has_uv:
            for i in keep:
                fh.write('vt %.6f %.6f\n' % (UV[i][0], 1.0 - UV[i][1]))
        for f in faces:
            if f[0] in drop or f[1] in drop or f[2] in drop:
                continue
            a, b, c = remap[f[0]] + 1, remap[f[1]] + 1, remap[f[2]] + 1
            fh.write('f %d/%d %d/%d %d/%d\n' % (a, a, b, b, c, c) if has_uv
                     else 'f %d %d %d\n' % (a, b, c))
    print('wrote %s  (%.2f MB, %d verts)' % (dst, os.path.getsize(dst) / 1048576, len(keep)))

    # -- textures
    if texdir:
        os.makedirs(texdir, exist_ok=True)
    imgs = extract_images(gltf, binary, texdir)
    if imgs:
        print('embedded textures%s:' % ('' if texdir else ' (pass --textures=DIR to write them)'))
        for name, slot, size in imgs:
            print('  %-28s %-18s %.2f MB' % (name, slot, size / 1048576))


if __name__ == '__main__':
    main()
