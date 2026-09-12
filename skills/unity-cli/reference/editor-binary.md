# The Editor binary as a CLI — exit codes, guards, and the wrapper around them

> Part of the `unity-cli` skill. **The exit-code table in `SKILL.md` is the `unity` CLI's own.
> It does not apply here.** `Unity.app/Contents/MacOS/Unity` is a different program with a
> different (and undocumented) set, and mapping one onto the other is how a run that never
> happened gets reported as green.

Unity documents none of these codes as a contract, so treat them as diagnostic hints and take the
**verdict from the results file**, never from `$?`.

---

## 1. The codes, and what each one means

| Exit | Cause | Results XML | Log length |
|---|---|---|---|
| `0` | Real success — **and also**: another Editor holds the project lock; `-quit` given to an async `-executeMethod`; a bad CLI argument | absent when nothing ran | tens of lines when nothing ran |
| `1` | A compile error in **any** assembly — `-batchmode` EditMode `-runTests`, and `-executeMethod` | none written | several hundred lines (~850–950) |
| `2` | Tests ran and some failed | **written**, `failed` > 0 | full-length |
| `3` | Windowed PlayMode `-runTests` that never started — a compile error, which a batchmode run reports as `1` instead | none written | several hundred lines (~850–950) |
| `198` | No valid Editor licence (`No valid Unity Editor license` in the log; sometimes `com.unity.editor.headless not found`) | none | tens of lines |

Two things fall out of that table:

- **The same kind of fault produces different codes depending on how you invoked it.** An
  ordinary compile error gives `1` from a batchmode EditMode run (e.g. `error CS0119`) and `3`
  from a windowed PlayMode run (e.g. `error CS0102`). So `1` vs `3` is not "compile" vs "something
  else"; both mean *nothing ran*, and what changes the code is how the run was launched.
- **`2` is a verdict, not a crash.** A run reporting `exit=2` alongside
  `total="70" passed="69" failed="1"` is the harness working correctly. Do not retry it; the
  reasoning is in `unity-debug` → `reference/harness-trust.md`.

## 2. The verdict lives in the results XML, not in `$?`

`unity-debug` → `reference/harness-trust.md` owns the *why* (a 36-minute-old XML read as four
consecutive passes). The mechanics for this binary:

```bash
rm -f "$xml"                                     # before the run — a stale XML reads as a pass
"$UNITY" -batchmode -projectPath "$PWD" -runTests -testPlatform EditMode \
         -testResults "$xml" -logFile "$log"     # NEVER also pass -quit
echo "exit=$? log=$(wc -l < "$log") lines"
grep -o 'total="[0-9]*" passed="[0-9]*"[^>]*failed="[0-9]*"' "$xml" | head -1
```

If the XML is missing, the run did not happen, and the cause is in the log:

```bash
grep -E "error CS|Aborting batchmode|No valid Unity Editor license" "$log" | sort -u
```

For example, an `exit 3` traces this way to
`Assets/Games/<Project>/<Project>Game.cs(31,145): error CS1026: ) expected` — a scripted edit that
inserted a `//` comment into the middle of a multi-line argument list, commenting out the closing
`);`.

> **Log length separates "never started" from "started", and nothing finer.** A run blocked by
> another Editor or a locked project leaves tens of lines (about **30–45**); a compile failure
> leaves several hundred (about **850–950**); a real EditMode run can leave fewer than that (about
> **760**, `exit=2`, one test failed), and a full PlayMode run leaves thousands. So tens of lines
> means the Editor never came up — but several hundred lines does **not** distinguish a compile
> failure from a real EditMode run. Use the XML for that, and calibrate the bands on your own
> project before a wrapper branches on them.

## 3. `198` is an account session, not a project problem

Every headless invocation starts failing at once — `-executeMethod`, `-runTests`, builds — each
with a short log saying `No valid Unity Editor license`. Nothing about the project changed; the
`unity` CLI's login session went stale (`unity auth status` reports `stale`).

```bash
unity license status --format json    # healthy output below
```

```json
{"success":true,"data":{"active":true,"signedIn":true,"authMode":"oauth",
 "licenses":[{"product":"Unity Personal Version","type":"Assigned"}]}}
```

**Branch on `data.active`, not on the exit code** — the same rule as every other command in this
CLI (`SKILL.md` → the conventions). `active:false` → `unity auth login`, or open Unity Hub once.
Make it the first line of any session that will drive the Editor: it costs under a second and it
is otherwise an hour of reading a log that looks exactly like a compile failure.

Cheap grep for a wrapper, without a JSON parser:

```bash
unity license status --format json | grep -q '"active":[[:space:]]*true' \
  || { echo "no active licence — run: unity auth login" >&2; exit 4; }
```

## 4. `-executeMethod` is blocked by *any* assembly's compile error

Unity compiles every assembly before it will invoke anything, so a broken **test** file stops an
Editor method that has nothing to do with tests. Worked example: a font-building entry point
returns `exit=1` with a 940-line log and never runs; the cause is six copies of
`Assets/Tests/EditMode/CoreTests.cs(98,90): error CS0103: The name 'SystemLanguage' does not
exist in the current context` — one test file missing a `using UnityEngine;`. Fix that one file
and the identical command succeeds.

**So: `grep -E 'error CS' <logfile> | sort -u` before you conclude the failure is in your
method.** The first `error CS` line is usually in a file you were not thinking about.

## 5. Which entry points must not be given `-quit`

| Entry point shape | `-quit`? | Why |
|---|---|---|
| Synchronous method ending in `EditorApplication.Exit(code)` | Safe | Nothing is pending when it returns |
| Anything that starts an **async** Editor operation | **Never** | The Editor exits before the first `EditorApplication.update` tick — exit 0, nothing done |
| `-runTests` | **Never** | The test framework exits by itself; `-quit` can kill it before the report is written |

Two common async cases: the UPM client (`Client.AddAndRemove`) and
`AssetDatabase.ImportPackage`, which finishes in an `importPackageCompleted` callback. Run both
without `-quit` and have them call `EditorApplication.Exit` themselves. The worked installer,
including the busy-wait deadlock that is the other way to break this, is
`unity-new-project` → `reference/package-bootstrap.md`.

**Verify the artifact, never the exit code**: `grep` the manifest, stat the generated asset. A
`-quit`ed async run and a successful one both exit `0`.

## 6. One Editor per project — and the `pgrep` pattern that catches it

A headless run against a project an Editor already has open dies with:

```
Aborting batchmode due to fatal error: 似乎有另一個正在執行的 Unity 實例開啟了此專案
```

**That message is localized to the Editor's language**, so grep `Aborting batchmode`, not the
sentence. A wrapper sees something like `exit=1, log=31 lines` and no results file.

Two plausible patterns are wrong on macOS:

| Pattern | Verdict |
|---|---|
| `pgrep -f "Contents/MacOS/Unity$"` | **Too strict.** Misses a Hub-launched Editor, whose command line continues `-projectpath …` so it does not end at `Unity`. The guard says "no editor", the run then does nothing |
| `pgrep -fl "MacOS/Unity"` or `pgrep -f "Hub/Editor/<version>"` | **Too loose.** Also matches `Unity Hub.app/Contents/MacOS/Unity Hub`, three `Unity Hub Helper` processes (gpu-process, utility, renderer), `UnityLicensingClient_V1.app/…/Unity.Licensing.Client`, the Editor's own `Helpers/UnityLicensingClient.app/…`, and the Roslyn compiler server — which live for days and cause a false refusal |
| `pgrep -f "Contents/MacOS/Unity( -\|$)"` | **Correct.** Matches a bare Editor and a Hub-launched one, and nothing else |

*(Written unescaped in a script: `pgrep -f "Contents/MacOS/Unity( -|$)"`.)*

Disambiguating a suspicious match by hand costs a round of
`ps -o pid=,ppid=,etime=,args= -p <pids>` — worth doing once, not every session. If the `unity`
CLI is installed, `unity editors running --format json` answers the same question with the
project path and PID attached; before swapping it in for the `pgrep` guard, check once that the
two agree on your machine.

**Refuse, do not fight the lock.** A driver that exits with a message ("an Editor has this
project open") is better than one that runs anyway: with the project open in the Hub, the
too-strict pattern above reports no Editor, and a change goes out with its EditMode suite
silently unrun. If nothing matches the correct pattern but
`Temp/UnityLockfile` exists, the lockfile is a corpse — `unity-debug` →
`reference/harness-trust.md`.

## 7. The wrapper is written in bash 3.2

macOS ships **bash 3.2.57**, and `#!/usr/bin/env bash` still finds it first. Two traps that both
stop Unity from ever being invoked:

| Written | What happens |
|---|---|
| `"${1,,}"` (lowercase expansion, bash 4) | `bad substitution` at expansion time — and `bash -n` reports the script as *fine*, because it is not a syntax error |
| `"${arr[@]}"` on an **empty** array under `set -u` | bash 3.2 treats it as an unbound variable and aborts |

Replacements: `lower="$(printf %s "$1" | tr '[:upper:]' '[:lower:]')"` and
`${arr[@]+"${arr[@]}"}`.

## 8. The whole thing, composed

```bash
#!/bin/bash
# Drive the Editor binary for one test platform. bash 3.2 compatible.
set -u
UNITY="/Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/MacOS/Unity"
mode="$(printf %s "${1:-edit}" | tr '[:upper:]' '[:lower:]')"   # NOT ${1,,}
case "$mode" in
  edit) platform=EditMode; window=(-batchmode) ;;               # logic only
  play) platform=PlayMode; window=() ;;                         # windowed: screenshots need frames
  *)    echo "usage: $0 edit|play" >&2; exit 2 ;;
esac

out="/tmp/unity-$mode"; mkdir -p "$out"
xml="$out/results.xml"; log="$out/run.log"
rm -f "$xml"                                    # a leftover XML reads as a pass

unity license status --format json | grep -q '"active":[[:space:]]*true' \
  || { echo "no active licence — run: unity auth login" >&2; exit 4; }

if pgrep -f "Contents/MacOS/Unity( -|$)" >/dev/null; then
  echo "an Editor has a project open — close it first" >&2; exit 6
fi

"$UNITY" ${window[@]+"${window[@]}"} -projectPath "$PWD" \
  -runTests -testPlatform "$platform" -testResults "$xml" -logFile "$log"
code=$?                                         # -runTests never gets -quit
echo "exit=$code log=$(wc -l < "$log") lines"

if [ ! -f "$xml" ]; then
  echo "no results file — the run did not happen:" >&2
  grep -E "error CS|Aborting batchmode|No valid Unity Editor license" "$log" \
    | sort -u | head >&2
  exit 1
fi
summary="$(grep -o 'total="[0-9]*" passed="[0-9]*"[^>]*failed="[0-9]*"' "$xml" | head -1)"
echo "$summary"
case "$summary" in *'failed="0"'*) echo green ;; *) exit 8 ;; esac
```

Exit codes it *reports* are the `unity` CLI's own (`4` precondition, `6` retryable, `8` tests
failed), so a caller only has to learn one set. That mapping is a choice this driver makes, not
something Unity does for you.

## Porting the codes and the guard

- **Re-derive each Editor exit code on a new Unity version, platform or CI image** with one
  deliberately broken run per code — Unity publishes no contract for them.
- **Check the Linux and Windows process names before porting the one-Editor guard**; the `pgrep`
  patterns above match macOS process names only.
