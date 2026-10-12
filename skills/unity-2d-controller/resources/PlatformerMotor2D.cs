// PlatformerMotor2D — the collision half of a side-view character: it is handed a velocity,
// asks the physics engine what is in the way, and reports where the ground, ceiling and walls are.
//
// Drop into a Runtime assembly and add it to the runner beside a Rigidbody2D and one solid
// Collider2D (a BoxCollider2D or CapsuleCollider2D). Awake sets the body to Kinematic with
// rotation frozen; set Interpolate on the body in the Inspector for a camera that follows it.
// REQUIRES com.unity.modules.physics2d (built in; read Packages/manifest.json).
//
// It decides nothing: no input, no gravity, no jump. PlatformerController2D.cs (the rules half)
// owns the velocity and calls Move once per FixedUpdate. Exactly one script calls Move.
//
//   Vector2 v = ...rules...;
//   v = motor.Move(v, Time.fixedDeltaTime);      // blocked components come back as zero
//
// The cast sweeps every collider attached to this body, so keep hurtboxes and pickup magnets on
// a child object with its own kinematic Rigidbody2D, not on this one.
using System.Collections.Generic;
using UnityEngine;

[DisallowMultipleComponent]
[RequireComponent(typeof(Rigidbody2D))]
public sealed class PlatformerMotor2D : MonoBehaviour
{
    [Header("What stops the runner")]
    [Tooltip("Rooftops, walls, ceilings: solid from every side.")]
    public LayerMask solid;
    [Tooltip("Platforms that are solid from above only. A separate layer, never part of 'solid'.")]
    public LayerMask oneWay;

    [Header("Contact")]
    [Tooltip("The gap kept between the body and any surface. Keep it above Physics2D.defaultContactOffset (0.01): a cast that starts touching reports nothing useful.")]
    public float skin = 0.02f;
    [Tooltip("Steepest surface that counts as ground, in degrees. Anything steeper is a wall and the runner slides off it.")]
    public float maxSlopeAngle = 50f;
    [Tooltip("How far below the feet a grounded runner is pulled back onto the ground. Keeps it on a down-slope and over a crest.")]
    public float groundSnap = 0.25f;
    [Tooltip("How far to the side a wall is looked for when the runner is not moving into it.")]
    public float wallProbe = 0.06f;
    [Tooltip("Seconds a drop through a one-way platform ignores that layer.")]
    public float dropSeconds = 0.25f;
    [Tooltip("Keep a moving platform's velocity when the runner leaves it.")]
    public bool inheritPlatformVelocity = true;

    /// <summary>Standing on a surface no steeper than maxSlopeAngle, as of the last Move.</summary>
    public bool Grounded { get; private set; }
    /// <summary>Unit normal of the ground, or up when airborne.</summary>
    public Vector2 GroundNormal { get; private set; } = Vector2.up;
    /// <summary>Angle between the ground and level, in degrees.</summary>
    public float GroundAngle => Vector2.Angle(GroundNormal, Vector2.up);
    public Collider2D Ground { get; private set; }
    /// <summary>The ground is on the one-way layer, so DropThrough has something to drop through.</summary>
    public bool OnOneWay { get; private set; }
    /// <summary>The upward part of the last Move was stopped.</summary>
    public bool OnCeiling { get; private set; }
    /// <summary>-1 a wall on the left, +1 on the right, 0 none.</summary>
    public int WallSide { get; private set; }
    /// <summary>The platform under the feet, or null.</summary>
    public MovingPlatform2D Platform { get; private set; }
    /// <summary>What the body did over the last Move, platform carry included — the value a probe or a camera wants.</summary>
    public Vector2 Velocity { get; private set; }
    public Vector2 Position => _body.position;
    public Rigidbody2D Body => _body;

    const float MinMove = 1e-5f;
    // How far past a landing sweep a rising platform is still looked for: one step of a lift at
    // 25 units/s.
    const float LiftLook = 0.5f;

    Rigidbody2D _body;
    Collider2D _collider;
    ContactFilter2D _solidFilter;
    ContactFilter2D _allFilter;
    readonly List<RaycastHit2D> _hits = new List<RaycastHit2D>(8);
    readonly List<Collider2D> _overlaps = new List<Collider2D>(8);
    float _minGroundNormalY;
    float _dropUntil = -1f;
    float _dt;
    float _hitRise;          // set by Sweep: how far the platform it reported rises this step

    void Awake()
    {
        _body = GetComponent<Rigidbody2D>();
        _body.bodyType = RigidbodyType2D.Kinematic;
        _body.freezeRotation = true;
        // Kinematic bodies do not report contacts with static or kinematic ones unless asked.
        // Nothing here needs them; triggers fire either way.
        foreach (Collider2D c in GetComponents<Collider2D>())
            if (!c.isTrigger) { _collider = c; break; }
        if (_collider == null)
            Debug.LogError("[MOTOR2D] no solid Collider2D beside the Rigidbody2D on " + name, this);
        Configure();
    }

    void OnValidate() => Configure();

    /// <summary>Re-read the masks and the slope limit. Call it after changing them from script.</summary>
    public void Configure()
    {
        _solidFilter = new ContactFilter2D();
        _solidFilter.SetLayerMask(solid);
        _solidFilter.useTriggers = false;
        _allFilter = new ContactFilter2D();
        _allFilter.SetLayerMask(solid.value | oneWay.value);
        _allFilter.useTriggers = false;
        _minGroundNormalY = Mathf.Cos(maxSlopeAngle * Mathf.Deg2Rad);
        if (Application.isPlaying && (solid.value & oneWay.value) != 0)
            Debug.LogError("[MOTOR2D] 'solid' and 'oneWay' share a layer: the runner can never pass up through it", this);
    }

    /// <summary>Ignore the one-way layer for dropSeconds. The caller decides when (down held and the press spent).</summary>
    public void DropThrough()
    {
        if (!OnOneWay) return;
        _dropUntil = Time.time + dropSeconds;
        Grounded = false;
        Ground = null;
        Platform = null;
    }

    /// <summary>Place the runner somewhere without a sweep: a respawn, a situation, a door.</summary>
    public void Teleport(Vector2 position)
    {
        _body.position = position;
        transform.position = new Vector3(position.x, position.y, transform.position.z);
        Physics2D.SyncTransforms();
        Grounded = false;
        Ground = null;
        Platform = null;
        GroundNormal = Vector2.up;
        Velocity = Vector2.zero;
    }

    /// <summary>
    /// Move by velocity * dt, stopping at whatever is in the way. Returns the velocity the rules
    /// should carry into the next step: x is zero after a wall, y is zero after a floor or a
    /// ceiling, and a platform's velocity is added on the step the runner leaves it.
    /// </summary>
    public Vector2 Move(Vector2 velocity, float dt)
    {
        if (dt <= 0f) return velocity;
        _dt = dt;

        Vector2 start = _body.position;
        Vector2 pos = Depenetrate(start);
        bool wasGrounded = Grounded;
        MovingPlatform2D wasOn = Platform;
        Vector2 groundNormal = GroundNormal;
        bool rising = velocity.y > 0f;

        OnCeiling = false;
        WallSide = 0;

        // 1 · carry. The platform publishes this step's velocity before the runner reads it, and
        // both bodies are moved by the same simulation step, so the feet do not lag or sink.
        // Sideways now; the vertical part waits for step 6.
        if (wasGrounded && wasOn != null)
        {
            float carry = wasOn.Velocity.x * dt;
            if (Mathf.Abs(carry) > MinMove)
            {
                Vector2 side = new Vector2(Mathf.Sign(carry), 0f);
                float want = Mathf.Abs(carry);
                pos += side * (Sweep(pos, side, want, false, out RaycastHit2D blocked)
                    ? Mathf.Clamp(blocked.distance - skin, 0f, want) : want);
            }
        }

        // 2 · along the ground, or level in the air.
        float dx = velocity.x * dt;
        if (Mathf.Abs(dx) > MinMove)
        {
            float sign = Mathf.Sign(dx);
            Vector2 dir = wasGrounded && !rising ? Tangent(groundNormal, sign) : new Vector2(sign, 0f);
            float remaining = Mathf.Abs(dx);
            for (int pass = 0; pass < 2 && remaining > MinMove; pass++)
            {
                if (!Sweep(pos, dir, remaining, false, out RaycastHit2D hit))
                {
                    pos += dir * remaining;
                    break;
                }
                float travel = Mathf.Clamp(hit.distance - skin, 0f, remaining);
                pos += dir * travel;
                remaining -= travel;
                if (Walkable(hit.normal))
                {
                    // A slope met from level ground: spend what is left along it, once.
                    if (pass == 0) { dir = Tangent(hit.normal, sign); continue; }
                    break;
                }
                WallSide = (int)sign;
                velocity.x = 0f;
                break;
            }
        }

        // 3 · vertical.
        Grounded = false;
        float dy = velocity.y * dt;
        if (dy > MinMove)
        {
            if (Sweep(pos, Vector2.up, dy, false, out RaycastHit2D hit))
            {
                pos.y += Mathf.Clamp(hit.distance - skin, 0f, dy);
                OnCeiling = true;
                velocity.y = 0f;
            }
            else pos.y += dy;
        }
        else if (dy < -MinMove)
        {
            float fall = -dy;
            if (Sweep(pos, Vector2.down, fall, true, out RaycastHit2D hit))
            {
                // Further than the fall only onto a platform that is rising to meet the feet.
                float travel = Mathf.Clamp(hit.distance - skin, 0f, fall + _hitRise);
                pos.y -= travel;
                if (Walkable(hit.normal))
                {
                    Land(hit);
                    velocity.y = 0f;
                }
                else
                {
                    // Too steep to stand on: the rest of the fall goes down the surface. The
                    // fall speed is kept, so the slide accelerates like the fall it is.
                    Vector2 down = Tangent(hit.normal, 1f);
                    if (down.y > 0f) down = -down;
                    float slide = Mathf.Max(0f, fall - travel) * -down.y;
                    if (slide > MinMove)
                        pos += down * (Sweep(pos, down, slide, true, out RaycastHit2D stop)
                            ? Mathf.Clamp(stop.distance - skin, 0f, slide) : slide);
                }
            }
            else pos.y -= fall;
        }

        // 4 · the ground under a runner that is not rising: a short look when airborne, a longer
        // one with a pull-down when it was grounded, which is what keeps it on a down-slope.
        if (!Grounded && !rising)
        {
            float reach = wasGrounded ? Mathf.Max(groundSnap, skin * 2f) : skin * 2f;
            if (Sweep(pos, Vector2.down, reach, true, out RaycastHit2D under) && Walkable(under.normal))
            {
                if (wasGrounded) pos.y -= Mathf.Clamp(under.distance - skin, 0f, reach + _hitRise);
                Land(under);
                if (velocity.y < 0f) velocity.y = 0f;
            }
        }
        if (!Grounded)
        {
            Ground = null;
            OnOneWay = false;
            Platform = null;
            GroundNormal = Vector2.up;
        }

        // 5 · a wall the runner is beside but not pushing into, for the wall slide.
        if (WallSide == 0 && !Grounded && wallProbe > 0f)
        {
            if (Sweep(pos, Vector2.right, wallProbe, false, out RaycastHit2D r) && !Walkable(r.normal)) WallSide = 1;
            else if (Sweep(pos, Vector2.left, wallProbe, false, out RaycastHit2D l) && !Walkable(l.normal)) WallSide = -1;
        }

        // 6 · the lift's rise or fall, last. Every cast above saw the platform where it is now,
        // not where this step takes it: lifted first, the ground look would pull the feet back
        // down onto the old pose; lowered first, they would start inside it.
        if (Grounded && Platform != null) pos.y += Platform.Velocity.y * dt;

        Velocity = (pos - start) / dt;
        _body.MovePosition(pos);

        if (wasGrounded && !Grounded && wasOn != null && inheritPlatformVelocity)
        {
            // Only the upward part: a platform going down must not shorten the jump off it.
            Vector2 pv = wasOn.Velocity;
            velocity += new Vector2(pv.x, Mathf.Max(0f, pv.y));
        }
        return velocity;
    }

    bool Walkable(Vector2 normal) => normal.y >= _minGroundNormalY;

    // The direction along a surface: sign +1 runs right, -1 left.
    static Vector2 Tangent(Vector2 normal, float sign) => new Vector2(normal.y, -normal.x) * sign;

    void Land(RaycastHit2D hit)
    {
        Grounded = true;
        GroundNormal = hit.normal;
        if (hit.collider == Ground) return;
        Ground = hit.collider;
        OnOneWay = (oneWay.value & (1 << hit.collider.gameObject.layer)) != 0;
        Platform = hit.collider.GetComponentInParent<MovingPlatform2D>();
    }

    /// <summary>
    /// The nearest thing in the way of a move from <paramref name="from"/>. The cast runs one
    /// skin further than the move so a surface the move would end touching is still reported. A
    /// landing sweep also reports a platform beyond that when its rise this step closes the gap:
    /// the cast sees it where it is, and it will be higher when the step lands.
    /// </summary>
    bool Sweep(Vector2 from, Vector2 direction, float distance, bool landing, out RaycastHit2D nearest)
    {
        nearest = default;
        _hitRise = 0f;
        bool useOneWay = landing && Time.time >= _dropUntil;
        float reach = distance + skin;
        int count = _body.Cast(from, _body.rotation, direction, useOneWay ? _allFilter : _solidFilter,
                               _hits, landing ? reach + LiftLook : reach);
        float feet = _collider.bounds.min.y + (from.y - _body.position.y);
        float best = float.MaxValue;
        for (int i = 0; i < count; i++)
        {
            RaycastHit2D hit = _hits[i];
            if (hit.collider == null) continue;
            // Grazing or receding: a surface slid along is not a surface run into.
            if (Vector2.Dot(hit.normal, direction) > -0.001f) continue;
            if ((oneWay.value & (1 << hit.collider.gameObject.layer)) != 0)
            {
                // Solid only to feet that are already above it and coming down onto its top.
                if (hit.normal.y < 0.7f) continue;
                if (hit.distance <= 1e-4f) continue;          // the cast began inside it: passing through
                if (feet < hit.point.y - skin) continue;
            }
            float rise = 0f;
            if (hit.distance > reach)
            {
                MovingPlatform2D lift = hit.collider.GetComponentInParent<MovingPlatform2D>();
                if (lift != null) rise = Mathf.Max(0f, lift.Velocity.y * _dt);
                if (hit.distance > reach + rise) continue;
            }
            if (hit.distance >= best) continue;
            best = hit.distance;
            nearest = hit;
            _hitRise = rise;
        }
        return best < float.MaxValue;
    }

    // A kinematic body is not pushed by anything: a platform that moves sideways into the runner
    // passes into it. Step out by the shortest separation before sweeping, or every cast starts
    // inside a collider.
    Vector2 Depenetrate(Vector2 pos)
    {
        int count = _collider.Overlap(_solidFilter, _overlaps);
        for (int i = 0; i < count; i++)
        {
            Collider2D other = _overlaps[i];
            if (other == null || other.attachedRigidbody == _body) continue;
            ColliderDistance2D d = _collider.Distance(other);
            if (!d.isValid || !d.isOverlapped) continue;
            Vector2 push = d.pointB - d.pointA;          // from the point on this collider to the one on theirs
            if (push.sqrMagnitude < 1e-10f) continue;
            pos += push + push.normalized * skin;
        }
        return pos;
    }
}
