# Image to 3D — budgets, knobs and symptoms

Every knob is a node input, addressed `NODE.INPUT` and changed per run with `--set`
(`reference/comfyui-api.md`). Change one knob per run and compare against the previous run's QA
renders and `inspect_glb.py` output.

## Node addresses

The ids are the same in all three templates unless noted, and the same as in the saved UI
workflows.

| Node | Class | Holds |
|---|---|---|
| `122` | LoadImage | the input image (single-image templates) |
| `801`–`804` | LoadImage | front, left, back, right views (multi-view) |
| `192` / `193` | RemoveBackground, loader | the subject mask (single image) |
| `312` | ImageCropToMask | 1024×1024 on black; `pad_factor` 1.1 (Pixal3D), 1.0 (TRELLIS.2) |
| `56`→`242`→`298` | MoGeInference → MoGeGeometryToFOV → Pixal3DConditioning | per-image FoV (Pixal3D single image) |
| `299` | Trellis2Conditioning | TRELLIS.2 template |
| `324` | Pixal3DMultiViewConditioning | `fov` 20; `front`, `left`, `back`, `right` |
| `319` / `40` | UNETLoader | Pixal3D or multi-view model / TRELLIS.2 model |
| `3` | KSampler | sparse structure: `seed` 56, `steps` 12, `cfg` 7.5 |
| `119` | VaeDecodeStructureTrellis2 | `resolution` "32" |
| `18` | KSampler | shape at 512: `seed` 42, `steps` 20 |
| `94` | Trellis2UpsampleStage | `target_resolution` 1536 (1024–2048, step 128) |
| `23` | KSampler | upsampled shape: `seed` 42, `steps` 12 |
| `12` | KSampler | texture: `seed` 43, `steps` 12, `cfg` 1 |
| `241` | RemeshMesh | `resolution` 384, `sign_mode` udf, `smooth_iters` 20, `drop_small_components` 0.01 |
| `186` | DecimateMesh | `target_face_count` 8000, `placement_mode` midpoint |
| `238`, `260` | MeshSmoothNormals | `crease_angle` 180 (before unwrap; after texturing) |
| `196` | UnwrapMesh | `segmenter` pec, `padding` 4, `weld_distance` 0.0002 |
| `288` | PrimitiveInt | `value` 1024: texture size for unwrap, base-colour bake and normal bake |
| `147` | BakeTextureFromVoxel | base colour, metallic, roughness |
| `224` | BakeNormalMapFromMesh | decimated mesh against the remeshed one; `cage_distance` 0.05 |
| `233` | BakeAmbientOcclusion | `resolution` 1024, `samples` 64, `max_distance` 0.71, `bias` 0.05, `strength` 1 |
| `210` | ApplyTextureToMesh | assembles the material |
| `322` | Save3DAdvanced | writes `3d/<template name>_NNNNN.glb` |
| `900`–`953` | RotateMesh, RenderMesh, RenderUVAtlas, SaveImage | the QA renders under `3d/qa/`; `953` (`crop`) single image only |

Dynamic-combo inputs take dotted keys: `sign_mode` udf carries `sign_mode.qef`; `placement_mode`
qem needs `placement_mode.line_quadric_weight`, `.feature_edge_quadric_weight`,
`.feature_edge_min_dihedral_deg` and `.clamp_v_to_edge` in the same run.

The templates differ from the saved UI workflow on purpose: face count 8000 (UI 700000),
remesh resolution 384 (UI 768), texture size 1024 (UI 4096), normal-bake resolution tied to
`288` (UI fixed 2048), occlusion `bias` 0.05 (UI 0.01), unwrap `padding` 4 (UI 1). They add the QA renders, replace the UI's
switch nodes with one template per path, and the multi-view template takes four prepared views
where the UI crops each sheet panel to its own mask.

## Budget presets

| Preset | `186.target_face_count` | `241.resolution` | `288.value` | File size |
|---|---|---|---|---|
| Pickup | 2000 | 128 | 1024 | ~3 MB |
| Obstacle, environment prop | 4000 | 256 | 1024 | ~4 MB |
| Hero (template default) | 8000 | 384 | 1024 | ~4 MB |
| Close-up prop | 20000 | 768 | 2048 | ~15 MB |
| Showcase (the UI workflow's values) | 700000 | 768 | 4096 | ~65 MB |

The first three are named for the rows of the triangle-budget table in `unity-3d-models` and
sit inside them; that table, not this one, says what a game can afford. Close-up is for a prop
the camera gets near and the game does not pool; showcase is not a game asset.

```bash
--set 186.target_face_count=2000 --set 241.resolution=128                        # pickup
--set 186.target_face_count=4000 --set 241.resolution=256                        # obstacle, environment prop
--set 186.target_face_count=20000 --set 241.resolution=768 --set 288.value=2048  # close-up prop
```

- **The face target and the remesh resolution move together.** 5000 faces asked of a 768 remesh
  shreds the mesh: thin parts vanish, the silhouette collapses, the bounding box shrinks. 4000
  from a 256 remesh, or 2000 from 128, holds both. 2000 is the floor of the pairs above: below
  it, run the check on every asset.
- Check: compare `extents` from `inspect_glb.py` with a higher-budget run of the same input. A
  shrink over 10% means the pair is mismatched, whatever the triangle count says.
- Keep `241` in the chain. Decimating the decoded mesh directly returns half the requested
  faces with shrunken bounds, at three times the run time.
- Leave `placement_mode` at midpoint: qem adds four inputs and no visible gain at these budgets.
- From 20000 faces down, small relief (engraving on a crate lid) leaves the geometry and survives in the
  normal map and base colour: judge it on the textured renders, not on `clay`.

### The mesh is a thin double shell

Every face has an opposite-facing twin a fraction of a percent of the bounding-box diagonal
behind it; about half the triangles and half the UV atlas face inward. Both model paths do
this, and no remesh option removes it — not `sign_mode.drop_inverted_components`, not
`sign_mode.drop_enclosed_components`, not `sign_mode` sdf, with or without `manifold`.

- The inner shell sits just behind the outer one and faces away from the viewer: it is hidden
  from outside, so it is not a visual defect.
- The visible surface gets about half of `target_face_count`: N triangles buy the detail of N/2.
- The GLB's material is exported double-sided (`double_sided` in `inspect_glb.py` output), which
  draws the inner shell as well and lets it z-fight at a distance. Make the imported material
  front-face only, then confirm in the engine that no face went missing.
- The engine's triangle budget still counts all of them.

## Occlusion

The occlusion image looks half black at any setting: the inward-facing shell is legitimately
dark and holds half the atlas. Judge `3d/qa/occlusion` by shape, never by its amount of black.

| Pattern | Meaning | Move |
|---|---|---|
| hard-edged black blocks matching whole UV charts, next to white ones | the inner shell | none |
| black speckle or patches inside otherwise-white charts | rays starting inside the dense mesh | `--set 233.bias=0.1` |

Occlusion cannot be unplugged with `--set`; `--set 233.strength=0` bakes it white, which is the
same thing to the engine.

## Symptoms and the knob that moves them

| Symptom | Cause | Move |
|---|---|---|
| Mesh tilted in the world; `front` render equals the input | Pixal3D single image is pixel-aligned | rotate the `Model` child in Unity, or use the multi-view template |
| Depth far too large or small, sides smeared | straight-on single view | three-quarter view, or multi-view |
| Depth stretched on a wide object (multi-view) | views fitted one by one, not at one scale | cut all four as squares of one side |
| Orange turns yellow-green, hues bleed between sides (multi-view) | left and right views swapped | swap `802.image` and `804.image` first; re-seeding does not fix it |
| Mesh distorted (multi-view) | `324.fov` too wide for generated views | keep 20 |
| Shredded silhouette, `extents` shrunk >10% | face target too low for the remesh resolution | lower `241.resolution` with the target |
| Fewer faces than asked, shrunken bounds, per-triangle charts | `sign_mode` sdf | keep udf |
| Triangle count about half the target, bounds shrunk | remesh bypassed | keep `241` in the chain |
| Black patches inside lit charts of the occlusion map | `bias` too low | `233.bias` 0.1 |
| Small details smeared, hue drift | TRELLIS.2 path | Pixal3D path |
| Top face plain, emblem missing (multi-view) | a level turnaround never shows the top | single-image three-quarter path |
| Texture darker than the input (multi-view) | the multi-view texture stage | correct in the material, or regenerate single-image |
| Dark skirt round the base | a contact shadow inside the mask | regenerate the source without it |

## VRAM and time

- `94.target_resolution` 1024 is the first move when free VRAM is short: about 20% faster, no
  visible loss at prop budgets.
- Switching between the three models costs one reload, tens of seconds, and no `/free`.

## Knobs to try with a check step

These follow the nodes' own advice. Change one, rerun, and keep it only when the check holds.

| Knob | Advice | Check |
|---|---|---|
| `238.crease_angle`, `260.crease_angle` 30–60 | hard-surface shading; splits vertices | crisp edges in `clay` |
| `224.cage_distance` up / down | up for missing normal-map patches under heavy decimation; down when it grabs across gaps | textured renders |
| `241.smooth_iters` below 20 | keeps sharp edges; 2–3 cleans staircase artefacts, higher over-smooths | no stair-stepping in `clay` |
| `'119.resolution="64"'`, `94.target_resolution` above 1536 | higher resolution, at a cost in VRAM and time | a visible gain in `clay`; `vram_free_min` in the client output, run time |
| `196.segmenter` adaptive, `196.weld_distance` ~0.001 | for per-triangle charts; adaptive runs on CPU, slower | `uv_atlas` shows islands |
