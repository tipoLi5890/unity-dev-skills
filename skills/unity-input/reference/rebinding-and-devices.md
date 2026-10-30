# Rebinding, devices and prompts

> Part of the `unity-input` skill. `resources/RebindStore.cs` is the code. Nothing here reaches
> gameplay: a rebind changes which control feeds an action, and `RunInput` is unchanged.

## A rebind is an override, not an edit

The asset on disk is never modified at runtime. Each binding has a `path` (shipped) and an
`overridePath` (the player's); `effectivePath` is the override when there is one. What gets
saved is the override layer alone, as a small JSON document keyed by **binding id**.

```csharp
string json = actions.SaveBindingOverridesAsJson();   // only bindings that have an override
actions.LoadBindingOverridesFromJson(json);           // removes existing overrides first
actions.RemoveAllBindingOverrides();                  // "reset to defaults"
```

Three rules follow from that shape:

- **Load into the instance that is enabled.** A generated C# class, a second player's
  `PlayerInput` and a serialised asset field are different copies. Overrides loaded into one are invisible to
  the others.
- **Load before the first frame of play**, at boot, on the persistent object that owns the
  reader — not when the options screen opens.
- **A shipped asset keeps its ids.** Regenerating the `.inputactions` file gives every binding a
  new GUID, and every saved override silently stops matching. Edit the shipped file; do not
  rebuild it.

`RebindStore` wraps the three calls with the two things they do not do:

| Call | Adds |
|---|---|
| `RebindStore.Load(actions)` / `LoadFromPath(actions, path)` | Loading clears existing overrides before parsing, so a corrupt document would drop the player to defaults mid-session. The store keeps the current layer and restores it when the load throws, and returns `false` |
| `RebindStore.SaveToPath(actions, path)` | Writes beside and swaps, so a quit mid-write leaves the old file |
| `RebindStore.Save(actions)` | `PlayerPrefs` under `input.rebinds.v1`, flushed |

`PlayerPrefs` is enough for one profile on one machine. A file under
`Application.persistentDataPath` is the choice when rebinds belong to a save slot or have to
travel with a cloud save. Version the key or the file name: when an action is removed, the old
document still loads — an id with no binding is skipped with a warning in the log — but a
change in what the actions *mean* deserves `v2` and a clean start.

## One interactive rebind

```csharp
int index = RebindStore.IndexInScheme(launch, "Gamepad");        // -1: no binding in that scheme
_label.text = "Press a button…";
_op = RebindStore.Begin(launch, index, ok =>
{
    if (ok && RebindStore.FindConflict(launch, index) is string other)
        _warning.text = "Also bound to " + other;
    _label.text = RebindStore.Label(launch, index);
    RebindStore.Save(actions);
});
```

`Begin` is `PerformInteractiveRebinding` with the traps removed. Each one is a real failure
when it is left out:

| Trap | What happens | What `Begin` does |
|---|---|---|
| The action is enabled | `InvalidOperationException: Cannot rebind action … while it is enabled` | Disables the action, re-enables it when the operation ends |
| The operation is never disposed | It holds unmanaged memory until `Dispose()` | Disposes in both the complete and the cancel path |
| No way out of a Button row | The package adds an Escape cancel only when the action is *not* a Button, so a mis-clicked `Launch` row waits for ever | `WithCancelingThrough("<Keyboard>/escape")` always; pass a gamepad path when the screen is pad-only |
| A stick sweeps | The first control over the threshold wins, often an axis the thumb passed on its way; the package waits 0.05 s for a better match | `OnMatchWaitForAnother(0.1f)` |

Already handled by `PerformInteractiveRebinding` itself, so not repeated: pointer position and
delta are excluded as candidates (the click on "rebind" is followed by mouse motion), and
matching events are suppressed so the new key does not also act on the UI.

What it does not decide for the game:

- **Conflicts.** `FindConflict` names another action in the same map on the same control. Swap
  the two, refuse, or allow — say which in the UI. Silently allowing is how Launch and Interact
  end up on one button.
- **Composites.** `Move` on the keyboard is four bindings. Rebind the *parts*: walk
  `action.bindings`, and for each row with `isPartOfComposite` call `Begin` with that index, in
  turn. The composite row's own index throws `InvalidOperationException`.
- **Scheme filtering.** A gamepad row should not accept a key. `Begin` targets one binding
  index; choose that index with `IndexInScheme(action, scheme)`, and build one row per scheme.
- **The cancel control is itself unbindable.** With Escape as cancel, Escape can never be bound.
  Decide whether that is acceptable for `Pause`.

The rebinding screen itself is UI — rows, focus, a modal "press a button" plate — and is built
with whichever UI system the project uses. The Input System package ships a *Rebinding UI* sample
(Package Manager → Input System → Samples) that is worth reading for the row logic.

Interactive rebinding needs a human and a device. The parts a test can cover are the store
(`Save`, break the JSON, `Load` returns `false` and the bindings are unchanged) and the override
itself (`action.ApplyBindingOverride(index, "<Keyboard>/k")`, then assert
`action.bindings[index].effectivePath`).

## Prompt glyphs: two different questions

"Show the right button" is two lookups, and mixing them is the usual bug.

**1 · Which control is bound?** From the action, after overrides:

```csharp
string text = action.GetBindingDisplayString(index, out string deviceLayout, out string controlPath);
// "A", "Gamepad", "buttonSouth"        ·        "Space", "Keyboard", "space"
```

`controlPath` is the key for a sprite table (`buttonSouth` → the bottom face button);
`text` is the fallback when there is no sprite. For a composite, ask each part.

**2 · Which device is the player holding?** The binding says `<Gamepad>/buttonSouth` for every
pad ever made; whether to draw a letter or a shape symbol, and which letter, is a property of
the *device last used*, not of the binding. Classify the device's layout:

| `InputSystem.IsFirstLayoutBasedOnSecond(device.layout, …)` | Glyph family |
|---|---|
| `"DualShockGamepad"` | Shape symbols on the face buttons |
| `"SwitchProControllerHID"` | Letters, with the confirm button on the east side |
| `"XInputController"`, or any other `Gamepad` | Letters, confirm on the south side — the safe default |
| `Keyboard` / `Mouse` | Key caps and mouse icons |
| A gamepad with the `OnScreen` usage | None — the on-screen control is its own prompt |

### The switching problem

`RunInputReader.ActiveScheme` and its `SchemeChanged` event report `Keyboard&Mouse`, `Gamepad` or
`Touch` from the device behind the last triggered action. Prompt UI subscribes and redraws.
What makes this harder than it sounds:

- **A resting hand moves a mouse.** If pointer motion counts as "the player switched", prompts
  flicker between pad and keyboard for anyone with both plugged in. The reader ignores pointer
  motion and sub-threshold stick noise on `Aim` when deciding; only a real press or a deflection
  switches.
- **Switch on use, not on connect.** `InputSystem.onDeviceChange` says a pad was *added*; it does
  not say anyone is holding it. Use it for the opposite case — `Disconnected` or `Removed` for
  the device in use means pause the run.
- **Redraw on the event, not every frame.** `GetBindingDisplayString` allocates.
- **Text prompts are part of localisation.** "Press {0} to launch" with the glyph inline, never
  a sentence baked per device.

With a `PlayerInput` component the equivalent is `currentControlScheme` and `onControlsChanged`
(or the `OnControlsChanged` message), and the same two caveats apply.

## Local multiplayer, in brief

One reader assumes one player: the map is enabled unmasked and every device drives it. Two
players on one machine need **device pairing**, and that is what `PlayerInput` and
`PlayerInputManager` are for:

1. A player prefab carries `PlayerInput` (the actions asset, default map `Run`,
   `notificationBehavior = InvokeCSharpEvents`) and a `RunInputReader`.
2. `PlayerInputManager` in the scene, `playerPrefab` set, `joinBehavior =
   JoinPlayersWhenButtonIsPressed` — the first press on an unpaired device spawns a player paired
   to it. `onPlayerJoined` hands over the new `PlayerInput`.
3. Each `PlayerInput` owns **its own instance** of the asset — the original for the first
   player, a clone for each one after — masked to its scheme and restricted to its devices. Keep the reader disabled in the prefab; in `onPlayerJoined` set
   `reader.actions = playerInput.actions` and enable it. A reader that enables on its own picks
   up the shared original, and both players drive both runners.
4. Rebinds are per copy: one `RebindStore` key per player index (`input.rebinds.v1.p0`).

- **Two players on one keyboard** is not pairing — there is one device. Add two schemes
  (`KeyboardLeft`, `KeyboardRight`) with their own binding groups, and spawn explicitly:
  `PlayerInput.Instantiate(prefab, controlScheme: "KeyboardLeft", pairWithDevice: Keyboard.current)`.
- **Do not let a joined player auto-switch scheme** onto another player's device:
  `neverAutoSwitchControlSchemes = true` once there is more than one player.
- **`RunInputReader.ActiveScheme` becomes per player**, which is what split-screen prompts need.

Players on different machines are a different problem — the input is sent, predicted and
reconciled. Those netcode APIs are out of scope for this plugin; the topology and authority
decisions behind them are `unity-live-services` → `reference/multiplayer.md`.

## Checks

- Rebind works until restart → `Save` is not called in the finished callback, or `Load` runs on
  a different instance from the one the reader enables.
- Every rebind lost after an update → the asset was regenerated; compare binding ids in version
  control.
- `Cannot rebind action … while it is enabled` → `PerformInteractiveRebinding` called directly.
- A rebind row that cannot be cancelled → a Button action with no `WithCancelingThrough`.
- Prompts flicker → pointer motion is being treated as a device switch.
- Both runners move together → two readers on the shared asset; pass each `playerInput.actions`.
