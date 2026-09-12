// Drop-in physics probe. Attach to BOTH objects of a suspected pair, read the
// console, then REMOVE it. Project-agnostic: no project types referenced.
//
//   Neither logs [Setup]           -> not attached where you think, or inactive in the hierarchy
//   collider none / enabled False  -> nothing of this object is in the physics scene
//   Both [Setup], no contact logs  -> Rigidbody / layer matrix / trigger mismatch
//   Only one side logs             -> the other object is not the one colliding
//   [2D Collision] appears         -> 2D components in a 3D scene
using UnityEngine;

public class CollisionDebugger : MonoBehaviour
{
    void Awake()
    {
        var col  = GetComponent<Collider>();
        var body = GetComponent<Rigidbody>();
        Debug.Log(
            $"[Setup] {name} | layer {gameObject.layer} ({LayerMask.LayerToName(gameObject.layer)}) " +
            $"| collider {(col ? col.GetType().Name : "none")} " +
            $"| enabled {(col ? col.enabled.ToString() : "-")} " +
            $"| isTrigger {(col ? col.isTrigger.ToString() : "-")} " +
            $"| rigidbody {(body ? (body.isKinematic ? "Kinematic" : "Dynamic") : "none")} " +
            $"| active {gameObject.activeInHierarchy}", this);
    }

    void OnCollisionEnter(Collision c) =>
        Debug.Log($"[Collision] {name} <- {c.gameObject.name} | contacts {c.contactCount} " +
                  $"| impulse {c.impulse.magnitude:F2}", this);

    void OnTriggerEnter(Collider other) =>
        Debug.Log($"[Trigger] {name} <- {other.name} | layer {other.gameObject.layer}", this);

    // Fires only if 2D components ended up in a 3D scene. That is the finding.
    void OnCollisionEnter2D(Collision2D c) =>
        Debug.LogWarning($"[2D Collision] {name} <- {c.gameObject.name} — 2D physics in a 3D scene", this);
}
