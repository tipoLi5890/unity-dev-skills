#!/usr/bin/env bash
#
# On-device acceptance for a Unity Android build, driven from the log (reference/android-driver.md).
#
#   device-acceptance.sh [-s <adb serial>] --apk <path> [--pkg <id>] [--wait]
#
#   --wait   unattended: physical steps watch the DEVICE for the change (up to 10 min) instead of
#            waiting for Enter, so latency assertions are measured from the real event.
#
# Exit 0 = every step green · 2 = a step failed (a verdict about the app) · 3 = the harness could
# not run the test (no device, screen off, APK missing, nobody acted). Keep those apart.
#
# EDIT the CONFIG block and the STEPS at the bottom for your probe's lines. The helpers are generic.

set -uo pipefail

# ── CONFIG ────────────────────────────────────────────────────────────────────────────────
PKG="${PKG:-}"                                   # default: read from the APK with aapt, else --pkg
TAG='\[Probe\]'                                  # the probe's log tag, regex-escaped
DIALOG_FOCUS='GrantPermissionsActivity|MediaProjectionPermissionActivity'   # system dialogs the driver may tap
# Present-tense state of "the thing a human changes". Default: a charger. Replace with YOUR source —
# one that is true only WHILE it is so (never a dump that also lists history).
present() { "${ADB[@]}" shell dumpsys battery 2>/dev/null | grep -q 'powered: true'; }

# ── args ──────────────────────────────────────────────────────────────────────────────────
SERIAL=""; APK=""; WAIT=0
while [ $# -gt 0 ]; do
  case "$1" in
    -s) SERIAL="$2"; shift 2 ;;
    --apk) APK="$2"; shift 2 ;;
    --pkg) PKG="$2"; shift 2 ;;
    --wait) WAIT=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 3 ;;
  esac
done
ADB=(adb); [ -n "$SERIAL" ] && ADB=(adb -s "$SERIAL")

say()  { printf '\n== %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*"; cleanup; exit 2; }
harn() { printf 'HARNESS: %s\n' "$*"; exit 3; }

# ── helpers ───────────────────────────────────────────────────────────────────────────────
reach() { local n=0; until "${ADB[@]}" get-state >/dev/null 2>&1; do
            n=$((n+1)); [ "$n" -ge 20 ] && return 1; adb devices >/dev/null 2>&1; sleep 2; done; }

tap_dialog_if_present() {
  "${ADB[@]}" shell dumpsys window 2>/dev/null | grep -qE "mCurrentFocus=.*($DIALOG_FOCUS)" || return 0
  local size w h rot t
  size="$("${ADB[@]}" shell wm size | sed -n 's/.*: //p' | tr -d '\r')"; w="${size%x*}"; h="${size#*x}"
  # `wm size` is the PHYSICAL portrait size in every rotation, and adb output ends in \r.
  rot="$("${ADB[@]}" shell dumpsys window displays | grep -m1 -oE 'ROTATION_[0-9]+' | tr -d '\r')"
  case "$rot" in ROTATION_90|ROTATION_270) t="$w"; w="$h"; h="$t" ;; esac
  # Confirm button as a fraction of the screen — measure once per OEM skin from a screenshot.
  if [ "$w" -gt "$h" ]; then "${ADB[@]}" shell input tap $((w*62/100)) $((h*90/100))
  else                        "${ADB[@]}" shell input tap $((w*70/100)) $((h*94/100)); fi
  echo "   (tapped a system dialog)"; sleep 2
}

# Wait up to $2 s for a log line matching $1 since the last `logcat -c`. Polls; never tails.
wait_log() { local pat="$1" secs="$2" i=0
  while [ "$i" -lt "$secs" ]; do
    "${ADB[@]}" logcat -d -v brief 2>/dev/null | grep -qE "$pat" && return 0
    tap_dialog_if_present; sleep 1; i=$((i+1))
  done; return 1; }

# physical <gone|back> <instruction>
physical() { local want="$1"; shift
  if [ "$WAIT" -eq 0 ]; then printf '\n>>> %s  (press Enter when done) ' "$*"; read -r _; return; fi
  printf '\n>>> %s  (watching the device, up to 10 min)\n' "$*"
  local i=0
  while [ "$i" -lt 1200 ]; do
    if [ "$want" = gone ]; then present || return 0; else present && return 0; fi
    sleep 0.5; i=$((i+1))
  done
  harn "nobody did it: $*"; }

cleanup() { "${ADB[@]}" shell settings put system screen_off_timeout "${OLD_TIMEOUT:-30000}" >/dev/null 2>&1 || true; }

# ── pre-flight (every failure here is exit 3) ─────────────────────────────────────────────
[ -f "$APK" ] || harn "APK not found: $APK"
reach || harn "no adb device (a headless Unity build restarts adb; Wi-Fi devices need 10-30 s)"
if [ -z "$PKG" ] && command -v aapt >/dev/null 2>&1; then
  PKG="$(aapt dump badging "$APK" 2>/dev/null | sed -n "s/^package: name='\([^']*\)'.*/\1/p")"
fi
[ -n "$PKG" ] || harn "package id unknown — pass --pkg"
"${ADB[@]}" shell input keyevent KEYCODE_WAKEUP >/dev/null; "${ADB[@]}" shell wm dismiss-keyguard >/dev/null 2>&1
"${ADB[@]}" shell dumpsys power | grep -q 'mWakefulness=Awake' || harn "screen is not awake — a black screenshot here is NOT an app bug"
OLD_TIMEOUT="$("${ADB[@]}" shell settings get system screen_off_timeout | tr -d '\r')"
"${ADB[@]}" shell settings put system screen_off_timeout 1800000 >/dev/null
present || harn "the accessory is not in its starting state — attach it first"

# ── STEPS — edit for your probe ───────────────────────────────────────────────────────────
say "1. install + cold start"
"${ADB[@]}" shell am force-stop "$PKG"
"${ADB[@]}" install -r -g "$APK" >/dev/null || harn "adb install failed"
ACT="$("${ADB[@]}" shell cmd package resolve-activity --brief "$PKG" | tail -1 | tr -d '\r')"
"${ADB[@]}" logcat -c
"${ADB[@]}" shell am start -W -n "$ACT" >/dev/null
wait_log "$TAG state Stopped -> Starting" 20 || fail "the probe never started"
wait_log "$TAG state Starting -> Running" 60 || fail "never reached Running (dialog not accepted? another app holding the device?)"
echo "   OK"

say "2. remove it"
"${ADB[@]}" logcat -c
physical gone "UNPLUG the accessory now"
wait_log "$TAG state Running -> Faulted" 3 || fail "no Faulted within 3 s of the physical unplug"
echo "   OK"

say "3. put it back"
"${ADB[@]}" logcat -c
physical back "PLUG the accessory back in"
wait_log "$TAG state .* -> Running" 60 || fail "did not recover after replug"
echo "   OK"

say "4. background 20 s, then resume"
"${ADB[@]}" logcat -c
"${ADB[@]}" shell input keyevent KEYCODE_HOME; sleep 20
"${ADB[@]}" shell am start -n "$ACT" >/dev/null 2>&1; sleep 3
"${ADB[@]}" logcat -d -v brief | grep -qE "$TAG (error|state Running ->)" && fail "state changed across background/resume"
echo "   OK"

cleanup
say "ALL GREEN"
exit 0
