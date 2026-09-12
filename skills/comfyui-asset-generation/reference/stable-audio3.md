# Stable Audio 3

`stable-audio-3-medium` is post-trained for direct generation. Medium Base is
primarily a fine-tuning base and normally requires many more inference steps.

Typical Medium components:

| Component | File |
|---|---|
| Checkpoint | `stable_audio_3_medium.safetensors` |
| Text encoder | `t5gemma_b_b_ul2.safetensors` |

Verify `CheckpointLoaderSimple` and `CLIPLoader` choices before submission. A saved
workflow can retain a filename after the underlying model was removed or misplaced.

Post-trained Medium starting settings:

```text
sampler: lcm
scheduler: simple
steps: 8
cfg: 1.0
```

For SFX, describe source, material or timbre, perspective, space, attack, decay,
motion, and exact duration. End with `Length: N seconds`. Put unwanted music,
voice, ambience, distortion, and clipping in the negative prompt.

Use 2–8 seconds for the first one-shot test. Check duration, codec, sample rate,
channels, file size, decode noise, and clipping before judging creative quality.

## Post-processing and acceptance

- Requested lengths of 0.15–2 s come back at the requested length. Trim each clip to that exact
  length (`atrim`), apply a 30 ms tail fade and pad (`apad`) so every clip is the declared
  duration — Unity's one-shot playback is more predictable that way. Keep the source lossless (the
  template's `SaveAudioAdvanced` saves FLAC): MP3 encoder padding adds silence at both ends, so the
  trim arithmetic lands on the wrong sample.
- Peak-normalise to −3 dBFS (−9 dBFS for quiet UI ticks) and deliver mono 44.1 kHz WAV.
- If the game listens on the microphone (a data channel carried in audio, a clap or blow input),
  keep the SFX out of the band it listens to: low-pass every clip the way the music is low-passed
  (`minimax-music3.md`) and require RMS above 16 kHz ≤ −45 dB before delivery.
- Batch all SFX with the model loaded once, then `/free` before the next family; a whole batch of
  short clips costs less GPU time than two music beds.
