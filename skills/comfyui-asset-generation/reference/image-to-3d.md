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
  To mask by the image's own alpha instead of background removal:
  `--set '312.masks=["122",1]'`.

Multi-view input is four square views with alpha or on black, straight-on at eye level, the
object about 1/1.1 of the frame at its widest and **at the same scale in every view**. Cropping
each view to its own mask breaks that for an object wider than tall (a crate's depth stretches
about 1.5×). The `left` view is taken from the object's left side: its front points to the left of
the image.

Generating the source is `codex-visual`: its reference on source images for 3D covers the
three-quarter brief and the one-row turnaround sheet, and its `turnaround_to_views.py` splits
the sheet by content into four squares of one scale.

## Run

```bash
# one image → GLB at the pickup budget
python3 scripts/comfy_asset_client.py --workflow templates/pixal3d_image_to_model_api.json \
  --output-dir out/crate --upload art/pickup_crate.png \
  --set 122.image=pickup_crate.png \
  --set 186.target_face_count=2000 --set 241.resolution=128
python3 scripts/inspect_glb.py out/crate/*.glb --max-triangles 2000 --texture-size 1024 \
  --require base,normal,occlusion,metallic-roughness

# four views → upright GLB
python3 scripts/comfy_asset_client.py --workflow templates/pixal3d_multiview_to_model_api.json \
  --output-dir out/crate_mv \
  --upload views/crate_front.png --upload views/crate_left.png \
  --upload views/crate_back.png --upload views/crate_right.png \
  --set 801.image=crate_front.png --set 802.image=crate_left.png \
  --set 803.image=crate_back.png --set 804.image=crate_right.png
```

An upload keeps its basename, and a second file of that name needs `--overwrite-uploads`: prefix
views per asset. Budgets and every other knob: `reference/image-to-3d-tuning.md`.

## What a job costs and reports

- Allow one to five minutes per job; bulk and the TRELLIS.2 path cost the most. The client's
  default timeout covers it.
- Peak VRAM is 8–17 GB above idle. Read `/system_stats` for about 18 GB free first; when short,
  `--set 94.target_resolution=1024`.
- Read `execution_cached` in the history status before assuming a mesh-only variant is cheap:
  when it lists nothing, the whole graph ran again.
- The GLB is reported under a `3d` key and the QA images as ordinary `images`; the client
  downloads both into `--output-dir`.
- The GLB holds one mesh, one material and three images: base colour, packed
  occlusion-roughness-metallic, normal. It is centred on the origin, largest extent a little
  under 1 unit; scale carries no real-world size.

## Acceptance

`scripts/inspect_glb.py` is the numeric gate: exit 0 pass, 1 gate failed, 2 unreadable. It fails
a triangle count over 1.05× `--max-triangles` or under half of it, more than one material, an
image over `--texture-size`, a missing `--require` slot, a file over `--max-bytes`. `--extract
DIR` writes the embedded images out. Keep the printed `extents` to compare variants.

The renders saved under `3d/qa/` are the visual gate. Look at every one before importing:

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
  limbs chunky and evenly thick, thin parts (ears, a tail) thick and drawn the same in every
  view. Drawing and gating the sheet is `codex-visual`, its reference on source images for 3D.
- **No held prop.** Generate the prop as its own job and attach it after rigging.
- **The close-up budget.** The visible surface gets half the triangles, and a joint that bends
  needs them.
- A-pose is what `blender-character-rig` takes. Mixamo wants a T-pose: read
  `unity-rigged-character` before drawing the views for that route.

```bash
python3 scripts/comfy_asset_client.py --workflow templates/pixal3d_multiview_to_model_api.json \
  --output-dir out/runner \
  --upload views/runner_front.png --upload views/runner_left.png \
  --upload views/runner_back.png --upload views/runner_right.png \
  --set 801.image=runner_front.png --set 802.image=runner_left.png \
  --set 803.image=runner_back.png --set 804.image=runner_right.png \
  --set 186.target_face_count=20000 --set 241.resolution=768 --set 288.value=2048
python3 scripts/inspect_glb.py out/runner/*.glb --max-triangles 20000 --texture-size 2048
```

On `clay`, on top of the acceptance table: each arm separate from the torso, a gap between the
legs, both ears and the tail present and not fused to the head or body. A limb fused to the body
cannot be skinned apart: fix the views and regenerate.

## Hand-off

The result is an unrigged mesh, and it leaves by one of two routes. A prop is imported as it is:
`unity-3d-models`. A character is rigged first and reaches Unity as FBX: `blender-character-rig`
for chibi or short-limbed proportions, extra parts (ears, a tail) or a custom action; Mixamo in
`unity-rigged-character` for standard humanoid proportions and stock clips. These facts go with
it either way:

- The file is already at budget, with normal map and occlusion baked from the dense mesh onto
  the decimated one. Simplifying it afterwards with gltf-transform breaks that match: set the
  budget in the graph and regenerate.
- That holds for a character too: welding or decimating the GLB in a glTF tool is still wrong.
  The weld by position inside `blender-character-rig` is a different operation — it merges the
  vertices split at UV seams, keeps every face and island, and has its own check (that skill's
  import-and-survey reference).
- The origin is the bounding-box centre, not the base: scale and offset the `Model` child, and
  rotate it for a Pixal3D single-image mesh.
- One material, exported double-sided (`double_sided` in the gate's output). The mesh is a
  double shell, so make the imported material front-face only
  (`reference/image-to-3d-tuning.md`).
