# A build you can repeat

Clicking through Build Settings is not a procedure. It cannot be reviewed, it cannot be run by CI,
and it silently picks up whatever the last person left in the dialog. Two committed pieces replace
it: an Editor entry point that pins what the artifact IS, and a shell driver that decides what
happens around it.

## Build Profiles, and why this template does not use them

Unity 6 documents a newer idiom: a **Build Profile** asset plus `-activeBuildProfile` and
`BuildPipeline.BuildPlayer(BuildPlayerWithProfileOptions)`, which takes scenes and settings from the
profile instead of from code.

Both are current. Choose on where you want the settings to live:

| | Profile asset | Pinned in the build method (this template) |
|---|---|---|
| Where settings live | a `.asset`, edited in the inspector | C#, in the diff |
| Reviewable | YAML diff | reads as code |
| Drift between "tested" and "built" | possible if the profile is edited | impossible; the method sets them every time |

For a small team shipping one target, pinning in code is the stronger guarantee — the point of
the script is that a CLI build **cannot** quietly differ from the one that was tested. Switch to
profiles when you have several targets or several people editing configuration.

## The split that matters

| Committed `Editor/BuildScript.cs` | The shell driver |
|---|---|
| scenes, scripting backend, architecture, stripping | which mode, which format, whether to test first |
| things that must not drift between builds | things that differ per artifact |
| pinned in code, reviewed in diffs | flags and a gitignored env file |

Pinning the backend and architecture **in the build method** rather than trusting the project file
is deliberate: it makes a CLI build unable to quietly differ from the one that was tested.

```csharp
EditorUserBuildSettings.buildAppBundle = aab;
PlayerSettings.SetScriptingBackend(NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
PlayerSettings.stripEngineCode = true;
```

`NamedBuildTarget` needs `using UnityEditor.Build;` — a separate namespace from
`UnityEditor.Build.Reporting`.

## Read arguments from the command line, secrets from the environment

```csharp
static string Arg(string name)
{
    string[] args = Environment.GetCommandLineArgs();
    for (int i = 0; i < args.Length - 1; i++)
        if (args[i] == name) return args[i + 1];
    return null;
}
```

```bash
Unity -quit -batchmode -nographics -projectPath . \
      -buildTarget Android -executeMethod BuildScript.BuildAndroid \
      -logFile build.log -output Builds/game.apk -versionCode 3
```

Two mechanical details that cost a round trip each: `-executeMethod` takes the **fully qualified**
name, so a class inside a namespace is `-executeMethod Company.Build.BuildScript.BuildAndroid` and a
class with none is just `BuildScript.BuildAndroid`; and the file must be Editor-only — inside an
`Editor/` folder, or an asmdef with `includePlatforms: ["Editor"]`, or wrapped in `#if UNITY_EDITOR`
as the template is — otherwise it fails to compile for the player and takes the build with it.

## The empty-scene silent failure

`BuildPipeline.BuildPlayer` handed an empty scene list fails with `Result: Unknown` and **no error
line in the log**, which in a headless run is indistinguishable from a crash. Check it yourself and
fail loudly:

```csharp
if (scenes.Length == 0) { Fail("no enabled scenes in Build Settings — nothing to build"); return; }
```

**A non-zero check is not enough when the scene list is generated.** When a scaffold rebuilds
`EditorBuildSettings.scenes` from per-feature status, forgetting to re-run it after enabling a
feature produces an APK that shows "coming soon" forever: the runtime guards its loads with
`Application.CanStreamedLevelBeLoaded(name)` and fails politely, the log is clean, and the gate
passes because *some* scenes are enabled. A generated list needs an assertion about its
**contents** — the expected count, or the expected names — not about its length being positive.

## Never trust Unity's exit code

This is not folklore. Unity's own manual page for a custom build script documents the flags and
tells you to check `report.summary.result` and throw `BuildFailedException` — and **says nothing
about exit codes or verifying the result**. There is no contract to rely on, which is why the
community convention in CI is to grep the log for a success string or to check the file exists.

It also exits **0 when it never started**. The artifact either exists or it does not — that is the only
signal worth branching on:

```bash
rm -f "$OUTPUT"                       # so a stale artifact cannot be mistaken for a fresh one
... run unity ...
if [[ ! -f "$OUTPUT" ]]; then
  tail -25 "$BUILD_LOG"
  die "no artifact produced (unity exit $UNITY_EXIT, log $(wc -l < "$BUILD_LOG") lines)"
fi
```

Same discipline as `unity-debug` → `reference/harness-trust.md`: delete the expected output first,
then check for its existence, then check the log length.

## Refuse rather than warn

A warning in a build log is read once, by nobody. Make the script stop where stopping is right:

- **release still on the template package name** — store identity, locked once published;
- **release with no keystore** — the artifact would be debug-signed and unpublishable;
- **a `versionCode` already in the build history** — Play rejects a re-used one;
- **a native `.aar` with no `arm64-v8a`** — builds fine, crashes on launch;
- **a prebuilt `.so` aligned to 4 KB while `targetSdk` is 35+ or left on Auto** — builds fine, and
  crashes on launch only on 16 KB-page devices (`player-settings-android.md`).

## Ready-made

`templates/BuildScript.cs`, `templates/build-android.sh` and `templates/build-env.example` in this
skill are the working versions of everything above, project-agnostic. Where each file goes and the
four modes (`doctor` and `preflight` build nothing; `release` is a signed AAB that runs the test
suite first) are in `SKILL.md` and the script's own header. Run `doctor` first.

`doctor` exists because of `device-triage.md`: it follows the reference chain from
GraphicsSettings to the render pipeline asset that is genuinely loaded, reports whether the quality
tiers override it, decodes the pinned graphics APIs, and checks every native `.aar` — its ABI and
its page alignment — including those inside `file:` UPM dependencies, which live outside the
project. Without it, "which asset is in force?" costs round trips of "build, install, still
broken"; with it, the answer is one command.

`preflight` is the same checks with the release gates applied and a real exit code, so it works as
a CI gate.

## Wait on a marker file, never on a word in the console

Anything that automates a build — an agent, a CI step, a second terminal — needs to know when it
finished. Grepping the build's console output for a completion word is the obvious approach and it
is a trap: Unity's output carries ANSI colour escapes, so the line does not actually *end* with the
word you can see, an anchored pattern never matches, and the waiter spins until someone notices.

Write one marker instead, from an `EXIT` trap so it appears whatever happened:

```bash
RESULT_FILE="$OUT_DIR/build-${STAMP}.result"
finish() {
  local rc=$?
  printf '%s\t%s\t%s\n' "$([ $rc -eq 0 ] && echo ok || echo fail)" "$rc" "${OUTPUT:-}" > "$RESULT_FILE"
}
trap finish EXIT
```

```bash
until [ -f "$RESULT" ]; do sleep 10; done; cat "$RESULT"     # the waiter
```

A file either exists or it does not. Modes that build nothing (`doctor`) deliberately write no
marker, so a waiter cannot mistake a read-only run for a finished build.

## Four shell traps that cost real time

Each of these looks correct and is wrong, and only RUNNING the script finds them.

**1 · `cmd | grep -q` under `set -o pipefail` reports failure ON A MATCH.** `grep -q` exits the
instant it finds one, the upstream command dies of SIGPIPE, and `pipefail` surfaces that as the
pipeline's status. A healthy plugin reads as a hard failure. Capture, then match:

```bash
AAR_LIST="$(unzip -l "$aar" 2>/dev/null || true)"
if grep -q "jni/arm64-v8a/" <<<"$AAR_LIST"; then ...
```

**2 · macOS ships bash 3.2**, where `"${arr[@]}"` on an **empty** array is an unbound-variable error
under `set -u`. Bash 4.4 fixed it; a `#!/usr/bin/env bash` shebang does not guarantee it.

```bash
"$UNITY" ... ${AAB_FLAG[@]+"${AAB_FLAG[@]}"} ${SIGN_ARGS[@]+"${SIGN_ARGS[@]}"}
```

The same shell has no `${var,,}` — a lowercasing helper copied from anywhere newer fails outright
with `bad substitution`, which is at least loud. Use `tr 'A-Z' 'a-z'`.

**3 · `grep -c` exits 1 when the count is ZERO**, so the habitual `X="$(grep -c ... || echo 0)"`
produces the two-line string `"0\n0"`, which then fails every comparison against `"0"` — including
the `[[ "$X" == "0" ]]` guarding the thing you wanted to report. Assign on failure instead of
appending to the output:

```bash
SCENES="$(grep -c 'enabled: 1' ProjectSettings/EditorBuildSettings.asset)" || SCENES=0
```

**4 · `pgrep -f "<pattern>"` matches the waiting loop itself** when the loop's own command line
contains the pattern — an `until pgrep -f build.sh; do sleep; done` never exits. Wait on a marker
in the log instead, or match a pattern the waiter cannot contain.

Related: `pgrep -f "Hub/Editor/<version>"` also matches Unity's Roslyn compiler server and its
licensing client, both of which live for days. To ask "is the editor open", match the editor binary:
`pgrep -fl "Contents/MacOS/Unity$"`.

## The search that silently finds nothing

Scanning `Assets Packages Library/PackageCache` for native plugins finds **zero** `.aar` files on a
project whose only native plugin is a `file:` UPM dependency — the package lives outside the
project entirely, so the check passes by finding nothing. The check you most want is the one most
likely to no-op quietly.

```bash
ROOTS=(Assets Packages Library/PackageCache)
while IFS= read -r p; do [[ -d "$p" ]] && ROOTS+=("$p"); done \
  < <(sed -n 's/.*"file:\([^"]*\)".*/\1/p' Packages/manifest.json)

FOUND=0
# ... scan "${ROOTS[@]}" ...
[[ "$FOUND" == "0" ]] && ok "no native .aar plugins to check"   # say so, do not stay silent
```

Always report the zero case explicitly. A silent pass and a real pass look identical otherwise.

While each `.aar` is open, check the page alignment of its `.so` files as well as their ABI — it is
the same unzip, and it decides the highest `targetSdk` the project may set
(`player-settings-android.md`).

## Exit codes should say whether retrying is honest

`Never trust Unity's exit code` above is about a raw `Unity -batchmode`, which returns 0 when it
never started. A driver script has no such excuse: it knows what happened, so it should say so in
a code the caller can branch on. The distinction that matters is **"the thing under test is
broken" versus "the machinery failed"** — only the second is worth a retry.

| Code | Means | Retry? |
|---|---|---|
| `0` | Built, verified, artifact read back | — |
| `2` | Bad arguments / bad configuration | No |
| `3` | Refused a gate (template package name, no keystore, reused versionCode, missing ABI) | No — that is the gate working |
| `6` | Infrastructure: Unity would not start, network, disk | **Yes** |
| `8` | The test suite ran and failed | **No — that is a real verdict** |

```bash
Tools/build-android.sh release
case $? in
  0) ;;
  8) echo "tests failed — a verdict, not a flake" ; exit 1 ;;
  3) echo "refused by a gate — read the message, do not --force" ; exit 1 ;;
  6) echo "infrastructure — retry once" ;;
  *) exit 1 ;;
esac
```

Retrying an `8` reruns a genuine failure until it flakes green. Retrying a `3` means adding a
flag to defeat a check that exists because it caught something once.

## Write a provenance record for every build, including the failed ones

`build-history.tsv` answers "what versionCode did we ship". It does not answer "what was in it",
which is the question asked six weeks later when a store report names a build nobody can
reproduce. Emit a small JSON next to each artifact:

```json
{ "editorVersion": "<version>", "editorChangeset": "…",
  "target": "Android", "outcome": "success",
  "gitRevision": "160f48d", "gitDirty": false,
  "packages": { "com.unity.render-pipelines.universal": "17.x.y", "…": "…" },
  "versionCode": 42, "artifactSha256": "…" }
```

Three rules make it trustworthy rather than decorative:

- **`gitDirty` is not optional.** A build from a dirty tree is not reproducible, and that is
  exactly the build someone will later try to reproduce.
- **Failed builds get a record too**, with `outcome` set accordingly. A gap in the record is
  indistinguishable from a build nobody wrote down.
- **Redact.** No keystore path, no passwords, no full argv, no hostname, no absolute paths under
  a home directory. This file gets attached to bug reports.
