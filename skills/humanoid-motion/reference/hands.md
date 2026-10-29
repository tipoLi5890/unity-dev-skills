# Hands: a fixed hand pose by default

> Part of the `humanoid-motion` skill. The contract's finger bones:
> `unity-rigged-character` → `reference/humanoid-contract.md`.

Two orthographic views of a full body do not resolve fingers: a hand covers a few dozen pixels,
and the two-camera solve leaves every finger bone at rest. So a body clip ships with a **fixed hand
pose**, layered on after the solve, and finger animation is a separate, deliberate choice. A clip
retargeted from a pack with flickering fingers is the same case: leave the finger bones out of its
map (`blender-retarget`).

## One pose per hand state

Make a small set of hand poses once per character set, on the contract skeleton, and reuse them in
every clip:

| Pose | Use | Curl (proximal / middle / distal) |
|---|---|---|
| `relaxed` | walk, run, idle | 15° / 20° / 10°, thumb 10° / 10° / 5° |
| `fist` | push, climb, carry | 70° / 90° / 60°, thumb across, 30° / 40° / 30° |
| `grip` | holding a prop (the courier's parcel strap) | the fist opened 20° per joint, thumb opposed |
| `flat` | a palm on a surface | 0° everywhere |

Key the pose as constant curves on the finger bones of each clip's action, at its first and last
frame, in Blender:

```python
import bpy, math
from mathutils import Euler
CURL = {"1": 15, "2": 20, "3": 10}                     # relaxed; per phalanx
rig = bpy.data.objects["RunnerRig"]
act = bpy.data.actions["RunnerWalk"]
rig.animation_data.action = act
f0, f1 = (int(round(x)) for x in act.frame_range)
for pb in rig.pose.bones:
    base = pb.name.split(".")[0]                       # Index2.L -> Index2
    if not base.startswith(("Index", "Middle", "Ring", "Little")):
        continue
    pb.rotation_mode = "XYZ"
    pb.rotation_euler = Euler((math.radians(CURL[base[-1]]), 0, 0), "XYZ")
    for f in (f0, f1):
        pb.keyframe_insert("rotation_euler", frame=f, group=pb.name)
```

The curl axis is the bone's local X only when the finger bones were rolled with their X across
the knuckle. Confirm it on one finger in the viewport before keying all of them: a curl that bends
the finger sideways or backwards means another axis or the opposite sign for that rig. The thumb
needs its own axis; pose it by hand once and copy its rotations.

In Unity, a hand state that changes during play (relaxed while running, a grip on pickup) is an
Avatar Mask layer for the hands on the contract skeleton, with one-frame clips of the poses above
(`unity-rigged-character` → `reference/humanoid-contract.md` and `unity-rigged-character` → `reference/unity-import.md` for
the mask and the Humanoid avatar it needs).
