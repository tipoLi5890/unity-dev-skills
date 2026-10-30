# Failures, fixed locally — every gate, and its fix

A gate failure is fixed here, never by loosening the limit for one character. What each gate
measures and its limit: `reference/gates.md`.

| What failed | Fix |
|---|---|
| `legs_separated` (mesh_check) | the legs are one tube or a long garment: regenerate the views with a gap between the legs, or the mesh; no marker helps |
| `arms_separated` | arms glued to the ribs, held against the body, or a T-pose: regenerate in an A-pose with the arms 30–60° down and clear of the torso |
| `double_shell` | a same-facing inner twin, or two skins pressed together: regenerate. A back-to-back inward-facing inner shell does not fail it (`inner_shell`): keep it, the deformation gate reads the outer skin |
| `markers.windows` | proportions this route was not made for: hand-built route |
| `markers.symmetry` | the pose is not symmetric (one arm higher, a turned foot): regenerate, or `--adjust` each marker it names and accept the mirror (`asymmetry_accepted`) |
| a marker looks off in the pictures | `--adjust` with that marker's position (`reference/markers.md`), run again, look again |
| `arp.spine_bones` | the rig holds a different number of spine bones than Count − 1 asked for: run `scripts/tests/test_arp_pipeline.py` on this Blender and add-on before trusting the rig |
| `arp.refs_placed` | the markers name a reference bone the preset lacks; regenerate the markers file |
| `arp.vertices_without_group`, `arp.export_unweighted` | a part the bind did not reach: join it to the body, or separate it and put it on a bone (`blender-character-rig` → `reference/prop-on-bone.md`) |
| contract `UpperChest` missing | the rig has two spine bones (Count 3): rerun with `spine_count: 4`, the markers file's default; the add-on's Count counts its root |
| `deform.volume_loss_max` at an elbow or knee | the blend across that joint is too wide. First two `brt_weights` transfers around the joint, `brt_arp` `export`, gate again, on a copy (`autorig.py` does this); if that does not pass, by hand, one at a time: a finer bind (`resolution`), the marker moved to the crease (`reference/arp-pipeline.md`) |
| `deform.joints_measured` | an elbow or knee the volume gate could not read (an opening, too few triangles there): fix the mesh, never drop the pose |
| `deform.self_intersection_p95` from `fist` on a hand whose markers say `fingers.mode` `fixed` | a mitten, or fingers held together, folds into itself in a fist: gate the other five poses (`--poses arms_up,deep_squat,torso_twist,leg_raise,elbow_120`), as stage 4 drops `--min-fingers` |
| `deform.self_intersection_p95` (other poses) | a hard seam (skin follows one bone rigidly): smooth the weights over the joint; in a squat, thighs crossing the belly mean the hip markers sit too low |
