// Perception — what an agent knows about its target, bought cheaply: a vision cone as distance,
// then a dot product, then one line-of-sight cast; a per-step budget for those casts; hearing as
// events with a radius; and a memory of where the target was last seen.
//
// Drop into a Runtime assembly. No package needed. Nothing here is a MonoBehaviour and nothing
// here names a physics engine: the cast is asked for through ILineOfSight, so the same cone
// serves a 3D gate room and a 2D depot. SentryBrain.cs casts with Physics.Linecast when no
// ILineOfSight component is beside it; Perception2D.cs is the 2D answer.
//
//   SightResult r = cone.Covers(eye, facing, targetPoint, Vector3.up, tracking);   // no physics
//   if (r == SightResult.Seen)
//   {
//       if (!PerceptionBudget.TryTake()) return false;        // keep the last answer, ask next step
//       if (!sight.Clear(eye, targetPoint)) r = SightResult.Blocked;               // one cast
//   }
//
//   NoiseEvents.Emit(runner.position, 8f, team: 0);        // a launch, a dropped pickup, a gate opening
using System;
using UnityEngine;

public enum SightResult { NoTarget, OutOfRange, OutOfCone, OutOfTerritory, Blocked, Seen }

/// <summary>The one question that costs a physics query: is the segment free of cover?</summary>
public interface ILineOfSight
{
    bool Clear(Vector3 from, Vector3 to);
}

/// <summary>
/// A vision cone as numbers. Two sets: the cone that notices, and a wider one that keeps a target
/// already noticed — without the second, a runner on the cone's edge is seen and lost every tick.
/// </summary>
[Serializable]
public sealed class SightCone
{
    [Tooltip("Units. A target farther than this is not noticed. Keep it inside the camera's view.")]
    public float range = 6f;
    [Tooltip("Full cone angle in degrees, centred on the facing.")]
    public float angle = 70f;
    [Tooltip("Units. A target already tracked is kept out to this range.")]
    public float keepRange = 7.5f;
    [Tooltip("Full cone angle in degrees for a target already tracked.")]
    public float keepAngle = 100f;
    [Tooltip("Units. Inside this the angle is ignored: a runner touching the sentry's back is noticed.")]
    public float closeRange = 1f;

    /// <summary>
    /// Distance, then angle — no physics. Seen means "inside the cone": the caller then spends one
    /// cast to find out whether cover is in the way.
    /// </summary>
    /// <param name="planeNormal">The play plane's normal: Vector3.up for 3D ground, Vector3.forward
    /// for 2D on XY. Height along it is ignored, so a runner on a step is not above the cone.
    /// Vector3.zero tests a true 3D cone.</param>
    /// <param name="tracking">True when the target is already noticed: the keep numbers apply.</param>
    public SightResult Covers(Vector3 eye, Vector3 forward, Vector3 target, Vector3 planeNormal, bool tracking)
    {
        Vector3 to = target - eye;
        if (planeNormal != Vector3.zero)
        {
            to -= planeNormal * Vector3.Dot(to, planeNormal);
            forward -= planeNormal * Vector3.Dot(forward, planeNormal);
        }

        float reach = tracking ? keepRange : range;
        float sqr = to.sqrMagnitude;
        if (sqr > reach * reach) return SightResult.OutOfRange;
        if (sqr <= closeRange * closeRange) return SightResult.Seen;

        float full = tracking ? keepAngle : angle;
        if (full >= 360f) return SightResult.Seen;
        // Compare cosines: no acos, no angle in degrees, one square root.
        float cosHalf = Mathf.Cos(full * 0.5f * Mathf.Deg2Rad);
        float dot = Vector3.Dot(forward.normalized, to / Mathf.Sqrt(sqr));
        return dot >= cosHalf ? SightResult.Seen : SightResult.OutOfCone;
    }
}

/// <summary>
/// A cap on line-of-sight casts per simulation step, shared by every agent. An agent that is
/// refused keeps what it knew and asks again on the next step, so a crowd spreads its casts over
/// several steps instead of spending them all on one.
/// </summary>
public static class PerceptionBudget
{
    /// <summary>Casts allowed per step. 8 serves about forty agents deciding at 10 Hz on a 50 Hz step.</summary>
    public static int CastsPerStep = 8;

    /// <summary>Casts granted in the current step.</summary>
    public static int Used { get; private set; }
    /// <summary>Requests refused since the last Reset. A number that climbs every step means the budget is too small for the crowd.</summary>
    public static int Deferred { get; private set; }

    static float _stamp = -1f;
    static bool _stampFixed;

    public static bool TryTake()
    {
        bool inFixed = Time.inFixedTimeStep;
        float stamp = inFixed ? Time.fixedTime : Time.time;
        if (stamp != _stamp || inFixed != _stampFixed)
        {
            _stamp = stamp;
            _stampFixed = inFixed;
            Used = 0;
        }
        if (Used >= CastsPerStep) { Deferred++; return false; }
        Used++;
        return true;
    }

    // Statics survive entering play mode when domain reload is off.
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    public static void Reset()
    {
        Used = 0;
        Deferred = 0;
        _stamp = -1f;
    }
}

/// <summary>Where and when the target was last perceived. A plain value: the blackboard holds one.</summary>
[Serializable]
public struct TargetMemory
{
    public bool has;
    public Vector3 position;
    public float seenAt;

    public void Remember(Vector3 where, float now)
    {
        has = true;
        position = where;
        seenAt = now;
    }

    public float Age(float now) => has ? now - seenAt : float.PositiveInfinity;

    /// <summary>True when there is nothing remembered, or it is older than <paramref name="seconds"/>.</summary>
    public bool Expired(float now, float seconds) => !has || now - seenAt >= seconds;

    public void Forget() => has = false;
}

public struct NoiseEvent
{
    public Vector3 position;
    /// <summary>Units. Listeners farther than this do not hear it.</summary>
    public float radius;
    /// <summary>Who made it. A listener ignores its own team.</summary>
    public int team;
}

/// <summary>
/// Hearing is an event with a radius, never a poll: the thing that makes the sound says so once,
/// and each listener does one distance test. No cast, no per-frame cost.
/// </summary>
public static class NoiseEvents
{
    public static event Action<NoiseEvent> Emitted;

    public static void Emit(Vector3 position, float radius, int team = 0)
    {
        Emitted?.Invoke(new NoiseEvent { position = position, radius = radius, team = team });
    }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void Reset() => Emitted = null;
}
