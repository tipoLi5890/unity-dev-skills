# Seeded soak: random input you can replay to the frame

> Part of the `unity-play-harness` skill. A soak drives every situation with random but plausible
> input for minutes, checks cheap invariants every frame and records a timeline; one printed seed
> makes any red run replayable. `templates/SoakTest.cs` is the test to copy.

A journey asks one question about one moment, with input someone wrote. A soak asks what breaks
under input nobody wrote: a lane change on the frame a pickup is grabbed, a launch held across a
crash, the fortieth lap leaving one hazard behind. It is worth **whether a red run replays** (else
it is a flake generator) and **which invariants it checks** (else it only proves nothing crashed).

## The seed contract

| Rule | Why |
|---|---|
| One seed per run, printed before anything else: `[SOAK] seed=… situation=…` | A run that dies loading the scene still said what it was |
| `SOAK_SEED` pins it; unset, one fresh seed is drawn per run and printed `source=fresh` | Pinned regresses, fresh explores; both replay because both are printed |
| Inputs draw from their own `System.Random`, never `UnityEngine.Random` | One global stream: an extra draw by gameplay shifts every input after it, and the soak's draws shift the spawns |
| Each situation's stream is `(seed, id)` hashed with FNV-1a | `string.GetHashCode` is not promised stable between runs |
| Exactly two draws per decision — the action, then its hold — whatever the game did | The schedule is a function of seed and step index alone |
| The seed is in the journey id `soak-<id>-<seed>`, in `params.soakSeed`, and in every `FAIL` line | `head -1 timeline.jsonl` names the run; the `FAIL` line carries its replay command |

```
[SOAK] seed=40213 situation=hazard-lane source=env seconds=120.00 steps=6000 step=0.0200 every=1
[SOAK] FAIL seed=40213 situation=hazard-lane lap=3 step=2817 frame=9123 rule=stuck-state 'Crashed' for 4.02s, limit 4.00s | replay: SOAK_SEED=40213 SOAK_SITUATIONS=hazard-lane SOAK_SECONDS=120.00 -testFilter CourierSoak
```

> **`step` is the replay coordinate, not `frame`.** `Time.frameCount` depends on whatever ran
> before the test; the step index counts from the first lap's readiness. Steps do not advance while
> a lap waits on its readiness set, and held levels are released for the wait — so how long a
> section takes to stream cannot decide how far the runner steers.

## Input: the funnel, a weighted table, plausible holds

The soak adds `ScriptedRunInput` to the object holding the game's own `RunInputSource` and switches
the reader off; gameplay's `RunInputSource.Resolve` picks the script up on its next fixed step.
Calling `ShiftLane` directly would skip the latch and the buffer, where half the bugs live.
→ `unity-input` → `reference/reading-input.md`

| Action | Writes | Weight | Lasts |
|---|---|---|---|
| Idle | `SetMove(0)` | 3 | 0.20–1.00 s |
| SteerLeft · SteerRight | `SetMove(-1, 0)` · `SetMove(1, 0)` | 2 · 2 | 0.15–0.50 s |
| TapLaunch | `Tap(Launch)` | 2 | 0.15–0.30 s |
| HoldLaunch | `Hold(Launch)`, released by the next decision | 1 | 0.15–0.60 s |
| TapInteract | `Tap(Interact)` | 1 | 0.15–0.30 s |

- **The minimums are the plausibility.** Nothing shorter than a thumb manages, and no button pressed
  again inside the funnel's 0.12 s buffer: two presses before the first is used collapse into one
  in the latch, and presses and uses then disagree for a reason that is not a bug.
- **Pause is not in the table:** a soak that pauses spends its budget on a menu. Soak the pause
  menu as its own situation.
- **The weights model a player; they are not one.** Bias them toward what the game is about
  (steering, for a lane runner) and keep the reason next to the number.
- **A lap's parameters come from a second stream** (the starting lane), so a lap that ends early
  never shifts the input schedule.

## The run

```
[OneTimeSetUp]  one seed for the run: SOAK_SEED, or a fresh one
[SetUp]         PlayerPrefs.DeleteAll · ClearParams · GameProbe.Reset · captureDeltaTime = fixedDeltaTime
per situation   [SOAK] seed=… first · Random.InitState(stream) · load Single · attach ScriptedRunInput
lap             SetParam lane, soakSeed → Enter → WaitUntilReady → milestone lap-N
drive           decide when the hold runs out · one frame · sample · in-loop checks
terminal        state Done → next lap, same situation; the step count carries on
end             samples · cap · input landed · never-inside · lap-leak · [SOAK] PASS
```

- **One test case per situation**, through `[ValueSource]` on the `[UnityTest]`: a verdict each.
  `SOAK_SITUATIONS=hazard-lane` narrows a run to one; it is read when the test list is built, so
  an open Editor keeps the value it was launched with. Confirm the results file lists the cases.
- **Its own tier, `[Category("Soak")]`.** The everyday run leaves it out with
  `-testCategory '!Perf;!Soak'`; a soak run selects it with `-testFilter CourierSoak`. Untagged,
  every suite run would soak for minutes and wipe PlayerPrefs on the way.
- **Bounded by frames.** `SOAK_SECONDS` is game time at the pinned frame time, turned into a step
  count; a wall-clock bound would stop on a different step on a busier machine.
- **The Test Framework stops a `[UnityTest]` after 180 s of wall clock** unless the test raises it
  (`Timeout value of 180000 ms was exceeded`). The template sets `[Timeout]` to 45 minutes; confirm
  the default on your version, and size `SOAK_SECONDS` from the `wall=` of a short run.
- **Past a few minutes, `SOAK_EVERY=3`.** In-loop checks still run every frame, on a live snapshot
  when the recorder skips one; `MaxSamples` is raised from the step count, and the run asserts the
  cap was never reached.

## Invariants: cheap ones every frame, the rest over the recording

| When | Rule | Catches |
|---|---|---|
| every frame | `runner-missing` | The player transform is gone — destroyed, or never registered |
| every frame | `non-finite` | NaN or infinity in `pos` or `vel`: a normalised zero vector, a division by a zero distance |
| every frame | `undeclared-state` · `state-backwards` | A state nobody listed; a phase re-entered **inside one lap** |
| every frame | `stuck-state` | A state held past its ceiling — every state has one; the table names the short ones |
| end | samples · cap | Nothing recorded; a timeline cut off at `MaxSamples` |
| end | `input-landed` | Presses sent, and the lane never changed inside a lap: the game is not reading the script |
| end | `never-inside` | The runner inside the static lane walls — random steering finds the seams |
| end | `lap-leak` | Live pickups plus hazards at a lap's start climbing past lap 1's |

The first in-loop failure stops the soak and tags its row `fail-<rule>`: after NaN, every row is
noise. The framework adds the cheapest invariant: **an error or exception logged during the run
fails the test** (`Unhandled log message`). Never set `LogAssert.ignoreFailingMessages` in a soak.

> **Prove the gate can fail.** `SOAK_BREAK=deaf` leaves the device reader enabled, so the script
> reaches nothing and `input-landed` must go red. A soak that stays green under it is checking a
> game nobody is playing.

Then the report, over the soak's timeline:

```bash
python3 scripts/journey_report.py --after "$JOURNEY_OUT/soak-hazard-lane-40213/timeline.jsonl" \
  --no-null speed --no-null state --no-null cam \
  --together laneMesh,laneCollider --min pos.y:-0.5 --max speed:14
```

- **`--no-null speed` is the NaN check after the fact:** the probe writes a non-finite float, or
  the speed of a missing player, as `null`.
- **No `--monotonic` and no `--ready-before`.** Every lap goes back to `Idle` by design, and the
  `lap-N` rows are tagged after readiness; the per-lap order check lives in the loop.
- The report's exit codes are its own: 0 clean, 1 violations, 2 usage or parse error
  (`reference/timeline-format.md`).

## Replaying a red soak

1. **Copy the failing directory aside.** The replay writes the same `soak-<id>-<seed>` directory and
   deletes it first.
2. **Run the `replay:` part of the `FAIL` line**, on the same Editor version.
3. **Same rule, same step:** the run is deterministic. Look just before that step — a milestone and
   a windowed screenshot. → `reference/journeys.md`
4. **Another step, or green:** the inputs replayed and the game did not. Find where the runs part:

```bash
python3 - failing/timeline.jsonl replay/timeline.jsonl <<'PY'
import json, sys
def rows(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if "n" in r and not r.get("milestone"):
            out.setdefault(r["custom"].get("soakStep"), (r.get("state"), r.get("pos")))
    return out
a, b = rows(sys.argv[1]), rows(sys.argv[2])
for step in sorted(set(a) & set(b)):
    if a[step] != b[step]:
        print("parts at soakStep", step, a[step], "vs", b[step]); break
else:
    print("identical over", len(set(a) & set(b)), "steps")
PY
```

## Determinism: what the seed pins, and what it cannot

The seed pins the input; the game replays only as far as it is a function of that input. Check:

- **Frame time.** The template sets `Time.captureDeltaTime = Time.fixedDeltaTime`: one rendered
  frame per fixed step, every frame the same length. Confirm `Time.timeScale` is back at 1 when each
  lap starts; a slow motion left over from the last lap changes the game time per frame. The wall
  clock is outside all of it:
  `grep -rn 'unscaledTime\|realtimeSinceStartup\|DateTime.Now' Assets --include='*.cs'`.
- **Velocity under a pinned step.** The probe's fallback divides by unscaled time and reads nonsense;
  register the body with `SetPlayer`, or use `SetPlayerVelocity` (`reference/probe-contract.md`).
- **The game's own randomness.** The template seeds `UnityEngine.Random` before the scene loads; a
  game that seeds from the clock overrides it: `grep -rn 'InitState\|new System.Random(' Assets`.
- **Collections.** Iterating a `Dictionary` or a `HashSet` has no defined order
  (`unity-2d-level` → `reference/procedural.md`).
- **Physics.** Replay on the same machine and Editor version; confirm whether Enhanced Determinism is
  on (`grep -rn m_EnableEnhancedDeterminism ProjectSettings/`) and whether your replays need it.
- **Streaming** finishes on the wall clock: a lap's readiness wait absorbs the loads at its start,
  but a section that streams in mid-drive lands on a different step each run.
- **`System.Random` is stable for a seed within one runtime**, not promised across Editor upgrades:
  keep the failing timeline, not only the seed.

## Where it runs: a clone lane, for as long as it takes

A soak is the natural long job for a test lane: a read-only PlayMode run holding one lane for an
hour while the others stay free for the edit-compile loop. → `unity-debug` → `reference/parallel-runs.md`

- **The pinned frame time keeps the neighbours out of the verdict:** a loaded CPU changes `wall=`,
  not the step that fails. Not beside a performance run, which needs the machine to itself.
- **Split by situation when the results are merged:** one test name in two files is a duplicate.
  Split by seed only when each lane's verdict is read on its own.
- **Give every job its own `JOURNEY_OUT`.** Every lane resolves the same `persistentDataPath`.
- **Confirm whether your lanes share PlayerPrefs** before a soak runs beside other tests: the
  `[SetUp]` wipe reaches the other lanes, and their writes reach the soak.

```bash
seed=$(date +%s)
for id in approach-gate runner-launch hazard-lane; do
  SOAK_SEED=$seed SOAK_SITUATIONS=$id SOAK_SECONDS=900 JOURNEY_OUT=/tmp/<game>_soak_$id \
    lanes.sh run -- -batchmode -projectPath '{project}' -runTests -testPlatform PlayMode \
      -testFilter CourierSoak -testResults /tmp/<game>_soak_$id.xml -logFile /tmp/<game>_soak_$id.log &
done
wait
grep -h '\[SOAK\] \(PASS\|FAIL\)' /tmp/<game>_soak_*.log
```

Exit 2 with a `FAIL` line is a real verdict: replay that seed — a fresh seed that goes green says
nothing about it. No results file, or no `[SOAK] seed=` line in the log, means nothing was soaked.
→ `unity-debug` → `reference/test-verdicts.md`

## Reading a red soak

| Symptom | Cause |
|---|---|
| `input-landed` with `laneMoves=0 laneKey=yes` | The controller cached the reader in `Awake` instead of resolving each step |
| `input-landed` with `laneKey=no` | The probe has no `lane` key — register it, or witness the input with another value |
| `stuck-state 'Crashed'` | The way out waits on an event nothing raises, or on input the table never sends |
| `state-backwards` inside one lap | A trigger that fires on enter and on stay; a handler subscribed twice |
| `not-ready` on lap 2 or later | Re-entry inherits state the first entry never had |
| `Timeout value of … ms was exceeded`, no `FAIL` line | The wall clock outran `[Timeout]`: shorten `SOAK_SECONDS`, or raise it |
| Green every night, `unvisited=AtGate` | Chance never gets there — add a situation that starts there |

## What a soak cannot tell you

Anything no invariant names (a runner clipping through a moving hazard passes every rule above);
coverage beyond `states=` and `unvisited=` in the `PASS` line; feel
(`reference/complaint-to-test.md`); frame time (`unity-profiling`); a device
(`unity-device-testing`). Report it as *N seeds × T seconds per situation, these invariants held*,
never as "no bugs".
