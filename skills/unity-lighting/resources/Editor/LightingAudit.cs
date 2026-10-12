// LightingAudit.cs — a read-only audit of the 3D lighting set-up in the open scene, printed as
// one JSON object. It changes nothing: no light, no flag, no setting, no asset.
//
// Drop into an Editor folder.
//
// REQUIRES com.unity.render-pipelines.universal 17.x (read Packages/manifest.json). When the
// pipeline in force is not URP the audit still runs and reports "pipeline":"not-urp" with the
// scene half of the report.
//
//   Tools/Unity Dev/Lighting/Audit Open Scene      logs "[LIGHTING-AUDIT] {json}"
//   LightingAudit.Audit()                          returns the same JSON, for an eval or a test
//
// Read through SerializedObject, because the public surface of UniversalRenderPipelineAsset
// does not carry them: m_DefaultRendererIndex (which renderer of rendererDataList is the
// default) and m_SoftShadowQuality. A field that does not resolve is reported as "unread".
// The Screen Space Shadows renderer feature is an internal class and is recognised by name.
//
// Each finding is a candidate, not a verdict. `check` names the rule:
//
//   pipeline-not-urp               the pipeline in force is not a UniversalRenderPipelineAsset
//   mixed-lighting-off             a Mixed light, and Mixed Lighting is unticked on the URP asset
//   baked-light-never-baked        a Baked or Mixed light with no bake behind it: it lights nothing or acts Realtime
//   light-mode-changed-since-bake  the light's mode, or the Lighting Mode, differs from what was baked
//   nothing-contributes-gi         Baked or Mixed lights, and no renderer with Contribute GI
//   contributes-gi-without-uv2     Contribute GI + Receive GI Lightmaps on a mesh with no second UV set
//   scale-in-lightmap-zero         Contribute GI + Receive GI Lightmaps with Scale In Lightmap 0
//   dynamic-without-probes         baked lighting, moving renderers, and neither baked probes nor APV
//   probe-groups-ignored           Light Probe Groups in a scene whose URP asset uses Adaptive Probe Volumes
//   probe-volume-ignored           a Probe Volume in a scene whose URP asset uses Light Probe Groups
//   box-projection-off-in-asset    a probe asks for box projection, the URP asset does not allow it
//   probe-blending-off-in-asset    two or more probes, and Probe Blending is off on the URP asset
//   baked-probe-without-texture    a Baked reflection probe that has never been baked
//   main-shadows-off-in-asset      a directional light casts shadows, the URP asset has main light shadows off
//   additional-shadows-off         a point or spot light casts shadows the URP asset will not render
//   second-directional-shadowless  a shadow-casting directional light that is not the main light
//   sun-not-assigned               several directional lights and no Sun Source: the brightest becomes the main light
//   no-environment-reflection      the reflection source is Custom with no cubemap, or its intensity is 0
using System.Collections.Generic;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

public static class LightingAudit
{
    const string MenuPath = "Tools/Unity Dev/Lighting/Audit Open Scene";
    const int MaxListed = 40;   // paths listed per list; the counts are always complete

    struct Finding { public string check, path, detail; }

    [MenuItem(MenuPath)]
    static void Menu() => Debug.Log("[LIGHTING-AUDIT] " + Audit());

    public static string Audit()
    {
        Scene scene = SceneManager.GetActiveScene();
        var lights = new List<Light>();
        var renderers = new List<MeshRenderer>();
        var probeGroups = new List<LightProbeGroup>();
        var reflectionProbes = new List<ReflectionProbe>();
        var probeVolumes = new List<ProbeVolume>();
        var perSceneData = new List<ProbeVolumePerSceneData>();
        int skinned = 0;
        // Walk the roots so that inactive objects are read too: a disabled light is part of the
        // set-up, and a bake skips it.
        foreach (GameObject root in scene.GetRootGameObjects())
        {
            lights.AddRange(root.GetComponentsInChildren<Light>(true));
            renderers.AddRange(root.GetComponentsInChildren<MeshRenderer>(true));
            probeGroups.AddRange(root.GetComponentsInChildren<LightProbeGroup>(true));
            reflectionProbes.AddRange(root.GetComponentsInChildren<ReflectionProbe>(true));
            probeVolumes.AddRange(root.GetComponentsInChildren<ProbeVolume>(true));
            perSceneData.AddRange(root.GetComponentsInChildren<ProbeVolumePerSceneData>(true));
            skinned += root.GetComponentsInChildren<SkinnedMeshRenderer>(true).Length;
        }

        var findings = new List<Finding>();
        var sb = new StringBuilder(2048);
        sb.Append("{\"scene\":").Append(Quote(scene.path));

        // ---------------------------------------------------------------- pipeline
        var urp = GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
        bool apvOnAsset = false, forwardPlus = false;
        sb.Append(",\"pipeline\":");
        if (urp == null)
        {
            RenderPipelineAsset other = GraphicsSettings.currentRenderPipeline;
            sb.Append("{\"active\":\"not-urp\",\"asset\":")
              .Append(Quote(other != null ? other.GetType().Name : "none (built-in)")).Append('}');
            findings.Add(new Finding
            {
                check = "pipeline-not-urp", path = "",
                detail = "GraphicsSettings.currentRenderPipeline is not a UniversalRenderPipelineAsset; the URP half of this report is empty"
            });
        }
        else
        {
            apvOnAsset = urp.lightProbeSystem == LightProbeSystem.ProbeVolumes;
            var so = new SerializedObject(urp);
            SerializedProperty indexProp = so.FindProperty("m_DefaultRendererIndex");
            SerializedProperty softProp = so.FindProperty("m_SoftShadowQuality");

            string rendererName = "unread", renderingMode = "unread";
            bool screenSpaceShadows = false;
            if (indexProp != null)
            {
                int index = indexProp.intValue;
                System.ReadOnlySpan<ScriptableRendererData> list = urp.rendererDataList;
                ScriptableRendererData data = index >= 0 && index < list.Length ? list[index] : null;
                if (data != null)
                {
                    rendererName = data.name;
                    renderingMode = data is UniversalRendererData universal
                        ? universal.renderingMode.ToString()
                        : data.GetType().Name;
                    forwardPlus = renderingMode == "ForwardPlus" || renderingMode == "DeferredPlus";
                    foreach (ScriptableRendererFeature feature in data.rendererFeatures)
                        if (feature != null && feature.isActive && feature.GetType().Name == "ScreenSpaceShadows")
                            screenSpaceShadows = true;
                }
                else rendererName = "missing";
            }

            string softQuality = "unread";
            if (softProp != null && softProp.propertyType == SerializedPropertyType.Enum &&
                softProp.enumValueIndex >= 0 && softProp.enumValueIndex < softProp.enumNames.Length)
                softQuality = softProp.enumNames[softProp.enumValueIndex];

            sb.Append("{\"active\":\"urp\",\"asset\":").Append(Quote(AssetDatabase.GetAssetPath(urp)));
            sb.Append(",\"qualityLevel\":").Append(Quote(QualitySettings.names[QualitySettings.GetQualityLevel()]));
            sb.Append(",\"renderer\":").Append(Quote(rendererName));
            sb.Append(",\"renderingMode\":").Append(Quote(renderingMode));
            sb.Append(",\"mainLight\":").Append(Quote(urp.mainLightRenderingMode.ToString()));
            sb.Append(",\"additionalLights\":").Append(Quote(urp.additionalLightsRenderingMode.ToString()));
            sb.Append(",\"perObjectLimit\":").Append(urp.maxAdditionalLightsCount);
            sb.Append(",\"perObjectLimitApplies\":").Append(Bool(!forwardPlus));
            sb.Append(",\"maxVisibleAdditionalLights\":").Append(UniversalRenderPipeline.maxVisibleAdditionalLights);
            sb.Append(",\"mixedLighting\":").Append(Bool(urp.supportsMixedLighting));
            sb.Append(",\"lightProbeSystem\":").Append(Quote(urp.lightProbeSystem.ToString()));
            sb.Append(",\"reflectionProbeBlending\":").Append(Bool(urp.reflectionProbeBlending));
            sb.Append(",\"reflectionProbeBoxProjection\":").Append(Bool(urp.reflectionProbeBoxProjection));
            sb.Append(",\"reflectionProbeAtlas\":").Append(Bool(urp.reflectionProbeAtlas));
            sb.Append(",\"shadows\":{\"mainLightShadows\":").Append(Bool(urp.supportsMainLightShadows));
            sb.Append(",\"additionalLightShadows\":").Append(Bool(urp.supportsAdditionalLightShadows));
            sb.Append(",\"distance\":").Append(Num(urp.shadowDistance));
            sb.Append(",\"cascades\":").Append(urp.shadowCascadeCount);
            sb.Append(",\"cascadeBorder\":").Append(Num(urp.cascadeBorder));
            sb.Append(",\"mainResolution\":").Append(urp.mainLightShadowmapResolution);
            sb.Append(",\"additionalAtlas\":").Append(urp.additionalLightsShadowmapResolution);
            sb.Append(",\"depthBias\":").Append(Num(urp.shadowDepthBias));
            sb.Append(",\"normalBias\":").Append(Num(urp.shadowNormalBias));
            sb.Append(",\"soft\":").Append(Bool(urp.supportsSoftShadows));
            sb.Append(",\"softQuality\":").Append(Quote(softQuality));
            sb.Append(",\"screenSpaceShadowsFeature\":").Append(Bool(screenSpaceShadows));
            sb.Append(",\"shadowmaskMode\":").Append(Quote(QualitySettings.shadowmaskMode.ToString()));
            sb.Append("}}");
        }

        // ---------------------------------------------------------------- lighting settings
        LightingSettings settings;
        bool hasAsset = Lightmapping.TryGetLightingSettings(out settings) && settings != null;
        if (!hasAsset) settings = Lightmapping.lightingSettingsDefaults;
        sb.Append(",\"settings\":{\"asset\":").Append(Quote(hasAsset ? AssetDatabase.GetAssetPath(settings) : "defaults"));
        if (settings != null)
        {
            sb.Append(",\"lightmapper\":").Append(Quote(settings.lightmapper.ToString()));
            sb.Append(",\"lightingMode\":").Append(Quote(settings.mixedBakeMode.ToString()));
            sb.Append(",\"bakedGI\":").Append(Bool(settings.bakedGI));
            sb.Append(",\"realtimeGI\":").Append(Bool(settings.realtimeGI));
            sb.Append(",\"lightmapResolution\":").Append(Num(settings.lightmapResolution));
            sb.Append(",\"lightmapMaxSize\":").Append(settings.lightmapMaxSize);
            sb.Append(",\"directSamples\":").Append(settings.directSampleCount);
            sb.Append(",\"indirectSamples\":").Append(settings.indirectSampleCount);
            sb.Append(",\"maxBounces\":").Append(settings.maxBounces);
        }
        sb.Append('}');

        // ---------------------------------------------------------------- lights
        int bakedOrMixed = 0, directionals = 0;
        sb.Append(",\"lights\":[");
        for (int i = 0; i < lights.Count; i++)
        {
            Light l = lights[i];
            LightBakingOutput baked = l.bakingOutput;
            bool on = l.enabled && l.gameObject.activeInHierarchy;
            bool wantsBake = l.lightmapBakeType != LightmapBakeType.Realtime;
            if (wantsBake && on) bakedOrMixed++;
            if (l.type == LightType.Directional && on) directionals++;

            if (i > 0) sb.Append(',');
            sb.Append("{\"path\":").Append(Quote(PathOf(l.transform)));
            sb.Append(",\"type\":").Append(Quote(l.type.ToString()));
            sb.Append(",\"mode\":").Append(Quote(l.lightmapBakeType.ToString()));
            sb.Append(",\"bakedAs\":").Append(Quote(baked.isBaked ? baked.lightmapBakeType.ToString() : "not-baked"));
            sb.Append(",\"bakedLightingMode\":").Append(Quote(baked.isBaked ? baked.mixedLightingMode.ToString() : "none"));
            sb.Append(",\"shadows\":").Append(Quote(l.shadows.ToString()));
            sb.Append(",\"intensity\":").Append(Num(l.intensity));
            sb.Append(",\"active\":").Append(Bool(on)).Append('}');

            if (!on) continue;
            if (l.lightmapBakeType == LightmapBakeType.Mixed && urp != null && !urp.supportsMixedLighting)
                Add(findings, "mixed-lighting-off", l,
                    "Mixed light, and Mixed Lighting is unticked on the URP asset: the shadowmask and subtractive paths are never selected");
            if (wantsBake && !baked.isBaked)
                Add(findings, "baked-light-never-baked", l,
                    l.lightmapBakeType == LightmapBakeType.Baked
                        ? "Baked light with no bake behind it: it lights nothing until the scene is baked"
                        : "Mixed light with no bake behind it: it renders as a Realtime light and adds no bounce");
            else if (baked.isBaked && baked.lightmapBakeType != l.lightmapBakeType)
                Add(findings, "light-mode-changed-since-bake", l,
                    "mode is " + l.lightmapBakeType + ", the bake holds it as " + baked.lightmapBakeType + ": rebake");
            else if (baked.isBaked && l.lightmapBakeType == LightmapBakeType.Mixed && settings != null &&
                     baked.mixedLightingMode != settings.mixedBakeMode)
                Add(findings, "light-mode-changed-since-bake", l,
                    "Lighting Mode is " + settings.mixedBakeMode + ", the bake holds " + baked.mixedLightingMode + ": rebake");

            if (urp == null || l.shadows == LightShadows.None || l.lightmapBakeType == LightmapBakeType.Baked) continue;
            if (l.type == LightType.Directional && !urp.supportsMainLightShadows)
                Add(findings, "main-shadows-off-in-asset", l, "casts shadows; Main Light > Cast Shadows is off on the URP asset");
            if (l.type != LightType.Directional)
            {
                bool perPixel = urp.additionalLightsRenderingMode == LightRenderingMode.PerPixel || forwardPlus;
                if (!urp.supportsAdditionalLightShadows || !perPixel)
                    Add(findings, "additional-shadows-off", l,
                        "casts shadows; the URP asset needs Additional Lights Per Pixel (or Forward+) and Cast Shadows ticked");
            }
        }
        sb.Append(']');

        // URP has one main light: the Sun Source when it is an active directional light, otherwise
        // the brightest directional. Every other directional light is an additional light, and
        // those never cast shadows.
        Light main = RenderSettings.sun;
        if (main == null || !main.enabled || !main.gameObject.activeInHierarchy || main.type != LightType.Directional)
        {
            main = null;
            foreach (Light l in lights)
                if (l.type == LightType.Directional && l.enabled && l.gameObject.activeInHierarchy &&
                    l.lightmapBakeType != LightmapBakeType.Baked && (main == null || l.intensity > main.intensity))
                    main = l;
        }
        foreach (Light l in lights)
            if (l != main && l.type == LightType.Directional && l.enabled && l.gameObject.activeInHierarchy &&
                l.lightmapBakeType != LightmapBakeType.Baked && l.shadows != LightShadows.None && urp != null)
                Add(findings, "second-directional-shadowless", l,
                    "casts shadows, but it is not the main light ('" + (main != null ? main.name : "none") +
                    "'): URP renders no shadow for an additional directional light");

        if (directionals > 1 && RenderSettings.sun == null)
            findings.Add(new Finding
            {
                check = "sun-not-assigned", path = "",
                detail = directionals + " active directional lights and no Sun Source: the brightest is the main light, the rest are additional lights"
            });

        // ---------------------------------------------------------------- static flags and UVs
        int contributeGI = 0, receiveLightmaps = 0, receiveProbes = 0, lightmapped = 0, dynamic = skinned;
        int reflectionStatic = 0, noUv2 = 0, zeroScale = 0;
        foreach (MeshRenderer r in renderers)
        {
            StaticEditorFlags flags = GameObjectUtility.GetStaticEditorFlags(r.gameObject);
            if ((flags & StaticEditorFlags.ReflectionProbeStatic) != 0) reflectionStatic++;
            if (r.lightmapIndex >= 0 && r.lightmapIndex < 65534) lightmapped++;
            if ((flags & StaticEditorFlags.ContributeGI) == 0) { dynamic++; continue; }

            contributeGI++;
            if (r.receiveGI != ReceiveGI.Lightmaps) { receiveProbes++; continue; }
            receiveLightmaps++;

            if (r.scaleInLightmap <= 0f)
            {
                zeroScale++;
                if (zeroScale <= MaxListed)
                    Add(findings, "scale-in-lightmap-zero", r, "Scale In Lightmap is 0: the renderer gets no texels and bakes black");
            }

            MeshFilter filter = r.GetComponent<MeshFilter>();
            Mesh mesh = filter != null ? filter.sharedMesh : null;
            if (mesh == null || mesh.HasVertexAttribute(VertexAttribute.TexCoord1)) continue;
            noUv2++;
            if (noUv2 > MaxListed) continue;
            string source = AssetDatabase.GetAssetPath(mesh);
            var importer = AssetImporter.GetAtPath(source) as ModelImporter;
            string why = importer != null
                ? "imported from " + source + " with Generate Lightmap UVs " + (importer.generateSecondaryUV ? "on (unwrap failed or the mesh was replaced)" : "off")
                : "mesh '" + mesh.name + "' is not a model import; unwrap it with Unwrapping.GenerateSecondaryUVSet or author UV2";
            Add(findings, "contributes-gi-without-uv2", r,
                "no second UV set, so the bake falls back to UV0, which is right only when UV0 has no overlap; " + why);
        }
        sb.Append(",\"static\":{\"meshRenderers\":").Append(renderers.Count);
        sb.Append(",\"skinnedRenderers\":").Append(skinned);
        sb.Append(",\"contributeGI\":").Append(contributeGI);
        sb.Append(",\"receiveLightmaps\":").Append(receiveLightmaps);
        sb.Append(",\"receiveProbes\":").Append(receiveProbes);
        sb.Append(",\"lightmapped\":").Append(lightmapped);
        sb.Append(",\"notContributing\":").Append(dynamic);
        sb.Append(",\"reflectionProbeStatic\":").Append(reflectionStatic);
        sb.Append(",\"contributeGIWithoutUv2\":").Append(noUv2);
        sb.Append(",\"scaleInLightmapZero\":").Append(zeroScale).Append('}');

        if (bakedOrMixed > 0 && contributeGI == 0)
            findings.Add(new Finding
            {
                check = "nothing-contributes-gi", path = "",
                detail = bakedOrMixed + " Baked or Mixed light(s) and no MeshRenderer with the Contribute GI static flag: a bake has nothing to write"
            });

        // ---------------------------------------------------------------- bake output
        LightmapData[] maps = LightmapSettings.lightmaps;
        int width = 0, height = 0;
        bool shadowMask = false, directional = false;
        foreach (LightmapData map in maps)
        {
            if (map.lightmapColor != null && map.lightmapColor.width > width)
            {
                width = map.lightmapColor.width;
                height = map.lightmapColor.height;
            }
            if (map.shadowMask != null) shadowMask = true;
            if (map.lightmapDir != null) directional = true;
        }
        LightingDataAsset dataAsset = Lightmapping.lightingDataAsset;
        sb.Append(",\"bake\":{\"running\":").Append(Bool(Lightmapping.isRunning));
        sb.Append(",\"lightingData\":").Append(Quote(dataAsset != null ? AssetDatabase.GetAssetPath(dataAsset) : "none"));
        sb.Append(",\"lightmaps\":").Append(maps.Length);
        sb.Append(",\"largest\":").Append(Quote(width + "x" + height));
        sb.Append(",\"shadowMask\":").Append(Bool(shadowMask));
        sb.Append(",\"directional\":").Append(Bool(directional)).Append('}');

        // ---------------------------------------------------------------- probes
        int authored = 0;
        foreach (LightProbeGroup group in probeGroups) authored += group.probePositions.Length;
        LightProbes bakedProbes = LightmapSettings.lightProbes;
        int bakedCount = bakedProbes != null ? bakedProbes.count : 0;

        string bakingSet = "none";
        bool apvBaked = false;
        foreach (ProbeVolumePerSceneData data in perSceneData)
        {
            if (data.bakingSet == null) continue;
            bakingSet = data.bakingSet.name;
            apvBaked = data.bakingSet.HasBakedData();
        }
        sb.Append(",\"probes\":{\"groups\":").Append(probeGroups.Count);
        sb.Append(",\"authored\":").Append(authored);
        sb.Append(",\"baked\":").Append(bakedCount);
        sb.Append(",\"apv\":{\"enabledOnAsset\":").Append(Bool(apvOnAsset));
        sb.Append(",\"volumes\":").Append(probeVolumes.Count);
        sb.Append(",\"bakingSet\":").Append(Quote(bakingSet));
        sb.Append(",\"hasBakedData\":").Append(Bool(apvBaked));
        sb.Append(",\"loaded\":").Append(Bool(ProbeReferenceVolume.instance != null && ProbeReferenceVolume.instance.isInitialized));
        sb.Append("}}");

        bool anyBake = maps.Length > 0 || bakedOrMixed > 0;
        bool anyProbes = apvOnAsset ? apvBaked : bakedCount > 0;
        if (anyBake && dynamic > 0 && !anyProbes)
            findings.Add(new Finding
            {
                check = "dynamic-without-probes", path = "",
                detail = dynamic + " renderer(s) do not contribute GI and there are no baked probes: they get the ambient probe only, with no bounce and no baked light"
            });
        if (apvOnAsset && probeGroups.Count > 0)
            Add(findings, "probe-groups-ignored", probeGroups[0],
                probeGroups.Count + " Light Probe Group(s), and the URP asset's Light Probe System is Adaptive Probe Volumes: the groups are not sampled");
        if (urp != null && !apvOnAsset && probeVolumes.Count > 0)
            Add(findings, "probe-volume-ignored", probeVolumes[0],
                probeVolumes.Count + " Probe Volume(s), and the URP asset's Light Probe System is Light Probe Groups: set it to Adaptive Probe Volumes");

        // ---------------------------------------------------------------- reflection probes
        int activeProbes = 0;
        sb.Append(",\"reflectionProbes\":[");
        for (int i = 0; i < reflectionProbes.Count; i++)
        {
            ReflectionProbe p = reflectionProbes[i];
            bool on = p.enabled && p.gameObject.activeInHierarchy;
            if (on) activeProbes++;
            bool hasTexture = p.mode == ReflectionProbeMode.Custom ? p.customBakedTexture != null : p.bakedTexture != null;

            if (i > 0) sb.Append(',');
            sb.Append("{\"path\":").Append(Quote(PathOf(p.transform)));
            sb.Append(",\"mode\":").Append(Quote(p.mode.ToString()));
            sb.Append(",\"refresh\":").Append(Quote(p.mode == ReflectionProbeMode.Realtime ? p.refreshMode.ToString() : "n/a"));
            sb.Append(",\"boxProjection\":").Append(Bool(p.boxProjection));
            sb.Append(",\"resolution\":").Append(p.resolution);
            sb.Append(",\"importance\":").Append(p.importance);
            sb.Append(",\"blendDistance\":").Append(Num(p.blendDistance));
            sb.Append(",\"hasTexture\":").Append(Bool(hasTexture));
            sb.Append(",\"active\":").Append(Bool(on)).Append('}');

            if (!on) continue;
            if (p.boxProjection && urp != null && !urp.reflectionProbeBoxProjection)
                Add(findings, "box-projection-off-in-asset", p,
                    "Box Projection is ticked on the probe and off on the URP asset (Lighting > Reflection Probes): the reflection is not projected");
            if (p.mode == ReflectionProbeMode.Baked && !hasTexture)
                Add(findings, "baked-probe-without-texture", p, "Baked probe with no cubemap: bake the scene or the probe");
        }
        sb.Append(']');
        if (activeProbes > 1 && urp != null && !urp.reflectionProbeBlending)
            findings.Add(new Finding
            {
                check = "probe-blending-off-in-asset", path = "",
                detail = activeProbes + " reflection probes and Probe Blending is off on the URP asset: reflections pop at each probe's boundary"
            });

        // ---------------------------------------------------------------- environment
        Material sky = RenderSettings.skybox;
        Light sun = RenderSettings.sun;
        sb.Append(",\"environment\":{\"skybox\":").Append(Quote(sky != null ? sky.name + " (" + sky.shader.name + ")" : "none"));
        sb.Append(",\"sun\":").Append(Quote(sun != null ? PathOf(sun.transform) : "none"));
        sb.Append(",\"ambientMode\":").Append(Quote(RenderSettings.ambientMode.ToString()));
        sb.Append(",\"ambientIntensity\":").Append(Num(RenderSettings.ambientIntensity));
        sb.Append(",\"ambientColour\":").Append(Quote(ColorUtility.ToHtmlStringRGB(RenderSettings.ambientLight)));
        sb.Append(",\"reflectionSource\":").Append(Quote(RenderSettings.defaultReflectionMode.ToString()));
        sb.Append(",\"reflectionIntensity\":").Append(Num(RenderSettings.reflectionIntensity));
        sb.Append(",\"fog\":").Append(Bool(RenderSettings.fog));
        sb.Append(",\"fogMode\":").Append(Quote(RenderSettings.fogMode.ToString()));
        sb.Append(",\"fogDensity\":").Append(Num(RenderSettings.fogDensity));
        sb.Append(",\"fogStart\":").Append(Num(RenderSettings.fogStartDistance));
        sb.Append(",\"fogEnd\":").Append(Num(RenderSettings.fogEndDistance)).Append('}');

        if (RenderSettings.reflectionIntensity <= 0f ||
            (RenderSettings.defaultReflectionMode == DefaultReflectionMode.Custom && RenderSettings.customReflectionTexture == null))
            findings.Add(new Finding
            {
                check = "no-environment-reflection", path = "",
                detail = "the environment reflection is empty (Custom with no cubemap, or Intensity Multiplier 0): metallic and smooth surfaces render black outside every probe"
            });

        // ---------------------------------------------------------------- findings
        var counts = new SortedDictionary<string, int>();
        foreach (Finding f in findings)
        {
            counts.TryGetValue(f.check, out int n);
            counts[f.check] = n + 1;
        }
        sb.Append(",\"ok\":").Append(Bool(findings.Count == 0));
        sb.Append(",\"counts\":{");
        bool first = true;
        foreach (KeyValuePair<string, int> kv in counts)
        {
            if (!first) sb.Append(',');
            first = false;
            sb.Append(Quote(kv.Key)).Append(':').Append(kv.Value);
        }
        sb.Append("},\"findings\":[");
        for (int i = 0; i < findings.Count; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append("{\"check\":").Append(Quote(findings[i].check));
            sb.Append(",\"path\":").Append(Quote(findings[i].path));
            sb.Append(",\"detail\":").Append(Quote(findings[i].detail)).Append('}');
        }
        return sb.Append("]}").ToString();
    }

    static void Add(List<Finding> findings, string check, Component on, string detail) =>
        findings.Add(new Finding { check = check, path = PathOf(on.transform), detail = detail });

    static string PathOf(Transform t)
    {
        var sb = new StringBuilder(t.name);
        for (t = t.parent; t != null; t = t.parent) sb.Insert(0, t.name + "/");
        return sb.ToString();
    }

    static string Bool(bool b) => b ? "true" : "false";

    static string Num(float f) =>
        float.IsNaN(f) || float.IsInfinity(f)
            ? "null"
            : f.ToString("0.####", System.Globalization.CultureInfo.InvariantCulture);

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
