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
in the same frame. Headless, `scripts/game_mesh.py` runs steps 1–5 and their gates in one call
([the gated run](#the-gated-run)); the steps below are what it does, and the calls for a session
in the user's Blender.

1. **One surface.** A generated mesh is a thin double shell split along every UV seam, and
   QuadriFlow on it can return the wrong face count or a fused shell. Voxel-remesh a copy first,
   with a voxel smaller than the thinnest part that must survive (a finger, an ear), delete the
   specks it leaves (pieces of a few vertices), then check: one loose part, extents within e.g. 1%
   of the showcase's. Never keep only the largest piece: legs the grid leaves apart from a hem
   above them are a piece too. **A voxel remesh does not remove a back-to-back inward-facing inner
   shell** when it is joined to the skin at the hems and cuffs: it comes out as the inside of a
   thin hollow wall, one piece, closed, and QuadriFlow then spends about half the budget on the
   inside. Check the enclosed volume against a coarse (2% of the height) voxel copy, which fills
   any thin wall, and fill the cavity (`game_mesh.py` floods the outside on a voxel grid and adds the
   rest as blocks before remeshing again). Stripping the shell first (`scripts/shell_strip.py`)
   and closing the holes it leaves is not enough on its own: the voxel copy stays partly hollow.
2. **Retopology.** QuadriFlow returns quads, so ask for half the triangle target:
   `target_faces = target_tris / 2`, symmetry on for a symmetric character. It reports failure
   only as a `{'CANCELLED'}` return and a warning that the mesh "needs to be manifold" — which it
   says of a closed manifold voxel mesh more than about 6 times the target's triangles. Check the
   return and the face count; collapse-decimate the voxel mesh to 4 times the target first. It
   returns somewhat fewer faces than asked: rescale `target_faces` by target / result and rerun.
   A retopology service or another tool is checked the same way. QuadriFlow does not place loops
   at joints; the deformation test is what says whether its flow is good enough.
3. **UVs.** Smart UV Project, or seams and Unwrap where islands should follow the body. A
   projected island can fold onto itself (a hem, a sleeve cuff): at a 66° angle limit that is a few
   percent of the texels on a coat. Project at 45°, mark seams from the islands, unwrap them
   angle-based, project again the faces that still overlap (a band-shaped island flattens onto
   itself), average the island scales and pack. The island margin is in UV units: e.g. 4 px at `target_tex_px` is
   `4 / target_tex_px`. Check for overlaps (`uv.select_overlap`).
4. **Rebake from the showcase**, Selected-to-Active in Cycles: one image per map at
   `target_tex_px` — base colour (Diffuse, colour pass only, sRGB), normal (tangent, Non-Color),
   occlusion. `cage_extrusion` and `max_ray_distance` scale with the character: start around 2–3%
   of its height, e.g. 0.03 and 0.1 for a 1.7 m runner. The Diffuse colour pass is base colour ×
   (1 − metallic): hold the showcase's Metallic at 0 for that bake, or a metal button bakes black.
   Save each image to a file.
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
pre = game.modifiers.new("pre", "DECIMATE")             # 4 x the target, or QuadriFlow cancels
pre.ratio = min(1.0, 4 * 8000 / sum(len(p.vertices) - 2 for p in game.data.polygons))
bpy.ops.object.modifier_apply(modifier="pre")
done = bpy.ops.object.quadriflow_remesh(target_faces=4000, use_mesh_symmetry=True, mode="FACES", seed=0)
assert done == {"FINISHED"}, "QuadriFlow cancelled: read the warning, step 2"     # target_tris 8000
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=0.7854, island_margin=4 / 2048)   # 45 degrees
bpy.ops.uv.seams_from_islands()
bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=4 / 2048); bpy.ops.uv.pack_islands(margin=4 / 2048)
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

### The gated run

```bash
python3 scripts/game_mesh.py Runner_showcase.glb --out ArtDirection/sources \
        --target-tris 8000 --tex-px 2048 --name Runner --body human --symmetry
```

It starts Blender itself (`scripts/game_mesh.py --blender PATH`, else `$BLENDER`, `blender` on
`PATH`, the usual install), or runs inside it: `blender -b --factory-startup -P
scripts/game_mesh.py -- ...`. A `.blend` showcase names its object with `scripts/game_mesh.py
--object Runner_showcase`; it is appended into an empty scene, never opened for writing. It
writes `<name>_game.glb`, `<name>_game.blend` (the game mesh alone, the maps linked),
`textures/<name>_{BaseColor,Normal,Occlusion}.png`, `<name>_game_vs_showcase.png` (rows: showcase
textured, game textured, showcase clay, game clay; columns front, three-quarter, side, back),
`<name>_bake_miss.png` (the UV layout, red where no ray hit), `mesh_check.json` and
`game_mesh.json` (gate/1). Roughness and metallic are not baked: the material reads 0.7 and 0. Exit 0 every gate passed, 2 a gate failed, 1 refused.

| Gate | Value, and its limit |
|---|---|
| `game.tris` | triangles, in [0.5 × target, target] |
| `game.one_surface` | loose pieces of the game mesh, ≤ 1 |
| `game.solid` | enclosed volume over that of a 2%-of-height voxel remesh of the game mesh (which fills a thin hollow wall), ≥ 0.9; a hollow shell reads its wall's share |
| `game.extent` | the largest of the three axis differences between game and showcase extents, over the height, ≤ 0.01 |
| `game.silhouette_iou_min` | the smallest silhouette IoU of 8 orthographic views (every 45°, one frame, 512 px), ≥ 0.95 |
| `game.uv_bounds` | UV corners outside 0–1, 0 |
| `game.uv_overlap` | texels covered by two or more UV triangles over texels covered, at `--tex-px`, a texel counted when its centre lies strictly inside, so a shared edge never counts twice; ≤ 0.001 (projection folds of Smart UV Project) |
| `game.uv_stretch` | per triangle, the singular values s1 ≥ s2 of the 3D → UV map over the whole mesh's mean scale k: max(s1/k, k/s2), how far a texel is stretched or squashed in its worst direction; 95th percentile by surface area, ≤ 2 |
| `game.bake_miss` | texels inside the islands (1 px in) no ray reached, from a no-margin base colour bake, ≤ 0.005 |
| `game.bake_delta` | mean CIE76 ΔE between unlit texture renders of showcase and game, same 8 cameras, over the pixels both cover (2 px in), ≤ 6 |
| `game.mesh_check` | `character-autorig` `mesh_check.py --body` on the written GLB passes |

The knobs, each a fraction of the height H where it is a length:

```bash
python3 scripts/game_mesh.py SHOWCASE.glb --out DIR --target-tris N --voxel 0.005 --cage 0.02 --ray 0.06 \
        --margin-px 4 --ao-samples 32 --seed 0
```

`--voxel` under the thinnest part to keep; `--cage` and `--ray` the bake's `cage_extrusion` and
`max_ray_distance`; `--margin-px` the island and bake margin in texels. A failed
`game.bake_miss` is a cage or ray too short, or webbing the retopology stretched across a gap
(an armpit, a crotch under a coat) with no showcase surface behind it: the miss map says which.
A failed `game.silhouette_iou_min` or `game.extent`
at a sound bake is detail the budget cannot carry (spiky hair tips, fingers merged into a
mitten): look at the sheet, then a larger budget, hair cards, or the regenerate route.

**AutoRemesher** (MIT, a desktop app with a command line; OBJ only) is the alternative retopology:

```bash
python3 scripts/game_mesh.py SHOWCASE.glb --out DIR --target-tris N \
        --autoremesher /path/to/autoremesher.app --timeout 600
```

It runs on the voxel surface with `--target-quads` target / 2 and `QT_QPA_PLATFORM=offscreen`,
under `--timeout` seconds. A timeout, a crash, no output or a result over the budget falls back
to QuadriFlow, and `retopo.fallback` says which; the gates are the same either way.

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
| Budget | `inspect_glb.py --budgets` on the exported GLB, or the triangle count read in Blender: at or under `target_tris × 1.25`, never over a ceiling; maps at `target_tex_px`. Route B's `game.tris` holds it at or under `target_tris` |
| One surface | Route B: one loose part, no inner shell (`game.one_surface`, `game.solid`) |
| Silhouette | Same camera, showcase and game mesh: extents within e.g. 1%, no thin part lost (`game.extent`, `game.silhouette_iou_min`) |
| UVs | No overlaps; every island inside 0–1 (`game.uv_overlap`, `game.uv_bounds`; `game.uv_stretch`) |
| Bake | No black or smeared patches where rays missed or the cage crossed a gap (`game.bake_miss`, `game.bake_delta`, then the sheet) |
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
