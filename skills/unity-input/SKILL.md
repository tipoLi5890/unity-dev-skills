---
name: unity-input
description: >-
  Input System controls: gamepad, touch joystick, mouse aim, rebinding; a jump
  missed or doubled.
---

# unity-input — gameplay reads one struct, never a device

> **A press happens on the render clock; gameplay runs on the physics clock.** The Input System
> updates once per rendered frame, so `WasPressedThisFrame()` polled in `FixedUpdate` is true for
> zero fixed steps on a fast frame and for several on a slow one. The same line of code loses the
> jump on a 144 Hz monitor and double-fires it on a phone that dropped to 20 fps.

## Symptom → where to look

| The report | Go to |
|---|---|
| "the jump doesn't always register", "it jumps twice" | §1, `reference/reading-input.md` |
| "Input.GetKey throws", Active Input Handling | §0, `reference/legacy-migration.md` |
| "add gamepad support", schemes, the actions asset | §1, `reference/action-asset.md` |
| "add a virtual joystick", touch and swipes | `reference/touch-and-on-screen.md` |
| "aim at the mouse", click-to-move | `reference/pointer-and-aim.md` |
| "let players rebind keys", button prompts | `reference/rebinding-and-devices.md` |
| Grid steps with key repeat; a press graded in milliseconds | §2 |
| A scripted source for journey tests | §1 step 5, `templates/InputJourneyTest.cs` |

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
   `RunInputSource.Resolve(gameObject, ref _input)`, then `_input.Peek()` for levels (move, aim,
   held) and `if (_grounded && _input.TryUse(RunButton.Launch)) Launch();` for a press — spent
   once, buffered 0.12 s; variable height reads `launchHeld`. The full method:
   `reference/reading-input.md`.

5. **Prove it** with `templates/InputJourneyTest.cs`: ten taps at four fixed steps per frame and
   at one step per six frames, asserting `launches == presses` and never more.

`Peek` clears nothing. `TryUse` is true once per press and only while the press is younger than
`bufferSeconds`, so *condition first, then `TryUse`* is the whole input buffer: a launch pressed
0.05 s before landing fires on landing; one pressed 0.3 s before does not.
`Consume` returns the snapshot and spends every press in it, for a consumer that acts now or never.

## 2. Pick the branch

The funnel is the same in every branch; what changes is which bindings exist and how `aim` and
`move` are produced.

- **Keyboard and gamepad** — the template as shipped; both live, `ActiveScheme` says which →
  `reference/action-asset.md`.
- **Touch** — an on-screen stick **is** a gamepad; taps and swipes are a gesture layer →
  `reference/touch-and-on-screen.md`.
- **Pointer aim · click-to-move** — `Aim` is PassThrough over stick and pointer; a world click is
  a destination, not a UI click → `reference/pointer-and-aim.md`.
- **A timing press graded in milliseconds** — device timestamps, windows no narrower than one
  quantum → `reference/timing-press.md`.
- **Grid step with key repeat** — one step at once, 0.25 s, then every 0.10 s via `StepRepeater`
  → `reference/reading-input.md`.

Each branch in full: `reference/branches.md`.

## Load what the situation needs

| The situation | Read |
|---|---|
| Maps, control schemes, composites; generated C# class vs `PlayerInput` vs `InputActionReference`; building the asset from script | `reference/action-asset.md` |
| "The jump doesn't always register"; "it fires twice"; buffering; why the read sits in `Update`; update modes | `reference/reading-input.md` |
| Virtual joystick, on-screen buttons, taps and swipes, multi-touch, safe area, testing touch in the Editor | `reference/touch-and-on-screen.md` |
| Rebinding UI, saving overrides, "show the right button prompt", scheme switching, two players on one machine | `reference/rebinding-and-devices.md` |
| Aim at the mouse, stick aim and dead zones, pointer to world in 2D and 3D, a click that went through the UI | `reference/pointer-and-aim.md` |
| `Input.GetKey` throws; Active Input Handling; replacing `GetAxis` / `GetButtonDown` | `reference/legacy-migration.md` |
| "Presses read late" or early after a pause; PERFECT narrower than the device resolves; where the ideal press goes when input arrives 90 ms late; one press per player when two sensors fire | `reference/timing-press.md` |
| The clock those timestamps convert onto; the sim thread that consumes them | `unity-gameplay` → `reference/sim-host-and-clock.md` |
| The zero-package keyboard stand-in for the first hour | `unity-game-brief` → `resources/Presentation/RunLegacyInput.cs` |
| Turning a screen point into a hit on a 3D collider | `unity-physics-3d` → `reference/queries.md` |
| Sending an agent to the clicked point | `unity-navigation` → `reference/recipes.md` |
| A button that will not click; focus; gamepad navigation between UI controls | `unity-ui-ugui` |
| Look input that moves a camera; camera-relative movement axes | `unity-camera` |
| Recording a run, readiness, the probe the journey samples | `unity-play-harness` → `reference/journeys.md` |
| The interact press spent on one selected target | `unity-interaction` |
| Pause as a game state; what stops while paused | `unity-scene-flow` → `reference/game-state-and-pause.md` |
| Touch that works in the Editor and not on the phone | `unity-device-testing` |
| Which controls this kind of game needs at all | `unity-gameplay` |

Copy `resources/RunInput.cs`, `resources/RunInputReader.cs`, `resources/ScriptedRunInput.cs` and
`resources/RebindStore.cs` into a Runtime assembly (only the reader and the store need a reference
to `Unity.InputSystem`), `resources/Editor/CreateRunActions.cs` into an Editor one, and
`templates/InputJourneyTest.cs` into a PlayMode test assembly.

## Discipline

- **One reader.** A second `Keyboard.current` in a pickup script is a second input system, and
  the one the journey cannot drive.
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
- **Action names are an API**: looked up with `throwIfNotFound: true`, a rename fails at
  `OnEnable` with the name instead of reading as "never pressed".
- **An asset that has shipped keeps its binding ids.** Saved rebinds are keyed by id; regenerating
  the file gives every binding a new one and silently drops every player's overrides.
- **Do not add a dead-zone processor to a stick binding.** The gamepad's stick controls already
  carry one (0.125–0.925 by default); a second one applies it twice and the stick feels numb.
- **Aim needs a bigger threshold than move.** A released stick springs past centre; below 0.35
  the reader reports no aim and gameplay keeps its last facing.
- **Lint the asset, then drive the journey** — the lint proves every device reaches every action,
  the journey that a press arrives once.
- **Test through the funnel, not around it.** A journey that calls `Launch()` directly passes on
  a build where no button reaches it. `ScriptedRunInput` presses what the player presses.
- **A graded press keeps the device's timestamp.** Stamping it when gameplay reads it adds a
  frame of jitter and the whole capture latency to the player's error; a pause between press and
  conversion must not move it (`reference/timing-press.md` §1).
- **The human keeps the feel verdict.** Whether 0.12 s of buffer feels generous or sloppy, and
  whether the stick has too much slack, is a judgement; the harness only shows the number moved.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Canvas, buttons, focus, `EventSystem`, gamepad navigation between controls · UI Toolkit events | `unity-ui-ugui` · `unity-ui-toolkit` |
| Where a prompt or an on-screen control sits in the frame | `unity-game-ui` → `reference/hud-placement.md` |
| The 2D · 3D controller that consumes `RunInput` | `unity-2d-controller` · `unity-3d-controller` |
| Moving a camera from look input; update order between input, body and camera | `unity-camera` |
| Feeding Animator parameters from the state input produced | `unity-animation` |
| Raycasts, layers, a query that misses | `unity-physics-3d` → `reference/queries.md` |
| Pathfinding to the clicked point | `unity-navigation` |
| Sending input over the network, client prediction | Out of scope — netcode APIs are out of scope for this plugin; topology and authority: `unity-live-services` → `reference/multiplayer.md` |
| Proving a touch layout on a real phone | `unity-device-testing` |
| Adding the package, assembly definitions, the project's pinned Editor | `unity-new-project` |
| Recorders, situations, the probe contract | `unity-play-harness` |
| Which movement model and which controls the game needs | `unity-gameplay` |
