# The Mixamo route — optional

The service has had no substantive updates for years and has had multi-day outages. Treat it as
one optional route and keep an alternative ready: a standard humanoid with Auto-Rig Pro installed
is rigged and given its clips in `blender-retarget`; a custom body is rigged in
`blender-character-rig`; an auto-rig service's FBX enters at `reference/unity-import.md`. The route
is chosen once per character, in `game-character-pipeline`.

It suits a character with standard humanoid proportions that plays stock clips. It wants a
**T-pose mesh in one piece**; the Blender route wants an A-pose and keeps every piece. Choose
before commissioning the art (`game-character-pipeline` G0; the Unity side:
`reference/source-art-and-3d.md`).

## 1. The art: a T-pose

Draw it to the T-pose variant of `codex-visual` → `reference/image-to-3d-input.md` §10: arms fully
horizontal with daylight between arm and torso, legs apart. A natural arms-down pose makes the
auto-rigger weld arm and torso skin weights together, and nothing downstream unpicks it.

## 2. Reduce the mesh BEFORE rigging

**Decimating a rigged mesh destroys its skin weights**, so it happens first. Discover the cost
after rigging and the only route is decimate, then rig again. The face count the character needs
comes from the `character` row of the 3D budgets table (`unity-3d-models` →
`reference/budgets.md`), not from the uploader. Mixamo's uploader has a face-count and file-size limit of its own — a tool limit, not a
quality budget: confirm the current limit on the upload page.

## 3. Clean the mesh — `fbx2mixamo.py`, `glb2mixamo.py`

**Symptom: the upload progress bar stops mid-way and never errors.** The upload succeeded; the
server-side parse is stuck. Three causes, all handled by the scripts:

1. **Stray disconnected shells.** A thin sliver unconnected to the body — typically a "ground
   spike" spanning the whole scene depth — inflates the bounding box. The auto-rigger infers
   skeleton placement from the bounding box, so a skewed box means it never finds a humanoid.
2. **Wrong axes.** Geometry authored Z-up while the FBX header declares Y-up: anything trusting
   the header sees a character lying down, and one export can carry its arm-span on X, the next on
   Y. So **infer axes from the body's own extents** (height > arm-span > depth, facing from the
   toes) instead of hardcoding a conversion matrix.
3. **Embedded PBR textures.** The maps can be most of the file and are worthless to the
   auto-rigger. Keep the original: they are reattached in Unity afterwards (`reference/textures.md`).

**Symptom: Mixamo rejects the file — it already has a skeleton.** Detect a pre-existing rig by
scanning the **raw bytes** for `LimbNode` / `Deformer` / `Cluster`. Skeleton nodes carry no array
properties, so a parser inspecting only decoded arrays reports "no rig" and sends you into an
upload that was never going to work.

```bash
python3 scripts/fbx2mixamo.py <character>.fbx <character>_mixamo.obj --height=170
python3 scripts/glb2mixamo.py <character>.glb <character>_mixamo.obj --height=170 --textures=<maps-dir>
```

Output: T-pose, Y-up, feet on the origin, scaled to `--height` units, UVs preserved, no textures.
`--keep-spike` (FBX) / `--keep-stray` (GLB) disables stray-shell removal. **Check the printed
ratios before uploading:** arm-span/height **0.8–1.0**, depth/height **0.2–0.3**. A depth/height
near 0.5 means stray geometry is still polluting the bounding box — re-clean, don't upload. The
ASCII front/side views printed at the end should read as a T-pose.

> **Never run index-level connectivity checks on glTF geometry.** FBX keeps a de-duplicated
> vertex array and indexes UVs separately; **glTF binds every attribute to one vertex, so each UV
> seam splits a vertex in two**. A solid body then reports as thousands of disconnected
> fragments, and a stray-shell filter deletes real anatomy. Weld by position first and it is one
> shell again. `glb2mixamo.py` does this; the OBJ still stores the split vertices because they
> carry the UVs.

> **Stray-shell removal is for Mixamo.** Its auto-rigger wants one body and a clean bounding box.
> The Blender route keeps every island and the inner shell: the baked normal and occlusion maps
> address them, and its weights are computed by position, so a mesh in several pieces is not a
> failure there. Do not run this cleanup on a mesh bound for it.

## 4. Upload and joint markers

Follow Adobe's own help page for the upload and marker steps:
<https://helpx.adobe.com/creative-cloud/help/mixamo-rigging-animation.html>. The interface
changes; these three checks do not:

1. **Before upload** — the file is the cleaned OBJ, its ratios inside the ranges above, the ASCII
   views a T-pose.
2. **Markers on the joints in the front view** — each one on the joint it names, left and right
   the right way round; a marker off its joint misplaces that bone.
3. **Before the first download** — play a stock clip with the arms overhead and the knees deep:
   skin dragged off the torso by an arm, or a knee bending mid-thigh, means a marker or the pose
   was wrong. Fix and rig again; nothing downstream repairs it.

## 5. Export settings

- **Format: `FBX for Unity(.fbx)`** — not plain `FBX(.fbx)`.
- **First download: the body, With Skin.** It carries the mesh and owns the Avatar.
- **Every other animation: Without Skin.** A clip file about as large as the body means the skin
  toggle was left on.
- **In Place: on** for locomotion. Translation belongs to the Rigidbody / CharacterController; a
  clip that also translates fights it every frame.
- **Trim: keep the full range** — cutting either end of a loop makes the seam pop.
- **Frames per second: 30.** One rate across the set.
- **Keyframe Reduction: none** — a loop is short already, so reduction costs quality and saves
  little.
- Leave **Overdrive / Arm-Space** neutral; speed variation is a runtime concern
  (`reference/unity-import.md` §5).

## 6. File naming — the one thing to get right by hand

Mixamo names each download after the animation. Rename before the files reach the character
folder; the Editor automation keys off these names (`reference/editor-scripts.md`):

| File | Meaning |
|---|---|
| `runner.fbx` | The **With Skin** export. Carries the mesh, owns the Avatar. **No `@` in the name.** |
| `runner@RunSlow.fbx` | Animation only. `runslow` → clip `RunSlow`, looping. |
| `runner@RunFast.fbx` | Animation only. `runfast` → clip `RunFast`, looping. |
| `runner@Jump.fbx` | Animation only. `jump` → clip `Jump`, one-shot. |
| `runner@HitReaction.fbx` | Animation only. `hit` → clip `Hurt`, one-shot. |

Then: `reference/unity-import.md` for the importer and Avatar, `reference/textures.md` and
`MixamoTextures.cs` for the material Mixamo did not return.
