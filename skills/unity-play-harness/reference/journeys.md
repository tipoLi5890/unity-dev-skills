# Journey tests: assert on the recording, not on one frame

> Part of the `unity-play-harness` skill. A journey enters a situation, drives the game, samples
> the probe into a timeline and asserts over the whole run. `resources/JourneyRecorder.cs` is the
> file; `templates/JourneyTest.cs` is a complete test to copy.

A frame assertion answers "was it right when I looked". Almost every interesting failure is about
what happened *between* the looks: the lane collider that arrived two frames after the runner was
drawn, the state that briefly went backwards, the speed that was only excessive for 0.3 s.

## Anatomy

```
[SetUp]            PlayerPrefs.DeleteAll() · Situations.ClearParams() · GameProbe.Reset()
                   leave the journeys root alone — the recorder clears its own folder
load               the scene, LoadSceneMode.Single, then one frame
enter              Situations.Enter(id) → WaitUntilReady()          ← never WaitForSeconds
record             using (var journey = new JourneyRecorder(id, dir))
drive              through the project's own input funnel, for N unscaled seconds
sample             journey.Sample() every frame (or every k frames), in Update
milestone          journey.Milestone("arrival") → tag the row AND capture the PNG, same frame
assert             over journey.Captured, then print the numbers the assertions used
```

Five details in there that are the difference between a journey that catches things and one that
only looks like it does:

- **Delete the journey directory in `[SetUp]`.** A half-overwritten timeline next to last run's
  screenshots reads as one run and describes neither. The recorder deletes its own subdirectory
  too — belt and braces, because the constructor runs after the test has already started.
- **Drive through the input funnel.** Calling a movement method directly skips the code the
  complaint is about; three physical buttons mean three commands, and the test presses those.
- **Time the drive on unscaled seconds** — `journey.ElapsedUnscaled`. A run that sets `timeScale`
  to 0 to inspect something would otherwise loop forever.
- **Sample in `Update`.** `WaitForEndOfFrame` does not resume in batch mode, so a journey that
  samples there records nothing headless and everything windowed, which is the worst of both.
- **Tag and photograph in the same frame.** `Milestone` writes the row; the capture that follows
  it must be the same moment, or the image and the row disagree and nothing says so.

## Three families of invariant

Everything worth asserting over a recording has been one of these three shapes.

**1 · Never in an illegal place.** Static geometry only — it is evaluated against the colliders
present when it runs, which is right for lane walls and the gate frame and wrong for anything
that moves. For movers, sample an overlap flag into `custom{}` each frame and use family 3.

```csharp
var inside = JourneyAsserts.NeverInside(samples, LayerMask.GetMask("Track"), 0.25f);
Assert.IsEmpty(inside, JourneyAsserts.Describe(inside));
```

A 2D game uses the sibling in `resources/JourneyInvariants2D.cs` — the same rule on the x/y
plane, with `Physics2D.OverlapCircle` behind it. It is a separate file so that a project without
the 2D physics module still compiles the rest of the harness.

```csharp
var inside = JourneyInvariants2D.NeverInside2D(samples, LayerMask.GetMask("Rooftop"), 0.2f);
Assert.IsEmpty(inside, JourneyAsserts.Describe(inside));
```

- **Triggers never count**, whatever `Physics2D.queriesHitTriggers` is set to: a pickup and a
  sentry's vision cone are places the runner is allowed to be.
- **Keep the radius smaller than the body.** A runner standing on a rooftop touches it, and a
  circle as wide as its collider reports every grounded sample. Start at half the collider's
  smallest half-extent — 0.2 for a 0.8-wide runner — and leave the runner's own layer out of the mask.
- **`pos` is the transform, not the collider's centre.** A sprite pivoted at the feet puts the
  circle half inside the floor; sample from a child at the body's centre, or pass that child to
  `SetPlayerVelocity`.

**2 · The state machine only moved forward.** Catches a re-entered phase and a state nobody
declared — both of which pass every single-frame check.

```csharp
var backwards = JourneyAsserts.Monotonic(samples, new[] { "Idle", "Launched", "Approach", "AtGate" });
```

**3 · Readiness held before the moment.** The window narrows it to the frames that matter, so a
lane still loading 40 units out is not a failure and the same lane still loading 2 units out is.

```csharp
var late = JourneyAsserts.ReadyBefore(samples, "arrival", s => s.Number("gateDist", 999f) < 20f);
```

And the general form, which covers every budget-shaped assertion — a predicate that must never
hold anywhere in the recording:

```csharp
var tooFast = JourneyAsserts.Never(samples, s => s.Number("gateDist", 999f) < 2f && s.speed > 12f,
                                   "entry-speed");
```

**Assert on transitions and bounds, not on absolute values.** `speed == 9.8` fails the first time
someone tunes the launch; `speed < 12 within 2 units of the gate` keeps meaning the same thing.
The absolute numbers belong in the printed line underneath, where they stay readable:

```csharp
TestContext.WriteLine($"samples={samples.Count} maxEntrySpeed={maxEntry:F2} timeline={journey.TimelinePath}");
```

## What a 2D game asserts

The recorder, the timeline and the report are the same; only the registration differs —
`templates/CourierSituations2D.cs` registers `SetPlayerVelocity` and the 2D colliders. `speed` and
`vel` are then as trustworthy as the delegate behind them. → `reference/probe-contract.md`

| View | Situation | Worth asserting over the run |
|---|---|---|
| Side run | `ledge-drop` | `NeverInside2D` on the rooftop layer · `rooftopMesh` and `rooftopCollider` true in the same sample · `-vel[1]` under the terminal fall speed · `custom.grounded` false for no longer than the designed air time |
| Top-down depot | `depot-aisle` | `NeverInside2D` on the shelving layer · `speed` under the run speed (a diagonal that reads 1.41× is an un-normalised input) · `custom.seen` never true while `custom.sentryDist` exceeds the cone length |
| Sorting yard | `yard-step` | `custom.pickupToGate` never rises · one step changes `cellX` + `cellY` by exactly 1 · `pos` equals the cell centre whenever `custom.stepping` is false |

```csharp
// Side run: the fall never exceeds the designed terminal speed.
var tooFast = JourneyAsserts.Never(samples, s => -s.vel.y > 22f, "terminal-fall");
// Depot: seen only from inside the cone's reach.
var seenFar = JourneyAsserts.Never(samples,
    s => s.CustomOf("seen") is bool seen && seen && s.Number("sentryDist") > 5f, "seen-out-of-range");
// Yard: the pickup only ever gets closer to the gate cell.
int best = int.MaxValue;
var drifted = JourneyAsserts.Never(samples, s =>
{
    int d = (int)s.Number("pickupToGate", 0f);
    bool worse = d > best;
    if (d < best) best = d;
    return worse;
}, "pickup-moved-away");
```

Two things a 2D recording gets wrong on its own:

- **A body moved in `FixedUpdate` and sampled in `Update` repeats.** Without interpolation `pos`
  holds for several frames and then jumps, so a per-frame `Never` on position deltas fires on
  the sampling, not on the game. Set `Rigidbody2D.interpolation`, or assert on `vel`.
- **A moving platform or a pushed pickup is not static geometry.** `NeverInside2D` tests the
  colliders where they are when the assertion runs; sample an overlap flag into `custom{}` each
  frame and use `Never` on it.

## What to sample

Sample the handful of values a complaint could be about, and nothing else — a timeline is read by
a human eventually.

| Key | Why it is in the line |
|---|---|
| `speed` | Every "comes in too fast / feels sluggish" report resolves against this |
| `custom.gateDist` | Turns "near the gate" into a window a report can filter on |
| `custom.lane` | Three lanes 1.3 units apart; an off-by-one lane looks like a physics bug |
| `custom.laneOffset` | The runner's actual x, which is how lane drift is distinguished from lane choice |
| `counts.hazards` · `counts.pickups` | A streaming failure shows up as a count that never rises |
| `ready.laneMesh` · `ready.laneCollider` | The pair whose split is the whole "disappears while it loads" class |
| `cam` | A null camera explains a black screenshot before anyone examines the pixels |
| `custom.lodLevel` | Two shots at two distances mean nothing without the level each was taken at |

## The summary line

`Dispose` writes the end row and logs one line, which is the thing to grep for after a run:

```
[JOURNEY] approach-gate samples=74 milestones=1 seconds=12.34 path=/…/journeys/approach-gate/timeline.jsonl
```

`samples=0` next to a passing test is the failure mode worth naming: the drive loop never ran, the
assertions all iterated an empty list, and every one of them passed. **Assert the sample count**
before asserting anything else.

```csharp
Assert.IsNotEmpty(samples, "the journey recorded nothing — did the drive loop run?");
```

That is the same class of lie as a green suite that checked nothing.
→ `unity-debug` → `reference/test-verdicts.md`

## Sampling rate

Every frame for a 20-second journey is ~1200 rows and about 400 KB — fine, and the default.
Drop to `everyNFrames: 3` for a journey measured in minutes. The recorder always writes a
milestone row, whatever the filter says, so the tagged moments survive any rate.

For a long run, raise `MaxSamples` deliberately rather than discovering the cap: it exists so a
journey that never terminates fills a file instead of memory.

## Windowed and batch are two different runs

Both modes write the timeline — that is the point: the assertions and the report run identically
headless, and only the images need a window. Which mode can capture, and at what resolution, is
`unity-debug` → `reference/visual-checks.md`.

The one consequence that belongs to a journey: **"the milestone screenshots exist" must never be
a pass condition**, because a batch run passes and writes none. Assert on the timeline; treat the
images as the thing a person looks at afterwards.

## After the run

```bash
python3 scripts/journey_report.py \
  --after "$JOURNEYS/approach-gate/timeline.jsonl" \
  --monotonic state:Idle,Launched,Approach,AtGate \
  --max 'speed:12@gateDist<2' \
  --ready-before arrival --together laneMesh,laneCollider --no-null cam
```

The report prints `[REPORT] violations=N`, one line per violation with the frame and the value,
and a median/p95/max table for every numeric key. It exits 1 on a violation, so it works as a CI
step as-is. Pass `--before` with the previous run's timeline for the two-column table that turns
"it feels better" into a number. → `reference/timeline-format.md`

Confirm on your version: that `Object.FindAnyObjectByType` is the lookup your Editor resolves (it
replaced `FindObjectOfType`), and that your test assembly definition references both the runtime
assembly holding `GameProbe` and `UnityEditor.TestRunner` — a journey that cannot see
`EditorSceneManager` fails to compile rather than failing to load a scene.

## The autoplayer smoke run

The cheapest journey that covers boot, flow, input, rules, presentation and audio together: start
a match with the autoplayer on seat 0 (`situations.md`), let it play 22 s of match time, then
assert. From a tennis game, every assertion earned its place by catching something:

| Assert | Catches |
|---|---|
| No error or exception logged (collected from `logMessageReceived`) | Everything nothing else asserts on |
| The session is still running on every frame; the simulation thread reported no fault | A worker thread that died silently while the last snapshot stayed on screen |
| Points scored > 0, hits ≥ 5 | A match that runs but never plays |
| **The autoplayer's own seat hit the ball at least once** | A green run in which the input path did nothing and the bots played each other |
| Worst frame < 250 ms, after the first 30 frames | Gross stalls; not a performance test |
| Frames where the simulation was more than 2 ticks behind the clock ≤ 3 | The ball freezing at contact (the first-use JIT stall, `unity-debug` → `reference/unity-gotchas.md` §23) |

Log every number on one line whether or not it passed:

```
[SMOKE] <mode>: points <a>:<b> hits=<n> humanHits=<n> accepted=<n> frames=<n> maxDt=<ms> lagFrames(>2)=<n> maxLag=<ticks>
```

Two rules from running it on a machine shared with other agents: the lag counter is the first
assertion that load trips (red 5 > 3 under load, green alone with a worst lag of 1 tick), so a red
smoke run is rerun alone before it is called a regression; and the smoke run takes no
screenshots, because a capture stalls the frame for about 100 ms (`unity-debug` →
`reference/motion-and-timing.md`). Tag it `Smoke` and run it on every change; it took about a
minute.
