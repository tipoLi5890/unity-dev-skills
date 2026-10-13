// HitStop.cs — the one owner of Time.timeScale: hit stop, slow motion and pause all ask it.
//
// Drop into a Runtime assembly. No package needed. Nothing has to be placed in a scene: the
// first request creates a hidden owner that survives scene loads. Place one HitStop component
// in the boot scene only to change the numbers below in the inspector.
//
//   HitStop.Request(0.08f);              // a hit: 80 ms at the default scale
//   HitStop.Request(0.6f, 0.3f);         // slow motion: 600 ms at 30 % speed
//   HitStop.SetBase(0f);                 // pause — and SetBase(1f) to resume
//
// Why one owner: "timeScale = 0; wait; timeScale = 1" written on the thing that got hit breaks
// three ways. Two overlapping stops restore twice, and the second restores the first one's
// dip. A stop that begins inside slow motion restores to 1 and ends the slow motion. And the
// requester is often destroyed by the hit that froze the game, taking the restore with it.
// Here a request is a value (an end time and a scale) in a list this object owns; nothing of
// the requester is kept, so nothing of it can be missing when the time comes.
using System;
using UnityEngine;

[AddComponentMenu("Courier/Hit Stop")]
[DefaultExecutionOrder(-10000)]   // the scale is settled before any gameplay Update reads deltaTime
public sealed class HitStop : MonoBehaviour
{
    [Tooltip("Scale used when a request names none. 0.05 reads as a freeze and still leaves deltaTime above zero, so nothing divides by it.")]
    [Range(0f, 1f)] public float defaultScale = 0.05f;
    [Tooltip("Longest single request, seconds. A longer one is clamped to this.")]
    public float maxSeconds = 1f;
    [Tooltip("Longest run of overlapping or back-to-back hit stops (scale under 0.2), seconds, measured from the first. Thirty hits in a row freeze the game this long, not thirty times as long.")]
    public float maxContinuousSeconds = 0.25f;
    [Tooltip("Hit stops are refused for this long after one ends, so a stream of hits is not a stream of freezes.")]
    public float cooldownSeconds = 0.05f;

    /// <summary>Accessibility and debugging: false refuses every request. SetBase still works.</summary>
    public static bool Enabled = true;

    const int Capacity = 16;
    const float HitStopBelow = 0.2f;   // a request under this scale is a freeze and spends the continuous budget

    struct Entry
    {
        public int id;
        public float end;      // Time.unscaledTime
        public float scale;
    }

    static HitStop _instance;
    static bool _quitting;
    static int _nextId = 1;

    readonly Entry[] _entries = new Entry[Capacity];
    int _count;
    float _base = 1f;          // what timeScale is when nothing is requested
    bool _applied;             // this object's value is the one in Time.timeScale
    float _written = 1f;
    float _burstStart = -1f;
    float _lastEnd = float.NegativeInfinity;

    // ------------------------------------------------------------------------------ the API

    /// <summary>True while at least one request is live.</summary>
    public static bool Active => _instance != null && _instance._count > 0;

    /// <summary>The scale time returns to when the last request ends.</summary>
    public static float Base => _instance != null ? _instance._base : Time.timeScale;

    /// <summary>Requests accepted since the owner was created.</summary>
    public static int Accepted { get; private set; }

    /// <summary>Requests refused: disabled, on cooldown, over the continuous budget, or no room.</summary>
    public static int Refused { get; private set; }

    /// <summary>
    /// Scale time for <paramref name="seconds"/> of real time. Overlapping requests do not add:
    /// the lowest scale among the live ones applies and time comes back when the last ends, to
    /// the value it had before the first. Returns an id for <see cref="Cancel"/>, or 0 when
    /// refused. A negative <paramref name="scale"/> means the owner's default.
    /// </summary>
    public static int Request(float seconds, float scale = -1f)
    {
        if (!Enabled || _quitting || seconds <= 0f) { Refused++; return 0; }
        HitStop owner = Owner();
        return owner != null ? owner.Add(seconds, scale) : 0;
    }

    /// <summary>End one request early. The others keep their time.</summary>
    public static void Cancel(int id)
    {
        if (id == 0 || _instance == null) return;
        for (int i = 0; i < _instance._count; i++)
        {
            if (_instance._entries[i].id != id) continue;
            _instance.RemoveAt(i);
            _instance.Apply();
            return;
        }
    }

    /// <summary>
    /// The scale underneath every request: 0 to pause, 1 to resume, 0.5 for a slow field. A
    /// pause that writes Time.timeScale itself races the restore; a pause that calls this never
    /// does, because the restore goes to whatever the base is by then.
    /// </summary>
    public static void SetBase(float scale)
    {
        scale = Mathf.Max(0f, scale);
        if (_instance == null && !_quitting)
        {
            Time.timeScale = scale;      // no owner exists: the first request adopts this value
            return;
        }
        if (_instance == null) return;
        _instance._base = scale;
        _instance.Apply(true);
    }

    /// <summary>Drop every request and put the base scale back now — on a scene change, a restart, a test's tear-down.</summary>
    public static void Clear()
    {
        if (_instance == null) return;
        _instance._count = 0;
        _instance._burstStart = -1f;
        _instance._lastEnd = float.NegativeInfinity;
        _instance.Apply();
    }

    // ---------------------------------------------------------------------------- the owner

    static HitStop Owner()
    {
        if (_instance != null) return _instance;
        _instance = FindAnyObjectByType<HitStop>();
        if (_instance != null) return _instance;
        var go = new GameObject("HitStop") { hideFlags = HideFlags.HideAndDontSave };
        DontDestroyOnLoad(go);
        return go.AddComponent<HitStop>();      // Awake sets _instance
    }

    void Awake()
    {
        if (_instance != null && _instance != this)
        {
            Destroy(this);      // a second owner is the bug this file exists to remove
            return;
        }
        _instance = this;
        _base = Time.timeScale;
    }

    int Add(float seconds, float scale)
    {
        float now = Time.unscaledTime;
        if (scale < 0f) scale = defaultScale;
        scale = Mathf.Clamp01(scale);
        seconds = Mathf.Min(seconds, maxSeconds);
        bool freeze = scale < HitStopBelow;

        if (_count == 0)
        {
            // Someone may have written timeScale directly since the last restore. Adopt it: the
            // value before the first request is the value to go back to.
            if (!_applied) _base = Time.timeScale;
            if (freeze && now - _lastEnd < cooldownSeconds) { Refused++; return 0; }
        }

        float end = now + seconds;
        if (freeze)
        {
            if (_burstStart < 0f) _burstStart = now;
            end = Mathf.Min(end, _burstStart + maxContinuousSeconds);
            if (end <= now) { Refused++; return 0; }
        }
        if (_count == Capacity) { Refused++; return 0; }

        int id = _nextId++;
        _entries[_count++] = new Entry { id = id, end = end, scale = scale };
        Accepted++;
        Apply();
        return id;
    }

    void Update()
    {
        if (_count == 0) return;
        // Unscaled: a timer on scaled time would never finish the stop it is timing.
        float now = Time.unscaledTime;
        bool removed = false;
        for (int i = _count - 1; i >= 0; i--)
        {
            if (_entries[i].end > now) continue;
            RemoveAt(i);
            removed = true;
        }
        if (removed) Apply();
    }

    void RemoveAt(int i)
    {
        _entries[i] = _entries[--_count];
        if (_count == 0)
        {
            _burstStart = -1f;
            _lastEnd = Time.unscaledTime;
        }
    }

    // The single place Time.timeScale is written.
    void Apply(bool baseChanged = false)
    {
        // A value in timeScale that is not the one this object last wrote was put there by
        // something else — a pause menu that never heard of SetBase. It is not fought: it
        // becomes the base, so the restore goes back to it and a pause survives a hit stop.
        bool foreign = _applied && !Mathf.Approximately(Time.timeScale, _written);
        if (foreign && !baseChanged)
        {
            Debug.LogWarning("[HITSTOP] Time.timeScale was written outside HitStop (" + Time.timeScale.ToString("F2") +
                             "). Route pause and slow motion through HitStop.SetBase / Request.");
            _base = Time.timeScale;
        }

        if (_count == 0)
        {
            if (_applied || baseChanged) Time.timeScale = _base;
            _applied = false;
            return;
        }

        float target = _base;
        for (int i = 0; i < _count; i++)
            if (_entries[i].scale < target) target = _entries[i].scale;
        Time.timeScale = target;
        _written = target;
        _applied = true;
    }

    // Guaranteed restore: whatever ends this object — a scene unload, a domain teardown, a quit —
    // time is put back first. A frozen Editor after a stopped play session is this missing.
    void OnDisable() => Restore();

    void OnDestroy()
    {
        Restore();
        if (_instance == this) _instance = null;
    }

    void OnApplicationQuit()
    {
        _quitting = true;
        Restore();
    }

    void Restore()
    {
        if (_count == 0 && !_applied) return;
        _count = 0;
        _burstStart = -1f;
        if (_applied) Time.timeScale = _base;
        _applied = false;
    }

    // With domain reload off, statics survive from one play session into the next.
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        _instance = null;
        _quitting = false;
        _nextId = 1;
        Accepted = 0;
        Refused = 0;
        Enabled = true;
    }
}
