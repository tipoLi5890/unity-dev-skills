# MiniMax H3 keyframe segments — a multi-step clip as a chain of first/last-frame shots

A clip with several steps — objects regrouped in stages, a tutorial, a short choreography — is
built here as ~5 s first/last-frame (FL2V) segments, one step each, generated between keyframes
drawn on one camera, measured, then assembled. The evidence is one project: a ~30 s clay-style
clip of nine coloured blocks being regrouped in stages, then four characters stepping in. Its
disk holds 36 H3 generations (35 FL2V segments and one 362-frame multi-frame attempt; its log
counts 37 runs because one segment was run twice into one folder), 10 of them in the final cut,
about 135 s each at 1344x768 x 124 frames. Thresholds below are that project's and are
labelled where nothing was swept.

## 1. When to split, and the call

Split when the clip has more than one action. The one attempt to get a whole 15 s sequence from
one R2V multi-frame generation failed (§8). An FL2V segment of 124 frames (~5.2 s) between two
keyframes did one simple action reliably. `templates/minimax_h3_fl2v_api.json` is the I2V
template with a second `LoadImage` (node 17) wired to `last_frame`:

```bash
python3 <skill>/scripts/comfy_asset_client.py --workflow <skill>/templates/minimax_h3_fl2v_api.json \
  --output-dir out/seg_02 --upload kf/k01.png --upload kf/k02.png --overwrite-uploads \
  --set 1.image=k01.png --set 17.image=k02.png --set 7.prompt=@prompts/seg_02.txt \
  --set 7.width=1344 --set 7.height=768 --set 7.length=124 --set 8.noise_seed=515 \
  --set 16.filename_prefix=video/seg_02 --keep-loaded          # not on the last job (§7)
```

Crop every keyframe to the output aspect and resize it the same way (centre crop, then LANCZOS)
before upload, so the first and the last frame frame the scene identically.

## 2. Keyframes: one camera, chained from the first

Generate the first keyframe from the style anchor and its layout map (§3); every later keyframe
passes **the first keyframe** as Image 1 ("keep the room, the camera, the lighting and the look of
every object identical to it") plus its own layout map, never the previous keyframe — drift
compounds down a chain. The failure to watch is the **camera**: measure one fixed scene feature
on every keyframe against the first — here the row where the back wall meets the floor, read in a
column no object crosses — and re-roll when it moves.

- 27 to 37 px off (on 941 px tall keyframes) in three tries of one keyframe: H3 invented a dolly
  between the frames and the objects drifted with it; both segments made from it were discarded.
- 21 px off on another keyframe; its two segments showed no visible effect.
- The project re-rolled anything over 6 px (4 of its 17 keyframe generations). That number was
  chosen, not found: between 6 and 21 px nothing was tested. Keep it tight anyway — a re-roll
  costs one image, a bad segment costs a GPU run and a look.

## 3. A drawn layout map as the layout authority

Draw each keyframe's arrangement by program: object positions on the ground plane, projected
through one fixed camera, flat colours, a mark for which way each object faces. It is the
storyboard that cannot be wrong, and it is Image 2 of the keyframe prompt: "Image 2 is the LAYOUT
MAP: the same number of objects, each in the same place, with the same colour and facing. Take
ONLY positions, colours and facing from it; do not copy its flat diagram look."

`codex-visual`'s image-model.md §6 says a crosshair template buys no pixel placement, and that
still holds: this map carries *which object, roughly where, which colour, which way*. All 13
accepted keyframes matched their map by eye, one with slightly looser spacing; the 4 rejections
were camera drift (§2). Exact geometry comes from measuring, never from the prompt. The same
coordinates drive §4's check.

## 4. One action per segment; paths that never cross

- **One kind of motion per segment** — a group sliding together, or each object one small step,
  or a character entering. "Slide the group across and close it into a new shape" in one segment
  spun and wandered on 3 of 3 tries; as two segments ("slide", then "close up") both were usable.
- **No crossing paths.** Steps whose straight-line paths crossed tumbled and overlapped on 6 of
  7 tries (new prompts and seeds included); the seventh was marginal. Before generating, move
  every object in a straight line between consecutive layouts, test every pair for overlap along
  the way, and re-order until no step overlaps; an object boxed in on all sides *jumps* and is left
  out. Re-choreographed so, every step gave a usable take, some on the second seed.
- **Non-crossing is necessary, not sufficient.** Four pairs turning on the spot, swept circles
  checked clear, all at once: wild spinning on 2 of 2 seeds, the pair meant to stay still
  included. The same turns one after another: 1 of 2 seeds usable (the other grew a dark ring on
  the floor; the usable one over-turned one pair by half a turn).
- Between the first and the last keyframe change only what moves.

## 5. Prompt wording

Open with "The supplied first frame and last frame must be preserved exactly", then the timeline
in seconds ("for the first second nothing moves", "finished by about the 1.5 s mark; after that
everything rests"), the invariants (how many objects, rigid, never change colour; fixed camera:
no zoom, no pan, no cut), and the audio line. **Do not name the style "stop-motion"**: the first
segments did ("clay stop-motion animation") and came back on twos, each drawing held for two
frames. Later prompts said "smooth, fluid and continuous at the full 24 frames per second, with
gentle ease-in and ease-out; it is NOT stop-motion: no stepping, no held frames, no jitter; the
clay look is only in the materials and lighting". Twos still came back on 3 of the 25 runs with
that wording, two of them clean on another seed with the same prompt: wording lowers the rate,
measuring catches it.

## 6. Check every segment

`ffprobe` for the basics; a contact sheet of every 8th frame against the layout map for wrong
objects; then `scripts/video_motion.py profile seg.mp4 --curve` for the motion — still head and
tail, stall% and jerk — and `smooth` to rebuild a segment on twos. Its 0.6 threshold is one
project's, to be retuned for another resolution or subject (the script's header). The first cut
was checked on contact sheets alone; on playback it dragged, and the profile read 62% and 46%
stalled frames inside the moving spans.

## 7. Assemble, and the audio

`scripts/assemble_segments.py OUT seg1 seg2:keep '|' seg3:hold2.5 …` trims each segment's still
ends (a few frames kept), crossfades over 6 frames, and takes per-segment suffixes: `:keep` for a
segment already right (the character entrances were never touched), `:holdS` to hold the opening
(a viewer needed 2–3 s to read the starting arrangement), `:x0.8` for a motion-compensated
slow-down, `:rA-B` to cut a still middle out, `|` for a longer chapter fade, `--timeline` for
where each segment lands. With re-choreography and these, the cut went from 41.5 s to 31.7 s and
the stalled share from 62% / 46% to 7% / 20%. Never crossfade a segment generated from an old
version of a keyframe into one generated from its replacement: the objects show twice through
the fade — regenerate the neighbour. Even matched segments ghost briefly where positions differ.

**Audio:** every segment brings its own music, different in tune and loudness (mean −26 to −14
dB across one project's segments), so the assembled track changes at every seam. Treat it as a
scratch track and re-score the final cut as one piece, cues placed from `--timeline`.

**Batching:** one job at a time (`reference/operations.md`); `--keep-loaded` on every segment of
a run but the last, which frees the GPU. `segment.sh` stands for the keyframe crop plus the §1
call. Log each run to a file and redact the server before printing any of it:

```bash
n=$(grep -c . batch.txt); i=0                    # batch.txt: first last prompt outdir seed
while read -r first last prompt out seed; do
  i=$((i+1)); keep=--keep-loaded; [ "$i" -eq "$n" ] && keep=
  if ./segment.sh "$first" "$last" "$prompt" "$out" "$seed" $keep > "$out.log" 2>&1 < /dev/null; then
    f=$(ls "$out"/*.mp4 | head -1)
    ffmpeg -nostdin -v error -y -i "$f" -vf "select='not(mod(n\,8))',scale=672:-2,tile=4x4" -frames:v 1 "$out/qa.png"
  else tail -5 "$out.log" | sed -E 's#https?://[^/" ]+#<server>#g'; fi
done < batch.txt
```

## 8. What did not work

One 362-frame R2V multi-frame run with four still guides (frames 0, 120, 240, 354) and the REF2V
4-step LoRA: the four guide frames came out right, every frame between them dark, speckled with
white and recoloured. One trial, and the full-step path was not tried (`multiframe-reference.md`).
