// LodGroupBuilder.cs — builds a LODGroup on a prefab or a scene object from child renderers
// whose GameObject names end in _LOD0, _LOD1 … _LODn, with screen heights from one rule.
//
// Drop into an Editor folder. No package required.
//
//   Tools/Unity Dev/Scene Optimisation/Build LODGroup From Children               select the root
//   Tools/Unity Dev/Scene Optimisation/Build LODGroup From Children (Cross-Fade)  the same, dithered
//
// The command reports what it would write and waits for confirmation. From an eval or a test
// fixture, call Plan(root) first, show the text, then call Build(root) — Build does not ask.
//
// The selection is a prefab asset in the Project window, the root open in Prefab Mode, or a
// scene object. An imported model is refused: the model importer already builds a LODGroup
// from the same names, so a model that arrives without one has its meshes named differently.
//
// Screen heights (reference/lod.md): LOD0 hands over at 0.5 of the screen height, each later
// level at 0.4 of the one before, and the last level is culled below 0.01.
//
//   levels   hand-over heights
//   1        cull 0.01
//   2        0.5 · cull 0.01
//   3        0.5 · 0.2 · cull 0.01
//   4        0.5 · 0.2 · 0.08 · cull 0.01
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class LodGroupBuilder
{
    const string MenuRoot = "Tools/Unity Dev/Scene Optimisation/";

    public const float FirstTransition = 0.5f;    // LOD0 is drawn above half the screen height
    public const float TransitionRatio = 0.4f;    // each later hand-over, as a share of the one before
    public const float CullHeight = 0.01f;        // about 11 px at 1080p: below it nothing is drawn
    public const float CrossFadeWidth = 0.1f;     // the share of a level's range spent blending
    public const float ExpectedReduction = 0.5f;  // a level worth having halves the triangles

    static readonly Regex LodSuffix = new Regex(@"_LOD(\d+)$", RegexOptions.IgnoreCase);

    // ------------------------------------------------------------------ menu

    [MenuItem(MenuRoot + "Build LODGroup From Children")]
    static void MenuBuild() => Run(false);

    [MenuItem(MenuRoot + "Build LODGroup From Children (Cross-Fade)")]
    static void MenuBuildCrossFade() => Run(true);

    static void Run(bool crossFade)
    {
        GameObject root = Selection.activeGameObject;
        string plan = Plan(root, crossFade);
        Debug.Log("[LOD-BUILD] plan\n" + plan);
        if (!CanBuild(root)) { EditorUtility.DisplayDialog("Build LODGroup", plan, "OK"); return; }
        if (!EditorUtility.DisplayDialog("Build LODGroup?", plan, "Create", "Cancel")) return;
        Build(root, crossFade);
    }

    // ------------------------------------------------------------------ plan

    public static float[] Heights(int levels)
    {
        var heights = new float[levels];
        float h = FirstTransition;
        for (int i = 0; i < levels - 1; i++, h *= TransitionRatio) heights[i] = h;
        if (levels > 0) heights[levels - 1] = CullHeight;
        return heights;
    }

    public static bool CanBuild(GameObject root) => Refusal(root, Collect(root)) == null;

    public static string Plan(GameObject root, bool crossFade = false)
    {
        var sb = new StringBuilder();
        List<List<Renderer>> levels = Collect(root);
        string refusal = Refusal(root, levels);
        if (refusal != null) return sb.Append("Nothing to build: ").Append(refusal).ToString();

        float[] heights = Heights(levels.Count);
        bool isAsset = PrefabUtility.IsPartOfPrefabAsset(root);
        sb.AppendLine((isAsset ? "Prefab asset: " + AssetDatabase.GetAssetPath(root) : "Object: " + root.name) +
                      (root.TryGetComponent(out LODGroup _) ? " — replace the LODs of its LODGroup" : " — add a LODGroup"));
        sb.AppendLine("Fade mode: " + (crossFade
            ? "CrossFade, animated, width " + F(CrossFadeWidth) + " (the shader must support LOD_FADE_CROSSFADE)"
            : "None"));

        int previous = 0;
        for (int i = 0; i < levels.Count; i++)
        {
            int tris = 0;
            foreach (Renderer r in levels[i]) tris += Triangles(r);
            sb.Append("  LOD").Append(i).Append("  ").Append(levels[i].Count).Append(" renderer(s), ")
              .Append(tris).Append(" triangles, drawn above ").Append(F(heights[i]));
            if (i > 0 && previous > 0 && tris > previous * ExpectedReduction)
                sb.Append("  — more than ").Append(F(ExpectedReduction)).Append(" of LOD").Append(i - 1)
                  .Append(": the swap costs a pop and saves little");
            sb.AppendLine();
            previous = tris;
        }
        sb.AppendLine("  culled below " + F(CullHeight));

        int strays = 0;
        for (int i = 1; i < levels.Count; i++)
            foreach (Renderer r in levels[i])
                if (r.GetComponent<Collider>() != null) strays++;
        if (strays > 0)
            sb.AppendLine(strays + " collider(s) sit on LOD1+ children. A LODGroup switches renderers only: " +
                          "keep one collider on the root and delete these.");
        return sb.ToString();
    }

    // ------------------------------------------------------------------ build

    public static LODGroup Build(GameObject root, bool crossFade = false)
    {
        string refusal = Refusal(root, Collect(root));
        if (refusal != null) { Debug.LogError("[LOD-BUILD] " + refusal); return null; }

        if (!PrefabUtility.IsPartOfPrefabAsset(root))
        {
            LODGroup group = Apply(root, crossFade, true);
            EditorUtility.SetDirty(group);
            if (root.scene.IsValid()) EditorSceneManager.MarkSceneDirty(root.scene);
            return Log(group, root.name);
        }

        // A prefab asset is edited through its contents and saved back: writing to the asset's
        // own objects is not persisted.
        string path = AssetDatabase.GetAssetPath(root);
        GameObject contents = PrefabUtility.LoadPrefabContents(path);
        try
        {
            Log(Apply(contents, crossFade, false), path);
            PrefabUtility.SaveAsPrefabAsset(contents, path);
        }
        finally { PrefabUtility.UnloadPrefabContents(contents); }
        return AssetDatabase.LoadAssetAtPath<GameObject>(path).GetComponent<LODGroup>();
    }

    static LODGroup Apply(GameObject root, bool crossFade, bool undo)
    {
        List<List<Renderer>> levels = Collect(root);
        float[] heights = Heights(levels.Count);
        if (!root.TryGetComponent(out LODGroup group))
            group = undo ? Undo.AddComponent<LODGroup>(root) : root.AddComponent<LODGroup>();
        else if (undo) Undo.RecordObject(group, "Build LODGroup");

        var lods = new LOD[levels.Count];
        for (int i = 0; i < lods.Length; i++)
        {
            lods[i] = new LOD(heights[i], levels[i].ToArray());
            lods[i].fadeTransitionWidth = crossFade ? CrossFadeWidth : 0f;
        }
        group.fadeMode = crossFade ? LODFadeMode.CrossFade : LODFadeMode.None;
        group.animateCrossFading = crossFade;
        group.SetLODs(lods);
        group.RecalculateBounds();
        return group;
    }

    static LODGroup Log(LODGroup group, string where)
    {
        LOD[] lods = group.GetLODs();
        var sb = new StringBuilder("[LOD-BUILD] wrote " + where + " levels=" + lods.Length + " heights=");
        for (int i = 0; i < lods.Length; i++) sb.Append(i > 0 ? "/" : "").Append(F(lods[i].screenRelativeTransitionHeight));
        Debug.Log(sb.Append(" size=").Append(F(group.size)).Append(" fade=").Append(group.fadeMode).ToString());
        return group;
    }

    // ------------------------------------------------------------------ parts

    // levels[i] holds every renderer under root whose GameObject name ends in _LODi.
    static List<List<Renderer>> Collect(GameObject root)
    {
        var levels = new List<List<Renderer>>();
        if (root == null) return levels;
        foreach (Renderer r in root.GetComponentsInChildren<Renderer>(true))
        {
            Match m = LodSuffix.Match(r.gameObject.name);
            if (!m.Success || !int.TryParse(m.Groups[1].Value, out int index) || index > 7) continue;
            while (levels.Count <= index) levels.Add(new List<Renderer>());
            levels[index].Add(r);
        }
        return levels;
    }

    static string Refusal(GameObject root, List<List<Renderer>> levels)
    {
        if (root == null) return "select the prefab or the object that holds the _LOD0 … _LODn children.";
        if (PrefabUtility.GetPrefabAssetType(root) == PrefabAssetType.Model && PrefabUtility.IsPartOfPrefabAsset(root))
            return "'" + root.name + "' is an imported model and cannot be saved. The importer builds the LODGroup " +
                   "itself when the meshes are named _LOD0 … _LODn; otherwise make a prefab variant and run this on it.";
        if (levels.Count == 0) return "no renderer under '" + root.name + "' has a name ending in _LOD0, _LOD1 …";
        for (int i = 0; i < levels.Count; i++)
            if (levels[i].Count == 0)
                return "_LOD" + i + " is missing under '" + root.name + "': levels must run from 0 with no gap.";
        return null;
    }

    static int Triangles(Renderer r)
    {
        Mesh mesh = null;
        if (r is SkinnedMeshRenderer skinned) mesh = skinned.sharedMesh;
        else if (r.TryGetComponent(out MeshFilter filter)) mesh = filter.sharedMesh;
        if (mesh == null) return 0;
        long indices = 0;
        for (int s = 0; s < mesh.subMeshCount; s++)
            if (mesh.GetTopology(s) == MeshTopology.Triangles) indices += mesh.GetIndexCount(s);
        return (int)(indices / 3);
    }

    static string F(float v) => v.ToString("0.###", CultureInfo.InvariantCulture);
}
