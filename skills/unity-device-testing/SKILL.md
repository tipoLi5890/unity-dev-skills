---
name: unity-device-testing
description: >-
  Run acceptance tests on a REAL Android or iOS device from a terminal: an agent
  drives, a human does only the physical part. A probe scene that logs one
  tagged line per state change, an adb / devicectl driver that asserts on those
  lines, system dialogs tapped for you, files pulled back, and three exit codes
  that separate a real failure from a broken harness. Load for "test it on the
  phone", "unplug / replug / background it and check", "the screenshot is
  black", "adb lost the device", "how do I read logs from an iPhone", "passes
  once, fails the next run", "compare two devices". Building the artifact is
  unity-android-release or unity-ios-build; the editor-side harness is
  unity-play-harness.
---

# unity-device-testing — the phone is an instrument; prove it before you read it

A device run has three parties: the **app**, the **driver** (your script), and usually a **human**
who plugs, unplugs, waves or taps. Any of the three can be the thing that failed, and only one of
them is the thing you were testing.

> **"It didn't work on the phone."** Says nothing yet. The screen may have been off, the old build
> may still be installed, another app may hold the hardware, adb may have dropped, or the human did
> a different thing from the one you asked for. Every one of those produces the same symptom as a
> real bug.

So the rule is the one `unity-debug` applies to the editor, moved to hardware: **check the
instrument first**, and make the run say which of the three parties failed.

## The four parts

| Part | Done when |
|---|---|
| **Probe** | A scene in the project logs `[Probe] state A -> B`, `[Probe] <event> …` and one `[Probe] diag k=v …` line per second, and shows the same on screen — `reference/device-probe.md` |
| **Driver** | A script installs the artifact, launches it, and waits on those lines with a timeout per step; exits **0** all green, **2** a step failed, **3** the harness failed — `reference/android-driver.md` · `reference/ios-driver.md` |
| **Human protocol** | Each physical action is one instruction, armed *before* it is asked for, and **detected from the device**, never taken on the human's word — `reference/human-in-the-loop.md` |
| **Evidence** | Every verdict quotes the log lines and their timestamps; every surprise gets a control run before it gets a theory — `reference/verdicts-and-evidence.md` |

## Pre-flight: five things that look like bugs and are not

Run these before the first step of every run. Each is one command; each has cost a full round trip
to someone who skipped it.

| Check | Android | iOS |
|---|---|---|
| The device is reachable *now* | `adb -s <serial> get-state` in a retry loop — a headless Unity build restarts the adb server and a Wi-Fi device vanishes for 10–30 s | `xcrun devicectl list devices` → State must be `connected`/`available`, not `unavailable` (locked, off-network, or never paired) |
| The screen is on | `input keyevent KEYCODE_WAKEUP`, `wm dismiss-keyguard`, then `dumpsys power \| grep mWakefulness=Awake`. **A black screenshot with `mWakefulness=Dozing` is not an app bug** | Ask the human; there is no query. The console shows `applicationWillResignActive` when the screen locks |
| It is *your* build | `dumpsys package <pkg> \| grep lastUpdateTime` against the artifact's mtime; install with `-r -g` every run | Reinstall every run; `devicectl device install app` prints the bundle id it replaced |
| Nothing else holds the hardware | `am force-stop` every other app that uses the same hardware (camera, Bluetooth, sensors) — a backgrounded app keeps its native handle | Same idea: terminate the previous instance with `--terminate-existing` |
| The thing a human will change is in the state you think | Read a **present-tense** source — `dumpsys battery \| grep 'powered: true'` for a charger, `settings get …` for a toggle — never a dump that also lists history | The probe lists inputs at start; assert on that line |

## Two platforms, two log channels

| | Android | iOS |
|---|---|---|
| Logs | `adb logcat -c` then poll `logcat -d` — never a long-lived `logcat`, it dies with the adb server | `devicectl device process launch --console` redirected to a file; that file **is** the log. Unity `Debug.Log` and native `NSLog` both land in it |
| Screenshots | `adb exec-out screencap -p` | None from the CLI. The probe's log line is the readout — design it so a screenshot is never needed |
| Tap a system dialog | Detect it by focus (`dumpsys window \| grep mCurrentFocus`), tap by coordinates — and **`wm size` is the physical portrait size in every rotation** (`reference/android-driver.md`) | Impossible. A system sheet shows as `applicationWillResignActive` right after launch; the human taps it |
| Pull a file the app wrote | `adb pull /sdcard/Android/data/<pkg>/files/…` | `devicectl device copy from --domain-type appDataContainer …` |
| Release builds strip logs | R8 `-assumenosideeffects` removes `Log.*` from an `.aar`; keep `i/w/e` or your tags never appear | — |

## Load what the situation needs

| The situation | Read |
|---|---|
| Writing the scene that makes a device run readable; what a log line must carry; mode buttons; dumping raw data to a file | `reference/device-probe.md` |
| adb over Wi-Fi, waking the screen, polling logcat, tapping permission dialogs, rotation, detecting physical unplug, pulling files | `reference/android-driver.md` |
| Reading an iPhone from a terminal: devicectl states, the console as the only log, system sheets, pulling files, relaunching | `reference/ios-driver.md` |
| A step needs a person: what to ask, in what order, how to verify they did it, how to batch | `reference/human-in-the-loop.md` |
| A run surprised you; one device counts and the other does not; deciding between "bug", "harness" and "protocol" | `reference/verdicts-and-evidence.md` |
| Building and signing the APK/AAB you are about to install | `unity-android-release` |
| Getting a Unity project onto an iPhone at all: Xcode project, signing, install, console | `unity-ios-build` |
| The probe idea in the editor: one-line snapshots, situations, journeys | `unity-play-harness` |
| Whether a results file or an exit code can be believed; PlayMode runs | `unity-debug` |
| Frame time on the device | `unity-profiling` |

## Ready-made templates

| File | Where it goes |
|---|---|
| `templates/DeviceProbe.cs` | `Assets/` of a dev/host project, on one GameObject in a `DeviceProbe` scene. Rename the tag and fill the three marked hooks |
| `templates/device-acceptance.sh` | `Tools/`. Android driver: pre-flight, install, steps, dialog tapper, `--wait` for unattended physical steps |
| `templates/ios-acceptance.sh` | `Tools/`. iOS driver over a console log file: launch, wait on lines, prompt or `--wait`, pull files |

```bash
Tools/device-acceptance.sh -s <serial> --apk Builds/probe.apk          # interactive: press Enter after each physical step
Tools/device-acceptance.sh -s <serial> --apk Builds/probe.apk --wait   # unattended: watches the device for the physical change
Tools/ios-acceptance.sh --device <udid> --bundle com.example.probe --wait
```

## Discipline

- **Exit 0 / 2 / 3, and mean it.** 2 is a verdict about the app. 3 is "I could not run the test" —
  no device, screen off, build missing, adb died. A harness failure reported as a test failure
  sends someone to debug code that was never exercised.
- **Time assertions from the physical event, not from when the human says "done".** Poll the
  device for the change (the charger line flips, the app's own event line appears), then start the clock.
- **Clear the log at the start of each step** and assert only on lines after it. A pattern that
  matched the previous step's output is the most common false green.
- **One variable per run.** A new build, a new cable position and a new mode in the same run
  cannot be told apart afterwards.
- **A surprise gets a control before it gets a theory.** Swap the two phones' positions, run the
  same stimulus on the other OS, or repeat with the previous build. One round trip each, and each
  removes a whole class of explanation.
- **The first seconds lie.** Counters read 0 and averages read empty until the first full window;
  never conclude from a probe's first two diag lines.
- **Put the fix for a harness lesson in the script**, not in your memory: the rotation-aware tap,
  the retry loop after a build, the presence check. The next run is by someone who was not here.
- **Leave the device as you found it**: restore `screen_off_timeout`, force-stop the probe, and
  say which steps were *not* run.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Building, signing, reading back an Android artifact | `unity-android-release` |
| Unity → Xcode → signed → installed on an iPhone | `unity-ios-build` |
| Probes, situations and journeys inside the editor | `unity-play-harness` |
| Trusting a results file, exit codes, PlayMode side effects | `unity-debug` |
| Frame-time windows and counters on the device | `unity-profiling` |
| Device farms, cloud labs, store review testing | Not covered — this is one phone on your desk |

## Related skills

`unity-play-harness` for the same observability idea inside the editor · `unity-debug` for harness
trust · `unity-android-release` and `unity-ios-build` for the artifact you install.
