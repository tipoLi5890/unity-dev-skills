// SpringCollider — a body sphere or capsule that spring chains stay outside of. It sits on a
// child GameObject of a bone (SecondaryMotionSetup names them SM_Collider_<name>), so it moves
// with the animated body; a capsule runs from this transform to endB.
//
// Radii are in the model's own units (metres from the rig side) and scale with the model, so a
// character fitted to a height by scaling its visual child keeps its colliders in proportion.
using UnityEngine;

namespace UnityDev.SecondaryMotion
{
    public sealed class SpringCollider : MonoBehaviour
    {
        public enum Shape { Sphere, Capsule }

        public Shape shape = Shape.Capsule;

        [Tooltip("Radius in model units, before the model's scale.")]
        public float radius = 0.1f;

        [Tooltip("Capsule: the far end. This transform is the near end.")]
        public Transform endB;

        [Tooltip("Capsule: fraction trimmed off each end, so a thigh capsule stops short of the hip.")]
        [Range(0f, 0.5f)] public float inset;

        [Tooltip("Sphere: centre in this transform's local space (the head's centre is not a bone origin).")]
        public Vector3 localCenter;

        /// <summary>World end points and radius. A sphere returns a == b. scale is the model's
        /// uniform scale (SecondaryMotionSystem passes its own lossyScale.x).</summary>
        public void GetWorld(float scale, out Vector3 a, out Vector3 b, out float r)
        {
            r = radius * scale;
            if (shape == Shape.Sphere || endB == null)
            {
                a = b = transform.TransformPoint(localCenter);
                return;
            }
            Vector3 p = transform.position, q = endB.position;
            a = Vector3.Lerp(p, q, inset);
            b = Vector3.Lerp(q, p, inset);
        }

        void OnDrawGizmosSelected()
        {
            float scale = 1f;
            var system = GetComponentInParent<SecondaryMotionSystem>();
            if (system != null) scale = Mathf.Abs(system.transform.lossyScale.x);
            GetWorld(scale, out Vector3 a, out Vector3 b, out float r);
            Gizmos.color = new Color(0.2f, 0.8f, 1f, 0.8f);
            Gizmos.DrawWireSphere(a, r);
            if (a == b) return;
            Gizmos.DrawWireSphere(b, r);
            Vector3 axis = b - a;
            Vector3 side = Vector3.Cross(axis, Mathf.Abs(Vector3.Dot(axis.normalized, Vector3.up)) > 0.9f ? Vector3.right : Vector3.up).normalized * r;
            Vector3 side2 = Vector3.Cross(axis.normalized, side);
            Gizmos.DrawLine(a + side, b + side);
            Gizmos.DrawLine(a - side, b - side);
            Gizmos.DrawLine(a + side2, b + side2);
            Gizmos.DrawLine(a - side2, b - side2);
        }
    }
}
