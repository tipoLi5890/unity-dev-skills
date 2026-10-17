# Triage: which layer is wrong, and when to stop

> Part of the `blender-retarget` skill. How a `brt_*` module is called and what every `run`
> returns are in `SKILL.md`.

## First: the quality target

Before any triage or refinement, set the quality target with the user: camera distance, which
shots, which body parts must hold up. Stop at the target. A request to stop refining stands until
the user sets a new target; a request to document or archive is not a request to redo assets.

## The layer

A rigged, retargeted character can be wrong in four layers. Each has a test that clears it and a
place where its fix belongs. Change one layer at a time, and compare the same camera at the same
frame before and after; a comparison across cameras or frames proves nothing.

### The four layers

| Layer | It is this layer when | Look at | Fix in |
|---|---|---|---|
| Geometry | holes, fused fingers, cloth joined to skin — already at rest, with the Armature modifier off | a clay render at rest, back faces culled and not | the source or a rebuild (last section) |
| Skinning | clean at rest; a pose dents, tears or drags | the worst frame, an extreme pose, region weights | weights (`reference/weight-repair.md`) or bone placement |
| Animation | the skin deforms cleanly but the motion is wrong: a limb points the wrong way, a joint over-extends, a pose mixes two clips | source and target overlaid at frame 1; the NLA and the active action | rest conversion, bone mapping, FK/IK switch values, action stacking |
| Material | clay looks right and the textured render does not | base colour, normal, occlusion and UV, one at a time | maps and UVs — never sculpt to fix a colour |

### Tests that separate them

Run in order and stop at the first that shows the fault. Hide the bone overlay first: control
shapes and wires read as broken faces.

1. **Rest pose, clay, Armature modifier off.** A fault here is geometry. Go to the source.
2. **Rest pose, modifier on.** Any change from step 1 means the bind is off: a bone moved after
   skinning, or a scale left unapplied.
3. **The worst frame, clay.** A fault that appears here is skinning or animation.
4. **The same frame, mesh hidden.** The skeleton alone in the wrong pose: animation. The skeleton
   right and the skin wrong: skinning.
5. **The same frame, textured.** A fault that appears only now is material.

The animation causes, cheapest to rule out first:

- **Rest mismatch.** A clip from the T-pose rig on an A-pose target leaves every arm off by the
  difference between the two rests. Convert the rest pose before baking, traceably — never by
  adding a few degrees to the shoulders across a batch.
- **FK/IK mode.** A clip baked onto FK controls plays wrong while the limb is in IK. The switch
  value is animation data: key it with the clip.
- **Mapping.** A hand or finger chain fitted to the wrong bones tears the hand. Leave it out of the
  map until a mapping for that side is checked on one clip.
- **Stacking.** The active action evaluated over a live review track (`reference/action-library.md`).

## The picture wins

A gate proves its own number and nothing else. When a change improves the number while the
picture gets worse, revert to the last version whose picture was right, and keep that one.

- A contact solver that iterates finger vertices against a handle lowers its count of
  intersecting pairs on every pass while the fingers grow spikes. The count says better; the hand
  says worse. Revert. Cap any fit or contact displacement against the feature it fits: a vertex
  moved by more than about a quarter of the handle's radius is a spike, not a grip.
- `weights.weight_sum_error` passing says the deform weights sum to 1; `drift.max_drift` and
  `drift.max_rotation` passing say the prop kept its place and its angle on the hand at the frames
  sampled. Neither says the shoulder or the grip looks right.
- Save the last good file under its own name before every experiment.
- Keep failed scripts and their logs so the attempt is not repeated, not so it can be rerun.

## A fixed grip, not a solver

A held prop that cuts through the fingers is solved by two pieces that never interact:

- **A grip shape key on the character mesh**: only the finger vertices near the handle, smoothed
  into a closed shape. A shape key moves vertices and nothing else, so topology and UVs are kept,
  and value 0 gives the open hand back: it is reversible. Every vertex away from the handle stays
  at its basis position.
- **An anchor Empty on the hand bone**, with the prop parented to it. The Empty is the socket:
  parent it to the bone, update, then assign its world matrix — the order in
  `blender-character-rig` → `reference/prop-on-bone.md`. Change the grip angle only on the
  Empty's local offset, in a copy of the file; never move the prop's geometry and never add a
  second constraint.

After moving the anchor, run `brt_drift` over every clip, not one. It measures the prop against
the anchor bone once at rest, then at `samples_per_action` frames of each action (every NLA track
muted): `drift.max_drift` is the largest slip of the grip point in metres (`tolerance`, default
2e-5), `drift.max_rotation` the largest turn of the prop against the hand in degrees
(`rotation_tolerance`, default 0.5): a prop that spins about its own grip moves no grip point, so
the distance alone passes it. `per_action` and `per_action_rotation` give each clip's own largest,
`worst` and `worst_rotation` the clip and frame. The grip point is `grip_local`, a 4x4 in the prop's own
space (else the prop's `brt_grip_local` property, else its origin). Then look at the extreme
frames of several clips: a grip that suits idle can put the prop through the head overhead.

The grip shape does not show: read the driver before anything else. A driver with a scripted
expression outside the simple-expression subset does not run while the file's Python auto-run is
off; `brt_audit` lists such drivers as `python_drivers`, and broken ones as `invalid_drivers`.
Use a simple expression or a single-property driver, or key the shape value. Do not change the
machine's security settings to preview it, and do not rig again.

## Stop rules

- **The same input, the same parameters and the same error are never sent again.** Change one
  thing, or stop.
- **Pick one diagnostic that can answer the cause** — a render with one layer isolated, a probe of
  one region, one stage's output — instead of another full run.
- **No gain from it: record the limit and keep the working baseline.** A character that animates
  with known flaws is worth more than one that is never finished.
- **Stop at the quality target** set first (top of this page); refine past it only on a new
  target from the user.
- **Close-up hands are a rebuild**, not more solver passes: retopology, finger bones, or a hand
  modelled closed. At gameplay distance a static hand around a handle reads as held.
- **Fix only the layer the user is looking at.** Without a new request, the asset stays as it is.

## The failure log

One row for every failure that took more than one attempt. Write what was seen, what was tested,
what was ruled out and what is still uncertain. A guess is not a cause: a process that exited with
a code nothing explained is logged as "exited with code N", not given a named reason.

| Symptom | Evidence | Action taken | Avoid next time |
|---|---|---|---|
| Every arm in `HurdleVault` angled down | source and target at frame 1: the T-pose rig against the A-pose target | rest conversion before the bake, one clip first, then the batch | verify one clip before any batch |
| Preview raises `KeyError: 'Runner_GateLatchSwing'`, or plays a stale take | a test take held the name: `brt_arp` baked `GateLatchSwing.001`, `brt_retarget` refused | lookup through the manifest's `action`, or `brt_clip` (`brt_library` `provenance_key: "brt_clip"`) | a name is not an identifier; delete test takes before a batch |
| Every clip of a batch reports failed | each bake succeeded; a metadata step after it raised `KeyError` on every clip | the report split into `bake` and `metadata`; the metadata checked before the first bake | a `dry_run` of one clip, read end to end, before the batch |
| The add-on lists many "preset bones do not exist" | the map was made for another skeleton | the map rebuilt from `source_bones` on this file | one map per `skeleton` hash |
| `Bone.select` raises `AttributeError` | Blender 5 keeps selection on the pose bone | `PoseBone.select` | read the API of the running version |
| `pack_all` fails | images no material uses, with paths that do not resolve on this machine | the unused images removed, then packed | `brt_audit` `images_without_users` 0 before packing |
| Weight-sum check fails right after a transfer | the sum included non-deform groups; a receiver clamped at 1 | `restore` from the backup, then one `transfer` that normalises deform groups only | never sum every group |
| Intersection count falls, fingers spike | the stills, not the count | reverted to the stable hand; fixed grip shape | a number is not art acceptance |

## When the mesh is wrong at the source

Geometry faults go back to generation. Bisect by stage, and keep each stage's output so the stage
that introduced the fault can be named:

| Stage | Keep | Look for |
|---|---|---|
| shape (the raw decode) | the mesh before remesh | sheets, slabs, a missing limb already here |
| remesh and decimate | the remeshed mesh | bounds shrunk, thin parts gone — compare extents and silhouette, never the face count |
| texture | the mesh before bake | one side's colours on another |
| bake or projection | each map on its own | colour projected onto surfaces the source never showed: skin onto clothing, front onto back |

- A wrong source — sides swapped, a bad orientation — is fixed in the source image. Re-seeding
  does not fix it.
- Save the workflow, the job and its check renders with every run, not only the last mesh.
- A good front view says nothing about the back or the UVs: look at clay, UV, normal and occlusion.
- "Looks like a hole" has four causes: missing faces, an inner shell showing through, flipped
  normals under back-face culling, a transparent material. Clay with and without culling first.
- The knobs per stage and their symptoms: `comfyui-asset-generation` →
  `reference/image-to-3d-tuning.md`.
