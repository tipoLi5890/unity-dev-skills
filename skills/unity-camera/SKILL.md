---
name: unity-camera
description: >-
  Cinemachine game cameras: follow, confiner, orbit, first person, shake;
  jitter and wall clipping.
---

# unity-camera — a jittering camera is two clocks disagreeing

> **Camera jitter is almost never a damping value.** The target moves on one clock — the
> physics step — and the camera eases on another — the rendered frame — and at 60 frames against
> 50 steps a second, one frame in six has no step in it. No amount of smoothing removes a beat
> between two clocks; putting both on one clock removes it completely. Find the two clocks
> before touching a number.

## Symptom → where to look (first match wins)

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
| A court or pitch sport: broadcast framing, follow, between-point and end moves | `reference/broadcast-sports.md` |
| "It looks fine to me" — proving a rig holds every frame | §6 |

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

Every recipe is one rig: the output `Camera` with a `CinemachineBrain` at the scene root, never
parented to the player, and `CinemachineCamera` objects with tracking targets; the Brain shows the
enabled one with the highest `Priority`. `resources/Editor/CameraRigBuilder.cs`
(`Tools/Unity Dev/Camera/`) builds 2D follow, third-person and fixed rigs, reporting first.

## 1. Jitter: find the two clocks

| What moves | Its clock |
|---|---|
| A `Transform` written in `Update`; `CharacterController.Move` from `Update` | Rendered frame |
| A `Rigidbody` / `Rigidbody2D`, interpolation `None` | Physics step |
| A `Rigidbody` / `Rigidbody2D`, interpolation `Interpolate` | Rendered frame |
| A `Transform` written in `FixedUpdate` with no body | Physics step, and nothing can interpolate it |
| The Cinemachine camera | Whichever the Brain's `UpdateMethod` puts it on |

Work down; stop at the first that applies.

1. **The followed body has interpolation `None`** → set `Interpolate` (one property, one step of
   visual latency on that body). The fix in most projects.
2. **The Brain was forced off `SmartUpdate`**, which puts each camera on its target's clock.
3. **One Transform has two writers** (physics and an `Update` script) → jitter in bursts.
4. **A hand-written follow runs in `FixedUpdate`, or before the player moved** → `LateUpdate`,
   damped with `Time.deltaTime`.
5. **The offset measures smooth and still looks wrong** → not a clock: look-ahead noise, a pixel
   snap (§3), the deoccluder (§4), or an uneven frame time.

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

- **Screen position 0 is the centre in 3.x** (0.5 in 2.x). **A new `CinemachineCamera` carries
  its own lens** — orthographic size 10, field of view 40 — and overwrites the `Camera`'s.
- **Turn hard limits on**: damping is a preference, the hard limit keeps the player on screen.
- **`CinemachineConfiner2D` takes a Box, Polygon or Composite collider only**, and does nothing
  until `BoundingShapeIsBaked`. `InvalidateBoundingShapeCache()` after the outline changes,
  `InvalidateLensCache()` after any zoom.
- **Room to room: one camera per room, switched by priority**; `resources/RoomConfinerSwitch.cs`
  is the one-camera alternative. **The lane run tracks an anchor** at 35 % of the runner's
  sideways offset. **Orthographic size is half the view height**: hold a width with `W / (2 × aspect)`.

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

- **Track a pivot at chest height** (or a target offset of (0, 1.5, 0)) — the root is at the feet.
- **`Reset()` does not run for components added from code in play mode** (orbit radius 10, not 5;
  obstacle avoidance off): assign every field.
- **`CinemachineDeoccluder` keeps the target visible; `CinemachineDecollider` only keeps the
  camera out of geometry.** Ignore the runner's tag, 0.1 s minimum occlusion, 0.2 s smoothing.
- **Lock on is a second, higher-priority camera** framing a target group of runner and sentry.
- **First person: the camera owns the look angles, the body copies the yaw**; no damping.
- **Fixed cameras: movement stays relative to the camera live when the stick was pushed.**
- **Look input** goes through `CinemachineInputAxisController`, or the game writes the axis from
  its input struct.

Component tables, the deoccluder settings, the lock-on rig, first-person rules, switching by
trigger, and the input controller: `reference/follow-3d.md`.

## 5. Shake and blends

- **A source needs a listener**: `CinemachineImpulseSource` on the cause, a
  `CinemachineImpulseListener` on every camera that reacts.
- **Budget first**: ≤ 3 % of view height, 0.1–0.3 s, three named tiers, `UseLargest`, and a
  player slider on the listener's gain.
- **Shake is applied after the confiner** and reads scaled time.
- **The default blend is 2 s.** Set 0.4 s for gameplay, and name the cuts in the Brain's custom
  blends — which match cameras by name.
- **A Timeline hands back cleanly when its last shot is the gameplay camera**, with the camera
  state reset if the runner moved.

The definition and listener tables, blend hints, the activation event and the hand-off:
`reference/shake-and-blends.md`. Building the Timeline is `unity-animation`.

## 6. Prove the rig holds

`resources/CameraProbe.cs` puts `camViewport`, `camInBounds` and `camOffset` on the probe every
frame; `templates/CameraJourneyTest.cs` records 600 frames of a side-run room and asserts them;
`scripts/camera_jitter.py` counts sign changes in the offset (limit 0.1). **Break it once**
(`CAMERA_JOURNEY_BREAK=confiner`, `=clocks`) before a green run means anything. Keys, command
and numbers: `reference/prove-the-rig.md`. Framing and shake feel stay a person's judgement.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| The pixel-perfect camera component, reference resolution, import settings | `unity-2d-pixel-perfect` |
| Input actions, control schemes, pointer and stick aim, rebinding | `unity-input` |
| Which perspective and movement model the game's constraints imply | `unity-gameplay` |
| Which game event triggers a shake or a hit stop, and how strongly; the impulse itself stays here | `unity-game-feel` |
| The 3D character the camera follows: its controller, view-relative movement | `unity-3d-controller` |
| The probe, situations, journeys and the timeline format · Timeline, Animator, root motion | `unity-play-harness` · `unity-animation` |
| Why a body does not move, or a cast misses the wall | `unity-physics-3d` · `unity-physics-2d` |
| Parallax, sorting layers, draw order · room bounds as level data | `unity-2d-rendering` · `unity-2d-level` |
| Post-processing, renderer features, the 2D renderer | `unity-render-urp` |
| Uneven frame time, GC spikes · adding and pinning packages, asmdef layout | `unity-profiling` · `unity-new-project` |
| Running tests headless, reading a windowed capture | `unity-debug` |
