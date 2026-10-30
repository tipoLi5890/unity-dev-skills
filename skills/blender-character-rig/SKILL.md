---
name: blender-character-rig
description: >-
  Hand-built Blender rig, fallback to the default character-autorig: mascot
  bodies, pack-skeleton fit.
---

# blender-character-rig — measure the mesh, compute the weights, prove the file

A generated character is a mesh and nothing else: no skeleton, no scale, a thin double shell in
several islands. An auto-rigger wants standard proportions and one watertight body; automatic
weights want a surface every bone can see. A short-limbed mascot with long ears gives neither.

> **A standard humanoid goes to `character-autorig` first** — Auto-Rig Pro, headless, onto the
> humanoid contract. This skill is the hand-built fallback: a custom body that rig cannot take, or
> a mesh fitted to one clip pack's skeleton.

## Start here — the request, and where it is answered

| The request or symptom | Read |
|---|---|
| "Rig this GLB" by hand: a mascot body the default auto-rig cannot take | [the pipeline](#1-the-pipeline), then `reference/import-and-survey.md` |
| "Chibi / short limbs", "automatic weights failed" (bone heat on a double shell), "the ears tear when posed": the bone spec, radii, the positional rule, gradient chains, symptom → fix | `reference/armature-and-skinning.md` |
| "Fit my character to the mocap pack's skeleton": what may change, canonical and display scale, soles on the floor, hip width, the skin method by measured intersection | `reference/fit-to-clip-skeleton.md` |
| "Run Blender headless": stage layout (`blender -b`), gates JSON, exit 0/1/2, byte-identical FBX, a Unity lab outside the repo | `reference/headless-pipeline.md` |
| Registering the server, the cheapest probes, running a module through it (the stub, the reload order, the loader when Blender cannot read the skill directory), where a render really lands | `reference/mcp-session.md` |
| Someone else's scene: collections, hiding, a second scene, translated UI names (`KeyError 'Principled BSDF'`), what to report | `reference/scene-discipline.md` |
| Importing the GLB, origin, height, facing, the weld, reading landmarks from slices and boxes | `reference/import-and-survey.md` |
| A prop in a hand: grip measured from the prop, the sanity ratio, bone parenting | `reference/prop-on-bone.md` |
| Poses in armature axes, keying an action, the contact probe, chunked renders, GIF and contact sheet | `reference/action-and-preview.md` |
| The ship track's game mesh before rigging: regenerate at the preset, or retopology, UVs and a rebake | `reference/game-mesh.md` |
| Exporter options, clip naming, export FBX and prove it by re-import, the Unity check | `reference/fbx-export.md` |
| "LOD spikes": lighter skinned levels on one skeleton — hidden shells, shard props, normals, boundary weights, names Unity will not turn into a LODGroup | `reference/skinned-lod.md` |
| A worked example: the plush runner with long ears and a mallet, every step | `reference/worked-example.md` |
| The call contract of each module (its docstring) | `scripts/bcr_*.py`, `scripts/rig_gate.py`, `scripts/frames_preview.py` |

> **Nothing here is placed by eye or solved.** Joints are read from slices of the mesh, weights
> are computed from where each vertex is, the swing is measured at the contact frame before it is
> rendered, and the FBX is imported back and compared.

Every step is one call to a module in `scripts/` that returns a dict of gates: through the MCP
server of a Blender the user already has open, for one character explored by hand; or from a stage
script under `blender -b --factory-startup --python`, for a character rebuilt the same way every
time. Every module runs unchanged headless (`reference/headless-pipeline.md`); through the server,
a short stub imports and reloads it and `result` is the dict it returns (`reference/mcp-session.md`).

> **One clip pack supplies the motion? Fit, do not build.** Move the pack's skeleton onto the
> mesh once (names, parents and rest rotations kept) and the clips play unchanged:
> `reference/fit-to-clip-skeleton.md`. Building a skeleton from landmarks is for a custom body.

## Working contract

- **The user's Blender, the user's file.** Installing Blender, the add-on or the server is the
  user's, on request only. Never save unasked; say whether the file is saved when handing back.
- **List the server's tools, do not recall them.** "Unreachable" is not "absent": ask whether
  Blender is open and connected before concluding anything.
- **Work additively.** New objects go in their own collection. Hide instead of delete; add a
  camera, light or world instead of editing the user's. Report every non-additive change.
- **Find nodes by type, not by name.** With a non-English UI `nodes["Principled BSDF"]` raises
  `KeyError`; `bcr_common.node_of` looks a node up by `bl_idname`.
- **`ok` covers one step.** Read a failed gate's `value` against its `limit`, change one
  parameter and rerun before the next step. Calls are idempotent by name, and `bcr_import_prep`
  and `bcr_attach` reuse what exists and ignore new parameters: remove the object, or put the
  prop back, before a rerun. A call that raises
  removes what it created; edits to datablocks that already existed are not undone.
- **Headless, the stage owns its files.** It reads the previous stage's output and writes its own
  `.blend` and gates JSON; it never opens the user's file for writing. Exit 0 pass, 1 a gate
  failed, 2 refused input; two runs give the same mesh hashes and FBX bytes.

## 1. The pipeline

In order. A row is done when its gates pass or, where it says picture, when someone has looked.

| # | Step | Module / op | Passes when |
|---|---|---|---|
| 1 | Probe the session | The server's blend-file and objects summaries | File path, save state, collections, active object and mode are known before any code runs |
| 2 | Import and prep | `bcr_import_prep` | `one_mesh`, `identity_scale_rotation`, `origin_at_base`, `weld_kept_faces`; `height` as asked |
| 3 | Survey | `bcr_survey` | `has_vertices`, `empty_boxes`; `parts` reads 2 at the legs and ears, 3 where the arms hang |
| 4 | Armature | `bcr_armature` | `bone_count`, `zero_length_bones`, `roots`, `pose_bones_not_xyz`, `deform_bones_without_radius` |
| 5 | Skin | `bcr_skin` | `unweighted_vertices` 0, `max_influences` ≤ 4, `weight_sum_error` < 1e-4, `deform_bones_without_vertices`; no bone with a near-empty `dominant_vertices` |
| 6 | Extreme-pose test | `bcr_pose` op `apply` → `bcr_preview` `still` → `bcr_pose` op `reset` | **Picture**: nothing torn into strips, no torso dragged by an arm, no folded crease; then `pose_is_rest` |
| 7 | Prop on the hand bone | `bcr_import_prep` (`weld_distance: None`), then `bcr_attach` at the rest pose | `handle_radius_ratio` ≤ 0.15, `world_drift_after_parenting` < 1e-4 |
| 8 | Key the action | `bcr_pose` op `key`; op `key_object` for a target that reacts | `slot_assigned`, `fcurves` ≥ 3 per keyed bone, `first_equals_last` when `loop` is set |
| 9 | Probe contact, then preview | `bcr_probe`; `bcr_preview` in chunks; `scripts/frames_preview.py` on the host | `distance_to_target` ≤ 0.05, `direction_z` ≥ −0.8; `frames_missing`, `settings_restored`; exit 0; **picture**: the GIF and the contact sheet |
| 10 | FBX export, re-import, gate | `bcr_fbx` ops `snapshot` → `export` → `reimport` → `discard`, with `scripts/rig_gate.py` on the two snapshots | `finished`, `file_bytes`, `one_armature`; exit 0 on `bones`, `parents`, `bone_positions`, `groups`, `bone_parents`, `influences`, `scale`, `action` |

Numbers cannot close steps 6 and 9: a mesh passes every weight gate and still tears; a swing
lands on a target that stands between the camera and the character.

## Discipline

- **Weights are judged in an extreme pose, never at rest.** At rest every weighting looks correct.
- **Probe before rendering.** The probe says by how much a swing misses; a render says that it does.
- **Do not trust a sign you have not seen.** Rotations are steps in armature axes, applied in the
  order written. Before keying, apply one step and probe which way the point moved.
- **Keep the inner shell and every island**; cull back faces instead. The baked maps address them.
- **"FINISHED" proves a file, not a rig.** Only the re-import and `rig_gate.py` do.
- **Decide the clip name before Unity.** One action exports as a take named after the scene;
  all-actions writes every action in the .blend as `<rig>|<action>`.
- **State the limits when handing back**: FK only, feet planted, single-handed, a hand that does
  not close around the handle.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| The source image and the four-view sheet (A-pose, thick ears, no held prop) | `codex-visual` |
| Generating the GLB and gating its triangle and texture budget | `comfyui-asset-generation` |
| Mixamo for standard proportions; the Unity FBX importer, Avatar, Animator, PBR maps | `unity-rigged-character` |
| Static props that need no skeleton | `unity-3d-models` |
| Moving the character in Unity: controller, grounding, the Animator bridge | `unity-3d-controller` |
| Retargeting stock or purchased clips onto a rig, a library of them, a grip held across clips | `blender-retarget` |
| IK, foot planting, facial rigs, cloth or physics bones | Not covered — this is FK on a hand-specified skeleton |
| Installing Blender, the add-on or the MCP server | The user's, on request only |
| The character's stage order: preview or ship track, the game mesh before the rig | `game-character-pipeline` |
| A humanoid rigged headless onto the humanoid contract: Auto-Rig Pro from measured markers, the mesh and deformation gates | `character-autorig` |
| Clips from two-camera video onto the contract, contact bake | `humanoid-motion` |
| Proving the action plays in the running game | `unity-debug` |
