# MiniMax Music 3

Typical local components:

| Component | File |
|---|---|
| Diffusion model | `minimax_music3_dit_fp16.safetensors` |
| Text encoder | `minimax_music3_text_encoder_pruned_int8_convrot.safetensors` |
| Audio VAE | `minimax_music3_dav.safetensors` |

Always verify filenames in the live node definitions.

Write the caption in three labelled sections — **Global Metadata** (genre, BPM, key, mood and
how it moves, where it is heard, production character), **Vocal Details** (the voice, or that
there is none), **Arrangement** (the instruments, then section by section what enters, exits or
changes). The lyrics field carries the structure: `[Intro]`, `[Verse]`, `[Pre-Chorus]`,
`[Chorus]`, `[Bridge]`, `[Instrumental]`, `[Solo]`, `[Outro]`. Tags are the instructions; lyric
text between them is sung.

**A background bed with no voice** — the wording that keeps it instrumental, the caption
skeleton, three worked captions and the check that proves it: `reference/instrumental-bgm.md`.
Never leave the lyrics empty for one.

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
- **Length comes from the described sections, not from `max_duration`.** A single-mood
  description ends early or stalls; an Arrangement that names its sections (intro, A, B, A,
  breakdown, outro) holds the structure and the length (`reference/instrumental-bgm.md`).
- Deliver the source as `SaveAudioAdvanced` FLAC (lossless), then post-process locally: mono
  44.1 kHz, `loudnorm` to −16 LUFS, and a 0.5 s fade in/out for looping beds; ship as 160 kbps
  MP3.
- **If the game listens on the microphone** — a data channel carried in audio, a clap or blow
  input — its own music must stay out of the band it listens to: add a brick-wall low-pass around
  14–15 kHz (two stages) and require RMS above 16 kHz ≤ −45 dB relative to full band on every
  delivered clip.
- Generate playlist beds as `bgm_x`, `bgm_x_2`, … (same group, different seeds) so the runtime
  can rotate them without repeating the last one.
