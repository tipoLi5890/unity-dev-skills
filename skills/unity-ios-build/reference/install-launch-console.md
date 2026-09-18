# Install it, launch it, and read the only log you have

`devicectl` (Xcode 15+) replaces the older third-party tools for everything except one thing it
does not do at all: **there is no screenshot verb.** On iOS the app's own output is your entire
view of it — so make the app say what you need (skill `unity-device-testing` for the probe that
does).

## Is the device there?

```bash
xcrun devicectl list devices
# Name    Hostname                 Identifier                             State        Model
# iPhone  iPhone.coredevice.local  XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX   connected    iPhone …
```

| State | Meaning | Do |
|---|---|---|
| `unavailable` | Paired once, not reachable now | Unlock it; same Wi-Fi as the Mac; for wireless, it must have been paired by cable once with *Connect via network* ticked in Xcode ▸ Devices |
| `available` | Reachable, no tunnel yet | Fine — the first command opens the tunnel |
| `connected` | Tunnel up | Go |
| not listed | Never paired, or the trust prompt was dismissed | Cable, unlock, *Trust This Computer* |

Use the `Identifier` for every `--device`. The UDID that provisioning profiles list is a different
string (`signing-from-the-terminal.md`, step 3).

## Install

```bash
xcrun devicectl device install app --device <identifier> <dd>/Build/Products/Debug-iphoneos/<Product>.app
# App installed:
# • bundleID: com.you.app
```

Reinstalling over an existing app **keeps its data and its granted permissions**. To test a first
launch, `xcrun devicectl device uninstall app --device <identifier> <bundle>` first.

## Launch with the console attached

```bash
nohup xcrun devicectl device process launch --device <identifier> \
      --console --terminate-existing <bundle> > /tmp/ios.log 2>&1 &
```

- `--console` holds the command open and streams the process's stdout/stderr. Unity's
  `Debug.Log`, `NSLog` from your plugin, and UnityAppController's lifecycle lines all arrive here.
  **The command lives as long as the app** — run it in the background and read the file.
- `--terminate-existing` makes the launch a cold start. Without it a running instance is
  foregrounded and you attach to nothing.
- One console per app. Launching again kills the previous stream; write each run to a new file if
  you need to compare them.
- Wait on the log, not on a sleep:
  `until grep -q "<your first line>" /tmp/ios.log || [ $((n+=1)) -gt 40 ]; do sleep 1; done`

Unity prints a stack under every `Debug.Log` in a development build. Filter when reading:

```bash
grep -E "\[YourTag\]|YourPlugin/iOS" /tmp/ios.log | sed -E 's/^([0-9-]+ [0-9:.]+) [^ ]+ /\1 /'
```

## The launch that goes quiet

The most common "it launched and nothing happens" is not a hang:

```
-> applicationDidBecomeActive()
…
-> applicationWillResignActive()        ← a system sheet just covered the app
                                          (nothing more until someone taps)
```

`applicationWillResignActive` within a second or two of launch means **iOS is showing a
permission sheet and the app is paused behind it.** The process is alive; its log resumes at
`applicationDidBecomeActive` after the tap. Nothing on the Mac can tap it — ask the human, and say
which sheet to expect.

> **Development builds raise a sheet of their own.** The Unity player connection broadcasts on the
> LAN, so a development build asks for **Local Network** access on first launch — before or after
> your own permission. One requested permission is therefore **two taps**. A human who tapped
> "Allow" once and reports "done" has usually answered the other sheet. Read the log: your
> permission's line (or your plugin's "granted") is the proof, not the report.

| Log shape | It is |
|---|---|
| Lifecycle lines, then `WillResignActive`, then silence | A system sheet. Ask for the tap |
| Silence after `applicationDidFinishLaunching`, process gone from `devicectl device info processes` | Crash on first use of a guarded API — missing usage string in `Info.plist` (`headless-build.md`) |
| `WillResignActive` → `DidEnterBackground` with nobody touching it | The device locked. Keep it awake in the app (`Screen.sleepTimeout = SleepTimeout.NeverSleep`) |
| The console command exits immediately with a CoreDevice error | Device locked at launch time, or Developer Mode off |

Is the process alive at all:

```bash
xcrun devicectl device info processes --device <identifier> | grep -i "<Product>"
```

## Backgrounding is not observable from the Mac — and not drivable

There is no `devicectl` verb for Home, for switching apps, or for tapping. Every step that needs
one is a step a person performs. What you *can* do is make the effect legible: log on
`OnApplicationPause`, and have long-running native work print a heartbeat, so that a log with a
20-second hole followed by a recovery line proves the round trip happened.

## Pull files back from the app

`Application.persistentDataPath` on iOS is `<container>/Documents`.

```bash
xcrun devicectl device copy from --device <identifier> \
      --domain-type appDataContainer --domain-identifier <bundle> \
      --source Documents/run.json --destination ./out/run.json
```

- `--source` is **relative to the container root** — `Documents/…`, `Library/Caches/…`. The
  absolute `/var/mobile/Containers/…` path the app logs is not accepted.
- One file per call; loop for several. Have the app log the file name it wrote so the pull does
  not have to guess.
- This works for development-signed apps you installed. It is how a recording, a timeline or a
  crash breadcrumb gets from the phone to something that can analyse it.
