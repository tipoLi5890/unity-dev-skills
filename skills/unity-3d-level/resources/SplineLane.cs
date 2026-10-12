// SplineLane.cs — turns "distance along the track, lane number" into a world position and a
// facing, on a spline. The lane run's three lanes follow a curve instead of the Z axis, and the
// runner, the hazards and the pickups all ask the same component where a lane is.
//
// Drop into a Runtime assembly (an asmdef that references Unity.Splines and Unity.Mathematics)
// and add it to the GameObject that carries the SplineContainer.
//
// REQUIRES com.unity.splines (written against 2.8.4).
//
//   lane.EvaluateLane(distance, 1, out pos, out rot)      the middle lane: on the spline itself
//   lane.Evaluate(distance, lateral, out pos, out rot)    any sideways offset, for a lane change
//   lane.Project(worldPoint, out distance, out lateral)   where on the track a world point is
//
// The component only answers; it moves nothing. The one writer of the runner's transform calls
// Evaluate with the distance it has travelled and the lateral offset it is easing towards.
// Keep the container's scale uniform: distances are then world units along the curve.
using Unity.Mathematics;
using UnityEngine;
using UnityEngine.Splines;

[AddComponentMenu("Courier/Spline Lane")]
public class SplineLane : MonoBehaviour
{
    [Tooltip("The track. Left empty, the SplineContainer on this GameObject is used.")]
    public SplineContainer container;
    [Tooltip("Which spline of the container is the track.")]
    public int splineIndex = 0;
    [Tooltip("Distance between neighbouring lane centres, in units.")]
    public float laneSpacing = 1.3f;
    [Tooltip("Lanes across the track. With 3, lane 1 is the spline itself.")]
    public int laneCount = 3;
    [Tooltip("Keep lanes level: sideways is measured against world up, not the spline's own roll.")]
    public bool level = true;

    /// <summary>World length of the track. Call Rebuild after the spline is edited at runtime.</summary>
    public float Length { get; private set; }

    public bool Closed => container != null && container.Splines.Count > splineIndex && container.Splines[splineIndex].Closed;

    void Awake() => Rebuild();

    public void Rebuild()
    {
        if (container == null) container = GetComponent<SplineContainer>();
        Length = container != null && container.Splines.Count > splineIndex ? container.CalculateLength(splineIndex) : 0f;
    }

    /// <summary>Sideways offset of a lane centre from the spline: lane 1 of 3 is 0, lane 0 is
    /// -spacing (left of the direction of travel), lane 2 is +spacing.</summary>
    public float LaneOffset(int lane) => (Mathf.Clamp(lane, 0, laneCount - 1) - (laneCount - 1) * 0.5f) * laneSpacing;

    public bool EvaluateLane(float distance, int lane, out Vector3 position, out Quaternion rotation) =>
        Evaluate(distance, LaneOffset(lane), out position, out rotation);

    /// <summary>World position and facing at a distance along the track and a sideways offset
    /// from it. False when there is no track; position and rotation are then this transform's.</summary>
    public bool Evaluate(float distance, float lateral, out Vector3 position, out Quaternion rotation)
    {
        position = transform.position;
        rotation = transform.rotation;
        if (container == null || Length <= 0f) return false;

        // The container's ratio runs evenly along the curve's length, so distance / Length is it.
        float t = Closed ? Mathf.Repeat(distance, Length) / Length : Mathf.Clamp01(distance / Length);
        if (!container.Evaluate(splineIndex, t, out float3 p, out float3 tangent, out float3 up)) return false;

        Vector3 forward = ((Vector3)tangent).normalized;
        Vector3 upward = level ? Vector3.up : ((Vector3)up).normalized;
        Vector3 right = Vector3.Cross(upward, forward);
        if (right.sqrMagnitude < 1e-6f)                      // the track points straight up or down
        {
            upward = ((Vector3)up).normalized;
            right = Vector3.Cross(upward, forward);
        }
        right.Normalize();

        position = (Vector3)p + right * lateral;
        rotation = Quaternion.LookRotation(forward, Vector3.Cross(forward, right));
        return true;
    }

    /// <summary>The distance along the track nearest to a world point, and how far to the side
    /// of the spline that point is. Use it to place a hazard that was authored in world space,
    /// or to find the lane something landed in.</summary>
    public bool Project(Vector3 worldPoint, out float distance, out float lateral)
    {
        distance = 0f;
        lateral = 0f;
        if (container == null || Length <= 0f) return false;

        float3 local = container.transform.InverseTransformPoint(worldPoint);
        SplineUtility.GetNearestPoint(container.Splines[splineIndex], local, out float3 _, out float t);
        distance = t * Length;
        if (!Evaluate(distance, 0f, out Vector3 onTrack, out Quaternion facing)) return false;
        lateral = Vector3.Dot(worldPoint - onTrack, facing * Vector3.right);
        return true;
    }

    /// <summary>The lane whose centre is nearest to a sideways offset.</summary>
    public int NearestLane(float lateral) =>
        Mathf.Clamp(Mathf.RoundToInt(lateral / laneSpacing + (laneCount - 1) * 0.5f), 0, laneCount - 1);

    void OnDrawGizmosSelected()
    {
        if (container == null) container = GetComponent<SplineContainer>();
        if (container == null || container.Splines.Count <= splineIndex) return;
        float length = container.CalculateLength(splineIndex);
        if (length <= 0f) return;
        float saved = Length;
        Length = length;

        Gizmos.color = new Color(0.95f, 0.85f, 0.2f);
        int steps = Mathf.Clamp(Mathf.CeilToInt(length), 2, 512);
        for (int lane = 0; lane < laneCount; lane++)
        {
            Evaluate(0f, LaneOffset(lane), out Vector3 previous, out Quaternion _);
            for (int i = 1; i <= steps; i++)
            {
                Evaluate(length * i / steps, LaneOffset(lane), out Vector3 next, out Quaternion _);
                Gizmos.DrawLine(previous, next);
                previous = next;
            }
        }
        Length = saved;
    }
}
