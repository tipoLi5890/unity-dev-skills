# The gate room — the first runner, built and proven

`SKILL.md` §1 in full: the body and its numbers, the runner, the probe, the journey that proves
it, and the break switches that show the journey can fail.


1. **Decide the body and six numbers** before the room exists: capsule 1.8 high, radius 0.4,
   skin 0.04; slope limit 45°, step offset 0.3; run speed 5; apex 1.2 in 0.35 s. Gravity (19.6)
   and jump velocity (6.86) are derived, never typed in.
2. **Build the runner.** `CharacterController` + `RunInputReader` + `CharacterMotor3D` +
   `ThirdPersonController`, with `view` set to the camera. No `Rigidbody`. Set the motor's
   `ground` mask to the level's layers, without the runner's own. The model and its Animator go
   on a child; an empty `Chest` child sits at the capsule's centre.
3. **Register with the probe**, where the game wires its harness:

```csharp
GameProbe.SetPlayerVelocity(() => chest, () => run.Velocity);   // the centre, not the feet
GameProbe.Register("grounded", () => run.Grounded);             // the motor's, never isGrounded
GameProbe.SetState(() => run.State);                            // Grounded · Rising · Falling
```

4. **Prove it** with `templates/Controller3DJourneyTest.cs`, which builds its own room from box
   colliders:

| Test | Asserts |
|---|---|
| `ThirdPerson_Ramp_IsClimbedGroundedAndHeld` | Every frame on a 30° ramp is grounded; over 2 units climbed in 0.8 s; at rest it slides under 0.02 in 0.5 s |
| `ThirdPerson_LowStep_IsClimbed` · `ThirdPerson_TallStep_IsRefused` | Feet on top of a 0.3 step; stopped at the face of a 0.6 one |
| `ThirdPerson_Jump_ReachesTheConfiguredApex` | A held jump peaks at 1.2 within 0.05, 0.35 s after the press |
| `ThirdPerson_Stick_IsRelativeToTheView` | With the view yawed 90°, stick up runs along +X |
| `FirstPerson_YawTurnsTheBody_PitchClampsOnTheHead` | 900 pointer counts turn the body 90°; pitch stops at 85°; the body never pitches |
| `LaneRunner_Change_LandsOnTheLaneInTheConfiguredTime` | x = ±1.3 within 0.01 after 0.15 s; a change asked for mid-change is kept; one past the edge is refused |
| the on-foot tests | `JourneyAsserts.NeverInside` reports nothing |

5. **Show the gate can fail.** `CONTROLLER3D_JOURNEY_BREAK=slope`, `=step`, `=tallstep`, `=tap`,
   `=pitch` and `=lane` each turn one test red. A journey nobody has seen fail proves nothing.
6. **Measure the jump** with `unity-gameplay` → `scripts/jump_report.py` against the timeline
   the jump test wrote, then build the room to the table `scripts/level_metrics.py
   --integrator exact` prints.
7. **Add the picture.** `AnimatorBridge3D` on the runner; the camera from `unity-camera`.

First person is step 2 with `FirstPersonController` and a `Head` child; the depot is
`TopDownController3D`; the lane run is `LaneRunnerController` alone, with no motor.
