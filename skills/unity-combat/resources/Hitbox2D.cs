// Hitbox2D — the 2D melee volume: a box QUERY against the Hurtbox layer on every fixed step of
// an open window, with a swing id and the list of who this swing has already hit.
//
// Drop into a Runtime assembly beside DamageInfo.cs. Add it to an empty child of the attacker
// placed where the blow lands. It needs no Collider2D and no Rigidbody2D of its own. Set
// 'hurtMask' to the Hurtbox layer.
// REQUIRES com.unity.modules.physics2d (built in; read Packages/manifest.json).
//
// Whoever owns the attack calls Open() when the active frames start and Close() when they end:
// an IAttackWindowReceiver beside the Animator (skill unity-animation, AttackWindowBehaviour.cs),
// or a timer in the game's own attacking state. Every Open() is a new swing with an empty hit
// list; a move that hits three times is three windows.
//
// The box turns with the transform's Z rotation. For a sprite flipped by scale, move the child
// to the other side from the facing; a negative scale does not mirror a query.
using System;
using System.Collections.Generic;
using UnityEngine;

[DisallowMultipleComponent]
public sealed class Hitbox2D : MonoBehaviour
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

    [Header("The volume")]
    [Tooltip("Full width and height of the box, in world units. Not multiplied by the transform's scale.")]
    public Vector2 size = new Vector2(1f, 1f);
    [Tooltip("The Hurtbox layer, and only that.")]
    public LayerMask hurtMask;
    [Tooltip("Solid layers. A target with one of these between it and the owner is not hit. " +
             "Nothing: hits reach through walls.")]
    public LayerMask blockMask;
    [Tooltip("From the owner's pivot to where the blow comes from.")]
    public Vector2 originOffset = new Vector2(0f, 0f);

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
    /// step each.</summary>
    public int ContactsThisSwing { get; private set; }
    /// <summary>Hits accepted over the life of this component; Open() does not reset it.</summary>
    public int TotalHits { get; private set; }

    readonly List<IDamageable> _hit = new List<IDamageable>(8);
    readonly List<Collider2D> _overlaps = new List<Collider2D>(16);
    readonly List<RaycastHit2D> _casts = new List<RaycastHit2D>(16);
    // Its own list: the line-of-sight test runs while _casts is being walked.
    readonly List<RaycastHit2D> _blockers = new List<RaycastHit2D>(4);
    bool _open;
    bool _queried;
    Vector2 _last;

    Transform Owner => owner != null ? owner.transform : transform.root;

    /// <summary>Start a swing: a new id, an empty hit list. Returns the id.</summary>
    public int Open()
    {
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
        // A window shorter than one fixed step still asks once, after telling Box2D where the
        // Animator put things this frame.
        if (!_queried)
        {
            Physics2D.SyncTransforms();
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
        Vector2 at = transform.position;
        float angle = transform.eulerAngles.z;

        // A fresh ContactFilter2D leaves triggers out, and hurtboxes are triggers.
        var filter = new ContactFilter2D();
        filter.SetLayerMask(hurtMask);
        filter.useTriggers = true;

        int n = Physics2D.OverlapBox(at, size, angle, filter, _overlaps);
        for (int i = 0; i < n; i++) Consider(_overlaps[i]);

        if (sweep)
        {
            Vector2 delta = at - _last;
            float distance = delta.magnitude;
            if (distance > 1e-4f)
            {
                int m = Physics2D.BoxCast(_last, size, angle, delta / distance, filter, _casts, distance);
                for (int i = 0; i < m; i++) Consider(_casts[i].collider);
            }
        }
        _last = at;
    }

    void Consider(Collider2D hurtbox)
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

        Vector2 from = (Vector2)ownerRoot.position + originOffset;
        Vector2 point = hurtbox.ClosestPoint(transform.position);
        if (blockMask.value != 0 && Blocked(from, point)) return;

        // Listed before the receiver answers: a target that refuses for invincibility has had
        // this swing's one chance.
        if (oncePerSwing) _hit.Add(target);

        Vector2 direction = (Vector2)hurtbox.bounds.center - from;
        direction = direction.sqrMagnitude > 1e-6f ? direction.normalized : (Vector2)ownerRoot.right;

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

    bool Blocked(Vector2 from, Vector2 to)
    {
        var solid = new ContactFilter2D();
        solid.SetLayerMask(blockMask);
        solid.useTriggers = false;
        return Physics2D.Linecast(from, to, solid, _blockers) > 0;
    }

    void OnDrawGizmosSelected()
    {
        Gizmos.color = _open ? Color.red : new Color(1f, 0.5f, 0f, 0.6f);
        Gizmos.matrix = Matrix4x4.TRS(transform.position,
                                      Quaternion.Euler(0f, 0f, transform.eulerAngles.z), Vector3.one);
        Gizmos.DrawWireCube(Vector3.zero, size);
    }
}
