// RunInputReader — the only file in the game that knows an input device exists.
//
// REQUIRES com.unity.inputsystem (and Active Input Handling set to "Input System Package" or "Both").
// Drop into a Runtime assembly that references Unity.InputSystem, beside RunInput.cs. Put it on
// the runner (or a persistent input object) and assign the .inputactions asset; with no asset
// assigned it falls back to the project-wide actions.
//
// It enables one action map, reads it once per rendered frame, and writes the result into the
// funnel in RunInput.cs: levels as levels, presses as latched presses. Gameplay reads the funnel
// from FixedUpdate and never touches an InputAction.
//
// The map is enabled unmasked — every control scheme is live at once — which is what one local
// player wants: pick up the pad and it works. For several players use PlayerInput, one per
// player, and feed each one's actions to its own reader.
using System;
using UnityEngine;
using UnityEngine.InputSystem;

[AddComponentMenu("Courier/Run Input Reader")]
[DefaultExecutionOrder(-100)]   // latch before any gameplay Update looks
public sealed class RunInputReader : RunInputSource
{
    [Header("Actions")]
    [Tooltip("The .inputactions asset. Empty: InputSystem.actions, the project-wide asset.")]
    public InputActionAsset actions;
    public string mapName = "Run";

    [Header("Aim")]
    [Tooltip("Camera a pointer aims through. Empty: Camera.main, looked up once.")]
    public Camera aimCamera;
    [Tooltip("Where aim is measured from — the runner. Empty: this transform.")]
    public Transform aimOrigin;
    public AimPlane aimPlane = AimPlane.XZ;
    [Tooltip("The play plane's position along its normal: z for XY, y for XZ.")]
    public float planeOffset;
    [Tooltip("A stick below this is not aiming. Larger than the move dead zone on purpose: a released stick springs past centre and would flick the aim.")]
    [Range(0f, 0.9f)] public float aimStickThreshold = 0.35f;

    /// <summary>"Keyboard&amp;Mouse", "Gamepad" or "Touch" — the control scheme of the last device used.</summary>
    public string ActiveScheme { get; private set; } = "Keyboard&Mouse";
    /// <summary>Raised when <see cref="ActiveScheme"/> changes. Prompt glyphs listen here.</summary>
    public event Action<string> SchemeChanged;

    InputActionMap _map;
    InputAction _move, _aim, _launch, _interact, _pause;
    Vector2 _pointerScreen, _stickAim;
    bool _aimFromPointer;

    void OnEnable()
    {
        if (actions == null) actions = InputSystem.actions;
        if (actions == null)
        {
            Debug.LogError("[INPUT] RunInputReader has no InputActionAsset and the project has no " +
                           "project-wide actions — nothing will be read.", this);
            enabled = false;
            return;
        }

        // throwIfNotFound: a renamed action must fail here, loudly, not read as "never pressed".
        _map = actions.FindActionMap(mapName, true);
        _move = _map.FindAction("Move", true);
        _aim = _map.FindAction("Aim", true);
        _launch = _map.FindAction("Launch", true);
        _interact = _map.FindAction("Interact", true);
        _pause = _map.FindAction("Pause", true);

        _aim.performed += OnAim;
        _map.actionTriggered += OnAnyAction;
        _map.Enable();
    }

    protected override void OnDisable()
    {
        if (_map != null)
        {
            _aim.performed -= OnAim;
            _map.actionTriggered -= OnAnyAction;
            _map.Disable();
            _map = null;
        }
        base.OnDisable();
    }

    void Update()
    {
        if (_map == null) return;

        SetMove(_move.ReadValue<Vector2>());
        Latch(_launch, RunButton.Launch);
        Latch(_interact, RunButton.Interact);
        Latch(_pause, RunButton.Pause);

        if (_aimFromPointer)
        {
            if (aimCamera == null) aimCamera = Camera.main;
            Transform origin = aimOrigin != null ? aimOrigin : transform;
            if (RunAim.PointOnPlane(aimCamera, _pointerScreen, aimPlane, planeOffset, out Vector3 world))
                SetAimPoint(world, origin.position, aimPlane);
            else
                SetAim(Vector2.zero);
        }
        else
        {
            SetAim(_stickAim.magnitude >= aimStickThreshold ? _stickAim : Vector2.zero);
        }
    }

    void Latch(InputAction action, RunButton button)
    {
        // Press before held: a press and release inside one frame still latches, and ends not held.
        if (action.WasPressedThisFrame()) Press(button);
        SetHeld(button, action.IsPressed());
    }

    // Aim is a PassThrough action bound to a stick and to a pointer position. A Value action
    // would let the larger magnitude win, and a pointer position in pixels always out-shouts a
    // stick; PassThrough reports whichever control changed, and the device says which kind it is.
    void OnAim(InputAction.CallbackContext ctx)
    {
        Vector2 v = ctx.ReadValue<Vector2>();
        if (ctx.control.device is Pointer)
        {
            _pointerScreen = v;
            _aimFromPointer = true;
        }
        else
        {
            _stickAim = v;
            if (v.magnitude >= aimStickThreshold) _aimFromPointer = false;
        }
    }

    void OnAnyAction(InputAction.CallbackContext ctx)
    {
        if (ctx.phase != InputActionPhase.Performed && ctx.phase != InputActionPhase.Started) return;
        InputDevice device = ctx.control.device;
        // A resting hand moves a mouse; that must not flip the prompts away from the pad.
        if (ctx.action == _aim && device is Pointer) return;
        if (ctx.action == _aim && ctx.ReadValue<Vector2>().magnitude < aimStickThreshold) return;

        string scheme = SchemeOf(device);
        if (scheme == ActiveScheme) return;
        ActiveScheme = scheme;
        SchemeChanged?.Invoke(scheme);
    }

    static string SchemeOf(InputDevice device)
    {
        if (device is Touchscreen) return "Touch";
        if (!(device is Gamepad)) return "Keyboard&Mouse";
        // An on-screen stick or button is a Gamepad the Input System created itself, and it tags
        // that device with the "OnScreen" usage.
        foreach (var usage in device.usages)
            if (usage == "OnScreen") return "Touch";
        return "Gamepad";
    }
}
