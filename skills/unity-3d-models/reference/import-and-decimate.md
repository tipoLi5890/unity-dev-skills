# From a source file to an imported asset

## Prerequisites

- **glTFast** importer: `Window ▸ Package Manager ▸ + ▸ Add package by name ▸
  `com.unity.cloud.gltfast``. Then `.glb`/`.gltf` under `Assets/` import as model
  prefabs (URP materials auto-created). FBX imports natively (no package).
- **gltf-transform CLI** (via `npx`; needs `node` on PATH) for
  inspect/optimize. **In zsh, don't stuff the command in a variable** (`$CLI foo` won't
  word-split) — call `npx --yes @gltf-transform/cli …` directly.
- Assumes a URP project with models under `Assets/Models/` — substitute your own
  path in the commands below.

## Pipeline (do these in order)

### 1. Inspect — see how bad it is
```bash
npx --yes @gltf-transform/cli inspect Assets/Models/<file>.glb 2>&1 | grep -A4 MESHES
```
Look at `glPrimitives` (triangles). AI models: expect 6–7 figures.

### 2. Optimize — decimate mesh (the big win) + shrink textures
The **mesh** is almost the entire file/runtime cost, so `simplify` is what
matters. Decimate from the **original** (not an already-decimated copy) for best
quality:
```bash
# --ratio = target fraction of ORIGINAL triangles; --error = max shape error (bbox fraction)
npx --yes @gltf-transform/cli simplify ORIGINAL.glb Assets/Models/<file>.glb --ratio 0.0025 --error 0.05
```
Textures (secondary): compress/resize in Unity (select the model's textures →
Max Size 512, compression on) or `npx … @gltf-transform/cli optimize in out
--texture-compress webp --texture-size 512`.

**Triangle budgets** (a runner; scale for your game):

| Asset | Budget |
|-------|--------|
| Pickup (coin/gem) | 0.5–2k |
| Small obstacle (rock/log) | 2–5k |
| Character / hero | 3–10k |
| Environment prop | 1–5k |

Verify: `inspect` again — confirm the new triangle count.

### 3. Stage into `Assets/Models/` — glTFast imports it
Overwriting the same path keeps the asset GUID, so wired prefabs update in place
(but re-run the swap in step 5 if the mesh hierarchy changed).

### 4. Import — focus Unity (or right-click the `.glb` → Reimport)
It becomes an expandable model with mesh + URP materials.

### 5. Wire into a prefab — Editor script, layer-aware
Swap a sprite/placeholder prefab's visual to the model **via Unity's API**
(robust vs. hand-edited YAML). Pattern — write a one-off Editor script under
`Assets/Scripts/Editor/` (e.g. `SwapModelIntoPrefab.cs`):
```csharp
var model = AssetDatabase.LoadAssetAtPath<GameObject>("Assets/Models/x.glb");
var root  = PrefabUtility.LoadPrefabContents(prefabPath);
DestroyImmediate(root.GetComponent<SpriteRenderer>());   // drop the 2.5D visual
DestroyImmediate(root.GetComponent<Billboard>());
var vis = (GameObject)PrefabUtility.InstantiatePrefab(model);
vis.name = "Model"; vis.transform.SetParent(root.transform, false);
SetLayer(vis, root.layer);                                // ← critical, see below
PrefabUtility.SaveAsPrefabAsset(root, prefabPath);
PrefabUtility.UnloadPrefabContents(root);
```
Keep the root's collider + tag + gameplay scripts; the model is just the visual.
