# targets: skills/character-autorig/scripts/deform_gate.py, skills/blender-retarget/scripts/brt_arp.py, skills/humanoid-motion/scripts/twocam/blender/prepare_rig.py
def chain_free_tails(bones, prefix="cc_", tol=1e-4):
    """{name: tail} for bones [(name, parent, head, tail)] (armature space), each tail where Blender's
    FBX importer puts it when the file holds no `prefix` (secondary-chain) bones.

    The importer gives a bone the mean distance to its child bones' heads as its length (a child at the
    same point counts), its parent's length when it has none, at least 0.01, along the bone's own axis;
    it never turns a bone toward a child. So a chain hung under a contract bone (hair under the Head,
    shorts hems under a thigh) lengthens that bone and every childless bone below it, and nothing else.
    A rig whose lengths do not follow that rule (built in Blender, not imported) is returned unchanged,
    and so is every bone the chains do not reach. Chain bones keep their own tails."""
    info = {n: (p, tuple(map(float, h)), tuple(map(float, t))) for n, p, h, t in bones}
    kids = {}
    for n, (p, _, _) in info.items():
        if p in info:
            kids.setdefault(p, []).append(n)

    def dist(a, b):
        return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5

    def sizes(skip):
        out = {}

        def walk(n, parent_size):
            h = info[n][1]
            ch = [c for c in kids.get(n, []) if not (skip and c.startswith(prefix))]
            own = sum(dist(info[c][1], h) for c in ch) / len(ch) if ch else parent_size
            out[n] = own
            for c in kids.get(n, []):
                walk(c, own)
        for n, (p, _, _) in info.items():
            if p not in info:
                walk(n, 1.0)
        return out

    tails = {n: t for n, (_, _, t) in info.items()}
    if not any(n.startswith(prefix) for n in info):
        return tails
    with_cc, without = sizes(False), sizes(True)
    near = lambda a, b: abs(a - b) <= tol * max(1.0, abs(a))
    if not all(near(max(0.01, with_cc[n]), dist(h, t)) for n, (_, h, t) in info.items()):
        return tails                       # not the importer's lengths: leave the rig as it is
    for n, (_, h, t) in info.items():
        if n.startswith(prefix) or near(with_cc[n], without[n]):
            continue
        length = dist(h, t)
        k = max(0.01, without[n]) / length if length > 0 else 0.0
        tails[n] = tuple(hh + (tt - hh) * k for hh, tt in zip(h, t))
    return tails
