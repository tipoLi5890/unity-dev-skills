# Example ComfyUI inventory

An example: one server's saved workflows and installed H3, 3D and image-edit files. It is a routing
hint, not a substitute for live validation — verify every name with
`GET /object_info` before use.

## Saved workflows

| Mode | Saved workflow |
|---|---|
| MiniMax Music 3 | `audio_minimax_music_3.json` |
| Stable Audio 3 Medium | `audio_stable_audio_3_medium.json` |
| MiniMax H3 T2V | `video_minimax_h3_t2v.json` |
| MiniMax H3 I2V | `video_minimax_h3_i2v.json` |
| MiniMax H3 R2V | `video_minimax_h3_r2v.json` |
| MiniMax H3 multi-frame reference | `video_minimax_h3_multiframe_reference.json` |
| Pixal3D / TRELLIS.2 image to model | `3d_pixal3d_trellis2_image_to_model.json` |
| Pixal3D multi-view to model | `3d_pixal3d_multi_views.json` |

## H3 model-family mapping

| Component | Installed filename |
|---|---|
| FL2VA diffusion model | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` |
| REF2VA diffusion model | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` |
| Shared text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |
| Video VAE | `minimax_h3_video_vae_fp16.safetensors` |
| Audio VAE | `minimax_h3_audio_vae_fp32.safetensors` |
| FL2V Turbo LoRA | `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` |
| REF2V Turbo LoRA | `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` |

The four user-facing H3 modes are not four independent diffusion models. T2V and
I2V share FL2VA; R2V and multi-frame reference share REF2VA.

## 3D components

| Role | Folder | Installed filename |
|---|---|---|
| Pixal3D diffusion model | `diffusion_models` | `pixal3d_int8_convrot.safetensors` |
| Pixal3D multi-view diffusion model | `diffusion_models` | `pixal3d_multiview_int8_convrot.safetensors` |
| TRELLIS.2 diffusion model | `diffusion_models` | `trellis_2_int8_convrot.safetensors` |
| Shape VAE | `vae` | `trellis_2_shape_vae_bf16.safetensors` |
| Texture VAE | `vae` | `trellis_2_texture_vae_bf16.safetensors` |
| Image encoder | `clip_vision` | `dino_v3_L_naf_fp32.safetensors` |
| Field-of-view estimate | `geometry_estimation` | `moge_2_vitl_normal_fp16.safetensors` |
| Background removal | `background_removal` | `birefnet.safetensors` |

Both 3D workflows are official templates built from core nodes, and the API
templates in this skill keep their node ids. The three diffusion models share
the encoder and both VAEs and schedule as one family.

## Image edit components

The image-edit family `mesh-texture-paint` paints each view with (Qwen-Image-Edit-2511 and its
4-step Lightning LoRA, both Apache-2.0). It is a separate model family from H3 and 3D: free the
3D models before the first paint job.

| Role | Folder | Installed filename |
|---|---|---|
| Qwen-Image-Edit-2511 diffusion model | `diffusion_models` | `qwen_image_edit_2511_int8_convrot.safetensors` |
| Text encoder | `text_encoders` | `qwen_2.5_vl_7b_fp8_scaled.safetensors` |
| VAE | `vae` | `qwen_image_vae.safetensors` |
| Lightning LoRA, 4 steps | `loras` | `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` |

Before every first job in a session, verify these choices through the relevant
`/object_info/{class}` endpoints. A renamed, moved, or removed file invalidates
this inventory.
