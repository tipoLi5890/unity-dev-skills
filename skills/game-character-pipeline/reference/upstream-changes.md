# When something upstream changes — the stage to go back to

Read with the stage table in `SKILL.md`; the ledger's `stale` names the downstream records
(`art-asset-registry` → `reference/workflow.md`).

| What changed | Back to |
|---|---|
| The class's `instances`, `frame_ms`, the game camera or the target device | S0, then S5 and S6 if the picked rung moves |
| The budget row, after the rig exists | S5, then **S6 again**: nothing taken on the old vertices carries over |
| The views or the design | S1, and every stage after it |
| The generation graph or a preset | S3; a drift from the official template is put back before any tuning |
| One clip's source, map or rest frame | S8 for that clip, then S9's checks, then S11 |
| A weight repair or a prop grip | S9, then S11 and S12 |
| The upgrade track: a cloud mesh | S4, `mesh_check`, S5 on the ship track, S6; clips carry over, S9's prop and drift checks again |
| Fit route: a new character, or its mesh | that character's `prep` onward; the clip library is untouched |
| Fit route: a clip from another skeleton | its one offline conversion to the pack's skeleton, then the unity-gate |

## Worked example — the Runner with a Mallet, ship track

1. **G0.** Target: the runner behind the shoulder at the lane camera's distance, the swing at the
   gate as the one close shot. Adult proportions: `character-autorig` onto the contract; the jog
   and the leap over the gate from two-camera takes. The Mallet is its own `hero-prop` asset,
   attached at S9.
2. **S1 → S5.** Views approved; the `character` ladder under the game camera, a person picks a
   rung; a green local GLB, `Runner_game.blend` at the preset.
3. **S6 → S12.** `mesh_check` exit 0; `RunnerRig` from markers a person accepted, the contract
   gate and the six poses passing; the jog and the leap solved onto the rig, baked and gated; the
   first four files read back, then a throwaway Unity project; a person approves. S13 records every file with its licence.
4. **Later, upgrade.** After the demo, a person sends the runner's views to a paid mesh service;
   the new mesh re-enters at S4, is rigged locally the same way, and plays the jog and the leap
   unchanged.
