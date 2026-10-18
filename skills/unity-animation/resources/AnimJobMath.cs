// AnimJobMath — the continuity tools Animation Jobs need: a critically damped spring, soft
// reach limits, a C1 bump, and a two-bone solver that bends about a stored hinge axis.
//
// Drop into a Runtime folder. Every function is usable inside IAnimationJob.ProcessAnimation
// (no managed allocation). The rule they serve: an IK target or weight must be continuous in
// position AND velocity, or the joint it drives pops for one frame
// (reference/foot-lock-and-prop-ik.md §1).
using UnityEngine;
using UnityEngine.Animations;

public static class AnimJobMath
{
    // ── Smoothing ────────────────────────────────────────────────────────────────────────────

    /// <summary>
    /// Critically damped spring toward a fixed target, advanced exactly by dt (stable for any dt).
    /// Position and velocity stay continuous when the target jumps; only acceleration jumps.
    /// omega in rad/s: about 4.7 / omega seconds to close 99% of the gap.
    /// To release a lock smoothly, start x at (lock − source) and v at −sourceVelocity, target 0.
    /// </summary>
    public static void Spring(ref float x, ref float v, float target, float omega, float dt)
    {
        if (dt <= 0f) return;
        float y = x - target, e = Mathf.Exp(-omega * dt), j = v + omega * y;
        x = target + (y + j * dt) * e;
        v = (v - omega * j * dt) * e;
    }

    public static void Spring(ref Vector3 x, ref Vector3 v, Vector3 target, float omega, float dt)
    {
        if (dt <= 0f) return;
        Vector3 y = x - target, j = v + omega * y;
        float e = Mathf.Exp(-omega * dt);
        x = target + (y + j * dt) * e;
        v = (v - (omega * dt) * j) * e;
    }

    /// <summary>Smoothstep on [0, 1].</summary>
    public static float Smooth(float u) { u = Mathf.Clamp01(u); return u * u * (3f - 2f * u); }

    /// <summary>C1 bump: 0 at u = 0 and 1 with zero slope, 1 at u = 0.5 (16u²(1−u)²). Step lifts, hops.</summary>
    public static float Bump(float u) { u = Mathf.Clamp01(u); float a = u * (1f - u); return 16f * a * a; }

    // ── Reach limits ─────────────────────────────────────────────────────────────────────────

    /// <summary>
    /// Soft reach: d unchanged up to softFrom × L, then an exponential approach to L.
    /// A target moving near full extension no longer snaps the middle joint. softFrom = 1 disables.
    /// </summary>
    public static float SoftReach(float d, float L, float softFrom)
    {
        if (softFrom >= 1f) return d;
        float s0 = softFrom * L, band = (1f - softFrom) * L;
        if (d <= s0 || band <= 1e-6f) return d;
        return s0 + band * (1f - Mathf.Exp(-(d - s0) / band));
    }

    /// <summary>
    /// Soft reach relative to the clip: softening starts at max(softFrom × L, dClip) and approaches
    /// max(reachFrac × L, dClip). With the target at the clip's own position the output equals the
    /// clip, so turning IK on or off never bends a limb the clip held straight.
    /// </summary>
    public static float SoftReachRel(float d, float dClip, float L, float softFrom, float reachFrac)
    {
        float top = Mathf.Max(reachFrac * L, Mathf.Min(dClip, L));
        float s0 = Mathf.Min(Mathf.Max(softFrom * L, dClip), top);
        if (d <= s0) return d;
        float band = top - s0;
        if (band <= 1e-6f) return s0;
        return s0 + band * (1f - Mathf.Exp(-(d - s0) / band));
    }

    /// <summary>Linear to `linear` degrees, then a smooth saturation toward `max` degrees (a wrist limit).</summary>
    public static float SoftAngle(float deg, float linear, float max)
    {
        float a = Mathf.Abs(deg);
        if (a <= linear || max <= linear) return deg;
        return Mathf.Sign(deg) * (linear + (max - linear) * (1f - Mathf.Exp(-(a - linear) / (max - linear))));
    }

    // ── Hinge axis ───────────────────────────────────────────────────────────────────────────

    /// <summary>
    /// The hinge axis of a bent limb in the upper bone's local frame (u = upper bone vector,
    /// l = lower bone vector, world). Returns zero when the limb bends less than minDeg.
    /// Measure it once from a pose where the limb is clearly bent (a ready stance), never per frame.
    /// </summary>
    public static Vector3 HingeOf(Quaternion upperRot, Vector3 u, Vector3 l, float minDeg)
    {
        if (Vector3.Angle(u, l) < minDeg) return Vector3.zero;
        var n = Vector3.Cross(u, l);
        return n.sqrMagnitude > 1e-12f ? Quaternion.Inverse(upperRot) * n.normalized : Vector3.zero;
    }

    /// <summary>
    /// Refine a stored hinge axis slowly from the clip's own bend: only when the bend exceeds 25°,
    /// and never toward a candidate more than 45° away (that is a flip, not a refinement).
    /// </summary>
    public static Vector3 RefineHinge(Vector3 hinge, Quaternion upperRot, Vector3 u, Vector3 l, float rate = 0.05f)
    {
        var m = HingeOf(upperRot, u, l, 25f);
        if (m == Vector3.zero) return hinge;
        if (hinge.sqrMagnitude < 0.5f) return m;
        if (Vector3.Angle(hinge, m) > 45f) return hinge;
        return Vector3.Slerp(hinge, m, rate).normalized;
    }

    // ── Two-bone solvers ─────────────────────────────────────────────────────────────────────

    /// <summary>
    /// Two-bone IK bending about a hinge axis (knee, elbow). The lower bone rotates about the axis
    /// until the root-to-tip distance equals the softened target distance, always to the bending
    /// side; then the upper bone takes the minimal rotation onto the target (twist follows the clip).
    /// While the clip bends 8–30° or more, its own bend plane is blended in, so a bent limb keeps
    /// the clip's plane and a nearly straight one uses the stored axis (no flip from noise).
    /// relativeToClip: soften with SoftReachRel (arms whose IK weight goes to 0), else SoftReach (legs).
    /// Returns false when degenerate; call TwoBoneHint instead.
    /// </summary>
    public static bool TwoBoneHinge(AnimationStream s, TransformStreamHandle root, TransformStreamHandle mid, TransformStreamHandle tip,
                                    Vector3 target, Vector3 hingeLocal, float softFrom, float reachFrac, bool relativeToClip)
    {
        Vector3 a = root.GetPosition(s), b = mid.GetPosition(s), c = tip.GetPosition(s);
        Vector3 u = b - a, l = c - b, at = target - a;
        float d0 = at.magnitude;
        if (u.sqrMagnitude < 1e-10f || l.sqrMagnitude < 1e-10f || d0 < 1e-5f) return false;
        Vector3 axis = root.GetRotation(s) * hingeLocal;
        if (axis.sqrMagnitude < 1e-8f) return false;
        axis.Normalize();

        Vector3 nClip = Vector3.Cross(u, l);
        float bend = Vector3.Angle(u, l);
        if (nClip.sqrMagnitude > 1e-12f)
        {
            nClip.Normalize();
            float wf = Smooth((bend - 8f) / 22f) * Smooth(Vector3.Dot(nClip, axis) / 0.5f);
            if (wf > 0f) { var m = Vector3.Lerp(axis, nClip, wf); if (m.sqrMagnitude > 1e-8f) axis = m.normalized; }
        }
        Vector3 un = u.normalized;
        axis -= Vector3.Dot(axis, un) * un;
        if (axis.sqrMagnitude < 1e-8f) return false;
        axis.Normalize();

        // |c(θ) − a|² = K + 2(A + B cosθ + C sinθ), θ = rotation of the lower bone about the axis
        Vector3 lPar = Vector3.Dot(l, axis) * axis, lPerp = l - lPar;
        float A = Vector3.Dot(u, lPar), B = Vector3.Dot(u, lPerp), C = Vector3.Dot(u, Vector3.Cross(axis, lPerp));
        float R = Mathf.Sqrt(B * B + C * C);
        if (R < 1e-6f) return false;
        float K = u.sqrMagnitude + l.sqrMagnitude;
        float dMax = Mathf.Sqrt(Mathf.Max(0f, K + 2f * (A + R)));
        float dMin = Mathf.Sqrt(Mathf.Max(0f, K + 2f * (A - R)));
        float want = relativeToClip
            ? SoftReachRel(d0, (c - a).magnitude, dMax, softFrom, reachFrac)
            : SoftReach(d0, dMax * reachFrac, softFrom / reachFrac);
        want = Mathf.Clamp(want, dMin + 1e-4f, dMax);
        float x = Mathf.Clamp((0.5f * (want * want - K) - A) / R, -1f, 1f);
        float th = Mathf.Atan2(C, B) + Mathf.Acos(x);
        if (th > Mathf.PI) th -= 2f * Mathf.PI; else if (th < -Mathf.PI) th += 2f * Mathf.PI;
        if (Mathf.Abs(th) > 1e-6f) mid.SetRotation(s, Quaternion.AngleAxis(th * Mathf.Rad2Deg, axis) * mid.GetRotation(s));
        Vector3 c1 = tip.GetPosition(s) - a;
        if (c1.sqrMagnitude > 1e-10f) root.SetRotation(s, Quaternion.FromToRotation(c1, at) * root.GetRotation(s));
        return true;
    }

    /// <summary>
    /// Classic two-bone IK with a hint position: bend plane through root, target and hint, middle
    /// joint placed by the cosine rule, minimal rotations. The fallback while no hinge axis exists;
    /// for a knee, pass root + body forward as the hint (never the toe direction, which flips).
    /// </summary>
    public static void TwoBoneHint(AnimationStream s, TransformStreamHandle root, TransformStreamHandle mid, TransformStreamHandle tip,
                                   Vector3 target, Vector3 hint, float softFrom = 1f, float reachFrac = 0.999f)
    {
        Vector3 a = root.GetPosition(s), b = mid.GetPosition(s), c = tip.GetPosition(s);
        Vector3 ab = b - a, bc = c - b, at = target - a;
        float lab = ab.magnitude, lbc = bc.magnitude, d0 = at.magnitude;
        if (lab < 1e-5f || lbc < 1e-5f || d0 < 1e-5f) return;
        float want = SoftReach(d0, (lab + lbc) * reachFrac, softFrom);
        want = Mathf.Clamp(want, Mathf.Abs(lab - lbc) + 1e-3f, (lab + lbc) * reachFrac);
        Vector3 atn = at / d0;
        Vector3 nH = Vector3.Cross(at, hint - a), nF = Vector3.Cross(at, ab);
        Vector3 n = nH.sqrMagnitude > 1e-8f ? nH.normalized
                  : nF.sqrMagnitude > 1e-10f ? nF.normalized
                  : Vector3.Cross(atn, Mathf.Abs(atn.y) < 0.9f ? Vector3.up : Vector3.right).normalized;
        float cosA = Mathf.Clamp((lab * lab + want * want - lbc * lbc) / (2f * lab * want), -1f, 1f);
        float sinA = Mathf.Sqrt(Mathf.Max(0f, 1f - cosA * cosA));
        Vector3 perp = Vector3.Cross(n, atn);
        Vector3 bWant = a + (atn * cosA + perp * sinA) * lab;
        root.SetRotation(s, Quaternion.FromToRotation(ab, bWant - a) * root.GetRotation(s));
        Vector3 b1 = mid.GetPosition(s), c1 = tip.GetPosition(s), tWant = a + atn * want;
        if ((c1 - b1).sqrMagnitude > 1e-10f && (tWant - b1).sqrMagnitude > 1e-10f)
            mid.SetRotation(s, Quaternion.FromToRotation(c1 - b1, tWant - b1) * mid.GetRotation(s));
    }

    /// <summary>Yaw in degrees of a rotation's forward, about world up.</summary>
    public static float YawOf(Quaternion q)
    {
        var f = q * Vector3.forward;
        return Mathf.Atan2(f.x, f.z) * Mathf.Rad2Deg;
    }
}
