---
name: unity-game-brief
description: >-
  The first hour of a game or a new feature, before any Unity work: turn one
  line of idea into a one-page brief, lock the look with images, derive an
  architecture proposal from the stated constraints (simulation / presentation
  split, seeded generation, floating origin), write readiness as testable
  invariants, then build ONE interaction the human can play and react to. Load
  for "I want to make a game where…", "here's my game idea", "propose an
  architecture", "what should we build first", "new feature — where do we
  start", "write the brief", "is this ready to build". Editor pinning, asmdef
  mechanics and folders are unity-new-project; art generation is codex-visual.
---

# unity-game-brief — the spec comes last

An idea arrives as one sentence, and the expensive mistake is to answer it with a plan. A plan is
a guess about how something will feel, written in the one form nobody can react to.

> **The first hour ends with a human playing something, not reading something.**
> One page, one locked image, one derived proposal, one playable interaction — in that order,
> because each is worthless before the one above it.

The order is not a ritual. Constants written before the look is settled get re-tuned when it
settles. An architecture chosen before the constraints are written down is a preference nobody can
argue with. And a feature list written before anyone has played anything is a list of guesses, each
of which will be built.

---

## 0. Where in the first hour are you?

```bash
ls GAME_BRIEF.md ARCHITECTURE_PROPOSAL.md ART_DIRECTION.md 2>/dev/null
grep -m1 '^Status:' ART_DIRECTION.md 2>/dev/null
grep -rln 'Situation\|\[PROBE\]' Assets --include='*.cs' 2>/dev/null | head
```

| What is there | Start at |
|---|---|
| Nothing, or one sentence in a message | §1 |
| A brief, no locked look | §2 |
| A brief, and an art direction marked LOCKED | §3 |
| A brief and a proposal; `Assets/` has no gameplay scripts | §5 |
| A brief whose non-negotiables have no numbers in them | §4, then back to §3 |
| A shipping game, and someone wants a new feature | §1's new-feature variant — existing invariants are inherited, not restated |
| A proposal nobody accepted, and work already started | Stop. §3's open question is usually what the work is stuck on |

---

## 1. The brief in five questions

Five, asked **one at a time**, because each answer changes what the next one is worth asking:
player verbs (at most three) → three moments (before, during, after) → where it is played, as
numbers → what must never break → what you are willing to cut.

Then rewrite every answer as a sentence with a number in it and read it back for a yes. "It should
feel fast" is a mood; "a run is 20–40 s from launch to the gate" is a requirement, and the
difference is whether anything can ever check it.

Fill `templates/GAME_BRIEF.md`. **One page.** A second page means a feature list got in.
→ `reference/experience-brief.md`

## 2. Lock the look before the first line of code

Five decisions, and this skill decides only these five: **palette roles** (≤5, one meaning each),
**reactive-vs-ground contrast** as a ratio (3:1 floor by default), **three silhouettes** that stay
tellable apart in black at shipping size, the **camera** (distance, pitch, aspect), and **one anchor
image**. Everything else about art is production.

Budget: 2–3 distinct boards → the human picks → at most 2 correction rounds → locked. Corrections
are one sentence, one axis: *keep [what works], change [one axis], toward [the other end], not all
the way.* A third round means the brief is wrong, not the image.

Generating the boards, the art bible and the anchor is `codex-visual` — that skill generates, this
one decides. → `reference/visual-direction.md`

## 3. Constraints → architecture proposal

The agent proposes; the human accepts or forks it. Every row of the proposal names the constraint
that forced it, so disagreeing is cheap:

| Constraint (from the brief) | Forced decision | Rules out | Routed to |
|---|---|---|---|
| Three physical buttons, played at 2–3 m | Three commands, no analogue input | Aiming, cursors, hover | `unity-game-ui` |
| The same seed must give the same run | Seeded generation inside the rules assembly | Scene-authored levels, engine randomness in gameplay | `reference/sim-presentation-split.md` |
| The look is still moving | Simulation and presentation split; one state type crosses | Rules inside a `MonoBehaviour` | `reference/sim-presentation-split.md` |
| Played in a browser on a tablet | A heap budget as a number, on day one | Unbounded pools, uncompressed everything | `unity-web-release` |
| Real distances in kilometres | Positions relative to a shifting origin | Absolute world coordinates as the source of truth | `reference/architecture-proposal.md` |

The proposal has six headings and a word budget each: layers (≤4) · what talks to what (≤6 arrows,
every arrow's payload named) · swappable (and **the one type that crosses** each boundary) ·
deliberately not done · the first interaction · **exactly one** open question, with the default you
will build if nobody answers. → `templates/ARCHITECTURE_PROPOSAL.md`, `reference/architecture-proposal.md`

The split, in six lines: the rules assembly sets `"noEngineReferences": true`; the presenter reads
state every frame and writes none of it; commands go in as named intents, never device events;
`Tick(dt)` takes a fixed dt from whoever owns the clock; the tests open no scene; one type crosses
the boundary. A skeleton that compiles as-is is in `resources/` — two assemblies, a seeded track,
a presenter, a keyboard stand-in for three buttons, and one test per invariant.
→ `reference/sim-presentation-split.md`. Assembly definition mechanics and folder layout are
`unity-new-project` §5.

## 4. Readiness and invariants as requirements

Six shapes. Each one is a sentence in the brief, an ID, and a test named after the ID:

| Shape | Courier example | Becomes |
|---|---|---|
| Ready together | Lane mesh, its collider, hazards and pickups all exist before the runner is drawn | One construction pass and one readiness flag; live, a readiness set |
| Never | The runner is never outside lanes 0–2, never inside a hazard | One clamp, in one place |
| Always within | A run is 20–40 s from launch to the gate | A band, both ends asserted |
| Reachable | Every hazard row leaves at least one of the three lanes open | Structural, over 1000 seeds |
| Ordering | Idle → Launched → (AtGate \| Crashed), no phase skipped | One transition method |
| Budget | The run holds its frame budget on the tablet | Checked, not enforced |

Numbers come from the device line, the experience sentence, a stated baseline, or a default marked
as a default — never from nowhere. IDs are never reused, and every test prints the number it
asserted on. → `reference/invariants.md`

## 5. The first interaction

One thing, chosen by three rules together: it **carries the experience sentence**, it **touches
simulation, presentation and input**, and it is **playable in the Editor by the end of this
session**. The courier run's answer: launch the runner down a lane and reach the gate — three
commands, one state machine, one seeded track. A start menu fails rule 1; a generator verified only
by tests fails rule 2; anything built on the proposal's open question gets thrown away.

Build order inside the session: rules → one test per invariant → presenter → input → camera →
screenshot walk and hand-back. **Tests before the scene exists**, or they drift into testing the
scene. If it overruns, cut content, never the last three steps — the session's output is a human's
reaction, and only those steps produce one. → `reference/first-interaction.md`

## 6. Role contract

| The human decides | The agent decides, and reports |
|---|---|
| How it looks and how it feels | The implementation and the file layout |
| What is worth building next, and what gets cut | The tests, and what each one asserts on |
| Whether an invariant's number is the right number | How that number is measured |
| Whether it is done | What is provably true right now |

Every hand-back is the same five lines: **numbers, the invariant they were checked against, one
screenshot with its state logged next to it, one change, and one question with the default you will
take if nobody answers.**
→ `templates/REPORT.md`

---

## Load what the situation needs

| The situation | Read |
|---|---|
| An idea with no page yet; a new feature on a shipping game | `reference/experience-brief.md` |
| The look is unsettled; deciding what to lock and when it is accepted | `reference/visual-direction.md` |
| Deriving the proposal, or critiquing one | `reference/architecture-proposal.md` |
| Where the assembly boundary goes and what it costs; copying the skeleton | `reference/sim-presentation-split.md` |
| A non-negotiable that has to become a test | `reference/invariants.md` |
| Choosing what to build first; what Done means; the loop after they play it | `reference/first-interaction.md` |
| Generating the boards, the art bible, the anchor image | skill `codex-visual` |
| Booting straight into a moment, journey tests, a feel complaint turned into a test | skill `unity-play-harness` |
| What a frame costs, and whether a change actually helped | skill `unity-profiling` |
| Creating the project, editor pinning, `.meta`/LFS, asmdef mechanics | skill `unity-new-project` |
| Type sizes, contrast and HUD layout at the brief's viewing distance | skill `unity-game-ui` |
| Verifying a change in the running game; reading a screenshot the agent took | skill `unity-debug` |
| Download size and heap ceilings as day-one budgets | skill `unity-web-release` |

---

## Discipline

- **Five questions, then write.** A sixth is the brief avoiding its first draft. Ask one at a time;
  a numbered list of five comes back as five one-word answers.
- **No number, no invariant.** A non-negotiable without a number is a preference. Find the number,
  or move the line to the visual direction, or drop it.
- **Pictures before code, and the human says yes to the picture.** Not to a description of the
  picture, and not to a recommendation the agent argued for.
- **Derive, never prefer.** Every decision in the proposal names the constraint that forced it and
  what it rules out. A decision with no constraint behind it belongs in the open question.
- **The rules assembly never imports UnityEngine.** Not "just for `Mathf`". The first import is the
  end of the test lane that made the split worth having.
- **One open question, with a default.** Three questions is an unfinished proposal handed back as
  homework, and work stops on all three.
- **Build one interaction, then let them play it.** Not two, not a menu around one.
- **One change per round.** Two changes and the next reaction is unattributable, in the loop where
  attribution is worth the most.
- **Numbers, one screenshot, one question.** Anything longer asks the human to do the reading the
  agent was supposed to do.
- **The judgement of feel stays with the human.** The agent reports what it measured over what
  sample; "it feels better" is not the agent's line.
- **Any multi-agent critique runs only when the user has explicitly asked for multi-agent
  orchestration.**

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Creating the project, editor pinning, version control, asmdef mechanics, packages | `unity-new-project` |
| Generating art, the art bible, the anchor image, sprite sheets | `codex-visual` |
| Making the game drivable and readable by an agent; journeys; a feel complaint turned into a test | `unity-play-harness` |
| What a frame costs, counters, before/after windows | `unity-profiling` |
| Verifying a change in the running game, screenshots, trusting a harness | `unity-debug` |
| Type sizes, contrast ratios in practice, HUD layout | `unity-game-ui` |
| Download size, heap ceilings, browser headers | `unity-web-release` |
| Collisions, agents that will not move, post-processing | `unity-physics-3d` · `unity-navigation` · `unity-render-urp` |
| Building the whole game from the proposal | Every other skill in this plugin |
