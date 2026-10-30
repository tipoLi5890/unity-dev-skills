# Build the board before the scene — the rules as one class, tested before any sprite

The board is plain C#: it owns the cells, answers every rule at once, and returns what changed for
a presenter to animate. Undo is a stack of those records.


1. **Copy the four resources** into the assembly that holds the rules, and
   `resources/Tests/GridCoordsTests.cs` into an EditMode test assembly. Run the tests; they need
   no scene.
2. **Write the board as one class** that owns a `GridOccupancy` (and a `TurnQueue` for tactics)
   and exposes commands that return what changed:

```csharp
// YardBoard — the sorting yard's rules. Plain C#; the scene is not involved.
public sealed class YardBoard
{
    public const int RunnerId = 1;
    public readonly GridOccupancy Cells = new GridOccupancy();
    public readonly HashSet<Vector3Int> Gates = new HashSet<Vector3Int>();
    public readonly GridShape Shape;
    readonly Stack<StepRecord> _undo = new Stack<StepRecord>();

    public YardBoard(GridShape shape) { Shape = shape; }

    public StepRecord Step(int direction)                     // 0 .. NeighbourCount - 1
    {
        Vector3Int to = GridCoords.Neighbour(Shape, Cells.CellOf(RunnerId), direction);
        Vector3Int beyond = GridCoords.Neighbour(Shape, to, direction);
        StepRecord step = Cells.StepOrPush(RunnerId, to, beyond);
        if (step.Result != StepResult.Blocked) _undo.Push(step);
        return step;                                          // the presenter animates exactly this
    }

    public bool Undo(out StepRecord undone)
    {
        undone = default;
        if (_undo.Count == 0) return false;
        undone = _undo.Pop();
        Cells.Revert(undone);
        return true;
    }

    public int PickupsOnGates { get { int n = 0; foreach (Vector3Int g in Gates) if (Cells.IsPushable(Cells.OccupantAt(g))) n++; return n; } }
    public bool Solved => PickupsOnGates == Gates.Count;
}
```

3. **Test the rules in EditMode**: a step into a wall changes nothing; a push moves one pickup one
   cell; two pickups in a row do not move; undo after N steps restores the first board exactly.
4. **Then the scene.** One `Grid`; load the board and the Tilemaps from one source —
   `unity-2d-level` → `reference/level-data.md`. The presenter turns each `StepRecord` into
   tweens toward `Grid.GetCellCenterWorld(cell)`. The mover in `unity-2d-controller` →
   `reference/grid-step.md` speaks `Vector2Int` and asks through delegates, so adapt at the edge:
   `mover.CanEnter = (from, to) => board.Cells.CanEnter(new Vector3Int(to.x, to.y, 0));`
5. **Expose the logical state, not the transform**, to the probe:
   `GameProbe.Register("cell", () => $"{c.x},{c.y}")`, `GameProbe.Count("pickupsOnGates", …)`,
   `GameProbe.Register("turn", …)`. A journey then asserts that the transform sits at the centre
   of the cell the probe reports whenever no tween is running, and that a blocked step changed
   neither.
