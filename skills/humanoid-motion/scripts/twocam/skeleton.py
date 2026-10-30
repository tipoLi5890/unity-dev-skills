#!/usr/bin/env python3
"""skeleton.py — the humanoid contract skeleton as the two-camera solve's rig: bones, keypoints, feet, limits, paint.

Replaces patch-gg/anymove's per-creature rig.json and the rig half of blender/common.py (load_rig, mirror,
write_rig_info, LEG_BONES / LEG_COLORS) and the hard-coded paw names of mocap/solve.py (LEGS, fpaw/ftoe/hpaw/htoe),
commit 7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0. Changes from upstream: the bones, the feet,
the limb pairs and the limb paint come from the humanoid contract (skills/unity-rigged-character/reference/
humanoid-contract.md) instead of a hand-written rig.json; the joint limits are a humanoid table written in an
anatomical frame per bone (X = flexion about the body's left-right axis, Y = twist about the bone, Z = the third
axis), so they mean the same whatever roll the rigging tool gave the bone, the right side mirrored from the left;
the ground term gets a clearance per foot joint (its rest height) instead of z >= 0; the rig_info.json written
here keeps upstream's fields, so the ported solve reads both.

The rig_info.json carries what the solve needs to redo Blender's forward kinematics: per bone its name, parent
index, rest matrix (armature space, 4 x 4 rows), length, head and tail keypoint, limits_deg and limit_frame
(the 3 x 3 rotation from the anatomical frame to the bone's local frame); per keypoint its bone, end and rest
position; the layout; and a "twocam" block (feet, ground clearances, limb pairs, paint groups and colours, the
prompt's colour sentence). Fingers are not solved: they stay at rest here, and a fixed hand shape goes on after.
Root (the contract's non-deform bone at the origin) is not solved either: Hips is the solve's root, with free
rotation and translation.

Blender writes the real rig_info from the rigged character (blender/prepare_rig.py, which reads the rest matrices
with their roll); this script builds one from a skeleton/1 JSON with Blender's roll-0 rule, for the selftests,
the exam and a quick look before Blender.

usage:
    skeleton.py rig-info SKELETON.json --out RIG_INFO.json [--map ROLE_MAP.json] [--height 1.7]
    skeleton.py limits            the limit table, left side, degrees
    skeleton.py --selftest
SKELETON.json: skeleton/1 as `contract_map.py contract --out` writes it (bones with name, parent, head, tail;
"up": "+Z"; "+Y" is turned with (x, y, z) -> (x, -z, y)). --map: a role-map/1 file {"bones": {contract: source}}
when the armature's bones carry other names (`contract_map.py map ... --map-out`).
Prints one JSON object. Exit codes: 0 every gate passed, 2 a gate failed (a required bone missing, sides
mirrored, not upright), 1 refused input or a failed selftest.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

# --- the contract's bones the solve moves, in solve order (parents first) ---------------------------------------
CENTRE = ["Hips", "Spine", "Chest", "UpperChest", "Neck", "Head"]
ARM = ["Shoulder", "UpperArm", "LowerArm", "Hand"]
LEG = ["UpperLeg", "LowerLeg", "Foot", "Toes"]
CONTRACT_PARENT = {"Hips": None, "Spine": "Hips", "Chest": "Spine", "UpperChest": "Chest", "Neck": "UpperChest",
                   "Head": "Neck"}
for _s in ("L", "R"):
    CONTRACT_PARENT.update({f"Shoulder.{_s}": "UpperChest", f"UpperArm.{_s}": f"Shoulder.{_s}",
                            f"LowerArm.{_s}": f"UpperArm.{_s}", f"Hand.{_s}": f"LowerArm.{_s}",
                            f"UpperLeg.{_s}": "Hips", f"LowerLeg.{_s}": f"UpperLeg.{_s}",
                            f"Foot.{_s}": f"LowerLeg.{_s}", f"Toes.{_s}": f"Foot.{_s}"})
SOLVE_BONES = CENTRE + [f"{b}.{s}" for s in ("L", "R") for b in ARM] + [f"{b}.{s}" for s in ("L", "R") for b in LEG]
FINGERS = [f"{f}{i}" for f in ("Thumb", "Index", "Middle", "Ring", "Little") for i in (1, 2, 3)]
# keypoint names for a bone's tail when no solved child starts there
TIP = {"Head": "HeadTop", "Hand": "HandTip", "Toes": "ToesTip"}

# Euler XYZ limits in degrees, in the anatomical frame, left side and centre. For the right side Y and Z mirror
# ([lo, hi] -> [-hi, -lo]); X keeps its sign (flexion is flexion on both sides).
#   centre bones (along +Z): X + bends forward, Z + leans to the character's left... (see reference/two-camera.md)
#   legs (along -Z):         X + swings the bone backward (hip extension, knee flexion), Z + adducts
#   arms (A-pose):           X + swings the arm backward, Z + lowers it toward the body
#   foot / toes:             X + points the toes down
LIMITS_DEG = {
    "Hips": [[-30, 30], [-20, 20], [-30, 30]],          # root: its rotation is free; these only bound a prior
    "Spine": [[-25, 40], [-25, 25], [-20, 20]],
    "Chest": [[-15, 25], [-20, 20], [-15, 15]],
    "UpperChest": [[-10, 20], [-15, 15], [-10, 10]],
    "Neck": [[-40, 50], [-50, 50], [-30, 30]],
    "Head": [[-35, 35], [-50, 50], [-30, 30]],
    "Shoulder": [[-25, 25], [-10, 10], [-35, 12]],
    "UpperArm": [[-170, 60], [-80, 80], [-125, 50]],
    "LowerArm": [[-150, 5], [-85, 85], [-12, 12]],
    "Hand": [[-70, 70], [-20, 20], [-35, 35]],
    "UpperLeg": [[-125, 35], [-40, 40], [-50, 25]],
    "LowerLeg": [[-5, 150], [-10, 10], [-6, 6]],
    "Foot": [[-30, 50], [-20, 20], [-20, 20]],
    "Toes": [[-50, 30], [-5, 5], [-5, 5]],
}
# limb paint: every limb its own colour, so left and right never swap (upstream LEG_COLORS, upright limbs)
PAINT = {"ArmL": ("#F53CD1", "pink", "left arm"), "ArmR": ("#2F6BFF", "blue", "right arm"),
         "LegL": ("#FFD21F", "yellow", "left leg"), "LegR": ("#19D3E0", "cyan", "right leg")}

SAFE, CRITICAL = 6.1e-3, 2.5e-4


def side_of(name: str) -> str:
    """'L', 'R' or '' from a contract (.L) or upstream (_L) suffix."""
    for s in ("L", "R"):
        if name.endswith((f".{s}", f"_{s}")):
            return s
    return ""


def mirror_name(name: str) -> str:
    s = side_of(name)
    return name[:-1] + {"L": "R", "R": "L"}[s] if s else name


def stem(name: str) -> str:
    return name[:-2] if side_of(name) else name


def roll0_matrix(head, tail) -> np.ndarray:
    """Blender's bone rest rotation for a bone from head to tail with roll 0 (vec_roll_to_mat3): columns x, y, z."""
    d = np.asarray(tail, float) - np.asarray(head, float)
    n = d / np.linalg.norm(d)
    x, y, z = n
    theta, alt = 1 + y, x * x + z * z
    if theta > SAFE or alt > CRITICAL * CRITICAL:
        if theta <= SAFE:
            theta = alt * 0.5 + alt * alt * 0.125
        cols = np.array([[1 - x * x / theta, -x, -x * z / theta], [x, y, z], [-x * z / theta, -z, 1 - z * z / theta]])
    else:
        cols = np.array([[-1.0, 0, 0], [0, -1.0, 0], [0, 0, 1.0]])
    return cols.T   # rows of the matrix; column i is axis i


def matrix_local(head, tail) -> list:
    M = np.eye(4)
    M[:3, :3] = roll0_matrix(head, tail)
    M[:3, 3] = head
    return M.tolist()


def _left_frame(d) -> np.ndarray:
    """Anatomical frame for a left or centre bone along unit d: y = d, x = world +X off d (world +Z when the bone
    runs within ~18 deg of X, the clavicle), z = x cross y."""
    d = d / np.linalg.norm(d)
    ref = np.array([1.0, 0, 0]) if abs(d[0]) < 0.95 else np.array([0, 0, 1.0])
    x = ref - ref.dot(d) * d
    x /= np.linalg.norm(x)
    return np.stack([x, d, np.cross(x, d)], 1)


def anatomical_frame(d, side: str) -> np.ndarray:
    """Columns x, y, z in armature space. A right bone gets its mirrored direction's left frame mirrored back as
    (-Mx, My, Mz), M = diag(-1, 1, 1): a right-handed frame in which X keeps its meaning and Y, Z mirror."""
    d = np.asarray(d, float)
    if side != "R":
        return _left_frame(d)
    M = np.diag([-1.0, 1, 1])
    A = _left_frame(M @ d)
    return np.stack([-(M @ A[:, 0]), M @ A[:, 1], M @ A[:, 2]], 1)


def mat_to_quat(R) -> np.ndarray:
    """Rotation matrices (..., 3, 3) to unit quaternions (w, x, y, z), w >= 0, by the largest-diagonal branch
    (accurate for every rotation, unlike the copysign formula whose small components lose ~1e-5)."""
    R = np.asarray(R, float)
    flat = R.reshape(-1, 3, 3)
    out = np.empty((len(flat), 4))
    for n, m in enumerate(flat):
        t = np.trace(m)
        if t > 0:
            s = 2 * np.sqrt(1 + t)
            q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
        elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
            s = 2 * np.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2])
            q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
        elif m[1, 1] > m[2, 2]:
            s = 2 * np.sqrt(1 - m[0, 0] + m[1, 1] - m[2, 2])
            q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
        else:
            s = 2 * np.sqrt(1 - m[0, 0] - m[1, 1] + m[2, 2])
            q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
        q = np.asarray(q)
        q /= np.linalg.norm(q)
        out[n] = q if q[0] >= 0 else -q
    return out.reshape(*R.shape[:-2], 4)


def limits_for(contract: str) -> list:
    lim = [list(r) for r in LIMITS_DEG[stem(contract)]]
    if side_of(contract) == "R":
        lim[1], lim[2] = [-lim[1][1], -lim[1][0]], [-lim[2][1], -lim[2][0]]
    return lim


# --- skeleton/1 in --------------------------------------------------------------------------------------------
class Refused(ValueError):
    pass


def read_skeleton(doc) -> dict:
    """skeleton/1 (list form or {name: {...}} form) -> {name: {parent, head, tail, matrix_local?}} in +Z up."""
    bones = doc.get("bones") if isinstance(doc, dict) else doc
    if isinstance(bones, dict):
        bones = [{"name": k, **v} for k, v in bones.items()]
    if not isinstance(bones, list) or not bones:
        raise Refused("no bones")
    yup = isinstance(doc, dict) and str(doc.get("up", "+Z")).upper() in ("+Y", "Y")
    out = {}
    for b in bones:
        if "head" not in b or "tail" not in b:
            raise Refused(f"bone {b.get('name')} has no head/tail")
        h, t = np.asarray(b["head"], float), np.asarray(b["tail"], float)
        if yup:
            h, t = np.array([h[0], -h[2], h[1]]), np.array([t[0], -t[2], t[1]])
        out[b["name"]] = {"parent": b.get("parent"), "head": h, "tail": t, "matrix_local": b.get("matrix_local")}
    return out


def build_rig_info(skel: dict, role_map: dict | None = None, layout: dict | None = None) -> tuple:
    """Return (rig_info, gates). skel: {armature bone: {parent, head, tail, matrix_local?}} in armature space."""
    role = {k: (v if isinstance(v, str) else next((c for c in v if c in skel), v[0]))
            for k, v in (role_map or {}).items()}
    src = {c: role.get(c, c) for c in SOLVE_BONES}
    missing = [c for c in SOLVE_BONES if src[c] not in skel]
    gates = [{"name": "rig.required_bones", "value": missing, "limit": "the 22 contract body bones", "pass": not missing}]
    if missing:
        return None, gates
    head = {c: skel[src[c]]["head"] for c in SOLVE_BONES}
    tail = {c: skel[src[c]]["tail"] for c in SOLVE_BONES}
    sides = all(head[f"{b}.L"][0] > head[f"{b}.R"][0] for b in ("UpperArm", "UpperLeg", "Hand", "Foot"))
    upright = head["Head"][2] > head["Hips"][2] > head["Foot.L"][2] and tail["Toes.L"][1] < head["Foot.L"][1]
    gates += [{"name": "rig.sides", "value": sides, "limit": ".L at +X", "pass": bool(sides)},
              {"name": "rig.upright", "value": bool(upright), "limit": "Head > Hips > Foot in Z, toes at -Y",
               "pass": bool(upright)}]
    order = SOLVE_BONES
    idx = {c: i for i, c in enumerate(order)}
    # each bone's tail keypoint: a solved child whose head sits on the tail (1 mm), else a tip keypoint
    child_on_tail = {}
    for c in order:
        p = CONTRACT_PARENT[c]
        if p and np.linalg.norm(head[c] - tail[p]) < 1e-3 and p not in child_on_tail:
            child_on_tail[p] = c
    kps, bones = [], []
    seen = set()

    def kp(name, bone, end, rest):
        if name not in seen:
            seen.add(name)
            kps.append({"name": name, "bone": idx[bone], "end": end, "rest": [round(float(v), 6) for v in rest]})

    for c in order:
        tail_kp = child_on_tail.get(c) or (TIP.get(stem(c), stem(c) + "Tip") + (f".{side_of(c)}" if side_of(c) else ""))
        ml = skel[src[c]]["matrix_local"]
        M = np.asarray(ml, float) if ml is not None else np.asarray(matrix_local(head[c], tail[c]))
        A = anatomical_frame(tail[c] - head[c], side_of(c))
        C = M[:3, :3].T @ A
        par = CONTRACT_PARENT[c]
        bones.append({"name": src[c], "contract": c, "parent": idx[par] if par else -1,
                      "matrix_local": M.round(9).tolist(), "length": float(np.linalg.norm(tail[c] - head[c])),
                      "head_joint": c, "tail_joint": tail_kp, "limits_deg": limits_for(c),
                      "limit_frame": C.round(9).tolist()})
    for i, c in enumerate(order):
        kp(c, c, "head", head[c])
        if bones[i]["tail_joint"] not in idx:
            kp(bones[i]["tail_joint"], c, "tail", tail[c])
    names = [k["name"] for k in kps]
    rest = {k["name"]: k["rest"] for k in kps}
    feet = [n for n in names if stem(n) in ("Foot", "Toes", "ToesTip")]
    ground = {n: round(max(0.0, rest[n][2]), 6) for n in feet}
    pairs = {"arm": [], "leg": []}
    for n in names:
        if side_of(n) == "L" and mirror_name(n) in names:
            limb = "leg" if stem(n) in LEG + ["ToesTip"] else "arm"
            pairs[limb].append([n, mirror_name(n)])
    paint = {}
    for key, (hexcol, word, what) in PAINT.items():
        s = key[-1]
        chain = ARM if key.startswith("Arm") else LEG
        bnames = [src[f"{b}.{s}"] for b in chain if b != "Shoulder"]
        if key.startswith("Arm"):
            bnames += [role.get(f"{f}.{s}", f"{f}.{s}") for f in FINGERS if role.get(f"{f}.{s}", f"{f}.{s}") in skel]
        paint[key] = {"color": hexcol, "word": word, "limb": what, "bones": bnames}
    colour_code = ", ".join(f"{v['limb']} {v['word']}" for v in paint.values())
    info = {"bones": bones, "keypoints": kps, "layout": layout or {},
            "twocam": {"schema": "twocam-rig/1", "root": src["Hips"], "agreement_joints": [n for n in feet if stem(n) in ("Foot", "Toes")],
                       "feet": feet, "ground": ground, "limb_pairs": pairs, "paint": paint,
                       "colour_code": colour_code, "count": "Exactly two arms, two legs, one head.",
                       "fingers": "rest", "contract_names": {src[c]: c for c in order}}}
    return info, gates


# --- selftest -------------------------------------------------------------------------------------------------
def demo_skeleton(height=1.7) -> dict:
    """The contract's body proportions (A-pose, +Z up, facing -Y) as skeleton/1, for selftests and the exam."""
    k = height / 1.7
    P = {"Root": ([0, 0, 0], [0, 0.17, 0]), "Hips": ([0, 0, .901], [0, 0, .986]), "Spine": ([0, 0, .986], [0, 0, 1.105]),
         "Chest": ([0, 0, 1.105], [0, 0, 1.224]), "UpperChest": ([0, 0, 1.224], [0, 0, 1.394]),
         "Neck": ([0, 0, 1.394], [0, 0, 1.479]), "Head": ([0, 0, 1.479], [0, 0, 1.7])}
    for s, sx in (("L", 1), ("R", -1)):
        P.update({f"Shoulder.{s}": ([.034 * sx, 0, 1.36], [.17 * sx, 0, 1.36]),
                  f"UpperArm.{s}": ([.17 * sx, 0, 1.36], [.37435 * sx, 0, 1.15565]),
                  f"LowerArm.{s}": ([.37435 * sx, 0, 1.15565], [.55467 * sx, 0, .97533]),
                  f"Hand.{s}": ([.55467 * sx, 0, .97533], [.62679 * sx, 0, .90321]),
                  f"UpperLeg.{s}": ([.153 * sx, 0, .85], [.153 * sx, 0, .459]),
                  f"LowerLeg.{s}": ([.153 * sx, 0, .459], [.153 * sx, 0, .068]),
                  f"Foot.{s}": ([.153 * sx, 0, .068], [.153 * sx, -.17, .017]),
                  f"Toes.{s}": ([.153 * sx, -.17, .017], [.153 * sx, -.255, .017])})
    parent = dict(CONTRACT_PARENT, Root=None, Hips="Root")
    return {"schema": "skeleton/1", "up": "+Z", "forward": "-Y", "units": "m",
            "bones": [{"name": n, "parent": parent[n], "head": [v * k for v in h], "tail": [v * k for v in t]}
                      for n, (h, t) in P.items()]}


def selftest() -> int:
    checks = []

    def check(name, cond):
        checks.append({"name": name, "pass": bool(cond)})

    for h, t in (([0, 0, 0], [0, 0, 1]), ([0, 0, 0], [0.3, -0.2, -0.9]), ([0, 0, 0], [0, -1, 0]), ([0, 0, 0], [0, 1, 0])):
        R = roll0_matrix(h, t)
        d = np.subtract(t, h) / np.linalg.norm(np.subtract(t, h))
        check(f"roll0 y axis along the bone {t}", np.allclose(R[:, 1], d))
        check(f"roll0 orthonormal {t}", np.allclose(R.T @ R, np.eye(3)) and np.isclose(np.linalg.det(R), 1))
    for d in ([0.7, 0, -0.7], [1, 0, 0], [0, -0.95, -0.3], [0, 0, 1]):
        AL = anatomical_frame(np.array(d), "L")
        AR = anatomical_frame(np.diag([-1, 1, 1]) @ np.array(d, float), "R")
        check(f"frame right-handed {d}", np.isclose(np.linalg.det(AL), 1) and np.isclose(np.linalg.det(AR), 1))
        check(f"frame mirrors {d}", np.allclose(AR[:, 0], -(np.diag([-1, 1, 1]) @ AL[:, 0])))
    check("right limits mirror Y and Z", limits_for("UpperLeg.R") == [[-125, 35], [-40, 40], [-25, 50]])
    info, gates = build_rig_info(read_skeleton(demo_skeleton()))
    check("demo contract passes", all(g["pass"] for g in gates))
    names = [k["name"] for k in info["keypoints"]]
    check("22 bones", len(info["bones"]) == 22)
    check("keypoints: heads plus HeadTop, HandTip, ToesTip", len(names) == 22 + 1 + 2 + 2 and "ToesTip.R" in names)
    check("Hips is the root", info["bones"][0]["contract"] == "Hips" and info["bones"][0]["parent"] == -1)
    check("feet from the contract", set(info["twocam"]["agreement_joints"]) == {"Foot.L", "Foot.R", "Toes.L", "Toes.R"})
    check("ground clearance is the rest height", abs(info["twocam"]["ground"]["Foot.L"] - 0.068) < 1e-6)
    check("leg pairs", ["Foot.L", "Foot.R"] in info["twocam"]["limb_pairs"]["leg"])
    check("colour sentence", info["twocam"]["colour_code"].startswith("left arm pink, right arm blue"))
    hips = info["bones"][0]
    check("Hips tail keypoint is Spine", hips["tail_joint"] == "Spine")
    # FK at rest reproduces the keypoints
    ok = True
    for k in info["keypoints"]:
        b = info["bones"][k["bone"]]
        M = np.asarray(b["matrix_local"])
        p = M[:3, 3] if k["end"] == "head" else M[:3, 3] + M[:3, 1] * b["length"]
        ok &= np.allclose(p, k["rest"], atol=1e-5)
    check("rest FK lands on the keypoints", ok)
    # failing inputs: a missing foot, mirrored sides, upside down
    sk = demo_skeleton(); sk["bones"] = [b for b in sk["bones"] if b["name"] != "Foot.L"]
    _, g = build_rig_info(read_skeleton(sk))
    check("missing Foot.L fails rig.required_bones", not g[0]["pass"])
    sk = demo_skeleton()
    for b in sk["bones"]:
        b["head"][0] *= -1; b["tail"][0] *= -1
    _, g = build_rig_info(read_skeleton(sk))
    check("mirrored sides fail rig.sides", not next(x for x in g if x["name"] == "rig.sides")["pass"])
    sk = demo_skeleton(); sk["up"] = "+Y"
    _, g = build_rig_info(read_skeleton(sk))
    check("a Z-up file read as Y-up fails rig.upright", not next(x for x in g if x["name"] == "rig.upright")["pass"])
    # role map: other armature names
    sk = demo_skeleton()
    for b in sk["bones"]:
        b["name"] = "src_" + b["name"]; b["parent"] = b["parent"] and "src_" + b["parent"]
    info2, g = build_rig_info(read_skeleton(sk), {c: "src_" + c for c in SOLVE_BONES})
    check("role map", all(x["pass"] for x in g) and info2["bones"][0]["name"] == "src_Hips")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "sk.json"; p.write_text(json.dumps(demo_skeleton()))
        o = Path(td) / "ri.json"
        code = main(["rig-info", str(p), "--out", str(o)], quiet=True)
        check("CLI writes rig_info, exit 0", code == 0 and o.exists())
        sk = demo_skeleton(); sk["bones"] = [b for b in sk["bones"] if b["name"] != "Toes.R"]
        p.write_text(json.dumps(sk))
        check("CLI exit 2 on a missing bone", main(["rig-info", str(p), "--out", str(o)], quiet=True) == 2)
        p.write_text("{not json")
        check("CLI exit 1 on unreadable input", main(["rig-info", str(p), "--out", str(o)], quiet=True) == 1)
    ok = all(c["pass"] for c in checks)
    print(json.dumps({"tool": "skeleton.py", "selftest": "pass" if ok else "fail", "checks": len(checks),
                      "failed": [c["name"] for c in checks if not c["pass"]]}))
    return 0 if ok else 1


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main(argv=None, quiet=False) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv or argv[:1] == ["selftest"]:
        return selftest()
    ap = UsageParser(prog="skeleton.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rig-info")
    r.add_argument("skeleton"); r.add_argument("--out", required=True); r.add_argument("--map")
    r.add_argument("--height", type=float, help="character height for the layout (default: the Head tail)")
    sub.add_parser("limits")
    a = ap.parse_args(argv)
    emit = (lambda d: None) if quiet else (lambda d: print(json.dumps(d)))
    if a.cmd == "limits":
        emit({"tool": "skeleton.py", "op": "limits", "frame": "anatomical, left side", "limits_deg": LIMITS_DEG})
        return 0
    try:
        doc = json.loads(Path(a.skeleton).read_text(encoding="utf-8"))
        role = json.loads(Path(a.map).read_text(encoding="utf-8")).get("bones") if a.map else None
        skel = read_skeleton(doc)
    except (OSError, ValueError, json.JSONDecodeError, Refused) as exc:
        emit({"tool": "skeleton.py", "ok": False, "error": f"refused: {exc}"}); return 1
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from layout import Layout
    info, gates = build_rig_info(skel, role)
    ok = all(g["pass"] for g in gates)
    out = {"tool": "skeleton.py", "op": "rig-info", "gates": gates, "ok": ok}
    if info is not None:
        top = max(b["head"][2] for b in skel.values()) if a.height is None else a.height
        top = max(top, max(b["tail"][2] for b in skel.values())) if a.height is None else top
        info["layout"] = Layout.humanoid(float(top)).as_dict()
        if ok:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(json.dumps(info, indent=1), encoding="utf-8")
            out.update({"out": a.out, "bones": len(info["bones"]), "keypoints": len(info["keypoints"]),
                        "layout": info["layout"]})
    emit(out)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
