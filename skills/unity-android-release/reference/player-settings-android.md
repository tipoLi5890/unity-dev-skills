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

## minSdk: the floor is 25 on Unity 6000.4, not 23

Unity 6000.4 does not take `PlayerSettings.Android.minSdkVersion` below `AndroidApiLevel25`: a
lower value does not survive, and `ProjectSettings.asset` records `AndroidMinSdkVersion: 25`. Note
that the enum is *not* the guard — `AndroidApiLevel16` through `AndroidApiLevel24` are still
declared in the editor's `UnityEditor.dll`, so assigning 23 compiles cleanly and throws nothing —
the value simply is not what ships. Read the floor back from `ProjectSettings.asset`, or from the
artifact (`artifact-verification.md`), not from the line you wrote. Any plan, README or store
answer that says "API 23" or "Android 6" is therefore not achievable on this editor line; correct
the document rather than the setting. **On another editor line, find the floor the same way:** set
it, read `PlayerSettings.Android.minSdkVersion` back, and ship that value — and give a Gradle
template that claims to push it lower the same test, reading `sdkVersion` off the artifact.

## targetSdk is decided by your native libraries, not by you

From Android 15, an app with `targetSdk >= 35` fails to load native libraries that are aligned to
4 KB pages on devices with 16 KB pages, and Play requires 16 KB compatibility for new apps
(`store-submission.md` — confirm the current wording before you plan around it). So **the
alignment of every prebuilt `.so` you ship decides the highest `targetSdk` you may set.**

For example, when the `LOAD` segments of the `.so` files inside a vendored SDK's `.aar` report
`Align 0x1000` (4 KB), pin `targetSdk` to 34 in code — Auto resolves to the highest installed
level, e.g. 36 — with the reason in a comment beside it:

```csharp
// Pinned, not Auto: <plugin>'s .so files are 4 KB aligned (llvm-readelf -l → Align 0x1000),
// which fails to load on 16 KB-page devices under targetSdk >= 35. Unpin when the library
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
| `0x4000` | 16 KB aligned — `targetSdk` 35+ is available to you |
| `0x1000` | 4 KB aligned — pin `targetSdk` to 34 until the library is rebuilt |

A UPM package's `.aar` is wherever that package put it under `Library/PackageCache/<pkg>/` (e.g.
`Runtime/Plugins/Android/`), and a `file:` dependency's lives outside the project
entirely — the same blind spot that makes an ABI scan pass by finding nothing
(`build-automation.md`).

The skill's `templates/build-android.sh` runs exactly this check on every `.aar` it finds. Against
a project with a 4 KB-aligned plugin it prints:

```
▸ Native plugins
  ✓ <plugin>.aar carries arm64-v8a
  ! libusb1.0.so is 4 KB aligned (LOAD 0x1000) — needs 0x4000 for 16 KB-page devices
  ! libvendor_engine.so is 4 KB aligned (LOAD 0x1000) — needs 0x4000 for 16 KB-page devices
```

In `preflight` it warns rather than refuses while `targetSdk` is pinned to 34 — it refuses only
when `targetSdk` is 35+ or left on Auto, which is the combination that ships a crash.

### The real fix belongs upstream

The library is rebuilt with `-Wl,-z,max-page-size=16384` (NDK r28 makes that the default), then
re-checked with the same command showing `0x4000` before the pin comes off. Record the pin as an
open question with the check attached, not as a preference — otherwise the next person raises
`targetSdk` because a store console asked them to, and the crash appears only on the subset of
devices with 16 KB pages.

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
