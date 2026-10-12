// GridOccupancy.cs — the one map from cell to occupant: walls, pieces, reservations for moves
// that resolve together, and the sorting yard's step-or-push with a record that undoes it.
// Pure C#, no scene.
//
// Drop it beside GridCoords.cs in the assembly that holds the rules. Every rule that asks "what
// is in that cell" asks this object; nothing asks a collider or a transform. An occupant is an
// int id the game hands out (1 and up; 0 means "nobody"), so the map holds no reference to a
// GameObject and a board can be copied, searched and tested with no scene.
//
//   var yard = new GridOccupancy();
//   yard.AddWall(new Vector3Int(4, 0, 0));
//   yard.Place(RunnerId, new Vector3Int(1, 0, 0));
//   yard.Place(PickupId, new Vector3Int(2, 0, 0), pushable: true);
//   Vector3Int to = GridCoords.Neighbour(shape, yard.CellOf(RunnerId), direction);
//   Vector3Int beyond = GridCoords.Neighbour(shape, to, direction);
//   StepRecord step = yard.StepOrPush(RunnerId, to, beyond);     // step.Result: Blocked, Moved, Pushed
//   if (step.Result != StepResult.Blocked) undo.Push(step);
//   yard.Revert(undo.Pop());                                     // exactly the board before the step
using System;
using System.Collections.Generic;
using UnityEngine;

public enum StepResult { Blocked, Moved, Pushed }

/// <summary>Everything one step changed, which is everything needed to take it back.</summary>
public readonly struct StepRecord
{
    public readonly StepResult Result;
    public readonly int Mover, Pushed;
    public readonly Vector3Int From, To, Beyond;

    public StepRecord(StepResult result, int mover, Vector3Int from, Vector3Int to, int pushed, Vector3Int beyond)
    {
        Result = result; Mover = mover; From = from; To = to; Pushed = pushed; Beyond = beyond;
    }
}

public sealed class GridOccupancy
{
    public const int Nobody = 0;

    readonly HashSet<Vector3Int> _walls = new HashSet<Vector3Int>();
    readonly Dictionary<Vector3Int, int> _at = new Dictionary<Vector3Int, int>();
    readonly Dictionary<int, Vector3Int> _cellOf = new Dictionary<int, Vector3Int>();
    readonly HashSet<int> _pushable = new HashSet<int>();
    readonly Dictionary<int, Vector3Int> _reservedBy = new Dictionary<int, Vector3Int>();
    readonly Dictionary<Vector3Int, int> _reservedAt = new Dictionary<Vector3Int, int>();
    readonly List<int> _commitOrder = new List<int>();

    public int Count => _cellOf.Count;

    // ------------------------------------------------------------------ walls

    public void AddWall(Vector3Int cell) => _walls.Add(cell);
    public void RemoveWall(Vector3Int cell) => _walls.Remove(cell);
    public bool IsWall(Vector3Int cell) => _walls.Contains(cell);

    // ------------------------------------------------------------------ occupants

    /// <summary>Puts a new occupant on the board. Throws when the id is 0 or in use, or the cell
    /// is a wall or taken: a level that places two pieces on one cell is a data fault to fix, not
    /// a state to play from.</summary>
    public void Place(int id, Vector3Int cell, bool pushable = false)
    {
        if (id == Nobody) throw new ArgumentException("GridOccupancy.Place: id 0 means nobody.");
        if (_cellOf.ContainsKey(id)) throw new InvalidOperationException($"GridOccupancy.Place: id {id} is already on the board.");
        if (!IsFree(cell)) throw new InvalidOperationException($"GridOccupancy.Place: cell {cell} is not free for id {id}.");
        _at[cell] = id; _cellOf[id] = cell;
        if (pushable) _pushable.Add(id);
    }

    /// <summary>Takes an occupant off the board. Returns false when it was not there.</summary>
    public bool Remove(int id)
    {
        if (!_cellOf.TryGetValue(id, out Vector3Int cell)) return false;
        _at.Remove(cell); _cellOf.Remove(id); _pushable.Remove(id);
        if (_reservedBy.TryGetValue(id, out Vector3Int reserved)) { _reservedBy.Remove(id); _reservedAt.Remove(reserved); _commitOrder.Remove(id); }
        return true;
    }

    /// <summary>The occupant of a cell, or 0.</summary>
    public int OccupantAt(Vector3Int cell) => _at.TryGetValue(cell, out int id) ? id : Nobody;

    public bool Has(int id) => _cellOf.ContainsKey(id);

    /// <summary>The cell an occupant is in. Throws for an id that is not on the board.</summary>
    public Vector3Int CellOf(int id) => _cellOf[id];

    public bool TryGetCell(int id, out Vector3Int cell) => _cellOf.TryGetValue(id, out cell);

    public bool IsPushable(int id) => _pushable.Contains(id);

    /// <summary>No wall and no occupant.</summary>
    public bool IsFree(Vector3Int cell) => !_walls.Contains(cell) && !_at.ContainsKey(cell);

    /// <summary>No wall, no occupant and no reservation: the "can enter" a mover or a path search
    /// asks. The method group converts to a Func of Vector3Int to bool.</summary>
    public bool CanEnter(Vector3Int cell) => IsFree(cell) && !_reservedAt.ContainsKey(cell);

    /// <summary>Moves an occupant to a free cell. The board changes in this call; a tween that
    /// takes 0.12 s to show it does not own the origin cell for those 0.12 s.</summary>
    public bool TryMove(int id, Vector3Int to)
    {
        if (!_cellOf.TryGetValue(id, out Vector3Int from) || !CanEnter(to)) return false;
        _at.Remove(from); _at[to] = id; _cellOf[id] = to;
        return true;
    }

    // ------------------------------------------------------------------ step or push

    /// <summary>One step of <paramref name="mover"/> into the adjacent <paramref name="to"/>. When
    /// a pushable occupant stands there it moves on to <paramref name="beyond"/>, which must be
    /// free: one pickup, one cell, never into a wall or another piece. The caller supplies both
    /// cells from the same direction index, so the rule is identical on every grid shape. A
    /// Blocked record means nothing changed.</summary>
    public StepRecord StepOrPush(int mover, Vector3Int to, Vector3Int beyond)
    {
        Vector3Int from = _cellOf[mover];
        if (_walls.Contains(to)) return new StepRecord(StepResult.Blocked, mover, from, to, Nobody, beyond);

        int other = OccupantAt(to);
        if (other == Nobody)
        {
            if (!TryMove(mover, to)) return new StepRecord(StepResult.Blocked, mover, from, to, Nobody, beyond);
            return new StepRecord(StepResult.Moved, mover, from, to, Nobody, beyond);
        }
        if (!_pushable.Contains(other) || !CanEnter(beyond))
            return new StepRecord(StepResult.Blocked, mover, from, to, Nobody, beyond);

        _at.Remove(to); _at[beyond] = other; _cellOf[other] = beyond;
        _at.Remove(from); _at[to] = mover; _cellOf[mover] = to;
        return new StepRecord(StepResult.Pushed, mover, from, to, other, beyond);
    }

    /// <summary>Takes one step back. Records must be reverted newest first.</summary>
    public void Revert(StepRecord step)
    {
        if (step.Result == StepResult.Blocked) return;
        _at.Remove(step.To); _at[step.From] = step.Mover; _cellOf[step.Mover] = step.From;
        if (step.Result == StepResult.Pushed)
        {
            _at.Remove(step.Beyond); _at[step.To] = step.Pushed; _cellOf[step.Pushed] = step.To;
        }
    }

    // ------------------------------------------------------------------ reserve, then move

    /// <summary>Claims <paramref name="to"/> for a move that resolves with others in Commit. Ask in
    /// initiative order: the first claim on a cell wins. Refused when the cell is a wall, already
    /// claimed, or held by an occupant that has not already claimed a move away. Two occupants can
    /// therefore never swap through each other: whichever asks first is refused.</summary>
    public bool TryReserve(int id, Vector3Int to)
    {
        if (!_cellOf.ContainsKey(id)) return false;
        if (_reservedBy.ContainsKey(id) || _walls.Contains(to) || _reservedAt.ContainsKey(to)) return false;
        int holder = OccupantAt(to);
        if (holder != Nobody && !_reservedBy.ContainsKey(holder)) return false;
        _reservedBy[id] = to; _reservedAt[to] = id; _commitOrder.Add(id);
        return true;
    }

    public bool HasReservation(int id) => _reservedBy.ContainsKey(id);

    /// <summary>Applies every reservation at once and clears them. Returns how many occupants moved.</summary>
    public int Commit()
    {
        // Lift every mover first, then set them down: in a chain, the cell a follower lands on is
        // still held by the one ahead until that one has moved.
        for (int i = 0; i < _commitOrder.Count; i++) _at.Remove(_cellOf[_commitOrder[i]]);
        for (int i = 0; i < _commitOrder.Count; i++)
        {
            int id = _commitOrder[i];
            Vector3Int to = _reservedBy[id];
            _at[to] = id; _cellOf[id] = to;
        }
        int moved = _commitOrder.Count;
        ClearReservations();
        return moved;
    }

    /// <summary>Drops every reservation, moving nobody. There is no cancelling one alone: a later
    /// claim may have been granted because of it.</summary>
    public void ClearReservations()
    {
        _reservedBy.Clear(); _reservedAt.Clear(); _commitOrder.Clear();
    }

    /// <summary>Removes every wall, occupant and reservation.</summary>
    public void Clear()
    {
        _walls.Clear(); _at.Clear(); _cellOf.Clear(); _pushable.Clear();
        ClearReservations();
    }
}
