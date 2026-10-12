// TopDownMotor2D — free movement seen from above: 4-way, 8-way or analogue, with acceleration and
// stopping as numbers, a wall slide the solver provides, aim kept apart from movement, and an
// optional clamp to the screen for a fixed-screen shooter.
//
// Drop into a Runtime assembly and add it to the runner beside a Rigidbody2D and a
// CircleCollider2D at the feet (radius about 0.3 of a tile) carrying a zero-friction
// PhysicsMaterial2D. Awake sets the body to Dynamic, gravity scale 0, damping 0, rotation frozen.
// It reads IRunInputSource from RunInput.cs (skill unity-input) and never a device.
// REQUIRES com.unity.modules.physics2d (built in; read Packages/manifest.json).
//
// A dynamic body is the right owner here: with no gravity there is no slope and no ground to
// decide, and the solver's push-out against shelving is exactly the wall slide wanted.
//
// Register with the probe where the game wires its harness:
//   GameProbe.SetPlayerVelocity(() => run.transform, () => (Vector3)run.Velocity);
using UnityEngine;

public enum MoveDirections { Analogue, EightWay, FourWay }

[DisallowMultipleComponent]
[RequireComponent(typeof(Rigidbody2D))]
public sealed class TopDownMotor2D : MonoBehaviour
{
    [Header("Move")]
    public MoveDirections directions = MoveDirections.Analogue;
    public float speed = 5f;
    [Tooltip("Units/s². 62.5 reaches 5 units/s in 0.08 s.")]
    public float accel = 62.5f;
    [Tooltip("Units/s². 100 stops from 5 units/s in 0.05 s, 0.125 units of slide.")]
    public float decel = 100f;
    [Tooltip("Stick deflection below this is rest. The reader has already applied the device dead zone.")]
    public float moveThreshold = 0.1f;

    [Header("Facing")]
    [Tooltip("Twin-stick: facing follows aim while there is one, movement otherwise.")]
    public bool faceAim = false;
    [Tooltip("Snap the facing to 4 directions (sprite sets) instead of keeping it continuous.")]
    public bool snapFacing = true;

    [Header("Fixed screen")]
    [Tooltip("Keep the runner inside this camera's view. Leave empty for a level that scrolls.")]
    public Camera clampTo;
    [Tooltip("Distance kept from the edge of the view, in units — at least the collider radius.")]
    public float clampMargin = 0.4f;

    /// <summary>The body's velocity, knock-back included.</summary>
    public Vector2 Velocity => _body.linearVelocity;
    /// <summary>Unit vector. From input or aim, never from velocity; keeps its value at rest.</summary>
    public Vector2 Facing { get; private set; } = Vector2.down;
    /// <summary>Unit aim direction, or the facing when nothing is aiming.</summary>
    public Vector2 Aim { get; private set; } = Vector2.down;
    public bool Moving { get; private set; }
    public bool Stunned => _stun > 0f;

    Rigidbody2D _body;
    IRunInputSource _input;
    float _stun;

    void Awake()
    {
        _body = GetComponent<Rigidbody2D>();
        _body.bodyType = RigidbodyType2D.Dynamic;
        _body.gravityScale = 0f;             // per body, so props that should fall still do
        _body.linearDamping = 0f;            // stopping is 'decel', one number in one place
        _body.freezeRotation = true;
        _body.collisionDetectionMode = CollisionDetectionMode2D.Continuous;
    }

    /// <summary>
    /// A hit's knock-back: the velocity is replaced and the stick is ignored for
    /// <paramref name="stunSeconds"/>, after which 'decel' brings the runner back under control.
    /// </summary>
    public void Push(Vector2 velocity, float stunSeconds)
    {
        _body.linearVelocity = velocity;
        _stun = stunSeconds;
    }

    void FixedUpdate()
    {
        float dt = Time.fixedDeltaTime;
        bool hasInput = RunInputSource.Resolve(gameObject, ref _input);
        RunInput i = hasInput ? _input.Peek() : default;

        Vector2 wish = Shape(i.move);
        Moving = wish.sqrMagnitude > 0f;

        if (_stun > 0f)
        {
            _stun -= dt;
            wish = Vector2.zero;
            Moving = false;
            // The push decays at half the stopping rate, so it reads as a shove and not a stop.
            _body.linearVelocity = Vector2.MoveTowards(_body.linearVelocity, Vector2.zero, decel * 0.5f * dt);
        }
        else
        {
            float rate = Moving ? accel : decel;
            _body.linearVelocity = Vector2.MoveTowards(_body.linearVelocity, wish * speed, rate * dt);
        }

        if (i.aim.sqrMagnitude > 0.5f) Aim = i.aim;
        else if (Moving) Aim = wish.normalized;

        Vector2 look = faceAim && i.aim.sqrMagnitude > 0.5f ? i.aim : wish;
        if (look.sqrMagnitude > 0.0001f) Facing = snapFacing ? Snap4(look, Facing) : look.normalized;

        if (clampTo != null) ClampToView();
    }

    /// <summary>
    /// Input to a wish vector of magnitude 0..1. Clamped, never normalised: a half-pushed stick
    /// stays half speed, and a keyboard diagonal of (1, 1) is not 41% faster than a cardinal.
    /// </summary>
    Vector2 Shape(Vector2 move)
    {
        if (move.magnitude < moveThreshold) return Vector2.zero;
        switch (directions)
        {
            case MoveDirections.FourWay:
                // The vector's magnitude, not the axis's: two keys held arrive as (0.71, 0.71)
                // and must still be full speed along the one axis that wins.
                return (Mathf.Abs(move.x) >= Mathf.Abs(move.y)
                    ? new Vector2(Mathf.Sign(move.x), 0f)
                    : new Vector2(0f, Mathf.Sign(move.y))) * Mathf.Min(1f, move.magnitude);
            case MoveDirections.EightWay:
            {
                // Nearest of eight directions, keeping the stick's magnitude.
                float step = Mathf.PI / 4f;
                float angle = Mathf.Round(Mathf.Atan2(move.y, move.x) / step) * step;
                return new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * Mathf.Min(1f, move.magnitude);
            }
            default:
                return Vector2.ClampMagnitude(move, 1f);
        }
    }

    // The current facing wins a near tie, so a diagonal does not flicker between two sprite sets.
    static Vector2 Snap4(Vector2 v, Vector2 current)
    {
        float ax = Mathf.Abs(v.x), ay = Mathf.Abs(v.y);
        bool horizontal = Mathf.Abs(current.x) > 0.5f ? ax >= ay * 0.9f : ax > ay * 1.1f;
        return horizontal ? new Vector2(Mathf.Sign(v.x), 0f) : new Vector2(0f, Mathf.Sign(v.y));
    }

    void ClampToView()
    {
        if (!clampTo.orthographic) return;
        float halfHeight = clampTo.orthographicSize - clampMargin;
        float halfWidth = clampTo.orthographicSize * clampTo.aspect - clampMargin;
        Vector2 centre = clampTo.transform.position;
        Vector2 p = _body.position;
        Vector2 v = _body.linearVelocity;
        // Stop the outward velocity at the edge and leave the rest alone: sliding along the
        // screen edge must feel like sliding along a wall.
        if (p.x < centre.x - halfWidth) { p.x = centre.x - halfWidth; v.x = Mathf.Max(0f, v.x); }
        else if (p.x > centre.x + halfWidth) { p.x = centre.x + halfWidth; v.x = Mathf.Min(0f, v.x); }
        if (p.y < centre.y - halfHeight) { p.y = centre.y - halfHeight; v.y = Mathf.Max(0f, v.y); }
        else if (p.y > centre.y + halfHeight) { p.y = centre.y + halfHeight; v.y = Mathf.Min(0f, v.y); }
        if (p != _body.position)
        {
            _body.position = p;
            _body.linearVelocity = v;
        }
    }
}
