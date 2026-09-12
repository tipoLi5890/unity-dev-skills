# Example ComfyUI inventory

An example: one server's saved workflows and installed H3 files. It is a routing
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

Before every first job in a session, verify these choices through the relevant
`/object_info/{class}` endpoints. A renamed, moved, or removed file invalidates
this inventory.
