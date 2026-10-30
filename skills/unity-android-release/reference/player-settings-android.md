# The Android Player Settings you do not get to choose freely

> Part of the `unity-android-release` skill. Read before promising a `minSdk`, before raising
> `targetSdk`, and before the first artifact carries an icon.

Two of the Android settings people treat as project preferences are not preferences at all: the
editor sets a floor under one, and a third-party native library sets a ceiling on the other.

## Apply them from one idempotent code path

Everything settable from the API belongs in a single `ConfigureAndroid`-style Editor method —
application id on every platform, scripting backend, architecture, `minSdk`/`targetSdk`, stripping,
colour space, orientation, icons, `EditorSettings.serializationMode = ForceText`, visible meta
files — so there is no second settings asset that was never in effect (`device-triage.md`: a
change made on a dormant asset ships nothing). Such a method is synchronous, so it is safe
under `-batchmode -quit`:

```bash
Unity -batchmode -quit -projectPath . -buildTarget Android \
      -executeMethod <Namespace>.ProjectSetup.ConfigureAndroid -logFile -
```

The trap that comes with it: **a hardcoded version string in that method silently reverts a version
bump you made in the asset.** See `signing-and-versioning.md` — grep for `bundleVersion` before
believing any bump.

## minSdk: the floor is 25 on Unity 6000.4 (26 from 6000.5), not 23

Unity 6000.4 does not take `PlayerSettings.Android.minSdkVersion` below `AndroidApiLevel25`: a
lower value does not survive, and `ProjectSettings.asset` records `AndroidMinSdkVersion: 25`. Note
that the enum is *not* the guard — `AndroidApiLevel16` through `AndroidApiLevel24` are still
declared in the editor's `UnityEditor.dll`, so assigning 23 compiles cleanly and throws nothing —
the value simply is not what ships. From 6000.5 the floor is API 26, so the same clamp lands on
`AndroidApiLevel26` (repo `VERSIONS.md`). Read the floor back from `ProjectSettings.asset`, or from the
artifact (`artifact-verification.md`), not from the line you wrote. Any plan, README or store
answer that says "API 23" or "Android 6" is therefore not achievable on this editor line; correct
the document rather than the setting. **On another editor line, find the floor the same way:** set
it, read `PlayerSettings.Android.minSdkVersion` back, and ship that value — and give a Gradle
template that claims to push it lower the same test, reading `sdkVersion` off the artifact.

## targetSdk is set by the store, so your native libraries must meet it

From Android 15, an app with `targetSdk >= 35` fails to load native libraries that are aligned to
4 KB pages on devices with 16 KB pages. Play requires every new app and update to target a recent
API level (above 35; the current level and date are in the repo's `VERSIONS.md`) and requires
16 KB page support from every app that targets 35 or higher. So **a 4 KB-aligned prebuilt `.so`
is a blocker for a store build**: the library is rebuilt at 16 KB or replaced. Lowering
`targetSdk` to 34 no longer gets past the store.

Set `targetSdk` explicitly to the level Play requires, not Auto (Auto follows whichever SDKs the
build machine has installed):

```csharp
// Play's current target-API requirement (VERSIONS.md). A cast, because an older Editor's enum
// may not name the level yet. Every .so must be 16 KB aligned (llvm-readelf -l → Align 0x4000)
// or it fails to load on 16 KB-page devices.
PlayerSettings.Android.targetSdkVersion = (AndroidSdkVersions)36;
```

A pin at 34 is still a way to keep a **sideloaded or internal** build running while the library is
rebuilt. Write the reason beside it, and never send that artifact to a store track:

```csharp
// Internal builds only: <plugin>'s .so files are 4 KB aligned (Align 0x1000) and fail to load on
// 16 KB-page devices under targetSdk >= 35. Play rejects this target. Remove when the library
// ships 0x4000.
PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevel34;
```

### The check, before you choose

Unity ships the NDK, so the tool is already on the machine:

```bash
NDK="<editor>/PlaybackEngines/AndroidPlayer/NDK"
READELF="$(ls "$NDK"/toolchains/llvm/prebuilt/*/bin/llvm-readelf | head -1)"

unzip -o <plugin>.aar 'jni/arm64-v8a/*' -d /tmp/aar
"$READELF" -l /tmp/aar/jni/arm64-v8a/lib*.so | awk '$1=="LOAD"{print $NF}' | sort -u
```

| Output | Means |
|---|---|
| `0x4000` | 16 KB aligned — the store's `targetSdk` is available to you |
| `0x1000` | 4 KB aligned — not shippable to Play: rebuild or replace the library (a pin at 34 serves internal builds only) |

A UPM package's `.aar` is wherever that package put it under `Library/PackageCache/<pkg>/` (e.g.
`Runtime/Plugins/Android/`), and a `file:` dependency's lives outside the project
entirely — the same blind spot that makes an ABI scan pass by finding nothing
(`build-automation.md`).

The skill's `templates/build-android.sh` runs exactly this check on every `.aar` it finds. Against
a project with a 4 KB-aligned plugin it prints:

```
▸ Native plugins
  ✓ <plugin>.aar carries arm64-v8a
  ! libnative_plugin.so is 4 KB aligned (LOAD 0x1000) — needs 0x4000 for 16 KB-page devices
  ! libvendor_engine.so is 4 KB aligned (LOAD 0x1000) — needs 0x4000 for 16 KB-page devices
```

In `preflight` it refuses when `targetSdk` is 35+ or left on Auto with a 4 KB library present,
which is the combination that ships a crash. With `targetSdk` pinned to 34 it only warns: treat
that warning as a stop for any store build, because Play rejects the target.

### The real fix belongs upstream

The library is rebuilt with `-Wl,-z,max-page-size=16384` (NDK r28 makes that the default), then
re-checked with the same command showing `0x4000`. Until then the project has no store build:
record that as a release blocker with the check attached. An internal pin at 34 that outlives its
reason is how a crash reaches the subset of devices with 16 KB pages the day someone raises
`targetSdk` because a store console asked them to.

Then confirm what actually shipped, from the artifact rather than the setting:

```bash
"$BT/aapt" dump badging app.apk | grep -E "sdkVersion|targetSdkVersion"
```

## Launcher icons, set from code

Icons are the one Player Setting where a silent mistake is visible to every user, and the API's
argument order is where it happens.

```csharp
var kind    = UnityEditor.Android.AndroidPlatformIconKind.Adaptive;
var icons   = PlayerSettings.GetPlatformIcons(NamedBuildTarget.Android, kind);
foreach (var i in icons) i.SetTextures(background, foreground);   // BACKGROUND FIRST
PlayerSettings.SetPlatformIcons(NamedBuildTarget.Android, kind, icons);
```

Reversing those two arguments ships an inverted icon and throws nothing. `Round` and `Legacy` kinds
take a single texture, `SetTextures(legacy)`.

Geometry that works:

| Source | Size | Content |
|---|---|---|
| adaptive foreground | 432×432 | artwork at ~66% of the canvas, centred, transparent elsewhere — the adaptive safe zone, since the launcher masks and parallaxes it |
| adaptive background | 432×432 | flat colour |
| legacy / round | 512×512 | artwork at ~82% over a rounded rectangle |

One texture per kind is enough: Unity generates every density from it, and `aapt dump badging`
shows `application-icon-*` pointing at the adaptive XML. Two practical notes:

- **Skip icon assignment entirely when a source file is missing**, rather than applying half a set —
  a half-applied icon set is harder to notice than none.
- **Keep the icon sources out of any folder your importer rules act on.** For example, keep them in
  `Assets/AppIcon/` when an `AssetPostprocessor` converts everything under `Assets/Art/` into
  sprites, which is the wrong texture type for an icon source.

## A 3D game's baseline, and the quality tiers that go with it

What a 3D tennis game for phones set on day one, from one re-runnable setup method, before it had
a test device:

| Setting | Value | Why, and who decided |
|---|---|---|
| Scripting backend, architecture | IL2CPP, ARM64 only | Required by Play for 64-bit; IL2CPP also removes the Editor's first-use JIT stalls, which the Editor still needs a warmup for (`unity-debug` → `reference/unity-gotchas.md` §23) |
| `minSdk` | 29 | Recorded as an **open question for the person**: it drops devices without Vulkan 1.1. A minSdk is a market decision, not a technical default |
| `targetSdk` | Play's required level, set explicitly | Not `Auto`: Auto follows whichever SDKs are installed on the build machine, so two machines build two targets. Check the current requirement (`VERSIONS.md`) before each release |
| Graphics APIs | Vulkan, then OpenGLES3; automatic selection off | So an Editor upgrade cannot change the default order |
| Quality tiers | Low, Medium, High, chosen per device | One URP asset per tier, written by the same setup method and read back in the log |

The three tiers, as first tuned in the Editor (numbers to re-tune on devices):

| Tier | Render scale, MSAA | Real-time shadows | Post-processing |
|---|---|---|---|
| High | 1.0, 4×, HDR | 2048, 52 m, 2 cascades, soft | Tonemapping, grading, light bloom |
| Medium | 0.85, 2× | 2048, 50 m, 1 cascade, hard; off in split screen (URP renders a shadow map per camera) | Tonemapping and grading |
| Low | 0.7, 2× | None; blob shadows only (the ball's shadow is a depth cue, so every tier keeps one) | Tonemapping and grading, FXAA |

**Skin weights: 4 bones on every tier, Android included.** The Low and Medium tiers first used
2 bones, a common mobile saving. Measured on the game's characters, 2 bones raised the share of
self-intersecting geometry by 0.6 to 0.9 percentage points, because the characters were skinned
for up to 4 influences. The person chose 4 on all tiers. Measure your own rig in an extreme pose
before taking the saving (`unity-rigged-character`); and when a tier lowers it, it is a quality
setting (`QualitySettings.skinWeights`), so check it per tier in the setup method's read-back.

Without a device, every number above is an Editor number. Put "reference test devices: low,
mid and high" in the open questions on day one; the tiers are a guess until they exist.
