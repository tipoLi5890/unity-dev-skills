# Jump maths — the numbers the controller is built from

> Part of the `unity-2d-controller` skill. How `PlatformerController2D` turns two numbers a
> player can see into the two a motor needs, what a fall multiplier and a jump cut do to them,
> and why the jump the game performs is not the one the formula describes. This file is the
> controller's side of the arithmetic; the reach tables, the level check and the measuring
> script belong to `unity-gameplay` → `reference/level-metrics.md`.

## 1. Author height and time, derive the rest

A player sees how high the runner goes and how long it takes. Nobody sees gravity. The
controller therefore stores `apexHeight` (H) and `timeToApex` (T) and computes:

```
gravity        g  = 2·H / T²
jump velocity  v0 = 2·H / T
```

| Side-run start | H 3 units · T 0.4 s | → g 37.5 units/s² · v0 15 units/s |
|---|---|---|

Tune by moving H or T and nothing else. Halving T at the same H quadruples gravity and doubles
jump velocity: the jump covers the same height in half the time and reads as snappy. Raising H
at the same T makes it both higher and faster. Editing gravity directly changes height and
time together, which is why a controller that exposes gravity is hard to tune.

**The project's gravity is not the jump's.** `Physics2D.gravity` at −9.81 gives a 3-unit apex a
time to apex of 0.78 s. The kinematic motor never reads it. A dynamic-body character sets
`Rigidbody2D.gravityScale = g / 9.81` (3.82 here) on its own body and leaves the project value
for crates.

## 2. Rise and fall are two gravities

```
rising    v.y > 0     g
falling   v.y < 0     g · fallMultiplier        (1.5 → 56.25)
capped                v.y >= −maxFallSpeed      (20)
```

The fall multiplier shortens the second half of the arc: from the 2.85 apex back to take-off
height takes 0.32 s against 0.40 s up. It does not change the apex. It **does** shorten air time
and so every gap — the reach table takes it as `--fall-multiplier`.

The cap matters on long drops only: at 56.25 units/s² the runner reaches 20 units/s after 0.36 s
and 3.6 units of fall. Below that, the cap has no effect on reach; above it, a drop is slower
than the uncapped formula says and the runner travels further sideways.

## 3. What the cut and the hang do to the arc

| Tunable | Changes the apex | Changes air time | Changes reach |
|---|---|---|---|
| `fallMultiplier` | no | yes, shorter | yes |
| `maxFallSpeed` | no | on long drops | on long drops |
| `jumpCutMultiplier` | only on a released jump: the minimum hop | yes | the minimum, not the maximum |
| `apexHangSpeed` · `apexHangGravity` | **yes, higher** | yes, longer | yes |
| `coyoteTime` | no | no | yes: `runSpeed × coyoteTime` on every gap |
| `extraJumps` | yes: a second apex from wherever the first is spent | yes | yes |
| `airAccel` below `groundAccel` | no | no | yes, for a jump that starts below run speed |

A level is built against the **held** jump with the hang as configured. Any change to a row
marked "yes" under reach is a level-design change: re-run the table.

## 4. From controller numbers to the reach table

The same four numbers, passed across:

```bash
python3 scripts/level_metrics.py --apex 3 --time-to-apex 0.4 --run-speed 8 \
    --fall-multiplier 1.5 --max-fall-speed 20 --coyote 0.1 --fixed-dt 0.02 \
    --gap 5 --height 1                     # exit 1 when the gap is out of reach
```

The script is `unity-gameplay` → `scripts/level_metrics.py`; the flags, the table it prints and
the 90% margin are in `unity-gameplay` → `reference/level-metrics.md`. Use the default
`--integrator semi-implicit` for this controller (§5). Run it once per ability set an
exploration platformer can hold — with and without the double jump, with and without the dash
(a 3-unit level dash adds 3 units to a gap it is used across).

## 5. Why the simulated apex is not H

The formula describes a continuous arc. The controller advances in steps of `dt`, and what a
step does first decides which side of H the apex lands on.

| Integrator | A step is | Simulated apex | At v0 15, dt 0.02 |
|---|---|---|---|
| Semi-implicit — this controller, `Rigidbody2D`, most hand-written motors | velocity −= g·dt, then position += velocity·dt | `H − v0·dt/2` | **2.85** |
| Explicit | position += velocity·dt, then velocity −= g·dt | `H + v0·dt/2` | 3.15 |
| Exact | position += velocity·dt − ½·g·dt², then velocity −= g·dt | `H` | 3.00 |

Three consequences:

- **A ledge at exactly H is unreachable.** Build to the simulated apex, and the 90% margin
  under it.
- **The apex moves with the fixed step.** At `dt` 1/60 it is 2.875; at 0.02, 2.85; at 1/30,
  2.75. A project that changes `Time.fixedDeltaTime` changes its jump — a reason to pin the
  step early and to assert the apex in a test.
- **The take-off step counts.** This controller applies gravity on the step the jump starts.
  One that sets velocity and skips gravity for that step peaks `v0·dt` higher (3.15, the
  explicit row); one that applies the jump a step late peaks the same but leaves 0.02 s later.

To make the simulated apex equal H exactly, either use the exact row (replace the two lines in
the controller's vertical block) or raise the authored H by `v0·dt/2`. Most games keep the
semi-implicit row and build levels to the number it produces: it is what every body in the
engine does, so a crate and the runner fall alike.

## 6. Measure the jump the game performs

`templates/PlatformerJourneyTest.cs` performs a held jump on level rooftop and asserts the apex
within 0.05 of `apexHeight − JumpVelocity · fixedDeltaTime / 2`. It registers the flag the
measuring script cuts arcs on:

```csharp
GameProbe.SetPlayerVelocity(() => run.transform, () => (Vector3)run.Velocity);
GameProbe.Register("grounded", () => run.Grounded);
```

```bash
python3 scripts/jump_report.py "$JOURNEY_OUT/side-run-jump/timeline.jsonl" \
    --grounded-key grounded --apex 2.85 --air-time 0.72
```

The script is `unity-gameplay` → `scripts/jump_report.py`. Pass it the simulated apex, not H. The
table of what each kind of disagreement means is in `unity-gameplay` →
`reference/level-metrics.md` §7; the three that come from this controller:

| The report says | Look at |
|---|---|
| Apex near a quarter of the designed one | The driver tapped: the cut fired on the take-off step. Use `Hold`, release after landing |
| Apex high by `v0·dt` | Gravity is being skipped on the take-off step, or the jump is added to an upward velocity (a lift: `inheritPlatformVelocity`) |
| Air time long, apex right | `fallMultiplier` is 1, or `apexHangSpeed` is above 0 |

## 7. Horizontal numbers

```
time to top speed   = runSpeed / accel          8 / 80  = 0.10 s on the ground, 8 / 40 = 0.20 s in the air
stopping distance   = runSpeed² / (2 · decel)   64 / 160 = 0.4 units
turn-round time     = 2 · runSpeed / accel      0.2 s on the ground
```

Above 0.15 s to top speed a runner reads as heavy; above 0.5 units of stopping distance it
reads as ice, and a landing platform must grow to match (two body widths plus the stopping
distance). `airAccel` at half `groundAccel` lets a jump be corrected and not reversed: a
standing jump reaches full speed 0.2 s in, having covered 0.8 units, so the widest gap from a
standstill is 0.8 units shorter than the table's.

## Where each need is answered

| Need | Answer |
|---|---|
| The reach table, margins, steps, doors and ceilings | `unity-gameplay` → `reference/level-metrics.md` |
| Recording a journey, the timeline the report reads | `unity-play-harness` → `reference/journeys.md` |
| The tunables themselves and what each rule does | `reference/platformer.md` |
| The fixed step, simulation mode, interpolation | `unity-physics-2d` → `reference/bodies-and-simulation.md` |
