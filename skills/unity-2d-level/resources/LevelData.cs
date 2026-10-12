// LevelData.cs — a level as data: size, layers of tile ids, a spawn, a gate, pickups and
// entities with typed fields. The same shape is a ScriptableObject asset in the project and
// a JSON file on disk (reference/level-data.md), and nothing in it references a Unity asset.
//
// Drop into a Runtime assembly. The file name must stay LevelData.cs: the asset type is
// found by it. No package needed — it uses UnityEngine.JsonUtility and nothing from Tilemaps.
//
//   LevelData level = LevelData.FromJson(textAsset.text);     // throws on a wrong format or a newer version
//   List<string> problems = level.Problems();                 // empty when the shape is sound
//   int id = level.TileAt(LevelLayers.Ground, x, y);          // 0 is empty
//
// Cell (0, 0) is the bottom-left cell and y grows upwards, which is Tilemap cell space, so
// no code that reads a LevelData ever flips a row. A converter from an editor whose rows
// run downwards flips once, on the way in.
using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

/// <summary>The layer names of the stack, bottom to top. reference/layer-stack.md.</summary>
public static class LevelLayers
{
    public const string Background = "Background";
    public const string Ground = "Ground";
    public const string Walls = "Walls";
    public const string OneWay = "OneWay";
    public const string Front = "Front";
    public const string Markers = "Markers";

    public static readonly string[] All = { Background, Ground, Walls, OneWay, Front, Markers };
}

[Serializable]
public struct LevelCell
{
    public int x, y;
    public LevelCell(int x, int y) { this.x = x; this.y = y; }
    public Vector3Int ToVector3Int() => new Vector3Int(x, y, 0);
}

/// <summary>One row of the id table. The name is for people; code binds by id.</summary>
[Serializable]
public class LevelTile
{
    public int id;
    public string name;
}

[Serializable]
public class LevelLayer
{
    public string name;
    public int[] cells = Array.Empty<int>();       // width x height tile ids, index = x + y * width, 0 empty
    public int[] flips = Array.Empty<int>();       // empty, or one entry per cell: 1 horizontal, 2 vertical, 4 diagonal
}

[Serializable]
public class LevelField
{
    public string key;
    public string type;                            // "int", "float", "bool", "string": what value parses as
    public string value;
}

[Serializable]
public class LevelEntity
{
    public string id;
    public string type;                            // "pickup", "hazard", "launch", "sentry", "room", "door"…
    public int x, y;                               // the bottom-left cell it occupies
    public int w = 1, h = 1;                       // its size in cells
    public List<LevelField> fields = new List<LevelField>();

    public LevelCell Cell => new LevelCell(x, y);
    public int Width => Mathf.Max(1, w);           // a file that leaves w and h out reads as 0
    public int Height => Mathf.Max(1, h);

    public bool Has(string key) => Find(key) != null;

    public string GetString(string key, string fallback = "")
    {
        LevelField f = Find(key);
        return f != null ? f.value : fallback;
    }

    public int GetInt(string key, int fallback = 0)
    {
        LevelField f = Find(key);
        return f != null && int.TryParse(f.value, NumberStyles.Integer, CultureInfo.InvariantCulture, out int v)
            ? v : fallback;
    }

    // Invariant culture: a level written on one machine reads the same on a machine whose
    // decimal separator is a comma.
    public float GetFloat(string key, float fallback = 0f)
    {
        LevelField f = Find(key);
        return f != null && float.TryParse(f.value, NumberStyles.Float, CultureInfo.InvariantCulture, out float v)
            ? v : fallback;
    }

    public bool GetBool(string key, bool fallback = false)
    {
        LevelField f = Find(key);
        return f != null && bool.TryParse(f.value, out bool v) ? v : fallback;
    }

    LevelField Find(string key)
    {
        for (int i = 0; i < fields.Count; i++)
            if (fields[i].key == key) return fields[i];
        return null;
    }
}

[CreateAssetMenu(menuName = "Unity Dev/Level Data", fileName = "Level")]
public sealed class LevelData : ScriptableObject
{
    public const string Format = "courier-level";
    public const int CurrentVersion = 1;

    public string format = Format;
    public int version = CurrentVersion;
    public string id = "";
    public string view = "side";                   // "side" or "topdown": which layers are solid
    public int width, height;
    public float cellSize = 1f;
    public List<LevelTile> tiles = new List<LevelTile>();
    public List<LevelLayer> layers = new List<LevelLayer>();
    public LevelCell spawn, gate;
    public List<LevelEntity> pickups = new List<LevelEntity>();
    public List<LevelEntity> entities = new List<LevelEntity>();

    // ------------------------------------------------------------------ JSON

    /// <summary>Parse a level file. Throws FormatException when it is not one, or is newer than this code.</summary>
    public static LevelData FromJson(string json)
    {
        LevelData level = CreateInstance<LevelData>();
        level.format = "";                         // so a file with no "format" key does not pass
        level.version = 0;
        JsonUtility.FromJsonOverwrite(json, level);
        if (level.format != Format)
            throw new FormatException("Not a level file: format is '" + level.format + "', expected '" + Format + "'.");
        level.Upgrade();
        if (string.IsNullOrEmpty(level.id)) level.id = "level";
        level.name = level.id;
        return level;
    }

    public string ToJson(bool pretty = false) => JsonUtility.ToJson(this, pretty);

    /// <summary>
    /// Bring an older file up to CurrentVersion, one step per version, in order. A newer file
    /// is refused: reading it with old rules loses whatever the new version added, silently.
    /// </summary>
    public void Upgrade()
    {
        if (version > CurrentVersion)
            throw new FormatException("Level '" + id + "' is version " + version + "; this build reads up to " + CurrentVersion + ".");
        if (version < 1)
            throw new FormatException("Level '" + id + "' has no version.");
        // if (version == 1) { …rename, default, convert…; version = 2; }
        version = CurrentVersion;
    }

    // ------------------------------------------------------------------ cells

    public bool InBounds(int x, int y) => x >= 0 && y >= 0 && x < width && y < height;
    public int Index(int x, int y) => x + y * width;

    public LevelLayer Layer(string layerName)
    {
        for (int i = 0; i < layers.Count; i++)
            if (layers[i].name == layerName) return layers[i];
        return null;
    }

    /// <summary>The tile id at a cell of a layer; 0 when the layer or the cell does not exist.</summary>
    public int TileAt(string layerName, int x, int y)
    {
        LevelLayer layer = Layer(layerName);
        if (layer == null || !InBounds(x, y) || layer.cells.Length != width * height) return 0;
        return layer.cells[Index(x, y)];
    }

    /// <summary>Does the cell stop the runner? Side view: Ground or Walls. Top-down: Walls only.</summary>
    public bool IsSolid(int x, int y)
    {
        if (TileAt(LevelLayers.Walls, x, y) != 0) return true;
        return view != "topdown" && TileAt(LevelLayers.Ground, x, y) != 0;
    }

    public bool IsOneWay(int x, int y) => !IsSolid(x, y) && TileAt(LevelLayers.OneWay, x, y) != 0;

    /// <summary>The centre of a cell in the Grid's local space, for a Grid whose cell size is cellSize.</summary>
    public Vector3 CellCentre(int x, int y) => new Vector3((x + 0.5f) * cellSize, (y + 0.5f) * cellSize, 0f);

    /// <summary>The level's rectangle in the Grid's local space.</summary>
    public Rect LocalRect => new Rect(0f, 0f, width * cellSize, height * cellSize);

    // ------------------------------------------------------------------ shape check

    /// <summary>
    /// Everything wrong with the shape of the data, as sentences. Reachability is not checked
    /// here: scripts/level_validate.py does that on the JSON.
    /// </summary>
    public List<string> Problems()
    {
        var problems = new List<string>();
        if (width <= 0 || height <= 0) problems.Add("width and height must be greater than zero");
        if (cellSize <= 0f) problems.Add("cellSize must be greater than zero");

        var known = new HashSet<int>();
        foreach (LevelTile t in tiles)
            if (t.id <= 0) problems.Add("tile '" + t.name + "' has id " + t.id + "; ids start at 1, 0 means empty");
            else if (!known.Add(t.id)) problems.Add("tile id " + t.id + " is listed twice");

        var layerNames = new HashSet<string>();
        foreach (LevelLayer layer in layers)
        {
            if (!layerNames.Add(layer.name)) problems.Add("layer '" + layer.name + "' appears twice");
            if (Array.IndexOf(LevelLayers.All, layer.name) < 0)
                problems.Add("layer '" + layer.name + "' is not in the layer stack");
            if (layer.cells.Length != width * height)
            {
                problems.Add("layer '" + layer.name + "' has " + layer.cells.Length + " cells, expected " + width * height);
                continue;
            }
            if (layer.flips.Length != 0 && layer.flips.Length != layer.cells.Length)
                problems.Add("layer '" + layer.name + "' has flips for " + layer.flips.Length + " cells");
            for (int i = 0; i < layer.cells.Length; i++)
            {
                if (layer.cells[i] == 0 || known.Contains(layer.cells[i])) continue;
                problems.Add("layer '" + layer.name + "' uses tile id " + layer.cells[i] + ", which is not in the tile table");
                break;
            }
        }

        if (!InBounds(spawn.x, spawn.y)) problems.Add("spawn is outside the level");
        if (!InBounds(gate.x, gate.y)) problems.Add("gate is outside the level");

        var ids = new HashSet<string>();
        CheckEntities(pickups, ids, problems);
        CheckEntities(entities, ids, problems);
        return problems;
    }

    void CheckEntities(List<LevelEntity> list, HashSet<string> ids, List<string> problems)
    {
        foreach (LevelEntity e in list)
        {
            if (string.IsNullOrEmpty(e.id) || !ids.Add(e.id)) problems.Add("entity id '" + e.id + "' is empty or used twice");
            if (string.IsNullOrEmpty(e.type)) problems.Add("entity '" + e.id + "' has no type");
            if (!InBounds(e.x, e.y) || !InBounds(e.x + e.Width - 1, e.y + e.Height - 1))
                problems.Add("entity '" + e.id + "' is outside the level");
        }
    }
}

/// <summary>
/// The reach table a generator or a chunk stitcher holds hops to: the widest gap for each
/// rise, in level units. Fill it by hand, or from the JSON that unity-gameplay's
/// level_metrics.py prints — JsonUtility.FromJson&lt;ReachTable&gt;(text) reads its "reach" rows.
/// </summary>
[Serializable]
public class ReachTable
{
    [Serializable]
    public struct Row
    {
        public float rise;          // landing height minus take-off height
        public float max_gap;       // 100% of reach
        public float usable_gap;    // the share a main path may use
    }

    public List<Row> reach = new List<Row>();

    /// <summary>
    /// The widest usable gap to a landing <paramref name="rise"/> above take-off, or -1 when
    /// the landing is above the highest row. A rise between two rows is held to the higher
    /// row, and a drop below the lowest row to the lowest: both are the shorter gap.
    /// </summary>
    public float UsableGap(float rise)
    {
        float best = -1f, bestRise = float.PositiveInfinity;
        for (int i = 0; i < reach.Count; i++)
        {
            if (reach[i].rise + 1e-4f < rise || reach[i].rise >= bestRise) continue;
            bestRise = reach[i].rise;
            best = reach[i].usable_gap;
        }
        return best;
    }

    public bool Allows(float gap, float rise) => gap <= UsableGap(rise) + 1e-4f;
}
