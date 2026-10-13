# Additive scenes — loading beside Boot, and what the active scene decides

> Part of the `unity-scene-flow` skill. `resources/SceneLoader.cs` is the file: one content
> scene loaded additively beside the Boot scene, progress reported, the old scene unloaded, one
> operation at a time. Worked setting: the **gate room**, and for streaming the **lane run** cut
> into stretches.

## 1. The five calls

| Call | What it does | What it does not |
|---|---|---|
| `SceneManager.LoadSceneAsync(index, LoadSceneMode.Additive)` | Starts reading the scene in the background; returns an `AsyncOperation` | Make it the active scene. Returns nothing usable when the scene is not in the build list |
| `op.allowSceneActivation = false` | Holds the scene at "read, not activated"; `op.progress` stops at 0.9 | Let any other async operation finish: they queue behind it |
| `op.allowSceneActivation = true` | Activates on a following frame: every `Awake` and `OnEnable` of the scene, in one frame | Spread that cost. It is the hitch the loading screen hides |
| `SceneManager.SetActiveScene(scene)` | Chooses where new objects land and whose render settings apply (§3) | Move anything that already exists |
| `SceneManager.UnloadSceneAsync(scene)` | Destroys the scene's objects | Free the assets they used: that is `Resources.UnloadUnusedAssets()` |

`LoadSceneMode.Single` appears nowhere. A single-mode load unloads every scene, Boot included.

## 2. Using the loader

```csharp
SceneLoader loader = Bootstrap.Get<SceneLoader>();
loader.Loaded += scene => Debug.Log("in " + scene.name);
loader.Failed += (path, reason) => Debug.LogError(path + ": " + reason);

bool started = loader.Load("Assets/Scenes/GateRoom.unity");   // false: an operation is in flight
```

Normally the game does not call `Load` directly: `Bootstrap.LoadContent(path, arriveAs)` moves
the phase to `Loading`, calls it, and moves to `arriveAs` when `Loaded` is raised
(`reference/game-state-and-pause.md`).

| Member | Meaning |
|---|---|
| `Load(path)` | Unload the current content, load this one, make it active. `false` while busy |
| `Unload()` | Leave only Boot. `false` while busy or with nothing loaded |
| `Adopt(scene)` | Take an already-loaded scene as content: Play pressed in the Editor with a level open, or a scene a test created |
| `IsBusy`, `Progress` | One operation in flight; 0..1 across it, 0.9 meaning ready and held |
| `Refused` | Requests turned away because one was in flight — a count that should stay 0 in a timeline |
| `activationGate` | `Func<bool>`: hold at 0.9 until it returns true (a fade finishing) |
| `stallSeconds` 10, `minimumSeconds` 0, `unloadUnusedAssets` on | Serialised tunables |

**Old scene out first, then the new one in.** Both in memory at once is the peak that gets a
phone build killed. The cost is a frame with only Boot on screen, which is what the loading
screen in Boot is for.

**One operation at a time.** A double-clicked "Retry" must not start two loads of the same room.
The guard is in the loader, not in the button: `Load` returns `false` and counts the refusal.

## 3. What the active scene decides

Exactly one loaded scene is active. Two things follow it.

| Follows the active scene | Consequence |
|---|---|
| Where `Instantiate(prefab)` and `new GameObject()` land when given no parent | With Boot active, every projectile, pickup and effect a level spawns is in Boot and survives the level |
| `RenderSettings`: skybox, ambient light, fog, the sun source, reflection settings | The level looks lit by Boot's empty settings until the level is active |

`SceneLoader` sets the active scene from `SceneManager.sceneLoaded`, which is raised after the
scene's `Awake` and `OnEnable` and before its `Start`. So:

- From `Start` onwards a level's `Instantiate` lands in the level.
- In `Awake` and `OnEnable` it lands in the scene that was active before. Pass a parent, or name
  the scene: `Instantiate(prefab, gameObject.scene)` and
  `SceneManager.MoveGameObjectToScene(go, gameObject.scene)` (root objects only).
- Anything spawned **into Boot on purpose** — a pooled instance — is parented under its owner.

What does **not** follow the active scene: physics (every loaded scene simulates in one world
unless it was loaded with a local physics mode), `FindAnyObjectByType` (searches all loaded
scenes), and baked lightmaps, which each scene brings with it.

**Check:** `spawned.scene.name` is the level's name. The journey asserts exactly that after the
second level arrives.

## 4. Unloading

`UnloadSceneAsync` destroys every object in the scene and raises `OnDestroy` on each. Three
things it leaves behind:

- **Assets.** Textures, meshes and clips the scene referenced stay in memory until
  `Resources.UnloadUnusedAssets()` — a full scan and a hitch. The loader runs it after each
  unload, behind the loading screen. Never call it during play.
- **Subscriptions.** A level object that subscribed to a Boot service and did not unsubscribe in
  `OnDisable` is held by the service for ever: a destroyed object whose method still runs, and a
  `MissingReferenceException` on the first event after the reload. Grep for it:

  ```bash
  # each subscription to a Boot service needs its -= in OnDisable
  grep -rnE "(Changed|Refused|Loaded|Unloaded|Failed|Backgrounded) [+-]= " Assets --include='*.cs'
  ```

- **Anything that was moved or parented into another scene.** It is no longer in the scene and
  is not destroyed with it.

`UnloadSceneAsync` returns `null` when the scene is the only one loaded. With Boot loaded that
cannot happen.

## 5. A loading screen that cannot hang

The loading screen lives in Boot, is shown on entering `Loading` and hidden on leaving it. Every
way it gets stuck, and what prevents each:

| The hang | Prevention |
|---|---|
| Waiting for `op.progress >= 1` with activation held | Progress stops at 0.9. Wait for `>= 0.9f`, then for `isDone` after allowing activation |
| `yield return new WaitForSeconds(…)` while `timeScale` is 0 — a load started from the pause menu | Wait on frames (`yield return null`) and compare real time. `WaitForSecondsRealtime` where a delay is wanted |
| A fade driven by `Time.deltaTime` or an Animator on scaled time | Unscaled time for anything in the loading path → `unity-game-ui` → `reference/screen-transitions.md` |
| `allowSceneActivation` never set back to true — an exception between the two lines, a gate nobody opens | `activationGate` is bounded by `stallSeconds`; the loader activates anyway and logs it |
| The scene is not in the build list: `LoadSceneAsync` hands back nothing and the caller dereferences it | The path is resolved with `SceneUtility.GetBuildIndexByScenePath` first; −1 fails before anything unloads |
| No progress at all — a queue blocked by another held operation | `stallSeconds` of real time with no progress raises `Failed` |
| An exception in a `Loaded` handler | The loader is already idle when it raises the event; the phase is moved by `Bootstrap`, not by the handler that threw |

The screen itself reads two values and decides nothing:

```csharp
void Update()
{
    bar.value = loader.Progress;                       // 0..1; 0.9 = ready and held
    if (state.Phase != GamePhase.Loading) Hide();      // the phase says when, never the progress
}
```

Set `minimumSeconds` to 0.5 when a fast load makes the screen flash; it is real time.
`Application.backgroundLoadingPriority = ThreadPriority.High` shortens a load behind a static
screen; leave it at `BelowNormal` when something animates over the load.

## 6. Name scenes by build path

| Reference | Breaks when |
|---|---|
| Name — `"GateRoom"` | Two scenes share a file name in different folders: the first in the list wins, silently |
| Build index — `3` | A scene is inserted above it in the list |
| Path — `"Assets/Scenes/GateRoom.unity"` | The file is moved — and then `GetBuildIndexByScenePath` returns −1, loudly |

Keep the paths in one place — constants, or a ScriptableObject list
(`reference/scriptable-objects.md`) — and check the list against the build:

```csharp
[Test]
public void EveryScenePath_IsInTheBuildList()
{
    var inBuild = new HashSet<string>();
    foreach (EditorBuildSettingsScene s in EditorBuildSettings.scenes) if (s.enabled) inBuild.Add(s.path);
    foreach (string path in ScenePaths.All) Assert.IsTrue(inBuild.Contains(path), path);
    Assert.AreEqual("Assets/Scenes/Boot.unity", EditorBuildSettings.scenes[0].path);
}
```

A `SceneAsset` field is Editor-only and cannot be read in a player; a serialised string path
can. The save file stores the same path (`reference/save-format.md`).

## 7. Streaming neighbours with a trigger ring

A level too large for one scene is cut into stretches, each its own scene, loaded additively
around the runner. These never become the active scene and never go through `SceneLoader` —
that holds the one content scene; a streamer holds many small ones.

Two rings per stretch, both centred on it:

| Ring | Size for a 40-unit stretch at run speed 8 | Does |
|---|---|---|
| Load ring | The stretch plus 30 units each side | Entering it requests the load |
| Unload ring | The stretch plus 45 units each side | Leaving it requests the unload |

The gap between the rings is the hysteresis: a runner turning round at the boundary does not
load and unload the same scene every second. The load ring's margin is distance, so it is time:
30 units at speed 8 is 3.75 s to finish a load. Size it from the slowest device's load time,
not from what looks far.

```csharp
// One per stretch, in the always-loaded scene, on a trigger collider sized to the load ring.
public sealed class StretchGate : MonoBehaviour
{
    public string scenePath = "Assets/Scenes/Lane_02.unity";
    public float unloadMargin = 15f;                     // unload ring = load ring + this
    AsyncOperation _op; bool _wanted; Transform _runner; Bounds _unloadRing;

    void Awake()
    {
        _unloadRing = GetComponent<Collider>().bounds;
        _unloadRing.Expand(unloadMargin * 2f);
    }

    void OnTriggerEnter(Collider other)
    {
        if (!other.CompareTag("Player")) return;
        _runner = other.transform; _wanted = true;
    }

    void Update()
    {
        if (_op != null && !_op.isDone) return;          // one operation per stretch at a time
        bool loaded = SceneManager.GetSceneByPath(scenePath).isLoaded;
        if (_wanted && _runner != null && !_unloadRing.Contains(_runner.position)) _wanted = false;
        if (_wanted && !loaded) _op = SceneManager.LoadSceneAsync(scenePath, LoadSceneMode.Additive);
        else if (!_wanted && loaded) _op = SceneManager.UnloadSceneAsync(scenePath);
    }
}
```

- **Nothing in a stretch may be referenced from another stretch.** Cross-scene references do not
  serialise. Neighbours meet through `PersistentId` or through Boot.
- **The ground loads before the runner arrives, and its collider with it.** A stretch whose mesh
  is drawn before its collider exists is the lane that drops the runner. Register both as
  readiness members and enter the stretch cold → `unity-play-harness` →
  `reference/situations.md`, the hazard lane situation.
- **Count the work.** Loads requested, completed and thrown away while still loading →
  `unity-profiling` → `reference/work-counters.md`. A high discard count means the rings are too
  tight.
- **Do not call `Resources.UnloadUnusedAssets` per stretch.** Let memory ride until a natural
  pause.
- Rooms and chunks in a 2D level have their own stitching → `unity-2d-level` →
  `reference/rooms-and-chunks.md`.

## 8. Lighting data comes with the scene

Each scene carries the lightmaps baked for it and they load with it. Two things do not sort
themselves out:

- **Render settings come from the active scene only** (§3). Stretches that stream in share the
  active scene's skybox, fog and ambient.
- **Light probes from several scenes must be re-tetrahedralised** after an additive load or
  unload, or dynamic objects are lit from the previous set:

  ```csharp
  LightProbes.needsRetetrahedralization += LightProbes.TetrahedralizeAsync;   // once, in Boot
  ```

Baking scenes that will be loaded together, which settings asset each uses, and probe placement
→ `unity-lighting` → `reference/bake-setup.md`.

## 9. Addressables scenes, in brief

A scene delivered through Addressables is not in the build's scene list, so none of the calls
above can see it. The shape is the same with three substitutions:

| Built-in | Addressables (REQUIRES com.unity.addressables) |
|---|---|
| `SceneManager.LoadSceneAsync(path, Additive)` | `Addressables.LoadSceneAsync(key, LoadSceneMode.Additive, activateOnLoad)` — returns a handle |
| `op.allowSceneActivation` | `activateOnLoad: false`, then `handle.Result.ActivateAsync()` |
| `SceneManager.UnloadSceneAsync(scene)` | `Addressables.UnloadSceneAsync(handle)` — the handle, never the scene: unloading by scene leaks the bundle |

Keep the handle next to the path, and confirm the signatures against the installed version
before writing the call:

```bash
grep -rn "public static .* LoadSceneAsync\|public static .* UnloadSceneAsync" \
    Library/PackageCache/com.unity.addressables*/Runtime/Addressables.cs
```

Boot stays in the build list either way. Groups, catalogs and what a sprite atlas inside a
bundle needs → `unity-sprite-atlas` → `reference/addressables-delivery.md`.
