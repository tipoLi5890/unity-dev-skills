---
name: art-asset-registry
description: >-
  One append-only ledger per project, ArtDirection/assets.jsonl, for every 2D
  and 3D asset: files with sha256 (each .blend version too), lineage (parent,
  links to the art direction, a job or an evidence image), gates, verdict and
  status. Record after each generation, check that the disk still matches
  (exit 0/2/3), set a status as a person's act, list what a newer upstream made
  stale, print rows for manifest.md, adopt an existing manifest.md read-only.
  Load for: "track generated assets", "which asset came from which prompt",
  "stale after a style bump", "which version is current", "a manifest.md with
  PENDING rows". Generating: codex-visual, comfyui-asset-generation.
---

# art-asset-registry — what exists, where it came from, who approved it

Every generation skill writes files, and none of them remembers which prompt, anchor, seed or
workflow made which file, or whether anyone looked at it. A hand-written `manifest.md` drifts the
same way in every project: rows for files that are gone, files no row names, rows still `PENDING`
long after the spec locked, and nothing that notices an approved image being overwritten. The
ledger keeps the facts a script can know (paths, hashes, lineage, links, gates, status) and leaves
the prose to people. It treats 2D and 3D alike: a sprite sheet, a mesh with its raw original, a
rig with the `.blend` it came from, a clip, a QA sheet a decision rests on.

> **The ledger is the truth; `manifest.md` is the story.** Record what was made, check that the
> disk still matches, and let a person decide what is approved.

## Working contract

- **The ledger is the truth.** `ArtDirection/assets.jsonl`, one JSON record per line, appended and
  never edited. A correction is a new revision; an id's current record is its last line.
- **The current version is the latest approved revision.** A newer candidate is a proposal until
  someone approves it; `history ID` names the current version and the previous good one.
- **`manifest.md` is prose.** Nothing here rewrites it: `render` prints rows to paste, and adopting
  an existing manifest reads it without changing it.
- **Approval is a human act.** `status ID approved` follows a person looking at the asset where it
  will be seen, never the end of a script, and names who and on what image (`--approver`,
  `--evidence`). It refuses a failed verdict, a failing gate, a missing or changed file, output of
  an unsaved Blender file, and a `diagnostic` run.
- **Ids are permanent; hashes are content.** An id is made once from a path (NFC, any script) and
  survives edits and moves (`mv`). Changed bytes are a new revision, back to `candidate`. One file
  belongs to one asset.
- **Facts, never secrets.** `params` holds `prompt_file` and `prompt_sha256`, never the prompt
  text, and `server_label`, never a URL. Purchased and third-party files carry `source`, `license`
  and `vendor: true`, and stay out of git.
- **The method lives here; the records live in the project.** This skill holds the schema and the
  scripts. Ledgers, assets and purchased packs stay in each project.

## Load what the situation needs

| The situation | Read |
|---|---|
| What a field means, the vocabularies (kinds, statuses, link rels), how an id is made, every check rule with its level, the exit codes, the JSON output | `reference/ledger-schema.md` |
| Starting a ledger, recording after a generation, `check` and its fixes, setting a status, stale after an upstream change, a change record and which evidence wins, moving a file, rows for the manifest, several writers at once | `reference/workflow.md` |
| A project with a hand-written manifest and no ledger: reading it once into records, dry run first, the manifest never edited | `reference/adopt.md` |
| A producer's JSON output (a codex call, a frames sidecar, a Blender report) turned into records | `reference/ingest.md` |
| The flags of one command | `scripts/registry.py <command> --help` and the module docstrings |

## Commands

| Command | Does | Exit |
|---|---|---|
| `init` | creates the empty ledger; warns when git ignores it | 0 · 3 |
| `record` | appends a record built from a partial record (`--json FILE` or stdin) and flags (`--art-version N`, `--link REL=TO`); hashes every file and the `.blend` named in `file`; refuses a schema break, an unknown parent or link, a cycle, a file another id holds | 0 · 2 refused · 3 bad input |
| `check [--strict]` | every rule, then orphans under `ArtDirection/` | 0 · 2 · 3 |
| `stale [--art-version N] [--at NS:KEY=N]` | current candidate and approved records with a link behind: an upstream asset with newer bytes, or an outside version given here; writes nothing | 0 · 3 |
| `status ID STATE` | the status change as a new revision; `approved` refuses what `check` would fail; `superseded --by ID` refuses an unknown, dead or circular successor | 0 · 2 · 3 |
| `history ID` | every revision, with the current version and the previous good one marked | 0 · 3 |
| `mv ID NEWPATH` | the same id at its new path, hashed again | 0 · 2 · 3 |
| `render` | Markdown rows for `manifest.md`, printed only | 0 · 3 |
| `adopt --dry-run [--out FILE]` · `adopt --write` | reads `manifest.md` (never written) once into records; prints counts and line numbers only; the dry run never opens the ledger | 0 · 2 nothing written · 3 |
| `ingest [--json FILE] [--write]` | a producer's JSON output — anything with a `record` key (the Blender reports), `frames.json`, a codex call — as a partial record, printed; `--write` hands it to `record` | 0 · 2 · 3 |
| `selftest` | every case in a temporary directory, 100 concurrent appends among them | 0 · 2 |

Every command takes `--root DIR` and `--ledger PATH` (or `ART_LEDGER`). `record` and `ingest` read
their input from `--json FILE` (or stdin); every other command takes `--json` to print one JSON
object. Exit codes follow `unity-debug`'s `merge_results.py`: 0 green, 2 failed or refused, 3
harness. `scripts/registry_ledger.py` is the library (`load`, `last_by_id`, `current_version`,
`content_rev`, `append`, `validate`, `sha256_file`, `slugify`) that the other scripts import.

## Worked example

The courier run: `Runner` has a locked anchor, a run sheet, a hammer prop `Mallet` and a
`GateLatchSwing` clip.

1. **Start.** `registry.py init` creates `ArtDirection/assets.jsonl`. Git ignores
   `ArtDirection/raw/` and the purchased `ArtDirection/vendor/`, not the ledger.
2. **A sheet.** `codex-visual` writes `ArtDirection/sheets/runner_run.png` from the anchor.
   `record --kind sheet --source generated --art-version 2`, with the call's gates, its prompt file
   and hash, and the anchor as parent: id `artdirection/sheets/runner-run`, rev 1, `candidate`,
   linked `made-under art:direction` rev 2.
3. **A look, then approval.** Its QA sheet is recorded too (`kind qa-sheet`). At game scale the
   run reads right: `status artdirection/sheets/runner-run approved --approver lead --evidence
   artdirection/qa/runner-run`. Overwriting the sheet later fails `check` with
   `changed-after-approval` until the new bytes are recorded (a new candidate) or put back.
4. **A mesh, and a run to learn from.** `comfyui-asset-generation` turns the `Mallet` turnaround
   into `Assets/Models/HeroProp/Mallet/Mallet.glb` (shipped, listed first) and a raw original
   under `ArtDirection/raw/3d/Mallet/` (role `source`), the turnaround as parent and as a
   `depends-on` link. A raw shape-decode export made only to see where sheets come from is
   recorded `--status diagnostic`: kept, never approved.
5. **A clip.** The `GateLatchSwing` report from `blender-retarget` carries a `record` key;
   `ingest --kind clip --file …@GateLatchSwing.fbx --write` records it with its gates and the
   `.blend`'s state and sha256. The `.blend` was unsaved, so approval refuses with `dirty-file`;
   saved, exported and ingested again, it is approved.
6. **An upstream change.** The turnaround is regenerated (new bytes, rev 3): `stale` lists the
   mallet, whose `depends-on` link still says rev 1. `ART_DIRECTION.md` goes to Version 3:
   `stale --art-version 3` lists everything made under 2. Each is regenerated, carried forward
   (recorded again with `--art-version 3`, then approved) or rejected, with a change record.
7. **The manifest.** `render` prints one row per asset; the user pastes the new ones under the
   manifest's own table.

## Discipline

- **Record when the file is written.** The producer's call is the only moment the prompt hash,
  seed and inputs are known; recorded later, they are guesses.
- **Never edit a line.** A wrong record is fixed by a new revision. A `rev-gap` means someone
  edited the ledger, and the fix is the ledger from git, not new numbers.
- **A warning is not a verdict.** `local-only`, `no-hash`, `moved-on`, `torn-line` and orphans
  pass `check`; read them anyway.
- **A script that writes records validates them.** It imports `registry_ledger`, calls
  `validate`, then `append(..., assign_rev=True)`, so its revisions are numbered inside the lock.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Generating 2D art, sheets, turnarounds and QA sheets; the art bible itself | `codex-visual` |
| Generating meshes and textures through ComfyUI | `comfyui-asset-generation` |
| Rigging, skinning and the game mesh in Blender | `blender-character-rig` |
| Retargeting clips onto a rig in Blender | `blender-retarget` |
| Which stage of a character comes next, and its gate | `game-character-pipeline` |
| Triangle and texture budgets, the import audit in Unity | `unity-3d-models` |
| Which packs may be bought and which licences may ship | The project's own policy; the ledger records `source` and `license` and keeps vendor files out of git |

## Related skills

`codex-visual` for the art bible, the anchor and every 2D asset · `comfyui-asset-generation` for
meshes and textures from images · `blender-character-rig` for a rig built from landmarks ·
`blender-retarget` for clips on that rig · `game-character-pipeline` for the order of the stages
· `unity-3d-models` for budgets and the import audit.
