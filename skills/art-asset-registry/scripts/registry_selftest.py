#!/usr/bin/env python3
"""registry_selftest.py — the cases behind `registry.py selftest`.

Every case runs in its own temporary directory on a courier-run project and raises
AssertionError on the first thing that is wrong. `registry.py selftest` runs them all and exits
0 when every case passed, 2 otherwise. Running this file does the same. Standard library only.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry_ledger as L  # noqa: E402


def _registry():
    for name in ("registry", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "cmd_record") and hasattr(mod, "Ctx"):
            return mod
    import registry
    return registry


R = None
ART = "ArtDirection"


# ------------------------------------------------------------------------------------- helpers


def _rec(ident, path, **extra):
    rec = {"schema": L.SCHEMA, "id": ident, "ts": L.now_utc(), "kind": "other",
           "status": "candidate", "source": "generated", "files": [{"path": path, "role": "shipped"}]}
    rec.update(extra)
    return rec


def _append_job(job):
    """One worker of the concurrency case: append one record, rev assigned under the lock."""
    led, ident, k = job
    rec = _rec(ident, f"ArtDirection/courier/{ident.rsplit('/', 1)[-1]}.png", note=f"job {k}")
    return L.append(led, rec, assign_rev=True)["rev"]


def _project(d):
    root = os.path.join(d, "proj")
    os.makedirs(os.path.join(root, ART))
    return root, os.path.join(root, ART, "assets.jsonl")


def _put(root, rel, data):
    full = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as fh:
        fh.write(data)
    return full


def _pinned(root, rel, **extra):
    full = os.path.join(root, *rel.split("/"))
    return dict({"path": rel, "role": "shipped", "sha256": L.sha256_file(full),
                 "bytes": os.path.getsize(full)}, **extra)


def _cli(root, led, command, *rest):
    return R.run_quiet(command, "--root", root, "--ledger", led, *rest)


def _check(root, led, *extra):
    code, out = _cli(root, led, "check", "--json", *extra)
    data = json.loads(out)
    return code, {(i["level"], i["rule"]) for i in data["items"]}


def _errors(rules):
    return {r for lv, r in rules if lv == "ERROR"}


def _record(root, led, part, *flags):
    src = os.path.join(os.path.dirname(root), f"part-{len(os.listdir(os.path.dirname(root)))}.json")
    with open(src, "w", encoding="utf-8") as fh:
        json.dump(part, fh, ensure_ascii=False)
    return _cli(root, led, "record", "--json", src, *flags)


def _git(root, *args):
    subprocess.run(["git", "-C", root] + list(args), capture_output=True, check=True)


def _current(led):
    return L.last_by_id(L.load(led))


# --------------------------------------------------------------------------------------- cases


def t_append_load(d):
    led = os.path.join(d, "assets.jsonl")
    first = _rec("artdirection/sheets/runner-run", "ArtDirection/sheets/runner_run.png")
    L.append(led, first, assign_rev=True)
    L.append(led, dict(first, status="approved"), assign_rev=True)
    with open(led, "rb") as fh:
        raw = fh.read()
    assert raw.count(b"\n") == 2 and raw.endswith(b"\n"), "two records are not two lines"
    recs = L.load(led)
    assert [r["rev"] for r in recs] == [1, 2], [r["rev"] for r in recs]
    assert L.validate(recs[0]) == [], L.validate(recs[0])
    try:
        L.append(led, dict(first, note=float("nan")), assign_rev=True)
    except ValueError:
        pass
    else:
        raise AssertionError("append wrote a NaN")
    assert len(L.load(led)) == 2, "a refused append left a line behind"


def t_last_wins(d):
    led = os.path.join(d, "assets.jsonl")
    L.append(led, _rec("runner", "ArtDirection/runner.png"), assign_rev=True)
    L.append(led, _rec("mallet", "ArtDirection/mallet.png"), assign_rev=True)
    L.append(led, _rec("runner", "ArtDirection/runner.png", status="approved"), assign_rev=True)
    cur = L.last_by_id(L.load(led))
    assert cur["runner"]["status"] == "approved" and cur["runner"]["rev"] == 2, cur["runner"]
    assert cur["mallet"]["rev"] == 1
    try:
        L.append(led, _rec("runner", "ArtDirection/runner.png"), expect_rev=1)
    except L.LedgerConflict:
        pass
    else:
        raise AssertionError("expect_rev=1 was accepted after rev 2")


def t_validate(d):
    good = dict(_rec("artdirection/sheets/runner-run", "ArtDirection/sheets/runner_run.png"), rev=1)
    assert L.validate(good) == [], L.validate(good)
    cases = [({"id": "Runner Run"}, "id:"), ({"id": "artdirection/Runner"}, "id:"),
             ({"files": []}, "files:"),
             ({"files": [{"path": "/abs/runner.png"}]}, "absolute"),
             ({"files": [{"path": "ArtDirection/../runner.png"}]}, "'..'"),
             ({"files": [{"path": "ArtDirection\\runner.png"}]}, "backslash"),
             ({"source": "purchased"}, "license:"), ({"kind": "Mesh"}, "kind:"),
             ({"status": "pending"}, "status:"), ({"ts": "2026-13-01"}, "ts:"),
             ({"params": {"prompt": "a courier"}}, "params.prompt"),
             ({"params": {"argv": ["--server", "http://10.0.0.2:8188"]}}, "URL"),
             ({"gates": [{"name": "frames.count"}]}, "gates[0].pass"),
             ({"gates": [{"name": "tris", "value": float("nan"), "pass": True}]}, "gates[0].value"),
             ({"gates": [{"name": "tris", "value": float("-inf"), "pass": True}]}, "gates[0].value"),
             ({"links": [{"rel": "made-under", "to": "Art Direction"}]}, "links[0].to"),
             ({"links": [{"rel": "Made Under", "to": "art:direction"}]}, "links[0].rel"),
             ({"art_version": 2}, "art_version: unknown")]
    for patch, needle in cases:
        errs = L.validate(dict(good, **patch), strict=needle.endswith("unknown"))
        assert any(needle in e for e in errs), (patch, errs)
    assert L.validate(dict(good, kind="turnaround-sheet")) == [], "an open kind was refused"
    assert L.vocabulary_notes(dict(good, kind="turnaround-sheet")), "no note for an unknown kind"
    assert L.validate(dict(good, status="diagnostic")) == []
    linked = dict(good, links=[{"rel": "made-under", "to": "art:direction", "rev": 2},
                               {"rel": "made-by", "to": "job:courier-0412"},
                               {"rel": "evidence", "to": "artdirection/qa/runner-run", "rev": 1}])
    assert L.validate(linked) == [], L.validate(linked)
    assert L.validate(dict(good, extra=1)) == [], "an unknown key failed without --strict"
    assert any("unknown key" in e for e in L.validate(dict(good, extra=1), strict=True))
    assert L.rel_posix(os.path.join(d, "a", "b.png"), d) == "a/b.png"
    try:
        L.rel_posix(os.path.dirname(d), d)
    except ValueError:
        pass
    else:
        raise AssertionError("a path outside the root was accepted")
    try:
        L.loads('{"value": NaN}')
    except ValueError:
        pass
    else:
        raise AssertionError("NaN parsed")


def t_ids(d):
    assert L.slugify("ArtDirection/sheets/Runner_Run.png") == "artdirection/sheets/runner-run"
    assert L.slugify("Assets/Models/Character/Runner/Runner@GateLatchSwing.fbx") == \
        "assets/models/character/runner/runner-gatelatchswing"
    composed = "ArtDirection/角色/Café.png"
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed and L.slugify(composed) == L.slugify(decomposed) == \
        "artdirection/角色/café", (L.slugify(composed), L.slugify(decomposed))
    a, b = L.slugify("ArtDirection/角色/跑者.png"), L.slugify("ArtDirection/角色/信差.png")
    assert a == "artdirection/角色/跑者" and b == "artdirection/角色/信差" and a != b, (a, b)
    # a vowel sign is a combining mark NFC does not compose: it stays in the id
    hi, hi2 = L.slugify("ArtDirection/नमस्ते.png"), L.slugify("ArtDirection/नमस्त.png")
    assert hi == "artdirection/नमस्ते" and hi != hi2 and L.is_id(hi) and L.is_id(hi2), (hi, hi2)
    assert L.slugify("ArtDirection/วิ่ง.png") == "artdirection/วิ่ง"
    star = L.slugify("ArtDirection/sheets/★.png")
    assert star.startswith("artdirection/sheets/") and len(star.rsplit("/", 1)[1]) == 8, star
    assert star != L.slugify("ArtDirection/sheets/☆.png")
    assert L.validate(dict(_rec(a, "ArtDirection/角色/跑者.png"), rev=1)) == []
    nfd_id = unicodedata.normalize("NFD", "artdirection/角色/café")
    assert any("id:" in e for e in L.validate(dict(_rec(nfd_id, "x.png"), rev=1))), "NFD id passed"

    # recording the decomposed spelling of a recorded file is a revision of the same asset
    root, led = _project(d)
    _put(root, composed, b"runner")
    code, out = _record(root, led, {"files": [composed]}, "--kind", "ref", "--source", "generated")
    assert code == 0, out
    code, out = _record(root, led, {"files": [decomposed]}, "--kind", "ref", "--source", "generated")
    assert code == 0, out
    recs = L.load(led)
    assert [r["id"] for r in recs] == ["artdirection/角色/café"] * 2 and recs[1]["rev"] == 2, recs
    for name in ("跑者", "信差"):
        _put(root, f"ArtDirection/角色/{name}.png", name.encode())
        code, out = _record(root, led, {"files": [f"ArtDirection/角色/{name}.png"]}, "--kind",
                            "ref", "--source", "generated")
        assert code == 0, out
    assert {"artdirection/角色/跑者", "artdirection/角色/信差"} <= set(_current(led))
    code, rules = _check(root, led)
    assert code == 0, rules


def t_rev_gap(d):
    root, led = _project(d)
    _put(root, "ArtDirection/runner.png", b"runner")
    pinned = [_pinned(root, "ArtDirection/runner.png")]
    L.append(led, _rec("artdirection/runner", "x", files=pinned, rev=1))
    code, rules = _check(root, led)
    assert code == 0, rules
    L.append(led, _rec("artdirection/runner", "x", files=pinned, rev=3))
    code, rules = _check(root, led)
    assert code == 2 and _errors(rules) == {"rev-gap"}, (code, rules)


def t_torn_and_corrupt(d):
    root, led = _project(d)
    _put(root, "ArtDirection/runner.png", b"runner")
    good = _rec("artdirection/runner", "x", files=[_pinned(root, "ArtDirection/runner.png")], rev=1)
    _put(root, "ArtDirection/assets.jsonl", (L.dumps(good) + "\n").encode()
         + b'{"schema": 1, "id": "artdirection/torn"')
    code, rules = _check(root, led)
    assert code == 0 and ("WARN", "torn-line") in rules, ("a torn last line must warn", code, rules)
    _put(root, "ArtDirection/mallet.png", b"mallet")
    code, out = _record(root, led, {"files": ["ArtDirection/mallet.png"]}, "--kind", "ref",
                        "--source", "authored")
    assert code == 0 and "torn-line" in out, out
    with open(led + ".torn", "rb") as fh:
        assert fh.read().startswith(b'{"schema": 1, "id": "artdirection/torn"'), "fragment lost"
    code, rules = _check(root, led)
    assert code == 0 and not any(r == "torn-line" for _, r in rules), rules
    # a broken line with lines after it is a corrupt ledger: check exit 3, every write stops
    _put(root, "ArtDirection/assets.jsonl", b'{"schema": 1, "id": "artdirection/torn"\n'
         + (L.dumps(good) + "\n").encode())
    code, rules = _check(root, led)
    assert code == 3 and ("ERROR", "corrupt-line") in rules, (code, rules)
    code, _ = _record(root, led, {"files": ["ArtDirection/mallet.png"]}, "--kind", "other",
                      "--source", "generated")
    assert code == 3, "record wrote into a corrupt ledger"
    _put(root, "ArtDirection/assets.jsonl", (L.dumps(good) + "\n").encode()
         + b'{"schema": 1, "id": "artdirection/x", "bytes": NaN}\n')
    code, rules = _check(root, led)
    assert code == 3 and ("ERROR", "corrupt-line") in rules, ("NaN must not parse", code, rules)
    code, _ = _cli(root, os.path.join(root, "nowhere.jsonl"), "check")
    assert code == 3, "a missing ledger did not exit 3"
    code, _ = R.run_quiet("check", "--no-such-flag")
    assert code == 3, "a usage error did not exit 3"


def t_hash_drift(d):
    root, led = _project(d)
    code, out = _cli(root, led, "init")
    assert code == 0, out
    sheet = "ArtDirection/sheets/runner_run.png"
    _put(root, sheet, b"frame-a")
    part = {"files": [{"path": sheet, "role": "shipped"}],
            "tool": {"skill": "codex-visual", "script": "codex_generate.py"},
            "gates": [{"name": "frames.count", "value": 8, "limit": 8, "pass": True}],
            "verdict": "green"}
    code, out = _record(root, led, part, "--kind", "sheet", "--source", "generated",
                        "--art-version", "2")
    assert code == 0, out
    ident = "artdirection/sheets/runner-run"
    code, rules = _check(root, led)
    assert code == 0, rules
    _put(root, sheet, b"frame-b")
    code, rules = _check(root, led)
    assert code == 2 and ("ERROR", "hash-drift") in rules, (code, rules)
    code, out = _cli(root, led, "status", ident, "approved")
    assert code == 2, f"approving a drifted file exited {code}: {out}"
    _put(root, sheet, b"frame-a")
    code, out = _cli(root, led, "status", ident, "approved")
    assert code == 0, out
    _put(root, sheet, b"frame-c")
    code, rules = _check(root, led)
    assert code == 2 and ("ERROR", "changed-after-approval") in rules, (code, rules)
    code, _ = _record(root, led, {"files": ["/elsewhere/runner.png"]}, "--kind", "ref",
                      "--source", "generated")
    assert code == 2, "a path outside --root is a refusal, exit 2"


def t_mutable_blend(d):
    root, led = _project(d)
    clip = "ArtDirection/clips/runner_gatelatchswing.fbx"
    blend = "ArtDirection/sources/Runner.blend"
    _put(root, clip, b"clip")
    _put(root, blend, b"blend v1")
    part = {"files": [{"path": clip, "role": "shipped"},
                      {"path": blend, "role": "source", "mutable": True}],
            "file": {"path": blend, "saved": True, "dirty": False}, "verdict": "green"}
    code, out = _record(root, led, part, "--kind", "clip", "--source", "authored")
    assert code == 0, out
    rec = L.load(led)[-1]
    assert rec["files"][1]["sha256"] == L.sha256_file(os.path.join(root, *blend.split("/")))
    assert rec["file"]["sha256"] == rec["files"][1]["sha256"], rec["file"]
    _put(root, blend, b"blend v2")
    code, rules = _check(root, led)
    assert code == 0 and ("WARN", "moved-on") in rules, (code, rules)
    # a working file outside --root is kept by its name only: no machine path in the ledger
    away = os.path.join(d, "elsewhere", "Runner.blend")
    code, out = _record(root, led, dict(part, file={"path": away, "saved": True}), "--kind",
                        "clip", "--source", "authored")
    assert code == 0 and "file-outside-root" in out, (code, out)
    assert L.load(led)[-1]["file"]["path"] == "Runner.blend", L.load(led)[-1]["file"]


def t_vendor_tracked(d):
    if shutil.which("git") is None:
        return "git not found"
    root, led = _project(d)
    _git(root, "init", "-q")
    crate = "ArtDirection/vendor/courier_pack/crate.fbx"
    _put(root, crate, b"crate")
    _git(root, "add", "-f", crate)
    code, out = _record(root, led, {"files": [{"path": crate, "role": "source", "vendor": True}]},
                        "--kind", "mesh", "--source", "purchased", "--license",
                        "purchased:courier-pack")
    assert code == 0, out
    code, rules = _check(root, led)
    assert code == 2 and ("ERROR", "vendor-not-ignored") in rules, (code, rules)
    _git(root, "rm", "-q", "--cached", crate)
    _put(root, ".gitignore", b"ArtDirection/vendor/\n")
    code, rules = _check(root, led)
    assert code == 0, rules
    label = "ArtDirection/textures/crate_label.png"
    _put(root, label, b"label")
    _git(root, "add", label)
    code, out = _record(root, led, {"files": [label]}, "--kind", "texture",
                        "--source", "third-party", "--license", "cc0")
    assert code == 0, out
    code, rules = _check(root, led)
    assert code == 0 and ("WARN", "licensed-tracked") in rules, (code, rules)
    code, rules = _check(root, led, "--strict")
    assert code == 2 and ("ERROR", "licensed-tracked") in rules, (code, rules)


def t_missing_parent(d):
    root, led = _project(d)
    turn = "ArtDirection/turnarounds/mallet.png"
    _put(root, turn, b"four views")
    part = {"files": [turn], "parent": ["artdirection/anchors/master"]}
    code, out = _record(root, led, part, "--kind", "ref", "--source", "generated")
    assert code == 2 and "unresolved-parent" in out, (code, out)
    L.append(led, _rec("artdirection/turnarounds/mallet", "x", files=[_pinned(root, turn)],
                       parent=["artdirection/anchors/master"]), assign_rev=True)
    code, rules = _check(root, led)
    assert code == 2 and ("ERROR", "unresolved-parent") in rules, (code, rules)
    _put(root, "ArtDirection/anchors/master.png", b"anchor")
    code, out = _record(root, led, {"files": ["ArtDirection/anchors/master.png"]},
                        "--kind", "ref", "--source", "authored")
    assert code == 0, out
    code, rules = _check(root, led)
    assert code == 0, rules
    code, out = _record(root, led, {"files": [turn], "links": [
        {"rel": "depends-on", "to": "artdirection/anchors/nowhere"}]}, "--kind", "ref")
    assert code == 2 and "unresolved-link" in out, (code, out)


def t_cycles(d):
    root, led = _project(d)
    for name in ("gate", "latch", "sentry"):
        _put(root, f"ArtDirection/props/{name}.png", name.encode())
    pin = {n: [_pinned(root, f"ArtDirection/props/{n}.png")] for n in ("gate", "latch", "sentry")}
    # parent: gate -> latch -> gate
    L.append(led, _rec("artdirection/props/gate", "x", files=pin["gate"], rev=1,
                       parent=["artdirection/props/latch"]))
    L.append(led, _rec("artdirection/props/latch", "x", files=pin["latch"], rev=1,
                       parent=["artdirection/props/gate"]))
    code, rules = _check(root, led)
    assert code == 2 and _errors(rules) == {"parent-cycle"}, (code, rules)
    # record refuses to close one: sentry's parent is gate, then gate's parent is sentry
    led2 = os.path.join(root, ART, "two.jsonl")
    for n in ("gate", "sentry"):
        code, out = _record(root, led2, {"files": [f"ArtDirection/props/{n}.png"]}, "--kind", "ref",
                            "--source", "generated")
        assert code == 0, out
    code, out = _record(root, led2, {"files": ["ArtDirection/props/sentry.png"],
                                     "parent": ["artdirection/props/gate"]}, "--kind", "ref")
    assert code == 0, out
    code, out = _record(root, led2, {"files": ["ArtDirection/props/gate.png"],
                                     "parent": ["artdirection/props/sentry"]}, "--kind", "ref")
    assert code == 2 and "parent-cycle" in out, (code, out)
    # superseded_by: gate -> latch -> gate, written by hand
    led3 = os.path.join(root, ART, "three.jsonl")
    L.append(led3, _rec("artdirection/props/gate", "x", files=pin["gate"], rev=1,
                        status="superseded", superseded_by="artdirection/props/latch"))
    L.append(led3, _rec("artdirection/props/latch", "x", files=pin["latch"], rev=1,
                        status="superseded", superseded_by="artdirection/props/gate"))
    code, rules = _check(root, led3)
    assert code == 2 and _errors(rules) == {"superseded-cycle"}, (code, rules)


def t_dual_owner(d):
    root, led = _project(d)
    _put(root, "ArtDirection/角色/跑者.png", b"runner")
    _put(root, "ArtDirection/角色/信差.png", b"courier")
    code, out = _record(root, led, {"files": ["ArtDirection/角色/跑者.png"]}, "--kind", "ref",
                        "--source", "generated")
    assert code == 0, out
    code, out = _record(root, led, {"files": ["ArtDirection/角色/跑者.png"]}, "--kind", "ref",
                        "--source", "generated", "--id", "artdirection/courier")
    assert code == 2 and "dual-owner" in out, (code, out)
    # written by hand, once composed and once decomposed: still one file, two owners
    nfd = unicodedata.normalize("NFD", "ArtDirection/角色/Café.png")
    _put(root, "ArtDirection/角色/Café.png", b"cafe")
    for ident, path in (("artdirection/角色/café", "ArtDirection/角色/Café.png"),
                        ("artdirection/old", nfd)):
        L.append(led, _rec(ident, path, rev=1, files=[{"path": path, "role": "shipped"}]))
    code, rules = _check(root, led)
    assert code == 2 and ("ERROR", "dual-owner") in rules, (code, rules)
    # the old one superseded by the new one hands the file on
    code, out = _cli(root, led, "status", "artdirection/old", "superseded",
                     "--by", "artdirection/角色/café")
    assert code == 0, out
    code, rules = _check(root, led)
    assert "dual-owner" not in _errors(rules), rules
    # mv onto another asset's file is refused
    code, out = _cli(root, led, "mv", "artdirection/角色/跑者", "ArtDirection/角色/Café.png")
    assert code == 2 and "dual-owner" in out, (code, out)
    # approving one of two hand-written ids that hold one file is refused, as check would fail it
    root, led = _project(os.path.join(d, "approve"))
    _put(root, "ArtDirection/gate.png", b"gate")
    for ident in ("x/one", "x/two"):
        L.append(led, _rec(ident, "x", files=[_pinned(root, "ArtDirection/gate.png")], rev=1))
    code, out = _cli(root, led, "status", "x/one", "approved")
    assert code == 2 and "dual-owner" in out, (code, out)
    assert _current(led)["x/one"]["status"] == "candidate"


def t_status(d):
    root, led = _project(d)
    names = ("runner_run", "runner_run_v2", "mallet", "qa_runner_run")
    for n in names:
        _put(root, f"ArtDirection/sheets/{n}.png", n.encode())
        code, out = _record(root, led, {"files": [f"ArtDirection/sheets/{n}.png"]},
                            "--kind", "qa-sheet" if n.startswith("qa") else "sheet",
                            "--source", "generated")
        assert code == 0, out
    old, new = "artdirection/sheets/runner-run", "artdirection/sheets/runner-run-v2"
    qa = "artdirection/sheets/qa-runner-run"
    for argv, want in ((("superseded", "--by", "artdirection/sheets/nowhere"), 3),
                       (("superseded", "--by", old), 2),
                       (("rejected", "--by", new), 3),
                       (("approved", "--approver", "lead", "--evidence", "artdirection/nowhere"), 3)):
        code, out = _cli(root, led, "status", old, *argv)
        assert code == want, (argv, code, out)
    code, out = _cli(root, led, "status", "artdirection/sheets/mallet", "rejected")
    assert code == 0, out
    code, out = _cli(root, led, "status", old, "superseded", "--by", "artdirection/sheets/mallet")
    assert code == 2 and "bad-successor" in out, (code, out)
    code, out = _cli(root, led, "status", new, "approved", "--approver", "lead",
                     "--evidence", qa, "--note", "QA sheet beside the anchor")
    assert code == 0, out
    rec = _current(led)[new]
    assert rec["approver"] == "lead" and rec["links"] == [{"rel": "evidence", "to": qa, "rev": 1}]
    code, out = _cli(root, led, "status", old, "superseded", "--by", new)
    assert code == 0, out
    code, out = _cli(root, led, "status", new, "superseded", "--by", old)
    assert code == 2 and "superseded-cycle" in out, (code, out)
    code, out = _cli(root, led, "status", old, "superseded", "--by", new)
    assert code == 0 and "nothing written" in out, out
    # the current version is the latest approved revision, also after a new candidate
    _put(root, "ArtDirection/sheets/runner_run_v2.png", b"regenerated")
    code, out = _record(root, led, {"files": ["ArtDirection/sheets/runner_run_v2.png"]})
    assert code == 0, out
    code, out = _cli(root, led, "history", new, "--json")
    data = json.loads(out)
    assert code == 0 and data["current_version"] == 2 and data["previous_good"] is None, data
    assert [h["status"] for h in data["history"]] == ["candidate", "approved", "candidate"]
    code, out = _cli(root, led, "status", new, "approved")
    assert code == 0, out
    data = json.loads(_cli(root, led, "history", new, "--json")[1])
    assert data["current_version"] == 4 and data["previous_good"] == 2, data
    code, rules = _check(root, led)
    assert code == 0, rules
    # a withdrawn approval is no current version; the last approved one is the fallback
    code, out = _cli(root, led, "status", new, "rejected")
    assert code == 0, out
    data = json.loads(_cli(root, led, "history", new, "--json")[1])
    assert data["current_version"] is None and data["previous_good"] == 4, data


def t_dirty_approve(d):
    root, led = _project(d)
    clip = "ArtDirection/clips/runner_gatelatchswing.fbx"
    _put(root, clip, b"clip")
    part = {"files": [{"path": clip, "role": "derived"}], "verdict": "green",
            "file": {"path": "ArtDirection/sources/Runner.blend", "saved": True, "dirty": True}}
    code, out = _record(root, led, part, "--kind", "clip", "--source", "authored")
    assert code == 0, out
    ident = "artdirection/clips/runner-gatelatchswing"
    code, out = _cli(root, led, "status", ident, "approved")
    assert code == 2 and "dirty-file" in out, (code, out)
    code, out = _cli(root, led, "status", ident, "approved", "--allow-dirty")
    assert code == 0, out
    cur = _current(led)[ident]
    assert cur["status"] == "approved" and cur["rev"] == 2 and cur.get("warnings"), cur


def t_diagnostic(d):
    root, led = _project(d)
    raw = "ArtDirection/diagnostics/mallet_raw_decode.glb"
    _put(root, raw, b"raw shape")
    code, out = _record(root, led, {"files": [raw]}, "--kind", "mesh", "--source", "generated",
                        "--status", "diagnostic", "--note", "raw shape decode: no remesh")
    assert code == 0 and "(diagnostic)" in out, out
    ident = "artdirection/diagnostics/mallet-raw-decode"
    os.remove(os.path.join(root, *raw.split("/")))
    code, rules = _check(root, led)
    assert code == 0, ("a diagnostic run's files are not held to disk", rules)
    code, out = _cli(root, led, "status", ident, "approved")
    assert code == 2 and "diagnostic" in out, (code, out)
    code, out = _cli(root, led, "stale", "--art-version", "9", "--json")
    assert json.loads(out)["stale"] == [], out


def t_stale_links(d):
    root, led = _project(d)
    for n in ("turnaround", "mallet", "crate"):
        _put(root, f"ArtDirection/props/{n}.png", n.encode())
    code, out = _record(root, led, {"files": ["ArtDirection/props/turnaround.png"]}, "--kind",
                        "ref", "--source", "generated", "--art-version", "2")
    assert code == 0, out
    turn = "artdirection/props/turnaround"
    code, out = _record(root, led, {"files": ["ArtDirection/props/mallet.png"]}, "--kind", "mesh",
                        "--source", "generated", "--art-version", "2",
                        "--link", f"depends-on={turn}", "--link", "made-by=job:courier-0412",
                        "--link", "made-under=flow:mesh@1")
    assert code == 0, out
    mallet = _current(led)["artdirection/props/mallet"]
    assert {"rel": "depends-on", "to": turn, "rev": 1} in mallet["links"], mallet["links"]
    code, out = _record(root, led, {"files": ["ArtDirection/props/crate.png"]}, "--kind", "mesh",
                        "--source", "generated", "--art-version", "1")
    assert code == 0, out

    def stale(*flags):
        code, out = _cli(root, led, "stale", "--json", *flags)
        assert code == 0, out
        return {s["id"] for s in json.loads(out)["stale"]}

    assert stale("--art-version", "2") == {"artdirection/props/crate"}
    assert stale() == set()
    # a status change upstream is not new content; new bytes are
    code, out = _cli(root, led, "status", turn, "approved")
    assert code == 0, out
    assert stale() == set(), "approving the turnaround made the mallet stale"
    _put(root, "ArtDirection/props/turnaround.png", b"turnaround v2")
    code, out = _record(root, led, {"files": ["ArtDirection/props/turnaround.png"]},
                        "--art-version", "2")
    assert code == 0, out
    assert stale() == {"artdirection/props/mallet"}
    assert stale("--at", "flow:mesh=2", "--art-version", "1") == {"artdirection/props/mallet"}
    code, out = _cli(root, led, "stale", "--at", "flow mesh=2")
    assert code == 3, out


def t_mv_render(d):
    root, led = _project(d)
    for name in ("runner_run", "mallet"):
        _put(root, f"ArtDirection/sheets/{name}.png", name.encode())
        code, out = _record(root, led, {"files": [f"ArtDirection/sheets/{name}.png"]},
                            "--kind", "sheet", "--source", "generated", "--art-version", "2")
        assert code == 0, out
    os.makedirs(os.path.join(root, ART, "props"))
    os.rename(os.path.join(root, ART, "sheets", "mallet.png"),
              os.path.join(root, ART, "props", "mallet.png"))
    code, rules = _check(root, led)
    assert code == 2 and ("ERROR", "missing") in rules, (code, rules)
    code, out = _cli(root, led, "mv", "artdirection/sheets/mallet", "ArtDirection/props/mallet.png")
    assert code == 0, out
    cur = _current(led)["artdirection/sheets/mallet"]
    assert cur["files"][0]["path"] == "ArtDirection/props/mallet.png" and cur["rev"] == 2, cur
    code, rules = _check(root, led)
    assert code == 0, rules
    code, out = _cli(root, led, "status", "artdirection/sheets/runner-run", "superseded",
                     "--by", "artdirection/sheets/mallet")
    assert code == 0, out
    code, out = _cli(root, led, "render")
    rows = [r for r in out.splitlines() if r]
    assert code == 0 and len(rows) == 2 and all(r.startswith("| ") for r in rows), out
    assert any("| superseded | 2 |" in r for r in rows), rows


def t_init_ignored(d):
    root = os.path.join(d, "proj")
    os.makedirs(root)
    saved = os.environ.pop("ART_LEDGER", None)
    try:
        code, out = R.run_quiet("init", "--root", root)
        assert code == 0 and os.path.isfile(os.path.join(root, ART, "assets.jsonl")), out
        code, out = R.run_quiet("init", "--root", root)
        assert code == 0 and "exists" in out, out
        if shutil.which("git") is None:
            return "git not found (the created and exists halves passed)"
        _git(root, "init", "-q")
        _put(root, ".gitignore", b"ArtDirection/\n")
        code, out = R.run_quiet("init", "--root", root)
        assert code == 0 and "git-ignored" in out, out
        os.environ["ART_LEDGER"] = os.path.join(root, "Docs", "art", "assets.jsonl")
        code, out = R.run_quiet("init", "--root", root)
        assert code == 0 and os.path.isfile(os.environ["ART_LEDGER"]), out
        assert "the ledger is git-ignored" not in out and "ArtDirection/: git-ignored" in out, out
    finally:
        os.environ.pop("ART_LEDGER", None)
        if saved is not None:
            os.environ["ART_LEDGER"] = saved


def t_concurrent(d):
    led = os.path.join(d, "assets.jsonl")
    ids = [f"artdirection/courier/runner-{k}" for k in range(5)]
    jobs = [(led, ids[k % len(ids)], k) for k in range(100)]
    with multiprocessing.get_context("spawn").Pool(8) as pool:
        revs = pool.map(_append_job, jobs, chunksize=1)
    problems, torn = [], []
    lines = L.load_lines(led, problems, torn)
    assert not problems and not torn and len(lines) == 100, (problems, torn, len(lines))
    for ident in ids:
        seq = [r["rev"] for _, r in lines if r["id"] == ident]
        assert seq == list(range(1, 21)), (ident, seq)
    assert sorted(revs) == sorted(list(range(1, 21)) * 5)


H3_LOCAL = {"source": "minimax-h3-local", "id": "runner-run-take-2",
            "territory": {"excludes": ["US", "EU", "UK", "KR"]}}


def t_territory(d):
    root, led = _project(d)

    def declare(line):
        path = os.path.join(root, "ART_DIRECTION.md")
        if line is None:
            if os.path.exists(path):
                os.remove(path)
            return
        _put(root, "ART_DIRECTION.md", ("# Courier run\n\nStatus: LOCKED\n\n```\nSales territory: "
                                        "worldwide\n```\n\n" + line + "\n").encode())

    def territory_rules(line):
        declare(line)
        return _check(root, led)

    # licence objects: their shape is the schema's
    for lic, want in (({"source": "motion-solver", "territory": "global"}, "licence.territory:"),
                      ({"source": "motion-solver"}, "licence.territory:"),
                      ({"source": "Gem X", "territory": "worldwide"}, "licence.source:"),
                      ({"source": "hy-motion", "territory": {"excludes": ["usa"]}},
                       "licence.territory.excludes[0]:"),
                      ({"source": "hy-motion", "territory": {"excludes": []}}, "licence.territory:"),
                      ("hy-motion", "licence:")):
        errs = L.validate(_rec("artdirection/clips/x", "ArtDirection/clips/x.fbx", rev=1,
                               licence=lic))
        assert any(e.startswith(want) for e in errs), (lic, errs)
    assert not L.validate(_rec("artdirection/clips/x", "ArtDirection/clips/x.fbx", rev=1,
                               licence=H3_LOCAL), strict=True)
    assert L.territory_codes(["UK", "EL"]) == {"GB", "GR"} and "DE" in L.territory_codes(["EU"])

    # an approved clip whose own licence excludes territories
    video = "ArtDirection/motion/runner_run_h3.mp4"
    clip = "ArtDirection/clips/runner_run.fbx"
    _put(root, video, b"generated performance video")
    _put(root, clip, b"clip solved from the video")
    code, out = _record(root, led, {"files": [video], "licence": H3_LOCAL}, "--kind", "preview",
                        "--source", "generated")
    assert code == 0, out
    vid = "artdirection/motion/runner-run-h3"
    code, out = _cli(root, led, "status", vid, "approved")       # nothing declared: a warning
    assert code == 0 and "territory-undeclared" in out, (code, out)
    for line, want_code, want in (
            (None, 0, ("WARN", "territory-undeclared")),
            ("Sales territory: undecided", 0, ("WARN", "territory-undeclared")),
            ("**Sales territory:** JP, TW", 0, None),
            ("Sales territory: worldwide", 2, ("ERROR", "territory-excluded")),
            ("- Sales territory: JP, DE", 2, ("ERROR", "territory-excluded")),   # DE is in the EU
            ("Sales territory: GB", 2, ("ERROR", "territory-excluded")),         # UK is GB
            ("Sales territory: JP, Narnia", 0, ("WARN", "territory-unknown"))):
        code, rules = territory_rules(line)
        assert code == want_code, (line, code, rules)
        if want:
            assert want in rules, (line, rules)
        else:
            assert not {r for _, r in rules if r.startswith("territory")}, (line, rules)
    # a declared EU meets a licence that excludes one member state
    code, out = _cli(root, led, "status", vid, "rejected")
    assert code == 0, out
    one = "ArtDirection/motion/runner_idle.mp4"
    _put(root, one, b"idle")
    code, out = _record(root, led, {"files": [one], "licence": {
        "source": "hy-motion", "territory": {"excludes": ["FR"]}}}, "--kind", "preview",
        "--source", "generated")
    assert code == 0, out
    declare("Sales territory: EU")
    code, out = _cli(root, led, "status", "artdirection/motion/runner-idle", "approved")
    assert code == 2 and "territory-excluded" in out and "excludes FR" in out, (code, out)
    code, out = _cli(root, led, "status", "artdirection/motion/runner-idle", "rejected")
    assert code == 0, out

    # upstream: the clip's own licence is clean, its parent's is not
    declare("Sales territory: worldwide")
    code, out = _record(root, led, {"files": [clip], "parent": [vid],
                                    "licence": {"source": "motion-solver", "territory": "worldwide"}},
                        "--kind", "clip", "--source", "generated")
    assert code == 0, out
    cid = "artdirection/clips/runner-run"
    code, rules = _check(root, led)
    assert code == 0, ("a candidate is never refused for its territory", rules)
    code, out = _cli(root, led, "status", cid, "approved", "--approver", "lead")
    assert code == 2 and "territory-excluded" in out and f"via {cid} -> {vid}" in out, (code, out)
    assert "excludes EU, GB, KR, US" in out, out
    # the same through a depends-on link only, refused by record --status approved too
    take = "ArtDirection/clips/runner_run_take2.fbx"
    _put(root, take, b"second take")
    code, out = _record(root, led, {"files": [take], "links": [{"rel": "depends-on", "to": vid}],
                                    "licence": {"source": "motion-solver", "territory": "worldwide"}},
                        "--kind", "clip", "--source", "generated", "--status", "approved")
    assert code == 2 and "territory-excluded" in out and "nothing recorded" in out, (code, out)
    declare("Sales territory: JP, TW")
    code, out = _cli(root, led, "status", cid, "approved", "--approver", "lead")
    assert code == 0, out
    rec = _current(led)[cid]
    assert rec["licence"]["source"] == "motion-solver", rec
    _put(root, clip, b"clip solved again")
    code, out = _record(root, led, {"files": [clip]})        # a new revision keeps the licence
    assert code == 0 and _current(led)[cid].get("licence", {}).get("source") == "motion-solver", out
    # a circle through parent ends: the rule visits each id once
    ring = ("ArtDirection/motion/a.png", "ArtDirection/motion/b.png")
    for p in ring:
        _put(root, p, p.encode())
    for i, p in enumerate(ring):
        L.append(led, _rec(f"artdirection/motion/{'ab'[i]}", p, status="approved",
                           parent=[f"artdirection/motion/{'ba'[i]}"], licence=H3_LOCAL,
                           files=[_pinned(root, p)]), assign_rev=True)
    declare("Sales territory: KR")
    code, rules = _check(root, led)
    assert code == 2 and {"parent-cycle", "territory-excluded"} <= _errors(rules), rules


def t_adopt_ingest(d):
    import registry_adopt
    import registry_ingest
    registry_adopt.selftest(os.path.join(d, "a"))
    registry_ingest.selftest(os.path.join(d, "i"))


CASES = (("append-load", t_append_load), ("last-wins", t_last_wins), ("validate", t_validate),
         ("ids-nfc-cjk", t_ids), ("rev-gap", t_rev_gap), ("torn-and-corrupt", t_torn_and_corrupt),
         ("hash-drift", t_hash_drift), ("mutable-blend", t_mutable_blend),
         ("vendor-tracked", t_vendor_tracked), ("missing-parent", t_missing_parent),
         ("cycles", t_cycles), ("dual-owner", t_dual_owner), ("status", t_status),
         ("dirty-approve", t_dirty_approve), ("diagnostic", t_diagnostic),
         ("stale-links", t_stale_links), ("mv-render", t_mv_render),
         ("init-ignored", t_init_ignored), ("concurrent-append", t_concurrent),
         ("territory", t_territory), ("adopt-ingest", t_adopt_ingest))


def run(rep):
    """Every case; the Report gets one OK, WARN (skipped) or ERROR line per case."""
    global R
    R = _registry()
    failed = []
    with tempfile.TemporaryDirectory(prefix="registry-selftest-") as tmp:
        for name, case in CASES:
            d = os.path.join(tmp, name)
            os.makedirs(d)
            try:
                skipped = case(d)
            except Exception as e:                       # a failed assert, or anything it raised
                failed.append(name)
                rep.error("selftest", name, f"{e.__class__.__name__}: {e}")
                continue
            if skipped:
                rep.warn("selftest", name, f"skipped: {skipped}")
            else:
                rep.ok("selftest", name)
    rep.data.update(cases=len(CASES), failed=failed)
    if failed:
        rep.summary("ERROR", "selftest", f"{len(failed)} of {len(CASES)} case(s) failed")
        return R.FAILED
    rep.summary("OK", "selftest", f"{len(CASES)} of {len(CASES)} cases passed")
    return R.OK


if __name__ == "__main__":
    sys.exit(_registry().main(["selftest", *sys.argv[1:]]))
