// GameState.cs — the game's phase as an explicit state machine: Boot, Menu, Loading, Playing,
// Paused, Won, Lost, with a table of legal transitions. A transition that is not in the table is
// refused and counted, never performed.
//
// Drop into a Runtime assembly. No package needed. Plain C#, so an EditMode test can drive it
// with no scene; Bootstrap.cs creates the one instance the game uses.
//
// Pause is a state here, and Time.timeScale follows the state — not the other way round. With
// ownsTimeScale on, entering Paused stores the current scale and sets 0; leaving restores it.
//
// The harness: RegisterOnProbe() looks GameProbe up by name through reflection and hands it a
// delegate, so this file compiles and runs in a project that never copied unity-play-harness.
// When the probe is there the phase appears as "state" in every snapshot. Under IL2CPP with
// managed stripping, a GameProbe.SetState that nothing calls directly can be stripped, and the
// method then returns false: wire it with one direct line instead, where the game registers its
// other probe hooks —   GameProbe.SetState(() => Bootstrap.Get<GameState>().Name);
using System;
using System.Reflection;
using UnityEngine;

public enum GamePhase { Boot, Menu, Loading, Playing, Paused, Won, Lost }

public sealed class GameState
{
    /// <summary>
    /// The legal transitions. Everything else is refused, including a move to the phase the
    /// game is already in.
    ///
    ///   Boot    → Menu · Loading
    ///   Menu    → Loading
    ///   Loading → Playing · Menu
    ///   Playing → Paused · Won · Lost · Loading
    ///   Paused  → Playing · Loading · Menu
    ///   Won     → Loading · Menu
    ///   Lost    → Loading · Menu
    /// </summary>
    public static bool DefaultRule(GamePhase from, GamePhase to)
    {
        switch (from)
        {
            case GamePhase.Boot: return to == GamePhase.Menu || to == GamePhase.Loading;
            case GamePhase.Menu: return to == GamePhase.Loading;
            case GamePhase.Loading: return to == GamePhase.Playing || to == GamePhase.Menu;
            case GamePhase.Playing:
                return to == GamePhase.Paused || to == GamePhase.Won || to == GamePhase.Lost ||
                       to == GamePhase.Loading;
            case GamePhase.Paused:
                return to == GamePhase.Playing || to == GamePhase.Loading || to == GamePhase.Menu;
            case GamePhase.Won:
            case GamePhase.Lost:
                return to == GamePhase.Loading || to == GamePhase.Menu;
            default: return false;
        }
    }

    /// <summary>The table in use. Replace it for a game with different phases of play; it is
    /// data, so the journey can also swap it to show the gate failing.</summary>
    public Func<GamePhase, GamePhase, bool> Rule = DefaultRule;

    /// <summary>Entering Paused sets Time.timeScale to 0 and leaving restores it.</summary>
    public bool ownsTimeScale = true;

    public GamePhase Phase { get; private set; } = GamePhase.Boot;
    public GamePhase Previous { get; private set; } = GamePhase.Boot;

    /// <summary>The phase as the probe and the timeline print it.</summary>
    public string Name => Phase.ToString();

    public bool IsPlaying => Phase == GamePhase.Playing;
    public bool IsPaused => Phase == GamePhase.Paused;

    /// <summary>Transitions performed since construction.</summary>
    public int Transitions { get; private set; }

    /// <summary>Transitions asked for and refused. A number that grows in a timeline is a caller
    /// that does not know which phase the game is in.</summary>
    public int Refusals { get; private set; }

    /// <summary>"Paused → Won", for the log line and the assertion message.</summary>
    public string LastRefusal { get; private set; } = "";

    /// <summary>Raised after the phase has changed: (from, to).</summary>
    public event Action<GamePhase, GamePhase> Changed;

    /// <summary>Raised when a transition is refused: (from, asked for).</summary>
    public event Action<GamePhase, GamePhase> Refused;

    float _resumeScale = 1f;
    bool _changing;

    public bool CanGo(GamePhase to) => !_changing && to != Phase && Rule != null && Rule(Phase, to);

    /// <summary>
    /// Move to a phase when the table allows it. False, with nothing changed, when it does not —
    /// the caller decides whether that matters; the machine never throws for it.
    /// </summary>
    public bool TryGo(GamePhase to)
    {
        // A handler that asks for another transition from inside Changed would have later
        // handlers hear the two changes in the wrong order. It is refused like any other
        // illegal move: start the next transition from the frame after.
        if (!CanGo(to))
        {
            Refusals++;
            LastRefusal = Phase + " → " + to + (_changing ? " (inside a Changed handler)" : "");
            Refused?.Invoke(Phase, to);
            return false;
        }

        GamePhase from = Phase;
        Previous = from;
        Phase = to;
        Transitions++;

        if (ownsTimeScale)
        {
            if (to == GamePhase.Paused)
            {
                _resumeScale = Time.timeScale;
                Time.timeScale = 0f;
            }
            else if (from == GamePhase.Paused)
            {
                // Back to play: the scale the game was running at, so a pause in slow motion
                // resumes in slow motion. Anywhere else: a menu or a load runs at 1.
                Time.timeScale = to == GamePhase.Playing ? _resumeScale : 1f;
            }
        }

        _changing = true;
        try { Changed?.Invoke(from, to); }
        finally { _changing = false; }
        return true;
    }

    /// <summary>Playing ⇄ Paused. False in any other phase: a menu or a load cannot be paused.</summary>
    public bool TogglePause()
    {
        if (Phase == GamePhase.Playing) return TryGo(GamePhase.Paused);
        if (Phase == GamePhase.Paused) return TryGo(GamePhase.Playing);
        Refusals++;
        LastRefusal = Phase + " → pause toggle";
        return false;
    }

    /// <summary>Give the scale back when the machine is thrown away while paused.</summary>
    public void ReleaseTimeScale()
    {
        if (ownsTimeScale && Phase == GamePhase.Paused) Time.timeScale = 1f;
    }

    /// <summary>
    /// Publish the phase on GameProbe when the harness is in the project. With no key the phase
    /// becomes the probe's "state" (what JourneyAsserts.Monotonic and journey_report.py read);
    /// with a key it is registered as a custom value, for a game whose runner already owns the
    /// state slot. False when the probe is not there — nothing else changes.
    /// </summary>
    public bool RegisterOnProbe(string customKey = null)
    {
        Type probe = FindType("GameProbe");
        if (probe == null) return false;

        const BindingFlags flags = BindingFlags.Public | BindingFlags.Static;
        if (string.IsNullOrEmpty(customKey))
        {
            MethodInfo setState = probe.GetMethod("SetState", flags, null, new[] { typeof(Func<string>) }, null);
            if (setState == null) return false;
            setState.Invoke(null, new object[] { (Func<string>)(() => Name) });
            return true;
        }

        MethodInfo register = probe.GetMethod("Register", flags, null,
                                              new[] { typeof(string), typeof(Func<object>) }, null);
        if (register == null) return false;
        register.Invoke(null, new object[] { customKey, (Func<object>)(() => Name) });
        return true;
    }

    static Type FindType(string name)
    {
        // The probe has no namespace and lives in whichever assembly the game put it in.
        foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
        {
            Type t = assembly.GetType(name, false);
            if (t != null) return t;
        }
        return null;
    }
}
