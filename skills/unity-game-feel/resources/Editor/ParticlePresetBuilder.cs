// ParticlePresetBuilder.cs — builds a burst-style ParticleSystem prefab from one of four
// presets, so every one-shot effect in the game starts from the same known settings.
//
// Drop into an Editor folder. No package needed (the built-in Particle System module).
//
//   Tools/Unity Dev/Feel/Build Particle Preset/Hit Spark
//   Tools/Unity Dev/Feel/Build Particle Preset/Pickup Pop
//   Tools/Unity Dev/Feel/Build Particle Preset/Land Dust
//   Tools/Unity Dev/Feel/Build Particle Preset/Launch Burst
//
// Every command reports what it would create and waits for confirmation. From an eval or a
// test fixture, call Plan(...) first, show the text, then Build(...) — Build does not ask.
//
// Two shapes of the same preset:
//   shared   (the menu)  Play On Awake off, no stop action. One instance lives in the scene; a
//                        Feedback row moves it and calls Emit(count). World simulation space
//                        keeps the particles where they were born when it moves on.
//   pooled   Build(preset, folder, true)   Play On Awake on, stop action Disable. Enabling the
//                        object plays it and it switches itself off — what a pool hands out.
//
// The material is the active render pipeline's own default particle material, so the prefab is
// never pink under URP; with no pipeline asset it is the built-in one. Nothing is written but
// the prefab.
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

public static class ParticlePresetBuilder
{
    const string MenuRoot = "Tools/Unity Dev/Feel/Build Particle Preset/";
    public const string DefaultFolder = "Assets/Feel/Particles";

    public struct Preset
    {
        public string name;
        public short count;                 // the burst when it is played, and the default for Emit
        public float lifetimeMin, lifetimeMax;
        public float speedMin, speedMax;
        public float sizeMin, sizeMax;
        public float gravity;
        public float drag;
        public ParticleSystemShapeType shape;
        public float angle, radius;
        public Color colour;
        public bool stretch;                // drawn as streaks along the velocity
        public int maxParticles;
    }

    // Lifetimes stay under 0.5 s and counts under 24: a burst is punctuation. maxParticles is
    // four bursts' worth, the most that can be alive when events arrive back to back.
    public static readonly Preset HitSpark = new Preset
    {
        name = "HitSpark", count = 12, lifetimeMin = 0.15f, lifetimeMax = 0.30f, speedMin = 6f, speedMax = 10f,
        sizeMin = 0.06f, sizeMax = 0.12f, gravity = 1f, drag = 2f, shape = ParticleSystemShapeType.Cone,
        angle = 35f, radius = 0.05f, colour = new Color(1f, 0.9f, 0.6f, 1f), stretch = true, maxParticles = 48,
    };

    public static readonly Preset PickupPop = new Preset
    {
        name = "PickupPop", count = 6, lifetimeMin = 0.20f, lifetimeMax = 0.35f, speedMin = 2f, speedMax = 4f,
        sizeMin = 0.10f, sizeMax = 0.18f, gravity = 0f, drag = 3f, shape = ParticleSystemShapeType.Sphere,
        angle = 0f, radius = 0.1f, colour = new Color(1f, 0.85f, 0.2f, 1f), stretch = false, maxParticles = 24,
    };

    public static readonly Preset LandDust = new Preset
    {
        name = "LandDust", count = 8, lifetimeMin = 0.25f, lifetimeMax = 0.45f, speedMin = 1f, speedMax = 2.5f,
        sizeMin = 0.20f, sizeMax = 0.40f, gravity = -0.05f, drag = 4f, shape = ParticleSystemShapeType.Hemisphere,
        angle = 0f, radius = 0.3f, colour = new Color(0.8f, 0.8f, 0.8f, 0.6f), stretch = false, maxParticles = 32,
    };

    public static readonly Preset LaunchBurst = new Preset
    {
        name = "LaunchBurst", count = 20, lifetimeMin = 0.20f, lifetimeMax = 0.40f, speedMin = 5f, speedMax = 9f,
        sizeMin = 0.08f, sizeMax = 0.16f, gravity = 0.5f, drag = 2f, shape = ParticleSystemShapeType.Cone,
        angle = 20f, radius = 0.15f, colour = new Color(0.6f, 0.9f, 1f, 1f), stretch = true, maxParticles = 80,
    };

    // ------------------------------------------------------------------ menu

    [MenuItem(MenuRoot + "Hit Spark")] static void MenuHitSpark() => Menu(HitSpark);
    [MenuItem(MenuRoot + "Pickup Pop")] static void MenuPickupPop() => Menu(PickupPop);
    [MenuItem(MenuRoot + "Land Dust")] static void MenuLandDust() => Menu(LandDust);
    [MenuItem(MenuRoot + "Launch Burst")] static void MenuLaunchBurst() => Menu(LaunchBurst);

    static void Menu(Preset preset)
    {
        string plan = Plan(preset, DefaultFolder, false);
        Debug.Log("[PARTICLE-PRESET] plan\n" + plan);
        if (!EditorUtility.DisplayDialog("Build " + preset.name + "?", plan, "Create", "Cancel")) return;
        GameObject prefab = Build(preset, DefaultFolder, false);
        Selection.activeObject = prefab;
        EditorGUIUtility.PingObject(prefab);
    }

    // ------------------------------------------------------------------ plan

    public static string Plan(Preset p, string folder, bool pooled)
    {
        Material material = ParticleMaterial();
        var sb = new StringBuilder();
        if (!AssetDatabase.IsValidFolder(folder)) sb.AppendLine("Create folder " + folder);
        sb.AppendLine("Create " + AssetDatabase.GenerateUniqueAssetPath(PathFor(p, folder, pooled)) + " with:");
        sb.AppendLine("  ParticleSystem   looping off, duration 1 s, play on awake " + (pooled ? "on" : "off") +
                      ", stop action " + (pooled ? "Disable" : "None"));
        sb.AppendLine("                   simulation space World, scaling mode Hierarchy, max particles " + p.maxParticles);
        sb.AppendLine("                   one burst of " + p.count + " at 0 s, rate over time 0");
        sb.AppendLine("                   lifetime " + p.lifetimeMin + "–" + p.lifetimeMax + " s, speed " + p.speedMin + "–" + p.speedMax +
                      ", size " + p.sizeMin + "–" + p.sizeMax + ", gravity " + p.gravity + ", drag " + p.drag);
        sb.AppendLine("                   shape " + p.shape + ", radius " + p.radius + (p.shape == ParticleSystemShapeType.Cone ? ", angle " + p.angle : ""));
        sb.AppendLine("                   size over lifetime 1 → 0, alpha over lifetime 1 → 0");
        sb.AppendLine("  Renderer         " + (p.stretch ? "stretched billboard, speed scale 0.05" : "billboard") + ", shadows off");
        sb.AppendLine("                   material: " + (material != null ? material.name + " (" + material.shader.name + ")"
                                                                           : "NONE FOUND — assign one, or it draws magenta"));
        sb.AppendLine("Nothing else is written. No scene object is left behind.");
        return sb.ToString();
    }

    // ------------------------------------------------------------------ build

    public static GameObject Build(Preset p, string folder, bool pooled)
    {
        EnsureFolder(folder);
        string path = AssetDatabase.GenerateUniqueAssetPath(PathFor(p, folder, pooled));

        var go = new GameObject(p.name);
        try
        {
            var ps = go.AddComponent<ParticleSystem>();
            // AddComponent leaves it playing in the Editor; settings such as duration cannot be
            // assigned to a playing system.
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);

            ParticleSystem.MainModule main = ps.main;
            main.duration = 1f;
            main.loop = false;
            main.playOnAwake = pooled;
            main.stopAction = pooled ? ParticleSystemStopAction.Disable : ParticleSystemStopAction.None;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.scalingMode = ParticleSystemScalingMode.Hierarchy;
            main.maxParticles = p.maxParticles;
            main.startLifetime = new ParticleSystem.MinMaxCurve(p.lifetimeMin, p.lifetimeMax);
            main.startSpeed = new ParticleSystem.MinMaxCurve(p.speedMin, p.speedMax);
            main.startSize = new ParticleSystem.MinMaxCurve(p.sizeMin, p.sizeMax);
            main.startColor = new ParticleSystem.MinMaxGradient(p.colour);
            main.gravityModifier = new ParticleSystem.MinMaxCurve(p.gravity);

            ParticleSystem.EmissionModule emission = ps.emission;
            emission.enabled = true;
            emission.rateOverTime = new ParticleSystem.MinMaxCurve(0f);
            emission.SetBursts(new[] { new ParticleSystem.Burst(0f, p.count) });

            ParticleSystem.ShapeModule shape = ps.shape;
            shape.enabled = true;
            shape.shapeType = p.shape;
            shape.radius = p.radius;
            if (p.shape == ParticleSystemShapeType.Cone) shape.angle = p.angle;

            ParticleSystem.LimitVelocityOverLifetimeModule limit = ps.limitVelocityOverLifetime;
            limit.enabled = p.drag > 0f;
            limit.drag = new ParticleSystem.MinMaxCurve(p.drag);
            limit.dampen = 0f;                 // drag only: no speed limit is applied
            limit.multiplyDragByParticleSize = false;
            limit.multiplyDragByParticleVelocity = false;

            ParticleSystem.SizeOverLifetimeModule size = ps.sizeOverLifetime;
            size.enabled = true;
            size.size = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.Linear(0f, 1f, 1f, 0f));

            var fade = new Gradient();
            fade.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                         new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(1f, 0.5f), new GradientAlphaKey(0f, 1f) });
            ParticleSystem.ColorOverLifetimeModule colour = ps.colorOverLifetime;
            colour.enabled = true;
            colour.color = new ParticleSystem.MinMaxGradient(fade);

            var renderer = go.GetComponent<ParticleSystemRenderer>();
            renderer.renderMode = p.stretch ? ParticleSystemRenderMode.Stretch : ParticleSystemRenderMode.Billboard;
            if (p.stretch)
            {
                renderer.velocityScale = 0.05f;
                renderer.lengthScale = 1f;
            }
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            renderer.sharedMaterial = ParticleMaterial();

            GameObject prefab = PrefabUtility.SaveAsPrefabAsset(go, path, out bool ok);
            if (!ok) Debug.LogError("[PARTICLE-PRESET] could not save " + path);
            else Debug.Log("[PARTICLE-PRESET] created " + path);
            return prefab;
        }
        finally
        {
            Object.DestroyImmediate(go);
        }
    }

    // The pipeline's own default: URP's is its Particles/Unlit material, textured and alpha
    // blended. The built-in default draws magenta under any scriptable pipeline.
    public static Material ParticleMaterial()
    {
        RenderPipelineAsset pipeline = GraphicsSettings.currentRenderPipeline;
        Material material = pipeline != null ? pipeline.defaultParticleMaterial : null;
        if (material == null) material = AssetDatabase.GetBuiltinExtraResource<Material>("Default-ParticleSystem.mat");
        return material;
    }

    static string PathFor(Preset p, string folder, bool pooled)
        => folder.TrimEnd('/') + "/" + p.name + (pooled ? "Pooled" : "") + ".prefab";

    static void EnsureFolder(string folder)
    {
        folder = folder.TrimEnd('/');
        if (AssetDatabase.IsValidFolder(folder)) return;
        string[] parts = folder.Split('/');
        string current = parts[0];                         // "Assets"
        for (int i = 1; i < parts.Length; i++)
        {
            string next = current + "/" + parts[i];
            if (!AssetDatabase.IsValidFolder(next)) AssetDatabase.CreateFolder(current, parts[i]);
            current = next;
        }
    }
}
