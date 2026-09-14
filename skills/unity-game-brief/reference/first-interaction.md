# The first interaction

> Part of the `unity-game-brief` skill. The first hour ends with something a human can play and
> react to — not a plan, not a scaffold, not a menu. This file is how to choose it, how to build it
> inside one session, and how to hand it over so the reaction is useful.

A brief and a proposal are both guesses about how something will feel. The cheapest way to test a
guess about feel is to make the smallest playable version of it and give it to the person who had
the idea. Everything they say after thirty seconds of playing is worth more than everything they
said about the document.

---

## Choosing it — three rules, all three required

1. **It carries the experience sentence.** If the brief says "launch the runner down one of three
   lanes and get it through the gate", the first interaction is launching, shifting and arriving.
   Not the menu that precedes it, not the score that follows it.
2. **It touches all three layers.** Simulation, presentation and input. A first interaction that
   exercises only one layer proves nothing about the boundary, and the boundary is the part of the
   proposal most likely to be wrong.
3. **It is playable in the Editor by the end of this session.** Not "after the art lands", not
   "once the input system is wired". Placeholder primitives and three keyboard keys standing in for
   three buttons are the point, not a compromise.

Rule 3 is the one that gets negotiated away, and it is the one that makes the other two worth
anything.

### Three candidates the courier run rejected

| Candidate | Why it lost |
|---|---|
| A start menu with a Play button | Touches no simulation. It is the part of the game nobody has an opinion about |
| Track generation, verified by a test only | Touches no presentation and no input. It is a correct answer to a question nobody has asked yet, and it is already covered by INV-4 and INV-5 |
| The sentry closing the gate on a timer | Depends on the gate behaviour that is still the proposal's one open question. Building on an unanswered fork is how a session's work gets thrown away |

The winner: **launch the runner down a lane and reach the gate.** Three commands, one state
machine, one seeded track, one camera. It fails in an interesting way if the run is boring, and
that failure is exactly what the session is for.

---

## Build order inside one session

Roughly two to three hours, and the order matters more than the timings — each step ends with
something that can be checked, so a step that overruns is visible immediately rather than at the end.

| Step | Ends with | Rough box |
|---|---|---|
| 1 · Simulation: phases, commands, config, `Tick(dt)` | It compiles and does nothing visible | 30 min |
| 2 · One test per invariant, each printing its number | A green EditMode run with the numbers in the log | 25 min |
| 3 · Presenter: clock, spawning, mapping, phase logging | Primitives moving in the Game view | 35 min |
| 4 · Input: three keys into the three commands | Playable | 15 min |
| 5 · Camera and framing at the brief's aspect | It reads at the brief's distance | 15 min |
| 6 · A screenshot walk and the hand-back | A numbered PNG per moment, and five lines | 20 min |

**Step 2 before step 3.** Writing the tests while the rules are the only thing that exists is what
keeps them about the rules. Written after the scene exists, they drift into testing the scene, and
the split stops paying for itself.

**If step 3 overruns, cut content, never steps 4–6.** A run with three hazards and no pickups that
a human can play beats a full track nobody has touched. The session's output is a reaction, and
steps 4–6 are the only ones that produce one.

---

## Done, with the proof for each line

Not "it works". Each line has a command behind it, and the hand-back quotes what the command
printed:

| Done when | Proved by |
|---|---|
| The rules compile with no engine reference | `Game.Sim.asmdef` has `"noEngineReferences": true` and the project compiles |
| Every invariant in the brief has a test | One test per `INV-n`, each named after it |
| The tests pass and print their numbers | An EditMode run, then `grep 'INV-' /tmp/tests.log` |
| A human can play it with the game's own inputs | The three commands reach the simulation from the input funnel, nothing else does |
| The moments in the brief were photographed | A numbered PNG per moment, each with its state logged next to it |
| The hand-back is five lines | `templates/REPORT.md` |

Deleting the results file before the run, proving the run happened, and reading a screenshot the
agent took itself are `unity-debug` → `reference/visual-checks.md`.

---

## The loop after they play it

The first reaction is the most valuable data in the project and the easiest to waste. Four steps:

1. **Watch, or ask for exactly one sentence.** "What did you want to do that you couldn't?" beats
   "what do you think?" — the second one gets a review of the placeholder art.
2. **Turn the sentence into a change with a number.** "It comes in too fast" is a feel report, not a
   bug; it becomes a value and a band before anything is touched. Turning a feel complaint into a
   repeatable, named situation and a test that holds after the fix is `unity-play-harness`.
3. **Change one thing.** One value, one file. Two changes and the next reaction is unattributable,
   and this is the loop where attribution is worth the most.
4. **Re-run the same situation and hand back the same five lines.** Same seeds, same numbers, so the
   before and after sit side by side. Then ask them to play it again — the judgement of feel stays
   with the human, always.

Three rounds of that in an afternoon is a tuned first interaction. Zero rounds, with a long document
instead, is a first interaction nobody has an opinion about.

---

## What the first session does not do

Each of these looks like progress and costs the session its output:

- **A menu, a pause screen or a settings panel.** None of them is the experience sentence.
- **Saving, scoring persistence or a profile.** The run is 20–40 seconds; it can be replayed.
- **Audio.** It changes feel enormously, which is why it comes after the feel it is changing has
  been reacted to once.
- **Object pooling, addressables, streaming.** Optimisations against a cost nobody has measured.
  Measure first: `unity-profiling`.
- **Final art.** The look is locked as five decisions and an anchor image; production art is
  `codex-visual` and the asset skills, and it starts once the interaction is worth dressing.
- **A second interaction.** The most tempting one. Build it after the first one has been played,
  changed, and played again.
