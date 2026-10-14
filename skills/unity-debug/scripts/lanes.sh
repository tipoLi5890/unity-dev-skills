#!/usr/bin/env bash
#
# lanes.sh — several Unity Editors on one project at once, one Editor per test lane.
#
# Unity allows one Editor per PROJECT FOLDER (Temp/UnityLockfile), not one per machine. A test lane
# is another project folder beside the repo: Assets, Packages and ProjectSettings are links back to
# the repo, Library is a copy, Temp and Logs are its own. Every lane sees the same code and each can
# hold its own Editor. Lane 0 is the repo itself. The method: reference/parallel-runs.md.
#
#   lanes.sh setup [N]   build clone lanes 1..N (default 2); idempotent, and restartable after an
#                        interrupted copy. Holds lane 0 while copying its Library; refuses (6) while
#                        an Editor has the repo open.
#   lanes.sh status      every lane: free, busy (pid), Editor open, or a lockfile nobody claims
#   lanes.sh clean       remove every clone lane; refuses (6) while one is busy. Never touches lane 0
#   lanes.sh run [--main-only] [--lane K] [--no-wait] -- <Editor arguments>
#
# run takes a free lane, replaces {project} and {lane} in the arguments, exports LANE=<K> and
# $LANE_DATA_VAR=<prefix>_data_lane<K> (lane 0 runs with it unset), deletes the -testResults file
# it is about to write, runs the Editor with no pipe, releases the lane on every exit path, and
# returns the Editor's own exit code. It prints [LANE] lines: lane and project first, then the
# exit code, the log's line count and whether the results file exists.
#
#   --main-only   lane 0 only: work that writes Assets, Packages or ProjectSettings
#   --lane K      that lane only
#   --no-wait     exit 6 at once when no lane is free. The default is to queue: busy is normal.
#
# Read-only runs try clone lanes first and lane 0 last, so lane 0 stays free for --main-only work.
# With no -projectPath among the arguments, -projectPath <lane> is appended; one that names any
# other folder is refused, because the lane's lock would not cover it.
#
#   lanes.sh run -- -projectPath '{project}' -runTests -testPlatform PlayMode \
#       -testResults '/tmp/courier_play_lane{lane}.xml' -logFile '/tmp/courier_play_lane{lane}.log'
#   lanes.sh run --main-only -- -batchmode -nographics -projectPath '{project}' \
#       -executeMethod CourierRun.EditorTools.Scaffold.BuildGates -quit -logFile /tmp/courier_gen.log
#
# Quote the tokens: zsh reads `{project} >file` as a redirection into a variable named project.
#
# Environment (all optional):
#   PROJECT            the repo, lane 0                          default: the current directory
#   LANES_ROOT         where clone lanes live                    default: <repo>.lanes, beside it
#   LANE_LOCK_PREFIX   lane K's lock directory is <prefix>K.lock default: /tmp/<repo folder>_lane
#   LANE_DATA_PREFIX   lane K's data dir is <prefix>_data_laneK  default: /tmp/<repo folder>
#   LANE_DATA_VAR      the variable that carries the data dir    default: GAME_DATA_DIR
#                      (resources/LaneDataPath.cs reads it; keep the two names in step)
#   LANE_LINKS         folders linked from the repo              default: Assets Packages ProjectSettings
#   LANE_WAIT_SECONDS  how long run and setup queue for a lane   default: 3600
#   LANE_POLL_SECONDS  how often a queued run looks again        default: 10
#   UNITY              the Editor binary     default: the Hub install of ProjectVersion.txt's version
#
# Exit: run returns the Editor's code whenever the Editor ran. Otherwise 3 = the harness could not
# run anything (bad arguments, not a Unity project, no Editor binary, lane K not set up, a copy
# that failed, an unsupported OS for setup) · 6 = no lane free (--no-wait, or the wait ran out),
# or setup/clean refused because an Editor or a run holds a lane they must touch.
#
# macOS /bin/bash 3.2 compatible: no associative arrays, no mapfile, no ${var,,}.

set -u

MARKER=".lane-ready"

die()  { echo "lanes.sh: $*" >&2; exit 3; }
busy() { echo "lanes.sh: $*" >&2; exit 6; }

# ── configuration ─────────────────────────────────────────────────────────────────────────────

PROJECT="${PROJECT:-$PWD}"
[ -d "$PROJECT" ] || die "PROJECT=$PROJECT is not a directory"
PROJECT="$(cd "$PROJECT" && pwd -P)"
NAME="$(printf '%s' "$(basename "$PROJECT")" | tr -c 'A-Za-z0-9_.-' '_')"

LANES_ROOT="${LANES_ROOT:-$PROJECT.lanes}"
case "$LANES_ROOT" in /*) ;; *) LANES_ROOT="$PWD/$LANES_ROOT" ;; esac
LANE_LOCK_PREFIX="${LANE_LOCK_PREFIX:-/tmp/${NAME}_lane}"
LANE_DATA_PREFIX="${LANE_DATA_PREFIX:-/tmp/${NAME}}"
LANE_DATA_VAR="${LANE_DATA_VAR:-GAME_DATA_DIR}"
LANE_LINKS="${LANE_LINKS:-Assets Packages ProjectSettings}"
LANE_WAIT_SECONDS="${LANE_WAIT_SECONDS:-3600}"
LANE_POLL_SECONDS="${LANE_POLL_SECONDS:-10}"

case "$LANE_DATA_VAR" in ''|[0-9]*|*[!A-Za-z0-9_]*) die "LANE_DATA_VAR='$LANE_DATA_VAR' is not a variable name" ;; esac
case "$LANE_WAIT_SECONDS$LANE_POLL_SECONDS" in *[!0-9]*) die "LANE_WAIT_SECONDS and LANE_POLL_SECONDS are whole seconds" ;; esac
[ "$LANE_POLL_SECONDS" -gt 0 ] || die "LANE_POLL_SECONDS must be at least 1"

default_unity() {
  local v
  v="$(sed -n 's/^m_EditorVersion: *//p' "$PROJECT/ProjectSettings/ProjectVersion.txt" 2>/dev/null | tr -d '\r')"
  [ -n "$v" ] || return 1
  case "$(uname -s)" in
    Darwin) echo "/Applications/Unity/Hub/Editor/$v/Unity.app/Contents/MacOS/Unity" ;;
    Linux)  echo "$HOME/Unity/Hub/Editor/$v/Editor/Unity" ;;
    *)      return 1 ;;
  esac
}

# ── lanes ─────────────────────────────────────────────────────────────────────────────────────

lane_dir()  { if [ "$1" = 0 ]; then echo "$PROJECT"; else echo "$LANES_ROOT/lane$1"; fi; }
lane_lock() { echo "${LANE_LOCK_PREFIX}$1.lock"; }
lane_data() { if [ "$1" = 0 ]; then echo "-"; else echo "${LANE_DATA_PREFIX}_data_lane$1"; fi; }

clone_lanes() { # the numbers of the clone lanes that finished setup, ascending
  local d k
  for d in "$LANES_ROOT"/lane*; do
    [ -f "$d/$MARKER" ] || continue
    k="${d##*/lane}"
    case "$k" in ''|*[!0-9]*) continue ;; esac
    echo "$k"
  done | sort -n
}

# A process that is gone, or a zombie nobody has reaped yet, holds nothing. `ps`, not `kill -0`:
# kill -0 on a live process owned by another user fails with EPERM and reads as "not running".
alive() {
  local s
  [ -n "${1:-}" ] || return 1
  s="$(ps -o stat= -p "$1" 2>/dev/null)" || return 1
  case "$s" in ''|Z*) return 1 ;; esac
  return 0
}

# An Editor launched with -projectPath <dir>. Matching the EDITOR BINARY matters: a looser pattern
# also matches the compiler server and the licensing client, which outlive every Editor.
re_escape() { printf '%s' "$1" | sed 's/[][\.*^$+?(){}|]/\\&/g'; }
editor_on() {
  local re
  re="$(re_escape "$1")"
  pgrep -f "(Contents/MacOS/Unity|/Editor/Unity)( -.*)? -projectPath +\"?${re}/?(\"| |\$)" >/dev/null 2>&1
}
# An Editor launched without -projectPath on its command line is invisible to pgrep; its lockfile
# is not. A lockfile with no Editor behind it is a corpse — `status` says which.
lockfile_in() { [ -e "$1/Temp/UnityLockfile" ]; }

# ── locks: mkdir is atomic, the pid file says whether the holder still lives ──────────────────

HELD=()
hold()    { HELD=(${HELD[@]+"${HELD[@]}"} "$1"); }
release() {
  local l
  for l in ${HELD[@]+"${HELD[@]}"}; do
    [ "$(cat "$l/pid" 2>/dev/null)" = "$$" ] && rm -rf "$l"
  done
  HELD=()
}

try_lock() { # try_lock <lock dir>: 0 when this process now holds it
  local l="$1" other
  if mkdir "$l" 2>/dev/null; then echo "$$" > "$l/pid"; hold "$l"; return 0; fi
  other="$(cat "$l/pid" 2>/dev/null)"
  if [ -z "$other" ]; then
    # mkdir's winner writes its pid a moment later: an empty file is far likelier to be a lock
    # a millisecond old than an abandoned one. Look again before treating it as dead.
    sleep 1
    other="$(cat "$l/pid" 2>/dev/null)"
  fi
  alive "$other" && return 1
  rm -rf "$l"
  mkdir "$l" 2>/dev/null || return 1
  echo "$$" > "$l/pid"
  # Two callers can see the same dead holder; the one whose pid is still there a second later won.
  sleep 1
  [ "$(cat "$l/pid" 2>/dev/null)" = "$$" ] || return 1
  hold "$l"
  return 0
}

PICKED=""; PICKED_DIR=""
pick_lane() { # pick_lane <order> <wait 0|1>
  local order="$1" wait="$2" waited=0 said="" k d why
  while :; do
    why=""
    for k in $order; do
      d="$(lane_dir "$k")"
      if try_lock "$(lane_lock "$k")"; then
        if editor_on "$d"; then release; why="$why lane$k=editor-open"; continue; fi
        if lockfile_in "$d"; then release; why="$why lane$k=lockfile"; continue; fi
        PICKED="$k"; PICKED_DIR="$d"
        [ "$waited" -gt 0 ] && echo "[LANE] lane $k free after ${waited}s" >&2
        return 0
      fi
      why="$why lane$k=busy"
    done
    if [ "$wait" != 1 ]; then echo "[LANE] no lane free:$why" >&2; return 1; fi
    if [ "$waited" -ge "$LANE_WAIT_SECONDS" ]; then
      echo "[LANE] no lane free after ${waited}s:$why  (lanes.sh status)" >&2; return 1
    fi
    [ -z "$said" ] && { echo "[LANE] every lane is taken:$why — queueing (every ${LANE_POLL_SECONDS}s)" >&2; said=1; }
    sleep "$LANE_POLL_SECONDS"; waited=$((waited + LANE_POLL_SECONDS))
  done
}

# ── setup ─────────────────────────────────────────────────────────────────────────────────────

copy_library() { # copy_library <lane dir>: into a temporary name first, so a cut-off copy is never "done"
  local d="$1" tmp="$1/Library.copying" how
  rm -rf "$tmp" "$d/Library"
  case "$(uname -s)" in
    Darwin)
      # APFS clonefile: seconds, and no second copy on disk until a block changes.
      if cp -cR "$PROJECT/Library" "$tmp" 2>/dev/null; then how="clonefile (cp -cR)"
      else
        rm -rf "$tmp"; echo "  ! cp -c failed (not an APFS volume?) — making a full copy" >&2
        cp -R "$PROJECT/Library" "$tmp" || return 1; how="full copy (cp -R)"
      fi ;;
    Linux)
      if cp -a --reflink=auto "$PROJECT/Library" "$tmp" 2>/dev/null; then how="cp -a --reflink=auto"
      else rm -rf "$tmp"; cp -a "$PROJECT/Library" "$tmp" || return 1; how="cp -a"; fi ;;
    *) return 1 ;;
  esac
  # The asset databases' lock files describe the repo's Editor, not this lane's.
  rm -f "$tmp/ArtifactDB-lock" "$tmp/SourceAssetDB-lock"
  mv "$tmp" "$d/Library" || return 1
  echo "  Library: $how"
}

take_lane0_for_copy() {
  local waited=0 said=""
  while ! try_lock "$(lane_lock 0)"; do
    [ "$waited" -ge "$LANE_WAIT_SECONDS" ] && busy "lane 0 still held after ${waited}s (lanes.sh status)"
    [ -z "$said" ] && { echo "[LANE] waiting for lane 0 to copy its Library" >&2; said=1; }
    sleep "$LANE_POLL_SECONDS"; waited=$((waited + LANE_POLL_SECONDS))
  done
  if editor_on "$PROJECT" || lockfile_in "$PROJECT"; then
    release
    busy "an Editor has $PROJECT open (or left Temp/UnityLockfile behind): close it first — a Library copied while an Editor writes it gives the lane a torn database"
  fi
}

cmd_setup() {
  local n="${1:-2}" k d x
  case "$n" in ''|*[!0-9]*) die "setup takes a number of lanes" ;; esac
  [ "$n" -ge 1 ] || die "setup takes a number of lanes"
  [ -f "$PROJECT/ProjectSettings/ProjectVersion.txt" ] || die "$PROJECT is not a Unity project (no ProjectSettings/ProjectVersion.txt)"
  [ -d "$PROJECT/Library" ] || die "$PROJECT has no Library yet: open it once, or run one batchmode compile on it, so lanes copy an imported Library instead of each importing from scratch"
  case "$(uname -s)" in
    Darwin|Linux) ;;
    *) die "setup knows macOS and Linux; on Windows build lanes with junctions (reference/parallel-runs.md)" ;;
  esac
  mkdir -p "$LANES_ROOT" || die "cannot create $LANES_ROOT"
  LANES_ROOT="$(cd "$LANES_ROOT" && pwd -P)"
  case "$LANES_ROOT/" in "$PROJECT/"*) die "LANES_ROOT is inside the repo; put it beside the repo" ;; esac
  trap release EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM

  k=1
  while [ "$k" -le "$n" ]; do
    d="$LANES_ROOT/lane$k"
    if [ -f "$d/$MARKER" ]; then echo "[LANE] lane$k ready  $d"; k=$((k + 1)); continue; fi
    mkdir -p "$d" || die "cannot create $d"
    for x in $LANE_LINKS; do
      if [ ! -e "$PROJECT/$x" ]; then echo "  lane$k: the repo has no $x — not linked"; continue; fi
      if [ -e "$d/$x" ] && [ ! -L "$d/$x" ]; then
        die "$d/$x is a real folder, not a link: lanes.sh clean, then set up again"
      fi
      ln -sfn "$PROJECT/$x" "$d/$x" || die "cannot link $d/$x"
    done
    [ ${#HELD[@]} -gt 0 ] || take_lane0_for_copy
    echo "[LANE] lane$k copying Library from lane 0"
    copy_library "$d" || die "copying Library into $d failed"
    touch "$d/$MARKER"
    echo "[LANE] lane$k ready  $d"
    k=$((k + 1))
  done
  release
}

# ── status and clean ──────────────────────────────────────────────────────────────────────────

lane_state() { # one word-ish description of lane $1
  local k="$1" d holder
  d="$(lane_dir "$k")"
  holder="$(cat "$(lane_lock "$k")/pid" 2>/dev/null)"
  if alive "$holder"; then echo "busy (pid $holder)"
  elif editor_on "$d"; then echo "Editor open"
  elif lockfile_in "$d"; then echo "lockfile, no run holds it (an Editor launched without -projectPath, or a corpse: rm $d/Temp/UnityLockfile once nothing runs)"
  elif [ -n "$holder" ]; then echo "free (stale lock of pid $holder; the next run reclaims it)"
  else echo "free"
  fi
}

cmd_status() {
  local k d
  echo "[LANE] project=$PROJECT lanes=$LANES_ROOT locks=${LANE_LOCK_PREFIX}<K>.lock $LANE_DATA_VAR=${LANE_DATA_PREFIX}_data_lane<K>"
  for k in 0 $(clone_lanes); do
    printf 'lane%-3s %s  %s\n' "$k" "$(lane_state "$k")" "$(lane_dir "$k")"
  done
  for d in "$LANES_ROOT"/lane*; do
    [ -d "$d" ] && [ ! -f "$d/$MARKER" ] && printf 'lane%-3s not ready (setup interrupted? run setup again)  %s\n' "${d##*/lane}" "$d"
  done
  return 0
}

cmd_clean() {
  local d k why=""
  [ -d "$LANES_ROOT" ] || { echo "[LANE] nothing to clean: no $LANES_ROOT"; return 0; }
  trap release EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  # Hold every clone lane while deleting, so no run can pick one half-way through.
  for d in "$LANES_ROOT"/lane*; do
    [ -d "$d" ] || continue
    k="${d##*/lane}"
    case "$k" in ''|*[!0-9]*) continue ;; esac
    if ! try_lock "$(lane_lock "$k")"; then why="$why lane$k=busy"; continue; fi
    editor_on "$d" && why="$why lane$k=editor-open"
    lockfile_in "$d" && why="$why lane$k=lockfile"
  done
  if [ -n "$why" ]; then release; busy "refusing to clean:$why  (lanes.sh status)"; fi
  for d in "$LANES_ROOT"/lane*; do
    [ -d "$d" ] || continue
    k="${d##*/lane}"
    case "$k" in ''|*[!0-9]*) continue ;; esac
    rm -f "$d/$MARKER"
    rm -rf "$d" && echo "[LANE] removed $d"
  done
  release
  rmdir "$LANES_ROOT" 2>/dev/null && echo "[LANE] removed $LANES_ROOT" \
    || echo "[LANE] left $LANES_ROOT: it holds files that are not lanes"
  return 0
}

# ── run ───────────────────────────────────────────────────────────────────────────────────────

REPLY=""
replace_all() { # replace_all <text> <token> <value> → REPLY. No ${x//p/r}: bash 5.2 reads & in r.
  local s="$1" out=""
  while :; do
    case "$s" in
      *"$2"*) out="$out${s%%"$2"*}$3"; s="${s#*"$2"}" ;;
      *) break ;;
    esac
  done
  REPLY="$out$s"
}

UNITY_PID=""
on_exit() {
  local rc=$? g=0
  if alive "$UNITY_PID"; then
    kill "$UNITY_PID" 2>/dev/null
    while alive "$UNITY_PID" && [ "$g" -lt 15 ]; do sleep 1; g=$((g + 1)); done
    alive "$UNITY_PID" && kill -9 "$UNITY_PID" 2>/dev/null
    echo "[LANE] lane=$PICKED stopped the Editor (pid $UNITY_PID) on the way out" >&2
    sleep 1
    clear_corpse
  fi
  release
  exit "$rc"
}

clear_corpse() { # the Editor this run started is gone; a lockfile it left would block the lane
  [ -n "$PICKED_DIR" ] && lockfile_in "$PICKED_DIR" || return 0
  editor_on "$PICKED_DIR" && return 0
  rm -f "$PICKED_DIR/Temp/UnityLockfile" && echo "[LANE] lane=$PICKED removed the Temp/UnityLockfile its Editor left behind" >&2
}

cmd_run() {
  local mainonly=0 forced="" wait=1 order a prev="" has_pp=0 results="" log="" rc lines v want
  while [ $# -gt 0 ]; do
    case "$1" in
      --main-only) mainonly=1 ;;
      --lane)      [ $# -ge 2 ] || die "--lane needs a lane number"; forced="$2"; shift ;;
      --no-wait)   wait=0 ;;
      --wait)      wait=1 ;;
      --)          shift; break ;;
      *)           break ;;
    esac
    shift
  done
  [ $# -gt 0 ] || die "run needs the Editor's arguments after --"
  [ -f "$PROJECT/ProjectSettings/ProjectVersion.txt" ] || die "$PROJECT is not a Unity project (no ProjectSettings/ProjectVersion.txt)"

  if [ -n "$forced" ]; then
    case "$forced" in *[!0-9]*) die "--lane takes a lane number" ;; esac
    [ "$mainonly" = 1 ] && [ "$forced" != 0 ] && die "--main-only and --lane $forced contradict each other"
    [ "$forced" = 0 ] || [ -f "$(lane_dir "$forced")/$MARKER" ] || die "lane $forced is not set up (lanes.sh setup $forced)"
    order="$forced"
  elif [ "$mainonly" = 1 ]; then
    order="0"
  else
    order="$(clone_lanes | tr '\n' ' ')0"
  fi

  UNITY="${UNITY:-$(default_unity)}"
  [ -n "$UNITY" ] && [ -x "$UNITY" ] || die "no Editor binary at '${UNITY}' — set UNITY to the Editor executable"

  trap on_exit EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  pick_lane "$order" "$wait" || exit 6

  ARGS=()
  for a in "$@"; do
    replace_all "$a" "{project}" "$PICKED_DIR"
    replace_all "$REPLY" "{lane}" "$PICKED"
    a="$REPLY"
    case "$prev" in
      -projectPath)
        has_pp=1
        v="$(cd "$a" 2>/dev/null && pwd -P)"
        want="$(cd "$PICKED_DIR" && pwd -P)"
        [ "$v" = "$want" ] || die "-projectPath $a is not lane $PICKED ($PICKED_DIR): pass -projectPath {project}"
        ;;
      -testResults) results="$a" ;;
      -logFile)     log="$a" ;;
    esac
    ARGS=(${ARGS[@]+"${ARGS[@]}"} "$a")
    prev="$a"
  done
  case "$prev" in
    -projectPath|-testResults|-logFile|-executeMethod|-testPlatform|-testFilter|-testCategory|-assemblyNames|-buildTarget)
      die "$prev is the last argument and has no value (in zsh, quote '{project}': zsh reads {name}>file as a redirection)" ;;
  esac
  [ "$has_pp" = 1 ] || ARGS=("${ARGS[@]}" -projectPath "$PICKED_DIR")
  for v in "$results" "$log"; do
    case "$v" in ''|/*|-) ;; *) echo "[LANE] warning: $v is relative — the Editor may resolve it against the lane, not here; pass an absolute path" >&2 ;; esac
  done

  export LANE="$PICKED"
  if [ "$PICKED" = 0 ]; then
    unset "$LANE_DATA_VAR"
    echo "[LANE] lane=0 project=$PICKED_DIR $LANE_DATA_VAR=(unset: persistentDataPath)"
  else
    export "$LANE_DATA_VAR=$(lane_data "$PICKED")"
    echo "[LANE] lane=$PICKED project=$PICKED_DIR $LANE_DATA_VAR=$(lane_data "$PICKED")"
  fi
  if [ -n "$results" ]; then
    rm -f "$results"
    echo "[LANE] results=$results (deleted before the run: a file there afterwards is this run's)"
  fi
  [ -n "$log" ] && echo "[LANE] log=$log"
  printf '[LANE] exec %q' "$UNITY"; printf ' %q' "${ARGS[@]}"; echo

  # In the background so a Ctrl-C or a TERM reaches the trap, which stops the Editor before the
  # lane is released. The exit code is wait's, never a pipe's.
  "$UNITY" "${ARGS[@]}" &
  UNITY_PID=$!
  wait "$UNITY_PID"; rc=$?
  UNITY_PID=""
  clear_corpse

  lines="-"
  if [ -n "$log" ] && [ "$log" != "-" ]; then lines="$(wc -l < "$log" 2>/dev/null | tr -d ' ')"; lines="${lines:-0}"; fi
  v=""
  if [ -n "$results" ]; then
    if [ -f "$results" ]; then v=" results=present"; else v=" results=MISSING"; fi
  fi
  echo "[LANE] lane=$PICKED exit=$rc log=$lines lines${v}"
  exit "$rc"
}

# ── main ──────────────────────────────────────────────────────────────────────────────────────

cmd="${1:-status}"
[ $# -gt 0 ] && shift
case "$cmd" in
  setup)  cmd_setup "$@" ;;
  status) cmd_status ;;
  clean)  cmd_clean ;;
  run)    cmd_run "$@" ;;
  -h|--help|help) sed -n '2,/^# macOS/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "usage: lanes.sh setup [N] | status | clean | run [--main-only] [--lane K] [--no-wait] -- <Editor arguments>" >&2; exit 3 ;;
esac
