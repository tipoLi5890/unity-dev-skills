# Wording an in-place clip for H3

The prompt's job is narrow: one motion, performed **on the spot**, by the character in the first
frame, filmed by a camera that never moves, on a field that never changes. Everything a film prompt
usually asks for — camera moves, atmosphere, lighting, a ground to stand on, sound — is what breaks
the cut. H3's general prompt rules: `comfyui-asset-generation` → `reference/minimax-h3.md`.

## 1. The rules

| Rule | Wording | What it prevents |
|---|---|---|
| Preserve the first frame | open with "The supplied first frame must be preserved exactly." | a redrawn character whose outfit or proportions differ from the still |
| In place | "in place, as if on a treadmill"; "stays in the same spot and never moves across the screen" | a walk that leaves the frame (edge contact) or a loop whose body drifts |
| Fixed camera | "Fixed camera: no zoom, no pan, no cut, no reframing." | a scale or framing change between cycles, which no period survives |
| Flat key for the whole clip | "The background stays one perfectly flat pure chroma green #00FF00 fill edge to edge for the whole clip" | a gradient, vignette or lighting shift the keyer cannot cut |
| No floor, no shadow | "no floor, no shadow, no gradient, no lighting change" | a contact shadow keyed in as part of the feet, a floor line that becomes a stripe |
| Real-time pace | "Smooth motion at full frame rate, real-time pace"; for an action, "no slow motion, no lingering pose" | a slow-motion stride whose period exceeds the window, a held pose mid-action |
| Observable rhythm | "about one step every half second, continuous for the whole clip" | a walk that stops halfway, leaving fewer cycles to choose from |
| A clear end for an action | "lands on the same spot, absorbs the landing and stands still again for the last second" | a one-shot with no settled end (`--mode once` refuses it) |
| Silent | "Silent: no music, no voice, no sound effects." | words spent on a track that is discarded anyway; H3 still decodes one, and `video_frames.py` leaves it out |

Name the key the canvas carries: `#00FF00` for a green field, `#FF00FF` for magenta, matching
`video_canvas.py`'s `key` in its output.

## 2. Failures and the wording that fixes them

| The clip came back… | Change |
|---|---|
| nearly frozen | the motion must be the subject of the prompt and continuous for the whole clip; never give the same still as both first and last frame |
| walking across the frame | say "in place" twice: as the action ("walks in place, as if on a treadmill") and as a constraint ("never moves across the screen") |
| zooming or reframing between steps | the fixed-camera sentence, verbatim; drop every word that suggests a shot (close-up, follows, tracking) |
| with a shadow or floor | "no floor, no shadow" in the background sentence; a still with a drawn floor needs regenerating first |
| with frames repeated in pairs | remove "stop-motion", "frame by frame", "12 fps" and any style word that implies held frames: they invite animation on twos, where every second step distance is zero |
| too slow, the stride over the window | "real-time pace", and a concrete rate ("one step every half second") |
| jumping out of the top of the frame | a tall canvas (`video_canvas.py --state jump`) and "reaches the top in the upper part of the frame" |
| with the action ending mid-move | "stands still again for the last second" |

**Never write "stop-motion".** It asks for exactly the held, doubled frames the period and seam
measurements read as noise.

## 3. Worked prompts

The runner is the courier-run character: a young courier in a teal jacket, dark grey cargo shorts,
white sneakers and a small orange satchel, side view facing right. The prompt does not describe
the character again — the first frame does that; it names the motion and the constraints.

**`runner_walk`** — square canvas, `--state walk`, cut by `--state walk`:

```text
The supplied first frame must be preserved exactly. The courier runner, side view facing right,
walks naturally in place, as if on a treadmill: legs alternate in full steps, arms swing opposite
to the legs, the satchel bounces lightly, steady even rhythm, about one step every half second,
continuous for the whole clip. The runner stays in the same spot and never moves across the
screen. Fixed camera: no zoom, no pan, no cut, no reframing. The background stays one perfectly
flat pure chroma green #00FF00 fill edge to edge for the whole clip: no floor, no shadow, no
gradient, no lighting change. Smooth motion at full frame rate, real-time pace. Silent: no music,
no voice, no sound effects.
```

**`runner_run`** — the same, with the gait and rate changed: "runs in place, as if on a treadmill:
knees lift high, arms pump hard, a quick even rhythm, about three steps every second, continuous
for the whole clip". Cut with `--state run`.

**`runner_launch`** — the jump onto the next lane; tall canvas, `--state jump`, cut with
`--mode once`:

```text
The supplied first frame must be preserved exactly. The courier runner, side view facing right,
does one vertical jump in place: from standing he crouches briefly, springs straight up, reaches
the top in the upper part of the frame, lands on the same spot, absorbs the landing and stands
still again for the last second. He does not move left or right. Fixed camera: no zoom, no pan,
no cut, no reframing. The background stays one perfectly flat pure chroma green #00FF00 fill edge
to edge for the whole clip: no floor, no shadow, no gradient, no lighting change. Real-time pace,
no slow motion, no lingering pose. Silent: no music, no voice, no sound effects.
```

**`sentry_swipe`** — the sentry at the gate; wide canvas, `--state attack --facing left`, cut
with `--mode once`:

```text
The supplied first frame must be preserved exactly. The sentry, side view facing left, stands at
guard and makes one fast forward swipe with the baton: a short wind-up, the swipe, the follow-
through, then returns to the same guard stance and holds it still for the last second. The feet
stay planted on the same spot the whole time. Fixed camera: no zoom, no pan, no cut, no
reframing. The background stays one perfectly flat pure chroma green #00FF00 fill edge to edge
for the whole clip: no floor, no shadow, no gradient, no lighting change. Real-time pace, no slow
motion, no lingering pose. Silent: no music, no voice, no sound effects.
```

**`sentry_idle`** — only when the idle must shift its weight; a breath alone is `breathe.py`
(`codex-visual` → `reference/animation-scripts.md`). Square canvas, cut with `--state idle`:

```text
The supplied first frame must be preserved exactly. The sentry stands in place, side view facing
left, waiting at the gate: slow breathing, chest and shoulders rise and fall gently, a small
natural weight shift from one foot to the other and back, arms relaxed. The feet stay planted on
the same spot the whole time; the sentry never walks or moves across the screen. Fixed camera: no
zoom, no pan, no cut, no reframing. The background stays one perfectly flat pure chroma green
#00FF00 fill edge to edge for the whole clip: no floor, no shadow, no gradient, no lighting
change. Smooth, evenly paced motion at full frame rate. Silent: no music, no voice, no sound
effects.
```

No prompt asks for "the last frame returns to the first": with image-to-video there is no last
frame to hold to, and the loop's seam is found by `video_loop.py`, not requested.
