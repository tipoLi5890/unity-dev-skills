# Pointer and aim

> Part of the `unity-input` skill. How a mouse position, a finger and a right stick all become
> the same two fields — `RunInput.aim` (a unit direction on the play plane) and `aimPoint` (the
> world point under a pointer) — and how a click on the world is told apart from a click on the UI.

## One action, two kinds of control

`Aim` is bound to `<Gamepad>/rightStick` and `<Mouse>/position`. One is a direction in −1..1,
the other a position in pixels. Two decisions in the asset and the reader make that workable:

- **`Aim` is a PassThrough action.** A Value action resolves several actuated controls by
  magnitude, and a pointer position of (960, 540) beats a fully deflected stick every time: the
  stick would never aim while a mouse is connected. PassThrough reports every change of every
  bound control and leaves the choosing to the reader.
- **The reader chooses by device, in the callback.** `ctx.control.device is Pointer` → store the
  screen position and switch to pointer aim. Anything else is a stick → store the vector, and
  switch to stick aim only once it is past the threshold.

So whichever was used last wins, a mouse lying still does not override a stick in use, and a
stick at rest does not override the mouse.

Gameplay reads the result and does not care which it was:

```csharp
RunInput i = _input.Peek();
if (i.aim != Vector2.zero) _facing = i.aim;          // zero means "not aiming": keep the last facing
if (i.hasAimPoint) _reticle.position = i.aimPoint;   // only a pointer has a point
```

## Pointer to world

A screen position becomes a world point by intersecting the camera's ray with **the play
plane**. `RunAim.PointOnPlane` in `resources/RunInput.cs` is that one operation, and it is the
same code for both projections:

```csharp
Ray ray = camera.ScreenPointToRay(new Vector3(screen.x, screen.y, 0f));
var plane = new Plane(normal, normal * planeOffset);   // XY: normal = forward · XZ: normal = up
if (plane.Raycast(ray, out float enter)) world = ray.GetPoint(enter);
```

| View | `aimPlane` | `planeOffset` | Note |
|---|---|---|---|
| 2D, orthographic (side run, depot top-down) | `XY` | The z of the gameplay layer, usually 0 | The ray is parallel to z, so the hit is the pointer's x and y at that depth |
| 3D, perspective, ground aim (gate room from above, lane run) | `XZ` | **The height of whatever is aimed**, not the floor | See the parallax rule below |
| 3D, orthographic or isometric | `XZ` | As above | Same code; only the ray's origin differs |

Three mistakes this replaces:

- **`ScreenToWorldPoint` with z = 0 on a perspective camera returns the camera's own
  position**, for every pixel. The z passed in is the distance from the camera, not a world
  coordinate. The symptom is an aim direction that never changes.
- **`ScreenToWorldPoint` on an orthographic camera returns the camera's z**, so a sprite placed
  there sits on the near plane and vanishes. Works for a direction, wrong for a point.
- **Aiming at the floor from a raised muzzle.** With a tilted camera, the floor point under the
  cursor and the point at muzzle height under the cursor are different places; shots pass beside
  what the player pointed at, by more the lower the camera. Put the plane at the muzzle's
  height: `planeOffset = muzzle.position.y`.

`PointOnPlane` returns `false` when the ray is parallel to the plane or the plane is behind the
camera; the reader then reports no aim rather than a point at infinity.

**When the ground is not a plane** — ramps, platforms at several heights — the point comes from
a physics ray against the ground layer instead: `Physics.Raycast(ray, out hit, maxDistance,
groundMask)`. Keep it in the reader's `Update`, feed `hit.point` to `SetAimPoint`, and take the
layer mask, trigger and distance rules from `unity-physics-3d` → `reference/queries.md`. In 2D
the pointer needs no ray at all for a point; `Physics2D.OverlapPoint(world)` answers "what is
under it".

## Stick aim

| Stage | Where | Value |
|---|---|---|
| Radial dead zone | On the gamepad's stick control itself (`stickDeadzone`) | 0.125 inner, 0.925 outer, from `InputSystem.settings` |
| Aim threshold | `RunInputReader.aimStickThreshold` | 0.35 — below it `aim` is zero |
| Direction | `SetAim` normalises | Aim is a direction; how far the stick is pushed means nothing |

- **Do not add a `StickDeadzone` processor to the binding.** The control already has one; a
  second squares the curve and the first third of the stick's travel does nothing.
- **The aim threshold is larger than the move dead zone on purpose.** A released stick springs
  back past centre; at 0.125 that overshoot registers as a flick to the opposite side and the
  runner turns round on release.
- **Zero means keep facing.** Gameplay holds the last non-zero aim. A twin-stick sentry-dodger
  that snaps to "up" when the stick is released has skipped this.
- **Stick axes are plane axes.** `aim.x` is the plane's right, `aim.y` its up (XY) or forward
  (XZ). With a camera yawed off the world axes — an isometric 45° — rotate once, in gameplay or
  in the reader, by the camera's yaw only:

```csharp
Vector3 world = Quaternion.Euler(0f, _camera.eulerAngles.y, 0f) * new Vector3(i.aim.x, 0f, i.aim.y);
```

  The same rotation applies to `move`. Camera rigs and their update order are `unity-camera`.
- **Turn at a rate, not instantly,** when the body should show weight:
  `Vector3.RotateTowards(current, target, turnRate * Time.fixedDeltaTime, 0f)`. A pointer can
  cross the runner in one frame; a body that follows instantly reads as a glitch.

**Mouse delta is not a stick.** For first-person look, `<Mouse>/delta` is pixels moved since the
last input update — already a per-frame amount, so it is *not* multiplied by `deltaTime`. A
stick is a rate and *is*. One look action over both needs a scale processor on the mouse
binding and the `deltaTime` applied to the stick only; getting it backwards makes mouse look
depend on frame rate. Locking the cursor (`Cursor.lockState`) freezes `position` and leaves
`delta` working.

## A world click versus a UI click

A click on a button in the HUD is also a press of whatever action the left button is bound to.
The UI does not consume input for the action system; both see it. So a pointer press that means
something in the world passes one test first:

```csharp
// In the reader — the only place that knows a pointer exists.
bool PointerOverUi() =>
    EventSystem.current != null && EventSystem.current.IsPointerOverGameObject();

void LatchWorldClick(InputAction action, RunButton button)
{
    if (action.WasPressedThisFrame() && !PointerOverUi()) Press(button);
    SetHeld(button, action.IsPressed());
}
```

- **Ask in `Update`, never in an action callback.** Inside a callback the Input System warns
  that the call "will query UI state from the last frame" — the answer belongs to the previous
  pointer position. Polling in `Update`, as the reader does, is correct.
- **Ask on the press, not the release.** When a touch ends its pointer is removed, and the
  no-argument call can no longer see what the finger was over.
- **It needs `InputSystemUIInputModule` on the EventSystem.** With no EventSystem there is no UI
  to be over and the test is `false`.
- **Only raycast targets count.** A full-screen transparent `Image` left with Raycast Target on
  makes every click "over UI" and the world goes dead — which is also exactly how an on-screen
  swipe zone is built on purpose. Which graphics block, and why a button will not click, is
  `unity-ui-ugui`.
- A physics ray does not see UI and a UI raycast does not see colliders; they are separate
  systems with separate rules — `unity-physics-3d` → `reference/queries.md`.

## Click-to-move

The pointer names a destination instead of a direction. Three changes to the template:

1. Add a binding for the click to an action — `Interact` gets `<Mouse>/leftButton` in
   `Keyboard&Mouse` and `<Touchscreen>/primaryTouch/tap` in `Touch` — and, for touch, bind
   `Aim` to `<Touchscreen>/primaryTouch/position` in `Touch` so the finger has a position.
2. Latch that action through `LatchWorldClick`, so a HUD click moves nobody.
3. Spend it with the point:

```csharp
void FixedUpdate()
{
    RunInput i = _input.Peek();
    if (i.hasAimPoint && _input.TryUse(RunButton.Interact))
        _mover.SetDestination(i.aimPoint);
}
```

Set `bufferSeconds` to 0 on a source used this way: the point is read when the press is
*spent*, and a buffered click would travel with the pointer.

What `SetDestination` does with the point — snapping it onto the walkable surface, refusing a
point with no path, the agent's stopping distance — is `unity-navigation` →
`reference/recipes.md`, which also carries the click read on both input backends. On a cell
grid the point is converted to a cell first and the path is found over cells.

Re-run `scripts/inputactions_lint.py` after step 1: adding a touch binding for one action and
forgetting the other is the failure it exists to catch.

## A cursor for the gamepad

A menu or a point-and-click screen that must work from a pad needs a pointer the stick can
drive. The package's `VirtualMouseInput` component creates a virtual mouse moved by a stick
action, and the UI then treats it as a mouse. It is a UI device: keep it out of the `Run` map.

## Checks

- Aim never changes → `ScreenToWorldPoint` with z = 0 on a perspective camera, or `aimCamera`
  is not the camera that renders the play field.
- Stick cannot aim while a mouse is plugged in → `Aim` is a Value action; make it PassThrough.
- Aim flicks backwards on release → threshold too low, or a second dead-zone processor.
- Shots land beside the cursor → the aim plane is on the floor, not at muzzle height.
- A HUD click also fires in the world → the press is latched without the UI test.
- Every click is "over UI" → a full-screen graphic with Raycast Target on.
