# Game state and pause — the phase is a fact, and time scale only follows it

> Part of the `unity-scene-flow` skill. `resources/GameState.cs` is the file: seven phases, a
> table of legal transitions, a count of the ones refused. Plain C#, created once by
> `Bootstrap`. Worked setting: the **gate room** — the runner walks to the switch, the gate
> opens, reaching it wins; the sentry seeing the runner loses.

## 1. Seven phases, one table

```
                 ┌────────────────────────────────────────────┐
                 ▼                                            │
Boot ──► Menu ──► Loading ──► Playing ⇄ Paused ───────────────┤
  │                 ▲  │         │  │      │                  │
  └─────────────────┘  │         ▼  ▼      └──► Menu          │
                       └► Menu  Won Lost ──► Loading · Menu ──┘
```

| From | May go to | Because |
|---|---|---|
| `Boot` | `Menu`, `Loading` | A build goes to the menu; a situation or an Editor run goes straight to a level |
| `Menu` | `Loading` | Every way into play passes through a load |
| `Loading` | `Playing`, `Menu` | Arrived, or the load failed and the menu is the one place always reachable |
| `Playing` | `Paused`, `Won`, `Lost`, `Loading` | The last is a door to the next room |
| `Paused` | `Playing`, `Loading`, `Menu` | Resume, restart, quit |
| `Won`, `Lost` | `Loading`, `Menu` | Next or retry, or leave |

Everything else is refused: `Paused → Won` (a paused game cannot be won — the bug where the
gate's trigger fires on the frame the menu opens), `Won → Playing`, `Menu → Playing` without a
load, and any move to the phase the game is already in.

```csharp
GameState state = Bootstrap.Get<GameState>();

if (!state.TryGo(GamePhase.Won))                        // false: nothing changed
    Debug.Log("refused " + state.LastRefusal);          // "Paused → Won"

state.Changed += (from, to) => { if (to == GamePhase.Lost) ShowRetry(); };
```

| Member | Meaning |
|---|---|
| `TryGo(to)` | Perform a legal transition and raise `Changed(from, to)`. `false`, with nothing changed, otherwise |
| `CanGo(to)` | The same question without the side effect — for greying out a button |
| `TogglePause()` | `Playing ⇄ Paused`; `false` in any other phase |
| `Phase`, `Previous`, `Name` | Where the game is, where it was, and the string the probe prints |
| `Refusals`, `LastRefusal` | How many transitions were turned away, and the last one |
| `Rule` | The table, as a `Func<GamePhase, GamePhase, bool>`; `GameState.DefaultRule` is the one above |
| `ownsTimeScale` | On: entering `Paused` sets `Time.timeScale` to 0, leaving restores it |

**The machine never throws for an illegal move, and it never performs one.** A caller that
cannot tell which phase the game is in asks and is told no; the count of refusals shows up in
the timeline, where a number that grows is a caller worth finding.

**A handler does not start the next transition.** `TryGo` from inside `Changed` is refused:
later subscribers would hear the two changes in the wrong order. Start it from the next frame.

**One object moves the phase for each reason.** The gate asks for `Won`. The sentry's detection
asks for `Lost`. `Bootstrap` moves in and out of `Loading`. The pause owner toggles `Paused`.
Nothing else calls `TryGo` — grep for it and count the callers:

```bash
grep -rnE "\.(TryGo|TogglePause)\(" Assets --include='*.cs'
```

A game that needs another phase — a cutscene, a shop, a turn waiting on the opponent — adds a
value to `GamePhase` and rows to its own rule function, then assigns `state.Rule`. Sub-states of
play (the runner grounded or falling, a sentry suspicious or alert) are not game phases; they
belong to the object that has them.

## 2. Pause is a state, not a time scale

`Time.timeScale = 0` stops some things. A paused game has stopped *all* of the simulation and
none of the interface. The difference is the list below, and it is why the phase is the fact
and the scale is one consequence of it.

| At `timeScale` 0 | Stops | Keeps running |
|---|---|---|
| The fixed step | `FixedUpdate`, physics, anything on `Time.fixedDeltaTime` | — |
| The frame | — | `Update` and `LateUpdate`, every frame, with `Time.deltaTime == 0` |
| Scaled waits | `WaitForSeconds`, `Invoke`, a timer adding `Time.deltaTime` | `WaitForSecondsRealtime`, `yield return null`, anything on `Time.unscaledDeltaTime` |
| Animation | An `Animator` in `Normal` or `Fixed` update mode | One set to `AnimatorUpdateMode.UnscaledTime` — the pause menu's own |
| Particles | Systems on scaled time | A system whose main module has `useUnscaledTime` on |
| UI | — | Events, clicks, navigation: input is not scaled |
| Audio | **Nothing.** Sources keep playing | Use `AudioListener.pause`, with `ignoreListenerPause` on what plays through it |
| Input | — | Actions still fire; a press made in the menu is still pending on resume |
| Cameras | Cinemachine damping and blends | A Brain told to ignore time scale |

So code in `Update` that does not multiply by `Time.deltaTime` — a cooldown counted in frames,
a raycast that opens the gate, a sentry that turns by a fixed angle — runs straight through a
pause that is only a time scale. Two rules cover it:

1. **Simulation runs on the fixed step, or checks the phase.**

   ```csharp
   void Update()
   {
       if (!_state.IsPlaying) return;          // the phase, not Time.timeScale == 0
       ...
   }
   ```

2. **One writer of `Time.timeScale`.** With no hit stop or slow motion in the game, that is
   `GameState` (`ownsTimeScale` on): entering `Paused` remembers the scale it found and resuming
   restores it. Once hit stop or slow motion exists, two writers race — a stop live at 0.05 when
   the player pauses is stored as the scale to resume to, and the game resumes at 5 % for good.
   Then the hit-stop owner writes the scale and the phase only sets its base:

   ```csharp
   state.ownsTimeScale = false;                                  // where Bootstrap builds GameState
   state.Changed += (from, to) => HitStop.SetBase(to == GamePhase.Paused ? 0f : 1f);
   ```

   The owner, its request queue and why a pause survives a stop → `unity-game-feel` →
   `reference/hit-stop-and-time.md`.

   ```bash
   grep -rn "timeScale *=" Assets --include='*.cs'      # one file may appear: GameState.cs or HitStop.cs
   ```

What each neighbour needs for the pause to be complete:

| System | On entering `Paused` | Detail |
|---|---|---|
| Music | Keeps playing; fades run on unscaled time; `ignoreListenerPause` on the music sources when gameplay sound is silenced with `AudioListener.pause` | `unity-audio` → `reference/music-playback.md` |
| Input | Disable the gameplay map, enable the UI map; on resume the reverse, then `ClearPresses()` — a press made in the menu never aged | `unity-input` → `reference/action-asset.md`, `unity-input` → `reference/reading-input.md` |
| Camera | Damping freezes; turn the Brain's ignore-time-scale on only for a menu that moves the camera | `unity-camera` → `reference/update-order-and-jitter.md` |
| Menu animation | Unscaled, and never used as a state: a fading menu is still "visible" | `unity-game-ui` → `reference/screen-transitions.md` |

The wiring, in the one object that owns the pause — in Boot, beside the menu it shows:

```csharp
void OnEnable()  => _state.Changed += OnPhase;
void OnDisable() => _state.Changed -= OnPhase;

void Update()
{
    // Spent on the frame: at timeScale 0 no fixed step runs to spend it.
    if (RunInputSource.Resolve(_inputHost, ref _input) && _input.TryUse(RunButton.Pause))
        _state.TogglePause();
}

void OnPhase(GamePhase from, GamePhase to)
{
    bool paused = to == GamePhase.Paused;
    pauseMenu.SetActive(paused);
    AudioListener.pause = paused;                       // music sources ignore it
    if (from == GamePhase.Paused && to == GamePhase.Playing) _input.ClearPresses();
}
```

## 3. Quitting and going to the background

| Event | Desktop | Phone | Do |
|---|---|---|---|
| `OnApplicationPause(true)` | Rare | The app left the foreground: a call, the home gesture, the task switcher | Pause, **and write the save now** |
| `OnApplicationPause(false)` | — | Back in the foreground | Stay paused. The player resumes, not the OS |
| `OnApplicationFocus(false)` | Window lost focus | Also raised by a system dialog or the keyboard | Pause if the game is real-time; do not save on every one |
| `OnApplicationQuit`, `Application.quitting` | Reliable | **Not reliable**: an app swiped away or killed for memory gets neither | Nothing the game depends on |
| `Application.wantsToQuit` | Return `false` to cancel — "unsaved progress" | Not raised | Desktop only |

`Bootstrap` handles the first row: with `pauseOnBackground` on it moves `Playing → Paused`, then
raises `Backgrounded`. Subscribe once, where the game writes checkpoints:

```csharp
Bootstrap.WhenReady(boot => boot.Backgrounded += () =>
    boot.Saves.Write(_current, DateTimeOffset.UtcNow.ToUnixTimeSeconds()));
```

The write is synchronous and small, so it finishes inside the callback; an asynchronous write
started there may never complete. A quit button calls `Application.Quit()` after the same
write. It does nothing in the Editor, and a phone game has no quit button at all.

A game that pauses on lost focus is undebuggable in the Editor with the Game view unfocused.
Gate it: `if (!Application.isEditor)`.

## 4. On the probe

`Bootstrap.Awake` calls `state.RegisterOnProbe()`. When `GameProbe` is in the project the phase
becomes `state` in every snapshot:

```
[PROBE] frame=412 t=6.840 scene=GateRoom situation=gate-room state=Paused …
```

The call goes through reflection, so `GameState.cs` compiles in a project with no harness and
returns `false` there. Two cases need one line by hand:

- **The runner already owns the state slot** (`GameProbe.SetState(() => run.State)`). Publish the
  phase under a key instead: `state.RegisterOnProbe("phase")`.
- **A player build with managed stripping.** A `GameProbe.SetState` nothing calls directly may be
  stripped. Call it directly where the game registers its other hooks:
  `GameProbe.SetState(() => state.Name);`

What a journey asserts over the timeline:

| Claim | Check |
|---|---|
| The phases happened in this order | The distinct `state` values equal `Boot, Loading, Playing, Paused, Playing, Won` |
| No illegal change ever happened | Every pair of consecutive samples with different states satisfies `GameState.DefaultRule` |
| A refused move changed nothing | `TryGo` returned `false`, `Refusals` went up by one, `Phase` is the same |
| Paused means stopped | Position and `Time.time` are identical across fifteen paused frames |
| A phase sequence with no pause in it only moves forward | `JourneyAsserts.Monotonic(samples, order)` — it rejects `Playing` after `Paused`, so it fits a run with no pause |

`templates/SceneFlowJourneyTest.cs` holds the first four; `SCENEFLOW_JOURNEY_BREAK=illegal`
swaps in a table that allows everything and turns the test red. Count waits in frames in any
journey that pauses: `Time.time` does not advance, and a loop waiting on it never ends →
`unity-play-harness` → `reference/journeys.md`.
