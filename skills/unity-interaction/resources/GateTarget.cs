// GateTarget.cs — a gate that is a state machine whose collider changes with the state:
// Closed → Opening → Open → Closing. It owns the panel's motion, the blocking collider and the
// count of how many times it opened; GateSwitch.cs drives it by reference.
//
// Drop into the same Runtime assembly as GateSwitch.cs and IInteractable.cs. Add GateTarget to
// the gate and assign its blocker. Works in 2D and 3D: assign whichever blocker the gate has. No
// package needed.
//
// Components added from code read their fields in Awake: build the object inactive, set the
// fields, then activate it.
//
// Register with the probe where the game wires its harness:
//   GameProbe.SetState(() => gate.State.ToString());
//   GameProbe.Count("gateOpens", () => gate.OpenCount);
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
