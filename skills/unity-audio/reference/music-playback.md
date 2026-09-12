# Music that survives a pause, a screen change and a lost focus

Import settings decide what music *costs*. This file is about the three runtime failures that
make it sound broken anyway: it cuts hard on a screen change, it freezes when the game pauses, and
a playlist goes permanently silent after the app loses focus.

## Two sources, one crossfade

One `AudioSource` cannot fade out of itself. Keep **two** on the music object and alternate: the
incoming track starts at volume 0 on the idle source, the outgoing one fades on the active source,
and they swap. A single fade timer `t` drives both — `a.volume = k`, `b.volume = 1 - k` — so the
pair can never both be loud.

Two fade lengths, not one:

| Transition | Length |
|---|---|
| Screen change (menu → game) | ~0.5 s — the player asked for it, get there |
| One playlist track into the next | ~2 s — nobody should notice a seam |

Stop the outgoing source once the fade completes, or it keeps decoding at volume 0.

## Advance the fade on unscaled time

A paused game normally sets `Time.timeScale = 0`. Anything driving a fade from `Time.deltaTime`
then stops mid-fade and the music sits at whatever volume it had reached — usually half.

```csharp
t = Mathf.Min(1f, t + Time.unscaledDeltaTime / fade);
```

`AudioSource.ignoreListenerPause = true` on both sources is the companion setting when the project
also uses `AudioListener.pause` to silence gameplay SFX: music keeps playing through the pause
menu while everything else goes quiet.

## Detecting "this track is ending" — and the state that ruins it

To crossfade *into* the next track, the check is remaining time, not a callback:

```csharp
bool ending = cur.clip != null && cur.isPlaying && cur.clip.length - cur.time <= CrossfadeSeconds;
```

The bug this ships with is the case where the source is not playing at all. A source stopped by
something outside the playlist — application focus loss, a Stop from another system — never
satisfies `ending`, because `isPlaying` is false and `time` has stopped advancing. The playlist
then waits forever and the game is silent for the rest of the session. Treat it as a second exit:

```csharp
bool stopped = cur.clip != null && !cur.isPlaying && musicEnabled;
if (ending || stopped) { AdvanceToNextTrack(); }
```

Note the `musicEnabled` term: without it, a source stopped *because the player turned music off*
looks identical to a source stopped by focus loss, and the playlist restarts itself on the next
frame.

Also: set `loop = true` only when the group holds a single track. A looping source never stops on
its own, so the `!isPlaying` exit above is dead for it — the playlist is left with only the
remaining-time test, and a missed handover restarts the same track instead of moving on.

## Make track selection a pure function

The "random, but never the same track twice in a row" rule is the part that is easy to get subtly
wrong and impossible to eyeball. Keep it out of the MonoBehaviour:

```csharp
public static int PickNext(int count, int last, System.Random rng)
{
    if (count <= 1) return 0;
    int i = rng.Next(count - 1);              // pick from the other tracks
    return i >= last && last >= 0 ? i + 1 : i; // skip over `last`
}
```

Uniform over the other `count - 1` tracks, and unit-testable in EditMode with no `AudioSource`, no
scene and no clips — feed it a seeded `System.Random` and assert the distribution and the
never-repeat property directly.

Read the arithmetic of the first pick before you copy it: with `last < 0` (nothing has played yet)
this form still draws `rng.Next(count - 1)`, so the final track can never be the one it opens with.
That is the class of thing a seeded test states in one assertion and eyeballing never finds —
decide whether you care, but decide it in the test.

Remembering "what played last" **per group**, in a static map keyed by group id, is what stops a
player who bounces between the menu and a game from hearing the same menu track every time.

## Scope

Nothing here is about mixing or musical structure — cue points, stingers timed to bars, adaptive
layers. Those are sound-design decisions and a middleware job (see the skill's scope note).
