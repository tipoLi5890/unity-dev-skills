# Armature and skinning — bones from numbers, weights from position

> Part of the `blender-character-rig` skill. How a `bcr_*` module is called and what every `run`
> returns are in `SKILL.md`; the landmarks the spec is filled from come out of
> `reference/import-and-survey.md`.

Two calls: `bcr_armature` turns a bone spec into an armature, `bcr_skin` computes every vertex
weight from where the vertex is. Neither places or weights anything by eye; the picture comes
last, as the test.

## The bone spec

The spec is data, in the mesh's local coordinates (origin between the feet, +Z up, the character
facing −Y). The armature takes the mesh object's world transform, so the same numbers stay valid
wherever the character stands.

| Field | Meaning |
|---|---|
| `name` | bone name; it becomes the vertex group name |
| `head`, `tail` | the two ends, `[x, y, z]`; a bone shorter than 1e-5 fails the gate |
| `parent` | name of another bone in the spec; exactly one bone has none |
| `deform` | default true; false for a bone that carries no skin (`Root`) |
| `radius` | how far from the bone its surface lies; required on every deform bone |
| `segment` | optional `[[x, y, z], [x, y, z]]`: the stretch distances are measured to, instead of head → tail |

Call parameters: `name`, `collection`, `mesh`, `mirror`, `bones`.

- **`radius` is a measurement, not a tuning knob to start from.** Read it off the survey: half the
  width of the limb's slice, half the torso's depth. `bcr_skin` divides every distance by it, so a
  thick bone and a thin bone compete fairly for a vertex that lies between them.
- **`segment` is for a ball.** The head bone runs from the neck to the crown so that it pivots at
  the neck, but a ball's surface is equidistant from its centre, not from that line: give a short
  segment around the centre and keep the radius equal to the ball's.
- **A child whose head sits on its parent's tail is connected**; anywhere else it is parented
  with an offset (ears on the head, legs under the hips).

## Naming and side

- `.L` is the character's left: **+X** when the character faces −Y. In a front render the `.L`
  limbs are on the right of the picture.
- With `mirror: true`, author only the `.L` bones. Each gets a `.R` twin with x negated on `head`,
  `tail` and `segment`, and a parent renamed the same way. Centre bones are not mirrored.
  Authoring a `.R` bone as well raises "duplicate bone names".
- Mirroring is only as good as the mesh's symmetry: compare the survey's left and right box
  centroids first, and author both sides with `mirror: false` when they visibly disagree.
- Every pose bone is set to XYZ euler; `bcr_pose` writes eulers.
- The expanded spec is stored on the rig as the custom property `bcr_bones` (JSON). `bcr_skin`
  reads radii and segments from there, so a bone added by hand in edit mode has none and is
  refused. Change the spec and call again: an armature of that name gets its bones rebuilt in
  place.

## Worked spec — the runner

A 1.2 m plush courier: a ball head on a short torso, arms in an A-pose, long ears. Fourteen
authored bones, twenty-two after mirroring.

```python
result = bcr_armature.run({
    "name": "RunnerRig", "collection": "Character", "mesh": "Runner", "mirror": True,
    "bones": [
        {"name": "Root",  "head": [0, 0, 0],    "tail": [0, 0.18, 0], "deform": False},
        {"name": "Hips",  "head": [0, 0, 0.19], "tail": [0, 0, 0.27], "parent": "Root",  "radius": 0.21},
        {"name": "Spine", "head": [0, 0, 0.27], "tail": [0, 0, 0.36], "parent": "Hips",  "radius": 0.20},
        {"name": "Chest", "head": [0, 0, 0.36], "tail": [0, 0, 0.47], "parent": "Spine", "radius": 0.21},
        {"name": "Head",  "head": [0, 0, 0.47], "tail": [0, 0, 0.82], "parent": "Chest", "radius": 0.30,
         "segment": [[0, 0, 0.58], [0, 0, 0.74]]},
        {"name": "Tail",  "head": [0, 0.17, 0.24], "tail": [0, 0.30, 0.28], "parent": "Hips", "radius": 0.075},

        {"name": "Ear.L",    "head": [0.12, 0.02, 0.82], "tail": [0.17, 0.02, 1.02], "parent": "Head",  "radius": 0.062},
        {"name": "EarTip.L", "head": [0.17, 0.02, 1.02], "tail": [0.20, 0.01, 1.19], "parent": "Ear.L", "radius": 0.062},

        {"name": "UpperArm.L", "head": [0.19, 0, 0.43], "tail": [0.27, 0, 0.35], "parent": "Chest",      "radius": 0.062},
        {"name": "LowerArm.L", "head": [0.27, 0, 0.35], "tail": [0.34, 0, 0.28], "parent": "UpperArm.L", "radius": 0.062},
        {"name": "Hand.L",     "head": [0.34, 0, 0.28], "tail": [0.39, 0, 0.23], "parent": "LowerArm.L", "radius": 0.068},

        {"name": "UpperLeg.L", "head": [0.10, 0, 0.19], "tail": [0.10, 0, 0.11],     "parent": "Hips",       "radius": 0.10},
        {"name": "LowerLeg.L", "head": [0.10, 0, 0.11], "tail": [0.10, 0, 0.04],     "parent": "UpperLeg.L", "radius": 0.10},
        {"name": "Foot.L",     "head": [0.10, 0, 0.04], "tail": [0.10, -0.11, 0.02], "parent": "LowerLeg.L", "radius": 0.11},
    ],
})
```

Where each number comes from: the leg and ear x from the z slices whose `parts` is 2; the neck
(z 0.47) from the narrowest slice between torso and head; the shoulder from the highest slice with
three `parts`; hand, foot, ear base, ear mid, ear tip and tail from box centroids. `Root` carries no
skin and lies on the ground pointing back (+Y).

Gates: `bone_count` (22 here), `zero_length_bones`, `roots` (exactly one),
`pose_bones_not_xyz`, `deform_bones_without_radius`. Returns `armature`, `bones`, `deform`.

## Why not automatic weights

The generated mesh is a thin double shell in several disconnected islands. The heat solve needs
each vertex to be visible from a bone and the surface to be one connected piece: the inner
shell is hidden from every bone and the islands do not conduct to each other, so the solve
either fails outright or leaves vertices with no weight — and those stay behind when the rig
moves. Deleting the inner shell to make it solvable is destructive and breaks what the baked
maps address. A rule that looks only at position has neither problem: the inner twin of a vertex
sits at almost the same point and gets the same weights.

## The positional rule

```python
result = bcr_skin.run({
    "mesh": "Runner", "armature": "RunnerRig",
    "tau": 0.2, "smooth_passes": 4, "max_influences": 4,
    "gradients": [
        {"bones": ["Ear.L", "EarTip.L"], "parent": "Head", "fade_in": 0.22, "blend": 0.22},
        {"bones": ["Ear.R", "EarTip.R"], "parent": "Head"},
    ],
})
```

1. **Normalised distance.** For each deform bone: distance from the vertex to the bone's segment,
   divided by the bone's `radius`. The smallest value owns the vertex.
2. **Blend only with family.** The owner shares the vertex with its own parent and children and
   nobody else: weight = exp(−(d − d_nearest) / `tau`). An arm reaches the torso through the
   shoulder, never through the ribs it hangs beside.
3. **Gradient chains.** A vertex owned by a bone named in `gradients` is weighted by how far along
   the chain it lies instead, so a long thin part bends as a curve and not as a hinge.
4. **Smooth, cut, renormalise.** Weights are averaged over mesh edges, the largest
   `max_influences` per vertex are kept, and they are scaled to sum to 1.

| Parameter | Default | What it does |
|---|---|---|
| `tau` | 0.2 | softness of the hand-over between a bone and its parent or child, in radius units; smaller is a harder joint |
| `smooth_passes` | 4 | averaging passes over mesh edges; each pass widens every blend by one edge |
| `max_influences` | 4 | bones kept per vertex — the limit Unity skins with by default |
| `gradients` | none | list of chains, each `bones` in order from base to tip |
| chain `parent` | none | the bone the chain grows from; it holds the base of the chain |
| chain `fade_in` | 0.22 | fraction of the chain's length over which `parent` lets go |
| chain `blend` | 0.22 | half the width of the hand-over between two bones of the chain, as a fraction of its length |

The call replaces every vertex group on the mesh, adds one Armature modifier (or re-points the
existing one) and parents the mesh to the rig without moving it. It raises on a mesh whose object
scale is not 1 — unapplied scale on a skinned mesh is the classic bind-pose bug at export — and
on a deform bone with no radius.

Gates: `unweighted_vertices` (0), `max_influences`, `weight_sum_error` (< 1e-4),
`deform_bones_without_vertices` (none). Returns `vertices` and `dominant_vertices`: per bone, the
number of vertices it weighs most. Read that table before any render — a bone that owns almost
nothing has a radius that is too small or lies inside a thicker neighbour, and left and right
twins should own nearly the same count.

## The extreme-pose test

The gates prove every vertex has weights, not that the weights are right. That is a picture:
bend every joint far past anything the action will ask for and look at the creases.

```python
bcr_pose.run({"op": "apply", "armature": "RunnerRig", "pose": {
    "UpperArm.R": [["Y", 135]],     # arm straight up
    "UpperArm.L": [["X", -90]],     # other arm forward
    "Head":       [["Z", 40]],      # head turned
    "Spine":      [["X", 25]],      # spine bent
    "Ear.L":      [["X", 80]],      # one ear folded
    "EarTip.R":   [["X", -60]],     # the other ear's tip bent
    "UpperLeg.L": [["X", -70]],     # a leg lifted
}})
result = bcr_preview.run({"out_dir": "/abs/path/preview", "still": 1, "prefix": "pose_",
                          "percentage": 100, "camera": "PreviewCamera"})
# look at result["files"][0]; then a second still through a side or back camera
result = bcr_pose.run({"op": "reset", "armature": "RunnerRig"})   # gate pose_is_rest
```

- Steps are in armature axes (`reference/action-and-preview.md`). Before trusting a sign, apply
  one step alone and look which way the part went.
- Run it **before** an action exists on the rig: rendering sets the frame, and a keyed bone
  snaps back to its curve.
- One view hides half the creases: the armpit of the raised arm and the back of the lifted leg
  need a second camera.
- Always end on `reset` and read `pose_is_rest`; a prop attached or an action keyed on a
  leftover pose inherits it.

What passes: the raised arm takes the shoulder and nothing of the ribs; the folded ear is a
curve; the turned head leaves the chest where it was; no vertex is left hanging in the rest
position.

## Symptom → cause → change

| Symptom | Cause | Change |
|---|---|---|
| A thin part (ear, tail) torn into strips or steps | hard nearest-bone weights across it | name the chain in `gradients`; check `smooth_passes` is not 0 |
| The ear bends as one hinge at its middle | `blend` too narrow for the chain | raise `blend`, or add a third bone to the chain |
| A sharp crease where the ear meets the head | `fade_in` too small: `Head` lets go at once | raise `fade_in` |
| The lower ear stays rigid with the head | `fade_in` too large | lower `fade_in` |
| The torso follows a raised arm | arm `radius` too large: the arm wins vertices on the ribs | set arm radii to the limb's measured half-width; keep torso radii at the body's |
| The shoulders and upper chest turn with the head | head distances measured to the whole neck-to-crown line, which starts at the neck | give `Head` a `segment` around the ball's centre |
| A crease that looks folded, a sharp line at a joint | hand-over too narrow | raise `tau`, then `smooth_passes` |
| A joint that bends like rubber over a wide area | hand-over too wide | lower `tau` or `smooth_passes` |
| A bone with a tiny count in `dominant_vertices` | radius too small, or the bone lies inside a thicker neighbour | raise that radius, or move the bone to the part's centre line |
| `deform_bones_without_vertices` fails | a bone owns nothing above the 0.01 cut | as above; or mark a helper bone `deform: false` |
| Left and right counts differ widely | the mesh is not symmetric about x = 0 | author both sides from their own box centroids, `mirror: false` |
| Vertices stay at rest when the rig moves | vertex groups changed after the call | call `bcr_skin` again; read `unweighted_vertices` |
| Raises on object scale | the mesh was scaled after prep | apply the scale into the mesh, survey again, rebuild the armature, skin again |
