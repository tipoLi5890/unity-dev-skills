# The ledger: `assets.jsonl`, schema 1

One JSON object per line, appended and never edited. Each line is one revision of one asset.
An id's **current record** is its last line, and `rev` counts that id's lines from 1 with no gap.
An asset's **current version** is its latest `approved` revision: a later candidate is a proposal,
and the approved revision before the current version with other bytes is the **previous good**
one, the rollback target (`registry.py history ID` marks both). When an id's last record is
`rejected`, `superseded` or `unused`, its approval is withdrawn: it has no current version
(`current_version: null`), and its last approved revision is marked previous good. Hashes pin content but are not
identity: an asset keeps its id when its bytes change or its file moves.

The ledger lives at `ArtDirection/assets.jsonl` unless `--ledger PATH` or `ART_LEDGER` names
another file. It belongs in git: `init` warns when git ignores it. `scripts/registry_ledger.py`
reads, validates and appends it, and any script in this skill's `scripts/` may import it.

## Fields

Readers accept keys they do not know; `check --strict` rejects them. An optional field set to
`null` counts as absent. NaN and Infinity are not JSON: a line holding one does not parse, and
nothing writes one.

| Field | Type | Req. | Meaning |
|---|---|---|---|
| `schema` | int | Y | `1` |
| `id` | str | Y | set once, from the first file's path, and never changed; see Ids |
| `rev` | int | Y | 1, 2, 3 … per id, in file order, no gap |
| `ts` | str | Y | RFC3339 UTC (`2026-03-14T09:26:53Z`); an adopted row may carry `YYYY-MM-DD` |
| `kind` | slug | Y | `[a-z][a-z0-9-]*`; the vocabulary below; another slug is allowed and `check --strict` warns |
| `class` | str | N | the 3D asset class, a row of the project's `3D asset classes` (e.g. `hero-prop`) |
| `status` | enum | Y | `candidate` `approved` `rejected` `superseded` `unused` `diagnostic` |
| `superseded_by` | id | N | the id that replaced this one |
| `parent` | [id] | N | lineage: a mesh to its turnaround, the turnaround to its anchor, a game mesh to its showcase mesh |
| `links` | array | N | `[{rel, to, rev?}]`; see Links |
| `files` | array | Y | at least one entry; see below |
| `tool` | object | N | `{skill, script, version}` of the producer |
| `params` | object | N | what the producer was given; reserved keys below |
| `inputs` | array | N | `[{path, sha256}]`: which version of each input made this asset |
| `gates` | array | N | `[{name, value, limit, pass}]`, the shape the Blender skills' gates already have |
| `warnings` | [str] | N | notes that do not decide anything ("rendered with alpha") |
| `verdict` | enum | N | `green` `failed` `harness` |
| `source` | enum | Y | `generated` `authored` `purchased` `third-party` `unknown` |
| `license` | str | when `source` is `purchased` or `third-party` | e.g. `purchased:<pack>`, `cc0` |
| `file` | object | N | `{path, saved, dirty, sha256, bytes}`: the Blender file the asset came out of, as it stood; `record` hashes it when it is on disk inside the project |
| `approver` | str | N | who looked, on an `approved` revision |
| `note` | str | N | one line for people |

### Vocabularies

| Word | Means |
|---|---|
| **kind** `sprite` `sheet` `frames` `preview` `ref` `texture` `mesh` `rig` `clip` `audio` | what the asset is (`ref` covers anchors, turnarounds, concept art) |
| **kind** `qa-sheet` | an image a decision rests on: a multi-view QA sheet, an animation contact sheet, a before/after pair, a preset comparison |
| **kind** `change` | a change record (`reference/workflow.md` §6) |
| **kind** `other` | anything else |
| **status** `candidate` | made, not yet judged |
| **status** `approved` | a person looked where it will be seen; the latest one is the current version |
| **status** `rejected` | looked at and turned down; kept so nobody makes it again unknowingly |
| **status** `superseded` | replaced, usually by `superseded_by` |
| **status** `unused` | kept, not in the game |
| **status** `diagnostic` | made to learn something (a raw shape decode, a downstream-only rerun, a preset made for comparison), never shipped; its files are not held to disk |
| **rel** `made-under` | the version of an outside spec it was made under: `art:direction` with `rev` = the `ART_DIRECTION.md` Version |
| **rel** `made-by` | the job that produced it: `job:<id>` |
| **rel** `evidence` | a recorded `qa-sheet` the status rests on |
| **rel** `explained-by` | the recorded change record behind this revision |
| **rel** `depends-on` | an upstream asset (a ledger id) whose content this one was made from |

Other words for a version map onto these: *current* and *previous good* are derived (above), a
*source* file is `role: source`, and a *diagnostic* run is the status of that name.

### Links

`to` is a ledger id, or `ns:key` for something outside the ledger: `art:direction`, `job:<id>`,
`flow:<node>`, `beat:<id>`. `rev` is the version linked to:

- **to a ledger id**, its **content rev**: the rev at which that id's file hashes last changed. A
  status change or a move is not new content. `record` fills it in when the link leaves it out.
- **to `ns:key`**, the outside version (`art:direction` rev 2 is Version 2). A link without `rev`
  is a reference and never stale.

A link is **stale** when its `rev` is behind the current value: the target's content rev now, or
the value given to `stale` (`--art-version N` is `--at art:direction=N`). With `--art-version`, a
record with no `made-under art:direction` link is stale too, since every asset was made under some
art direction. Links are not inherited: a new revision recorded without them has none.

### `files[]`

| Key | Meaning |
|---|---|
| `path` | relative to the project root, forward slashes; never absolute, never `..`; stored NFC unless only another form exists on disk |
| `role` | `source` (the original, e.g. an undecimated mesh, a working `.blend`) · `derived` · `shipped` (what the game loads) · `preview` · `ref` |
| `sha256`, `bytes` | the content when it was recorded; `record` computes both for every file, a working `.blend` included |
| `vendor` | `true`: purchased or third-party bytes that must stay out of git |
| `mutable` | `true`: expected to change (a working `.blend`); its recorded hash names the version that made this asset, and a later change is a warning, not an error |
| `missing` | `true`: not on disk when it was recorded |

### `params`

Reserved keys: `model` `seed` `prompt_sha256` `prompt_file` `workflow_sha256` `overrides`
`server_label` `argv`. Other keys are allowed. Two things are refused anywhere in `params`:

- **the prompt text**, as a key `prompt`. Keep the prompt in a file (`prompt_file`) and its hash
  (`prompt_sha256`);
- **a URL** (`scheme://`). Name the machine with `server_label` (`studio-gpu`), never its address.

## Ids and revisions

`record` takes the id from the first file's path: NFC, lower case, the last extension dropped,
every run of characters that are not letters or digits (in any script) becomes one `-`, `/` kept.
A name with no letter or digit left becomes the first 8 hex digits of the sha256 of its NFC path,
under its folder's id.

| Path | Id |
|---|---|
| `ArtDirection/sheets/Runner_Run.png` | `artdirection/sheets/runner-run` |
| `Assets/Models/HeroProp/Mallet/Mallet.glb` | `assets/models/heroprop/mallet/mallet` |
| `ArtDirection/角色/跑者.png` | `artdirection/角色/跑者` |
| `ArtDirection/角色/Café.png`, composed or decomposed | `artdirection/角色/café` |
| `ArtDirection/sheets/★.png` | `artdirection/sheets/<8 hex digits>` |

An id is valid when it is NFC, lower case, starts with a letter or digit and holds only letters,
digits, `/`, `.`, `_` and `-`. List the shipped file first, or pass `--id`, so that the id names
what the game loads.

Recording a path the ledger already holds adds a revision of the id that holds it (paths compare
NFC, so a decomposed spelling is the same file). A new path whose id is already taken by other
files (`runner_run.psd` beside `runner_run.png`) is refused until `--id` says which asset it is. A
file held by another id is refused (`dual-owner`). `mv` writes the same id at its new path.

Revisions are numbered inside an exclusive lock on the ledger, so producers can append at the
same time and every id's revs still run 1, 2, 3.

## Three records

Each is one line in the file; they are wrapped here to be read, and the hashes are shortened.

```json
{"schema": 1, "id": "artdirection/sheets/runner-run", "rev": 2, "ts": "2026-03-14T09:26:53Z",
 "kind": "sheet", "status": "approved", "source": "generated",
 "parent": ["artdirection/anchors/master"],
 "links": [{"rel": "made-under", "to": "art:direction", "rev": 2},
           {"rel": "evidence", "to": "artdirection/qa/runner-run", "rev": 1}],
 "files": [{"path": "ArtDirection/sheets/runner_run.png", "role": "shipped",
            "sha256": "9f2c…", "bytes": 412873}],
 "inputs": [{"path": "ArtDirection/anchors/master.png", "sha256": "41d0…"}],
 "tool": {"skill": "codex-visual", "script": "codex_generate.py"},
 "params": {"model": "<pinned model>", "prompt_file": "ArtDirection/prompts/runner_run.txt",
            "prompt_sha256": "c07e…"},
 "gates": [{"name": "frames.count", "value": 8, "limit": 8, "pass": true}],
 "verdict": "green", "approver": "lead", "note": "QA sheet at game scale"}

{"schema": 1, "id": "assets/models/character/runner/runner-gatelatchswing", "rev": 1,
 "ts": "2026-03-15T11:02:10Z", "kind": "clip", "status": "candidate", "source": "authored",
 "parent": ["assets/models/character/runner/runner"],
 "links": [{"rel": "made-under", "to": "art:direction", "rev": 2},
           {"rel": "made-by", "to": "job:retarget-0315"}],
 "files": [{"path": "Assets/Models/Character/Runner/Runner@GateLatchSwing.fbx", "role": "shipped", "sha256": "…", "bytes": 1840212},
           {"path": "ArtDirection/sources/Runner.blend", "role": "source", "mutable": true, "sha256": "…", "bytes": 48113920}],
 "file": {"path": "ArtDirection/sources/Runner.blend", "saved": true, "dirty": false, "sha256": "…", "bytes": 48113920},
 "tool": {"skill": "blender-retarget", "script": "brt_retarget"},
 "gates": [{"name": "clip.root_drift_m", "value": 0.004, "limit": 0.01, "pass": true}],
 "verdict": "green"}

{"schema": 1, "id": "artdirection/vendor/courier-pack/crate", "rev": 1, "ts": "2026-03-16T08:40:00Z",
 "kind": "mesh", "class": "env-prop", "status": "approved", "source": "purchased",
 "license": "purchased:courier-pack",
 "files": [{"path": "ArtDirection/vendor/courier_pack/crate.fbx", "role": "source", "vendor": true,
            "sha256": "…", "bytes": 220431}]}
```

## Check rules

`check` reads every line, then applies the rules below. **Current** means an id's last line;
**live** means a current record whose status is `candidate` or `approved`. Every finding names
its rule, so a fixture can expect a particular one.

| Rule | Level | When |
|---|---|---|
| `no-ledger` | ERROR, exit 3 | no ledger at the path |
| `corrupt-line` | ERROR, exit 3 | a line that is not UTF-8, not JSON (NaN included), or not an object, with a newline after it |
| `torn-line` | WARN | the last line has no newline and does not parse: a writer died mid-line, or one is still writing. It is skipped, and the next write moves it to `<ledger>.torn` |
| `schema` | ERROR | any line breaks the field table; with `--strict`, an unknown key |
| `vocabulary` | WARN, `--strict` only | a kind or a link rel outside the vocabulary |
| `rev-gap` | ERROR | an id's revs, in file order, are not 1, 2, 3 … (a gap, a repeat, a step back) |
| `missing` | ERROR | a live file is not on disk; WARN for a candidate whose file was recorded `missing` |
| `local-only` | WARN | a live file is not on disk, but git ignores its path (a raw or vendor file on another machine) |
| `not-a-file` | ERROR | the path is a directory |
| `recorded-missing` | WARN | recorded `missing`, on disk now: record it again to pin its hash |
| `no-hash` | WARN | a live file with no `sha256` |
| `hash-drift` | ERROR | a live candidate's file differs from its recorded bytes |
| `changed-after-approval` | ERROR | an approved file differs from its recorded bytes |
| `moved-on` | WARN | a live `mutable` file (a working `.blend`) differs from the version recorded |
| `verdict-failed` | ERROR | an approved record's verdict is `failed` |
| `verdict-harness` | WARN | an approved record's verdict is `harness`: its gates did not run |
| `failing-gate` | ERROR | an approved record has a gate with `pass: false` |
| `vendor-not-ignored` | ERROR | a current `vendor: true` file that git does not ignore, or tracks |
| `licensed-tracked` | WARN | a current `purchased` or `third-party` file (not vendor) that git tracks; ERROR with `--strict` |
| `unresolved-parent` | ERROR | a current record's `parent` names an id the ledger does not have, or itself |
| `unresolved-superseded-by` | ERROR | the same for `superseded_by` |
| `unresolved-link` | ERROR | a link's `to` is an id (no `:`) the ledger does not have |
| `parent-cycle` | ERROR | current records' `parent` goes round in a circle (A's parent is B, B's is A) |
| `superseded-cycle` | ERROR | the same for `superseded_by` |
| `dual-owner` | ERROR | two current records name one file (paths compared NFC), unless one is superseded, directly or down a chain, by the other |
| `orphans`, `orphan` | WARN | files under `ArtDirection/` that no record names (in `files`, `inputs` or `params.prompt_file`): the count, then up to 20 paths |
| `no-git`, `git-failed` | WARN | the vendor and tracked rules could not ask git, so they did not run |

The orphan scan skips the ledger and its `.torn` file, `manifest.md`, dot-files, `.meta` files
and `ArtDirection/raw/` (git-ignored originals). A file named only by an old revision is not an
orphan.

The writing commands apply the same rules before they append:

| Command | Refused (exit 2) when | Also |
|---|---|---|
| `record` | the composed record breaks the schema (`art_version` included: it is a `made-under` link); a path is outside the root; a parent, `superseded_by` or link id is not in the ledger; the record closes a cycle or takes a file another id holds; `id-taken`; with `--status approved`, anything approval refuses | a missing file is recorded with `missing: true` and a WARN; a `file.path` outside the root is kept by its name only, `file-outside-root` WARN |
| `status ID approved` | any rule above for this record, read as approved: a file missing, recorded missing, or changed since it was recorded, a failed verdict, a failing gate, a tracked vendor file, an unresolved parent, a file another id holds (`dual-owner`), a cycle through it; `dirty-file`, its Blender file unsaved, unless `--allow-dirty`; `diagnostic`, the record is a diagnostic run | the same status again with nothing new writes nothing |
| `status ID superseded --by X` | X is the record itself, X is superseded down a chain by ID (`superseded-cycle`), X is not a candidate or approved (`bad-successor`) | X unknown exits 3 |
| `mv` | the new path is not on disk or outside the root; an approved file's bytes differ at the new path; another asset holds the new path | `old-path-exists` WARN when the old path is still there |

Every other status is never refused, except for an unknown id. Any write into a ledger that holds
a `corrupt-line` stops with exit 3; a write into one with a `torn-line` moves it aside first.

## Exit codes and output

| Exit | Verdict | Means |
|---|---|---|
| 0 | green | nothing failed; warnings allowed |
| 2 | failed | a rule failed, or a write was refused |
| 3 | harness | no ledger, a corrupt line, input that is not a JSON object, a bad argument, an unknown id, the ledger changed under a write (`conflict`) |

Lines read `ERROR <path>: <rule>: <message> (id <id> rev <n>)`, `WARN …` or `OK …`, then one
summary line. `--json` (every command except `record` and `ingest`, where `--json` names the
input) prints one object instead: `command`, `exit`, `verdict`, `errors`, `warnings`, `items` (each
with `level`, `rule`, `path`, `msg`, `id`, `rev`), `summary`, and the command's own keys: `lines`,
`ids` and `orphans` for `check`; `stale` and `at` for `stale`; `history`, `current_version` and
`previous_good` for `history`; `rows` for `render`; `record` for the writing commands.
