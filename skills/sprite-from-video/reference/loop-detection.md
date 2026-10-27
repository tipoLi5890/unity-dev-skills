# Loop detection, one-shot cuts and every refusal

How `video_loop.py` decides a cut, the numbers it decides with, and what to do when a script
refuses. §1–6 are the algorithm; §7–8 are the exit codes of all three scripts with their fixes.
The rule for every fix: **a bad clip is re-rolled, a good clip with a wrong cut gets an option.**

## 1. Distances and the lag profile

Every keyed frame is shrunk to fit 96 px and its colour multiplied by its alpha (so the empty
field counts as zero, whatever colour it was). `D[i, j]` is the mean absolute difference of two
such thumbnails, RGBA in 0..1 — a pose distance that ignores the key entirely.

The **lag profile** `P[L]` is the mean of `D[j, j+L]` over `j = 0, 2, 4 …`: how far a frame is,
on average, from the frame `L` later. A clip that repeats every `L` frames has a valley at `L` (and
at `2L`, `3L` …). The ordinary step is `D[k, k+1]`; seams and departures are measured in steps.

**The step cadence.** A generated clip can carry a regular rhythm in its steps — the largest
`D[k, k+1]` arriving every fourth frame, say. That is not
animation on twos (no step is zero) and it moves no valley, but it makes the ordinary step uneven:
read a seam ratio of 1.5 as "about one large step", not as a pop.

## 2. The period

**The window.** `--state` sets the lags searched (overridden by `--min-len` / `--max-len`, in
source frames):

| State | Window | Gait floor | Periodicity gate |
|---|---|---|---|
| `walk` | 0.5–1.6 s (ceiling capped at half the clip) | 0.6 s | on |
| `run` | 0.3–1.2 s | 0.35 s | on |
| `idle` | 60–95 % of the clip | — | off |
| `jump` | 11–45 % of the clip | — | on; auto fails over to a one-shot |
| any other state | 10–45 % of the clip | — | on; auto fails over to a one-shot |
| `attack` | 11 % of the clip to 2.5 s, half a second of context kept | — | on, scaled for partial coverage; auto fails over |

At 24 fps a walk searches 12–38 frames with its floor at 14.

**The period** is the smallest local minimum of `P` inside the window whose depth is within 15 %
of the deepest. A clean repeat also dips at twice and three times the period; taking the smallest
near-deepest valley takes the fundamental. A walk whose two steps take 0.92 s has its valley at 22
frames at 24 fps.

**The half-step guard** (walk and run). A gait's left step and right step look alike in
silhouette, so a valley at one step is common. Under the gait floor the period is one step: the
deepest minimum within 3 frames of `2P` is taken when `P[2P] ≤ 1.25 · P[P]`; otherwise there is
no full stride in the clip and it is refused (exit 2). Above the floor, a valley at `2P ± 1` about
as deep (within the same 25 %, and itself periodic), where `P` is not a near-exact repeat (over
0.10 steps off), is also taken — the cut then holds two phase occurrences rather than one stride
— and recorded as an `ambiguous-harmonic` fault (exit 3).

**Periodicity** `(mean P − P[period]) / mean P` must be at least 0.15: the valley has to stand out
of the profile. A clean treadmill walk reads about 0.5. Under the gate a loop is refused (exit 2);
in auto, a jump, attack or other action fails over to the one-shot detector, and the rejected
attempt is kept in `periodic_attempt`. Idle is exempt: a breath is not strictly periodic, and its
long window takes the smoothest seam instead.

**The multi-cycle screen.** At half and a third of the period, the deepest local minimum within a
frame is read: if it repeats (periodicity ≥ 0.15 on its own) and is no shorter than the window
floor (the gait floor for a gait), the loop may hold two or three cycles. That is a
`multi-cycle-suspect` fault with exit 3. The loop is **never cut shorter automatically**: the
message names the `--max-len` that would take the shorter cycle, and the preview decides.

## 3. The start and the seam

Over `L` in {P−1, P, P+1} and every start `i`, the cut scores
`|log(D[i+L−1, i] / mean adjacent step inside the cut)|`: the wrap from the cut's last frame back
to its first should be **one ordinary step**, neither a pop (ratio ≫ 1) nor a stall (≪ 1). For a
gait the score adds how far the quarter-cycle around the cut is from the same poses one cycle
later, in steps, so the chosen stride is one the clip actually repeats. The least score wins.

**The seam gate** reads the wrap again on the frames that ship (after subsampling): wrap over mean
step, at most `--seam-max` (2.0). When the drift ramp (§5) moved the frames, it is read on the moved
cells as well, and the cut passes if those read under the gate (`seam.read_on: moved-cells`).
It is then read at the source rate too, on every frame of the cut (`seam.source_rate_ratio`;
on the moved frames when the ramp moved them): subsampling can step over a pop between the cut's
last frame and its first, so a 20-frame cut of a walk whose stride is longer can read 1.7 on the
shipped frames and 2.9 at the source rate. Either over the gate, nothing is handed over (exit 2):
the loop pops at the seam.

## 4. One-shot and once

**`--mode oneshot`** looks for a pair of frames `start`, `end` that match (the return within a
quarter of the departure) and enclose a real action: the departure curve `(D[start] + D[end]) / 2`
peaks at least 3 MADs above its median (or the departure is 0.4 of the body's mean mass), the
action spans at least 4 frames with two rest frames kept on each side, and it departs at least 3
ordinary steps. Of the pairs within 95 % of the strongest departure, the **shortest** is cut.
The search runs up to 90 % of the clip (or the state window's ceiling, if longer; `--max-len`
overrides it), in `--mode oneshot` as in `auto`'s failover, so an action that fills most of the
clip is still found. For a
jump that is the rising crouch to the landing absorb — a beat that starts and ends bent. `loop:
false`, `hold_last: false`.

**`--mode once`** reads the steps `D[k, k+1]` against the clip's rest level (10th percentile) and
its range (to the 90th). The action starts at the first step past rest + 25 % of the range; the cut
begins two frames earlier. It ends on the first frame after the largest step from which every step
stays under rest + 10 % of the range for 0.2 s. So a jump cut by `once` runs stand → crouch → up →
land → stand, with `hold_last: true`. `auto` never picks `once`; ask for it.

## 5. Drift

**A loop:** the last frame's top 60 % (head and torso, from the first frame's box — the legs
are what moves) is registered against the first frame's over ±24 px, and that offset is spread as
a whole-pixel ramp `round(dx · k / L)` across the cycle. A treadmill walk that creeps 1–2 px per
cycle then wraps without a jump. `drift.wrap_dx_px` says how far.

**A one-shot or once:** a straight line fitted to the body's horizontal centre is removed —
horizontal only, since the vertical travel is the action. A jump that drifts sideways 13 px lands
where it took off. `drift.drift_removed_px` says how much.

`--no-drift` leaves every frame where it was filmed.

## 6. What the frames become

- **Subsampling.** `--fps` (12) picks evenly spaced frames from the cut: for a loop
  `round(k · L / cap)` with no repeat of frame 0 at the end, for a one-shot both ends kept.
  `--fps 0` keeps every frame. When `L` is not a multiple of the step, the gaps differ by one
  source frame (a 21-frame cut kept as 10: gaps of 2 and 3); `subsample.steps` lists them and
  `subsample.even` says whether they are one.
- **`fps_hint`** = output frames / cycle seconds, so the motion plays at the speed it was
  filmed: a 21-frame cut at 24 fps (0.875 s) kept as 10 frames is 11.43, not 12.
- **One canvas.** The union of every frame's box (alpha tails included) plus `--margin` (8) on every
  side, bottom-aligned; no frame is resampled, so pixels stay as keyed.
- **`register`**: the feet line is the lowest row of each frame's core silhouette (alpha over 127,
  opened by 4 px), the line `codex-visual`'s `audit_frames.py` gates. When it spreads by no more
  than max(3 px, 2 % of the body's height), loop or not, every frame is moved whole pixels up or
  down onto frame 0's line and the set is `ground` (spread 0); otherwise it is `keep` with nothing
  moved (a jump, a run's flight). `pivot_norm` is the first frame's
  foot centre (the alpha-weighted x of the lowest 20 % of its box) from the bottom-left.

## 7. Exit codes — `video_canvas.py` and `video_frames.py`

| Script, exit | Means | Fix |
|---|---|---|
| `video_canvas.py` 1 | bad arguments or an unreadable still | the command |
| `video_canvas.py` 2 | the four corners differ by more than 24 in a channel: the field is not one flat colour and cannot be extended | regenerate the still on a flat key (`codex-visual`), or key it there and composite it onto a flat field |
| `video_canvas.py` 3 | the corners are not a chroma key, `--key` names the wrong one, or a corner survives the keyer (a white or grey base is refused, not padded) | pick a key with `codex-visual`'s `pick_key.py` and regenerate the still on it; or pass the right `--key` |
| `video_frames.py` 1 | bad arguments, the clip missing or unreadable, ffmpeg/ffprobe missing or failing | install nothing yourself; ask the user for ffmpeg 5.1+; probe the file |
| `video_frames.py` 2 | a frame keyed to under 1 % transparent: the field is not this key | `--key` to the colour the canvas was padded with; a clip whose field changed colour mid-way is a re-roll (prompt: §1 of `reference/video-prompts.md`) |
| `video_frames.py` 3, `residual` | an opaque piece at the top, left or right edge that carries only the key's hue: leftover background, a gradient or vignette the keyer did not cut | normalise the still with `video_canvas.py` (it repaints the field to the exact key) and regenerate; `--allow-edge-contact` accepts it when the piece is known harmless |
| `video_frames.py` 3, `subject` | the character itself reaches the top, left or right edge: a jump out of the top, an arm or a walk out of the side | a taller or wider canvas (`video_canvas.py --state jump`, `--shape wide`, more `--headroom`/`--lead`) and regenerate; `--allow-subject-edge-contact` accepts it (a loop then has a clipped limb) |

The flatness report is a reading, never a gate. An `off_by` of 14–22 for a green field is
ordinary and is handled; a `border_std_max` climbing into the tens, or a `border_mean_drift_max`
in the tens, means the field changed during the clip — expect residual contact, and re-roll if it
appears.

## 8. Exit codes — `video_loop.py`

| Exit, message | Means | Fix |
|---|---|---|
| 1 | bad arguments, no frames, no source fps (a plain folder needs `--source-fps`), frames of different sizes, an empty frame | the command; feed it `video_frames.py`'s out-dir |
| 2, "no periodic cycle — the period profile is flat" | the motion does not repeat inside the window (periodicity under 0.15) | **re-roll**: the walk stopped, slowed, or drifted. For a genuine single action, `--mode oneshot` or `--mode once` |
| 2, "the only repeat is one step … the clip shows a half stride" | the clip holds one step, never the full left-right stride | **re-roll**, with a steadier rhythm; a stride longer than the window needs `--max-len` |
| 2, "the window … is empty" | the clip is shorter than the window for the state | a longer clip (`7.length`), or `--min-len`/`--max-len` |
| 2, "the loop's wrap is … mean steps: the loop pops at the seam" | no start in the window closes within 2.0 steps, on the shipped frames or at the source rate | **re-roll**; a cut that is right by eye but just over can take `--min-len`/`--max-len` to widen the search, never a larger `--seam-max` to hide the pop |
| 2, "no complete one-shot return" | the clip never leaves a rest pose and returns to it | `--mode once` when the action ends in a different held pose; otherwise re-roll with "stands still again for the last second" |
| 2, "no action to cut once" | fewer than 4 active steps, or a departure under 3 steps | the clip is nearly still: re-roll with the action stated plainly |
| 2, "the action never settles" | no 0.2 s window under the settle line after the largest step | re-roll with the end pose held still for the last second |
| 3, `multi-cycle-suspect` | the loop may hold two or three cycles | **watch the GIF**: count the strides; if it holds two, re-run with the `--max-len` the message names; if one, keep it |
| 3, `ambiguous-harmonic` | the profile repeats about as well at P and 2P; the cut holds 2P | watch the GIF; if it shows two full strides, re-run with `--max-len P+1` as the message says |

On exit 3 the frames, `frames.json` (`verdict.ok: false`, the faults named) and the GIF are
written, so the look decides. On exit 2 the frame folder and the GIF are removed and
`NAME.report.json` keeps the cut's diagnostics for reading.
