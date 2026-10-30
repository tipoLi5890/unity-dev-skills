# The pipeline — still → canvas → clip → keyed frames → cut → Unity

Five stages, each with a gate. The worked example throughout is the courier-run **runner**: one
approved side-view still on a green key becomes `runner_walk` (a loop) and `runner_launch` (the
jump onto the next lane, a one-shot); the **sentry** at the gate gets `sentry_idle`.

## 1. Which route for which motion

| Motion | Route | Why |
|---|---|---|
| walk, run | image-to-video from the still, in place, continuous → period detection → loop | a gait repeats, so the clip holds several cycles and the cut takes the one with the smoothest wrap |
| idle breath | `codex-visual` → `reference/animation-scripts.md` (`breathe.py` on the keyed still) | pixel-exact, closed by construction, no clip at all |
| idle that shifts weight | image-to-video, in place → `--state idle` | a slow sway is not strictly periodic; the idle window is long and its periodicity gate is off |
| jump, launch | image-to-video from standing, tall canvas → `--mode once` | one performed action that starts and ends standing |
| attack, swipe | image-to-video from standing, wide canvas → `--mode once` or `--mode oneshot` | one action; `once` when it ends in a held stance, `oneshot` for a self-contained beat |

**Never first frame = last frame for a loop.** The first/last-frame template given the same still
at both ends returns a clip that barely moves — the body's centre travels under a pixel. Both
ends are satisfied by staying still. A loop is found in a continuous clip, not forced by its ends.

## 2. Setup

```bash
PY=$HOME/.codex/imagegen-venv/bin/python
S=<repo>/skills/sprite-from-video/scripts
C=<repo>/skills/comfyui-asset-generation
command -v ffmpeg && command -v ffprobe && ffmpeg -version | head -1      # 5.1 or later
```

The generation runs through `comfyui-asset-generation`: read its working contract and
`comfyui-asset-generation` → `reference/comfyui-api.md` before the first submission (server
resolution, `/system_stats`, `/queue`, live model choices). Uploading a still is uploading a
user's input: only with their authorisation.

The base still comes from `codex-visual`: full body, side view, generous empty space on every
side, on one flat key the subject does not contain (`pick_key.py` chooses it), feet on an
imagined floor. A still cropped at the feet or touching an edge fails stage 3 later.

## 3. Stage 1 — the canvas

A video model keeps the input's framing, so the room a motion needs is added on the still:

```bash
"$PY" "$S/video_canvas.py" ArtDirection/keyed/runner_still.png --state walk --out work/runner_walk_canvas.png
"$PY" "$S/video_canvas.py" ArtDirection/keyed/runner_still.png --state jump --out work/runner_launch_canvas.png
"$PY" "$S/video_canvas.py" ArtDirection/keyed/sentry_still.png --state attack --facing left \
  --out work/sentry_swipe_canvas.png
```

| `--state` | Shape | Room |
|---|---|---|
| `jump`, `land` | tall 3:4 | 0.34 of the height above the still |
| `attack` | wide 16:9 | 0.20 above, 0.28 in front, 0.20 behind |
| `projectile` | wide 16:9 | 0.34 in front |
| `cheer`, `wave`, `celebrate` | wide 16:9 | 0.30 in front |
| `death`, `fall`, `hurt_hold` | wide 16:9 | 0.10 above, 0.32 in front and behind |
| `cast`, `transform` | wide 16:9 | 0.25 above, in front and behind |
| `idle`, `walk`, `run`, any other state | square | none |

`--shape square|tall|wide` overrides the table (a walk forced wide gets room in front and behind
and none above); `--headroom`, `--lead`, `--trail` override the shares; `--facing` says which side
is in front. The still is pasted **at the bottom**, so the feet stay on the floor of the clip.

The field is repainted first: every pixel the keyer would erase becomes the **exact** key, the
subject stays byte-identical, and the padding is that same key — the video model then repaints one
uniform colour rather than a drawn green with seams where the padding begins. The canvas is fitted
into a frame whose long side is `--long-side` (768) and whose other side is a multiple of 16:
768x768 square, 576x768 tall, 768x432 wide. stdout is one JSON object; stderr repeats the
generation size on its own line, ready to paste:

```text
--set 7.width=576 --set 7.height=768
```

Gate: exit 0. Exit 2 (corners not one flat colour) and 3 (not a key, or a corner the key keeps):
`reference/loop-detection.md` §7.

## 4. Stage 2 — generate the clip

Image-to-video, one job, with the canvas as the first frame. Write the prompt to a file first
(`reference/video-prompts.md`), then:

```bash
python3 "$C/scripts/comfy_asset_client.py" --workflow "$C/templates/minimax_h3_i2v_api.json" \
  --output-dir clips/runner_walk_s1201 --upload work/runner_walk_canvas_s1201.png \
  --set 1.image=runner_walk_canvas_s1201.png --set 7.prompt=@prompts/runner_walk.txt \
  --set 7.width=768 --set 7.height=768 --set 7.length=124 --set 8.noise_seed=1201 \
  --set 16.filename_prefix=video/runner_walk_s1201 --job-log jobs.jsonl
```

| Node.input | Value |
|---|---|
| `1.image` | the uploaded canvas's **basename** — the upload keeps its local name |
| `7.prompt` | `@file`, so the text keeps its line breaks and the result records only its hash |
| `7.width`, `7.height` | the line `video_canvas.py` printed; never the template's default for a tall or wide canvas |
| `7.length` | `124` — about 5 s at 24 fps, the floor of H3's trained range and enough for four or more walk cycles |
| `8.noise_seed` | a new number per attempt, recorded; a re-roll is a new seed, not the same request again |
| `16.filename_prefix` | per asset and seed, so outputs never collide |

- **Name the upload per asset and attempt** (`runner_walk_canvas_s1201.png`). A server that
  already holds a different file of that name stores the new one as `name (1).png` and the graph
  reads the old one, with only a warning.
- **One GPU job at a time.** The client refuses while the queue holds a running or pending job;
  wait for its terminal result before the next. Pass `--keep-loaded` only when the next job is
  another H3 clip, and not on the last one.
- **Completion is the downloaded file.** The client waits on `/history`, downloads every output
  and prints `output_files` with their `sha256`; probe the MP4 (`ffprobe`) before keying it.
- **The MP4 carries audio.** H3 decodes a sound track with every clip; stage 3 drops it, and it
  is never kept.

H3's modes, frame grid and prompt rules beyond this route: `comfyui-asset-generation` →
`reference/minimax-h3.md`.

## 5. Stage 3 — key every frame

```bash
CLIP=clips/runner_walk_s1201/runner_walk_s1201.mp4      # the path the client listed in output_files
"$PY" "$S/video_frames.py" "$CLIP" --out-dir work/runner_walk
```

ffprobe reads the clip's own frame rate and frame count; ffmpeg writes every picture frame with
`-an -fps_mode passthrough` (no `-r`: no frame is duplicated or dropped). Each frame is keyed by
the same block as `codex-visual`'s `key_unmix.py --edge tint`: a hard cut within 96 of the
declared key and, within 96 of the **painted** key read once from frame 0's border, the pixels
carrying the key's hue signature and what is 8-connected to them inside that ball; the rim 1–4 rings in is un-mixed, trapped spill despilled. Stray specks far from the
body are dropped.

Read `work/runner_walk/frames.report.json`:

| Key | What it says |
|---|---|
| `key.painted_rgb`, `key.off_by` | the colour the model actually painted and its distance from the declared key — (2, 238, 3) for "#00FF00", 14–22 off, is ordinary and is why the second erase ball exists |
| `flatness.border_std_max` | the largest per-channel spread in the 4-px border ring of any frame; a flat field stays in single digits |
| `flatness.border_mean_drift_max` | how far the field's colour wanders across the clip |
| `transparent_pct_min` | the emptiest frame's share of transparent pixels |
| `edge.contacts` | frames with opaque pixels in the top, left or right 4-px band, each classed `residual` or `subject` |

Gate: exit 0, and `keyed/` exists. A refused run keeps its frames in `keyed.refused/` to look at.
Exit 2 and 3, and their fixes: `reference/loop-detection.md` §7. `--drop-raw` removes the
decoded frames once the keyed ones pass.

## 6. Stage 4 — cut

```bash
"$PY" "$S/video_loop.py" work/runner_walk --state walk --name runner_walk --out-dir out
"$PY" "$S/video_loop.py" work/runner_launch --state jump --mode once --name runner_launch --out-dir out
"$PY" "$S/video_loop.py" work/sentry_idle --state idle --name sentry_idle --out-dir out --fps 10
```

`--state` picks the search window (walk 0.5–1.6 s, run 0.3–1.2 s, idle 60–95 % of the clip,
jump 11–45 %, attack 11 % to 2.5 s, any other state 10–45 %); `--mode` the kind of cut:

| `--mode` | Cut | `loop` | `hold_last` |
|---|---|---|---|
| `auto` (default) | a loop; for `jump`, `attack` and other actions, a one-shot when the clip does not repeat | per cut | false |
| `loop` | one cycle, refused when there is none | true | false |
| `oneshot` | rest → action → rest with matching end poses | false | false |
| `once` | two rest frames before the action → the first settled frame after it | false | true |

**A jump or launch takes `--mode once`.** `auto` and `oneshot` pick the **shortest** pair of
matching poses around the strongest departure, which for a jump is the rising crouch and the
landing absorb: a self-contained beat that starts and ends bent, with the standing pose outside the
cut. `once` keeps the stand before the crouch and ends on the settled stand after the landing,
with `hold_last: true` — it leaves idle and returns to it. Use `oneshot` when the game blends into
the action from its own crouch.

The worked walk: a 124-frame clip at 24 fps whose two steps take 0.92 s has its lag-profile
minimum at 22 frames; the seam search over 21, 22 and 23 picks a 21-frame cut with a wrap of 0.7
mean steps (0.96 at the source rate); the body's 1 px wrap offset is spread as a ramp; 12 fps
subsampling keeps 10 frames, 2 or 3 source frames apart (`subsample.steps`); the feet line, which
spreads 8 px across them, is seated onto frame 0's, so the set is `ground`.

Gate: exit 0, `verdict.ok` true, and **the GIF watched once** (`out/runner_walk.gif`): count the
strides, look at the wrap. Exit 3 writes frames with `verdict.ok: false` and names the fault; exit
2 hands nothing over. Both: `reference/loop-detection.md` §8.

## 7. Stage 5 — hand off

The frame folder `out/runner_walk/` holds `runner_walk_000.png …` and `frames.json`; the preview
and report sit beside it, so the folder can be copied under `Assets/` as it is.

- **Unity** — `unity-2d-sprites` → `reference/sprite-animation.md`: copy the folder under
  `Assets/`. `resources/Editor/FramesJsonImporter.cs` imports the frames from `frames.json`
  (frames/1): one pivot for every frame from `pivot_norm`, and PPU =
  `register.reference_core_height_px` / the character's height in world units, one PPU for every
  set of the character. Then `resources/Editor/SheetToAnimationClip.cs` builds the clip, taking
  `fps_hint`, `loop` and `hold_last` from the same file:

```bash
# UNITY = the project's Editor binary
"$UNITY" -batchmode -projectPath . -logFile - \
  -executeMethod UnityDev.Sprites.FramesJsonImporter.RunFromCommandLine \
  -framesDir Assets/Art/runner_walk -worldHeight 1.8
"$UNITY" -batchmode -quit -projectPath . -logFile - -executeMethod SheetToAnimationClip.RunFromCommandLine \
  -source Assets/Art/runner_walk -clip Assets/Art/runner_walk.anim \
  -framesJson Assets/Art/runner_walk/frames.json
```

  A `once` cut is written `loop: false, hold_last: true`; add extra held frames (`-holdLast N`)
  and an end event (`-endEvent OnAnimationFinished`) for gameplay.
- **`key_color`** is the declared key from `frames.report.json` (`key.declared`), `key_painted`
  the colour the model painted; both audits measure the rim against `key_color`. A bare PNG
  folder has no report: pass `--key-color HEX` (or `none` for art never keyed), else exit 1.
- **`register.foot_margin_px`** is the rows under frame 0's feet line (`pivot_norm`'s y in px);
  `canvas_margin_px` is `--margin`, the room kept round the union box.
- **`fps_hint` is the clip's `frameRate`, never 24.** It is output frames over the cycle's
  seconds: the 21-frame walk lasts 0.875 s and keeps 10 frames, so `fps_hint` is 11.43. The cycle
  plays at the speed it was filmed at.
- **`register`**: `ground` when the feet line (the core silhouette's lowest row, as
  `codex-visual`'s `audit_frames.py` reads it) spreads by at most max(3 px, 2 % of the body): every
  frame is moved whole pixels up or down onto frame 0's line, so `audit_frames.py`'s feet gate
  (3 px) passes and Unity's frame audit runs its slip test on the feet. `keep` when it spreads
  more (a jump, a run with a flight phase): nothing is seated and neither audit gates the feet.
  `register.source_floor_spread_px` is the spread before seating, `seated_max_px` the largest
  move. A treadmill walk can read as slip where a planted foot moves with the belt; check
  `SpriteFramesAudit` before shipping and re-roll a walk whose feet slide.
- **Ledger** — `art-asset-registry` → `reference/ingest.md`:

```bash
R=<repo>/skills/art-asset-registry/scripts
python3 "$R/registry.py" ingest --json out/runner_walk/frames.json            # print the partial record
python3 "$R/registry.py" ingest --json out/runner_walk/frames.json --write    # record it
```

  `ingest` reads the sidecar's `producer` to name the script that made it; `source.file` names its
  input, which `--write` hashes when that path is on disk, and `verdict.ok` gives its
  verdict. Record the generation run too (the
  client's `record` from stage 2), so the seed that made the clip is on file.

## 8. Re-roll budget

A stage that fails on the clip — no period, a popping seam, a subject out of frame, a frozen or
drifting clip — is a re-roll: a new `8.noise_seed`, and the prompt tightened where the failure
points (`reference/video-prompts.md` §2). Change an option only when the clip is good and the cut
is wrong (`--mode once` for a jump, `--max-len` for a loop that holds two strides). After two
failed seeds on one prompt, rewrite the prompt before spending a third.
