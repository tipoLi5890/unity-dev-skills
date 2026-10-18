# Timing sports — a rally decided by when the player presses

> Part of the `unity-gameplay` skill. Racket and bat games where characters move themselves and
> the player's input is **when** (and which way) to strike: tennis, badminton, table tennis,
> pickleball, a batting game. Worked setting: a 3D tennis game with a deterministic 120 Hz rally
> simulation, bots, split-screen for two, and a library of purchased motion-capture clips. The
> input device has about 90 ms of latency and timestamps quantised to about 43 ms.

## 0. Measure the animation library before you set a single simulation number

This is the lesson that arrived last and should have come first. The simulation chose its numbers
from the sport (a player's sprint, where a racket meets the ball); the clips had their own, and
every gap between the two became IK, warping and pops in the presentation.

| Quantity | Simulation said | The clips could do | What the gap cost |
|---|---|---|---|
| Top run speed | 7.0 m/s (p95 of frames; 15–22% of frames at 4.5 m/s or more) | Fastest run loop 2.7 m/s | Run played at 1.8× and strides warped 1.5×; legs over-long, hips low; about 40% of the remaining single-frame pops were in the sprint |
| Forehand contact, relative to the body | 0.75 m to the side, 0.30 m forward | About 0.93 m to the side, −0.07 to 0.09 m forward | Racket centre a median 18.5 cm from the ball before racket IK |
| Overhead contact height | 2.60 m | 2.35 m (mean of the three smash takes) | 25 cm the arm, already straight, could not reach |
| Serve | Toss 0.35 m right, 0.50 m forward; contact 2.65 m | Contact 2.46 m, and 65 cm from the simulated toss point | Root correction pinned at its 0.35 m cap for every serve; the gate could not pass |

**The method, before the first rally is tuned:**

1. Import the clip library and, on the reference body, sample each locomotion loop's ground speed
   and each stroke's racket-bed centre at its contact frame: lateral, forward and height, measured
   from the hip's ground projection with forward along the shot.
2. Group strokes by contact height (here three classes: 0.45–0.95, 0.95–1.40, 1.40–1.85 m) and
   average each class; the simulation interpolates linearly between classes and clamps at the ends.
3. **Set the simulation from those numbers** (top speed 6.0 m/s here, contact geometry from the
   table) and scale per body (a 1.70 m character is 0.93 of the reference). Leave IK the last
   few centimetres; it is a finisher, not a bridge.
4. Put the geometry and speeds into the tuning hash in every replay header, and add tests that the
   planned contact point equals body position plus scaled geometry.
5. Gaps the library cannot close (no split-step clip, no lob clip, no run faster than 2.7 m/s)
   are asset requests or design decisions, written down, not tuning targets for IK.

How the presentation follows a simulation that is still faster than its clips (rate, stride and
orientation warping, foot lock): `unity-animation` → `reference/sim-driven-animation.md` §6.

## The constraints

| Constraint | Value | Why |
|---|---|---|
| Dimension · projection | 3D · perspective | Depth of a lob and the bounce read from a broadcast camera |
| View | Behind the near baseline, broadcast framing; split-screen halves for two players | `unity-camera` → `reference/broadcast-sports.md` |
| Movement model | Characters move themselves to the stance the simulation planned | The player's whole job is timing and direction |
| Transform owner | **The simulation.** Position, contact point and contact time are outputs of the rally sim; the animation conforms | See §1 |
| Level unit | The court's regulation dimensions | Lines, net and service boxes are drawn from the rule constants, not from a modelled venue |
| Input | One timed press with a direction (forward, back, left, right map to four shot kinds in a table the sport owns) | `unity-input` → `reference/timing-press.md` |

## 1. Contact is decided by the simulation, never by the animated racket

When the opponent strikes, the whole flight, bounces included, is known. The simulation picks the
contact point and tick, forehand or backhand, and the stance; the motion layer then schedules the
swing so its contact frame lands on that tick (measured offset 0.00 ms).

The prior prototype did it the other way: a hit was judged from where the animated racket was.
Its record: PERFECT presses that missed the ball, replays that did not reproduce, feet sliding
0.6 m. Animation is frame-rate dependent and blended; a judgement built on it inherits both.

## 2. Timing invariants, as tests

| Invariant | Value | Test |
|---|---|---|
| Reaction floor: opponent's strike → ideal press | Easy 1.5 s, Normal 1.0 s, Hard 0.75 s; never below 0.75 | Every human plan on every difficulty and cue scheme, a perfect press each time, asserts the floor |
| How the floor is kept | Contact candidates that violate it are dropped; a shot aimed at a human is slowed (more net clearance, +1 m apex, or speed × 0.82, up to six tries) until strike to second bounce ≥ floor + 0.55 s + display latency | So Easy balls are visibly slower: a hardware rule, not a bug |
| PERFECT width | Never narrower than ± one timestamp quantum (±45 ms against 42.7 ms) | Table test over all three difficulties |
| Difficulty | Comes from bots, placement and pace inside the floor, never from shrinking windows below it | |
| Faults | Scatter by timing quality is added to the **target**, then the solver flies a real shot; nets and outs happen, none are scripted | |

The press → swing → contact timing and the two cue schemes the player chose between:
`unity-input` → `reference/timing-press.md`.

## 3. A rally at full speed

No hit stop, no slow motion and no time-scale change during a rally: every one shifts the moment
the player is timing against. Impact is sold with a flash, dust, sound and a 4 cm camera kick on a smash;
slow motion and push-ins happen between points. `unity-game-feel` → `reference/hit-stop-and-time.md`.

## 4. Balance with bots, as a grid

The rules run without the Editor, so whole matches run in seconds. A grid tool plays every cell
and writes a report: here 16 cells × 40 matches (bot singles and doubles per difficulty; a
simulated human with timing σ 50, 90 and 140 ms against a bot on each difficulty; the rejected cue
scheme at the same three σ).

| Column | Reads as |
|---|---|
| Points and seconds per match, strokes per point (mean, median, p90) | Pace |
| Win rate and point rate of side 0 | Fairness, and difficulty for the simulated human |
| Whiffs and let-goes per match | Whether the timing model is punishing |
| Per-tick cost p99 / max | 0.01 ms p99, but up to 35 ms max in doubles: why the sim runs on its own thread (`reference/sim-host-and-clock.md`) |
| Shot usage and speed (mean / p90) per kind | Whether one shot dominates |
| Grade distribution | Whether PERFECT is reachable |
| **Counter matrix**: per shot kind × opponent state at the strike (deep, mid, front, pulled wide, moving > 3 m/s), the share the opponent failed to return, with n | Whether the designed counters exist |

Gates, written before tuning: **each designed counter wins by at least 10 points**, and **no shot
kind exceeds 40% usage between best-strategy bots.** The first grid did not pass: one shot kind
took 37–60% of strokes, and lobs were returned 100% of the time from every state. That is the
grid working; it says which numbers to move. For the simulated human the target was a
recognisable curve: Normal, σ 90 ms, wins about 60%; σ 140 ms on Hard wins 5%.

## 5. Order of work

1. Rules and ball as plain C# with tests (`unity-physics-3d` → `reference/own-ball-physics.md`);
   first balance grid.
2. Greybox playable with capsules: both cue schemes, a human plays both and chooses.
3. Clip library measured (§0), simulation numbers set from it.
4. Characters, then motion gates (`unity-animation` → `reference/motion-metrics.md`), then venues
   and polish.

## Who owns each need

| Need | Where |
|---|---|
| Sim thread, clock, snapshot, render tick, warmup, no-Editor tests | `reference/sim-host-and-clock.md` |
| The ball: drag, spin, bounce, net, swept contact, the shot solver | `unity-physics-3d` → `reference/own-ball-physics.md` |
| Timestamps, latency, the ideal press, cue schemes, grouping | `unity-input` → `reference/timing-press.md` |
| A graph that follows the sim; contact frame on the contact tick | `unity-animation` → `reference/sim-driven-animation.md` |
| Foot lock and racket IK | `unity-animation` → `reference/foot-lock-and-prop-ik.md` |
| Proving the motion: slide, contact, pops | `unity-animation` → `reference/motion-metrics.md` |
| One skeleton for every body, clips unchanged | `unity-rigged-character` → `reference/shared-skeleton-generic.md` |
| Venue by script; colliders exported as data | `unity-3d-level` → `reference/venue-from-scripts.md` |
| Broadcast camera, split-screen | `unity-camera` → `reference/broadcast-sports.md` |
| Impact without stopping time; a ball readable at distance | `unity-game-feel` → `reference/hit-stop-and-time.md`, `unity-game-feel` → `reference/sports-readability.md` |
| Situations straight into a rally moment; autoplay journeys | `unity-play-harness` → `reference/situations.md` |
| Frame time on the phone | `unity-profiling` |
