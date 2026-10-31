// SecondaryMotionSetup — builds the spring chains, the body colliders and the
// SecondaryMotionSystem on a character from its secondary/1 file (<name>.secondary.json, written
// beside the body FBX by the rig side). Re-runnable: it removes every spring component and
// SM_Collider_* object under the model first and builds again from the file.
//
// Drop into an Editor folder; the runtime files (SpringSolver, SpringChain, SpringCollider,
// SecondaryMotionSystem, SecondarySpec) go in a runtime folder. No package needed.
//
//   Tools/Unity Dev/Rigged Character/Add Secondary Motion   select the character prefab (or a scene
//                                                            instance) first; logs "[RIGGED-CHAR] {json}"
//   SecondaryMotionSetup.Setup(root, specPath)               returns the same JSON, for an eval
//   Unity -batchmode -quit -projectPath . \
//     -executeMethod UnityDev.SecondaryMotion.SecondaryMotionSetup.SetupFromCommandLine \
//     -character Assets/Characters/Runner/Runner.prefab [-spec Assets/Characters/Runner/Runner.secondary.json] \
//     [-out Assets/Characters/Runner/Runner_Secondary.prefab]
//     exit 0 built, 2 refused, 1 usage error, 3 harness error
//
// It refuses (and changes nothing) when: the file is not secondary/1; Optimize Game Objects is on
// (the bones would not skin the mesh); a cc_ bone is missing (the FBX predates the chains); a chain
// bone is not under the one before it; or the rest position the file gives for a chain's parent
// bone is more than 1 cm from that bone's bind pose (axis or scale mismatch at export).
// A chain joint that starts inside a collider of its group would pop on frame one: that collider is
// shrunk (to no less than half its radius) or dropped from that chain's group, and the JSON says so.
// A file with no chains (nothing loose on the body) removes what an earlier run built and adds nothing.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace UnityDev.SecondaryMotion
{
    public static class SecondaryMotionSetup
    {
        const string MenuPath = "Tools/Unity Dev/Rigged Character/Add Secondary Motion";
        public const string ColliderPrefix = "SM_Collider_";
        const float SelfCheckTolerance = 0.01f;     // metres

        [MenuItem(MenuPath)]
        static void Menu()
        {
            GameObject go = Selection.activeGameObject;
            if (go == null) { Debug.LogError("[RIGGED-CHAR] select the character prefab or a scene instance first"); return; }
            string prefabPath = AssetDatabase.GetAssetPath(go);
            if (!string.IsNullOrEmpty(prefabPath) && !prefabPath.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase))
            {
                // an imported model asset cannot hold components: a prefab or a scene instance can
                Debug.LogError("[RIGGED-CHAR] " + prefabPath + " is a model, not a prefab: select the character prefab or a " +
                               "scene instance (batch: -character <model> writes <name>_Secondary.prefab)");
                return;
            }
            if (string.IsNullOrEmpty(prefabPath) && PrefabUtility.IsPartOfPrefabInstance(go))
                prefabPath = PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(go);
            if (!string.IsNullOrEmpty(prefabPath) && prefabPath.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase))
            {
                GameObject root = PrefabUtility.LoadPrefabContents(prefabPath);
                try
                {
                    string spec = FindSpec(root);
                    string result = Setup(root, spec);
                    if (result.Contains("\"ok\":true")) PrefabUtility.SaveAsPrefabAsset(root, prefabPath);
                    Debug.Log("[RIGGED-CHAR] " + result);
                }
                finally { PrefabUtility.UnloadPrefabContents(root); }
                return;
            }
            Debug.Log("[RIGGED-CHAR] " + Setup(go, FindSpec(go)));
        }

        /// <summary>For -executeMethod. Exits 0 built, 2 refused, 1 usage error, 3 harness error.</summary>
        public static void SetupFromCommandLine()
        {
            int code;
            try { code = Run(Environment.GetCommandLineArgs()); }
            catch (Exception e)
            {
                Debug.LogError("[RIGGED-CHAR] secondary: harness error: " + e);
                code = 3;
            }
            EditorApplication.Exit(code);
        }

        /// <summary>The command-line run without exiting. Returns the exit code.</summary>
        public static int Run(string[] argv)
        {
            string character = null, spec = null, output = null;
            for (int i = 0; i + 1 < argv.Length; i++)
            {
                if (argv[i] == "-character") character = argv[++i];
                else if (argv[i] == "-spec") spec = argv[++i];
                else if (argv[i] == "-out") output = argv[++i];
            }
            if (string.IsNullOrEmpty(character))
            {
                Debug.LogError("[RIGGED-CHAR] secondary: usage: -character <prefab or model> [-spec <secondary.json>] [-out <prefab>]");
                return 1;
            }
            var asset = AssetDatabase.LoadAssetAtPath<GameObject>(character);
            if (asset == null) { Debug.LogError("[RIGGED-CHAR] secondary: no GameObject asset at " + character); return 1; }

            bool isPrefab = character.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase);
            if (string.IsNullOrEmpty(output))
                output = isPrefab ? character
                       : Path.Combine(Path.GetDirectoryName(character) ?? "", Path.GetFileNameWithoutExtension(character) + "_Secondary.prefab").Replace('\\', '/');

            GameObject root = isPrefab ? PrefabUtility.LoadPrefabContents(character)
                                       : (GameObject)PrefabUtility.InstantiatePrefab(asset);
            try
            {
                if (string.IsNullOrEmpty(spec)) spec = FindSpec(root);
                string result = Setup(root, spec);
                Debug.Log("[RIGGED-CHAR] " + result);
                if (!result.Contains("\"ok\":true")) return 2;
                PrefabUtility.SaveAsPrefabAsset(root, output, out bool saved);
                if (!saved) { Debug.LogError("[RIGGED-CHAR] secondary: could not save " + output); return 3; }
                return 0;
            }
            finally
            {
                if (isPrefab) PrefabUtility.UnloadPrefabContents(root);
                else Object.DestroyImmediate(root);
            }
        }

        /// <summary><name>.secondary.json beside the FBX that holds the character's skinned mesh.</summary>
        public static string FindSpec(GameObject root)
        {
            foreach (SkinnedMeshRenderer smr in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                string model = smr.sharedMesh != null ? AssetDatabase.GetAssetPath(smr.sharedMesh) : null;
                if (string.IsNullOrEmpty(model)) continue;
                string spec = Path.Combine(Path.GetDirectoryName(model) ?? "",
                                           Path.GetFileNameWithoutExtension(model) + ".secondary.json").Replace('\\', '/');
                if (File.Exists(spec)) return spec;
            }
            return null;
        }

        /// <summary>Builds the components on root (a loaded prefab's contents or a scene object)
        /// from the secondary/1 file at specPath. Returns the [RIGGED-CHAR] JSON; "ok":false names
        /// why and leaves root unchanged.</summary>
        public static string Setup(GameObject root, string specPath)
        {
            var report = new Report { spec = specPath };
            if (root == null) return report.Refuse("no character");
            report.character = root.name;
            if (string.IsNullOrEmpty(specPath) || !File.Exists(specPath))
                return report.Refuse("no secondary/1 file" + (string.IsNullOrEmpty(specPath) ? " beside the model FBX (<name>.secondary.json); pass -spec" : " at " + specPath));
            if (!SecondarySpec.TryParse(File.ReadAllText(specPath), out SecondarySpec spec, out string error))
                return report.Refuse(specPath + ": " + error);

            Animator animator = root.GetComponentInChildren<Animator>(true);
            GameObject model = animator != null ? animator.gameObject : root;
            if (animator == null) report.warnings.Add("no Animator under " + root.name + ": the system goes on the root");

            // nothing loose on the body: take off what an earlier run built, add nothing
            if (spec.chains.Length == 0)
            {
                Clear(root, model);
                EditorUtility.SetDirty(model);
                report.warnings.Add("the file lists no chains: nothing to simulate, no system added");
                report.ok = true;
                return report.Json();
            }

            SkinnedMeshRenderer skin = null;
            foreach (SkinnedMeshRenderer smr in model.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                if (skin == null || smr.bones.Length > skin.bones.Length) skin = smr;
            if (skin != null && skin.sharedMesh != null &&
                AssetImporter.GetAtPath(AssetDatabase.GetAssetPath(skin.sharedMesh)) is ModelImporter importer &&
                importer.optimizeGameObjects)
                return report.Refuse(importer.assetPath + ": Optimize Game Objects is on — chain bones would not skin the mesh. Turn it off on the Rig tab and reimport");
            if (animator != null && animator.isActiveAndEnabled && !animator.hasTransformHierarchy)
                return report.Refuse(model.name + ": the Animator has no transform hierarchy (Optimize Game Objects) — turn it off");

            // ---- resolve every bone first; refuse before touching anything
            var byName = new Dictionary<string, Transform>();
            foreach (Transform t in model.GetComponentsInChildren<Transform>(true))
                if (!byName.ContainsKey(t.name)) byName[t.name] = t;
            Transform Resolve(string boneName, string role)
            {
                if (!string.IsNullOrEmpty(boneName) && byName.TryGetValue(boneName, out Transform t)) return t;
                if (animator != null && animator.isHuman && !string.IsNullOrEmpty(role) &&
                    Enum.TryParse(role, out HumanBodyBones hb) && hb != HumanBodyBones.LastBone)
                    return animator.GetBoneTransform(hb);
                return null;
            }

            var missing = new List<string>();
            var chainBones = new Transform[spec.chains.Length][];
            var parents = new Transform[spec.chains.Length];
            for (int c = 0; c < spec.chains.Length; c++)
            {
                SecondaryChainSpec cs = spec.chains[c];
                parents[c] = Resolve(cs.parent, cs.parentRole);
                if (parents[c] == null) missing.Add(cs.parent);
                chainBones[c] = new Transform[cs.bones.Length];
                for (int i = 0; i < cs.bones.Length; i++)
                {
                    chainBones[c][i] = Resolve(cs.bones[i], null);
                    if (chainBones[c][i] == null) missing.Add(cs.bones[i]);
                }
            }
            var colliderA = new Transform[spec.colliders.Length];
            var colliderB = new Transform[spec.colliders.Length];
            for (int k = 0; k < spec.colliders.Length; k++)
            {
                SecondaryColliderSpec cs = spec.colliders[k];
                colliderA[k] = Resolve(cs.a, cs.aRole);
                if (colliderA[k] == null) missing.Add(cs.a);
                if (cs.shape == "capsule")
                {
                    colliderB[k] = Resolve(cs.b, cs.bRole);
                    if (colliderB[k] == null) missing.Add(cs.b);
                }
            }
            if (missing.Count > 0)
                return report.Refuse("bones not in " + model.name + ": " + string.Join(", ", missing) +
                                     " — the FBX predates the chains, or Optimize Game Objects stripped them");

            for (int c = 0; c < spec.chains.Length; c++)
            {
                Transform[] b = chainBones[c];
                for (int i = 1; i < b.Length; i++)
                    if (b[i] == b[i - 1] || !b[i].IsChildOf(b[i - 1]))
                        return report.Refuse("chain " + spec.chains[c].name + ": " + b[i].name + " is not under " + b[i - 1].name);
                if (!b[0].IsChildOf(parents[c]) || b[0] == parents[c])
                    report.warnings.Add("chain " + spec.chains[c].name + ": " + b[0].name + " is not under " + parents[c].name);
            }

            // ---- frame self-check: the file's rest head of each parent against its bind pose
            for (int c = 0; c < spec.chains.Length; c++)
            {
                SecondaryChainSpec cs = spec.chains[c];
                if (!cs.hasParentHead) continue;
                Vector3 want = SecondarySpec.ToUnity(cs.parentHead);
                Vector3 have = RestInModel(model.transform, skin, parents[c]);
                float off = Vector3.Distance(want, have);
                if (off > SelfCheckTolerance)
                    return report.Refuse("chain " + cs.name + ": " + parents[c].name + " rest head is " + off.ToString("0.000") +
                                         " m from where the file puts it — axis or scale mismatch: export with FBX_SCALE_ALL and unit scale applied, import with Convert Units on");
                report.selfChecked++;
            }
            for (int c = 0; c < spec.chains.Length; c++)
            {
                SecondaryChainSpec cs = spec.chains[c];
                if (cs.joints == null) continue;
                for (int i = 0; i < cs.joints.Length; i++)
                {
                    Vector3 have = model.transform.InverseTransformPoint(chainBones[c][i].position);
                    float off = Vector3.Distance(SecondarySpec.ToUnity(cs.joints[i]), have);
                    if (off > SelfCheckTolerance)
                    {
                        report.warnings.Add("chain " + cs.name + ": " + cs.bones[i] + " sits " + off.ToString("0.000") + " m from its rest joint in the file");
                        break;
                    }
                }
            }

            // ---- rebuild from clean
            Clear(root, model);

            float scale = Mathf.Abs(model.transform.lossyScale.x);
            var colliderByName = new Dictionary<string, SpringCollider>();
            for (int k = 0; k < spec.colliders.Length; k++)
            {
                SecondaryColliderSpec cs = spec.colliders[k];
                var go = new GameObject(ColliderPrefix + cs.name);
                go.transform.SetParent(colliderA[k], false);
                var col = go.AddComponent<SpringCollider>();
                col.radius = cs.radius;
                if (cs.shape == "capsule")
                {
                    col.shape = SpringCollider.Shape.Capsule;
                    col.endB = colliderB[k];
                    col.inset = cs.inset;
                }
                else
                {
                    col.shape = SpringCollider.Shape.Sphere;
                    if (cs.hasCenter)
                        col.localCenter = go.transform.InverseTransformPoint(model.transform.TransformPoint(SecondarySpec.ToUnity(cs.center)));
                }
                colliderByName[cs.name] = col;
            }
            var allColliders = new List<SpringCollider>(colliderByName.Values);

            var chains = new SpringChain[spec.chains.Length];
            for (int c = 0; c < spec.chains.Length; c++)
            {
                SecondaryChainSpec cs = spec.chains[c];
                var chain = chainBones[c][0].gameObject.AddComponent<SpringChain>();
                chain.bones = chainBones[c];
                chain.stiffness = cs.stiffness;
                chain.drag = cs.drag;
                chain.gravity = cs.gravity;
                chain.wind = cs.wind;
                chain.radius = cs.radius;
                chain.inertia = cs.inertia;
                chain.maxAngle = Mathf.Clamp(cs.maxAngleDeg, 1f, 180f);
                // Always an explicit group, so a collider dropped below leaves the others in force.
                chain.useAllColliders = false;
                var group = new List<SpringCollider>();
                if (cs.hasColliders) foreach (string n in cs.colliders) group.Add(colliderByName[n]);
                else group.AddRange(allColliders);
                chain.colliders = group.ToArray();
                chain.CaptureRest();
                chains[c] = chain;
                report.bones += cs.bones.Length;
            }

            // ---- rest penetration: no joint but the pinned first one may start inside its colliders
            var originalRadius = new Dictionary<SpringCollider, float>();
            foreach (SpringCollider col in allColliders) originalRadius[col] = col.radius;
            foreach (SpringChain chain in chains)
            {
                var keep = new List<SpringCollider>(chain.colliders);
                for (int i = 1; i < chain.bones.Length; i++)
                {
                    Vector3 p = chain.bones[i].position;
                    for (int g = keep.Count - 1; g >= 0; g--)
                    {
                        SpringCollider col = keep[g];
                        col.GetWorld(scale, out Vector3 a, out Vector3 b, out float r);
                        float axis = Vector3.Distance(p, SpringSolver.ClosestOnSegment(a, b, p));
                        float allowed = (axis / scale) - chain.radius - 0.001f;   // model units, 1 mm margin
                        if (allowed >= col.radius) continue;
                        if (allowed >= 0.5f * originalRadius[col])
                        {
                            col.radius = allowed;
                            report.Shrunk(col.name.Substring(ColliderPrefix.Length));
                        }
                        else
                        {
                            keep.RemoveAt(g);
                            report.dropped.Add(chain.name + ":" + col.name.Substring(ColliderPrefix.Length));
                        }
                    }
                }
                chain.colliders = keep.ToArray();
                report.particles += chain.bones.Length;
            }

            var system = model.AddComponent<SecondaryMotionSystem>();
            report.chains = chains.Length;
            report.colliders = allColliders.Count;
            EditorUtility.SetDirty(model);
            foreach (SpringChain chain in chains) EditorUtility.SetDirty(chain);
            foreach (SpringCollider col in allColliders) EditorUtility.SetDirty(col);
            EditorUtility.SetDirty(system);
            report.ok = true;
            return report.Json();
        }

        /// <summary>Removes every spring component and SM_Collider_* object an earlier run built.</summary>
        static void Clear(GameObject root, GameObject model)
        {
            foreach (SpringChain old in model.GetComponentsInChildren<SpringChain>(true)) Object.DestroyImmediate(old);
            foreach (SecondaryMotionSystem old in root.GetComponentsInChildren<SecondaryMotionSystem>(true)) Object.DestroyImmediate(old);
            var stale = new List<GameObject>();
            foreach (Transform t in model.GetComponentsInChildren<Transform>(true))
                if (t.name.StartsWith(ColliderPrefix, StringComparison.Ordinal)) stale.Add(t.gameObject);
            foreach (SpringCollider old in model.GetComponentsInChildren<SpringCollider>(true))
                if (!stale.Contains(old.gameObject)) Object.DestroyImmediate(old);
            foreach (GameObject go in stale) if (go != null) Object.DestroyImmediate(go);
        }

        /// <summary>A bone's rest head in the model's local space: from the skin's bind pose when the
        /// bone skins the mesh (a tip or lightly weighted bone may not), else its current position.</summary>
        static Vector3 RestInModel(Transform model, SkinnedMeshRenderer skin, Transform bone)
        {
            if (skin != null && skin.sharedMesh != null)
            {
                Transform[] bones = skin.bones;
                Matrix4x4[] bind = skin.sharedMesh.bindposes;
                int j = Array.IndexOf(bones, bone);
                if (j >= 0 && j < bind.Length)
                {
                    Vector3 inSkin = bind[j].inverse.GetColumn(3);
                    return model.InverseTransformPoint(skin.transform.TransformPoint(inSkin));
                }
            }
            return model.InverseTransformPoint(bone.position);
        }

        sealed class Report
        {
            public string character, spec;
            public bool ok;
            public int chains, bones, colliders, particles, selfChecked;
            public readonly List<string> shrunk = new List<string>(), dropped = new List<string>(), warnings = new List<string>();
            string refused;

            public void Shrunk(string n) { if (!shrunk.Contains(n)) shrunk.Add(n); }

            public string Refuse(string why) { ok = false; refused = why; return Json(); }

            public string Json()
            {
                var sb = new StringBuilder(256);
                sb.Append("{\"step\":\"secondary\",\"ok\":").Append(ok ? "true" : "false");
                sb.Append(",\"character\":").Append(Q(character));
                sb.Append(",\"spec\":").Append(Q(spec));
                sb.Append(",\"chains\":").Append(chains);
                sb.Append(",\"bones\":").Append(bones);
                sb.Append(",\"particles\":").Append(particles);
                sb.Append(",\"colliders\":").Append(colliders);
                sb.Append(",\"self_checked\":").Append(selfChecked);
                sb.Append(",\"shrunk\":").Append(Arr(shrunk));
                sb.Append(",\"dropped\":").Append(Arr(dropped));
                sb.Append(",\"warnings\":").Append(Arr(warnings));
                sb.Append(",\"refused\":").Append(Q(refused));
                return sb.Append('}').ToString();
            }

            static string Arr(List<string> items)
            {
                var sb = new StringBuilder("[");
                for (int i = 0; i < items.Count; i++) sb.Append(i > 0 ? "," : "").Append(Q(items[i]));
                return sb.Append(']').ToString();
            }

            static string Q(string s)
            {
                if (s == null) return "null";
                var sb = new StringBuilder("\"");
                foreach (char c in s)
                {
                    if (c == '"' || c == '\\') sb.Append('\\').Append(c);
                    else if (c == '\n') sb.Append("\\n");
                    else if (c < ' ') sb.Append("\\u").Append(((int)c).ToString("x4"));
                    else sb.Append(c);
                }
                return sb.Append('"').ToString();
            }
        }
    }
}
