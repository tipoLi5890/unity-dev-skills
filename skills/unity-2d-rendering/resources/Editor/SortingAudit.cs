// SortingAudit.cs — every renderer in the open scenes with the keys that decide its draw
// order, and the pairs that tie on all of them, as one JSON object. Reads only.
//
// Drop into an Editor folder. Menu: Tools/Unity Dev/2D Rendering/Audit Sorting.
// From `unity command eval`:
//
//   return SortingAudit.Json();
//
// REQUIRES the built-in Tilemap module (com.unity.modules.tilemap). No render-pipeline
// assembly is referenced: the renderer asset is read through SerializedObject, so the file
// compiles on the Built-in pipeline, on URP with the Universal Renderer and on the 2D Renderer.
//
// Per renderer:
//   layer / layerValue   sorting layer name and its position in the layer list (key 1)
//   order                Order in Layer (key 2)
//   queue                the material's render queue (key 3)
//   distance             along the sort axis in force, larger draws first (key 4)
//   sortPoint            Pivot · Center · Bounds (not a sprite) · GroupRoot (inside a SortingGroup)
//   group                the outermost SortingGroup that sorts this renderer as part of a unit
//   lit                  lit · unlit · built-in · other — whether a Light2D can change it.
//                        Read from the shader's pass tags: a NormalsRendering pass is lit, a
//                        Universal2D pass alone is unlit, a Sprites/ shader is built-in, and
//                        a shader with neither pass (a 3D material on a mesh) is other.
//
// ties[] lists pairs whose bounds overlap in x/y and whose four keys are equal: their order
// is not defined and can change between frames. Give one of the pair a different key.
//
// Assumptions: the camera looks along +z (the 2D default); a SortingGroup is measured at its
// root Transform; a TilemapRenderer is measured at its bounds centre, which is exact for
// neither Chunk nor Individual mode — read its `tilemapMode` and reference/sort-order.md.
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.Tilemaps;

public static class SortingAudit
{
    const string Menu = "Tools/Unity Dev/2D Rendering/Audit Sorting";
    const float Epsilon = 1e-4f;
    const int MaxPairRenderers = 1500;
    const int MaxTies = 200;

    static readonly ShaderTagId LightModeTag = new ShaderTagId("LightMode");
    static readonly ShaderTagId NormalsTag = new ShaderTagId("NormalsRendering");
    static readonly ShaderTagId Universal2DTag = new ShaderTagId("Universal2D");

    static int s_NextId;

    // One thing the sorter compares: a SortingGroup, or a renderer.
    sealed class Unit
    {
        public int id;
        public string path;
        public int layerValue;
        public int order;
        public int queue;      // -1 for a group: a group has no material
        public float distance;
    }

    sealed class Row
    {
        public Renderer renderer;
        public List<Unit> chain = new List<Unit>(2); // outermost group first, the renderer last
        public Rect rect;
    }

    struct SortSetup
    {
        public string pipeline, rendererData, rendererType, source;
        public bool is2DRenderer;
        public TransparencySortMode mode;
        public Vector3 axis;
        public Camera camera;
    }

    [MenuItem(Menu)]
    static void Run() { Debug.Log("[SORT] " + Json()); }

    /// <summary>The audit of every loaded scene as one JSON object on one line.</summary>
    public static string Json()
    {
        Camera cam = FindCamera();
        SortSetup setup = ReadSetup(cam);

        var rows = new List<Row>();
        var units = new Dictionary<SortingGroup, Unit>();
        int light2D = 0, masks = 0;
        s_NextId = 1;
        for (int s = 0; s < SceneManager.sceneCount; s++)
        {
            Scene scene = SceneManager.GetSceneAt(s);
            if (!scene.isLoaded) continue;
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                foreach (Renderer r in root.GetComponentsInChildren<Renderer>(false))
                {
                    if (!r.enabled) continue;
                    // A SpriteMask is a Renderer that draws no colour; it is counted, not sorted.
                    if (r.GetType().Name == "SpriteMask") { masks++; continue; }
                    rows.Add(BuildRow(r, setup, units));
                }
                foreach (Behaviour b in root.GetComponentsInChildren<Behaviour>(false))
                    if (b != null && b.enabled && b.GetType().Name == "Light2D") light2D++;
            }
        }

        var sb = new StringBuilder(4096);
        sb.Append("{\"pipeline\":").Append(Str(setup.pipeline))
          .Append(",\"rendererData\":").Append(Str(setup.rendererData))
          .Append(",\"rendererType\":").Append(Str(setup.rendererType))
          .Append(",\"is2DRenderer\":").Append(setup.is2DRenderer ? "true" : "false")
          .Append(",\"sortMode\":").Append(Str(setup.mode.ToString()))
          .Append(",\"sortAxis\":").Append(Vec(setup.axis))
          .Append(",\"sortSource\":").Append(Str(setup.source))
          .Append(",\"camera\":").Append(Str(cam != null ? cam.name : null))
          .Append(",\"orthographic\":").Append(cam != null && cam.orthographic ? "true" : "false")
          .Append(",\"light2DCount\":").Append(light2D)
          .Append(",\"spriteMaskCount\":").Append(masks)
          .Append(",\"renderers\":[");

        for (int i = 0; i < rows.Count; i++)
        {
            if (i > 0) sb.Append(',');
            AppendRow(sb, rows[i]);
        }
        sb.Append("],\"ties\":[");

        int ties = 0;
        bool skipped = rows.Count > MaxPairRenderers;
        if (!skipped)
        {
            var seen = new HashSet<long>();
            for (int a = 0; a < rows.Count && ties < MaxTies; a++)
            for (int b = a + 1; b < rows.Count && ties < MaxTies; b++)
            {
                if (!rows[a].rect.Overlaps(rows[b].rect)) continue;
                if (!Tie(rows[a], rows[b], out Unit ua, out Unit ub)) continue;
                long key = ((long)Mathf.Min(ua.id, ub.id) << 32) ^ (uint)Mathf.Max(ua.id, ub.id);
                if (!seen.Add(key)) continue;
                if (ties++ > 0) sb.Append(',');
                sb.Append("{\"a\":").Append(Str(ua.path)).Append(",\"b\":").Append(Str(ub.path))
                  .Append(",\"layerValue\":").Append(ua.layerValue)
                  .Append(",\"order\":").Append(ua.order)
                  .Append(",\"distance\":").Append(Num(ua.distance)).Append('}');
            }
        }
        sb.Append("],\"tiesTruncated\":").Append(ties >= MaxTies ? "true" : "false")
          .Append(",\"tiesSkipped\":").Append(skipped ? "true" : "false")
          .Append(",\"warnings\":[");
        AppendWarnings(sb, setup, rows, light2D);
        sb.Append("]}");
        return sb.ToString();
    }

    // ------------------------------------------------------------------ setup

    static Camera FindCamera()
    {
        if (Camera.main != null) return Camera.main;
        for (int s = 0; s < SceneManager.sceneCount; s++)
        {
            Scene scene = SceneManager.GetSceneAt(s);
            if (!scene.isLoaded) continue;
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                Camera c = root.GetComponentInChildren<Camera>(false);
                if (c != null) return c;
            }
        }
        return null;
    }

    static SortSetup ReadSetup(Camera cam)
    {
        var setup = new SortSetup { camera = cam, axis = Vector3.forward };
        RenderPipelineAsset asset = GraphicsSettings.currentRenderPipeline;
        if (asset == null)
        {
            // Built-in: the camera carries the pair, seeded from Project Settings > Graphics.
            setup.pipeline = "built-in";
            setup.mode = cam != null ? cam.transparencySortMode : GraphicsSettings.transparencySortMode;
            setup.axis = cam != null ? cam.transparencySortAxis : GraphicsSettings.transparencySortAxis;
            setup.source = cam != null ? "Camera.transparencySortMode" : "GraphicsSettings.transparencySortMode";
            return setup;
        }

        setup.pipeline = AssetDatabase.GetAssetPath(asset);
        var so = new SerializedObject(asset);
        SerializedProperty list = so.FindProperty("m_RendererDataList");
        SerializedProperty def = so.FindProperty("m_DefaultRendererIndex");
        int index = def != null ? def.intValue : 0;

        // A camera can pick another entry of the list; -1 means the default.
        if (cam != null)
        {
            Component extra = cam.GetComponent("UniversalAdditionalCameraData");
            if (extra != null)
            {
                SerializedProperty ri = new SerializedObject(extra).FindProperty("m_RendererIndex");
                if (ri != null && ri.intValue >= 0) index = ri.intValue;
            }
        }

        Object data = list != null && list.isArray && index < list.arraySize
            ? list.GetArrayElementAtIndex(index).objectReferenceValue : null;
        if (data == null)
        {
            setup.source = "no renderer data at index " + index;
            setup.mode = cam != null ? cam.transparencySortMode : TransparencySortMode.Default;
            if (cam != null) setup.axis = cam.transparencySortAxis;
            return setup;
        }

        setup.rendererData = AssetDatabase.GetAssetPath(data);
        setup.rendererType = data.GetType().Name;
        setup.is2DRenderer = setup.rendererType == "Renderer2DData";
        if (setup.is2DRenderer)
        {
            var rso = new SerializedObject(data);
            SerializedProperty mode = rso.FindProperty("m_TransparencySortMode");
            SerializedProperty axis = rso.FindProperty("m_TransparencySortAxis");
            setup.mode = mode != null ? (TransparencySortMode)mode.intValue : TransparencySortMode.Default;
            setup.axis = axis != null ? axis.vector3Value : Vector3.up;
            setup.source = "Renderer2DData";
        }
        else
        {
            setup.mode = cam != null ? cam.transparencySortMode : TransparencySortMode.Default;
            if (cam != null) setup.axis = cam.transparencySortAxis;
            setup.source = "Camera.transparencySortMode";
        }
        return setup;
    }

    // Larger means further back, which draws first.
    static float Distance(Vector3 point, SortSetup setup)
    {
        Camera cam = setup.camera;
        TransparencySortMode mode = setup.mode;
        if (mode == TransparencySortMode.Default)
            mode = cam == null || cam.orthographic ? TransparencySortMode.Orthographic : TransparencySortMode.Perspective;
        switch (mode)
        {
            case TransparencySortMode.CustomAxis:
                return Vector3.Dot(point, setup.axis);
            case TransparencySortMode.Perspective:
                return cam != null ? (point - cam.transform.position).magnitude : point.z;
            default:
                return cam != null ? Vector3.Dot(point - cam.transform.position, cam.transform.forward) : point.z;
        }
    }

    // ------------------------------------------------------------------ rows

    static Row BuildRow(Renderer r, SortSetup setup, Dictionary<SortingGroup, Unit> units)
    {
        var row = new Row { renderer = r };
        Bounds b = r.bounds;
        row.rect = Rect.MinMaxRect(b.min.x, b.min.y, b.max.x, b.max.y);

        // Groups that sort this renderer, outermost first. sortAtRoot cuts the chain above it.
        var groups = new List<SortingGroup>(2);
        for (Transform t = r.transform; t != null; t = t.parent)
        {
            if (!t.TryGetComponent(out SortingGroup g) || !g.enabled) continue;
            groups.Add(g);
            if (g.sortAtRoot) break;
        }
        for (int i = groups.Count - 1; i >= 0; i--)
        {
            SortingGroup g = groups[i];
            if (!units.TryGetValue(g, out Unit gu))
            {
                gu = new Unit
                {
                    id = s_NextId++, path = Path(g.transform),
                    layerValue = SortingLayer.GetLayerValueFromID(g.sortingLayerID),
                    order = g.sortingOrder, queue = -1,
                    distance = Distance(g.transform.position, setup),
                };
                units[g] = gu;
            }
            row.chain.Add(gu);
        }

        Material m = r.sharedMaterial;
        row.chain.Add(new Unit
        {
            id = s_NextId++, path = Path(r.transform),
            layerValue = SortingLayer.GetLayerValueFromID(r.sortingLayerID),
            order = r.sortingOrder, queue = m != null ? m.renderQueue : -1,
            distance = Distance(SortPoint(r), setup),
        });
        return row;
    }

    static Vector3 SortPoint(Renderer r)
    {
        if (r is SpriteRenderer sr && sr.spriteSortPoint == SpriteSortPoint.Pivot) return r.transform.position;
        return r.bounds.center;
    }

    static string SortPointName(Row row)
    {
        if (row.chain.Count > 1) return "GroupRoot";
        if (row.renderer is SpriteRenderer sr) return sr.spriteSortPoint.ToString();
        return "Bounds";
    }

    // Walk both chains from the outside in; the first unit that is not shared decides.
    static bool Tie(Row a, Row b, out Unit ua, out Unit ub)
    {
        ua = ub = null;
        int depth = 0;
        while (depth < a.chain.Count && depth < b.chain.Count && a.chain[depth].id == b.chain[depth].id) depth++;
        if (depth >= a.chain.Count || depth >= b.chain.Count) return false;
        ua = a.chain[depth];
        ub = b.chain[depth];
        if (ua.layerValue != ub.layerValue || ua.order != ub.order) return false;
        if (ua.queue >= 0 && ub.queue >= 0 && ua.queue != ub.queue) return false;
        return Mathf.Abs(ua.distance - ub.distance) <= Epsilon;
    }

    static string Lit(Material m)
    {
        if (m == null || m.shader == null) return "other";
        Shader shader = m.shader;
        if (shader.name.StartsWith("Sprites/")) return "built-in";
        // Every lit 2D shader, hand-written or Shader Graph, carries a pass tagged
        // LightMode = NormalsRendering; the unlit ones have only the Universal2D pass.
        bool draws2D = false;
        for (int i = 0; i < shader.passCount; i++)
        {
            ShaderTagId mode = shader.FindPassTagValue(i, LightModeTag);
            if (mode == NormalsTag) return "lit";
            if (mode == Universal2DTag) draws2D = true;
        }
        return draws2D ? "unlit" : "other";
    }

    static void AppendRow(StringBuilder sb, Row row)
    {
        Renderer r = row.renderer;
        Unit u = row.chain[row.chain.Count - 1];
        Material m = r.sharedMaterial;
        sb.Append("{\"path\":").Append(Str(u.path))
          .Append(",\"type\":").Append(Str(r.GetType().Name))
          .Append(",\"layer\":").Append(Str(r.sortingLayerName))
          .Append(",\"layerValue\":").Append(u.layerValue)
          .Append(",\"order\":").Append(u.order)
          .Append(",\"queue\":").Append(u.queue)
          .Append(",\"distance\":").Append(Num(u.distance))
          .Append(",\"sortPoint\":").Append(Str(SortPointName(row)))
          .Append(",\"group\":").Append(Str(row.chain.Count > 1 ? row.chain[0].path : null))
          .Append(",\"groupDepth\":").Append(row.chain.Count - 1)
          .Append(",\"shader\":").Append(Str(m != null && m.shader != null ? m.shader.name : null))
          .Append(",\"lit\":").Append(Str(Lit(m)));
        if (r is TilemapRenderer tr)
            sb.Append(",\"tilemapMode\":").Append(Str(tr.mode.ToString()))
              .Append(",\"tilemapSortOrder\":").Append(Str(tr.sortOrder.ToString()));
        sb.Append('}');
    }

    static void AppendWarnings(StringBuilder sb, SortSetup setup, List<Row> rows, int light2D)
    {
        var w = new List<string>();
        int lit = 0, unlit = 0, builtIn = 0;
        foreach (Row row in rows)
        {
            switch (Lit(row.renderer.sharedMaterial))
            {
                case "lit": lit++; break;
                case "unlit": unlit++; break;
                case "built-in": builtIn++; break;
            }
        }
        if (setup.camera == null) w.Add("no camera in the open scenes: distances use world z");
        if (light2D > 0 && !setup.is2DRenderer)
            w.Add(light2D + " Light2D in the scene and the renderer in force is not a 2D Renderer: they light nothing");
        if (light2D > 0 && lit == 0)
            w.Add("no renderer uses a lit 2D material: no Light2D can change the picture");
        if (light2D == 0 && lit > 0 && setup.is2DRenderer)
            w.Add("no Light2D in the scene: lit materials draw at full colour until the first light is added");
        if (builtIn > 0 && setup.pipeline != "built-in")
            w.Add(builtIn + " renderer(s) on a Built-in Sprites/ shader under a scriptable pipeline");
        if (setup.is2DRenderer && setup.camera != null &&
            (setup.camera.transparencySortMode != TransparencySortMode.Default))
            w.Add("Camera.transparencySortMode is set and ignored: the 2D Renderer reads the Renderer2DData asset");
        for (int i = 0; i < w.Count; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append(Str(w[i]));
        }
    }

    // ------------------------------------------------------------------ text

    static string Path(Transform t)
    {
        var sb = new StringBuilder(t.name);
        for (Transform p = t.parent; p != null; p = p.parent) sb.Insert(0, p.name + "/");
        return sb.ToString();
    }

    static string Num(float v) => v.ToString("0.####", CultureInfo.InvariantCulture);

    static string Vec(Vector3 v) => "[" + Num(v.x) + "," + Num(v.y) + "," + Num(v.z) + "]";

    static string Str(string s)
    {
        if (s == null) return "null";
        var sb = new StringBuilder(s.Length + 2).Append('"');
        foreach (char c in s)
        {
            if (c == '"' || c == '\\') sb.Append('\\').Append(c);
            else if (c < ' ') sb.Append(' ');
            else sb.Append(c);
        }
        return sb.Append('"').ToString();
    }
}
