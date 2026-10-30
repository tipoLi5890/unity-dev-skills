# Prove the rig holds

> Part of the `unity-camera` skill (SKILL.md §6). The camera probe keys, the journey that asserts
> them, the jitter count, and the two deliberate breaks.

`resources/CameraProbe.cs` puts three facts on the probe every frame, latched after the Brain
has run so the pair is from one instant:

| Key | Meaning |
|---|---|
| `camViewport` | The player is inside the viewport |
| `camInBounds` | Every corner of the view is inside the bounds given to `SetBounds` |
| `camOffset` | Camera position minus player position |

`templates/CameraJourneyTest.cs` builds a side-run room, a runner and a follow rig, records 600
frames and asserts all three. `scripts/camera_jitter.py` reads the timeline and counts how often
the offset's frame-to-frame delta changes sign:

```bash
python3 scripts/camera_jitter.py journeys/camera-side-run/timeline.jsonl --axis x
```

A damped follow measures about 0.01, two clocks about 0.3; the limit is 0.1, and a missing key
exits 1 too. **Break it once**: `CAMERA_JOURNEY_BREAK=confiner` and `CAMERA_JOURNEY_BREAK=clocks`
must each turn the journey red before a green run means anything.

Framing, shake feel and pixel shimmer stay a person's judgement, from a windowed capture.
