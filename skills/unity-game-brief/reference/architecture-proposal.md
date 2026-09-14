# Deriving the architecture from the constraints

> Part of the `unity-game-brief` skill. The agent proposes; the human accepts or forks it. The rule
> that makes the proposal readable is that **every decision names the constraint that forced it** —
> a decision with no constraint behind it is a preference, and preferences go in the open question.

An architecture chosen from experience arrives as a list of good practices, and the human can only
trust it or not. An architecture **derived** from the brief arrives with its reasoning attached:
disagree with the constraint and the decision falls with it. That is worth the extra column.

---

## The derivation table

Four columns. The third is the one people skip and the one that makes the table useful: what a
decision **rules out** is how a reader spots the wrong call in ten seconds.

| Constraint (from the brief) | Forced decision | Rules out | Routed to |
|---|---|---|---|
| Three physical buttons, played at 2–3 m | Three commands, no analogue input, never more than three choices at once | Aiming, cursor menus, anything hover-driven | `unity-game-ui` |
| The same seed must give the same run | Seeded generation lives in the simulation, not in `Awake` | Scene-authored levels, engine randomness in gameplay | `reference/sim-presentation-split.md` |
| The look is still moving | Simulation and presentation split; one state type crosses | Rules inside a `MonoBehaviour`; art changes that force re-tuning | `reference/sim-presentation-split.md` |
| A run is 20–40 s and repeats immediately | Restart is a new simulation object, not a scene reload | A scene per level, singletons carrying run state | `unity-new-project` |
| Hazards and pickups are spawned per run | A pool sized from the generator's own counts | Instantiate-per-frame, garbage spikes mid-run | `unity-profiling` |
| Played in a browser on a tablet | A heap budget stated as a number on day one, before content exists | Uncompressed textures, unbounded pools, streaming everything | `unity-web-release` |
| Lanes are 1.3 units apart and readable at distance | Lane spacing is a simulation constant; the camera derives from it | Hard-coded scene transforms, spacing tuned by eye per prefab | `reference/invariants.md` |
| Real distances beyond a few kilometres | Positions stored relative to a shifting origin | Absolute world coordinates far from zero as the source of truth | the floating-origin section below |

Eight rows is where a first proposal stops earning its length. A ninth usually means one constraint
is really two — split it in the brief instead.

---

## The proposal, six headings and a word budget

`templates/ARCHITECTURE_PROPOSAL.md` is this list as a file. The budgets are not decoration — a
proposal nobody reads is one nobody disagrees with.

| Heading | Budget | What makes it wrong |
|---|---|---|
| **Layers** | ≤4 rows | A layer owning two unrelated things; more layers than the first version has weeks |
| **What talks to what** | ≤6 arrows | An arrow whose payload cannot be named; bidirectional arrows |
| **Swappable** | ≤3 rows | "Everything is swappable" — then nothing has been decided |
| **Deliberately NOT done** | 3–6 bullets | An empty list; things nobody would have expected anyway |
| **First interaction** | 1 sentence + a Done table | A milestone instead of something playable today |
| **One open question** | exactly 1, with a default | Three questions, or a question with no default |

**The open question has a default for a reason.** The human is not always awake, and work should not
stop on a fork the agent can take provisionally. State the branch you will build, and what reversing
it costs.

---

## The swappability test: one type crosses

For each part marked swappable, write down **the types that cross its boundary**. One type: it is
swappable. "A state object, plus an enum, plus these two events, plus a config struct": it is not —
and knowing that now is worth more than the label.

The courier run passes with `RunState`: the presenter reads it, the tests assert on it, a probe
prints it, and replacing the whole presentation layer touches no simulation file. The moment a
second type crosses — the presenter reading the hazard list to decide something, say — the boundary
has quietly moved, and the next art change starts touching gameplay files again.

Check it the cheap way: the `using` lines, and whether the types named in signatures across the
boundary are countable on one hand.

---

## Condensed courier proposal

What the four-column table above collapses into, as a proposal:

- **Layers.** `Game.Sim` (rules, seeded generation, no engine references) · `Game.Presentation`
  (scene, clock, input funnel, logging) · one scene of primitives. No third layer on day one.
- **What talks to what.** Input funnel --command--> presenter; presenter --`RunCommand`--> sim;
  sim --`RunState`--> presenter; presenter --transform writes--> scene objects. Four arrows.
- **Swappable.** The presentation layer (replaceable wholesale once the look locks; `RunState`
  crosses) · the track generator (replaceable by a hand-authored track; the hazard and pickup lists
  cross).
- **Deliberately NOT done.** No physics body on the runner — the run is a distance and a lane, and a
  rigidbody would make "the same seed, the same run" untrue. No scene per level, no save system, no
  networking, no pooling until the generator's counts say it is needed.
- **First interaction.** Launch the runner down a lane and reach the gate, playable in the Editor
  with three keys standing in for the three buttons.
- **One open question.** At the gate: does the run stop, or pass through into a result screen?
  Default: pass through with a 0.5 s deceleration, which keeps the retry under two seconds.

---

## Floating origin, when real distances are in the brief

Any brief with real-world distances in it — a course in kilometres, a map at true scale, a flight —
has this decision in it whether anyone names it or not, and retrofitting it is expensive:

1. Single-precision positions lose resolution far from zero; jitter typically appears somewhere in
   the tens of kilometres, depending on the scale of the motion drawn. Confirm on your own content
   rather than assuming a number.
2. So the **simulation's** position is not a world position: it is a distance, a cell, or an offset
   from an origin the simulation owns.
3. The **presentation** layer maps that to a world position and shifts everything back toward zero
   when the player crosses a threshold.
4. The shift moves every transform and particle system at once, so it belongs in one place, and
   everything positional reads from it.
5. Anything caching an absolute world position across the shift — a trail, a camera target, a path
   result, a joint — is re-based in the same frame.
6. Physics and rendering are re-based; the simulation is not, its numbers never having left the
   safe range.
7. Another reason the split earns itself: the shift is invisible to every rule and every test.
8. If the brief's distances are small, write the decision down as **not needed, and why** — that
   line stops the question coming back every month.

---

## A multi-agent critique of the proposal

**Only run this when the user has explicitly asked for multi-agent orchestration.**

A proposal is a good critique target: short, self-contained, falsifiable. Shape: three lenses in
parallel (constraint fidelity · what it rules out · what it costs to reverse), each lens's findings
attacked by a different lens, then one synthesis pass ranking by impact ÷ effort.

Give every agent the same brief — the constraint list verbatim, the proposal, and the rule that
**a finding must name the constraint it violates or the reversal it makes expensive**. "Consider an
event bus" is a platitude and gets refuted; default the challenger to refute. The full method,
output schema included: `unity-game-ui` → `reference/ui-review-workflow.md`.

Then verify the survivors yourself against the brief. The panel produces hypotheses, not decisions,
and the proposal still reaches the human with exactly one open question.
