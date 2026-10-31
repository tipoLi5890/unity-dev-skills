// SpringSolver — the math of one spring-bone substep, with no scene in it: Verlet, the pull back
// to the animated pose, sphere and capsule push-out, the angle clamp and the exact bone length.
// SpringChain calls it; the EditMode tests drive it through SecondaryMotionSystem.Simulate.
//
// Units: stiffness and drag are fractions per 1/60 s. PerSubstep converts them to the substep
// length, so a chain settles the same way at 30, 60 or 144 frames a second.
using UnityEngine;

namespace UnityDev.SecondaryMotion
{
    public static class SpringSolver
    {
        /// <summary>The rate the per-1/60 s parameters are written for.</summary>
        public const float ReferenceRate = 60f;

        const float Tiny = 1e-12f;

        /// <summary>A fraction per 1/60 s as the same fraction per substep of h seconds:
        /// 1 - (1 - x)^(h * 60). 0 stays 0, 1 stays 1.</summary>
        public static float PerSubstep(float perSixtieth, float h)
        {
            float x = Mathf.Clamp01(perSixtieth);
            if (x >= 1f) return 1f;
            return 1f - Mathf.Pow(1f - x, h * ReferenceRate);
        }

        /// <summary>One Verlet step. carry moves the particle and its history together (the part of
        /// the body's motion the chain follows without lag).</summary>
        public static void Integrate(ref Vector3 p, ref Vector3 prev, Vector3 accel, float h,
                                     float dragH, Vector3 carry)
        {
            Vector3 v = (p - prev) * (1f - dragH);
            prev = p + carry;
            p = p + carry + v + accel * (h * h);
        }

        /// <summary>Pull toward the animated segment hung from the simulated parent.</summary>
        public static Vector3 Pull(Vector3 p, Vector3 parentSim, Vector3 animatedSegment, float stiffH)
        {
            Vector3 q = parentSim + animatedSegment;
            return p + (q - p) * stiffH;
        }

        public static Vector3 ClosestOnSegment(Vector3 a, Vector3 b, Vector3 p)
        {
            Vector3 ab = b - a;
            float len2 = ab.sqrMagnitude;
            if (len2 < Tiny) return a;
            float t = Mathf.Clamp01(Vector3.Dot(p - a, ab) / len2);
            return a + ab * t;
        }

        /// <summary>Pushes p out of a capsule (a == b: a sphere) of radius r. True when it moved.</summary>
        public static bool PushOut(ref Vector3 p, Vector3 a, Vector3 b, float r)
        {
            Vector3 c = ClosestOnSegment(a, b, p);
            Vector3 d = p - c;
            float d2 = d.sqrMagnitude;
            if (d2 >= r * r) return false;
            if (d2 < Tiny)
            {
                // Dead centre: leave along any axis perpendicular to the capsule.
                Vector3 axis = b - a;
                d = axis.sqrMagnitude < Tiny ? Vector3.up : Vector3.Cross(axis, Vector3.up);
                if (d.sqrMagnitude < Tiny) d = Vector3.Cross(axis, Vector3.right);
                d2 = d.sqrMagnitude;
            }
            p = c + d * (r / Mathf.Sqrt(d2));
            return true;
        }

        /// <summary>Distance from p to the surface of a capsule (negative inside).</summary>
        public static float SurfaceDistance(Vector3 p, Vector3 a, Vector3 b, float r)
        {
            return Vector3.Distance(p, ClosestOnSegment(a, b, p)) - r;
        }

        /// <summary>The segment parent → p turned toward the animated direction until the angle
        /// between them is at most maxRadians. Length is left to KeepLength.</summary>
        public static Vector3 ClampAngle(Vector3 parentSim, Vector3 p, Vector3 animatedSegment, float maxRadians)
        {
            Vector3 d = p - parentSim;
            float len = d.magnitude;
            if (len < 1e-6f || animatedSegment.sqrMagnitude < Tiny) return p;
            if (Vector3.Angle(animatedSegment, d) * Mathf.Deg2Rad <= maxRadians) return p;
            Vector3 dir = Vector3.RotateTowards(animatedSegment.normalized, d / len, maxRadians, 0f);
            return parentSim + dir * len;
        }

        /// <summary>p placed at exactly length from the parent, along parent → p; a zero-length
        /// direction falls back to the animated one, then to up, so nothing turns NaN.</summary>
        public static Vector3 KeepLength(Vector3 parentSim, Vector3 p, float length, Vector3 animatedSegment)
        {
            Vector3 d = p - parentSim;
            float m2 = d.sqrMagnitude;
            if (m2 < Tiny)
            {
                d = animatedSegment;
                m2 = d.sqrMagnitude;
                if (m2 < Tiny) { d = Vector3.up; m2 = 1f; }
            }
            return parentSim + d * (length / Mathf.Sqrt(m2));
        }

        public static bool IsFinite(Vector3 v)
        {
            return !(float.IsNaN(v.x) || float.IsNaN(v.y) || float.IsNaN(v.z) ||
                     float.IsInfinity(v.x) || float.IsInfinity(v.y) || float.IsInfinity(v.z));
        }
    }
}
