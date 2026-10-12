// OcclusionBake.cs — reports what a baked occlusion-culling pass would work on, bakes it
// after confirmation, and reads the result back as one JSON object.
//
// Drop into an Editor folder. No package required.
//
//   Tools/Unity Dev/Scene Optimisation/Bake Occlusion         plan, confirm, bake, log "[OCCLUSION-BAKE] {json}"
//   Tools/Unity Dev/Scene Optimisation/Clear Occlusion Data   confirm, then clear
//   OcclusionBake.Plan()                                      the report alone; changes nothing
//   OcclusionBake.Bake(5f, 0.25f, 100f)                       bakes without asking; returns the JSON
//
// The menu bakes with the scene's current settings. Bake() takes the three settings as
// arguments; their defaults are Unity's own (reference/occlusion.md).
//
// The bake is synchronous and writes OcclusionCullingData.asset in a folder named after the
// scene, beside the scene file. The scene must be saved first. Unity publishes no cell count,
// and StaticOcclusionCulling.umbraDataSize reads 0 in batch mode even after a good bake, so the
// read-back is the data file: `bytes` is its size on disk and `written` says the bake rewrote
// it. With no renderer flagged Occluder Static the bake is refused, because its result would
// hide nothing.
using System.Globalization;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

public static class OcclusionBake
{
    const string MenuRoot = "Tools/Unity Dev/Scene Optimisation/";

    public const float DefaultSmallestOccluder = 5f;      // metres: nothing smaller hides anything
    public const float DefaultSmallestHole = 0.25f;       // metres: the narrowest gap the camera sees through
    public const float DefaultBackfaceThreshold = 100f;   // 100 keeps every cell; lower trims the data

    struct Census
    {
        public int renderers, occluders, occludees, dynamicOccludees, areas, portals, camerasCulling, cameras;
    }

    // ------------------------------------------------------------------ menu

    [MenuItem(MenuRoot + "Bake Occlusion")]
    static void MenuBake()
    {
        string plan = Plan();
        Debug.Log("[OCCLUSION-BAKE] plan\n" + plan);
        if (Refusal() != null) { EditorUtility.DisplayDialog("Bake occlusion", plan, "OK"); return; }
        if (!EditorUtility.DisplayDialog("Bake occlusion?", plan, "Bake", "Cancel")) return;
        Debug.Log("[OCCLUSION-BAKE] " + Bake(StaticOcclusionCulling.smallestOccluder,
                                             StaticOcclusionCulling.smallestHole,
                                             StaticOcclusionCulling.backfaceThreshold));
    }

    [MenuItem(MenuRoot + "Clear Occlusion Data")]
    static void MenuClear()
    {
        Scene scene = SceneManager.GetActiveScene();
        string message = "Clear the baked occlusion data of '" + scene.name + "' (" + FileBytes(scene) + " bytes on disk)?";
        if (!EditorUtility.DisplayDialog("Clear occlusion data?", message, "Clear", "Cancel")) return;
        StaticOcclusionCulling.Clear();
        EditorSceneManager.MarkSceneDirty(scene);
        Debug.Log("[OCCLUSION-BAKE] cleared; save the scene to drop its reference to the data");
    }

    // ------------------------------------------------------------------ plan

    public static string Plan()
    {
        Scene scene = SceneManager.GetActiveScene();
        Census c = Count(scene);
        var sb = new StringBuilder();
        sb.AppendLine("Scene: " + (string.IsNullOrEmpty(scene.path) ? scene.name + " (not saved)" : scene.path));
        sb.AppendLine("Settings: smallest occluder " + F(StaticOcclusionCulling.smallestOccluder) +
                      ", smallest hole " + F(StaticOcclusionCulling.smallestHole) +
                      ", backface threshold " + F(StaticOcclusionCulling.backfaceThreshold));
        sb.AppendLine("Renderers: " + c.renderers + " — Occluder Static " + c.occluders +
                      ", Occludee Static " + c.occludees + ", dynamic occludees " + c.dynamicOccludees);
        sb.AppendLine("Occlusion Areas: " + c.areas + (c.areas == 0 ? " (the view volume is the bounds of the static geometry)" : "") +
                      " · Occlusion Portals: " + c.portals);
        sb.AppendLine("Cameras with occlusion culling on: " + c.camerasCulling + " of " + c.cameras);
        long onDisk = FileBytes(scene);
        sb.AppendLine("Baked data now: " + (onDisk < 0 ? "none" : onDisk + " bytes in " + DataPath(scene)));

        string refusal = Refusal();
        if (refusal != null) return sb.Append("Nothing to bake: ").Append(refusal).ToString();
        if (c.camerasCulling == 0) sb.AppendLine("No camera uses the result: turn Occlusion Culling on on the game camera.");
        sb.Append("Bake writes ").Append(DataPath(scene)).Append(" and marks the scene dirty.");
        return sb.ToString();
    }

    static string Refusal()
    {
        Scene scene = SceneManager.GetActiveScene();
        if (string.IsNullOrEmpty(scene.path)) return "save the scene first; the data is stored beside it.";
        if (EditorApplication.isPlayingOrWillChangePlaymode) return "leave play mode first.";
        if (StaticOcclusionCulling.isRunning) return "a bake is already running.";
        if (Count(scene).occluders == 0)
            return "no renderer has the Occluder Static flag, so nothing can hide anything. " +
                   "Flag the walls, floors and large solid props, then run this again.";
        return null;
    }

    // ------------------------------------------------------------------ bake

    public static string Bake(float smallestOccluder = DefaultSmallestOccluder,
                              float smallestHole = DefaultSmallestHole,
                              float backfaceThreshold = DefaultBackfaceThreshold)
    {
        Scene scene = SceneManager.GetActiveScene();
        string refusal = Refusal();
        if (refusal != null) return Json(scene, false, refusal, FileBytes(scene), 0, Count(scene));

        long before = FileBytes(scene);
        long started = System.DateTime.UtcNow.Ticks;
        StaticOcclusionCulling.smallestOccluder = smallestOccluder;
        StaticOcclusionCulling.smallestHole = smallestHole;
        StaticOcclusionCulling.backfaceThreshold = backfaceThreshold;

        bool ok = StaticOcclusionCulling.Compute();
        EditorSceneManager.MarkSceneDirty(scene);
        return Json(scene, ok, ok ? null : "StaticOcclusionCulling.Compute returned false; read the console", before, started, Count(scene));
    }

    // ------------------------------------------------------------------ parts

    static Census Count(Scene scene)
    {
        var c = new Census();
        foreach (GameObject root in scene.GetRootGameObjects())
        {
            foreach (Renderer r in root.GetComponentsInChildren<Renderer>(false))
            {
                if (!r.enabled) continue;
                c.renderers++;
                StaticEditorFlags flags = GameObjectUtility.GetStaticEditorFlags(r.gameObject);
                bool occludee = (flags & StaticEditorFlags.OccludeeStatic) != 0;
                if ((flags & StaticEditorFlags.OccluderStatic) != 0) c.occluders++;
                if (occludee) c.occludees++;
                else if (r.allowOcclusionWhenDynamic) c.dynamicOccludees++;
            }
            c.areas += root.GetComponentsInChildren<OcclusionArea>(false).Length;
            c.portals += root.GetComponentsInChildren<OcclusionPortal>(false).Length;
            foreach (Camera cam in root.GetComponentsInChildren<Camera>(false))
            {
                c.cameras++;
                if (cam.useOcclusionCulling) c.camerasCulling++;
            }
        }
        return c;
    }

    static string DataPath(Scene scene)
    {
        string folder = Path.Combine(Path.GetDirectoryName(scene.path) ?? "", Path.GetFileNameWithoutExtension(scene.path));
        return Path.Combine(folder, "OcclusionCullingData.asset").Replace('\\', '/');
    }

    // Size of the scene's OcclusionCullingData.asset, or -1 when there is none.
    static long FileBytes(Scene scene)
    {
        if (string.IsNullOrEmpty(scene.path)) return -1;
        string path = DataPath(scene);
        return File.Exists(path) ? new FileInfo(path).Length : -1;
    }

    // startedTicks 0: no bake ran in this call, so `written` is false.
    static string Json(Scene scene, bool ok, string error, long bytesBefore, long startedTicks, Census c)
    {
        string dataPath = string.IsNullOrEmpty(scene.path) ? "" : DataPath(scene);
        long onDisk = FileBytes(scene);
        bool written = startedTicks > 0 && onDisk >= 0 && File.GetLastWriteTimeUtc(dataPath).Ticks >= startedTicks;
        var sb = new StringBuilder(512);
        sb.Append("{\"scene\":").Append(Quote(scene.path));
        sb.Append(",\"ok\":").Append(ok && (startedTicks == 0 || written) ? "true" : "false");
        sb.Append(",\"error\":").Append(error == null && startedTicks > 0 && !written
            ? Quote("Compute returned true and the data file was not rewritten; read the console")
            : error == null ? "null" : Quote(error));
        sb.Append(",\"bytesBefore\":").Append(bytesBefore);
        sb.Append(",\"bytes\":").Append(onDisk);
        sb.Append(",\"written\":").Append(written ? "true" : "false");
        sb.Append(",\"dataAsset\":").Append(onDisk < 0 ? "null" : Quote(dataPath));
        sb.Append(",\"smallestOccluder\":").Append(F(StaticOcclusionCulling.smallestOccluder));
        sb.Append(",\"smallestHole\":").Append(F(StaticOcclusionCulling.smallestHole));
        sb.Append(",\"backfaceThreshold\":").Append(F(StaticOcclusionCulling.backfaceThreshold));
        sb.Append(",\"renderers\":").Append(c.renderers);
        sb.Append(",\"occluders\":").Append(c.occluders);
        sb.Append(",\"occludees\":").Append(c.occludees);
        sb.Append(",\"dynamicOccludees\":").Append(c.dynamicOccludees);
        sb.Append(",\"occlusionAreas\":").Append(c.areas);
        sb.Append(",\"occlusionPortals\":").Append(c.portals);
        sb.Append(",\"camerasCulling\":").Append(c.camerasCulling);
        return sb.Append('}').ToString();
    }

    static string F(float v) => v.ToString("0.###", CultureInfo.InvariantCulture);

    static string Quote(string s)
    {
        var sb = new StringBuilder(s.Length + 2).Append('"');
        foreach (char ch in s)
        {
            if (ch == '"' || ch == '\\') sb.Append('\\').Append(ch);
            else if (ch == '\n') sb.Append("\\n");
            else if (ch < ' ') sb.Append(' ');
            else sb.Append(ch);
        }
        return sb.Append('"').ToString();
    }
}
