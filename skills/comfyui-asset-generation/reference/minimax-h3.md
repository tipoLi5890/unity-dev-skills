# MiniMax H3 video

MiniMax H3 jointly produces 24 fps video and stereo audio. Select the mode from
the available inputs and the control wanted:

| Mode | Node and model family | Use when |
|---|---|---|
| T2V | `MiniMaxH3ImageToVideo`, FL2VA | No image is supplied |
| I2V / FL2V | `MiniMaxH3ImageToVideo`, FL2VA | A first frame, last frame, or both are supplied |
| R2V | `MiniMaxH3ReferenceToVideo`, REF2VA | Images, videos, or audio are semantic identity/style/motion references |
| Multi-frame | R2V plus `MiniMaxH3AddGuide`, REF2VA | Exact stills or clips must occur at particular output frames |

## Duration and sampling

- H3 uses a 17k+5 frame grid at 24 fps. Approximately 5 seconds is 124 frames;
  approximately 15 seconds is 362 frames.
- The reliable trained range is about 124–362 frames. Do not exceed it without
  explicitly telling the user that the behavior is untested.
- Use `res_multistep`.
- Known fast paths are the installed FL2V 8-step LoRA and REF2V 4-step LoRA.
- Match the LoRA to the diffusion family. Never apply the REF2V LoRA to FL2VA or
  the FL2V LoRA to REF2VA.
- A semantic reference video is expected at 24 fps. For motion or pace transfer,
  do not pass a higher-frame-rate source through unchanged: normalize it to 24
  fps and the intended H3 frame count first. Read `h3-motion-transfer.md`.

## Native audio/video path

The H3 latent contains both modalities:

1. Feed the sampled latent to `VAEDecode` with the video VAE.
2. Feed the same latent to `VAEDecodeAudio` with the audio VAE.
3. Send frames and audio to `CreateVideo` at 24 fps.
4. Save with `SaveVideo`.

Every H3 template sets both `format.codec` and `codec` on `SaveVideo`; read
`/object_info/SaveVideo` and keep the spelling it declares.

Describe dialogue, music, ambience, and sound effects in the same prompt as the
visual timeline. If the final asset should be silent, state that explicitly and
omit or discard audio downstream.

## Prompt routing

- T2V: describe subject, environment, shot progression, camera, motion, style,
  soundscape, and exclusions.
- I2V: state that the supplied first or last frame must be preserved, then specify
  the intended motion and camera behavior.
- R2V: tag semantic inputs exactly as `<Picture 1>`, `<Video 1>`, or
  `<Audio 1>` in connection order.
- R2V character motion transfer: assign identity and wardrobe authority to the
  picture, and motion, timing, framing, and interaction authority to the video.
  Read `h3-motion-transfer.md` for preprocessing, prompting, and QA.
- Multi-frame: also read `multiframe-reference.md`.
