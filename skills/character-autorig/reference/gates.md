# The mesh gate and the deformation gate

> Part of the `character-autorig` skill. `scripts/mesh_check.py` runs before any marker;
> `scripts/deform_gate.py` runs on the bound result. Both print one JSON object and exit 0 pass,
> 2 a gate failed, 1 refused input.

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
| `legs_separated` | share of the cuts in the leg band (0.12–0.38 H) holding a part wholly left of the midline, one wholly right, and none across it | ≥ 0.9 | both legs in one tube, a long skirt or robe |
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
30–60° down and clear, a gap between the legs) or to the 3D generation.

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

Each pose is sampled at `--steps` fractions (default 2: half and full); `--poses` picks a subset.

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

**Volume loss** per rotated joint: the skin triangles within half the shorter adjoining bone of the
joint at rest, and the volume they wrap, as the sum of cones from their vertex centroid,
(a − c) · ((b − c) × (d − c)) / 6. loss = 1 − posed / rest. A rigid turn keeps it; a blend that
averages two rotations shrinks the skin toward the joint (a 50/50 blend at a 120° elbow loses
0.75). Gated, `deform.volume_loss_max` ≤ 0.35, at the elbows, knees, wrists, ankles and spine
joints, where the patch is a tube around the joint. Shoulders and hips are reported as
`ball_joint_loss_max` and not gated: their patch mixes torso and limb, and an arm overhead reads
as a loss there for any skin. A joint whose patch does not wrap around it, or holds fewer than 8
triangles, is listed in `joints_not_measured`. An elbow or knee there fails
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

**`deform.poses`**: every requested pose was applied. Under `--poses all` the fist may be skipped on a rig
without finger bones; named in `--poses`, a skipped fist fails.

**A mitten in a fist.** Auto-Rig Pro binds finger bones to a mitten hand too, and a mitten folds
into itself when its phalanges close, so the fist alone can fail the intersection gate on a sound
bind. When `arp_markers.py` reported `fingers.mode` `fixed`, gate the other five poses:
`--poses arms_up,deep_squat,torso_twist,leg_raise,elbow_120`.

**Reading a failure.** The report names the pose and joint of the worst loss and the pose of the
worst intersection ratio. `--render` writes a front and a side picture per pose of the gated mesh
alone; look at that pose first.

| Symptom | Likely cause | Fix |
|---|---|---|
| loss at an elbow or knee | the blend across the joint is wide, or the joint marker sits off the crease | move the marker (`arp_markers.py --adjust`) and rig again, or repair weights at that joint and re-export (`reference/arp-pipeline.md`, the elbow and knee repair) |
| loss at the waist in `torso_twist` | the whole torso follows one spine bone, or a 50/50 blend over the full length | spread the weights along the three spine bones |
| intersections in `elbow_120` or `fist` | a hard seam: the skin follows one bone rigidly; in `fist` on a `fingers.mode` `fixed` hand, the mitten itself | smooth the weights over the joint; for the mitten, drop `fist` from `--poses` |
| intersections in `deep_squat` | thighs crossing the belly or calves into thighs | hip markers too low or too far in; a soft belly touching the thighs is expected, so never loosen the limit for one character |
| `deform.joints_measured` names an elbow or knee | the patch around the joint has fewer than 8 outward triangles or does not wrap it: an opening, a decimated joint, flipped normals | look at the mesh there (`mesh_check.py`, a picture); fix the mesh, never drop the pose |
| a whole limb moves with the wrong pose | weights on the wrong side's bone | rebind; check `markers.symmetry` and the sides gate of the contract |

The selftest builds a metaball runner, a contract skeleton from its markers, and three skins:
distance-based weights smoothed over the joints pass; nearest-bone-only weights fail the
self-intersection gate; a 50/50 blend around the elbows fails the volume gate. A copy of the good
skin with an inward-facing twin 4 mm inside it, on the same weights, passes with every hinge
measured and the single skin's p95 (counted whole, every hinge goes unmeasured and
`deform.joints_measured` fails); the good skin split along a UV seam keeps no rest crossings and
the single skin's p95 (the raw vertex test reports the seam as crossing); an opening at the left
elbow fails `deform.joints_measured`. On mesh_check's tube body, four thin fingers held together
keep every triangle, and an inner shell standing farther than 0.01 H off the legs is still left out.
