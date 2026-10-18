# A timing press: grading when the player pressed, on a device with latency and coarse timestamps

> Part of the `unity-input` skill. For games that grade **when** a press happened (strike timing,
> rhythm, a quick-time window) on an input device that reports late and coarsely: a sensor with
> about 90 ms of capture latency and timestamps quantised to about 43 ms, or anything else that is
> not a keyboard. Worked setting: a tennis game where a timed press with a direction is the whole
> input, graded against a 120 Hz simulation. The sim thread and its clock are
> `unity-gameplay` → `reference/sim-host-and-clock.md` (`resources/SimClock.cs`).

## 1. Every press carries two times

| Field | Meaning | Where it comes from |
|---|---|---|
| `pressUs` | When the player actually pressed, in match time | The device's own timestamp (the moment the edge happened, back-dated inside the device's batch), converted to match time |
| `ingestTick` | The simulation tick at which the press arrived | Stamped by the sim when it drains the command queue |

The judgement uses `pressUs`; the simulation can only act on it from `ingestTick`. A replay records
both, and injects each press at its recorded tick, so a replay reproduces the match exactly.
Keyboard and touch presses use `Time.unscaledTimeAsDouble` as their timestamp and go through the
same conversion.

**Converting a timestamp to match time across pauses:** subtract only the pauses that **ended
before** that timestamp. The first version subtracted the total pause time, so a press stamped
before a pause and converted after it read early by the length of the pause. `SimClock.ExternalToMatchUs`
does this, and pins a stamp inside a pause to the pause's start.

## 2. The latency model, per seat and per output path

| Latency | Default | Measured by |
|---|---|---|
| Capture: the press happens → the simulation receives it (capture, detection, debounce) | 90 ms | A sync page |
| Display: the frame is produced → the player sees it (phone screen, TV over HDMI, wireless casting) | 30 ms | The same page, one profile per output path |

The sync page: a ball bounces on a 0.8 s beat with a flash and a click; the player presses along 16
times. The median offset is stored, the distribution is shown in quantum-wide bins, and the result
is accepted only if the median absolute deviation is ≤ 25 ms; otherwise the player redoes it.

Measure the device's own timestamp jitter against an ideal "quantum number × quantum length"
clock first. If p95 jitter exceeds 10 ms, rebuild timestamps from the quantum count with a slow
linear fit to the wall clock, inside the device layer, before any game logic sees them.

## 3. Grading windows: no narrower than the device can resolve

Windows are relative to the ideal press moment, in ms; negative is early. Each band is about one
timestamp quantum wider than the one inside it.

| Band | Easy | Normal | Hard |
|---|---|---|---|
| PERFECT | ±64 (1.5 quanta) | ±45 | ±45 |
| GREAT | ±120 | ±90 | ±85 |
| GOOD | ±190 | ±150 | ±130 |
| Early / late | −300 / +240 | −240 / +200 | −240 / +170 |
| Too early (early side only) | −420 | −380 | −340 |
| Reaction floor (opponent's strike → ideal press) | 1.5 s | 1.0 s | 0.75 s |

- **PERFECT is never narrower than one quantum** (here ±45 ms against 42.7 ms). Narrower, and the
  device's resolution decides the grade, not the player. A table test asserts it for every
  difficulty, and asserts every reaction floor ≥ 0.75 s and Easy ≥ 1.5 s.
- **Difficulty never comes from shrinking windows or the floor below these.** It comes from pace,
  placement and the opponent.
- A press before the window opens is refused with its error ("wait for it") and the player may
  press again; the **first valid press inside the window locks the stroke**, later ones are
  refused. A press when it is not your ball is refused too.
- Grades map to a quality (1.0, 0.8, 0.6, 0.35 early or late, 0.1 too early) that the simulation
  turns into pace, placement and scatter. A miss is a real miss, not a scripted one.
- "Who pressed first" cannot be a mechanic: two presses in one quantum have no order.

## 4. Where the ideal press goes: two cue schemes, and the one players chose

Capture latency means a late press is only known 90 ms after it happened. The ideal press has to
sit where every press inside the late window still arrives before the simulation must commit.

| | **A: press, then swing** | **B: dwell** |
|---|---|---|
| Ideal press | contact − (capture latency + late window + 1 tick): about 0.29 s before contact on Normal (0.34 Easy, 0.27 Hard) | contact + display latency |
| What the player sees | The cue ring closes at the ideal press; the racket meets the ball about 0.3 s later | The ball waits on the racket (up to 0.20 s) until the press arrives |
| A late press | Arrives before contact; the swing is rushed and the quality lower, but it connects | Arrives at press + 90 ms; past the dwell cap it is a whiff: **the late window is truncated** |

Balance grid, Normal difficulty, simulated human against a bot:

| Simulated timing σ | A win rate | B win rate | B whiffs per match |
|---|---|---|---|
| 50 ms (skilled) | 80% | 87% | 0.6 |
| 90 ms (typical) | 60% | 13% | 3.4 |
| 140 ms (beginner) | 13% | 3% | 3.7 |

B scored better for skilled players and punished everyone else. Both were built into the greybox
and the user played both before choosing: **A was chosen.** B stays in the simulation for tests and
balance comparison only. A press-then-swing delay of about 0.3 s matches the real decide-to-strike
time in tennis, and it is the convention of button-press tennis games. Bots have no
capture latency and always use A's placement.

Rejected as a third option: strike at contact and correct the direction afterwards. The player
then always sees contact before the input is known, which brings back the misses and pops the
prior prototype had.

## 5. Cues that are always early enough

All cues appear the moment the opponent strikes, so they always precede the floor: a ring under
the receiver, a marker on the predicted first bounce, a timing ring that closes on the ideal
press, and a timing bar whose PERFECT band is drawn one quantum wide. Draw them on the render
clock, which must not be clamped to the snapshot (`unity-gameplay` →
`reference/sim-host-and-clock.md`).

## 6. Grouping presses per player, not per sensor

When several sensors fire in the same quantum, a group passes only one (the strongest) and holds
the rest until released. **Group by player**: one contact bridging two of the same player's
sensors becomes one press, and two players never mask each other. One group per sensor is for
chords, where two simultaneous presses are the input; in a game with no chords it only hands the
simulation two presses with no order between them.

Keyboard and touch bypass the device's grouping. Apply the same rule where they enter (one press
per seat per quantum) so tests behave like the hardware.

## 7. The development keyboard drives the real signal path

In the Editor a key does not inject a press; it switches on the synthetic signal for that sensor,
and the press travels the whole capture, detection, debounce and grouping path. Latency measured
in the Editor is then the device's latency, and a timing bug in that path shows up at a desk, not
only with the hardware. A `ForceDirect` switch sends raw edges instead, for comparing the two.

## Checklist

- [ ] Every press carries a device timestamp and an ingest tick; replays inject at the recorded tick
- [ ] Timestamp conversion subtracts only earlier pauses; a test presses, pauses, then converts
- [ ] Latency per seat and per output path, from a sync page with an MAD acceptance gate
- [ ] PERFECT ≥ one quantum and reaction floors asserted by a table test
- [ ] Ideal press placed so the whole late window arrives before the commit point
- [ ] Grouping per player; the same rule applied to keyboard and touch
- [ ] Cues appear at the opponent's strike and are drawn on the unclamped render clock
