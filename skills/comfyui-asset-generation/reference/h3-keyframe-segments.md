# MiniMax H3 keyframe segments — a multi-step clip as a chain of first/last-frame shots

A clip with several steps — objects regrouped in stages, a tutorial, a short choreography — is
built as ~5 s first/last-frame (FL2V) segments, one step each, between keyframes drawn on one
camera, measured, then assembled. Thresholds below are starting points; re-tune per resolution.

## 1. When to split, and the call

Split when the clip has more than one action: a whole 15 s sequence from one R2V multi-frame
generation failed (§8); an FL2V segment of 124 frames (~5.2 s) did one simple action reliably.
`templates/minimax_h3_fl2v_api.json` is the I2V template with a second `LoadImage` (node 17)
wired to `last_frame`:

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

Generate the first keyframe from the style anchor and its layout map (§3); it becomes the
reference. Every later keyframe passes **the first keyframe** as Image 1 ("keep the room, the
camera, the lighting and the look of every object identical to it") plus its own layout map,
never the previous one — drift compounds down a chain. Watch the **camera**: the model invents a
dolly and the objects drift with it (a 3–4% horizon shift ruins the segments made from that
keyframe; about 2% can pass unseen). Re-roll over ~0.6% of the height. A re-roll costs one
image, a bad segment a GPU run and a look.

`scripts/camera_gate.py --ref kf/k01.png cand.png` reads the row where wall or sky meets floor in
one column (`--column 0.1`, picked by eye where nothing stands): exit 0 pass, 2 moved past
`--tol` or a different size, 3 no horizon, 64 a usage error. Only a `cand` verdict rejects the
roll; a crash, a bad option or a bad reference stops the loop (`keyframe.sh` = one image call):

```bash
mkdir -p rejected; ok=
for try in 1 2 3 4; do                                # N tries, then stop and look
  ./keyframe.sh kf/k01.png maps/k04.png prompts/k04.txt cand.png > k04.log 2>&1 < /dev/null \
    || { tail -3 k04.log | sed -E 's#https?://[^/" ]+#<server>#g'; break; }
  python3 <skill>/scripts/camera_gate.py --ref kf/k01.png cand.png > gate.json; rc=$?
  [ "$rc" -eq 0 ] && { mv cand.png kf/k04.png; ok=1; break; }
  { [ "$rc" -eq 2 ] || [ "$rc" -eq 3 ]; } && grep -q '"which": "cand"' gate.json \
    || { echo "gate exit $rc"; cat gate.json; break; }
  mv cand.png "rejected/k04_$try.png"; mv gate.json "rejected/k04_$try.json"
done
[ -n "$ok" ] || echo "k04: nothing passed; see rejected/"
```

## 3. A drawn layout map as the layout authority

Each keyframe's arrangement drawn by program — ground positions through one fixed camera, flat
colours, a mark for facing — is Image 2 of the keyframe prompt: "Image 2 is the LAYOUT MAP: the
same number of objects, each in the same place, with the same colour and facing. Take ONLY
positions, colours and facing from it; do not copy its flat diagram look."

`scripts/layout_map.py SCENE.json --out maps --check-paths` writes `maps/<frame>.png` and
`maps/layouts.json` (each object's pixel box), exiting 2 when moves cross (§4). Keep the horizon
in frame (pitch < fov/2): it is the line the gate reads. A map buys no pixel placement, only
*which object, roughly where, which colour, which way*; every accepted keyframe matched its map
by eye. Exact geometry comes from measuring the keyframe against the boxes.

## 4. One action per segment; paths that never cross

- **One kind of motion per segment** — a group sliding together, or each object one small step,
  or a character entering. "Slide the group across and close it into a new shape" in one segment
  spun and wandered on 3 of 3 tries; as two segments ("slide", then "close up") both were usable.
- **No crossing paths.** Steps whose straight-line paths crossed tumbled and overlapped on 6 of
  7 tries; the seventh was marginal. `layout_map.py --check-paths` lists every pair whose swept
  footprints touch; re-order until it exits 0. An object boxed in on all sides *jumps*: leave it
  out. Re-choreographed so, every step gave a usable take, some on the second seed.
- **Non-crossing is necessary, not sufficient.** Four pairs turning on the spot at once, swept
  circles clear: wild spinning on 2 of 2 seeds. One after another: 1 of 2 seeds usable.
- Between the first and the last keyframe change only what moves.

## 5. Prompt wording

Open with "The supplied first frame and last frame must be preserved exactly", then the timeline
in seconds ("for the first second nothing moves", "finished by about the 1.5 s mark; after that
everything rests"), the invariants (how many objects, rigid, never change colour; fixed camera:
no zoom, no pan, no cut), and the audio line. **Do not name the style "stop-motion"**: it came
back on twos, each drawing held two frames. "Smooth, fluid and continuous at the full 24 frames
per second, with gentle ease-in and ease-out; it is NOT stop-motion: no stepping, no held
frames; the clay look is only in the materials and lighting" still gave twos on 3 of 25 runs:
wording lowers the rate, measuring catches it.

## 6. Check every segment

`ffprobe` for the basics; a contact sheet of every 8th frame against the layout map for wrong
objects; then `scripts/video_motion.py profile seg.mp4 --curve` for the motion — still head and
tail, stall% and jerk — and `smooth` to rebuild a segment on twos (retune its 0.6 threshold per
resolution or subject). A cut checked on contact sheets alone dragged on playback: 62% and 46%
stalled frames inside the moving spans.

## 7. Assemble, and the audio

`scripts/assemble_segments.py OUT seg1 seg2:keep '|' seg3:hold2.5 …` trims each segment's still
ends (a few frames kept), crossfades over 6 frames, and takes per-segment suffixes: `:keep` for a
segment already right, `:holdS` to hold the opening (a viewer needs 2–3 s to read it), `:x0.8`
for a motion-compensated slow-down, `:rA-B` to cut a still middle out, `|` for a longer chapter
fade, `--timeline` for where each segment lands. With re-choreography and these, the stalled
share fell to 7% / 20%. Never crossfade a segment made from an old version of a keyframe into one
made from its replacement: the objects show twice through the fade — regenerate the neighbour.

**Audio:** every segment brings its own music, different in tune and loudness, so the track
changes at every seam. Treat it as scratch and re-score the cut as one piece from `--timeline`.

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

One 362-frame R2V multi-frame run with four still guides and the REF2V 4-step LoRA: the guide
frames came out right, every frame between them dark, speckled and recoloured. One trial; the
full-step path was not tried (`multiframe-reference.md`).
