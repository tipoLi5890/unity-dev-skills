---
name: unity-android-release
description: >-
  Take a Unity game from "it works in play mode" to a signed, installed,
  verified Android artifact, and diagnose it when the device disagrees with
  the editor. Load for "build an APK", "make an AAB for Play", "set up the
  build script", "keystore", "versionCode", "which permissions does my app
  actually declare", "which minSdk/targetSdk can I set", "16 KB page size",
  "adaptive launcher icon", or "it works in the editor but the phone shows
  garbage / crashes on launch / renders wrong". Ships a BuildScript and a
  shell driver that refuse rather than warn, and reads the artifact back with
  aapt/apksigner. Web builds are unity-web-release; the CLI's own surface is
  unity-cli.
---

# unity-android-release — build it, then prove it

Two claims are worth nothing on their own, and this skill exists to replace both with evidence:

> **"It built."** Says compilation and packaging finished. Not whether it is signed, not with what,
> not which permissions it declares, not whether it contains code for the CPU you ship to.
>
> **"I changed that setting."** Says a file on disk differs. Not that the file is the one the
> project actually loads — a dormant asset takes every change silently
> (`reference/device-triage.md`).

---

## Settings that are expensive to change later

Get these right before the **first** artifact leaves your machine.

- **IL2CPP + ARM64.** Play requires 64-bit; Mono and ARMv7 are dead ends. Strip Engine Code on;
  managed stripping starts Low until reflection users are annotated in `link.xml`, because
  over-stripping only shows up in the built player.
- **Package name is store identity and is locked once published.** Unity's template default
  (`com.DefaultCompany.<Project>`) reaching a store is unrecoverable. Set it on every platform.
- **`versionCode` is monotonic per artifact handed to anyone**, not just per store upload.
- **Keystore before the first release build**, backed up outside the repo, password with it.
- **`minSdk` has a floor and `targetSdk` has a ceiling, and neither is your preference.** Unity
  6000.4 would not take `minSdkVersion` below 25, so a plan promising "Android 6 / API 23" is
  already wrong; and a prebuilt `.so` aligned to 4 KB pages caps you at `targetSdk` 34, because
  from Android 15 a `targetSdk` 35+ app cannot load it on a 16 KB-page device. Check the alignment
  **before** promising a `targetSdk` — `reference/player-settings-android.md`.
- **Secrets arrive on stdin, never in `argv`.** A password expanded from an environment variable
  is still visible in the process list; CI must mask it in logs as well. `Tools/.build-env` stays
  gitignored and is read, not passed.

## Ready-made templates

`templates/` holds the working versions, project-agnostic — they discover the project, the Unity
version, the SDK and the plugins instead of hardcoding any of it:

| File | Where it goes |
|---|---|
| `templates/BuildScript.cs` | `Assets/Scripts/Editor/` |
| `templates/build-android.sh` | `Tools/` (or anywhere inside the project) |
| `templates/build-env.example` | copy to `.build-env` beside the script, gitignore it |

```bash
Tools/build-android.sh doctor       # resolve what is ACTUALLY in effect; builds nothing
Tools/build-android.sh preflight    # doctor + release gates; exit 1 if unshippable → a CI gate
Tools/build-android.sh test         # debug-signed APK for sideloading
Tools/build-android.sh release --apk --install
```

**Run `doctor` first, every time you are about to change a setting and draw a conclusion from it.**
It prints the render-pipeline asset the project genuinely loads (from `GraphicsSettings`), the
pinned graphics APIs, and every native `.aar`'s ABI and 16 KB page alignment, `file:` UPM
dependencies included — what each check does and why: `reference/build-automation.md`.

## The CLI can sign an Android build itself — when that is enough

`unity build` takes `--android-export-type apk|aab|android-studio-project`,
`--android-keystore-base64`, `--android-keystore-password`, `--android-key-alias`,
`--android-key-alias-password`, `--android-target-sdk-version`, `--android-version-code` and
`--android-symbol-type none|public|debugging` (check `unity build --help` on your CLI version). So
a one-line signed build is possible with no BuildScript at all.

| Use the CLI flags when | Use the committed script when |
|---|---|
| A throwaway or exploratory build | Anything anyone else will install |
| You are checking whether signing works at all | You need the gates: template package name, reused `versionCode`, missing ABI |
| Nothing depends on the result being reproducible | You want the artifact read back and a provenance record written |

Two things the flags do not change:

- **Secrets in `argv` are visible** — the CLI's own help says so. Read them from a gitignored
  env file; never expand them onto a command line, and mask them in CI logs.
- **`unity build` refuses a dirty tree by default** (there is an `--allow-dirty-build` to
  override it). Leave the default alone. A build from an uncommitted tree is not reproducible,
  and that is exactly the build someone will later ask you to reproduce.

## Load what the situation needs

| The situation | Read |
|---|---|
| Setting up a repeatable build; writing the script; shell traps that bite | `reference/build-automation.md` |
| `minSdk`/`targetSdk`, the 16 KB page-size rule, launcher icons from code | `reference/player-settings-android.md` |
| An artifact exists — is it signed, what does it declare, what ABIs? | `reference/artifact-verification.md` |
| Keystore, credentials, versionCode, build history, package name | `reference/signing-and-versioning.md` |
| **Works in the editor, wrong on the device** | `reference/device-triage.md` |
| APK vs AAB, symbols, Data Safety, the new-app testing gate | `reference/store-submission.md` |
| The artifact is too large; "works in the editor, missing on device" after stripping | `reference/size-and-stripping.md` |
| Shipping to the web instead of Android | skill `unity-web-release` |
| Runtime behaviour in the editor; screenshots; temporal faults | skill `unity-debug` |

## Native plugins: trust the merged output, not your settings

A UPM package's `.aar` merges its manifest, permissions and native libs at build time. When a
permission "isn't there" or appears unexpectedly, read the **merged** result out of the artifact —
never your own manifest.

The failure that passes every editor test and then kills the app on launch is an **ABI mismatch**:
the `.aar` has no `arm64-v8a` while you build ARM64-only. Check it before building, not after
installing — and make sure the check actually looked somewhere, because a `file:` UPM dependency
lives outside the project and a naive scan finds nothing and passes.

The same `.aar` also decides your `targetSdk`. Its `.so` files being aligned to 4 KB pages
(`llvm-readelf -l …| awk '$1=="LOAD"{print $NF}'` → `0x1000` rather than `0x4000`) means a
`targetSdk` 35+ build fails to load them on 16 KB-page devices — a crash that appears only on some
hardware. Pin `targetSdk` with the reason in a comment: `reference/player-settings-android.md`.

When a plugin needs custom Gradle (minSdk, dependencies), prefer a **Custom Main Gradle Template**
over hand-editing the export — exports are regenerated, templates persist.

## Discipline

- **Delete the expected artifact before building.** Unity exits 0 when it never started; a stale
  file then reads as success. Branch on the artifact existing, never on the exit code.
- **Refuse, do not warn**, for anything unrecoverable: template package name on a release, missing
  keystore, re-used `versionCode`, missing ABI. A warning in a build log is read by nobody.
- **Install it and play it.** IL2CPP stripping faults and shader-variant gaps are invisible until
  launch.
- **Quote the artifact's size from the file, never from the build report.** The report counts
  symbols and intermediates, so `BuildReport.summary.totalSize` can say 844 MB for a 69 MB APK.
  `du -h` is the download size (`reference/artifact-verification.md`).
- **Bisect one variable per round trip**, and say what each outcome would prove. A build plus an
  install plus someone playing it is expensive; reproduce in the editor first where you can.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| WebGL / WebGPU artifacts | `unity-web-release` |
| The `unity` CLI's own surface, licences, CI wiring | `unity-cli` |
| Why the game misbehaves in the editor too | `unity-debug` |
| Store listing copy, pricing, screenshots | Not a build problem |
| IAP and ad SDKs, and what they add to the manifest | `unity-monetization` |

## Related skills

`unity-new-project` for day-one decisions · `unity-debug` for runtime verification and screenshots
· `unity-game-ui` for the UI that survives the device's real viewing conditions.
