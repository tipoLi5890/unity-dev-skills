// GridPathfinder.cs — A* paths and movement ranges on a bounded board of rectangular, isometric
// or hexagonal cells. Pure C#, no scene; allocates in the constructor and never again, as long
// as the caller keeps its own cost delegate and result lists.
//
// Drop it beside GridCoords.cs (which it needs) in the assembly that holds the rules. One
// instance per board; it is not thread-safe, and a second search overwrites the first one's
// working arrays, so read CostTo and PathFromRange before searching again.
//
// Costs are integers in TENTHS of a move point: a straight step onto terrain of cost 1 is 10, a
// diagonal step is DiagonalWeight (14, or 10 when a diagonal is one step). Range takes whole
// move points and multiplies by 10 itself.
//
//   var finder = new GridPathfinder(origin, 9, 7, GridShape.Rect4);
//   GridPathfinder.EnterCost cost = (from, to) => occupancy.CanEnter(to) ? 1 : 0;   // cache this
//   if (finder.FindPath(runnerCell, gateCell, cost, path)) { /* path[0] is the start */ }
//   finder.Range(runnerCell, 4, cost, reachable);                                   // start included
using System;
using System.Collections.Generic;
using UnityEngine;

public sealed class GridPathfinder
{
    /// <summary>The terrain cost of entering <paramref name="to"/> from the adjacent
    /// <paramref name="from"/>: 1 for open floor, 2 for slow ground, 0 or less for "cannot enter".
    /// One delegate per kind of unit is how passability differs between units.</summary>
    public delegate int EnterCost(Vector3Int from, Vector3Int to);

    public const int Straight = 10;

    /// <summary>Rect8 only. 14 prices a diagonal at about root two; 10 makes a diagonal one step
    /// (Chebyshev). Keep it between 10 and 20: below 10 the heuristic overestimates and paths
    /// stop being shortest. The heuristic follows this value, so change it here and nowhere else.</summary>
    public int DiagonalWeight = 14;

    /// <summary>Rect8 only. False (the default) forbids a diagonal step unless both cells it
    /// squeezes between can be entered, so a path never clips a wall's corner.</summary>
    public bool CutCorners;

    /// <summary>Total cost of the path FindPath last returned, in tenths of a move point.</summary>
    public int PathCost { get; private set; }

    /// <summary>Cells taken off the open set by the last search. A number to watch, not to assert.</summary>
    public int Expanded { get; private set; }

    public readonly GridShape Shape;
    public readonly Vector3Int Origin;
    public readonly int Width, Height;

    readonly bool _oddShifted;
    readonly int _neighbours;
    readonly int[] _g, _parent, _stamp, _heapPos, _heap, _f, _h;
    readonly bool[] _closed;
    int _heapCount, _generation, _lastStart = -1;
    bool _lastWasRange;

    /// <summary>A board of <paramref name="width"/> × <paramref name="height"/> cells whose
    /// lowest cell is <paramref name="origin"/>. Every cell outside it is impassable.</summary>
    public GridPathfinder(Vector3Int origin, int width, int height, GridShape shape, bool oddShifted = true)
    {
        if (width <= 0 || height <= 0) throw new ArgumentException("GridPathfinder: the board needs a positive width and height.");
        Origin = new Vector3Int(origin.x, origin.y, 0);
        Width = width; Height = height; Shape = shape;
        _oddShifted = oddShifted;
        _neighbours = GridCoords.NeighbourCount(shape);
        int n = width * height;
        _g = new int[n]; _parent = new int[n]; _stamp = new int[n]; _heapPos = new int[n];
        _heap = new int[n]; _f = new int[n]; _h = new int[n]; _closed = new bool[n];
    }

    public bool Contains(Vector3Int cell)
    {
        int x = cell.x - Origin.x, y = cell.y - Origin.y;
        return x >= 0 && y >= 0 && x < Width && y < Height;
    }

    /// <summary>The cheapest path from start to goal, both included, written into
    /// <paramref name="path"/> (cleared first). False, with an empty list, when the goal cannot be
    /// reached. The start cell's own cost is never asked for: a unit stands where it stands.</summary>
    public bool FindPath(Vector3Int start, Vector3Int goal, EnterCost cost, List<Vector3Int> path)
    {
        path.Clear();
        PathCost = 0; Expanded = 0;
        _lastWasRange = false; _lastStart = -1;
        if (cost == null) throw new ArgumentNullException(nameof(cost));
        if (!Contains(start) || !Contains(goal)) return false;
        int s = Index(start), t = Index(goal);
        if (s == t) { path.Add(Cell(s)); return true; }

        Begin(s, Heuristic(start, goal));
        while (_heapCount > 0)
        {
            int current = Pop();
            Expanded++;
            if (current == t)
            {
                PathCost = _g[t];
                Trace(t, path);
                return true;
            }
            Vector3Int from = Cell(current);
            for (int i = 0; i < _neighbours; i++)
            {
                Vector3Int to = GridCoords.Neighbour(Shape, from, i, _oddShifted);
                int step = StepCost(from, to, i, cost);
                if (step <= 0) continue;
                Relax(current, Index(to), _g[current] + step, Heuristic(to, goal));
            }
        }
        return false;
    }

    /// <summary>Every cell whose cheapest route from start costs at most
    /// <paramref name="movePoints"/>, start included, nearest first, written into
    /// <paramref name="reached"/> (cleared first). Returns the count. This is a flood through the
    /// cost delegate, so it stops at walls; "every cell within distance N" does not.</summary>
    public int Range(Vector3Int start, int movePoints, EnterCost cost, List<Vector3Int> reached)
    {
        reached.Clear();
        Expanded = 0;
        _lastWasRange = false; _lastStart = -1;
        if (cost == null) throw new ArgumentNullException(nameof(cost));
        if (!Contains(start) || movePoints < 0) return 0;
        int budget = movePoints * Straight;
        int s = Index(start);

        Begin(s, 0);
        while (_heapCount > 0)
        {
            int current = Pop();
            Expanded++;
            Vector3Int from = Cell(current);
            reached.Add(from);
            for (int i = 0; i < _neighbours; i++)
            {
                Vector3Int to = GridCoords.Neighbour(Shape, from, i, _oddShifted);
                int step = StepCost(from, to, i, cost);
                if (step <= 0 || _g[current] + step > budget) continue;
                Relax(current, Index(to), _g[current] + step, 0);
            }
        }
        _lastWasRange = true; _lastStart = s;
        return reached.Count;
    }

    /// <summary>After Range: the cost of reaching <paramref name="cell"/> in tenths of a move
    /// point, or -1 when it was not reached.</summary>
    public int CostTo(Vector3Int cell)
    {
        if (!_lastWasRange || !Contains(cell)) return -1;
        int i = Index(cell);
        return _stamp[i] == _generation && _closed[i] ? _g[i] : -1;
    }

    /// <summary>After Range: the path from that range's start to <paramref name="goal"/>, without
    /// a second search. False when the goal was not in the range.</summary>
    public bool PathFromRange(Vector3Int goal, List<Vector3Int> path)
    {
        path.Clear();
        if (CostTo(goal) < 0) return false;
        Trace(Index(goal), path);
        return true;
    }

    // ------------------------------------------------------------------ internals

    int Index(Vector3Int c) => (c.y - Origin.y) * Width + (c.x - Origin.x);

    Vector3Int Cell(int i) => new Vector3Int(Origin.x + i % Width, Origin.y + i / Width, 0);

    int StepCost(Vector3Int from, Vector3Int to, int direction, EnterCost cost)
    {
        if (!Contains(to)) return 0;
        int terrain = cost(from, to);
        if (terrain <= 0) return 0;
        if (Shape != GridShape.Rect8 || direction < 4) return terrain * Straight;
        if (!CutCorners)
        {
            var sideA = new Vector3Int(to.x, from.y, 0);
            var sideB = new Vector3Int(from.x, to.y, 0);
            if (!Contains(sideA) || !Contains(sideB) || cost(from, sideA) <= 0 || cost(from, sideB) <= 0) return 0;
        }
        return terrain * DiagonalWeight;
    }

    // Never more than the true remaining cost while every terrain cost is 1 or more.
    int Heuristic(Vector3Int a, Vector3Int b)
    {
        switch (Shape)
        {
            case GridShape.Rect4: return GridCoords.Manhattan(a, b) * Straight;
            case GridShape.Rect8: return GridCoords.Octile(a, b, Straight, Math.Max(Straight, Math.Min(DiagonalWeight, 2 * Straight)));
            default: return GridCoords.HexDistance(a, b, _oddShifted) * Straight;
        }
    }

    void Begin(int start, int h)
    {
        // A fresh generation is what "clears" the arrays: a cell whose stamp is old is unvisited.
        if (++_generation == int.MaxValue) { Array.Clear(_stamp, 0, _stamp.Length); _generation = 1; }
        _heapCount = 0;
        Visit(start, 0, -1, h);
        Push(start);
    }

    void Visit(int i, int g, int parent, int h)
    {
        _stamp[i] = _generation; _closed[i] = false;
        _g[i] = g; _parent[i] = parent; _h[i] = h; _f[i] = g + h; _heapPos[i] = -1;
    }

    void Relax(int from, int to, int g, int h)
    {
        if (_stamp[to] != _generation)
        {
            Visit(to, g, from, h);
            Push(to);
        }
        else if (!_closed[to] && g < _g[to])
        {
            _g[to] = g; _parent[to] = from; _f[to] = g + _h[to];
            SiftUp(_heapPos[to]);
        }
    }

    void Trace(int goal, List<Vector3Int> path)
    {
        int first = path.Count;
        for (int i = goal; i >= 0; i = _parent[i]) path.Add(Cell(i));
        path.Reverse(first, path.Count - first);
    }

    // Binary min-heap of cell indices keyed by f, then by h (the cell nearer the goal), then by
    // index, so two runs over the same board pop in the same order and return the same path.
    bool Less(int a, int b)
    {
        if (_f[a] != _f[b]) return _f[a] < _f[b];
        if (_h[a] != _h[b]) return _h[a] < _h[b];
        return a < b;
    }

    void Push(int cell)
    {
        _heap[_heapCount] = cell; _heapPos[cell] = _heapCount;
        SiftUp(_heapCount++);
    }

    int Pop()
    {
        int top = _heap[0];
        _closed[top] = true; _heapPos[top] = -1;
        if (--_heapCount > 0)
        {
            _heap[0] = _heap[_heapCount]; _heapPos[_heap[0]] = 0;
            SiftDown(0);
        }
        return top;
    }

    void SiftUp(int i)
    {
        int cell = _heap[i];
        while (i > 0)
        {
            int up = (i - 1) / 2;
            if (!Less(cell, _heap[up])) break;
            _heap[i] = _heap[up]; _heapPos[_heap[i]] = i;
            i = up;
        }
        _heap[i] = cell; _heapPos[cell] = i;
    }

    void SiftDown(int i)
    {
        int cell = _heap[i];
        while (true)
        {
            int child = 2 * i + 1;
            if (child >= _heapCount) break;
            if (child + 1 < _heapCount && Less(_heap[child + 1], _heap[child])) child++;
            if (!Less(_heap[child], cell)) break;
            _heap[i] = _heap[child]; _heapPos[_heap[i]] = i;
            i = child;
        }
        _heap[i] = cell; _heapPos[cell] = i;
    }
}
