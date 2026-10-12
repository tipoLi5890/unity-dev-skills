# Shake, blends and the Timeline hand-off

> Part of the `unity-camera` skill. Three things that move the camera without moving its rig:
> an impulse added on top, a blend between two rigs, and a Timeline that takes the camera away
> and gives it back. Names are Cinemachine 3.x — `reference/version-and-names.md` translates;
> the impulse classes keep their names in 2.x and only lose the `m_` prefix in 3.x.

## Shake is a source and a listener

| Piece | Where | Job |
|---|---|---|
| `CinemachineImpulseSource` | On the thing that causes it: the hazard, the gate, the runner's landing | Emits a signal on a channel |
| `CinemachineImpulseListener` | An extension on each Cinemachine camera that should react | Turns signals it can hear into a camera offset |
| `CinemachineCollisionImpulseSource` | On a collider | Emits by itself on a collision or trigger |
| `CinemachineBasicMultiChannelPerlin` | A noise component on the camera | Continuous sway. Not a hit reaction — it never ends |

A source without a listener on the live camera does nothing, and nothing says so.

```csharp
// On the hazard. The definition is tuned in the inspector; code only fires it.
[SerializeField] CinemachineImpulseSource impulse;

void OnHit(Vector3 contactNormal, float strength01)
{
    impulse.GenerateImpulseWithVelocity(-contactNormal * strength01);   // direction and force
}
```

`GenerateImpulse()` uses `DefaultVelocity`; `GenerateImpulseWithForce(float)` scales it;
`GenerateImpulseAt(position, velocity)` places it somewhere other than the source.

The definition (`ImpulseDefinition` on the source):

| Field | Value |
|---|---|
| `ImpulseChannel` | A bit mask. One bit per category — impacts 1, ambient 2, UI 4 — so a listener's `ChannelMask` can opt out |
| `ImpulseShape` | `Bump` for a landing, `Recoil` for a shot, `Explosion` for a blast, `Rumble` for something heavy passing |
| `ImpulseDuration` | 0.2 s. See the budget |
| `ImpulseType` | `Uniform`: felt everywhere at once, the right default for a single-screen game. `Dissipating`: fades with distance, set `DissipationDistance`. `Propagating`: also arrives late, like sound |

**A source added from code keeps `ImpulseType = Legacy`**, the compatibility mode; Reset is what
sets `Uniform`, and Reset runs only in the Editor. Assign the type when creating a source at run
time.

The listener:

| Field | Value |
|---|---|
| `ChannelMask` | Which categories this camera hears |
| `Gain` | The camera's sensitivity. Multiply the player's shake setting into this |
| `Use2DDistance` | On for 2D: distance to the source ignores z |
| `UseCameraSpace` | On: the impulse direction is read in camera axes, so "down" is screen down |
| `SignalCombinationMode` | `Additive` sums overlapping signals; `UseLargest` takes the strongest |
| `ReactionSettings` | A secondary noise the impulse excites. `AmplitudeGain` 0 to leave it out |

## A shake budget

Shake is spent, not added. Write the budget down before tuning any single effect:

| Rule | Number |
|---|---|
| Largest displacement, orthographic | 3 % of the view height: 0.3 units at size 5 |
| Largest displacement, perspective | 0.15 units of position or 1.5° of rotation at a 5-unit follow distance |
| Hit reactions | 0.1 to 0.3 s. Longer than 0.4 s stops reading as an impact |
| Overlap | `UseLargest`. Ten pickups in one frame are one bump, not ten |
| Tiers | Three strengths, named: light 0.3, medium 0.6, heavy 1.0 of the budget. Every event picks a tier |
| Player setting | A 0 to 1 shake slider multiplied into every listener's `Gain`. At 0 the game is fully playable |
| Pixel art | Displacements in whole art pixels: at 16 pixels per unit, 1 to 3 pixels is 0.0625 to 0.1875 units |

- **Shake is applied after the confiner.** The listener offsets the finished camera position, so
  a shake at the room's edge shows past the wall by its amplitude. Extend the art that far, or
  accept it; `camInBounds` from `resources/CameraProbe.cs` allows `boundsTolerance` for exactly
  this, and a journey that asserts bounds should either raise it to the shake budget or run with
  the gain at 0.
- **Shake reads scaled time.** During a hit-stop at `timeScale` 0 the shake freezes too.
  `CinemachineImpulseManager.Instance.IgnoreTimeScale = true` keeps it running.
- **A camera test runs with shake off.** Shake is noise by design; with it on, the flip rate of
  `camOffset` measures the shake.
- **The verdict is a person's.** A budget makes shake consistent, and consistent is not the same
  as right. Hand over a windowed capture and ask.

## Blends by priority

The Brain shows the enabled camera with the highest `Priority` and, when that changes, blends.

| Setting | Where | Use |
|---|---|---|
| `DefaultBlend` | On the Brain | Any pair with no rule. Ships as ease in-out over 2 s; set it to 0.4 s for gameplay |
| `CustomBlends` | A `CinemachineBlenderSettings` asset on the Brain | Rules by camera **name**: From, To, and a blend. Renaming a camera object silently drops its rule |
| `CinemachineBlendDefinition.Styles` | In either | `Cut`, `EaseInOut`, `EaseIn`, `EaseOut`, `HardIn`, `HardOut`, `Linear`, `Custom` |
| `BlendHint` | On the incoming camera | How the path between the two is shaped |

| `BlendHint` flag | Effect |
|---|---|
| `SphericalPosition` | The camera arcs round the tracking target. For blends between two orbit positions |
| `CylindricalPosition` | Arcs horizontally, moves linearly in height |
| `ScreenSpaceAimWhenTargetsDiffer` | Blends where the target is on screen rather than through world space |
| `InheritPosition` | The incoming camera starts from the outgoing camera's position |
| `FreezeWhenBlendingOut` | The outgoing camera holds a snapshot instead of continuing to move |

Rules that keep blends from looking like bugs:

- **A straight blend between two cameras on opposite sides of the runner passes through the
  runner.** Use `SphericalPosition`, or cut.
- **The first camera of a scene is a cut**, whatever the default blend says: there is nothing to
  blend from. A scene that opens on a drift is damping catching up with a runner that was placed
  after the camera woke — call `CinemachineCore.ResetCameraState()` once the runner is placed.
- **Changing priority twice in a frame is one blend, to the last winner.** Changing it back
  during a blend reverses from where the blend had got to.
- **Input is ignored during a blend** when `SuppressInputWhileBlending` is on (the default on
  `CinemachineInputAxisController`). A 2 s default blend is therefore 2 s of dead stick.
- **Knowing it happened**: `CinemachineCore.CameraActivatedEvent` passes the outgoing and incoming
  cameras and `IsCut`; `CinemachineCore.BlendFinishedEvent` fires at the end; `brain.IsBlending`
  answers a poll.

```csharp
void OnEnable()  { CinemachineCore.CameraActivatedEvent.AddListener(OnCamera); }
void OnDisable() { CinemachineCore.CameraActivatedEvent.RemoveListener(OnCamera); }

void OnCamera(ICinemachineCamera.ActivationEventParams e)
{
    // A cut is the moment to snap anything that smooths toward the camera: audio listeners,
    // screen-space UI anchored to world points, a hand-rolled parallax.
    if (e.IsCut) parallax.Snap();
}
```

A blend where both cameras track the same runner inherits the two-clocks rule from each: if
either camera jitters alone, the blend jitters. Fix the rigs first.

## The Timeline hand-off, in brief

A `CinemachineTrack` in a Timeline is bound to the `CinemachineBrain`. Each `CinemachineShot`
clip names a Cinemachine camera. While the track plays, it overrides the priority system
entirely; overlapping clips blend with the overlap as the blend time; when it stops, the Brain
returns to whichever camera has the highest priority.

The hand-off is clean when three things are true:

1. **The last shot is the gameplay camera.** End the track on a clip that names the same
   Cinemachine camera gameplay will use, long enough to cover the blend into it. Releasing the
   override then changes nothing on screen.
2. **The runner is where the gameplay camera expects.** A cutscene that moves the runner has
   teleported the camera's target. Call `CinemachineCore.ResetCameraState()` on the frame the
   Timeline stops, or the gameplay camera pans from where it last saw the runner.
3. **The gameplay camera kept updating, or was reset.** A camera in standby updates round-robin
   by default; one with `StandbyUpdate = Never` wakes with stale state and needs the reset.

Shot cameras used only by the Timeline keep `Priority` at 0 and stay enabled; the track, not the
priority, makes them live. `TrackPriority` on the track orders several Cinemachine tracks among
themselves and has nothing to do with camera priority.

Building the Timeline — tracks, signals, binding at run time, skipping — is `unity-animation` →
`reference/timeline.md`.

## Related skills

Timeline authoring and Animator-driven moments: `unity-animation`. The sound that goes with an
impact: `unity-audio`. Capturing a windowed run for a person to judge: `unity-debug` →
`reference/visual-checks.md`.
