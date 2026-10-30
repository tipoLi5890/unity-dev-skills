---
name: unity-game-brief
description: >-
  See the game before code: idea to brief, the look, a gameplay preview,
  architecture, first build step.
---

# unity-game-brief — the spec comes last

An idea arrives as one sentence, and the expensive mistake is to answer it with a plan. A plan is
a guess about how something will feel, written in the one form nobody can react to.

> **The first hour ends with a human playing something, not reading something.**
> One page, one locked image, one derived proposal, one playable interaction — in that order,
> because each is worthless before the one above it.

## Request → where to start

| The request | Go to |
|---|---|
| "I want to make a game where…", "here's my game idea", "write the brief" | §1 |
| The look, "lock the art direction" | §2 |
| "preview it before code", see the game before it is built | §2b |
| "propose an architecture" | §3 |
| "is this ready to build", a non-negotiable to test | §4 |
| "what should we build first" | §5 |
| "new feature — where do we start" | §1's new-feature variant (`reference/experience-brief.md`) |
| Existing files, unsure where you are | §0 |

The order is not a ritual. Constants written before the look settles get re-tuned when it does; an
architecture chosen before the constraints are written is a preference nobody can argue with; a
feature list written before anyone has played is a list of guesses, each of which will be built.

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
tellable apart in black at shipping size, **perspective and movement**, and **one anchor image**.
Everything else about art is production.

Perspective and movement are constraints, never a genre label: dimension; projection (size and
pixels per unit, or FOV, distance and pitch); view axis; movement model (free, lane with width,
cell with size and layout) and who owns the transform; aspect; input devices.

Budget: 2–3 distinct boards → the human picks → at most 2 correction rounds → locked. Corrections
are one sentence, one axis: *keep [what works], change [one axis], toward [the other end], not all
the way.* A third round means the brief is wrong, not the image.

Generating the boards, the art bible and the anchor is `codex-visual` — that skill generates, this
one decides. → `reference/visual-direction.md`

## 2b. Preview before code

When the person wants to see the game before it is built, make these in order, each only after the
one before it is agreed: a **flow diagram** (screens and story beats, each node with an id) → **key
art** (§2's anchor) → **screen mockups at the target resolution** → **layout and keyframes**
(`comfyui-asset-generation`) → a **timed simulated-gameplay preview** → then §5's greybox playable. A polished image is not proof of gameplay; a preview shows
intent and timing, and its timings are constants written down, the same numbers the brief and the
invariants use.

`scripts/examples/courier_run_preview.py` turns the rules into `timeline.json` and `preview.mp4`;
`scripts/preview_compose.py` composes a timeline with its sounds; `scripts/preview_reel.py` adds
title cards and music at −16 LUFS. The compositor writes its events and a contact sheet next to the video; the reel writes its
timeline. → `reference/preview-before-code.md`

## 3. Constraints → architecture proposal

The agent proposes; the human accepts or forks it. Every row of the proposal names the constraint
that forced it, so disagreeing is cheap. For example, three physical buttons played at 2–3 m force three commands and rule out aiming;
"the same seed gives the same run" forces seeded generation inside the rules assembly; a look
still moving forces the simulation/presentation split; a browser on a tablet forces a heap budget
on day one; real distances in kilometres force a shifting origin. The full table:
`reference/architecture-proposal.md`.

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

**Ready together** (lanes, colliders, hazards and pickups before the runner is drawn) · **Never**
(outside lanes 0–2, inside a hazard) · **Always within** (a run is 20–40 s) · **Reachable** (every
hazard row leaves a lane open, over 1000 seeds) · **Ordering** (Idle → Launched → AtGate or
Crashed) · **Budget** (the frame budget on the tablet, checked, not enforced).

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

The human decides how it looks and feels, what is next, whether a number is right and whether it
is done; the agent decides and reports the implementation, the tests and how numbers are measured
(the full table: `reference/first-interaction.md`). Every hand-back is the same five lines: **numbers, the invariant they were checked against, one
screenshot with its state logged next to it, one change, and one question with the default you will
take if nobody answers.**
→ `templates/REPORT.md`

## 7. After the first interaction

Rebuild a prototype whose scoring follows its animation; port only intent. Milestones carry a ★ on
gates only the person closes. A feel question gets both options behind a runtime switch, and the
loser leaves the menus but stays in the sim. Decisions go to three places: locked (rule file,
verbatim), small (decided, reported), open (with a default). Reconcile docs with code after each
milestone. Several agents: an ownership block per brief.
→ `reference/running-the-build.md`, `templates/DECISION_LOG.md`, `templates/AGENT_BRIEF.md`

## Load what the situation needs

| The situation | Read |
|---|---|
| An idea with no page yet; a new feature on a shipping game | `reference/experience-brief.md` |
| The look is unsettled; deciding what to lock and when it is accepted | `reference/visual-direction.md` |
| Seeing the game before code: flow, mockups, a timed gameplay preview, a reel | `reference/preview-before-code.md` |
| Deriving the proposal, or critiquing one | `reference/architecture-proposal.md` |
| Where the assembly boundary goes and what it costs; copying the skeleton | `reference/sim-presentation-split.md` |
| A non-negotiable that has to become a test | `reference/invariants.md` |
| Choosing what to build first; what Done means; the loop after they play it | `reference/first-interaction.md` |
| Rebuild or port; milestones and ★ gates; a decision log; briefing several agents | `reference/running-the-build.md` |

## Discipline

- **Five questions, one at a time, then write.** A numbered list of five comes back as five
  one-word answers; a sixth question is the brief avoiding its first draft.
- **No number, no invariant** — find the number, move the line to the visual direction, or drop it.
- **The human says yes to the picture**, not to a description of it or a recommendation argued for.
- **Derive, never prefer**: a decision with no constraint behind it belongs in the open question.
- **The rules assembly never imports UnityEngine** — not "just for `Mathf`".
- **One open question, with a default.** Three is homework, and work stops on all three.
- **Build one interaction, then let them play it.** Not two, not a menu around one.
- **One change per round**, or the next reaction is unattributable.
- **Numbers, one screenshot, one question** in every hand-back.
- **The judgement of feel stays with the human**; the agent reports what it measured, over what sample.
- **Any multi-agent critique runs only when the user has explicitly asked for multi-agent
  orchestration.**

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Creating the project, editor pinning, `.meta`/LFS, asmdef mechanics, packages | `unity-new-project` |
| Generating the boards, the art bible, the anchor image, sprite sheets | `codex-visual` |
| Booting into a moment, journeys, a feel complaint turned into a test | `unity-play-harness` |
| What a frame costs; whether a change helped | `unity-profiling` |
| Verifying in the running game, screenshots, trusting a harness | `unity-debug` |
| Type sizes, contrast and HUD layout in practice | `unity-game-ui` |
| Download size, heap ceilings, browser headers | `unity-web-release` |
| Collisions · agents · post-processing | `unity-physics-3d` · `unity-navigation` · `unity-render-urp` |
| Which controller and camera skills a perspective needs | `unity-gameplay` |
| Building the whole game from the proposal | Every other skill in this plugin |
