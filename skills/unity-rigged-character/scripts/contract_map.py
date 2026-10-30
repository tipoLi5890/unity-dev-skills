#!/usr/bin/env python3
"""contract_map.py — map any humanoid skeleton onto the humanoid contract, and gate it.

The contract (`reference/humanoid-contract.md`) is one fixed bone set with Blender names: Unity's
Humanoid bones plus Chest, UpperChest, Neck, toes, 15 finger bones per hand and a non-deform Root
on the ground. Every motion source (Mixamo, Auto-Rig Pro's export, a purchased clip pack,
any other dumped skeleton) reaches the contract through a role map: contract bone -> source bone.

usage:
    contract_map.py map SKELETON [--map auto|contract|mixamo|arp|arp-ue|FILE.json]
                        [--require unity|contract] [--min-fingers N] [--arm-angle 30,60]
                        [--out REPORT.json] [--unity-out HUMAN_MAP.json] [--map-out ROLE_MAP.json]
    contract_map.py bvh FILE.bvh [--scale S] [--keep-axes] [--out SKELETON.json]
    contract_map.py contract [--height 1.7] [--out SKELETON.json]
    contract_map.py suggest SKELETON [--out ROLE_MAP.json]
    contract_map.py presets
    contract_map.py selftest            (or --selftest)

SKELETON is a skeleton JSON (below) or a .bvh file (its header is read; the motion is ignored).

Skeleton JSON (schema "skeleton/1"). Any of these shapes is read:
    {"schema": "skeleton/1", "up": "+Z", "forward": "-Y", "units": "m",
     "bones": [{"name": "Hips", "parent": "Root", "head": [0, 0, 0.9], "tail": [0, 0, 1.0],
                "deform": true}, ...]}
    {"bones": {"Hips": {"parent": "Root", "head": [...], "deform": true}, ...}}   # bcr_fbx snapshot
    [{"name": "Hips", "parent": null}, ...]                                       # names only
`head`, `tail` and `deform` are optional; without heads the position gates are skipped. `up`
"+Y" (a BVH, a Y-up dump) is converted on read with (x, y, z) -> (x, -z, y), Blender's own
Y-up import, so a Y-up file facing +Z ends facing -Y. A Blender dump is armature space:
`bone.head_local` / `bone.tail_local` per bone, `bone.parent.name`, `bone.use_deform`.

Role map JSON (schema "role-map/1"): contract bone -> source bone, or a list of candidates (the
first one present wins). A source name also matches with its namespace stripped
("mixamorig1:Hips" matches "Hips").
    {"schema": "role-map/1", "name": "my-pack", "bones": {"Hips": "pelvis", "Chest": ["spine_02"]}}

Gates (each failing one makes exit 2):
  required     the 15 bones Unity's Humanoid requires are mapped
  contract     (--require contract) every contract bone is mapped, Root is non-deform, the rest
               is the contract's: Root at the origin, feet either side of it, arms in an A-pose
               (upper arm --arm-angle degrees below horizontal)
  fingers      (--min-fingers N > 0) at least N finger bones are mapped, both hands together
  unique       no source bone is mapped to two contract bones
  parent_chain each mapped bone's nearest mapped source ancestor is its nearest mapped contract
               ancestor (a source joint the contract skips, a second neck bone or a metacarpal, passes;
               a finger under the forearm or a leg under the wrong hip fails)
  sides        (heads present) every .L bone lies at larger x than its .R twin
  axes         (heads present) Head above Hips above the feet; toes in front of the foot (-Y)

The report carries `retarget_map` {contract_bone: source_bone}, the orientation brt_retarget's
`map` takes (target: source), and `human` [{humanName, boneName}] for Unity's HumanDescription
(also written by --unity-out, the file CharacterHumanoidAvatar.cs reads).

Prints one JSON object. Exit codes: 0 every gate passed; 2 a gate failed (required bones missing,
a broken chain, ...); 1 refused input (unreadable file, unknown preset, malformed BVH).
Requires Python 3 and numpy.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

SIDES = ("L", "R")
FINGERS = ("Thumb", "Index", "Middle", "Ring", "Little")
PHALANX = ("Proximal", "Intermediate", "Distal")

# (contract bone, contract parent, Unity human name or None, Unity-required)
_CENTRE = [
    ("Root", None, None, False),
    ("Hips", "Root", "Hips", True),
    ("Spine", "Hips", "Spine", True),
    ("Chest", "Spine", "Chest", False),
    ("UpperChest", "Chest", "UpperChest", False),
    ("Neck", "UpperChest", "Neck", False),
    ("Head", "Neck", "Head", True),
]
_LIMB = [  # per side; parent None = a centre bone named in _LIMB_PARENT
    ("Shoulder", "UpperChest", "Shoulder", False),
    ("UpperArm", "Shoulder", "UpperArm", True),
    ("LowerArm", "UpperArm", "LowerArm", True),
    ("Hand", "LowerArm", "Hand", True),
    ("UpperLeg", "Hips", "UpperLeg", True),
    ("LowerLeg", "UpperLeg", "LowerLeg", True),
    ("Foot", "LowerLeg", "Foot", True),
    ("Toes", "Foot", "Toes", False),
]
CENTRE_NAMES = {c[0] for c in _CENTRE}


def _side_name(base: str, side: str) -> str:
    return f"{base}.{side}"


def contract_bones() -> list[dict]:
    """The contract, root first: name, parent, unity (HumanTrait.BoneName string), required, finger."""
    out = [dict(name=n, parent=p, unity=u, required=r, finger=False) for n, p, u, r in _CENTRE]
    for side in SIDES:
        word = "Left" if side == "L" else "Right"
        for n, p, u, r in _LIMB:
            parent = p if p in CENTRE_NAMES else _side_name(p, side)
            out.append(dict(name=_side_name(n, side), parent=parent, unity=word + u, required=r, finger=False))
        for f in FINGERS:
            parent = _side_name("Hand", side)
            for i, ph in enumerate(PHALANX, 1):
                name = _side_name(f"{f}{i}", side)
                out.append(dict(name=name, parent=parent, unity=f"{word} {f} {ph}", required=False, finger=True))
                parent = name
    return out


CONTRACT = contract_bones()
BY_NAME = {b["name"]: b for b in CONTRACT}
REQUIRED = [b["name"] for b in CONTRACT if b["required"]]
FINGER_BONES = [b["name"] for b in CONTRACT if b["finger"]]


def contract_skeleton(height: float = 1.7) -> dict:
    """A reference contract rest: A-pose (upper arm 45 deg below horizontal), +Z up, facing -Y,
    origin between the feet. Proportions are a default; the gates read ratios, not these numbers."""
    h = {}
    h["Root"] = (0, 0, 0)
    for n, z in (("Hips", .53), ("Spine", .58), ("Chest", .65), ("UpperChest", .72), ("Neck", .82), ("Head", .87)):
        h[n] = (0, 0, z)
    tails = {"Root": (0, .10, 0), "Head": (0, 0, 1.0)}
    a = math.radians(45)
    for side in SIDES:
        s = 1 if side == "L" else -1
        d = np.array([s * math.cos(a), 0, -math.sin(a)])
        sh = np.array([s * .02, 0, .80])
        ua = np.array([s * .10, 0, .80])
        la, hd = ua + .17 * d, ua + .32 * d
        h[f"Shoulder.{side}"], h[f"UpperArm.{side}"] = tuple(sh), tuple(ua)
        h[f"LowerArm.{side}"], h[f"Hand.{side}"] = tuple(la), tuple(hd)
        tails[f"Hand.{side}"] = tuple(hd + .06 * d)
        for f, off in zip(FINGERS, (-.025, -.015, -.005, .005, .015)):
            base = hd + (.02 if f == "Thumb" else .06) * d + np.array([0, off, 0])
            fd = d if f != "Thumb" else (d + np.array([0, -1, 0])) / math.sqrt(2)
            p = base
            for i, length in enumerate((.025, .02, .015), 1):
                h[f"{f}{i}.{side}"] = tuple(p)
                p = p + length * fd
            tails[f"{f}3.{side}"] = tuple(p)
        h[f"UpperLeg.{side}"] = (s * .09, 0, .50)
        h[f"LowerLeg.{side}"] = (s * .09, 0, .27)
        h[f"Foot.{side}"] = (s * .09, 0, .04)
        h[f"Toes.{side}"] = (s * .09, -.10, .01)
        tails[f"Toes.{side}"] = (s * .09, -.15, .01)
    children: dict[str, list[str]] = {}
    for b in CONTRACT:
        if b["parent"]:
            children.setdefault(b["parent"], []).append(b["name"])
    bones = []
    for b in CONTRACT:
        name = b["name"]
        kids = [k for k in children.get(name, []) if not BY_NAME[k]["finger"] and "Shoulder" not in k
                and "UpperLeg" not in k]
        if name in tails:
            tail = tails[name]
        elif kids:
            tail = h[kids[0]]
        else:
            tail = tuple(np.array(h[name]) + (0, 0, .05))
        bones.append({"name": name, "parent": b["parent"], "deform": name != "Root",
                      "head": [round(v * height, 5) for v in h[name]],
                      "tail": [round(v * height, 5) for v in tail]})
    return {"schema": "skeleton/1", "source": "humanoid-contract", "up": "+Z", "forward": "-Y",
            "units": "m", "bones": bones}


# ------------------------------------------------------------------------------- role maps

def _sided(table: dict, left: str, right: str, fmt) -> dict:
    """Expand {contract_base: source_base} into both sides with a naming function."""
    out = {}
    for side, word in (("L", left), ("R", right)):
        for base, src in table.items():
            out[f"{base}.{side}"] = [fmt(s, word) for s in (src if isinstance(src, list) else [src])]
    return out


def _fingers(names: dict, start: int = 1) -> dict:
    """{'Thumb': 'Thumb', ...} -> contract finger bases mapped to source finger bases + index."""
    out = {}
    for f in FINGERS:
        for i in range(1, 4):
            first = start if f != "Thumb" else 1
            out[f"{f}{i}"] = f"{names[f]}{first + i - 1}"
    return out


def builtin_maps() -> dict:
    maps = {"contract": {"name": "contract", "bones": {b["name"]: [b["name"]] for b in CONTRACT}}}

    mixamo_limbs = {"Shoulder": "Shoulder", "UpperArm": "Arm", "LowerArm": "ForeArm", "Hand": "Hand",
                    "UpperLeg": "UpLeg", "LowerLeg": "Leg", "Foot": "Foot", "Toes": "ToeBase"}
    mixamo_limbs.update(_fingers({f: "Hand" + ("Pinky" if f == "Little" else f) for f in FINGERS}))
    bones = {"Hips": ["Hips"], "Spine": ["Spine"], "Chest": ["Spine1"], "UpperChest": ["Spine2"],
             "Neck": ["Neck"], "Head": ["Head"]}
    bones.update(_sided(mixamo_limbs, "Left", "Right", lambda s, w: w + s))
    maps["mixamo"] = {"name": "mixamo", "bones": bones}

    # Auto-Rig Pro humanoid export, bone names as exported without "Rename for UE".
    arp_limbs = {"Shoulder": "shoulder", "UpperArm": ["arm_stretch", "arm"],
                 "LowerArm": ["forearm_stretch", "forearm"], "Hand": "hand",
                 "UpperLeg": ["thigh_stretch", "thigh"], "LowerLeg": ["leg_stretch", "leg"],
                 "Foot": "foot", "Toes": "toes_01"}
    arp_limbs.update(_fingers({f: "c_" + ("pinky" if f == "Little" else f.lower()) for f in FINGERS}))
    bones = {"Root": ["c_traj", "root"], "Hips": ["root.x"], "Spine": ["spine_01.x"],
             "Chest": ["spine_02.x"], "UpperChest": ["spine_03.x"], "Neck": ["neck.x", "neck_01.x"],
             "Head": ["head.x"]}
    bones.update(_sided(arp_limbs, "l", "r", lambda s, w: f"{s}.{w}"))
    maps["arp"] = {"name": "arp", "bones": bones}

    # Auto-Rig Pro with "Rename for UE" (also the shape many purchased packs share).
    ue_limbs = {"Shoulder": "clavicle", "UpperArm": "upperarm", "LowerArm": "lowerarm", "Hand": "hand",
                "UpperLeg": "thigh", "LowerLeg": "calf", "Foot": "foot", "Toes": "ball"}
    for f in FINGERS:
        for i in range(1, 4):
            ue_limbs[f"{f}{i}"] = f"{'pinky' if f == 'Little' else f.lower()}_0{i}"
    bones = {"Root": ["root"], "Hips": ["pelvis"], "Spine": ["spine_01"], "Chest": ["spine_02"],
             "UpperChest": ["spine_03"], "Neck": ["neck_01"], "Head": ["head"]}
    bones.update(_sided(ue_limbs, "l", "r", lambda s, w: f"{s}_{w}"))
    maps["arp-ue"] = {"name": "arp-ue", "bones": bones}
    return maps


BUILTIN = builtin_maps()


# ------------------------------------------------------------------------------- skeleton I/O

class Refused(Exception):
    pass


def y_up_to_z_up(v):
    return [v[0], -v[2], v[1]]


def normalise_skeleton(data) -> dict:
    """Any accepted shape -> {"bones": [ {name, parent, head|None, tail|None, deform} ], ...} in Z up."""
    meta = {}
    if isinstance(data, dict):
        meta = {k: v for k, v in data.items() if k != "bones"}
        data = data.get("snapshot", data)
        raw = data.get("bones")
    else:
        raw = data
    if isinstance(raw, dict):
        raw = [dict(v, name=k) for k, v in raw.items()]
    if not isinstance(raw, list) or not raw:
        raise Refused("no bones: expected a 'bones' list or dict")
    up = str(meta.get("up", "+Z")).upper()
    if up not in ("+Z", "+Y", "Z", "Y"):
        raise Refused(f"up {up!r}: only +Z and +Y are read")
    convert = up in ("+Y", "Y")
    bones, seen = [], set()
    for b in raw:
        if not isinstance(b, dict) or not b.get("name"):
            raise Refused("every bone needs a name")
        if b["name"] in seen:
            raise Refused(f"bone {b['name']!r} appears twice")
        seen.add(b["name"])
        out = {"name": str(b["name"]), "parent": b.get("parent") or None, "deform": bool(b.get("deform", True)),
               "head": None, "tail": None}
        for key in ("head", "tail"):
            v = b.get(key)
            if v is not None:
                if len(v) != 3 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in v):
                    raise Refused(f"{b['name']}: {key} is not three finite numbers")
                out[key] = y_up_to_z_up(v) if convert else list(map(float, v))
        if "channels" in b:
            out["channels"] = b["channels"]
        bones.append(out)
    for b in bones:
        if b["parent"] is not None and b["parent"] not in seen:
            raise Refused(f"{b['name']}: parent {b['parent']!r} is not a bone")
    meta.update({"up": "+Z", "forward": meta.get("forward", "-Y") if not convert else "-Y"})
    meta["bones"] = bones
    return meta


def read_bvh_header(text: str, scale: float = 1.0) -> dict:
    """The HIERARCHY of a BVH file as skeleton/1 in the file's own axes (up +Y): head = summed
    OFFSETs, tail = the first child's head, else the End Site, else head + 10% of the offset."""
    tokens = re.findall(r"[{}]|[^\s{}]+", text.split("MOTION")[0])
    if not tokens or tokens[0].upper() != "HIERARCHY":
        raise Refused("not a BVH file: no HIERARCHY")
    i, stack, bones, by = 1, [], [], {}
    pending = None  # ("joint", name) or ("end",)
    while i < len(tokens):
        t = tokens[i]
        tu = t.upper()
        if tu in ("ROOT", "JOINT"):
            if i + 1 >= len(tokens):
                raise Refused("truncated BVH header")
            pending = ("joint", tokens[i + 1])
            i += 2
        elif tu == "END":
            pending = ("end",)
            i += 2
        elif t == "{":
            if pending is None:
                raise Refused("BVH: '{' without a joint")
            parent = stack[-1] if stack else None
            if pending[0] == "joint":
                name = pending[1]
                if name in by:
                    raise Refused(f"BVH: joint {name!r} twice")
                b = {"name": name, "parent": parent["name"] if parent and parent.get("name") else None,
                     "offset": None, "channels": [], "end": None, "kids": []}
                bones.append(b)
                by[name] = b
                if parent and parent.get("name"):
                    parent["kids"].append(name)
                stack.append(b)
            else:
                stack.append({"end_of": parent})
            pending = None
            i += 1
        elif t == "}":
            if not stack:
                raise Refused("BVH: unbalanced '}'")
            stack.pop()
            i += 1
        elif tu == "OFFSET":
            try:
                off = [float(x) * scale for x in tokens[i + 1:i + 4]]
            except ValueError:
                raise Refused("BVH: OFFSET is not three numbers")
            if len(off) != 3 or not stack:
                raise Refused("BVH: OFFSET outside a joint")
            top = stack[-1]
            if "end_of" in top:
                top["end_of"]["end"] = off
            else:
                top["offset"] = off
            i += 4
        elif tu == "CHANNELS":
            try:
                n = int(tokens[i + 1])
            except (IndexError, ValueError):
                raise Refused("BVH: CHANNELS without a count")
            if not stack:
                raise Refused("BVH: CHANNELS outside a joint")
            stack[-1]["channels"] = tokens[i + 2:i + 2 + n]
            i += 2 + n
        else:
            i += 1
    if stack:
        raise Refused("BVH: unbalanced braces")
    if not bones:
        raise Refused("BVH: no joints")
    head = {}
    for b in bones:  # parents precede children in a BVH
        if b["offset"] is None:
            raise Refused(f"BVH: joint {b['name']!r} has no OFFSET")
        base = head[b["parent"]] if b["parent"] else np.zeros(3)
        head[b["name"]] = base + np.array(b["offset"])
    out = []
    for b in bones:
        hd = head[b["name"]]
        if b["kids"]:
            tl = head[b["kids"][0]]
        elif b["end"] is not None:
            tl = hd + np.array(b["end"])
        else:
            tl = hd + 0.1 * np.array(b["offset"])
        if np.linalg.norm(tl - hd) < 1e-9:
            tl = hd + np.array([0, 0.01 * scale, 0])
        out.append({"name": b["name"], "parent": b["parent"], "head": [round(float(v), 6) for v in hd],
                    "tail": [round(float(v), 6) for v in tl], "deform": True, "channels": b["channels"]})
    return {"schema": "skeleton/1", "source": "bvh", "up": "+Y", "forward": "+Z",
            "units": f"file units x {scale}", "bones": out}


def load_skeleton(path: Path, scale: float = 1.0) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise Refused(f"{path}: {exc}")
    if path.suffix.lower() == ".bvh":
        return normalise_skeleton(read_bvh_header(text, scale))
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise Refused(f"{path}: not JSON ({exc})")
    return normalise_skeleton(data)


def load_map(spec: str) -> dict:
    if spec in BUILTIN:
        return BUILTIN[spec]
    p = Path(spec)
    if not p.exists():
        raise Refused(f"--map {spec!r}: not a preset ({', '.join(BUILTIN)}, auto) and not a file")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Refused(f"{p}: {exc}")
    bones = data.get("bones")
    if not isinstance(bones, dict):
        raise Refused(f"{p}: role map needs a 'bones' object of contract bone -> source bone")
    unknown = sorted(k for k in bones if k not in BY_NAME)
    if unknown:
        raise Refused(f"{p}: not contract bones: {unknown[:8]} (names are case-sensitive: UpperArm.L, Little1.L)")
    return {"name": data.get("name", p.stem),
            "bones": {k: (v if isinstance(v, list) else [v]) for k, v in bones.items() if v}}


# ------------------------------------------------------------------------------- mapping

def _strip_ns(name: str) -> str:
    return name.rsplit(":", 1)[-1]


def resolve(role_map: dict, names: list[str]) -> dict:
    """contract bone -> the source bone present in this skeleton (exact, then namespace-stripped)."""
    exact = set(names)
    stripped: dict[str, str] = {}
    for n in names:
        stripped.setdefault(_strip_ns(n), n)
    out = {}
    for contract, cands in role_map["bones"].items():
        for c in cands:
            if c in exact:
                out[contract] = c
                break
            if _strip_ns(c) in stripped:
                out[contract] = stripped[_strip_ns(c)]
                break
    return out


def pick_map(spec: str, names: list[str]) -> tuple[dict, dict]:
    if spec != "auto":
        rm = load_map(spec)
        return rm, resolve(rm, names)
    best = None
    for key, rm in BUILTIN.items():
        got = resolve(rm, names)
        score = (sum(1 for r in REQUIRED if r in got), len(got))
        if best is None or score > best[0]:
            best = (score, rm, got)
    return best[1], best[2]


def contract_ancestors(name: str) -> list[str]:
    out, p = [], BY_NAME[name]["parent"]
    while p:
        out.append(p)
        p = BY_NAME[p]["parent"]
    return out


def evaluate(skel: dict, spec: str = "auto", require: str = "unity", min_fingers: int = 0,
             arm_angle=(30.0, 60.0)) -> dict:
    bones = skel["bones"]
    names = [b["name"] for b in bones]
    src = {b["name"]: b for b in bones}
    role_map, mapped = pick_map(spec, names)
    gates = []

    def gate(name, passed, **detail):
        gates.append({"name": name, "pass": bool(passed), **detail})

    missing_req = [r for r in REQUIRED if r not in mapped]
    gate("required", not missing_req, missing=missing_req, need=len(REQUIRED))

    # unique
    owners: dict[str, list[str]] = {}
    for c, s in mapped.items():
        owners.setdefault(s, []).append(c)
    dup = {s: cs for s, cs in owners.items() if len(cs) > 1}
    gate("unique", not dup, duplicates=dup)

    # parent chain
    rev = {s: c for c, s in mapped.items()}
    breaks = []
    for c, s in mapped.items():
        p = src[s]["parent"]
        while p is not None and p not in rev:
            p = src[p]["parent"]
        got = rev.get(p) if p is not None else None
        expected = next((a for a in contract_ancestors(c) if a in mapped), None)
        if got != expected:
            breaks.append({"bone": c, "source": s, "source_parent": got, "expected": expected})
    gate("parent_chain", not breaks, breaks=breaks)

    fingers = [f for f in FINGER_BONES if f in mapped]
    if min_fingers > 0:
        gate("fingers", len(fingers) >= min_fingers, mapped=len(fingers), need=min_fingers)

    def head(c):
        s = mapped.get(c)
        return np.array(src[s]["head"]) if s and src[s]["head"] is not None else None

    have_pos = any(b["head"] is not None for b in bones)
    if have_pos:
        swapped = []
        for b in CONTRACT:
            if b["name"].endswith(".L"):
                hl, hr = head(b["name"]), head(b["name"][:-2] + ".R")
                if hl is not None and hr is not None and not hl[0] > hr[0]:
                    swapped.append(b["name"][:-2])
        gate("sides", not swapped, swapped=swapped)
        problems = []
        hh, hp = head("Head"), head("Hips")
        feet = [x for x in (head("Foot.L"), head("Foot.R")) if x is not None]
        if hh is not None and hp is not None and not hh[2] > hp[2]:
            problems.append("Head is not above Hips: wrong up axis")
        if hp is not None and feet and not hp[2] > max(f[2] for f in feet):
            problems.append("Hips are not above the feet: wrong up axis")
        for side in SIDES:
            f, t = head(f"Foot.{side}"), head(f"Toes.{side}")
            if f is not None and t is not None and not t[1] < f[1]:
                problems.append(f"Toes.{side} is not in front of the foot (-Y): wrong facing")
        gate("axes", not problems, problems=problems)

    if require == "contract":
        missing = [b["name"] for b in CONTRACT if b["name"] not in mapped]
        problems = []
        if "Root" in mapped and src[mapped["Root"]]["deform"]:
            problems.append("Root deforms: it must be a non-deform bone")
        if have_pos:
            hh, root = head("Head"), head("Root")
            feet = [x for x in (head("Foot.L"), head("Foot.R")) if x is not None]
            height = float(hh[2]) if hh is not None else 1.0
            tol = 0.02 * max(height, 1e-6)
            if root is not None and np.linalg.norm(root) > tol:
                problems.append(f"Root head at {np.round(root, 4).tolist()}, not the origin")
            if len(feet) == 2 and abs(feet[0][0] + feet[1][0]) / 2 > tol:
                problems.append("the origin is not between the feet (x)")
            for side in SIDES:
                ua, la = head(f"UpperArm.{side}"), head(f"LowerArm.{side}")
                if ua is not None and la is not None:
                    v = la - ua
                    ang = math.degrees(math.atan2(-v[2], math.hypot(v[0], v[1])))
                    if not arm_angle[0] <= ang <= arm_angle[1]:
                        problems.append(f"UpperArm.{side} is {ang:.1f} deg below horizontal; "
                                        f"the A-pose wants {arm_angle[0]:g}-{arm_angle[1]:g}")
        else:
            problems.append("no heads: the rest pose cannot be checked")
        gate("contract", not missing and not problems, missing=missing, problems=problems)

    end_like = re.compile(r"(_end|end|_End|End|_nub|Nub|_tip|Site)$")
    extra = [n for n in names if n not in rev]
    extra_bones = [n for n in extra if not end_like.search(n)]
    human = [{"humanName": BY_NAME[c]["unity"], "boneName": s} for c, s in
             sorted(mapped.items(), key=lambda kv: [b["name"] for b in CONTRACT].index(kv[0]))
             if BY_NAME[c]["unity"]]
    ok = all(g["pass"] for g in gates)
    return {"op": "map", "ok": ok, "preset": role_map["name"], "require": require,
            "mapped": len(mapped), "contract_bones": len(CONTRACT),
            "missing_required": missing_req,
            "missing_optional": [b["name"] for b in CONTRACT if b["name"] not in mapped and not b["required"]],
            "fingers_mapped": len(fingers),
            "extra": extra_bones, "end_sites": [n for n in extra if end_like.search(n)],
            "translation_channels": [b["name"] for b in bones if any("position" in str(c).lower()
                                                                      for c in b.get("channels", []))],
            "gates": gates, "retarget_map": dict(mapped), "human": human}


# ------------------------------------------------------------------------------- suggest

_SIDE_RE = [
    (re.compile(r"(^|[^a-z])(left|lft)", re.I), "L"), (re.compile(r"(^|[^a-z])(right|rgt)", re.I), "R"),
    (re.compile(r"([._\s-]l$|^l[._\s-]|[._\s-]l[._\s-])", re.I), "L"),
    (re.compile(r"([._\s-]r$|^r[._\s-]|[._\s-]r[._\s-])", re.I), "R"),
]
_ROLE_KEYS = [  # (keyword regex on the side-free lower-case name, contract base); first match wins
    (r"thumb", "Thumb"), (r"index", "Index"), (r"middle", "Middle"), (r"ring", "Ring"),
    (r"pinky|little", "Little"), (r"toe|ball", "Toes"), (r"foot|ankle", "Foot"),
    (r"calf|shin|knee|lowerleg|lower_leg", "LowerLeg"), (r"upleg|thigh|upperleg|upper_leg", "UpperLeg"),
    (r"forearm|lowerarm|lower_arm|elbow", "LowerArm"), (r"hand|wrist", "Hand"),
    (r"clavicle|shoulder|collar", "Shoulder"), (r"upperarm|upper_arm|arm", "UpperArm"),
    (r"head", "Head"), (r"neck", "Neck"), (r"pelvis|hips?$|hip", "Hips"),
    (r"chest|spine|back|torso", "Spine*"), (r"^root$|traj|master", "Root"),
]


def suggest(skel: dict) -> dict:
    """A first role map from bone names, for a person to review: never gated, never trusted."""
    bones = skel["bones"]
    picked: dict[str, list[str]] = {}
    spine: list[str] = []
    for b in bones:
        raw = _strip_ns(b["name"])
        side = None
        for rx, sd in _SIDE_RE:
            if rx.search(raw):
                side = sd
                break
        low = re.sub(r"(left|right|lft|rgt)", "", raw.lower())
        low = re.sub(r"([._\s-][lr]$|^[lr][._\s-])", "", low)
        if re.search(r"(end|nub|tip|twist|roll|bend|ik|pole|target|helper)", low):
            continue
        for rx, role in _ROLE_KEYS:
            if re.search(rx, low):
                if role == "Spine*":
                    spine.append(b["name"])
                elif role in FINGERS:
                    if side:
                        picked.setdefault(f"{role}?.{side}", []).append(b["name"])
                elif role in CENTRE_NAMES:
                    picked.setdefault(role, []).append(b["name"])
                elif side:
                    picked.setdefault(f"{role}.{side}", []).append(b["name"])
                break
    out: dict[str, str] = {}
    for k, v in picked.items():
        if "?" in k:
            base, side = k.split("?.")
            # the last three joints of a finger chain are its phalanges (a metacarpal comes first)
            chain = [n for n in v if not re.search(r"meta|carpal|base", n, re.I)][-3:]
            for i, n in enumerate(chain, 1):
                out[f"{base}{i}.{side}"] = n
        else:
            out[k] = v[0]
    for c, n in zip(("Spine", "Chest", "UpperChest"), spine):
        out[c] = n
    return {"schema": "role-map/1", "name": "suggested", "review": True,
            "bones": {c: out[c] for c in [b["name"] for b in CONTRACT] if c in out}}


# ------------------------------------------------------------------------------- CLI

def _write(path, data):
    if path:
        Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def cmd_map(args) -> int:
    try:
        lo, hi = (float(x) for x in args.arm_angle.split(","))
    except ValueError:
        raise Refused(f"--arm-angle {args.arm_angle!r}: two numbers, low,high degrees (30,60)")
    skel = load_skeleton(Path(args.skeleton), args.scale)
    report = evaluate(skel, args.map, args.require, args.min_fingers, (lo, hi))
    report["skeleton"] = args.skeleton
    _write(args.out, report)
    _write(args.unity_out, {"schema": "unity-human-map/1", "preset": report["preset"], "human": report["human"]})
    _write(args.map_out, {"schema": "role-map/1", "name": report["preset"], "bones": report["retarget_map"]})
    print(json.dumps(report))
    return 0 if report["ok"] else 2


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["selftest"], ["--selftest"]):
        return selftest()
    ap = UsageParser(description=__doc__.split("\n")[0],
                                 epilog="Exit codes: 0 pass, 2 a gate failed, 1 refused input.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("map", help="map a skeleton onto the contract and gate it")
    m.add_argument("skeleton")
    m.add_argument("--map", default="auto", help="auto | " + " | ".join(BUILTIN) + " | a role-map JSON file")
    m.add_argument("--require", choices=("unity", "contract"), default="unity",
                   help="unity: Unity's 15 required bones; contract: the whole contract and its rest")
    m.add_argument("--min-fingers", type=int, default=0, help="gate: at least N finger bones mapped")
    m.add_argument("--arm-angle", default="30,60", help="A-pose range, degrees below horizontal")
    m.add_argument("--scale", type=float, default=1.0, help="BVH input only: multiply offsets")
    m.add_argument("--out")
    m.add_argument("--unity-out", help="write the HumanDescription map CharacterHumanoidAvatar reads")
    m.add_argument("--map-out", help="write the resolved role map (contract -> source), for review")
    b = sub.add_parser("bvh", help="a BVH header as skeleton JSON")
    b.add_argument("file")
    b.add_argument("--scale", type=float, default=1.0)
    b.add_argument("--keep-axes", action="store_true", help="keep the file's +Y up (default: convert to +Z)")
    b.add_argument("--out")
    c = sub.add_parser("contract", help="the contract skeleton at a reference A-pose")
    c.add_argument("--height", type=float, default=1.7)
    c.add_argument("--out")
    s = sub.add_parser("suggest", help="a first role map from bone names, to review")
    s.add_argument("skeleton")
    s.add_argument("--scale", type=float, default=1.0)
    s.add_argument("--out")
    sub.add_parser("presets", help="the built-in role maps")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "map":
            return cmd_map(args)
        if args.cmd == "bvh":
            try:
                text = Path(args.file).read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                raise Refused(str(exc))
            skel = read_bvh_header(text, args.scale)
            if not args.keep_axes:
                skel = normalise_skeleton(skel)
                skel = {"schema": "skeleton/1", "source": "bvh", **{k: v for k, v in skel.items()
                                                                     if k not in ("schema", "source")}}
            _write(args.out, skel)
            print(json.dumps({"op": "bvh", "ok": True, "bones": len(skel["bones"]), "up": skel["up"],
                              "out": args.out} if args.out else skel))
            return 0
        if args.cmd == "contract":
            skel = contract_skeleton(args.height)
            _write(args.out, skel)
            print(json.dumps({"op": "contract", "ok": True, "bones": len(skel["bones"]), "out": args.out,
                              "table": [{k: b[k] for k in ("name", "parent", "unity", "required")}
                                        for b in CONTRACT]}))
            return 0
        if args.cmd == "suggest":
            rm = suggest(load_skeleton(Path(args.skeleton), args.scale))
            _write(args.out, rm)
            print(json.dumps(rm))
            return 0
        if args.cmd == "presets":
            print(json.dumps({k: v["bones"] for k, v in BUILTIN.items()}))
            return 0
    except Refused as exc:
        print(json.dumps({"op": args.cmd, "ok": False, "error": str(exc)}))
        return 1
    return 1


# ------------------------------------------------------------------------------- selftest

def _renamed(skel: dict, rename: dict, drop=()) -> dict:
    bones = []
    for b in skel["bones"]:
        if b["name"] in drop:
            continue
        nb = dict(b)
        nb["name"] = rename.get(b["name"], b["name"])
        p = b["parent"]
        while p in drop:
            p = next(x for x in skel["bones"] if x["name"] == p)["parent"]
        nb["parent"] = rename.get(p, p) if p else None
        bones.append(nb)
    return {**skel, "bones": bones}


def _to_bvh(skel: dict, rename: dict) -> str:
    """Write a skeleton (Z up) as a Y-up BVH header plus one motion frame."""
    by = {b["name"]: b for b in skel["bones"]}
    kids: dict = {}
    for b in skel["bones"]:
        kids.setdefault(b["parent"], []).append(b["name"])

    def yup(v):  # inverse of (x, y, z) -> (x, -z, y)
        return np.array([v[0], v[2], -v[1]]) * 100.0  # centimetres

    lines = ["HIERARCHY"]

    def emit(name, depth):
        b, pad = by[name], "  " * depth
        off = yup(b["head"]) - (yup(by[b["parent"]]["head"]) if b["parent"] else 0)
        lines.append(f"{pad}{'ROOT' if depth == 0 else 'JOINT'} {rename.get(name, name)}")
        lines.append(pad + "{")
        lines.append(f"{pad}  OFFSET {off[0]:.4f} {off[1]:.4f} {off[2]:.4f}")
        lines.append(f"{pad}  CHANNELS {'6 Xposition Yposition Zposition' if depth == 0 else '3'}"
                     " Zrotation Xrotation Yrotation")
        if kids.get(name):
            for k in kids[name]:
                emit(k, depth + 1)
        else:
            e = yup(b["tail"]) - yup(b["head"])
            lines.extend([pad + "  End Site", pad + "  {", f"{pad}    OFFSET {e[0]:.4f} {e[1]:.4f} {e[2]:.4f}",
                          pad + "  }"])
        lines.append(pad + "}")

    emit(kids[None][0], 0)
    n_ch = 6 + 3 * (len(skel["bones"]) - 1)
    lines += ["MOTION", "Frames: 1", "Frame Time: 0.0333333", " ".join(["0"] * n_ch)]
    return "\n".join(lines) + "\n"


def selftest() -> int:
    checks = []

    def check(name, cond, detail=None):
        checks.append({"name": name, "pass": bool(cond), **({"detail": detail} if detail is not None else {})})

    def gate_of(rep, name):
        return next((g for g in rep["gates"] if g["name"] == name), {"pass": None})

    contract = contract_skeleton(1.7)
    check("contract has 15 Unity-required bones", len(REQUIRED) == 15)
    check("contract has 30 finger bones", len(FINGER_BONES) == 30)
    check("Unity finger names say Little, not Pinky",
          any(b["unity"] == "Left Little Distal" for b in CONTRACT) and not any("Pinky" in (b["unity"] or "")
                                                                                 for b in CONTRACT))

    rep = evaluate(normalise_skeleton(contract), "auto", "contract", 10)
    check("full contract passes --require contract", rep["ok"] and rep["preset"] == "contract",
          [g for g in rep["gates"] if not g["pass"]])

    no_root = _renamed(contract, {}, drop=("Root",))
    rep = evaluate(normalise_skeleton(no_root), "contract", "unity")
    check("no Root passes the unity tier", rep["ok"], [g for g in rep["gates"] if not g["pass"]])
    rep = evaluate(normalise_skeleton(no_root), "contract", "contract")
    check("no Root fails the contract tier", not rep["ok"] and "Root" in gate_of(rep, "contract")["missing"])

    deform_root = json.loads(json.dumps(contract))
    deform_root["bones"][0]["deform"] = True
    rep = evaluate(normalise_skeleton(deform_root), "contract", "contract")
    check("deforming Root fails the contract tier", not gate_of(rep, "contract")["pass"])

    tpose = json.loads(json.dumps(contract))
    by = {b["name"]: b for b in tpose["bones"]}
    for side, s in (("L", 1), ("R", -1)):
        ua = np.array(by[f"UpperArm.{side}"]["head"])
        by[f"LowerArm.{side}"]["head"] = (ua + np.array([s * 0.29, 0, 0])).tolist()
    rep = evaluate(normalise_skeleton(tpose), "contract", "contract")
    check("a T-pose fails the contract rest", not gate_of(rep, "contract")["pass"])

    # Mixamo-named skeleton without the namespace, via a BVH header, Y up, cm. Its LeftLeg is the
    # LOWER leg (LeftUpLeg the thigh), so the map orientation and the leg chain are both exercised.
    cbones = {b["name"] for b in CONTRACT}
    mixamo = BUILTIN["mixamo"]["bones"]
    rename = {c: v[0] for c, v in mixamo.items()}
    mix_skel = _renamed(contract, rename, drop=("Root",))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bvh = tmp / "mixamo.bvh"
        bvh.write_text(_to_bvh(_renamed(contract, {}, drop=("Root",)), rename), encoding="utf-8")
        sk = load_skeleton(bvh, 0.01)
        head_l = next(b for b in sk["bones"] if b["name"] == "LeftHand")["head"]
        ref_l = next(b for b in contract["bones"] if b["name"] == "Hand.L")["head"]
        check("BVH header round-trips to Z up in metres", np.allclose(head_l, ref_l, atol=1e-4), [head_l, ref_l])
        check("BVH root carries position channels",
              any("position" in c.lower() for c in sk["bones"][0].get("channels", [])))
        rep = evaluate(sk, "auto", "unity", 10)
        check("Mixamo BVH auto-picks mixamo and passes", rep["ok"] and rep["preset"] == "mixamo",
              [rep["preset"], [g for g in rep["gates"] if not g["pass"]]])
        check("retarget_map is contract -> source", rep["retarget_map"].get("UpperLeg.L") == "LeftUpLeg"
              and rep["retarget_map"].get("LowerLeg.L") == "LeftLeg")
        check("human map names Chest", any(h["humanName"] == "Chest" for h in rep["human"]))

        # CLI: exit 0 on the BVH, exit 2 with Hips missing, exit 1 on garbage
        script = str(Path(__file__).resolve())
        r = subprocess.run([sys.executable, script, "map", str(bvh), "--scale", "0.01",
                            "--unity-out", str(tmp / "h.json")], capture_output=True, text=True)
        check("CLI map on a good BVH exits 0", r.returncode == 0, r.stdout[-300:])
        hm = json.loads((tmp / "h.json").read_text())
        check("--unity-out writes unity-human-map/1", hm.get("schema") == "unity-human-map/1" and hm["human"])

        no_hips = _renamed(mix_skel, {}, drop=("Hips",))
        (tmp / "nohips.json").write_text(json.dumps(no_hips))
        r = subprocess.run([sys.executable, script, "map", str(tmp / "nohips.json"), "--map", "mixamo"],
                           capture_output=True, text=True)
        out = json.loads(r.stdout)
        check("missing Hips exits 2", r.returncode == 2 and "Hips" in out["missing_required"], r.stdout[-300:])

        (tmp / "noroot.json").write_text(json.dumps(no_root))
        r = subprocess.run([sys.executable, script, "map", str(tmp / "noroot.json"), "--map", "contract",
                            "--require", "contract"], capture_output=True, text=True)
        check("CLI --require contract without Root exits 2", r.returncode == 2, r.stdout[-200:])
        mirrored = json.loads(json.dumps(contract))
        for bb in mirrored["bones"]:
            bb["head"][0], bb["tail"][0] = -bb["head"][0], -bb["tail"][0]
        (tmp / "mirrored.json").write_text(json.dumps(mirrored))
        r = subprocess.run([sys.executable, script, "map", str(tmp / "mirrored.json")], capture_output=True, text=True)
        check("CLI on swapped sides exits 2", r.returncode == 2, r.stdout[-200:])
        leg = json.loads(json.dumps(mix_skel))
        for bb in leg["bones"]:
            if bb["name"] == "LeftLeg":
                bb["parent"] = "RightUpLeg"
        (tmp / "leg.json").write_text(json.dumps(leg))
        r = subprocess.run([sys.executable, script, "map", str(tmp / "leg.json"), "--map", "mixamo"],
                           capture_output=True, text=True)
        check("CLI on a broken chain exits 2", r.returncode == 2, r.stdout[-200:])
        (tmp / "nofingers.json").write_text(json.dumps(_renamed(contract, {}, drop=tuple(FINGER_BONES))))
        r = subprocess.run([sys.executable, script, "map", str(tmp / "nofingers.json"), "--min-fingers", "10"],
                           capture_output=True, text=True)
        check("CLI --min-fingers 10 on a fingerless rig exits 2", r.returncode == 2, r.stdout[-200:])

        (tmp / "bad.bvh").write_text("HIERARCHY\nROOT Hips\n{\n  OFFSET 0 0\n")
        r = subprocess.run([sys.executable, script, "map", str(tmp / "bad.bvh")], capture_output=True, text=True)
        check("malformed BVH exits 1", r.returncode == 1, r.stdout[-200:])
        r = subprocess.run([sys.executable, script, "map", str(tmp / "nohips.json"), "--map", "nope"],
                           capture_output=True, text=True)
        check("unknown preset exits 1", r.returncode == 1)

    # parent chain: the left lower leg hung under the right thigh
    broken = json.loads(json.dumps(mix_skel))
    for b in broken["bones"]:
        if b["name"] == "LeftLeg":
            b["parent"] = "RightUpLeg"
    rep = evaluate(normalise_skeleton(broken), "mixamo", "unity")
    check("a leg under the wrong hip fails parent_chain", not gate_of(rep, "parent_chain")["pass"])

    # parent chain: a finger under the forearm
    broken = json.loads(json.dumps(mix_skel))
    for b in broken["bones"]:
        if b["name"] == "LeftHandIndex2":
            b["parent"] = "LeftForeArm"
    rep = evaluate(normalise_skeleton(broken), "mixamo", "unity")
    check("a finger under the forearm fails parent_chain", not gate_of(rep, "parent_chain")["pass"])

    # sides swapped
    swapped = json.loads(json.dumps(contract))
    for b in swapped["bones"]:
        b["head"][0], b["tail"][0] = -b["head"][0], -b["tail"][0]
    rep = evaluate(normalise_skeleton(swapped), "contract", "unity")
    check("mirrored .L/.R fails sides", not gate_of(rep, "sides")["pass"])

    # Y-up dump declared +Z: the up axis is wrong
    lying = json.loads(json.dumps(contract))
    for b in lying["bones"]:
        b["head"] = [b["head"][0], b["head"][2], -b["head"][1]]
        b["tail"] = [b["tail"][0], b["tail"][2], -b["tail"][1]]
    rep = evaluate(normalise_skeleton(lying), "contract", "unity")
    check("a Y-up skeleton read as Z-up fails axes", not gate_of(rep, "axes")["pass"])
    lying["up"] = "+Y"
    rep = evaluate(normalise_skeleton(lying), "contract", "unity")
    check("the same skeleton declared +Y passes axes", gate_of(rep, "axes")["pass"])

    # duplicate: one source bone for two contract bones
    rm = {"name": "dup", "bones": {"Hand.L": ["Hand.L"], "LowerArm.L": ["Hand.L"]}}
    BUILTIN["_dup"] = rm
    rep = evaluate(normalise_skeleton(contract), "_dup", "unity")
    del BUILTIN["_dup"]
    check("a source bone mapped twice fails unique", not gate_of(rep, "unique")["pass"])

    # fingers gate
    nof = _renamed(contract, {}, drop=tuple(FINGER_BONES))
    rep = evaluate(normalise_skeleton(nof), "contract", "unity", 10)
    check("no fingers fails --min-fingers 10", not gate_of(rep, "fingers")["pass"])

    # presets: Mixamo, ARP, ARP-UE names auto-detected
    for preset in ("mixamo", "arp", "arp-ue"):
        ren = {c: v[0] for c, v in BUILTIN[preset]["bones"].items()}
        if preset == "mixamo":
            ren = {c: "mixamorig:" + n for c, n in ren.items()}
        drop = ("Root",) if "Root" not in ren else ()
        rep = evaluate(normalise_skeleton(_renamed(contract, ren, drop=drop)), "auto", "unity", 10)
        check(f"{preset} names auto-detected and pass", rep["ok"] and rep["preset"] == preset,
              [rep["preset"], [g for g in rep["gates"] if not g["pass"]]])

    # suggest on a UE-style pack names most of the body
    ren = {c: v[0] for c, v in BUILTIN["arp-ue"]["bones"].items()}
    sug = suggest(normalise_skeleton(_renamed(contract, ren)))
    hit = sum(1 for c, n in sug["bones"].items() if ren.get(c) == n)
    check("suggest recovers a UE-style pack's body", all(sug["bones"].get(r) == ren[r] for r in REQUIRED)
          and hit >= 40, {"hit": hit})
    check("names-only skeleton is read", evaluate(normalise_skeleton(
        [{"name": b["name"], "parent": b["parent"]} for b in contract["bones"]]), "contract")["ok"])
    check("all contract names unique", len(cbones) == len(CONTRACT))

    failed = [c for c in checks if not c["pass"]]
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": len(checks),
                      "failed": failed}))
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
