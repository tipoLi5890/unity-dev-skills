---
name: blender-character-rig
description: >-
  Rig and animate an image-to-3D character in a running Blender driven through
  its MCP server: import the GLB, measure landmarks, build an armature from
  them, skin by position (bone heat fails on a double shell), parent a prop to
  a hand bone, key an action, render a preview, export FBX and prove it by
  re-import. Load for: "rig this GLB in Blender", "chibi / short limbs, Mixamo
  cannot rig it", "automatic weights failed", "the ears tear when posed",
  "attach the prop to the hand", "make a swing animation", "drive Blender over
  MCP", KeyError 'Principled BSDF'. Judge weights in an extreme pose. Mixamo
  and Unity import: unity-rigged-character; the GLB: comfyui-asset-generation.
---

# blender-character-rig — measure the mesh, compute the weights, prove the file

A generated character is a mesh and nothing else: no skeleton, no scale, a thin double shell in
several islands. An auto-rigger wants standard proportions and one watertight body; automatic
weights want a surface every bone can see. A short-limbed mascot with long ears gives neither.

> **Nothing here is placed by eye or solved.** Joints are read from slices of the mesh, weights
> are computed from where each vertex is, the swing is measured at the contact frame before it is
> rendered, and the FBX is imported back and compared.

Every step is one call, through the MCP server of a Blender the user already has open, to a
module in `scripts/` that returns a dict of gates.

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

## Load what the situation needs

| The situation | Read |
|---|---|
| Registering the server, the cheapest probes, running code, where a render really lands | `reference/mcp-session.md` |
| Someone else's scene: collections, hiding, a second scene, translated UI names, what to report | `reference/scene-discipline.md` |
| Importing the GLB, origin, height, facing, the weld, reading landmarks from slices and boxes | `reference/import-and-survey.md` |
| The bone spec, radii, why automatic weights fail, the positional rule, gradient chains, symptom → fix | `reference/armature-and-skinning.md` |
| A prop in a hand: grip measured from the prop, the sanity ratio, bone parenting | `reference/prop-on-bone.md` |
| Poses in armature axes, the key table, the contact probe, chunked renders, GIF and contact sheet | `reference/action-and-preview.md` |
| Exporter options, clip naming, the round trip, what Unity still has to confirm | `reference/fbx-export.md` |
| The call contract of each module (its docstring) | `scripts/bcr_*.py`, `scripts/rig_gate.py`, `scripts/frames_preview.py` |

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

## 2. Running a module through the server

The modules run inside Blender, not on a command line. Send this through the server's code tool:

```python
import sys, importlib
p = "<skill>/scripts"                      # absolute path of this skill's scripts directory
if p not in sys.path: sys.path.insert(0, p)
import bcr_common, bcr_skin
importlib.reload(bcr_common); importlib.reload(bcr_skin)
result = bcr_skin.run({"mesh": "Runner", "armature": "RunnerRig"})
```

- **`result` is the return value**: the code tool hands back the JSON-serialisable dict assigned
  to it. Object keys come back as strings — a frame table is keyed `"18"`, not `18`.
- **Reload every time.** Blender keeps `sys.modules` alive for the session, so a plain `import`
  returns the copy the first call loaded. Reload `bcr_common` first (and `bcr_pose` before
  `bcr_fbx`, which imports it).
- **Every `run` returns one shape**, plus the keys its docstring lists; `report_path` in the
  params also writes it to a file.

```python
{"ok": True,                                   # every gate passed
 "gates": [{"name": "unweighted_vertices", "value": 0, "limit": 0, "pass": True}, ...],
 "created": {"objects": [...], "meshes": [...]},   # datablocks this call added, by kind
 "blender": [major, minor, patch],
 "dominant_vertices": {...}}                   # module-specific keys
```

**When Blender cannot read the skill directory** (another machine, a sandboxed install), send the
source followed by the run call, in one call:

```python
import sys, types
def load(name, source):
    module = types.ModuleType(name)
    sys.modules[name] = module               # so `import bcr_common` in the next one resolves
    exec(compile(source, name + ".py", "exec"), module.__dict__)
    return module
load("bcr_common", r'''<contents of bcr_common.py>''')
bcr_skin = load("bcr_skin", r'''<contents of bcr_skin.py>''')
result = bcr_skin.run({"mesh": "Runner", "armature": "RunnerRig"})
```

Load `bcr_common` first; `bcr_fbx` also needs `bcr_pose` loaded before it.

`scripts/rig_gate.py` and `scripts/frames_preview.py` run on the host and never go through the server.

## 3. Worked example

The courier run's runner: a plush mascot with short limbs and long ears, swinging a delivery
mallet at the latch of a gate.

1. **Prep.** `name: "Runner"`, `collection: "Character"`, `height: 1.2`. A 20,000-triangle GLB
   goes from 14,991 vertices to 9,994 with every face kept, in 13 islands.
2. **Survey.** 20 z slices; boxes for each hand, foot, ear base, ear tip and the tail.
3. **Armature.** `RunnerRig`, 22 bones with `mirror: true`: `Root` (non-deform), `Hips`, `Spine`,
   `Chest`, `Head`, `Tail`, and per side `Ear`, `EarTip`, `UpperArm`, `LowerArm`, `Hand`,
   `UpperLeg`, `LowerLeg`, `Foot`. Radii: torso 0.20–0.21, head 0.30, arms 0.062, legs 0.10.
4. **Skin.** Defaults, plus one `gradients` chain per ear (`Ear`, `EarTip`, parent `Head`).
5. **Extreme pose.** One arm straight up, the other forward, head turned, spine bent, one ear
   folded, a leg lifted; one still; reset.
6. **Prop.** `Mallet`, prepped without a weld, attached to `Hand.R` with `length: 0.62`.
7. **Action.** `GateLatchSwing`, frames 1–40 at 24 fps, `loop: true`, 10 bones keyed at frames 1,
   8, 13, 15, 18, 20, 23, 27, 34, 40; contact is frame 18.
8. **Probe.** A first pass that swings too far reads `direction_z` near −1 with the striking edge
   at floor height; the keys are corrected before any render. `GateLatch` goes at the measured
   contact, the probe is rerun with `target`, and `key_object` keys `GateLatchPop` on the latch.
9. **Preview.** Frames [1, 20] and [21, 40] at 50%, then the GIF and a sheet of the key frames.
10. **FBX.** `RunnerRig`, `Runner` and `Mallet` exported, re-imported into a scene `FbxCheck`,
    gated, discarded. The baked take has 229 f-curves against 30 authored: expected.

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

## Related skills

`comfyui-asset-generation` for the GLB this starts from · `codex-visual` for the image and
four-view sheet that job is fed · `unity-rigged-character` for the Mixamo route and everything
after the FBX reaches Unity · `blender-retarget` for stock or purchased clips moved onto this rig
and kept as a library · `unity-3d-models` for props that stay static · `unity-debug` for proving
the action plays in the running game.
