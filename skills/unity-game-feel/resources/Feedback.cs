// Feedback.cs — plays one row of the feedback table: what a gameplay event shows, sounds and
// shakes, for how long and how strongly. The rows are data on this component; a designer
// tunes them without opening code, and an audit can add them up.
//
// Drop into a Runtime assembly with HitStop.cs, RendererFlash.cs, Tween.cs and SfxPlayer.cs
// (this skill → resources/). No package needed. Put one on the runner, one on each sentry.
//
//   feedback.Play("hit", contactPoint, -contactNormal);
//   feedback.Play("pickup");
//
// Gameplay raises the event and nothing else. It never names a particle system, a clip or a
// shake strength: change the row and the game changes, with no gameplay code touched.
//
// Two channels leave this file as static events, so it compiles with neither Cinemachine nor
// the Input System installed. The side that owns the device subscribes:
//   Feedback.ShakeRequested   the camera side turns it into an impulse (skill unity-camera,
//                             reference/shake-and-blends.md)
//   Feedback.HapticRequested  the input side turns it into motor speeds (reference/haptics.md)
// With no subscriber the channel is silent, and Play still returns true.
using System;
using UnityEngine;
using UnityDev.GameFeel;

/// <summary>What the player chose. Every channel reads these; none of them is optional to honour.</summary>
public static class FeelSettings
{
    /// <summary>No squash, no shake, no time dip. The event still sounds, flashes and counts.</summary>
    public static bool reduceMotion;
    /// <summary>Flashes blend 35 % of the way to their colour and never repeat faster than 3 a second.</summary>
    public static bool reduceFlash;
    /// <summary>0..1, multiplied into every shake strength. The camera side multiplies it into its listener gain too.</summary>
    public static float shake = 1f;
    /// <summary>0..1, multiplied into every motor speed. 0 is off.</summary>
    public static float haptics = 1f;

    public const float ReducedFlashStrength = 0.35f;
    public const float ReducedFlashInterval = 1f / 3f;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        reduceMotion = false;
        reduceFlash = false;
        shake = 1f;
        haptics = 1f;
    }
}

[Serializable]
public struct MotionChannel
{
    public bool on;
    [Tooltip("The child that only draws. Never the object carrying the body or the collider.")]
    public Transform visual;
    [Tooltip("Height at the start, as a fraction: 0.8 squashes (a landing), 1.2 stretches (a launch).")]
    public float squash;
    public int ms;
    [Tooltip("On for a sprite: the one visible side axis takes 1/squash. Off: both side axes take 1/sqrt(squash).")]
    public bool is2D;
}

[Serializable]
public struct FlashChannel
{
    public bool on;
    public RendererFlash target;
    public Color colour;
    public int ms;
}

[Serializable]
public struct ParticleChannel
{
    public bool on;
    [Tooltip("A scene emitter in World simulation space. It is moved to the event and asked for 'count' particles: no instantiate, no pool.")]
    public ParticleSystem system;
    public int count;
}

[Serializable]
public struct ShakeChannel
{
    public bool on;
    [Tooltip("Share of the camera's shake budget: 0.3 light, 0.6 medium, 1 heavy.")]
    [Range(0f, 1f)] public float strength;
}

[Serializable]
public struct SoundChannel
{
    public bool on;
    [Tooltip("An event name in the SfxPlayer's table.")]
    public string sfxEvent;
}

[Serializable]
public struct HapticChannel
{
    public bool on;
    [Tooltip("The heavy motor: a thud.")]
    [Range(0f, 1f)] public float low;
    [Tooltip("The light motor: a buzz.")]
    [Range(0f, 1f)] public float high;
    public int ms;
}

[Serializable]
public struct TimeChannel
{
    public bool on;
    public int ms;
    [Tooltip("Time scale during the stop. 0.05 is a freeze; 0.3 for 600 ms is slow motion.")]
    [Range(0f, 1f)] public float scale;
}

[Serializable]
public sealed class FeedbackRow
{
    public string id = "hit";
    [Tooltip("0 small (pickup, step), 1 medium (hit, land), 2 big (gate, launch, fail).")]
    public int priority;
    [Tooltip("While this row is live, rows of lower priority are muted for this long. 0 mutes nothing.")]
    public int muteLowerMs;
    public MotionChannel motion;
    public FlashChannel flash;
    public ParticleChannel particles;
    public ShakeChannel shake;
    public SoundChannel sound;
    public HapticChannel haptic;
    public TimeChannel time;

    /// <summary>The longest enabled channel: how long this row occupies the player, in milliseconds.</summary>
    public int LengthMs
    {
        get
        {
            int ms = 0;
            if (motion.on) ms = Mathf.Max(ms, motion.ms);
            if (flash.on) ms = Mathf.Max(ms, flash.ms);
            if (haptic.on) ms = Mathf.Max(ms, haptic.ms);
            if (time.on) ms = Mathf.Max(ms, time.ms);
            return ms;
        }
    }
}

[AddComponentMenu("Courier/Feedback")]
public sealed class Feedback : MonoBehaviour
{
    public FeedbackRow[] rows = new FeedbackRow[0];
    public SfxPlayer sfx;
    [Tooltip("Longest any one row may run, milliseconds. A longer row is reported by Audit and by OnValidate.")]
    public int eventBudgetMs = 300;
    [Tooltip("Rows live at once, across every Feedback in the game. A row past this plays only when it outranks one that is live.")]
    public int globalLiveRows = 3;

    /// <summary>Where, which way (unit vector; zero when the event has no direction), strength 0..1 after the player's setting.</summary>
    public static event Action<Vector3, Vector3, float> ShakeRequested;
    /// <summary>Low motor 0..1, high motor 0..1, seconds — after the player's setting.</summary>
    public static event Action<float, float, float> HapticRequested;

    const int Live = 16;
    static readonly float[] _liveEnd = new float[Live];
    static readonly int[] _livePriority = new int[Live];
    static float _muteUntil;
    static int _muteBelow;
    static float _lastFlash = float.NegativeInfinity;

    /// <summary>Rows played by this component.</summary>
    public int Played { get; private set; }
    /// <summary>Rows refused: muted by a bigger event, or over the global budget.</summary>
    public int Muted { get; private set; }
    /// <summary>Ids asked for that no row has. Not zero means a typo.</summary>
    public int Unknown { get; private set; }

    public bool Play(string id) => Play(id, transform.position, Vector3.zero);

    /// <summary>Play the row named <paramref name="id"/>. False when it was muted, over budget or unknown.</summary>
    public bool Play(string id, Vector3 position, Vector3 direction)
    {
        FeedbackRow row = Find(id);
        if (row == null)
        {
            Unknown++;
            return false;
        }

        // Unscaled throughout: the row's own time dip must not stretch the row.
        float now = Time.unscaledTime;
        if (now >= _muteUntil) _muteBelow = 0;
        if (row.priority < _muteBelow || !TakeLiveSlot(row, now))
        {
            Muted++;
            return false;
        }
        if (row.muteLowerMs > 0 && row.priority >= _muteBelow)
        {
            _muteBelow = row.priority;
            _muteUntil = Mathf.Max(_muteUntil, now + row.muteLowerMs * 0.001f);
        }

        bool calm = FeelSettings.reduceMotion;

        if (row.time.on && !calm && row.time.ms > 0)
            HitStop.Request(row.time.ms * 0.001f, row.time.scale);

        if (row.motion.on && !calm && row.motion.visual != null && row.motion.ms > 0)
            // Unscaled, so the squash is seen through the stop it accompanies. The rest scale is
            // Vector3.one by convention: the visual child carries no authored scale of its own.
            Tween.Squash(row.motion.visual, Vector3.one, row.motion.squash, row.motion.ms * 0.001f, row.motion.is2D,
                         Ease.OutBack, true);

        if (row.flash.on && row.flash.target != null && row.flash.ms > 0)
        {
            if (!FeelSettings.reduceFlash)
                row.flash.target.Flash(row.flash.colour, row.flash.ms * 0.001f, 1f);
            else if (now - _lastFlash >= FeelSettings.ReducedFlashInterval)
            {
                row.flash.target.Flash(row.flash.colour, row.flash.ms * 0.001f, FeelSettings.ReducedFlashStrength);
                _lastFlash = now;
            }
        }

        if (row.particles.on && row.particles.system != null && row.particles.count > 0)
        {
            Transform emitter = row.particles.system.transform;
            emitter.position = position;
            if (direction.sqrMagnitude > 1e-6f) emitter.rotation = Quaternion.LookRotation(direction);
            row.particles.system.Emit(calm ? Mathf.Max(1, row.particles.count / 2) : row.particles.count);
        }

        if (row.shake.on && !calm)
        {
            float strength = row.shake.strength * Mathf.Clamp01(FeelSettings.shake);
            if (strength > 0f) ShakeRequested?.Invoke(position, direction, strength);
        }

        if (row.sound.on && sfx != null) sfx.Play(row.sound.sfxEvent, position);

        if (row.haptic.on && row.haptic.ms > 0)
        {
            float gain = Mathf.Clamp01(FeelSettings.haptics);
            if (gain > 0f) HapticRequested?.Invoke(row.haptic.low * gain, row.haptic.high * gain, row.haptic.ms * 0.001f);
        }

        Played++;
        return true;
    }

    // Reset runs when the component is added in the Editor: it starts as the courier table, and
    // every number in it is one to change.
    void Reset() => rows = DefaultRows();

    /// <summary>
    /// The courier run's table. Targets (the visual, the flash, the emitters) are left empty: a
    /// channel with no target is skipped, so the rows play as far as they are wired.
    /// </summary>
    public static FeedbackRow[] DefaultRows()
    {
        return new[]
        {
            new FeedbackRow
            {
                id = "pickup", priority = 0,
                motion = new MotionChannel { on = true, squash = 1.15f, ms = 100 },
                particles = new ParticleChannel { on = true, count = 6 },
                sound = new SoundChannel { on = true, sfxEvent = "pickup" },
            },
            new FeedbackRow
            {
                id = "land", priority = 1,
                motion = new MotionChannel { on = true, squash = 0.8f, ms = 120 },
                particles = new ParticleChannel { on = true, count = 8 },
                shake = new ShakeChannel { on = true, strength = 0.3f },
                sound = new SoundChannel { on = true, sfxEvent = "land" },
                haptic = new HapticChannel { on = true, low = 0.3f, high = 0f, ms = 60 },
            },
            new FeedbackRow
            {
                id = "hit", priority = 1, muteLowerMs = 100,
                motion = new MotionChannel { on = true, squash = 0.85f, ms = 100 },
                flash = new FlashChannel { on = true, colour = Color.white, ms = 80 },
                particles = new ParticleChannel { on = true, count = 12 },
                shake = new ShakeChannel { on = true, strength = 0.6f },
                sound = new SoundChannel { on = true, sfxEvent = "hit" },
                haptic = new HapticChannel { on = true, low = 0.6f, high = 0.3f, ms = 120 },
                time = new TimeChannel { on = true, ms = 80, scale = 0.05f },
            },
            new FeedbackRow
            {
                id = "launch", priority = 2, muteLowerMs = 150,
                motion = new MotionChannel { on = true, squash = 1.25f, ms = 150 },
                particles = new ParticleChannel { on = true, count = 20 },
                shake = new ShakeChannel { on = true, strength = 0.6f },
                sound = new SoundChannel { on = true, sfxEvent = "launch" },
                haptic = new HapticChannel { on = true, low = 0.5f, high = 0.5f, ms = 150 },
            },
            new FeedbackRow
            {
                id = "fail", priority = 2, muteLowerMs = 300,
                flash = new FlashChannel { on = true, colour = Color.red, ms = 120 },
                particles = new ParticleChannel { on = true, count = 24 },
                shake = new ShakeChannel { on = true, strength = 1f },
                sound = new SoundChannel { on = true, sfxEvent = "fail" },
                haptic = new HapticChannel { on = true, low = 1f, high = 1f, ms = 250 },
                time = new TimeChannel { on = true, ms = 120, scale = 0.05f },
            },
        };
    }

    public FeedbackRow Find(string id)
    {
        if (rows == null || id == null) return null;
        for (int i = 0; i < rows.Length; i++)
            if (rows[i] != null && rows[i].id == id) return rows[i];
        return null;
    }

    /// <summary>One line per row over the event budget; empty when every row fits.</summary>
    public string Audit()
    {
        var sb = new System.Text.StringBuilder();
        if (rows == null) return "";
        foreach (FeedbackRow row in rows)
        {
            if (row == null) continue;
            if (row.LengthMs > eventBudgetMs)
                sb.AppendLine("row '" + row.id + "' runs " + row.LengthMs + " ms, budget " + eventBudgetMs + " ms");
            if (row.time.on && row.time.scale < 0.2f && row.time.ms > 150)
                sb.AppendLine("row '" + row.id + "' freezes time for " + row.time.ms + " ms; over 150 ms reads as a hang");
        }
        return sb.ToString();
    }

    void OnValidate()
    {
        string problems = Audit();
        if (problems.Length > 0) Debug.LogWarning("[FEEDBACK] " + name + "\n" + problems, this);
    }

    // A row takes a slot for its length. With every slot of the global budget taken, it plays
    // only by replacing a live row of strictly lower priority — a pickup never displaces a hit.
    bool TakeLiveSlot(FeedbackRow row, float now)
    {
        int length = row.LengthMs;
        if (length <= 0) return true;                 // sound or particles only: occupies nobody
        int live = 0, free = -1, lowest = -1;
        for (int i = 0; i < Live; i++)
        {
            if (_liveEnd[i] <= now) { if (free < 0) free = i; continue; }
            live++;
            if (lowest < 0 || _livePriority[i] < _livePriority[lowest]) lowest = i;
        }
        int slot = free;
        if (live >= Mathf.Max(1, globalLiveRows) || free < 0)
        {
            if (lowest < 0 || _livePriority[lowest] >= row.priority) return false;
            slot = lowest;
        }
        _liveEnd[slot] = now + length * 0.001f;
        _livePriority[slot] = row.priority;
        return true;
    }

    /// <summary>Forget every live row and mute — on a restart, a scene change, a test's tear-down.</summary>
    public static void ResetBudget()
    {
        for (int i = 0; i < Live; i++) { _liveEnd[i] = 0f; _livePriority[i] = 0; }
        _muteUntil = 0f;
        _muteBelow = 0;
        _lastFlash = float.NegativeInfinity;
    }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        ResetBudget();
        ShakeRequested = null;
        HapticRequested = null;
    }
}
