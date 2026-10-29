# G0 — the start gate in full

`SKILL.md` lists the three answers; this file holds what each one decides and what follows from
it. A person gives the answers, and they are written down (the brief, or the ledger's `note`)
before the first image is generated.

## 1. The quality target, first

Camera distance, the shots that matter, the body parts that must hold up under them. Every later
stop decision is taken against it, and a request to stop refining stands until the user sets a
new one (`blender-retarget` → `reference/defect-triage-and-stop.md`).

The quality target decides how far S3 and S10 go. It does **not** decide where the mesh is made:
S3 is always the local multi-view generation (`comfyui-asset-generation` →
`reference/image-to-3d.md`, A character), and a target the local mesh cannot reach is recorded as
the baseline's limit ("adopt the usable baseline and record its limits" is a valid S3 exit). A
paid cloud mesh enters only through the upgrade track below, chosen by a person after the demo.

## 2. The route

The route decides the art (pose, fingers, one piece or many), so it comes before S1. The full
table, and what each route hands Unity: `reference/routes.md`. In short:

- **A standard adult humanoid** (the default): rigged locally onto the humanoid contract by
  `character-autorig`, clips from `humanoid-motion` or a pack retarget.
- **A custom or Q-version body** (short limbs, a large head, ears, a tail, mitten hands):
  `character-autorig`'s hand-built route when the body still maps to the contract, else
  `blender-character-rig`'s positional skinning; motion through `humanoid-motion` (two cameras) or keyed.
- **One clip pack supplies every motion**: the fit route, the pack's skeleton fitted to the mesh.

Rigging is always local. No cloud rigging service (an image-to-3D service's auto-rig, Mixamo) is a
route of this pipeline: an FBX from one can still be imported (`unity-rigged-character` →
`reference/mixamo-route.md`), but it has passed none of S6's gates and is not shipped through them.

## 3. The track

| Track | Stages | For | Who starts it |
|---|---|---|---|
| **Preview** | S1–S4, S6–S13 (no S0, no S5) | a prototype, a pitch, a preview reel: fastest; the dense mesh is rigged as it is | G0 |
| **Ship** | S0–S13 | the character the game ships: budget, game mesh, one rig | G0 |
| **Upgrade** | S3 (cloud mesh) → S4 → S5 when the ship track applies → S6 → S9 (prop and drift checks) → S11 → S12 → S13 | a character whose demo is approved and whose mesh a person wants better than the local generation gives | a **person**, after the demo; never a gate or the quality target |

**Preview into ship.** A preview that turns into the shipping character goes back to S0 and S5
and is rigged again; its rig, weights, wrist correction and grip do not carry over (S5 may borrow
its weights as a starting point — `blender-character-rig` → `reference/game-mesh.md`). The preview
track ends in a timed gameplay preview and reel: `unity-game-brief` →
`reference/preview-before-code.md`.

## 4. The upgrade track

The demo is approved and the character's clips exist on the humanoid contract. A person picks the
character and decides to pay for a better mesh.

1. **S3, in the cloud, mesh only.** The approved S1 views (or S2's cut-outs) go to a paid
   image-to-3D service (Tripo, Meshy or similar) on its commercial plan. Only the mesh comes back;
   the service's rig, skin and animation, when it offers them, are not used. Record the new GLB in
   the ledger with that service's `licence` (`art-asset-registry` → `reference/licences.md`).
   Confirm the service's commercial terms and sales territory before the first upload and record
   them in the licence; terms that stay unclear stop the upload.
2. **S4 and the mesh gate.** The new mesh is normalised like any other, then
   `character-autorig` → `scripts/mesh_check.py` must exit 0 before any rig. A fail goes back to
   the service (re-generate) or to S1, exactly as for a local mesh.
3. **S5 on the ship track.** The cloud mesh is a new showcase: the game mesh is built from it at
   the class's picked rung, through S5's gates.
4. **S6, local, the same contract.** `character-autorig`: markers, Auto-Rig Pro (or the
   hand-built route), `contract_map.py --require contract`, `deform_gate.py`. The same gates, the
   same limits; the rig record keeps `auto-rig-pro`.
5. **Clips carry over.** The skeleton is the contract, so every clip made for the demo binds on
   the new rig unchanged: skip S7–S9 for clips; S9's prop grip and drift checks run again on the new
   mesh, then S11 and S12 as usual. A clip that looks wrong on the new mesh is a skin or mesh
   defect (S10 names the layer), not a reason to re-make the clip.
6. **The ledger.** `stale` names every record downstream of the old mesh; the new rig, the FBX and
   the Unity screenshot are recorded and approved again.
