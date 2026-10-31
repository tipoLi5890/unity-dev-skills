#!/usr/bin/env python3
# Any FBX with embedded maps (reference/textures.md); the Mixamo route needs it on the ORIGINAL export.
"""Extract embedded textures from an FBX, keeping their original file names.

usage:
    fbx_textures.py <input.fbx> [outdir]
    fbx_textures.py --selftest

Stdlib only. Mixamo strips materials, so after the auto-rigger returns a rigged
FBX the maps have to be reattached in Unity by hand - this pulls them out of the
ORIGINAL export so you know which map is which.

Why not just carve the PNG/JPEG byte ranges out of the file: that gives you
tex0..tex3 in storage order with no idea which is normal and which is roughness,
and guessing from file size is a coin flip on a character whose metallic map is
nearly flat. FBX stores each image in a Video node next to a RelativeFilename,
so the real names ("texture_normal.png") are right there - this reads that
pairing instead. Each map is printed with the material slot the FBX connects it
to (DiffuseColor, NormalMap, ...). A generic name (Image_0, an Auto-Rig Pro
export's) is replaced by <fbx name>_<Role> from that slot: Runner_BaseColor.png,
Runner_Normal.png, the names CharacterImportSettings.cs gives the same maps.

Exit codes: 0 done; 1 usage error or an unreadable file.
"""
import os, re, struct, sys, tempfile


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


# FBX material property -> role; the names CharacterImportSettings.cs binds (BaseColor, Normal).
ROLES = {'diffusecolor': 'BaseColor', 'diffuse': 'BaseColor', 'basecolor': 'BaseColor',
         'basecolormap': 'BaseColor', 'colormap': 'BaseColor', 'texcolormap': 'BaseColor',
         'normalmap': 'Normal', 'bump': 'Normal', 'bumpmap': 'Normal', 'normalcamera': 'Normal',
         'texnormalmap': 'Normal', 'reflectionfactor': 'Metallic', 'shininessexponent': 'Roughness'}
GENERIC = re.compile(r'^(image|texture|tex|img)[_ .-]?\d*$', re.I)


def role_of(prop):
    """Role of an FBX material texture property ('Maya|baseColor' -> 'BaseColor'), or None."""
    return ROLES.get(prop.lower().rsplit('|', 1)[-1].replace('_', '')) if prop else None


def fbx_name(s):
    """'Image_0\\x00\\x01Video' -> 'Image_0'."""
    return s.split('\x00')[0] if isinstance(s, str) else ''


def parse(data):
    if data[:20] != b'Kaydara FBX Binary  ':
        raise ValueError('not a binary FBX (an ASCII FBX keeps no embedded images)')
    ver = struct.unpack('<I', data[23:27])[0]
    roots, pos = [], 27
    while pos < len(data) - 30:
        n, pos = read_node(data, pos, ver)
        if n is None: break
        roots.append(n)
    return roots


def maps(roots):
    """[(file name, kind, w, h, bytes, [(material, property)])] for every embedded image."""
    videos, textures, materials, conns = [], [], [], []
    for r in roots:
        walk(r, 'Video', videos)
        walk(r, 'Texture', textures)
        walk(r, 'Material', materials)
        walk(r, 'C', conns)
    mat_name = {m[1][0]: fbx_name(m[1][1]) for m in materials if len(m[1]) > 1}
    tex_ids = {t[1][0] for t in textures if t[1]}
    video_tex, tex_slot = {}, {}
    for c in conns:
        kp = c[1]
        if len(kp) >= 3 and kp[0] == 'OO' and kp[2] in tex_ids:
            video_tex.setdefault(kp[1], []).append(kp[2])
        elif len(kp) >= 4 and kp[0] == 'OP' and kp[1] in tex_ids:
            tex_slot.setdefault(kp[1], []).append((mat_name.get(kp[2], ''), kp[3]))
    out, n = [], 0
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
        n += 1
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
        slots = [s for t in video_tex.get(v[1][0] if v[1] else None, []) for s in tex_slot.get(t, [])]
        out.append((base, kind, w, h, bytes(content), slots))
    return out


def names(found, stem):
    """Output file name per image: the authored one, or <stem>_<Role> when that is generic."""
    per_role = {}
    for base, _, _, _, _, slots in found:
        for _, prop in slots[:1]:
            per_role.setdefault(role_of(prop), set()).add(base)
    out, used = [], set()
    for base, _, _, _, _, slots in found:
        root, ext = os.path.splitext(base)
        name = base
        if slots and GENERIC.match(root) and role_of(slots[0][1]):
            mat, prop = slots[0]
            role = role_of(prop)
            mat = re.sub(r'[^A-Za-z0-9-]', '_', mat) if len(per_role[role]) > 1 and mat else ''
            name = '_'.join(x for x in (stem, mat, role) if x) + ext.lower()
        while name.lower() in used:
            r, e = os.path.splitext(name)
            name = r + '_' + e if not e else r + '_x' + e
        used.add(name.lower())
        out.append(name)
    return out


def extract(src, outdir):
    found = maps(parse(open(src, 'rb').read()))
    stem = os.path.splitext(os.path.basename(src))[0]
    os.makedirs(outdir, exist_ok=True)
    rows = []
    for (base, kind, w, h, content, slots), name in zip(found, names(found, stem)):
        open(os.path.join(outdir, name), 'wb').write(content)
        rows.append((name, kind, w, h, len(content), ','.join(p for _, p in slots) or '-'))
    return rows


def _node(name, props, kids=()):
    """One FBX 7.4 binary node (32-bit header) - the selftest's writer."""
    body = b''
    for p in props:
        if isinstance(p, str):
            b = p.encode(); body += b'S' + struct.pack('<I', len(b)) + b
        elif isinstance(p, bytes):
            body += b'R' + struct.pack('<I', len(p)) + p
        else:
            body += b'L' + struct.pack('<q', p)
    sub = b''.join(kids)
    if kids:
        sub += b'\x00' * 13
    head_len = 13 + len(name)
    return lambda off: (struct.pack('<III', off + head_len + len(body) + len(sub), len(props), len(body)) +
                        bytes([len(name)]) + name.encode() + body + sub)


def _fbx(nodes):
    """Lay nodes out from offset 27, resolving each end offset."""
    def emit(n, off):
        name, props, kids = n
        out_kids, cur = [], None
        head = 13 + len(name)
        body_len = len(_node(name, props)(0)) - head
        cur = off + head + body_len
        for k in kids:
            b = emit(k, cur)
            out_kids.append(b); cur += len(b)
        return _node(name, props, out_kids)(off)
    data, off = bytearray(b'Kaydara FBX Binary  \x00\x1a\x00' + struct.pack('<I', 7400)), 27
    for n in nodes:
        b = emit(n, off); data += b; off += len(b)
    return bytes(data + b'\x00' * 13 + b'\x00' * 40)


def selftest():
    png = lambda w, h: b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + w.to_bytes(4, 'big') + h.to_bytes(4, 'big') + b'\x08\x02\x00\x00\x00'
    jpg = b'\xff\xd8\xff\xc0\x00\x11\x08\x00\x40\x00\x80' + b'\x00' * 12
    vid = lambda i, n, c: ('Video', [i, n + '\x00\x01Video', 'Clip'], [('RelativeFilename', ['Runner.fbm/' + n + ('.jpg' if c[:2] == b'\xff\xd8' else '.png')], []), ('Content', [c], [])])
    tex = lambda i, n: ('Texture', [i, n + '\x00\x01Texture', ''], [])
    objects = ('Objects', [], [
        ('Material', [10, 'RunnerMat\x00\x01Material', ''], []),
        tex(20, 'base_color_texture'), tex(21, 'normalmap_texture'), tex(22, 'metal'), tex(23, 'authored'),
        vid(30, 'Image_0', png(2048, 2048)), vid(31, 'Image_2', png(1024, 1024)),
        vid(32, 'Image_3', jpg), vid(33, 'courier_skin', png(16, 16)), vid(34, 'Image_9', png(8, 8))])
    conns = ('Connections', [], [
        ('C', ['OO', 30, 20], []), ('C', ['OO', 31, 21], []), ('C', ['OO', 32, 22], []), ('C', ['OO', 33, 23], []),
        ('C', ['OP', 20, 10, 'DiffuseColor'], []), ('C', ['OP', 21, 10, 'NormalMap'], []),
        ('C', ['OP', 22, 10, 'ReflectionFactor'], []), ('C', ['OP', 23, 10, 'EmissiveColor'], [])])
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, 'Runner.fbx')
        open(src, 'wb').write(_fbx([objects, conns]))
        rows = extract(src, os.path.join(d, 'out'))
        got = {r[0]: r for r in rows}
        want = {'Runner_BaseColor.png': (2048, 'DiffuseColor'), 'Runner_Normal.png': (1024, 'NormalMap'),
                'Runner_Metallic.jpg': (128, 'ReflectionFactor'),
                'courier_skin.png': (16, 'EmissiveColor'),      # an authored name is kept
                'Image_9.png': (8, '-')}                         # no slot: kept as it is
        for name, (w, slot) in want.items():
            assert name in got, (name, sorted(got))
            assert got[name][2] == w and got[name][5] == slot, got[name]
            assert os.path.exists(os.path.join(d, 'out', name))
        assert len(rows) == 5, rows
        assert role_of('Maya|baseColor') == 'BaseColor' and role_of('Bump') == 'Normal' and role_of('X') is None
        try:
            parse(b'; FBX 7.4.0 project file\n')
            raise AssertionError('ASCII accepted')
        except ValueError:
            pass
    print('fbx_textures selftest: ok (5 maps: names from slots, authored names kept, ASCII refused)')
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (['-h'], ['--help']):
        print(__doc__)
        return 0
    if argv[:1] == ['--selftest']:
        return selftest()
    if not argv or len(argv) > 2 or any(a.startswith('-') for a in argv):
        print(__doc__, file=sys.stderr)
        return 1
    src = argv[0]
    outdir = argv[1] if len(argv) > 1 else os.path.splitext(src)[0] + '_textures'
    try:
        rows = extract(src, outdir)
    except (OSError, ValueError, struct.error) as e:
        print('fbx_textures: %s: %s' % (src, e), file=sys.stderr)
        return 1
    for name, kind, w, h, size, slot in rows:
        print('  %-28s %s %dx%d  %d KB  %s' % (name, kind, w, h, size // 1024, slot))
    print('%d texture(s) -> %s' % (len(rows), outdir))
    if not rows:
        print('  (no embedded textures - they may be external files next to the FBX)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
