// GreyboxBuilderProBuilder.cs — the same gate-room greybox as GreyboxBuilder.cs, built from
// ProBuilder meshes instead of primitives, so every block can be pushed, pulled and cut in the
// Scene view afterwards. The ramp is a real wedge, not a tilted slab.
//
// Drop into an Editor folder beside GreyboxBuilder.cs (an Editor asmdef that references
// Unity.ProBuilder and Unity.ProBuilder.Editor). Leave this file out of a project without the
// package: GreyboxBuilder.cs compiles and builds on its own.
//
// REQUIRES com.unity.probuilder (written against 6.0.9), and GreyboxBuilder.cs for the metrics,
// the layout, the colours and the plan.
//
//   Tools/Unity Dev/3D Level/Build Gate-Room Greybox (ProBuilder)      reports the blocks, then asks
//
// Call Plan(metrics), show it, then Build(metrics) from an eval or a fixture; Build does not ask.
//
// Solid blocks carry a MeshCollider, not a BoxCollider: ProBuilder keeps a MeshCollider's mesh
// in step with the edited shape on every Refresh(), and a BoxCollider would keep the size the
// block had before it was edited.
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.ProBuilder;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.ProBuilder;

public static class GreyboxBuilderProBuilder
{
    const string MenuPath = "Tools/Unity Dev/3D Level/Build Gate-Room Greybox (ProBuilder)";

    [MenuItem(MenuPath)]
    static void Menu()
    {
        GreyboxMetrics m = GreyboxMetrics.GateRoom;
        string plan = Plan(m);
        Debug.Log("[GREYBOX] plan\n" + plan);
        if (!UnityEditor.EditorUtility.DisplayDialog("Build the gate-room greybox with ProBuilder?", plan, "Create", "Cancel")) return;
        Selection.activeGameObject = Build(m);
    }

    public static string Plan(GreyboxMetrics m) =>
        GreyboxBuilder.Plan(m) +
        "Blocks are ProBuilder meshes with MeshColliders; the ramp is a wedge. The ruler stays a primitive capsule.\n";

    public static GameObject Build(GreyboxMetrics m)
    {
        int layer = Mathf.Max(0, LayerMask.NameToLayer(GreyboxBuilder.LayerName));
        var root = new GameObject(GreyboxBuilder.RootName);
        Undo.RegisterCreatedObjectUndo(root, "Build Gate-Room Greybox");

        var materials = new Dictionary<GreyboxFunction, Material>();
        foreach (GreyboxBlock block in GreyboxBuilder.Layout(m))
        {
            GameObject go;
            if (block.shape == GreyboxShape.Capsule)
            {
                go = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                Object.DestroyImmediate(go.GetComponent<Collider>());
                go.transform.SetParent(root.transform, false);
                GreyboxBuilder.Place(go.transform, block);
            }
            else
            {
                // Sizes are baked into the vertices, so every block keeps a scale of (1, 1, 1).
                ProBuilderMesh mesh = block.shape == GreyboxShape.Ramp
                    ? Wedge(block.size)
                    : ShapeGenerator.GenerateCube(PivotLocation.Center, block.size);
                go = mesh.gameObject;
                go.transform.SetParent(root.transform, false);
                go.transform.localPosition = block.centre;

                // A generated mesh has no material of its own; MaterialFor below replaces this one.
                mesh.GetComponent<MeshRenderer>().sharedMaterial = BuiltinMaterials.defaultMaterial;
                if (block.solid)
                {
                    go.AddComponent<MeshCollider>();
                    go.layer = layer;
                }
                mesh.ToMesh();
                mesh.Refresh();                      // also hands the mesh to the MeshCollider
                mesh.Optimize();
            }
            go.name = block.name;
            var renderer = go.GetComponent<Renderer>();
            renderer.sharedMaterial = GreyboxBuilder.MaterialFor(block.function, materials, renderer);
        }

        EditorSceneManager.MarkSceneDirty(root.scene);
        Debug.Log("[GREYBOX] created " + GreyboxBuilder.RootName + " (ProBuilder) blocks=" + root.transform.childCount +
                  " layer=" + LayerMask.LayerToName(layer) + " warnings=" + GreyboxBuilder.Check(m).Count);
        return root;
    }

    /// <summary>A wedge filling the box of the given size: low edge at -Z, high edge at +Z,
    /// pivot at the centre of the box. Each face owns its vertices, so the edges stay hard.</summary>
    public static ProBuilderMesh Wedge(Vector3 size)
    {
        float hx = size.x * 0.5f, hy = size.y * 0.5f, hz = size.z * 0.5f;
        Vector3 a0 = new Vector3(-hx, -hy, -hz), a1 = new Vector3(hx, -hy, -hz);   // low edge
        Vector3 b0 = new Vector3(-hx, -hy, hz), b1 = new Vector3(hx, -hy, hz);     // under the high edge
        Vector3 c0 = new Vector3(-hx, hy, hz), c1 = new Vector3(hx, hy, hz);       // high edge

        var positions = new[]
        {
            a0, c0, c1, a1,        // slope
            a0, a1, b1, b0,        // underside
            b0, b1, c1, c0,        // back
            a0, b0, c0,            // left
            a1, c1, b1,            // right
        };
        var faces = new[]
        {
            new Face(new[] { 0, 1, 2, 0, 2, 3 }),
            new Face(new[] { 4, 5, 6, 4, 6, 7 }),
            new Face(new[] { 8, 9, 10, 8, 10, 11 }),
            new Face(new[] { 12, 13, 14 }),
            new Face(new[] { 15, 16, 17 }),
        };
        ProBuilderMesh mesh = ProBuilderMesh.Create(positions, faces);
        mesh.gameObject.name = "Wedge";
        return mesh;
    }
}
