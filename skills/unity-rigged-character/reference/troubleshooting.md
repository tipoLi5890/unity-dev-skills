# Symptom → cause → fix

## The source mesh

| Symptom | Cause | Fix |
|---|---|---|
| Generated model is one fused blob | a whole turnaround sheet fed as one image | cut it into single views, one array entry each (`codex-visual` → `reference/image-to-3d-input.md` §5) |
| Text-shaped lumps on the geometry | `FRONT` / `BACK` labels in the reference | no text in frame: the sheet prompt says no labels; regenerate or crop them out (`codex-visual` → `reference/image-to-3d-input.md` §1, §5) |
| Face melts, eyebrows break | too few face pixels in the input | give the face more pixels from a larger source **before** switching tools (`codex-visual` → `reference/image-to-3d-input.md` §10) |
| Back view came out as a profile | only two images passed; `back` consumed as `left` | supply three entries (`source-art-and-3d.md`, multi-view input) |
| Asymmetric accessories mirrored | left/right semantics guessed wrong | swap the left and right entries (`source-art-and-3d.md`, multi-view input) |
| Arms welded to the torso after auto-rig | input was not a T-pose | regenerate from a T-pose reference (`mixamo-route.md` §1) |

## The Mixamo upload

| Symptom | Cause | Fix |
|---|---|---|
| Mixamo progress bar stalls, no error | stray shell / axis mismatch / embedded maps | `fbx2mixamo.py` or `glb2mixamo.py`, upload the OBJ (`mixamo-route.md` §3) |
| Mixamo rejects the file | it already has a skeleton | export without the armature; detect via raw-byte `LimbNode` scan (`mixamo-route.md` §3) |
| depth/height ≈ 0.5 in the cleanup report | stray geometry still in the bounding box | re-clean; do not upload (`mixamo-route.md` §3) |
| A GLB reads as thousands of shells and the cleanup deletes real anatomy | glTF splits a vertex at every UV seam | weld by position first; `glb2mixamo.py` does (`mixamo-route.md` §3) |

## Import, Avatar and clips

| Symptom | Cause | Fix |
|---|---|---|
| Character T-poses in place, Animator looks fine | animation FBX built its own Avatar | Copy From Other Avatar; re-run Link Animation Avatars (`unity-import.md` §2) |
| Animator can't distinguish clips | every clip is named `mixamo.com`, `Take 001`, `Scene` or `<rig>\|<action>` | `<name>@<Clip>.fbx`; the importer renames (`unity-import.md` §2) |
| An animation file got its own materials and Avatar | no `@` in its file name, so it was read as a body | rename to `<name>@<Clip>.fbx` (`editor-scripts.md`) |
| A body whose name contains run, idle or hit imported as an animation | an older keyword-detecting importer | the `@` contract; reimport the folder (`editor-scripts.md`) |
| Hitch every ~0.5 s during a run loop | `loopTime` set but `loopPose` not | set both (`unity-import.md` §2) |
| Character slides / fights the controller | root motion on, or clip not In Place | `applyRootMotion = false` + In Place clips (`unity-import.md` §2) |
| Visible in Scene, invisible in Game | model imported on layer 0, camera culls it | set model + children to the prefab root's layer (`unity-import.md` §2) |
| Pose a few degrees off Blender, a held prop 10+ cm off the hand | the clip plays through Humanoid muscle space | Generic for clips retargeted in Blender; Anim. Compression Off when the prop must line up (`unity-import.md` §1) |
| One joint bent far wrong on Humanoid only | the pose is outside the muscle limits and was clamped | Generic, or fix the pose in Blender (`unity-import.md` §1) |
| The chest does not move on Humanoid, or the spine bends oddly | the automatic mapping left a bone such as `Chest` unmapped | Build Humanoid Avatar: an explicit map with Chest and the fingers (`humanoid-contract.md`); or Configure by hand, re-check `isValid` (`unity-import.md` §1) |
| Humanoid Avatar built on the wrong pose | the default pose is the clip's first frame, not the Blender rest | Enforce T-Pose, or an explicit skeleton (`unity-import.md` §1) |
| Extra bones (ears, a tail) frozen on a Humanoid | they sit outside the humanoid map | check in Play mode; Generic when the game needs no body-part mask (`unity-import.md` §1) |
| A prop socket under the hand is missing | Optimize Game Objects removed the bone Transforms | list it in Extra Transforms to Expose (`unity-import.md` §3) |
| The exposed socket is found nowhere under the hand | an exposed transform is re-parented under the model root | find it by name, not by path (`unity-import.md` §3) |
| A socket bone is missing after a deform-only export | its Deform flag was off | flag it Deform; it needs no weights (`unity-import.md` §4) |
| A held prop's shape key does not move in Unity | a Blender driver is not exported | bake the driven value to keys, Import BlendShapes on (`unity-import.md` §4) |
| Some clips of a pack play nothing on the character, the rest are fine | their root node is named differently and Generic binds by path | rename the path prefix at import, RemapRoot (`shared-skeleton-generic.md`) |
| Limbs stretch or shrink to the pack body's proportions in a few clips | stray translation curves on non-root bones | strip every position and scale curve except the root bone's (`shared-skeleton-generic.md`) |
| A head or hand sits a few to 70° off in one clip only, on your character but not on the pack's body | keyframe reduction deleted that bone's curve; the bone holds the model's default | write the clip file's default as a constant curve, BakeNodeDefaults (`shared-skeleton-generic.md`) |
| The opening frames of a clip differ between Blender and Unity (a whole body 1.2 m apart at frame 0) | a curve starts late: Unity holds its first key, Blender uses the node's static value | measure the opening frames in Unity; play the purchased files rather than Blender re-bakes (`blender-retarget` → `reference/route-bakeoff.md`) |
| A fitted character is the wrong height in the scene | the skeleton is at the pack's scale by design | the prefab root takes `display_scale` from the fit's manifest (`shared-skeleton-generic.md`) |
| A batchmode tool samples a clip and every frame reads the default pose | `PlayableGraph.Evaluate` does not pose the Animator in a batchmode editor | `AnimationMode.SamplePlayableGraph` inside Begin/EndSampling (`shared-skeleton-generic.md`) |
| `BakeMesh` returns the same mesh at every frame in batchmode | it keeps returning the bind pose | compute linear blend skinning from the weights and bind poses (`shared-skeleton-generic.md`) |
| More clothing pokes through on the low quality tier only | the tier's Skin Weights is 2 Bones; the asset was skinned with 4 | one count for both (`unity-import.md` §3) |
| GLB character, Humanoid clip does nothing | no Avatar on the glTFast import | build one with `AvatarBuilder.BuildHumanAvatar`, then `Rebind()` (`unity-import.md` §1) |

## Materials

| Symptom | Cause | Fix |
|---|---|---|
| White mannequin | the FBX carried no materials (Mixamo never does) | rebuild the material from the original export's maps (`textures.md`) |
| Uniform plastic look on a Blender FBX | Unity binds base colour and normal only; the metallic and roughness maps are dropped | build the metallic/smoothness map, bind it with the keyword (`textures.md`) |
| Uniform plastic look | metallic JPEG carries no smoothness alpha | composite metallic + inverted roughness into an RGBA PNG (`textures.md`) |
| Another character's texture on this one | an embedded texture resolved by file name to a same-named image elsewhere | extract the maps into the character folder under unique names (`textures.md`) |
| Normals lit wrong | texture not imported as NormalMap | `TextureImporterType.NormalMap` (`textures.md`) |
| Maps assigned, nothing changes on screen | URP keyword not enabled | `EnableKeyword("_NORMALMAP")` / `"_METALLICSPECGLOSSMAP"` (`textures.md`) |
| Lighting "vaguely wrong", no obvious cause | mask imported as sRGB | sRGB off (linear) (`textures.md`) |
| Maps import at 1024 or 2048 where 512 was expected | Max Size left at the importer's value | set `maxTextureSize` or `targetTexPx` in `character-pipeline.json` (`editor-scripts.md`) |

## In play

| Symptom | Cause | Fix |
|---|---|---|
| Frame rate tanks with one character on screen | the mesh is far past what the class needs | game mesh **before** rigging (`blender-character-rig` → `reference/game-mesh.md`; Mixamo route: `mixamo-route.md` §2); the target from the `character` row of the 3D budgets table (`unity-3d-models`), the cost from `unity-profiling` |
| Whole character stalls on every minor hit | reaction plays on the base layer | upper-body mask on an override layer (`unity-import.md` §5) |
| Sprint arm-swing at jogging speed | one clip being time-scaled | 1D blend tree across slow + fast clips (`unity-import.md` §5) |
| Hit box far wider than the character | sized from the skinned renderer's bounds | constant volume (`gameplay-rig.md`) |
| Part of the character vanishes at the edge of the screen mid-swing | the pose leaves the import-time culling box | widen `localBounds`, or Update When Offscreen (`gameplay-rig.md`) |
| Bounds read in a test do not match the pose | read straight after an Animator evaluate | read after a rendered frame (`gameplay-rig.md`) |
| Character collides with its own accessories | colliders left on the model child | strip them; the root's collider is the hit box (`gameplay-rig.md`) |
| Character's hit box is a different shape than the collider gizmo suggests | a parent has non-uniform scale | apply scale in the DCC tool so the FBX imports at `(1,1,1)` (`unity-physics-3d` → `reference/sleep-shapes-build.md` §5) |
| Held prop or hit volume stops moving with the body | a `Rigidbody` on a child cut the compound body | remove it, or make the split deliberate (`unity-physics-3d` → `reference/sleep-shapes-build.md` §5) |
| Ragdoll launches itself on activation | colliders overlap in the start pose | shrink colliders; confirm with `Window > Analysis > Physics Debugger` (`unity-physics-3d` → `reference/sleep-shapes-build.md` §5) |
| `OnCollisionEnter` never fires on the player | it is a `CharacterController` | use `OnControllerColliderHit`; do not add a `Rigidbody` (`unity-physics-3d` §1) |
| `Animator is not playing an AnimatorController`, character stands still | a second, empty Animator on the root | no `RequireComponent(Animator)` on the root (`gameplay-rig.md`) |
