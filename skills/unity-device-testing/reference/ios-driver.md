# Driving an iOS device from a terminal

`xcrun devicectl` (Xcode 15+) is the whole toolbox: list, install, launch, copy. It has **no
screenshot verb and no tap verb**, so an iOS run is designed around the log from the first minute —
the probe's lines are the only readout you get (`device-probe.md`).

Getting the `.app` built and signed is `unity-ios-build`. This page starts with an installed app.

## Is the device usable right now?

```bash
xcrun devicectl list devices
# Name   Hostname                 Identifier                             State        Model
# iPhone iPhone.coredevice.local  XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX   connected    iPhone …
```

| State | Means | Do |
|---|---|---|
| `unavailable` | Paired once, not reachable: locked, off the Wi-Fi, or "Connect via network" is off | Ask the human to unlock it and check the network — exit 3, not a verdict |
| `available` | Reachable, no tunnel yet | Any command brings it to `connected` |
| `connected` | Ready | Go |

The `Identifier` is a CoreDevice id used by `--device`; the hardware UDID that provisioning profiles
list is in `devicectl device info details --device <id> | grep -i udid`.

## The console is the log

```bash
nohup xcrun devicectl device process launch --device "$DEV" --console --terminate-existing "$BUNDLE" \
      > "$LOG" 2>&1 &
```

- `--console` attaches stdout/stderr and blocks for the life of the app, so run it in the
  background and **read the file**. Unity's `Debug.Log` and native `NSLog` both arrive there; `NSLog`
  lines carry a timestamp, Unity's do not — put a timestamp or a counter in the probe's own lines if
  order across the two matters.
- `--terminate-existing` makes every launch a cold start. One log file per launch; never append.
- To "relaunch without the accessory", kill the previous `process launch` (it holds the console),
  then launch again.

```bash
wait_log() { local pat="$1" secs="$2" i=0
  while [ $i -lt "$secs" ]; do grep -qE "$pat" "$LOG" && return 0; sleep 1; i=$((i+1)); done; return 1; }
```

Steps that must assert "only lines after this point" record `wc -l < "$LOG"` first and grep
`tail -n +$((mark+1))`.

## System sheets stop the app and only a human can dismiss them

A permission sheet cannot be tapped from the CLI. Recognise it in the log instead:

```
-> applicationDidBecomeActive()
-> sceneWillResignActive()          <- a system sheet just covered the app
-> applicationWillResignActive()
```

If that pair appears within a second or two of launch and the probe's lines stop, the app is
waiting behind a sheet. Ask for **one tap**, then look again — a development build raises the
*Local Network* prompt (the player connection) **before** the app's own permission, so the first
"I tapped Allow" is often the wrong sheet and a second one follows. Assert on the permission's own
log line (its own "granted" message, or the probe's state change), never on the human's report.

## Backgrounding

No CLI verb presses Home. Ask the human: *Home, wait 20 s, open the app again*, and read
`applicationDidEnterBackground` / `applicationWillEnterForeground` from the log to time it. iOS
suspends the process in the background, so **no probe lines are written while it is away** —
"nothing logged for 20 s" is expected, and whatever the app must recover (a socket, a sensor stream)
shows up in the first seconds after `applicationDidBecomeActive`.

## Pull what the app wrote

`Application.persistentDataPath` is the app container's `Documents/`:

```bash
xcrun devicectl device copy from --device "$DEV" \
      --domain-type appDataContainer --domain-identifier "$BUNDLE" \
      --source "Documents/run-01.csv" --destination "./out/run-01.csv"
```

Have the probe log each file's name; the container's absolute path changes per install.

## What iOS will not let the driver do — design around it

| You cannot | So |
|---|---|
| Take a screenshot | The probe logs everything the screen shows, once a second |
| Tap the app or a system sheet | Mode switches are on-screen buttons for the human, and the probe logs `mode -> X` so the driver sees it happened |
| Know the screen is locked | The human tells you; the log shows `WillResignActive` |
| Detect a physical accessory change out-of-band | The app must log the change itself; the driver waits on that line |
| Keep the process alive in the background | Expect a gap in the log, then assert recovery |
