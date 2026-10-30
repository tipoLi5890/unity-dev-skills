// Pickup — one thing the runner collects, by touch or by the interact press, counted exactly once
// and handed back to whoever pooled it. With it: PickupBag (PickupBag.cs), the smallest inventory
// that works — counts by item id — which is also what a locked gate asks for a key.
//
// Drop into the same Runtime assembly as PickupBag.cs and IInteractable.cs. Add Pickup to the
// pickup beside a trigger collider (2D or 3D) on its own layer, and PickupBag to the runner. No
// package needed; it uses the built-in physics and physics2d modules for the two trigger callbacks.
//
// Three rules it holds:
//   - the pickup decides it was taken, once: a runner made of two colliders still counts one
//   - a sensor is not a body: a trigger collider on the runner (an interactor's reach, a magnet
//     field) does not collect, only a solid collider or the magnet's own distance check does
//   - it never calls Destroy: it invokes Release, and inactive is the fallback
//
// Register with the probe where the game wires its harness:
//   GameProbe.Count("parcels", () => bag.CountOf("parcel"));
using System;
using System.Collections.Generic;
using UnityEngine;

public enum PickupMode { Touch, Interact }

/// <summary>What a pickup is handed to. Return false to refuse it — a full bag — and it stays in the world.</summary>
public interface IPickupReceiver
{
    bool Receive(string itemId, int amount);
}

[AddComponentMenu("Courier/Pickup")]
public class Pickup : InteractableBase
{
    [Header("Pickup")]
    [Tooltip("What the bag counts. Items are data: the id is the item.")]
    public string itemId = "parcel";
    public int amount = 1;
    [Tooltip("Touch: collected on contact. Interact: selected, prompted and pressed like a switch.")]
    public PickupMode mode = PickupMode.Touch;

    [Header("Magnet — Touch mode")]
    [Tooltip("Units at which it starts flying to the nearest bag. 0 is off; 1.5 suits a runner at 5 units/s.")]
    public float magnetRadius = 0f;
    [Tooltip("Units/s. Faster than the runner, or it trails behind for ever.")]
    public float magnetSpeed = 12f;
    [Tooltip("Units at which a magnetised pickup counts as collected.")]
    public float collectRadius = 0.3f;

    [Header("Persistence")]
    [Tooltip("Stable id for a pickup that stays taken across a save. Empty for anything that respawns.")]
    public string saveId = "";

    /// <summary>Raised once per collection, with the collector. Audio, feel, score and the save listen here.</summary>
    public static event Action<Pickup, GameObject> Collected;
    /// <summary>The save's answer to "was this one taken already?". Asked once, in Start, by a pickup with a saveId.</summary>
    public static Func<string, bool> AlreadyTaken;

    /// <summary>The pool's hook. Unassigned, the pickup deactivates itself.</summary>
    public Action<Pickup> Release;

    public bool Taken { get; private set; }

    PickupBag _pull;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        // Statics outlive a play session when domain reload is off.
        Collected = null;
        AlreadyTaken = null;
    }

    protected virtual void OnEnable()
    {
        // A pooled pickup is the same object again: forget the last life.
        Taken = false;
        _pull = null;
    }

    protected virtual void Start()
    {
        // In Start, not OnEnable: an object cannot deactivate itself while it is being activated.
        if (string.IsNullOrEmpty(saveId) || AlreadyTaken == null || !AlreadyTaken(saveId)) return;
        Taken = true;
        Leave();
    }

    protected override bool Allows(GameObject actor) => mode == PickupMode.Interact && !Taken;

    protected override bool OnInteract(GameObject actor) => TryCollect(actor);

    void OnTriggerEnter(Collider other)
    {
        if (mode != PickupMode.Touch || other.isTrigger) return;
        TryCollect(other.attachedRigidbody != null ? other.attachedRigidbody.gameObject : other.gameObject);
    }

    void OnTriggerEnter2D(Collider2D other)
    {
        if (mode != PickupMode.Touch || other.isTrigger) return;
        TryCollect(other.attachedRigidbody != null ? other.attachedRigidbody.gameObject : other.gameObject);
    }

    void Update()
    {
        if (Taken || mode != PickupMode.Touch || magnetRadius <= 0f) return;

        if (_pull == null || !_pull.isActiveAndEnabled)
            _pull = PickupBag.Nearest(transform.position, magnetRadius);
        if (_pull == null) return;

        // Once pulled it does not let go: a pickup that gives up at the rim reads as a miss.
        Vector3 to = _pull.transform.position;
        transform.position = Vector3.MoveTowards(transform.position, to, magnetSpeed * Time.deltaTime);
        if ((to - transform.position).sqrMagnitude <= collectRadius * collectRadius)
            TryCollect(_pull.gameObject);
    }

    /// <summary>Hand it to the collector. True exactly once per life of the pickup.</summary>
    public bool TryCollect(GameObject collector)
    {
        if (Taken || collector == null) return false;
        IPickupReceiver receiver = collector.GetComponentInParent<IPickupReceiver>();
        if (receiver == null) return false;
        if (!receiver.Receive(itemId, amount))
        {
            _pull = null;           // a full bag: stop chasing it
            return false;
        }

        Taken = true;               // before anything that could re-enter
        Collected?.Invoke(this, collector);
        Leave();
        return true;
    }

    void Leave()
    {
        if (Release != null) Release(this);
        else gameObject.SetActive(false);
    }
}
