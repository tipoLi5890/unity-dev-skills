// DirectionalBlendTreeBuilder — one Animator state holding a 2D directional blend tree, built
// from clips keyed by direction. Serves a 3D strafe set and the 4-way or 8-way sprite sets of a
// top-down character with the same call.
//
// Drop into an Editor folder. Menu: Tools/Unity Dev/Animation/Directional Blend Tree From
// Selection. From `unity command eval`, call Report(...) first, show the text, wait for a yes,
// then call Build(...) with the same arguments.
//
// Building writes into a .controller asset: it adds float parameters that are missing, creates
// the state when it is missing, and REPLACES that state's motion. Report what would change and
// wait for confirmation before calling Build.
//
// Clip names carry the direction as their last token, split on '_', '-' or ' ':
//   n ne e se s sw w nw            runner_walk_ne
//   up down left right             sentry_walk_left
//   forward back (backward)        strafe_forward, strafe_back_left
//   idle (centre, optional)        runner_idle
// A two-token suffix (back_left, forward_right, up_left) is read before a one-token one.
using System.Collections.Generic;
using System.Text;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

public static class DirectionalBlendTreeBuilder
{
    public struct Entry
    {
        public AnimationClip clip;
        public Vector2 position;        // x = right, y = up (2D) or forward (3D)

        public Entry(AnimationClip clip, Vector2 position)
        {
            this.clip = clip;
            this.position = position;
        }
    }

    const float Diag = 0.70710678f;

    static readonly Dictionary<string, Vector2> Directions = new Dictionary<string, Vector2>
    {
        { "idle", Vector2.zero },
        { "n", new Vector2(0f, 1f) },      { "up", new Vector2(0f, 1f) },     { "forward", new Vector2(0f, 1f) },
        { "s", new Vector2(0f, -1f) },     { "down", new Vector2(0f, -1f) },  { "back", new Vector2(0f, -1f) },
        { "backward", new Vector2(0f, -1f) },
        { "e", new Vector2(1f, 0f) },      { "right", new Vector2(1f, 0f) },
        { "w", new Vector2(-1f, 0f) },     { "left", new Vector2(-1f, 0f) },
        { "ne", new Vector2(Diag, Diag) }, { "nw", new Vector2(-Diag, Diag) },
        { "se", new Vector2(Diag, -Diag) }, { "sw", new Vector2(-Diag, -Diag) },
    };

    // ---------------------------------------------------------------- names → entries

    /// <summary>Reads the direction off the end of a clip name. False when no token matches.</summary>
    public static bool DirectionOf(string clipName, out Vector2 position)
    {
        position = Vector2.zero;
        if (string.IsNullOrEmpty(clipName)) return false;
        string[] t = clipName.ToLowerInvariant().Split('_', '-', ' ');
        if (t.Length == 0) return false;

        Vector2 a, b;
        if (t.Length >= 2 && Directions.TryGetValue(t[t.Length - 2], out a)
                          && Directions.TryGetValue(t[t.Length - 1], out b)
                          && a != Vector2.zero && b != Vector2.zero
                          && Mathf.Abs(Vector2.Dot(a, b)) < 0.01f)
        {
            position = (a + b).normalized;      // back_left → (-0.707, -0.707)
            return true;
        }
        return Directions.TryGetValue(t[t.Length - 1], out position);
    }

    /// <summary>Entries for every clip whose name ends in a direction token; the rest are
    /// returned in skipped so the report can name them.</summary>
    public static List<Entry> FromNames(IEnumerable<AnimationClip> clips, List<string> skipped = null)
    {
        var list = new List<Entry>();
        foreach (AnimationClip c in clips)
        {
            if (c == null) continue;
            Vector2 p;
            if (DirectionOf(c.name, out p)) list.Add(new Entry(c, p));
            else if (skipped != null) skipped.Add(c.name);
        }
        list.Sort((x, y) => Angle(x.position).CompareTo(Angle(y.position)));
        return list;
    }

    // Centre first, then clockwise from north — the order the Inspector reads best in.
    static float Angle(Vector2 p)
    {
        if (p == Vector2.zero) return -1f;
        float a = Mathf.Atan2(p.x, p.y) * Mathf.Rad2Deg;
        return a < 0f ? a + 360f : a;
    }

    // ---------------------------------------------------------------- problems and report

    const string Warning = "warning: ";

    /// <summary>Everything wrong with the tree before it is built. An entry starting with
    /// "warning: " is reported and does not stop Build; any other entry does.</summary>
    public static List<string> Problems(IList<Entry> entries, BlendTreeType type)
    {
        var p = new List<string>();
        if (type != BlendTreeType.SimpleDirectional2D && type != BlendTreeType.FreeformDirectional2D
            && type != BlendTreeType.FreeformCartesian2D)
            p.Add("blend type " + type + " is not a 2D type");
        if (entries == null || entries.Count < 2) { p.Add("needs at least two clips"); return p; }

        bool centre = false;
        for (int i = 0; i < entries.Count; i++)
        {
            Entry e = entries[i];
            if (e.clip == null) { p.Add("entry " + i + " has no clip"); continue; }
            if (e.clip.legacy) p.Add(e.clip.name + " is a Legacy clip; an Animator cannot play it");
            // The tree's length is the weight-blended length of its children, and normalised
            // time is elapsed time over that length.
            if (e.clip.length <= 0f)
                p.Add(e.clip.name + " has length 0 — give it a second key one frame later");
            if (e.position == Vector2.zero) centre = true;
            for (int k = 0; k < i; k++)
                if (entries[k].clip != null && (entries[k].position - e.position).sqrMagnitude < 1e-6f)
                    p.Add(e.clip.name + " and " + entries[k].clip.name + " share position " + e.position);
        }

        if (type == BlendTreeType.SimpleDirectional2D)
        {
            // Simple Directional allows one motion per direction: two on the same ray from the
            // origin (walk and run, both north) need Freeform Directional instead.
            for (int i = 0; i < entries.Count; i++)
                for (int k = 0; k < i; k++)
                {
                    Vector2 a = entries[i].position, b = entries[k].position;
                    if (a == Vector2.zero || b == Vector2.zero) continue;
                    if (Vector2.Angle(a, b) < 1f)
                        p.Add(Name(entries[i]) + " and " + Name(entries[k]) + " point the same way; " +
                              "use BlendTreeType.FreeformDirectional2D for two speeds per direction");
                }
        }
        // Not fatal: a facing tree fed the last non-zero direction never sits at the origin.
        if (!centre)
            p.Add(Warning + "no clip at (0, 0) — with both parameters at 0 the tree blends opposing " +
                  "directions; add an idle or in-place clip, or never write (0, 0)");
        return p;
    }

    static bool Blocks(string problem) => !problem.StartsWith(Warning);

    static string Name(Entry e) => e.clip != null ? e.clip.name : "(null)";

    /// <summary>What Build would do, without doing it.</summary>
    public static string Report(AnimatorController controller, int layer, string stateName,
                                string paramX, string paramY, IList<Entry> entries,
                                BlendTreeType type = BlendTreeType.SimpleDirectional2D)
    {
        var sb = new StringBuilder();
        string path = controller != null ? AssetDatabase.GetAssetPath(controller) : "(no controller)";
        sb.Append("controller   ").Append(string.IsNullOrEmpty(path) ? "(in memory)" : path).Append('\n');
        if (controller == null) return sb.Append("PROBLEM      no controller").ToString();
        if (layer < 0 || layer >= controller.layers.Length)
            return sb.Append("PROBLEM      layer ").Append(layer).Append(" does not exist").ToString();

        AnimatorState existing = FindState(controller.layers[layer].stateMachine, stateName);
        sb.Append("state        ").Append(stateName)
          .Append(existing == null ? "  (create)" : "  (exists — its motion is REPLACED)").Append('\n');
        sb.Append("tree         ").Append(type).Append(" on ").Append(paramX).Append(", ").Append(paramY).Append('\n');
        foreach (string prm in new[] { paramX, paramY })
            sb.Append("parameter    ").Append(prm)
              .Append(HasParameter(controller, prm) ? "  (exists)" : "  (add, Float)").Append('\n');
        if (entries != null)
            foreach (Entry e in entries)
                sb.Append("motion       ").Append(e.position.ToString("F3")).Append("  ").Append(Name(e))
                  .Append(e.clip != null ? "  " + e.clip.length.ToString("F3") + " s" : "").Append('\n');
        foreach (string problem in Problems(entries, type))
            sb.Append(Blocks(problem) ? "PROBLEM      " : "WARNING      ")
              .Append(Blocks(problem) ? problem : problem.Substring(Warning.Length)).Append('\n');
        return sb.ToString().TrimEnd('\n');
    }

    // ---------------------------------------------------------------- build

    /// <summary>Creates or replaces the state's blend tree. Throws on a blocking entry of Problems().
    /// Returns the tree; read tree.children back to confirm the positions.</summary>
    public static BlendTree Build(AnimatorController controller, int layer, string stateName,
                                  string paramX, string paramY, IList<Entry> entries,
                                  BlendTreeType type = BlendTreeType.SimpleDirectional2D)
    {
        if (controller == null) throw new System.ArgumentNullException("controller");
        if (layer < 0 || layer >= controller.layers.Length)
            throw new System.ArgumentException("layer " + layer + " does not exist");
        List<string> problems = Problems(entries, type).FindAll(Blocks);
        if (problems.Count > 0)
            throw new System.InvalidOperationException("DirectionalBlendTreeBuilder: " +
                                                       string.Join("; ", problems.ToArray()));

        Undo.RegisterCompleteObjectUndo(controller, "Build directional blend tree");

        foreach (string prm in new[] { paramX, paramY })
            if (!HasParameter(controller, prm))
                controller.AddParameter(prm, AnimatorControllerParameterType.Float);

        AnimatorStateMachine machine = controller.layers[layer].stateMachine;
        AnimatorState state = FindState(machine, stateName);
        if (state == null) state = machine.AddState(stateName);

        bool persistent = AssetDatabase.Contains(controller);

        // The old tree is a hidden sub-asset of the controller; leaving it behind grows the
        // file by one orphan on every rebuild.
        var old = state.motion as BlendTree;
        if (old != null && persistent
            && AssetDatabase.GetAssetPath(old) == AssetDatabase.GetAssetPath(controller))
            Object.DestroyImmediate(old, true);

        var tree = new BlendTree
        {
            name = stateName,
            blendType = type,
            blendParameter = paramX,
            blendParameterY = paramY,
            hideFlags = HideFlags.HideInHierarchy,
        };
        if (persistent) AssetDatabase.AddObjectToAsset(tree, controller);

        foreach (Entry e in entries) tree.AddChild(e.clip, e.position);
        state.motion = tree;

        if (persistent)
        {
            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();
        }
        return tree;
    }

    /// <summary>The positions as the asset holds them, for the read-back after Build.</summary>
    public static string Describe(BlendTree tree)
    {
        var sb = new StringBuilder();
        sb.Append(tree.blendType).Append(" on ").Append(tree.blendParameter).Append(", ")
          .Append(tree.blendParameterY).Append(": ");
        ChildMotion[] kids = tree.children;
        for (int i = 0; i < kids.Length; i++)
        {
            if (i > 0) sb.Append(" | ");
            sb.Append(kids[i].motion != null ? kids[i].motion.name : "(null)").Append(' ')
              .Append(kids[i].position.ToString("F3"));
        }
        return sb.ToString();
    }

    static AnimatorState FindState(AnimatorStateMachine machine, string name)
    {
        foreach (ChildAnimatorState s in machine.states)
            if (s.state != null && s.state.name == name) return s.state;
        return null;
    }

    static bool HasParameter(AnimatorController controller, string name)
    {
        foreach (AnimatorControllerParameter p in controller.parameters)
            if (p.name == name) return true;
        return false;
    }

    // ---------------------------------------------------------------- menu

    const string Menu = "Tools/Unity Dev/Animation/Directional Blend Tree From Selection";

    [MenuItem(Menu, true)]
    static bool CanBuildFromSelection() => Selection.GetFiltered<AnimationClip>(SelectionMode.Assets).Length >= 2;

    /// <summary>Select the clips and one AnimatorController. The state is named "Move" and the
    /// parameters "MoveX" / "MoveY"; call Build directly for anything else.</summary>
    [MenuItem(Menu)]
    static void BuildFromSelection()
    {
        AnimatorController[] controllers = Selection.GetFiltered<AnimatorController>(SelectionMode.Assets);
        if (controllers.Length != 1)
        {
            EditorUtility.DisplayDialog("Directional blend tree",
                "Select the direction clips and exactly one AnimatorController.", "OK");
            return;
        }

        var skipped = new List<string>();
        List<Entry> entries = FromNames(Selection.GetFiltered<AnimationClip>(SelectionMode.Assets), skipped);
        string report = Report(controllers[0], 0, "Move", "MoveX", "MoveY", entries);
        if (skipped.Count > 0)
            report += "\nskipped      " + string.Join(", ", skipped.ToArray()) + "  (no direction token)";
        Debug.Log("[ANIM] directional blend tree — report\n" + report);

        if (report.Contains("PROBLEM"))
        {
            EditorUtility.DisplayDialog("Directional blend tree", report, "OK");
            return;
        }
        if (!EditorUtility.DisplayDialog("Directional blend tree", report, "Build", "Cancel")) return;

        BlendTree tree = Build(controllers[0], 0, "Move", "MoveX", "MoveY", entries);
        Debug.Log("[ANIM] directional blend tree — built: " + Describe(tree));
    }
}
