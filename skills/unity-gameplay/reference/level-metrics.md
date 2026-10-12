# Level metrics — every level number is derived from a controller number

> Part of the `unity-gameplay` skill. The formulas that turn apex height, time to apex and run
> speed into the widest gap, the highest ledge, the tallest step and the narrowest door a level
> may contain; a worked table for the side run; and the check that holds a level to it.

A level and a controller are one design written twice. Written independently they disagree, and
the disagreement surfaces as "this jump feels unfair" three weeks after the room was built. So
the controller numbers come first, the level numbers are computed from them, and a script fails
the build when a level number leaves reach.

## 1. Design the jump from what the player sees

Players see how **high** the runner goes and how **long** it takes. They do not see gravity. So
decide the two visible numbers and derive the two the motor needs:

```
gravity        g  = 2·H / T²          H  apex height, units
jump velocity  v0 = 2·H / T           T  time to apex, seconds
```

Going the other way, for a motor that already exists:

```
apex height    H  = v0² / (2·g)
time to apex   T  = v0 / g
```

Starting values that read as responsive rather than floaty: `T` between 0.30 and 0.45 s, `H`
between 1.5 and 2.5 times the character's height in a side view and 0.5 to 0.7 times in a 3D
third-person view, where the camera makes height look larger than it is.

**The project's gravity setting is not the jump's gravity.** `-9.81` gives a 3-unit apex a time
to apex of 0.78 s, which reads as the moon. A character motor carries its own gravity — a field
on the motor, or `Rigidbody2D.gravityScale = g / 9.81` — and leaves the project value for
everything that is not the player.

## 2. The fall is a second gravity

Falling faster than rising is what makes a jump feel weighted. Multiply gravity by `m` once
vertical speed turns negative (1.5 to 2.0), and clamp fall speed so a long drop stays readable:

```
fall time from the apex to a landing R above take-off     t_down = √( 2·(H − R) / (m·g) )
air time to that landing                                  t_air  = T + t_down
with a clamp v_max: time to reach it is v_max/(m·g); beyond that distance, the rest falls at v_max
```

`R` is negative for a landing below take-off. `R > H` has no solution: the ledge is above the apex.

## 3. Reach

```
widest gap to a landing R above take-off     D(R) = S · ( t_air(R) + t_coyote )
```

`S` is the horizontal speed held through the jump; `t_coyote` is coyote time, which lets the
take-off happen that long after the edge. Three corrections decide whether the number is true:

- **The fixed step moves the apex.** A motor that updates velocity and then position — which is
  what `Rigidbody2D`, `Rigidbody` and most hand-written motors do — peaks `v0·dt/2` **below**
  `H`. At `v0 = 15`, `dt = 0.02` that is 0.15 units: a ledge at exactly `H` is unreachable. A
  motor that moves and then updates velocity overshoots by the same amount. The script applies
  the correction (`--integrator`, `--fixed-dt`); `jump_report.py` shows which one the game has.
  A `CharacterController` moved by the mean of the velocities before and after gravity, as
  `unity-3d-controller` does, lands on `H` exactly: read its table with `--integrator exact`.
- **Air control below full speed shortens every gap.** `S` is the speed actually held in the
  air. If acceleration in the air is lower than on the ground and the jump starts from rest, use
  the speed reached, not the top speed.
- **A gap is measured edge to edge; reach is measured centre to centre.** A box-footed runner can
  overhang each edge by up to half its width, which is free margin. Do not spend it.

A level uses **90% of reach** as its ordinary maximum (`--margin 0.9`). Between 90% and 100% is
`tight`: allowed for a deliberate challenge, never for the main path. Above 100% is a level bug.

## 4. The worked table — side run

The runner: apex 3 units in 0.4 s, run speed 8 units/s, fall multiplier 1.5, fixed step 0.02,
level unit 1 tile.

```bash
python3 scripts/level_metrics.py --apex 3 --time-to-apex 0.4 --run-speed 8 \
    --fall-multiplier 1.5 --indent 2
```

Derived: gravity 37.5, jump velocity 15, apex on the fixed step **2.85** (analytic 3.0), fall
gravity 56.25, air time on level ground 0.718 s.

| Landing relative to take-off | Air time | Widest gap | Usable (90%) | In whole tiles |
|---|---|---|---|---|
| 3 below | 0.856 s | 6.85 | 6.16 | 6 |
| 2 below | 0.815 s | 6.52 | 5.87 | 5 |
| 1 below | 0.770 s | 6.16 | 5.54 | 5 |
| level | 0.718 s | 5.75 | 5.17 | 5 |
| 1 above | 0.656 s | 5.25 | 4.73 | 4 |
| 2 above | 0.574 s | 4.59 | 4.13 | 4 |
| 3 above | — | — | — | unreachable: apex is 2.85 |

Three things the table says that the constants do not: the "3-unit jump" clears a 2-tile ledge
and not a 3-tile one; a gap of 5 is the main-path maximum on level ground and one tile less when
climbing; and adding 0.1 s of coyote time widens every row by 0.8 units (`--coyote 0.1`) — which
is a level-design change, so decide coyote time before the rooms are drawn.

## 5. Steps, doors, corridors and ceilings

These come from the body, not the jump. `W` is the collider width (twice the radius for a
capsule), `B` its height.

| Level number | Derived as | Why |
|---|---|---|
| Tallest walked step | the motor's step height; `CharacterController.stepOffset` in 3D (default 0.3) | A step is crossed without a jump. Anything taller is a ledge and belongs in the reach table |
| Door / opening width | at least `1.5·W`; `W` itself is the hard floor | At exactly `W` the body fits only when perfectly centred |
| Corridor width | at least `2·W`; in third person, at least the camera's follow distance | Two bodies pass; the camera has somewhere to be |
| Landing platform | at least `2·W` long | One body width to land on, one to stop in |
| Ceiling to walk under | at least `1.1·B` | Head clearance |
| Ceiling for a full jump | at least `B + H` | Below this the head ends the jump early and **every gap under that ceiling is shorter than the table says** |
| Slope | at or below the motor's limit; `CharacterController.slopeLimit` in 3D (default 45°) | Above it the body slides or stops |

3D greybox defaults for a 1.8-unit capsule of radius 0.4 (`W` 0.8), behind-the-character camera
at 4 units: step 0.3, door 1.2 wide by 2.2 high, corridor 4.0, ceiling 3.0. Real-world
dimensions (a 0.9 m door, a 1.2 m corridor) are too tight once a camera sits behind the
character — build to the camera, then check with the numbers.
The metrics sheet and the room built from these numbers: `unity-3d-level` →
`reference/greybox.md`. How the capsule meets steps and slopes: `unity-3d-controller` →
`reference/grounding-and-slopes.md`.

On a `CharacterController`, keep `skinWidth` near 10% of `radius`, and keep `stepOffset` well
under the jump apex — a step offset taller than the apex makes the jump pointless.

```bash
python3 scripts/level_metrics.py --apex 1.2 --time-to-apex 0.35 --run-speed 5 \
    --integrator exact --body-width 0.8 --body-height 1.8 --step-offset 0.3 \
    --step 0.25 --door 1.2 --ceiling 3.0
```

## 6. Checking a level number against reach

Every number in a room is one of five kinds; pass each to the script:

| Flag | Held to | Failing verdict |
|---|---|---|
| `--height R` | the apex (fixed-step) | `unreachable` |
| `--gap D` (with `--height R` for a gap to a higher or lower landing) | `D(R)` | `unreachable` |
| `--step H` | `--step-offset`; without one, the apex | `blocks-walking` · `unreachable` |
| `--door W` | `--body-width` | `too-narrow` |
| `--ceiling H` | `--body-height`, then `B + H` | `too-narrow`; `clips-jump` is reported and does not fail |

Exit 0 when every number is inside reach, 1 when one is outside (`--strict` also fails `tight`),
2 on a usage error. One JSON object on stdout carries `derived`, `reach`, `clearance`, `checks`
and `verdict`, so a level tool can loop over a room's numbers:

```bash
# Every gap in the side run, one per line as "gap rise"; stop at the first one out of reach.
while read -r gap rise; do
  python3 scripts/level_metrics.py --apex 3 --time-to-apex 0.4 --run-speed 8 \
      --fall-multiplier 1.5 --gap "$gap" --height "$rise" > /dev/null \
    || { echo "out of reach: gap $gap to a landing $rise up"; break; }
done < gaps.txt
```

Tile levels make the list cheap to produce: a gap is a run of empty cells in the ground row, a
rise is the difference between the two ground heights either side of it. In a greybox scene,
measure between collider bounds, not between pivots.

## 7. Close the loop: measure what the game does

The table is a prediction. The game's own numbers come from a journey that performs the jump
and records it — `unity-play-harness` → `reference/journeys.md` — then:

```bash
python3 scripts/jump_report.py "$JOURNEY_OUT/ledge-drop/timeline.jsonl" \
    --grounded-key grounded --apex 2.85 --air-time 0.718
```

Register the flag the report cuts arcs on, next to the player registration:

```csharp
GameProbe.Register("grounded", () => _motor.Grounded);
```

| The report says | The cause is usually |
|---|---|
| Apex low by about `v0·dt/2` | Nothing: that is the fixed step. Pass the fixed-step apex, not the analytic one |
| Apex low by more | Linear damping on the body; a variable-height jump cutting velocity because the scripted driver released early; the jump applied a step late |
| Apex high | Jump velocity added to a non-zero upward velocity (a slope, a moving platform); position-then-velocity integration |
| Air time long, apex right | The fall multiplier is not applied; fall speed clamped lower than designed |
| Air time short, apex right | The ground check reports grounded early — its cast distance is longer than the skin |
| No arc found | The driver never pressed jump, or `pos` is missing because the player was never registered with the probe |

Air time resolves no finer than one sample interval, and the report allows for that. Run the
journey at the frame rate the game ships at. Without `--grounded-key` arcs are inferred from
height holding still, which reads a slope as flight — register the flag.

When the measured numbers and the designed ones agree, write them into
`templates/GAMEPLAY_RECIPE.md`. From then on a change to the jump is a change to that row, and
the reach check is re-run over every room.

## Lane and cell games have metrics too

- **Lane run.** Three lanes 1.3 units apart; a lane change takes `t_lane` seconds. A hazard
  must be readable for at least `t_lane` plus a 0.25 s reaction allowance, so the minimum sight
  distance is `forward speed × (t_lane + 0.25)`. At 12 units/s and a 0.15 s change that is 4.8
  units: no hazard spawns closer than that to the runner, and consecutive hazards that force
  opposite lane changes are at least that far apart.
- **Cells.** Reach is a count: movement range in cells per turn, and the push rule (one pickup,
  one cell, never into an occupied cell). The level check is solvability — a breadth-first
  search over board states from the start to "every pickup on a gate cell" — not a distance.
