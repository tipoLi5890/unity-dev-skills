# Symptom → cause → fix

| Symptom | Cause | Fix |
|---|---|---|
| Generated model is one fused blob | a whole turnaround sheet fed as one image | crop into single views, one array entry each (§2) |
| Text-shaped lumps on the geometry | `FRONT`/`BACK` labels in the reference | crop the labels out (§2) |
| Face melts, eyebrows break | too few face pixels in the input | raise input resolution **before** switching tools (§2) |
| Back view came out as a profile | only 2 images passed; `back` consumed as `left` | supply 3 entries (§4) |
| Asymmetric accessories mirrored | left/right semantics guessed wrong | swap the left/right entries (§4) |
| Arms welded to the torso after auto-rig | input was not a T-pose | regenerate from a T-pose reference (§2) |
| Mixamo progress bar stalls, no error | stray shell / axis mismatch / embedded 4K maps | `fbx2mixamo.py`, upload the OBJ (§6) |
| Mixamo rejects the file | it already has a skeleton | export without armature; detect via raw-byte `LimbNode` scan (§6) |
| depth/height ≈ 0.5 in the report | stray geometry still in the bounding box | re-clean; do not upload (§6) |
| Character T-poses in place, Animator looks fine | animation FBX built its own Avatar | Copy From Other Avatar; re-run the linker command (§8) |
| Animator can't distinguish clips | every clip is named `mixamo.com` | rename clips from file names on import (§8) |
| Hitch every ~0.5 s during a run loop | `loopTime` set but `loopPose` not | set both (§8) |
| Character slides / fights the controller | root motion on, or clip not In Place | `applyRootMotion = false` + re-export In Place (§7, §8) |
| Visible in Scene, invisible in Game | model imported on layer 0, camera culls it | set model + children to the prefab root's layer (§8) |
| White mannequin | Mixamo returns no materials | rebuild the material from the original export's maps (§10) |
| Uniform plastic look | metallic JPEG carries no smoothness alpha | composite metallic + inverted roughness into an RGBA PNG (§10) |
| Normals lit wrong | texture not imported as NormalMap | `TextureImporterType.NormalMap` (§10) |
| Maps assigned, nothing changes on screen | URP keyword not enabled | `EnableKeyword("_NORMALMAP")` / `"_METALLICSPECGLOSSMAP"` (§10) |
| Lighting "vaguely wrong", no obvious cause | mask imported as sRGB | sRGB off (linear) (§10) |
| Frame rate tanks with one character on screen | ~94k triangles | decimate — **before** rigging (§5) |
| Whole character stalls on every minor hit | reaction plays on the base layer | upper-body AvatarMask on an override layer (§9) |
| Sprint arm-swing at jogging speed | one clip being time-scaled | 1D blend tree across slow + fast clips (§9) |
| Character's hit box is a different shape than the collider gizmo suggests | A parent has non-uniform scale | Apply scale in the DCC tool so the FBX imports at `(1,1,1)`; see `gameplay-rig.md` |
| Held prop or hit volume stops moving with the body | A `Rigidbody` on a child cut the compound body | Remove it, or make the split deliberate |
| Ragdoll launches itself on activation | Colliders overlap in the start pose | Shrink colliders; confirm with `Window > Analysis > Physics Debugger` |
| `OnCollisionEnter` never fires on the player | It is a `CharacterController` | Use `OnControllerColliderHit`; do not add a `Rigidbody` |
