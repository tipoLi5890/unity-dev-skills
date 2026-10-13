// Projectile3D — a shot that cannot tunnel, because it is never simulated: every fixed step it
// casts a sphere along the distance it is about to travel (speed × dt) and stops at the first
// thing in the way.
//
// Drop into a Runtime assembly beside DamageInfo.cs. Add it to the projectile prefab's root.
// The prefab needs NO Collider and NO Rigidbody: a body here would be a second writer of the
// position and a second, tunnelling, opinion about what was hit. Set 'hitMask' to the Hurtbox
// layer plus the solid layers.
// REQUIRES com.unity.modules.physics (built in; read Packages/manifest.json).
//
// Fire it with Launch(). It reports the end of its flight through Finished — the place a pool
// takes it back; with no listener it switches its GameObject off.
//
//   var shot = pool.Get();                       // UnityEngine.Pool.ObjectPool<Projectile3D>
//   shot.Launch(muzzle.position, muzzle.forward, CombatTeam.Runner, runner.gameObject);
using System;
using UnityEngine;

[DisallowMultipleComponent]
public sealed class Projectile3D : MonoBehaviour
{
    [Header("Flight")]
    [Tooltip("Units/s. The cast each step is speed × Time.fixedDeltaTime long: 0.6 units at 30.")]
    public float speed = 30f;
    [Tooltip("Radius of the cast, in world units.")]
    public float radius = 0.1f;
    [Tooltip("Seconds before it gives up. Range is speed × lifetime.")]
    public float lifetime = 2f;
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
    [Tooltip("A child holding the mesh and trail. It is placed between the last two simulated " +
             "positions each frame, so a 50 Hz shot does not stutter at 120 Hz. Optional.")]
    public Transform visual;

    /// <summary>Raised once per flight, when it hits or its lifetime ends. Return it to the pool here.</summary>
    public event Action<Projectile3D> Finished;

    public bool Flying { get; private set; }
    public int Team { get; private set; }
    public GameObject Owner { get; private set; }
    public Vector3 Direction { get; private set; }
    /// <summary>What ended the flight; null when the lifetime ran out.</summary>
    public Collider StoppedBy { get; private set; }
    /// <summary>True when the flight ended on a receiver that accepted the damage.</summary>
    public bool DealtDamage { get; private set; }
    public float Travelled { get; private set; }

    readonly RaycastHit[] _hits = new RaycastHit[8];
    readonly Collider[] _overlaps = new Collider[8];
    float _age;
    Vector3 _previous;

    /// <summary>Start a flight. 'owner' is never hit, and 'team' is passed through.</summary>
    public void Launch(Vector3 position, Vector3 direction, int team, GameObject owner)
    {
        transform.position = position;
        Direction = direction.sqrMagnitude > 1e-6f ? direction.normalized : transform.forward;
        transform.rotation = Quaternion.LookRotation(Direction);
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
            Vector3 wanted = homingTarget.position - transform.position;
            if (wanted.sqrMagnitude > 1e-6f)
            {
                Direction = Vector3.RotateTowards(Direction, wanted.normalized,
                                                  turnRate * Mathf.Deg2Rad * dt, 0f).normalized;
                transform.rotation = Quaternion.LookRotation(Direction);
            }
        }

        Vector3 from = transform.position;
        float distance = speed * dt;
        _previous = from;

        if (sweep ? Sweep(from, distance, out Collider hit, out Vector3 point, out float travelled)
                  : EndPointOnly(from + Direction * distance, distance, out hit, out point, out travelled))
        {
            transform.position = from + Direction * travelled;
            Travelled += travelled;
            Stop(hit, point);
            return;
        }

        transform.position = from + Direction * distance;
        Travelled += distance;
        _age += dt;
        if (_age >= lifetime) Stop(null, transform.position);
    }

    void Update()
    {
        if (visual == null || !Flying) return;
        float alpha = Mathf.Clamp01((Time.time - Time.fixedTime) / Time.fixedDeltaTime);
        visual.position = Vector3.Lerp(_previous, transform.position, alpha);
    }

    // The nearest thing along this step that the shot does not pass through.
    bool Sweep(Vector3 from, float distance, out Collider hit, out Vector3 point, out float travelled)
    {
        hit = null; point = from; travelled = distance;
        int n = Physics.SphereCastNonAlloc(from, radius, Direction, _hits, distance, hitMask,
                                           QueryTriggerInteraction.Collide);
        float nearest = float.MaxValue;
        for (int i = 0; i < n; i++)
        {
            RaycastHit h = _hits[i];
            if (!Stops(h.collider) || h.distance >= nearest) continue;
            nearest = h.distance;
            hit = h.collider;
            // A collider the sphere already overlaps at the start is reported at distance 0 with
            // point (0,0,0); the shot is where the contact is.
            point = h.distance > 0f ? h.point : from;
            travelled = h.distance;
        }
        return hit != null;
    }

    bool EndPointOnly(Vector3 at, float distance, out Collider hit, out Vector3 point, out float travelled)
    {
        hit = null; point = at; travelled = distance;
        int n = Physics.OverlapSphereNonAlloc(at, radius, _overlaps, hitMask, QueryTriggerInteraction.Collide);
        for (int i = 0; i < n; i++)
        {
            if (!Stops(_overlaps[i])) continue;
            hit = _overlaps[i];
            return true;
        }
        return false;
    }

    // Passes through its owner, its own team and the dead; stops on everything else in the mask.
    bool Stops(Collider c)
    {
        if (c == null) return false;
        if (Owner != null && c.transform.IsChildOf(Owner.transform)) return false;
        IDamageable target = c.GetComponentInParent<IDamageable>();
        if (target == null) return true;                    // level geometry
        return target.IsAlive && CombatTeam.CanDamage(Team, target.Team);
    }

    void Stop(Collider hit, Vector3 point)
    {
        Flying = false;
        StoppedBy = hit;
        if (visual != null) visual.position = transform.position;

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
}
