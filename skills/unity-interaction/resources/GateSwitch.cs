// GateSwitch.cs — a switch that drives gates by reference. GateTarget.cs is the gate it drives: a
// state machine whose collider changes with the state.
//
//   GateSwitch   an interactable (OneShot or Toggle) or a pressure plate (Held): it owns one
//                bool, On, and tells every target in its list what that bool now is
//   GateTarget   (GateTarget.cs) Closed → Opening → Open → Closing: it owns the panel's motion,
//                the blocking collider and the count of how many times it opened
//
// Drop into the same Runtime assembly as GateTarget.cs and IInteractable.cs. Add GateSwitch to
// the switch beside a collider on the interactable layer; add GateTarget to the gate and assign
// its blocker. Works in 2D and 3D: assign whichever blocker the gate has. No package needed.
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
