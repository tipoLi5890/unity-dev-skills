# Editor scripts — entry points, arguments, the config

Four files in `resources/Editor/`. Copy all four into an `Editor` folder of the project:
`MixamoTextures.cs` serves every FBX route: an FBX from Blender's exporter or from Mixamo never
arrives with its metallic/smoothness map bound, and any other carrier is checked as
`reference/textures.md` says. They automate `reference/unity-import.md`
and `reference/textures.md`; nothing in them is character- or game-specific.

**The rule behind the split:** anything that depends only on the file being imported belongs in
the postprocessor; anything that depends on *another* asset already existing is a re-runnable
command. Every command **rebuilds from a clean state** rather than reconciling with what is there.

| File | Kind | Menu: `Tools/Unity Dev/Rigged Character/…` | From an eval | Writes |
|---|---|---|---|---|
| `CharacterImportSettings.cs` | `AssetPostprocessor`, plus a command | Reimport Character Folder | `CharacterImportSettings.Reimport(folder)`, `.Describe(folder)` | import settings of every FBX and texture in the folder |
| `CharacterAvatarLinker.cs` | command | Link Animation Avatars | `CharacterAvatarLinker.Link(folder)` | the Rig tab of every `<name>@<Clip>.fbx` |
| `CharacterAnimatorBuilder.cs` | command | Build Animator | `CharacterAnimatorBuilder.Build(folder)` | the controller and mask, deleted and created again |
| `MixamoTextures.cs` | command, any FBX route; needs URP | Apply Mixamo Textures | `MixamoTextures.Apply(folder)` | the URP Lit material; the mask only from a `*_MetallicSmoothness` map, a skipped raw metallic map named in `note` |

Order: drop the files in (the postprocessor applies on import) → Link Animation Avatars → Build
Animator → Apply Mixamo Textures → the prefab step below. A menu command acts on the folder
selected in the Project window, else the default folder. Each logs `[RIGGED-CHAR] {json}` and an
eval call returns the same string; `"ok": false` carries the reason. Build Animator and Apply Mixamo
Textures overwrite assets at the config's paths: confirm a path holds nothing hand-built before
the first run.

## The naming contract

| File | Read as |
|---|---|
| `runner.fbx` | the body: mesh and Avatar (Create From This Model). Its clips keep their exporter names. |
| `runner@RunFast.fbx` | animation only: no materials; Copy From Other Avatar → `runner.fbx` in the same folder; the text after `@` matched against `clipRules` |

The `@` — not a keyword anywhere in the name — marks an animation file, because a body named
`runner.fbx` contains `run`. Text after `@` that matches no rule becomes the clip name as it
stands, not looping, and the file still imports without materials (`runner@Wave.fbx` → clip
`Wave`).

A project moving from a keyword-detecting importer sees different results on the same files: a
body whose name contains run, walk, idle, jump, hurt, hit or fall is now a body (it was read as an
animation, with no materials and a looping clip), and `runner@Idle.fbx` gives `Idle` rather than
the first keyword found in the whole name. Reimport the folder and re-read the clip names.

## `character-pipeline.json`

Which file applies: the nearest `character-pipeline.json` at or above the asset's folder (that
folder is then the character folder); else `Assets/Editor/character-pipeline.json`, whose `folder`
names the character folder; else the defaults below with folder `Assets/Models/Character`. Edit
the file, then run Reimport Character Folder — a config change alone re-imports nothing.

```json
{
  "rig": "Generic",
  "maxTextureSize": 512,
  "targetTexPx": 0,
  "clipRules": [
    { "keyword": "runfast", "clip": "RunFast", "loop": true },
    { "keyword": "runslow", "clip": "RunSlow", "loop": true },
    { "keyword": "jump", "clip": "Jump", "loop": false },
    { "keyword": "hit", "clip": "Hurt", "loop": false },
    { "keyword": "swing", "clip": "GateLatchSwing", "loop": false }
  ],
  "material": "Assets/Materials/Runner.mat",
  "animator": {
    "controller": "Assets/Animations/Runner.controller", "mask": "Assets/Animations/RunnerUpperBody.mask",
    "slowClip": "RunSlow", "fastClip": "RunFast", "singleClip": "Run", "jumpClip": "Jump", "hurtClip": "Hurt",
    "grounded": "Grounded", "moveBlend": "MoveBlend", "moveSpeed": "MoveSpeed", "hurt": "Hurt"
  }
}
```

Leave out a top-level field to keep its default; when you set anything in `animator`, give the
whole block, as above.

| Field | Default | Meaning |
|---|---|---|
| `folder` | `Assets/Models/Character` | read only from the default-path file; a folder file is its own folder |
| `rig` | `Humanoid` | `Generic` for clips retargeted or keyed in Blender (`reference/unity-import.md` §1): no Avatar validation as human, no body-part mask on the Hurt layer. Keep `Humanoid` on the Mixamo route, or where the game needs the body-part mask or IK |
| `clipRules` | runfast, fastrun, runslow, slowrun, run, walk, idle (loop); jump, hurt, hit, fall (one-shot) | replaces the built-in list; first match wins, so a specific keyword precedes a general one |
| `maxTextureSize` | 0 | Max Size for every texture in the folder, rounded up to a power of two; 0 or absent leaves the importer's own value (2048 on a fresh importer), so a 1024 px map stays 1024. Set 512 for a 512 cap |
| `targetTexPx` | 0 | the `target_tex_px` of the `character` row of the 3D budgets table (`unity-3d-models` → `reference/budgets.md`); Max Size when `maxTextureSize` is 0; rounded up to a power of two |
| `material` | `Assets/Materials/Character.mat` | written by `MixamoTextures.cs` |
| `animator.controller`, `.mask` | `Assets/Animations/Character.controller`, `…/UpperBody.mask` | written by `CharacterAnimatorBuilder.cs` |
| `animator.slowClip`, `.fastClip`, `.singleClip`, `.jumpClip`, `.hurtClip` | `RunSlow`, `RunFast`, `Run`, `Jump`, `Hurt` | clip names the controller is built from |
| `animator.grounded`, `.moveBlend`, `.moveSpeed`, `.hurt` | `Grounded`, `MoveBlend`, `MoveSpeed`, `Hurt` | parameter names; the defaults are what `AnimatorBridge3D` (`unity-3d-controller`) writes. Rename here and on the bridge together; an empty name leaves the parameter, and what hangs off it, out |

Read what is in force before importing a new character: `CharacterImportSettings.Describe(folder)`.

## The prefab step — a snippet, not a file

Prefab layouts differ per game, so this stays a snippet to adapt. Three rules it encodes: keep the
gameplay root untouched (collider, `Rigidbody`, tag, layer, tuning) and fit by scaling the visual
child; nest the model under a `Rig` child; re-apply material, layer and Animator on every run, or
the character silently reverts to the white default.

```csharp
public static void SwapModel(string prefabPath, string modelPath, Material material,
                             RuntimeAnimatorController controller, float targetHeight)
{
    GameObject root = PrefabUtility.LoadPrefabContents(prefabPath);
    Transform old = root.transform.Find("Rig");
    if (old != null) Object.DestroyImmediate(old.gameObject);           // rebuild, never reconcile
    var rig = new GameObject("Rig").transform;
    rig.SetParent(root.transform, false);
    var model = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(modelPath));
    Bounds b = model.GetComponentInChildren<Renderer>().bounds;         // at identity, before parenting; a
    float fit = targetHeight / Mathf.Max(0.0001f, b.size.y);            // loose box: a visual fit, never a hit box
    model.transform.SetParent(rig, false);
    model.transform.localScale = Vector3.one * fit;
    model.transform.localPosition = new Vector3(0f, -b.min.y * fit, 0f); // soles on the root
    foreach (Renderer r in model.GetComponentsInChildren<Renderer>(true))
    {
        var slots = new Material[Mathf.Max(1, r.sharedMaterials.Length)]; // keep every submesh
        for (int i = 0; i < slots.Length; i++) slots[i] = material;
        r.sharedMaterials = slots;
    }
    foreach (Collider c in model.GetComponentsInChildren<Collider>(true)) Object.DestroyImmediate(c);
    foreach (Transform t in rig.GetComponentsInChildren<Transform>(true)) t.gameObject.layer = root.layer;
    if (!model.TryGetComponent(out Animator anim)) anim = model.AddComponent<Animator>();
    anim.applyRootMotion = false;
    anim.runtimeAnimatorController = controller;
    PrefabUtility.SaveAsPrefabAsset(root, prefabPath);
    PrefabUtility.UnloadPrefabContents(root);
}
```

## API cheat sheet

| Need | API |
|---|---|
| Force Humanoid on import | `ModelImporter.animationType = ModelImporterAnimationType.Human` |
| "Create From This Model" | `ModelImporter.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel` |
| "Copy From Other Avatar" | `avatarSetup = CopyFromOther` + `ModelImporter.sourceAvatar = <Avatar>` |
| Rename / loop clips | `ModelImporter.clipAnimations` — set `name`, `loopTime`, **and `loopPose`** |
| Keep a bone for a socket | `ModelImporter.optimizeGameObjects`, `ModelImporter.extraExposedTransformPaths` |
| Bones per vertex | `ModelImporter.skinWeights` (`Standard` = 4), `maxBonesPerVertex` for `Custom` |
| Fetch the Avatar (a sub-asset) | `AssetDatabase.LoadAllAssetsAtPath(modelPath)` → first `Avatar` |
| Validate a rig | `avatar.isHuman && avatar.isValid` |
| Create a controller | `AnimatorController.CreateAnimatorControllerAtPath(path)` |
| Blend tree as sub-asset | `new BlendTree { hideFlags = HideFlags.HideInHierarchy }` + `AssetDatabase.AddObjectToAsset(tree, controller)` |
| Humanoid mask | `AvatarMask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.…, bool)` |
| Extra layer | `controller.AddLayer(new AnimatorControllerLayer { blendingMode = Override, avatarMask = … })` |
| Normal-map import | `TextureImporter.textureType = TextureImporterType.NormalMap` |
| Data map import | `sRGBTexture = false`, `alphaSource = FromInput`, `alphaIsTransparency = false` |
| URP map keywords | `EnableKeyword("_NORMALMAP")`, `EnableKeyword("_METALLICSPECGLOSSMAP")` |
| Edit a prefab asset | `PrefabUtility.LoadPrefabContents` → mutate → `SaveAsPrefabAsset` → `UnloadPrefabContents` |
| Nest a model prefab | `(GameObject)PrefabUtility.InstantiatePrefab(model)` |
