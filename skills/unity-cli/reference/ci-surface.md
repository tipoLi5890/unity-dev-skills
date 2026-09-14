# The CI surface — reports, coverage, builds, fan-out, jobs

> Part of the `unity-cli` skill. Global flags, env vars and the CLI's own exit codes are in
> `SKILL.md` and apply to everything here.

**Learn a command's grammar cheaply:** probe it with a path that is not a Unity project, or a stub
project pinned to an uninstalled Editor version — the argument checks and exit codes come back and
nothing launches. Repeat per CLI upgrade.

---

## 1. The three exit codes a CI step actually branches on

`SKILL.md` carries the full set. Three of them decide what the step does next, and telling `2`
from `6` from `8` is the most useful thing on this page:

| Exit | What it means for the step | Example |
|---|---|---|
| `2` | **You invoked the command wrongly.** Fix the script, do not retry | `--junit-output` without `--report-format nunit,junit`; `--report-format bogus`; `--retries 99`; `--profile` together with `--target`; a built-in build with no `--output-path` |
| `6` | **The command ran and failed**, or a precondition on disk was not met. Retryable only once you have read the code | project path with no `ProjectVersion.txt`; the project's Editor version not installed; a forwarded flag the command reserves; the Editor exiting non-zero |
| `8` | **`unity test` only — the suite ran and some tests failed.** A verdict. Never retried, never folded into the `6` column | a red suite |

A red suite is neither `2` nor `6`. If your step's retry rule matches "non-zero and not 2", it
will re-run failing tests until they flake green, which is the laundering §4 and
`unity-debug` → `reference/harness-trust.md` exist to forbid. Match `8` explicitly and stop.

Argument checks run **before** the project and Editor are resolved, so a typo reports itself as a
typo instead of surfacing three layers down as a missing-Editor error. For example,
`unity test /not/a/project --report-format nunit --junit-output ./j.xml` exits `2` naming the
flag conflict, while the same path with valid flags exits `6` naming the missing
`ProjectVersion.txt`.

> **A path that does not exist is a `6`, not a `2`.** The retry column in `SKILL.md` calls `6`
> retryable, and for infrastructure it is — but a wrong `--project-path` also lands here and no
> number of retries will grow one. Read `errors[0].code` before deciding to retry.

**Branch on `errors[].code`, never on `errors[].message`.** The message is translated into whatever
`unity language` is set to; e.g. with the display language at `zh_tw`, the JSON envelope comes
back with `"code": "COMMAND_FAILED"` and a Traditional Chinese `message`. `UNITY_LANGUAGE=en`
does not override it — the persisted setting wins. A CI job that greps English
error text will pass or fail depending on a developer preference stored on the runner.

`--format github` is accepted everywhere, and it only changes the output on a failure.
`unity status --format github` against a live project prints the ordinary human block and exits
`0` — no workflow commands at all; a failing `unity test` prints `::error::<message>` followed by
the log-file hint. Treat it as an annotation layer for failures, not as a machine format: the
annotation carries the **localized** message, so pin the runner's language if anything but a human
reads it.

## 2. Test reports — NUnit, JUnit, and the three ways to get it wrong

The Editor's test runner writes NUnit3 and nothing else; JUnit is a conversion applied to that
report afterwards. `--report-format` therefore decides what `--output` ends up holding:

| `--report-format` | `--output` holds | JUnit lands at |
|---|---|---|
| `nunit` (default) | NUnit3 | — |
| `junit` | JUnit | nowhere else — `--output` **is** the JUnit file |
| `nunit,junit` | NUnit3 | wherever `--junit-output` points |

`--output` defaults to `test-results.xml` relative to the working directory. `--junit-output` has
**no** default clause in `--help`, so name it whenever you ask for both formats. Some
documentation describes it falling back to `--output` with the extension swapped; `--help` does
not, so do not let a CI step collect the JUnit report from a guessed path.

`--report-format` accepts only the values `nunit` and `junit`, comma-joined. Anything else is
rejected by name, exit `2`. The full text:

```
error: option '--report-format <formats>' argument 'bogus' is invalid. Invalid report format. Allowed values: nunit, junit.
```

That one stays English whatever the display language: option-parse refusals come
from the argument parser and never reach the localization layer §1 warns about. The exit-`6`
messages do, which is why the parse errors are the only strings on this page worth grepping — and
even then, prefer the code.

Three refusals, each exit `2`:

- `--junit-output` with `--report-format junit` or with the default `nunit` — the refusal says the
  flag applies only when both reports are produced, and names `--report-format nunit,junit` as the
  fix. With `junit` alone the JUnit report already *is* `--output`, so accepting the flag would
  have to silently ignore one of the two paths you named.
- `--junit-output` resolving to the same file as `--output` — writing both reports to one path
  overwrites the NUnit report with the JUnit one while still reporting two artifacts.
- `--coverage-output` or `--coverage-options` without `--coverage`.

> **The JUnit report is documented to be written even when tests fail** — and that is the only
> moment the report matters. If your CI annotates from JUnit, confirm the file exists on one red
> run on your CLI version before a pipeline depends on it.

**`--testFilter` is still not the flag.** `unity test --testFilter Foo` exits `2` with
`unknown option '--testFilter'`. The flag is `--filter`.

## 3. Coverage

```bash
unity test . --coverage --coverage-output ./coverage
unity test . --coverage --coverage-options "generateHtmlReport"
```

`--coverage-output` defaults to `CodeCoverage` relative to the working directory.
`--coverage-options` is a semicolon-separated string handed straight to Unity's Code Coverage
package, which the project must depend on — `--help` states the dependency as a requirement.

**Without the package, coverage is documented to degrade rather than fail.** The dependency is
looked for in `Packages/manifest.json` and then `Packages/packages-lock.json`; if it is in neither,
a warning names the missing package, the coverage flags are dropped, and the suite runs and
reports normally. Under `--format json` that case shows up as `coverage.requested` true with
`enabled` false. Confirm that on your CLI version before gating a pipeline on it, and assert the
coverage directory is non-empty in the step after the tests either way. A green suite with no
coverage output is the failure mode this behaviour makes quiet.

## 4. Sharding, retries and reruns

`unity test` carries four flags for splitting a suite and re-running failures:

| Flag | Reading |
|---|---|
| `--shard <n/m>` | Run slice `n` of `m`, so parallel jobs can split one suite |
| `--shard-inventory <path>` | The results report whose test list the shards are computed from; defaults to the unsharded `--output` path |
| `--retries <n>` | Re-run failing tests up to `n` extra times and report anything that passes on a retry as **flaky**. Range enforced at `0`–`10` (`--retries 99` exits `2`) |
| `--rerun-failed` | Run only the tests that failed in the previous run's report |

`--shard` needs a full-suite report to slice against, so the first sharded pipeline still has to
produce one — that is what `--shard-inventory` points at.

> `--retries` reports a flake; it does not launder one. The verdict a suite is allowed to give is
> still the first one, and a suite retried until it passes is indistinguishable from a suite with
> no assertions — `unity-debug` → `reference/harness-trust.md`. Use the flake label as a bug
> report, not as a pass.

## 5. `unity build` — pick exactly one strategy

| Strategy | Flags | Refusal if you get it wrong |
|---|---|---|
| Unity 6 build profile | `--profile "<name or .asset path>"` — the profile decides the target | `--profile` with `--target` exits `2`, the refusal naming `--target` as the flag to remove because the profile already fixes the target |
| Built-in player build | `--target <desktop target>` + `--output-path` | `--target Android` alone exits `2`: only `StandaloneLinux64`, `StandaloneOSX`, `StandaloneWindows64` have a built-in command-line build. `--target StandaloneOSX` without `--output-path` exits `2` |
| Your own method | `--execute-method Builder.PerformBuild` (+ `--output-path`, forwarded as `-buildOutput`) | none — but **your method has to honour `-buildOutput` itself**; the CLI only passes it |

Other flags worth knowing before the first pipeline:

- `-l, --log-file` defaults to `<project>/Logs/build-<target>-<timestamp>.log`, and the log
  **streams to stdout as well** unless you pass `--no-tail`; `--quiet` and `--format ndjson` also
  stop the stream.
- `--versioning-strategy semantic|tag|custom|none` (default `none`); `--build-version` is read
  only under `custom`.
- `--allow-dirty-build` exists, which is to say the default refuses to build an uncommitted tree.
  Leave it off — a build nobody can check out again is the build someone will later be asked to
  reproduce.
- `--provenance-path` / `--no-provenance`: a manifest is written beside the output (or beside the
  log file when there is no `--output-path`) unless you opt out. Keep it; it is the cheapest
  answer to "which commit is this APK".
- `--timeout <seconds>` (env `UNITY_BUILD_TIMEOUT`) is off by default. A CI build with no timeout
  is a runner held until the platform's own limit fires, with no log line saying why.

### Android signing, and the rule that governs it

`--android-export-type apk|aab|android-studio-project`, `--android-keystore-base64`,
`--android-keystore-password`, `--android-key-alias`, `--android-key-alias-password`,
`--android-target-sdk-version`, `--android-symbol-type none|public|debugging`,
`--android-version-code`.

The keystore flags are validated as a set: `--android-keystore-base64` alone exits `2` naming
`--android-keystore-password` and `--android-key-alias` as missing.

> **Everything you pass in argv is readable by every process on the machine.** Expanding a secret
> from an environment variable removes the literal from the script, not the value from `ps` — and
> CI still has to mask it in the log. Prefer a committed build script that reads the keystore from
> a gitignored env file at build time: `unity-android-release`.

Interrupting a build exits with the signal convention — `130` for SIGINT, `143` for SIGTERM —
rather than a generic `1`, so an aborted build is distinguishable from a failed one. That is
documented; confirm it on your CLI version before gating a pipeline on it.

## 6. `unity projects exec` — fan-out across the Hub registry

```bash
unity projects exec --filter <expr> -p <n> --continue-on-error --dry-run -- <command...>
```

`--filter` is repeatable and the terms are AND-ed, so each one narrows the set further. Three term
shapes:

| Term | Matches |
|---|---|
| `name:<glob>` | the project name or its path — a bare glob with no prefix means this |
| `version:<glob>` | the Editor version the project requires |
| `pinned[:<bool>]` | pinned state; bare `pinned` means pinned |

Globs are path-aware: `name:My*` selects by project name, `name:**/work/*` selects by where the
project lives on disk. `-p, --parallel` defaults to **1**, so a fan-out is serial until you say
otherwise. `--continue-on-error` keeps going past a failing project instead of stopping the run.

> **The `-- <command>` tail is not run through a shell.** The tokens after `--` are handed to the
> process directly, so `&&`, `|`, `>` and variable expansion are text, not operators.
> `-- npm test && npm run lint` therefore does not chain — the `&&` is either
> swallowed by your own shell before the CLI sees it or passed to `npm` as an argument. Put the
> chain in a script and fan out over the script. Each project's command does get
> `UNITY_PROJECT_PATH` and `UNITY_EDITOR_VERSION` in its environment, and runs in that project's
> directory.

> **A fan-out that matched nothing exits `0`.** `--filter` with no match prints *"No
> registered projects matched the filters. Nothing was run."* and exits `0`. A CI step that runs a
> migration across every project and silently matches none is a green step that did nothing.
> Always `--dry-run` first, and assert the project count from the JSON envelope
> (`data.projects[]`) rather than trusting the exit code.

`--dry-run --format json` returns `data.dryRun`, `data.command` (the tokenized command) and
`data.projects[]` with `name`, `path` and `version` per project.

## 7. Driving a live Editor headlessly, and what the envelope looks like

`unity run <project> --command <name> -- <args>` starts the Editor in batch mode, waits for the
project's Pipeline server, parses the args after `--` against the command's own schema, prints the
return value and shuts down; an Editor already holding the project is reused. It needs
`com.unity.pipeline` in the project.

The same command against an Editor that is **already** running is `unity command <name>`, and its
envelope looks like this:

```json
{ "success": true, "command": "command eval",
  "data": { "command": "eval",
            "parameters": { "code": "return UnityEngine.Application.unityVersion;" },
            "result": { "output": null, "diagnostics": [], "success": true, "result": "<version>" },
            "target": { "host": "127.0.0.1", "port": 7800, "projectPath": "…" },
            "success": true },
  "errors": [], "warnings": [] }
```

Three nested `success` fields, and the outer one is the one to branch on: a compile failure inside
`eval` and an unknown command name both come back as outer `success: false`, `data: null`,
`errors[0].code = "COMMAND_FAILED"`, **exit 6**. `data.result.result` is the return
value; `data.result.diagnostics` carries compile diagnostics when the command is `eval`.

`unity run --command` is documented to return the same envelope with `data.result` as the return
value and `data.reusedRunningEditor` saying whether an open Editor was reused; confirm it on your
CLI version before gating a pipeline on it.

**A failure is still a complete document on stdout**, so there is no reason to scrape stderr — and
`data` can be present and well-formed while `success` is false:

```json
{ "success": false, "command": "status",
  "data": { "count": 0, "instances": [] },
  "errors": [ { "code": "STATUS_NO_INSTANCES", "message": "…" } ], "warnings": [] }
```

> **Branch on `success`, never on the presence of `data`.** `errors[0].code` is the stable
> identifier; the message is not.

`unity status` is the cheap availability gate before any of it:

```json
{ "success": true, "command": "status",
  "data": { "count": 1, "instances": [ { "port": 7800, "project": "…", "version": "<version>",
                                         "pid": 23434, "state": "ready" } ] },
  "errors": [], "warnings": [] }
```

A **headless** Editor does appear here — `state: "ready"`, with its port and PID — so
`unity status --format json` is a valid gate in a pipeline, not only on a developer's desktop;
confirm it on your CLI version before a pipeline depends on it.
`unity list` is the discovery-only sibling: it prints the connected Editor's registered tools and
never runs one.

### Detached jobs

`unity command <name> --detach` submits the work and prints a job id instead of blocking. Then:

| Command | Flags beyond `--project-path` |
|---|---|
| `unity job status <job-id>` | — |
| `unity job wait <job-id>` | `--poll-interval <ms>` (default 500), `--timeout <seconds>` (`0` = wait forever, the default) |
| `unity job cancel <job-id>` | — |

This is the right shape for a long bake or import inside a step that also has to report progress:
submit, then `unity job wait` with a real `--timeout` so the runner is never held open by a job
that died. The job commands are documented; confirm them on your CLI version before gating a
pipeline on them.

## 8. Reserved flags — the ones the command manages itself

`unity test . -- -runTests` exits `6`; the message names the forwarded argument and says it
conflicts with a reserved Unity flag the command manages. The message text
itself is localized — see §1 — so gate on the exit code. `-batchmode`, `-projectPath` and
`-useHub` are refused identically, and the match is spelling-insensitive: `-projectPath`,
`--projectPath` and `-projectPath=/x` each produce the same `6` — even against a stub project
pinned to an Editor version that is **not** installed.

That last detail shows the check runs early: the same stub with `-nographics`,
`-logFile` or `-executeMethod` after `--` gets past the reserved-flag check and fails on the
uninstalled Editor instead — those three are not reserved and do pass through. The
coverage trio (`-enableCodeCoverage`, `-coverageResultsPath`, `-coverageOptions`) is managed by
`--coverage`; pass the CLI flags, not the Editor ones.

> **`unity test` deliberately never passes `-quit`.** `-runTests` exits on its own once the report
> is written, and `-quit` can kill the Editor before that happens. The same trap, from the other
> side, is in `SKILL.md` → §The other CLI.

## 9. Pipeline package installs

```bash
unity pipeline list                                  # every reachable Editor and its package status
unity pipeline list-versions                         # every version on the registry, newest first
unity pipeline install --project-path <path>
unity pipeline install --package-version <version>   # pin
unity pipeline install --force                       # re-resolve to latest even if installed
unity pipeline upgrade                               # only when the registry actually has a newer one
```

> **The pin flag is `--package-version`, not `--version`.** `-V, --version` is the global flag that
> prints the CLI's own version, so `--version` on this subcommand would be answering a different
> question. Same trap as `--filter` vs `--testFilter`: the flag that "should" exist is the one that
> silently means something else.

## 10. The preflight, the workflow file, and the cache key

The three commands that run *before* everything on this page — `unity ci init`, `unity doctor --ci`
and `unity cache key` — plus the pipeline skeleton and the `unity projects verify` check codes have
moved to `reference/ci-preflight.md`.
