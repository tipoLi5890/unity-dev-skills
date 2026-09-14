# Named situations: boot straight into the moment

> Part of the `unity-play-harness` skill. A situation is a name, a way in, and the set of things
> that must be true before anyone looks. `resources/Situations.cs` is the file;
> `templates/CourierSituations.cs` is a filled-in registration to copy.

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
