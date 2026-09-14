# Invariants: requirements a test can hold

> Part of the `unity-game-brief` skill. A non-negotiable that cannot be checked is a mood. This file
> is the six shapes a checkable one comes in, where its number comes from, and how it keeps its
> identity from the brief all the way into a failing test's name.

The rewrite is mechanical once you know the shapes. Someone says "you should always have a way
out"; the shape is **reachable**; the sentence becomes "every hazard row leaves at least one of the
three lanes open"; the ID is INV-5; the test is `INV5_EveryRowLeavesALane`; and the day it breaks,
the failure names the brief line that it broke.

---

## The six shapes

### 1 · Ready together

*A set of things must exist in the same pass, before anything is drawn or moved.*

Half-built worlds are the most common first-version bug and the hardest to see, because the missing
member usually arrives a frame later and the screenshot looks fine. Write the **set**, not a flag.

- Courier: the lane mesh, its collider, the hazard row and the pickups all exist before the runner
  is drawn for the first time.
- In code: one construction pass that ends with a single readiness flag, checked before spawning.
  `resources/Sim/RunSimulation.cs` sets `TrackReady` in its constructor, and the presenter refuses
  to spawn without it.
- Under test: `INV1_TrackIsReadyBeforeFirstTick`. As a live check, it is a readiness set on a probe
  and a wait-until with a timeout that names the missing members: `unity-play-harness`.

### 2 · Never

*A state the game must never be in.*

The strongest shape, because it is checked continuously rather than at a moment. Keep it physical
and cheap: a position, a count, a phase.

- Courier: the runner is never outside lanes 0–2; it is never inside a hazard's volume.
- In code: the clamp lives in exactly one place — `Shift()` drops an out-of-range move — so there is
  one line to read when it breaks.
- Under test: `INV2_LaneNeverLeavesTrack` pushes far harder against both edges than a player could.
  Over a whole played run it becomes a journey assertion: `unity-play-harness`.

### 3 · Always within

*A number that must stay inside a band.*

Bands, not maximums. A one-sided bound hides the failure at the other end: a run that is too short
is as wrong as one that is too long, and only the band catches both.

- Courier: a run is 20–40 s from launch to gate. The runner's speed at the gate is at or below the
  gate's entry speed.
- In code: the band's two numbers are constants in the test, not in the game, so the game cannot
  quietly satisfy them by definition.
- Under test: `INV3_LaunchReachesGateWithinBudget`, printing median and worst over five seeds.

### 4 · Reachable

*From any reachable state, a way forward exists.*

The shape that catches generated content. It is cheap to assert over a thousand seeds and expensive
to discover from a bug report that says "sometimes it's impossible".

- Courier: every hazard row leaves at least one of the three lanes open.
- In code: make it **structural**, not repaired. `TrackGen` picks the open lane first and blocks
  only among the others, so the property holds by construction and the test confirms the
  construction rather than patrolling the output.
- Under test: `INV5_EveryRowLeavesALane` over seeds 1–1000.

### 5 · Ordering

*B never happens before A.*

Half of all "it flickers on load" reports are an ordering invariant nobody wrote down.

- Courier: the phase order is Idle → Launched → (AtGate | Crashed), and no phase is skipped or
  revisited. The track is ready before the first tick.
- In code: transitions go through one method. A phase assigned from two places is an ordering
  invariant with no owner.
- Under test: a state sequence recorded over a run and checked for monotonicity — as a played
  journey, `unity-play-harness`.

### 6 · Budget

*A cost that must not be exceeded.*

The shape that is worth writing down before there is anything to measure, because its value is set
by the brief's device, not by what the game currently does.

- Courier: the whole run holds its frame budget on the tablet, and the browser build stays under the
  download and heap numbers the brief names.
- In code: nothing. Budgets are not enforced by the game, they are measured against it.
- Under test: a fixed window of frames, median and p95 and worst, compared across a change —
  `unity-profiling`. The download and heap ceilings for a browser build are `unity-web-release`.

---

## Where the number comes from

Every invariant needs a number, and it has to come from somewhere defensible. In order of
preference:

1. **The brief's device line.** Viewing distance, aspect and input hardware give type sizes, minimum
   silhouette size and the number of simultaneous choices. These are the strongest numbers because
   nobody has to agree to them — they are physical.
2. **The experience sentence.** "Before the sentry closes the gate" contains a duration; ask what it
   is, in seconds, and the answer is the band.
3. **A measurement of the current build.** Legitimate for budgets: today's median is the baseline, and
   the invariant is "no worse than this". Say that it is a baseline, so nobody later reads it as a
   target that was chosen.
4. **A default, marked as one.** Better than no number: `3:1` contrast, `20–40 s`, `90` frames in a
   measurement window. Write it as a default so the first person who disagrees knows it is theirs to
   change.

**Never a number with no source.** "Under 100 ms" that nobody can trace is the line that gets argued
about for a week and then deleted.

---

## IDs that survive

The ID is the only thing connecting a sentence in a brief to a red line in a test report. Give it
one and never renumber it:

```
GAME_BRIEF.md          INV-3   A run is 20-40 s from launch to the gate.
RunSimulationTests.cs  INV3_LaunchReachesGateWithinBudget
Test output            INV-3 median=27.72s worst=27.73s budget=20-40s
A journey assertion    INV-3 window: t(AtGate) - t(Launched)
```

Four rules:

- **Numbers are never reused.** A deleted invariant leaves a hole with a one-line note saying when
  it went and why. Reusing INV-4 for something new makes every old log line wrong.
- **The ID goes in the test name**, so a failing run names the brief line without anyone looking it
  up.
- **The test prints the number it asserted on.** A green tick says a test passed; `median=27.68s
  budget=20-40s` says why, and keeps saying it after the next change.
- **Inherited invariants are listed by ID in a feature's brief**, not restated. Restating them is
  how two versions of the same rule end up disagreeing.

A brief with three to six invariants is healthy. Fewer and the first version has nothing to hold it
straight; more and they are being used as a feature list in disguise.
