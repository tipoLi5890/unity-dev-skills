// SpriteStateGraphBuilder — the Animator graph of a frame-clip character: idle, run, jump, fall
// and hurt, wired so the picture follows the game's state on the frame the state changes.
//
// Drop into an Editor folder. Menu: Tools/Unity Dev/Animation/Sprite State Graph From Folder.
// From `unity command eval`, call Report(...) first, show the text, wait for a yes, then call
// Build(...) with the same arguments.
//
// Building writes a .controller asset. When one already exists at the path, its parameters and
// layer 0 are rebuilt IN PLACE — the asset keeps its GUID, so every Animator that references it
// keeps working — and further layers are left alone. Report and wait for confirmation first.
//
// Parameters, each written by one bridge component and nothing else:
//   Grounded  Bool      Moving  Bool      VelY  Float      Hurt  Trigger
//
// Every transition has duration 0 and no exit time, except Hurt → Idle, which leaves when the
// one-shot ends. A sprite clip swaps whole frames, so a cross-fade has nothing to blend: a
// non-zero duration only delays the swap.
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

public static class SpriteStateGraphBuilder
{
    public const string Grounded = "Grounded";
    public const string Moving = "Moving";
    public const string VelY = "VelY";
    public const string Hurt = "Hurt";

    /// <summary>idle and run are required; the rest are optional and their states are left out.</summary>
    public sealed class Clips
    {
        public AnimationClip idle, run, jump, fall, hurt;
    }

    // ---------------------------------------------------------------- clips by name

    /// <summary>Finds clips in a folder by the last token of their name: runner_idle, runner_run,
    /// runner_jump, runner_fall, runner_hurt. Not recursive.</summary>
    public static Clips FindClips(string folder)
    {
        var c = new Clips();
        foreach (string guid in AssetDatabase.FindAssets("t:AnimationClip", new[] { folder }))
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (Path.GetDirectoryName(path).Replace('\\', '/') != folder.TrimEnd('/')) continue;
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
            if (clip == null) continue;
            string[] t = clip.name.ToLowerInvariant().Split('_', '-', ' ');
            switch (t[t.Length - 1])
            {
                case "idle": c.idle = clip; break;
                case "run":  c.run = clip; break;
                case "jump": c.jump = clip; break;
                case "fall": c.fall = clip; break;
                case "hurt": c.hurt = clip; break;
            }
        }
        return c;
    }

    // ---------------------------------------------------------------- problems and report

    public static List<string> Problems(Clips c)
    {
        var p = new List<string>();
        if (c == null) { p.Add("no clips"); return p; }
        if (c.idle == null) p.Add("no idle clip");
        if (c.run == null) p.Add("no run clip");
        Check(p, c.idle, "idle", true);
        Check(p, c.run, "run", true);
        Check(p, c.jump, "jump", false);
        Check(p, c.fall, "fall", true);
        Check(p, c.hurt, "hurt", false);
        return p;
    }

    static void Check(List<string> p, AnimationClip clip, string role, bool shouldLoop)
    {
        if (clip == null) return;
        if (clip.legacy) p.Add(role + ": " + clip.name + " is a Legacy clip; an Animator cannot play it");
        bool loops = AnimationUtility.GetAnimationClipSettings(clip).loopTime;
        if (role == "hurt" && loops)
            p.Add("hurt: " + clip.name + " has Loop Time on — the exit-time transition back to idle " +
                  "fires once per loop, not once per hit; turn Loop Time off");
        else if (shouldLoop && !loops)
            p.Add(role + ": " + clip.name + " has Loop Time off and freezes on its last frame");
    }

    /// <summary>What Build would do, without doing it.</summary>
    public static string Report(string controllerPath, Clips c)
    {
        var sb = new StringBuilder();
        bool exists = AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath) != null;
        sb.Append("controller   ").Append(controllerPath)
          .Append(exists ? "  (exists — parameters and layer 0 are REBUILT, GUID kept)" : "  (create)").Append('\n');
        sb.Append("parameters   Grounded Bool, Moving Bool, VelY Float, Hurt Trigger\n");
        if (c != null)
        {
            Line(sb, "Idle", c.idle, "default");
            Line(sb, "Run", c.run, "Grounded && Moving");
            Line(sb, "Jump", c.jump, "!Grounded && VelY > 0");
            Line(sb, "Fall", c.fall, c.jump != null ? "!Grounded, after Jump in priority" : "!Grounded");
            Line(sb, "Hurt", c.hurt, "Any State on the Hurt trigger; back to Idle at the clip's end");
        }
        sb.Append("transitions  duration 0, no exit time (Hurt → Idle: exit time 1)\n");
        foreach (string problem in Problems(c)) sb.Append("PROBLEM      ").Append(problem).Append('\n');
        return sb.ToString().TrimEnd('\n');
    }

    static void Line(StringBuilder sb, string state, AnimationClip clip, string when)
    {
        sb.Append("state        ").Append(state.PadRight(5));
        if (clip == null) sb.Append("  (no clip — state left out)\n");
        else sb.Append("  ").Append(clip.name).Append("  ").Append(clip.length.ToString("F3")).Append(" s  — ")
               .Append(when).Append('\n');
    }

    // ---------------------------------------------------------------- build

    /// <summary>Creates the controller, or rebuilds layer 0 of the one at the path. Throws when
    /// idle or run is missing; the other entries of Problems() are warnings the report shows.</summary>
    public static AnimatorController Build(string controllerPath, Clips c)
    {
        if (c == null || c.idle == null || c.run == null)
            throw new System.InvalidOperationException("SpriteStateGraphBuilder: idle and run clips are required");

        var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);
        if (controller == null)
        {
            string dir = Path.GetDirectoryName(controllerPath).Replace('\\', '/');
            if (!AssetDatabase.IsValidFolder(dir))
                throw new System.InvalidOperationException("folder does not exist: " + dir);
            controller = AnimatorController.CreateAnimatorControllerAtPath(controllerPath);
        }
        else
        {
            Undo.RegisterCompleteObjectUndo(controller, "Rebuild sprite state graph");
            Clear(controller);
        }

        controller.AddParameter(Grounded, AnimatorControllerParameterType.Bool);
        controller.AddParameter(Moving, AnimatorControllerParameterType.Bool);
        controller.AddParameter(VelY, AnimatorControllerParameterType.Float);
        controller.AddParameter(Hurt, AnimatorControllerParameterType.Trigger);

        AnimatorStateMachine sm = controller.layers[0].stateMachine;
        AnimatorState idle = AddState(sm, "Idle", c.idle, new Vector3(260f, 60f));
        AnimatorState run = AddState(sm, "Run", c.run, new Vector3(260f, 160f));
        AnimatorState jump = c.jump != null ? AddState(sm, "Jump", c.jump, new Vector3(520f, 60f)) : null;
        AnimatorState fall = c.fall != null ? AddState(sm, "Fall", c.fall, new Vector3(520f, 160f)) : null;
        AnimatorState hurt = c.hurt != null ? AddState(sm, "Hurt", c.hurt, new Vector3(260f, -60f)) : null;
        sm.defaultState = idle;

        Instant(idle.AddTransition(run), (Grounded, true), (Moving, true));
        Instant(run.AddTransition(idle), (Grounded, true), (Moving, false));

        // Transitions on one state are tried in list order and the first whose conditions hold
        // wins, so the narrower one (rising) is added before the wider one (airborne at all).
        foreach (AnimatorState ground in new[] { idle, run })
        {
            if (jump != null)
            {
                AnimatorStateTransition up = Instant(ground.AddTransition(jump), (Grounded, false));
                if (fall != null) up.AddCondition(AnimatorConditionMode.Greater, 0f, VelY);
            }
            if (fall != null) Instant(ground.AddTransition(fall), (Grounded, false));
        }

        if (jump != null && fall != null)
            Instant(jump.AddTransition(fall)).AddCondition(AnimatorConditionMode.Less, 0f, VelY);

        foreach (AnimatorState air in new[] { jump, fall })
        {
            if (air == null) continue;
            Instant(air.AddTransition(run), (Grounded, true), (Moving, true));   // land running: no idle frame
            Instant(air.AddTransition(idle), (Grounded, true));
        }

        if (hurt != null)
        {
            AnimatorStateTransition any = sm.AddAnyStateTransition(hurt);
            Instant(any).AddCondition(AnimatorConditionMode.If, 0f, Hurt);
            // A trigger is consumed by the transition it fires, so allowing self-transition here
            // means a second hit restarts the clip. With a Bool condition this must be false,
            // or Any State re-enters Hurt on every evaluation while the bool is held.
            any.canTransitionToSelf = true;

            AnimatorStateTransition back = hurt.AddTransition(idle);
            back.hasExitTime = true;
            back.exitTime = 1f;
            back.hasFixedDuration = true;
            back.duration = 0f;
            back.offset = 0f;
        }

        EditorUtility.SetDirty(controller);
        AssetDatabase.SaveAssets();
        return controller;
    }

    static AnimatorState AddState(AnimatorStateMachine sm, string name, AnimationClip clip, Vector3 at)
    {
        AnimatorState s = sm.AddState(name, at);
        s.motion = clip;
        return s;
    }

    static AnimatorStateTransition Instant(AnimatorStateTransition t, params (string name, bool value)[] bools)
    {
        t.hasExitTime = false;
        t.hasFixedDuration = true;
        t.duration = 0f;
        t.offset = 0f;
        foreach ((string name, bool value) in bools)
            t.AddCondition(value ? AnimatorConditionMode.If : AnimatorConditionMode.IfNot, 0f, name);
        return t;
    }

    // Empties layer 0 and the parameter list without deleting the asset: a delete-and-recreate
    // gives the controller a new GUID and every Animator referencing it shows "None".
    static void Clear(AnimatorController controller)
    {
        if (controller.layers.Length == 0) controller.AddLayer("Base Layer");
        AnimatorStateMachine sm = controller.layers[0].stateMachine;
        foreach (AnimatorStateTransition t in sm.anyStateTransitions) sm.RemoveAnyStateTransition(t);
        foreach (AnimatorTransition t in sm.entryTransitions) sm.RemoveEntryTransition(t);
        foreach (ChildAnimatorState s in sm.states) sm.RemoveState(s.state);
        foreach (ChildAnimatorStateMachine child in sm.stateMachines) sm.RemoveStateMachine(child.stateMachine);
        controller.parameters = new AnimatorControllerParameter[0];
    }

    /// <summary>States, default state and transition count as the asset holds them.</summary>
    public static string Describe(AnimatorController controller)
    {
        AnimatorStateMachine sm = controller.layers[0].stateMachine;
        var sb = new StringBuilder();
        int transitions = sm.anyStateTransitions.Length;
        sb.Append("states=");
        for (int i = 0; i < sm.states.Length; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append(sm.states[i].state.name);
            transitions += sm.states[i].state.transitions.Length;
        }
        sb.Append(" default=").Append(sm.defaultState != null ? sm.defaultState.name : "(none)")
          .Append(" transitions=").Append(transitions)
          .Append(" parameters=").Append(controller.parameters.Length);
        return sb.ToString();
    }

    // ---------------------------------------------------------------- menu

    const string Menu = "Tools/Unity Dev/Animation/Sprite State Graph From Folder";

    /// <summary>Select the folder holding the clips. The controller is written beside them,
    /// named after the folder.</summary>
    [MenuItem(Menu)]
    static void BuildFromFolder()
    {
        string folder = Selection.activeObject != null ? AssetDatabase.GetAssetPath(Selection.activeObject) : null;
        if (string.IsNullOrEmpty(folder) || !AssetDatabase.IsValidFolder(folder))
        {
            EditorUtility.DisplayDialog("Sprite state graph", "Select the folder that holds the clips.", "OK");
            return;
        }

        Clips clips = FindClips(folder);
        string path = folder + "/" + Path.GetFileName(folder) + ".controller";
        string report = Report(path, clips);
        Debug.Log("[ANIM] sprite state graph — report\n" + report);

        if (clips.idle == null || clips.run == null)
        {
            EditorUtility.DisplayDialog("Sprite state graph", report, "OK");
            return;
        }
        if (!EditorUtility.DisplayDialog("Sprite state graph", report, "Build", "Cancel")) return;

        AnimatorController controller = Build(path, clips);
        Debug.Log("[ANIM] sprite state graph — built: " + Describe(controller));
    }
}
