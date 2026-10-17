# FBX export — write the file, read it back, compare

> Part of the `blender-character-rig` skill. The stub that calls a `bcr_*` module and the shape of
> every result are in `SKILL.md`.

An export that returns `FINISHED` says a file was written, not that the rig is in it. The file is
proven by importing it into a scene of its own and comparing a snapshot of what came back with a
snapshot of what went in.

## What goes in the file

The armature, the skinned mesh and the bone-parented prop: `RunnerRig`, `Runner`, `Mallet`. Name
them; do not export "everything visible".

- Every named object must be in the **active view layer** — the export selects them, and an
  object outside it cannot be selected (the call raises and names them). A rig built in a second
  scene needs that scene shown in the window first.
- The rig's assigned action is `GateLatchSwing`. The target `GateLatch` and its `GateLatchPop`
  are not in this file: a target is the level's object, exported or rebuilt on its own.
- Characters go out as FBX: Unity's Model Importer gives the Rig tab, the Avatar and the clip
  settings. A GLB through glTFast has none of them (`unity-rigged-character` →
  `reference/unity-import.md` §1).

## The four ops

```python
before = bcr_fbx.run({"op": "snapshot", "armature": "RunnerRig", "meshes": ["Runner", "Mallet"],
                      "path": "/abs/path/before.json"})
bcr_fbx.run({"op": "export", "objects": ["RunnerRig", "Runner", "Mallet"],
             "path": "/abs/path/runner.fbx",
             "options": {"apply_scale_options": "FBX_SCALE_ALL", "apply_unit_scale": True}})
after = bcr_fbx.run({"op": "reimport", "fbx": "/abs/path/runner.fbx", "scene": "FbxCheck",
                     "path": "/abs/path/after.json"})
# on the host: python3 scripts/rig_gate.py /abs/path/before.json /abs/path/after.json
# a later call: pass the reimport result's `created` back as a literal
result = bcr_fbx.run({"op": "discard", "created": {"objects": ["RunnerRig.001", "Runner.001", "Mallet.001"], "scenes": ["FbxCheck"]}})
```

| Op | Does | Gates / returns |
|---|---|---|
| `snapshot` | reads the rig; changes nothing | `snapshot`, also written to `path` |
| `export` | selects `objects`, makes the armature active, exports the selection, restores selection and active object | `finished`, `file_bytes`; returns `bytes` and the `options` used |
| `reimport` | creates scene `FbxCheck`, shows it in the window while importing, puts the window's scene back, snapshots what arrived | `one_armature`; returns `snapshot`, `scene`, `created` |
| `discard` | removes exactly the datablocks named in `created` | returns `removed` |

- A snapshot holds, per bone: parent, deform flag, head position in metres relative to the
  armature; per mesh: vertex and face counts, vertex groups in use, the largest number of
  influences on a vertex, unweighted vertices, world scale, the bone it is parented to; the
  armature's world scale; the action's name, frame range and f-curve count.
- `reimport` passes `anim_offset` 0. The importer's default shifts every key by one frame, which
  reads as an action that grew or moved.
- The .blend still holds the originals, so the re-imported objects are named `Runner.001`,
  `Mallet.001`. That is expected; nothing was renamed in the file.
- Take the snapshot **with the action assigned and the pose untouched** — after op `key`, not
  after an extreme-pose test that was never reset.
- Keep the whole `created` dict the `reimport` call returned: `discard` runs in a later call, where
  the earlier call's variables are gone, and removes only what that dict names (the example
  above shortens it).
- `discard` last, after the gate has run: the check scene, its objects, meshes, materials, images
  and the imported action all go, and the user's scenes are as they were.

## Exporter options

`EXPORT` in `scripts/bcr_fbx.py` holds the defaults; `options` overrides any of them. Read the
exporter's parameters on your Blender before relying on one — the bundled API docs list them.

| Option | Default | Why |
|---|---|---|
| `use_selection` | `True` | only the named objects |
| `object_types` | `{'ARMATURE', 'MESH'}` | no camera, light or empty |
| **`add_leaf_bones`** | `False` | see below |
| **`use_armature_deform_only`** | `False` | see below |
| `bake_anim` | `True` | the action is in the file |
| `bake_anim_use_all_bones` | `True` | every bone gets curves, keyed or not |
| `bake_anim_use_nla_strips` | `False` | no take per NLA strip |
| **`bake_anim_use_all_actions`** | `False` | see below |
| `bake_anim_force_startend_keying` | `True` | the take spans the whole range |
| `bake_anim_simplify_factor` | `0.0` | no key reduction: the curves are the authored motion |
| `mesh_smooth_type` | `'FACE'` | smoothing written per face |
| `path_mode` / `embed_textures` | `'COPY'` / `True` | textures travel inside the file |
| `apply_scale_options` | the exporter's own (`'FBX_SCALE_NONE'`) | not in `EXPORT`; pass `'FBX_SCALE_ALL'` with `apply_unit_scale: True` in `options` for a model that imports into Unity at File Scale 1 |

What each of the three costs when flipped:

| Flipped to | The file gets | And then |
|---|---|---|
| `add_leaf_bones: True` | an `_end` bone on every chain tip (ear tips, hands, feet, tail) | a longer bone list in Unity, more transforms per character, and `rig_gate.py` fails `bones` unless run with `--allow-leaf-bones` |
| `use_armature_deform_only: True` | no non-deform bones: `Root` is gone, and so is any socket or helper bone whose Deform flag is off, weighted or not | the skeleton's top bone is missing, and `rig_gate.py` fails `bones` (and `parents` wherever a deform bone hung from a non-deform one). A socket bone that must survive gets the Deform flag; it needs no weights |
| `bake_anim_use_all_actions: True` | every action in the .blend, written onto this armature — one authored for another object included — each named `<rig>\|<action>` and re-based to start at frame 0 | `GateLatchPop` arrives as a clip on the runner, and frame numbers no longer match the snapshot |

## Clip names: decide before Unity

With all-actions off the file carries **one take, named after the scene**, with its frame numbers
kept (1–40). Nothing in it says `GateLatchSwing`. Pick one:

| Choice | Clip name in the file | Use when |
|---|---|---|
| Rename the scene to the clip name before exporting | `GateLatchSwing` | one clip per file and the scene is yours to rename — it is a change to report |
| Leave the scene alone; rename the clip in Unity's importer | the scene's name (`Scene` by default) | the scene name must stay, or the import is scripted anyway |
| One action per .blend, all-actions on | `RunnerRig\|GateLatchSwing`, starting at 0 | several files, one action each; not while a reaction action shares the .blend |

Whichever it is, write the expected clip name and length down next to the file: the Unity check
below reads them.

## The gate

```bash
python3 scripts/rig_gate.py /abs/path/before.json /abs/path/after.json
python3 scripts/rig_gate.py /abs/path/before.json /abs/path/after.json \
    --allow-leaf-bones --position-tolerance 0.002
```

Stdlib only; prints one JSON object with `ok`, `gates` and `vertices`. It accepts a snapshot
file or a whole `bcr_fbx` report.

| Gate | Passes when |
|---|---|
| `bones` | the same bone names; extra `*_end` bones pass only with `--allow-leaf-bones` |
| `parents` | every bone has the parent it had |
| `bone_positions` | every head within `--position-tolerance` metres (0.001) of where it was |
| `groups` | every skinned mesh uses the same vertex groups, and no mesh is missing |
| `bone_parents` | a prop parented to a bone is still on that bone |
| `influences` | no vertex has more than `--max-influences` (4) weights, none is unweighted |
| `scale` | armature and meshes come back at scale 1 within `--scale-tolerance` (0.001) |
| `action` | an action came back with the same frame range and it has f-curves |

| Exit | Meaning |
|---|---|
| 0 | every gate passed |
| 1 | a gate failed — read its detail (`missing`, `moved`, `different`, `not_one`, …) |
| 2 | a snapshot is missing or unreadable |

Reading the output:

- **More f-curves after than before is expected.** The bake keys every bone: 229 curves for the
  22 bones against the 30 authored for ten. The gate asks only that there are some.
- **A vertex count that differs is reported under `vertices`, not failed**: an exporter may split
  vertices at seams.
- Meshes are matched by name with the `.001` suffix ignored. A bone-parented prop carries no
  vertex groups and is checked for presence, its bone and its scale.

| Failing gate | Usual cause | Fix |
|---|---|---|
| `bones` with `*_end` names | leaf bones switched on | switch it off, or accept them with the flag |
| `bones` / `parents`, `Root` missing | deform-only switched on | switch it off |
| `scale` | an object scale that was never applied, or a scale or unit option overridden | apply scale before skinning (`reference/armature-and-skinning.md`); drop the override |
| `bone_parents` | the prop was not in `objects`, or was parented to the armature object rather than the bone | export it, attach with `bcr_attach` |
| `action`, range off by one | a re-import without `anim_offset` 0 | use op `reimport` |
| `action`, range starts at 0 | all-actions on | compare lengths by hand, or switch it off |
| `influences` | weights edited after skinning | run `bcr_skin` again |

## The Unity check

The round trip proves the file against Blender's own importer. Then import it into a throwaway
Unity project and read the imported asset before the character is called done:

1. **Scale.** Model tab: File Scale 1. The root and the armature sit at (1, 1, 1) and the
   character stands at its authored height. Read three bones' world positions and compare with
   the snapshot's heads in metres under the axis change, Blender (x, y, z) → Unity (−x, z, −y):
   they match to the millimetre when scale was applied and the file was exported with
   `FBX_SCALE_ALL` (the example above). Anything else is unapplied scale in the .blend or an
   export without `FBX_SCALE_ALL`: fix it there, never with the importer's Scale Factor.
   `rig_gate.py`'s `scale` and `bone_positions` gates pass with or without that option, so the
   unit scale is read here, in Unity.
2. **The clip.** One clip under the expected name (the scene's, or `<rig>|<action>` with
   all-actions on), frames 1–40 at 24 fps (39 intervals, about 1.63 s), looping from its last
   frame into its first. The model's default pose in Unity is the clip's first frame, not the
   rest pose.
3. **The rig type: Generic.** Rig tab → Generic, Create From This Model. Sample the clip at a
   contact frame and compare a hand with the same frame in Blender: about a degree with the
   default Keyframe Reduction, a few hundredths with Anim. Compression Off. Humanoid only when the
   game needs a body-part mask or IK, and only after measuring its deviation on this clip — on a
   courier rig it moved bones up to 20° and a hand socket 13–15 cm; the extra `Ear`, `EarTip`
   and `Tail` bones and very short limbs also need the Configure screen there
   (`unity-rigged-character` → `reference/unity-import.md` §1).
4. **The prop.** `Mallet` is a child of `Hand.R` and follows it through the clip. With Optimize
   Game Objects on, the hand bone or socket survives only when listed in Extra Transforms to
   Expose, and it then sits directly under the model root, still following the hand.
5. **Materials.** Base colour and normal arrive bound. The metallic and roughness maps are in the
   FBX but Unity's material does not bind them: build the metallic/smoothness map in Unity
   (`unity-rigged-character` → `reference/textures.md`). With embedded textures, check that the
   bound images are this character's own and not same-named files elsewhere in the project.

The import steps themselves — rig type, Avatar, clip settings, the Animator — are in
`unity-rigged-character` → `reference/unity-import.md`.
