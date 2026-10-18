# Named situations: boot straight into the moment

> Part of the `unity-play-harness` skill. A situation is a name, a way in, and the set of things
> that must be true before anyone looks. `resources/Situations.cs` is the file;
> `templates/CourierSituations.cs` is a filled-in registration to copy, and
> `templates/CourierSituations2D.cs` is the same registration for a 2D game.

This answers the question that decides whether a game is testable at all: **how does a test reach
this screen?** If the answer is "play for ninety seconds", that moment is never checked twice.

```csharp
public sealed class Situation
{
    public string Id;                                   // kebab-case, used from the command line
    public Action Enter;                                // drives the game in, via the game's own API
    public Dictionary<string, Func<bool>> Ready;        // named members, all re-evaluated each poll
    public float TimeoutSeconds = 15f;                  // unscaled
}
```

## Register in the boot scene's Awake

Register everything before anything can ask for it, including a command line that named one.
`Awake` on a boot-scene object is early enough; "register on first use" is not, because the id
list is usually asked for *before* first use.

```csharp
void Awake()
{
    Situations.Register(new Situation("approach-gate", EnterApproachGate, 15f)
        .Needs("laneMesh")                              // no predicate: the game registered this one
        .Needs("laneCollider")
        .Needs("gate", () => _gate != null && _gate.IsArmed)
        .Needs("sentry", () => _sentry != null && _sentry.Patrolling));
}

void EnterApproachGate()
{
    float angle = Situations.Param("angle", 0f);        // -situation-param angle=80
    _run.ResetRun(lane: 1);                             // the game's own methods, never a field poke
    _run.PlaceAt(_track.PointBeforeGate(12f), angle);
    _run.Launch();
}
```

A member declared with **no predicate** is one the game itself registered on `GameProbe` at
startup — `laneMesh`, `laneCollider`. The situation only states that this moment requires it; the
game keeps owning it. A member declared **with** a predicate belongs to the situation, and is
removed again when another situation is entered.

`Situations.Enter(id)` drops the previous situation's own members, pushes this one's into
`GameProbe`, runs `Enter`, logs `[SITUATION] enter=approach-gate needs=…`, and returns a handle.
**Entering is not arriving.** The handle is where the waiting happens:

```csharp
SituationHandle h = Situations.Enter("approach-gate");
yield return h.WaitUntilReady();     // TimeoutException: "approach-gate not ready after 15.0s: laneCollider, sentry"
```

The timeout message names the members that never arrived — the whole return on this design. A
`WaitForSeconds(3f)` that fails tells you only that three seconds passed.

## Four ways in

| Caller | How |
|---|---|
| PlayMode test | `EditorSceneManager.LoadSceneAsyncInPlayMode(scenePath, new LoadSceneParameters(LoadSceneMode.Single))`, then `Situations.Enter` |
| Live Editor | `unity command eval 'return Situations.Enter("approach-gate").Id;'` |
| Windowed or player run | `-situation approach-gate -situation-param angle=80`, or `PLAY_SITUATION=approach-gate` |
| Project command | `unity command situation_enter -- --id approach-gate --params "angle=80"` |

**From a test**, load the scene `Single` in every test rather than additively: additive loading
leaves the previous test's objects alive, and the members then read true because *something*
named `laneCollider` exists — just not this test's. A scene missing from Build Settings still
loads by asset path. → `unity-debug` → `reference/visual-checks.md`

**From the command line**, `SituationBoot` installs itself after the first scene loads, waits one
frame so every `Awake` has registered, enters, waits and logs one of:

```
[SITUATION] enter=approach-gate needs=laneMesh,laneCollider,gate,sentry timeout=15.0s
[SITUATION] ready=approach-gate after 1.84s
[SITUATION] TIMEOUT approach-gate not ready after 15.0s: sentry
```

A timeout logs an error and **leaves the window up** rather than throwing into nothing: a moment
that failed to assemble is worth photographing.

**From a project command**, `situation_enter` outside Play mode starts Play mode and answers
`{"entered":false,"retry":true}`. Entering Play mode reloads the domain, so there is nothing to
return yet: poll `unity command probe` until `playing:true`, then re-issue it.

## Three situations for one game

| Id | Enters | Ready set | Because |
|---|---|---|---|
| `approach-gate` | Runner 12 units out, aimed at the gate, optional entry `angle` | `laneMesh`, `laneCollider`, `gate`, `sentry` | Every complaint about arriving at the gate starts here |
| `runner-launch` | Runner at the start line, `Launch()` called | `laneMesh`, `laneCollider`, `runner`, `pickups` | The first two seconds: sluggish or twitchy |
| `hazard-lane` | Mid-track, middle lane, `cold=true` forces a fresh load | `laneMesh`, `laneCollider`, `hazardVolume` | Streaming: the lane that pops in late |

`templates/CourierSituations2D.cs` carries the same idea into the three 2D views of the run —
keep the one the game is. The ready sets name the 2D colliders, because a tilemap drawn before
its collider is generated is the same split as a lane mesh without its collider.

| Id | Enters | Ready set | Because |
|---|---|---|---|
| `ledge-drop` | Side run: runner on a rooftop, `inset` units short of the edge, a gap below | `runnerCollider`, `rooftopMesh`, `rooftopCollider`, `gapHazard` | Every report about a jump that felt late or a fall that felt heavy |
| `depot-aisle` | Top-down depot: runner in aisle `lane`, sentry posted `distance` units ahead | `runnerCollider`, `aisleFloor`, `aisleWalls`, `sentry`, `visionCone` | "It saw me through the shelving" and "it never sees me" |
| `yard-step` | Sorting yard: pickup one cell short of the gate cell, runner one cell behind it | `runnerCollider`, `yardCells`, `yardWalls`, `pickup`, `gateCell` | One step decides it, so one step is the whole journey |

Two differences from the 3D file. Velocity is registered with `SetPlayerVelocity`, so the probe
never names a 2D type → `reference/probe-contract.md`. And every placement writes x and y only:
z is the sorting depth in a 2D scene, and a situation that zeroes it moves the runner behind the
background.

Keep the set small and keep the ids stable. They end up in test names, in journey directories,
in screenshot filenames and in the sentence you write back to the person who complained.

## Writing the set

- **List every member that has to exist.** Mesh, collider, volume, agent, camera target: the set
  is the specification of "this moment has assembled". The members that belong together — visible
  ground and its collider — are the ones worth naming separately.
- **Each member is a predicate, evaluated on every poll.** Never a `bool` set during load.
- **An empty set is not ready.** `GameProbe.AllReady` is false when nothing is registered, so a
  situation whose registration silently failed times out instead of passing instantly.

## Gotchas

**A situation that sets state directly tests a label.** `_run.Phase = Phase.Approach` produces the
right state with none of the work done — no track, no sentry, no camera move. Call the transition
the game itself calls, and let readiness prove the work happened.

**Stale readiness across a second Enter.** Two situations in one session, and the second inherits
the first's members; a `true` left over reads as "already ready" and the wait returns instantly
on a moment that has not assembled. `Situations.Enter` removes the members the previous situation
added for exactly this — and removes only those, so the game's own members survive.

**`-situation` leaking into `-runTests`.** A CI line carrying both boots the situation *and* lets
the test enter its own, and the two race. `SituationBoot` suppresses itself when `-runTests` or
`-testPlatform` is on the command line; set `SituationBoot.Suppress = true` before the first
scene load for any other case.

**Registry residue when domain reload is off.** With Enter Play Mode Options set to skip domain
reload, statics survive the previous session, so the registry still holds delegates closing over
destroyed objects and the second run enters a situation built from the first run's scene. Both
`Situations` and `GameProbe` reset from `RuntimeInitializeLoadType.SubsystemRegistration`, which
runs before the first scene of every session either way.

**`Application.runInBackground` is two different things.** `SituationBoot` sets the *runtime*
property so an unfocused window keeps ticking and waits do not time out for a reason that has
nothing to do with the game. That is unrelated to the test framework flipping `runInBackground`
in `ProjectSettings.asset` and leaving it there — a project-file edit to revert before
committing. → `unity-debug` → `reference/harness-trust.md`

**Parameters have defaults, so they are never required.** `Situations.Param("angle", 0f)` answers
0 when nobody passed one, and the same situation runs bare from a test and with `angle=80` from
the command line. A test sets them with `SetParam` before `Enter`; `ClearParams` in `[SetUp]`
keeps one test's parameters out of the next.

Confirm on your version: that `EditorSceneManager.LoadSceneAsyncInPlayMode` resolves from your
test assembly (it is `UnityEditor.SceneManagement`, so the call sits inside `#if UNITY_EDITOR`).

## A shot list over every situation

The same ids drive a screenshot pass that an agent which cannot see the screen uses to accept a
layout. In a 3D tennis game, 22 situations (four menu screens, matches in each venue and quality
tier, the pause panel, match end per venue, characters, a motion review) each played to a few
named moments and captured them:

- **One parameterised test over the whole list**, `[UnityTest] Situation([ValueSource(nameof(Ids))] string id)`,
  in its own category (`Shots`), never in Smoke: it is slow, and its output is pictures, not
  verdicts. An environment variable narrows it (`SITUATIONS=match/solo,shell/modes`) so a change
  to one screen re-shoots one screen.
- **Each shot is named for the moment**, `<id with / as _>-NN-<tag>.png` (`match_solo-04-contact.png`),
  and logged with its size: `[SHOT] <path> 1920x1080`. The test asserts every file exists and is
  over 10 KB, and that no error was logged. Opening the images is the agent's job, not the test's
  (`unity-debug` → `reference/visual-checks.md`).
- **Shots wait on the moment, not on time.** "Contact" waits for the hit event from the game's
  event stream and captures on that frame; "between points" waits for the phase. A fixed delay
  is used only for an animation that has no event (a menu focus slide).
- **Before every capture, wait for the render to be real**: a fixed resolution and no shader
  compiling (`unity-debug` → `reference/visual-checks.md`, hooks installed from an Editor assembly).
- **Situations never write the player's saved settings.** A static `ReadOnly` switch on the
  preferences store, set by the harness and by the command-line boot, makes every `Save` a no-op.
  This is a different tool from resetting prefs in `[SetUp]` (`unity-debug` →
  `reference/test-verdicts.md`): resetting protects the test from the developer's saves; read-only
  protects the developer's saves (a calibration done by hand in the Editor) from the tests.
- **Each run lives inside a harness object** that subscribes to `Application.logMessageReceived`
  for errors and exceptions, and on `Dispose` ends the match and destroys every persistent
  singleton the boot created, so the next id starts from nothing.
- **The built player takes the same ids**: `-situation <id> [-screenshotDir DIR] [-quit]`, plus
  `-autoplay` (below) and a switch that skips the physical input device. A build can
  then be checked with the same shot list as the Editor.

## Matches play themselves: the autoplayer

A moment deep in a match ("the contact frame of the third rally") is only reachable if someone
plays. **An autoplayer stands in for the human by injecting into the same input funnel the
device uses** (the router's `Down` / `Up`), never by calling the rules directly, so a situation
exercises the real path from input to judgement. Give it:

- one switch per seat, so a test can autoplay seat 0 against a bot;
- a key in the Editor (F8 here) that toggles it for player 1, so a person can watch a rally
  without a device attached;
- **timing noise**: it presses at the ideal moment plus a Gaussian offset (σ 40 ms here, drawn once
  per shot from a seeded generator), so it produces the range of judgements a person does, not
  only perfect hits, and the same seed gives the same match;
- a varied choice of command (a weighted random shot type), so every branch of the rules gets
  played;
- a press *and* a release a few frames later, because a device that ignores a held input needs
  the release before the next press counts.

It is test equipment that ships, like the probe: the command-line `-autoplay` uses it in a player.
The smoke test that rides on it is in `journeys.md`.
