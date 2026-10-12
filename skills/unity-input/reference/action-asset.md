# The actions asset: maps, schemes, and three ways to reach it from code

> Part of the `unity-input` skill. `templates/RunActions.inputactions` is the asset,
> `resources/Editor/CreateRunActions.cs` builds the same thing from script, and
> `scripts/inputactions_lint.py` reads either and names the holes.

## What the courier-run asset contains

One map, `Run`. Five actions:

| Action | Type | Control type | Keyboard&Mouse | Gamepad and Touch |
|---|---|---|---|---|
| `Move` | Value | Vector2 | WASD and arrows, two `2DVector` composites | `<Gamepad>/leftStick` |
| `Aim` | PassThrough | Vector2 | `<Mouse>/position` | `<Gamepad>/rightStick` |
| `Launch` | Button | Button | `<Keyboard>/space` | `<Gamepad>/buttonSouth` |
| `Interact` | Button | Button | `<Keyboard>/e` | `<Gamepad>/buttonWest` |
| `Pause` | Button | Button | `<Keyboard>/escape` | `<Gamepad>/start` |

Three control schemes:

| Scheme | Binding group | Devices |
|---|---|---|
| `Keyboard&Mouse` | `Keyboard&Mouse` | `<Keyboard>`, `<Mouse>` |
| `Gamepad` | `Gamepad` | `<Gamepad>` |
| `Touch` | `Touch` | `<Touchscreen>`, `<Gamepad>` optional |

The gamepad bindings carry the groups `Gamepad;Touch`. That is not a shortcut: an on-screen stick
or button synthesises a gamepad device, so on a phone the gamepad bindings *are* the touch
bindings, and listing the gamepad as an optional device of `Touch` keeps the finger and the
virtual pad in one scheme. → `reference/touch-and-on-screen.md`

### Action type decides conflict resolution

| Type | When several bound controls are actuated | Use for |
|---|---|---|
| Value | The one with the greatest magnitude drives the action | `Move` — keys and a stick never fight meaningfully |
| Button | Same, with press and release thresholds | `Launch`, `Interact`, `Pause` |
| PassThrough | No resolution: every change of every control is reported | `Aim` — a pointer position in pixels would out-shout a stick every time under Value |

Value actions also perform an initial state check when enabled (`initialStateCheck: true` in the
JSON), so a stick already held when the map is enabled is read at once; Button and PassThrough
actions wait for a change.

### What lives on a binding

- **Groups** — a `;`-separated list of scheme binding groups. A binding with no group is dropped
  whenever a scheme mask is applied (`PlayerInput` applies one), so in an asset that has schemes,
  every binding belongs to at least one.
- **Composites** — a parent row (`isComposite`, path `2DVector`) followed by part rows
  (`isPartOfComposite`, named `up` / `down` / `left` / `right`). The parts carry the groups; the
  parent carries none. A `2DVector` from four keys normalises diagonals by default, so WASD
  diagonal is magnitude 1, not 1.41.
- **Processors and interactions** — strings such as `ScaleVector2(x=2,y=2)` or `Hold(duration=0.4)`.
  Leave stick bindings without a dead-zone processor: `<Gamepad>/leftStick` and `rightStick`
  already carry `stickDeadzone`, with `InputSystem.settings.defaultDeadzoneMin` 0.125 and
  `defaultDeadzoneMax` 0.925. A second one on the binding applies the curve twice.
- **Ids** — every map, action and binding has a GUID. Saved rebinds are keyed by binding id.

## Lint it

```bash
python3 scripts/inputactions_lint.py Assets/Input/RunActions.inputactions --pretty
```

Exit 0 is clean, 1 is at least one finding, 2 is an unreadable file. The findings are the ones
the asset editor never reports:

| Finding | What the player experiences |
|---|---|
| `action-unbound-in-scheme` | A button that does nothing on one kind of device |
| `composite-incomplete` | WASD where one direction is dead |
| `binding-missing-action` | A binding orphaned by renaming or deleting an action |
| `binding-unknown-group` | A binding in a scheme that was renamed away — dead under `PlayerInput` |
| `duplicate-id` | Two bindings that overwrite each other's rebind |

A deliberate gap is declared, not ignored: `--allow Pause:Touch` when pause on a phone is a UI
button and not an action. `--scheme Gamepad` narrows the coverage check to one scheme.

## Three ways to reach the asset from code

| | Generated C# class | `PlayerInput` component | `InputActionAsset` / `InputActionReference` field |
|---|---|---|---|
| How | Tick **Generate C# Class** on the asset's importer and set **C# Class Name** (below); `new RunControls()` | Add the component, assign the asset | Drag the asset (or one action) onto a serialised field |
| Lookup | Typed members — a rename is a compile error | Strings, or callbacks wired in the Inspector | Strings (`FindAction("Launch", true)`) or a direct reference |
| Who enables | You: `actions.Run.Enable()` | The component, with the default map | You |
| Instances | Each `new` is a private copy of the asset | The assigned asset for the first player, a clone for each further one | The shared asset object |
| Schemes | You set `bindingMask` and `devices` | Automatic: pairing, masking, switching | You, or none — every scheme live |
| Fits | One player, code-first team, renames caught at compile time | **Two or more local players**, or a team that wants Inspector wiring | One player, no codegen step, asset swappable per build |

`resources/RunInputReader.cs` uses the third: an `InputActionAsset` field, the `Run` map enabled
unmasked, actions found by name with `throwIfNotFound: true` so a rename fails at `OnEnable` with
the name in the message. With the field empty it falls back to `InputSystem.actions`, the
project-wide asset.

Whichever is chosen, it stays behind the reader. The differences that bite:

- **A generated class and a serialised asset field are different instances.** Rebinds loaded
  into one do not exist in the other. Load overrides into the instance that is enabled.
- **A generated class collides with its maps two ways.** An asset `Run.inputactions` containing
  a map `Run` is an import error. And each map `X` becomes a nested struct `XActions`, so the
  class generated from `RunActions.inputactions` would contain a `RunActions` struct — compile
  error CS0542. With the template, set **C# Class Name** on the importer (`RunControls`) before
  ticking the box.
- **`PlayerInput` with Send Messages calls `OnLaunch(InputValue)` by name** — on `performed`,
  and on `canceled` only for Value actions. A Button action therefore reports the press and never
  the release, so a held level cannot be built from it. Prefer
  `notificationBehavior = InvokeCSharpEvents` and one subscription inside the reader.
- **`PlayerInput` owns the instance it enables** — the assigned asset for the first player, a
  clone for every player after it. A `RunInputReader` beside it takes `playerInput.actions`,
  never its own asset field, or the second player's reader listens to the first player's copy.
- **`InputActionReference` points into one asset.** It is the right field type for a UI prefab
  that needs exactly one action — a rebind row, an on-screen prompt — and the wrong one for
  gameplay, which should not hold an action at all.

Callbacks (`performed`, `canceled`, `actionTriggered`) run during the input update, before
`Update`. Use them to *record* — which is all the reader's `OnAim` does — and never to move the
runner: the callback fires zero or many times relative to the fixed step, for the reason in
`reference/reading-input.md`.

## Building the asset from script

`resources/Editor/CreateRunActions.cs` is the whole method:

```csharp
var asset = ScriptableObject.CreateInstance<InputActionAsset>();
InputActionMap run = asset.AddActionMap("Run");

InputAction move = run.AddAction("Move", InputActionType.Value, expectedControlLayout: "Vector2");
move.AddCompositeBinding("2DVector")
    .With("up", "<Keyboard>/w", "Keyboard&Mouse")
    .With("down", "<Keyboard>/s", "Keyboard&Mouse")
    .With("left", "<Keyboard>/a", "Keyboard&Mouse")
    .With("right", "<Keyboard>/d", "Keyboard&Mouse");
move.AddBinding("<Gamepad>/leftStick", groups: "Gamepad;Touch");

asset.AddControlScheme("Touch").WithBindingGroup("Touch")
     .WithRequiredDevice("<Touchscreen>").WithOptionalDevice("<Gamepad>");

File.WriteAllText(path, asset.ToJson());
AssetDatabase.ImportAsset(path);
```

- **Write the JSON, then import.** An `.inputactions` file is a text asset behind a scripted
  importer; `AssetDatabase.CreateAsset` would produce a `.asset` the importer never sees.
- **Report first.** The menu item `Tools/Unity Dev/Input/Create Run Actions…` shows the path, the
  map, each action with its type and binding count, and the schemes, and writes only on
  confirmation. From a live Editor, `CreateRunActions.Plan(path)` returns the same report and
  `CreateRunActions.Write(path, overwrite)` refuses an existing file unless told otherwise.
- **Read it back.** `Write` loads the imported `InputActionAsset` and reports what the importer
  produced, then run the lint on the file — the script proves the write, the lint proves the
  coverage.
- **Every build generates new ids.** Overwriting a shipped asset orphans saved rebinds; the
  report says so when the file exists.
- **Editing by hand is fine** — it is JSON. Keep `version`, `name`, `maps[]`, `controlSchemes[]`;
  give each new row a fresh GUID; a part row comes after its composite row.

The same extension methods work at runtime, on an asset or on a free-standing `InputActionMap`,
with one condition: `AddAction` throws `InvalidOperationException` on a map that is enabled.
Disable, change, enable.

## More than one map

`Run` is the gameplay map. A game with menus adds a `UI` map (the Input System's UI input module
has its own default actions) and switches between them rather than leaving both live:

```csharp
actions.FindActionMap("Run", true).Disable();     // the reader's OnDisable does this
actions.FindActionMap("UI", true).Enable();
```

Disabling the reader is the switch: `RunInputSource.OnDisable` clears pending presses and held
levels, so nothing leaks from the menu into the run. A press that is bound in both maps —
`buttonSouth` as Submit and as Launch — is the classic leak, and it is why the reader comes back
with an empty latch.
