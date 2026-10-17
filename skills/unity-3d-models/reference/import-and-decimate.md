# From a source file to an imported asset

## Prerequisites

- **glTFast** importer: `Window ▸ Package Manager ▸ + ▸ Add package by name ▸
  `com.unity.cloud.gltfast``. Then `.glb`/`.gltf` under `Assets/` import as model
  prefabs (URP materials auto-created). FBX imports natively (no package).
- **gltf-transform CLI** (via `npx`; needs `node` on PATH) for
  inspect/optimize. **In zsh, don't stuff the command in a variable** (`$CLI foo` won't
  word-split) — call `npx --yes @gltf-transform/cli …` directly.
- Assumes a URP project with the source outside `Assets/` in `ArtDirection/raw/3d/<Name>/` and
  shipped models in `Assets/Models/<Class>/<Name>/` (`reference/asset-classes.md`) — substitute
  your own paths in the commands below.

## Pipeline (do these in order)

### 1. Inspect — see how bad it is
```bash
npx --yes @gltf-transform/cli inspect ArtDirection/raw/3d/<Name>/<file>.glb 2>&1 | grep -A4 MESHES
```
Look at `glPrimitives` (triangles). AI models: expect 6–7 figures.

Then read the full output (drop the `grep`) and decide whether step 2 runs. The comparison is
with the class's row in `3D budgets` — `reference/budgets.md`. **Over** means the audit would
warn or fail: more than `target_tris × 1.25`, or over `ceiling_tris`. A class with no
`target_tris` yet has no budget, and nothing says what it can afford: run the preset ladder on
this asset first (`reference/budgets.md`) and bring it to the rung a person picks.

| Triangles vs. the class's target | `TEXTURES` slots | Step 2 |
|---|---|---|
| Over | base colour only, or none | Run it |
| Within | base colour only, or none | Skip — nothing to remove |
| Within | `normalTexture` and `occlusionTexture` present | Skip, and never run it later — the maps are baked to this surface |
| Over | `normalTexture` and `occlusionTexture` present | Generated at a face target (the ComfyUI templates): do not simplify; lower the target there and regenerate. A dense mesh from a tool with no face target: run it |

### 2. Optimize — decimate mesh (the big win) + shrink textures
Static props only. A mesh that will be skinned is decimated or retopologised in Blender
**before rigging** — `blender-character-rig` → `reference/game-mesh.md`; which tool for which
mesh is the table in `reference/budgets.md`.

The **mesh** is almost the entire file/runtime cost, so `simplify` is what
matters. Decimate from the **original** (not an already-decimated copy) for best
quality. Skip this step when the step 1 table says so: `simplify` moves the surface out
from under baked normal and occlusion maps.
```bash
# --ratio = target_tris ÷ the ORIGINAL's triangles; --error = max shape error (bbox fraction)
npx --yes @gltf-transform/cli simplify ArtDirection/raw/3d/<Name>/<file>.glb \
    Assets/Models/<Class>/<Name>/<Name>.glb --ratio <R> --error 0.05
```
Textures (secondary): compress/resize in Unity (select the model's textures → Max Size = the
class's `target_tex_px`, compression on) or `npx … @gltf-transform/cli optimize in out
--texture-compress webp --texture-size <target_tex_px>`.

What a class can afford is its row in `3D budgets`, picked from the generation preset ladder —
`reference/budgets.md`. There is no fixed table of triangle counts.

Verify: `inspect` again — confirm the new triangle count.

### 3. Stage into `Assets/Models/<Class>/<Name>/` — glTFast imports it
Overwriting the same path keeps the asset GUID, so wired prefabs update in place
(but re-run the swap in step 5 if the mesh hierarchy changed).

### 4. Import — focus Unity (or right-click the `.glb` → Reimport)
It becomes an expandable model with mesh + URP materials.

### 5. Wire into a prefab — Editor script, layer-aware
Swap a sprite/placeholder prefab's visual to the model **via Unity's API**
(robust vs. hand-edited YAML). Pattern — write a one-off Editor script under
`Assets/Scripts/Editor/` (e.g. `SwapModelIntoPrefab.cs`):
```csharp
var model = AssetDatabase.LoadAssetAtPath<GameObject>("Assets/Models/Obstacle/LaneBarrier/LaneBarrier.glb");
var root  = PrefabUtility.LoadPrefabContents(prefabPath);
DestroyImmediate(root.GetComponent<SpriteRenderer>());   // drop the 2.5D visual
DestroyImmediate(root.GetComponent<Billboard>());
var vis = (GameObject)PrefabUtility.InstantiatePrefab(model);
vis.name = "Model"; vis.transform.SetParent(root.transform, false);
SetLayer(vis, root.layer);                                // ← critical, see below
PrefabUtility.SaveAsPrefabAsset(root, prefabPath);
PrefabUtility.UnloadPrefabContents(root);
```
Keep the root's collider + tag + gameplay scripts; the model is just the visual. Pivot, scale,
collision and the prefab's name per class: `reference/asset-classes.md`.

### 6. Audit the class folder, then record it
`Tools/Unity Dev/3D Models/Audit Folder` on `Assets/Models/<Class>/` reads every model there
against the class's row — triangles, materials, texture sizes, rig type, bones, clips — and
prints one `[MODEL-AUDIT]` JSON line; it changes nothing — `reference/model-audit.md`. Then record
the asset, its source and the audit in the project ledger: skill `art-asset-registry`, whose
`art-asset-registry` → `reference/ingest.md` reads a tool's JSON output.

## A GLB generated by the ComfyUI templates

The image-to-3D templates in skill `comfyui-asset-generation` decimate inside the graph and
bake normal and occlusion maps from the dense mesh onto the result. Step 2 is skipped; steps
3–6 apply unchanged, glTFast included.

- **Budget.** Generate at the `preset` of the class's `3D budgets` row (`reference/budgets.md`).
  The face target is a `--set` on the graph, and it moves together with the remesh resolution,
  so take both from the preset. Confirm with step 1, or with that skill's
  `inspect_glb.py --budgets ART_DIRECTION.md --class <class>`; more than 25% over `target_tris`
  → the next preset down, regenerated. A class with no target yet runs the ladder
  first: the same asset at every preset up to the class's baseline (`reference/budgets.md`).
- **Thin double shell.** Every face has an inward-facing twin just behind it, so the
  visible surface carries about half the triangle count while Unity's budget counts all of
  them. Budget by the full count and accept the halved detail. The material arrives flagged
  double-sided, which draws the inner shell too: turn double-sided off on the imported
  material so only **front faces** render (where the toggle lives depends on the importer's
  shader — confirm on your glTFast version), then orbit the prop once in the Scene view to
  confirm no face went missing.
- **Scale and origin.** The largest extent is ≈ 1 unit and the origin sits at the
  bounding-box centre, not the base. Scale and offset the `Model` child, never the root:

  ```csharp
  // courier run: a pickup crate 0.6 units across, resting on the lane
  var b = vis.GetComponentInChildren<Renderer>().bounds;       // read before scaling
  float s = 0.6f / Mathf.Max(b.size.x, b.size.y, b.size.z);
  vis.transform.localScale    = Vector3.one * s;
  vis.transform.localPosition = new Vector3(0f, b.extents.y * s, 0f);
  ```
- **Rotation.** A mesh from the Pixal3D single-image template keeps the pose of the input
  view — a three-quarter view yields a tilted mesh. Set the `Model` child's
  `localRotation` until it stands upright, then compute the scale and offset above from the
  rotated bounds. The multi-view template returns an axis-aligned mesh and needs none.
- **Textures.** Base colour, normal and one packed occlusion-roughness-metallic image
  arrive at the size set in the graph. Unity's Max Size still applies on import — set it per
  texture as in step 2.
