// SharedSkeletonClipImporter — import rules for characters fitted to a clip pack's skeleton, and
// for that pack's clip files played unchanged on them (Generic, no retargeting anywhere).
//
// Drop into an Editor folder and edit the five constants below. Scoped to two folders only, so it
// never touches another FBX; keep CharacterImportSettings.cs (character-pipeline.json) away from
// these two folders, or the two postprocessors will fight over the same files.
//
//   CharacterDir  fitted character FBX files: Generic, Avatar from this model, no root node
//                 (the root bone's translation stays in the clips), no animation, no materials,
//                 Standard skin weights (4 bones; the fit route's skin stage gates <= 4).
//   ClipDir       the pack's clip FBX files, unedited on disk: Generic, Optimal compression,
//                 no loop (the game sets time), then after import:
//                   RemapRoot              root-node aliases renamed to RootNode in every binding
//                   StripNonRootPositions  position and scale curves removed except on RootBonePath
//                   BakeNodeDefaults       a bone with no rotation curve gets the file's own default
//                                          rotation as a constant curve
// Why each step exists, with the measurements: unity-rigged-character reference/
// shared-skeleton-generic.md. Bump GetVersion after changing a rule so Unity reimports.
using System;
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;

public sealed class SharedSkeletonClipImporter : AssetPostprocessor
{
    // ---- edit these for your project -------------------------------------------------------
    public const string CharacterDir = "Assets/Art/Characters/";
    public const string ClipDir = "Assets/Art/Animations/Pack/";
    /// <summary>The clip files' root node (the FBX null above the root bone), as most clips name it.</summary>
    public const string RootNode = "PackRoot";
    /// <summary>Other names the same node carries in some clips of the pack.</summary>
    public static readonly string[] RootAliases = { "PackRoot_TakeB", "PackRoot_TakeC" };
    /// <summary>The only bone allowed to translate: the root bone under RootNode.</summary>
    public const string RootBonePath = RootNode + "/Hips";
    // -----------------------------------------------------------------------------------------

    public override uint GetVersion() => 1;

    static bool IsFbx(string path) => path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase);
    public static bool IsCharacter(string path) => path.StartsWith(CharacterDir, StringComparison.Ordinal) && IsFbx(path);
    public static bool IsClip(string path) => path.StartsWith(ClipDir, StringComparison.Ordinal) && IsFbx(path);

    void OnPreprocessModel()
    {
        bool character = IsCharacter(assetPath), clip = IsClip(assetPath);
        if (!character && !clip) return;
        var mi = (ModelImporter)assetImporter;
        mi.importCameras = false;
        mi.importLights = false;
        mi.importVisibility = false;
        mi.importBlendShapes = false;
        mi.isReadable = false;
        mi.useFileScale = true;
        mi.globalScale = 1f;
        mi.animationType = ModelImporterAnimationType.Generic;
        mi.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;  // Generic binds by path
        mi.motionNodeName = "";
        mi.optimizeGameObjects = false;     // feet, hands and sockets stay readable for IK and tests
        mi.materialImportMode = ModelImporterMaterialImportMode.None;
        mi.importAnimation = clip;
        if (character)
        {
            mi.importNormals = ModelImporterNormals.Import;
            mi.importTangents = ModelImporterTangents.CalculateMikk;
            mi.meshCompression = ModelImporterMeshCompression.Off;
            mi.skinWeights = ModelImporterSkinWeights.Standard;
        }
        else
        {
            // the demo body shipped inside each clip file is never referenced, so never built
            mi.meshCompression = ModelImporterMeshCompression.High;
            mi.animationCompression = ModelImporterAnimationCompression.Optimal;
            mi.resampleCurves = true;
        }
    }

    void OnPreprocessAnimation()
    {
        if (!IsClip(assetPath)) return;
        var mi = (ModelImporter)assetImporter;
        var clips = mi.defaultClipAnimations;
        if (clips == null || clips.Length == 0) return;
        foreach (var c in clips) { c.loopTime = false; c.loopPose = false; }
        mi.clipAnimations = clips;
    }

    void OnPostprocessAnimation(GameObject root, AnimationClip clip)
    {
        if (!IsClip(assetPath)) return;
        int remapped = RemapRoot(clip);
        int stripped = StripNonRootPositions(clip);
        int baked = BakeNodeDefaults(root, clip);
        if (remapped + stripped + baked > 0)
            Debug.Log($"[RIGGED-CHAR] {{\"clip\":\"{assetPath}\",\"remapped\":{remapped},\"stripped\":{stripped},\"bakedDefaults\":{baked}}}");
    }

    /// <summary>Rename alias root nodes in every binding path. Generic binds by path, so a clip whose
    /// root is named differently binds nothing until this runs.</summary>
    public static int RemapRoot(AnimationClip clip)
    {
        int n = 0;
        foreach (var b in AnimationUtility.GetCurveBindings(clip))
        {
            string p = Canonical(b.path);
            if (p == b.path) continue;
            var curve = AnimationUtility.GetEditorCurve(clip, b);
            AnimationUtility.SetEditorCurve(clip, b, null);
            var nb = b;
            nb.path = p;
            AnimationUtility.SetEditorCurve(clip, nb, curve);
            n++;
        }
        return n;
    }

    public static string Canonical(string path)
    {
        foreach (var a in RootAliases)
        {
            if (path == a) return RootNode;
            if (path.StartsWith(a + "/", StringComparison.Ordinal)) return RootNode + path.Substring(a.Length);
        }
        return path;
    }

    /// <summary>Only the root bone translates. A stray position curve on any other bone (a few keys of
    /// noise are enough) replaces the fitted character's bone length with the pack body's.</summary>
    public static int StripNonRootPositions(AnimationClip clip)
    {
        int n = 0;
        foreach (var b in AnimationUtility.GetCurveBindings(clip))
        {
            if (b.type != typeof(Transform) || b.path == RootBonePath) continue;
            if (!b.propertyName.StartsWith("m_LocalPosition", StringComparison.Ordinal) &&
                !b.propertyName.StartsWith("m_LocalScale", StringComparison.Ordinal)) continue;
            AnimationUtility.SetEditorCurve(clip, b, null);
            n++;
        }
        return n;
    }

    /// <summary>Keyframe reduction can delete a bone's whole curve. On the pack's own body that bone then
    /// holds this file's node default; on another model it would hold that model's default. Write the
    /// file's default as a constant curve so every body plays the same pose.</summary>
    public static int BakeNodeDefaults(GameObject root, AnimationClip clip)
    {
        var rotated = new HashSet<string>(AnimationUtility.GetCurveBindings(clip)
            .Where(b => b.propertyName.StartsWith("m_LocalRotation", StringComparison.Ordinal) ||
                        b.propertyName.StartsWith("localEulerAngles", StringComparison.Ordinal))
            .Select(b => b.path));
        float end = Mathf.Max(clip.length, 1f / Mathf.Max(clip.frameRate, 1f));
        int n = 0;
        foreach (var t in root.GetComponentsInChildren<Transform>(true))
        {
            if (t == root.transform || t.GetComponent<Renderer>() != null) continue;
            string path = Canonical(AnimationUtility.CalculateTransformPath(t, root.transform));
            if (!path.StartsWith(RootNode + "/", StringComparison.Ordinal) || rotated.Contains(path)) continue;
            var q = t.localRotation;
            Constant(clip, path, "m_LocalRotation.x", q.x, end);
            Constant(clip, path, "m_LocalRotation.y", q.y, end);
            Constant(clip, path, "m_LocalRotation.z", q.z, end);
            Constant(clip, path, "m_LocalRotation.w", q.w, end);
            n++;
        }
        return n;
    }

    static void Constant(AnimationClip clip, string path, string prop, float v, float end)
    {
        var b = EditorCurveBinding.FloatCurve(path, typeof(Transform), prop);
        AnimationUtility.SetEditorCurve(clip, b, AnimationCurve.Constant(0f, end, v));
    }
}
