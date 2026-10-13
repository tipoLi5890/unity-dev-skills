# The Boot scene — one place that owns everything that outlives a level

> Part of the `unity-scene-flow` skill. `resources/Bootstrap.cs` is the file: a component on the
> root of a scene named Boot, first in the build's scene list. It creates the services, puts them
> in one registry and loads the first content scene additively. Worked setting: the **gate room**
> — the runner walks to a switch, the switch opens the gate, a sentry watches.

## 1. What lives where

| Lives in Boot, for the whole session | Lives in a content scene, rebuilt on every load |
|---|---|
| `GameState` — which phase the game is in | The room: floor, gate, switch, sentry posts |
| `SceneLoader` — the only caller of `LoadSceneAsync` | The runner, the sentry, the level's camera target |
| `SaveStore` and the save currently in memory | Lights and the level's lighting data |
| `PickupObjectPool`, and every pooled instance under it | Spawn points, checkpoints, `PersistentId` objects |
| The music sources, the `AudioListener` when the camera is persistent | Ambient sources of the room |
| The root UI document or canvas: loading screen, pause menu | World-space prompts |
| The input reader, when one player object is not its natural owner | — |

The test for a new object: **would it be wrong for this to reset when the gate room reloads?**
Yes → Boot. No → the level. Anything in the level that needs to *remember* across a reload does
not move to Boot; it writes a fact into the save (`reference/save-format.md`) and reads it back.

The Boot scene holds no geometry, no light and no camera a level could want to replace. A scene
that is first in the build list and has a level in it is a level that can never unload.

## 2. Set-up

1. Create `Assets/Scenes/Boot.unity`. One root object, `Boot`, with `Bootstrap`. Add
   `SceneLoader` and `PickupObjectPool` (on a child) in the Inspector so their fields are editable;
   `Bootstrap` adds a missing `SceneLoader` itself.
2. Put Boot at index 0 of the build's scene list, and every content scene after it.
3. Set `firstScenePath` to the scene that follows boot — `Assets/Scenes/Menu.unity` — and
   `firstPhase` to the phase it arrives in (`Menu`). Empty loads nothing: the game stays in
   `Boot` until something calls `LoadContent`.
4. Check it from the terminal: the log of a run carries
   `[BOOT] ready services=3 scene=Boot`, then `[SCENE] loaded Assets/Scenes/Menu.unity in …`.

```csharp
// Anywhere in a level, from Start onwards:
GameState state = Bootstrap.Get<GameState>();
Bootstrap.Instance.LoadContent("Assets/Scenes/GateRoom.unity");      // → Loading → Playing
```

## 3. Service access without a singleton per class

Ten managers with ten `static Instance` fields is ten lifetimes nobody wrote down: each decides
on its own when it exists, each survives or dies with whatever scene it was dropped in, and each
is found by whoever happens to ask first. One registry replaces them:

```csharp
public sealed class ServiceRegistry
{
    public void Provide<T>(T service) where T : class;   // throws when T is already provided
    public T Get<T>() where T : class;                   // throws, listing what IS provided
    public bool TryGet<T>(out T service) where T : class;
}
```

- **One static in the game**: `Bootstrap.Instance`, and `Bootstrap.Get<T>()` on top of it.
- **Created once, in one method, in dependency order.** `Bootstrap.Awake` reads top to bottom as
  the initialisation order of the game. A service that needs another takes it as a constructor
  argument on the line below.
- **A second `Provide<T>` throws.** A service cannot be swapped behind a caller that already
  holds it. A test that wants a fake builds its own registry.
- **Register by interface when there is one**: `Services.Provide<ISaveStore>(store)`. The key is
  the type argument, not the runtime type.
- **Plain C# first.** `GameState` and `SaveStore` are not components: an EditMode test builds
  them with `new`. Only a service that needs coroutines, serialised fields or a transform
  (`SceneLoader`, `PickupObjectPool`) is a `MonoBehaviour`.
- **Pass, do not fetch, below the top.** The object that builds the runner calls
  `Bootstrap.Get<GameState>()` once and hands the state to the runner. Code that reaches for the
  registry from every `Update` has only renamed the singleton.

Add a game's own service where the three built-in ones are provided:

```csharp
Bootstrap.WhenReady(boot => boot.Services.Provide(new RunSimulation(seed: 7)));
```

## 4. Initialisation order

| Order | What runs | What may be assumed |
|---|---|---|
| 1 | `[RuntimeInitializeOnLoadMethod(SubsystemRegistration)]` — statics are cleared | Nothing. This exists for Enter Play Mode with domain reload off |
| 2 | `[RuntimeInitializeOnLoadMethod(BeforeSceneLoad)]` — the first scene's objects are in memory, no `Awake` has run | The active scene's name and path |
| 3 | `Bootstrap.Awake` (execution order −1000) — services created, registry filled, `WhenReady` callbacks run | Nothing from a content scene |
| 4 | `Awake` and `OnEnable` of everything else in Boot | The registry |
| 5 | `Bootstrap.Start` — the first content load begins | — |
| 6 | Content scene `Awake` and `OnEnable`; the scene becomes active; its `Start`; `SceneLoader.Loaded` within the frame after | Every service, from `Start` |

Three rules keep that table true:

- **`Awake` wires the object to itself; `Start` talks to others.** A content object caches its
  own components in `Awake` and asks for services in `Start`.
- **`DefaultExecutionOrder` orders scripts within one scene load, not across loads.** It makes
  `Bootstrap` first in Boot. It does nothing about a scene that was already open.
- **Subscribe in `OnEnable`, unsubscribe in `OnDisable`** — and when the service might not exist
  on the first `OnEnable`, subscribe through `Bootstrap.WhenReady`.

## 5. Pressing Play from any scene

In a build the first scene is always index 0. In the Editor it is whichever scene is open, and a
level opened on its own has no services. Two fixes; pick one per project.

**A. Load Boot beside the open scene** — what `Bootstrap.EnsureBootScene` does, with no set-up:

```csharp
[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
static void EnsureBootScene()
{
    if (SceneManager.sceneCountInBuildSettings == 0) return;
    if (Path.GetFileNameWithoutExtension(SceneUtility.GetScenePathByBuildIndex(0)) != "Boot") return;
    Scene opened = SceneManager.GetActiveScene();
    if (opened.buildIndex == 0) return;
    s_OpenedScenePath = opened.path;
    SceneManager.LoadScene(0, LoadSceneMode.Additive);     // completes on the next frame
}
```

Boot then adopts the open scene as content and goes `Boot → Loading → Playing`. The cost: the
open scene's `Awake` and `OnEnable` run **before** Boot exists. That is why content never touches
a service in `Awake`, and why `Bootstrap.WhenReady` exists — it runs at once in a build and one
frame late here. A scene opened this way must also be in the build's scene list, or its path
means nothing to `SceneLoader.Load` on the next reload.

**B. Always start from Boot** — the order is then identical to a build, at the cost of one
Editor file. Put this in an `Editor` folder; the menu item toggles it:

```csharp
// Assets/Editor/PlayFromBoot.cs
using UnityEditor;
using UnityEditor.SceneManagement;

static class PlayFromBoot
{
    const string Path = "Assets/Scenes/Boot.unity";

    [MenuItem("Tools/Unity Dev/Scene Flow/Play From Boot")]
    static void Toggle()
    {
        bool on = EditorSceneManager.playModeStartScene == null;
        EditorSceneManager.playModeStartScene = on ? AssetDatabase.LoadAssetAtPath<SceneAsset>(Path) : null;
        UnityEngine.Debug.Log("[BOOT] play mode starts from " + (on ? Path : "the open scene"));
    }
}
```

With B the open level is not loaded at all: Boot loads `firstScenePath`. Reaching a particular
moment is then a situation's job, not the open scene's → `unity-play-harness` →
`reference/situations.md`. Situations are registered in the Boot scene's `Awake`, which is the
reason their registration never misses a command-line request.

A PlayMode test run starts in a scene the test framework names `InitTestScene…`;
`EnsureBootScene` leaves it alone, and a journey builds the Boot it needs
(`templates/SceneFlowJourneyTest.cs`).

## 6. `DontDestroyOnLoad` or a persistent scene

Both keep an object alive across loads. They differ in what can be seen and undone.

| | `DontDestroyOnLoad(gameObject)` | A Boot scene that is never unloaded |
|---|---|---|
| Where the object is authored | Wherever the script that calls it happens to be | One scene asset, opened and edited like any other |
| What the Hierarchy shows before Play | Nothing: the set exists only at runtime | The whole persistent set, with its wiring |
| References between persistent objects | Found at runtime | Dragged in the Inspector, serialised |
| Returning to the first scene | Loads the object a second time; every such script needs a duplicate guard | Content loads never include Boot, so there is no second copy |
| Works with single-mode loads | Yes — that is what it is for | No: a single-mode load unloads Boot. Every load is additive |
| Tearing it down | Destroy each object by hand | Unload one scene |
| Restriction | Root objects only | None |

Use the scene. `DontDestroyOnLoad` is the right call in one place: a package or a third-party
object that marks itself, which then sits in the runtime-only scene the Hierarchy labels
DontDestroyOnLoad and is nobody's to manage.

**The duplicate guard is still there**, because loading scene 0 by mistake is one line away:

```csharp
if (Instance != null && Instance != this) { Destroy(gameObject); return; }
```

It logs a warning when it fires. A project that sees that warning has a "back to menu" button
that loads the Boot scene; it should call `LoadContent` with the menu's path.

## 7. Checks

```bash
# Boot is scene 0, and every scene the code names is in the list.
grep -n "path:" ProjectSettings/EditorBuildSettings.asset
# Nothing but the loader loads a scene, and nothing loads in single mode.
grep -rnE "LoadScene(Async)?\(" Assets --include='*.cs' | grep -v SceneLoader.cs
# No service is reached from Awake or OnEnable in content code.
grep -rnE "Bootstrap\.(Get|Instance)" Assets --include='*.cs'
```

Read the third list against the method each hit is in. A hit inside `Awake` or `OnEnable`
outside the Boot scene is a null reference waiting for route A.

The journey proves the survival half: `Boot_SurvivesTheLevel_AndThePoolHandsBackTheSameObjects`
unloads the level and asserts `Bootstrap.Instance` is the same object in the scene named Boot;
`SCENEFLOW_JOURNEY_BREAK=boot` puts the root in the level instead and turns it red.

## 8. Traps

- **A persistent object parented under a level object.** It is in the level's scene from that
  moment and unloads with it. Pooled instances are parented under the pool for this reason.
- **`Instantiate` with no parent lands in the active scene**, which is the level
  (`reference/additive-scenes.md`). A persistent object created at runtime is moved with
  `SceneManager.MoveGameObjectToScene(go, Bootstrap.Instance.gameObject.scene)` — root objects
  only.
- **Statics outlive Play mode when domain reload is off.** Every static in the flow is cleared
  in a `SubsystemRegistration` method; a static added later needs the same.
- **A level camera with an `AudioListener`, plus one in Boot.** Two listeners log a warning every
  frame and the engine picks one. One listener, in one place.
- **Assemblies.** `Bootstrap.cs` references `GameState`, `SceneLoader` and `SaveStore`; put the
  four in one Runtime assembly that gameplay assemblies reference, never the reverse. Where the
  boundaries go is `unity-new-project`.
