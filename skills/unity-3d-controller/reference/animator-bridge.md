# The Animator bridge — one writer, four parameters

> Part of the `unity-3d-controller` skill. `resources/AnimatorBridge3D.cs` is the only script
> that writes a 3D character's Animator. It copies what the mover already knows into the
> parameters the character's controller asset was built with. The contract behind it — one
> writer per parameter, types, triggers that queue — is
> `unity-animation` → `reference/parameter-contract.md`.

## 1. What it writes

| Parameter | Type | Written as | From |
|---|---|---|---|
| `Grounded` | Bool | Every frame | `IMoveFacts3D.Grounded` — the motor's cast, not `isGrounded` |
| `MoveBlend` | Float, 0..1 | Every frame, damped 0.1 s | `InverseLerp(slowSpeed, fastSpeed, ground speed)` |
| `MoveSpeed` | Float | Every frame, undamped | `ground speed / authoredSpeed`, at least `minPlayback` |
| `Hurt` | Trigger | When the game calls `Hurt()` | The game's hit event |

Those four names are the ones `unity-rigged-character` → `reference/editor-templates.md` builds
into the character's controller: a `Move` state that is a 1D blend on `MoveBlend` when there are
two gait clips, or one clip whose playback rate is `MoveSpeed` when there is one; a `Jump` state
entered when `Grounded` is false; a masked `Hurt` layer. The bridge is the runtime half of that
asset. Rename a field on the bridge only if the asset was built with other names.

**Ground speed is planar.** `new Vector2(v.x, v.z).magnitude` of the mover's actual velocity.
A jump or a lift is not a faster run, and a runner pushing against a wall is not running: its
velocity is zero, so its legs stop.

## 2. The two speed parameters do different jobs

| | `MoveBlend` | `MoveSpeed` |
|---|---|---|
| Chooses | **Which gait**: the weight between the slow and the fast clip | **How fast the clip plays** |
| Range | 0 at `slowSpeed` (2), 1 at `fastSpeed` (5) | 1.0 at `authoredSpeed` (5) |
| Damping | 0.1 s — a gait that changes in one frame pops | None — a rate that lags the ground is what makes feet slide |
| Used when | The controller has a slow and a fast clip | The controller has one move clip, or a clip is stretched across a speed range |

Set the three speeds from the clips, not from the controller:

1. Play the fast clip in place and measure its stride: the distance a planted foot travels
   backwards over one cycle, divided by the cycle's length in seconds. That is `authoredSpeed`
   and `fastSpeed`.
2. The same for the slow clip is `slowSpeed`.
3. If the controller's `runSpeed` is not the fast clip's speed, either change `runSpeed` or
   accept that `MoveSpeed` plays the clip at `runSpeed / authoredSpeed`. Between 0.8 and 1.2
   reads as natural; beyond that the gait is wrong and a different clip is needed.

`minPlayback` at 0 freezes a single-clip `Move` state when the runner stands still. That is
right for the lane run, which never stops, and wrong for the gate room: add an idle clip as the
tree's 0 end instead of raising `minPlayback`, which makes a standing runner jog on the spot.

## 3. Why it is written this way

- **One writer.** No controller, hazard or pickup calls `SetBool` or `SetTrigger`. They change
  game state; the bridge copies it. A second writer is how a character ends up stuck in a state
  nobody set.
- **Every parameter, every frame.** A pooled sentry that is disabled and re-enabled comes back
  with its Animator at defaults; the next `Update` puts every value right.
- **`Update`, after gameplay.** `[DefaultExecutionOrder(100)]` puts the copy after the
  controllers' `Update`, so the frame's own state is the one shown. The Animator evaluates
  after `Update`, so a value written in `LateUpdate` is a frame late. With
  `Animator.updateMode` set to `Fixed`, write from `FixedUpdate` instead.
- **Names resolved once, with their types.** A parameter the controller lacks, or has with
  another type, is one error at `Awake` naming it — not a warning per frame and a character
  frozen in one pose. Clear a name on the bridge to leave it unwritten.
- **An instant is an event.** `Hurt()` is public and takes no arguments so the game's damage
  code, a `UnityEvent` or a test can call it. It is not polled from a flag: a flag set and
  cleared between two frames is never seen.
- **`IMoveFacts3D` is two properties.** `Grounded` and `Velocity`. All four controllers
  implement it; so can an agent wrapper (`Velocity => agent.velocity`, `Grounded => true`). The
  bridge finds it on its own object, or takes it from `mover`.

## 4. Root motion is off

A character moved by `CharacterController.Move`, by `MovePosition` or by an agent must not also
be moved by its clips. The bridge checks `Animator.applyRootMotion` at `Awake`, logs an error
and switches it off (`forceRootMotionOff`). Two things still need doing by hand:

- **Clips that travel.** Root Transform Position (XZ) → Bake Into Pose stores a clip's travel
  in the bones, not as root motion: the model walks away from its capsule and snaps back each
  loop, whatever `applyRootMotion` says. On a clip that travels, leave XZ unbaked — the travel
  is then root motion, and a script-moved character discards it. Baking is safe only on a clip
  authored in place. Check it: play the run with the capsule held still and watch the `Model`
  child — it stays over the capsule, or the clip's travel is in its pose.
- **An `OnAnimatorMove` left in any script on the Animator's object** switches the Animator to
  "handled by script" and nothing moves unless that method moves it.

The exception is a design where the stride sets the speed. Then the mover applies the clip's
delta through the `CharacterController` — still one owner — and `forceRootMotionOff` is off.
Which arrangement, and the mover for it: `unity-animation` → `reference/root-motion.md`.

## 5. Wiring

```
Runner                CharacterController · CharacterMotor3D · ThirdPersonController · AnimatorBridge3D
├─ Model              Animator (the character's controller asset; Apply Root Motion off)
└─ Chest              empty at the capsule's centre: the probe's player transform, the camera's pivot
```

- The Animator goes on the **model child**, never on the root: the root is the mover's.
- The model's feet sit a skin (0.04) below the capsule's lowest point, or the character hovers.
- The bridge's `animator` is found in children when left empty.
- Hit and hurt volumes hang off the rig's bones —
  `unity-rigged-character` → `reference/gameplay-rig.md`.

```csharp
// Where the game applies damage to the runner:
bridge.Hurt();
// Where the harness is wired:
GameProbe.Register("moveBlend", () => bridge.animator.GetFloat("MoveBlend"));
GameProbe.Count("hurts", () => bridge.Hurts);
```

## 6. More parameters

The four are what the built asset has. A controller with more states adds parameters to its own
copy of the bridge, by the same rule — a fact the mover exposes, copied every frame:

| State wanted | Parameter | Source |
|---|---|---|
| Rise and fall poses | `VelY`, float, undamped | `Velocity.y` |
| Strafing legs | `MoveX`, `MoveY`, floats, damped | `transform.InverseTransformDirection(Velocity)`, x and z, over `fastSpeed` |
| Crouch | `Crouched`, bool | `FirstPersonController.Crouched` |
| Lane lean | `Lean`, float, damped 0.05 | `LaneRunnerController`: sideways velocity over `laneWidth / laneChangeTime` |
| Turn in place | `Turn`, float, damped | Signed angle between the body and the wish, over 180 |

Add the parameter to the asset first, then the line to the bridge; the audit that compares the
two is `unity-animation` → `reference/parameter-contract.md`, section 5.

## 7. Symptoms

| Seen | Cause |
|---|---|
| T-pose, or frozen on one frame of the run | `MoveSpeed` is never written (it defaults to 0) — the bridge is missing, or its name is cleared |
| Jump pose flickers on slopes and stairs | `Grounded` fed from `isGrounded`; feed the motor's |
| Feet slide | `authoredSpeed` is not the clip's stride speed; or `MoveSpeed` is damped somewhere |
| Gait snaps between walk and run | `MoveBlend` written undamped, or written by two scripts |
| The model drifts off the capsule and snaps back | Translation left in the clip — section 4 |
| Runs on the spot against a wall | Ground speed taken from the wish, not from `Velocity` |
| Hurt plays twice | Two callers of `Hurt()` for one hit: the hazard and the health script |
