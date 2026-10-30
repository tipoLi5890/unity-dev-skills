// Phase 2: turn the old post-processing stack into a URP VolumeProfile that survives a
// reload, wire the open scene to it, and switch the legacy components off so the capture
// shows one stack rather than two.
//
// Put this under Assets/Editor/, let Unity compile, then call it with one line:
//   unity command eval --code 'return UnityDev.UrpMigration.VolumeMigration.Run();'
//
// The one step that is easy to skip and impossible to see: VolumeProfile.Add creates the
// override object but does not make it a sub-asset of the profile. Without
// AssetDatabase.AddObjectToAsset the profile saves, reloads with components: [] or
// {fileID: 0} entries, and every tool log along the way said it worked.
//
// Confirm on your version: the legacy stack's type names are read as strings, so this file
// compiles whether or not that package is installed. If the project uses a differently
// namespaced fork, print the FullName of one of its components and widen LegacyPrefix.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace UnityDev.UrpMigration
{
    public static class VolumeMigration
    {
        const string LegacyPrefix = "UnityEngine.Rendering.PostProcessing.";

        // Legacy effect name -> the URP override types that carry it. Names not in this map
        // are reported as manual work rather than approximated.
        static readonly Dictionary<string, Type[]> Mapping = new Dictionary<string, Type[]>(StringComparer.Ordinal)
        {
            { "Bloom", new[] { typeof(Bloom) } },
            { "ColorGrading", new[] { typeof(ColorAdjustments), typeof(Tonemapping) } },
            { "Vignette", new[] { typeof(Vignette) } },
            { "DepthOfField", new[] { typeof(DepthOfField) } },
            { "MotionBlur", new[] { typeof(MotionBlur) } },
            { "ChromaticAberration", new[] { typeof(ChromaticAberration) } },
            { "Grain", new[] { typeof(FilmGrain) } },
            { "LensDistortion", new[] { typeof(LensDistortion) } }
        };

        // No URP Volume override is equivalent to these; naming them is the honest answer.
        static readonly Dictionary<string, string> ManualOnly = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            { "AutoExposure", "no Volume equivalent — start from ColorAdjustments.postExposure" },
            { "AmbientOcclusion", "SSAO is a renderer feature, not a Volume override" },
            { "ScreenSpaceReflections", "unsupported — needs a renderer feature or a replacement" }
        };

        // What a project with no legacy stack still wants on a first URP profile.
        static readonly Type[] DefaultOverrides =
        {
            typeof(Bloom), typeof(ColorAdjustments), typeof(Tonemapping), typeof(Vignette)
        };

        [MenuItem("Tools/Unity Dev/URP Migration/Post-processing")]
        public static void RunFromMenu()
        {
            Run();
        }

        /// <summary>
        /// Build (or repair) the profile at <paramref name="profilePath"/>, wire the open
        /// scene to it, and optionally disable the legacy components. Returns one readback
        /// line built from the reloaded profile and the saved scene text.
        /// </summary>
        public static string Run(string profilePath = "Assets/Settings/Migrated-PostProcess.asset",
                                 bool disableLegacy = true)
        {
            var manual = new List<string>();
            var wanted = DiscoverWantedOverrides(manual);

            var directory = Path.GetDirectoryName(profilePath);
            if (!string.IsNullOrEmpty(directory) && !Directory.Exists(directory))
                Directory.CreateDirectory(directory);

            var profile = AssetDatabase.LoadAssetAtPath<VolumeProfile>(profilePath);
            if (profile == null)
            {
                profile = ScriptableObject.CreateInstance<VolumeProfile>();
                AssetDatabase.CreateAsset(profile, profilePath);
            }

            foreach (var type in wanted)
                AddPersistentOverride(profile, type);

            EditorUtility.SetDirty(profile);
            AssetDatabase.SaveAssets();
            AssetDatabase.ImportAsset(profilePath);

            // Readback 1: the profile as it comes back off disk, not the object just edited.
            var reloaded = AssetDatabase.LoadAssetAtPath<VolumeProfile>(profilePath);
            if (reloaded == null)
                throw new Exception("Profile at " + profilePath + " did not reload -- nothing was persisted.");

            var live = reloaded.components.Where(c => c != null).ToList();
            var nullEntries = reloaded.components.Count - live.Count;

            // Scene wiring. Reuse an existing URP Volume where there is one; a second global
            // Volume in the same scene is a blend nobody asked for.
            var volume = UnityEngine.Object.FindFirstObjectByType<Volume>();
            if (volume == null)
            {
                var go = new GameObject("URP Global Volume");
                volume = go.AddComponent<Volume>();
            }
            volume.isGlobal = true;
            volume.enabled = true;
            volume.sharedProfile = reloaded;   // sharedProfile at Editor time: `profile` clones
            EditorUtility.SetDirty(volume);

            var camPostProcessing = false;
            var camera = Camera.main;
            if (camera != null)
            {
                var data = camera.GetComponent<UniversalAdditionalCameraData>();
                if (data == null) data = camera.gameObject.AddComponent<UniversalAdditionalCameraData>();
                data.renderPostProcessing = true;
                camPostProcessing = data.renderPostProcessing;
                EditorUtility.SetDirty(data);
            }

            int legacyTotal = 0, legacyDisabled = 0;
            foreach (var behaviour in UnityEngine.Object.FindObjectsByType<Behaviour>(FindObjectsSortMode.None))
            {
                if (behaviour == null) continue;
                var fullName = behaviour.GetType().FullName ?? string.Empty;
                if (!fullName.StartsWith(LegacyPrefix, StringComparison.Ordinal)) continue;

                legacyTotal++;
                if (!disableLegacy) continue;

                behaviour.enabled = false;
                legacyDisabled++;
                EditorUtility.SetDirty(behaviour);
            }

            var scene = volume.gameObject.scene;
            EditorSceneManager.MarkSceneDirty(scene);
            var sceneSaved = EditorSceneManager.SaveScene(scene);

            // Readback 2: the saved scene text. SaveAssets writes the profile; only SaveScene
            // writes the Volume that references it, and only the file proves which happened.
            var profileGuid = AssetDatabase.AssetPathToGUID(profilePath);
            var sceneReferencesProfile = false;
            if (!string.IsNullOrEmpty(scene.path) && File.Exists(scene.path))
            {
                var text = File.ReadAllText(scene.path);
                sceneReferencesProfile = !string.IsNullOrEmpty(profileGuid) && text.Contains(profileGuid);
            }

            // The legacy readback re-asks the components and then asks whether the write landed.
            // Grepping the saved scene for "m_Enabled: 0" would prove nothing: every disabled
            // component in the scene emits that line, including the ones nobody touched.
            var legacyStillEnabled = UnityEngine.Object
                .FindObjectsByType<Behaviour>(FindObjectsSortMode.None)
                .Count(b => b != null && b.enabled &&
                            (b.GetType().FullName ?? string.Empty).StartsWith(LegacyPrefix, StringComparison.Ordinal));
            var legacyDisableSaved = !disableLegacy || legacyTotal == 0 ||
                                     (legacyStillEnabled == 0 && sceneSaved && !scene.isDirty);

            var status = nullEntries == 0 && live.Count > 0 && sceneReferencesProfile &&
                         camPostProcessing && legacyDisableSaved && manual.Count == 0
                ? "complete"
                : "partial";

            var line = "[URP-MIG] postfx status=" + status +
                       " profile=" + profilePath +
                       " overrides=" + (live.Count == 0 ? "none" : string.Join(",", live.Select(c => c.GetType().Name))) +
                       " nullEntries=" + nullEntries +
                       " sceneVolume=" + (sceneReferencesProfile ? volume.gameObject.name : "NOT-IN-SAVED-SCENE") +
                       " camPostProcessing=" + camPostProcessing +
                       " legacyDisabled=" + legacyDisabled + "/" + legacyTotal +
                       " manual=" + (manual.Count == 0 ? "none" : string.Join(",", manual)) +
                       " scene=" + (string.IsNullOrEmpty(scene.path) ? "unsaved" : scene.path);

            Debug.Log(line);
            return line;
        }

        // Ask the open scene which legacy effects are actually configured, by type name, and
        // translate only the ones with a real URP counterpart. An empty answer falls back to
        // the four overrides a first URP grade almost always wants.
        static List<Type> DiscoverWantedOverrides(List<string> manual)
        {
            var found = new HashSet<string>(StringComparer.Ordinal);

            foreach (var behaviour in UnityEngine.Object.FindObjectsByType<Behaviour>(FindObjectsSortMode.None))
            {
                if (behaviour == null) continue;
                var fullName = behaviour.GetType().FullName ?? string.Empty;
                if (fullName != LegacyPrefix + "PostProcessVolume") continue;

                var profileProperty = behaviour.GetType().GetProperty(
                    "sharedProfile", BindingFlags.Public | BindingFlags.Instance);
                var legacyProfile = profileProperty == null ? null : profileProperty.GetValue(behaviour, null);
                if (legacyProfile == null) continue;

                var settingsField = legacyProfile.GetType().GetField(
                    "settings", BindingFlags.Public | BindingFlags.Instance);
                var settings = settingsField == null ? null : settingsField.GetValue(legacyProfile) as System.Collections.IEnumerable;
                if (settings == null) continue;

                foreach (var setting in settings)
                {
                    if (setting == null) continue;
                    found.Add(setting.GetType().Name);
                }
            }

            var types = new List<Type>();
            foreach (var name in found)
            {
                Type[] mapped;
                if (Mapping.TryGetValue(name, out mapped))
                {
                    foreach (var type in mapped)
                        if (!types.Contains(type)) types.Add(type);
                    continue;
                }

                string reason;
                manual.Add(ManualOnly.TryGetValue(name, out reason) ? name + "(" + reason + ")" : name + "(unmapped)");
            }

            if (types.Count == 0)
                types.AddRange(DefaultOverrides);

            return types;
        }

        static VolumeComponent AddPersistentOverride(VolumeProfile profile, Type type)
        {
            VolumeComponent existing;
            if (profile.TryGet(type, out existing) && existing != null)
                return existing;

            // Add(type, true) switches overrideState on for every parameter; without the flag
            // the component reads back correctly and contributes nothing to the frame.
            var component = profile.Add(type, true);
            component.name = type.Name;
            AssetDatabase.AddObjectToAsset(component, profile);
            EditorUtility.SetDirty(component);
            EditorUtility.SetDirty(profile);
            return component;
        }
    }
}
