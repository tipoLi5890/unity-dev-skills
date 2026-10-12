# Changelog

Versions are the plugin's, in `.claude-plugin/plugin.json`.

## 0.19.0

`comfyui-asset-generation` grows image-to-3D: one image or four views become a game-budget GLB on
a self-hosted ComfyUI, and the budget is set where the mesh is generated — not repaired after it.
The same release teaches its music to stay instrumental when it is a background bed, and gives
`codex-visual` a call that proves it produced a file and a gate on the image before a conversion.

- **Three API templates**, core nodes only: `templates/pixal3d_image_to_model_api.json` and
  `templates/trellis2_image_to_model_api.json` (one image → GLB) and
  `templates/pixal3d_multiview_to_model_api.json` (four views → GLB). The saved UI workflow picks
  its path with switch nodes; an API graph has nobody to flip them, so each switch is resolved
  statically into one template per path. Node ids are the UI workflow's, so a knob has the same
  address in both.
- **Six deliberate differences from the saved UI workflow**: 8000 faces instead of 700000, a 384
  remesh instead of 768, a 1024 texture instead of 4096, the normal bake tied to that texture size
  instead of a fixed 2048, occlusion `bias` 0.05 instead of 0.01, unwrap `padding` 4 instead of 1.
  The UI values make a ~65 MB showcase file; the defaults make a ~4 MB hero. The presets are named
  for the rows of `unity-3d-models`' triangle-budget table and sit inside them — pickup 2000,
  obstacle or environment prop 4000, hero 8000 — with a 20000-face close-up prop above the table.
- **Which path is the decision that matters.** Pixal3D from one image is pixel-aligned: highest
  fidelity, but the mesh takes the pose of the input view — a three-quarter view from above comes
  back tilted in world space, and a straight-on view comes back upright with invented depth (a
  pickup crate 2.5× too deep). Pixal3D multi-view is axis-aligned with true proportions on the
  four seen sides, a little darker than the input, and invents the top a level turnaround never
  shows — a lid emblem is lost. TRELLIS.2 gives an upright pose of its own at the lowest fidelity:
  small details smear, hue drifts. The pose is not an error to tune away: rotate in Unity, or
  take the multi-view path.
- **The one-scale finding.** The multi-view model wants the same scale in every view. Cropping
  each sheet panel to its own mask keeps one scale only when every view is height-limited; on an
  object wider than tall the front is fitted to its width and the side to its height, and a crate
  came back with its depth at 0.88 of the width instead of 0.56. `codex-visual` gains
  **`scripts/turnaround_to_views.py`**, which splits a one-row turnaround by content (panels are
  not equal width) and cuts all four views as squares of one side — which is why the multi-view
  template takes four prepared views and has no background-removal step.
- **The left/right finding.** Side views fed swapped do not break the geometry of a
  near-symmetric object; they show up as colour — orange turned yellow-green and bled across
  neighbouring panels. Re-seeding does not fix it; swapping nodes `802` and `804` does, and is the
  first move on any hue shift.
- **Face target and remesh resolution move together.** 5000 faces asked of a 768 remesh shredded
  the mesh: a thin part vanished, the silhouette collapsed and the bounding box shrank 12%. 4000
  from a 256 remesh and 2000 from 128 held both. Skipping the remesh breaks too — half the
  requested faces, shrunken bounds, three times the run time. A shrunken `extents` against a
  higher-budget run of the same input is the tell.
- **The double shell.** Every face has an opposite-facing twin a fraction of a percent of the
  bounding-box diagonal behind it, on both model paths, and no remesh option removes it
  (`sign_mode` sdf damages the mesh on top). It faces away from the viewer, so a budget of N
  triangles buys the visible detail of N/2 — and the GLB's material is exported double-sided, so
  the imported material is set to front faces only.
- **The occlusion finding.** At the UI workflow's `bias` 0.01, 6–24% of the outward-facing surface
  bakes pure black; at 0.05 it is 1–3%, at 0.1 about none. The map still looks half black at any
  bias, because the inner shell is legitimately dark and owns half the atlas — so it is judged by
  shape: whole black charts are the shell, speckle inside a lit chart is the error.
- **Two gates.** **`scripts/inspect_glb.py`** is the numeric one: triangles against a budget (over
  by 5% or under half of it fails), material count, texture size, required texture slots, bytes;
  exit 0 / 1 / 2, one JSON object out. The QA renders each template saves beside the GLB are the
  visual one — `front`, `right`, `back`, `left`, `top`, `clay`, `occlusion`, `uv_atlas`, and on
  the single-image templates `crop`, which is all the model saw of the input.
- **`scripts/comfy_asset_client.py`** takes a repeatable `--set NODE.INPUT=VALUE` (JSON when it
  parses, so a list rewires a link), refuses to submit while any input still holds a
  `REPLACE_WITH_` placeholder, and prints `elapsed_seconds` and `vram_free_min`.
- **`codex-visual`** gains `reference/image-to-3d-input.md` — the image a 3D graph can use: the
  mask crop is everything the model sees, lighting in the image becomes base colour, a contact
  shadow becomes geometry, the project's usual key colour needs no change, and a turnaround is
  asked as four objects in one row on flat black with the approved three-quarter image attached.
- **An instrumental bed that stays instrumental.** MiniMax Music 3 is a song model, and a
  background bed with a voice in it fights the game's own sound. Fifty-odd 30-second takes across
  a chase bed, a menu bed and a world-map bed, each screened by separating the vocal stem and
  tagging the stem: a plain caption with **empty lyrics** came back with a hum or a voice on 4 of
  8; `[Instrumental]` in the lyrics on 1 of 8; a caption that only mentioned a choir pad on 1 of
  2; and the form now documented — a three-section caption whose Vocal Details spell the
  exclusions out and name the lead instrument, with `[Intro]` / `[Instrumental]` / `[Outro]` as
  the only lyrics — on 1 of 23. **`reference/instrumental-bgm.md`** carries that wording, a
  caption skeleton, what makes a caption a bed rather than a song, and three worked captions for
  the courier run. Length is the other finding: `max_duration` is only a ceiling — a 90-second
  request with one described section came back at 26–35 s, and the same bed with five described
  sections at one to two minutes, varying by seed. **`scripts/check_instrumental.py`** is the
  screen (a stem separator alone calls a flute a voice; the tagger on the stem tells them apart),
  and the client's `--set` takes `@file`, so a caption with line breaks is not a shell-quoting
  problem. The music template's default lyrics are now `[Intro]` / `[Instrumental]` / `[Outro]`.
- **`codex-visual` is easier to enter and harder to fool.** `SKILL.md` opens on a table from what
  you want (a set that matches, a loop that jitters, a fringed cut-out, a source image for 3D) to
  where to read. **`scripts/codex_generate.py`** makes the generation call and proves it:
  `codex exec` exits 0 when the agent model is rejected and when no image was made, so the script
  probes the model, runs from a scratch directory (the image tool leaves a copy under `output/`
  wherever it runs), takes the original from `generated_images` and reads back its size — exit 3
  for a rejected model, 4 for no image. **`scripts/audit_3d_source.py`** gates an image before a
  conversion: square, a flat field out to the frame, one piece, clear of the edge; and with
  `--views`, four views at one scale. `reference/animation-sheets.md` had grown to three times the
  size of `SKILL.md` and is now three files by purpose — the prompt side stays there, diagnosis
  and acceptance thresholds are `reference/animation-faults.md`, script usage, previews, the
  pixel post-process and the handoff are `reference/animation-scripts.md` — with every pointer
  renumbered. `SKILL.md` no longer repeats the four locks in full and has room again.
- **`unity-3d-models`** no longer tells you to simplify a mesh that was generated at budget: its
  normal map and occlusion are baked from the dense mesh onto the decimated one, and a later
  simplify throws that correspondence away. Inspect first; set the budget in the graph and
  regenerate. Largest extent is about 1 unit with the origin at the bounding-box centre, so scale
  and offset go on the `Model` child.

## 0.18.0

`codex-visual` learns that position and size are never the model's job — and gets the scripts
that make the promise hold, plus the gate that reads it back from the files that shipped.

- **The stray-pixel finding.** A keyed render keeps one or two pixels at alpha ~20 in a canvas
  corner. `slice_grid.py` and `normalize_set.py` measured a plain `alpha > 16` bounding box, so
  that pixel dragged the box to the canvas edge: a set asked at 78% of the canvas shipped at 58–68%,
  pushed up to 14% of the canvas off-centre, per asset by a different amount — and read as "the
  model draws some sprites off-centre". A set shrunk the same way in every cell was even internally
  consistent (identical bboxes, 0% spread), so the old CV line passed it. Both scripts now isolate
  the **subject** (pixels at alpha ≥ 96 grown through their connected soft pixels; a speck never
  joins and is cleared), place the subject's **core** (alpha > 40, so a glow's haze does not steer
  it), and paste mask-free — a masked paste onto transparency had been squaring the alpha of every
  soft rim. `--raw-bbox` keeps the old behaviour for a diff against an old delivery.
- **`scripts/audit_set.py`** — the geometry gate on shipped files: per asset the core, the centre
  offset, the fill against `--expect-frac`, the strays; the set's width/height spread; with
  `--symmetry` mirror IoU, tilt and rim level for upright objects. Exit 1 on a centre over 2 px or
  a fill more than 0.02 off. It is the step between "normalised" and "registered".
- **`slice_grid.py`** cuts on the found gutters (the emptiest row/column within a third of a cell
  of each equal split) instead of the exact split, reports a haze-only cell as EMPTY instead of
  scaling the haze up, warns when a subject — not its haze — touches the cell edge, and takes
  `--canvas-h` for a non-square asset. **`normalize_set.py --recenter`** repairs a shipped set by
  translation only, no rescale, for the files whose keyed source is gone.
- **`sheet_to_frames.py --drop-strays`** — the same speck, in an animation sheet, gives one cell
  `edge yes`, a bottom at the cell edge and a baseline of 0; the flag clears it before measuring
  and prints what it dropped, leaving the alpha ≤ 16 haze to `--clear-below-thr`.
- **`SKILL.md`** gains the symptom table for this — including the question "can I hand the model a
  1x1 / 2x2 / 4x4 template with crosshairs so it draws in the right place?" (no: it paints the
  guides and still places approximately; the grid belongs on the output side, one sheet per
  family), and why a single member regenerated alone drifts from its siblings while the same three
  on one sheet come back identical to the pixel. `reference/codex-runtime.md` §5 records it as
  keying Trap 3; §8 and `reference/image-model.md` §6 carry the new flags and the gate step.

The same rule, for **animation**: where a frame sits is never the model's job either, and neither
is its edge. Both findings come from one shipped set of 25 animation sheets whose characters
"jittered wildly" and whose cut-outs had a pink rim — re-measured from the raw sheets, old pipeline
against new.

- **The jitter finding.** `sheet_to_frames.py` kept each cell's in-cell position, on the belief that
  in a sheet of frames the arc *is* the cell-to-cell offset. On a generated sheet it is the model's
  grid: over 21 character sheets the body wandered 17–119 px inside its cell (3–24% of it), the
  grid **column** explained 81–100% of the sideways spread on 18 of them and the **row** 90–100% of
  the vertical spread on 19 — the two exceptions were a jump and a leap. Written that way, one idle
  pose sat 65–120 px apart on alternate frames and feet lines 16–57 px apart; `--align both`, the
  repair the skill offered, still left 8–45 px on 14 of 21, because a centroid is steered by a bat.
  A contact sheet tiling one frame per cell shows none of it. `--register ground | free` now seats
  every frame on one reference by its **core silhouette** (the solid shape opened by 4 px, by FFT
  overlap; feet locked to one line for a grounded action): 0 px out of register on all 21 and feet
  within 2 px on the 19 grounded ones, on the same sheets, with no regeneration — the eleven takes
  a regeneration had replaced pass too. **`--register` is required to write** (`ground` · `free` · `centroid` · `keep`);
  `keep` is the old behaviour and is gated when the kept wander follows the grid.
- **The cut finding.** The model does not draw its rows at thirds: the equal split cut the subject
  in 34 of 85 frames on one take and 21 of 85 on its regeneration with a stricter prompt (asked for
  75% of the cell height, drew 86–98%). `sheet_to_frames.py` now cuts on the found gutters, columns
  per row — 0 of 85 on both takes — and a cut already on an empty line does not move, so
  `--gutters nominal --register keep` reproduces an old set byte for byte.
- **The fringe finding.** A binary key leaves the anti-aliased rim opaque and half key: 25–40% of
  the rim within 150 RGB of the key (`fringe`) and 43–60% measurably mixed with it (`tint`);
  `remove_chroma_key.py --despill` left 5–52% / 26–84% per static asset. *Alpha Is Transparency*
  repairs transparent pixels, and these are opaque — the claim in `sheet_to_frames.py` that it
  covered this was wrong. **`scripts/key_unmix.py`** un-mixes the 2 px boundary band only (alpha
  along key→outline; `--edge fill` projects an effect's rim onto the fill beside it): 0.0–0.2% /
  0.0–0.3%, interior untouched. `--defringe` repairs sprites already shipped (49 assets to
  0.0–0.7% / 0.0–0.4%, bounding boxes within 1 px). Two simpler keys are documented as wrong, with
  numbers: alpha from RGB distance everywhere (36–83% of the interior translucent, or the rim left
  33–41% mixed), and an effect keyed by spill (a pink rim on 29% of a yellow spark) — `tint` exists
  because `fringe` reads 0.00% on both.
- **Gates instead of numbers.** `sheet_to_frames.py` ends on `verdict OK | FAIL` and **exits 3** on
  a fault with one repair: a subject cut by the sheet edge or a cell line, foreign pixels on the
  cut, frames clipped by the canvas, a feet line or a slip over its limit, grid wander under
  `keep`, key colour on the rim. The first pipeline had printed `bleed`, `content will be cropped`
  and a 22 px residual on that set and exited 0. `--no-gate` restores exit 0; `--report` can now
  fail. **`scripts/audit_frames.py`** re-reads the written PNGs (feet, slip, fringe, tint, cut;
  `--hold` classifies a one-pose loop `hold` / `BOIL`; `--onion` writes one onion skin per
  sequence), `audit_set.py --key-color` does the rim for static sets, and `frames_to_anim.py`
  gains `--onion` and `--bg`. **`scripts/sprite_ops.py`** holds the definitions all of them share,
  and is the first script here that the others import.
- **`unity-2d-sprites`** reads the new sidecar: the pivot is `pivot_norm` (the feet line, which is
  not the canvas floor once a foot margin sits under it), the canvas is whatever was fitted rather
  than 512, and a one-pose loop whose frames are different drawings (`iou_to_ref_min` 0.76–0.80
  against 0.96 for a true hold) plays ONE frame with engine motion instead of a clip.
  **`resources/Tests/SpriteFramesAudit.cs`** re-measures shipped frames in the Editor from their
  own bytes, because the slicer's verdict is the slicer's.
- **What this does not do.** It does not rescale a frame to fit: `--scale-search` exists, is off,
  and warns — on 21 sheets it gained at most 0.04 IoU and on a crouch-to-rise it shrank the
  character 4–8% with the head unchanged. It does not fix a boiling idle, only names it. It does
  not recover a jump's rise or a lunge's advance from a generated sheet (`free` holds the body
  still; travel goes on the transform) and warns when the offsets it removed did not follow the
  grid. `slice_grid.py` and `normalize_set.py` still end a resample in an alpha 1–3 ring of noise
  colour (6–9 px per 256 px icon) — `--defringe` clears it, the scripts do not yet. And
  `SpriteFramesAudit.cs` has run only in halves: its measuring kernel matched the Python gate on
  210 frames outside Unity, and its NUnit half compiles against 6000.3 and 6000.4 but has not been
  run in an Editor.

## 0.17.0

`comfyui-asset-generation` grows the MiniMax H3 path that transfers motion from a reference clip
onto a character, and hardens the two scripts around it.

- **`reference/h3-motion-transfer.md`** — one input owns identity and wardrobe, the other owns
  motion, cadence and framing, and the prompt says which is which. Why a 60 fps reference passed
  through unchanged softens the cadence, what to write instead of "fast" when timing matters, and
  a QA pass that compares motion phase at matching timestamps in a synchronized side-by-side
  rather than trusting a successful `/prompt`.
- **`scripts/prepare_h3_motion_reference.py`** — a motion reference normalized to 24 fps and an
  exact 17k+5 frame count, then read back with `ffprobe` and refused unless the frame count, rate
  and codecs are what was asked for. Audio is dropped by default; `--keep-audio` keeps it and
  verifies the track covers the whole timeline. A source too short to fill the requested frames is
  rejected before ffmpeg runs, naming the duration it would need.
- **`scripts/comfy_asset_client.py`** — `upload_image` is now `upload_asset`, because video and
  audio inputs go through the same endpoint and field name. The run reports `vram_after_unload`
  from `/system_stats`; a failure to read it no longer discards the outputs of a job that
  succeeded.

## 0.16.0

Thirty-six skills. Two new ones cover the part of the loop that happens **on a phone on your
desk** — the part an editor-side harness cannot reach.

- **`unity-device-testing`** — acceptance on a real Android or iOS device from a terminal. A probe
  scene that logs one tagged line per state change and one `k=v` line per second; an `adb` driver
  and a `devicectl` driver that assert on those lines with a timeout per step; system dialogs found
  by window focus and tapped by coordinates that respect rotation; physical steps (unplug, replug,
  background) detected **from the device** so a latency assertion starts at the real event; files
  pulled back from `persistentDataPath` on both platforms; and three exit codes — pass, a verdict
  about the app, a broken harness. Its pre-flight names the five things that look like bugs and are
  not: a dozing screen, a stale install, another app holding the hardware, an adb server restarted
  by a headless build, and a presence check that reads history instead of the present.
- **`unity-ios-build`** — from a Unity project to a process on an iPhone without opening Xcode:
  the headless build that produces an Xcode project and nothing else, an unsigned compile gate that
  needs no device, signing decided by the intersection of certificate, profile and device on this
  Mac (`doctor` prints it; the id in a certificate's name is a person, not a team), `devicectl`
  install, and `--console` as the only log channel. Native `.mm` plugins: the `.meta`, the
  `__Internal` import with stubs elsewhere, Objective-C exceptions being off, and iterating native
  code in 30 seconds by syncing into the generated project. App Store submission is out of scope.
- **Neighbours route to them.** `unity-android-release`, `unity-debug`, `unity-play-harness` and
  `unity-cli` each gained the row that hands you over.

## 0.15.0

Thirty-four load-by-situation skills, each teaching the same three things: what to check, the call
that checks it, and the script that does it for you.

- **`unity-urp-migration`** — a Built-in Render Pipeline project moved to URP in five gated phases,
  every gate read back from the **saved** project rather than from the converter log, plus the four
  traps that let a half-moved project report success: an assignment that sits in Graphics settings
  but not in the quality tiers, 3D materials claimed by the 2D shader provider, a Volume profile
  that reloads empty because its overrides were never added as sub-assets, and lighting that is
  still Built-in baked data.
- **`unity-search`** — a *find / where is / which prefabs use / what references X* question turned
  into one Unity Search query: asset type filters, folders, labels, `ref=` relationships and scene
  component queries, written out before it runs and opened in a live Editor when one is reachable.
  Read-only — it never selects, moves or edits a result.
- **`unity-cli` grows the two surfaces a repo hits first.** `reference/version-control.md` covers
  the verbs that know what a scene is — `vcs diff` and `blame` by object and field with their
  identity-confidence levels, `merge-setup` and its `--check` exit, `sync`/`switch` refusing while
  an Editor holds the project, `affected`/`summarize` and why their answer is a lower bound, and
  the three different meanings of `--since`. `reference/ci-preflight.md` covers `unity ci init`,
  the `doctor --ci` exit codes that say whether a retry is honest, and `cache key`.
- **The TMP Essentials import no longer hard-codes a package path.** `unity-localization` scans
  `Library/PackageCache` for the resource package instead, and names the menu item that returns
  `true` and then blocks a headless run on a modal dialog.
- **Smaller additions across the UI, 2D, runtime and backend skills** — USS patterns, sprite and
  atlas scripts, NavMesh areas and costs, a URP pre-flight snippet, package selection, and the
  documentation maps the services SDKs publish.
- **One layout for every skill.** `SKILL.md` is a router with a symptom table; `reference/` holds
  the depth it names; `resources/`, `scripts/` and `templates/` hold what you run or copy. No skill
  keeps content at its own root.
- **Every section is a method section** — what to check and how to check it, in present tense,
  never a record of how this repo checked it. A doubt that should change what you do is written as
  a step you run, not as a hedge.
- **Package tables** keep ids and API floors, and point at `Packages/packages-lock.json` for what
  actually resolved.
- **Skills route to each other, never out of the repo.** Each one's `Scope — what this skill does
  NOT do` section hands you to the right neighbour, so you land in the right skill from any
  direction.
- **Gates, run by CI on every push and pull request:** `tools/lint-skills.py` (frontmatter, name
  matches directory, shipped executables parse), `tools/check-consistency.py` (the two manifests
  agree, every route out of this repo is declared) and `tools/sync-codex-manifests.py` (the Codex
  manifests are generated — never hand-edit them).
