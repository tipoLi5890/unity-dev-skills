// MotionMetricsSampler — read-only motion quality metrics for PlayMode tests: foot slide per
// plant, plant speed, root against the simulation, root velocity jumps, pops (spikes in the final
// pose that the clip does not have), and contact timing. It reads transforms and delegates; it
// changes nothing.
//
// Drop into a Runtime (or test-support) folder. Register each character with a MotionSubject,
// then call Sample(Time.deltaTime) once per rendered frame AFTER the pose is final
// (yield return new WaitForEndOfFrame()). Record contacts with RecordContact. Print Lines(label)
// and assert on Summarize(). Definitions and the gates: reference/motion-metrics.md.
//
// Do not capture screenshots during a metrics run: a PNG write blocks the main thread ~100 ms and
// the frame after it is measured late.
using System;
using System.Collections.Generic;
using UnityEngine;

public sealed class MotionSubject
{
    public string Name = "character";
    /// <summary>Left and right toe (ball of the foot) transforms.</summary>
    public Transform ToeL, ToeR;
    /// <summary>Is this foot planted? Use the same signal the foot lock uses (the weight vote).</summary>
    public Func<bool, bool> Planted;
    /// <summary>Optional: is this foot in a procedural step? Those frames are steps, not slide.</summary>
    public Func<bool, bool> Stepping;
    /// <summary>The character root as drawn (simulated position + presentation correction).</summary>
    public Transform Root;
    /// <summary>Optional: the pelvis ground projection is compared with this while Locomotion() is true.</summary>
    public Transform Pelvis;
    public Func<Vector3> SimPosition;
    public Func<bool> Locomotion;
    /// <summary>Joints watched for pops, and optionally each joint's local rotation in the mixer output (before IK) this frame.</summary>
    public Transform[] PopJoints = Array.Empty<Transform>();
    public Func<int, Quaternion> ClipLocal;
}

public sealed class MotionMetricsSampler
{
    // Gates (a tennis game's; tune per project, then never loosen to pass)
    public const float SlideP95Gate = 0.015f, SlideMaxGate = 0.03f, PlantSpeedGate = 0.03f;
    public const float RootDevP95Gate = 0.10f, RootDevMaxGate = 0.25f, RootJumpGate = 0.5f;
    public const float ContactErrGateMs = 1f, HitchMs = 40f;
    // Pop definition: a spike, ~3° extra in a frame, faster than the clip itself
    public const float SpikeRatio = 1.8f, SpikeExcessDeg = 180f, ClipFactor = 1.2f, SpeedFloor = 30f;
    // Teleport: a reset, counted but not gated
    public const float TeleportMove = 0.2f, TeleportDv = 4f;

    sealed class FootTrack { public bool On; public Vector3 Start, Last; public float Max, Path, Seconds; public int Frames; }

    sealed class Track
    {
        public MotionSubject S;
        public FootTrack L = new FootTrack(), R = new FootTrack();
        public bool HasPrev, HasVel;
        public Vector3 PrevRoot, PrevSim, PrevVel, PrevSimVel;
        public Quaternion[] Prev, PrevClip;
        public float[,] W, F;            // [joint, 0..3] newest first: final pose and clip angular speed (deg/s)
        public int History;
    }

    readonly List<Track> tracks = new List<Track>();
    public readonly List<float> Slides = new List<float>(), PlantSpeeds = new List<float>(), RootDevs = new List<float>(), RootJumps = new List<float>();
    public readonly List<string> PopLog = new List<string>();
    public int PopsSingle, PopsWide, Teleports, Contacts, ContactHitches;
    public float ContactErrMaxMs;
    readonly List<float> planeErrs = new List<float>();
    public int PlaneFails;

    public void Add(MotionSubject s)
    {
        int n = s.PopJoints.Length;
        tracks.Add(new Track { S = s, Prev = new Quaternion[n], PrevClip = new Quaternion[n], W = new float[n, 4], F = new float[n, 4] });
    }

    public void Sample(float dt)
    {
        if (dt <= 1e-5f) return;
        foreach (var t in tracks)
        {
            var s = t.S;
            Foot(t.L, s.ToeL, s.Planted(true) && !(s.Stepping?.Invoke(true) ?? false), dt);
            Foot(t.R, s.ToeR, s.Planted(false) && !(s.Stepping?.Invoke(false) ?? false), dt);

            Vector3 root = s.Root.position, sim = s.SimPosition();
            if (s.Pelvis != null && (s.Locomotion?.Invoke() ?? false))
            {
                var p = s.Pelvis.position;
                RootDevs.Add(new Vector2(p.x - sim.x, p.z - sim.z).magnitude);
            }
            if (t.HasPrev)
            {
                Vector3 v = (root - t.PrevRoot) / dt, sv = (sim - t.PrevSim) / dt;
                bool teleport = (root - t.PrevRoot).magnitude > TeleportMove || (t.HasVel && (sv - t.PrevSimVel).magnitude > TeleportDv);
                if (teleport) { Teleports++; t.HasVel = false; }
                else
                {
                    if (t.HasVel) RootJumps.Add((v - t.PrevVel).magnitude * (1f / 60f) / dt);   // per 60 fps frame
                    t.PrevVel = v; t.PrevSimVel = sv; t.HasVel = true;
                }
            }
            t.PrevRoot = root; t.PrevSim = sim;

            for (int j = 0; j < s.PopJoints.Length; j++)
            {
                var q = s.PopJoints[j].localRotation;
                var qc = s.ClipLocal != null ? s.ClipLocal(j) : q;
                float w = t.HasPrev ? Quaternion.Angle(t.Prev[j], q) / dt : 0f;
                float f = t.HasPrev && s.ClipLocal != null ? Quaternion.Angle(t.PrevClip[j], qc) / dt : -1f;
                for (int k = 3; k > 0; k--) { t.W[j, k] = t.W[j, k - 1]; t.F[j, k] = t.F[j, k - 1]; }
                t.W[j, 0] = w; t.F[j, 0] = f;
                t.Prev[j] = q; t.PrevClip[j] = qc;
                if (t.History >= 4) Pop(t, j);
            }
            if (t.HasPrev) t.History++;
            t.HasPrev = true;
        }
    }

    void Foot(FootTrack f, Transform toe, bool planted, float dt)
    {
        var p = toe.position; p.y = 0f;
        if (planted)
        {
            if (!f.On) { f.On = true; f.Start = f.Last = p; f.Max = f.Path = f.Seconds = 0f; f.Frames = 0; }
            f.Max = Mathf.Max(f.Max, (p - f.Start).magnitude);
            f.Path += (p - f.Last).magnitude; f.Seconds += dt; f.Frames++; f.Last = p;
        }
        else if (f.On)
        {
            f.On = false;
            if (f.Frames >= 3) { Slides.Add(f.Max); PlantSpeeds.Add(f.Path / Mathf.Max(f.Seconds, 1e-4f)); }
        }
    }

    /// <summary>
    /// Candidate frames are 1 (single) and 1+2 (two wide); 0 is newest, 3 oldest.
    /// Without a clip reading (ClipLocal null) a spike alone counts, as for whole-body yaw.
    /// </summary>
    void Pop(Track t, int j)
    {
        float w0 = t.W[j, 0], w1 = t.W[j, 1], w2 = t.W[j, 2], w3 = t.W[j, 3];
        float f1 = t.F[j, 1], f2 = t.F[j, 2];
        bool hasClip = f1 >= 0f && f2 >= 0f;
        float nb = Mathf.Max(w0, w2);
        bool single = w1 > SpikeRatio * Mathf.Max(nb, SpeedFloor) && w1 - nb > SpikeExcessDeg;
        if (single && (!hasClip || w1 > ClipFactor * f1 + SpikeExcessDeg))
        {
            PopsSingle++;
            if (PopLog.Count < 60) PopLog.Add($"POP {t.S.Name} {t.S.PopJoints[j].name} {w1:0} deg/s vs {nb:0} (clip {f1:0})");
            return;
        }
        float nb2 = Mathf.Max(w0, w3);
        bool singleEither = single || w2 > SpikeRatio * Mathf.Max(Mathf.Max(w1, w3), SpeedFloor);
        if (!singleEither && Mathf.Min(w1, w2) > SpikeRatio * Mathf.Max(nb2, SpeedFloor) && (w1 + w2 - 2f * nb2) / 60f >= 3f &&
            (!hasClip || w1 + w2 > ClipFactor * (f1 + f2) + 2f * SpikeExcessDeg))
        {
            PopsWide++;
            if (PopLog.Count < 60) PopLog.Add($"WIDE {t.S.Name} {t.S.PopJoints[j].name} {w2:0},{w1:0} deg/s vs {nb2:0} (clip {f2:0},{f1:0})");
        }
    }

    /// <summary>
    /// One contact. clipErrMs: the clip's contact frame against the simulated hit tick. gapMs: time
    /// between the two rendered frames that bracket the hit tick; over HitchMs the interpolated prop
    /// position is unreliable, so the contact is listed but not gated.
    /// </summary>
    public void RecordContact(float clipErrMs, float planeErrMm, float ellipse, float gapMs, float planeTolMm = 15f, float ellipseGate = 0.8f)
    {
        Contacts++;
        ContactErrMaxMs = Mathf.Max(ContactErrMaxMs, Mathf.Abs(clipErrMs));
        if (gapMs > HitchMs) { ContactHitches++; return; }
        planeErrs.Add(Mathf.Abs(planeErrMm));
        if (Mathf.Abs(planeErrMm) > planeTolMm || ellipse > ellipseGate) PlaneFails++;
    }

    public struct Summary
    {
        public float SlideP50, SlideP95, SlideMax, PlantSpeedP95, RootDevP95, RootDevMax, RootJumpP99, RootJumpMax, PlaneErrP95Mm, ContactErrMaxMs;
        public int Plants, RootJumpFails, Pops, PlaneFails, Teleports, ContactHitches;
    }

    public Summary Summarize()
    {
        int fails = 0;
        foreach (var j in RootJumps) if (j > RootJumpGate) fails++;
        return new Summary
        {
            SlideP50 = P(Slides, 0.5f), SlideP95 = P(Slides, 0.95f), SlideMax = P(Slides, 1f), PlantSpeedP95 = P(PlantSpeeds, 0.95f),
            RootDevP95 = P(RootDevs, 0.95f), RootDevMax = P(RootDevs, 1f),
            RootJumpP99 = P(RootJumps, 0.99f), RootJumpMax = P(RootJumps, 1f), PlaneErrP95Mm = P(planeErrs, 0.95f),
            ContactErrMaxMs = ContactErrMaxMs, Plants = Slides.Count, RootJumpFails = fails, Pops = PopsSingle + PopsWide,
            PlaneFails = PlaneFails, Teleports = Teleports, ContactHitches = ContactHitches,
        };
    }

    public List<string> Lines(string label)
    {
        var s = Summarize();
        string Ok(bool b) => b ? "PASS" : "FAIL";
        var o = new List<string>
        {
            $"[MOTION] {label} foot slide per plant ({s.Plants}): p50 {s.SlideP50 * 100:0.00} p95 {s.SlideP95 * 100:0.00} max {s.SlideMax * 100:0.00} cm; plant speed p95 {s.PlantSpeedP95 * 100:0.0} cm/s " +
                $"{Ok(s.Plants > 0 && s.SlideP95 <= SlideP95Gate && s.SlideMax <= SlideMaxGate && s.PlantSpeedP95 <= PlantSpeedGate)}",
            $"[MOTION] {label} root vs sim (locomotion): p95 {s.RootDevP95 * 100:0.0} max {s.RootDevMax * 100:0.0} cm {Ok(s.RootDevP95 <= RootDevP95Gate && s.RootDevMax <= RootDevMaxGate)}",
            $"[MOTION] {label} root velocity jump: {s.RootJumpFails} frames > {RootJumpGate} m/s, p99 {s.RootJumpP99:0.00} max {s.RootJumpMax:0.00}; teleports {s.Teleports} (not gated) {Ok(s.RootJumpFails == 0)}",
            $"[MOTION] {label} pops: {s.Pops} = single {PopsSingle} + two-frame {PopsWide} {Ok(s.Pops == 0)}",
            $"[MOTION] {label} contacts {Contacts}: timing max {s.ContactErrMaxMs:0.00} ms {Ok(s.ContactErrMaxMs <= ContactErrGateMs)}; plane p95 {s.PlaneErrP95Mm:0.0} mm, {s.PlaneFails} outside {Ok(s.PlaneFails == 0)}; frame hitches not gated {s.ContactHitches}",
        };
        o.AddRange(PopLog);
        return o;
    }

    public static float P(List<float> v, float q)
    {
        if (v.Count == 0) return 0f;
        var c = new List<float>(v); c.Sort();
        return c[Mathf.Clamp(Mathf.CeilToInt(q * c.Count) - 1, 0, c.Count - 1)];
    }
}
