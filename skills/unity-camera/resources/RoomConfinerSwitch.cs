// RoomConfinerSwitch.cs — one follow camera, many rooms: when the runner enters this
// room's trigger, the confiner's bounding shape becomes this room's shape.
//
// Drop into a Runtime assembly that references Unity.Cinemachine. Put one on each room's
// trigger object; point every one at the same CinemachineConfiner2D.
//
// REQUIRES com.unity.cinemachine 3.x (written against 3.1.7) and the built-in 2D physics
// module. On 2.x the same swap is confiner.m_BoundingShape2D + confiner.InvalidateCache() —
// reference/version-and-names.md.
//
// Scene rules this script depends on:
//   - The trigger and the bounding shape are two colliders. The trigger is what the runner
//     overlaps; the shape is what the camera stays inside, and it is a BoxCollider2D,
//     PolygonCollider2D or CompositeCollider2D — any other collider type confines nothing.
//   - Triggers of neighbouring rooms do not overlap. Inset each by half a unit from the
//     doorway, so the runner is inside one trigger at most and walking back re-enters.
//   - One side of the pair carries a Rigidbody2D, or OnTriggerEnter2D never fires.
//   - The shape sits on a layer that collides with nothing, or it is a wall.
using Unity.Cinemachine;
using UnityEngine;

[RequireComponent(typeof(Collider2D))]
public sealed class RoomConfinerSwitch : MonoBehaviour
{
    [Tooltip("The confiner on the follow camera. Shared by every room.")]
    public CinemachineConfiner2D confiner;

    [Tooltip("This room's camera bounds: Box, Polygon or Composite collider.")]
    public Collider2D roomShape;

    [Tooltip("Only this object switches rooms. Empty means anything tagged Player.")]
    public Transform runner;

    [Tooltip("On: the camera snaps to the new room. Off: it slides there on the confiner's damping.")]
    public bool cut;

    [Tooltip("Seconds of baking to spend in the switch frame, so the first frame is already confined. 0 leaves it to the confiner.")]
    public float bakeBudgetSeconds = 0.01f;

    void Reset()
    {
        GetComponent<Collider2D>().isTrigger = true;
    }

    void OnTriggerEnter2D(Collider2D other)
    {
        // A compound runner reports the child collider; its Rigidbody2D is the runner.
        Transform who = other.attachedRigidbody != null ? other.attachedRigidbody.transform : other.transform;
        if (runner != null ? who != runner : !who.CompareTag("Player")) return;
        Apply();
    }

    /// <summary>Make this room the confining room now. Safe to call for the starting room.</summary>
    public void Apply()
    {
        if (confiner == null || roomShape == null || confiner.BoundingShape2D == roomShape) return;

        confiner.BoundingShape2D = roomShape;

        // A different collider is noticed on the next update by itself. The explicit call
        // covers what is not noticed — a shape whose points were edited or that was rotated
        // or scaled unevenly — and drops the per-lens solution with it.
        confiner.InvalidateBoundingShapeCache();

        CinemachineVirtualCameraBase vcam = confiner.ComponentOwner;
        if (vcam == null) return;

        // Until the bake finishes the confiner has no effect, and a camera that is free for
        // a few frames shows the next room's wall. A box bakes at once; a polygon may not.
        if (bakeBudgetSeconds > 0f) confiner.BakeBoundingShape(vcam, bakeBudgetSeconds);

        // Without this the camera damps across the wall from the old room, which reads as a
        // slow pan through solid geometry. With it, the next frame is a cut.
        if (cut) vcam.PreviousStateIsValid = false;
    }
}
