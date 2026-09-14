using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;
using UnityEngine.SceneManagement;

/// <summary>
/// GameProbe — one line of machine-readable state, readable from four places:
///
///   unity command eval 'return GameProbe.Json();'        (live Editor, sub-second)
///   unity command probe                                  (resources/Editor/ProbeCommands.cs)
///   grep '\[PROBE\]' Editor.log                          (any run that has a reporter)
///   GameProbe.Snapshot()                                 (inside a PlayMode test)
///
/// The probe READS. It never sets a flag, never advances a state machine, never
/// instantiates anything. Every value comes from a delegate the game registered,
/// so the probe cannot drift from the game: when the game stops producing a value,
/// the key disappears and that absence is visible in the line.
///
/// Lives in a Runtime assembly with the game. It is a contract, not instrumentation:
/// unlike a temporary debug component, it ships.
///
/// Unity 6 API notes: Rigidbody.linearVelocity (was .velocity before Unity 6),
/// Time.frameCount, SceneManager.GetActiveScene().name, Camera.main.
/// </summary>
public static class GameProbe
{
    public const int Schema = 1;

    /// <summary>Set by Situations.Enter. Free-standing so GameProbe works without Situations.cs.</summary>
    public static string Situation;

    /// <summary>
    /// Opt-in: drop every registration when a scene unloads, for projects where each scene
    /// registers its own hooks. Off by default, because a single-mode load can raise
    /// sceneUnloaded after the next scene's Awake on some versions — which would wipe the
    /// registrations that Awake just made. Confirm the order on your version before turning it
    /// on; a persistent boot object that registers once needs it off either way.
    /// </summary>
    public static bool ResetOnSceneUnload;

    static readonly Dictionary<string, Func<bool>> _ready = new Dictionary<string, Func<bool>>();
    static readonly List<string> _readyOrder = new List<string>();
    static readonly Dictionary<string, Func<int>> _counts = new Dictionary<string, Func<int>>();
    static readonly List<string> _countsOrder = new List<string>();
    static readonly Dictionary<string, Func<object>> _custom = new Dictionary<string, Func<object>>();
    static readonly List<string> _customOrder = new List<string>();

    static Func<string> _state;
    static Func<Transform> _player;
    static Func<Rigidbody> _body;
    static bool _hooked;

    static Vector3 _lastPos;
    static float _lastPosUt = -1f;
    static Vector3 _derivedVel;

    // ---------------------------------------------------------------- registration

    /// <summary>A readiness member. Re-evaluated on every snapshot — never cache the bool.</summary>
    public static void Ready(string name, Func<bool> isReady)
    {
        if (string.IsNullOrEmpty(name) || isReady == null) return;
        Hook();
        if (!_ready.ContainsKey(name)) _readyOrder.Add(name);
        _ready[name] = isReady;
    }

    /// <summary>Drop one readiness member, or all of them when name is null.</summary>
    public static void ClearReady(string name = null)
    {
        if (name == null) { _ready.Clear(); _readyOrder.Clear(); return; }
        if (_ready.Remove(name)) _readyOrder.Remove(name);
    }

    /// <summary>A named integer that appears under counts{} — spawned hazards, pooled pickups.</summary>
    public static void Count(string name, Func<int> value)
    {
        if (string.IsNullOrEmpty(name) || value == null) return;
        Hook();
        if (!_counts.ContainsKey(name)) _countsOrder.Add(name);
        _counts[name] = value;
    }

    /// <summary>A game-specific value under custom{} — lane index, distance to the gate, LOD level.</summary>
    public static void Register(string key, Func<object> value)
    {
        if (string.IsNullOrEmpty(key) || value == null) return;
        Hook();
        if (!_custom.ContainsKey(key)) _customOrder.Add(key);
        _custom[key] = value;
    }

    public static void Unregister(string key)
    {
        if (key == null) return;
        if (_custom.Remove(key)) _customOrder.Remove(key);
        if (_counts.Remove(key)) _countsOrder.Remove(key);
        if (_ready.Remove(key)) _readyOrder.Remove(key);
    }

    /// <summary>state comes from the game's own state machine. Never from a copy the probe keeps.</summary>
    public static void SetState(Func<string> state) { Hook(); _state = state; }

    /// <summary>pos/vel/speed. Pass the Rigidbody accessor when there is one; otherwise velocity
    /// is derived from the position delta between snapshots (valid when sampled every frame).</summary>
    public static void SetPlayer(Func<Transform> player, Func<Rigidbody> body = null)
    {
        Hook();
        _player = player;
        _body = body;
        _lastPosUt = -1f;
    }

    // ---------------------------------------------------------------- readiness

    /// <summary>True only when at least one member is registered and every member reads true.
    /// An empty set is NOT ready: nothing has declared itself yet.</summary>
    public static bool AllReady
    {
        get
        {
            if (_ready.Count == 0) return false;
            for (int i = 0; i < _readyOrder.Count; i++)
                if (!Eval(_ready[_readyOrder[i]])) return false;
            return true;
        }
    }

    /// <summary>One member, re-evaluated now. An unregistered name reads false — a member that
    /// never appeared and a member that is not ready yet are the same thing to a waiter.</summary>
    public static bool IsReady(string name)
        => name != null && _ready.TryGetValue(name, out Func<bool> f) && Eval(f);

    public static bool HasReadyMember(string name) => name != null && _ready.ContainsKey(name);

    public static string[] ReadyMembers() => _readyOrder.ToArray();

    /// <summary>The members that are not ready — the list a timeout prints.</summary>
    public static string[] MissingReady()
    {
        if (_ready.Count == 0) return new[] { "(no readiness members registered)" };
        var missing = new List<string>();
        for (int i = 0; i < _readyOrder.Count; i++)
        {
            string name = _readyOrder[i];
            if (!Eval(_ready[name])) missing.Add(name);
        }
        return missing.ToArray();
    }

    // ---------------------------------------------------------------- snapshot

    public static ProbeSnapshot Snapshot()
    {
        var s = new ProbeSnapshot
        {
            schema = Schema,
            playing = Application.isPlaying,
            batch = Application.isBatchMode,
        };
        if (!s.playing) return s;

        s.frame = Time.frameCount;
        s.t = Time.time;
        s.ut = Time.unscaledTime;
        s.dt = Time.deltaTime;
        s.timeScale = Time.timeScale;
        s.scene = SceneManager.GetActiveScene().name;
        s.situation = Situation;
        s.state = _state != null ? EvalString(_state) : null;

        var cam = Camera.main;
        s.cam = cam != null ? cam.name : null;

        Transform tr = _player != null ? EvalRef(_player) : null;
        if (tr != null)
        {
            s.hasPlayer = true;
            s.pos = tr.position;
            Rigidbody rb = _body != null ? EvalRef(_body) : null;
            if (rb != null) s.vel = rb.linearVelocity;          // Unity 6 name
            else s.vel = DeriveVelocity(s.pos, s.ut);
            s.speed = s.vel.magnitude;
        }

        s.readyOrder = _readyOrder.ToArray();
        for (int i = 0; i < s.readyOrder.Length; i++)
        {
            string name = s.readyOrder[i];
            s.ready[name] = Eval(_ready[name]);
        }
        s.allReady = s.readyOrder.Length > 0;
        for (int i = 0; i < s.readyOrder.Length && s.allReady; i++)
            if (!s.ready[s.readyOrder[i]]) s.allReady = false;

        s.countsOrder = _countsOrder.ToArray();
        for (int i = 0; i < s.countsOrder.Length; i++)
        {
            string name = s.countsOrder[i];
            s.counts[name] = EvalInt(_counts[name]);
        }

        s.customOrder = _customOrder.ToArray();
        for (int i = 0; i < s.customOrder.Length; i++)
        {
            string key = s.customOrder[i];
            s.custom[key] = EvalObject(_custom[key]);
        }
        return s;
    }

    /// <summary>One JSON object on one line. Outside Play mode: {"schema":1,"playing":false}.</summary>
    public static string Json() => ToJson(Snapshot());

    /// <summary>Human/grep line: [PROBE] frame=412 state=Approach speed=9.800 ready=3/4 missing=laneCollider</summary>
    public static string Line() => ToLine(Snapshot());

    public static void Log(string tag = "PROBE") => Debug.Log("[" + tag + "] " + ToLine(Snapshot()));

    /// <summary>Drop every registration. Runs before the first scene of every session, and from
    /// a test's [SetUp] — call it there, so one test's hooks cannot answer for the next.</summary>
    public static void Reset()
    {
        _ready.Clear(); _readyOrder.Clear();
        _counts.Clear(); _countsOrder.Clear();
        _custom.Clear(); _customOrder.Clear();
        _state = null; _player = null; _body = null;
        Situation = null;
        _lastPosUt = -1f;
        _derivedVel = Vector3.zero;
    }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetBeforeFirstScene()
    {
        // With Enter Play Mode Options set to skip domain reload, statics survive the
        // previous session. Without this the second run starts with a registry full of
        // delegates that close over destroyed objects.
        Reset();
        _hooked = false;
    }

    static void Hook()
    {
        if (_hooked) return;
        _hooked = true;
        SceneManager.sceneUnloaded -= OnSceneUnloaded;
        SceneManager.sceneUnloaded += OnSceneUnloaded;
    }

    static void OnSceneUnloaded(Scene scene)
    {
        if (ResetOnSceneUnload) Reset();
    }

    // ---------------------------------------------------------------- JSON

    /// <summary>A live snapshot carries schema/batch/playing; a journey sample carries n and
    /// milestone instead, because the journey's meta line already states the schema.</summary>
    public static string ToJson(ProbeSnapshot s)
    {
        bool sample = s.n >= 0;
        var sb = new StringBuilder(512);
        sb.Append('{');
        if (sample) Field(sb, "n").Append(s.n);
        else Field(sb, "schema").Append(s.schema);

        if (!s.playing) { Field(sb, "playing").Append("false"); return sb.Append('}').ToString(); }

        Field(sb, "frame").Append(s.frame);
        Field(sb, "t").Append(F(s.t));
        Field(sb, "ut").Append(F(s.ut));
        Field(sb, "dt").Append(s.dt.ToString("F4", CultureInfo.InvariantCulture));
        Field(sb, "timeScale").Append(F(s.timeScale));
        Field(sb, "scene").Append(Str(s.scene));
        Field(sb, "situation").Append(Str(s.situation));
        Field(sb, "state").Append(Str(s.state));
        Field(sb, "cam").Append(Str(s.cam));
        Field(sb, "pos").Append(s.hasPlayer ? Vec(s.pos) : "null");
        Field(sb, "vel").Append(s.hasPlayer ? Vec(s.vel) : "null");
        Field(sb, "speed").Append(s.hasPlayer ? F(s.speed) : "null");

        Field(sb, "ready").Append('{');
        for (int i = 0; i < s.readyOrder.Length; i++)
            Field(sb, s.readyOrder[i]).Append(s.ready[s.readyOrder[i]] ? "true" : "false");
        sb.Append('}');
        Field(sb, "allReady").Append(s.allReady ? "true" : "false");

        Field(sb, "counts").Append('{');
        for (int i = 0; i < s.countsOrder.Length; i++)
            Field(sb, s.countsOrder[i]).Append(s.counts[s.countsOrder[i]]);
        sb.Append('}');

        Field(sb, "custom").Append('{');
        for (int i = 0; i < s.customOrder.Length; i++)
            Field(sb, s.customOrder[i]).Append(Value(s.custom[s.customOrder[i]]));
        sb.Append('}');

        if (sample) Field(sb, "milestone").Append(Str(s.milestone));
        else
        {
            Field(sb, "batch").Append(s.batch ? "true" : "false");
            Field(sb, "playing").Append("true");
        }
        return sb.Append('}').ToString();
    }

    public static string ToLine(ProbeSnapshot s)
    {
        if (!s.playing) return "playing=false";
        int ok = 0;
        for (int i = 0; i < s.readyOrder.Length; i++) if (s.ready[s.readyOrder[i]]) ok++;
        var missing = new List<string>();
        for (int i = 0; i < s.readyOrder.Length; i++)
            if (!s.ready[s.readyOrder[i]]) missing.Add(s.readyOrder[i]);
        var sb = new StringBuilder(160);
        sb.Append("frame=").Append(s.frame)
          .Append(" t=").Append(F(s.t))
          .Append(" scene=").Append(s.scene)
          .Append(" situation=").Append(s.situation ?? "-")
          .Append(" state=").Append(s.state ?? "-");
        if (s.hasPlayer)
            sb.Append(" pos=").Append(Vec(s.pos)).Append(" speed=").Append(F(s.speed));
        sb.Append(" ready=").Append(ok).Append('/').Append(s.readyOrder.Length);
        if (missing.Count > 0) sb.Append(" missing=").Append(string.Join(",", missing.ToArray()));
        return sb.ToString();
    }

    // Appends "key": and the separating comma when one is needed — which is any time the
    // object is not empty, so the same helper works for nested objects.
    static StringBuilder Field(StringBuilder sb, string k)
    {
        if (sb[sb.Length - 1] != '{') sb.Append(',');
        return sb.Append(Str(k)).Append(':');
    }

    static string F(float v)
    {
        if (float.IsNaN(v) || float.IsInfinity(v)) return "null";
        return v.ToString("F3", CultureInfo.InvariantCulture);
    }

    static string Vec(Vector3 v) => "[" + F(v.x) + "," + F(v.y) + "," + F(v.z) + "]";

    static string Str(string s)
    {
        if (s == null) return "null";
        var sb = new StringBuilder(s.Length + 2).Append('"');
        foreach (char c in s)
        {
            if (c == '"' || c == '\\') sb.Append('\\').Append(c);
            else if (c == '\n') sb.Append("\\n");
            else if (c == '\r') sb.Append("\\r");
            else if (c == '\t') sb.Append("\\t");
            else if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
            else sb.Append(c);
        }
        return sb.Append('"').ToString();
    }

    static string Value(object o)
    {
        if (o == null) return "null";
        if (o is bool b) return b ? "true" : "false";
        if (o is float f) return F(f);
        if (o is double d) return F((float)d);
        if (o is int i) return i.ToString(CultureInfo.InvariantCulture);
        if (o is long l) return l.ToString(CultureInfo.InvariantCulture);
        if (o is Vector3 v) return Vec(v);
        if (o is Vector2 v2) return "[" + F(v2.x) + "," + F(v2.y) + "]";
        return Str(o.ToString());
    }

    // ---------------------------------------------------------------- delegate safety

    // A hook that throws must not take the probe with it: a probe that stops answering
    // during a failure is a probe that is missing exactly when it is needed.
    static bool Eval(Func<bool> f)
    {
        try { return f(); } catch (Exception e) { Warn(e); return false; }
    }

    static int EvalInt(Func<int> f)
    {
        try { return f(); } catch (Exception e) { Warn(e); return -1; }
    }

    static string EvalString(Func<string> f)
    {
        try { return f(); } catch (Exception e) { Warn(e); return "(error)"; }
    }

    static object EvalObject(Func<object> f)
    {
        try { return f(); } catch (Exception e) { Warn(e); return null; }
    }

    static T EvalRef<T>(Func<T> f) where T : class
    {
        try { return f(); } catch (Exception e) { Warn(e); return null; }
    }

    static void Warn(Exception e) => Debug.LogWarning("[PROBE] hook threw: " + e.Message);

    static Vector3 DeriveVelocity(Vector3 pos, float ut)
    {
        if (_lastPosUt >= 0f)
        {
            float dt = ut - _lastPosUt;
            if (dt > 1e-5f) _derivedVel = (pos - _lastPos) / dt;
        }
        _lastPos = pos;
        _lastPosUt = ut;
        return _derivedVel;
    }
}

/// <summary>One frame of probe state. Plain data — safe to keep in a list for a whole journey.</summary>
public sealed class ProbeSnapshot
{
    public int schema;
    public bool playing;
    public bool batch;
    public int frame;
    public float t;
    public float ut;
    public float dt;
    public float timeScale;
    public string scene;
    public string situation;
    public string state;
    public string cam;
    public bool hasPlayer;
    public Vector3 pos;
    public Vector3 vel;
    public float speed;
    public string[] readyOrder = new string[0];
    public readonly Dictionary<string, bool> ready = new Dictionary<string, bool>();
    public bool allReady;
    public string[] countsOrder = new string[0];
    public readonly Dictionary<string, int> counts = new Dictionary<string, int>();
    public string[] customOrder = new string[0];
    public readonly Dictionary<string, object> custom = new Dictionary<string, object>();

    /// <summary>Sample index inside a journey. -1 for a live snapshot.</summary>
    public int n = -1;
    public string milestone;

    public bool IsReady(string name) => ready.TryGetValue(name, out bool v) && v;
    public bool HasReady(string name) => ready.ContainsKey(name);
    public int CountOf(string name) => counts.TryGetValue(name, out int v) ? v : 0;
    public object CustomOf(string name) => custom.TryGetValue(name, out object v) ? v : null;

    public float Number(string key, float fallback = 0f)
    {
        object o = CustomOf(key);
        if (o is float f) return f;
        if (o is double d) return (float)d;
        if (o is int i) return i;
        if (o is long l) return l;
        return fallback;
    }

    public string ToJson() => GameProbe.ToJson(this);
    public override string ToString() => GameProbe.ToLine(this);
}

/// <summary>
/// Writes one [PROBE] line to the log every N frames, so a run with no live Editor and no
/// test still leaves a readable trail. Attach to a boot object.
///
/// Gated on a development build: a release player logs nothing.
/// </summary>
public sealed class GameProbeReporter : MonoBehaviour
{
    [Tooltip("0 disables periodic logging; the reporter still answers Log() on demand.")]
    public int logEveryNFrames = 30;

    [Tooltip("Also log one line the frame the readiness set flips to complete.")]
    public bool logReadyTransition = true;

    bool _enabledHere;
    bool _wasReady;

    void Awake()
    {
        _enabledHere = Debug.isDebugBuild || Application.isEditor;
        if (!_enabledHere) enabled = false;
    }

    void Update()
    {
        if (!_enabledHere) return;

        if (logReadyTransition)
        {
            bool now = GameProbe.AllReady;
            if (now && !_wasReady) GameProbe.Log("PROBE");
            _wasReady = now;
        }

        if (logEveryNFrames > 0 && Time.frameCount % logEveryNFrames == 0)
            GameProbe.Log("PROBE");
    }
}
