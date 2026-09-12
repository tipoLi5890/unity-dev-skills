---
name: unity-cli
description: >-
  Operate Unity from a terminal with the `unity` CLI: install editors and
  modules, create projects from templates, check licences, run builds and tests
  in CI, and diagnose the tool itself. Load for "install Unity 6000.x with the
  Android module", "get a JUnit report out of the test runner", "shard the
  suite across CI jobs", "wire Unity into my agent via MCP", or a command that
  exits non-zero when you must decide whether retrying is honest. Also the raw
  `Unity -batchmode` binary: exit 198, "No valid Unity Editor license",
  "another Unity instance has this project open", a batch run that exits 0
  having done nothing. Day-one decisions are unity-new-project; driving a live
  Editor is unity-debug.
---

# unity-cli — the tool, its exit codes, and what it will not tell you

> **This CLI is in beta and its surface moves.** A flag that "should" exist and does not is the
> most common way a script here fails; a flag that did not exist and now does is the second.
> Re-read `unity <command> --help` when the version moves.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| `unity: command not found` right after installing | §Install — open a new shell |
| A command exits non-zero and you must decide whether to retry | §Exit codes |
| A headless `Unity -batchmode …` exits `198`, `1`, `2` or `3` | §The other CLI → `reference/editor-binary.md` |
| A batch command exits `0` and nothing happened | §The other CLI — a lock, a licence, or `-quit` on an async method |
| Every headless command fails at once on a machine that worked yesterday | §Auth and licence |
| A flag from a tutorial is rejected | §The conventions — and re-read `unity --help`; this is beta |
| `unity run` refuses to start | §Running — it reserves some editor flags |
| CI needs a JUnit report, coverage, or a sharded suite | §Running → `reference/ci-surface.md` |
| A CI step exits `2` and you cannot see which flag | §Exit codes — a usage error, checked first |
| A grep on the CLI's error text stopped matching | §The conventions — messages are localized, `errors[].code` is not |
| A long bake or import blocks the CI step | §Driving a connected Editor — `--detach`, then `unity job wait` |
| Tests "passed" but you do not believe it | skill `unity-debug` → `reference/harness-trust.md` |
| You need the Editor to *do* something, not just start | skill `unity-debug` → `reference/editor-control.md` |

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Driving a running Editor to verify a change; screenshots; Safe Mode | `unity-debug` → `reference/editor-control.md` |
| Android signing, keystores, artifact verification | `unity-android-release` |
| WebGL/WebGPU builds | `unity-web-release` |
| Choosing which packages a project needs; headless package installs | `unity-new-project` |

## Install, and the one that catches everyone

```bash
which unity && unity --version          # detect before installing
curl -fsSL https://public-cdn.cloud.unity3d.com/hub/prod/cli/install.sh | UNITY_CLI_CHANNEL=beta bash
```

The install script checks the binary's SHA-256 against the release manifest and aborts if it
cannot — drop the `| bash` and read the script yourself if that check has to be more than a
claim. **Open a new shell afterwards** — the PATH entry is not in the one you installed from.
`unity doctor` checks for exactly this.

## The conventions that apply to every command

| | |
|---|---|
| Output | `--format human\|json\|tsv\|ndjson\|github`; `--json` is shorthand for the second |
| CI | `--non-interactive` together with `--yes` |
| Env | Everything is `UNITY_`-prefixed (`UNITY_PROJECT_PATH`, `UNITY_EDITOR_VERSION`, `UNITY_FORMAT`, `UNITY_RUN_TIMEOUT`, `UNITY_BUILD_TIMEOUT`…). **A flag always beats an env var** |
| Paging | Off for non-TTY, machine formats, `--quiet` and `TERM=dumb`; `--no-pager` (env `UNITY_NO_PAGER`) forces it off |
| Language | `unity language --set <code>` picks from ten display languages, and **it translates the error messages too** |

`unity status --format github` is accepted, and a failing command prints `::error::<message>` —
GitHub Actions annotation syntax (`reference/ci-surface.md` §1).

**The message in that annotation is localized; the code beside it is not.** `UNITY_LANGUAGE=en`
does **not** override the persisted display language, so a CI job that greps English error text
passes or fails on a developer preference stored on the runner. Branch on `errors[].code`.

**A failure is still a complete document on stdout.** There is no reason to scrape stderr:

```json
{ "success": false, "command": "status",
  "data": { "count": 0, "instances": [] },
  "errors": [ { "code": "STATUS_NO_INSTANCES", "message": "…" } ], "warnings": [] }
```

> **Branch on `success`, never on the presence of `data`.** That is real output — `success` is
> false while `data` is present and well-formed. `errors[0].code` is the stable identifier; the
> message is not.

## Exit codes are the interface

**This table is the `unity` CLI's own set.** The Editor binary
(`…/Unity.app/Contents/MacOS/Unity -batchmode …`) uses a different one (§The other CLI), and
reading it against this table turns a run that never started into a green tick.

| Code | Means | Retry? |
|---|---|---|
| `0` | Success | — |
| `2` | Bad arguments | No |
| `3` | Auth failure | No — sign in |
| `4` | Precondition missing (no licence, no editor) | No — provision |
| `6` | Command failed / infrastructure | **Yes** |
| `8` | **`unity test` only** — tests ran and some failed | **No. This is a verdict** |
| `130` / `143` | SIGINT / SIGTERM | — |

`unity doctor --ci` adds `7 = service unreachable, worth retrying`, and `6` takes precedence
over `7`.

**Two overlapping `unity test` runs on one project return `6`** — *"another Unity instance has
this project open"* — retryable once the other finishes. **One Editor per project at a time:** a
second run launched before the first exits does not queue, it fails.

> Retrying an `8` reruns a genuine failure until it flakes green. A suite that is retried until
> it passes is indistinguishable from a suite with no assertions.

**`2` is checked before the project is.** **A project path that does not exist is a `6`, not a
`2`** — retryable on paper, and no retry will grow a `ProjectVersion.txt`. Read `errors[0].code`
before deciding (`reference/ci-surface.md` §1).

## The other CLI: the Editor binary itself

Test drivers, scaffolders and anything needing a flag the CLI reserves invoke
`/Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/MacOS/Unity` directly — and that
program answers with its own undocumented codes: `0` is success — **or** a locked project, or
`-quit` killing an async method before it ran; `1` is a compile error in *any* assembly; `2` is
tests ran and some failed, a verdict; `3` is a windowed PlayMode run that never started; `198` is
no valid Editor licence. Four rules follow:

1. **Take the verdict from the results file, not from `$?`.** Delete it before the run; if it is
   missing afterwards, `grep -E "error CS|Aborting batchmode|No valid Unity Editor license"` the
   log. `1` and `3` both mean *nothing ran*.
2. **Check the licence session first** — §Auth and licence.
3. **Refuse to start while an Editor has the project open**: `pgrep -f "Contents/MacOS/Unity( -|$)"`
   catches Hub-launched Editors and not the Hub's long-lived helpers.
4. **Never pass `-quit` to `-runTests` or to an async `-executeMethod`** — the method exits `0`
   having done nothing. Verify the artifact, not the code.

→ `reference/editor-binary.md` — the code table with results-file and log-length evidence, the
wrong `pgrep` patterns, the bash 3.2 traps, and a driver script. **Read it when** you are writing
or debugging a script that runs the Editor binary.

## Auth and licence, before anything else

A stale login session makes **every** headless command fail at once — `-executeMethod`,
`-runTests`, builds — each with a short log saying `No valid Unity Editor license` and Editor
exit `198`. It looks exactly like a compile failure and is not a project problem.

Run `unity license status --format json` first and **branch on `data.active`, not on the exit
code**; `unity auth status` says `stale` when the session has expired, and `unity auth login` (or
opening Unity Hub once) fixes it. The healthy JSON and a wrapper-ready grep:
`reference/editor-binary.md` §3.

## Editors and modules

`unity install lts --module android --yes --accept-eula` installs; `unity editors --installed
--format json` proves it landed. **One failed module does not abort the batch** — read per-item
status from the NDJSON `result` frame's `items[]`, not from the exit code alone. The full command
set: `reference/everyday-commands.md` §1.

## Projects and templates

List template ids with `unity templates list --format json`; never guess one. `unity projects
create … --vcs github|uvcs` sets up version control in one step: pass `--no-initial-commit`, and
**secrets go in on stdin** (`--git-token-stdin`). Recipes and reasons:
`reference/everyday-commands.md` §2.

## Running, building, testing

```bash
# run — batch mode is implied. Passing -batchmode/-quit/-projectPath/-useHub/-hubIPC
# is refused before launch (exit 6), including the -x / --x / -x=v spellings.
unity run <proj> --editor-version <v> --allow-install --timeout 300 \
      -- -executeMethod Builder.Build -logFile out.log

# three build strategies — pick exactly one (reference/ci-surface.md §5)
unity build <proj> --target StandaloneLinux64 -o ./build \
      --allow-install --versioning-strategy <s>
unity build <proj> --execute-method Builder.PerformBuild -o ./build --allow-install
unity build <proj> --profile "Windows Release" -o ./Build/MyGame.exe

unity test <proj> --mode PlayMode --filter "MyFixture" \
      --report-format nunit,junit --output ./results.xml --junit-output ./junit.xml \
      --allow-install --timeout 900 --coverage
unity test <proj> --shard 2/4 --shard-inventory ./results.xml   # beta.6+
unity test <proj> --rerun-failed --retries 1                    # beta.6+
```

**The test filter flag is `--filter`, not `--testFilter`**, which is rejected with
`error: unknown option` and exit `2` — the reason to read `--help` rather than recall a flag.

> **`--retries` labels a flake, it does not launder one** (`unity-debug` →
> `reference/harness-trust.md`). Sharding and retry flags: `reference/ci-surface.md` §4.

Three behaviours to know before writing the CI step:

- **`unity test` deliberately does not pass `-quit`.** `-runTests` exits on its own, and adding
  `-quit` can kill the Editor before the report is written.
- **`unity build` can sign an Android artifact itself** with its `--android-*` flags, and its
  help text warns why not to: **argv is visible.** Prefer a committed build script reading a
  gitignored env file — `unity-android-release`.
- **`--allow-dirty-build`** exists, so the default refuses a dirty tree. Leave it off: a build
  from an uncommitted tree is the one someone will later try to reproduce.

→ `reference/ci-surface.md` — report and coverage grammar, build strategies, fan-out, envelopes,
jobs, a pipeline skeleton. **Read it when** you are writing the CI step.

## Driving a connected Editor, and detaching the long jobs

An Editor with `com.unity.pipeline` installed publishes its registered commands to the CLI. Three
read-only entry points:

```bash
unity status --format json            # port, project, version, PID, state — the availability gate
unity list                            # what this Editor exposes; discovery only, runs nothing
unity command --detail compact --limit 20   # the same catalogue, and this one can also run them
unity command eval 'return UnityEngine.Application.unityVersion;' --format json
```

**A headless Editor does show up in `unity status`** — `state: "ready"`, with its port and PID —
so gating a pipeline on it is legitimate. Confirm it on your own CLI version: a gate that quietly
stops seeing the Editor is expensive to diagnose.

Long work does not have to block the step: `unity command <name> --detach` prints a job id and
returns, and `unity job wait <job-id>` joins it. **`unity job wait --timeout 0` waits forever, and
that is the default** — give it a real number or a dead job holds the runner open.
`unity pipeline install --package-version <v>` pins the package; `--version` prints the CLI's own
version. Envelopes and job commands: `reference/ci-surface.md` §7; pinning the Pipeline
package: §9.

## Two commands that are not about your project

**`unity collaboration`** (alias `collab`) works on a Unity Cloud organisation's annotations and
touches no project on disk. **`unity skill install <client>`** writes the CLI's bundled agent
skill into a client's skills directory — a directory named `unity-cli`, the same name as this
skill. Two skills with one name is a silent shadowing bug, not an error:
know which one is loaded before anything writes there. Flags and clients:
`reference/mcp-and-shell.md`.

## Diagnosing the tool

`unity doctor --ci` is the first step of any pipeline. **`unity projects verify . --strict` is the
cheapest gate there is.** It checks `META_MISSING`, `META_ORPHAN`, `GUID_DUPLICATE`,
`CONFLICT_MARKERS`, `MANIFEST_INVALID` and `EDITOR_VERSION_DRIFT` from disk without starting Unity,
so a merge conflict marker inside a `.unity` file costs a second rather than twenty minutes of
build. The rest of the diagnosis set: `reference/everyday-commands.md` §3.

> **`unity logs` reads the Hub log.** Not `Editor.log`, not your game's output. Reaching for it
> to debug a build returns something plausible and irrelevant. Editor logs and how to read them
> are in `unity-debug` → `reference/cli-harness.md`.

## MCP and the warm shell

→ `reference/mcp-and-shell.md` — wiring a running Editor into an agent as MCP tools, and the
REPL that avoids paying process startup per command. **Read it when** you are about to issue
more than a handful of commands in a row, or when an agent needs to touch the Editor directly.

## Never hand-edit a scene, prefab or asset YAML

Three reasons, all of which produce a diff that looks right: `fileID` and GUID references fail
at load, not at edit; a running Editor has the file in memory and overwrites your change on save;
and it is easy to edit a file the project never loads (`unity-debug` →
`reference/harness-trust.md`). Drive a live Editor instead: `unity-debug` →
`reference/editor-control.md`.

## Reference

- [`reference/ci-surface.md`](reference/ci-surface.md) — reports, coverage, build strategies,
  fan-out, envelopes, jobs, a pipeline skeleton.
- [`reference/editor-binary.md`](reference/editor-binary.md) — raw `Unity -batchmode` exit codes,
  wrapper guards, a driver script.
- [`reference/everyday-commands.md`](reference/everyday-commands.md) — editors, templates,
  project creation, diagnosis.
- [`reference/mcp-and-shell.md`](reference/mcp-and-shell.md) — the MCP server and its clients,
  `unity skill install`, `unity collaboration`, the warm REPL.
