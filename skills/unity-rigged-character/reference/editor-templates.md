# Editor automation templates

Generalised Unity Editor code for stages 4–5 of the pipeline in `SKILL.md`:
`reference/unity-import.md` §8–§9 and `reference/textures.md` §10.
Copy each block to the stated path under `Assets/Scripts/Editor/`, adjust the folder
constant, and add rows to `ClipRules` for whatever animations the project uses.
Nothing here is character- or game-specific.

## Why this is five files and not one

| File | Kind | Why it must be this kind |
|---|---|---|
| `CharacterImportSettings.cs` | `AssetPostprocessor` | Import settings must apply the moment a file is dropped in, including on a fresh clone. Nobody should have to remember the Rig-tab dance. |
| `CharacterAvatarLinker.cs` | menu command | Cross-asset: an animation needs the *mesh's* Avatar. **Import order is not guaranteed** — a postprocessor can run before that Avatar exists, and fails silently. A menu command is deterministic and re-runnable. |
| `BuildCharacterAnimator.cs` | menu command | Generating the controller in code makes it reproducible and survives a re-export: delete the asset, re-run. |
| `CharacterTextures.cs` | menu command | The material is rebuilt from maps that arrive separately from the mesh, on their own schedule. |
| `CharacterToPrefab.cs` | menu command | Prefab surgery via the API, not hand-edited YAML. Re-runs after every re-export. |

**The rule behind the split:** anything that depends only on the file being imported
belongs in the postprocessor; anything that depends on *another* asset already existing
must be a re-runnable command. And every command **rebuilds from a clean state** rather
than reconciling with what is already there.

Menu path convention below: `Tools ▸ Art ▸ Character → …`, run in pipeline order.

---

## `CharacterImportSettings.cs` — import postprocessor

Fixes the three things Mixamo does that break the Animator: identical clip names, one
FBX per animation, looping off by default. Also routes texture maps to the right
importer type.

```csharp
#if UNITY_EDITOR
using System.IO;
using UnityEditor;
using UnityEngine;

/// <summary>
/// Makes character FBX drops under <see cref="CharacterDir"/> game-ready on import.
///
/// File naming contract — the only thing to get right by hand:
///   • the mesh export ("With Skin") contains NO clip keyword   e.g. <character>.fbx
///   • animation exports contain a clip keyword                 e.g. <character>@Running.fbx
/// </summary>
public class CharacterImportSettings : AssetPostprocessor
{
    public const string CharacterDir = "Assets/Models/Character/";

    /// <summary>Max texture size for character maps. One character on screen, but mobile.</summary>
    const int MaxTextureSize = 512;

    /// <summary>
    /// File-name keyword → clip name + whether it loops. Locomotion loops; one-shot
    /// reactions don't. Add a row here rather than special-casing anywhere else.
    /// </summary>
    public static readonly (string keyword, string clipName, bool loop)[] ClipRules =
    {
        // ORDER MATTERS — first match wins, so specific keywords must precede general
        // ones. "runfast" has to beat "run", or both fast and slow runs end up named
        // "Run" and the Animator picks whichever the asset database returns first.
        ("runfast",  "RunFast", true),
        ("fastrun",  "RunFast", true),
        ("runslow",  "RunSlow", true),
        ("slowrun",  "RunSlow", true),
        ("run",      "Run",     true),
        ("walk",     "Walk",    true),
        ("idle",     "Idle",    true),
        ("jump",     "Jump",    false),
        ("hurt",     "Hurt",    false),
        ("hit",      "Hurt",    false),   // Mixamo calls it "Hit Reaction"
        ("fall",     "Fall",    false),
    };

    public static bool IsCharacterModel(string path) =>
        path.StartsWith(CharacterDir) && (path.EndsWith(".fbx") || path.EndsWith(".FBX"));

    /// <summary>The mesh export is the one with no clip keyword in its name.</summary>
    public static bool IsSkinnedModel(string path) =>
        MatchRule(Path.GetFileNameWithoutExtension(path).ToLowerInvariant()) == -1;

    static int MatchRule(string lowerFileName)
    {
        for (int i = 0; i < ClipRules.Length; i++)
            if (lowerFileName.Contains(ClipRules[i].keyword)) return i;
        return -1;
    }

    void OnPreprocessModel()
    {
        if (!IsCharacterModel(assetPath)) return;
        var importer = (ModelImporter)assetImporter;

        // Humanoid is the whole reason characters route through FBX instead of glTFast:
        // Avatar retargeting AND the humanoid AvatarMask that lets a reaction play on the
        // upper body while the legs keep moving.
        importer.animationType = ModelImporterAnimationType.Human;

        if (IsSkinnedModel(assetPath))
            importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
        else
            // Animation-only: no materials to import. Its Avatar is linked by the menu
            // command — import order makes doing it here unreliable.
            importer.materialImportMode = ModelImporterMaterialImportMode.None;
    }

    void OnPreprocessAnimation()
    {
        if (!IsCharacterModel(assetPath)) return;
        var importer = (ModelImporter)assetImporter;
        var clips = importer.defaultClipAnimations;
        if (clips == null || clips.Length == 0) return;

        int rule = MatchRule(Path.GetFileNameWithoutExtension(assetPath).ToLowerInvariant());

        for (int i = 0; i < clips.Length; i++)
        {
            if (rule >= 0)
            {
                // Rename off "mixamo.com" so clips can be found by name; suffix extras if a
                // single file somehow holds several takes.
                clips[i].name = clips.Length == 1 ? ClipRules[rule].clipName
                                                  : $"{ClipRules[rule].clipName}_{i}";
                clips[i].loopTime = ClipRules[rule].loop;
                // loopPose forces the first and last frames to match. Run cycles are short
                // (~17 frames at 30 fps) and a one-frame mismatch reads as a visible hitch
                // twice a second — felt as "something's off" without being seen.
                clips[i].loopPose = ClipRules[rule].loop;
            }
            else clips[i].loopTime = false;
        }
        importer.clipAnimations = clips;
    }

    void OnPreprocessTexture()
    {
        if (!assetPath.StartsWith(CharacterDir)) return;
        var importer = (TextureImporter)assetImporter;

        importer.maxTextureSize     = MaxTextureSize;
        importer.textureCompression = TextureImporterCompression.Compressed;

        // Only the colour map is colour. The others carry DATA, and importing them as sRGB
        // silently gamma-warps every value — the classic "lighting looks vaguely wrong and
        // nobody can say why". Matched on file name so any character's maps work the same.
        string file = Path.GetFileNameWithoutExtension(assetPath).ToLowerInvariant();

        if (file.Contains("normal"))
        {
            // NormalMap type also unpacks the encoding; leave it Default and the surface
            // normals point in entirely wrong directions.
            importer.textureType = TextureImporterType.NormalMap;
        }
        else if (file.Contains("metallic") || file.Contains("smoothness") || file.Contains("roughness"))
        {
            importer.textureType = TextureImporterType.Default;
            importer.sRGBTexture = false;                                 // linear: raw values
            importer.alphaSource = TextureImporterAlphaSource.FromInput;  // smoothness lives in A
            importer.alphaIsTransparency = false;                         // material property, not opacity
        }
    }
}
#endif
```

---

## `CharacterAvatarLinker.cs` — the Copy From Other Avatar step

The API equivalent of opening each animation's Rig tab and setting **Copy From Other
Avatar**. Skip it and every animation file builds its own Avatar, none of them retarget,
and the character **T-poses in place while the Animator reports no problem**.

```csharp
#if UNITY_EDITOR
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

public static class CharacterAvatarLinker
{
    [MenuItem("Tools/Art/Character → Link Animation Avatars")]
    public static void LinkAll()
    {
        string dir = CharacterImportSettings.CharacterDir;
        if (!Directory.Exists(dir))
        {
            Debug.LogError($"CharacterAvatarLinker: {dir} doesn't exist. Create it and drop " +
                           "the Mixamo FBX exports in first.");
            return;
        }

        var all = new List<string>(Directory.GetFiles(dir, "*.fbx", SearchOption.AllDirectories));
        if (all.Count == 0)
        {
            Debug.LogError($"CharacterAvatarLinker: no .fbx under {dir}. Export from Mixamo as " +
                           "'FBX for Unity' (In Place) and drop the files in.");
            return;
        }

        string skinnedPath = all.Find(p => CharacterImportSettings.IsSkinnedModel(p.Replace('\\', '/')));
        if (string.IsNullOrEmpty(skinnedPath))
        {
            Debug.LogError("CharacterAvatarLinker: couldn't find the 'With Skin' export — every FBX " +
                           "matched an animation keyword. One file must carry the mesh and have NO " +
                           "clip keyword in its name.");
            return;
        }
        skinnedPath = skinnedPath.Replace('\\', '/');

        Avatar avatar = FindAvatar(skinnedPath);
        if (avatar == null)
        {
            Debug.LogError($"CharacterAvatarLinker: {skinnedPath} produced no Avatar. The auto-rig " +
                           "likely didn't map onto Unity's Humanoid skeleton — open the file's Rig " +
                           "tab, set Animation Type to Humanoid and press Configure to see which " +
                           "bones are missing.");
            return;
        }
        if (!avatar.isHuman || !avatar.isValid)
        {
            Debug.LogError($"CharacterAvatarLinker: Avatar on {skinnedPath} is not a valid Humanoid " +
                           $"(isHuman={avatar.isHuman}, isValid={avatar.isValid}). A Mixamo auto-rig " +
                           "should map cleanly; a hand-named skeleton may not.");
            return;
        }

        int linked = 0;
        foreach (string raw in all)
        {
            string path = raw.Replace('\\', '/');
            if (path == skinnedPath) continue;
            if (!(AssetImporter.GetAtPath(path) is ModelImporter importer)) continue;

            importer.animationType = ModelImporterAnimationType.Human;
            importer.avatarSetup   = ModelImporterAvatarSetup.CopyFromOther;
            importer.sourceAvatar  = avatar;
            importer.SaveAndReimport();
            linked++;
        }

        Debug.Log($"CharacterAvatarLinker: Avatar from '{Path.GetFileName(skinnedPath)}' linked to " +
                  $"{linked} animation file(s).");
    }

    /// <summary>The Avatar is a sub-asset of the imported model, not a separate file.</summary>
    static Avatar FindAvatar(string modelPath)
    {
        foreach (var asset in AssetDatabase.LoadAllAssetsAtPath(modelPath))
            if (asset is Avatar avatar) return avatar;
        return null;
    }
}
#endif
```

---

## `BuildCharacterAnimator.cs` — controller, blend tree, masked layer

Built in code so it is reproducible: delete the asset, re-run, done. Two layers only —
a locomotion base layer, and an override layer masked to the upper body.

```csharp
#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

public static class BuildCharacterAnimator
{
    public const string AnimationsDir  = "Assets/Animations";
    public const string ControllerPath = AnimationsDir + "/Character.controller";
    public const string MaskPath       = AnimationsDir + "/UpperBody.mask";

    [MenuItem("Tools/Art/Character → Build Animator")]
    public static void Build()
    {
        // Two locomotion clips unlock a blend tree, which beats time-scaling one clip: a
        // sprint slowed down still swings its arms like a sprint, and a jog sped up looks
        // like cartoon fast-forward. Blending changes the MOTION, not just its rate.
        var moveFast = FindClip("RunFast");
        var moveSlow = FindClip("RunSlow");
        var move     = FindClip("Run");
        var jump     = FindClip("Jump");
        var hurt     = FindClip("Hurt");

        if (moveFast == null && moveSlow == null && move == null)
        {
            Debug.LogError("BuildCharacterAnimator: no locomotion clip under " +
                           $"{CharacterImportSettings.CharacterDir}. Drop a Mixamo run export in, " +
                           "then run Character → Link Animation Avatars first.");
            return;
        }

        if (!AssetDatabase.IsValidFolder(AnimationsDir))
            AssetDatabase.CreateFolder("Assets", "Animations");

        // Re-runnable: start from a clean asset rather than reconciling an existing graph.
        AssetDatabase.DeleteAsset(ControllerPath);
        var controller = AnimatorController.CreateAnimatorControllerAtPath(ControllerPath);

        controller.AddParameter("Grounded",  AnimatorControllerParameterType.Bool);
        controller.AddParameter("MoveBlend", AnimatorControllerParameterType.Float);  // 0=slow, 1=fast
        controller.AddParameter("MoveSpeed", AnimatorControllerParameterType.Float);  // playback rate
        controller.AddParameter("Hurt",      AnimatorControllerParameterType.Trigger);

        BuildBaseLayer(controller, moveFast, moveSlow, move, jump);
        if (hurt != null) BuildHurtLayer(controller, hurt);

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
    }

    static void BuildBaseLayer(AnimatorController controller, AnimationClip fast,
                               AnimationClip slow, AnimationClip single, AnimationClip jump)
    {
        var machine = controller.layers[0].stateMachine;
        var moveState = machine.AddState("Move");
        machine.defaultState = moveState;

        if (fast != null && slow != null)
        {
            // 1D blend on MoveBlend (0 = slow, 1 = fast). Feed it the current speed
            // normalised between the min and max run speeds, so the GAIT changes as the
            // game ramps up instead of one clip just playing faster.
            var tree = new BlendTree
            {
                name           = "MoveBlend",
                blendType      = BlendTreeType.Simple1D,
                blendParameter = "MoveBlend",
                hideFlags      = HideFlags.HideInHierarchy   // sub-asset of the controller
            };
            AssetDatabase.AddObjectToAsset(tree, controller);
            tree.AddChild(slow, 0f);
            tree.AddChild(fast, 1f);
            moveState.motion = tree;
        }
        else
        {
            // Only one clip: scale playback rate so the feet roughly keep up with the ground.
            moveState.motion = fast ?? slow ?? single;
            moveState.speedParameterActive = true;
            moveState.speedParameter = "MoveSpeed";
        }

        if (jump == null) return;
        var jumpState = machine.AddState("Jump");
        jumpState.motion = jump;

        // No exit time on either transition: leaving the ground and landing are EVENTS, and
        // waiting for a clip to finish would delay the pose by up to a full stride.
        var toJump = moveState.AddTransition(jumpState);
        toJump.AddCondition(AnimatorConditionMode.IfNot, 0f, "Grounded");
        toJump.hasExitTime = false;
        toJump.duration    = 0.08f;

        var toMove = jumpState.AddTransition(moveState);
        toMove.AddCondition(AnimatorConditionMode.If, 0f, "Grounded");
        toMove.hasExitTime = false;
        toMove.duration    = 0.10f;
    }

    static void BuildHurtLayer(AnimatorController controller, AnimationClip hurt)
    {
        var machine = new AnimatorStateMachine
        {
            name = "Hurt",
            hideFlags = HideFlags.HideInHierarchy   // sub-asset; keeps the .controller tidy
        };
        AssetDatabase.AddObjectToAsset(machine, controller);

        // An empty default state means the layer contributes nothing until a hit lands.
        var idle  = machine.AddState("None");
        var state = machine.AddState("Hurt");
        state.motion = hurt;
        machine.defaultState = idle;

        var toHurt = idle.AddTransition(state);
        toHurt.AddCondition(AnimatorConditionMode.If, 0f, "Hurt");
        toHurt.hasExitTime = false;
        toHurt.duration    = 0.05f;

        // Return automatically near the end of the reaction — nothing has to clear the trigger.
        var back = state.AddTransition(idle);
        back.hasExitTime = true;
        back.exitTime    = 0.85f;
        back.duration    = 0.15f;

        controller.AddLayer(new AnimatorControllerLayer
        {
            name          = "Hurt",
            stateMachine  = machine,
            defaultWeight = 1f,
            blendingMode  = AnimatorLayerBlendingMode.Override,
            avatarMask    = CreateUpperBodyMask()
        });
    }

    /// <summary>
    /// Upper body only. Legs and root stay off so locomotion keeps driving them — exactly the
    /// trick Generic rigs can't do and Humanoid can, because the mask is expressed in abstract
    /// body parts rather than bone names.
    /// </summary>
    static AvatarMask CreateUpperBodyMask()
    {
        var mask = new AvatarMask();
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.Root,         false);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.Body,         true);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.Head,         true);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.LeftArm,      true);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.RightArm,     true);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.LeftFingers,  true);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.RightFingers, true);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.LeftLeg,      false);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.RightLeg,     false);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.LeftFootIK,   false);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.RightFootIK,  false);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.LeftHandIK,   false);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.RightHandIK,  false);

        AssetDatabase.DeleteAsset(MaskPath);
        AssetDatabase.CreateAsset(mask, MaskPath);
        return mask;
    }

    /// <summary>
    /// Clips live as sub-assets of their FBX; the postprocessor has already renamed them off
    /// Mixamo's useless "mixamo.com" default.
    /// </summary>
    static AnimationClip FindClip(string clipName)
    {
        foreach (string guid in AssetDatabase.FindAssets("t:Model",
                     new[] { CharacterImportSettings.CharacterDir.TrimEnd('/') }))
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            foreach (var asset in AssetDatabase.LoadAllAssetsAtPath(path))
                if (asset is AnimationClip clip && !clip.name.StartsWith("__preview") &&
                    clip.name == clipName)
                    return clip;
        }
        return null;
    }
}
#endif
```

**Runtime side (a small bridge MonoBehaviour, not shown):** each frame set `Grounded`,
set `MoveBlend` to `Mathf.InverseLerp(minSpeed, maxSpeed, currentSpeed)`, and fire the
`Hurt` trigger on a hit. Keep it a thin adapter — the controller shape is authored here.

---

## `CharacterTextures.cs` — rebuild the URP material

Maps are matched by file-name keyword, not hardcoded names, so any character's export
works. `SetTexture` alone is not enough — see the keyword calls.

```csharp
#if UNITY_EDITOR
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

public static class CharacterTextures
{
    public const string MaterialPath = "Assets/Materials/Character.mat";

    [MenuItem("Tools/Art/Character → Apply Textures")]
    public static void ApplyMenu() => BuildMaterial();

    public static Material BuildMaterial()
    {
        Texture2D baseMap = FindMap("color", "basecolor", "albedo", "diffuse");
        Texture2D normal  = FindMap("normal");
        Texture2D mask    = FindMap("metallicsmoothness", "metallic");

        if (baseMap == null)
        {
            Debug.LogError("CharacterTextures: no colour map under " +
                           $"{CharacterImportSettings.CharacterDir} — expected a file whose name " +
                           "contains \"color\", \"basecolor\", \"albedo\" or \"diffuse\". Extract " +
                           "them from the ORIGINAL pre-Mixamo export with fbx_textures.py.");
            return null;
        }

        var shader = Shader.Find("Universal Render Pipeline/Lit");
        if (shader == null) { Debug.LogError("CharacterTextures: URP Lit shader not found."); return null; }

        var material = AssetDatabase.LoadAssetAtPath<Material>(MaterialPath);
        if (material == null)
        {
            if (!AssetDatabase.IsValidFolder("Assets/Materials"))
                AssetDatabase.CreateFolder("Assets", "Materials");
            material = new Material(shader);
            AssetDatabase.CreateAsset(material, MaterialPath);
        }
        material.shader = shader;

        material.SetTexture("_BaseMap", baseMap);
        // The tint MULTIPLIES the map, so anything but white darkens the character for nothing.
        material.SetColor("_BaseColor", Color.white);

        if (normal != null)
        {
            material.SetTexture("_BumpMap", normal);
            // Assigning the texture is NOT enough. URP compiles the normal-map path behind this
            // keyword — without it the map loads, costs memory, and is silently ignored, and you
            // end up debugging the texture while the shader never asked for it.
            material.EnableKeyword("_NORMALMAP");
        }
        else material.DisableKeyword("_NORMALMAP");

        if (mask != null)
        {
            material.SetTexture("_MetallicGlossMap", mask);
            material.EnableKeyword("_METALLICSPECGLOSSMAP");
            // With a map bound, metallic comes straight from RGB and smoothness is MULTIPLIED by
            // _Smoothness — so 1.0 means "use the map as authored".
            material.SetFloat("_Metallic", 1f);
            material.SetFloat("_Smoothness", 1f);
        }
        else
        {
            material.DisableKeyword("_METALLICSPECGLOSSMAP");
            // Cloth and skin: no metal, low gloss. Stops a stylised character reading as wet vinyl.
            material.SetFloat("_Metallic", 0f);
            material.SetFloat("_Smoothness", 0.25f);
        }

        EditorUtility.SetDirty(material);
        AssetDatabase.SaveAssets();
        return material;
    }

    /// <summary>
    /// First texture under the character folder matching a keyword. Keywords are tried in order,
    /// so pass the most specific first — "metallicsmoothness" must beat a stray "metallic".
    /// </summary>
    static Texture2D FindMap(params string[] keywords)
    {
        var paths = new List<string>();
        foreach (string guid in AssetDatabase.FindAssets("t:Texture2D",
                     new[] { CharacterImportSettings.CharacterDir.TrimEnd('/') }))
            paths.Add(AssetDatabase.GUIDToAssetPath(guid));

        foreach (string keyword in keywords)
            foreach (string path in paths)
                if (Path.GetFileNameWithoutExtension(path).ToLowerInvariant().Contains(keyword))
                    return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
        return null;
    }
}
#endif
```

---

## `CharacterToPrefab.cs` — swap the model into the gameplay prefab

Prefab surgery through `PrefabUtility`, never by hand-editing YAML. Re-runnable.

Three rules this encodes:

1. **Keep the gameplay root untouched** — collider, Rigidbody, tag, layer, and every
   tuning number. Do **not** resize the character by editing a gameplay scale field:
   other systems commonly derive positions from it, so "making the character fit" would
   silently move unrelated things. Fit by scaling the visual container instead.
2. **Nest under a container that cancels root transforms.** If the gameplay root is
   scaled or yawed for its own reasons, a model parented straight to it runs sideways at
   the wrong size. A `Rig` child that inverts those lets everything inside be authored in
   plain upright world units.
3. **Re-apply the material every run**, because each run re-instantiates the model —
   otherwise the character silently reverts to Unity's white default.

```csharp
#if UNITY_EDITOR
using System.IO;
using UnityEditor;
using UnityEngine;

public static class CharacterToPrefab
{
    const string PrefabPath = "Assets/Prefabs/Character.prefab";
    const string RigName    = "Rig";
    const string ModelName  = "Model";

    /// <summary>Visual height head-to-toe in world units. Deliberately taller than the collider —
    /// head and shoulders reading above the hit box is normal and looks right.</summary>
    const float TargetHeight = 1.0f;

    [MenuItem("Tools/Art/Character → 3D Model")]
    public static void Swap()
    {
        string modelPath = FindSkinnedModel();
        if (modelPath == null) return;

        var model = AssetDatabase.LoadAssetAtPath<GameObject>(modelPath);
        var root  = PrefabUtility.LoadPrefabContents(PrefabPath);
        if (model == null || root == null) { Debug.LogError("CharacterToPrefab: model or prefab missing."); return; }

        // Drop the placeholder's visuals. The collider stays — it IS the hit box.
        var meshFilter   = root.GetComponent<MeshFilter>();
        var meshRenderer = root.GetComponent<MeshRenderer>();
        if (meshFilter   != null) Object.DestroyImmediate(meshFilter);
        if (meshRenderer != null) Object.DestroyImmediate(meshRenderer);

        // Re-runnable: rebuild from scratch instead of reconciling whatever is there.
        var existing = root.transform.Find(RigName);
        if (existing != null) Object.DestroyImmediate(existing.gameObject);

        var rig = new GameObject(RigName);
        rig.transform.SetParent(root.transform, false);
        rig.transform.localPosition = Vector3.zero;
        rig.transform.localRotation = Quaternion.identity;
        // Cancel any gameplay scale on the root (see rule 2). Mirror whatever the runtime does,
        // so the Scene view preview isn't misleading.
        rig.transform.localScale = Vector3.one;

        var visual = BuildModel(model, rig.transform);
        ApplyMaterial(visual);

        // Visual-only children must not keep colliders: they share the root's Rigidbody and merge
        // into one compound collider, so the character collides through its own accessories.
        StripColliders(rig);

        // Imported objects land on layer 0 — if the camera culls it, the model shows in the Scene
        // view and is invisible in the Game view.
        SetLayerRecursive(rig, root.layer);

        WireAnimator(visual);

        PrefabUtility.SaveAsPrefabAsset(root, PrefabPath);
        PrefabUtility.UnloadPrefabContents(root);
    }

    /// <summary>
    /// Nests the model and fits it to <see cref="TargetHeight"/>. Measurement happens BEFORE
    /// parenting, while the instance is still at identity — measuring afterwards folds the
    /// parents' scales into the numbers.
    /// </summary>
    static GameObject BuildModel(GameObject model, Transform rig)
    {
        var visual = (GameObject)PrefabUtility.InstantiatePrefab(model);
        visual.name = ModelName;
        visual.transform.position   = Vector3.zero;
        visual.transform.rotation   = Quaternion.identity;
        visual.transform.localScale = Vector3.one;

        Bounds? measured = RendererBounds(visual);
        float fit = 1f, feetOffset = 0f;
        if (measured.HasValue && measured.Value.size.y > 0.0001f)
        {
            fit = TargetHeight / measured.Value.size.y;
            // Where the soles sit relative to the model's own pivot after fitting. Bottom-Center
            // pivots give ~0; centre pivots give -height/2. Handling both means a re-export with a
            // different pivot convention doesn't leave the character sunk into the ground.
            feetOffset = measured.Value.min.y * fit;
        }

        visual.transform.SetParent(rig, false);
        visual.transform.localScale    = Vector3.one * fit;
        visual.transform.localPosition = new Vector3(0f, -feetOffset, 0f);  // + any collider offset
        visual.transform.localRotation = Quaternion.identity;
        return visual;
    }

    static void ApplyMaterial(GameObject visual)
    {
        var material = AssetDatabase.LoadAssetAtPath<Material>(CharacterTextures.MaterialPath);
        if (material == null)
        {
            Debug.LogWarning("CharacterToPrefab: no character material yet — the model stays white. " +
                             "Run Character → Apply Textures, then re-run this.");
            return;
        }
        foreach (var renderer in visual.GetComponentsInChildren<Renderer>(true))
        {
            // Preserve the submesh count — a shorter array drops submeshes entirely.
            var slots = new Material[Mathf.Max(1, renderer.sharedMaterials.Length)];
            for (int i = 0; i < slots.Length; i++) slots[i] = material;
            renderer.sharedMaterials = slots;
        }
    }

    static void WireAnimator(GameObject visual)
    {
        var animator = visual.GetComponent<Animator>() ?? visual.AddComponent<Animator>();
        // Root motion OFF: the controller owns position, and a clip that also translated would
        // fight it every frame. The Mixamo exports are "In Place" too — belt and braces, because
        // either one alone is easy to forget.
        animator.applyRootMotion = false;

        var controller = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(
            BuildCharacterAnimator.ControllerPath);
        if (controller != null) animator.runtimeAnimatorController = controller;
    }

    static string FindSkinnedModel()
    {
        string dir = CharacterImportSettings.CharacterDir;
        if (!Directory.Exists(dir)) { Debug.LogError($"CharacterToPrefab: {dir} doesn't exist."); return null; }
        foreach (string raw in Directory.GetFiles(dir, "*.fbx", SearchOption.AllDirectories))
        {
            string path = raw.Replace('\\', '/');
            if (CharacterImportSettings.IsSkinnedModel(path)) return path;
        }
        Debug.LogError("CharacterToPrefab: every FBX matched an animation keyword. One file must " +
                       "carry the mesh and have no clip keyword in its name.");
        return null;
    }

    // ---- shared helpers; extract to their own file once a second prefab builder needs them ----

    static void SetLayerRecursive(GameObject go, int layer)
    {
        go.layer = layer;
        foreach (Transform child in go.transform) SetLayerRecursive(child.gameObject, layer);
    }

    /// <summary>Combined world bounds of every renderer, or null if there are none. Lets the model
    /// be auto-fitted instead of hardcoding a scale that only suits one export — AI models come out
    /// at arbitrary scales, so a hardcoded number breaks on the next re-export.</summary>
    static Bounds? RendererBounds(GameObject go)
    {
        var renderers = go.GetComponentsInChildren<Renderer>(true);
        if (renderers.Length == 0) return null;
        Bounds bounds = renderers[0].bounds;
        for (int i = 1; i < renderers.Length; i++) bounds.Encapsulate(renderers[i].bounds);
        return bounds;
    }

    static void StripColliders(GameObject go)
    {
        foreach (var collider in go.GetComponentsInChildren<Collider>(true))
            Object.DestroyImmediate(collider);
    }
}
#endif
```

---

## API cheat sheet

| Need | API |
|---|---|
| Force Humanoid on import | `ModelImporter.animationType = ModelImporterAnimationType.Human` |
| "Create From This Model" | `ModelImporter.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel` |
| "Copy From Other Avatar" | `avatarSetup = CopyFromOther` + `ModelImporter.sourceAvatar = <Avatar>` |
| Rename / loop clips | `ModelImporter.clipAnimations` — set `name`, `loopTime`, **and `loopPose`** |
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
