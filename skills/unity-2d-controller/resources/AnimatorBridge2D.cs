// AnimatorBridge2D — the one script that writes the runner's Animator: it copies what the 2D
// controller already knows (grounded, moving, vertical speed, facing) into parameters, once per
// frame, and mirrors the sprite from the game's facing.
//
// Drop into a Runtime assembly and add it to the runner (the object with the controller). Point
// 'animator' and 'sprite' at the Visual child. It finds whichever of PlatformerController2D,
// TopDownMotor2D or GridStepMover is on the same object.
// REQUIRES com.unity.modules.animation and com.unity.modules.physics2d (both built in).
//
// Parameter names default to the ones the sprite state graph and the directional blend tree of
// skill unity-animation are built with. Clear a name to stop writing it; a name the controller
// does not have is reported once at start, not silently skipped every frame.
using UnityEngine;

[DefaultExecutionOrder(100)]              // after gameplay, so this frame's state is the one copied
[DisallowMultipleComponent]
public sealed class AnimatorBridge2D : MonoBehaviour
{
    [Header("Where the picture is")]
    public Animator animator;
    public SpriteRenderer sprite;

    [Header("Parameters — clear a name to leave it unwritten")]
    [Tooltip("Bool. Platformer only.")]
    public string grounded = "Grounded";
    [Tooltip("Bool. Platformer: horizontal speed above 0.1. Top-down: input asks for movement. Cell: a step is running.")]
    public string moving = "Moving";
    [Tooltip("Float. Vertical speed in units/s. Platformer only.")]
    public string verticalSpeed = "VelY";
    [Tooltip("Float. Ground speed divided by the speed the run clip was drawn for.")]
    public string speed = "";
    [Tooltip("Floats. The facing as a unit vector, for a directional blend tree.")]
    public string faceX = "";
    public string faceY = "";

    [Header("Facing")]
    [Tooltip("Mirror the sprite when facing left. Off when the Animator picks directional clips from FaceX / FaceY.")]
    public bool flipSprite = true;
    [Tooltip("The art is drawn facing left.")]
    public bool artFacesLeft = false;
    [Tooltip("Children that must mirror with the sprite: a muzzle point, a hitbox. Their local x is negated.")]
    public Transform[] mirrorWithFacing = new Transform[0];
    [Tooltip("The speed the run clip was drawn for; 'speed' is written as a multiple of it.")]
    public float authoredRunSpeed = 8f;

    PlatformerController2D _platformer;
    TopDownMotor2D _topDown;
    GridStepMover _grid;
    int _groundedId, _movingId, _velYId, _speedId, _faceXId, _faceYId;
    bool _facingLeft;
    float[] _mirrorX;

    void Awake()
    {
        _platformer = GetComponent<PlatformerController2D>();
        _topDown = GetComponent<TopDownMotor2D>();
        _grid = GetComponent<GridStepMover>();
        if (animator == null) animator = GetComponentInChildren<Animator>();
        if (sprite == null) sprite = GetComponentInChildren<SpriteRenderer>();

        _groundedId = Resolve(grounded, AnimatorControllerParameterType.Bool);
        _movingId = Resolve(moving, AnimatorControllerParameterType.Bool);
        _velYId = Resolve(verticalSpeed, AnimatorControllerParameterType.Float);
        _speedId = Resolve(speed, AnimatorControllerParameterType.Float);
        _faceXId = Resolve(faceX, AnimatorControllerParameterType.Float);
        _faceYId = Resolve(faceY, AnimatorControllerParameterType.Float);

        _mirrorX = new float[mirrorWithFacing.Length];
        for (int i = 0; i < mirrorWithFacing.Length; i++)
            _mirrorX[i] = mirrorWithFacing[i] != null ? Mathf.Abs(mirrorWithFacing[i].localPosition.x) : 0f;
    }

    // Every parameter, every frame: a pooled runner that was disabled comes back with the
    // Animator at its defaults, and the next Update puts every one of them right.
    void Update()
    {
        bool isGrounded = true, isMoving = false;
        float velY = 0f, groundSpeed = 0f;
        Vector2 facing = Vector2.right;

        if (_platformer != null)
        {
            Vector2 v = _platformer.Velocity;
            isGrounded = _platformer.Grounded;
            velY = v.y;
            groundSpeed = Mathf.Abs(v.x);
            // Speed, not input: a runner pushed against a wall is not running.
            isMoving = groundSpeed > 0.1f;
            facing = new Vector2(_platformer.Facing, 0f);
        }
        else if (_topDown != null)
        {
            groundSpeed = _topDown.Velocity.magnitude;
            isMoving = _topDown.Moving;
            facing = _topDown.Facing;
        }
        else if (_grid != null)
        {
            groundSpeed = _grid.Velocity.magnitude;
            isMoving = _grid.Stepping;
            facing = _grid.Facing;
        }

        if (animator != null)
        {
            if (_groundedId != 0) animator.SetBool(_groundedId, isGrounded);
            if (_movingId != 0) animator.SetBool(_movingId, isMoving);
            if (_velYId != 0) animator.SetFloat(_velYId, velY);
            // Undamped: a playback rate that lags the ground speed is what makes feet slide.
            if (_speedId != 0) animator.SetFloat(_speedId, authoredRunSpeed > 0f ? groundSpeed / authoredRunSpeed : 0f);
            if (_faceXId != 0) animator.SetFloat(_faceXId, facing.x);
            if (_faceYId != 0) animator.SetFloat(_faceYId, facing.y);
        }

        // The facing is the game's, so it does not flip when velocity passes through zero.
        if (facing.x > 0.01f) _facingLeft = false;
        else if (facing.x < -0.01f) _facingLeft = true;

        if (flipSprite && sprite != null) sprite.flipX = _facingLeft != artFacesLeft;
        for (int i = 0; i < mirrorWithFacing.Length; i++)
        {
            Transform t = mirrorWithFacing[i];
            if (t == null) continue;
            Vector3 p = t.localPosition;
            p.x = _facingLeft ? -_mirrorX[i] : _mirrorX[i];
            t.localPosition = p;
        }
    }

    // 0 means "do not write". A name the controller lacks would otherwise log a warning per
    // frame and leave the character frozen in one pose.
    int Resolve(string parameter, AnimatorControllerParameterType type)
    {
        if (string.IsNullOrEmpty(parameter) || animator == null || animator.runtimeAnimatorController == null)
            return 0;
        int id = Animator.StringToHash(parameter);
        foreach (AnimatorControllerParameter p in animator.parameters)
        {
            if (p.nameHash != id) continue;
            if (p.type == type) return id;
            Debug.LogError("[ANIM2D] parameter '" + parameter + "' is " + p.type + ", the bridge writes " + type, this);
            return 0;
        }
        Debug.LogError("[ANIM2D] '" + parameter + "' is not a parameter of " +
                       animator.runtimeAnimatorController.name + " — clear the name or add the parameter", this);
        return 0;
    }
}
