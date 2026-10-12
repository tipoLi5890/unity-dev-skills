// SceneCostAudit.cs — a read-only census of what the open scene asks the renderer to do,
// printed as one JSON object. It changes nothing: no component, no setting, no asset.
//
// Drop into an Editor folder. No package required; it compiles on any render pipeline.
//
//   Tools/Unity Dev/Scene Optimisation/Audit Open Scene    logs "[SCENE-COST] {json}"
//   SceneCostAudit.Audit()                                  returns the same JSON, for an eval or a test
//
// It counts what is in the scene, not what a frame draws: no camera, no culling. Use it to
// find where a counter from unity-profiling comes from, then measure the change with a window.
//
//   renderers         enabled renderers on active objects, by type
//   triangles         LOD0 triangles, in total and by layer (lower LOD levels are not added twice)
//   materials         distinct materials and shaders, how many enable GPU instancing, and the
//                     20 shaders with the most materials
//   propertyBlocks    renderers carrying a MaterialPropertyBlock: each leaves the SRP Batcher.
//                     Blocks are set at runtime — run the audit in play mode to see them.
//   staticFlags       mesh renderers and their triangle share under Batching / Occluder / Occludee Static
//   lod               LODGroup and Mesh LOD coverage by triangle share, and the 10 heaviest
//                     meshes with neither
//   shadows           lights that cast shadows, and renderers that cast them
//   textures          textures used by the scene's materials and sprites at or above
//                     LargeTextureSize that do not stream mipmaps
//   cameras           far plane, occlusion culling, per-layer cull distances
//   twoD              sprite renderers, sprites drawn as a plain quad, tilemap renderer modes
//
// Whether a shader is SRP Batcher compatible is not readable from public API. Read it on the
// shader asset's inspector ("SRP Batcher: compatible"), or per draw in the Frame Debugger —
// reference/batching.md.
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

public static class SceneCostAudit
{
    const string MenuPath = "Tools/Unity Dev/Scene Optimisation/Audit Open Scene";

    public const int LargeTextureSize = 2048;   // the longer side, in texels, at which a texture is listed
    public const int ListLimit = 20;            // rows kept in each list
    public const int HeaviestLimit = 10;

    struct Row { public string name; public long a, b; }

    [MenuItem(MenuPath)]
    static void Menu() => Debug.Log("[SCENE-COST] " + Audit());

    public static string Audit()
    {
        Scene scene = SceneManager.GetActiveScene();
        var renderers = new List<Renderer>();
        var lodGroups = new List<LODGroup>();
        var lights = new List<Light>();
        var cameras = new List<Camera>();
        foreach (GameObject root in scene.GetRootGameObjects())
        {
            // Active objects only: a pooled, inactive pickup costs nothing until it is taken.
            renderers.AddRange(root.GetComponentsInChildren<Renderer>(false));
            lodGroups.AddRange(root.GetComponentsInChildren<LODGroup>(false));
            lights.AddRange(root.GetComponentsInChildren<Light>(false));
            cameras.AddRange(root.GetComponentsInChildren<Camera>(false));
        }
        renderers.RemoveAll(r => !r.enabled);

        // Which LOD level each grouped renderer belongs to. Level 0 is the cost up close.
        var lodLevel = new Dictionary<Renderer, int>();
        foreach (LODGroup group in lodGroups)
        {
            LOD[] lods = group.GetLODs();
            for (int i = 0; i < lods.Length; i++)
                foreach (Renderer r in lods[i].renderers)
                    if (r != null && !lodLevel.ContainsKey(r)) lodLevel[r] = i;
        }

        var byType = new SortedDictionary<string, int>();
        var byLayer = new SortedDictionary<int, Row>();
        var materials = new HashSet<Material>();
        var heaviest = new List<Row>();
        var blockPaths = new List<string>();
        var tilemapModes = new SortedDictionary<string, int>();
        var shared = new List<Material>();
        var sprites = new HashSet<Sprite>();

        long total = 0, lowerLevels = 0, inGroups = 0, meshLodTris = 0;
        long batchingTris = 0, occluderTris = 0, occludeeTris = 0, meshTris = 0;
        int meshRenderers = 0, batching = 0, occluders = 0, occludees = 0, noFlags = 0;
        int blocks = 0, casters = 0, slots = 0, meshLodRenderers = 0, spriteRenderers = 0, quadSprites = 0;

        foreach (Renderer r in renderers)
        {
            string type = r.GetType().Name;
            byType.TryGetValue(type, out int n);
            byType[type] = n + 1;

            r.GetSharedMaterials(shared);
            slots += shared.Count;
            foreach (Material m in shared) if (m != null) materials.Add(m);
            if (r.HasPropertyBlock())
            {
                blocks++;
                if (blockPaths.Count < ListLimit) blockPaths.Add(PathOf(r.transform));
            }
            if (r.shadowCastingMode != ShadowCastingMode.Off) casters++;

            if (r is SpriteRenderer sr)
            {
                spriteRenderers++;
                if (sr.sprite != null)
                {
                    sprites.Add(sr.sprite);
                    // Two triangles is a quad: full-rect, or tight on an opaque rectangle.
                    if (sr.sprite.triangles.Length == 6) quadSprites++;
                }
            }
            else if (type == "TilemapRenderer")
            {
                // By reflection, so the file does not depend on the Tilemap module.
                object mode = r.GetType().GetProperty("mode")?.GetValue(r);
                string key = mode != null ? mode.ToString() : "unknown";
                tilemapModes.TryGetValue(key, out int count);
                tilemapModes[key] = count + 1;
            }

            Mesh mesh = MeshOf(r);
            if (mesh == null) continue;
            long tris = Triangles(mesh);
            bool grouped = lodLevel.TryGetValue(r, out int level);
            if (grouped && level > 0) { lowerLevels += tris; continue; }

            total += tris;
            byLayer.TryGetValue(r.gameObject.layer, out Row layer);
            layer.a++;
            layer.b += tris;
            byLayer[r.gameObject.layer] = layer;

            bool hasMeshLod = mesh.lodCount > 1;
            if (grouped) inGroups += tris;
            else if (hasMeshLod) { meshLodTris += tris; meshLodRenderers++; }
            else heaviest.Add(new Row { name = PathOf(r.transform), a = tris });

            if (!(r is MeshRenderer)) continue;
            meshRenderers++;
            meshTris += tris;
            StaticEditorFlags flags = GameObjectUtility.GetStaticEditorFlags(r.gameObject);
            bool any = false;
            if ((flags & StaticEditorFlags.BatchingStatic) != 0) { batching++; batchingTris += tris; any = true; }
            if ((flags & StaticEditorFlags.OccluderStatic) != 0) { occluders++; occluderTris += tris; any = true; }
            if ((flags & StaticEditorFlags.OccludeeStatic) != 0) { occludees++; occludeeTris += tris; any = true; }
            if (!any) noFlags++;
        }
        heaviest.Sort((x, y) => y.a.CompareTo(x.a));

        // ---- materials and shaders
        var perShader = new Dictionary<string, int>();
        int instancing = 0;
        foreach (Material m in materials)
        {
            if (m.enableInstancing) instancing++;
            string shader = m.shader != null ? m.shader.name : "(none)";
            perShader.TryGetValue(shader, out int n);
            perShader[shader] = n + 1;
        }
        var shaderRows = new List<Row>();
        foreach (KeyValuePair<string, int> kv in perShader) shaderRows.Add(new Row { name = kv.Key, a = kv.Value });
        shaderRows.Sort((x, y) => y.a.CompareTo(x.a));

        // ---- textures
        var textures = new HashSet<Texture>();
        foreach (Material m in materials)
            foreach (int id in m.GetTexturePropertyNameIDs())
            {
                Texture t = m.GetTexture(id);
                if (t != null) textures.Add(t);
            }
        foreach (Sprite s in sprites) if (s.texture != null) textures.Add(s.texture);
        var large = new List<Texture>();
        int streaming = 0;
        foreach (Texture t in textures)
        {
            bool streams = t is Texture2D t2 && t2.streamingMipmaps;
            if (streams) streaming++;
            else if (Mathf.Max(t.width, t.height) >= LargeTextureSize) large.Add(t);
        }
        large.Sort((x, y) => (y.width * y.height).CompareTo(x.width * x.height));

        // ---- write
        var sb = new StringBuilder(4096);
        sb.Append("{\"scene\":").Append(Quote(scene.path));
        sb.Append(",\"playing\":").Append(Bool(EditorApplication.isPlaying));
        RenderPipelineAsset pipeline = GraphicsSettings.currentRenderPipeline;
        sb.Append(",\"pipeline\":").Append(Quote(pipeline != null ? pipeline.GetType().Name : "built-in"));
        sb.Append(",\"srpBatcher\":").Append(Bool(pipeline != null && GraphicsSettings.useScriptableRenderPipelineBatching));
        BuildTarget target = EditorUserBuildSettings.activeBuildTarget;
        sb.Append(",\"buildTarget\":").Append(Quote(target.ToString()));
        sb.Append(",\"staticBatching\":").Append(Bool(PlayerSettings.GetStaticBatchingForPlatform(target)));
        sb.Append(",\"dynamicBatching\":").Append(Bool(PlayerSettings.GetDynamicBatchingForPlatform(target)));

        sb.Append(",\"renderers\":{\"total\":").Append(renderers.Count).Append(",\"byType\":{");
        bool first = true;
        foreach (KeyValuePair<string, int> kv in byType)
        {
            sb.Append(first ? "" : ",").Append(Quote(kv.Key)).Append(':').Append(kv.Value);
            first = false;
        }
        sb.Append("}}");

        sb.Append(",\"triangles\":{\"total\":").Append(total).Append(",\"byLayer\":[");
        first = true;
        foreach (KeyValuePair<int, Row> kv in byLayer)
        {
            sb.Append(first ? "" : ",").Append("{\"layer\":").Append(Quote(LayerName(kv.Key)));
            sb.Append(",\"renderers\":").Append(kv.Value.a).Append(",\"triangles\":").Append(kv.Value.b);
            sb.Append(",\"share\":").Append(Share(kv.Value.b, total)).Append('}');
            first = false;
        }
        sb.Append("]}");

        sb.Append(",\"materials\":{\"distinct\":").Append(materials.Count);
        sb.Append(",\"slots\":").Append(slots);
        sb.Append(",\"shaders\":").Append(perShader.Count);
        sb.Append(",\"instancingEnabled\":").Append(instancing).Append(",\"byShader\":[");
        for (int i = 0; i < shaderRows.Count && i < ListLimit; i++)
            sb.Append(i > 0 ? "," : "").Append("{\"shader\":").Append(Quote(shaderRows[i].name))
              .Append(",\"materials\":").Append(shaderRows[i].a).Append('}');
        sb.Append("]}");

        sb.Append(",\"propertyBlocks\":{\"renderers\":").Append(blocks).Append(",\"paths\":[");
        for (int i = 0; i < blockPaths.Count; i++) sb.Append(i > 0 ? "," : "").Append(Quote(blockPaths[i]));
        sb.Append("]}");

        sb.Append(",\"staticFlags\":{\"meshRenderers\":").Append(meshRenderers);
        sb.Append(",\"batching\":").Append(batching).Append(",\"batchingTriangleShare\":").Append(Share(batchingTris, meshTris));
        sb.Append(",\"occluder\":").Append(occluders).Append(",\"occluderTriangleShare\":").Append(Share(occluderTris, meshTris));
        sb.Append(",\"occludee\":").Append(occludees).Append(",\"occludeeTriangleShare\":").Append(Share(occludeeTris, meshTris));
        sb.Append(",\"none\":").Append(noFlags);
        sb.Append(",\"occlusionDataBytes\":").Append(OcclusionDataBytes(scene)).Append('}');

        sb.Append(",\"lod\":{\"groups\":").Append(lodGroups.Count);
        sb.Append(",\"lodBias\":").Append(F(QualitySettings.lodBias));
        sb.Append(",\"maximumLODLevel\":").Append(QualitySettings.maximumLODLevel);
        sb.Append(",\"groupTriangleShare\":").Append(Share(inGroups, total));
        sb.Append(",\"meshLodRenderers\":").Append(meshLodRenderers);
        sb.Append(",\"meshLodTriangleShare\":").Append(Share(meshLodTris, total));
        sb.Append(",\"lowerLevelTriangles\":").Append(lowerLevels).Append(",\"heaviestWithout\":[");
        for (int i = 0; i < heaviest.Count && i < HeaviestLimit; i++)
            sb.Append(i > 0 ? "," : "").Append("{\"path\":").Append(Quote(heaviest[i].name))
              .Append(",\"triangles\":").Append(heaviest[i].a).Append('}');
        sb.Append("]}");

        sb.Append(",\"shadows\":{\"casterRenderers\":").Append(casters).Append(",\"lights\":").Append(lights.Count).Append(",\"casting\":[");
        first = true;
        foreach (Light l in lights)
        {
            if (!l.enabled || l.shadows == LightShadows.None) continue;
            sb.Append(first ? "" : ",").Append("{\"path\":").Append(Quote(PathOf(l.transform)));
            sb.Append(",\"type\":").Append(Quote(l.type.ToString()));
            sb.Append(",\"shadows\":").Append(Quote(l.shadows.ToString())).Append('}');
            first = false;
        }
        sb.Append("]}");

        sb.Append(",\"textures\":{\"distinct\":").Append(textures.Count);
        sb.Append(",\"streaming\":").Append(streaming);
        sb.Append(",\"streamingActive\":").Append(Bool(QualitySettings.streamingMipmapsActive));
        sb.Append(",\"budgetMB\":").Append(F(QualitySettings.streamingMipmapsMemoryBudget));
        sb.Append(",\"threshold\":").Append(LargeTextureSize).Append(",\"largeNotStreaming\":[");
        for (int i = 0; i < large.Count && i < ListLimit; i++)
        {
            Texture t = large[i];
            sb.Append(i > 0 ? "," : "").Append("{\"name\":").Append(Quote(t.name));
            sb.Append(",\"asset\":").Append(Quote(AssetDatabase.GetAssetPath(t)));
            sb.Append(",\"width\":").Append(t.width).Append(",\"height\":").Append(t.height);
            sb.Append(",\"mipmaps\":").Append(t.mipmapCount).Append('}');
        }
        sb.Append("],\"largeNotStreamingCount\":").Append(large.Count).Append('}');

        sb.Append(",\"cameras\":[");
        first = true;
        foreach (Camera cam in cameras)
        {
            int layersWithDistance = 0;
            foreach (float d in cam.layerCullDistances) if (d > 0f) layersWithDistance++;
            sb.Append(first ? "" : ",").Append("{\"path\":").Append(Quote(PathOf(cam.transform)));
            sb.Append(",\"farClipPlane\":").Append(F(cam.farClipPlane));
            sb.Append(",\"occlusionCulling\":").Append(Bool(cam.useOcclusionCulling));
            sb.Append(",\"layersWithCullDistance\":").Append(layersWithDistance);
            sb.Append(",\"layerCullSpherical\":").Append(Bool(cam.layerCullSpherical)).Append('}');
            first = false;
        }
        sb.Append(']');

        sb.Append(",\"twoD\":{\"spriteRenderers\":").Append(spriteRenderers);
        sb.Append(",\"quadSprites\":").Append(quadSprites).Append(",\"tilemapModes\":{");
        first = true;
        foreach (KeyValuePair<string, int> kv in tilemapModes)
        {
            sb.Append(first ? "" : ",").Append(Quote(kv.Key)).Append(':').Append(kv.Value);
            first = false;
        }
        return sb.Append("}}}").ToString();
    }

    // ------------------------------------------------------------------ parts

    static Mesh MeshOf(Renderer r)
    {
        if (r is SkinnedMeshRenderer skinned) return skinned.sharedMesh;
        return r is MeshRenderer && r.TryGetComponent(out MeshFilter filter) ? filter.sharedMesh : null;
    }

    // The baked occlusion data file beside the scene, -1 when there is none. Its size is the
    // read-back: StaticOcclusionCulling.umbraDataSize reads 0 in batch mode.
    static long OcclusionDataBytes(Scene scene)
    {
        if (string.IsNullOrEmpty(scene.path)) return -1;
        string path = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(scene.path) ?? "",
            System.IO.Path.GetFileNameWithoutExtension(scene.path), "OcclusionCullingData.asset");
        return System.IO.File.Exists(path) ? new System.IO.FileInfo(path).Length : -1;
    }

    static long Triangles(Mesh mesh)
    {
        long indices = 0;
        for (int s = 0; s < mesh.subMeshCount; s++)
            if (mesh.GetTopology(s) == MeshTopology.Triangles) indices += mesh.GetIndexCount(s);
        return indices / 3;
    }

    static string LayerName(int layer)
    {
        string name = LayerMask.LayerToName(layer);
        return string.IsNullOrEmpty(name) ? "layer " + layer : name;
    }

    static string PathOf(Transform t)
    {
        var sb = new StringBuilder(t.name);
        for (t = t.parent; t != null; t = t.parent) sb.Insert(0, t.name + "/");
        return sb.ToString();
    }

    static string Share(long part, long whole) => whole > 0 ? F((float)((double)part / whole)) : "0";
    static string Bool(bool b) => b ? "true" : "false";
    static string F(float v) => v.ToString("0.###", CultureInfo.InvariantCulture);

    static string Quote(string s)
    {
        if (s == null) return "\"\"";
        var sb = new StringBuilder(s.Length + 2).Append('"');
        foreach (char ch in s)
        {
            if (ch == '"' || ch == '\\') sb.Append('\\').Append(ch);
            else if (ch == '\n') sb.Append("\\n");
            else if (ch == '\r') sb.Append("\\r");
            else if (ch == '\t') sb.Append("\\t");
            else if (ch < ' ') sb.Append("\\u").Append(((int)ch).ToString("x4"));
            else sb.Append(ch);
        }
        return sb.Append('"').ToString();
    }
}
