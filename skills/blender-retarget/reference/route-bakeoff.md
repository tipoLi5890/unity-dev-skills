# Fit or retarget — the measured bake-off, and when each route wins

> Part of the `blender-retarget` skill. The fit route's method:
> `blender-character-rig` → `reference/fit-to-clip-skeleton.md`; its Unity import:
> `unity-rigged-character` → `reference/shared-skeleton-generic.md`. The numbers come from
> `scripts/clip_metrics.py`, the table from `scripts/bakeoff_report.py`.

A tennis game had 75 purchased mocap clips on one skeleton and generated characters. Three routes
were built for the same character and measured the same way.

| Route | What happens |
|---|---|
| **(b) Fit, Generic** | the character's mesh fitted once to the pack's skeleton; the purchased clips played as bought, Generic, sharing the character's Avatar |
| **(a) Humanoid** | character and clips both Humanoid, an explicit bone map, root motion baked into the pose; also measured with foot IK on (a+IK) |
| **(c) Retarget per clip** | the character's own skeleton (A-pose, Blender's default roll), each clip baked in Blender with `brt_retarget` and exported as its own FBX, played Generic. The old workflow's shape, without Auto-Rig Pro |

## How it was measured

- **Against the same clip on the pack's own body, in Unity.** Every route is sampled frame by
  frame in a Unity batchmode lab and compared with the pack's own body playing the same clip in
  the same lab, one formula for both, lengths scaled to the character's height. Measuring the
  target alone, or in Blender alone, hides what Unity does to the curves.
- **Representative clips:** an idle (641 frames), the fastest forehand (73), a smash (116).
- **Added foot slide, not absolute.** Inside each plant (sole under 4 cm, horizontal speed under
  0.15 m/s, at least 3 frames, found on the reference body), how far the character's foot moved
  from its plant-start position **beyond** what the reference foot moved:
  `|(c(t) − c(start)) − (r(t) − r(start))|`. The pack's own mocap failed an absolute gate of
  p95 ≤ 1.5 cm: 1.8 / 3.3 / 4.4 cm on the three clips. A character pipeline can only promise not
  to slide more than the source; the absolute gate is met in the game by foot-lock IK during
  plants (`unity-animation` → `reference/foot-lock-and-prop-ik.md`).
- **Limb direction error:** the angle between the character's and the reference's upper-arm,
  forearm, thigh and shin directions, per frame. Arm pose error: the wrist relative to its own
  shoulder divided by the arm's own length, so proportions cancel.

## The numbers (p95; idle / forehand / smash)

| Metric | (b) Fit, Generic | (a) Humanoid | (a+IK) | (c) as exported | (c) from each curve's first key |
|---|---|---|---|---|---|
| limb direction error | 0.0002° (all) | 1.55 / 4.38 / 2.91° | 2.38 / 4.87 / 3.31° | 0.31 / 0.63 / 2.15° | 0.16 / 0.51 / 0.16° |
| head rotation error | 0.00 / 0.02 / 0.00° | 1.33 / 5.29 / 3.78° | as (a) | not comparable (other bone axes) | |
| arm pose error | 0.28 / 0.54 / 0.51% | 2.5 / 8.2 / 3.9% | as (a) | 2.0 / 1.1 / 3.0% | 0.6 / 0.5 / 0.6% |
| worst elbow or knee angle error | 0.0002° | 0.36° | knees 5.1 / 8.8 / 9.2° | 0.03° | 0.22° |
| added slide p95 (≤ 1.5 cm) | 0.36 / 0.84 / 0.94 cm | 1.13 / **2.71** / **1.72** | 1.16 / 1.21 / 1.18 | 0.39 / 0.90 / **7.72** | 0.37 / 0.62 / 0.94 |
| added slide max (≤ 3 cm) | 0.59 / 0.97 / 0.95 cm | 1.78 / **3.08** / 2.00 | 1.80 / 1.34 / 1.45 | 1.14 / **7.53** / **8.10** | 0.76 / 0.71 / 0.95 |
| root deviation | 0 | 1.05 / 1.01 / 2.10 cm | as (a) | 0.01 / 0.05 / 0.15 cm | 0.01 cm |
| grip point error | 5.6 / 7.0 / 5.1 cm | 6.5 / 7.2 / 6.5 cm | as (a) | 6.0 / 7.0 / 6.4 cm | |
| new self-intersections | 6.2 / 3.7 / 5.5% | 6.3 / 4.0 / 5.4% | 6.6 / 4.0 / 5.5% | 5.9 / 3.3 / 5.0% | |
| clip size in Unity | 203 / 33 / 45 KB | 439 / 64 / 104 KB | as (a) | 1,372 / 202 / 307 KB | |

| | (b) | (a) | (c) |
|---|---|---|---|
| all 75 clips in Unity | **4.2 MB** (measured, default compression) | about 9 MB (2.2× from the three clips) | about 28 MB (6.7×) |
| the old interactive workflow's baked clips | | | about 387 MB |
| a new character needs | one fit, 93 to 137 s | one fit plus the Humanoid setup | one fit **and all 75 clips re-baked** |

Notes the table needs:

- **(b) in Blender matched (b) in Unity** (limbs 0.0002°, added slide 0.51 / 1.19 / 0.95 cm).
  Unity's default Optimal compression changed the forehand's added slide from 1.16 cm
  (compression off) to 0.84 cm: compression is not where the error lives.
- **Naive per-clip retargeting starts 55 to 72° off** on the limbs (arm pose 77 to 102%): no
  reference frame and the hand aimed at its tail. With a reference frame (the pack's skeleton posed
  into the character's A-pose), aim off and the curveless bones filled with the file's defaults,
  route (c) matched (b) in Blender (0.0003°). What remains against (b) in Unity is Unity
  resampling Blender's baked Euler curves, the late-curve difference below, and 6.7× the size.
- **Humanoid on the same skeleton gains nothing and costs accuracy.** The muscle-space round trip
  moved limbs 1.5 to 4.4° and the head 5°, and failed the slide gate on the forehand and smash.
  Foot IK pulled slide back to 1.2 cm and bent the knees 5 to 9° more. Unity's automatic mapping
  got all 22 body bones right but no fingers: an explicit finger map is still needed.
- **Grip error is not a route property.** 5 to 7 cm on every route: proportions, not angles.

## When each route wins

| The situation | Route |
|---|---|
| One pack, one skeleton, supplies the motion; characters have standard proportions | **Fit (b).** Exact, smallest, one step per new character |
| A few extra clips from another skeleton join that library | (b), with each extra clip **converted once, offline**, to the pack's skeleton (below) |
| Clips from many skeletons, none dominant | (c) retarget onto the character's rig, or Auto-Rig Pro (`reference/arp-route.md`) |
| A custom body: short limbs, ears, a tail | (c) onto the rig `blender-character-rig` builds |
| The same clip must play on bodies with different skeletons, or the game needs Humanoid-only features (muscle-space IK, body-part masks by humanoid part) | (a), measured on the real clip first (`unity-rigged-character` → `reference/unity-import.md` §1) |

## Converting a clip from another skeleton once

Four stock jogs from a different skeleton were converted to the pack's skeleton offline, in
Blender headless, gated and written as FBX with the pack's structure, then imported like any pack
clip. What made them pass every gate (limb direction p95 0.0001°, one open loop 2.05°):

- **Scale by leg length** (thigh + shin; 1.0817), not hip height: the two skeletons put the hip
  joint 4 cm below and 7 cm above the thighs, so the hip-height ratio said 0.96.
- **Limbs by direction, the rest by rotation from rest.** Thighs, shins, upper arms and forearms
  copy the source's world directions; hip, spine, neck, head, clavicles, hands, feet and toes copy
  each bone's rotation away from its own rest, because the joint layouts differ by up to 31° and
  matching their directions tilts the pelvis and pitches the feet off flat.
- **The hip gets a constant speed plus a small repeating offset** (1.5 to 3.8 cm), fitted so the
  stance toe stays still in every plant: a constant speed alone left 1.8 to 2.5 cm of toe drift.
- **An open source loop is spread half backward, half forward per bone** (up to 8.2° on one hand).
- **The held prop is a constraint on the source.** An empty-hand wrist drove the pack's prop into
  the face (5.1 cm deep); the wrist was held at the pack's average running grip instead, a choice
  logged with a switch to restore the source wrist.
- **Prove the exporter first:** a pack clip sent through the same writer re-imported identical.

## Clip-file behaviour that decides a route

Measured on the pack; check any pack the same way before choosing.

| Behaviour | Consequence | Handle it |
|---|---|---|
| **Late-starting curves.** Keyframe reduction made some curves start late: 44, 26, 46 frames into three clips | before a curve's first key **Unity holds the first key; Blender's FBX importer uses the node's static value**. One idle's frame 0 differed by 1.2 m. Every clip baked in Blender carries Blender's reading | play the purchased files in Unity (route b); a measurement taken in Blender over a clip's opening frames is re-checked in Unity; a test asserts no late curve on the chain that matters (27 clips had one, none on the racket arm) |
| **Bones with no curve at all** (reduction removed a constant curve) | on the pack's body they hold that file's node defaults (a head 8.7° off, a hand 72° off); on another model they hold **that model's** defaults | write the file's defaults as constant curves at import (`unity-rigged-character` → `reference/shared-skeleton-generic.md`); route (c) fills them before baking; Humanoid samples the whole pose and does not need it |
| **Root node names vary**: 63 clips one name, 7 and 8 others | Generic binds by path, so those clips bind nothing | rename the path prefix at import (RemapRoot) |
| **Stray translation curves** on a few non-root bones (2 to 4 keys, under 1e-4 cm) | they replace the character's bone lengths with the pack's | strip every position and scale curve except the root bone's at import |
| **No-root variant had no translation at all**, the hip's height included | the hip is pinned at about 1.0 m; feet float in a crouch (0.28 m) and a kneel (0.55 m) | take the standard variant; its hip height varies 2 to 50 cm per clip; horizontal hip travel goes to the game's planner |
| A standard clip's first frames jump (up to 9 frames) | a root that teleports | trim or skip them before using root motion |
