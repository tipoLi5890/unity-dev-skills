# The mesh gate, the deformation gate and the spring-chain gates

> Part of the `character-autorig` skill. `scripts/mesh_check.py` runs before any marker;
> `scripts/deform_gate.py` runs on the bound result; `scripts/secondary_chains.py` gates the
> spring chains it adds. Each prints one JSON object and exits 0 pass, 2 a gate failed, 1 refused
> input.

## mesh_check.py — is the mesh riggable?

```bash
python3 scripts/mesh_check.py Runner.glb --out rig/runner.mesh.json
python3 scripts/mesh_check.py Runner.obj --up z      # a file that is already +Z up
python3 scripts/mesh_check.py --selftest
```

It reads GLB, glTF (with external or embedded buffers) and OBJ, every node's mesh with its
transform, and turns +Y up into +Z up as Blender does. Draco- or meshopt-compressed files and
sparse accessors are refused: decompress them, or export an OBJ from Blender.

| Gate | Measures | Default | Fails on |
|---|---|---|---|
| `legs_separated` | share of the cuts in the leg band (0.12–0.38 H) holding a part wholly left of the midline, one wholly right, and none across it | ≥ 0.9 | both legs in one tube; a long coat, skirt or robe (take `--body skirt`, below) |
| `arms_separated` | longest run of consecutive cuts in the arm band (0.50–0.74 H) with a part wholly outside the torso on both sides | ≥ 0.05 H | an arm glued along the ribs, arms held against the body, a T-pose |
| `double_shell` | share of the surface with another sheet parallel to it (normals within 60°) within 0.006 H along its normal, facing the same way or facing it from in front, from 6000 area-weighted samples | ≤ 0.25 | an outer skin over a same-facing inner twin (near 0.5 or above), two skins pressed together |

- **Bands are fractions of the height.** A body with unusual proportions moves them:
  `--leg-band 0.10,0.32` for short legs. Move a band once for the body type, never to let one mesh
  through.
- **An inward-facing inner shell is kept.** A sheet behind the surface facing the other way, back
  to back with it, is a thin wall: the inward-facing inner shell some image-to-3D generators write
  on every mesh, a cloth flap, an ear. It is reported as `double_shell.inner_shell` (a share, often
  0.5–0.7 for such a generator: both walls count, so the shell itself is about half) and not gated: Auto-Rig Pro binds it with the skin, and
  `deform_gate.py` measures the outward-facing side only. Do not delete it before rigging.
- **The double-shell gap** stays below a finger's thickness (about 1 cm on a 1.7 m body), so limbs
  and fingers do not count; ears and cloth flaps do, and stay a small share. A hollow mesh with a
  thick wall (gap above 0.006 H) passes; Auto-Rig Pro's voxel bind fills it either way.
- The report also gives `crotch_h`, `legs.first_fused_h` (the lowest cut where the legs read as
  one) and `arms.armpit_h`, to say where to look in the views.

**On failure, regenerate; do not rig.** A fused limb cannot be fixed by markers or weights: the
skin between the arm and the ribs stretches with every arm swing. Go back to the views (the arms
30–60° down and clear, a gap between the legs) or to the 3D generation. A long garment is not a
fused limb: when the report carries `skirt_hint`, rig it on the skirt route.

**The skirt route (`--body skirt`)** — a long coat, a skirt, a robe: one part across the midline
from a hem at 0.22–0.42 H up, the legs apart under it. Chosen by a person (`autorig.py all
--body skirt`); the default body reports `skirt_hint` (the hem's height, the hem at least 1.15 x
the legs' span) instead of reading the hem as a crotch.

| Gate | Measures | Default | Fails on |
|---|---|---|---|
| `legs_separated` | as above, in the band from 0.12 H up to 0.02 H under the hem | ≥ 0.9 | legs fused under the hem |
| `skirt_hem` | a hem was found, and the legs show under it for ≥ 0.08 H of the band | found | a floor-length robe (no leg to mark: the hand-built route) |
| `double_shell` | as above, over the surface outside the skirt zone (the hem to 0.55 H) | ≤ 0.25 | a twin shell on the body |

The skirt zone's own share is reported as `skirt.layer`, not gated: a coat over trousers is two
sheets there by design (a knee-length greatcoat reads about 0.38 inside the zone, 0.16 outside).
The markers then follow the legs inside the skirt (`reference/markers.md`), `autorig.py` binds
the skirt off the thighs' seam, and the deform gate reads its tear (`deform.skirt_tear`, below).

**The chibi route (`--body chibi`)** — a big head on short limbs, chosen by a person at G0. The
bands follow the body type, the limits do not: the crotch is searched from 0.10 H, `legs_separated`
reads 0.06 H up to 0.02 H under it, `arms_separated` reads 0.35–0.65 H (the hands of a short arm
hang near 0.35–0.45 H, the armpit near 0.55 H). The report adds `chibi` {crotch_h, leg_band,
arm_band}. Fused legs or arms still fail it.

## deform_gate.py — six extremes

```bash
blender -b -P scripts/deform_gate.py -- --fbx export/Runner.fbx --map rig/runner.contract.json \
  --render rig/poses/ --out rig/runner.deform.json
blender -b rig/Runner_hand.blend -P scripts/deform_gate.py -- --armature RunnerRig --mesh Runner
blender -b --factory-startup -P scripts/deform_gate.py -- --selftest
```

Pose a plain skeleton. An exported FBX is one; so is a hand-built rig. Auto-Rig Pro's own rig
drives its deform bones through constraints from its controls, so a rotation set on a deform bone
there does nothing: gate the export.

**Spring chains do not change a reading.** Blender's FBX importer gives each bone the mean
distance to its child bones as its length (its parent's when it has none), along the bone's own
axis. A `cc_` chain under the Head or a thigh therefore lengthens that bone and every childless
bone below it. The gate reads each tail where the importer puts it without the `cc_` children
(`chain_free_tails`, the same rule `brt_arp` uses for skeleton/1 tails), so a rig reads the same
with its chains as without; a rig built in Blender, whose lengths are not the importer's, keeps
its own tails.

**The poses** are rotations in world axes, each relative to its parent, read off the rest
skeleton, so they fit any arm angle and hand orientation:

| Pose | Bones turned |
|---|---|
| `arms_up` | both upper arms to 20° from vertical; the shoulders 15° after them |
| `deep_squat` | thighs 100° forward, knees 120°, spine and chest 10° forward each |
| `torso_twist` | spine, chest and upper chest 20° each about their own axis (60° in all) |
| `fist` | each finger phalanx 60° toward the palm, the thumb's 30°; skipped without finger bones |
| `leg_raise` | the left thigh 90° forward, knee straight |
| `elbow_120` | both forearms 120° toward the front |
| `mitten` | only when named (autorig.py names it instead of `fist` on a `fixed` hand): Middle1–3 40° toward the palm, the thumb's 20°, the other fingers at rest; adds `deform.mitten_tear` |
| `jaw_open` | the Jaw 20° down; only when named (`--poses all,jaw_open`), for a rig with a face; the self-intersection gate covers it, the volume gate does not |

Each pose is sampled at `--steps` fractions (default 2: half and full); `--poses` picks a subset.

**`--body chibi`** (`autorig.py` passes it when the markers say chibi): `arms_up` stops 45° from
vertical and `elbow_120` bends 90°. Past that a chibi's mitten enters its own head, and a forearm
about twice its radius long meets the upper arm (two limbs of radius r touch r / tan(half the inner
angle) from the hinge, the whole forearm at 120°). Every limit stays; the rig exam's chibi base still
catches each planted fault.

**The outward-facing skin.** Both measures read the skin, not an inner shell behind it. Per
triangle at rest: it *sees out* when a ray from it (its normal and six directions 70° around it)
leaves the mesh, and it is *back to back* when a sheet facing the other way lies right behind it
(within 0.01 H). Seeing out is skin, never overruled (folds and thin fingers see out). Back to back
without seeing out is inner shell. A triangle with neither (the skin farther than 0.01 H behind it,
a crumpled patch) takes the side of its edge neighbours, spread from the known ones; a piece no
triangle of which sees out is hidden inside and left out. Then every triangle that does not see out
takes its neighbours' majority, so the split follows the sheets, not single rays. Neighbours share
an edge of welded vertices (vertices at one position are one, so UV seams do not cut a sheet).
A single skin keeps every triangle but what is hidden inside another part. The report gives
`outward_triangles` and `inward_triangles`: on a mesh with an inner shell, about half. Counted
whole, an inner shell cancels the skin's cones (every joint reads as not measured) and crosses the
skin as it folds (the intersection ratio inflates).

`mesh_check.py`'s `double_shell.inner_shell` counts both walls of the thin wall (each sees the
other back to back) within its smaller gap, so the inner shell's own share is about half of it, or
more where the shell stands farther off; compare `inward_triangles` with that half, not the whole.

**Volume loss** per rotated joint: the skin triangles within half the shorter adjoining span of the
joint at rest (joint to joint, so a limb split into twist and stretch bones counts whole), and the volume they wrap, as the sum of cones from their vertex centroid,
(a − c) · ((b − c) × (d − c)) / 6. loss = 1 − posed / rest. A rigid turn keeps it; a blend that
averages two rotations shrinks the skin toward the joint (a 50/50 blend at a 120° elbow loses
0.75). Gated, `deform.volume_loss_max` ≤ 0.35, at the elbows, knees, wrists, ankles and spine
joints, where the patch is a tube around the joint. Shoulders and hips are reported as
`ball_joint_loss_max` and not gated: their patch mixes torso and limb, and an arm overhead reads
as a loss there for any skin. A joint whose patch does not wrap around it, or holds fewer than 8
triangles, is listed in `joints_not_measured`. Two fallbacks read an elbow or knee that would
otherwise be lost, and change no patch that already reads: one with fewer than 8 triangles (a short
thick limb whose skin lies past half its span) takes 1.25 x the distance to the nearest skin instead,
when that skin sits around the joint (an opening at the joint leaves it along the limb, still unmeasured);
one that does not wrap (a hem across a short leg's knee, its lining facing in) keeps the triangles
within 1.3 x the limb's own radius from the bone's axis (the median of the quarter nearest the
joint), and is read when those wrap. An elbow or knee there fails
`deform.joints_measured` (below); for the other joints, check that list before reading a pass: on a torso
wider than half a spine bone the spine joints have no triangles inside the patch, so `torso_twist`
and the spine in `deep_squat` are judged by the self-intersection gate and their renders only.
A gain (a negative loss, common at a knee bent 120°) is reported and not gated.

**New self-intersections** per sample: outward triangles that cross another outward triangle
sharing no vertex with it (vertices welded by position: a glTF or FBX splits them at UV seams, and
two triangles meeting at a seam touch, they do not cross) in the pose and did not at rest (Blender's BVH overlap), divided by the
outward triangles that moved (a vertex more than 0.1 % of the height). A double shell or an accessory that already
crosses the body at rest is not counted again. Gated, `deform.self_intersection_p95` ≤ 0.08 over
every sample. The denominator is the whole moved region, so a seam at one joint is diluted: a hard
skin (each vertex following only its heaviest bone) can pass this gate on a normally proportioned
body. The elbow volume loss and the `elbow_120` and `deep_squat` renders are what catch it; look at
them before reading a pass.

**`deform.joints_measured`**: every hinge joint a requested pose bends (`LowerArm.*` in
`elbow_120`, `LowerLeg.*` in `deep_squat`) was measured by the volume gate in at least one pose;
the value lists the ones never measured. A hinge the volume gate cannot read is a failure, not a
pass at 0.0: an opening at the joint, too few triangles there, or a mesh that faces inward.

**`deform.skirt_tear`** (with `--skirt MARKERS`, the skirt route's markers): on the skirt's own
skin (the hem band up to the hip + 0.06 H, inside the body's box at each height, off the legs'
followed loops: `arp_markers.skirt_region`), every outward edge's posed length over its rest length
in every sample; the share of those edges stretched past 3 x (`--tear-stretch`) ≤ 0.002
(`--tear-max`). A coat skinned by the bind alone parts between the thighs or rides one thigh in
`deep_squat` and `leg_raise`: a few edges stretch five to fifty times while volume and
self-intersection stay green. A skirt blended across the thighs spreads its stretch (p99 near 1.5,
no edge past 3). The leg joints' volume patches leave the skirt's skin out (it is not the knee's).

**`deform.poses`**: every requested pose was applied. Under `--poses all` the fist may be skipped on a rig
without finger bones; named in `--poses`, a skipped fist fails, and so does `jaw_open` when the map
names no Jaw. `autorig.py` names `jaw_open` when the markers carry the face and the contract maps a
Jaw.

**A mitten.** Auto-Rig Pro binds its four finger chains to a mitten too, one strip each, and a
mitten folds into itself in a fist. When `arp_markers.py` reported `fingers.mode` `fixed`,
`autorig.py` folds the chains onto Middle (`mitten_bind`) and gates
`--poses arms_up,deep_squat,torso_twist,leg_raise,elbow_120,mitten`.

**`deform.mitten_tear`** (when the `mitten` pose ran): the skirt tear's reading on the hands' own
skin (vertices Hand and the finger bones hold ≥ 0.5 of), same limits. A mitten left on four strips
opens between them when only Middle bends (about 1 % of its edges past 3 x, the worst near 5 x);
folded onto one chain it bends whole (no edge past 2 x).

**Reading a failure.** The report names the pose and joint of the worst loss and the pose of the
worst intersection ratio. `--render` writes a front and a side picture per pose of the gated mesh
alone; look at that pose first.

| Symptom | Likely cause | Fix |
|---|---|---|
| loss at an elbow or knee | the blend across the joint is wide, or the joint marker sits off the crease | move the marker (`arp_markers.py --adjust`) and rig again, or repair weights at that joint and re-export (`reference/arp-pipeline.md`, the elbow and knee repair) |
| loss at the waist in `torso_twist` | the whole torso follows one spine bone, or a 50/50 blend over the full length | spread the weights along the three spine bones |
| intersections in `elbow_120` or `fist` | a hard seam: the skin follows one bone rigidly; in `fist` on a `fingers.mode` `fixed` hand, the mitten itself | smooth the weights over the joint; for the mitten, `mitten` replaces `fist` in `--poses` |
| intersections in `arms_up` or `elbow_120` on a big-headed, short-limbed body | the mittens enter the head; a thick forearm meets the upper arm | the chibi route (`--body chibi`), chosen at G0 |
| `deform.mitten_tear` fails | the mitten rides four finger chains, one strip each | `autorig.py contract` (its `mitten_bind`) |
| intersections in `deep_squat` | thighs crossing the belly or calves into thighs | hip markers too low or too far in; a soft belly touching the thighs is expected, so never loosen the limit for one character |
| `deform.joints_measured` names an elbow or knee | the patch around the joint has fewer than 8 outward triangles or does not wrap it: an opening, a decimated joint, flipped normals | look at the mesh there (`mesh_check.py`, a picture); fix the mesh, never drop the pose |
| a whole limb moves with the wrong pose | weights on the wrong side's bone | rebind; check `markers.symmetry` and the sides gate of the contract |
| `deform.cross_side_weight` fails | a limb's skin holds weight on the other side's limb bones | the repair ladder moves it to the mirrored bones past the band (`reference/arp-pipeline.md`); still failing: rebind |
| `deform.hinge_blended` fails | a hard seam: no vertex at that elbow or knee shares the two bones | rebind, or smooth the weights over the joint |
| `deform.skirt_tear` fails | the skirt follows one thigh on each side, or Hips beside a thigh: a seam in its weights | `autorig.py contract` (its `skirt_bind`) on the skirt route; on the chained rig, chains that take a thigh's weight without hanging from it |

**Two readings of the bind at rest** (no pose is needed, so a defect no pose bends is still seen; both
are in the report's `skin`). A bone belongs to the contract bone it is mapped to, or else to the first
mapped bone up its parent chain (a twist twin to its limb bone); `cc_` chain bones belong to none.

- **`deform.cross_side_weight`**: on the skin farther than half the hip half-width from the Hips, the
  share of each side's limb weight (UpperArm to the fingers, UpperLeg to Toes, and the bones below them;
  not the Shoulder) held by the other side's limb bones; the larger side's share ≤ 0.05
  (`--cross-side-max`), and no vertex there held at least half by the other side (`held` 0). A bind
  leaks nothing past the crotch; a shoe sole bound to the other foot is a small share of the side
  but still tears when the legs part, hence the count.
- **`deform.hinge_blended`**: at each elbow and knee, within the volume patch's radius, the share of
  vertices that the upper and the lower bone each hold at least 0.1 of; the least ≥ 0.03
  (`--hinge-blend-min`). A rigid skin reads 0 there, though it keeps its volume and its seam can stay
  under the self-intersection limit on a slim body.

**What the gates miss.** `scripts/rig_exam.py faults` plants known defects in a good rig
(`reference/rig-exam.md`) and lists which gate catches each. Run the exam's volume check before you
change the patch or the limit, and the faults before you change either reading's limit.

The selftest builds a metaball runner, a contract skeleton from its markers, and four skins:
distance-based weights smoothed over the joints pass; nearest-bone-only weights fail the
self-intersection gate and `deform.hinge_blended`; a 50/50 blend around the elbows fails the volume
gate; half the left leg's weight on the right leg fails `deform.cross_side_weight`. A copy of the good
skin with an inward-facing twin 4 mm inside it, on the same weights, passes with every hinge
measured and the single skin's p95 (counted whole, every hinge goes unmeasured and
`deform.joints_measured` fails); the good skin split along a UV seam keeps no rest crossings and
the single skin's p95 (the raw vertex test reports the seam as crossing); an opening at the left
elbow fails `deform.joints_measured`. On mesh_check's tube body, four thin fingers held together
keep every triangle, and an inner shell standing farther than 0.01 H off the legs is still left out.

## secondary_chains.py — spring chains on a fused shell

```bash
blender -b rig/Runner_arp.blend -P scripts/secondary_chains.py -- --mesh Runner \
  --map rig/runner.contract.json --fbx secondary/Runner.fbx --out secondary/Runner.secondary.json
blender -b --factory-startup -P scripts/secondary_chains.py -- --selftest
```

What it finds and how it weights is in `reference/secondary-chains.md`. Its gate/1 report:

| Gate | Passes when |
|---|---|
| `secondary.chains_placed` | every `--require` kind got a chain (a hem: four or more); `[]` without `--require`, so a body with nothing loose passes with no chain |
| `secondary.weighted_vertices` | every weighted chain bone holds at least 50 vertices |
| `secondary.max_influences` | at most 4 deform weights on every vertex (the exporter's own limit pass then trims nothing) |
| `secondary.weight_sum` | every vertex's deform weights sum to 1 (within 1e-4) |
| `secondary.body_weights_unchanged` | outside every chain's region, every weight is exactly what the bind left |
| `secondary.tip_unweighted` | no `cc_<chain>_end` tip carries a weight |
| `secondary.leak` | each chain's bones turned 25°: no vertex outside its region moves more than 1 mm |
| `secondary.rest_penetration` | no chain joint below the root starts inside a collider of its group, after shrinking (`colliders.shrunk`, `colliders.dropped`) |
| `secondary.export_bones` | with `--fbx`: every `cc_` bone is in the re-imported FBX, its parent kept |
| `secondary.export_weights` | with `--fbx`: every re-imported vertex weighted to a `cc_` bone lies in that chain's region and its weight matches within 0.01 |

A separate hair object (a character in parts) counts in every gate above with the body;
`detect.dropped_small` lists hair spikes left rigid for want of 50 vertices a bone. The hair's own
bind, `parts_bind` (`parts.transform_residual`, `parts.hair_bound`, then the `arp.export_*` gates
of its re-export), and the eyeballs' `eyes_bind` (`eyes.*`), are gated in `blender-character-rig` →
`reference/part-assembly.md`.

With `--fbx` the report also carries `brt_arp`'s own `arp.export_*` gates. Then `contract_map.py`
on the new skeleton (the `cc_` bones are extras) and `deform_gate.py` on the new FBX:
`autorig.py secondary` runs all three and puts the volume reading with and without the chains
side by side in its summary.

| Symptom | Likely cause | Fix |
|---|---|---|
| a chain on a body part that does not hang loose | a bulge or a step that passed the thresholds | `"skip": ["<chain>"]` in the markers file and run again on the rig without chains |
| a loose part without a chain (`detect.found` lacks it) | it sits outside the search windows, or a thin mesh | a marker chain (`reference/secondary-chains.md`) |
| `secondary.leak` or `body_weights_unchanged` fails | a region reaching skin of another part | a smaller `region_radius` for a marker chain, or skip the chain |
| `secondary.rest_penetration` fails | a joint deep inside a body capsule | move the marker chain's joints onto the surface |
| refused: the rig already has `cc_` bones | a second run on the chained rig | run on the rig before the chains (`repair/aN/` or `rig/`) |

