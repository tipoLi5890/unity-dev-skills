#!/usr/bin/env python3
"""make_prompt.py — write a two-camera video prompt for a character from its words, its rig and one action sentence.

Ported from patch-gg/anymove (https://github.com/patch-gg/anymove), tools/make_prompt.py, commit
7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0. Changes from upstream: the template is written for an
upright humanoid (front camera at the face, side camera at the right side, arms and legs); the colour sentence and
the body count come from rig_info.json's twocam block, which skeleton.py / prepare_rig.py generate from the
contract's left and right limbs, instead of a hand-written creature.json; an image-to-video line asks the model to
keep the first frame, and a silence line asks for no sound (H3 makes audio with the video; it is discarded);
--check rebuilds one prompt file instead of a prompts/ tree; one JSON report; --selftest.

usage:
    make_prompt.py CHARACTER.json RIG_INFO.json "the runner crouches, leaps and throws a right punch at the top, then lands." [--out PROMPT.txt]
    make_prompt.py --check PROMPT.txt CHARACTER.json RIG_INFO.json
    make_prompt.py --selftest
CHARACTER.json ("twocam-character/1"): {"name": "runner", "noun": "courier runner", "describe": "a lean courier in
a grey jacket, cargo trousers and trainers"}; optional "count" overrides the rig's body count.
The prompt pins what video models otherwise drift on: both halves are one moment from two locked cameras, the
model stays exactly as rendered, every limb keeps its colour, the body count is fixed, the character stays centred,
no sound. Only the action changes from move to move: one action per 5 s clip.
Prints one JSON object (the prompt in "prompt"). Exit codes: 0 written (--check: rebuilds exactly), 2 --check found a
different prompt, 1 refused input or a failed selftest.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

TEMPLATE = (
    "Animate the exact {noun} game model shown twice in this split-screen image, starting from this exact frame. "
    "Left: a front camera, the {name} faces the viewer. Right: a side camera at its right side, the {name} faces "
    "right. Both are locked-off cameras filming the same {name} at the same moment, so every movement "
    "happens in both views at exactly the same time, frame for frame. Keep the model exactly as it is: {describe}. "
    "Its arms and legs are colour-coded and the colours never change or swap: {colour_code}. {count} "
    "Action: {action} It stays on the same spot, centred in both views, its whole body inside each view. "
    "One continuous 5-second shot at natural speed, no slow motion. The cameras never move, cut, pan or zoom; the "
    "plain grey studio background, the floor band and the dark vertical divider stay fixed. "
    "Silence: no music, no voices, no sound effects."
)


def prompt(character: dict, rig_info: dict, action: str) -> str:
    tc = rig_info.get("twocam") or {}
    if not tc.get("colour_code"):
        raise ValueError("rig_info.json has no twocam.colour_code (write it with skeleton.py or prepare_rig.py)")
    for k in ("name", "describe"):
        if not str(character.get(k, "")).strip():
            raise ValueError(f"CHARACTER.json needs '{k}'")
    action = action.strip()
    if not action:
        raise ValueError("empty action")
    if not action.endswith("."):
        action += "."
    return TEMPLATE.format(noun=character.get("noun", character["name"]), name=character["name"],
                           describe=character["describe"].strip().rstrip("."), colour_code=tc["colour_code"],
                           count=character.get("count", tc.get("count", "")).strip(), action=action)


def check(path, character, rig_info) -> tuple:
    text = Path(path).read_text(encoding="utf-8").strip()
    m = re.search(r"Action: (.*?) It stays on the same spot", text)
    if not m:
        return False, "no 'Action: ... It stays on the same spot' in the file (written by hand?)"
    return prompt(character, rig_info, m.group(1)) == text, m.group(1)


def selftest() -> int:
    checks = []

    def ok_(name, cond):
        checks.append({"name": name, "pass": bool(cond)})

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from skeleton import build_rig_info, demo_skeleton, read_skeleton
    info, _ = build_rig_info(read_skeleton(demo_skeleton()))
    ch = {"name": "runner", "noun": "courier runner", "describe": "a lean courier in a grey jacket and trainers"}
    p = prompt(ch, info, "the runner leaps and throws a right punch at the top, then lands")
    ok_("colours from the contract", "left arm pink, right arm blue, left leg yellow, right leg cyan" in p)
    ok_("silence stated", "Silence: no music" in p)
    ok_("first frame kept", "starting from this exact frame" in p)
    ok_("action closed with a full stop", "then lands. It stays" in p)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "c.json").write_text(json.dumps(ch)); (td / "r.json").write_text(json.dumps(info))
        out = td / "p.txt"
        ok_("CLI writes, exit 0", main([str(td / "c.json"), str(td / "r.json"), "the runner vaults the gate",
                                         "--out", str(out)], True) == 0)
        ok_("--check rebuilds exactly, exit 0", main(["--check", str(out), str(td / "c.json"), str(td / "r.json")], True) == 0)
        out.write_text(out.read_text().replace("pink", "red"))
        ok_("an edited colour fails --check, exit 2", main(["--check", str(out), str(td / "c.json"), str(td / "r.json")], True) == 2)
        bad = dict(info); bad.pop("twocam")
        (td / "r2.json").write_text(json.dumps(bad))
        ok_("a rig without twocam is refused, exit 1",
            main([str(td / "c.json"), str(td / "r2.json"), "jumps"], True) == 1)
    good = all(c["pass"] for c in checks)
    print(json.dumps({"tool": "make_prompt.py", "selftest": "pass" if good else "fail", "checks": len(checks),
                      "failed": [c["name"] for c in checks if not c["pass"]]}))
    return 0 if good else 1


def main(argv=None, quiet=False) -> int:
    argv = sys.argv[1:] if argv is None else argv
    emit = (lambda d: None) if quiet else (lambda d: print(json.dumps(d)))
    if "--selftest" in argv:
        return selftest()
    try:
        if argv and argv[0] == "--check":
            if len(argv) != 4:
                raise ValueError("--check PROMPT.txt CHARACTER.json RIG_INFO.json")
            ch = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
            ri = json.loads(Path(argv[3]).read_text(encoding="utf-8"))
            same, detail = check(argv[1], ch, ri)
            emit({"tool": "make_prompt.py", "op": "check", "file": argv[1], "rebuilds": same, "action": detail,
                  "ok": same})
            return 0 if same else 2
        ap = argparse.ArgumentParser(prog="make_prompt.py", description=__doc__.split("\n")[0])
        ap.add_argument("character"); ap.add_argument("rig_info"); ap.add_argument("action"); ap.add_argument("--out")
        a = ap.parse_args(argv)
        ch = json.loads(Path(a.character).read_text(encoding="utf-8"))
        ri = json.loads(Path(a.rig_info).read_text(encoding="utf-8"))
        text = prompt(ch, ri, a.action)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit({"tool": "make_prompt.py", "ok": False, "error": f"refused: {exc}"})
        return 1
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    emit({"tool": "make_prompt.py", "op": "write", "out": a.out, "prompt": text, "ok": True})
    return 0


if __name__ == "__main__":
    sys.exit(main())
