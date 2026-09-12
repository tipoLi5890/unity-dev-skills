# MiniMax H3 semantic references and timeline guides

R2V semantic references and multi-frame guides solve different problems.

## Semantic inputs

`MiniMaxH3ReferenceToVideo` accepts up to nine reference images, three
reference videos with paired audio, and three standalone audio clips. Tags are
assigned by connection order:

- first connected image: `<Picture 1>`
- second connected image: `<Picture 2>`
- first connected video: `<Video 1>`
- first connected audio: `<Audio 1>`

Only connected semantic inputs receive tags. A picture connected solely to an
`AddGuide` node does not automatically become the next `<Picture N>`.

Read the current input counts off `/object_info/MiniMaxH3ReferenceToVideo` before
building a graph that depends on them.

Use `ref_image_size=match` for speed and normal identity retention. Use `max`
only when reference fidelity justifies the extra token and memory cost.

## Timeline guides

`MiniMaxH3AddGuide` anchors an image, video-frame batch, audio clip, or a
combination at `frame_idx`. Chain its `positive` output into the next guide,
then send the final conditioning to `BasicGuider`.

- `frame_idx=0` anchors the first frame.
- Negative values count backward from the end.
- A guide plus its clip length must fit inside the generated latent length.
- Multi-frame video batches are cropped to valid 17k+5 lengths.
- A still guide needs the video VAE; an audio guide needs the audio VAE.

For a 362-frame video, practical still anchors include 0, 120, 240, and 354.
Keep the prompt timeline consistent with those positions. Too many unrelated
anchors can cause abrupt morphing even when validation succeeds.
