# Failures, fixed locally — every gate, and its fix

A gate failure is fixed here, never by loosening the limit for one character. What each gate
measures and its limit: `reference/gates.md`.

| What failed | Fix |
|---|---|
| `legs_separated` (mesh_check) | the legs are one tube: regenerate the views with a gap between the legs, or the mesh; no marker helps. A long coat, skirt or robe (the report's `skirt_hint`): the skirt route, `autorig.py all --body skirt` (`reference/gates.md`) |
| `skirt_hem` (`--body skirt`) | no hem, or under 0.08 H of leg shows below it (a floor-length robe): the hand-built route, or views with the legs showing |
| `markers.windows` hip at a hem (`crotch_h` 0.25–0.40, a coat or skirt in the pictures) | the hem read as the crotch: `--body skirt`, never `--adjust` the hip to pass |
| `arms_separated` | arms glued to the ribs, held against the body, or a T-pose: regenerate in an A-pose with the arms 30–60° down and clear of the torso |
| `double_shell` | a same-facing inner twin, or two skins pressed together: regenerate. A back-to-back inward-facing inner shell does not fail it (`inner_shell`): keep it, the deformation gate reads the outer skin |
| `legs_separated`, `arms_separated` or `markers.windows` on a big head and short limbs (shoulder near 0.6 H) | a chibi, if the concept is one: `autorig.py all --body chibi`, its own bands and windows (`reference/markers.md`); chosen at G0, never to rescue an adult body |
| `markers.windows` | with stage `smart`'s file, a landmark at most 0.03 H outside whose AI marker sits inside the window passes (`confirmed_by`); hair raising the head top is the usual case (`reference/arp-ai.md`). Still failing: proportions this route was not made for, hand-built route |
| `smart.*` (stage 2) | never blocks: the markers take what passed, slices for the rest. Its own fixes (AI files, eyes, shading, a second rig) are in `reference/arp-ai.md` |
| `markers.symmetry` | the pose is not symmetric (one arm higher, a turned foot): regenerate, or `--adjust` each marker it names and accept the mirror (`asymmetry_accepted`) |
| a marker looks off in the pictures | `--adjust` with that marker's position (`reference/markers.md`), run again, look again |
| the knee sits on a hem, a boot top or a knee pad in the pictures | the notes name the knee's cue. A hem only shows as a step when the girth jumps 10 % within 1 % of the leg; a softer cuff can still read as the narrowing. `--adjust` both knees to the crease (`reference/markers.md`, the knee) |
| `deform.joints_measured` names LowerLeg on legs in shorts | the knee marker may sit near the hem: check it in the pictures and move it to the crease (`--adjust`) before touching the mesh |
| `deform.skirt_tear` | the skirt's skin holds a seam (one thigh per side, Hips beside a thigh): rerun `autorig.py contract` on the skirt route (its `skirt_bind`); on the chained rig, a chain taking a thigh's weight must hang from that thigh |
| `arp.spine_bones` | the rig holds a different number of spine bones than Count − 1 asked for: run `scripts/tests/test_arp_pipeline.py` on this Blender and add-on before trusting the rig |
| `arp.refs_placed` | the markers name a reference bone the preset lacks, or a roll from `ref_rolls` did not hold; regenerate the markers file |
| `arp.face_added` | the add-on added no face or ear bones on the head: read `probe`'s operator properties for this version, or rig without the face (markers without `--smart`, or `smart` without `--facial`) |
| `arp.vertices_without_group`, `arp.export_unweighted` | a part the bind did not reach: join it to the body, or separate it and put it on a bone (`blender-character-rig` → `reference/prop-on-bone.md`) |
| contract `UpperChest` missing | the rig has two spine bones (Count 3): rerun with `spine_count: 4`, the markers file's default; the add-on's Count counts its root |
| `deform.volume_loss_max` at an elbow or knee | the blend across that joint is too wide. First two `brt_weights` transfers around the joint, `brt_arp` `export`, gate again, on a copy (`autorig.py` does this); if that does not pass, by hand, one at a time: a finer bind (`resolution`), the marker moved to the crease (`reference/arp-pipeline.md`) |
| `deform.joints_measured` | an elbow or knee the volume gate could not read (an opening, too few triangles there): fix the mesh, never drop the pose |
| `deform.self_intersection_p95` from `fist` on a hand whose markers say `fingers.mode` `fixed` | a mitten, or fingers held together, folds into itself in a fist: `autorig.py` gates `mitten` instead (`--poses arms_up,deep_squat,torso_twist,leg_raise,elbow_120,mitten`) after `mitten_bind`; on a glove, stage `smart` may part the fingers (`ai`) |
| `deform.mitten_tear` | the mitten rides four finger chains: rerun `autorig.py contract` (its `mitten_bind` folds them onto Middle) |
| finger markers on a closed hand in the pictures (`fingers.mode` `detected` on a mitten or glove) | the surface did cut into four loops (fingers pressed but modelled apart): rerun `arp_markers.py --fingers fixed`, so stage 5 folds the chains and stage 7 gates the mitten |
| a satchel on the hip, or a cap read as hair spikes, in the chain pictures | bag detection reads the back alone, and a cap's crown can pass the hair test: a `bag` marker chain on the satchel and `skip` for the cap's chains (`reference/secondary-chains.md`, the markers file) |
| `smart.fingers` on a mitten | the add-on finds no fingers on a closed hand; it never blocks, the slices' `fixed` hand stands, and when the markers read `fixed` too `all` adds no exit 2 for it (`smart.mitten` in the summary) |
| `deform.joints_measured` names LowerLeg on a short leg under a shorts hem | the gate keeps the leg's own skin when the hem's lining unwraps the patch; still listed: the knee marker sits inside the shorts, `--adjust` it to the visible crease |
| `rig_exam.py score` exits 2: a false pass or a slipped fault | the change that caused it does not ship: read that case on `sheet.png` and its gates in `exam.json` (`reference/rig-exam.md`); never move `--tol` or a gate limit to clear it |
| `deform.self_intersection_p95` (other poses) | a hard seam (skin follows one bone rigidly): smooth the weights over the joint; in a squat, thighs crossing the belly mean the hip markers sit too low |
