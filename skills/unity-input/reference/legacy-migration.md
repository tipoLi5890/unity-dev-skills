# From `UnityEngine.Input` to the Input System

> Part of the `unity-input` skill. For a project that has `Input.GetKey` in it and needs to stop,
> and for the exception that appears the day the setting changes and the code does not.

## Active Input Handling

One player setting decides which backends exist at runtime:
**Project Settings → Player → Other Settings → Active Input Handling**, stored as
`activeInputHandler` in `ProjectSettings/ProjectSettings.asset`.

| Value | Inspector name | `UnityEngine.Input` | `UnityEngine.InputSystem` | Scripting define |
|---|---|---|---|---|
| 0 | Input Manager (Old) | works | present if the package is, but receives nothing | `ENABLE_LEGACY_INPUT_MANAGER` |
| 1 | Input System Package (New) | **throws on first read** | works | `ENABLE_INPUT_SYSTEM` |
| 2 | Both | works | works | both |

```bash
grep -n 'activeInputHandler' ProjectSettings/ProjectSettings.asset
grep -n -A1 '"com.unity.inputsystem"' Packages/packages-lock.json
```

- **Changing the value needs an Editor restart** to take effect; installing the package offers
  to change it and restarts for you. A value edited in the YAML with the Editor closed is picked
  up at the next open.
- **The defines are how code stays honest.** `unity-game-brief` →
  `resources/Presentation/RunLegacyInput.cs` wraps its `Input.GetKeyDown` calls in
  `#if ENABLE_LEGACY_INPUT_MANAGER` and logs once in the `#else`, so the stand-in compiles to
  nothing harmful under value 1 instead of throwing.

## The exception

Under value 1, `UnityEngine.Input` still exists and still compiles. The first call to any of its
members — `GetKey`, `GetAxis`, `mousePosition`, `touchCount` — throws an
`InvalidOperationException` whose message names the `UnityEngine.Input` class and the Active
Input Handling setting. Read the exact text from the Console; what matters is how it behaves:

- **It compiles clean.** No warning, no obsolete marker. The failure is at runtime only.
- **It throws on the frame the line first runs**, which for a debug key or a rarely visited
  screen is long after the migration looked finished.
- **It throws every frame in `Update`**, so the method stops at that line each time and
  everything below it in the same `Update` silently never runs. The visible symptom is usually
  something unrelated further down the method.
- **Packages and store assets throw too.** A camera controller or a debug console that reads
  `Input` is as broken as the project's own code.

The census, before changing the setting:

```bash
grep -rnE '\bInput\.(Get|mouse|touch|anyKey|acceleration|gyro|compass|inputString)' \
  Assets Packages --include='*.cs' | grep -v 'InputSystem'
grep -rn 'StandaloneInputModule' Assets --include='*.unity' --include='*.prefab' -l
grep -rnE 'void OnMouse(Down|Up|Enter|Exit|Over|Drag)' Assets --include='*.cs'
```

Every hit is a line that throws, a UI that stops responding, or a callback that stops arriving.

## Replacing the calls

The shape of the replacement matters more than the table. A one-for-one swap of
`Input.GetKeyDown(KeyCode.Space)` for `Keyboard.current.spaceKey.wasPressedThisFrame` keeps
every structural problem: the device is still read in gameplay, still polled wherever the old
line happened to be, still untestable. **Move the read into the reader and the meaning into an
action**; the right-hand column is for debug keys and tools.

| Legacy | Through the funnel (gameplay) | Direct device read (tools, debug) |
|---|---|---|
| `Input.GetAxis("Horizontal")` / `("Vertical")` | `Peek().move` | `Gamepad.current.leftStick.ReadValue()` |
| `Input.GetAxisRaw(…)` | `Peek().move` — action values are already raw | same |
| `Input.GetButtonDown("Jump")` | `TryUse(RunButton.Launch)` | `action.WasPressedThisFrame()` |
| `Input.GetButton("Jump")` | `Peek().launchHeld` | `action.IsPressed()` |
| `Input.GetButtonUp("Jump")` | `!Peek().launchHeld` after it was held | `action.WasReleasedThisFrame()` |
| `Input.GetKeyDown(KeyCode.F1)` | — | `Keyboard.current[Key.F1].wasPressedThisFrame` |
| `Input.GetKey(KeyCode.LeftShift)` | — | `Keyboard.current.leftShiftKey.isPressed` |
| `Input.mousePosition` | `Peek().aimPoint` (world) | `Mouse.current.position.ReadValue()` |
| `Input.GetMouseButtonDown(0)` | `TryUse(RunButton.Interact)` | `Mouse.current.leftButton.wasPressedThisFrame` |
| `Input.GetAxis("Mouse X")` | a look action — `unity-camera` | `Mouse.current.delta.ReadValue().x` |
| `Input.mouseScrollDelta` | an action on `<Mouse>/scroll` | `Mouse.current.scroll.ReadValue()` |
| `Input.touches`, `Input.touchCount` | on-screen controls, or a gesture layer | `Touch.activeTouches` (EnhancedTouch) |
| `Input.anyKeyDown` | — | `Keyboard.current.anyKey.wasPressedThisFrame` |

Things that change meaning, not just name:

- **`Keyboard.current`, `Mouse.current`, `Gamepad.current` are `null` when no such device is
  connected.** `Input.GetKey` returned `false` on a phone; `Keyboard.current.spaceKey` throws a
  `NullReferenceException` there. Every direct read is guarded — another reason gameplay reads
  none.
- **`GetAxis` smoothed; actions do not.** The Input Manager ramped a digital axis toward its
  target (its Gravity and Sensitivity settings), so a key press reached 1 over several frames.
  An action bound to keys jumps from 0 to 1. Movement tuned against `GetAxis` feels sharper and
  twitchier after the swap; if the ramp was part of the feel, put it back in gameplay with
  `Mathf.MoveTowards` on the fixed step, where it is visible and tunable.
- **Axis names are gone.** `"Horizontal"` and `"Jump"` lived in the Input Manager's table; their
  replacement is an action in the asset. Sticks keep a dead zone, but it comes from
  `InputSystem.settings` (0.125–0.925), not from the per-axis Dead value.
- **Mouse delta is in pixels per input update**, not scaled by a Sensitivity setting. Old look
  code that multiplied `GetAxis("Mouse X")` by a factor needs that factor re-tuned.
- **`Input.GetKeyDown` in `FixedUpdate` had the same lost-press bug** as its replacement; the
  migration is the moment to fix it, not to port it — `reference/reading-input.md`.

## The parts that are not code

| Part | Under value 1 | Do |
|---|---|---|
| uGUI `EventSystem` with a Standalone Input Module | The module reads `UnityEngine.Input` and throws every frame; no button responds | Replace it with `InputSystemUIInputModule` (the component's Inspector offers the swap). Canvas and focus questions are `unity-ui-ugui` |
| `OnMouseDown`, `OnMouseEnter`, … on colliders | Delivered under the Input System backend from Unity 6.4; on earlier versions they stop arriving | Replace with a pointer press through the reader and a ray — `reference/pointer-and-aim.md` |
| A scene's click-to-move script | Whichever backend it was written for | `unity-navigation` → `reference/recipes.md` shows the same click on both backends |
| Third-party code reading `Input` | Throws | Value 2 until it is replaced or patched |
| Device builds | The setting is baked into the player | Rebuild after changing it; an old build keeps the old backend |

## Migration order

1. **Census.** Run the three greps above; the hit count is the size of the job.
2. **Add the package and set the handler to Both (2).** Nothing breaks: old reads keep working.
   Package and assembly-definition references are `unity-new-project`.
3. **Add the asset and the reader** (SKILL.md §1) beside the old code, and lint the asset.
4. **Move gameplay reads to the funnel**, one system at a time. While both paths are live a
   single press can act twice — once through the old poll, once through the latch — so remove
   the old line in the same change that adds the new one.
5. **Swap the UI input module** in every scene and prefab the second grep listed.
6. **Guard what is left** — debug keys and tools — with a null check on the device.
7. **Set the handler to 1 and restart the Editor.** Re-run the first grep: it must be empty
   outside `#if ENABLE_LEGACY_INPUT_MANAGER` blocks.
8. **Run every scene once in a play-mode test that fails on a logged exception.** The exception
   only appears on lines that execute, so a scene nobody opened is a scene nobody migrated.
   `templates/InputJourneyTest.cs` covers the funnel; running the suite and trusting its result
   is `unity-debug`.

Staying on Both is a state, not a destination: both backends process every event, and any
click wired through both paths fires twice.

## The first-hour stand-in

A prototype on its first day does not need any of this. `unity-game-brief` →
`resources/Presentation/RunLegacyInput.cs` is a keyboard-only reader on the old backend that
calls the same three commands — launch, lane left, lane right — and it is deliberately the only
file there that knows a device exists. That is the same rule as this skill, with a cheaper
reader. Replace it when any of these becomes true: a gamepad or touch is wanted, a press has to
be read by physics-clocked code, input needs a test, or the project's handler is already 1 (the
stand-in compiles to a log line there and reads nothing).

The swap is one component: remove `RunLegacyInput`, add `RunInputReader`, and have the presenter
keep an `IRunInputSource` through `RunInputSource.Resolve` and spend presses from its fixed step
instead of receiving calls.
