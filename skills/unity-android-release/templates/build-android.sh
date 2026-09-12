#!/usr/bin/env bash
#
# Build a Unity project for Android, and prove the result.
#
#   build-android.sh doctor       resolve what is ACTUALLY in effect; build nothing
#   build-android.sh preflight    doctor + the release gates; exit non-zero if unshippable
#   build-android.sh test         debug-signed APK, for sideloading
#   build-android.sh release      signed AAB for the store (runs the test suite first)
#   build-android.sh release --apk --install
#
#   --version-code N   set explicitly (default: keep for test, bump for release)
#   --output PATH      where to write the artifact
#   --install          adb install afterwards
#   --no-test / --test override whether the PlayMode suite runs first
#
# A build writes Builds/build-<stamp>.result on exit — "ok|fail <exit> <artifact>". Wait on THAT
# file, never on a word in the console log: colour escapes make anchored patterns fail silently.
#
# Signing comes from <script dir>/.build-env, gitignored, never from the command line where it
# would land in shell history and the process table:
#
#     UNITY_KEYSTORE=/Users/you/keys/app.keystore
#     UNITY_KEYSTORE_PASS=...
#     UNITY_KEY_ALIAS=app
#     UNITY_KEY_ALIAS_PASS=...
#
# Pairs with Editor/BuildScript.cs from the same skill. Project-agnostic: everything is discovered
# from the project, nothing is hardcoded.
#
# WHY IT IS SHAPED LIKE THIS
#   · Unity exits 0 when it never started, so the artifact — not the exit code — is the signal.
#   · "It built" is not "it runs": the artifact is read back for signer, ABIs and merged manifest.
#   · A settings file with the right name may be dormant; `doctor` follows reference chains and
#     prints what the project actually loads.
#   · Anything unrecoverable (template package name, missing keystore, re-used versionCode, a
#     native plugin with no matching ABI, a 4 KB-aligned .so under targetSdk 35+) is a REFUSAL,
#     not a warning nobody reads.

set -euo pipefail

# ── help, before anything that needs a project ────────────────────────────────────────────────

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '3,37p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0
fi

# ── locate the project ────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$SCRIPT_DIR"
while [[ "$REPO" != "/" && ! -f "$REPO/ProjectSettings/ProjectVersion.txt" ]]; do
  REPO="$(dirname "$REPO")"
done
[[ -f "$REPO/ProjectSettings/ProjectVersion.txt" ]] || {
  echo "not inside a Unity project (no ProjectSettings/ProjectVersion.txt above $SCRIPT_DIR)" >&2
  exit 2
}
cd "$REPO"

PS=ProjectSettings/ProjectSettings.asset
GS=ProjectSettings/GraphicsSettings.asset
QS=ProjectSettings/QualitySettings.asset
ENV_FILE="${UNITY_BUILD_ENV:-$SCRIPT_DIR/.build-env}"
HISTORY="${UNITY_BUILD_HISTORY:-$SCRIPT_DIR/build-history.tsv}"
OUT_DIR="${UNITY_BUILD_OUT:-$REPO/Builds}"
TARGET_ABI="${UNITY_TARGET_ABI:-arm64-v8a}"

# ── arguments ─────────────────────────────────────────────────────────────────────────────────

MODE="${1:-doctor}"; shift || true
FORMAT="aab"; VERSION_CODE=""; DO_INSTALL=0; RUN_TESTS=""; OUTPUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apk)          FORMAT="apk" ;;
    --aab)          FORMAT="aab" ;;
    --version-code) VERSION_CODE="${2:?--version-code needs a number}"; shift ;;
    --output)       OUTPUT="${2:?--output needs a path}"; shift ;;
    --install)      DO_INSTALL=1 ;;
    --no-test)      RUN_TESTS=0 ;;
    --test)         RUN_TESTS=1 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

case "$MODE" in
  doctor|preflight) : ;;
  test)    FORMAT="apk"; RUN_TESTS="${RUN_TESTS:-0}" ;;   # quick loop
  release) RUN_TESTS="${RUN_TESTS:-1}" ;;                 # never ship something unverified
  *) echo "usage: $0 {doctor|preflight|test|release} [options]   (--help)" >&2; exit 2 ;;
esac

# ── output helpers ────────────────────────────────────────────────────────────────────────────

if [[ -t 1 ]]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'
else B=""; G=""; Y=""; R=""; N=""; fi
STAMP="$(date +%Y%m%d-%H%M)"
mkdir -p "$OUT_DIR"

# A machine-readable completion marker, written exactly once on exit whatever happens.
#
# Anything automating this needs to know when it finished, and grepping the console log for a word
# is a trap: colour escapes mean the line does not END with the word you can see, so an anchored
# pattern never matches and the waiter spins forever. A file either exists or it does not.
#
#   RESULT="Builds/build-<stamp>.result"
#   until [ -f "$RESULT" ]; do sleep 10; done; cat "$RESULT"
RESULT_FILE="$OUT_DIR/build-${STAMP}.result"
finish() {
  local rc=$?
  printf '%s\t%s\t%s\n' "$([ $rc -eq 0 ] && echo ok || echo fail)" "$rc" "${OUTPUT:-}" > "$RESULT_FILE"
}

# doctor only reads; it leaves no trace in Builds/.
if [[ "$MODE" != "doctor" ]]; then trap finish EXIT; fi

say()  { printf '%s▸ %s%s\n' "$B" "$*" "$N"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '  %s✗ %s%s\n' "$R" "$*" "$N" >&2; exit 1; }

FAILED=0
gate() { # gate <condition-result> <message> — records a preflight failure without exiting
  if [[ "$1" == "0" ]]; then ok "$2"; else printf '  %s✗%s %s\n' "$R" "$N" "$2"; FAILED=1; fi
}

yaml() { # yaml <key> [file] — first scalar value of a top-level-ish key
  grep -m1 -E "^[[:space:]]*$1:" "${2:-$PS}" 2>/dev/null | sed 's/.*: *//' | tr -d '\r' || true
}

# ── toolchain ─────────────────────────────────────────────────────────────────────────────────

say "Toolchain"
UNITY_VERSION="$(sed -n 's/^m_EditorVersion: *//p' ProjectSettings/ProjectVersion.txt | tr -d '\r')"
UNITY="${UNITY_PATH:-/Applications/Unity/Hub/Editor/${UNITY_VERSION}/Unity.app/Contents/MacOS/Unity}"
[[ -x "$UNITY" ]] || die "Unity $UNITY_VERSION not found at $UNITY (set UNITY_PATH to override)"
ok "Unity $UNITY_VERSION"

# .../<version>/Unity.app/Contents/MacOS/Unity → .../<version>   (four levels, not three:
# the PlaybackEngines directory sits BESIDE Unity.app, not inside it)
UNITY_ROOT="$(dirname "$(dirname "$(dirname "$(dirname "$UNITY")")")")"
SDK="${ANDROID_SDK_ROOT:-$UNITY_ROOT/PlaybackEngines/AndroidPlayer/SDK}"
BUILD_TOOLS=""; AAPT=""; APKSIGNER=""; ADB=""
if [[ -d "$SDK" ]]; then
  BUILD_TOOLS="$(ls -d "$SDK"/build-tools/* 2>/dev/null | sort -V | tail -1 || true)"
  [[ -n "$BUILD_TOOLS" ]] && { AAPT="$BUILD_TOOLS/aapt"; APKSIGNER="$BUILD_TOOLS/apksigner"; }
  ADB="$SDK/platform-tools/adb"
  ok "Android SDK build-tools $(basename "${BUILD_TOOLS:-none}")"
else
  warn "no Android SDK at $SDK — the Android module may not be installed"
fi

# The bundled NDK carries llvm-readelf, which is how a native library's page alignment is read.
READELF="$(ls "$UNITY_ROOT"/PlaybackEngines/AndroidPlayer/NDK/toolchains/llvm/prebuilt/*/bin/llvm-readelf 2>/dev/null | head -1 || true)"

# ── the project lock ──────────────────────────────────────────────────────────────────────────
# A stale lockfile makes every run exit 0 immediately with a ~45-line log. Match the EDITOR binary:
# a version-path pattern also matches Unity's Roslyn server and licensing client, which live for days.

if [[ -f Temp/UnityLockfile && "$MODE" != "doctor" ]]; then
  if pgrep -f "Contents/MacOS/Unity$" >/dev/null 2>&1; then
    die "another Unity process holds the project lock (editor, or a build already running)"
  fi
  rm -f Temp/UnityLockfile
  warn "removed a stale Temp/UnityLockfile"
fi

# ── doctor: what is ACTUALLY in effect ────────────────────────────────────────────────────────
# A settings file with a plausible name is not evidence. These follow reference chains.

say "Project"
PRODUCT="$(yaml productName)"
PACKAGE="$(awk '/^  applicationIdentifier:/{f=1;next} f&&/^    Android:/{print $2;exit} f&&/^  [a-zA-Z]/{exit}' "$PS")"
VERSION_NAME="$(yaml bundleVersion)"
CURRENT_CODE="$(yaml AndroidBundleVersionCode)"
ARCH="$(yaml AndroidTargetArchitectures)"
MIN_SDK="$(yaml AndroidMinSdkVersion)"
TARGET_SDK="$(yaml AndroidTargetSdkVersion)"
BACKEND="$(awk '/^  scriptingBackend:/{f=1;next} f&&/^    Android:/{print $2;exit} f&&/^  [a-zA-Z]/{exit}' "$PS")"

info "product      ${PRODUCT:-?}"
info "package      ${PACKAGE:-<unparsed>}"
info "version      ${VERSION_NAME:-?}  code ${CURRENT_CODE:-?}"
MIN_NOTE=""   # the clamp to 25 is known for 6000.4 only; assert no floor for other editor lines
case "$UNITY_VERSION" in 6000.4*) MIN_NOTE="  (6000.4 would not go below 25)" ;; esac
info "backend      ${BACKEND:-?}  (1 = IL2CPP)     minSdk ${MIN_SDK:-?}${MIN_NOTE}"
case "${TARGET_SDK:-0}" in
  0|"") info "targetSdk    Auto = highest installed — which may be 35+, see the page-alignment check below" ;;
  *)    info "targetSdk    $TARGET_SDK (pinned)" ;;
esac
case "${ARCH:-}" in
  2) info "architecture ARM64 only" ;;
  *) info "architecture AndroidTargetArchitectures=${ARCH:-?}  (2 = ARM64 only, which is what stores want)" ;;
esac

# `grep -c` exits 1 when the count is ZERO, so `$(grep -c ... || echo 0)` produces "0\n0" —
# which then fails every comparison against "0". Assign on failure; never append.
SCENES="$(grep -c 'enabled: 1' ProjectSettings/EditorBuildSettings.asset 2>/dev/null)" || SCENES=0
info "scenes       $SCENES enabled in Build Settings"

say "Graphics — resolved, not assumed"
RP_GUID="$(grep -m1 'm_CustomRenderPipeline:' "$GS" | sed -n 's/.*guid: \([a-f0-9]*\).*/\1/p')"
if [[ -n "$RP_GUID" ]]; then
  RP_META="$(grep -rl "^guid: $RP_GUID" --include='*.meta' Assets Packages 2>/dev/null | head -1 || true)"
  RP_ASSET="${RP_META%.meta}"
  if [[ -n "$RP_ASSET" ]]; then
    ok "render pipeline in force: $RP_ASSET"
    info "HDR=$(yaml m_SupportsHDR "$RP_ASSET")  MSAA=$(yaml m_MSAA "$RP_ASSET")  renderScale=$(yaml m_RenderScale "$RP_ASSET")"
  else
    warn "GraphicsSettings points at guid $RP_GUID but no .meta matches it"
  fi
else
  info "no custom render pipeline (built-in renderer)"
fi

# Quality levels only override the above when they name an asset of their own.
OVERRIDES="$(grep -c 'renderPipeline: {fileID: 11400000' "$QS" 2>/dev/null)" || OVERRIDES=0
LEVELS="$(grep -c '^    name:' "$QS" 2>/dev/null)" || LEVELS=0
if [[ "$OVERRIDES" == "0" ]]; then
  info "quality levels ($LEVELS) do NOT override it — any per-tier RP asset in the project is DORMANT"
else
  warn "$OVERRIDES of $LEVELS quality levels override the pipeline — check which tier the platform uses:"
  grep -n 'm_PerPlatformDefaultQuality' -A6 "$QS" | sed 's/^/      /'
fi

API_RAW="$(awk '/m_BuildTarget: AndroidPlayer/{f=1} f&&/m_APIs:/{print $2; exit}' "$PS")"
AUTO="$(awk '/m_BuildTarget: AndroidPlayer/{f=1} f&&/m_Automatic:/{print $2; exit}' "$PS")"
APIS=""
for (( i=0; i<${#API_RAW}; i+=8 )); do
  case "${API_RAW:$i:8}" in
    15000000) APIS="$APIS Vulkan" ;;
    0b000000) APIS="$APIS OpenGLES3" ;;
    08000000) APIS="$APIS OpenGLES2" ;;
    *)        APIS="$APIS ${API_RAW:$i:8}" ;;
  esac
done
info "graphics APIs:${APIS:- (auto)}  $([[ "$AUTO" == "0" ]] && echo '(pinned by hand)' || echo '(automatic)')"

say "Native plugins"
ROOTS=(Assets Packages Library/PackageCache)
while IFS= read -r p; do [[ -d "$p" ]] && ROOTS+=("$p"); done \
  < <(sed -n 's/.*"file:\([^"]*\)".*/\1/p' Packages/manifest.json 2>/dev/null || true)
FOUND_AAR=0; ABI_BAD=0; ALIGN_BAD=0
while IFS= read -r aar; do
  [[ -z "$aar" ]] && continue
  FOUND_AAR=1
  # Captured, not piped: `unzip | grep -q` under pipefail reports FAILURE on a match, because
  # grep -q exits early and unzip dies of SIGPIPE.
  LIST="$(unzip -l "$aar" 2>/dev/null || true)"
  if grep -q "jni/${TARGET_ABI}/" <<<"$LIST"; then
    ok "$(basename "$aar") carries $TARGET_ABI"
  else
    printf '  %s✗%s %s has no %s — it will build fine and crash on launch\n' "$R" "$N" "$(basename "$aar")" "$TARGET_ABI"
    ABI_BAD=1
  fi
  # Page alignment decides the highest targetSdk you may set: from Android 15, a targetSdk 35+ app
  # cannot load a 4 KB-aligned .so on a 16 KB-page device. Same unzip, so check it here.
  if [[ -n "$READELF" ]]; then
    TMP_SO="$(mktemp -d)"
    unzip -oq "$aar" "jni/${TARGET_ABI}/*" -d "$TMP_SO" >/dev/null 2>&1 || true
    while IFS= read -r so; do
      [[ -z "$so" ]] && continue
      ALIGNS="$("$READELF" -l "$so" 2>/dev/null | awk '$1=="LOAD"{print $NF}' | sort -u | tr '\n' ' ')"
      ALIGNS="${ALIGNS% }"
      case " $ALIGNS " in
        *" 0x1000 "*) printf '  %s!%s %s is 4 KB aligned (LOAD %s) — needs 0x4000 for 16 KB-page devices\n' \
                             "$Y" "$N" "$(basename "$so")" "$ALIGNS"; ALIGN_BAD=1 ;;
        *)            [[ -n "${ALIGNS// /}" ]] && info "$(basename "$so") LOAD alignment $ALIGNS" ;;
      esac
    done < <(find "$TMP_SO" -name '*.so' 2>/dev/null || true)
    rm -rf "$TMP_SO"
  fi
done < <(find "${ROOTS[@]}" -name '*.aar' 2>/dev/null | grep -v '/Temp/' | sort -u || true)
# Say the zero case out loud: a silent pass and a real pass look identical otherwise.
[[ "$FOUND_AAR" == "0" ]] && info "no native .aar plugins found (searched ${#ROOTS[@]} roots incl. file: deps)"

say "Signing"
if [[ -f "$ENV_FILE" ]]; then set -a; . "$ENV_FILE"; set +a; ok "loaded $(basename "$ENV_FILE")"; fi
KEYSTORE="${UNITY_KEYSTORE:-}"
if [[ -n "$KEYSTORE" && -f "$KEYSTORE" ]]; then ok "keystore $(basename "$KEYSTORE")"
elif [[ -n "$KEYSTORE" ]];                 then warn "keystore configured but missing: $KEYSTORE"
else                                            info "no keystore configured — builds will be DEBUG-SIGNED"; fi

if [[ "$MODE" == "doctor" ]]; then say "Done"; exit 0; fi

# ── gates ─────────────────────────────────────────────────────────────────────────────────────

say "Gates"
[[ "$ABI_BAD" == "0" ]] && ok "native ABIs match $TARGET_ABI" || { FAILED=1; }
# 16 KB pages: a 4 KB-aligned library will not load under targetSdk 35+ on such a device. That is a
# refusal for anything published (Play is reported to require 16 KB compatibility for new apps) and
# a loud warning for a sideloaded test APK, which still runs on every 4 KB-page device.
if [[ "$ALIGN_BAD" == "1" ]]; then
  case "${TARGET_SDK:-0}" in
    ""|0|3[5-9]|[4-9][0-9])
      if [[ "$MODE" == "release" || "$MODE" == "preflight" ]]; then
        gate 1 "a native library is 4 KB aligned but targetSdk is ${TARGET_SDK:-Auto} — pin targetSdk 34, or have the library rebuilt with -Wl,-z,max-page-size=16384"
      else
        warn "4 KB-aligned native library with targetSdk ${TARGET_SDK:-Auto} — this APK dies on launch on 16 KB-page devices"
      fi ;;
    *)
      warn "a native library is 4 KB aligned; targetSdk $TARGET_SDK still loads it — do not raise targetSdk until it ships 0x4000" ;;
  esac
elif [[ -z "$READELF" ]]; then
  info "no llvm-readelf in the bundled NDK — native page alignment (16 KB rule) NOT checked"
fi
[[ "$SCENES" -gt 0 ]] && ok "$SCENES scene(s) to build" \
  || { printf '  %s✗%s no enabled scenes — BuildPipeline fails with "Result: Unknown" and no error line\n' "$R" "$N"; FAILED=1; }

if [[ "$MODE" == "release" || "$MODE" == "preflight" ]]; then
  case "$PACKAGE" in
    "")                  gate 1 "package name could not be parsed from $PS" ;;
    com.DefaultCompany.*) gate 1 "package is still Unity's template default ($PACKAGE) — store identity, LOCKED once published" ;;
    *)                   gate 0 "package $PACKAGE" ;;
  esac
  [[ -n "$KEYSTORE" && -f "$KEYSTORE" ]] && gate 0 "release keystore present" || gate 1 "release needs a keystore — see the skill's signing reference"
  if grep -q '"file:' Packages/manifest.json 2>/dev/null; then
    warn "manifest.json has a file: dependency — this build is not reproducible off this machine:"
    grep -n '"file:' Packages/manifest.json | sed 's/^/      /'
  fi
fi

if [[ "$MODE" == "preflight" ]]; then
  [[ "$FAILED" == "0" ]] && { say "Shippable"; exit 0; } || { say "NOT shippable"; exit 1; }
fi
[[ "$FAILED" == "0" ]] || die "pre-flight gates failed — nothing was built"

# ── versionCode ───────────────────────────────────────────────────────────────────────────────

if [[ -z "$VERSION_CODE" ]]; then
  if [[ "$MODE" == "release" ]]; then
    VERSION_CODE=$(( ${CURRENT_CODE:-0} + 1 ))
    ok "versionCode ${CURRENT_CODE:-0} → $VERSION_CODE (auto-bumped; --version-code overrides)"
  else
    VERSION_CODE="${CURRENT_CODE:-1}"
  fi
fi
if [[ "$MODE" == "release" && -f "$HISTORY" ]] \
   && awk -F'\t' -v c="$VERSION_CODE" '$3==c{f=1} END{exit !f}' "$HISTORY"; then
  die "versionCode $VERSION_CODE was already built — see $HISTORY. Stores reject a re-used code."
fi

# ── tests ─────────────────────────────────────────────────────────────────────────────────────

if [[ "$RUN_TESTS" == "1" ]]; then
  say "PlayMode suite"
  rm -f /tmp/unity_build_tests.xml
  "$UNITY" -projectPath "$REPO" -runTests -testPlatform PlayMode \
           -testResults /tmp/unity_build_tests.xml -logFile /tmp/unity_build_tests.log || true
  [[ -f /tmp/unity_build_tests.xml ]] \
    || die "no results file — Unity never started (log: $(wc -l < /tmp/unity_build_tests.log 2>/dev/null || echo 0) lines)"
  RESULT="$(grep -oE 'total="[0-9]+" passed="[0-9]+"[^>]*failed="[0-9]+"' /tmp/unity_build_tests.xml | head -1)"
  info "$RESULT"
  grep -q 'failed="0"' <<<"$RESULT" || die "tests failed — not packaging. See /tmp/unity_build_tests.log"
  ok "green"
fi

# ── build ─────────────────────────────────────────────────────────────────────────────────────

SLUG="$(echo "${PRODUCT:-app}" | tr 'A-Z ' 'a-z-' | tr -cd 'a-z0-9-')"
STAMP="${STAMP:?}"
[[ -z "$OUTPUT" ]] && OUTPUT="$OUT_DIR/${SLUG}-${MODE}-${VERSION_CODE}-${STAMP}.${FORMAT}"
mkdir -p "$(dirname "$OUTPUT")"
rm -f "$OUTPUT"                       # so a stale artifact cannot be mistaken for a fresh one

BUILD_LOG="$OUT_DIR/build-${STAMP}.log"
say "Building $FORMAT → $OUTPUT"
info "(several minutes; log: $BUILD_LOG)"

# macOS ships bash 3.2, where "${arr[@]}" on an EMPTY array is an unbound-variable error under
# `set -u`. Bash 4.4 fixed it; a `env bash` shebang does not guarantee it.
AAB_FLAG=(); if [[ "$FORMAT" == "aab" ]]; then AAB_FLAG=(-aab); fi
SIGN_ARGS=()
if [[ -n "$KEYSTORE" && -f "$KEYSTORE" ]]; then
  SIGN_ARGS=(-keystore "$KEYSTORE" -keystorePass "${UNITY_KEYSTORE_PASS:-}"
             -keyalias "${UNITY_KEY_ALIAS:-}" -keyaliasPass "${UNITY_KEY_ALIAS_PASS:-}")
fi

set +e
"$UNITY" -quit -batchmode -nographics -projectPath "$REPO" \
         -buildTarget Android -executeMethod BuildScript.BuildAndroid \
         -logFile "$BUILD_LOG" -output "$OUTPUT" -versionCode "$VERSION_CODE" \
         ${AAB_FLAG[@]+"${AAB_FLAG[@]}"} ${SIGN_ARGS[@]+"${SIGN_ARGS[@]}"}
UNITY_EXIT=$?
set -e

grep '\[BUILD\]' "$BUILD_LOG" 2>/dev/null | sed 's/^/  /' || true

# Unity's exit code cannot be trusted alone: it reports 0 when it failed to start at all.
if [[ ! -f "$OUTPUT" ]]; then
  info "--- last 25 lines of $BUILD_LOG ---"
  tail -25 "$BUILD_LOG" 2>/dev/null | sed 's/^/    /'
  die "no artifact produced (unity exit $UNITY_EXIT, log $(wc -l < "$BUILD_LOG" 2>/dev/null || echo 0) lines)"
fi

# ── verify the artifact, not the exit code ────────────────────────────────────────────────────

say "Verifying $(basename "$OUTPUT")"
ok "$(du -h "$OUTPUT" | cut -f1)"

if [[ "$FORMAT" == "apk" && -x "$AAPT" ]]; then
  BADGING="$("$AAPT" dump badging "$OUTPUT" 2>/dev/null || true)"
  info "$(grep -o "package: name='[^']*' versionCode='[^']*' versionName='[^']*'" <<<"$BADGING" || echo 'package: (unreadable)')"
  info "permissions (MERGED — this is what the store sees, not your manifest):"
  grep -o "uses-permission: name='[^']*'" <<<"$BADGING" \
    | sed "s/uses-permission: name='/      /;s/'$//" | sort -u || info "      (none)"
  ABIS="$(grep -o 'native-code: .*' <<<"$BADGING" || true)"
  info "${ABIS:-native-code: (none reported — IL2CPP produced no library)}"
  grep -q "$TARGET_ABI" <<<"$ABIS" || warn "the APK does not report $TARGET_ABI"

  if [[ -x "$APKSIGNER" ]]; then
    if "$APKSIGNER" verify --print-certs "$OUTPUT" >/tmp/unity_sig.txt 2>&1; then
      DN="$(grep -m1 'Signer #1 certificate DN' /tmp/unity_sig.txt | sed 's/.*DN: //')"
      if grep -qi 'CN=Android Debug' <<<"$DN"; then
        warn "signed with the DEBUG key ($DN) — stores will reject this"
      else ok "signed: $DN"; fi
    else warn "apksigner could not verify:"; sed 's/^/      /' /tmp/unity_sig.txt | head -5; fi
  fi
elif [[ "$FORMAT" == "aab" ]]; then
  BUNDLE="$(unzip -l "$OUTPUT" 2>/dev/null || true)"
  grep -q 'base/manifest/AndroidManifest.xml' <<<"$BUNDLE" \
    && ok "valid app bundle (base/manifest present)" || die "this does not look like an app bundle"
  warn "full AAB inspection needs bundletool; upload to an internal track to see the merged result"
fi

# ── record ────────────────────────────────────────────────────────────────────────────────────

[[ -f "$HISTORY" ]] || printf 'date\tmode\tversionCode\tversionName\tpackage\tartifact\n' > "$HISTORY"
printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date +%Y-%m-%dT%H:%M)" "$MODE" "$VERSION_CODE" \
       "$VERSION_NAME" "$PACKAGE" "$(basename "$OUTPUT")" >> "$HISTORY"
ok "recorded in $(basename "$HISTORY")"

if [[ "$DO_INSTALL" == "1" ]]; then
  say "Installing"
  [[ "$FORMAT" == "aab" ]] && die "an AAB cannot be installed directly — build with --apk"
  DEVICES="$("$ADB" devices 2>/dev/null || true)"
  grep -qw device <<<"$DEVICES" || die "no device attached (an 'offline' entry is a stale wireless pairing)"
  "$ADB" install -r "$OUTPUT" && ok "installed — now LAUNCH it; stripping and shader faults only appear here"
fi

say "Done"
info "$OUTPUT"
info "result marker: $RESULT_FILE"
