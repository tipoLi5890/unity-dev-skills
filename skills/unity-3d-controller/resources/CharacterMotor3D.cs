// CharacterMotor3D — the collision half of a 3D character on a CharacterController: it is handed
// a velocity, moves the capsule to where the level allows, and reports where the ground is and
// what it is made of.
//
// Drop into a Runtime assembly, with MovingPlatform3D.cs (the motor names its type), and add it
// to the runner beside a CharacterController. No Rigidbody on that object and no NavMeshAgent:
// the CharacterController is the one owner of the transform. Keep the object's scale at 1 and leave the runner's own layer out of 'ground'.
// REQUIRES com.unity.modules.physics (built in; read Packages/manifest.json). The built-in
// CharacterController component needs no package.
//
// It decides nothing: no input, no gravity, no jump. A rules script (ThirdPersonController.cs,
// FirstPersonController.cs, TopDownController3D.cs) owns the velocity and calls Move once per
// frame, from Update. Exactly one script calls Move.
//
//   motor.Move(planar + Vector3.up * vertical, Time.deltaTime);
//   if (motor.Grounded) vertical = 0f;
//
// Ground is this motor's own cast, never CharacterController.isGrounded: that flag is only true
// on a frame whose Move pressed into the floor, so it flickers on flat ground and on every
// down-slope.
using UnityEngine;

/// <summary>What an Animator bridge, a probe or a camera reads from whatever moves a 3D character.</summary>
public interface IMoveFacts3D
{
    /// <summary>Standing on walkable ground as of the last step.</summary>
    bool Grounded { get; }
    /// <summary>What the body did over the last step, in world units per second.</summary>
    Vector3 Velocity { get; }
}

[DisallowMultipleComponent]
[RequireComponent(typeof(CharacterController))]
public sealed class CharacterMotor3D : MonoBehaviour
{
    [Header("What counts as ground")]
    [Tooltip("Layers the ground cast reads. Leave the runner's own layer out.")]
    public LayerMask ground = Physics.DefaultRaycastLayers;
    [Tooltip("How far below resting contact a surface still counts as ground, in units.")]
    public float groundTolerance = 0.05f;
    [Tooltip("How far a grounded runner is pulled down onto the ground it just left: down-slopes, crests, stairs. Keep it at or under stepOffset.")]
    public float snapDistance = 0.3f;

    [Header("Steps")]
    [Tooltip("Tallest ledge walked up without a jump. The motor writes it, plus the skin width, to the CharacterController while grounded and writes 0 in the air, so a jump cannot climb what a walk cannot.")]
    public float stepOffset = 0.3f;

    [Header("Other bodies")]
    [Tooltip("Keep a moving platform's velocity when the runner leaves it.")]
    public bool inheritPlatformVelocity = true;
    [Tooltip("Speed given to a dynamic Rigidbody the runner walks into, in units/s. 0 pushes nothing.")]
    public float pushSpeed = 0f;

    /// <summary>Standing on a surface no steeper than the CharacterController's slopeLimit.</summary>
    public bool Grounded { get; private set; }
    /// <summary>Touching a surface steeper than slopeLimit: not ground, and uphill input is refused.</summary>
    public bool OnSteep { get; private set; }
    /// <summary>Unit normal of the surface under the feet, or up when airborne.</summary>
    public Vector3 GroundNormal { get; private set; } = Vector3.up;
    /// <summary>Angle between that surface and level, in degrees.</summary>
    public float GroundAngle => Vector3.Angle(GroundNormal, Vector3.up);
    public Collider Ground { get; private set; }
    /// <summary>The platform under the feet, or null.</summary>
    public MovingPlatform3D Platform { get; private set; }
    /// <summary>The upward part of the last Move was stopped.</summary>
    public bool OnCeiling { get; private set; }
    /// <summary>The last Move ran into something sideways.</summary>
    public bool HitSide { get; private set; }
    /// <summary>What the body did over the last Move, platform carry included.</summary>
    public Vector3 Velocity { get; private set; }
    /// <summary>
    /// The platform's velocity on the step the runner left it, zero on every other step. The
    /// rules add it to their own velocity once. Only the upward part of the vertical is kept: a
    /// platform going down must not shorten the jump off it.
    /// </summary>
    public Vector3 PlatformLaunch { get; private set; }
    public CharacterController Controller => _cc;
    /// <summary>World position of the lowest point of the capsule.</summary>
    public Vector3 Feet => transform.TransformPoint(_cc.center) + Vector3.down * (Height * 0.5f);

    // The ground cast uses a sphere this much narrower than the capsule, so a wall the runner is
    // pressed against is not reported as something under it.
    const float CastShrink = 0.9f;
    // A settle shorter than this is not worth a second Move.
    const float MinSettle = 0.005f;
    // Slope limits are compared with a little slack: a ramp built at exactly the limit is walkable.
    const float AngleSlack = 0.5f;

    CharacterController _cc;

    float Radius
    {
        get
        {
            Vector3 s = transform.lossyScale;
            return _cc.radius * Mathf.Max(Mathf.Abs(s.x), Mathf.Abs(s.z));
        }
    }

    float Height => Mathf.Max(_cc.height * Mathf.Abs(transform.lossyScale.y), Radius * 2f);

    void Awake()
    {
        _cc = GetComponent<CharacterController>();
        // The default (0.001) drops any move shorter than a millimetre: a slow walk at a high
        // frame rate does not move at all.
        _cc.minMoveDistance = 0f;
        _cc.stepOffset = stepOffset + _cc.skinWidth;
        if (TryGetComponent(out Rigidbody body) && !body.isKinematic)
            Debug.LogError("[MOTOR3D] a non-kinematic Rigidbody beside the CharacterController on " + name +
                           ": two owners of one transform", this);
    }

    /// <summary>Place the runner somewhere without a sweep: a respawn, a situation, a door.</summary>
    public void Teleport(Vector3 position)
    {
        // A CharacterController keeps its own copy of the position; a write to the transform
        // while it is enabled is undone by the next Move.
        bool was = _cc.enabled;
        _cc.enabled = false;
        transform.position = position;
        _cc.enabled = was;
        Physics.SyncTransforms();
        Grounded = false;
        OnSteep = false;
        Ground = null;
        Platform = null;
        GroundNormal = Vector3.up;
        Velocity = Vector3.zero;
        PlatformLaunch = Vector3.zero;
    }

    /// <summary>
    /// Move by velocity * dt, stopping at whatever is in the way, then find the ground. Read
    /// Grounded, OnCeiling and PlatformLaunch afterwards and correct the rules' own velocity.
    /// </summary>
    public void Move(Vector3 velocity, float dt)
    {
        if (dt <= 0f || !_cc.enabled) return;

        Vector3 start = transform.position;
        bool wasGrounded = Grounded;
        MovingPlatform3D wasOn = Platform;
        bool rising = velocity.y > 0f;
        PlatformLaunch = Vector3.zero;

        // 1 · steps are for feet on the ground. Left on in the air, the capsule climbs a ledge
        // of stepOffset from the side of a jump that did not clear it. The skin is added because
        // the capsule rests a skin above the floor and has to clear the ledge by a skin: without
        // it a ledge of exactly stepOffset is the one height that depends on rounding.
        _cc.stepOffset = wasGrounded && !rising ? stepOffset + _cc.skinWidth : 0f;

        // 2 · carry. The platform says how fast the point under the feet is going, turn included.
        Vector3 carry = Vector3.zero;
        if (wasGrounded && wasOn != null)
        {
            carry = wasOn.PointVelocity(Feet) * dt;
            float yaw = wasOn.YawRate * dt;
            if (Mathf.Abs(yaw) > 1e-5f) transform.Rotate(0f, yaw, 0f, Space.World);
        }

        // 3 · shape the horizontal part to the surface under the feet.
        Vector3 planar = new Vector3(velocity.x, 0f, velocity.z);
        if (OnSteep)
        {
            // No walking up what is too steep to stand on, whatever the capsule would allow.
            Vector3 uphill = new Vector3(-GroundNormal.x, 0f, -GroundNormal.z);
            if (uphill.sqrMagnitude > 1e-6f)
            {
                uphill.Normalize();
                float into = Vector3.Dot(planar, uphill);
                if (into > 0f) planar -= uphill * into;
            }
        }
        else if (wasGrounded && !rising && planar.sqrMagnitude > 1e-8f)
        {
            // Along the slope at the speed asked for: the same pace uphill, downhill and level,
            // and a down-slope is followed and not stepped off.
            Vector3 along = Vector3.ProjectOnPlane(planar, GroundNormal);
            if (along.sqrMagnitude > 1e-8f) planar = along.normalized * planar.magnitude;
        }

        CollisionFlags flags = _cc.Move((planar + Vector3.up * velocity.y) * dt + carry);
        OnCeiling = (flags & CollisionFlags.Above) != 0;
        HitSide = (flags & CollisionFlags.Sides) != 0;

        // 4 · the ground, never while rising: a short look when airborne, a longer one with a
        // pull-down when the runner was grounded.
        Grounded = false;
        OnSteep = false;
        if (!rising)
        {
            float reach = wasGrounded ? Mathf.Max(snapDistance, groundTolerance) : groundTolerance;
            if (Probe(reach, out RaycastHit hit, out Vector3 normal, out float gap))
            {
                if (Vector3.Angle(normal, Vector3.up) <= _cc.slopeLimit + AngleSlack)
                {
                    if (hit.collider != Ground)
                    {
                        Ground = hit.collider;
                        Platform = hit.collider.GetComponentInParent<MovingPlatform3D>();
                    }
                    // A platform's collider moves on the physics clock and the runner on the
                    // frame: up to two steps of its travel is phase, not a gap to close.
                    float slack = MinSettle;
                    if (Platform != null) slack += Mathf.Abs(Platform.Velocity.y) * Time.fixedDeltaTime * 2f;
                    if (gap > slack) _cc.Move(Vector3.down * gap);
                    Grounded = true;
                    GroundNormal = normal;
                }
                else if (gap <= groundTolerance)
                {
                    OnSteep = true;
                    GroundNormal = normal;
                }
            }
        }
        if (!Grounded)
        {
            Ground = null;
            Platform = null;
            if (!OnSteep) GroundNormal = Vector3.up;
        }

        Velocity = (transform.position - start) / dt;

        if (wasGrounded && !Grounded && wasOn != null && inheritPlatformVelocity)
        {
            Vector3 pv = wasOn.PointVelocity(Feet);
            PlatformLaunch = new Vector3(pv.x, Mathf.Max(0f, pv.y), pv.z);
        }
    }

    /// <summary>
    /// The surface under the capsule within <paramref name="reach"/> of resting contact.
    /// <paramref name="normal"/> is the surface's own normal, not the contact's: a sphere that
    /// meets the corner of a step reports a tilted normal for a level step.
    /// <paramref name="gap"/> is how far the capsule can still drop before it rests.
    /// </summary>
    bool Probe(float reach, out RaycastHit hit, out Vector3 normal, out float gap)
    {
        normal = Vector3.up;
        gap = 0f;
        float radius = Radius;
        float castRadius = radius * CastShrink;
        float rest = radius + _cc.skinWidth - castRadius;      // the cast's travel at resting contact, on level ground
        Vector3 origin = transform.TransformPoint(_cc.center) + Vector3.down * (Height * 0.5f - radius);

        // Slopes lengthen the travel by 1 / normal.y; twice covers every walkable angle.
        if (!Physics.SphereCast(origin, castRadius, Vector3.down, out hit, rest * 2f + reach, ground,
                                QueryTriggerInteraction.Ignore))
            return false;
        if (hit.collider.transform.IsChildOf(transform)) return false;      // a collider of the runner's own

        normal = hit.normal;
        Vector3 outward = hit.point - origin;
        outward.y = 0f;
        outward = outward.sqrMagnitude > 1e-8f ? outward.normalized * 0.01f : Vector3.zero;
        Vector3 above = hit.point + Vector3.up * 0.05f;
        // Outward first: the face that supports a capsule perched on an edge is on the far side
        // of the contact from its axis.
        if (hit.collider.Raycast(new Ray(above + outward, Vector3.down), out RaycastHit face, 0.2f) ||
            hit.collider.Raycast(new Ray(above - outward, Vector3.down), out face, 0.2f))
            normal = face.normal;

        gap = Mathf.Max(0f, hit.distance - rest / Mathf.Max(normal.y, 0.1f));
        return gap <= reach;
    }

    // A CharacterController never raises OnCollisionEnter; this is the message it sends, once per
    // contact per Move. It pushes nothing unless code here says so.
    void OnControllerColliderHit(ControllerColliderHit hit)
    {
        if (pushSpeed <= 0f) return;
        Rigidbody body = hit.rigidbody;
        if (body == null || body.isKinematic) return;
        if (hit.moveDirection.y < -0.3f) return;                // standing on it, not walking into it
        Vector3 direction = new Vector3(hit.moveDirection.x, 0f, hit.moveDirection.z);
        if (direction.sqrMagnitude < 1e-6f) return;
        Vector3 v = direction.normalized * pushSpeed;
        body.linearVelocity = new Vector3(v.x, body.linearVelocity.y, v.z);
    }
}
