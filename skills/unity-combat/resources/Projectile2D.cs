// Projectile2D — the 2D shot that cannot tunnel: every fixed step it casts a circle along the
// distance it is about to travel (speed × dt) and stops at the first thing in the way.
//
// Drop into a Runtime assembly beside DamageInfo.cs. Add it to the projectile prefab's root.
// The prefab needs NO Collider2D and NO Rigidbody2D: Continuous detection does nothing for a
// kinematic body or against a trigger, and hurtboxes are triggers. Set 'hitMask' to the Hurtbox
// layer plus the solid layers.
// REQUIRES com.unity.modules.physics2d (built in; read Packages/manifest.json).
//
// Fire it with Launch(). It reports the end of its flight through Finished — the place a pool
// takes it back; with no listener it switches its GameObject off.
//
//   var shot = pool.Get();                       // UnityEngine.Pool.ObjectPool<Projectile2D>
//   shot.Launch(muzzle.position, motor.Aim, CombatTeam.Runner, runner.gameObject);
using System;
using System.Collections.Generic;
using UnityEngine;

[DisallowMultipleComponent]
public sealed class Projectile2D : MonoBehaviour
{
    [Header("Flight")]
    [Tooltip("Units/s. The cast each step is speed × Time.fixedDeltaTime long: 0.28 units at 14.")]
    public float speed = 14f;
    [Tooltip("Radius of the cast, in world units.")]
    public float radius = 0.1f;
    [Tooltip("Seconds before it gives up. Range is speed × lifetime.")]
    public float lifetime = 1.2f;
    [Tooltip("The Hurtbox layer plus every solid layer. Hurtboxes are triggers and are included.")]
    public LayerMask hitMask;
    [Tooltip("Off, only the end point of each step is tested, and the shot passes through anything " +
             "thinner than speed × dt. It exists so a journey can show its gate fail.")]
    public bool sweep = true;

    [Header("The blow")]
    [Min(0)] public int damage = 1;
    public float knockback = 4f;
    public float stun = 0.1f;
    public DamageTags tags = DamageTags.Projectile;

    [Header("Homing")]
    [Tooltip("Degrees/s the direction may turn towards 'homingTarget'. 0 flies straight.")]
    public float turnRate = 0f;
    public Transform homingTarget;

    [Header("Presentation")]
    [Tooltip("A child holding the sprite and trail. It is placed between the last two simulated " +
             "positions each frame. Optional.")]
    public Transform visual;

    /// <summary>Raised once per flight, when it hits or its lifetime ends. Return it to the pool here.</summary>
    public event Action<Projectile2D> Finished;

    public bool Flying { get; private set; }
    public int Team { get; private set; }
    public GameObject Owner { get; private set; }
    public Vector2 Direction { get; private set; }
    /// <summary>What ended the flight; null when the lifetime ran out.</summary>
    public Collider2D StoppedBy { get; private set; }
    /// <summary>True when the flight ended on a receiver that accepted the damage.</summary>
    public bool DealtDamage { get; private set; }
    public float Travelled { get; private set; }

    readonly List<RaycastHit2D> _hits = new List<RaycastHit2D>(8);
    readonly List<Collider2D> _overlaps = new List<Collider2D>(8);
    float _age;
    Vector2 _previous;

    /// <summary>Start a flight. 'owner' is never hit, and 'team' is passed through.</summary>
    public void Launch(Vector2 position, Vector2 direction, int team, GameObject owner)
    {
        transform.position = new Vector3(position.x, position.y, transform.position.z);
        Direction = direction.sqrMagnitude > 1e-6f ? direction.normalized : (Vector2)transform.right;
        Face();
        Team = team;
        Owner = owner;
        StoppedBy = null;
        DealtDamage = false;
        Travelled = 0f;
        _age = 0f;
        _previous = position;
        Flying = true;
        gameObject.SetActive(true);
    }

    void FixedUpdate()
    {
        if (!Flying) return;
        float dt = Time.fixedDeltaTime;

        if (turnRate > 0f && homingTarget != null)
        {
            Vector2 wanted = (Vector2)homingTarget.position - (Vector2)transform.position;
            if (wanted.sqrMagnitude > 1e-6f)
            {
                Direction = ((Vector2)Vector3.RotateTowards(Direction, wanted.normalized,
                                                            turnRate * Mathf.Deg2Rad * dt, 0f)).normalized;
                Face();
            }
        }

        Vector2 from = transform.position;
        float distance = speed * dt;
        _previous = from;

        if (sweep ? Sweep(from, distance, out Collider2D hit, out Vector2 point, out float travelled)
                  : EndPointOnly(from + Direction * distance, distance, out hit, out point, out travelled))
        {
            MoveTo(from + Direction * travelled);
            Travelled += travelled;
            Stop(hit, point);
            return;
        }

        MoveTo(from + Direction * distance);
        Travelled += distance;
        _age += dt;
        if (_age >= lifetime) Stop(null, transform.position);
    }

    void Update()
    {
        if (visual == null || !Flying) return;
        float alpha = Mathf.Clamp01((Time.time - Time.fixedTime) / Time.fixedDeltaTime);
        Vector2 shown = Vector2.Lerp(_previous, transform.position, alpha);
        visual.position = new Vector3(shown.x, shown.y, visual.position.z);
    }

    // The nearest thing along this step that the shot does not pass through. The smallest
    // distance is picked here rather than trusting the order the list comes back in.
    bool Sweep(Vector2 from, float distance, out Collider2D hit, out Vector2 point, out float travelled)
    {
        hit = null; point = from; travelled = distance;
        int n = Physics2D.CircleCast(from, radius, Direction, Filter(), _hits, distance);
        float nearest = float.MaxValue;
        for (int i = 0; i < n; i++)
        {
            RaycastHit2D h = _hits[i];
            if (!Stops(h.collider) || h.distance >= nearest) continue;
            nearest = h.distance;
            hit = h.collider;
            point = h.point;
            travelled = h.distance;
        }
        return hit != null;
    }

    bool EndPointOnly(Vector2 at, float distance, out Collider2D hit, out Vector2 point, out float travelled)
    {
        hit = null; point = at; travelled = distance;
        int n = Physics2D.OverlapCircle(at, radius, Filter(), _overlaps);
        for (int i = 0; i < n; i++)
        {
            if (!Stops(_overlaps[i])) continue;
            hit = _overlaps[i];
            return true;
        }
        return false;
    }

    // A fresh ContactFilter2D leaves triggers out, and hurtboxes are triggers.
    ContactFilter2D Filter()
    {
        var filter = new ContactFilter2D();
        filter.SetLayerMask(hitMask);
        filter.useTriggers = true;
        return filter;
    }

    // Passes through its owner, its own team and the dead; stops on everything else in the mask.
    bool Stops(Collider2D c)
    {
        if (c == null) return false;
        if (Owner != null && c.transform.IsChildOf(Owner.transform)) return false;
        IDamageable target = c.GetComponentInParent<IDamageable>();
        if (target == null) return true;                    // level geometry
        return target.IsAlive && CombatTeam.CanDamage(Team, target.Team);
    }

    void Stop(Collider2D hit, Vector2 point)
    {
        Flying = false;
        StoppedBy = hit;
        if (visual != null)
            visual.position = new Vector3(transform.position.x, transform.position.y, visual.position.z);

        IDamageable target = hit != null ? hit.GetComponentInParent<IDamageable>() : null;
        if (target != null)
        {
            var info = new DamageInfo
            {
                amount = damage,
                source = Owner,
                team = Team,
                point = point,
                direction = Direction,
                knockback = knockback,
                stun = stun,
                tags = tags,
            };
            DealtDamage = target.TakeDamage(info);
        }

        if (Finished != null) Finished(this);
        else gameObject.SetActive(false);
    }

    void MoveTo(Vector2 p) => transform.position = new Vector3(p.x, p.y, transform.position.z);

    // Sprites are drawn pointing along +X.
    void Face() => transform.rotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(Direction.y, Direction.x) * Mathf.Rad2Deg);
}
