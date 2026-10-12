---
name: unity-camera
description: >-
  Build and debug game cameras in Unity 6 with Cinemachine: 2D side follow with
  a room confiner, runner, top-down, isometric, pixel-perfect follow,
  third-person orbit with deocclusion, first person, fixed rigs, shake and
  blends, plus the 2.x to 3.x name table, a rig builder, a camera probe and a
  journey that proves a rig holds. Load for: "the camera jitters", "the player
  stutters when the camera follows", "CinemachineVirtualCamera not found", "the
  camera shows outside the level", "the camera pans across the map after a
  respawn", "the camera clips through walls". The pixel-perfect camera
  component is unity-2d-pixel-perfect; look input is unity-input; recording a
  run is unity-play-harness.
---

# unity-camera — a jittering camera is two clocks disagreeing

> **Camera jitter is almost never a damping value.** The target moves on one clock — the
> physics step — and the camera eases on another — the rendered frame — and at 60 frames against
> 50 steps a second, one frame in six has no step in it. No amount of smoothing removes a beat
> between two clocks; putting both on one clock removes it completely. Find the two clocks
> before touching a number.

## Symptom → where to look

First match wins.

| Symptom | Go to |
|---|---|
| A component the tutorial names does not exist; `CS0246` on a Cinemachine type | §0 |
| The camera or the player jitters, shivers or stutters while moving | §1 |
| The camera pans across the level after a respawn or a door | §1 — a teleport is a cut |
| The camera freezes, or a blend stops half way, while the game is paused | §1 — time scale |
| The view doubled, or the field of view changed, when the rig was added | §2 — the lens belongs to the rig now |
| The camera shows outside the level; the confiner does nothing | §2 |
| The confiner is wrong after a zoom, or after the room's outline was edited | §2 — two caches |
| The camera slides through a wall between two rooms | §2 — room to room |
| Which rig for a side view, a runner, a top down or an isometric game | §2 |
| Pixel art shimmers, or the size pops, under a follow camera | §3 |
| Which rig for third person, first person or fixed cameras | §4 |
| The camera clips through walls, or pumps in and out along one | §4 — deocclusion |
| The stick does not turn the camera; look input is dead during a blend | §4 — input axes |
| Lock on to an enemy | §4 — a second target |
| Shake does nothing, or ten small shakes add up to one huge one | §5 |
| The camera cuts where it should blend, or drifts after a cutscene | §5 |
| "It looks fine to me" — proving a rig holds on every frame | §6 |

## 0. Read the lock before naming a component

Cinemachine 2.x and 3.x share a package id and almost no component names. Read
`Packages/packages-lock.json` for `com.unity.cinemachine` first:

| The lock says | The camera component | Namespace | Asmdef reference |
|---|---|---|---|
| `2.x` | `CinemachineVirtualCamera`, fields prefixed `m_` | `Cinemachine` | `Cinemachine` |
| `3.x` | `CinemachineCamera`, plain fields | `Unity.Cinemachine` | `Unity.Cinemachine` |

- **An add with no version on Unity 6 resolves 2.10.7.** 3.x is always an explicit pin:
  `"com.unity.cinemachine": "3.1.7"` in `Packages/manifest.json`.
- **Everything shipped here is written for 3.x** and says so in its `REQUIRES` line. A 2.x project
  follows the same recipes through the name table: `reference/version-and-names.md`.
- **Body and Aim became Position Control and Rotation Control**, and the components moved from
  a hidden child onto the camera's own GameObject: `AddComponent<T>()`.
- **3.x still compiles the 2.x names**, marked `[Obsolete]`: `CS0618` naming
  `CinemachineVirtualCamera` means the rig is on the compatibility layer.

Every recipe below is the same rig: the output `Camera` with a `CinemachineBrain` at the scene
root, never parented to the player; one or more `CinemachineCamera` objects, each with a tracking
target; and the Brain showing the enabled one with the highest `Priority`.
`resources/Editor/CameraRigBuilder.cs` builds a 2D follow rig, a third-person rig and a fixed rig
from `Tools/Unity Dev/Camera/`, and reports what it will create before creating it.

## 1. Jitter: find the two clocks

| What moves | Its clock |
|---|---|
| A `Transform` written in `Update`; `CharacterController.Move` from `Update` | Rendered frame |
| A `Rigidbody` / `Rigidbody2D`, interpolation `None` | Physics step |
| A `Rigidbody` / `Rigidbody2D`, interpolation `Interpolate` | Rendered frame |
| A `Transform` written in `FixedUpdate` with no body | Physics step, and nothing can interpolate it |
| The Cinemachine camera | Whichever the Brain's `UpdateMethod` puts it on |

Work down; stop at the first that applies.

1. **The followed body has interpolation `None`.** Set `Interpolate`. This is the fix in most
   projects, it is one property, and it costs one physics step of visual latency on that body.
2. **The Brain was forced off `SmartUpdate`**, which watches each target and puts its camera
   on that target's clock. `LateUpdate` under an uninterpolated body, or `FixedUpdate` over an
   `Update`-driven character, is the mismatch written down as a setting.
3. **One Transform has two writers** — a body stepped by physics and a script nudging the same
   object in `Update`. `SmartUpdate` changes its mind between windows and the jitter comes in
   bursts. One writer per Transform.
4. **A hand-written follow runs in `FixedUpdate`, or in `Update` before the player moved.** Read
   the target and write the camera in `LateUpdate`, damped with `Time.deltaTime`.
5. **The offset measures smooth and it still looks wrong.** Then it is not a clock: look-ahead
   amplifying noise, a pixel snap (§3), the deoccluder (§4), or an uneven frame time.

**A teleport has to be announced.** A damped camera cannot tell a respawn from a very fast run,
so it pans across the level. `CinemachineCore.OnTargetObjectWarped(target, delta)` carries the
camera with the target; `vcam.PreviousStateIsValid = false` makes the next frame a cut.

**At `timeScale` 0 the camera gets a delta of zero.** Damping freezes and blends stop.
`CinemachineBrain.IgnoreTimeScale` is the pause-menu setting, and it also makes the camera ignore
slow motion.

Every pair of clocks with its symptom and fix, the three teleport calls, and the pause table:
`reference/update-order-and-jitter.md`. Measure before and after with §6.

## 2. 2D rigs: side follow, runner, top down, isometric

All four are one rig — an orthographic `Camera`, a `CinemachineCamera` with rotation identity, a
`CinemachinePositionComposer`, and usually a `CinemachineConfiner2D` — with different numbers.

| Game | Screen position | Dead zone | Damping (x, y) | Look-ahead |
|---|---|---|---|---|
| Side view platformer | (−0.15, −0.1) | 0.10 × 0.15 | 0.5, 0.3 | 0.25 s, ignore Y |
| Auto-runner, side | (−0.25, −0.1) | 0 × 0.15 | 0, 0.3 | Off — the offset is the look-ahead |
| Top down | (0, 0) | 0.08 × 0.08 | 0.3, 0.3 | 0.15 s |
| Isometric on a cell grid | (0, 0) | 0.08 × 0.08 | 0.2, 0.2 | Off |

- **Screen position 0 is the centre in 3.x**; in 2.x the centre is 0.5.
- **A new `CinemachineCamera` carries its own lens — orthographic size 10, field of view 40 —
  and overwrites the `Camera`.** Set the size on the Cinemachine camera; the `Camera`'s own value
  is no longer the setting.
- **Hard limits are off by default.** Turn them on: damping is a preference, the hard limit is
  what keeps the player on screen.
- **`CinemachineConfiner2D` accepts a Box, Polygon or Composite collider and silently ignores any
  other.** It has no effect until `BoundingShapeIsBaked`.
- **Two caches, two calls.** `InvalidateBoundingShapeCache()` after the outline's points change;
  `InvalidateLensCache()` after any zoom. A new collider or a new aspect ratio is noticed
  without either.
- **Room to room: one camera per room, switched by priority, is the default.** Each confiner
  bakes once and the Brain blends. `resources/RoomConfinerSwitch.cs` is the one-camera
  alternative for a few rooms at one zoom.
- **The lane run tracks an anchor, not the runner**: the anchor copies the runner's forward
  position and 35 % of its sideways offset, so a lane change of 1.3 units moves the camera 0.45.
- **Orthographic size is half the view height.** To hold a width, compute `W / (2 × aspect)`.

World-unit conversions, the cache table, both room recipes, the anchor script, 3D top down and
isometric angles, and zoom: `reference/follow-2d.md`.

## 3. Pixel-perfect follow

A pixel-perfect camera and Cinemachine both write orthographic size every frame. **Add the
`CinemachinePixelPerfect` extension to every Cinemachine camera that can go live**, on the
camera's own object. One camera without it breaks the shot it owns, because once the extension
has been used the pixel camera stops writing the size itself.

- The extension compiles to an empty component unless the project has URP or
  `com.unity.2d.pixel-perfect` 2.0.3 or newer. Read the lock.
- Legal sizes are the pixel camera's size divided by whole numbers. A smooth zoom arrives as
  steps; a blend between two sizes is not pixel-perfect while it runs.
- Damping makes the camera and the sprite round to the pixel grid on different frames: a
  one-pixel wobble with a perfectly smooth offset. Zero damping on the axis of travel is the
  default for pixel art.

The four checks, the size table and the damping options: `reference/pixel-perfect-follow.md`.
The pixel camera component itself is `unity-2d-pixel-perfect`.

## 4. 3D rigs: orbit, shoulder, lock on, first person, fixed

| Rig | Position Control | Rotation Control | Also |
|---|---|---|---|
| Third-person orbit | `CinemachineOrbitalFollow` | `CinemachineRotationComposer` | `CinemachineInputAxisController`, `CinemachineDeoccluder` |
| Over the shoulder | `CinemachineThirdPersonFollow` | None — it turns with the target | `CinemachineThirdPersonAim` |
| First person | `CinemachineHardLockToTarget` on a head pivot | `CinemachinePanTilt` | `CinemachineInputAxisController` |
| Fixed post | None | None, or `CinemachineRotationComposer` to turn and track | Priority switching |

- **Track a pivot at chest height**, or give the components a target offset of (0, 1.5, 0). The
  runner's root is at its feet.
- **Reset() does not run for components added from code in play mode.** Orbit radius is then 10,
  not 5, and the deoccluder's obstacle avoidance is off. Assign every field.
- **Deoccluder or decollider.** `CinemachineDeoccluder` keeps the target visible;
  `CinemachineDecollider` only keeps the camera out of geometry. Give the deoccluder the
  runner's tag to ignore, 0.1 s of minimum occlusion and 0.2 s of smoothing, or it pumps.
- **Lock on is a second target**: the runner stays the tracking target, the sentry becomes the
  look-at target. Build it as a second, higher-priority camera that frames a target group of
  both.
- **In first person the camera owns the look angles and the body copies the yaw.** The reverse
  is a feedback loop. No damping anywhere on this rig.
- **Fixed cameras: movement stays relative to the camera that was live when the stick was
  pushed**, or every cut reverses the runner.
- **Look input** reaches an axis through `CinemachineInputAxisController` and the project's own
  Look action, or the game writes the axis value from the input struct it already reads.

Component tables, the deoccluder settings, the lock-on rig, first-person rules, switching by
trigger, and the input controller: `reference/follow-3d.md`.

## 5. Shake and blends

- **A source needs a listener.** `CinemachineImpulseSource` on the cause,
  `CinemachineImpulseListener` on every camera that should react.
- **Write the budget first**: 3 % of view height at most, 0.1 to 0.3 s, three named tiers,
  `UseLargest` so overlapping hits do not sum, and a player slider multiplied into the
  listener's gain.
- **Shake is applied after the confiner** and reads scaled time.
- **The default blend is 2 s.** Set 0.4 s for gameplay, and name the cuts in the Brain's custom
  blends — which match cameras by name.
- **A Timeline hands the camera back cleanly when its last shot is the gameplay camera** and the
  camera state is reset if the runner was moved.

The definition and listener tables, blend hints, the activation event and the hand-off:
`reference/shake-and-blends.md`. Building the Timeline is `unity-animation`.

## 6. Prove the rig holds

`resources/CameraProbe.cs` puts three facts on the probe every frame, latched after the Brain
has run so the pair is from one instant:

| Key | Meaning |
|---|---|
| `camViewport` | The player is inside the viewport |
| `camInBounds` | Every corner of the view is inside the bounds given to `SetBounds` |
| `camOffset` | Camera position minus player position |

`templates/CameraJourneyTest.cs` builds a side-run room, a runner and a follow rig, records 600
frames and asserts all three. `scripts/camera_jitter.py` reads the timeline and counts how often
the offset's frame-to-frame delta changes sign:

```bash
python3 scripts/camera_jitter.py journeys/camera-side-run/timeline.jsonl --axis x
```

A damped follow measures about 0.01, two clocks about 0.3; the limit is 0.1, and a missing key
exits 1 too. **Break it once**: `CAMERA_JOURNEY_BREAK=confiner` and `CAMERA_JOURNEY_BREAK=clocks`
must each turn the journey red before a green run means anything.

Framing, shake feel and pixel shimmer stay a person's judgement, from a windowed capture.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| The pixel-perfect camera component, reference resolution, import settings | `unity-2d-pixel-perfect` |
| Input actions, control schemes, pointer and stick aim, rebinding | `unity-input` |
| Which perspective and movement model the game's constraints imply | `unity-gameplay` |
| The 3D character the camera follows: its controller, view-relative movement | `unity-3d-controller` |
| The probe, situations, journeys and the timeline format themselves | `unity-play-harness` |
| Timeline authoring, Animator states, root motion | `unity-animation` |
| Why a body does not move, or a cast misses the wall | `unity-physics-3d` · `unity-physics-2d` |
| Parallax layers, sorting layers, draw order | `unity-2d-rendering` |
| Room bounds as level data, rooms and chunks | `unity-2d-level` |
| Post-processing, renderer features, the 2D renderer | `unity-render-urp` |
| Uneven frame time, GC spikes | `unity-profiling` |
| Adding and pinning packages, asmdef layout | `unity-new-project` |
| Running tests headless, reading a windowed capture | `unity-debug` |
