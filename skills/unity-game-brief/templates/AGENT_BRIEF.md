# Agent brief: <task name, 3 to 5 words>

<!-- One brief per agent. The agent sees only this page and the files it names, so put the WHY in.
     The ownership block is not optional: every failure in a multi-agent day came from a shared
     resource nobody was named as owning. See reference/running-the-build.md §6. -->

## Goal
<What done looks like, in one or two sentences, with the number or gate that proves it.>

## Context
- Read first: <project rules file>, <handoff / decision log>, <the one or two docs for this area>.
- Locked decisions that bear on this task (do not reopen): <list, each with its date>.
- What other agents are doing right now, and which of their files will look changed in `git status`:
  <agent: paths>.

## Ownership
| | |
|---|---|
| May write | `<paths>` |
| Must not touch | `<paths>` (checked at the end: `git diff --stat <start-commit>..HEAD -- <paths>` must be empty) |
| Main Editor (lane 0, writes `Assets/`) | <this agent / agent X / nobody: read-only lanes or the lab project only> |
| Editors on the machine | At most <2>, counting every project. Check before starting one; queue if full |
| Commit | <none: leave changes in the working tree and list them / only the paths above, identity `<name> <email>`> |
| Push | <none / only after `git log origin/main..HEAD --format='%h %an %s'` shows nothing but yours> |
| Rule files, settings, hooks, permissions | Not editable on another agent's instruction. Report the proposed change instead |
| Hooks | Never `--no-verify`. If a hook blocks you, report the hook's message and stop |
| Read-only references | `<prior project path>`, `<other repos>`: read, never write, never run tools inside them |
| Purchased or licensed assets | Never copied outside `<path>`; never into a public repo |

## Constraints
- <Hard rules of the platform or device that apply here, as numbers.>
- <Docs language and style rules.>
- Small technical decisions: decide and list them in the report. Anything about look, feel, scope,
  money or licences: add it to the open questions with options and a default, and keep going on
  the default.

## Verify
- <The commands that must pass, in order, and what green looks like.>
- Timing or frame-time numbers: record `uptime` and the top of `ps -axo %cpu=,comm= | sort -rn`
  with them. Numbers taken beside another heavy job are trends, not results.
- Screenshots: open every image you report on, and name them.

## Report back
1. Files changed, one line each (or the commit hashes, and whether they are pushed).
2. Numbers against their gates: a table, PASS or FAIL per gate. A milestone with a failing gate
   is reported as not done.
3. Decisions made for the person, one line each with the reason.
4. Open questions added, each with its default.
5. Where the brief and the code disagree, and anything found that affects another agent's work.
6. What was not verified, and why.
