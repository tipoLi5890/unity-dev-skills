// CollisionProxyBuilder.cs — adds a collision proxy to each selected object: a child named
// "Collision" on the World layer carrying a box or a capsule sized from the render meshes, or
// one convex hull per mesh. The render meshes and any collider already present are left alone.
//
// Drop into an Editor folder. No package needed (built-in 3D physics module).
//
//   Tools/Unity Dev/3D Level/Add Box Proxy          a BoxCollider around all render meshes
//   Tools/Unity Dev/3D Level/Add Capsule Proxy      a CapsuleCollider along the longest axis
//   Tools/Unity Dev/3D Level/Add Convex Proxies     a convex MeshCollider per render mesh
//
// Every command reports what it would create and waits for confirmation. From an eval or a
// test fixture, call Plan(targets, shape) first, show the text, then Build(target, shape) —
// Build does not ask.
//
// Run it on the prefab, not on an instance: open the prefab and select its root. On an instance
// in a scene the proxy is an added-object override that no other instance receives; the plan
// says so. Build refuses when the layer is missing rather than leaving the proxy on Default.
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public enum ProxyShape { Box, Capsule, Convex }

public static class CollisionProxyBuilder
{
    const string MenuRoot = "Tools/Unity Dev/3D Level/";
    public const string ChildName = "Collision";
    public const string LayerName = "World";

    /// <summary>PhysX builds a convex hull of at most this many faces; a denser mesh is reduced
    /// to fit, which rounds concave detail away.</summary>
    public const int HullFaceLimit = 255;

    // ------------------------------------------------------------------ menu

    [MenuItem(MenuRoot + "Add Box Proxy")]
    static void MenuBox() => Run(ProxyShape.Box);

    [MenuItem(MenuRoot + "Add Capsule Proxy")]
    static void MenuCapsule() => Run(ProxyShape.Capsule);

    [MenuItem(MenuRoot + "Add Convex Proxies")]
    static void MenuConvex() => Run(ProxyShape.Convex);

    static void Run(ProxyShape shape)
    {
        GameObject[] targets = Selection.gameObjects;
        string plan = Plan(targets, shape);
        Debug.Log("[COLLISION-PROXY] plan\n" + plan);
        if (targets.Length == 0 || LayerMask.NameToLayer(LayerName) < 0)
        {
            EditorUtility.DisplayDialog("Collision proxy", plan, "OK");
            return;
        }
        if (!EditorUtility.DisplayDialog("Add " + shape + " collision proxy?", plan, "Create", "Cancel")) return;
        foreach (GameObject target in targets) Build(target, shape);
    }

    // ------------------------------------------------------------------ plan

    public static string Plan(GameObject[] targets, ProxyShape shape)
    {
        var sb = new StringBuilder();
        if (targets == null || targets.Length == 0)
        {
            sb.AppendLine("Nothing selected. Open the prefab and select its root.");
            return sb.ToString();
        }
        if (LayerMask.NameToLayer(LayerName) < 0)
        {
            sb.AppendLine("No layer named '" + LayerName + "'. Add it in Tags and Layers, then run this again; nothing is created without it.");
            return sb.ToString();
        }

        foreach (GameObject target in targets)
        {
            sb.AppendLine("'" + target.name + "':");
            if (!KitBounds(target, out Bounds b))
            {
                sb.AppendLine("  no render mesh under it: skipped.");
                continue;
            }
            bool exists = target.transform.Find(ChildName) != null;
            sb.AppendLine("  " + (exists ? "add to the existing child '" : "create child '") + ChildName + "' on layer '" + LayerName + "' with:");
            switch (shape)
            {
                case ProxyShape.Box:
                    sb.AppendLine("    BoxCollider      centre " + V(b.center) + ", size " + V(b.size));
                    break;
                case ProxyShape.Capsule:
                    Capsule(b, out int axis, out float height, out float radius);
                    sb.AppendLine("    CapsuleCollider  along " + "XYZ"[axis] + ", height " + F(height) + ", radius " + F(radius) + ", centre " + V(b.center));
                    break;
                default:
                    foreach (MeshFilter filter in Meshes(target))
                    {
                        int triangles = Triangles(filter.sharedMesh);
                        sb.AppendLine("    MeshCollider     convex hull of '" + filter.sharedMesh.name + "' (" + triangles + " triangles" +
                                      (triangles > HullFaceLimit ? ", reduced to the " + HullFaceLimit + "-face limit" : "") + ")");
                    }
                    break;
            }

            foreach (Collider c in target.GetComponentsInChildren<Collider>(true))
            {
                if (c.transform.name == ChildName || (c.transform.parent != null && c.transform.parent.name == ChildName)) continue;
                sb.AppendLine("  existing " + c.GetType().Name + " on '" + c.name + "' is left in place — remove it once the proxy is checked.");
            }
            if (PrefabUtility.IsPartOfPrefabInstance(target) && PrefabStageUtility.GetPrefabStage(target) == null)
                sb.AppendLine("  this is a prefab instance in a scene: the proxy becomes an added-object override. Open the prefab and run it there instead.");
        }
        return sb.ToString();
    }

    // ------------------------------------------------------------------ build

    /// <summary>The Collision child, or null when nothing was built.</summary>
    public static GameObject Build(GameObject target, ProxyShape shape)
    {
        int layer = LayerMask.NameToLayer(LayerName);
        if (layer < 0)
        {
            Debug.LogError("[COLLISION-PROXY] no layer named '" + LayerName + "': nothing created");
            return null;
        }
        if (target == null || !KitBounds(target, out Bounds b)) return null;

        Transform existing = target.transform.Find(ChildName);
        GameObject child;
        if (existing != null) child = existing.gameObject;
        else
        {
            child = new GameObject(ChildName);
            Undo.RegisterCreatedObjectUndo(child, "Add Collision Proxy");
            child.transform.SetParent(target.transform, false);      // identity: the root's own space
        }
        child.layer = layer;

        switch (shape)
        {
            case ProxyShape.Box:
                var box = Undo.AddComponent<BoxCollider>(child);
                box.center = b.center;
                box.size = b.size;
                break;
            case ProxyShape.Capsule:
                Capsule(b, out int axis, out float height, out float radius);
                var capsule = Undo.AddComponent<CapsuleCollider>(child);
                capsule.direction = axis;
                capsule.center = b.center;
                capsule.height = height;
                capsule.radius = radius;
                break;
            default:
                foreach (MeshFilter filter in Meshes(target))
                {
                    var hull = new GameObject("Hull_" + filter.sharedMesh.name) { layer = layer };
                    Undo.RegisterCreatedObjectUndo(hull, "Add Collision Proxy");
                    // Take the mesh's own pose first, then move under Collision keeping it.
                    hull.transform.SetParent(filter.transform, false);
                    hull.transform.SetParent(child.transform, true);
                    var mesh = Undo.AddComponent<MeshCollider>(hull);
                    mesh.sharedMesh = filter.sharedMesh;
                    mesh.convex = true;
                }
                break;
        }

        EditorUtility.SetDirty(target);
        EditorSceneManager.MarkSceneDirty(target.scene);
        Debug.Log("[COLLISION-PROXY] " + target.name + " shape=" + shape + " layer=" + LayerName +
                  " colliders=" + child.GetComponentsInChildren<Collider>(true).Length);
        return child;
    }

    // ------------------------------------------------------------------ parts

    // Render meshes only. A proxy carries no MeshRenderer, so it is never measured as one.
    static List<MeshFilter> Meshes(GameObject target)
    {
        var found = new List<MeshFilter>();
        foreach (MeshFilter filter in target.GetComponentsInChildren<MeshFilter>(true))
        {
            if (filter.sharedMesh == null || filter.GetComponent<MeshRenderer>() == null) continue;
            found.Add(filter);
        }
        return found;
    }

    /// <summary>Bounds of the render meshes in the target's own space.</summary>
    public static bool KitBounds(GameObject target, out Bounds bounds)
    {
        bounds = new Bounds();
        bool any = false;
        Matrix4x4 toRoot = target.transform.worldToLocalMatrix;
        foreach (MeshFilter filter in Meshes(target))
        {
            Matrix4x4 m = toRoot * filter.transform.localToWorldMatrix;
            Vector3 c = filter.sharedMesh.bounds.center, e = filter.sharedMesh.bounds.extents;
            for (int i = 0; i < 8; i++)
            {
                var corner = new Vector3(c.x + ((i & 1) == 0 ? -e.x : e.x), c.y + ((i & 2) == 0 ? -e.y : e.y),
                                         c.z + ((i & 4) == 0 ? -e.z : e.z));
                Vector3 p = m.MultiplyPoint3x4(corner);
                if (!any) { bounds = new Bounds(p, Vector3.zero); any = true; }
                else bounds.Encapsulate(p);
            }
        }
        return any;
    }

    // The capsule stands along the longest axis and is as wide as the wider of the other two.
    static void Capsule(Bounds b, out int axis, out float height, out float radius)
    {
        Vector3 s = b.size;
        axis = s.x >= s.y && s.x >= s.z ? 0 : (s.y >= s.z ? 1 : 2);
        height = s[axis];
        float across = Mathf.Max(s[(axis + 1) % 3], s[(axis + 2) % 3]);
        radius = Mathf.Min(across, height) * 0.5f;
    }

    static int Triangles(Mesh mesh)
    {
        long indices = 0;
        for (int i = 0; i < mesh.subMeshCount; i++) indices += mesh.GetIndexCount(i);
        return (int)(indices / 3);
    }

    static string F(float v) => v.ToString("0.###", CultureInfo.InvariantCulture);
    static string V(Vector3 v) => "(" + F(v.x) + ", " + F(v.y) + ", " + F(v.z) + ")";
}
