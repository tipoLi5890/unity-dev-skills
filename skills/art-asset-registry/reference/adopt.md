# Adopting a hand-written `manifest.md`

A project that has kept `ArtDirection/manifest.md` by hand and has no ledger reads it **once**
into records with `adopt`. The manifest stays as it is: `adopt` opens it read-only, and from then
on the ledger is the truth and the manifest the story (`reference/workflow.md` §8). Run every
command from the project root, or pass `--root`.

## The loop

```bash
python3 registry.py adopt --dry-run --out /tmp/adopt.jsonl          # counts; records to a scratch file
python3 registry.py check --ledger /tmp/adopt.jsonl                 # what the ledger would say
python3 registry.py adopt --write                                   # append them for real
python3 registry.py check
```

1. **Dry run first.** `--dry-run` never opens the project ledger and writes nothing inside
   `--root`; `--out FILE` must be outside it (inside, it is refused with exit 3). FILE is a
   complete scratch ledger, revs numbered, so `check --ledger FILE` reads it as it would the real
   one.
2. **Read the counts** (below), then the scratch ledger itself. A row that came out wrong is fixed
   in the manifest (a clearer path cell, a status word) and the dry run repeated.
3. **Write.** `--write` appends to the ledger (`--ledger`, `ART_LEDGER`, or
   `ArtDirection/assets.jsonl`), creating it when absent. Every record is validated first; if one
   would break the schema, or rows would form a circle or hold one file as two assets, nothing is
   written (exit 2).
4. **Check.** Drift the manifest never showed now has a rule name: `missing` for a live row whose
   file is gone, `orphan` for a file no row names. Fix them as `reference/workflow.md` §3 says.

Adopting again writes nothing new: an id the ledger already holds for the same files is skipped
(`skipped_existing`). Changes after adoption go through `record`, never a second adopt.

## What it reads

Every Markdown table outside a code fence whose header has a **path column**. Header cells are
matched loosely, and a column that matches nothing is ignored; a table with no path column (a
palette, a schedule) is skipped and counted.

| Field | Header words | Becomes |
|---|---|---|
| path | `path` `file` `filename` `路徑` `檔案` `檔名`; `asset` `資產` only in a table with none of those | `files[]` |
| type | `type` `kind` `類型` | `kind` (`anchor` and `turnaround` are `ref`, `model` and `模型` are `mesh`, `動作` is `clip`, `骨架` is `rig` …); without one, the path's extension and folder words decide; else `other` |
| date | `date` `日期` | `ts` as `YYYY-MM-DD`; none, the time of the adopt |
| version | `version` `規格版本` `版本` | the link `made-under art:direction` with `rev` the first integer (`v2` is 2) |
| prompt | `prompt` | `params.prompt_file` and `prompt_sha256` when the cell names a file on disk; prompt text is never stored |
| status | `status` `狀態` | see the status rules |
| anchor | `anchor` | `inputs[]` with hashes, and `parent` when a row of the manifest (or a record) holds that file |

Every record also gets `source: unknown`, `tool: {skill: art-asset-registry, script: "registry.py
adopt"}` and `note: "manifest.md:<line>"`, the row it came from.

### The path cell

| Written | Means |
|---|---|
| `` `sheets/runner_run.png` `` | backticks are dropped; inside them a space is part of the path |
| `a.png + b.png`, `a.png<br>b.png`, `a.png and b.png`, `a.png, b.png` | several files of one asset |
| `sheets/runner_{run,idle}.png` | `runner_run.png` and `runner_idle.png` (a comma inside braces does not split) |
| `frames/runner_run/run_1..6.png`, `run_{01..12}.png` | a numbered range; a leading zero keeps the width; at most 10,000 names, and a longer one is cut there with a `range-capped` WARN |
| `Assets/Models/Character/Runner/Runner@*.fbx`, `frames/runner_run/*` | a glob; every match, sorted |
| `frames/runner_run/` | a folder: not taken whole, a `folder-cell` WARN with the line; write `frames/runner_run/*` |
| `[sheet](sheets/runner_run.png)` | a link stands for its target |
| `TBD`, `-`, `n/a`, words | no file: the row is counted and skipped |

Each name is looked up under `ArtDirection/` first, then at the project root, so
`sheets/runner_run.png` and `Assets/Models/HeroProp/Mallet/Mallet.glb` both resolve; the case on
disk wins over the case written. A name found nowhere is still recorded, with
`files[].missing: true`, under `ArtDirection/` unless its first folder exists at the root. A name
outside the project, or a glob that matches nothing, cannot be recorded and is only counted.

A `.blend` is a working file: it is recorded `role: source`, `mutable: true`, with the sha256 of
the bytes the row found. When the artist saves it again, `check` warns `moved-on`; it never fails
`changed-after-approval`.

### Status

| In the row | Status |
|---|---|
| the path struck, `~~sheets/runner_run_v1.png~~` | `superseded` |
| some paths struck and others not | two records: the live paths, and the struck ones `superseded` with `superseded_by` the live one |
| `**unused**` anywhere in the row, or `unused` / `未使用` in the status cell; `not unused`, `not **unused**`, `never unused`, `不是未使用` do not count | `unused` |
| `superseded`, `archived`, `已取代`, `已歸檔`, `封存` (bold anywhere, or in the status cell) | `superseded` |
| `rejected`, `已拒絕` (the same) | `rejected` |
| anything else: `approved`, `LOCKED`, `PENDING`, `已核准`, empty | `approved` |

A live row is `approved` because a row in the manifest was the approval the project had. From
here `check` holds those bytes: a later change to the file fails with `changed-after-approval`
until it is recorded again. A `PENDING` row that really waits on someone goes back to
`candidate` after the adopt: `record` its files again (a new revision, `candidate` by default).

**A live row wins.** A path struck in one row and named unstruck in another (or in the same
row) belongs to the live row: it is dropped from the struck record, and counted as
`struck_live`. So is a struck path that a candidate or approved record already in the ledger
holds (`--write` reads the ledger). Records are written superseded, unused and rejected first,
then live, so a live row sharing an id with an older one is current.

**Between rows.** Before anything is written, the records are read as the ledger would hold them:
rows whose anchors are each other's files (`parent-cycle`), or two rows that hold one file as two
assets (`dual-owner`), stop the adopt with exit 2 and the manifest line numbers. The message says
"a row and a ledger record" when the other holder is already in the ledger.

### Orphans

A file under `ArtDirection/` that no row names in any column (path, prompt, anchor) is an
orphan; `ArtDirection/raw/`, dot-files, `.meta` files, the ledger and the manifest are not
scanned. Orphans are counted and never written, unless `--include-orphans` records each as a
`candidate` with `source: unknown`. In write mode, a file the ledger already names is not an
orphan.

## Output: counts only

Nothing from the project is printed: no path, no cell, no id. The lines:

```text
OK ArtDirection/manifest.md: 2 table(s) with a path column (1 other table(s) skipped), 13 row(s), 1 naming no file
OK ArtDirection/manifest.md: 24 file name(s) after expansion: 23 on disk, 1 not
WARN ArtDirection/manifest.md:31: folder-cell: 1 name(s) are folders, not taken whole; write `folder/*` for every file in one
WARN ArtDirection/manifest.md: unresolved: 1 recorded with missing: true, 0 not recordable (…)
OK ArtDirection/manifest.md: 13 record(s): 9 approved, 3 superseded, 1 unused; 2 row(s) with struck paths
WARN ArtDirection/: orphans: 1 file(s) under ArtDirection/ are in no row; --include-orphans records them as candidates
OK ArtDirection/manifest.md: schema-valid 13 of 13 (100%)
OK ArtDirection/manifest.md: dry run: 13 record(s) in /tmp/adopt.jsonl; the ledger was not opened
```

`--json` prints one object with `mode` and `stats`: `tables`, `tables_skipped`, `rows`,
`rows_without_path`, `files`, `resolved`, `unresolved`, `unrecordable`, `struck_rows`,
`struck_live`, `folders`, `capped`, `records`, `by_status`, `orphans`, `orphans_recorded`,
`skipped_existing`, `schema_valid`, `schema_ratio`, `blocked`. A record that would break the
schema is reported by manifest line and field name only, a problem between rows by line numbers.

| Exit | When |
|---|---|
| 0 | every record is schema-valid; written (`--write`) or not (`--dry-run`) |
| 2 | a record would break the schema, or rows form a circle or hold one file twice: nothing written to the ledger |
| 3 | no manifest, no table with a path column, `--out` inside the project or with `--write`, an unreadable ledger |

The fixture `scripts/fixtures/manifest_courier.md` has the path-cell, status and orphan shapes
above, and the selftest (`registry.py selftest`, case `adopt-ingest`) adopts it over the tree
`scripts/fixtures/make_tree.py` builds; small manifests in the same case cover the header words,
a negated status, a folder cell, a capped range, a struck row after a live one, and the rows that
stop an adopt.
