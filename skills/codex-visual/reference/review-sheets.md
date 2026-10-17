# review-sheets — one composer for every sheet a person decides from

A decision about a generated asset is made by looking: eight views of a mesh, one pose per clip,
five presets side by side, the same camera before and after a fix. `scripts/contact_sheet.py`
composes all of them from one JSON spec, and with `--require` it refuses to compose while the
numeric checks disagree — so a sheet in front of a person always belongs to files that passed.

## 1. The call

```bash
python3 <skill>/scripts/contact_sheet.py sheet.json --out review/runner_r03_qa.png \
    --require out/runner_r03/inspect.json            # repeatable; several after one flag
python3 <skill>/scripts/contact_sheet.py --selftest
```

```json
{"title": "Runner r03 — Large preset",
 "cols": 4, "cell": 512,
 "items": [{"image": "out/runner_r03/front_00001.png", "label": "front"},
           {"image": "out/runner_r03/left_00001.png",  "label": "left"}]}
```

- `cell` is a side in px or `[w, h]`; an image larger than the cell is scaled down to fit, a
  smaller one stays at its own size, centred. Transparency is laid over `bg` (default `#202020`).
- `image` paths are relative to the spec's folder. `label` is printed above the cell; `frame`
  is printed after it (`f12`) and, for an animated GIF, APNG or WebP, picks that frame.
- `"sheets": [{"name": "jog", "items": [...]}, ...]` in place of `items` writes one file per
  entry, `<out stem>-<name>.png`; each may set its own `cols`, `cell`, `bg`, `title`.
- `--require FILE`: each file must be a JSON object whose `ok`, `all_pass` or `pass` is `true`, or
  whose `verdict` or `record.verdict` is `"green"` — every one of those it carries, and at least
  one. That covers `inspect_glb.py --json-out`, `audit_3d_source.py --json-out`, the Blender
  reports with `ok`, and any project check that writes `all_pass`.
- Exit **0** written; **2** refused by `--require` (nothing written) or a usage error, such as an
  `--out` suffix Pillow cannot write; **3** the spec or an image cannot be read, or a sheet cannot
  be written (nothing written, no sheet of the run left behind). It prints `written`, `sheets`, `items` and
  `required` (each file with `pass` and, on failure, `why`).

## 2. The sheets

| Sheet | Items | `--require` |
|---|---|---|
| 8-view mesh QA | front, left, back, right, top, clay, occlusion, uv_atlas from `3d/qa/`; `cols` 4, `cell` 512 | the GLB gate's JSON (`comfyui-asset-generation` → `scripts/inspect_glb.py --json-out`) |
| raw shape vs final | the raw shape-decode render and the final `clay`, same camera | — |
| preset comparison | one `clay` or textured render per generation preset, labelled by preset | each preset's gate JSON |
| before / after | the same camera and frame, two cells, labelled with the two versions | the after version's checks |
| animation contact sheet | one still per clip at a named `frame`, labelled by clip; `sheets` per family | the retarget and library reports (`ok`) |
| overview page | themed pages of a project's pictures, ungated | none: `scripts/overview_sheet.py` (`reference/overview-sheets.md`) |

Label every cell with what differs (`r03`, `Large`, `before`), never with a file name only.

## 3. What a sheet is not

A sheet shows; it does not measure. The numbers live in the files `--require` reads, and a cell
nobody looked at is not a pass. One still per clip says nothing about motion: judge an animation
on its onion skin and its preview (`reference/animation-scripts.md` §1, §2). A sheet composed
without `--require` is a draft for discussion, not evidence for a decision.
