# "It built" is not "it runs"

The build report says Succeeded. That statement covers compilation and packaging, and nothing else:
not whether it is signed, not with what, not which permissions it ended up declaring, not whether it
contains code for the CPU you are shipping to. All four are readable from the artifact in seconds,
and all four have been wrong on a build that reported success.

Unity bundles the tools, so there is nothing to install:

```bash
SDK="/Applications/Unity/Hub/Editor/<version>/PlaybackEngines/AndroidPlayer/SDK"
BT="$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)"
"$BT/aapt"       # merged manifest, ABIs, identity
"$BT/apksigner"  # who signed it
"$SDK/platform-tools/adb"
```

The editor's `AndroidPlayer` module carries build-tools, platforms, the NDK and an OpenJDK, so no
separate Android SDK installation is needed for any of the commands below. Derive the editor path
from `ProjectSettings/ProjectVersion.txt` rather than hardcoding a version, and note that
`PlaybackEngines/` sits **beside** `Unity.app`, not inside it — from the `Unity` binary that is four
`dirname` levels up, which is the easy off-by-one.

## Identity, permissions and ABIs

```bash
B="$("$BT/aapt" dump badging app.apk)"
grep -o "package: name='[^']*' versionCode='[^']*' versionName='[^']*'" <<<"$B"
grep -E "sdkVersion|targetSdkVersion" <<<"$B"      # what the artifact really targets
grep -o "uses-permission: name='[^']*'" <<<"$B" | sort -u
grep -o "native-code: .*" <<<"$B"
```

The `sdkVersion` / `targetSdkVersion` line is the only proof that a pinned `targetSdk` survived into
the artifact — and if it did not, a 4 KB-aligned native library is now a crash on 16 KB-page devices
(`player-settings-android.md`).

**Read the permissions from the artifact, never from your own manifest.** A build whose project
declares none can still ship seven, e.g.:

```
android.permission.BLUETOOTH                        ← nobody expected this one
android.permission.FOREGROUND_SERVICE
android.permission.FOREGROUND_SERVICE_MICROPHONE    ← store scrutiny magnet
android.permission.INTERNET                         ← nor this one
android.permission.MODIFY_AUDIO_SETTINGS
android.permission.RECORD_AUDIO
<package>.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION
```

They arrive by manifest merging from plugins, packages and the engine. Every one of them is
something you sign a declaration about on the store listing, so the merged output is the only
honest source for that form.

Another example: a project with no manifest of its own can ship `RECORD_AUDIO`,
`FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MICROPHONE`, `FOREGROUND_SERVICE_CONNECTED_DEVICE` — all
from one plugin `.aar` — plus `INTERNET`, in an app that uploads nothing: **`INTERNET` comes from
the engine**, because Unity's `UnityWebRequest` modules are present in the build. Know which of
the two sources a surprise permission came from before you write the justification, because "a
dependency needs it" and "the engine always adds it" are different answers on the form.

`native-code:` must contain every ABI you target. Empty or missing means IL2CPP produced nothing
for it — that ships and dies on launch.

## Who signed it

```bash
"$BT/apksigner" verify --print-certs app.apk
```

```
Signer #1 certificate DN: C=US, O=Android, CN=Android Debug     ← Play will reject this
Signer #1 certificate DN: CN=<App>, O=<Org>, C=<CC>             ← your upload key
```

An unsigned or debug-signed release is a build that looks entirely successful right up until the
store refuses it. Have the script name the debug key out loud rather than printing a cheerful tick.

Debug-signing is not just a store problem, and it is not reversible on a device: a later
release-signed build **cannot update** an installed debug-signed one — Android refuses the install
because the signer changed, so every tester has to uninstall first, losing their save data. That is
survivable for the first internal APK and expensive once a build is in more than a few hands, which
is the argument for creating the keystore before the first artifact rather than after.

## App bundles

`aapt` cannot read an AAB. Verify what you can and say what you cannot:

```bash
unzip -l app.aab | grep -q 'base/manifest/AndroidManifest.xml'   # it is at least a bundle
```

Full inspection needs `bundletool`. Until you have it, upload to an internal track and read the
merged result Play shows you.

## How big is it, really

```bash
du -h app.apk
```

That is the number, and the build report is not: `BuildReport.summary.totalSize` counts symbols
and intermediates rather than the shipped file — e.g. **844 MB** for a **69 MB** APK (IL2CPP/ARM64).
Log the report's number as a diagnostic if you like, but never quote it as a download size — see
`size-and-stripping.md` before trying to reduce it.

## Then install it and play it

```bash
adb install -r app.apk
```

IL2CPP stripping faults, missing shader variants and native ABI mismatches are all invisible until
launch. An `adb devices` entry marked `offline` is a stale wireless pairing, not a device.

If it launches but renders wrong, go to `device-triage.md` — the fault is narrowed by what still
looks correct, and a build-and-hope loop costs minutes per attempt.
