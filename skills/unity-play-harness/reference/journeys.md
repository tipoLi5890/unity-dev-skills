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
                   delete the journey directory
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
