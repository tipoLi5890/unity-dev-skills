---
name: unity-cli
description: >-
  The unity CLI and -batchmode: install editors, licences, builds, tests,
  scene diffs, exit codes.
---

# unity-cli — the tool, its exit codes, and what it will not tell you

> **This CLI is in beta and its surface moves.** A flag that "should" exist and does not is the
> most common way a script here fails; a flag that did not exist and now does is the second.
> Re-read `unity <command> --help` when the version moves.

Documented against CLI `1.0.0-beta.9` (September 2026). **When `unity --version` is newer than
that, `--help` outranks this file.**

## Symptom → where to look

| Symptom | Go to |
|---|---|
| `unity: command not found` right after installing | §Install — open a new shell |
| A non-zero exit you must decide whether to retry; a CI step exits `2` and you cannot see which flag | §Exit codes |
| A headless `Unity -batchmode …` exits `198` ("No valid Unity Editor license"), `1`, `2` or `3` | §The other CLI → `reference/editor-binary.md` |
| A batch run that exits `0` having done nothing, or with no results file | skill `unity-debug` |
| "install Unity 6000.x with the Android module", create a project | §Editors, modules, templates, projects |
| "wire Unity into an agent via MCP" | `reference/mcp-and-shell.md` |
| Every headless command fails at once on a machine that worked yesterday | §Auth and licence |
| A flag from a tutorial is rejected; a grep on the CLI's error text stopped matching | §The conventions |
| `unity run` refuses to start | §Running — it reserves some editor flags |
| CI needs a JUnit report, coverage, or a sharded suite | §Running → `reference/ci-surface.md` |
| CI needs the workflow file itself, a `doctor --ci` verdict, or the runner's cache key | `reference/ci-preflight.md` |
| A `git diff` of a `.unity` file is unreadable `fileID` lines; `git blame` names only a line; "who changed this prefab" | §Version control → `reference/version-control.md` §3–§4 |
| A vcs verb answers `outcome: binary-serialized`; `sync`/`switch` refuses while an Editor is open | §Version control → `reference/version-control.md` §1, §6 |
| `AMBIGUOUS_EDITOR` exit `6`; no instance in `unity status` while an Editor is open; a long bake blocks the step | §Driving a connected Editor |
| "Find every material in Assets/UI", "what references this texture" | skill `unity-search` |
| Tests "passed" but you do not believe it | skill `unity-debug` → `reference/harness-trust.md` |
| You need the Editor to *do* something, not just start | skill `unity-debug` → `reference/editor-control.md` |

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Driving a running Editor to verify a change; screenshots; Safe Mode; a run that did nothing | `unity-debug` |
| Android signing, keystores, artifact verification | `unity-android-release` |
| WebGL/WebGPU builds | `unity-web-release` |
| Which packages a project needs; `.gitattributes`, LFS patterns, `.meta` policy | `unity-new-project` → `reference/version-control-setup.md` |
| "find / where is / what references X" | `unity-search` |
| An iOS build into an app running on a device | `unity-ios-build` |

## Install, and the one that catches everyone

```bash
which unity && unity --version          # detect before installing
curl -fsSL https://public-cdn.cloud.unity3d.com/hub/prod/cli/install.sh | UNITY_CLI_CHANNEL=beta bash
```

The script checks the binary's SHA-256 against the release manifest (drop `| bash` to read it
first). **Open a new shell afterwards** — the PATH entry is not in this one; `unity doctor` checks.

## The conventions that apply to every command

Output is `--format human|json|tsv|ndjson|github`; CI passes `--non-interactive --yes`; every env
var is `UNITY_`-prefixed and **a flag always beats an env var**. The full table — paging, the ten
display languages — and the surface this skill leaves to `--help`: `reference/everyday-commands.md` §4–§5.

**The message in an annotation is localized; the code beside it is not.** `UNITY_LANGUAGE=en`
does **not** override the persisted display language, so a CI job that greps English error text
passes or fails on a developer preference stored on the runner. Branch on `errors[].code`.

**A failure is still a complete document on stdout**, and `data` can be present and well-formed
while `success` is false — so **branch on `success`, never on the presence of `data`**
(`reference/ci-surface.md` §7).

## Exit codes are the interface

**This table is the `unity` CLI's own set.** The Editor binary uses a different one (§The other
CLI); reading one against the other turns a run that never started into a green tick.

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
over `7`; `unity vcs merge-setup --check` adds `4 = work remains`.

**One Editor per project at a time:** a second `unity test` on the same project returns `6` rather
than queueing, retryable once the first exits. **`2` is checked before the project is**, so a
project path that does not exist is a `6` — retryable on paper, though no retry grows a
`ProjectVersion.txt`. Read `errors[0].code` first (`ci-surface.md` §1).

> Retrying an `8` reruns a genuine failure until it flakes green. A suite retried until it passes
> is indistinguishable from a suite with no assertions.

## The other CLI: the Editor binary itself

Test drivers, scaffolders and anything needing a flag the CLI reserves invoke
`…/Unity.app/Contents/MacOS/Unity` directly, and it answers with its **own** undocumented codes —
in which `0` also covers a locked project and a `-quit`ed async method, and `1` and `3` both mean
nothing ran. So **take the verdict from the results file, not from `$?`**, check the licence
session first (§Auth and licence), refuse to start while an Editor holds the project, and **never
pass `-quit` to `-runTests` or to an async `-executeMethod`**.

The full code table, log greps, `pgrep` patterns, bash 3.2 traps and a driver script:
`reference/editor-binary.md`.

## Auth and licence, before anything else

A stale login makes **every** headless command fail at once with `No valid Unity Editor license`
and Editor exit `198` — it looks like a compile failure and is not a project problem.

Run `unity license status --format json` first and **branch on `data.active`, not on the exit
code**; `unity auth status` says `stale` when the session has expired, and `unity auth login` (or
opening Unity Hub once) fixes it. The healthy JSON and a wrapper-ready grep:
`reference/editor-binary.md` §3.

## Editors, modules, templates, projects

`unity install lts --module android --yes --accept-eula` installs; `unity editors --installed
--format json` proves it landed. **One failed module does not abort the batch** — read per-item
status from the NDJSON `result` frame's `items[]`, not the exit code. List template ids with
`unity templates list --format json`; never guess one. `unity projects create … --vcs
github|uvcs` sets up version control in one step, with `--no-initial-commit` and **secrets on
stdin**. Recipes: `reference/everyday-commands.md` §1–§2.

## Running, building, testing

```bash
# batch mode is implied; -batchmode/-quit/-projectPath/-useHub/-hubIPC are refused
# before launch (exit 6), in every spelling: -x, --x, -x=v.
unity run <proj> --editor-version <v> --allow-install --timeout 300 \
      -- -executeMethod Builder.Build -logFile out.log
```

`unity build` takes **exactly one** strategy — `--target` with `-o`, or `--profile`, or
`--execute-method` — and mixing two exits `2`. `unity test`'s filter flag is `--filter`, never
`--testFilter`; its report grammar is `--report-format nunit,junit` with `--output` and
`--junit-output`.

Before the CI step: **`unity test` deliberately does not pass `-quit`** (it can kill the Editor
before the report is written); **`unity build` can sign Android itself, but argv is visible** —
use a build script reading a gitignored env file (`unity-android-release`); leave
`--allow-dirty-build` off; `--retries` labels a flake, it does not launder one.
Report, coverage and sharding grammar, build strategies, fan-out, envelopes, jobs, reserved flags:
`reference/ci-surface.md`.

## Version control with Unity semantics

`git` does not know that a scene is YAML ordered by serialization, that a `.meta` file *is* the
reference, or that a changed GUID breaks every prefab pointing at it. `unity vcs` does — the only
reason to prefer it over porcelain you already have.

```bash
unity vcs diff Assets/Scenes/Gate.unity      # by GameObject and component, not fileID
unity vcs blame Assets/Scenes/Gate.unity --object Runner --field m_Mass
unity vcs merge-setup --check                # exits 4 while work remains: a CI gate
unity vcs affected --since main              # assets, prefabs, scenes, asmdefs, tests
```

They need **Force Text** (a binary asset answers `outcome: binary-serialized`); `--since` means a
revision on `affected`/`summarize` and a git date on `git migrate-lfs`; never hand-edit the YAML.
Verb map, identity confidence, worktrees, LFS migration: `reference/version-control.md`.

## Driving a connected Editor, and detaching the long jobs

An Editor with `com.unity.pipeline` installed publishes its registered commands to the CLI — and,
through `unity mcp configure`, to an agent as tools (`reference/mcp-and-shell.md`). Three read-only
entry points:

```bash
unity status --format json      # port, project, version, PID, state — the availability gate
unity list                      # what this Editor exposes; discovery only, runs nothing
unity command --detail compact --limit 20   # same catalogue, and this one can run them
unity command eval 'return UnityEngine.Application.unityVersion;' --format json
```

**A headless Editor shows up in `unity status`** (`state: "ready"`). **Name `--project-path`
whenever a second Editor could be running** — without it the deepest project containing the
working directory wins, and a tie exits `6` `AMBIGUOUS_EDITOR` with `data.candidates[]`
(resolution order: `reference/mcp-and-shell.md`). Long work: `--detach`, then
`unity job wait <job-id>` **with a real `--timeout`** — the default waits forever
(`reference/ci-surface.md` §7; `--package-version` pinning §9).

## Diagnosing the tool

`unity doctor --ci` is the first step of any pipeline. **`unity projects verify . --strict` is the
cheapest gate there is** — it reads the asset tree from disk without starting Unity, so a conflict
marker inside a `.unity` file costs a second, not twenty minutes of build (`reference/ci-preflight.md`
§4). The rest of the set, and why `unity logs` is the Hub's log and not `Editor.log`:
`reference/everyday-commands.md` §3.

**`unity skill install <client>`** writes the CLI's own agent skill into a directory named
`unity-cli` — this skill's name, so it silently shadows one or the other
(`reference/mcp-and-shell.md`).

## Discipline

- **Feed it trusted input only.** `unity shell`, `--protocol ndjson`, `command eval` and
  `projects exec` run what they are handed, as you: never a line from a log, an issue or
  unreviewed model output.
- **"No instances" inside a sandbox is not proof the Editor is down** — ask, name the sandbox, and
  never switch it off or quietly run headless instead (`reference/mcp-and-shell.md`).
- **List, never recall** template ids, command names and package ids (`--format json`).

## Reference

`reference/ci-surface.md` (reports, coverage, builds, jobs) · `reference/ci-preflight.md`
(`unity ci init`, `doctor --ci`, cache key) · `reference/version-control.md` · `reference/editor-binary.md`
(raw `-batchmode` codes, wrapper guards) · `reference/everyday-commands.md` (editors, templates,
projects, diagnosis) · `reference/mcp-and-shell.md` (MCP clients, targeting, sandbox, REPL).
