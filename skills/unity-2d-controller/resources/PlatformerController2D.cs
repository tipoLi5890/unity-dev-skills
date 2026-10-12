// PlatformerController2D — the rules half of a side-view character: it reads intent from the
// input funnel, decides a velocity, and hands it to PlatformerMotor2D to be made to fit the level.
//
// Drop into a Runtime assembly and add it to the runner beside PlatformerMotor2D and a
// RunInputSource (RunInputReader in the game, ScriptedRunInput in a journey test). It reads
// IRunInputSource from RunInput.cs (skill unity-input) and never a device.
// REQUIRES com.unity.modules.physics2d (built in; read Packages/manifest.json).
//
// The jump is authored as what the player sees — apex height and time to apex — and gravity and
// jump velocity are derived from the pair. The jump buffer is not here: it is bufferSeconds on
// the input source, and "condition first, then TryUse" is what spends it.
//
// Register with the probe where the game wires its harness (not here, so this file compiles
// without it):
//   GameProbe.SetPlayerVelocity(() => run.transform, () => (Vector3)run.Velocity);
//   GameProbe.Register("grounded", () => run.Grounded);
using System;
using UnityEngine;

[Flags]
public enum RunAbility
{
    None = 0,
    Jump = 1,
    VariableJump = 2,
    DropThrough = 4,
    WallSlide = 8,
    WallJump = 16,
    Dash = 32,
}

[DisallowMultipleComponent]
[RequireComponent(typeof(PlatformerMotor2D))]
public sealed class PlatformerController2D : MonoBehaviour
{
    [Header("Abilities — a gated room hands these out; the level is checked against the set")]
    public RunAbility abilities = RunAbility.Jump | RunAbility.VariableJump | RunAbility.DropThrough;
    [Tooltip("Jumps allowed in the air after the first. 1 is a double jump.")]
    public int extraJumps = 0;

    [Header("Run")]
    public float runSpeed = 8f;
    [Tooltip("Units/s². 80 reaches run speed in 0.1 s.")]
    public float groundAccel = 80f;
    [Tooltip("Units/s². 80 stops from run speed in 0.1 s, about 0.4 units of slide.")]
    public float groundDecel = 80f;
    [Tooltip("Units/s². 40 reaches run speed in 0.2 s: enough to correct a jump, not to reverse it.")]
    public float airAccel = 40f;
    [Tooltip("Runner mode: horizontal input is replaced by full speed to the right.")]
    public bool autoRun = false;

    [Header("Jump — what the player sees")]
    [Tooltip("Units. The fixed step lands about jumpVelocity * dt / 2 below this.")]
    public float apexHeight = 3f;
    [Tooltip("Seconds from take-off to the top.")]
    public float timeToApex = 0.4f;
    [Tooltip("Gravity multiplier once the runner is falling.")]
    public float fallMultiplier = 1.5f;
    public float maxFallSpeed = 20f;
    [Tooltip("Seconds after walking off an edge in which a jump still counts as a ground jump.")]
    public float coyoteTime = 0.1f;
    [Tooltip("Upward velocity is multiplied by this, once, when the button is let go on the way up.")]
    public float jumpCutMultiplier = 0.5f;
    [Tooltip("Below this vertical speed the apex-hang gravity applies. 0 turns the hang off.")]
    public float apexHangSpeed = 0f;
    [Tooltip("Gravity multiplier inside the hang band. Any value below 1 raises the apex: re-measure it.")]
    public float apexHangGravity = 0.5f;

    [Header("Wall")]
    [Tooltip("Fall speed while pressed against a wall.")]
    public float wallSlideSpeed = 3f;
    [Tooltip("Horizontal speed away from the wall on a wall jump.")]
    public float wallJumpPush = 9f;
    [Tooltip("Seconds after a wall jump in which horizontal input is ignored, or the runner steers straight back.")]
    public float wallJumpLock = 0.15f;
    [Tooltip("Seconds after leaving a wall in which a wall jump is still accepted.")]
    public float wallCoyoteTime = 0.1f;

    [Header("Dash")]
    public RunButton dashButton = RunButton.Interact;
    public float dashSpeed = 20f;
    [Tooltip("Seconds. 20 units/s for 0.15 s covers 3 units.")]
    public float dashTime = 0.15f;
    public float dashCooldown = 0.4f;

    public float Gravity => 2f * apexHeight / (timeToApex * timeToApex);
    public float JumpVelocity => 2f * apexHeight / timeToApex;

    public bool Grounded => _motor.Grounded;
    /// <summary>What the body did last step, platform carry included.</summary>
    public Vector2 Velocity => _motor.Velocity;
    /// <summary>+1 right, -1 left. Follows input, keeps its value when input is zero.</summary>
    public int Facing { get; private set; } = 1;
    /// <summary>Seconds since the last grounded step; 0 while grounded.</summary>
    public float TimeSinceGrounded => _sinceGrounded;
    public bool WallSliding { get; private set; }
    public bool Dashing => _dashLeft > 0f;
    /// <summary>Every jump taken since enable, of any kind — a probe count.</summary>
    public int Jumps { get; private set; }
    public string State =>
        Dashing ? "Dash" : Grounded ? "Grounded" : WallSliding ? "WallSlide" : _velocity.y > 0f ? "Rising" : "Falling";

    /// <summary>Raised on the step a jump starts and on the step the runner lands — for sound and dust.</summary>
    public event Action Jumped;
    public event Action Landed;

    PlatformerMotor2D _motor;
    IRunInputSource _input;
    Vector2 _velocity;
    float _sinceGrounded = 99f;
    float _sinceWall = 99f;
    int _lastWallSide;
    int _airJumpsLeft;
    bool _airDashLeft;
    bool _cut;
    bool _wasGrounded;
    bool _pushed;
    float _steerLock;
    float _dashLeft;
    float _dashReady;
    float _dashDirection;

    void Awake() => _motor = GetComponent<PlatformerMotor2D>();

    public bool Has(RunAbility ability) => (abilities & ability) != 0;
    public void Grant(RunAbility ability) => abilities |= ability;
    public void Revoke(RunAbility ability) => abilities &= ~ability;

    /// <summary>A hazard's knock-back: replace the velocity and take the stick away for a moment.</summary>
    public void Push(Vector2 velocity, float lockSeconds)
    {
        _velocity = velocity;
        _steerLock = lockSeconds;
        _dashLeft = 0f;
        _pushed = true;
    }

    /// <summary>Stop dead and forget timers. Call it with the motor's Teleport on a respawn.</summary>
    public void ResetMotion()
    {
        _velocity = Vector2.zero;
        _sinceGrounded = _sinceWall = 99f;
        _steerLock = _dashLeft = 0f;
        _wasGrounded = false;
    }

    void FixedUpdate()
    {
        float dt = Time.fixedDeltaTime;
        // Resolve, not a field cached in Awake: a journey swaps the enabled source on a live runner.
        bool hasInput = RunInputSource.Resolve(gameObject, ref _input);
        RunInput i = hasInput ? _input.Peek() : default;

        bool grounded = _motor.Grounded;
        int wall = _motor.WallSide;
        Vector2 v = _velocity;

        if (grounded)
        {
            if (!_wasGrounded) Landed?.Invoke();
            _sinceGrounded = 0f;
            _airJumpsLeft = extraJumps;
            _airDashLeft = true;
            _cut = true;                   // nothing to shorten until a jump says otherwise
        }
        else _sinceGrounded += dt;
        _wasGrounded = grounded;

        if (_pushed)
        {
            _pushed = false;
            _cut = true;                   // a push is not a jump the player can shorten
            if (v.y > 0f)
            {
                // Off the ground on this step: the grounded branch below would zero the launch,
                // and coyote time would let the player jump out of it.
                grounded = false;
                _sinceGrounded = 99f;
            }
        }

        if (wall != 0 && !grounded) { _sinceWall = 0f; _lastWallSide = wall; }
        else _sinceWall += dt;

        // ---- horizontal ------------------------------------------------------------------
        float wish = autoRun ? 1f : i.move.x;
        if (_steerLock > 0f) { _steerLock -= dt; wish = 0f; }
        else
        {
            float rate = !grounded ? airAccel : Mathf.Abs(wish) > 0.01f ? groundAccel : groundDecel;
            v.x = Mathf.MoveTowards(v.x, wish * runSpeed, rate * dt);
        }
        if (Mathf.Abs(wish) > 0.01f) Facing = wish > 0f ? 1 : -1;

        // ---- the Launch press: the condition first, then TryUse, so a press that cannot be
        // acted on stays pending for the source's buffer --------------------------------------
        bool jumped = false;
        if (hasInput && _dashLeft <= 0f)
        {
            if (grounded && _motor.OnOneWay && i.move.y < -0.5f && Has(RunAbility.DropThrough))
            {
                if (_input.TryUse(RunButton.Launch))
                {
                    _motor.DropThrough();
                    grounded = false;
                    _sinceGrounded = 99f;          // a drop is not an edge: no coyote jump out of it
                }
            }
            else if (Has(RunAbility.Jump) && _sinceGrounded <= coyoteTime)
            {
                if (_input.TryUse(RunButton.Launch)) { v.y = JumpVelocity; jumped = true; }
            }
            else if (Has(RunAbility.WallJump) && _sinceWall <= wallCoyoteTime)
            {
                if (_input.TryUse(RunButton.Launch))
                {
                    v = new Vector2(-_lastWallSide * wallJumpPush, JumpVelocity);
                    Facing = -_lastWallSide;
                    _steerLock = wallJumpLock;
                    _sinceWall = 99f;
                    jumped = true;
                }
            }
            else if (Has(RunAbility.Jump) && _airJumpsLeft > 0)
            {
                if (_input.TryUse(RunButton.Launch)) { v.y = JumpVelocity; _airJumpsLeft--; jumped = true; }
            }
        }
        if (jumped)
        {
            // Assigned, never added: a slope or a second press must not stack on the first.
            _sinceGrounded = 99f;
            _cut = false;
            Jumps++;
            Jumped?.Invoke();
        }

        // ---- dash --------------------------------------------------------------------------
        if (hasInput && Has(RunAbility.Dash) && _dashLeft <= 0f && Time.time >= _dashReady
            && (grounded || _airDashLeft) && _input.TryUse(dashButton))
        {
            _dashLeft = dashTime;
            _dashReady = Time.time + dashTime + dashCooldown;
            _dashDirection = Mathf.Abs(i.move.x) > 0.01f ? Mathf.Sign(i.move.x) : Facing;
            Facing = _dashDirection > 0f ? 1 : -1;
            if (!grounded) _airDashLeft = false;
        }

        // ---- vertical ----------------------------------------------------------------------
        WallSliding = false;
        if (_dashLeft > 0f)
        {
            _dashLeft -= dt;
            v = new Vector2(_dashDirection * dashSpeed, 0f);          // level, gravity suspended
            if (_dashLeft <= 0f) v.x = _dashDirection * runSpeed;     // leave at run speed, not dash speed
        }
        else if (grounded && !jumped)
        {
            v.y = 0f;
        }
        else
        {
            // The short hop: once per jump, on the way up, when the button is no longer held.
            if (Has(RunAbility.VariableJump) && !_cut && v.y > 0f && !i.launchHeld)
            {
                v.y *= jumpCutMultiplier;
                _cut = true;
            }

            float g = Gravity;
            if (apexHangSpeed > 0f && Mathf.Abs(v.y) < apexHangSpeed) g *= apexHangGravity;
            else if (v.y < 0f) g *= fallMultiplier;
            // Velocity first, then position (in Move): gravity acts from the take-off step, and
            // the apex is jumpVelocity * dt / 2 below apexHeight.
            v.y -= g * dt;

            float cap = maxFallSpeed;
            if (Has(RunAbility.WallSlide) && wall != 0 && v.y < 0f && wish * wall > 0.01f)
            {
                WallSliding = true;
                cap = wallSlideSpeed;
            }
            if (v.y < -cap) v.y = -cap;
        }

        _velocity = _motor.Move(v, dt);
    }
}
