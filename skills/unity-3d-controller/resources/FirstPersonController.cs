// FirstPersonController — the rules half of a first-person character: yaw turns the body, pitch
// turns the head and nothing else, the stick moves relative to the body, and the velocity goes to
// CharacterMotor3D to be made to fit the level.
//
// Drop into a Runtime assembly and add it to the runner beside CharacterMotor3D and a
// RunInputSource. Assign 'head' to an empty child at eye height; the camera (or the Cinemachine
// camera's tracking target) is that child. It reads IRunInputSource from RunInput.cs (skill
// unity-input) and never a device.
// REQUIRES com.unity.modules.physics (built in; read Packages/manifest.json).
//
// Look has two feeds because the two devices measure different things:
//   AddLookDelta(counts)     a pointer: counts moved since the last frame. Never times deltaTime.
//   LookRate = stick         a stick: -1..1, a rate. Times deltaTime, here.
// RunInput carries no look field, so the game's reader calls one of them each frame. With
// 'lookFromAim' on, a stick aim in RunInput (a direction, so always full rate) drives LookRate
// when nothing else has.
using System;
using UnityEngine;

[DisallowMultipleComponent]
[RequireComponent(typeof(CharacterMotor3D))]
public sealed class FirstPersonController : MonoBehaviour, IMoveFacts3D
{
    [Header("Head")]
    [Tooltip("An empty child at eye height. Only its local pitch and local height are written.")]
    public Transform head;
    [Tooltip("Units above the feet.")]
    public float eyeHeight = 1.6f;
    [Tooltip("Degrees up and down. Never 90: straight up loses the heading.")]
    public float maxPitch = 85f;

    [Header("Look")]
    [Tooltip("Degrees per pointer count. Not multiplied by deltaTime.")]
    public float degreesPerCount = 0.1f;
    [Tooltip("Degrees per second at full stick, yaw.")]
    public float stickYawSpeed = 180f;
    [Tooltip("Degrees per second at full stick, pitch.")]
    public float stickPitchSpeed = 120f;
    public bool invertY = false;
    [Tooltip("Use a stick aim from RunInput as the look stick when LookRate is zero.")]
    public bool lookFromAim = true;

    [Header("Run")]
    public float runSpeed = 5f;
    [Tooltip("Multiplies runSpeed: 0.4 for a walk, 1.4 for a sprint.")]
    public float speedScale = 1f;
    [Tooltip("Units/s². 33 reaches run speed in 0.15 s.")]
    public float groundAccel = 33f;
    [Tooltip("Units/s². 50 stops from run speed in 0.1 s.")]
    public float groundDecel = 50f;
    [Tooltip("Units/s².")]
    public float airAccel = 15f;

    [Header("Jump — what the player sees")]
    public bool canJump = true;
    public float apexHeight = 1.2f;
    public float timeToApex = 0.35f;
    public float fallMultiplier = 1.5f;
    public float maxFallSpeed = 20f;
    public float coyoteTime = 0.1f;

    [Header("Crouch")]
    [Tooltip("Capsule height while crouched. The standing height is read from the CharacterController at Awake.")]
    public float crouchHeight = 1.2f;
    [Tooltip("Multiplies run speed while crouched.")]
    public float crouchSpeedScale = 0.5f;
    [Tooltip("Units per second the head travels between the two heights.")]
    public float crouchHeadSpeed = 4f;

    [Header("Footsteps")]
    [Tooltip("Ground distance between two Footstep events. 1.6 is three steps a second at run speed.")]
    public float strideLength = 1.6f;

    public float Gravity => 2f * apexHeight / (timeToApex * timeToApex);
    public float JumpVelocity => 2f * apexHeight / timeToApex;

    public bool Grounded => _motor.Grounded;
    public Vector3 Velocity => _motor.Velocity;
    /// <summary>Degrees the head looks above level; negative below.</summary>
    public float Pitch => _pitch;
    /// <summary>The body's heading in degrees about world up.</summary>
    public float Yaw => transform.eulerAngles.y;
    public bool Crouched { get; private set; }
    public int Jumps { get; private set; }
    public int Footsteps { get; private set; }
    public string State => Grounded ? (Crouched ? "Crouched" : "Grounded") : _vertical > 0f ? "Rising" : "Falling";

    /// <summary>A stick's look, -1..1 on each axis, as a level. Set it every frame or leave it zero.</summary>
    public Vector2 LookRate { get; set; }

    /// <summary>Raised each time the feet have covered strideLength on the ground — play the step here.</summary>
    public event Action Footstep;
    public event Action Jumped;
    public event Action Landed;

    CharacterMotor3D _motor;
    CharacterController _cc;
    IRunInputSource _input;
    Vector3 _planar;
    Vector2 _lookDelta;
    float _vertical;
    float _pitch;
    float _sinceGrounded = 99f;
    float _stride;
    float _standHeight;
    float _feetLocalY;
    bool _wasGrounded;
    bool _wantCrouch;
    readonly Collider[] _overlaps = new Collider[8];

    void Awake()
    {
        _motor = GetComponent<CharacterMotor3D>();
        _cc = GetComponent<CharacterController>();
        _standHeight = _cc.height;
        _feetLocalY = _cc.center.y - _cc.height * 0.5f;
        if (head != null)
        {
            Vector3 p = head.localPosition;
            head.localPosition = new Vector3(p.x, _feetLocalY + eyeHeight, p.z);
        }
    }

    /// <summary>A pointer's movement since the last frame, in counts. x turns right, y looks up.</summary>
    public void AddLookDelta(Vector2 counts) => _lookDelta += counts;

    /// <summary>Ask to crouch or to stand. Standing waits until there is room overhead.</summary>
    public void SetCrouch(bool crouch) => _wantCrouch = crouch;

    /// <summary>Point the view somewhere at once: a respawn, a situation.</summary>
    public void SetLook(float yawDegrees, float pitchDegrees)
    {
        transform.rotation = Quaternion.Euler(0f, yawDegrees, 0f);
        _pitch = Mathf.Clamp(pitchDegrees, -maxPitch, maxPitch);
        _lookDelta = Vector2.zero;
        ApplyPitch();
    }

    public void ResetMotion()
    {
        _planar = Vector3.zero;
        _vertical = 0f;
        _sinceGrounded = 99f;
        _wasGrounded = false;
        _stride = 0f;
    }

    void Update()
    {
        float dt = Time.deltaTime;
        if (dt <= 0f) return;
        bool hasInput = RunInputSource.Resolve(gameObject, ref _input);
        RunInput i = hasInput ? _input.Peek() : default;

        // ---- look: before movement, so this frame's step goes where the view now points --------
        Vector2 rate = LookRate;
        if (lookFromAim && rate == Vector2.zero && !i.hasAimPoint) rate = i.aim;
        float yaw = _lookDelta.x * degreesPerCount + rate.x * stickYawSpeed * dt;
        float pitch = _lookDelta.y * degreesPerCount + rate.y * stickPitchSpeed * dt;
        _lookDelta = Vector2.zero;
        if (invertY) pitch = -pitch;
        // Yaw on the body, added to whatever it is: a turning platform's carry survives.
        if (yaw != 0f) transform.Rotate(0f, yaw, 0f, Space.World);
        _pitch = Mathf.Clamp(_pitch + pitch, -maxPitch, maxPitch);
        ApplyPitch();

        UpdateCrouch(dt);

        bool grounded = _motor.Grounded;
        if (grounded)
        {
            if (!_wasGrounded) Landed?.Invoke();
            _sinceGrounded = 0f;
        }
        else _sinceGrounded += dt;
        _wasGrounded = grounded;

        // ---- the stick, relative to the body --------------------------------------------------
        Vector3 wish = Vector3.ClampMagnitude(transform.forward * i.move.y + transform.right * i.move.x, 1f);
        float top = runSpeed * speedScale * (Crouched ? crouchSpeedScale : 1f);
        float accel = !grounded ? airAccel : wish.sqrMagnitude > 1e-4f ? groundAccel : groundDecel;
        _planar = Vector3.MoveTowards(_planar, wish * top, accel * dt);

        bool jumped = false;
        if (hasInput && canJump && !Crouched && _sinceGrounded <= coyoteTime && _input.TryUse(RunButton.Launch))
        {
            _vertical = JumpVelocity;
            _sinceGrounded = 99f;
            jumped = true;
            Jumps++;
            Jumped?.Invoke();
        }

        float stepVertical = 0f;
        if (grounded && !jumped) _vertical = 0f;
        else
        {
            float g = Gravity * (_vertical < 0f ? fallMultiplier : 1f);
            float before = _vertical;
            _vertical = Mathf.Max(_vertical - g * dt, -maxFallSpeed);
            stepVertical = (before + _vertical) * 0.5f;       // exact under constant gravity at any frame rate
        }

        _motor.Move(_planar + Vector3.up * stepVertical, dt);

        if (_motor.OnCeiling && _vertical > 0f) _vertical = 0f;
        if (_motor.Grounded && _vertical < 0f) _vertical = 0f;
        Vector3 carried = _motor.PlatformLaunch;
        _planar += new Vector3(carried.x, 0f, carried.z);
        _vertical += carried.y;

        // ---- footsteps: by distance covered, so the cadence follows the speed ------------------
        if (_motor.Grounded && strideLength > 0f)
        {
            Vector3 v = _motor.Velocity;
            _stride += new Vector2(v.x, v.z).magnitude * dt;
            if (_stride >= strideLength)
            {
                _stride -= strideLength;
                Footsteps++;
                Footstep?.Invoke();
            }
        }
    }

    void ApplyPitch()
    {
        // Positive pitch looks up; Unity's X rotation is positive downwards.
        if (head != null) head.localRotation = Quaternion.Euler(-_pitch, 0f, 0f);
    }

    void UpdateCrouch(float dt)
    {
        if (_wantCrouch != Crouched && (_wantCrouch || HasHeadroom()))
        {
            Crouched = _wantCrouch;
            float height = Crouched ? Mathf.Max(crouchHeight, _cc.radius * 2f) : _standHeight;
            // Shrink towards the feet: the centre moves so the lowest point stays where it was.
            _cc.height = height;
            _cc.center = new Vector3(_cc.center.x, _feetLocalY + height * 0.5f, _cc.center.z);
        }
        if (head == null) return;
        float eye = _feetLocalY + eyeHeight - (Crouched ? _standHeight - crouchHeight : 0f);
        Vector3 p = head.localPosition;
        head.localPosition = new Vector3(p.x, Mathf.MoveTowards(p.y, eye, crouchHeadSpeed * dt), p.z);
    }

    // Room for the standing capsule above the crouched one. An overlap, unlike a cast, reports
    // the runner's own capsule, so its colliders are skipped by hand.
    bool HasHeadroom()
    {
        float radius = _cc.radius * 0.95f;
        Vector3 feet = transform.TransformPoint(new Vector3(_cc.center.x, _feetLocalY, _cc.center.z));
        Vector3 low = feet + Vector3.up * (_cc.height - _cc.radius);
        Vector3 high = feet + Vector3.up * (_standHeight - _cc.radius);
        int count = Physics.OverlapCapsuleNonAlloc(low, high, radius, _overlaps, _motor.ground,
                                                   QueryTriggerInteraction.Ignore);
        for (int k = 0; k < count; k++)
            if (!_overlaps[k].transform.IsChildOf(transform)) return false;
        return true;
    }
}
