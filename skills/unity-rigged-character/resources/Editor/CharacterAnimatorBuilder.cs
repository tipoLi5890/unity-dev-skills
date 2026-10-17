// CharacterAnimatorBuilder — the locomotion controller, built in code so it is reproducible:
// delete nothing by hand, re-run after a re-export. Two layers:
//   Base Layer   Move (a 1D blend tree on MoveBlend across the slow and the fast clip, or one clip
//                whose playback rate is MoveSpeed) and Jump, both ways on Grounded, no exit time
//   Hurt         None → Hurt on the Hurt trigger, back on exit time; Override, masked to the upper
//                body so a hit plays on torso and arms while the legs keep running
//
// Drop into an Editor folder with CharacterImportSettings.cs (config, clip names). No package
// needed beyond the built-in Animation module.
//
//   Tools/Unity Dev/Rigged Character/Build Animator     select the character folder first;
//                                                        logs "[RIGGED-CHAR] {json}"
//   CharacterAnimatorBuilder.Build("Assets/Models/Runner")    returns the same JSON, for an eval
//
// REWRITES the controller and mask assets at the config's "animator.controller" and
// "animator.mask" paths: both are deleted and created again on every run. Parameter names come
// from the same block and default to the four AnimatorBridge3D (skill unity-3d-controller) writes:
// Grounded (Bool), MoveBlend (Float, 0 slow to 1 fast), MoveSpeed (Float, playback rate) and Hurt
// (Trigger). An empty name leaves that parameter out, and what hangs off it with it.
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

public static class CharacterAnimatorBuilder
{
    const string MenuPath = "Tools/Unity Dev/Rigged Character/Build Animator";

    [MenuItem(MenuPath)]
    static void Menu()
    {
        Debug.Log("[RIGGED-CHAR] " + Build(CharacterImportSettings.SelectedFolder()));
    }

    public static string Build(string folder)
    {
        CharacterPipelineConfig cfg = CharacterImportSettings.ForFolder(folder);
        if (cfg == null) return CharacterImportSettings.NotACharacterFolder("build-animator", folder);
        CharacterAnimatorConfig a = cfg.animator;
        var notes = new List<string>();

        AnimationClip fast = FindClip(cfg.folder, a.fastClip);
        AnimationClip slow = FindClip(cfg.folder, a.slowClip);
        AnimationClip single = FindClip(cfg.folder, a.singleClip);
        AnimationClip jump = FindClip(cfg.folder, a.jumpClip);
        AnimationClip hurt = FindClip(cfg.folder, a.hurtClip);
        if (fast == null && slow == null && single == null)
            return Report(false, cfg, notes, "no locomotion clip named " + a.slowClip + ", " + a.fastClip + " or " +
                          a.singleClip + " under " + cfg.folder + " — import the clips and run Link Animation Avatars first");

        EnsureFolder(Path.GetDirectoryName(a.controller));
        AssetDatabase.DeleteAsset(a.controller);       // rebuild from a clean asset, never reconcile
        AnimatorController controller = AnimatorController.CreateAnimatorControllerAtPath(a.controller);

        AddParameter(controller, a.grounded, AnimatorControllerParameterType.Bool);
        AddParameter(controller, a.moveBlend, AnimatorControllerParameterType.Float);
        AddParameter(controller, a.moveSpeed, AnimatorControllerParameterType.Float);
        AddParameter(controller, a.hurt, AnimatorControllerParameterType.Trigger);

        BuildBaseLayer(controller, a, fast, slow, single, jump, notes);
        if (hurt == null) notes.Add("no " + a.hurtClip + " clip: no Hurt layer");
        else if (string.IsNullOrEmpty(a.hurt)) notes.Add("hurt parameter name empty: no Hurt layer");
        else BuildHurtLayer(controller, a, hurt, cfg.Humanoid, notes);

        AssetDatabase.SaveAssets();
        return Report(true, cfg, notes, null);
    }

    static void BuildBaseLayer(AnimatorController controller, CharacterAnimatorConfig a, AnimationClip fast,
                               AnimationClip slow, AnimationClip single, AnimationClip jump, List<string> notes)
    {
        AnimatorStateMachine machine = controller.layers[0].stateMachine;
        AnimatorState move = machine.AddState("Move");
        machine.defaultState = move;

        if (fast != null && slow != null && !string.IsNullOrEmpty(a.moveBlend))
        {
            // Blending changes the gait; time-scaling one clip only changes its rate — a slowed
            // sprint still swings its arms like a sprint.
            var tree = new BlendTree
            {
                name = a.moveBlend,
                blendType = BlendTreeType.Simple1D,
                blendParameter = a.moveBlend,
                hideFlags = HideFlags.HideInHierarchy      // a sub-asset of the controller
            };
            AssetDatabase.AddObjectToAsset(tree, controller);
            tree.AddChild(slow, 0f);
            tree.AddChild(fast, 1f);
            move.motion = tree;
            notes.Add("Move: 1D blend tree " + slow.name + " → " + fast.name);
        }
        else
        {
            move.motion = fast != null ? fast : slow != null ? slow : single;
            if (!string.IsNullOrEmpty(a.moveSpeed))
            {
                move.speedParameterActive = true;
                move.speedParameter = a.moveSpeed;
            }
            notes.Add("Move: one clip, " + move.motion.name + (string.IsNullOrEmpty(a.moveSpeed) ? "" : ", rate " + a.moveSpeed));
        }

        if (jump == null) { notes.Add("no " + a.jumpClip + " clip: no Jump state"); return; }
        if (string.IsNullOrEmpty(a.grounded)) { notes.Add("grounded parameter name empty: no Jump state"); return; }
        AnimatorState jumpState = machine.AddState("Jump");
        jumpState.motion = jump;

        // No exit time either way: leaving the ground and landing are events, and waiting for a
        // clip to finish delays the pose by up to a stride.
        AnimatorStateTransition up = move.AddTransition(jumpState);
        up.AddCondition(AnimatorConditionMode.IfNot, 0f, a.grounded);
        up.hasExitTime = false;
        up.duration = 0.08f;

        AnimatorStateTransition down = jumpState.AddTransition(move);
        down.AddCondition(AnimatorConditionMode.If, 0f, a.grounded);
        down.hasExitTime = false;
        down.duration = 0.10f;
    }

    static void BuildHurtLayer(AnimatorController controller, CharacterAnimatorConfig a, AnimationClip hurt,
                               bool humanoid, List<string> notes)
    {
        var machine = new AnimatorStateMachine { name = "Hurt", hideFlags = HideFlags.HideInHierarchy };
        AssetDatabase.AddObjectToAsset(machine, controller);

        // An empty default state: the layer contributes nothing until a hit lands.
        AnimatorState none = machine.AddState("None");
        AnimatorState state = machine.AddState("Hurt");
        state.motion = hurt;
        machine.defaultState = none;

        AnimatorStateTransition into = none.AddTransition(state);
        into.AddCondition(AnimatorConditionMode.If, 0f, a.hurt);
        into.hasExitTime = false;
        into.duration = 0.05f;

        // Back near the end of the reaction on its own; nothing has to clear the trigger.
        AnimatorStateTransition back = state.AddTransition(none);
        back.hasExitTime = true;
        back.exitTime = 0.85f;
        back.duration = 0.15f;

        AvatarMask mask = null;
        if (humanoid) mask = CreateUpperBodyMask(a.mask);
        else notes.Add("Generic rig: the Hurt layer has no mask — a body-part mask needs a Humanoid Avatar");

        controller.AddLayer(new AnimatorControllerLayer
        {
            name = "Hurt",
            stateMachine = machine,
            defaultWeight = 1f,
            blendingMode = AnimatorLayerBlendingMode.Override,
            avatarMask = mask
        });
    }

    /// <summary>
    /// Upper body only; legs, root and IK stay off so locomotion keeps driving them. Expressed in
    /// body parts, not bone names, so it survives a re-rig — the payoff of Humanoid over Generic.
    /// </summary>
    static AvatarMask CreateUpperBodyMask(string path)
    {
        var mask = new AvatarMask();
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.Root, false);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.Body, true);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.Head, true);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.LeftArm, true);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.RightArm, true);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.LeftFingers, true);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.RightFingers, true);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.LeftLeg, false);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.RightLeg, false);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.LeftFootIK, false);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.RightFootIK, false);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.LeftHandIK, false);
        mask.SetHumanoidBodyPartActive(AvatarMaskBodyPart.RightHandIK, false);

        EnsureFolder(Path.GetDirectoryName(path));
        AssetDatabase.DeleteAsset(path);
        AssetDatabase.CreateAsset(mask, path);
        return mask;
    }

    static void AddParameter(AnimatorController controller, string name, AnimatorControllerParameterType type)
    {
        if (!string.IsNullOrEmpty(name)) controller.AddParameter(name, type);
    }

    /// <summary>Clips are sub-assets of their FBX, already renamed by CharacterImportSettings.</summary>
    static AnimationClip FindClip(string folder, string clipName)
    {
        if (string.IsNullOrEmpty(clipName)) return null;
        foreach (string guid in AssetDatabase.FindAssets("t:Model", new[] { folder.TrimEnd('/') }))
            foreach (Object asset in AssetDatabase.LoadAllAssetsAtPath(AssetDatabase.GUIDToAssetPath(guid)))
                if (asset is AnimationClip clip && !clip.name.StartsWith("__preview") && clip.name == clipName)
                    return clip;
        return null;
    }

    static void EnsureFolder(string folder)
    {
        folder = CharacterImportSettings.Norm(folder).TrimEnd('/');
        if (string.IsNullOrEmpty(folder) || AssetDatabase.IsValidFolder(folder)) return;
        string parent = CharacterImportSettings.Norm(Path.GetDirectoryName(folder));
        EnsureFolder(parent);
        AssetDatabase.CreateFolder(parent, Path.GetFileName(folder));
    }

    static string Report(bool ok, CharacterPipelineConfig cfg, List<string> notes, string error)
    {
        var sb = new StringBuilder(256);
        sb.Append("{\"op\":\"build-animator\",\"ok\":").Append(ok ? "true" : "false");
        sb.Append(",\"folder\":").Append(CharacterImportSettings.Q(cfg.folder));
        sb.Append(",\"controller\":").Append(CharacterImportSettings.Q(cfg.animator.controller));
        if (error != null) sb.Append(",\"error\":").Append(CharacterImportSettings.Q(error));
        sb.Append(",\"notes\":[");
        for (int i = 0; i < notes.Count; i++) sb.Append(i > 0 ? "," : "").Append(CharacterImportSettings.Q(notes[i]));
        sb.Append("]}");
        return sb.ToString();
    }
}
