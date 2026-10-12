// ThirdPersonController — the rules half of a third-person character: it reads intent from the
// input funnel, turns the stick into a direction relative to the camera, decides a velocity, and
// hands it to CharacterMotor3D to be made to fit the level.
//
// Drop into a Runtime assembly and add it to the runner beside CharacterMotor3D and a
// RunInputSource (RunInputReader in the game, ScriptedRunInput in a journey test). Assign 'view'
// to the camera's transform. It reads IRunInputSource from RunInput.cs (skill unity-input) and
// never a device.
// REQUIRES com.unity.modules.physics (built in; read Packages/manifest.json).
//
// The jump is authored as what the player sees — apex height and time to apex — and gravity and
// jump velocity are derived from the pair. The jump buffer is not here: it is bufferSeconds on
// the input source, and "condition first, then TryUse" is what spends it.
//
// Register with the probe where the game wires its harness (not here, so this file compiles
// without it):
//   GameProbe.SetPlayerVelocity(() => chest, () => run.Velocity);     // chest: a child at the capsule's centre
//   GameProbe.Register("grounded", () => run.Grounded);
using System;
using UnityEngine;

public enum FacingMode3D
{
    /// <summary>Turn towards where the stick points. Free-roaming third person.</summary>
    Movement,
    /// <summary>Keep the view's heading and side-step. Aiming, over the shoulder.</summary>
    Strafe,
    /// <summary>Face lockTarget and circle it. Falls back to Movement while the target is null.</summary>
    LockOn,
}

[DisallowMultipleComponent]
[RequireComponent(typeof(CharacterMotor3D))]
public sealed class ThirdPersonController : MonoBehaviour, IMoveFacts3D
{
    [Header("View")]
    [Tooltip("The camera's transform. Its heading defines what 'forward' on the stick means. Empty: world axes.")]
    public Transform view;

    [Header("Run")]
    public float runSpeed = 5f;
    [Tooltip("Multiplies runSpeed: 0.4 for a walk (2 units/s), 1.4 for a sprint (7).")]
    public float speedScale = 1f;
    [Tooltip("Units/s². 33 reaches run speed in 0.15 s.")]
    public float groundAccel = 33f;
    [Tooltip("Units/s². 50 stops from run speed in 0.1 s, a quarter of a unit of slide.")]
    public float groundDecel = 50f;
    [Tooltip("Units/s². 15 reaches run speed in a third of a second: enough to correct a jump, not to reverse it.")]
    public float airAccel = 15f;

    [Header("Facing")]
    public FacingMode3D facing = FacingMode3D.Movement;
    [Tooltip("Degrees per second. 720 reverses in a quarter of a second; 0 turns instantly.")]
    public float turnRate = 720f;
    [Tooltip("What LockOn faces.")]
    public Transform lockTarget;

    [Header("Jump — what the player sees")]
    public bool canJump = true;
    [Tooltip("Units.")]
    public float apexHeight = 1.2f;
    [Tooltip("Seconds from take-off to the top.")]
    public float timeToApex = 0.35f;
    [Tooltip("Gravity multiplier once the runner is falling.")]
    public float fallMultiplier = 1.5f;
    public float maxFallSpeed = 20f;
    [Tooltip("Seconds after walking off an edge in which a jump still counts as a ground jump.")]
    public float coyoteTime = 0.1f;
    [Tooltip("Shorten the jump when the button is let go on the way up.")]
    public bool variableJump = true;
    [Tooltip("Upward velocity is multiplied by this, once, on that release.")]
    public float jumpCutMultiplier = 0.5f;

    public float Gravity => 2f * apexHeight / (timeToApex * timeToApex);
    public float JumpVelocity => 2f * apexHeight / timeToApex;

    public bool Grounded => _motor.Grounded;
    /// <summary>What the body did last frame, platform carry included.</summary>
    public Vector3 Velocity => _motor.Velocity;
    /// <summary>Seconds since the last grounded frame; 0 while grounded.</summary>
    public float TimeSinceGrounded => _sinceGrounded;
    /// <summary>Every jump taken since enable — a probe count.</summary>
    public int Jumps { get; private set; }
    public string State => Grounded ? "Grounded" : _vertical > 0f ? "Rising" : "Falling";

    /// <summary>Raised on the frame a jump starts and on the frame the runner lands — for sound and dust.</summary>
    public event Action Jumped;
    public event Action Landed;

    CharacterMotor3D _motor;
    IRunInputSource _input;
    Vector3 _planar;
    float _vertical;
    float _sinceGrounded = 99f;
    float _steerLock;
    bool _cut = true;
    bool _wasGrounded;
    bool _pushed;

    void Awake() => _motor = GetComponent<CharacterMotor3D>();

    /// <summary>A hazard's knock-back or a launch pad: replace the velocity and take the stick away for a moment.</summary>
    public void Push(Vector3 velocity, float lockSeconds)
    {
        _planar = new Vector3(velocity.x, 0f, velocity.z);
        _vertical = velocity.y;
        _steerLock = lockSeconds;
        _pushed = true;
    }

    /// <summary>Stop dead and forget timers. Call it with the motor's Teleport on a respawn.</summary>
    public void ResetMotion()
    {
        _planar = Vector3.zero;
        _vertical = 0f;
        _sinceGrounded = 99f;
        _steerLock = 0f;
        _wasGrounded = false;
        _cut = true;
    }

    // Update, not FixedUpdate: a CharacterController has no interpolation, so it moves on the
    // clock the camera renders on.
    void Update()
    {
        float dt = Time.deltaTime;
        if (dt <= 0f) return;
        // Resolve, not a field cached in Awake: a journey swaps the enabled source on a live runner.
        bool hasInput = RunInputSource.Resolve(gameObject, ref _input);
        RunInput i = hasInput ? _input.Peek() : default;

        bool grounded = _motor.Grounded;
        if (grounded)
        {
            if (!_wasGrounded) Landed?.Invoke();
            _sinceGrounded = 0f;
            _cut = true;                   // nothing to shorten until a jump says otherwise
        }
        else _sinceGrounded += dt;
        _wasGrounded = grounded;

        bool launched = false;
        if (_pushed)
        {
            _pushed = false;
            _cut = true;                   // a push is not a jump the player can shorten
            if (_vertical > 0f)
            {
                // Off the ground on this frame: the grounded branch below would zero the launch,
                // and coyote time would let the player jump out of it.
                launched = true;
                _sinceGrounded = 99f;
            }
        }

        // ---- the stick, relative to the view --------------------------------------------------
        Vector3 forward = Vector3.forward;
        if (view != null)
        {
            forward = Vector3.ProjectOnPlane(view.forward, Vector3.up);
            // A camera looking straight down has no forward on the ground; its up is the heading.
            if (forward.sqrMagnitude < 1e-4f) forward = Vector3.ProjectOnPlane(view.up, Vector3.up);
            forward.Normalize();
        }
        Vector3 right = Vector3.Cross(Vector3.up, forward);
        // Clamped, not normalised: a half-pushed stick is a walk.
        Vector3 wish = Vector3.ClampMagnitude(forward * i.move.y + right * i.move.x, 1f);

        if (_steerLock > 0f) { _steerLock -= dt; wish = Vector3.zero; }
        else
        {
            float rate = !grounded ? airAccel : wish.sqrMagnitude > 1e-4f ? groundAccel : groundDecel;
            _planar = Vector3.MoveTowards(_planar, wish * (runSpeed * speedScale), rate * dt);
        }

        // ---- the Launch press: the condition first, then TryUse, so a press that cannot be
        // acted on stays pending for the source's buffer ------------------------------------------
        if (hasInput && canJump && !launched && _sinceGrounded <= coyoteTime && _input.TryUse(RunButton.Launch))
        {
            // Assigned, never added: a slope or a lift must not stack on the jump.
            _vertical = JumpVelocity;
            _sinceGrounded = 99f;
            _cut = false;
            launched = true;
            Jumps++;
            Jumped?.Invoke();
        }

        // ---- vertical -------------------------------------------------------------------------
        float stepVertical = 0f;
        if (grounded && !launched)
        {
            _vertical = 0f;                // the motor holds the feet down; no resting gravity is needed
        }
        else
        {
            // The short hop: once per jump, on the way up, when the button is no longer held.
            if (variableJump && !_cut && _vertical > 0f && !i.launchHeld)
            {
                _vertical *= jumpCutMultiplier;
                _cut = true;
            }
            float g = Gravity * (_vertical < 0f ? fallMultiplier : 1f);
            float before = _vertical;
            _vertical = Mathf.Max(_vertical - g * dt, -maxFallSpeed);
            // The mean of the velocity before and after: exact under constant gravity, so the
            // apex is the same at 30 frames per second and at 240.
            stepVertical = (before + _vertical) * 0.5f;
        }

        _motor.Move(_planar + Vector3.up * stepVertical, dt);

        if (_motor.OnCeiling && _vertical > 0f) _vertical = 0f;
        if (_motor.Grounded && _vertical < 0f) _vertical = 0f;
        Vector3 carried = _motor.PlatformLaunch;
        _planar += new Vector3(carried.x, 0f, carried.z);
        _vertical += carried.y;

        // ---- facing: from intent, never from velocity, and it keeps its value at rest -----------
        Vector3 look = Vector3.zero;
        if (facing == FacingMode3D.LockOn && lockTarget != null)
            look = Vector3.ProjectOnPlane(lockTarget.position - transform.position, Vector3.up);
        else if (facing == FacingMode3D.Strafe)
            look = forward;
        else if (wish.sqrMagnitude > 0.01f)
            look = wish;
        if (look.sqrMagnitude > 1e-4f)
        {
            Quaternion target = Quaternion.LookRotation(look.normalized, Vector3.up);
            transform.rotation = turnRate > 0f
                ? Quaternion.RotateTowards(transform.rotation, target, turnRate * dt)
                : target;
        }
    }
}
