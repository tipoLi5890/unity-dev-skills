#!/usr/bin/env python3
"""registry_ingest.py — a producer's JSON output as a ledger record (`registry.py ingest`).

  registry.py ingest --json FILE [--kind K] [--file PATH ...]           print the partial record
  registry.py ingest --json FILE [--kind K] [--file PATH ...] --write   record it

The shapes it reads, tried in this order:
  record       any JSON with a `record` object (the Blender skills' reports carry one): that
               object is the partial record. A top-level `file` ({path, saved, dirty}) is carried
               in, and what the JSON's own shape below would add fills the keys the record leaves
               out
  frames       sheet_to_frames.py's frames.json, or any frames.json naming its `producer`
               ({skill, script}: breathe.py, video_loop.py): the sidecar and every frame
               (relative to it), the sheet or `source` as input, one `frames.faults` gate
  blender      a Blender skill's report (`gates` and `blender`): its gates and verdict; the file
               it wrote comes from --file, else its top-level `path`, else the saved .blend
               (role source, mutable; hashed like any file, so each version has its sha256)
  codex        codex_generate.py's output (`out` and `size`): the image, a `codex.size` gate when
               --expect-size was given; more than one image is refused (none was chosen)
Anything else exits 3. Text output (an audit's lines) is never parsed: ask the producer for JSON.

Without --write it prints only the partial record, so it can be read first or piped on:
`registry.py ingest --json frames.json | registry.py record --kind frames`. With --write it is
handed to `registry.py record`, which hashes the files, validates and appends; its rules and
output are record's. Paths become relative to --root; a file outside it is refused (exit 2), an
input outside it is dropped with a warning in the record. --kind --class --source --license
--status --art-version --link --id --note set those fields, as on `record`, and the
printed partial carries them too.

registry.py imports this module and calls register(); running this file passes its arguments to
`registry.py ingest` (`registry_ingest.py selftest` runs the ingest cases alone).
Exit codes: 0 green, 2 refused (record's refusals, a path outside --root, several images),
3 not JSON (NaN and Infinity are not), not an object, a shape ingest does not read, an error
output, nothing that names a file.
Standard library only.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry_ledger as L  # noqa: E402
from registry_adopt import guess_kind  # noqa: E402

FLAGS = (("kind", "kind"), ("class_", "class"), ("source", "source"), ("license", "license"),
         ("status", "status"), ("id", "id"), ("note", "note"))


class Bad(Exception):
    """The input is not something ingest reads (exit 3)."""


class Refused(Exception):
    """The input is read, but it cannot become a record as it stands (exit 2)."""


def _strings(value):
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


# ---------------------------------------------------------------------------------- shapes


def _frames(doc, src):
    base = os.path.dirname(src) if src else os.getcwd()
    files = [{"path": src, "role": "derived"}] if src else []
    for frame in doc.get("frames") or []:
        if isinstance(frame, dict) and isinstance(frame.get("file"), str):
            files.append({"path": os.path.join(base, frame["file"]), "role": "derived"})
    tool = {"skill": "codex-visual", "script": "sheet_to_frames.py"}
    producer = doc.get("producer")
    if producer is not None:
        if not (isinstance(producer, dict) and isinstance(producer.get("skill"), str)
                and isinstance(producer.get("script"), str)):
            raise Bad("`producer` is not an object with string `skill` and `script`")
        tool = {"skill": producer["skill"], "script": producer["script"]}
    part = {"kind": "frames", "source": "generated", "files": files, "tool": tool}
    origin = doc.get("source")
    if isinstance(origin, dict):
        origin = origin.get("file")
    if isinstance(doc.get("sheet"), str):
        part["inputs"] = [{"path": doc["sheet"]}]
    elif isinstance(origin, str):
        part["inputs"] = [{"path": origin}]
    verdict = doc.get("verdict")
    if isinstance(verdict, dict) and isinstance(verdict.get("ok"), bool):
        faults = [f for f in verdict.get("faults") or [] if isinstance(f, dict)]
        part["gates"] = [{"name": "frames.faults", "value": len(faults), "limit": 0,
                          "pass": verdict["ok"]}]
        part["verdict"] = "green" if verdict["ok"] else "failed"
        kinds = sorted({str(f.get("kind")) for f in faults})
        if kinds:
            part["note"] = "faults: " + ", ".join(kinds)
    params = {k: doc[k] for k in ("rows", "cols", "fps_hint", "align") if k in doc}
    if params:
        part["params"] = params
    return part


def _blender(doc, src):
    gates = [g for g in doc.get("gates") or [] if isinstance(g, dict)]
    ok = doc["ok"] if isinstance(doc.get("ok"), bool) else all(g.get("pass") is True for g in gates)
    part = {"source": "authored", "gates": gates, "verdict": "green" if ok else "failed"}
    if _strings(doc.get("warnings")):
        part["warnings"] = _strings(doc["warnings"])
    return part


def _codex(doc, src):
    images = doc.get("images") if isinstance(doc.get("images"), list) else []
    count = doc["new_images"] if isinstance(doc.get("new_images"), int) else max(len(images), 1)
    if count > 1:
        raise Refused(f"the call made {count} images and none was chosen; record the one meant "
                      "with `registry.py record`")
    if not isinstance(doc.get("out"), str):
        raise Bad("codex_generate output without an `out` path")
    first = {"path": doc["out"]}
    if isinstance(doc.get("out_sha256"), str):
        first["sha256"] = doc["out_sha256"]          # record keeps the file's own and warns
    part = {"source": "generated", "files": [first],
            "tool": {"skill": "codex-visual", "script": "codex_generate.py"}}
    params = {k: doc[k] for k in ("model", "seed", "prompt_sha256", "prompt_file")
              if doc.get(k) is not None}
    if params:
        part["params"] = params
    if isinstance(doc.get("inputs"), list):
        part["inputs"] = doc["inputs"]
    gates = []
    if isinstance(doc.get("expect_size"), list):
        ok = images[0].get("size_ok") if images and isinstance(images[0], dict) else None
        if not isinstance(ok, bool):
            ok = doc.get("size") == doc["expect_size"]
        gates.append({"name": "codex.size", "value": doc.get("size"),
                      "limit": doc["expect_size"], "pass": ok})
        part["gates"] = gates
    part["verdict"] = "failed" if any(not g["pass"] for g in gates) else "green"
    if doc.get("alpha") is True:
        part["warnings"] = ["rendered with alpha: the agent keyed it; ask for an opaque render"]
    return part


SHAPES = {"frames": _frames, "blender": _blender, "codex": _codex}


def legacy_shape(doc):
    """Which shape a producer's output has, setting its `record` key aside; None for none."""
    if doc.get("tool") == "sheet_to_frames.py" or (
            isinstance(doc.get("frames"), list) and "cell" in doc and "verdict" in doc):
        return "frames"
    if isinstance(doc.get("producer"), dict) and isinstance(doc.get("frames"), list):
        return "frames"
    if "gates" in doc and "blender" in doc:
        return "blender"
    if "out" in doc and "size" in doc:
        return "codex"
    return None


# ------------------------------------------------------------------------------ converting


def _norm(ctx, p):
    try:
        return ctx.norm(p)
    except ValueError as e:
        raise Refused(f"{p}: {e}") from None


def convert(doc, src, ctx, args):
    """The partial record a producer's JSON stands for: paths relative to --root, the flags
    applied. Raises Bad or Refused."""
    shape = legacy_shape(doc)
    if "record" in doc:
        if not isinstance(doc["record"], dict):
            raise Bad("`record` is not an object")
        part = copy.deepcopy(doc["record"])
        base = {}
        if shape:
            try:
                base = SHAPES[shape](doc, src)
            except Bad:
                base = {}
        for k, v in base.items():
            part.setdefault(k, v)
    elif shape:
        part = SHAPES[shape](doc, src)
    elif "error" in doc:
        raise Bad("the producer reported an error and wrote nothing to record")
    else:
        raise Bad("not a shape ingest reads: a JSON with a `record` object, frames.json from "
                  "sheet_to_frames.py or with a `producer`, a Blender report (gates, blender), or codex_generate "
                  "output (out, size)")
    for k in ("schema", "rev", "ts"):
        part.pop(k, None)

    raw = part.get("files")
    raw = [raw] if isinstance(raw, (str, dict)) else raw if isinstance(raw, list) else []
    files = [{"path": f} if isinstance(f, str) else dict(f) for f in raw
             if isinstance(f, (str, dict))]
    for p in args.file or []:
        files.append({"path": p})
    state = part.get("file") if isinstance(part.get("file"), dict) else \
        doc.get("file") if isinstance(doc.get("file"), dict) else None
    if not files and isinstance(doc.get("path"), str) and doc["path"]:
        files = [{"path": doc["path"]}]                       # a Blender export's file
    if not files and state and isinstance(state.get("path"), str) and state["path"]:
        files = [{"path": state["path"], "role": "source", "mutable": True}]   # the .blend
    if not files:
        raise Bad("it names no file the producer wrote: pass --file PATH")
    unique = {}
    for f in files:
        f["path"] = _norm(ctx, f.get("path"))
        unique.setdefault(f["path"], f)              # a path given twice is listed once
    files = list(unique.values())
    part["files"] = files

    if "inputs" in part and part["inputs"] is not None:
        raw = part["inputs"] if isinstance(part["inputs"], list) else [part["inputs"]]
        kept, outside = [], []
        for f in raw:
            f = {"path": f} if isinstance(f, str) else dict(f) if isinstance(f, dict) else None
            if f is None:
                continue
            try:
                f["path"] = ctx.norm(f.get("path"))
                kept.append(f)
            except ValueError:
                outside.append(os.path.basename(str(f.get("path"))))
        part["inputs"] = kept
        if not kept:
            part.pop("inputs")
        if outside:
            part["warnings"] = _strings(part.get("warnings")) + \
                ["inputs outside --root, not pinned: " + ", ".join(outside)]
    if state is not None:
        state = dict(state)
        if isinstance(state.get("path"), str) and state["path"]:
            try:
                state["path"] = ctx.norm(state["path"])
            except ValueError:
                state["path"] = os.path.basename(state["path"])
        part["file"] = state

    for attr, key in FLAGS:
        if getattr(args, attr, None) is not None:
            part[key] = getattr(args, attr)
    if not part.get("kind"):
        part["kind"] = guess_kind(files[0]["path"]) or "other"
    return L.canonical(part)


# ------------------------------------------------------------------------------------ command


def cmd_ingest(ctx, args, rep):
    R = sys.modules[type(ctx).__module__]
    doc, label = R._read_input(args, rep)
    if doc is None:
        rep.summary("ERROR", label, "nothing ingested")
        return R.HARNESS
    src = None if label == "stdin" else os.path.abspath(label)
    try:
        part = convert(doc, src, ctx, args)
    except Bad as e:
        rep.error(label, "shape", str(e))
        rep.summary("ERROR", label, "nothing ingested")
        return R.HARNESS
    except Refused as e:
        rep.error(label, "refused", str(e))
        rep.summary("ERROR", label, "nothing ingested")
        return R.FAILED
    if not args.write:
        # the printed partial carries --link and --art-version too, so a pipe into `record`
        # needs no flag twice (with --write, record applies them)
        extra = R._link_flags(getattr(args, "link", None), rep)
        if extra is None:
            rep.summary("ERROR", label, "nothing ingested")
            return R.HARNESS
        if getattr(args, "art_version", None) is not None:
            extra.append({"rel": "made-under", "to": L.ART_DIRECTION, "rev": args.art_version})
        if extra:
            links = list(part["links"]) if isinstance(part.get("links"), list) else []
            for link in extra:
                R._set_link(links, link)
            part["links"] = links
            part = L.canonical(part)
        rep.rows.append(json.dumps(part, indent=2, ensure_ascii=False))
        return R.OK
    with tempfile.TemporaryDirectory(prefix="registry-ingest-") as tmp:
        given = os.path.join(tmp, os.path.basename(label) if src else "stdin.json")
        with open(given, "w", encoding="utf-8") as fh:
            json.dump(part, fh, ensure_ascii=False)
        record_args = argparse.Namespace(**vars(args))
        record_args.json_in = given
        return R.cmd_record(ctx, record_args, rep)


def register(sub, common, machine, commands):
    """Add the `ingest` subcommand to registry.py's parser and command table. Its --json names
    the input, as on `record`, so it takes no machine-output flag."""
    p = sub.add_parser("ingest", parents=[common],
                       help="a producer's JSON output as a partial record (--write records it)")
    p.add_argument("--json", dest="json_in", metavar="FILE",
                   help="the producer's JSON output (default, or '-': stdin)")
    p.add_argument("--kind", help="a slug (default: from the shape or the path); the vocabulary: "
                   + " ".join(L.KINDS))
    p.add_argument("--class", dest="class_", metavar="CLASS", help="the 3D asset class")
    p.add_argument("--source", help=" ".join(L.SOURCES))
    p.add_argument("--license", help="required for purchased and third-party")
    p.add_argument("--status", help="default candidate; diagnostic for a run made to learn, not "
                   "to ship")
    p.add_argument("--art-version", dest="art_version", type=int,
                   help="the ART_DIRECTION.md Version: a made-under art:direction link")
    p.add_argument("--link", action="append", metavar="REL=TO[@REV]",
                   help="a link, as on record (repeat)")
    p.add_argument("--id", help="default: the id that holds the first file, else its path slugified")
    p.add_argument("--note")
    p.add_argument("--file", action="append", metavar="PATH",
                   help="a file the producer wrote, when its JSON names none (repeat; shipped first)")
    p.add_argument("--write", action="store_true",
                   help="record it through `registry.py record`; without it, print the partial")
    p.set_defaults(allow_dirty=False)
    commands["ingest"] = cmd_ingest


# ------------------------------------------------------------------------------------ selftest


def _registry():
    for name in ("registry", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "cmd_record") and hasattr(mod, "Ctx"):
            return mod
    import registry
    return registry


def selftest(d):
    """The ingest cases; raises AssertionError on the first failure."""
    R = _registry()
    work = os.path.join(d, "ingest")
    root = os.path.join(work, "proj")
    ledger = os.path.join(root, "ArtDirection", "assets.jsonl")

    def put(rel, data=b""):
        full = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(data)
        return full

    def ingest(doc, *flags, name=None):
        src = os.path.join(work, name or f"in-{len(os.listdir(work))}.json")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(doc if isinstance(doc, str) else json.dumps(doc))
        code, out = R._run("ingest", "--root", root, "--ledger", ledger, "--json", src, *flags)
        return code, (json.loads(out) if code == 0 and "--write" not in flags else out)

    anchor = put("ArtDirection/anchors/runner.png", b"runner")
    sheet = put("ArtDirection/sheets/runner_run.png", b"sheet")
    frames_dir = os.path.join(root, "ArtDirection", "frames", "runner_run")
    for k in range(2):
        put(f"ArtDirection/frames/runner_run/run_{k:02d}.png", bytes([k]))
    clip = put("ArtDirection/clips/runner_gatelatchswing.fbx", b"clip")
    blend = put("ArtDirection/sources/Runner.blend", b"blend")

    # codex_generate: one image; a size gate; several images refused
    codex = {"out": anchor, "size": [64, 64], "alpha": False, "original": "/elsewhere/a.png",
             "new_images": 1, "elapsed_seconds": 3.0, "session_id": "s1", "isolated": True,
             "capture": "private", "images": [{"out": anchor, "size": [64, 64], "size_ok": None}]}
    code, part = ingest(codex)
    assert code == 0, part
    assert part["files"] == [{"path": "ArtDirection/anchors/runner.png"}], part
    assert part["kind"] == "ref" and part["source"] == "generated" and part["verdict"] == "green"
    assert part["tool"] == {"skill": "codex-visual", "script": "codex_generate.py"}
    sized = dict(codex, expect_size=[128, 128], images=[{"size": [64, 64], "size_ok": False}])
    code, part = ingest(sized, "--kind", "sprite")
    assert code == 0 and part["kind"] == "sprite" and part["verdict"] == "failed", part
    assert part["gates"][0]["name"] == "codex.size" and part["gates"][0]["pass"] is False
    code, _ = ingest(dict(codex, new_images=2))
    assert code == 2, code

    # sheet_to_frames.py's frames.json: the sidecar, its frames, the sheet as input
    doc = {"tool": "sheet_to_frames.py", "sheet": sheet, "rows": 1, "cols": 2, "cell": [32, 32],
           "fps_hint": 10.0, "verdict": {"ok": True, "faults": []},
           "frames": [{"name": f"run_{k:02d}", "file": f"run_{k:02d}.png"} for k in range(2)]}
    side = os.path.join(frames_dir, "frames.json")
    with open(side, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    code, out = R._run("ingest", "--root", root, "--ledger", ledger, "--json", side)
    part = json.loads(out)
    assert code == 0 and part["kind"] == "frames", out
    assert [f["path"] for f in part["files"]] == [
        "ArtDirection/frames/runner_run/frames.json",
        "ArtDirection/frames/runner_run/run_00.png", "ArtDirection/frames/runner_run/run_01.png"]
    assert part["inputs"] == [{"path": "ArtDirection/sheets/runner_run.png"}], part
    assert part["gates"] == [{"name": "frames.faults", "value": 0, "limit": 0, "pass": True}]
    assert part["tool"] == {"skill": "codex-visual", "script": "sheet_to_frames.py"}, part

    # a frames.json naming its producer: that tool, `source` (a path or {file}) as the input
    for source in (sheet, {"file": sheet, "sha256": "0" * 64, "fps": 24.0}):
        named = {"tool": "video_loop.py", "source": source, "canvas": [32, 32], "loop": True,
                 "producer": {"skill": "sprite-from-video", "script": "video_loop.py"},
                 "verdict": {"ok": False, "faults": [{"kind": "multi-cycle-suspect"}]},
                 "frames": [{"index": k, "file": f"run_{k:02d}.png"} for k in range(2)]}
        with open(side, "w", encoding="utf-8") as fh:
            json.dump(named, fh)
        code, out = R._run("ingest", "--root", root, "--ledger", ledger, "--json", side)
        part = json.loads(out)
        assert code == 0 and part["kind"] == "frames", out
        assert part["tool"] == {"skill": "sprite-from-video", "script": "video_loop.py"}, part
        assert part["inputs"] == [{"path": "ArtDirection/sheets/runner_run.png"}], part
        assert len(part["files"]) == 3 and part["verdict"] == "failed", part
    with open(side, "w", encoding="utf-8") as fh:
        json.dump(dict(named, producer={"skill": "sprite-from-video", "script": 3}), fh)
    code, out = R._run("ingest", "--root", root, "--ledger", ledger, "--json", side)
    assert code == 3 and "`producer`" in out, (code, out)
    with open(side, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)

    # a Blender report: no file named -> 3; --file; a newer report with record and file
    report = {"ok": True, "gates": [{"name": "rig.bones", "value": 24, "limit": 15, "pass": True}],
              "blender": [5, 2, 1]}
    code, _ = ingest(report)
    assert code == 3, code
    code, part = ingest(report, "--file", "ArtDirection/clips/runner_gatelatchswing.fbx")
    assert code == 0 and part["kind"] == "mesh" and part["source"] == "authored", part
    assert part["verdict"] == "green" and part["gates"] == report["gates"]
    newer = dict(report, schema=1, warnings=[],
                 file={"path": blend, "saved": False, "dirty": True},
                 record={"tool": {"skill": "blender-retarget", "script": "brt_retarget"},
                         "params": {"clip": "GateLatchSwing"}, "gates": report["gates"],
                         "verdict": "green"})
    code, part = ingest(newer, "--kind", "rig")
    assert code == 0 and part["kind"] == "rig", part
    assert part["files"] == [{"path": "ArtDirection/sources/Runner.blend", "role": "source",
                              "mutable": True}], part
    assert part["file"] == {"path": "ArtDirection/sources/Runner.blend", "saved": False,
                            "dirty": True}
    assert part["tool"]["skill"] == "blender-retarget" and part["source"] == "authored"

    # any JSON with a record; NaN refused; shapes ingest does not read
    code, part = ingest({"record": {"files": [clip], "kind": "clip", "source": "authored"}})
    assert code == 0 and part["files"] == [{"path": "ArtDirection/clips/runner_gatelatchswing.fbx"}]
    code, part = ingest({"record": {"files": [clip], "kind": "clip", "source": "authored"}},
                        "--art-version", "3", "--link", "made-by=job:courier-17")
    assert code == 0 and part["links"] == [{"rel": "made-by", "to": "job:courier-17"},
                                           {"rel": "made-under", "to": "art:direction",
                                            "rev": 3}], part
    code, out = ingest('{"record": {"files": ["x.png"], "gates": [{"name": "g", "value": NaN, '
                       '"pass": true}]}}')
    assert code == 3 and "NaN is not JSON" in out, (code, out)
    for bad, why in (({"lines": ["OK x"]}, "shape: not a shape ingest reads"),
                     ("[1, 2]", "input: not a JSON object"), ("not json", "input: not JSON"),
                     ({"error": "codex is not on PATH"}, "shape: the producer reported an error"),
                     ({"record": "x"}, "shape: `record` is not an object")):
        code, out = ingest(bad)
        assert code == 3 and why in out, (bad, code, out)
    code, _ = ingest(dict(codex, out="/elsewhere/a.png"))
    assert code == 2, code

    # --write goes through record: hashed, validated, numbered; nothing printed as a partial
    assert not os.path.exists(ledger)
    code, out = ingest(codex, "--write")
    assert code == 0 and "recorded artdirection/anchors/runner rev 1 (candidate)" in out, out
    code, out = R._run("ingest", "--root", root, "--ledger", ledger, "--json", side, "--write")
    assert code == 0, out
    recs = L.load(ledger)
    assert len(recs) == 2 and all(L.validate(r) == [] for r in recs), recs
    assert recs[0]["files"][0]["sha256"] == L.sha256_file(anchor)
    assert recs[1]["inputs"][0]["sha256"] == L.sha256_file(sheet)
    code, text = R._run("check", "--root", root, "--ledger", ledger, "--json")
    assert code == 0, text

    # a Blender report written as a diagnostic run: the saved .blend and file state both hashed
    code, out = ingest(dict(newer, file={"path": blend, "saved": True, "dirty": False}),
                       "--kind", "rig", "--status", "diagnostic", "--art-version", "2", "--write")
    assert code == 0 and "(diagnostic)" in out, out
    rec = L.load(ledger)[-1]
    assert rec["files"][0]["sha256"] == L.sha256_file(blend) and rec["files"][0]["mutable"], rec
    assert rec["file"]["sha256"] == L.sha256_file(blend), rec["file"]
    assert rec["links"] == [{"rel": "made-under", "to": "art:direction", "rev": 2}], rec


def _main(argv):
    if argv in (["selftest"], ["--selftest"]):
        with tempfile.TemporaryDirectory(prefix="registry-ingest-") as d:
            try:
                selftest(d)
            except Exception as e:                      # a failed assert, or anything it raised
                print(f"ERROR selftest: ingest: {e.__class__.__name__}: {e}")
                return 2
        print("OK selftest: ingest")
        return 0
    return _registry().main(["ingest", *argv])


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
