# Numbers to start from

> Part of the `unity-animation` skill. Starting values for transitions, damping, windows, IK and
> the motion gates — then tune per clip.


| Quantity | 3D skeletal | 2D frame clips |
|---|---|---|
| Transition duration into a reaction (jump, hurt) | 0.05–0.10 s, no exit time | 0, no exit time |
| Transition duration between gaits | 0.10–0.20 s | 0 |
| `SetFloat` damp on a blend position | 0.08–0.15 s | 0 |
| `SetFloat` damp on a condition or a playback rate | 0 | 0 |
| `MoveSpeed` (playback rate) clamp | 0.5–1.6 | — |
| Journey budget: `animState` agrees with `state` within | 3 frames once the fade is 0; else fade + 3 | 3 frames |
| Attack window, as fractions of the state | open 0.25, close 0.55 — then tune per clip | same |
| Foot IK smoothing · ray reach below the foot | 0.1 s · 0.45 units | — |
| Hand IK weight ramp | 0.15–0.25 s | — |
| Swing rate to land a contact frame on a sim tick | 0.8–1.25, start trimmed when clamped | — |
| Sprint playback rate when the sim outruns the clip · stride warp | up to 1.8 · 0.3–1.8× | — |
| Foot-lock release spring · landing anticipation · pelvis drop cap | omega 28 · 0.08 s · 10 cm | — |
| Prop IK window around contact | −120 ms to +60 ms, release 0.15 s | — |
| Motion gates: slide p95 / max per plant · plant speed · root jump | 1.5 / 3 cm · 3 cm/s · 0.5 m/s per frame | — |
