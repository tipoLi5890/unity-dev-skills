# Driving an Android device from a script

Everything here is one `adb` call you can paste. The order is the order a run needs them.

## Reach the device, and keep reaching it

```bash
ADB=(adb -s "$SERIAL")
reach() { local n=0; until "${ADB[@]}" get-state >/dev/null 2>&1; do
            [ $((n++)) -ge 20 ] && return 1; adb devices >/dev/null; sleep 2; done; }
```

- **Call `reach` after anything that runs Unity headless.** A Unity Android build starts its own
  adb and restarts the server; every open `adb` connection dies (`logcat` exits 255, the next call
  prints `daemon not running; starting now`). A cabled device is back at once; a **Wi-Fi (mDNS)
  device takes 10–30 s** to be rediscovered. A watcher running across a build reads "device not
  found" as "the human did it" — so never let a presence poll and a build overlap.
- `timeout` does not exist on macOS. Bound waits with a counter, as above.
- A command that hangs with no output is usually adb waiting for a device that dropped:
  `adb kill-server`, then `reach`.

## Wake it, and prove it is awake

```bash
"${ADB[@]}" shell input keyevent KEYCODE_WAKEUP
"${ADB[@]}" shell wm dismiss-keyguard
"${ADB[@]}" shell dumpsys power | grep -q 'mWakefulness=Awake' || exit 3     # harness, not a verdict
"${ADB[@]}" shell settings put system screen_off_timeout 1800000               # restore it afterwards
```

With the screen off Unity logs `APP_CMD_RESUME` and then `APP_CMD_PAUSE` a moment later, renders
nothing, and every screenshot is pure black. That is a sleeping phone, and it is indistinguishable
from a "black screen on launch" bug until you read `mWakefulness`.

## Install the build you mean to test

```bash
"${ADB[@]}" shell am force-stop "$PKG"
"${ADB[@]}" install -r -g "$APK" >/dev/null || exit 3        # -g grants runtime permissions up front
"${ADB[@]}" shell dumpsys package "$PKG" | grep lastUpdateTime
ACT=$("${ADB[@]}" shell cmd package resolve-activity --brief "$PKG" | tail -1)
"${ADB[@]}" shell am start -W -n "$ACT"
```

`-g` removes the runtime-permission dialogs from the run. It does **not** cover consent the system
asks for per session (screen capture is one) — those dialogs still appear, and the driver taps them.

**Force-stop every other app that can hold the same hardware.** A Unity app sent to the background
is paused, but its native threads and handles are not — a previous test build keeps the camera
or a Bluetooth link claimed, and the app under test then waits forever on a busy device. `dumpsys activity processes | grep <your sdk tag>` or the log tag's pid
(`cat /proc/<pid>/cmdline`) tells you who else is there.

## Read the log by polling, never by tailing

```bash
"${ADB[@]}" logcat -c                                    # at the start of EVERY step
wait_log() { local pat="$1" secs="$2" i=0
  while [ $i -lt "$secs" ]; do
    "${ADB[@]}" logcat -d -v brief 2>/dev/null | grep -qE "$pat" && return 0
    tap_dialog_if_present; sleep 1; i=$((i+1)); done; return 1; }
wait_log '\[Probe\] state Starting -> Running' 60 || fail "never reached Running"
```

- `logcat -d` reads the device's ring buffer, so it survives an adb restart; a piped
  `adb logcat | grep` does not.
- Use `-v time` and `-t '<MM-DD HH:MM:SS.mmm>'` when you need "everything since then".
- Unity prints a stack under every `Debug.Log`; filter on your tag, not on `Unity`.
- **Tags from a release `.aar` may be missing.** A ProGuard/R8 rule
  `-assumenosideeffects class android.util.Log { *; }` deletes every call. Strip only `d`/`v` and
  keep `i/w/e`, or the field log is empty exactly when you need it.

## Tap a system dialog: detect by focus, aim by rotation

```bash
tap_dialog_if_present() {
  "${ADB[@]}" shell dumpsys window 2>/dev/null | grep -q 'mCurrentFocus=.*GrantPermissionsActivity' || return 0
  local size w h rot
  size="$("${ADB[@]}" shell wm size | sed -n 's/.*: //p' | tr -d '\r')"; w="${size%x*}"; h="${size#*x}"
  rot="$("${ADB[@]}" shell dumpsys window displays | grep -m1 -oE 'ROTATION_[0-9]+' | tr -d '\r')"
  case "$rot" in ROTATION_90|ROTATION_270) local t="$w"; w="$h"; h="$t" ;; esac
  if [ "$w" -gt "$h" ]; then "${ADB[@]}" shell input tap $((w*62/100)) $((h*90/100))
  else                        "${ADB[@]}" shell input tap $((w*70/100)) $((h*94/100)); fi
  sleep 2; }
```

Three traps, each of which produces "tapped forty times, dialog still there":

- **`wm size` reports the physical (portrait) size whatever the rotation.** A landscape game needs
  the axes swapped before computing a coordinate.
- **`adb shell` output ends in `\r`.** `case "$rot" in ROTATION_90)` never matches `ROTATION_90\r`.
  Strip it on every value you compare.
- The button row is not centred on a split: measure the confirm button once from a screenshot
  (`exec-out screencap -p`) and express it as a percentage, then re-check it per OEM skin.

Match the focus string to the dialog you expect (`GrantPermissionsActivity`,
`MediaProjectionPermissionActivity`, …) so the tapper never touches the game.

## Detect a physical change on the device itself

```bash
# 0 = true · 1 = false · 2 = the phone did not answer — do NOT read that as "the human did it"
charging() { local out; out="$("${ADB[@]}" shell dumpsys battery 2>/dev/null)" || return 2
             [ -n "$out" ] || return 2; printf '%s' "$out" | grep -q 'powered: true'; }
```

Whatever you ask a human to change, find the source that is true **only while** it is so, and poll
that: `dumpsys battery` (`powered: true`) for a charger, `settings get global airplane_mode_on` for
a toggle, the app's own `[Probe] connected …` line for an accessory the OS does not expose.

- **Prefer the present tense.** Several `dumpsys` services also print recent history; a grep that
  matches a history line never sees the thing leave, and an unattended run waits forever.
- **Distinguish "no answer" from "false".** A poll that returns false on any adb error reports a
  change that never happened — typically at the second a build finished and restarted adb.

## Background and resume

```bash
"${ADB[@]}" logcat -c
"${ADB[@]}" shell input keyevent KEYCODE_HOME; sleep 20
"${ADB[@]}" shell am start -n "$ACT" >/dev/null; sleep 3
"${ADB[@]}" logcat -d -v brief | grep -qE '\[Probe\] (error|state Running ->)' && fail "state changed across background"
```

`am start` on a running task prints *"Activity not started, its current task has been brought to
the front"* — that is success.

## Pull what the app wrote

`Application.persistentDataPath` is `/storage/emulated/0/Android/data/<pkg>/files`, readable by
`adb pull` without root. Have the probe log the full path of every file it writes and pull exactly
those.

## Put it back

```bash
"${ADB[@]}" shell am force-stop "$PKG"
"${ADB[@]}" shell settings put system screen_off_timeout 30000
```
