// PrefabOverrideAudit.cs — a read-only list of the prefab instances in the open scene that
// carry overrides, by kind, printed as one JSON object. It changes nothing: no instance is
// reverted, applied or unpacked.
//
// Drop into an Editor folder. No package needed.
//
//   Tools/Unity Dev/3D Level/Audit Prefab Overrides     logs "[PREFAB-OVERRIDES] {json}"
//   PrefabOverrideAudit.Audit()                         returns the same JSON, for an eval or a test
//
// Only outermost instance roots are listed; an override on a nested prefab is reported on the
// instance that holds it. Position, rotation, name and sibling order of the root are what Unity
// calls default overrides — every placed instance has them — and are left out. Kinds:
//
//   property            a serialised value differs from the asset (listed as Type.path)
//   added-component     a component that exists only on this instance
//   removed-component   a component of the asset removed on this instance
//   added-object        a child GameObject that exists only on this instance
//   removed-object      a child of the asset deleted on this instance
//   missing-asset       the instance's prefab asset no longer exists
//
// A scale override on the root is a `property` and is also counted under `scaled`: on a kit
// piece it is the override that takes the piece off the grid — reference/prefab-architecture.md.
using System.Collections.Generic;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

public static class PrefabOverrideAudit
{
    const string MenuPath = "Tools/Unity Dev/3D Level/Audit Prefab Overrides";
    const int MaxPropertiesListed = 12;

    [MenuItem(MenuPath)]
    static void Menu() => Debug.Log("[PREFAB-OVERRIDES] " + Audit());

    public static string Audit()
    {
        Scene scene = SceneManager.GetActiveScene();
        var totals = new SortedDictionary<string, int>();
        var rows = new StringBuilder(1024);
        int instances = 0, withOverrides = 0, scaled = 0;

        foreach (GameObject sceneRoot in scene.GetRootGameObjects())
        {
            foreach (Transform t in sceneRoot.GetComponentsInChildren<Transform>(true))
            {
                GameObject go = t.gameObject;
                if (!PrefabUtility.IsOutermostPrefabInstanceRoot(go)) continue;
                instances++;

                var kinds = new SortedDictionary<string, int>();
                var properties = new List<string>();
                bool rootScaled = false;

                if (PrefabUtility.GetPrefabInstanceStatus(go) == PrefabInstanceStatus.MissingAsset)
                    kinds["missing-asset"] = 1;

                PropertyModification[] mods = PrefabUtility.GetPropertyModifications(go);
                if (mods != null)
                {
                    Object rootSource = PrefabUtility.GetCorrespondingObjectFromSource(go.transform);
                    foreach (PropertyModification mod in mods)
                    {
                        if (mod == null || mod.target == null || PrefabUtility.IsDefaultOverride(mod)) continue;
                        Bump(kinds, "property");
                        if (mod.target == rootSource && mod.propertyPath.StartsWith("m_LocalScale")) rootScaled = true;
                        string label = mod.target.GetType().Name + "." + mod.propertyPath;
                        if (properties.Count < MaxPropertiesListed && !properties.Contains(label)) properties.Add(label);
                    }
                }

                List<AddedComponent> addedComponents = PrefabUtility.GetAddedComponents(go);
                List<RemovedComponent> removedComponents = PrefabUtility.GetRemovedComponents(go);
                List<AddedGameObject> addedObjects = PrefabUtility.GetAddedGameObjects(go);
                List<RemovedGameObject> removedObjects = PrefabUtility.GetRemovedGameObjects(go);
                if (addedComponents.Count > 0) kinds["added-component"] = addedComponents.Count;
                if (removedComponents.Count > 0) kinds["removed-component"] = removedComponents.Count;
                if (addedObjects.Count > 0) kinds["added-object"] = addedObjects.Count;
                if (removedObjects.Count > 0) kinds["removed-object"] = removedObjects.Count;

                if (kinds.Count == 0) continue;
                if (rootScaled) scaled++;
                foreach (KeyValuePair<string, int> kv in kinds)
                {
                    totals.TryGetValue(kv.Key, out int n);
                    totals[kv.Key] = n + kv.Value;
                }

                if (withOverrides++ > 0) rows.Append(',');
                rows.Append("{\"path\":").Append(Quote(PathOf(t)));
                rows.Append(",\"asset\":").Append(Quote(PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(go) ?? ""));
                rows.Append(",\"assetType\":").Append(Quote(PrefabUtility.GetPrefabAssetType(go).ToString()));
                rows.Append(",\"rootScaled\":").Append(rootScaled ? "true" : "false");
                rows.Append(",\"kinds\":").Append(Counts(kinds));
                rows.Append(",\"properties\":[");
                for (int i = 0; i < properties.Count; i++)
                {
                    if (i > 0) rows.Append(',');
                    rows.Append(Quote(properties[i]));
                }
                rows.Append("],\"added\":[");
                int listed = 0;
                foreach (AddedComponent c in addedComponents)
                    if (c.instanceComponent != null)
                        rows.Append(listed++ > 0 ? "," : "").Append(Quote(c.instanceComponent.GetType().Name));
                foreach (AddedGameObject o in addedObjects)
                    if (o.instanceGameObject != null)
                        rows.Append(listed++ > 0 ? "," : "").Append(Quote(o.instanceGameObject.name + "/"));
                rows.Append("],\"removed\":[");
                listed = 0;
                foreach (RemovedComponent c in removedComponents)
                    if (c.assetComponent != null)
                        rows.Append(listed++ > 0 ? "," : "").Append(Quote(c.assetComponent.GetType().Name));
                foreach (RemovedGameObject o in removedObjects)
                    if (o.assetGameObject != null)
                        rows.Append(listed++ > 0 ? "," : "").Append(Quote(o.assetGameObject.name + "/"));
                rows.Append("]}");
            }
        }

        var sb = new StringBuilder(256 + rows.Length);
        sb.Append("{\"scene\":").Append(Quote(scene.path));
        sb.Append(",\"instances\":").Append(instances);
        sb.Append(",\"withOverrides\":").Append(withOverrides);
        sb.Append(",\"scaled\":").Append(scaled);
        sb.Append(",\"ok\":").Append(withOverrides == 0 ? "true" : "false");
        sb.Append(",\"totals\":").Append(Counts(totals));
        sb.Append(",\"overridden\":[").Append(rows).Append("]}");
        return sb.ToString();
    }

    static void Bump(SortedDictionary<string, int> counts, string key)
    {
        counts.TryGetValue(key, out int n);
        counts[key] = n + 1;
    }

    static string Counts(SortedDictionary<string, int> counts)
    {
        var sb = new StringBuilder("{");
        bool first = true;
        foreach (KeyValuePair<string, int> kv in counts)
        {
            if (!first) sb.Append(',');
            first = false;
            sb.Append(Quote(kv.Key)).Append(':').Append(kv.Value);
        }
        return sb.Append('}').ToString();
    }

    static string PathOf(Transform t)
    {
        var sb = new StringBuilder(t.name);
        for (t = t.parent; t != null; t = t.parent) sb.Insert(0, t.name + "/");
        return sb.ToString();
    }

    static string Quote(string s)
    {
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
