# Driving a live Editor — loop 0

> Part of the `unity-debug` skill. The other three loops in `SKILL.md` all pay for a cold start.
> This one does not. Read it when you are about to run `-batchmode` more than twice in a row.
>
> The `unity` CLI's full surface — editors, licences, templates, CI, MCP — is the `unity-cli`
> skill. What follows is only the part a debugging loop needs, plus the traps that cost real
> time.

## Why this loop exists

`-batchmode` is ~20 s warm because every invocation boots an Editor, reloads the domain and
throws it away. A **live** Editor with the Pipeline package installed accepts commands over a
local socket and answers without recompiling or reloading the domain — the same work, minus
the boot. For an iteration loop that is the difference between "run it once and hope" and
"actually poke at it".

**Expect a first call around a second, then sub-second warm round trips** — against ~20 s for a
warm `-batchmode` round trip. Time it on your own machine before designing a loop around it — the
point of this skill is not believing an instrument you have not checked.

## The mechanism

The project installs `com.unity.pipeline` (a UPM package). Inside a running Editor it opens a
local server, one lockfile plus one auth token **per Editor instance**. The CLI discovers it
and connects. Nothing is exposed off the machine and the token is why you cannot point the CLI
at a bare `host:port`.

```bash
unity pipeline install [--project-path <p>] [--force] [--package-version <v>]
unity pipeline list                      # every Editor instance + its package status
unity status --format json               # port / project / version / PID / state
unity command                            # list the commands THIS Editor exposes
unity list --format json                 # same catalogue with argument schemas
unity command eval 'return UnityEngine.Application.unityVersion;'
unity command screenshot --output ./shot.png --width 1920 --height 1080
```

`unity pipeline install` edits `Packages/manifest.json`. On a clean tree that is trivially
revertible (`git checkout -- Packages/`), but **check the tree is clean before running it** so
you can tell your change from someone else's.

## Three ways to get a drivable Editor — and one that looks like a fourth

| Want | Do |
|---|---|
| Headless, stays up, no window | Run the Editor binary directly: `-batchmode -projectPath <p> -logFile editor.log &` — **and do not pass `-quit`** |
| A window you can also screenshot | `unity open <p>` |
| One shot in CI, releases the licence seat | `unity run <p> --command <name>` |

> **Bare `unity run <project>` is not a way to get a persistent Editor.** With no `--command` it
> runs and exits. Reaching for it in a loop just reintroduces the cold start you were escaping.

Two things about the headless route:

- It **holds a licence seat until it exits.** The one-shot `unity run` path releases it. If a
  second machine or a CI job suddenly cannot get a licence, look for the Editor you left running.
- **Prove reachability, do not assume it.** The Editor accepts connections only once the package
  has imported and compiled — on a cold project that is a minute or two after the process starts.
  Poll rather than sleep:

  ```bash
  until unity command --project-path "$PWD" --format json >/dev/null 2>&1; do sleep 3; done
  ```

> A batch-mode Editor **does** appear in `unity status` — listed with its port, PID and
> `state: ready`. Check it on your own version before designing a reachability probe around it.

## `eval` compiles a statement block, not a file

There is no file, so there is nowhere to put a `using` **directive** — the compiler reads the
word as the start of a `using` *statement* and the errors point at the wrong thing:

```bash
$ unity command eval 'using UnityEngine; return Application.unityVersion;'
Compilation Failed
  Identifier expected
  'UnityEngine' is a namespace but is used like a type
  You must provide an initializer in a fixed or using statement declaration
```

Drop it and the same code works:

```bash
$ unity command eval 'return UnityEngine.Application.unityVersion;'     # success
$ unity command eval 'return Application.unityVersion;'                 # ALSO success
```

> **Common namespaces are already imported.** Guidance that says every type must be fully
> qualified is over-strict — bare `Application` resolves.
> Qualify when a name is genuinely ambiguous (`Debug` exists in both `UnityEngine` and
> `System.Diagnostics` — that one is `CS0104`), not as a ritual.

## Extending the catalogue from inside the project

The command list is defined by the Editor, not by the CLI, so a project can add its own without
anyone upgrading anything. Put this in an **Editor** assembly:

```csharp
using Unity.Pipeline.Commands;

[CliCommand("spawn_light", "Create a GameObject with a Light", MainThreadRequired = true)]
public static string SpawnLight([CliArg("name", "GameObject name")] string name = "Light")
    => new GameObject(name, typeof(Light)).name;
```

Must be `static`. `MainThreadRequired` defaults to true — leave it on for anything that touches
engine state. After editing: `unity command recompile` → poll `unity command recompile_status`
until `completed` → `unity list` to confirm it registered. **Never assume the name you wrote is
the name that registered** — list it.

Same rule for built-in commands: `unity command --format json` is the catalogue. Do not cite a
command name from memory. When the catalogue is long, `--query`, `--tag`, `--detail compact`,
`--limit` and `--offset` trim it. Two sharp edges: `--group_by` really is an underscore, and
**when a command name is present these listing flags are forwarded to that command as arguments
instead** — which is why every one of them takes an optional value.

## Safe Mode is a deadlock, not an outage

A C# compile error puts the Editor in Safe Mode. Safe Mode does not load packages. The Pipeline
package is a package. So `unity command`, `unity status`, `unity list` and the MCP server all
stop answering — **because of the very errors you were going to use them to fix.**

There is no CLI-side escape. Work it in this order:

1. `unity pipeline list --format json` → `data.summary.instancesInSafeMode`, or per instance
   `data.instances[].safeMode` (**`null` when healthy** — do not test it for a
   `detected` field that is not there in a normal response).
2. `grep -iE 'error CS[0-9]{4}|Scripts have compiler errors' <log> | tail -40`
3. **Fix the file by hand.** This is the one situation where hand-editing is correct — everywhere
   else, drive the Editor.
4. Restart by PID: `unity pipeline list --format json` → `data.instances[].pid` → `kill <pid>`.

> **Never `pkill -f Unity` or `killall Unity`.** They match on name, and they will take down every
> Editor on the machine — including other projects with unsaved scenes.

> **Killing an Editor leaves `Temp/UnityLockfile` behind, and the next `unity test` dies
> instantly against it** — exit 0, an empty log, no results file. This is the same
> stale-lockfile trap `reference/harness-trust.md` opens with, except here *you* created it by
> following the advice above. Clean up after yourself, and check before you delete:

```bash
pgrep -fl "Contents/MacOS/Unity( -|$)" && echo "still running — do NOT delete" \
                                       || rm -f Temp/UnityLockfile
```

> **It can also leave the build backend wedged**, which looks like a compile failure and is not.
> The symptom: `unity test` aborts with *"Scripts have compiler errors"* while the Editor
> log actually says *"Internal build system error … The backend process appears to still be
> running"* and contains **no `error CS` line at all**. That absence is the tell —
> `grep -c 'error CS' <log>` returning 0 next to a "compiler errors" abort means the compiler
> never ran. `rm -rf Temp/` and re-run; `Temp/` is rebuildable and holds no project state.

## Two levels of `success`, and only one of them is about your request

The trap that belongs in this skill more than any other:

```jsonc
// unity command screenshot, on a batch-mode Editor with no scene loaded
{ "success": true,                              // ← the COMMAND was delivered and ran
  "data": { "result": { "success": false,       // ← the WORK failed
                        "path": null,
                        "message": "No camera found to capture the Game view …" } },
  "errors": [] }
```

> **The outer `success` means the command reached the Editor. It says nothing about whether the
> command did what you asked.** `errors` is empty. Exit code is 0. A harness that checks either
> one records a screenshot that was never taken — which is exactly the class of lie this skill
> exists to catch.

For any command that produces an artefact, assert on the artefact: `data.result.success`, and
then the file on disk.

The envelope nests one level further than it looks: an `eval` return value lands at
**`data.result.result`**, alongside `data.result.executionTimeMs` — useful for timing a probe
without wrapping it in `time`.

**Commands that change the project refuse by default.** `package_add` returns outer
`success: true` with inner `status: "rejected"` and *"Re-run with confirm=true to apply"* —
a gate, not an error, and invisible to anything checking the outer flag:

```bash
unity command package_add -- --identifier com.unity.2d.sprite --confirm true
unity command package_status          # poll until status is "completed"
```

Two details worth having: the parameter is `--identifier`, not `--name` (a wrong name comes back
as a 400 from the Pipeline server, not as a usage message), and an install that reports
`requiresRecompile: true` may still leave `recompile_status` at `up_to_date` — the domain
reloaded on its own. **Verify by resolving a type you expect**, not by waiting for a status.

Two practical notes on `screenshot` specifically: it captures the Scene or Game view and returns
a path, and a **batch-mode Editor starts with an empty scene, so it has no camera** — open a
scene first, or take screenshots from the windowed loop instead
(`reference/visual-checks.md`). For before/after pairs outside a test run — aiming the Scene view
at a chosen pivot and angle, writing each PNG to its own temp path — there is a drop-in script at
`unity-urp-migration` → `resources/SceneCapture.cs`.

## Reading the envelope, not the exit line

Every machine-format response has the same shape, and a failure is still a complete document on
**stdout** — there is no need to scrape stderr:

```json
{ "success": false, "command": "status",
  "data": { "count": 0, "instances": [] },
  "errors": [ { "code": "STATUS_NO_INSTANCES", "message": "…" } ],
  "warnings": [] }
```

> **Branch on `success`, never on `data`** — and then on the inner `result.success` where there
> is one. The example above is real output: `success` is false while `data` is present and
> well-formed. Code that tests for the presence of `data` reads that as a healthy Editor with
> zero instances.

`errors[0].code` is the stable identifier; the message is not. `--format` accepts
`human | json | tsv | ndjson | github` — check `unity --help` rather than assuming a format
exists, and pair `--non-interactive` with `--yes` in CI.

## Two names that mean the wrong thing

| Looks like | Actually is |
|---|---|
| `unity logs` | The **Hub** log. Not `Editor.log`, not your game's output. Reaching for it to debug a build returns something plausible and irrelevant. |
| `unity list` | The connected Editor's **command catalogue**. Not a list of editors (`unity editors`) or projects (`unity projects`). |

## Installing the package is a project change

`unity pipeline install` adds `com.unity.pipeline` to `Packages/manifest.json` and pulls its
dependencies. On a project that already uses `com.unity.collections`, the import logs:

```
Duplicate assembly 'System.Runtime.CompilerServices.Unsafe.dll' with different versions detected
```

Harmless — the Editor resolves it and the pipeline works. Worth knowing before you attribute an
unrelated compile problem to it.

If you installed it only to debug, revert deliberately:

```bash
git checkout -- Packages/manifest.json Packages/packages-lock.json
```

## Re-measure before you quote

```bash
unity pipeline install --project-path <p>
# start a headless Editor, poll until reachable, then:
for i in 1 2 3 4 5; do /usr/bin/time -p \
  unity command eval 'return UnityEngine.Application.unityVersion;' >/dev/null; done
```

| Loop | Cost per iteration |
|---|---|
| `-batchmode` | ~20 s warm (`reference/cli-harness.md`) |
| live Editor `eval` | **sub-second warm** (a first call around a second) |
