// Health — the receiving end of a hit: hearts, a team, an invincibility timer, and death as a
// state that is entered once.
//
// Drop into a Runtime assembly beside DamageInfo.cs and add it to the ROOT of whatever can be
// hit — the object that owns the character's state — with the hurtbox colliders on its children.
// No package needed; no physics type is named here.
//
// What it does not do: move anything, destroy anything, play anything. Knock-back is a field of
// the DamageInfo that the character's own controller reads in its Damaged handler and hands to
// its motor; flashes and sounds subscribe to the same event. Death flips IsAlive and raises Died
// once — the game decides what a dead sentry does next (play out, return to its pool).
//
// Register with the probe where the game wires its harness:
//   GameProbe.Register("health", () => health.Current);
//   GameProbe.Count("damageEvents", () => health.DamageEvents);
using System;
using UnityEngine;

[DisallowMultipleComponent]
public sealed class Health : MonoBehaviour, IDamageable
{
    [Tooltip("CombatTeam.Neutral 0, Runner 1, Sentry 2. An attack of the same team is refused.")]
    public int team = CombatTeam.Runner;
    [Min(1)] public int max = 3;
    [Tooltip("Seconds of invincibility after a hit that lands. 0.6 for the runner; 0 for a sentry " +
             "that is meant to be juggled — then only the attacker's hit list stops a double hit.")]
    [Min(0f)] public float invincibleSeconds = 0.6f;

    /// <summary>Raised once per hit that lands, after Current changed and before Died.</summary>
    public event Action<DamageInfo> Damaged;
    /// <summary>Raised once, by the hit that takes Current to 0. Not raised again until Revive.</summary>
    public event Action<DamageInfo> Died;
    /// <summary>Raised when a hit is refused for invincibility — a place for a "blocked" tick.</summary>
    public event Action<DamageInfo> Refused;

    public int Current { get; private set; }
    public int Team => team;
    public bool IsAlive => Current > 0;
    /// <summary>True while a hit would be refused for invincibility.</summary>
    public bool Invincible => Time.fixedTime < _invincibleUntil;
    /// <summary>Seconds of invincibility left, for presentation that blinks the sprite.</summary>
    public float InvincibleRemaining => Mathf.Max(0f, _invincibleUntil - Time.fixedTime);
    /// <summary>Hits that landed since the last Revive. A journey asserts on this.</summary>
    public int DamageEvents { get; private set; }
    /// <summary>Hits refused for invincibility since the last Revive.</summary>
    public int RefusedEvents { get; private set; }
    public DamageInfo LastHit { get; private set; }

    // Combat is counted on the fixed clock: hitboxes query in FixedUpdate, so a timer on
    // Time.time would be a different length depending on where in the frame the hit arrived.
    float _invincibleUntil = float.NegativeInfinity;

    void Awake() => Current = max;

    public bool TakeDamage(in DamageInfo info)
    {
        if (!IsAlive || info.amount <= 0) return false;
        if (!CombatTeam.CanDamage(info.team, team)) return false;
        if (Invincible && !info.Has(DamageTags.IgnoreInvincibility))
        {
            RefusedEvents++;
            Refused?.Invoke(info);
            return false;
        }

        // State first, events last: a handler that reads Current or IsAlive sees the result.
        Current = Mathf.Max(0, Current - info.amount);
        DamageEvents++;
        LastHit = info;
        if (invincibleSeconds > 0f) _invincibleUntil = Time.fixedTime + invincibleSeconds;

        Damaged?.Invoke(info);
        if (Current == 0) Died?.Invoke(info);
        return true;
    }

    /// <summary>Invincibility from the game's own rules: a dash, a respawn, a scripted moment.
    /// Extends the timer, never shortens it.</summary>
    public void GrantInvincibility(float seconds)
        => _invincibleUntil = Mathf.Max(_invincibleUntil, Time.fixedTime + seconds);

    public void Heal(int amount)
    {
        if (!IsAlive || amount <= 0) return;
        Current = Mathf.Min(max, Current + amount);
    }

    /// <summary>Back to full, alive, counters cleared. Call it when a pooled object is taken out
    /// again; OnEnable does not do it, so a sentry switched off mid-fight keeps its hearts.</summary>
    public void Revive()
    {
        Current = max;
        DamageEvents = 0;
        RefusedEvents = 0;
        LastHit = default;
        _invincibleUntil = float.NegativeInfinity;
    }
}
