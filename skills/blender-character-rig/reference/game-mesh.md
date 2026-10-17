# Game mesh — the ship track's mesh, made before the rig

> Part of the `blender-character-rig` skill. Stage S5 of the ship track (skill
> `game-character-pipeline`): the class's budget is picked first
> (`unity-3d-models` → `reference/budgets.md`), this file turns the character into a mesh at
> that budget, and the rig is built once, on that mesh. The preview track rigs the dense
> generated mesh as it is and never ships it.

**Every decimation, retopology and rebake of a mesh that will be skinned happens before
rigging.** Decimating a rigged mesh breaks its weights and its UVs, and invalidates everything
taken on the old vertices: weight snapshots and their backups, the wrist correction, the grip
point of a held prop. Discover the budget after rigging and the rig is built again.

## Pick the route

| Situation | Route |
|---|---|
| The default | **A — regenerate at the preset.** The class's `3D budgets` row names a `preset`; generate the same approved views at it |
| A static copy reads well, but the joints deform badly in the deformation test below (an elbow pinches to a line, a shoulder caves in, a knee folds), or the generated topology swirls through a joint | **B — retopology, UVs, rebake from the showcase** |
| Close-up hands or face | B, plus hand work on those parts — finger loops are a modelling job, not a setting |

Both routes end at the same gates. Run route A first: it costs one generation, and its baked maps
already sit on its surface.

## Route A — regenerate at the preset

1. Generate at the row's `preset` from the inputs and seeds the showcase used, with upload names
   unique to this run — `comfyui-asset-generation` → `reference/image-to-3d-tuning.md`.
2. Check the GLB against the row: `inspect_glb.py rung.glb --budgets ART_DIRECTION.md --class
   character` (`comfyui-asset-generation`).
3. Import and normalise it as the showcase was (`reference/import-and-survey.md`; `bcr_import_prep`
   and its gates). Never decimate it further: its normal and occlusion maps were baked onto this
   exact surface.
4. Run the deformation test, then the gates.

## Route B — retopology, UVs, rebake

The showcase stays untouched as the source of detail; the game mesh is a new object beside it,
both normalised (scale, facing, origin between the feet) before anything else.

1. **One surface.** A generated mesh is a thin double shell split along every UV seam, and
   QuadriFlow on it can return the wrong face count or a fused shell. Voxel-remesh a copy first,
   with a voxel smaller than the thinnest part that must survive (a finger, an ear), then
   check: one loose part, extents within e.g. 1% of the showcase's.
2. **Retopology.** QuadriFlow returns quads, so ask for half the triangle target:
   `target_faces = target_tris / 2`, symmetry on for a symmetric character. It reports failure
   only as a `{'CANCELLED'}` return and a warning that the mesh "needs to be manifold" — which it
   can say of a closed voxel mesh many times denser than the target. Check the return and the
   face count; collapse-decimating the voxel mesh to a few times the target first gets it through.
   A retopology service or another tool is checked the same way. QuadriFlow does not place loops
   at joints; the deformation test is what says whether its flow is good enough.
3. **UVs.** Smart UV Project, or seams and Unwrap where islands should follow the body. The
   island margin is in UV units: e.g. 4 px at `target_tex_px` is `4 / target_tex_px`. Check for
   overlaps (`uv.select_overlap`).
4. **Rebake from the showcase**, Selected-to-Active in Cycles: one image per map at
   `target_tex_px` — base colour (Diffuse, colour pass only, sRGB), normal (tangent, Non-Color),
   occlusion. `cage_extrusion` and `max_ray_distance` scale with the character: start around 2–3%
   of its height, e.g. 0.03 and 0.1 for a 1.7 m runner. Save each image to a file.
5. **Look at it.** The game mesh textured, beside the showcase, from the same camera — front, side,
   back, and the game camera.

The calls, as one script for the server's code tool or `Blender -b --python` (names are the
courier run's; adapt the numbers):

```python
import bpy
show, game = bpy.data.objects["Runner_showcase"], bpy.data.objects["Runner_game"]  # game: a copy
def only(*objs, active):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = active

only(game, active=game)
game.data.remesh_voxel_size = 0.005                      # under the thinnest part to keep
bpy.ops.object.voxel_remesh()
pre = game.modifiers.new("pre", "DECIMATE")             # a few times the target, or QuadriFlow cancels
pre.ratio = min(1.0, 8 * 4000 / len(game.data.polygons))
bpy.ops.object.modifier_apply(modifier="pre")
done = bpy.ops.object.quadriflow_remesh(target_faces=4000, use_mesh_symmetry=True, mode="FACES", seed=0)
assert done == {"FINISHED"}, "QuadriFlow cancelled: read the warning, step 2"     # target_tris 8000
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=4 / 2048)
bpy.ops.object.mode_set(mode="OBJECT")

game.data.materials.clear()
mat = bpy.data.materials.new("Runner_game"); mat.use_nodes = True; game.data.materials.append(mat)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
bake = scene.render.bake
bake.use_selected_to_active, bake.cage_extrusion, bake.max_ray_distance, bake.margin = True, 0.03, 0.1, 4
only(show, game, active=game)
for name, kind, space, extra in (("BaseColor", "DIFFUSE", "sRGB", {"pass_filter": {"COLOR"}}),
                                 ("Normal", "NORMAL", "Non-Color", {}),
                                 ("Occlusion", "AO", "Non-Color", {})):
    image = bpy.data.images.new(f"Runner_{name}", 2048, 2048)
    image.colorspace_settings.name = space
    node = mat.node_tree.nodes.new("ShaderNodeTexImage"); node.image = image
    mat.node_tree.nodes.active = node                    # the bake writes to the active image node
    bpy.ops.object.bake(type=kind, **extra)
    image.filepath_raw = f"//textures/Runner_{name}.png"   # // is the saved .blend's folder
    image.file_format = "PNG"; image.save()
```

Then wire the baked images into the game mesh's material, and look before the gates.

**Blender's Decimate modifier** (Collapse, Triangulate on, Symmetry for a symmetric character) is
the quick alternative where topology does not deform — a prop on a bone, a hard-surface part.
Its `ratio` is a fraction of the current **triangles**: `target_tris / triangles`. Which tool for
which mesh: the table in `unity-3d-models` → `reference/budgets.md`.

## The deformation test, and carrying the preview weights

A static picture cannot show a joint. Before the real rig, give the candidate mesh the preview
rig's weights and pose it:

```python
only(game, active=game)
for group in show.vertex_groups:
    if group.name not in game.vertex_groups: game.vertex_groups.new(name=group.name)
dt = game.modifiers.new("weights", "DATA_TRANSFER")
dt.object, dt.use_vert_data = show, True
dt.data_types_verts = {"VGROUP_WEIGHTS"}
dt.vert_mapping = "POLYINTERP_NEAREST"
dt.layers_vgroup_select_src, dt.layers_vgroup_select_dst = "ALL", "NAME"
bpy.ops.object.modifier_apply(modifier="weights")
bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)
game.modifiers.new("Armature", "ARMATURE").object = bpy.data.objects["RunnerRig"]
```

Then the extreme-pose table of step 6 in `SKILL.md`: `bcr_pose` op `apply` → `bcr_preview`
`still` → op `reset`. **The picture is mandatory.** Transferred weights blur across every gap the
nearest-face lookup can jump: arm to torso, leg to leg, between fingers. Use them as the test, or
as a head start the real skinning step then checks with the same gates (unweighted vertices 0, at
most 4 influences, sums 1) and the same picture; local repairs are `blender-retarget` →
`reference/weight-repair.md`. Never take them unseen.

Joints that pinch or collapse here send route A to route B, and route B back to its retopology
step with loops placed at those joints.

## Gates and artefacts

| Gate | Passes when |
|---|---|
| Budget | `inspect_glb.py --budgets` on the exported GLB, or the triangle count read in Blender: at or under `target_tris × 1.25`, never over a ceiling; maps at `target_tex_px` |
| One surface | Route B: one loose part, no inner shell |
| Silhouette | Same camera, showcase and game mesh: extents within e.g. 1%, no thin part lost |
| UVs | No overlaps; every island inside 0–1 |
| Bake | No black or smeared patches where rays missed or the cage crossed a gap |
| Joints | **Picture**: the extreme poses with transferred weights |
| Approval | **A person**, from one side-by-side image: showcase and game mesh, clay and textured, same cameras |

Artefacts, each with its hash in the ledger (skill `art-asset-registry`), the showcase version as
its parent:

- `ArtDirection/sources/Runner_game.blend` — the game mesh, unrigged, saved before S6 starts;
- the baked maps, `ArtDirection/sources/textures/Runner_*.png`;
- `ArtDirection/previews/Runner_game_vs_showcase.png` — the approval image;
- the inspect JSON of the exported GLB.

Then stage S6: rig once, on this file — this skill's pipeline, or the Auto-Rig Pro route in
`blender-retarget` → `reference/arp-route.md`.
