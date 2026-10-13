# Doors and switches — a switch owns a bool, a gate owns a state machine

> Part of the `unity-interaction` skill. `resources/GateSwitch.cs`: `GateSwitch`, which holds one
> fact and tells its targets, and `GateTarget`, which turns that fact into motion, a collider
> and events. Worked setting: the **gate room** — the runner walks to a switch, the switch
> opens the gate, a sentry watches.

## 1. Two objects, one direction

```
GateSwitch                         GateTarget
  On : bool   ── SetOpen(On) ──►     State : Closed → Opening → Open → Closing → Closed
  targets[]   (by reference)         panel motion · blocker collider · OpenCount · events
```

| Object | Owns | Never does |
|---|---|---|
| `GateSwitch` | `On`, the lock, which targets it drives | Move anything, time anything, touch a collider |
| `GateTarget` | Its state, its travel time, its collider, how many times it opened | Know what asked it, read input, look for a switch |

The arrow has one direction. The gate never searches for its switch, and the switch asks the
gate one question — `Busy` — so that it can refuse while the gate moves. A gate can therefore
have two switches, a timer or a sentry driving it, and a switch can drive a gate, a light and
a lift together.

## 2. By reference, not by name

`targets` is a serialised array of `GateTarget`, assigned in the Inspector.

| Wiring | Fails when |
|---|---|
| `GameObject.Find("Gate")` | The gate is renamed, duplicated, or in a scene that has not loaded |
| A tag, or `FindObjectsByType<GateTarget>()` | The level gets a second gate: both open |
| A string id matched at runtime | A typo; nothing reports it until a player stands at the switch |
| A serialised reference | The object is deleted — and the Inspector shows `Missing` at once |

- **Draw the wiring.** A gizmo line from each switch to its targets in `OnDrawGizmosSelected`
  shows a level's logic at a glance and makes an unassigned switch visible.
- **Across scenes a reference cannot be serialised.** Wire through an asset both scenes hold —
  an event channel `ScriptableObject` — `unity-scene-flow` → `reference/scriptable-objects.md`,
  and for additively loaded rooms `unity-scene-flow` → `reference/additive-scenes.md`.
- **In a prefab,** switch and gate inside one prefab keep their reference; a switch in one
  prefab and a gate in another are wired on the instances in the scene, as overrides.

## 3. Three kinds of switch

| `mode` | `On` becomes | Refuses when | Use for |
|---|---|---|---|
| `OneShot` | `true`, for good | It is already on | Progress: a gate that stays open once earned |
| `Toggle` | The opposite, each use | Any target is `Busy` (`lockWhileMoving`) | A gate the player opens and closes at will |
| `Held` | `true` while a body stands on it | Always — it is a pressure plate, not pressable | A plate the runner, or a pushed pickup, weighs down |

**The toggle is the one that goes wrong.** A second press while the gate is a third of the way
up flips `On` back; the gate reverses, and a player who double-pressed sees a gate that
twitched and stayed shut. `lockWhileMoving` makes the switch refuse until every target has
reached a rest state. The journey proves it and can be made to fail:

```
INTERACTION_JOURNEY_BREAK=reentry   →  Press_OpensTheGateOnce_AndASecondPressWhileItOpensDoesNothing is red:
                                       the gate's state reads Closing, which is not in Closed → Opening → Open
```

**The plate counts bodies, it does not time them.** `OnTriggerEnter` adds the collider to a
list, `OnTriggerExit` removes it, and each fixed step prunes entries that are destroyed or
inactive — a body pooled while standing on a 3D plate sends no exit, and without the prune the
gate stays open for ever. Trigger colliders do not press it, and `pressedBy` names the layers
that do. Counting with an integer instead of a list breaks on a runner with two colliders: two
enters, and after a pooled exit the count never returns to zero.

## 4. The gate is a state machine

| State | Panel | Blocker collider | `Busy` | Leaves by |
|---|---|---|---|---|
| `Closed` | At rest, shut | Enabled | no | `Open()` → `Opening`, `OpenCount` + 1 |
| `Opening` | Moving, `Progress` 0 → 1 over `travelSeconds` (1) | Enabled | yes | Reaching 1 → `Open`; `Close()` → `Closing` |
| `Open` | At rest, `openOffset` (0, 3, 0) away | **Disabled** | no | `Close()` → `Closing`, unless the doorway is occupied |
| `Closing` | Moving, 1 → 0 | Enabled, from the first step | yes | Reaching 0 → `Closed`; `Open()` → `Opening` |

- **Four states, not a bool and a coroutine.** "Is it open" has three wrong answers during the
  second the panel is moving; `State` has none. Register it:
  `GameProbe.SetState(() => gate.State.ToString());`
- **Asking for what it already is does nothing.** `Open()` on an `Open` or `Opening` gate
  returns. `OpenCount` rises only when it leaves `Closed`, so "exactly once" is `OpenCount == 1`.
- **Motion is stepped in `FixedUpdate`** from `Progress`, so the gate takes the same time at any
  frame rate and stops with the game at `timeScale` 0. Give a 3D panel that carries its own
  collider a kinematic `Rigidbody`: a collider moved by its transform with no body is a static
  collider being moved.
- **Events, not polling:** `onOpening`, `onOpened`, `onClosing`, `onClosed` for sound and
  light; `StateChanged` for code. The grind starts on `onOpening` and the thud lands on
  `onOpened` — `unity-game-feel` → `reference/sfx-events.md`.

## 5. The collider changes with the state

The collider follows the **state**, not the picture:

| Choice | Result |
|---|---|
| Blocker disabled when `Opening` starts | The runner walks through a gate that is visibly shut |
| Blocker disabled at `Open`, enabled when `Closing` starts — what `GateTarget` does | Passable only when it looks passable |
| Blocker enabled only at `Closed` | The runner is caught inside a closing gate and pushed out sideways |

- **`keepClear` stops a gate closing on someone.** With layers assigned, `Close()` on an `Open`
  gate checks the doorway — `Physics.CheckBox`, or `Physics2D.OverlapBox` — and waits, closing
  the first step it is clear. The doorway's bounds are read in `Awake`, while the blocker is
  enabled: a disabled collider reports empty bounds.
- **A blocker that moves with the panel** is fine and needs no toggling at all for a gate that
  slides fully out of the way; assign it anyway, so `Blocks` and the collider agree.
- **In 2D the blocker is a `Collider2D`** on the `Gate` layer; if it is part of a composite,
  toggle the composite's source or use a separate collider — `unity-physics-2d` →
  `reference/tilemap-colliders.md`.
- **A journey checks both halves:** sample `blocker.enabled` into the probe and assert it is
  never false outside `Open`, and false once `Open`.

## 6. Locked gates, keys as data

```
requiredKey  "gate-key"     the item id the actor must carry; empty is unlocked
consumeKey   true           spent on the first use
lockedPrompt "Locked"       shown in place of the prompt while the actor lacks it
```

- **The key is an item id, not a `Key` component.** The switch asks the actor for
  `IKeyHolder` and calls `HasKey(requiredKey)`. Colours, shapes and names of keys are rows of
  data; a new key is a new id — `reference/pickups.md` §5.
- **Unlocking is a fact of its own.** `Unlocked` stays true after the key is spent, so a
  toggle gate opened with a key can be closed and opened again.
- **A press without the key is delivered and refused**, which raises `onRefused`: the rattle.
  The prompt already reads "Locked" — `reference/prompts.md` §5.
- **Lock the switch, not the gate.** A gate with its own lock and a switch with another is two
  rules for one door, and a second switch on the same gate needs the lock copied.

## 7. What a gate does to pathfinding

A closed gate that sentries must route around is a change to the map, not something to steer
past:

| Gate | NavMesh set-up |
|---|---|
| Opens once and stays open | A `NavMeshObstacle` with Carve on, disabled on `onOpened` |
| Opens and closes | The same obstacle, enabled from `StateChanged`: on in every state except `Open` |
| Changes which rooms connect for some agents only | A `NavMeshLink` through the doorway, or an area the agent's mask forbids |

```csharp
gate.StateChanged += state => obstacle.enabled = state != GateState.Open;
```

Without a carve, sentries plan a path through the shut gate and jam at it. Why, and what a
carve costs: `unity-navigation` §4. On a board the gate is a wall cell that is added and
removed — `unity-2d-grid` → `reference/occupancy-and-turns.md`. What the sentry does when its
route opens up is `unity-game-ai` → `reference/patrol-and-chase.md`.

## 8. Persistence

| Saved | Restored with |
|---|---|
| `GateSwitch.On`, `GateSwitch.Unlocked`, under an authored id | `gateSwitch.Restore(on, unlocked)` |
| Nothing for the gate | The switch snaps its targets: `Snap(open)` — rest state, no motion, no events |

- **Save the cause, derive the effect.** Saving the gate's `Progress` as well gives two facts
  that can disagree. A game loaded mid-travel resumes at the rest state the switch implies.
- **`Snap` raises no events,** so loading a level with ten open gates plays no ten thuds.
- **`Restore` may run before the gate's `Awake`;** the gate applies the snapped state when it
  wakes and ignores `startOpen`.
- A `Held` plate saves nothing: the bodies standing on it are restored and press it again.
- The file and its ids: `unity-scene-flow` → `reference/save-format.md`.

## Checks

- Press a toggle twice, 0.3 s apart, at a gate that travels for 1 s: one use, one refusal, the
  state never reads `Closing`.
- Walk at an `Opening` gate: the runner is stopped until the state reads `Open`.
- Stand in the doorway with `keepClear` set and toggle the gate shut: it waits, then closes.
- Rename the gate object: the switch still opens it.
- Pool the runner while it stands on a plate: `On` is false within one fixed step.
- Send a sentry to the far side of a shut gate: it takes the long way round, or reports no
  path — it does not walk into the gate.
- Save with the gate open, reload: the gate is open on the first frame and no sound played.
