# Action and preview — key in armature axes, measure the contact, then render

> Part of the `blender-character-rig` skill. The stub that calls a `bcr_*` module and the shape of
> every result are in `SKILL.md`.

An action is judged three times, cheapest first: by gates when it is keyed, by numbers at the
frame of contact, by pictures last. Each step catches what the one before cannot.

| Step | Call | Passes when |
|---|---|---|
| Find a sign | `bcr_pose` op `apply` → `bcr_probe` → op `reset` | the point moved the way the beat needs |
| Key the action | `bcr_pose` op `key` | `slot_assigned`, `fcurves`, `first_equals_last` |
| Measure the contact | `bcr_probe` with `gate_frame` | `distance_to_target`, `direction_z` |
| Key the reaction | `bcr_pose` op `key_object` | `slot_assigned`, `fcurves` |
| Render | `bcr_preview`, a chunk per call | `frames_missing`, `settings_restored` |
| Look | `scripts/frames_preview.py` | exit 0, then the GIF and the sheet read right |

## Rotations are steps in armature axes

A bone's own axes depend on its roll, so "40° about X" means something different on every bone.
`bcr_pose` takes every rotation in the **armature's** axes instead — for a character that faces
−Y: X is its left, −Y its front, Z up — and converts it with the bone's rest matrix (B⁻¹·R·B).

- A rotation is a list of `[axis, degrees]` steps, **applied in the order written**:
  in `[["Y", 40], ["X", -85]]` the turn about Y happens first, then the turn about X.
- Each rotation is **relative to the parent**: a twisted chest carries the arm with it, so an arm
  value is what the arm adds, not where it ends up.
- Angles are right-handed about the named axis; the euler written to the bone is the one nearest
  its previous value. FK only, rotation only: no bone is translated or scaled.

**Find a sign by measuring it, not by deriving it.** Before any action is keyed, apply one step
to one bone, read where a point went, and reset:

```python
bcr_pose.run({"op": "apply", "armature": "RunnerRig", "pose": {"UpperArm.R": [["Y", 30]]}})
result = bcr_probe.run({"object": "Mallet", "extreme": {"axis": "X", "sign": 1, "band": 0.02}})
# result["frames"]["<current frame>"]["position"] — compare with the same call at rest
bcr_pose.run({"op": "reset", "armature": "RunnerRig"})      # gate pose_is_rest
```

- `bcr_probe` reads an **object's** world matrix, so it follows the prop parented to `Hand.R` and
  therefore the whole arm chain. The skinned mesh object itself never moves; for a chain with
  nothing parented to it (an ear, the head) the sign test is a `bcr_preview` `still`.
- Do this **before** op `key`. The probe sets the frame, and once an action drives a bone, setting
  the frame overwrites whatever `apply` put there.

## The frame table

Op `key` takes one table: frame → bone → steps. Write beats, not in-betweens.

| Frame | Beat | What changes |
|---|---|---|
| 1 | ready | arm low, chest square |
| 8 | wind-up starts | chest begins to turn away, arm lifts |
| 13 | top | arm overhead, chest turned and leaning back, ears trail |
| 15 | hold | the same pose, a touch further: the pause that sells the hit |
| 18 | contact | arm forward, chest turned through and leaning in |
| 20 | ears thrown forward | body stops, ears keep going |
| 23 | ears rebound | ears swing back past upright |
| 27 | settle | chest and arm ease off |
| 34 | return | most of the way back |
| 40 | ready | identical to frame 1 |

Ten bones carry it: `Spine`, `Chest`, `Head`, `UpperArm.R`, `LowerArm.R`, `UpperArm.L`, `Ear.L`,
`Ear.R`, `EarTip.L`, `EarTip.R`. The top and the contact, written out:

```python
ready = {"UpperArm.R": [["Y", 10]], "LowerArm.R": [["X", 20]]}
result = bcr_pose.run({
    "op": "key", "armature": "RunnerRig", "action": "GateLatchSwing",
    "fps": 24, "loop": True, "set_scene_range": True,
    "frames": {
        "1": ready,
        "13": {"Spine": [["Z", -10]], "Chest": [["X", -12], ["Z", -20]], "Head": [["Z", 15]],
               "UpperArm.R": [["Y", 130]], "LowerArm.R": [["X", -40]], "UpperArm.L": [["X", 25]],
               "Ear.L": [["X", -15]], "Ear.R": [["X", -15]]},
        "18": {"Spine": [["Z", 8]], "Chest": [["X", 14], ["Z", 18]], "Head": [["X", 8]],
               "UpperArm.R": [["Y", 45], ["Z", 80]], "LowerArm.R": [["X", 10]],
               "UpperArm.L": [["X", -20]], "Ear.L": [["X", 8]], "Ear.R": [["X", 8]]},
        # 8, 15, 20, 23, 27, 34 in the same shape
        "40": ready,
    },
})
```

The degrees are this rig's; a different skeleton gets its own from the sign test above.

- **A bone named in any frame is keyed in every frame**, at rest where a frame leaves it out: a
  bone that holds a pose across a beat is written again in that beat.
- `loop` adds the gate `first_equals_last` (< 1e-5 on every f-curve): give the last frame the
  first frame's entry. An action that already has the name is **replaced**.
- The call sets the scene's fps when `fps` is given, sets the frame range to the first and last key (pass
  `"set_scene_range": False` to keep the range) and moves the current frame to the first key.
  Report those as changes to the scene; `"scene"` names another scene to change instead.
- Returns `keyed_bones`, `keyed_frames`, `fcurves`, `frame_range`, `scene_range`, `fps`. Frame
  numbers are sent as strings and come back as strings wherever they are keys.

## Slotted actions and the slot gate

An action holds its channels per **slot**, and an object plays only the slot assigned to it. An
action assigned without one has every f-curve it should and moves nothing — the rig stands at
rest through the whole range, with no error.

- Gate `slot_assigned` fails that case. Gate `fcurves` wants at least 3 per keyed bone: 30 for
  the ten bones above.
- Read f-curves the way `bcr_pose` does — through the action's layers, strips and the channelbag
  of the object's slot — and fall back to `action.fcurves` only where there are no layers.
- Code of your own that assigns or fills an action is checked the same way: read
  `animation_data.action_slot` after it, not the curve count.

## Measure the contact before rendering

A render shows that a pose is wrong; the probe shows by how much and in which direction, in one
call that only reads. First without a target, to see where the swing goes:

```python
result = bcr_probe.run({
    "object": "Mallet",
    "frames": [1, 15, 17, 18, 20],
    "extreme": {"axis": "X", "sign": 1, "band": 0.02},   # the far edge along the prop's local +X
    "direction": [1, 0, 0],                              # where the striking face points, local
})
```

Per frame: world `position`, world `direction` (unit length), and `distance` once a target is
given. `extreme` averages the vertices within `band` of the far end of a local axis; `point`
gives a local coordinate instead.

- **A swing that goes too far reads as `direction` z near −1 with `position` z at floor height**:
  the face is driven into the ground. Take forward rotation off the arm or chest at the contact
  beat and probe again — no render needed to see it.
- A `position` that never changes means the prop is not on the hand (`reference/prop-on-bone.md`).

**Place the target at the measured contact** — the position read at frame 18 — rather than
bending the swing to meet a target placed by eye. Then the same call becomes the gate:

```python
result = bcr_probe.run({
    "object": "Mallet", "frames": [1, 15, 17, 18, 20],
    "extreme": {"axis": "X", "sign": 1, "band": 0.02}, "direction": [1, 0, 0],
    "target": [0.12, -0.5, 0.35],        # world point: where GateLatch sits
    "gate_frame": 18, "within": 0.05, "direction_z_min": -0.8,
})
```

`distance_to_target` passes at or under `within` metres; `direction_z` fails a face that points
more steeply down than `direction_z_min`. Run it again after every change to the table.

## The target and its reaction

`GateLatch` is an object of its own at the target point. Its reaction is a second action on that
object, keyed with op `key_object`:

```python
bcr_pose.run({"op": "key_object", "object": "GateLatch", "action": "GateLatchPop",
              "frames": {"1": [], "18": [], "19": [["X", 3.5]], "21": [["X", -2.2]], "29": []}})
```

- Steps are in **world** axes, added to the rotation the object has when the call is made; `[]`
  is that rotation unchanged.
- Key the contact frame at `[]` and the reaction on the frame after it: the still key at 18
  holds the target through the wind-up.
- The object's rotation mode becomes XYZ euler; an action of that name is replaced. Gates:
  `slot_assigned`, `fcurves`.

## Preview in chunks

One call must return before the host's tool timeout, so a range is rendered a chunk at a time, at
a fraction of the output resolution:

```python
result = bcr_preview.run({"out_dir": "/abs/path/preview", "prefix": "f_",
                          "frames": [1, 20], "percentage": 50, "camera": "PreviewCamera"})
result = bcr_preview.run({"out_dir": "/abs/path/preview", "prefix": "f_",
                          "frames": [21, 40], "percentage": 50, "camera": "PreviewCamera"})
result = bcr_preview.run({"out_dir": "/abs/path/preview", "still": 18, "prefix": "pose_"})
```

- Start at 20 frames per call at 50%. Read `seconds_per_frame` from the first chunk and size the
  rest to the timeout: a light EEVEE scene at half of 1280×960 takes a fraction of a second per
  frame, a heavier scene much longer. Halve the chunk when a call is slow.
- Files are `<prefix><frame:04d>.png`, exactly where `out_dir` says. A file left in the range from
  an earlier run is deleted first, so a failed render cannot pass as this run's picture.
- The render path, resolution percentage, file format, camera and current frame are put back in a
  `finally`. Gates: `frames_missing` (must be empty), `settings_restored`.
- `camera` renders through a camera of your own without leaving it as the scene's.

Then, on the host:

```bash
python3 scripts/frames_preview.py /abs/path/preview --prefix f_ --fps 24 \
    --gif /abs/path/out/swing.gif --sheet /abs/path/out/swing_keys.png \
    --keys 1,8,13,15,18,20,23,27,34,40
```

The GIF shows whether the swing reads; the sheet puts the beats side by side. `--crop 0.6` keeps
the middle 60% of each cell's width, `--columns` (5) and `--cell-width` (480) shape the sheet.
Existing outputs are deleted before anything is written.

| Exit | Meaning |
|---|---|
| 0 | written |
| 1 | a `--keys` frame was not rendered, a frame is missing from the range, or the frames differ in size |
| 2 | no frames, Pillow missing, or bad usage |

It needs Pillow. Run it with an interpreter that has it; when none does, open the key-frame PNGs
directly instead of installing anything.

## What only the pictures show

Every gate above can pass on an action that looks wrong. Look at the sheet for:

- **The target standing between the camera and the character.** The contact is exact and the
  frame shows the back of the target. Move the camera, not the target.
- **Material slots swapped on an object you built.** Slots assigned by face creation order
  instead of by geometry put the wrong material on the wrong part; no number reports it.
- **The prop through the face**, or a beat that never changed: two cells with the same picture.

## Limits

- **Single-handed.** Short arms do not meet, so the free arm counterbalances instead of gripping.
- **Feet planted.** No IK: the hips do not dip and the feet do not step. Weight shift is the
  spine and chest only.
- **The hand stays open.** The handle passes through the palm (`reference/prop-on-bone.md`).
- **The reaction is a second action on a second object**: `reference/fbx-export.md` says what
  that does to an export.
