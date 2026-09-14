# Version control that knows what a scene is

> Part of the `unity-cli` skill. Global flags, env vars and the CLI's own exit codes are in
> `SKILL.md` and apply to everything here.

**These verbs come from the CLI's own documentation, not from a run on this machine.** Take the
shape and the traps from this page, then **confirm the flags with `unity vcs <verb> --help`**
before a script depends on them.

---

## 1. Why any of this exists, and two preconditions

You already have `git`. Each verb earns its place by knowing one thing a generic tool cannot: a
scene is YAML ordered by **serialization**, not structure, so a one-object edit lands as hunks
scattered through thousands of unnamed lines; a `.meta` file **is** the reference; switching
branches under a live Editor invites a reimport storm; and a GUID that changes takes down, without
a word, every prefab that pointed at it.

That is also why hand-editing the YAML is the wrong repair. `fileID` and GUID references fail at
load rather than at edit; a running Editor holds the file in memory and overwrites your change on
save; and it is easy to edit a file the project never loads (`unity-debug` →
`reference/harness-trust.md`). Drive a live Editor instead — `unity-debug` →
`reference/editor-control.md`.

**Force Text.** `diff`, `blame`, `explain` and `resolve` all parse YAML. Against a binary asset
they report `outcome: binary-serialized` — an answer, not a failure and not an empty result. Where
Asset Serialization Mode is set: `unity-new-project` → `reference/generated-assets.md`.
**Repository policy is somebody else's file:** `.gitattributes` content, LFS patterns and `.meta`
commit policy belong to project setup — `unity-new-project` →
`reference/version-control-setup.md`.

## 2. The verb map

| Verb | Answers |
|---|---|
| `vcs setup` · `vcs providers` | Get into version control; which host this machine reaches, as whom |
| `vcs status` | What changed, bucketed by what it means to Unity, with meta-pairing faults called out |
| `vcs sync` · `vcs switch <branch>` | Pull, or move to another branch, without ignoring an open Editor or LFS |
| `vcs doctor` | Is this repository's Unity configuration — ignores, LFS patterns, pinning — actually right |
| `vcs merge-setup` | Wire up the scene and prefab merge driver so merges are possible |
| `vcs conflicts` · `vcs explain <path>` · `vcs resolve` | List, understand, resolve |
| `vcs diff <path>` · `vcs blame <path>` | What changed inside a scene; who last changed each object |
| `vcs summarize` · `vcs affected` | What this branch changed; what a change reaches |
| `vcs hooks` | Put the Unity integrity checks on commit, checkout and merge |
| `vcs git migrate-lfs` · `vcs git worktree add\|remove` | The git-only verbs |
| `vcs uvcs …` | Unity Version Control reads joined to your project |

**`vcs doctor --fix` is idempotent by contract**, and is not `unity projects verify`: that one
checks the asset tree, this one the repository's Unity configuration. **`vcs providers` spawns the
provider CLIs and makes network requests**, and never resolves a token — a read-only report must
not prompt for a credential.

## 3. `vcs diff` — by object, with a confidence

```bash
unity vcs diff Assets/Scenes/Gate.unity                        # HEAD vs the working tree
unity vcs diff Assets/Scenes/Gate.unity --from main --to HEAD
unity vcs diff Assets/Prefabs/Runner.prefab --format json
```

`--from` defaults to `HEAD`; **`--to` defaults to the working tree**, which is a different
comparison from `--to HEAD`. Rows read as GameObject, component, hierarchy path, before→after.

**Identity carries a confidence, and below `exact` it is a hypothesis.** Matching falls through
three tiers: `fileID` with the class tag; failing that, the class together with the object's name
and hierarchy path; failing that, similarity of content. Re-serialize a scene and the renumbered
`fileID`s push every row down a tier. The failure to watch for is a rename reported confidently as
a delete plus an add.

**A prefab override is flagged, not attributed.** The override lives in the *referencing* asset,
inside `PrefabInstance.m_Modification`. The row therefore lands on the instance, carries a
`prefabInstance` flag, and attribution ends at that point — never as "the runner's mass changed".

## 4. `vcs blame` — who last changed this object

```bash
unity vcs blame Assets/Scenes/Gate.unity --object Runner
unity vcs blame Assets/Scenes/Gate.unity --object Gate/Actors/Runner --field m_Mass
unity vcs blame Assets/Scenes/Gate.unity --at v1.4.0 --max-revisions 50
```

`git blame` on a scene answers "who last touched line 4,812", a question nobody has. This answers
"who last changed the runner's Rigidbody".

- `--object` accepts three spellings: the object's own name, its hierarchy path, **or the name of
  the GameObject holding it** — so `--object Runner` returns the runner and every component on it.
- `--field m_Mass` pins every row to the latest commit in which that field moved, and objects
  without the field drop out of the answer. `--at <rev>` blames as of another revision, so a release branch can be
  asked what it shipped.
- `--max-revisions` (default 200) caps how far back the walk goes. What it budgets is **time**:
  memory scales with how many objects the scene holds, not with how many revisions are read.

Three honest answers instead of a confident wrong one: `confidence` below `exact` (identity was
matched, not established); **`walkBounded: true`** (the bound was hit with that object still
unchanged, so the real answer is older — raise `--max-revisions`); and `historyCrossedNonYaml` (the
walk met a binary-serialized revision and halted there, instead of handing every object in the file
to whichever commit switched serialization mode).

## 5. `vcs merge-setup` — and the exit code that makes it a gate

A fresh Unity repository cannot merge a scene or a prefab at all. Every Editor install ships
`UnityYAMLMerge`; this verb writes the `.gitattributes` entries, configures the merge driver, and
runs a test merge proving the tool executes (`--skip-verify` drops that proof).

```bash
unity vcs merge-setup
unity vcs merge-setup --check          # report only
unity vcs merge-setup --editor-version <version>
```

**`--check` exits `4` while work remains** — which is what makes it a CI gate, and why a `set -e`
script stops there by design. A `merge=unityyamlmerge` line committed at project setup is a
*declaration*; this verb is what makes it true on this machine.

## 6. `vcs sync` and `vcs switch` — the refusal is the feature

```bash
unity vcs sync --rebase --verify
unity vcs switch main --dry-run           # runs the checks, prints the reimport scope, changes nothing
unity vcs switch main --close-editor
```

Both **refuse while an Editor holds the project**. Reach for `--close-editor` *before* `--force`:
closing the Editor is the supported order, forcing past it is how a `Library` ends up half-written.
`sync` pulls LFS objects too and reports the reimport the pull causes (`--rebase`,
`--allow-dirty`, `--verify`); `switch` adds `--discard-changes`. Run `--dry-run` before any branch
change that moves assets.

## 7. `vcs affected` and `vcs summarize` — a graph with holes it admits to

`vcs affected` follows GUID references outward: the changed asset → whatever prefabs hold its GUID →
the scenes holding those → asmdefs → the tests inside them. `--since <rev>` measures from that revision's **merge base** with
`HEAD`; bare, it reports uncommitted work.

> **The report is a lower bound and every format says so.** Addressables groups, `Resources`
> lookups, load-by-name code and binary assets are real dependencies no static reader sees.
> `--format json` carries `lowerBound` and a count of `holes`; skipping work on this trades
> correctness for time. `unity test --affected` consumes the same graph and is documented to refuse
> rather than guess when the diff carries non-code changes — confirm that with `--help`.

`vcs summarize --since <rev>` is the pull-request shape: counts by Unity category plus the risks a
reviewer should see — a GUID that moved and may have broken a reference, an asset relocated while
its `.meta` stayed behind, binaries no reviewer can read as text, a changed package manifest. `--since` is **required** here
and takes a **revision**. It is the one verb not gated on a Unity project root, so it runs from a
monorepo root one level above the project — which is where pull-request bodies get written.

## 8. `vcs git worktree` — a second branch without a full reimport

```bash
unity vcs git worktree add feature/hazards --into ../hazards --seed cache
unity vcs git worktree add feature/hazards --install-editor --dry-run
unity vcs git worktree remove ../hazards
```

Creates the worktree with the right Editor version, seeds `Library`, and registers the checkout
with the Hub. `--seed` takes `cache`, `full` or `none`, and the default **withholds
`PackageCache/`** on purpose. That folder is most of a real `Library` — on the order of three bytes
in four — and seeding it is *slower* end to end, since the import repopulates it out of UPM's
machine-wide store regardless. `remove` takes the path as an operand, so no bare invocation can
delete the checkout you are standing in.

## 9. `vcs git migrate-lfs` — prints, never runs

Finds binaries already committed to history and **prints** the `git lfs migrate import` command for
them, because this rewrites history.

> ⚠ **`--since` here is a git DATE** (`--since "6 months ago"`), while `vcs summarize --since` and
> `vcs affected --since` take revisions. One flag name, three verbs, two meanings.

**The recommendation is narrower than the report.** Set a `--min-size` floor and a long history
will surrender build output, sourcemaps and documentation just as willingly as it surrenders
textures — and source code pushed into LFS can no longer be diffed or merged at all. So the include
list stays at two things: file types the shipped `.gitattributes` template already sends to LFS, and
types this repository tracks today. The rest is listed, then explicitly declined. **A bounded scan
still prints an unbounded migration**: `--everything` rides on the printed command, because any
branch a rewrite skips keeps its blobs reachable and the repository never gets smaller.

## 10. Hooks, conflicts, explain, resolve

`vcs hooks install | status | uninstall` maintains `pre-commit`, `post-checkout` and `post-merge`
inside a managed block, so uninstall leaves hand-written hook content alone.

Then the conflict three, in the order a merge presents them: `vcs conflicts` lists every unresolved
conflict classified by Unity type **with an auto-mergeable column** — the column that says which
ones need a human; `vcs explain <path>` says what each side changed, per object, in one file (no
repository-wide form exists, because the output is per object); `vcs resolve` defaults to `--merge`
through `UnityYAMLMerge`, so §5 has to have run first, and also takes `--ours`, `--theirs` and
`--all` (which replaces the path operand).

## 11. Machine output

Every read verb takes `--format json` / `--ndjson` with the standard envelope. **The `data` payload
is unsanitized** — object names, paths and field names spelled as the file spells them, since that
is what a consumer matches back against the asset; human and `tsv` output are cleaned up for
display. **`tsv` is the default whenever stdout is redirected**, not `human`. The advisories —
identity confidence, a bounded walk, the lower-bound caveat — are written to **stderr**, so a script
reading stdout keeps them instead of losing them.

| Field | Verb | Branch on it because |
|---|---|---|
| `confidence` | `diff`, `blame` | Anything under `exact` is a match, not proof of identity |
| `walkBounded` | `blame` | The real answer may be older than the one reported |
| `historyCrossedNonYaml` | `blame` | History reached a binary revision and the walk stopped |
| `prefabInstance` | `diff` | Attribution ends here; the override lives in the instance |
| `lowerBound`, `holes` | `affected` | Edges a static reader cannot see are missing from the list |
| `outcome` | `diff`, `blame` | Both `binary-serialized` and `not-a-serialized-asset` count as answers |

## 12. Traps

- **One flag name, two readings.** `summarize` and `affected` want a revision; `git migrate-lfs`
  wants a git date.
- **`--vcs` has no `git` value.** It accepts `github`, `gitlab`, `uvcs` or a self-hosted host
  name; anything else fails with `VCS_PROVIDER_UNSUPPORTED`.
- **Three adjacent namespaces.** `unity vcs uvcs <verb>` is a Unity-aware wrapped read with a stable
  envelope — prefer it when something parses the output; `unity uvcs <args>` is an opaque
  passthrough to `cm` in `cm`'s own vocabulary — prefer it when a human reads it, or for a verb the
  wrapper does not cover; `unity collaboration` is Unity Cloud annotations and touches no working
  tree. Deeper UVCS work is `--help` territory.
- **Serialize a scene to binary and every semantic verb above goes dark** — §1.
