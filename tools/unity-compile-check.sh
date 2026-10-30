#!/usr/bin/env bash
# unity-compile-check.sh — compile every shipped C# file of every skill in one throwaway Unity
# project, and fail on any `error CS`. Run it before a release; it needs a local Unity Editor
# and an active licence, so CI runs only the static rules (tools/check-csharp.py).
#
#   tools/unity-compile-check.sh                    # create, compile twice, delete
#   tools/unity-compile-check.sh --keep             # keep the project and print its path
#   tools/unity-compile-check.sh --reuse DIR        # re-copy the skills into a kept project and
#                                                   # compile again (warm Library: minutes, not tens)
#   tools/unity-compile-check.sh --editor 6000.4.4f1 --timeout 3600
#
# What it does
#   1. Refuses to start while any Unity Editor is running (one Editor at a time on this machine).
#   2. Creates a project from the Universal 2D template (`unity projects create`, falling back
#      to a bare folder), then merges a known-good package set into Packages/manifest.json:
#      every package the skills' C# names (Input System, Cinemachine 3, URP, 2D Sprite /
#      Animation / Tilemap / Tilemap Extras, Localization, Addressables, Splines, ProBuilder,
#      Test Framework, Performance Testing, Collections, Mathematics, Profiling Core, AI
#      Navigation, uGUI/TextMeshPro, and com.unity.pipeline for the Editor commands).
#   3. Opens it once so the packages resolve, then copies every skill's resources/ and
#      templates/ *.cs and *.asmdef to Assets/UnityDevSkills/<skill>/, keeping the folders.
#      Three generated assemblies hold them:
#        UnityDevSkills          every runtime file (all platforms)
#        UnityDevSkills.Editor   every file under an Editor/ folder (an .asmref per folder)
#        UnityDevSkills.Tests    every NUnit file, moved to a _Tests/ folder beside it (Editor
#                                only; references the two above and the test runners)
#      A folder that ships its own .asmdef (unity-game-brief's Sim / Presentation / Tests) is
#      copied as it is and compiles as its own assembly. The generated assemblies reference
#      every package assembly that resolved, read from the package folders.
#   4. Compiles twice: once as copied, once with the optional defines on (UNITY_ADDRESSABLES,
#      PERF_PROFILING_CORE, HAS_UNITY_PIPELINE, each set through versionDefines when its package
#      is present — the way the skills' docs tell a project to set them).
#   5. Prints each `error CS` mapped back to its file under skills/, and a summary.
#
# One project holds every skill at once, which works because no two skills declare the same
# global type (tools/check-csharp.py rule c keeps it that way). A file that cannot share the
# project with the rest — an alternative implementation needing a package that must not sit
# beside the others — is listed in SEPARATE below as `<skill>/<path>=<package>@<version>`. It is
# left out of the two main passes and compiled, with the rest of its skill, in a pass of its own
# with that package added; nothing is renamed. Today that is unity-2d-pixel-perfect's
# CameraSetupBuiltIn.cs: the built-in pipeline's PixelPerfectCamera comes from
# com.unity.2d.pixel-perfect, which the skill says never to add to a URP project.
#
# Exit codes: 0 no compile error in any pass; 2 a pass has `error CS` in a skill's file; 3
# harness error (an Editor already running, project creation or package resolve failed, a
# timeout, no log, or errors only inside a package — the package set is wrong, not the skills);
# 1 usage error.
#
# bash 3.2 (macOS's /bin/bash) safe. It kills only the Editor process it started, and deletes
# the project at the end unless --keep (or --reuse) is given. The Hub registration that
# `unity projects create` adds is removed again.
set -u

EDITOR_VERSION="6000.4.4f1"
TIMEOUT=3600            # seconds per Editor run; the first import of URP + Addressables is slow
KEEP=0
REUSE=""
# Files that compile in a pass of their own, with a package the main project must not have
# (see above). Space separated `<skill>/<path under the skill>=<package>@<version>`.
SEPARATE="unity-2d-pixel-perfect/resources/CameraSetupBuiltIn.cs=com.unity.2d.pixel-perfect@5.1.1"
# Files that need a build-support module, as `<skill>/<path>=<PlaybackEngines folder>`. Without
# that module installed the file is left out and named in the summary as not compiled.
NEEDS_MODULE="unity-web-release/templates/WebOptimizer.cs=WebGLSupport"

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; }
while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP=1 ;;
    --reuse) shift; REUSE="${1:-}"; [ -n "$REUSE" ] || { echo "--reuse needs a directory" >&2; exit 1; } ;;
    --editor) shift; EDITOR_VERSION="${1:-}" ;;
    --timeout) shift; TIMEOUT="${1:-}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unity-compile-check: unknown argument $1" >&2; usage >&2; exit 1 ;;
  esac
  shift
done
case "$TIMEOUT" in ''|*[!0-9]*) echo "--timeout takes seconds" >&2; exit 1 ;; esac

REPO="$(cd "$(dirname "$0")/.." && pwd)"
# The Editor puts its compiler's IPC sockets under $TMPDIR, and a Unix socket path is capped at
# 104 bytes: a long TMPDIR (a sandbox's scratch folder) fails every compile with "Unhandled
# exception during build". Editor runs get a short one; the project can live anywhere.
EDITOR_TMP=/tmp
EDITOR_PATTERN='(Contents/MacOS/Unity|/Editor/Unity)( -|$)'

say() { printf '[compile-check] %s\n' "$*"; }
die3() { say "HARNESS: $*"; exit 3; }

if pgrep -f "$EDITOR_PATTERN" >/dev/null 2>&1; then
  pgrep -fl "$EDITOR_PATTERN" | sed 's/^/  running: /'
  die3 "a Unity Editor is already running; close it first (one Editor at a time)"
fi

# --- the Editor binary ----------------------------------------------------------------------
ED_DIR=""
if command -v unity >/dev/null 2>&1; then
  ED_DIR="$(unity editors path "$EDITOR_VERSION" --format json 2>/dev/null \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["path"])' 2>/dev/null)"
fi
[ -n "$ED_DIR" ] || ED_DIR="/Applications/Unity/Hub/Editor/$EDITOR_VERSION"
if   [ -d "$ED_DIR/Unity.app" ];   then APP="$ED_DIR/Unity.app"
elif [ "${ED_DIR%.app}" != "$ED_DIR" ]; then APP="$ED_DIR"
else APP=""; fi
UNITY_BIN="$APP/Contents/MacOS/Unity"
[ -n "$APP" ] && [ -x "$UNITY_BIN" ] || die3 "no Unity $EDITOR_VERSION Editor at $ED_DIR"
BUILTIN="$APP/Contents/Resources/PackageManager/BuiltInPackages"

# --- the project ----------------------------------------------------------------------------
UNITY_PID=""
CREATED_ROOT=""
REGISTERED=""
cleanup() {
  if [ -n "$UNITY_PID" ] && kill -0 "$UNITY_PID" 2>/dev/null; then
    say "stopping the Editor this script started (pid $UNITY_PID)"
    kill "$UNITY_PID" 2>/dev/null; sleep 3; kill -9 "$UNITY_PID" 2>/dev/null
  fi
  if [ -n "$REGISTERED" ] && command -v unity >/dev/null 2>&1; then
    unity projects remove "$REGISTERED" --non-interactive >/dev/null 2>&1 || true
  fi
  if [ -n "$CREATED_ROOT" ] && [ "$KEEP" = 0 ]; then
    rm -rf "$CREATED_ROOT"
  fi
}
trap cleanup EXIT
trap 'exit 3' INT TERM

if [ -n "$REUSE" ]; then
  PROJECT="$(cd "$REUSE" 2>/dev/null && pwd)" || die3 "--reuse $REUSE: no such directory"
  [ -f "$PROJECT/Packages/manifest.json" ] || die3 "--reuse $PROJECT is not a Unity project"
  KEEP=1
else
  CREATED_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/unity-compile-check.XXXXXX")" || die3 "mktemp failed"
  PROJECT="$CREATED_ROOT/UnityDevCompileCheck"
  say "creating $PROJECT (Unity $EDITOR_VERSION, Universal 2D template)"
  if command -v unity >/dev/null 2>&1 && TMPDIR="$EDITOR_TMP" unity projects create UnityDevCompileCheck \
       --path "$CREATED_ROOT" --editor-version "$EDITOR_VERSION" \
       --template com.unity.template.universal-2d --with-pipeline --no-cloud \
       --non-interactive >"$CREATED_ROOT/create.log" 2>&1 && [ -f "$PROJECT/Packages/manifest.json" ]; then
    REGISTERED="$PROJECT"
  else
    say "unity projects create did not give a project (see below); using a bare project folder"
    tail -5 "$CREATED_ROOT/create.log" 2>/dev/null | sed 's/^/  /'
    rm -rf "$PROJECT"; mkdir -p "$PROJECT/Packages" "$PROJECT/Assets" "$PROJECT/ProjectSettings"
    printf 'm_EditorVersion: %s\n' "$EDITOR_VERSION" >"$PROJECT/ProjectSettings/ProjectVersion.txt"
    echo '{ "dependencies": {} }' >"$PROJECT/Packages/manifest.json"
  fi
  # A creation step that opened an Editor must be gone before ours starts.
  pgrep -f "$EDITOR_PATTERN" >/dev/null 2>&1 && die3 "an Editor is running after project creation"
fi
LOGDIR="$PROJECT/../compile-check-logs"; mkdir -p "$LOGDIR"; LOGDIR="$(cd "$LOGDIR" && pwd)"

# --- the known-good package set, merged over what the template brought ----------------------
python3 -B - "$PROJECT/Packages/manifest.json" <<'PY' || die3 "could not write the manifest"
import json, sys
path = sys.argv[1]
m = json.load(open(path, encoding='utf-8'))
deps = m.setdefault('dependencies', {})
want = {
    'com.unity.inputsystem': '1.19.0',
    'com.unity.cinemachine': '3.1.7',
    'com.unity.render-pipelines.universal': '17.4.0',
    'com.unity.2d.sprite': '1.0.0',
    'com.unity.2d.animation': '14.0.3',
    'com.unity.2d.tilemap': '1.0.0',
    'com.unity.2d.tilemap.extras': '7.0.1',
    'com.unity.localization': '1.5.13',
    'com.unity.addressables': '2.9.1',
    'com.unity.splines': '2.8.4',
    'com.unity.probuilder': '6.1.4',
    'com.unity.pipeline': '0.9.1-exp.1',
    'com.unity.test-framework': '1.6.0',
    'com.unity.test-framework.performance': '3.4.0',
    'com.unity.collections': '6.4.0',
    'com.unity.mathematics': '1.3.3',
    'com.unity.profiling.core': '1.0.3',
    'com.unity.ai.navigation': '2.0.12',
    'com.unity.ugui': '2.0.0',
    'com.unity.timeline': '1.8.12',
}
for k, v in want.items():
    deps[k] = v
# The template's extras this check does not need slow every import down.
for k in ('com.unity.collab-proxy', 'com.unity.visualscripting', 'com.unity.2d.psdimporter',
          'com.unity.2d.aseprite', 'com.unity.2d.spriteshape', 'com.unity.2d.tooling'):
    deps.pop(k, None)
json.dump(m, open(path, 'w', encoding='utf-8'), indent=2)
PY

# --- one Editor run, with a timeout, killing only its own process ---------------------------
run_editor() {   # $1 log file; returns the Editor's exit code, 124 on a timeout
  local log="$1" waited=0 code
  if pgrep -f "$EDITOR_PATTERN" >/dev/null 2>&1; then
    say "an Editor started by someone else is running; not starting another"; return 125
  fi
  TMPDIR="$EDITOR_TMP" "$UNITY_BIN" -batchmode -nographics -quit -projectPath "$PROJECT" \
    -logFile "$log" >/dev/null 2>&1 &
  UNITY_PID=$!
  while kill -0 "$UNITY_PID" 2>/dev/null; do
    if [ "$waited" -ge "$TIMEOUT" ]; then
      say "timed out after ${TIMEOUT}s; stopping pid $UNITY_PID"
      kill "$UNITY_PID" 2>/dev/null; sleep 5; kill -9 "$UNITY_PID" 2>/dev/null
      wait "$UNITY_PID" 2>/dev/null; UNITY_PID=""; return 124
    fi
    sleep 5; waited=$((waited + 5))
  done
  wait "$UNITY_PID"; code=$?
  UNITY_PID=""
  return $code
}

# --- layout: copy the skills and generate the assemblies -------------------------------------
LAYOUT="$LOGDIR/layout.py"
cat >"$LAYOUT" <<'PY'
"""layout.py REPO PROJECT BUILTIN MODE SKILLS... : copy the skills' C# into the project and
write the generated assemblies. MODE is `plain` or `defines`. SKILLS empty means all of them."""
import json, os, pathlib, re, shutil, sys

repo, project, builtin = (pathlib.Path(a) for a in sys.argv[1:4])
mode = sys.argv[4]
only = set(sys.argv[5:])
exclude = {e for e in os.environ.get('UCC_EXCLUDE', '').split(',') if e}
dest = project / 'Assets' / 'UnityDevSkills'
if dest.exists():
    shutil.rmtree(dest)
dest.mkdir(parents=True)

# Package assemblies that resolved: Library/PackageCache and the Editor's built-in packages.
lock = json.load(open(project / 'Packages' / 'packages-lock.json', encoding='utf-8'))['dependencies']
pkg_dirs = []
cache = project / 'Library' / 'PackageCache'
for name in lock:
    hits = sorted(cache.glob(name + '@*')) if cache.is_dir() else []
    if hits:
        pkg_dirs.append(hits[-1])
    elif (builtin / name).is_dir():
        pkg_dirs.append(builtin / name)
TEST_SUITE = re.compile(r'(?:^|\.)Tests?(?:\.|$)|Sample|Example|Demo|Benchmark', re.I)
runtime_refs, editor_refs, test_refs = set(), set(), set()
for d in pkg_dirs:
    for a in d.rglob('*.asmdef'):
        if any(p.endswith('~') or p in ('Tests', 'Samples') for p in a.relative_to(d).parts[:-1]):
            continue
        try:
            j = json.loads(a.read_text(encoding='utf-8-sig'))
        except Exception:
            continue
        name = j.get('name', '')
        if not name:
            continue
        if TEST_SUITE.search(name) and 'TestRunner' not in name and 'PerformanceTesting' not in name:
            continue
        constraints = j.get('defineConstraints') or []
        editor_only = (j.get('includePlatforms') or []) == ['Editor']
        if 'UNITY_INCLUDE_TESTS' in constraints or 'TestRunner' in name or 'PerformanceTesting' in name:
            test_refs.add(name)
            continue
        if constraints:
            continue        # only present under a define this project does not set
        (editor_refs if editor_only else runtime_refs).add(name)

skills = sorted(p for p in (repo / 'skills').iterdir() if p.is_dir() and (not only or p.name in only))
mapping = {}            # project-relative path -> repo-relative path
nunit = re.compile(r'^\s*using\s+NUnit\.Framework\s*;', re.M)
for sk in skills:
    for top in ('resources', 'templates'):
        src_root = sk / top
        if not src_root.is_dir():
            continue
        own_asm = {p.parent for p in src_root.rglob('*.asmdef')}
        for f in sorted(src_root.rglob('*')):
            if f.suffix not in ('.cs', '.asmdef') or not f.is_file():
                continue
            rel = f.relative_to(sk)
            if f'{sk.name}/{rel}' in exclude:
                continue
            in_own = any(o == f.parent or o in f.parents for o in own_asm)
            target = dest / sk.name / rel
            if not in_own and f.suffix == '.cs' and nunit.search(f.read_text(encoding='utf-8-sig', errors='replace')):
                target = dest / sk.name / rel.parent / '_Tests' / rel.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, target)
            mapping[str(target.relative_to(project))] = str(f.relative_to(repo))

def asmdef(path, name, refs, platforms=(), extra=None):
    j = {'name': name, 'rootNamespace': '', 'references': sorted(refs),
         'includePlatforms': list(platforms), 'excludePlatforms': [], 'allowUnsafeCode': True,
         'overrideReferences': False, 'precompiledReferences': [], 'autoReferenced': True,
         'defineConstraints': [], 'versionDefines': [], 'noEngineReferences': False}
    j.update(extra or {})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(j, indent=4), encoding='utf-8')

version_defines = []
if mode == 'defines':
    version_defines = [
        {'name': 'com.unity.addressables', 'expression': '', 'define': 'UNITY_ADDRESSABLES'},
        {'name': 'com.unity.profiling.core', 'expression': '', 'define': 'PERF_PROFILING_CORE'},
        {'name': 'com.unity.pipeline', 'expression': '', 'define': 'HAS_UNITY_PIPELINE'},
    ]
own = {'Game.Sim', 'Game.Presentation'} & {json.loads(p.read_text(encoding='utf-8-sig'))['name']
                                          for p in dest.rglob('*.asmdef')}
asmdef(dest / 'UnityDevSkills.asmdef', 'UnityDevSkills', runtime_refs | own,
       extra={'versionDefines': version_defines})
asmdef(dest / '_Generated' / 'Editor' / 'UnityDevSkills.Editor.asmdef', 'UnityDevSkills.Editor',
       runtime_refs | editor_refs | own | {'UnityDevSkills'}, platforms=['Editor'],
       extra={'versionDefines': version_defines})
asmdef(dest / '_Generated' / 'Tests' / 'UnityDevSkills.Tests.asmdef', 'UnityDevSkills.Tests',
       runtime_refs | editor_refs | test_refs | own | {'UnityDevSkills', 'UnityDevSkills.Editor'},
       platforms=['Editor'],
       extra={'versionDefines': version_defines, 'overrideReferences': True,
              'precompiledReferences': ['nunit.framework.dll'],
              'defineConstraints': ['UNITY_INCLUDE_TESTS'], 'autoReferenced': False})
n_editor = n_tests = 0
for d in sorted({p.parent for p in dest.rglob('*.cs')}):
    if any(q.suffix == '.asmdef' for q in d.iterdir()) or d.parent.name == '_Generated':
        continue
    parts = d.relative_to(dest).parts
    if '_Tests' in parts:
        (d / 'UnityDevSkills.Tests.asmref').write_text(json.dumps({'reference': 'UnityDevSkills.Tests'}))
        n_tests += 1
    elif d.name == 'Editor':
        (d / 'UnityDevSkills.Editor.asmref').write_text(json.dumps({'reference': 'UnityDevSkills.Editor'}))
        n_editor += 1
(project / 'Library').mkdir(exist_ok=True)
json.dump(mapping, open(pathlib.Path(sys.argv[2]).parent / 'compile-check-logs' / 'map.json', 'w'), indent=1)
print(f'{len(skills)} skills, {sum(1 for k in mapping if k.endswith(".cs"))} C# files; '
      f'{n_editor} Editor folders, {n_tests} test folders; package assemblies: '
      f'{len(runtime_refs)} runtime, {len(editor_refs)} editor, {len(test_refs)} test')
PY

REPORT="$LOGDIR/report.py"
cat >"$REPORT" <<'PY'
"""report.py LOG MAP PKGOUT : print each `error CS` in the skills' files once, mapped back under
skills/; errors inside a package go to PKGOUT instead."""
import json, re, sys
log, mapping = open(sys.argv[1], encoding='utf-8', errors='replace').read(), json.load(open(sys.argv[2]))
seen, out, pkg = set(), [], []
for m in re.finditer(r'^(?P<file>[^\n(]+\.cs)\((?P<pos>\d+,\d+)\): error (?P<code>CS\d+): (?P<msg>[^\n]*)$', log, re.M):
    f = m.group('file').strip()
    key = (f, m.group('pos'), m.group('code'))
    if key in seen:
        continue
    seen.add(key)
    line = f"{mapping.get(f, f)}({m.group('pos')}): {m.group('code')}: {m.group('msg')}"
    (pkg if f.startswith(('Library/', 'Packages/')) else out).append(line)
print('\n'.join(out))
if pkg:
    open(sys.argv[3], 'w').write('\n'.join(pkg) + '\n')
PY

# --- passes ----------------------------------------------------------------------------------
# The generated assemblies reference the package assemblies found on disk, so packages resolve
# in a run of their own, with no skill code in the project, whenever the manifest changed.
resolve_packages() {
  local rc
  if [ -f "$LOGDIR/manifest.resolved.json" ] && [ -f "$PROJECT/Packages/packages-lock.json" ] \
     && cmp -s "$PROJECT/Packages/manifest.json" "$LOGDIR/manifest.resolved.json"; then
    return 0
  fi
  rm -rf "$PROJECT/Assets/UnityDevSkills" "$PROJECT/Assets/UnityDevSkills.meta"
  say "resolving packages (slow on a new project)"
  run_editor "$LOGDIR/resolve.log"; rc=$?
  [ $rc -eq 124 ] && die3 "package resolve timed out"
  [ $rc -eq 125 ] && die3 "an Editor was running"
  [ -f "$PROJECT/Packages/packages-lock.json" ] || die3 "packages did not resolve; see $LOGDIR/resolve.log"
  if grep -q "An error occurred while resolving packages" "$LOGDIR/resolve.log" 2>/dev/null; then
    grep -A8 "An error occurred while resolving packages" "$LOGDIR/resolve.log" | head -20
    die3 "package resolve failed; see $LOGDIR/resolve.log"
  fi
  cp "$PROJECT/Packages/manifest.json" "$LOGDIR/manifest.resolved.json"
}
resolve_packages

TOTAL=0
PKG_ERRORS=0
SUMMARY=""
compile_pass() {   # $1 pass name, $2 mode (plain|defines), $3.. skills (empty = all)
  local name="$1" mode="$2" log rc n np; shift 2
  log="$LOGDIR/compile-$name.log"
  python3 -B "$LAYOUT" "$REPO" "$PROJECT" "$BUILTIN" "$mode" "$@" || die3 "layout failed"
  say "pass $name: compiling"
  run_editor "$log"; rc=$?
  [ $rc -eq 124 ] && die3 "pass $name timed out"
  [ $rc -eq 125 ] && die3 "an Editor was running"
  [ -s "$log" ] || die3 "pass $name left no log"
  rm -f "$LOGDIR/package-errors-$name.txt"
  python3 -B "$REPORT" "$log" "$LOGDIR/map.json" "$LOGDIR/package-errors-$name.txt" \
    >"$LOGDIR/errors-$name.txt"
  n=$(grep -c . "$LOGDIR/errors-$name.txt" | tr -d ' ')
  np=0
  if [ -f "$LOGDIR/package-errors-$name.txt" ]; then
    np=$(grep -c . "$LOGDIR/package-errors-$name.txt" | tr -d ' ')
    say "pass $name: $np error(s) inside packages — the package set is wrong, and every assembly"
    say "  that references the failed one went uncompiled:"
    sed 's/^/  /' "$LOGDIR/package-errors-$name.txt" | cut -c1-240
    PKG_ERRORS=$((PKG_ERRORS + np))
  fi
  if [ "$n" -gt 0 ]; then
    sed 's/^/  /' "$LOGDIR/errors-$name.txt"
  elif [ $rc -ne 0 ] && [ "$np" -eq 0 ]; then
    grep -m3 -A3 "Unhandled exception during build\|Scripts have compiler errors\|error " "$log" | cut -c1-240
    die3 "pass $name: the Editor exited $rc with no error CS to report; see $log"
  fi
  say "pass $name: $n error(s) in skill files, Editor exit $rc"
  TOTAL=$((TOTAL + n))
  SUMMARY="$SUMMARY
  $name: $n error CS"
}

EXCLUDE=""
NOT_COMPILED=""
for entry in $SEPARATE; do EXCLUDE="$EXCLUDE,${entry%%=*}"; done
for entry in $NEEDS_MODULE; do
  if [ ! -d "$ED_DIR/PlaybackEngines/${entry#*=}" ]; then
    EXCLUDE="$EXCLUDE,${entry%%=*}"
    NOT_COMPILED="$NOT_COMPILED
  ${entry%%=*}: needs the ${entry#*=} module, not installed in this Editor"
  fi
done
for mode in plain defines; do
  UCC_EXCLUDE="$EXCLUDE" compile_pass "$mode" "$mode"
done
for entry in $SEPARATE; do
  file="${entry%%=*}"; pkg="${entry#*=}"; skill="${file%%/*}"
  cp "$PROJECT/Packages/manifest.json" "$LOGDIR/manifest.main.json"
  python3 -B - "$PROJECT/Packages/manifest.json" "${pkg%@*}" "${pkg##*@}" <<'PY' || die3 "manifest edit failed"
import json, sys
m = json.load(open(sys.argv[1], encoding='utf-8'))
m['dependencies'][sys.argv[2]] = sys.argv[3]
json.dump(m, open(sys.argv[1], 'w', encoding='utf-8'), indent=2)
PY
  say "separate pass for $file, with $pkg added"
  resolve_packages
  UCC_EXCLUDE="" compile_pass "separate-$skill" plain "$skill"
  cp "$LOGDIR/manifest.main.json" "$PROJECT/Packages/manifest.json"
done
[ -n "$NOT_COMPILED" ] && say "not compiled on this machine:$NOT_COMPILED"

say "summary:$SUMMARY"
if pgrep -f "$EDITOR_PATTERN" >/dev/null 2>&1; then say "note: a Unity Editor is running now (not one this script started)"; fi
if [ "$KEEP" = 1 ]; then say "project kept at $PROJECT (logs in $LOGDIR)"; fi
if [ "$TOTAL" -gt 0 ]; then
  [ "$KEEP" = 1 ] || say "rerun with --keep to look at the logs"
  exit 2
fi
[ "$PKG_ERRORS" -gt 0 ] && die3 "errors only inside packages; fix the package set in this script"
say "no compile errors"
exit 0
