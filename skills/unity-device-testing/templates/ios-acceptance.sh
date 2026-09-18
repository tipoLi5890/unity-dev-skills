#!/usr/bin/env bash
#
# On-device acceptance for an INSTALLED Unity iOS app, driven from the console log
# (reference/ios-driver.md). Building, signing and installing the .app is unity-ios-build.
#
#   ios-acceptance.sh --device <coredevice id> --bundle <bundle id> [--log <file>] [--out <dir>] [--wait]
#
#   --wait   unattended: physical steps wait for the APP's own log line (iOS gives the driver no
#            out-of-band way to see a cable) for up to 10 min, instead of waiting for Enter.
#
# Exit 0 = all green · 2 = a step failed · 3 = the harness could not run the test.
# EDIT the STEPS at the bottom for your probe's lines.

set -uo pipefail

DEV=""; BUNDLE=""; LOG="${TMPDIR:-/tmp}/ios-probe.log"; OUT="./device-out"; WAIT=0
TAG='\[Probe\]'
while [ $# -gt 0 ]; do
  case "$1" in
    --device) DEV="$2"; shift 2 ;;
    --bundle) BUNDLE="$2"; shift 2 ;;
    --log) LOG="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --wait) WAIT=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 3 ;;
  esac
done

say()  { printf '\n== %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*"; stop_console; exit 2; }
harn() { printf 'HARNESS: %s\n' "$*"; stop_console; exit 3; }
CONSOLE_PID=""
stop_console() { [ -n "$CONSOLE_PID" ] && kill "$CONSOLE_PID" >/dev/null 2>&1 || true; }

[ -n "$DEV" ] && [ -n "$BUNDLE" ] || harn "--device and --bundle are required"
STATE="$(xcrun devicectl list devices 2>/dev/null | grep "$DEV" | awk '{print $(NF-2)}')"
case "$STATE" in connected|available) ;; *) harn "device state is '${STATE:-not listed}' — unlock it, same network, 'Connect via network' on" ;; esac

# One log file per launch. --console blocks for the life of the app, so it runs in the background.
launch() { stop_console; : > "$LOG"
  nohup xcrun devicectl device process launch --device "$DEV" --console --terminate-existing "$BUNDLE" > "$LOG" 2>&1 &
  CONSOLE_PID=$!; }

MARK=0
mark()     { MARK="$(wc -l < "$LOG" | tr -dc 0-9)"; }                       # assert only on lines after this
since()    { tail -n +"$((MARK+1))" "$LOG"; }
wait_log() { local pat="$1" secs="$2" i=0
  while [ "$i" -lt "$secs" ]; do since | grep -qE "$pat" && return 0; sleep 1; i=$((i+1)); done; return 1; }

# A system sheet cannot be tapped from here. It looks like this in the log:
sheet_is_up() { since | tail -4 | grep -q 'applicationWillResignActive'; }

# physical <line the app logs when it happened> <instruction>
physical() { local pat="$1"; shift
  if [ "$WAIT" -eq 0 ]; then printf '\n>>> %s  (press Enter when done) ' "$*"; read -r _; return; fi
  printf '\n>>> %s  (waiting for the app to report it, up to 10 min)\n' "$*"
  wait_log "$pat" 600 || harn "nobody did it: $*"; }

pull_written_files() { mkdir -p "$OUT"
  grep -oE 'wrote [^ ]*/Documents/[^ ]+' "$LOG" | sed 's/.*\/Documents\///' | sort -u | while read -r f; do
    xcrun devicectl device copy from --device "$DEV" --domain-type appDataContainer \
          --domain-identifier "$BUNDLE" --source "Documents/$f" --destination "$OUT/$f" >/dev/null 2>&1 \
      && echo "   pulled $f" || echo "   could not pull $f"
  done; }

# ── STEPS — edit for your probe ───────────────────────────────────────────────────────────
say "1. cold start"
launch; mark
if ! wait_log "$TAG state Starting -> Running" 30; then
  sheet_is_up && harn "a system sheet is covering the app — tap Allow on the device (dev builds show Local Network first, then the app's own permission) and re-run"
  fail "never reached Running"
fi
echo "   OK"

say "2. remove it"
mark
physical "$TAG state Running -> Faulted" "UNPLUG the accessory now"
wait_log "$TAG state Running -> Faulted" 5 || fail "unplug was not detected"
echo "   OK"

say "3. put it back"
mark
physical "$TAG state .* -> Running" "PLUG the accessory back in"
wait_log "$TAG state .* -> Running" 30 || fail "did not recover after replug"
echo "   OK"

say "4. background (a human presses Home, waits 20 s, reopens the app)"
mark
physical 'applicationDidBecomeActive' "Press HOME, wait 20 seconds, open the app again"
sleep 5                                           # recovery shows in the first seconds after foreground
since | grep -qE "$TAG error" && fail "an error was logged after returning to the foreground"
echo "   OK"

pull_written_files
stop_console
say "ALL GREEN"
exit 0
