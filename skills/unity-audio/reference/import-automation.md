# Import settings that apply themselves

Per-asset `AudioImporter` calls are a chore you have to remember. Every new file dropped into the
project imports on the defaults — Decompress On Load, quality 1.0, stereo — and nobody notices
until the memory report. The fix is to make the rule the project's default: one
`AssetPostprocessor` scoped to the audio folder, keyed on the filename, committed as code.

## The postprocessor

```csharp
using UnityEditor;
using UnityEngine;

public sealed class AudioImportRules : AssetPostprocessor
{
    const string Root = "Assets/Audio/";

    void OnPreprocessAudio()
    {
        if (!assetPath.StartsWith(Root)) return;
        var ai = (AudioImporter)assetImporter;
        string file = System.IO.Path.GetFileNameWithoutExtension(assetPath);
        bool music = file.StartsWith("bgm_") || file.StartsWith("jingle_");

        ai.forceToMono = true;              // importer-level
        ai.loadInBackground = music;        // importer-level

        var s = ai.defaultSampleSettings;   // STRUCT COPY — see below
        s.sampleRateSetting = AudioSampleRateSetting.PreserveSampleRate;
        s.preloadAudioData = !music;
        if (music)
        {
            s.loadType = AudioClipLoadType.Streaming;
            s.compressionFormat = AudioCompressionFormat.Vorbis;
            s.quality = 0.6f;
        }
        else
        {
            s.loadType = AudioClipLoadType.DecompressOnLoad;
            s.compressionFormat = AudioCompressionFormat.PCM;
        }
        ai.defaultSampleSettings = s;       // assign back or nothing happens
    }
}
```

What this shape does, for a phone target: music streams so it never stalls a scene load, short
SFX decompress so first play has no hitch, everything is mono for a phone speaker, and the sample
rate is preserved because the delivered files are already normalised. Dropping a file into the
folder is then the entire workflow — no `.meta` is ever hand-edited, and the settings live in a
diff instead of in one `.meta` per clip.

> **`Streaming` is the wrong answer for a clip that plays many times at once.** It is the right
> one for music and long ambience — one or two streams, almost no resident memory. A short hazard
> or pickup clip set to `Streaming` opens a read per voice instead, so a moment with a dozen of
> them overlapping turns a memory saving into disk pressure and a late first frame of sound. Short
> and frequent stays `DecompressOnLoad`; occasional and medium is `CompressedInMemory`. And every
> `Streaming` clip wants `loadInBackground`, or the first play stalls the main thread.

Two properties are **not** on the sample settings and stay on the importer itself: `forceToMono`
and `loadInBackground`. `preloadAudioData`, `loadType`, `compressionFormat`, `quality` and
`sampleRateSetting` are all per-platform sample settings.

`defaultSampleSettings` covers every platform that has no override. Per-platform divergence
(22050 Hz on mobile, 44100 on desktop) needs `ai.SetOverrideSampleSettings("Android", s)`.

## Gotcha: `defaultSampleSettings` is a struct copy

`AudioImporterSampleSettings` is a **struct**, so the property getter hands back a copy. The
direct form does not even compile — C# rejects assigning into the return value of a property
(`CS1612`, a language rule, not a Unity one) — so the mistake that
actually ships is the half-done version:

```csharp
var s = ai.defaultSampleSettings;
s.loadType = AudioClipLoadType.Streaming;
// … and no assign-back: the importer keeps its old settings, silently, and the reimport looks fine
```

Edit the local, then **assign it back**. This is the silent half of the `preloadAudioData` trap:
the compiler shouts about the obsolete member and says nothing about the dropped copy.

## Gotcha: the obsolete `preloadAudioData` is an ERROR, and it takes the whole project down

Writing `ai.preloadAudioData = …` on Unity 6 does not warn. It fails the compile:

```
Assets/Scripts/Editor/AudioImportRules.cs(24,13): error CS0619:
'AudioImporter.preloadAudioData' is obsolete: 'Preload audio data has been moved to
AudioImporter.SampleSettings as a per platform local setting'
```

The blast radius is what makes this worth its own heading. Editor scripts compile as one
assembly, so a single obsolete line in one import rule stops **every** unrelated headless entry
point in the project:

```
Aborting batchmode due to failure: Scripts have compiler errors.
```

Any `-executeMethod` run — a sprite metadata pass, a content scaffold — exits 1 for this reason,
whether or not it touches audio. If a headless Unity command starts failing right
after audio work, read the compile errors before debugging the method you invoked.

The fix is the local-copy form above: `s.preloadAudioData = !music;`.

## Delivery format: hand Unity a source, not the shipping codec

Unity re-encodes whatever you give it. Pre-encoding a deliverable to the format you want in the
build means decoding lossy audio and re-encoding it — the extra generation buys nothing, and it
puts an external encoder into a pipeline that did not need one. (A local `ffmpeg` build can lack a
Vorbis encoder entirely, which turns a wasted step into a broken one.) Ship a source file
and let the postprocessor pick the runtime codec.

Which source format is a repo-size decision, and the honest answer differs by clip length — e.g.
for music of nine tracks at 141–180 s each:

| Content | Delivered as | Why |
|---|---|---|
| SFX, UI, short stingers | 44.1 kHz mono WAV | lossless, small anyway; a second lossy generation buys nothing |
| Music beds, 2–3 minutes each | 160 kbps mono MP3 | nine tracks ≈ 30 MB in LFS; 44.1 kHz mono WAV is 705.6 kbps, so the same nine would be ≈ 130 MB |

This qualifies the usual "sources must be WAV or AIFF" rule rather than overturning it. The rule
is right about quality: importing an MP3 means Unity's Vorbis encoder is re-compressing an
already-compressed signal, and the loss is not recoverable. Accept that generation only for long
music where repo weight dominates, keep SFX lossless, and say which way you went.

Before the first commit of a **new** binary extension, confirm LFS actually matches it — patterns
are per-extension, and adding `.mp3` to a repo whose `.gitattributes` only lists `.wav`/`.ogg`
commits a 30 MB blob into Git history:

```bash
git check-attr filter Assets/Audio/Shared/bgm_lobby.mp3    # want: filter: lfs
```

Version-control setup itself (LFS on day one, `.meta` policy) is `unity-new-project`.

## Verify without a device

Import settings are testable in EditMode, because the imported `AudioClip` reports what actually
happened rather than what the importer was asked for:

```csharp
foreach (var clip in ClipsReferencedByTheCatalog())
{
    Assert.AreEqual(1, clip.channels,      $"{clip.name}: must be mono");
    Assert.AreEqual(44100, clip.frequency, $"{clip.name}: must be 44.1 kHz");
}
```

This catches both ends: a source file that was delivered stereo or at the wrong rate, and a
postprocessor that stopped matching the path (a folder rename, a file added one level up). It
does not cover `loadType`, `compressionFormat` or `quality` — those are importer state, not clip
state, and need `AssetImporter.GetAtPath` to read back.

## Where the audit stops, and what measures the rest

An import audit changes what the importer reports. Two things it cannot tell you, and neither is
worth guessing at:

- **What the clips actually cost at runtime.** The **Memory Profiler package** lists resident
  `AudioClip`s by byte cost on the device that loaded them, which is the number that settles an
  argument about `loadType`. Point at it rather than extrapolating from importer figures.
- **What the mixer costs per frame.** The **Profiler's Audio module** shows DSP CPU and the voice
  count while the game runs. If a mixer restructure was the point, that is the before/after;
  frame-time windows either side of the change are `unity-profiling`.

Neither runs headless with anything useful to say, so both are a hand-back: name the tool, name
the number to look at, and say which of your changes it would confirm.
