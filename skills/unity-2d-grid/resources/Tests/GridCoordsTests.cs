// GridCoordsTests.cs — EditMode tests for the board arithmetic: every conversion round-trips,
// the hexagonal distance behaves like a distance, neighbours are mutual, a known board has a
// known shortest path, an open field has a known range size, and a walled-off goal has no path.
//
// Drop it into an EditMode test assembly that references the assembly holding GridCoords.cs,
// GridPathfinder.cs, GridOccupancy.cs and TurnQueue.cs (it needs nunit and nothing else: no
// scene, no Grid, no play mode). Run it before the first sprite exists and after every change
// to a neighbour rule or a cost.
//
// A test that fails on a negative row means a conversion used `% 2` where it needs `& 1`.
using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;

public class GridCoordsTests
{
    static readonly GridShape[] Shapes = { GridShape.Rect4, GridShape.Rect8, GridShape.Hex };

    static IEnumerable<Vector3Int> Block(int min, int max)
    {
        for (int y = min; y <= max; y++)
            for (int x = min; x <= max; x++)
                yield return new Vector3Int(x, y, 0);
    }

    // ------------------------------------------------------------------ conversions

    [Test]
    public void Offset_cube_axial_round_trip_on_both_row_parities([Values(true, false)] bool oddShifted)
    {
        foreach (Vector3Int cell in Block(-6, 6))
        {
            Vector3Int cube = GridCoords.OffsetToCube(cell, oddShifted);
            Assert.AreEqual(0, cube.x + cube.y + cube.z, $"cube of {cell} is off the plane");
            Assert.AreEqual(cell.y, cube.y, "the cube r is the offset row");
            Assert.AreEqual(cell, GridCoords.CubeToOffset(cube, oddShifted), $"offset -> cube -> offset at {cell}");

            Vector2Int axial = GridCoords.OffsetToAxial(cell, oddShifted);
            Assert.AreEqual(cube, GridCoords.AxialToCube(axial), $"axial -> cube at {cell}");
            Assert.AreEqual(axial, GridCoords.CubeToAxial(cube), $"cube -> axial at {cell}");
            Assert.AreEqual(cell, GridCoords.AxialToOffset(axial, oddShifted), $"offset -> axial -> offset at {cell}");
        }
    }

    [Test]
    public void Odd_rows_sit_half_a_cell_along_x()
    {
        // Half-cell units along x for a point-top layout: 2q + r. Unity's rows with odd y are the
        // shifted ones, so (0, 1) is one half-cell right of (0, 0) and (0, -1) is too.
        int HalfCellsX(Vector3Int cell) { Vector3Int c = GridCoords.OffsetToCube(cell); return 2 * c.x + c.y; }
        Assert.AreEqual(0, HalfCellsX(new Vector3Int(0, 0, 0)));
        Assert.AreEqual(1, HalfCellsX(new Vector3Int(0, 1, 0)));
        Assert.AreEqual(1, HalfCellsX(new Vector3Int(0, -1, 0)));
        Assert.AreEqual(0, HalfCellsX(new Vector3Int(0, 2, 0)));
        Assert.AreEqual(2, HalfCellsX(new Vector3Int(1, 0, 0)));
    }

    [Test]
    public void Cube_round_returns_the_cell_it_was_given_and_stays_on_the_plane()
    {
        foreach (Vector3Int cell in Block(-4, 4))
        {
            Vector3Int cube = GridCoords.OffsetToCube(cell);
            Assert.AreEqual(cube, GridCoords.CubeRound(cube.x + 0.2, cube.y - 0.1, cube.z - 0.1));
        }
        Vector3Int r = GridCoords.CubeRound(0.5, 0.5, -1.0);
        Assert.AreEqual(0, r.x + r.y + r.z);
    }

    // ------------------------------------------------------------------ neighbours

    [Test]
    public void Neighbours_are_distinct_at_distance_one_and_mutual([ValueSource(nameof(Shapes))] GridShape shape)
    {
        int n = GridCoords.NeighbourCount(shape);
        foreach (Vector3Int cell in Block(-5, 5))
        {
            var seen = new HashSet<Vector3Int>();
            for (int i = 0; i < n; i++)
            {
                Vector3Int other = GridCoords.Neighbour(shape, cell, i);
                Assert.IsTrue(seen.Add(other), $"{shape}: direction {i} from {cell} repeats a neighbour");
                Assert.AreEqual(1, GridCoords.Distance(shape, cell, other), $"{shape}: {cell} -> {other}");
                Assert.AreEqual(cell, GridCoords.Neighbour(shape, other, GridCoords.Opposite(shape, i)),
                    $"{shape}: stepping back from {other} does not return to {cell}");
                Assert.AreEqual(i, GridCoords.DirectionTo(shape, cell, other));
            }
        }
    }

    [Test]
    public void Hex_neighbours_of_an_even_and_an_odd_row_differ()
    {
        // The table a hard-coded offset list gets wrong: NE of an even row keeps x, NE of an odd row adds 1.
        Assert.AreEqual(new Vector3Int(0, 1, 0), GridCoords.Neighbour(GridShape.Hex, new Vector3Int(0, 0, 0), 1));
        Assert.AreEqual(new Vector3Int(1, 2, 0), GridCoords.Neighbour(GridShape.Hex, new Vector3Int(0, 1, 0), 1));
        Assert.AreEqual(new Vector3Int(-1, 1, 0), GridCoords.Neighbour(GridShape.Hex, new Vector3Int(0, 0, 0), 2));
        Assert.AreEqual(new Vector3Int(0, 2, 0), GridCoords.Neighbour(GridShape.Hex, new Vector3Int(0, 1, 0), 2));
    }

    // ------------------------------------------------------------------ distances

    [Test]
    public void Hex_distance_is_a_metric()
    {
        var cells = new List<Vector3Int>(Block(-3, 3));
        foreach (Vector3Int a in cells)
        {
            Assert.AreEqual(0, GridCoords.HexDistance(a, a));
            foreach (Vector3Int b in cells)
            {
                int ab = GridCoords.HexDistance(a, b);
                Assert.AreEqual(ab, GridCoords.HexDistance(b, a), $"{a} {b} is not symmetric");
                if (a != b) Assert.Greater(ab, 0);
                Vector3Int ca = GridCoords.OffsetToCube(a), cb = GridCoords.OffsetToCube(b);
                int dq = System.Math.Abs(ca.x - cb.x), dr = System.Math.Abs(ca.y - cb.y), ds = System.Math.Abs(ca.z - cb.z);
                Assert.AreEqual(System.Math.Max(dq, System.Math.Max(dr, ds)), ab, "half the sum equals the largest component");
                foreach (Vector3Int c in cells)
                    Assert.LessOrEqual(ab, GridCoords.HexDistance(a, c) + GridCoords.HexDistance(c, b), $"triangle {a} {c} {b}");
            }
        }
    }

    [Test]
    public void Rectangular_distances_have_their_known_values()
    {
        Vector3Int a = new Vector3Int(-2, 1, 0), b = new Vector3Int(3, -3, 0);     // dx 5, dy 4
        Assert.AreEqual(9, GridCoords.Manhattan(a, b));
        Assert.AreEqual(5, GridCoords.Chebyshev(a, b));
        Assert.AreEqual(4 * 14 + 1 * 10, GridCoords.Octile(a, b));
    }

    [Test]
    public void A_ring_holds_exactly_the_cells_at_its_radius([ValueSource(nameof(Shapes))] GridShape shape, [Values(0, 1, 2, 4)] int radius)
    {
        var centre = new Vector3Int(1, -3, 0);                                     // an odd row on purpose
        var ring = new List<Vector3Int>();
        GridCoords.Ring(shape, centre, radius, ring);
        int expected = radius == 0 ? 1 : shape == GridShape.Rect4 ? 4 * radius : shape == GridShape.Rect8 ? 8 * radius : 6 * radius;
        Assert.AreEqual(expected, ring.Count);
        Assert.AreEqual(expected, new HashSet<Vector3Int>(ring).Count, "a ring cell is listed twice");
        foreach (Vector3Int cell in ring) Assert.AreEqual(radius, GridCoords.Distance(shape, centre, cell));
    }

    // ------------------------------------------------------------------ lines

    [Test]
    public void Lines_connect_their_ends_and_read_the_same_both_ways()
    {
        var forward = new List<Vector3Int>();
        var back = new List<Vector3Int>();
        foreach (Vector3Int b in Block(-4, 4))
        {
            Vector3Int a = new Vector3Int(1, -1, 0);

            forward.Clear(); back.Clear();
            GridCoords.Line(a, b, forward); GridCoords.Line(b, a, back);
            Assert.AreEqual(GridCoords.Chebyshev(a, b) + 1, forward.Count, $"Bresenham {a} -> {b}");
            Assert.AreEqual(a, forward[0]); Assert.AreEqual(b, forward[forward.Count - 1]);
            back.Reverse();
            CollectionAssert.AreEqual(forward, back, $"Bresenham {a} -> {b} differs from {b} -> {a}");

            forward.Clear(); back.Clear();
            GridCoords.Supercover(a, b, forward); GridCoords.Supercover(b, a, back);
            Assert.AreEqual(a, forward[0]); Assert.AreEqual(b, forward[forward.Count - 1]);
            CollectionAssert.AreEquivalent(forward, back, $"supercover {a} -> {b}");
            for (int i = 1; i < forward.Count; i++)
                Assert.AreEqual(1, GridCoords.Chebyshev(forward[i - 1], forward[i]), "supercover skipped a cell");

            forward.Clear(); back.Clear();
            GridCoords.HexLine(a, b, forward); GridCoords.HexLine(b, a, back);
            back.Reverse();
            CollectionAssert.AreEqual(forward, back, $"hex line {a} -> {b} differs from {b} -> {a}");
            Assert.AreEqual(GridCoords.HexDistance(a, b) + 1, forward.Count, $"hex line {a} -> {b}");
            Assert.AreEqual(a, forward[0]); Assert.AreEqual(b, forward[forward.Count - 1]);
            for (int i = 1; i < forward.Count; i++)
                Assert.AreEqual(1, GridCoords.HexDistance(forward[i - 1], forward[i]), "hex line skipped a cell");
        }
    }

    [Test]
    public void A_supercover_line_through_a_corner_can_report_both_corner_cells()
    {
        var cells = new List<Vector3Int>();
        GridCoords.Supercover(new Vector3Int(0, 0, 0), new Vector3Int(2, 2, 0), cells, includeCornerCells: true);
        CollectionAssert.Contains(cells, new Vector3Int(1, 0, 0));
        CollectionAssert.Contains(cells, new Vector3Int(0, 1, 0));
        Assert.AreEqual(7, cells.Count);                                           // 3 on the diagonal + 2 per corner
    }

    // ------------------------------------------------------------------ paths and ranges

    static GridPathfinder.EnterCost Open => (from, to) => 1;

    static GridPathfinder.EnterCost Avoiding(HashSet<Vector3Int> walls) => (from, to) => walls.Contains(to) ? 0 : 1;

    [Test]
    public void An_open_field_range_has_the_closed_form_size([Values(1, 2, 3)] int radius)
    {
        // 4 neighbours: 2r^2 + 2r + 1 · 8 neighbours at one step a diagonal: (2r + 1)^2 · hexagons: 3r^2 + 3r + 1
        var reached = new List<Vector3Int>();
        var centre = new Vector3Int(10, 11, 0);                                    // an odd row, far from every edge

        var rect4 = new GridPathfinder(Vector3Int.zero, 21, 23, GridShape.Rect4);
        Assert.AreEqual(2 * radius * radius + 2 * radius + 1, rect4.Range(centre, radius, Open, reached));

        var rect8 = new GridPathfinder(Vector3Int.zero, 21, 23, GridShape.Rect8) { DiagonalWeight = 10 };
        Assert.AreEqual((2 * radius + 1) * (2 * radius + 1), rect8.Range(centre, radius, Open, reached));

        var hex = new GridPathfinder(Vector3Int.zero, 21, 23, GridShape.Hex);
        Assert.AreEqual(3 * radius * radius + 3 * radius + 1, hex.Range(centre, radius, Open, reached));
        foreach (Vector3Int cell in reached)
            Assert.AreEqual(GridCoords.HexDistance(centre, cell) * GridPathfinder.Straight, hex.CostTo(cell));
    }

    [Test]
    public void A_range_stops_at_walls_and_prices_slow_ground()
    {
        // A corridor one cell high: the wall at x = 3 ends the flood although x = 4 is within distance.
        var finder = new GridPathfinder(Vector3Int.zero, 9, 1, GridShape.Rect4);
        var walls = new HashSet<Vector3Int> { new Vector3Int(3, 0, 0) };
        var reached = new List<Vector3Int>();
        Assert.AreEqual(3, finder.Range(Vector3Int.zero, 6, Avoiding(walls), reached));
        Assert.AreEqual(-1, finder.CostTo(new Vector3Int(4, 0, 0)));

        // Slow ground at x = 1 costs 2: four move points reach x = 3, not x = 4.
        GridPathfinder.EnterCost slow = (from, to) => to.x == 1 ? 2 : 1;
        Assert.AreEqual(4, finder.Range(Vector3Int.zero, 4, slow, reached));
        Assert.AreEqual(40, finder.CostTo(new Vector3Int(3, 0, 0)));

        var path = new List<Vector3Int>();
        Assert.IsTrue(finder.PathFromRange(new Vector3Int(3, 0, 0), path));
        Assert.AreEqual(4, path.Count);
        Assert.IsFalse(finder.PathFromRange(new Vector3Int(8, 0, 0), path));
    }

    [Test]
    public void A_known_board_has_a_known_shortest_path()
    {
        // 7 × 5, a wall down x = 3 with one gap at the top row. From (1, 0) to (5, 0):
        //   y4  . . . . . . .      the only way round is up to y = 4 and back down,
        //   y3  . . . # . . .      4 across + 4 up + 4 down = 12 steps, 13 cells.
        //   y2  . . . # . . .
        //   y1  . . . # . . .
        //   y0  . S . # . G .
        var walls = new HashSet<Vector3Int>();
        for (int y = 0; y <= 3; y++) walls.Add(new Vector3Int(3, y, 0));
        var finder = new GridPathfinder(Vector3Int.zero, 7, 5, GridShape.Rect4);
        var path = new List<Vector3Int>();
        Vector3Int start = new Vector3Int(1, 0, 0), goal = new Vector3Int(5, 0, 0);

        Assert.IsTrue(finder.FindPath(start, goal, Avoiding(walls), path));
        Assert.AreEqual(13, path.Count);
        Assert.AreEqual(120, finder.PathCost);
        Assert.AreEqual(start, path[0]);
        Assert.AreEqual(goal, path[path.Count - 1]);
        for (int i = 1; i < path.Count; i++)
        {
            Assert.AreEqual(1, GridCoords.Manhattan(path[i - 1], path[i]), "the path skipped a cell");
            Assert.IsFalse(walls.Contains(path[i]), "the path crosses a wall");
        }

        var again = new List<Vector3Int>();
        finder.FindPath(start, goal, Avoiding(walls), again);
        CollectionAssert.AreEqual(path, again, "the same board gave two different paths");
    }

    [Test]
    public void A_star_agrees_with_the_flood_on_every_shape([ValueSource(nameof(Shapes))] GridShape shape)
    {
        // A* with a wrong heuristic still returns a path, only not the shortest. Dijkstra has no
        // heuristic to get wrong, so its costs are the reference.
        var walls = new HashSet<Vector3Int>();
        for (int y = 1; y <= 7; y++) walls.Add(new Vector3Int(4, y, 0));
        for (int x = 6; x <= 9; x++) walls.Add(new Vector3Int(x, 5, 0));
        var finder = new GridPathfinder(new Vector3Int(-2, -3, 0), 12, 11, shape);
        var flood = new GridPathfinder(new Vector3Int(-2, -3, 0), 12, 11, shape);
        GridPathfinder.EnterCost cost = (from, to) => walls.Contains(to) ? 0 : (to.x + to.y) % 3 == 0 ? 2 : 1;
        var reached = new List<Vector3Int>();
        var path = new List<Vector3Int>();
        var start = new Vector3Int(0, 3, 0);

        flood.Range(start, 1000, cost, reached);
        Assert.Greater(reached.Count, 80);
        foreach (Vector3Int goal in reached)
        {
            Assert.IsTrue(finder.FindPath(start, goal, cost, path), $"{shape}: no path to {goal}");
            Assert.AreEqual(flood.CostTo(goal), finder.PathCost, $"{shape}: A* cost to {goal}");
        }
    }

    [Test]
    public void A_diagonal_does_not_cut_a_corner_unless_asked()
    {
        // . G        The wall is at (1, 0). Stepping (0, 0) -> (1, 1) squeezes past its corner.
        // S #
        var walls = new HashSet<Vector3Int> { new Vector3Int(1, 0, 0) };
        var finder = new GridPathfinder(Vector3Int.zero, 2, 2, GridShape.Rect8);
        var path = new List<Vector3Int>();

        Assert.IsTrue(finder.FindPath(Vector3Int.zero, new Vector3Int(1, 1, 0), Avoiding(walls), path));
        Assert.AreEqual(3, path.Count, "the path went round the corner");
        Assert.AreEqual(20, finder.PathCost);

        finder.CutCorners = true;
        Assert.IsTrue(finder.FindPath(Vector3Int.zero, new Vector3Int(1, 1, 0), Avoiding(walls), path));
        Assert.AreEqual(2, path.Count);
        Assert.AreEqual(14, finder.PathCost);
    }

    [Test]
    public void An_unreachable_goal_returns_no_path([ValueSource(nameof(Shapes))] GridShape shape)
    {
        // The goal is sealed inside a ring of walls two cells thick, so no neighbour rule leaks in.
        var goal = new Vector3Int(8, 8, 0);
        var walls = new HashSet<Vector3Int>();
        foreach (Vector3Int cell in Block(5, 11))
            if (GridCoords.Chebyshev(cell, goal) >= 1 && GridCoords.Chebyshev(cell, goal) <= 2) walls.Add(cell);
        var finder = new GridPathfinder(Vector3Int.zero, 16, 16, shape);
        var path = new List<Vector3Int> { Vector3Int.one };

        Assert.IsFalse(finder.FindPath(Vector3Int.zero, goal, Avoiding(walls), path));
        Assert.AreEqual(0, path.Count, "a failed search must leave the list empty");
        Assert.IsFalse(finder.FindPath(Vector3Int.zero, new Vector3Int(99, 0, 0), Open, path), "a goal off the board");
        Assert.IsTrue(finder.FindPath(goal, goal, Avoiding(walls), path));
        Assert.AreEqual(1, path.Count);
    }

    // ------------------------------------------------------------------ occupancy and turns

    [Test]
    public void A_push_moves_one_pickup_one_cell_and_reverts_exactly()
    {
        const int runner = 1, pickupA = 2, pickupB = 3;
        var yard = new GridOccupancy();
        yard.AddWall(new Vector3Int(5, 0, 0));
        yard.Place(runner, new Vector3Int(0, 0, 0));
        yard.Place(pickupA, new Vector3Int(1, 0, 0), pushable: true);
        yard.Place(pickupB, new Vector3Int(4, 0, 0), pushable: true);
        var undo = new Stack<StepRecord>();

        StepRecord Step()
        {
            Vector3Int to = GridCoords.Neighbour(GridShape.Rect4, yard.CellOf(runner), 0);
            StepRecord s = yard.StepOrPush(runner, to, GridCoords.Neighbour(GridShape.Rect4, to, 0));
            if (s.Result != StepResult.Blocked) undo.Push(s);
            return s;
        }

        Assert.AreEqual(StepResult.Pushed, Step().Result);                         // A to x = 2
        Assert.AreEqual(StepResult.Pushed, Step().Result);                         // A to x = 3
        Assert.AreEqual(StepResult.Blocked, Step().Result, "two pickups in a row do not move");
        Assert.AreEqual(new Vector3Int(2, 0, 0), yard.CellOf(runner));
        Assert.AreEqual(pickupA, yard.OccupantAt(new Vector3Int(3, 0, 0)));

        while (undo.Count > 0) yard.Revert(undo.Pop());
        Assert.AreEqual(new Vector3Int(0, 0, 0), yard.CellOf(runner));
        Assert.AreEqual(new Vector3Int(1, 0, 0), yard.CellOf(pickupA));
        Assert.AreEqual(GridOccupancy.Nobody, yard.OccupantAt(new Vector3Int(2, 0, 0)));
        Assert.AreEqual(3, yard.Count);
    }

    [Test]
    public void Reservations_resolve_together_and_never_swap()
    {
        var yard = new GridOccupancy();
        yard.Place(1, new Vector3Int(0, 0, 0));
        yard.Place(2, new Vector3Int(1, 0, 0));
        yard.Place(3, new Vector3Int(2, 0, 0));

        Assert.IsFalse(yard.TryReserve(1, new Vector3Int(1, 0, 0)), "the holder has not claimed a move away");
        Assert.IsTrue(yard.TryReserve(3, new Vector3Int(3, 0, 0)));
        Assert.IsTrue(yard.TryReserve(2, new Vector3Int(2, 0, 0)), "a cell being vacated can be claimed");
        Assert.IsTrue(yard.TryReserve(1, new Vector3Int(1, 0, 0)));
        Assert.IsFalse(yard.CanEnter(new Vector3Int(3, 0, 0)), "a claimed cell is not enterable");
        Assert.AreEqual(3, yard.Commit());
        Assert.AreEqual(1, yard.OccupantAt(new Vector3Int(1, 0, 0)));
        Assert.AreEqual(3, yard.OccupantAt(new Vector3Int(3, 0, 0)));
        Assert.AreEqual(GridOccupancy.Nobody, yard.OccupantAt(new Vector3Int(0, 0, 0)));

        // 1 at x = 1, 2 at x = 2. A swap needs each to claim the other's cell, and whichever
        // asks first is refused because the holder has not claimed a move away.
        Assert.IsFalse(yard.TryReserve(1, new Vector3Int(2, 0, 0)));
        Assert.IsFalse(yard.TryReserve(2, new Vector3Int(1, 0, 0)));
        Assert.IsTrue(yard.TryReserve(1, new Vector3Int(0, 0, 0)));
        yard.ClearReservations();
        Assert.AreEqual(0, yard.Commit());
    }

    [Test]
    public void The_turn_order_is_by_initiative_then_id_and_survives_a_removal()
    {
        var turns = new TurnQueue();
        turns.Add(30, 9); turns.Add(10, 12); turns.Add(20, 9); turns.Add(40, 3);
        Assert.AreEqual(10, turns.Begin());
        Assert.AreEqual(1, turns.Round);
        Assert.AreEqual(20, turns.Advance(), "equal initiative goes to the lower id");
        Assert.AreEqual(30, turns.Peek(1));

        turns.Remove(10);                                                          // already acted
        Assert.AreEqual(20, turns.Current, "removing an earlier actor must not change whose turn it is");
        turns.Add(50, 99);                                                         // joins next round
        Assert.AreEqual(30, turns.Advance());
        turns.Remove(30);                                                          // the one acting
        Assert.AreEqual(40, turns.Advance());
        Assert.AreEqual(1, turns.Round);
        Assert.AreEqual(50, turns.Advance(), "the newcomer leads round 2");
        Assert.AreEqual(2, turns.Round);
        Assert.AreEqual(20, turns.Advance());
        Assert.AreEqual(40, turns.Advance());
        Assert.AreEqual(50, turns.Advance());
        Assert.AreEqual(3, turns.Round);
    }
}
