// AnimatorParamAudit — every parameter of a controller, where the graph reads it, and every
// script that writes or reads it, as one JSON object. Finds the parameter nobody writes, the
// parameter two scripts write, the parameter no transition reads, and the name a script sets
// that the controller does not have.
//
// Drop into an Editor folder. Menu: Tools/Unity Dev/Animation/Audit Parameters (select one
// AnimatorController). From `unity command eval`:
//
//   return AnimatorParamAudit.Json(
//       UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEditor.Animations.AnimatorController>(
//           "Assets/Animations/Runner.controller"));
//
// Reads only. The script side is a TEXT scan of *.cs under the root: it sees
//   anim.SetBool("Grounded", …)            a string literal
//   anim.SetBool(GroundedId, …)            an identifier assigned from Animator.StringToHash("Grounded")
//                                          anywhere in the scanned files
// and it does not see a name built at runtime or passed through a variable. A script that
// writes two controllers' parameters is counted for both; read "writers" as candidates.
//
// verdict per parameter:
//   ok              one writing file, and the graph reads it
//   no-writer       the graph reads it and no script sets it — it stays at its default
//   multi-writer    more than one file sets it — the last one to run each frame wins
//   unread          scripts set it and nothing in the graph reads it
//   dead            neither
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

public static class AnimatorParamAudit
{
    sealed class Ref
    {
        public string file;
        public int line;
        public string call;
    }

    static readonly Regex HashDecl = new Regex(
        @"(\w+)\s*=\s*Animator\s*\.\s*StringToHash\s*\(\s*""([^""]+)""\s*\)", RegexOptions.Compiled);

    static readonly Regex Call = new Regex(
        @"\.\s*(SetFloat|SetBool|SetInteger|SetTrigger|ResetTrigger|GetFloat|GetBool|GetInteger)\s*\(\s*" +
        @"(?:""([^""]+)""|([A-Za-z_][\w\.]*))", RegexOptions.Compiled);

    /// <summary>The audit as one JSON object on one line.</summary>
    public static string Json(AnimatorController controller, string scanRoot = "Assets")
    {
        if (controller == null) return "{\"error\":\"no controller\"}";

        // 1 · where the graph reads each parameter
        var graph = new Dictionary<string, List<string>>();
        for (int i = 0; i < controller.layers.Length; i++)
        {
            AnimatorControllerLayer layer = controller.layers[i];
            if (layer.stateMachine != null) Walk(layer.stateMachine, layer.name, graph);
        }

        // 2 · where scripts write and read each name
        var writers = new Dictionary<string, List<Ref>>();
        var readers = new Dictionary<string, List<Ref>>();
        int files = Scan(scanRoot, writers, readers);

        // 3 · join
        var sb = new StringBuilder(1024);
        sb.Append("{\"controller\":").Append(Str(AssetDatabase.GetAssetPath(controller)))
          .Append(",\"scanRoot\":").Append(Str(scanRoot))
          .Append(",\"filesScanned\":").Append(files)
          .Append(",\"parameters\":[");

        var known = new HashSet<string>();
        int problems = 0;
        AnimatorControllerParameter[] parameters = controller.parameters;
        for (int i = 0; i < parameters.Length; i++)
        {
            AnimatorControllerParameter p = parameters[i];
            known.Add(p.name);
            List<string> uses = Get(graph, p.name);
            List<Ref> w = Get(writers, p.name);
            List<Ref> r = Get(readers, p.name);
            int writingFiles = DistinctFiles(w);

            string verdict = "ok";
            if (writingFiles > 1) verdict = "multi-writer";
            else if (writingFiles == 0 && uses.Count > 0) verdict = "no-writer";
            else if (writingFiles > 0 && uses.Count == 0) verdict = "unread";
            else if (writingFiles == 0 && uses.Count == 0) verdict = "dead";
            if (verdict != "ok") problems++;

            if (i > 0) sb.Append(',');
            sb.Append("{\"name\":").Append(Str(p.name))
              .Append(",\"type\":").Append(Str(p.type.ToString()))
              .Append(",\"verdict\":").Append(Str(verdict))
              .Append(",\"graph\":[");
            for (int k = 0; k < uses.Count; k++) sb.Append(k > 0 ? "," : "").Append(Str(uses[k]));
            sb.Append("],\"writers\":");
            Refs(sb, w);
            sb.Append(",\"readers\":");
            Refs(sb, r);
            sb.Append('}');
        }

        // Names the graph or a script uses that the controller does not declare. A script-side
        // entry here is usually a typo, and Animator.SetBool on a missing name only warns.
        sb.Append("],\"undeclaredInGraph\":[");
        bool first = true;
        foreach (KeyValuePair<string, List<string>> g in graph)
        {
            if (known.Contains(g.Key)) continue;
            sb.Append(first ? "" : ",").Append(Str(g.Key));
            first = false;
            problems++;
        }
        sb.Append("],\"setByScriptsNotInController\":[");
        first = true;
        foreach (KeyValuePair<string, List<Ref>> w in writers)
        {
            if (known.Contains(w.Key)) continue;
            sb.Append(first ? "" : ",").Append("{\"name\":").Append(Str(w.Key)).Append(",\"writers\":");
            Refs(sb, w.Value);
            sb.Append('}');
            first = false;
        }
        sb.Append("],\"problems\":").Append(problems).Append('}');
        return sb.ToString();
    }

    // ---------------------------------------------------------------- graph walk

    static void Walk(AnimatorStateMachine sm, string path, Dictionary<string, List<string>> graph)
    {
        foreach (AnimatorStateTransition t in sm.anyStateTransitions)
            Conditions(t, path + "/AnyState→" + Dest(t), graph);
        foreach (AnimatorTransition t in sm.entryTransitions)
            Conditions(t, path + "/Entry→" + Dest(t), graph);

        foreach (ChildAnimatorState child in sm.states)
        {
            AnimatorState s = child.state;
            if (s == null) continue;
            string here = path + "/" + s.name;
            foreach (AnimatorStateTransition t in s.transitions)
                Conditions(t, here + "→" + Dest(t), graph);
            if (s.speedParameterActive) Add(graph, s.speedParameter, here + " speed");
            if (s.cycleOffsetParameterActive) Add(graph, s.cycleOffsetParameter, here + " cycleOffset");
            if (s.mirrorParameterActive) Add(graph, s.mirrorParameter, here + " mirror");
            if (s.timeParameterActive) Add(graph, s.timeParameter, here + " motionTime");
            Motion(s.motion, here, graph);
        }

        foreach (ChildAnimatorStateMachine child in sm.stateMachines)
        {
            if (child.stateMachine == null) continue;
            foreach (AnimatorTransition t in sm.GetStateMachineTransitions(child.stateMachine))
                Conditions(t, path + "/" + child.stateMachine.name + "→" + Dest(t), graph);
            Walk(child.stateMachine, path + "/" + child.stateMachine.name, graph);
        }
    }

    static string Dest(AnimatorTransitionBase t)
    {
        if (t.destinationState != null) return t.destinationState.name;
        if (t.destinationStateMachine != null) return t.destinationStateMachine.name;
        return t.isExit ? "Exit" : "?";
    }

    static void Conditions(AnimatorTransitionBase t, string where, Dictionary<string, List<string>> graph)
    {
        foreach (AnimatorCondition c in t.conditions) Add(graph, c.parameter, where);
    }

    static void Motion(Motion motion, string where, Dictionary<string, List<string>> graph)
    {
        var tree = motion as BlendTree;
        if (tree == null) return;
        string here = where + " tree";
        if (tree.blendType == BlendTreeType.Direct)
        {
            foreach (ChildMotion c in tree.children) Add(graph, c.directBlendParameter, here + " direct");
        }
        else
        {
            Add(graph, tree.blendParameter, here + " X");
            if (tree.blendType != BlendTreeType.Simple1D) Add(graph, tree.blendParameterY, here + " Y");
        }
        foreach (ChildMotion c in tree.children) Motion(c.motion, here, graph);
    }

    // ---------------------------------------------------------------- script scan

    static int Scan(string root, Dictionary<string, List<Ref>> writers, Dictionary<string, List<Ref>> readers)
    {
        if (!Directory.Exists(root)) return 0;
        string[] paths = Directory.GetFiles(root, "*.cs", SearchOption.AllDirectories);
        var texts = new string[paths.Length];
        var ids = new Dictionary<string, string>();          // identifier → parameter name

        for (int i = 0; i < paths.Length; i++)
        {
            texts[i] = File.ReadAllText(paths[i]);
            foreach (Match m in HashDecl.Matches(texts[i])) ids[m.Groups[1].Value] = m.Groups[2].Value;
        }

        for (int i = 0; i < paths.Length; i++)
        {
            string file = paths[i].Replace('\\', '/');
            // An Editor script that builds the controller names parameters without writing them.
            if (file.Contains("/Editor/")) continue;
            foreach (Match m in Call.Matches(texts[i]))
            {
                string name = m.Groups[2].Success ? m.Groups[2].Value : null;
                if (name == null)
                {
                    string id = m.Groups[3].Value;
                    int dot = id.LastIndexOf('.');
                    if (dot >= 0) id = id.Substring(dot + 1);
                    if (!ids.TryGetValue(id, out name)) continue;
                }
                string call = m.Groups[1].Value;
                var r = new Ref { file = file, line = LineOf(texts[i], m.Index), call = call };
                Dictionary<string, List<Ref>> into = call.StartsWith("Get") ? readers : writers;
                List<Ref> list;
                if (!into.TryGetValue(name, out list)) into[name] = list = new List<Ref>();
                list.Add(r);
            }
        }
        return paths.Length;
    }

    static int LineOf(string text, int index)
    {
        int line = 1;
        for (int i = 0; i < index && i < text.Length; i++) if (text[i] == '\n') line++;
        return line;
    }

    // ---------------------------------------------------------------- helpers

    static void Add(Dictionary<string, List<string>> graph, string parameter, string where)
    {
        if (string.IsNullOrEmpty(parameter)) return;
        List<string> list;
        if (!graph.TryGetValue(parameter, out list)) graph[parameter] = list = new List<string>();
        if (!list.Contains(where)) list.Add(where);
    }

    static List<T> Get<T>(Dictionary<string, List<T>> d, string key)
    {
        List<T> list;
        return d.TryGetValue(key, out list) ? list : new List<T>();
    }

    static int DistinctFiles(List<Ref> refs)
    {
        var files = new HashSet<string>();
        foreach (Ref r in refs) files.Add(r.file);
        return files.Count;
    }

    static void Refs(StringBuilder sb, List<Ref> refs)
    {
        sb.Append('[');
        for (int i = 0; i < refs.Count; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append("{\"file\":").Append(Str(refs[i].file))
              .Append(",\"line\":").Append(refs[i].line)
              .Append(",\"call\":").Append(Str(refs[i].call)).Append('}');
        }
        sb.Append(']');
    }

    static string Str(string s)
    {
        if (s == null) return "null";
        return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
    }

    // ---------------------------------------------------------------- menu

    const string Menu = "Tools/Unity Dev/Animation/Audit Parameters";

    [MenuItem(Menu, true)]
    static bool CanAudit() => Selection.activeObject is AnimatorController;

    [MenuItem(Menu)]
    static void AuditSelected()
    {
        Debug.Log("[ANIM] " + Json((AnimatorController)Selection.activeObject));
    }
}
