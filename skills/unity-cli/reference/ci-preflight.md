# CI preflight — scaffolding the workflow, gating it, and keying the cache

> Part of the `unity-cli` skill. Global flags, env vars and the CLI's own exit codes are in
> `SKILL.md`; report grammar, build strategies, fan-out and job envelopes are in
> `reference/ci-surface.md`.

Three commands stand in front of a pipeline: one writes the workflow, one refuses to let a long
step start on a machine that cannot finish it, and one produces the cache key. **Confirm each
one's flags with `--help` on your CLI version** before a pipeline depends on them.

---

## 1. `unity ci init` — write the workflow instead of assembling it

```bash
unity ci init                                     # GitHub Actions → .github/workflows/unity.yml
unity ci init --provider gitlab                   # → .gitlab-ci.yml
unity ci init --target Android --shards 4
unity ci init --dry-run                           # prints the workflow to stdout and writes nothing
unity ci init --project-path ./CourierRun --overwrite
```

`--project-path` is a **flag, not a positional operand** here — unlike `build`, `test` and
`cache key`, which take the project as an operand. Its default is the working directory, which
makes an argument-free `unity ci init` the ordinary invocation from a project root. The templates
live inside the binary: no network is involved, and what lands matches the CLI that wrote it.

**What the generated workflow does, in order.** Install the CLI · restore the Editor download cache
and the project's `Library/` · install the Editor version read from
`ProjectSettings/ProjectVersion.txt` · activate a licence · run `unity doctor --ci` as the preflight
· run the tests with a JUnit report · build · upload the report and the artifact · **hand the
licence seat back in a teardown step that still runs after a failed or cancelled job.** That last
step is the one a hand-written workflow forgets, and a seat nobody returns is a pipeline that stops
working on a Tuesday.

**What it derives from the project.** The Editor version, which is refused unless it reads as a
genuine Unity version number, because the runner's install command has it substituted in — and, where the target
names one unambiguously, the Editor module: `Android`, `iOS`, `tvOS`, `WebGL`, `WindowsStoreApps`,
`VisionOS`, `Lumin`. Desktop standalone targets get **no** module. Each of them has il2cpp, mono and
server variants, and the target name alone does not say which one you want, so `StandaloneOSX` or
`StandaloneWindows64` comes back with a warning that you name the install step's `--module`
yourself.

**Secrets are referenced by name only.** The command reads no credential and the generated file
contains none. It expects `UNITY_SERVICE_ACCOUNT_ID`, `UNITY_SERVICE_ACCOUNT_SECRET` and
`UNITY_LICENSE_SERIAL` to be present as repository secrets, and once the file is written it lists
the ones still missing.

> **A service account is not an Editor licence.** Service-account auth covers Unity *services*;
> `unity license activate --personal` is refused outright for one. The generated step therefore
> activates from a serial, with the floating-licence-server and offline `.ulf` alternatives shipped
> beside it as commented blocks.

**Interactive versus scripted.** On a terminal, whatever went unpassed is asked for — the provider, the build
target, the number of parallel jobs the tests are divided between — each picker opening on its default,
plus a confirmation before replacing an existing workflow. A flag always beats its prompt. No
prompt appears at all under `--non-interactive`, under a machine `--format` — `json`, `ndjson`,
`tsv` — under `--format github`, or with stdout redirected; whatever went unpassed falls to its
default (`github`, `StandaloneLinux64`, unsharded), and a workflow file already sitting there
becomes an **exit `2`** naming `--overwrite` instead of a question. A script therefore behaves the
same way with or without a terminal attached.

**Sharding: `--shards 2..64`.** Off by default. Passing `1` is an error rather than a single-leg
matrix — no spelling of the flag means "do not shard", so leave it off. Asking for more shards than
there are tests is safe: the extra slice comes back empty and its Editor never launches, instead of
the full suite running quietly under a shard's name. The generated matrix covers two cases a
hand-written one usually misses:

- **A cold pipeline has nothing to divide.** `--shard N/M` splits up an NUnit report left by some
  *earlier* run, because listing the tests means running them. Rather than failing, one shard
  executes everything to lay down that inventory while the others exit at once — so the first run
  is green, at the price of a single unsharded suite.
- **A stale inventory is the dangerous case**, because a test written after it belongs to no shard,
  runs nowhere, and is green. The stored inventory therefore hangs off a hash over every `.cs`,
  `.asmref`, `.asmdef` and `packages-lock.json` the repository holds; touch one of them and the
  whole suite is re-seeded. `unity cache key` ignores script edits by design — correct for a `Library/`
  cache, wrong here — which is why this inventory carries a key of its own.

The bargain: a run carrying a C# change buys one unsharded suite, while a run that carries none —
an asset, a scene, a shader, a config edit, a retry, a nightly — is divided `n` ways. **The build
belongs in its own job outside the matrix**: inside it, it would rebuild once per shard and consume
`n` licence seats. No merge step is needed either way, because each provider collects the per-shard
JUnit reports itself.

Under `--format json` the files written appear as `data.paths`, alongside the provider, Editor
version, target and module that were resolved. **Exit `2`** covers an unrecognised `--provider`, a
`--target` that does not validate, a workflow already in place without `--overwrite`, and a stray
positional argument; **exit `6`** means the directory is not a Unity project, or its Editor version
could not be read.

## 2. `unity doctor --ci` — a preflight, not a report

```bash
unity doctor --ci                    # the job's first step
unity doctor --ci --format json      # one row per check, for a workflow to branch on
unity doctor --ci --format github    # failures arrive as inline annotations
```

`--ci` swaps the diagnostic report for a verdict. What it asks is whether this environment could
finish a build or a test run at all: a licence it can activate, the Editor this project requires,
disk headroom, and an answer from Unity's services endpoint. `PATH`, long-path and
git-credential-helper checks ride along as advisory rows that never fail the job.

| Exit | Means | Retry? |
|---|---|---|
| `0` | Every blocking check passed; warnings do not fail the preflight | — |
| `6` | Definitive: no licence, the required Editor is not installed, disk below the floor | **No** |
| `7` | No verdict reached — a required service was unreachable | **Yes** |

**A `6` outranks a `7`** where the two coincide, so nothing that genuinely blocks the job is ever
dressed up as retryable. Each row carries a `code` a machine can read — `LICENSE_NONE`,
`EDITOR_NOT_INSTALLED`, `DISK_SPACE_LOW`, `NETWORK_UNREACHABLE` and the rest — plus a `hint` naming
the fix. Under `--format json` **the per-check rows stay in `data` even on failure**, with one coded
entry per failure in `errors[]`. Output is redacted — no tokens, no absolute user paths — so it can
be pasted into a public log.

> **`--ci` is always explicit and is never inferred from `CI=true`.** A report that quietly changed
> both its shape and its exit code the moment it ran on a runner would be a trap. Remember too that
> redirected stdout already selects `--format tsv`, which on CI is the usual case; the first row of
> that output is the `verdict`.

## 3. `unity cache key` — one hash for the runner's cache step

```bash
unity cache key                      # whichever project the working directory holds
unity cache key --target Android     # Library/ contents differ per platform
unity cache key ./CourierRun --format json
unity cache key --component editor   # a single component, for the restore-keys ladder
```

A single hash over the inputs that genuinely invalidate a project's build cache: the Editor
version, the resolved package set (`Packages/packages-lock.json`, falling back to
`Packages/manifest.json`), and optionally `--target`. It **does not move** for unrelated edits —
scenes, scripts, assets, other project settings. Given the same inputs it is also **the same hash on
every machine and every operating system**: line endings and a UTF-8 BOM are normalised ahead of
hashing, and no path, user name or timestamp is folded in.

Whenever stdout is not an interactive terminal the key is the only thing written, which lets it
sit directly inside a shell substitution or a workflow expression:

```yaml
- id: librarykey
  run: |
    printf 'hash=%s\n' "$(unity cache key CourierRun --target Android)" >> "$GITHUB_OUTPUT"
- uses: actions/cache@v4
  with:
    key: Library-${{ steps.librarykey.outputs.hash }}
    restore-keys: Library-        # for a real ladder, pair this with `--component editor`
    path: CourierRun/Library
```

`--format json` hands back the key together with every component's raw value and hash, so a single
call is enough to assemble a layered key. `--component <editor|packages|target>` prints only that
component's hash for
the fallback rungs, and under `--format json` it becomes `data.key`, keeping `jq -r .data.key`
meaningful in both modes. No Editor and no network are involved. **Exit `2`** on an unrecognised
`--target` or `--component`: were a typo waved through, the key it produced would match nothing —
and **exit `6`** when the directory is not a Unity project. Where neither package file exists a key
is still produced, with a warning that the package set is not represented in it.

## 4. A pipeline skeleton

Nothing exotic — the ordering is the point. Provision, prove the environment, then run.

```bash
set -euo pipefail
unity doctor --ci                      # environment gate; adds 7 = service unreachable
unity license status --format json     # branch on data.active, not on $?
unity projects require . --yes         # install the project's Editor version if absent
unity projects verify . --strict       # META_MISSING, GUID_DUPLICATE, CONFLICT_MARKERS, …
unity cache key --target Android       # deterministic key for the runner's cache step
unity test . --mode EditMode --report-format nunit,junit \
            --output ./results/nunit.xml --junit-output ./results/junit.xml --timeout 900
unity build . --profile "Android Release" -o ./out/app.aab --timeout 3600
```

`unity projects verify` checks a project without launching the Editor and takes
`--check META_MISSING,META_ORPHAN,GUID_DUPLICATE,CONFLICT_MARKERS,MANIFEST_INVALID,EDITOR_VERSION_DRIFT`,
`--strict` (warnings become errors) and `--expect-editor <version>` for the drift check. It is the
fastest gate in the list and the only one that catches a merge-conflict marker inside a `.unity`
file before a build spends twenty minutes finding it. `unity projects clean --dry-run` reports the
regenerable folders (`Library`, `Temp`, `Logs`, …) with sizes and deletes nothing.

A gate worth adding beside these on a repository where scenes get merged:
`unity vcs merge-setup --check`, which **exits `4`** while the merge driver is not wired up —
`reference/version-control.md` §5.
