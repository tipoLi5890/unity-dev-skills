// DamageInfo — the one message an attack hands to whatever it hit, and the interface that
// receives it.
//
// Drop into a Runtime assembly. No package needed, and no physics type is named here, so the
// same file serves a 2D and a 3D project. Health.cs, Hitbox3D.cs, Hitbox2D.cs, Projectile3D.cs
// and Projectile2D.cs all depend on it.
//
// It is a struct on purpose: it is filled on the stack by the attack, passed by reference with
// 'in', and never stored by the receiver beyond the call. A class here is one allocation per hit.
using System;
using UnityEngine;

/// <summary>What kind of hit this is. The receiver and the presentation read it; the attack sets it.</summary>
[Flags]
public enum DamageTags
{
    None = 0,
    Melee = 1 << 0,
    Projectile = 1 << 1,
    Hazard = 1 << 2,
    /// <summary>The receiver staggers even when its own rules would shrug the hit off.</summary>
    Heavy = 1 << 3,
    /// <summary>Lands through invincibility: a kill plane, a crusher, a scripted hit.</summary>
    IgnoreInvincibility = 1 << 4,
}

/// <summary>Team numbers used by the files of this skill. Any int works; these are the defaults.</summary>
public static class CombatTeam
{
    /// <summary>Hits every team and is hit by every team: spikes, a crusher, a falling crate.</summary>
    public const int Neutral = 0;
    public const int Runner = 1;
    public const int Sentry = 2;

    /// <summary>The one friendly-fire rule. Neutral damages everybody, a team never damages itself.</summary>
    public static bool CanDamage(int attackerTeam, int targetTeam)
        => attackerTeam == Neutral || targetTeam == Neutral || attackerTeam != targetTeam;
}

public struct DamageInfo
{
    /// <summary>Hearts, or hit points. Whole numbers: nothing ever compares a health to 0.0001.</summary>
    public int amount;
    /// <summary>The attacker's root — the runner, not the hitbox on its arm. May be null for a hazard.</summary>
    public GameObject source;
    public int team;
    /// <summary>World position of the contact: where the spark goes.</summary>
    public Vector3 point;
    /// <summary>Unit vector the hit travels along, attacker towards target. In 2D, z is 0.</summary>
    public Vector3 direction;
    /// <summary>Launch speed in units/s along <see cref="direction"/>. 0 leaves the target where it is.</summary>
    public float knockback;
    /// <summary>Seconds without control after the hit. The controller applies it with the push.</summary>
    public float stun;
    public DamageTags tags;
    /// <summary>Which swing this is, from the hitbox that made it. 0 for a projectile or a hazard.</summary>
    public int swingId;

    public bool Has(DamageTags tag) => (tags & tag) != 0;

    /// <summary>The push the receiver's controller hands to its motor.</summary>
    public Vector3 KnockbackVelocity => direction * knockback;
}

/// <summary>
/// Anything that can be hit. Resolve it from a hurtbox collider with
/// GetComponentInParent&lt;IDamageable&gt;() — the hurtboxes are children, the receiver is the root.
/// </summary>
public interface IDamageable
{
    int Team { get; }
    bool IsAlive { get; }

    /// <summary>True when the damage was applied. False when it was refused — dead, own team,
    /// invincible, zero amount — and then nothing changed and no Damaged or Died was raised.</summary>
    bool TakeDamage(in DamageInfo info);
}
