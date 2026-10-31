# The rig exam — the automatic rig scored against bodies whose joints are known

> Part of the `character-autorig` skill. The stages it runs are in `SKILL.md`; what each gate measures
> is in `reference/gates.md`. `scripts/rig_exam.py` drives the exam and scores it;
> `scripts/rig_exam_blender.py` builds the bodies and the weight faults inside Blender.

A change to the markers, the pipeline or a gate is scored before it ships. The exam rigs a fixed cast
of procedural bodies whose skeletons are known, compares every marker and exported joint with the
truth, plants known defects in a good rig, and checks that the gates fail each one. Run it on the
current version first and keep the report as the baseline. Then make the change and run the exam
again. Compare the two reports: the change should improve scores or catch more faults, and it should
not add a false pass.

## Commands

```bash
python3 scripts/rig_exam.py build exam/                      # the cast: exam/cast/NAME.glb + NAME.truth.json
python3 scripts/rig_exam.py run exam/ [--only standard,heavy] [--threads 4]
python3 scripts/rig_exam.py faults exam/ --base standard     # known defects on the standard body's rig
python3 scripts/rig_exam.py reference exam/ runner --glb Runner.glb --markers rig/Runner.markers.json \
  --fbx repair/Runner.fbx --contract rig/Runner.contract.json
python3 scripts/rig_exam.py faults exam/ --base runner --fbx exam/refs/runner/accepted.fbx \
  --contract exam/refs/runner/accepted.contract.json
python3 scripts/rig_exam.py score exam/ [--tol 0.04] [--volume-max 0.35]   # exam/exam.json, exam/sheet.png
python3 scripts/rig_exam.py --selftest                       # numpy, planted data; runs in CI
```

`build`, `run` and `faults` call Blender one process at a time (`--blender PATH`, else `$BLENDER`, else
`autorig.py`'s default). `run` and `faults` need the user's Auto-Rig Pro, as the pipeline does. A body
takes about half a minute on a laptop CPU. `score` only reads JSON and needs no Blender. Keep the exam
folder outside the repository: a reference case holds a real character's mesh.

## The cast

`rig_exam_blender.py` builds each body from metaballs around a known skeleton: an A-pose facing −Y,
with the soles on Z 0. Each body is one mesh of about 40k triangles. `--seed` jitters the proportions
by up to 2 %, so a seed always gives the same cast.

| Body | What it tests | Expected |
|---|---|---|
| `standard` | adult proportions, arms 45°, fingers apart | every stage passes |
| `chibi` | a big head and short limbs, mitten hands | stops at `mesh_check`'s bands and the marker windows (the hand-built route) |
| `heavy` | a wide torso and thick limbs, arms 50° | every stage passes |
| `thin` | slim limbs, arms 55° | every stage passes |
| `long_limbs` | longer arms and legs, arms 30° | every stage passes |
| `mitten` | the standard body with fused fingers | `fingers.mode` `fixed` |
| `spiky_hair` | hair that raises the top of the mesh | the windows read the hair as height |
| `skirt` | a solid skirt over the crotch, hem at 0.40 of 1.7 m | the crotch read at the hem |
| `asym` | arms a few degrees apart, one knee and shoulder a few mm higher | within the symmetry gate |

**Truth** (`NAME.truth.json`, `exam/1`, kind `truth`, in the GLB's frame with Z up):

- **Joints** are the ends of the capsules the body was built from: shoulder, elbow, wrist, hip, knee
  and ankle. The pelvis is the midpoint of the hips. `neck_base` and `head_base` are the ends of the
  neck.
- **Ends** are the mesh's own extreme points along the true axis: `hand_tip`, `toe_tip` and `heel`.
  `ball` is where the toe capsule starts. `head_top` is the top of the skull, measured before any
  hair is added.
- **Fingers** count as apart only where the built surface falls into four parts across the middle
  phalanx (`fingers.parts_across`). Metaballs can fuse fingers that sit close together, and fused
  fingers are scored as a mitten.

## Running and scoring

`run` calls `autorig.py all exam/runs/NAME exam/cast/NAME.glb --name NAME --height H --no-smart`, with
H the body's own height. The prep then only grounds and centres the mesh, and the scorer moves the
truth the same way. When a run stops before the markers (a chibi), the exam measures the markers
anyway with `--no-window-gate` (`rig/NAME.markers_only.json`). Those landmarks are scored, but the
case can never count as a pass.

Each landmark's error is its distance from the truth divided by H, the markers' height. The exam
scores the markers file and also the exported skeleton (UpperArm head against the shoulder, LowerArm
against the elbow, and so on), in four groups:

| Group | Landmarks | Notes |
|---|---|---|
| `joints` | shoulder, elbow, wrist, hip, knee, ankle, pelvis, neck_base, head_base | decide whether the rig is correct |
| `ends` | hand_tip, ball, toe_tip, heel, head_top | reported |
| `fingers` | index, middle, ring, little, joints 0–3 | only on bodies whose fingers are apart |
| `thumb` | thumb 0–3 | always the fixed hand shape |

A rig is **correct** when every joint lies within `--tol` × H (0.04). The outcome compares that with
what the stages did:

| Outcome | Meaning |
|---|---|
| `true_pass` | correct, and every stage passed (after a repair that passed) |
| `false_fail` | correct, but a gate failed that the case does not expect |
| `expected_fail` | failed only the gates the case expects (the chibi) |
| `true_fail` | a joint out of tolerance, and a gate failed |
| `false_pass` | a joint out of tolerance, and every gate passed: the worst outcome |
| `stopped` | the pipeline stopped for a reason the case does not expect |

**Fingers found:** `detected` counts as 4, `ai` as its own count, and `fixed` as 0. The count is
compared with the truth's apart fingers.

**Deformation:** the report gives the pre-repair report (what Auto-Rig Pro's bind gave) and the final
one after the repair ladder. It includes the worst volume loss with its joint and pose, the
self-intersection p95, the ball-joint loss and the joints the volume gate could not measure.

## Faults

Each fault is planted on a copy of the base rig and must be caught by a gate. Faults on the markers
move them with `arp_markers.py --adjust`, then run `arp`, `contract` and `deform` without the repair
ladder. Faults on the weights edit the base FBX's weights (`rig_exam_blender.py weights`) and gate
the result with `deform_gate.py`.

| Fault | The defect | Expected gate |
|---|---|---|
| `elbow_shift` | both elbow markers 0.05 H toward the wrist | `deform.volume_loss_max` |
| `knee_swap` | the left and right knee markers swapped | the contract's `sides` |
| `finger_collapse` | index 1–3 on top of index 0, both hands | `arp.refs_placed` or a contract gate |
| `leg_smear` | half of the left leg's weight on the right leg's bones | a deform gate |
| `elbow_blend`, `knee_blend` | the joint's weight split 50/50 between its two bones within 0.6 of the shorter span | `deform.volume_loss_max` |
| `rigid` | every vertex on its heaviest bone alone | `deform.self_intersection_p95` |
| `none` | the base FBX unchanged (the control) | none: a failure here is a false fail |

The verdict is `caught` when the expected gate failed, `caught_by_other_gate` when another gate
failed, and `slipped` when no gate failed. A gate the base rig already failed does not count as
catching a fault (`base_failed`). For example, a reference whose markers fail the windows without the
AI cannot catch a collapsed finger through those windows.

**Defects the gates do not catch.** Look at the renders for these:

- A whole limb weighted to the other side's bones. No pose bends the limb it pulls on, and a hip's
  patch is too small to measure.
- A rigid skin on a slim body. The joint turns rigidly, so it keeps its volume, and the seam is
  diluted over the moved region.
- A finger chain collapsed to a point. No gate checks a finger bone's length.
- An elbow marker off the crease on a slim limb. The loss rises but can stay under the limit.
- A mitten read as four fingers. The split is read from random surface samples, and a mitten's
  sample gaps can mimic four parts. The fist on such a hand is then gated as fingers.

**The volume check** (`summary.volume`) compares two readings: the largest gated loss of the good
rigs (true passes after any repair, the accepted references, the `none` controls) and the smallest
loss of the volume faults. The limit separates good from bad when it lies between them; the margins
are given both ways. The `elbow_shift` readings are listed as `mild`. Rerun this check whenever
deform_gate's patch or limit changes, and retune the limit only when it stops separating.

## The reference set — rigs a person accepted

A rig a person accepted becomes a case that is scored the same way:

```bash
python3 scripts/rig_exam.py reference exam/ NAME --glb NAME.glb --markers rig/NAME.markers.json \
  [--fbx export/NAME.fbx --contract rig/NAME.contract.json]
python3 scripts/rig_exam.py run exam/ --refs
```

`reference` copies the mesh and the accepted files into `exam/refs/NAME/`. Its truth is the accepted
markers, in the prepared frame (kind `reference`). `run` puts the mesh through the current pipeline
into `exam/refruns/NAME/`, compares the new markers with the accepted ones, and gates the accepted
rig again with the current `deform_gate.py` (`accepted.deform.json`). A gate that fails the accepted
rig is a false fail. Add a case only for a rig a person looked at and accepted. A rig that merely
passed the gates does not qualify: the exam would then test the gates against themselves.

## Auto-Rig Pro's AI in the exam

`run --smart` drops `--no-smart`, so the add-on's AI runs (stage 2, a Blender window that closes
itself). The markers' `smart_agreement` is copied into the case as `smart_second_opinion`. It is a
second opinion only: it is never used as truth, never as a label, and never to set a limit. Its
licence covers running it on the user's device, not training or tuning on its output. Keep a
`--smart` run in its own exam folder, so that the slice-only baseline stays comparable.

## The report

`exam/exam.json` (`exam/1`, kind `report`, local to this skill and not a cross-skill contract) holds:

- `summary`: the joints' p50, p95 and worst; each group and each landmark pooled over both sides;
  the weakest landmarks and bodies; the outcomes; fingers right; the faults caught and slipped; and
  the volume check.
- `cases`: per case, every landmark's error, the rig's joints, the failed gates, both deformation
  readings and the outcome.
- `faults`: per fault, the gates it failed and the verdict.

`exam/sheet.png` shows the front and side of each case, with the truth in green, the markers in red
and a red line where they differ. `score` exits 2 when a case is a false pass or a fault slipped
through, so the exit code reads as a verdict on the version.
