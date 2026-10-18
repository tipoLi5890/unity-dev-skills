// TwoBoneIKJob — one limb (upper, lower, end bone) reaching a goal inside a hand-built
// PlayableGraph, with an optional tool point (a racket face, a sword tip, a key) that is put on
// the goal instead of the end bone. Generic or Humanoid rigs; no Animation Rigging package.
//
// Drop into a Runtime folder beside AnimJobMath.cs. Wire it after the mixer:
//
//   var job = TwoBoneIKJob.Create(animator, upperArm, foreArm, hand, toolPoint);
//   var ik  = AnimationScriptPlayable.Create(graph, job, 1);
//   graph.Connect(previous, 0, ik, 0); ik.SetInputWeight(0, 1f);
//   ... each frame: job.Goal = …; job.Weight = …; job.Dt = …; ik.SetJobData(job); graph.Evaluate(0f);
//   ... on destroy: job.Dispose();
//
// What the job does, in order (reference/foot-lock-and-prop-ik.md §4):
//   1. the displacement d = Weight × (Goal − tool point), applied to the end bone (the tool is rigid);
//   2. two-bone IK about the stored hinge axis, softened relative to the clip so Weight 0 = the clip;
//   3. the end bone keeps its clip rotation;
//   4. the end bone is rotated LAST so the tool point lands on the goal, linear to WristLinear
//      degrees and smoothly saturating toward WristMax (a hard clamp pops).
// Weight is the caller's: ramp it with AnimJobMath.Spring or a C1 curve, never a step.
using Unity.Collections;
using UnityEngine;
using UnityEngine.Animations;

public struct TwoBoneIKJob : IAnimationJob, System.IDisposable
{
    public TransformStreamHandle Upper, Lower, End, Tool;
    /// <summary>[0] hinge axis in the upper bone's frame (zero until measured), [1] tool position after IK (diagnostic).</summary>
    public NativeArray<Vector3> State;

    public Vector3 Goal;
    public float Weight;
    public float Dt;
    /// <summary>Soft reach start as a fraction of limb length: 0.93 for a swinging arm, 0.97 when the clip's arm is already straight.</summary>
    public float SoftFrom;
    public float WristLinear, WristMax;

    public static TwoBoneIKJob Create(Animator animator, Transform upper, Transform lower, Transform end, Transform tool = null)
    {
        var job = new TwoBoneIKJob
        {
            Upper = animator.BindStreamTransform(upper),
            Lower = animator.BindStreamTransform(lower),
            End = animator.BindStreamTransform(end),
            Tool = tool != null ? animator.BindStreamTransform(tool) : default,
            State = new NativeArray<Vector3>(2, Allocator.Persistent),
            SoftFrom = 0.93f, WristLinear = 14f, WristMax = 24f,
        };
        // Measure the hinge from the pose the limb is in now if it is bent; else the job measures it later.
        var hinge = AnimJobMath.HingeOf(upper.rotation, lower.position - upper.position, end.position - lower.position, 15f);
        var st = job.State; st[0] = hinge; job.State = st;
        return job;
    }

    public void Dispose() { if (State.IsCreated) State.Dispose(); }

    public void ProcessRootMotion(AnimationStream stream) { }

    public void ProcessAnimation(AnimationStream stream)
    {
        if (!Upper.IsValid(stream) || !Lower.IsValid(stream) || !End.IsValid(stream)) return;
        Vector3 a = Upper.GetPosition(stream), b = Lower.GetPosition(stream), c = End.GetPosition(stream);
        State[0] = AnimJobMath.RefineHinge(State[0], Upper.GetRotation(stream), b - a, c - b);
        bool hasTool = Tool.IsValid(stream);
        Vector3 point = hasTool ? Tool.GetPosition(stream) : c;
        if (Weight <= 0f) { State[1] = point; return; }

        Vector3 d = (Goal - point) * Mathf.Clamp01(Weight);
        Vector3 goalPoint = point + d;
        Vector3 endGoal = c + d;
        Quaternion endRot = End.GetRotation(stream);

        if (State[0].sqrMagnitude < 0.5f ||
            !AnimJobMath.TwoBoneHinge(stream, Upper, Lower, End, endGoal, State[0], SoftFrom, 0.999f, true))
        {
            // No hinge yet: keep the clip's current bend side as the hint.
            Vector3 mid = (a + c) * 0.5f, side = b - mid;
            if (side.sqrMagnitude < 1e-6f) side = Vector3.down;
            AnimJobMath.TwoBoneHint(stream, Upper, Lower, End, endGoal, a + side.normalized, SoftFrom);
        }
        End.SetRotation(stream, endRot);

        if (hasTool)
        {
            Vector3 w = End.GetPosition(stream), p = Tool.GetPosition(stream);
            if ((goalPoint - p).sqrMagnitude > 1e-8f && (p - w).sqrMagnitude > 1e-8f)
            {
                Quaternion.FromToRotation(p - w, goalPoint - w).ToAngleAxis(out float ang, out Vector3 axis);
                if (ang > 180f) ang -= 360f;
                if (Mathf.Abs(ang) > 1e-3f && axis.sqrMagnitude > 0.5f)
                    End.SetRotation(stream, Quaternion.AngleAxis(AnimJobMath.SoftAngle(ang, WristLinear, WristMax), axis) * endRot);
            }
        }
        State[1] = hasTool ? Tool.GetPosition(stream) : End.GetPosition(stream);
    }
}
