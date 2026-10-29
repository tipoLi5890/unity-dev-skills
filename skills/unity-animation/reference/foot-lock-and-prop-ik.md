# Foot lock and prop IK with Animation Jobs

> Part of the `unity-animation` skill. Clips that are blended, rate-scaled and stride-warped
> will not keep a planted foot still or put a racket face on a ball. Three Animation Jobs after
> the mixer do: a foot lock, a look-at and a prop (hand) IK. This page is how they were built
> for a tennis game on a Generic rig, what broke on the way, and the numbers that ended it. The
> graph they sit in is `reference/sim-driven-animation.md`; the gate that measures them is
> `reference/motion-metrics.md`. A Humanoid that only needs feet on uneven ground is simpler:
> `reference/ik-and-rigging.md` §3.

## 1. The rule the second round proved

**Every IK target and every IK weight must be continuous in position and in velocity.** The
first round's pops were almost all one procedural quantity jumping in speed for one frame: a
0.15 s smoothstep releasing a foot lock (the target stops, then moves at the foot's full speed),
a hard 20° wrist clamp, a reach clamp the swing leg hit and left, a weight snapping to 0 when a
swing ended early, a knee plane re-chosen from noise. None came from the clips or the blends.

The tools that replaced each of them, all in `resources/AnimJobMath.cs`:

| Need | Use | Not |
|---|---|---|
| Follow a target that jumps | `Spring` — critically damped, exact for any `dt`; position and velocity stay continuous, only acceleration jumps | First-order lerp (velocity jumps), `MoveTowards` (velocity jumps twice) |
| A limit near full extension | `SoftReach` — linear to a fraction of length, then an exponential approach to the cap | `Mathf.Clamp` (a wall the joint hits at full speed) |
| A limit that must equal the clip when IK is off | `SoftReachRel` — softening starts at the larger of the soft point and the clip's own distance | A soft limit that bends an arm the clip held straight, so turning IK on bends the elbow in one frame |
| An arc that starts and ends at rest | `Bump` — 16u²(1−u)², value and slope 0 at both ends | `sin(πu)` (slope jumps at the ends) |
| A joint that bends one way | `TwoBoneHinge` — the bend plane from a stored hinge axis | A hint position, or the plane of the current bend |

`omega` in `Spring` is the speed: about 4.7 / omega seconds to 1% of the gap. The values below are
all `omega` in rad/s.

## 2. The foot lock — `resources/FootLockJob.cs`

### Plant windows come first

The lock needs to know when each foot is planted in each clip. Annotate it offline with
`blender-retarget` → `scripts/motion_metrics.py`, which writes the windows (`plants.<side>.ranges`).

**Plant, one definition** (the same sentence in `reference/motion-metrics.md`,
`reference/foot-lock-and-prop-ik.md` and `blender-retarget` → `scripts/motion_metrics.py`): a
foot is planted over a run of at least 3 frames where its sole is under 4 cm above the floor and
its ground-relative horizontal speed is under 0.15 m/s; an in-place loop gets its travel speed
added back before the speed test, and supplied contact probabilities (≥ 0.5) define the plant
instead.

In an in-place loop a planted foot slides backward under the pelvis at the travel speed, so a
detector that does not add the travel back finds almost no stance. Confirm that each foot's
windows cover its stance (`plants.<side>.coverage`) before trusting them; when they do not, look
at per-frame foot height and speed, fix the declared travel, and never loosen the speed.

At runtime, plant is a **weight vote**: each active input's plant flag at its current time,
weighted by the input's mixer weight, entered at 0.6 and left at 0.4. The metrics use the same
signal, so the gate measures exactly what the lock was asked to hold.

### What happens to one foot each frame

1. **Stride warp** the toe and ankle along the travel direction (from the scheduler), softened
   past 0.85 of leg length toward 0.97.
2. **Ground** the lower of two contact points (heel under the ankle, ball under the toe,
   measured in the bind pose): pulled to the ground while planted, only kept above it while
   swinging; the blend between the two is a spring (`omega` 45).
3. **Lock.** On the first planted frame record the toe's horizontal position and the foot's
   yaw *as drawn on that frame* (including any release offset still decaying). Hold both while
   planted.
4. **Release** when the foot lifts, or step when it cannot stay:
   - the leg cannot reach even with the pelvis lowered,
   - the body has turned more than a release angle since the lock,
   - or the lock point is too far from where the clip has the foot.

   A forced release becomes a procedural step: 0.2 s, a `Bump` lift of at most 6 cm, landing
   where the clip has the foot.
5. **Blend back with a spring whose start velocity is minus the foot's velocity.** At release
   the offset is `lockPoint − clipFoot` and its velocity is `−clipFootVelocity`. The target's
   velocity is therefore 0 on the release frame, as it was while locked, and rises continuously
   to the clip's. `omega` 28 for position (about 0.17 s), 12 for yaw (the foot is in the air,
   and a long lock may have accumulated a large yaw). The old 0.15 s smoothstep made the
   velocity jump at release: a knee pop on every lift.
6. **Anticipate landing.** For 0.08 s before the predicted touchdown, blend the horizontal
   target toward where the clip's foot will be at touchdown, extrapolated with its velocity and
   only the deceleration along that velocity (a swinging foot is decelerating; linear
   extrapolation overshoots, then pulls back). The foot arrives nearly still, and locking does
   not stop it in one frame. The scheduler supplies time-to-plant per foot by looking ahead in
   the clips' plant windows.
7. **Lower the pelvis** to the larger of the pre-drop (from the stride) and what the farthest
   locked leg needs, capped at 10 cm, through a spring that drops fast and rises slowly (`omega`
   60 down, 16 up). Compute "needs" at a reach fraction *below* the leg's softening start: a
   locked foot inside the soft zone slides a few millimetres, which was enough to push short
   plants' mean speed toward the gate.
8. **Solve the leg** with the hinge solver (§3), and set the foot's rotation to the clip's plus
   the yaw correction.

| Constant | Value |
|---|---|
| Plant hysteresis | enter 0.6, leave 0.4 |
| Release spring | position `omega` 28, yaw 12 |
| Landing anticipation | 0.08 s |
| Procedural step | 0.2 s, lift ≤ 6 cm |
| Pelvis drop | ≤ 10 cm; spring 60 down, 16 up; pre-drop 0.10 m per stride unit, ≤ 0.06 m |
| Leg softening | from 0.985 of length while locked or about to land, 0.93 while swinging, never past 0.998; the two blended by a spring (60) |
| Swing-leg stride limit | soft from 0.85, toward 0.97 |

Result over two 24 s matches and the last three runs: slide p95 per plant 0.12–0.27 cm, max
0.27–0.41 cm against gates of 1.5 and 3 cm; mean speed while planted 0.7–2.0 cm/s against 3,
one run reaching 2.7. Before: p95 109–225 cm, mean speed 465–704 cm/s.

## 3. The two-bone solver — a hinge, not a hint

A knee and an elbow bend about one axis. The first solver used the classic arrangement — a bend
plane from root, target and a hint, the cosine rule for the middle joint, minimal rotations —
with the knee hint derived from the toe's horizontal direction. Near full extension the
clip's own bend direction is noise, and the toe direction flips when the foot turns; the knee
plane flipped with it.

`TwoBoneHinge` instead:

1. Keeps a **hinge axis in the upper bone's local frame**, measured once from a pose where the
   limb is clearly bent (the ready stance), and refined slowly from the clip when it bends more
   than 25° (a candidate more than 45° away is rejected as a flip).
2. Uses the clip's own bend plane while it bends enough (8–30°), blending to the stored axis as
   it straightens.
3. Rotates the lower bone about that axis by the angle that puts the tip at the (softened)
   target distance — always toward the bending side, so it cannot hyper-extend — then turns the
   upper bone by the minimal rotation onto the target. Twist follows the clip.

If no axis has been measured yet (the limb never bent), fall back to the hint solver with the
character's forward as the hint for a knee. The knee direction is anchored to the body's
forward, not to the foot.

## 4. Prop IK — a racket face onto a ball

The job moves the hand so that a point on the held prop (the racket face centre, a child of the
hand's prop bone) is one ball radius from the ball centre along the face normal at the
simulated contact instant.

| Piece | Setting | Why |
|---|---|---|
| Window | Weight ramps to 1 from contact − 120 ms (reached at −20 ms), holds to +60 ms, releases over 0.15 s; ramp up ≥ 0.08 s, down ≥ 0.15 s | Long enough to be invisible, short enough not to fight the swing |
| Weight under the swing | Never above the swing clip's own weight while it fades in | IK on a pose that is still mostly the run |
| Early end | Keep the last error and keep releasing; never step to 0 | |
| Displacement field | `d = w · E`, `E = target − predicted face position at contact`; the whole swing path is translated, not pinned at one point | A pinned face stops the swing |
| Prediction | The clip's face path to the contact frame (sampled offline at 120 Hz, −0.4 to +0.3 s) plus the character's own movement and turn until contact; in the last 0.05 s extrapolate the prediction's own drift, not the face (a serve's face moves 20 m/s on a small circle) | |
| Freeze | `E` frozen after contact | |
| Face side | Which side of the face meets the ball comes from the stroke's swing direction at contact, fixed for the stroke | Choosing it per frame from velocity flipped it mid-window |
| Clavicle | Adds only the reach the IK wants beyond the clip's own and beyond 0.88 of arm length, times the weight, smoothed over 0.04 s; at most 15° (groundstroke), 25° (overhead, serve) | A clavicle that helped whenever the arm was straight popped at window edges |
| Arm | Hinge two-bone at the elbow; soft from 0.93 (groundstroke), 0.97 (overhead, serve); relative to the clip (`SoftReachRel`) | IK on/off never bends a straight arm in one frame |
| Wrist | **Solved last**: rotate the hand so the face centre lands on the goal; linear to 14°, then a smooth saturation toward 24° | Was a hard 20° clamp |
| Other hand | On a two-handed stroke, follow the grip in its clip-relative pose, weight fading in from 35 cm to 10 cm away | |
| Expected miss | A late or unreachable ball (too far, under 15 cm high) is not chased | |

Racket face centre to ball centre at contact went from p50 18.4–18.6 cm to 3.4–4.1 cm;
face-plane error p95 from 27–137 mm to 8.4–17.8 mm against ±15 mm. One match type passed every hit;
the other still missed 1–2 hits per run, each a face-plane distance (2–13 cm from the centre, the
ball sunk into or short of the face), which is what led to moving the simulation's contact
geometry onto the clips (`reference/sim-driven-animation.md` §6).

## 5. Look-at

Head, neck and chest share the turn (1.0, 0.4, 0.2; the chest not at all during a swing), at
most 75° from the clip's head direction. The look direction is smoothed in world space (time
constant 0.1 s) and capped at 360°/s; the weight (1 when the ball is visible, 0.6 when not,
× 0.3 during reactions) is smoothed over 0.3 s. The weight is smoothed because a stepped weight shows as a pop like any other.

## 6. Diagnostics the jobs should expose

The second round's progress came from being able to say which layer moved a joint:

- After the foot job and after the look job, copy the local rotations of the measured joints
  into a `NativeArray` (each job its own array). The mixer output is a third copy. The bones
  after the last job are the fourth. A pop is then attributed to the layer whose difference from
  the previous layer has the spike.
- Per foot: locked or not, drift from the lock point, release reason, reach wanted ÷ leg
  length, the clip's reach, how far the hinge axis turned this frame, pelvis drop.
- Per contact: face normal used, how often the face side flipped in the window, how much the
  last pre-freeze `E` changed, and whether the ball position came from the hit event, the plan
  or extrapolation.

## 7. Symptoms

| Symptom | Cause | Fix |
|---|---|---|
| A knee pops when the lock releases | Release blended over a fixed time; the target's velocity jumps from 0 to the clip foot's | §2 step 5: spring with start velocity `−footVelocity` |
| The foot stops dead on landing | Locked at the first planted frame while still moving | §2 step 6: anticipate the touchdown point 0.08 s ahead |
| The knee flips sideways when the leg straightens | Bend plane from a hint or from the clip's near-zero bend | §3: hinge axis stored in the thigh's frame |
| The swing leg snaps straight for one frame at speed | Stride warp clamped hard at leg length | Soft reach from 0.85 toward 0.97 |
| A locked foot creeps a few millimetres | Lock point inside the leg's soft zone | Lower the pelvis using a reach fraction below the softening start |
| The elbow bends the moment the racket IK turns on | Soft reach not relative to the clip | `SoftReachRel` |
| The racket arm pops at the window's edges | Clavicle or wrist hard-clamped; weight stepping on early end | Clavicle only for extra reach × weight; wrist soft saturation; keep releasing from the last error |
| The ball is on the wrong side of the face | Face side picked per frame | Fix it from the stroke's swing direction |
| Feet still skate in run loops although the lock exists | The lock never engages: an in-place loop annotated without its travel speed, so no plant windows | Re-annotate ground-relative (the loop's travel speed declared, §2) and check the windows cover stance |
