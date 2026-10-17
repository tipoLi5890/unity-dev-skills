#!/usr/bin/env python3
"""registry_ledger.py — read, validate and append the art-asset ledger (schema 1).

Not a command: `registry.py` imports it, and so may any script in this skill's `scripts/`
directory. Standard library only.

The ledger is JSONL and append-only: one record per line, never edited in place. An id's current
record is its last line; `rev` counts that id's lines from 1 with no gap. The current version of an
asset is its latest `approved` revision. The field table and the check rules are
`reference/ledger-schema.md`.

  load(path)                   every record in file order; a bad line raises LedgerError
  load(path, errors=[], torn=[])
                               the same, but bad lines go into `errors` and a torn last line
                               (no newline, does not parse) into `torn`; both are skipped
  load_lines(path, errors, torn)  (line number, record) pairs
  last_by_id(records)          id -> current record; the last line for an id wins
  last_rev(records, id)        the highest rev written for id, 0 for none
  content(rec)                 the sorted file hashes of one record
  content_rev(records, id)     the rev at which id's file hashes last changed, 0 for none
  current_version(records, id) id's latest approved record; None when never approved or when
                               its last record is rejected, superseded or unused
  append(path, rec, assign_rev=True, expect_rev=N, notes=[])
                               one os.write of one line under an exclusive lock, then fsync;
                               rev = last + 1 read inside the lock; LedgerConflict when the id
                               moved past N meanwhile; a torn last line is moved to <path>.torn
  validate(rec, strict=False)  a list of problems against schema 1; [] when valid
  vocabulary_notes(rec)        kinds and link rels outside the documented vocabulary
  cycles(edges)                every cycle in {id: [id, ...]}
  sha256_file, rel_posix, slugify, path_key, path_problem, now_utc, dumps, canonical
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import re
import unicodedata

try:
    import fcntl
except ImportError:              # Windows
    fcntl = None
    try:
        import msvcrt
    except ImportError:
        msvcrt = None

SCHEMA = 1
# `kind` is an open slug; these are the words the skill documents. Another slug is allowed and
# `check --strict` warns about it.
KINDS = ("sprite", "sheet", "frames", "preview", "ref", "texture", "mesh", "rig", "clip", "audio",
         "qa-sheet", "change", "other")
# `links[].rel` is an open slug too; the documented words.
RELS = ("made-under", "made-by", "evidence", "explained-by", "depends-on", "flow-node", "beat")
STATUSES = ("candidate", "approved", "rejected", "superseded", "unused", "diagnostic")
ROLES = ("source", "derived", "shipped", "preview", "ref")
VERDICTS = ("green", "failed", "harness")
SOURCES = ("generated", "authored", "purchased", "third-party", "unknown")
LICENSED_SOURCES = ("purchased", "third-party")

FIELDS = ("schema", "id", "rev", "ts", "kind", "class", "status", "superseded_by", "source",
          "license", "parent", "links", "files", "inputs", "tool", "params", "gates", "verdict",
          "warnings", "file", "approver", "note")
REQUIRED = ("schema", "id", "rev", "ts", "kind", "status", "files", "source")
FILE_FIELDS = ("path", "role", "sha256", "bytes", "vendor", "mutable", "missing")
INPUT_FIELDS = ("path", "sha256")
LINK_FIELDS = ("rel", "to", "rev")
TOOL_FIELDS = ("skill", "script", "version")
GATE_FIELDS = ("name", "value", "limit", "pass")
FILESTATE_FIELDS = ("path", "saved", "dirty", "sha256", "bytes")
PARAMS_RESERVED = ("model", "seed", "prompt_sha256", "prompt_file", "workflow_sha256",
                   "overrides", "server_label", "argv")

# An id: Unicode letters, digits and combining marks (NFC, lower case; a mark is a Devanagari or
# Thai vowel sign NFC does not compose), '/', '.', '_', '-'; it starts with a letter or a digit.
# `ns:key` names something outside the ledger (`art:direction`, `job:<id>`).
ID_PUNCT = "/._-"
SLUG_RE = re.compile(r"[a-z][a-z0-9-]*\Z")
NS_KEY_RE = re.compile(r"([a-z][a-z0-9-]*):(\S+)\Z")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00))?\Z")
URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://", re.IGNORECASE)
ART_DIRECTION = "art:direction"

# Where the Windows lock sits: one byte far past any real ledger's end, so a reader never meets it.
_WIN_LOCK_OFFSET = 0x7FFFFFFF


class LedgerError(Exception):
    """The ledger cannot be read or written as asked. `problems` holds one message per cause."""

    def __init__(self, problems):
        self.problems = [problems] if isinstance(problems, str) else list(problems)
        super().__init__("; ".join(self.problems))


class LedgerConflict(LedgerError):
    """Another writer appended a rev for this id between the read and the write."""


# ------------------------------------------------------------------------------------- reading


def _no_constant(name):
    raise ValueError(f"{name} is not JSON")


def loads(text):
    """json.loads that refuses NaN, Infinity and -Infinity."""
    return json.loads(text, parse_constant=_no_constant)


def _split(data):
    """(segments, torn): the file's lines, and the bytes after its last newline (b"" when it ends
    with one)."""
    segments = data.split(b"\n")
    return segments, segments[-1]


def _parse(raw, n):
    """(record, problem): one line read as a JSON object."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return None, f"not UTF-8 ({e.reason})"
    if n == 1:
        text = text.lstrip("﻿")
    try:
        rec = loads(text)
    except ValueError as e:
        return None, f"not JSON ({e})"
    if not isinstance(rec, dict):
        return None, f"a JSON {type(rec).__name__}, not an object"
    return rec, None


def load_lines(path, errors=None, torn=None):
    """[(line number, record)] in file order. A blank line is skipped. A line that is not UTF-8,
    not JSON (NaN and Infinity are not), or JSON but not an object is a problem: appended to
    `errors` when a list is given, otherwise raised together as one LedgerError after the whole
    file is read. The last line, when it has no newline and does not parse, is a torn line (a
    writer that died, or one still writing): it goes into `torn` when a list is given and is never
    an error. Unknown keys are kept. A missing file raises FileNotFoundError."""
    problems, out = [], []
    with open(path, "rb") as fh:
        data = fh.read()
    segments, tail = _split(data)
    last = len(segments)
    for n, raw in enumerate(segments, 1):
        if not raw.strip():
            continue
        rec, why = _parse(raw, n)
        if why is None:
            out.append((n, rec))
        elif n == last and tail:
            if torn is not None:
                torn.append(f"{path}:{n}: {why}; {len(raw)} byte(s) after the last newline")
        else:
            problems.append(f"{path}:{n}: {why}")
    if problems:
        if errors is None:
            raise LedgerError(problems)
        errors.extend(problems)
    return out


def load(path, errors=None, torn=None):
    """Every record in file order; see load_lines for what counts as a bad line."""
    return [rec for _, rec in load_lines(path, errors, torn)]


def last_by_id(records):
    """id -> current record. The last line written for an id wins, whatever its rev says;
    `registry.py check` reports a rev that is out of sequence."""
    current = {}
    for rec in records:
        ident = rec.get("id")
        if isinstance(ident, str):
            current[ident] = rec
    return current


def last_rev(records, ident):
    """The highest integer rev written for `ident`, or 0 when it has none."""
    revs = [r.get("rev") for r in records if r.get("id") == ident and _is_int(r.get("rev"))]
    return max(revs, default=0)


def content(rec):
    """The sorted file hashes of one record: what `content_rev` compares."""
    files = rec.get("files") if isinstance(rec.get("files"), list) else []
    return sorted(str(f.get("sha256")) for f in files if isinstance(f, dict))


def content_rev(records, ident):
    """The rev at which `ident`'s file hashes last changed: a status change or a move is not new
    content. 0 when the id has no record."""
    out, before = 0, None
    for r in records:
        if r.get("id") != ident or not _is_int(r.get("rev")):
            continue
        now = content(r)
        if now != before:
            out, before = r["rev"], now
    return out


WITHDRAWN = ("rejected", "superseded", "unused")


def current_version(records, ident):
    """`ident`'s latest approved record (what the game should load), or None: never approved, or
    its last record is rejected, superseded or unused (the approval was withdrawn)."""
    found, last = None, None
    for r in records:
        if r.get("id") == ident:
            last = r
            if r.get("status") == "approved":
                found = r
    return None if last is None or last.get("status") in WITHDRAWN else found


def cycles(edges):
    """Every cycle in the graph {node: [node, ...]}, each as the list of its nodes, starting at
    its smallest node. Edges to nodes outside the dict are followed no further."""
    found, state = set(), {}

    def visit(node, stack):
        state[node] = 1
        stack.append(node)
        for nxt in edges.get(node) or ():
            if state.get(nxt) == 1:
                ring = stack[stack.index(nxt):]
                k = ring.index(min(ring))
                found.add(tuple(ring[k:] + ring[:k]))
            elif state.get(nxt) is None and nxt in edges:
                visit(nxt, stack)
        stack.pop()
        state[node] = 2

    for node in sorted(edges):
        if state.get(node) is None:
            visit(node, [])
    return [list(c) for c in sorted(found)]


# ------------------------------------------------------------------------------------- writing


def canonical(rec):
    """A copy with the schema's keys first, in table order, then any other keys as they came."""
    out = {k: rec[k] for k in FIELDS if k in rec}
    out.update((k, v) for k, v in rec.items() if k not in out)
    files = out.get("files")
    if isinstance(files, list):
        out["files"] = [_ordered(f, FILE_FIELDS) if isinstance(f, dict) else f for f in files]
    return out


def _ordered(d, keys):
    out = {k: d[k] for k in keys if k in d}
    out.update((k, v) for k, v in d.items() if k not in out)
    return out


def dumps(rec):
    """One ledger line, without its newline. json escapes every newline inside strings; NaN and
    Infinity raise ValueError."""
    return json.dumps(canonical(rec), ensure_ascii=False, allow_nan=False)


def _lock(fd):
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX)
    elif msvcrt is not None:
        os.lseek(fd, _WIN_LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)    # retries for 10 s, then raises OSError


def _unlock(fd):
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
    elif msvcrt is not None:
        os.lseek(fd, _WIN_LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


def _clear_torn_tail(path, fd, notes):
    """Inside the lock: a last line without its newline is either a whole record (it gets its
    newline) or a torn fragment of a writer that died (no live writer holds the lock), which is
    moved to <path>.torn so the next line does not turn it into a corrupt middle line. Returns the
    bytes to write before the new line."""
    with open(path, "rb") as fh:
        data = fh.read()
    if not data or data.endswith(b"\n"):
        return b""
    _, tail = _split(data)
    rec, _ = _parse(tail, data.count(b"\n") + 1)
    if rec is not None:
        return b"\n"
    with open(path + ".torn", "ab") as side:
        side.write(tail + b"\n")
    os.ftruncate(fd, len(data) - len(tail))
    if notes is not None:
        notes.append(f"a torn last line ({len(tail)} byte(s)) was moved to "
                     f"{os.path.basename(path)}.torn")
    return b""


def append(path, rec, assign_rev=False, expect_rev=None, notes=None):
    """Append `rec` as one line and return what was written. The file is created when absent.

    The line goes out in one os.write on a descriptor opened with O_APPEND, under an exclusive
    lock, then fsync. A torn last line is moved aside first (see _clear_torn_tail), with a message
    in `notes` when a list is given. assign_rev=True sets rev to the id's last rev + 1, read inside
    the lock; expect_rev=N raises LedgerConflict when the id's last rev is no longer N.
    Validation is the caller's; a NaN or Infinity raises ValueError before anything is written."""
    if not isinstance(rec, dict):
        raise LedgerError("a record is a JSON object")
    rec = dict(rec)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        _lock(fd)
        try:
            if assign_rev or expect_rev is not None:
                ident = rec.get("id")
                if not isinstance(ident, str):
                    raise LedgerError("cannot number a record without an id")
                last = last_rev(load(path, errors=[]), ident)
                if expect_rev is not None and last != expect_rev:
                    raise LedgerConflict(f"{ident}: rev {last} was written while rev {expect_rev} "
                                         "was being changed; read the ledger again")
                if assign_rev:
                    rec["rev"] = last + 1
            line = dumps(rec).encode("utf-8") + b"\n"
            data = _clear_torn_tail(path, fd, notes) + line
            written = os.write(fd, data)
            while written < len(data):           # only if the OS split it; the lock is held
                written += os.write(fd, data[written:])
            os.fsync(fd)
        finally:
            _unlock(fd)
    finally:
        os.close(fd)
    return rec


# ---------------------------------------------------------------------------------- validating


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def is_id(v):
    """Whether `v` is a ledger id: the characters above, lower case, NFC, no empty segment."""
    return (isinstance(v, str) and v[:1].isalnum()
            and all(_word(c) or c in ID_PUNCT for c in v) and v == v.lower()
            and unicodedata.normalize("NFC", v) == v and "//" not in v and not v.endswith("/"))


def is_link_target(v):
    """A ledger id, or `ns:key` for something outside the ledger."""
    return is_id(v) or (isinstance(v, str) and bool(NS_KEY_RE.match(v)))


def path_key(p):
    """A path as the ledger compares it: NFC, so a composed and a decomposed name are one file."""
    return unicodedata.normalize("NFC", p) if isinstance(p, str) else p


def path_problem(p):
    """Why `p` is not a ledger path (project-root-relative, forward slashes), or None."""
    if not isinstance(p, str) or not p:
        return "is empty or not a string"
    if any(c in p for c in "\n\r\0"):
        return "contains a control character"
    if "\\" in p:
        return "uses a backslash; ledger paths use forward slashes"
    if p.startswith(("/", "~")) or re.match(r"[A-Za-z]:", p):
        return "is absolute; ledger paths are relative to the project root"
    segments = p.split("/")
    if ".." in segments:
        return "contains '..'"
    if any(s in ("", ".") for s in segments):
        return "is not normalised (an empty or '.' segment)"
    return None


def _unknown(d, keys, where, errs):
    for k in d:
        if k not in keys:
            errs.append(f"{where}{k}: unknown key (check --strict)")


def _urls(value, where, errs):
    if isinstance(value, str):
        if URL_RE.search(value):
            errs.append(f"{where}: holds a URL; record server_label, never a server address")
    elif isinstance(value, dict):
        for k, v in value.items():
            _urls(v, f"{where}.{k}", errs)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _urls(v, f"{where}[{i}]", errs)


def _non_finite(value, where, errs):
    if isinstance(value, float) and not math.isfinite(value):
        errs.append(f"{where}: {value!r} is not a number JSON can hold")
    elif isinstance(value, dict):
        for k, v in value.items():
            _non_finite(v, f"{where}.{k}" if where else str(k), errs)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _non_finite(v, f"{where}[{i}]", errs)


def validate(rec, strict=False):
    """Problems with `rec` against schema 1, each `field: message`; [] when it is valid.
    An optional field set to null counts as absent. strict=True also rejects keys the schema does
    not name, at the top level and inside files, inputs, links, tool, gates and file; params stays
    open. A kind or rel outside the vocabulary is not a problem here: see vocabulary_notes."""
    if not isinstance(rec, dict):
        return ["record: not a JSON object"]
    errs = []

    def err(field, msg):
        errs.append(f"{field}: {msg}")

    def has(k):
        return rec.get(k) is not None

    _non_finite(rec, "", errs)
    for k in REQUIRED:
        if not has(k):
            err(k, "required")
    if has("schema") and (not _is_int(rec["schema"]) or rec["schema"] != SCHEMA):
        err("schema", f"is {rec['schema']!r}, expected {SCHEMA}")
    if has("id") and not is_id(rec["id"]):
        err("id", f"{rec['id']!r} is not an id (NFC, lower case, word characters and / . _ -)")
    if has("rev") and (not _is_int(rec["rev"]) or rec["rev"] < 1):
        err("rev", f"is {rec['rev']!r}, expected an integer from 1")
    if has("ts") and (not isinstance(rec["ts"], str) or not TS_RE.match(rec["ts"])
                      or not _real_time(rec["ts"])):
        err("ts", f"{rec['ts']!r} is neither RFC3339 UTC (…T…Z) nor YYYY-MM-DD")
    if has("kind") and not (isinstance(rec["kind"], str) and SLUG_RE.match(rec["kind"])):
        err("kind", f"{rec['kind']!r} is not a slug [a-z][a-z0-9-]*")
    for k, allowed in (("status", STATUSES), ("source", SOURCES), ("verdict", VERDICTS)):
        if has(k) and rec[k] not in allowed:
            err(k, f"{rec[k]!r} is not one of {' '.join(allowed)}")
    for k in ("class", "note", "approver"):
        if has(k) and not isinstance(rec[k], str):
            err(k, "is not a string")
    if has("superseded_by") and not is_id(rec["superseded_by"]):
        err("superseded_by", f"{rec['superseded_by']!r} is not an id")
    if rec.get("source") in LICENSED_SOURCES:
        if not isinstance(rec.get("license"), str) or not rec["license"].strip():
            err("license", f"required when source is {rec['source']} (e.g. purchased:<pack>, cc0)")
    elif has("license") and not isinstance(rec["license"], str):
        err("license", "is not a string")
    if has("parent"):
        if not isinstance(rec["parent"], list):
            err("parent", "is not a list of ids")
        else:
            for i, p in enumerate(rec["parent"]):
                if not is_id(p):
                    err(f"parent[{i}]", f"{p!r} is not an id")
    if has("links"):
        _validate_links(rec["links"], strict, errs)
    if has("files"):
        _validate_files(rec["files"], strict, errs)
    if has("inputs"):
        if not isinstance(rec["inputs"], list):
            err("inputs", "is not a list")
        else:
            for i, f in enumerate(rec["inputs"]):
                where = f"inputs[{i}]"
                if not isinstance(f, dict):
                    err(where, "is not an object")
                    continue
                why = path_problem(f.get("path"))
                if why:
                    err(f"{where}.path", f"{f.get('path')!r} {why}")
                if f.get("sha256") is not None and not (isinstance(f["sha256"], str)
                                                        and SHA_RE.match(f["sha256"])):
                    err(f"{where}.sha256", "is not 64 lowercase hex digits")
                if strict:
                    _unknown(f, INPUT_FIELDS, f"{where}.", errs)
    if has("tool"):
        if not isinstance(rec["tool"], dict):
            err("tool", "is not an object")
        else:
            for k in TOOL_FIELDS:
                if rec["tool"].get(k) is not None and not isinstance(rec["tool"][k], str):
                    err(f"tool.{k}", "is not a string")
            if strict:
                _unknown(rec["tool"], TOOL_FIELDS, "tool.", errs)
    if has("params"):
        if not isinstance(rec["params"], dict):
            err("params", "is not an object")
        else:
            if "prompt" in rec["params"]:
                err("params.prompt", "store prompt_sha256 or prompt_file, never the prompt text")
            _urls(rec["params"], "params", errs)
    if has("gates"):
        if not isinstance(rec["gates"], list):
            err("gates", "is not a list")
        else:
            for i, g in enumerate(rec["gates"]):
                where = f"gates[{i}]"
                if not isinstance(g, dict):
                    err(where, "is not an object")
                    continue
                if not isinstance(g.get("name"), str) or not g["name"]:
                    err(f"{where}.name", "required, a string")
                if not isinstance(g.get("pass"), bool):
                    err(f"{where}.pass", "required, true or false")
                if strict:
                    _unknown(g, GATE_FIELDS, f"{where}.", errs)
    if has("warnings") and (not isinstance(rec["warnings"], list)
                            or not all(isinstance(w, str) for w in rec["warnings"])):
        err("warnings", "is not a list of strings")
    if has("file"):
        if not isinstance(rec["file"], dict):
            err("file", "is not an object")
        else:
            f = rec["file"]
            if f.get("path") is not None and not isinstance(f["path"], str):
                err("file.path", "is not a string")
            for k in ("saved", "dirty"):
                if f.get(k) is not None and not isinstance(f[k], bool):
                    err(f"file.{k}", "is not true or false")
            if f.get("sha256") is not None and not (isinstance(f["sha256"], str)
                                                    and SHA_RE.match(f["sha256"])):
                err("file.sha256", "is not 64 lowercase hex digits")
            if strict:
                _unknown(f, FILESTATE_FIELDS, "file.", errs)
    if strict:
        _unknown(rec, FIELDS, "", errs)
    return errs


def _validate_links(links, strict, errs):
    if not isinstance(links, list):
        errs.append("links: is not a list")
        return
    for i, link in enumerate(links):
        where = f"links[{i}]"
        if not isinstance(link, dict):
            errs.append(f"{where}: is not an object")
            continue
        if not (isinstance(link.get("rel"), str) and SLUG_RE.match(link["rel"])):
            errs.append(f"{where}.rel: {link.get('rel')!r} is not a slug [a-z][a-z0-9-]*")
        if not is_link_target(link.get("to")):
            errs.append(f"{where}.to: {link.get('to')!r} is neither a ledger id nor ns:key")
        if link.get("rev") is not None and (not _is_int(link["rev"]) or link["rev"] < 0):
            errs.append(f"{where}.rev: {link['rev']!r} is not a whole number")
        if strict:
            _unknown(link, LINK_FIELDS, f"{where}.", errs)


def _validate_files(files, strict, errs):
    if not isinstance(files, list) or not files:
        errs.append("files: needs at least one entry")
        return
    seen = set()
    for i, f in enumerate(files):
        where = f"files[{i}]"
        if not isinstance(f, dict):
            errs.append(f"{where}: is not an object")
            continue
        why = path_problem(f.get("path"))
        if why:
            errs.append(f"{where}.path: {f.get('path')!r} {why}")
        elif path_key(f["path"]) in seen:
            errs.append(f"{where}.path: {f['path']} is listed twice")
        else:
            seen.add(path_key(f["path"]))
        if f.get("role") is not None and f["role"] not in ROLES:
            errs.append(f"{where}.role: {f['role']!r} is not one of {' '.join(ROLES)}")
        if f.get("sha256") is not None and not (isinstance(f["sha256"], str)
                                                and SHA_RE.match(f["sha256"])):
            errs.append(f"{where}.sha256: is not 64 lowercase hex digits")
        if f.get("bytes") is not None and (not _is_int(f["bytes"]) or f["bytes"] < 0):
            errs.append(f"{where}.bytes: is not a byte count")
        for k in ("vendor", "mutable", "missing"):
            if f.get(k) is not None and not isinstance(f[k], bool):
                errs.append(f"{where}.{k}: is not true or false")
        if strict:
            _unknown(f, FILE_FIELDS, f"{where}.", errs)


def vocabulary_notes(rec):
    """A kind or a link rel the skill does not document: allowed, and named here so that
    `check --strict` can warn about a typo."""
    out = []
    if isinstance(rec.get("kind"), str) and rec["kind"] not in KINDS:
        out.append(f"kind {rec['kind']!r} is not in the vocabulary ({' '.join(KINDS)})")
    for link in rec.get("links") or []:
        if isinstance(link, dict) and isinstance(link.get("rel"), str) and link["rel"] not in RELS:
            out.append(f"link rel {link['rel']!r} is not in the vocabulary ({' '.join(RELS)})")
    return out


def _real_time(ts):
    try:
        if len(ts) == 10:
            datetime.date.fromisoformat(ts)
        else:
            datetime.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
        return True
    except ValueError:
        return False


# ------------------------------------------------------------------------------------- helpers


def now_utc():
    """Now as RFC3339 UTC to the second: 2026-03-14T09:26:53Z."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    """Hex sha256 of a file's bytes, read 1 MiB at a time."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rel_posix(path, root):
    """`path` relative to `root`, with forward slashes. A relative `path` is read against the
    current directory. ValueError when it lies outside `root` or is `root` itself."""
    def rel(p, r):
        try:
            return os.path.relpath(p, r)
        except ValueError:                       # another drive on Windows
            return os.pardir
    out = rel(os.path.abspath(path), os.path.abspath(root))
    if out == os.pardir or out.startswith(os.pardir + os.sep):
        out = rel(os.path.realpath(path), os.path.realpath(root))   # /tmp vs /private/tmp
    if out == os.pardir or out.startswith(os.pardir + os.sep):
        raise ValueError(f"{path} is outside the project root {root}")
    if out == os.curdir:
        raise ValueError(f"{path} is the project root itself, not a file in it")
    return out.replace(os.sep, "/")


def _word(c):
    """A letter, a digit or a combining mark, in any script."""
    return c.isalnum() or unicodedata.category(c)[0] == "M"


def _slug(segment):
    """Each run of other characters as one '-', trimmed; a segment starts with a letter or digit."""
    out, gap = [], False
    for c in segment:
        if not _word(c):
            gap = True
        elif out or c.isalnum():
            out.append("-" if gap and out else "")
            out.append(c)
            gap = False
    return "".join(out)


def slugify(relpath):
    """The id a path gets when it is first recorded: NFC, lower case, the last extension dropped,
    every run of characters that are not letters, digits or combining marks (in any script)
    turned into one '-',
    trimmed per segment, '/' kept. A name with no letter or digit left becomes the first 8 hex
    digits of the sha256 of its NFC path, under its folder's id.
      'ArtDirection/sheets/Runner_Run.png' -> 'artdirection/sheets/runner-run'
      'ArtDirection/角色/跑者.png'          -> 'artdirection/角色/跑者'
      'ArtDirection/sheets/★.png'          -> 'artdirection/sheets/<sha8>'"""
    nfc = unicodedata.normalize("NFC", relpath.replace("\\", "/"))
    p = unicodedata.normalize("NFC", nfc.lower())
    head, _, tail = p.rpartition("/")
    stem, dot, _ = tail.rpartition(".")
    if dot and stem:
        tail = stem
    folder = "/".join(s for s in (_slug(s) for s in head.split("/")) if s) if head else ""
    name = _slug(tail) or hashlib.sha256(nfc.encode("utf-8")).hexdigest()[:8]
    slug = f"{folder}/{name}" if folder else name
    if not is_id(slug):
        raise ValueError(f"{relpath!r} gives no usable id; pass one with --id")
    return slug
