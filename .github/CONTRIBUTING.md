# Contributing to unity-dev-skills

The checks CI runs, and the two rules that keep the manifests honest.

## Working on this repo

```bash
python3 tools/lint-skills.py            # frontmatter + name/dir match + size limits + executable syntax
python3 tools/check-consistency.py      # manifests agree, companions declared
python3 tools/check-registry.py        # asset registry selftests and fixtures, the budget table in one place
python3 tools/sync-codex-manifests.py   # regenerate the Codex manifests
claude plugin validate .                # manifest shape
```

Run them from the repository root.

[`.claude-plugin/*`](../.claude-plugin/) are the sources of truth.
[`.codex-plugin/plugin.json`](../.codex-plugin/plugin.json) and
[`.agents/plugins/marketplace.json`](../.agents/plugins/marketplace.json) are **generated — never
hand-edit them.**

Routing to a plugin outside this repo is a declared dependency: add it to `COMPANIONS` in
[`tools/check-consistency.py`](../tools/check-consistency.py), with the reason. An undeclared one
fails the gate.

What this release contains: [CHANGELOG.md](../CHANGELOG.md).
