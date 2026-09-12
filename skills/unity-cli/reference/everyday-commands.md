# Everyday commands — editors, projects, diagnosis

> Part of the `unity-cli` skill. Global flags, env vars and the CLI's own exit codes are in
> `SKILL.md` and apply to everything here. `unity <command> --help` is the authority on flags.

## 1. Editors and modules

```bash
unity releases --stream lts --limit 5 --format json
unity install lts --module android --module ios --yes --accept-eula
unity install 6000.0.47f1 --resume | --force | --dry-run | --list-components
unity install-modules --editor-version <v> --module android --retries 3
unity editors --installed --format json     # did it actually land?
unity editors running --format json         # what is open, on which project, which PID
unity editors path <v> --format json        # install dir, offline, no release feed
unity editors upgrade --all --dry-run       # same major.minor → latest f patch, modules follow
unity editors prune [--remove --yes]        # editors no registered project uses
unity editors verify <v>                    # structural check; prints the repair command
```

`-m android ios` (space-separated) is the same as repeating `-m`. **One failed module does not
abort the batch** — read per-item status from the NDJSON `result` frame's `items[]`, not from
the exit code alone.

## 2. Projects and templates

```bash
unity templates list --editor lts --format json      # list real ids; never guess one
unity projects create "MyGame" --path ~/Unity --editor-version lts \
      --template com.unity.template.3d
unity projects info <path> --format json             # reads editorVersion
unity open <path>            # unity <version> [path] is the same thing
```

Creating with version control in one step — three shapes, and the choice is the user's:

```bash
# GitHub/GitLab; token on STDIN, never in argv
unity projects create "MyGame" … --vcs github --git-namespace org --git-repo g \
  --git-visibility private --git-default-branch main --git-token-stdin --git-lfs --no-initial-commit
# UVCS — handles large binaries natively, needs no LFS
unity projects create "MyGame" … --vcs uvcs --vcs-region <region>
```

`--no-initial-commit` matters: an initial commit taken before packages resolve and `.meta`
files exist is a commit you will immediately have to amend.

> **Secrets go in on stdin.** A token expanded from an environment variable is still visible in
> the process list, and CI must mask it in logs on top of that.

## 3. Diagnosing the tool

```bash
unity doctor --format json          # auth, editors, recent errors, proxy, PATH
unity doctor --ci                   # first step of any pipeline
unity license status --format json  # §Auth and licence — read data.active, not the exit code
unity env --format json             # paths, and the proxy actually resolved
unity cache key --target Android    # deterministic CI cache key
unity projects verify . --strict    # meta/GUID/conflict-marker check, no Editor launched
unity diagnose proxy --json
unity diagnose update               # why this install is or is not updating
unity bug --title … --steps … --share-project .
```

`unity projects verify` is the cheapest gate in the list. Its checks and flags are in
`reference/ci-surface.md` §10.
