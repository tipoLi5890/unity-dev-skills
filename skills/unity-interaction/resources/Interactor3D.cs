// Interactor3D — detection for a 3D actor, in two modes chosen by the camera:
//   Overlap   third person and overhead: a sphere around the body on a tick, then a cone on the
//             body's facing, then one line of sight per candidate
//   Ray       first person: one ray from the view through the centre of the screen
//
// Drop into the same Runtime assembly as IInteractable.cs and add it to the runner, beside its
// RunInputSource (skill unity-input → resources/). Put interactables on a layer in 'interactable'
// and leave the runner's own layer out of both masks. REQUIRES com.unity.modules.physics (built
// in; read Packages/manifest.json).
//
// Selection, the press and the hold are InteractorBase's; this file only answers "what is in
// reach". Every query passes QueryTriggerInteraction explicitly: a switch is often a trigger, a
// wall never is, and the project-wide default is not this component's to rely on.
using System.Collections.Generic;
using UnityEngine;

public enum InteractDetect3D { Overlap, Ray }

[DisallowMultipleComponent]
[AddComponentMenu("Courier/Interactor 3D")]
public sealed class Interactor3D : InteractorBase
{
    [Header("Detection")]
    public InteractDetect3D mode = InteractDetect3D.Overlap;
    [Tooltip("Layers that hold interactables. Never the runner's own layer.")]
    public LayerMask interactable = Physics.DefaultRaycastLayers;
    [Tooltip("Solid layers that hide an interactable: walls, closed gates. Empty skips the line-of-sight test.")]
    public LayerMask blockers = 0;
    [Tooltip("Overlap: degrees either side of the body's forward. 180 selects all round.")]
    public float halfAngle = 60f;
    [Tooltip("Height above the feet the reach is measured from.")]
    public float originHeight = 1f;
    [Tooltip("Height above the feet line of sight starts from, and the ray when 'view' is empty.")]
    public float eyeHeight = 1.6f;

    [Header("Ray mode")]
    [Tooltip("The first-person camera. The ray leaves its position along its forward.")]
    public Transform view;
    [Tooltip("0 is a ray. 0.1 is a sphere cast that forgives a near miss on a small switch.")]
    public float rayRadius = 0f;

    readonly Collider[] _overlaps = new Collider[16];

    protected override float HalfAngle => mode == InteractDetect3D.Ray ? 180f : halfAngle;

    Vector3 Eye => transform.position + Vector3.up * eyeHeight;

    protected override void Gather(List<InteractionCandidate> into)
    {
        if (mode == InteractDetect3D.Ray) GatherRay(into);
        else GatherOverlap(into);
    }

    void GatherOverlap(List<InteractionCandidate> into)
    {
        Vector3 origin = transform.position + Vector3.up * originHeight;
        Vector3 forward = Vector3.ProjectOnPlane(transform.forward, Vector3.up);

        int count = Physics.OverlapSphereNonAlloc(origin, KeepRange, _overlaps, interactable,
                                                  QueryTriggerInteraction.Collide);
        for (int i = 0; i < count; i++)
        {
            Collider hit = _overlaps[i];
            IInteractable target = hit.GetComponentInParent<IInteractable>();
            if (target == null) continue;

            // Bounds, not Collider.ClosestPoint: that one rejects a non-convex mesh collider.
            Vector3 nearest = hit.bounds.ClosestPoint(origin);
            Vector3 flat = Vector3.ProjectOnPlane(nearest - origin, Vector3.up);
            // Standing on top of it, there is no direction to be wrong about.
            float angle = flat.sqrMagnitude < 0.0025f || forward.sqrMagnitude < 1e-6f
                ? 0f : Vector3.Angle(forward, flat);

            if (!Visible(target, hit)) continue;
            Add(into, target, Vector3.Distance(origin, nearest), angle);
        }
    }

    bool Visible(IInteractable target, Collider collider)
    {
        if (blockers.value == 0) return true;
        Transform anchor = target.Anchor;
        Vector3 to = anchor != null ? anchor.position : collider.bounds.center;
        if (!Physics.Linecast(Eye, to, out RaycastHit wall, blockers, QueryTriggerInteraction.Ignore))
            return true;
        // A gate is both a blocker and the thing being used: hitting the target itself is sight.
        return ReferenceEquals(wall.collider.GetComponentInParent<IInteractable>(), target);
    }

    void GatherRay(List<InteractionCandidate> into)
    {
        Ray ray = view != null ? new Ray(view.position, view.forward) : new Ray(Eye, transform.forward);
        int mask = interactable | blockers;
        RaycastHit hit;
        bool any = rayRadius > 0f
            ? Physics.SphereCast(ray, rayRadius, out hit, KeepRange, mask, QueryTriggerInteraction.Collide)
            : Physics.Raycast(ray, out hit, KeepRange, mask, QueryTriggerInteraction.Collide);
        if (!any) return;

        // First hit only: a wall in front of the switch is the answer, not an obstacle to skip.
        IInteractable target = hit.collider.GetComponentInParent<IInteractable>();
        if (target != null) Add(into, target, hit.distance, 0f);
    }
}
