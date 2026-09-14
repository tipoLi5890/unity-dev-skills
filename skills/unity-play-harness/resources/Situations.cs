using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

/// <summary>
/// A named moment the game can boot straight into, plus the set of things that must be
/// true before anyone — a test, a screenshot, a human — is allowed to look at it.
///
/// Enter calls the game's OWN transition. It never assigns a state field: a situation that
/// sets `state = "Approach"` by hand tests a label, not the game.
/// </summary>
public sealed class Situation
{
    /// <summary>Kebab-case, stable, used from the command line: approach-gate.</summary>
    public string Id;

    /// <summary>Drives the game into the moment, using the same methods a player's input reaches.</summary>
    public Action Enter;

    /// <summary>Named members that must ALL read true. A null Func means "resolve this name
    /// against GameProbe's registry" — for members the game registers itself.</summary>
    public Dictionary<string, Func<bool>> Ready = new Dictionary<string, Func<bool>>();

    /// <summary>Unscaled seconds before WaitUntilReady gives up and names what is missing.</summary>
    public float TimeoutSeconds = 15f;

    public Situation() { }

    public Situation(string id, Action enter, float timeoutSeconds = 15f)
    {
        Id = id;
        Enter = enter;
        TimeoutSeconds = timeoutSeconds;
    }

    /// <summary>Chainable member declaration: .Needs("laneCollider", () => _lane != null &amp;&amp; _lane.HasCollider)</summary>
    public Situation Needs(string name, Func<bool> isReady = null)
    {
        Ready[name] = isReady;
        return this;
    }
}

/// <summary>
/// The registry. Register every situation from the boot scene's Awake, so the ids exist
/// before anything asks for them — including a command line that named one.
/// </summary>
public static class Situations
{
    static readonly Dictionary<string, Situation> _all = new Dictionary<string, Situation>();
    static readonly List<string> _order = new List<string>();
    static readonly Dictionary<string, string> _params = new Dictionary<string, string>();
    static readonly List<string> _pushed = new List<string>();
    static bool _paramsParsed;

    /// <summary>The id of the situation most recently entered. Mirrored into the probe.</summary>
    public static string Current { get; private set; }

    public static void Register(Situation s)
    {
        if (s == null || string.IsNullOrEmpty(s.Id)) throw new ArgumentException("situation needs an Id");
        if (s.Enter == null) throw new ArgumentException("situation '" + s.Id + "' has no Enter");
        if (!_all.ContainsKey(s.Id)) _order.Add(s.Id);
        _all[s.Id] = s;
    }

    public static Situation Register(string id, Action enter, float timeoutSeconds = 15f)
    {
        var s = new Situation(id, enter, timeoutSeconds);
        Register(s);
        return s;
    }

    /// <summary>Every registered id, in registration order. Print this instead of recalling names.</summary>
    public static string[] Ids() => _order.ToArray();

    public static bool Has(string id) => id != null && _all.ContainsKey(id);

    public static Situation Get(string id)
    {
        if (!Has(id))
            throw new ArgumentException("no situation '" + id + "'; registered: " + string.Join(", ", Ids()));
        return _all[id];
    }

    /// <summary>
    /// Runs the situation's Enter, pushes its readiness members into the probe, and hands back a
    /// handle to wait on. Entering does NOT mean the moment is ready — that is what the handle is for.
    /// </summary>
    public static SituationHandle Enter(string id)
    {
        Situation s = Get(id);

        // A second Enter in the same session would otherwise inherit the first one's members,
        // and a stale true reads as "already ready". Drop only what a situation added: the
        // members the GAME registered at startup belong to the game and stay.
        for (int i = 0; i < _pushed.Count; i++) GameProbe.ClearReady(_pushed[i]);
        _pushed.Clear();

        Current = s.Id;
        GameProbe.Situation = s.Id;

        foreach (KeyValuePair<string, Func<bool>> m in s.Ready)
        {
            // A null predicate means the member is one the game already registered — leave it
            // alone rather than re-registering it, which would make it resolve against itself.
            if (m.Value == null) continue;
            GameProbe.Ready(m.Key, m.Value);
            _pushed.Add(m.Key);
        }

        s.Enter();
        Debug.Log("[SITUATION] enter=" + s.Id + " needs=" + string.Join(",", NamesOf(s)) +
                  " timeout=" + s.TimeoutSeconds.ToString("F1", CultureInfo.InvariantCulture) + "s");
        return new SituationHandle(s);
    }

    static string[] NamesOf(Situation s)
    {
        var names = new List<string>(s.Ready.Keys);
        return names.ToArray();
    }

    // ---------------------------------------------------------------- parameters

    /// <summary>
    /// Situation parameters, from three sources, later wins:
    ///   -situation-param angle=80        (command line, repeatable)
    ///   PLAY_SITUATION_PARAMS=angle=80,cold=true   (environment)
    ///   Situations.SetParam("angle", 80)           (a test, before Enter)
    /// </summary>
    public static void SetParam(string name, object value)
    {
        EnsureParams();
        _params[name] = Convert.ToString(value, CultureInfo.InvariantCulture);
    }

    public static void ClearParams()
    {
        _params.Clear();
        _paramsParsed = true;   // a test that cleared params does not want the command line back
    }

    public static string Param(string name, string fallback = null)
    {
        EnsureParams();
        return _params.TryGetValue(name, out string v) ? v : fallback;
    }

    public static float Param(string name, float fallback)
    {
        string v = Param(name, null);
        return v != null && float.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out float f)
            ? f : fallback;
    }

    public static int Param(string name, int fallback)
    {
        string v = Param(name, null);
        return v != null && int.TryParse(v, NumberStyles.Integer, CultureInfo.InvariantCulture, out int i)
            ? i : fallback;
    }

    public static bool Param(string name, bool fallback)
    {
        string v = Param(name, null);
        if (v == null) return fallback;
        v = v.Trim().ToLowerInvariant();
        return v == "1" || v == "true" || v == "yes";
    }

    /// <summary>Every parameter in play, for the journey's meta line.</summary>
    public static Dictionary<string, string> AllParams()
    {
        EnsureParams();
        return new Dictionary<string, string>(_params);
    }

    static void EnsureParams()
    {
        if (_paramsParsed) return;
        _paramsParsed = true;

        string env = Environment.GetEnvironmentVariable("PLAY_SITUATION_PARAMS");
        if (!string.IsNullOrEmpty(env))
            foreach (string pair in env.Split(','))
                Assign(pair);

        string[] args = Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == "-situation-param") Assign(args[i + 1]);
    }

    static void Assign(string pair)
    {
        if (string.IsNullOrEmpty(pair)) return;
        int eq = pair.IndexOf('=');
        if (eq <= 0) return;
        _params[pair.Substring(0, eq).Trim()] = pair.Substring(eq + 1).Trim();
    }

    // ---------------------------------------------------------------- lifetime

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetBeforeFirstScene()
    {
        // Statics survive a play session when domain reload is disabled. A registry holding
        // last session's delegates enters a situation that points at destroyed objects.
        _all.Clear();
        _order.Clear();
        _params.Clear();
        _pushed.Clear();
        _paramsParsed = false;
        Current = null;
    }
}

/// <summary>What Enter hands back: the wait, and the list of what is still missing.</summary>
public sealed class SituationHandle
{
    readonly Situation _s;

    public SituationHandle(Situation s) { _s = s; }

    public string Id => _s.Id;
    public float TimeoutSeconds => _s.TimeoutSeconds;

    /// <summary>Every member, re-evaluated now.</summary>
    public bool IsReady => Missing().Length == 0;

    /// <summary>The members not yet true, in declaration order.</summary>
    public string[] Missing()
    {
        var missing = new List<string>();
        foreach (KeyValuePair<string, Func<bool>> m in _s.Ready)
        {
            bool ok;
            try { ok = m.Value != null ? m.Value() : GameProbe.IsReady(m.Key); }
            catch (Exception e) { Debug.LogWarning("[SITUATION] " + m.Key + " threw: " + e.Message); ok = false; }
            if (!ok) missing.Add(m.Key);
        }
        return missing.ToArray();
    }

    /// <summary>
    /// yield return handle.WaitUntilReady() — polls once per frame on UNSCALED time, so a
    /// situation that sets timeScale to 0 still times out instead of hanging the suite.
    /// Throws TimeoutException naming the members that never arrived.
    /// </summary>
    public IEnumerator WaitUntilReady(float? timeoutSeconds = null)
    {
        float limit = timeoutSeconds ?? _s.TimeoutSeconds;
        float start = Time.unscaledTime;
        string[] missing = Missing();
        while (missing.Length > 0)
        {
            if (Time.unscaledTime - start > limit)
                throw new TimeoutException(_s.Id + " not ready after " +
                    limit.ToString("F1", CultureInfo.InvariantCulture) + "s: " + string.Join(", ", missing));
            yield return null;
            missing = Missing();
        }
        Debug.Log("[SITUATION] ready=" + _s.Id + " after " +
                  (Time.unscaledTime - start).ToString("F2", CultureInfo.InvariantCulture) + "s");
    }
}

/// <summary>
/// Boots a windowed or player run straight into a situation named on the command line or in
/// the environment, with no test framework involved:
///
///   "$UNITY" -projectPath &lt;p&gt; -situation approach-gate -situation-param angle=80
///   PLAY_SITUATION=approach-gate ./Build/Game
///
/// Installs itself after the first scene loads. Suppressed during -runTests, because a test
/// enters its own situation and two Enters race each other.
/// </summary>
public sealed class SituationBoot : MonoBehaviour
{
    /// <summary>Set true before the first scene load to keep the boot out of a run entirely.</summary>
    public static bool Suppress;

    /// <summary>The id this run was told to enter, or null.</summary>
    public static string Requested { get; private set; }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Install()
    {
        Requested = FromCommandLine() ?? Environment.GetEnvironmentVariable("PLAY_SITUATION");
        if (string.IsNullOrEmpty(Requested) || Suppress) return;
        if (IsTestRun())
        {
            Debug.Log("[SITUATION] boot suppressed: this is a test run");
            return;
        }

        // A windowed run that loses focus stops ticking, and every wait then times out for a
        // reason that has nothing to do with the game.
        Application.runInBackground = true;

        var go = new GameObject("~SituationBoot") { hideFlags = HideFlags.HideInHierarchy };
        DontDestroyOnLoad(go);
        go.AddComponent<SituationBoot>();
    }

    static string FromCommandLine()
    {
        string[] args = Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == "-situation") return args[i + 1];
        return null;
    }

    static bool IsTestRun()
    {
        foreach (string a in Environment.GetCommandLineArgs())
            if (a == "-runTests" || a == "-testPlatform") return true;
        return false;
    }

    IEnumerator Start()
    {
        // One frame, so every Awake that registers a situation has run.
        yield return null;

        if (!Situations.Has(Requested))
        {
            Debug.LogError("[SITUATION] unknown id=" + Requested + " registered=" +
                           string.Join(",", Situations.Ids()));
            yield break;
        }

        SituationHandle handle = Situations.Enter(Requested);
        IEnumerator wait = handle.WaitUntilReady();
        while (true)
        {
            // C# forbids yielding inside a catch clause, so the failure leaves the try as data.
            bool moved = false;
            string timedOut = null;
            try { moved = wait.MoveNext(); }
            catch (TimeoutException e) { timedOut = e.Message; }

            if (timedOut != null)
            {
                // A boot must not throw into nothing: name the missing members and leave the
                // window up, so the moment can still be looked at and photographed.
                Debug.LogError("[SITUATION] TIMEOUT " + timedOut);
                yield break;
            }
            if (!moved) break;
            yield return wait.Current;
        }

        GameProbe.Log("PROBE");
    }
}
