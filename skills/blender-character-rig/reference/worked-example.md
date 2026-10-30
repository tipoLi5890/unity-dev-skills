# Worked example — the courier run's runner, hand-built

The fallback route end to end: the steps are the pipeline table in `SKILL.md`; each module's
gates are in its docstring.

The courier run's runner: a plush mascot with short limbs and long ears, swinging a delivery
mallet at the latch of a gate.

1. **Prep.** `name: "Runner"`, `collection: "Character"`, `height: 1.2`. A 20,000-triangle GLB
   goes from 14,991 vertices to 9,994 with every face kept, in 13 islands.
2. **Survey.** 20 z slices; boxes for each hand, foot, ear base, ear tip and the tail.
3. **Armature.** `RunnerRig`, 22 bones with `mirror: true`: `Root` (non-deform), `Hips`, `Spine`,
   `Chest`, `Head`, `Tail`, and per side `Ear`, `EarTip`, `UpperArm`, `LowerArm`, `Hand`,
   `UpperLeg`, `LowerLeg`, `Foot`. Radii: torso 0.20–0.21, head 0.30, arms 0.062, legs 0.10.
4. **Skin.** Defaults, plus one `gradients` chain per ear (`Ear`, `EarTip`, parent `Head`).
5. **Extreme pose.** One arm straight up, the other forward, head turned, spine bent, one ear
   folded, a leg lifted; one still; reset.
6. **Prop.** `Mallet`, prepped without a weld, attached to `Hand.R` with `length: 0.62`.
7. **Action.** `GateLatchSwing`, frames 1–40 at 24 fps, `loop: true`, 10 bones keyed at frames 1,
   8, 13, 15, 18, 20, 23, 27, 34, 40; contact is frame 18.
8. **Probe.** A first pass that swings too far reads `direction_z` near −1 with the striking edge
   at floor height; the keys are corrected before any render. `GateLatch` goes at the measured
   contact, the probe is rerun with `target`, and `key_object` keys `GateLatchPop` on the latch.
9. **Preview.** Frames [1, 20] and [21, 40] at 50%, then the GIF and a sheet of the key frames.
10. **FBX.** `RunnerRig`, `Runner` and `Mallet` exported, re-imported into a scene `FbxCheck`,
    gated, discarded. The baked take has 229 f-curves against 30 authored: expected.
