# Reading input: latch in Update, spend in FixedUpdate

> Part of the `unity-input` skill. This is the mechanism behind "the jump doesn't always register"
> and "it fires twice", and the reason the read lives in one component. `resources/RunInput.cs` is
> the funnel, `resources/RunInputReader.cs` the device side, `templates/InputJourneyTest.cs` the
> proof.

## Two clocks

The Input System processes its event queue once per rendered frame, immediately before `Update`
(`InputSettings.UpdateMode.ProcessEventsInDynamicUpdate`, the default). "This frame" in
`WasPressedThisFrame()` therefore means *since the last input update* — not since the last fixed
step. A press stays "this frame" from one `Update` to the next, and every `FixedUpdate` in between
sees the same answer:

| Frame rate vs fixed rate (50 Hz default) | Fixed steps between two input updates | A `FixedUpdate` poll sees the press |
|---|---|---|
| 144 fps | 0 on roughly two frames in three | **never** — the jump is lost |
| 50 fps, steady | 1 | once — works on the developer's machine |
| 20 fps (a hitch, a slow phone) | 2 or 3 | **two or three times** — a double jump, or a jump and an instant cut |

Nothing about this is intermittent in the random sense. It is a ratio, which is why it reproduces
on one machine and never on another, and why `templates/InputJourneyTest.cs` pins the ratio with
`Time.captureDeltaTime` and `Time.fixedDeltaTime` instead of hoping for a slow frame.

The package describes the default mode as one where querying input state in `FixedUpdate` is an
error in the Editor and in development builds, and returns the dynamic-update state in a release
player. Do not wait for a log line to find it — grep for the poll (see Checks).

## Do not fix it with the update mode

`InputSystem.settings.updateMode` has three values:

| Mode | Input is processed | Use it when |
|---|---|---|
| `ProcessEventsInDynamicUpdate` | before every `Update` | Always, unless one of the two below is a deliberate decision |
| `ProcessEventsInFixedUpdate` | before every `FixedUpdate` | Never as a jump fix: presses quantise to the physics rate, a frame with no fixed step reads no input at all, and anything that polls in `Update` — UI included — is now the one reading on the wrong clock |
| `ProcessEventsManually` | when the game calls `InputSystem.Update()` | A deterministic replay or lockstep loop that owns the whole frame |

Moving gameplay to `Update` is the other non-fix: a character driven by a `Rigidbody` or a kinematic
motor still has to apply its velocity on the physics clock.

## The latch

A press is turned from an event into a small piece of state the moment it is seen:

```
Update        if (action.WasPressedThisFrame()) Press(button)      → pending = true, pressedAt = Time.time
              SetHeld(button, action.IsPressed())                  → the level, for variable height
FixedUpdate   TryUse(button)                                       → pending && age <= window ? (pending = false, true) : false
```

Three properties fall out of that shape, and they are the three assertions of the journey:

- **Never lost.** The press waits in `pending` across any number of frames with no fixed step.
- **Never doubled.** The first `TryUse` clears it; the second fixed step of the same frame gets
  `false`.
- **Never stale.** A press older than the window is dropped the next time anything asks, so a
  launch pressed long before landing does not fire on landing.

Press before held, in that order, in the reader: a press and release inside one frame still
latches the press and leaves the level `false`.

Two presses of one button before either is spent collapse into one. For a launch that is correct.
For a button where every press must count — a fire button on a rapid weapon — spend it in `Update`
instead, or count presses in the reader and drain the count.

## Buffering a press for N seconds

The buffer is not a separate system. It is the latch's window plus one rule about the order of
the test:

```csharp
// Right: the press stays pending while the runner is airborne, for bufferSeconds.
if (_grounded && _input.TryUse(RunButton.Launch)) Launch();

// Wrong: the press is spent in the air and the buffer never gets a chance.
if (_input.TryUse(RunButton.Launch) && _grounded) Launch();
```

| `bufferSeconds` | Feels like |
|---|---|
| 0 | "This fixed step or never" — the window is still one fixed step, so a press is never invisible |
| 0.10–0.15 | The default range for a jump or a launch: forgives pressing a little early |
| 0.20+ | Starts to read as the game acting on its own; reserve it for slow, deliberate actions |

The window is never shorter than `Time.fixedDeltaTime`, whatever the field says — otherwise a
press could age out before any fixed step had the chance to see it.

**The buffer runs on game time (`Time.time`), on purpose.** In `FixedUpdate`, `Time.time` is the
fixed time, so the age is measured on the clock the consumer runs on, and slow motion stretches
the buffer with everything else. A buffer on unscaled time expires between two slow-motion fixed
steps and loses the press again.

The cost of that choice: at `timeScale` 0 nothing ages. A press made while paused — the confirm
that closes the menu — is still pending when time resumes. **Call `ClearPresses()` on resume.**
`RunInputSource.OnDisable` clears as well, so disabling the reader while a menu owns the input
has the same effect.

The mirror image of the buffer is coyote time: the *condition* stays true for a moment after the
runner leaves the ledge (`_timeSinceGrounded < 0.10f`). That is gameplay state, not input, and it
sits on the other side of the `&&`.

## Levels are read, presses are spent

| Field | Kind | Read with |
|---|---|---|
| `move`, `aim`, `aimPoint` | level | `Peek()` — any number of readers, any callback |
| `launchHeld` | level | `Peek()` — variable launch height cuts the rise when it goes false |
| `launchPressed`, `interactPressed`, `pausePressed` | pending press | `TryUse(button)` from the one consumer, or `Consume()` |

`Peek()` returns the pressed flags too, for a HUD that wants to flash a prompt, but looking does
not spend. `Consume()` returns the same snapshot and clears every press in it: right for a
consumer that acts on a press now or not at all, wrong for anything that wants the buffer.

`Pause` is the one press usually spent in `Update`, by whatever owns the pause state — at
`timeScale` 0 there is no `FixedUpdate` to spend it.

## The single funnel

Every source of input derives from `RunInputSource` and writes through the same four calls —
`SetMove`, `SetAim` / `SetAimPoint`, `Press`, `SetHeld`:

| Source | Writes when | File |
|---|---|---|
| The Input System | `Update`, from the action map | `resources/RunInputReader.cs` |
| A journey test | when the test says | `resources/ScriptedRunInput.cs` |
| A replay, an attract mode, a tutorial ghost | from recorded `RunInput` values | derive a third source the same way |

Gameplay keeps its source with `RunInputSource.Resolve(gameObject, ref _input)` at the top of
its fixed step: it returns the enabled source and resolves again when the one it holds has been
disabled. A journey adds `ScriptedRunInput` to the live runner and disables the reader; the
controller picks the script up on its next step and never learns which it got. A controller that
cached `RunInputSource.On(gameObject)` once in `Awake` would go on holding the disabled reader —
the journey would sample a game nobody is playing and every bound would pass. That is what
"drive through the input funnel" means in
`unity-play-harness` → `reference/journeys.md`: the latch and the buffer under test are the ones
the player gets.

What the scripted source skips is the device and the bindings. When the doubt is "does Space
reach Launch", use the package's `InputTestFixture` (assembly `Unity.InputSystem.TestFramework`):
it adds a fake `Keyboard`, `Press(keyboard.spaceKey)` queues a real event, and the action asset
and `RunInputReader` run unmodified. Keep both: the scripted journey for timing, the fixture for
bindings.

## Grid step with key repeat

A cell-stepped mover in the sorting yard wants *steps*, not a level: one step at once when a
direction is pressed, a pause, then a steady repeat while it is held. Three things that look like
the answer and are not:

- The OS key repeat belongs to text entry, differs per machine, and does not exist on a stick.
- A `Hold` interaction fires once, after its duration (0.4 s by default). It is "long press",
  not "repeat".
- `move != Vector2.zero` every fixed step moves a cell every 0.02 s.

`StepRepeater` in `resources/RunInput.cs` is the method: quantise `move` to the dominant axis
above a threshold of 0.5, step immediately on a new direction, then after `initialDelay`
(0.25 s) step every `interval` (0.10 s).

```csharp
readonly StepRepeater _repeat = new StepRepeater();

void FixedUpdate()
{
    RunInput i = _input.Peek();
    if (!_stepping && _repeat.Step(i.move, Time.time, out Vector2Int dir))
        TryStep(dir);                       // the grid decides whether the cell is free
}
```

Four directions, never a diagonal, and the threshold is high so a stick resting near 45° does
not flicker between two axes. Gate it on `!_stepping` when a step takes time to animate; the
repeater keeps its own clock either way, so a blocked step does not restart the initial delay.

## Checks

- `grep -rn 'WasPressedThisFrame\|wasPressedThisFrame' Assets --include='*.cs'` — every hit
  outside the reader is a second door. Inside a `FixedUpdate` it is this bug.
- `grep -rn 'using UnityEngine.InputSystem' Assets --include='*.cs'` — the list should be the
  reader, the rebind store, on-screen UI and Editor code.
- Run the journey in both ratios. It prints `polled=` beside `launches=`: what a `FixedUpdate`
  poll would have counted on the same run — above the tap count in the fast-fixed case, below it
  in the slow one.

## The read from gameplay, in full

The shape SKILL.md §1 step 4 describes — levels from `Peek`, a press spent once with `TryUse`:

```csharp
IRunInputSource _input;

void FixedUpdate()
{
    if (!RunInputSource.Resolve(gameObject, ref _input)) return;   // no enabled source
    RunInput i = _input.Peek();                       // levels: move, aim, held
    _motor.Move(i.move);
    if (_grounded && _input.TryUse(RunButton.Launch)) // a press: spent once, buffered 0.12 s
        Launch();
    if (_rising && !i.launchHeld) CutLaunch();        // variable height reads the level
}
```
