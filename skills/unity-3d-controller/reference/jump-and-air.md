# Jump and air — the numbers, the press, and the frame

> Part of the `unity-3d-controller` skill. How the controllers turn two numbers a player can see
> into a jump, how a press survives arriving early or late, and why a `CharacterController` jump
> written the obvious way changes height with the frame rate. Reach tables, the level check and
> the measuring script belong to `unity-gameplay` → `reference/level-metrics.md`.

## 1. Author height and time, derive the rest

```
gravity        g  = 2·H / T²          H  apex height, units
jump velocity  v0 = 2·H / T           T  time to apex, seconds
```

| Gate-room start | H 1.2 units · T 0.35 s | → g 19.6 units/s² · v0 6.86 units/s |
|---|---|---|

`ThirdPersonController`, `FirstPersonController` and `LaneRunnerController` store `apexHeight`
and `timeToApex` and compute `Gravity` and `JumpVelocity`. Tune H or T and nothing else.

**The project's gravity is not the jump's.** `Physics.gravity` at −9.81 gives a 1.2-unit apex a
time to apex of 0.49 s — 40% longer than designed, and every crate in the room would have to
change with it to fix it. The controllers never read it. Leave it for props.

A third-person camera makes height look larger than it is: 0.5 to 0.7 of the character's height
reads as an athletic jump. Get the table before building a ledge:

```bash
python3 scripts/level_metrics.py --apex 1.2 --time-to-apex 0.35 --run-speed 5 \
    --fall-multiplier 1.5 --coyote 0.1 --integrator exact \
    --body-width 0.8 --body-height 1.8 --step-offset 0.3
```

The script ships with `unity-gameplay`, under its `scripts/`. `--integrator exact` is these
controllers (section 3); the default, `semi-implicit`, is a motor that moves by the velocity at
the end of each step and prints an apex of 1.131 for the same numbers.

## 2. Rise and fall are two gravities

```
rising    vertical > 0     g
falling   vertical < 0     g · fallMultiplier        (1.5 → 29.4)
capped                     vertical >= −maxFallSpeed (20)
```

The multiplier shortens the way down — 0.29 s from the apex against 0.35 s up — without moving
the apex. It shortens every gap, so the reach table takes it as `--fall-multiplier`.

## 3. The frame moves the apex — and how the controllers stop it

A `CharacterController` moves in `Update`, so each step of the jump is `Time.deltaTime` long,
and that varies. The obvious integration is velocity first, then position:

```csharp
vertical -= g * dt;                       // semi-implicit Euler
controller.Move(Vector3.up * vertical * dt);
```

Each step moves by the velocity at its **end**, so the arc is short by `v0 · dt / 2`:

| Frame rate | `dt` | Apex of a 1.2-unit jump |
|---|---|---|
| 30 | 0.0333 | 1.086 |
| 60 | 0.0167 | 1.143 |
| 144 | 0.0069 | 1.176 |

Nine centimetres between a phone and a desktop is a ledge that one of them cannot reach. Two
fixes; the controllers here use the first.

**Move by the mean velocity.** Take the velocity before and after gravity and move by their
average:

```csharp
float before = vertical;
vertical = Mathf.Max(vertical - g * dt, -maxFallSpeed);
float stepVertical = (before + vertical) * 0.5f;          // what Move is given
```

Under constant acceleration that is exact for any `dt`: the apex is `H` at 30 frames per second
and at 240, and the only frame-rate effect left is that the peak falls between two frames
(under `g · dt² / 8`, 0.7 mm at 60). The fall multiplier switches on at the first
frame after the apex, which moves the landing time by less than one frame. So with these
controllers the designed apex is the one to pass to `jump_report.py --apex`, and the reach table
is computed with `--integrator exact`.

**Step the simulation on a fixed accumulator.** When the vertical rules are not constant
acceleration — an apex hang, a glide, wind volumes — or the run must replay step for step, run
the rules at a fixed length and draw between the last two results:

```csharp
float _accumulator;
Vector3 _previous, _current;                  // simulated positions

void Update()
{
    _accumulator += Time.deltaTime;
    while (_accumulator >= Step)              // Step: 1/60, a constant
    {
        _previous = _current;
        Simulate(Step);                       // rules, then controller.Move, as before
        _current = transform.position;
        _accumulator -= Step;
    }
    visual.position = Vector3.Lerp(_previous, _current, _accumulator / Step);
}
```

The capsule now sits at a simulated position and only the model child is drawn between steps,
so the camera follows `visual`. Do not call `CharacterController.Move` from `FixedUpdate` and
stop there: the capsule has no interpolation of its own, and the picture stutters whenever the
frame rate is not the physics rate.

Whichever is used, prove it at the shipping frame rate and one other:

```csharp
Time.captureDeltaTime = 1f / 30f;   // then 1f / 120f — the journey's apex assertion holds at both
```

## 4. The press: coyote time and the buffer

Both forgive a press that is slightly wrong, and both live in different places.

| | What it forgives | Where it lives | Default |
|---|---|---|---|
| Coyote time | A press just **after** leaving the ground | `coyoteTime` on the controller: a jump is allowed while `TimeSinceGrounded <= coyoteTime` | 0.1 s |
| Buffer | A press just **before** landing | `bufferSeconds` on the input source: a press stays pending that long | 0.12 s |

```csharp
// Condition first, then TryUse: a press that cannot be acted on stays pending for the buffer.
if (canJump && _sinceGrounded <= coyoteTime && _input.TryUse(RunButton.Launch))
    _vertical = JumpVelocity;
```

Reversed — `TryUse` first — the press is spent in mid-air and the buffer does nothing. The
latch, why a polled press is lost between frames and steps, and the scripted source a journey
drives it with: `unity-input` → `reference/reading-input.md`.

- **A jump ends coyote time.** The controller sets its timer past the window when it jumps, or
  one press gives two jumps 0.05 s apart.
- **A push off the ground ends it too.** `Push` with an upward velocity is not an edge to jump
  from.
- **Coyote time is a level number.** It lengthens every gap by `runSpeed × coyoteTime` (0.5
  units here). Fix it before ledges are placed.
- **The jump is assigned, never added.** `_vertical = JumpVelocity`. Added to a lift's upward
  carry it is a different jump on every surface; the lift's own velocity arrives separately,
  through the motor's `PlatformLaunch`.

## 5. Variable height

With `variableJump` on, letting go of the button on the way up multiplies the upward velocity by
`jumpCutMultiplier` (0.5), once per jump. The full jump is the held one:

| Press | Apex |
|---|---|
| Held to the top | 1.2 |
| Tapped (released on the first frame) | about 0.3 |

A journey that taps is measuring the short hop. `CONTROLLER3D_JOURNEY_BREAK=tap` is that
mistake on purpose, and it turns the apex test red.

First person leaves the cut out: with no body on screen a shortened jump reads as a failed one.

## 6. Air control

`airAccel` (15 units/s²) against `groundAccel` (33) decides how much of a jump can be changed
after take-off. At 15, a standing jump reaches 5 units/s after 0.33 s — half the air time — and
a full-speed jump cannot be reversed before landing. Reach assumes the run speed is held through
the jump; an `airAccel` of 0 makes a standing jump vertical and every gap a commitment.

Facing in the air follows the same rule as on the ground: it turns towards intent, not towards
velocity, so a runner knocked backwards does not spin to face where it is thrown.

## 7. Ceilings, slopes and the step offset

- Hitting a ceiling zeroes upward velocity (`OnCeiling`). A ceiling lower than `body height +
  apex` (3.0 here) ends the jump early and shortens every gap under it.
- A jump from a slope leaves vertically: the motor stops following the surface on a rising step.
- The step offset is off in the air — `reference/grounding-and-slopes.md`, section 4.

## 8. Measure it

```bash
python3 scripts/jump_report.py "$JOURNEY_OUT/gate-room-jump/timeline.jsonl" \
    --grounded-key grounded --apex 1.2
```

| The report says | Usually |
|---|---|
| Apex low by `v0 · dt / 2` | The velocity-then-position integrator: section 3 |
| Apex about a quarter of the design | The driver tapped; hold the button |
| Apex high | Jump added to an upward velocity; a step offset left on in the air lifting the runner onto a ledge |
| Air time short, apex right | `groundTolerance` longer than it should be: grounded is reported early |
| No arc found | `grounded` is not registered with the probe, or the press never reached the controller — assert the source's `Sent` count moved |
