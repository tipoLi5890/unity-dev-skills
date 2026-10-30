#!/usr/bin/env python3
"""registry_adopt.py — read a hand-written manifest.md once into ledger records (`registry.py adopt`).

A project that kept `ArtDirection/manifest.md` by hand and has no ledger starts here. The manifest
is read and never written: every Markdown table with a path column (outside code fences) gives
one record per row that names a file.

  registry.py adopt --dry-run [--out FILE] [--include-orphans]
                    the counts; FILE (outside --root) gets the records as a scratch ledger,
                    and the project ledger is never opened
  registry.py adopt --write [--include-orphans]
                    append the records to the ledger (--ledger / ART_LEDGER / the default);
                    ids the ledger already holds for the same files are skipped

Output is counts only: tables, rows, file names after expansion, on disk or not, struck rows,
records by status, orphans, the schema-valid ratio, and manifest line numbers for a row that cannot
be adopted (a folder cell, a range cut short, a cycle, a file two rows hold). No path or cell from
the project is printed; the records themselves go to FILE or to the ledger. The rules:
reference/adopt.md.

registry.py imports this module and calls register(); running this file passes its arguments to
`registry.py adopt` (`registry_adopt.py selftest` runs the adopt and ingest cases alone).
Exit codes are registry.py's: 0 green, 2 a record would break the schema, or rows that supersede
or parent each other in a circle, or two rows that hold one file (nothing written), 3 no manifest,
no table with a path column, a bad --out, an unreadable ledger.
Standard library only.
"""
from __future__ import annotations

import builtins
import contextlib
import datetime
import glob
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry_ledger as L  # noqa: E402

ART_DIR = "ArtDirection"
TOOL = {"skill": "art-asset-registry", "script": "registry.py adopt"}
EXPAND_CAP = 10000                 # names one path cell may expand to
LIVE = ("approved",)

# A header cell's field: the first pattern that matches it, in this order, so "Prompt file" is
# the prompt column and "Anchor file" the anchor column. Columns that match nothing are ignored.
HEADERS = (
    ("prompt", re.compile(r"prompt|提示", re.I)),
    ("anchor", re.compile(r"anchor|錨", re.I)),
    ("version", re.compile(r"\bver(sion)?\b|規格版本|版本", re.I)),
    ("date", re.compile(r"\bdate\b|日期", re.I)),
    ("status", re.compile(r"\bstatus\b|\bstate\b|狀態", re.I)),
    ("type", re.compile(r"\btype\b|\bkind\b|類型|種類", re.I)),
    ("path", re.compile(r"\bpaths?\b|\bfiles?\b|\bfile ?names?\b|路徑|檔案|檔名", re.I)),
    ("asset", re.compile(r"\bassets?\b|資產", re.I)),      # the path column only when none is
)

# Words that end a row's life: bold anywhere in the row, or plain in its status cell.
STATUS_WORDS = (
    ("unused", re.compile(r"\bunused\b|未使用", re.I)),
    ("rejected", re.compile(r"\brejected\b|已拒絕|退件", re.I)),
    ("superseded", re.compile(r"\bsuperseded\b|\barchived?\b|已取代|已歸檔|歸檔|封存", re.I)),
)
BOLD = re.compile(r"(\*\*|__)(.+?)\1")
NEGATED = re.compile(r"(?:\bnot|\bno longer|\bnever|不是|並非|非)\s*\Z", re.I)

# A type cell's kind, or a path's: the first match wins ("sprite sheet" is a sheet).
KIND_WORDS = tuple((k, re.compile(p, re.I)) for k, p in (
    ("qa-sheet", r"\bqa\b|\bcontact ?sheets?\b|檢查表|對照表"),
    ("sheet", r"\bsheets?\b|\bspritesheets?\b|\batlas\b|圖集"),
    ("frames", r"\bframes?\b|影格"),
    ("sprite", r"\bsprites?\b|精靈"),
    ("preview", r"\bpreviews?\b|\bgif\b|預覽"),
    ("ref", r"\bref\b|\breferences?\b|\banchors?\b|\bturnarounds?\b|\bconcepts?\b|參考|錨點|視圖"),
    ("texture", r"\btextures?\b|\bmaterials?\b|貼圖|材質"),
    ("rig", r"\brigs?\b|\bskeleton\b|\barmature\b|骨架|綁定"),
    ("clip", r"\bclips?\b|\banim(ation)?s?\b|\bmotions?\b|動作|動畫"),
    ("mesh", r"\bmesh(es)?\b|\bmodels?\b|\b3d\b|模型|網格"),
    ("audio", r"\baudio\b|\bsfx\b|\bsounds?\b|\bmusic\b|音效|音樂|音訊"),
))
EXT_KIND = {".wav": "audio", ".ogg": "audio", ".mp3": "audio", ".flac": "audio", ".aif": "audio",
            ".aiff": "audio", ".glb": "mesh", ".gltf": "mesh", ".obj": "mesh", ".fbx": "mesh",
            ".anim": "clip"}

LINK = re.compile(r"!?\[[^\]]*\]\(\s*([^)\s]+)[^)]*\)")
BR = re.compile(r"<br\s*/?>", re.I)
PLAIN_SEP = re.compile(r"[\s+,，、;；]+")
QUOTED_SEP = re.compile(r"\s*[+,，、;；]\s*|\s+(?:and|&)\s+", re.I)
BRACE = re.compile(r"\{([^{}]*)\}")
RANGE = re.compile(r"(?<![\d.])(\d+)\.\.(\d+)(?!\d)")
DATE = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
EXT = re.compile(r"\.[A-Za-z0-9]{1,8}\Z")
STOP = {"n/a", "na", "tbd", "todo", "none", "-", "—", "–", "?", "and", "&", "+"}
TRIM = " \t\"'()[]<>:;"


# ------------------------------------------------------------------------------- the manifest


def split_row(line):
    """A table line's cells, stripped; `\\|` is a literal pipe."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur, i = [], [], 0
    while i < len(s):
        if s[i] == "\\" and s[i + 1:i + 2] == "|":
            cur.append("|")
            i += 2
            continue
        if s[i] == "|":
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(s[i])
        i += 1
    cells.append("".join(cur).strip())
    return cells


def _is_separator(line):
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-+:?", c) for c in cells)


def read_tables(text):
    """[(header cells, [(line number, cells, raw line)])] for every table outside code fences."""
    lines = text.splitlines()
    tables, fence, i = [], None, 0
    while i < len(lines):
        m = re.match(r"\s*(`{3,}|~{3,})", lines[i])
        if m:
            mark = m.group(1)[0] * 3
            fence = mark if fence is None else (None if fence == mark else fence)
            i += 1
            continue
        if fence is None and lines[i].lstrip().startswith("|") and i + 1 < len(lines) \
                and _is_separator(lines[i + 1]):
            header, rows, j = split_row(lines[i]), [], i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append((j + 1, split_row(lines[j]), lines[j]))
                j += 1
            tables.append((header, rows))
            i = j
            continue
        i += 1
    return tables


def plain(text):
    """A cell without its Markdown: strike, bold, code and line-break marks."""
    text = BR.sub(" ", text)
    return re.sub(r"~~|\*\*|__|`", "", text).strip()


def columns(header):
    """field -> column index, by the HEADERS patterns; the first column claiming a field wins. An
    `Asset` column is the path column only in a table that has no Path, File or Filename column."""
    out = {}
    for i, cell in enumerate(header):
        text = plain(cell)
        for field, pattern in HEADERS:
            if pattern.search(text):
                out.setdefault(field, i)
                break
    asset = out.pop("asset", None)
    if "path" not in out and asset is not None:
        out["path"] = asset
    return out


def said(pattern, text):
    """Whether `pattern` occurs in `text` without a "not" / "never" / 不是 in front of it."""
    return any(not NEGATED.search(text[:m.start()]) for m in pattern.finditer(text))


def kind_of(text):
    """The ledger kind a type cell or a path names, or None."""
    for kind, pattern in KIND_WORDS:
        if pattern.search(text):
            return kind
    return None


def guess_kind(path):
    """The kind a path suggests: its extension (`name@Clip.fbx` is a clip), then its words."""
    p = path.replace("\\", "/").lower()
    name = p.rsplit("/", 1)[-1]
    ext = os.path.splitext(name)[1]
    if ext == ".fbx" and "@" in name:
        return "clip"
    if ext in EXT_KIND:
        return EXT_KIND[ext]
    return kind_of(re.sub(r"[/_.\-@]+", " ", p))


def row_status(raw, status_cell, has_status):
    """unused / rejected / superseded from a bold marker anywhere in the row, or a plain word in
    the status cell; None for a live row."""
    for m in BOLD.finditer(raw):
        if NEGATED.search(raw[:m.start()]):              # not **unused**
            continue
        for status, pattern in STATUS_WORDS:
            if said(pattern, m.group(2)):
                return status
    if has_status:
        text = plain(status_cell)
        for status, pattern in STATUS_WORDS:
            if said(pattern, text):
                return status
    return None


def row_date(cell):
    m = DATE.search(plain(cell))
    if m:
        try:
            return datetime.date(*(int(g) for g in m.groups())).isoformat()
        except ValueError:
            pass
    return None


def row_version(cell):
    m = re.search(r"\d+", plain(cell))
    return int(m.group()) if m else None


# --------------------------------------------------------------------------- the path cell


def _split(s, a, b, sep):
    """(start, end) ranges of s[a:b] between separators that are outside braces."""
    out, start = [], a
    for m in sep.finditer(s, a, b):
        if s.count("{", a, m.start()) > s.count("}", a, m.start()):
            continue
        if m.start() > start:
            out.append((start, m.start()))
        start = m.end()
    if b > start:
        out.append((start, b))
    return out


def _pathlike(tok):
    if not tok or tok.lower() in STOP or "://" in tok:
        return False
    first = expand(tok, cap=1)[0]
    if re.fullmatch(r"[\d./\-]+", first):           # a date or a number
        return False
    return "/" in first or "*" in first or bool(EXT.search(first))


def tokens(cell):
    """[(token, struck)] for the path-like tokens of a path cell, in order.

    `~~` marks a struck span; `<br>`, `+`, commas (outside braces), `;` and whitespace separate
    paths, and inside backticks whitespace does not (`` `Art Dir/x.png` `` is one path) but
    ` and ` does. A Markdown link stands for its target."""
    cell = LINK.sub(lambda m: m.group(1), cell)
    cell = BR.sub(lambda m: " " * len(m.group()), cell)
    chars, mask, struck, i = [], [], False, 0
    while i < len(cell):
        if cell.startswith("~~", i):
            struck = not struck
            i += 2
            continue
        if cell.startswith("**", i) and cell[i - 1:i] not in ("/", "*") \
                and cell[i + 2:i + 3] not in ("/", "*"):
            i += 2                                   # bold, not a `**/` recursive glob
            continue
        chars.append(cell[i])
        mask.append(struck)
        i += 1
    s = "".join(chars)
    ranges, pos = [], 0
    for m in re.finditer(r"`([^`]*)`", s):
        ranges += _split(s, pos, m.start(), PLAIN_SEP)
        ranges += _split(s, m.start(1), m.end(1), QUOTED_SEP)
        pos = m.end()
    ranges += _split(s, pos, len(s), PLAIN_SEP)
    out = []
    for a, b in ranges:
        tok = s[a:b].strip(TRIM).rstrip(".")
        while tok.startswith("./"):
            tok = tok[2:]
        if _pathlike(tok):
            out.append((tok, any(mask[a:b])))
    return out


def _numbers(a, b, cut=None):
    lo, hi = int(a), int(b)
    step = 1 if hi >= lo else -1
    width = len(a) if (len(a) == len(b) or (a.startswith("0") and len(a) > 1)) else 0
    count = abs(hi - lo) + 1
    if count > EXPAND_CAP:
        count = EXPAND_CAP
        if cut is not None:
            cut.append(abs(hi - lo) + 1)
    return [str(lo + k * step).zfill(width) for k in range(count)]


def expand(tok, cap=EXPAND_CAP, cut=None):
    """`a_{x,y}.png`, `a_{1..3}.png` and `a_1..3.png` into every name they stand for, in order.
    At most `cap` names; when a range or the whole is cut short, `cut` (a list) is told."""
    out, todo = [], [tok]
    while todo and len(out) < cap:
        t = todo.pop(0)
        m = BRACE.search(t)
        if m:
            r = re.fullmatch(r"\s*(\d+)\.\.(\d+)\s*", m.group(1))
            opts = _numbers(*r.groups(), cut) if r else [o.strip() for o in m.group(1).split(",")]
            todo[0:0] = [t[:m.start()] + o + t[m.end():] for o in opts]
            continue
        m = RANGE.search(t)
        if m:
            todo[0:0] = [t[:m.start()] + n + t[m.end():] for n in _numbers(*m.groups(), cut)]
            continue
        out.append(t)
    if todo and cut is not None and cap == EXPAND_CAP:
        cut.append(len(out) + len(todo))
    return out


# ------------------------------------------------------------------------------- resolving


class Resolver:
    """Names from the manifest -> project-root-relative paths, read against ArtDirection/ first,
    then the project root. Paths take the case the disk has."""

    def __init__(self, root):
        self.root = root
        self.art = os.path.join(root, ART_DIR)
        self._names = {}
        self._hashes = {}

    def names(self, d):
        if d not in self._names:
            try:
                self._names[d] = set(os.listdir(d))
            except OSError:
                self._names[d] = set()
        return self._names[d]

    def true_case(self, rel):
        cur, out = self.root, []
        for part in rel.split("/"):
            names = self.names(cur)
            if part not in names:
                want = unicodedata.normalize("NFC", part).lower()
                hits = [n for n in names if unicodedata.normalize("NFC", n).lower() == want]
                if len(hits) == 1:
                    part = hits[0]
            out.append(part)
            cur = os.path.join(cur, part)
        return "/".join(out)

    def rel(self, full):
        """The ledger path of `full`, or None when it is outside the root or not a ledger path."""
        try:
            rel = L.rel_posix(full, self.root)
        except ValueError:
            return None
        return None if L.path_problem(rel) else self.true_case(rel)

    @staticmethod
    def wanted(full):
        name = os.path.basename(full)
        return os.path.isfile(full) and not name.startswith(".") and not name.endswith(".meta")

    def resolve(self, name):
        """[(path or None, on disk)] for one expanded name: one entry, or every file of a glob.
        None: outside the project, or a glob that matched nothing. A folder is ("dir", None): it is
        not taken whole; `folder/*` takes every file in it."""
        c = name.replace("\\", "/")
        while c.startswith("./"):
            c = c[2:]
        absolute = os.path.isabs(c)
        bases = (self.root,) if absolute else (self.art, self.root)
        if "*" in c:
            for base in bases:
                pattern = c if absolute else os.path.join(glob.escape(base), *c.split("/"))
                hits = sorted(h for h in glob.glob(pattern, recursive=True) if self.wanted(h))
                if hits:
                    return [(self.rel(h), True) for h in hits]
            return [(None, False)]
        for base in bases:
            full = os.path.normpath(c if absolute else os.path.join(base, *c.split("/")))
            if os.path.isfile(full):
                return [(self.rel(full), True)]
            if os.path.isdir(full):
                return [("dir", None)]
        if absolute:
            return [(self.rel(c), False)]
        first = c.split("/", 1)[0]
        if os.path.isdir(os.path.join(self.art, first)):
            rel = ART_DIR + "/" + c
        elif first == ART_DIR or os.path.isdir(os.path.join(self.root, first)):
            rel = c
        else:
            rel = ART_DIR + "/" + c
        rel = posixpath.normpath(rel)
        return [(None if L.path_problem(rel) else self.true_case(rel), False)]

    def entry(self, rel, on_disk):
        if not on_disk:
            return {"path": rel, "missing": True}
        if rel not in self._hashes:
            full = os.path.join(self.root, *rel.split("/"))
            self._hashes[rel] = (L.sha256_file(full), os.path.getsize(full))
        sha, size = self._hashes[rel]
        if rel.lower().endswith(".blend"):
            # a working file: the artist saves it again, which is a moved-on warning, not a change
            # after approval; its hash still names the version this row recorded
            return {"path": rel, "role": "source", "mutable": True, "sha256": sha, "bytes": size}
        return {"path": rel, "sha256": sha, "bytes": size}

    def existing(self, cell):
        """The on-disk paths a cell names (an anchor or prompt cell)."""
        out = []
        for tok, _ in tokens(cell):
            for name in expand(tok):
                for rel, on_disk in self.resolve(name):
                    if rel and on_disk and rel not in out:
                        out.append(rel)
        return out


# ------------------------------------------------------------------------------- composing


def _id_for(first, paths, taken, line):
    try:
        base = L.slugify(first)
    except ValueError:
        base = f"manifest/line-{line}"
    ext = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(first)[1].lower()).strip("-")
    options = [base] + ([f"{base}-{ext}"] if ext else []) + [f"{base}-{k}" for k in range(2, 10000)]
    for ident in options:
        if ident not in taken or taken[ident] & paths:
            return ident
    raise ValueError(f"no free id near {base}")


def _resolve_row(res, cell, stats, flags, line):
    """(live, struck) file entries of one path cell."""
    live, struck, seen = [], [], set()
    for tok, is_struck in tokens(cell):
        cut = []
        names = expand(tok, cut=cut)
        if cut:
            flags["capped"].append(line)
        for name in names:
            for rel, on_disk in res.resolve(name):
                if rel == "dir":
                    flags["folders"].append(line)
                    continue
                if rel is not None and L.path_key(rel) in seen:
                    continue
                stats["files"] += 1
                if rel is None:
                    stats["unresolved"] += 1
                    stats["unrecordable"] += 1
                    continue
                seen.add(L.path_key(rel))
                stats["resolved" if on_disk else "unresolved"] += 1
                (struck if is_struck else live).append(res.entry(rel, on_disk))
    return live, struck


def compose(tables, res, note_name, stats, flags):
    """One record per row (two when a cell strikes some paths and not others), in manifest
    order; each carries `_line`, `_anchors` and `_live` until it is written. A struck path that a
    row names unstruck anywhere in the manifest is dropped from the struck record: the live row
    wins, and no struck row can demote it."""
    rows_out = []
    for header, rows in tables:
        cols = columns(header)
        if "path" not in cols:
            stats["tables_skipped"] += 1
            continue
        stats["tables"] += 1
        for line, cells, raw in rows:
            stats["rows"] += 1

            def get(field, cells=cells, cols=cols):
                i = cols.get(field)
                return cells[i] if i is not None and i < len(cells) else ""

            live, struck = _resolve_row(res, get("path"), stats, flags, line)
            rows_out.append((line, raw, get, "status" in cols, live, struck))
    live_paths = {L.path_key(f["path"]) for row in rows_out for f in row[4]}

    records = []
    for line, raw, get, has_status, live, struck in rows_out:
        kept = [f for f in struck if L.path_key(f["path"]) not in live_paths]
        stats["struck_live"] += len(struck) - len(kept)
        struck = kept
        if not (live or struck):
            stats["rows_without_path"] += 1
            continue
        if struck:
            stats["struck_rows"] += 1
        kind = kind_of(plain(get("type")))
        ts = row_date(get("date")) or L.now_utc()
        version = row_version(get("version")) if plain(get("version")) else None
        prompt = res.existing(get("prompt"))[:1]
        anchors = res.existing(get("anchor"))
        marker = row_status(raw, get("status"), has_status)
        groups = []
        if live:
            groups.append((live, marker or "approved"))
        if struck:
            groups.append((struck, "superseded"))
        for files, status in groups:
            rec = {"schema": L.SCHEMA, "ts": ts,
                   "kind": kind or guess_kind(files[0]["path"]) or "other",
                   "status": status, "source": "unknown", "files": files,
                   "tool": dict(TOOL), "note": f"{note_name}:{line}",
                   "_line": line, "_anchors": anchors, "_live": status in LIVE,
                   "_struck": files is struck}
            if version is not None:
                rec["links"] = [{"rel": "made-under", "to": L.ART_DIRECTION, "rev": version}]
            if prompt:
                rec["params"] = {"prompt_file": prompt[0],
                                 "prompt_sha256": res.entry(prompt[0], True)["sha256"]}
            if anchors:
                rec["inputs"] = [{"path": p, "sha256": res.entry(p, True)["sha256"]}
                                 for p in anchors]
            records.append(rec)
        if live and struck:
            records[-1]["_superseded_by"] = records[-2]
    return records


def assign_ids(records, taken):
    """Ids in manifest order. A record whose first file's id is taken by other files gets the
    extension, then a number, appended; one that shares a file with it is a revision of it."""
    for rec in records:
        paths = {L.path_key(f["path"]) for f in rec["files"]}
        rec["id"] = _id_for(rec["files"][0]["path"], paths, taken, rec["_line"])
        taken.setdefault(rec["id"], set()).update(paths)
    for rec in records:
        target = rec.pop("_superseded_by", None)
        if target is not None and target["id"] != rec["id"]:
            rec["superseded_by"] = target["id"]


def link_parents(records, owners):
    """parent: the ids of the records (this run's, then the ledger's) holding the anchor files."""
    for rec in sorted(records, key=lambda r: not r["_live"]):
        for f in rec["files"]:
            owners.setdefault(L.path_key(f["path"]), rec["id"])
    for rec in records:
        parents = []
        for p in rec["_anchors"]:
            ident = owners.get(L.path_key(p))
            if ident and ident != rec["id"] and ident not in parents:
                parents.append(ident)
        if parents:
            rec["parent"] = parents


def public(rec):
    return {k: v for k, v in rec.items() if not k.startswith("_")}


# ------------------------------------------------------------------------------------ command


def _inside(path, root):
    try:
        L.rel_posix(path, root)
        return True
    except ValueError:
        return os.path.realpath(path) == os.path.realpath(root)


def cmd_adopt(ctx, args, rep):
    R = sys.modules[type(ctx).__module__]
    m = args.manifest.replace("\\", "/")
    manifest = m if os.path.isabs(m) else os.path.join(ctx.root, *m.split("/"))
    try:
        mdisp = L.rel_posix(manifest, ctx.root)
    except ValueError:
        mdisp = args.manifest
    note_name = os.path.basename(manifest)
    mode = "dry run" if args.dry_run else "write"

    out = None
    if args.out is not None:
        if not args.dry_run:
            rep.error(args.out, "usage", "--out goes with --dry-run; --write appends to the ledger")
            rep.summary("ERROR", args.out, "nothing read")
            return R.HARNESS
        out = os.path.abspath(args.out)
        if _inside(out, ctx.root) or os.path.realpath(out) == os.path.realpath(ctx.ledger):
            rep.error(args.out, "usage", "a dry run writes nothing inside the project: put --out "
                      "outside --root")
            rep.summary("ERROR", args.out, "nothing read")
            return R.HARNESS

    try:
        with open(manifest, encoding="utf-8-sig") as fh:          # read-only, never written
            text = fh.read()
    except (OSError, UnicodeDecodeError) as e:
        rep.error(mdisp, "no-manifest", f"cannot read it ({e.__class__.__name__})")
        rep.summary("ERROR", mdisp, "nothing adopted")
        return R.HARNESS

    stats = {k: 0 for k in ("tables", "tables_skipped", "rows", "rows_without_path", "files",
                            "resolved", "unresolved", "unrecordable", "struck_rows",
                            "struck_live")}
    flags = {"capped": [], "folders": []}
    res = Resolver(ctx.root)
    records = compose(read_tables(text), res, note_name, stats, flags)
    stats["capped"], stats["folders"] = len(set(flags["capped"])), len(set(flags["folders"]))
    if not stats["tables"]:
        rep.error(mdisp, "no-table", "no Markdown table with a path column (path, file, 路徑)")
        rep.data["stats"] = stats
        rep.summary("ERROR", mdisp, "nothing adopted")
        return R.HARNESS

    ledger_recs = []
    if args.write:                                   # a dry run never opens the ledger
        lines, ok = R.read_ledger(ctx, rep, must_exist=False)
        if not ok:
            rep.summary("ERROR", ctx.disp, "nothing adopted: the ledger is unreadable")
            return R.HARNESS
        ledger_recs = [r for _, r in lines]
    current = L.last_by_id(ledger_recs)
    # a struck path that a live ledger record (candidate or approved) holds is dropped, as one a
    # live row names is: no struck row demotes it
    ledger_live = {L.path_key(f["path"]) for r in current.values() if r.get("status") in R.LIVE
                   for f in R.files_of(r)}
    kept_records = []
    for rec in records:
        if rec.get("_struck"):
            files = [f for f in rec["files"] if L.path_key(f["path"]) not in ledger_live]
            stats["struck_live"] += len(rec["files"]) - len(files)
            if not files:
                continue
            rec["files"] = files
        kept_records.append(rec)
    records[:] = kept_records
    held = {ident: {L.path_key(f["path"]) for f in R.files_of(r)} for ident, r in current.items()}
    taken = {ident: set(paths) for ident, paths in held.items()}
    assign_ids(records, taken)
    owners = {}
    for ident, rec in current.items():
        for f in R.files_of(rec):
            owners.setdefault(L.path_key(f["path"]), ident)
    link_parents(records, owners)

    # an orphan is a file under ArtDirection/ that no row names in any column
    referenced = {mdisp} if L.path_problem(mdisp) is None else set()
    for r in records:
        referenced.update(r["_anchors"])
        if "params" in r:
            referenced.add(r["params"]["prompt_file"])
    named = [public(r) for r in records] + ledger_recs + \
        [{"files": [{"path": p} for p in sorted(referenced)]}]
    orphans = R.find_orphans(ctx, named)
    if args.include_orphans:
        for rel in orphans:
            files = [res.entry(rel, True)]
            records.append({"schema": L.SCHEMA, "ts": L.now_utc(),
                            "kind": guess_kind(rel) or "other", "status": "candidate",
                            "source": "unknown", "files": files, "tool": dict(TOOL),
                            "note": f"orphan: no row of {note_name} names it",
                            "id": _id_for(rel, {rel}, taken, 0), "_line": 0, "_anchors": [],
                            "_live": False, "_orphan": True})
            taken.setdefault(records[-1]["id"], set()).add(L.path_key(rel))

    skipped = 0
    keep = []
    for rec in records:
        if rec["id"] in held and held[rec["id"]] & {L.path_key(f["path"]) for f in rec["files"]}:
            skipped += 1                             # adopted or recorded before: left alone
            continue
        keep.append(rec)
    # superseded, unused and rejected rows first, so a live row sharing their id is current
    order = sorted(keep, key=lambda r: (r.get("_orphan", False), r["_live"]))
    revs = {}
    valid, final = 0, []
    for rec in order:
        revs[rec["id"]] = revs.get(rec["id"], L.last_rev(ledger_recs, rec["id"])) + 1
        row = public(rec)
        row["rev"] = revs[rec["id"]]
        errs = L.validate(row)
        if errs:
            fields = sorted({e.split(":", 1)[0] for e in errs})
            where = f"{mdisp}:{rec['_line']}" if rec["_line"] else ART_DIR + "/"
            rep.error(where, "schema", "the record would break the schema in: " + ", ".join(fields))
            continue
        valid += 1
        final.append(row)

    # what the ledger would hold afterwards: no circle, no file held by two assets
    after = dict(current)
    lines_of = {}
    for rec in order:
        after[rec["id"]] = public(rec)
        lines_of.setdefault(rec["id"], set()).add(rec["_line"])
    adopted = set(lines_of)
    blocked = 0
    for rule, ring in R.check_graph(ctx, R.Report(), after):
        ids = [i for i in ring if i in adopted]
        if not ids:
            continue
        rows = sorted(n for i in ids for n in lines_of[i] if n)
        blocked += 1
        who = "rows" if len(ids) == len(set(ring)) else "a row and a ledger record"
        what = {"parent-cycle": f"{who} whose anchors are each other's files",
                "superseded-cycle": f"{who} that supersede each other",
                "dual-owner": f"{who} that hold one file as two assets"}[rule]
        rep.error(f"{mdisp}:{','.join(map(str, rows)) or '-'}", rule,
                  f"{what}; make one of them the only one")
    stats["blocked"] = blocked

    by_status = {}
    for r in final:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    total = len(order)
    stats.update(records=total, by_status=by_status, orphans=len(orphans),
                 orphans_recorded=sum(1 for r in final if r["status"] == "candidate"),
                 skipped_existing=skipped, schema_valid=valid,
                 schema_ratio=round(valid / total, 4) if total else 1.0)
    rep.data.update(mode=mode, stats=stats)

    rep.ok(mdisp, f"{stats['tables']} table(s) with a path column ({stats['tables_skipped']} "
           f"other table(s) skipped), {stats['rows']} row(s), {stats['rows_without_path']} "
           "naming no file")
    rep.ok(mdisp, f"{stats['files']} file name(s) after expansion: {stats['resolved']} on disk, "
           f"{stats['unresolved']} not")
    if flags["folders"]:
        rep.warn(f"{mdisp}:{','.join(map(str, sorted(set(flags['folders']))))}", "folder-cell",
                 f"{len(flags['folders'])} name(s) are folders, not taken whole; write "
                 "`folder/*` for every file in one")
    if flags["capped"]:
        rep.warn(f"{mdisp}:{','.join(map(str, sorted(set(flags['capped']))))}", "range-capped",
                 f"a range or brace list stops at {EXPAND_CAP} names; the rest were not read")
    if stats["struck_live"]:
        rep.ok(mdisp, f"{stats['struck_live']} struck name(s) are live in another row; "
               "the live row holds them")
    if stats["unresolved"]:
        rep.warn(mdisp, "unresolved", f"{stats['unresolved'] - stats['unrecordable']} recorded "
                 f"with missing: true, {stats['unrecordable']} not recordable (outside the "
                 "project, or a glob that matched nothing)")
    statuses = ", ".join(f"{n} {s}" for s, n in sorted(by_status.items())) or "none"
    rep.ok(mdisp, f"{total} record(s): {statuses}; {stats['struck_rows']} row(s) with struck paths"
           + (f"; {skipped} already in the ledger, skipped" if skipped else ""))
    if orphans:
        rep.warn(ART_DIR + "/", "orphans", f"{len(orphans)} file(s) under ArtDirection/ are in no "
                 "row" + ("; recorded as candidates" if args.include_orphans
                          else "; --include-orphans records them as candidates"))
    pct = f"{100 * valid / total:.0f}%" if total else "-"
    rep.ok(mdisp, f"schema-valid {valid} of {total} ({pct})")

    if args.dry_run:
        if out is not None:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".adopt-", dir=os.path.dirname(out))
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.writelines(L.dumps(r) + "\n" for r in final)
            os.replace(tmp, out)
        where = f"{len(final)} record(s) in {args.out}" if out else "no --out, nothing written"
        if blocked:
            rep.summary("ERROR", mdisp, f"dry run: {blocked} problem(s) between rows; {where}; "
                        "the ledger was not opened")
            return R.FAILED
        if valid < total:
            rep.summary("ERROR", mdisp, f"dry run: {total - valid} record(s) would be refused; "
                        f"{where}; the ledger was not opened")
            return R.FAILED
        rep.summary("OK", mdisp, f"dry run: {where}; the ledger was not opened")
        return R.OK

    if valid < total or blocked:
        rep.summary("ERROR", ctx.disp, f"nothing written: {total - valid} record(s) would break "
                    f"the schema, {blocked} problem(s) between rows")
        return R.FAILED
    os.makedirs(os.path.dirname(ctx.ledger), exist_ok=True)
    for row in final:
        R.append(ctx, rep, row, assign_rev=True)
    rep.summary("OK", ctx.disp, f"adopted {len(final)} record(s)"
                + (f"; {skipped} already there" if skipped else ""))
    return R.OK


def register(sub, common, machine, commands):
    """Add the `adopt` subcommand to registry.py's parser and command table."""
    p = sub.add_parser("adopt", parents=[common, machine],
                       help="read manifest.md once into records (dry run first)")
    p.add_argument("--manifest", default=ART_DIR + "/manifest.md",
                   help="relative to --root (default: ArtDirection/manifest.md); never written")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="counts only; the ledger is never opened")
    mode.add_argument("--write", action="store_true", help="append the records to the ledger")
    p.add_argument("--out", metavar="FILE",
                   help="with --dry-run: write the records here, a scratch ledger outside --root")
    p.add_argument("--include-orphans", action="store_true",
                   help="files under ArtDirection/ that no row names become candidate records")
    commands["adopt"] = cmd_adopt


# ------------------------------------------------------------------------------------ selftest

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# What fixtures/manifest_courier.md adopts to over the tree fixtures/make_tree.py builds.
EXPECTED = {
    "artdirection/anchors/master": "approved",
    "artdirection/anchors/runner": "approved",
    "artdirection/anchors/runner-v1": "superseded",
    "artdirection/sheets/runner-run": "approved",
    "artdirection/frames/runner-run/run-1": "approved",
    "artdirection/turnarounds/mallet-front": "approved",
    "artdirection/sheets/runner-run-v1": "superseded",
    "artdirection/previews/runner-run": "unused",
    "artdirection/sheets/runner-jump": "approved",
    "assets/models/heroprop/mallet/mallet": "approved",
    "artdirection/sources/runner-rig-v1": "superseded",
    "assets/models/character/runner/runner-gatelatchswing": "approved",
    "assets/models/character/runner/runner": "approved",
}
ORPHAN = "artdirection/sheets/runner-wave"


def _registry():
    """registry.py's module: the one running (it may be __main__), else imported now."""
    for name in ("registry", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "cmd_record") and hasattr(mod, "Ctx"):
            return mod
    import registry
    return registry


def _stamp(path):
    with open(path, "rb") as fh:
        return fh.read(), os.stat(path).st_mtime_ns


@contextlib.contextmanager
def _opened():
    """Every path open() or os.open() is given while the block runs."""
    seen, real_open, real_os_open = [], builtins.open, os.open

    def spy_open(file, *a, **k):
        if isinstance(file, (str, bytes, os.PathLike)):
            seen.append(os.path.realpath(os.fsdecode(file)))
        return real_open(file, *a, **k)

    def spy_os_open(path, *a, **k):
        seen.append(os.path.realpath(os.fsdecode(path)))
        return real_os_open(path, *a, **k)

    builtins.open, os.open = spy_open, spy_os_open
    try:
        yield seen
    finally:
        builtins.open, os.open = real_open, real_os_open


def _adopt(R, root, ledger, *flags):
    code, out = R._run("adopt", "--root", root, "--ledger", ledger, "--json", *flags)
    return code, json.loads(out) if out.strip().startswith("{") else {"raw": out}


def selftest(d):
    """The adopt cases; raises AssertionError on the first failure."""
    R = _registry()
    assert [t for t, _ in tokens("`a/x_{1, 2}.png` + b/y.png<br>c/z.png and d/w.png, e/v.png TBD")] \
        == ["a/x_{1, 2}.png", "b/y.png", "c/z.png", "d/w.png", "e/v.png"]
    assert tokens("~~`a/old.png`~~ `a/new.png`") == [("a/old.png", True), ("a/new.png", False)]
    assert expand("a/x_{1, 2}.png") == ["a/x_1.png", "a/x_2.png"]
    assert expand("run_08..10.png") == ["run_08.png", "run_09.png", "run_10.png"]
    assert row_status("| x | **unused** |", "", False) == "unused"
    assert row_status("| x | not **unused** |", "", False) is None
    assert row_status("| x | 已歸檔 |", "已歸檔", True) == "superseded"

    work = os.path.join(d, "adopt")
    os.makedirs(work)
    subprocess.run([sys.executable, "-I", os.path.join(FIXTURES, "make_tree.py"), work],
                   check=True, capture_output=True)
    root = os.path.join(work, "tree")
    manifest = os.path.join(root, ART_DIR, "manifest.md")
    ledger = os.path.join(root, ART_DIR, "assets.jsonl")
    before = _stamp(manifest)

    # 1. a dry run: the counts, the records in --out, and no ledger created
    out = os.path.join(work, "dry.jsonl")
    code, data = _adopt(R, root, ledger, "--dry-run", "--out", out)
    assert code == 0, data
    st = data["stats"]
    want = {"tables": 2, "tables_skipped": 1, "rows": 13, "rows_without_path": 1, "files": 24,
            "resolved": 23, "unresolved": 1, "struck_rows": 2, "records": 13, "orphans": 1,
            "schema_valid": 13, "schema_ratio": 1.0}
    assert {k: st[k] for k in want} == want, st
    assert st["by_status"] == {"approved": 9, "superseded": 3, "unused": 1}, st
    assert not os.path.exists(ledger), "a dry run created the ledger"
    recs = L.load(out)
    assert sorted(r["id"] for r in recs) == sorted(EXPECTED), sorted(r["id"] for r in recs)
    cur = {r["id"]: r for r in recs}
    assert {i: r["status"] for i, r in cur.items()} == EXPECTED
    assert all(L.validate(r) == [] and r["rev"] == 1 for r in recs)
    assert all(r["tool"]["script"] == "registry.py adopt" for r in recs)
    assert cur["artdirection/sheets/runner-jump"]["files"] == \
        [{"path": "ArtDirection/sheets/runner_jump.png", "missing": True}]
    assert cur["artdirection/anchors/runner-v1"]["superseded_by"] == "artdirection/anchors/runner"
    assert len(cur["artdirection/frames/runner-run/run-1"]["files"]) == 6
    assert [f["path"] for f in cur["assets/models/character/runner/runner-gatelatchswing"]["files"]] \
        == ["Assets/Models/Character/Runner/Runner@GateLatchSwing.fbx",
            "Assets/Models/Character/Runner/Runner@Run.fbx"]
    assert [f["path"] for f in cur["assets/models/heroprop/mallet/mallet"]["files"]] == \
        ["Assets/Models/HeroProp/Mallet/Mallet.glb", "ArtDirection/raw/3d/Mallet/mallet_raw.glb"]
    sheet = cur["artdirection/sheets/runner-run"]
    assert sheet["parent"] == ["artdirection/anchors/master"] and R.made_under(sheet) == 2
    assert [f["path"] for f in sheet["files"]] == ["ArtDirection/sheets/runner_run.png",
                                                   "ArtDirection/sheets/runner_idle.png"]
    master = cur["artdirection/anchors/master"]
    with open(manifest, encoding="utf-8") as fh:
        line = next(n for n, t in enumerate(fh, 1) if "`anchors/master.png` | anchor" in t)
    assert master["ts"] == "2026-03-02" and master["note"] == f"manifest.md:{line}", master
    assert master["kind"] == "ref" and master["params"]["prompt_file"] == "ArtDirection/prompts/master.txt"
    assert R.made_under(cur["artdirection/sheets/runner-run-v1"]) == 1
    assert cur["artdirection/sources/runner-rig-v1"]["kind"] == "rig"
    assert ORPHAN not in cur
    code, text = R._run("check", "--root", root, "--ledger", out, "--json")
    rules = {i["rule"] for i in json.loads(text)["items"] if i["level"] == "ERROR"}
    assert code == 2 and rules == {"missing"}, (code, rules)

    # 2. a dry run beside an existing ledger never opens it; orphans become candidates
    sentinel = {"schema": 1, "id": ORPHAN, "rev": 1, "ts": "2026-03-01", "kind": "sheet",
                "status": "candidate", "source": "generated",
                "files": [{"path": "ArtDirection/sheets/runner_wave.png",
                           "sha256": L.sha256_file(os.path.join(root, ART_DIR, "sheets",
                                                                "runner_wave.png")), "bytes": 0}]}
    L.append(ledger, sentinel)
    held = _stamp(ledger)
    out2 = os.path.join(work, "dry-orphans.jsonl")
    with _opened() as seen:
        code, data = _adopt(R, root, ledger, "--dry-run", "--out", out2, "--include-orphans")
    assert code == 0, data
    assert os.path.realpath(ledger) not in seen, "the dry run opened the ledger"
    assert _stamp(ledger) == held, "the dry run changed the ledger"
    recs = {r["id"]: r for r in L.load(out2)}
    assert len(recs) == 14 and recs[ORPHAN]["status"] == "candidate", sorted(recs)

    # 3. --out inside the project is refused before anything is read
    inside = os.path.join(root, "adopt.jsonl")
    code, _ = _adopt(R, root, ledger, "--dry-run", "--out", inside)
    assert code == 3 and not os.path.exists(inside), code

    # 4. --write appends; the ledger already names the orphan, so it is not one
    code, data = _adopt(R, root, ledger, "--write", "--include-orphans")
    assert code == 0 and data["stats"]["orphans"] == 0, data
    lines = L.load(ledger)
    assert len(lines) == 14 and {r["id"] for r in lines[1:]} == set(EXPECTED), len(lines)
    code, text = R._run("check", "--root", root, "--ledger", ledger, "--json")
    rules = {i["rule"] for i in json.loads(text)["items"] if i["level"] == "ERROR"}
    assert code == 2 and rules == {"missing"}, (code, rules)

    # 5. adopting again writes nothing
    code, data = _adopt(R, root, ledger, "--write")
    assert code == 0 and data["stats"]["skipped_existing"] == 13, data
    assert len(L.load(ledger)) == 14

    # 6. the artist saves the working .blend: moved-on, never changed-after-approval
    blend = [f for r in lines for f in r["files"] if f["path"].endswith("/Runner.blend")]
    assert blend and all(f.get("mutable") is True and f.get("role") == "source" and f.get("sha256")
                         for f in blend), blend
    with open(os.path.join(root, ART_DIR, "sources", "Runner.blend"), "ab") as fh:
        fh.write(b"saved again")
    code, text = R._run("check", "--root", root, "--ledger", ledger, "--json")
    items = json.loads(text)["items"]
    rules = {i["rule"] for i in items if i["level"] == "ERROR"}
    assert code == 2 and rules == {"missing"}, (code, rules)
    assert any(i["rule"] == "moved-on" and i["level"] == "WARN" for i in items), items

    assert _stamp(manifest) == before, "manifest.md changed"
    _selftest_rows(R, os.path.join(d, "rows"))


def _mini(R, work, table, files):
    """Adopt one small manifest over `files`; (exit, stats, {id: record}, output)."""
    root = os.path.join(work, f"p{len(os.listdir(work)) if os.path.isdir(work) else 0}")
    for rel in files:
        full = os.path.join(root, ART_DIR, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(rel.encode("utf-8"))
    os.makedirs(os.path.join(root, ART_DIR), exist_ok=True)
    with open(os.path.join(root, ART_DIR, "manifest.md"), "w", encoding="utf-8") as fh:
        fh.write(table)
    out = os.path.join(work, os.path.basename(root) + ".jsonl")
    code, text = R._run("adopt", "--root", root, "--ledger", os.path.join(root, "x.jsonl"),
                        "--dry-run", "--out", out, "--json")
    data = json.loads(text)
    recs = L.last_by_id(L.load(out)) if os.path.exists(out) else {}
    return code, data, recs


def _selftest_rows(R, work):
    """Rows the courier manifest does not have: a struck row after the live one, header words,
    a negated status word, a folder cell, a capped range, rows that form a circle."""
    os.makedirs(work)
    head = "| Date | Path | Status |\n|---|---|---|\n"
    # a later struck row names the live file: the live row wins, the struck one keeps its own file
    code, data, recs = _mini(R, work, head + "| 2026-03-01 | `sheets/runner_run.png` | approved |\n"
                             "| 2026-03-02 | ~~`sheets/runner_v0.png`~~ ~~`sheets/runner_run.png`~~ "
                             "| |\n", ["sheets/runner_run.png", "sheets/runner_v0.png"])
    assert code == 0, data
    assert recs["artdirection/sheets/runner-run"]["status"] == "approved", recs
    assert [f["path"] for f in recs["artdirection/sheets/runner-v0"]["files"]] == \
        ["ArtDirection/sheets/runner_v0.png"] and data["stats"]["struck_live"] == 1, recs
    # Filename and Asset headers; "not unused" is not unused
    code, data, recs = _mini(R, work, "| Asset | Filename | Status |\n|---|---|---|\n"
                             "| Runner | `sheets/runner_run.png` | not unused |\n",
                             ["sheets/runner_run.png"])
    assert code == 0 and recs["artdirection/sheets/runner-run"]["status"] == "approved", recs
    code, data, recs = _mini(R, work, "| Asset | Notes |\n|---|---|\n"
                             "| `sheets/runner_run.png` | **unused** |\n", ["sheets/runner_run.png"])
    assert code == 0 and recs["artdirection/sheets/runner-run"]["status"] == "unused", recs
    # a folder is not taken whole; a range past the cap says so
    code, data, recs = _mini(R, work, head + "| 2026-03-01 | `frames/runner_run/` | approved |\n"
                             "| 2026-03-02 | frames/run_{1..20000}.png | approved |\n",
                             ["frames/runner_run/run_1.png"])
    items = {i["rule"] for i in data["items"]}
    assert code == 0 and {"folder-cell", "range-capped"} <= items, data
    assert data["stats"]["folders"] == 1 and data["stats"]["capped"] == 1, data["stats"]
    assert not any("runner_run/run_1" in str(r["files"]) for r in recs.values()), recs
    # two rows that supersede each other, and two rows whose anchors are each other: exit 2
    code, data, recs = _mini(R, work, head + "| 2026-03-01 | ~~`a/gate.png`~~ `a/latch.png` | |\n"
                             "| 2026-03-02 | ~~`a/latch_old.png`~~ `a/gate.png` | |\n",
                             ["a/gate.png", "a/latch.png", "a/latch_old.png"])
    assert code == 0, data                         # live rows win: gate is live, so not struck
    code, data, recs = _mini(R, work, "| Path | Anchor |\n|---|---|\n"
                             "| `a/gate.png` | `a/latch.png` |\n| `a/latch.png` | `a/gate.png` |\n",
                             ["a/gate.png", "a/latch.png"])
    rules = {i["rule"] for i in data["items"] if i["level"] == "ERROR"}
    assert code == 2 and rules == {"parent-cycle"}, (code, data)
    code, data, recs = _mini(R, work, "| Path |\n|---|\n| `a/gate.png` + `a/shared.png` |\n"
                             "| `a/latch.png` + `a/shared.png` |\n",
                             ["a/gate.png", "a/latch.png", "a/shared.png"])
    rules = {i["rule"] for i in data["items"] if i["level"] == "ERROR"}
    assert code == 2 and rules == {"dual-owner"}, (code, data)
    assert not any("shared" in i["path"] for i in data["items"]), "a path was printed"
    # over a ledger: a struck row naming a file an approved record holds drops that path, adopts
    # its other file, and is no dual-owner block
    root = os.path.join(work, "over-ledger")
    for rel in ("sheets/runner_run.png", "sheets/runner_v0.png"):
        os.makedirs(os.path.join(root, ART_DIR, "sheets"), exist_ok=True)
        with open(os.path.join(root, ART_DIR, *rel.split("/")), "wb") as fh:
            fh.write(rel.encode("utf-8"))
    ledger = os.path.join(root, ART_DIR, "assets.jsonl")
    part = os.path.join(work, "run.json")
    with open(part, "w", encoding="utf-8") as fh:
        json.dump({"files": ["ArtDirection/sheets/runner_run.png"]}, fh)
    code, text = R._run("record", "--root", root, "--ledger", ledger, "--json", part, "--kind",
                        "sheet", "--source", "generated", "--status", "approved")
    assert code == 0, text
    with open(os.path.join(root, ART_DIR, "manifest.md"), "w", encoding="utf-8") as fh:
        fh.write("| Path | Status |\n|---|---|\n"
                 "| ~~`sheets/runner_v0.png`~~ ~~`sheets/runner_run.png`~~ | |\n")
    code, text = R._run("adopt", "--root", root, "--ledger", ledger, "--write", "--json")
    data = json.loads(text)
    assert code == 0 and data["stats"]["struck_live"] == 1, data
    cur = L.last_by_id(L.load(ledger))
    assert cur["artdirection/sheets/runner-run"]["status"] == "approved", cur
    assert [f["path"] for f in cur["artdirection/sheets/runner-v0"]["files"]] == \
        ["ArtDirection/sheets/runner_v0.png"], cur


def _main(argv):
    if argv in (["selftest"], ["--selftest"]):
        import registry_ingest
        with tempfile.TemporaryDirectory(prefix="registry-adopt-") as d:
            for name, case in (("adopt", selftest), ("ingest", registry_ingest.selftest)):
                os.makedirs(os.path.join(d, name + "-case"))
                try:
                    case(os.path.join(d, name + "-case"))
                except Exception as e:                  # a failed assert, or anything it raised
                    print(f"ERROR selftest: {name}: {e.__class__.__name__}: {e}")
                    return 2
                print(f"OK selftest: {name}")
        return 0
    return _registry().main(["adopt", *argv])


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
