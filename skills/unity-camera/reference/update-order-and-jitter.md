# Update order and jitter — find the two clocks

> Part of the `unity-camera` skill. `SKILL.md` §1 states the rule: a jittering camera is two
> clocks disagreeing. This file names every clock in the frame, gives the fix for each pair,
> covers the teleport and the pause, and shows how to prove the diagnosis with a recorded journey
> before changing a damping value. Names are Cinemachine 3.x; the 2.x spellings are in
> `reference/version-and-names.md`.

## The clocks in one frame

Unity runs zero, one or several physics steps, then one rendered frame:

```
FixedUpdate ×N      scripts that drive a Rigidbody
physics step ×N     non-interpolated bodies write their Transform here
Update              scripts that move a Transform; coroutines resume after it
LateUpdate          the Brain (execution order 100) positions the Camera
render
```

N is not constant. At 60 rendered and 50 simulated frames a second, five frames in six have one
step and the sixth has none. Anything that advances once per step and is looked at once per
frame therefore stands still on one frame in six.

| What moves | Its clock |
|---|---|
| A `Transform` written in `Update`, a `CharacterController.Move` called from `Update`, an Animator in Normal mode | Render frame |
| A `Rigidbody` or `Rigidbody2D` with interpolation `None` | Physics step |
| A `Rigidbody` or `Rigidbody2D` with interpolation `Interpolate` | Render frame — the Transform is blended between the last two steps before `Update` |
| A `Transform` written in `FixedUpdate` with no body | Physics step, and nothing can interpolate it |
| An Animator with Update Mode Fixed (root motion on a body) | Physics step |
| The Cinemachine camera's own damping | Whichever clock the Brain updates that camera on |
| The Unity `Camera` transform | The Brain's Blend Update Method |

Jitter needs two of those rows on different clocks **and** something that compares them every
frame — damping, a dead zone edge, look-ahead. A hard-locked camera with zero damping on the
wrong clock does not jitter relative to its target; the world behind it stutters instead.

## What the Brain does with each setting

`CinemachineBrain.UpdateMethod` decides when the Cinemachine cameras compute; `BlendUpdateMethod`
decides when the result is written to the Unity `Camera`.

| `UpdateMethod` | Cameras compute |
|---|---|
| `SmartUpdate` (default) | Per camera: after the physics step when its target moves on the physics clock, in `LateUpdate` otherwise |
| `LateUpdate` | In `LateUpdate`, with `Time.deltaTime` |
| `FixedUpdate` | After each physics step, with `Time.fixedDeltaTime` |
| `ManualUpdate` | Only when the game calls `brain.ManualUpdate()` — never from `FixedUpdate` |

`SmartUpdate` decides by watching the target's Transform over a 30-frame window: it counts the
frames in which the Transform changed during physics and the frames in which it changed by
`LateUpdate`, and picks the physics clock only when there are more than three physics moves and
fewer than a third as many late moves. Three consequences:

- **An interpolated body reads as a render-frame target**, because its Transform changes every
  frame. That is the correct answer, and it is why interpolation plus the default Brain works.
- **A target moved on both clocks confuses the vote.** A body stepped by physics whose child
  model is also nudged in `Update`, or a controller that writes `transform.position` in `Update`
  and velocity in `FixedUpdate`, can change the vote from one window to the next — jitter that
  comes and goes in bursts of 30 frames.
- **The first frames are a guess.** A new target starts on the render-frame clock and moves to
  the physics clock only after four physics moves have been seen. A journey that samples from
  frame zero records that; start sampling after the readiness set.

`BlendUpdateMethod` stays `LateUpdate` unless every target is a non-interpolated body and the
Brain's `UpdateMethod` is `FixedUpdate` — then both go to `FixedUpdate`, and the whole view runs
at the simulation rate.

## The pairs, and the fix for each

| Target moves on | Camera computes on | Looks like | Fix |
|---|---|---|---|
| Physics, interpolation `None` | `LateUpdate` | The player shivers against the frame while standing scenery is smooth | **Set interpolation to `Interpolate` on the body.** One property; do this first |
| Physics, interpolation `None` | Physics (Smart or Fixed) | Player and camera agree; everything animated in `Update` shivers, and the whole view steps at the simulation rate | Interpolate the body, so the camera can return to `LateUpdate` |
| `Update` | `FixedUpdate` (Brain forced) | The player shivers while the world is smooth | Put the Brain back on `SmartUpdate` |
| A `Transform` written in `FixedUpdate`, no body | `LateUpdate` | The same as the first row, and interpolation is not available | Move the write to `Update` with `Time.deltaTime`, or put a kinematic interpolated body on it and use `MovePosition` |
| Both clocks (see above) | Alternates | Jitter in bursts | One writer per Transform; the model follows the body as a child and is never moved separately |
| `Update` | `LateUpdate` | Smooth | — |
| Interpolated body | `LateUpdate` | Smooth | — |

Interpolation is the answer in four of five broken rows. It costs one physics step of visual
latency on that body and nothing else; apply it to every body a camera follows and to every body
the player watches closely.

A hand-written follow script obeys the same table. Its rule in one line: **read the target and
write the camera in `LateUpdate`, damp with `Time.deltaTime`, and interpolate the body.** A
follow in `FixedUpdate` is the second row.

Parenting the Unity `Camera` under the player is the remaining clock: the camera then inherits
the player's Transform on the player's clock and the Brain overwrites it on its own. The output
camera sits at the scene root.

## Jitter that is not a clock

Work these only after the offset has been measured smooth (below).

| Cause | Tell | Fix |
|---|---|---|
| Look-ahead amplifying noisy motion | Stops when `Lookahead.Enabled` is off | Lower `Lookahead.Time`, raise `Lookahead.Smoothing`, or smooth the target |
| Dead zone edge with zero damping | Camera snaps a pixel each time the target touches the edge | Give the composer damping of 0.2 or more on that axis |
| A pixel-perfect camera and Cinemachine both writing the size | Size pops between two values | `reference/pixel-perfect-follow.md` |
| The deoccluder hunting between two resolutions | Only near walls | `reference/follow-3d.md`, the deocclusion section |
| Frame time itself is uneven | Everything stutters, the offset is smooth | `unity-profiling` |

## A teleport is a cut, and the camera has to be told

A respawn, a door between rooms, a wrap at the screen edge: the target jumps, and a damped camera
does what damping does — it pans across the level to catch up. The camera cannot tell a teleport
from a very fast run. Three calls, by intent:

```csharp
// The player moved and the camera should move with it, keeping its offset and its damping
// state. A world-origin shift, a wrap, a moving platform snap.
Vector3 delta = destination - runner.position;
runner.position = destination;
CinemachineCore.OnTargetObjectWarped(runner, delta);

// The camera should appear at the new place as if the shot started there: no damping,
// no blend, no look-ahead history. A respawn, a door, a cutscene end.
runner.position = destination;
vcam.PreviousStateIsValid = false;                    // this camera
CinemachineCore.ResetCameraState();                   // or every camera and every Brain

// The camera is placed by hand and the rig continues from there.
vcam.ForceCameraPosition(position, rotation);
```

With a `Rigidbody`, teleport by assigning `body.position`. `MovePosition` on an interpolated
body is a move, not a teleport: it is drawn as a sweep through everything in between.

A teleport that uses none of the three reads in a timeline as one sample with a very large
`camOffset` followed by a long monotonic decay. That signature is a missing cut, not jitter.

## `timeScale` 0

The Brain computes with scaled time, so at `Time.timeScale == 0` every camera receives a delta
of zero: damping freezes, blends stop half way, an orbit does not answer the stick.

| What must keep moving while paused | Setting |
|---|---|
| Camera damping and blends (a pause menu that pans, a photo mode) | `CinemachineBrain.IgnoreTimeScale = true` — the Brain uses unscaled delta time |
| Orbit and pan-tilt input | `CinemachineInputAxisController.IgnoreTimeScale = true` on that camera |
| Shake that should play over the pause | `CinemachineImpulseManager.Instance.IgnoreTimeScale = true` |

`IgnoreTimeScale` on the Brain applies to slow motion too: a camera that ignores time scale
follows a slowed player at full speed. For bullet time, leave it off; for a pause menu, turn it
on with the menu and off again with it.

Physics does not step at `timeScale` 0, so a follow target on the physics clock holds its last
interpolated pose. A camera that keeps moving while the game is paused is an unscaled camera
looking at a frozen world; that is correct, and it is the only case where the two clocks are
supposed to disagree.

## Prove it before changing a number

The eye cannot tell a clock mismatch from a tuning problem; the offset between camera and player
can. `resources/CameraProbe.cs` registers that offset on the probe as `camOffset`, a journey
records it every frame, and `scripts/camera_jitter.py` counts how often its frame-to-frame delta
changes sign.

1. Attach `CameraProbe` to any object, assign the player. It latches its values at the end of
   `LateUpdate`, after the Brain, so the pair it reports was true at the same instant. Reading
   the two transforms from the test coroutine would pair this frame's player with last frame's
   camera — a third clock, and the measurement would report jitter in a clean rig.
2. Record a journey in which the player moves at a steady speed for several seconds —
   `templates/CameraJourneyTest.cs`, or any journey from `unity-play-harness` once the probe is
   in the scene. Pin the frame time with `Time.captureDeltaTime = 1f / 60f` for the run and
   restore it afterwards: the step-per-frame pattern is then identical on every machine.
3. Read the timeline:

```bash
python3 scripts/camera_jitter.py journeys/camera-side-run/timeline.jsonl --axis x
```

```
[JITTER] violations=1 samples=600 journey=camera-side-run key=camOffset worstFlipRate=0.333 limit=0.100 end=ok
  x  flips=199 moving=599 rate=0.333 maxDelta=0.133
  VIOLATION camOffset.x flip rate 0.333 over 0.100 (199 flips in 599 moving frames)
```

| Flip rate on the travel axis | Reading |
|---|---|
| Under 0.05 | The offset eases. One or two flips per change of direction is a camera lagging and catching up |
| 0.25 to 0.4 | One reversal every three or four frames: the 60-against-50 beat. Two clocks |
| Near 1.0 | Every frame reverses: two writers on one Transform, or a snap fighting a damper |
| 0 with `moving=0` | The offset never changed: a hard lock. Clean relative to the player; check the scenery by eye |

The limit of 0.1 separates the first two rows with room on both sides. A rate between 0.05 and
0.25 is a rig that is mostly on one clock: look for `SmartUpdate` changing its mind.

Then apply the fix from the table, record again and compare. The same file feeds
`unity-play-harness` → `reference/timeline-format.md` for a before-and-after table of any other
key.

What the measure does not see: the stutter of the second row, where camera and player step
together. For that, sample the player's own position and look for frames where it does not
change while `speed` is non-zero — the frame with no physics step.

## Related skills

Recording and reading journeys, and what stays a human judgement: `unity-play-harness`. A frame
time that is uneven by itself: `unity-profiling`. Why a body does or does not move in a step:
`unity-physics-3d`.
