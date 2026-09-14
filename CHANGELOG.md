# Changelog

Versions are the plugin's, in `.claude-plugin/plugin.json`.

## 0.15.0

Thirty-four load-by-situation skills, each teaching the same three things: what to check, the call
that checks it, and the script that does it for you.

- **`unity-urp-migration`** — a Built-in Render Pipeline project moved to URP in five gated phases,
  every gate read back from the **saved** project rather than from the converter log, plus the four
  traps that let a half-moved project report success: an assignment that sits in Graphics settings
  but not in the quality tiers, 3D materials claimed by the 2D shader provider, a Volume profile
  that reloads empty because its overrides were never added as sub-assets, and lighting that is
  still Built-in baked data.
- **`unity-search`** — a *find / where is / which prefabs use / what references X* question turned
  into one Unity Search query: asset type filters, folders, labels, `ref=` relationships and scene
  component queries, written out before it runs and opened in a live Editor when one is reachable.
  Read-only — it never selects, moves or edits a result.
- **`unity-cli` grows the two surfaces a repo hits first.** `reference/version-control.md` covers
  the verbs that know what a scene is — `vcs diff` and `blame` by object and field with their
  identity-confidence levels, `merge-setup` and its `--check` exit, `sync`/`switch` refusing while
  an Editor holds the project, `affected`/`summarize` and why their answer is a lower bound, and
  the three different meanings of `--since`. `reference/ci-preflight.md` covers `unity ci init`,
  the `doctor --ci` exit codes that say whether a retry is honest, and `cache key`.
- **The TMP Essentials import no longer hard-codes a package path.** `unity-localization` scans
  `Library/PackageCache` for the resource package instead, and names the menu item that returns
  `true` and then blocks a headless run on a modal dialog.
- **Smaller additions across the UI, 2D, runtime and backend skills** — USS patterns, sprite and
  atlas scripts, NavMesh areas and costs, a URP pre-flight snippet, package selection, and the
  documentation maps the services SDKs publish.
- **One layout for every skill.** `SKILL.md` is a router with a symptom table; `reference/` holds
  the depth it names; `resources/`, `scripts/` and `templates/` hold what you run or copy. No skill
  keeps content at its own root.
- **Every section is a method section** — what to check and how to check it, in present tense,
  never a record of how this repo checked it. A doubt that should change what you do is written as
  a step you run, not as a hedge.
- **Package tables** keep ids and API floors, and point at `Packages/packages-lock.json` for what
  actually resolved.
- **Skills route to each other, never out of the repo.** Each one's `Scope — what this skill does
  NOT do` section hands you to the right neighbour, so you land in the right skill from any
  direction.
- **Gates, run by CI on every push and pull request:** `tools/lint-skills.py` (frontmatter, name
  matches directory, shipped executables parse), `tools/check-consistency.py` (the two manifests
  agree, every route out of this repo is declared) and `tools/sync-codex-manifests.py` (the Codex
  manifests are generated — never hand-edit them).
