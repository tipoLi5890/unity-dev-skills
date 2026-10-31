---
name: mesh-texture-paint
description: "Repaint an image-to-3D mesh's texture from concept art, view by view, with a local edit model."
---

# mesh-texture-paint — keep the mesh, repaint the colour

Image-to-3D gives a good shape and a dull, blotchy, guessed texture. This skill keeps the mesh, its
UVs, normal and occlusion maps, and repaints only the base colour: render the mesh from a camera,
have a local image-edit model paint that view to match the concept art, register and gate the
result, project the painted pixels into the UV texture, pick the next camera, repeat.

## Start here — request / symptom → where to look

| Request or symptom | Go to |
|---|---|
| "Repaint this dull Pixal3D texture from the concept art" (a character) | `reference/pipeline.md` §1–4 |
| The same for a prop (the courier backpack, a parcel crate, a cone) | `reference/pipeline.md` §1, §4 (`--kind object`) |
| The face is blurry | `reference/projection.md` §7 (`--detail head`) |
| A collage of several small figures in one view | `reference/painting.md` §3; `reference/gates.md` §2 |
| Dark hair or fabric came back silver or grey | `reference/painting.md` §5; `reference/troubleshooting.md` |
| A purple or olive tint spreading | `reference/painting.md` §5 (rejected markers) |
| A green fringe on the edges | `reference/painting.md` §6 (despill) |
| Side views rejected | `reference/troubleshooting.md` (Cameras); `reference/gates.md` §5 |
| Low-angle or top-down views rejected | `reference/projection.md` §1 (pitch band) |
| Zoomed views of a thin prop fail | `reference/projection.md` §5 (thin meshes) |
| One view keeps failing | `reference/gates.md` §2, §5; `reference/troubleshooting.md` |
| Coverage stops early | `reference/projection.md` §6; `reference/troubleshooting.md` (The loop) |
| Resume an interrupted run | `reference/pipeline.md` §5 (`--resume`) |
| The server names the model files differently | `reference/painting.md` §7 (`--models`) |

> **A painted view is evidence, not paint.** Every view is registered to the render and passes six
> gates before a pixel reaches the texture; a view that fails is re-tried with another seed or
> reference, then dropped. Nothing is painted by hand and no view is projected unchecked.

## Rules the route is built on

- **The mesh stays.** Geometry, UVs, normal and occlusion come out of the image-to-3D GLB
  untouched; the finished GLB differs only in its base-colour image.
- **Two images per paint call, never three.** Picture 1 is the guide render (its layout is kept),
  picture 2 one reference. A third image makes the model leave the guide almost unpainted.
- **Qwen-Image-Edit-2511 + the 4-step Lightning LoRA**, latent = the guide's own VAE encoding,
  denoise 1. Without Lightning (20 steps) the output is ghostly; denoise under 1 returns the guide.
- **Unpainted surface shows a prior, never a marker.** The mesh's own image-to-3D texture,
  brightness-matched with one gain/offset for all channels. Grey reads as grey material (silver
  hair), magenta bleeds into purple, per-channel matching tints greys olive.
- **The sheet first, the nearest single view as fallback.** A sheet can produce a collage, a
  single view can copy its own facing; each try alternates.
- **Steep cameras are not used.** Pitch stays in −40…50°; steeper views come back drawn at eye
  level. Undersides keep the prior.
- **Licences:** the edit model and its Lightning LoRA are Apache-2.0; no non-commercial rasteriser
  (projection is numpy); table in `reference/painting.md` §8.

## Files

| Path | Role |
|---|---|
| `scripts/paint_loop.py` | the loop: cameras, context renders, paint tries, gates, projection, outputs |
| `scripts/mvtex.py` | geometry core: GLB read/write, camera, rasteriser, alignment, gates, back-projection |
| `scripts/qwen_paint.py` | one paint call on ComfyUI through `comfyui-asset-generation`'s client; `--models` |
| `templates/qwen_image_edit_2511_view_paint_api.json` | the paint graph as an API template |
| `reference/pipeline.md` | concept → background removal → Pixal3D → paint → hand-off, with commands |
| `reference/painting.md` | the graph, the prompts, the reference, the context prior, despill, licences |
| `reference/projection.md` | cameras, visibility, weights, refine, colour match, NBV, zoom, coverage |
| `reference/gates.md` | each gate, its default and what it catches; `report.json` |
| `reference/troubleshooting.md` | symptom → cause → fix |

```bash
S=<repo>/skills/mesh-texture-paint/scripts     # python3 with numpy, scipy and Pillow
python3 "$S/mvtex.py" --selftest && python3 "$S/paint_loop.py" --selftest && python3 "$S/qwen_paint.py" --selftest
```

The self-tests need no server. A paint run needs a ComfyUI server with the four model files
(`reference/painting.md` §1) and `comfyui-asset-generation` installed beside this skill.

## The route

| Stage | Run | Gate before the next stage |
|---|---|---|
| 1. Concept | `codex-visual`: three-quarter hero, then a 4:1 FRONT / LEFT / BACK / RIGHT sheet on black; `turnaround_to_views.py` | a person approves the hero; `audit_3d_source.py --views` exit 0; `left.png` faces left |
| 2. Background removal | `comfyui-asset-generation` `four_view_background_removal_api.json` | the black composites show the whole subject; skipping it gives black slabs |
| 3. Mesh | `pixal3d_multiview_to_model_api.json` | `inspect_glb.py` exit 0; the GLB has UVs and a base-colour image |
| 4. Paint | `paint_loop.py` | `turntable.png` looked at; `coverage.png`; `report.json` |
| 5. Check | `inspect_glb.py --require base,normal,occlusion` on the painted GLB | exit 0 |
| 6. Hand on | a character to `game-character-pipeline` S4 (Blender normalise); a prop to `unity-3d-models` | then `/free` on the server |

## Quick start

```bash
python3 "$S/paint_loop.py" out/runner_r01/runner.glb \
  --concept views/runner --sheet runner_sheet.png --out paint/runner \
  --kind character --subject "courier runner" --detail head --server "$COMFYUI_SERVER_URL"
```

A prop: `--kind object --subject "courier backpack"`, no `--detail`. A runner reaches about 0.88
of its seeable surface in about 13 painted views plus three head passes; a prop about 0.7, its
underside staying on the prior. Thin props (a flat sign, a thin frame) paint without zoom and with
a lower IoU around holes.

## Outputs

In `--out`: `basecolor.png` (the new texture, gutter filled), `<glb-stem>_painted.glb` (the input
GLB with only that image replaced), `coverage.png` (white painted, grey seeable but unpainted),
`turntable.png` (eight yaws, `--compare` adds a before row), `report.json` (`reference/gates.md`
§6), `views/` (each view's `_guide.png`, raw `_s<seed>.png` and `_aligned.png`) and `state.npz`
(for `--resume`).

## Scope — what this skill does NOT do

- **New geometry** — the mesh, its UVs and its faces come from `comfyui-asset-generation`; a wrong
  shape goes back there. Remeshing and retopology: `blender-character-rig`.
- **PBR beyond base colour** — roughness, metallic, normal and occlusion are kept as generated, not
  painted.
- **Rigging and animation** — `character-autorig`, in the order `game-character-pipeline` sets.
- **The concept art** — the hero image, the sheet, the style: `codex-visual`.
- **Running the server** — uploads, queue, model loading, `/free`: `comfyui-asset-generation`.
- **Unity import** — `unity-3d-models`.

Related: `codex-visual` → `reference/image-to-3d-input.md` (the turnaround), `comfyui-asset-generation`
→ `reference/image-to-3d.md` (the mesh and its gate), `game-character-pipeline` (where a character
goes next), `unity-3d-models` (import and budgets), `art-asset-registry` (the ledger record).
