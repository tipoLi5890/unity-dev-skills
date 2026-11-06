# Data contracts

Files that cross skill boundaries, each defined once, here, as JSON Schema (draft 2020-12).
A producer stamps the file with `schema`. `tools/check-contracts.py` validates producer output
against these schemas in CI. Skills never import a validator: each skill's scripts stay copyable
on their own, and a selftest checks its own output's required keys by hand.

Stamps take the form `<name>/<major>`, the form already used by `skeleton/1`, `role-map/1`,
`motion-samples/1` and `contacts/1`. A new major version means a reader of the old one would
misread the file. Adding an optional key does not need a new version.

| Contract | Schema | Producers | Consumers |
|---|---|---|---|
| A frame set's `frames.json` | [`frames-1.json`](frames-1.json) | `codex-visual` `sheet_to_frames.py`, `breathe.py`; `sprite-from-video` `video_loop.py` | `audit_frames.py`, `audit_pixel.py`, `frames_to_anim.py`, `registry_ingest.py`, `unity-2d-sprites` `FramesJsonImporter`, `SheetToAnimationClip`, `SpriteFramesAudit` |
| A gate script's report | [`gate-1.json`](gate-1.json) | `rig_gate`, `deform_gate`, `mesh_check`, `motion_metrics`, `clip_metrics`, `contact_bake`, `twocam/solve`, the Blender ops (`blender_common` / `bcommon` `report()`), `contract_map map`, `inspect_glb`, `audit_3d_source`, `camera_gate`, `autorig.py all --repeat` (`autorig.stability.json`), `concept_match`, `audit_identity` (report-only) | `autorig.py`, `rig_exam.py bench`, `twocam.py`, `registry_ingest.py`, `contact_sheet.py --require`, `bakeoff_report.py` |
| A character's parts plan `<c>.parts.json` | [`parts-1.json`](parts-1.json) | `blender-character-rig` `part_math.py plan`; `comfyui-asset-generation` `part_views.py` (its own keys) | `part_views.py`, `assemble_parts.py` |
| One line of a journey's `timeline.jsonl` | [`timeline-1.json`](timeline-1.json) | `unity-play-harness` `JourneyRecorder.cs` (samples from `GameProbe.ToJson`) | `journey_report.py`, `jump_report.py`, `camera_jitter.py` |
| A rigged character's `<name>.secondary.json` | [`secondary-1.json`](secondary-1.json) | `character-autorig` `secondary_chains.py` | `unity-rigged-character` `SecondarySpec`, `SecondaryMotionSetup` |
| A layered 2D character's `rig2d.json` | [`rig2d-1.json`](rig2d-1.json) | `comfyui-asset-generation` `layer_split.py split` | `unity-2d-animation` `AutoRig2D` |
| The rig exam's files (`NAME.truth.json`, `fault.json`, `exam.json`) | [`exam-1.json`](exam-1.json) | `character-autorig` `rig_exam.py` (`reference`, `faults`, `score`), `rig_exam_blender.py` (`cast`) | `rig_exam.py score`, `bench` |
| One version's rig readings, `<label>.bench.json` | [`bench-1.json`](bench-1.json) | `character-autorig` `rig_exam.py bench` | `rig_exam.py compare` |
| A pre-review of one review sheet `NAME.review.json` | [`review-1.json`](review-1.json) | `codex-visual` `prereview.py` (`new`, `answer`, `check`) | `prereview.py check`, `registry_ingest.py` |
| A rest skeleton (`<fbx>.skeleton.json`, `contract_map.py contract/bvh --out`) | [`skeleton-1.json`](skeleton-1.json) | `unity-rigged-character` `contract_map.py contract`, `bvh`; `blender-retarget` `brt_arp.py` `pipeline`/`export`; `humanoid-motion` `twocam/skeleton.py` (`demo_skeleton`) | `contract_map.py map`, `suggest`; `twocam/skeleton.py rig-info` |
| One clip's joint positions (`samples.json`, or `.npz` with a JSON `meta`) | [`motion-samples-1.json`](motion-samples-1.json) | `humanoid-motion` `twocam/solve.py --samples-out` (JSON), `contact_bake.py --samples-out` (NPZ) | `blender-retarget` `motion_metrics.py`, `clip_metrics.py`; `contact_bake.py --rig-info`, `--readings` |

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

- The report is `{schema, pass, gates: [{name, value, limit, pass, margin?}]}`. Both levels accept
  extra keys (`tool`, `clip`, `blender`, per-gate detail). The required keys are what catch a
  misspelt or old-dialect verdict.
- **A gate without a boolean `pass` has failed. A report without a boolean `pass` has failed.**
  A reader never defaults to passing.
- `pass: true` needs at least one gate, every gate passing, no `refused` and no `error`. A
  refused or harness report is `pass: false`, with `gates` possibly empty.
- `value` and `limit` can be any JSON value, including null or a string such as `"<= 0.03"`.
- **`margin`** (optional, a number on a gate) is the signed distance from `value` to the limit,
  scaled by the limit, so margins compare across gates, runs and characters. Positive is safe,
  negative is failing, and 0 sits on the limit:

  | Limit | `margin` |
  |---|---|
  | `<= L` (a ceiling) | `(L - v) / abs(L)` |
  | `>= L` (a floor) | `(v - L) / abs(L)` |
  | `[lo, hi]` (a range) | `min(v - lo, hi - v) / ((hi - lo) / 2)` |
  | `L = 0`, or `hi = lo` | the plain difference, not scaled |
  | a value or limit that is null, a bool, a string (other than `"<= L"` / `">= L"`) or not finite | no `margin` |

  It is rounded to 4 decimals. Example: a self-intersection p95 of 0.06 against `<= 0.08` has a
  margin of 0.25, and 0.10 has -0.25. Most limits in a report do not say whether they are a
  ceiling or a floor, so the producer passes the direction itself. A gate whose verdict also rests
  on a second condition carries no margin while that condition fails (a tear gate with too few
  edges to read). Every
  producer computes it with the same pasted `gate_margin(value, limit, op)`, from
  `tools/shared-blocks/gate_margin.py`.
- **A report-only gate** has `limit: null`, `pass: true`, `"report_only": true` and no `margin`: it
  is read by a person and gates nothing. When it could not be measured its `value` is null and it
  is listed in a top-level `not_measured: [{name, why}]` (`concept_match`, `audit_identity`). Not
  measured is not a pass.
- **`ok` is gone.** It was the old name of `pass`. No producer writes it, and the schema refuses a
  stamped report or a gate that carries `ok`.

## timeline/1

- Each line validates on its own. The first line is meta and is the only line that carries
  `"schema": "timeline/1"`. Each sample is one `GameProbe` snapshot with `n`. The last line is
  end, and a run that did not finish has no end line.
- A sample line is closed at its top level. Game-specific values go in `custom`, `counts` and
  `ready`.
- Keys resolve in one order: `pos.x|y|z` and `vel.x|y|z` (or `.0` to `.2`), then an exact dotted
  path, then `custom.<k>`, `counts.<k>`, `ready.<k>`, then a top-level field. Every reader carries
  the same pasted `resolve()`, which is kept identical by `tools/shared-blocks`.

## secondary/1

- Every bone is named as the FBX exports it. A chain lists `bones` root to tip, each a `cc_` bone;
  the last is the unweighted tip `cc_<chain>_end.<side>`, since Unity imports no bone tails.
  `parent` is the exported bone the chain hangs from; `parent_role` is its `HumanBodyBones` name,
  the fallback on a Humanoid.
- Positions are checks, not the source: `joints`, `parent_head` and a sphere's `center` are in
  the skeleton/1 frame (metres, +Z up, facing −Y). A capsule is two bone origins and a radius.
- `chains: []` is valid: the body has nothing loose, and the rig was left unchanged.

## parts/1

- **The anchor comes first.** `anchor` (required unless the tier is `whole`) is the whole-body mesh
  every part is registered onto; `glb_sha256` pins it, and a reader refuses a plan whose anchor file
  no longer matches. Geometry is in the anchor GLB's own frame (glTF: +Y up, front = the multi-view
  front); paths are relative to the plan.
- **Each writer owns its keys.** `part_math.py plan` writes `anchor` (with `painted_glb` when given
  `--painted`), `region_box`, the `seam` heights and `views.boxes`; `part_views.py` writes `views.dir`, `views.sheet`, `views.colours` and
  `generated`; a person edits `tier`, `preset`, `seam.mode`, `prompt_hint`, `budget_share` and
  `split.delta`. A writer rewrites only its own keys.
- **Rules the tools check** (exit 1): exactly one `source: anchor`; the tier's region set (`three`
  = body, head, hair); a split's `from` names a generated part; no `Large` on a part that carries
  hair; budget shares sum to at most 1. `fine` and `custom`, and the regions beyond body, head and
  hair, are reserved: the tools refuse them.
- `budget_share` is a fraction of the class's `3D budgets` row, never a triangle count.

## Migration (the 0.34 dialect)

The pipeline readers (autorig.py, twocam.py and the frames readers) still read
the unstamped 0.34 dialect. Each time they do, they print one `WARN` line naming the file and the
old key. `registry.py ingest` does not: it refuses `ok` at every level (exit 3).

- `frames.json` with no `schema`: read as the old dialect. `margin_px` is read as
  `foot_margin_px`. `set_metrics.key_color` is read as `key_color`. When there is no key at all,
  the fringe check reports `n/a` with a warning and is not counted as passed. A missing or zero
  `reference_core_height_px` skips the size check, with a warning.
- A gate report with no `schema`: a gate's `ok` is read as `pass`, and a report's `ok` is read as
  `pass`. Producers no longer write `ok` at either level, and a stamped gate/1 report that carries
  it is refused (see gate/1).
- A timeline meta line with `"schema": 1` is read as `timeline/1`.

Only an unstamped file gets this treatment. A file stamped `frames/1`, `gate/1` or
`timeline/1` that is missing a required key is a producer bug, and the reader fails on it rather
than warning. A Blender op that reports with zero gates is returning a result, not a gate report:
it has no `schema` or `pass`, and carries `ok`.

This reading exists only for files written before the stamps. New files are never written in the
old dialect.

## rig2d/1

- **Image pixels, y down**, on the layered file's own canvas; the Unity reader flips y. Arrays are
  flat (`hx, hy, tx, ty`; `verts` as x, y pairs; `bw` as `i0, w0, i1, w1` per vertex, indices into
  the part's own `bones`), because `JsonUtility` reads no nested arrays.
- **`layers`** is the layer order, top to bottom, and every name is the PSB layer's name: a renamed
  layer loses its rig, so the auto-rig runs again after any rename.
- **`view`** is `front` (sides `R`, `L`: the character's own) or `side` (sides `near`, `far`, with
  `facing` `right` or `left`). **`swaps`** names the layer pairs a Sprite Resolver switches
  (eyes open/closed, mouth closed/open).

## exam/1

- **One `kind` per file.** `truth` (a built body: `name`, `height`, `landmarks` in the GLB's frame,
  `fingers.separate`, `expect_fail`), `reference` (the markers a person accepted, in the prepared
  frame: `frame: "prepared"`), `fault` (`fault`, `base`, `steps` with each step's `failed_gates`) and
  `report` (`summary`, `cases`, `faults`). A landmark is `[x, y, z]` in metres, +Z up.
- **The summary** is what `bench` carries and `compare` reads: `outcomes` (case names per outcome),
  `false_pass`, `false_fail`, `faults_caught`, `faults_slipped` (`fault@base`), `control_fail` (bases)
  and `fingers_right`.
- The exam folder and its files stay outside the repository: a reference case holds a real
  character's mesh.

## bench/1

- **`exam`** is exam/1's report summary (the same required keys), or null when no exam case was
  scored. **`real`** has one entry per character folder: `name`, `stages` (per `autorig.py` step,
  `{pass, gates}`, each gate `{name, value, limit, pass, margin}` with `margin` null when the gate has
  none), `stability` (the folder's `autorig.stability.json`, gate/1, or null) and `worst_margin`.
- **`repair`** (optional, per character) is what `autorig.py`'s repair ladder did:
  - `chosen`, for the run `OUT/autorig.all.json` stands for:
    - `result`: passed, exhausted, error or not_applicable; kept_repair or kept_original after a
      near-limit ladder; or none, not_reached or unknown;
    - `trigger`: failed or near_limit;
    - `fired`, `used`, `attempts`, `hinges` and `rungs` [{hinges, amount, cross_side, passed}].
  - `runs`, after `--repeat`: {n, chosen, read, repaired, used, per_run}; null without it.

  A bench without `repair`, or with a run that was not read, reads to `compare` as `repair_unknown`.
- **`compare` keys a gate by character, step and gate name.** A margin is compared only when both
  files carry a number for it; a gate a later version renames reads as not read. It prints:
  - `regressions` and `improvements`;
  - `repair`: repair_now, repair_gone, repair_changed or repair_unknown;
  - `repair_tradeoffs`: a volume or self-intersection drop paid for by a rise in the other, when one
    side's bind is a repair and the new margin stays at `--tradeoff-floor` or above;
  - `informational`: a drop of at most `--near` that ends at `--near` or above.

  A pass to fail, `stable` and a gate no longer read always regress.
- Bench files are kept beside the exam folder, outside the repository; the repository holds the
  tools, not the scores.

## review/1

- **Two sheets, one checklist.** `sheets` is `[a, b]`: a in the spec's cell order (`order: null`),
  b the same cells shuffled by `contact_sheet.py --order` (`order[k]` = the spec item in cell k,
  `seed` from the subject's sha256). Every checklist item is answered on each:
  `answers.a` / `answers.b` = `{id: {answer: defect | clear | unsure, view: label | null, note}}`.
- **Flagged** = defect or unsure in either pass, or the passes disagree. `verdict` is `draft`
  until `prereview.py check` writes `clear` (nothing flagged) or `flagged`.
- **Paths** (the sheets, the subject) are relative to the review file's folder; `subject.sha256`
  and each sheet's `sha256` pin the bytes, and `check` refuses a review whose files changed.
- **It approves nothing.** `registry.py ingest` refuses a draft, a review whose answers no longer
  give its `flagged` ids, a sheet changed since the review, and `--status approved`; it records a
  review as `qa-sheet` with its verdict and flagged ids in `params`, and changes no status;
  `check` warns `review-flagged` when an approved asset's latest pre-review flagged items.

## skeleton/1

- Metres, +Z up, facing −Y. A file stamped `up: "+Y"` (a BVH header kept in its own axes) is turned on
  read with (x, y, z) → (x, −z, y). `units` is `m`, or `file units x S` for a BVH read at `--scale S`.
- Each bone needs `name` and `parent` (null for a root). `head` and `tail` are optional for
  `contract_map.py` (it then skips its position gates); `twocam/skeleton.py` refuses a bone without them.
- `deform` is true for a bone that deforms skin. `brt_arp` sets it from the weights, since the FBX importer
  marks every bone deform.

## motion-samples/1

- `fps`, and `joints` with one [x, y, z] per frame per joint, are required. Every other key is optional.
  Without `feet`, `motion_metrics` needs `--feet`.
- The NPZ form carries `positions` (frames, joints, 3), `names`, `fps`, optional `contacts` (frames, 2) and
  `reading_joints` with `reading_names`, and a JSON string `meta` holding the optional keys. A reader stamps
  it and rebuilds `joints`. `check-contracts.py` validates it the same way.
