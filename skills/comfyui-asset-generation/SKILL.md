---
name: comfyui-asset-generation
description: >-
  Generate and validate audio, video and 3D assets on a self-hosted ComfyUI
  server: MiniMax Music 3 vocal-free beds and jingles, Stable Audio 3 SFX,
  MiniMax H3 text-, image- and reference-to-video with multi-frame guides,
  Pixal3D / TRELLIS.2 props from one image or four views. Use for "generate
  BGM / a jingle / sound effects", "instrumental, no vocals", "make a video
  from this image", "turn this image into a 3D model", "the mesh came out
  tilted", "MiniMax", "Stable Audio", "the ComfyUI queue is busy", "free the
  model before switching", or running ComfyUI workflows over LAN or a private
  network, one GPU job at a time (only /history proves completion). Unity
  side: unity-audio, unity-3d-models.
---

# ComfyUI asset generation

Create standalone audio, video or 3D assets through an existing ComfyUI
installation. Works from Claude Code or Codex alike; nothing here assumes one agent. Do not install models, change server settings, expose ports, or
infer permission to upload private inputs unless the user authorizes those actions.

## Working contract

- Resolve the server URL in this order: explicit `--server`,
  `COMFYUI_SERVER_URL`, then the local config documented in
  `reference/comfyui-api.md`. Never put private server addresses in reusable
  templates or references.
- Before the first submission, check `/system_stats`, `/queue`, required node
  classes, and live model choices. Saved workflow dropdowns are not proof that a
  model is installed.
- Keep at most one running or pending workflow. Wait for terminal history before
  submitting the next job.
- Reuse a loaded model for consecutive work in the same model family. Before a
  model-family switch, or after the final known job, wait for an empty queue and
  call `/free`.
- Preserve saved UI workflows. Submit an API-format copy or a template from this
  skill; a UI workflow, especially one containing subgraphs, is not itself an API
  graph.
- A successful `POST /prompt` only queues work. Completion requires terminal
  `/history/{prompt_id}`, successful output download, and media inspection.
- Stop after one unchanged validation or runtime failure. Report the failing node
  instead of repeatedly consuming GPU time.

## Route by task

| Task | Read or use |
|---|---|
| API, config, uploads, submission, download | `reference/comfyui-api.md`, `scripts/comfy_asset_client.py` |
| Queue order, model reuse, switching, cleanup | `reference/operations.md` |
| Example inventory: saved workflows, model-family mapping | `reference/server-inventory.md` |
| MiniMax Music 3 | `reference/minimax-music3.md`, `templates/minimax_music3_api.json` |
| A background bed with no vocals: wording, worked captions, length, the voice check | `reference/instrumental-bgm.md`, `scripts/check_instrumental.py` |
| Stable Audio 3 music or SFX | `reference/stable-audio3.md`, `templates/stable_audio3_medium_api.json` |
| Any MiniMax H3 video mode | `reference/minimax-h3.md` and the matching H3 template |
| H3 semantic references or timeline guides | Also read `reference/multiframe-reference.md` |
| A static 3D prop from one image or four views: path choice, input, run, acceptance | `reference/image-to-3d.md`; `templates/pixal3d_image_to_model_api.json`, `templates/trellis2_image_to_model_api.json`, `templates/pixal3d_multiview_to_model_api.json` |
| 3D budgets, node knobs, occlusion, a mesh that came out tilted, shredded or discoloured | `reference/image-to-3d-tuning.md`; gate every GLB with `scripts/inspect_glb.py` |
| H3 character motion transfer, pace matching, or side-by-side QA | Also read `reference/h3-motion-transfer.md`; normalize non-24 fps sources with `scripts/prepare_h3_motion_reference.py` |

Read only the references relevant to the current request.

`agents/openai.yaml` is host packaging rather than method: it registers this skill
with the Codex host — display name, one-line summary, and the
`$comfyui-asset-generation` prompt that invokes it. Nothing below depends on it.

## Execution outline

1. Resolve configuration and verify server reachability without changing state.
2. Select T2V, I2V, R2V, multi-frame, music, SFX, or image-to-3D (one image or
   four views) from the actual inputs and requested outcome.
3. Verify every node and model filename used by the selected API graph against
   live `/object_info`.
4. Upload only authorized inputs, override the closest template's inputs with
   `--set NODE.INPUT=VALUE` (or edit a copy when the graph itself changes), and
   submit one job.
5. Wait for terminal history, download every declared output, and validate its
   codec, duration, dimensions or sample properties, and non-zero size. A GLB
   passes `scripts/inspect_glb.py` and a look at every QA render under `3d/qa/`. A
   background bed passes `scripts/check_instrumental.py`, or a listen.
6. Keep the model loaded only for a known next job in the same family. Otherwise
   follow `reference/operations.md` and release it.

## Scope — what this skill does NOT do

- **Importing the result into Unity** — load type, sample rate override, compression,
  mono/stereo, `AssetPostprocessor` rules and the playback layer (playlists, crossfades,
  pause behaviour): `unity-audio`. This skill stops at a validated file on disk.
- **Importing a GLB into Unity** — glTFast, scale, pivot and rotation on the `Model` child,
  prefab wiring, culling and the triangle budget: `unity-3d-models`.
- **A character that needs a rig** — skeleton, Avatar, animation clips: `unity-rigged-character`.
  The 3D templates here produce static props.
- **Images and sprites** — reference art, icons, sprite sheets, chroma-key transparency and the
  art-bible discipline, and the source image or turnaround sheet an image-to-3D job starts from:
  `codex-visual`.
- **Video playback inside a Unity build** (VideoPlayer, transcoding for mobile): not covered
  anywhere in this family yet; treat H3 output as a delivered media file.
- **Installing or reconfiguring ComfyUI, models or ports**: left to the user, on request only.

## Boundaries

- MiniMax H3's reliable trained range is approximately 5–15 seconds per video;
  disclose when a request exceeds that tested range.
- Image-to-3D yields static props: one mesh, one material, no skeleton, no real-world scale.
- Keep engine import, compression, middleware, and Unity/Unreal/Godot integration
  in downstream skills.
- Do not expose unauthenticated ComfyUI to the public internet. Prefer LAN or an
  authenticated private overlay network.
- Open weights do not imply unrestricted commercial rights. Check the applicable
  model and output license when commercial use matters; an image-to-3D graph
  loads several components, so check the licence of each one's weights.
