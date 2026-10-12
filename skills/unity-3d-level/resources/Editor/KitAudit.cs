// KitAudit.cs — a read-only audit of the modular-kit prefabs in one folder, printed as one JSON
// object. It changes nothing: no prefab, no import setting, no scene.
//
// Drop into an Editor folder. No package needed.
//
//   Tools/Unity Dev/3D Level/Audit Kit Folder     select the kit folder in the Project window
//                                                 first; logs "[KIT-AUDIT] {json}"
//   KitAudit.Audit("Assets/Kit")                  returns the same JSON, for an eval or a test
//   KitAudit.Audit("Assets/Kit", 4f, 0.2f, 1f)    grid, wall thickness, height step
//
// The kit rule it enforces is the one in reference/modular-kit.md, measured on the prefab's
// render meshes in the root's own space:
//
//   off-grid-size         X or Z size is neither a multiple of the grid nor the wall thickness
//   off-grid-height       Y size is not a multiple of the height step (floor slabs are exempt)
//   pivot-off-corner      the pivot is not at the floor corner: bounds.min is not (0, 0, 0), allowing
//                         -thickness/2 on an axis the piece is centred across, and max.y = 0 for a slab
//   root-scaled           the prefab root's scale is not (1, 1, 1)
//   non-uniform-scale     a transform inside the prefab has a non-uniform scale
//   missing-collider      render meshes and no Collider anywhere in the prefab
//   dense-mesh-collider   a MeshCollider whose mesh has more than DenseTriangles triangles
//
// Each finding is a candidate, not a verdict: a prop that is not a kit piece fails the grid on
// purpose. Keep kit pieces and props in separate folders and audit the kit one.
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEditor;
using UnityEngine;

public static class KitAudit
{
    const string MenuPath = "Tools/Unity Dev/3D Level/Audit Kit Folder";

    /// <summary>A collision mesh above this is doing a proxy's job badly.</summary>
    public const int DenseTriangles = 500;
    const float Tolerance = 0.01f;

    [MenuItem(MenuPath)]
    static void Menu()
    {
        string folder = AssetDatabase.GetAssetPath(Selection.activeObject);
        if (string.IsNullOrEmpty(folder) || !AssetDatabase.IsValidFolder(folder)) folder = "Assets";
        Debug.Log("[KIT-AUDIT] " + Audit(folder));
    }

    public static string Audit(string folder, float grid = 2f, float wallThickness = 0.2f, float heightStep = 1f)
    {
        var sb = new StringBuilder(1024);
        var counts = new SortedDictionary<string, int>();
        int audited = 0, skipped = 0, flagged = 0;

        var rows = new StringBuilder(1024);
        foreach (string guid in AssetDatabase.FindAssets("t:Prefab", new[] { folder }))
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            var root = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            if (root == null) { skipped++; continue; }
            if (!LocalBounds(root, out Bounds b, out int triangles)) { skipped++; continue; }   // no render mesh: not a kit piece

            var checks = new List<string>();
            var details = new List<string>();
            Vector3 size = b.size, min = b.min;
            bool slab = Mathf.Abs(b.max.y) < Tolerance && min.y < -Tolerance;                  // a floor: top face on the pivot plane

            if (!OnGrid(size.x, grid, wallThickness) || !OnGrid(size.z, grid, wallThickness))
                Flag(checks, details, "off-grid-size", "footprint " + F(size.x) + " x " + F(size.z) + " against a grid of " + F(grid));
            if (!slab && !Multiple(size.y, heightStep))
                Flag(checks, details, "off-grid-height", "height " + F(size.y) + " against a step of " + F(heightStep));

            // Where the floor corner sits relative to the pivot. Zero when the piece obeys the rule.
            var offset = new Vector3(CornerOffset(min.x, size.x, wallThickness), slab ? b.max.y : min.y,
                                     CornerOffset(min.z, size.z, wallThickness));
            if (Mathf.Abs(offset.x) > Tolerance || Mathf.Abs(offset.y) > Tolerance || Mathf.Abs(offset.z) > Tolerance)
                Flag(checks, details, "pivot-off-corner", "floor corner is " + V(offset) + " from the pivot");

            if ((root.transform.localScale - Vector3.one).sqrMagnitude > 1e-6f)
                Flag(checks, details, "root-scaled", "root scale " + V(root.transform.localScale));
            foreach (Transform t in root.GetComponentsInChildren<Transform>(true))
            {
                Vector3 s = t.localScale;
                if (Mathf.Abs(s.x - s.y) > 1e-3f || Mathf.Abs(s.y - s.z) > 1e-3f)
                {
                    Flag(checks, details, "non-uniform-scale", "'" + t.name + "' scale " + V(s));
                    break;
                }
            }

            Collider[] colliders = root.GetComponentsInChildren<Collider>(true);
            if (colliders.Length == 0)
                Flag(checks, details, "missing-collider", "no Collider in the prefab: the runner walks through it");
            foreach (Collider c in colliders)
            {
                if (!(c is MeshCollider mc) || mc.sharedMesh == null) continue;
                int tris = Triangles(mc.sharedMesh);
                if (tris > DenseTriangles)
                {
                    Flag(checks, details, "dense-mesh-collider", "MeshCollider on '" + c.name + "' has " + tris + " triangles" +
                         (mc.convex ? " (convex: the hull is rebuilt from them)" : ""));
                    break;
                }
            }

            foreach (string check in checks)
            {
                counts.TryGetValue(check, out int n);
                counts[check] = n + 1;
            }
            if (checks.Count > 0) flagged++;

            if (audited++ > 0) rows.Append(',');
            rows.Append("{\"prefab\":").Append(Quote(path));
            rows.Append(",\"size\":").Append(V(size));
            rows.Append(",\"pivotOffset\":").Append(V(offset));
            rows.Append(",\"triangles\":").Append(triangles);
            rows.Append(",\"colliders\":").Append(colliders.Length);
            rows.Append(",\"checks\":[");
            for (int i = 0; i < checks.Count; i++)
            {
                if (i > 0) rows.Append(',');
                rows.Append("{\"check\":").Append(Quote(checks[i])).Append(",\"detail\":").Append(Quote(details[i])).Append('}');
            }
            rows.Append("]}");
        }

        sb.Append("{\"folder\":").Append(Quote(folder));
        sb.Append(",\"grid\":").Append(F(grid));
        sb.Append(",\"wallThickness\":").Append(F(wallThickness));
        sb.Append(",\"heightStep\":").Append(F(heightStep));
        sb.Append(",\"prefabs\":").Append(audited);
        sb.Append(",\"skipped\":").Append(skipped);
        sb.Append(",\"flagged\":").Append(flagged);
        sb.Append(",\"ok\":").Append(flagged == 0 ? "true" : "false");
        sb.Append(",\"counts\":{");
        bool first = true;
        foreach (KeyValuePair<string, int> kv in counts)
        {
            if (!first) sb.Append(',');
            first = false;
            sb.Append(Quote(kv.Key)).Append(':').Append(kv.Value);
        }
        sb.Append("},\"pieces\":[").Append(rows).Append("]}");
        return sb.ToString();
    }

    // ------------------------------------------------------------------ measuring

    /// <summary>Bounds of every render mesh in the root's own space, from the mesh bounds and the
    /// transforms alone: Renderer.bounds is a world box and a prefab asset is not in the world.</summary>
    public static bool LocalBounds(GameObject root, out Bounds bounds, out int triangles)
    {
        bounds = new Bounds();
        triangles = 0;
        bool any = false;
        Matrix4x4 toRoot = root.transform.worldToLocalMatrix;
        foreach (MeshFilter filter in root.GetComponentsInChildren<MeshFilter>(true))
        {
            Mesh mesh = filter.sharedMesh;
            if (mesh == null || filter.GetComponent<MeshRenderer>() == null) continue;
            triangles += Triangles(mesh);
            Matrix4x4 m = toRoot * filter.transform.localToWorldMatrix;
            Vector3 c = mesh.bounds.center, e = mesh.bounds.extents;
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

    // Works on a mesh that is not readable: the index count is metadata.
    static int Triangles(Mesh mesh)
    {
        long indices = 0;
        for (int i = 0; i < mesh.subMeshCount; i++) indices += mesh.GetIndexCount(i);
        return (int)(indices / 3);
    }

    static bool Multiple(float value, float step)
    {
        if (step <= 0f) return true;
        float n = Mathf.Round(value / step);
        return n >= 1f && Mathf.Abs(value - n * step) <= Tolerance;
    }

    static bool OnGrid(float value, float grid, float thickness) =>
        Multiple(value, grid) || Mathf.Abs(value - thickness) <= Tolerance;

    // A piece as thin as a wall is centred across the grid line; anything else starts on it.
    static float CornerOffset(float min, float size, float thickness) =>
        Mathf.Abs(size - thickness) <= Tolerance ? min + thickness * 0.5f : min;

    static void Flag(List<string> checks, List<string> details, string check, string detail)
    {
        checks.Add(check);
        details.Add(detail);
    }

    static string F(float v) => v.ToString("0.###", CultureInfo.InvariantCulture);
    static string V(Vector3 v) => "[" + F(v.x) + "," + F(v.y) + "," + F(v.z) + "]";

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
