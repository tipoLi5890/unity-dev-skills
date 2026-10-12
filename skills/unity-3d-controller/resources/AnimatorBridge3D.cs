// AnimatorBridge3D — the one script that writes a 3D character's Animator: it copies what the
// mover already knows (grounded, ground speed) into parameters, once per frame, and fires the
// hurt trigger when the game says so.
//
// Drop into a Runtime assembly and add it to the runner (the object with the controller). Point
// 'animator' at the model child. It reads IMoveFacts3D from CharacterMotor3D.cs, which
// ThirdPersonController, FirstPersonController, TopDownController3D and LaneRunnerController all
// implement; a mover of your own implements the same two properties.
// REQUIRES com.unity.modules.animation (built in; read Packages/manifest.json).
//
// Parameter names default to the ones the character controller asset of skill
// unity-rigged-character is built with: Grounded (bool), MoveBlend (float, 0 slow to 1 fast),
// MoveSpeed (float, a playback rate) and Hurt (trigger). Clear a name to stop writing it; a name
// the controller does not have is reported once at start, not silently skipped every frame.
using UnityEngine;

[DefaultExecutionOrder(100)]              // after gameplay, so this frame's state is the one copied
[DisallowMultipleComponent]
public sealed class AnimatorBridge3D : MonoBehaviour
{
    [Header("Where the picture is")]
    public Animator animator;
    [Tooltip("The mover: any component that implements IMoveFacts3D. Empty: found on this object.")]
    public MonoBehaviour mover;

    [Header("Parameters — clear a name to leave it unwritten")]
    [Tooltip("Bool.")]
    public string grounded = "Grounded";
    [Tooltip("Float, 0..1: ground speed between slowSpeed and fastSpeed. The blend tree's position.")]
    public string moveBlend = "MoveBlend";
    [Tooltip("Float: ground speed divided by authoredSpeed. A state's playback rate.")]
    public string moveSpeed = "MoveSpeed";
    [Tooltip("Trigger. Fired by Hurt().")]
    public string hurt = "Hurt";

    [Header("Speeds")]
    [Tooltip("Ground speed at which MoveBlend is 0: the pace the slow clip was animated for.")]
    public float slowSpeed = 2f;
    [Tooltip("Ground speed at which MoveBlend is 1: the pace the fast clip was animated for.")]
    public float fastSpeed = 5f;
    [Tooltip("The ground speed at which the move clip's feet do not slide; MoveSpeed is a multiple of it.")]
    public float authoredSpeed = 5f;
    [Tooltip("Lowest MoveSpeed written. 0 freezes a single-clip state when the runner stands still.")]
    public float minPlayback = 0f;
    [Tooltip("Seconds MoveBlend takes to follow the speed. Hides velocity noise; a gait that changes in one frame pops.")]
    public float blendDamp = 0.1f;

    [Header("Root motion")]
    [Tooltip("This character is moved by script, so the Animator must not move it too. Off only when the mover applies the clip's delta itself.")]
    public bool forceRootMotionOff = true;

    /// <summary>Ground speed last written, in units per second.</summary>
    public float GroundSpeed { get; private set; }
    /// <summary>Hurt triggers fired since enable — a probe count.</summary>
    public int Hurts { get; private set; }

    IMoveFacts3D _facts;
    int _groundedId, _moveBlendId, _moveSpeedId, _hurtId;

    void Awake()
    {
        if (animator == null) animator = GetComponentInChildren<Animator>();
        _facts = mover != null ? mover as IMoveFacts3D : GetComponent<IMoveFacts3D>();
        if (_facts == null)
            Debug.LogError("[ANIM3D] no IMoveFacts3D on " + name + " — assign 'mover' to the controller", this);

        _groundedId = Resolve(grounded, AnimatorControllerParameterType.Bool);
        _moveBlendId = Resolve(moveBlend, AnimatorControllerParameterType.Float);
        _moveSpeedId = Resolve(moveSpeed, AnimatorControllerParameterType.Float);
        _hurtId = Resolve(hurt, AnimatorControllerParameterType.Trigger);

        if (animator != null && forceRootMotionOff && animator.applyRootMotion)
        {
            // Two writers of one transform: the clip's translation argues with the mover's.
            Debug.LogError("[ANIM3D] Apply Root Motion is on for a script-moved character on " + animator.name +
                           " — switched off; a clip that travels must keep its travel out of the pose (reference/animator-bridge.md, section 4)", this);
            animator.applyRootMotion = false;
        }
    }

    /// <summary>The game's hit event calls this. An instant has no value to copy each frame.</summary>
    public void Hurt()
    {
        Hurts++;
        if (animator != null && _hurtId != 0) animator.SetTrigger(_hurtId);
    }

    // Every parameter, every frame: a pooled runner that was disabled comes back with the
    // Animator at its defaults, and the next Update puts every one of them right.
    void Update()
    {
        if (animator == null || _facts == null) return;

        Vector3 v = _facts.Velocity;
        // Planar: a jump or a lift is not a faster run.
        GroundSpeed = new Vector2(v.x, v.z).magnitude;

        if (_groundedId != 0) animator.SetBool(_groundedId, _facts.Grounded);
        if (_moveBlendId != 0)
        {
            float blend = Mathf.InverseLerp(slowSpeed, fastSpeed, GroundSpeed);
            if (blendDamp > 0f) animator.SetFloat(_moveBlendId, blend, blendDamp, Time.deltaTime);
            else animator.SetFloat(_moveBlendId, blend);
        }
        // Undamped: a playback rate that lags the ground speed is what makes feet slide.
        if (_moveSpeedId != 0)
            animator.SetFloat(_moveSpeedId, authoredSpeed > 0f ? Mathf.Max(minPlayback, GroundSpeed / authoredSpeed) : 1f);
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
            Debug.LogError("[ANIM3D] parameter '" + parameter + "' is " + p.type + ", the bridge writes " + type, this);
            return 0;
        }
        Debug.LogError("[ANIM3D] '" + parameter + "' is not a parameter of " +
                       animator.runtimeAnimatorController.name + " — clear the name or add the parameter", this);
        return 0;
    }
}
