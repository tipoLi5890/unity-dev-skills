// A ball you integrate yourself, with no PhysX: quadratic drag, Magnus lift, spin decay, swept
// contact by bisection on a distance function, and an impulse bounce that couples spin and friction.
// Pure C# (no UnityEngine), double precision, only + − × ÷ and sqrt in the per-step path, so the
// same inputs give the same bits on the same build. Reference: unity-physics-3d ->
// reference/own-ball-physics.md. Numbers are a tennis ball's; every one is a parameter.
//
//   var world = new List<IBallCollider> { new GroundPlane(), new BoxShape(center, half, wood) };
//   var s = new BallState(pos, vel, BallFlight.TopspinAxisSpin(dir, 2500));
//   for (int i = 0; i < substepsPerTick; i++) BallFlight.Substep(ref s, p, world, dt, contacts);
//
// Do not tunnel: one substep must move less than the ball's diameter at the highest speed you allow.
// 120 Hz × 8 substeps = 1.04 ms; at 60 m/s that is 6.25 cm against a 6.7 cm diameter.
using System;
using System.Collections.Generic;

namespace Game.Sim.Ball
{
    public readonly struct Vec3d
    {
        public readonly double X, Y, Z;
        public Vec3d(double x, double y, double z) { X = x; Y = y; Z = z; }
        public static readonly Vec3d Zero = new Vec3d(0, 0, 0);
        public static readonly Vec3d Up = new Vec3d(0, 1, 0);
        public static Vec3d operator +(Vec3d a, Vec3d b) => new Vec3d(a.X + b.X, a.Y + b.Y, a.Z + b.Z);
        public static Vec3d operator -(Vec3d a, Vec3d b) => new Vec3d(a.X - b.X, a.Y - b.Y, a.Z - b.Z);
        public static Vec3d operator -(Vec3d a) => new Vec3d(-a.X, -a.Y, -a.Z);
        public static Vec3d operator *(Vec3d a, double k) => new Vec3d(a.X * k, a.Y * k, a.Z * k);
        public static Vec3d operator /(Vec3d a, double k) => new Vec3d(a.X / k, a.Y / k, a.Z / k);
        public static double Dot(Vec3d a, Vec3d b) => a.X * b.X + a.Y * b.Y + a.Z * b.Z;
        public static Vec3d Cross(Vec3d a, Vec3d b) =>
            new Vec3d(a.Y * b.Z - a.Z * b.Y, a.Z * b.X - a.X * b.Z, a.X * b.Y - a.Y * b.X);
        public static Vec3d Lerp(Vec3d a, Vec3d b, double t) => a + (b - a) * t;
        public double Length => Math.Sqrt(X * X + Y * Y + Z * Z);
        public override string ToString() => $"({X:0.####}, {Y:0.####}, {Z:0.####})";
    }

    public struct BallState
    {
        public Vec3d Pos, Vel;
        /// <summary>Angular velocity, rad/s, right-hand rule.</summary>
        public Vec3d Spin;
        public BallState(Vec3d pos, Vec3d vel, Vec3d spin) { Pos = pos; Vel = vel; Spin = spin; }
    }

    public sealed class BallParams
    {
        public double Mass = 0.057, Radius = 0.0335, AirDensity = 1.21, DragCoeff = 0.55;
        /// <summary>Lift coefficient C_L = 1 / (2 + |v| / (r|ω|)), clamped to this.</summary>
        public double LiftMax = 0.35;
        /// <summary>Spin decay time constant: ω *= (1 − dt/τ) per step (no Exp in the sim).</summary>
        public double SpinDecayTau = 4.0;
        public double Gravity = 9.81;
        /// <summary>Normal speed below which a contact is resting, not a bounce (no event, e = 0).</summary>
        public double RestingSpeed = 0.25;
        public double Area => Math.PI * Radius * Radius;
        /// <summary>a_drag = −DragK·|v|·v. About 0.0206 /m for a tennis ball.</summary>
        public double DragK => 0.5 * AirDensity * DragCoeff * Area / Mass;
        public double MagnusK => 0.5 * AirDensity * Area / Mass;
        /// <summary>Hollow sphere: I/m = ⅔r². A solid ball is ⅖r².</summary>
        public double InertiaPerMass => 2.0 / 3.0 * Radius * Radius;
    }

    public sealed class SurfaceMaterial
    {
        public string Name = "default";
        /// <summary>e(v_n) = Restitution − Slope·(v_n − RefSpeed), clamped to [Min, Max].</summary>
        public double Restitution = 0.5, RestitutionSlope = 0, RestitutionRefSpeed = 10, RestitutionMin = 0, RestitutionMax = 1;
        public double Friction = 0.4;
        public double RestitutionAt(double vn) =>
            Math.Max(RestitutionMin, Math.Min(RestitutionMax, Restitution - RestitutionSlope * (vn - RestitutionRefSpeed)));
        /// <summary>A hard court: e 0.78 − 0.0035(v_n − 10) within [0.70, 0.80], μ 0.55.</summary>
        public static SurfaceMaterial HardCourt() => new SurfaceMaterial
        { Name = "court", Restitution = 0.78, RestitutionSlope = 0.0035, RestitutionMin = 0.70, RestitutionMax = 0.80, Friction = 0.55 };
    }

    public interface IBallCollider
    {
        SurfaceMaterial Material { get; }
        /// <summary>Distance from p to the surface (negative inside).</summary>
        double Distance(Vec3d p);
        /// <summary>Outward unit normal at the surface point nearest p.</summary>
        Vec3d Normal(Vec3d p);
    }

    public sealed class GroundPlane : IBallCollider
    {
        public SurfaceMaterial Material { get; set; } = SurfaceMaterial.HardCourt();
        public double Height;
        public double Distance(Vec3d p) => p.Y - Height;
        public Vec3d Normal(Vec3d p) => Vec3d.Up;
    }

    /// <summary>Axis-aligned box. Rotate the point into the box's frame first if you need oriented boxes.</summary>
    public sealed class BoxShape : IBallCollider
    {
        public SurfaceMaterial Material { get; set; } = new SurfaceMaterial();
        public Vec3d Center, Half;
        public BoxShape(Vec3d center, Vec3d half, SurfaceMaterial m = null) { Center = center; Half = half; if (m != null) Material = m; }
        public double Distance(Vec3d p)
        {
            Vec3d d = p - Center;
            double qx = Math.Abs(d.X) - Half.X, qy = Math.Abs(d.Y) - Half.Y, qz = Math.Abs(d.Z) - Half.Z;
            var outside = new Vec3d(Math.Max(qx, 0), Math.Max(qy, 0), Math.Max(qz, 0));
            return outside.Length + Math.Min(Math.Max(qx, Math.Max(qy, qz)), 0);
        }
        public Vec3d Normal(Vec3d p)
        {
            Vec3d d = p - Center;
            double qx = Math.Abs(d.X) - Half.X, qy = Math.Abs(d.Y) - Half.Y, qz = Math.Abs(d.Z) - Half.Z;
            if (qx >= qy && qx >= qz) return new Vec3d(Math.Sign(d.X), 0, 0);
            if (qy >= qz) return new Vec3d(0, Math.Sign(d.Y), 0);
            return new Vec3d(0, 0, Math.Sign(d.Z));
        }
    }

    public struct BallContact
    {
        public IBallCollider Collider;
        public Vec3d Pos, Normal, VelBefore, VelAfter;
        public double ImpactSpeed;
        /// <summary>Seconds into the substep. Events carry their own time: a frame may show a later moment.</summary>
        public double TimeInStep;
    }

    public static class BallFlight
    {
        public const double RpmToRadS = 2.0 * Math.PI / 60.0;
        public const int MaxContactsPerSubstep = 4;

        public static Vec3d Acceleration(Vec3d vel, Vec3d spin, BallParams p)
        {
            Vec3d a = new Vec3d(0, -p.Gravity, 0);
            double speed = vel.Length;
            if (speed < 1e-9) return a;
            a = a - vel * (p.DragK * speed);
            double w = spin.Length;
            if (w > 1e-6)
            {
                double cl = Math.Min(p.LiftMax, 1.0 / (2.0 + speed / (p.Radius * w)));
                a = a + Vec3d.Cross(spin / w, vel) * (p.MagnusK * cl * speed);
            }
            return a;
        }

        /// <summary>Free flight for dt (midpoint method). Prediction and play must call this with the same dt.</summary>
        public static void Integrate(ref BallState s, BallParams p, double dt)
        {
            Vec3d a1 = Acceleration(s.Vel, s.Spin, p);
            Vec3d vMid = s.Vel + a1 * (0.5 * dt);
            Vec3d a2 = Acceleration(vMid, s.Spin, p);
            s.Pos = s.Pos + vMid * dt;
            s.Vel = s.Vel + a2 * dt;
            s.Spin = s.Spin * Math.Max(0.0, 1.0 - dt / p.SpinDecayTau);
        }

        /// <summary>Topspin (rpm &gt; 0) or backspin (rpm &lt; 0) for a ball travelling along horizontal direction dir.</summary>
        public static Vec3d TopspinAxisSpin(Vec3d dir, double rpm)
        {
            var flat = new Vec3d(dir.X, 0, dir.Z);
            double len = flat.Length;
            if (len < 1e-12) return Vec3d.Zero;
            return Vec3d.Cross(Vec3d.Up, flat / len) * (rpm * RpmToRadS);
        }

        /// <summary>
        /// Impulse response at a contact with outward normal n. Normal impulse (1+e)·v_n; tangential impulse
        /// is the smaller of "what brings the contact point to pure rolling" and μ·J_n, applied to velocity
        /// AND spin. Topspin kicks forward, backspin checks, and kinetic plus rotational energy never grows.
        /// </summary>
        public static void Bounce(ref BallState s, Vec3d n, SurfaceMaterial m, BallParams p)
        {
            double vn = Vec3d.Dot(s.Vel, n);
            if (vn >= 0) return;
            double impact = -vn;
            double e = impact < p.RestingSpeed ? 0 : m.RestitutionAt(impact);
            double jn = (1 + e) * impact;                       // per unit mass
            Vec3d rc = n * (-p.Radius);                         // centre to contact point
            Vec3d u = s.Vel + Vec3d.Cross(s.Spin, rc);          // contact-point velocity
            Vec3d ut = u - n * Vec3d.Dot(u, n);
            double utLen = ut.Length;
            Vec3d dv = n * jn;
            if (utLen > 1e-9)
            {
                double iPerM = p.InertiaPerMass;
                double rollFactor = 1.0 + p.Radius * p.Radius / iPerM;   // 2.5 for a hollow sphere
                double jt = Math.Min(utLen / rollFactor, m.Friction * jn);
                Vec3d jtVec = ut * (-jt / utLen);
                dv = dv + jtVec;
                s.Spin = s.Spin + Vec3d.Cross(rc, jtVec) / iPerM;
            }
            s.Vel = s.Vel + dv;
        }

        /// <summary>
        /// One substep: integrate, find the EARLIEST contact over every collider (bisection on the distance
        /// function, 24 halvings), re-integrate from the step start to the contact time, bounce, push out of
        /// overlap, and spend the remaining time. At most <see cref="MaxContactsPerSubstep"/> contacts.
        /// A zero-thickness surface (a net plane) needs its own crossing test: a distance function cannot
        /// see a plane the ball jumps across between two samples.
        /// </summary>
        public static void Substep(ref BallState s, BallParams p, IReadOnlyList<IBallCollider> world, double dt,
                                   List<BallContact> contacts = null)
        {
            double r = p.Radius, remaining = dt, consumed = 0;
            for (int n = 0; n <= MaxContactsPerSubstep && remaining > 1e-9; n++)
            {
                BallState s0 = s, s1 = s;
                Integrate(ref s1, p, remaining);
                IBallCollider hit = null;
                double hitF = 2;
                for (int i = 0; i < world.Count; i++)
                {
                    var c = world[i];
                    if (c.Distance(s1.Pos) >= r && c.Distance(Vec3d.Lerp(s0.Pos, s1.Pos, 0.5)) >= r) continue;
                    double f;
                    if (c.Distance(s0.Pos) < r) f = 0;
                    else
                    {
                        double lo = 0, hi = 1;
                        for (int k = 0; k < 24; k++)
                        {
                            double mid = 0.5 * (lo + hi);
                            if (c.Distance(Vec3d.Lerp(s0.Pos, s1.Pos, mid)) < r) hi = mid; else lo = mid;
                        }
                        f = lo;
                    }
                    if (f < hitF) { hitF = f; hit = c; }
                }
                if (hit == null) { s = s1; break; }

                double tHit = hitF * remaining;
                BallState sc = s0;
                if (tHit > 0) Integrate(ref sc, p, tHit);    // exact contact state, same path as prediction
                Vec3d normal = hit.Normal(sc.Pos);
                double vn = Vec3d.Dot(sc.Vel, normal);
                if (vn < 0)
                {
                    Vec3d before = sc.Vel;
                    Bounce(ref sc, normal, hit.Material, p);
                    if (contacts != null && -vn >= p.RestingSpeed)    // rolling contact is not an event
                        contacts.Add(new BallContact { Collider = hit, Pos = sc.Pos, Normal = normal, ImpactSpeed = -vn,
                                                       VelBefore = before, VelAfter = sc.Vel, TimeInStep = consumed + tHit });
                }
                double d = hit.Distance(sc.Pos);
                if (d < r) sc.Pos = sc.Pos + normal * (r - d + 1e-7);
                s = sc;
                consumed += tHit;
                remaining -= tHit;
                if (tHit <= 1e-9 && vn >= 0)
                {
                    // Touching but not moving in: finish the step without searching again, or it sticks.
                    Integrate(ref s, p, remaining);
                    double d2 = hit.Distance(s.Pos);
                    if (d2 < r) s.Pos = s.Pos + normal * (r - d2 + 1e-7);
                    break;
                }
            }
        }
    }
}
