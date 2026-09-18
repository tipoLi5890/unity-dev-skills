#!/usr/bin/env bash
#
# Take a Unity project to a process running on an iPhone/iPad, one provable stage at a time.
#
#   ios-run.sh doctor                    identities, profiles, devices — and which team+profile covers which device
#   ios-run.sh build                     Unity → Xcode project (deletes the old one first)
#   ios-run.sh compile                   unsigned compile gate: no device, no team, no profile
#   ios-run.sh install                   signed build for the device + devicectl install
#   ios-run.sh launch [--console FILE]   cold start; with --console the app's log streams to FILE (backgrounded)
#   ios-run.sh pull <container path> <dest>    e.g. pull Documents/run.json ./out/
#   ios-run.sh native-sync               copy changed plugin sources into the generated project, rebuild, reinstall
#
# Settings come from `.ios-env` beside this script (see ios-env.example) or the environment.
# Nothing identifying is hardcoded, and nothing identifying is committed.
#
# Every stage deletes its expected output first and then checks that the output exists —
# an exit code alone proves nothing. Exit 0 = the stage produced its proof; 1 = it did not;
# 3 = the harness could not run (no Unity, no device, no project).
#
# Pairs with IosBuildScript.cs / IosPostprocess.cs from the same skill.

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32m✓\033[0m %s\n' "$*"; }
bad()  { printf '   \033[31m✗\033[0m %s\n' "$*"; }
die()  { bad "$*"; exit 1; }
harn() { printf '\033[33mHARNESS: %s\033[0m\n' "$*"; exit 3; }

# ── project + settings ────────────────────────────────────────────────────
ROOT="$HERE"
while [ "$ROOT" != "/" ] && [ ! -f "$ROOT/ProjectSettings/ProjectVersion.txt" ]; do ROOT="$(dirname "$ROOT")"; done
[ -f "$ROOT/ProjectSettings/ProjectVersion.txt" ] || harn "no Unity project above $HERE (ProjectSettings/ProjectVersion.txt)"

# shellcheck disable=SC1091
[ -f "$HERE/.ios-env" ] && { set -a; . "$HERE/.ios-env"; set +a; }

TEAM="${IOS_TEAM_ID:-}"
BUNDLE="${IOS_BUNDLE_ID:-}"
DEVICE="${IOS_DEVICE:-}"
OUT="${IOS_BUILD_OUT:-Builds/ios}";          case "$OUT" in /*) ;; *) OUT="$ROOT/$OUT" ;; esac
DD="${IOS_DERIVED_DATA:-Builds/ios-dd}";     case "$DD"  in /*) ;; *) DD="$ROOT/$DD"  ;; esac
CONF="${IOS_CONFIGURATION:-Debug}"
METHOD="${IOS_BUILD_METHOD:-IosBuildScript.Build}"
PLUGIN_ROOTS="${IOS_PLUGIN_ROOTS:-Assets Packages}"
ALLOW_UPDATES="${IOS_ALLOW_PROVISIONING_UPDATES:-0}"
PROJ="$OUT/Unity-iPhone.xcodeproj"
LOGDIR="${TMPDIR:-/tmp}"; LOGDIR="${LOGDIR%/}"
PB=/usr/libexec/PlistBuddy

unity_bin() {
  local v; v="$(sed -n 's/^m_EditorVersion: //p' "$ROOT/ProjectSettings/ProjectVersion.txt" | tr -d '\r')"
  local u="${UNITY:-/Applications/Unity/Hub/Editor/$v/Unity.app/Contents/MacOS/Unity}"
  [ -x "$u" ] || harn "Unity $v not found at $u (set UNITY=…)"
  printf '%s' "$u"
}

# devicectl identifier of the device to use: IOS_DEVICE, else the only connected/available one.
pick_device() {
  if [ -n "$DEVICE" ]; then printf '%s' "$DEVICE"; return; fi
  local ids
  ids="$(xcrun devicectl list devices 2>/dev/null | awk '/connected|available/ && !/unavailable/ {for(i=1;i<=NF;i++) if ($i ~ /^[0-9A-F]{8}-([0-9A-F]{4}-){3}[0-9A-F]{12}$/) print $i}')"
  [ -n "$ids" ] || harn "no reachable device — xcrun devicectl list devices (unlock it; same Wi-Fi; paired once by cable)"
  [ "$(printf '%s\n' "$ids" | wc -l | tr -d ' ')" = 1 ] || harn "several devices — set IOS_DEVICE to one of: $(echo $ids)"
  printf '%s' "$ids"
}

device_udid() {   # the UDID provisioning profiles list — NOT the devicectl identifier
  xcrun devicectl device info details --device "$1" 2>/dev/null | sed -n 's/.* udid: *//p' | head -1
}

app_path() { find "$DD/Build/Products/$CONF-iphoneos" -maxdepth 1 -name '*.app' 2>/dev/null | head -1; }

bundle_of_app() { "$PB" -c 'Print :CFBundleIdentifier' "$1/Info.plist" 2>/dev/null; }

profiles() {
  local d
  for d in "$HOME/Library/MobileDevice/Provisioning Profiles" "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"; do
    [ -d "$d" ] && find "$d" -maxdepth 1 -name '*.mobileprovision'
  done
}

# ── doctor ────────────────────────────────────────────────────────────────
cmd_doctor() {
  say "signing identities (the id in parentheses is a PERSON, not the team)"
  local idents; idents="$(security find-identity -v -p codesigning 2>/dev/null | grep -E '^ +[0-9]+\)')"
  [ -n "$idents" ] && printf '%s\n' "$idents" || bad "none — no certificate with a private key in the keychain"
  local have; have="$(printf '%s\n' "$idents" | awk '{print $2}')"

  say "devices"
  xcrun devicectl list devices 2>/dev/null | sed 's/^/   /'
  local dev udid=""
  dev="$( (pick_device) 2>/dev/null )" || dev=""
  if [ -n "$dev" ]; then
    udid="$(device_udid "$dev")"
    xcrun devicectl device info details --device "$dev" 2>/dev/null | grep -iE 'osVersionNumber|developerModeStatus|marketingName' | sed 's/^/  /'
    echo "   UDID (what profiles list): ${udid:-unknown}"
  else
    bad "no single reachable device — the profile join below cannot check device coverage"
  fi

  say "provisioning profiles"
  local tmp; tmp="$(mktemp)"; local der; der="$(mktemp)"; local any=0 usable=0
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    security cms -D -i "$p" > "$tmp" 2>/dev/null || continue
    any=1
    local name team appid exp ndev certok=no devok=no i=0 fp
    name="$("$PB" -c 'Print :Name' "$tmp" 2>/dev/null)"
    team="$("$PB" -c 'Print :TeamIdentifier:0' "$tmp" 2>/dev/null)"
    appid="$("$PB" -c 'Print :Entitlements:application-identifier' "$tmp" 2>/dev/null)"
    exp="$("$PB" -c 'Print :ExpirationDate' "$tmp" 2>/dev/null)"
    ndev="$("$PB" -c 'Print :ProvisionedDevices' "$tmp" 2>/dev/null | grep -vc '[{}]')"
    while "$PB" -c "Print :DeveloperCertificates:$i" "$tmp" > "$der" 2>/dev/null; do
      fp="$(openssl x509 -inform DER -in "$der" -noout -fingerprint -sha1 2>/dev/null | sed 's/.*=//' | tr -d ':')"
      printf '%s\n' "$have" | grep -qi "^$fp$" && certok=yes
      i=$((i+1))
    done
    [ -n "$udid" ] && "$PB" -c 'Print :ProvisionedDevices' "$tmp" 2>/dev/null | grep -q "$udid" && devok=yes
    local managed=no; case "$name" in "iOS Team Provisioning Profile"*|"Mac Team Provisioning Profile"*) managed=yes ;; esac
    printf '   %s\n      team=%s  appid=%s  devices=%s  expires=%s\n      cert-on-this-mac=%s  covers-device=%s  xcode-managed=%s\n' \
           "$name" "$team" "$appid" "$ndev" "$exp" "$certok" "$devok" "$managed"
    if [ "$certok" = yes ] && { [ "$devok" = yes ] || [ -z "$udid" ]; } && [ "$ndev" != 0 ]; then
      usable=1
      ok "usable → IOS_TEAM_ID=$team  bundle id must match: ${appid#*.}  signing: $( [ $managed = yes ] && echo 'CODE_SIGN_STYLE=Automatic (managed profiles refuse Manual)' || echo 'Automatic or Manual')"
    fi
  done < <(profiles)
  rm -f "$tmp" "$der"
  [ "$any" = 1 ] || bad "no provisioning profiles on this Mac — a signed build needs Xcode with the team's account, once"
  [ "$usable" = 1 ] || bad "no profile joins a local certificate with this device — only 'compile' will work"

  say "settings in effect"
  echo "   project   $ROOT"
  echo "   team      ${TEAM:-(unset)}    bundle ${BUNDLE:-(project default)}"
  echo "   xcodeproj $PROJ $( [ -d "$PROJ" ] && echo '(exists)' || echo '(missing — run build)')"
  echo "   products  $DD/Build/Products/$CONF-iphoneos"
  [ "$ALLOW_UPDATES" = 1 ] && echo "   -allowProvisioningUpdates ON (needs an Xcode account logged in)"
  return 0
}

# ── build: Unity → Xcode project ──────────────────────────────────────────
cmd_build() {
  local u; u="$(unity_bin)"
  pgrep -f "Unity.*-projectPath $ROOT" >/dev/null && harn "this project is open in a Unity instance — close it (one Unity per project)"
  say "Unity → $PROJ  (minutes; log $LOGDIR/ios-unity.log)"
  rm -rf "$OUT"
  IOS_BUILD_OUT="$OUT" IOS_TEAM_ID="$TEAM" IOS_BUNDLE_ID="$BUNDLE" IOS_MIN_VERSION="${IOS_MIN_VERSION:-15.0}" \
    "$u" -batchmode -quit -projectPath "$ROOT" -buildTarget iOS -executeMethod "$METHOD" \
         -logFile "$LOGDIR/ios-unity.log" >/dev/null 2>&1
  local rc=$?
  if [ ! -d "$PROJ" ]; then
    grep -E "error CS|No valid Unity Editor license|another Unity instance|\[IosBuild\] FAILED" "$LOGDIR/ios-unity.log" | head -8
    [ $rc = 198 ] && harn "exit 198 — Unity licence, not the project"
    die "no Xcode project produced (unity exit $rc)"
  fi
  ok "Xcode project written"
  ( cd "$ROOT" && git diff --stat -- ProjectSettings 2>/dev/null | sed 's/^/   changed: /' )
  return 0
}

xcb() {   # xcb <log> <extra args…>
  local log="$1"; shift
  [ -d "$PROJ" ] || harn "no $PROJ — run: $(basename "$0") build"
  xcodebuild -project "$PROJ" -scheme Unity-iPhone -sdk iphoneos -configuration "$CONF" \
             -derivedDataPath "$DD" "$@" build > "$log" 2>&1
  if ! grep -q '\*\* BUILD SUCCEEDED \*\*' "$log"; then
    grep -E "error:|\*\* BUILD FAILED" "$log" | sort -u | head -12
    echo "   full log: $log"
    return 1
  fi
}

# ── compile: the gate that needs nothing ──────────────────────────────────
cmd_compile() {
  say "unsigned compile gate"
  xcb "$LOGDIR/ios-xcode-compile.log" CODE_SIGNING_ALLOWED=NO || die "does not compile"
  ok "BUILD SUCCEEDED (unsigned) — generated C++ and native plugins compile and link"
}

signed_build() {
  local dev="$1"
  [ -n "$TEAM" ] || die "IOS_TEAM_ID is unset — run: $(basename "$0") doctor"
  local extra=(); [ "$ALLOW_UPDATES" = 1 ] && extra+=(-allowProvisioningUpdates)
  rm -rf "$DD/Build/Products/$CONF-iphoneos"/*.app
  xcb "$LOGDIR/ios-xcode-device.log" -destination "id=$dev" CODE_SIGN_STYLE=Automatic DEVELOPMENT_TEAM="$TEAM" "${extra[@]+"${extra[@]}"}" \
    || die "signed build failed — see reference/signing-from-the-terminal.md for the error table"
  grep -E "Signing Identity|Provisioning Profile" "$LOGDIR/ios-xcode-device.log" | sort -u | sed 's/^ */   /'
  [ -n "$(app_path)" ] || die "BUILD SUCCEEDED but no .app under $DD/Build/Products/$CONF-iphoneos"
}

# ── install ───────────────────────────────────────────────────────────────
cmd_install() {
  local dev; dev="$(pick_device)"
  say "signed build for $dev"
  signed_build "$dev"
  local app; app="$(app_path)"
  say "install $(basename "$app")"
  local out; out="$(xcrun devicectl device install app --device "$dev" "$app" 2>&1)"
  printf '%s\n' "$out" | grep -q 'bundleID' || { printf '%s\n' "$out" | tail -5; die "install failed (Developer Mode on? device unlocked?)"; }
  ok "installed $(bundle_of_app "$app")"
}

# ── launch ────────────────────────────────────────────────────────────────
cmd_launch() {
  local console=""
  while [ $# -gt 0 ]; do case "$1" in --console) console="$2"; shift 2 ;; *) die "unknown arg $1" ;; esac; done
  local dev; dev="$(pick_device)"
  local b="$BUNDLE"; [ -n "$b" ] || { local a; a="$(app_path)"; [ -n "$a" ] && b="$(bundle_of_app "$a")"; }
  [ -n "$b" ] || die "no bundle id — set IOS_BUNDLE_ID or run install first"
  if [ -z "$console" ]; then
    xcrun devicectl device process launch --device "$dev" --terminate-existing "$b" | tail -2
    return
  fi
  pkill -f "devicectl device process launch.*$b" 2>/dev/null
  : > "$console"
  nohup xcrun devicectl device process launch --device "$dev" --console --terminate-existing "$b" > "$console" 2>&1 &
  say "launched $b — log → $console (pid $!)"
  local n=0
  until [ -s "$console" ] || [ $n -ge 20 ]; do sleep 1; n=$((n+1)); done
  [ -s "$console" ] || die "no output after 20 s — device locked, or Developer Mode off"
  sleep 3
  if tail -5 "$console" | grep -q 'WillResignActive'; then
    printf '   \033[33m!\033[0m the app resigned active right after launch: a system sheet is up.\n'
    echo "     Someone has to tap it on the device. Development builds ask for Local Network too — that is TWO sheets."
  fi
  ok "streaming; read it with: grep -E '<your tag>' $console"
}

# ── pull ──────────────────────────────────────────────────────────────────
cmd_pull() {
  [ $# -eq 2 ] || die "usage: pull <path relative to the container, e.g. Documents/run.json> <dest file or dir>"
  local dev; dev="$(pick_device)"
  local b="$BUNDLE"; [ -n "$b" ] || { local a; a="$(app_path)"; [ -n "$a" ] && b="$(bundle_of_app "$a")"; }
  [ -n "$b" ] || die "no bundle id — set IOS_BUNDLE_ID"
  case "$1" in /*) die "source must be relative to the container root (Documents/…), not the absolute path the app logs" ;; esac
  local dest="$2"; [ -d "$dest" ] && dest="${dest%/}/$(basename "$1")"
  rm -f "$dest"
  xcrun devicectl device copy from --device "$dev" --domain-type appDataContainer --domain-identifier "$b" \
        --source "$1" --destination "$dest" >/dev/null 2>&1
  [ -s "$dest" ] || die "nothing copied — does $1 exist in $b's container?"
  ok "$dest ($(wc -c < "$dest" | tr -d ' ') bytes)"
}

# ── native-sync ───────────────────────────────────────────────────────────
cmd_native_sync() {
  [ -d "$OUT/Libraries" ] || harn "no $OUT/Libraries — run build first"
  say "syncing native plugin sources into the generated project"
  local changed=0 seen=0 dst src root base
  while IFS= read -r dst; do
    base="$(basename "$dst")"; src=""
    for root in $PLUGIN_ROOTS; do
      case "$root" in /*) ;; *) root="$ROOT/$root" ;; esac
      [ -d "$root" ] || continue
      src="$(find -L "$root" -path '*/Plugins/iOS/*' -name "$base" -not -path "$OUT/*" 2>/dev/null | head -1)"
      [ -n "$src" ] && break
    done
    [ -n "$src" ] || continue
    seen=$((seen+1))
    if ! diff -q "$src" "$dst" >/dev/null 2>&1; then
      cp "$src" "$dst"; changed=$((changed+1)); echo "   updated $base  ← $src"
    fi
  done < <(find "$OUT/Libraries" -type f \( -name '*.mm' -o -name '*.m' -o -name '*.h' -o -name '*.cpp' -o -name '*.swift' \) -path '*Plugins*')
  [ "$seen" -gt 0 ] || die "matched no plugin source under: $PLUGIN_ROOTS — a file: package lives outside the project; add its path to IOS_PLUGIN_ROOTS"
  echo "   $seen source(s) matched, $changed changed"
  [ "$changed" -gt 0 ] || { ok "already in sync — nothing to rebuild"; return 0; }
  cmd_install
  echo "   note: C# changes, new files and .meta flag changes are NOT covered — those need: $(basename "$0") build"
}

case "${1:-}" in
  doctor)      shift; cmd_doctor "$@" ;;
  build)       shift; cmd_build "$@" ;;
  compile)     shift; cmd_compile "$@" ;;
  install)     shift; cmd_install "$@" ;;
  launch)      shift; cmd_launch "$@" ;;
  pull)        shift; cmd_pull "$@" ;;
  native-sync) shift; cmd_native_sync "$@" ;;
  *) sed -n '3,12p' "$0" | sed 's/^# \{0,1\}//'; exit 3 ;;
esac
