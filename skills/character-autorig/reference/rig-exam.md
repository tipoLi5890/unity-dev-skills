# The rig exam — the automatic rig scored against bodies whose joints are known

> Part of the `character-autorig` skill. The stages it runs are in `SKILL.md`; what each gate measures
> is in `reference/gates.md`. `scripts/rig_exam.py` drives the exam and scores it;
> `scripts/rig_exam_blender.py` builds the bodies and the weight faults inside Blender.

A change to the markers, the pipeline or a gate is scored before it ships. The exam rigs a fixed cast
of procedural bodies whose skeletons are known, compares every marker and exported joint with the
truth, plants known defects in a good rig, and checks that the gates fail each one. Run it on the
current version first and keep its bench file as the baseline. Then make the change, run the exam
again and compare the two (`bench`, `compare` below): the change should improve scores or catch more
faults, and it should not add a false pass.

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
python3 scripts/rig_exam.py bench exam/ --real couriers/runner --out bench/before.bench.json   # bench/1
python3 scripts/rig_exam.py compare bench/before.bench.json bench/after.bench.json [--margin-drop 0.02] [--near 1.0] [--tradeoff-floor 0.05]
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
| `chibi` | a big head and short limbs, mitten hands; run with `--body chibi` | every stage passes on the chibi route (without it, `mesh_check`'s bands and the windows refuse it) |
| `heavy` | a wide torso and thick limbs, arms 50° | thick thighs meet below the hip joints (the hip is read a leg's half-width over the crotch) and the chest at the armpit reaches past the shoulder joint: every stage passes; a hip read low fails `markers.limb_ratio`, not a false pass |
| `thin` | slim limbs, arms 55° | every stage passes |
| `long_limbs` | longer arms and legs, arms 30° | every stage passes |
| `mitten` | the standard body with fused fingers | `fingers.mode` `fixed`, `mitten_bind`, the `mitten` pose |
| `spiky_hair` | hair that raises the top of the mesh | the windows read the hair as height |
| `skirt` | a solid skirt over the crotch, hem at 0.40 of 1.7 m; run with `--body skirt` | without it, the crotch read at the hem; with it, the crotch hidden and the hip placed from the knee |
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
H the body's own height (`--body skirt` or `--body chibi` for the bodies built as one). `faults`
re-measures a base's markers on its own body route and gates its weight faults with the base's poses. The prep then only grounds and centres the mesh, and the scorer moves the
truth the same way. When a run stops before the markers, the exam measures the markers
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
| `expected_fail` | failed only the gates the case expects (`expect_fail` in its truth) |
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
| `elbow_shift` | both elbow markers 0.05 H toward the wrist | `markers.limb_ratio` (or `deform.volume_loss_max`) |
| `knee_swap` | the left and right knee markers swapped | the contract's `sides` |
| `finger_collapse` | index 1–3 on top of index 0, both hands | `markers.finger_lengths` |
| `leg_smear` | half of the left leg's weight on the right leg's bones | `deform.cross_side_weight` |
| `elbow_blend`, `knee_blend` | the joint's weight split 50/50 between its two bones within 0.6 of the shorter span | `deform.volume_loss_max` |
| `rigid` | every vertex on its heaviest bone alone | `deform.hinge_blended` (or the self-intersection gate) |
| `mitten_split` | a mitten base only (`fingers.mode` `fixed`, not a reference): each Middle phalanx's weight back on the nearest of the four chains, four strips as a plain bind leaves a mitten | `deform.mitten_tear` |
| `skirt_split` | a skirt base only (planted when its markers carry `skirt`): the skirt's own skin on Hips and the thigh of its own side, the thigh's share rising to 1 at the hem, switching sides at the midline (a plain bind's long coat) | `deform.skirt_tear` |
| `none` | the base FBX unchanged (the control) | none: a failure here is a false fail |

The verdict is `caught` when the expected gate failed, `caught_by_other_gate` when another gate
failed, and `slipped` when no gate failed. A gate the base rig already failed does not count as
catching a fault (`base_failed`). For example, a reference whose markers fail the windows without the
AI cannot catch a collapsed finger through those windows.

**Defects that once slipped** and the gate that now reads each one without a pose: a whole limb
weighted to the other side's bones (no pose bends the limb it pulls on; `deform.cross_side_weight`
reads the bind at rest), a rigid skin on a slim body (it keeps its volume and its seam is diluted over
the moved region; `deform.hinge_blended` finds no blended vertex at the hinges), a finger chain
collapsed to a point (`markers.finger_lengths`) and an elbow marker 0.05 H toward the wrist (the loss
can stay under the limit on a slim limb; `markers.limb_ratio` reads one segment over twice the other).
A smaller marker slip than that is still the volume gate's and the renders'. The new limits sit
between the good rigs (controls, accepted references, the cast's exports) and the faults with a
margin both ways; rerun the faults and the controls before retuning one.

**Defects the gates do not catch.** Look at the renders for this:

- Fingers modelled apart but pressed together read as `detected` when the surface does cut into four
  loops; the pictures show it.

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

## Bench and compare — one version against another

`bench` writes one file per version (`bench/1`, `schemas/bench-1.json`); `compare` reads two of
them. Neither needs Blender.

- **`exam`**: `score`'s summary of the exam folder (outcomes, false passes, faults caught and
  slipped, failed controls, fingers right, the volume check), or null when no case has run.
  `--no-exam` benches real characters alone.
- **`real`**, one entry per `--real OUT` (a character's `autorig.py` folder): its name, body, and per
  step of `autorig.all.json` every gate of the step's report with `value`, `limit`, `pass` and
  `margin` (null when the gate has none). `deform` is the reading after the repair ladder.
  `stability` is `autorig.stability.json` when the folder was run with `--repeat`, and
  `worst_margin` is the least margin over its gates. `repair` says what the repair ladder did:
  `chosen` for the run `autorig.all.json` stands for (`result`: the ladder's `passed`, `exhausted`,
  `error` or `not_applicable`, after a pass near the limit `kept_repair` or `kept_original`, `none`
  when no ladder ran, `not_reached` when deform did not run; `trigger` `failed` or `near_limit`;
  `fired`, an attempt was made; `used`, the bind taken on is the repair; each rung's hinges, amount
  and cross-side bones), and with `--repeat` `runs`: each `repeat/rN/autorig.all.json` read the
  same way, how many of them were `repaired` (fired) and how many `used` it. After `kept_original`
  `deform` is the first reading.
- **`made_with`**: `--label` (say, the version), the plugin version when its manifest is found, and
  a short hash of each script in this folder.

`compare OLD NEW` exits 2 on any regression and lists each one: a gate that passed and now fails or
is no longer read, a gate new to a step OLD read that fails, a margin that drops by more than
`--margin-drop` (0.02) and ends under `--near` (1.0) or drops by more than it, a real character or exam case of OLD missing
from NEW, a case that was a true pass or an expected fail and is not now, fewer fingers right, or a
new false pass, slipped fault or failed control. Improvements, the same changes the other way, are
listed too and never fail it. Two more lists hold drops that are not regressions:

- **`informational`: the noise floor.** A margin is in units of the limit (gate/1), so a margin of
  1.0 sits one limit's size away from it. A `<=` gate (a loss, a tear, an intersection) or a range
  never reads a margin above 1.0, so the floor never excuses one of them; it only lets through a
  `>=` gate whose value is more than twice its limit (a finger 9 cm long against a 1 cm minimum,
  margin 8) moving by run-to-run noise: a drop of at most `--near` that ends at `--near` or more. A
  drop from 8 to 0.6 lands under the floor and regresses; one from 8 to 1.2 moves more than one
  limit's size and regresses too. The `stable` gate is never listed there. This is the detector's
  floor, not a gate limit: no gate passes or fails differently, and `--near` changes only which
  list a drop is printed in. A large value (`--near 1000`) turns the floor off.
- **`repair_tradeoffs`: a designed repair.** The repair ladder moves weight across a hinge to bring
  the volume loss under its limit, and a sharper hinge self-intersects a little more. When a
  character's repair differs between the two files (the `repair` list: `repair_now`, `repair_gone`,
  `repair_changed`: other rungs, or another share of runs repaired or using it, a folder without
  `--repeat` being one run; `repair_now` and `repair_gone` follow `used` first, so a near-limit
  ladder that kept the original reads as gone against a used repair), a still-passing margin drop
  of `deform.volume_loss_max` or `deform.self_intersection_p95` (the pair the ladder trades; no
  other gate) on that character, in `deform`, `secondary_deform` or `stability`, is listed there
  when the other of the pair, still passing in the same step, rose by more than `--margin-drop`
  (the rise it bought), a side's bind is the repair (`used`), and its new margin is at least `--tradeoff-floor` (0.05, the
  ladder's near band: a drop onto the edge of a limit regresses whatever the repair did); otherwise
  it stays a regression. Never excused: a gate going from pass to fail, the `stable` gate, a
  new false pass, a slipped fault or a failed control. Read the rung's renders before the change
  ships, as for any repair.
- **`repair_unknown`.** A bench written before the repair reading (no `repair` key), or one whose
  chosen or `--repeat` run's `autorig.all.json` was not found, says nothing about the ladder, so
  `compare` lists the character as `repair_unknown` and every drop stays under the plain rule; bench the baseline again from its folders to get the reading.

A change ships when `compare` exits 0 against the last baseline. `bench` refuses to write
a file with nothing in it (no scored exam case, no `--real`), and `compare` refuses such an OLD.
A gate compares margins only when both files carry one. Reports from before 0.43 say a bare limit
(`0.35`, not `<= 0.35`), so against such a baseline `compare` sees pass and fail alone on those
gates; bench the next baseline on 0.43 or later.

**Keep bench files outside the repository**, beside the exam folder: they hold paths to real
characters and change with every run. The repository holds the tools, not the scores.

**A real-character bench.** The exam's cases are built; the characters the project ships are what a
change must not break. Bench a few that between them cover the bodies the markers read (the
default, `--body skirt`, `--body chibi`) and the shapes that test them (a long coat, mittens, armour
plates), each run with `--repeat` so a drop can be read against its own run-to-run spread, from the
same meshes before and after the change. Before a change to the markers:

```bash
python3 scripts/rig_exam.py build exam/ && python3 scripts/rig_exam.py run exam/
python3 scripts/rig_exam.py faults exam/ --base standard && python3 scripts/rig_exam.py score exam/
# once per character, with the --body its markers take
python3 scripts/autorig.py all couriers/<name> <Name>.glb [--body skirt|chibi] --repeat 3
python3 scripts/rig_exam.py bench exam/ --real couriers/<name> [couriers/<name> ...] \
  --out bench/before.bench.json --label before
```

After the change, the same commands into `bench/after.bench.json`, then:

```bash
python3 scripts/rig_exam.py compare bench/before.bench.json bench/after.bench.json
```

Read it list by list:

- **`regressions`** (exit 2). A margin that still passes but dropped by more than `--margin-drop`
  toward its limit is a `margin_drop` naming the character, the step and the gate: look at that
  pose's render before the change ships, though the gate passes.
- **`repair`, `repair_tradeoffs`.** A character whose elbow or knee now takes the repair ladder is
  listed `repair_now`; a self-intersection margin its rung lowered while the volume margin rose by
  more than `--margin-drop` goes under `repair_tradeoffs`, not `regressions`, on the terms above
  (the repair is the bind used, the new margin at `--tradeoff-floor` or more). Read the rung's renders.
- **`informational`.** A `>=` gate far past its limit (a finger's length) moving by run-to-run noise.
- **`improvements`.** The same changes the other way: an exam case whose fingers read `detected`
  again shows a higher `fingers_right`.

