#!/usr/bin/env python3
"""Extract embedded textures from an FBX, keeping their original file names.

usage:
    fbx_textures.py <input.fbx> [outdir]

Stdlib only. Mixamo strips materials, so after the auto-rigger returns a rigged
FBX the maps have to be reattached in Unity by hand - this pulls them out of the
ORIGINAL export so you know which map is which.

Why not just carve the PNG/JPEG byte ranges out of the file: that gives you
tex0..tex3 in storage order with no idea which is normal and which is roughness,
and guessing from file size is a coin flip on a character whose metallic map is
nearly flat. FBX stores each image in a Video node next to a RelativeFilename,
so the real names ("texture_normal.png") are right there - this reads that
pairing instead.
"""
import struct, zlib, sys, os


def read_prop(d, p):
    """Returns (value, new_pos). Raw ('R') stays bytes - that's the image data."""
    t = chr(d[p]); p += 1
    if t == 'Y': return None, p + 2
    if t == 'C': return None, p + 1
    if t == 'I': return struct.unpack('<i', d[p:p+4])[0], p + 4
    if t == 'F': return None, p + 4
    if t == 'D': return struct.unpack('<d', d[p:p+8])[0], p + 8
    if t == 'L': return struct.unpack('<q', d[p:p+8])[0], p + 8
    if t in 'SR':
        n = struct.unpack('<I', d[p:p+4])[0]; p += 4
        v = d[p:p+n]; p += n
        return (v.decode('utf-8', 'replace') if t == 'S' else v), p
    if t in 'fdlib':
        cnt, enc, cl = struct.unpack('<III', d[p:p+12]); p += 12
        p += cl
        return None, p
    raise ValueError('unknown property type %r' % t)


def read_node(d, p, ver):
    if ver >= 7500:
        end, nprops, _ = struct.unpack('<QQQ', d[p:p+24]); p += 24
        nlen = d[p]; p += 1; zero = 25
    else:
        end, nprops, _ = struct.unpack('<III', d[p:p+12]); p += 12
        nlen = d[p]; p += 1; zero = 13
    if end == 0:
        return None, p
    name = d[p:p+nlen].decode('utf-8', 'replace'); p += nlen
    props = []
    for _ in range(nprops):
        v, p = read_prop(d, p)
        props.append(v)
    kids = []
    while p < end - zero:
        c, p = read_node(d, p, ver)
        if c is None: break
        kids.append(c)
    return (name, props, kids), end


def walk(node, want, out):
    name, props, kids = node
    if name == want:
        out.append(node)
    for k in kids:
        walk(k, want, out)


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        return 0
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + '_textures'

    data = open(src, 'rb').read()
    ver = struct.unpack('<I', data[23:27])[0]
    roots, pos = [], 27
    while pos < len(data) - 30:
        n, pos = read_node(data, pos, ver)
        if n is None: break
        roots.append(n)

    videos = []
    for r in roots:
        walk(r, 'Video', videos)

    os.makedirs(outdir, exist_ok=True)
    n = 0
    for v in videos:
        rel, content = None, None
        for kn, kp, _ in v[2]:
            if kn == 'RelativeFilename' and kp and isinstance(kp[0], str):
                rel = kp[0]
            elif kn == 'Content' and kp and isinstance(kp[0], (bytes, bytearray)):
                content = kp[0]
        if not content:
            continue
        base = os.path.basename((rel or 'texture_%d' % n).replace('\\', '/'))
        if content[:8] == b'\x89PNG\r\n\x1a\n':
            w, h = int.from_bytes(content[16:20], 'big'), int.from_bytes(content[20:24], 'big')
            kind = 'PNG'
        elif content[:3] == b'\xff\xd8\xff':
            w = h = 0
            kind = 'JPEG'
            i = 2
            while i < len(content) - 9:      # walk JPEG segments to the SOF for dimensions
                if content[i] != 0xFF: i += 1; continue
                m = content[i+1]
                if m in (0xC0, 0xC1, 0xC2):
                    h = int.from_bytes(content[i+5:i+7], 'big')
                    w = int.from_bytes(content[i+7:i+9], 'big')
                    break
                if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7: i += 2; continue
                i += 2 + int.from_bytes(content[i+2:i+4], 'big')
        else:
            kind, w, h = '?', 0, 0
        path = os.path.join(outdir, base)
        open(path, 'wb').write(content)
        print('  %-28s %s %dx%d  %d KB' % (base, kind, w, h, len(content)//1024))
        n += 1

    print('%d texture(s) -> %s' % (n, outdir))
    if n == 0:
        print('  (no embedded textures - they may be external files next to the FBX)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
