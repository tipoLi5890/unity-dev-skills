// GridCoords.cs — cell arithmetic for rectangular, isometric and hexagonal boards: neighbours,
// distances, hexagonal offset <-> axial <-> cube, rings and lines. Static, pure C#, no scene.
//
// Drop it into the assembly that holds the rules (the simulation), beside GridPathfinder.cs,
// GridOccupancy.cs and TurnQueue.cs. The only engine type used is UnityEngine.Vector3Int, so a
// cell here is the value Grid.WorldToCell and Tilemap.GetTile already speak, and EditMode tests
// run it with no scene. In an assembly with noEngineReferences, replace Vector3Int and
// Vector2Int with a three-int and a two-int struct of your own that implement IEquatable<T>;
// nothing else in these files touches the engine.
//
// Conventions
//   * A board cell is Vector3Int (x, y, 0). Isometric boards use the rectangular functions:
//     isometric is a drawing convention, not a neighbour rule.
//   * A hexagonal board cell is Unity's OFFSET coordinate: rows where y is odd sit half a cell
//     along +x. Arithmetic happens in CUBE coordinates, Vector3Int (q, r, s) with q + r + s == 0
//     and r equal to the offset row. Convert at the edges with OffsetToCube / CubeToOffset.
//   * Nothing here knows world units. Cell <-> world is Grid's job, in the presenter.
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>The neighbour rule of a board. Isometric boards are Rect4 or Rect8.</summary>
public enum GridShape
{
    /// <summary>Four neighbours; distance is Manhattan.</summary>
    Rect4,
    /// <summary>Eight neighbours; distance is Chebyshev, or octile when diagonals cost more.</summary>
    Rect8,
    /// <summary>Six neighbours on Unity's offset layout; distance is the cube distance.</summary>
    Hex,
}

public static class GridCoords
{
    // ------------------------------------------------------------------ directions

    /// <summary>E, N, W, S. The opposite of i is (i + 2) % 4.</summary>
    public static readonly Vector3Int[] Dirs4 =
    {
        new Vector3Int(1, 0, 0), new Vector3Int(0, 1, 0), new Vector3Int(-1, 0, 0), new Vector3Int(0, -1, 0),
    };

    /// <summary>E, N, W, S, then NE, NW, SW, SE. The four cardinals come first on purpose: a search
    /// that visits them first prefers straight runs when costs tie.</summary>
    public static readonly Vector3Int[] Dirs8 =
    {
        new Vector3Int(1, 0, 0), new Vector3Int(0, 1, 0), new Vector3Int(-1, 0, 0), new Vector3Int(0, -1, 0),
        new Vector3Int(1, 1, 0), new Vector3Int(-1, 1, 0), new Vector3Int(-1, -1, 0), new Vector3Int(1, -1, 0),
    };

    /// <summary>Cube steps (q, r, s), anticlockwise from +q. On a point-top Grid they read
    /// E, NE, NW, W, SW, SE; on a flat-top Grid (swizzle YXZ) the same six read N, NE, SE, S, SW, NW.
    /// The opposite of i is (i + 3) % 6.</summary>
    public static readonly Vector3Int[] CubeDirs =
    {
        new Vector3Int(1, 0, -1), new Vector3Int(0, 1, -1), new Vector3Int(-1, 1, 0),
        new Vector3Int(-1, 0, 1), new Vector3Int(0, -1, 1), new Vector3Int(1, -1, 0),
    };

    public static int NeighbourCount(GridShape shape) => shape == GridShape.Rect4 ? 4 : shape == GridShape.Rect8 ? 8 : 6;

    /// <summary>The index of the direction pointing back.</summary>
    public static int Opposite(GridShape shape, int direction)
    {
        switch (shape)
        {
            case GridShape.Rect4: return (direction + 2) % 4;
            case GridShape.Rect8: return direction < 4 ? (direction + 2) % 4 : 4 + (direction - 4 + 2) % 4;
            default: return (direction + 3) % 6;
        }
    }

    /// <summary>The neighbour of a board cell in direction index 0 .. NeighbourCount - 1. The one
    /// function every rule calls: on a hexagonal board `cell + offset` is wrong on every second row.</summary>
    public static Vector3Int Neighbour(GridShape shape, Vector3Int cell, int direction, bool oddShifted = true)
    {
        switch (shape)
        {
            case GridShape.Rect4: return cell + Dirs4[direction];
            case GridShape.Rect8: return cell + Dirs8[direction];
            default: return CubeToOffset(OffsetToCube(cell, oddShifted) + CubeDirs[direction], oddShifted);
        }
    }

    /// <summary>The direction index that takes <paramref name="from"/> to the adjacent
    /// <paramref name="to"/>, or -1 when the two are not neighbours.</summary>
    public static int DirectionTo(GridShape shape, Vector3Int from, Vector3Int to, bool oddShifted = true)
    {
        int n = NeighbourCount(shape);
        for (int i = 0; i < n; i++)
            if (Neighbour(shape, from, i, oddShifted) == to) return i;
        return -1;
    }

    // ------------------------------------------------------------------ hexagonal conversions

    /// <summary>Unity offset cell -> cube (q, r, s). <paramref name="oddShifted"/> is true for
    /// Unity's Hexagon layout, where rows with odd y sit half a cell along +x; pass false only if
    /// the GetCellCenterWorld check in reference/coordinates.md says the even rows shift.</summary>
    public static Vector3Int OffsetToCube(Vector3Int cell, bool oddShifted = true)
    {
        int parity = cell.y & 1;                      // 1 for odd rows, negative ones included
        int q = cell.x - (cell.y - (oddShifted ? parity : -parity)) / 2;
        return new Vector3Int(q, cell.y, -q - cell.y);
    }

    /// <summary>Cube (q, r, s) -> Unity offset cell (x, y, 0).</summary>
    public static Vector3Int CubeToOffset(Vector3Int cube, bool oddShifted = true)
    {
        int parity = cube.y & 1;
        return new Vector3Int(cube.x + (cube.y - (oddShifted ? parity : -parity)) / 2, cube.y, 0);
    }

    /// <summary>Axial is cube without the redundant third number: (q, r).</summary>
    public static Vector2Int CubeToAxial(Vector3Int cube) => new Vector2Int(cube.x, cube.y);

    public static Vector3Int AxialToCube(Vector2Int axial) => new Vector3Int(axial.x, axial.y, -axial.x - axial.y);

    public static Vector2Int OffsetToAxial(Vector3Int cell, bool oddShifted = true) => CubeToAxial(OffsetToCube(cell, oddShifted));

    public static Vector3Int AxialToOffset(Vector2Int axial, bool oddShifted = true) => CubeToOffset(AxialToCube(axial), oddShifted);

    /// <summary>The cube cell nearest a fractional cube position. Rounds all three, then repairs
    /// the one that moved furthest so q + r + s is 0 again.</summary>
    public static Vector3Int CubeRound(double q, double r, double s)
    {
        int rq = (int)Math.Round(q), rr = (int)Math.Round(r), rs = (int)Math.Round(s);
        double dq = Math.Abs(rq - q), dr = Math.Abs(rr - r), ds = Math.Abs(rs - s);
        if (dq > dr && dq > ds) rq = -rr - rs;
        else if (dr > ds) rr = -rq - rs;
        else rs = -rq - rr;
        return new Vector3Int(rq, rr, rs);
    }

    // ------------------------------------------------------------------ distances

    /// <summary>Steps between two cells with four neighbours.</summary>
    public static int Manhattan(Vector3Int a, Vector3Int b) => Math.Abs(a.x - b.x) + Math.Abs(a.y - b.y);

    /// <summary>Steps between two cells with eight neighbours when a diagonal costs one step.</summary>
    public static int Chebyshev(Vector3Int a, Vector3Int b) => Math.Max(Math.Abs(a.x - b.x), Math.Abs(a.y - b.y));

    /// <summary>Cost between two cells with eight neighbours when a straight step costs
    /// <paramref name="straight"/> and a diagonal <paramref name="diagonal"/> (10 and 14 by default).</summary>
    public static int Octile(Vector3Int a, Vector3Int b, int straight = 10, int diagonal = 14)
    {
        int dx = Math.Abs(a.x - b.x), dy = Math.Abs(a.y - b.y);
        int min = Math.Min(dx, dy), max = Math.Max(dx, dy);
        return diagonal * min + straight * (max - min);
    }

    /// <summary>Steps between two CUBE cells.</summary>
    public static int CubeDistance(Vector3Int a, Vector3Int b) =>
        (Math.Abs(a.x - b.x) + Math.Abs(a.y - b.y) + Math.Abs(a.z - b.z)) / 2;

    /// <summary>Steps between two hexagonal OFFSET cells.</summary>
    public static int HexDistance(Vector3Int a, Vector3Int b, bool oddShifted = true) =>
        CubeDistance(OffsetToCube(a, oddShifted), OffsetToCube(b, oddShifted));

    /// <summary>Steps between two board cells under the shape's own metric: Manhattan, Chebyshev or hex.</summary>
    public static int Distance(GridShape shape, Vector3Int a, Vector3Int b, bool oddShifted = true)
    {
        switch (shape)
        {
            case GridShape.Rect4: return Manhattan(a, b);
            case GridShape.Rect8: return Chebyshev(a, b);
            default: return HexDistance(a, b, oddShifted);
        }
    }

    // ------------------------------------------------------------------ rings and discs

    /// <summary>Appends every cell exactly <paramref name="radius"/> steps from the centre by the
    /// shape's metric, ignoring walls: a diamond outline, a square outline or a hexagon outline.
    /// This is an attack range, not a movement range.</summary>
    public static void Ring(GridShape shape, Vector3Int centre, int radius, List<Vector3Int> into, bool oddShifted = true)
    {
        if (radius < 0) return;
        if (radius == 0) { into.Add(centre); return; }
        if (shape == GridShape.Hex)
        {
            Vector3Int cube = OffsetToCube(centre, oddShifted) + CubeDirs[4] * radius;
            for (int side = 0; side < 6; side++)
                for (int i = 0; i < radius; i++)
                {
                    into.Add(CubeToOffset(cube, oddShifted));
                    cube += CubeDirs[side];
                }
            return;
        }
        for (int dy = -radius; dy <= radius; dy++)
            for (int dx = -radius; dx <= radius; dx++)
            {
                int d = shape == GridShape.Rect4 ? Math.Abs(dx) + Math.Abs(dy) : Math.Max(Math.Abs(dx), Math.Abs(dy));
                if (d == radius) into.Add(new Vector3Int(centre.x + dx, centre.y + dy, 0));
            }
    }

    /// <summary>Appends every cell from <paramref name="minRadius"/> to <paramref name="maxRadius"/>
    /// steps away, nearest ring first.</summary>
    public static void Disc(GridShape shape, Vector3Int centre, int minRadius, int maxRadius, List<Vector3Int> into, bool oddShifted = true)
    {
        for (int r = Math.Max(0, minRadius); r <= maxRadius; r++) Ring(shape, centre, r, into, oddShifted);
    }

    // ------------------------------------------------------------------ lines

    /// <summary>Appends a Bresenham line from a to b, both included: one cell per step along the
    /// longer axis, so it slips diagonally between two cells that touch at a corner. Traced from
    /// the lesser endpoint, so Line(a, b) and Line(b, a) hold the same cells; the list is then
    /// ordered a -> b.</summary>
    public static void Line(Vector3Int a, Vector3Int b, List<Vector3Int> into)
    {
        bool swap = a.y > b.y || (a.y == b.y && a.x > b.x);
        Vector3Int p = swap ? b : a, q = swap ? a : b;
        int first = into.Count;
        int dx = Math.Abs(q.x - p.x), dy = Math.Abs(q.y - p.y);
        int sx = p.x < q.x ? 1 : -1, sy = p.y < q.y ? 1 : -1;
        int err = dx - dy, x = p.x, y = p.y;
        while (true)
        {
            into.Add(new Vector3Int(x, y, 0));
            if (x == q.x && y == q.y) break;
            int e2 = 2 * err;
            if (e2 > -dy) { err -= dy; x += sx; }
            if (e2 < dx) { err += dx; y += sy; }
        }
        if (swap) into.Reverse(first, into.Count - first);
    }

    /// <summary>Appends every cell the straight segment between the two cell centres passes
    /// through, both ends included. Where the segment crosses exactly through a corner it steps
    /// diagonally; pass <paramref name="includeCornerCells"/> to add the two cells that meet at
    /// that corner as well, which is the rule that makes a diagonal gap between two walls opaque.
    /// The cell set is the same in both directions.</summary>
    public static void Supercover(Vector3Int a, Vector3Int b, List<Vector3Int> into, bool includeCornerCells = false)
    {
        int nx = Math.Abs(b.x - a.x), ny = Math.Abs(b.y - a.y);
        int sx = b.x > a.x ? 1 : -1, sy = b.y > a.y ? 1 : -1;
        int x = a.x, y = a.y;
        into.Add(new Vector3Int(x, y, 0));
        for (int ix = 0, iy = 0; ix < nx || iy < ny;)
        {
            // Which border does the segment reach first: the next column's or the next row's?
            int decision = (1 + 2 * ix) * ny - (1 + 2 * iy) * nx;
            if (decision == 0)
            {
                if (includeCornerCells)
                {
                    into.Add(new Vector3Int(x + sx, y, 0));
                    into.Add(new Vector3Int(x, y + sy, 0));
                }
                x += sx; y += sy; ix++; iy++;
            }
            else if (decision < 0) { x += sx; ix++; }
            else { y += sy; iy++; }
            into.Add(new Vector3Int(x, y, 0));
        }
    }

    /// <summary>Appends the hexagonal line from offset cell a to offset cell b, both included:
    /// distance + 1 cells, each a neighbour of the last. A sample that lands exactly on an edge is
    /// nudged toward one fixed side, so the same pair of cells gives the same cells in either
    /// direction; <paramref name="otherSide"/> nudges the opposite way, which yields the second
    /// candidate line when a strict sight rule needs both clear.</summary>
    public static void HexLine(Vector3Int a, Vector3Int b, List<Vector3Int> into, bool oddShifted = true, bool otherSide = false)
    {
        Vector3Int ca = OffsetToCube(a, oddShifted), cb = OffsetToCube(b, oddShifted);
        int n = CubeDistance(ca, cb);
        if (n == 0) { into.Add(a); return; }
        double side = otherSide ? -1.0 : 1.0;
        double eq = 1e-6 * side, er = 2e-6 * side, es = -3e-6 * side;   // sums to 0: the point stays on the plane
        for (int i = 0; i <= n; i++)
        {
            double t = (double)i / n;
            Vector3Int c = CubeRound(ca.x + (cb.x - ca.x) * t + eq, ca.y + (cb.y - ca.y) * t + er, ca.z + (cb.z - ca.z) * t + es);
            into.Add(CubeToOffset(c, oddShifted));
        }
    }
}
