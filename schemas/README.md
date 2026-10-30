# Data contracts

Three files that cross skill boundaries, each defined once, here, as JSON Schema (draft 2020-12).
A producer stamps the file with `schema`. `tools/check-contracts.py` validates producer output
against these schemas in CI. Skills never import a validator: each skill's scripts stay copyable
on their own, and a selftest checks its own output's required keys by hand.

Stamps take the form `<name>/<major>`, the form already used by `skeleton/1`, `role-map/1`,
`motion-samples/1` and `contacts/1`. A new major version means a reader of the old one would
misread the file. Adding an optional key does not need a new version.

| Contract | Schema | Producers | Consumers |
|---|---|---|---|
| A frame set's `frames.json` | [`frames-1.json`](frames-1.json) | `codex-visual` `sheet_to_frames.py`, `breathe.py`; `sprite-from-video` `video_loop.py` | `audit_frames.py`, `audit_pixel.py`, `frames_to_anim.py`, `registry_ingest.py`, `unity-2d-sprites` `FramesJsonImporter`, `SheetToAnimationClip`, `SpriteFramesAudit` |
| A gate script's report | [`gate-1.json`](gate-1.json) | `rig_gate`, `deform_gate`, `mesh_check`, `motion_metrics`, `clip_metrics`, `contact_bake`, `twocam/solve`, the Blender ops (`blender_common` / `bcommon` `report()`), `contract_map map`, `inspect_glb`, `audit_3d_source`, `camera_gate` | `autorig.py`, `twocam.py`, `registry_ingest.py`, `contact_sheet.py --require`, `bakeoff_report.py` |
| One line of a journey's `timeline.jsonl` | [`timeline-1.json`](timeline-1.json) | `unity-play-harness` `JourneyRecorder.cs` (samples from `GameProbe.ToJson`) | `journey_report.py`, `jump_report.py`, `camera_jitter.py` |

## frames/1

- **`key_color`** is the declared chroma key that the frames were keyed against: the colour
  picked before generating, in lowercase `#rrggbb`. The fringe and tint checks measure the rim
  against this colour, on both the Python and the Unity side. `key_painted` is optional and
  records the colour the model actually painted. `null` is allowed only when the producer was told
  explicitly that the art was never keyed (native alpha). A reader then skips the fringe check and
  prints that it did. It never treats `null` as a pass.
- **The margin field is `register.foot_margin_px`**: the transparent pixels between the reference
  frame's feet line and the bottom of the canvas. The other name, `margin_px`, is refused in
  frames/1.
- **`register.reference_core_height_px`** is required and is an integer of at least 1: the
  reference frame's core height, in pixels of the written frame files, after any pixel upscale.
  Every set of one character carries the same number.
- **PPU rule:** `PPU = reference_core_height_px / the character's height in world units`, with one
  PPU for every set of the character. The core height is measured on the written files, so a pixel
  set's upscale factor F (`pixel.block_px`) is already included. For pixel art, choose the world
  height so that `PPU / block_px` is a whole number: the art-pixel PPU that the tiles and the Pixel
  Perfect Camera use.
- **Pivot:** `pivot_norm` `[x, y]` is a fraction of the canvas measured from its bottom-left,
  which is Unity's own sprite-pivot convention. The importer sets `SpriteAlignment.Custom` with
  `spritePivot = pivot_norm` on every frame, and the feet then sit at `transform.position`.
  `pivot` (`bottom-center`, `center` or `foot-center`) is only a coarse statement kept for older
  readers.
- **`loop`** is always written, because a typed reader such as `JsonUtility` cannot tell a missing
  bool from `false`. **`hold_last`** is a bool, default false: true means a one-shot that ends on
  its last pose and holds it, which implies `loop: false`. It is not a count of frames.
- **`fps_hint`** sets the clip's frame rate. **`pixel.block_px`** is the integer F. It is present
  only for a pixel set.
- `register` stays flat, with no object-valued member. `verdict` is the producer's own
  `{ok, faults}`. It is not a gate/1 report, and it is bridged to a `pass` gate when the set is
  recorded in the registry.

## gate/1

- The report is `{schema, pass, gates: [{name, value, limit, pass}]}`. Both levels accept extra
  keys (`tool`, `clip`, `blender`, per-gate detail). The required keys are what catch a misspelt
  or old-dialect verdict.
- **A gate without a boolean `pass` has failed. A report without a boolean `pass` has failed.**
  A reader never defaults to passing.
- `pass: true` needs at least one gate, every gate passing, no `refused` and no `error`. A
  refused or harness report is `pass: false`, with `gates` possibly empty.
- `value` and `limit` can be any JSON value, including null or a string such as `"<= 0.03"`.
- A gate carrying `ok` is refused.

## timeline/1

- Each line validates on its own. The first line is meta and is the only line that carries
  `"schema": "timeline/1"`. Each sample is one `GameProbe` snapshot with `n`. The last line is
  end, and a run that did not finish has no end line.
- A sample line is closed at its top level. Game-specific values go in `custom`, `counts` and
  `ready`.
- Keys resolve in one order: `pos.x|y|z` and `vel.x|y|z` (or `.0` to `.2`), then an exact dotted
  path, then `custom.<k>`, `counts.<k>`, `ready.<k>`, then a top-level field. Every reader carries
  the same pasted `resolve()`, which is kept identical by `tools/shared-blocks`.

## Migration (one release)

Consumers still read the 0.34 dialect for one release. Each time they do, they print one `WARN`
line naming the file and the old key:

- `frames.json` with no `schema`: read as the old dialect. `margin_px` is read as
  `foot_margin_px`. `set_metrics.key_color` is read as `key_color`. When there is no key at all,
  the fringe check reports `n/a` with a warning and is not counted as passed. A missing or zero
  `reference_core_height_px` skips the size check, with a warning.
- A gate report with no `schema`: a gate's `ok` is read as `pass`, and a report's `ok` is read as
  `pass`. For this one release producers still write the report-level `ok` beside `pass`, and
  `gate-1.json` requires the two to be equal. A gate-level `ok` is not written.
- A timeline meta line with `"schema": 1` is read as `timeline/1`.

Only an unstamped file gets this treatment. A file stamped `frames/1`, `gate/1` or
`timeline/1` that is missing a required key is a producer bug, and the reader fails on it rather
than warning. A Blender op that reports with zero gates is returning a result, not a gate report:
it has no `schema` and keeps `ok`.

The release after this one removes the old dialect.
