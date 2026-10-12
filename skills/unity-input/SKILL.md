---
name: unity-input
description: >-
  Wire player input with the Input System so gameplay reads one struct, never a
  device: an actions asset with keyboard, gamepad and touch schemes, a reader
  that latches presses in Update and hands each to FixedUpdate once, input
  buffering, on-screen sticks, pointer and stick aim, click-to-move, grid steps
  with key repeat, rebinding saved as JSON, a scripted source for journey tests.
  Load for: "the jump doesn't always register", "it jumps twice", "add gamepad
  support", "add a virtual joystick", "aim at the mouse", "let players rebind
  keys", "Input.GetKey throws". Camera look is unity-camera; UI focus and
  navigation are unity-ui-ugui; which controls a genre needs is unity-gameplay.
---

# unity-input — gameplay reads one struct, never a device

> **A press happens on the render clock; gameplay runs on the physics clock.** The Input System
> updates once per rendered frame, so `WasPressedThisFrame()` polled in `FixedUpdate` is true for
> zero fixed steps on a fast frame and for several on a slow one. The same line of code loses the
> jump on a 144 Hz monitor and double-fires it on a phone that dropped to 20 fps.

The cure is structural, not a setting: one component reads the device in `Update`, **latches** each
press with its time, and gameplay **spends** that press from `FixedUpdate` exactly once. Everything
else in this skill hangs off that one funnel.

```
device ──► .inputactions ──► RunInputReader ──► RunInput ──► RunController
           (bindings)        (Update: latch)    (struct)     (FixedUpdate: spend)
                             ScriptedRunInput ──┘  the same funnel, driven by a journey test
```

| Layer | Knows about | Never knows about |
|---|---|---|
| `templates/RunActions.inputactions` | controls, schemes, composites | what a launch does |
| `resources/RunInputReader.cs` | actions, the latch, which scheme was used last | the runner's state |
| `resources/RunInput.cs` | move, aim, launch pressed/held, interact, pause | keys, sticks, fingers |
| the game's `RunController` | `IRunInputSource` | `InputAction`, `Keyboard`, `Gamepad` |

A `using UnityEngine.InputSystem;` in a gameplay file is the smell. It means a second place reads
the device, and the day a test, a replay or a touch layout needs to drive the game there is no
single door to come in through.

---

## 0. Which backend is this project on

Two checks before any code, because the wrong answer fails at runtime, not at compile time:

```bash
grep -n 'activeInputHandler' ProjectSettings/ProjectSettings.asset   # 0 old · 1 Input System · 2 both
grep -n -A1 '"com.unity.inputsystem"' Packages/packages-lock.json    # the resolved version, or nothing
```

- **Package absent, handler 0** — a prototype can stay on the stand-in for its first hour:
  `unity-game-brief` → `resources/Presentation/RunLegacyInput.cs` is the zero-package keyboard
  reader, and it calls the same three commands. This skill is the path once the package is in.
- **Handler 1** — every `UnityEngine.Input` read throws at runtime while compiling clean.
  → `reference/legacy-migration.md`
- **Handler 2** — both work, and a click wired through both fires twice. Treat it as a migration
  state, not a destination.

## 1. Start here

1. **Get an actions asset.** Copy `templates/RunActions.inputactions` into `Assets/Input/`, or
   build it with `resources/Editor/CreateRunActions.cs` (it reports what it will write and waits).
   One `Run` map: `Move`, `Aim`, `Launch`, `Interact`, `Pause`; schemes `Keyboard&Mouse`,
   `Gamepad`, `Touch`.
2. **Lint it** — `python3 scripts/inputactions_lint.py Assets/Input/RunActions.inputactions`
   exits 1 when an action has no binding in some scheme, a composite is missing a part or a
   binding points at an action that no longer exists. Run it after every edit in the asset editor.
3. **Put `RunInputReader` on the runner** with `RunInput.cs` beside it and assign the asset.
4. **Read it from gameplay, in `FixedUpdate`:**

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

5. **Prove it** with `templates/InputJourneyTest.cs`: ten taps at four fixed steps per frame and
   at one step per six frames, asserting `launches == presses` and never more.

`Peek` clears nothing. `TryUse` is true once per press and only while the press is younger than
`bufferSeconds`, so *condition first, then `TryUse`* is the whole input buffer: a launch pressed
0.05 s before landing fires on landing; one pressed 0.3 s before does not.
`Consume` returns the snapshot and spends every press in it, for a consumer that acts now or never.

## 2. Pick the branch

The funnel is the same in every branch; what changes is which bindings exist and how `aim` and
`move` are produced.

| Branch | What is different | Read |
|---|---|---|
| Keyboard and gamepad (lane run, side run, gate room) | Nothing — the template as shipped. Both schemes are live at once; `ActiveScheme` says which was used last | `reference/action-asset.md` |
| Touch and on-screen controls (mobile casual) | An on-screen stick **is** a gamepad to the action system, so `Touch` shares the gamepad bindings; taps and swipes are a separate gesture layer | `reference/touch-and-on-screen.md` |
| Pointer aim (twin-stick depot) | `Aim` is PassThrough over a stick and a pointer position; the reader resolves it to a direction on the play plane | `reference/pointer-and-aim.md` |
| Click-to-move | A world click is not a UI click; the pointer becomes a destination, not a direction | `reference/pointer-and-aim.md` |
| Grid step with key repeat (sorting yard) | A held direction becomes steps: one at once, 0.25 s, then every 0.10 s — `StepRepeater` in `resources/RunInput.cs`, not the OS key repeat and not a Hold interaction | `reference/reading-input.md` |

## Load what the situation needs

| The situation | Read |
|---|---|
| Maps, control schemes, composites; generated C# class vs `PlayerInput` vs `InputActionReference`; building the asset from script | `reference/action-asset.md` |
| "The jump doesn't always register"; "it fires twice"; buffering; why the read sits in `Update`; update modes | `reference/reading-input.md` |
| Virtual joystick, on-screen buttons, taps and swipes, multi-touch, safe area, testing touch in the Editor | `reference/touch-and-on-screen.md` |
| Rebinding UI, saving overrides, "show the right button prompt", scheme switching, two players on one machine | `reference/rebinding-and-devices.md` |
| Aim at the mouse, stick aim and dead zones, pointer to world in 2D and 3D, a click that went through the UI | `reference/pointer-and-aim.md` |
| `Input.GetKey` throws; Active Input Handling; replacing `GetAxis` / `GetButtonDown` | `reference/legacy-migration.md` |
| The zero-package keyboard stand-in for the first hour | `unity-game-brief` → `resources/Presentation/RunLegacyInput.cs` |
| Turning a screen point into a hit on a 3D collider | `unity-physics-3d` → `reference/queries.md` |
| Sending an agent to the clicked point | `unity-navigation` → `reference/recipes.md` |
| A button that will not click; focus; gamepad navigation between UI controls | `unity-ui-ugui` |
| Look input that moves a camera; camera-relative movement axes | `unity-camera` |
| Recording a run, readiness, the probe the journey samples | `unity-play-harness` → `reference/journeys.md` |
| Touch that works in the Editor and not on the phone | `unity-device-testing` |
| Which controls this kind of game needs at all | `unity-gameplay` |

Copy `resources/RunInput.cs`, `resources/RunInputReader.cs`, `resources/ScriptedRunInput.cs` and
`resources/RebindStore.cs` into a Runtime assembly (only the reader and the store need a reference
to `Unity.InputSystem`), `resources/Editor/CreateRunActions.cs` into an Editor one, and
`templates/InputJourneyTest.cs` into a PlayMode test assembly.

---

## Discipline

- **One reader.** The device is read in exactly one component. A second `Keyboard.current` in a
  pickup script is a second input system, and it is the one the journey cannot drive.
- **Read in `Update`, spend in `FixedUpdate`.** Never poll `WasPressedThisFrame()` from a fixed
  step, and do not move the Input System to `ProcessEventsInFixedUpdate` to make it "work" — that
  quantises every press to the physics rate and breaks UI that reads in `Update`.
- **Levels and presses are different things.** `move`, `aim` and `launchHeld` are read; a press is
  spent. Deriving a press from a level (`held && !wasHeld`) in `FixedUpdate` reintroduces the bug.
- **Condition first, then `TryUse`.** `TryUse(Launch) && grounded` spends the press while
  airborne and throws the buffer away.
- **Buffer in game time, clear on resume.** The latch ages on `Time.time`, so a press made at
  `timeScale` 0 never ages: call `ClearPresses()` when a pause or a menu closes, or the confirm
  press that closed it also launches the runner.
- **Action names are an API.** The reader looks them up with `throwIfNotFound: true`, so a rename
  in the asset editor fails at `OnEnable` with the name in the message instead of reading as
  "never pressed".
- **An asset that has shipped keeps its binding ids.** Saved rebinds are keyed by id; regenerating
  the file gives every binding a new one and silently drops every player's overrides.
- **Do not add a dead-zone processor to a stick binding.** The gamepad's stick controls already
  carry one (0.125–0.925 by default); a second one applies it twice and the stick feels numb.
- **Aim needs a bigger threshold than move.** A released stick springs past centre; below 0.35
  the reader reports no aim and gameplay keeps its last facing.
- **Lint the asset, then drive the journey.** The lint proves every device can reach every
  action; the journey proves a press arrives once. Neither proves the other.
- **Test through the funnel, not around it.** A journey that calls `Launch()` directly passes on
  a build where no button reaches it. `ScriptedRunInput` presses what the player presses.
- **The human keeps the feel verdict.** Whether 0.12 s of buffer feels generous or sloppy, and
  whether the stick has too much slack, is a judgement; the harness only shows the number moved.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Canvas, buttons, focus, `EventSystem` set-up, gamepad navigation between UI controls | `unity-ui-ugui` |
| UI Toolkit events and focus | `unity-ui-toolkit` |
| Where a prompt or an on-screen control sits in the frame | `unity-game-ui` → `reference/hud-placement.md` |
| The 2D controller that consumes `RunInput`: motor, grounding, jump, cell step | `unity-2d-controller` |
| The 3D controller that consumes `RunInput`: third and first person, top-down, the lane run | `unity-3d-controller` |
| Moving a camera from look input; update order between input, body and camera | `unity-camera` |
| Feeding Animator parameters from the state input produced | `unity-animation` |
| Raycasts, layers, a query that misses | `unity-physics-3d` → `reference/queries.md` |
| Pathfinding to the clicked point | `unity-navigation` |
| Sending input over the network, client prediction | `unity-multiplayer` |
| Proving a touch layout on a real phone | `unity-device-testing` |
| Adding the package, assembly definitions, the project's pinned Editor | `unity-new-project` |
| Recorders, situations, the probe contract | `unity-play-harness` |
| Which movement model and which controls the game needs | `unity-gameplay` |
