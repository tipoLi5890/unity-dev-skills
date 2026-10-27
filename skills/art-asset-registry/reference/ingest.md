# Ingesting a producer's output

Every producer prints or writes JSON about what it made. `ingest` turns that JSON into the
partial record `record` takes, so the facts are copied by a script, not retyped. Run it from the
project root, or pass `--root`.

```bash
python3 registry.py ingest --json frames.json                       # print the partial record
python3 registry.py ingest --json frames.json --write               # record it
python3 registry.py ingest --json report.json --kind clip \
    --file Assets/Models/Character/Runner/Runner@GateLatchSwing.fbx --write
```

Without `--write` it prints only the partial record, to read before writing or to pipe on:
`registry.py ingest --json out.json | registry.py record --kind sheet --art-version 2`. With
`--write` the partial goes through `record`: every file hashed, every input pinned, the record
validated, a refusal exactly as `record` refuses (`reference/workflow.md` §2), the result a
`candidate` unless the producer's own record says otherwise.

`--kind --class --source --license --status --art-version --link --id --note` set those fields
as on `record`, in the printed partial too (`--art-version` and `--link` as `links`). `--file PATH` (repeatable, the shipped file first) adds a file the JSON does not
name.

## The shapes

Tried in this order; the first that fits is used.

| Shape | Recognised by | Becomes |
|---|---|---|
| a record | a `record` object, from any producer that writes one (every Blender skill report carries one; the ComfyUI and codex clients where they add one) | that object; keys it leaves out are filled from the shape below it, and a top-level `file` (`{path, saved, dirty}`) is carried in and hashed. A ComfyUI job is read only through its `record` |
| frames | `sheet_to_frames.py`'s `frames.json` (`tool`, or `frames` with `cell` and `verdict`), or any `frames.json` with `frames` and a `producer` (`breathe.py`, `video_loop.py`) | the sidecar first, then every frame (read next to it), the sheet (else `source`, a path or `{file}`) as an input, a `frames.faults` gate, `verdict` from `verdict.ok`, fault kinds in `note`; `tool` is the `producer`'s `{skill, script}` when it names one (both strings, else exit 3), else `codex-visual`/`sheet_to_frames.py` |
| Blender | `gates` and `blender` | its gates and verdict (`ok`), `source: authored`; the file comes from `--file`, else the report's top-level `path` (an FBX export), else the saved `.blend` from `file.path` as `role: source, mutable: true`, hashed like any file |
| codex | `out` and `size` | the image, `source: generated`; with `--expect-size`, a `codex.size` gate; an alpha render adds a warning |

Anything else exits 3, and so does a producer's error output (an `error` with nothing written)
and JSON holding NaN or Infinity.
Text output is never parsed: an audit's lines are for people. Ask the producer for its JSON
output instead.

Rules that hold for every shape:

- **Paths become project-relative.** Absolute paths inside `--root` are rewritten, and a relative
  path is read against `--root` (so a producer is run from the project root); a file outside
  it is refused (exit 2). An input outside it is dropped and named in the record's `warnings`.
  The Blender file's own path is made relative too, or cut to its name when it lies outside.
- **No file, no record.** A Blender report from before `record` existed names no output: pass
  `--file`, or it exits 3.
- **Several images, no record.** `codex_generate.py` exits 5 when one call made more than one
  image, because which one was meant is a person's call. `ingest` refuses that output (exit 2):
  pick the image, then `record` it.
- **The kind** is the flag's, else the producer's, else the shape's (`frames`),
  else guessed from the first file's path (`@` in an `.fbx` name is a clip, `.glb` a mesh, a
  `sheets/` folder a sheet), else `other`.
- **A hash the producer printed** (`out_sha256`) is kept as given; `record` hashes the file again,
  and when the two differ records the file's and warns `sha256-replaced`: the file changed after
  the producer wrote it.

## The courier run

A run sheet cut into frames:

```bash
python3 codex-visual/scripts/sheet_to_frames.py ArtDirection/sheets/runner_run.png \
    --rows 1 --cols 8 --outdir ArtDirection/frames/runner_run
python3 registry.py ingest --json ArtDirection/frames/runner_run/frames.json --art-version 2 --write
# OK ArtDirection/frames/runner_run/frames.json: recorded artdirection/frames/runner-run/frames rev 1 (candidate)
```

The record lists `frames.json` and the eight frames, pins the sheet's hash as its input and
carries `frames.faults` (0, pass). The `GateLatchSwing` clip from a Blender report that carries a
`record` and a dirty `file`:

```bash
python3 registry.py ingest --json raw/reports/gatelatchswing.json --kind clip \
    --file Assets/Models/Character/Runner/Runner@GateLatchSwing.fbx --write
```

It is recorded with `file.dirty: true` and the `.blend`'s sha256, so `status … approved` refuses
it until the `.blend` is saved, the clip exported again and that report ingested. A report from a
run made only to learn something (a downstream-only rerun) is ingested with `--status diagnostic`.

| Exit | When |
|---|---|
| 0 | printed, or recorded |
| 2 | `record` refused it, a file outside `--root`, several images from one call |
| 3 | not JSON, not an object, not a shape listed above, an error output, no file named |
