---
name: unity-ios-build
description: >-
  Take a Unity project to an app RUNNING on a real iPhone or iPad from a
  terminal, and prove it: headless iOS build, the generated Xcode project,
  signing with what this Mac actually has, devicectl install, launch with the
  console attached. Load for "build for iOS", "run it on my iPhone", "No Account
  for Team", "No profiles for … were found", "is Xcode managed", "which team
  id", "how do I read the iOS log", "it launches and nothing happens", "pull a
  file off the iPhone", or writing a native .mm plugin ("cannot use @try",
  "DllImport __Internal"). Android artifacts are unity-android-release; driving
  the running app is unity-device-testing; CLI and licences are unity-cli.
---

# unity-ios-build — from a Unity project to a process on the phone, without opening Xcode

An iOS build is **two builds and a delivery**, and each one fails in its own vocabulary:

> **Unity builds an Xcode project, not an app.** Exit 0 means a folder of generated C++ exists.
> Nothing has been compiled for the device, nothing has been signed.
>
> **`xcodebuild` builds the app.** This is where a native plugin first meets a compiler, and where
> signing is decided — by what this Mac holds, not by what `PlayerSettings` says.
>
> **`devicectl` delivers and launches it.** It is also the only log channel you have. There is no
> screenshot verb; what the app prints is what you know.

So "it built" is three separate claims. Make each one separately, and read each one back.

---

## The pipeline, and what proves each stage

| Stage | Command | Proof it happened |
|---|---|---|
| 1. Unity → Xcode project | `Unity -batchmode -quit -buildTarget iOS -executeMethod IosBuildScript.Build` | `<out>/Unity-iPhone.xcodeproj` exists **and is newer than the run** — the script deletes the old one first |
| 2. Compile gate, no device, no signing | `xcodebuild … -sdk iphoneos CODE_SIGNING_ALLOWED=NO build` | `** BUILD SUCCEEDED **` — native plugins compile, frameworks link |
| 3. Signed build | `xcodebuild … -destination id=<device> -derivedDataPath <dd> CODE_SIGN_STYLE=Automatic DEVELOPMENT_TEAM=<team>` | the log names the `Signing Identity` and `Provisioning Profile` it chose; `<dd>/Build/Products/Debug-iphoneos/*.app` exists |
| 4. Install | `xcrun devicectl device install app --device <id> <app>` | prints `bundleID:` |
| 5. Launch + log | `xcrun devicectl device process launch --device <id> --console --terminate-existing <bundle>` | the app's own first log line, in your file |

`templates/ios-run.sh` runs these as subcommands and refuses to continue past a stage that did
not produce its proof.

```bash
Tools/ios-run.sh doctor        # identities, profiles, devices — and which team+profile covers which device
Tools/ios-run.sh build         # stage 1 (deletes the old Xcode project first)
Tools/ios-run.sh compile       # stage 2 — run this before you own a device, and in CI
Tools/ios-run.sh install       # stages 3 + 4
Tools/ios-run.sh launch --console /tmp/ios.log      # stage 5, log streamed to a file
Tools/ios-run.sh pull Documents/run.json ./out/     # a file out of Application.persistentDataPath
Tools/ios-run.sh native-sync   # edited a .mm? 30 s, not 6 min — reference/native-plugins.md
```

**Run `doctor` before the first signed build on any Mac.** Signing is decided by the intersection
of three things on disk — a certificate with its private key, a provisioning profile that embeds
that certificate, and that profile listing the device. `doctor` prints the intersection; guessing
at it costs a full build per guess.

## Ready-made templates

| File | Where it goes |
|---|---|
| `templates/IosBuildScript.cs` | `Assets/Editor/` (or any Editor assembly) |
| `templates/IosPostprocess.cs` | `Assets/Editor/`, or a package's `Editor/` — edit the two tables at the top |
| `templates/ios-run.sh` | `Tools/` (anywhere inside the project) |
| `templates/ios-env.example` | copy to `.ios-env` beside the script, gitignore it |

## Load what the situation needs

| The situation | Read |
|---|---|
| Writing the build entry point; plist keys and frameworks; a build that exits 0 and produced nothing; `ProjectSettings` changed after a build | `reference/headless-build.md` |
| "No Account for Team", "No profiles for … were found", "is Xcode managed", "does not support provisioning profiles", which team id is real | `reference/signing-from-the-terminal.md` |
| Device shows `unavailable`; installing; reading the log; the app launches and then says nothing; pulling files back | `reference/install-launch-console.md` |
| Writing a `.mm` plugin, its `.meta`, the C# side; `@try` will not compile; iterating native code without rebuilding in Unity | `reference/native-plugins.md` |
| Exit 198, "No valid Unity Editor license", a second Unity instance on the same project | skill `unity-cli` |
| The app is running — now drive it, assert on its log, ask a human for a physical action | skill `unity-device-testing` |
| The same project, as a signed Android artifact | skill `unity-android-release` |
| It misbehaves in the Editor too | skill `unity-debug` |

## Discipline

- **Delete the expected output before each stage.** A stale `.xcodeproj` or `.app` reads as
  success. Branch on the artifact existing and being new, never on an exit code.
- **The id in a certificate's name is a person, not a team.** `Apple Development: Name (XXXXXXXXXX)`
  carries the member id. The team is the certificate's `OU` and the profile's `TeamIdentifier`.
  Passing the member id as `DEVELOPMENT_TEAM` gives *"No Account for Team"*.
- **Do not pass `-allowProvisioningUpdates` on a Mac with no Xcode account.** It asks Xcode to
  talk to Apple and fails; without it, automatic signing happily uses a cached managed profile.
- **The compile gate is free — use it.** `CODE_SIGNING_ALLOWED=NO` needs no device, no team, no
  profile. Every native-plugin error shows up there. Never discover a `.mm` typo at stage 3.
- **A launch that goes quiet is waiting for a human.** `applicationWillResignActive` right after
  launch means a system permission sheet is up. Development builds raise *Local Network* as well as
  your own permission — that is two taps, and the app's log is stalled until both.
- **One Unity at a time per project**, and after a headless build read `git diff ProjectSettings/`:
  the build method writes the bundle id, team and signing mode into `ProjectSettings.asset`.
  Decide whether that diff is yours before it is committed.
- **Before trusting a native-sync run, `diff -q` the package source against the copy in the Xcode
  project.** The next Unity build regenerates that copy from the package; an edit made only in the
  Xcode project is an edit you are about to lose.
- **Keep identifiers out of the repo.** Team id, device id and bundle id live in a gitignored
  `.ios-env`; the scripts read them, they never appear on a committed command line.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| App Store / TestFlight: distribution certificates, App Store Connect, review, export options | Not covered — this skill ends at a development-signed app running on a device you hold |
| Android APK / AAB | `unity-android-release` |
| Driving the running app, asserting on its log, human-in-the-loop physical steps | `unity-device-testing` |
| Installing editors and modules, licences, CI wiring | `unity-cli` |
| Behaviour that is also wrong in the Editor | `unity-debug` |
| WebGL / WebGPU | `unity-web-release` |

## Related skills

`unity-device-testing` once the process is up · `unity-android-release` for the other phone ·
`unity-cli` when Unity itself will not start · `unity-new-project` for bundle id and asmdef
decisions made on day one.
