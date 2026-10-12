// Renderer2DSetup.cs — report which pipeline asset, renderer and sort axis are in force, then
// (on confirmation) create a 2D Renderer Data asset, add it to the active URP asset and make it
// the default renderer, or set the sort axis on the 2D Renderer already in force.
//
// Drop into an Editor folder. With an Editor asmdef, reference
// Unity.RenderPipelines.Universal.Runtime, Unity.RenderPipelines.Universal.2D.Runtime and
// Unity.RenderPipelines.Core.Runtime — Renderer2DData lives in the second one.
//
// REQUIRES com.unity.render-pipelines.universal (compiles against 17.3 and 17.4).
//
//   Tools/Unity Dev/2D Rendering/Report Renderer           read-only, logs one JSON object
//   Tools/Unity Dev/2D Rendering/Create 2D Renderer        flat scene: sort mode Default
//   Tools/Unity Dev/2D Rendering/Create 2D Renderer (Y-Sort)   Custom Axis (0, 1, 0)
//   Tools/Unity Dev/2D Rendering/Set Y-Sort Axis On Active 2D Renderer
//
// Every writing command reports what it would change and waits for confirmation. From an
// eval or a test fixture call Report() or Plan…() first, show the text, then Create() or
// SetSortAxis() — those do not ask.
//
// The sort mode, the sort axis and the renderer list have no public setter, so they are
// written through SerializedObject by field name. A project with no URP asset in force is not
// converted here: the report says so and nothing is created.
using System.Globalization;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

public static class Renderer2DSetup
{
    const string MenuRoot = "Tools/Unity Dev/2D Rendering/";
    const string UrpPackage = "Packages/com.unity.render-pipelines.universal";
    const string DefaultPath = "Assets/Settings/Renderer2D.asset";

    // ------------------------------------------------------------------ menu

    [MenuItem(MenuRoot + "Report Renderer")]
    static void MenuReport() { Debug.Log("[RENDERER-2D] " + Report()); }

    [MenuItem(MenuRoot + "Create 2D Renderer")]
    static void MenuCreateFlat() { MenuCreate(TransparencySortMode.Default, Vector3.up); }

    [MenuItem(MenuRoot + "Create 2D Renderer (Y-Sort)")]
    static void MenuCreateYSort() { MenuCreate(TransparencySortMode.CustomAxis, Vector3.up); }

    static void MenuCreate(TransparencySortMode mode, Vector3 axis)
    {
        string plan = PlanCreate(DefaultPath, mode, axis);
        Debug.Log("[RENDERER-2D] plan\n" + plan);
        if (ActiveAsset() == null)
        {
            EditorUtility.DisplayDialog("No URP asset in force", plan, "OK");
            return;
        }
        if (!EditorUtility.DisplayDialog("Create a 2D Renderer?", plan, "Create", "Cancel")) return;
        Renderer2DData data = Create(DefaultPath, mode, axis);
        Selection.activeObject = data;
        Debug.Log("[RENDERER-2D] " + Report());
    }

    [MenuItem(MenuRoot + "Set Y-Sort Axis On Active 2D Renderer")]
    static void MenuSetAxis()
    {
        Renderer2DData data = ActiveRenderer2D();
        string plan = PlanSetSortAxis(data, TransparencySortMode.CustomAxis, Vector3.up);
        Debug.Log("[RENDERER-2D] plan\n" + plan);
        if (data == null)
        {
            EditorUtility.DisplayDialog("No 2D Renderer in force", plan, "OK");
            return;
        }
        if (!EditorUtility.DisplayDialog("Set the sort axis?", plan, "Set", "Cancel")) return;
        SetSortAxis(data, TransparencySortMode.CustomAxis, Vector3.up);
        Debug.Log("[RENDERER-2D] " + Report());
    }

    // ------------------------------------------------------------------ read

    /// <summary>The URP asset the current quality level renders with, or null.</summary>
    public static UniversalRenderPipelineAsset ActiveAsset()
    {
        return GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
    }

    /// <summary>The default renderer of the active URP asset when it is a 2D Renderer, or null.</summary>
    public static Renderer2DData ActiveRenderer2D()
    {
        UniversalRenderPipelineAsset asset = ActiveAsset();
        if (asset == null) return null;
        var so = new SerializedObject(asset);
        SerializedProperty list = so.FindProperty("m_RendererDataList");
        int index = so.FindProperty("m_DefaultRendererIndex").intValue;
        if (list == null || index < 0 || index >= list.arraySize) return null;
        return list.GetArrayElementAtIndex(index).objectReferenceValue as Renderer2DData;
    }

    /// <summary>
    /// One JSON object: the project default, every quality level's override, the asset in
    /// force, its renderer list, and the sort mode and axis of each 2D Renderer in it.
    /// </summary>
    public static string Report()
    {
        var sb = new StringBuilder(512);
        RenderPipelineAsset current = GraphicsSettings.currentRenderPipeline;
        sb.Append("{\"projectDefault\":").Append(AssetStr(GraphicsSettings.defaultRenderPipeline))
          .Append(",\"qualityLevel\":").Append(Str(QualitySettings.names[QualitySettings.GetQualityLevel()]))
          .Append(",\"qualityOverrides\":[");
        for (int i = 0; i < QualitySettings.count; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append("{\"level\":").Append(Str(QualitySettings.names[i]))
              .Append(",\"asset\":").Append(AssetStr(QualitySettings.GetRenderPipelineAssetAt(i))).Append('}');
        }
        sb.Append("],\"inForce\":").Append(AssetStr(current))
          .Append(",\"pipeline\":").Append(Str(current == null ? "built-in" : current.GetType().Name))
          .Append(",\"renderers\":[");

        bool active2D = false;
        if (current is UniversalRenderPipelineAsset)
        {
            var so = new SerializedObject(current);
            SerializedProperty list = so.FindProperty("m_RendererDataList");
            int def = so.FindProperty("m_DefaultRendererIndex").intValue;
            for (int i = 0; list != null && i < list.arraySize; i++)
            {
                Object data = list.GetArrayElementAtIndex(i).objectReferenceValue;
                if (i > 0) sb.Append(',');
                sb.Append("{\"index\":").Append(i)
                  .Append(",\"default\":").Append(i == def ? "true" : "false")
                  .Append(",\"asset\":").Append(AssetStr(data))
                  .Append(",\"type\":").Append(Str(data != null ? data.GetType().Name : null));
                if (data is Renderer2DData)
                {
                    if (i == def) active2D = true;
                    var rso = new SerializedObject(data);
                    var mode = (TransparencySortMode)rso.FindProperty("m_TransparencySortMode").intValue;
                    sb.Append(",\"sortMode\":").Append(Str(mode.ToString()))
                      .Append(",\"sortAxis\":").Append(Vec(rso.FindProperty("m_TransparencySortAxis").vector3Value));
                }
                sb.Append('}');
            }
        }
        sb.Append("],\"renderer2DInForce\":").Append(active2D ? "true" : "false");
        if (current == null)
            sb.Append(",\"graphicsSortMode\":").Append(Str(GraphicsSettings.transparencySortMode.ToString()))
              .Append(",\"graphicsSortAxis\":").Append(Vec(GraphicsSettings.transparencySortAxis));
        return sb.Append('}').ToString();
    }

    // ------------------------------------------------------------------ plan

    public static string PlanCreate(string path, TransparencySortMode mode, Vector3 axis)
    {
        var sb = new StringBuilder();
        UniversalRenderPipelineAsset asset = ActiveAsset();
        if (asset == null)
        {
            sb.AppendLine(GraphicsSettings.currentRenderPipeline == null
                ? "The Built-in pipeline is in force: no URP asset is assigned for this quality level."
                : "The pipeline in force is " + GraphicsSettings.currentRenderPipeline.GetType().Name + ", not URP.");
            sb.AppendLine("Nothing is created. Assign a URP asset first, then run this again.");
            return sb.ToString();
        }

        Renderer2DData existing = ActiveRenderer2D();
        sb.AppendLine("URP asset in force: " + AssetDatabase.GetAssetPath(asset));
        if (existing != null)
            sb.AppendLine("Its default renderer is already a 2D Renderer: " + AssetDatabase.GetAssetPath(existing));
        sb.AppendLine("Create " + AssetDatabase.GenerateUniqueAssetPath(path) + " (Renderer2DData) with:");
        sb.AppendLine("  Transparency Sort Mode  " + mode + (mode == TransparencySortMode.CustomAxis ? "  axis " + Vec(axis) : ""));
        sb.AppendLine("  Post-process Data       the package default");
        sb.AppendLine("Append it to the asset's Renderer List and make it the default renderer.");
        sb.AppendLine("The previous default stays in the list; cameras that name a renderer by index keep theirs.");
        return sb.ToString();
    }

    public static string PlanSetSortAxis(Renderer2DData data, TransparencySortMode mode, Vector3 axis)
    {
        if (data == null)
            return "The default renderer of the URP asset in force is not a 2D Renderer. Nothing is changed.\n";
        var so = new SerializedObject(data);
        var was = (TransparencySortMode)so.FindProperty("m_TransparencySortMode").intValue;
        return AssetDatabase.GetAssetPath(data) + "\n" +
               "  Transparency Sort Mode  " + was + " -> " + mode + "\n" +
               "  Transparency Sort Axis  " + Vec(so.FindProperty("m_TransparencySortAxis").vector3Value) +
               " -> " + Vec(axis) + "\n";
    }

    // ------------------------------------------------------------------ write

    /// <summary>
    /// Creates the asset, appends it to the active URP asset's renderer list and makes it the
    /// default. Returns null, and writes nothing, when no URP asset is in force.
    /// </summary>
    public static Renderer2DData Create(string path, TransparencySortMode mode, Vector3 axis)
    {
        UniversalRenderPipelineAsset asset = ActiveAsset();
        if (asset == null) return null;

        EnsureFolder(System.IO.Path.GetDirectoryName(path).Replace('\\', '/'));
        path = AssetDatabase.GenerateUniqueAssetPath(path);

        // CreateInstance runs the asset's own Awake, which builds the four light blend styles.
        var data = ScriptableObject.CreateInstance<Renderer2DData>();
        AssetDatabase.CreateAsset(data, path);
        ResourceReloader.ReloadAllNullIn(data, UrpPackage);

        var dso = new SerializedObject(data);
        dso.FindProperty("m_PostProcessData").objectReferenceValue =
            AssetDatabase.LoadAssetAtPath<PostProcessData>(UrpPackage + "/Runtime/Data/PostProcessData.asset");
        dso.FindProperty("m_TransparencySortMode").intValue = (int)mode;
        dso.FindProperty("m_TransparencySortAxis").vector3Value = axis;
        dso.ApplyModifiedPropertiesWithoutUndo();
        EditorUtility.SetDirty(data);

        var so = new SerializedObject(asset);
        SerializedProperty list = so.FindProperty("m_RendererDataList");
        int index = list.arraySize;
        list.InsertArrayElementAtIndex(index);
        list.GetArrayElementAtIndex(index).objectReferenceValue = data;
        so.FindProperty("m_DefaultRendererIndex").intValue = index;
        so.ApplyModifiedProperties();
        EditorUtility.SetDirty(asset);
        AssetDatabase.SaveAssets();
        return data;
    }

    /// <summary>Writes the sort mode and axis on a 2D Renderer Data asset.</summary>
    public static void SetSortAxis(Renderer2DData data, TransparencySortMode mode, Vector3 axis)
    {
        if (data == null) return;
        var so = new SerializedObject(data);
        so.FindProperty("m_TransparencySortMode").intValue = (int)mode;
        so.FindProperty("m_TransparencySortAxis").vector3Value = axis;
        so.ApplyModifiedProperties();
        EditorUtility.SetDirty(data);
        AssetDatabase.SaveAssets();
    }

    static void EnsureFolder(string folder)
    {
        if (string.IsNullOrEmpty(folder) || AssetDatabase.IsValidFolder(folder)) return;
        int slash = folder.LastIndexOf('/');
        string parent = slash > 0 ? folder.Substring(0, slash) : "Assets";
        EnsureFolder(parent);
        AssetDatabase.CreateFolder(parent, folder.Substring(slash + 1));
    }

    // ------------------------------------------------------------------ text

    static string AssetStr(Object o) => Str(o != null ? AssetDatabase.GetAssetPath(o) : null);

    static string Num(float v) => v.ToString("0.###", CultureInfo.InvariantCulture);

    static string Vec(Vector3 v) => "[" + Num(v.x) + "," + Num(v.y) + "," + Num(v.z) + "]";

    static string Str(string s)
    {
        if (s == null) return "null";
        return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
    }
}
