---
name: sprite-from-video
description: >-
  Walk, run or jump sprite loops from one still via generated video: keyed
  frames, clean seam.
---

# sprite-from-video — one still, one clip, one clean cut

An image model draws a pose; a video model moves it. This skill takes **one approved still** of a
character on a chroma key, has a video model perform one motion **in place** on it, and cuts that
clip into frames a sprite pipeline can ship: transparent, on one canvas, with the loop seam or the
one-shot's ends found by measurement rather than by eye.

## Start here — symptom → where to look

| Symptom | Go to |
|---|---|
| "Turn this still into a walk loop"; a run, or an idle with a weight shift, from a video (a breathing idle: `codex-visual` `breathe.py`) | `reference/pipeline.md` §1–6 |
| Which canvas: the jump leaves the top of the frame, the attack hits the side | `reference/pipeline.md` §3; `video_canvas.py --state/--shape` |
| `video_canvas.py` exit 2 or 3: the still's corners disagree or are not a key | `reference/loop-detection.md` §7 |
| The clip came back frozen, zooming, panning or walking out of frame | `reference/video-prompts.md` §1–2, then re-roll |
| Green rim on the frames, or key colour left at the edge | `reference/loop-detection.md` §7 (`video_frames.py` exit 3, residual) |
| A limb or the head leaves the frame | `reference/loop-detection.md` §7 (exit 3, subject) — a taller or wider canvas |
| A frame keyed to nearly nothing transparent | `reference/loop-detection.md` §7 (exit 2) — the field is not the key |
| The loop pops at the seam | `reference/loop-detection.md` §3, §8 (seam over 2.0) |
| The clip is half a stride; the legs swap at the wrap | `reference/loop-detection.md` §2 (half-step guard) |
| The loop holds two strides, or `verdict.ok` is false | `reference/loop-detection.md` §2, §8 (exit 3) |
| No period found in a walk | `reference/loop-detection.md` §8 — the motion does not repeat: re-roll |
| The character drifts across the loop | `reference/loop-detection.md` §5 (drift ramp) |
| "Cut the jump out of this clip"; the jump cut starts mid-crouch or ends mid-landing | `reference/pipeline.md` §6 — `--mode once` |
| The animation plays too fast or too slow in Unity | `reference/pipeline.md` §7 — `fps_hint`, never 24 |
| The walk slides in Unity's frame audit | `reference/pipeline.md` §7 (register ground) |

> **The clip is raw material, never the asset.** Every stage has a gate, and a clip that fails a
> gate is re-rolled (a new seed, a better prompt) rather than repaired. Nothing here interpolates,
> retimes or paints frames.

## Rules the route is built on

- **A loop comes from plain image-to-video plus period detection.** Generate the motion running
  continuously in place (a walk on a treadmill), then `video_loop.py` finds one cycle in it and
  the start whose wrap is smoothest.
- **First frame = last frame does not make a loop.** First/last-frame video with the same still
  at both ends comes back almost frozen: the model satisfies both ends by barely moving. Do not
  use it for any loop.
- **An idle breath is `breathe.py`** (skill `codex-visual`) on the keyed still — pixel-exact and
  closed by construction. An image-to-video idle cut by `video_loop.py --state idle` is the
  second choice, for an idle that has to shift its weight.
- **Jump, launch and attack are one-shots.** They are generated once from standing and cut with
  `--mode once` (standing → action → settled) or `--mode oneshot` (matching end poses).
- **The painted key is not the declared key.** A video model paints "#00FF00" a dozen or more
  units off, and differently per clip; `video_frames.py` reads the painted colour from the first
  frame's border and erases around it as well as around the exact key.
- **H3 always writes an audio track.** `video_frames.py` extracts pictures only; never keep or
  ship the sound.

## Files

| Path | Role |
|---|---|
| `scripts/video_canvas.py` | still → the canvas the motion needs (square, tall for a jump, wide for an attack), field repainted to the exact key, sized for H3; prints the `--set 7.width=… --set 7.height=…` line |
| `scripts/video_frames.py` | clip → every frame keyed to RGBA, with a key-flatness report and an edge-contact gate |
| `scripts/video_loop.py` | keyed frames → one loop, one-shot or once cut, drift removed, subsampled, on one canvas, plus `frames.json` and a preview GIF |
| `reference/pipeline.md` | the five stages with exact commands, which route each motion takes, the handoff |
| `reference/video-prompts.md` | how to word an in-place clip for H3, and the worked prompts |
| `reference/loop-detection.md` | the distance matrix, period, seam, one-shot and once rules, every exit code and its fix |

```bash
PY=$HOME/.codex/imagegen-venv/bin/python        # numpy + Pillow
S=<repo>/skills/sprite-from-video/scripts
"$PY" "$S/video_canvas.py" --selftest && "$PY" "$S/video_frames.py" --selftest && "$PY" "$S/video_loop.py" --selftest
```

`video_frames.py` also needs `ffmpeg` and `ffprobe` on `PATH` (5.1 or later for
`-fps_mode passthrough`). Missing → **stop and ask the user**; never install them.
`video_canvas.py` imports `video_frames.py` from its own folder for the keyer, so the two
travel together.

## The route

| Stage | Run | Gate before the next stage |
|---|---|---|
| 1. Canvas | `video_canvas.py STILL --state walk --out CANVAS.png` | exit 0: corners flat (±24 per channel), a chroma key, field repainted to the exact key |
| 2. Generate | `comfyui-asset-generation`'s `comfy_asset_client.py` with `templates/minimax_h3_i2v_api.json`, the canvas uploaded as `1.image`, the prompt as `7.prompt`, `7.width`/`7.height` from stage 1, `7.length=124`, a recorded `8.noise_seed` | terminal `/history`, the MP4 downloaded and probed; one GPU job at a time |
| 3. Key | `video_frames.py CLIP --out-dir WORK` | exit 0: every frame transparent enough to be the key, nothing but the floor touching the frame edge |
| 4. Cut | `video_loop.py WORK --state walk --name runner_walk --out-dir OUT` | exit 0: `verdict.ok`, seam ≤ 2.0 mean steps, the GIF watched once |
| 5. Hand off | `unity-2d-sprites` builds the clip from the frame folder at `fps_hint`; `art-asset-registry` ingests `frames.json` | the Unity acceptance reads; the ledger record |

The commands in full, the per-motion choices and a worked runner walk: `reference/pipeline.md`.

**Which cut for which motion** (`--state` sets the search window; `--mode` the kind of cut):

| Motion | Canvas `--state` | Prompt | Cut |
|---|---|---|---|
| walk, run | `walk` / `run` (square) | treadmill, continuous | `--state walk` / `run`, auto → loop |
| idle breath | — | — | `codex-visual` `breathe.py` on the keyed still |
| idle with a weight shift | `idle` (square) | in place, continuous | `--state idle` (no periodicity gate) |
| jump, launch | `jump` (tall 3:4, head-room 0.34) | one jump from standing, still for the last second | `--state jump --mode once` |
| attack, swipe | `attack` (wide 16:9, lead 0.28) | one attack from standing, back to stance | `--state attack --mode once`, or `oneshot` for a self-contained beat |

## Outputs

`video_loop.py` writes `OUT/NAME/NAME_000.png …` on **one canvas** (the union of every frame's box
plus `--margin`, bottom-aligned, never resampled) and `OUT/NAME/frames.json` beside them, with
`OUT/NAME.gif` (the preview) and `OUT/NAME.report.json` (the whole decision) **outside** the frame
folder, so a Unity folder import picks up frames only. `frames.json` follows the frame contract
of `codex-visual` → `reference/animation-scripts.md` §4: `canvas`, `pivot_norm` (foot centre,
from the bottom-left), `fps_hint` (output frames / cycle seconds), `loop`, `hold_last`, `register`
(mode `ground` with every frame seated on one feet line when it spreads by at most max(3 px, 2 % of
the body), `keep` for vertical travel),
`verdict{ok, faults}`, `producer{skill: sprite-from-video, script: video_loop.py}`, the clip's
`sha256`, and per frame its `source_frame`.

## Scope — what this skill does NOT do

- **Running the generation** — the server URL, uploads, the queue, model loading and `/free`,
  the H3 templates and their node ids: `comfyui-asset-generation`. This skill decides the canvas,
  the prompt and the cut; that skill runs the job.
- **The still itself, sprite sheets, the art bible and the key choice** — generating and keying
  the base still, `pick_key.py` for a key the subject does not contain, a grid sheet sliced into
  frames, a breathing idle from one frame (`breathe.py`): `codex-visual`.
- **Unity import** — slicing, the shared pivot, `AnimationClip`, loop vs one-shot playback, the
  frame audit: `unity-2d-sprites`.
- **The ledger** — recording the clip, the seed and the frames as one asset with links:
  `art-asset-registry`.
- **Choosing 2D frames over a rig** for a character: `game-character-pipeline`; 2D bones and
  skinning: `unity-2d-animation`.
- **Frame interpolation, repainting a frame, multi-direction sets**: not done. A bad clip is
  re-rolled.

Related: `comfyui-asset-generation` → `reference/minimax-h3.md` (modes, frame grid, audio),
`codex-visual` → `reference/animation-scripts.md` (the frames contract, `breathe.py`),
`unity-2d-sprites` → `reference/sprite-animation.md` (the clip from a frame folder).
