# Image to 3D — generation presets, knobs and symptoms

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
| `241` | RemeshMesh | `resolution` 768, `sign_mode` udf, `smooth_iters` 20, `drop_small_components` 0.01 |
| `186` | DecimateMesh | `target_face_count` 70000, `placement_mode` midpoint |
| `238`, `260` | MeshSmoothNormals | `crease_angle` 180 (before unwrap; after texturing) |
| `196` | UnwrapMesh | `segmenter` pec, `padding` 4, `weld_distance` 0.0002 |
| `288` | PrimitiveInt | `value` 2048: texture size for unwrap, base-colour bake and normal bake |
| `147` | BakeTextureFromVoxel | base colour, metallic, roughness |
| `224` | BakeNormalMapFromMesh | decimated mesh against the remeshed one; `cage_distance` 0.05 |
| `233` | BakeAmbientOcclusion | `resolution` 1024, `samples` 64, `max_distance` 0.71, `bias` 0.05, `strength` 1 |
| `210` | ApplyTextureToMesh | assembles the material |
| `322` | Save3DAdvanced | writes `3d/<template name>_NNNNN.glb` |
| `900`–`953` | RotateMesh, RenderMesh, RenderUVAtlas, SaveImage | the QA renders under `3d/qa/`; `953` (`crop`) single image only |

Dynamic-combo inputs take dotted keys: `sign_mode` udf carries `sign_mode.qef`; `placement_mode`
qem needs `placement_mode.line_quadric_weight`, `.feature_edge_quadric_weight`,
`.feature_edge_min_dihedral_deg` and `.clamp_v_to_edge` in the same run.

The templates differ from the official UI workflow on purpose: face count 70000 (UI 700000),
texture size 2048 (UI 4096), normal-bake resolution tied to `288` (UI fixed 2048), occlusion
`bias` 0.05 (UI 0.01), unwrap `padding` 4 (UI 1). They add the
QA renders, replace the UI's switch nodes with one template per path, and the multi-view template
takes four prepared views where the UI crops each sheet panel to its own mask.

## Diff against the official template before tuning

A project graph drifts: a copy made for one asset keeps its padding, a bias someone tried, a
resolution that was a link to `288` and is now a number. Seen from the output, every such drift
looks like a model fault. Before changing a knob, export the official workflow in API format
(`reference/comfyui-api.md`, Saved workflows) and compare the graph you are about to tune with it:

```bash
python3 scripts/graph_diff.py official_multiview_api.json work/runner_r03_api.json \
  --ignore filename_prefix --ignore image          # exit 0 same, 1 differ, 3 unreadable
#   node 196 UnwrapMesh.padding: 1 -> 4
#   node 224 BakeNormalMapFromMesh.resolution: 2048 -> link 288:0  [literal -> link]
```

Every line is either a choice you can name (a preset below, the QA renders) or a drift: put the
drift back first, rerun once, and only then tune. `--json` gives the same as one object for a
change record; `--common-only` leaves out nodes only one graph holds. Node ids match between the
templates and the saved UI workflow; a graph renumbered by hand diffs as nodes added and removed.

## Generation presets

| Preset | `186.target_face_count` | `241.resolution` | `288.value` | File size |
|---|---|---|---|---|
| Small | 2000 | 128 | 1024 | ~3 MB |
| Medium | 4000 | 256 | 1024 | ~4 MB |
| Compact | 8000 | 384 | 1024 | ~4 MB |
| Large | 20000 | 768 | 2048 | ~10–15 MB |
| Template (no `--set`) | 70000 | 768 | 2048 | ~13–18 MB |
| Showcase (the official UI workflow's values) | 700000 | 768 | 4096 | ~65 MB |

These are generation settings — a face target, the remesh resolution that holds it, a texture
size — and none of them is a budget. File size is mostly the textures and moves with the input
more than with the face target. 70000 is the templates' default, not "the character budget", and
700000 is not "the quality setting": they are rungs of one ladder. What a class of asset may cost
is its `3D budgets` row, chosen by comparing these presets in the game: `unity-3d-models` →
`reference/budgets.md`.

- **Generate each preset once and compare.** Run time barely depends on the face count — a
  700000-face run takes about as long as a 20000-face one (e.g. 90 s against 80 s on one
  server) — and a rerun that changes only a late stage can reuse the server's cache up to it
  (`execution_cached` lists what was reused): only the changed stages run. One input, the same seeds, six presets: the
  comparison costs minutes, a wrong guess costs a rigging pass.
- **Showcase is the baseline**, the version every cheaper one is compared with; it need not ship.
  The `--set`s below give its face count and texture only (the remesh is the template's). For the official
  workflow's full settings add `--set 196.padding=1 --set 233.bias=0.01 --set 224.resolution=2048`,
  then confirm with `graph_diff.py` that nothing else differs.
- A character that will be rigged: generate the ladder up to Showcase; the preset that ships is
  the `character` row's (`unity-3d-models` → `reference/budgets.md`). The visible surface gets
  half the triangles, and a joint that bends needs them: below Large, look at the joints in an
  extreme pose before accepting a rung, and a rung that deforms badly goes to route B of
  `blender-character-rig` → `reference/game-mesh.md`. A preview rig takes the template's mesh
  (70000 faces, about 35000 on the visible skin) as it is.

```bash
--set 186.target_face_count=2000 --set 241.resolution=128 --set 288.value=1024  # small
--set 186.target_face_count=4000 --set 241.resolution=256 --set 288.value=1024  # medium
--set 186.target_face_count=8000 --set 241.resolution=384 --set 288.value=1024  # compact
--set 186.target_face_count=20000                                               # large
                                                                                # template: no --set
--set 186.target_face_count=700000 --set 288.value=4096                         # showcase
```

- **The face target and the remesh resolution move together.** 5000 faces asked of a 768 remesh
  shreds the mesh: thin parts vanish, the silhouette collapses, the bounding box shrinks. 4000
  from a 256 remesh, or 2000 from 128, holds both. 2000 is the floor of the pairs above: below
  it, run the check on every asset.
- Check: compare `extents` from `inspect_glb.py` with a higher-face-target run of the same input. A
  shrink over 10% means the pair is mismatched, whatever the triangle count says.
- Keep `241` in the chain. Decimating the decoded mesh directly returns half the requested
  faces with shrunken bounds, at three times the run time.
- Leave `placement_mode` at midpoint: qem adds four inputs and no visible gain at these face targets.
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
- The engine draws all of them, and a class's triangle budget counts all of them.
- Automatic (bone-heat) skin weights fail on it: the inner shell is hidden from every bone and
  the mesh is several islands, so the solve fails or leaves vertices unweighted.
- Weights computed from position give the inner twin of a vertex the same weights as the skin
  over it: skill `blender-character-rig`, its armature-and-skinning reference.
- Keep the shell when rigging — the baked normal and occlusion maps address it — and cull back
  faces instead of deleting it.

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
  visible loss at the prop presets above.
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

## Diagnosing a bad shell by stage

Sheets, slabs, a missing limb or a torn silhouette came from somewhere in the graph or its input.
Narrow it down before changing a knob: one diagnostic that can answer costs less than another
full run, and an unchanged rerun answers nothing.

1. **Diff the graph first** (Diff against the official template, above). A drifted setting is
   the cheapest cause to rule out.
2. **Look at what the model was given.** Single image: `3d/qa/crop` is all the model sees and
   must show the subject whole on black; node `312` takes its mask from `192`, or from the
   image's own alpha through an added `InvertMask` (`reference/image-to-3d.md`, Input image).
   Four views: the black composites from `reference/image-to-3d.md`, Background removal for
   four views. An inverted mask — background kept, subject cut out — is one way to get thin
   sheets around the silhouette, not the only one: soft halos, a contact shadow or a background
   that is near-black but not black can do it too. Which way a mask points is a convention of
   each node: `RemoveBackground` gives 1 on the subject and `ImageCropToMask` keeps 1;
   `LoadImage`'s mask is 1 where the image is transparent and `JoinImageWithAlpha` writes
   alpha = 1 − mask. A crop that shows the background, or a cut-out with the subject
   transparent, is a mask fed across the two conventions without an `InvertMask`.
3. **Bisect by stage, keeping each stage's output.** The templates save only the final GLB. On a
   copy of the graph, add a `MeshToFile3D` and a second `Save3DAdvanced` with its own
   `filename_prefix` on the output of `92`, the shape decode, so the raw mesh is kept beside it.
   While the server keeps its cache, only the added and changed nodes run (`execution_cached`
   lists the rest), so such a rerun can take seconds.

   | Stage | Nodes | Keep | What it can tell |
   |---|---|---|---|
   | shape decode | `3`, `119`, `18`, `94`, `23` → `92` | the raw mesh | sheets already here did not come from remesh or decimate; the input, the views and the model all remain suspects |
   | remesh and decimate | `241`, `186` | the final GLB beside the raw mesh | a fault absent from the raw mesh and present after: the remesh–decimate pair (Generation presets) |
   | texture | `12`, `147` | the textured renders | one side's colours on another: the views (Symptoms) |
   | bake | `224`, `233` | each map on its own | colour or shading projected where the input never showed |

   The inner twin of the thin double shell above is expected output, not this fault: it lies a
   fraction of a percent behind the outer surface and faces inward, where these sheets stand away
   from the body.
4. **Name every upload uniquely per asset, view and run.** An upload keeps its basename
   (`reference/comfyui-api.md`), and `--set 801.image=<name>` points the graph at whatever file
   the server holds under that name. Without `--overwrite-uploads`, a stock ComfyUI server that
   already holds a different file of that name stores the new one under a suffixed name
   (`front (1).png`), and the run uses the older image with no error. Put the asset, the view and
   the run in each name (`runner_front_r03.png`); the client warns on stderr when the server
   stored an upload under another name.
5. **Never resend an identical input and parameter set.** The template seeds are fixed, so the same
   image and the same knobs return the same mesh, and the server may serve every node from its cache
   (`execution_cached`). Change one thing (the input, one knob, a seed) or stop.

Each diagnosis ends in one of these, written into the change record (`art-asset-registry`):

| Outcome | When |
|---|---|
| fix the input | the crop, a mask or a view is wrong where you can see it |
| fix the drift | `graph_diff.py` shows a setting nobody chose |
| change one knob | the stage is named and the symptom table has a move for it |
| switch to a known-good baseline graph | the project graph is far from the official one, or nobody knows why it differs: run the official workflow's settings on the same cleaned input and seeds, and compare |
| adopt the usable baseline and record its limits | the best version so far is usable for the quality target agreed with the user and further runs stop gaining: keep it, and write down what is still wrong (texture blotches, a fused part) so nobody mistakes it for clean |
