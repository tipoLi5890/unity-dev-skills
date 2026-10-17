# Weight repair: moving skin weights locally

> Part of the `blender-retarget` skill. How a `brt_*` module is called and what every `run`
> returns are in `SKILL.md`.

A dent or a pull that appears only when a joint moves is a weight fault when the rest pose is
clean and the joints sit where the body bends. Repair it in place: measure the region, move weight
from the influences that reach too far to the bones that should hold it, normalise the deform
groups only, and keep a backup that undoes exactly what changed. `brt_weights` runs the steps
(`probe`, `snapshot`, `transfer`, `normalize`, `restore`); this file is the method.

## Before touching a weight

- **Read the sums right after binding**, before any clip: `probe` with no `mask`, band or bones
  covers the whole mesh. `deform_sum` should read 1 everywhere; `all_group_sum_max` counts every
  group, and non-deform groups (modifier masks, control-bone leftovers) can push it to several
  times 1 on a correct skin. Judge the deform sum only.
- **Confirm the layer**: clean at rest, faulty only in a pose
  (`reference/defect-triage-and-stop.md`). A dent visible at rest is geometry; a crease centred
  away from the anatomical joint is bone placement. Move the bone or rebuild the mesh: weights fix
  neither.
- **Weights you can regenerate are fixed at their input.** When a generator produced them from
  parameters (radii in `blender-character-rig`'s `bcr_skin`), change the parameter and skin again.
  Local repair is for weights you keep.
- **Read the Armature modifier.** With `use_deform_preserve_volume` off, try it first, with one
  still before and after. Already on: weights are next.
- **Save As a new file** before the first write. The previous file is the safest comparison.
- **Fix the views now**: the clip and frame where the fault is worst, one extreme pose
  (`blender-character-rig` → `reference/armature-and-skinning.md`), a camera that will not move.
  Render the "before" stills before any edit.

## Probe the region

`probe` reads only. Everything is world space at rest: vertices through the mesh object's matrix
(`v.co` is the undeformed coordinate whatever pose the rig holds), bone heads and tails through the
rig's, with the rig's `pose_position` at REST for the call.

| Field | Reading |
|---|---|
| `inside_vertices` | vertices with mask weight > 0.5: the size of the edit; gate `weights.region_vertices` > 0 |
| `touched_vertices` | mask weight > 0: what `snapshot` and `transfer` cover |
| `would_change` | touched vertices that hold a from-bone weight and have a to-bone on their side |
| `mean_weight` | per from- and to-bone, inside: who owns the region; a limb group with a large mean on the midline is the suspect |
| `deform_sum` | min, mean, max of the deform sum inside: should be 1; less is unweighted share |
| `all_group_sum_max` | the largest sum over every group, non-deform ones included: for reading, never the skin check |
| `mean_share` | each to-bone's mean share inside: the hand-over the share rule below gives |
| `region`, `rig_height` | the region in world units as resolved, and the rig's rest height the fractions use |
| `rig_origin_on_axis` | where the rig origin sits on `axis`: the mask reads `|c|` about the plane c = 0 |
| `applied` | the recipe hashes already applied to this mesh |

A mean is a mean: half the shoulder on average is not half on every vertex. The influence count
per vertex is not reported; count it by hand when the engine's limit (4 in Unity by default) is
close. Then name the suspects (`from_bones`, the influences that reach too far) and the receivers
(`to_bones`, the neighbouring deform bones that should hold the region).

`Runner`'s upper back follows a raised arm. Region: inside the two shoulder joints, from the
`Spine`–`Chest` joint to the neck. Readout: `UpperArm.L` and `UpperArm.R` carry a large share on
the midline. Suspects: the two upper-arm groups. Receivers: `Spine` below, `Chest` above.

## The mask

The vertices are chosen and the edit faded with a smooth mask, so no seam marks where it stops:

```text
s(a, b, x) = t²·(3 − 2t),   t = clamp((x − a) / (b − a), 0, 1)
m          = s(inner, outer, |c|) · s(z_lo, z_lo + feather, z) · (1 − s(z_hi − feather, z_hi, z))
```

`c` is the coordinate on `axis` (default X); `mask` gives `inner` and `outer` in world units. With
`inner` < `outer` the mask is 0 inside `inner` and 1 past `outer`; `inner` > `outer` keeps the
middle band instead. The Z band is either factor's partner, and `transfer` needs at least one:

- `z_band_fraction: [lo, hi]`: fractions of the rig's rest height (lowest to highest bone head or
  tail, 0 at the lowest), so one recipe reads the same on a taller or shorter build of the body.
  `feather` is then a fraction of the height too.
- `z_band: [z_lo, z_hi]`: world Z, for a band measured on this file only.
- Four values `[lo_start, lo_full, hi_full, hi_end]` in either form give each end its own fade
  (a long fade up the back, a short one under the neck) in place of `feather`.

Only vertices with `m > 0` are touched; `probe` reports the band it resolved to.

Every bound is a measurement of this body in this rest pose. From `RunnerRig`'s bone spec (rest
height 1.19 from `Root` to the ear tip, shoulder joint at x 0.19, arm radius 0.062, `Spine` from
z 0.27, `Chest` from z 0.36 to the neck at 0.47):

| Param | Derive from | Runner |
|---|---|---|
| `mask.inner` | shoulder joint x minus the arm's radius: the fade ends before the arm's own skin | 0.13 |
| `mask.outer` | about half of `inner`: full strength on the midline band (`inner` > `outer`) | 0.06 |
| `z_band_fraction` | from the middle of the lower receiver (0.32 / 1.19) to the neck (0.47 / 1.19) | `[0.27, 0.40]` |
| `feather` | the fade inside each end of the band (default 0.05) | 0.03 |
| `amount` | below 1, so the limb keeps some pull (default 0.85) | 0.8 |

At `amount` 1 the region goes rigid when the arm lifts. A mask copied from another character
edits the wrong vertices: measure height, chest, shoulder joint and armpit again for every body.

## The transfer

Per touched vertex, from its current weights:

1. Each suspect group with weight `w` gives `amount · m · w`; `T` is the sum given.
2. Each receiver `k` gains `T · share_k`.
3. The deform entries are normalised in memory (next section).
4. Each value is written once, with `REPLACE`. Groups missing for receivers are created.

**The share rule** (`share`). The default, `z_split`, takes one or two receivers stacked up the
body. With two, the vertex's height decides: `t = s(z0, z1, z)`, `1 − t` to the lower receiver and
`t` to the upper, where `z0` and `z1` are their rest head heights, or `split_band` (world) /
`split_band_fraction` (of the rig height) when the hand-over belongs elsewhere. With one, it takes
everything. For `Runner`: `Spine` below its head height, `Chest` above the `Chest` head, a smooth
hand-over between.

`share: "reach"` is an option for receivers that are not stacked along Z (a mirrored pair, three
or more): `share_k ∝ 1 − s(0, reach_k, |along_k|)`, where `along_k` is the vertex's distance from
the receiver's head along its rest axis and `reach_k = max(length_k, distance to the farthest other
receiver head)`. A receiver whose head is off the mirror plane by more than `feather` takes only
from its own side (faded over ±`feather`). Where every share is 0 the nearest receiver on the
vertex's side (by segment distance) takes it all; a vertex with no receiver on its side keeps its
weights. Probe it first: `mean_share` shows the hand-over it gives.

**Compute, normalise, then write.** `VertexGroup.add` clamps every weight to [0, 1]: a receiver
pushed past 1 before normalising is cut at 1, and normalising afterwards keeps the wrong ratio.

**Count influences after the write.** A vertex that had four influences and gains a receiver has
five. The module does not cap them; above the engine's limit, drop the smallest and renormalise,
rather than leave the choice to the importer.

## Moving skin to fit a prop: cap the move

Weights are not the only local edit. Closing a gap between a palm and a held handle, or pushing
skin out of a prop it passes through, moves vertices. Cap every such displacement relative to the
feature it fits: at most about 25% of the handle's radius (or of the gap's own size), faded to 0 at
the edge of the region the same way as the mask above. A move larger than the feature it fits
pulls single vertices into spikes that show in every frame of every clip. When the cap leaves a
visible gap, the grip pose or the prop placement is wrong: move the prop or key the fingers.

## Deform groups only

`v.groups` lists every group the vertex is in. Only a group named after a bone with `use_deform`
on the armature driving the mesh is skin; modifier masks, groups named after control bones and
leftovers sit in the same list.

```python
rig = bpy.data.objects["RunnerRig"]
deform = {b.name for b in rig.data.bones if b.use_deform}
```

- Normalising divides the deform weights of each vertex by their sum, without clamping first, and
  folds the float32 rounding into the largest. Non-deform groups are not changed or counted.
- `normalize` does that over the region (the whole mesh with no `mask` or Z band); a vertex
  whose deform sum is 0 is skipped and counted in `zero_sum_vertices`.
- A sum over all groups is not a skin check: it fails on a correct mesh and passes a wrong one.

## Backup and the apply-twice guard

`snapshot` stores **every** membership of each vertex the mask touches (every vertex when neither
`mask` nor a Z band is given), not only the groups that move, as `.npz` at `backup_path`. An
existing file is refused unless `overwrite: True`: it could be the only copy of the weights.

| Array | Content |
|---|---|
| `vertices` | every vertex covered |
| `vidx`, `gidx`, `weight` | one row per existing membership, zero weights included; `gidx` indexes `group_names` |
| `group_names` | the group names when the backup was taken |
| `n_vertices`, `mesh` | the mesh's vertex count and object name |
| `applied`, `region` | the guard property's value then; the region as JSON |
| `format` | the layout, 2; a format-1 backup (no `topology`) restores with the warning "legacy snapshot format 1: topology not verified" |
| `topology` | a sha256 over the vertex, face and corner counts and every corner's vertex index |

**Snapshot first.** `transfer` refuses unless `snapshot` wrote `backup_path` for this mesh in
this file session (kept in `bpy.app.driver_namespace`, cleared when a file loads), unchanged since,
from the same vertex count, covering every vertex the mask touches (`require_snapshot`, default
true; `normalize` checks it only when set).

**The guard is a hash list on the mesh**: the custom property `brt_weights_applied`. `transfer`
hashes its recipe (mesh, armature, bones, the region as resolved, `share`, `amount`) and appends
the hash after a write that changed vertices. The same recipe again is a no-op: `reused: True`,
gate `weights.already_applied`, nothing written. A different recipe applies on top of the current
weights.

The backup is valid only while the vertex count **and** the indices are unchanged. Retopology,
decimation, remesh, merge by distance, separating parts or applying a modifier that adds or removes
geometry all renumber vertices. Do not trust a backup after any of these even when the count
happens to match. Restore works by group name, never by index: groups may have been added since.

## Restore

1. Refuse when the vertex count or object name differs from the backup's (raises), or the
   topology hash does (reason `topology_mismatch`, `weights.topology` failing, nothing written;
   `allow_topology_mismatch: True` overrides).
2. On every backed-up vertex, remove each deform membership the backup does not list
   (`group.remove([index])`); no zero is written in its place. Skip this and the receiver entries
   the transfer created stay: writing the backup's own entries back never touches them.
3. Write every stored (group name, weight) row back with `REPLACE`, creating a group that is gone.
4. Read it back: gate `weights.restored`. On a pass, `brt_weights_applied` goes back to its value
   at snapshot time (removed when there was none).

## The five ops

| Op | Does | Gates |
|---|---|---|
| `probe` | the region statistics above; changes nothing | `weights.region_vertices` > 0 |
| `snapshot` | writes the backup; changes no weight | `weights.snapshot_written` |
| `transfer` | mask, move, normalise in memory, one write, then the guard; a repeated recipe is a no-op | `weights.changed_vertices` > 0, `weights.sum_before_normalize` (info), `weights.weight_sum_error` < 1e-4, `weights.deform_only` == 0; `weights.already_applied` when reused |
| `normalize` | renormalises the deform groups in the region; moves nothing between bones | `weights.deform_only` == 0, `weights.weight_sum_error` < 1e-6 |
| `restore` | the procedure above | `weights.restored` < 1e-6; `weights.topology` failing when it refuses |

- `weights.weight_sum_error` is the largest |sum of deform weights − 1| over the changed vertices.
  A correct write reads float noise, around 1e-7; the skinning gate in `blender-character-rig`
  allows 1e-4. Anything larger means a deform group was skipped or a value was clamped.
- `weights.sum_before_normalize` always passes: it reports how far the sums were off before the
  normalise, for reading, not judging.
- `weights.deform_only` fails when a non-deform group changed, in weight or membership.
- `transfer`, `normalize` and `restore` overwrite weights: on a file with unsaved edits each adds a
  warning unless `acknowledge_destructive: True`, and with `strict: True` raises before writing.
- A failed write puts the touched vertices back and removes the groups it created. The call runs
  in Object Mode with the rig at REST and puts both back. Parameter names are in the docstring.

## Judge the picture

Same camera, same action, same frame, before and after, plus the extreme pose; back and side for
a fault on the back. It passes when the region keeps its volume at the worst frame, the raised
limb still pulls the skin next to its joint, and no new crease appears where the mask fades out.
A texture seam or a colour patch in the same place is a material fault: it stays, and the weight
repair does not claim it.
