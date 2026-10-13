// Interactor2D — detection for a 2D actor, in two modes:
//   TriggerList   side view and top-down: a trigger collider on the runner is the reach; what
//                 enters it joins a list, what leaves is removed, the nearest in the list wins
//   Overlap       one circle on a tick, with an optional facing cone and a line of sight —
//                 for a runner with no sensor collider, or when the reach needs a kept margin
//
// Drop into the same Runtime assembly as IInteractable.cs and add it to the runner, beside its
// Rigidbody2D and RunInputSource (skill unity-input → resources/). TriggerList needs a trigger
// Collider2D on this object or a child of the same body, sized to the reach, and a Rigidbody2D
// on the runner or on the interactable. REQUIRES com.unity.modules.physics2d (built in; read
// Packages/manifest.json).
//
// Selection, the press and the hold are InteractorBase's; this file only answers "what is in
// reach".
using System;
using System.Collections.Generic;
using UnityEngine;

public enum InteractDetect2D { TriggerList, Overlap }

[DisallowMultipleComponent]
[AddComponentMenu("Courier/Interactor 2D")]
public sealed class Interactor2D : InteractorBase
{
    [Header("Detection")]
    public InteractDetect2D mode = InteractDetect2D.TriggerList;
    [Tooltip("Layers that hold interactables. Never the runner's own layer.")]
    public LayerMask interactable = Physics2D.DefaultRaycastLayers;
    [Tooltip("Solid layers that hide an interactable: shelving, walls. Empty skips the line-of-sight test.")]
    public LayerMask blockers = 0;
    [Tooltip("Degrees either side of the facing. 180 selects all round; a cone needs Facing assigned.")]
    public float halfAngle = 180f;
    [Tooltip("Where the reach is measured from, relative to the runner.")]
    public Vector2 originOffset = Vector2.zero;

    /// <summary>The runner's facing, from its motor. Unassigned means no cone, whatever halfAngle says.</summary>
    public Func<Vector2> Facing;

    struct Near
    {
        public Collider2D collider;
        public IInteractable target;
    }

    readonly List<Near> _near = new List<Near>(8);
    readonly List<Collider2D> _overlaps = new List<Collider2D>(16);
    readonly List<RaycastHit2D> _sight = new List<RaycastHit2D>(4);
    ContactFilter2D _find;
    ContactFilter2D _walls;

    protected override float HalfAngle => Facing == null ? 180f : halfAngle;
    // The sensor collider is the reach: applying 'range' as well would be a second, different one.
    protected override bool GateByRange => mode != InteractDetect2D.TriggerList;

    Vector2 Origin => (Vector2)transform.position + originOffset;

    void OnTriggerEnter2D(Collider2D other)
    {
        if ((interactable.value & (1 << other.gameObject.layer)) == 0) return;
        IInteractable target = other.GetComponentInParent<IInteractable>();
        if (target == null) return;
        for (int i = 0; i < _near.Count; i++)
            if (_near[i].collider == other) return;
        _near.Add(new Near { collider = other, target = target });
    }

    void OnTriggerExit2D(Collider2D other)
    {
        for (int i = _near.Count - 1; i >= 0; i--)
            if (_near[i].collider == other) _near.RemoveAt(i);
    }

    protected override void OnDisable()
    {
        _near.Clear();
        base.OnDisable();
    }

    protected override void Gather(List<InteractionCandidate> into)
    {
        if (mode == InteractDetect2D.TriggerList) GatherList(into);
        else GatherOverlap(into);
    }

    void GatherList(List<InteractionCandidate> into)
    {
        Vector2 origin = Origin;
        for (int i = _near.Count - 1; i >= 0; i--)
        {
            Collider2D c = _near[i].collider;
            // A pickup returned to its pool while inside the sensor may never send an exit.
            if (c == null || !c.enabled || !c.gameObject.activeInHierarchy)
            {
                _near.RemoveAt(i);
                continue;
            }
            Consider(into, origin, c, _near[i].target);
        }
    }

    void GatherOverlap(List<InteractionCandidate> into)
    {
        Vector2 origin = Origin;
        _find.SetLayerMask(interactable);
        _find.useTriggers = true;                 // a switch is usually a trigger
        Physics2D.OverlapCircle(origin, KeepRange, _find, _overlaps);
        for (int i = 0; i < _overlaps.Count; i++)
        {
            IInteractable target = _overlaps[i].GetComponentInParent<IInteractable>();
            if (target != null) Consider(into, origin, _overlaps[i], target);
        }
    }

    void Consider(List<InteractionCandidate> into, Vector2 origin, Collider2D collider, IInteractable target)
    {
        Vector2 nearest = collider.ClosestPoint(origin);
        Vector2 to = nearest - origin;
        float angle = 0f;
        if (Facing != null && to.sqrMagnitude > 0.0025f)
        {
            Vector2 facing = Facing();
            if (facing.sqrMagnitude > 1e-6f) angle = Vector2.Angle(facing, to);
        }
        if (!Visible(origin, collider, target)) return;
        Add(into, target, to.magnitude, angle);
    }

    bool Visible(Vector2 origin, Collider2D collider, IInteractable target)
    {
        if (blockers.value == 0) return true;
        Transform anchor = target.Anchor;
        Vector2 to = anchor != null ? (Vector2)anchor.position : (Vector2)collider.bounds.center;
        _walls.SetLayerMask(blockers);
        _walls.useTriggers = false;
        int hits = Physics2D.Linecast(origin, to, _walls, _sight);
        if (hits == 0) return true;
        // The nearest hit decides: the target's own solid collider is sight, anything else a wall.
        int nearest = 0;
        for (int i = 1; i < hits; i++)
            if (_sight[i].fraction < _sight[nearest].fraction) nearest = i;
        return ReferenceEquals(_sight[nearest].collider.GetComponentInParent<IInteractable>(), target);
    }
}
