# Working with the ledger

The loop is short: **record** every asset a producer writes, **check** before anything is
committed, set a **status** only after a person has looked, and after an upstream change ask what
went **stale**. Run every command from the project root, or pass `--root`. `registry.py` below is
this skill's `scripts/registry.py`.

## 1. Start

```bash
python3 registry.py init
```

It creates `ArtDirection/assets.jsonl` empty, or leaves an existing one alone. When git ignores
the ledger (often because `ArtDirection/` as a whole is ignored), it warns: un-ignore the ledger,
or keep it at a tracked path with `--ledger PATH` or `ART_LEDGER=PATH`, and give every later
command the same path. A relative `--ledger` or `ART_LEDGER` is read against the current
directory; every path inside the ledger is relative to the project root.

What stays out of git is the bytes, not the facts: `ArtDirection/raw/` (undecimated originals)
and purchased packs are ignored, and their records stay in the ledger. `check` then reports such a
file as `local-only` on a machine that does not have it, and hashes it where it exists.

## 2. Record after every generation

`record` takes a partial record, from `--json FILE` or on stdin, and the fields the producer does
not know as flags: `--kind --class --source --license --status --id --art-version --link --note`.
It fills in `schema`, `id`, `rev`, `ts` and `status` (`candidate` unless `--status` says
otherwise), hashes every file under `files[]` and the Blender file named in `file`, pins the hash
of every input and the content rev of every linked id that has none, validates, and appends one
line.

A sheet from `codex-visual`, made from the master anchor under `ART_DIRECTION.md` Version 2:

```json
{"files": [{"path": "ArtDirection/sheets/runner_run.png", "role": "shipped"},
           {"path": "ArtDirection/previews/runner_run.gif", "role": "preview"}],
 "parent": ["artdirection/anchors/master"],
 "inputs": ["ArtDirection/anchors/master.png"],
 "tool": {"skill": "codex-visual", "script": "codex_generate.py"},
 "params": {"prompt_file": "ArtDirection/prompts/runner_run.txt", "prompt_sha256": "c07e…"},
 "gates": [{"name": "frames.count", "value": 8, "limit": 8, "pass": true}],
 "verdict": "green"}
```

```bash
python3 registry.py record --json runner_run.record.json --kind sheet --source generated --art-version 2
# OK ArtDirection/sheets/runner_run.png: recorded artdirection/sheets/runner-run rev 1 (candidate)
```

`--art-version 2` is the link `{"rel": "made-under", "to": "art:direction", "rev": 2}`;
`--link depends-on=artdirection/turnarounds/mallet` links an upstream asset at its current
content rev, and `--link made-by=job:retarget-0315` names the job that produced it.

The same shape serves every producer. A mesh from `comfyui-asset-generation` names its shipped
file first, then its raw original with `role: source`, with `--class hero-prop` and the turnaround
as `parent` and as a `depends-on` link. A clip from `blender-retarget` carries the gates its module
returned and `file: {path, saved, dirty}` for the `.blend` it came out of; `record` adds that
file's sha256, so every version of the `.blend` that produced something is pinned. A purchased
crate is `--source purchased --license purchased:courier-pack` with `vendor: true` on its file.
A video or a clip made with a model whose licence limits where it may be sold carries
`"licence": {"source": "minimax-h3-local", "territory": {"excludes": ["US", "EU", "UK", "KR"]}}`
in its partial record; what is made from it links back to it (`parent` or `depends-on`) and needs
no copy (`reference/licences.md`). Turning a producer's own JSON output into this shape is `reference/ingest.md`.

**A headless character pipeline** (`blender-character-rig` → `reference/headless-pipeline.md`)
records one row per shipped output: the character FBX (with its LOD levels inside), the prop FBX,
the textures, each with the stage's `.blend` as `role: source`. The stage's gates JSON already
carries `{name, value, limit, ok}` and the input and output hashes: copy its gates with `ok`
renamed `pass`, and `--link made-by=job:<character>-<stage>`. A purchased clip pack is one
record, `--source purchased`, `vendor: true`; the clips played unchanged from it need no row per
clip, while a clip converted from another skeleton is its own record with `depends-on` both
packs. A change to the fit (a new canonical scale) is a new revision of the character, and
`stale` then names everything measured on the old one.

**Git LFS is a budget, per character and per clip set.** Measured in a tennis game against a
1 GB free tier: about 9 MB per character (a 1.6 MB FBX with two LOD levels, three 1024 base
textures and a normal map), 105 MB for 75 purchased clips, 104 MB more for the pack's second
variant kept beside them, and about 450 MB used in total after two characters. Before tracking a
pack's second variant, or the original archive beside its extracted files (byte-identical in
that pack), decide whether it can be re-extracted instead. A project that keeps purchased files
in a private repository is overriding this skill's default (`vendor: true` stays out of git):
write that decision down, and expect `check --strict` to flag the tracked vendor files.

- **The id comes from the first file**, or from the id that already holds it. List the shipped
  file first, or pass `--id`.
- **Regenerating at the same path** adds a revision of the same id, back to `candidate`; `kind`,
  `class`, `source`, `license` and `licence` carry over when they are not given again, links do not.
- **A new path for the same asset** is a new id. Approve the new one, then
  `status OLD superseded --by NEW`.
- **A run made to learn something** (a raw decode export, a downstream-only rerun, one preset of
  several made for comparison) is `--status diagnostic`: kept as evidence, never approved.
- **A file not on disk** is recorded with `missing: true` and a WARN, and `check` keeps warning
  until it is recorded again.
- **Refused** (exit 2, nothing written): a schema break, a path outside the root or with `..`, a
  `parent` or link id the ledger does not have (record it first), a cycle, a file another asset
  holds, the prompt text or a URL in `params`, a `purchased` or `third-party` source without
  `--license`.

## 3. Check

```bash
python3 registry.py check            # before a commit, and in CI
python3 registry.py check --strict   # unknown keys and tracked purchased files become errors
```

Exit 0, 2 or 3; every finding names its rule (the table is `reference/ledger-schema.md`). The
usual fixes:

| Rule | Fix |
|---|---|
| `hash-drift` | the file was regenerated or edited without a `record`: record it again |
| `changed-after-approval` | put the approved bytes back, or record the new bytes, which start again as `candidate` |
| `missing` | restore the file, `mv` the record to where the file went, or set it `rejected` |
| `rev-gap` | lines were deleted or edited; restore the ledger from git, never renumber it |
| `dual-owner` | the older asset is `superseded --by` the newer one, or the wrong one is recorded again without the file |
| `parent-cycle`, `superseded-cycle` | a new revision of one of them with the wrong parent or successor corrected |
| `vendor-not-ignored` | add the vendor path to `.gitignore` and `git rm --cached` the file |
| `unresolved-parent`, `unresolved-link` | record the parent first, or correct the id in a new revision; an outside name is `ns:key` |
| `torn-line` | nothing: the next write moves it to `assets.jsonl.torn`; read that, then delete it |
| `orphan` | record the file, or delete it if it is a leftover; orphans never fail a check |
| `territory-excluded` | remake the asset (or the upstream one the message names) from a source licensed where the game is sold, record and approve it, and supersede the old one; or narrow the `Sales territory:` line (`reference/licences.md`) |
| `territory-undeclared` | write the `Sales territory:` line in `ART_DIRECTION.md` before shipping; until then it only warns |

## 4. Status: a person's act

Approval says that someone looked at the asset where it will be seen: the preview strip at game
scale, a QA sheet beside the anchor, the clip played through, a side-by-side in the game scene. It
is never the last line of a generation script. Record the image the decision rests on (`kind
qa-sheet`), then name it and the person:

```bash
python3 registry.py status artdirection/sheets/runner-run approved \
    --approver lead --evidence artdirection/qa/runner-run --note "QA sheet at game scale"
python3 registry.py status artdirection/sheets/runner-run rejected --note "arms swing out of phase"
python3 registry.py status artdirection/anchors/runner-v1 superseded --by artdirection/anchors/runner
```

`approved` checks the record as if it were already approved and refuses (exit 2) on a missing or
changed file, a failed verdict, a failing gate, a tracked vendor file, a licence (its own or an
upstream one) that excludes part of the declared sales territory, an unresolved parent, a
`diagnostic` run, or a Blender file that was unsaved when the asset was produced (`file.dirty`).
Save the `.blend`, run the step again and record that; `--allow-dirty` approves anyway and writes
the reason into the record's `warnings`. `superseded --by X` refuses an X that is the record
itself, is already superseded by it, or is not a candidate or approved asset; an unknown X exits
3. `candidate`, `unused` and `diagnostic` are set the same way.

**Which version is current.** The current version of an asset is its latest `approved` revision,
also while a newer candidate waits for a look. `history ID` lists every revision and marks the
current version and the previous good one, whose sha256 is what a rollback restores. An id whose
last record is `rejected`, `superseded` or `unused` has no current version; its last approved
revision is the previous good one.

## 5. Stale: an upstream change

Every link with a `rev` is a claim: "made from this version". When the version moves, the claim
is behind.

```bash
python3 registry.py stale                       # upstream assets with newer bytes
python3 registry.py stale --art-version 3       # and everything not made under Version 3
python3 registry.py stale --at flow:mesh=2      # and an outside node's version
# WARN Assets/Models/HeroProp/Mallet/Mallet.glb: stale: candidate; artdirection/turnarounds/mallet rev 1 < 3 (id …)
```

A link to a ledger id is behind when that id has newer content (new bytes, not a status change or
a move). A link to `ns:key` is behind the value given with `--at` (or `--art-version` for
`art:direction`); with `--art-version`, a record with no `made-under` link at all is listed too.
`stale` lists current candidate and approved records and never writes. For each one, decide with
the user: regenerate it (a new candidate with the new links), carry it forward unchanged (record
the same files again with the new links, then approve, which pins that someone judged it against
the new upstream), or set it `rejected`.

## 6. A change record, and which evidence wins

Change one thing at a time, and write down why before the next attempt. Keep each change record
as a Markdown file under `ArtDirection/changes/`, record it (`kind change`), and link the revision
it explains to it (`--link explained-by=<its id>`):

```markdown
# <asset id>: <one line>
- Problem:      what is wrong, seen where (camera, scene, frame)
- Source:       <id> rev <n>, sha256 <first 12>  (`registry.py history <id>`)
- Check:        the measurement or image that shows it, and its value
- Hypothesis:   the one cause this change tests
- Change:       the one setting, input or step changed, from → to
- Verification: the same check, same camera and inputs, after the change
- Result:       better / same / worse, with the numbers; the new rev
- Rollback:     the rev and sha256 to restore if this is worse (the previous good version)
```

When two sources of evidence disagree, the higher one wins:

1. an audit of the saved file, re-opened (the `.blend`, the FBX, the imported asset);
2. results and renders that agree with each other (gates, QA sheets, contact sheets);
3. the scripts that produced it, read;
4. what was asked for in conversation;
5. general references and documentation.

A record's `gates` and its evidence image sit at levels 1 and 2; a `note` saying it worked sits at
level 4.

## 7. Moving a file

Move it in the Unity Editor or with `git mv`, so its `.meta` goes with it, then:

```bash
python3 registry.py mv assets/models/heroprop/mallet/mallet Assets/Models/HeroProp/Mallet/Mallet_LOD0.glb \
    --file Assets/Models/HeroProp/Mallet/Mallet.glb
```

The id stays; the new revision carries the new path and its hash. `--file` names the file that
moved; a record with one file does not need it. An approved file whose bytes differ at the new
path is refused: that is a new candidate, not a move. A path another asset holds is refused too.

## 8. `manifest.md`

`ArtDirection/manifest.md` stays the prose people write, with their own columns and shorthand.
Nothing in this skill rewrites it.

```bash
python3 registry.py render
# | 2026-03-14 | `ArtDirection/sheets/runner_run.png` +1 | sheet | approved | 2 | QA sheet at game scale |
```

`render` prints one row per current record (date, path, kind, status, the `made-under
art:direction` version, note), the first file's path with `+N` for the rest, sorted by date.
Paste the rows you want under the manifest's own table. A project that already has a manifest
and no ledger starts with `reference/adopt.md`, which reads the manifest without changing it.

## 9. Several writers at once

Producers may record at the same time. Each append takes an exclusive lock on the ledger, reads
the id's last revision inside it, and writes its line with one `write` and an `fsync`, so the
lines never interleave and every id's revisions stay gapless. A reader without the lock may see a
line still being written, and a writer that dies mid-line leaves a fragment; either way the last
line has no newline and does not parse, so `check` warns `torn-line` and reads the rest. The next
append, holding the lock (so no live writer owns the fragment), moves it to `assets.jsonl.torn`
before writing. A broken line with lines after it is different: `corrupt-line`, exit 3, and every
write stops until the ledger is restored from git.
