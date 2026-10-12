// LaneRunnerController — the whole of a lane runner's movement: a lane index, a forward speed
// that ramps, and a jump that is a formula. There is no stick and no collision to resolve, so
// there is no motor; this script is the one owner of the transform.
//
// Drop into a Runtime assembly and add it to the runner beside a RunInputSource and one Collider
// (the body that hazards and pickups overlap). Awake adds or configures a kinematic Rigidbody
// with Interpolate — without a body on one side, trigger volumes never fire. The lanes run along
// the runner's forward at start; lane 1 of 3 is where it stands. It reads IRunInputSource from
// RunInput.cs (skill unity-input) and never a device, and implements IMoveFacts3D from
// CharacterMotor3D.cs.
// REQUIRES com.unity.modules.physics (built in; read Packages/manifest.json).
//
// A lane change is asked for by the move level crossing 'laneThreshold' from rest: a key, a
// stick flick, or a swipe that pulses the virtual stick. Holding does not repeat. One change is
// remembered while another runs.
//
// Register with the probe where the game wires its harness:
//   GameProbe.SetPlayerVelocity(() => run.transform, () => run.Velocity);
//   GameProbe.Register("lane", () => run.Lane);
//   GameProbe.Register("laneOffset", () => run.LaneOffset);
using System;
using UnityEngine;

[DisallowMultipleComponent]
public sealed class LaneRunnerController : MonoBehaviour, IMoveFacts3D
{
    [Header("Lanes")]
    [Tooltip("How many lanes. The middle one is where the runner starts.")]
    public int lanes = 3;
    [Tooltip("Units between two lane centres.")]
    public float laneWidth = 1.3f;
    [Tooltip("Seconds one lane change takes.")]
    public float laneChangeTime = 0.15f;
    [Tooltip("Ease in and out of the change. Off: constant sideways speed.")]
    public bool easeLaneChange = true;
    [Tooltip("How far the move level has to be pushed sideways to ask for a change.")]
    public float laneThreshold = 0.5f;

    [Header("Forward")]
    [Tooltip("Units per second at the start of a run.")]
    public float forwardSpeed = 12f;
    [Tooltip("Units per second the speed ramps to.")]
    public float maxForwardSpeed = 20f;
    [Tooltip("Units per second gained per second of running. 0.1 takes 80 s from 12 to 20.")]
    public float speedRamp = 0.1f;
    [Tooltip("Start running on enable. Off: call ResetRun, then set Running.")]
    public bool runOnStart = true;

    [Header("Jump — what the player sees")]
    public bool canJump = true;
    [Tooltip("Units.")]
    public float apexHeight = 1.2f;
    [Tooltip("Seconds from take-off to the top; the same again to come down.")]
    public float timeToApex = 0.35f;

    public float Gravity => 2f * apexHeight / (timeToApex * timeToApex);
    public float JumpVelocity => 2f * apexHeight / timeToApex;

    /// <summary>The lane the runner is in or changing to. It changes when the change starts: the lane is the truth, the transform catches up.</summary>
    public int Lane { get; private set; }
    /// <summary>Sideways distance from the middle lane, in units, as shown.</summary>
    public float LaneOffset { get; private set; }
    public bool Changing { get; private set; }
    public bool Running { get; set; }
    /// <summary>Forward units per second now.</summary>
    public float Speed { get; private set; }
    /// <summary>Forward units covered since ResetRun.</summary>
    public float Distance { get; private set; }
    public bool Grounded => !_airborne;
    public Vector3 Velocity { get; private set; }
    /// <summary>Lane changes started since ResetRun — a probe count.</summary>
    public int LaneChanges { get; private set; }
    /// <summary>Changes asked for at the outer lane — the bump the player should hear.</summary>
    public int Refused { get; private set; }
    public int Jumps { get; private set; }
    public string State => !Running ? "Idle" : _airborne ? "Jump" : Changing ? "Change" : "Run";

    /// <summary>Raised when a change starts, with -1 or +1.</summary>
    public event Action<int> LaneChanged;
    public event Action Jumped;
    public event Action Landed;

    Rigidbody _body;
    IRunInputSource _input;
    Vector3 _origin;
    Vector3 _forward;
    Vector3 _right;
    float _fromOffset;
    float _toOffset;
    float _changeElapsed;
    float _runElapsed;
    float _airElapsed;
    float _height;
    int _lastSide;
    int _queued;
    bool _airborne;

    int MiddleLane => (Mathf.Max(1, lanes) - 1) / 2;

    void Awake()
    {
        if (!TryGetComponent(out _body)) _body = gameObject.AddComponent<Rigidbody>();
        _body.isKinematic = true;
        _body.useGravity = false;
        _body.interpolation = RigidbodyInterpolation.Interpolate;
        _origin = transform.position;
        _forward = Vector3.ProjectOnPlane(transform.forward, Vector3.up).normalized;
        if (_forward.sqrMagnitude < 0.5f) _forward = Vector3.forward;
        _right = Vector3.Cross(Vector3.up, _forward);
        ResetRun(MiddleLane);
        Running = runOnStart;
    }

    /// <summary>Sideways offset of a lane's centre from the middle lane: lane 1 of 3 is 0, lane 0 is -1.3.</summary>
    public float OffsetOf(int lane) => (lane - MiddleLane) * laneWidth;

    /// <summary>Back to the start of the track in the given lane, stopped in the air or mid-change. Leaves Running as it was.</summary>
    public void ResetRun(int lane)
    {
        Lane = Mathf.Clamp(lane, 0, Mathf.Max(1, lanes) - 1);
        LaneOffset = _fromOffset = _toOffset = OffsetOf(Lane);
        Changing = false;
        _queued = 0;
        _lastSide = 0;
        _airborne = false;
        _height = 0f;
        _runElapsed = 0f;
        Distance = 0f;
        Speed = forwardSpeed;
        LaneChanges = Refused = Jumps = 0;
        Velocity = Vector3.zero;
        Vector3 at = _origin + _right * LaneOffset;
        _body.position = at;
        transform.position = at;
    }

    /// <summary>
    /// Move the track's origin and the runner together, keeping Distance. Call it with the same
    /// shift applied to the track every 1000 units: far from the origin positions lose precision
    /// and the runner shimmers.
    /// </summary>
    public void ShiftOrigin(Vector3 delta)
    {
        _origin += delta;
        _body.position += delta;
        transform.position += delta;
    }

    /// <summary>Ask for a lane change: -1 left, +1 right. The same entry the input uses.</summary>
    public void RequestLane(int side)
    {
        if (side == 0) return;
        side = side > 0 ? 1 : -1;
        if (Changing) { _queued = side; return; }       // one deep: the last ask wins
        Begin(side);
    }

    void Begin(int side)
    {
        int target = Lane + side;
        if (target < 0 || target >= Mathf.Max(1, lanes)) { Refused++; return; }
        Lane = target;
        _fromOffset = LaneOffset;
        _toOffset = OffsetOf(target);
        _changeElapsed = 0f;
        Changing = true;
        LaneChanges++;
        LaneChanged?.Invoke(side);
    }

    // FixedUpdate: this body is a kinematic Rigidbody, and MovePosition belongs to the physics step.
    void FixedUpdate()
    {
        float dt = Time.fixedDeltaTime;
        bool hasInput = RunInputSource.Resolve(gameObject, ref _input);
        RunInput i = hasInput ? _input.Peek() : default;

        // ---- a change is an edge of the level, not the level: holding does not repeat ----------
        int side = i.move.x > laneThreshold ? 1 : i.move.x < -laneThreshold ? -1 : 0;
        if (Running && side != 0 && side != _lastSide) RequestLane(side);
        _lastSide = side;

        if (Changing)
        {
            _changeElapsed += dt;
            float t = laneChangeTime > 0f ? Mathf.Clamp01(_changeElapsed / laneChangeTime) : 1f;
            LaneOffset = Mathf.Lerp(_fromOffset, _toOffset, easeLaneChange ? Mathf.SmoothStep(0f, 1f, t) : t);
            if (t >= 1f)
            {
                LaneOffset = _toOffset;                 // the lane centre exactly, not a float away
                Changing = false;
                int next = _queued;
                _queued = 0;
                if (next != 0) Begin(next);
            }
        }

        // ---- the jump: height is a function of time in the air, so the apex is the designed
        // one at any step length and there is no ground to find --------------------------------
        if (Running && canJump && !_airborne && hasInput && _input.TryUse(RunButton.Launch))
        {
            _airborne = true;
            _airElapsed = 0f;
            Jumps++;
            Jumped?.Invoke();
        }
        if (_airborne)
        {
            _airElapsed += dt;
            _height = JumpVelocity * _airElapsed - 0.5f * Gravity * _airElapsed * _airElapsed;
            if (_airElapsed >= 2f * timeToApex || _height <= 0f)
            {
                _height = 0f;
                _airborne = false;
                Landed?.Invoke();
            }
        }

        if (Running)
        {
            _runElapsed += dt;
            Speed = Mathf.Min(maxForwardSpeed, forwardSpeed + speedRamp * _runElapsed);
            Distance += Speed * dt;
        }

        Vector3 pose = _origin + _forward * Distance + _right * LaneOffset + Vector3.up * _height;
        Velocity = (pose - _body.position) / dt;
        _body.MovePosition(pose);
    }
}
