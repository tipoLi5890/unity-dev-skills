# Sim-driven animation — a hand-built graph that follows a simulation

> Part of the `unity-animation` skill. When a deterministic simulation already decides where
> the character is and when it hits the ball, the animation's job is to arrive there on time,
> never to decide. That rules out an Animator Controller: there is no state the graph may own,
> and a clip's time has to be a function of the simulation's clock, not of how many frames have
> passed. This page is the arrangement a tennis game shipped with, and the numbers it was tuned
> to. The IK that finishes the pose is `reference/foot-lock-and-prop-ik.md`; the gate that
> proves it is `reference/motion-metrics.md`.

## 1. When to leave the Animator Controller

| Keep the Controller | Build a `PlayableGraph` per character |
|---|---|
| The game's state is a handful of flags; transitions can be written as parameters | A planner already knows a contact time 0.9–1.7 s ahead, and a clip's key frame must land on it |
| Clip time can run on its own clock | Clip time must be recomputed from simulation time every frame, so a replay poses identically |
| Humanoid, `OnAnimatorIK` is enough | A Generic rig (no `OnAnimatorIK`), or IK that must run between blend and output |
| Few clips at once | Many weighted inputs (loops with seam cross-fades, two height variants of one swing, reactions) |

No runtime motion matching either. With the contact known a second ahead, the schedule is
computed once, its result is fixed and replayable, and it costs nothing per frame.

## 2. The graph

```
AnimationClipPlayable ─► InputAlignJob ─┐
AnimationClipPlayable ─► InputAlignJob ─┤
        … one pair per slot …           ├─► AnimationMixerPlayable ─► FootLockJob ─► LookAtJob ─► PropIKJob ─► AnimationPlayableOutput
AnimationClipPlayable ─► InputAlignJob ─┘                                                                         (Animator)
```

| Piece | Why it is there |
|---|---|
| `graph.SetTimeUpdateMode(DirectorUpdateMode.Manual)` | Nothing advances on its own. Each frame the scheduler sets every slot's time and weight, writes the job structs, then calls `graph.Evaluate(0f)` |
| `clipPlayable.SetTime(t)` per slot, only when its weight is above 0 | The clip's time is computed (§3), never accumulated |
| `SetApplyFootIK(false)`, `SetApplyPlayableIK(false)` on each clip playable | The jobs are the only IK |
| `InputAlignJob` before the mixer, one per input | Moves that clip's pelvis ground projection to the origin and turns its facing to +Z. Before this, the whole model was moved to follow the heaviest clip, and a blend between two clips dragged the pelvis round |
| Jobs after the mixer, in the order foot → look → prop | Each corrects what the previous one left. The hand reaches last, so a leg or spine change cannot move it off its target |
| `Animator.applyRootMotion = false`, `cullingMode = AlwaysAnimate` | The simulation owns the position; an off-screen character still poses |
| Cross-frame job state in `NativeArray`s the rig owns, disposed in `Destroy` | A job struct is copied in each frame; anything that must survive to the next frame lives in a native array |

Evaluate in `LateUpdate`, after the frame's render tick is known:

```csharp
public void Evaluate()                           // called from LateUpdate by the view
{
    footPlayable.SetJobData(foot);               // the scheduler edited these structs this frame
    lookPlayable.SetJobData(look);
    propPlayable.SetJobData(prop);
    graph.Evaluate(0f);                          // writes the bones now, synchronously
}
```

The object hierarchy keeps three owners apart:

```
Root     position and facing from the simulation, interpolated to the render tick
└ Align  the root correction (§5): the only offset presentation adds
  └ Model the imported rig; the Animator lives here
```

`resources/AnimJobMath.cs`, `resources/TwoBoneIKJob.cs` and `resources/FootLockJob.cs` are the
job side. Generic rigs never get `OnAnimatorIK`; Animation Jobs (`IAnimationJob` with
`TransformStreamHandle`s from `animator.BindStreamTransform`) are how a Generic rig is corrected
without the Animation Rigging package.

## 3. Clip time is a function of simulation time

Every one-shot keeps its contact tick `tc` and a rate. At render tick `T` (fractional, the same
one the renderer interpolates the ball with):

```
clipTime = clip.contact − (tc − T) · tickSeconds · rate
```

There is no `time += dt` anywhere. A frame hitch, a replay or a seek lands on the same pose, and
the contact frame lands on the contact tick **by construction**: the measured error was 0.00 ms
on every hit, before and after all the IK work.

Loops are the same: a loop's phase is derived from distance or from the simulation's time and
the playback rate, and a loop that is faded in takes the phase of the step already showing
(the plant phase of the left foot), so a gait change does not restart the stride.

## 4. Scheduling a swing onto a contact tick

When the planner publishes a contact (`tc`, contact point, family, side, contact height):

1. **Pick the clip pair by height.** In the family and side, take the two clips whose contact
   heights bracket the planned height, and play both at the same `tc` and rate, weighted
   linearly by height. Use one clip when the two heights differ by under 5 cm or the ball is
   outside the group's range. The family itself is the plan's decision, not the animation's; only
   when an overhead ball is higher than every clip in its group does the choice widen to the whole
   overhead family.
   The contact offset, the root correction and the racket path are all the weighted blend.
2. **Lead time.** `lead = min(contact − windupStart, 0.85 s)` (1.0 s for overheads). Before the
   swing starts the character is in locomotion.
3. **Rate and trim.**

```
avail = (tc − now) · tickSeconds
if avail ≤ 0.03 s:      do not start a swing — too late to show one
elif avail ≥ lead:      rate = 1;  start at tc − lead
else:                   rate = min(1.25, lead / avail);  start now
```

   When the rate is clamped at 1.25 the formula in §3 starts the clip part-way into its
   wind-up: the start is trimmed, the contact is still exact. A serve instead sets its rate so
   the toss-release frame meets the simulation's toss tick, clamped 0.8–1.25.
4. **Shorter fade for a late start.** Be fully in the swing 0.18 s before contact; fade in over
   0.08–0.2 s depending on the time left. A fixed 0.2 s fade on a late start leaves the contact
   frame half-blended with the run.
5. **Late player input.** When the shot type is still unknown 0.10 s (scaled by rate) before
   contact, the swing creeps at 0.35× toward the contact pose. When the input arrives, cross-fade
   0.12 s into the chosen variant at up to 1.6× to meet `tc`. A miss plays through at 1.2×.
6. **Start from the predicted stop.** If the simulated character is still running, predict when
   it stops from the simulation's own movement model (top speed, acceleration, deceleration) and
   begin the swing fade 0.2 s before that stop, and never later than 0.3 s before contact. After
   contact, if the predicted speed exceeds 1.2 m/s 0.1 s later, fade the follow-through out over
   0.25 s and hand back to locomotion.

## 5. Root correction — the last few centimetres, with caps

The clip's contact point rarely lands on the planned contact point. The Align node shifts the
model by at most:

| Stroke | Cap | Why |
|---|---|---|
| Groundstroke | 0.15 m | The arm IK can reach the rest |
| Overhead | 0.25 m | The arm is already straight; IK has little left to give |
| Serve stance | 0.35 m | The plan's hard limit |
| Yaw, any stroke | 25° | |

Before the caps the limit was 0.6 m and the needed correction ranged from 3 to 144 cm — a body
sliding sideways under a planted foot. The rules that made the shift invisible:

- **Solve against the predicted position at contact**, not the current one. Solving against the
  current position re-solves, and jumps, as the character arrives.
- **Fix the shift in the frame it was solved in.** When the root turns later, the shift does not
  swing round the simulation position.
- **Ramp it in from the swing start to `max(start + 0.4 s, contact − 0.15 s)`**, keep the weight
  continuous, and when a swing ends early release it over 0.15 s.
- **Absorb the simulation's own discontinuities.** A simulated velocity change above 20 m/s² in
  one tick is smoothed by the root; above 4 m/s it is a teleport (a point reset) and is not
  smoothed.

Root velocity jumps over 0.5 m/s per frame fell from 39–86 frames per 24 s match to 17–36 with
the caps, and to 0 once the shift was solved against the contact-time position with a residual
spring (measured with the teleport rule above, widened in the same change).

## 6. When the simulation runs faster than any clip

The simulation's top speed was 7 m/s (p95 of all frames, 15–22% of frames at 4.5 m/s or more);
the fastest usable run loop moved at 2.7 m/s. Playback rate alone cannot close that, and a foot
lock without the rest of this section is pulled apart every stride. Before any of it, feet slid
p50 22.9–26.5 cm and p95 109–225 cm per plant.

| Layer | Setting | Note |
|---|---|---|
| Gait choice | From the predicted velocity `v + a · 0.12 s`, with hysteresis (sprint enters at 2.6, leaves at 2.1 m/s) | Starts and stops react a step early |
| Playback rate | `speed / clipSpeed`, 0.8–1.25 for shuffles and backpedal; up to **1.8×** for the sprint (about 4.5 steps per second) | Rate and stride use the actual speed, not the predicted one |
| Stride warping | `stride = speed / (clipSpeed · rate)`, 0.3–1.8×, applied to each toe's offset from the pelvis along the travel direction | The planted foot then stays still in the world |
| Swing-leg reach | Past 0.85 of leg length the warped ankle is softened exponentially toward 0.97 | Without it the swing leg snaps straight one frame and stops the next |
| Stride axis | Follows the velocity direction with smoothing; held when stopping | |
| Pelvis pre-drop | 0.10 m per unit of stride above 1, capped at 0.06 m | A long stride is only reachable with the hips lower |
| Orientation warping | Legs turned toward the velocity, ±60° (fading beyond); spine counter-rotates 35 / 35 / 30% so the chest keeps facing | |
| Lean | Forward 10°, back 6°, side 6°, from acceleration | |
| Facing | Toward the play normally; toward the run direction when sprinting, at most 540°/s | |
| Split step | Procedural: crouch, hop 5 cm, land 0.05 s after the opponent's contact with a 4.5 cm knee dip; only when nearly still (< 0.8 m/s) | The library had no split-step clip |

After all of it, with the foot lock: slide p95 0.12–0.27 cm, max 0.27–0.41 cm per plant.
The cost is visible: legs very long and hips low at 7 m/s, and about 40% of the remaining
single-frame pops were in that sprint. The lesson that came after: **measure the gap between
the simulation and the clips first, and change the simulation's numbers when the gap is
large.** The project then capped run speed at 6.0 m/s and moved each stroke's contact geometry
(serve toss point, contact heights) to where the clips actually put the racket, leaving IK the
last few centimetres. A serve whose simulated toss point sat 65 cm from the clip's could not be
fixed by a 0.35 m cap however good the IK. The design-time method (sample loop speeds and
contact points on the reference body before freezing the simulation's numbers):
`unity-gameplay` → `reference/genre-timing-sports.md` §0.

## 7. Symptoms

| Symptom | Cause | Fix |
|---|---|---|
| The swing contact is early or late by a frame or two | Clip time accumulated with `dt`; a hitch or a rate change drifts it | §3: compute clip time from the contact tick every frame |
| Contact is exact but the swing starts with a jerk | Rate clamped, start not trimmed — the clip was started from its first frame and then jumped | §4 step 3: start mid-wind-up when the rate is clamped |
| The pelvis swings round during every blend | The whole model is moved to follow the heaviest clip | §2: align each input before the mixer |
| Feet skate when the character runs faster than the clip | Playback rate clamp leaves a gap | §6 stride warping, pelvis drop, then the foot lock |
| The swing starts while the body is still sliding to a stop | Swing scheduled by lead time only | §4 step 6: start from the predicted stop |
| The body slides sideways at every contact | Root correction too large or solved against the current position | §5 caps and the contact-time solve |
| A replay poses differently from the live match | Some time or weight is accumulated per frame | Everything the graph reads is a function of the simulation tick |
