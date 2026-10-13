// StateMachine — states as objects, transitions as data, and two clocks: Tick runs the current
// state every simulation step, Decide evaluates transitions on a slower decision tick.
//
// Drop into a Runtime assembly. Plain C#: no MonoBehaviour, no scene, no package, so a state
// graph is testable in an edit-mode test with a fake context. SentryBrain.cs is the worked
// use; the same file drives a hazard, a gate or a boss phase.
//
//   var machine = new StateMachine<SentryBrain>(this);
//   machine.Add("Patrol", new PatrolState());
//   machine.Add("Chase", new ChaseState());
//   machine.AddTransition("Patrol", "Chase", c => c.Board.alert >= 1f);
//   machine.Start("Patrol");
//
//   void FixedUpdate()
//   {
//       if (_clock.Due(Time.fixedDeltaTime)) machine.Decide();     // 10 Hz: may change state
//       machine.Tick(Time.fixedDeltaTime);                         // every step: never changes state
//   }
//
// Register the state with the probe where the game wires its harness:
//   GameProbe.Register("sentry", () => machine.Current);
using System;
using System.Collections.Generic;

/// <summary>One state. It owns what happens while it is current, and nothing about when it ends.</summary>
public interface IState<TContext>
{
    void Enter(TContext context);
    /// <summary>Every simulation step while current. Cheap work only: timers, arrival, a re-path interval.</summary>
    void Tick(TContext context, float dt);
    void Exit(TContext context);
}

/// <summary>A state made of delegates, for one that is too small to deserve a class.</summary>
public sealed class DelegateState<TContext> : IState<TContext>
{
    readonly Action<TContext> _enter, _exit;
    readonly Action<TContext, float> _tick;

    public DelegateState(Action<TContext> enter = null, Action<TContext, float> tick = null, Action<TContext> exit = null)
    {
        _enter = enter; _tick = tick; _exit = exit;
    }

    public void Enter(TContext context) => _enter?.Invoke(context);
    public void Tick(TContext context, float dt) => _tick?.Invoke(context, dt);
    public void Exit(TContext context) => _exit?.Invoke(context);
}

/// <summary>
/// Fires once per interval of accumulated time. The phase spreads agents created together across
/// the interval, so twenty sentries do not all decide on the same step.
/// </summary>
public sealed class DecisionClock
{
    public float Interval;
    float _elapsed;

    /// <param name="phase">0..1: how far into its first interval this clock starts.</param>
    public DecisionClock(float interval, float phase = 0f)
    {
        Interval = interval;
        _elapsed = interval * Math.Max(0f, Math.Min(1f, phase));
    }

    public bool Due(float dt)
    {
        _elapsed += dt;
        if (_elapsed < Interval - 1e-5f) return false;
        // Keep the remainder, so a 0.1 s interval on a 0.02 s step fires every fifth step exactly;
        // but never owe more than one decision after a stall.
        _elapsed = Interval > 0f ? Math.Min(_elapsed - Interval, Interval) : 0f;
        return true;
    }
}

public sealed class StateMachine<TContext>
{
    struct Transition
    {
        public int From;          // AnyState for a transition out of every state
        public int To;
        public Func<TContext, bool> When;
        public float MinTime;     // seconds the source state must have been current
    }

    const int AnyState = -1;

    readonly TContext _context;
    readonly List<string> _names = new List<string>();
    readonly List<IState<TContext>> _states = new List<IState<TContext>>();
    readonly List<Transition> _transitions = new List<Transition>();
    int _current = -1;
    int _previous = -1;

    public StateMachine(TContext context) { _context = context; }

    /// <summary>Name of the current state, or null before Start. This is the string a probe exposes.</summary>
    public string Current => _current >= 0 ? _names[_current] : null;
    public string Previous => _previous >= 0 ? _names[_previous] : null;
    /// <summary>Seconds of Tick time since the current state was entered.</summary>
    public float TimeInState { get; private set; }
    /// <summary>How many times the state has changed. A number that climbs every decision is a flapping transition.</summary>
    public int Changes { get; private set; }

    /// <summary>(from, to), raised after Exit and Enter have both run.</summary>
    public event Action<string, string> Changed;

    public void Add(string name, IState<TContext> state)
    {
        if (string.IsNullOrEmpty(name)) throw new ArgumentException("a state needs a name", nameof(name));
        if (state == null) throw new ArgumentNullException(nameof(state));
        if (_names.Contains(name)) throw new ArgumentException("state '" + name + "' is already added", nameof(name));
        _names.Add(name);
        _states.Add(state);
    }

    /// <summary>
    /// A transition, evaluated by Decide in the order added: the first whose condition holds wins,
    /// so order is priority. <paramref name="minTimeInFrom"/> is a dwell time — the condition is
    /// not even asked until the source state has been current that long.
    /// </summary>
    public void AddTransition(string from, string to, Func<TContext, bool> when, float minTimeInFrom = 0f)
    {
        if (when == null) throw new ArgumentNullException(nameof(when));
        _transitions.Add(new Transition { From = IndexOf(from), To = IndexOf(to), When = when, MinTime = minTimeInFrom });
    }

    /// <summary>A transition out of every state except its own target — "stunned", "dead", "the run ended".</summary>
    public void AddAnyTransition(string to, Func<TContext, bool> when)
    {
        if (when == null) throw new ArgumentNullException(nameof(when));
        _transitions.Add(new Transition { From = AnyState, To = IndexOf(to), When = when });
    }

    public void Start(string name)
    {
        _current = IndexOf(name);
        _previous = -1;
        TimeInState = 0f;
        _states[_current].Enter(_context);
    }

    /// <summary>Run the current state for one step. Never changes state.</summary>
    public void Tick(float dt)
    {
        if (_current < 0) return;
        TimeInState += dt;
        _states[_current].Tick(_context, dt);
    }

    /// <summary>
    /// Evaluate transitions once. At most one fires per call, so a state entered on this decision
    /// is current for at least one whole decision interval — the floor under every flicker.
    /// </summary>
    public bool Decide()
    {
        if (_current < 0) return false;
        for (int i = 0; i < _transitions.Count; i++)
        {
            Transition t = _transitions[i];
            if (t.From != _current && t.From != AnyState) continue;
            if (t.To == _current) continue;
            if (TimeInState < t.MinTime) continue;
            if (!t.When(_context)) continue;
            Change(t.To);
            return true;
        }
        return false;
    }

    /// <summary>Change state without asking a transition — a situation, a cutscene, a hit reaction.</summary>
    public void Go(string name)
    {
        int to = IndexOf(name);
        if (_current < 0) { Start(name); return; }
        if (to != _current) Change(to);
    }

    /// <summary>Leave the current state and start again in <paramref name="name"/>, even when it is the same one — a pooled agent taken out again.</summary>
    public void Restart(string name)
    {
        int to = IndexOf(name);
        if (_current >= 0) _states[_current].Exit(_context);
        Start(_names[to]);
    }

    public bool Is(string name) => _current >= 0 && _names[_current] == name;

    void Change(int to)
    {
        int from = _current;
        _states[from].Exit(_context);
        _previous = from;
        _current = to;
        TimeInState = 0f;
        Changes++;
        _states[to].Enter(_context);
        Changed?.Invoke(_names[from], _names[to]);
    }

    int IndexOf(string name)
    {
        int i = _names.IndexOf(name);
        if (i < 0) throw new ArgumentException("no state named '" + name + "' — Add it before naming it", nameof(name));
        return i;
    }
}
