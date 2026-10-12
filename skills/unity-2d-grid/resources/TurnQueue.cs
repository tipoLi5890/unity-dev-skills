// TurnQueue.cs — whose turn it is: actors ordered by initiative, an index that advances, a round
// counter. Pure C#, no engine type at all; it compiles in an assembly with noEngineReferences.
//
// Drop it in the assembly that holds the rules. Actors are int ids, the same ids GridOccupancy
// holds. Order is initiative, highest first; equal initiative goes to the lower id, so the same
// roster always gives the same order and a journey can assert it.
//
//   var turns = new TurnQueue();
//   turns.Add(RunnerId, 12); turns.Add(SentryA, 9); turns.Add(SentryB, 9);
//   turns.Begin();                       // round 1, Current == RunnerId
//   int next = turns.Advance();          // SentryA; after the last actor, round 2 starts
//   turns.Remove(SentryB);               // gone at once; nobody's turn is skipped
using System;
using System.Collections.Generic;

public sealed class TurnQueue
{
    struct Entry { public int Id, Initiative; }

    readonly List<Entry> _order = new List<Entry>();
    readonly List<Entry> _joining = new List<Entry>();
    int _index = -1;
    bool _dirty;

    /// <summary>0 before Begin, then 1 and up.</summary>
    public int Round { get; private set; }

    /// <summary>Actors in this round's order. One added during the round is counted from the next.</summary>
    public int Count => _order.Count;

    /// <summary>Position of the acting actor inside the round, 0-based; -1 before Begin.</summary>
    public int Index => _index;

    /// <summary>The actor whose turn it is, or 0 before Begin or when the queue is empty.</summary>
    public int Current => _index >= 0 && _index < _order.Count ? _order[_index].Id : 0;

    /// <summary>Raised when a new round starts, with the round number, before its first turn.</summary>
    public event Action<int> RoundStarted;

    /// <summary>Adds an actor. Before Begin it is sorted in; during a round it acts from the next
    /// round on, so a reinforcement never takes a turn in the middle of someone else's.</summary>
    public void Add(int id, int initiative)
    {
        if (id == 0) throw new ArgumentException("TurnQueue.Add: id 0 means nobody.");
        if (Contains(id)) throw new InvalidOperationException($"TurnQueue.Add: id {id} is already queued.");
        var entry = new Entry { Id = id, Initiative = initiative };
        if (Round == 0) { _order.Add(entry); Sort(); }
        else { _joining.Add(entry); _dirty = true; }
    }

    /// <summary>Removes an actor at once. When it had already acted this round, or is the one
    /// acting, the index steps back so the next Advance lands on the right actor.</summary>
    public bool Remove(int id)
    {
        for (int i = 0; i < _joining.Count; i++)
            if (_joining[i].Id == id) { _joining.RemoveAt(i); return true; }
        int at = IndexOf(id);
        if (at < 0) return false;
        _order.RemoveAt(at);
        if (_index >= 0 && at <= _index) _index--;
        return true;
    }

    /// <summary>Changes an actor's initiative from the next round on.</summary>
    public bool SetInitiative(int id, int initiative)
    {
        for (int i = 0; i < _joining.Count; i++)
            if (_joining[i].Id == id) { Entry j = _joining[i]; j.Initiative = initiative; _joining[i] = j; return true; }
        int at = IndexOf(id);
        if (at < 0) return false;
        Entry e = _order[at]; e.Initiative = initiative; _order[at] = e;
        _dirty = true;
        return true;
    }

    public bool Contains(int id)
    {
        for (int i = 0; i < _joining.Count; i++) if (_joining[i].Id == id) return true;
        return IndexOf(id) >= 0;
    }

    /// <summary>Starts round 1 and returns the first actor, or 0 when nobody is queued.</summary>
    public int Begin()
    {
        Round = 0; _index = -1;
        return Advance();
    }

    /// <summary>Ends the current turn and returns the next actor. Past the last actor a new round
    /// starts: the order is sorted again if anything changed, and RoundStarted is raised.</summary>
    public int Advance()
    {
        if (_order.Count + _joining.Count == 0) { _index = -1; return 0; }
        _index++;
        if (Round == 0 || _index >= _order.Count)
        {
            for (int i = 0; i < _joining.Count; i++) _order.Add(_joining[i]);
            _joining.Clear();
            if (_dirty) Sort();
            _index = 0;
            Round++;
            RoundStarted?.Invoke(Round);
        }
        return _order[_index].Id;
    }

    /// <summary>The actor <paramref name="ahead"/> turns from now in this round's order, wrapping
    /// into the next round; for a turn-order strip in the HUD. 0 is the current actor.</summary>
    public int Peek(int ahead)
    {
        if (_order.Count == 0 || _index < 0 || ahead < 0) return 0;
        return _order[(_index + ahead) % _order.Count].Id;
    }

    int IndexOf(int id)
    {
        for (int i = 0; i < _order.Count; i++) if (_order[i].Id == id) return i;
        return -1;
    }

    void Sort()
    {
        // Insertion sort: a roster is a few dozen entries, and it must not allocate or reorder ties.
        for (int i = 1; i < _order.Count; i++)
        {
            Entry e = _order[i];
            int j = i - 1;
            while (j >= 0 && Before(e, _order[j])) { _order[j + 1] = _order[j]; j--; }
            _order[j + 1] = e;
        }
        _dirty = false;
    }

    static bool Before(Entry a, Entry b) => a.Initiative != b.Initiative ? a.Initiative > b.Initiative : a.Id < b.Id;
}
