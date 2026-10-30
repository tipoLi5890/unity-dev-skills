---
name: unity-scene-flow
description: >-
  Boot scene and additive loading, pause as a state, save files with migrations, checkpoints, pools.
---

# unity-scene-flow — one scene that never unloads owns what must survive a load; everything else is rebuilt from data

> **Almost nothing should survive a scene load by staying alive.** The instinct is to keep the
> player, the score and the managers with `DontDestroyOnLoad` and carry them from scene to scene.
> Do the opposite: a handful of services live in one scene that is never unloaded, and
> *everything else is destroyed and rebuilt from a short list of facts*. That list is the save
> file. A game that can rebuild a room from data already has saving, checkpoints and a retry
> button; a game that keeps objects alive across loads has to invent all three later, against
> its own structure.

## Load what the situation needs

| The situation | Read |
|---|---|
| "My managers are duplicated after returning to the menu"; what goes in Boot; the service registry; initialisation order; pressing Play from any scene; `DontDestroyOnLoad` against a persistent scene; duplicated managers | `reference/bootstrap.md` |
| `LoadSceneAsync`, `allowSceneActivation`, what the active scene decides, unloading, "the loading screen hangs at 90%" (stuck at 0.9), scene paths, streaming neighbours, Addressables scenes | `reference/additive-scenes.md` |
| "Pausing doesn't stop everything"; the phases and their legal transitions; what `timeScale` 0 stops and what it does not; backgrounding and quitting on a phone; the phase on the probe | `reference/game-state-and-pause.md` |
| "Add a save system"; "the save got corrupted"; what a save holds and never holds; the atomic write; versions and migrations; `JsonUtility` limits; where the file lives | `reference/save-format.md` |
| "Respawn at the checkpoint"; a checkpoint as a small save; respawn without reloading; what resets; the teleport | `reference/checkpoints.md` |
| `ObjectPool<T>` parameters, prewarming, resetting an instance, pooled objects in triggers, whether the pool helps | `reference/pooling.md` |
| Config assets, ids for kinds of thing, runtime sets, event channels; "progress resets in the build, not in the editor" | `reference/scriptable-objects.md` |
| Music and fades across a pause; `ignoreListenerPause` | `unity-audio` → `reference/music-playback.md` |
| Switching action maps for the pause menu · clearing presses on resume | `unity-input` → `reference/action-asset.md` · `unity-input` → `reference/reading-input.md` |
| A menu fade that became a state machine | `unity-game-ui` → `reference/screen-transitions.md` |
| Telling the camera a respawn was a cut; cameras at `timeScale` 0 | `unity-camera` → `reference/update-order-and-jitter.md` |
| Hit stop and slow motion beside a pause | `unity-game-feel` → `reference/hit-stop-and-time.md` |
| Baked lighting for scenes loaded together | `unity-lighting` → `reference/bake-setup.md` |
| `Physics.IgnoreCollision` lost on a reused instance | `unity-physics-3d` → `reference/editor-vs-build.md` |
| Scheduled, completed and discarded work for a pool or a streamer | `unity-profiling` → `reference/work-counters.md` |
| Cloud saves: access classes, locks, conflicts | `unity-ugs` → `reference/cloud-save.md` |
| Scenes and atlases delivered through Addressables | `unity-sprite-atlas` → `reference/addressables-delivery.md` |
| Rooms and chunks stitched in a 2D level | `unity-2d-level` → `reference/rooms-and-chunks.md` |
| Booting a test into a moment; journeys and timelines | `unity-play-harness` → `reference/situations.md` · `unity-play-harness` → `reference/journeys.md` |
| Rules as plain data with no scene | `unity-game-brief` → `reference/sim-presentation-split.md` |

```
Boot scene — build index 0, never unloaded        content scene — one at a time, additive
  Bootstrap ─ ServiceRegistry                        the room, the runner, the sentry
    GameState    Boot·Menu·Loading·Playing·           PersistentId on what the save names
                 Paused·Won·Lost                 ◄──  asks for services from Start
    SceneLoader  load · unload · one in flight        rebuilt from SaveData on every arrival
    SaveStore    save.json · .bak · .tmp
    PickupObjectPool  instances parented under it
```

| File | Is |
|---|---|
| `resources/Bootstrap.cs` | The root of the Boot scene: creates the services once, in order, and the registry that hands them out |
| `resources/SceneLoader.cs` | Additive load and unload by build path, progress, a stall limit, one operation at a time |
| `resources/GameState.cs` | Seven phases and the table of legal transitions; owns `Time.timeScale` while paused unless a hit-stop owner does; plain C# |
| `resources/SaveStore.cs` | `SaveData`, the migration chain, and a write that leaves the old save or the new one, never neither |
| `resources/PersistentId.cs` | The string a save uses to name a scene object |
| `resources/PickupObjectPool.cs` | `ObjectPool<T>` in Boot, with the counters that say whether it is working |
| `scripts/save_check.py` | Reads a save from outside Unity; exit 1 on a finding |
| `templates/SaveRoundTripTests.cs`, `templates/SceneFlowJourneyTest.cs` | The two gates |

---

## 1. Start here — the gate room

1. **Make the Boot scene.** `Assets/Scenes/Boot.unity`, first in the build's scene list: one
   root object with `Bootstrap`, a child with `PickupObjectPool`, the loading screen and pause menu.
   No geometry, no lights. Set `firstScenePath` to the menu's build path.
2. **Load only through Boot.** `Bootstrap.Instance.LoadContent("Assets/Scenes/GateRoom.unity")`
   moves the phase to `Loading`, unloads the old room, loads the new one additively, makes it
   the active scene and arrives in `Playing`. Nothing else calls `LoadScene`, and nothing loads
   in single mode.
3. **Ask for services from `Start`, never from `Awake`.**

```csharp
void Start()
{
    _state = Bootstrap.Get<GameState>();
    _state.Changed += OnPhase;                      // and -= in OnDisable
}

void OnReachedGate() => _state.TryGo(GamePhase.Won);   // false, and nothing happens, while Paused
```

4. **Give every saved object a `PersistentId`**, record facts as they happen
   (`save.SetFlag(id.Id, 1)`), and make each object able to put itself back from the save
   (`ResetTo(SaveData)`): the same pass runs after a load and after a respawn.
5. **Write the save at checkpoints and when the app leaves the foreground**, with the clock
   passed in: `Bootstrap.Get<SaveStore>().Write(save, DateTimeOffset.UtcNow.ToUnixTimeSeconds())`.
6. **Prove it, then prove the proof can fail.**

| Gate | Asserts |
|---|---|
| `SaveRoundTrip` (EditMode, 9 tests) | Write then read is equal; a version 1 file arrives as version 2; half a file is detected and the save before it is returned; a newer build's file is never overwritten |
| `GateRoom_PhaseMovesOnlyAlongLegalTransitions` | The timeline's phases are exactly Boot, Loading, Playing, Paused, Playing, Won; `Paused → Won` is refused; nothing moves and game time stands still while paused |
| `Boot_SurvivesTheLevel_AndThePoolHandsBackTheSameObjects` | The level unloads, Boot does not; a second unload in flight is refused; the pickups set out again are the same three objects; a new object lands in the level |

```bash
"$UNITY" -projectPath . -batchmode -runTests -testPlatform PlayMode -testFilter SceneFlowJourney \
    -testResults /tmp/results.xml -logFile /tmp/tests.log
SCENEFLOW_JOURNEY_BREAK=illegal   # · boot · pool — each turns one test red
python3 scripts/save_check.py "<persistentDataPath>/save.json"     # exit 1 on a finding
```

The journey builds its scenes with `SceneManager.CreateScene` — no scene asset, no build-list
entry — and drives pause through `ScriptedRunInput`. Copy the `resources/` files into one
Runtime assembly; the journey also needs the harness (`unity-play-harness` → `resources/`),
`RunInput.cs` and `ScriptedRunInput.cs` (`unity-input` → `resources/`) and
`com.unity.test-framework`. `GameState` publishes its phase on `GameProbe` by reflection, so the
runtime files compile with no harness in the project.

## Discipline

- **Every load is additive, and only `SceneLoader` loads.** One single-mode `LoadScene` unloads
  Boot. Grep for it before every release.
- **Boot holds services, never content.** If it would be wrong for a thing to reset when the
  room reloads, it is a service or a fact in the save — not a level object kept alive.
- **One static: `Bootstrap.Instance`.** Services are created in one method in dependency order
  and handed out by type. Below the top, pass them; do not fetch them every frame.
- **`Awake` wires an object to itself; `Start` talks to services.** Pressing Play on a level
  runs its `Awake` before Boot exists.
- **Name scenes by build path.** A name matches the first scene that has it; an index shifts.
- **Wait on frames and real time in the loading path.** `progress` stops at 0.9 while activation
  is held, and `WaitForSeconds` never returns at `timeScale` 0.
- **The active scene is the level.** New objects land there. Anything meant for Boot is parented
  under its owner.
- **The phase is the fact; `Time.timeScale` follows it.** `Update` runs at scale 0, audio plays,
  input fires. Simulation checks `IsPlaying` or runs on the fixed step. One object writes the
  scale: `GameState`, or — once the game has hit stop — the hit-stop owner, with
  `ownsTimeScale` off and the phase setting its base.
- **`TryGo` may say no.** An illegal transition is refused and counted, never performed. One
  object asks for each transition.
- **A save is facts by id.** No object references, instance ids, hierarchy paths or build
  indices; nothing derivable. The clock is a parameter.
- **Write to a temporary file, flush, verify, then replace — and never back up a damaged file
  over a good one.**
- **A version bump comes with a frozen old class, one migration step and one hand-typed
  fixture.** Old steps are never edited.
- **Respawn runs the same `ResetTo` pass as arrival.** Two ways of setting up a room are two
  rooms.
- **A pooled instance is cleaned on release, and the pool's own double-release check exists in
  the Editor only.** Watch `Created` stay flat; that is the measurement.
- **Nothing writes a ScriptableObject asset's serialised fields at runtime.** It persists in the
  Editor and is lost in a build.
- **The human keeps the feel verdict.** The journey shows the phase order and that time stood
  still; whether the pause, the fade and the respawn feel right is a judgement.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Menus, HUD, the loading screen's look, transitions | `unity-game-ui` |
| Music and mixers, action assets and rebinding, Cloud Save and accounts, test situations and journeys, the brief, lightmaps, frame-time counters, Addressables delivery, 2D rooms | the handoff rows of the table at the top: `unity-audio` · `unity-input` · `unity-ugs` · `unity-play-harness` · `unity-game-brief` · `unity-lighting` · `unity-profiling` · `unity-sprite-atlas` · `unity-2d-level` |
| Assemblies, version control, project creation | `unity-new-project` |
| LOD, occlusion, batching, texture streaming | `unity-scene-optimisation` |
| Building a 3D level: kits, prefabs, terrain | `unity-3d-level` |
| What a pickup, a switch or a door does | `unity-interaction` |
| Damage, projectiles, hit windows | `unity-combat` |
| Sentry behaviour, spawners and waves | `unity-game-ai` |
| Hit stop, shake, particles, haptics | `unity-game-feel` |
| Networked scene management and host migration | Out of scope — netcode APIs are out of scope for this plugin; topology and authority: `unity-live-services` → `reference/multiplayer.md` |

What is left is the frame the rest hangs on: **what exists for the whole session, how one room
replaces another, which phase the game is in, and the facts that put a room back.**
