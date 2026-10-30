---
name: unity-interaction
description: >-
  Press-to-use in 2D and 3D: doors, switches, gates, pickups, use prompts,
  point-and-click hotspots.
---

# unity-interaction — detection is chosen by perspective; the contract is the same everywhere

> **Finding what is in reach is the easy tenth.** The complaints — the prompt that flickers, the
> gate that opens twice, the switch used through a wall, the parcel counted twice — are never
> about the overlap call. They are about selecting **one** target and keeping it, and about who
> owns the change. The fix is the same in every view: the interactor selects and delivers a
> press; the interactable decides what the press means, and refuses on its own.

## Symptom → where to look

| The report | Go to |
|---|---|
| "press E to open the door", locked doors, switches, gates | §1, `reference/doors-and-switches.md` |
| "the prompt flickers between two objects", "I can use the switch through the wall" | `reference/detection-choice.md` |
| "the door opens twice" | `reference/interactable-contract.md` (the double-press guard) |
| "the coin gets collected twice", pickups | `reference/pickups.md` |
| "walk over and then use it", point-and-click hotspots | `reference/point-and-click.md` |
| The use prompt: placement, glyph, hold ring | `reference/prompts.md` |
| Which detection for this camera | §0 |

```
RunInput ──► interactor ──────────────► interactable ───────────► the world
(struct)     who is in reach             may this actor use me?    gate opens, parcel counted
             which ONE is selected       what does using me do?    events out: audio, feel, UI
             spends one press on it      refuses by itself
```

| Half | Knows | Never knows |
|---|---|---|
| Interactor — `resources/Interactor2D.cs`, `resources/Interactor3D.cs` | Reach, facing, layers, the selected target, the press, the hold timer | What a switch does, whether a gate is locked, any item id |
| Interactable — `resources/IInteractable.cs` and what derives from it | Its own state, its rule for refusing, what changes when used | Buttons, cameras, distance, what else is nearby |

One interface, one selected target, one prompt. What varies with the camera is only how the
candidates are found.

---

## 0. Pick the detection

By what the player points with — not by whether the project is 2D or 3D. If the project has not
named its perspective, `unity-gameplay` does that first.

| Perspective | The player points with | Detection | Use |
|---|---|---|---|
| Side view | Standing at it | Trigger collider on the runner + a list | `Interactor2D`, `TriggerList` |
| Top-down | The body and its facing | The same list, or a circle on a tick with a cone | `Interactor2D`, either mode, `Facing` assigned |
| Third person, overhead | The body's forward | Sphere on a 0.1 s tick, 60° cone, one line of sight | `Interactor3D`, `Overlap` |
| First person | The centre of the screen | One ray from the camera, first hit only | `Interactor3D`, `Ray` |
| Cells | The cell in front | A board lookup, no physics | Four lines in the turn handler |
| Pointer hotspots | The cursor | A hit under the pointer, then walk there | A queue of one intent |

A screen-centre ray in third person selects things the runner is nowhere near; an overlap
sphere in first person names the switch beside the one being looked at. Each row, with its
numbers: `reference/detection-choice.md`.

## 1. Start here — the gate room

1. **Layers.** `Interactable` for switches and interact pickups, `World` for walls, `Runner`
   for the runner. The interactor's `interactable` mask holds the first, `blockers` the second,
   and the runner's layer is in neither.
2. **The gate.** `GateTarget` on the gate, `blocker` assigned to its collider: opens 3 units
   in 1 s, and the collider is off only in `Open`.
3. **The switch.** `GateSwitch` beside a collider on `Interactable`, `mode` Toggle, the gate
   dragged into `targets` — a reference, never a name.
4. **The runner.** `Interactor3D` beside its `RunInputSource`: `Overlap`, `range` 2,
   `halfAngle` 60. It spends `RunButton.Interact` in `FixedUpdate`.
5. **Register with the probe**, where the game wires its harness:

```csharp
GameProbe.Register("target", () => interactor.TargetName);     // "" when nothing is selected
GameProbe.Count("interactions", () => interactor.Interactions);
GameProbe.Count("gateOpens", () => gate.OpenCount);
GameProbe.SetState(() => gate.State.ToString());               // Closed · Opening · Open · Closing
```

6. **Prove it** with `templates/InteractionJourneyTest.cs`, which builds its own rooms:

| Test | Asserts |
|---|---|
| `Runner_WalksIntoReach_AndOnlyThenIsTheSwitchSelected` | Nothing selected and a press ignored at 5.8 units; the switch selected by 2, never beyond |
| `Press_OpensTheGateOnce_AndASecondPressWhileItOpensDoesNothing` | `gateOpens` is 1; state only goes Closed → Opening → Open; the second press is a refusal |
| `Switch_BehindTheRunner_IsNotSelected` | In reach but 180° off the facing: no target |
| `Selection_HoldsBetweenTwoEqualSwitches` (2D) | The runner shifts 0.1 units between mirrored switches; the selection never changes |
| `Press_UsesOnlyTheSelectedSwitch_AndNothingOutOfReach` (2D) | One use on the selected switch, none on its neighbour, none after leaving the sensor |

7. **Show the gate can fail.** `INTERACTION_JOURNEY_BREAK=range`, `=reentry`, `=cone` and
   `=flicker` each turn one test red. A journey nobody has seen fail proves nothing.
8. **Add the prompt last**, as a view of `interactor.Target` — `reference/prompts.md`.

The depot is the same loop with `Interactor2D` and a trigger circle on the runner; the sorting
yard needs no interactor at all.

## Load what the situation needs

| The situation | Read |
|---|---|
| The interface; who owns the state change; the guard against a double press; hold and cancel; cooldown; events for audio and feel; another actor using the same switch | `reference/interactable-contract.md` |
| Which detection for which camera; scoring by distance and angle; priority; a prompt that flickers; a switch used through a wall; interactable layers; the cell in front | `reference/detection-choice.md` |
| World-space or screen-space; following the target; the glyph for the device in hand; dimmed when blocked; the hold ring; highlights | `reference/prompts.md` |
| Touch or interact pickups; counted twice; a magnet; back to the pool; an inventory as data; taken for good across a save | `reference/pickups.md` |
| A switch wired by reference; once, toggle or pressure plate; the gate's four states and its collider; locks and keys; sentries routing round a shut gate; saving it | `reference/doors-and-switches.md` |
| Hotspots; walk there, then act; a queue of one; overlapping hotspots; cursor verbs; gamepad and touch | `reference/point-and-click.md` |
| Sphere, ray and line casts; trigger flags; a query that misses | `unity-physics-3d` → `reference/queries.md` |
| Circle and point overlaps, contact filters, the list overloads | `unity-physics-2d` → `reference/queries-2d.md` |
| Which layers exist and which pairs report | `unity-physics-2d` → `reference/layers-and-matrix.md` |
| The input struct, the press latch, `TryUse`, a scripted driver | `unity-input` → `reference/reading-input.md` |
| The pointer as a world point; a click on UI against a click on the world | `unity-input` → `reference/pointer-and-aim.md` |
| Binding display strings and glyph families | `unity-input` → `reference/rebinding-and-devices.md` |
| The cell ahead on rectangular and hexagonal boards | `unity-2d-grid` → `reference/neighbours-and-range.md` |
| Which UI system draws the prompt | `unity-game-ui` |
| Pools for pickups and their effects | `unity-scene-flow` → `reference/pooling.md` |
| The save file that holds "taken" and "on" | `unity-scene-flow` → `reference/save-format.md` |
| Carving a shut gate out of the NavMesh | `unity-navigation` |
| Walking to a hotspot in 2D | `unity-game-ai` → `reference/pathfinding-2d.md` |
| Draw order that decides the hotspot on top | `unity-2d-rendering` → `reference/sort-order.md` |
| Sound and effect stacks fired from the events | `unity-game-feel` → `reference/feedback-stack.md` |
| Journeys, the probe, proving a gate can fail | `unity-play-harness` → `reference/journeys.md` |

Copy `resources/IInteractable.cs` and the files the game needs into a Runtime assembly beside
`RunInput.cs` (`unity-input` → `resources/`), and the journey from `templates/` into a PlayMode
test assembly that also references the harness. The runtime files need no package — both
physics modules are built in; the journey needs `com.unity.test-framework`. Components that read
fields in `Awake` (`GateTarget`) are built inactive from code, configured, then activated.

---

## Discipline

- **The interactor never changes the world.** It selects and delivers. A `switch` on the
  target's type in the player script is the first step to a player that knows every object.
- **The guard lives in the interactable, inside `Interact`.** Re-checked on every call, so a
  second press, a second actor and a replay all meet the same refusal.
- **One selected target, and everything reads it.** The prompt, the highlight and the press
  use `Target`; none of them runs a query of its own.
- **Hysteresis is not optional.** Keep the target to `range × 1.15` and make a challenger win
  by 0.15, or two equal switches swap on every sway.
- **Condition first, then `TryUse`, in `FixedUpdate`.** `Target != null && TryUse(Interact)`
  honours a press made just before arrival; never a device, never `Update`.
- **First hit only on a ray; one line of sight on an overlap.** Skipping the wall is how a
  switch is used through it.
- **Pass the trigger flag on every query.** A switch is often a trigger and a wall never is.
- **A sensor is not a body.** A reach circle on the runner must not collect a touch pickup.
- **The pickup marks itself taken before it tells anyone, and never calls `Destroy`.**
- **A switch owns a bool; a gate owns four states.** The collider follows the state, not the
  picture, and "exactly once" is `OpenCount == 1`.
- **Wire by reference.** A name, a tag or a search opens the wrong gate after the first rename.
- **Keys and items are ids.** The lock asks the actor for an interface, not for a class.
- **Events out carry no rules.** Remove every listener and the level still completes.
- **Save the cause, derive the effect.** The switch's bool is saved; the gate is snapped from it.
- **The pointer never acts at a distance.** A click queues an intent; the runner arrives; then
  the same `Interact` runs.
- **The human keeps the feel verdict.** The journey shows the gate opened once; whether a
  0.4 s hold feels deliberate is a judgement.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Damage, hit and hurt boxes, knock-back, a crate that breaks when struck | `unity-combat` |
| How a cast or an overlap behaves; a trigger callback that never fires | `unity-physics-3d`, `unity-physics-2d` |
| The actions asset, the reader, rebinding, the on-screen interact button | `unity-input` |
| Building the prompt's canvas or UXML; type size; HUD layout | `unity-game-ui`, then `unity-ui-ugui` or `unity-ui-toolkit` |
| The verb in another language | `unity-localization` |
| Moving the runner to the switch | `unity-3d-controller`, `unity-2d-controller` |
| Cell coordinates, occupancy, pushing a pickup one cell | `unity-2d-grid` |
| A sentry that sees, patrols or decides to use a switch | `unity-game-ai` |
| NavMesh obstacles, links and agents | `unity-navigation` |
| Pools, save files, scene loading, pause | `unity-scene-flow` |
| Screen shake, flashes, the sound a gate makes | `unity-game-feel`, `unity-audio` |
| The reach and open animations | `unity-animation` |
| Recorders, situations, the probe contract | `unity-play-harness` |

Dialogue trees, quest logs and shop screens are game systems built on this contract: an
interactable whose `OnInteract` opens them, and nothing here that models them.
