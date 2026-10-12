// BakeAndReadBack.cs — bake the open scene asynchronously and print what the bake changed as
// one JSON object: lightmap count, baked probe count, the lighting data file's write time and
// the bake's duration, before and after. "Baked" is a claim until those numbers move.
//
// Drop into an Editor folder. No package is needed; it runs on any render pipeline.
//
//   Tools/Unity Dev/Lighting/Bake And Read Back     reports the plan, waits for confirmation, bakes, logs the result
//   BakeAndReadBack.Plan()                          what Start() would do, as text; changes nothing
//   BakeAndReadBack.Start()                         starts the bake and returns; does not ask
//   BakeAndReadBack.Status()                        "running" with progress, or the before/after report
//   -batchmode -executeMethod BakeAndReadBack.BatchBake [-bakeScene Assets/Scenes/GateRoom.unity]
//                                                   bakes, logs the report, exits 0 baked · 1 nothing written · 2 refused
//                                                   (do not pass -quit: the bake outlives the method call)
//
// A bake overwrites the scene's lighting data asset and its lightmap textures, which is why the
// menu asks first. From an eval, call Plan(), show the text, then Start().
//
// The Progressive GPU lightmapper needs a graphics device. Under -nographics there is none
// (SystemInfo.graphicsDeviceType is Null), so the CPU lightmapper is the path: Start() bakes
// with ProgressiveCPU for that run, restores the asset's own choice when the bake ends, and
// reports both as "requested" and "ran". With a device present, "ran" is the requested
// lightmapper; if the Console shows the GPU lightmapper falling back, trust the Console.
//
// The before-evidence is written to Library/UnityDev/Lighting/bake-before.txt, so Status() can
// still report after a domain reload or from a later call, and the watcher that logs the report
// (and exits a batch run) re-attaches itself after a reload. The method is the one in
// unity-urp-migration's resources/LightingMigration.cs: evidence on disk, never in a field.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

public static class BakeAndReadBack
{
    const string MenuPath = "Tools/Unity Dev/Lighting/Bake And Read Back";
    const string EvidencePath = "Library/UnityDev/Lighting/bake-before.txt";

    struct Evidence
    {
        public int lightmaps, probes, contributors, bakedLights;
        public string largest, dataPath;
        public long dataTicks;      // write time of the lighting data asset, UTC ticks; 0 when there is none
    }

    static bool s_Watching;
    static bool s_ExitWhenDone;

    // ------------------------------------------------------------------ entry points

    [MenuItem(MenuPath)]
    static void Menu()
    {
        string plan = Plan();
        Debug.Log("[LIGHTING-BAKE] plan\n" + plan);
        if (!EditorUtility.DisplayDialog("Bake the open scene?", plan, "Bake", "Cancel")) return;
        Debug.Log("[LIGHTING-BAKE] " + Start());
    }

    public static string Plan()
    {
        Scene scene = SceneManager.GetActiveScene();
        Evidence now = Read();
        LightingSettings settings = Settings(out bool hasAsset);
        var sb = new StringBuilder();
        sb.AppendLine("Scene: " + (string.IsNullOrEmpty(scene.path) ? "(unsaved — a bake needs a saved scene)" : scene.path));
        sb.AppendLine("Lighting Settings: " + (hasAsset ? AssetDatabase.GetAssetPath(settings) : "none assigned — the project defaults"));
        sb.AppendLine("Lightmapper: " + Requested(settings) + (ForcesCpu(settings)
            ? " requested; no graphics device, so this run bakes with ProgressiveCPU and restores the setting afterwards"
            : ""));
        sb.AppendLine("Lighting Mode: " + (settings != null ? settings.mixedBakeMode.ToString() : "unknown"));
        sb.AppendLine("Will bake: " + now.bakedLights + " Baked or Mixed light(s) onto " + now.contributors +
                      " renderer(s) with Contribute GI.");
        if (now.bakedLights == 0 || now.contributors == 0)
            sb.AppendLine("  With either count at 0 the bake writes the environment only, or nothing.");
        sb.AppendLine("Overwrites: " + (now.dataPath == "none" ? "nothing yet — creates the lighting data asset" : now.dataPath) +
                      " and the lightmap textures beside it (" + now.lightmaps + " now).");
        sb.AppendLine("Does not save the scene. Save it after reading the report.");
        return sb.ToString();
    }

    public static string Start()
    {
        Scene scene = SceneManager.GetActiveScene();
        if (string.IsNullOrEmpty(scene.path)) return Refused("scene-not-saved", "save the scene first; the bake writes beside it");
        if (Lightmapping.isRunning) return Refused("already-running", "poll BakeAndReadBack.Status()");
        if (EditorApplication.isPlayingOrWillChangePlaymode) return Refused("play-mode", "leave Play mode first");

        LightingSettings settings = Settings(out bool hasAsset);
        string requested = Requested(settings);
        string ran = requested;
        if (ForcesCpu(settings))
        {
            if (!hasAsset)
                return Refused("no-graphics-device",
                    "the default lightmapper is ProgressiveGPU and there is no graphics device; assign a Lighting Settings asset, or run without -nographics");
            // Not marked dirty and restored when the bake ends: the asset on disk keeps its value.
            settings.lightmapper = LightingSettings.Lightmapper.ProgressiveCPU;
            ran = "ProgressiveCPU";
        }

        Evidence before = Read();
        WriteEvidence(before, requested, ran, DateTime.UtcNow.Ticks, s_ExitWhenDone);

        if (!Lightmapping.BakeAsync())
        {
            Restore(requested);
            File.Delete(EvidencePath);
            return Refused("bake-not-started", "Lightmapping.BakeAsync returned false; read the Console");
        }
        Watch();
        return "{\"status\":\"started\",\"scene\":" + Quote(scene.path) + ",\"requested\":" + Quote(requested) +
               ",\"ran\":" + Quote(ran) + ",\"graphicsDevice\":" + Quote(SystemInfo.graphicsDeviceType.ToString()) +
               ",\"before\":" + Json(before) + "}";
    }

    public static string Status()
    {
        if (Lightmapping.isRunning)
            return "{\"status\":\"running\",\"progress\":" + Num(Lightmapping.buildProgress) + "}";
        if (!File.Exists(EvidencePath))
            return "{\"status\":\"idle\",\"detail\":\"no bake was started with BakeAndReadBack.Start()\",\"now\":" + Json(Read()) + "}";

        Dictionary<string, string> stored = ReadEvidence();
        string requested = Get(stored, "requested", "unknown");
        Restore(requested);

        Evidence before = FromStored(stored);
        Evidence after = Read();
        long started = long.Parse(Get(stored, "started", "0"), CultureInfo.InvariantCulture);
        // The lighting data asset's write time is the proof that a bake finished and when.
        bool wrote = after.dataTicks > started;
        bool hasOutput = after.lightmaps > 0 || after.probes > 0;
        string status = !wrote ? "nothing-written" : hasOutput ? "baked" : "baked-empty";
        string seconds = wrote ? Num((float)TimeSpan.FromTicks(after.dataTicks - started).TotalSeconds) : "null";

        return "{\"status\":" + Quote(status) +
               ",\"scene\":" + Quote(SceneManager.GetActiveScene().path) +
               ",\"requested\":" + Quote(requested) +
               ",\"ran\":" + Quote(Get(stored, "ran", "unknown")) +
               ",\"graphicsDevice\":" + Quote(SystemInfo.graphicsDeviceType.ToString()) +
               ",\"bakeSeconds\":" + seconds +
               ",\"before\":" + Json(before) +
               ",\"after\":" + Json(after) +
               ",\"detail\":" + Quote(Explain(status, after)) + "}";
    }

    /// <summary>Batch entry: bake, log the report, exit 0 baked, 1 nothing written, 2 refused.</summary>
    public static void BatchBake()
    {
        string[] args = Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == "-bakeScene")
                EditorSceneManager.OpenScene(args[i + 1], OpenSceneMode.Single);

        // Set before Start(): it is written into the evidence file, which is what survives a reload.
        s_ExitWhenDone = true;
        string started = Start();
        Debug.Log("[LIGHTING-BAKE] " + started);
        if (started.StartsWith("{\"status\":\"refused\""))
            EditorApplication.Exit(2);
    }

    // ------------------------------------------------------------------ polling

    // Statics and the update subscription do not survive a domain reload; the evidence file
    // does. Pick a bake that is still running back up from it.
    [InitializeOnLoadMethod]
    static void Resume()
    {
        if (!File.Exists(EvidencePath) || !Lightmapping.isRunning) return;
        // Only a batch run may exit the Editor: a stale file must never close an interactive session.
        s_ExitWhenDone = Application.isBatchMode && Get(ReadEvidence(), "batch", "0") == "1";
        Watch();
    }

    static void Watch()
    {
        if (s_Watching) return;
        s_Watching = true;
        EditorApplication.update += Poll;
    }

    static void Poll()
    {
        if (Lightmapping.isRunning) return;
        EditorApplication.update -= Poll;
        s_Watching = false;

        string report = Status();
        Debug.Log("[LIGHTING-BAKE] " + report);
        if (s_ExitWhenDone)
        {
            // The scene carries the reference to the new lighting data; a batch run has nobody to save it.
            EditorSceneManager.SaveScene(SceneManager.GetActiveScene());
            EditorApplication.Exit(report.StartsWith("{\"status\":\"baked\"") ? 0 : 1);
        }
    }

    // ------------------------------------------------------------------ evidence

    static Evidence Read()
    {
        var e = new Evidence { largest = "0x0", dataPath = "none" };
        LightmapData[] maps = LightmapSettings.lightmaps;
        e.lightmaps = maps.Length;
        int width = 0;
        foreach (LightmapData map in maps)
            if (map.lightmapColor != null && map.lightmapColor.width > width)
            {
                width = map.lightmapColor.width;
                e.largest = width + "x" + map.lightmapColor.height;
            }

        LightProbes probes = LightmapSettings.lightProbes;
        e.probes = probes != null ? probes.count : 0;

        foreach (GameObject root in SceneManager.GetActiveScene().GetRootGameObjects())
        {
            foreach (MeshRenderer r in root.GetComponentsInChildren<MeshRenderer>(false))
                if ((GameObjectUtility.GetStaticEditorFlags(r.gameObject) & StaticEditorFlags.ContributeGI) != 0)
                    e.contributors++;
            foreach (Light l in root.GetComponentsInChildren<Light>(false))
                if (l.enabled && l.lightmapBakeType != LightmapBakeType.Realtime)
                    e.bakedLights++;
        }

        // A never-baked scene points at Unity's built-in default data, which is not a file of the
        // project: report it as none.
        LightingDataAsset data = Lightmapping.lightingDataAsset;
        string path = data != null ? AssetDatabase.GetAssetPath(data) : "";
        if (path.StartsWith("Assets/") && File.Exists(path))
        {
            e.dataPath = path;
            e.dataTicks = File.GetLastWriteTimeUtc(path).Ticks;
        }
        return e;
    }

    static string Explain(string status, Evidence after)
    {
        if (status == "baked") return "the lighting data asset was written after the bake started and the scene has baked output";
        if (status == "nothing-written")
            return "the lighting data asset was not written: the bake was cancelled, failed (read the Console), or is disabled (Baked Global Illumination off)";
        if (after.contributors == 0) return "the bake ran and produced no lightmap: no renderer has the Contribute GI static flag";
        if (after.bakedLights == 0) return "the bake ran and produced no lightmap: every light is Realtime";
        return "the bake ran and produced neither lightmaps nor probes; under Adaptive Probe Volumes the probe count stays 0 — read LightingAudit's probes.apv block";
    }

    static void WriteEvidence(Evidence e, string requested, string ran, long startedTicks, bool batch)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(EvidencePath));
        File.WriteAllLines(EvidencePath, new[]
        {
            "started=" + startedTicks.ToString(CultureInfo.InvariantCulture),
            "requested=" + requested,
            "ran=" + ran,
            "batch=" + (batch ? "1" : "0"),
            "lightmaps=" + e.lightmaps,
            "probes=" + e.probes,
            "contributors=" + e.contributors,
            "bakedLights=" + e.bakedLights,
            "largest=" + e.largest,
            "dataPath=" + e.dataPath,
            "dataTicks=" + e.dataTicks.ToString(CultureInfo.InvariantCulture),
        });
    }

    static Dictionary<string, string> ReadEvidence()
    {
        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (string line in File.ReadAllLines(EvidencePath))
        {
            int at = line.IndexOf('=');
            if (at > 0) map[line.Substring(0, at)] = line.Substring(at + 1);
        }
        return map;
    }

    static Evidence FromStored(Dictionary<string, string> s)
    {
        return new Evidence
        {
            lightmaps = int.Parse(Get(s, "lightmaps", "0"), CultureInfo.InvariantCulture),
            probes = int.Parse(Get(s, "probes", "0"), CultureInfo.InvariantCulture),
            contributors = int.Parse(Get(s, "contributors", "0"), CultureInfo.InvariantCulture),
            bakedLights = int.Parse(Get(s, "bakedLights", "0"), CultureInfo.InvariantCulture),
            largest = Get(s, "largest", "0x0"),
            dataPath = Get(s, "dataPath", "none"),
            dataTicks = long.Parse(Get(s, "dataTicks", "0"), CultureInfo.InvariantCulture),
        };
    }

    static string Get(Dictionary<string, string> map, string key, string fallback) =>
        map.TryGetValue(key, out string value) ? value : fallback;

    // ------------------------------------------------------------------ lightmapper

    static LightingSettings Settings(out bool hasAsset)
    {
        hasAsset = Lightmapping.TryGetLightingSettings(out LightingSettings settings) && settings != null;
        return hasAsset ? settings : Lightmapping.lightingSettingsDefaults;
    }

    static string Requested(LightingSettings settings) =>
        settings != null ? settings.lightmapper.ToString() : "unknown";

    static bool ForcesCpu(LightingSettings settings) =>
        settings != null &&
        settings.lightmapper == LightingSettings.Lightmapper.ProgressiveGPU &&
        SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null;

    // Put back the lightmapper Start() replaced for a run without a graphics device.
    static void Restore(string requested)
    {
        if (requested != LightingSettings.Lightmapper.ProgressiveGPU.ToString()) return;
        if (Lightmapping.TryGetLightingSettings(out LightingSettings settings) && settings != null &&
            settings.lightmapper != LightingSettings.Lightmapper.ProgressiveGPU)
            settings.lightmapper = LightingSettings.Lightmapper.ProgressiveGPU;
    }

    // ------------------------------------------------------------------ JSON

    static string Refused(string reason, string detail) =>
        "{\"status\":\"refused\",\"reason\":" + Quote(reason) + ",\"detail\":" + Quote(detail) + "}";

    static string Json(Evidence e)
    {
        string written = e.dataTicks > 0
            ? new DateTime(e.dataTicks, DateTimeKind.Utc).ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture)
            : "never";
        return "{\"lightmaps\":" + e.lightmaps + ",\"largest\":" + Quote(e.largest) + ",\"probes\":" + e.probes +
               ",\"contributeGI\":" + e.contributors + ",\"bakedOrMixedLights\":" + e.bakedLights +
               ",\"lightingData\":" + Quote(e.dataPath) + ",\"lightingDataWritten\":" + Quote(written) + "}";
    }

    static string Num(float f) =>
        float.IsNaN(f) || float.IsInfinity(f) ? "null" : f.ToString("0.###", CultureInfo.InvariantCulture);

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
