# Sample rate and codec, per platform

> Part of the `unity-audio` skill (SKILL.md §2). The codec each platform decodes cheapest, the
> quality and sample-rate levers, and what format the source files should be in.

| Platform | Codec | Notes |
|---|---|---|
| iOS | **AAC** | Hardware decode — the cheapest CPU option on the platform |
| Android, Web | Vorbis | |
| Desktop / cross-platform | Vorbis | quality **0.5–0.7** |
| Xbox | **XMA** | Set it as a platform override, not as the default |
| PlayStation | **ATRAC9** | Same — a platform override |

The two console codecs are real enum members, not aspirational: `AudioCompressionFormat`
enumerates `PCM, Vorbis, ADPCM, MP3, VAG, HEVAG, XMA, AAC, GCADPCM, ATRAC9`.
**Reach them through a per-platform override**, never by changing `defaultSampleSettings` — a
default set to XMA is meaningless on every other target and the Editor will quietly fall back, so
the console build gets the codec and every other build gets a setting nobody chose.

- **Dialogue goes to Vorbis quality 0.7–0.85.** Two things to get right: the API is `0`–`1`
  while the Inspector shows `0`–`100`, and **the import default is `1` (100%), not 0.5**. The
  usual mistake here is the opposite of the one you expect: clips ship at full
  quality and cost more than anyone intended. Set it deliberately, downward, per category.
- **Mobile SFX and UI: 22050 Hz** (44100 on desktop and console). **Halving the sample rate
  halves the PCM memory** — this is the second-largest lever after Load Type and it is
  imperceptible on short effects.
- **Source files should be WAV or AIFF.** Quality lost by importing an MP3 cannot be recovered
  by Unity's re-encode; you are compressing an already-compressed signal. **Do not pre-encode a
  deliverable to the shipping codec either** — Unity re-encodes whatever you hand it, so that is
  a wasted lossy generation and an extra external tool in the pipeline.
  The one deliberate exception is repo weight on long music: 2–3 minute beds delivered as
  160 kbps mono MP3 put nine tracks at ~30 MB in LFS instead of the ~130 MB the same nine cost
  as 44.1 kHz mono WAV, while every SFX stays lossless. Take that trade knowingly, per category,
  and say which way you went —
  `reference/import-automation.md` has the table.

**Worked example, so the win is predictable before you touch anything** (44 100 Hz stereo 0.5 s
WAV): `sampleRateSetting = OverrideSampleRate` at `22050` moves the clip from
`44100 Hz / 22050 samples` to `22050 Hz / 11025 samples` — **exactly half the PCM data**.
`forceToMono` takes `channels 2 → 1`, halving it again. Both are import-time and both reversible.
