// TilemapLevelLoader.cs — paints a LevelData into the layer stack and hands its entities to
// the game. The LevelData stays the truth; the Tilemaps are one rendering of it.
//
// Drop into a Runtime assembly beside LevelData.cs and put it on the Grid that owns the
// layer Tilemaps (children named Background, Ground, Walls, OneWay, Front, Markers — build
// them with Tools/Unity Dev/2D Level/Build Layer Stack).
//
// REQUIRES the built-in Tilemap and 2D physics modules (com.unity.modules.tilemap,
// com.unity.modules.physics2d). No tile type from com.unity.2d.tilemap.extras is named here:
// a RuleTile is bound through its TileBase like any other tile.
//
//   loader.spawnEntity = (entity, position) => pool.Spawn(entity.type, position, entity);
//   loader.Load(LevelData.FromJson(json.text));
//   runner.position = loader.SpawnPosition;
//
// One SetTilesBlock per layer, not one SetTile per cell: every SetTile refreshes the cell
// and its neighbours and marks the collider dirty, and a 200 x 40 level is 8000 of those.
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Tilemaps;

public sealed class TilemapLevelLoader : MonoBehaviour
{
    [Serializable]
    public struct TileBinding
    {
        public int id;              // the id in LevelData.tiles
        public TileBase tile;       // what this project draws for it
    }

    [Serializable]
    public struct MarkerBinding
    {
        public TileBase tile;       // a tile painted on the Markers layer
        public string entityType;   // "spawn", "gate", "pickup", or any entity type
    }

    [Tooltip("The Grid whose child Tilemaps are the layer stack. Empty means this object.")]
    public Grid grid;

    [Tooltip("Tile id to tile asset. One table for every level of the game.")]
    public List<TileBinding> tiles = new List<TileBinding>();

    [Tooltip("Marker tile to entity type, for levels painted by hand and read with Capture.")]
    public List<MarkerBinding> markers = new List<MarkerBinding>();

    /// <summary>Called once per pickup and entity with the world position of its centre.</summary>
    public Action<LevelEntity, Vector3> spawnEntity;

    public LevelData Loaded { get; private set; }
    public Vector3 SpawnPosition => CellCentreWorld(Loaded.spawn.x, Loaded.spawn.y);
    public Vector3 GatePosition => CellCentreWorld(Loaded.gate.x, Loaded.gate.y);

    readonly Dictionary<string, Tilemap> _maps = new Dictionary<string, Tilemap>();
    readonly Dictionary<int, TileBase> _byId = new Dictionary<int, TileBase>();
    readonly List<TileChangeData> _flipped = new List<TileChangeData>();
    TileBase[] _block = Array.Empty<TileBase>();

    // ------------------------------------------------------------------ load

    /// <summary>
    /// Replace whatever the stack shows with this level. Throws before painting anything when
    /// the data is malformed, a tile id has no binding or a layer has no Tilemap: a level
    /// that loads with holes is found by a player, a level that refuses to load by a test.
    /// </summary>
    public void Load(LevelData level)
    {
        if (level == null) throw new ArgumentNullException(nameof(level));
        List<string> problems = level.Problems();
        Bind();
        foreach (LevelLayer layer in level.layers)
        {
            if (!_maps.ContainsKey(layer.name)) problems.Add("no child Tilemap named '" + layer.name + "' under " + grid.name);
            foreach (int id in layer.cells)
                if (id != 0 && !_byId.ContainsKey(id))
                {
                    problems.Add("tile id " + id + " (layer '" + layer.name + "') has no binding on " + name);
                    break;
                }
        }
        if (problems.Count > 0)
            throw new InvalidOperationException("Level '" + level.id + "' cannot load:\n  " + string.Join("\n  ", problems));
        if (Mathf.Abs(grid.cellSize.x - level.cellSize) > 1e-4f)
            Debug.LogWarning("[LEVEL] '" + level.id + "' is authored at cell size " + level.cellSize +
                             " and the Grid is " + grid.cellSize.x + ": entity positions follow the Grid.", this);

        var bounds = new BoundsInt(0, 0, 0, level.width, level.height, 1);   // a z size of 0 holds no cells
        if (_block.Length != level.width * level.height) _block = new TileBase[level.width * level.height];

        foreach (KeyValuePair<string, Tilemap> pair in _maps)
        {
            Tilemap map = pair.Value;
            map.ClearAllTiles();
            LevelLayer layer = level.Layer(pair.Key);
            if (layer == null) continue;

            // The block is filled x first, then y — the order of LevelLayer.cells. Verify()
            // reads it back cell by cell; run it once per project.
            for (int i = 0; i < _block.Length; i++)
                _block[i] = layer.cells[i] == 0 ? null : _byId[layer.cells[i]];
            map.SetTilesBlock(bounds, _block);

            if (layer.flips.Length == layer.cells.Length)
            {
                _flipped.Clear();
                for (int i = 0; i < layer.flips.Length; i++)
                {
                    if (layer.flips[i] == 0 || layer.cells[i] == 0) continue;
                    _flipped.Add(new TileChangeData
                    {
                        position = new Vector3Int(i % level.width, i / level.width, 0),
                        tile = _block[i],
                        color = Color.white,
                        transform = FlipMatrix(layer.flips[i]),
                    });
                }
                // ignoreLockFlags: a Tile asset that locks its transform would drop the flip.
                if (_flipped.Count > 0) map.SetTiles(_flipped.ToArray(), true);
            }
            map.CompressBounds();
        }

        SyncColliders();
        if (_maps.TryGetValue(LevelLayers.Markers, out Tilemap markerMap)) Hide(markerMap);

        Loaded = level;
        if (spawnEntity != null)
        {
            foreach (LevelEntity e in level.pickups) spawnEntity(e, EntityCentreWorld(e));
            foreach (LevelEntity e in level.entities) spawnEntity(e, EntityCentreWorld(e));
        }
    }

    /// <summary>Change one cell at runtime: the data first, then its rendering.</summary>
    public void SetCell(string layerName, int x, int y, int tileId)
    {
        LevelLayer layer = Loaded != null ? Loaded.Layer(layerName) : null;
        if (layer == null || !Loaded.InBounds(x, y)) throw new ArgumentOutOfRangeException(nameof(layerName), layerName + " (" + x + ", " + y + ")");
        TileBase tile = null;
        if (tileId != 0 && !_byId.TryGetValue(tileId, out tile)) throw new ArgumentException("tile id " + tileId + " has no binding");
        layer.cells[Loaded.Index(x, y)] = tileId;
        _maps[layerName].SetTile(new Vector3Int(x, y, 0), tile);
    }

    /// <summary>
    /// Make every tilemap collider in the stack match its tiles now. Without this the
    /// colliders catch up later in the frame, and a runner placed straight after Load
    /// spends its first physics step with no floor.
    /// </summary>
    public void SyncColliders()
    {
        foreach (Tilemap map in _maps.Values)
        {
            if (!map.TryGetComponent(out TilemapCollider2D tiles2D)) continue;
            if (tiles2D.hasTilemapChanges) tiles2D.ProcessTilemapChanges();
            if (map.TryGetComponent(out CompositeCollider2D composite) &&
                composite.generationType == CompositeCollider2D.GenerationType.Manual)
                composite.GenerateGeometry();
        }
    }

    public Vector3 CellCentreWorld(int x, int y) => grid.GetCellCenterWorld(new Vector3Int(x, y, 0));

    /// <summary>The world centre of the cells an entity covers.</summary>
    public Vector3 EntityCentreWorld(LevelEntity e)
    {
        var centre = new Vector3(e.x + e.Width * 0.5f, e.y + e.Height * 0.5f, 0f);
        return grid.LocalToWorld(grid.CellToLocalInterpolated(centre));
    }

    // ------------------------------------------------------------------ read back

    /// <summary>
    /// Count the cells whose painted tile differs from the data. 0 after Load proves the id
    /// table, the block order and the layer names in one number.
    /// </summary>
    public int Verify(LevelData level)
    {
        Bind();
        int wrong = 0;
        foreach (LevelLayer layer in level.layers)
        {
            if (!_maps.TryGetValue(layer.name, out Tilemap map)) { wrong += layer.cells.Length; continue; }
            for (int y = 0; y < level.height; y++)
                for (int x = 0; x < level.width; x++)
                {
                    int id = layer.cells[level.Index(x, y)];
                    TileBase expected = id != 0 && _byId.TryGetValue(id, out TileBase t) ? t : null;
                    if (map.GetTile(new Vector3Int(x, y, 0)) != expected) wrong++;
                }
        }
        return wrong;
    }

    [ContextMenu("Verify Loaded Level")]
    void VerifyLoaded()
    {
        if (Loaded == null) { Debug.LogWarning("[LEVEL] nothing loaded", this); return; }
        Debug.Log("[LEVEL] '" + Loaded.id + "' mismatched cells: " + Verify(Loaded), this);
    }

    /// <summary>
    /// Read a hand-painted stack into a LevelData: tiles become ids through the same table,
    /// and tiles on the Markers layer become the spawn, the gate, pickups and entities. The
    /// lowest painted cell becomes (0, 0). Tile flips are not read back. Throws on a tile
    /// with no binding and on a level without exactly one spawn and one gate marker.
    /// </summary>
    public LevelData Capture(string levelId, string view)
    {
        Bind();
        var idOf = new Dictionary<TileBase, int>();
        foreach (TileBinding b in tiles) if (b.tile != null) idOf[b.tile] = b.id;
        var typeOf = new Dictionary<TileBase, string>();
        foreach (MarkerBinding m in markers) if (m.tile != null) typeOf[m.tile] = m.entityType;

        bool any = false;
        int minX = 0, minY = 0, maxX = 0, maxY = 0;
        foreach (Tilemap map in _maps.Values)
        {
            map.CompressBounds();
            BoundsInt b = map.cellBounds;
            if (b.size.x == 0 || b.size.y == 0) continue;
            minX = any ? Mathf.Min(minX, b.xMin) : b.xMin; minY = any ? Mathf.Min(minY, b.yMin) : b.yMin;
            maxX = any ? Mathf.Max(maxX, b.xMax) : b.xMax; maxY = any ? Mathf.Max(maxY, b.yMax) : b.yMax;
            any = true;
        }
        if (!any) throw new InvalidOperationException("Nothing is painted under " + grid.name + ".");

        LevelData level = ScriptableObject.CreateInstance<LevelData>();
        level.id = levelId; level.name = levelId; level.view = view;
        level.width = maxX - minX; level.height = maxY - minY;
        level.cellSize = grid.cellSize.x;
        var used = new SortedSet<int>();
        int spawns = 0, gates = 0;

        foreach (string layerName in LevelLayers.All)
        {
            if (!_maps.TryGetValue(layerName, out Tilemap map)) continue;
            bool isMarkers = layerName == LevelLayers.Markers;
            var cells = new int[level.width * level.height];
            bool painted = false;
            for (int y = 0; y < level.height; y++)
                for (int x = 0; x < level.width; x++)
                {
                    TileBase tile = map.GetTile(new Vector3Int(minX + x, minY + y, 0));
                    if (tile == null) continue;
                    if (isMarkers)
                    {
                        if (!typeOf.TryGetValue(tile, out string type))
                            throw new InvalidOperationException("Marker tile '" + tile.name + "' at (" + x + ", " + y + ") has no entity type.");
                        if (type == "spawn") { level.spawn = new LevelCell(x, y); spawns++; }
                        else if (type == "gate") { level.gate = new LevelCell(x, y); gates++; }
                        else
                        {
                            var e = new LevelEntity { id = type + "-" + x + "-" + y, type = type, x = x, y = y };
                            (type == "pickup" ? level.pickups : level.entities).Add(e);
                        }
                        continue;
                    }
                    if (!idOf.TryGetValue(tile, out int id))
                        throw new InvalidOperationException("Tile '" + tile.name + "' on layer '" + layerName + "' has no id binding.");
                    cells[level.Index(x, y)] = id;
                    used.Add(id);
                    painted = true;
                }
            if (painted) level.layers.Add(new LevelLayer { name = layerName, cells = cells });
        }
        if (spawns != 1 || gates != 1)
            throw new InvalidOperationException("A level has exactly one spawn and one gate marker; found " + spawns + " and " + gates + ".");
        foreach (int id in used)
        {
            TileBase tile = _byId[id];
            level.tiles.Add(new LevelTile { id = id, name = tile.name });
        }
        return level;
    }

    // ------------------------------------------------------------------ internals

    void Bind()
    {
        if (grid == null) grid = GetComponent<Grid>();
        if (grid == null) throw new InvalidOperationException(name + " needs a Grid: assign one or put the loader on it.");
        _maps.Clear();
        foreach (string layerName in LevelLayers.All)
        {
            Transform child = grid.transform.Find(layerName);
            if (child != null && child.TryGetComponent(out Tilemap map)) _maps[layerName] = map;
        }
        _byId.Clear();
        foreach (TileBinding b in tiles)
        {
            if (b.tile == null) continue;
            if (_byId.ContainsKey(b.id)) throw new InvalidOperationException("Tile id " + b.id + " is bound twice on " + name + ".");
            _byId[b.id] = b.tile;
        }
    }

    // The markers are read, then never drawn: the layer is data that happens to be painted.
    static void Hide(Tilemap markerMap)
    {
        if (markerMap.TryGetComponent(out TilemapRenderer r)) r.enabled = false;
    }

    // flips: 1 horizontal, 2 vertical, 4 diagonal; the diagonal flip is applied first. With
    // y up, the diagonal flip maps (x, y) to (-y, -x), so 4 + 1 is a quarter turn clockwise.
    // The matrix turns the sprite about the tile anchor, so flipped tiles want a centred pivot.
    static Matrix4x4 FlipMatrix(int flips)
    {
        float m00 = 1f, m01 = 0f, m10 = 0f, m11 = 1f;
        if ((flips & 4) != 0) { m00 = 0f; m01 = -1f; m10 = -1f; m11 = 0f; }
        if ((flips & 1) != 0) { m00 = -m00; m01 = -m01; }
        if ((flips & 2) != 0) { m10 = -m10; m11 = -m11; }
        Matrix4x4 m = Matrix4x4.identity;
        m.m00 = m00; m.m01 = m01; m.m10 = m10; m.m11 = m11;
        return m;
    }
}
