# Image to 3D — an unrigged mesh from one image or four views

Three API templates turn images into a textured GLB with core ComfyUI nodes only. They share one
back half — structure → shape → texture → remesh → decimate → unwrap → bake → save, plus QA
renders — and differ in the front half:

| Template | Input | Front half |
|---|---|---|
| `templates/pixal3d_image_to_model_api.json` | one image, node `122` | background removal, crop, field-of-view estimate, Pixal3D |
| `templates/trellis2_image_to_model_api.json` | one image, node `122` | background removal, crop, TRELLIS.2 |
| `templates/pixal3d_multiview_to_model_api.json` | four views, nodes `801`–`804` | no background removal; Pixal3D multi-view |

## Components

Verify every filename against live `/object_info` before the first job.

| Role | Folder | File |
|---|---|---|
| Pixal3D diffusion model | `diffusion_models` | `pixal3d_int8_convrot.safetensors` |
| Pixal3D multi-view diffusion model | `diffusion_models` | `pixal3d_multiview_int8_convrot.safetensors` |
| TRELLIS.2 diffusion model | `diffusion_models` | `trellis_2_int8_convrot.safetensors` |
| Shape VAE (shared) | `vae` | `trellis_2_shape_vae_bf16.safetensors` |
| Texture VAE (shared) | `vae` | `trellis_2_texture_vae_bf16.safetensors` |
| Image encoder (shared) | `clip_vision` | `dino_v3_L_naf_fp32.safetensors` |
| FoV estimate (Pixal3D single image) | `geometry_estimation` | `moge_2_vitl_normal_fp16.safetensors` |
| Background removal (single image) | `background_removal` | `birefnet.safetensors` |

About 15 GB on disk for the single-image set. The three diffusion models are one family for
scheduling (`reference/operations.md`).

## Choosing a path

| | Pixal3D, one image | Pixal3D multi-view | TRELLIS.2, one image |
|---|---|---|---|
| Pose | the pose of the input view: a three-quarter view from above gives a mesh tilted in world space | axis-aligned, posed to the front view | its own upright pose; a flat object can come back with its thin axis on X |
| Fidelity | highest: texture and silhouette match the image | high on the four seen sides; darker and less saturated | lowest: a latch or emblem smears or drops, hue drifts |
| Unseen sides | back and underside invented | top and bottom invented: a lid emblem is lost | invented |
| Proportions | right from a three-quarter view; wrong from a straight-on view (a crate comes back 2.5× too deep) | right, when the four views share one scale | plausible, not faithful |
| Use it for | a hero prop where one view carries the design; rotate it upright afterwards | hard-surface props that must stand upright with true proportions | a quick upright blockout; a fallback when Pixal3D misreads the object |

- Pixal3D single image takes a three-quarter view — front, one side and the top visible. Never
  give it a straight-on elevation alone.
- The Pixal3D tilt is not an error to tune away: rotate the `Model` child in Unity, or use the
  multi-view path.
- A level turnaround never shows the top, the face a runner camera sees most. For a pickup whose
  top carries the design, take the single-image path.

## Input image

The single-image templates mask the subject and cut it out at 1024×1024 on black; that crop is
all the model sees. Outside the mask is gone (floor, cast shadow, glow halo). Inside it is
geometry or texture: an attached contact shadow becomes a dark skirt, highlights become albedo,
glow becomes painted-on colour.

- One object, whole in frame, about 80% of it; chunky, because thin floating parts (straps,
  antennae) fuse or drop. A 1254 px square source is already enough; do not upscale.
- Soft even lighting; no cast shadow, ground plane or rim glow.
- No special background is needed: mid-grey, the project's key colour and alpha convert alike.
  To mask by the image's own alpha instead of background removal, use a copy of the graph with
  `"313": {"class_type": "InvertMask", "inputs": {"mask": ["122", 1]}}` added and
  `--set '312.masks=["313",0]'`: `LoadImage`'s mask is 1 where the image is transparent, and
  `ImageCropToMask` keeps where the mask is 1, so `["122",1]` straight into `312` crops the
  background.

Multi-view input is four square views with alpha or on black, straight-on at eye level, the
object about 1/1.1 of the frame at its widest and **at the same scale in every view**. Cropping
each view to its own mask breaks that for an object wider than tall (a crate's depth stretches
about 1.5×). The `left` view is taken from the object's left side: its front points to the left of
the image.

Generating the source is `codex-visual`: its reference on source images for 3D covers the
three-quarter brief and the one-row turnaround sheet, and its `turnaround_to_views.py` splits
the sheet by content into four squares of one scale.

### Background removal for four views

The multi-view template does no background removal. A sheet drawn on pure black can still carry
a soft halo, a contact shadow or near-black noise, and the model can rebuild any of it as thin
sheets; removal can also eat dark hair, a dark shoe or a thin part. So clean the four views on
the server first and keep three outputs per view: the **RGBA cut-out**, the **mask preview**, and
the **black composite** — the file the generation job uploads.

`templates/four_view_background_removal_api.json` is that graph: core nodes and the BiRefNet
component of the single-image templates, one block per view.

| Node (front; left 20–28, back 30–38, right 40–48) | Class | Inputs |
|---|---|---|
| `1` | LoadBackgroundRemovalModel | `bg_removal_name` `birefnet.safetensors` |
| `2` | EmptyImage | width and height = the views' side (`turnaround_to_views.py --size`, default 1024), `color` 0: the black square |
| `10` | LoadImage | `REPLACE_WITH_FRONT_VIEW.png` |
| `11` | RemoveBackground | `bg_removal_model` ← `1`, `image` ← `10` |
| `12` | InvertMask | `mask` ← `11` |
| `13` | JoinImageWithAlpha | `image` ← `10`, `alpha` ← `12` |
| `14` | SaveImage | `13`, prefix `3d/clean/front_rgba` |
| `15`, `16` | MaskToImage → SaveImage | `11`, prefix `3d/clean/front_mask` |
| `17`, `18` | ImageCompositeMasked → SaveImage | `destination` ← `2`, `source` ← `10`, `mask` ← `11`, `x` 0, `y` 0, `resize_source` false; prefix `3d/clean/front_black` |

The masks point two ways, and the wiring above is fixed, not a choice per run:
`RemoveBackground` gives 1 on the subject, which `ImageCompositeMasked` and `ImageCropToMask` take
as is; `JoinImageWithAlpha` writes alpha = 1 − mask (it takes `LoadImage`'s convention, 1 where
transparent), so its alpha goes through `12`. Fed `11` directly it returns the subject transparent
and the background opaque.

```bash
python3 scripts/comfy_asset_client.py --workflow templates/four_view_background_removal_api.json \
  --output-dir work/clean --upload runner_front_r03.png --upload runner_left_r03.png \
  --upload runner_back_r03.png --upload runner_right_r03.png \
  --set 10.image=runner_front_r03.png --set 20.image=runner_left_r03.png \
  --set 30.image=runner_back_r03.png --set 40.image=runner_right_r03.png
#   saves 3d/clean/<view>_rgba, _mask and _black; set 14/16/18 (24/26/28, …) filename_prefix per asset
```

- **Open the outputs of the first view before trusting the batch.** The mask preview white on
  the subject, the RGBA transparent around it and opaque on it, the black composite showing the
  subject, not a hole, at the view's own size (a black square of another size crops the view or
  leaves it in a corner: set `2` to match). An inverted result means the graph was edited: a
  missing `12`, or `12` moved onto `15` or `17`.
- **Check what removal took.** Hair, hands, feet and thin parts present in the RGBA over a light
  and a dark backdrop; a part that went missing is lost to the mesh too.
- **Upload names are unique per asset, view and run** (`runner_front_r03.png`, then `_r04`): the
  server serves an older file of the same name without an error
  (`reference/image-to-3d-tuning.md`, Diagnosing a bad shell by stage). The names in the
  generation job's `--set 801.image=…` are the black composites' names.
- Removal is a checkpoint, not a cure: sheets can survive a clean mask (the diagnosis order in
  the tuning reference).

## Run

```bash
# one image → GLB at the small preset
python3 scripts/comfy_asset_client.py --workflow templates/pixal3d_image_to_model_api.json \
  --output-dir out/crate --upload art/pickup_crate.png \
  --set 122.image=pickup_crate.png \
  --set 186.target_face_count=2000 --set 241.resolution=128 --set 288.value=1024
python3 scripts/inspect_glb.py out/crate/*.glb --max-triangles 2000 --texture-size 1024 \
  --require base,normal,occlusion,metallic-roughness

# four views → upright GLB
python3 scripts/comfy_asset_client.py --workflow templates/pixal3d_multiview_to_model_api.json \
  --output-dir out/crate_mv \
  --upload views/crate_front_r01.png --upload views/crate_left_r01.png \
  --upload views/crate_back_r01.png --upload views/crate_right_r01.png \
  --set 801.image=crate_front_r01.png --set 802.image=crate_left_r01.png \
  --set 803.image=crate_back_r01.png --set 804.image=crate_right_r01.png
```

An upload keeps its basename, and the server keeps the first file of a name: name each upload by
asset, view and run (`crate_front_r01.png`), and read the client's stderr for an upload stored
under another name. Before a tuning run, diff the graph against the official template
(`reference/image-to-3d-tuning.md`). Generation presets and every other knob: `reference/image-to-3d-tuning.md`. What
a class of asset may cost is not set here: `unity-3d-models` → `reference/budgets.md`.

## What a job costs and reports

- Allow one to five minutes per job; bulk and the TRELLIS.2 path cost the most. The client's
  default timeout covers it.
- Peak VRAM is 8–17 GB above idle. Read `/system_stats` for about 18 GB free first; when short,
  `--set 94.target_resolution=1024`.
- Read `execution_cached` in the history status before assuming a mesh-only variant is cheap:
  when it lists nothing, the whole graph ran again.
- The GLB is reported under a `3d` key and the QA images as ordinary `images`; the client
  downloads both into `--output-dir`.
- The client's JSON pins the run for skill `art-asset-registry`: `workflow_sha256` and
  `workflow_name` (the template's hash and file name), `overrides` (each `--set` target with its
  value: numbers, booleans and links as they are, any text as `sha256:` and 12 hex characters),
  `server_label`, `output_files` (each download with its `sha256` and `bytes`; `outputs` stays a
  list of paths), a `sha256` on each `uploads` entry, and `record`, the partial ledger record
  (`tool`, `params`, `inputs`, `files`, `verdict`).
- `--server-label NAME` names the machine (`studio-gpu`); a label holding `://` is refused. No
  server address is written to the output or to the job log. `--job-log PATH` appends one JSON
  line per run, success or failure, with `ts` and `exit_code`; a failed run's line carries its
  `error`, with the address and any URL replaced, and a `record` whose verdict is `failed` once
  the graph was submitted, `harness` before. A failure still exits 1.
- The GLB holds one mesh, one material and three images: base colour, packed
  occlusion-roughness-metallic, normal. It is centred on the origin, largest extent a little
  under 1 unit; scale carries no real-world size.

## Acceptance

`scripts/inspect_glb.py` is the numeric gate: exit 0 pass, 1 gate failed, 2 unreadable. It fails
a triangle count over 1.05× `--max-triangles` (the face target the graph was given) or under half
of it, more than one material, an image over `--texture-size`, a missing `--require` slot, a file
over `--max-bytes`. `--extract DIR` writes the embedded images out. Keep the printed `extents` to
compare variants.

```bash
python3 scripts/inspect_glb.py out/crate/*.glb --class pickup --budgets ART_DIRECTION.md \
  --json-out out/crate/inspect.json
```

`--budgets FILE --class CLASS` reads that class's row of the project's `3D budgets` table (rows
chosen by `unity-3d-models` → `reference/budgets.md`); a file without the table only reports. The
script's header says what each column gates. The JSON adds `gates` (one `{name, value, limit,
pass}` per check), `warnings`, `sha256` and `record`, the partial ledger record for skill
`art-asset-registry`; `--json-out PATH` writes the same object to a file.

The renders saved under `3d/qa/` are the visual gate. Look at every one before importing, on
one 8-view sheet (4 × 2 cells of 512 px: front, left, back, right, top, clay, occlusion,
uv_atlas) composed by `codex-visual` → `scripts/contact_sheet.py` with `--require` on the gate's
JSON, so a sheet exists only for a mesh whose numbers passed:

| Image | Check |
|---|---|
| `crop` (single image) | whole subject, nothing cut by the mask, no shadow attached |
| `front`, `right`, `back`, `left` | pose as the path predicts, depth in proportion, no hue shift between sides |
| `top` | the design is there, not a smear |
| `clay` | silhouette intact, no holes, thin parts neither fused nor missing |
| `occlusion` | no black speckle inside otherwise-white charts |
| `uv_atlas` | charts are islands, not one per triangle |

## Failure classes

| Response | Do |
|---|---|
| `Refusing to submit: unfilled placeholders` | a `REPLACE_WITH_…` input remains: `--set 122.image=<uploaded name>`, or all of `801`–`804` |
| `Refusing to submit: ComfyUI has a running or pending job` | someone else is using the server: wait for an empty queue, never work around it |
| `node_errors` | a node class or component file is missing: report it, do not retry unchanged |
| `status_str: error` | report the failing node; when out of memory, lower `94.target_resolution` and retry once |
| success, but a gate or render fails | the symptom table in `reference/image-to-3d-tuning.md` |

## A character

A character that will be rigged takes the multi-view template only: the rig needs a mesh that
stands upright, axis-aligned and in true proportion, and the single-image paths return a tilted
mesh or invent the back.

- **Four views of one pose at one scale.** FRONT, LEFT, BACK, RIGHT of a strict symmetric
  A-pose: arms straight, about 45° down and clear of the hips, legs apart with a visible gap,
  empty hands, true side views. A mascot has chunky limbs and thin parts (ears, a tail) drawn
  thick and the same in every view; a realistic humanoid has separated fingers only where a close
  grip matters. Drawing and gating the sheet is `codex-visual` → `reference/image-to-3d-input.md`
  (§9); clean each view (Background removal for four views, above).
- **No held prop.** Generate the prop as its own job, at the same scale, and attach it after
  rigging.
- **The ladder up to Showcase; the `character` row picks.** Generating each preset once is cheap
  (`reference/image-to-3d-tuning.md`); which one ships is the `character` row of the budget,
  `unity-3d-models` → `reference/budgets.md`. The visible surface gets half the triangles, and a
  joint that bends needs them: below Large, look at the joints in an extreme pose before
  accepting a rung; one that deforms badly goes to route B of `blender-character-rig` →
  `reference/game-mesh.md`.

```bash
python3 scripts/comfy_asset_client.py --workflow templates/pixal3d_multiview_to_model_api.json \
  --output-dir out/runner_r03 \
  --upload clean/runner_front_r03_black.png --upload clean/runner_left_r03_black.png \
  --upload clean/runner_back_r03_black.png --upload clean/runner_right_r03_black.png \
  --set 801.image=runner_front_r03_black.png --set 802.image=runner_left_r03_black.png \
  --set 803.image=runner_back_r03_black.png --set 804.image=runner_right_r03_black.png
python3 scripts/inspect_glb.py out/runner_r03/*.glb --max-triangles 70000 --texture-size 2048
```

On `clay`, on top of the acceptance table: each arm separate from the torso, a gap between the
legs, every thin part present and not fused to the head or body. A limb fused to the body
cannot be skinned apart: fix the views and regenerate.

## Hand-off

The result is an unrigged mesh. A prop is imported as it is: `unity-3d-models`. A character's
route — body type, rigging tool, motion source, preview or ship track — is chosen once, at the
start, in `game-character-pipeline`; in short: a standard humanoid with Auto-Rig Pro installed
is rigged and gets its clips in `blender-retarget`; a custom body (short limbs, ears, a tail) is
rigged in `blender-character-rig`; Mixamo through `unity-rigged-character` is an optional route.
The preview track rigs the generated mesh as it is; the ship track makes the game mesh first and
rigs once. These facts go with it either way:

- The file is already at the face target the graph was given, with normal map and occlusion
  baked from the dense mesh onto the decimated one. Simplifying it afterwards with gltf-transform
  breaks that match: regenerate at the target preset, or retopologise and rebake from the dense
  mesh (`blender-character-rig` → `reference/game-mesh.md`).
- Any decimation happens before rigging: decimating a rigged mesh breaks its weights and UVs.
- Welding or decimating a character's GLB in a glTF tool is still wrong. The weld by position
  inside `blender-character-rig` is a different operation — it merges the vertices split at UV
  seams, keeps every face and island, and has its own check (that skill's import-and-survey
  reference).
- The origin is the bounding-box centre, not the base: scale and offset the `Model` child, and
  rotate it for a Pixal3D single-image mesh.
- One material, exported double-sided (`double_sided` in the gate's output). The mesh is a
  double shell, so make the imported material front-face only
  (`reference/image-to-3d-tuning.md`).
