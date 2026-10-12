# Touch and on-screen controls

> Part of the `unity-input` skill. The mobile branch: virtual sticks and buttons, direct touch,
> gestures, and where on the glass any of it may sit. The funnel does not change — a finger ends
> up as the same `RunInput` a gamepad produces.

## An on-screen control is a gamepad

`OnScreenStick` and `OnScreenButton` (namespace `UnityEngine.InputSystem.OnScreen`) do not call
gameplay and do not raise actions. Each one names a control path — `<Gamepad>/leftStick`,
`<Gamepad>/buttonSouth` — and when enabled, the Input System **creates a device of that layout**
and feeds it state as the finger moves. The action asset then sees a gamepad.

Consequences, all of them useful once expected:

- **No touch-specific bindings are needed** for sticks and buttons. The template's gamepad
  bindings carry the groups `Gamepad;Touch` for this reason.
- **All on-screen controls with the same layout share one device.** A stick and three buttons
  that all name `<Gamepad>/…` paths are one virtual pad; a control naming `<Keyboard>/space`
  would create a second, virtual keyboard.
- **The virtual pad is tagged.** The Input System adds the usage `OnScreen` to the device it
  creates, which is how `RunInputReader.ActiveScheme` answers `Touch` rather than `Gamepad` — and
  why a phone with a controller attached shows pad glyphs only when the real pad is used.

### Set-up

| Piece | Requirement |
|---|---|
| Canvas | Screen Space, with a `GraphicRaycaster`; scale with screen size so the stick is the same physical size across phones — `unity-ui-ugui` → `reference/canvas-scaler-and-anchors.md` |
| EventSystem | `InputSystemUIInputModule`, not the legacy standalone module — on-screen controls receive pointer events through the UI |
| The stick | An `Image` (raycast target on) with `OnScreenStick`; `controlPath` `<Gamepad>/leftStick`; `movementRange` 50 by default, in the canvas's units |
| A button | An `Image` with `OnScreenButton`; `controlPath` `<Gamepad>/buttonSouth` |

`OnScreenStick.behaviour` has three values:

| Value | Feels like | Use for |
|---|---|---|
| `RelativePositionWithStaticOrigin` | The stick sits still; the finger's travel from where it landed is the value | The default: a visible stick in a corner |
| `ExactPositionWithStaticOrigin` | The stick snaps under the finger; landing off-centre is already a deflection | Small sticks where a precise centre matters |
| `ExactPositionWithDynamicOrigin` | The stick appears where the thumb lands, within `dynamicOriginRange` (100) of its home | Mobile casual: the thumb never has to find the stick |

### The scheme-switch trap

With a `PlayerInput` component and automatic scheme switching, the finger arrives as
`Touchscreen` and the stick it drives arrives as `Gamepad`. If those belong to two different
schemes, every drag switches scheme, switching cancels the actions in progress, and the stick
snaps back to centre under the thumb. Three defences, in order of preference:

1. **One scheme owns both devices.** The template's `Touch` scheme requires `<Touchscreen>` and
   lists `<Gamepad>` as optional, so the finger and the virtual pad never compete.
2. **Do not auto-switch on a phone.** `playerInput.neverAutoSwitchControlSchemes = true` with
   `defaultControlScheme = "Touch"`.
3. **`OnScreenStick.useIsolatedInputActions = true`** — the stick's own pointer actions stop
   sharing state with the game's, so a switch cannot cancel them.

`RunInputReader` enables the map unmasked and pairs nothing, so a single-player phone game using
it is not exposed to this at all. It becomes relevant the moment `PlayerInput` enters the scene.

## Direct touch: when the finger is the control

Not every phone game wants a stick. Direct bindings exist for the cases where the screen itself
is the control:

| Path | Control | Typical binding |
|---|---|---|
| `<Touchscreen>/primaryTouch/position` | Vector2, pixels | `Aim` — aim at the finger |
| `<Touchscreen>/primaryTouch/tap` | Button | `Launch` — tap anywhere |
| `<Touchscreen>/primaryTouch/press` | Button | Held while the first finger is down |
| `<Touchscreen>/primaryTouch/delta` | Vector2, pixels per update | Drag-to-steer, after scaling |
| `<Touchscreen>/primaryTouch/startPosition` | Vector2 | Where the current touch began |
| `<Pointer>/position`, `<Pointer>/press` | — | Mouse, pen and touch in one binding |

Add them to the `Touch` group and re-run `scripts/inputactions_lint.py`.

**Direct touch and on-screen controls collide.** A tap on an on-screen button is also a
`primaryTouch/tap`; a thumb on the stick also moves `primaryTouch/position`. Choose per action:
either the screen is the control, or a widget on it is. Where both must coexist — tap-anywhere
launch with a pause button in the corner — the tap goes through the world-versus-UI test in
`reference/pointer-and-aim.md`, or the pause button is a plain UI `Button` and not an action.

`delta` and `position` are in pixels. Dividing by `Screen.dpi` (when it is non-zero) or by
`Screen.height` turns a drag into something that means the same on every phone; a raw pixel
threshold tuned on one device is a different gesture on the next.

## Gestures as actions

A swipe is not a control, so it cannot be bound. The move that keeps the funnel intact is to
make the gesture **drive a control**, exactly as the on-screen stick does — then the asset, the
reader and the journey are untouched. Derive from `OnScreenControl`:

```csharp
// LaneSwipe — a full-screen, transparent Image; a horizontal swipe pulses the virtual left stick.
// REQUIRES com.unity.inputsystem. Runtime assembly referencing Unity.InputSystem and UnityEngine.UI.
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.Layouts;
using UnityEngine.InputSystem.OnScreen;

public sealed class LaneSwipe : OnScreenControl, IPointerDownHandler, IPointerUpHandler
{
    [InputControl(layout = "Vector2")]
    [SerializeField] string m_ControlPath = "<Gamepad>/leftStick";
    [Tooltip("Fraction of the screen width a swipe must cover.")]
    public float minTravel = 0.08f;
    public float pulseSeconds = 0.08f;

    Vector2 _down;
    float _releaseAt = -1f;

    protected override string controlPathInternal { get => m_ControlPath; set => m_ControlPath = value; }

    public void OnPointerDown(PointerEventData e) => _down = e.position;

    public void OnPointerUp(PointerEventData e)
    {
        float dx = (e.position.x - _down.x) / Screen.width;
        if (Mathf.Abs(dx) < minTravel) return;
        SendValueToControl(new Vector2(Mathf.Sign(dx), 0f));
        _releaseAt = Time.unscaledTime + pulseSeconds;
    }

    void Update()
    {
        if (_releaseAt < 0f || Time.unscaledTime < _releaseAt) return;
        SendValueToControl(Vector2.zero);
        _releaseAt = -1f;
    }
}
```

The pulse length is the part that matters. `move` is a level, read from `FixedUpdate`; a pulse
of one rendered frame falls between two fixed steps the same way a polled press does. Hold it
longer than a fixed step (0.02 s) and shorter than the step repeat's initial delay (0.25 s):
0.08 s gives one lane change per swipe through `StepRepeater`.

Gestures that need per-finger history — pinch, two-finger rotate, a swipe measured in speed —
read **EnhancedTouch** instead of `PointerEventData`:

```csharp
using UnityEngine.InputSystem.EnhancedTouch;
using Touch = UnityEngine.InputSystem.EnhancedTouch.Touch;

void OnEnable()  { EnhancedTouchSupport.Enable(); }     // balanced: one Disable per Enable
void OnDisable() { EnhancedTouchSupport.Disable(); }

void Update()
{
    foreach (Touch t in Touch.activeTouches)
    {
        // t.finger.index · t.phase (Began, Moved, Stationary, Ended, Canceled)
        // t.screenPosition · t.startScreenPosition · t.delta · t.startTime · t.time · t.isTap
    }
}
```

- `Touch.activeTouches` throws `InvalidOperationException` ("EnhancedTouch API is not enabled")
  until `EnhancedTouchSupport.Enable()` has run. Enable in `OnEnable`, not lazily in `Update`.
- `Touch.onFingerDown`, `onFingerMove` and `onFingerUp` are events with a `Finger` argument;
  they fire during the input update, so record there and act in `Update`.
- Handle `Canceled` as well as `Ended`. A notification shade, a system gesture or an incoming
  call cancels a touch; a gesture recogniser that only releases on `Ended` holds the stick over
  for ever.
- Whatever the recogniser concludes, it reports through a control (as above) or through the
  source's public `Press` — never by calling the runner.

## Safe area and reach

`Screen.safeArea` is the rectangle, in pixels from the bottom-left, that is free of the notch,
the rounded corners and the home indicator. On-screen controls live inside it. Put them under
one panel that follows it:

```csharp
// SafeAreaPanel — on a full-stretch RectTransform directly under the Canvas.
using UnityEngine;

[RequireComponent(typeof(RectTransform))]
public sealed class SafeAreaPanel : MonoBehaviour
{
    Rect _applied;

    void Update()
    {
        Rect safe = Screen.safeArea;
        if (safe == _applied) return;          // changes on rotation and on fold/unfold
        _applied = safe;
        var rt = (RectTransform)transform;
        rt.anchorMin = new Vector2(safe.xMin / Screen.width, safe.yMin / Screen.height);
        rt.anchorMax = new Vector2(safe.xMax / Screen.width, safe.yMax / Screen.height);
        rt.offsetMin = rt.offsetMax = Vector2.zero;
    }
}
```

| Rule | Number |
|---|---|
| Smallest touch target | 9 mm on the glass — about 48 dp on Android, 44 pt on iOS |
| Stick home | Lower-left, its centre at least one stick radius inside the safe area |
| Primary button | Lower-right, under the right thumb; secondary buttons on an arc above it |
| Dead band at the bottom edge | Leave the system gesture strip clear, or a swipe-up leaves the game |
| Landscape, both ways | Read the safe area after rotation: the notch changes side |

What the controls cover is a HUD question — `unity-game-ui` → `reference/hud-placement.md`.

## Testing touch without a phone

| Method | How | Proves |
|---|---|---|
| Touch simulation | Window → Analysis → Input Debugger → Options → **Simulate Touch Input From Mouse or Pen**, or `TouchSimulation.Enable()` from code | The `Touchscreen` paths and EnhancedTouch, one finger |
| Device Simulator | The Game view's Simulator mode | Safe area, notch, resolution; touch from the mouse |
| `InputTestFixture` | `BeginTouch(1, pos)` / `EndTouch(1, pos)` in a test | Bindings and gesture code, deterministic, several fingers |
| `ScriptedRunInput` | `templates/InputJourneyTest.cs` | That the gameplay consuming the result is right, with no device at all |

None of them proves thumb reach, palm rejection, a 120 Hz touch panel or the system gesture
strip. Those need the phone in a hand — `unity-device-testing`.

## Checks

- Stick snaps back under the thumb → the scheme-switch trap; apply defence 1, 2 or 3.
- On-screen button does nothing → no `InputSystemUIInputModule` on the EventSystem, no
  `GraphicRaycaster` on the Canvas, or the `Image` has Raycast Target off.
- Tap launches *and* presses a button → a direct `tap` binding live beside on-screen controls.
- Works in the Editor, dead on the phone → the Editor was being driven by the mouse through a
  `<Pointer>` or `<Mouse>` binding that is not in the `Touch` group; lint the asset.
- Controls under the notch on one phone only → not parented to the safe-area panel.
