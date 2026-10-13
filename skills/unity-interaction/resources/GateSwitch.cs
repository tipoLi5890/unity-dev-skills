// GateSwitch and GateTarget — a switch that drives gates by reference, and a gate that is a
// state machine whose collider changes with the state.
//
//   GateSwitch   an interactable (OneShot or Toggle) or a pressure plate (Held): it owns one
//                bool, On, and tells every target in its list what that bool now is
//   GateTarget   Closed → Opening → Open → Closing: it owns the panel's motion, the blocking
//                collider and the count of how many times it opened
//
// Drop into the same Runtime assembly as IInteractable.cs. Add GateSwitch to the switch beside a
// collider on the interactable layer; add GateTarget to the gate and assign its blocker. Works in
// 2D and 3D: assign whichever blocker the gate has. No package needed.
//
// Components added from code read their fields in Awake: build the object inactive, set the
// fields, then activate it.
//
// Register with the probe where the game wires its harness:
//   GameProbe.SetState(() => gate.State.ToString());
//   GameProbe.Count("gateOpens", () => gate.OpenCount);
//   GameProbe.Register("switchOn", () => gateSwitch.On);
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Events;

public enum GateState { Closed, Opening, Open, Closing }

[DisallowMultipleComponent]
[AddComponentMenu("Courier/Gate Target")]
public sealed class GateTarget : MonoBehaviour
{
    [Header("Motion")]
    [Tooltip("What moves. Empty means this transform.")]
    public Transform panel;
    [Tooltip("Local offset of the panel when fully open.")]
    public Vector3 openOffset = new Vector3(0f, 3f, 0f);
    [Tooltip("Seconds from closed to open, and back.")]
    public float travelSeconds = 1f;
    public bool startOpen = false;

    [Header("Collider — one of the two")]
    [Tooltip("3D: what stops the runner. Enabled in every state except Open.")]
    public Collider blocker;
    [Tooltip("2D: the same.")]
    public Collider2D blocker2D;
    [Tooltip("Layers that keep the gate from closing while they stand in the doorway. Empty closes regardless.")]
    public LayerMask keepClear = 0;

    public UnityEvent onOpening;
    public UnityEvent onOpened;
    public UnityEvent onClosing;
    public UnityEvent onClosed;

    /// <summary>Raised on every transition. A NavMesh obstacle, a light and the save listen here.</summary>
    public event Action<GateState> StateChanged;

    public GateState State { get; private set; } = GateState.Closed;
    /// <summary>Between two rest states. A switch that toggles refuses while this is true.</summary>
    public bool Busy => State == GateState.Opening || State == GateState.Closing;
    /// <summary>True while the doorway is shut to the runner.</summary>
    public bool Blocks => State != GateState.Open;
    /// <summary>How many times it left Closed. A probe count: "exactly once" is this being 1.</summary>
    public int OpenCount { get; private set; }
    /// <summary>0 closed, 1 open.</summary>
    public float Progress { get; private set; }

    readonly List<Collider2D> _inDoorway = new List<Collider2D>(4);
    Vector3 _closedLocal;
    Bounds _doorway;
    bool _wantClosed;
    bool _awake;
    bool _snapped;

    void Awake()
    {
        if (panel == null) panel = transform;
        _closedLocal = panel.localPosition;
        // Read now, while it is enabled and closed: a disabled collider reports empty bounds.
        if (blocker != null) _doorway = blocker.bounds;
        else if (blocker2D != null) _doorway = blocker2D.bounds;
        _awake = true;
        // A save restored before this Awake has already chosen the state; it wins over startOpen.
        if (startOpen && !_snapped) Snap(true); else Apply();
    }

    /// <summary>Ask for open or closed. Asking for what it already is, or is on its way to, does nothing.</summary>
    public void SetOpen(bool open)
    {
        if (open) Open(); else Close();
    }

    public void Open()
    {
        _wantClosed = false;
        if (State == GateState.Open || State == GateState.Opening) return;
        if (State == GateState.Closed) OpenCount++;
        Enter(GateState.Opening);
    }

    public void Close()
    {
        if (State == GateState.Closed || State == GateState.Closing) return;
        if (State == GateState.Open && DoorwayOccupied())
        {
            _wantClosed = true;         // closes when the doorway clears
            return;
        }
        _wantClosed = false;
        Enter(GateState.Closing);
    }

    /// <summary>Put it in a rest state with no motion and no events — for a loaded save.</summary>
    public void Snap(bool open)
    {
        _wantClosed = false;
        _snapped = true;
        Progress = open ? 1f : 0f;
        State = open ? GateState.Open : GateState.Closed;
        Apply();
    }

    void FixedUpdate()
    {
        if (State == GateState.Open && _wantClosed && !DoorwayOccupied()) Close();
        if (!Busy) return;

        float step = travelSeconds > 0f ? Time.fixedDeltaTime / travelSeconds : 1f;
        Progress = Mathf.Clamp01(Progress + (State == GateState.Opening ? step : -step));
        Apply();
        if (State == GateState.Opening && Progress >= 1f) Enter(GateState.Open);
        else if (State == GateState.Closing && Progress <= 0f) Enter(GateState.Closed);
    }

    void Enter(GateState next)
    {
        State = next;
        Apply();
        switch (next)
        {
            case GateState.Opening: onOpening?.Invoke(); break;
            case GateState.Open: onOpened?.Invoke(); break;
            case GateState.Closing: onClosing?.Invoke(); break;
            default: onClosed?.Invoke(); break;
        }
        StateChanged?.Invoke(next);
    }

    void Apply()
    {
        if (!_awake) return;
        panel.localPosition = _closedLocal + openOffset * Progress;
        // The collider follows the state, not the picture: it is back the step Closing starts.
        if (blocker != null) blocker.enabled = Blocks;
        if (blocker2D != null) blocker2D.enabled = Blocks;
    }

    bool DoorwayOccupied()
    {
        if (keepClear.value == 0) return false;
        if (blocker != null)
            return Physics.CheckBox(_doorway.center, _doorway.extents, Quaternion.identity, keepClear,
                                    QueryTriggerInteraction.Ignore);
        if (blocker2D == null) return false;
        var filter = new ContactFilter2D();
        filter.SetLayerMask(keepClear);
        filter.useTriggers = false;
        return Physics2D.OverlapBox(_doorway.center, _doorway.size, 0f, filter, _inDoorway) > 0;
    }
}

public enum SwitchMode { OneShot, Toggle, Held }

[AddComponentMenu("Courier/Gate Switch")]
public class GateSwitch : InteractableBase
{
    [Header("Switch")]
    [Tooltip("OneShot: on for good. Toggle: each use flips it. Held: on while something stands on it — a pressure plate, not pressable.")]
    public SwitchMode mode = SwitchMode.OneShot;
    [Tooltip("The gates it drives, assigned by reference. A name or a tag here is a bug waiting for a rename.")]
    public GateTarget[] targets = new GateTarget[0];
    [Tooltip("Toggle: refuse while any target is still moving, so a second press cannot reverse it half way.")]
    public bool lockWhileMoving = true;

    [Header("Lock")]
    [Tooltip("Item id the actor must carry. Empty is unlocked.")]
    public string requiredKey = "";
    [Tooltip("Spend the key on the first use.")]
    public bool consumeKey = true;
    [Tooltip("Shown in place of the prompt while the actor lacks the key.")]
    public string lockedPrompt = "Locked";

    [Header("Held mode")]
    [Tooltip("Layers whose bodies press the plate.")]
    public LayerMask pressedBy = ~0;

    /// <summary>Raised when On changes, with the new value.</summary>
    public event Action<bool> Switched;

    /// <summary>The one fact this switch owns, and the only thing a save stores for it.</summary>
    public bool On { get; private set; }
    public bool Unlocked { get; private set; }

    readonly List<Component> _pressing = new List<Component>(4);
    // Who asked last. The prompt has no actor argument, and "Locked" is true of an actor, not of
    // the switch: with two local players, give each its own prompt from CanInteract instead.
    GameObject _lastAsked;

    public override string Prompt => IsLockedFor(_lastAsked) ? lockedPrompt : prompt;

    protected override bool Allows(GameObject actor)
    {
        _lastAsked = actor;
        if (mode == SwitchMode.Held) return false;
        if (mode == SwitchMode.OneShot && On) return false;
        if (mode == SwitchMode.Toggle && lockWhileMoving && AnyTargetBusy()) return false;
        return !IsLockedFor(actor);
    }

    protected override bool OnInteract(GameObject actor)
    {
        if (!Unlocked && !string.IsNullOrEmpty(requiredKey))
        {
            IKeyHolder keys = actor != null ? actor.GetComponentInParent<IKeyHolder>() : null;
            if (keys == null || !keys.HasKey(requiredKey)) return false;
            if (consumeKey && !keys.UseKey(requiredKey)) return false;
        }
        Unlocked = true;
        Set(mode == SwitchMode.OneShot || !On);
        return true;
    }

    /// <summary>Restore from a save: the bool, and every target snapped to match with no motion and no events.</summary>
    public void Restore(bool on, bool unlocked)
    {
        On = on;
        Unlocked = unlocked;
        for (int i = 0; i < targets.Length; i++)
            if (targets[i] != null) targets[i].Snap(on);
    }

    bool IsLockedFor(GameObject actor)
    {
        if (Unlocked || string.IsNullOrEmpty(requiredKey)) return false;
        IKeyHolder keys = actor != null ? actor.GetComponentInParent<IKeyHolder>() : null;
        return keys == null || !keys.HasKey(requiredKey);
    }

    bool AnyTargetBusy()
    {
        for (int i = 0; i < targets.Length; i++)
            if (targets[i] != null && targets[i].Busy) return true;
        return false;
    }

    void Set(bool on)
    {
        if (On == on) return;
        On = on;
        for (int i = 0; i < targets.Length; i++)
            if (targets[i] != null) targets[i].SetOpen(on);
        Switched?.Invoke(on);
    }

    // ---- Held: a pressure plate. The plate's collider is a trigger; bodies are counted, not timed.

    void OnTriggerEnter(Collider other) => Pressed(other, other.isTrigger);
    void OnTriggerExit(Collider other) => _pressing.Remove(other);
    void OnTriggerEnter2D(Collider2D other) => Pressed(other, other.isTrigger);
    void OnTriggerExit2D(Collider2D other) => _pressing.Remove(other);

    void Pressed(Component other, bool isTrigger)
    {
        if (mode != SwitchMode.Held || isTrigger) return;
        if ((pressedBy.value & (1 << other.gameObject.layer)) == 0) return;
        if (!_pressing.Contains(other)) _pressing.Add(other);
    }

    void FixedUpdate()
    {
        if (mode != SwitchMode.Held) return;
        // A body disabled or pooled while standing on the plate sends no exit in 3D.
        for (int i = _pressing.Count - 1; i >= 0; i--)
            if (_pressing[i] == null || !_pressing[i].gameObject.activeInHierarchy) _pressing.RemoveAt(i);
        Set(_pressing.Count > 0);
    }
}
