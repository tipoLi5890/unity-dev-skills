// MovingPlatform2D — a platform that travels between two points and says how fast it is going.
//
// Drop into a Runtime assembly and add it to a platform that has a Collider2D. Awake adds or
// configures a kinematic Rigidbody2D. Put the collider on the 'solid' layer, or on the 'oneWay'
// layer for a lift the runner can jump up through.
// REQUIRES com.unity.modules.physics2d (built in; read Packages/manifest.json).
//
// Velocity is the reason this file exists. A kinematic body moved with MovePosition does not
// report a linearVelocity a rider can rely on, so the platform works out this step's velocity
// itself, before any rider's FixedUpdate, and PlatformerMotor2D adds it to whoever stands on it.
using UnityEngine;

[DefaultExecutionOrder(-50)]            // before the riders, so they read this step's velocity
[DisallowMultipleComponent]
public sealed class MovingPlatform2D : MonoBehaviour
{
    [Tooltip("Where the platform travels to, relative to where it starts.")]
    public Vector2 travel = new Vector2(4f, 0f);
    [Tooltip("Units per second along the path.")]
    public float speed = 2f;
    [Tooltip("Seconds to wait at each end. A lift with no pause is hard to board.")]
    public float pause = 0.5f;

    /// <summary>The velocity this platform has over the fixed step now running.</summary>
    public Vector2 Velocity { get; private set; }

    Rigidbody2D _body;
    Vector2 _origin;
    float _t;               // 0 at the origin, 1 at the far end
    float _direction = 1f;
    float _waiting;

    void Awake()
    {
        if (!TryGetComponent(out _body)) _body = gameObject.AddComponent<Rigidbody2D>();
        _body.bodyType = RigidbodyType2D.Kinematic;
        _body.interpolation = RigidbodyInterpolation2D.Interpolate;
        _origin = _body.position;
    }

    void FixedUpdate()
    {
        float dt = Time.fixedDeltaTime;
        float length = travel.magnitude;
        if (length < 1e-4f || speed <= 0f) { Velocity = Vector2.zero; return; }

        if (_waiting > 0f)
        {
            _waiting -= dt;
            Velocity = Vector2.zero;
            return;
        }

        float next = Mathf.Clamp01(_t + _direction * speed * dt / length);
        Vector2 from = _origin + travel * _t;
        Vector2 to = _origin + travel * next;
        // Derived from the two positions, so the last short step into an end stop is reported
        // as the short step it is and a rider does not overshoot the platform.
        Velocity = (to - from) / dt;
        _t = next;
        _body.MovePosition(to);

        if (_t <= 0f || _t >= 1f)
        {
            _direction = -_direction;
            _waiting = pause;
        }
    }

    void OnDisable() => Velocity = Vector2.zero;

    void OnDrawGizmosSelected()
    {
        Vector3 a = Application.isPlaying ? (Vector3)_origin : transform.position;
        Gizmos.color = Color.cyan;
        Gizmos.DrawLine(a, a + (Vector3)travel);
    }
}
