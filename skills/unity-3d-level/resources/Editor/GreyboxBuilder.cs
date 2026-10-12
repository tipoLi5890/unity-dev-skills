// GreyboxBuilder.cs — builds the gate-room greybox in the open scene from one metrics struct:
// a corridor, a door, a room, a step, a ramp, two ledges across a jump gap, a gate, a switch
// pedestal and a 1.8-unit ruler capsule. Blocks are Unity primitives, coloured by function.
//
// Drop into an Editor folder. No package needed: this file uses primitives only, so it compiles
// in any project. The ProBuilder route is a separate file, GreyboxBuilderProBuilder.cs, which
// reads the same Layout() — keeping it out of this file is what lets this one compile without
// com.unity.probuilder.
//
//   Tools/Unity Dev/3D Level/Build Gate-Room Greybox      reports the blocks, then asks
//
// The command reports what it would create and waits for confirmation. From an eval or a test
// fixture, call Plan(metrics) first, show the text, then Build(metrics) — Build does not ask.
//
// Every number is a CLEAR dimension: the door is 1.2 between its jambs, the corridor 2.4 between
// its walls. Walls are added outside those numbers. The blocks' own BoxColliders are the level's
// collision until art replaces them — reference/greybox.md.
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

/// <summary>What a block is for. One colour each, so a screenshot reads without labels.</summary>
public enum GreyboxFunction { Floor, Wall, Climb, Jump, Gate, Interact, Hazard, Sentry, Marker }

public enum GreyboxShape { Box, Ramp, Capsule }

/// <summary>One block of the layout. For a Ramp, centre and size are its bounding box and it
/// climbs towards +Z; every other shape is axis-aligned.</summary>
public struct GreyboxBlock
{
    public string name;
    public GreyboxFunction function;
    public GreyboxShape shape;
    public Vector3 centre;
    public Vector3 size;
    public bool solid;                    // false: a marker, built without a collider
}

[System.Serializable]
public struct GreyboxMetrics
{
    // The body the level is built for.
    public float bodyHeight, bodyRadius, stepOffset, slopeLimit;
    // The level numbers. Each one is checked against the body in Plan().
    public float doorWidth, doorHeight, corridorWidth, corridorLength;
    public float stepHeight, rampAngle, rampWidth, ledgeHeight, jumpGap;
    public float roomWidth, roomDepth, wallHeight, wallThickness, floorThickness;

    /// <summary>The gate-room sheet in reference/greybox.md.</summary>
    public static GreyboxMetrics GateRoom => new GreyboxMetrics
    {
        bodyHeight = 1.8f, bodyRadius = 0.4f, stepOffset = 0.3f, slopeLimit = 45f,
        doorWidth = 1.2f, doorHeight = 2.2f, corridorWidth = 2.4f, corridorLength = 6f,
        stepHeight = 0.3f, rampAngle = 30f, rampWidth = 2f, ledgeHeight = 1f, jumpGap = 3f,
        roomWidth = 10f, roomDepth = 14f, wallHeight = 3f, wallThickness = 0.2f, floorThickness = 0.2f,
    };
}

public static class GreyboxBuilder
{
    public const string RootName = "Greybox_GateRoom";
    public const string LayerName = "World";
    const string MenuPath = "Tools/Unity Dev/3D Level/Build Gate-Room Greybox";

    // ------------------------------------------------------------------ menu

    [MenuItem(MenuPath)]
    static void Menu()
    {
        GreyboxMetrics m = GreyboxMetrics.GateRoom;
        string plan = Plan(m);
        Debug.Log("[GREYBOX] plan\n" + plan);
        if (!EditorUtility.DisplayDialog("Build the gate-room greybox?", plan, "Create", "Cancel")) return;
        Selection.activeGameObject = Build(m);
    }

    // ------------------------------------------------------------------ colours

    public static Color ColourOf(GreyboxFunction f)
    {
        switch (f)
        {
            case GreyboxFunction.Floor:    return new Color(0.55f, 0.55f, 0.55f);
            case GreyboxFunction.Wall:     return new Color(0.30f, 0.30f, 0.33f);
            case GreyboxFunction.Climb:    return new Color(0.25f, 0.50f, 0.85f);
            case GreyboxFunction.Jump:     return new Color(0.95f, 0.60f, 0.15f);
            case GreyboxFunction.Gate:     return new Color(0.95f, 0.85f, 0.20f);
            case GreyboxFunction.Interact: return new Color(0.25f, 0.75f, 0.35f);
            case GreyboxFunction.Hazard:   return new Color(0.85f, 0.20f, 0.20f);
            case GreyboxFunction.Sentry:   return new Color(0.65f, 0.30f, 0.80f);
            default:                       return Color.white;
        }
    }

    // ------------------------------------------------------------------ layout

    /// <summary>The blocks, in local space: the origin is the corridor entrance at floor level
    /// and the runner walks towards +Z.</summary>
    public static List<GreyboxBlock> Layout(GreyboxMetrics m)
    {
        var blocks = new List<GreyboxBlock>();
        float wt = m.wallThickness, wh = m.wallHeight, ft = m.floorThickness;
        float cw = m.corridorWidth, cl = m.corridorLength, rw = m.roomWidth, rd = m.roomDepth;

        // ---- corridor: clear width between the inner faces of its walls.
        Box(blocks, "Floor_Corridor", GreyboxFunction.Floor, new Vector3(0f, -ft * 0.5f, cl * 0.5f), new Vector3(cw + wt * 2f, ft, cl));
        Box(blocks, "Wall_Corridor_L", GreyboxFunction.Wall, new Vector3(-(cw + wt) * 0.5f, wh * 0.5f, cl * 0.5f), new Vector3(wt, wh, cl));
        Box(blocks, "Wall_Corridor_R", GreyboxFunction.Wall, new Vector3((cw + wt) * 0.5f, wh * 0.5f, cl * 0.5f), new Vector3(wt, wh, cl));

        // ---- the door wall, then the room behind it.
        Opening(blocks, "Door", m, cl + wt * 0.5f, false);
        float z0 = cl + wt;
        Box(blocks, "Floor_Room", GreyboxFunction.Floor, new Vector3(0f, -ft * 0.5f, cl + (rd + wt * 2f) * 0.5f), new Vector3(rw + wt * 2f, ft, rd + wt * 2f));
        Box(blocks, "Wall_Room_L", GreyboxFunction.Wall, new Vector3(-(rw + wt) * 0.5f, wh * 0.5f, z0 + rd * 0.5f), new Vector3(wt, wh, rd));
        Box(blocks, "Wall_Room_R", GreyboxFunction.Wall, new Vector3((rw + wt) * 0.5f, wh * 0.5f, z0 + rd * 0.5f), new Vector3(wt, wh, rd));
        Opening(blocks, "Gate", m, z0 + rd + wt * 0.5f, true);

        // ---- left half: the step, then the ramp up to a ledge, then the gap to a second ledge.
        float left = -rw * 0.25f;
        Box(blocks, "Step", GreyboxFunction.Climb, new Vector3(left, m.stepHeight * 0.5f, z0 + 2.5f), new Vector3(3f, m.stepHeight, 2f));

        float run = m.ledgeHeight / Mathf.Tan(Mathf.Clamp(m.rampAngle, 1f, 89f) * Mathf.Deg2Rad);
        float rampStart = z0 + 5f;
        blocks.Add(new GreyboxBlock
        {
            name = "Ramp", function = GreyboxFunction.Climb, shape = GreyboxShape.Ramp, solid = true,
            centre = new Vector3(left, m.ledgeHeight * 0.5f, rampStart + run * 0.5f),
            size = new Vector3(m.rampWidth, m.ledgeHeight, run),
        });
        float ledgeZ = rampStart + run + 1f;
        Box(blocks, "Ledge_A", GreyboxFunction.Jump, new Vector3(left, m.ledgeHeight * 0.5f, ledgeZ), new Vector3(2f, m.ledgeHeight, 2f));
        Box(blocks, "Ledge_B", GreyboxFunction.Jump, new Vector3(left + 2f + m.jumpGap, m.ledgeHeight * 0.5f, ledgeZ), new Vector3(2f, m.ledgeHeight, 2f));

        // ---- right half: the flat route to the switch, past a hazard pad and the sentry's post.
        float right = rw * 0.25f;
        Box(blocks, "GateSwitch", GreyboxFunction.Interact, new Vector3(rw * 0.5f - 1.5f, 0.5f, z0 + rd - 1.5f), new Vector3(0.4f, 1f, 0.4f));
        Marker(blocks, "Hazard_Pad", GreyboxFunction.Hazard, new Vector3(right, 0.01f, z0 + 4f), new Vector3(1.3f, 0.02f, 1.3f));
        Marker(blocks, "Sentry_Post", GreyboxFunction.Sentry, new Vector3(right, 0.01f, z0 + rd - 4f), new Vector3(0.8f, 0.02f, 0.8f));
        Marker(blocks, "Spawn", GreyboxFunction.Marker, new Vector3(0f, 0.01f, 1f), new Vector3(0.8f, 0.02f, 0.8f));

        // ---- the ruler: a body-sized capsule left standing by the door, never removed.
        blocks.Add(new GreyboxBlock
        {
            name = "Ruler_Runner", function = GreyboxFunction.Marker, shape = GreyboxShape.Capsule, solid = false,
            centre = new Vector3(cw * 0.5f - m.bodyRadius, m.bodyHeight * 0.5f, cl - 1f),
            size = new Vector3(m.bodyRadius * 2f, m.bodyHeight, m.bodyRadius * 2f),
        });
        return blocks;
    }

    // A wall across the room with one opening of the door's size at x = 0. The gate adds the
    // block that fills the opening: the thing the switch removes.
    static void Opening(List<GreyboxBlock> blocks, string name, GreyboxMetrics m, float z, bool filled)
    {
        float span = m.roomWidth + m.wallThickness * 2f;
        float side = (span - m.doorWidth) * 0.5f;
        float x = m.doorWidth * 0.5f + side * 0.5f;
        var size = new Vector3(side, m.wallHeight, m.wallThickness);
        Box(blocks, "Wall_" + name + "_L", GreyboxFunction.Wall, new Vector3(-x, m.wallHeight * 0.5f, z), size);
        Box(blocks, "Wall_" + name + "_R", GreyboxFunction.Wall, new Vector3(x, m.wallHeight * 0.5f, z), size);
        float lintel = m.wallHeight - m.doorHeight;
        if (lintel > 0.001f)
            Box(blocks, "Lintel_" + name, GreyboxFunction.Wall, new Vector3(0f, m.doorHeight + lintel * 0.5f, z),
                new Vector3(m.doorWidth, lintel, m.wallThickness));
        if (filled)
            Box(blocks, "Gate", GreyboxFunction.Gate, new Vector3(0f, m.doorHeight * 0.5f, z),
                new Vector3(m.doorWidth, m.doorHeight, m.wallThickness));
    }

    static void Box(List<GreyboxBlock> blocks, string name, GreyboxFunction function, Vector3 centre, Vector3 size) =>
        blocks.Add(new GreyboxBlock { name = name, function = function, shape = GreyboxShape.Box, centre = centre, size = size, solid = true });

    static void Marker(List<GreyboxBlock> blocks, string name, GreyboxFunction function, Vector3 centre, Vector3 size) =>
        blocks.Add(new GreyboxBlock { name = name, function = function, shape = GreyboxShape.Box, centre = centre, size = size, solid = false });

    // ------------------------------------------------------------------ plan

    /// <summary>Every way the numbers disagree with the body. Empty when the sheet holds.</summary>
    public static List<string> Check(GreyboxMetrics m)
    {
        var bad = new List<string>();
        float w = m.bodyRadius * 2f;
        if (m.doorWidth < w * 1.5f) bad.Add("door " + F(m.doorWidth) + " wide is under 1.5 x body width " + F(w) + " = " + F(w * 1.5f));
        if (m.doorHeight < m.bodyHeight * 1.1f) bad.Add("door " + F(m.doorHeight) + " high is under 1.1 x body height = " + F(m.bodyHeight * 1.1f));
        if (m.corridorWidth < w * 2f) bad.Add("corridor " + F(m.corridorWidth) + " is under 2 x body width = " + F(w * 2f));
        if (m.stepHeight > m.stepOffset + 0.0001f) bad.Add("step " + F(m.stepHeight) + " is above the step offset " + F(m.stepOffset) + ": it is a ledge, not a step");
        if (m.rampAngle > m.slopeLimit - 10f) bad.Add("ramp " + F(m.rampAngle) + " degrees is within 10 of the slope limit " + F(m.slopeLimit));
        if (m.wallHeight < m.doorHeight) bad.Add("wall " + F(m.wallHeight) + " is lower than the door " + F(m.doorHeight));
        if (m.roomWidth < 2f + m.jumpGap + 2f + 1f) bad.Add("room " + F(m.roomWidth) + " wide cannot hold two ledges and a gap of " + F(m.jumpGap));
        return bad;
    }

    public static string Plan(GreyboxMetrics m)
    {
        List<GreyboxBlock> blocks = Layout(m);
        int layer = LayerMask.NameToLayer(LayerName);
        var sb = new StringBuilder();
        sb.AppendLine("Scene: " + EditorSceneManager.GetActiveScene().name);
        sb.AppendLine("Create '" + RootName + "' at the origin with " + blocks.Count + " primitives; the runner walks +Z.");
        sb.AppendLine("  door " + F(m.doorWidth) + " x " + F(m.doorHeight) + ", corridor " + F(m.corridorWidth) +
                      ", step " + F(m.stepHeight) + ", ramp " + F(m.rampAngle) + " degrees, ledge " + F(m.ledgeHeight) +
                      ", gap " + F(m.jumpGap) + ", ceiling " + F(m.wallHeight));
        sb.AppendLine(layer >= 0
            ? "Solid blocks go on layer '" + LayerName + "'."
            : "No layer named '" + LayerName + "': solid blocks go on Default. Add the layer in Tags and Layers first to keep queries narrow.");
        sb.AppendLine("Markers (hazard pad, sentry post, spawn, ruler) are built without colliders.");
        sb.AppendLine("One material per function is created inside the scene; no asset is written.");
        if (GameObject.Find(RootName) != null)
            sb.AppendLine("A '" + RootName + "' is already in the scene: a second one is created on top of it.");
        foreach (string problem in Check(m)) sb.AppendLine("WARNING " + problem);
        return sb.ToString();
    }

    // ------------------------------------------------------------------ build

    public static GameObject Build(GreyboxMetrics m)
    {
        int layer = Mathf.Max(0, LayerMask.NameToLayer(LayerName));
        var root = new GameObject(RootName);
        Undo.RegisterCreatedObjectUndo(root, "Build Gate-Room Greybox");

        var materials = new Dictionary<GreyboxFunction, Material>();
        foreach (GreyboxBlock block in Layout(m))
        {
            GameObject go = GameObject.CreatePrimitive(block.shape == GreyboxShape.Capsule ? PrimitiveType.Capsule : PrimitiveType.Cube);
            go.name = block.name;
            go.transform.SetParent(root.transform, false);
            Place(go.transform, block);

            if (!block.solid) Object.DestroyImmediate(go.GetComponent<Collider>());
            else go.layer = layer;

            go.GetComponent<Renderer>().sharedMaterial = MaterialFor(block.function, materials, go.GetComponent<Renderer>());
        }

        EditorSceneManager.MarkSceneDirty(root.scene);
        Debug.Log("[GREYBOX] created " + RootName + " blocks=" + root.transform.childCount +
                  " layer=" + LayerMask.LayerToName(layer) + " warnings=" + Check(m).Count);
        return root;
    }

    /// <summary>Position, rotation and scale of a primitive standing in for a block.</summary>
    public static void Place(Transform t, GreyboxBlock block)
    {
        if (block.shape == GreyboxShape.Ramp)
        {
            // A slab whose top face is the slope. Its ends sink into the floor and the ledge, so
            // there is no lip at either end for a foot to catch on.
            const float slab = 0.2f;
            float angle = Mathf.Atan2(block.size.y, block.size.z) * Mathf.Rad2Deg;
            Quaternion tilt = Quaternion.Euler(-angle, 0f, 0f);
            float length = Mathf.Sqrt(block.size.y * block.size.y + block.size.z * block.size.z);
            t.localRotation = tilt;
            t.localPosition = block.centre - tilt * Vector3.up * (slab * 0.5f);
            t.localScale = new Vector3(block.size.x, slab, length);
        }
        else if (block.shape == GreyboxShape.Capsule)
        {
            // The built-in capsule is 2 high and 1 across.
            t.localPosition = block.centre;
            t.localScale = new Vector3(block.size.x, block.size.y * 0.5f, block.size.z);
        }
        else
        {
            t.localPosition = block.centre;
            t.localScale = block.size;
        }
    }

    /// <summary>One material per function, copied from the active pipeline's default so the
    /// block is lit correctly on URP and on the built-in pipeline alike.</summary>
    public static Material MaterialFor(GreyboxFunction function, Dictionary<GreyboxFunction, Material> cache, Renderer fallback)
    {
        if (cache.TryGetValue(function, out Material found)) return found;
        RenderPipelineAsset pipeline = GraphicsSettings.currentRenderPipeline;
        Material source = pipeline != null && pipeline.defaultMaterial != null ? pipeline.defaultMaterial : fallback.sharedMaterial;
        var material = new Material(source) { name = "Greybox_" + function };
        material.color = ColourOf(function);          // the shader's [MainColor]: _BaseColor on URP Lit
        cache[function] = material;
        return material;
    }

    static string F(float v) => v.ToString("0.##", CultureInfo.InvariantCulture);
}
