# The contract — one interface, one selected target, and the interactable decides

> Part of the `unity-interaction` skill. `resources/IInteractable.cs`: the interface, the base
> class that owns the guard, and `InteractorBase`, the half of an interactor that is the same in
> every perspective. Detection — who is in reach — is `reference/detection-choice.md`. Worked
> setting: the **gate room** — the runner walks to a switch, the switch opens the gate.

## 1. Two sides that never swap jobs

```
RunInput ──► interactor ───────────────────► interactable ──────────► the world
(struct)     who is in reach                  may this actor use me?   gate opens, parcel counted
             which ONE is selected            what does using me do?   events out: audio, feel, UI
             spends one press on it           refuses on its own
```

| Side | Knows | Never knows |
|---|---|---|
| Interactor — `InteractorBase` and its two subclasses | Range, facing, layers, the selected target, the press, the hold timer | What a switch does, whether a gate is locked, any item id |
| Interactable — anything implementing `IInteractable` | Its own state, its rule for refusing, what changes when it is used | Buttons, cameras, distance, who else is nearby |

A `switch` statement on the target's type inside the player script is the two jobs swapped. The
symptom arrives with the third kind of interactable: the player script grows a branch, and the
second kind of actor — a sentry that opens gates — has to copy all of them.

## 2. The interface

```csharp
public interface IInteractable
{
    bool CanInteract(GameObject actor);   // cheap, no side effects: asked every scan
    void Interact(GameObject actor);      // every press aimed at it, allowed or not
    string Prompt { get; }                // verb or localisation key; empty hides the prompt
    int Priority { get; }                 // higher wins outright; 0 for almost everything
    float HoldSeconds { get; }            // 0 is a tap
    Transform Anchor { get; }             // prompt position and line-of-sight point
}
```

- **The actor is a `GameObject`, not a player class.** A sentry, a thrown pickup and a test can
  all be actors. The interactable asks the actor for what it needs through an interface —
  `actor.GetComponentInParent<IKeyHolder>()` — and gets `null` from actors that have none.
- **`Interact` is called on a refused press too.** The interactor does not filter: it delivers
  the press, and the interactable answers with its effect or with a refusal. That is what lets
  a locked gate rattle, and it is why the guard cannot live in the interactor.
- **`CanInteract` is asked often and must be free.** No allocation, no physics query, no state
  change. It drives the prompt's enabled look as well as the press.
- **`Prompt` is data.** A verb ("Open", "Take") or a key for the string table — `unity-localization`
  → `reference/string-tables.md`. The glyph beside it is not the interactable's business:
  `reference/prompts.md`.

## 3. The base class owns the guard

`InteractableBase` implements the interface once so that every subclass gets the same three
refusals for nothing:

```csharp
public bool CanInteract(GameObject actor)
    => isActiveAndEnabled && Time.time >= _readyAt && Allows(actor);

public void Interact(GameObject actor)
{
    if (!CanInteract(actor) || !OnInteract(actor)) { onRefused?.Invoke(); Refused?.Invoke(actor); return; }
    _readyAt = Time.time + cooldownSeconds;
    Uses++;
    onInteracted?.Invoke();
    Interacted?.Invoke(actor);
}
```

A subclass overrides two methods:

| Override | Returns | Rule |
|---|---|---|
| `Allows(actor)` | May it be used now | Read state only: locked, spent, busy. `GateSwitch` refuses while its gate moves |
| `OnInteract(actor)` | Whether anything happened | Change the state here and nowhere else. `false` turns the press into a refusal — a full bag |

**The guard is inside `Interact`, re-checked on every call.** A caller that asked `CanInteract`
a frame ago, a second interactor, a network replay and a UI button all reach the same check, so
"the gate opened twice" has one place to be wrong. `Uses` is the probe count that shows it:

```csharp
GameProbe.Count("switchUses", () => gateSwitch.Uses);
```

`cooldownSeconds` (0.25) absorbs a double press and a bouncing contact. It is not the rule that
protects a moving gate — that is `Allows` — and a journey that passes only because of the
cooldown is passing by accident; `templates/InteractionJourneyTest.cs` presses 0.3 s apart for
that reason.

## 4. One selected target

`InteractorBase` holds exactly one `Target`, re-chosen on a scan every 0.1 s (`scanInterval`)
and dropped on the next fixed step when it is destroyed, on the next scan when its GameObject is
deactivated. A disabled component stays selected as unavailable — `CanInteract` false, the
prompt dimmed — until something usable outscores it. Everything that shows or uses a target
reads that one property:

| Reader | Reads |
|---|---|
| The prompt | `TargetChanged(previous, current)`, `Target.Prompt`, `TargetAvailable` |
| An outline or highlight on the object | `TargetChanged` — off for `previous`, on for `current` |
| The press | `Target`, on the fixed step that spends the press |
| The probe | `TargetName` — the object's name, or `""` |

A prompt that runs its own overlap to decide what to label is a second selection, and the two
disagree on the frame it matters. How candidates are scored and why the selection does not
flicker: `reference/detection-choice.md` §3.

## 5. The press

```csharp
// InteractorBase.FixedUpdate — condition first, then TryUse.
if (Target != null && input.TryUse(RunButton.Interact)) Press();
```

- **The press is read from `IRunInputSource`, in `FixedUpdate`, with `TryUse`.** Never a device
  and never `Update`: a press latched by the input source is spent once, on the step that has a
  target for it — `unity-input` → `reference/reading-input.md`.
- **Condition first.** With nothing selected the press is left in the source's buffer (0.12 s)
  and ages out. A press made a moment before the runner reaches the switch is honoured on
  arrival; a press made across the room is not.
- **One button, context decides.** Interact, pick up, open and talk are one `RunButton`. A
  second button for a second verb is a second action in the asset, not a second interactor.
- **Other callers use `TryInteract()`.** A hotspot queue, a sentry and an on-screen button
  press the selected target through the same path and get the same refusals. Set `readInput`
  off on an interactor that only ever takes orders.

## 6. Hold and cancel

`HoldSeconds > 0` turns the press into a timer. `HoldProgress` runs 0 → 1 for the prompt's ring
and the effect fires once, at 1.

| Cancels a hold | Why |
|---|---|
| The selection changes or the target disappears | The hold was on that object, not on "whatever is selected" |
| `CanInteract` turns false | Someone else used it first |
| Move input above `holdCancelMove` (0.5) | Walking off is the natural "never mind" |
| A second press | With no held level to read, it is the only explicit stop |
| `Held` returns false, when assigned | Letting go, where the input exposes it |
| `CancelHold()` | A hit, a cutscene, a pause — called by whoever knows |

`RunInput` carries a held level for Launch only, so an unassigned `Held` makes every hold a
**channel**: the press starts it and it completes by itself. To make it a true hold, add an
`interactHeld` level to the game's input struct and assign the delegate once:

```csharp
interactor.Held = () => source.Peek().interactHeld;     // release now cancels
```

Design holds for the things that cannot be undone — a one-shot switch, a parcel that leaves the
level — and keep them short: 0.4 s reads as deliberate, 1 s as a chore. A hold on something
used fifty times a level is friction with no information in it.

## 7. Events out

The state change and its presentation are different subscribers of the same moment:

| Event | Raised | Listeners |
|---|---|---|
| `InteractableBase.onInteracted` / `Interacted` | After the state changed | The object's own sound and effect — `unity-game-feel` → `reference/feedback-stack.md` |
| `InteractableBase.onRefused` / `Refused` | A press it did not allow | The locked buzz, a shake on the prompt |
| `InteractorBase.Interacted` / `Refused` | The actor's side of the same | The runner's reach animation, controller rumble |
| `InteractorBase.TargetChanged` | The selection changed | The prompt, the outline |
| `InteractorBase.HoldStarted` / `HoldCancelled` | A hold began or was abandoned | The ring, a looping sound that must stop |

- **Nothing subscribed to an event changes game state.** If removing every listener changes
  what the level does, a rule is hiding in the presentation.
- **The animation follows the fact.** The gate is `Opening` from the step the press lands; the
  runner's reach clip is started by the event and catches up. A gate that opens from an
  animation event opens late, and not at all when the clip is interrupted — `unity-animation` →
  `reference/events-and-windows.md`.
- **Sounds are fired from events, not from polling `State`** — `unity-game-feel` →
  `reference/sfx-events.md`.

## 8. What the interface is not for

| Need | Why not here | Go to |
|---|---|---|
| Damage, hits, a breakable crate | A hit has an amount, a source and a direction, and nobody pressed anything | `unity-combat` → `reference/damage-contract.md` |
| A sentry noticing the runner | Perception has memory and a cone of its own | `unity-game-ai` → `reference/perception.md` |
| A menu button | UI has focus and navigation, not reach | `unity-game-ui` |
| Stepping onto a cell with something on it | The board resolves arrival, with no press | `unity-2d-grid` → `reference/occupancy-and-turns.md` |

## Checks

- Press twice, 0.3 s apart, at a toggle switch whose gate takes 1 s: `Uses` is 1, the
  interactor's `Refusals` is 1, the gate's state never reads `Closing`.
- Grep the player scripts for `is GateSwitch`, `GetComponent<Pickup>` and `CompareTag(` beside
  an interact press: each hit is a rule that belongs in an interactable.
- Disable every listener on `onInteracted`: the level still completes.
- Destroy the selected target from another script: `TargetName` is `""` on the next fixed step,
  and nothing throws.
- Start a hold and walk away: `HoldProgress` returns to 0 and the effect has not run.
