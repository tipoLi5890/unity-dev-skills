# Motion metrics — turning "the feet slide" into a gate

> Part of the `unity-animation` skill. Motion quality was argued about by eye until it had
> numbers; after that every change was a before and after. This page is the instrument a tennis
> game built (`resources/MotionMetricsSampler.cs` is its game-agnostic core), the gates, how the
> pop metric had to be redefined twice before it measured anything, and the ways the numbers
> lied. The graph is `reference/sim-driven-animation.md`; the jobs are
> `reference/foot-lock-and-prop-ik.md`.

## 1. The instrument

A read-only sampler. A PlayMode test (or a review situation) starts a match on autoplay and,
after each frame has rendered (`yield return new WaitForEndOfFrame()`), hands the sampler the
bones as drawn and the simulation snapshot for that frame's render tick. It changes nothing.
At the end it prints one tagged log line per metric with PASS or FAIL, and the test asserts the
gated ones.

**Take the baseline first.** Write the sampler, run it on the code you are about to change, and
keep that table. The baseline here was the pre-IK presentation code replayed under the same
sampler, so every "before" below is measured, not remembered.

## 2. What it measures, and the gates

| Metric | Definition | Gate |
|---|---|---|
| Foot slide per plant | Horizontal distance of the toe from its position on the plant's first frame, max over the plant; plants under 3 frames ignored | p95 ≤ 1.5 cm, max ≤ 3 cm |
| Plant speed | Horizontal path length ÷ plant duration | p95 ≤ 3 cm/s |
| Root vs simulation | Pelvis ground projection to the simulated position, locomotion frames only (no swing, no correction) | p95 ≤ 10 cm, max ≤ 25 cm |
| Root correction | The Align shift per contact | max ≤ 35 cm (hard); p95 ≤ 15 cm (target) |
| Prop at contact | Ball centre to face plane minus radius; ball's normalised radius in the face ellipse; at the exact contact instant | ± 15 mm and ≤ 0.8, every hit |
| Contact timing | The clip's contact frame against the simulated hit tick, in clip milliseconds | ≤ 1 ms |
| Pops | §3 | 0 |
| Root velocity jump | Change of the character root's velocity (simulated position + correction) per frame, scaled to a 60 fps frame; teleports excluded | ≤ 0.5 m/s |

**Plant, one definition** (the same sentence in `reference/motion-metrics.md`,
`reference/foot-lock-and-prop-ik.md` and `blender-retarget` → `scripts/motion_metrics.py`): a
foot is planted over a run of at least 3 frames where its sole is under 4 cm above the floor and
its ground-relative horizontal speed is under 0.15 m/s; an in-place loop gets its travel speed
added back before the speed test, and supplied contact probabilities (≥ 0.5) define the plant
instead.

**The sole is not a joint.** An ankle stands about 7 cm over the floor at rest, so a foot measured
by its lowest joint never comes under 4 cm: no plant is found, and the slide gate passes on
nothing. Offline, each foot joint's height has its rest height over the sole taken off first
(`sole_offsets` in the samples, from the rig's rest pose); the plant, penetration and slide all
read that sole. With the offsets, a foot that moves and finds no plant is reported as a warning
even when no gate asks for plants.

The offline report carries those windows (`plants.<side>.ranges`) and counts them per foot
(`plants_per_foot`) and in total (`plants_found`, as `contact_bake` reports it); its gate
`plants_min_per_foot` needs at least one on each foot. The runtime plant below is the foot lock's
vote over them. A baked clip is gated offline with `blender-retarget` →
`scripts/motion_metrics.py` (foot slide, ground penetration, jitter, joint limits, loop seam,
root drift, pops) before it reaches Unity.

Choices that made these honest:

- **Plant is the same signal the foot lock uses** (the weight vote), and a foot the lock had to
  release is still counted. The gate measures the lock against its own instructions.
- **The slide is absolute**, not relative to the clip. The purchased mocap itself failed it;
  the decision was to reach it at runtime with the foot lock rather than clean the clips or
  loosen the gate.
- **Procedural steps are excluded** from slide (they are steps), and counted separately.
- **Root velocity is measured on the character root**, not on the pelvis bone, which carries the
  clip's own pelvis motion (kept as information). A teleport is a move over 0.2 m in a frame or
  a simulated velocity change over 4 m/s; it is counted, not gated. Split the jump into the
  simulation's own part and the correction's part.
- **Contact position is interpolated** between the two rendered frames that bracket the hit
  tick. The nearest frame is up to a frame off (27.9 ms measured at 60 fps), which at swing speed
  is centimetres.

## 3. Pops — three definitions

**Version 1: "during a transition each joint's angular speed ≤ 1.2 × the larger of the two
clips' own peak at that joint".** Measured on the mixer output it failed 532–553 frames both
before and after any work: two different poses blended are faster than either clip. It could
not tell a visible pop from a normal blend. Kept as information only.

**Version 2: a single-frame spike in the final pose that the clip does not have.** A joint's
local angular speed at frame *i* is a pop when:

```
w[i] > 1.8 × max(w[i−1], w[i+1])           a spike, not a fast movement
w[i] − max(w[i−1], w[i+1]) > 180 °/s        at least ~3° extra in one frame at 60 fps
w[i] > 1.2 × clip[i] + 180 °/s              and faster than the clip itself at that frame
```

`clip[i]` is the same joint's angular speed in the mixer output, captured inside the first job.
The last condition is what separates a pop from a fast swing.

**Version 3: add two-frame-wide spikes and attribute every pop to a layer.** The review video
showed a serving arm straightening over two frames; version 2 missed it. A two-frame pop is two
adjacent frames both above 1.8× the frames outside them, at least 3° extra in total, and faster
than the clip's two frames by 1.2× plus 360 °/s. The whole-body yaw has no clip to compare, so a
spike alone counts. Each pop is logged with:

- the layer: compare the pose after the foot job, after the look job and after the prop job
  with the mixer output (`reference/foot-lock-and-prop-ik.md` §6) and name the first layer
  whose difference spikes; `clip` or `blend` when the mixer output itself spikes;
- a category: sprint, sprint-to-stop, locomotion, serving arm, hitting arm, other hand, upper
  body;
- the state of every procedural layer on that frame (lock, step, reach, pelvis, prop weight).

**What attribution showed:** of 31–63 pops per 24 s match after the first IK round, 0–2 came
from clips or blends. The rest came from the IK layers: about 40% in sprints at 4.5 m/s or more,
the rest at sprint-to-stop, the serving arm, and the other hand on two-handed strokes.
Inertialized transitions, which the design had planned, would not have removed a single one,
and were not built. The fix was velocity continuity in the jobs
(`reference/foot-lock-and-prop-ik.md` §1). Version 3, being wider, counted 68–120 for the same code;
the second round of continuity fixes took that to 58–114. A count that rises when the metric
widens is not a regression: compare counts only under one definition. Offline, a baked clip's
pops fail: `blender-retarget` → `scripts/motion_metrics.py` applies the same single- and
two-frame rule to the clip's segment directions (ratio 1.8, floor 30 °/s, 3° extra in the frame,
which is 180 °/s at 60 fps) and fails on any pop; `clip_metrics.py` adds the clip term against
the reference body (1.2 × the reference's speed + the same excess). Motion read from video carries
its readings (`reading_joints` with `reading_names`, the joints triangulated straight from the
views; arrays beside the positions in an NPZ) as that
reference: a spike the readings show too is a fast move in the source, listed as
`pops_in_source` and not gated; only a spike the solve added fails. Both counts are events, one
per frame and parent joint, so a twist segment beside the shin is not a second pop; `segments`
counts the segments that spiked. The runtime test (§6) logs
pops and asserts them once the count reaches 0.

## 4. Results, before → after

Two 24 s autoplay matches, two characters each; "after" is the range over the last three runs,
because autoplay plays differently every run.

| Metric | Before | After |
|---|---|---|
| Slide p95 per plant | 109–225 cm | 0.12–0.27 cm — PASS |
| Slide max | 205–418 cm | 0.27–0.41 cm — PASS |
| Plant speed p95 | 465–704 cm/s | 0.7–2.0 cm/s (one run 2.7) — PASS |
| Root vs simulation, locomotion | max 0.6–1.0 cm | max 1.2 cm — PASS |
| Root correction | 60 cm (cap 0.6 m) | 15 / 25 cm by stroke; serve 35 cm at its cap — serve FAIL |
| Face centre to ball, p50 | 18.4–18.6 cm | 3.4–4.1 cm |
| Face-plane error p95 | 27–137 mm | 8.4–17.8 mm; 1–2 hits per run outside ±15 mm in one mode — FAIL |
| Contact timing | 0.00 ms | 0.00 ms — PASS |
| Root velocity jump frames | 39–86 | 17–36; then 0 after the contact-time solve and the simulation-teleport rule — PASS |
| Pops | 0–6 under version 2 (no IK yet) | 31–63 under version 2; 68–120 → 58–114 under version 3 — FAIL |

## 5. Pitfalls that skewed the numbers

| Pitfall | What it did | Handling |
|---|---|---|
| **An Editor frame hitch across a contact** | The two frames bracketing the hit tick were ~100 ms apart; the interpolated face position was wrong by centimetres | A contact whose bracketing gap exceeds 40 ms is excluded from the face gate and listed separately; the last runs had none |
| **Screenshot PNG writes** | Saving a PNG blocked the main thread about 100 ms; on screenshot frames the measured contact frame was 97–126 ms after the hit tick | Do not capture screenshots in a metrics run; record video through async GPU readback in a separate review situation |
| **A gate with no margin** | Plant speed p95 reached 2.6–2.7 cm/s against 3.0: a flaky smoke test waiting to happen | Find the cause, not a looser gate: locked feet sat inside the leg's soft zone and crept; computing the pelvis drop below the soft start gave the margin back |
| **A plant detector that sees nothing** | Run loops had no plant windows, so their slide was never measured | Check window coverage per loop (10–30% of the cycle after the fix) |
| **Other work on the machine** | CPU contention from parallel editors made frame times and smoke runs unreliable | Treat perf numbers from a loaded machine as relative; rerun gates three times and report the range |
| **One run is one sample** | Autoplay rallies differ per run; a single PASS is luck | Three runs minimum, ranges in the table |

## 6. Wiring the test

```csharp
[UnityTest, Category("Smoke")]
public IEnumerator Match_MotionGates()
{
    var m = new MotionMetricsSampler();
    foreach (var c in StartAutoplayMatch())          // the game's: one entry per character view
        m.Add(new MotionSubject
        {
            Name = c.name, ToeL = c.ToeL, ToeR = c.ToeR, Root = c.Root, Pelvis = c.Pelvis,
            Planted = left => c.FootPlanted(left),   // the same vote the foot lock uses
            Stepping = left => c.FootStepping(left),
            SimPosition = () => c.SimPosition, Locomotion = () => c.InLocomotion,
            PopJoints = c.PopJoints, ClipLocal = j => c.MixerLocal(j),
        });
    float end = Time.unscaledTime + 24f;
    while (Time.unscaledTime < end)
    {
        yield return new WaitForEndOfFrame();         // the pose as drawn, after LateUpdate
        m.Sample(Time.deltaTime);
    }
    foreach (var line in m.Lines("match")) Debug.Log(line);
    var s = m.Summarize();
    Assert.Greater(s.Plants, 50, "too few plants: check the plant windows");
    Assert.LessOrEqual(s.SlideP95, MotionMetricsSampler.SlideP95Gate, "foot slide p95 during plants");
    Assert.LessOrEqual(s.SlideMax, MotionMetricsSampler.SlideMaxGate, "foot slide max during plants");
    Assert.LessOrEqual(s.PlantSpeedP95, MotionMetricsSampler.PlantSpeedGate, "plant mean speed p95");
    Assert.LessOrEqual(s.ContactErrMaxMs, MotionMetricsSampler.ContactErrGateMs, "contact frame vs hit tick");
    // Pops and root jumps are logged until they pass; assert them once they do.
}
```

`StartAutoplayMatch` and what each character hands the sampler are the game's; the harness side
(situations, probes, running headless) is `unity-play-harness` → `reference/journeys.md`.
