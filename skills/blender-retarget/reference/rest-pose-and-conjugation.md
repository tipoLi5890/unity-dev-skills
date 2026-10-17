# Retargeting: rest poses and rotation conjugation

> Part of the `blender-retarget` skill. How a `brt_*` module is called and what every `run`
> returns are in `SKILL.md`.

A keyed bone rotation is relative to that bone's rest orientation. Two skeletons with different
rests give the same four numbers two different meanings, so copying channels moves the wrong
way. `brt_retarget` converts each mapped bone's rotation from the source frame into the target
frame by conjugation, writes it as a new action on the target or into an action that already
exists, and gates the result. Its scope is the rotation of mapped bones only: location and scale
are not read or written, and every result says `translation: "not retargeted"` (with
`translation_keyed` naming mapped source bones whose clip moves them).

## Why a clip goes wrong between two skeletons

| Symptom | Cause | Fix |
|---|---|---|
| Arms flare out or cross the chest in every frame | the rests differ: a T-pose rig's upper arm rests level, an A-pose target's rests angled down; the same local rotation lands elsewhere | `reference_frame` on a frame where the source stands in the target's rest pose (below), or redefine the source rest before baking (`reference/arp-route.md`); never one fixed shoulder offset applied to every clip |
| The arm ignores its baked rotation and follows a hand target | the arm chain is in IK while the clip was baked onto FK controls | key the IK/FK switch in every action: the mode is animation data, not a rig setting |
| Palm folds, fingers tear the mesh | hand and finger bones fitted badly: the rest tail does not follow the real palm, so any large rotation shears the skin | leave them out of the map; convert only bones whose rest frame you have checked |
| Wrist frozen while the forearm moves | the hand was left out of the map (right for a first pass) | convert that one bone once the chain above it is right: into the same action with `into_action`, the body map as `reference_map` (below) |
| Nearly a full turn on a single frame | quaternion sign not kept continuous | sign continuity, below |

## The frame conversion

All orientations are world-space quaternions: the rig's world rotation × the bone's
`matrix_local` rotation. With both rigs unrotated that is armature space.

- `T`: the target bone's rest orientation, as above.
- `S`: the **source reference orientation**: the source bone's rest orientation as it would be
  with the source skeleton laid into the target's rest pose (rebuilt in the next section).
- `q_source`: the source bone's keyed rotation at one frame (its pose basis, relative to rest).

```text
K        = inverse(target_rest_orientation) × source_reference_orientation   # inverse(T) × S
q_target = K × q_source × inverse(K)
```

Why it holds: at the matched rest, the source key turns the bone by the world-space delta
`S × q_source × inverse(S)`. The target key must produce the same delta,
`T × q_target × inverse(T)`. Solve for `q_target` and the second line follows. `K` is constant
for one bone and one source/target pair: it is computed once per mapped bone, before any key is
read, and applied to every frame.

Three consequences decide how it is used:

- **It converts the local basis**, so it reproduces motion relative to the parent. A mapped bone
  is right only under a converted parent. Map from the root outward.
- **Conjugation keeps a rotation's angle.** The angle between two consecutive keys is the same on
  the target as on the source, so a speed check on the output only re-measures the source: it
  cannot catch a wrong map (left and right swapped passes it), and a correct fast swing (a wrist
  turning tens of degrees a frame) would fail it. `max_step` (the target's largest step, with
  `max_step_at`) and `source_max_step` are reported, not gated.
- **Only mapped bones are written.** `map` is `{target_bone: source_bone}`; a source bone mapped
  to two targets raises. The reference walk below covers every source bone, so a bone the map
  skips carries its parent's alignment down to its children, but it gets no curves of its own.

## Rebuilding the source reference orientation

A pass over rest data only; nothing is evaluated frame by frame.

1. Read each source bone's rest orientation `R[b]` (`matrix_local` as a quaternion) and the
   source object's world rotation `W`.
2. Walk parents before children (from the root bones through `children`; list order is not
   relied on):
   - root bone: `ref[b] = W × R[b]`
   - child: `ref[b] = ref[parent] × inverse(R[parent]) × R[b]`: the parent's corrected
     orientation, then the child's own rest offset from that parent.
   - with `reference_frame`: then `ref[b] = ref[b] × q_ref[b]`, the bone's pose at that frame.
3. If `b` is aimed at target bone `t`, take `t`'s rest direction in world,
   `d = target_world_rotation × (tail_local − head_local)`, and swing `ref[b]` by the shortest arc
   from its own bone axis (`ref[b] × (0, 1, 0)`: Blender bones point along local Y) to `d`:
   `ref[b] = rotation_difference(ref[b] × Y, d) × ref[b]`. Skipped when `d` is near zero length.
   The aimed bones are `reference_map` (`{target: source}`, default `map`) less `no_aim` (target
   bones); the written bones are `map`. So one bone can be written under a walk that aims the
   whole body, and a written bone whose fitted tail is off the real direction (a hand) can be
   left unaimed.
4. Normalise every `ref[b]`. `S` is `ref` of the source bone being converted.

The shortest arc fixes the bone's direction, not its roll; the roll is carried from the source's
own rest. Two rests that differ by a twist about the bone (palms down in one, palms forward in the
other) show as a constant twist at every frame. Check frame 1 of the converted clip beside the
source at frame 1 before widening.

**`reference_frame`** names a frame of the clip where the source stands in the target's rest pose.
The walk takes the source's pose at that frame as its rest (step 2), and every key is rebased on
it, `q_source ← inverse(q_ref) × q_source`, so the target sits exactly at rest on that frame.
Without it (default None) the source's own rest is the reference: the target is at rest only where
the source is at its rest, and on the frame where the source matches the target's rest pose the
target is off rest. A rest that differs in pose (T-pose against A-pose) is then only swung into
line by direction, and the arms keep the difference in every frame.

## Writing the keys

Per integer frame over `frame_range` (default the source action's own range):

1. Read the source bone's rotation from the clip's F-curves (`fcurve.evaluate`), never by stepping
   the scene: rotation only, no constraints, full rotation inheritance. A bone in `QUATERNION`,
   any Euler order or `AXIS_ANGLE` mode is converted to a quaternion per frame; a channel without
   a curve takes its rest value; a mapped bone with no curve at all for its mode raises. The
   source keys are made sign-continuous too, so `source_max_step` is a true angle.
2. With `reference_frame`, rebase: `q_source ← inverse(q_ref) × q_source`.
3. `q_target = K × q_source × inverse(K)`, normalised.
4. **Sign continuity**: the first key gets `w ≥ 0`; after that, if `dot(q_target, previous) < 0`,
   negate `q_target`. `q` and `−q` are the same rotation, but interpolating between them takes the
   long way round: a one-frame spin.

Then on the target, one of two ways:

- By default a **new action**, `output_action` (default `<target>_<source_action>`),
  with fake user on, assigned to the target through its slot. A name that is already taken
  refuses the call: `retarget.output_is_new` fails, `message` says why, nothing changes.
  `overwrite_action: True` replaces it: the new action is built under a free name and the old one
  is removed (and unlinked from whatever played it) only once the new one exists.
- With **`into_action: NAME`**, into an action that already exists, such as the one an Auto-Rig
  Pro retarget baked with the hands excluded (`reference/arp-route.md`). Pass the bake's body
  map as `reference_map` and the wrist alone as `map`: the walk then aims the root, spine, shoulder,
  arm and forearm into the target's rest, and not the hand. With `map` alone nothing above the
  wrist is aimed and the hand is swung onto its fitted tail, which gives another `K`. The curves
  go on the slot the target plays it through, else the slot named after the target, else its
  first slot; what the target plays is not changed. A mapped bone that already has a rotation curve there (quaternion,
  Euler or axis-angle) refuses the call: `retarget.channels_free` fails, `existing` lists them,
  nothing changes. `replace: True` removes those bones' rotation curves first (`curves_removed`).
  Every other curve keeps its keys exactly. `frame_range` defaults to that action's range.
  `output_action` and `overwrite_action` are refused beside it.
- Each mapped target pose bone is set to `QUATERNION` mode; this is not undone.
- Four curves per mapped bone, `rotation_quaternion` indices 0–3, one key per frame, linear
  interpolation. Keys this dense need no easing; Bezier handles between them overshoot.
- One custom property, `brt_retarget`, holds JSON: source, target, source action,
  `reference_frame`, the map, `K` per bone, `aim` (per bone, the bones aimed for its `K`) and
  `rest_hash` (both rests and the maps), so a later
  check can tell which conversion the action carries. A second `into_action` call from the same
  source, source action and reference frame merges its bones into the record; one from another
  conversion replaces it, with a warning.

Blender 5 actions are layered: curves live in layers → strips → channelbags, one channelbag per
slot, and `action.fcurves` does not exist. `brt_common.action_slot_fcurves` reads them,
`brt_common.ensure_fcurve` writes them, and `brt_common.assign_slot` sets `animation_data.action`
and then `action_slot`. The source is read through the slot it plays, else the slot named after
it, else its first slot.

## One bone, then widen

1. One bone, one clip. Convert, read the gates, look at stills.
2. The same bone across every clip.
3. The next bone, repeating 1 and 2.

Never widen a failing conversion: a wrong `K` is wrong in the same way on every clip, so a batch
only multiplies one error. A rerun onto a name kept from the last attempt needs
`overwrite_action: True`; without it the call refuses rather than leave two takes side by side.

## Bake and re-verify

| Gate | Reads | A failure means |
|---|---|---|
| `retarget.output_is_new` | new action: `output_action` was free, or `overwrite_action` was given | an action of that name exists; the call refused and changed nothing |
| `retarget.channels_free` | `into_action`: no mapped bone already has a rotation curve there, or `replace` was given | the call refused and changed nothing; `existing` lists the curves |
| `retarget.finite_keys` | no NaN or infinite value in the curves written | a zero-length quaternion was normalised, or a source channel is broken at some frame |
| `retarget.first_equals_last` | first and last key of every bone agree within 1e-4 rad | a loop whose seam pops. Emitted only with `loop: True`: a one-shot such as `GateLatchSwing` would fail it legitimately |

Reported beside the gates: `max_step` and `max_step_at` (the bone and frame), equal to
`source_max_step` by construction. A value near π is a lost sign; otherwise it says how fast the
clip moves, not whether the map is right. Numbers prove the channels are sane, not that the motion
is right. Then look: stills front and side at the first, middle and last frame, the target beside
the source.

## Mapping tables

Start from the remap preset the add-on provides for the nearest stock naming, and rename the source
column for each source skeleton. **Map by role in the chain, not by name**: the same word means
different bones in different skeletons. Left side shown; the right mirrors it with `.r`. In
`brt_retarget`'s `map` the target bone is the key and the source bone the value.

| Role | Target control | T-pose rig | A-pose rig |
|---|---|---|---|
| pelvis | `c_root_master.x` | `hips` | `Pelvis` |
| lower spine | `c_spine_01.x` | `spine_01` | `SpineLow` |
| middle spine | `c_spine_02.x` | `spine_02` | `SpineMid` |
| upper spine | `c_spine_03.x` | `spine_03` | `SpineTop` |
| neck, head | `c_neck.x`, `c_head.x` | `neck`, `head` | `Neck`, `Head` |
| clavicle | `c_shoulder.l` | `shoulder_l` | `L_Collar` |
| upper arm | `c_arm_fk.l` | `arm_l` | `L_Shoulder` |
| forearm | `c_forearm_fk.l` | `forearm_l` | `L_Elbow` |
| thigh, shin | `c_thigh_fk.l`, `c_leg_fk.l` | `upleg_l`, `leg_l` | `L_Hip`, `L_Knee` |
| foot, toe | `c_foot_ik.l`, `c_toes_ik.l` | `foot_l`, `toe_l` | `L_Ankle`, `L_Toe` |

`shoulder_l` is a clavicle; `L_Shoulder` is an upper arm. Mapped by name, the arm would follow the
collarbone. Control names follow the add-on's naming and may change with its version; confirm
them in your rig.

- Hand and finger bones stay out of the first map. Add one only after its rest frame is checked
  (the hand's rest tail along the real palm length).
- One map file per source skeleton, kept beside the clip manifest.
- Confirm the preset file's layout on your add-on version before editing it as text. Safer: import
  the preset, rename the source entries in the loaded bone list, then save that list as a config.

## K belongs to one pair of rests

`K` depends only on the two rests and the mapping above the bone. Recompute it when:

- either rest pose changes: a re-run of Match, a re-bind that moves bones, an edited roll;
- the source skeleton changes, even to another clip family with the same bone names;
- the aimed bones above it change (`reference_map`, `no_aim`: the alignment walk reads them).

**Never copy `K`, or converted curves, from another character** or from before a rest change.
Compare the `rest_hash` stored in the action's `brt_retarget` property before reusing anything.

## Out of scope

- **Fingers.** Many short bones with the least reliable fitted rests; converting them tears the
  mesh before it adds anything. A closed hand is a shape, not a conversion.
- **The other hand.** The same procedure applies per side, but it needs its own `K` and its own
  check. Do not mirror `K` across sides unless the two rests are exact mirrors, and do not assume
  they are.
- **Translation and root motion.** Only rotations are converted; `translation: "not retargeted"`
  in every result. Travel through space is chosen with the clip variant (in place or no-root,
  `reference/clip-sources.md`) and owned by the game; a hips height or travel the target needs
  comes from the add-on's bake or another tool.
- **Contact.** A converted wrist does not make the hand reach a prop. A prop carried on the hand is
  checked for drift across the library (`brt_drift`, `drift.max_drift` and `drift.max_rotation`); whether it touches
  anything is a separate check.
