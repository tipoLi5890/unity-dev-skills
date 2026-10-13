# Sound effects as events — a name, a table, a voice cap and a cooldown

> Part of the `unity-game-feel` skill. The layer between gameplay and `AudioSource`: gameplay
> names an event, the table picks a clip and its variance, a pooled source plays it, and three
> limits decide whether thirty pickups in one step are thirty sounds (they are not).

## 1. Why a layer

`AudioSource.PlayOneShot(clip)` at the call site works until the runner sweeps through a line of
pickups. Thirty copies of one clip a few milliseconds apart do not sound like thirty pickups:
they sum into a comb-filtered smear, clip the mix, and take every voice the engine has. The same
call site also cannot vary the pitch, cannot be muted by a bigger event, and cannot be found by
grepping for the event's name.

With a layer, gameplay calls `sfx.Play("pickup")` and the table decides the rest.

## 2. The table

`resources/SfxPlayer.cs` holds an array of `SfxEvent` rows:

| Field | Default | Meaning |
|---|---|---|
| `name` | — | What gameplay asks for. One name per event, matching the `Feedback` row's sound channel |
| `clips` | — | One is picked per play, never the same twice running when there are two or more |
| `volume` · `volumeVariance` | 1 · 0.1 | Volume, and its random spread (±10 %) |
| `pitch` · `pitchVariance` | 1 · 0.08 | Pitch, and its spread. ±0.08 hides repetition without changing the note |
| `cooldownSeconds` | 0.05 | The event cannot sound again within this |
| `maxVoices` | 3 | Sources this event may hold at once |
| `priority` | 0 | Wins a full pool: 0 pickups and footsteps, 1 hits, 2 the gate, the launch, a fail |
| `spatialBlend` | 0 | 0 is 2D, the same in both ears; 1 is positioned in the world |

And on the player:

| Field | Default | Meaning |
|---|---|---|
| `voiceCap` | 8 | Pooled sources, and so sounds at once. Eight is a safe phone number and still reads as busy |
| `output` | — | The mixer group every pooled source routes to |
| `minDistance` · `maxDistance` | 2 · 25 | Full volume inside 2, silence at 25, linear between — for positioned events |
| `ignoreListenerPause` | off | On for a player that carries interface sounds which must play while `AudioListener.pause` is set |

The courier run's rows: `pickup` (three clips, priority 0, cooldown 0.05, `maxVoices` 3),
`land` (priority 1), `hit` (two clips, priority 1, `pitchVariance` 0.05 so it stays heavy),
`gate-open` (priority 2, `spatialBlend` 1 in the gate room), `launch` and `fail` (priority 2,
`maxVoices` 1).

## 3. Three limits, in order

```
Play("pickup")
  ├─ cooldown   played under cooldownSeconds ago?            → dropped
  ├─ per event  already on maxVoices sources?                → dropped
  └─ voice cap  a free source?                               → plays
                none free: the least important busy voice,
                strictly below this priority, nearest its end → stolen, plays
                otherwise                                     → dropped
```

`Requested`, `Played`, `Dropped` and `Unknown` count each outcome. `Unknown` above zero means a
name in gameplay with no row, or a row with no clips — put it on the probe beside the
`Feedback` counters. `Requested == Played + Dropped + Unknown` always holds.

The cooldown is what turns a stream of pickups into a ticking run of sounds rather than a smear;
the cap is what protects a hit from being starved by pickups. With the defaults, thirty pickups
in 0.1 s sound two or three times. The journey sets the cooldown to 0 and the per-event limit to
64 so the cap alone is under test, and asserts no more than 8 start.

**Voices are timed on the player's own clock**, from `clip.length / pitch` on unscaled time —
not from `AudioSource.isPlaying`, which reads false in a run with no audio device (batch-mode
tests) and for a frame after `Play`. Unscaled because audio runs in real time: a cooldown on
scaled time never expires during a hit stop.

## 4. Variance that hides repetition

- **Two to four clips per frequent event**, recorded or generated as a set. One clip at varied
  pitch still repeats its transient.
- **Pitch ±0.05–0.1.** More than ±0.15 changes the note and the size of the thing; a pickup that
  is sometimes a coin and sometimes a bell is two events.
- **Volume ±10 %.** More, and quiet plays read as missed.
- **Pitch by streak** for a run of pickups — each pickup inside 0.5 s of the last raises the
  pitch a semitone (×1.059), up to five — is a game design choice, and it goes in the row as a
  second event name (`pickup-streak`) chosen by gameplay, not as hidden state in the player.

## 5. Routing and the mixer

Every pooled source routes to `output`. Leave it empty and effects bypass the mixer: the SFX
volume slider does nothing to them and a pause snapshot does not duck them. Create the groups
(Master → Music, SFX, UI) and route the rest of the scene's sources as `unity-audio` →
`reference/mixer-routing.md` lays out; this player only needs the SFX group's reference.

Use two players when two groups behave differently: one on SFX for the world (paused with
`AudioListener.pause`), one on UI with `ignoreListenerPause` on for menu clicks during a pause.
Music is not an sfx event: `unity-audio` → `reference/music-playback.md`.

## 6. 2D and 3D

| Game | `spatialBlend` | Why |
|---|---|---|
| Side run, depot, sorting yard (2D, the whole level on screen or close to it) | 0 for everything | A 2D camera's listener sits off the plane; positioned sounds pan by the camera's x and fade by its z, which is noise |
| Lane run (3D, fixed camera) | 0 for the runner's own sounds; 0.5 for hazards, so they pan without fading | The runner is always at the same place on screen |
| Gate room (3D, first or third person) | 1 for the world — the gate, the sentry, the switch; 0 for the runner's own and for UI | Position is information: the sentry's footstep says where it is |

For positioned events, `rolloffMode` is Linear (`minDistance` 2, `maxDistance` 25) so silence at
the far distance is exact; the default logarithmic rolloff is still audible at many times its
max distance. `dopplerLevel` is 0 on the pool: a one-shot on a pooled source must not bend when
the source is moved to the next event's position. Put the `AudioListener` on the runner, not the
camera, in a third-person game, so what the runner hears does not swing with the orbit.

## 7. Import and source clips

Short effects import as `DecompressOnLoad`, mono, and play without a first-play hitch — the
postprocessor that applies this to a folder is `unity-audio` → `reference/import-automation.md`.
Deliver clips as 44.1 kHz mono WAV.

Generating a set of variants (three pickup chimes, two hit thuds of the same family) on a
self-hosted server: `comfyui-asset-generation`, its Stable Audio 3 workflow. Generate more
than needed and keep the ones that sit together; level-match them by ear before import, because
`volumeVariance` assumes the clips start equal.

## 8. Checking it

The journey: thirty pickup events inside 0.1 s start no more sources than `voiceCap`, every
request is counted, and nothing is unknown. Whether the pickup sound is pleasant after the
thousandth time is a person's call — hand them a capture of a full run with sound, not a clip in
isolation.
