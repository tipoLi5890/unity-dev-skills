// FootLockJob — keeps planted feet still in the world under blended, rate-scaled, stride-warped
// locomotion, inside a hand-built PlayableGraph (Generic or Humanoid; no OnAnimatorIK needed).
//
// Drop into a Runtime folder beside AnimJobMath.cs. Bind the handles by role (pelvis, upper leg,
// lower leg, foot, toe) with animator.BindStreamTransform; the bone names are your rig's. Connect
// it directly after the mixer, before any look-at or hand IK. Each frame the scheduler writes
// PlantL/R, TimeToPlantL/R, Dt, BodyYaw, BodyYawRate, TravelDir and Stride, then SetJobData.
//
// Per foot, per frame (reference/foot-lock-and-prop-ik.md §2):
//   1. stride warp along TravelDir, the swing leg softened from 0.85 toward 0.97 of leg length;
//   2. ground the lower of heel and ball (pulled down while planted, only kept above while swinging);
//   3. lock the toe's horizontal position and the foot's yaw on the first planted frame, as drawn;
//   4. release on lift with a critically damped spring whose start velocity is −(clip foot velocity),
//      or take a procedural step (C1 bump) when the leg cannot reach, the body turned too far, or
//      the lock is too far from the clip's foot;
//   5. anticipate touchdown: in the last AnticipTime seconds steer toward the predicted landing point;
//   6. lower the pelvis (spring, fast down, slow up) to what the farthest leg needs;
//   7. hinge-axis two-bone IK per leg.
// Every target and weight here is continuous in position and velocity. Keep it that way.
using Unity.Collections;
using UnityEngine;
using UnityEngine.Animations;

public struct FootLockState
{
    public int Locked, Stepping, NeedStep, HasPrev;
    public Vector3 LockToe;               // world, horizontal used
    public float LockYaw;                 // body yaw at lock + yaw correction at lock
    public Vector3 RelOffset, RelVel;     // release offset (target − clip foot) and its velocity
    public float RelYaw, RelYawVel, RelT;
    public float StepT, StepH;
    public float GroundW, GroundWVel;     // 1 planted, 0 swinging
    public float Anticip, AnticipVel;     // landing anticipation weight
    public float SoftW, SoftWVel;         // 1 = locked leg softening, 0 = swing softening
    public Vector3 PrevClip, PrevClipVel; // clip foot (after warp and ground) last frame, for velocity
    public Vector3 Hinge;                 // knee hinge axis in the upper leg's frame (measure from a bent pose)
    public float Drift;                   // diagnostic: drawn toe distance from the lock point
    public int Reason;                    // diagnostic: 1 lift, 2 cannot reach, 3 turned, 4 too far
}

public struct FootLockJob : IAnimationJob, System.IDisposable
{
    public TransformStreamHandle Pelvis;
    public TransformStreamHandle UpperL, LowerL, FootL, ToeL, UpperR, LowerR, FootR, ToeR;
    /// <summary>Heel contact in the foot bone's frame and ball contact in the toe bone's frame, measured in the bind pose (world lengths).</summary>
    public Vector3 HeelL, BallL, HeelR, BallR;
    public NativeArray<FootLockState> Feet;   // [0] left, [1] right
    public NativeArray<float> PelvisDrop;     // [0] drop (m), [1] its velocity

    // ── written by the scheduler every frame ──
    public float Dt, Weight, GroundY;
    public int PlantL, PlantR;                // the weight vote over the active clips' plant windows
    public float TimeToPlantL, TimeToPlantR;  // seconds until the next plant; 0 planted; −1 unknown
    public float BodyYaw, BodyYawRate;        // degrees, degrees/s
    public Vector3 TravelDir;                 // unit, horizontal
    public float Stride, WarpWeight, BaseDrop;

    // ── tuning (the values a tennis game shipped with) ──
    public float MaxDrop, ReachFrac, ReleaseYaw, StepDist, StepTime, StepHeight;
    public const float ReleaseOmega = 28f, ReleaseYawOmega = 12f, AnticipTime = 0.08f;
    public const float LegSoft = 0.985f, LegSoftSwing = 0.93f, LegReach = 0.998f;
    public const float SwingReach = 0.97f, SwingSoftFrom = 0.85f, StepNeed = 0.01f;

    public static FootLockJob Create(Animator animator, Transform pelvis,
        Transform upperL, Transform lowerL, Transform footL, Transform toeL,
        Transform upperR, Transform lowerR, Transform footR, Transform toeR, float groundY)
    {
        TransformStreamHandle B(Transform t) => animator.BindStreamTransform(t);
        Vector3 Off(Transform bone, Transform at) =>
            Quaternion.Inverse(bone.rotation) * (new Vector3(at.position.x, groundY, at.position.z) - bone.position);
        var job = new FootLockJob
        {
            Pelvis = B(pelvis),
            UpperL = B(upperL), LowerL = B(lowerL), FootL = B(footL), ToeL = B(toeL),
            UpperR = B(upperR), LowerR = B(lowerR), FootR = B(footR), ToeR = B(toeR),
            // Call in the bind pose with the feet flat on the ground.
            HeelL = Off(footL, footL), BallL = Off(toeL, toeL), HeelR = Off(footR, footR), BallR = Off(toeR, toeR),
            Feet = new NativeArray<FootLockState>(2, Allocator.Persistent),
            PelvisDrop = new NativeArray<float>(2, Allocator.Persistent),
            Weight = 1f, GroundY = groundY, Stride = 1f, TravelDir = Vector3.forward,
            MaxDrop = 0.10f, ReachFrac = 0.975f, ReleaseYaw = 60f, StepDist = 0.30f, StepTime = 0.2f, StepHeight = 0.06f,
        };
        return job;
    }

    /// <summary>Store a knee hinge measured from a clearly bent pose (AnimJobMath.HingeOf); until then the knee bends toward body forward.</summary>
    public void SetHinge(bool left, Vector3 hingeLocal) { var s = Feet[left ? 0 : 1]; s.Hinge = hingeLocal; Feet[left ? 0 : 1] = s; }

    public void Dispose()
    {
        if (Feet.IsCreated) Feet.Dispose();
        if (PelvisDrop.IsCreated) PelvisDrop.Dispose();
    }

    public void ProcessRootMotion(AnimationStream stream) { }

    public void ProcessAnimation(AnimationStream stream)
    {
        if (!Pelvis.IsValid(stream) || !FootL.IsValid(stream) || !FootR.IsValid(stream)) return;
        float dt = Mathf.Max(Dt, 0f);
        Vector3 hip = Pelvis.GetPosition(stream);

        Target(stream, 0, UpperL, LowerL, FootL, ToeL, HeelL, BallL, PlantL != 0, TimeToPlantL, hip, out Vector3 ankleL, out Quaternion rotL);
        Target(stream, 1, UpperR, LowerR, FootR, ToeR, HeelR, BallR, PlantR != 0, TimeToPlantR, hip, out Vector3 ankleR, out Quaternion rotR);

        // Pelvis: the larger of the stride pre-drop and what the farthest leg needs; fast down, slow up.
        float want = Mathf.Clamp(Mathf.Max(Mathf.Max(Need(stream, UpperL, LowerL, FootL, ankleL), Need(stream, UpperR, LowerR, FootR, ankleR)), BaseDrop), 0f, MaxDrop);
        float drop = PelvisDrop[0], dropV = PelvisDrop[1];
        if (dt > 0f) AnimJobMath.Spring(ref drop, ref dropV, want, want > drop ? 60f : 16f, dt); else { drop = want; dropV = 0f; }
        if (drop < 0f) { drop = 0f; dropV = Mathf.Max(0f, dropV); }
        PelvisDrop[0] = drop; PelvisDrop[1] = dropV;
        if (drop > 1e-4f) { hip = Pelvis.GetPosition(stream); hip.y -= drop * Weight; Pelvis.SetPosition(stream, hip); }

        if (Weight <= 0f) return;
        // Still out of reach after the drop: step next frame instead of dragging the foot.
        FlagStep(0, Need(stream, UpperL, LowerL, FootL, ankleL) > StepNeed);
        FlagStep(1, Need(stream, UpperR, LowerR, FootR, ankleR) > StepNeed);
        Leg(stream, 0, UpperL, LowerL, FootL, ToeL, ankleL, rotL);
        Leg(stream, 1, UpperR, LowerR, FootR, ToeR, ankleR, rotR);
    }

    void FlagStep(int i, bool need) { var st = Feet[i]; st.NeedStep = need && st.Locked != 0 ? 1 : 0; Feet[i] = st; }

    /// <summary>Height the pelvis must drop for this leg to reach ankleT at ReachFrac of its length (below the soft zone, so a locked foot never creeps).</summary>
    float Need(AnimationStream s, TransformStreamHandle up, TransformStreamHandle lo, TransformStreamHandle ft, Vector3 ankleT)
    {
        if (!up.IsValid(s) || !lo.IsValid(s)) return 0f;
        Vector3 a = up.GetPosition(s), b = lo.GetPosition(s), c = ft.GetPosition(s);
        float L = ((b - a).magnitude + (c - b).magnitude) * ReachFrac;
        Vector3 d = ankleT - a;
        if (d.sqrMagnitude <= L * L) return 0f;
        float h = new Vector2(d.x, d.z).magnitude;
        if (h >= L) return 1f;
        return Mathf.Max(0f, -d.y - Mathf.Sqrt(L * L - h * h));
    }

    void Leg(AnimationStream s, int i, TransformStreamHandle up, TransformStreamHandle lo, TransformStreamHandle ft, TransformStreamHandle toe, Vector3 ankleT, Quaternion footRot)
    {
        if (!up.IsValid(s) || !lo.IsValid(s)) return;
        Vector3 a = up.GetPosition(s), b = lo.GetPosition(s), c = ft.GetPosition(s);
        var st = Feet[i];
        st.Hinge = AnimJobMath.RefineHinge(st.Hinge, up.GetRotation(s), b - a, c - b);
        if (Weight < 1f) ankleT = Vector3.Lerp(c, ankleT, Weight);
        // Locked (or about to land): soften late so the lock is reachable. Swinging: soften early so the knee never snaps straight.
        float softWant = st.Locked != 0 || st.Anticip > 0.05f ? 1f : 0f;
        if (Dt > 0f) AnimJobMath.Spring(ref st.SoftW, ref st.SoftWVel, softWant, 60f, Dt); else st.SoftW = softWant;
        float soft = Mathf.Lerp(LegSoftSwing, LegSoft, Mathf.Clamp01(st.SoftW));
        if (st.Locked != 0 && toe.IsValid(s))
        {
            var p = toe.GetPosition(s);
            st.Drift = new Vector2(p.x - st.LockToe.x, p.z - st.LockToe.z).magnitude;
        }
        Feet[i] = st;
        if (st.Hinge.sqrMagnitude < 0.5f || !AnimJobMath.TwoBoneHinge(s, up, lo, ft, ankleT, st.Hinge, soft, LegReach, false))
        {
            Vector3 fwd = Quaternion.AngleAxis(BodyYaw, Vector3.up) * Vector3.forward;   // knee toward body forward, never the toe
            AnimJobMath.TwoBoneHint(s, up, lo, ft, ankleT, a + fwd, soft, LegReach);
        }
        ft.SetRotation(s, Weight < 1f ? Quaternion.Slerp(ft.GetRotation(s), footRot, Weight) : footRot);
    }

    void Release(ref FootLockState st, Vector3 toeP, Vector3 vClip, int reason, bool step, float far)
    {
        st.Locked = 0; st.Reason = reason;
        var off = st.LockToe - toeP; off.y = 0f;
        st.RelOffset = off;
        st.RelVel = -vClip;                       // the target's velocity stays 0 on this frame, then rises to the clip's
        st.RelYaw = Mathf.DeltaAngle(BodyYaw, st.LockYaw);
        st.RelYawVel = -BodyYawRate;
        st.RelT = 0f;
        st.Anticip = 0f; st.AnticipVel = 0f;
        if (step) { st.Stepping = 1; st.StepT = 0f; st.StepH = Mathf.Min(StepHeight, 0.3f * far + 0.02f); }
    }

    void Target(AnimationStream s, int i, TransformStreamHandle up, TransformStreamHandle lo, TransformStreamHandle ft, TransformStreamHandle toe,
                Vector3 heelOff, Vector3 ballOff, bool planted, float touchIn, Vector3 hip, out Vector3 ankleT, out Quaternion footRot)
    {
        Vector3 ankle = ft.GetPosition(s), toeP = toe.GetPosition(s);
        Quaternion fr = ft.GetRotation(s), tr = toe.GetRotation(s);
        float dt = Mathf.Max(Dt, 0f);
        var st = Feet[i];

        // 1. Stride warp: the toe's offset from the pelvis along TravelDir × Stride, softened near full reach.
        if (WarpWeight > 0f && Mathf.Abs(Stride - 1f) > 1e-3f)
        {
            Vector3 rel = toeP - hip; rel.y = 0f;
            Vector3 dw = TravelDir * (Vector3.Dot(rel, TravelDir) * (Stride - 1f) * WarpWeight);
            if (dw.sqrMagnitude > 1e-8f && up.IsValid(s) && lo.IsValid(s))
            {
                Vector3 ta = up.GetPosition(s), sb = lo.GetPosition(s);
                float L = (sb - ta).magnitude + (ankle - sb).magnitude;
                ta.y -= PelvisDrop[0] * Weight;
                Vector3 pv = ankle - ta;
                float d1 = (pv + dw).magnitude;
                float R = AnimJobMath.SoftReach(d1, L * SwingReach, SwingSoftFrom / SwingReach);
                if (d1 > R + 1e-5f)
                {
                    float pd = Vector3.Dot(pv, dw), dd = dw.sqrMagnitude, pp = pv.sqrMagnitude;
                    float disc = pd * pd - dd * (pp - R * R);
                    dw *= pp >= R * R || disc < 0f ? 0f : Mathf.Clamp01((-pd + Mathf.Sqrt(disc)) / dd);
                }
            }
            ankle += dw; toeP += dw;
        }

        // 2. Ground: the lower contact point pulled to the ground when planted, only kept above it when swinging.
        float gTarget = planted ? 1f : 0f;
        if (dt > 0f) AnimJobMath.Spring(ref st.GroundW, ref st.GroundWVel, gTarget, 45f, dt); else { st.GroundW = gTarget; st.GroundWVel = 0f; }
        float gw = Mathf.Clamp01(st.GroundW);
        Vector3 heel = ankle + fr * heelOff, ball = toeP + tr * ballOff;
        float minY = Mathf.Min(heel.y, ball.y) - GroundY;
        float dy = Mathf.Clamp(Mathf.Lerp(Mathf.Max(0f, -minY), -minY, gw), -0.08f, 0.12f);
        ankle.y += dy; toeP.y += dy;

        // The clip foot's horizontal velocity and acceleration (release and landing prediction).
        Vector3 vClip = Vector3.zero, aClip = Vector3.zero;
        if (st.HasPrev != 0 && dt > 0f)
        {
            vClip = (toeP - st.PrevClip) / dt; vClip.y = 0f;
            if (vClip.magnitude > 12f) vClip = vClip.normalized * 12f;     // a teleport (reset), not a step
            aClip = (vClip - st.PrevClipVel) / dt;
            if (aClip.magnitude > 150f) aClip = aClip.normalized * 150f;
        }
        st.PrevClip = toeP; st.PrevClipVel = vClip; st.HasPrev = 1;

        float yawCorr = 0f;
        Vector3 tgt = toeP;
        if (Weight <= 0f)
        {
            st.Locked = 0; st.Stepping = 0; st.NeedStep = 0;
            st.RelOffset = st.RelVel = Vector3.zero; st.RelYaw = st.RelYawVel = 0f; st.RelT = 99f;
            st.Anticip = st.AnticipVel = 0f;
        }
        else
        {
            // 3–4. Hold the lock, or release it.
            if (st.Locked != 0)
            {
                float far = new Vector2(st.LockToe.x - toeP.x, st.LockToe.z - toeP.z).magnitude;
                int reason = !planted ? 1 : st.NeedStep != 0 ? 2 : Mathf.Abs(Mathf.DeltaAngle(st.LockYaw, BodyYaw)) > ReleaseYaw ? 3 : far > StepDist ? 4 : 0;
                if (reason != 0) Release(ref st, toeP, vClip, reason, reason != 1, far);
                else { tgt.x = st.LockToe.x; tgt.z = st.LockToe.z; yawCorr = Mathf.DeltaAngle(BodyYaw, st.LockYaw); }
            }
            st.NeedStep = 0;
            if (st.Locked == 0)
            {
                if (dt > 0f && st.RelT > 0f)
                {
                    AnimJobMath.Spring(ref st.RelOffset, ref st.RelVel, Vector3.zero, ReleaseOmega, dt);
                    AnimJobMath.Spring(ref st.RelYaw, ref st.RelYawVel, 0f, ReleaseYawOmega, dt);
                }
                float land = touchIn;
                if (st.Stepping != 0)
                {
                    st.StepT += dt;
                    float u = st.StepT / Mathf.Max(StepTime, 0.05f);
                    tgt.y = toeP.y + st.StepH * AnimJobMath.Bump(u);
                    land = planted ? Mathf.Max(0f, (1f - u) * StepTime) : -1f;
                    if (u >= 1f) st.Stepping = 0;
                }
                // 5. Landing anticipation: steer toward where the clip foot will be at touchdown,
                //    extrapolated with only the deceleration along its velocity.
                float aWant = land > 0f && land < AnticipTime ? 1f - AnimJobMath.Smooth(land / AnticipTime)
                            : land == 0f && st.Stepping == 0 && planted ? 1f : 0f;
                if (dt > 0f) AnimJobMath.Spring(ref st.Anticip, ref st.AnticipVel, aWant, 120f, dt); else st.Anticip = aWant;
                float aw = Mathf.Clamp01(st.Anticip);
                tgt = toeP + new Vector3(st.RelOffset.x, 0f, st.RelOffset.z) + Vector3.up * (tgt.y - toeP.y);
                if (aw > 1e-4f)
                {
                    float tl = Mathf.Max(land, 0f), vm = vClip.magnitude;
                    Vector3 adv = vClip * tl;
                    if (vm > 1e-3f)
                    {
                        float dec = Mathf.Max(0f, -Vector3.Dot(aClip, vClip / vm));
                        float te = Mathf.Min(tl, dec > 1e-3f ? vm / dec : float.MaxValue);
                        adv = (vClip / vm) * (vm * te - 0.5f * dec * te * te);
                    }
                    tgt.x = Mathf.Lerp(tgt.x, toeP.x + adv.x, aw);
                    tgt.z = Mathf.Lerp(tgt.z, toeP.z + adv.z, aw);
                }
                yawCorr = st.RelYaw;
                if (planted && st.Stepping == 0)
                {
                    // Lock where the foot is drawn this frame, release offset included: no jump.
                    st.Locked = 1; st.LockToe = tgt; st.LockYaw = BodyYaw + yawCorr; st.Reason = 0;
                    st.RelOffset = st.RelVel = Vector3.zero; st.RelYaw = st.RelYawVel = 0f; st.RelT = 99f;
                    st.Anticip = st.AnticipVel = 0f;
                }
                else st.RelT = Mathf.Min(st.RelT + dt, 99f);
            }
        }
        Feet[i] = st;
        footRot = Mathf.Abs(yawCorr) > 1e-3f ? Quaternion.AngleAxis(yawCorr, Vector3.up) * fr : fr;
        // The ball of the foot is the pivot: ankle = toe target − rotated (toe − ankle).
        Vector3 toeLocal = Quaternion.Inverse(fr) * (toe.GetPosition(s) - ft.GetPosition(s));
        ankleT = tgt - footRot * toeLocal;
    }
}
