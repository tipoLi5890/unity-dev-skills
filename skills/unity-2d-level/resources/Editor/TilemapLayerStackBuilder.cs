// TilemapLayerStackBuilder.cs — builds the Grid and its layer Tilemaps with renderers,
// colliders and sorting set per reference/layer-stack.md, and exports a painted stack as
// the level JSON that scripts/level_validate.py reads.
//
// Drop into an Editor folder beside an assembly that holds LevelData.cs and
// TilemapLevelLoader.cs. REQUIRES the built-in Tilemap and 2D physics modules
// (com.unity.modules.tilemap, com.unity.modules.physics2d).
//
//   Tools/Unity Dev/2D Level/Build Layer Stack (Side View)    Ground and Walls solid, OneWay with an effector
//   Tools/Unity Dev/2D Level/Build Layer Stack (Top-Down)     Walls solid, Ground is floor, no OneWay layer
//   Tools/Unity Dev/2D Level/Export Level JSON                select the Grid that carries a TilemapLevelLoader
//
// Every command reports what it would create and waits for confirmation. From an eval or a
// test fixture, call Plan(…) first, show the text, then call Build(…) — Build does not ask.
//
// Select an existing Grid to complete it: layers that exist are kept untouched, missing ones
// are added. Sorting layers and physics layers are never created here — both live in
// ProjectSettings/TagManager.asset, which is the project's to edit; a missing one is named
// in the plan and the layer falls back to Default.
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Tilemaps;

public static class TilemapLayerStackBuilder
{
    const string MenuRoot = "Tools/Unity Dev/2D Level/";

    public sealed class Options
    {
        public bool topDown;
        public string gridName = "Level";
        public Vector3 cellSize = new Vector3(1f, 1f, 0f);
        // Sorting layers, back to front. Shadows and Actors sit between Floor and Overhead.
        public string backSortingLayer = "Background";
        public string floorSortingLayer = "Floor";
        public string actorSortingLayer = "Actors";
        public string frontSortingLayer = "Overhead";
        // Physics layers. Empty solidPhysicsLayer means Rooftop for a side view, Obstacles from above.
        public string solidPhysicsLayer = "";
        public string oneWayPhysicsLayer = "Platform";

        public string SolidLayer => !string.IsNullOrEmpty(solidPhysicsLayer) ? solidPhysicsLayer : topDown ? "Obstacles" : "Rooftop";
    }

    struct Spec
    {
        public string name, sortingLayer, physicsLayer;
        public int order;
        public bool solid, oneWay, individual;
    }

    static List<Spec> Specs(Options o)
    {
        var specs = new List<Spec>
        {
            new Spec { name = LevelLayers.Background, sortingLayer = o.backSortingLayer, order = 0 },
            new Spec { name = LevelLayers.Ground, sortingLayer = o.floorSortingLayer, order = 0, solid = !o.topDown, physicsLayer = o.SolidLayer },
        };
        // From above, walls are tall: they sort against the runner tile by tile, on the actors' layer.
        if (o.topDown)
            specs.Add(new Spec { name = LevelLayers.Walls, sortingLayer = o.actorSortingLayer, order = 0, solid = true, individual = true, physicsLayer = o.SolidLayer });
        else
        {
            specs.Add(new Spec { name = LevelLayers.Walls, sortingLayer = o.floorSortingLayer, order = 10, solid = true, physicsLayer = o.SolidLayer });
            specs.Add(new Spec { name = LevelLayers.OneWay, sortingLayer = o.floorSortingLayer, order = 20, oneWay = true, physicsLayer = o.oneWayPhysicsLayer });
        }
        specs.Add(new Spec { name = LevelLayers.Front, sortingLayer = o.frontSortingLayer, order = 0 });
        specs.Add(new Spec { name = LevelLayers.Markers, sortingLayer = o.frontSortingLayer, order = 100 });
        return specs;
    }

    // ------------------------------------------------------------------ menu

    [MenuItem(MenuRoot + "Build Layer Stack (Side View)")]
    static void MenuSide() => Run(new Options { topDown = false });

    [MenuItem(MenuRoot + "Build Layer Stack (Top-Down)")]
    static void MenuTopDown() => Run(new Options { topDown = true });

    static void Run(Options options)
    {
        Grid existing = Selection.activeGameObject != null ? Selection.activeGameObject.GetComponent<Grid>() : null;
        string plan = Plan(existing, options);
        Debug.Log("[LEVEL-STACK] plan\n" + plan);
        if (!EditorUtility.DisplayDialog("Build layer stack?", plan, "Create", "Cancel")) return;
        Selection.activeGameObject = Build(existing, options).gameObject;
    }

    [MenuItem(MenuRoot + "Export Level JSON")]
    static void MenuExport()
    {
        GameObject go = Selection.activeGameObject;
        TilemapLevelLoader loader = go != null ? go.GetComponent<TilemapLevelLoader>() : null;
        if (loader == null)
        {
            EditorUtility.DisplayDialog("Export level JSON", "Select the Grid that carries a TilemapLevelLoader.", "OK");
            return;
        }
        string view = loader.transform.Find(LevelLayers.OneWay) != null ? "side" : "topdown";
        LevelData level;
        try { level = loader.Capture(go.name, view); }
        catch (System.InvalidOperationException e)
        {
            EditorUtility.DisplayDialog("Export level JSON", e.Message, "OK");
            return;
        }
        string path = EditorUtility.SaveFilePanelInProject("Export level JSON", level.id, "json", "Where the level file goes.");
        if (string.IsNullOrEmpty(path)) { Object.DestroyImmediate(level); return; }

        var sb = new StringBuilder();
        sb.AppendLine((File.Exists(path) ? "Overwrite " : "Create ") + path);
        sb.AppendLine("Level '" + level.id + "', view " + view + " (a OneWay layer means side), " + level.width + " x " + level.height + " cells.");
        foreach (LevelLayer layer in level.layers) sb.AppendLine("  layer " + layer.name);
        sb.AppendLine("  " + level.tiles.Count + " tile ids, " + level.pickups.Count + " pickups, " + level.entities.Count + " entities");
        sb.AppendLine("  spawn (" + level.spawn.x + ", " + level.spawn.y + "), gate (" + level.gate.x + ", " + level.gate.y + ")");
        foreach (string problem in level.Problems()) sb.AppendLine("  PROBLEM " + problem);
        Debug.Log("[LEVEL-STACK] export plan\n" + sb);
        if (EditorUtility.DisplayDialog("Export level JSON?", sb.ToString(), "Write", "Cancel"))
        {
            File.WriteAllText(path, level.ToJson(true));
            AssetDatabase.ImportAsset(path);
        }
        Object.DestroyImmediate(level);
    }

    // ------------------------------------------------------------------ plan

    public static string Plan(Grid existing, Options o)
    {
        var sb = new StringBuilder();
        sb.AppendLine("Scene: " + EditorSceneManager.GetActiveScene().name + (o.topDown ? "  (top-down stack)" : "  (side-view stack)"));
        sb.AppendLine(existing != null
            ? "Keep Grid '" + existing.name + "' and add the layers it lacks."
            : "Create Grid '" + o.gridName + "', rectangular, cell size " + o.cellSize.x + " x " + o.cellSize.y + ".");
        foreach (Spec s in Specs(o))
        {
            if (existing != null && existing.transform.Find(s.name) != null)
            {
                sb.AppendLine("  keep    " + s.name + "  (exists; not modified)");
                continue;
            }
            string collider = s.oneWay ? "TilemapCollider2D > CompositeCollider2D (polygons) > PlatformEffector2D (one-way, arc 170)"
                            : s.solid ? "TilemapCollider2D > CompositeCollider2D (outlines) on a static body"
                            : "no collider";
            sb.AppendLine("  create  " + s.name + "  sorting " + SortingName(s.sortingLayer) + " / " + s.order +
                          (s.individual ? " (individual)" : "") + "  " + collider +
                          (s.solid || s.oneWay ? "  physics layer " + PhysicsName(s.physicsLayer) : ""));
        }
        foreach (string missing in Missing(o)) sb.AppendLine("MISSING " + missing);
        return sb.ToString();
    }

    static IEnumerable<string> Missing(Options o)
    {
        var sorting = new List<string> { o.backSortingLayer, o.floorSortingLayer, o.frontSortingLayer };
        if (o.topDown) sorting.Add(o.actorSortingLayer);
        foreach (string layer in sorting)
            if (!HasSortingLayer(layer))
                yield return "sorting layer '" + layer + "': its Tilemaps go on Default — add it in Tags and Layers, then set the renderers.";
        var physics = new List<string> { o.SolidLayer };
        if (!o.topDown) physics.Add(o.oneWayPhysicsLayer);
        foreach (string layer in physics)
            if (LayerMask.NameToLayer(layer) < 0)
                yield return "physics layer '" + layer + "': its Tilemaps stay on Default — add it, then set the objects' layer and the runner's ground mask.";
    }

    // SortingLayer.NameToID returns 0 for Default and for a name that does not exist, so
    // existence is read off the list.
    static bool HasSortingLayer(string layerName)
    {
        foreach (SortingLayer layer in SortingLayer.layers)
            if (layer.name == layerName) return true;
        return false;
    }

    static string SortingName(string wanted) => HasSortingLayer(wanted) ? wanted : "Default";
    static string PhysicsName(string wanted) => LayerMask.NameToLayer(wanted) >= 0 ? wanted : "Default";

    // ------------------------------------------------------------------ build

    public static Grid Build(Grid existing, Options o)
    {
        Grid grid = existing;
        if (grid == null)
        {
            var root = new GameObject(o.gridName);
            Undo.RegisterCreatedObjectUndo(root, "Build Layer Stack");
            grid = root.AddComponent<Grid>();
            grid.cellLayout = GridLayout.CellLayout.Rectangle;
            grid.cellSize = o.cellSize;
        }

        foreach (Spec s in Specs(o))
        {
            if (grid.transform.Find(s.name) != null) continue;

            var go = new GameObject(s.name);
            Undo.RegisterCreatedObjectUndo(go, "Build Layer Stack");
            go.transform.SetParent(grid.transform, false);
            go.AddComponent<Tilemap>();
            var renderer = go.AddComponent<TilemapRenderer>();
            renderer.sortingLayerName = SortingName(s.sortingLayer);
            renderer.sortingOrder = s.order;
            if (s.individual) renderer.mode = TilemapRenderer.Mode.Individual;

            if (!s.solid && !s.oneWay) continue;

            int physicsLayer = LayerMask.NameToLayer(s.physicsLayer);
            if (physicsLayer >= 0) go.layer = physicsLayer;

            // One static body per collidable layer; the composite needs it on the same object.
            var body = go.AddComponent<Rigidbody2D>();
            body.bodyType = RigidbodyType2D.Static;
            var tiles = go.AddComponent<TilemapCollider2D>();
            tiles.compositeOperation = Collider2D.CompositeOperation.Merge;   // no seams between cells
            var composite = go.AddComponent<CompositeCollider2D>();
            // Outlines for the static level: no internal edges to catch on. The one-way layer is
            // polygons, so the platform has an inside for overlap queries.
            composite.geometryType = s.oneWay ? CompositeCollider2D.GeometryType.Polygons : CompositeCollider2D.GeometryType.Outlines;
            composite.generationType = CompositeCollider2D.GenerationType.Synchronous;

            if (s.oneWay)
            {
                var effector = go.AddComponent<PlatformEffector2D>();
                effector.useOneWay = true;
                effector.useOneWayGrouping = true;      // the merged shape is treated as one platform
                effector.surfaceArc = 170f;             // narrower than 180 so the ends are not "top"
                composite.usedByEffector = true;        // the composite owns the shapes the effector acts on
            }
        }

        EditorSceneManager.MarkSceneDirty(grid.gameObject.scene);
        return grid;
    }
}
