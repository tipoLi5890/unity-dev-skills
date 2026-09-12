#!/usr/bin/env python3
"""Diagnose an FBX for Mixamo auto-rigger compatibility and emit a clean OBJ.

usage:
    fbx2mixamo.py <input.fbx> [output.obj] [--height=170] [--keep-spike]

Stdlib only - no Blender, no FBX SDK, no pip install.

Why this exists: AI image-to-3D output (Tripo / Hunyuan3D / Meshy / Rodin, then
round-tripped through Blender) reliably breaks Mixamo's uploader, which stalls
mid-progress-bar instead of reporting an error. Three causes, all handled here:

  1. Stray shells. A disconnected sliver - often a ground spike running the whole
     depth of the scene - inflates the bounding box, so the rigger cannot find a
     humanoid. Shells that out-span the body are dropped (--keep-spike disables).
  2. Wrong axes. Geometry is authored Z-up and may face any axis, while the FBX
     header claims Y-up. Axis roles are inferred from the body shell's extents
     (height > arm-span > depth) and facing from the toes, then baked into a
     signed permutation with determinant +1 so the mesh rotates, never mirrors.
  3. Embedded textures. PBR maps can be >90% of the file and are useless to the
     auto-rigger. OBJ output carries UVs only, so materials can be reattached in
     Unity after Mixamo returns the rigged FBX.

Output is a T-posed, Y-up, origin-footed OBJ scaled to --height units. The ASCII
front/side views printed at the end are the sanity check - confirm a T-pose and a
plausible arm-span/height (~0.8-1.0) and depth/height (~0.2-0.3) before uploading.
"""
import struct, zlib, sys, os, re

# ---------------------------------------------------------------- FBX reader

def parse_fbx(path):
    data = open(path, 'rb').read()
    ver = struct.unpack('<I', data[23:27])[0]
    arrays, scalars = {}, []

    def read_prop(d, p):
        t = chr(d[p]); p += 1
        if t == 'Y': return None, p+2
        if t == 'C': return None, p+1
        if t == 'I': return struct.unpack('<i', d[p:p+4])[0], p+4
        if t == 'F': return None, p+4
        if t == 'D': return struct.unpack('<d', d[p:p+8])[0], p+8
        if t == 'L': return struct.unpack('<q', d[p:p+8])[0], p+8
        if t in 'SR':
            n = struct.unpack('<I', d[p:p+4])[0]; p += 4
            v = d[p:p+n]; p += n
            return (v.decode('utf-8', 'replace') if t == 'S' else None), p
        if t in 'fdlib':
            cnt, enc, cl = struct.unpack('<III', d[p:p+12]); p += 12
            raw = d[p:p+cl]; p += cl
            if enc == 1: raw = zlib.decompress(raw)
            fmt = {'f':'f','d':'d','l':'q','i':'i','b':'b'}[t]
            n = min(cnt, len(raw)//struct.calcsize(fmt))
            return ('ARR', struct.unpack('<%d%s' % (n, fmt), raw[:n*struct.calcsize(fmt)])), p
        raise ValueError('unknown property type %r' % t)

    def read_node(d, p):
        if ver >= 7500:
            end, nprops, _ = struct.unpack('<QQQ', d[p:p+24]); p += 24
            nlen = d[p]; p += 1; zero = 25
        else:
            end, nprops, _ = struct.unpack('<III', d[p:p+12]); p += 12
            nlen = d[p]; p += 1; zero = 13
        if end == 0: return None, p
        name = d[p:p+nlen].decode('utf-8', 'replace'); p += nlen
        props = []
        for _ in range(nprops):
            v, p = read_prop(d, p)
            props.append(v)
        for pr in props:
            if isinstance(pr, tuple) and pr and pr[0] == 'ARR':
                arrays.setdefault(name, []).append(pr[1])
        if name in ('P', 'Property70') and props and isinstance(props[0], str):
            scalars.append(props)
        while p < end - zero:
            c, p = read_node(d, p)
            if c is None: break
        return name, end

    pos = 27
    while pos < len(data) - 30:
        n, pos = read_node(data, pos)
        if n is None: break
    return data, ver, arrays, scalars


def components(nverts, faces):
    adj = [[] for _ in range(nverts)]
    for f in faces:
        for i in range(len(f)):
            a, b = f[i][0], f[(i+1) % len(f)][0]
            adj[a].append(b); adj[b].append(a)
    seen = [False]*nverts; out = []
    for s in range(nverts):
        if seen[s]: continue
        st = [s]; seen[s] = True; c = []
        while st:
            u = st.pop(); c.append(u)
            for w in adj[u]:
                if not seen[w]: seen[w] = True; st.append(w)
        out.append(c)
    out.sort(key=len, reverse=True)
    return out


def main():
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    flags = [x for x in sys.argv[1:] if x.startswith('--')]
    if '-h' in sys.argv[1:] or '--help' in flags:
        print(__doc__)
        sys.exit(0)
    if not a:
        print(__doc__)
        sys.exit(1)
    src = a[0]
    dst = a[1] if len(a) > 1 else os.path.splitext(src)[0] + '_mixamo.obj'
    height = 170.0
    for f in flags:
        if f.startswith('--height='):
            height = float(f.split('=', 1)[1])
        elif f not in ('--keep-spike',):
            print('unknown flag %s' % f); sys.exit(1)
    keep_spike = '--keep-spike' in flags

    data, ver, arrays, scalars = parse_fbx(src)
    print('=== %s ===' % os.path.basename(src))
    print('FBX version %d, %.1f MB' % (ver, len(data)/1048576))

    pngs = len(re.findall(re.escape(b'\x89PNG\r\n\x1a\n'), data))
    jpgs = len(re.findall(re.escape(b'\xff\xd8\xff'), data))
    if pngs or jpgs:
        print('embedded images: %d PNG, ~%d JPEG  <- dead weight for Mixamo' % (pngs, jpgs))

    # Skeleton nodes carry no array properties, so they never appear in `arrays` -
    # scan the raw bytes instead. Getting this wrong matters: Mixamo REJECTS a file
    # that already has a rig, so a false "none" sends you into a failing upload.
    rig = {k.decode(): data.count(k) for k in (b'LimbNode', b'Deformer', b'Cluster')}
    if any(rig.values()):
        print('existing rig: %s  <- Mixamo rejects pre-rigged files'
              % ', '.join('%s x%d' % kv for kv in rig.items() if kv[1]))
    else:
        print('existing rig: none (correct for auto-rig)')

    vs = arrays['Vertices'][0]
    pvi = arrays['PolygonVertexIndex'][0]
    uv = arrays.get('UV', [[]])[0]
    uvi = arrays.get('UVIndex', [[]])[0]
    has_uv = bool(uv) and len(uvi) == len(pvi)

    V_raw = [(vs[i], vs[i+1], vs[i+2]) for i in range(0, len(vs), 3)]

    faces, cur = [], []
    for k, idx in enumerate(pvi):
        last = idx < 0
        cur.append((~idx if last else idx, uvi[k] if has_uv else 0))
        if last:
            faces.append(cur); cur = []
    ngon = {}
    for f in faces: ngon[len(f)] = ngon.get(len(f), 0) + 1
    print('%d verts, %d faces %s, UV %s' % (
        len(V_raw), len(faces), dict(sorted(ngon.items())), 'yes' if has_uv else 'MISSING'))

    comps = components(len(V_raw), faces)
    print('connected shells: %d' % len(comps))
    body = comps[0]

    # Axis roles are read off the BODY shell only - a stray spike would otherwise
    # blow up one extent and swap the roles.
    ext = [max(V_raw[j][i] for j in body) - min(V_raw[j][i] for j in body) for i in range(3)]
    print('body bbox  X %.3f  Y %.3f  Z %.3f' % tuple(ext))

    # For a T/A-posed humanoid the three extents rank: height > arm-span > depth.
    order = sorted(range(3), key=lambda i: ext[i], reverse=True)
    h_ax, a_ax, d_ax = order[0], order[1], order[2]
    print('axis roles: height=%s  arm-span=%s  depth=%s'
          % ('XYZ'[h_ax], 'XYZ'[a_ax], 'XYZ'[d_ax]))

    # Facing: toes stick out further than heels, so the feet's centroid sits on
    # the front side of the body centre along the depth axis.
    hi = max(V_raw[j][h_ax] for j in body); lo = min(V_raw[j][h_ax] for j in body)
    feet = [V_raw[j] for j in body if V_raw[j][h_ax] < lo + 0.12*(hi-lo)]
    body_c = (min(V_raw[j][d_ax] for j in body) + max(V_raw[j][d_ax] for j in body)) / 2
    feet_c = sum(p[d_ax] for p in feet) / len(feet)
    sz = 1.0 if feet_c >= body_c else -1.0
    print('facing: toes point %s%s' % ('+' if sz > 0 else '-', 'XYZ'[d_ax]))

    # Build a signed permutation (arm-span->X, height->Y, depth->Z) and force
    # determinant +1 so the character is rotated, never mirrored.
    perm = [a_ax, h_ax, d_ax]
    psign = 1
    for i in range(3):
        for j in range(i+1, 3):
            if perm[i] > perm[j]: psign = -psign
    sy = 1.0
    sx = 1.0 if psign * sy * sz > 0 else -1.0
    V = [(p[a_ax]*sx, p[h_ax]*sy, p[d_ax]*sz) for p in V_raw]

    depth = max(V[j][2] for j in body) - min(V[j][2] for j in body)
    span = max(V[j][0] for j in body) - min(V[j][0] for j in body)
    drop = set()
    for c in comps[1:]:
        zs = [V[j][2] for j in c]; xs = [V[j][0] for j in c]
        if not keep_spike and (max(zs)-min(zs) > depth or max(xs)-min(xs) > span):
            drop |= set(c)
    for i, c in enumerate(comps[:6]):
        tag = ' <- STRAY, removing' if set(c) & drop else (' <- body' if i == 0 else '')
        print('  shell %2d: %5d verts%s' % (i, len(c), tag))
    if len(comps) > 6:
        print('  ... %d more small shells (kept)' % (len(comps)-6))

    keep = [f for f in faces if not any(v in drop for v, _ in f)]
    used_v, used_t = {}, {}
    for f in keep:
        for v, t in f:
            used_v.setdefault(v, len(used_v))
            if has_uv: used_t.setdefault(t, len(used_t))

    NV = [None]*len(used_v)
    for o, n in used_v.items(): NV[n] = V[o]
    NT = []
    if has_uv:
        NT = [None]*len(used_t)
        for o, n in used_t.items(): NT[n] = (uv[o*2], uv[o*2+1])

    ymin = min(p[1] for p in NV); ymax = max(p[1] for p in NV)
    s = height / (ymax - ymin)
    cx = (min(p[0] for p in NV) + max(p[0] for p in NV)) / 2
    cz = (min(p[2] for p in NV) + max(p[2] for p in NV)) / 2
    NV = [((p[0]-cx)*s, (p[1]-ymin)*s, (p[2]-cz)*s) for p in NV]

    out = ['# cleaned for Mixamo auto-rigger from %s' % os.path.basename(src),
           '# T-pose check below; Y-up, feet on origin, no embedded textures']
    out += ['v %.6f %.6f %.6f' % p for p in NV]
    out += ['vt %.6f %.6f' % t for t in NT]
    out.append('g character')
    for f in keep:
        if has_uv:
            out.append('f ' + ' '.join('%d/%d' % (used_v[v]+1, used_t[t]+1) for v, t in f))
        else:
            out.append('f ' + ' '.join(str(used_v[v]+1) for v, _ in f))
    open(dst, 'w').write('\n'.join(out) + '\n')

    fx = max(p[0] for p in NV)-min(p[0] for p in NV)
    fz = max(p[2] for p in NV)-min(p[2] for p in NV)
    print('removed %d stray verts / %d faces' % (len(drop), len(faces)-len(keep)))
    print('OUT %s  (%d KB)' % (dst, os.path.getsize(dst)//1024))
    print('final bbox  X %.1f  Y %.1f  Z %.1f  (arm-span/height %.2f, depth/height %.2f)'
          % (fx, height, fz, fx/height, fz/height))
    if fz/height > 0.4:
        print('  WARNING: still deep for a T-pose - check the side view')
    return NV


if __name__ == '__main__':
    NV = main()
    # quick ASCII front/side check
    H = 34
    for title, ax in (('FRONT (X across)', 0), ('SIDE (Z across)', 2)):
        xs = [p[ax] for p in NV]; ys = [p[1] for p in NV]
        x0, y0 = min(xs), min(ys)
        sc = (max(ys)-y0)/H
        W = int((max(xs)-x0)/(sc/2))+2
        g = [[' ']*W for _ in range(H+1)]
        for x, y in zip(xs, ys):
            cx2 = int((x-x0)/(sc/2)); cy = H-int((y-y0)/sc)
            if 0 <= cx2 < W and 0 <= cy <= H: g[cy][cx2] = '#'
        print('\n--- %s ---' % title)
        for r in g: print(''.join(r).rstrip())
