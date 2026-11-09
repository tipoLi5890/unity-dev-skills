# G0 — the start gate in full

`SKILL.md` lists the four answers; this file holds what each one decides and what follows from
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
- **A long coat, skirt or robe** over a standard body, or a cape or cloak bridging the legs from
  behind: the skirt route (`autorig.py all --body skirt`), the legs still apart and showing under
  the hem in S1.
- **A chibi** (a big head about a third of the height, short thick limbs, mitten hands): the chibi
  route (`autorig.py all --body chibi`), arms clear of the big head and legs apart in S1.
- **A custom body** (ears, a tail, proportions no route's windows fit):
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
4. **S6, local, the same contract.** `character-autorig`: markers (with Auto-Rig Pro's AI when
   its files are installed), Auto-Rig Pro (or the hand-built route), `contract_map.py --require contract`, `deform_gate.py`. The same gates, the
   same limits; the rig record keeps `auto-rig-pro`.
5. **Clips carry over.** The skeleton is the contract, so every clip made for the demo binds on
   the new rig unchanged: skip S7–S9 for clips; S9's prop grip and drift checks run again on the new
   mesh, then S11 and S12 as usual. A clip that looks wrong on the new mesh is a skin or mesh
   defect (S10 names the layer), not a reason to re-make the clip.
6. **The ledger.** `stale` names every record downstream of the old mesh; the new rig, the FBX and
   the Unity screenshot are recorded and approved again.

## 5. The parts tier

How far S3 goes, chosen by the quality target; not another flow. The tier is written in the
character's parts plan (`ArtDirection/parts/<c>/<c>.parts.json`, schema `parts/1`:
`comfyui-asset-generation` → `reference/image-to-3d-parts.md`).

| Tier | Parts | For | Costs beyond the anchor |
|---|---|---|---|
| `whole` | the anchor, one mesh | the demo, a preview, a character seen small | nothing: no plan file, every stage as it is |
| `three` | body (the anchor, its head cut off), head, hair (split from the head job) | showcase and ship; a face the camera comes close to | the plan, four redrawn head views, one background-removal job, **one** head job and its paint loop: e.g. 6–10 minutes of GPU time |
| `fine` | `three` plus both hands (each its own job, attached at the sleeve) and eyeballs (fitted behind the painted eyes, no job); accessories are not built yet | hand and face close-ups; fingers the rig finds | the hands: six redraws, one background-removal job and one job per hand (again on a failed gate), and a paint loop per hand: e.g. 25–35 more minutes of GPU time, most of it painting |
| `custom` | a person's own list | reserved | the tools refuse it |

**What `three` gains.** The head gets a whole generation to itself: ears, eyelids and lips form
that the anchor's head never has, and the face is clearly sharper. Hair becomes its own mesh, and
the head its own texture, so the face's texel density rises by the region ratio. **What it does
not:** hands. The anchor's fingers are fused; `fine` generates each hand on its own from the clean
views, redrawn with gaps between the fingers, and attaches it under the sleeve's cuff
(`comfyui-asset-generation` → `reference/image-to-3d-parts.md` §Hands). It needs a sleeve or a cuff
to hide the seam; a bare arm stays `three`.

**The anchor is always generated first.** S3 makes the whole body as today, and S3b paints it;
the parts are registered onto it and replace its regions, and S3c gates the assembled silhouette
and head height against it. The proportions therefore stay the anchor's, and so do the contract's
joint positions and every clip made for the demo.

**What changes downstream.**

- The rig mesh is `<c>_rig.glb`, body and head with both materials. S6 runs
  `character-autorig` `autorig.py all OUT <c>_rig.glb --hair <c>_hair.glb`: after the contract it
  binds the hair rigidly to the Head bone (`parts_bind`), so the deformation gate, every repair and
  the spring chains already have it. The hair stays rigid on Head unless `--hair-chains` asks for
  spikes on it.
- Tier `fine`: `assemble_parts.py hands` attaches both hands into a folder of its own, then
  `eye_fit.py fit` cuts the painted eyes out and writes `<c>_eyes.glb` (in that order: `hands`
  rewrites `<c>_rig.glb`). S6 adds `--eyes <c>_eyes.glb --facial`: each eyeball is bound to its eye
  bone (Unity's LeftEye / RightEye) after the hair (`blender-character-rig` →
  `reference/part-assembly.md` §6–7).
- The markers measure the rig mesh, which has no hair: the height is the skull top, and spiky
  hair no longer lifts the shoulders and hips.
- When the hair split fails its gates, the hair stays joined to the head and the run stops; a
  **person** may accept that, and the hair is then back in the rig mesh and in the height.
- The seam hides under a collar or hood by default; a raised hood or a helmet over the head is
  refused in this tier.
- On the ship track the parts merge into one mesh, one material and one atlas per map before S6
  (`assemble_parts.py ship`: `blender-character-rig` → `reference/part-assembly.md` §8), and that
  mesh is rigged once, hair included, without `--hair`; each part's triangles are checked against
  its `budget_share` (`unity-3d-models` → `reference/budgets.md`, A character in parts).

**From `whole` to `three` later.** The approved anchor stays: make the plan from it, the head
views and job, S3b on the head, then re-enter at S3c and S6 (a new rig on the same contract).
The clips carry over as on the upgrade track (§4, step 5); S9's prop and drift checks, S11 and S12
run again, and the ledger's `stale` lists what the new rig replaces.
