# Prop on a bone — the grip is measured from the prop

> Part of the `blender-character-rig` skill. How a `bcr_*` module is called and what every `run`
> returns are in `SKILL.md`.

`bcr_attach` finds where a handled prop is held from the prop's own vertices, moves the mesh
origin there, scales the prop, places it at a hand bone and parents it to that bone. One call,
two gates.

## Before the call

- **Rest pose, before keying.** The placement is computed from the bone's rest position; a prop
  attached to a posed rig moves away when the pose is cleared. Call `bcr_pose` with `op: "reset"`
  and read `pose_is_rest` first.
- **Prep the prop like the character, without the weld**: `bcr_import_prep` with
  `weld_distance: None` and `normal_strength` to taste. It must arrive with an identity transform
  and its long axis along `axis`, free end of the handle at the low end. A prop generated lying
  down needs its mesh turned upright first.
- The prop is generated on its own, never in the character's hand
  (skill `comfyui-asset-generation`, its image-to-3D reference).

## The grip measurement

All fractions run along `axis` from the handle's free end (0) to the far end of the head (1).

| Parameter | Default | What it selects |
|---|---|---|
| `axis` | `"Z"` | the prop's long axis, in its own space |
| `end_slice` | 0.10 | the free end: the lowest tenth. Its centroid across the other two axes **is the handle's axis** |
| `grip_at` | 0.27 | where the hand holds; the mesh origin moves to this point on the axis |
| `radius_band` | `[0.22, 0.28]` | a stretch that is certainly bare handle; the farthest vertex from the axis inside it is the handle radius |
| `max_radius_ratio` | 0.15 | limit for the gate below |
| `length` | none | metres along `axis` after scaling; omit to keep the prop's size |
| `rotation` | none | steps in armature axes, as in `bcr_pose` |
| `position` | middle of the bone | an armature-space point for the grip |

The free end is used because it is the one place where nothing but handle exists. A centroid
taken over the whole prop, or over a band that reaches the head, lands beside the handle: the
head pulls it sideways, and the prop then orbits the hand instead of turning in it.

## The ratio is the sanity number

`handle_radius_ratio` = handle radius ÷ prop length. A handle is a few percent of the prop's
length across. The gate passes for 0 < ratio ≤ `max_radius_ratio`.

| Ratio | Reading | Change |
|---|---|---|
| a few percent | bare handle, axis on the handle | none |
| near 0.3 | the band or the end slice caught the head | wrong `axis`, the prop is upside down, or the handle is short: lower `radius_band` and `grip_at` |
| just over the limit | a pommel, strap or flare inside the band | move `radius_band` to a clean stretch |
| 0 | no vertex inside the band | widen `radius_band` |

After a failed gate the prop is already attached: put it back as in "Calling again" before the
next try.

A passing ratio with a prop that still sits off the palm means the free end is not a clean
cross-section (a loop, a tassel): shrink `end_slice`, or pass `position`.

## The Mallet

```python
result = bcr_attach.run({
    "prop": "Mallet", "armature": "RunnerRig", "bone": "Hand.R",
    "axis": "Z", "end_slice": 0.10, "grip_at": 0.27, "radius_band": [0.22, 0.28],
    "length": 0.62,
    "rotation": [["Z", -90], ["X", 15]],
    "max_radius_ratio": 0.15,
})
```

Returns `prop`, `bone`, `length`, `handle_radius` (both after scaling), `head_side`,
`world_position` and `reused`.

- **`length`** is a design decision against the character: 0.62 m is about half the runner's
  height.
- **`head_side`** is a unit vector in the prop's own axes: the side the head overhangs the
  handle. Choose the first `rotation` step from it. With `head_side` `[1, 0, 0]`, `["Z", -90]`
  turns it to −Y, the character's front; with `[0, 1, 0]` the step is `["Z", 180]`. The second
  step, `["X", 15]`, tips the head forward of the hand. A head centred on the handle (a
  two-faced mallet) has no side: `head_side` is then only its small asymmetry — pick the facing
  from a still.
- **Two calls are normal**: the first without `rotation` to read `head_side`, then the redo
  below with it.
- **Check with a still**, front and side (`bcr_preview`, `still`): the handle crosses the palm,
  the head faces front, nothing intersects the ear at rest.

## Parenting

Bone parenting (`parent_type` `BONE`) attaches the child at the bone's **tail**, not its head, so
setting the parent moves a prop that was already placed. The module therefore sets
the parent, updates the view layer, assigns the wanted world matrix again and updates once more.
The gate `world_drift_after_parenting` (< 1e-4) compares the result with the wanted matrix.

The same order applies to anything parented to a bone by hand: parent, update, then assign
`matrix_world`.

## Calling again

- A prop already parented to that bone by this module returns `reused: true` with the stored
  measurement and changes nothing — **new parameters are ignored**, except `max_radius_ratio`,
  which the stored ratio is gated against.
- To change `rotation`, `grip_at`, `length` or the bone, put the prop back first, then call:

```python
import bpy
from mathutils import Matrix
prop = bpy.data.objects["Mallet"]
prop.parent = None
del prop["bcr_attach"]
prop.matrix_world = Matrix.Identity(4)     # the origin is already the grip
```

  The mesh is upright again with its origin at the old grip; the fractions measure the same
  handle, and `length` rescales from the current size.
- The call edits the prop's mesh data (origin, scale). A mesh shared with another object moves
  there too: make it single-user first.

## Keeping the grip stable across clips

A prop that has to ride through many clips (keyed here, or retargeted onto the rig) keeps one fixed
local offset to the hand bone. Nothing is re-solved per frame, so every clip carries it the same way.

- **The anchor Empty.** An Empty parented to the hand bone at the rest pose, placed at the grip, in
  the order under Parenting above. The prop is parented to the Empty with an identity local matrix
  (`matrix_parent_inverse` and `matrix_basis` both identity), so its origin, the grip point, sits on
  the Empty.
- **The grip angle lives on the Empty's local offset**, and only there. Change it in a copy of the
  file; never move the prop's geometry, key the prop on its own, or add a constraint beside the
  parent.
- **Check it after each set of clips** with `brt_drift` (skill `blender-retarget`). It reads the
  prop against the anchor bone once at rest, samples every action, and gates `drift.max_drift`
  (the grip point's slip, `tolerance` 2e-5 m by default) and `drift.max_rotation` (the prop's turn
  against the hand, `rotation_tolerance` 0.5° by default: a prop spinning about its grip moves no
  grip point); a failure names the action and frame in `worst` or `worst_rotation`. The usual causes
  are a prop keyed on its own, a clip that left the arm in IK, or a parent on the wrong bone. In the
  saved file, `brt_audit --props` checks each listed parent: the anchor on the hand bone, the prop
  on the anchor.
- **After moving the anchor, look at several clips at their extreme frames**, not one: a grip that
  suits an idle can put the prop through the head on an overhead swing.

**A grip shape key is optional.** When the open hand reads badly around the handle, add a shape key
on the character mesh that moves only the finger vertices near the handle, smoothed toward a closed
shape. A shape key moves vertices and nothing else: topology, UVs and the vertex count are kept, and
value 0 gives the open hand back. Cap every vertex's move at about a quarter of `handle_radius`: a
finger pushed farther than that toward the handle becomes a spike, however few intersections are
left. If its value must follow whether the prop is shown, drive it from
the prop's hide flag with a simple expression such as `1 - hidden`, or key the value. An expression
outside Blender's simple-expression subset does not run while the file's Python auto-run is off,
and no driver survives the FBX export: key the result there.

## Limits

- **A static hand does not close.** The mitten stays open and the handle passes through the
  palm. From a gameplay camera it reads as held; a close-up needs finger bones or a hand
  modelled closed.
- **One hand.** The prop follows `Hand.R` alone; on short arms the hands do not meet, so there is
  no two-handed grip.
- **No swap, no drop.** The prop is a rigid child of one bone for the whole action. Handing it
  over or letting go is a second object or a constraint keyed by hand.
- **The prop does not deform** and takes no weights; it leaves Blender as a child of the bone
  (`reference/fbx-export.md`).
- **Contact is measured afterwards**, on the keyed action, from the striking edge
  (`reference/action-and-preview.md`).
