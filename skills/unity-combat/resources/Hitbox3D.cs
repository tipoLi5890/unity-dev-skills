// Hitbox3D — a melee volume that is a QUERY, not a trigger: while a window is open it asks
// PhysX which hurtboxes its box overlaps or swept through this step, and it — not the engine —
// remembers who this swing has already hit.
//
// Drop into a Runtime assembly beside DamageInfo.cs. Add it to an empty child of the attacker
// placed where the blow lands (in front of the runner, or on the weapon bone). It needs no
// Collider and no Rigidbody of its own. Set 'hurtMask' to the Hurtbox layer.
// REQUIRES com.unity.modules.physics (built in; read Packages/manifest.json).
//
// Whoever owns the attack calls Open() when the active frames start and Close() when they end:
// an IAttackWindowReceiver beside the Animator (skill unity-animation, AttackWindowBehaviour.cs),
// or a timer in the game's own attacking state. Every Open() is a new swing with an empty hit
// list; a move that hits three times is three windows.
//
// Register with the probe where the game wires its harness:
//   GameProbe.Register("hitboxOpen", () => hitbox.IsOpen);
//   GameProbe.Count("swings", () => hitbox.SwingId);
using System;
using System.Collections.Generic;
using UnityEngine;

[DisallowMultipleComponent]
public sealed class Hitbox3D : MonoBehaviour
{
    [Header("Who is attacking")]
    [Tooltip("The attacker's root: never hit, and reported as DamageInfo.source. Empty: transform.root.")]
    public GameObject owner;
    [Tooltip("CombatTeam.Neutral 0, Runner 1, Sentry 2. Targets of the same team are passed over.")]
    public int team = CombatTeam.Runner;

    [Header("The blow")]
    [Min(0)] public int damage = 1;
    [Tooltip("Launch speed handed to the target's controller, units/s.")]
    public float knockback = 8f;
    [Tooltip("Seconds the target is without control.")]
    public float stun = 0.15f;
    public DamageTags tags = DamageTags.Melee;
    [Tooltip("Knock-back direction keeps no vertical part: the target is pushed along the floor.")]
    public bool planar = true;

    [Header("The volume")]
    [Tooltip("Half the box, in world units. Not multiplied by the transform's scale: a hit volume " +
             "is an authored constant, not a property of the mesh.")]
    public Vector3 halfExtents = new Vector3(0.5f, 0.5f, 0.5f);
    [Tooltip("The Hurtbox layer, and only that.")]
    public LayerMask hurtMask;
    [Tooltip("Solid layers. A target with one of these between it and the owner is not hit. " +
             "Nothing: hits reach through walls.")]
    public LayerMask blockMask;
    [Tooltip("From the owner's pivot to where the blow comes from — chest height.")]
    public Vector3 originOffset = new Vector3(0f, 1f, 0f);

    [Header("Rules")]
    [Tooltip("Also cast the box from where it was last step to where it is now, so a fast swing " +
             "cannot step over a target.")]
    public bool sweep = true;
    [Tooltip("A target is offered each swing once. Off, every overlapping collider deals damage on " +
             "every step — a beam held on a target, limited only by the target's own invincibility.")]
    public bool oncePerSwing = true;

    /// <summary>Raised when a hit is accepted by its target. Presentation hangs here.</summary>
    public event Action<IDamageable, DamageInfo> Landed;

    public bool IsOpen => _open;
    /// <summary>Counts every Open(); the id carried by the DamageInfo of the current swing.</summary>
    public int SwingId { get; private set; }
    /// <summary>Hits accepted by a target during the current swing.</summary>
    public int HitsThisSwing { get; private set; }
    /// <summary>Hurtbox colliders, the owner's own left out, that the queries returned this swing, once per
    /// step each. Far above HitsThisSwing is normal: that difference is what the hit list absorbs.</summary>
    public int ContactsThisSwing { get; private set; }
    /// <summary>Hits accepted over the life of this component; Open() does not reset it.</summary>
    public int TotalHits { get; private set; }

    readonly List<IDamageable> _hit = new List<IDamageable>(8);
    readonly Collider[] _overlaps = new Collider[16];
    readonly RaycastHit[] _casts = new RaycastHit[16];
    bool _open;
    bool _queried;
    bool _warnedFull;
    Vector3 _last;

    Transform Owner => owner != null ? owner.transform : transform.root;

    /// <summary>Start a swing: a new id, an empty hit list. Returns the id.</summary>
    public int Open()
    {
        // Two opens in a row is a window whose close was lost; end it rather than merge two swings.
        if (_open) Close();
        SwingId++;
        _hit.Clear();
        HitsThisSwing = 0;
        ContactsThisSwing = 0;
        _last = transform.position;
        _queried = false;
        _open = true;
        return SwingId;
    }

    /// <summary>End the swing. Safe to call when it is already closed.</summary>
    public void Close()
    {
        if (!_open) return;
        // A window shorter than one fixed step (a hitch that jumped over it) still asks once.
        // The pose was written by the Animator this frame, so PhysX is told first.
        if (!_queried)
        {
            Physics.SyncTransforms();
            Query();
        }
        _open = false;
    }

    void OnDisable() => _open = false;

    void FixedUpdate()
    {
        if (_open) Query();
    }

    void Query()
    {
        _queried = true;
        Vector3 at = transform.position;
        Quaternion rot = transform.rotation;

        // Hurtboxes are triggers; say so, whatever Physics.queriesHitTriggers is set to.
        int n = Physics.OverlapBoxNonAlloc(at, halfExtents, _overlaps, rot, hurtMask,
                                           QueryTriggerInteraction.Collide);
        WarnWhenFull(n, _overlaps.Length);
        for (int i = 0; i < n; i++) Consider(_overlaps[i]);

        if (sweep)
        {
            Vector3 delta = at - _last;
            float distance = delta.magnitude;
            if (distance > 1e-4f)
            {
                int m = Physics.BoxCastNonAlloc(_last, halfExtents, delta / distance, _casts, rot,
                                                distance, hurtMask, QueryTriggerInteraction.Collide);
                WarnWhenFull(m, _casts.Length);
                for (int i = 0; i < m; i++) Consider(_casts[i].collider);
            }
        }
        _last = at;
    }

    void Consider(Collider hurtbox)
    {
        if (hurtbox == null) return;
        Transform ownerRoot = Owner;
        if (hurtbox.transform.IsChildOf(ownerRoot)) return;
        ContactsThisSwing++;

        // Two hurtboxes of one sentry resolve to the same receiver: that is the dedupe key.
        IDamageable target = hurtbox.GetComponentInParent<IDamageable>();
        if (target == null || !target.IsAlive) return;
        if (!CombatTeam.CanDamage(team, target.Team)) return;
        if (oncePerSwing && _hit.Contains(target)) return;

        Vector3 from = ownerRoot.position + originOffset;
        // ClosestPoint needs a primitive or a convex mesh; hurtboxes are primitives.
        Vector3 point = hurtbox.ClosestPoint(transform.position);
        if (blockMask.value != 0 &&
            Physics.Linecast(from, point, blockMask, QueryTriggerInteraction.Ignore)) return;

        // Listed before the receiver answers: a target that refuses for invincibility has had
        // this swing's one chance, and is not hit when its timer runs out mid-swing.
        if (oncePerSwing) _hit.Add(target);

        Vector3 direction = hurtbox.bounds.center - from;
        if (planar) direction.y = 0f;
        direction = direction.sqrMagnitude > 1e-6f ? direction.normalized : ownerRoot.forward;

        var info = new DamageInfo
        {
            amount = damage,
            source = ownerRoot.gameObject,
            team = team,
            point = point,
            direction = direction,
            knockback = knockback,
            stun = stun,
            tags = tags,
            swingId = SwingId,
        };
        if (!target.TakeDamage(info)) return;
        HitsThisSwing++;
        TotalHits++;
        Landed?.Invoke(target, info);
    }

    void WarnWhenFull(int count, int capacity)
    {
        if (count < capacity || _warnedFull) return;
        _warnedFull = true;
        Debug.LogWarning("[COMBAT] Hitbox3D on " + name + " filled its " + capacity +
                         "-entry buffer; targets beyond it were not seen. Narrow hurtMask or the box.", this);
    }

    void OnDrawGizmosSelected()
    {
        Gizmos.color = _open ? Color.red : new Color(1f, 0.5f, 0f, 0.6f);
        Gizmos.matrix = Matrix4x4.TRS(transform.position, transform.rotation, Vector3.one);
        Gizmos.DrawWireCube(Vector3.zero, halfExtents * 2f);
    }
}
