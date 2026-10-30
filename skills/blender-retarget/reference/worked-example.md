# Worked example — two clips onto the runner

The pipeline table in `SKILL.md`, run once by hand; the module calls are in `reference/modules.md`.

`Runner`, rigged as `RunnerRig` with an A-pose rest, takes `HurdleVault` from a T-pose stock rig
and `GateLatchSwing` from a purchased pack. No Auto-Rig Pro and short limbs: `brt_retarget`.

1. **Manifest.** Two entries with file, fps and direction; of the pack's two-person take only the
   actor who swings goes onto `Runner`.
2. **One clip.** `HurdleVaultRig`'s frame 1 stands arms down, near `RunnerRig`'s rest, so it is
   the `reference_frame`; without it every arm hangs lower by the T-to-A difference. The map runs
   root outward and by role (`arm_l` is the upper arm; `shoulder_l` is a clavicle the target lacks);
   hands stay out of the first map.

   ```python
   import sys, importlib
   p = "<skill>/scripts"                      # this skill's scripts directory, absolute
   if p not in sys.path: sys.path.insert(0, p)
   import brt_common, brt_retarget; importlib.reload(brt_common); importlib.reload(brt_retarget)
   m = {"Hips": "hips", "Spine": "spine_01", "Chest": "spine_02",          # target: source
        "UpperArm.L": "arm_l", "LowerArm.L": "forearm_l", "UpperArm.R": "arm_r", "LowerArm.R": "forearm_r"}
   result = brt_retarget.run({"source": "HurdleVaultRig", "target": "RunnerRig", "map": m,
                              "reference_frame": 1, "output_action": "Runner_HurdleVault"})
   ```

   `retarget.output_is_new` passes, `retarget.finite_keys` 0; `max_step` equal to
   `source_max_step` says how fast the vault moves, not whether the map is right;
   `translation: "retargeted"` with `translation_k`; `retarget.translation_kept` passes.
3. **Look**, first, middle and last frame beside the source. A hand aimed at a tail that does not
   lie along the palm swings wrong, so the grip comes from the prop's anchor instead.
4. **The pack clip** rests in another A-pose with other names: its own map, its own `K`.
5. **Batch, library, prop.** One clip at a time; each `output_action` into the manifest's
   `action`; `brt_library` with `manifest`; `brt_drift` for `Mallet` on `Hand.R`; save when asked,
   `brt_audit --props`, then the minimal export.
