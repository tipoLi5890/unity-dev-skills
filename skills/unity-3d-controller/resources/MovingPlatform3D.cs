// MovingPlatform3D — a platform that travels between two points, optionally turning, and says how
// fast any point on it is going.
//
// Drop into a Runtime assembly and add it to a platform that has a Collider. Awake adds or
// configures a kinematic Rigidbody with Interpolate. Put the collider on a layer the runner's
// CharacterMotor3D reads as ground.
// REQUIRES com.unity.modules.physics (built in; read Packages/manifest.json).
//
// PointVelocity is the reason this file exists. A CharacterController is not carried by what it
// stands on, and a kinematic body moved with MovePosition reports no velocity a rider can rely
// on, so the platform works out this step's velocity itself and CharacterMotor3D adds the
// velocity of the point under the feet to whoever stands there.
using UnityEngine;

[DefaultExecutionOrder(-50)]            // before anything else in the fixed step reads Velocity
[DisallowMultipleComponent]
public sealed class MovingPlatform3D : MonoBehaviour
{
    [Tooltip("Where the platform travels to, relative to where it starts.")]
    public Vector3 travel = new Vector3(4f, 0f, 0f);
    [Tooltip("Units per second along the path.")]
    public float speed = 2f;
    [Tooltip("Seconds to wait at each end. A lift with no pause is hard to board.")]
    public float pause = 0.5f;
    [Tooltip("Degrees per second about the world up axis. 0 for a platform that does not turn.")]
    public float yawSpeed = 0f;

    /// <summary>The linear velocity this platform has over the fixed step now running.</summary>
    public Vector3 Velocity { get; private set; }
    /// <summary>Degrees per second about world up over the same step.</summary>
    public float YawRate { get; private set; }

    Rigidbody _body;
    Vector3 _origin;
    float _t;               // 0 at the origin, 1 at the far end
    float _direction = 1f;
    float _waiting;

    void Awake()
    {
        if (!TryGetComponent(out _body)) _body = gameObject.AddComponent<Rigidbody>();
        _body.isKinematic = true;
        _body.useGravity = false;
        _body.interpolation = RigidbodyInterpolation.Interpolate;
        _origin = _body.position;
    }

    void OnDisable()
    {
        Velocity = Vector3.zero;
        YawRate = 0f;
    }

    /// <summary>Velocity of a world point riding the platform: its travel plus its turn about the pivot.</summary>
    public Vector3 PointVelocity(Vector3 worldPoint)
    {
        if (Mathf.Abs(YawRate) < 1e-5f) return Velocity;
        Vector3 arm = worldPoint - _body.position;
        return Velocity + Vector3.Cross(Vector3.up * (YawRate * Mathf.Deg2Rad), arm);
    }

    void FixedUpdate()
    {
        float dt = Time.fixedDeltaTime;

        YawRate = yawSpeed;
        if (Mathf.Abs(yawSpeed) > 1e-5f)
            _body.MoveRotation(Quaternion.AngleAxis(yawSpeed * dt, Vector3.up) * _body.rotation);

        float length = travel.magnitude;
        if (length < 1e-4f || speed <= 0f) { Velocity = Vector3.zero; return; }

        if (_waiting > 0f)
        {
            _waiting -= dt;
            Velocity = Vector3.zero;
            return;
        }

        float before = _t;
        _t = Mathf.Clamp01(_t + _direction * speed * dt / length);
        if (_t <= 0f || _t >= 1f)
        {
            _direction = -_direction;
            _waiting = pause;
        }

        // From the distance actually covered, so the last step into an end is not overstated.
        Velocity = travel * ((_t - before) / dt);
        // A kinematic body is moved with MovePosition: the solver moves it to the target over the
        // step, so bodies resting on it are carried and interpolation has two poses to draw between.
        _body.MovePosition(_origin + travel * _t);
    }

    void OnDrawGizmosSelected()
    {
        Vector3 a = Application.isPlaying ? _origin : transform.position;
        Gizmos.color = Color.cyan;
        Gizmos.DrawLine(a, a + travel);
    }
}
