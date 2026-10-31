# Failures, fixed locally — every gate, and its fix

A gate failure is fixed here, never by loosening the limit for one character. What each gate
measures and its limit: `reference/gates.md`.

| What failed | Fix |
|---|---|
| `legs_separated` (mesh_check) | the legs are one tube or a long garment: regenerate the views with a gap between the legs, or the mesh; no marker helps |
| `arms_separated` | arms glued to the ribs, held against the body, or a T-pose: regenerate in an A-pose with the arms 30–60° down and clear of the torso |
| `double_shell` | a same-facing inner twin, or two skins pressed together: regenerate. A back-to-back inward-facing inner shell does not fail it (`inner_shell`): keep it, the deformation gate reads the outer skin |
| `markers.windows` | with stage `smart`'s file, a landmark at most 0.03 H outside whose AI marker sits inside the window passes (`confirmed_by`); hair raising the head top is the usual case (`reference/arp-ai.md`). Still failing: proportions this route was not made for, hand-built route |
| `smart.*` (stage 2) | never blocks: the markers take what passed, slices for the rest. Its own fixes (AI files, eyes, shading, a second rig) are in `reference/arp-ai.md` |
| `markers.symmetry` | the pose is not symmetric (one arm higher, a turned foot): regenerate, or `--adjust` each marker it names and accept the mirror (`asymmetry_accepted`) |
| a marker looks off in the pictures | `--adjust` with that marker's position (`reference/markers.md`), run again, look again |
| `arp.spine_bones` | the rig holds a different number of spine bones than Count − 1 asked for: run `scripts/tests/test_arp_pipeline.py` on this Blender and add-on before trusting the rig |
| `arp.refs_placed` | the markers name a reference bone the preset lacks, or a roll from `ref_rolls` did not hold; regenerate the markers file |
| `arp.face_added` | the add-on added no face or ear bones on the head: read `probe`'s operator properties for this version, or rig without the face (markers without `--smart`, or `smart` without `--facial`) |
| `arp.vertices_without_group`, `arp.export_unweighted` | a part the bind did not reach: join it to the body, or separate it and put it on a bone (`blender-character-rig` → `reference/prop-on-bone.md`) |
| contract `UpperChest` missing | the rig has two spine bones (Count 3): rerun with `spine_count: 4`, the markers file's default; the add-on's Count counts its root |
| `deform.volume_loss_max` at an elbow or knee | the blend across that joint is too wide. First two `brt_weights` transfers around the joint, `brt_arp` `export`, gate again, on a copy (`autorig.py` does this); if that does not pass, by hand, one at a time: a finer bind (`resolution`), the marker moved to the crease (`reference/arp-pipeline.md`) |
| `deform.joints_measured` | an elbow or knee the volume gate could not read (an opening, too few triangles there): fix the mesh, never drop the pose |
| `deform.self_intersection_p95` from `fist` on a hand whose markers say `fingers.mode` `fixed` | a mitten, or fingers held together, folds into itself in a fist: gate the other five poses (`--poses arms_up,deep_squat,torso_twist,leg_raise,elbow_120`), as stage 5 drops `--min-fingers`; on a glove, stage `smart` may part the fingers (`ai`) |
| finger markers on a closed hand in the pictures (`fingers.mode` `detected` on a mitten or glove) | the split is read from surface samples and a mitten can mimic four parts: rerun `arp_markers.py --fingers fixed`, so stage 5 drops `--min-fingers` and stage 7 the fist |
| `rig_exam.py score` exits 2: a false pass or a slipped fault | the change that caused it does not ship: read that case on `sheet.png` and its gates in `exam.json` (`reference/rig-exam.md`); never move `--tol` or a gate limit to clear it |
| `deform.self_intersection_p95` (other poses) | a hard seam (skin follows one bone rigidly): smooth the weights over the joint; in a squat, thighs crossing the belly mean the hip markers sit too low |
