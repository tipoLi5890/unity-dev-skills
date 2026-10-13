# Prompts — one prompt, drawn for the one selected target

> Part of the `unity-interaction` skill. The prompt is a view of `InteractorBase.Target`: where
> to draw it, how it follows, which glyph it shows and when it hides. Which UI system the
> project uses is decided by `unity-game-ui` before any of this is built; the selection itself
> is `reference/detection-choice.md`.

## 1. The prompt reads the interactor and nothing else

```csharp
// PromptView — one per interactor. Drop beside the HUD; assign the interactor.
void OnEnable()  => interactor.TargetChanged += OnTargetChanged;
void OnDisable() => interactor.TargetChanged -= OnTargetChanged;

void OnTargetChanged(IInteractable previous, IInteractable current)
{
    _anchor = current != null ? current.Anchor : null;
    _verb   = current != null ? current.Prompt : "";
    Redraw();                                   // text and glyph: on the event, not every frame
}

void LateUpdate()                               // position, availability, ring: every frame
{
    bool show = _anchor != null && _verb.Length > 0;
    SetVisible(show);
    if (!show) return;
    if (interactor.TargetAvailable != _available)   // locked → unlocked: same target, new text
    {
        _available = interactor.TargetAvailable;
        _verb = interactor.Target.Prompt;
        Redraw();
    }
    SetDimmed(!_available);
    SetRing(interactor.HoldProgress);
    Place(_anchor.position + Vector3.up * lift);
}
```

| Rule | Because |
|---|---|
| One prompt object per interactor, moved to the target | A prompt on every interactable, each deciding whether to show itself, is one selection per object and they disagree |
| Text and glyph change on `TargetChanged`, and when availability flips | Building the string every frame allocates, and the binding lookup allocates more |
| Position in `LateUpdate` | After the runner and the camera have moved — `unity-camera` → `reference/update-order-and-jitter.md` |
| The prompt never runs a physics query | It would be a second detection with a second answer |

## 2. World-space or screen-space

| | World-space | Screen-space, following | Screen-space, fixed slot |
|---|---|---|---|
| It is | A quad or a World Space canvas at the anchor, turned to the camera | A HUD element moved to the anchor's screen position | A HUD element that never moves |
| Size on screen | Shrinks with distance | Constant | Constant |
| Hidden by walls | Yes, unless drawn on top | No | No |
| Use for | Third person and overhead, where reach is short and the object is always near | Top-down and side view; any game where the text must stay legible | First person — the crosshair already says where; the prompt sits under it |
| Cost | A canvas or a renderer in the world | One conversion a frame | None |

Text in the world is sized by the distance it is read from, not by eye: take the height from
`unity-game-ui` → `reference/type-scale.md` for the camera's distance to a target at full reach.
In first person keep the prompt out of the centre of the frame, one line below the crosshair —
`unity-game-ui` → `reference/hud-placement.md`.

## 3. Following the target

**World-space.** Parent nothing; set the pose each `LateUpdate`:

```csharp
prompt.position = anchor.position + Vector3.up * lift;          // lift 0.4 clears a 0.4-unit switch
prompt.rotation = cam.transform.rotation;                       // face the view plane, not the camera point
```

Copying the camera's rotation keeps the text square on screen; `LookAt(cam.position)` skews it
towards the edges of the frame. Do not parent the prompt to the target: a pickup that spins
spins its prompt, and a target returned to its pool takes the prompt with it.

**Screen-space on a Canvas** (Screen Space – Overlay):

```csharp
Vector3 screen = cam.WorldToScreenPoint(anchor.position + Vector3.up * lift);
if (screen.z <= 0f) { SetVisible(false); return; }              // behind the camera
RectTransformUtility.ScreenPointToLocalPointInRectangle(
    canvasRect, screen, null, out Vector2 local);               // null camera: an overlay canvas
promptRect.anchoredPosition = local;
```

Pass the canvas camera in place of `null` for Screen Space – Camera. The prompt's anchors sit at
the canvas centre, or `anchoredPosition` is offset by them — `unity-ui-ugui` →
`reference/canvas-scaler-and-anchors.md`.

**Screen-space in UI Toolkit:**

```csharp
Vector2 panel = RuntimePanelUtils.CameraTransformWorldToPanel(
    promptElement.panel, anchor.position + Vector3.up * lift, cam);
promptElement.style.left = panel.x;                             // position: absolute in USS
promptElement.style.top  = panel.y;
```

Give the element `translate: -50% -100%` in USS so the point is its bottom centre. Binding the
label's text: `unity-ui-toolkit` → `reference/runtime-binding.md`.

**In every variant:**

- `z <= 0` from `WorldToScreenPoint` means the anchor is behind the camera: hide, or the prompt
  appears mirrored on the opposite side of the screen.
- Clamp a following prompt to the safe area with a margin of 5% of the short side, so a target
  at the edge of the view keeps a readable label.
- A pixel-art game snaps the prompt's position to whole pixels of its reference resolution, or
  the text shimmers as the runner walks — `unity-2d-pixel-perfect`.

## 4. The glyph for the active device

The prompt shows two things: the verb from the interactable and the control from the input
system. They come from different places and change at different times.

| Part | Source | Changes when |
|---|---|---|
| Verb — "Open" | `Target.Prompt`, through the string table | The target changes; the language changes |
| Control — the bottom face button, or E | The Interact action's binding, for the device last used | The player touches another device; a rebind is saved |

- The binding's display string, its control path as the key into a sprite table, and
  classifying the pad family: `unity-input` → `reference/rebinding-and-devices.md`, under
  "Prompt glyphs".
- Redraw the glyph on the device-changed and rebind events and on `TargetChanged`. Never per
  frame.
- Compose with a format string from the table — "{0} Open" — with the glyph inline, so word
  order survives translation: `unity-localization` → `reference/string-tables.md`.
- With TextMeshPro the glyph is a sprite tag from a sprite asset (`<sprite name="buttonSouth">`);
  in UI Toolkit it is a sibling element with a background image.
- On touch there is no glyph. The on-screen interact button is the prompt: enable it and set
  its label to the verb — `unity-input` → `reference/touch-and-on-screen.md`.

## 5. Blocked, held, hidden

| State | `Target` | `TargetAvailable` | The prompt |
|---|---|---|---|
| Nothing in reach | null | false | Hidden |
| Usable | set | true | Glyph and verb |
| Refuses: locked, spent, busy | set | false | Dimmed, the interactable's own text ("Locked"), no glyph |
| Holding | set | true | Glyph, verb, ring at `HoldProgress` |
| Empty `Prompt` | set | either | Hidden — the object is usable but unlabelled |

- **A refused target keeps a prompt.** Hiding it tells the player the door is scenery. Showing
  the verb with a glyph tells them a press will work. Dimmed, with the reason, is the state
  between.
- **`GateSwitch` returns `lockedPrompt` while the actor lacks the key**, so the text needs no
  branch in the view.
- **Hide every prompt when the game is not taking input:** a pause, a cutscene, a dialogue.
  Disable the interactor — its `OnDisable` clears the target and raises `TargetChanged` — do not
  hide the view and leave a live selection behind it.
- **Fade over 0.1 s, not instantly, and never animate the position.** A prompt that eases
  towards its target lags the object while the runner moves. Transitions that do not break the
  logic: `unity-game-ui` → `reference/screen-transitions.md`.
- **The ring fills from the event, the effect fires from the interactor.** A ring that reaches
  1 and then calls `Interact` itself is a second press path with no guard.

## 6. A highlight is the same event

An outline, a brighter material or a bobbing arrow on the object is the prompt's sibling:

```csharp
interactor.TargetChanged += (previous, current) =>
{
    SetHighlight(previous, false);
    SetHighlight(current, true);
};
```

Write the highlight through a `MaterialPropertyBlock` or a renderer feature, never through
`renderer.material`, which makes a copy per object and breaks batching — `unity-render-urp`.
In 2D a second sprite renderer one order above the first costs nothing —
`unity-2d-rendering` → `reference/sort-order.md`.

## Checks

- Walk between two switches: exactly one prompt exists in the hierarchy at every moment.
- Turn the camera until the selected target is behind it: the prompt is hidden, not mirrored.
- Unplug the gamepad and press a key: the glyph changes with no target change.
- Stand at a locked gate with no key: the prompt is dimmed and reads "Locked"; pick up the key
  and it changes within one scan (0.1 s).
- Pause the game with a target selected: no prompt is drawn over the pause menu.
- Profile a frame with a prompt showing and the runner still: no allocation from the prompt.
