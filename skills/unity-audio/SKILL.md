---
name: unity-audio
description: >-
  Unity audio: memory, first-play hitches, codecs, AudioMixer routing, silent
  or one-ear 3D sound.
---

# unity-audio — the knobs, and which ones are safe to turn

> **Audio is the cheapest large win in a Unity project and the easiest to make worse.** Almost
> every number here trades memory or CPU against something inaudible — and the two most common
> defaults (Decompress On Load on music, a stereo clip on a 3D source) are not trade-offs at
> all, they are simply wrong.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Audio memory too high | §1 load type, §2 sample rate (`reference/sample-rate-and-codec.md`) |
| Hitch the first time a sound plays | §1 — a Streaming clip without background loading |
| Long level-load stall | §1 — music set to Decompress On Load |
| A 3D sound plays in one ear only | §3 — this is a bug, not a setting |
| Everything is silent, or 3D positioning is wrong everywhere | §3 — count the `AudioListener`s first |
| A Streaming clip is silent the first time it plays | §1 — background loading has not finished |
| Which mixer group does this sound belong in | `reference/mixer-routing.md` |
| Dozens of Audio Sources route to Master | `reference/mixer-routing.md` |
| CPU cost does not drop when everything is muted | §4 |
| Latency / crackle | §4 DSP buffer |
| New audio files keep importing on the defaults | `reference/import-automation.md` |
| `-executeMethod` aborts with "Scripts have compiler errors" after audio work | The contract above, then `reference/import-automation.md` |
| Effects made in code; no game sound may carry energy above a cutoff (e.g. 16 kHz); a loop clicks at its seam | `reference/synth-and-band-limits.md`, `scripts/spectrum_check.py` |
| Music freezes mid-fade while paused, frozen at half volume, or a playlist goes silent for good after focus loss | §5 |
| Folder-wide import settings; routing every AudioSource to its mixer group | `reference/import-automation.md`, `reference/mixer-routing.md` |
| What to report after a change | *Report format* |

## The working contract

> **Report, then wait.** Changing import settings triggers a reimport: it is slow, it rewrites
> `.meta` files across the project, and it is not something to undo casually. Survey the assets,
> present what you would change with before/after values, and **wait for confirmation** before
> applying anything.

- **Never hand-edit a `.meta` file.** Import settings only take effect through
  `AudioImporter` + `SaveAndReimport()` — or, for anything that should hold for a whole folder,
  through an `AssetPostprocessor.OnPreprocessAudio` keyed on the filename, so a new file dropped
  in tomorrow imports correctly with nobody remembering to do it:
  `reference/import-automation.md`.
- **Two API traps, both compile errors rather than warnings:**
  `AudioCompressionFormat` is in **`UnityEngine`**, not `UnityEditor`;
  and **`AudioImporter.preloadAudioData` is obsolete — `error CS0619`, which fails the build.**
  Preload moved into the per-platform `AudioImporterSampleSettings`.
- **One bad Editor audio script blocks every `-executeMethod` in the project.** Editor scripts
  compile as one assembly, so that `CS0619` aborts every unrelated headless run with `Aborting
  batchmode due to failure: Scripts have compiler errors.` If a headless Unity command starts
  exiting 1 right after audio work, read the compile errors, not the method you invoked.
- **`ai.defaultSampleSettings` is a struct copy.** Take it into a local, edit it, **assign it
  back**; `loadType`, `compressionFormat`, `quality`, `preloadAudioData` and `sampleRateSetting`
  live there, while `forceToMono` and `loadInBackground` stay on the importer itself.
- **Read the value back after applying** — and pin it with an EditMode test where you can:
  `clip.channels` and `clip.frequency` on the imported `AudioClip` report what actually happened,
  and catch a postprocessor that silently stopped matching the path. An importer setting that did
  not take is indistinguishable from one that did until you look.
- At most three adjust-and-verify cycles on one asset. Beyond that the setting is not the
  problem.

Connecting to the Editor: `unity-debug` → `reference/editor-control.md`.

## 1. Load Type — the single biggest memory lever

| Clip | Load Type |
|---|---|
| Short SFX, **uncompressed size under ~200 KB** | Decompress On Load |
| Medium, played occasionally | Compressed In Memory |
| Music, ambient beds, voice-over | Streaming |

> **Decompress On Load on anything over ~1 MB is the classic memory blow-up.** The whole clip
> sits in memory as PCM. It is also why a level load stalls: the decompression happens up front.
> **And it is the import default** — a freshly imported `.wav` reads
> `loadType = DecompressOnLoad`. Every clip in a project nobody has audited is on the expensive
> setting.

**Every Streaming clip needs `Load In Background` on** — `loadInBackground` also defaults to
**`false`**. Without it, first play blocks.

> **And then the first play is silent instead.** That is the setting working, not failing: the
> clip has not finished loading when `Play()` is called, so there is nothing to hear and no
> error. Three mitigations, in the order to try them:
>
> 1. **Preload it.** `clip.LoadAudioData()` at scene start, before anything asks for it.
> 2. **Schedule it.** `AudioSource.PlayScheduled(AudioSettings.dspTime + lead)` gives the async
>    load a window to land in.
> 3. **Change the load type.** A source that must be audible the instant it is asked for belongs
>    on **Compressed In Memory** rather than on Streaming at all: the clip is already resident, so
>    `Play()` has its data immediately and there is no async load to wait on. It decodes on the
>    fly as it plays — a little CPU on every play, in exchange for never missing one.
>
> Both `AudioClip.LoadAudioData` and `AudioSource.PlayScheduled` are present — if a
> snippet does not compile, it is the qualification, not the API.

## 2. Sample rate and codec

- **Codec per platform**: AAC on iOS, Vorbis on Android, Web and desktop, XMA and ATRAC9 only as
  per-platform overrides — never in `defaultSampleSettings`.
- **Vorbis quality defaults to `1` (100%)** — set it downward per category; dialogue 0.7–0.85.
- **Mobile SFX and UI at 22050 Hz** halve the PCM memory; `forceToMono` halves it again.
- **Source files are WAV or AIFF**, never pre-encoded to the shipping codec.

The table, the worked example and the one exception for long music:
`reference/sample-rate-and-codec.md`.

## 3. 3D sound in one ear is a bug

> **`spatialBlend == 1` on a clip with `channels == 2` plays the left channel only.** This is not
> a subtle spatialisation artefact — half the audio is gone.

Fix at import: enable **Force To Mono** (leave `normalize` on so the level is preserved) and
reimport. `panStereo = 0` is a stopgap that hides it without recovering the missing channel.

### Count the listeners before you believe anything else

> **`AudioListener` count must be exactly one.** Zero and the whole game is silent; two or more
> and Unity uses one of them, so positions are computed against a listener nobody meant. Neither
> state produces an error, and both look from the inspector exactly like a mixer problem or an
> import problem.

```csharp
var ls = UnityEngine.Object.FindObjectsByType<UnityEngine.AudioListener>(
    UnityEngine.FindObjectsInactive.Include, UnityEngine.FindObjectsSortMode.None);
return ls.Length + ": " + string.Join(", ",
    System.Linq.Enumerable.Select(ls, l => l.gameObject.name + (l.enabled ? "" : " (disabled)")));
```

Zero → add one to the camera that represents the player's ears. More than one → disable all but
the intended one rather than deleting, and say which you kept: the extras are usually on a
prefab that ships a camera of its own, so deleting fixes the scene and not the prefab. Run this
before any import audit — an audit that ends "audio memory halved" on a project with no listener
has measured nothing anyone can hear.

## 4. Mixer cost

Before measuring anything here: confirm a mixer exists at all, and that the listener count is
one (§3). With no mixer asset in the project, routing and effect cost are not the problem you
are looking at. Inventorying the mixers, classifying every Audio Source and assigning groups —
the whole routing pass, and the hard line between what is public API and what is not — is
`reference/mixer-routing.md`.

- **Group depth beyond ~3 levels** (Master → SFX/Music/Voice → sub-bus) adds per-frame routing
  cost on every group, **including muted ones**.
- **An effect on a silent group still runs at full DSP cost.** SFX Reverb is the usual offender.
  Push expensive effects down to leaf groups, and switch mix states with **snapshots** rather
  than enabling and disabling effects at runtime.
- **DSP buffer size:** 256 (Best Latency) / 512 (Good Latency) / 1024 (Best Performance).
  **Below 256 is too small** and shows up as crackle under load. Read the live values rather than
  the settings asset — `AudioSettings.GetConfiguration()` gives `dspBufferSize` and the actual
  output `sampleRate`, which belongs to the device, not to your clips — e.g. a device reporting
  **`48000` against 44.1 kHz clips** resamples every clip at runtime, a cost that is invisible
  in the importer.

## 5. Music playback across a pause and a lost focus

Import settings decide what music costs; these three decide whether it sounds broken. Worked
detail, including the code: `reference/music-playback.md`.

- **Two `AudioSource`s, alternating.** One source cannot fade out of itself. ~0.5 s on a screen
  change, ~2 s between playlist tracks, and stop the outgoing source once the fade ends.
- **Drive the fade from `Time.unscaledDeltaTime`.** A pause menu sets `timeScale = 0`, and a fade
  on scaled time then parks the music at half volume until the player resumes. Pair it with
  `ignoreListenerPause = true` on the music sources if the project uses `AudioListener.pause`.
- **`clip.length - clip.time <= crossfade` detects the end of a track — and `!isPlaying` has to
  count as ended too.** A source stopped from outside (focus loss) never advances `time`, so a
  playlist waiting only on the remaining-time test stays silent for the rest of the session.
  Guard that second branch with "music is enabled", or turning music off restarts it.
- **Keep next-track selection a pure static function** (`PickNext(count, last, rng)`): the
  never-repeat rule is unit-testable in EditMode with no `AudioSource` and no clips.

## Report format

Never "optimised the audio". For each asset changed:

```
<asset>  loadType: DecompressOnLoad → Streaming   sampleRate: 44100 → 22050
         memory (reported by importer): 4.2 MB → 0.4 MB
```

Then say what you did **not** change and why.

## Scope — what this skill does NOT do

Mixing and sound design decisions, DSP authoring beyond the small synthesis rules in
`reference/synth-and-band-limits.md`, and middleware (FMOD, Wwise) — those bring
their own memory model and their own import path, and the numbers here do not transfer. Nor does
this skill author mixer structure: **creating a mixer or a group, re-parenting a group and
setting a group's volume have no public API**, so those stay with the user in the Audio Mixer
window. Routing sources into groups that already exist is fully in scope —
`reference/mixer-routing.md` draws the line. Adaptive
music structure (cues on bar boundaries, layered stems) is a design job, not an import one: §5
stops at "the next track starts without a seam". The SFX event layer — one cue per game event,
voice caps, cooldowns — is `unity-game-feel` → `reference/sfx-events.md`, and a footstep an
animation event asks for goes through it (`unity-animation` → `reference/events-and-windows.md`).

Git LFS and `.gitattributes` setup for the binaries this skill imports is `unity-new-project`;
this skill only says to check that a **new** audio extension is actually covered before the first
commit. Generating music and SFX is `comfyui-asset-generation`.
