# Changelog

Versions are the plugin's, in `.claude-plugin/plugin.json`.

## 0.14.0

Thirty-two load-by-situation skills, each teaching the same three things: what to check, the call
that checks it, and the script that does it for you.

- **Three new skills for the loop a human cannot run by hand.**
  - `unity-play-harness` — build the game so an agent can drive it and read it: a one-line probe
    snapshot readable from a live Editor, `Editor.log` or a PlayMode test; named situations that
    boot straight into a moment and wait on a **readiness set** rather than a sleep; journey tests
    that sample the probe into a timeline and assert invariants over it; and the method that turns
    a feel complaint into a repeatable test.
  - `unity-profiling` — the work behind a slow or uneven frame, as numbers you can compare:
    ProfilerRecorder counters without the Profiler window, 90-frame windows with median/p95/worst,
    scheduled / completed / discarded work counters for streaming and pooling, and a before/after
    table that says whether a change helped.
  - `unity-game-brief` — the first hour, before any Unity work: one line of idea into a one-page
    experience brief, the look locked with images, an architecture proposal **derived** from the
    stated constraints, readiness written as testable invariants, and one interaction the human
    can play and react to.
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
