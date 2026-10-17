#!/usr/bin/env python3
"""registry.py — the project's art-asset ledger: record, check, set a status, list stale, render.

One append-only JSONL ledger per project, `ArtDirection/assets.jsonl` unless `--ledger PATH` or
`ART_LEDGER` names another, with a record for every 2D and 3D asset: its files and their sha256,
where it came from (tool, params, inputs, parents, links), its gates and verdict, and its status.
The ledger is the truth. `ArtDirection/manifest.md` stays prose that people write: nothing here
rewrites it, and `render` only prints rows to paste. Fields and rules: `reference/ledger-schema.md`;
the day-to-day loop: `reference/workflow.md`.

Commands
  init                          create the empty ledger; warn when git ignores it
  record [--json FILE]          append a record built from a partial record (FILE, or stdin) and
                                --kind --class --source --license --status --id --art-version
                                --link REL=TO --note
  check [--strict]              every rule in reference/ledger-schema.md, then orphans under
                                ArtDirection/ (count and up to 20 examples)
  stale [--art-version N] [--at NS:KEY=N]
                                current candidate or approved records with a link behind the
                                current value: an upstream asset with newer content, or a
                                version given here
  status ID STATE [--by ID] [--allow-dirty] [--approver NAME] [--evidence ID] [--note TEXT]
                                append the status change; `approved` is refused when the record
                                would fail check, `superseded --by` when the successor is unknown,
                                not live, or would close a cycle
  history ID                    every revision, the current version (latest approved) and the
                                previous good one
  mv ID NEWPATH [--file OLD]    append the same id at its new path, hashed again
  render                        Markdown rows for manifest.md, printed, never written
  adopt --dry-run | --write     read manifest.md once into records (registry_adopt.py)
  ingest --json FILE [--write]  a producer's JSON output as a record (registry_ingest.py)
  selftest                      every case in a temporary directory (registry_selftest.py)

Every command takes --root DIR (the project root; default: the current directory) and --ledger
PATH. Every command but `record` and `ingest` takes --json, which prints one JSON object instead
of lines; on those two, --json names the input. Relative --ledger and ART_LEDGER paths are read
against the current directory; ledger paths are relative to --root.

Output: one line per finding, `ERROR <path>: <rule>: <message>`, `WARN …` or `OK …`, then one
summary line; `render` prints only its rows. Nothing else is printed.

Exit codes
  0  green: nothing failed (warnings allowed)
  2  failed: a check rule failed, or a write was refused: a schema break, a path outside --root,
     an id or a file another id holds, a cycle, an unresolved parent or link, a failed verdict or
     gate, an unsaved Blender file, a changed or missing file
  3  harness: no ledger, a corrupt line in the middle of the ledger, the ledger changed under a
     write, input that is not a JSON object, bad arguments, an unknown id

Examples, from the project root
  registry.py init
  registry.py record --json runner_run.record.json --kind sheet --source generated --art-version 2
  registry.py check
  registry.py status artdirection/sheets/runner-run approved --approver lead --evidence artdirection/qa/runner-run
  registry.py stale --art-version 3
  registry.py mv assets/models/heroprop/mallet/mallet Assets/Models/HeroProp/Mallet/Mallet_LOD0.glb
  registry.py render

Standard library only.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry_ledger as L  # noqa: E402
import registry_adopt, registry_ingest  # noqa: E402,E401

ART_DIR = "ArtDirection"
DEFAULT_LEDGER = ART_DIR + "/assets.jsonl"
MANIFEST = ART_DIR + "/manifest.md"
ORPHAN_SKIP_TOP = ("raw",)          # ArtDirection/raw/: git-ignored originals, not scanned for orphans
ORPHAN_EXAMPLES = 20
OK, FAILED, HARNESS = 0, 2, 3
VERDICT = {OK: "green", FAILED: "failed", HARNESS: "harness"}
LIVE = ("candidate", "approved")


class Usage(argparse.ArgumentParser):
    """argparse exits 2 on a usage error, which here means "check failed". Make it 3."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(HARNESS)


# -------------------------------------------------------------------------------------- output


class Report:
    def __init__(self):
        self.items = []          # {level, rule, path, msg[, id, rev]}
        self.rows = []           # render's Markdown rows
        self.data = {}           # extra keys for --json
        self.final = None        # (level, path, msg)

    def add(self, level, path, rule, msg, ident=None, rev=None):
        item = {"level": level, "rule": rule, "path": path, "msg": msg}
        if ident is not None:
            item["id"] = ident
        if rev is not None:
            item["rev"] = rev
        self.items.append(item)

    def error(self, path, rule, msg, ident=None, rev=None):
        self.add("ERROR", path, rule, msg, ident, rev)

    def warn(self, path, rule, msg, ident=None, rev=None):
        self.add("WARN", path, rule, msg, ident, rev)

    def ok(self, path, msg, ident=None, rev=None):
        self.add("OK", path, None, msg, ident, rev)

    def count(self, level):
        return sum(1 for i in self.items if i["level"] == level)

    def summary(self, level, path, msg):
        self.final = (level, path, msg)

    def emit(self, command, code, as_json):
        if as_json:
            out = {"command": command, "exit": code, "verdict": VERDICT.get(code, "harness")}
            out.update(self.data)
            out["errors"], out["warnings"] = self.count("ERROR"), self.count("WARN")
            out["items"] = self.items
            if self.final:
                out["summary"] = f"{self.final[0]} {self.final[1]}: {self.final[2]}"
            print(json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False))
            return
        for row in self.rows:
            print(row)
        for i in self.items:
            head = f"{i['level']} {i['path']}: " + (f"{i['rule']}: " if i["rule"] else "")
            tail = ""
            if "id" in i:
                tail = f" (id {i['id']}" + (f" rev {i['rev']})" if "rev" in i else ")")
            print(head + i["msg"] + tail)
        if self.final:
            print(f"{self.final[0]} {self.final[1]}: {self.final[2]}")


# ------------------------------------------------------------------------------------- context


class Git:
    """The few git questions the rules ask. None from a query means git could not answer."""

    def __init__(self, root):
        self.root = root
        self.why = ""
        self._ok = None

    def _run(self, args, cwd=None, stdin=None, literal=False):
        # Literal pathspecs keep a `[` or `*` in a file name from matching other files; only
        # ls-files takes pathspecs, and check-ignore refuses the flag.
        head = ["git", "--literal-pathspecs"] if literal else ["git"]
        try:
            return subprocess.run(head + ["-C", cwd or self.root] + args,
                                  input=stdin, capture_output=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as e:
            self.why = f"git did not run ({e.__class__.__name__})"
            return None

    def _fail(self, r):
        if r is not None:
            lines = r.stderr.decode("utf-8", "replace").strip().splitlines()
            self.why = lines[0] if lines else f"git exited {r.returncode}"

    def ok(self):
        if self._ok is None:
            r = self._run(["rev-parse", "--is-inside-work-tree"])
            self._ok = bool(r is not None and r.returncode == 0 and r.stdout.strip() == b"true")
            if r is not None and not self._ok:
                self.why = "not inside a git work tree"
        return self._ok

    def ignored(self, paths, cwd=None):
        """The subset of `paths` git ignores. A tracked file is never in it."""
        if not paths:
            return set()
        r = self._run(["check-ignore", "-z", "--stdin"], cwd,
                      b"".join(p.encode("utf-8") + b"\0" for p in paths))
        if r is None or r.returncode not in (0, 1):
            self._fail(r)
            return None
        return {p.decode("utf-8") for p in r.stdout.split(b"\0") if p}

    def tracked(self, paths):
        """The subset of `paths` in git's index."""
        out = set()
        for i in range(0, len(paths), 200):
            r = self._run(["-c", "core.quotepath=off", "ls-files", "-z", "--"]
                          + list(paths[i:i + 200]), literal=True)
            if r is None or r.returncode != 0:
                self._fail(r)
                return None
            out.update(p.decode("utf-8") for p in r.stdout.split(b"\0") if p)
        return out

    def ignores_file(self, full):
        """Whether git ignores the file at absolute path `full`; None outside a work tree."""
        here = os.path.dirname(full)
        while not os.path.isdir(here):
            here = os.path.dirname(here)
        r = self._run(["rev-parse", "--is-inside-work-tree"], here)
        if r is None or r.stdout.strip() != b"true":
            return None
        rel = os.path.relpath(full, here).replace(os.sep, "/")
        got = self.ignored([rel], here)
        return None if got is None else rel in got


class Ctx:
    def __init__(self, args):
        self.root_disp = getattr(args, "root", None) or os.curdir
        self.root = os.path.abspath(self.root_disp)
        ledger = (getattr(args, "ledger", None) or os.environ.get("ART_LEDGER")
                  or os.path.join(self.root, *DEFAULT_LEDGER.split("/")))
        self.ledger = os.path.abspath(ledger)
        try:
            self.disp = L.rel_posix(self.ledger, self.root)
        except ValueError:
            self.disp = self.ledger
        self.git = Git(self.root)

    def full(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def norm(self, p):
        """A path as given (relative to --root, or absolute inside it) -> its ledger form: NFC,
        unless only the form as given exists on disk."""
        if not isinstance(p, str) or not p.strip():
            raise ValueError("an empty path")
        q = p.replace("\\", "/")
        try:
            rel = L.rel_posix(q if os.path.isabs(q) else os.path.join(self.root, q), self.root)
        except ValueError:
            raise ValueError("is outside the project root (--root), or is the root itself") from None
        why = L.path_problem(rel)
        if why:
            raise ValueError(f"{rel} {why}")
        nfc = unicodedata.normalize("NFC", rel)
        if nfc != rel and not os.path.exists(self.full(nfc)) and os.path.exists(self.full(rel)):
            return rel
        return nfc


class Facts:
    """What git said about the paths the rules need: None means it was not asked or could not say."""

    def __init__(self, ignored=None, tracked=None):
        self.ignored, self.tracked = ignored, tracked


def read_ledger(ctx, rep, must_exist=True):
    """(lines, ok): (line number, record) pairs; ok is False when the ledger is missing (and
    must_exist) or holds a corrupt line before its last. A torn last line is a warning."""
    if not os.path.exists(ctx.ledger):
        if must_exist:
            rep.error(ctx.disp, "no-ledger",
                      "no ledger here; run `registry.py init`, or pass --ledger / set ART_LEDGER")
            return [], False
        return [], True
    if not os.path.isfile(ctx.ledger):
        rep.error(ctx.disp, "no-ledger", "exists but is not a file")
        return [], False
    problems, torn = [], []
    lines = L.load_lines(ctx.ledger, problems, torn)
    for p in problems:
        n, _, msg = p[len(ctx.ledger) + 1:].partition(": ")
        rep.error(f"{ctx.disp}:{n}", "corrupt-line", msg)
    for p in torn:
        n, _, msg = p[len(ctx.ledger) + 1:].partition(": ")
        rep.warn(f"{ctx.disp}:{n}", "torn-line", f"{msg}: a writer died mid-line, or is still "
                 "writing; skipped, and the next write moves it to "
                 f"{os.path.basename(ctx.ledger)}.torn")
    return lines, not problems


def append(ctx, rep, rec, **kw):
    """L.append, reporting a torn line it moved aside."""
    notes = []
    written = L.append(ctx.ledger, rec, notes=notes, **kw)
    for n in notes:
        rep.warn(ctx.disp, "torn-line", n)
    return written


def files_of(rec):
    """The record's file entries whose path is a valid ledger path (the others fail validation)."""
    files = rec.get("files")
    if not isinstance(files, list):
        return []
    return [f for f in files if isinstance(f, dict) and L.path_problem(f.get("path")) is None]


def where(ctx, rec, line=None):
    files = files_of(rec)
    if files:
        return files[0]["path"]
    return f"{ctx.disp}:{line}" if line else ctx.disp


def _id(rec):
    return rec.get("id") if isinstance(rec.get("id"), str) else None


def _rev(rec):
    return rec.get("rev") if L._is_int(rec.get("rev")) else None


def made_under(rec):
    """The ART_DIRECTION.md Version a record's `made-under art:direction` link names, or None."""
    for link in rec.get("links") or []:
        if isinstance(link, dict) and link.get("rel") == "made-under" \
                and link.get("to") == L.ART_DIRECTION and L._is_int(link.get("rev")):
            return link["rev"]
    return None


def successor_chain(current, ident):
    """The ids `ident` was superseded by, in order, stopping at a repeat."""
    out, seen = [], {ident}
    nxt = current.get(ident, {}).get("superseded_by")
    while isinstance(nxt, str) and nxt not in seen:
        out.append(nxt)
        seen.add(nxt)
        nxt = current.get(nxt, {}).get("superseded_by")
    return out


def owners_of(current):
    """NFC path -> the ids whose current record names it."""
    out = {}
    for ident, rec in current.items():
        for f in files_of(rec):
            out.setdefault(L.path_key(f["path"]), []).append(ident)
    return out


def rival_owners(current, ids):
    """The ids among `ids` that are not replaced by another of them: two or more is a dual owner."""
    return sorted(i for i in ids if not set(successor_chain(current, i)) & set(ids))


# --------------------------------------------------------------------------------------- rules


def gather_facts(ctx, rep, recs, approving=False):
    """Ask git once for every path the rules below need: vendor files and missing live files
    (ignored?), and purchased or third-party files (tracked?)."""
    vendor, licensed, missing = set(), set(), set()
    for r in recs:
        live = approving or r.get("status") in LIVE
        for f in files_of(r):
            if f.get("vendor") is True:
                vendor.add(f["path"])
            elif r.get("source") in L.LICENSED_SOURCES:
                licensed.add(f["path"])
            if live and not os.path.isfile(ctx.full(f["path"])):
                missing.add(f["path"])
    if not (vendor or licensed or missing):
        return Facts(set(), set())
    if not ctx.git.ok():
        if vendor or licensed:
            rep.warn(ctx.root_disp, "no-git",
                     f"{ctx.git.why}: the vendor and tracked-file rules did not run")
        return Facts()
    ignored = ctx.git.ignored(sorted(vendor | missing))
    tracked = ctx.git.tracked(sorted(licensed)) if licensed else set()
    if ignored is None or tracked is None:
        rep.warn(ctx.root_disp, "git-failed",
                 f"{ctx.git.why}: the vendor and tracked-file rules did not run")
    return Facts(ignored, tracked)


def check_files(ctx, rep, rec, facts, approving=False):
    """Live files: on disk, and the bytes recorded. A mutable file (a working .blend) that changed
    since is a warning: its recorded hash names the version that made this asset."""
    ident, rev = _id(rec), _rev(rec)
    for f in files_of(rec):
        p = f["path"]
        full = ctx.full(p)
        if not os.path.isfile(full):
            if os.path.exists(full):
                rep.error(p, "not-a-file", "exists but is not a file", ident, rev)
            elif approving:
                rep.error(p, "missing", "not on disk; an asset is approved where its files are",
                          ident, rev)
            elif facts.ignored is not None and p in facts.ignored:
                rep.warn(p, "local-only", "git-ignored and not on this machine; its hash is "
                         "checked where it exists", ident, rev)
            elif rec.get("status") == "candidate" and f.get("missing") is True:
                rep.warn(p, "missing", "recorded as missing and still missing", ident, rev)
            else:
                rep.error(p, "missing", "not on disk", ident, rev)
            continue
        if f.get("missing") is True:
            msg = "on disk now but recorded as missing: record it again to pin its hash"
            (rep.error if approving else rep.warn)(p, "recorded-missing", msg, ident, rev)
            continue
        sha = f.get("sha256")
        if not sha:
            rep.warn(p, "no-hash", "no sha256 recorded; only its existence is checked", ident, rev)
            continue
        size = os.path.getsize(full)
        if not ((L._is_int(f.get("bytes")) and f["bytes"] != size) or L.sha256_file(full) != sha):
            continue
        if f.get("mutable") is True:
            rep.warn(p, "moved-on", "the working file changed since this version was recorded; "
                     "the recorded sha256 is the version that made the asset", ident, rev)
        elif rec.get("status") == "approved":
            rep.error(p, "changed-after-approval", "the file changed after it was approved; "
                      "record it again as a candidate, or put the approved bytes back",
                      ident, rev)
        else:
            rep.error(p, "hash-drift", "the file differs from the bytes recorded; record it "
                      "again", ident, rev)


def check_approval(ctx, rep, rec, line=None):
    """An approved record: no failed verdict, no failing gate."""
    ident, rev, at = _id(rec), _rev(rec), where(ctx, rec, line)
    if rec.get("verdict") == "failed":
        rep.error(at, "verdict-failed", "verdict is failed; approve a green run", ident, rev)
    elif rec.get("verdict") == "harness":
        rep.warn(at, "verdict-harness", "verdict is harness: its gates did not run", ident, rev)
    gates = rec.get("gates") if isinstance(rec.get("gates"), list) else []
    failing = [str(g.get("name")) for g in gates if isinstance(g, dict) and g.get("pass") is False]
    if failing:
        rep.error(at, "failing-gate", "failing gate(s): " + ", ".join(failing), ident, rev)


def check_dirty(ctx, rep, rec, allow):
    """Approving output of an unsaved Blender file. Returns True when it was allowed through."""
    state = rec.get("file")
    if not (isinstance(state, dict) and state.get("dirty") is True):
        return False
    at = state.get("path") if isinstance(state.get("path"), str) and state["path"] else where(ctx, rec)
    if allow:
        rep.warn(at, "dirty-file", "approved with --allow-dirty: the file was unsaved when this "
                 "was produced", _id(rec), _rev(rec))
        return True
    rep.error(at, "dirty-file", "the file was unsaved when this was produced; save it, run the "
              "step again and record that, or approve with --allow-dirty", _id(rec), _rev(rec))
    return False


def check_vendor(ctx, rep, rec, facts, strict):
    ident, rev = _id(rec), _rev(rec)
    for f in files_of(rec):
        p = f["path"]
        if f.get("vendor") is True:
            if facts.ignored is not None and p not in facts.ignored:
                rep.error(p, "vendor-not-ignored", "vendor: true, but git does not ignore it (or "
                          "it is tracked); purchased content stays out of the repository",
                          ident, rev)
        elif rec.get("source") in L.LICENSED_SOURCES and facts.tracked is not None \
                and p in facts.tracked:
            (rep.error if strict else rep.warn)(
                p, "licensed-tracked", f"source {rec['source']} and tracked by git; confirm "
                "its licence allows it in the repository", ident, rev)


def check_refs(ctx, rep, rec, known, line=None):
    """parent, superseded_by and links name ids the ledger has (a link may name ns:key)."""
    ident, rev, at = _id(rec), _rev(rec), where(ctx, rec, line)
    parents = rec.get("parent") if isinstance(rec.get("parent"), list) else []
    for p in parents:
        if not isinstance(p, str):
            continue
        if p == ident:
            rep.error(at, "unresolved-parent", f"parent {p} is the record itself", ident, rev)
        elif p not in known:
            rep.error(at, "unresolved-parent", f"parent {p} is not in the ledger", ident, rev)
    by = rec.get("superseded_by")
    if isinstance(by, str):
        if by == ident:
            rep.error(at, "unresolved-superseded-by", "superseded by itself", ident, rev)
        elif by not in known:
            rep.error(at, "unresolved-superseded-by", f"superseded_by {by} is not in the ledger",
                      ident, rev)
    for link in rec.get("links") or []:
        to = link.get("to") if isinstance(link, dict) else None
        if L.is_id(to) and to not in known:
            rep.error(at, "unresolved-link", f"{link.get('rel')} -> {to}: not in the ledger "
                      "(an outside name is written ns:key)", ident, rev)


def check_graph(ctx, rep, current, last_line=None, only=None):
    """Cycles through parent and through superseded_by, and files two ids hold. With `only`,
    just the problems that involve that id. Returns [(rule, [ids])] for what it reported."""
    last_line, found = last_line or {}, []
    for field, rule in (("parent", "parent-cycle"), ("superseded_by", "superseded-cycle")):
        edges = {}
        for ident, rec in current.items():
            val = rec.get(field)
            vals = val if isinstance(val, list) else [val] if isinstance(val, str) else []
            edges[ident] = [v for v in vals if isinstance(v, str) and v != ident]
        for ring in L.cycles(edges):
            if only is not None and only not in ring:
                continue
            head = current[ring[0]]
            found.append((rule, ring))
            rep.error(where(ctx, head, last_line.get(ring[0])), rule,
                      " -> ".join(ring + [ring[0]]) + f": {field} goes round in a circle",
                      ring[0], _rev(head))
    for path, ids in sorted(owners_of(current).items()):
        rivals = rival_owners(current, ids)
        if len(rivals) > 1 and (only is None or only in rivals):
            found.append(("dual-owner", rivals))
            rep.error(path, "dual-owner", "named by the current records of " + ", ".join(rivals)
                      + "; one file belongs to one asset: `status OLD superseded --by NEW`, or "
                      "record the other one without it", only or rivals[0])
    return found


def find_orphans(ctx, records):
    """Files under ArtDirection/ that no record names in files, inputs or params.prompt_file. Skipped: the ledger, manifest.md,
    dot-files, .meta files, the ledger's .torn side file, and ArtDirection/raw/."""
    art = ctx.full(ART_DIR)
    if not os.path.isdir(art):
        return []
    named = {L.path_key(f["path"]) for r in records for f in files_of(r)}
    for r in records:                                # an input or a prompt file is named too
        for f in r.get("inputs") or []:
            if isinstance(f, dict) and isinstance(f.get("path"), str):
                named.add(L.path_key(f["path"]))
        prompt = (r.get("params") or {}).get("prompt_file") if isinstance(r.get("params"), dict) else None
        if isinstance(prompt, str):
            named.add(L.path_key(prompt))
    skip = {os.path.normcase(os.path.abspath(x))
            for x in (ctx.ledger, ctx.ledger + ".torn", ctx.full(MANIFEST))}
    found = []
    for dirpath, dirnames, filenames in os.walk(art):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".")
                             and not (dirpath == art and d in ORPHAN_SKIP_TOP))
        for name in sorted(filenames):
            if name.startswith(".") or name.endswith(".meta"):
                continue
            full = os.path.join(dirpath, name)
            if os.path.normcase(os.path.abspath(full)) in skip:
                continue
            rel = L.rel_posix(full, ctx.root)
            if L.path_key(rel) not in named:
                found.append(rel)
    return found


# ------------------------------------------------------------------------------------ commands


def cmd_init(ctx, args, rep):
    created = False
    if os.path.exists(ctx.ledger):
        lines, ok = read_ledger(ctx, rep)
        if not ok:
            rep.summary("ERROR", ctx.disp, "init stopped: the ledger is there and unreadable")
            return HARNESS
        rep.ok(ctx.disp, f"the ledger exists with {len(lines)} record(s); left as it is")
    else:
        os.makedirs(os.path.dirname(ctx.ledger), exist_ok=True)
        fd = os.open(ctx.ledger, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        os.fsync(fd)
        os.close(fd)
        created = True
        rep.ok(ctx.disp, "created an empty ledger")
    ledger_ignored = ctx.git.ignores_file(ctx.ledger)
    art_ignored = None
    if ctx.git.ok():
        got = ctx.git.ignored([ART_DIR])
        art_ignored = None if got is None else ART_DIR in got
    if ledger_ignored:
        rep.warn(ctx.disp, "git-ignored", "the ledger is git-ignored and would not be versioned; "
                 f"un-ignore it{' (ArtDirection/ is ignored)' if art_ignored else ''}, or keep "
                 "it at a tracked path with --ledger PATH or ART_LEDGER=PATH")
    elif art_ignored:
        rep.warn(ART_DIR + "/", "git-ignored", f"git ignores ArtDirection/, so the files the "
                 f"ledger names are not versioned; the ledger at {ctx.disp} is")
    rep.data.update(ledger=ctx.disp, created=created)
    rep.summary("OK", ctx.disp, "ready")
    return OK


def _read_input(args, rep):
    src = args.json_in
    if src in (None, "-"):
        if src is None and sys.stdin.isatty():
            rep.error("stdin", "usage", "give the partial record with --json FILE, or pipe it in")
            return None, "stdin"
        text, label = sys.stdin.read(), "stdin"
    else:
        label = src
        try:
            with open(src, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as e:
            rep.error(src, "input", f"cannot read it ({e})")
            return None, label
    try:
        part = L.loads(text)
    except ValueError as e:
        rep.error(label, "input", f"not JSON ({e})")
        return None, label
    if not isinstance(part, dict):
        rep.error(label, "input", "not a JSON object")
        return None, label
    return part, label


def _entries(raw, label, what, rep):
    """A list of file entries: a path string becomes {"path": ...}."""
    if isinstance(raw, (str, dict)):
        raw = [raw]
    out = []
    for i, f in enumerate(raw if isinstance(raw, list) else []):
        if isinstance(f, str):
            f = {"path": f}
        if not isinstance(f, dict):
            rep.error(label, "schema", f"{what}[{i}]: neither a path nor an object")
            return None
        out.append(dict(f))
    return out


def _link_flags(values, rep):
    """--link REL=TO[@REV] -> link objects; None after a usage error."""
    out = []
    for v in values or []:
        rel, eq, to = v.partition("=")
        to, at, rev = to.partition("@")
        if not eq or not rel or not to or (at and not rev.isdigit()):
            rep.error("--link", "usage", f"{v!r}: write REL=TO or REL=TO@REV")
            return None
        link = {"rel": rel, "to": to}
        if at:
            link["rev"] = int(rev)
        out.append(link)
    return out


def _set_link(links, link):
    """Replace the link with the same rel and to, or add it."""
    links[:] = [x for x in links if not (isinstance(x, dict) and x.get("rel") == link["rel"]
                                         and x.get("to") == link["to"])] + [link]


def cmd_record(ctx, args, rep):
    part, label = _read_input(args, rep)
    if part is None:
        return HARNESS
    lines, ok = read_ledger(ctx, rep, must_exist=False)
    if not ok:
        rep.summary("ERROR", ctx.disp, "nothing recorded: the ledger is unreadable")
        return HARNESS
    records = [r for _, r in lines]
    current = L.last_by_id(records)

    rec = {k: v for k, v in part.items() if k not in ("schema", "rev", "ts")}
    for attr, key in (("kind", "kind"), ("class_", "class"), ("source", "source"),
                      ("license", "license"), ("status", "status"), ("id", "id"),
                      ("note", "note")):
        if getattr(args, attr, None) is not None:
            rec[key] = getattr(args, attr)
    if "art_version" in rec:
        rep.error(label, "schema", "art_version: written as a link, "
                  "{\"rel\": \"made-under\", \"to\": \"art:direction\", \"rev\": N}, "
                  "or --art-version N")
        return FAILED
    extra = _link_flags(getattr(args, "link", None), rep)
    if extra is None:
        return HARNESS
    if getattr(args, "art_version", None) is not None:
        extra.append({"rel": "made-under", "to": L.ART_DIRECTION, "rev": args.art_version})
    if extra:
        links = list(rec["links"]) if isinstance(rec.get("links"), list) else []
        for link in extra:
            _set_link(links, link)
        rec["links"] = links

    files = _entries(rec.get("files"), label, "files", rep)
    if files is None:
        return FAILED
    if not files:
        hint = ("; this looks like a producer's whole output: `registry.py ingest` reads it"
                if isinstance(part.get("record"), dict) else "")
        rep.error(label, "schema", "files: needs at least one entry" + hint)
        return FAILED
    bad = False
    for f in files:
        try:
            f["path"] = ctx.norm(f.get("path"))
        except ValueError as e:
            rep.error(str(f.get("path")), "path", str(e))
            bad = True
            continue
        full = ctx.full(f["path"])
        if os.path.isfile(full):
            sha = L.sha256_file(full)
            if f.get("sha256") not in (None, sha):
                rep.warn(f["path"], "sha256-replaced", "the sha256 given is not the file's; the "
                         "file's is recorded")
            f["sha256"], f["bytes"] = sha, os.path.getsize(full)
            f.pop("missing", None)
        else:
            f["missing"] = True
            rep.warn(f["path"], "missing", "not on disk; recorded with missing: true")
    if "inputs" in rec and rec["inputs"] is not None:
        inputs = _entries(rec["inputs"], label, "inputs", rep)
        if inputs is None:
            return FAILED
        for f in inputs:
            try:
                f["path"] = ctx.norm(f.get("path"))
            except ValueError as e:
                rep.error(str(f.get("path")), "path", f"input: {e}")
                bad = True
                continue
            full = ctx.full(f["path"])
            if f.get("sha256") is None:
                if os.path.isfile(full):
                    f["sha256"] = L.sha256_file(full)
                else:
                    rep.warn(f["path"], "input-missing", "input not on disk; no sha256 pinned")
        rec["inputs"] = inputs
    state = rec.get("file")
    if isinstance(state, dict) and isinstance(state.get("path"), str) and state["path"]:
        state = rec["file"] = dict(state)
        try:
            state["path"] = ctx.norm(state["path"])
            full = ctx.full(state["path"])
            if state.get("sha256") is None and os.path.isfile(full):
                state["sha256"], state["bytes"] = L.sha256_file(full), os.path.getsize(full)
        except ValueError:                           # outside --root: no machine path in the ledger
            state["path"] = os.path.basename(state["path"].replace("\\", "/"))
            rep.warn(state["path"], "file-outside-root", "file outside --root: kept by name only, "
                     "unhashed")
    if bad:
        rep.summary("ERROR", label, "nothing recorded")
        return FAILED
    rec["files"] = files
    at = files[0]["path"]

    owners = owners_of(current)
    explicit = rec.get("id") is not None
    if not explicit:
        held = owners.get(L.path_key(at), [])
        if len(held) == 1:
            rec["id"] = held[0]                       # the same file again: a new revision
        else:
            try:
                rec["id"] = L.slugify(at)
            except ValueError as e:
                rep.error(at, "id", str(e))
                return FAILED
    ident = rec["id"]
    prev = current.get(ident) if isinstance(ident, str) else None
    if prev is not None:
        before = {L.path_key(f["path"]) for f in files_of(prev)}
        if not explicit and not before & {L.path_key(f["path"]) for f in files}:
            rep.error(at, "id-taken", f"id {ident} already names {sorted(before)[0] if before else 'other files'}; "
                      f"--id {ident} adds a revision of that asset, another --id makes a new one")
            rep.summary("ERROR", at, "nothing recorded")
            return FAILED
        for k in ("kind", "class", "source", "license"):
            if rec.get(k) is None and prev.get(k) is not None:
                rec[k] = prev[k]
    if rec.get("status") is None:
        rec["status"] = "candidate"
    rec["schema"] = L.SCHEMA
    rec["ts"] = L.now_utc()
    rec["rev"] = L.last_rev(records, ident) + 1 if isinstance(ident, str) else 1

    for link in rec.get("links") or []:
        if isinstance(link, dict) and L.is_id(link.get("to")) and link.get("rev") is None \
                and link["to"] in current:
            link["rev"] = L.content_rev(records, link["to"])
    for e in L.validate(rec):
        rep.error(at, "schema", e, _id(rec))
    known = {r["id"] for r in records if isinstance(r.get("id"), str)} | {_id(rec)}
    check_refs(ctx, rep, rec, known)
    if isinstance(ident, str) and not rep.count("ERROR"):
        # only the problems this record brings; an old cycle or a file held twice is check's
        check_graph(ctx, rep, dict(current, **{ident: rec}), only=ident)
    allowed_dirty = False
    if rec.get("status") == "approved":
        facts = gather_facts(ctx, rep, [rec], approving=True)
        check_files(ctx, rep, rec, facts, approving=True)
        check_approval(ctx, rep, rec)
        check_vendor(ctx, rep, rec, facts, strict=False)
        allowed_dirty = check_dirty(ctx, rep, rec, args.allow_dirty)
    if rep.count("ERROR"):
        rep.summary("ERROR", at, "nothing recorded")
        return FAILED
    if allowed_dirty:
        rec["warnings"] = list(rec.get("warnings") or []) + ["approved while file.dirty was true"]
    os.makedirs(os.path.dirname(ctx.ledger), exist_ok=True)
    written = append(ctx, rep, rec, assign_rev=True)
    rep.data["record"] = L.canonical(written)
    rep.summary("OK", at, f"recorded {ident} rev {written['rev']} ({written['status']})")
    return OK


def cmd_check(ctx, args, rep):
    lines, ok = read_ledger(ctx, rep)
    if not ok and not lines and not os.path.isfile(ctx.ledger):
        rep.summary("ERROR", ctx.disp, "check harness: no ledger")
        return HARNESS
    records = [r for _, r in lines]
    known = {r["id"] for r in records if isinstance(r.get("id"), str)}
    last_line, seq = {}, {}
    for n, rec in lines:
        ident, rev = _id(rec), _rev(rec)
        if ident is None:
            continue
        last_line[ident] = n
        if rev is not None:
            want = seq.get(ident, 0) + 1
            if rev != want:
                rep.error(f"{ctx.disp}:{n}", "rev-gap", f"rev {rev} where rev {want} comes next",
                          ident, rev)
            seq[ident] = max(seq.get(ident, 0), rev)
    current_lines = set(last_line.values())
    live = [rec for n, rec in lines if n in current_lines]
    facts = gather_facts(ctx, rep, live)
    for n, rec in lines:
        for e in L.validate(rec, args.strict):
            rep.error(f"{ctx.disp}:{n}", "schema", e, _id(rec), _rev(rec))
        if n not in current_lines:
            continue
        if args.strict:
            for note in L.vocabulary_notes(rec):
                rep.warn(f"{ctx.disp}:{n}", "vocabulary", note, _id(rec), _rev(rec))
        if rec.get("status") in LIVE:
            check_files(ctx, rep, rec, facts)
        if rec.get("status") == "approved":
            check_approval(ctx, rep, rec, n)
        check_vendor(ctx, rep, rec, facts, args.strict)
        check_refs(ctx, rep, rec, known, n)
    check_graph(ctx, rep, L.last_by_id(records), last_line)
    orphans = find_orphans(ctx, records)
    if orphans:
        rep.warn(ART_DIR + "/", "orphans", f"{len(orphans)} file(s) under ArtDirection/ are in "
                 f"no record" + (f"; the first {ORPHAN_EXAMPLES} follow" if len(orphans) >
                                 ORPHAN_EXAMPLES else ""))
        for p in orphans[:ORPHAN_EXAMPLES]:
            rep.warn(p, "orphan", "in no record")
    rep.data.update(ledger=ctx.disp, lines=len(lines), ids=len(last_line),
                    orphans={"count": len(orphans), "examples": orphans[:ORPHAN_EXAMPLES]})
    errors, warnings = rep.count("ERROR"), rep.count("WARN")
    bad_lines = sum(1 for i in rep.items if i["rule"] == "corrupt-line")
    if not ok:
        rep.summary("ERROR", ctx.disp, f"check harness: {bad_lines} line(s) are not records; the "
                    f"rules ran on the {len(lines)} that are")
        return HARNESS
    if errors:
        rep.summary("ERROR", ctx.disp, f"check failed: {errors} error(s), {warnings} warning(s) "
                    f"over {len(last_line)} id(s)")
        return FAILED
    rep.summary("OK", ctx.disp, f"check green: {len(lines)} line(s), {len(last_line)} id(s), "
                f"{warnings} warning(s)")
    return OK


def _at_flags(values, rep):
    """--at NS:KEY=N -> {ns:key: N}; None after a usage error."""
    out = {}
    for v in values or []:
        key, eq, n = v.rpartition("=")
        if not eq or not L.NS_KEY_RE.match(key) or not n.isdigit():
            rep.error("--at", "usage", f"{v!r}: write NS:KEY=N, e.g. art:direction=3")
            return None
        out[key] = int(n)
    return out


def cmd_stale(ctx, args, rep):
    at = _at_flags(args.at, rep)
    if at is None:
        rep.summary("ERROR", "--at", "nothing listed")
        return HARNESS
    if args.art_version is not None:
        at[L.ART_DIRECTION] = args.art_version
    lines, ok = read_ledger(ctx, rep)
    if not ok:
        rep.summary("ERROR", ctx.disp, "stale stopped: the ledger is unreadable")
        return HARNESS
    records = [r for _, r in lines]
    current = L.last_by_id(records)
    stale, unknown = [], set()
    for ident, rec in sorted(current.items()):
        if rec.get("status") not in LIVE:
            continue
        behind = []
        links = [x for x in rec.get("links") or [] if isinstance(x, dict)]
        for link in links:
            to, rev = link.get("to"), link.get("rev")
            if not L._is_int(rev):
                continue
            if L.is_id(to):
                now = L.content_rev(records, to) if to in current else None
            else:
                now = at.get(to)
                if now is None:
                    unknown.add(to)
            if now is not None and rev < now:
                behind.append({"rel": link.get("rel"), "to": to, "rev": rev, "now": now})
        # every asset is made under some art direction: one that names none is stale too
        if L.ART_DIRECTION in at and not any(x.get("to") == L.ART_DIRECTION
                                             and L._is_int(x.get("rev")) for x in links):
            behind.append({"rel": "made-under", "to": L.ART_DIRECTION, "rev": None,
                           "now": at[L.ART_DIRECTION]})
        if not behind:
            continue
        stale.append({"id": ident, "rev": _rev(rec), "status": rec.get("status"),
                      "path": where(ctx, rec), "behind": behind})
        rep.warn(where(ctx, rec), "stale", f"{rec.get('status')}; " + "; ".join(
            f"{b['to']} rev {b['rev'] if b['rev'] is not None else 'none'} < {b['now']}"
            for b in behind), ident, _rev(rec))
    if unknown:
        rep.warn(ctx.disp, "not-compared", "no current value given for "
                 + ", ".join(sorted(unknown)) + "; pass --at NS:KEY=N")
    rep.data.update(at=at, current=len(current), stale=stale)
    rep.summary("OK", ctx.disp, f"{len(stale)} of {len(current)} current record(s) are stale")
    return OK


def _current_or_stop(ctx, rep, ident):
    lines, ok = read_ledger(ctx, rep)
    if not ok:
        rep.summary("ERROR", ctx.disp, "nothing written: the ledger is unreadable")
        return None, None
    records = [r for _, r in lines]
    current = L.last_by_id(records)
    if ident not in current:
        rep.error(ctx.disp, "unknown-id", f"no record has id {ident}")
        rep.summary("ERROR", ctx.disp, "nothing written")
        return None, None
    if _rev(current[ident]) is None:
        rep.error(ctx.disp, "schema", f"id {ident}: its last line has no integer rev")
        rep.summary("ERROR", ctx.disp, "nothing written")
        return None, None
    return current[ident], records


def _write_rev(ctx, rep, old, new, verb):
    new.pop("rev", None)
    new["ts"] = L.now_utc()
    errs = L.validate(dict(new, rev=1))
    if errs:
        for e in errs:
            rep.error(where(ctx, new), "schema", e, new.get("id"))
        rep.summary("ERROR", where(ctx, new), "nothing written")
        return FAILED
    written = append(ctx, rep, new, assign_rev=True, expect_rev=old["rev"])
    rep.data["record"] = L.canonical(written)
    change = "" if old.get("status") == written.get("status") else \
        f" ({old.get('status')} -> {written.get('status')})"
    rep.summary("OK", where(ctx, written), f"{verb}: {written['id']} rev {written['rev']}{change}")
    return OK


def _refuse(ctx, rep, cur, rule, msg, code=FAILED):
    rep.error(where(ctx, cur), rule, msg, _id(cur), _rev(cur))
    rep.summary("ERROR", where(ctx, cur), "nothing written")
    return code


def cmd_status(ctx, args, rep):
    target, by = args.state, args.by
    if by is not None and target != "superseded":
        rep.error("--by", "usage", "--by names the successor of a superseded asset")
        return HARNESS
    if args.allow_dirty and target != "approved":
        rep.error("--allow-dirty", "usage", "--allow-dirty goes with approved")
        return HARNESS
    if args.approver is not None and target != "approved":
        rep.error("--approver", "usage", "--approver goes with approved")
        return HARNESS
    cur, records = _current_or_stop(ctx, rep, args.id)
    if cur is None:
        return HARNESS
    current = L.last_by_id(records)
    if by is not None:
        if by not in current:
            rep.error(ctx.disp, "unknown-id", f"--by {by}: no record has that id")
            rep.summary("ERROR", ctx.disp, "nothing written")
            return HARNESS
        if by == args.id:
            return _refuse(ctx, rep, cur, "superseded-cycle", "superseded by itself")
        if args.id in successor_chain(current, by):
            return _refuse(ctx, rep, cur, "superseded-cycle", f"{by} is already superseded, "
                           f"through {' -> '.join(successor_chain(current, by))}, by {args.id}")
        if current[by].get("status") not in LIVE:
            return _refuse(ctx, rep, cur, "bad-successor", f"{by} is {current[by].get('status')}; "
                           "the successor is a candidate or approved asset")
    evidence = []
    for e in args.evidence or []:
        if e not in current:
            rep.error(ctx.disp, "unknown-id", f"--evidence {e}: no record has that id; record the "
                      "image first (kind qa-sheet)")
            rep.summary("ERROR", ctx.disp, "nothing written")
            return HARNESS
        evidence.append({"rel": "evidence", "to": e, "rev": L.content_rev(records, e)})
    if cur.get("status") == target and (by is None or cur.get("superseded_by") == by) \
            and args.note is None and args.approver is None and not evidence:
        rep.summary("OK", where(ctx, cur), f"{args.id} is already {target}; nothing written")
        return OK
    allowed_dirty = False
    if target == "approved":
        if cur.get("status") == "diagnostic":
            return _refuse(ctx, rep, cur, "diagnostic", "a diagnostic run is evidence, not an "
                           "asset; record the files again as a candidate to ship them")
        known = {r["id"] for r in records if isinstance(r.get("id"), str)}
        for e in L.validate(cur):
            rep.error(where(ctx, cur), "schema", e, args.id, cur["rev"])
        facts = gather_facts(ctx, rep, [cur], approving=True)
        check_files(ctx, rep, cur, facts, approving=True)
        check_approval(ctx, rep, cur)
        check_vendor(ctx, rep, cur, facts, strict=False)
        check_refs(ctx, rep, cur, known)
        # what check would fail once it is approved: a file another id holds, a circle
        check_graph(ctx, rep, dict(current, **{args.id: dict(cur, status="approved")}),
                    only=args.id)
        allowed_dirty = check_dirty(ctx, rep, cur, args.allow_dirty)
        if rep.count("ERROR"):
            rep.summary("ERROR", where(ctx, cur), f"not approved: {args.id} would fail check")
            return FAILED
    new = copy.deepcopy(cur)
    new["status"] = target
    if target == "superseded" and by is not None:
        new["superseded_by"] = by
    elif target != "superseded":
        new.pop("superseded_by", None)
    if target == "approved":
        if args.approver is not None:
            new["approver"] = args.approver
    else:
        new.pop("approver", None)
    if evidence:
        links = list(new.get("links") or [])
        for link in evidence:
            _set_link(links, link)
        new["links"] = links
    if args.note is not None:
        new["note"] = args.note
    if allowed_dirty:
        new["warnings"] = list(new.get("warnings") or []) + ["approved while file.dirty was true"]
    return _write_rev(ctx, rep, cur, new, f"status {target}")


def cmd_history(ctx, args, rep):
    lines, ok = read_ledger(ctx, rep)
    if not ok:
        rep.summary("ERROR", ctx.disp, "history stopped: the ledger is unreadable")
        return HARNESS
    records = [r for _, r in lines]
    revs = [r for r in records if r.get("id") == args.id]
    if not revs:
        rep.error(ctx.disp, "unknown-id", f"no record has id {args.id}")
        rep.summary("ERROR", ctx.disp, "nothing to show")
        return HARNESS
    approved = [r for r in revs if r.get("status") == "approved"]
    shipped = L.current_version(records, args.id)
    if shipped is None and approved:                 # withdrawn: the last approval is the fallback
        previous = approved[-1]
    else:
        good = [r for r in approved if r is not shipped and L.content(r) != L.content(shipped)]
        previous = good[-1] if good else None
    rows = []
    for r in revs:
        first = files_of(r)[0] if files_of(r) else {}
        mark = "current version" if r is shipped else "previous good" if r is previous else ""
        rows.append({"rev": _rev(r), "ts": r.get("ts"), "status": r.get("status"),
                     "path": first.get("path"), "sha256": first.get("sha256"), "mark": mark,
                     "note": r.get("note")})
        sha = (first.get("sha256") or "")[:12] or "-"
        rep.ok(first.get("path") or ctx.disp, f"rev {_rev(r)} {r.get('ts')} {r.get('status')} "
               f"sha256 {sha}" + (f" [{mark}]" if mark else ""), args.id)
    rep.data.update(id=args.id, history=rows,
                    current_version=_rev(shipped) if shipped else None,
                    previous_good=_rev(previous) if previous else None)
    why = f"none (rev {_rev(revs[-1])} is {revs[-1].get('status')})" if approved else \
        "none (never approved)"
    rep.summary("OK", ctx.disp, f"{args.id}: {len(revs)} rev(s); current version "
                f"{_rev(shipped) if shipped else why}")
    return OK


def cmd_mv(ctx, args, rep):
    cur, records = _current_or_stop(ctx, rep, args.id)
    if cur is None:
        return HARNESS
    files = files_of(cur)
    paths = {}
    for key, given in (("new", args.newpath), ("old", args.file)):
        try:
            paths[key] = ctx.norm(given) if given else None
        except ValueError as e:
            rep.error(str(given), "path", str(e))
            rep.summary("ERROR", ctx.disp, "nothing written")
            return FAILED
    newpath, oldpath = paths["new"], paths["old"]
    if oldpath is None:
        if len(files) != 1:
            rep.error(ctx.disp, "usage", f"{args.id} has {len(files)} files; name the one that "
                      "moved with --file")
            rep.summary("ERROR", ctx.disp, "nothing written")
            return HARNESS
        oldpath = files[0]["path"]
    entry = next((f for f in files if L.path_key(f["path"]) == L.path_key(oldpath)), None)
    if entry is None or L.path_key(newpath) == L.path_key(oldpath) \
            or any(L.path_key(f["path"]) == L.path_key(newpath) for f in files):
        rep.error(newpath, "usage", f"{oldpath} is not one of {args.id}'s files" if entry is None
                  else f"{args.id} already lists {newpath}")
        rep.summary("ERROR", ctx.disp, "nothing written")
        return HARNESS
    current = L.last_by_id(records)
    held = [i for i in owners_of(current).get(L.path_key(newpath), []) if i != args.id]
    if rival_owners(current, held + [args.id]) != [args.id] and held:
        rep.error(newpath, "dual-owner", f"already a file of {', '.join(held)}", args.id, cur["rev"])
        rep.summary("ERROR", newpath, "nothing written")
        return FAILED
    full = ctx.full(newpath)
    if not os.path.isfile(full):
        rep.error(newpath, "missing", "not on disk; move the file (and its .meta) first, then "
                  "record the move", args.id, cur["rev"])
        rep.summary("ERROR", newpath, "nothing written")
        return FAILED
    sha, size = L.sha256_file(full), os.path.getsize(full)
    if cur.get("status") == "approved" and entry.get("mutable") is not True \
            and entry.get("sha256") and entry["sha256"] != sha:
        rep.error(newpath, "changed-after-approval", f"its bytes differ from the approved "
                  f"{oldpath}; record it as a new candidate instead", args.id, cur["rev"])
        rep.summary("ERROR", newpath, "nothing written")
        return FAILED
    if os.path.exists(ctx.full(oldpath)):
        rep.warn(oldpath, "old-path-exists", "still on disk: a copy, not a move?", args.id)
    new = copy.deepcopy(cur)
    for f in new["files"]:
        if isinstance(f, dict) and f.get("path") == entry["path"]:
            f.update(path=newpath, sha256=sha, bytes=size)
            f.pop("missing", None)
    if args.note is not None:
        new["note"] = args.note
    return _write_rev(ctx, rep, cur, new, f"moved {oldpath} -> {newpath}")


def _cell(text):
    return str(text).replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def cmd_render(ctx, args, rep):
    lines, ok = read_ledger(ctx, rep)
    if not ok:
        rep.summary("ERROR", ctx.disp, "render stopped: the ledger is unreadable")
        return HARNESS
    rows = []
    for ident, rec in L.last_by_id([r for _, r in lines]).items():
        paths = [f["path"] for f in files_of(rec)]
        rows.append({"date": str(rec.get("ts") or "")[:10], "id": ident,
                     "path": paths[0] if paths else "", "more": max(len(paths) - 1, 0),
                     "kind": rec.get("kind"), "status": rec.get("status"),
                     "art_version": made_under(rec), "note": rec.get("note") or ""})
    rows.sort(key=lambda r: (r["date"], r["id"]))
    for r in rows:
        more = f" +{r['more']}" if r["more"] else ""
        version = "-" if r["art_version"] is None else r["art_version"]
        rep.rows.append(f"| {r['date']} | `{r['path']}`{more} | {_cell(r['kind'])} | "
                        f"{_cell(r['status'])} | {version} | {_cell(r['note'])} |")
    rep.data["rows"] = rows
    return OK


def cmd_selftest(ctx, args, rep):
    import registry_selftest
    return registry_selftest.run(rep)


# ----------------------------------------------------------------------------------------- cli


COMMANDS = {"init": cmd_init, "record": cmd_record, "check": cmd_check, "stale": cmd_stale,
            "status": cmd_status, "history": cmd_history, "mv": cmd_mv, "render": cmd_render,
            "selftest": cmd_selftest}


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS,
                        help="the project root; ledger paths are relative to it (default: .)")
    common.add_argument("--ledger", default=argparse.SUPPRESS,
                        help="the ledger (default: $ART_LEDGER, else <root>/ArtDirection/assets.jsonl)")
    machine = argparse.ArgumentParser(add_help=False)
    machine.add_argument("--json", dest="as_json", action="store_true",
                         help="print one JSON object instead of lines")

    ap = Usage(prog="registry.py", parents=[common],
               description="The project's art-asset ledger. Exit 0 green, 2 failed, 3 harness.")
    sub = ap.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True
    sub.add_parser("init", parents=[common, machine], help="create the empty ledger")

    p = sub.add_parser("record", parents=[common], help="append a record from a partial record")
    p.add_argument("--json", dest="json_in", metavar="FILE",
                   help="the partial record (default, or '-': stdin)")
    p.add_argument("--kind", help="a slug; the vocabulary: " + " ".join(L.KINDS))
    p.add_argument("--class", dest="class_", metavar="CLASS",
                   help="the 3D asset class (a row of `3D asset classes`)")
    p.add_argument("--source", help=" ".join(L.SOURCES))
    p.add_argument("--license", help="required for purchased and third-party: purchased:<pack>, cc0")
    p.add_argument("--status", help="default candidate; approved runs the approval checks")
    p.add_argument("--id", help="default: the id that holds the first file, else its path slugified")
    p.add_argument("--art-version", dest="art_version", type=int,
                   help="the ART_DIRECTION.md Version: a made-under art:direction link")
    p.add_argument("--link", action="append", metavar="REL=TO[@REV]",
                   help="a link; TO is a ledger id (its rev is pinned) or ns:key (repeat)")
    p.add_argument("--note")
    p.add_argument("--allow-dirty", action="store_true",
                   help="with --status approved: accept an unsaved Blender file")

    p = sub.add_parser("check", parents=[common, machine], help="every rule, then orphans")
    p.add_argument("--strict", action="store_true",
                   help="unknown keys and tracked purchased or third-party files are errors; "
                   "kinds and rels outside the vocabulary are warnings")

    p = sub.add_parser("stale", parents=[common, machine],
                       help="current candidate or approved records with a link behind")
    p.add_argument("--art-version", dest="art_version", type=int,
                   help="the current ART_DIRECTION.md Version (= --at art:direction=N)")
    p.add_argument("--at", action="append", metavar="NS:KEY=N",
                   help="the current value of an outside name (repeat)")

    p = sub.add_parser("status", parents=[common, machine], help="append a status change")
    p.add_argument("id")
    p.add_argument("state", choices=L.STATUSES, metavar="STATE", help=" ".join(L.STATUSES))
    p.add_argument("--by", metavar="ID", help="with superseded: the id that replaces it")
    p.add_argument("--allow-dirty", action="store_true",
                   help="with approved: approve output of an unsaved Blender file anyway")
    p.add_argument("--approver", metavar="NAME", help="with approved: who looked")
    p.add_argument("--evidence", action="append", metavar="ID",
                   help="the recorded image the decision rests on (repeat)")
    p.add_argument("--note")

    p = sub.add_parser("history", parents=[common, machine],
                       help="every revision, the current version and the previous good one")
    p.add_argument("id")

    p = sub.add_parser("mv", parents=[common, machine], help="the same id at a new path")
    p.add_argument("id")
    p.add_argument("newpath")
    p.add_argument("--file", help="the old path, when the record has more than one file")
    p.add_argument("--note")

    sub.add_parser("render", parents=[common, machine], help="Markdown rows for manifest.md")
    registry_adopt.register(sub, common, machine, COMMANDS)
    registry_ingest.register(sub, common, machine, COMMANDS)
    sub.add_parser("selftest", parents=[machine], help="every case in a temporary directory")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    ctx = Ctx(args)
    rep = Report()
    try:
        code = COMMANDS[args.command](ctx, args, rep)
    except L.LedgerConflict as e:
        rep.error(ctx.disp, "conflict", str(e))
        rep.summary("ERROR", ctx.disp, "nothing written")
        code = HARNESS
    except (L.LedgerError, OSError) as e:
        rep.error(ctx.disp, "harness", str(e))
        rep.summary("ERROR", ctx.disp, f"{args.command} stopped")
        code = HARNESS
    rep.emit(args.command, code, getattr(args, "as_json", False))
    return code


def run_quiet(*argv):
    """(exit code, stdout) of main(argv), stderr swallowed; for the selftests."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = main(list(argv))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else HARNESS
    return code, out.getvalue()


_run = run_quiet


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(OK)
