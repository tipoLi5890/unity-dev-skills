# Running the build: from an accepted proposal to milestones, decisions and agents

> Part of the `unity-game-brief` skill. Templates: `templates/DECISION_LOG.md`,
> `templates/AGENT_BRIEF.md`.

The first interaction is played and the proposal is accepted. What follows is days of work, often
by several agents at once, for a person who looks in a few times a day. This page covers what
made a one-day 3D tennis build fast, and the rules that would have stopped what went wrong.

---

## 1. Rebuild or port the prototype

A prototype from another tool is a cheap source of **intent**: the look, the screens, the
numbers somebody tuned. It is an expensive source of **structure**. Port it when its structure
survives the brief's invariants. Rebuild it when one of these is true, because each one is a
property of the whole design and cannot be patched file by file:

| Fault in the prototype | What it produced | Why a port keeps it |
|---|---|---|
| Scoring decided by the animation | A PERFECT judgement that whiffed; matches that could not be replayed; feet sliding 0.6 m | Every presentation change becomes a rules change |
| The ball was a parabola to a precomputed landing point, with no drag, spin or scene collision | Nothing could hit the net or the fence | The rules have no world to ask |
| One god object owned input, rules and drawing | No test could run without a scene | Splitting it is the rebuild, done slowly |
| Inputs carried no timestamps | Timing quality depended on frame rate | The timing judgement is the game |
| Uncompressed animation clips, about 400 MB | Repo and build size | Re-importing is a pipeline, not a setting |
| No foot IK | Visible sliding | It has to be designed in, not added on |

The rebuild still takes everything that is not structure: the art style (which the person may
lock as "keep the prototype's look"), mockups, tuned constants, and the list of what went wrong.
Write that list into the handoff under "lessons from the prototype, do not repeat"; it is what
stops the new build from re-deriving the same faults.

**The prototype is read-only.** Record its path in the project rules as reference only. Copy
files in with their origin noted; never write into the prototype or its archive, and never run a
tool with the prototype as its working directory.

## 2. Milestones with a named gate

Each milestone has an exit condition that something can check, and a mark (★ here) on the ones
only the person can close:

| # | Content | Exit condition |
|---|---|---|
| M0 | Repo, project, assemblies, tools, build that installs | Compiles; pure tests green; a debug build passes its read-back checks |
| M1 | Pure simulation: physics, rules, bots, replay | Solver convergence ≥ 99.5% over 10,000 targets; golden replay identical; first balance report |
| M2 | Greybox playable, both feel options switchable | ★ the person plays both and picks one |
| M3 | Art direction | ★ the art bible marked LOCKED |
| M4 | First character through the character pipeline | ★ triangle budget; ★ character accepted |
| M5 | Motion system | Motion gates all green; ★ a motion video |

Agents close the unmarked gates by measurement and report the numbers. A ★ gate is never closed
by an agent's own judgement, and a milestone whose gates are not all green is reported as not
done, with which gates fail and by how much: "four of the motion gates still fail" is a correct
report, "M5 done" with a footnote is not.

## 3. Build both options when the choice is about feel

When the brief cannot settle a question by argument, because it is about how something feels,
build both behind a runtime switch and let the person play them. In the tennis build the open
question was the timing cue: press to swing (contact about 0.3 s after the press) or press at
contact. Both were built in M2 behind one setting, and the person chose after playing.

Then:

- **Remove the losing option from the menus**, so nobody ships or tests it by accident.
- **Keep it in the simulation** when it is cheap to keep: it remains a balance baseline (the
  simulation could show the second scheme's win rate was clearly lower) and a test that the
  rules do not quietly depend on one input mode.
- Record the decision with its date and the reason the person gave, in the decision log and the
  project rules.

## 4. The decision log

Three kinds of decision, and each goes to one place (`templates/DECISION_LOG.md`):

| Kind | Who makes it | Where it goes |
|---|---|---|
| **Locked**: the person decided | The person | The project rule file, verbatim and dated, under "do not overturn". Never reopened by an agent |
| **Small**: technical, reversible, inside the brief | The agent | Done, then listed in the hand-back as "decided for you", with the one-line reason |
| **Open**: changes the look, the feel, scope, money or a licence | The person | The open-questions list with the options, the numbers that bear on it and the default the work assumes meanwhile |

What made this fast: agents did not stop to ask about small decisions, and nothing open was
silently decided. When an open question is answered, strike it through in the list with the date
and move the answer to the locked rules; do not delete it, since the next agent needs to know it
was asked.

Measured numbers belong in open questions. "The simulation's top speed is 7.0 m/s; the fastest
run clip is 2.7 m/s; playing it at 1.8× still leaves pops. Lower the top speed to 6?" got an
answer in one line. "Should we change the speed?" would not have.

## 5. Docs drift from code: reconcile after every milestone

Planning documents are written before the code and name things the code never got. In the tennis
build, one pass of writing a code map (one row per source file, checked against the files)
found all of these at once:

- The architecture doc named about ten types that did not exist (planning names such as
  `MatchSim`, `TennisRules`, `BallIntegrator`), and called a triple-buffered snapshot
  "double-buffered".
- The tools section listed three scripts that were never written, and the tools doc said a
  script that existed was "not ported yet".
- A balance file named in a header and in the architecture did not exist; the live values were C#
  defaults.
- Two documented behaviours had no code: a duplicate-press filter and a test that bans certain
  maths calls in the simulation.
- A script's usage line and exit codes disagreed with what it did.

None of these broke a test, and each would have sent the next agent looking for something that
was not there. So **at each milestone's end, reconcile the docs against the code**: every type,
script, file and test a doc names must exist, or the doc says it is planned. A code map makes
this mechanical: each source file has a row with its role and interface, each row carries a stamp
of the interface it was reviewed against, and a `check` fails when a stamped interface changed or
a file has no row. Run the check in a pre-commit hook and the map cannot drift silently. (The hook
needs care when several agents share one working tree; see §6.)

## 6. Several agents on one machine

The build split work across about twenty agents in a day: architecture, simulation, greybox,
venues, art direction, a character pipeline, character integration, a polish pass, motion, code
map areas. Parallel work was the main speed gain. Everything that went wrong came from shared
resources: one working tree, one `main`, one CPU, and a two-Editor memory ceiling.

### Brief every agent with an ownership block

`templates/AGENT_BRIEF.md`. The block that matters most:

- **Paths it may write, and paths it must not touch**, named. "No changes to the simulation,
  match or input code" was checked at the end with `git diff --stat <start>..HEAD -- <paths>` and
  reported as empty.
- **Who owns the main Editor** (lane 0, the only place that writes `Assets/`). Everyone else runs
  read-only tests on clone lanes or works in a lab project outside the repo
  (`unity-debug` → `reference/parallel-runs.md`).
- **The Editor cap**: at most two on the machine, counting every project.
- **Commit and push authority.** Either "leave changes in the working tree, list them, the
  coordinator commits", or "commit only your paths, push only after checking what the push
  publishes".
- **Rule files are not editable on another agent's say-so.** An agent's brief comes from another
  agent; a change to the project rules, settings or permissions needs the person.
- **No `--no-verify`.** If the hook blocks you, report what it blocked on.

### Failures and their fixes

| What happened | Cause | Rule |
|---|---|---|
| A push published six commits by another agent | `git push` publishes every commit between `origin/main` and `HEAD`, whoever made them | Before pushing, `git log origin/main..HEAD --format='%h %an %s'`; push only when every line is yours or the coordinator said so. Report others' commits that went out |
| An agent held back its push: it would have sent about 318 MB of LFS, including a purchased pack whose licence was unconfirmed | Another agent's unpushed commits sat under its own | Right call. The coordinator decides large or licence-bearing pushes (`unity-new-project` → `reference/version-control-setup.md`) |
| The code-map pre-commit hook blocked a docs-only commit | The hook checked the working tree, and another agent's uncommitted code had changed interfaces | Make the hook check the staged tree, or give agents separate worktrees. The coordinator bypassed the hook once with `--no-verify`, the exact move the rule forbids every other agent; a rule with an exception for whoever wrote it trains everyone to find one |
| Smoke tests went red, frame times read 2 to 5 times high | Blender and a second Editor ran beside the tests | Look at the machine before a timing run; compare only numbers taken under the same load (`unity-debug` → `reference/parallel-runs.md`) |
| A coordinator's brief gave a pipeline's stages in the wrong order | The brief was written from memory of the plan | The agent wrote the order the script runs and reported the disagreement. Ask every agent to end its report with "where the brief and the code disagree" |

### The coordinator's own loop

- Brief, launch, and keep working on what is not delegated. Read each hand-back's file list and
  numbers, not its summary line.
- After each hand-back, check `git status` and `git log origin/main..HEAD` before anything else
  is committed: hand-backs arrive while other agents are still writing.
- Relay what one agent found that changes another's work (a vendor clip failing a gate, a
  measured speed mismatch) to the agent that owns it, not into a summary for the person.
