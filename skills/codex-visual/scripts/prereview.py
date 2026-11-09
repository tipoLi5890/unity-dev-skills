#!/usr/bin/env python3
"""prereview.py — a pre-review of one review sheet against a fixed defect checklist, recorded as review/1.

Before a person approves a sheet (the stages of game-character-pipeline whose
gate says **person**), the agent running these skills reads the sheet itself
and answers a fixed list of yes/no defect questions. Each question is answered
twice, on two cell orders of the same views (sheet a: the spec's order, sheet
b: shuffled), because a judge that looks at pictures favours some positions.
`check` then names the items a person must look at: a defect or an unsure
answer in either pass, or two passes that disagree. Nothing here approves
anything: a person still runs `registry.py status ID approved`.

usage:
    prereview.py list [--stage S3] [--json]
    prereview.py new --stage S3 --spec sheet.json --subject FILE --out review/NAME
                     [--require FILE ...] [--reviewer claude] [--model NAME] [--force]
    prereview.py new --spec OUT/prereview.spec.json --out review/NAME   # stage, subject, require from the spec
    prereview.py answer review/NAME.review.json --pass a --id s3.hole --answer defect
                     --view left --note "a gap under the left arm"
    prereview.py answer review/NAME.review.json --pass b --from answers_b.json
    prereview.py check review/NAME.review.json
    prereview.py --selftest

list    prints each stage's checklist: id, question, the views to look at first.
new     composes NAME.a.png (the spec's order) and NAME.b.png (contact_sheet.py
        --order with a seed taken from the subject's sha256) and writes
        NAME.review.json, a review/1 draft: the checklist copied in, no answers.
        The spec is contact_sheet.py's, with `items` (one sheet). --require is
        contact_sheet's: every file must pass, or nothing is written.
        A spec may also carry `stage`, `subject` and `require` (paths relative to
        the spec's folder), as the sidecar prereview.spec.json the producers write
        (autorig.py S6, concept_match.py S3b, game_mesh.py S5): --stage, --subject
        and --require, when given, win (a given --require replaces the spec's list).
answer  records answers into the draft, one item (--id --answer [--view] [--note])
        or a whole pass (--from FILE, or - for stdin: {id: {answer, view, note}}).
        An answer is defect, clear or unsure; a view is a cell label or omitted.
        Editing NAME.review.json by hand is accepted too: check validates it.
        Any answer puts the review back to draft until check runs again.
check   validates the review, needs every item answered in both passes, refuses a
        sheet or subject whose bytes changed since the draft, writes `flagged`
        and `verdict` (clear | flagged) back and prints the flagged items with
        their views and notes, for the person.

Paths in the review (the sheets, the subject) are relative to its folder.

Exit codes: list 0. new 0 written; 2 refused by --require; 3 the spec, an image
or the subject cannot be read, or a review is already there (--force replaces it).
answer 0 recorded; 3 the review is malformed. check 0 clear; 2 flagged (a person
looks at those items); 3 malformed, incomplete, or a sheet or the subject changed.
1 usage (an unknown flag, an id not on the checklist, an answer not in the list, no stage or
subject in the flags or the spec, a stage not on the list).
--selftest 0 pass, 2 fail. Pillow only (through contact_sheet.py).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contact_sheet import run as compose_sheet  # noqa: E402

SCHEMA = "review/1"
ANSWERS = ("defect", "clear", "unsure")
PASSES = ("a", "b")
SUFFIX = ".review.json"

# What each stage's sheet is, for `list`.
SHEETS = {
    "S1": "the approved three-quarter image and FRONT, LEFT, BACK, RIGHT from the turnaround sheet",
    "S3": "the 8-view mesh QA sheet: front, left, back, right, top, clay, occlusion, uv_atlas",
    "S3b": "paint_loop.py's turntable.png: eight yaws of the painted GLB (a before row with --compare); or "
           "concept_match.py's concept|render pairs: front, left, back, right, three_quarter",
    "S3c": "assemble_parts.py's compare.png: anchor and assembly, clay and textured, four columns",
    "S5": "game_mesh.py's showcase|game pairs at azimuth 0, 45, 90, 180 (front, three_quarter, side, back) "
          "and its bake_miss map (UV space: blue where only the second pass reached, red where neither did)",
    "S6": "markers_front.png and markers_side.png, then deform_gate.py --render's pose pictures",
    "S8": "one clip's rest and wrist stills, beside the source",
    "S12": "the Unity screenshot under the game camera",
    "A2": "a 2D clip's frames in order, one cell each, after the approved still (codex-visual PHASE 3A)",
}

# The checklists: stage -> [{id, question, views?}]. Every question asks about a defect, so "defect"
# always means something is wrong and "clear" that it is not there.
CHECKLISTS: dict[str, list[dict[str, Any]]] = {
    "S1": [
        {"id": "s1.same_character", "question": "Does any view show a different character from the others "
         "(shape, colours, proportions or a detail added or lost)?"},
        {"id": "s1.sides_mirror", "question": "Do the LEFT and RIGHT views fail to mirror each other, or does "
         "the LEFT view face anywhere but the left edge?", "views": ["left", "right"]},
        {"id": "s1.ears_edge_on", "question": "Does an ear show its inner side to the viewer in one side view "
         "and not in the other?", "views": ["left", "right"]},
        {"id": "s1.thin_parts", "question": "Does a thin part (an ear, a tail, a strap) change length, "
         "thickness or angle between views, or cross the body or a limb?"},
        {"id": "s1.arm_gap", "question": "Is the open space under either arm missing in the FRONT or BACK "
         "view?", "views": ["front", "back"]},
        {"id": "s1.leg_gap", "question": "Do the legs touch, with no gap between them in the FRONT or BACK "
         "view?", "views": ["front", "back"]},
        {"id": "s1.pose", "question": "Is the pose anything but a symmetric A-pose (arms not about 45 degrees "
         "down, an elbow bent, one side different)?", "views": ["front", "back"]},
        {"id": "s1.hands", "question": "In any view, is anything held in a hand, worn on a forearm or touching "
         "a hand (a shield, a weapon, a board, a bag)?"},
        {"id": "s1.prop_sheet", "question": "Is a prop the design has (a shield, a weapon, a board) drawn in "
         "these views, on the character or beside it, instead of on a sheet of its own?"},
        {"id": "s1.shadow", "question": "Is there a cast or contact shadow, a ground, a glow or a rim light?"},
        {"id": "s1.scale", "question": "Do the views differ in scale or baseline (one taller, one standing "
         "higher)?"},
        {"id": "s1.cropped", "question": "Is any part of the character cut off by the frame or overlapping "
         "another view?"},
    ],
    "S3": [
        {"id": "s3.fused_limb", "question": "Is any limb fused to the body or to another limb?",
         "views": ["front", "back", "clay"]},
        {"id": "s3.held_prop", "question": "Does the mesh carry anything held in a hand, worn on a forearm or "
         "touching a hand (a shield, a weapon, a board, a bag)?", "views": ["front", "left", "right", "clay"]},
        {"id": "s3.hole", "question": "Is there a hole, a missing part or a torn edge in the silhouette?"},
        {"id": "s3.inner_shell", "question": "Does any view show a second inner shell, a sheet or slab standing "
         "off the surface, or z-fighting?", "views": ["clay", "occlusion"]},
        {"id": "s3.thin_parts", "question": "Is a thin part (an ear, a tail, a finger, a strap) missing, broken "
         "off or melted into a blob?"},
        {"id": "s3.texture_colours", "question": "Do the texture colours depart from the concept views (a wrong "
         "colour, a part painted in another part's colour)?", "views": ["front", "back"]},
        {"id": "s3.texture_blotch", "question": "Is the texture blotchy or smeared, or does it carry a seam, a "
         "baked shadow or a baked highlight?"},
        {"id": "s3.proportions", "question": "Do the proportions differ from the concept views (head size, "
         "limb length, a shape added or lost)?", "views": ["front", "left"]},
        {"id": "s3.symmetry", "question": "Is one side of a symmetric body visibly different from the other "
         "(an arm thicker, a leg shorter)?", "views": ["front", "back"]},
        {"id": "s3.face", "question": "Is the face smeared, doubled, or off the front of the head?",
         "views": ["front"]},
        {"id": "s3.clay_surface", "question": "Does the clay or occlusion render show lumps, spikes, ridges or "
         "stair-step noise that the textured views hide?", "views": ["clay", "occlusion"]},
        {"id": "s3.uv_atlas", "question": "Does the UV atlas show large empty areas, overlapping islands, or "
         "one part stretched over most of it?", "views": ["uv_atlas"]},
    ],
    "S3b": [
        {"id": "s3b.seam", "question": "Is there a visible seam or colour step where two painted views meet?"},
        {"id": "s3b.collage", "question": "Does any yaw show a collage: a second copy of the character, or a "
         "face or pattern painted where it does not belong?"},
        {"id": "s3b.colours", "question": "Do the painted colours depart from the concept views?"},
        {"id": "s3b.unpainted", "question": "Is a large patch the camera sees left unpainted (the old texture, "
         "a different shade)?"},
        {"id": "s3b.baked_light", "question": "Is a shadow, a highlight or a background colour painted into "
         "the texture?"},
        {"id": "s3b.outline", "question": "Is there a dark or light outline along the silhouette or a part's "
         "edge?"},
        {"id": "s3b.washed_out", "question": "Is any area washed out, ghostly or blurred next to the rest?"},
        {"id": "s3b.lost_detail", "question": "Has a detail the concept views show (eyes, a logo, a stripe, a "
         "buckle) gone missing or moved?"},
    ],
    "S3c": [
        {"id": "s3c.head_shape", "question": "Does the assembled head differ in size, position or shape from "
         "the anchor's in any column?"},
        {"id": "s3c.face", "question": "Does the assembly's textured face read as another character (other "
         "eyes, mouth or expression)?"},
        {"id": "s3c.neck_seam", "question": "Is there a visible seam, gap, step or colour band at the neck?"},
        {"id": "s3c.hair", "question": "Is hair missing, floating off the head, or cutting into the face?"},
        {"id": "s3c.collar", "question": "Is a hood, collar or ponytail cut away, or left floating?"},
        {"id": "s3c.hole", "question": "Does the assembly have a hole or a missing part the anchor does not?"},
        {"id": "s3c.colours", "question": "Do the assembly's textured colours differ from the anchor's on any "
         "part?"},
        {"id": "s3c.double", "question": "Do two surfaces show through each other (the old head under the new "
         "one, z-fighting)?"},
    ],
    "S5": [
        {"id": "s5.silhouette", "question": "Does the game mesh's silhouette differ from the showcase's (a part "
         "lost, a shape flattened)?"},
        {"id": "s5.texture_blur", "question": "Is the game mesh's texture blurred, smeared or shifted against "
         "the showcase's?"},
        {"id": "s5.bake_artefact", "question": "Does the rebake show black spots, streaks, projection errors, "
         "or a part painted in another part's colour?"},
        {"id": "s5.shading", "question": "Does the shading show inverted, faceted or seamed normals the "
         "showcase does not?"},
        {"id": "s5.uv_seam", "question": "Is there a visible UV seam or colour step on the game mesh?"},
        {"id": "s5.joints", "question": "Are the elbows, knees, shoulders or hips too coarse to bend (a few "
         "edges, a sharp corner)?"},
        {"id": "s5.face", "question": "Has the face lost its features, or does it read as another character "
         "in the front or three-quarter pair?", "views": ["front", "three_quarter"]},
        {"id": "s5.hole", "question": "Is there a hole, a gap or a missing part on the game mesh?"},
    ],
    "S6": [
        {"id": "s6.hips", "question": "In the front picture, is a hip marker outside the thigh or off the "
         "crotch line?", "views": ["markers_front"]},
        {"id": "s6.knees_ankles", "question": "Is a knee marker off the knee (on a hem, a boot top or a pad), or "
         "an ankle marker off the ankle?", "views": ["markers_front"]},
        {"id": "s6.arms", "question": "Is a shoulder marker on the torso's surface, or an elbow or wrist "
         "marker off the arm?", "views": ["markers_front"]},
        {"id": "s6.spine_head", "question": "In the side picture, is the spine outside the body, the neck "
         "outside the neck, or the head top on a hat or a hair spike?", "views": ["markers_side"]},
        {"id": "s6.feet", "question": "Is a toe tip away from the front of the shoe, or a heel away from its "
         "back?", "views": ["markers_side"]},
        {"id": "s6.tear", "question": "In a pose picture, is the skin torn, pulled into strands, or parted "
         "between the legs (a coat, a skirt)?", "views": ["deep_squat", "leg_raise"]},
        {"id": "s6.joint_collapse", "question": "Does an elbow or knee collapse, pinch or lose volume at the "
         "bend?", "views": ["elbow_120", "deep_squat"]},
        {"id": "s6.intersection", "question": "Does a part pass through another (an arm through the torso, a "
         "leg through a leg) in a pose picture?"},
        {"id": "s6.wrong_bone", "question": "Does skin follow the wrong bone (a sleeve with the torso, hair with "
         "a hand)?"},
        {"id": "s6.hand", "question": "Does a hand fold into itself, or do fingers cross or splay, in the fist "
         "or mitten pose?", "views": ["fist", "mitten"]},
        {"id": "s6.spike", "question": "Does any vertex shoot out as a spike or a stretched sheet?"},
    ],
    "S8": [
        {"id": "s8.rest", "question": "In the rest still, does the target's pose differ from the source's (an "
         "arm angle, a bent spine, a turned foot)?", "views": ["rest"]},
        {"id": "s8.sides", "question": "Is left swapped with right (the target's left arm moving like the "
         "source's right)?"},
        {"id": "s8.limb_twist", "question": "Is a limb twisted, flipped, or bent the wrong way at a joint?"},
        {"id": "s8.wrist", "question": "Is a wrist bent at an angle the source's is not, or frozen while the "
         "forearm moves?"},
        {"id": "s8.hand_flip", "question": "Is a hand turned palm up, inside out, or flipped against the "
         "source's?"},
        {"id": "s8.feet", "question": "Does a foot sink into or float above the ground, or point another way "
         "than the source's?"},
        {"id": "s8.root", "question": "Is the whole character offset, leaning or turned against the source?"},
        {"id": "s8.mesh", "question": "Does the mesh tear, pinch, or pass through itself in any still?"},
    ],
    "S12": [
        {"id": "s12.texture_missing", "question": "Is the character pink, magenta, plain white or untextured "
         "anywhere?"},
        {"id": "s12.scale", "question": "Is the character the wrong size against the scene?"},
        {"id": "s12.placement", "question": "Is the character facing the wrong way, lying down, sunk into the "
         "ground or floating above it?"},
        {"id": "s12.inside_out", "question": "Do parts look inside out, see-through or black (flipped normals, "
         "wrong culling)?"},
        {"id": "s12.colours", "question": "Do the colours or brightness depart from the Blender renders (washed "
         "out, too dark, a wrong colour space)?"},
        {"id": "s12.pose", "question": "Is the pose broken: a limb at an impossible angle, a stretched bone, or "
         "the bind pose where a clip should play?"},
        {"id": "s12.chains", "question": "Does hair, a tail or a coat hang wrong, stick straight out, or pass "
         "through the body?"},
        {"id": "s12.prop", "question": "Is the prop missing, off the hand, or the wrong size?"},
        {"id": "s12.readability", "question": "Does the character read poorly at the game camera (features "
         "lost, the silhouette merging into the background)?"},
    ],
    "A2": [
        {"id": "a2.identity", "question": "Does any frame show a different character from the approved still "
         "(face, colours, proportions, a detail added or lost)?", "views": ["still"]},
        {"id": "a2.outfit", "question": "Does a colour, pattern or accessory change, appear or vanish between "
         "frames?"},
        {"id": "a2.pop", "question": "Does one frame jump out of the motion (a head, a limb or the whole body in "
         "a pose its neighbours do not lead into or out of)?"},
        {"id": "a2.size", "question": "Does the character grow, shrink or change its line weight from frame to "
         "frame?"},
        {"id": "a2.sides", "question": "Do the left and right arms or legs swap (the near limb drawn as the far "
         "one, a prop changing hands)?"},
        {"id": "a2.anatomy", "question": "Does any frame show an extra or missing limb, finger or ear, or a limb "
         "bent the wrong way?"},
        {"id": "a2.cut", "question": "Is any part cut off by its cell, or does a neighbouring cell's drawing show "
         "in it?"},
        {"id": "a2.edge", "question": "Is there a fringe, a halo, a key-coloured speck or a hole in a cut-out?"},
        {"id": "a2.loop", "question": "For a loop: does the last frame fail to lead back into the first?",
         "views": ["first", "last"]},
    ],
}
STAGES = tuple(CHECKLISTS)
# Stages whose cells are a sequence in time: sheet b reverses them instead of shuffling.
SEQUENCE_STAGES = ("S8", "A2")


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1, never 2: here 2 means a refusal or a flagged review."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


class Malformed(Exception):
    """The review file is not a review/1 draft or review this script can read: exit 3."""


class Usage(Exception):
    """An argument names something the review does not hold: exit 1."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rel_to(path: Path, base: Path) -> str:
    """`path` relative to `base`, with forward slashes; absolute when there is no relative path."""
    try:
        return Path(os.path.relpath(path.resolve(), base.resolve())).as_posix()
    except ValueError:                     # another drive on Windows
        return path.resolve().as_posix()


def review_paths(out: Path) -> tuple[Path, Path, Path]:
    """NAME.a.png, NAME.b.png and NAME.review.json from --out NAME (a trailing .review.json is dropped)."""
    name = out.name[:-len(SUFFIX)] if out.name.endswith(SUFFIX) else out.name
    base = out.with_name(name)
    return (base.with_name(name + ".a.png"), base.with_name(name + ".b.png"), base.with_name(name + SUFFIX))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    """Write through a temporary name, so a crash never leaves half a review."""
    temp = path.with_name(f".{path.name}.part")
    temp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


# ------------------------------------------------------------------------------------- list


def cmd_list(stage: str | None, as_json: bool) -> int:
    stages = [stage] if stage else list(STAGES)
    if as_json:
        print(json.dumps({s: {"sheet": SHEETS[s], "checklist": CHECKLISTS[s]} for s in stages},
                         indent=2, ensure_ascii=False))
        return 0
    for s in stages:
        print(f"{s}  {SHEETS[s]}")
        for item in CHECKLISTS[s]:
            views = f"  [{', '.join(item['views'])}]" if item.get("views") else ""
            print(f"  {item['id']:<20} {item['question']}{views}")
        print()
    return 0


# -------------------------------------------------------------------------------------- new


def from_spec(doc: dict[str, Any], base: Path, stage: str | None, subject: Path | None,
              require: list[Path] | None) -> tuple[str, Path, list[Path]]:
    """stage, subject and require: each flag given wins, else the spec's key (paths relative to the spec's
    folder). Raises Usage when a stage or a subject is in neither, or the stage is not on the list; ValueError
    when the spec's key is not text (a list of text for require)."""
    if stage is None:
        stage = doc.get("stage")
        if stage is None:
            raise Usage("no stage: give --stage, or a spec with \"stage\"")
        if not isinstance(stage, str):
            raise ValueError("the spec's stage must be text")
    if stage not in STAGES:
        raise Usage(f"stage {stage!r} is not one of {', '.join(STAGES)}")
    if subject is None:
        given = doc.get("subject")
        if given is None:
            raise Usage("no subject: give --subject, or a spec with \"subject\"")
        if not isinstance(given, str) or not given:
            raise ValueError("the spec's subject must be a path")
        subject = base / given
    if require is None:
        given = doc.get("require", [])
        if not isinstance(given, list) or not all(isinstance(r, str) and r for r in given):
            raise ValueError("the spec's require must be a list of paths")
        require = [base / r for r in given]
    return stage, subject, require


def cmd_new(stage: str | None, spec: Path, subject: Path | None, out: Path, require: list[Path] | None,
            reviewer: str, model: str | None, force: bool) -> tuple[int, dict[str, Any]]:
    path_a, path_b, path_review = review_paths(out)
    try:
        doc = json.loads(spec.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return 3, {"error": f"cannot read the spec {spec}: {exc}"}
    if not isinstance(doc, dict) or not isinstance(doc.get("items"), list) or "sheets" in doc:
        return 3, {"error": "the spec needs `items` (one sheet); a `sheets` spec makes several pairs, "
                            "so pre-review each sheet from its own spec"}
    try:
        stage, subject, require = from_spec(doc, spec.resolve().parent, stage, subject, require)
    except ValueError as exc:
        return 3, {"error": f"the spec {spec}: {exc}"}
    if path_review.exists() and not force:
        return 3, {"error": f"{path_review} is already there; --force replaces it and its answers"}
    labels = [item.get("label", "") if isinstance(item, dict) else "" for item in doc["items"]]
    if not subject.is_file():
        return 3, {"error": f"the subject {subject} is not a file"}
    digest = sha256_file(subject)
    seed = int(digest[:8], 16)
    code, res_a = compose_sheet(spec, path_a, require)
    if code != 0:
        return code, {"error": res_a.get("error"), "required": res_a.get("required", [])}
    if stage in SEQUENCE_STAGES:
        # a sequence keeps its neighbours: sheet b is the spec reversed, not shuffled, so a pop
        # or a loop seam can still be read on it
        seed = None
        rev = dict(doc, items=list(reversed(doc["items"])))
        tmp = spec.with_name(f".{spec.stem}.reversed{spec.suffix}")
        tmp.write_text(json.dumps(rev), encoding="utf-8")
        try:
            code, res_b = compose_sheet(tmp, path_b, require)
        finally:
            tmp.unlink(missing_ok=True)
        if code == 0:
            res_b["order"] = [list(range(len(doc["items"]) - 1, -1, -1))]
    else:
        code, res_b = compose_sheet(spec, path_b, require, seed)
    if code != 0:
        path_a.unlink(missing_ok=True)
        return code, {"error": res_b.get("error"), "required": res_b.get("required", [])}
    folder = path_review.parent
    review = {
        "schema": SCHEMA, "tool": "prereview.py", "stage": stage,
        "subject": {"path": rel_to(subject, folder), "sha256": digest},
        "sheets": [{"name": "a", "path": rel_to(path_a, folder), "sha256": sha256_file(path_a), "order": None},
                   {"name": "b", "path": rel_to(path_b, folder), "sha256": sha256_file(path_b),
                    "order": res_b["order"][0], "seed": seed}],
        "labels": labels,
        "checklist": [dict(item) for item in CHECKLISTS[stage]],
        "answers": {"a": {}, "b": {}},
        "flagged": [], "verdict": "draft", "reviewer": reviewer, "model": model, "ts": now(),
    }
    write_json(path_review, review)
    return 0, {"review": str(path_review), "sheets": [str(path_a), str(path_b)], "stage": stage,
               "items": len(review["checklist"]), "required": res_a.get("required", []),
               "next": "answer every item looking at sheet a only, then again looking at sheet b only; "
                       "then check"}


# ---------------------------------------------------------------------------------- reading


def load_review(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Malformed(f"cannot read {path}: {exc.strerror or exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Malformed(f"{path} is not JSON: {exc}") from exc
    problems = shape_errors(doc)
    if problems:
        raise Malformed(f"{path}: " + "; ".join(problems))
    return doc


def shape_errors(doc: Any) -> list[str]:
    """What keeps `doc` from being a review/1 file (answers may still be missing)."""
    if not isinstance(doc, dict):
        return ["not a JSON object"]
    errs = []
    if doc.get("schema") != SCHEMA:
        errs.append(f"schema is {doc.get('schema')!r}, not {SCHEMA!r}")
    for key in ("tool", "reviewer", "ts"):
        if not isinstance(doc.get(key), str) or not doc[key]:
            errs.append(f"{key} must be text")
    if doc.get("stage") not in STAGES:
        errs.append(f"stage {doc.get('stage')!r} is not one of {', '.join(STAGES)}")
    if "model" not in doc or not (doc["model"] is None or isinstance(doc["model"], str)):
        errs.append("model must be text or null")
    subject = doc.get("subject")
    if not (isinstance(subject, dict) and isinstance(subject.get("path"), str)
            and isinstance(subject.get("sha256"), str) and len(subject["sha256"]) == 64):
        errs.append("subject must be {path, sha256}")
    sheets = doc.get("sheets")
    if not (isinstance(sheets, list) and [s.get("name") if isinstance(s, dict) else None for s in sheets]
            == list(PASSES)):
        errs.append("sheets must be [a, b]")
    else:
        for s in sheets:
            if not (isinstance(s.get("path"), str) and isinstance(s.get("sha256"), str)):
                errs.append(f"sheet {s['name']} needs path and sha256")
            if "order" not in s or not (s["order"] is None or (isinstance(s["order"], list) and all(
                    isinstance(k, int) and not isinstance(k, bool) and k >= 0 for k in s["order"]))):
                errs.append(f"sheet {s['name']}: order must be a list of indices or null")
    checklist = doc.get("checklist")
    if not (isinstance(checklist, list) and checklist and all(
            isinstance(i, dict) and isinstance(i.get("id"), str) and isinstance(i.get("question"), str)
            for i in checklist)):
        errs.append("checklist must be a non-empty list of {id, question}")
    elif len({i["id"] for i in checklist}) != len(checklist):
        errs.append("checklist ids repeat")
    answers = doc.get("answers")
    if not (isinstance(answers, dict) and set(answers) == set(PASSES)
            and all(isinstance(answers[p], dict) for p in PASSES)):
        errs.append("answers must be {a: {...}, b: {...}}")
    if not isinstance(doc.get("flagged"), list) or not all(isinstance(i, str) for i in doc["flagged"]):
        errs.append("flagged must be a list of ids")
    if doc.get("verdict") not in ("draft", "clear", "flagged"):
        errs.append(f"verdict {doc.get('verdict')!r} is not draft, clear or flagged")
    if errs:
        return errs
    ids = {i["id"] for i in checklist}
    labels = doc.get("labels") if isinstance(doc.get("labels"), list) else None
    for p in PASSES:
        for ident, ans in answers[p].items():
            where = f"answers.{p}.{ident}"
            if ident not in ids:
                errs.append(f"{where}: not on the checklist")
            elif not isinstance(ans, dict):
                errs.append(f"{where}: must be {{answer, view, note}}")
            else:
                if ans.get("answer") not in ANSWERS:
                    errs.append(f"{where}: answer {ans.get('answer')!r} is not defect, clear or unsure")
                if "view" not in ans or not (ans["view"] is None or isinstance(ans["view"], str)):
                    errs.append(f"{where}: view must be a cell label or null")
                elif labels is not None and ans["view"] is not None and ans["view"] not in labels:
                    errs.append(f"{where}: view {ans['view']!r} is not a cell label ({', '.join(labels)})")
                if not isinstance(ans.get("note"), str):
                    errs.append(f"{where}: note must be text")
    return errs


# ----------------------------------------------------------------------------------- answer


def one_answer(doc: dict[str, Any], answer: Any, view: Any, note: Any) -> dict[str, Any]:
    if answer not in ANSWERS:
        raise Usage(f"--answer {answer!r}: one of {', '.join(ANSWERS)}")
    labels = doc.get("labels") if isinstance(doc.get("labels"), list) else None
    if view is not None and (not isinstance(view, str) or (labels is not None and view not in labels)):
        raise Usage(f"view {view!r} is not a cell label" + (f" ({', '.join(labels)})" if labels else ""))
    if note is not None and not isinstance(note, str):
        raise Usage("note must be text")
    return {"answer": answer, "view": view, "note": note or ""}


def cmd_answer(review: Path, pass_: str, ident: str | None, answer: str | None, view: str | None,
               note: str | None, source: str | None) -> tuple[int, dict[str, Any]]:
    doc = load_review(review)
    ids = [i["id"] for i in doc["checklist"]]
    if (ident is None) == (source is None):
        raise Usage("give --id with --answer, or --from FILE for a whole pass")
    if source is not None:
        try:
            text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
            given = json.loads(text)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise Usage(f"--from {source}: {exc}") from exc
        if not isinstance(given, dict):
            raise Usage("--from: a JSON object {id: {answer, view, note}}")
        new = {}
        for k, v in given.items():
            if k not in ids:
                raise Usage(f"--from: {k!r} is not on the {doc['stage']} checklist")
            if not isinstance(v, dict):
                raise Usage(f"--from: {k}: {{answer, view, note}}")
            new[k] = one_answer(doc, v.get("answer"), v.get("view"), v.get("note"))
    else:
        if ident not in ids:
            raise Usage(f"--id {ident!r} is not on the {doc['stage']} checklist ({', '.join(ids)})")
        if answer is None:
            raise Usage("--id needs --answer")
        new = {ident: one_answer(doc, answer, view, note)}
    doc["answers"][pass_].update(new)
    doc["flagged"], doc["verdict"], doc["ts"] = [], "draft", now()
    write_json(review, doc)
    missing = {p: [i for i in ids if i not in doc["answers"][p]] for p in PASSES}
    return 0, {"review": str(review), "pass": pass_, "recorded": sorted(new), "unanswered": missing}


# ------------------------------------------------------------------------------------ check


def cmd_check(review: Path) -> tuple[int, dict[str, Any]]:
    doc = load_review(review)
    folder = review.parent
    ids = [i["id"] for i in doc["checklist"]]
    missing = {p: [i for i in ids if i not in doc["answers"][p]] for p in PASSES}
    if missing["a"] or missing["b"]:
        return 3, {"review": str(review), "error": "every item is answered in both passes before check",
                   "unanswered": missing}
    changed = []
    for what, entry in [("sheet " + s["name"], s) for s in doc["sheets"]] + [("subject", doc["subject"])]:
        path = Path(entry["path"])
        path = path if path.is_absolute() else folder / path
        if not path.is_file():
            changed.append(f"{what} {entry['path']} is missing")
        elif sha256_file(path) != entry["sha256"]:
            changed.append(f"{what} {entry['path']} changed since the draft")
    if changed:
        return 3, {"review": str(review), "error": "the review no longer belongs to these files: "
                   + "; ".join(changed) + " (make a new draft)"}
    a, b = doc["answers"]["a"], doc["answers"]["b"]
    flagged = [i for i in ids if a[i]["answer"] != "clear" or b[i]["answer"] != "clear"
               or a[i]["answer"] != b[i]["answer"]]
    doc["flagged"], doc["verdict"], doc["ts"] = flagged, "flagged" if flagged else "clear", now()
    write_json(review, doc)
    questions = {i["id"]: i["question"] for i in doc["checklist"]}
    items = []
    for i in flagged:
        why = "the passes disagree" if a[i]["answer"] != b[i]["answer"] else f"both say {a[i]['answer']}"
        items.append({"id": i, "question": questions[i], "why": why, "a": a[i], "b": b[i]})
    out = {"review": str(review), "stage": doc["stage"], "verdict": doc["verdict"], "flagged": items,
           "sheets": [s["path"] if Path(s["path"]).is_absolute() else str(folder / s["path"]) for s in doc["sheets"]]}
    if flagged:
        out["next"] = ("a person looks at these items on the sheets; approving stays theirs "
                       "(registry.py status ID approved)")
    else:
        out["next"] = "nothing flagged; a person still approves (registry.py status ID approved)"
    return (2 if flagged else 0), out


# --------------------------------------------------------------------------------- selftest


def contract_out(path: Path, case: str) -> None:
    """Copy a review to where tools/check-contracts.py validates it against schemas/review-1.json:
    $UNITY_DEV_CONTRACT_OUT, else a fixed folder in the temp dir. Prints `selftest-output: PATH`."""
    import shutil
    out = os.environ.get("UNITY_DEV_CONTRACT_OUT") or os.path.join(tempfile.gettempdir(), "unity-dev-contract-out")
    os.makedirs(out, exist_ok=True)
    dest = os.path.join(out, f"prereview__{case}.review.json")
    shutil.copyfile(path, dest)
    print(f"selftest-output: {dest}")


def selftest() -> int:
    import contextlib
    import io

    from PIL import Image

    checks: list[tuple[str, bool]] = []

    def quiet(fn, *a, **k):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*a, **k)

    checks.append(("nine stages", list(STAGES) == ["S1", "S3", "S3b", "S3c", "S5", "S6", "S8", "S12", "A2"]
                   and set(SHEETS) == set(STAGES)))
    checks.append(("6-12 items a stage", all(6 <= len(c) <= 12 for c in CHECKLISTS.values())))
    all_ids = [i["id"] for c in CHECKLISTS.values() for i in c]
    checks.append(("ids unique, prefixed", len(all_ids) == len(set(all_ids)) and all(
        i["id"].startswith(s.lower() + ".") for s, c in CHECKLISTS.items() for i in c)))
    checks.append(("questions ask", all(i["question"].endswith("?") for c in CHECKLISTS.values() for i in c)))
    held = {s: {i["id"] for i in CHECKLISTS[s]} for s in ("S1", "S3")}
    checks.append(("held props stop at S1 and S3", {"s1.hands", "s1.prop_sheet"} <= held["S1"]
                   and "s3.held_prop" in held["S3"]))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cmd_list("S3", True)
    listed = json.loads(buf.getvalue())
    checks.append(("list --stage", code == 0 and list(listed) == ["S3"] and listed["S3"]["checklist"] == CHECKLISTS["S3"]))

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        views = ["front", "left", "back", "right", "top", "clay"]
        for k, name in enumerate(views):
            Image.new("RGB", (48, 48), (30 * k + 20, 120, 60)).save(t / f"{name}.png")
        spec = {"title": "Runner QA", "cols": 3, "cell": 64,
                "items": [{"image": f"{name}.png", "label": name} for name in views]}
        (t / "sheet.json").write_text(json.dumps(spec))
        (t / "runner.glb").write_bytes(b"glTF a courier runner")
        (t / "green.gate.json").write_text(json.dumps({"schema": "gate/1", "pass": True, "gates": [
            {"name": "glb.tris", "value": 1000, "limit": 50000, "pass": True}]}))
        (t / "red.gate.json").write_text(json.dumps({"schema": "gate/1", "pass": False, "gates": [
            {"name": "glb.tris", "value": 90000, "limit": 50000, "pass": False}]}))
        out = t / "review" / "runner_s3"
        code, res = cmd_new("S3", t / "sheet.json", t / "runner.glb", out, [t / "red.gate.json"], "claude", None, False)
        checks.append(("new refused by --require", code == 2 and not (t / "review" / "runner_s3.a.png").exists()))
        code, res = cmd_new("S3", t / "sheet.json", t / "runner.glb", out, [t / "green.gate.json"], "claude", None, False)
        review = t / "review" / "runner_s3.review.json"
        checks.append(("new writes a, b, draft", code == 0 and review.is_file()
                       and (t / "review" / "runner_s3.a.png").is_file() and (t / "review" / "runner_s3.b.png").is_file()))
        doc = json.loads(review.read_text())
        checks.append(("draft shape", shape_errors(doc) == [] and doc["verdict"] == "draft"
                       and doc["checklist"] == CHECKLISTS["S3"] and doc["answers"] == {"a": {}, "b": {}}
                       and doc["subject"]["path"] == "../runner.glb"
                       and doc["sheets"][0]["path"] == "runner_s3.a.png"))
        order = doc["sheets"][1]["order"]
        checks.append(("b is permuted", doc["sheets"][0]["order"] is None and sorted(order) == list(range(6))
                       and order != list(range(6))
                       and doc["sheets"][1]["seed"] == int(doc["subject"]["sha256"][:8], 16)))
        sheet_a = Image.open(t / "review" / "runner_s3.a.png").convert("RGB")
        sheet_b = Image.open(t / "review" / "runner_s3.b.png").convert("RGB")
        label_px = 14
        title_h, strip = label_px + 18, label_px + 10

        def cell(img, k):
            return img.getpixel(((k % 3) * 64 + 32, title_h + (k // 3) * (64 + strip) + strip + 32))
        checks.append(("a in spec order", all(cell(sheet_a, k) == (30 * k + 20, 120, 60) for k in range(6))))
        checks.append(("b cells follow order", all(cell(sheet_b, k) == (30 * order[k] + 20, 120, 60) for k in range(6))))
        # the label moves with its image: b's cell 0 caption is the label of item order[0]; compare the
        # caption strip of b's cell 0 with a's cell order[0]
        def strip_box(k):
            x, y = (k % 3) * 64, title_h + (k // 3) * (64 + strip)
            return (x, y, x + 64, y + strip)
        checks.append(("labels move", sheet_b.crop(strip_box(0)).tobytes() == sheet_a.crop(strip_box(order[0])).tobytes()))
        code, _ = cmd_new("S3", t / "sheet.json", t / "runner.glb", out, [], "claude", None, False)
        checks.append(("new keeps an existing review", code == 3))
        # a sequence stage reverses sheet b, so every frame keeps its neighbours
        code, _ = cmd_new("A2", t / "sheet.json", t / "runner.glb", t / "review" / "clip_a2", [], "claude",
                          None, False)
        seq = json.loads((t / "review" / "clip_a2.review.json").read_text())
        seq_b = Image.open(t / "review" / "clip_a2.b.png").convert("RGB")
        checks.append(("A2: b is the spec reversed, no seed", code == 0 and shape_errors(seq) == []
                       and seq["sheets"][1]["order"] == [5, 4, 3, 2, 1, 0] and seq["sheets"][1]["seed"] is None
                       and all(cell(seq_b, k) == (30 * (5 - k) + 20, 120, 60) for k in range(6))
                       and not list(t.glob(".*reversed*"))))

        code, res = cmd_check(review)
        checks.append(("unanswered -> 3", code == 3 and len(res["unanswered"]["a"]) == len(CHECKLISTS["S3"])))
        clear = {i["id"]: {"answer": "clear", "view": None, "note": ""} for i in CHECKLISTS["S3"]}
        (t / "clear.json").write_text(json.dumps(clear))
        code, res = cmd_answer(review, "a", None, None, None, None, str(t / "clear.json"))
        checks.append(("answer --from", code == 0 and res["unanswered"]["a"] == []
                       and len(res["unanswered"]["b"]) == len(CHECKLISTS["S3"])))
        partial = dict(clear)
        partial.pop("s3.uv_atlas")
        (t / "partial.json").write_text(json.dumps(partial))
        quiet(cmd_answer, review, "b", None, None, None, None, str(t / "partial.json"))
        code, res = cmd_check(review)
        checks.append(("one unanswered -> 3", code == 3 and res["unanswered"] == {"a": [], "b": ["s3.uv_atlas"]}))
        cmd_answer(review, "b", "s3.uv_atlas", "clear", None, None, None)
        code, res = cmd_check(review)
        doc = json.loads(review.read_text())
        checks.append(("all clear -> 0", code == 0 and res["verdict"] == "clear" and doc["verdict"] == "clear"
                       and doc["flagged"] == []))
        contract_out(review, "clear")

        code, res = cmd_answer(review, "b", "s3.hole", "defect", "left", "a gap under the left arm", None)
        checks.append(("answer resets the verdict", code == 0 and json.loads(review.read_text())["verdict"] == "draft"))
        code, res = cmd_check(review)
        doc = json.loads(review.read_text())
        checks.append(("disagreement -> 2", code == 2 and doc["verdict"] == "flagged" and doc["flagged"] == ["s3.hole"]
                       and res["flagged"][0]["b"]["view"] == "left" and res["flagged"][0]["why"] == "the passes disagree"))
        contract_out(review, "flagged")
        cmd_answer(review, "a", "s3.hole", "unsure", "left", "", None)
        cmd_answer(review, "b", "s3.hole", "unsure", "left", "", None)
        code, res = cmd_check(review)
        checks.append(("both unsure -> 2", code == 2 and res["flagged"][0]["why"] == "both say unsure"))

        for bad in (("b", "s3.nope", "defect", None), ("b", "s3.hole", "maybe", None), ("b", "s3.hole", "defect", "elbow")):
            try:
                cmd_answer(review, bad[0], bad[1], bad[2], bad[3], None, None)
                checks.append((f"usage {bad}", False))
            except Usage:
                checks.append((f"usage {bad}", True))
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                main(["answer", str(review), "--pass", "c", "--id", "s3.hole", "--answer", "clear"])
            checks.append(("bad pass exits 1", False))
        except SystemExit as exc:
            checks.append(("bad pass exits 1", exc.code == 1))
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                main(["check", str(review), "--bogus"])
            checks.append(("unknown flag exits 1", False))
        except SystemExit as exc:
            checks.append(("unknown flag exits 1", exc.code == 1))

        hand = json.loads(review.read_text())
        hand["answers"]["a"]["s3.hole"] = {"answer": "yes", "view": None, "note": ""}
        review.write_text(json.dumps(hand))
        checks.append(("hand edit validated -> 3", quiet(main, ["check", str(review)]) == 3))
        hand["answers"]["a"]["s3.hole"] = {"answer": "clear", "view": None, "note": ""}
        hand["answers"]["b"]["s3.hole"] = {"answer": "clear", "view": None, "note": ""}
        review.write_text(json.dumps(hand))
        checks.append(("hand edit accepted -> 0", quiet(main, ["check", str(review)]) == 0))

        with open(t / "review" / "runner_s3.b.png", "ab") as fh:
            fh.write(b"\0")
        code, res = cmd_check(review)
        checks.append(("changed sheet -> 3", code == 3 and "sheet b" in res["error"]))
        quiet(main, ["new", "--stage", "S3", "--spec", str(t / "sheet.json"), "--subject", str(t / "runner.glb"),
                     "--out", str(out), "--force"])
        cmd_answer(review, "a", None, None, None, None, str(t / "clear.json"))
        cmd_answer(review, "b", None, None, None, None, str(t / "clear.json"))
        (t / "runner.glb").write_bytes(b"glTF the runner, remeshed")
        code, res = cmd_check(review)
        checks.append(("changed subject -> 3", code == 3 and "subject" in res["error"]))
        (t / "sheets.json").write_text(json.dumps({"cols": 1, "cell": 64, "sheets": [{"name": "x", "items": spec["items"]}]}))
        code, _ = cmd_new("S3", t / "sheets.json", t / "runner.glb", t / "review" / "multi", [], "claude", None, False)
        checks.append(("sheets spec -> 3", code == 3))

        # the sidecar a producer writes: stage, subject and require in the spec, relative to its folder
        side = t / "rig"
        side.mkdir()
        (side / "gate.json").write_text(json.dumps({"schema": "gate/1", "pass": True, "gates": []}))
        (side / "red.json").write_text(json.dumps({"schema": "gate/1", "pass": False, "gates": []}))
        sidecar = dict(spec, items=[dict(i, image=f"../{i['image']}") for i in spec["items"]],
                       stage="S3", subject="../runner.glb", require=["gate.json"])
        (side / "prereview.spec.json").write_text(json.dumps(sidecar))
        code = quiet(main, ["new", "--spec", str(side / "prereview.spec.json"), "--out", str(t / "review" / "side")])
        sd = json.loads((t / "review" / "side.review.json").read_text()) if code == 0 else {}
        checks.append(("spec alone: stage, subject, require from the spec", code == 0 and sd.get("stage") == "S3"
                       and sd["subject"]["path"] == "../runner.glb" and sd["labels"] == views
                       and (t / "review" / "side.a.png").is_file() and (t / "review" / "side.b.png").is_file()))
        code = quiet(main, ["new", "--spec", str(side / "prereview.spec.json"), "--out", str(t / "review" / "side2"),
                            "--stage", "S3b", "--subject", str(t / "sheet.json"), "--require", str(t / "green.gate.json")])
        sd = json.loads((t / "review" / "side2.review.json").read_text()) if code == 0 else {}
        checks.append(("flags win over the spec", code == 0 and sd.get("stage") == "S3b"
                       and sd["subject"]["path"] == "../sheet.json" and sd["checklist"] == CHECKLISTS["S3b"]))
        (side / "prereview.spec.json").write_text(json.dumps(dict(sidecar, require=["red.json"])))
        code = quiet(main, ["new", "--spec", str(side / "prereview.spec.json"), "--out", str(t / "review" / "side3")])
        checks.append(("the spec's failing require -> 2", code == 2 and not (t / "review" / "side3.a.png").exists()))
        code = quiet(main, ["new", "--spec", str(side / "prereview.spec.json"), "--out", str(t / "review" / "side3"),
                            "--require", str(t / "green.gate.json")])
        checks.append(("--require replaces the spec's", code == 0))
        bare = {k: v for k, v in sidecar.items() if k != "stage"}
        (side / "bare.json").write_text(json.dumps(bare))
        for name, doc_, extra in (("no stage anywhere -> 1", bare, []),
                                  ("a stage not on the list -> 1", dict(sidecar, stage="S4"), []),
                                  ("no subject anywhere -> 1", {k: v for k, v in sidecar.items() if k != "subject"},
                                   ["--stage", "S3"])):
            (side / "bad.json").write_text(json.dumps(doc_))
            with contextlib.redirect_stderr(io.StringIO()):
                code = quiet(main, ["new", "--spec", str(side / "bad.json"), "--out", str(t / "review" / "bad"), *extra])
            checks.append((name, code == 1 and not (t / "review" / "bad.review.json").exists()))
        (side / "bad.json").write_text(json.dumps(dict(sidecar, require="gate.json")))
        code = quiet(main, ["new", "--spec", str(side / "bad.json"), "--out", str(t / "review" / "bad")])
        checks.append(("a require that is not a list -> 3", code == 3))

    failed = [name for name, ok in checks if not ok]
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": len(checks), "failed": failed}))
    return 0 if not failed else 2


# ------------------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = UsageParser(description=__doc__.split("\n")[0])
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="cmd", parser_class=UsageParser)
    p = sub.add_parser("list", help="print the checklists")
    p.add_argument("--stage", choices=STAGES)
    p.add_argument("--json", action="store_true", help="as JSON")
    p = sub.add_parser("new", help="compose sheets a and b and write the review/1 draft")
    p.add_argument("--stage", choices=STAGES, help="the checklist (default: the spec's stage)")
    p.add_argument("--spec", type=Path, required=True, help="contact_sheet.py's spec, with items")
    p.add_argument("--subject", type=Path, help="the file the sheet shows, pinned by sha256 (default: the spec's)")
    p.add_argument("--out", type=Path, required=True, help="review/NAME: writes NAME.a.png, NAME.b.png, NAME.review.json")
    p.add_argument("--require", nargs="+", action="extend", type=Path, default=None, metavar="FILE",
                   help="as on contact_sheet.py: every file must pass, or nothing is written (default: the spec's)")
    p.add_argument("--reviewer", default="claude", help="who answers (default claude)")
    p.add_argument("--model", help="the reviewer's model, when known")
    p.add_argument("--force", action="store_true", help="replace an existing review and its answers")
    p = sub.add_parser("answer", help="record answers into a draft")
    p.add_argument("review", type=Path)
    p.add_argument("--pass", dest="pass_", choices=PASSES, required=True, help="a or b: the sheet looked at")
    p.add_argument("--id", dest="ident", help="a checklist id")
    p.add_argument("--answer", help="defect, clear or unsure")
    p.add_argument("--view", help="the cell label the answer rests on")
    p.add_argument("--note", help="a short note for the person")
    p.add_argument("--from", dest="source", metavar="FILE", help="a whole pass: {id: {answer, view, note}}; - is stdin")
    p = sub.add_parser("check", help="validate, flag, and write the verdict")
    p.add_argument("review", type=Path)
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd is None:
        parser.error("a command: list, new, answer or check (or --selftest)")
    if args.cmd == "list":
        return cmd_list(args.stage, args.json)
    try:
        if args.cmd == "new":
            code, out = cmd_new(args.stage, args.spec, args.subject, args.out, args.require, args.reviewer,
                                args.model, args.force)
        elif args.cmd == "answer":
            code, out = cmd_answer(args.review, args.pass_, args.ident, args.answer, args.view, args.note, args.source)
        else:
            code, out = cmd_check(args.review)
    except Malformed as exc:
        code, out = 3, {"error": str(exc)}
    except Usage as exc:
        print(f"prereview.py {args.cmd}: error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main(["--selftest"] if sys.argv[1:] == ["selftest"] else None))
