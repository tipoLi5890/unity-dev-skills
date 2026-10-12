// TopDownController3D — the rules half of a 3D character seen from a fixed or overhead camera:
// the stick moves along axes that do not turn with the runner, the aim decides where it faces,
// and the velocity goes to CharacterMotor3D to be made to fit the level.
//
// Drop into a Runtime assembly and add it to the runner beside CharacterMotor3D and a
// RunInputSource. Leave 'view' empty for world axes, or assign the room's camera. It reads
// IRunInputSource from RunInput.cs (skill unity-input) and never a device.
// REQUIRES com.unity.modules.physics (built in; read Packages/manifest.json).
//
// No jump: the depot floor is level and a fall is only a fall. For click-to-move, call
// Release() and let a NavMeshAgent own the transform; Reclaim() takes it back.
using UnityEngine;

[DisallowMultipleComponent]
[RequireComponent(typeof(CharacterMotor3D))]
public sealed class TopDownController3D : MonoBehaviour, IMoveFacts3D
{
    [Header("Axes")]
    [Tooltip("The fixed camera whose heading defines 'up' on the stick. Empty: stick up is world +Z.")]
    public Transform view;
    [Tooltip("Keep the axes that were live when the stick left rest. A camera cut then does not reverse a held stick.")]
    public bool holdAxesWhileHeld = true;

    [Header("Run")]
    public float runSpeed = 5f;
    [Tooltip("Units/s². 33 reaches run speed in 0.15 s.")]
    public float accel = 33f;
    [Tooltip("Units/s². 50 stops from run speed in 0.1 s.")]
    public float decel = 50f;
    [Tooltip("Units/s² downwards when the floor ends.")]
    public float gravity = 19.6f;
    public float maxFallSpeed = 20f;

    [Header("Facing")]
    [Tooltip("Face the aim (a pointer's ground point or the aim stick) when there is one; otherwise face the movement.")]
    public bool faceAim = true;
    [Tooltip("Degrees per second. 720 reverses in a quarter of a second; 0 turns instantly.")]
    public float turnRate = 720f;

    public bool Grounded => _motor.Grounded;
    public Vector3 Velocity => _motor.Velocity;
    /// <summary>Unit direction on the ground the runner is asked to face. Keeps its value when nothing aims or moves.</summary>
    public Vector3 Facing { get; private set; } = Vector3.forward;
    /// <summary>Input is asking for movement. Not "has speed": a runner pushed against a wall is still moving its legs.</summary>
    public bool Moving { get; private set; }
    /// <summary>False after Release(): something else owns the transform.</summary>
    public bool Owns { get; private set; } = true;
    public string State => !Owns ? "Released" : !Grounded ? "Falling" : Moving ? "Moving" : "Idle";

    CharacterMotor3D _motor;
    IRunInputSource _input;
    Vector3 _planar;
    Vector3 _axisForward = Vector3.forward;
    float _vertical;
    float _steerLock;
    bool _stickAtRest = true;

    void Awake()
    {
        _motor = GetComponent<CharacterMotor3D>();
        Facing = Vector3.ProjectOnPlane(transform.forward, Vector3.up).normalized;
        if (Facing.sqrMagnitude < 0.5f) Facing = Vector3.forward;
    }

    /// <summary>A hazard's knock-back: replace the velocity and take the stick away for a moment.</summary>
    public void Push(Vector3 velocity, float lockSeconds)
    {
        _planar = new Vector3(velocity.x, 0f, velocity.z);
        _vertical = velocity.y;
        _steerLock = lockSeconds;
    }

    public void ResetMotion()
    {
        _planar = Vector3.zero;
        _vertical = 0f;
        _steerLock = 0f;
    }

    /// <summary>
    /// Give the transform away: this script stops moving and the CharacterController is switched
    /// off, so an agent on the same object is the only owner. Enable the agent after this call.
    /// </summary>
    public void Release()
    {
        Owns = false;
        ResetMotion();
        _motor.Controller.enabled = false;
    }

    /// <summary>Take the transform back. Disable the agent before this call.</summary>
    public void Reclaim()
    {
        _motor.Controller.enabled = true;
        _motor.Teleport(transform.position);
        Owns = true;
    }

    void Update()
    {
        float dt = Time.deltaTime;
        if (dt <= 0f || !Owns) return;
        bool hasInput = RunInputSource.Resolve(gameObject, ref _input);
        RunInput i = hasInput ? _input.Peek() : default;

        // ---- axes: world, or the camera's heading, latched while the stick is held --------------
        bool atRest = i.move.sqrMagnitude < 0.01f;
        if (view == null) _axisForward = Vector3.forward;
        else if (!holdAxesWhileHeld || _stickAtRest)
        {
            Vector3 f = Vector3.ProjectOnPlane(view.forward, Vector3.up);
            // An overhead camera looks straight down; its up is the heading on the ground.
            if (f.sqrMagnitude < 1e-4f) f = Vector3.ProjectOnPlane(view.up, Vector3.up);
            if (f.sqrMagnitude > 1e-6f) _axisForward = f.normalized;
        }
        _stickAtRest = atRest;
        Vector3 axisRight = Vector3.Cross(Vector3.up, _axisForward);

        Vector3 wish = Vector3.ClampMagnitude(_axisForward * i.move.y + axisRight * i.move.x, 1f);
        Moving = !atRest;

        if (_steerLock > 0f) _steerLock -= dt;
        else _planar = Vector3.MoveTowards(_planar, wish * runSpeed, (atRest ? decel : accel) * dt);

        float stepVertical = 0f;
        if (_motor.Grounded && _vertical <= 0f) _vertical = 0f;
        else
        {
            float before = _vertical;
            _vertical = Mathf.Max(_vertical - gravity * dt, -maxFallSpeed);
            stepVertical = (before + _vertical) * 0.5f;
        }

        _motor.Move(_planar + Vector3.up * stepVertical, dt);

        if (_motor.OnCeiling && _vertical > 0f) _vertical = 0f;
        Vector3 carried = _motor.PlatformLaunch;
        _planar += new Vector3(carried.x, 0f, carried.z);
        _vertical += carried.y;

        // ---- facing: the aim when there is one, else the movement, else what it was -------------
        Vector3 look = Vector3.zero;
        if (faceAim && i.hasAimPoint)
            look = Vector3.ProjectOnPlane(i.aimPoint - transform.position, Vector3.up);
        else if (faceAim && i.aim != Vector2.zero)
            look = _axisForward * i.aim.y + axisRight * i.aim.x;      // stick axes are the same axes as the move
        else if (!atRest)
            look = wish;
        // Closer than a body width the direction to a pointer swings wildly; keep the last one.
        if (look.sqrMagnitude > 0.04f) Facing = look.normalized;

        Quaternion target = Quaternion.LookRotation(Facing, Vector3.up);
        transform.rotation = turnRate > 0f
            ? Quaternion.RotateTowards(transform.rotation, target, turnRate * dt)
            : target;
    }
}
