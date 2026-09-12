# MiniMax Music 3

Typical local components:

| Component | File |
|---|---|
| Diffusion model | `minimax_music3_dit_fp16.safetensors` |
| Text encoder | `minimax_music3_text_encoder_pruned_int8_convrot.safetensors` |
| Audio VAE | `minimax_music3_dav.safetensors` |

Always verify filenames in the live node definitions.

The caption should cover genre, mood, instrumentation, arrangement, spatial
character, and vocal treatment. Lyrics can use `[Intro]`, `[Verse]`, `[Chorus]`,
`[Instrumental]`, and `[Outro]`. For instrumental material, keep lyrics empty when
supported or use sparse instrumental tags without sung text.

A 12–20 second first test validates the complete load → condition → sample → decode
→ save path, but not long-form musical coherence. Increase to production duration
only after the short test passes.

Known starting settings:

```text
text cfg_scale: 1.7
top_k: 50
sampler: euler
scheduler: simple
steps: 30
sampler cfg: 1.7
```

Keep the text-conditioning seed and sampler seed explicit for reproducibility.

## Post-processing and acceptance

- **The model can stop early.** A 180 s request can come back well short of it on some prompts,
  so any post-processing fade must read the *actual* duration (`ffprobe`) rather than assume the
  requested length, or the fade lands in silence and the real ending clicks.
- **Long tracks need a sectioned prompt.** A single-mood description produces loops that stall
  after ~60 s; tagging sections (intro / A / B / bridge / outro with bars or seconds) holds the
  structure across the full length.
- Deliver the source as `SaveAudioAdvanced` FLAC (lossless), then post-process locally: mono
  44.1 kHz, `loudnorm` to −16 LUFS, and a 0.5 s fade in/out for looping beds; ship as 160 kbps
  MP3.
- **If the game listens on the microphone** — a data channel carried in audio, a clap or blow
  input — its own music must stay out of the band it listens to: add a brick-wall low-pass around
  14–15 kHz (two stages) and require RMS above 16 kHz ≤ −45 dB relative to full band on every
  delivered clip.
- Generate playlist beds as `bgm_x`, `bgm_x_2`, … (same group, different seeds) so the runtime
  can rotate them without repeating the last one.
