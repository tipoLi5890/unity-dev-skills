# First person — yaw on the body, pitch on the head

> Part of the `unity-3d-controller` skill. What `resources/FirstPersonController.cs` does with
> look and movement, the capsule under a camera, and the hook that times footsteps. The camera
> component on the head — lens, near clip, a Cinemachine rig — is
> `unity-camera` → `reference/follow-3d.md`.

## 1. Two rotations on two objects

```
Runner            CharacterController · CharacterMotor3D · FirstPersonController      yaw only
└─ Head           empty, 1.6 above the feet                                           pitch only
   └─ Camera      or the Cinemachine camera's tracking target
```

| Rotation | Written to | Why there |
|---|---|---|
| Yaw | The body: `transform.Rotate(0, yaw, 0, Space.World)` | Movement is relative to the body, and the capsule, the hitboxes and anything other players see turn with it |
| Pitch | The head's local rotation: `Quaternion.Euler(-pitch, 0, 0)` | A pitched body tilts the capsule's children and sends "forward" into the floor |

Rules that follow from the split:

- **The stick moves along the body's axes** — `transform.forward` and `transform.right` — which
  stay level because the body never pitches. Looking at the floor does not slow a walk.
- **Pitch is a stored number, clamped, then written.** Reading it back from
  `localEulerAngles.x` returns 275 for −85 and the clamp fails at the first look upwards.
- **`maxPitch` is 85, never 90.** Straight up, the camera's forward has no heading and anything
  that derives one from it spins.
- **Yaw is added to the body's current rotation, not assigned from a stored angle.** A turning
  platform's carry and a scripted `SetLook` then compose with the player's look.
- **One owner of the look angles.** Either this controller turns the body and the head, or a
  Cinemachine pan-tilt owns the angles and the body copies its yaw. Both at once is a feedback
  loop and the view spins.

## 2. Look sensitivity is per device

A pointer reports **how far it moved since the last frame**. A stick reports **how hard it is
pushed**. One is an amount, the other a rate, and the controller takes them through different
doors so neither can be scaled wrongly:

| Device | Feed | Scale | `deltaTime` |
|---|---|---|---|
| Mouse, touch drag | `AddLookDelta(counts)` | `degreesPerCount` (0.1) | **No.** The count is already per frame |
| Gamepad stick | `LookRate = stick` (−1..1), every frame | `stickYawSpeed` 180°/s, `stickPitchSpeed` 120°/s | Yes, applied inside the controller |

Multiplying a pointer delta by `deltaTime` makes the view turn slower at high frame rates and
faster in a stutter — the classic "sensitivity changes when the game lags". The journey turns
the body 90° with 900 counts in one frame for that reason: the answer cannot depend on the
frame's length.

`RunInput` carries move, aim and three buttons, and no look. The game's reader therefore feeds
look itself, beside the funnel:

```csharp
// In the object that owns the Input System actions, each Update:
if (lookAction.activeControl != null && lookAction.activeControl.device is Pointer)
    fp.AddLookDelta(lookAction.ReadValue<Vector2>());          // <Mouse>/delta: counts
else
    fp.LookRate = lookAction.ReadValue<Vector2>();             // <Gamepad>/rightStick: a level
```

Bindings, processors and why one action can serve both:
`unity-input` → `reference/pointer-and-aim.md`. With `lookFromAim` on (the default) a stick aim already in
`RunInput.aim` drives the look when `LookRate` is zero — enough for a prototype and for the
journey, which steers through `ScriptedRunInput.SetAim`; it is a direction, so it always turns
at full rate.

- **Invert** is `invertY`; do not negate a binding and a field both.
- **Lock the cursor** with `Cursor.lockState = CursorLockMode.Locked`; pointer delta keeps
  arriving, position does not.
- **Sensitivity options multiply `degreesPerCount` and the stick speeds separately.** A player
  who halves mouse sensitivity has said nothing about the stick.
- **Aim assist, acceleration curves and gyro** change what is fed in, not the two feeds.

## 3. The capsule under a camera

| Number | Value | Because |
|---|---|---|
| Height · radius | 1.8 · 0.4 | The same body as third person: doors and corridors do not change with the view |
| Eye height | 1.6 above the feet | 0.2 under the crown; the controller places the head from `eyeHeight` at `Awake` |
| Near clip plane | 0.05 to 0.1 | The camera sits 0.4 from a wall the capsule touches; a near plane beyond that sees through it |
| Vertical field of view | 60 (about 91° horizontal at 16:9) | Narrower exaggerates speed, wider shrinks the room |
| Slope limit · step offset | 45° · 0.3 | Every step is a camera bump: keep stairs under a ramp collider |

**The step is felt in first person.** A 0.3 step moves the eye 0.3 in one frame. Either cover
stairs with a sloped collider (`unity-3d-level` → `reference/collision-proxies.md`) or smooth
the head: keep the head's world height moving towards its target at 4 units/s and let the
capsule jump.

**The body in its own camera.** Put the runner's mesh on a layer the first-person camera does
not render — `unity-3d-models` → `reference/culling-and-layers.md`.

## 4. Crouch

`SetCrouch(true)` shrinks the capsule towards the feet; `SetCrouch(false)` stands when there is
room.

```
standing   height 1.8   centre 0.9 above the feet   eye 1.6
crouched   height 1.2   centre 0.6 above the feet   eye 1.0     speed × 0.5
```

- **Towards the feet.** Changing `height` alone shrinks the capsule about its centre: the feet
  lift 0.3 off the floor and the runner drops. The controller moves `center` with it so the
  lowest point stays put.
- **Standing is a question.** Before growing, the controller overlaps the space the standing
  capsule would add, against the motor's `ground` mask, ignoring the runner's own colliders. No
  room, no standing — `Crouched` stays true and the request is retried every frame.
- **The head travels, the capsule snaps.** Collision changes at once; the eye moves at
  `crouchHeadSpeed` (4 units/s, 0.15 s for the 0.6 drop).
- **No jump while crouched**, and `crouchSpeedScale` multiplies the top speed.
- Crouch is asked for by the game: `RunInput` has no crouch button. Hold-to-crouch calls
  `SetCrouch(held)` every frame; toggle calls it on a press.

Vent height for the gate room follows: a crouched runner needs 1.2 plus headroom — 1.4 — and a
vent that must keep a standing runner out is lower than 1.8, the standing capsule.

## 5. Footstep cadence

Footsteps in first person are sound and a camera bob with no animation clip to carry an event,
so the controller counts distance:

```csharp
fp.Footstep += () => { stepSource.PlayOneShot(NextStepClip()); bob.Kick(); };
```

`Footstep` is raised each time the feet have covered `strideLength` (1.6 units) **on the
ground**, from the motor's actual planar velocity. So the cadence follows the speed — three a
second at a run, one and a half at a crouch — a runner pushing against a wall is silent, and
nothing fires in the air. `Landed` and `Jumped` are separate events for the heavier sounds.

A character with a visible body takes its footsteps from the clip instead, where the foot is
seen to land — `unity-animation` → `reference/events-and-windows.md`. Using both doubles them.
Which surface the step is on comes from the motor: `motor.Ground` is the collider under the
feet; read a tag or a component from it.

## 6. Checks

| Check | Expect |
|---|---|
| `FirstPerson_YawTurnsTheBody_PitchClampsOnTheHead` | 900 counts → 90° of yaw; stick held up 1.5 s → pitch 85.00; the body's up is world up; stick up then moves along the body's forward with under 0.05 of drift |
| The same with `CONTROLLER3D_JOURNEY_BREAK=pitch` | Red: a 170° limit lets the head go over the top |
| Turn rate with the mouse at 30 and at 144 frames per second | The same degrees per centimetre of mouse travel |
| Select the runner in play mode while looking up | Rotation X and Z are 0 on the runner; only the head has X |
| Crouch under a 1.4 ceiling and release | Stays crouched until clear |
