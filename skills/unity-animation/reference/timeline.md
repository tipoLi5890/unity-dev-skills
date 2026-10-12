# Timeline — taking the character over, and handing it back

> Part of the `unity-animation` skill. REQUIRES `com.unity.timeline`. A Timeline is an authored
> sequence that drives an Animator for a while. The handover has two ends, and the game owns
> both: it enters its own cutscene state **before** the director plays, and leaves it on the
> director's `stopped` event — never by counting the Timeline's seconds.

## 1. The pieces

| Piece | Type | Role |
|---|---|---|
| The asset | `TimelineAsset` | Tracks and clips; no scene references |
| The player | `PlayableDirector` (component) | Plays one asset; holds the bindings from tracks to scene objects |
| An Animation track | `AnimationTrack` | Bound to an `Animator`; its clips override the Animator's output while they play |
| A signal | `SignalAsset` + `SignalEmitter` (a marker) + `SignalReceiver` (component) | A named moment on the Timeline, delivered as a UnityEvent |

Bind at runtime when the character is spawned rather than placed:

```csharp
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

public static class LaunchCutscene
{
    public static void Bind(PlayableDirector director, Animator runner)
    {
        var timeline = (TimelineAsset)director.playableAsset;
        foreach (TrackAsset track in timeline.GetOutputTracks())
            if (track is AnimationTrack && track.name == "Runner")
                director.SetGenericBinding(track, runner);
    }
}
```

Tracks are matched by name here because the binding key is the track object itself; name the
track after the role, not after the character that happens to fill it.

## 2. The handover

```csharp
public sealed class LaunchSequence : MonoBehaviour
{
    public PlayableDirector director;
    public RunController run;                   // replace with your game's state owner

    void OnEnable()  { director.stopped += OnStopped; }
    void OnDisable() { director.stopped -= OnStopped; }

    public void Play()
    {
        run.EnterCutscene();                    // 1 · the game changes state first: input off
        director.time = 0;
        director.Play();                        // 2 · then the picture starts
    }

    void OnStopped(PlayableDirector d)
    {
        run.ExitCutscene(run.transform.position);   // 3 · the game takes the transform back
    }
}
```

What happens to the Animator in between:

- **The controller keeps running underneath.** The Animation track overrides the properties its
  clips animate; the state machine still evaluates and the bridge still writes parameters. That
  is what makes the hand-back clean — when the track lets go, the Animator is already in the
  state the game's state calls for. Keep the bridge enabled during a cutscene.
- **The track lets go when the director stops** — at the end with `DirectorWrapMode.None`, or on
  `Stop()`. With `DirectorWrapMode.Hold` it never stops: the last frame is held, `stopped` does
  not fire, and the game waits in its cutscene state forever. Use `None` for anything gameplay
  resumes after.
- **`stopped` fires for the natural end and for `director.Stop()`** from a skip button, so one
  handler is the game's single exit path.

Where the character is during and after:

| `AnimationTrack.trackOffset` | The clip plays | Use for |
|---|---|---|
| `TrackOffset.ApplySceneOffsets` | From where the character is standing | A launch, a pickup flourish — anything that starts wherever the run got to |
| `TrackOffset.ApplyTransformOffsets` | From the track's authored position | A staged scene; the character is moved there on the first frame |

A clip with root motion leaves the transform where the clip ended. The game reads the transform
once in `OnStopped` and adopts it; a mover that keeps its own position and was not told snaps the
runner back on the next frame.

## 3. Signals — named moments, again

A signal is the Timeline's version of an AnimationEvent, with the same contract: it tells the
game that a named moment was reached, and the game decides what follows.

1. Create a `SignalAsset` named for the moment: `GateOpens`.
2. Add a `SignalEmitter` marker on the track at that time, pointing at the asset.
3. Put a `SignalReceiver` on the GameObject that receives it and add a reaction for that asset.

Where the receiver must be:

| Marker is on | Receiver goes on |
|---|---|
| The Timeline's own marker row | The `PlayableDirector`'s GameObject |
| A track | The GameObject bound to that track |

Two emitter settings decide what a skip does:

| `SignalEmitter` setting | Off | On |
|---|---|---|
| `retroactive` | Emitted only when playback passes the marker | Also emitted when playback starts after the marker's time |
| `emitOnce` | Emits on every loop | Emits once per play |

A signal the game depends on — the gate actually opening — is `retroactive = true` and
`emitOnce = true`, which covers a Timeline started or resumed part way through. A signal that is
decoration is neither.

**No signal is emitted on `director.Evaluate()`.** Timeline treats an evaluate as a scrub, and
markers fire on playback frames only — retroactive or not. So a skip (§4) delivers none of them,
and every outcome the game depends on has a game-side fallback in the exit path:

```csharp
void OnStopped(PlayableDirector d)
{
    gateSwitch.Open();    // replace with your game's method; a no-op when GateOpens already ran
    run.ExitCutscene(run.transform.position);
}
```

Prove both paths once: log from the reaction and from `OnStopped`, play the cutscene through,
then run §4's skip, and read which lines appear in each.

## 4. Clocks, skipping, and tests

| Want | Set |
|---|---|
| Runs while `Time.timeScale` is 0 (a pause-menu flourish) | `director.timeUpdateMode = DirectorUpdateMode.UnscaledGameTime` |
| Stops with the game clock (anything over gameplay) | `DirectorUpdateMode.GameTime` (the default) |
| Driven by code, frame by frame | `DirectorUpdateMode.Manual`, then set `director.time` and call `director.Evaluate()` — poses only, no signals (§3) |

Skip by jumping to the end and stopping. The evaluate lands the last pose; the signals it passed
over are not emitted, which is why `OnStopped` applies their outcomes (§3):

```csharp
director.time = director.duration;
director.Evaluate();             // the last pose; a scrub, so no signal fires
director.Stop();                 // raises stopped → the game's one exit path
```

In a journey, a situation that starts after the cutscene enters it the same way — play, skip,
wait on a readiness member that reads the game's state, not the director's:

```csharp
GameProbe.Ready("cutsceneDone", () => !run.InCutscene);
```

Situations and readiness sets are `unity-play-harness` → `reference/situations.md`.

## 5. What Timeline is not for

- **Gameplay reactions.** A hurt, a jump, an attack belong to the Animator graph, where the
  game's state can interrupt them. A Timeline cannot be interrupted into another Timeline
  half way without authoring that.
- **Anything that has to adapt to where things are**, beyond a start offset. Reach a moving
  switch with IK (`reference/ik-and-rigging.md`), not with a baked clip.
- **Waiting.** `yield return new WaitForSeconds((float)director.duration)` is gameplay waiting on
  an animation with the name removed, and it is wrong the first time someone skips.
