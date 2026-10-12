// CollisionDebugger2D.cs — drop-in 2D physics probe. Attach to BOTH objects of a suspected
// pair, drag each one's collider into the other's `other` field, read the console, then
// REMOVE it. Project-agnostic: no project types referenced.
//
// Drop anywhere under Assets/ (a runtime folder, not Editor/).
//
// REQUIRES com.unity.modules.physics2d, and com.unity.modules.physics for the one handler that
// detects 3D components in a 2D scene (both built in; read Packages/manifest.json).
//
//   Neither logs [Setup]                         -> not attached where you think, or inactive in the hierarchy
//   collider none / enabled False / shapes 0     -> nothing of this object is in the 2D world
//   simulated False / layerSimulated False       -> the body or its layer is switched out of the simulation
//   [Pair] canContact False                      -> layer matrix or a layer override on one of the two
//   [Pair] ignored True                          -> Physics2D.IgnoreCollision is set for these two instances
//   Both [Setup], [Pair] clean, no contact logs  -> body types / full kinematic contacts / trigger mismatch
//   Only one side logs                           -> the other object is not the one colliding
//   [3D Collision] appears                       -> 3D components in a 2D scene
using UnityEngine;

public class CollisionDebugger2D : MonoBehaviour
{
    [Tooltip("The collider this object is expected to touch. Optional; enables the [Pair] line.")]
    public Collider2D other;

    void Awake()
    {
        var col = GetComponent<Collider2D>();
        // The body a collider belongs to is the nearest one up the hierarchy, not necessarily
        // one on this GameObject.
        Rigidbody2D body = col ? col.attachedRigidbody : GetComponentInParent<Rigidbody2D>();
        int layer = gameObject.layer;
        bool layerSimulated = (Physics2D.simulationLayers.value & (1 << layer)) != 0;

        Debug.Log(
            $"[Setup] {name} | layer {layer} ({LayerMask.LayerToName(layer)}) " +
            $"| collider {(col ? col.GetType().Name : "none")} " +
            $"| enabled {(col ? col.enabled.ToString() : "-")} " +
            $"| isTrigger {(col ? col.isTrigger.ToString() : "-")} " +
            $"| shapes {(col ? col.shapeCount.ToString() : "-")} " +
            $"| error {(col ? col.errorState.ToString() : "-")} " +
            $"| composite {(col ? col.compositeOperation.ToString() : "-")} " +
            $"| usedByEffector {(col ? col.usedByEffector.ToString() : "-")} " +
            $"| rigidbody {(body ? body.bodyType.ToString() : "none")} " +
            $"| simulated {(body ? body.simulated.ToString() : "-")} " +
            $"| fullKinematicContacts {(body ? body.useFullKinematicContacts.ToString() : "-")} " +
            $"| layerSimulated {layerSimulated} " +
            $"| active {gameObject.activeInHierarchy}", this);
    }

    // Start, not Awake: the other object's collider must have been created too.
    void Start()
    {
        var col = GetComponent<Collider2D>();
        if (col == null || other == null) return;

        ColliderDistance2D gap = col.Distance(other);
        Debug.Log(
            $"[Pair] {name} x {other.name} " +
            $"| canContact {col.CanContact(other)} " +
            $"| ignored {Physics2D.GetIgnoreCollision(col, other)} " +
            $"| layerMatrix {!Physics2D.GetIgnoreLayerCollision(gameObject.layer, other.gameObject.layer)} " +
            $"| distance {(gap.isValid ? gap.distance.ToString("F3") : "invalid")} " +
            $"| z {transform.position.z:F2} / {other.transform.position.z:F2}", this);
    }

    void OnCollisionEnter2D(Collision2D c) =>
        Debug.Log($"[Collision] {name} <- {c.gameObject.name} | contacts {c.contactCount} " +
                  $"| relative speed {c.relativeVelocity.magnitude:F2}", this);

    void OnTriggerEnter2D(Collider2D hit) =>
        Debug.Log($"[Trigger] {name} <- {hit.name} | layer {hit.gameObject.layer}", this);

    // Fires only if 3D components ended up in a 2D scene. That is the finding.
    void OnCollisionEnter(Collision c) =>
        Debug.LogWarning($"[3D Collision] {name} <- {c.gameObject.name} — 3D physics in a 2D scene", this);
}
