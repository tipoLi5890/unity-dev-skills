# Import and survey — one clean object, then numbers to place bones from

> Part of the `blender-character-rig` skill. The stub that loads a shipped module and the result
> shape every `run` returns are in `SKILL.md` and `reference/mcp-session.md`.

Two modules: `scripts/bcr_import_prep.py` turns a generated GLB into one object fit to rig;
`scripts/bcr_survey.py` reads where the joints are from the vertices. Their docstrings are the
contract for every parameter below.

## What arrives

An image-to-3D GLB is one mesh, one material and three images under the importer's helper objects.
Its origin sits at the bounding-box centre, its largest extent is just under one unit, and after
import it stands upright facing −Y. Two properties decide everything downstream:

- **A thin double shell.** Every face has an inward twin a hair's breadth behind it.
- **Every UV seam is a split vertex.** The mesh is far more vertices, in more loose pieces, than its
  surface suggests.

For a 20,000-triangle character: 14,991 vertices before the weld, 9,994 after, 13 islands, the
largest holding about two thirds of the vertices.

## `bcr_import_prep` — the complete call

```python
import sys, importlib
p = "<skill>/scripts"
if p not in sys.path: sys.path.insert(0, p)
import bcr_common, bcr_import_prep
importlib.reload(bcr_common); importlib.reload(bcr_import_prep)
result = bcr_import_prep.run({
    "glb": "/abs/path/runner.glb", "name": "Runner", "collection": "Character",
    "height": 1.2,              # metres; omit to keep the file's size
    "location": [0, 0, 0],
    "weld_distance": 1e-5,      # None skips the weld
    "normal_strength": 0.5,     # None leaves the material alone
    "backface_culling": True,
})
```

In order, it:

| Step | What it does | Why |
|---|---|---|
| Import | glTF import; raises unless the file holds exactly one mesh | a second mesh is a decision, not something to merge silently |
| Flatten | bakes the importer's transform into the mesh, unparents, removes the helper objects | the axis conversion lives on a parent empty; left there it becomes a rotated bind pose |
| Name | object and mesh `Runner`, material `RunnerMat`, linked only into `Character` | later calls find everything by name |
| Origin | moves the mesh so the origin is the centre of the base | a character stands on its origin; the rig's `Root` goes there |
| Height | uniform scale of the mesh data to `height` | bone radii and contact distances are in metres |
| Weld | `remove_doubles` by position at `weld_distance`, then smooth shading | seam vertices would otherwise take different weights and open under a pose |
| Material | backface culling on; normal-map `Strength` to `normal_strength` | culling hides the inner twin; plush fur baked as normals reads as wrinkles at full strength |
| Place | `location` on the object | scale and rotation stay identity |

**Gates:** `one_mesh`, `identity_scale_rotation`, `origin_at_base` (lowest vertex within 1e-4 of
z = 0), `weld_kept_faces` (face count unchanged by the weld).

**Returns:** `object`, `reused`, `vertices_before`, `vertices_after`, `faces`, `islands` (the eight
largest, by vertex count), `island_count`, `extents`, `height`, `custom_normals_before`,
`custom_normals_after`, `materials`.

- **Same `name` again imports nothing.** The call returns `reused: true` with the gates and counts
  of the object as it stands; `height`, `weld_distance`, the material settings and `location` are
  not applied a second time. To prep differently, remove the object and the data it brought
  (`reference/scene-discipline.md`) or use another name.
- **A prop that will not be skinned** takes `weld_distance: None`; give it its own `name` and
  `collection` and leave `height` out when its size is set later.
- **Facing.** `.L` is the character's left: +X when the character faces −Y. Confirm the facing
  before measuring anything — a still from a camera on −Y shows the face.
- **Never delete the inner shell or the small islands.** The baked normal and occlusion maps
  address them, and deleting is destructive. Culling hides the twin; positional weights give it the
  same weights as the face in front of it.

## The weld check

The weld merges by position only. UVs live on face corners, so seams survive; custom normals
survive; no face and no island is dropped. Two numbers in the result say so — `weld_kept_faces`
passes and `custom_normals_after` equals `custom_normals_before`. `island_count` is the welded
figure: it falls as seam-split pieces rejoin. Then check it as a picture:

1. Run `bcr_import_prep` once more with another `name` (`RunnerRaw`), the same `height` and
   `location`, and `weld_distance: None`.
2. Hide `Runner` from the render, render `RunnerRaw` with `bcr_preview` (`still`, a fixed `camera`,
   its own `prefix`); swap which one is hidden and render again through the same camera.
3. Compare the two files on the host. **The difference is confined to seam pixels.** A difference
   that spreads over a surface means the distance merged vertices that were not twins: lower
   `weld_distance` and prep again.
4. Remove `RunnerRaw` and the mesh, material and images its import added, each only at zero users.

## `bcr_survey` — the complete call

Reads only. Coordinates are mesh-local: origin between the feet, +Z up, the character's left on +X.

```python
import sys, importlib
p = "<skill>/scripts"
if p not in sys.path: sys.path.insert(0, p)
import bcr_common, bcr_survey
importlib.reload(bcr_common); importlib.reload(bcr_survey)
result = bcr_survey.run({
    "mesh": "Runner",
    "z_slices": 20,                  # horizontal slabs, feet to top
    "x_slices": 14,                  # vertical slabs across the width
    "x_band": [0.0, 0.5],            # height range the x slabs look at, as fractions
    "boxes": {                       # [[x_lo, x_hi], [y_lo, y_hi], [z_lo, z_hi]]; None is open
        "hand_l": [[0.30, None], [None, None], [None, 0.60]],
        "ear_tip_l": [[0.0, None], [None, None], [1.13, None]],
    },
})
```

**Returns:** `mesh`, `min`, `max`, `size`, `z_slices`, `x_slices`, `boxes`.
**Gates:** `has_vertices`, `empty_boxes` (names of boxes that caught nothing; such a box returns
`centroid: None`, `count: 0`).

| Entry | Keys | Reads as |
|---|---|---|
| z slice | `z` `[lo, hi]`, `x` and `y` ranges, `count`, `parts` | one horizontal slab; `parts` is the number of separate runs of vertices along X |
| x slice | `x` `[lo, hi]`, `z` and `y` ranges, `count` | one vertical slab, inside the `x_band` height range only |
| box | `centroid`, `count`, `min`, `max` | the vertices inside an axis-aligned box |

`parts` splits wherever neighbouring X values are further apart than `gap` — a fraction of the mesh
width, default 0.04. Legs that nearly touch need a smaller `gap`; a sparse slab that reports stray
parts needs a larger one or fewer `z_slices`. An empty slab is left out of the list.

## From slices to landmarks

Read `z_slices` bottom to top. `parts` gives the heights; the `x` and `y` ranges give the widths.

| Going up, the slices show | Landmark |
|---|---|
| `parts` 2 from the floor | the two legs; the top of this run is the crotch, the hip joints sit just above it |
| `parts` 1, wide | hips and belly |
| `parts` 3 | arms hanging beside the body: the bottom of the run is the hand, the top is the shoulder |
| `parts` 1 with the narrowest `x` range between two wider runs | the neck (lower down, the waist) |
| `parts` 1, wide again | the head; its centre is the middle of this run, its radius half the widest `x` range |
| `parts` 2 above the head | the ears; the first such slice is the ear base, the last slice is the tip |

`parts` counts along X only: a tail behind the body never splits a slice, it shows as a `y` range
that reaches further back (+Y) than the slices above and below. Arms that lie against the body
closer than `gap` do not split one either; there the `x` range widening is the only sign, and
`x_slices` take over — with `x_band` on the lower half, the outermost slabs hold nothing but arm, and
their `z` range is how far down the hand reaches.

Heights from the slices are slab-coarse. **Positions come from boxes**: one more `bcr_survey` call
whose boxes are cut from the heights just read, each bounded to one side so the centroid is of one
limb and not of a symmetric pair.

| Landmark | Box | Take |
|---|---|---|
| Hand | x beyond the torso's half width, z between hand bottom and wrist | `centroid`; `max` − `min` gives the limb's thickness |
| Foot | x ≥ 0, z in the lowest slab or two | `centroid` x and y for the leg's axis; `min` y for the toe |
| Elbow, shoulder, knee, hip | the same x bound, repeated in z bands up the limb | `centroid` of each |
| Ear base, mid, tip | x ≥ 0, three z bands over the `parts` 2 run above the head | three `centroid`s — a bent ear is a chain through them |
| Tail | y beyond the back of the hips, z around hip height | `centroid` for the tail's tip end, `min` y for where it leaves the body |

- A bone runs through the middle of its limb: head and tail are box centroids, not points on the
  surface. Half the box's `max` − `min` across the limb is the starting value for that bone's
  `radius`.
- A box with a small `count` is a centroid of noise. Widen it until the count is a real share of
  the limb.
- Survey the +X side and let the armature mirror it; then read the same boxes with the x bounds
  negated. A right-side centroid that is not the left one mirrored, by more than a fraction of the
  limb's thickness, means the mesh is not symmetric there: `mirror` twins every `.L` bone, so
  switch it off and write both sides into the spec.
- The numbers go straight into the bone spec, in the same mesh-local coordinates
  (`reference/armature-and-skinning.md`).
