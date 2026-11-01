#!/usr/bin/env python3
"""rig_exam.py — score the automatic rig against bodies whose joints are known, so a change is measured, not guessed.

usage:
    rig_exam.py build  EXAM [--only standard,chibi] [--seed 0] [--faces 40000]   the cast: EXAM/cast/NAME.glb + .truth.json
    rig_exam.py run    EXAM [--only ...] [--smart] [--refs] [--threads 4]       autorig.py all per body -> EXAM/runs/NAME/
    rig_exam.py faults EXAM [--base standard] [--only elbow_shift,...] [--fbx F --contract C]
                                                                                known defects on a good rig -> EXAM/faults/
    rig_exam.py reference EXAM NAME --glb G --markers M [--fbx F --contract C]  add a rig a person accepted -> EXAM/refs/NAME/
    rig_exam.py score  EXAM [--tol 0.04] [--out EXAM/exam.json] [--sheet EXAM/sheet.png]
    rig_exam.py --selftest
build, run, faults and reference's rig check take --blender PATH (env BLENDER, else autorig.py's default) and
--threads N; they run Blender one call at a time. score is numpy (Pillow for the sheet) and needs no Blender.

The cast (rig_exam_blender.py): metaball bodies built around a known skeleton, seeded, about 40k triangles each:
standard, chibi (a big head on short limbs and mittens, run with --body chibi), heavy, thin (arms 55 deg), long_limbs (arms
30 deg), mitten (fingers fused), spiky_hair (hair raising the top), skirt (a solid skirt over the crotch, run with
--body skirt), asym (a
few degrees and millimetres apart). Each truth file (exam/1, kind truth) holds the joints the body was built from.

run: `autorig.py all EXAM/runs/NAME EXAM/cast/NAME.glb --name NAME --height H --no-smart` (H the body's own height, so
the prep only grounds and centres it); a run that stops before the markers has them measured apart
(--no-window-gate, rig/NAME.markers_only.json) so its landmarks are still scored. --smart drops --no-smart: Auto-Rig Pro's AI runs, and its agreement with
the slices (the markers' smart_agreement) is recorded as a second opinion. It is never truth, never a label and
never used to set a limit. A reference case runs the same way, and its accepted rig is gated again with the
current deform_gate.py (EXAM/refs/NAME/accepted.deform.json).

faults, on a copy of the base rig (the markers file moved with arp_markers.py --adjust, then arp, contract, deform
without the repair ladder; or the base FBX's weights edited by rig_exam_blender.py, then deform_gate.py):
    elbow_shift     both elbow markers 0.05 H toward the wrist          expected: markers.limb_ratio, deform.volume_loss_max
    knee_swap       knee.L and knee.R markers swapped                   expected: contract sides, or any arp/deform gate
    finger_collapse index1-3 markers onto index0, both hands            expected: markers.finger_lengths, arp/contract
    leg_smear       half the left leg's weight on the right leg's bones expected: deform.cross_side_weight
    elbow_blend     50/50 upper/lower arm weight around each elbow      expected: deform.volume_loss_max
    knee_blend      50/50 thigh/shin weight around each knee            expected: deform.volume_loss_max
    rigid           every vertex on its heaviest bone alone             expected: deform.hinge_blended, self_intersection
    skirt_split     (a skirt base only) the skirt on Hips and its own side's thigh, split at the midline
                                                                        expected: deform.skirt_tear
    mitten_split    (a mitten base only) the mitten's Middle chain weight back on four strips
                                                                        expected: deform.mitten_tear
    none            the base FBX unchanged (the control)               expected: every gate passes
A fault that no gate fails has slipped through: the report lists it.

score: per case, each landmark's distance to the truth over H (the markers' height); the exported skeleton's joints
too (UpperArm head to shoulder, LowerArm to elbow, ...). Truth is moved into the run's frame first (prep grounds
the mesh and centres its box; a reference is already in it). Groups: joints (shoulder, elbow, wrist, hip, knee,
ankle, pelvis, neck_base, head_base), ends (hand_tip, ball, toe_tip, heel, head_top), fingers (index..little 0-3,
only where the body's fingers are apart), thumb (always the fixed shape). A rig is correct when every joint is
within --tol x H. Each case's outcome: true_pass (correct, every stage passed), false_fail (correct, a gate failed
that the case does not expect), expected_fail (failed only gates the case expects: its truth's expect_fail),
true_fail (a joint out of --tol and a gate failed), false_pass (a joint out of --tol and every gate passed),
stopped (the run stopped on a gate the case does not expect).
Fingers found: `detected` 4, `ai` its count, `fixed` 0, against the truth's apart fingers. The deform metrics are
read from the pre-repair report and the final one. The volume check sets the good rigs' largest elbow/knee/spine
loss beside the volume faults' smallest: the limit separates them when it lies between; the elbow_shift readings are
listed beside them as `mild` (a marker off the crease, which the volume gate may or may not reach).
The report (exam/1, kind report; skill-local, not a cross-skill contract) and a contact sheet (front and side of
each case, truth green, markers red, a line where they differ) are written.

Prints one JSON object. Exit codes: 0 done (score: no false pass and no slipped fault), 2 the score found a false
pass or a slipped fault (build/run/faults: a Blender step failed), 1 refused input or a failed selftest.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SCHEMA = "exam/1"
AUTORIG = HERE / "autorig.py"
MARKERS = HERE / "arp_markers.py"
DEFORM = HERE / "deform_gate.py"
HELPER = HERE / "rig_exam_blender.py"
JOINTS = ("shoulder", "elbow", "wrist", "hip", "knee", "ankle", "pelvis", "neck_base", "head_base")
ENDS = ("hand_tip", "ball", "toe_tip", "heel", "head_top")
FINGERS = ("index", "middle", "ring", "little")
# exported contract bone -> the landmark its head should sit on
RIG_JOINTS = {"UpperArm": "shoulder", "LowerArm": "elbow", "Hand": "wrist", "UpperLeg": "hip", "LowerLeg": "knee",
              "Foot": "ankle", "Toes": "ball", "Hips": "pelvis", "Neck": "neck_base", "Head": "head_base",
              "Index1": "index0", "Index2": "index1", "Index3": "index2", "Middle1": "middle0", "Middle2": "middle1",
              "Middle3": "middle2", "Ring1": "ring0", "Ring2": "ring1", "Ring3": "ring2", "Little1": "little0",
              "Little2": "little1", "Little3": "little2", "Thumb1": "thumb0", "Thumb2": "thumb1", "Thumb3": "thumb2"}
MARKER_FAULTS = ("elbow_shift", "knee_swap", "finger_collapse")
WEIGHT_FAULTS = ("leg_smear", "elbow_blend", "knee_blend", "rigid", "skirt_split", "mitten_split", "none")
EXPECT = {"elbow_shift": ["markers.limb_ratio", "deform.volume_loss_max"],
          "knee_swap": ["sides", "arp.*", "deform.*"],
          "finger_collapse": ["markers.finger_lengths", "arp.refs_placed", "axes", "parent_chain", "contract"],
          "leg_smear": ["deform.cross_side_weight"], "elbow_blend": ["deform.volume_loss_max"],
          "knee_blend": ["deform.volume_loss_max"],
          "rigid": ["deform.hinge_blended", "deform.self_intersection_p95"],
          "skirt_split": ["deform.skirt_tear"], "mitten_split": ["deform.mitten_tear"], "none": []}
VOLUME_FAULTS = ("elbow_blend", "knee_blend")
NO_FIST = "arms_up,deep_squat,torso_twist,leg_raise,elbow_120"
SHIFT_H = 0.05


class Refused(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):           # a usage error is a refusal (exit 1), never a verdict
        raise Refused(f"{self.prog}: {message}")


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(path, doc) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(doc, indent=1, default=_plain), encoding="utf-8")


def _plain(v):
    if isinstance(v, (np.floating, np.integer)):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    return str(v)


def group_of(name: str) -> str | None:
    base = name.split(".")[0]
    if base in JOINTS:
        return "joints"
    if base in ENDS:
        return "ends"
    if base[:-1] in FINGERS and base[-1:].isdigit():
        return "fingers"
    if base.startswith("thumb") and base[-1:].isdigit():
        return "thumb"
    return None


def landmark_key(name: str) -> str:
    """shoulder.L -> shoulder; index2.R -> index2: both sides pooled."""
    return name.split(".")[0]


# --- the score: pure numpy over JSON ----------------------------------------------------------------------------
def to_run_frame(truth: dict, centre_xy, ground_z: float, scale: float) -> dict:
    """Truth landmarks moved as the prep moved the mesh: box centre to x = y = 0, soles on 0, scaled."""
    c = np.array([centre_xy[0], centre_xy[1], ground_z], float)
    return {k: (np.asarray(v, float) - c) * scale for k, v in truth["landmarks"].items()}


def landmark_errors(truth_lm: dict, found: dict, H: float, fingers_apart: bool) -> dict:
    out = {}
    for name, t in truth_lm.items():
        g = group_of(name)
        if g is None or name not in found:
            continue
        if g == "fingers" and not fingers_apart:
            continue
        out[name] = round(float(np.linalg.norm(np.asarray(found[name], float) - t) / H), 5)
    return out


def rig_points(skeleton: dict | None, retarget_map: dict | None) -> dict:
    """{landmark: head} of the exported skeleton's contract bones (RIG_JOINTS)."""
    if not skeleton or not retarget_map:
        return {}
    bones = skeleton.get("bones", skeleton)
    if isinstance(bones, dict):
        bones = [dict(b, name=n) for n, b in bones.items()]
    heads = {b["name"]: b.get("head") for b in bones if b.get("head") is not None}
    out = {}
    for contract, src in retarget_map.items():
        base, _, side = contract.partition(".")
        lm = RIG_JOINTS.get(base)
        src = src[0] if isinstance(src, list) else src
        if lm and src in heads:
            out[lm + (f".{side}" if side else "")] = heads[src]
    return out


def stats(values) -> dict:
    v = np.asarray(list(values), float)
    if not len(v):
        return {"n": 0}
    return {"n": int(len(v)), "p50": round(float(np.percentile(v, 50)), 4),
            "p95": round(float(np.percentile(v, 95)), 4), "worst": round(float(v.max()), 4)}


def worst_of(errors: dict, group: str):
    items = [(e, k) for k, e in errors.items() if group_of(k) == group]
    return max(items, default=(None, None))


def fingers_found(markers: dict | None) -> int | None:
    if not markers:
        return None
    f = markers.get("fingers") or {}
    mode = f.get("mode")
    if mode == "detected":
        return 4
    if mode == "ai":
        return int(f.get("count", 4)) - (1 if f.get("count", 4) == 5 else 0)
    return 0


def failed_gates(rep: dict | None) -> list:
    if not rep:
        return []
    return [g["name"] for g in rep.get("gates", []) if g.get("pass") is not True]


def match(gate: str, patterns) -> bool:
    return any(gate == p or (p.endswith(".*") and gate.startswith(p[:-1])) for p in patterns)


def deform_summary(rep: dict | None) -> dict | None:
    if not rep or "volume_loss_max" not in rep:
        return None
    unmeasured = sorted({j for p in rep.get("poses", {}).values() for j in (p.get("joints_not_measured") or {})})
    return {"volume_loss_max": rep["volume_loss_max"], "self_intersection": rep.get("self_intersection"),
            "ball_joint_loss_max": rep.get("ball_joint_loss_max"), "joints_not_measured": unmeasured,
            "failed": failed_gates(rep)}


def outcome(correct: bool, failed: list, expect_fail: list) -> str:
    if correct and not failed:
        return "true_pass"
    if failed and all(match(g, expect_fail) for g in failed):
        return "expected_fail"
    if correct:
        return "false_fail"
    return "true_fail" if failed else "false_pass"


def score_case(case: dict, tol: float) -> dict:
    """One body or reference: case = {name, kind, truth, centre_xy, ground_z, markers, skeleton, contract,
    steps [{name, failed_gates}], deform_first, deform_final, smart?}. Pure: no files."""
    truth = case["truth"]
    markers = case.get("markers")
    out = {"name": case["name"], "kind": truth.get("kind", "truth")}
    if (not markers or "landmarks" not in markers) and case.get("markers_only"):
        markers = case["markers_only"]          # measured apart, with no window gate: scored, never a pass
    if not markers or "landmarks" not in markers:
        failed = [g for st in case.get("steps", []) for g in st.get("failed_gates", [])]
        expect = truth.get("expect_fail", [])
        out.update(error="no markers file: the run stopped before the markers", gates_failed=failed,
                   expect_fail=expect, outcome="no_run" if not failed else
                   "expected_fail" if all(match(g, expect) for g in failed) else "stopped")
        return out
    H = float(markers.get("height") or truth["height"])
    scale = 1.0 if truth.get("frame") == "prepared" else H / float(truth["height"])
    centre = (0.0, 0.0) if truth.get("frame") == "prepared" else case.get("centre_xy", (0.0, 0.0))
    ground = 0.0 if truth.get("frame") == "prepared" else case.get("ground_z", 0.0)
    t = to_run_frame(truth, centre, ground, scale)
    apart = bool((truth.get("fingers") or {}).get("separate", 0))
    err = landmark_errors(t, markers["landmarks"], H, apart)
    rig = rig_points(case.get("skeleton"), (case.get("contract") or {}).get("retarget_map"))
    rig_err = landmark_errors(t, rig, H, apart)
    joints = {k: e for k, e in err.items() if group_of(k) == "joints"}
    correct = bool(joints) and max(joints.values()) <= tol
    failed = [g for st in case.get("steps", []) for g in st.get("failed_gates", [])]
    final_deform = case.get("deform_final") or case.get("deform_first")
    if case.get("repaired") and final_deform is not None:   # a passing repair clears the first deform's failure
        failed = [g for g in failed if not g.startswith("deform.")] + failed_gates(final_deform)
    found, true_f = fingers_found(markers), int((truth.get("fingers") or {}).get("separate", 0))
    out.update({
        "height": round(H, 4), "correct": correct, "tol": tol,
        "landmarks": err, "rig": rig_err,
        "groups": {g: stats(e for k, e in err.items() if group_of(k) == g)
                   for g in ("joints", "ends", "fingers", "thumb")},
        "rig_groups": {g: stats(e for k, e in rig_err.items() if group_of(k) == g)
                       for g in ("joints", "ends", "fingers", "thumb")},
        "worst_joint": dict(zip(("error", "landmark"), worst_of(err, "joints"))),
        "fingers": {"truth": true_f, "found": found, "mode": (markers.get("fingers") or {}).get("mode"),
                    "right": found == true_f},
        "gates_failed": failed, "expect_fail": truth.get("expect_fail", []),
        "deform_first": deform_summary(case.get("deform_first")),
        "deform_final": deform_summary(case.get("deform_final")) if case.get("deform_final") else None,
        "outcome": outcome(correct, failed, truth.get("expect_fail", [])),
    })
    if markers is case.get("markers_only"):
        out["markers_only"] = True
        if out["outcome"] == "true_pass":       # the pipeline itself stopped before the markers
            out["outcome"] = "stopped"
    if markers.get("smart_agreement"):
        out["smart_second_opinion"] = markers["smart_agreement"]   # recorded only: never truth, never a limit
    if case.get("accepted_deform"):
        acc = case["accepted_deform"]
        out["accepted_rig"] = deform_summary(acc)
        out["accepted_rig_outcome"] = "true_pass" if not failed_gates(acc) else "false_fail"
    return out


def score_fault(f: dict) -> dict:
    """A gate the base rig already failed does not count as catching the fault."""
    base_failed = set(f.get("base_failed", []))
    failed = [g for st in f.get("steps", []) for g in st.get("failed_gates", []) if g not in base_failed]
    expect = EXPECT.get(f["fault"], [])
    out = {"fault": f["fault"], "base": f.get("base"), "expected": expect, "gates_failed": failed,
           "base_failed": sorted(base_failed),
           "deform": deform_summary(f.get("deform")), "error": f.get("error")}
    if f["fault"] == "none":
        out["verdict"] = "control_pass" if not failed else "control_fail"
    elif failed:
        out["verdict"] = "caught" if any(match(g, expect) for g in failed) else "caught_by_other_gate"
    else:
        out["verdict"] = "slipped" if not f.get("error") else "not_run"
    return out


def volume_check(cases: list, faults: list, limit: float) -> dict:
    """The good rigs' largest gated loss against the volume faults' smallest."""
    good = [((c.get("deform_final") or c["deform_first"])["volume_loss_max"]["value"], c["name"]) for c in cases
            if c.get("outcome") == "true_pass" and c.get("deform_first")]       # after a repair that passed
    good += [(c["accepted_rig"]["volume_loss_max"]["value"], c["name"] + " (accepted)") for c in cases
             if c.get("accepted_rig")]
    good += [(f["deform"]["volume_loss_max"]["value"], f"{f['base']}:none") for f in faults
             if f["fault"] == "none" and f.get("deform")]
    bad = [(f["deform"]["volume_loss_max"]["value"], f"{f['base']}:{f['fault']}") for f in faults
           if f["fault"] in VOLUME_FAULTS and f.get("deform")]
    mild = [(f["deform"]["volume_loss_max"]["value"], f"{f['base']}:{f['fault']}") for f in faults
            if f["fault"] == "elbow_shift" and f.get("deform")]
    out = {"limit": limit, "good_max": max(good, default=(None, None)), "bad_min": min(bad, default=(None, None)),
           "good": sorted(good, reverse=True), "bad": sorted(bad), "mild": sorted(mild)}
    g, b = out["good_max"][0], out["bad_min"][0]
    out["separates"] = None if g is None or b is None else bool(g <= limit < b)
    out["margin_good"] = None if g is None else round(limit - g, 4)
    out["margin_bad"] = None if b is None else round(b - limit, 4)
    return out


def summarise(cases: list, faults: list, tol: float, limit: float) -> dict:
    scored = [c for c in cases if "landmarks" in c]
    per_lm = {}
    for c in scored:
        for k, e in c["landmarks"].items():
            per_lm.setdefault(landmark_key(k), []).append(e)
    per_landmark = {k: stats(v) for k, v in sorted(per_lm.items())}
    by_group = {g: stats(e for c in scored for k, e in c["landmarks"].items() if group_of(k) == g)
                for g in ("joints", "ends", "fingers", "thumb")}
    rig_group = {g: stats(e for c in scored for k, e in c["rig"].items() if group_of(k) == g)
                 for g in ("joints", "ends", "fingers", "thumb")}
    weakest = sorted(((v["p95"], k) for k, v in per_landmark.items()
                      if v.get("n") and (group_of(k) or group_of(k + ".L")) in ("joints", "ends")), reverse=True)[:5]
    bodies = sorted(((c["groups"]["joints"].get("worst", 0.0), c["name"]) for c in scored), reverse=True)
    outcomes = {}
    for c in cases:
        outcomes.setdefault(c.get("outcome", "no_run"), []).append(c["name"])
    fingers = {c["name"]: c["fingers"] for c in scored}
    slipped = [f["fault"] + "@" + str(f["base"]) for f in faults if f["verdict"] == "slipped"]
    return {"tol": tol, "joints": by_group["joints"], "groups": by_group, "rig_groups": rig_group,
            "per_landmark": per_landmark, "weakest_landmarks": [k for _, k in weakest],
            "weakest_bodies": [n for _, n in bodies[:3]], "outcomes": outcomes,
            "fingers_right": sum(1 for f in fingers.values() if f["right"]), "fingers_cases": len(fingers),
            "false_pass": outcomes.get("false_pass", []), "false_fail": outcomes.get("false_fail", []),
            "faults_caught": [f["fault"] + "@" + str(f["base"]) for f in faults if f["verdict"].startswith("caught")],
            "faults_slipped": slipped,
            "control_fail": [f["base"] for f in faults if f["verdict"] == "control_fail"],
            "volume": volume_check(cases, faults, limit)}


# --- the contact sheet (Pillow) -------------------------------------------------------------------------------
def splat(V, axes, size, lo, hi):
    """A silhouette of the vertices projected on two axes, as a boolean image."""
    img = np.zeros((size[1], size[0]), bool)
    span = max(hi[0] - lo[0], hi[1] - lo[1]) * 1.06
    def px(p):
        return (((p[..., 0] - (lo[0] + hi[0]) / 2) / span + 0.5) * size[0],
                (0.5 - (p[..., 1] - (lo[1] + hi[1]) / 2) / span) * size[1])
    x, y = px(V[:, axes])
    x, y = np.clip(x.astype(int), 0, size[0] - 1), np.clip(y.astype(int), 0, size[1] - 1)
    img[y, x] = True
    img[1:, :] |= img[:-1, :]                    # one pixel of growth closes the gaps between samples
    img[:, 1:] |= img[:, :-1]
    return img, px


def contact_sheet(cells: list, path: str, cell=(220, 300)) -> str:
    """cells [{title, lines, V (n,3) or None, truth {k: xyz}, found {k: xyz}}] -> one PNG, front + side per cell."""
    from PIL import Image, ImageDraw
    cols = 4
    rows = (len(cells) + cols - 1) // cols
    W, Hh = cell[0] * 2 * cols, (cell[1] + 44) * max(rows, 1)
    sheet = Image.new("RGB", (W, Hh), (250, 250, 248))
    draw = ImageDraw.Draw(sheet)
    for i, c in enumerate(cells):
        ox, oy = (i % cols) * cell[0] * 2, (i // cols) * (cell[1] + 44)
        pts = [np.asarray(p, float) for p in list(c["truth"].values()) + list(c["found"].values())]
        V = c.get("V")
        allp = np.vstack(([V] if V is not None and len(V) else []) + ([np.array(pts)] if pts else []))
        for j, axes in enumerate(((0, 2), (1, 2))):
            lo, hi = allp[:, axes].min(0), allp[:, axes].max(0)
            if V is not None and len(V):
                img, px = splat(V, list(axes), cell, lo, hi)
                sil = Image.fromarray(np.where(img, 180, 250).astype(np.uint8)).convert("RGB")
                sheet.paste(sil, (ox + j * cell[0], oy))
            else:
                _, px = splat(np.zeros((1, 3)), list(axes), cell, lo, hi)
            for k, t in c["truth"].items():
                tx, ty = px(np.asarray(t, float)[list(axes)])
                X, Y = ox + j * cell[0] + tx, oy + ty
                if k in c["found"]:
                    fx, fy = px(np.asarray(c["found"][k], float)[list(axes)])
                    draw.line((X, Y, ox + j * cell[0] + fx, oy + fy), fill=(220, 40, 40), width=1)
                    draw.line((ox + j * cell[0] + fx - 2, oy + fy - 2, ox + j * cell[0] + fx + 2, oy + fy + 2),
                              fill=(220, 40, 40))
                    draw.line((ox + j * cell[0] + fx - 2, oy + fy + 2, ox + j * cell[0] + fx + 2, oy + fy - 2),
                              fill=(220, 40, 40))
                draw.ellipse((X - 2, Y - 2, X + 2, Y + 2), outline=(20, 150, 60))
        draw.text((ox + 4, oy + cell[1] + 2), c["title"], fill=(20, 20, 20))
        for n, line in enumerate(c.get("lines", [])[:2]):
            draw.text((ox + 4, oy + cell[1] + 15 + 13 * n), line, fill=(70, 70, 70))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    return path


# --- files: reading an exam folder -------------------------------------------------------------------------------
def glb_frame(glb: Path):
    """(vertices grounded, box centre x/y, ground z) of a .glb as mesh_check reads it; None when it cannot."""
    try:
        sys.path.insert(0, str(HERE))
        import mesh_check as M
        V, F = M.load_mesh(glb)
    except Exception:            # noqa: BLE001 — a missing or unreadable mesh only costs the sheet its silhouette
        return None, (0.0, 0.0), 0.0
    c = (V.min(0) + V.max(0)) / 2
    return np.vstack([V, V[F].mean(axis=1)]), (float(c[0]), float(c[1])), 0.0   # vertices and face centres


def run_files(run_dir: Path, name: str) -> dict:
    rig = run_dir / "rig"
    summary = read_json(run_dir / "autorig.all.json") or {}
    steps = [{"name": s.get("name"), "failed_gates": s.get("failed_gates") or []} for s in summary.get("steps", [])]
    repair = summary.get("repair") or {}
    attempts = repair.get("attempts") or []
    final = None
    repaired = False
    if attempts:
        final = read_json(attempts[-1].get("deform") or "")
        repaired = repair.get("result") == "passed"
    steps = [s for s in steps if not str(s["name"]).startswith(("repair", "deform_a"))]
    return {"markers": read_json(rig / f"{name}.markers.json"), "markers_only": read_json(rig / f"{name}.markers_only.json"), "contract": read_json(rig / f"{name}.contract.json"),
            "skeleton": read_json(run_dir / "export" / f"{name}.skeleton.json"), "steps": steps,
            "deform_first": read_json(rig / f"{name}.deform.json"), "deform_final": final, "repaired": repaired,
            "exit_code": summary.get("exit_code")}


def collect(exam: Path) -> tuple[list, list, list]:
    """(cases, faults, sheet cells) from an exam folder."""
    cases, cells = [], []
    for kind, folder in (("truth", exam / "cast"), ("reference", exam / "refs")):
        files = sorted(folder.glob("*.truth.json")) if kind == "truth" else sorted(folder.glob("*/*.truth.json"))
        for tf in files:
            truth = read_json(tf)
            if not truth:
                continue
            name = truth["name"]
            glb = tf.with_name(f"{name}.glb")
            V, centre, ground = glb_frame(glb)
            run = run_files(exam / ("runs" if kind == "truth" else "refruns") / name, name)
            case = {"name": name, "truth": truth, "centre_xy": centre, "ground_z": ground, **run}
            if kind == "reference":
                case["accepted_deform"] = read_json(tf.parent / "accepted.deform.json")
            cases.append(case)
            cells.append((case, V))
    faults = []
    for fj in sorted((exam / "faults").glob("*/*/fault.json")):
        doc = read_json(fj)
        if doc:
            faults.append(doc)
    return cases, faults, cells


def sheet_mesh(V, case) -> np.ndarray:
    """The mesh moved into the run's frame, as the prep moves it (a reference: also scaled to its height)."""
    V = V - [case["centre_xy"][0], case["centre_xy"][1], 0.0]
    if case["truth"].get("frame") == "prepared":
        V = V * (float(case["truth"]["height"]) / max(float(np.ptp(V[:, 2])), 1e-9))
    return V


def cmd_score(a) -> tuple[int, dict]:
    exam = Path(a.exam)
    if not exam.is_dir():
        raise Refused(f"no exam folder {exam}")
    cases, faults, cells = collect(exam)
    if not cases:
        raise Refused(f"{exam}: no truth files (rig_exam.py build first)")
    scored = [score_case(c, a.tol) for c in cases]
    fscored = [score_fault(f) for f in faults]
    summary = summarise(scored, fscored, a.tol, a.volume_max)
    sheet_cells = []
    for (case, V), s in zip(cells, scored):
        if "landmarks" not in s:
            sheet_cells.append({"title": f"{s['name']}: no run", "truth": {}, "found": {}, "V": V})
            continue
        truth = to_run_frame(case["truth"], *((0.0, 0.0), 0.0) if case["truth"].get("frame") == "prepared"
                             else (case["centre_xy"], case["ground_z"]), 1.0)
        found = (case.get("markers") or case.get("markers_only") or {}).get("landmarks", {})
        keys = [k for k in s["landmarks"] if group_of(k) in ("joints", "ends")]
        wj = s["worst_joint"]
        sheet_cells.append({"title": f"{s['name']}  {s['outcome']}",
                            "lines": [f"joints p50 {s['groups']['joints'].get('p50')} worst {wj['error']} "
                                      f"({wj['landmark']})",
                                      f"fingers {s['fingers']['found']}/{s['fingers']['truth']}  "
                                      + (f"failed {','.join(s['gates_failed'])[:40]}" if s['gates_failed']
                                       else "no gate failed")],
                            "truth": {k: truth[k] for k in keys},
                            "found": {k: found[k] for k in keys if k in found},
                            "V": None if V is None else sheet_mesh(V, case)})
    report = {"schema": SCHEMA, "kind": "report", "tool": "rig_exam", "exam": str(exam), "summary": summary,
              "cases": scored, "faults": fscored}
    out = a.out or str(exam / "exam.json")
    sheet = a.sheet or str(exam / "sheet.png")
    try:
        report["sheet"] = contact_sheet(sheet_cells, sheet)
    except ImportError:
        report["sheet"] = None
    write_json(out, report)
    report["report"] = out
    bad = summary["false_pass"] or summary["faults_slipped"]
    return (2 if bad else 0), report


# --- Blender steps -------------------------------------------------------------------------------------------------
def blender_path(a) -> str:
    if a.blender:
        return a.blender
    sys.path.insert(0, str(HERE))
    import autorig
    return autorig.default_blender()


def sh(cmd: list, log: Path, timeout=3600) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    with open(log, "w", encoding="utf-8") as fh:
        try:
            return subprocess.run([str(c) for c in cmd], stdout=fh, stderr=subprocess.STDOUT, env=env,
                                  timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            fh.write("\nrig_exam: timed out\n")
            return 1


def blender(a, script, *args, blend=None, factory=True) -> list:
    cmd = [blender_path(a), "-b"] + ([str(blend)] if blend else []) + (["--factory-startup"] if factory else [])
    if a.threads:
        cmd += ["-t", str(a.threads)]
    return cmd + ["--python-exit-code", "1", "-P", str(script), "--", *map(str, args)]


def autorig(a, *args) -> list:
    cmd = [sys.executable, str(AUTORIG), *map(str, args), "--blender", blender_path(a)]
    return cmd + (["--threads", str(a.threads)] if a.threads else [])


def names(a, folder: Path, suffix=".truth.json") -> list:
    found = sorted(p.name[: -len(suffix)] for p in folder.glob(f"*{suffix}"))
    if a.only:
        want = a.only.split(",")
        missing = [w for w in want if w not in found]
        if missing:
            raise Refused(f"not in {folder}: {missing}")
        return want
    return found


def cmd_build(a) -> tuple[int, dict]:
    exam = Path(a.exam)
    cast = exam / "cast"
    args = ["cast", cast, "--seed", a.seed, "--faces", a.faces] + (["--only", a.only] if a.only else [])
    code = sh(blender(a, HELPER, *args), exam / "logs" / "build.log")
    made = sorted(p.name[:-11] for p in cast.glob("*.truth.json"))
    return (0 if code == 0 else 2), {"tool": "rig_exam", "op": "build", "exit_code": code, "cast": made,
                                     "log": str(exam / "logs" / "build.log")}


def cmd_run(a) -> tuple[int, dict]:
    exam = Path(a.exam)
    done = {}
    cases = [(n, exam / "cast", exam / "runs") for n in names(a, exam / "cast")] if not a.refs else []
    if a.refs or not a.only:
        cases += [(p.parent.name, p.parent, exam / "refruns") for p in sorted((exam / "refs").glob("*/*.truth.json"))
                  if not a.refs or not a.only or p.parent.name in a.only.split(",")]
    for name, src, runs in cases:
        truth = read_json(src / f"{name}.truth.json")
        out = runs / name
        if out.exists():
            shutil.rmtree(out)
        cmd = autorig(a, "all", out, src / f"{name}.glb", "--name", name, "--height", truth["height"])
        if (truth.get("spec") or {}).get("skirt"):      # a long skirt: the case is rigged on the skirt route
            cmd += ["--body", "skirt"]
        if (truth.get("spec") or {}).get("body") == "chibi":   # a big head on short limbs: the chibi route
            cmd += ["--body", "chibi"]
        if not a.smart:
            cmd.append("--no-smart")
        code = sh(cmd, exam / "logs" / f"run_{name}.log")
        done[name] = code
        if not (out / "rig" / f"{name}.markers.json").exists() and (out / f"{name}.blend").exists():
            # stopped before the markers (a body off its route's bands): measure them anyway, to score them
            sh(blender(a, MARKERS, "--mesh", name, "--no-window-gate", "--out", out / "rig" / f"{name}.markers_only.json",
                       blend=out / f"{name}.blend"), exam / "logs" / f"markers_only_{name}.log")
        rig = truth.get("rig") or {}
        if truth.get("kind") == "reference" and rig.get("fbx") and rig.get("contract"):
            ref = Path(src)
            poses = [] if not rig.get("no_fist") else ["--poses", NO_FIST]
            done[name + ":accepted"] = sh(blender(a, DEFORM, "--fbx", ref / rig["fbx"], "--map", ref / rig["contract"],
                                                  *poses, "--out", ref / "accepted.deform.json"),
                                          exam / "logs" / f"accepted_{name}.log")
    bad = [n for n, c in done.items() if c == 1]
    return (2 if bad else 0), {"tool": "rig_exam", "op": "run", "exit_codes": done, "errors": bad}


def fault_poses(markers: dict | None, reference: bool = False) -> list:
    """deform_gate's poses and body for a fault, as autorig's deform stage gates that base: a mitten swaps fist
    for the mitten pose (a reference keeps the poses it was accepted with), a chibi takes its own poses."""
    fixed = ((markers or {}).get("fingers") or {}).get("mode") == "fixed"
    out = ["--poses", NO_FIST + ("" if reference else ",mitten")] if fixed else []
    return out + (["--body", "chibi"] if (markers or {}).get("body") == "chibi" else [])


def adjust_for(fault: str, markers: dict) -> dict:
    lm = {k: np.asarray(v, float) for k, v in markers["landmarks"].items()}
    H = float(markers["height"])
    if fault == "elbow_shift":
        out = {}
        for s in ("L", "R"):
            d = lm[f"wrist.{s}"] - lm[f"elbow.{s}"]
            out[f"elbow.{s}"] = lm[f"elbow.{s}"] + d / np.linalg.norm(d) * SHIFT_H * H
        return out
    if fault == "knee_swap":
        return {"knee.L": lm["knee.R"], "knee.R": lm["knee.L"]}
    if fault == "finger_collapse":
        out = {}
        for s in ("L", "R"):
            base, nxt = lm[f"index0.{s}"], lm[f"index1.{s}"]
            d = (nxt - base) / max(np.linalg.norm(nxt - base), 1e-9)
            for i in (1, 2, 3):
                out[f"index{i}.{s}"] = base + d * 0.0005 * i
        return out
    raise Refused(f"unknown marker fault {fault}")


def base_dir(exam: Path, base: str) -> tuple[Path, str]:
    for d in (exam / "runs" / base, exam / "refruns" / base):
        if (d / "rig" / f"{base}.markers.json").exists():
            return d, base
    raise Refused(f"no run for {base!r} in {exam}/runs or refruns (rig_exam.py run first)")


def cmd_faults(a) -> tuple[int, dict]:
    exam = Path(a.exam)
    src, name = base_dir(exam, a.base)
    markers = read_json(src / "rig" / f"{name}.markers.json")
    contract = src / "rig" / f"{name}.contract.json"
    fbx = src / "export" / f"{name}.fbx"
    if a.fbx:                                   # a reference: its accepted rig is the base for weight faults
        fbx, contract = Path(a.fbx), Path(a.contract or contract)
    skirt = (markers or {}).get("body") == "skirt"
    mitten = ((markers or {}).get("fingers") or {}).get("mode") == "fixed" and not a.fbx   # mitten_bind ran
    chosen = a.only.split(",") if a.only else [f for f in MARKER_FAULTS + WEIGHT_FAULTS
                                               if (skirt or f != "skirt_split") and (mitten or f != "mitten_split")]
    sk_arg = ["--skirt", src / "rig" / f"{name}.markers.json"] if skirt else []
    unknown = [f for f in chosen if f not in MARKER_FAULTS + WEIGHT_FAULTS]
    if unknown:
        raise Refused(f"unknown faults {unknown}; known {list(MARKER_FAULTS + WEIGHT_FAULTS)}")
    base_run = run_files(src, name)
    base_marker_failed = sorted({g for st in base_run["steps"] for g in st["failed_gates"]})
    base_deform = read_json(Path(a.fbx).parent / "accepted.deform.json") if a.fbx else base_run["deform_first"]
    results, errors = {}, []
    for fault in chosen:
        out = exam / "faults" / a.base / fault
        if out.exists():
            shutil.rmtree(out)
        (out / "rig").mkdir(parents=True)
        doc = {"schema": SCHEMA, "kind": "fault", "fault": fault, "base": a.base, "steps": [],
               "base_failed": base_marker_failed if fault in MARKER_FAULTS else failed_gates(base_deform)}
        if fault in MARKER_FAULTS:
            if fault == "finger_collapse" and "index1.L" not in markers["landmarks"]:
                doc["error"] = "the base markers have no finger landmarks"
            else:
                for f in (f"{name}.blend", f"{name}.glb"):
                    shutil.copy2(src / f, out / f)
                shutil.copy2(src / "rig" / f"{name}.mesh.json", out / "rig" / f"{name}.mesh.json")
                adj = out / "adjust.json"
                write_json(adj, {k: [round(float(x), 5) for x in v] for k, v in adjust_for(fault, markers).items()})
                mk = out / "rig" / f"{name}.markers.json"
                body = ["--body", markers["body"]] if markers.get("body") in ("skirt", "chibi") else []
                code = sh(blender(a, MARKERS, "--mesh", name, "--adjust", adj, "--out", mk, *body,
                                  blend=out / f"{name}.blend"), out / "markers.log")
                doc["steps"].append({"name": "markers", "exit_code": code, "failed_gates": failed_gates(read_json(mk))})
                if code == 1:
                    doc["error"] = "arp_markers.py --adjust exited 1"
                for stage in ("arp", "contract", "deform"):
                    if code == 1:
                        break
                    extra = ["--no-repair", "--no-render"] if stage == "deform" else []
                    code = sh(autorig(a, stage, out, "--name", name, *extra), out / f"{stage}.log")
                    if code == 1:
                        doc["error"] = f"autorig.py {stage} exited 1"
                    rep = read_json(out / f"autorig.{stage}.json") or {}
                    for st in rep.get("steps", []):
                        doc["steps"].append({"name": st.get("name"), "exit_code": st.get("exit_code"),
                                             "failed_gates": st.get("failed_gates") or []})
                    if stage in ("arp",) and code != 0:
                        break
                doc["deform"] = read_json(out / "rig" / f"{name}.deform.json")
        else:
            blend = out / f"{name}_{fault}.blend"
            wrep = out / "weights.json"
            code = sh(blender(a, HELPER, "weights", fbx, contract, fault, blend, "--report", wrep, *sk_arg),
                      out / "weights.log")
            w = read_json(wrep) or {}
            if code != 0:
                doc["error"] = w.get("error") or f"weights exited {code}"
            else:
                drep = out / f"{name}.deform.json"
                code = sh(blender(a, DEFORM, "--armature", w["armature"], "--mesh", w["mesh"], "--map", contract,
                                  *fault_poses(markers, bool(a.fbx)), *sk_arg, "--out", drep, blend=blend),
                          out / "deform.log")
                d = read_json(drep)
                doc["weights"] = {k: w.get(k) for k in ("moved", "joints", "changed_vertices")}
                doc["steps"].append({"name": "deform", "exit_code": code, "failed_gates": failed_gates(d)})
                doc["deform"] = d
                blend.unlink(missing_ok=True)       # the faulted file is large and rebuilt in seconds
        write_json(out / "fault.json", doc)
        sf = score_fault(doc)
        results[fault] = sf["verdict"]
        if sf["error"]:
            errors.append(fault)
    return (2 if errors else 0), {"tool": "rig_exam", "op": "faults", "base": a.base, "verdicts": results,
                                  "errors": errors}


def cmd_reference(a) -> tuple[int, dict]:
    exam = Path(a.exam)
    markers = read_json(a.markers)
    if not markers or "landmarks" not in markers:
        raise Refused(f"{a.markers}: not a markers file")
    if not Path(a.glb).is_file():
        raise Refused(f"no file {a.glb}")
    out = exam / "refs" / a.name
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(a.glb, out / f"{a.name}.glb")
    shutil.copy2(a.markers, out / "accepted.markers.json")
    rig = {}
    for key, path in (("fbx", a.fbx), ("contract", a.contract)):
        if path:
            dest = out / f"accepted{Path(path).suffix if key == 'fbx' else '.contract.json'}"
            shutil.copy2(path, dest)
            rig[key] = dest.name
    if rig:
        rig["no_fist"] = (markers.get("fingers") or {}).get("mode") == "fixed"
    sep = 4 if (markers.get("fingers") or {}).get("mode") in ("detected", "ai") else 0
    doc = {"schema": SCHEMA, "kind": "reference", "name": a.name, "height": markers["height"], "frame": "prepared",
           "source": "markers a person accepted", "landmarks": markers["landmarks"],
           "fingers": {"separate": sep, "thumb": sep > 0}, "expect_fail": [], "rig": rig}
    write_json(out / f"{a.name}.truth.json", doc)
    return 0, {"tool": "rig_exam", "op": "reference", "case": str(out), "landmarks": len(markers["landmarks"])}


# --- selftest -----------------------------------------------------------------------------------------------------
def planted(name="planted", shift=None, H=1.75, fingers=4, failed=(), expect_fail=()):
    """A truth file and a markers file whose differences are known."""
    rng = np.random.default_rng(len(name))
    lm = {}
    for b in JOINTS + ENDS:
        if b in ("pelvis", "neck_base", "head_base", "head_top"):
            lm[b] = rng.uniform(0.2, 1.7, 3)
        else:
            p = rng.uniform(0.1, 1.6, 3)
            lm[b + ".L"], lm[b + ".R"] = p, p * [-1, 1, 1]
    for f in FINGERS + ("thumb",):
        for i in range(4):
            p = rng.uniform(0.5, 1.0, 3)
            lm[f"{f}{i}.L"], lm[f"{f}{i}.R"] = p, p * [-1, 1, 1]
    centre = np.array([0.03, -0.02, 0.0])
    truth = {"schema": SCHEMA, "kind": "truth", "name": name, "height": H, "frame": "glb",
             "landmarks": {k: (v + centre).tolist() for k, v in lm.items()},
             "fingers": {"separate": fingers}, "expect_fail": list(expect_fail)}
    found = {k: v.copy() for k, v in lm.items()}
    for k, d in (shift or {}).items():
        found[k] = found[k] + np.array(d) * H
    markers = {"height": H, "landmarks": {k: v.tolist() for k, v in found.items()},
               "fingers": {"mode": "detected" if fingers else "fixed"}}
    contract = {"retarget_map": {"LowerArm.L": "forearm.l", "UpperLeg.R": "thigh.r"}}
    skeleton = {"bones": [{"name": "forearm.l", "head": (lm["elbow.L"] + [0, 0, 0.02 * H]).tolist()},
                          {"name": "thigh.r", "head": lm["hip.R"].tolist()}]}
    return {"name": name, "truth": truth, "centre_xy": (0.03, -0.02), "ground_z": 0.0, "markers": markers,
            "contract": contract, "skeleton": skeleton,
            "steps": [{"name": "markers", "failed_gates": list(failed)}],
            "deform_first": {"volume_loss_max": {"value": 0.08, "joint": "LowerArm.L"}, "gates": [], "poses": {}}}


def selftest() -> int:
    checks, failed = 0, []

    def ok(name, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failed.append(name)
    # a perfect markers file: every error 0, correct, true pass
    s = score_case(planted(), 0.04)
    ok("perfect: errors 0 after the frame move", max(s["landmarks"].values()) < 1e-6)
    ok("perfect: true_pass, fingers right", s["outcome"] == "true_pass" and s["fingers"]["right"])
    ok("rig heads: forearm 0.02 H off the elbow", abs(s["rig"]["elbow.L"] - 0.02) < 1e-4 and s["rig"]["hip.R"] < 1e-6)
    # known shifts: elbow 0.03 H, knee 0.06 H -> wrong rig; p50/p95/worst over the joints
    s = score_case(planted(shift={"elbow.L": (0.03, 0, 0), "knee.R": (0, 0, 0.06)}), 0.04)
    ok("shifted: elbow 0.03, knee 0.06", abs(s["landmarks"]["elbow.L"] - 0.03) < 1e-4 and
       abs(s["landmarks"]["knee.R"] - 0.06) < 1e-4)
    ok("shifted: worst joint is the knee", s["worst_joint"]["landmark"] == "knee.R" and
       abs(s["groups"]["joints"]["worst"] - 0.06) < 1e-4)
    ok("shifted, gates pass: false_pass", s["outcome"] == "false_pass" and not s["correct"])
    s2 = score_case(planted(shift={"knee.R": (0, 0, 0.06)}, failed=["markers.windows"]), 0.04)
    ok("shifted, a gate failed: true_fail", s2["outcome"] == "true_fail")
    s3 = score_case(planted(failed=["deform.volume_loss_max"]), 0.04)
    ok("correct, a gate failed: false_fail", s3["outcome"] == "false_fail")
    s4 = score_case(planted(failed=["markers.windows"], expect_fail=["markers.windows"],
                            shift={"hip.L": (0, 0, 0.1)}), 0.04)
    ok("an expected refusal", s4["outcome"] == "expected_fail")
    s5 = score_case(dict(planted(fingers=0), markers=dict(planted(fingers=0)["markers"],
                                                          fingers={"mode": "detected"})), 0.04)
    ok("a mitten read as four fingers: wrong, finger landmarks not scored",
       not s5["fingers"]["right"] and not any(group_of(k) == "fingers" for k in s5["landmarks"]))
    ok("no markers: no_run", score_case({"name": "x", "truth": {"height": 1.7}}, 0.04)["outcome"] == "no_run")
    # a reference case is already in the run frame
    ref = planted()
    ref["truth"] = dict(ref["truth"], frame="prepared",
                        landmarks={k: v for k, v in ref["markers"]["landmarks"].items()})
    ref["accepted_deform"] = {"volume_loss_max": {"value": 0.09}, "gates": [{"name": "deform.poses", "pass": True}],
                              "poses": {}}
    r = score_case(ref, 0.04)
    ok("reference: no frame move, accepted rig passes", max(r["landmarks"].values()) < 1e-6 and
       r["accepted_rig_outcome"] == "true_pass")
    # faults
    v = [score_fault({"fault": "elbow_blend", "base": "b", "steps": [{"failed_gates": ["deform.volume_loss_max"]}],
                      "deform": {"volume_loss_max": {"value": 0.5}, "gates": [], "poses": {}}}),
         score_fault({"fault": "knee_blend", "base": "b", "steps": [{"failed_gates": []}],
                      "deform": {"volume_loss_max": {"value": 0.30}, "gates": [], "poses": {}}}),
         score_fault({"fault": "rigid", "base": "b", "steps": [{"failed_gates": ["deform.volume_loss_max"]}]}),
         score_fault({"fault": "none", "base": "b", "steps": [{"failed_gates": []}],
                      "deform": {"volume_loss_max": {"value": 0.1}, "gates": [], "poses": {}}})]
    ok("fault verdicts", [x["verdict"] for x in v] == ["caught", "slipped", "caught_by_other_gate", "control_pass"])
    ok("a gate the base already failed catches nothing", score_fault(
        {"fault": "finger_collapse", "base": "b", "base_failed": ["markers.windows"],
         "steps": [{"failed_gates": ["markers.windows"]}]})["verdict"] == "slipped")
    cases = [score_case(planted(), 0.04), r]
    summ = summarise(cases, v, 0.04, 0.35)
    ok("summary: the slipped fault is listed", summ["faults_slipped"] == ["knee_blend@b"])
    vol = summ["volume"]
    ok("volume: good max 0.1, bad min 0.30, limit does not separate",
       vol["good_max"][0] == 0.1 and vol["bad_min"][0] == 0.30 and vol["separates"] is False)
    v[1]["deform"]["volume_loss_max"]["value"] = 0.42
    ok("volume: separates when every bad rig reads over the limit",
       volume_check(cases, v, 0.35)["separates"] is True)
    ok("matching: deform.* covers deform gates", match("deform.poses", ["deform.*"]) and not match("sides", ["deform.*"]))
    # the adjust files for marker faults
    mk = {"height": 1.75, "landmarks": {"elbow.L": [0.4, 0, 1.2], "wrist.L": [0.6, 0, 1.0], "elbow.R": [-0.4, 0, 1.2],
                                        "wrist.R": [-0.6, 0, 1.0], "knee.L": [0.1, 0, 0.5], "knee.R": [-0.1, 0, 0.5],
                                        "index0.L": [0.6, 0, 0.9], "index1.L": [0.62, 0, 0.88],
                                        "index0.R": [-0.6, 0, 0.9], "index1.R": [-0.62, 0, 0.88]}}
    adj = adjust_for("elbow_shift", mk)
    ok("elbow_shift: 0.05 H toward the wrist", abs(np.linalg.norm(adj["elbow.L"] - mk["landmarks"]["elbow.L"]) -
                                                   0.05 * 1.75) < 1e-6 and adj["elbow.L"][2] < 1.2)
    ok("knee_swap swaps", list(adjust_for("knee_swap", mk)["knee.L"]) == mk["landmarks"]["knee.R"])
    fc = adjust_for("finger_collapse", mk)
    ok("finger_collapse: index1-3 within 2 mm of index0", all(
        np.linalg.norm(fc[f"index{i}.L"] - np.array(mk["landmarks"]["index0.L"])) < 0.002 for i in (1, 2, 3)))
    # the files and the sheet on a planted exam folder
    with tempfile.TemporaryDirectory() as d:
        exam = Path(d)
        p = planted("body", shift={"elbow.L": (0.03, 0, 0)})
        write_json(exam / "cast" / "body.truth.json", p["truth"])
        import mesh_check as M                    # a box whose centre is the planted frame's (0.03, -0.02)
        box = np.array([[x, y, z] for x in (-0.47, 0.53) for y in (-0.32, 0.28) for z in (0.0, 1.75)])
        M.write_glb(exam / "cast" / "body.glb", box, np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5],
                                                               [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6]]))
        run = exam / "runs" / "body"
        write_json(run / "rig" / "body.markers.json", p["markers"])
        write_json(run / "rig" / "body.deform.json", p["deform_first"])
        write_json(run / "autorig.all.json", {"steps": [{"name": "markers", "failed_gates": []}], "exit_code": 0})
        write_json(exam / "faults" / "body" / "elbow_blend" / "fault.json",
                   {"fault": "elbow_blend", "base": "body", "steps": [{"failed_gates": []}],
                    "deform": {"volume_loss_max": {"value": 0.2}, "gates": [], "poses": {}}})
        args = parser().parse_args(["score", d])
        code, rep = cmd_score(args)
        ok("score: exit 2 on a slipped fault", code == 2 and rep["summary"]["faults_slipped"] == ["elbow_blend@body"])
        saved = read_json(rep["report"])
        ok("score: exam/1 report written", saved["schema"] == SCHEMA and saved["kind"] == "report" and
           abs(saved["cases"][0]["landmarks"]["elbow.L"] - 0.03) < 1e-3)
        try:
            import PIL  # noqa: F401
            ok("score: contact sheet written", rep["sheet"] and os.path.getsize(rep["sheet"]) > 1000)
        except ImportError:
            pass
        try:
            cmd_score(parser().parse_args(["score", os.path.join(d, "nope")]))
            ok("missing exam folder refused", False)
        except Refused:
            ok("missing exam folder refused", True)
    for argv in (["--no-such-flag"], ["score"], ["faults", "x", "--only", "bogus"]):
        try:
            a = parser().parse_args(argv)
            if a.cmd == "faults":
                cmd_faults(a)
            ok(f"usage error refused: {argv}", False)
        except Refused:
            ok(f"usage error refused: {argv}", True)
    print(json.dumps({"tool": "rig_exam", "selftest": True, "checks": checks, "failed": failed, "ok": not failed}))
    return 0 if not failed else 1


def parser() -> Parser:
    p = Parser(prog="rig_exam.py", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", parser_class=Parser)
    common = Parser(add_help=False)
    common.add_argument("exam", help="the exam folder")
    common.add_argument("--blender")
    common.add_argument("--threads", type=int, default=4)
    common.add_argument("--only")
    b = sub.add_parser("build", parents=[common])
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--faces", type=int, default=40000)
    r = sub.add_parser("run", parents=[common])
    r.add_argument("--smart", action="store_true", help="run Auto-Rig Pro's AI too (a second opinion, never truth)")
    r.add_argument("--refs", action="store_true", help="only the reference cases")
    f = sub.add_parser("faults", parents=[common])
    f.add_argument("--base", default="standard")
    f.add_argument("--fbx", help="the base rig's FBX for weight faults (default the base run's export)")
    f.add_argument("--contract", help="the contract report that goes with --fbx")
    ref = sub.add_parser("reference")
    ref.add_argument("exam")
    ref.add_argument("name")
    ref.add_argument("--glb", required=True)
    ref.add_argument("--markers", required=True)
    ref.add_argument("--fbx")
    ref.add_argument("--contract")
    s = sub.add_parser("score")
    s.add_argument("exam")
    s.add_argument("--tol", type=float, default=0.04, help="x H: a joint farther than this makes the rig wrong")
    s.add_argument("--volume-max", type=float, default=0.35, help="deform_gate's volume limit, for the volume check")
    s.add_argument("--out")
    s.add_argument("--sheet")
    p.add_argument("--selftest", action="store_true")
    return p


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (["--selftest"], ["selftest"]):
        return selftest()
    try:
        a = parser().parse_args(argv)
        if not a.cmd:
            raise Refused("rig_exam.py: name a command (build, run, faults, reference, score) or --selftest")
        code, rep = {"build": cmd_build, "run": cmd_run, "faults": cmd_faults, "reference": cmd_reference,
                     "score": cmd_score}[a.cmd](a)
    except Refused as exc:
        print(json.dumps({"tool": "rig_exam", "ok": False, "error": str(exc)}))
        return 1
    if a.cmd == "score":
        rep = {k: rep[k] for k in ("schema", "kind", "tool", "summary", "report", "sheet")}
    print(json.dumps(rep, indent=1, default=_plain))
    return code


if __name__ == "__main__":
    sys.exit(main())
