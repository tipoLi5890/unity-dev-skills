# MiniMax H3 character motion transfer

Use this workflow when one input defines a character or wardrobe and a reference
video defines athletic motion, dance, gesture, camera movement, or interaction
timing. It applies to H3 R2V semantic references. Use multi-frame guides only
when exact source frames must appear on the output timeline.

## Why reference frame rate matters

`MiniMaxH3ReferenceToVideo` expects reference video frames at 24 fps. Passing a
60 fps clip through unchanged can make a motion reference contain far more
frames than the target latent and can produce slower or softened cadence. Before
upload, normalize motion-critical references to:

- 24 fps;
- the same 17k+5 frame count as the intended output when practical;
- a duration of `frame_count / 24` seconds;
- H.264/AAC MP4 for predictable local inspection and Mac playback.

Use `scripts/prepare_h3_motion_reference.py SOURCE OUTPUT --frames N`. Valid
trained-range frame counts are 124, 141, 158, ... through 362. The script fails
instead of silently padding a source that is too short. The output is video-only
by default; pass `--keep-audio` when the source audio track must survive.

Match the reference and output timelines when pace matters. For example, prepare
124 source frames and generate 124 output frames. Do not compensate for an
un-normalized reference by immediately speeding up the generated result.

## Reference authority

Separate the responsibilities of semantic inputs in the prompt:

- `<Picture 1>`: identity, face, hair, body proportions, art direction,
  wardrobe design, colors, and stable markings.
- `<Video 1>`: motion sequence, real-time cadence, foot plants, weight transfer,
  object contact, camera, framing, and environmental layout.

Explicitly tell the model to ignore the source performer's identity, gender,
hair, clothing, and footwear. For a character sheet, request one character only
and exclude sheet layout, duplicate figures, split screens, and extra views.

For wardrobe consistency, name the colors and stable identifiers, state that
they persist from first to last frame, and list likely source-color leakage as
negative constraints. `ref_image_size=max` can improve identity and costume
retention but increases memory and runtime.

For speed-sensitive motion, describe observable timing instead of using only
adjectives such as "fast": same real-time pace, every foot plant and object
contact at the reference timing, immediate recoil, sharp direction changes, no
slow motion, no eased timing, no lingering pose, and complete the action within
the same frame count.

## Sampling strategy

- Use the matching REF2VA diffusion model and `res_multistep`.
- Use the REF2V 4-step LoRA for inexpensive exploration.
- Prefer the full model at about 20 steps when identity, wardrobe, anatomy, and
  motion fidelity justify the longer runtime. Do not present this as guaranteed;
  compare the actual outputs.
- Change one major variable at a time: reference normalization, authority prompt,
  reference size, sampler path, or seed.

## Validation and comparison

Success from `/prompt` is not quality approval. After download:

1. Verify non-zero size, duration, dimensions, frame rate, and codecs with
   `ffprobe`.
2. Inspect multiple evenly spaced frames, not just the first frame. Check face,
   hair, wardrobe color, markings, hands, feet, object contact, duplicates, and
   background continuity.
3. Create a synchronized side-by-side comparison using equal frame rate,
   duration, dimensions, and start time. Put the source on the left and generated
   output on the right.
4. Compare motion phase at the same timestamps: foot direction, planted foot,
   object position, torso rotation, and recovery pose.
5. Keep native-generation pace evaluation separate from post-production speed
   tests.

When H3 preserved identity but softened motion, first confirm that the reference
was normalized to 24 fps and matched the target frame count. If native motion is
still too slow, a clearly labeled post-production experiment may use `setpts`
for speed, `atempo` for pitch-preserving audio tempo, and `minterpolate` for a
60 fps viewing copy. Always generate this from the unmodified master rather than
compounding earlier speed changes.

## Delivery

Prefer H.264 video, AAC audio, `yuv420p`, and `+faststart` for a Mac-compatible
MP4. Preserve the native H3 master, any post-processed speed variant, and the
side-by-side comparison as distinct files with descriptive names.
